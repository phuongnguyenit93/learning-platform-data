Một Deployment đặt replicas bằng 4; quản trị viên xóa thủ công một Pod đang hoạt động, còn cluster đủ tài nguyên. Thành phần nào sẽ đưa số replica trở lại trạng thái mong muốn?
A. Kubelet khởi động lại chính Pod đã bị xóa để giữ nguyên định danh cũ.
B. Service tạo thêm một Pod mới khi số endpoint sẵn sàng bị giảm.
C. ReplicaSet tạo Pod thay thế để đưa số replica về trạng thái yêu cầu.
D. Scheduler tự tăng số replica của Deployment sau khi phát hiện thiếu.
Đáp án đúng: C

Một Pod vẫn Pending với sự kiện Insufficient cpu mặc dù CPU thực tế trên nhiều node đang nhàn rỗi. Scheduler chủ yếu dựa vào thông tin nào để đánh giá khả năng bố trí Pod?
A. CPU requests so với tài nguyên còn cấp phát được trên từng node.
B. CPU đang dùng thực tế so với mức CPU trung bình của cả cluster.
C. Tổng CPU limits của mọi container đang chạy trong cùng namespace.
D. Tổng số core vật lý chưa sử dụng tại thời điểm bắt đầu rollout.
Đáp án đúng: A

Một Pod API hiển thị Running nhưng readiness probe liên tục thất bại trong lúc nạp dữ liệu. Với Service thông thường chọn Pod này bằng nhãn, điều gì xảy ra khi chưa đạt readiness?
A. Pod không được chọn làm endpoint sẵn sàng của Service tới khi probe đạt.
B. Container bị kubelet khởi động lại ngay khi readiness probe thất bại.
C. Deployment xóa Pod tức thời và giảm số replica mong muốn xuống.
D. Service vẫn chuyển yêu cầu đến Pod vì trạng thái Pod đang là Running.
Đáp án đúng: A

Một Pod ở namespace default cần gọi Service tên orders tại cổng 8080 trong namespace billing; cluster dùng miền DNS mặc định cluster.local. Tên DNS nào xác định đúng Service đích mà không phụ thuộc địa chỉ IP của Pod?
A. orders.default.svc.cluster.local vì client đang ở namespace default.
B. orders vì DNS sẽ tìm Service có tên trùng trên mọi namespace.
C. localhost vì các Pod trong cluster cùng chia sẻ địa chỉ loopback.
D. orders.billing.svc.cluster.local vì Service thuộc namespace billing.
Đáp án đúng: D

Nhóm dữ liệu cần chạy ba replica của một hệ thống có trạng thái; mỗi replica cần danh tính mạng ổn định và một PVC riêng vẫn tồn tại khi Pod được thay thế. Loại workload nào phù hợp nhất?
A. Deployment kết hợp emptyDir để giữ dữ liệu riêng khi Pod đổi node.
B. DaemonSet kết hợp hostPath để mỗi bản sao có tên mạng cố định.
C. StatefulSet dùng volumeClaimTemplates để mỗi bản sao có PVC riêng.
D. Job dùng PersistentVolume chung để duy trì thứ tự bản sao khởi động.
Đáp án đúng: C

Một Pod cần gắn PVC đã Bound với PV nằm trên ổ đĩa chỉ hỗ trợ vùng A, nhưng Pod dự kiến chạy tại vùng B và không thể gắn volume. Cần kiểm tra yếu tố nào trước tiên?
A. Quyền RBAC đọc PVC của ServiceAccount khi container vừa khởi động.
B. Tùy chọn mở rộng dung lượng của StorageClass đang dùng cho volume.
C. Ràng buộc topology của PV với vùng mà volume có thể được gắn.
D. Nhãn của Service selector đối với những Pod đang sử dụng PVC.
Đáp án đúng: C

Deployment có tám replica và RollingUpdate cấu hình maxUnavailable bằng 2, maxSurge bằng 1. Phát biểu nào mô tả đúng các giới hạn này trong quá trình cập nhật?
A. Tối đa một replica tạm không sẵn sàng, và tạo thêm hai Pod trên mức tám.
B. Tối đa hai replica tạm không sẵn sàng, và thêm một Pod trên mức tám.
C. Chỉ hai replica được chạy cùng lúc, và một Pod dự phòng được giữ lại.
D. Mỗi đợt bắt buộc xóa hai Pod cũ rồi mới tạo một Pod thay thế.
Đáp án đúng: B

Một dịch vụ worker tiêu thụ hàng đợi; hàng đợi tăng rất nhanh nhưng mức CPU Pod thấp do phải chờ I/O. HPA hiện chỉ theo CPU không tăng replica. Hướng đánh giá nào phù hợp nhất?
A. Tăng CPU limit của Pod để HPA tự đo được số thông điệp đang chờ.
B. Giảm CPU request xuống rất thấp để HPA bắt buộc tạo Pod mới.
C. Tăng số readiness probe để HPA tính lượng tác vụ theo tốc độ HTTP.
D. Dùng metric phản ánh hàng đợi và kiểm tra khả năng cấp thêm node.
Đáp án đúng: D

Một ServiceAccount của pipeline chỉ cần sửa Deployment ở namespace dev mà không được thay tài nguyên ở namespace prod. Cách cấp quyền nào phù hợp nguyên tắc tối thiểu?
A. ClusterRoleBinding gắn cluster-admin để ServiceAccount sửa Deployment.
B. NetworkPolicy cho phép ServiceAccount kết nối tới Kubernetes API.
C. RoleBinding trỏ tới cluster-admin để có mọi quyền trong namespace dev.
D. Role cấp patch/update Deployment tại dev, gắn bằng RoleBinding.
Đáp án đúng: D

Nhóm bảo mật muốn chỉ cho các Pod frontend kết nối đến cổng API của Pod backend trong cùng cluster. Điều kiện nào phù hợp để Kubernetes thực thi kiểm soát mạng này?
A. CNI hỗ trợ NetworkPolicy và ingress chỉ cho frontend vào backend.
B. Service kiểu ClusterIP tự chặn các Pod không mang nhãn frontend.
C. Role chỉ cấp quyền get Pod frontend để kiểm soát kết nối mạng.
D. Secret trong namespace backend giúp chặn đường truyền từ Pod khác.
Đáp án đúng: A

Một Pod liên tục hiển thị CrashLoopBackOff sau khi cập nhật image; container khởi động rồi thoát với mã khác không. Thao tác chẩn đoán nào giúp xác định nguyên nhân sát nhất?
A. Xem log scheduler vì scheduler trực tiếp khởi động tiến trình trong Pod.
B. Xem sự kiện Pod và log container của lần chạy trước để tìm lỗi.
C. Xem endpoint của Service vì Service ghi nhận mã thoát của container.
D. Xem trạng thái HPA vì HPA ghi nguyên nhân mọi lần thoát của Pod.
Đáp án đúng: B

Một container có giới hạn bộ nhớ 512 MiB, tiến trình tăng tiêu thụ vượt giới hạn và trạng thái lần kết thúc gần nhất ghi OOMKilled. Diễn giải nào phù hợp nhất?
A. Container bị chấm dứt do vượt giới hạn bộ nhớ mà cgroup áp dụng.
B. Pod bị scheduler từ chối vì requests vượt tài nguyên còn trống.
C. Readiness probe đánh dấu Pod chưa sẵn sàng nên kubelet xóa Pod.
D. Service từ chối kết nối do không còn endpoint hợp lệ cho Pod.
Đáp án đúng: A

Một ứng dụng cần 140 giây khởi tạo dữ liệu nhưng liveness probe bắt đầu sau 15 giây và liên tục khiến container khởi động lại. Cách dùng probe nào phù hợp nhất?
A. Tăng maxSurge của Deployment để container có thêm thời gian khởi tạo.
B. Chỉ thêm readiness probe, giữ nguyên liveness probe đang thất bại.
C. Thêm startup probe để trì hoãn liveness tới khi ứng dụng khởi tạo.
D. Thêm PodDisruptionBudget để cấm kubelet khởi động lại container.
Đáp án đúng: C

CronJob chạy mỗi 5 phút nhưng mỗi Job thường cần 12 phút; yêu cầu là không cho hai Job của cùng CronJob chạy đồng thời. concurrencyPolicy: Forbid có ý nghĩa gì?
A. Các lịch bị bỏ qua được xếp hàng để luôn chạy bù khi Job hoàn tất.
B. Lượt mới bị bỏ qua khi Job cũ còn chạy, không dừng Job hiện tại.
C. Mọi lịch vẫn tạo Job song song để tránh bỏ sót lần kích hoạt.
D. Job đang chạy bị thay thế bằng Job mới ở mỗi mốc lịch tiếp theo.
Đáp án đúng: B

Deployment có năm Pod khỏe mạnh, PodDisruptionBudget yêu cầu minAvailable bằng 4. Khi quản trị viên drain một node đang chứa Pod, phát biểu nào mô tả đúng tác dụng của PDB?
A. PDB tự tạo thêm Pod trước khi bất kỳ node nào được phép drain.
B. Eviction có thể bị chặn nếu làm số Pod khả dụng xuống dưới bốn.
C. Node mất nguồn cũng không thể làm mất Pod khi PDB có hiệu lực.
D. PDB tự tăng replicas từ năm lên sáu nhằm bù trừ bảo trì node.
Đáp án đúng: B

Nhóm đã tạo đối tượng Ingress có luật định tuyến host và TLS đến Service kiểu ClusterIP, nhưng cluster chưa cài thành phần xử lý Ingress. Điều gì còn thiếu để luật này được áp dụng?
A. Service phải đổi thành ExternalName thì Ingress mới đọc được backend.
B. Deployment phải dùng hostNetwork để endpoint công khai được định tuyến.
C. Ingress cần một Pod cùng tên để Kubernetes tự cấu hình cân bằng tải.
D. Cần Ingress controller để thực thi các quy tắc định tuyến và TLS.
Đáp án đúng: D
