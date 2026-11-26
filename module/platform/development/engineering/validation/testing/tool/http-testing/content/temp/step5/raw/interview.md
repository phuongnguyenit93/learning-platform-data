Bạn sẽ xác định phạm vi kiểm thử HTTP từ request đến response cho một API Java trước khi chọn công cụ như thế nào?
Bạn sẽ phân biệt ý nghĩa và tình huống sử dụng GET, POST, PUT, PATCH và DELETE trong thiết kế test case ra sao?
Bạn sẽ kiểm chứng đặc tính an toàn và idempotent của một HTTP method bằng nhiều lần gọi lặp lại như thế nào?
Bạn sẽ thiết kế kiểm thử cho đường dẫn có path parameter, query parameter và ký tự cần URL encoding ra sao?
Bạn sẽ xác minh API xử lý tham số truy vấn trùng, thiếu, thừa hoặc sai định dạng theo hợp đồng như thế nào?
Bạn sẽ lựa chọn status code mong đợi cho thao tác tạo, cập nhật và xóa tài nguyên dựa trên hành vi thực tế ra sao?
Bạn sẽ kiểm tra sự khác nhau giữa phản hồi 200, 201, 202 và 204 trong một luồng nghiệp vụ như thế nào?
Bạn sẽ xác minh header Location trong phản hồi tạo tài nguyên dẫn đến tài nguyên vừa được tạo đúng như thế nào?
Bạn sẽ phân biệt lỗi đầu vào không hợp lệ, chưa xác thực, không đủ quyền và không tìm thấy tài nguyên qua status code như thế nào?
Bạn sẽ kiểm tra phản hồi 400, 404, 409 và 422 theo quy ước lỗi đã được API công bố ra sao?
Bạn sẽ xác minh status 401 và header xác thực liên quan khi request thiếu hoặc dùng thông tin xác thực sai như thế nào?
Bạn sẽ thiết kế kiểm thử 403 để bảo đảm người dùng đã xác thực vẫn không truy cập tài nguyên vượt quyền ra sao?
Bạn sẽ đánh giá tình huống API cố ý che giấu sự tồn tại tài nguyên bằng mã 404 nhằm tránh lộ thông tin như thế nào?
Bạn sẽ dùng curl để tái hiện chính xác method, URL, header và body của một request gây lỗi như thế nào?
Bạn sẽ sử dụng tùy chọn hiển thị header và thời gian phản hồi của curl để điều tra lỗi HTTP ra sao?
Bạn sẽ tổ chức collection Postman theo môi trường và biến cấu hình để tránh gắn cứng URL hoặc token như thế nào?
Bạn sẽ tạo assertion trên status, header và JSON body trong Postman để chạy lặp lại các kịch bản kiểm thử ra sao?
Bạn sẽ quyết định khi nào dùng REST Assured để kiểm thử HTTP ở mức tích hợp ứng dụng Java như thế nào?
Bạn sẽ cấu hình REST Assured để gửi request có query, path, header, cookie và JSON body đúng yêu cầu ra sao?
Bạn sẽ dùng MockMvc để kiểm thử lớp web Spring MVC và xác định những phần của hệ thống không được kiểm chứng trong test này như thế nào?
Bạn sẽ lựa chọn WebTestClient khi cần kiểm thử endpoint WebFlux hoặc gọi một dịch vụ đang chạy như thế nào?
Bạn sẽ so sánh kiểm thử bằng MockMvc, WebTestClient và HTTP client thật theo mức độ tin cậy và tốc độ phản hồi ra sao?
Bạn sẽ xác minh Content-Type và Accept để phát hiện sai sót trong content negotiation như thế nào?
Bạn sẽ kiểm chứng cách API phản hồi khi nhận Content-Type không được hỗ trợ hoặc không thể trả định dạng client yêu cầu ra sao?
Bạn sẽ kiểm tra body JSON theo kiểu dữ liệu, trường bắt buộc, trường tùy chọn và cấu trúc lồng nhau như thế nào?
Bạn sẽ quyết định so khớp toàn bộ JSON hay chỉ kiểm tra những trường thuộc hợp đồng để tránh test mong manh ra sao?
Bạn sẽ phân biệt giá trị null, thuộc tính vắng mặt và collection rỗng khi kiểm chứng response JSON ra sao?
Bạn sẽ xác minh cơ chế phân trang, sắp xếp và lọc trả dữ liệu đúng mà không bỏ sót hoặc lặp bản ghi ra sao?
Bạn sẽ kiểm tra hành vi của API với nội dung request rỗng, JSON sai cú pháp và giá trị biên như thế nào?
Bạn sẽ kiểm chứng thông báo lỗi có mã máy đọc được và đủ thông tin cho client nhưng không lộ dữ liệu nội bộ ra sao?
Bạn sẽ xây dựng phép thử xác thực với bearer token hoặc cookie phiên mà không đưa thông tin bí mật vào mã kiểm thử như thế nào?
Bạn sẽ thiết kế ma trận kiểm thử phân quyền theo vai trò, tài nguyên và hành động để phát hiện lỗi kiểm soát truy cập ra sao?
Bạn sẽ kiểm tra trường hợp người dùng tự thay ID trên URL để truy cập tài nguyên của người khác như thế nào?
Bạn sẽ kiểm chứng cookie có thuộc tính Secure, HttpOnly và SameSite phù hợp với ngữ cảnh ứng dụng ra sao?
Bạn sẽ thiết kế kiểm thử cho cơ chế chống CSRF khi API sử dụng cookie làm thông tin xác thực như thế nào?
Bạn sẽ xác minh phản hồi CORS và preflight OPTIONS có cho phép đúng origin, method và header dự kiến ra sao?
Bạn sẽ kiểm tra kết nối HTTPS, xác thực chứng chỉ và hành vi chuyển hướng HTTP sang HTTPS như thế nào?
Bạn sẽ xác minh API không để lộ token, dữ liệu cá nhân hoặc thông tin nhạy cảm trong response header và body như thế nào?
Bạn sẽ thiết kế kiểm thử cho ETag hoặc Last-Modified để xác nhận xử lý request có điều kiện như thế nào?
Bạn sẽ kiểm chứng Cache-Control và hành vi trả 304 để tránh đọc nội dung đã thay đổi từ cache cũ ra sao?
Bạn sẽ kiểm tra cập nhật đồng thời bằng If-Match hoặc phiên bản tài nguyên để phát hiện ghi đè dữ liệu như thế nào?
Bạn sẽ kiểm chứng hành vi 429, Retry-After và giới hạn tốc độ khi gửi nhiều request trong khoảng ngắn ra sao?
Bạn sẽ thiết kế phép thử timeout, mất kết nối hoặc lỗi 5xx mà không khiến test phụ thuộc vào dịch vụ bên ngoài như thế nào?
Bạn sẽ kiểm tra chính sách retry của HTTP client để tránh gửi trùng thao tác làm thay đổi trạng thái như thế nào?
Bạn sẽ kiểm chứng quy trình xử lý bất đồng bộ khi API trả 202 và cung cấp cơ chế theo dõi trạng thái công việc ra sao?
Bạn sẽ xử lý cách kiểm thử upload/download khi body là tệp lớn, dữ liệu nhị phân hoặc luồng nhiều phần như thế nào?
Bạn sẽ tạo dữ liệu và dọn dẹp tài nguyên sau test HTTP sao cho các lần chạy song song không tác động lẫn nhau ra sao?
Bạn sẽ xác định log và bằng chứng cần lưu khi phép thử HTTP thất bại mà vẫn che giấu token và cookie nhạy cảm như thế nào?
Bạn sẽ tổ chức test HTTP trong CI để cấu hình môi trường, seed dữ liệu và điều kiện sẵn sàng của dịch vụ có thể tái lập ra sao?
Bạn sẽ điều tra tình huống API vượt qua MockMvc test nhưng thất bại khi gọi HTTPS thật do reverse proxy, header hoặc cấu hình mạng như thế nào?
