Câu 1: Ứng dụng có VM ở East US và Storage Account ở West Europe, cùng vòng đời trong một subscription. Cách dùng Resource Group nào đúng?
A. Buộc hai tài nguyên của nhóm cùng chạy tại một Azure region duy nhất.
B. Đặt hai tài nguyên vào cùng Resource Group dù chúng khác region.
C. Dùng Resource Group để chứa tài nguyên từ nhiều subscription.
D. Đưa hai tài nguyên vào cùng VNet rồi mới tạo Resource Group.
Đáp án đúng: B

Câu 2: Nhân viên kiểm toán chỉ cần xem cấu hình tài nguyên trong một Resource Group và không được sửa. Cấp quyền nào phù hợp nhất?
A. Gán Contributor ở Resource Group để xem toàn bộ cấu hình.
B. Gán Reader ở subscription để xem mọi Resource Group.
C. Gán Reader ở đúng Resource Group cần được kiểm toán.
D. Gán User Access Administrator ở Resource Group đó.
Đáp án đúng: C

Câu 3: Web API trên Azure App Service cần đọc secret trong Key Vault mà không lưu client secret trong mã nguồn. Cấu hình nào phù hợp?
A. Lưu secret trong file cấu hình rồi commit vào repository riêng.
B. Bật managed identity của App Service và cấp quyền đọc Key Vault.
C. Bật public network access của Key Vault để API tự lấy secret.
D. Dùng storage account key làm token xác thực với Key Vault.
Đáp án đúng: B

Câu 4: VM chứa CSDL tại subnet riêng chỉ nên nhận TCP 1433 từ subnet ứng dụng. Cách kiểm soát lưu lượng nào phù hợp?
A. Đặt NSG allow từ subnet ứng dụng và deny nguồn khác trên TCP 1433.
B. Thêm outbound NSG rule TCP 1433 từ CSDL tới subnet ứng dụng.
C. Thêm route mặc định của subnet CSDL ra cổng Internet.
D. Cho phép inbound TCP 1433 từ 0.0.0.0/0 vào VM chứa CSDL.
Đáp án đúng: A

Câu 5: Các VM phục vụ website cần tự tăng số instance khi CPU cao, giảm khi tải thấp và có cân bằng tải. Nên triển khai gì?
A. Dùng Availability Set với số VM cố định sau load balancer.
B. Dùng Azure Load Balancer tự tạo VM khi CPU vượt ngưỡng.
C. Dùng Availability Zone tự nhân bản VM khi truy cập tăng.
D. Dùng Virtual Machine Scale Sets, autoscale và load balancing.
Đáp án đúng: D

Câu 6: API .NET cần triển khai mà không quản trị hệ điều hành và muốn thử bản mới qua deployment slot. Nên chọn dịch vụ nào?
A. Dùng Azure App Service với deployment slots cho staging.
B. Dùng Azure VMs rồi tự quản lý các bản vá hệ điều hành.
C. Dùng Azure Batch để chạy API như một tác vụ nền.
D. Dùng Azure Container Instances rồi tự tạo phiên bản slot.
Đáp án đúng: A

Câu 7: Khách hàng chỉ cần tải một file từ private Azure Blob container trong 10 phút, không được cấp account key. Cách chia sẻ nào đúng?
A. Bật public access cho container rồi khóa lại sau 10 phút.
B. Cấp role Storage Blob Data Owner để khách tự tạo link tải.
C. Chia sẻ account key của Storage Account qua kết nối HTTPS.
D. Tạo SAS quyền Read cho blob và đặt hết hạn sau 10 phút.
Đáp án đúng: D

Câu 8: Tệp trên Azure Blob thường được đọc trong 30 ngày đầu, sau đó rất ít truy cập nhưng phải lưu thêm một năm. Nên giảm chi phí thế nào?
A. Chuyển toàn bộ sang Azure Files Premium để lưu trữ lâu dài.
B. Bật soft delete rồi giữ nguyên lớp Hot trong suốt một năm.
C. Đặt lifecycle rule chuyển từ Hot sang Cool sau 30 ngày.
D. Chuyển toàn bộ tệp sang Archive ngay khi người dùng tải lên.
Đáp án đúng: C

Câu 9: Azure SQL Database phải phục hồi khi cả region chính gặp sự cố và ứng dụng cần endpoint chuyển sang vùng dự phòng. Cách nào phù hợp?
A. Cấu hình failover group với database thứ cấp ở region khác.
B. Bật zone redundancy cho database chỉ trong region hiện tại.
C. Tăng vCore cho database chính để tránh lỗi mất cả region.
D. Dùng long-term retention thay cho bản sao thứ cấp trực tuyến.
Đáp án đúng: A

Câu 10: Ứng dụng cần tự tạo ảnh thu nhỏ gần như ngay sau khi có blob mới mà không duy trì VM chạy thường trực. Cách nào phù hợp?
A. Dùng Timer Trigger quét Blob Storage mỗi giờ để xử lý.
B. Dùng Azure Monitor Activity Log theo dõi thao tác quản trị VM.
C. Dùng Event Grid báo BlobCreated để kích hoạt Azure Function.
D. Dùng NSG flow log gọi hàm khi container có tệp mới.
Đáp án đúng: C

Câu 11: AKS cần kéo container image riêng tư từ Azure Container Registry (ACR), tuân thủ quyền tối thiểu. Cấp quyền nào đúng?
A. Gán AcrPush cho mọi tài khoản người dùng của cluster.
B. Gán Owner ở subscription cho tất cả VM node của AKS.
C. Bật anonymous pull trên ACR để Pod tải image không cần quyền.
D. Gán AcrPull trên ACR cho danh tính kubelet của AKS.
Đáp án đúng: D

Câu 12: API qua nhiều microservice bị tăng độ trễ p95, nhóm muốn tìm bước xử lý chậm trong từng request. Nên dùng công cụ nào?
A. Xem Azure Activity Log để tìm trace HTTP xuyên các dịch vụ.
B. Dùng Network Watcher để xem thời gian từng hàm ứng dụng.
C. Xem Azure Cost Management để tìm request HTTP lỗi.
D. Dùng Application Insights xem request, dependency và trace.
Đáp án đúng: D

Câu 13: Tổ chức muốn ngăn việc tạo Storage Account bật public network access trong subscription. Cơ chế quản trị nào phù hợp?
A. Gán Reader ở subscription cho tất cả nhân viên triển khai.
B. Gán Azure Policy hiệu ứng deny đối với public network access.
C. Dùng NSG của VNet để chặn truy cập Internet vào các Storage Account.
D. Tạo Cost Management budget để chặn cấu hình sai.
Đáp án đúng: B

Câu 14: Đội vận hành đã backup Azure VM hằng ngày và cần xác nhận khả năng phục hồi trong RTO 60 phút. Cách kiểm chứng nào đúng?
A. Thử restore VM vào mạng cô lập và đo thời gian khôi phục.
B. Chỉ đọc dashboard backup job và đếm số lần thành công.
C. Tăng số bản backup mỗi ngày trong Recovery Services vault.
D. Tăng retention của bản backup mà không thử phục hồi.
Đáp án đúng: A

Câu 15: Nhiều VM và Storage Account thuộc các dự án khác nhau trong một subscription. Nhóm muốn xem chi phí theo dự án và cảnh báo vượt ngân sách. Nên làm gì?
A. Đổi tên từng VM theo dự án rồi xem hóa đơn toàn subscription.
B. Gắn tag dự án, nhóm chi phí theo tag và đặt budget alert.
C. Tạo NSG riêng từng dự án rồi phân bổ phí dựa trên NSG.
D. Gán RBAC Contributor để hệ thống tự chia phí theo thành viên.
Đáp án đúng: B

Câu 16: Quản trị viên đăng nhập Azure Portal phải xác thực MFA theo chính sách cho một nhóm Entra ID. Nên cấu hình tính năng nào?
A. Dùng NSG chặn mọi đăng nhập Azure Portal từ ngoài văn phòng.
B. Dùng Azure Policy để ép MFA khi đăng nhập của quản trị viên.
C. Dùng Entra Conditional Access yêu cầu MFA cho nhóm admin.
D. Gán Owner ở subscription để buộc quản trị viên dùng MFA.
Đáp án đúng: C
