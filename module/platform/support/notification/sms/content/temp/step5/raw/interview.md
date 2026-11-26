Bạn sẽ xác định trường hợp nào nên sử dụng SMS thay vì thông báo đẩy hoặc email để bảo đảm thông tin đến đúng người nhận như thế nào?
Bạn sẽ thiết kế quy trình thu thập và xác minh số điện thoại trước khi đăng ký kênh SMS ra sao?
Bạn sẽ giải thích ý nghĩa định dạng E.164 và cách chuyển số điện thoại nhập theo thói quen địa phương sang dạng chuẩn như thế nào?
Bạn sẽ xử lý trường hợp không xác định được mã quốc gia hoặc số điện thoại có độ dài không hợp lệ ra sao?
Bạn sẽ phân biệt việc số điện thoại có cú pháp hợp lệ với bằng chứng số đó đang hoạt động và thuộc người dùng như thế nào?
Bạn sẽ thiết kế lưu trữ số điện thoại theo dạng chuẩn và tránh mất dấu cộng hoặc số có ý nghĩa trong mã quốc gia ra sao?
Bạn sẽ xác định quyền đồng ý nhận tin và cơ chế hủy đăng ký cho các nhóm thông báo khác nhau như thế nào?
Bạn sẽ phân biệt SMS giao dịch, OTP và nội dung quảng bá khi xây dựng chính sách gửi và lưu lịch sử ra sao?
Bạn sẽ xác định cách bảo vệ thông tin cá nhân khi xử lý số điện thoại và nội dung SMS trong hệ thống ra sao?
Bạn sẽ lựa chọn dịch vụ SMS gateway theo vùng phủ sóng, chất lượng giao nhận, giới hạn tốc độ và giá cước như thế nào?
Bạn sẽ so sánh tích hợp SMS gateway qua HTTP API với giao thức SMPP về độ phức tạp, thông lượng và vận hành ra sao?
Bạn sẽ thiết kế một interface Java/Spring để nghiệp vụ không phụ thuộc trực tiếp vào một nhà cung cấp SMS cụ thể như thế nào?
Bạn sẽ chuẩn hóa dữ liệu request gửi SMS gồm người nhận, loại thông báo, nội dung và mã tương quan ra sao?
Bạn sẽ quản lý thông tin xác thực và endpoint gateway theo môi trường mà không để khóa bí mật xuất hiện trong mã nguồn như thế nào?
Bạn sẽ tổ chức HTTP client, timeout và kiểm soát kết nối khi gửi SMS qua REST API ra sao?
Bạn sẽ mô tả vòng đời phiên SMPP từ kết nối, xác thực đến gửi bản tin và nhận phản hồi như thế nào?
Bạn sẽ kiểm soát trạng thái phiên SMPP và cơ chế kết nối lại khi gateway hoặc đường truyền gián đoạn ra sao?
Bạn sẽ phân biệt kết quả gateway đã chấp nhận submit với trạng thái tin nhắn thực sự được giao đến thiết bị như thế nào?
Bạn sẽ sử dụng mã định danh tin do gateway trả về để liên kết các yêu cầu gửi với delivery receipt ra sao?
Bạn sẽ thiết kế endpoint hoặc luồng nhận delivery receipt để kiểm tra tính xác thực và cập nhật trạng thái tin nhắn như thế nào?
Bạn sẽ ánh xạ các trạng thái giao nhận khác nhau từ nhiều nhà cung cấp về mô hình trạng thái thống nhất ra sao?
Bạn sẽ xử lý delivery receipt đến muộn, bị lặp hoặc xuất hiện sai thứ tự so với trạng thái đã ghi nhận như thế nào?
Bạn sẽ quyết định khi nào một trạng thái gửi có thể coi là cuối cùng và khi nào cần tiếp tục chờ receipt như thế nào?
Bạn sẽ thiết kế chính sách hết hạn khi gateway không trả delivery receipt dù đã chấp nhận gửi ra sao?
Bạn sẽ tổ chức template SMS để nội dung dùng biến động nhưng vẫn được kiểm tra dữ liệu và độ dài như thế nào?
Bạn sẽ ngăn dữ liệu do người dùng cung cấp làm thay đổi ý nghĩa của một mẫu SMS có thông tin quan trọng ra sao?
Bạn sẽ xác định ảnh hưởng của bảng mã GSM và ký tự Unicode tiếng Việt đến số phân đoạn và chi phí gửi như thế nào?
Bạn sẽ xử lý thông điệp dài bị tách thành nhiều SMS và bảo đảm người nhận hiểu đúng nội dung như thế nào?
Bạn sẽ ước tính số phân đoạn, cước phí và giới hạn ngân sách trước khi chấp nhận một chiến dịch gửi lớn ra sao?
Bạn sẽ quản lý sender ID hoặc số gửi theo khu vực và quy định của từng nhà cung cấp như thế nào?
Bạn sẽ phân biệt lỗi cấu hình sender, lỗi người nhận và lỗi mạng tạm thời để áp dụng cách xử lý phù hợp ra sao?
Bạn sẽ đưa yêu cầu gửi SMS vào hàng đợi để không giữ giao dịch nghiệp vụ chờ phản hồi của gateway như thế nào?
Bạn sẽ thiết kế outbox hoặc lưu sự kiện bền vững để giảm nguy cơ mất yêu cầu gửi SMS khi hệ thống lỗi ra sao?
Bạn sẽ xây dựng cơ chế chống gửi trùng khi cùng một sự kiện nghiệp vụ được xử lý lại hoặc worker phải retry như thế nào?
Bạn sẽ xử lý trường hợp gateway đã gửi tin nhưng backend mất phản hồi trước khi nhận mã định danh thông điệp như thế nào?
Bạn sẽ sử dụng backoff và giới hạn số lần thử lại để tránh gửi lặp SMS gây tốn cước hoặc làm phiền người dùng ra sao?
Bạn sẽ áp dụng giới hạn tốc độ theo gateway, người nhận và loại thông báo khi hệ thống tăng tải như thế nào?
Bạn sẽ xác định khi nào một tin nhắn đã quá hạn và không nên gửi lại dù gateway đã phục hồi ra sao?
Bạn sẽ thiết kế định tuyến dự phòng sang gateway thứ hai mà không tạo nguy cơ gửi đôi một thông điệp như thế nào?
Bạn sẽ lựa chọn thứ tự ưu tiên gateway theo tỷ lệ lỗi, thời gian giao nhận, vùng phủ sóng và giá cước ra sao?
Bạn sẽ thiết kế quy trình tạo và gửi OTP sao cho mã ngẫu nhiên đủ mạnh, có hạn dùng và không thể sử dụng lại như thế nào?
Bạn sẽ xác định giới hạn số lần yêu cầu OTP, số lần nhập sai và khoảng cách giữa các lần gửi để chống lạm dụng ra sao?
Bạn sẽ bảo vệ OTP khỏi việc bị ghi vào log, lưu trữ dưới dạng rõ hoặc gửi nhầm sang số điện thoại của tài khoản khác như thế nào?
Bạn sẽ thiết kế xác thực OTP khi tin SMS đến muộn hoặc người dùng yêu cầu mã mới trước khi mã cũ hết hạn ra sao?
Bạn sẽ xác định các biện pháp giảm nguy cơ dò mã, chiếm đoạt tài khoản và khai thác chi phí SMS qua API công khai như thế nào?
Bạn sẽ theo dõi độ trễ gửi, tỷ lệ delivery receipt, chi phí theo nhà cung cấp và số tin lỗi bằng những chỉ số nào?
Bạn sẽ phân tích khiếu nại người dùng không nhận SMS bằng dữ liệu trạng thái gateway mà không lộ nội dung riêng tư ra sao?
Bạn sẽ viết unit test cho chuẩn hóa E.164, ánh xạ trạng thái, template, chống trùng và chính sách retry như thế nào?
Bạn sẽ dùng gateway giả để kiểm thử HTTP API hoặc SMPP khi nhà cung cấp trả lỗi giới hạn tốc độ, mất kết nối hay receipt lặp ra sao?
Bạn sẽ đánh giá hệ thống SMS khi tỷ lệ gateway chấp nhận gửi cao nhưng tỷ lệ giao nhận thực tế thấp và cước phí tăng như thế nào?
