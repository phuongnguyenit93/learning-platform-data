Câu 1. Mục tiêu quan trọng nhất của một Architecture Decision Record (ADR) là gì?
A. Thay mọi tài liệu triển khai bằng sơ đồ package
B. Lưu lý do và hệ quả của một lựa chọn kiến trúc
C. Ghi mọi thay đổi logic trong từng lần commit
D. Liệt kê riêng các vấn đề chưa có người xử lý
Đáp án đúng: B

Câu 2. Khi viết phần Context của ADR, thông tin nào hữu ích nhất cho người đọc sau này?
A. Tên tác giả mà không cần mô tả vấn đề cần giải
B. Danh sách lệnh build chạy qua trên máy tác giả
C. Các file Java vừa được formatter tự sửa đổi
D. Ràng buộc và lực tác động dẫn tới quyết định
Đáp án đúng: D

Câu 3. Một ADR nêu chọn message broker thay HTTP đồng bộ; mục Decision nên ghi gì?
A. Chỉ câu hỏi cần giải quyết mà không chọn hướng
B. Chỉ liệt kê tên các giải pháp đã từng được thử
C. Phương án được chọn và phạm vi áp dụng
D. Chỉ mô tả cách chạy deployment hiện tại
Đáp án đúng: C

Câu 4. Khi nhóm cân nhắc polling và CDC, cách ghi Alternatives nào có giá trị nhất?
A. Bỏ lựa chọn không được chọn để tài liệu ngắn
B. Nêu các lựa chọn khả thi và lý do loại bỏ
C. Đổi tên giải pháp còn lại theo tên đội phát triển
D. Chỉ ghi phương án dễ triển khai nhất trên máy dev
Đáp án đúng: B

Câu 5. Trạng thái Proposed của một ADR nên truyền đạt điều gì?
A. Quyết định đang được đưa ra để review
B. Quyết định cũ đã được thay thế hoàn toàn
C. Quyết định đã áp dụng ở mọi môi trường
D. Quyết định đã bị bác bỏ và không cần bàn nữa
Đáp án đúng: A

Câu 6. Một ADR Accepted cần thay đổi vì xuất hiện ràng buộc mới; cách giữ lịch sử hợp lý?
A. Sửa âm thầm nội dung cũ như chưa từng được chấp nhận
B. Xóa ADR cũ rồi chỉ để lại bản mô tả ngắn
C. Đưa ADR cũ về trạng thái Proposed và mất lịch sử
D. Tạo ADR kế tiếp và liên kết supersedes/superseded
Đáp án đúng: D

Câu 7. Sau quyết định dùng cache, phần Consequences nên ghi điều gì ngoài lợi ích?
A. Nguy cơ stale data và chi phí vận hành cache
B. Chỉ danh sách dependency đã build thành công
C. Chỉ phần code mẫu sử dụng annotation cache
D. Tất cả ticket đóng trong sprint trước đó
Đáp án đúng: A

Câu 8. Vì sao ADR nên ghi decision drivers trước khi chốt một lựa chọn?
A. Để mọi ADR đều bắt buộc chọn giải pháp nhanh nhất
B. Để thay thế hoàn toàn bước review với các bên liên quan
C. Để tiêu chí chọn có thể truy vết khi điều kiện đổi
D. Để tạo danh sách file cần thêm vào dự án
Đáp án đúng: C

Câu 9. Nếu một ADR nói “chọn database X vì tốt hơn”, thiếu yếu tố nào rõ nhất?
A. Sơ đồ UI của mọi màn hình đang dùng database
B. Tên lệnh chạy mọi database migration
C. Danh sách các biến môi trường của CI
D. Tiêu chí và đánh đổi so với phương án khác
Đáp án đúng: D

Câu 10. Vì sao nên lưu ADR cùng repository thay vì chỉ trong cuộc trò chuyện rời rạc?
A. Vì repository tự động kiểm chứng mọi luận điểm kiến trúc
B. Vì review, phiên bản và liên kết với thay đổi mã dễ hơn
C. Vì tệp Markdown bắt buộc thay thế kiểm thử hệ thống
D. Vì mọi tác giả có thể bỏ qua quy tắc bảo mật
Đáp án đúng: B

Câu 11. Đường liên kết nào hỗ trợ truy vết một ADR đã chấp nhận tới triển khai?
A. Chỉ liên kết tới trang tổng quan của công ty
B. Chỉ liên kết tới thời điểm hội thảo gần nhất
C. Liên kết PR, issue hoặc phần bị ảnh hưởng
D. Chỉ liên kết tới mô tả công việc người phê duyệt
Đáp án đúng: C

Câu 12. Khi review ADR về dữ liệu cá nhân, ai cần được tham gia phù hợp?
A. Chỉ người viết test để xác nhận định dạng Markdown
B. Người liên quan, gồm bảo mật và dữ liệu khi cần
C. Chỉ tác giả của commit gần nhất trong repository
D. Bất kỳ ai không biết hệ thống để không có thiên lệch
Đáp án đúng: B

Câu 13. Tại sao ADR không nên là một tài liệu dài mô tả toàn bộ codebase?
A. Vì ADR tập trung một quyết định và lý do
B. Vì ADR chỉ được chứa đúng một câu trong mỗi mục
C. Vì ADR không được phép mô tả kiến trúc phần mềm
D. Vì ADR luôn phải là sơ đồ thay vì văn bản
Đáp án đúng: A

Câu 14. Nếu phương án bị từ chối nhưng có lập luận tốt, nên xử lý thế nào trong ADR?
A. Xóa hoàn toàn để người sau không tranh luận lại
B. Ghi đó là phương án được chọn ở mọi tình huống
C. Ẩn rủi ro của phương án được chọn khỏi mọi người
D. Giữ lý do bác bỏ và điều kiện xét lại
Đáp án đúng: D

Câu 15. Khi ràng buộc latency đổi từ 500 ms sang 100 ms, ADR cũ cần được đánh giá ra sao?
A. Xem lại decision drivers và hiệu lực lựa chọn
B. Giữ nguyên vì ADR Accepted không thể bị thay đổi
C. Xóa mọi so sánh độ trễ để tránh xung đột
D. Chỉ đổi tiêu đề mà không xem lại hệ quả
Đáp án đúng: A

Câu 16. Trong một ADR chọn giao tiếp bất đồng bộ, “hệ quả” nào cần nêu bên cạnh throughput?
A. Chỉ tên queue đã tạo ở môi trường local
B. Chỉ sơ đồ deploy ở lần phát hành đầu
C. Độ trễ nhất quán và cách xử lý lỗi event
D. Chỉ số lượng controller HTTP còn trong mã
Đáp án đúng: C

Câu 17. Khi chọn giải pháp có rủi ro chưa được giải quyết, cách ghi nào giúp quản trị tốt hơn?
A. Bỏ qua rủi ro nếu đa số thành viên đã đồng ý
B. Đánh dấu lựa chọn hoàn toàn không có hệ quả
C. Ghi rủi ro, giả định và biện pháp giảm thiểu
D. Để người đọc tự suy đoán từ lịch sử commit
Đáp án đúng: C

Câu 18. Một ADR được review tốt cần giúp người mới trả lời câu hỏi nào?
A. Vì sao nhóm chọn hướng này trong bối cảnh đó
B. Ai là người viết nhiều dòng mã nhất cho tính năng
C. Tại sao mọi test trong repository đều phải chạy chậm
D. Khi nào trình formatter đổi thứ tự import
Đáp án đúng: A

Câu 19. Để tránh nhiều ADR tự mâu thuẫn, quản lý repository nên làm gì?
A. Chỉ đổi tên mọi ADR thành số thứ tự mới
B. Xóa những ADR cũ ngay khi có thảo luận
C. Bắt mọi ADR đều ở trạng thái Proposed mãi
D. Dùng trạng thái và liên kết thay thế rõ ràng
Đáp án đúng: D

Câu 20. Khi review ADR đề xuất tách một dịch vụ, câu hỏi nào phản ánh đánh đổi có ý nghĩa?
A. Chi phí vận hành và nhất quán dữ liệu thay đổi ra sao?
B. Tên package nên viết hoa hay viết thường?
C. Mỗi class có bao nhiêu dòng comment hợp lý?
D. Có thể bỏ hết test tích hợp để giảm build time không?
Đáp án đúng: A

Câu 21. Đội đã chấp nhận ADR nhưng giải pháp chưa được triển khai; diễn giải nào đúng nhất?
A. Accepted đồng nghĩa mã đã deploy lên production
B. Chấp nhận quyết định khác với đã triển khai
C. ADR phải tự chuyển sang Rejected sau mỗi sprint
D. Việc chưa triển khai khiến mọi lập luận trở nên sai
Đáp án đúng: B

Câu 22. Khi nhiều nhóm cùng quyết định ranh giới giữa hai dịch vụ, tài liệu nào giúp tránh hiểu khác nhau?
A. Chỉ tiêu đề ticket quản lý một trong hai nhóm
B. Chỉ ảnh sơ đồ được gửi trong buổi họp đầu
C. ADR nêu phạm vi và liên kết thỏa thuận liên quan
D. Chỉ danh sách các endpoint chưa được phân loại
Đáp án đúng: C

Câu 23. Một ADR mô tả lựa chọn công nghệ còn phụ thuộc benchmark chưa xong; trạng thái nào phù hợp?
A. Accepted dù chưa có đủ thông tin để chọn
B. Superseded vì chưa từng có quyết định cũ
C. Rejected vì mọi phép đo đều chưa hoàn tất
D. Proposed cho đến khi đủ căn cứ quyết định
Đáp án đúng: D

Câu 24. Một quyết định kiến trúc chỉ nên tách thành ADR mới khi nào?
A. Mỗi khi bổ sung một comment vào source code
B. Khi có quyết định với bối cảnh và đánh đổi riêng
C. Mỗi lần đội phát triển mở lại trình soạn thảo
D. Khi đổi tên một biến trong cùng use case
Đáp án đúng: B
