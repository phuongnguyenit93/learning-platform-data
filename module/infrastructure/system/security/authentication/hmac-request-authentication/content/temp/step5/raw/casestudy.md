Đối tác ký request bằng HTTP method viết thường trong khi verifier chuyển method thành chữ hoa trước khi tính HMAC; hai bên cần thống nhất bước chuẩn hóa method trong canonical request.
Client và gateway biểu diễn cùng một URI bằng các dạng percent-encoding khác nhau; chữ ký chỉ khớp ở một số đường dẫn và nhóm cần xác định chuẩn encode/decode duy nhất.
Request có query `tag=a&tag=b` nhưng gateway gộp hai giá trị thành một tham số; hợp đồng ký cần quy định thứ tự và cách giữ các query parameter trùng tên.
Một client sắp xếp query parameter theo alphabet còn server giữ nguyên thứ tự nhận được; request hợp lệ bị từ chối dù ứng dụng coi hai URL là tương đương.
API coi `/orders` và `/orders/` là cùng một route nhưng canonical request ký hai path khác nhau; nhóm cần thống nhất trailing slash trước khi xác minh.
Chữ ký được tạo khi URL chứa default port nhưng reverse proxy loại bỏ port khỏi Host header; hệ thống cần xác định authority nào thuộc canonical request.
Client ký Host header bên ngoài nhưng proxy thay Host bằng tên service nội bộ trước khi chuyển tiếp; verifier cần nhận đúng giá trị đã ký theo hợp đồng.
Hệ thống ký scheme HTTPS nhưng load balancer chuyển tiếp request nội bộ bằng HTTP; nhóm cần quyết định scheme gốc được xác thực qua trusted proxy metadata như thế nào.
Header names được viết hoa/thường khác nhau giữa client và server; canonicalization cần quy định cách chuẩn hóa tên header mà không làm thay đổi ý nghĩa.
Một request chứa nhiều giá trị cho cùng header được client nối bằng dấu phẩy nhưng proxy giữ thành nhiều header field; hai phía cần thống nhất cách ghép và thứ tự giá trị.
Client ký một tập signed headers nhưng verifier chấp nhận header bổ sung không được ký; attacker có thể thay đổi thông tin định tuyến hoặc điều khiển ngoài phạm vi chữ ký.
Proxy loại bỏ khoảng trắng đầu cuối trong header trong khi client ký nguyên văn giá trị; nhóm cần xác định quy tắc trim và chuẩn hóa whitespace.
Ứng dụng ký raw JSON body nhưng gateway parse rồi serialize JSON với thứ tự property khác; hai phía cần chọn ký byte gốc hay một dạng JSON canonical được định nghĩa rõ.
Body chứa ký tự Unicode được mã hóa bằng UTF-8 ở client nhưng backend diễn giải charset khác; digest không khớp và cần thống nhất byte sequence được băm.
Request có body rỗng nhưng client bỏ trường body digest trong khi server tính hash của chuỗi rỗng; hợp đồng canonical request cần mô tả trường hợp này.
Upload dùng Transfer-Encoding chunked và proxy tái đóng gói body; nhóm cần xác định HMAC bảo vệ payload bytes sau khi ghép hay cả framing truyền tải.
Gateway giải nén request trước khi gửi upstream trong khi chữ ký được tạo trên compressed bytes; cần xác định lớp nào kiểm tra digest và lớp nào được phép biến đổi body.
Client ký Content-Length nhưng proxy thay đổi framing hoặc kích thước sau khi nén; đội tích hợp cần đánh giá có nên ký metadata vận chuyển hay chỉ ký payload digest.
Canonical request nối các trường bằng newline nhưng cách escape delimiter trong giá trị path hoặc header khác nhau giữa hai phía; định dạng cần ngăn nhập nhằng giữa các thành phần.
Một request có path hoặc header chứa ký tự phân cách đặc biệt làm hai chuỗi canonical khác nhau trở thành cùng biểu diễn; nhóm cần định nghĩa escaping không nhập nhằng.
Client gửi body lớn và verifier phải đọc toàn bộ body trước khi tính HMAC; tải tăng làm cạn bộ nhớ và cần thiết kế streaming digest cùng giới hạn kích thước.
Ứng dụng tính HMAC trên chuỗi secret đã decode UTF-8 nhưng hệ thống quản lý khóa cung cấp raw bytes; hai phía tạo chữ ký khác nhau do quy ước encoding chưa thống nhất.
Một nhóm phát hành request với HMAC-SHA-256 nhưng verifier còn cấu hình HMAC-SHA-1; hai phía cần thống nhất thuật toán được cho phép và từ chối thuật toán ngoài policy.
Verifier so sánh chữ ký bằng phép so sánh chuỗi thông thường và thời gian phản hồi thay đổi theo số byte khớp; nhóm bảo mật cần thay bằng so sánh constant-time.
Client gửi signature dạng Base64 còn server kỳ vọng hex; một số chữ ký bị từ chối và cần thống nhất alphabet, padding cùng quy tắc decode nghiêm ngặt.
Header chứa key identifier do client gửi và verifier dùng trực tiếp giá trị đó để chọn secret; nhóm cần giới hạn key lookup vào danh mục key đã cấp cho client.
Một key identifier cũ bị tái sử dụng cho secret mới trong lúc rotation; log xác minh khó phân biệt phiên bản khóa và cần quy ước định danh không tái sử dụng.
Một shared secret được dùng chung cho hàng chục đối tác; khi một đối tác bị lộ khóa, tổ chức không thể thu hồi riêng danh tính đó mà không ảnh hưởng các bên còn lại.
Secret HMAC được lưu trong file cấu hình và xuất hiện trong log khi startup thất bại; nhóm cần chuyển sang secret manager và loại bỏ giá trị nhạy cảm khỏi log.
Đội vận hành xoay secret ngay lập tức trên signer nhưng verifier chưa nhận khóa mới; request bị từ chối trong thời gian rollout và cần quy trình overlap hai khóa.
Verifier tiếp tục chấp nhận khóa cũ sau thời gian rotation đã kết thúc; nhóm cần xác định thời điểm ngừng tin khóa cũ và cách xử lý request đang trên đường truyền.
Một secret bị nghi lộ nhưng chỉ một gateway đã thu hồi key; các replica còn lại tiếp tục xác minh request bằng khóa cũ do cấu hình chưa đồng bộ.
Client ký timestamp hiện tại nhưng request bị trì hoãn qua hàng đợi lâu hơn cửa sổ clock skew; hệ thống cần cân bằng giữa độ trễ thực tế và thời gian chống replay.
Đồng hồ của các gateway lệch nhau vài phút sau sự cố NTP; cùng một request được node này chấp nhận và node khác từ chối do kiểm tra timestamp.
Attacker gửi lại nguyên request hợp lệ trong cửa sổ timestamp cho phép; timestamp đơn lẻ không đủ ngăn replay và cần thêm nonce hoặc trạng thái đã dùng.
Hai request cùng nonce đến hai replica gần như đồng thời; cả hai replica đều kiểm tra chưa tồn tại rồi chấp nhận nếu thao tác lưu nonce không nguyên tử.
Nonce store bị phân vùng mạng và một số gateway không truy cập được; nhóm cần quyết định từ chối an toàn hay chấp nhận rủi ro replay trong chế độ suy giảm.
Nonce được giữ lâu hơn cửa sổ timestamp gây tăng dung lượng cache; chính sách TTL cần khớp với acceptance window và sai lệch đồng hồ cho phép.
Client retry request sau timeout bằng cùng nonce và cùng chữ ký; hệ thống cần phân biệt retry hợp lệ với replay độc hại mà không thực hiện nghiệp vụ hai lần.
Một API thanh toán dùng nonce để chống replay nhưng không có idempotency record cho thao tác nghiệp vụ; retry tạo giao dịch trùng dù chữ ký hợp lệ.
Request được ký method, path và body digest nhưng bỏ qua query parameter chứa account identifier; attacker thay query để truy cập đối tượng khác bằng chữ ký cũ.
Gateway xác minh HMAC rồi truyền header `X-Authenticated-Client` lên backend; nếu không xóa header cùng tên do client tự gửi, backend có thể tin nhầm danh tính.
Request có HMAC hợp lệ từ client đã xác thực nhưng client không có quyền đọc tenant được yêu cầu; hệ thống cần tách quyết định authentication khỏi authorization.
Một client được phép gọi endpoint đọc nhưng gửi request ký hợp lệ tới endpoint xóa dữ liệu; policy cần kiểm tra permission theo principal, method và resource.
API dùng chung một secret cho nhiều môi trường development, staging và production; rò rỉ ở môi trường thử nghiệm có thể mở đường vào production.
Proxy retry request sang upstream thứ hai sau khi upstream đầu đã xử lý nhưng phản hồi bị mất; nonce và idempotency cần phối hợp để tránh thực hiện hành động hai lần.
Đội tích hợp thay đổi canonicalization từ phiên bản 1 sang phiên bản 2 nhưng không gắn version vào hợp đồng chữ ký; client cũ và server mới tạo kết quả khác nhau.
Kiểm thử chỉ dùng một ví dụ request thành công nên bỏ sót query trùng, header lặp, Unicode, body rỗng và path encoding; bộ test cần có vector chuẩn và ca âm tính.
Nhóm fuzz canonicalization phát hiện hai request khác nhau tạo cùng chuỗi canonical; cần đánh giá khả năng signature collision ở tầng biểu diễn dù HMAC vẫn an toàn về mật mã.
Audit log lưu toàn bộ Authorization header và signature để hỗ trợ điều tra; dữ liệu này có thể hỗ trợ replay và cần được che hoặc loại bỏ khỏi log.
API nhận request có HMAC đúng nhưng payload bị thay đổi sau bước xác minh do middleware transform body; kiến trúc cần xác định ranh giới tin cậy và thứ tự xử lý.
