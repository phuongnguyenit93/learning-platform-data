Bạn mô tả một chu kỳ HTTP request-response từ lúc client gửi yêu cầu đến khi nhận và xử lý phản hồi như thế nào?
Khi người dùng nhập một URL vào trình duyệt, những bước nào diễn ra trước khi HTTP response được hiển thị?
Bạn phân biệt vai trò của client, origin server và các thành phần trung gian trong một phiên giao tiếp HTTP ra sao?
Bạn giải thích các thành phần của một HTTP request gồm method, request target, header và body bằng ví dụ nào?
Bạn sẽ đọc status line, response header và response body để hiểu kết quả xử lý của server như thế nào?
Bạn phân tích scheme, host, port, path, query và fragment trong một URL cụ thể ra sao?
Bạn quyết định đưa dữ liệu vào path hay query string theo ý nghĩa của thông tin đó như thế nào?
Vì sao fragment trong URL thường không được gửi đến server trong HTTP request, và điều này ảnh hưởng đến thiết kế ứng dụng ra sao?
Bạn giải thích mục đích của percent-encoding và những lỗi thường gặp khi mã hóa ký tự đặc biệt trong URL như thế nào?
Bạn sẽ xử lý các tham số query lặp lại, thiếu hoặc có giá trị rỗng để client và server hiểu thống nhất ra sao?
Bạn phân biệt URL tuyệt đối, đường dẫn tương đối và request target mà client gửi trong HTTP/1.1 như thế nào?
Bạn giải thích vai trò của header Host trong HTTP/1.1 khi nhiều website dùng chung địa chỉ IP ra sao?
Bạn phân biệt thông tin nằm trong HTTP header với dữ liệu nằm trong message body theo tiêu chí nào?
Bạn sẽ kiểm tra một request thiếu header bắt buộc hoặc có giá trị header sai định dạng như thế nào?
Bạn giải thích cách client và server biết điểm kết thúc của một HTTP message khi dùng HTTP/1.1 ra sao?
Bạn so sánh Content-Length và Transfer-Encoding: chunked trong cách xác định phần thân thông điệp như thế nào?
Khi Content-Length không khớp số byte thực tế, bạn dự đoán những lỗi giao tiếp hoặc xử lý nào có thể phát sinh?
Bạn phân biệt HTTP với TCP và giải thích mỗi giao thức chịu trách nhiệm gì trong quá trình trao đổi dữ liệu ra sao?
Bạn mô tả vai trò của DNS, TCP và TLS trong một yêu cầu HTTPS theo trình tự nào?
Bạn phân biệt HTTP và HTTPS về bảo mật đường truyền, xác thực máy chủ và khả năng quan sát thông điệp ra sao?
Bạn sẽ điều tra một lỗi chứng chỉ TLS khiến trình duyệt không thể gửi HTTP request như thế nào?
Bạn giải thích mục đích tái sử dụng kết nối trong HTTP/1.1 và tác động đến thời gian phản hồi ra sao?
Bạn so sánh cách HTTP/1.1 và HTTP/2 truyền nhiều request trên cùng kết nối như thế nào?
Bạn mô tả HTTP/2 sử dụng stream và frame để truyền thông điệp mà vẫn giữ ngữ nghĩa HTTP ra sao?
Bạn giải thích HTTP/3 sử dụng QUIC khác gì so với HTTP/2 chạy trên TCP về hành vi kết nối khi mạng biến động?
Bạn sẽ phân biệt lỗi ở tầng kết nối với phản hồi HTTP có mã trạng thái lỗi khi phân tích một sự cố như thế nào?
Bạn giải thích các đặc tính safe và idempotent của HTTP method bằng những tình huống cụ thể nào?
Bạn xác định khi nào nên dùng GET để truy xuất dữ liệu và những tác động ngoài ý muốn cần tránh ra sao?
Bạn so sánh GET và HEAD về mục đích sử dụng, header phản hồi và phần thân thông điệp như thế nào?
Bạn sử dụng OPTIONS để tìm hiểu khả năng hỗ trợ của một endpoint hoặc xử lý preflight như thế nào?
Bạn chọn POST để gửi dữ liệu tạo mới hoặc kích hoạt xử lý theo những ngữ nghĩa HTTP nào?
Bạn phân biệt PUT và PATCH khi gửi yêu cầu thay đổi một resource, đặc biệt với các trường không được gửi lên, ra sao?
Bạn giải thích ý nghĩa của việc gửi lặp lại cùng một yêu cầu DELETE trong một API được thiết kế idempotent như thế nào?
Khi client không được phép sử dụng một HTTP method trên resource, bạn sẽ đánh giá status code và header phản hồi nào?
Bạn quyết định có nên gửi body trong một HTTP request dựa trên method và hợp đồng của endpoint như thế nào?
Bạn giải thích Content-Type khác gì Accept khi client gửi JSON và mong đợi dữ liệu trả về ra sao?
Bạn phân tích ý nghĩa của charset trong Content-Type và cách phát hiện lỗi chữ tiếng Việt hiển thị sai như thế nào?
Bạn sẽ sử dụng Accept với nhiều media type và hệ số ưu tiên để thương lượng định dạng phản hồi như thế nào?
Bạn giải thích vai trò của Accept-Language khi server hỗ trợ nhiều ngôn ngữ và lựa chọn giá trị phản hồi ra sao?
Bạn phân biệt Content-Encoding với Transfer-Encoding trong quá trình truyền một response được nén như thế nào?
Bạn dùng Accept-Encoding và Content-Encoding để kiểm tra việc nén nội dung giữa client và server ra sao?
Bạn sẽ xử lý phản hồi HTTP 406 Not Acceptable và 415 Unsupported Media Type trong hai tình huống khác nhau như thế nào?
Bạn giải thích vì sao header Vary quan trọng khi nội dung phản hồi phụ thuộc Accept-Language hoặc Accept-Encoding?
Bạn chọn status code nào cho một yêu cầu đọc dữ liệu thành công và giải thích sự khác nhau giữa 200 và 204 ra sao?
Bạn thiết kế response 201 Created với thông tin resource mới và header Location như thế nào?
Bạn giải thích phản hồi 202 Accepted thể hiện điều gì đối với một tác vụ chạy bất đồng bộ ra sao?
Bạn phân tích cách client xử lý phản hồi 204 No Content mà không cố giải mã JSON từ body như thế nào?
Bạn giải thích mục đích của các phản hồi 1xx như 100 Continue trong quá trình trao đổi HTTP ra sao?
Bạn phân biệt HTTP 301 và 302 về ý nghĩa chuyển hướng và ảnh hưởng đến bộ nhớ cache như thế nào?
Bạn giải thích khi nào một server dùng 303 See Other sau POST để client đọc kết quả bằng GET ra sao?
Bạn so sánh HTTP 307 và 308 với 301 và 302 về khả năng giữ nguyên HTTP method khi chuyển hướng như thế nào?
Bạn sẽ kiểm tra header Location và phát hiện vòng lặp redirect khiến client không đến được trang đích ra sao?
Bạn xử lý tình huống redirect từ HTTPS sang HTTP hoặc chuyển sang domain khác để bảo vệ dữ liệu nhạy cảm như thế nào?
Bạn phân biệt lỗi request sai cú pháp với resource không tồn tại thông qua HTTP 400 và 404 ra sao?
Bạn giải thích khác biệt giữa 401 Unauthorized và 403 Forbidden dựa trên trạng thái xác thực và quyền truy cập như thế nào?
Bạn phân biệt HTTP 404 Not Found và 410 Gone trong tình huống tài nguyên từng tồn tại ra sao?
Bạn chọn HTTP 409 Conflict hay 412 Precondition Failed khi xảy ra xung đột cập nhật dựa trên điều kiện nào?
Bạn sẽ diễn giải thông tin trong response HTTP 429 Too Many Requests để quyết định thời điểm thử lại như thế nào?
Bạn phân biệt 500, 502, 503 và 504 khi một reverse proxy giao tiếp với dịch vụ phía sau như thế nào?
Bạn đề xuất cấu trúc error response nào giúp client phân biệt lỗi đầu vào, lỗi xác thực và lỗi server mà không dựa vào chuỗi thông báo?
Bạn giải thích cách trình duyệt hoặc proxy quyết định lưu lại và sử dụng một HTTP response từ cache như thế nào?
Bạn so sánh Cache-Control: no-store và Cache-Control: no-cache về hành vi lưu trữ và xác thực lại dữ liệu ra sao?
Bạn phân biệt Cache-Control: private và public đối với phản hồi có thông tin riêng của người dùng như thế nào?
Bạn giải thích tác dụng của max-age, Age và Expires khi đánh giá một response cache còn mới hay đã cũ ra sao?
Bạn mô tả cách ETag và If-None-Match tham gia vào một conditional GET dẫn đến HTTP 304 như thế nào?
Bạn so sánh Last-Modified và If-Modified-Since với ETag và If-None-Match về độ chính xác của việc xác thực cache như thế nào?
Bạn giải thích vì sao phản hồi HTTP 304 thường không có response body và client cần kết hợp nó với dữ liệu nào?
Bạn sẽ dùng If-Match kết hợp ETag để tránh ghi đè thay đổi của người dùng khác như thế nào?
Bạn phân biệt cache trên trình duyệt, proxy và CDN trong đường đi của một HTTP response ra sao?
Bạn sẽ điều tra trường hợp người dùng tiếp tục nhận nội dung cũ sau khi server đã cập nhật dữ liệu như thế nào?
Bạn giải thích vai trò của Cookie và Set-Cookie trong việc duy trì trạng thái ứng dụng trên nền HTTP ra sao?
Bạn phân tích tác dụng của các thuộc tính Secure, HttpOnly và SameSite đối với cookie như thế nào?
Bạn phân biệt cơ chế gửi cookie tự động với header Authorization trong yêu cầu HTTP như thế nào?
Bạn giải thích Origin header và cơ chế CORS khi frontend gọi API khác origin ra sao?
Bạn sẽ phân biệt một CORS preflight bị từ chối với request thực tế trả lỗi HTTP như thế nào?
Bạn phân biệt các giới hạn bảo mật do trình duyệt áp dụng với khả năng gọi HTTP trực tiếp từ công cụ dòng lệnh ra sao?
Bạn giải thích mục đích của header Range và phản hồi 206 Partial Content khi tải tệp lớn như thế nào?
Bạn sẽ kiểm tra Content-Range khi client tải tiếp một tệp đã bị gián đoạn để tránh ghép sai dữ liệu ra sao?
Bạn thiết kế timeout ở client và cách phản hồi khi server mất quá lâu để gửi dữ liệu như thế nào?
Bạn phân biệt lỗi DNS, từ chối kết nối, timeout và nhận response HTTP 503 bằng các dấu hiệu quan sát nào?
Bạn đánh giá rủi ro của việc client tự động retry request POST sau khi mất kết nối mà chưa biết server đã xử lý hay chưa ra sao?
Bạn quyết định khi nào client có thể retry request GET và lựa chọn backoff dựa trên loại lỗi như thế nào?
Bạn sẽ phân tích trường hợp client chỉ nhận được một phần HTTP response rồi kết nối bị ngắt như thế nào?
Bạn giải thích vai trò của reverse proxy và load balancer trong việc chuyển tiếp HTTP request-response ra sao?
Bạn sẽ xác định địa chỉ client và giao thức gốc khi request đi qua proxy dựa trên header chuyển tiếp và cấu hình tin cậy như thế nào?
Bạn sử dụng DevTools của trình duyệt để quan sát method, URL, status, request header, response header và timing ra sao?
Bạn dùng công cụ dòng lệnh như curl để tái hiện một HTTP request có header và body cụ thể như thế nào?
Bạn sẽ đọc một bản ghi HTTP thô để phân biệt lỗi do header, body hay status code bằng trình tự nào?
Bạn giải thích thông tin nào trong server log hoặc request ID giúp đối chiếu một yêu cầu HTTP với phản hồi mà client nhận được?
Bạn xác định nguyên nhân của phản hồi chậm bằng cách phân tích thời gian DNS, kết nối, TLS và chờ byte đầu tiên như thế nào?
Khi server trả JSON nhưng client không giải mã được, bạn sẽ kiểm tra Content-Type, encoding và body theo trình tự nào?
Khi người dùng báo lỗi chuyển hướng liên tục sau đăng nhập, bạn sẽ kiểm tra status code, Location và cookie như thế nào?
Khi một API hoạt động qua HTTP/1.1 nhưng lỗi qua HTTP/2, bạn sẽ khoanh vùng sự khác biệt về kết nối, header và thành phần trung gian ra sao?
Bạn sẽ hướng dẫn một đồng nghiệp phân tích một lần gọi HTTP thất bại từ URL đầu vào đến response cuối cùng theo những bước nào?
