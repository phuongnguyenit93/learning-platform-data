Câu 1. Trong tích hợp hệ thống, API đóng vai trò hợp đồng giao tiếp như thế nào?
A. Công bố sơ đồ triển khai máy chủ nội bộ
B. Quy định cách tổ chức mã nguồn của các bên
C. Công bố cách gọi, dữ liệu vào ra và mã lỗi
D. Quy định cơ chế lưu trữ dữ liệu của các bên
Đáp án đúng: C

Câu 2. Mô hình request-response đồng bộ có đặc trưng nào?
A. Server thông báo thay đổi mà không có yêu cầu mới
B. Client gửi yêu cầu rồi chờ phản hồi của server
C. Client đăng ký sự kiện để nhận thông báo về sau
D. Client gửi thông điệp và xử lý kết quả qua hàng đợi
Đáp án đúng: B

Câu 3. Khi xây API hướng tài nguyên, cách thiết kế đường dẫn thường phù hợp nhất là gì?
A. Dùng danh từ biểu diễn tài nguyên và tập tài nguyên
B. Dùng tên thao tác cơ sở dữ liệu làm đường dẫn
C. Dùng tên hành động làm định danh cho mỗi tài nguyên
D. Dùng mã trạng thái HTTP làm tên của từng tài nguyên
Đáp án đúng: A

Câu 4. Đặc điểm nào phù hợp với phương thức GET của HTTP?
A. Yêu cầu ghi đè toàn bộ tài nguyên đang tồn tại
B. Yêu cầu xóa tài nguyên sau khi đọc thành công
C. Yêu cầu tạo thêm tài nguyên sau mỗi lần truy cập
D. Yêu cầu lấy biểu diễn mà không chủ đích sửa dữ liệu
Đáp án đúng: D

Câu 5. Khi server cấp ID cho đơn hàng mới, request nào thường phù hợp?
A. GET /orders với dữ liệu đơn hàng trong body
B. POST /orders với dữ liệu đơn hàng trong body
C. PUT /orders với dữ liệu đơn hàng trong body
D. PATCH /orders với dữ liệu đơn hàng trong body
Đáp án đúng: B

Câu 6. Với PUT đến URI đã xác định, mô tả nào sát với ngữ nghĩa HTTP?
A. Thay trạng thái tài nguyên tại URI đã chỉ định
B. Đổi một số trường theo một tài liệu cập nhật
C. Tìm tài nguyên dựa vào tham số lọc trong URI
D. Thêm một bản ghi mới sau mỗi lần gửi lại request
Đáp án đúng: A

Câu 7. Khi chỉ muốn áp dụng các thay đổi một phần lên tài nguyên, nên chọn cách nào?
A. Dùng HEAD để ghi lại phần metadata thay đổi
B. Dùng GET với danh sách trường cần được sửa
C. Dùng PATCH với nội dung mô tả các thay đổi
D. Dùng POST với toàn bộ dữ liệu tài nguyên hiện có
Đáp án đúng: C

Câu 8. Tính idempotent của DELETE được hiểu như thế nào?
A. Gửi lại DELETE sẽ không được ghi vào access log
B. Gửi lại DELETE sẽ phục hồi bản ghi đã xóa
C. Gửi lại DELETE trả cùng mã phản hồi ở từng lần
D. Gửi lại DELETE có cùng hiệu ứng mong muốn cuối
Đáp án đúng: D

Câu 9. CORS trên trình duyệt chủ yếu kiểm soát điều gì?
A. Thứ tự xử lý các request trong một HTTP session
B. Kiểu JSON mà server có thể gửi cho client
C. Quyền của API key đối với từng bản ghi dữ liệu
D. Quyền mã web ở origin khác truy cập phản hồi
Đáp án đúng: D

Câu 10. HEAD khác GET chủ yếu ở điểm nào theo HTTP?
A. Yêu cầu đổi trạng thái trước khi đọc tài nguyên
B. Yêu cầu nhận một phiên bản mới của tài nguyên
C. Nhận headers tương ứng GET mà không có body
D. Yêu cầu cấp thêm phiên làm việc cho client
Đáp án đúng: C

Câu 11. HTTP 200 OK thường biểu thị kết quả nào?
A. Yêu cầu đã được xử lý thành công
B. Server không gửi nội dung trong phản hồi
C. Tài nguyên đã được tạo tại URI mới
D. Yêu cầu đã được nhận để xử lý về sau
Đáp án đúng: A

Câu 12. Khi POST tạo tài nguyên thành công, mã nào thường phù hợp nhất?
A. 202 Accepted cho biết đã nhận tác vụ nền
B. 204 No Content cho biết không có phần nội dung
C. 201 Created cho biết tài nguyên đã được tạo
D. 200 OK cho biết đã đọc tài nguyên hiện hữu
Đáp án đúng: C

Câu 13. Nếu API chỉ tiếp nhận một tác vụ và sẽ xử lý sau, mã nào phù hợp?
A. 204 No Content cho biết đã xong việc không body
B. 202 Accepted cho biết yêu cầu đã được nhận
C. 200 OK cho biết xử lý đồng bộ đã hoàn tất
D. 201 Created cho biết tài nguyên đã tồn tại
Đáp án đúng: B

Câu 14. Khi xử lý thành công và không cần trả body, mã nào thường phù hợp?
A. 204 No Content với phần body phản hồi rỗng
B. 201 Created kèm vị trí tài nguyên mới
C. 202 Accepted dành cho một tác vụ xử lý nền
D. 200 OK cùng nội dung biểu diễn tài nguyên
Đáp án đúng: A

Câu 15. Khi JSON gửi lên sai định dạng khiến server không phân tích được, mã nào phù hợp?
A. 403 Forbidden do client bị từ chối quyền truy cập
B. 401 Unauthorized do client chưa được xác thực
C. 404 Not Found do tài nguyên không được tìm thấy
D. 400 Bad Request do nội dung yêu cầu sai cấu trúc
Đáp án đúng: D

Câu 16. Khi endpoint yêu cầu đăng nhập nhưng client chưa gửi thông tin xác thực, mã nào phù hợp?
A. 403 Forbidden khi danh tính đã có nhưng thiếu quyền
B. 401 Unauthorized khi cần thông tin xác thực hợp lệ
C. 409 Conflict khi trạng thái tài nguyên đang xung đột
D. 400 Bad Request khi thông điệp gửi lên sai cấu trúc
Đáp án đúng: B

Câu 17. Client đã được xác thực nhưng không có quyền đọc tài nguyên, mã nào phù hợp?
A. 409 Conflict khi có phiên bản dữ liệu mới hơn
B. 403 Forbidden khi quyền truy cập không được cấp
C. 401 Unauthorized khi cần xác thực lại danh tính
D. 404 Not Found khi đường dẫn không được định nghĩa
Đáp án đúng: B

Câu 18. Client yêu cầu một URI không có tài nguyên tương ứng; phản hồi nào thường đúng?
A. 409 Conflict vì tài nguyên đã có phiên bản khác
B. 422 Unprocessable Content vì server không đủ quyền
C. 404 Not Found vì tài nguyên được yêu cầu không có
D. 400 Bad Request vì đường dẫn chưa được khai báo
Đáp án đúng: C

Câu 19. Hai client cùng cập nhật bản ghi dẫn đến xung đột trạng thái; mã nào có thể phù hợp?
A. 409 Conflict khi yêu cầu xung đột trạng thái
B. 429 Too Many Requests khi client gửi quá nhanh
C. 401 Unauthorized khi thiếu thông tin đăng nhập
D. 404 Not Found khi bản ghi đã bị đổi cấu trúc
Đáp án đúng: A

Câu 20. Client vượt giới hạn tần suất request đã công bố; mã nào phù hợp?
A. 429 Too Many Requests khi vượt mức gọi được phép
B. 408 Request Timeout khi client gửi yêu cầu chậm
C. 503 Service Unavailable khi backend bảo trì
D. 412 Precondition Failed khi ETag không khớp
Đáp án đúng: A

Câu 21. Khi server tạm ngừng phục vụ do quá tải, mã nào thường phù hợp?
A. 409 Conflict vì dữ liệu giữa các bản ghi mâu thuẫn
B. 503 Service Unavailable vì dịch vụ chưa sẵn sàng
C. 400 Bad Request vì nội dung yêu cầu không hợp lệ
D. 404 Not Found vì tài nguyên không hiện diện
Đáp án đúng: B

Câu 22. Content-Type trong HTTP request cho biết thông tin gì?
A. Các ngôn ngữ mà client muốn dùng khi hiển thị
B. Phiên bản hợp đồng API mà client đang hỗ trợ
C. Những định dạng response mà client ưu tiên nhận
D. Kiểu media của phần nội dung request được gửi
Đáp án đúng: D

Câu 23. Client muốn ưu tiên nhận phản hồi JSON thì header nào phù hợp?
A. Cache-Control: application/json để chọn loại bộ nhớ đệm
B. Content-Type: application/json để định dạng body gửi
C. Authorization: application/json để nêu cách xác thực
D. Accept: application/json để nêu định dạng mong nhận
Đáp án đúng: D

Câu 24. Trong schema của request, yêu cầu một thuộc tính bắt buộc có ý nghĩa gì?
A. Thuộc tính cần khác null dù schema cho phép null
B. Thuộc tính trở thành tham số trên URL của request
C. Thuộc tính phải hiện diện khi request theo schema đó
D. Thuộc tính có thể xuất hiện hoặc vắng mặt tùy client
Đáp án đúng: C

Câu 25. Trong API danh sách đơn hàng, nên phân biệt path và query parameter thế nào?
A. Path xác định tài nguyên, query có thể lọc kết quả
B. Path đặt hạn mức request, query chọn mã HTTP trả về
C. Path mô tả định dạng body, query chọn kiểu xác thực
D. Path chọn phương thức HTTP, query đặt header phản hồi
Đáp án đúng: A

Câu 26. Correlation ID hoặc trace ID giúp điều gì khi theo dõi tích hợp?
A. Tự sắp xếp log của các dịch vụ theo thời gian
B. Theo dấu một yêu cầu khi đi qua nhiều dịch vụ
C. Phát lại request thất bại từ điểm dừng gần nhất
D. Bảo đảm chỉ xử lý một lần các request trùng ID
Đáp án đúng: B

Câu 27. Với danh sách rất lớn và dữ liệu thay đổi liên tục, cursor pagination có ích gì?
A. Ngăn client nhận dữ liệu mới được tạo sau đó
B. Tăng kích thước response để giảm lần gọi API
C. Tiếp tục duyệt dựa trên vị trí do server cấp
D. Cho phép truy cập ngay trang bất kỳ theo số thứ tự
Đáp án đúng: C

Câu 28. Đối với GET /products?category=book&sort=price, tham số query chủ yếu phục vụ gì?
A. Xác định điều kiện lọc và thứ tự trả kết quả
B. Xác định định dạng dữ liệu trong request body
C. Xác định phương thức cập nhật tài nguyên
D. Xác định cách xác thực người dùng gọi API
Đáp án đúng: A

Câu 29. Khi GET có If-None-Match khớp ETag hiện tại, server có thể làm gì?
A. Trả 412 Precondition Failed để client ghi đè
B. Trả 201 Created để client lưu thêm một bản mới
C. Trả 409 Conflict để client xóa bản trong cache
D. Trả 304 Not Modified để client dùng bản đã lưu
Đáp án đúng: D

Câu 30. Khi cập nhật có If-Match với ETag đã cũ, phản hồi nào phù hợp để tránh ghi đè?
A. 200 OK và ghi đè dữ liệu dù ETag không khớp
B. 412 Precondition Failed và không áp dụng ghi
C. 304 Not Modified và thay dữ liệu phía server
D. 201 Created và tạo thêm bản sao của tài nguyên
Đáp án đúng: B

Câu 31. Thay đổi nào dễ phá vỡ client đã tích hợp với API phiên bản cũ?
A. Thêm tài liệu mô tả cho mã lỗi đã công bố
B. Thêm endpoint mới mà client hiện tại chưa gọi
C. Thêm trường tùy chọn vào một JSON response
D. Xóa một trường response mà client đang sử dụng
Đáp án đúng: D

Câu 32. Thay đổi nào thường giữ tương thích với client đọc JSON và bỏ qua trường lạ?
A. Đổi kiểu dữ liệu của trường số thành đối tượng
B. Xóa một giá trị enum mà client đang xử lý
C. Đổi tên trường định danh trong response hiện có
D. Thêm trường không bắt buộc vào response JSON
Đáp án đúng: D

Câu 33. OpenAPI thường hỗ trợ hoạt động nào khi thiết kế hợp đồng API?
A. Mô tả endpoint, tham số, schema và response
B. Phân phối trực tiếp request giữa các cụm backend
C. Tạo logic nghiệp vụ hoàn chỉnh cho các endpoint
D. Quyết định vòng đời và thời hạn hỗ trợ của API
Đáp án đúng: A

Câu 34. Tại sao cần kiểm tra dữ liệu đầu vào ngay tại ranh giới API?
A. Chặn dữ liệu thiếu trường, sai kiểu hoặc quá ngưỡng
B. Bảo đảm request đúng schema sẽ thành công nghiệp vụ
C. Loại bỏ việc kiểm tra quyền truy cập ở tầng dịch vụ
D. Thay thế các ràng buộc toàn vẹn trong cơ sở dữ liệu
Đáp án đúng: A

Câu 35. Dùng HTTPS khi trao đổi dữ liệu API nhằm bảo đảm điều gì chủ yếu?
A. Xác thực danh tính người dùng chỉ nhờ kết nối TLS
B. Mã hóa cả dữ liệu đã được lưu trong cơ sở dữ liệu
C. Ngăn người dùng truy cập tài nguyên trái quyền
D. Mã hóa dữ liệu truyền và xác minh danh tính máy chủ
Đáp án đúng: D

Câu 36. Phát biểu nào phân biệt xác thực và phân quyền trong API?
A. Xác thực cấp quyền, phân quyền kiểm tra token phiên
B. Xác thực nhận diện chủ thể, phân quyền kiểm tra quyền
C. Xác thực kiểm tra scope, phân quyền xác minh phiên
D. Xác thực xét vai trò, phân quyền đối chiếu mật khẩu
Đáp án đúng: B

Câu 37. Khi dịch vụ backend tích hợp API đối tác cần lưu API key, cách nào phù hợp nhất?
A. Lưu khóa trong bảng cấu hình dùng chung không phân quyền
B. Đặt khóa trong file cấu hình đóng gói với ứng dụng
C. Đặt khóa trong kho bí mật và giới hạn quyền đọc
D. Dùng chung một khóa cho môi trường test và production
Đáp án đúng: C

Câu 38. Khi thiết kế retry cho API tích hợp, chính sách nào hợp lý nhất?
A. Gửi đồng thời nhiều bản sao request ngay khi gặp lỗi
B. Đợi phản hồi từ server kể cả khi vượt SLA yêu cầu
C. Retry lỗi tạm thời với backoff và giới hạn số lần
D. Retry lỗi 401 định kỳ mà không đổi thông tin xác thực
Đáp án đúng: C

Câu 39. Idempotency key hữu ích khi client phải thử lại request tạo giao dịch vì lý do gì?
A. Giúp server tự khôi phục lỗi 5xx trong mỗi request
B. Giúp server nhận ra yêu cầu ghi trùng để tránh lặp
C. Giúp server xác thực client thay cho access token
D. Giúp server bỏ qua kiểm tra tính hợp lệ của giao dịch
Đáp án đúng: B

Câu 40. Bên A đã công bố endpoint HTTPS để nhận thay đổi từ B mà không chủ động thăm dò; cách tích hợp nào phù hợp?
A. A mở kết nối SSE đến API do B cung cấp
B. B ghi sự kiện vào cache để A chủ động truy vấn
C. B gửi webhook đến endpoint mà A đã đăng ký
D. A cấu hình định kỳ gọi API của B để đồng bộ
Đáp án đúng: C
