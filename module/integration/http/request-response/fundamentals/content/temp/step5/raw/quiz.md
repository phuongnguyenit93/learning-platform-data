Câu 01. Client mở `https://api.example.test/orders?state=open#detail`; phần nào không được gửi trong request-target?
A. `/orders` vì path chỉ để định tuyến phía client
B. `state=open` vì query chuyển thành header Host
C. `?state=open` vì query chỉ dùng để hiển thị URL
D. `#detail` vì fragment được trình duyệt xử lý
Đáp án đúng: D

Câu 02. Client gửi HTTP/1.1 GET `/orders?page=2` trực tiếp tới origin server; dòng request nào đúng?
A. `GET /orders?page=2 HTTP/2.0`
B. `HTTP/1.1 GET /orders?page=2`
C. `GET /orders?page=2 HTTP/1.1`
D. `GET /orders?page=2 200 OK`
Đáp án đúng: C

Câu 03. Header Host trong HTTP/1.1 chủ yếu giúp server xác định thông tin nào?
A. Kết nối có tiếp tục dùng sau response hiện tại
B. Tên máy chủ và cổng theo authority được yêu cầu
C. Định dạng nội dung mà trình duyệt muốn nhận về
D. Số byte dự kiến nằm trong phần request body
Đáp án đúng: B

Câu 04. Trong path của URL, chuỗi `%20` thường được giải mã thành giá trị nào?
A. Một ký tự dấu hỏi để bắt đầu phần query string
B. Một ký tự thăng để bắt đầu phần URL fragment
C. Một ký tự dấu cách đã được percent-encode
D. Một ký tự gạch chéo để tách hai path segment
Đáp án đúng: C

Câu 05. Tính safe của HTTP GET có ý nghĩa gì đối với hành động mà client yêu cầu?
A. Client yêu cầu ghi nhưng lặp lại không đổi kết quả
B. Client có thể xóa dữ liệu nếu không gửi request body
C. Client luôn lấy dữ liệu từ cache mà không gọi server
D. Client yêu cầu đọc, không chủ đích sửa trạng thái
Đáp án đúng: D

Câu 06. Client dùng HEAD để kiểm tra metadata của tài nguyên; phản hồi nên có đặc điểm gì?
A. Trả status 304 ngay cả khi chưa có validator nào
B. Trả header phù hợp GET nhưng không có message body
C. Trả status 204 bắt buộc cho mọi tài nguyên tìm thấy
D. Trả body JSON rỗng để biểu diễn tài nguyên hiện có
Đáp án đúng: B

Câu 07. POST `/orders` đã tạo một đơn hàng và server muốn chỉ URI mới; phản hồi nào phù hợp?
A. `204 No Content` kèm `ETag` làm địa chỉ đơn hàng
B. `201 Created` kèm `Location` của đơn hàng mới
C. `200 OK` kèm `Vary` làm địa chỉ đơn hàng mới
D. `202 Accepted` kèm `Retry-After` của đơn hàng mới
Đáp án đúng: B

Câu 08. Vì sao PUT được xem là idempotent theo ngữ nghĩa HTTP?
A. Lặp cùng yêu cầu có tác động cuối giống một lần
B. Mỗi lần PUT phải trả cùng status và response body
C. Mỗi lần PUT luôn sinh một resource mới ở URI khác
D. PUT không cần xác thực dù resource có dữ liệu riêng
Đáp án đúng: A

Câu 09. Điều nào đúng về tính idempotent của PATCH?
A. Luôn sai vì PATCH bắt buộc tạo resource ở URI mới
B. Phụ thuộc vào ngữ nghĩa và nội dung patch được gửi
C. Được bảo đảm chỉ vì PATCH có cùng URI đích
D. Luôn đúng vì PATCH chỉ thay đổi một trường dữ liệu
Đáp án đúng: B

Câu 10. Tại sao DELETE có thể idempotent dù hai lần gọi nhận status khác nhau?
A. Mọi lần xóa đều cần tạo một bản sao dữ liệu trước
B. DELETE phải hoàn tác lần xóa trước nếu lặp request
C. Trạng thái cuối của resource vẫn như sau lần xóa đầu
D. Server buộc phải phản hồi cùng một mã trong mọi lần
Đáp án đúng: C

Câu 11. Response có mã `204 No Content` thì phần message body phải được xử lý ra sao?
A. Gửi JSON `null` để client phân tích như object
B. Gửi JSON `{}` để biểu diễn tài nguyên đã rỗng
C. Gửi chuỗi `0` làm body với Content-Type text/plain
D. Không gửi nội dung message body trong phản hồi
Đáp án đúng: D

Câu 12. Server nhận tác vụ xuất báo cáo nhưng việc chạy đang chờ hàng đợi; mã phản hồi nào phù hợp?
A. `202 Accepted` vì yêu cầu đã nhận, xử lý chưa xong
B. `200 OK` vì server chắc chắn đã trả về báo cáo
C. `201 Created` vì file báo cáo đã sẵn sàng để tải
D. `204 No Content` vì mọi công việc đã hoàn thành
Đáp án đúng: A

Câu 13. Client gửi request line sai cú pháp khiến HTTP server không đọc được yêu cầu; status phù hợp?
A. `400 Bad Request` cho yêu cầu sai cú pháp giao thức
B. `422 Unprocessable Content` cho dữ liệu hợp lệ về cú pháp
C. `502 Bad Gateway` cho phản hồi từ upstream lỗi
D. `409 Conflict` cho xung đột phiên bản tài nguyên
Đáp án đúng: A

Câu 14. URI `/users/xyz` không khớp bất kỳ resource nào được server công bố; status thường dùng?
A. `401 Unauthorized` vì token chưa được gửi đến
B. `405 Method Not Allowed` vì URI có method khác
C. `404 Not Found` vì không có tài nguyên tại URI
D. `406 Not Acceptable` vì định dạng body chưa hợp
Đáp án đúng: C

Câu 15. URI `/files/7` hỗ trợ GET nhưng không hỗ trợ PATCH; server nên phản hồi thế nào?
A. `409 Conflict` và header `Retry-After`
B. `404 Not Found` và header `Cache-Control`
C. `415 Unsupported Media Type` và header `Vary`
D. `405 Method Not Allowed` và header `Allow`
Đáp án đúng: D

Câu 16. Endpoint yêu cầu Bearer token nhưng request chưa cung cấp thông tin xác thực; phản hồi nào đúng?
A. `401 Unauthorized` kèm `WWW-Authenticate` thích hợp
B. `404 Not Found` kèm `ETag` của endpoint được gọi
C. `409 Conflict` kèm `Vary` của tài nguyên bị cấm
D. `403 Forbidden` kèm `Location` đến endpoint mới
Đáp án đúng: A

Câu 17. Client đã xác thực nhưng không có quyền đọc resource này; status phù hợp trong trường hợp thông thường?
A. `401 Unauthorized` vì chưa xác định được danh tính
B. `405 Method Not Allowed` vì phương thức không hỗ trợ
C. `422 Unprocessable Content` vì body sai ngữ nghĩa
D. `403 Forbidden` vì quyền truy cập không được cấp
Đáp án đúng: D

Câu 18. Client vượt hạn mức request và server muốn chỉ thời điểm thử lại; cách phản hồi nào phù hợp?
A. `429 Too Many Requests` với `Retry-After`
B. `409 Conflict` với `Content-Encoding`
C. `408 Request Timeout` với `Content-Range`
D. `503 Service Unavailable` với `If-Match`
Đáp án đúng: A

Câu 19. Client cần chuyển POST sang URI mới vĩnh viễn mà vẫn giữ method và body; status redirect nào phù hợp?
A. `303 See Other` để giữ body của request POST cũ
B. `308 Permanent Redirect` để giữ method ban đầu
C. `302 Found` để bảo đảm không đổi method ban đầu
D. `301 Moved Permanently` để luôn giữ method POST
Đáp án đúng: B

Câu 20. Sau khi xử lý POST form, server muốn browser mở trang kết quả bằng GET; nên trả redirect nào?
A. `307 Temporary Redirect` giữ POST tới trang mới
B. `308 Permanent Redirect` giữ POST tới trang mới
C. `304 Not Modified` điều hướng tới trang kết quả
D. `303 See Other` với `Location` tới trang kết quả
Đáp án đúng: D

Câu 21. Khi nhận `307 Temporary Redirect`, client gửi lại request tới URI mới theo cách nào?
A. Giữ nguyên method và body của request ban đầu
B. Giữ body nhưng buộc đổi method thành GET mới
C. Chuyển mọi method thành GET và loại bỏ body cũ
D. Chỉ gửi HEAD để xác nhận URI trước khi chuyển
Đáp án đúng: A

Câu 22. Server trả header ETag trên response GET; mục đích chính của giá trị này là gì?
A. Khai báo loại media type được phép gửi từ client
B. Gợi ý khoảng thời gian cần chờ trước khi retry
C. Cung cấp validator cho biểu diễn resource hiện tại
D. Chỉ định URI để tạo bản sao resource mới nhất
Đáp án đúng: C

Câu 23. Client gửi GET `If-None-Match` trùng ETag hiện tại; phản hồi nào thích hợp?
A. `200 OK` bắt buộc gửi lại response body như cũ
B. `304 Not Modified` và không có response body
C. `412 Precondition Failed` cho mọi request GET này
D. `206 Partial Content` và chỉ gửi trường đã đổi
Đáp án đúng: B

Câu 24. Client PUT `If-Match` chứa ETag cũ, không khớp biểu diễn hiện tại; status nào đúng?
A. `428 Precondition Required` dù client đã gửi If-Match
B. `304 Not Modified` vì dữ liệu chưa đổi từ lần trước
C. `412 Precondition Failed` vì điều kiện không khớp
D. `409 Conflict` là phản hồi bắt buộc với mọi ETag cũ
Đáp án đúng: C

Câu 25. Dữ liệu response không được lưu ở bất cứ cache nào; chỉ thị Cache-Control nào diễn đạt đúng?
A. `private` yêu cầu mọi cache không lưu response
B. `no-store` yêu cầu cache không lưu response
C. `max-age=0` yêu cầu mọi cache không lưu response
D. `no-cache` yêu cầu cache không lưu response
Đáp án đúng: B

Câu 26. Cache-Control `no-cache` trên response cho phép cache làm gì?
A. Lưu response và dùng lại khi còn trong thời gian max-age
B. Lưu response nhưng phải xác thực lại trước khi dùng
C. Cấm lưu bất cứ byte nào của response vào cache
D. Cho cache chia sẻ phát response mà không cần xác thực
Đáp án đúng: B

Câu 27. Response chứa nội dung riêng của người dùng; directive nào cấm cache dùng chung lưu nó?
A. `Cache-Control: private` dành cho cache riêng
B. `Cache-Control: max-age=3600` cho phép cache một giờ
C. `Cache-Control: public` cho phép cache dùng chung
D. `Cache-Control: immutable` cho phép bỏ qua kiểm tra
Đáp án đúng: A

Câu 28. Server trả gzip hoặc br tùy `Accept-Encoding`; nên thêm header nào để cache tách biến thể?
A. `Vary: Authorization` để phân biệt cách nén
B. `Vary: Content-Length` để phân biệt cách nén
C. `Vary: Accept-Encoding` để phân biệt cách nén
D. `Vary: Content-Type` để phân biệt cách nén
Đáp án đúng: C

Câu 29. Client gửi `Accept: application/xml`, server chỉ tạo JSON và chọn từ chối; status nào phù hợp?
A. `406 Not Acceptable` vì không có biểu diễn phù hợp
B. `415 Unsupported Media Type` vì body request sai định dạng
C. `400 Bad Request` vì request không có header Content-Type
D. `422 Unprocessable Content` vì body sai quy tắc nghiệp vụ
Đáp án đúng: A

Câu 30. Endpoint chỉ nhận JSON, client POST với `Content-Type: application/xml`; status nào phù hợp?
A. `404 Not Found` vì không có schema XML trong kho
B. `406 Not Acceptable` vì định dạng response không phù hợp
C. `415 Unsupported Media Type` vì kiểu nội dung không hỗ trợ
D. `409 Conflict` vì bản ghi trùng với trạng thái hiện có
Đáp án đúng: C

Câu 31. Client gửi `Accept-Encoding: gzip`, server thực sự nén response bằng gzip; header nào mô tả body?
A. `Content-Type: gzip` để báo body có dạng JSON
B. `Content-Encoding: gzip` trên response đã nén
C. `Transfer-Encoding: gzip` để chỉ loại resource
D. `Accept-Encoding: gzip` để khai báo body đã nén
Đáp án đúng: B

Câu 32. Với HTTP/1.1 và request body chứa tiếng Việt UTF-8, `Content-Length` đếm đại lượng nào?
A. Số ký tự Unicode trước khi mã hóa thành UTF-8
B. Số phần tử JSON nằm trong body của request
C. Số dòng văn bản mà request body đã truyền đi
D. Số octet thực tế của body được truyền qua mạng
Đáp án đúng: D

Câu 33. Trong HTTP/1.1, muốn truyền body theo từng chunk khi chưa biết tổng chiều dài trước; header nào dùng?
A. `Accept-Encoding: chunked` để server gửi body dạng chunk
B. `Content-Length: chunked` để đánh dấu số byte chưa biết
C. `Content-Encoding: chunked` để báo nén body theo chunk
D. `Transfer-Encoding: chunked` cho framing theo chunk
Đáp án đúng: D

Câu 34. Client gửi `Expect: 100-continue` trước body lớn; server phản hồi `100 Continue` có nghĩa gì?
A. Client cần đóng kết nối TCP trước khi gửi request
B. Client có thể tiếp tục gửi request body đang chờ
C. Server yêu cầu client thay body bằng dữ liệu khác
D. Server đã xử lý xong và gửi response cuối cùng
Đáp án đúng: B

Câu 35. Server HTTP/1.1 trả `Connection: close`; client nên hiểu kết nối thế nào?
A. Kết nối hiện tại sẽ đóng sau khi response hoàn tất
B. Server sẽ giữ TCP kết nối để chạy nhiều request nữa
C. Client phải tự chuyển sang HTTP/2 cho request kế
D. Server chỉ đóng một HTTP/2 stream đang hoạt động
Đáp án đúng: A

Câu 36. HTTP/2 cho phép nhiều HTTP request chạy đồng thời trên cùng kết nối bằng cơ chế nào?
A. Thay mọi kết nối TCP bằng datagram QUIC ở ứng dụng
B. Tạo một kết nối TCP mới cho từng header của request
C. Gửi request tuần tự, đợi xong response mới gửi tiếp
D. Multiplexing nhiều stream trong một kết nối TCP
Đáp án đúng: D

Câu 37. Giao thức nền phổ biến của HTTP/3 là gì?
A. HTTP/1.1 chạy trên TLS với kết nối giữ lâu
B. WebSocket chạy trên TCP sau bước nâng cấp
C. HTTP/2 chạy trên TCP với frame nhị phân
D. QUIC chạy trên UDP với các stream độc lập
Đáp án đúng: D

Câu 38. Khi dùng HTTPS tới origin với chứng chỉ hợp lệ, TLS chủ yếu cung cấp gì?
A. Mã hóa URL nhưng không bảo vệ phần header và body
B. Bảo đảm server không bao giờ trả status lỗi 5xx
C. Mã hóa luồng truyền và xác thực máy chủ theo chứng chỉ
D. Tự bảo đảm mọi request nghiệp vụ đều idempotent
Đáp án đúng: C

Câu 39. Gateway có thể kết nối tới upstream nhưng nhận phản hồi HTTP không hợp lệ; status gateway nào phù hợp?
A. `408 Request Timeout` do client truyền request quá chậm
B. `504 Gateway Timeout` do upstream phản hồi quá thời gian
C. `502 Bad Gateway` do upstream trả phản hồi không hợp lệ
D. `503 Service Unavailable` do origin đang bảo trì tạm thời
Đáp án đúng: C

Câu 40. TCP bị reset trước khi client nhận được status line HTTP hợp lệ; client cần phân loại tình huống thế nào?
A. Lỗi truyền tải vì chưa có response HTTP hợp lệ
B. HTTP 408 vì server đã trả trạng thái timeout
C. HTTP 204 vì kết nối đóng mà không có body
D. HTTP 500 vì origin chắc chắn gặp lỗi xử lý nội bộ
Đáp án đúng: A
