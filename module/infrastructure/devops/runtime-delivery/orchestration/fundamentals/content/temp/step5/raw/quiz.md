Deployment khai báo năm replica nhưng sau khi một node lỗi chỉ còn ba Pod hoạt động. Cơ chế nào đưa workload về trạng thái mong muốn?
A. Scheduler trực tiếp tạo một Deployment mới mỗi khi số replica đang chạy bị giảm.
B. Kubelet tự sửa trường replicas của Deployment theo số Pod hiện còn trên node.
C. ReplicaSet tạo Pod thay thế, còn scheduler chọn node phù hợp cho những Pod mới.
D. Service tạo các Pod thay thế từ EndpointSlice khi một endpoint không còn sẵn sàng.
Đáp án đúng: C

Một Pod Pending dù mức CPU thực dùng của node thấp; sự kiện cho biết không node nào đủ memory request. Cách giải thích nào đúng?
A. Scheduler so resource requests với allocatable còn lại, không chỉ mức dùng thực tế.
B. Scheduler xét resource limits so với CPU dùng trung bình trong vài phút gần nhất.
C. Kubelet dùng readiness probe để chọn node thích hợp trước khi tạo đối tượng Pod.
D. Service chọn node dựa trên số endpoint Ready trước khi scheduler đưa ra quyết định.
Đáp án đúng: A

Pod của API bị xóa thủ công, trong khi Deployment vẫn khai báo ba replica. Điều gì thường xảy ra tiếp theo?
A. API server phục hồi đúng đối tượng Pod đã xóa và giữ nguyên UID cũ của Pod.
B. Scheduler khôi phục container cũ vào cùng node mà không tạo một đối tượng Pod mới.
C. Service sinh một Pod mới để duy trì số endpoint theo cấu hình của Service.
D. ReplicaSet tạo Pod thay thế có danh tính mới để đáp ứng số replica mong muốn.
Đáp án đúng: D

Service dùng selector app=orders nhưng các Pod mới được đổi nhãn thành app=checkout. Hệ quả nào phù hợp nhất?
A. Service không chọn được Pod mới làm endpoint dù địa chỉ ClusterIP vẫn còn tồn tại.
B. Kubernetes tự đổi selector của Service theo nhãn mới nhất trên các Deployment.
C. ClusterIP sẽ tự chuyển thành địa chỉ IP của Pod đầu tiên thuộc Deployment mới.
D. Kubelet sẽ chuyển lưu lượng tới mọi Pod Ready mà không cần xét selector của Service.
Đáp án đúng: A

Ứng dụng còn chạy nhưng tạm mất kết nối database, có thể phục hồi mà không cần khởi động lại. Probe nào phù hợp để ngừng nhận lưu lượng?
A. Liveness thất bại để bắt container khởi động lại cho tới khi database sẵn sàng.
B. Readiness thất bại để Pod tạm ngừng nhận lưu lượng qua endpoint của Service.
C. Startup thất bại liên tục để ngăn Pod nhận request trong suốt vòng đời ứng dụng.
D. Heartbeat của node thất bại để chuyển mọi Pod sang node khác khi database lỗi.
Đáp án đúng: B

Một Pod xử lý báo cáo cần giữ dữ liệu qua các lần tạo lại Pod. Nhận định nào đúng về PersistentVolumeClaim?
A. PVC lưu bản sao image trên node để các Pod mới không cần tải lại từ registry.
B. PVC đồng bộ tệp ứng dụng vào ConfigMap và phục hồi chúng mỗi khi Pod khởi chạy.
C. PVC yêu cầu tài nguyên lưu trữ để Pod gắn volume có vòng đời độc lập với Pod.
D. PVC tự sao chép dữ liệu tới mọi availability zone nhờ định danh Pod ổn định.
Đáp án đúng: C

Deployment có 10 replica, maxSurge=2 và maxUnavailable=1. Bỏ qua Pod đang chấm dứt, cặp giới hạn nào đúng khi rolling update?
A. Tối đa 11 Pod trong rollout và tối thiểu 8 Pod phải ở trạng thái Available.
B. Tối đa 10 Pod trong rollout và tối thiểu 9 Pod phải ở trạng thái Available.
C. Tối đa 12 Pod trong rollout và tối thiểu 8 Pod phải ở trạng thái Available.
D. Tối đa 12 Pod khi rollout, với ít nhất 9 Pod vẫn ở trạng thái Available.
Đáp án đúng: D

Namespace có NetworkPolicy chặn egress mặc định. Pod vẫn Ready nhưng không phân giải được tên miền qua DNS. Giải thích nào đúng?
A. Readiness không thể thành công nếu DNS bị chặn, kể cả probe không truy cập DNS.
B. Egress tới DNS có thể bị chặn; Pod Ready không chứng minh DNS đang thông suốt.
C. Các gói DNS luôn vượt qua NetworkPolicy nếu máy chủ DNS nằm trong kube-system.
D. Pod bị chặn egress sẽ mất IP nên readiness probe không thể chạy thành công.
Đáp án đúng: B

HPA theo CPU utilization của các Pod có một container. CPU request tăng gấp đôi, CPU thực dùng giữ nguyên. Điều gì xảy ra với utilization?
A. Utilization tăng gấp đôi vì scheduler dự phòng nhiều CPU hơn trước khi đặt Pod.
B. Utilization giữ nguyên vì HPA chỉ so CPU đang dùng với CPU limit của container.
C. Utilization không thể đo vì HPA loại mọi Pod vừa thay đổi resource requests.
D. Utilization có xu hướng giảm một nửa vì CPU sử dụng được so với CPU request.
Đáp án đúng: D

API server từ chối tạo thêm Pod với lỗi exceeded quota dù cluster còn node rảnh. Nhận định nào là chính xác?
A. ResourceQuota giới hạn tổng requests hoặc số lượng đối tượng trong namespace.
B. HPA tự chuyển các Pod mới sang namespace khác khi namespace cũ đã hết quota.
C. Kubelet tăng quota tự động khi tổng allocatable trên các node còn đủ tài nguyên.
D. ServiceAccount được phép tạo Pod có thể bỏ qua ResourceQuota của namespace.
Đáp án đúng: A

Controller dùng ServiceAccount ops-bot tại namespace dev và chỉ cần quyền đọc Pod ở dev. Cách cấp RBAC nào phù hợp nhất?
A. Gắn ClusterRoleBinding cho ops-bot để đọc mọi Pod trong toàn bộ các namespace.
B. Gắn RoleBinding cho ops-bot với quyền cập nhật Deployment thay vì đọc Pod.
C. Role cho get/list/watch Pod ở dev, cùng RoleBinding liên kết Role với ops-bot.
D. Tạo Role đọc Pod ở dev để quyền tự động mở rộng sang mọi namespace khác.
Đáp án đúng: C

PodDisruptionBudget đặt minAvailable=3 và dịch vụ hiện đúng ba Pod Ready. Điều gì có thể xảy ra khi drain node chứa một Pod đó?
A. Drain chắc chắn thành công vì Pod thay thế luôn được lập lịch trước khi eviction.
B. PDB chỉ bảo vệ trước node chết đột ngột nên không ảnh hưởng bảo trì chủ động.
C. Scheduler tự giảm minAvailable trong lúc drain rồi đặt lại khi bảo trì hoàn tất.
D. Eviction tự nguyện có thể bị từ chối đến khi đáp ứng được số Pod Available.
Đáp án đúng: D

Một cơ sở dữ liệu ba replica cần tên mạng ổn định và lưu trữ riêng cho từng replica. Workload controller nào phù hợp nhất?
A. Deployment kết hợp volume dùng chung và một hostname duy nhất cho toàn bộ replica.
B. StatefulSet với định danh Pod ổn định và mỗi replica có volume claim riêng.
C. DaemonSet tạo một Pod database trên mỗi node cho dù chỉ cần ba replica.
D. Job tạo lần lượt ba Pod rồi kết thúc sau khi các Pod bắt đầu chạy database.
Đáp án đúng: B

HPA muốn tăng từ sáu lên mười hai replica nhưng Pod mới Pending vì không còn node đủ requests. Thành phần nào có thể mở rộng số node?
A. Cluster Autoscaler hoặc bộ tự cấp node tương đương, nếu hạ tầng có đủ quota.
B. CoreDNS khi số endpoint của Service vượt quá số địa chỉ mà DNS có thể trả về.
C. NetworkPolicy controller khi phát hiện Pod Pending chưa có địa chỉ IP để kết nối.
D. Deployment controller trực tiếp cấp máy ảo mới mỗi khi chưa đặt được Pod lên node.
Đáp án đúng: A

Rollout của Deployment kẹt vì Pod mới không qua readiness, trong khi Pod cũ vẫn Ready. Dữ liệu nào giúp chẩn đoán đúng tiến độ?
A. Chỉ trạng thái ClusterIP và lượng truy vấn DNS đã gửi tới namespace trong kỳ.
B. Chỉ số image được cache tại node cùng thời gian tải từ registry của từng Pod.
C. Replica mong muốn, đã cập nhật, khả dụng, kèm events và tình trạng probe Pod.
D. Số lượng Secret của namespace cùng tuổi PVC đang được workload sử dụng.
Đáp án đúng: C

Nhóm lưu khóa truy cập đối tác trong ConfigMap vì chỉ có Pod nội bộ sử dụng. Nhận định nào đúng về bảo vệ dữ liệu?
A. ConfigMap tự mã hóa dữ liệu và chỉ giải mã khi tiến trình bên trong Pod đọc tệp.
B. ConfigMap không dành cho bí mật; phải kiểm soát quyền đọc và dữ liệu lưu trữ.
C. ConfigMap chỉ nằm trong bộ nhớ Pod nên không thể truy cập thông qua API server.
D. ConfigMap tự cấp quyền riêng cho từng khóa mà không cần kiểm soát quyền RBAC.
Đáp án đúng: B
