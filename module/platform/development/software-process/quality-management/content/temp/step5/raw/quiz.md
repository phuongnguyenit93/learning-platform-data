1. Điểm khác biệt trọng tâm giữa Quality Assurance (QA) và Quality Control (QC) là gì?
A. QA đo năng suất cá nhân; QC quyết định lịch phát hành nhóm
B. QA viết mọi test case; QC chỉ phê duyệt tài liệu quy trình
C. QA hướng vào quá trình; QC kiểm chất lượng sản phẩm
D. QA phụ trách thiết kế UI; QC phụ trách kiến trúc triển khai
Đáp án đúng: C

2. Mục tiêu chất lượng nào có tiêu chí định lượng và thời hạn rõ ràng nhất?
A. Số lỗi production phải giảm khi nhóm có thêm thời gian
B. Không quá hai lỗi nghiêm trọng lọt production mỗi quý
C. Chất lượng mỗi bản release nên tốt hơn bản trước
D. Đội ngũ cần tăng cường rà soát mã khi có nguồn lực
Đáp án đúng: B

3. Một quality management plan nên mô tả đầy đủ yếu tố nào?
A. Chỉ lịch họp nhóm, tên thành viên và danh sách công cụ
B. Chỉ biểu đồ tốc độ phát triển và năng suất lập trình
C. Mục tiêu, trách nhiệm, phép đo và rủi ro cần theo dõi
D. Chỉ danh mục framework được dùng trong dự án phần mềm
Đáp án đúng: C

4. Trong quản lý chất lượng, verification và validation khác nhau ở đâu?
A. Một bên chỉ chạy trên server; bên kia chỉ chạy trên client
B. Một bên đánh giá tốc độ; bên kia chỉ đánh giá bảo mật
C. Một bên dùng unit test; bên kia bắt buộc dùng review thủ công
D. Một bên so với đặc tả; bên kia xem đáp ứng nhu cầu thực
Đáp án đúng: D

5. Khi chọn ca kiểm thử theo rủi ro, nên ưu tiên yếu tố nào?
A. Độ dài mô tả test case và số lượng bước thực hiện
B. Khả năng xảy ra lỗi kết hợp mức độ tác động của nó
C. Thứ tự các chức năng được liệt kê trong đặc tả cũ
D. Tỷ lệ test tự động đang có của từng module duy nhất
Đáp án đúng: B

6. Tại sao peer review sớm thường giúp giảm chi phí sửa lỗi?
A. Mọi lỗi được review sẽ chắc chắn không xuất hiện trong runtime
B. Review sớm làm cho mọi ca kiểm thử hệ thống không cần chạy
C. Review mã là phương pháp thay thế hoàn toàn review yêu cầu
D. Phát hiện sai lệch trước khi lỗi lan sang các giai đoạn sau
Đáp án đúng: D

7. Khi review logic chuyển tiền, checklist nào hữu ích nhất?
A. Kiểm tra quyền, số dư và tác động của thao tác lặp
B. Kiểm tra chủ yếu khoảng trắng, định dạng và tên biến
C. Kiểm tra riêng thời gian mở IDE và tốc độ máy lập trình
D. Kiểm tra tên file biên dịch có thống nhất quy tắc chưa
Đáp án đúng: A

8. Static analysis đóng góp vào chất lượng theo cách nào?
A. Chứng minh mọi hành vi nghiệp vụ đúng với nhu cầu khách
B. Đo lỗi thực tế ở production dưới tải đồng thời cao
C. Tìm dấu hiệu lỗi trong mã mà chưa cần chạy chương trình
D. Thay thế việc reviewer xác minh luồng xử lý phức tạp
Đáp án đúng: C

9. Một quality gate của CI nên hành động thế nào khi vượt ngưỡng lỗi nghiêm trọng?
A. Chặn bước phát hành và lưu bằng chứng để nhóm xử lý
B. Tự thay đổi mức độ nghiêm trọng để build được đánh PASS
C. Bỏ qua cảnh báo nếu phần trăm coverage đang cao
D. Chỉ chuyển màu dashboard nhưng vẫn tự deploy production
Đáp án đúng: A

10. Vì sao cần đặt ngưỡng quality gate theo rủi ro của sản phẩm?
A. Mọi dự án đều cần cùng một tỷ lệ test coverage duy nhất
B. Số lượng assertion đủ để suy ra mức độ tổn thất kinh doanh
C. Lỗi của chức năng thanh toán luôn tương đương lỗi UI nhỏ
D. Mức lỗi chấp nhận được phụ thuộc tác động của chức năng
Đáp án đúng: D

11. Tại sao đạt 100% statement coverage chưa đủ chứng minh phần mềm đúng?
A. Coverage tự động kiểm tra đầy đủ mọi input của từng hàm
B. Coverage luôn bảo đảm xử lý chuẩn mọi trường hợp đồng thời
C. Dòng được chạy qua chưa đồng nghĩa đã kiểm chứng đúng
D. Coverage đã thay thế tất cả yêu cầu nghiệm thu sản phẩm
Đáp án đúng: C

12. Khi test tự động thất bại lúc có lúc không với cùng input, nhóm nên làm gì?
A. Thay dấu lỗi bằng PASS để giữ tốc độ pipeline ổn định
B. Xóa mọi test thất bại ngẫu nhiên khỏi repository ngay
C. Điều tra test flaky, theo dõi trước khi bỏ cách ly
D. Chạy lại đến khi xanh rồi coi như không tồn tại rủi ro
Đáp án đúng: C

13. Severity và priority của defect khác nhau thế nào?
A. Severity đo số lần xuất hiện; priority là thời gian build
B. Severity phản ánh mức ảnh hưởng; priority là thứ tự xử lý
C. Severity xác định người sửa; priority là loại test cần chạy
D. Severity là số ticket tồn; priority là số người tham gia
Đáp án đúng: B

14. Một 'escaped defect' trong đánh giá chất lượng thường là gì?
A. Lỗi đã được tìm thấy và sửa ngay trong code review
B. Lỗi lọt qua bước kiểm soát rồi mới được phát hiện
C. Lỗi được unit test phát hiện trước khi lập pull request
D. Lỗi giả do môi trường test thiếu dữ liệu cấu hình
Đáp án đúng: B

15. Muốn tính tỷ lệ defect escape cho một release, mẫu số hợp lý là gì?
A. Tổng lỗi được phát hiện ở cả hai phía mốc kiểm soát
B. Tổng số dòng code được thêm trong kỳ phát hành đó
C. Tổng số nhân viên tham gia kiểm thử tự động tháng đó
D. Tổng số phiên đăng nhập thành công của sản phẩm
Đáp án đúng: A

16. Khi đánh giá hiệu quả quy trình xử lý sự cố, chỉ số MTTR thường biểu thị gì?
A. Số lần kiểm thử hồi quy được chạy mỗi ngày ở pipeline
B. Tỷ lệ commit gây lỗi trên tổng số pull request đã merge
C. Tổng số phút ứng dụng không có người dùng đăng nhập
D. Thời gian trung bình từ lỗi tới khi khôi phục
Đáp án đúng: D

17. Change failure rate phản ánh tín hiệu chất lượng nào?
A. Tỷ lệ dòng mã bị test coverage bỏ qua khi phát hành
B. Tỷ lệ thay đổi triển khai phát sinh lỗi cần xử lý
C. Số lần một pipeline build thất bại do thiếu dependency
D. Tỷ lệ ticket bị đóng muộn hơn hạn xử lý mong đợi
Đáp án đúng: B

18. Khi phân tích một lỗi lặp lại, kết luận nào phù hợp tư duy nguyên nhân gốc?
A. Chỉ xác định cá nhân tạo commit có lỗi rồi kết thúc
B. Chỉ thêm một bước phê duyệt mà không xem dữ liệu lỗi
C. Chỉ theo dõi số lỗi mỗi tuần mà không xét nguyên nhân
D. Tìm nguyên nhân hệ thống khiến lỗi thường tái diễn
Đáp án đúng: D

19. Five Whys trong cải tiến chất lượng nên được dùng như thế nào?
A. Đào sâu chuỗi nguyên nhân dựa trên bằng chứng thực tế
B. Luôn hỏi đúng năm câu dù đã đủ căn cứ ở câu thứ ba
C. Chọn ngay nguyên nhân cuối do người có chức danh cao đề xuất
D. Thay thế hoàn toàn thử nghiệm xác nhận nguyên nhân lỗi
Đáp án đúng: A

20. Sau khi tìm ra lỗi do thiếu kiểm tra hợp đồng API, hành động phòng ngừa nào phù hợp?
A. Chỉ sửa response sai của lần này rồi đóng báo cáo
B. Tăng số người tham gia họp mà không thêm kiểm chứng
C. Đưa contract test vào CI để chặn lỗi hợp đồng lặp
D. Chỉ gửi thông báo nhắc mọi nhóm cẩn thận hơn
Đáp án đúng: C

21. Bằng chứng kiểm chứng một quality gate cần có đặc điểm nào?
A. Truy vết được bản build, tiêu chí và kết quả phép kiểm
B. Chỉ có ảnh chụp màn hình bảng điều khiển không ghi phiên bản
C. Chỉ có xác nhận miệng của người phụ trách phát hành
D. Chỉ lưu số lượng bài test mà không lưu kết quả chạy
Đáp án đúng: A

22. Nếu phải chấp nhận ngoại lệ quality gate trước khi release, quy trình nào phù hợp?
A. Đặt mọi cảnh báo thành mức thấp để không cần phê duyệt
B. Xóa rule kiểm tra khỏi pipeline cho các lần phát hành sau
C. Đổi status ticket thành xong khi chưa có bằng chứng
D. Ghi rủi ro, người phê duyệt, phạm vi và hạn xử lý
Đáp án đúng: D

23. Khi tỷ lệ lỗi giảm trong một tuần, điều gì cần làm trước khi kết luận cải tiến bền vững?
A. Dừng toàn bộ giám sát vì chỉ số hiện tại đã được cải thiện
B. Xem xu hướng nhiều kỳ, độ biến động và lượng công việc
C. Tăng ngưỡng chấp nhận lỗi để có thêm cải thiện thống kê
D. Chỉ lấy số lỗi của tuần thấp nhất làm chuẩn dài hạn
Đáp án đúng: B

24. Khi chu trình QA/QC đã có chỉ số tốt, tại sao vẫn cần cải tiến liên tục?
A. Rủi ro và điều kiện sử dụng thay đổi theo thời gian
B. Chỉ số tốt nghĩa là mọi cách kiểm soát đều có thể ngừng ngay
C. Một lần review thành công đủ bảo đảm sản phẩm luôn không lỗi
D. Thêm quality gate mới luôn làm tăng chất lượng bất kể chi phí
Đáp án đúng: A
