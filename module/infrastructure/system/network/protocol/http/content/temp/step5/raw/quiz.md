Câu 01. Trong HTTP/1.1, dòng đầu của một request thường chứa gì?
A. Mã trạng thái, reason phrase và phiên bản giao thức HTTP.
B. Phương thức, request-target và phiên bản giao thức HTTP.
C. Host đích, kiểu nội dung và độ dài response body.
D. URI tài nguyên, mã trạng thái và tên phần mềm server.
Đáp án đúng: B

Câu 02. Fragment đứng sau dấu # trong URL được xử lý thế nào khi gửi request HTTP?
A. Fragment được đưa vào HTTP method của dòng request.
B. Fragment không có trong request-target gửi tới server.
C. Fragment được truyền trong header Host của mỗi request.
D. Fragment được ghép vào Cookie để server xác định trang.
Đáp án đúng: B

Câu 03. Vì sao cần percent-encoding một số ký tự trong URI?
A. Để mã hóa bảo mật dữ liệu nhạy cảm trong log truy vấn.
B. Để chuyển toàn bộ phần query của URI thành JSON hợp lệ.
C. Để nén mọi giá trị query trước khi gửi trên kết nối TLS.
D. Để tránh ký tự đặc biệt bị hiểu là dấu phân tách URI.
Đáp án đúng: D

Câu 04. Header Host của request HTTP/1.1 có tác dụng quan trọng nào?
A. Chỉ định tên DNS resolver phải dùng khi gửi response.
B. Chỉ định địa chỉ IP client để server cấp quyền truy cập.
C. Chỉ định server proxy phải ghi request vào access log.
D. Chỉ định tên host để server chọn virtual host đích.
Đáp án đúng: D

Câu 05. Tính safe của phương thức GET được hiểu theo nghĩa nào?
A. Client không yêu cầu thay đổi trạng thái tài nguyên.
B. Server buộc phải cache mọi kết quả GET trong một ngày.
C. Server không được ghi log hay thống kê của request GET.
D. Client luôn nhận cùng nội dung qua mọi request GET.
Đáp án đúng: A

Câu 06. Vì sao retry POST tạo đơn sau timeout có thể gây trùng dữ liệu?
A. POST tự chuyển thành GET khi retry đến cùng một endpoint.
B. Response timeout có nghĩa server chưa nhận bất kỳ request.
C. Request trước có thể đã tạo đơn dù chưa trả response.
D. POST mặc định rollback thay đổi khi response đến quá chậm.
Đáp án đúng: C

Câu 07. Tính idempotent của PUT có ý nghĩa nào khi gọi lặp cùng request?
A. Mỗi lần gọi sẽ sinh tài nguyên mới với định danh khác nhau.
B. Hiệu ứng dự kiến lên trạng thái giống như chỉ gọi một lần.
C. Mã trạng thái phản hồi phải giống hệt nhau qua mọi lần gọi.
D. Server buộc phải bỏ qua body kể từ lần gọi thứ hai.
Đáp án đúng: B

Câu 08. Vì sao không thể mặc định mọi request PATCH đều idempotent?
A. Patch kiểu tăng bộ đếm có thể cộng thêm mỗi lần áp dụng.
B. PATCH luôn tạo tài nguyên mới ở một URI khác với tài nguyên cũ.
C. Mọi request PATCH đều yêu cầu thay toàn bộ tài nguyên như PUT.
D. PATCH chỉ sửa response cache và không thay đổi dữ liệu nguồn.
Đáp án đúng: A

Câu 09. DELETE trả 204 lần đầu rồi 404 ở lần sau có vi phạm tính idempotent không?
A. Có, vì DELETE chỉ được trả 204 trong tất cả các trường hợp.
B. Không, vì DELETE không thuộc nhóm phương thức idempotent.
C. Không, idempotent xét trạng thái chứ không xét status.
D. Có, vì mọi request lặp lại phải trả cùng một status code.
Đáp án đúng: C

Câu 10. Điểm khác nhau cơ bản giữa HEAD và GET khi phản hồi là gì?
A. HEAD chỉ được gửi bằng HTTP/2 còn GET dùng được HTTP/1.1.
B. HEAD không gửi nội dung response body dù có header tương ứng.
C. HEAD buộc server gửi body dạng JSON thay vì HTML như GET.
D. HEAD phải thay đổi tài nguyên trước khi trả các response header.
Đáp án đúng: B

Câu 11. Request OPTIONS preflight trong CORS thường nhằm mục đích nào?
A. Đặt lại trạng thái cache ở browser trước khi gửi request chính.
B. Đăng nhập bằng cookie rồi tự sinh token của request tiếp theo.
C. Kiểm tra method và các header dự kiến có được origin cho phép.
D. Yêu cầu server trả toàn bộ body của endpoint trước khi POST.
Đáp án đúng: C

Câu 12. Khi POST tạo tài nguyên, HTTP 201 Created cùng Location thường biểu thị gì?
A. Nội dung tài nguyên không thay đổi so với cache của client.
B. Server đã xử lý nhưng không có nội dung trả về ở response.
C. Tài nguyên đã được tạo và Location chỉ tới URI của nó.
D. Request mới được chấp nhận nhưng chắc chắn chưa xử lý xong.
Đáp án đúng: C

Câu 13. Mã HTTP 202 Accepted có ý nghĩa nào?
A. Yêu cầu được nhận xử lý nhưng chưa bảo đảm đã hoàn tất.
B. Tài nguyên đã được tạo và được lưu ở URI trong Location.
C. Phản hồi được lấy lại từ cache và không chứa body mới.
D. Giao dịch của backend đã commit chắc chắn trước khi trả.
Đáp án đúng: A

Câu 14. Khi server trả 204 No Content, client nên hiểu điều nào?
A. Response bị chặn vì client thiếu thông tin xác thực.
B. Yêu cầu chỉ được nhận vào hàng đợi và chưa được xử lý.
C. Tài nguyên được trả lại dưới dạng một phần nội dung.
D. Xử lý thành công mà response không có nội dung.
Đáp án đúng: D

Câu 15. Đặc điểm của HTTP 308 Permanent Redirect là gì?
A. Chuyển hướng vĩnh viễn nhưng phải thay method bằng POST.
B. Chuyển hướng tạm thời và yêu cầu client xóa request body.
C. Chuyển hướng vĩnh viễn và giữ method khi gửi tới URI mới.
D. Chuyển hướng tạm thời và bắt client đổi method thành GET.
Đáp án đúng: C

Câu 16. Khi GET với If-None-Match khớp ETag hiện tại, response 304 giúp gì?
A. Client phải tải lại body mới vì bản trong cache đã hết hạn.
B. Server phải tạo một tài nguyên mới rồi gửi Location cho client.
C. Server đã từ chối yêu cầu vì token xác thực vừa bị thu hồi.
D. Client có thể tái sử dụng representation đang giữ trong cache.
Đáp án đúng: D

Câu 17. Tình huống nào thường tương ứng với HTTP 400 Bad Request?
A. Request có cú pháp sai hoặc tham số gửi lên không hợp lệ.
B. Server đã chấp nhận tác vụ nền nhưng chưa xử lý xong.
C. Server đang chờ một upstream và hết thời gian nhận response.
D. Client đã được xác thực nhưng thiếu quyền thao tác tài nguyên.
Đáp án đúng: A

Câu 18. HTTP 401 Unauthorized thường có ý nghĩa nào với API được bảo vệ?
A. Đã vượt hạn mức request được phân bổ cho một client.
B. Thiếu thông tin xác thực hoặc credentials không còn hợp lệ.
C. Đã có xung đột trạng thái khi cập nhật cùng tài nguyên.
D. Đã xác thực thành công nhưng không đủ quyền xem tài nguyên.
Đáp án đúng: B

Câu 19. Khi API trả HTTP 403 Forbidden, diễn giải nào phù hợp?
A. Server không tìm thấy đường dẫn được gửi trong request.
B. Client phải gửi lại do JWT hết hạn hoặc thiếu thông tin.
C. Upstream của server ngừng phản hồi trong thời gian cho phép.
D. Server hiểu request nhưng không cho phép thực hiện thao tác.
Đáp án đúng: D

Câu 20. Khi cập nhật dữ liệu phụ thuộc phiên bản và gặp xung đột, nên dùng mã nào?
A. 304 Not Modified phản ánh bản cache vẫn đang sử dụng.
B. 404 Not Found phản ánh thiếu một tài nguyên trên server.
C. 202 Accepted phản ánh tác vụ đã vào hàng đợi xử lý.
D. 409 Conflict phản ánh xung đột với trạng thái hiện tại.
Đáp án đúng: D

Câu 21. Gateway từ chối request vì vượt hạn mức, mã HTTP nào hợp lý?
A. 404 Not Found, dùng khi không có route của endpoint.
B. 409 Conflict, dùng khi có hai bản ghi bị cập nhật cạnh tranh.
C. 429 Too Many Requests, có thể kèm thông tin Retry-After.
D. 401 Unauthorized, dùng để yêu cầu xác thực lại bằng token.
Đáp án đúng: C

Câu 22. Khi gateway không nhận được phản hồi hợp lệ từ upstream, mã nào phù hợp?
A. 502 Bad Gateway thường mô tả phản hồi upstream không hợp lệ.
B. 504 Gateway Timeout cho biết upstream quá lâu chưa phản hồi.
C. 503 Service Unavailable cho biết dịch vụ đang không sẵn sàng.
D. 403 Forbidden cho biết request bị từ chối do chính sách quyền.
Đáp án đúng: A

Câu 23. HTTP 503 Service Unavailable thường dùng trong tình huống nào?
A. Resource đã di chuyển vĩnh viễn sang một URI khác.
B. Client gửi thông tin đăng nhập sai trong request.
C. Dịch vụ tạm không sẵn sàng vì quá tải hoặc bảo trì.
D. Yêu cầu đã được xử lý nhưng không có response body.
Đáp án đúng: C

Câu 24. Trong HTTP, header Content-Type của response mô tả gì?
A. Media type của representation được gửi trong body.
B. Thuật toán nén đã áp dụng cho body khi truyền dữ liệu.
C. Chính sách cache mà các proxy phải tuân theo.
D. Media type mà client muốn server chọn ở request mới.
Đáp án đúng: A

Câu 25. Header Accept trong request giúp client thể hiện điều gì?
A. Những media type của response mà client có thể nhận.
B. Media type của request body đã được client gửi lên.
C. Thuật toán nén đã sử dụng cho request body hiện tại.
D. Độ dài body mà client sẽ chấp nhận trong response.
Đáp án đúng: A

Câu 26. Một response có Content-Encoding: gzip nghĩa là gì?
A. Gateway đã chuyển response thành nội dung dạng chunked.
B. Media type của body đã đổi từ JSON thành kiểu gzip.
C. Representation được mã hóa nén bằng gzip khi truyền.
D. Client chỉ được giải mã response nếu kết nối có TLS.
Đáp án đúng: C

Câu 27. Với Authorization: Bearer, header đang truyền thông tin nào?
A. Khóa TLS dùng để thiết lập một phiên mã hóa giữa hai bên.
B. Access token làm credential để server kiểm tra quyền truy cập.
C. ETag của tài nguyên để thực hiện request có điều kiện.
D. Cookie phiên đăng nhập để browser tự gắn cho mọi origin.
Đáp án đúng: B

Câu 28. Khi client gửi Range: bytes=0-999 và server hỗ trợ, phản hồi nào phù hợp?
A. 200 OK kèm Location để chỉ tới bản sao đã được cắt.
B. 206 Partial Content và header Content-Range đi kèm.
C. 304 Not Modified kèm ETag để tải 1000 byte đầu tiên.
D. 204 No Content kèm Accept-Ranges để trả đoạn nội dung.
Đáp án đúng: B

Câu 29. Phân biệt Set-Cookie và Cookie trong HTTP như thế nào?
A. Server đặt cookie qua Set-Cookie; client gửi lại bằng Cookie.
B. Cookie chỉ dùng cho cache còn Set-Cookie chỉ dùng cho TLS.
C. Client đặt cookie qua Set-Cookie; server gửi lại bằng Cookie.
D. Server và client đều đặt cookie bằng header Authorization.
Đáp án đúng: A

Câu 30. Thuộc tính Secure trên cookie có tác dụng gì?
A. Giới hạn cookie chỉ được gửi trong cùng một tab của trình duyệt.
B. Buộc cookie có chữ ký số được server xác nhận khi gửi lại.
C. Chỉ gửi cookie trên các kết nối an toàn như HTTPS.
D. Ngăn JavaScript đọc cookie khi truy cập document.cookie.
Đáp án đúng: C

Câu 31. Thuộc tính HttpOnly trên cookie chủ yếu bảo vệ điều gì?
A. Không cho trình duyệt gửi cookie trên các HTTP request.
B. Chỉ cho gửi cookie nếu cả trang và server ở cùng IP.
C. Buộc các cookie luôn được mã hóa trước khi vào bộ nhớ.
D. Ngăn JavaScript đọc cookie qua document.cookie.
Đáp án đúng: D

Câu 32. Thuộc tính SameSite trên cookie kiểm soát hành vi nào?
A. Thay thế hoàn toàn token chống CSRF ở mọi request thay đổi dữ liệu.
B. Chỉ cho browser ghi cookie khi tải trang qua cùng một port.
C. Buộc cookie chỉ có hiệu lực đối với tên miền không có subdomain.
D. Giới hạn việc gửi cookie trong những ngữ cảnh cross-site.
Đáp án đúng: D

Câu 33. Cache-Control: no-store trong response yêu cầu điều gì?
A. Cache được dùng lại tự do cho tới thời điểm max-age.
B. Cache không được lưu response đó vào bộ nhớ lưu trữ.
C. Cache chỉ được lưu ở browser, không được ở shared proxy.
D. Cache vẫn được lưu response nhưng phải xác minh trước mỗi lần.
Đáp án đúng: B

Câu 34. Điểm chính của Cache-Control: no-cache là gì?
A. Cho phép lưu nhưng yêu cầu revalidate trước khi dùng.
B. Không được lưu bất kỳ byte nào của response tại mọi cache.
C. Có thể dùng lại mọi response mà không hỏi server nguồn.
D. Buộc cache chỉ lưu response trên đĩa thay vì bộ nhớ.
Đáp án đúng: A

Câu 35. ETag cùng If-None-Match hỗ trợ cơ chế nào?
A. TLS session resumption để tái sử dụng khóa giữa các kết nối.
B. Conditional request kiểm tra bản cache có còn phù hợp không.
C. Content negotiation chọn ngôn ngữ hiển thị của representation.
D. Chunked transfer tách body thành nhiều phần khi gửi qua mạng.
Đáp án đúng: B

Câu 36. Vary: Accept-Encoding có ý nghĩa nào với HTTP cache?
A. Cache được tự đổi Content-Encoding dù server không hỗ trợ.
B. Cache phải giữ một body chung cho gzip và identity encoding.
C. Cache phân biệt response theo giá trị Accept-Encoding.
D. Cache cần bỏ qua Accept-Encoding khi tạo khóa của response.
Đáp án đúng: C

Câu 37. HTTPS bảo vệ request HTTP trên mạng bằng cơ chế nào?
A. Percent-encoding mã hóa path để không ai đọc được URL.
B. HTTP header Host xác thực máy chủ trước khi trao đổi.
C. Cache-Control ngăn các proxy nhìn thấy dữ liệu của body.
D. TLS mã hóa và xác thực server bằng chứng chỉ đáng tin.
Đáp án đúng: D

Câu 38. Khi API trả nội dung sai, công cụ dòng lệnh nào giúp xem header trao đổi?
A. Dùng curl -I để tải toàn bộ body của phản hồi GET.
B. Dùng curl -o để tự giải mã schema JSON của server.
C. Dùng curl --resolve để xem mọi header không cần gửi request.
D. Dùng curl -v để xem cả request lẫn response headers.
Đáp án đúng: D

Câu 39. Điểm khác biệt quan trọng của HTTP/2 so với HTTP/1.1 là gì?
A. HTTP/2 bắt buộc mở một TCP connection cho mỗi request mới.
B. HTTP/2 ghép nhiều stream đồng thời trên một kết nối TCP.
C. HTTP/2 xóa toàn bộ header của HTTP/1.1 để chỉ còn body.
D. HTTP/2 thay TCP bằng QUIC để tránh mất gói ở tầng vận chuyển.
Đáp án đúng: B

Câu 40. HTTP/3 khác HTTP/2 ở nền tảng truyền tải nào?
A. HTTP/3 dùng QUIC trên UDP thay vì HTTP/2 dùng TCP.
B. HTTP/3 dùng TLS trên TCP giống hệt HTTP/1.1 thông thường.
C. HTTP/3 dùng WebSocket như transport cho mọi request.
D. HTTP/3 dùng SCTP và không có cơ chế mã hóa nào.
Đáp án đúng: A
