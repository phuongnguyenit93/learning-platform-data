1. Hai hệ thống cùng lưu `status` dạng string nhưng hiểu `DONE` khác nhau. Lỗi nào xảy ra?
A. Sai khác ngữ nghĩa dù kiểu dữ liệu hai bên giống nhau
B. Sai kiểu JSON vì một hệ thống không nhận giá trị string
C. Sai định dạng file vì trường có tên giống nhau
D. Sai tính duy nhất vì nhiều trạng thái trùng ký tự
Đáp án đúng: A

2. Trong business glossary, một thuật ngữ dữ liệu nên được mô tả bằng gì?
A. Chỉ tên cột kỹ thuật và độ dài tối đa của kiểu
B. Chỉ tên file xuất báo cáo cùng lịch chạy batch
C. Định nghĩa, ví dụ, ngữ cảnh và người sở hữu
D. Chỉ nơi đặt database và số kết nối đang mở
Đáp án đúng: C

3. Hai nhóm báo cáo dùng trường `revenue` nhưng ra số khác. Cần làm rõ điều gì?
A. Trường có kiểu `decimal` hay `double` trong Java
B. Cột có tạo index tại hệ thống nguồn hay chưa
C. Doanh thu trước hay sau giảm trừ và theo kỳ nào
D. Bảng báo cáo có được phân vùng theo tháng không
Đáp án đúng: C

4. Khi cùng khái niệm có tên `client` và `customer`, nên làm gì?
A. Tạo hai mã nghiệp vụ khác nhau cho mỗi tên đang dùng
B. Chỉ đổi mọi tên cột thành chuỗi ngắn trong database
C. Giữ hai định nghĩa đối lập để không phải đổi schema
D. Thống nhất thuật ngữ chuẩn và ánh xạ tên khác
Đáp án đúng: D

5. Vì sao mã định danh khách hàng thường tốt hơn tên hiển thị để join?
A. Tên luôn duy nhất nếu đã được chuẩn hóa kiểu Unicode
B. Mã có quy tắc ổn định, còn tên có thể đổi hoặc trùng
C. Mã định danh tự mang đủ ý nghĩa mọi trường nghiệp vụ
D. Tên hiển thị luôn được cập nhật đồng thời giữa hệ thống
Đáp án đúng: B

6. Trong dữ liệu đa tenant, mã `customerId` chỉ duy nhất từng tenant. Khóa nào đúng?
A. Chỉ dùng `customerId` mà bỏ mọi thông tin tenant
B. Kết hợp `tenantId` và `customerId` khi định danh
C. Chỉ dùng tên khách hàng làm khóa toàn bộ hệ thống
D. Dùng ngày cập nhật thay cho định danh khách hàng
Đáp án đúng: B

7. Hai API dùng mã trạng thái khác nhau cho cùng nghiệp vụ. Cách tích hợp nào đúng?
A. Ép mọi mã nguồn thành chuỗi viết hoa rồi so thẳng
B. Giữ nguyên mọi mã và coi những ký tự giống là đồng nghĩa
C. Đổi kiểu dữ liệu mã thành số nhưng giữ nguyên nhãn
D. Tạo bảng ánh xạ từ mã nguồn sang nghĩa chuẩn đích
Đáp án đúng: D

8. Nguồn A đo khối lượng bằng kg, nguồn B dùng lb. Cần làm gì trước khi so sánh?
A. Chuẩn hóa đơn vị và chuyển đổi bằng hệ số tương ứng
B. Chỉ ép cả hai trường về cùng kiểu số thập phân
C. Chỉ làm tròn hai giá trị về cùng số chữ số
D. Giữ nguyên số đo vì tên trường ở hai nguồn giống nhau
Đáp án đúng: A

9. Để so sánh hai khoản tiền ở hai loại tiền tệ, quy tắc nào cần có?
A. Mã tiền, thời điểm tỷ giá và quy tắc quy đổi rõ ràng
B. Chỉ số chữ số sau dấu phẩy của hai nguồn dữ liệu
C. Chỉ tên cột nguồn và tên cột đích trong file mapping
D. Chỉ định dạng dấu phân cách hàng nghìn của JSON
Đáp án đúng: A

10. Một mốc `2026-03-01 09:00` không kèm múi giờ có rủi ro gì?
A. Không phân biệt được kiểu chuỗi với kiểu boolean
B. Thiếu múi giờ khiến thời điểm tuyệt đối mơ hồ
C. Không thể lưu vào bất kỳ cột timestamp của database
D. Không thể so sánh hai chuỗi nếu độ dài giống nhau
Đáp án đúng: B

11. Trong data contract, `null` có thể bị hiểu sai nếu thiếu đặc tả nào?
A. Chỉ yêu cầu mọi giá trị null đổi thành số nguyên 0
B. Chỉ yêu cầu mọi field được sắp xếp theo tên chữ cái
C. Chỉ yêu cầu schema chặn giá trị string dài quá mức
D. Phân biệt chưa biết, không áp dụng và cố ý bỏ trống
Đáp án đúng: D

12. Vì sao cần phân biệt property vắng mặt và property có giá trị `null`?
A. Chúng luôn được mọi consumer hiểu tương đương nhau
B. Chúng có thể mang hai thông điệp nghiệp vụ khác nhau
C. Chúng khác nhau duy nhất ở thứ tự key khi serialize
D. Chúng chỉ ảnh hưởng số lượng index của bảng dữ liệu
Đáp án đúng: B

13. Khi số dư bằng `0` là hợp lệ, quy ước missing value nào phù hợp?
A. Dùng số 0 làm mã cho mọi giá trị không được quan sát
B. Giữ số 0 hợp lệ và mã hóa thiếu dữ liệu riêng
C. Đổi mọi số 0 thành chuỗi trống để tránh hiểu nhầm
D. Loại mọi bản ghi số dư bằng 0 khỏi bảng dữ liệu
Đáp án đúng: B

14. Một enum `status` có mã `CLOSED` không còn dùng. Cần đặc tả điều gì?
A. Nghĩa mã cũ, mã thay thế và chính sách tương thích
B. Chỉ độ dài chuỗi lớn nhất của tất cả mã trạng thái
C. Chỉ thứ tự mã enum khi in sang giao diện người dùng
D. Chỉ kiểu bộ nhớ dùng để lưu trường mã tại runtime
Đáp án đúng: A

15. Khi ánh xạ `shipment_status` từ nguồn sang đích, yêu cầu nào quan trọng?
A. Giữ tương đương nghĩa trạng thái giữa nguồn và đích
B. Các mã chữ nguồn chỉ cần có cùng độ dài với mã đích
C. Các mã nguồn chỉ cần được chuyển sang chữ in hoa
D. Các mã đích phải được sắp xếp theo thứ tự bảng chữ cái
Đáp án đúng: A

16. Hai nhóm gọi người dùng `active` nhưng một bên tính 7 ngày, bên kia 30 ngày. Cần gì?
A. Chỉ đổi tên trường về một mã snake_case thống nhất
B. Chỉ ép cả hai giá trị sang cùng một kiểu boolean
C. Thống nhất tiêu chí active và cửa sổ thời gian
D. Chỉ đồng bộ lịch chạy batch của hai hệ thống nguồn
Đáp án đúng: C

17. Nguồn A mã hóa tỷ lệ `0.15`, nguồn B ghi `15` cho 15%. Cần đặc tả gì?
A. Chỉ độ chính xác dấu phẩy động của trường tỷ lệ
B. Chỉ thứ tự các trường khi xuất sang định dạng CSV
C. Chỉ số lượng bản ghi được phép gửi trong một batch
D. Đơn vị tỷ lệ và cách biểu diễn phần trăm trong dữ liệu
Đáp án đúng: D

18. Phân biệt `event_time` và `ingestion_time` nhằm tránh nhầm điều gì?
A. Thời điểm Java biên dịch với thời điểm API khởi động
B. Thời điểm tạo index với thời điểm tái tổ chức bảng
C. Thời điểm phát sinh nghiệp vụ với thời điểm nhận dữ liệu
D. Thời điểm mở socket với thời điểm đóng kết nối
Đáp án đúng: C

19. Nếu `accountId` và `customerId` đều là UUID, có thể coi là một định danh không?
A. Có, nếu chuỗi UUID đều dùng cùng số lượng ký tự
B. Có, nếu hai giá trị cùng được lưu bằng kiểu string
C. Có, nếu hai field được serialize dưới dạng JSON
D. Không, vì hai UUID có thể trỏ tới hai loại thực thể
Đáp án đúng: D

20. Khi một số liệu có nhiều nguồn, metadata nào giúp hiểu số liệu đáng tin hơn?
A. Ghi nguồn gốc, biến đổi và chủ sở hữu định nghĩa
B. Chỉ cấu hình số thread của job dùng để tổng hợp
C. Chỉ phiên bản IDE người lập trình dùng khi tạo bảng
D. Chỉ tên máy chạy dịch vụ và dung lượng RAM hiện có
Đáp án đúng: A

21. Vì sao cần ghi rõ granularity của trường `quantity` khi trao đổi dữ liệu?
A. Đảm bảo mọi số lượng được làm tròn lên số nguyên
B. Phân biệt số lượng theo dòng hàng hay toàn đơn hàng
C. Đảm bảo mọi trường quantity phải là kiểu số dương
D. Đảm bảo cột được sắp xếp tăng dần trước xuất dữ liệu
Đáp án đúng: B

22. Một trường `deleted=true` có thể mang nhiều nghĩa. Contract cần làm rõ gì?
A. Chỉ kiểu boolean và tên class giữ trường deleted
B. Chỉ thời điểm chạy lệnh xóa index trong database
C. Xóa mềm, xóa vật lý hay chỉ ẩn khỏi nghiệp vụ
D. Chỉ định dạng chữ hoa của tên field trong response
Đáp án đúng: C

23. Nếu vẫn giữ tên và kiểu field nhưng đổi nghĩa nghiệp vụ, rủi ro nào lớn nhất?
A. Consumer tự động phát hiện định nghĩa mới qua tên cột
B. Compiler sẽ báo lỗi kiểu dữ liệu ở mọi chỗ sử dụng
C. Consumer xử lý sai dù schema vẫn kiểm tra hợp lệ
D. Serializer sẽ luôn từ chối trường có nghĩa khác trước
Đáp án đúng: C

24. Để quản trị thay đổi ngữ nghĩa giữa các nhóm, bước nào phù hợp?
A. Chỉ cập nhật comment cục bộ của một phương thức
B. Chỉ đổi tên bảng ở một nơi mà bỏ qua các consumer
C. Chỉ đổi lịch chạy job mà không công bố định nghĩa
D. Review định nghĩa, version contract và test ánh xạ
Đáp án đúng: D
