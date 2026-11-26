Câu 1: Công ty dùng một tổ chức Google Cloud, muốn tách quyền IAM, hạn mức dịch vụ và theo dõi chi phí giữa môi trường dev và prod. Nên tổ chức tài nguyên ra sao?
A. Tạo hai subnet riêng trong cùng một project.
B. Tạo hai project riêng cho dev và prod.
C. Tạo hai zone riêng trong cùng một project.
D. Tạo hai service account cho dev và prod.
Đáp án đúng: B

Câu 2: Ứng dụng trong GKE cần đọc một bucket Cloud Storage mà không phân phối JSON key cho pod. Cách cấp danh tính nào phù hợp nhất?
A. Lưu JSON key trong Kubernetes Secret cho pod.
B. Gán quyền Storage Admin cho node service account.
C. Dùng Workload Identity Federation for GKE.
D. Gắn OAuth access token cố định vào image.
Đáp án đúng: C

Câu 3: Hai VM thuộc cùng một VPC Google Cloud nhưng chạy tại hai region; cần subnet riêng ở từng region. Mô tả nào đúng về VPC và subnet?
A. VPC là global; mỗi subnet nằm trong một region.
B. VPC nằm theo region; subnet là tài nguyên global.
C. Mỗi VPC chỉ được chứa subnet trong một zone.
D. Mỗi subnet trải đồng thời qua nhiều region.
Đáp án đúng: A

Câu 4: VM chỉ có IP nội bộ trong subnet cần truy cập API Cloud Storage, không triển khai Cloud NAT hay external IP. Cấu hình nào cần bật cho subnet?
A. Bật Private Google Access cho subnet.
B. Bật Cloud NAT và Cloud Router cho subnet.
C. Tạo VPC Network Peering với Cloud Storage.
D. Gắn external IP tĩnh vào VM trong subnet.
Đáp án đúng: A

Câu 5: Tác vụ tính toán theo lô có checkpoint, chấp nhận bị thu hồi và có thể chạy lại; muốn giảm giá VM so với on-demand. Loại Compute Engine nào hợp lý?
A. VM thường với cam kết chạy liên tục một năm.
B. Sole-tenant VM dành riêng phần cứng cho app.
C. VM với Persistent Disk và máy luôn hoạt động.
D. Spot VM với xử lý gián đoạn và chạy lại.
Đáp án đúng: D

Câu 6: Cơ sở dữ liệu do nhóm tự quản trị trên Compute Engine cần ổ block bền vững, chụp snapshot và vẫn còn dữ liệu khi VM dừng. Chọn loại nào?
A. Cloud Storage Standard theo mô hình object.
B. Persistent Disk gắn với VM Compute Engine.
C. Local SSD có vòng đời gắn với máy chủ.
D. Filestore cung cấp thư mục qua giao thức NFS.
Đáp án đúng: B

Câu 7: Nhóm cần triển khai ứng dụng Kubernetes và trực tiếp quản lý cấu hình node pool, kiểu máy cùng quyền truy cập hệ điều hành nút. Nên chọn gì?
A. GKE Autopilot để Google quản lý các node.
B. Cloud Run để triển khai container không quản node.
C. GKE Standard với node pool do nhóm cấu hình.
D. App Engine Standard với runtime được quản lý.
Đáp án đúng: C

Câu 8: Ứng dụng chạy trên Cloud Run vừa triển khai bản mới; cần thử 10% yêu cầu với revision mới, 90% ở bản trước. Tính năng nào hỗ trợ trực tiếp?
A. Cloud Build trigger cho lần build tiếp theo.
B. Cloud CDN tạo cache riêng cho mỗi phiên bản.
C. Cloud Scheduler chạy job theo lịch định kỳ.
D. Cloud Run chia lưu lượng theo revision.
Đáp án đúng: D

Câu 9: Cloud SQL for PostgreSQL cần tự chuyển sang instance dự phòng khi zone chính lỗi và phục vụ lại với downtime ngắn. Nên dùng cấu hình nào?
A. Cloud SQL HA với standby ở zone khác.
B. Cloud SQL read replica để tăng năng lực đọc.
C. Cloud SQL single-zone kèm backup hằng ngày.
D. Cloud SQL tăng vCPU cho primary instance.
Đáp án đúng: A

Câu 10: Nhóm phân tích cần chạy SQL tổng hợp trên hàng terabyte log, tách hạ tầng tính toán khỏi máy chủ giao dịch và không tự quản cluster. Chọn dịch vụ nào?
A. Cloud SQL PostgreSQL cho giao dịch OLTP.
B. Firestore lưu document cho ứng dụng web.
C. Bigtable phục vụ truy cập khóa hàng lớn.
D. BigQuery cho truy vấn phân tích SQL.
Đáp án đúng: D

Câu 11: Object Cloud Storage được đọc thường xuyên trong năm đầu, sau đó hầu như chỉ giữ để kiểm toán nhiều năm. Tự động giảm chi phí lưu bằng cách nào?
A. Bật versioning không giới hạn cho mọi object.
B. Dùng Lifecycle chuyển từ Standard sang Archive.
C. Bật CMEK để chuyển dữ liệu sang lớp giá rẻ.
D. Tăng số bản sao ở các region không cần thiết.
Đáp án đúng: B

Câu 12: Sự kiện đơn hàng phải được gửi tới dịch vụ hóa đơn và dịch vụ thông báo xử lý độc lập, từng bên có tiến độ nhận riêng. Nên dùng gì?
A. Cloud Tasks một queue chung cho hai worker.
B. Cloud Scheduler kích hoạt job theo lịch.
C. Pub/Sub topic với subscription riêng mỗi bên.
D. Cloud CDN nhân bản thông báo theo vùng.
Đáp án đúng: C

Câu 13: Pipeline CI đã build container image cho GKE và Cloud Run, cần nơi lưu image có quản lý phiên bản và quyền IAM để triển khai. Dịch vụ nào phù hợp?
A. Cloud Build lưu kết quả build và phân quyền.
B. Cloud Deploy lưu bản phát hành dưới dạng image.
C. Artifact Registry lưu image và kiểm soát IAM.
D. Cloud Storage bucket lưu image dưới dạng tar.
Đáp án đúng: C

Câu 14: Một API trên Cloud Run có tỷ lệ phản hồi 5xx cao hơn 2% trong 5 phút. Nhóm muốn tự động cảnh báo theo metric này. Nên dùng gì?
A. Cloud Monitoring alert theo metric lỗi.
B. Cloud Trace theo dõi từng yêu cầu truy cập.
C. Cloud Logging tạo log sink sang BigQuery.
D. Cloud Profiler ghi biểu đồ CPU theo hàm.
Đáp án đúng: A

Câu 15: Nhóm bảo mật muốn giới hạn việc cấp external IP cho VM trong mọi project thuộc cùng organization. Cơ chế kiểm soát nào phù hợp nhất?
A. IAM allow policy cấp Compute Viewer cho nhóm.
B. VPC firewall rule chặn mọi lưu lượng vào VM.
C. Cloud NAT chỉ cho VM truy cập Internet chiều ra.
D. Organization Policy constraint về external IP.
Đáp án đúng: D

Câu 16: Trưởng nhóm muốn nhận email khi chi phí Google Cloud dự báo của một project vượt 80% ngân sách tháng. Nên cấu hình ở đâu?
A. Cloud Monitoring uptime check và dashboard.
B. Cloud Billing budget với forecasted alerts.
C. Cloud Quotas tăng giới hạn API requests.
D. Cloud Logging sink xuất log sang bucket.
Đáp án đúng: B
