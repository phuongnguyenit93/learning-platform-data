Câu 1. Trong consumer-driven contract testing, consumer đóng góp thông tin quan trọng nào?
A. Toàn bộ bảng dữ liệu nội bộ của provider
B. Các tương tác và kỳ vọng mà consumer sử dụng
C. Mã nguồn triển khai từng lớp của provider
D. Danh sách cấu hình CPU của môi trường chạy
Đáp án đúng: B

Câu 2. Kiểm thử hợp đồng khác kiểm thử đầu cuối ở trọng tâm nào?
A. Bắt buộc chạy giao diện và database thật cùng lúc
B. Luôn phát hiện mọi lỗi điều phối giữa nhiều dịch vụ
C. Chỉ đánh giá tốc độ xử lý trong môi trường thật
D. Xác minh ranh giới giao tiếp và kỳ vọng hai bên
Đáp án đúng: D

Câu 3. Khi provider đổi cách triển khai nội bộ mà giữ nguyên hành vi API, kết quả contract test hợp lý là gì?
A. Luôn thất bại vì cấu trúc lớp Java đã thay đổi
B. Luôn thất bại vì truy vấn SQL không còn giống cũ
C. Vẫn đạt nếu các tương tác cam kết được đáp ứng
D. Chỉ đạt khi provider giữ nguyên toàn bộ mã nguồn
Đáp án đúng: C

Câu 4. Consumer cần header X-Tenant-ID để gửi request; điều gì nên nằm trong hợp đồng của tương tác đó?
A. Chỉ thời gian chạy trung bình của toàn hệ thống
B. Header bắt buộc, giá trị hợp lệ và phản hồi tương ứng
C. Mọi biến môi trường bí mật của hệ thống provider
D. Chỉ sơ đồ database độc lập với giao thức HTTP
Đáp án đúng: B

Câu 5. Provider thêm thuộc tính response tùy chọn; khi nào thay đổi này thường ít phá vỡ client cũ?
A. Consumer chấp nhận trường lạ theo kỳ vọng hiện có
B. Consumer yêu cầu response chỉ có đúng tập trường cũ
C. Provider thay luôn tên trường id bắt buộc trước đó
D. Provider trả thêm thuộc tính bằng kiểu dữ liệu khác
Đáp án đúng: A

Câu 6. Provider xóa trường response mà consumer đã khai báo là bắt buộc; hậu quả thường là gì?
A. Consumer tự suy ra trường mới từ header bất kỳ
B. Hợp đồng không đổi vì JSON vẫn có cú pháp hợp lệ
C. Không có tác động nếu provider vẫn trả HTTP 200
D. Provider verification thất bại vì thiếu trường cam kết
Đáp án đúng: D

Câu 7. Trong JSON contract, vì sao không nên buộc provider trả chính xác mọi field không liên quan?
A. Ràng buộc thừa có thể cản thay đổi tương thích
B. Kiểm thử hợp đồng không được kiểm tra kiểu dữ liệu
C. Bất kỳ response nào cũng phải được coi là hợp lệ
D. JSON bắt buộc mọi trường đều xuất hiện theo thứ tự
Đáp án đúng: A

Câu 8. Provider thêm tham số request bắt buộc không có giá trị mặc định; vì sao đây là thay đổi đáng ngại?
A. Consumer cũ sẽ tự động thêm tham số thiếu vào body
B. Provider sẽ luôn bỏ qua tham số trong mọi request
C. Request từ consumer cũ có thể bị từ chối
D. Header HTTP tự ánh xạ tham số từ dữ liệu trước đó
Đáp án đúng: C

Câu 9. Provider thêm một giá trị enum mới trong response; tình huống nào cho thấy rủi ro tương thích?
A. Client đọc enum dưới dạng chuỗi và có nhánh fallback
B. Provider vẫn dùng đúng tên field đang cam kết
C. Các giá trị enum cũ vẫn tiếp tục xuất hiện trong dữ liệu
D. Client xử lý enum theo danh sách đóng không có fallback
Đáp án đúng: D

Câu 10. Khi trường amount đổi từ number sang string, vấn đề chính đối với consumer là gì?
A. Trình duyệt sẽ luôn tự chuyển chuỗi thành số an toàn
B. Vi phạm kiểu dữ liệu mà consumer đang chờ
C. Thay đổi chỉ ảnh hưởng độ nén của JSON trả về
D. API có thể giữ hợp đồng nếu status code vẫn như cũ
Đáp án đúng: B

Câu 11. Trong API partial update, vì sao cần phân biệt field vắng mặt với field null?
A. Vì null luôn có nghĩa là không thay đổi giá trị
B. Vì field vắng mặt luôn tương đương chuỗi rỗng
C. Vì có thể tương ứng không sửa và xóa giá trị
D. Vì JSON không hỗ trợ property có giá trị null
Đáp án đúng: C

Câu 12. Consumer xử lý 404 cho trường hợp không tìm thấy; provider đổi sang 200 với body rỗng. Cần làm gì?
A. Chỉ kiểm tra body có được parse thành JSON hay không
B. Xác minh lại kỳ vọng status và cách consumer phản ứng
C. Coi 200 luôn tương thích vì là trạng thái thành công
D. Bỏ kiểm tra mã trạng thái khỏi mọi hợp đồng sau này
Đáp án đúng: B

Câu 13. Với hợp đồng sự kiện OrderCreated, thành phần nào quan trọng ngoài payload?
A. Tên chủ đề hoặc routing key và quy tắc phiên bản
B. Chi tiết implementation private của service phát sự kiện
C. Tên biến local được dùng khi phát ra mỗi sự kiện
D. Số lượng worker đang chạy trong cluster tại thời điểm đó
Đáp án đúng: A

Câu 14. Contract test cho thông điệp bất đồng bộ thường không chứng minh điều gì?
A. Tên loại sự kiện khớp kỳ vọng consumer
B. Dạng payload có những trường cần thiết
C. Phiên bản schema hợp lệ với consumer đã biết
D. Thời điểm giao hàng chính xác của mọi sự kiện
Đáp án đúng: D

Câu 15. Provider state trong consumer-driven contract giúp việc gì khi chạy verification?
A. Dựng điều kiện dữ liệu cần để phản hồi theo hợp đồng
B. Buộc consumer trực tiếp ghi vào database production
C. Đo throughput của provider dưới tải hàng nghìn request
D. Tự động triển khai provider đến mọi cluster đang chạy
Đáp án đúng: A

Câu 16. Vì sao test chỉ dùng mock tự viết ở phía consumer có thể bỏ sót lỗi hợp đồng?
A. Mock luôn thực thi toàn bộ hệ thống provider thực
B. Mock luôn truy xuất database thật của bên cung cấp
C. Mock có thể lệch provider nếu không được xác minh
D. Mock bắt buộc phải chạy trên cùng host với provider
Đáp án đúng: C

Câu 17. Tại sao cần gắn version và thông tin consumer/provider vào bản hợp đồng đã phát hành?
A. Để provider có thể bỏ qua mọi schema đã cam kết
B. Để người dùng không thể gọi endpoint phiên bản cũ
C. Để đối chiếu bản dựng nào tương thích trước deploy
D. Để tránh mọi cập nhật dependency ở phía consumer
Đáp án đúng: C

Câu 18. Quy trình phát hành provider có nhiều consumer; release gate nào có giá trị nhất?
A. Chỉ cho deploy khi đã xác minh hợp đồng liên quan
B. Chỉ cho deploy khi số dòng code không tăng quá nhiều
C. Chỉ cho deploy khi một consumer nội bộ chạy qua UI
D. Chỉ cho deploy khi response time nhỏ hơn một giây
Đáp án đúng: A

Câu 19. Consumer mới được triển khai trước provider mới; biện pháp nào giảm nguy cơ lỗi tích hợp?
A. Tắt toàn bộ xác minh compatibility cho consumer mới
B. Bắt consumer mới chỉ dùng field chưa tồn tại ở provider
C. Giả định provider mới đã hoạt động trên production
D. Kiểm tra consumer mới với provider đang được triển khai
Đáp án đúng: D

Câu 20. Khi schema registry áp dụng chính sách backward compatibility, kiểm tra nào là trọng tâm?
A. Reader dùng schema mới đọc được dữ liệu writer cũ
B. Writer cũ tự động sinh đúng toàn bộ trường schema mới
C. Provider có thể đổi ý nghĩa bất kỳ trường cũ đang dùng
D. Consumer mới bắt buộc nhận dữ liệu của phiên bản tương lai
Đáp án đúng: A

Câu 21. Trường schema được đổi từ optional sang required; rủi ro nào cần được kiểm tra?
A. Message cũ luôn có trường đó vì schema mới khai báo
B. Dữ liệu cũ có thể thiếu trường mà reader mới yêu cầu
C. Mọi reader tự tạo trường mới bằng giá trị ngẫu nhiên
D. Writer cũ bắt buộc lỗi khi đổi một trường khác bất kỳ
Đáp án đúng: B

Câu 22. Một provider phục vụ ba consumer với các trường response khác nhau; bộ hợp đồng nên bao phủ gì?
A. Chỉ toàn bộ các cột nội bộ của database provider
B. Chỉ hành vi của consumer dùng nhiều endpoint nhất
C. Các kỳ vọng thực tế mà từng consumer đang phụ thuộc
D. Mọi tham số cấu hình triển khai của từng máy chủ
Đáp án đúng: C

Câu 23. Cần bỏ một trường API cũ đã được nhiều consumer dùng; chiến lược nào giảm break change?
A. Xóa ngay rồi yêu cầu consumer tự phát hiện lỗi mới
B. Chỉ đổi tên trường trong tài liệu và không kiểm thử
C. Đổi kiểu dữ liệu trước rồi xóa field ở cùng một lần
D. Đánh dấu deprecated, di chuyển consumer rồi mới bỏ
Đáp án đúng: D

Câu 24. Một hợp đồng API đạt verification; điều gì vẫn cần được kiểm thử riêng?
A. Chỉ số lần chạy của các script tạo hợp đồng
B. Hành vi nghiệp vụ đầu cuối và tương tác thực tế
C. Mọi tên lớp nội bộ không nằm trong contract
D. Cách thụt đầu dòng của source code provider
Đáp án đúng: B
