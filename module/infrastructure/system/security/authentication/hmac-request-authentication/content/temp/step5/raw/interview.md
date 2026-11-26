Bạn giải thích HMAC cung cấp tính xác thực và toàn vẹn cho HTTP request như thế nào và vì sao nó không mã hóa nội dung?
Bạn phân biệt xác thực request bằng HMAC với xác thực bằng TLS client certificate hoặc bearer token ra sao?
Bạn mô tả vai trò của shared secret và yêu cầu hai phía phải quản lý cùng một bí mật như thế nào?
Bạn xác định những thành phần nào của HTTP request cần đưa vào canonical request theo hợp đồng ký như thế nào?
Bạn thiết kế định dạng canonical request để client và server tạo ra cùng một chuỗi byte từ request như thế nào?
Bạn chuẩn hóa HTTP method và xử lý method extension hoặc method override trong hợp đồng ký ra sao?
Bạn xác định quy tắc canonicalize path khi có dấu chấm, dấu phân cách lặp hoặc percent-encoded characters như thế nào?
Bạn xử lý percent-encoding và Unicode trong URI để tránh client và server diễn giải thành hai đường dẫn khác nhau ra sao?
Bạn chuẩn hóa query parameters khi có nhiều tham số cùng tên, thứ tự khác nhau hoặc giá trị rỗng như thế nào?
Bạn quyết định có sắp xếp query parameters hay giữ nguyên thứ tự dựa trên ngữ nghĩa API như thế nào?
Bạn phân biệt dấu cộng trong query string với khoảng trắng được percent-encode khi tạo canonical URI ra sao?
Bạn xác định cách xử lý dấu phân cách, fragment, Host và default port trong URI canonical như thế nào?
Bạn chuẩn hóa tên header không phân biệt chữ hoa chữ thường và thứ tự header trong canonical request ra sao?
Bạn xử lý header xuất hiện nhiều lần bằng quy tắc nối giá trị hoặc từ chối request như thế nào?
Bạn chuẩn hóa khoảng trắng và tab trong header value mà không làm thay đổi ý nghĩa giao thức như thế nào?
Bạn lựa chọn tập signed headers để bảo vệ các thuộc tính ảnh hưởng tới xác thực và xử lý nghiệp vụ như thế nào?
Bạn đánh giá rủi ro khi bỏ sót Content-Type, Content-Encoding hoặc header điều khiển hành vi khỏi danh sách ký ra sao?
Bạn xác định header nào không nên ký vì có thể bị proxy hoặc hạ tầng trung gian thay đổi hợp lệ như thế nào?
Bạn thiết kế canonical request version để tiến hóa hợp đồng ký mà không gây nhầm lẫn giữa các phiên bản ra sao?
Bạn sử dụng delimiter hoặc length-prefix để tránh nhập nhằng khi ghép các trường canonical request như thế nào?
Bạn phân biệt canonicalize dữ liệu với serialize dữ liệu và xác định trách nhiệm của từng bước ra sao?
Bạn lựa chọn ký raw body bytes hay biểu diễn JSON canonical dựa trên yêu cầu tương thích và ngữ nghĩa API như thế nào?
Bạn tính body digest và đưa digest vào canonical request để phát hiện nội dung bị sửa đổi như thế nào?
Bạn xử lý request body rỗng, binary hoặc multipart khi tính chữ ký ra sao?
Bạn thiết kế xác minh chữ ký cho request body streaming lớn mà không cần giữ toàn bộ payload trong RAM như thế nào?
Bạn xác định ảnh hưởng của gzip hoặc Content-Encoding tới thứ tự giải nén, tính digest và xác minh chữ ký ra sao?
Bạn phân biệt Content-Length với Transfer-Encoding khi xác định chính xác byte sequence được ký như thế nào?
Bạn lựa chọn HMAC-SHA-256 hoặc thuật toán được phê duyệt khác và quản lý định danh thuật toán trong hợp đồng ký ra sao?
Bạn ngăn client tự chọn thuật toán tùy ý hoặc hạ cấp thuật toán trong từng request như thế nào?
Bạn phân biệt encoding của signature với giá trị MAC nhị phân được tính từ thuật toán như thế nào?
Bạn xác minh chữ ký bằng cách tính lại MAC và so sánh kết quả theo constant-time như thế nào?
Bạn xử lý signature sai định dạng, sai độ dài hoặc chứa ký tự không hợp lệ trước bước so sánh ra sao?
Bạn phân biệt key identifier công khai với shared secret bí mật trong metadata xác thực như thế nào?
Bạn thiết kế header Authorization mang key ID, timestamp, nonce và danh sách signed headers như thế nào?
Bạn xác định cách parse metadata chữ ký để tránh gateway và backend diễn giải khác nhau ra sao?
Bạn xác minh HMAC ở giai đoạn nào để request chưa hợp lệ không thể kích hoạt side effect nghiệp vụ?
Bạn phân biệt xác thực chữ ký thành công với việc principal được cấp quyền thực hiện API như thế nào?
Bạn ánh xạ key ID sang client identity, tenant và phạm vi quyền được phép như thế nào?
Bạn thiết kế quyền riêng cho từng key theo method, resource hoặc loại thao tác ra sao?
Bạn ngăn một key hợp lệ gọi endpoint hoặc tenant ngoài phạm vi được cấp quyền như thế nào?
Bạn giải thích timestamp giúp giới hạn thời gian sử dụng của một request như thế nào?
Bạn lựa chọn clock skew window để cân bằng replay protection với sai lệch đồng hồ giữa client và server ra sao?
Bạn phát hiện và xử lý client có đồng hồ lệch lớn hoặc không đồng bộ NTP như thế nào?
Bạn thiết kế nonce khó đoán và gắn nonce với key identity cùng timestamp để chống replay ra sao?
Bạn lưu nonce theo cách atomic để hai request giống nhau đến đồng thời không cùng vượt qua kiểm tra replay như thế nào?
Bạn lựa chọn TTL và dung lượng nonce store theo cửa sổ timestamp và lưu lượng request ra sao?
Bạn xử lý nonce store phân tán hoặc đa vùng để cùng một nonce không được chấp nhận ở hai node khác nhau như thế nào?
Bạn xác định hành vi an toàn khi nonce store không khả dụng hoặc gặp lỗi consistency ra sao?
Bạn phân biệt chống replay bằng nonce với idempotency key dùng để xử lý retry hợp lệ của nghiệp vụ như thế nào?
Bạn xử lý request hợp lệ được retry sau timeout khi nonce cũ đã bị tiêu thụ như thế nào?
Bạn phân tích những thay đổi mà reverse proxy hoặc API gateway có thể thực hiện với method, path, host và headers trước khi ứng dụng xác minh chữ ký ra sao?
Bạn xác định ranh giới cần xác minh HMAC khi request đi qua nhiều gateway hoặc service mesh như thế nào?
Bạn thiết kế hợp đồng canonicalization thống nhất giữa client SDK, gateway và backend để tránh signature mismatch ra sao?
Bạn xử lý path rewrite, prefix stripping hoặc trailing slash normalization tại proxy như thế nào?
Bạn xác định cách xử lý header được proxy thêm, xóa hoặc gộp trước khi xác minh chữ ký ra sao?
Bạn bảo vệ header định danh client khỏi bị giả mạo khi proxy chuyển tiếp request tới backend như thế nào?
Bạn đánh giá rủi ro request smuggling hoặc parser differential khi proxy và backend diễn giải framing khác nhau ra sao?
Bạn xác định cách xác minh chữ ký khi HTTP/2 được chuyển đổi sang HTTP/1.1 tại gateway như thế nào?
Bạn lựa chọn xác minh tại gateway hay tại từng service dựa trên ranh giới tin cậy và yêu cầu audit nào?
Bạn truyền identity đã được gateway xác thực tới backend mà không tin header do client trực tiếp gửi như thế nào?
Bạn quản lý shared secret trong secret manager hoặc KMS và giới hạn quyền đọc secret cho từng thành phần ra sao?
Bạn thiết kế key rotation có giai đoạn chồng lấp giữa key cũ và key mới mà không làm gián đoạn client như thế nào?
Bạn xác định thời điểm ngừng chấp nhận key cũ và chứng minh toàn bộ client đã chuyển key mới ra sao?
Bạn phân biệt rotation định kỳ với thu hồi khẩn cấp khi secret có dấu hiệu bị lộ như thế nào?
Bạn thiết kế key riêng cho từng client hoặc tenant để giới hạn phạm vi ảnh hưởng khi một secret bị compromise ra sao?
Bạn lựa chọn cách tạo, phân phối và lưu trữ shared secret để tránh xuất hiện trong source code, log hoặc cấu hình rõ ra sao?
Bạn xác định quy trình cấp phát, gia hạn, thu hồi và kiểm kê key theo vòng đời client như thế nào?
Bạn xử lý request ký bằng key đã bị thu hồi nhưng vẫn nằm trong cache của một số instance như thế nào?
Bạn đánh giá khả năng dùng asymmetric signature thay cho HMAC khi cần nhiều verifier hoặc yêu cầu non-repudiation như thế nào?
Bạn thiết kế test vectors để client và server độc lập tạo ra cùng canonical request và signature ra sao?
Bạn kiểm thử từng trường hợp thay đổi method, path, query, signed header hoặc body để xác nhận chữ ký bị từ chối như thế nào?
Bạn xây dựng test cho percent encoding, Unicode, duplicate headers và query parameters lặp để phát hiện canonicalization mismatch ra sao?
Bạn kiểm thử replay với timestamp cũ, timestamp tương lai, nonce trùng và request đồng thời như thế nào?
Bạn kiểm thử key rotation, key revocation và cache propagation trên nhiều instance ra sao?
Bạn xây dựng integration test qua reverse proxy thực tế để phát hiện request bị biến đổi trước bước xác minh như thế nào?
Bạn kiểm tra khả năng tương thích giữa client SDK bằng ngôn ngữ khác nhau thông qua bộ canonical request fixtures ra sao?
Bạn xác minh request có chữ ký hợp lệ nhưng thiếu quyền vẫn bị từ chối đúng chính sách như thế nào?
Bạn kiểm thử lỗi nonce store, secret manager hoặc clock synchronization để xác nhận hệ thống xử lý fail-safe ra sao?
Bạn thiết kế logging và metrics cho signature mismatch, expired timestamp, replay detection và key ID không hợp lệ mà không ghi secret ra sao?
Bạn xây dựng cảnh báo cho tỷ lệ signature failure tăng bất thường để phân biệt tấn công với lỗi triển khai client như thế nào?
Bạn xác định thông tin cần có trong audit event để truy vết client, key version và request ID mà vẫn bảo vệ bí mật ra sao?
Bạn xây dựng runbook xử lý signature mismatch diện rộng sau khi thay đổi proxy hoặc canonicalization như thế nào?
Bạn xác định bằng chứng cần có để chứng minh HMAC authentication bảo đảm toàn vẹn, chống replay và giới hạn đúng quyền truy cập trong production như thế nào?
