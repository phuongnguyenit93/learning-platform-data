Câu 1. Một nhóm triển khai nhiều lần mỗi ngày nhưng thường mất hai tuần để gộp các feature branch. Thực hành nào gần với trunk-based development nhất?
A. Chia thay đổi nhỏ, tích hợp thường xuyên vào trunk qua nhánh ngắn.
B. Giữ feature branch riêng đến khi hoàn tất toàn bộ epic rồi mới merge.
C. Thêm nhánh develop dài hạn làm điểm tích hợp duy nhất theo tháng.
D. Tạo nhánh release cho từng developer để tránh va chạm trong ngày.
Đáp án đúng: A

Câu 2. Một repository áp dụng GitHub Flow và muốn nhánh chính luôn có thể phát hành. Quy trình thay đổi tính năng nào phù hợp?
A. Tạo feature từ develop, chờ kỳ release để merge sang main.
B. Gộp thẳng vào main rồi gửi pull request để kiểm tra lại.
C. Tạo nhánh từ main, mở PR, chạy CI/review rồi merge vào main.
D. Tạo release branch trước mỗi PR rồi chỉ merge khi đủ kế hoạch sprint.
Đáp án đúng: C

Câu 3. Theo GitFlow, cặp vai trò nào mô tả đúng hai nhánh lâu dài `main` và `develop`?
A. `main` chứa thử nghiệm hằng ngày; `develop` giữ bản production ổn định.
B. `main` theo dõi release đã phát hành; `develop` tích hợp tính năng.
C. `main` lưu hotfix chưa kiểm thử; `develop` chỉ lưu Git tag.
D. `main` dùng cho PR tạm thời; `develop` dùng để lưu artifact.
Đáp án đúng: B

Câu 4. Production gặp lỗi nghiêm trọng khi `develop` đã chứa tính năng chưa phát hành. Với GitFlow, nên tạo và tích hợp hotfix thế nào?
A. Tách hotfix từ develop, merge về develop và chờ đợt release mới.
B. Chỉnh trực tiếp trên main, không đồng bộ bản sửa với develop.
C. Tách hotfix từ main, phát hành từ main và đưa sửa đổi vào develop.
D. Đưa sửa lỗi vào feature branch dài hạn và đóng PR release hiện tại.
Đáp án đúng: C

Câu 5. Nhóm dùng trunk-based nhưng tính năng thanh toán mới chưa đủ điều kiện bật cho khách hàng. Cách nào vẫn giữ trunk ổn định?
A. Đưa thay đổi nhỏ lên trunk sau CI, ẩn luồng mới sau feature flag.
B. Để nhánh tính năng tồn tại đến ngày toàn bộ thay đổi được bật.
C. Bỏ kiểm thử trên trunk cho đến khi luồng mới đủ chức năng.
D. Merge tính năng vào trunk rồi yêu cầu vận hành tắt mọi triển khai.
Đáp án đúng: A

Câu 6. Repository bảo vệ `main` để tránh thay đổi thiếu kiểm chứng. Bộ điều kiện nào giúp kiểm soát chất lượng trước merge?
A. Yêu cầu PR được review và required CI checks đạt trước merge.
B. Cho phép push thẳng vào main nếu tác giả tự kiểm thử local.
C. Chỉ yêu cầu Git tag được ký sau khi code đã lên main.
D. Chỉ yêu cầu pipeline chạy, không phụ thuộc kết quả kiểm thử.
Đáp án đúng: A

Câu 7. Hai PR riêng lẻ đều vượt CI nhưng kết hợp vào main lại gây lỗi tích hợp. Cơ chế nào giảm rủi ro này?
A. Bỏ kiểm thử CI nếu hai PR đã có approval từ reviewer.
B. Giữ hai PR trên nhánh dài hạn và merge cùng một lúc thủ công.
C. Dùng merge queue kiểm tra trạng thái tích hợp dự kiến trước merge.
D. Cho phép merge trước rồi chạy test ở đợt release tiếp theo.
Đáp án đúng: C

Câu 8. Hai nhóm sửa cùng lớp trong các nhánh kéo dài hơn một tháng và liên tục xung đột. Cách nào giảm chi phí hợp nhất?
A. Đóng băng trunk đến khi các feature branch đều hoàn thiện.
B. Giữ mỗi nhóm một nhánh chính để tránh cùng sửa một repository.
C. Tự động ưu tiên thay đổi ở nhánh merge trước và bỏ nhánh còn lại.
D. Chia PR nhỏ, cập nhật trunk sớm, giải xung đột rồi chạy CI.
Đáp án đúng: D

Câu 9. Một commit đã merge vào `main` dùng chung gây lỗi sản xuất, nhưng lịch sử đã được đồng nghiệp kéo về. Cách hoàn tác an toàn là gì?
A. Force-push main lùi về commit cũ để xóa lịch sử lỗi.
B. Amend commit gốc rồi yêu cầu mọi người reset nhánh local theo SHA mới.
C. Tạo commit revert thông qua quy trình review để giữ lịch sử.
D. Xóa nhánh main trên remote rồi tạo lại từ tag ổn định.
Đáp án đúng: C

Câu 10. Với GitFlow, đội muốn đóng băng phạm vi một bản phát hành trong khi `develop` tiếp tục nhận tính năng mới. Cách nào phù hợp?
A. Tạo release branch từ develop để ổn định bản phát hành trước merge.
B. Tạo hotfix branch từ main để gom mọi tính năng cho release mới.
C. Đổi tên develop thành main để tạm ngừng việc hợp nhất tính năng.
D. Giữ toàn bộ tính năng trên main và ổn định bằng Git tag tạm thời.
Đáp án đúng: A

Câu 11. Đội bật squash merge cho PR lên `main`. Tác động nào đúng với lịch sử commit trên nhánh đích?
A. Mỗi commit ở nhánh nguồn luôn được bảo toàn nguyên SHA trên nhánh main.
B. Git sẽ tạo một merge commit chứa đủ tất cả commit gốc trên main.
C. Git tự động rebase mọi commit rồi bắt buộc tạo release tag.
D. Nội dung PR thường thành một commit mới trên main thay vì chuỗi gốc.
Đáp án đúng: D

Câu 12. Sửa lỗi bảo mật cần áp dụng cho nhánh release đang hỗ trợ và trunk, nhưng hai nhánh khác nhau nhiều tính năng. Cách nào kiểm soát tốt?
A. Merge toàn bộ trunk vào release để kéo theo mọi tính năng chưa ra mắt.
B. Chỉ sửa trunk vì nhánh release đã tồn tại trước khi có lỗi.
C. Chỉnh trực tiếp nhánh release bằng force-push và không cần test.
D. Chọn lọc commit sửa lỗi cho từng nhánh, review và chạy CI riêng.
Đáp án đúng: D

Câu 13. PR có CI xanh trên commit cũ, nhưng `main` đã thêm commit mới có thể xung đột ngữ nghĩa. Chính sách nào hữu ích?
A. Giữ kết quả kiểm thử cũ vì PR chưa đổi nội dung.
B. Yêu cầu kiểm tra lại trên trạng thái base mới trước merge.
C. Cho merge khi hai nhánh có cùng số lượng commit.
D. Bỏ required checks nếu reviewer xác nhận không có xung đột.
Đáp án đúng: B

Câu 14. Developer muốn rebase để cập nhật nhánh tính năng. Trường hợp nào ít gây rủi ro cho người cùng làm việc?
A. Rebase nhánh main đã được mọi thành viên clone rồi force-push.
B. Rebase nhánh local chưa chia sẻ, kiểm thử trước khi tạo PR.
C. Rebase tag đã phát hành để cập nhật lịch sử cho đúng.
D. Rebase nhánh release đang dùng chung mà không thông báo.
Đáp án đúng: B

Câu 15. Pipeline phát hành từ tag `v2.3.1`, sau đó phát hiện bản build cần chỉnh sửa. Cách nào bảo toàn truy vết phiên bản?
A. Đẩy tag `v2.3.1` sang commit mới rồi build lại artifact từ source.
B. Giữ tag cũ nhưng thay nội dung artifact cùng version.
C. Tạo branch trùng tên tag và xóa Git history trước đó.
D. Giữ tag phát hành bất biến, sửa lỗi rồi tạo version/tag mới.
Đáp án đúng: D

Câu 16. Nhóm dùng GitHub Flow phát hiện lỗi production trong khi `main` vẫn là nhánh phát hành. Cách xử lý nào phù hợp nhất?
A. Đợi nhánh develop hoàn thành các tính năng mới rồi hotfix.
B. Tách nhánh sửa từ main, mở PR, chạy CI, merge và triển khai.
C. Tạo release branch lâu dài rồi gộp toàn bộ feature đang mở.
D. Chỉnh file trực tiếp trên production mà không cập nhật Git.
Đáp án đúng: B
