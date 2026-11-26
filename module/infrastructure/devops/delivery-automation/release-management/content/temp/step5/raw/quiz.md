Câu 1: Đợt phát hành gồm API, worker và migration DB có phụ thuộc. Trước khi chốt rollout, cần làm gì?
A. Chốt thứ tự theo thời điểm merge các pull request.
B. Triển khai mọi dịch vụ đồng thời theo từng runner CI.
C. Lập thứ tự theo phụ thuộc và phân công owner rollout.
D. Chốt thứ tự theo lúc từng artifact được đóng gói.
Đáp án đúng: C

Câu 2: Trong dự án theo Semantic Versioning, việc xóa endpoint API công khai khiến client cũ lỗi cần tăng phiên bản nào?
A. Tăng PATCH vì thay đổi chỉ ở định nghĩa của API.
B. Tăng MINOR vì client có thể cập nhật khi cần.
C. Giữ phiên bản vì không đổi cấu trúc artifact.
D. Tăng MAJOR vì client cũ có thể mất tương thích.
Đáp án đúng: D

Câu 3: RC-2 đã vượt qua kiểm thử staging. Cách đưa lên production nào giữ đúng gói đã kiểm thử?
A. Rebuild cùng commit trên runner triển khai production.
B. Build lại từ nhánh release bằng toolchain mới nhất.
C. Dùng tag `latest` vừa xuất hiện trong artifact store.
D. Promote artifact theo digest đã được kiểm chứng.
Đáp án đúng: D

Câu 4: Quality gate bắt buộc về hiệu năng của RC không đạt ngưỡng. Cách ra quyết định phù hợp?
A. Giữ trạng thái no-go, sửa lỗi và kiểm thử lại RC.
B. Cho go-live nếu unit test còn đạt ngưỡng yêu cầu.
C. Đổi ngưỡng sau khi xem kết quả để tiếp tục phát hành.
D. Chỉ tắt alert hiệu năng trong giai đoạn rollout.
Đáp án đúng: A

Câu 5: Nâng cấp thư viện dùng chung có thay đổi API làm client cũ lỗi. Release notes cần nêu gì?
A. Danh sách commit nội bộ cùng kết quả từng job kiểm thử.
B. Thay đổi phá tương thích, cách migrate và phạm vi ảnh hưởng.
C. Thời gian build của từng job và lịch nâng cấp runner.
D. Dung lượng artifact và lịch xoá cache ở các môi trường.
Đáp án đúng: B

Câu 6: Đợt release có thay đổi thanh toán phải được duyệt trước go-live. Phê duyệt nào truy vết được?
A. Tin nhắn đồng ý chung trong kênh nhóm của sprint.
B. Mẫu phê duyệt gắn với nhánh feature đang phát triển.
C. Bản duyệt gắn đúng RC, người duyệt và kết quả gate.
D. Biên bản tổng kết từ lần phát hành gần nhất.
Đáp án đúng: C

Câu 7: Ứng dụng đã triển khai toàn cụm; muốn bật tính năng cho 5% tài khoản mà không deploy thêm. Cần dùng gì?
A. Chỉ tăng số replica của phiên bản ứng dụng đang chạy.
B. Dùng feature flag có quy tắc nhắm nhóm tài khoản.
C. Tạo thêm release branch và yêu cầu client cập nhật.
D. Đổi tag image trong registry nhưng giữ workload cũ.
Đáp án đúng: B

Câu 8: Canary nhận 10% traffic và các pod Ready. Khi nào nên mở rộng lên 50%?
A. Khi chỉ số canary đạt ngưỡng so với baseline.
B. Khi job triển khai đã hoàn thành trước hạn.
C. Khi pod canary đều Ready và không restart.
D. Khi tag image trùng với tag đã dùng ở staging.
Đáp án đúng: A

Câu 9: Release thay đổi schema DB; để rollback ứng dụng trong thời gian chuyển đổi, nên làm gì?
A. Áp dụng expand–contract, giữ schema tương thích tạm thời.
B. Xóa cột cũ trước rồi cập nhật app trong cùng pipeline.
C. Chỉ giữ backup DB và triển khai schema phá tương thích.
D. Buộc mọi service dừng trước khi chạy migration phá tương thích.
Đáp án đúng: A

Câu 10: Trong sự cố, cần biết chính xác mã và artifact đang chạy. Release record nên chứa gì?
A. Tên nhánh, nhãn `latest` và thời gian bắt đầu deploy.
B. Tên người merge, version app và URL của trang pipeline.
C. Tên môi trường, mã ticket và thời điểm mở release.
D. Commit SHA, build ID, artifact digest và mốc triển khai.
Đáp án đúng: D

Câu 11: Producer muốn đổi cấu trúc event khiến consumer cũ không đọc được. Kế hoạch nào giảm gián đoạn?
A. Triển khai producer trước rồi yêu cầu consumer bắt kịp.
B. Đổi schema trong registry và chỉ cập nhật tag consumer.
C. Nâng consumer đọc cả hai dạng trước khi đổi producer.
D. Chặn event trong queue đến khi mọi service deploy xong.
Đáp án đúng: C

Câu 12: Sau deploy không có lỗi job nhưng khách hàng báo checkout chậm. Kiểm tra nào phát hiện vấn đề?
A. Kiểm tra artifact có giữ nguyên tên file cũ hay không.
B. Chỉ đối chiếu trạng thái job deploy đã hoàn thành.
C. Theo dõi latency giao dịch, lỗi và synthetic check.
D. Đếm số commit kể từ mốc cắt nhánh release.
Đáp án đúng: C

Câu 13: Phát hiện lỗ hổng nghiêm trọng sau code freeze. Cách xử lý hotfix trước ngày release?
A. Merge nhanh thay đổi rồi bỏ qua vòng kiểm thử RC.
B. Ghi nhận ngoại lệ, đánh giá rủi ro và test lại RC.
C. Chuyển thay đổi sang nhánh main sau lúc go-live.
D. Hạ mức nghiêm trọng để giữ nguyên release window.
Đáp án đúng: B

Câu 14: Đang rollout, tỷ lệ lỗi vượt ngưỡng rollback đã thống nhất. Quyết định nào phù hợp?
A. Dừng rollout, quay về artifact tốt và báo incident.
B. Chờ đủ 100% traffic rồi mới so sánh chỉ số tổng.
C. Tăng số replica để bỏ qua kết quả cảnh báo.
D. Bỏ metric lỗi và giữ kế hoạch vì deploy đã xong.
Đáp án đúng: A

Câu 15: Phải hoãn bản phát hành do lỗi tích hợp chưa sửa xong. Thông báo nào hữu ích nhất?
A. Công bố lại danh sách commit và số dòng bị thay đổi.
B. Gửi log test đầy đủ kèm danh sách tất cả job CI.
C. Chỉ nói release bị hoãn và chờ thông tin tiếp theo.
D. Nêu tác động, blocker, owner và mốc cập nhật kế tiếp.
Đáp án đúng: D

Câu 16: RC-2 đã qua UAT, nhưng cấu hình đóng gói phải chỉnh. Cách duy trì tính truy vết?
A. Ghi đè artifact RC-2 rồi giữ nguyên biên bản UAT.
B. Tạo RC-3 có định danh riêng và kiểm tra lại.
C. Sửa manifest ở production sau khi go-live.
D. Đổi release note của RC-2 mà không sửa artifact.
Đáp án đúng: B
