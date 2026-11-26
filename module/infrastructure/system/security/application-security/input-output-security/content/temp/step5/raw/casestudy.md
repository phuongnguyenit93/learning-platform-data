Một API nhận tuổi người dùng dưới dạng chuỗi và chỉ kiểm tra giá trị có thể parse thành số; giá trị âm hoặc lớn hơn giới hạn nghiệp vụ vẫn được lưu, gây lỗi ở bước tính quyền lợi.
Một endpoint kiểm tra độ dài tên theo số byte UTF-8 trong khi giao diện giới hạn số ký tự Unicode; tên tiếng Việt có dấu bị từ chối không nhất quán giữa client và server.
Ứng dụng chỉ kiểm tra dữ liệu ở JavaScript phía trình duyệt; attacker gọi API trực tiếp và gửi giá trị không qua form validation, khiến dữ liệu sai lọt vào database.
Một trường quantity được kiểm tra là số nguyên nhưng không giới hạn giá trị tối đa; request rất lớn gây tràn số khi nhân với đơn giá và làm sai tổng tiền.
API nhận enum status nhưng dùng kiểm tra chuỗi không phân biệt hoa thường ở một tầng và so sánh phân biệt hoa thường ở tầng khác; giá trị lạ vượt qua validation rồi làm sai luồng phân quyền.
Backend xác thực số lượng item trong JSON nhưng không giới hạn kích thước body hoặc độ sâu object; payload rất lớn làm tăng CPU và bộ nhớ trước khi business validation chạy.
Một API nhận cùng một giá trị qua query parameter và JSON body; hai đường xử lý áp dụng rule validation khác nhau nên attacker chọn đường ít kiểm soát hơn.
Ứng dụng kiểm tra URL đầu vào trước khi percent-decode; sau decode, ký tự phân cách và đường dẫn thay đổi khiến giá trị thực khác với chuỗi đã được kiểm tra.
Reverse proxy giải mã URL một lần còn ứng dụng giải mã thêm lần nữa; chuỗi traversal được mã hóa lồng nhau vượt qua kiểm tra ở proxy rồi trở thành đường dẫn ngoài thư mục cho phép.
Hệ thống chuẩn hóa Unicode sau khi kiểm tra danh sách ký tự; ký tự tương đương được biến đổi thành dấu phân cách hoặc ký tự có ý nghĩa đặc biệt sau validation.
Ứng dụng so sánh tên tài khoản theo Unicode NFC nhưng lưu theo dạng khác; hai chuỗi nhìn giống nhau tạo hai tài khoản riêng và làm sai kiểm soát trùng lặp.
Một bộ lọc loại dấu chấm trong filename trước khi giải mã phần trăm; sau decode, tên tệp lại chứa chuỗi đường dẫn và vượt khỏi thư mục upload.
Nhóm dùng HTML sanitizer để làm sạch nội dung nhưng sanitizer chạy trước khi chuyển đổi entity; bước decode sau đó khôi phục markup đã bị che trong dữ liệu đầu vào.
Ứng dụng loại thẻ script bằng regex nhưng vẫn cho phép thuộc tính sự kiện trên thẻ HTML khác; nội dung rich text được lưu và thực thi JavaScript khi hiển thị.
Trang bình luận cho phép HTML giới hạn nhưng sanitizer dùng allowlist thẻ mà không giới hạn URL trong href; liên kết dùng scheme nguy hiểm vẫn được render.
Một hệ thống nhận rich text và dùng sanitizer phía client; API lưu trực tiếp HTML gốc nên người dùng khác xem lại nội dung bị stored XSS.
Template server-side tự động escape HTML nhưng developer dùng hàm render raw/safe cho trường mô tả do người dùng nhập; stored XSS xuất hiện ở trang quản trị.
Ứng dụng chèn tên người dùng vào text node HTML bằng string concatenation; ký tự markup trong tên được trình duyệt diễn giải thành phần tử thay vì hiển thị nguyên văn.
Một trang đặt giá trị tìm kiếm vào thuộc tính HTML title; nhóm chỉ encode HTML text context và không xử lý dấu nháy, khiến thuộc tính bị đóng ngoài ý muốn.
Ứng dụng tạo inline JavaScript bằng cách nối trực tiếp tên hiển thị vào string literal; ký tự quote hoặc dấu xuống dòng làm thay đổi cú pháp script và gây XSS.
Backend serialize object thành JSON nhưng frontend nhúng JSON đó trực tiếp vào thẻ script HTML; chuỗi kết thúc thẻ script có thể phá vỡ ngữ cảnh HTML dù JSON hợp lệ.
Một API trả JSON bằng cách tự nối chuỗi thay vì dùng serializer; tên người dùng có dấu nháy hoặc newline làm response sai cú pháp và có thể thay đổi cấu trúc dữ liệu.
Frontend đưa dữ liệu không tin cậy vào innerHTML để cập nhật thông báo; cùng dữ liệu đó nếu gán qua textContent sẽ chỉ hiển thị văn bản nhưng hiện tại lại được parse thành HTML.
Ứng dụng encode URL component rồi đặt kết quả vào thuộc tính href nhưng quên kiểm tra scheme; javascript: vẫn là URL hợp lệ về mặt cú pháp và có thể thực thi khi người dùng bấm.
Một link redirect nhận returnUrl từ query string; server chỉ kiểm tra URL bắt đầu bằng dấu slash nhưng không xử lý trường hợp slash/backslash và host parsing khác nhau giữa proxy với framework.
Ứng dụng đưa giá trị người dùng vào query string bằng cách encode toàn URL thay vì từng component; dấu phân cách bị encode sai và tham số bảo mật bị ghép vào giá trị khác.
Trang hiển thị Markdown do người dùng gửi và chuyển sang HTML bằng renderer hỗ trợ raw HTML; không có sanitizer sau bước render nên nội dung có thể chứa markup thực thi.
Ứng dụng tạo nội dung CSS động từ màu người dùng chọn; giá trị chỉ được kiểm tra là chuỗi nhưng không giới hạn theo grammar màu, khiến CSS injection ảnh hưởng giao diện.
Một truy vấn SQL dùng PreparedStatement cho giá trị nhưng ghép tên cột sort do client gửi vào câu lệnh; parameter binding không áp dụng cho identifier nên cần allowlist tên cột và hướng sắp xếp.
Ứng dụng dùng parameterized query cho điều kiện WHERE nhưng vẫn ghép đoạn ORDER BY và tên bảng từ request; SQL injection còn tồn tại ở phần cú pháp không thể bind như value.
Backend escape dấu nháy theo quy tắc của một database rồi chuyển ứng dụng sang database khác; cách escape khác nhau khiến truy vấn động không còn an toàn.
Một bộ lọc tìm kiếm cho phép ký tự wildcard SQL; người dùng nhập pattern rộng làm truy vấn quét toàn bảng và tạo tải cao dù không thực hiện injection.
Ứng dụng gọi shell command bằng cách ghép filename vào chuỗi lệnh; tên file chứa shell metacharacter làm phát sinh command injection ngoài thao tác dự kiến.
Java ProcessBuilder nhận executable và từng argument riêng nhưng ứng dụng không kiểm tra filename bắt đầu bằng dấu gạch ngang; chương trình đích hiểu tên file là option và thực hiện hành vi ngoài ý muốn.
Script gọi tiện ích hệ điều hành với đối số do API cung cấp; dù không qua shell, giá trị có thể kích hoạt option injection nếu chương trình đích diễn giải chuỗi bắt đầu bằng dấu gạch ngang.
Ứng dụng escape chuỗi cho shell bằng quy tắc POSIX rồi chạy trên Windows PowerShell; quoting khác nhau giữa shell khiến đối số vẫn có thể bị phân tách hoặc diễn giải sai.
Một bộ lọc LDAP ghép username vào filter expression nhưng dùng escaping dành cho distinguished name; ký tự đặc biệt của filter vẫn làm thay đổi điều kiện tìm kiếm.
Ứng dụng xây LDAP distinguished name từ tên người dùng bằng cách escape theo cú pháp filter; dấu phẩy và dấu cộng trong DN không được bảo vệ đúng ngữ cảnh.
XML parser xử lý file do người dùng upload vẫn bật external entity resolution; tài liệu XML có thể khiến server đọc tài nguyên nội bộ hoặc gửi request ngoài dự kiến.
Ứng dụng deserialize object từ dữ liệu không tin cậy bằng cơ chế cho phép class tùy ý; validation sau deserialize diễn ra quá muộn vì gadget chain có thể chạy trong quá trình tạo object.
API nhận file upload và chỉ tin Content-Type do trình duyệt gửi; người dùng đổi header thành image/png dù nội dung thực tế là file thực thi.
Upload validator chỉ kiểm tra phần mở rộng .jpg; file có nội dung khác định dạng vẫn được lưu và được web server phục vụ như nội dung chủ động.
Ứng dụng lưu file upload dưới tên gốc do người dùng cung cấp; tên có path separator hoặc ký tự điều khiển làm file được ghi ngoài thư mục dự kiến.
File upload được lưu trong web root và server cấu hình thực thi một số loại script; file nguy hiểm có thể được gọi trực tiếp qua URL sau khi tải lên.
Ứng dụng kiểm tra đường dẫn sau khi resolve symlink nhưng thư mục đích có thể bị thay symlink giữa lúc kiểm tra và lúc mở file; race condition làm thao tác ghi đi ra ngoài vùng cho phép.
Archive upload được giải nén mà không kiểm tra đường dẫn entry; tên entry chứa traversal ghi đè file bên ngoài thư mục giải nén.
Server nhận archive nhỏ nhưng bên trong chứa hàng triệu file hoặc dữ liệu nén phình rất lớn; giải nén không giới hạn gây cạn disk, inode hoặc CPU.
Ứng dụng tạo thumbnail SVG từ file người dùng gửi và hiển thị trực tiếp trên cùng origin; SVG có thể chứa nội dung chủ động mà chính sách ảnh raster không xử lý.
File được xác thực bằng magic bytes nhưng không kiểm tra cấu trúc sâu hoặc giới hạn kích thước; file lỗi định dạng kích hoạt bug trong thư viện xử lý ảnh.
API trả object nội bộ nguyên trạng và vô tình serialize trường passwordHash, resetToken hoặc internalNotes; người dùng nhận được dữ liệu không thuộc contract công khai.
Ứng dụng chỉ kiểm tra quyền truy cập endpoint nhưng không lọc thuộc tính theo người dùng; response chứa email, số điện thoại hoặc dữ liệu của bản ghi liên quan mà caller không được xem.
Thông báo lỗi API trả stack trace và SQL exception chi tiết khi request sai; response tiết lộ schema, đường dẫn máy chủ và thông tin kết nối nội bộ.
Ứng dụng ghi toàn bộ request headers vào access log; Authorization, cookie phiên và API key bị lưu ở hệ thống log có quyền truy cập rộng hơn.
Người dùng nhập newline vào trường username và giá trị được ghi nguyên vào log dạng text; log forging tạo dòng giả giống cảnh báo xác thực thành công.
Ứng dụng mask email trong application log nhưng reverse proxy vẫn ghi query string chứa token reset password; dữ liệu bí mật tiếp tục tồn tại ở một tầng khác.
Backend trả dữ liệu nhạy cảm trong JSON nhưng đặt Cache-Control công khai; proxy hoặc shared cache có thể lưu response và phục vụ lại cho người dùng khác.
API trả lỗi validation bằng cách echo nguyên giá trị input; trường đầu vào chứa secret hoặc dữ liệu cá nhân bị phản chiếu vào response và log giám sát.
Ứng dụng nhận dữ liệu từ webhook rồi đưa thẳng vào template email HTML; nội dung độc hại được gửi tới nhân viên và có thể thực thi khi mở email client hỗ trợ HTML.
Frontend nhận JSON từ API và dùng tên trường do server trả về để truy cập thuộc tính động; dữ liệu không được kiểm tra schema dẫn đến prototype pollution trong một số thư viện xử lý object.
Ứng dụng dùng JSON.parse an toàn nhưng sau đó merge object do người dùng kiểm soát vào cấu hình mặc định bằng deep merge không chặn thuộc tính đặc biệt; cấu hình kế thừa bị thay đổi.
API nhận Content-Type không đúng với body thực tế; middleware parse theo fallback khác nhau giữa gateway và ứng dụng, khiến lớp kiểm tra và lớp xử lý nhìn thấy hai cấu trúc dữ liệu.
Ứng dụng chấp nhận nhiều dạng biểu diễn cùng một địa chỉ IP hoặc URL; allowlist kiểm tra dạng chữ ban đầu nhưng thư viện network parse sang địa chỉ khác sau canonicalization.
Webhook validator kiểm tra chữ ký trên body đã parse và serialize lại; khác biệt khoảng trắng hoặc thứ tự field làm kiểm tra chữ ký không nhất quán với bytes thực tế đã nhận.
Ứng dụng loại bỏ HTML tags trước khi lưu nhưng vẫn giữ nội dung attribute và entity; downstream renderer khác diễn giải dữ liệu theo cách khác và tái tạo markup không an toàn.
Đội phát triển dùng cùng một hàm escape cho HTML, JavaScript, URL và JSON; mỗi ngữ cảnh có grammar khác nhau nên dữ liệu vẫn có thể phá vỡ cú pháp ở một số đầu ra.
