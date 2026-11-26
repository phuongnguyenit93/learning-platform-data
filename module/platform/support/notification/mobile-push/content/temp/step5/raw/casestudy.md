Trong ứng dụng ngân hàng, khách hàng chưa cấp quyền nhận thông báo nhưng backend Java vẫn coi việc gửi yêu cầu tới FCM thành công là bằng chứng người dùng đã nhìn thấy cảnh báo giao dịch.
Ứng dụng mua sắm xin quyền nhận push ngay khi mới mở lần đầu; nhiều người từ chối trước khi hiểu lợi ích và đội sản phẩm không biết cách tiếp cận người dùng đã tắt quyền.
Một nhân viên đổi điện thoại và đăng nhập lại ứng dụng giao hàng; token push cũ vẫn gắn với tài khoản, khiến cảnh báo tiếp tục được gửi tới thiết bị không còn sử dụng.
Trong hệ thống chăm sóc sức khỏe, người dùng đăng xuất khỏi máy tính bảng dùng chung nhưng app vẫn giữ đăng ký thiết bị cho tài khoản trước; thông báo lịch hẹn xuất hiện trên màn hình khóa của người đăng nhập sau.
Ứng dụng bán vé cho phép cùng một tài khoản đăng nhập trên hai điện thoại; backend chỉ lưu một push token mới nhất nên một thiết bị không nhận được thay đổi trạng thái vé.
Đội phát triển lưu token FCM theo userId nhưng không ghi thiết bị hay phiên đăng nhập; sau khi cài lại ứng dụng, nhiều bản ghi token cũ gây tăng lỗi gửi và khó phân biệt token còn hiệu lực.
Ứng dụng iOS đã nhận quyền thông báo nhưng không cập nhật APNs device token về backend khi token thay đổi; lệnh gửi từ service Java thành công ở hệ thống nội bộ nhưng không đến máy mới.
Trong một bản phát hành, app Android gửi token đăng ký của Firebase project thử nghiệm lên backend production; những thông báo đặt hàng thực tế không thể đến đúng dự án cấu hình.
Nhóm tích hợp APNs chỉ thử trên bản build development; khi đưa ứng dụng lên App Store, cấu hình môi trường đích khác khiến nhiều thiết bị production ngừng nhận push.
Đội backend lưu khóa ký hoặc credential gửi push trong file cấu hình được commit; khi repository được chia sẻ rộng hơn, nhóm bảo mật không biết phiên bản ứng dụng nào đang dùng bí mật cũ.
Một ứng dụng nhiều tenant chọn sai bộ credential FCM theo tenantId; token của khách hàng A bị gửi qua cấu hình thuộc ứng dụng B và phát sinh lỗi mà hệ thống không phân loại.
Trong ứng dụng giao hàng, nhân viên đổi vùng phụ trách nhưng nhóm đăng ký topic khu vực cũ chưa được cập nhật; họ tiếp tục nhận cảnh báo đơn hàng ngoài phạm vi làm việc.
Đội sản phẩm gửi push chương trình khuyến mãi đến mọi token mà không kiểm tra người dùng đã chọn nhận thông tin marketing hay chưa; người dùng không muốn quảng cáo vẫn nhận tin ngoài mong đợi.
Ứng dụng quản lý lớp học có nhiều nhóm phụ huynh và giáo viên; một lỗi ánh xạ phân khúc làm thông báo điểm số của học sinh được gửi tới thiết bị của phụ huynh khác.
Trong hệ thống đặt lịch, thông báo nhắc hẹn được lên lịch từ hôm trước; khách đã hủy hoặc đổi giờ nhưng job vẫn gửi lời nhắc với thời điểm cũ.
Một đơn đặt hàng được xác nhận trên ba thiết bị; khi khách mở thông báo ở máy thứ nhất, hai thiết bị khác vẫn giữ nội dung 'Cần xác nhận' khiến khách thực hiện thao tác trùng.
Ứng dụng thương mại tạo payload thông báo chứa đầy đủ địa chỉ và số điện thoại người nhận; iOS hiển thị phần nội dung trên màn hình khóa trong khi điện thoại đang dùng chung.
Đội thiết kế payload FCM chỉ gồm URL tuyệt đối chứa token đăng nhập; khi người dùng nhấn vào thông báo, dữ liệu xác thực có thể xuất hiện trong log hoặc lịch sử chia sẻ liên kết.
Trong ứng dụng nhắn tin, backend gửi nội dung chat trong notification payload dù người nhận đã bật chế độ ẩn bản xem trước; cơ chế xử lý trên app chưa phản ánh tùy chọn quyền riêng tư.
Ứng dụng Android xử lý data message khi đang mở nhưng bỏ qua trường hợp app ở nền bị hệ điều hành giới hạn hoạt động; cùng một sự kiện tạo ra trải nghiệm khác nhau theo trạng thái app.
Ứng dụng iOS mong xử lý tác vụ đồng bộ nặng ngay khi nhận silent push; thiết bị đang ở chế độ tiết kiệm pin không chạy tác vụ và dữ liệu hiển thị trở nên cũ.
Trong hệ thống giao hàng, app hiển thị một thông báo từ hệ thống khi ở nền rồi tự tạo thêm thông báo local cho cùng message; người dùng nhìn thấy hai cảnh báo trùng nội dung.
Người dùng bấm thông báo 'Đơn đã giao' sau khi ứng dụng bị đóng hẳn; màn hình mở ra trang chủ thay vì chi tiết đơn vì dữ liệu điều hướng không được khôi phục trong quá trình khởi động.
Một app bán vé nhận push cho vé đã bị xóa khỏi tài khoản; khi người dùng nhấn vào, màn hình chi tiết yêu cầu đối tượng không còn tồn tại và ứng dụng báo lỗi.
Nhóm phát triển gửi mã ưu đãi có ký tự tiếng Việt và emoji trong payload; một số phiên bản app hiển thị chữ bị cắt vì không kiểm thử nội dung dài và hỗ trợ đa ngôn ngữ.
Trong ứng dụng tin tức, nhiều bản cập nhật cùng chủ đề được phát trong vài phút; thiết bị hiển thị hàng chục thông báo thay vì giữ trạng thái tin mới nhất, gây nhiễu cho người dùng.
Hệ thống cảnh báo chuyến bay gửi thay đổi cửa khởi hành với TTL quá dài; thiết bị offline nhiều giờ nhận thông tin cũ sau khi máy bay đã khởi hành.
Đội đặt TTL cực ngắn cho push nhắc xác nhận thanh toán; khi thiết bị mất mạng trong ít phút, cảnh báo hết hạn trước khi khách có thể nhận được.
Ứng dụng giao dịch gửi thông báo quan trọng cùng mức ưu tiên với tin marketing; trong giờ cao điểm, việc hiển thị và sắp xếp trên thiết bị khiến khách không thấy cảnh báo có thời hạn.
Trong app sức khỏe, người dùng cấu hình không làm phiền ban đêm nhưng backend gửi nhắc nhở không khẩn cấp vào thời điểm đó; tỷ lệ tắt hoàn toàn quyền thông báo tăng cao.
Backend Java phát push ngay sau khi tạo đơn nhưng transaction lưu đơn sau đó bị rollback; thiết bị nhận tin 'Tạo đơn thành công' nhưng không có đơn hàng nào để mở.
Service gửi yêu cầu qua FCM gặp timeout nhưng không biết nhà cung cấp đã nhận hay chưa; cơ chế retry không gắn định danh nghiệp vụ và khách nhận hai thông báo cùng một sự kiện.
Một batch gửi hàng chục nghìn push nhận lỗi giới hạn tốc độ tạm thời; nhóm retry đồng loạt không có giãn cách và tiếp tục làm tăng lỗi từ nhà cung cấp.
Đội gửi lại tất cả token bị lỗi theo cùng một chính sách; token đã hết hiệu lực do gỡ ứng dụng vẫn được đưa vào hàng đợi mỗi ngày và tiêu tốn tài nguyên.
Trong quy trình khôi phục mật khẩu, backend Java gửi thông báo chứa đường dẫn xác nhận có thời hạn; job retry trễ làm người dùng nhận liên kết đã hết hạn và tiếp tục bấm thử.
Ứng dụng hỗ trợ FCM và APNs nhưng mã backend chỉ gom lỗi gửi về chuỗi 'failed'; đội vận hành không phân biệt lỗi credential, token không hợp lệ và sự cố mạng tạm thời.
Một nền tảng di động tính tỷ lệ giao thông báo từ số yêu cầu được FCM/APNs chấp nhận; người quản lý hiểu lầm đây là tỷ lệ thông báo đã hiển thị trên màn hình người dùng.
Trong bản cập nhật Android, ứng dụng bổ sung notification channel mới nhưng người dùng đã tắt channel cũ; nhóm không kiểm tra tác động của cài đặt thông báo trên các phiên bản hệ điều hành.
Đội kiểm thử push chỉ dùng trình giả lập và tài khoản thử nghiệm; khi chạy trên thiết bị thật với app ở nền, bị khóa màn hình hoặc không có mạng, các lỗi xử lý mới xuất hiện.
Hệ thống cảnh báo nhiều ngôn ngữ nhận sự kiện từ dịch vụ đặt đơn; backend gửi chung nội dung tiếng Việt cho cả người dùng chọn tiếng Anh và không có thông tin locale ổn định tại thời điểm gửi.
