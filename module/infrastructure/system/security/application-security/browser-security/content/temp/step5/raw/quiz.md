Một origin trong trình duyệt được xác định bởi những thành phần nào?
A. Scheme, host và path.
B. Scheme, host và port.
C. Host, path và query string.
D. Tên miền đăng ký và path gốc.
Đáp án đúng: B

Same-Origin Policy chủ yếu hạn chế hành vi nào của script?
A. Ngăn trang nhúng mọi hình ảnh từ một origin khác.
B. Ngăn tab điều hướng đến một URL thuộc origin khác.
C. Ngăn browser gửi bất kỳ request nào đến origin khác.
D. Ngăn script đọc dữ liệu được bảo vệ từ origin khác.
Đáp án đúng: D

CORS cho phép server thực hiện điều gì đối với script ở origin khác?
A. Cho server từ xa đọc DOM và storage của tab gọi.
B. Cho phép người dùng đăng nhập mà không xác minh danh tính.
C. Tắt kiểm tra quyền phía server cho API được gọi.
D. Cho phép script đọc response cross-origin khi server đồng ý.
Đáp án đúng: D

Khi request cross-origin cần preflight, trình duyệt thường gửi request nào trước?
A. Gửi HEAD để xem metadata trước request thật.
B. Gửi OPTIONS để hỏi method và header được phép.
C. Gửi GET để lấy cookie và token từ origin đích.
D. Gửi POST rỗng để kiểm tra server còn hoạt động.
Đáp án đúng: B

Header nào cho biết các method được phép trong CORS preflight?
A. Access-Control-Allow-Credentials.
B. Access-Control-Max-Age.
C. Access-Control-Expose-Headers.
D. Access-Control-Allow-Methods.
Đáp án đúng: D

Một request CORS có credentials cần response đáp ứng điều kiện nào?
A. Origin cụ thể và Allow-Credentials là false.
B. Origin cụ thể và Allow-Credentials là true.
C. Wildcard origin và Allow-Credentials là true.
D. Wildcard origin và Allow-Headers liệt kê Cookie.
Đáp án đúng: B

Server phản hồi Access-Control-Allow-Origin theo origin request; header nào hỗ trợ cache đúng theo biến thể?
A. Vary: Origin làm cache phân biệt origin request.
B. Cache-Control: private ngăn mọi cache trung gian.
C. Access-Control-Max-Age đặt thời gian cache preflight.
D. Origin: * phân tách cache theo từng website gọi.
Đáp án đúng: A

Một request cross-origin dùng method đơn giản và header safelisted có đặc điểm nào?
A. Request đó luôn được đọc response mà không cần CORS header.
B. Browser tự chuyển request cross-origin thành same-origin.
C. Có thể bỏ preflight, nhưng CORS vẫn kiểm soát việc đọc response.
D. Request đó bỏ qua SOP và có thể đọc mọi response.
Đáp án đúng: C

Cookie không khai báo thuộc tính Domain thường được giới hạn thế nào?
A. Cookie chỉ gửi path hiện tại trên mọi host khác.
B. Cookie chỉ gửi đến đúng host đã tạo nó.
C. Cookie gửi đến mọi subdomain cùng registrable domain.
D. Cookie gửi đến mọi host cùng scheme và port.
Đáp án đúng: B

Thuộc tính Path của cookie nên được xem là cơ chế nào?
A. Path xác thực người dùng cho từng endpoint của ứng dụng.
B. Path cách ly mạnh các ứng dụng chạy trên cùng host.
C. Path giới hạn URL gửi cookie, không tạo ranh giới bảo mật.
D. Path mã hóa cookie trước khi trình duyệt lưu giá trị.
Đáp án đúng: C

Cookie cần được gửi trong ngữ cảnh cross-site để hỗ trợ luồng đăng nhập; cấu hình nào phù hợp?
A. SameSite=Lax đi kèm Domain.
B. SameSite=None đi kèm Path=/.
C. SameSite=Strict đi kèm HttpOnly.
D. SameSite=None đi kèm Secure.
Đáp án đúng: D

HttpOnly trên cookie phiên giúp giảm rủi ro nào?
A. Ngăn JavaScript đọc trực tiếp giá trị cookie.
B. Ngăn XSS thực hiện hành động bằng phiên hiện tại.
C. Ngăn trình duyệt tự gửi cookie trong request.
D. Ngăn server nhận cookie qua kết nối HTTP.
Đáp án đúng: A

Thuộc tính Secure trên cookie có tác dụng chính nào?
A. Mã hóa giá trị cookie bằng khóa của trình duyệt.
B. Ngăn JavaScript đọc cookie từ document.cookie.
C. Giới hạn gửi cookie qua kênh HTTPS an toàn.
D. Giới hạn cookie chỉ được gửi trong request POST.
Đáp án đúng: C

Vì sao cookie phiên tự động đính kèm request có thể tạo rủi ro CSRF?
A. SOP cho phép trang ngoài đọc nội dung cookie phiên.
B. Trình duyệt tự chuyển request GET thành request POST.
C. Trang ngoài có thể kích hoạt request kèm cookie phiên.
D. Cookie được gửi đến mọi server bất kể domain.
Đáp án đúng: C

Synchronizer token chống CSRF thường được kiểm tra như thế nào?
A. Server xác minh token khó đoán gắn với phiên hiện tại.
B. Browser tự kiểm tra token trước khi gửi request thay đổi trạng thái.
C. Server so sánh token với một secret cố định toàn ứng dụng.
D. Server chấp nhận token bất kỳ khớp một cookie không liên quan.
Đáp án đúng: A

Trong mô hình double-submit cookie, điều gì giúp token chống giả mạo tốt hơn?
A. Token dùng chung một giá trị cố định cho mọi phiên.
B. Token được ký hoặc ràng buộc mật mã với phiên.
C. Token được đặt trong URL để trình duyệt tự gửi.
D. Token chỉ chứa tên host và không cần kiểm tra.
Đáp án đúng: B

Kiểm tra Origin hoặc Referer trên request thay đổi trạng thái có vai trò nào?
A. Bảo đảm request đã bắt không thể bị phát lại.
B. Mã hóa body trước khi ứng dụng xử lý dữ liệu.
C. Thay thế xác thực và phân quyền phía server.
D. Kiểm tra nguồn gửi bổ sung bên cạnh CSRF token.
Đáp án đúng: D

Vì sao SameSite cookie không nên là biện pháp CSRF duy nhất?
A. Same-site và client cũ vẫn cần lớp CSRF bổ sung.
B. SameSite tự xác minh quyền của người dùng ở server.
C. SameSite chỉ có hiệu lực với cookie không có Secure.
D. SameSite ngăn mọi request cross-origin kể cả điều hướng.
Đáp án đúng: A

Một trang phản chiếu chuỗi từ query parameter vào HTML mà không mã hóa; đây là dạng XSS nào?
A. Stored XSS: nội dung độc hại được lưu và hiển thị lại.
B. DOM clobbering: phần tử HTML làm đổi tra cứu thuộc tính.
C. CSRF: browser có phiên hợp lệ bị dụ gửi request.
D. Reflected XSS: dữ liệu request được phản chiếu ngay.
Đáp án đúng: D

Một comment độc hại được lưu trong cơ sở dữ liệu và chạy khi người khác mở trang; đây là dạng nào?
A. DOM-based XSS: client script đưa dữ liệu vào DOM sink.
B. CSRF: browser có phiên hợp lệ bị dụ gửi request.
C. Stored XSS: nội dung độc hại được lưu và phát lại.
D. Reflected XSS: dữ liệu request phản chiếu vào response.
Đáp án đúng: C

JavaScript lấy dữ liệu từ location.hash rồi gán vào innerHTML; điểm yếu chính thuộc dạng nào?
A. CORS sai cấu hình khi API thiếu header cho phép.
B. DOM-based XSS: script đưa dữ liệu vào sink DOM không an toàn.
C. CSRF xảy ra khi browser tự gửi cookie xác thực.
D. Clickjacking che một nút nhạy cảm bằng frame trong suốt.
Đáp án đúng: B

Cách nào phù hợp khi chèn dữ liệu không tin cậy vào HTML text node?
A. Mã hóa URL rồi chèn nguyên chuỗi vào HTML.
B. Loại bỏ dấu ngoặc kép rồi giữ nguyên ký tự còn lại.
C. Dùng Base64 để trình duyệt tự giải mã an toàn.
D. Dùng output encoding phù hợp với ngữ cảnh HTML.
Đáp án đúng: D

Ứng dụng cho phép người dùng đăng nội dung rich text; cách phòng vệ nào phù hợp?
A. Sanitize rich text bằng allowlist thẻ và thuộc tính.
B. Escape toàn bộ nội dung rồi cho phép mọi thẻ.
C. Chặn ký tự nhỏ hơn và lớn hơn ở phía client.
D. Chỉ xóa thẻ script bằng biểu thức chính quy.
Đáp án đúng: A

CSP dùng nonce để cho phép inline script an toàn hơn cần điều kiện nào?
A. Nonce chỉ cần có trong thẻ script, policy không cần khai báo.
B. Nonce ngẫu nhiên theo response, khớp giữa header và script.
C. Nonce cố định được dùng chung qua mọi response.
D. Nonce được tạo từ URL và gửi trong query string.
Đáp án đúng: B

CSP hash phù hợp nhất với trường hợp nào?
A. Hash cho phép script động bất kỳ do người dùng nhập.
B. Hash cho phép script từ mọi origin HTTPS không cần nguồn.
C. Hash bật eval mà không cần directive script bổ sung.
D. Hash cho phép inline script tĩnh khớp nội dung policy.
Đáp án đúng: D

Content-Security-Policy-Report-Only được dùng để làm gì?
A. Chỉ áp dụng policy cho request cùng origin.
B. Tắt CSP trên trang sau lần vi phạm đầu tiên.
C. Chỉ báo cáo vi phạm, không chặn nội dung.
D. Chặn nội dung vi phạm và bỏ qua báo cáo.
Đáp án đúng: C

Trong CSP, default-src thường đóng vai trò nào?
A. Chỉ áp dụng cho tài nguyên tải từ cùng origin.
B. Nguồn fallback khi directive fetch riêng chưa khai báo.
C. Directive luôn ghi đè script-src và style-src.
D. Chỉ kiểm soát request điều hướng top-level.
Đáp án đúng: B

Trusted Types giúp giảm rủi ro XSS ở nhóm thao tác nào?
A. Mọi request mạng phát sinh từ script trong trang.
B. Mọi cookie được lưu bởi trình duyệt của người dùng.
C. Yêu cầu giá trị trusted tại DOM injection sink thay vì chuỗi tùy ý.
D. Mọi truy vấn SQL được tạo từ mã JavaScript client.
Đáp án đúng: C

Ứng dụng muốn ngăn website khác nhúng trang nhạy cảm vào iframe; CSP directive nào phù hợp?
A. default-src kiểm soát mọi frame cha theo mặc định.
B. frame-ancestors chỉ định origin được phép nhúng.
C. form-action giới hạn trang nào được phép tạo iframe.
D. frame-src chỉ định origin được phép nhúng trang hiện tại.
Đáp án đúng: B

X-Frame-Options thường được dùng để kiểm soát điều gì?
A. Ngăn trình duyệt gửi cookie trong request cross-site.
B. Giới hạn origin được phép đọc response qua CORS.
C. Ngăn hoặc giới hạn việc nhúng trang trong frame.
D. Chặn script inline và script từ bên thứ ba.
Đáp án đúng: C

Khi nhúng nội dung bên thứ ba bằng iframe, thuộc tính sandbox có ý nghĩa nào?
A. Hạn chế capability iframe trừ khi token cụ thể mở lại.
B. Mã hóa dữ liệu truyền giữa iframe và parent.
C. Chia sẻ cookie phiên của parent cho iframe.
D. Bỏ Same-Origin Policy để iframe trao đổi dữ liệu.
Đáp án đúng: A

COOP với giá trị same-origin chủ yếu tạo ra thay đổi nào?
A. Ngăn trang sử dụng cookie first-party của chính nó.
B. Tách cửa sổ khỏi context group khác origin.
C. Bắt buộc mọi response ảnh phải có CORS header.
D. Chặn mọi request tài nguyên cross-origin của trang.
Đáp án đúng: B

Để bật cross-origin isolation cho nhiều API trình duyệt, cấu hình nào thường cần phối hợp?
A. HSTS cùng Permissions-Policy geolocation=() tạo isolation.
B. CORS wildcard cùng X-Frame-Options DENY tạo isolation cho tab.
C. COOP same-origin cùng COEP require-corp hoặc credentialless.
D. CORP same-site cùng Referrer-Policy no-referrer tạo isolation.
Đáp án đúng: C

CORP response header chủ yếu kiểm soát điều gì?
A. Kiểm soát nhúng tài nguyên cross-origin trong no-cors.
B. Việc script cross-origin đọc response qua CORS.
C. Việc trang hiện tại được nhúng vào iframe bên ngoài.
D. Việc trình duyệt gửi cookie trong request cross-site.
Đáp án đúng: A

X-Content-Type-Options: nosniff giúp ngăn hành vi nào?
A. Ngăn MIME sniffing khác Content-Type khai báo.
B. Trang khác origin đọc response không có CORS header.
C. Script inline chạy khi CSP không khai báo nonce.
D. Trình duyệt tự gửi referrer đầy đủ đến mọi origin.
Đáp án đúng: A

Referrer-Policy kiểm soát thông tin nào khi điều hướng hoặc tải tài nguyên?
A. Loại script nào được phép chạy trong document.
B. Cookie nào được đính kèm trong request cross-site.
C. Origin nào được phép đọc response của tài nguyên.
D. Mức thông tin URL nguồn được gửi trong Referer.
Đáp án đúng: D

Khi dùng window.postMessage giữa hai cửa sổ khác origin, cách kiểm tra nào cần thiết?
A. Xác minh event.origin, event.source và cấu trúc dữ liệu.
B. Chỉ kiểm tra event.data có phải chuỗi JSON hợp lệ.
C. Chấp nhận mọi origin nếu message có nonce bất kỳ.
D. Dùng targetOrigin="*" để trình duyệt tự xác thực người gửi.
Đáp án đúng: A

Header Strict-Transport-Security (HSTS) chủ yếu giúp bảo vệ điều gì?
A. Yêu cầu trình duyệt dùng HTTPS cho các lần truy cập tiếp theo.
B. Giới hạn website được phép nhúng trang hiện tại trong frame.
C. Buộc trình duyệt gửi cookie chỉ trong request cùng site.
D. Cho phép script đọc response từ các origin được liệt kê.
Đáp án đúng: A

Vì sao không nên lưu session token nhạy cảm trong localStorage?
A. localStorage được mã hóa tự động bằng khóa riêng của tab.
B. Trình duyệt tự gửi localStorage trong mọi request cross-site.
C. Script cùng origin, kể cả script do XSS thực thi, có thể đọc giá trị.
D. localStorage chỉ hoạt động khi server bật CORS cho origin.
Đáp án đúng: C
