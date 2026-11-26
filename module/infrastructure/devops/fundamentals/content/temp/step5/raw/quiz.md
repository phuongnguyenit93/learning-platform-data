Câu 1. Hai nhóm Dev và Ops thường đổ lỗi cho nhau khi phát hành gặp sự cố. Cách tổ chức nào phù hợp nhất với DevOps?
A. Để nhóm Dev sở hữu mã, nhóm Ops sở hữu mọi lỗi phát hành.
B. Tách hoàn toàn trực vận hành khỏi nhóm phát triển sản phẩm cốt lõi.
C. Chia sẻ mục tiêu, dữ liệu vận hành và trách nhiệm chất lượng.
D. Chỉ yêu cầu nhóm Ops duyệt release sau khi Dev giao mã.
Đáp án đúng: C

Câu 2. Một merge request sửa logic thanh toán có nguy cơ gây regression. Kiểm soát nào nên được tự động hóa trước merge?
A. Chạy kiểm thử liên quan trong CI và chặn merge khi thất bại.
B. Chờ đợt kiểm thử cuối sprint rồi mới gộp mọi thay đổi.
C. Cho phép merge nếu developer xác nhận đã chạy thử trên máy cá nhân.
D. Đẩy mã lên staging trước rồi bỏ qua kết quả unit test.
Đáp án đúng: A

Câu 3. Nhóm thường giữ feature branch nhiều tuần, đến ngày phát hành mới gặp xung đột lớn. Thay đổi nào giúp tăng phản hồi sớm?
A. Chia thay đổi nhỏ, tích hợp thường xuyên qua nhánh tồn tại ngắn.
B. Gộp tất cả nhánh lớn vào cuối kỳ rồi mới giải quyết xung đột.
C. Đợi tính năng hoàn chỉnh mới cho chạy pipeline kiểm thử.
D. Tăng số nhánh dài hạn để mỗi nhóm ít sửa chung tệp.
Đáp án đúng: A

Câu 4. Ứng dụng đã được kiểm thử trên staging. Để production chạy đúng nội dung đã kiểm chứng, pipeline nên xử lý artifact thế nào?
A. Build lại từ cùng Git tag bằng runner riêng của production.
B. Build lại từ cùng commit với cấu hình build của production.
C. Gắn lại version release rồi biên dịch từ mã đã được duyệt.
D. Triển khai đúng artifact đã kiểm thử theo digest bất biến.
Đáp án đúng: D

Câu 5. Máy chủ production bị chỉnh cấu hình bằng tay, khiến môi trường lệch khỏi khai báo. Phương án nào giảm drift bền vững?
A. Ghi lại toàn bộ thao tác thủ công vào nhật ký sau mỗi đợt triển khai.
B. Đồng bộ cấu hình bằng script do quản trị viên chạy tùy ý.
C. Chụp image máy chủ hiện tại rồi bỏ các file cấu hình cũ.
D. Quản lý cấu hình bằng IaC, review và kiểm tra sai lệch định kỳ.
Đáp án đúng: D

Câu 6. Nhóm chọn blue-green deployment để giảm gián đoạn khi đổi phiên bản. Thao tác nào đúng với chiến lược này?
A. Kiểm tra môi trường green rồi chuyển lưu lượng khỏi blue.
B. Tăng dần tỷ lệ lưu lượng vào từng instance của bản mới.
C. Cập nhật trực tiếp toàn bộ instance trong cùng một môi trường.
D. Đẩy release lên staging rồi thay database production tại chỗ.
Đáp án đúng: A

Câu 7. Sau một release, độ trễ API tăng nhưng chỉ một số request gặp lỗi. Dữ liệu nào giúp truy nguyên từ triệu chứng đến request?
A. Chỉ lưu log build và số lượng commit trên nhánh chính.
B. Chỉ theo dõi CPU bình quân và số job CI chạy trong pipeline.
C. Chỉ xem trạng thái deployment mà bỏ qua luồng request.
D. Kết hợp metric, log và trace gắn request cùng phiên bản.
Đáp án đúng: D

Câu 8. Một dịch vụ đặt SLO khả dụng 99,9% trong tháng. Đội muốn dùng error budget để quyết định có nên phát hành tiếp. Error budget nghĩa là gì?
A. Số lỗi unit test tối đa được bỏ qua trong sprint hiện tại.
B. Phần mức độ không đạt SLO còn được chấp nhận trong kỳ.
C. Số lần pipeline deploy được phép thất bại trong một tháng.
D. Phần ngân sách cloud dành cho khôi phục khi có sự cố.
Đáp án đúng: B

Câu 9. Sau sự cố production, buổi postmortem có xu hướng tập trung tìm người gây lỗi. Cách thực hành nào phù hợp với DevOps?
A. Ghi tên cá nhân vào KPI để giảm số thay đổi rủi ro.
B. Phân tích yếu tố hệ thống và theo dõi hành động cải tiến.
C. Chỉ báo cáo thời gian phục hồi rồi đóng mọi action item đã tạo.
D. Chuyển toàn bộ nhiệm vụ khắc phục sang nhóm vận hành.
Đáp án đúng: B

Câu 10. Đội muốn đo lead time for changes cho phần mềm chạy production. Khoảng thời gian nào phản ánh chỉ số này theo cách đo DORA thường dùng?
A. Từ khi commit được tạo đến lúc thay đổi có trên production.
B. Từ khi issue được mở đến lúc developer bắt đầu lập trình tính năng.
C. Từ khi unit test bắt đầu đến lúc pipeline build hoàn tất.
D. Từ khi container được tạo đến lúc upload lên registry.
Đáp án đúng: A

Câu 11. CI phát hiện dependency có lỗ hổng nghiêm trọng vượt ngưỡng policy trước khi deploy. Cơ chế nào phù hợp?
A. Cho deploy chạy rồi bổ sung finding vào báo cáo định kỳ.
B. Chặn release theo policy và quản lý ngoại lệ được phê duyệt.
C. Tắt quy tắc quét khi unit test và integration test đều đạt yêu cầu.
D. Chỉ chuyển cảnh báo cho nhóm Ops sau khi ứng dụng chạy.
Đáp án đúng: B

Câu 12. Dịch vụ cần đổi schema database, nhưng phiên bản cũ và mới có thể chạy đồng thời khi rolling update. Chiến lược nào thích hợp?
A. Xóa cột cũ ngay trước khi triển khai phiên bản mới.
B. Đổi tên các cột đang dùng rồi mới tạo artifact mới.
C. Thay đổi schema theo expand–contract, tương thích chuyển tiếp.
D. Đợi traffic về không rồi thay schema trực tiếp, không cần kiểm thử.
Đáp án đúng: C

Câu 13. Job CI cần đọc credential để phát hành nhưng mã từ fork không tin cậy cũng được chạy. Cách phân quyền nào đúng?
A. Cấp secret cho mọi job nếu giá trị đã được che trong log.
B. Đặt cùng token vào biến môi trường của mọi nhánh.
C. Chỉ cấp secret ngắn hạn, đúng quyền cho job tin cậy.
D. Đưa secret vào cache để các job không phải truy cập vault.
Đáp án đúng: C

Câu 14. Một rollout canary làm tỷ lệ lỗi vượt ngưỡng sức khỏe đã xác định. Automation nên thực hiện hành động nào?
A. Tăng lưu lượng canary để thu thêm dữ liệu phân tích lỗi.
B. Tiếp tục triển khai nếu build và test trước đó đều xanh.
C. Chờ hết cửa sổ phát hành rồi cập nhật dashboard của sự cố.
D. Dừng tăng lưu lượng và rollback theo health gate đã đặt.
Đáp án đúng: D

Câu 15. Đội vận hành phát hiện một kiểu lỗi mới lặp lại sau deploy. Hành động nào tạo vòng phản hồi cải tiến liên tục?
A. Chỉ tăng mức cảnh báo mà không thay đổi quy trình kiểm thử.
B. Đưa lỗi vào changelog rồi đóng incident sau khi phục hồi.
C. Bổ sung kiểm thử hồi quy và điều chỉnh alert từ sự cố.
D. Hoãn các cuộc họp cải tiến cho đến kỳ phát hành kế tiếp.
Đáp án đúng: C

Câu 16. Trong 30 lần triển khai production, có 3 lần gây lỗi dịch vụ cần khắc phục. Change failure rate theo quy ước này là bao nhiêu?
A. 3% trên tổng số lần triển khai production được ghi nhận trong kỳ.
B. 10% trên tổng số lần triển khai production được ghi nhận.
C. 30% trên tổng số lần triển khai production được ghi nhận.
D. 90% trên tổng số lần triển khai production được ghi nhận.
Đáp án đúng: B
