Ứng dụng thương mại cho phép khách thêm sản phẩm vào giỏ và cập nhật số lượng; khi người dùng chuyển số lượng về 0, dòng sản phẩm vẫn tồn tại và tổng tiền không khớp hành vi xóa đã mô tả.
Màn hình đăng ký tài khoản yêu cầu email duy nhất; người dùng nhập địa chỉ có chữ hoa trong phần domain rồi đăng ký lại bằng chữ thường và hệ thống tạo hai tài khoản dù quy tắc xác định đó là một email.
API tạo đơn hàng chỉ cho phép số lượng sản phẩm từ 1 đến 999; yêu cầu với số lượng 1.000 trả HTTP 201 nhưng cơ sở dữ liệu lại lưu 999, khiến response và kết quả lưu không thống nhất.
Trong quy trình đổi mật khẩu, người dùng nhập sai mật khẩu hiện tại nhưng API vẫn trả thông báo thành công; lần đăng nhập tiếp theo thất bại với cả mật khẩu cũ và mới.
Ứng dụng đặt vé giữ chỗ trong 10 phút trước khi thanh toán; khi người dùng thanh toán đúng lúc phiên giữ chỗ hết hạn, giao diện báo thành công dù ghế đã được cấp cho người khác.
Trang quản lý hồ sơ có nút Lưu sau khi chỉnh sửa số điện thoại; thông báo thành công xuất hiện nhưng tải lại trang vẫn thấy số cũ do yêu cầu lưu đã thất bại ở tầng API.
Một API cập nhật tài nguyên theo phương thức PUT ghi đè toàn bộ cấu hình; request bỏ trường timezone khiến giá trị cũ bị xóa trong khi tài liệu chức năng yêu cầu giữ múi giờ khi người dùng không thay đổi.
Trong ứng dụng chăm sóc khách hàng, tính năng sửa từng trường bằng PATCH không phân biệt khóa bị bỏ qua và khóa được gửi giá trị null; thao tác xóa địa chỉ khẩn cấp không xảy ra dù giao diện báo đã lưu.
Quy trình xóa khách hàng cho phép xác nhận trên hộp thoại; sau khi xác nhận, danh sách đã bỏ người đó nhưng API đọc theo ID vẫn trả hồ sơ đầy đủ dù yêu cầu đặt trạng thái đã xóa.
Một tài khoản bị vô hiệu hóa vẫn có thể truy cập chi tiết đơn hàng bằng đường dẫn bookmark cũ; màn hình điều hướng ẩn menu nhưng chức năng đọc qua API vẫn thực hiện được.
Website bán hàng lọc sản phẩm theo giá từ 200.000 đến 500.000 đồng; các sản phẩm có giá đúng 200.000 bị bỏ khỏi danh sách trong khi các bộ lọc khác hoạt động bình thường.
Trang báo cáo doanh số cho phép chọn ngày bắt đầu và kết thúc bằng nhau để lấy dữ liệu một ngày; bảng kết quả lại rỗng vì bộ lọc chỉ chấp nhận khoảng có hai ngày khác nhau.
Ứng dụng quản lý lịch hẹn hiển thị lịch theo múi giờ người dùng; cuộc hẹn 09:00 tại Hà Nội được hiển thị thành 09:00 ở Paris dù hồ sơ quy định thời điểm tuyệt đối của cuộc hẹn.
Đội sản phẩm áp dụng phí giao hàng cố định cho đơn dưới 300.000 đồng và miễn phí từ ngưỡng đó; giỏ hàng đúng 300.000 vẫn bị tính phí khi hệ thống áp dụng mã giảm giá.
Chức năng hoàn tiền một phần cho phép hoàn tối đa phần tiền còn lại; sau hai lần hoàn, yêu cầu thứ ba bằng toàn bộ giá trị ban đầu vẫn được chấp thuận dù đã vượt số tiền thanh toán.
Trong cổng học tập, học viên phải hoàn tất bài A trước khi mở bài B; API cho phép bắt đầu bài B bằng URL trực tiếp dù giao diện vẫn khóa nút mở bài đúng như thiết kế.
Ứng dụng đặt hàng cho phép hủy khi đang chuẩn bị và từ chối sau khi giao vận chuyển; hai request hủy gửi liên tiếp tạo hai giao dịch hoàn tiền dù đơn chỉ chuyển sang Đã hủy một lần.
Trang quản trị phân trang danh sách 30 khách hàng mỗi trang; khi lọc còn 12 khách hàng trên trang thứ ba, UI hiển thị không có kết quả dù trang đầu chứa dữ liệu phù hợp.
Người dùng nhập từ khóa có dấu tiếng Việt trong chức năng tìm kiếm sản phẩm; kết quả tìm kiếm khác biệt khi chỉ thay chữ hoa, khiến sản phẩm đã được đánh chỉ mục không được tìm thấy.
Một bảng công việc cho phép sắp xếp theo ngày cập nhật mới nhất; khi hai công việc có cùng thời điểm, thứ tự thay đổi giữa các lần tải khiến người dùng thấy mục bị nhảy giữa các trang.
Ứng dụng nhập danh sách học viên từ CSV; một dòng có email không hợp lệ khiến toàn bộ file bị từ chối nhưng giao diện chỉ báo 'Lỗi tải lên' mà không thể hiện số dòng đã được tiếp nhận.
Hệ thống quản lý phòng họp từ chối đặt lịch trùng thời gian; hai phòng khác nhau cùng khung giờ vẫn bị báo xung đột dù quy tắc chỉ giới hạn trùng trong cùng một phòng.
Một trang checkout có thể sử dụng điểm thưởng để giảm tiền; người dùng thay đổi số lượng sản phẩm sau khi áp điểm nhưng tổng thanh toán không được tính lại theo giỏ hàng hiện tại.
Trong ứng dụng ngân hàng, khách nhận OTP có hiệu lực 90 giây; mã được chấp nhận sau mốc 90 giây trên một đường xác minh nhưng bị từ chối trên đường xác minh còn lại.
Người dùng thay đổi email đăng nhập và cần xác nhận địa chỉ mới; hệ thống hiển thị email mới ngay trước xác nhận rồi gửi thông báo bảo mật đến email cũ theo luồng khác.
Một chức năng tải báo cáo PDF cho phép chọn nhiều chi nhánh; dữ liệu trên màn hình đúng theo bộ lọc nhưng file xuất lại chứa toàn bộ chi nhánh của tổ chức.
Ứng dụng thương mại ghi đơn sau khi nhận callback thanh toán; callback tới hai lần do đối tác gửi lại và hệ thống tạo hai đơn từ cùng một giao dịch đã thanh toán.
Trong hệ thống thông báo bất đồng bộ, người dùng đổi ngôn ngữ từ tiếng Việt sang tiếng Anh trước lúc worker gửi email; thư đến vẫn dùng ngôn ngữ không phù hợp với quy tắc áp dụng tại thời điểm gửi.
Ứng dụng theo dõi giao hàng cập nhật trạng thái theo các event từ đối tác; event Delivered tới trước event InTransit bị xử lý lại khiến đơn đã hoàn tất quay về trạng thái đang vận chuyển.
Dịch vụ tạo đơn trả HTTP 202 để xử lý nền; màn hình lập tức hiển thị Đã hoàn tất dù sau đó tác vụ bất đồng bộ thất bại vì sản phẩm hết tồn kho.
Một luồng cấp quyền quản trị gửi sự kiện cập nhật đến các dịch vụ khác; người dùng đã bị thu hồi quyền ở giao diện nhưng vẫn có thể thực hiện hành động trong một service chưa nhận sự kiện.
Trong hệ thống đặt lịch, sự kiện hủy được gửi qua hàng đợi rồi worker gửi thông báo; người dùng đã hủy thành công nhưng vẫn nhận email xác nhận lịch hẹn do thông điệp được xử lý sai thứ tự.
API tìm kiếm phải trả tổng số kết quả và danh sách item trong cùng phạm vi bộ lọc; khi chuyển sang trang thứ hai, totalCount đột ngột đổi từ 95 thành 20 dù bộ lọc không thay đổi.
Ứng dụng bán hàng tính tổng tiền ở backend nhưng frontend lại tự tính theo phép làm tròn khác; màn xác nhận hiển thị một số tiền, còn hóa đơn cuối cùng hiển thị số khác.
Trang đăng ký khóa học cho phép dùng mã giảm giá một lần trên mỗi tài khoản; sau khi gửi form thất bại vì lỗi mạng, mã bị đánh dấu đã dùng dù đơn đăng ký chưa được tạo.
Trong chức năng tạo phiếu hỗ trợ, người dùng chọn mức Khẩn cấp và đính kèm hai file; tải lại chi tiết phiếu thấy đủ file nhưng mức ưu tiên trở về Bình thường.
Một đợt sửa lỗi cho phép quản trị viên khóa nhiều tài khoản cùng lúc; sau khi deploy, chức năng khóa đơn lẻ hoạt động nhưng thao tác mở khóa từng tài khoản trước đây không còn cập nhật đúng trạng thái.
Ứng dụng khách hàng lưu thông tin form trong trình duyệt khi mạng yếu; sau khi khôi phục kết nối và gửi, số điện thoại cũ được ghi đè lên giá trị mới người dùng đã sửa ở phiên khác.
Chức năng đổi địa chỉ giao hàng chỉ hợp lệ trước khi đơn được bàn giao đơn vị vận chuyển; khi người dùng giữ trang chỉnh sửa mở nhiều giờ, thao tác Lưu vẫn chấp nhận dù trạng thái đơn đã đổi.
Một quy trình đặt chỗ gồm chọn ghế, áp voucher, thanh toán và nhận vé; bộ test trước đây chỉ kiểm tra từng màn hình độc lập nên không phát hiện vé cuối được cấp cho ghế khác ghế đã thanh toán.
