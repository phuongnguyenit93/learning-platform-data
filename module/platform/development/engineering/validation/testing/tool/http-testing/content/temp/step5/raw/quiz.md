Câu 1: Với API REST, GET được xem là method an toàn theo ý nghĩa nào?
A. Chỉ đọc mà không chủ ý đổi trạng thái resource
B. Luôn tạo bản ghi mới khi URL chứa query parameter
C. Luôn ghi audit vào cùng bảng chứa dữ liệu nghiệp vụ
D. Luôn hủy bản ghi cũ nếu resource không tồn tại
Đáp án đúng: A

Câu 2: Khi kiểm thử PUT idempotent, điều nào đúng về hai lần gửi cùng request?
A. HTTP status mọi lần gửi bắt buộc giống hệt nhau
B. Mỗi lần gửi phải sinh thêm một tài nguyên mới
C. Gửi lặp có cùng hiệu ứng dự định trên resource
D. Mỗi lần gửi phải đổi khóa chính của resource
Đáp án đúng: C

Câu 3: Khi POST tạo tài nguyên thành công, tổ hợp response nào thường hợp lý?
A. 204 No Content và Location trỏ tới toàn bộ collection
B. 401 Unauthorized và Set-Cookie chứa mã tài nguyên mới
C. 304 Not Modified và Retry-After cho lần ghi tiếp
D. 201 Created và Location trỏ tới tài nguyên vừa tạo
Đáp án đúng: D

Câu 4: Khi server trả HTTP 202 Accepted, client nên hiểu gì?
A. Dữ liệu chắc chắn đã được ghi xong và đã commit
B. Yêu cầu đã nhận nhưng xử lý có thể chưa hoàn tất
C. Không cần kiểm tra trạng thái tác vụ bất đồng bộ nữa
D. Resource đích chắc chắn đã bị xóa khỏi hệ thống
Đáp án đúng: B

Câu 5: Trong HTTP, khi kiểm tra response 204 No Content nên kỳ vọng gì?
A. Response bắt buộc có JSON chứa mã lỗi rỗng
B. Response bắt buộc có Content-Length lớn hơn 0
C. Response thành công và không có nội dung body
D. Response bắt buộc có Location tới resource mới
Đáp án đúng: C

Câu 6: Request JSON sai cú pháp và không parse được thường cần kiểm tra gì?
A. Status 200 vì server vẫn nhận đủ byte request
B. Status 201 vì JSON đã gửi qua kênh HTTPS
C. Status 304 vì request body chưa được parse
D. Status 400 với body lỗi theo hợp đồng của API
Đáp án đúng: D

Câu 7: Khi request thiếu hoặc có thông tin đăng nhập không hợp lệ, status thường là gì?
A. 401 Unauthorized báo xác thực chưa thành công
B. 403 Forbidden luôn có nghĩa tài khoản chưa tồn tại
C. 409 Conflict luôn có nghĩa access token đã hết hạn
D. 422 Unprocessable Content luôn có nghĩa thiếu token
Đáp án đúng: A

Câu 8: Request đã xác thực nhưng user không có quyền sửa resource, nên test status nào?
A. 403 Forbidden khi bị từ chối vì thiếu quyền
B. 401 Unauthorized chỉ vì role không được cấp
C. 201 Created vì authentication đã thành công
D. 304 Not Modified vì không có thay đổi được lưu
Đáp án đúng: A

Câu 9: Khi tra cứu mã đơn hàng không tồn tại, response nào thường đúng hợp đồng?
A. 200 OK với dữ liệu của một đơn hàng khác
B. 201 Created với ID mới thay cho ID đã hỏi
C. 404 Not Found kèm response lỗi theo hợp đồng
D. 301 Moved Permanently tới endpoint ghi đơn
Đáp án đúng: C

Câu 10: Khi cập nhật sử dụng phiên bản cũ gây xung đột, response nào thường phù hợp?
A. 409 Conflict kèm thông tin xung đột cần xử lý
B. 202 Accepted vì server chưa thể tìm được dữ liệu
C. 404 Not Found vì dữ liệu vẫn tồn tại trên server
D. 304 Not Modified vì server từ chối xác thực
Đáp án đúng: A

Câu 11: Khi endpoint không cho phép method POST, mã nào và header nào thường liên quan?
A. 404 Not Found cùng header Content-Encoding
B. 405 Method Not Allowed cùng header Allow
C. 304 Not Modified cùng header Set-Cookie
D. 200 OK cùng header WWW-Authenticate
Đáp án đúng: B

Câu 12: Header Content-Type trong HTTP request mô tả điều gì?
A. Kiểu media client mong muốn nhận ở response
B. Múi giờ của người dùng gửi request HTTP
C. Kiểu media của phần body trong HTTP request
D. Cách cache endpoint cần phân phối theo vùng
Đáp án đúng: C

Câu 13: Header Accept của request dùng để thể hiện thông tin gì?
A. Kiểu encoding chính xác của file nguồn server
B. Kiểu content đã được server ghi vào database
C. Chính sách retry nếu request bị trả về 500
D. Kiểu media response mà client có thể chấp nhận
Đáp án đúng: D

Câu 14: Khi API sử dụng Bearer token, header request nào cần kiểm tra?
A. Content-Type chứa Bearer và access token hợp lệ
B. Authorization chứa Bearer và access token hợp lệ
C. Accept-Encoding chứa Bearer và access token hợp lệ
D. Cache-Control chứa Bearer và access token hợp lệ
Đáp án đúng: B

Câu 15: Khi kiểm tra session cookie, bộ thuộc tính nào giúp bảo vệ cookie?
A. Secure, HttpOnly và SameSite theo ngữ cảnh
B. Expires, ETag và Last-Modified của response
C. Content-Type, Accept và Transfer-Encoding
D. Origin, Referer và Content-Disposition
Đáp án đúng: A

Câu 16: Trong curl, muốn xem response headers cùng phần body, dùng tùy chọn nào?
A. --head để tải cả headers và response body
B. -X để in toàn bộ response headers và body
C. -L để hiển thị mọi header và body thô
D. -i để kèm các header response vào output
Đáp án đúng: D

Câu 17: Khi dùng curl gửi JSON với body, cách nào đúng?
A. -H Accept:text/plain cùng -I dữ liệu JSON
B. -L Content-Type:application/json cùng -X JSON
C. Dùng -H cho Content-Type và -d để gửi JSON
D. -v Content-Type:application/json cùng -G body
Đáp án đúng: C

Câu 18: Trong curl, muốn theo HTTP redirect tới URL mới thì dùng gì?
A. Dùng -L để theo các lần HTTP redirect
B. Dùng -i để theo các lần HTTP redirect
C. Dùng --head để theo các lần HTTP redirect
D. Dùng -X để theo các lần HTTP redirect
Đáp án đúng: A

Câu 19: Khi test HTTP lỗi bằng curl trong CI, --fail-with-body có ưu điểm gì?
A. Luôn biến status 4xx thành 200 để test tiếp
B. Có exit code lỗi nhưng vẫn trả response body
C. Luôn tự động gửi lại request khi gặp 5xx
D. Luôn bỏ kiểm tra chứng chỉ TLS ở máy CI
Đáp án đúng: B

Câu 20: Vì sao không nên mặc định dùng curl -k khi kiểm tra HTTPS?
A. Nó buộc tất cả request chuyển sang HTTP/1.0
B. Nó luôn làm body response bị mã hóa hai lần
C. Nó khiến mọi header Authorization bị xóa
D. Bỏ kiểm tra chứng chỉ TLS của server đích
Đáp án đúng: D

Câu 21: Trong Postman, nên quản lý base URL theo môi trường bằng cách nào?
A. Dùng environment variable thay vì hardcode URL
B. Đổi tên request mỗi lần đổi staging và production
C. Ghi URL trực tiếp trong mọi assertion riêng lẻ
D. Đặt URL vào request body để client tự lựa chọn
Đáp án đúng: A

Câu 22: Muốn kiểm tra status và field JSON trong Postman, nên dùng gì?
A. Chỉ nhấn Send mà bỏ qua kết quả trả về
B. Dùng pm.test để assert status và dữ liệu body
C. Chỉ đặt status mong đợi vào request body
D. Chỉ kiểm tra thời gian tải của workspace
Đáp án đúng: B

Câu 23: Trong REST Assured, cấu trúc nào biểu đạt request rồi xác minh response?
A. assertThrows().given().when() trong bộ JUnit
B. post().commit().rollback() trong JDBC
C. start().stop().reset() trong client curl
D. Dùng given().when().then() để kiểm chứng response
Đáp án đúng: D

Câu 24: Với REST Assured, cách kiểm tra field id của JSON response là gì?
A. header("id", expectedId) để đọc field trong body
B. cookie("id", expectedId) để đọc field trong body
C. body("id", equalTo(expectedId)) theo JSONPath
D. statusCode(expectedId) để đọc field trong body
Đáp án đúng: C

Câu 25: Trong Spring MVC, MockMvc phù hợp cho loại HTTP test nào?
A. Phát tải trực tiếp tới production qua kết nối Internet
B. Kiểm tra tầng MVC mà không mở HTTP socket
C. Kiểm thử TCP handshake của reverse proxy ngoài hệ
D. Sinh Pact contract từ toàn bộ bảng của database
Đáp án đúng: B

Câu 26: WebTestClient trong ứng dụng Spring hữu ích vì điều gì?
A. Chỉ hỗ trợ test phương thức Java private không HTTP
B. Chỉ chạy được nếu browser thực đã được cài đặt
C. Tự bật server production trước khi chạy unit test
D. Fluent HTTP assertion, đặc biệt cho Spring WebFlux
Đáp án đúng: D

Câu 27: Khi GET kèm If-None-Match khớp ETag hiện tại, nên test gì?
A. 201 Created và JSON tạo resource giống hệt
B. 304 Not Modified và body không có nội dung
C. 401 Unauthorized và yêu cầu gửi lại cookie
D. 409 Conflict và thông báo phiên bản cũ
Đáp án đúng: B

Câu 28: Khi đưa HTTP test vào CI, thực hành nào giúp kết quả tái lập và bảo mật?
A. Dùng tài khoản production chung rồi lưu token trong log
B. Tái dùng dữ liệu của job cũ mà không có cleanup
C. Dữ liệu cô lập, secret an toàn và assertion lỗi rõ
D. Chỉ assert status 200 rồi bỏ mọi negative test
Đáp án đúng: C
