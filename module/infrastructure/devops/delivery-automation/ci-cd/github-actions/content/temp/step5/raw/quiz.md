Câu 1: Một workflow YAML đã commit nhưng GitHub Actions không nhận diện. Nên đặt file ở đường dẫn nào?
A. `.github/actions/ci.yml`.
B. `.github/workflows/ci.yml`.
C. `.github/pipelines/ci.yml`.
D. `.github/runners/ci.yml`.
Đáp án đúng: B

Câu 2: Workflow cần chạy khi pull request được mở hoặc cập nhật commit. Sự kiện nào phù hợp?
A. Khai báo `on: release` trong workflow.
B. Khai báo `on: push` trong workflow.
C. Khai báo `on: workflow_dispatch` trong workflow.
D. Khai báo `on: pull_request` trong workflow.
Đáp án đúng: D

Câu 3: Job `test` chỉ được bắt đầu sau khi job `build` thành công. Cấu hình nào phù hợp?
A. Thêm `needs: build` vào job `test`.
B. Thêm `runs-on: build` vào job `test`.
C. Thêm `uses: build` vào job `test`.
D. Thêm `concurrency: build` vào job `test`.
Đáp án đúng: A

Câu 4: Một job cần chạy trên runner Ubuntu do GitHub quản lý. Trường nào chọn runner?
A. Đặt `runs-on: ubuntu-latest` cho job.
B. Đặt `shell: ubuntu-latest` cho job.
C. Đặt `env: ubuntu-latest` cho job.
D. Đặt `needs: ubuntu-latest` cho job.
Đáp án đúng: A

Câu 5: Muốn chạy một job test trên Java 17 và 21 thành hai lượt độc lập, dùng cấu hình nào?
A. Dùng `env.JAVA_VERSION` đặt một giá trị cố định.
B. Dùng `needs` trỏ tới hai job kiểm thử khác.
C. Dùng `strategy.matrix` khai báo hai phiên bản JDK.
D. Dùng `concurrency.group` theo tên từng phiên bản.
Đáp án đúng: C

Câu 6: Workflow Maven cần làm mới cache dependency khi POM thay đổi. Cache key nên dựa vào gì?
A. ID từng lượt chạy lấy từ `github.run_id`.
B. Hash nội dung của các file `pom.xml` liên quan.
C. Tên repository cố định mà không xét nội dung POM.
D. Timestamp của runner khi bắt đầu chạy job CI.
Đáp án đúng: B

Câu 7: Job build tạo JAR; job deploy chạy trên runner khác. Cách nào chuyển JAR giữa hai job?
A. Ghi nội dung JAR vào `$GITHUB_ENV` của job build.
B. Lưu JAR trong cache dependency với key cố định.
C. Truy cập trực tiếp workspace của runner build.
D. Dùng upload-artifact rồi download-artifact ở job sau.
Đáp án đúng: D

Câu 8: Job chỉ đọc mã để build. Quyền `GITHUB_TOKEN` nào tuân thủ nguyên tắc tối thiểu?
A. Đặt `contents: write` cho mọi job trong workflow.
B. Đặt `actions: write` cho toàn bộ repository.
C. Đặt `contents: read` trong `permissions` của job.
D. Đặt `id-token: write` cho mọi job build.
Đáp án đúng: C

Câu 9: Pull request từ fork cần chạy test nhưng không được dùng secret triển khai. Thiết kế nào an toàn?
A. Chạy test không secret; chỉ deploy ở sự kiện tin cậy.
B. Đưa khóa deploy vào biến `env` của workflow test.
C. Dùng `pull_request_target` để chạy mã PR với token ghi.
D. Dùng `workflow_dispatch` để tự cấp secret cho fork.
Đáp án đúng: A

Câu 10: Pipeline muốn gọi cloud mà không lưu access key dài hạn. Cấu hình nào phù hợp?
A. Lưu mật khẩu runner và cấp `contents: write`.
B. Cache token cloud giữa các lần chạy của job.
C. Dùng OIDC federation với quyền `id-token: write`.
D. Đưa credential vào artifact và cấp `actions: write`.
Đáp án đúng: C

Câu 11: Job triển khai production cần người phê duyệt trước khi chạy. GitHub Actions hỗ trợ cách nào?
A. Đặt `if: success()` trước các bước triển khai.
B. Dùng environment có required reviewers.
C. Đặt `needs: test` nối với job kiểm thử.
D. Dùng `concurrency` để giới hạn số lần deploy.
Đáp án đúng: B

Câu 12: Một PR được push liên tục; muốn hủy lượt CI cũ khi có lượt mới cùng PR. Cấu hình nào đúng?
A. Dùng `timeout-minutes` ngắn cho mỗi lượt CI cùng PR.
B. Dùng `strategy.fail-fast` trên các job của cùng PR.
C. Dùng `concurrency.group` và `cancel-in-progress: true`.
D. Dùng `needs` nối các lượt workflow theo thứ tự commit.
Đáp án đúng: C

Câu 13: Bước thu thập log cần chạy khi job thành công, thất bại hoặc bị hủy. Điều kiện nào đáp ứng?
A. Dùng điều kiện `if: success()` cho bước log.
B. Dùng điều kiện `if: failure()` cho bước log.
C. Dùng điều kiện `if: cancelled()` cho bước log.
D. Dùng điều kiện `if: always()` cho bước log.
Đáp án đúng: D

Câu 14: Workflow sử dụng action bên thứ ba. Cách tham chiếu nào hạn chế mã action thay đổi ngoài ý muốn?
A. Ghim action theo nhánh `main` của tác giả.
B. Ghim action theo SHA commit đầy đủ đã duyệt.
C. Ghim action theo tag `latest` do tác giả tạo.
D. Ghim action theo tên nhánh mặc định của repo.
Đáp án đúng: B

Câu 15: Với dự án Maven có unit test, lệnh nào đóng gói và chạy test theo lifecycle mặc định?
A. Chạy `mvn -B verify` trong job CI.
B. Chạy `mvn -B package -DskipTests` trong job CI.
C. Chạy `mvn -B test-compile` trong job CI.
D. Chạy `mvn -B dependency:resolve` trong job CI.
Đáp án đúng: A

Câu 16: Sau khi phát hành JAR, dữ liệu nào giúp đối chiếu artifact với source và lượt chạy CI?
A. Tên nhánh, số commit gần nhất và hostname runner.
B. Tên workflow, thời gian hoàn thành và loại runner.
C. Tên release, email actor và thời gian mở pull request.
D. Commit SHA, run ID và digest của artifact phát hành.
Đáp án đúng: D
