Bạn phân biệt input validation, canonicalization, sanitization và output encoding theo mục tiêu bảo mật như thế nào?
Bạn xác định ranh giới tin cậy của dữ liệu khi đi từ trình duyệt, API client, message queue và file vào ứng dụng ra sao?
Bạn thiết kế quy tắc validation theo allowlist dựa trên kiểu dữ liệu, định dạng, độ dài và miền giá trị như thế nào?
Bạn lựa chọn allowlist hay denylist khi chấp nhận dữ liệu đầu vào và đánh giá giới hạn của từng cách ra sao?
Bạn phân biệt kiểm tra cú pháp với kiểm tra ngữ nghĩa nghiệp vụ đối với một input như thế nào?
Bạn xác định thứ tự canonicalization và validation để tránh dữ liệu vượt qua kiểm tra bằng biểu diễn khác nhau ra sao?
Bạn xử lý Unicode normalization, ký tự tương đương và ký tự điều khiển trong input như thế nào?
Bạn kiểm tra nguy cơ bypass validation bằng double encoding hoặc nhiều lớp percent encoding ra sao?
Bạn xử lý tham số HTTP trùng tên hoặc xuất hiện đồng thời trong query string và request body như thế nào?
Bạn xác định content type và schema cần chấp nhận cho từng API endpoint ra sao?
Bạn thiết kế giới hạn kích thước, độ sâu và số phần tử của JSON input để ngăn payload gây cạn tài nguyên như thế nào?
Bạn phân biệt dữ liệu thiếu, null, rỗng và giá trị mặc định để tránh logic validation không nhất quán ra sao?
Bạn lựa chọn cách từ chối input sai định dạng mà vẫn cung cấp lỗi đủ hữu ích nhưng không tiết lộ chi tiết nội bộ như thế nào?
Bạn tổ chức validation dùng chung giữa REST API, tác vụ nền và message consumer để tránh mỗi luồng xử lý một quy tắc khác nhau ra sao?
Bạn đánh giá vì sao validation ở giao diện người dùng không thể thay thế kiểm tra tại backend như thế nào?
Bạn phân biệt sanitization với validation và xác định khi nào việc loại bỏ ký tự có thể làm thay đổi ý nghĩa dữ liệu như thế nào?
Bạn quyết định giữ nguyên dữ liệu gốc, lưu dữ liệu đã chuẩn hóa hay lưu cả hai theo mục đích nào?
Bạn ngăn dữ liệu đã được canonicalize hoặc sanitize ở một tầng bị xử lý lại gây sai lệch ở tầng tiếp theo như thế nào?
Bạn thiết kế quy trình xử lý input nhiều định dạng để mỗi bước parser chỉ nhận đúng loại dữ liệu đã khai báo như thế nào?
Bạn kiểm tra parser JSON, XML hoặc multipart có giới hạn tài nguyên và xử lý lỗi an toàn ra sao?
Bạn phòng chống XML External Entity và truy cập tài nguyên ngoài ý muốn bằng cấu hình parser nào?
Bạn đánh giá rủi ro deserialization dữ liệu không tin cậy và lựa chọn định dạng trao đổi an toàn như thế nào?
Bạn phân biệt serialize dữ liệu để truyền tải với deserialize object có thể kích hoạt hành vi trong runtime ra sao?
Bạn xác định các loại input có thể gây regex denial of service và kiểm soát thời gian thực thi pattern như thế nào?
Bạn thiết kế validation cho số, ngày giờ, timezone và đơn vị đo để tránh lỗi chuyển đổi hoặc tràn giá trị ra sao?
Bạn phân biệt kiểm tra đường dẫn theo chuỗi với kiểm tra đường dẫn sau khi resolve canonical path như thế nào?
Bạn ngăn path traversal qua dấu chấm, dấu phân cách mã hóa hoặc đường dẫn tuyệt đối trên các hệ điều hành khác nhau ra sao?
Bạn xử lý symbolic link và TOCTOU khi ứng dụng kiểm tra đường dẫn rồi mới mở file như thế nào?
Bạn thiết kế kiểm soát quyền truy cập thư mục để một input file name không thể ghi ra ngoài vùng lưu trữ được phép ra sao?
Bạn giải thích output encoding khác gì với input validation và vì sao dữ liệu hợp lệ vẫn cần encode theo ngữ cảnh hiển thị như thế nào?
Bạn lựa chọn HTML text encoding và HTML attribute encoding theo vị trí dữ liệu được chèn vào document ra sao?
Bạn xử lý dữ liệu không tin cậy trong thuộc tính HTML có chứa URL hoặc giá trị cần kiểm tra scheme như thế nào?
Bạn phân biệt HTML encoding với JavaScript string encoding khi đưa dữ liệu vào inline script ra sao?
Bạn thiết kế cách truyền dữ liệu server-rendered vào JavaScript bằng JSON serialization an toàn thay vì nối chuỗi như thế nào?
Bạn xác định vì sao JSON.stringify hoặc serializer đúng chuẩn không tự động bảo vệ mọi vị trí nhúng JSON vào HTML như thế nào?
Bạn lựa chọn URL component encoding cho query parameter và path segment để tránh phá cấu trúc URL ra sao?
Bạn phân biệt URL encoding với HTML attribute encoding khi đặt một URL vào thuộc tính href như thế nào?
Bạn kiểm tra scheme và đích đến của URL do người dùng cung cấp để ngăn javascript hoặc data URL ở vị trí không được phép như thế nào?
Bạn giải thích JSON output cần dùng serializer chuẩn và Content-Type phù hợp để tránh tạo dữ liệu sai cấu trúc ra sao?
Bạn phân biệt JSON escaping với encoding cho HTML, JavaScript và URL khi cùng một giá trị được dùng ở nhiều ngữ cảnh như thế nào?
Bạn xử lý dữ liệu người dùng được hiển thị trong HTML email hoặc template server-side để tránh stored XSS như thế nào?
Bạn đánh giá tác dụng và giới hạn của auto-escaping trong template engine khi có raw HTML hoặc safe-markup escape hatch ra sao?
Bạn xác định DOM sink nguy hiểm như innerHTML và lựa chọn API DOM an toàn hơn để cập nhật nội dung như thế nào?
Bạn phân biệt reflected, stored và DOM-based XSS qua nguồn dữ liệu và vị trí thực thi payload ra sao?
Bạn thiết kế quy trình kiểm tra context trước khi render dữ liệu vào HTML, attribute, script, style hoặc URL như thế nào?
Bạn đánh giá Content Security Policy hỗ trợ giảm tác động XSS và những hạn chế khi ứng dụng vẫn có unsafe-inline ra sao?
Bạn xác định khi nào cần HTML sanitization cho nội dung rich text và lựa chọn allowlist tag, attribute, protocol như thế nào?
Bạn phân biệt HTML sanitizer với output encoder và giải thích vì sao chúng không thể thay thế lẫn nhau ra sao?
Bạn ngăn double encoding hoặc double decoding làm hiển thị sai dữ liệu và mở ra đường bypass XSS như thế nào?
Bạn thiết kế kiểm thử XSS theo từng context gồm HTML body, attribute, JavaScript string và URL như thế nào?
Bạn phòng chống SQL injection bằng parameterized query và xác định trường hợp tên bảng hoặc cột không thể bind như giá trị ra sao?
Bạn lựa chọn allowlist cho dynamic sort column hoặc order direction thay vì nối trực tiếp input vào SQL như thế nào?
Bạn đánh giá nguy cơ SQL injection còn tồn tại trong stored procedure, ORM native query hoặc query builder ra sao?
Bạn phân biệt escaping SQL thủ công với parameter binding và lý do không nên tự xây dựng cơ chế quoting như thế nào?
Bạn xác định cách xử lý dữ liệu tìm kiếm có ký tự wildcard để tránh thay đổi ngoài ý muốn ngữ nghĩa LIKE query ra sao?
Bạn phòng chống command injection khi ứng dụng gọi tiến trình hệ điều hành từ input người dùng như thế nào?
Bạn lựa chọn API thực thi process với danh sách đối số tách biệt thay vì ghép chuỗi shell ra sao?
Bạn kiểm soát executable, option và working directory để input không thể biến thành tham số lệnh nguy hiểm như thế nào?
Bạn xử lý tên file bắt đầu bằng dấu gạch ngang hoặc chứa ký tự đặc biệt khi truyền vào command-line tool như thế nào?
Bạn xác định khi nào cần shell invocation và cách giảm rủi ro khi không thể tránh dùng shell ra sao?
Bạn ngăn log injection khi input chứa newline, carriage return hoặc ký tự giả mạo mức độ log như thế nào?
Bạn thiết kế structured logging để dữ liệu người dùng không thể giả mạo ranh giới giữa các trường log ra sao?
Bạn xác định trường nào cần redact như password, access token, session ID và thông tin định danh trước khi ghi log như thế nào?
Bạn phân biệt correlation ID an toàn với dữ liệu người dùng không nên đưa trực tiếp vào log ra sao?
Bạn xử lý lỗi API để không trả stack trace, câu SQL, đường dẫn nội bộ hoặc secret trong response như thế nào?
Bạn thiết kế response DTO theo allowlist field để tránh lộ thuộc tính nội bộ hoặc dữ liệu của đối tượng liên quan ra sao?
Bạn phân biệt dữ liệu được phép lưu trong database với dữ liệu được phép xuất hiện trong API response như thế nào?
Bạn xác định cách mask hoặc truncate dữ liệu nhạy cảm khi hiển thị trong log, audit record và API response ra sao?
Bạn lựa chọn HTTP status và error code nhất quán mà không tiết lộ tài nguyên hoặc quy tắc bảo mật nội bộ như thế nào?
Bạn kiểm tra nguy cơ API trả quá nhiều trường do serialize trực tiếp entity hoặc object domain như thế nào?
Bạn thiết kế file upload validation theo extension, MIME type và file signature mà không tin riêng một trường do client khai báo ra sao?
Bạn kiểm soát tên file do người dùng cung cấp để tránh path traversal, ghi đè file và lộ cấu trúc thư mục như thế nào?
Bạn thiết kế lưu trữ upload ngoài web root và cấp quyền truy cập file qua một luồng kiểm soát riêng như thế nào?
Bạn xác định giới hạn kích thước file, số file, archive expansion ratio và thời gian xử lý để chống zip bomb ra sao?
Bạn xử lý archive extraction để ngăn Zip Slip và đường dẫn giải nén thoát khỏi thư mục đích như thế nào?
Bạn kiểm tra symbolic link, nested archive và file polyglot khi tiếp nhận tệp không tin cậy ra sao?
Bạn tổ chức quarantine, malware scanning và trạng thái file trước khi cho phép ứng dụng hoặc người dùng tải xuống như thế nào?
Bạn thiết kế download response với Content-Disposition và X-Content-Type-Options để giảm nguy cơ browser diễn giải sai nội dung như thế nào?
Bạn xác định khi nào nên dùng Content-Disposition attachment thay vì inline cho loại file do người dùng tải lên như thế nào?
Bạn xử lý SVG, HTML hoặc file văn bản do người dùng cung cấp để ngăn nội dung chủ động chạy trong origin của ứng dụng ra sao?
Bạn bảo đảm file upload không bị thực thi do cấu hình web server hoặc mapping MIME không an toàn như thế nào?
Bạn lựa chọn test cases cho input validation và output encoding dựa trên ranh giới ngữ cảnh và các kiểu biểu diễn khác nhau như thế nào?
Bạn thiết kế fuzzing hoặc property-based tests để phát hiện parser crash, bypass canonicalization và lỗi xử lý ký tự như thế nào?
Bạn xây dựng regression tests cho SQL injection, command injection, XSS, path traversal và log injection ra sao?
Bạn kiểm thử toàn bộ luồng input-to-output qua API, database, template và log để phát hiện lỗi encode sai tầng như thế nào?
Bạn xác định bằng chứng cần thu để chứng minh một biện pháp validation, encoding hoặc file handling đã chặn được payload nguy hiểm mà không làm hỏng dữ liệu hợp lệ như thế nào?
