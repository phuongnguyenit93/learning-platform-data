Câu 1. Dự án khai báo các stage `build`, `test`, `deploy`. Cách nào gán job `unit_test` chạy `npm test` vào stage `test` một cách tường minh?
A. Khai báo `stage: build` cùng `script: npm test`.
B. Khai báo `stage: deploy` cùng `script: npm test`.
C. Khai báo `stage: test` cùng `script: npm test`.
D. Khai báo `stage: .post` cùng `script: npm test`.
Đáp án đúng: C

Câu 2. Một push vào nhánh đã mở merge request tạo cả branch pipeline và MR pipeline. Cấu hình nào quyết định việc tạo toàn bộ pipeline?
A. Đặt `rules` tại riêng job kiểm thử chính của nhánh.
B. Dùng `workflow: rules` lọc nguồn và điều kiện pipeline.
C. Đặt `when: manual` cho job triển khai staging.
D. Dùng `resource_group` chung cho hai job triển khai.
Đáp án đúng: B

Câu 3. Trong merge request pipeline, job kiểm tra migration chỉ nên xuất hiện khi tệp trong `db/migrations/**` thay đổi. Điều kiện nào phù hợp?
A. Dùng `rules:exists` để kiểm tra thư mục migration.
B. Dùng `rules:changes` theo đường dẫn migration.
C. Dùng `cache:paths` để đánh dấu thư mục migration.
D. Dùng `artifacts:paths` để chỉ định thư mục migration.
Đáp án đúng: B

Câu 4. Frontend build mất hai phút, backend build mất tám phút. Muốn job kiểm thử frontend chạy ngay sau frontend build mà không chờ cả stage build, nên dùng gì?
A. Đặt `needs` từ job kiểm thử tới job frontend build.
B. Đặt `dependencies` để kiểm thử lấy bản build frontend.
C. Chuyển job kiểm thử frontend sang stage `deploy` sau.
D. Tăng `artifacts:expire_in` của job frontend build.
Đáp án đúng: A

Câu 5. Job có `tags: [docker, linux]`. Runner nào đáp ứng yêu cầu gắn tag của GitLab CI?
A. Runner có tag `linux` nhưng không có tag `docker`.
B. Runner có đủ cả tag `docker` và `linux` đã đăng ký.
C. Runner có tag `docker` nhưng không có tag `linux`.
D. Runner được phép nhận untagged job nhưng thiếu hai tag.
Đáp án đúng: B

Câu 6. Job khai báo `image: node:22` nhưng chỉ được gán cho Shell executor. Nhận định nào giải thích đúng hành vi `image`?
A. Shell executor tự khởi tạo container như Docker executor.
B. GitLab server sẽ chạy container thay cho Shell runner.
C. `image` được hỗ trợ bởi executor như Docker/Kubernetes.
D. Chỉ cần runner gắn tag `docker` để Shell chạy image.
Đáp án đúng: C

Câu 7. Job build tạo `dist/app.zip`; job deploy cùng pipeline cần tải đúng gói đó. Cơ chế nào phù hợp nhất?
A. Dùng `cache:paths` chứa gói để deploy tìm lại bằng cache key.
B. Dùng `rules:exists` trong deploy để nhìn thấy gói.
C. Dùng `artifacts:paths` ở build để job sau nhận gói.
D. Dùng `environment:url` trỏ vào đường dẫn của gói.
Đáp án đúng: C

Câu 8. Pipeline Node.js chạy `npm ci`; cache dependency cần đổi khóa khi `package-lock.json` thay đổi. Nên cấu hình thế nào?
A. Dùng `cache:key:files` dựa trên `package-lock.json`.
B. Dùng `artifacts:expire_in` đặt thời gian sống cache.
C. Dùng `cache:key` cố định cho mọi lần chạy pipeline.
D. Dùng `resource_group` kết hợp tên nhánh và lockfile.
Đáp án đúng: A

Câu 9. Muốn job kiểm tra merge request chỉ xuất hiện trong pipeline có source `merge_request_event`, biểu thức `rules:if` cần xem biến nào?
A. So `$CI_PIPELINE_SOURCE` với `merge_request_event`.
B. So `$CI_COMMIT_BRANCH` với giá trị `merge_request_event`.
C. So `$CI_JOB_STAGE` với `merge_request_event`.
D. So `$CI_DEFAULT_BRANCH` với `merge_request_event`.
Đáp án đúng: A

Câu 10. Job production cần token riêng; token chỉ được cấp cho pipeline trên nhánh phát hành được quản trị. Cách cấu hình nào phù hợp?
A. Ghi token trong YAML `variables` dùng chung mọi nhánh.
B. Đưa token vào `cache` để các job deploy dùng lại.
C. Lưu token dưới CI/CD variable `protected` cho protected ref.
D. Xuất token vào `artifacts:paths` có thời hạn rất ngắn.
Đáp án đúng: C

Câu 11. Nhóm muốn production chạy đúng container image từng được kiểm thử, dù tag image có thể trỏ sang nội dung mới. Nên truyền gì sang deploy?
A. Dùng tag `latest` đã đẩy từ build lên container registry.
B. Dùng tên nhánh Git nơi image đã được build thành công.
C. Dùng tên runner đã thực hiện job build của pipeline.
D. Dùng image digest đã kiểm thử sau khi image được push.
Đáp án đúng: D

Câu 12. Muốn GitLab Environments hiển thị deployment `staging` kèm URL ứng dụng, nên khai báo gì trong job deploy?
A. Khai báo `environment:name` và `environment:url`.
B. Khai báo `artifacts:name` và `artifacts:paths` trong deploy.
C. Khai báo `cache:key` và `cache:paths` trong job.
D. Khai báo `rules:changes` và `rules:exists`.
Đáp án đúng: A

Câu 13. Deployment production cần người được cấp quyền bấm chạy thủ công, còn job CI khác chạy tự động. Thiết kế nào thích hợp?
A. Dùng `when: always` và runner có tag `production`.
B. Dùng `allow_failure: true` cùng job deploy tự động.
C. Dùng `interruptible: true` cho mọi job production.
D. Dùng `when: manual` cùng protected environment.
Đáp án đúng: D

Câu 14. Hai pipeline của nhánh chính cùng tới bước deploy production; đội cần đảm bảo chúng không chạy song song. Cấu hình nào giải quyết trực tiếp?
A. Dùng `needs` để deploy chờ artifact của build.
B. Dùng `parallel` để giới hạn lượng job deploy.
C. Dùng `cache:key` chung cho hai pipeline deploy.
D. Dùng `resource_group` chung cho job deploy production.
Đáp án đúng: D

Câu 15. Nhiều project cần tái sử dụng job quét bảo mật từ một repo template và khóa vào revision được duyệt. Nên dùng cấu hình nào?
A. Sao chép YAML quét bảo mật vào từng repo của nhóm.
B. Dùng `include:project` trỏ template và cố định `ref`.
C. Dùng `cache:paths` để tải cấu hình từ project khác.
D. Dùng `artifacts:paths` truyền file YAML giữa các project khác.
Đáp án đúng: B

Câu 16. Pipeline cần lấy quyền truy cập cloud ngắn hạn nhưng chính sách cấm lưu access key dài hạn trong GitLab. Cách nào phù hợp?
A. Dùng masked variable chứa cloud access key dài hạn.
B. Dùng protected variable chứa cloud access key dài hạn.
C. Dùng dotenv artifact để phát cloud access key dài hạn.
D. Dùng OIDC ID token đổi lấy thông tin xác thực ngắn hạn.
Đáp án đúng: D
