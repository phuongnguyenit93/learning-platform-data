Bạn sẽ mô tả đường đi của một thông báo đẩy từ backend Java đến ứng dụng di động thông qua FCM hoặc APNs như thế nào?
Bạn sẽ phân biệt vai trò của Firebase Cloud Messaging và Apple Push Notification service khi phục vụ Android và iOS ra sao?
Bạn sẽ lựa chọn tích hợp FCM, APNs trực tiếp hoặc kết hợp hai cách dựa trên kiến trúc ứng dụng như thế nào?
Bạn sẽ thiết kế bước xin quyền nhận thông báo để người dùng hiểu lợi ích trước khi hệ điều hành hiển thị hộp thoại như thế nào?
Bạn sẽ phân biệt trạng thái người dùng đã từ chối quyền với trạng thái thiết bị chưa đăng ký nhận push trong hệ thống ra sao?
Bạn sẽ xác định hành vi của ứng dụng khi quyền thông báo bị thay đổi trong phần cài đặt thiết bị như thế nào?
Bạn sẽ tổ chức đăng ký token thiết bị với backend theo tài khoản người dùng và ứng dụng như thế nào?
Bạn sẽ phân biệt registration token của FCM với token thiết bị của APNs và tránh dùng nhầm khi định tuyến ra sao?
Bạn sẽ xử lý sự kiện token được làm mới để không tiếp tục gửi tới định danh thiết bị cũ như thế nào?
Bạn sẽ quản lý trường hợp một người dùng đăng nhập đồng thời trên nhiều thiết bị và chỉ một số thiết bị cho phép thông báo ra sao?
Bạn sẽ hủy liên kết token khỏi tài khoản khi người dùng đăng xuất hoặc chuyển tài khoản trên cùng thiết bị như thế nào?
Bạn sẽ kiểm soát trường hợp hai người dùng từng đăng nhập trên một điện thoại để thông báo riêng tư không gửi sai người ra sao?
Bạn sẽ xác định cơ chế dọn dẹp token không còn hợp lệ dựa trên phản hồi gửi và hoạt động gần nhất như thế nào?
Bạn sẽ thiết kế mô hình dữ liệu đăng ký thiết bị gồm nền tảng, phiên bản ứng dụng và tùy chọn nhận thông báo ra sao?
Bạn sẽ phân biệt thông báo hiển thị và thông điệp chứa dữ liệu để ứng dụng tự xử lý theo trạng thái hoạt động như thế nào?
Bạn sẽ lựa chọn payload notification hoặc data cho một yêu cầu mở màn hình cụ thể mà vẫn bảo vệ thông tin nhạy cảm ra sao?
Bạn sẽ xác định những trường dữ liệu nên nằm trong payload và những dữ liệu cần được tải lại sau khi người dùng mở ứng dụng như thế nào?
Bạn sẽ xử lý giới hạn kích thước payload để thông báo vẫn truyền được dù dữ liệu nghiệp vụ rất lớn ra sao?
Bạn sẽ thiết kế nội dung thông báo có tiêu đề, nội dung ngắn và liên kết điều hướng phù hợp với từng thiết bị như thế nào?
Bạn sẽ chuẩn hóa đường dẫn mở sâu trong ứng dụng để người dùng đến đúng đối tượng mà vẫn kiểm tra quyền truy cập ra sao?
Bạn sẽ xử lý trường hợp người dùng bấm vào thông báo khi ứng dụng đang mở, chạy nền hoặc chưa được khởi động như thế nào?
Bạn sẽ làm rõ giới hạn của việc xử lý thông báo trong nền trên iOS và Android trước khi thiết kế tác vụ quan trọng ra sao?
Bạn sẽ lựa chọn mức ưu tiên gửi phù hợp cho cảnh báo khẩn cấp và tránh lạm dụng ưu tiên cao như thế nào?
Bạn sẽ xác định thời gian sống của thông báo để cảnh báo đã hết giá trị không xuất hiện muộn sau nhiều giờ ra sao?
Bạn sẽ sử dụng cơ chế gom hoặc thay thế thông báo cũ khi nhiều sự kiện tương tự liên tiếp phát sinh như thế nào?
Bạn sẽ thiết kế khóa chống trùng để hạn chế hiển thị nhiều lần cùng một sự kiện khi backend phải retry ra sao?
Bạn sẽ phân biệt nhắm đích theo thiết bị, theo người dùng và theo nhóm chủ đề khi thiết kế bộ định tuyến như thế nào?
Bạn sẽ xác định điều kiện được phép dùng topic broadcast thay vì gửi tới từng token riêng biệt ra sao?
Bạn sẽ kiểm soát việc đăng ký hoặc hủy theo dõi topic để người dùng không nhận thông báo của nhóm mà họ đã rời khỏi như thế nào?
Bạn sẽ tách mẫu nội dung và ngôn ngữ thông báo khỏi logic xử lý nghiệp vụ để hỗ trợ đa ngôn ngữ như thế nào?
Bạn sẽ tôn trọng múi giờ, giờ yên tĩnh và tùy chọn từng loại thông báo khi xây dựng lịch gửi ra sao?
Bạn sẽ thiết kế phân loại thông báo giao dịch, bảo mật và quảng bá để mỗi loại có chính sách đồng ý nhận khác nhau như thế nào?
Bạn sẽ tổ chức backend Java/Spring tạo sự kiện thông báo mà không gọi trực tiếp FCM hoặc APNs trong transaction chính ra sao?
Bạn sẽ sử dụng hàng đợi hoặc outbox để tránh mất yêu cầu thông báo khi tiến trình lỗi giữa lúc lưu nghiệp vụ và gửi push như thế nào?
Bạn sẽ xác định trạng thái đang chờ, đã gửi tới nhà cung cấp, thất bại và không còn hợp lệ trong hệ thống như thế nào?
Bạn sẽ phân biệt việc nhà cung cấp chấp nhận request với bằng chứng thông báo đã đến hoặc được người dùng xem ra sao?
Bạn sẽ phân loại lỗi xác thực, token không hợp lệ, payload sai và lỗi máy chủ tạm thời để quyết định retry như thế nào?
Bạn sẽ áp dụng exponential backoff có jitter và giới hạn lần thử cho thông báo bị lỗi tạm thời ra sao?
Bạn sẽ xử lý lỗi giới hạn tốc độ bằng cách điều chỉnh tốc độ gửi theo phản hồi của FCM hoặc APNs như thế nào?
Bạn sẽ chia nhỏ các đợt gửi lớn và kiểm soát số worker đồng thời để không làm nghẽn tài nguyên backend ra sao?
Bạn sẽ xác định cách xử lý khi một phần token gửi thành công còn phần khác thất bại trong cùng một đợt gửi như thế nào?
Bạn sẽ bảo vệ khóa truy cập, chứng chỉ hoặc thông tin xác thực FCM/APNs bằng cơ chế quản lý bí mật và phân quyền ra sao?
Bạn sẽ tách môi trường phát triển và production để thông báo thử nghiệm không đến người dùng thật như thế nào?
Bạn sẽ giảm rủi ro lộ nội dung riêng tư trên màn hình khóa hoặc trong log bằng cách thiết kế payload và nội dung ra sao?
Bạn sẽ xây dựng các chỉ số tỷ lệ chấp nhận, lỗi gửi, token không hợp lệ và độ trễ hàng đợi để theo dõi hệ thống như thế nào?
Bạn sẽ liên kết một sự kiện nghiệp vụ với nhiều lần thử gửi mà không lưu thông tin nhạy cảm trong log như thế nào?
Bạn sẽ viết unit test cho bộ định tuyến, quản lý token, tạo payload và chính sách retry bằng dependency giả như thế nào?
Bạn sẽ kiểm thử tích hợp backend với phản hồi giả lập của FCM/APNs và kiểm thử ứng dụng trên trạng thái foreground/background ra sao?
Bạn sẽ xử lý tình huống backend báo gửi thành công nhưng người dùng không thấy thông báo do quyền hệ điều hành hoặc chính sách thiết bị như thế nào?
Bạn sẽ đánh giá việc giảm thông báo gây nhiễu có thực sự cải thiện mức tương tác mà không bỏ sót cảnh báo quan trọng như thế nào?
