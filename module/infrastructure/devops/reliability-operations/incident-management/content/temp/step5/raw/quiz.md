Câu 1: Pipeline deploy báo thành công nhưng khách không thể thanh toán. Tín hiệu nào cần kiểm tra đầu tiên?
A. Mức sử dụng CPU của runner CI trong đợt triển khai vừa rồi.
B. Trạng thái hoàn thành của pipeline vừa phát hành.
C. Tỷ lệ thanh toán thành công và lỗi ở lưu lượng thực.
D. Số commit vừa được gộp vào nhánh chính hôm nay.
Đáp án đúng: C

Câu 2: Cùng xuất hiện lỗi HTTP 500: checkout ảnh hưởng mọi khách, trang demo chỉ ảnh hưởng đội nội bộ. Dựa vào đâu phân severity?
A. Thời gian build và số artifact đang chờ triển khai.
B. Số lượng thay đổi mã trong lần phát hành cuối.
C. Dung lượng log tạo ra trên từng node của dịch vụ.
D. Phạm vi khách bị ảnh hưởng và tác động nghiệp vụ.
Đáp án đúng: D

Câu 3: Nhiều đội xử lý sự cố SEV1 cùng lúc, việc điều tra chồng chéo. Incident Commander cần làm gì?
A. Nhận mọi ticket kỹ thuật và tự sửa lỗi trên máy chủ.
B. Phân vai, quyết định ưu tiên và giữ nhịp phối hợp.
C. Chỉ duyệt thay đổi source code của đội phát triển.
D. Hoãn mọi cập nhật đến khi có root cause chắc chắn.
Đáp án đúng: B

Câu 4: Trong cuộc gọi xử lý, quyết định rollback bị lặp vì không ghi ai làm gì. Cách nào khắc phục?
A. Chuyển cuộc gọi sang riêng từng đội, không ghi biên bản chung.
B. Chỉ định scribe ghi mốc, quyết định và người thực hiện.
C. Yêu cầu từng kỹ sư tổng hợp từ trí nhớ sau sự cố.
D. Chỉ ghi trạng thái cuối khi hệ thống phục hồi xong.
Đáp án đúng: B

Câu 5: Vừa bật tính năng qua feature flag, lỗi 5xx tăng mạnh; thao tác tắt flag đã được kiểm thử. Ưu tiên gì?
A. Tắt flag để giảm tác động rồi tiếp tục điều tra.
B. Giữ flag bật để thu thập thêm lỗi ở production.
C. Hạ ngưỡng alert để tránh nhận thêm trang báo.
D. Chờ phân tích nguyên nhân gốc rồi mới giảm thiểu.
Đáp án đúng: A

Câu 6: Deploy gây lỗi 5xx; bản trước ổn định và schema DB vẫn tương thích. Biện pháp nào hợp lý?
A. Khởi động lại phiên bản lỗi trên tất cả instance đang chạy.
B. Chỉ thêm replica của phiên bản mới đang gặp lỗi.
C. Rollback về bản ổn định rồi kiểm chứng luồng chính.
D. Khôi phục DB từ backup dù dữ liệu vẫn hợp lệ.
Đáp án đúng: C

Câu 7: Primary on-call không phản hồi trong thời hạn quy định, dịch vụ đang xấu đi. Cần làm gì?
A. Đợi primary phản hồi rồi mới gửi thông báo tiếp.
B. Chỉ giảm mức severity để dừng việc paging liên tục.
C. Chuyển incident thành backlog và chờ giờ làm việc.
D. Escalate tới backup theo policy, thông tin cho IC.
Đáp án đúng: D

Câu 8: Nguyên nhân chưa được xác nhận nhưng khách hàng yêu cầu cập nhật SEV1. Status page nên nêu gì?
A. Ảnh hưởng đã biết, biện pháp và mốc cập nhật kế tiếp.
B. Giả thuyết chưa kiểm chứng như nguyên nhân đã xác nhận.
C. Danh sách truy cập nội bộ và toàn bộ log lỗi nhạy cảm.
D. Chỉ thời điểm mở ticket mà bỏ trạng thái hệ thống.
Đáp án đúng: A

Câu 9: Trong incident có ba giả thuyết về lỗi database, metrics chưa rõ. Cách điều tra nào có cơ sở?
A. Chọn giả thuyết đến sớm nhất rồi công bố ngay là root cause.
B. Đối chiếu thời điểm metric, log và thay đổi để kiểm chứng.
C. Khởi động lại DB để xem cảnh báo có tự biến mất không.
D. Dựa vào lần incident cũ để chốt nguyên nhân hiện tại.
Đáp án đúng: B

Câu 10: Đã rollback, healthcheck HTTP 200 trở lại nhưng checkout vẫn lỗi. Khi nào có thể công bố khôi phục?
A. Khi luồng thanh toán và chỉ số người dùng ổn định lại.
B. Khi pipeline rollback kết thúc không có lỗi kỹ thuật.
C. Khi mọi pod đều trả về readiness probe thành công.
D. Khi log không còn ghi lần restart của instance.
Đáp án đúng: A

Câu 11: Postmortem ghi 'kỹ sư X cấu hình sai'. Cách trình bày nào phù hợp nguyên tắc không đổ lỗi?
A. Phân tích điều kiện hệ thống và rào chắn đã thiếu.
B. Gắn tên kỹ sư và yêu cầu người đó không tái phạm.
C. Chỉ tường thuật hành động, bỏ qua yếu tố bối cảnh.
D. Đánh giá từng cá nhân theo số lần thao tác lỗi.
Đáp án đúng: A

Câu 12: Sau sự cố, các đội nhớ khác nhau về thứ tự rollback và lỗi. Dựng timeline thế nào đáng tin?
A. Chỉ dựa vào ghi chú của người tham gia lâu nhất.
B. Lấy thứ tự ticket khi được phân công xử lý.
C. Dùng thời điểm gửi email nội bộ làm mốc duy nhất.
D. Đối chiếu timestamp log, metric, deploy và ghi chép.
Đáp án đúng: D

Câu 13: Postmortem ghi action 'cải thiện cảnh báo' nhưng không ai thực hiện. Sửa thế nào để theo dõi được?
A. Giữ nguyên action để các nhóm tự chia phần việc.
B. Chuyển action thành đề xuất không có hạn hoàn tất.
C. Gán owner, hạn hoàn thành và tiêu chí xác nhận.
D. Chỉ tăng độ ưu tiên của incident đã đóng trong hệ thống.
Đáp án đúng: C

Câu 14: On-call chạy nhầm bước rollback vì runbook không có tiêu chí dừng. Cần cải tiến thế nào?
A. Chỉ bổ sung đường dẫn tới dashboard mà bỏ các bước làm.
B. Ghi điều kiện kích hoạt, bước làm, kiểm chứng và cách hoàn tác.
C. Xóa phần rollback để tránh kỹ sư thực hiện sai thao tác khi trực.
D. Ghi toàn bộ lệnh gần đây nhưng không cần nêu thứ tự.
Đáp án đúng: B

Câu 15: Trước ngày bán hàng cao điểm, cần thử phân vai khi primary on-call mất liên lạc. Hoạt động gì?
A. Chỉ chạy benchmark CPU cho từng container của dịch vụ.
B. Chỉ review danh sách người trực trong bảng tính của đội.
C. Chỉ kiểm tra dashboard trong cuộc họp định kỳ tuần.
D. Diễn tập sự cố, đo thời gian escalation và rút kinh nghiệm.
Đáp án đúng: D

Câu 16: Mười alert từ cùng một outage gây nhiều page trùng lặp cho on-call. Cải tiến nào hợp lý?
A. Tắt toàn bộ alert của hệ thống đang lỗi tới hết tuần.
B. Chỉ tăng ngưỡng cảnh báo dù chưa đánh giá ảnh hưởng.
C. Nhóm alert cùng sự cố, dedup và page theo tác động.
D. Chỉ gửi cảnh báo sau khi khách hàng tự báo lỗi.
Đáp án đúng: C
