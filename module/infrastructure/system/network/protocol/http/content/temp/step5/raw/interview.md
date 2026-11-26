HTTP giải quyết nhu cầu trao đổi dữ liệu giữa client và server như thế nào, và mô hình request/response có những giới hạn gì?
Bạn mô tả vòng đời của một yêu cầu HTTP từ lúc người dùng nhập URL đến khi client nhận được response như thế nào?
Bạn phân biệt vai trò của scheme, authority, path, query và fragment trong một URI như thế nào?
Bạn giải thích mối liên hệ giữa URL, URI và tài nguyên được định danh trên web như thế nào?
Bạn xác định những trường hợp nào cần percent-encoding khi truyền giá trị trong path hoặc query string?
Bạn thiết kế URI cho tài nguyên API sao cho ổn định, dễ hiểu và không phụ thuộc vào cấu trúc lưu trữ nội bộ như thế nào?
Bạn phân biệt path parameter, query parameter, request header và request body khi thiết kế đầu vào API ra sao?
Bạn kiểm tra cách client và proxy xử lý dấu gạch chéo cuối path, ký tự đặc biệt và chữ hoa chữ thường trong URL như thế nào?
Bạn giải thích cấu trúc start line, header section và message body của một thông điệp HTTP/1.1 như thế nào?
Bạn phân biệt các thành phần của request line và status line trong HTTP/1.1 như thế nào?
Host header trong HTTP/1.1 ảnh hưởng thế nào đến khả năng phục vụ nhiều website trên cùng một địa chỉ mạng?
Bạn phân biệt header mô tả nội dung, header điều khiển cache và header phục vụ xác thực thông qua những tình huống nào?
Bạn giải thích tính không lưu trạng thái của HTTP và cách ứng dụng duy trì phiên làm việc qua nhiều request như thế nào?
Bạn xác định ý nghĩa của safe và idempotent khi đánh giá một HTTP method như thế nào?
GET phù hợp với những thao tác nào và bạn tránh tạo tác dụng phụ ngoài ý muốn khi xử lý GET ra sao?
Bạn dùng HEAD để kiểm tra metadata của một tài nguyên và so sánh với GET như thế nào?
Bạn lựa chọn POST hoặc PUT khi tạo mới tài nguyên dựa trên ngữ nghĩa và quyền quyết định URI như thế nào?
Bạn thiết kế thao tác PUT khi tài nguyên đã tồn tại hoặc chưa tồn tại để đáp ứng tính idempotent ra sao?
Bạn chọn PATCH thay cho PUT trong trường hợp nào và làm thế nào để kiểm soát xung đột cập nhật?
Bạn thiết kế DELETE sao cho client có thể gửi lại request an toàn khi gặp timeout như thế nào?
Bạn sử dụng OPTIONS để khám phá phương thức được hỗ trợ và xử lý preflight của trình duyệt như thế nào?
Bạn đánh giá rủi ro và chính sách cho phép đối với các phương thức CONNECT và TRACE trong hệ thống API như thế nào?
Bạn thiết kế request body cho POST hoặc PATCH và chọn media type để hai phía hiểu đúng dữ liệu như thế nào?
Bạn phân biệt Content-Type với Accept khi client gửi và nhận biểu diễn tài nguyên như thế nào?
Bạn sử dụng content negotiation để phục vụ JSON, XML hoặc định dạng khác mà vẫn giữ ý nghĩa tài nguyên ra sao?
Những đặc điểm của kết quả xử lý quyết định việc trả 200 OK, 201 Created, 202 Accepted hay 204 No Content cho một API?
Bạn dùng Location header sau thao tác tạo tài nguyên hoặc redirect theo những quy tắc nào?
Bạn phân biệt chuyển hướng 301, 302, 303, 307 và 308 theo cách client xử lý method và khả năng lưu cache như thế nào?
Bạn phân biệt các trường hợp nên trả 400 Bad Request, 404 Not Found, 405 Method Not Allowed và 422 Unprocessable Content dựa trên tiêu chí nào?
Bạn phân biệt 401 Unauthorized với 403 Forbidden theo trạng thái xác thực và quyền truy cập như thế nào?
Bạn dùng 409 Conflict và 412 Precondition Failed trong những tình huống cập nhật đồng thời nào?
Bạn phân biệt 408 Request Timeout, 429 Too Many Requests và 503 Service Unavailable khi hệ thống quá tải hoặc chờ lâu như thế nào?
Bạn giải thích sự khác nhau giữa 500, 502, 503 và 504 khi request đi qua reverse proxy đến backend như thế nào?
Bạn thiết kế error response để client có thể xử lý lỗi ổn định mà không làm lộ thông tin nội bộ như thế nào?
Khi response dùng mã 204 hoặc 304, client cần diễn giải việc không có message body như thế nào?
Bạn xử lý trường hợp HTTP response có mã 200 nhưng body chứa lỗi nghiệp vụ khiến client hiểu sai kết quả ra sao?
Bạn phân biệt header Content-Length với cơ chế Transfer-Encoding: chunked trong HTTP/1.1 như thế nào?
Bạn giải thích việc đóng kết nối, dùng Content-Length hoặc chunked framing giúp xác định điểm kết thúc body trong HTTP/1.1 như thế nào?
Bạn nhận diện sự khác biệt giữa encoding ở mức nội dung và framing ở mức truyền tải như thế nào?
Bạn thương lượng nén nội dung với Accept-Encoding và Content-Encoding để giảm băng thông ra sao?
Bạn đánh giá khi nào nén response mang lại lợi ích và khi nào CPU hoặc kích thước payload khiến nén kém hiệu quả?
Bạn sử dụng Range và Content-Range để hỗ trợ tải tiếp tệp lớn hoặc chỉ đọc một phần nội dung như thế nào?
Bạn giải thích cơ chế multipart/form-data khi client gửi biểu mẫu có tệp đính kèm như thế nào?
Bạn thiết lập giới hạn kích thước body, thời gian nhận và số lượng header để bảo vệ server như thế nào?
Bạn thiết kế upload hoặc download lớn qua HTTP mà vẫn xử lý được ngắt kết nối và truyền lại ra sao?
Bạn xác định cách client sử dụng Keep-Alive hoặc kết nối HTTP/1.1 kéo dài để giảm chi phí thiết lập kết nối như thế nào?
Bạn phân biệt kết nối TCP với từng request HTTP khi một kết nối có thể phục vụ nhiều request như thế nào?
Bạn phân tích hiện tượng head-of-line blocking trong HTTP/1.1 và ảnh hưởng của nó đến độ trễ như thế nào?
HTTP/2 sử dụng stream và multiplexing để cải thiện xử lý nhiều request đồng thời so với HTTP/1.1 ra sao?
Bạn phân biệt frame, stream và connection trong HTTP/2 khi phân tích luồng truyền dữ liệu như thế nào?
HPACK trong HTTP/2 giúp giảm chi phí truyền header và có những đánh đổi vận hành nào?
Bạn đánh giá vai trò của flow control và stream priority khi nhiều luồng HTTP/2 dùng chung một kết nối như thế nào?
Vì sao HTTP/2 vẫn có thể chịu ảnh hưởng của mất gói TCP dù hỗ trợ multiplexing ở tầng HTTP?
Bạn kiểm tra khả năng thương lượng HTTP/2 bằng ALPN khi thiết lập kết nối TLS như thế nào?
Bạn phân tích các điểm khác nhau về truyền tải giữa HTTP/2 trên TCP và HTTP/3 trên QUIC như thế nào?
Bạn giải thích cách QUIC xử lý stream độc lập để giảm head-of-line blocking giữa các stream như thế nào?
Bạn đánh giá ảnh hưởng của UDP, NAT và firewall đến việc sử dụng HTTP/3 trong mạng thực tế như thế nào?
Bạn mô tả cơ chế thương lượng và chuyển về giao thức khác khi client hoặc mạng không hỗ trợ HTTP/3 như thế nào?
Bạn giải thích các khác biệt về nén header HPACK và QPACK khi so sánh HTTP/2 với HTTP/3 như thế nào?
Bạn phân tích lợi ích và rủi ro replay khi sử dụng TLS 1.3 early data hoặc 0-RTT cho request HTTP như thế nào?
Bạn lựa chọn HTTP/1.1, HTTP/2 hoặc HTTP/3 dựa trên kiểu workload, chất lượng mạng và khả năng hỗ trợ của client như thế nào?
HTTPS bảo vệ những thuộc tính nào của dữ liệu khi truyền và còn để lộ những loại metadata mạng nào?
Bạn mô tả vai trò của TLS handshake, chứng chỉ máy chủ và chuỗi tin cậy khi thiết lập kết nối HTTPS như thế nào?
Bạn phân biệt lỗi chứng chỉ hết hạn, sai hostname và CA không được tin cậy khi chẩn đoán HTTPS ra sao?
Bạn áp dụng HSTS để giảm nguy cơ hạ cấp từ HTTPS sang HTTP và cân nhắc điều gì khi triển khai?
Bạn quyết định vị trí TLS termination tại reverse proxy hoặc ứng dụng và bảo vệ kết nối chặng sau như thế nào?
Bạn sử dụng mTLS trong giao tiếp giữa các dịch vụ để xác minh cả client lẫn server trong trường hợp nào?
Bạn phân biệt các cách gửi credential bằng Authorization header, cookie và API key theo rủi ro bảo mật như thế nào?
Bạn tổ chức quá trình xác thực bằng HTTP challenge và WWW-Authenticate khi server trả 401 như thế nào?
Bạn lựa chọn Bearer token và các biện pháp bảo vệ token khi xây dựng API qua HTTPS ra sao?
Bạn giải thích cách Set-Cookie và Cookie header giúp browser duy trì phiên người dùng qua nhiều request như thế nào?
Bạn lựa chọn thuộc tính Secure, HttpOnly và SameSite của cookie để giảm rủi ro tấn công như thế nào?
Bạn cân nhắc Domain, Path, Expires và Max-Age của cookie khi chia sẻ hoặc giới hạn phạm vi phiên đăng nhập như thế nào?
Bạn xử lý tình huống cookie không được browser gửi sau redirect hoặc request cross-site bằng cách kiểm tra những thuộc tính nào?
Bạn phân biệt cơ chế phòng chống CSRF và XSS trong bối cảnh xác thực dựa trên cookie như thế nào?
Bạn mô tả same-origin policy và vai trò của CORS khi JavaScript gọi API khác origin như thế nào?
Bạn phân biệt CORS request đơn giản với request cần preflight và các trường hợp browser gửi OPTIONS như thế nào?
Bạn cấu hình Access-Control-Allow-Origin, các header CORS khác và credential sao cho đáp ứng chính sách truy cập như thế nào?
Bạn giải thích vì sao CORS trong trình duyệt không thay thế việc kiểm tra xác thực và phân quyền ở server?
Bạn xác định các lớp phòng vệ trước header injection, request smuggling và thông điệp HTTP có framing không nhất quán như thế nào?
Bạn kiểm soát những header do reverse proxy chuyển tiếp như Forwarded hoặc X-Forwarded-For để tránh giả mạo thông tin client ra sao?
Bạn phân biệt cache của trình duyệt, proxy trung gian và CDN về phạm vi sử dụng và cách vô hiệu hóa dữ liệu như thế nào?
Bạn diễn giải Cache-Control: max-age, s-maxage, public, private, no-store và no-cache khi thiết kế chính sách cache ra sao?
ETag và If-None-Match phối hợp như thế nào để client xác minh biểu diễn tài nguyên có thay đổi?
Bạn dùng Last-Modified và If-Modified-Since khi nào và cân nhắc những hạn chế về độ chính xác nào?
Bạn phân biệt response 304 Not Modified với response 200 có nội dung mới khi xử lý conditional GET như thế nào?
Bạn sử dụng If-Match và ETag để ngăn thao tác ghi đè dữ liệu của người khác khi cập nhật tài nguyên như thế nào?
Trong trường hợp nào bạn cần Vary để cache phân biệt response theo Accept-Encoding, Accept-Language hoặc header khác?
Bạn phân tích tình huống CDN trả nhầm dữ liệu cá nhân do cache key hoặc Cache-Control cấu hình sai ra sao?
Bạn áp dụng stale-while-revalidate hoặc stale-if-error trong những tình huống cần cân bằng độ mới và khả năng sẵn sàng như thế nào?
Bạn thiết kế cơ chế cache invalidation khi tài nguyên thay đổi nhưng client vẫn thấy nội dung cũ như thế nào?
Bạn dùng curl hoặc công cụ tương đương để tạo request có method, header, body và xem chi tiết response ra sao?
Bạn phân tích một bản ghi HTTP request/response để xác định URI, method, status, content negotiation và thời gian xử lý như thế nào?
Bạn sử dụng browser DevTools để tìm nguyên nhân request bị redirect lặp, lỗi CORS hoặc thiếu cookie như thế nào?
Bạn đối chiếu request gửi trực tiếp đến backend với request đi qua gateway để phát hiện header hoặc path bị biến đổi ra sao?
Bạn thiết kế các trường hợp kiểm thử API cho method sai, payload sai, thiếu quyền và tài nguyên không tồn tại như thế nào?
Bạn kiểm chứng tính idempotent khi client retry PUT hoặc DELETE sau timeout nhưng không biết server đã xử lý hay chưa như thế nào?
Bạn thiết kế retry, backoff và timeout cho client HTTP để tránh nhân đôi tác dụng phụ hoặc khuếch đại quá tải ra sao?
Bạn dùng Retry-After, rate limit response và mã 429 hoặc 503 để hướng dẫn client giảm tải như thế nào?
Bạn sử dụng request ID, distributed tracing và access log để theo dõi một request qua proxy và nhiều backend ra sao?
Bạn phân rã thời gian DNS, TCP connect, TLS handshake, gửi request, chờ byte đầu tiên và tải body khi phân tích độ trễ như thế nào?
Bạn chẩn đoán sự khác nhau giữa lỗi DNS, lỗi TLS, connection reset, timeout và HTTP error response như thế nào?
Bạn đánh giá ảnh hưởng của proxy, NAT, CDN và bộ cân bằng tải đối với kết nối HTTP đang tồn tại như thế nào?
Bạn kiểm tra các vấn đề về connection pooling và giới hạn kết nối khi client gửi nhiều request HTTP đồng thời ra sao?
Khi một API hoạt động trên HTTP/1.1 nhưng lỗi trên HTTP/2 hoặc HTTP/3, bạn sẽ thu thập những bằng chứng giao thức nào?
Bạn thiết kế bộ chỉ số kiểm thử về latency, throughput, tỷ lệ lỗi, khả năng retry và hiệu quả cache cho một API như thế nào?
