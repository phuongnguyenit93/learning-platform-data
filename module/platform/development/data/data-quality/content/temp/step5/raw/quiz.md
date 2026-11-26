1. Một đơn hàng thiếu trường `customer_id` bắt buộc làm giảm chiều chất lượng nào?
A. Độ hợp lệ vì giá trị nằm ngoài miền đã khai báo
B. Độ duy nhất vì có nhiều bản ghi chung một khóa
C. Tính kịp thời vì đơn hàng được gửi sau thời hạn
D. Độ đầy đủ vì thông tin bắt buộc chưa được cung cấp
Đáp án đúng: D

2. Trường `age = 180` có kiểu số đúng nhưng vượt miền 0–120. Vấn đề chính là gì?
A. Độ hợp lệ do giá trị nằm ngoài miền nghiệp vụ
B. Độ đầy đủ do trường tuổi vắng mặt trong JSON
C. Độ duy nhất do nhiều người có cùng giá trị tuổi
D. Tính kịp thời do bản ghi tuổi đến quá trễ
Đáp án đúng: A

3. Địa chỉ giao hàng đúng định dạng nhưng khác địa chỉ thực tế vi phạm chiều nào?
A. Độ đầy đủ vì địa chỉ không có dấu phân cách
B. Độ chính xác vì giá trị khác sự thật đối chiếu
C. Độ duy nhất vì địa chỉ xuất hiện ở nhiều đơn
D. Tính kịp thời vì đơn hàng cập nhật không đều
Đáp án đúng: B

4. Trạng thái đơn ở CRM là `PAID`, còn hệ thống kho là `NEW`. Vấn đề nổi bật là gì?
A. Tính duy nhất vì mỗi hệ thống có một mã đơn
B. Độ đầy đủ vì hệ thống kho không có trường trạng thái
C. Tính nhất quán vì trạng thái hai nguồn lệch nhau
D. Độ chính xác của kiểu dữ liệu trong JSON bị sai
Đáp án đúng: C

5. Hai bản ghi khách hàng có cùng mã định danh nghiệp vụ nên kiểm tra chiều nào?
A. Độ duy nhất theo khóa định danh nghiệp vụ
B. Độ hợp lệ của email theo biểu thức chính quy
C. Tính kịp thời của lần đồng bộ gần nhất
D. Độ đầy đủ của các trường tùy chọn trong hồ sơ
Đáp án đúng: A

6. Bản ghi giá cập nhật sau 3 giờ dù SLA yêu cầu 5 phút. Cần đo chiều nào?
A. Độ hợp lệ của giá theo kiểu số thập phân
B. Tính kịp thời so với ngưỡng SLA đã đặt
C. Độ duy nhất của mã mặt hàng trong catalog
D. Độ đầy đủ của các trường bắt buộc trong giá
Đáp án đúng: B

7. Khi profiling một cột, tập thống kê nào thường hữu ích nhất?
A. Chỉ tổng số index đang được tạo trên bảng dữ liệu
B. Chỉ số lượt gọi API tới server trong ngày hôm đó
C. Chỉ thời gian biên dịch dự án khi thay đổi schema
D. Tỷ lệ null, số giá trị phân biệt và phân bố giá trị
Đáp án đúng: D

8. Trong SQL, biểu thức nào đếm giá trị `NULL` của cột `email`?
A. `COUNT(email)` trên toàn bộ tập bản ghi đang xét
B. `COUNT(*) - COUNT(email)` trên tập bản ghi xét
C. `COUNT(DISTINCT email)` trên toàn bộ tập xét
D. `SUM(email)` trên toàn bộ tập bản ghi đang xét
Đáp án đúng: B

9. Để phát hiện khóa nghiệp vụ trùng trong SQL, mẫu truy vấn nào đúng?
A. `ORDER BY business_key LIMIT 1` trên bảng
B. `SELECT DISTINCT business_key` rồi ghi đè
C. `WHERE business_key IS NOT NULL` trên bảng
D. Dùng `GROUP BY ... HAVING COUNT(*) > 1`
Đáp án đúng: D

10. Để tìm bản ghi con có khóa ngoại không tồn tại ở bảng cha, dùng SQL nào?
A. `INNER JOIN` bảng cha rồi chỉ lấy khóa khớp
B. `ORDER BY` khóa ngoại rồi tìm dòng đầu tiên
C. Dùng `LEFT JOIN` và lọc cha có khóa null
D. `GROUP BY` bảng con rồi lấy tổng số bản ghi
Đáp án đúng: C

11. Khi miền nghiệp vụ xem chuỗi trắng như dữ liệu thiếu, rule completeness nên làm gì?
A. Chỉ đếm SQL NULL và mặc định chấp nhận chuỗi trắng
B. Chỉ đếm lỗi JSON parse khi có dấu cách ở cuối
C. Đếm cả chuỗi trắng lẫn giá trị null là thiếu
D. Chỉ đếm bản ghi có cùng mã khóa xuất hiện lại
Đáp án đúng: C

12. Một đơn hàng có `endDate` trước `startDate` dù cả hai đúng định dạng. Cần rule gì?
A. Chỉ kiểm tra regex ngày tháng độc lập từng field
B. Kiểm tra quan hệ thứ tự giữa hai field ngày
C. Chỉ kiểm tra mỗi field có mặt trong dữ liệu JSON
D. Chỉ kiểm tra số ký tự của trường thời gian
Đáp án đúng: B

13. Để giới hạn trường `status` chỉ nhận `NEW`, `PAID`, `CANCELLED`, nên làm gì?
A. Dùng danh sách giá trị hợp lệ cho status
B. Chỉ ép mọi giá trị về kiểu dữ liệu string
C. Chỉ bỏ qua khoảng trắng trước và sau chuỗi
D. Chỉ ghi log khi hệ thống gặp trạng thái lạ
Đáp án đúng: A

14. Hai nguồn cùng có trường `amount` nhưng dùng VND và USD. Trước khi so cần làm gì?
A. Đổi kiểu dữ liệu của trường sang chuỗi văn bản
B. Lấy trung bình hai giá trị để tránh sai lệch
C. Chuẩn hóa đơn vị tiền trước khi đối chiếu
D. Giữ nguyên và so sánh trực tiếp giá trị số
Đáp án đúng: C

15. Muốn đo độ trễ dữ liệu sự kiện, nên so sánh mốc thời gian nào?
A. Thời điểm sự kiện phát sinh và lúc hệ thống nhận được
B. Thời điểm JVM build và lúc container bắt đầu chạy
C. Thời điểm tạo bảng và lúc index được tái xây dựng
D. Thời điểm tạo query và lúc lệnh SQL được parse
Đáp án đúng: A

16. Phương pháp nào phù hợp để phát hiện outlier số khi phân bố dữ liệu lệch?
A. Dùng IQR hoặc percentile và xem xét ngoại lệ nghiệp vụ
B. Chỉ dùng trung bình cộng rồi bỏ mọi giá trị lớn hơn
C. Chỉ kiểm tra tên cột có trùng với catalog hay không
D. Chỉ so số bản ghi của mỗi file với kích thước byte
Đáp án đúng: A

17. Để phát hiện lưu lượng dữ liệu bất thường có tính chu kỳ tuần, nên so ra sao?
A. So với đúng một giờ ngẫu nhiên của tháng trước
B. So với số build thành công của cùng nhóm phát triển
C. So với baseline cùng ngày trong tuần và khung giờ
D. So với số lượng class Java thay đổi trong bản mới
Đáp án đúng: C

18. Kiểm soát schema drift trong pipeline thường nên thực hiện thế nào?
A. Chỉ so thời gian chạy job với phiên chạy nhanh nhất
B. Đối chiếu schema mới với data contract hiện hành
C. Chỉ so tổng dung lượng lưu trữ giữa hai hệ thống
D. Chỉ so số lượng log phát sinh khi deploy dịch vụ
Đáp án đúng: B

19. Đối với cảnh báo anomaly nhưng có khuyến mãi lớn, bước nào hợp lý?
A. Tự xóa mọi bản ghi khác phân phối dữ liệu hôm trước
B. Tắt vĩnh viễn toàn bộ rule giám sát về độ lệch
C. Mặc định coi tất cả dữ liệu bất thường là giả
D. Xem ngữ cảnh khuyến mãi trước khi gắn cờ lỗi
Đáp án đúng: D

20. Đặt quality gate cho field thanh toán quan trọng, cách đánh giá nào tốt?
A. Chỉ ghi nhận số dòng xử lý và bỏ qua chất lượng giá trị
B. Cho mọi bản ghi đi qua nếu batch đã hoàn thành đủ số dòng
C. Chỉ kiểm tra kiểu dữ liệu vào ngày cuối mỗi tháng
D. Dùng ngưỡng lỗi phù hợp rủi ro và chặn khi vượt ngưỡng
Đáp án đúng: D

21. Khi phát hiện bản ghi sai quy tắc, quy trình quarantine nên lưu gì?
A. Chỉ tên bảng đích rồi xóa bản ghi không hợp lệ
B. Chỉ lưu tổng số lỗi mà không lưu định danh bản ghi
C. Dữ liệu lỗi, lý do lỗi và dấu vết nguồn để xử lý lại
D. Chỉ gửi thông báo nhưng vẫn phát hành dữ liệu lỗi
Đáp án đúng: C

22. Với lỗi mạng tạm thời khác lỗi schema cố định, pipeline nên xử lý ra sao?
A. Retry hữu hạn lỗi mạng; cách ly lỗi schema
B. Retry vô hạn cho mọi lỗi schema cho tới khi hết hạn
C. Coi mọi lỗi mạng là dữ liệu hỏng cần loại vĩnh viễn
D. Chuyển mọi lỗi sang trạng thái thành công để khỏi dừng
Đáp án đúng: A

23. Trong Java, `Validator.validate(bean)` của Jakarta Validation giúp làm gì?
A. Tự sửa mọi trường lỗi rồi cập nhật bản ghi trong DB
B. Trả về các vi phạm constraint đã khai báo trên bean
C. Kiểm tra tính chính xác với mọi nguồn dữ liệu bên ngoài
D. Tự loại bản ghi trùng trước khi commit một transaction
Đáp án đúng: B

24. Để giám sát chất lượng qua nhiều lần chạy pipeline, nên theo dõi gì?
A. Chỉ tổng số thư viện được tải khi chạy tác vụ ETL
B. Chỉ tên người tạo migration ở phiên bản gần nhất
C. Chỉ dung lượng log khi job thành công hoàn toàn
D. Theo dõi tỷ lệ null, trùng, lỗi và trễ theo batch
Đáp án đúng: D
