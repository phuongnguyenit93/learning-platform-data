Câu 1. Nhóm đo deployment frequency của một dịch vụ theo tuần. Sự kiện nào nên được đếm nếu phạm vi đo là production?
A. Số lần phiên bản mới được triển khai thành công vào production.
B. Số lần pipeline build hoàn thành thành công trong tuần trên CI.
C. Số commit được đưa vào nhánh chính của dự án trong tuần.
D. Số image được đẩy lên container registry trong tuần.
Đáp án đúng: A

Câu 2. Đội muốn đo lead time for changes từ Git và nhật ký phát hành. Cặp mốc nào phản ánh thời gian đưa một thay đổi tới người dùng?
A. Từ khi ticket được tạo đến khi được đưa vào sprint kế tiếp.
B. Từ khi merge request mở đến khi review được duyệt.
C. Từ lúc commit được tạo đến khi thay đổi chạy trên production.
D. Từ lúc build hoàn thành đến khi kiểm thử staging đạt.
Đáp án đúng: C

Câu 3. Trong 40 lần triển khai production, 4 lần gây suy giảm dịch vụ cần khắc phục. Theo quy ước đó, change failure rate là bao nhiêu?
A. 10% tổng số lần triển khai production trong kỳ.
B. 4% tổng số lần triển khai production trong kỳ.
C. 25% tổng số lần triển khai production trong kỳ.
D. 40% tổng số lần triển khai production trong kỳ.
Đáp án đúng: A

Câu 4. Một bản phát hành lúc 09:00 gây lỗi từ 09:10; rollback lúc 09:30 và dịch vụ phục hồi lúc 09:40. Khoảng nào thể hiện thời gian phục hồi sự cố?
A. Từ 09:00 khi triển khai đến 09:30 khi thực hiện rollback.
B. Từ 09:10 khi lỗi bắt đầu đến 09:40 khi dịch vụ phục hồi.
C. Từ 09:00 khi triển khai đến 09:10 khi phát hiện lỗi.
D. Từ 09:30 khi rollback đến 09:40 khi dịch vụ hoạt động.
Đáp án đúng: B

Câu 5. Một lần phát hành gộp nhiều commit. Để tính lead time cho từng commit, bộ dữ liệu nào cần liên kết với nhau?
A. Mã issue, ngày tạo sprint và kết quả kiểm thử trước phát hành.
B. Thời điểm review và số dòng mã trong từng merge request.
C. Commit SHA, thời điểm commit và bản production chứa commit.
D. Kích thước artifact, số runner và lịch sử cache của build.
Đáp án đúng: C

Câu 6. Một pipeline triển khai cùng phiên bản tới dev, staging và production. Với deployment frequency ở production, ghi nhận thế nào?
A. Ba lần triển khai vì pipeline sử dụng ba môi trường.
B. Một lần cho mỗi stage trong pipeline của bản phát hành.
C. Một lần triển khai production của dịch vụ đang xét.
D. Không ghi nhận vì ba môi trường dùng chung một pipeline.
Đáp án đúng: C

Câu 7. Trong kỳ, 2 lần triển khai production gây gián đoạn phải khắc phục; 5 pipeline kiểm thử thất bại trước phát hành. Tử số change failure rate là gì?
A. Bảy lần lỗi gồm cả kiểm thử và triển khai production.
B. Hai lần triển khai production gây gián đoạn dịch vụ.
C. Năm lần kiểm thử thất bại trước khi triển khai thực tế.
D. Tất cả lần triển khai lẫn job kiểm thử trong cùng kỳ.
Đáp án đúng: B

Câu 8. Một release lỗi được khắc phục bằng fix-forward thay vì rollback. Khi đo tốc độ phục hồi, mốc kết thúc nào phù hợp?
A. Khi pipeline sửa lỗi bắt đầu chạy job triển khai vào production.
B. Khi dịch vụ trở lại trạng thái phục vụ bình thường.
C. Khi merge request sửa lỗi vừa được review xong.
D. Khi ticket sự cố được chuyển sang trạng thái đóng.
Đáp án đúng: B

Câu 9. Phân tích value stream cho thấy phần lớn lead time nằm ở hàng đợi phê duyệt trước production. Hướng cải tiến nào tác động trực tiếp nút thắt?
A. Giảm thời gian chờ phê duyệt bằng quy trình kiểm soát phù hợp.
B. Tăng cache ở bước compile dù build chỉ mất vài phút mỗi lần.
C. Thêm runner cho test dù thời gian test đã rất ngắn.
D. Đổi công cụ build image khi chưa có giới hạn tài nguyên.
Đáp án đúng: A

Câu 10. Một đội triển khai thủ công ngoài GitLab CI nhưng dashboard chỉ đếm pipeline deploy. Rủi ro chính với deployment frequency là gì?
A. Đếm thừa các lần release vì các job kiểm thử chạy song song.
B. Đếm cả môi trường staging khi chỉ có môi trường production.
C. Đếm gộp các commit khác nhau thành một thay đổi duy nhất.
D. Bỏ sót các lần phát hành thủ công ngoài nguồn pipeline CI.
Đáp án đúng: D

Câu 11. Median lead time giảm mạnh nhưng p95 còn cao. Cách diễn giải nào hữu ích nhất khi chọn cải tiến tiếp theo?
A. Median thấp chứng minh mọi thay đổi đều được giao nhanh.
B. p95 cao là bình thường nên không cần kiểm tra dữ liệu.
C. Chỉ dùng median vì p95 luôn bị sai lệch bởi số commit.
D. Điều tra các thay đổi chậm để tìm phần chờ đợi kéo dài.
Đáp án đúng: D

Câu 12. Sau một đợt cải tiến, deployment frequency tăng nhưng change failure rate cũng tăng rõ rệt. Đánh giá nào hợp lý?
A. Đã cải thiện toàn diện vì số lần đưa phần mềm lên nhiều hơn.
B. Tốc độ phát hành tăng nhưng cần xử lý rủi ro chất lượng.
C. Có thể bỏ qua lỗi vì nhiều bản phát hành giúp thử nhanh.
D. Chỉ cần giảm thời gian build là chất lượng sẽ cải thiện.
Đáp án đúng: B

Câu 13. Hai dịch vụ có mức độ rủi ro và quy trình phê duyệt khác nhau. Nên so sánh chỉ số DORA như thế nào để tránh kết luận sai?
A. Thống nhất cách đo, xét bối cảnh rồi theo dõi xu hướng riêng.
B. So tốc độ triển khai tuyệt đối rồi xếp hạng hiệu quả dịch vụ.
C. So số lần triển khai mà bỏ qua phạm vi mỗi dịch vụ.
D. Chỉ so thời gian build vì hai hệ thống đều có CI.
Đáp án đúng: A

Câu 14. Một release gộp 10 commit được đưa lên production cùng lúc. Khi đo lead time for changes theo từng commit, cách tính nào phù hợp?
A. Lấy thời điểm merge của commit cuối làm mốc chung cho tất cả.
B. Tính từ lúc job deploy bắt đầu đến khi job trả về success.
C. Chỉ đo commit mới nhất vì các commit cũ đã được kiểm thử.
D. Dùng mốc tạo từng commit và lúc bản chứa nó lên production.
Đáp án đúng: D

Câu 15. Sau deploy, tính năng mới làm tăng lỗi. Nhóm tắt feature flag và dịch vụ hồi phục trước khi rollback code. Thời điểm nào kết thúc thời gian phục hồi?
A. Khi pipeline deploy gần nhất chuyển về trạng thái thành công.
B. Khi ticket sự cố đã được giao cho người trực ca xử lý.
C. Khi commit sửa lỗi vừa được tạo trên nhánh chính.
D. Khi dịch vụ thực tế phục hồi sau thao tác tắt feature flag.
Đáp án đúng: D

Câu 16. Để điều tra sự cố liên quan phát hành và tính thời gian phục hồi, mỗi bản ghi incident cần thông tin nào?
A. Người review, độ dài diff và thời lượng unit test.
B. Runner ID, loại build image và dung lượng cache.
C. Deployment ID liên quan, lúc bắt đầu lỗi và lúc phục hồi.
D. Sprint ID, số story point và lượt bình luận trên issue phát hành.
Đáp án đúng: C
