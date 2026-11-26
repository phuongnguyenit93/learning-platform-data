Câu 1: Trong kiến trúc Jenkins controller–agent, phân công nào đúng khi chạy pipeline?
A. Controller biên dịch mã; agent chỉ thu thập log build từ từng stage.
B. Controller giữ workspace; agent chỉ quản lý plugin.
C. Controller chạy test; agent chỉ tiếp nhận webhook.
D. Controller điều phối job; agent thực thi các bước build.
Đáp án đúng: D

Câu 2: Cấu trúc gốc hợp lệ của Declarative Jenkinsfile là gì?
A. `node { agent any; stages { ... } }`.
B. `pipeline { agent any; stages { ... } }`.
C. `pipeline { agent any; steps { ... } }`.
D. `stages { pipeline { agent any; steps { ... } } }`.
Đáp án đúng: B

Câu 3: Vì sao nên lưu Jenkinsfile trong repository cùng mã nguồn ứng dụng?
A. Để Jenkins tự thêm credential vào repository khi commit.
B. Để thay đổi pipeline được version và review cùng mã.
C. Để các agent dùng chung filesystem ở mọi job.
D. Để Jenkins tự cập nhật plugin khi commit mới.
Đáp án đúng: B

Câu 4: Trong stage CI của dự án Maven, lệnh nào chạy test và các bước xác minh đến pha `verify`?
A. Chạy `mvn -B package -DskipTests` trên agent CI.
B. Chạy `mvn -B dependency:resolve` trên agent.
C. Chạy `mvn -B verify` trên agent được cấp phát.
D. Chạy `mvn -B test-compile` trên agent.
Đáp án đúng: C

Câu 5: Bước nào trong Jenkins Pipeline dùng báo cáo JUnit XML để hiển thị số test đạt và thất bại?
A. Dùng `junit` để đọc kết quả kiểm thử từ XML.
B. Dùng `stash` để đọc kết quả kiểm thử từ XML.
C. Dùng `archiveArtifacts` để đếm test từ XML.
D. Dùng `fingerprint` để tổng hợp số test từ XML.
Đáp án đúng: A

Câu 6: Muốn lưu JAR để tải về từ trang lịch sử của bản build, bước nào phù hợp?
A. Dùng `junit` lưu JAR vào hồ sơ test của build.
B. Dùng `stash` giữ JAR cho mọi lượt build về sau trên CI.
C. Dùng `fingerprint` lưu JAR thành file tải về.
D. Dùng `archiveArtifacts` lưu JAR theo bản build.
Đáp án đúng: D

Câu 7: Job publish cần token registry. Cách cấp secret nào giảm phạm vi sử dụng?
A. Dùng `withCredentials` cấp secret trong bước cần thiết.
B. Đặt token trực tiếp trong lệnh `sh` đã commit ở Jenkinsfile.
C. Nhúng token vào JAR để job deploy có thể lấy lại.
D. Ghi token vào file cấu hình đã commit trong Git.
Đáp án đúng: A

Câu 8: Stage cần chạy trên agent có label `jdk21`. Khai báo Declarative nào chọn đúng agent?
A. `tools { jdk 'jdk21' }` trong stage.
B. `environment { NODE = 'jdk21' }` trong stage.
C. `agent { label 'jdk21' }` trong stage.
D. `options { label 'jdk21' }` trong stage.
Đáp án đúng: C

Câu 9: Trước khi nâng plugin Jenkins đang dùng cho pipeline production, nên làm gì?
A. Cập nhật hết plugin trên controller rồi xem log.
B. Chỉ nâng Jenkins core và giữ nguyên mọi plugin.
C. Kiểm tra tương thích, thử ở staging và sao lưu.
D. Gỡ các plugin không được gọi trực tiếp trong file.
Đáp án đúng: C

Câu 10: Trong multibranch Pipeline, muốn stage deploy chỉ chạy ở nhánh `main`, dùng điều kiện nào?
A. `when { buildingTag() }` của Declarative stage.
B. `when { branch 'main' }` của Declarative stage.
C. `when { changelog 'main' }` của Declarative stage.
D. `when { expression { true } }` của stage.
Đáp án đúng: B

Câu 11: Pipeline có giới hạn chạy tối đa 20 phút. Cấu hình Declarative nào đặt giới hạn này?
A. `options { retry(20) }` trong Jenkinsfile.
B. `options { quietPeriod(20) }` trong Jenkinsfile.
C. `options { disableConcurrentBuilds() }` của job.
D. `options { timeout(time: 20, unit: 'MINUTES') }`.
Đáp án đúng: D

Câu 12: Stage deploy production cần người vận hành phê duyệt trước khi tiếp tục. Bước nào phù hợp?
A. Dùng `when` để chờ thao tác xác nhận thủ công.
B. Dùng `retry` để chờ thao tác xác nhận thủ công.
C. Dùng `lock` để chờ thao tác xác nhận thủ công.
D. Dùng `input` để chờ thao tác phê duyệt thủ công.
Đáp án đúng: D

Câu 13: Build tạo file tạm cần dùng trên agent khác trong cùng lượt pipeline. Cơ chế nào phù hợp?
A. Dùng `stash` rồi `unstash` trong lượt pipeline.
B. Dùng `archiveArtifacts` rồi đọc từ biến `env`.
C. Dùng `junit` rồi `fingerprint` trên agent mới.
D. Dùng `checkout scm` để lấy file chưa commit.
Đáp án đúng: A

Câu 14: Hai bộ kiểm thử độc lập cần chạy đồng thời trong Declarative Pipeline. Thiết kế nào đúng?
A. Nối hai stage qua `post { success { ... } }`.
B. Cho cả hai stage dùng `retry` của pipeline.
C. Đặt hai nhánh kiểm thử trong block `parallel`.
D. Đặt hai stage cùng `agent` để tự chạy song song.
Đáp án đúng: C

Câu 15: Tại sao nhóm tích hợp Git webhook với Jenkins thay vì chỉ quét SCM theo lịch?
A. Webhook tự động cấp credential của Git cho job.
B. Webhook gửi sự kiện Git đến Jenkins để kích hoạt build.
C. Webhook bỏ qua bước checkout của các stage build.
D. Webhook tự động sửa lỗi trong Jenkinsfile khi push.
Đáp án đúng: B

Câu 16: Một stage test fail trên agent Linux. Nguồn nào giúp khoanh vùng nguyên nhân trước khi rerun?
A. Xem console log, stage thất bại và báo cáo test.
B. Đổi branch rồi chạy lại để bỏ qua stage lỗi.
C. Xóa workspace và coi như kiểm thử đã thành công.
D. Tăng số executor và đánh dấu job là thành công.
Đáp án đúng: A
