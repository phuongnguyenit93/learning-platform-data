Bạn giải thích REST là gì và những ràng buộc kiến trúc nào giúp một API thể hiện đúng tinh thần REST?
Bạn phân biệt resource, representation và endpoint như thế nào khi thiết kế một REST API?
Bạn sẽ xác định ranh giới resource từ yêu cầu nghiệp vụ của hệ thống quản lý đơn hàng ra sao?
Vì sao URI nên biểu diễn tài nguyên thay vì mô tả hành động, và bạn xử lý một thao tác nghiệp vụ đặc biệt như hủy đơn hàng thế nào?
Bạn lựa chọn cách đặt tên và cấu trúc URI nào để API nhất quán, dễ hiểu và có thể mở rộng?
Khi nào bạn dùng resource lồng nhau như /orders/{orderId}/items và khi nào bạn tách thành resource độc lập?
Bạn phân biệt path parameter và query parameter theo tiêu chí nào trong thiết kế endpoint?
Bạn sẽ thiết kế bộ lọc, tìm kiếm và sắp xếp cho danh sách sản phẩm để tránh URI mơ hồ như thế nào?
Tính stateless của REST ảnh hưởng ra sao đến việc lưu phiên đăng nhập và mở rộng hệ thống?
Bạn giải thích sự khác nhau giữa tính safe và tính idempotent của phương thức HTTP bằng ví dụ nào?
Bạn thiết kế hành vi của GET như thế nào để tránh làm thay đổi trạng thái nghiệp vụ ngoài ý muốn?
Trong trường hợp nào HEAD hoặc OPTIONS đem lại giá trị thực tế cho client và hạ tầng API?
Bạn quyết định dùng POST hay PUT cho yêu cầu tạo resource dựa trên quyền chọn URI của client như thế nào?
Bạn mong đợi điều gì khi client gửi lại cùng một yêu cầu PUT nhiều lần?
Bạn chọn PUT hay PATCH khi người dùng chỉ cập nhật một phần hồ sơ, và giải thích tác động của từng lựa chọn ra sao?
Bạn sẽ định nghĩa hành vi DELETE khi resource đã bị xóa hoặc yêu cầu xóa được gửi lặp lại như thế nào?
Khi client dùng sai HTTP method, API nên phản hồi thế nào để họ biết các method được hỗ trợ?
Bạn chọn mã trạng thái và header nào khi POST tạo resource thành công, và vì sao?
Bạn thiết kế phản hồi HTTP 202 Accepted thế nào cho một tác vụ xuất báo cáo chạy bất đồng bộ?
Bạn sử dụng HTTP 204 No Content trong những tình huống nào và client cần xử lý phản hồi ra sao?
Bạn phân biệt lỗi cú pháp request với lỗi dữ liệu không hợp lệ bằng HTTP 400 và 422 như thế nào?
Bạn giải thích sự khác nhau giữa HTTP 401 Unauthorized và 403 Forbidden trong một API có xác thực ra sao?
Khi người dùng truy cập resource của tài khoản khác, bạn cân nhắc phản hồi 403 hay 404 dựa trên điều gì?
Bạn sử dụng HTTP 409 Conflict khi nào và mô tả xung đột để client có thể giải quyết ra sao?
Bạn xử lý HTTP 412 Precondition Failed trong tình huống hai người cùng chỉnh sửa một bản ghi thế nào?
Bạn sẽ phản hồi HTTP 429 Too Many Requests kèm thông tin nào để client có thể giảm tốc độ gọi API?
Bạn phân biệt lỗi tạm thời của máy chủ với lỗi request của client khi lựa chọn mã trạng thái HTTP như thế nào?
Bạn thiết kế cấu trúc lỗi theo Problem Details để client xử lý thống nhất mà không phụ thuộc thông điệp văn bản ra sao?
Bạn quyết định trả về những thông tin xác thực dữ liệu nào khi request có nhiều trường không hợp lệ?
Bạn phân biệt trường vắng mặt, trường có giá trị null và trường có giá trị rỗng trong hợp đồng JSON như thế nào?
Bạn sẽ chọn kiểu dữ liệu và quy ước cho tiền tệ, số thập phân, ngày giờ và múi giờ trong API ra sao?
Bạn quản lý những giá trị enum chưa được client cũ nhận biết như thế nào để tránh gây lỗi tương thích?
Vì sao nên tách DTO của API khỏi entity cơ sở dữ liệu khi xây dựng REST API bằng Java hoặc Spring?
Bạn sẽ xử lý trường dữ liệu mới và trường dữ liệu bị loại bỏ để client cũ vẫn hoạt động như thế nào?
Bạn đánh giá một thay đổi hợp đồng API có phá vỡ tương thích ngược hay không bằng các tiêu chí nào?
Bạn lựa chọn chiến lược versioning qua đường dẫn, header hoặc media type dựa trên những đánh đổi gì?
Bạn sẽ thông báo deprecation và lên kế hoạch ngừng hỗ trợ một phiên bản API ra sao?
Bạn sử dụng OpenAPI để thống nhất hợp đồng giữa backend, frontend và QA ngay trước khi lập trình như thế nào?
Bạn đảm bảo tài liệu OpenAPI phản ánh đúng hành vi thực tế của endpoint, kể cả lỗi và xác thực, bằng cách nào?
Bạn sẽ cung cấp ví dụ request và response nào để người tích hợp hiểu được các ràng buộc dữ liệu phức tạp?
Bạn thiết kế cấu trúc trả về cho một API danh sách thế nào để hỗ trợ phân trang và mở rộng metadata?
Bạn so sánh phân trang offset và cursor về hiệu năng, tính ổn định và trải nghiệm client ra sao?
Nếu dữ liệu liên tục được thêm mới trong lúc client chuyển trang, bạn giữ kết quả phân trang nhất quán bằng cách nào?
Vì sao bộ sắp xếp cần có thứ tự xác định khi phân trang, và bạn lựa chọn khóa sắp xếp như thế nào?
Bạn quyết định có nên trả tổng số bản ghi cho mỗi request phân trang hay không dựa trên yếu tố nào?
Bạn sẽ giới hạn page size và tổ hợp bộ lọc như thế nào để ngăn truy vấn tốn tài nguyên?
Bạn bảo đảm bộ lọc và tìm kiếm không làm rò rỉ dữ liệu giữa các tenant bằng cách nào?
Bạn chọn Cache-Control cho dữ liệu công khai và dữ liệu thay đổi liên tục theo những tiêu chí nào?
Bạn giải thích luồng GET với ETag và If-None-Match dẫn đến HTTP 304 Not Modified như thế nào?
Bạn so sánh cơ chế Last-Modified với ETag và lựa chọn một trong hai theo tình huống ra sao?
Bạn dùng If-Match và ETag để chống ghi đè cập nhật đồng thời như thế nào?
Vì sao header Vary quan trọng khi phản hồi phụ thuộc ngôn ngữ hoặc các header của request?
Bạn cấu hình cache cho response chứa thông tin cá nhân thế nào để tránh dữ liệu xuất hiện sai người dùng?
Bạn thiết kế cơ chế vô hiệu hóa cache khi một resource bị cập nhật hoặc xóa như thế nào?
Bạn giải thích vì sao POST thường không idempotent và cách dùng Idempotency-Key cho API thanh toán ra sao?
Bạn xử lý hai request có cùng Idempotency-Key nhưng payload khác nhau như thế nào?
Bạn thiết kế retry với timeout và exponential backoff ra sao để tránh tạo trùng giao dịch hoặc tăng tải hệ thống?
Bạn phân biệt request ID, correlation ID và trace ID trong quá trình điều tra lỗi API như thế nào?
Bạn tách trách nhiệm authentication và authorization trong luồng xử lý REST API ra sao?
Bạn xây dựng phân quyền theo vai trò và quyền sở hữu resource cho endpoint xem đơn hàng như thế nào?
Bạn kiểm tra và phòng tránh lỗ hổng truy cập resource bằng cách thay đổi ID trên URL như thế nào?
Bạn đánh giá những rủi ro nào khi API sử dụng bearer token và xác minh JWT?
Bạn sẽ xử lý token hết hạn, token bị thu hồi và sai phạm vi quyền truy cập như thế nào?
Bạn giải thích CORS hoạt động ra sao và vì sao việc cấu hình CORS không thay thế xác thực hoặc phân quyền?
Bạn xác định khi nào một REST API dùng cookie cần bảo vệ CSRF và triển khai biện pháp nào?
Bạn so sánh API key với OAuth 2.0 cho tích hợp giữa các hệ thống trong những điều kiện nào?
Bạn thiết kế rate limiting theo người dùng, API key hoặc IP để công bằng và chống lạm dụng ra sao?
Bạn bảo vệ dữ liệu nhạy cảm trong URL, log, thông báo lỗi và đường truyền HTTPS như thế nào?
Bạn kiểm soát input để tránh truy vấn quá lớn, mass assignment và các giá trị độc hại như thế nào?
Trong Spring Boot, bạn tổ chức controller, service và repository thế nào để HTTP contract không phụ thuộc logic lưu trữ?
Bạn kết hợp Bean Validation với request DTO để báo lỗi đầu vào nhất quán như thế nào?
Bạn dùng @ControllerAdvice hoặc cơ chế tương đương để chuyển exception thành HTTP response có cấu trúc ra sao?
Bạn đặt transaction ở lớp nào khi một request cần cập nhật nhiều bảng và điều gì xảy ra nếu một bước thất bại?
Bạn triển khai kiểm thử endpoint với MockMvc hoặc WebTestClient để kiểm tra mã trạng thái, header và payload như thế nào?
Bạn sẽ thiết kế integration test với cơ sở dữ liệu thật hoặc Testcontainers cho API tạo và sửa resource ra sao?
Bạn kiểm thử những trường hợp nào để phát hiện lỗi phân quyền, dữ liệu đầu vào và xung đột cập nhật?
Bạn kiểm chứng tương thích hợp đồng OpenAPI giữa các phiên bản API và giữa nhà cung cấp với client bằng cách nào?
Bạn đo p95 latency, throughput và tỷ lệ lỗi để tìm điểm nghẽn của REST API như thế nào?
Bạn xử lý timeout và lỗi từ dịch vụ phía sau để API trả phản hồi nhất quán và không gây quá tải dây chuyền ra sao?
Nếu API đọc danh sách đơn hàng chậm do nhiều truy vấn dữ liệu liên tiếp, bạn sẽ điều tra và cải thiện từ đâu?
Khi thiết kế một REST API mới cho ứng dụng bán hàng, bạn sẽ đi từ yêu cầu nghiệp vụ đến hợp đồng, bảo mật, kiểm thử và triển khai theo trình tự nào?
