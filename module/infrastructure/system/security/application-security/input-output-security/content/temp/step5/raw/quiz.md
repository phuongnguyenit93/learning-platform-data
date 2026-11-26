Câu 1. Input validation trong API nên xác nhận điều gì?
A. Chỉ kiểm tra token còn hạn trước khi đọc body request.
B. Chỉ kiểm tra chuỗi có chứa ký tự đặc biệt hay không.
C. Chỉ xác minh request dùng HTTPS và đúng Content-Type.
D. Kiểm tra kiểu, cấu trúc, miền giá trị và rule nghiệp vụ.
Đáp án đúng: D

Câu 2. Canonicalization có vai trò gì trước khi áp dụng validation?
A. Mã hóa dữ liệu để browser không hiển thị ký tự đặc biệt.
B. Xóa mọi ký tự không phải chữ số trước khi parse.
C. Thay output encoding bằng một bộ lọc input toàn cục.
D. Chuẩn hóa biểu diễn trước khi validate và so sánh.
Đáp án đúng: D

Câu 3. Vì sao allowlist thường an toàn hơn denylist khi kiểm tra input?
A. Chỉ nhận định dạng và giá trị nằm trong tập dự kiến.
B. Chặn vài chuỗi tấn công đã biết rồi cho phép phần còn lại.
C. Chỉ kiểm tra ký tự đầu cuối của chuỗi do client gửi.
D. Tin dữ liệu nếu request đã được truyền qua HTTPS.
Đáp án đúng: A

Câu 4. Sanitization khác output encoding ở điểm nào?
A. Sanitization xác minh danh tính; encoding quyết định quyền object.
B. Sanitization chỉ dùng cho JSON; encoding chỉ dùng cho SQL.
C. Sanitizer giới hạn markup; encoding bảo vệ dữ liệu tại sink.
D. Hai thao tác giống nhau và thay thế được cho nhau.
Đáp án đúng: C

Câu 5. Khi hiển thị dữ liệu không tin cậy trong HTML text node, cần làm gì?
A. URL-encode toàn bộ trang rồi đặt vào text node HTML.
B. Loại dấu cách và dấu câu khỏi nội dung trước khi render.
C. HTML-encode ký tự đặc biệt trước khi render text.
D. Chỉ kiểm tra UTF-8 rồi chèn trực tiếp vào HTML.
Đáp án đúng: C

Câu 6. Khi đưa dữ liệu vào HTML attribute, cách xử lý nào phù hợp?
A. Chỉ encode dấu nháy đơn rồi dùng attribute không quote.
B. Quote attribute và encode theo ngữ cảnh attribute.
C. JavaScript-encode toàn bộ tag trước khi gán attribute.
D. Loại dấu cách nhưng giữ nguyên dấu nháy và control character.
Đáp án đúng: B

Câu 7. Vì sao không nên nối chuỗi input trực tiếp vào inline JavaScript?
A. Input có thể thoát literal và trở thành mã chạy.
B. JavaScript tự encode mọi chuỗi lấy từ HTTP request.
C. Inline script không thể đọc dữ liệu do server render.
D. CORS chặn mọi script có chứa dữ liệu động từ server.
Đáp án đúng: A

Câu 8. Khi chèn dữ liệu vào URL query parameter, nên encode thế nào?
A. Encode riêng query component rồi ghép vào URL đã kiểm tra.
B. Encode toàn bộ URL sau khi ghép scheme, host và query.
C. HTML-encode giá trị rồi dùng nguyên trong query string.
D. Base64-encode URL để server tự xác minh đích an toàn.
Đáp án đúng: A

Câu 9. API nên tạo JSON response an toàn bằng cách nào?
A. Ghép key và value thủ công sau khi xóa dấu ngoặc kép.
B. Dùng JSON serializer chuẩn thay vì tự nối chuỗi JSON.
C. HTML-encode JSON rồi khai báo response là text/plain.
D. Chuyển mọi giá trị thành chuỗi để parser khỏi kiểm tra kiểu.
Đáp án đúng: B

Câu 10. Biện pháp chính để ngăn SQL injection trong truy vấn có tham số là gì?
A. Escape dấu nháy thủ công rồi nối input vào SQL.
B. Base64-encode input trước khi ghép vào câu SQL.
C. Ẩn lỗi SQL nhưng vẫn nối chuỗi query động.
D. Dùng prepared statement hoặc parameterized query.
Đáp án đúng: D

Câu 11. Khi gọi chương trình hệ điều hành với dữ liệu người dùng, cách nào giảm shell injection?
A. Nối input vào command string rồi quote bằng dấu nháy kép.
B. Dùng executable và argument array, không qua shell.
C. Base64-encode input rồi thực thi qua shell mặc định.
D. Chặn dấu chấm phẩy nhưng cho phép ký tự shell khác.
Đáp án đúng: B

Câu 12. Khi tạo LDAP search filter từ input, cần xử lý ký tự đặc biệt ra sao?
A. Escape ký tự đặc biệt bằng LDAP filter builder.
B. URL-encode filter rồi nối trực tiếp vào biểu thức LDAP.
C. Chỉ xóa dấu ngoặc tròn ở đầu chuỗi input.
D. Chuyển input sang chữ thường để vô hiệu cú pháp LDAP.
Đáp án đúng: A

Câu 13. Reflected XSS xảy ra trong tình huống nào?
A. Request data được phản chiếu vào HTML mà thiếu encoding.
B. Payload lưu trong database nhưng không bao giờ hiển thị.
C. Server thực thi SQL query có parameter do client gửi.
D. Browser chặn script vì response thiếu CORS header.
Đáp án đúng: A

Câu 14. Với dữ liệu lưu trong database rồi hiển thị lại, cách phòng stored XSS phù hợp là gì?
A. Sanitize lúc ghi database rồi render trực tiếp ở mọi context.
B. Encode theo context mỗi lần dữ liệu được hiển thị.
C. Chỉ lọc input lúc đăng nhập vì stored data đáng tin.
D. Mã hóa backup database để browser không chạy nội dung.
Đáp án đúng: B

Câu 15. Trong DOM, API nào phù hợp để đưa chuỗi không tin cậy vào nội dung văn bản?
A. Gán chuỗi bằng `textContent`, không parse HTML.
B. Dùng `innerHTML` sau khi xóa riêng thẻ script.
C. Dùng `document.write` để browser tự escape chuỗi.
D. Dùng `eval` để parse chuỗi rồi gán vào DOM.
Đáp án đúng: A

Câu 16. Khi sản phẩm cho phép người dùng gửi rich HTML, cách xử lý nào phù hợp?
A. Xóa thẻ script bằng regex rồi cho phép mọi tag còn lại.
B. HTML-encode toàn bộ dù ứng dụng cần hỗ trợ rich text.
C. Lọc tag, attribute và scheme bằng sanitizer tin cậy.
D. Cho phép mọi tag và dựa vào CSP để làm sạch markup.
Đáp án đúng: C

Câu 17. Khi kiểm tra đường dẫn file có thể chứa `../`, thứ tự xử lý nào an toàn?
A. Kiểm tra chuỗi thô trước decode rồi nối vào thư mục gốc.
B. Normalize và resolve path rồi xác minh nằm trong base.
C. Decode lặp đến hết `%` rồi tin đường dẫn thu được.
D. Chặn `../` trước khi chuẩn hóa separator và symlink.
Đáp án đúng: B

Câu 18. Vì sao chỉ tìm chuỗi `../` chưa đủ để chống path traversal?
A. Path traversal chỉ dùng `../` nên so khớp chuỗi là đủ.
B. Hệ điều hành luôn chặn đường dẫn vượt thư mục ứng dụng.
C. Resolve thực tế chịu ảnh hưởng của encoding và symlink.
D. URL encoding khiến đường dẫn không thể truy cập filesystem.
Đáp án đúng: C

Câu 19. Khi nhận file upload, tổ hợp kiểm tra nào phù hợp?
A. Tin extension client khai báo và giữ nguyên filename gốc.
B. Chỉ kiểm tra MIME header mà không đọc file bytes.
C. Kiểm extension, bytes thực, kích thước và tên lưu.
D. Quét antivirus một lần rồi nhận mọi loại file.
Đáp án đúng: C

Câu 20. Để giảm rủi ro khi phục vụ file người dùng upload, nên lưu và phân phối thế nào?
A. Lưu trong thư mục thực thi để URL file dễ truy cập.
B. Lưu ngoài web root hoặc origin riêng có kiểm soát.
C. Dùng filename client gửi làm đường dẫn public trực tiếp.
D. Phục vụ mọi file inline để browser tự nhận diện nội dung.
Đáp án đúng: B

Câu 21. Giải nén archive do người dùng cung cấp cần ngăn kiểu tấn công nào?
A. SQL injection do tên archive được nối vào query.
B. CSRF do archive chứa nhiều entry trùng tên.
C. Zip Slip cho phép entry thoát khỏi thư mục giải nén.
D. Session fixation do archive giữ cookie người tải.
Đáp án đúng: C

Câu 22. Vì sao SVG hoặc HTML upload cần được xem là nội dung có thể thực thi?
A. SVG và HTML luôn là ảnh tĩnh nên không thể thực thi.
B. Chỉ file JavaScript mới có thể chạy mã trong browser.
C. HTTPS tự vô hiệu script nhúng trong file người dùng tải.
D. Có thể chứa script được browser diễn giải.
Đáp án đúng: D

Câu 23. Header `X-Content-Type-Options: nosniff` hỗ trợ kiểm soát điều gì?
A. Mã hóa response body để proxy không đọc được nội dung.
B. Xác thực upload dựa trên extension của filename.
C. Ngăn client gửi request có Content-Type ngoài allowlist.
D. Ngăn browser MIME-sniff sang loại nội dung khác.
Đáp án đúng: D

Câu 24. Log injection qua CR/LF có thể được giảm thiểu bằng cách nào?
A. Structured log và encode CR/LF trong field không tin cậy.
B. Nối nguyên input vào log vì log file không được browser render.
C. Chỉ thay dấu nháy kép vì CR/LF không giả mạo record.
D. Base64 toàn bộ log line rồi bỏ qua ranh giới record.
Đáp án đúng: A

Câu 25. Log ứng dụng nên xử lý access token và mật khẩu ra sao?
A. Redact token, password và dữ liệu nhạy cảm khỏi log.
B. Ghi đầy đủ token và password để hỗ trợ điều tra sau này.
C. Chỉ che token trong response, log nội bộ giữ nguyên.
D. Hash log line sau khi ghi để secret không còn bị lộ.
Đáp án đúng: A

Câu 26. Khi API gặp lỗi nội bộ, response nào an toàn hơn cho client?
A. Trả stack trace, SQL và đường dẫn nội bộ cho caller.
B. Thông điệp an toàn cho client; chi tiết giữ trong log.
C. Trả nguyên exception message để client sửa backend.
D. Trả HTTP 200 cùng lỗi nội bộ dưới dạng HTML.
Đáp án đúng: B

Câu 27. JSON serializer có làm chuỗi JSON an toàn khi chèn vào HTML script context không?
A. Có; mọi JSON string đều vô hiệu HTML và JavaScript khi nhúng.
B. Có; `application/json` khiến browser không thể parse nội dung khác.
C. JSON encoding không làm an toàn chuỗi ở HTML/JS sink.
D. Không; JSON serializer chỉ hỗ trợ payload ASCII.
Đáp án đúng: C

Câu 28. CSV export có thể gây rủi ro gì khi ô dữ liệu bắt đầu bằng ký tự công thức?
A. SQL injection vì CSV parser thực thi truy vấn trên database.
B. XSS trực tiếp trong mọi trình duyệt khi mở file CSV.
C. Ô CSV có thể bị ứng dụng bảng tính chạy như formula.
D. Path traversal vì dấu bằng đổi thư mục lưu file.
Đáp án đúng: C

Câu 29. Regex validation có thể dẫn đến ReDoS trong trường hợp nào?
A. Input chứa Unicode hợp lệ nhưng không thuộc ASCII.
B. Regex backtracking có thể gây thời gian xử lý cực lớn.
C. Input có nhiều field optional được schema cho phép.
D. Input dùng UTF-8 thay vì UTF-16 để truyền dữ liệu.
Đáp án đúng: B

Câu 30. Khi JSON hoặc query string có nhiều giá trị cho cùng một key, server nên xử lý thế nào?
A. Chọn ngẫu nhiên một giá trị để phân tán request tới handler.
B. Gộp mọi giá trị thành chuỗi rồi dùng giá trị đầu tiên.
C. Tin parser gọi sau cùng sẽ tự hợp nhất kết quả.
D. Reject duplicate keys hoặc định nghĩa policy duy nhất.
Đáp án đúng: D

Câu 31. Vì sao cần giới hạn kích thước, độ sâu và số phần tử của input?
A. Bảo đảm mọi request được xử lý trong một thread duy nhất.
B. Giảm số lần kiểm tra quyền vì input có kích thước nhỏ.
C. Ngăn parser và downstream tiêu tốn CPU, RAM hoặc I/O quá mức.
D. Ngăn browser cache response khi request có nhiều phần tử.
Đáp án đúng: C

Câu 32. Unicode normalization hữu ích thế nào trong kiểm tra và so sánh input?
A. Chuyển mọi Unicode thành ASCII bằng cách xóa dấu.
B. Dùng byte length thay cho quy tắc ký tự với mọi chuỗi.
C. Bỏ normalization vì chuỗi nhìn giống luôn có cùng bytes.
D. Chuẩn hóa Unicode trước khi so sánh và áp dụng rule.
Đáp án đúng: D

Câu 33. Client-side validation có thay thế được validation phía server không?
A. Có; browser validate nên API có thể tin mọi request.
B. Có; hai bên dùng cùng schema thì server khỏi kiểm tra.
C. Không; server chỉ cần xác nhận request dùng HTTPS.
D. Server phải tự validate; client check chỉ hỗ trợ UX.
Đáp án đúng: D

Câu 34. Validation hợp lệ có đồng nghĩa caller được phép thao tác trên tài nguyên không?
A. Có; dữ liệu hợp lệ đồng nghĩa caller được sửa object.
B. Dữ liệu hợp lệ không tự cấp quyền truy cập tài nguyên.
C. Có; schema xác định role và quyền của người gửi.
D. Không; authorization chỉ cần cho endpoint quản trị.
Đáp án đúng: B

Câu 35. Trong template engine, vì sao không nên đánh dấu tùy tiện chuỗi input là safe?
A. Template engine luôn escape lại chuỗi safe trước khi render.
B. Safe marker có thể tắt auto-escaping và tạo XSS.
C. Safe marker chỉ ảnh hưởng màu sắc và kiểu chữ.
D. Safe marker tự xác minh người dùng đã có quyền.
Đáp án đúng: B

Câu 36. Content Security Policy giúp bảo vệ ứng dụng web theo cách nào?
A. Policy browser hạn chế nguồn script và hành vi.
B. Thay thế output encoding cho mọi HTML context.
C. Xác thực user trước khi API đọc hoặc sửa object.
D. Mã hóa file upload để loại bỏ script độc hại.
Đáp án đúng: A

Câu 37. Vì sao output encoding phải được chọn theo context nơi dữ liệu được render?
A. Một bộ HTML escaping duy nhất an toàn cho mọi sink.
B. Validation lúc nhận dữ liệu đủ loại bỏ nguy cơ khi render.
C. Chỉ encode `<` vì các context khác dùng cùng parser.
D. Encoding phụ thuộc parser và context tại điểm render.
Đáp án đúng: D

Câu 38. Kiểm thử XSS và injection nên bao gồm cách tiếp cận nào?
A. Chỉ thử chuỗi script trong một trang HTML tĩnh.
B. Chỉ quét dependency vì XSS luôn do thư viện cũ.
C. Chỉ kiểm response status mà không xem dữ liệu được render.
D. Thử payload ở từng context và đường đi dữ liệu.
Đáp án đúng: D

Câu 39. Property-based hoặc fuzz testing giúp ích gì cho input handling?
A. Sinh nhiều input để tìm edge case và invariant bị phá.
B. Thay hoàn toàn review thủ công và kiểm thử phân quyền.
C. Chỉ tạo chuỗi ASCII ngẫu nhiên để kiểm tra giao diện.
D. Chứng minh không còn lỗ hổng nếu fuzz chạy đủ lâu.
Đáp án đúng: A

Câu 40. Khi đưa dữ liệu không tin cậy vào log, API response và shell command, nguyên tắc chung nào cần áp dụng?
A. Chỉ lọc ký tự nguy hiểm một lần rồi dùng lại mọi nơi.
B. Tin dữ liệu từ API vì log và shell đều là thành phần nội bộ.
C. Kiểm soát dữ liệu theo ngữ cảnh và tránh coi input là mã.
D. Base64 mọi input trước khi gửi tới log, API và shell.
Đáp án đúng: C
