Một ứng dụng theo dõi cảm biến lưu mẫu đo mỗi giây vào mảng có kích thước cố định; khi số mẫu vượt dự tính, chương trình phải dừng ghi dù người dùng vẫn cần truy cập nhanh theo thời điểm.
Nhóm xử lý sự kiện dùng mảng động để lưu hàng triệu bản ghi được thêm liên tục; khi tải đột ngột tăng, thời gian chèn có vài đỉnh trễ và bộ nhớ cấp phát tăng, khiến nhóm phải phân tích chi phí mở rộng dung lượng.
Một danh sách xếp hạng hiển thị theo thứ tự ưu tiên và thường xuyên chèn phần tử vào đầu; cấu trúc đang dùng đáp ứng tốt truy cập bằng chỉ số nhưng mỗi lần chèn làm dịch chuyển nhiều phần tử.
Một trình phát nhạc lưu danh sách bài hát bằng danh sách liên kết vì thường đổi vị trí phát, nhưng thao tác nhảy tới bài hát thứ mười nghìn chậm hơn mong đợi; nhóm cần đối chiếu chi phí truy cập và chỉnh sửa.
Hệ thống quản lý phiên làm việc thường xóa một nút đã biết khỏi danh sách liên kết đơn; người phát triển chỉ có tham chiếu đến nút cần xóa và phải đánh giá bất biến liên kết khi nút ở cuối danh sách.
Một giao diện duyệt lịch sử thao tác yêu cầu di chuyển tới trước và sau, xóa phần tử giữa và giữ con trỏ hiện tại ổn định; nhóm cân nhắc danh sách liên kết kép nhưng lo chi phí tham chiếu và cập nhật liên kết.
Một bộ phân tích biểu thức cần xác định dấu ngoặc mở đóng có khớp thứ tự hay không, kể cả khi nhiều loại ngoặc được lồng sâu; hiện tại nhóm chỉ đếm số dấu mở và đóng nên chấp nhận một số biểu thức sai.
Ứng dụng chỉnh sửa văn bản hỗ trợ hoàn tác nhiều bước nhưng nhật ký thao tác tăng đến mức chiếm phần lớn bộ nhớ; nhóm cần xác định dữ liệu nào phải lưu, thứ tự khôi phục và giới hạn lịch sử.
Hệ thống xử lý hóa đơn nhận yêu cầu trước nhưng một worker tự lấy phần tử cuối trong danh sách đang chờ, làm khách hàng đến sau được xử lý trước; nhóm cần làm rõ bất biến thứ tự của hàng đợi.
Một máy chủ nhận hàng chục nghìn thông báo mỗi giây trong khi hệ thống gửi chỉ xử lý được một phần; hàng đợi không giới hạn làm cạn bộ nhớ và nhóm phải cân nhắc dung lượng, chính sách nhận và xử lý tràn.
Ứng dụng giám sát cần giữ cửa sổ một nghìn giá trị mới nhất và loại bỏ giá trị cũ liên tục; cách hiện tại sao chép cả mảng cho mỗi mẫu, gây chi phí lớn trong giờ cao điểm.
Trong hệ thống đặt vé, bảng băm dùng một hàm băm đơn giản trên chuỗi mã đặt chỗ; một nhóm mã có tiền tố giống nhau khiến thời gian tìm kiếm tăng mạnh, yêu cầu xem lại cách phân bố khóa và xử lý va chạm.
Một ứng dụng dùng đối tượng hồ sơ có thể chỉnh sửa làm khóa của bảng băm; sau khi đổi số điện thoại trong hồ sơ, thao tác tìm kiếm bằng cùng đối tượng không thấy bản ghi đã thêm.
Kho dữ liệu trong bộ nhớ tăng từ vài trăm lên hàng triệu mục, khiến một số thao tác thêm vào bảng băm đột nhiên chậm; kỹ sư cần phân tích hệ số tải, tái băm và chi phí bộ nhớ theo thời gian.
Một bộ nhớ đệm chỉ được giữ một nghìn trang truy cập gần đây, nhưng cách hiện tại phải duyệt toàn bộ trang để tìm phần tử ít dùng nhất mỗi khi đầy; nhóm cần cân nhắc phối hợp cấu trúc tra cứu và thứ tự sử dụng.
Hệ thống chống xử lý trùng sự kiện cần biết một mã đã xuất hiện hay chưa, không cần giữ thứ tự nhận; nhóm hiện lưu mọi mã trong danh sách và tìm tuần tự, khiến thời gian tra cứu tăng theo lượng sự kiện.
Nền tảng thương mại điện tử thường tìm các sản phẩm có giá trong một khoảng và lấy theo thứ tự tăng dần; bảng băm đang dùng tra cứu mã sản phẩm nhanh nhưng không hỗ trợ tốt truy vấn phạm vi.
Một cây tìm kiếm nhị phân được xây từ các mã khách hàng đã sắp tăng dần; sau đợt nhập dữ liệu lớn, độ sâu cây tăng bất thường và truy vấn trở nên chậm dù số bản ghi không quá lớn.
Một dịch vụ duy trì chỉ mục cân bằng theo khóa nhưng cập nhật và xóa nhiều nút trong mỗi giao dịch; nhóm cần xác minh các bất biến thứ tự và cân bằng sau những thao tác có thể làm thay đổi cấu trúc cây.
Một hệ thống khuyến nghị cần liên tục chọn công việc có mức ưu tiên cao nhất, nhưng dữ liệu hiện được sắp xếp lại toàn bộ sau mỗi lần thêm; nhóm muốn đánh giá hiệu quả của cấu trúc hỗ trợ truy xuất phần tử ưu tiên.
Một scheduler dùng heap để chọn tác vụ có hạn chót gần nhất, nhưng sau khi thay hạn chót của một tác vụ đã nằm trong heap, thứ tự lấy tác vụ đôi lúc sai; nhóm phải xem xét bất biến heap và cập nhật khóa.
Trong luồng hàng triệu giá trị đo, ứng dụng chỉ cần giữ một trăm giá trị lớn nhất tại mỗi thời điểm; giải pháp hiện tại lưu và sắp xếp toàn bộ dữ liệu khiến bộ nhớ tăng không cần thiết.
Một dịch vụ gợi ý tìm kiếm muốn hiển thị những thuật ngữ bắt đầu bằng tiền tố người dùng nhập, nhưng đang duyệt toàn bộ từ điển cho mỗi ký tự; nhóm cần đánh giá lợi ích và mức tiêu thụ bộ nhớ của chỉ mục theo tiền tố.
Nền tảng cộng đồng thường xuyên gộp hai nhóm người dùng và cần trả lời nhanh liệu hai người cùng nhóm hay không; cách hiện tại duyệt lại mọi quan hệ sau mỗi lần gộp, gây chậm khi số nhóm tăng.
Trong trò chơi bản đồ ô vuông, người chơi cần tìm đường có ít bước di chuyển nhất qua các ô hợp lệ; hệ thống đang thử mọi lộ trình và thường bị giới hạn thời gian khi bản đồ lớn.
Ứng dụng điều hướng lưu đường đi với thời gian di chuyển khác nhau giữa các cạnh; một phiên bản chỉ chọn đường ít chặng nhất khiến người dùng đến đích muộn hơn dù tồn tại tuyến nhanh hơn.
Một nền tảng xây dựng phần mềm phải chạy các công việc theo quan hệ phụ thuộc, nhưng đôi lúc job đóng gói bắt đầu khi thư viện chưa biên dịch; nhóm cần biểu diễn phụ thuộc và xác định thứ tự thực thi hợp lệ.
Đội triển khai bổ sung một phụ thuộc mới giữa các dịch vụ và hệ thống khởi tạo rơi vào vòng chờ; dữ liệu phụ thuộc hiện lưu như danh sách đơn nên khó nhận ra chu trình trước khi phát hành.
Một hệ thống phân tích mạng xã hội có hàng triệu tài khoản nhưng mỗi tài khoản chỉ kết nối với rất ít người; nhóm đang cấp phát ma trận quan hệ lớn và phải cân nhắc biểu diễn đồ thị theo mật độ cạnh.
Một ứng dụng mô hình mạng giao thông có nhiều giao lộ và các đường nối thay đổi thường xuyên; nhóm cần lựa chọn giữa danh sách kề và ma trận kề khi cả truy vấn có cạnh trực tiếp lẫn duyệt láng giềng đều quan trọng.
Một thuật toán duyệt đồ thị đánh dấu đã thăm quá muộn, khiến cùng đỉnh được đưa vào hàng đợi nhiều lần trên mạng có nhiều đường vòng; nhóm cần xác định thời điểm cập nhật trạng thái và bảo toàn tính đúng đắn.
Sau khi thay danh sách liên kết bằng mảng động để tối ưu truy cập, nhóm thấy giảm thời gian xử lý dù số thao tác lý thuyết gần tương đương; họ cần đối chiếu độ phức tạp tiệm cận với vị trí bộ nhớ, chi phí cấp phát và dữ liệu tải thực tế.
