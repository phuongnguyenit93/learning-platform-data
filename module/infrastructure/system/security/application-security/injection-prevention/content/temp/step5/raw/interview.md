Bạn sẽ giải thích lỗ hổng injection hình thành như thế nào khi dữ liệu không tin cậy bị diễn giải thành lệnh hoặc cú pháp thực thi?
Bạn sẽ xây dựng threat model cho injection bằng cách xác định nguồn dữ liệu, điểm nối chuỗi, bộ phân tích và tác động như thế nào?
Bạn sẽ phân biệt dữ liệu và cú pháp trong một truy vấn hoặc lệnh để xác định ranh giới cần bảo vệ ra sao?
Bạn sẽ giải thích vì sao blacklist ký tự nguy hiểm thường không đủ để ngăn injection trong nhiều ngữ cảnh như thế nào?
Bạn sẽ lựa chọn biện pháp phòng vệ dựa trên ngữ cảnh diễn giải thay vì dùng một bộ lọc đầu vào chung cho mọi loại injection ra sao?
Bạn sẽ phân biệt validation đầu vào, parameterization và output encoding về mục đích cùng giới hạn bảo vệ ra sao?
Bạn sẽ thiết kế nguyên tắc an toàn để dữ liệu người dùng không thể thay đổi cấu trúc của câu lệnh hoặc biểu thức như thế nào?
Bạn sẽ giải thích SQL injection phát sinh khi dữ liệu đầu vào làm thay đổi cấu trúc câu SQL như thế nào?
Bạn sẽ sử dụng prepared statement và parameterized query để tách SQL syntax khỏi giá trị đầu vào ra sao?
Bạn sẽ phân biệt parameter binding cho giá trị với việc tham số hóa tên bảng, tên cột hoặc từ khóa SQL như thế nào?
Bạn sẽ xử lý dynamic sorting hoặc filtering bằng allowlist identifier và mapping cố định ra sao?
Bạn sẽ phân tích vì sao nối chuỗi đầu vào vào mệnh đề WHERE hoặc ORDER BY vẫn nguy hiểm dù đã kiểm tra kiểu dữ liệu như thế nào?
Bạn sẽ ngăn SQL injection trong ORM khi ứng dụng sử dụng native query, raw SQL hoặc API truy vấn động ra sao?
Bạn sẽ kiểm tra các điểm rủi ro khi ORM hỗ trợ query builder nhưng tên trường hoặc biểu thức vẫn được ghép từ input như thế nào?
Bạn sẽ thiết kế quyền database tối thiểu để giảm tác động nếu một lỗ hổng SQL injection vẫn bị khai thác ra sao?
Bạn sẽ phân biệt error-based, union-based, boolean-based và time-based SQL injection theo dấu hiệu quan sát như thế nào?
Bạn sẽ xác định dấu hiệu blind SQL injection khi API không trả nội dung truy vấn nhưng hành vi phản hồi thay đổi ra sao?
Bạn sẽ đánh giá nguy cơ second-order SQL injection khi dữ liệu độc hại được lưu trước rồi sử dụng trong truy vấn khác như thế nào?
Bạn sẽ xử lý stored procedure có dynamic SQL để tránh nối chuỗi dữ liệu không tin cậy vào câu lệnh ra sao?
Bạn sẽ phân biệt escaping theo dialect SQL với parameterization và xác định khi nào escaping không đủ an toàn như thế nào?
Bạn sẽ kiểm thử SQL injection trên các nhánh tìm kiếm, phân trang, lọc, báo cáo và export bằng cách nào?
Bạn sẽ giải thích NoSQL injection trong MongoDB hoặc document database khác với SQL injection về cấu trúc truy vấn ra sao?
Bạn sẽ ngăn input biến thành toán tử truy vấn như $ne, $where hoặc biểu thức điều kiện ngoài ý muốn như thế nào?
Bạn sẽ thiết kế schema validation và allowlist toán tử cho bộ lọc NoSQL do client gửi lên ra sao?
Bạn sẽ tránh chuyển trực tiếp JSON request thành query object khi client có thể điều khiển tên trường và toán tử như thế nào?
Bạn sẽ kiểm soát việc sử dụng JavaScript expression hoặc server-side scripting trong truy vấn NoSQL để giảm nguy cơ thực thi mã ra sao?
Bạn sẽ kiểm thử NoSQL injection bằng các payload thay đổi kiểu dữ liệu, cấu trúc object và toán tử truy vấn như thế nào?
Bạn sẽ giải thích OS command injection xảy ra khi dữ liệu người dùng ảnh hưởng đến command line được thực thi như thế nào?
Bạn sẽ ưu tiên API gọi process trực tiếp với danh sách argument tách biệt thay cho shell command ghép chuỗi ra sao?
Bạn sẽ phân biệt truyền tham số an toàn với việc shell vẫn diễn giải metacharacter khi ứng dụng gọi qua sh -c hoặc bash -c như thế nào?
Bạn sẽ thiết kế allowlist executable và argument hợp lệ cho chức năng chạy công cụ hệ thống theo cách nào?
Bạn sẽ kiểm soát đường dẫn executable, working directory và environment để tránh gọi nhầm chương trình do PATH bị thao túng như thế nào?
Bạn sẽ ngăn option injection khi một đối số bắt đầu bằng dấu gạch ngang bị chương trình đích hiểu thành tùy chọn nguy hiểm ra sao?
Bạn sẽ xử lý tên file có khoảng trắng, dấu nháy, ký tự Unicode và ký tự đặc biệt khi truyền cho process như thế nào?
Bạn sẽ giảm tác động của command injection bằng tài khoản không đặc quyền, sandbox và giới hạn hệ thống ra sao?
Bạn sẽ kiểm thử command injection trên các chức năng chuyển đổi file, tạo báo cáo, backup hoặc gọi tiện ích hệ điều hành như thế nào?
Bạn sẽ giải thích LDAP injection khi dữ liệu đầu vào thay đổi cấu trúc filter hoặc distinguished name như thế nào?
Bạn sẽ phân biệt escaping giá trị LDAP filter theo RFC 4515 với escaping thành phần DN theo RFC 4514 ra sao?
Bạn sẽ sử dụng LDAP API có parameter hoặc filter builder để tránh ghép chuỗi filter trực tiếp như thế nào?
Bạn sẽ xác định rủi ro khi input người dùng được đưa vào các toán tử AND, OR hoặc wildcard trong LDAP filter ra sao?
Bạn sẽ thiết kế allowlist thuộc tính tìm kiếm và giới hạn phạm vi LDAP query để giảm nguy cơ truy xuất dữ liệu ngoài ý muốn như thế nào?
Bạn sẽ kiểm thử LDAP injection trong chức năng đăng nhập, tìm kiếm người dùng và tra cứu nhóm bằng cách nào?
Bạn sẽ giải thích XPath injection khi dữ liệu không tin cậy làm thay đổi biểu thức truy vấn XML như thế nào?
Bạn sẽ sử dụng XPath variable binding hoặc API phù hợp để tách giá trị đầu vào khỏi biểu thức XPath ra sao?
Bạn sẽ xử lý trường hợp thư viện XPath không hỗ trợ bind variable trực tiếp mà vẫn cần xây dựng biểu thức an toàn như thế nào?
Bạn sẽ đánh giá rủi ro XPath injection trong kiểm tra thông tin đăng nhập hoặc truy xuất node XML theo quyền ra sao?
Bạn sẽ phân biệt XPath injection với XML External Entity và xác định biện pháp phòng vệ riêng cho parser XML như thế nào?
Bạn sẽ kiểm thử XPath injection bằng cách thay đổi logic điều kiện và phạm vi node được truy xuất ra sao?
Bạn sẽ giải thích server-side template injection xảy ra khi dữ liệu không tin cậy được biên dịch như một phần của template như thế nào?
Bạn sẽ phân biệt truyền dữ liệu vào template đã cố định với việc cho người dùng cung cấp nội dung template có thể thực thi ra sao?
Bạn sẽ thiết kế template rendering an toàn bằng autoescaping, dữ liệu có cấu trúc và giới hạn khả năng thực thi như thế nào?
Bạn sẽ đánh giá rủi ro khi template engine cho phép gọi method, truy cập object hoặc thực thi biểu thức tùy ý ra sao?
Bạn sẽ lựa chọn sandbox hoặc engine giới hạn tính năng khi cần hỗ trợ template do người dùng định nghĩa như thế nào?
Bạn sẽ kiểm tra SSTI trong email template, trang tùy chỉnh, báo cáo và hệ thống CMS bằng cách nào?
Bạn sẽ giải thích XSS là trường hợp dữ liệu không tin cậy được trình duyệt diễn giải thành nội dung hoặc mã thực thi như thế nào?
Bạn sẽ phân biệt reflected XSS, stored XSS và DOM-based XSS theo nguồn dữ liệu và thời điểm thực thi ra sao?
Bạn sẽ chọn output encoding theo đúng ngữ cảnh HTML text, HTML attribute, JavaScript, CSS và URL như thế nào?
Bạn sẽ giải thích vì sao HTML escaping không tự động bảo vệ dữ liệu khi chèn vào JavaScript string hoặc URL context ra sao?
Bạn sẽ ưu tiên safe DOM APIs như textContent và tránh các sink nguy hiểm như innerHTML khi hiển thị dữ liệu người dùng như thế nào?
Bạn sẽ đánh giá khi nào cần HTML sanitization cho nội dung rich text và cách dùng allowlist tag, attribute và URL scheme ra sao?
Bạn sẽ phân biệt output encoding với sanitization và xác định vai trò riêng của từng biện pháp trong phòng chống XSS như thế nào?
Bạn sẽ kiểm tra DOM-based XSS khi dữ liệu từ location, hash hoặc postMessage được đưa vào sink trình duyệt như thế nào?
Bạn sẽ thiết kế Content Security Policy để giảm tác động XSS và đánh giá những giới hạn của CSP ra sao?
Bạn sẽ lựa chọn cookie HttpOnly, Secure và SameSite để giảm khả năng đánh cắp session khi XSS xảy ra như thế nào?
Bạn sẽ kiểm thử XSS trên template server-side, frontend framework, rich-text editor và các điểm render DOM bằng cách nào?
Bạn sẽ giải thích prompt injection khác với SQL hoặc command injection truyền thống về cách mô hình xử lý chỉ dẫn và dữ liệu như thế nào?
Bạn sẽ phân biệt direct prompt injection từ người dùng với indirect prompt injection được nhúng trong tài liệu hoặc nội dung truy xuất ra sao?
Bạn sẽ xác định ranh giới tin cậy giữa system instruction, developer instruction, user input và dữ liệu bên ngoài trong một ứng dụng AI như thế nào?
Bạn sẽ thiết kế quy trình xử lý tài liệu truy xuất để nội dung không tin cậy không thể tự nâng quyền thành chỉ dẫn điều khiển mô hình ra sao?
Bạn sẽ giới hạn quyền tool và API mà agent AI có thể gọi để giảm tác động khi prompt injection thành công như thế nào?
Bạn sẽ yêu cầu xác nhận hoặc kiểm tra chính sách ở phía server trước hành động có tác động như gửi tiền, xóa dữ liệu hoặc gửi thông điệp ra sao?
Bạn sẽ kiểm soát dữ liệu nhạy cảm trong context window và ngăn prompt injection dụ mô hình tiết lộ secrets như thế nào?
Bạn sẽ phân biệt instruction hierarchy với việc chỉ yêu cầu mô hình bỏ qua chỉ dẫn độc hại và giải thích vì sao không thể dựa vào prompt đơn thuần như thế nào?
Bạn sẽ kiểm thử indirect prompt injection trong email, trang web, file đính kèm và kết quả tìm kiếm bằng kịch bản nào?
Bạn sẽ giám sát hành vi gọi tool, truy cập dữ liệu và output bất thường để phát hiện dấu hiệu prompt injection ra sao?
Bạn sẽ xây dựng defense in depth cho ứng dụng AI gồm phân tách dữ liệu, giới hạn tool, kiểm tra output và quyền tối thiểu như thế nào?
Bạn sẽ sử dụng fuzzing hoặc property-based testing để tìm lỗi khi dữ liệu đi qua nhiều bước encode, decode và parse ra sao?
Bạn sẽ xác định cách kiểm thử các dạng encoding kép, Unicode normalization và canonicalization để tìm bypass bộ lọc như thế nào?
Bạn sẽ phân biệt kiểm thử dựa trên phản hồi trực tiếp với kiểm thử blind qua timing hoặc side effect trong từng loại injection ra sao?
Bạn sẽ tích hợp SAST, DAST, dependency scanning và kiểm thử thủ công vào pipeline phát triển để phát hiện injection như thế nào?
Bạn sẽ thiết kế code review checklist để tìm nối chuỗi SQL, gọi shell, LDAP/XPath expression, template compilation và DOM sink nguy hiểm ra sao?
Bạn sẽ đánh giá false positive và false negative của quy tắc phát hiện injection trong SAST hoặc WAF bằng cách nào?
Bạn sẽ xác định metric và log nào giúp phát hiện hoạt động dò payload injection mà không ghi lại dữ liệu nhạy cảm ra sao?
Bạn sẽ thiết kế cảnh báo khi xuất hiện nhiều lỗi truy vấn, phản hồi bất thường hoặc payload có dấu hiệu injection theo cùng nguồn như thế nào?
Nếu một endpoint tìm kiếm dùng parameterized SQL nhưng tên cột được ghép từ input, bạn sẽ xác định và sửa điểm injection còn lại ra sao?
Nếu API gọi một tiện ích hệ điều hành bằng shell wrapper và tên file chứa ký tự đặc biệt, bạn sẽ chuyển sang cách thực thi an toàn như thế nào?
Nếu LDAP filter đăng nhập trả về nhiều tài khoản khi nhận một input đặc biệt, bạn sẽ kiểm tra escaping và cấu trúc filter ra sao?
Nếu một trang chỉ bị XSS khi nội dung được render trong thuộc tính HTML hoặc JavaScript, bạn sẽ xác định đúng context và biện pháp encoding như thế nào?
Nếu một agent AI đọc tài liệu bên ngoài rồi cố gọi tool để trích xuất dữ liệu nội bộ, bạn sẽ giới hạn quyền và kiểm tra hành động ở đâu?
Bạn sẽ thiết kế chiến lược phòng chống injection xuyên suốt một ứng dụng web gồm database, hệ điều hành, directory service, template, browser và AI như thế nào?
