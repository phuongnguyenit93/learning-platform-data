Câu 1: Người dùng vừa cài ứng dụng nhưng chưa cấp quyền hiển thị thông báo; backend Java nên hiểu điều gì?
A. Gửi thành công không chứng minh thông báo đã hiện
B. Có registration token nghĩa là người dùng đã bật banner
C. FCM sẽ tự bật quyền thông báo ngay khi gửi payload
D. Quyền thông báo được cấp tự động khi đăng nhập app
Đáp án đúng: A

Câu 2: Khi gửi thông báo tới một thiết bị qua FCM, định danh nào thường dùng làm đích nhận cụ thể?
A. Mã phiên đăng nhập HTTP do dịch vụ Java phát hành
B. Địa chỉ IP của thiết bị trong lần kết nối gần nhất
C. Tên tài khoản đăng nhập được lưu trong Firebase
D. Registration token gắn với bản cài ứng dụng trên máy
Đáp án đúng: D

Câu 3: Ứng dụng iOS cần nhận push từ APNs; điều gì đúng về token thiết bị mà backend lưu?
A. Token theo ứng dụng, môi trường và có thể được cấp lại
B. Token luôn giống nhau cho mọi ứng dụng của một máy
C. Token không thay đổi sau khi người dùng cài lại ứng dụng
D. Token được tạo cố định từ tài khoản đăng nhập iCloud
Đáp án đúng: A

Câu 4: Ứng dụng iOS dùng FCM ở backend nhưng không nhận thông báo Apple; phần tích hợp nào cần kiểm tra?
A. Cấu hình Google Play Services trên máy chủ Java gửi
B. Cấu hình notification channel của bản Android cũ
C. Cấu hình kết nối FCM đến APNs cho ứng dụng iOS
D. Cấu hình endpoint đăng nhập API của ứng dụng web
Đáp án đúng: C

Câu 5: Khi backend gửi trực tiếp tới APNs, thông tin xác thực phía máy chủ cần được quản lý ra sao?
A. Quản lý an toàn khóa hoặc chứng chỉ APNs ở server
B. Đính khóa xác thực vào payload để client kiểm tra
C. Đặt khóa riêng trong bản build iOS của ứng dụng
D. Ghi thông tin xác thực vào log cho từng request
Đáp án đúng: A

Câu 6: Payload push chỉ chứa dữ liệu để ứng dụng xử lý; nhận định nào đúng khi app ở nền?
A. Data message luôn đánh thức ứng dụng ngay khi đến
B. FCM sẽ luôn hiện banner từ các trường dữ liệu tùy ý
C. App sẽ tự mở foreground khi nhận bản tin dữ liệu
D. Tác vụ có thể bị OS trì hoãn theo trạng thái app
Đáp án đúng: D

Câu 7: Trên Android, muốn phân nhóm cách hiển thị và để người dùng điều chỉnh thông báo; thành phần nào cần chú ý?
A. FCM topic dùng để thiết lập quyền thông báo của OS
B. Notification channel do ứng dụng Android đăng ký
C. APNs device token lưu ở phần cấu hình Android
D. Quy tắc retry của backend khi đăng ký người dùng
Đáp án đúng: B

Câu 8: Người dùng iOS tắt quyền hiển thị thông báo trong cài đặt; backend có thể kết luận điều gì?
A. APNs tự bật lại quyền khi có registration token mới
B. FCM tự đổi quyền hiển thị cho từng message được gửi
C. Mức ưu tiên cao luôn vượt quyền thông báo của thiết bị
D. Có thể nhận thông điệp nhưng không hiển thị banner
Đáp án đúng: D

Câu 9: FCM registration token thay đổi trong lúc người dùng vẫn đăng nhập; backend nên xử lý thế nào?
A. Giữ token cũ vì Firebase luôn chuyển tiếp tới token mới
B. Đăng ký lại topic cho toàn bộ thiết bị trong hệ thống
C. Tạo một user mới tương ứng với mỗi token được cấp
D. Thay ánh xạ token cũ bằng token mới cho thiết bị
Đáp án đúng: D

Câu 10: FCM báo token của một thiết bị không còn hợp lệ; hành động dữ liệu nào phù hợp nhất?
A. Thử gửi liên tục vào token lỗi với thời gian chờ ngắn
B. Chuyển token lỗi sang user khác có cùng loại điện thoại
C. Loại bỏ token lỗi và cập nhật đăng ký của thiết bị
D. Đổi mức ưu tiên trong payload để khôi phục token
Đáp án đúng: C

Câu 11: Nhân viên đăng xuất điện thoại nhưng vẫn nhận push chứa dữ liệu công ty; cần ưu tiên điều gì?
A. Đổi tên title để nhân viên không nhìn ra dữ liệu
B. Tăng TTL cho các cảnh báo còn trong hàng đợi gửi
C. Chuyển mọi tin có dữ liệu riêng sang một topic chung
D. Gỡ liên kết token khỏi người dùng đã đăng xuất
Đáp án đúng: D

Câu 12: Ứng dụng gửi bản tin cá nhân hóa qua FCM topic có nhiều thiết bị; rủi ro chính nào xuất hiện?
A. FCM chỉ gửi tới userId mà backend ghi trong payload
B. Tin cá nhân có thể tới cả người không thuộc đích
C. Topic sẽ tự phân quyền theo từng hồ sơ người dùng
D. APNs sẽ lọc dữ liệu theo vai trò của từng tài khoản
Đáp án đúng: B

Câu 13: Một người đăng nhập cùng lúc trên điện thoại và máy tính bảng; cách quản lý đích gửi nào phù hợp?
A. Một tài khoản chỉ được giữ token của máy mới nhất
B. Một topic chung dùng thay cho mọi registration token
C. Một tài khoản có thể gắn nhiều token thiết bị
D. Một địa chỉ IP là định danh của mọi máy cùng tài khoản
Đáp án đúng: C

Câu 14: Người dùng chạm thông báo khi app chưa chạy nhưng không mở đúng màn hình đơn hàng; cần xem xét gì?
A. Client cần xử lý dữ liệu điều hướng khi khởi chạy
B. Backend cần tăng số worker gửi message vào FCM
C. Thiết bị cần chuyển sang token của môi trường staging
D. Backend cần đổi khóa APNs sau mỗi lần gửi thông báo
Đáp án đúng: A

Câu 15: Push dữ liệu không được xử lý ngay khi máy ở chế độ tiết kiệm pin; nhận định nào đúng?
A. Mọi data push đều bắt buộc xử lý tức thì khi máy khóa
B. FCM phải mở app ở foreground để hoàn tất mỗi message
C. APNs không bao giờ chịu ảnh hưởng bởi chế độ nguồn
D. OS có thể hạn chế xử lý thông điệp trong nền
Đáp án đúng: D

Câu 16: Cùng hệ thống gửi bản tin định kỳ và cảnh báo bảo mật; cách chọn mức ưu tiên nào phù hợp?
A. Dùng high priority cho tất cả tin để tăng độ tin cậy
B. Chọn ưu tiên dựa trên độ khẩn cấp thực tế
C. Dùng mức thấp cho mọi tin để tránh lỗi rate limit
D. Đổi mức ưu tiên theo độ dài title của mỗi thông báo
Đáp án đúng: B

Câu 17: Một thông báo giảm giá đến sau lúc ưu đãi hết hạn; thuộc tính nào có thể hạn chế tin lỗi thời?
A. Title chứa ngày khuyến mãi theo múi giờ của điện thoại
B. TTL giới hạn thời gian thông điệp còn hữu ích
C. Token được cấp cho phiên cài đặt ứng dụng hiện tại
D. Mã thiết bị được đặt trong khóa phân nhóm thông điệp
Đáp án đúng: B

Câu 18: Giá vé thay đổi nhiều lần trước khi khách mở app; cách nào giúp giảm loạt thông báo trạng thái cũ?
A. Tăng thời gian lưu của mọi message để giữ đầy đủ lịch sử
B. Tạo token thiết bị mới cho từng lần giá vé thay đổi
C. Gửi mỗi bản cập nhật với mức ưu tiên khẩn cấp cao
D. Gộp các bản cập nhật có thể thay thế nhau
Đáp án đúng: D

Câu 19: Backend timeout khi gửi FCM và không biết lần đầu đã thành công chưa; retry có nguy cơ nào?
A. FCM luôn hủy request đầu ngay khi client mất kết nối
B. Thiết bị chỉ hiển thị message của lần gửi cuối cùng
C. Một sự kiện có thể đến nhiều lần vì retry
D. APNs tự đánh dấu mọi message retry là đã bị thu hồi
Đáp án đúng: C

Câu 20: FCM chấp nhận yêu cầu gửi tới token; kết luận nào đúng về việc người dùng đã xem tin?
A. Đã chắc chắn hiện banner dù thiết bị đang ngoại tuyến
B. Đã bảo đảm người dùng chạm và đọc toàn bộ nội dung
C. Chưa chứng minh người dùng nhìn thấy thông báo
D. Đã xác nhận mọi trường payload đều được app xử lý
Đáp án đúng: C

Câu 21: APNs báo token không còn đăng ký hợp lệ; backend nên xử lý danh sách đích thế nào?
A. Loại bỏ token không hợp lệ khỏi danh sách gửi
B. Tăng số lần gửi tới token lỗi để khôi phục thiết bị
C. Giữ token lỗi nhưng chuyển sang topic có nhiều người
D. Đổi userId của tài khoản mà không thay token đích
Đáp án đúng: A

Câu 22: FCM hoặc APNs tạm hạn chế lưu lượng gửi; chiến lược retry nào phù hợp nhất?
A. Gửi lặp liên tục bằng nhiều kết nối để giảm chờ đợi
B. Tạo thêm registration token để vượt hạn mức server
C. Điều tiết tốc độ và retry có khoảng lùi
D. Đổi nội dung push nhưng giữ nguyên tốc độ gửi cũ
Đáp án đúng: C

Câu 23: Khi nhà cung cấp báo rate limit trong đợt gửi hàng loạt, dữ liệu nào cần xét khi gửi lại?
A. Số lần người dùng mở ứng dụng trong tuần gần nhất
B. Tín hiệu thời gian chờ kết hợp chính sách backoff
C. Phần trăm dung lượng pin của thiết bị lúc đăng ký
D. Mã phân nhóm giao diện do client tự đặt cho title
Đáp án đúng: B

Câu 24: Backend Java gửi push bằng khóa xác thực nhà cung cấp; cách quản lý nào phù hợp?
A. Đóng gói khóa server trong ứng dụng mobile phát hành
B. Giữ khóa ở backend và giới hạn quyền truy cập
C. Gắn khóa vào deep link để client tự xác minh khi mở
D. Ghi khóa vào log HTTP đầy đủ cho mọi lần gửi lỗi
Đáp án đúng: B

Câu 25: APNs sandbox hoạt động nhưng ứng dụng iOS production không nhận push; cần kiểm tra giả định nào?
A. Phân biệt môi trường token và cấu hình APNs
B. Token sandbox có thể dùng cho production nếu cùng máy
C. Tên bundle trên iOS không ảnh hưởng cấu hình gửi push
D. Máy Java cần chạy iOS mới gọi được APNs production
Đáp án đúng: A

Câu 26: Sau khi gỡ rồi cài lại app, backend vẫn gửi vào token lưu từ lần cài cũ; cần kiểm tra gì?
A. Đăng ký lại token cho lần cài đặt hiện tại
B. Token luôn bất biến theo số điện thoại của người dùng
C. FCM tự nối token cũ với bản cài mới mà không đăng ký
D. APNs giữ vĩnh viễn mọi token ngay cả khi xóa app
Đáp án đúng: A

Câu 27: Khi người dùng không muốn nhận tin marketing, backend nên quản lý khác biệt gì?
A. Vô hiệu hóa mọi cảnh báo giao dịch dù chưa được yêu cầu
B. Quản lý quyền nhận theo chủ đề và thiết bị
C. Chuyển mọi registration token sang một kênh công khai
D. Cho phép tiếp tục gửi marketing vì OS đã cấp quyền
Đáp án đúng: B

Câu 28: Ứng dụng gửi thông báo có hình ảnh nhưng chỉ một số hệ điều hành hiển thị đúng; cần đánh giá gì?
A. Đưa toàn bộ ảnh nhị phân trực tiếp vào phần title
B. Đổi token người dùng để thiết bị nhận diện tệp ảnh
C. Giữ nguyên cấu trúc push cho mọi nền tảng không kiểm tra
D. Kiểm tra hỗ trợ media và xử lý payload ở app
Đáp án đúng: D

Câu 29: Payload push chứa toàn bộ hóa đơn khiến yêu cầu vượt giới hạn; thay đổi nào phù hợp?
A. Giữ payload tối thiểu và tải dữ liệu khi cần
B. Đặt nội dung hóa đơn đầy đủ vào trường title dài hơn
C. Gửi hóa đơn qua topic thay vì dùng device token trực tiếp
D. Giữ nguyên payload rồi tăng ưu tiên của thông báo
Đáp án đúng: A

Câu 30: Deep link từ push mở sai tài khoản khi người dùng chuyển hồ sơ đăng nhập; cần kiểm tra điều gì?
A. Tin vào mọi liên kết vì FCM đã xác minh thiết bị
B. Bỏ qua đăng nhập vì notification token còn hiệu lực
C. Xác thực deep link với tài khoản hiện tại
D. Dựa vào tên màn hình thay cho kiểm tra quyền tài khoản
Đáp án đúng: C

Câu 31: Đội chỉ đo số request FCM được chấp nhận, trong khi khách báo không thấy push; cần bổ sung gì?
A. Chỉ thống kê dung lượng hình ảnh của payload theo ngày
B. Chỉ xem phiên bản JDK trên máy chủ của service gửi
C. Ghi kết quả gửi, trạng thái thiết bị và tương tác
D. Chỉ đếm số template thông báo từng được phát hành
Đáp án đúng: C

Câu 32: Ứng dụng nhắc lịch quan trọng phải hoạt động khi thiết bị ngoại tuyến hoặc push gián đoạn; điều gì phù hợp?
A. Coi mọi push đã chấp nhận là người dùng đã đọc ngay
B. Xét giới hạn giao nhận và phương án dự phòng
C. Gửi tin vô hạn để chắc chắn điện thoại luôn nhận được
D. Dùng registration token làm bằng chứng có thể liên lạc
Đáp án đúng: B
