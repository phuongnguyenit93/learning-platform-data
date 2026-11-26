Câu 01. Nguyên nhân cốt lõi khiến truy vấn SQL dễ bị injection là gì?
A. Ứng dụng dùng kết nối mã hóa để gửi truy vấn tới máy chủ.
B. Cơ sở dữ liệu lưu nhiều bản ghi trong cùng một bảng.
C. Ghép dữ liệu vào chuỗi SQL trước khi thực thi.
D. Ứng dụng không giới hạn số dòng trả về từ truy vấn.
Đáp án đúng: C

Câu 02. Khi truy vấn SQL cần lọc theo giá trị người dùng nhập, cách nào an toàn nhất?
A. Kiểm tra chuỗi không chứa từ khóa SQL rồi nối vào câu lệnh.
B. Mã hóa chuỗi đầu vào rồi nối vào câu SQL trước khi chạy.
C. Giữ câu SQL cố định, truyền giá trị qua bind parameters.
D. Xóa ký tự đặc biệt khỏi đầu vào bằng danh sách cấm.
Đáp án đúng: C

Câu 03. Một truy vấn cần chọn tên cột do người dùng chọn từ giao diện. Cách xử lý phù hợp là gì?
A. Escape tên cột bằng hàm dành cho giá trị chuỗi SQL.
B. Ánh xạ lựa chọn sang danh sách tên cột được cho phép.
C. Nhận tên cột tự do rồi kiểm tra sau khi truy vấn chạy.
D. Truyền tên cột như một bind parameter trong câu SQL.
Đáp án đúng: B

Câu 04. Tìm kiếm SQL dùng LIKE và cần coi ký tự phần trăm do người dùng nhập là ký tự thường. Cần làm gì?
A. Nối trực tiếp giá trị vào mẫu LIKE sau khi trim khoảng trắng.
B. Bind giá trị và escape ký tự wildcard theo quy tắc LIKE.
C. Chỉ dùng HTML encoding trước khi truyền giá trị vào LIKE.
D. Tắt collation để cơ sở dữ liệu bỏ qua wildcard.
Đáp án đúng: B

Câu 05. Một bộ lọc SQL nhận danh sách ID có số phần tử thay đổi. Cách tạo truy vấn phù hợp là gì?
A. Dùng stored procedure để tự nối mọi ID thành câu lệnh.
B. Nối danh sách ID thành đoạn SQL sau khi kiểm tra kiểu số.
C. Tạo placeholder tương ứng từng ID và bind từng giá trị.
D. Bind toàn bộ danh sách thành một chuỗi duy nhất trong IN.
Đáp án đúng: C

Câu 06. Stored procedure vẫn có nguy cơ SQL injection trong tình huống nào?
A. Procedure chỉ truy vấn bảng cố định bằng câu lệnh tĩnh.
B. Procedure chạy dưới tài khoản có quyền đọc giới hạn.
C. Nối dữ liệu vào dynamic SQL trong procedure.
D. Procedure nhận tham số có kiểu dữ liệu rõ ràng và bind chúng.
Đáp án đúng: C

Câu 07. Một ORM cung cấp hàm raw query; nhóm phát triển nối chuỗi tìm kiếm vào SQL thô. Đánh giá nào đúng?
A. ORM không tự bảo vệ đoạn SQL được tạo bằng nối chuỗi.
B. ORM luôn tự tham số hóa mọi chuỗi truyền vào raw query.
C. ORM ngăn injection miễn là model đã khai báo schema.
D. ORM chỉ cần escape dữ liệu khi cơ sở dữ liệu dùng NoSQL.
Đáp án đúng: A

Câu 08. API nhận bộ lọc JSON cho cơ sở dữ liệu document. Cách nào giảm nguy cơ query operator injection?
A. Mã hóa Base64 JSON rồi gửi nguyên nội dung tới database.
B. Chuyển nguyên JSON của client thành query object của database.
C. Chỉ giới hạn kích thước JSON trước khi chuyển thành query.
D. Xác thực schema và kiểu dữ liệu, rồi tự dựng query được phép.
Đáp án đúng: D

Câu 09. Một endpoint NoSQL nhận giá trị tìm kiếm nhưng chấp nhận cả object thay vì chuỗi. Rủi ro chính là gì?
A. Đầu vào có thể làm thay đổi cấu trúc và toán tử của truy vấn.
B. Object luôn được so sánh như giá trị literal trong mọi driver.
C. Kiểu object chỉ ảnh hưởng định dạng kết quả trả về.
D. Cơ sở dữ liệu sẽ tự chuyển mọi object thành chuỗi an toàn.
Đáp án đúng: A

Câu 10. API cập nhật document cho phép client gửi toàn bộ object hồ sơ. Cách nào hạn chế mass assignment và operator injection?
A. Chấp nhận mọi trường JSON sau khi xác thực người dùng đăng nhập.
B. Xóa trường có tiền tố ký hiệu rồi cập nhật object còn lại.
C. Chỉ nhận trường được phép rồi tự dựng lệnh update.
D. Dùng quyền database cao hơn để cập nhật object nguyên trạng.
Đáp án đúng: C

Câu 11. Một ứng dụng cần gọi chương trình hệ điều hành với tham số do người dùng cung cấp. Cách nào an toàn hơn?
A. Chỉ chặn dấu chấm phẩy rồi thực thi chuỗi lệnh.
B. Gọi executable cố định, truyền riêng từng đối số.
C. Nối executable và tham số thành một chuỗi rồi chạy qua shell.
D. Escape dấu nháy trong chuỗi lệnh trước khi gọi shell.
Đáp án đúng: B

Câu 12. Ngay cả khi không gọi shell, tham số tên file vẫn có thể gây vấn đề nào?
A. Path traversal hoặc option injection vẫn xảy ra.
B. API truyền argv luôn loại bỏ quyền truy cập ngoài thư mục.
C. Tên file không thể ảnh hưởng chương trình được gọi.
D. Hệ điều hành tự diễn giải mọi tham số như câu lệnh shell.
Đáp án đúng: A

Câu 13. Vì sao blacklist ký tự thường không phải biện pháp chính để chống command injection?
A. Mọi shell đều dùng cùng một bộ ký tự cấm cố định.
B. Cách diễn giải phụ thuộc shell và quoting.
C. Blacklist làm mất khả năng xác thực danh tính người gọi.
D. Command injection chỉ xảy ra khi tham số là dữ liệu nhị phân.
Đáp án đúng: B

Câu 14. Một bộ lọc LDAP tạo search filter từ tên người dùng. Biện pháp nào phù hợp?
A. Chỉ kiểm tra độ dài tên rồi ghép trực tiếp vào filter.
B. HTML-encode tên người dùng trước khi ghép vào filter LDAP.
C. Base64-encode filter sau khi nối các thuộc tính tìm kiếm.
D. Escape dữ liệu theo cú pháp LDAP filter.
Đáp án đúng: D

Câu 15. Vì sao phải phân biệt LDAP filter escaping với DN escaping?
A. Filter và DN dùng quy tắc escape khác nhau.
B. DN escaping chỉ cần cho mật khẩu còn filter cho username.
C. Filter escaping chỉ áp dụng khi LDAP chạy qua TLS.
D. Hai ngữ cảnh dùng cùng cú pháp nhưng khác cách viết hoa.
Đáp án đúng: A

Câu 16. Một ứng dụng tạo XPath bằng cách nối giá trị tìm kiếm vào biểu thức. Cách phòng vệ nào tốt hơn?
A. HTML-encode giá trị trước khi nối vào biểu thức XPath.
B. Dùng biến XPath hoặc API truy vấn có hỗ trợ tham số.
C. Mã hóa XML toàn bộ biểu thức sau khi nối dữ liệu.
D. Chặn dấu ngoặc vuông rồi tiếp tục tạo XPath bằng chuỗi.
Đáp án đúng: B

Câu 17. Trong server-side template injection, lỗi thiết kế thường nằm ở đâu?
A. Template chỉ hiển thị nội dung đã được kiểm tra kiểu.
B. Template được biên dịch một lần và nhận dữ liệu theo biến riêng.
C. Dữ liệu bị diễn giải như template thực thi.
D. Ứng dụng dùng template tĩnh với autoescaping phù hợp.
Đáp án đúng: C

Câu 18. Autoescaping của template engine có giới hạn quan trọng nào?
A. Nó tự kiểm tra quyền truy cập của người dùng trên dữ liệu.
B. Autoescape phải phù hợp với ngữ cảnh hiển thị.
C. Nó thay thế được sandbox và quản lý quyền của template.
D. Nó luôn vô hiệu hóa mọi loại injection trong ứng dụng.
Đáp án đúng: B

Câu 19. Khi cho phép người dùng tùy biến template, kiểm soát nào cần được cân nhắc?
A. Giới hạn khả năng template và không cấp đối tượng nhạy cảm.
B. Cho template quyền truy cập đầy đủ vào môi trường máy chủ.
C. Chỉ kiểm tra template có đuôi file thuộc danh sách cho phép.
D. Tin rằng autoescaping sẽ ngăn template gọi tài nguyên nội bộ.
Đáp án đúng: A

Câu 20. Stored XSS xảy ra trong tình huống nào?
A. Nội dung độc hại được lưu rồi render cho người khác.
B. Ứng dụng lưu dữ liệu nhưng không bao giờ hiển thị lại.
C. Dữ liệu phản hồi chỉ tồn tại trong URL của một request.
D. Trình duyệt chặn mọi script trước khi đọc nội dung HTML.
Đáp án đúng: A

Câu 21. Khi hiển thị nội dung người dùng trong HTML text node, biện pháp nào phù hợp?
A. Escape dữ liệu theo cú pháp SQL trước khi đưa vào HTML.
B. Mã hóa toàn bộ response bằng Base64 trước khi gửi.
C. Chỉ validate độ dài dữ liệu khi người dùng gửi biểu mẫu.
D. Encode output theo ngữ cảnh HTML text trước khi render.
Đáp án đúng: D

Câu 22. Một giao diện dùng JavaScript đưa dữ liệu không tin cậy vào DOM. Lựa chọn nào an toàn hơn?
A. Gán dữ liệu vào innerHTML sau khi xóa từ khóa script.
B. Chèn chuỗi vào HTML rồi dựa vào CSP để lọc nội dung.
C. Dùng textContent thay cho innerHTML.
D. Mã hóa URL dữ liệu trước khi gán vào innerHTML.
Đáp án đúng: C

Câu 23. Khi đặt dữ liệu vào thuộc tính HTML có dấu nháy, cần làm gì?
A. Loại bỏ khoảng trắng rồi đặt giá trị trực tiếp vào markup.
B. Encode theo ngữ cảnh thuộc tính và luôn đặt giá trị trong dấu nháy.
C. Chỉ encode ký tự dấu gạch chéo trước khi render thuộc tính.
D. Dùng JavaScript string escaping cho mọi thuộc tính HTML.
Đáp án đúng: B

Câu 24. Một liên kết HTML nhận URL do người dùng cung cấp. Kiểm soát nào cần kết hợp?
A. Chỉ kiểm tra hostname rồi ghép URL vào thuộc tính.
B. Base64-encode URL để trình duyệt tự giải mã khi nhấp.
C. Chỉ HTML-encode URL mà không kiểm tra scheme được phép.
D. Cho phép scheme phù hợp và encode URL trong ngữ cảnh thuộc tính.
Đáp án đúng: D

Câu 25. Dữ liệu không tin cậy cần được đưa vào một đoạn JavaScript. Cách nào nên ưu tiên?
A. HTML-encode chuỗi rồi nối trực tiếp vào JavaScript source.
B. Tránh ghép mã động; dùng dữ liệu JSON an toàn ngoài mã thực thi.
C. Escape dấu nháy đơn rồi đặt dữ liệu trong script inline.
D. URL-encode dữ liệu rồi chèn vào biểu thức JavaScript.
Đáp án đúng: B

Câu 26. Một giá trị người dùng được đưa vào CSS style. Biện pháp nào phù hợp?
A. Dùng SQL parameterization trước khi gán giá trị vào style.
B. HTML-encode chuỗi rồi ghép vào bất kỳ thuộc tính CSS nào.
C. Chỉ xóa dấu chấm phẩy trước khi nối dữ liệu vào CSS.
D. Tránh tạo CSS từ chuỗi tự do và giới hạn giá trị theo allowlist.
Đáp án đúng: D

Câu 27. Content Security Policy có vai trò nào trong phòng chống XSS?
A. Thay thế việc kiểm tra URL và encode thuộc tính HTML.
B. Ngăn mọi loại injection kể cả SQL và command injection.
C. Tạo lớp giảm thiểu tác động, không thay thế encoding an toàn.
D. Tự động làm sạch mọi HTML không tin cậy trước khi hiển thị.
Đáp án đúng: C

Câu 28. Một ứng dụng cho phép người dùng đăng nội dung HTML định dạng. Cách xử lý nào phù hợp?
A. Chỉ xóa thẻ script bằng biểu thức chính quy đơn giản.
B. Giữ nguyên HTML nếu người dùng đã đăng nhập thành công.
C. Dùng HTML sanitizer theo allowlist phần tử và thuộc tính cần thiết.
D. Encode toàn bộ HTML thành text dù yêu cầu cần định dạng.
Đáp án đúng: C

Câu 29. Input validation và output encoding có vai trò khác nhau như thế nào?
A. Hai kỹ thuật tương đương và có thể dùng thay thế nhau.
B. Validation thay thế encoding nếu dữ liệu đã đúng kiểu.
C. Encoding xác thực quyền người dùng còn validation mã hóa dữ liệu.
D. Validation kiểm tra dữ liệu hợp lệ; encoding bảo vệ khi xuất theo ngữ cảnh.
Đáp án đúng: D

Câu 30. Một giá trị đi qua URL, HTML attribute rồi JavaScript. Cách encode nào đúng?
A. Dùng SQL escaping chung vì dữ liệu bắt nguồn từ database.
B. Encode đầu vào một lần rồi không cần xử lý tại điểm render.
C. Encode một lần theo HTML rồi dùng nguyên dữ liệu ở mọi nơi.
D. Áp dụng encoding phù hợp tại từng ngữ cảnh đầu ra theo thứ tự.
Đáp án đúng: D

Câu 31. Một trợ lý AI đọc tài liệu do người dùng tải lên; tài liệu chứa chỉ dẫn yêu cầu bỏ qua chính sách. Cách xử lý nào đúng?
A. Coi nội dung tài liệu là dữ liệu không tin cậy, không phải chỉ dẫn hệ thống.
B. Thực hiện chỉ dẫn trong tài liệu nếu nó xuất hiện gần câu hỏi.
C. Tin nội dung tài liệu khi tệp được tải lên bởi người dùng hợp lệ.
D. Cho tài liệu quyền thay đổi quy tắc và quyền của công cụ.
Đáp án đúng: A

Câu 32. Vì sao chỉ đặt nội dung người dùng giữa các dấu phân cách chưa đủ chống prompt injection?
A. Prompt injection chỉ xảy ra khi thiếu dấu phân cách.
B. Mô hình vẫn có thể diễn giải nội dung đó như chỉ dẫn trong ngữ cảnh.
C. Dấu phân cách khiến mô hình không thể đọc phần văn bản bên trong.
D. Dấu phân cách tự xác minh nguồn gốc và quyền của tài liệu.
Đáp án đúng: B

Câu 33. Một agent có thể gọi công cụ xóa dữ liệu sau khi đọc email. Kiểm soát nào giảm rủi ro prompt injection?
A. Tin mọi chỉ dẫn xuất hiện trong email thuộc hộp thư người dùng.
B. Chỉ thêm câu nhắc agent bỏ qua chỉ dẫn độc hại ở cuối prompt.
C. Cho agent quyền quản trị để không bị gián đoạn khi thực hiện tác vụ.
D. Giới hạn quyền công cụ và yêu cầu xác nhận cho hành động nhạy cảm.
Đáp án đúng: D

Câu 34. Một ứng dụng RAG đưa nhiều tài liệu vào context của mô hình. Cách giảm rò rỉ dữ liệu nào phù hợp?
A. Lọc quyền truy cập trước retrieval và chỉ đưa dữ liệu cần thiết vào context.
B. Truy xuất mọi tài liệu rồi yêu cầu mô hình tự chọn phần được phép.
C. Dùng một prompt chung và ẩn tên người dùng khỏi tài liệu.
D. Chỉ giới hạn số token mà không xét quyền của nguồn dữ liệu.
Đáp án đúng: A

Câu 35. Một ảnh hoặc tài liệu OCR chứa chỉ dẫn nhắm vào agent. Rủi ro này nên được hiểu thế nào?
A. Đó là prompt injection gián tiếp qua nội dung đa phương thức.
B. Đó là XSS vì mọi nội dung OCR đều chạy trong trình duyệt.
C. Đó là SQL injection vì OCR chuyển ảnh thành chuỗi ký tự.
D. Đó là lỗi xác thực vì hình ảnh không có chữ ký số.
Đáp án đúng: A

Câu 36. Khi kiểm thử endpoint có nguy cơ injection, bộ test nên tập trung vào điều gì?
A. Chỉ kiểm tra bộ lọc từ khóa có chặn các chuỗi đã biết.
B. Chỉ kiểm tra hiệu năng khi gửi request với kích thước lớn.
C. Chỉ kiểm tra ứng dụng có trả HTTP 200 cho dữ liệu bình thường.
D. Kiểm tra đầu vào thay đổi cú pháp hay cấu trúc thực thi ngoài dự kiến.
Đáp án đúng: D

Câu 37. SAST và DAST đóng góp khác nhau thế nào trong kiểm thử injection?
A. SAST kiểm tra runtime; DAST chỉ đọc source code tĩnh.
B. Cả hai chỉ kiểm tra dependency và phiên bản thư viện.
C. SAST rà mã nguồn; DAST quan sát hành vi ứng dụng đang chạy.
D. SAST thay thế kiểm thử thủ công còn DAST thay thế code review.
Đáp án đúng: C

Câu 38. Fuzz testing có thể giúp phát hiện injection bằng cách nào?
A. Tạo nhiều biến thể đầu vào để tìm cách phá vỡ giả định xử lý.
B. Thay thế kiểm tra quyền và xác thực trong các endpoint.
C. Chỉ gửi lại một payload cố định để đo thời gian phản hồi.
D. Tự chứng minh ứng dụng an toàn nếu không có crash.
Đáp án đúng: A

Câu 39. Một API trả lỗi SQL chi tiết kèm tên bảng và câu truy vấn cho client. Rủi ro nào phát sinh?
A. Tên bảng chỉ lộ metadata không liên quan đến injection.
B. Thông báo lỗi không ảnh hưởng nếu database dùng TLS.
C. Lỗi chi tiết tự động làm truy vấn trở nên an toàn hơn.
D. Thông tin nội bộ giúp người ngoài hiểu cấu trúc và tinh chỉnh tấn công.
Đáp án đúng: D

Câu 40. Một ứng dụng dùng nhiều parser và interpreter cho cùng dữ liệu. Nguyên tắc phòng vệ tổng quát nào phù hợp?
A. Dùng một hàm escape chung cho mọi ngôn ngữ và parser.
B. Giữ dữ liệu tách khỏi cú pháp và encode hoặc validate theo từng ngữ cảnh.
C. Chỉ lọc dữ liệu tại giao diện trước khi gửi tới máy chủ.
D. Tin rằng dữ liệu từ hệ thống nội bộ không cần kiểm tra.
Đáp án đúng: B
