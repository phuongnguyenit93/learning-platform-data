Một service tính tiền cần tra tỷ lệ chiết khấu từ repository, nhưng unit test hiện truy cập cơ sở dữ liệu thật và thất bại mỗi khi dữ liệu thử bị sửa; nhóm muốn cô lập phụ thuộc để chỉ đánh giá quy tắc tính tiền.
Đội Java dùng chung từ mock cho mọi đối tượng thử, kể cả bảng giá lưu trong bộ nhớ có hành vi thật và đối tượng chỉ trả dữ liệu cố định; khi một ca kiểm thử cần quan sát lời gọi, cách tổ chức test double hiện tại gây nhầm lẫn.
Một unit test Mockito cấu hình repository trả cùng sản phẩm cho mọi mã, nên service lấy nhầm mã hàng nhưng kết quả kiểm thử vẫn đúng; nhóm cần đánh giá cách stubbing phản ánh đầu vào và phát hiện lựa chọn sai.
Hàm đăng ký tài khoản phải kiểm tra trùng email trước khi lưu người dùng, nhưng mock repository luôn báo không tồn tại; suite hiện không kiểm tra trường hợp email đã được sử dụng và hành vi ngừng ghi.
Một service định tuyến yêu cầu đến hai nhà cung cấp tùy khu vực; bài test chỉ xác nhận kết quả đầu ra mà không nhận ra lời gọi đã gửi tới nhà cung cấp sai vùng với chi phí khác biệt.
Trong Mockito, nhóm dùng matcher chấp nhận mọi chuỗi cho mã khách hàng và bỏ qua giá trị quan trọng; một lần refactor truyền mã rỗng vào repository vẫn khiến bài kiểm thử xanh.
Một lời gọi repository có ba tham số gồm mã đơn, trạng thái và thời điểm; nhóm trộn giá trị cụ thể với argument matcher không nhất quán, khiến bài kiểm thử không chạy tới bước xác minh nghiệp vụ.
Ứng dụng lưu đối tượng yêu cầu với nhiều trường tùy chọn, nhưng lớp test xác nhận đối tượng truyền cho gateway bằng tham chiếu của một instance khác; hành vi đúng bị báo sai vì cách so sánh tham số không phản ánh nội dung cần kiểm tra.
Một service tạo yêu cầu gửi email gồm người nhận, mẫu thư và mã đơn, nhưng unit test chỉ verify phương thức gửi được gọi một lần; hệ thống có thể gửi thư tới địa chỉ sai mà test không phát hiện.
Lớp xử lý đơn xây yêu cầu gửi thông báo rồi chuyển cho adapter; nhóm muốn dùng ArgumentCaptor để kiểm tra các trường quan trọng, nhưng đối tượng yêu cầu có thể tiếp tục bị chỉnh sửa sau khi gửi.
Một service gửi ba thông điệp đến broker trong thứ tự có ý nghĩa nghiệp vụ; bài kiểm thử hiện chỉ đếm số lần gọi và không nhận ra thông điệp hủy được gửi trước thông điệp tạo đơn.
Nhóm xác minh mọi lời gọi repository và logger theo thứ tự tuyệt đối; khi bổ sung bước đọc cache để tối ưu, hàng chục bài test hỏng dù hợp đồng công khai và tác động nghiệp vụ không thay đổi.
Chức năng từ chối thanh toán phải không gọi cổng thu tiền khi dữ liệu không hợp lệ; các bài unit test hiện chỉ xác nhận mã lỗi trả về và chưa quan sát được tác dụng phụ cần ngăn chặn.
Một service thử lại sau lỗi tạm thời; mock gateway luôn ném cùng ngoại lệ nên đội không kiểm tra được trường hợp lần gọi thứ hai thành công và số lần gọi đúng theo chính sách.
Một lệnh gửi dữ liệu là phương thức không trả giá trị, nhưng test cần mô phỏng lỗi truyền mạng; nhóm mới dùng Mockito và chưa rõ cách tạo hành vi lỗi phù hợp cho lời gọi kiểu này.
Khi gateway ném ngoại lệ xác thực thay vì ngoại lệ mạng, service vẫn thử lại ba lần; unit test cấu hình mock chỉ cho trường hợp lỗi chung nên bỏ sót việc phân loại lỗi không thể phục hồi.
Một phương thức mock trả giá trị mặc định rỗng khi chưa được stub, khiến service rẽ vào nhánh hết hàng thay vì nhánh có hàng; nhóm hiểu nhầm rằng Mockito đã kiểm thử trường hợp thiếu dữ liệu thực tế.
Lớp xử lý giá được tiêm hai repository cùng một interface nhưng thuộc hai nguồn khác nhau; cấu hình Mockito trong test tiêm nhầm phụ thuộc khiến kiểm thử phản ánh luồng dữ liệu không giống lúc chạy thật.
Một bài JUnit Jupiter dùng mock chung rồi chỉnh stub qua nhiều ca kiểm thử; khi chạy toàn lớp theo thứ tự khác, các ca nhận hành vi từ thiết lập trước và thất bại không ổn định.
Đội bật strict stubbing và thấy cảnh báo về các stub không được sử dụng từ fixture chung; thay vì phân tích thiết lập thừa, nhóm cân nhắc tắt kiểm tra nghiêm ngặt cho toàn dự án.
Một lập trình viên gọi reset trên mock sau mỗi bước hành vi để tái sử dụng một test dài; kiểm tra cuối không còn nhận được lịch sử những tương tác cần thiết để xác nhận quy tắc nghiệp vụ.
Một bài kiểm thử dùng spy trên đối tượng có phương thức gọi HTTP thật; trong lúc thiết lập giá trị trả về, phương thức thật đã chạy và gửi yêu cầu ngoài ý muốn tới môi trường thử.
Nhóm muốn kiểm tra phương thức hỗ trợ riêng bên trong một service bằng cách spy và ghi đè phần lớn logic thật; sau refactor thay cấu trúc nội bộ, các bài test vỡ dù hành vi bên ngoài vẫn đúng.
Một lớp tiện ích dùng phương thức tĩnh đọc thời gian hiện tại nên kết quả test thay đổi theo đồng hồ; nhóm cân nhắc mock phương thức tĩnh hay thay đổi thiết kế để dễ kiểm thử mà không ràng buộc vào chi tiết cài đặt.
Một adapter tạo client bên ngoài ngay trong constructor khiến Mockito không thể thay phụ thuộc bằng test double đơn giản; đội cần đánh giá thiết kế phụ thuộc và mức độ kiểm thử có thể thực hiện độc lập.
Một service xử lý đơn nhận callback từ adapter giao vận; mock chỉ xác nhận việc đăng ký callback nên bài test không phát hiện lỗi khi callback báo thất bại được xử lý như thành công.
Một chức năng trả CompletableFuture từ gateway, nhưng test chỉ stub future đã hoàn tất thành công; nhánh timeout và lỗi bất đồng bộ trong service chưa từng được kiểm chứng.
Một test dùng verify số lần gọi chính xác với logger và truy vấn cache trong một thuật toán có thể xử lý theo batch; thay đổi cách gom dữ liệu làm test đỏ dù tổng kết quả và tác dụng phụ vẫn chính xác.
Một bộ fake repository lưu dữ liệu trong Map được dùng cho unit test, nhưng không mô phỏng ràng buộc duy nhất và transaction của database thật; đội tranh luận nơi nên kiểm tra những hành vi thuộc hạ tầng.
Một mock client ngoài trả DTO do test tự dựng nhưng cấu trúc DTO không phản ánh schema mới của nhà cung cấp; unit test xanh trong khi API tích hợp thật gặp lỗi đọc trường bắt buộc.
Một bài kiểm thử xác minh service gửi thông báo đúng một lần, nhưng nhiều worker thực thi bất đồng bộ và lời gọi đôi lúc chưa diễn ra ở thời điểm verify; người viết tăng sleep khiến bộ test chậm và vẫn thất bại ngẫu nhiên.
Sau nhiều sprint, số unit test dùng Mockito tăng nhanh nhưng thay đổi tên phương thức repository làm hàng loạt ca hỏng, trong khi lỗi tính phí sản xuất không bị phát hiện; nhóm cần đánh giá mức cô lập, cách đặt assertion và phụ thuộc vào chi tiết triển khai.
