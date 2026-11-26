Câu 1. Xác thực (authentication) trong API chủ yếu trả lời câu hỏi nào?
A. Quyết định caller có được đọc hay sửa một tài nguyên cụ thể.
B. Kiểm tra dữ liệu request có đúng schema và kiểu hay không.
C. Giới hạn số request mà một địa chỉ IP được gửi.
D. Xác minh danh tính của caller hoặc client gửi request.
Đáp án đúng: D

Câu 2. Phân quyền (authorization) trong API chủ yếu quyết định điều gì?
A. Quyết định caller được làm gì trên tài nguyên.
B. Xác minh mật khẩu hoặc chữ ký token của caller.
C. Mã hóa payload để bảo vệ dữ liệu khi truyền qua mạng.
D. Xác định phiên bản schema mà client đang sử dụng.
Đáp án đúng: A

Câu 3. Người dùng đã đăng nhập thành công; kiểm tra nào vẫn cần trước khi trả dữ liệu đơn hàng?
A. Chỉ kiểm tra access token còn hạn rồi trả order theo ID.
B. Kiểm tra quyền đọc order thuộc phạm vi của caller.
C. Kiểm tra request đến từ origin đã được CORS cho phép.
D. Chỉ xác minh order ID tồn tại trong cơ sở dữ liệu.
Đáp án đúng: B

Câu 4. Lỗ hổng BOLA thường xuất hiện trong tình huống nào?
A. Caller gọi endpoint quản trị mà không có quyền chức năng.
B. Caller gửi payload có field không tồn tại trong schema.
C. Caller gửi quá nhiều request trong một khoảng thời gian.
D. Truy cập object ngoài phạm vi bằng cách sửa ID.
Đáp án đúng: D

Câu 5. BFLA mô tả kiểu lỗi phân quyền nào?
A. Người dùng đọc được object của tenant khác bằng cách đổi ID.
B. Truy cập chức năng đặc quyền mà caller không được cấp.
C. Client gửi field nhạy cảm để ghi đè thuộc tính nội bộ.
D. Server tải URL do client cung cấp và truy cập mạng nội bộ.
Đáp án đúng: B

Câu 6. Kiểm soát quyền ở mức property giúp ngăn rủi ro nào?
A. Ngăn người chưa đăng nhập gửi request tới API.
B. Ngăn client gửi nhiều request trong cùng một giây.
C. Ngăn trình duyệt gửi request từ origin khác.
D. Ngăn đọc hoặc sửa property ngoài quyền được cấp.
Đáp án đúng: D

Câu 7. API đa tenant nên giới hạn truy vấn tài nguyên theo cách nào?
A. Lấy object theo ID trước rồi chỉ kiểm tra tenant ở giao diện.
B. Đưa tenant và quyền vào điều kiện truy vấn phía server.
C. Tin tenant ID do client gửi mà không đối chiếu danh tính.
D. Dùng chung một cache key cho mọi tenant để giảm truy vấn.
Đáp án đúng: B

Câu 8. Chính sách phân quyền mặc định an toàn nên hoạt động ra sao?
A. Cho phép mặc định rồi chặn riêng các endpoint nhạy cảm.
B. Từ chối mặc định, chỉ cho phép theo rule rõ ràng.
C. Chỉ yêu cầu đăng nhập cho thao tác ghi dữ liệu.
D. Dùng CORS allowlist làm chính sách phân quyền mặc định.
Đáp án đúng: B

Câu 9. Vì sao API phải kiểm tra quyền ở phía server trên từng request?
A. Trình duyệt luôn thực thi chính xác mọi rule phân quyền của UI.
B. TLS tự kiểm tra quyền trên từng object trước khi gửi response.
C. API gateway tự suy ra quyền dữ liệu từ HTTP method.
D. Client có thể sửa request trước khi gửi lên server.
Đáp án đúng: D

Câu 10. Khi nhận JWT access token, API cần xác minh những gì trước khi tin claims?
A. Tên người dùng, HTTP method, CORS origin và request body.
B. Chỉ `exp` và `sub`, vì chữ ký được kiểm tra bởi client.
C. Xác minh signature, algorithm, issuer, audience và thời hạn.
D. Chỉ issuer và thời điểm phát hành, vì HTTPS bảo vệ claims.
Đáp án đúng: C

Câu 11. Khi quản lý API key, biện pháp nào giúp giảm rủi ro lộ và bị lạm dụng?
A. Ghi API key vào URL để log gateway có thể truy vết dễ dàng.
B. Lưu secret an toàn, giới hạn scope, hỗ trợ rotation và thu hồi.
C. Dùng chung một key không hết hạn cho mọi ứng dụng tích hợp.
D. Chỉ giới hạn API key theo CORS origin của trình duyệt.
Đáp án đúng: B

Câu 12. Schema validation cho request body nên xử lý field không được khai báo thế nào?
A. Tự động bind mọi field để tương thích client tương lai.
B. Chuyển field không biết thành thuộc tính mở rộng của model.
C. Từ chối hoặc bỏ qua field ngoài contract đã định nghĩa.
D. Chỉ kiểm tra JSON parse được rồi tin mọi giá trị còn lại.
Đáp án đúng: C

Câu 13. Validation ngữ nghĩa khác validation cú pháp ở điểm nào?
A. Cú pháp kiểm tra quyền; ngữ nghĩa xác minh chữ ký token.
B. Cú pháp giới hạn tốc độ; ngữ nghĩa mã hóa dữ liệu request.
C. Cú pháp xác minh TLS; ngữ nghĩa chọn phiên bản API.
D. Cú pháp kiểm tra format; ngữ nghĩa kiểm tra quy tắc nghiệp vụ.
Đáp án đúng: D

Câu 14. Vì sao cần chuẩn hóa dữ liệu trước khi áp dụng rule validation?
A. Giúp response JSON ngắn hơn khi serialize dữ liệu.
B. Giúp API không cần kiểm tra quyền trên từng object.
C. Giúp client và server tự đồng bộ clock khi xác thực token.
D. Chuẩn hóa trước để cùng dữ liệu có cùng cách kiểm tra.
Đáp án đúng: D

Câu 15. Mass assignment thường xảy ra khi nào?
A. Client ghi đè thuộc tính model không được phép.
B. Client gửi object ID của tài nguyên thuộc user khác.
C. Server nhận URL và truy cập địa chỉ IP nội bộ.
D. Caller gửi request lặp lại với cùng idempotency key.
Đáp án đúng: A

Câu 16. Cách nào giúp giảm nguy cơ SQL injection khi API hỗ trợ lọc dữ liệu?
A. Dùng parameterized query và allowlist cho sort field.
B. Nối trực tiếp filter string vào SQL sau khi loại dấu nháy.
C. Chỉ mã hóa response JSON trước khi gửi về trình duyệt.
D. Ẩn query error khỏi client nhưng vẫn ghép SQL từ input.
Đáp án đúng: A

Câu 17. API cho phép người dùng cung cấp URL để server tải nội dung; cách phòng SSRF nào phù hợp?
A. Chỉ kiểm tra URL có tiền tố HTTPS rồi tải bằng HTTP client mặc định.
B. Chỉ chặn chuỗi localhost trước khi resolve hostname.
C. Allowlist đích và kiểm tra IP resolve trước khi fetch.
D. Tin hostname do client gửi nếu DNS trả về ít nhất một IP.
Đáp án đúng: C

Câu 18. Vì sao cần kiểm tra lại địa chỉ đích sau redirect hoặc DNS resolution?
A. DNS chỉ trả lời tên miền nên không ảnh hưởng địa chỉ IP đích.
B. Redirect luôn giữ nguyên host và scheme ban đầu.
C. Kiểm tra TLS certificate làm mọi redirect trở nên an toàn.
D. DNS hoặc redirect có thể đổi đích sang mạng nội bộ.
Đáp án đúng: D

Câu 19. Kiểm soát egress network hỗ trợ phòng SSRF như thế nào?
A. Chỉ cho server kết nối tới đích cần thiết và chặn mạng nhạy cảm.
B. Mở outbound tới mọi subnet để ứng dụng không bị lỗi tích hợp.
C. Chỉ lọc inbound traffic vì SSRF không tạo kết nối outbound.
D. Cho phép outbound tùy ý nếu API yêu cầu xác thực JWT.
Đáp án đúng: A

Câu 20. Endpoint fetch URL cần xử lý truy cập cloud metadata ra sao?
A. Cho phép metadata endpoint vì chỉ workload nội bộ truy cập được.
B. Chỉ xóa metadata URL khỏi response sau khi fetch hoàn tất.
C. Dùng CORS để ngăn server gửi request tới metadata service.
D. Chặn metadata endpoint và hạn chế egress tới vùng này.
Đáp án đúng: D

Câu 21. Rate limit cho API nên gắn với những định danh nào?
A. Identity hoặc tenant làm khóa chính; IP là tín hiệu phụ.
B. Chỉ IP nguồn vì identity có thể thay đổi giữa các request.
C. Chỉ User-Agent vì client thường giữ nguyên chuỗi này.
D. Chỉ HTTP method vì mỗi method có tần suất cố định.
Đáp án đúng: A

Câu 22. Token bucket phù hợp để giới hạn lưu lượng theo cách nào?
A. Cho phép mọi burst không giới hạn rồi chặn theo tổng request ngày.
B. Cho phép burst ngắn nhưng giới hạn tốc độ trung bình.
C. Chia đều request thành lịch cố định và không cho burst.
D. Giới hạn tổng số session đang đăng nhập mà không xét tốc độ.
Đáp án đúng: B

Câu 23. Ngoài request rate, API cần quota nào để kiểm soát lạm dụng tài nguyên?
A. Giới hạn concurrency, payload, thời gian và chi phí xử lý.
B. Chỉ giới hạn số request mỗi phút, không cần giới hạn payload.
C. Chỉ giới hạn số user đăng nhập và để tác vụ chạy vô hạn.
D. Chỉ giới hạn response size sau khi server đã xử lý xong.
Đáp án đúng: A

Câu 24. Pagination an toàn nên giới hạn và kiểm soát tham số nào?
A. Cho phép page size tùy ý nếu caller đã đăng nhập thành công.
B. Dùng offset không giới hạn và trả mọi field để client tự lọc.
C. Giới hạn page size, dùng cursor ổn định và kiểm tra thứ tự sắp xếp.
D. Dùng cursor do client tự ký mà không kiểm tra quyền trên dữ liệu.
Đáp án đúng: C

Câu 25. API cho phép client chọn filter và sort; cách thiết kế nào giảm rủi ro?
A. Allowlist field/operator, giới hạn độ phức tạp và tham số đầu vào.
B. Chấp nhận mọi field và biểu thức rồi chuyển thẳng vào ORM.
C. Chỉ lọc ký tự đặc biệt nhưng cho phép mọi phép sort lồng nhau.
D. Dựa vào tên field trong UI để quyết định truy vấn phía server.
Đáp án đúng: A

Câu 26. Biện pháp nào giúp giảm resource exhaustion từ request đắt đỏ?
A. Tăng worker vô hạn để mọi request đều được xử lý ngay.
B. Tắt timeout và giữ kết nối mở để client hoàn tất payload.
C. Đặt giới hạn body, timeout, concurrency và chi phí truy vấn.
D. Chỉ cache response sau khi tác vụ tốn tài nguyên đã chạy xong.
Đáp án đúng: C

Câu 27. Nguyên tắc nào giúp hạn chế sensitive data exposure trong response?
A. Trả toàn bộ model rồi trông chờ client ẩn field nhạy cảm.
B. Ẩn tên field nhưng vẫn gửi giá trị nhạy cảm trong JSON.
C. Chỉ trả field cần thiết và kiểm soát quyền đọc property.
D. Mã hóa response bằng Base64 để dữ liệu không bị lộ.
Đáp án đúng: C

Câu 28. API nên phản hồi lỗi nội bộ như thế nào để tránh lộ thông tin?
A. Trả stack trace, SQL và đường dẫn nội bộ để client tự sửa request.
B. Trả token, config và dependency version khi gặp lỗi 500.
C. Trả cùng một HTTP 200 cho mọi lỗi để không tiết lộ trạng thái.
D. Thông điệp an toàn cho client; chi tiết giữ trong log.
Đáp án đúng: D

Câu 29. Idempotency key hữu ích nhất trong tình huống nào?
A. Dùng key để tránh tạo tác vụ trùng khi client retry.
B. Đọc danh sách tài nguyên bằng GET không có side effect.
C. Lấy health check của service để xác nhận server đang hoạt động.
D. Tải file tĩnh qua CDN bằng một URL công khai.
Đáp án đúng: A

Câu 30. Để xử lý hai request đồng thời cùng idempotency key an toàn, server cần làm gì?
A. Lưu key và trạng thái kết quả một cách atomic; ràng buộc với request tương ứng.
B. Chỉ lưu key trong memory của worker đã nhận request đầu tiên.
C. Chấp nhận cùng key cho mọi payload và xử lý tất cả request lặp.
D. Xóa key ngay khi gửi response đầu tiên dù xử lý còn chưa commit.
Đáp án đúng: A

Câu 31. CORS bảo vệ loại tương tác nào và không thay thế cơ chế nào?
A. Xác thực danh tính người gọi API trước khi xử lý request.
B. Phân quyền caller trên object và function phía server.
C. Mã hóa request body giữa browser và API server.
D. Kiểm soát JavaScript cross-origin trong browser.
Đáp án đúng: D

Câu 32. Khi API dùng credential trong browser, cấu hình CORS nào phù hợp?
A. Dùng wildcard origin cùng credentials cho mọi website.
B. Allowlist origin cụ thể và bật credentials có chủ đích.
C. Phản chiếu mọi Origin header và luôn bật credentials.
D. Tắt kiểm tra origin vì access token đã được gửi trong request.
Đáp án đúng: B

Câu 33. TLS giúp bảo vệ API trên đường truyền bằng cách nào?
A. Phân quyền người dùng theo object ID và tenant ID.
B. Mã hóa đường truyền và xác thực server certificate.
C. Giới hạn số request theo identity và endpoint.
D. Xác thực schema JSON trước khi lưu dữ liệu vào database.
Đáp án đúng: B

Câu 34. Khi phát hành API version mới, nhóm vận hành cần bảo đảm điều gì?
A. Giữ bản cũ vĩnh viễn vì client cũ không thể được nâng cấp.
B. Bỏ authorization ở bản mới để tránh phá vỡ tương thích.
C. Giữ security parity và quản lý deprecation có kế hoạch.
D. Chỉ bảo vệ version mới vì version cũ không còn được phát triển.
Đáp án đúng: C

Câu 35. Audit log cho API nên ghi nhận dữ liệu nào để hỗ trợ điều tra?
A. Toàn bộ access token, password và request body để phục vụ audit.
B. Chỉ IP và user-agent vì không cần biết hành động trên object.
C. Principal, action, object, outcome và correlation ID.
D. Chỉ status code tổng hợp mà không cần identity hoặc thời điểm.
Đáp án đúng: C

Câu 36. Tín hiệu nào có thể chỉ ra API đang bị dò quét hoặc lạm dụng?
A. Số lượng 200 tăng nhẹ trong giờ làm việc bình thường.
B. Phát hiện mẫu lỗi quyền và hành vi dò tài nguyên.
C. Số phiên bản client cũ giảm dần sau khi phát hành.
D. Số health check nội bộ ổn định theo chu kỳ.
Đáp án đúng: B

Câu 37. Kiểm thử BOLA nên tập trung vào tình huống nào?
A. User không đăng nhập thử gọi endpoint health công khai.
B. Kiểm tra chéo quyền giữa hai người dùng hoặc tenant.
C. Admin thử cập nhật object trong tenant mình quản lý.
D. Client gửi JSON sai cú pháp và nhận về lỗi validation.
Đáp án đúng: B

Câu 38. Kiểm thử BFLA nên bao gồm trường hợp nào?
A. User đọc object cùng tenant đã được cấp quyền rõ ràng.
B. Client gửi request thiếu field bắt buộc theo schema.
C. Thử endpoint đặc quyền với tài khoản quyền thấp.
D. Browser gửi preflight OPTIONS từ origin khác.
Đáp án đúng: C

Câu 39. Kiểm thử mass assignment cần xác minh điều gì?
A. Gửi request body hợp lệ và xác minh JSON parse thành công.
B. Đổi header Accept và xác minh server trả đúng content type.
C. Thử field đặc quyền và kiểm tra server không bind chúng.
D. Gửi request lặp lại và xác minh API trả cùng status code.
Đáp án đúng: C

Câu 40. Kiểm thử SSRF nên bao gồm những đường đi nào?
A. Kiểm tra các đường dẫn URL có thể tới mạng riêng.
B. Chỉ URL HTTPS công khai với certificate hợp lệ và không redirect.
C. URL sai cú pháp bị từ chối trước khi tạo outbound connection.
D. URL trỏ tới host allowlist và trả nội dung mong đợi.
Đáp án đúng: A
