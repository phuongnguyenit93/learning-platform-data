Trong kiến trúc client–server, bạn phân định trách nhiệm cốt lõi của client và server dựa trên tiêu chí nào?
Bạn phân biệt vai trò logic của client–server với số lượng tiến trình hoặc máy chủ triển khai thực tế như thế nào?
Nếu giao diện web chứa nhiều logic nghiệp vụ, bạn xác định phần nào cần chuyển về server để bảo đảm tính đúng đắn ra sao?
Bạn mô tả vòng đời một yêu cầu từ thao tác người dùng đến khi client hiển thị phản hồi như thế nào?
Bạn sẽ thiết kế hợp đồng request và response để client và server phát triển độc lập ra sao?
Khi HTTP trả mã thành công nhưng tác vụ nghiệp vụ thất bại, bạn biểu diễn kết quả cho client như thế nào?
Bạn lựa chọn giữa REST, RPC và giao thức giao tiếp khác dựa trên đặc điểm ứng dụng nào?
Đặc điểm không đồng bộ của mạng ảnh hưởng thế nào đến các giả định về thứ tự phản hồi trên client?
Bạn quyết định sử dụng request–response thông thường, long polling hay WebSocket cho cập nhật thời gian thực như thế nào?
Khi một lời gọi mạng có thể mất nhiều giây, bạn thiết kế trạng thái chờ và khả năng hủy thao tác trên client ra sao?
Bạn phân biệt xác thực dữ liệu ở client với kiểm tra bắt buộc ở server bằng ví dụ nào?
Khi cùng một quy tắc nghiệp vụ được triển khai ở cả hai phía, bạn sẽ phòng tránh hành vi không nhất quán như thế nào?
Bạn sẽ tổ chức mã phía server thành lớp giao tiếp, dịch vụ nghiệp vụ và truy cập dữ liệu dựa trên trách nhiệm nào?
Một lớp trung gian giữa client và server giúp giải quyết vấn đề nào và làm phát sinh chi phí gì?
Bạn phân biệt nhiệm vụ của reverse proxy, API gateway và application server trong một luồng request ra sao?
Khi sử dụng backend-for-frontend cho web và mobile, bạn xác định trách nhiệm riêng của từng lớp như thế nào?
Bạn xử lý phiên bản API thế nào khi ứng dụng di động cũ không thể được cập nhật đồng thời với server?
Bạn đánh giá những trường hợp nào nên trả dữ liệu tổng hợp từ server thay vì để client gọi nhiều endpoint?
Khi client lặp lại một yêu cầu ghi sau timeout, bạn thiết kế idempotency để tránh phát sinh thao tác trùng ra sao?
Bạn lựa chọn thời gian timeout, số lần retry và backoff cho client dựa trên đặc điểm giao dịch như thế nào?
Bạn sẽ quản lý trạng thái phiên làm việc khi server có nhiều instance phục vụ cùng một người dùng ra sao?
Bạn so sánh session lưu trên server, session lưu ở kho dùng chung và token tự chứa theo những rủi ro nào?
Trong thiết kế stateless, những loại trạng thái nào vẫn cần được lưu hoặc quản lý ở server?
Khi dùng cookie để xác thực, bạn kiểm soát thuộc tính bảo mật và nguy cơ CSRF như thế nào?
Bạn phân biệt xác thực danh tính với phân quyền trên từng tài nguyên tại server ra sao?
Nếu client gửi trường role hoặc ownerId, server sẽ xác minh quyền thực hiện thao tác theo nguồn nào?
Bạn bảo vệ dữ liệu nhạy cảm khi truyền qua TLS và qua các thành phần trung gian như thế nào?
Bạn sẽ đặt rate limit tại client, gateway và server trong những tình huống nào?
Khi cần cân bằng tải giữa nhiều server, bạn lựa chọn thuật toán phân phối yêu cầu dựa trên thông tin nào?
Bạn thiết kế health check và readiness check để load balancer loại bỏ instance chưa sẵn sàng ra sao?
Sticky session có thể giúp ứng dụng stateful trong ngắn hạn nhưng hạn chế khả năng mở rộng như thế nào?
Bạn sẽ mở rộng server theo chiều ngang khi có trạng thái phiên hoặc cache cục bộ mà không gây lỗi cho người dùng ra sao?
Khi lưu lượng tập trung vào một endpoint, bạn phân biệt giới hạn của server với nút thắt của database bằng cách nào?
Bạn lựa chọn cache ở trình duyệt, CDN, reverse proxy hoặc server theo độ mới dữ liệu và khả năng vô hiệu hóa ra sao?
Nếu client đọc dữ liệu cũ sau một thao tác ghi thành công, bạn thiết kế cơ chế đồng bộ trạng thái như thế nào?
Bạn đánh giá ảnh hưởng của kích thước payload và số lượt request tới trải nghiệm ở mạng di động ra sao?
Khi server hết connection pool tới database, bạn sẽ xác định ảnh hưởng lên thời gian phản hồi client như thế nào?
Bạn thiết kế xử lý graceful degradation khi server hoặc một dịch vụ phụ thuộc không sẵn sàng ra sao?
Khi nhiều client retry đồng thời sau lỗi mạng, bạn kiểm soát nguy cơ làm hệ thống quá tải bằng cách nào?
Bạn sẽ triển khai rolling update nhiều phiên bản server mà vẫn giữ hợp đồng tương thích với client như thế nào?
Bạn dùng log có correlation ID, metrics và distributed tracing để truy vết lỗi từ client tới server ra sao?
Khi cần phục vụ nhiều khu vực địa lý, bạn đánh đổi độ trễ, định tuyến và tính nhất quán dữ liệu như thế nào?
Một client hoạt động ngoại tuyến cần lưu hàng đợi thay đổi và xử lý xung đột khi kết nối lại ra sao?
Bạn phân biệt lỗi mạng, lỗi xác thực, lỗi nghiệp vụ và lỗi server trong thông báo trả về client như thế nào?
Bạn tổ chức kiểm thử hợp đồng API để phát hiện thay đổi server làm hỏng client cũ ra sao?
Bạn kiểm tra hiệu năng và khả năng chịu tải của kiến trúc client–server bằng các hành trình người dùng nào?
Khi gateway trở thành điểm lỗi đơn, bạn lựa chọn cơ chế dự phòng và giám sát như thế nào?
Trong quá trình tách một ứng dụng nguyên khối thành client và server độc lập, bạn sẽ xác định ranh giới dữ liệu ra sao?
Bạn lựa chọn kiến trúc client–server hai tầng, ba tầng hay có gateway trung gian dựa trên yếu tố vận hành nào?
Bạn đánh giá một thiết kế client–server mới theo độ phức tạp, bảo mật, hiệu năng và khả năng thay đổi bằng cách nào?
