Câu 1: Trong repository dịch vụ Java, nơi nào nên khai báo entity Component để Software Catalog nhận diện?
A. Ghi entity trong `mkdocs.yml` của tài liệu dịch vụ.
B. Ghi `kind`, `metadata`, `spec` vào `catalog-info.yaml`.
C. Ghi entity trong workflow CI dưới mục `jobs`.
D. Ghi entity vào biến môi trường của portal Backstage.
Đáp án đúng: B

Câu 2: Catalog hiển thị Component nhưng không biết đội nào chịu trách nhiệm. Trường nào gán nhóm sở hữu?
A. Đặt `metadata.owner` trỏ tới entity Group tương ứng.
B. Đặt `spec.lifecycle` trỏ tới entity Group tương ứng.
C. Đặt `metadata.tags` là tên Group phụ trách dịch vụ.
D. Đặt `spec.owner` trỏ tới entity Group tương ứng.
Đáp án đúng: D

Câu 3: Một Component tên `payment-api` nằm trong namespace mặc định. Entity reference đầy đủ nên viết thế nào?
A. `component:default/payment-api` trong đường dẫn tham chiếu.
B. `component/payment-api:default` trong đường dẫn tham chiếu.
C. `payment-api:component/default` trong đường dẫn tham chiếu.
D. `service:default/payment-api` trong đường dẫn tham chiếu.
Đáp án đúng: A

Câu 4: Nhóm đã có `catalog-info.yaml` trong Git, muốn Catalog tiếp nhận và theo dõi mô tả đó. Cách nào đúng?
A. Chỉ đính kèm đường dẫn Git vào trang TechDocs của dịch vụ.
B. Đăng ký Location trỏ tới tệp mô tả entity trong Git.
C. Sao chép nội dung YAML thủ công vào database frontend.
D. Chỉ tạo menu plugin trỏ đến đường dẫn repository.
Đáp án đúng: B

Câu 5: Dịch vụ thanh toán phụ thuộc cơ sở dữ liệu được khai báo là Resource trong Catalog. Quan hệ nào mô tả phụ thuộc?
A. Dùng `spec.providesApis` trỏ tới Resource cơ sở dữ liệu.
B. Dùng `spec.consumesApis` trỏ tới Resource cơ sở dữ liệu.
C. Dùng `spec.dependsOn` tham chiếu Resource cơ sở dữ liệu.
D. Dùng `spec.memberOf` trỏ tới Resource cơ sở dữ liệu.
Đáp án đúng: C

Câu 6: Muốn tạo luồng self-service sinh repository từ mẫu trong Backstage. Cấu trúc entity nào phù hợp?
A. Dùng `kind: Template`, gồm `parameters` và `steps`.
B. Dùng `kind: Component`, gồm `parameters` và `steps`.
C. Dùng `kind: Location`, gồm `parameters` và `steps`.
D. Dùng `kind: Group`, gồm `parameters` và `steps`.
Đáp án đúng: A

Câu 7: Template yêu cầu người dùng chọn Java hoặc Node.js và nhập tên repo bắt buộc. Khai báo nào phù hợp?
A. Đưa enum và required vào `metadata.annotations` của Template.
B. Đưa enum và required vào `spec.output` của Template.
C. Đưa enum và required vào `spec.owner` của Template.
D. Định nghĩa enum và required trong schema `spec.parameters`.
Đáp án đúng: D

Câu 8: Software Template tạo repository trên Git bằng credential được cấp cho portal. Thiết kế nào an toàn nhất?
A. Ghi token tạo repo vào tham số nhập của mọi Template.
B. Đặt token tạo repo trong nội dung file mẫu được sinh.
C. Giới hạn quyền token và xử lý secret ở backend an toàn.
D. Trả token tạo repo trong output để người dùng tái sử dụng.
Đáp án đúng: C

Câu 9: Dịch vụ đã có mã nguồn nhưng chưa có TechDocs. Bộ tệp nào thường cần để biên soạn tài liệu?
A. Có `mkdocs.yml`, nội dung `docs/` và cấu hình TechDocs.
B. Chỉ có `Dockerfile` và biến môi trường chạy portal.
C. Chỉ có `package.json` và workflow kiểm thử frontend.
D. Chỉ có `catalog-info.yaml` mà không có nguồn tài liệu.
Đáp án đúng: A

Câu 10: Trong metadata annotations, giá trị nào trỏ TechDocs đến tài liệu nằm trong cùng repository?
A. `backstage.io/techdocs-ref: dir:.` cho entity tương ứng.
B. `backstage.io/source-location: dir:.` cho entity tương ứng.
C. `backstage.io/managed-by-location: dir:.` cho entity.
D. `backstage.io/view-url: dir:.` cho entity tương ứng.
Đáp án đúng: A

Câu 11: Portal cần truy vấn công cụ DevOps bằng token tổ chức nhưng không muốn lộ token trên browser. Cách tích hợp nào đúng?
A. Gọi API trực tiếp từ browser kèm token trong JavaScript.
B. Nhúng token vào URL của iframe hiển thị trong portal.
C. Đặt tích hợp ở backend, lưu secret ngoài mã frontend.
D. Đưa token vào metadata entity trong Software Catalog.
Đáp án đúng: C

Câu 12: Nhóm muốn thêm tab UI để hiển thị chất lượng build trên trang Component. Thành phần mở rộng nào phù hợp?
A. Viết Entity Provider để thay thế toàn bộ UI của Catalog.
B. Chỉ tạo backend scheduler rồi mong tab tự xuất hiện.
C. Chỉ bổ sung YAML của Group vào Software Catalog.
D. Tạo frontend plugin/extension gắn vào trang Component.
Đáp án đúng: D

Câu 13: Người dùng đã đăng nhập qua SSO nhưng không được phép thực thi Template tạo repository production. Điều gì cần kiểm soát?
A. Chỉ cần có session SSO, bỏ kiểm tra hành động tạo repo.
B. Áp quyền theo hành động và danh tính tại backend.
C. Ẩn nút tạo repo ở frontend là đủ để chặn mọi API.
D. Gán quyền tạo repo cho toàn bộ User trong Catalog.
Đáp án đúng: B

Câu 14: Nhân viên đăng nhập bằng SSO cần được ánh xạ tới User trong Catalog. Thành phần nào xử lý nhận diện này?
A. Cấu hình Scaffolder Action viết lại `spec.owner` khi chạy.
B. Cấu hình TechDocs Plugin thay đổi User entity theo email.
C. Cấu hình Catalog Processor tự tạo session đăng nhập mới.
D. Cấu hình sign-in resolver ánh xạ danh tính sang user ref.
Đáp án đúng: D

Câu 15: Team phụ trách dịch vụ đổi từ `team-a` sang `team-b`, nhưng trang Catalog vẫn hiển thị owner cũ. Nên kiểm tra gì?
A. Chỉ đổi tên tab trên trang Component trong portal.
B. Chỉ thay đổi tên pipeline CI của repository dịch vụ.
C. Cập nhật `spec.owner`, đồng bộ entity và kiểm Group ref.
D. Thay URL TechDocs để trang Catalog tải dữ liệu mới.
Đáp án đúng: C

Câu 16: Chuẩn bị triển khai Backstage dùng chung cho nhiều đội trong production. Bộ biện pháp nào phù hợp?
A. Cho truy cập HTTP công khai và ghi token vào `app-config`.
B. Áp TLS, bảo vệ secret, phân quyền và giám sát backend.
C. Cho mọi plugin dùng chung admin token của SCM.
D. Tắt xác thực portal khi đã giới hạn menu frontend.
Đáp án đúng: B
