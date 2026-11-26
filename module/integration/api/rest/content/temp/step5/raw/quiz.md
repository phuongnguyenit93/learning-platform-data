Câu 01. Thiết kế URI để định danh đơn hàng có mã o-42 theo hướng resource, lựa chọn nào phù hợp nhất?
A. Dùng `/getOrder/o-42` để biểu diễn thao tác đọc
B. Dùng `/orders/find/o-42` để gọi chức năng tìm
C. Dùng `/actions/orders/o-42` để gom các lệnh
D. Dùng `/orders/o-42` để định danh một đơn hàng
Đáp án đúng: D

Câu 02. Phát biểu nào thể hiện đúng tính safe của phương thức GET trong HTTP?
A. GET có thể tạo resource khi server phản hồi mã 201
B. GET yêu cầu đọc mà không chủ đích sửa trạng thái
C. GET có thể cập nhật dữ liệu nếu request không mang body
D. GET có thể xóa resource nhờ query `delete=true`
Đáp án đúng: B

Câu 03. Khi thiết kế PUT để cập nhật một resource tại URI xác định, ý nghĩa chính là gì?
A. Thay thế trạng thái resource theo biểu diễn gửi lên
B. Chỉ nối trường mới vào resource và giữ mọi trường cũ
C. Luôn thêm một phần tử vào collection hiện tại
D. Luôn tạo resource khác với URI do máy chủ tự cấp
Đáp án đúng: A

Câu 04. Phát biểu nào đúng về PATCH so với PUT trong thiết kế REST API?
A. Bảo đảm mọi định dạng PATCH đều idempotent
B. Yêu cầu tạo một URI mới sau mỗi lần cập nhật
C. Thay thế toàn bộ resource bằng biểu diễn hoàn chỉnh
D. Áp dụng thay đổi một phần theo patch document
Đáp án đúng: D

Câu 05. POST /orders đã tạo xong một đơn hàng mới; phản hồi nào giúp client biết URI resource mới rõ nhất?
A. Trả `200 OK` và để client suy ra URI từ request
B. Trả `204 No Content` và dùng `ETag` như URI mới
C. Trả `201 Created` kèm `Location` resource mới
D. Trả `202 Accepted` dù không còn tác vụ chờ xử lý
Đáp án đúng: C

Câu 06. Vì sao DELETE được xem là phương thức idempotent theo ngữ nghĩa HTTP?
A. Vì DELETE không cần xác thực hay kiểm tra quyền
B. Lặp DELETE không đổi tác động cuối lên resource
C. Vì các lần DELETE phải trả cùng một HTTP status
D. Vì server luôn phục hồi resource sau khi xóa xong
Đáp án đúng: B

Câu 07. Yêu cầu xuất báo cáo mới được nhận vào hàng đợi, chưa xử lý xong và chưa tạo resource kết quả; nên trả gì?
A. Trả `200 OK` vì server đã nhận được yêu cầu
B. Trả `201 Created` vì báo cáo đã sẵn sàng
C. Trả `202 Accepted` vì xử lý vẫn chưa hoàn tất
D. Trả `204 No Content` vì kết quả chưa có body
Đáp án đúng: C

Câu 08. Khi endpoint trả trạng thái 204 No Content, phần response body phải thế nào?
A. Gửi JSON rỗng `{}` để client xác nhận response
B. Gửi JSON `null` để client vẫn parse được dữ liệu
C. Không gửi bất kỳ nội dung nào trong phần body
D. Luôn gửi chuỗi rỗng có `Content-Type` là JSON
Đáp án đúng: C

Câu 09. Client gửi JSON lỗi cú pháp nên server không thể phân tích request body, mã nào phù hợp nhất?
A. `415 Unsupported Media Type` vì loại body không hỗ trợ
B. `400 Bad Request` vì cú pháp request không hợp lệ
C. `409 Conflict` vì dữ liệu xung đột trạng thái
D. `422 Unprocessable Content` vì vi phạm nghiệp vụ
Đáp án đúng: B

Câu 10. Endpoint yêu cầu Bearer authentication nhưng client không cung cấp token; phản hồi thông thường là gì?
A. `404 Not Found` vì không xác minh được danh tính
B. `409 Conflict` vì token xung đột với trạng thái
C. `403 Forbidden` vì thiếu quyền trên từng resource
D. `401 Unauthorized` kèm header `WWW-Authenticate`
Đáp án đúng: D

Câu 11. Client đã được xác thực nhưng không có quyền xem báo cáo; mã nào phản ánh rõ nhất việc từ chối quyền?
A. `422 Unprocessable Content` vì JSON sai cấu trúc
B. `404 Not Found` vì báo cáo chắc chắn chưa tồn tại
C. `401 Unauthorized` vì client chưa được xác thực
D. `403 Forbidden` vì không có quyền đọc báo cáo
Đáp án đúng: D

Câu 12. Resource /invoices/7 tồn tại nhưng không hỗ trợ PATCH; cặp status và header nào phù hợp?
A. `405 Method Not Allowed` kèm header `Allow`
B. `409 Conflict` đi kèm header `Location`
C. `415 Unsupported Media Type` kèm `Accept`
D. `404 Not Found` đi kèm header `ETag`
Đáp án đúng: A

Câu 13. Client muốn chỉnh sửa đơn hàng đã khóa, xung đột với trạng thái hiện tại; mã nào phù hợp?
A. `400 Bad Request` khi URI sai cấu trúc cú pháp
B. `409 Conflict` do sửa trái trạng thái đơn hàng
C. `404 Not Found` khi đơn hàng hoàn toàn không có
D. `503 Service Unavailable` khi dịch vụ tạm ngưng
Đáp án đúng: B

Câu 14. API giới hạn 100 request mỗi phút và client đã vượt mức; phản hồi nào phù hợp?
A. `429 Too Many Requests` do client vượt quota
B. `408 Request Timeout` kèm thời gian xử lý cũ
C. `403 Forbidden` kèm ETag của response bị chặn
D. `503 Service Unavailable` kèm URI của resource
Đáp án đúng: A

Câu 15. Server gặp lỗi nội bộ không mong muốn khi xử lý một request hợp lệ; mã nào phản ánh lỗi đó?
A. `409 Conflict` vì trạng thái resource xung đột
B. `400 Bad Request` vì payload sai cú pháp request
C. `500 Internal Server Error` do lỗi phía server
D. `429 Too Many Requests` vì client vượt hạn mức
Đáp án đúng: C

Câu 16. GET kèm If-None-Match với ETag vẫn khớp biểu diễn hiện tại; server nên phản hồi thế nào?
A. `304 Not Modified` và không gửi response body
B. `206 Partial Content` và chỉ gửi trường khác biệt
C. `412 Precondition Failed` và yêu cầu gửi lại
D. `200 OK` và trả lại toàn bộ representation cũ
Đáp án đúng: A

Câu 17. Client gửi PUT kèm If-Match chứa ETag cũ, không còn khớp resource; mã nào phù hợp?
A. `428 Precondition Required` dù đã có If-Match
B. `409 Conflict` là mã bắt buộc cho mọi ETag cũ
C. `304 Not Modified` vì client đã giữ bản sao cũ
D. `412 Precondition Failed` vì điều kiện không khớp
Đáp án đúng: D

Câu 18. Response chứa dữ liệu riêng và yêu cầu không cache nào được lưu lại; Cache-Control nào phù hợp?
A. `Cache-Control: max-age=3600` để giữ response lâu
B. `Cache-Control: no-store` để ngăn lưu response
C. `Cache-Control: public` để cache dùng chung response
D. `Cache-Control: no-cache` để cấm hoàn toàn lưu trữ
Đáp án đúng: B

Câu 19. POST thanh toán có thể bị client gửi lại do timeout; làm sao giảm nguy cơ tạo hai giao dịch?
A. Đổi POST thành GET để cache loại yêu cầu trùng
B. Giữ nguyên idempotency key cho cùng giao dịch
C. Tăng timeout client đến khi request chắc chắn xong
D. Tạo request ID khác nhau cho mỗi lần client retry
Đáp án đúng: B

Câu 20. Nhược điểm nào có thể gặp khi dùng offset pagination trên tập dữ liệu thường xuyên thêm hoặc xóa?
A. Thay đổi giữa các trang có thể gây trùng hoặc sót
B. Offset luôn làm API trả mã 429 khi dữ liệu lớn
C. Không cần sort thì thứ tự trang vẫn luôn ổn định
D. Offset buộc API phải bỏ hết điều kiện lọc dữ liệu
Đáp án đúng: A

Câu 21. Khi nào cursor pagination thường hữu ích hơn offset pagination cho một feed cập nhật liên tục?
A. Khi cần tiếp tục từ mốc trong thứ tự xác định
B. Khi cần mọi trang luôn có đúng số item cố định
C. Khi cần truy cập thẳng trang N mà không cần sort
D. Khi muốn thay thế hoàn toàn filter của collection
Đáp án đúng: A

Câu 22. Để cursor pagination không mơ hồ khi nhiều bản ghi cùng createdAt, nên sắp xếp thế nào?
A. Chỉ sort theo createdAt và bỏ qua mọi giá trị trùng
B. Dùng offset thay cho sort để giữ trang cố định
C. Sort theo createdAt rồi thêm ID làm khóa phân định
D. Đảo thứ tự sort ngẫu nhiên khi lấy trang tiếp theo
Đáp án đúng: C

Câu 23. URI nào diễn đạt collection đơn hàng với query parameter cho lọc trạng thái và sắp xếp?
A. `/orders/action?status=pending&sort=createdAt`
B. `/orders/filter/pending/sort/createdAt`
C. `/orders?status=pending&sort=createdAt`
D. `/getOrders?state=pending&order=createdAt`
Đáp án đúng: C

Câu 24. API thêm một trường tùy chọn vào JSON response nhưng giữ nguyên các trường cũ; đánh giá nào đúng?
A. Luôn làm hỏng mọi client bất kể cách parse JSON
B. Thường tương thích với client bỏ qua trường lạ
C. Buộc client phải thay HTTP method của yêu cầu
D. Bắt buộc chuyển tất cả endpoint sang version mới
Đáp án đúng: B

Câu 25. Muốn bỏ một trường response mà client cũ đang phụ thuộc, cách xử lý thay đổi hợp lý là gì?
A. Đánh giá breaking change và công bố lộ trình phiên bản
B. Đổi mã 200 thành 204 để client tự xử lý thiếu trường
C. Giữ URI cũ và âm thầm thay schema response hiện tại
D. Xóa trường ngay rồi chỉ cập nhật phần mô tả API
Đáp án đúng: A

Câu 26. Trong Problem Details dạng application/problem+json, field nào chứa mã trạng thái HTTP dạng số nếu được cung cấp?
A. `title` chứa URL định danh cho loại lỗi tương ứng
B. `status` chứa mã HTTP dạng số của phản hồi lỗi
C. `instance` chứa toàn bộ request body gây ra lỗi
D. `type` chứa mã HTTP ở dạng URI của lỗi phát sinh
Đáp án đúng: B

Câu 27. Trong OpenAPI, mô tả operation POST /orders và schema dùng chung được tổ chức phù hợp thế nào?
A. `externalDocs` chứa method; schema nằm trong `paths`
B. `servers` chứa operation; schema nằm trong `security`
C. `tags` chứa request body; schema nằm trong `info`
D. `paths` chứa operation; schema có thể nằm ở `components`
Đáp án đúng: D

Câu 28. Khi thay implementation của REST API, kiểm thử nào trực tiếp phát hiện response lệch hợp đồng OpenAPI?
A. Smoke test chỉ kiểm tra endpoint có trả mã 2xx
B. Load test đo throughput khi traffic tăng liên tục
C. Unit test riêng thuật toán sắp xếp ở repository
D. Contract test so status và response với API contract
Đáp án đúng: D

Câu 29. API có issuer và audience xác định cho JWT Bearer; server cần kiểm tra token thế nào?
A. Chỉ giải mã payload để lấy role client tự khai
B. Chuyển JWT vào query string để tự động xác thực
C. Kiểm tra chữ ký, hạn dùng, issuer và audience
D. Tin mọi thuật toán ghi trong header do client gửi
Đáp án đúng: C

Câu 30. Để chống Broken Object Level Authorization trên GET /orders/123, server cần làm gì?
A. Chỉ kiểm tra token có chữ ký của issuer tin cậy
B. Kiểm tra principal có quyền với đơn hàng 123
C. Chỉ dùng mã UUID khó đoán thay cho số đơn hàng
D. Chỉ giới hạn tần suất các request cho mỗi IP
Đáp án đúng: B

Câu 31. Client có JWT hợp lệ nhưng thiếu quyền admin để gọi endpoint quản trị; xử lý thông thường là gì?
A. Trả 200 với body đánh dấu thao tác bị từ chối
B. Trả 404 bắt buộc và bỏ kiểm tra quyền truy cập
C. Trả 401 để buộc client xác thực lại từ đầu
D. Trả 403 vì danh tính đã xác thực nhưng thiếu quyền
Đáp án đúng: D

Câu 32. Khi API giới hạn request theo tài khoản đã đăng nhập, khóa đếm rate limit nên dựa trên gì?
A. Chỉ dựa vào mã trạng thái của request trước
B. Chỉ dựa vào URI mà mọi tài khoản cùng gọi
C. Định danh principal đã xác thực của request
D. Chỉ dựa vào User-Agent do client tự cung cấp
Đáp án đúng: C

Câu 33. Browser gửi cross-origin PUT kèm Authorization; request preflight thông thường là gì?
A. `HEAD` kèm bearer token để kiểm tra cache từ xa
B. `TRACE` nhằm kiểm tra từng proxy trên đường đi
C. `OPTIONS` kèm `Origin` và method dự kiến trong header
D. `GET` để tự xác thực toàn bộ URI trước khi sửa
Đáp án đúng: C

Câu 34. Client chỉ chấp nhận XML qua Accept, server chỉ hỗ trợ JSON và chọn từ chối thương lượng; mã nào phù hợp?
A. `406 Not Acceptable` vì không có biểu diễn được chấp nhận
B. `400 Bad Request` khi không parse được query string
C. `415 Unsupported Media Type` khi body sai loại dữ liệu
D. `404 Not Found` khi resource không tìm thấy trên server
Đáp án đúng: A

Câu 35. Client POST XML vào endpoint chỉ chấp nhận JSON, Content-Type là application/xml; mã nào phù hợp?
A. `406 Not Acceptable` vì client không chấp nhận JSON
B. `422 Unprocessable Content` vì dữ liệu sai nghiệp vụ
C. `500 Internal Server Error` vì server không hiểu body
D. `415 Unsupported Media Type` vì body sai media type
Đáp án đúng: D

Câu 36. Để truy dấu một request qua gateway và nhiều service, cơ chế nào hữu ích nhất?
A. Ghi Authorization header đầy đủ vào mọi dòng log
B. Chỉ lưu response body mà bỏ status và timestamp
C. Đặt User-Agent ngẫu nhiên tại mỗi service trung gian
D. Truyền trace ID xuyên suốt và log cùng định danh
Đáp án đúng: D

Câu 37. Kiểm thử HTTP cho POST /orders bằng Spring, cách nào xác minh resource được tạo đúng?
A. Chỉ kiểm tra log có thông điệp bắt đầu tạo đơn
B. Gọi endpoint, assert 201, Location và dữ liệu lưu
C. Chỉ assert hàm service trả object mà không gọi HTTP
D. Chỉ đo response time khi chưa kiểm tra dữ liệu
Đáp án đúng: B

Câu 38. Trong Spring MVC, muốn từ chối request DTO vi phạm @NotBlank, cách thông dụng là gì?
A. Gắn `@Cacheable` để phát hiện dữ liệu request sai
B. Gắn `@Transactional` lên controller để validate body
C. Gắn `@Valid` vào DTO tham số và xử lý validation error
D. Gắn `@Async` rồi trả lỗi sau khi lưu bản ghi
Đáp án đúng: C

Câu 39. Để hạn chế hai client đồng thời ghi đè thay đổi của nhau khi cập nhật tồn kho, nên dùng gì?
A. Version/ETag với precondition hoặc optimistic locking
B. Cookie chung cố định để chia sẻ trạng thái các client
C. `Cache-Control: public` trong mọi request cập nhật
D. HTTP redirect 302 cho cả hai transaction cạnh tranh
Đáp án đúng: A

Câu 40. Dịch vụ tạm bảo trì vài phút; cách phản hồi nào giúp client retry phù hợp?
A. `503 Service Unavailable` kèm `Retry-After`
B. `408 Request Timeout` kèm ETag của dữ liệu trước
C. `301 Moved Permanently` kèm `Cache-Control: public`
D. `500 Internal Server Error` với `Location` của resource
Đáp án đúng: A
