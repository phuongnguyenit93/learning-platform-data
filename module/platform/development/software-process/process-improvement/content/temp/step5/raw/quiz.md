1. Khi lập value stream map cho tính năng phần mềm, nên vẽ phạm vi nào?
A. Từ lần đầu commit mã đến lúc unit test báo thành công
B. Từ lúc lập kế hoạch sprint đến lúc nhóm họp retrospective
C. Từ lúc phát sinh nhu cầu đến khi giá trị đến người dùng
D. Từ khi pull request mở đến khi reviewer nhấn approve
Đáp án đúng: C

2. Trong bản đồ dòng giá trị, thời gian chờ ở hàng đợi thể hiện điều gì?
A. Công việc chưa được xử lý dù vẫn làm tăng lead time
B. Công việc đang được chỉnh sửa tích cực trong một bước
C. Thời gian máy CI thực thi các ca kiểm thử cần thiết
D. Thời gian lập trình viên kiểm chứng bản sửa trước merge
Đáp án đúng: A

3. Khi một ticket chờ review ba ngày và được review một giờ, đâu là nhận định đúng?
A. Thời gian xử lý gần bằng tổng thời gian nằm trong review
B. Thời gian chờ không được tính vào lead time của ticket
C. Tốc độ review chắc chắn là nút thắt của toàn hệ thống
D. Thời gian chờ lớn hơn nhiều thời gian xử lý thực tế
Đáp án đúng: D

4. Flow efficiency thường được tính bằng tỷ lệ nào?
A. Số ticket hoàn tất chia tổng số ticket đã được tạo
B. Thời gian xử lý tạo giá trị chia tổng thời gian luồng
C. Tổng thời gian chờ chia số người tham gia quy trình
D. Thời gian sửa lỗi chia thời gian chạy pipeline CI
Đáp án đúng: B

5. Nếu một việc được xử lý hai ngày trong tổng lead time mười ngày, flow efficiency là bao nhiêu?
A. 80%, vì tám ngày chờ được xem là chi phí vận hành
B. 20%, vì 2 ngày xử lý trên tổng 10 ngày lead time
C. 5%, vì mười ngày lead time lớn hơn hai ngày xử lý
D. 50%, vì chỉ có hai loại thời gian xử lý và chờ đợi
Đáp án đúng: B

6. Tín hiệu nào thường gợi ý một bước đang là điểm nghẽn của dòng công việc?
A. Nhân viên ở bước ấy báo rằng mình thường xuyên bận rộn
B. Bước ấy có số công cụ tự động hóa ít hơn các bước khác
C. Bước ấy nằm gần cuối quy trình nên nhận nhiều ticket
D. Hàng đợi trước bước ấy liên tục tăng qua nhiều kỳ đo
Đáp án đúng: D

7. Giới hạn WIP giúp cải thiện dòng chảy chủ yếu bằng cách nào?
A. Đảm bảo mọi người luôn làm đồng thời nhiều việc nhất có thể
B. Buộc tất cả ticket chạy qua cùng một người phê duyệt cuối
C. Giảm việc làm dở và thúc đẩy hoàn tất trước khi nhận thêm
D. Tăng kích thước mỗi batch để giảm số lần chuyển giao
Đáp án đúng: C

8. Định luật Little trong hệ thống ổn định liên hệ các đại lượng nào?
A. Throughput trung bình bằng WIP cộng thời gian xử lý
B. WIP trung bình bằng throughput nhân cycle time trung bình
C. Lead time trung bình bằng số người nhân số ticket mở
D. Cycle time trung bình bằng thời gian chờ trừ throughput
Đáp án đúng: B

9. Trên cumulative flow diagram, vùng trạng thái 'In Review' rộng dần thường gợi ý gì?
A. Số việc tồn trong bước review đang tích lũy theo thời gian
B. Thời gian viết code của từng ticket đang giảm đều liên tục
C. Mỗi reviewer đang xử lý cùng số ticket ở mọi thời điểm
D. Tỷ lệ lỗi sản phẩm chắc chắn đang tăng với cùng tốc độ
Đáp án đúng: A

10. Throughput của một nhóm phát triển nên đo theo cách nào?
A. Số hạng mục được khởi tạo nhưng chưa có người xử lý
B. Tổng số giờ lập trình đã được mọi thành viên ghi nhận
C. Số hạng mục hoàn tất trong một khoảng thời gian xác định
D. Số lần hệ thống CI được kích hoạt bởi các lần commit
Đáp án đúng: C

11. Vì sao giảm batch size có thể giúp cải tiến quy trình?
A. Bảo đảm mọi hạng mục trong batch không còn phát sinh lỗi
B. Nhận phản hồi sớm hơn và giảm phạm vi công việc tồn đọng
C. Thay thế hoàn toàn nhu cầu ưu tiên backlog của sản phẩm
D. Tăng thời gian chờ để toàn bộ nhóm làm việc cùng một lúc
Đáp án đúng: B

12. Điều gì thường xảy ra với hàng đợi khi một công đoạn luôn chạy sát 100% công suất?
A. Biến động nhỏ có thể gây thời gian chờ tăng mạnh
B. Mỗi ticket mới luôn được tiếp nhận mà không phải xếp hàng
C. Thông lượng luôn tăng tuyến tính theo số ticket đưa vào
D. Thời gian hoàn thành tất cả hạng mục sẽ giảm về bằng không
Đáp án đúng: A

13. Kỹ thuật Five Whys chủ yếu nhằm mục đích gì?
A. Ghi nhận năm người chịu trách nhiệm cho sự cố gần nhất
B. Bảo đảm nguyên nhân gốc luôn xuất hiện đúng câu hỏi thứ năm
C. Truy tìm cơ chế gây ra vấn đề thay vì dừng ở triệu chứng
D. Thay thế dữ liệu thực nghiệm bằng đánh giá chủ quan nhóm
Đáp án đúng: C

14. Fishbone diagram hữu ích nhất trong tình huống nào?
A. Sắp thứ tự commit theo thời gian nhằm tìm điểm regression
B. Tạo ma trận phân quyền truy cập cho từng module ứng dụng
C. Nhóm giả thuyết nguyên nhân theo các nhánh để kiểm chứng
D. Đánh giá ưu tiên backlog chỉ bằng ước lượng story points
Đáp án đúng: C

15. Khi một lỗi triển khai lặp lại, cải tiến theo tư duy hệ thống nên ưu tiên gì?
A. Yêu cầu cá nhân ký cam kết không bao giờ sai lần nữa
B. Tăng số bước duyệt cho mọi thay đổi mà không đo tác dụng
C. Loại bỏ phần lớn chỉ số lỗi để không ảnh hưởng tinh thần
D. Xem điều kiện quy trình khiến lỗi dễ tái diễn
Đáp án đúng: D

16. Trước khi thay đổi quy trình review, vì sao cần lưu baseline?
A. Bảo đảm mọi cải tiến đều đạt kết quả như dự đoán
B. Giúp dự đoán chính xác mọi kết quả mà không cần thử
C. Có số liệu trước can thiệp để so sánh hiệu quả thực tế
D. Thay thế đo sau thử nghiệm bằng nhận xét cá nhân
Đáp án đúng: C

17. Trong vòng PDCA, bước Plan nên xác định điều gì?
A. Lập tức áp dụng phương pháp mới cho toàn tổ chức
B. Đóng các ticket cũ để thông lượng kỳ đo tăng
C. Công bố phương án mới là chuẩn mà chưa cần kiểm chứng
D. Vấn đề, giả thuyết cải tiến, mục tiêu đo và cách thử
Đáp án đúng: D

18. Với thay đổi quy trình có rủi ro, bước Do trong PDCA nên triển khai thế nào?
A. Thử ở phạm vi giới hạn và thu thập dữ liệu trong lúc chạy
B. Áp dụng trên mọi nhóm ngay để nhận đủ báo cáo đồng thời
C. Chỉ viết tài liệu hướng dẫn mà không cho nhóm thực hiện
D. Đo lại số liệu trước can thiệp rồi bỏ kế hoạch ban đầu
Đáp án đúng: A

19. Trong bước Check của PDCA, cách kiểm chứng hợp lý là gì?
A. So kết quả với baseline và xem cả tác dụng ngoài dự kiến
B. Chỉ hỏi nhóm có thấy quy trình mới quen thuộc hay không
C. Chỉ so số lượng buổi họp trước và sau khi thử nghiệm
D. Chỉ chọn dữ liệu từ các ticket hoàn thành nhanh nhất
Đáp án đúng: A

20. Nếu thử nghiệm cải tiến tốt và các tác dụng phụ chấp nhận được, bước Act làm gì?
A. Quay lại quy trình cũ dù số liệu đã xác nhận tốt
B. Chuẩn hóa thực hành và tiếp tục theo dõi kết quả
C. Nhân rộng lập tức mà bỏ mọi hướng dẫn và đào tạo
D. Ngừng đo lường vì quá trình cải tiến đã hoàn tất
Đáp án đúng: B

21. Kaizen trong cải tiến quy trình thường nhấn mạnh điều gì?
A. Một lần tái cấu trúc lớn để kết thúc mọi vòng cải tiến
B. Chỉ áp dụng thay đổi khi có chứng chỉ quy trình bên ngoài
C. Chỉ xem cải tiến là trách nhiệm của người quản lý cấp cao
D. Những thay đổi nhỏ liên tục có sự tham gia của người làm
Đáp án đúng: D

22. Nếu deployment frequency tăng nhưng change failure rate cũng tăng mạnh, nên kết luận gì?
A. Phải xem thêm chất lượng thay đổi trước khi khẳng định tốt hơn
B. Thông lượng cải thiện chứng minh chất lượng đã tốt hơn trước
C. Số lần triển khai cao tự động bù lại mọi sự cố sản xuất
D. Việc deploy nhiều hơn không liên quan đến trải nghiệm người dùng
Đáp án đúng: A

23. Khi rút ngắn thời gian review, guardrail nào đáng theo dõi để tránh tác dụng phụ?
A. Số lượng biểu tượng trên bảng điều khiển review
B. Tỷ lệ lỗi lọt và công việc sửa lại sau review
C. Số email gửi nhắc người review trong mỗi ngày
D. Tổng số nhánh Git được tạo trong tháng
Đáp án đúng: B

24. Để duy trì cải tiến sau khi thử nghiệm xong, nhóm nên làm gì?
A. Đóng toàn bộ kênh nhận phản hồi để tránh làm rối quy trình
B. Dùng kết quả một tuần làm cam kết vĩnh viễn cho mọi dự án
C. Chuyển quyền quyết định mọi thay đổi cho công cụ thống kê
D. Theo dõi chỉ số định kỳ và điều chỉnh khi bối cảnh đổi
Đáp án đúng: D
