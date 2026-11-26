Bạn sẽ giải thích mục tiêu của Microkernel Architecture khi giữ lõi ứng dụng ổn định và mở rộng bằng plugin như thế nào?
Bạn sẽ phân biệt lõi hệ thống với các plugin tùy chọn trong một ứng dụng quản lý tài liệu ra sao?
Bạn sẽ xác định chức năng nào thuộc trách nhiệm lõi và chức năng nào nên được đưa ra điểm mở rộng như thế nào?
Bạn sẽ phân biệt kiến trúc plugin của ứng dụng với khái niệm microkernel trong hệ điều hành ra sao?
Bạn sẽ đánh giá khi nào một ứng dụng cần hỗ trợ plugin thay vì tích hợp trực tiếp mọi tính năng như thế nào?
Bạn sẽ thiết kế extension point để nhiều plugin có thể đóng góp hành vi mà không sửa mã lõi ra sao?
Bạn sẽ quyết định một extension point nên cung cấp những dữ liệu và thao tác nào để hợp đồng không quá rộng như thế nào?
Bạn sẽ thiết kế interface plugin trong Java để lõi không phải biết trước lớp triển khai cụ thể ra sao?
Bạn sẽ phân biệt API dành cho plugin với API nội bộ của lõi để hạn chế phụ thuộc không mong muốn như thế nào?
Bạn sẽ dùng cơ chế đăng ký plugin để lõi phát hiện những tiện ích mở rộng có sẵn như thế nào?
Bạn sẽ đánh giá ưu và nhược điểm của Java ServiceLoader khi phát hiện plugin qua service provider interface ra sao?
Bạn sẽ chọn cách khám phá plugin bằng cấu hình, metadata hay quét classpath dựa trên môi trường triển khai như thế nào?
Bạn sẽ xác thực metadata như tên, phiên bản và các capability của plugin trước khi kích hoạt như thế nào?
Bạn sẽ tổ chức thứ tự khởi tạo plugin khi một plugin phụ thuộc vào extension point do plugin khác cung cấp ra sao?
Bạn sẽ kiểm tra và xử lý phụ thuộc vòng giữa nhiều plugin trước khi hệ thống bắt đầu chạy như thế nào?
Bạn sẽ thiết kế các trạng thái của vòng đời plugin từ phát hiện, nạp, khởi tạo, hoạt động đến dừng như thế nào?
Bạn sẽ xác định trách nhiệm cấp phát và giải phóng tài nguyên của plugin khi khởi động hoặc tắt hệ thống ra sao?
Bạn sẽ xử lý trường hợp plugin khởi tạo thất bại sau khi đã mở kết nối hoặc tạo tác vụ chạy nền như thế nào?
Bạn sẽ xác định chính sách hệ thống tiếp tục chạy hay dừng khi một plugin tùy chọn không thể tải như thế nào?
Bạn sẽ thiết kế cơ chế bật hoặc tắt plugin qua cấu hình mà không làm ảnh hưởng những chức năng lõi khác ra sao?
Bạn sẽ giải thích vai trò của ClassLoader trong việc nạp plugin Java và các rủi ro khi nhiều phiên bản thư viện cùng tồn tại như thế nào?
Bạn sẽ phân biệt classpath chung với cơ chế ClassLoader riêng cho từng plugin về khả năng cô lập phụ thuộc ra sao?
Bạn sẽ phân tích lỗi ClassCastException khi cùng một kiểu được tải bởi hai ClassLoader khác nhau như thế nào?
Bạn sẽ thiết kế gói API chung để plugin và lõi thống nhất kiểu dữ liệu mà không ràng buộc vào thư viện triển khai ra sao?
Bạn sẽ xác định những giới hạn của việc nạp hoặc gỡ plugin khi JVM vẫn còn tham chiếu đến lớp và tài nguyên của plugin như thế nào?
Bạn sẽ nhận biết nguy cơ rò rỉ bộ nhớ từ thread, listener hoặc ClassLoader sau khi gỡ một plugin ra sao?
Bạn sẽ thiết kế hợp đồng phiên bản và chính sách tương thích ngược để plugin cũ tiếp tục chạy khi lõi nâng cấp như thế nào?
Bạn sẽ kiểm tra khả năng tương thích của plugin dựa trên phiên bản API và những capability thực tế được hỗ trợ ra sao?
Bạn sẽ quyết định cách xử lý plugin dùng một phương thức API đã bị ngừng hỗ trợ như thế nào?
Bạn sẽ tổ chức quá trình nâng cấp plugin sao cho có thể hoàn nguyên khi phát hiện lỗi sau triển khai ra sao?
Bạn sẽ giới hạn phạm vi lỗi từ một plugin để ngoại lệ của nó không làm hỏng trạng thái lõi như thế nào?
Bạn sẽ thiết kế timeout và cơ chế ngắt khi một plugin thực hiện tác vụ quá lâu như thế nào?
Bạn sẽ kiểm soát việc nhiều plugin đồng thời sửa cùng một dữ liệu hoặc đăng ký cùng một sự kiện ra sao?
Bạn sẽ lựa chọn thứ tự gọi plugin, mức ưu tiên và cách giải quyết xung đột giữa nhiều phần mở rộng như thế nào?
Bạn sẽ xác định plugin được phép đọc hoặc thay đổi những loại dữ liệu nào dựa trên nguyên tắc đặc quyền tối thiểu ra sao?
Bạn sẽ phân tích giới hạn của việc dùng ClassLoader để cô lập plugin không đáng tin cậy trong cùng tiến trình JVM như thế nào?
Bạn sẽ lựa chọn khi nào cần chạy plugin trong tiến trình riêng để tăng mức độ cô lập và kiểm soát lỗi như thế nào?
Bạn sẽ thiết kế kiểm tra nguồn gốc và tính toàn vẹn của gói plugin trước khi cài đặt ra sao?
Bạn sẽ bảo vệ thông tin cấu hình nhạy cảm và token khi plugin cần gọi dịch vụ bên ngoài như thế nào?
Bạn sẽ xác định cách plugin công bố cấu hình riêng mà không làm phức tạp cấu hình lõi ra sao?
Bạn sẽ thiết kế cách plugin khai báo migration dữ liệu và xử lý hoàn nguyên khi nâng cấp thất bại như thế nào?
Bạn sẽ thiết kế test hợp đồng bảo đảm một plugin tuân thủ extension point đã công bố như thế nào?
Bạn sẽ xây dựng bộ kiểm thử lõi bằng plugin giả lập để xác minh việc đăng ký, kích hoạt và dừng plugin ra sao?
Bạn sẽ tổ chức integration test cho nhiều plugin cùng hoạt động để phát hiện xung đột phụ thuộc và thứ tự khởi tạo như thế nào?
Bạn sẽ kiểm thử tình huống một plugin bị lỗi, trả dữ liệu sai hoặc không phản hồi mà lõi vẫn giữ hành vi chấp nhận được ra sao?
Bạn sẽ thu thập log, metric và thông tin phiên bản theo từng plugin để hỗ trợ chẩn đoán sự cố như thế nào?
Bạn sẽ xây dựng quy tắc đánh giá và phát hành plugin để tránh phiên bản thiếu tương thích được đưa vào môi trường dùng chung ra sao?
Bạn sẽ đánh giá chi phí vận hành, kiểm thử và hỗ trợ phiên bản khi số lượng plugin tăng nhanh như thế nào?
Bạn sẽ chuyển một hệ thống đang chứa nhiều nhánh điều kiện theo loại khách hàng sang kiến trúc plugin theo từng bước như thế nào?
Bạn sẽ xử lý tình huống một plugin của bên thứ ba làm ứng dụng chậm và giữ tài nguyên sau khi đã bị vô hiệu hóa như thế nào?
