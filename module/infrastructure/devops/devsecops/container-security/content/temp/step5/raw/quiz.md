Câu 1: Nhóm cần giảm bề mặt tấn công của image Java dùng Maven để build. Cách đóng gói nào phù hợp?
A. Giữ Maven và toàn bộ build cache trong image chạy.
B. Dùng multi-stage, chỉ sao chép JAR vào image runtime.
C. Sao chép toàn bộ mã nguồn vào lớp image cuối.
D. Chạy Maven ngay khi container production khởi động.
Đáp án đúng: B

Câu 2: Tag `release` có thể được gán lại sau kiểm thử. Để triển khai đúng image đã duyệt, nên dùng gì?
A. Pull tag `release` theo lịch rồi giữ image cache.
B. Gán thêm tag `stable` nhưng không cố định digest.
C. Dùng timestamp push mới nhất trong registry đích.
D. Tham chiếu digest image đã kiểm thử và phê duyệt.
Đáp án đúng: D

Câu 3: Đội kiểm toán cần biết package và phiên bản hiện diện trong image. Tài liệu nào đáp ứng trực tiếp?
A. SBOM liệt kê thành phần phần mềm và phiên bản.
B. Chữ ký image liệt kê các quyền runtime của pod.
C. Log registry liệt kê dependency nhúng vào JAR.
D. Manifest deployment ghi chi tiết mọi package.
Đáp án đúng: A

Câu 4: Image từng được scan sạch nhưng xuất hiện CVE mới sau phát hành. Hành động nào phù hợp?
A. Chỉ quét lại khi một tag mới được tạo cho image.
B. Quét lại với dữ liệu CVE mới và đánh giá tác động.
C. Đổi tên tag để công cụ nhận image là bản mới.
D. Bỏ qua vì digest image không thay đổi sau scan.
Đáp án đúng: B

Câu 5: Admission policy phải xác định image đúng artifact được publisher tin cậy ký. Bước xác minh nào cần?
A. Chỉ so tên repository với danh sách registry cho phép.
B. Chỉ kiểm tra tag trùng mã version của release.
C. Kiểm chữ ký theo digest và danh tính người ký.
D. Chỉ kiểm tra TLS của đường truyền khi pull image.
Đáp án đúng: C

Câu 6: Ứng dụng Java không cần tài khoản root. `securityContext` nào trực tiếp ép tiến trình chạy non-root?
A. `runAsNonRoot: true` kèm `runAsUser` khác 0.
B. `readOnlyRootFilesystem: true` của container.
C. `allowPrivilegeEscalation: false` của container.
D. `automountServiceAccountToken: false` của pod.
Đáp án đúng: A

Câu 7: Container chỉ lắng nghe HTTP trên cổng 8080 và không cần quyền Linux đặc biệt. Cách quản lý capability nào hợp lý?
A. Giữ mặc định mọi capability của runtime để ổn định.
B. Thêm `NET_ADMIN` để bind được cổng HTTP 8080.
C. Drop `ALL`, chỉ add lại quyền khi chứng minh cần.
D. Bật `privileged` rồi giới hạn bằng cổng HTTP 8080.
Đáp án đúng: C

Câu 8: Pod đã bật `readOnlyRootFilesystem` nhưng ứng dụng cần ghi `/tmp` mà không dùng filesystem của node. Cách nào phù hợp?
A. Tắt `readOnlyRootFilesystem` để ghi được `/tmp`.
B. Đổi quyền `/tmp` ở Dockerfile sang ghi toàn bộ.
C. Mount hostPath thư mục gốc của host để ghi tạm.
D. Mount `emptyDir` tại `/tmp` và giữ rootfs read-only.
Đáp án đúng: D

Câu 9: Muốn áp bộ lọc syscall mặc định do container runtime cung cấp cho Pod, trường nào cần cấu hình?
A. `appArmorProfile.type: Unconfined` trong container.
B. `seccompProfile.type: Unconfined` của container.
C. `allowPrivilegeEscalation: false` của container.
D. `seccompProfile.type: RuntimeDefault` của pod.
Đáp án đúng: D

Câu 10: Cluster đã bật Pod Security Admission. Muốn từ chối Pod vi phạm mức Restricted trong namespace, dùng nhãn nào?
A. `pod-security.kubernetes.io/audit: restricted`.
B. `pod-security.kubernetes.io/enforce: restricted`.
C. `pod-security.kubernetes.io/warn: restricted`.
D. `pod-security.kubernetes.io/enforce: baseline`.
Đáp án đúng: B

Câu 11: Nhóm dùng Kubernetes Secret chứa khóa truy cập database. Nhận định nào đúng về bảo vệ dữ liệu?
A. Cần kiểm soát RBAC và mã hóa Secret ở nơi lưu.
B. Dữ liệu base64 của Secret đã được mã hóa an toàn.
C. Secret mặc định được mount vào mọi Pod trong namespace.
D. Secret luôn được ẩn khỏi log dù ứng dụng in ra.
Đáp án đúng: A

Câu 12: Với CNI hỗ trợ NetworkPolicy, muốn chỉ cho Pod API kết nối DB trên cổng 5432. Cách nào phù hợp?
A. Cho phép toàn bộ egress, chỉ lọc qua liveness probe.
B. Default-deny egress rồi mở kết nối tới DB:5432.
C. Chặn mọi ingress của API nhưng giữ egress mặc định.
D. Cấu hình ServiceAccount thay cho chính sách egress.
Đáp án đúng: B

Câu 13: Pod xử lý ảnh không gọi Kubernetes API. Cách nào giảm nguy cơ lộ API token mặc định?
A. Đặt `automountServiceAccountToken: false` cho Pod.
B. Cho ServiceAccount quyền `cluster-admin` để tránh lỗi.
C. Ghi token vào Docker image để bỏ mount tự động.
D. Đặt `imagePullPolicy: Never` ở container.
Đáp án đúng: A

Câu 14: Runtime phát hiện Java service bất ngờ tạo shell và gọi ra địa chỉ lạ. Hành động đầu tiên hợp lý?
A. Chỉ restart pod và bỏ qua tiến trình vừa phát hiện.
B. Tắt rule runtime vì Java có thể khởi tạo shell.
C. Chỉ scan lại image, giữ pod nghi vấn hoạt động.
D. Cô lập pod, giữ bằng chứng và điều tra kết nối.
Đáp án đúng: D

Câu 15: Phát hiện token CI có quyền push lên registry đã lộ. Ưu tiên ứng phó nào đúng?
A. Đổi tag của các image mà không thay token bị lộ.
B. Chỉ tắt pipeline CI, giữ token để điều tra sau.
C. Thu hồi token, giới hạn quyền và kiểm tra audit.
D. Xóa cache runner để token hết hiệu lực ở registry.
Đáp án đúng: C

Câu 16: Image production có CVE ở base image và upstream đã phát hành bản vá. Làm gì để xử lý rủi ro?
A. Thay tag image cũ bằng version mới mà không build.
B. Sửa SBOM để ghi phiên bản base image đã vá rồi deploy.
C. Rebuild với base đã vá, quét lại và phát hành digest mới.
D. Giữ digest hiện tại, thêm rule NetworkPolicy cho pod.
Đáp án đúng: C
