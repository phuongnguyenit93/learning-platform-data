Một API nhận URL do người dùng cung cấp để tạo bản xem trước. Cách kiểm tra nào giảm nguy cơ parser và HTTP client diễn giải URL khác nhau?
A. Dùng regex tìm chuỗi https ở đầu rồi giữ nguyên URL ban đầu
B. Dùng cùng URL parser với HTTP client, chuẩn hóa rồi kiểm tra scheme, host và port
C. Tách chuỗi tại dấu gạch chéo đầu tiên rồi kiểm tra phần còn lại
D. Chỉ chuyển hostname sang lowercase rồi dùng regex so khớp phần host với allowlist
Đáp án đúng: B

Một hostname ban đầu trỏ tới IP công khai nhưng có thể đổi DNS trước lúc kết nối. Biện pháp nào chống DNS rebinding hiệu quả nhất?
A. Tin TTL DNS và dùng lại kết quả phân giải trong cache hệ điều hành
B. Chặn hostname có chữ localhost và giữ nguyên các tên còn lại
C. Kiểm tra mọi IP được phân giải rồi kết nối tới IP đã xác thực, giữ TLS hostname
D. Chỉ phân giải DNS lúc lưu URL, sau đó tái sử dụng IP đã cache cho mọi request sau
Đáp án đúng: C

Một tên miền trả về đồng thời địa chỉ công khai và địa chỉ thuộc mạng private. Chính sách nào an toàn cho dịch vụ fetch URL?
A. Từ chối hostname nếu bất kỳ kết quả DNS nào thuộc dải không công khai
B. Chọn IP đầu tiên vì resolver thường ưu tiên địa chỉ hợp lệ
C. Chỉ kiểm tra bản ghi A, còn AAAA để hệ điều hành tự lựa chọn theo cấu hình mạng
D. Cho phép nếu URL dùng HTTPS và certificate của hostname hợp lệ
Đáp án đúng: A

Một allowlist domain phải hỗ trợ tên miền quốc tế hóa. Cách so khớp nào tránh bypass bằng Unicode và Punycode?
A. So sánh tên miền Unicode sau khi bỏ dấu chấm cuối và chuyển toàn bộ về chữ thường
B. Dùng phép contains trên hostname để nhận mọi subdomain liên quan
C. Chuẩn hóa IDNA thành ASCII rồi so khớp hostname đầy đủ theo allowlist
D. Chuyển hostname về lowercase rồi so sánh hậu tố bằng chuỗi thường
Đáp án đúng: C

Một validator chặn IPv4 private nhưng không xét địa chỉ IPv6 tương đương. Cần bổ sung bước nào?
A. Chỉ từ chối IPv6 có hai dấu hai chấm và địa chỉ bắt đầu bằng fe80
B. Chặn mọi hostname có bản ghi AAAA dù địa chỉ đó công khai
C. Chuẩn hóa IP sang dạng nhị phân rồi kiểm tra các dải special-use
D. Chuyển IPv6 sang dạng text đầy đủ trước khi so sánh chuỗi
Đáp án đúng: C

URL chứa userinfo dạng https://trusted.example@127.0.0.1/ vượt qua bộ lọc kiểm tra chuỗi. Cách xử lý nào đúng?
A. Tin phần hostname xuất hiện trước ký tự @ trong URL
B. Bỏ path rồi so sánh authority mà không xác minh host sau parse
C. Chỉ từ chối userinfo khi username hoặc password không rỗng
D. Dùng URL parser xác định host thực tế và từ chối URL có userinfo
Đáp án đúng: D

Một dịch vụ tải tài liệu tự động theo redirect. URL công khai trả 302 tới địa chỉ loopback. Kiểm soát nào cần thiết?
A. Kiểm tra lại scheme, hostname và IP đích ở từng hop redirect
B. Chỉ xác minh URL ban đầu rồi cho phép tối đa năm redirect
C. Tin redirect nếu response đầu tiên có certificate hợp lệ
D. Chặn redirect chỉ khi hostname đích khác domain gốc
Đáp án đúng: A

HTTP client gửi Authorization header tới URL ban đầu rồi nhận redirect sang origin khác. Cách bảo vệ credential nào phù hợp?
A. Không chuyển credential qua origin khác và chỉ forward header được cho phép
B. Giữ nguyên mọi header nhạy cảm để endpoint redirect có thể tiếp tục xác thực caller
C. Chỉ xóa Cookie khi redirect đổi hostname nhưng giữ bearer token
D. Chuyển Authorization sang query parameter để tránh mất header
Đáp án đúng: A

Một URL shortener có thể tạo chuỗi redirect nhiều bước. Chính sách nào hạn chế SSRF và lạm dụng tài nguyên?
A. Cho phép mọi redirect HTTPS miễn response có Content-Type hợp lệ
B. Chỉ xác minh URL ban đầu, giới hạn số hop nhưng không kiểm tra lại từng đích
C. Giới hạn hop, phát hiện vòng lặp và áp lại policy đích cho từng hop
D. Chỉ giới hạn tổng thời gian request và giữ nguyên đích cuối cùng
Đáp án đúng: C

Một tích hợp chỉ được phép gọi HTTPS trên cổng 443. URL có port tùy chỉnh vẫn vượt qua kiểm tra scheme. Cần xác minh gì?
A. Kiểm tra port hiệu lực sau parse và chỉ cho phép cặp scheme/port đã duyệt
B. Chỉ kiểm tra scheme và để HTTP client tự chọn cổng mặc định
C. Chặn mọi URL có dấu hai chấm sau hostname kể cả port mặc định
D. So sánh port trong chuỗi gốc trước khi chuẩn hóa scheme và hostname của URL
Đáp án đúng: A

Một worker resolve hostname để kiểm tra IP nhưng HTTP client lại tự resolve lần nữa. Thiết kế nào giảm race condition?
A. Dùng hostname để resolve DNS rồi để HTTP client tự chọn IP từ cache hiện có cho từng request
B. Pin kết nối tới IP đã xác thực, đồng thời giữ hostname cho TLS/SNI và Host
C. Tăng TTL DNS để giảm khả năng thay đổi bản ghi trong lúc request
D. Tắt xác minh certificate để client có thể kết nối trực tiếp tới IP
Đáp án đúng: B

DNS resolver không trả lời trong lúc ứng dụng kiểm tra đích outbound. Hành vi nào an toàn nhất?
A. Dùng hostname trực tiếp vì HTTP client có thể tự xử lý phân giải
B. Fail closed khi DNS lỗi, retry giới hạn và không fallback
C. Dùng IP gần nhất trong cache dù kết quả đó đã quá hạn
D. Bỏ bước kiểm tra DNS nếu URL dùng HTTPS và có hostname hợp lệ
Đáp án đúng: B

Một đối tác dùng certificate TLS tự ký. Cách hỗ trợ mà vẫn xác minh peer phù hợp là gì?
A. Cấu hình trust anchor hoặc certificate pinning có quản lý cho đối tác
B. Tắt certificate verification cho hostname đối tác trong mọi môi trường
C. Chấp nhận mọi certificate miễn kết nối được mã hóa bằng TLS
D. Bỏ hostname verification nhưng vẫn kiểm tra thời hạn chứng chỉ
Đáp án đúng: A

Một URL bắt đầu bằng HTTPS nhưng redirect cuối cùng hạ xuống HTTP. Chính sách nào giữ bảo mật đường truyền?
A. Chấp nhận HTTP nếu hostname không đổi và hop đầu có certificate hợp lệ
B. Chỉ kiểm tra certificate ở hop đầu tiên của chuỗi redirect
C. Bắt buộc HTTPS và xác minh certificate cùng hostname tại mọi hop
D. Chỉ từ chối HTTP khi request có header Authorization
Đáp án đúng: C

Nhiều workload dùng chung một client certificate mTLS để gọi dịch vụ đối tác. Rủi ro quản lý danh tính nào phát sinh?
A. Không thể xác minh certificate chain khi nhiều workload dùng chung khóa
B. Mọi request tự động được mã hóa bằng cùng một session key cố định
C. Khó cô lập quyền và thu hồi riêng workload khi một client key bị lộ
D. Certificate hết hạn nhanh hơn khi được nhiều process sử dụng
Đáp án đúng: C

Một endpoint fetch URL chuyển tiếp header của request inbound sang máy chủ đích. Cách thiết kế nào giảm rò rỉ thông tin?
A. Tạo header outbound theo allowlist và không chuyển credential inbound
B. Forward header inbound trừ các trường client không hỗ trợ
C. Chỉ xóa User-Agent và giữ Cookie cùng Authorization
D. Chuyển header nhạy cảm thành query parameter trước khi gửi
Đáp án đúng: A

Một dịch vụ ghi toàn bộ URL outbound vào log, trong khi URL có signed query token. Cách xử lý nào phù hợp?
A. Ghi URL đầy đủ vì log chỉ nhân viên vận hành được xem
B. Mã hóa log file nhưng vẫn lưu nguyên query string
C. Chỉ xóa scheme và hostname trước khi ghi log
D. Redact token query và không đặt secret trong URL
Đáp án đúng: D

Một tính năng tạo preview có thể truy cập cloud metadata endpoint qua SSRF. Lớp phòng vệ nào phù hợp nhất?
A. Chỉ chặn chuỗi hostname metadata trong bộ lọc URL
B. Chỉ yêu cầu HTTPS tới metadata và tin certificate của máy chủ
C. Chỉ giảm timeout kết nối tới metadata endpoint xuống một giây
D. Chặn egress metadata và mạng nhạy cảm, giảm quyền workload
Đáp án đúng: D

Một pod có thể gọi bất kỳ IP nào trong VPC do không có chính sách egress. Kiểm soát nào giảm phạm vi SSRF?
A. Chỉ dùng NetworkPolicy ingress để giới hạn ai gọi được pod
B. Tắt DNS trong pod nhưng vẫn cho phép kết nối IP trực tiếp
C. Áp dụng default-deny egress rồi chỉ mở các đích cần thiết cho workload
D. Mã hóa traffic bằng service mesh mà không giới hạn đích đến
Đáp án đúng: C

Ứng dụng đã kiểm tra URL ở tầng code nhưng worker vẫn có thể kết nối tới mọi subnet. Phòng vệ bổ sung nào hợp lý?
A. Tăng số lần kiểm tra URL trong cùng một hàm validation
B. Chỉ ghi log các IP đích để điều tra sau khi có sự cố
C. Chỉ chuyển outbound request qua một HTTP client dùng chung
D. Áp dụng egress firewall hoặc network policy làm lớp giới hạn độc lập
Đáp án đúng: C

Một tenant tự cấu hình webhook URL và có thể thay đổi DNS sau khi lưu cấu hình. Cách xử lý nào an toàn?
A. Chỉ kiểm tra URL khi tenant lưu cấu hình rồi tin hostname đó trong mọi lần gửi
B. Kiểm tra policy lúc gửi, resolve và pin IP, rồi xác minh redirect từng lần
C. Chỉ kiểm tra IP lúc lưu webhook, không kiểm tra lại khi worker gửi request
D. Chỉ ký payload webhook để endpoint không thể sửa nội dung request
Đáp án đúng: B

Một job lưu URL để xử lý sau vài giờ. DNS của hostname thay đổi trước lúc worker thực thi. Cần làm gì?
A. Dùng kết quả DNS đã lưu khi tạo job dù thời điểm thực thi đã khác
B. Tin cache DNS của node để bảo đảm tính nhất quán giữa các job
C. Chỉ xác minh TLS certificate sau khi worker đã mở kết nối
D. Resolve và áp policy đích tại thời điểm thực thi từng request
Đáp án đúng: D

Một URL hợp lệ redirect tới địa chỉ thuộc mạng quản trị. Kiểm soát nào ngăn redirect-based SSRF?
A. Chỉ kiểm tra hostname gốc vì redirect là hành vi của máy chủ đích
B. Cho phép redirect nếu response có status code thuộc nhóm 3xx
C. Chặn redirect cross-origin nhưng không cần kiểm tra IP cùng origin
D. Xác minh lại hostname, IP, port và scheme của từng đích redirect
Đáp án đúng: D

Một endpoint proxy nhận URL cùng method, body và header do caller chỉ định. Cách giảm bề mặt lạm dụng nào tốt nhất?
A. Cho phép mọi method nhưng giới hạn số byte của response
B. Chỉ cho phép method, header, content type và body theo use case cụ thể
C. Forward method, body và header inbound theo request gốc
D. Chỉ thay đổi User-Agent trước khi gửi request ra ngoài
Đáp án đúng: B

Một fetch service tải response lớn từ host bên ngoài; Content-Length có thể thiếu hoặc sai. Giới hạn nào đáng tin cậy?
A. Dựa hoàn toàn vào Content-Length để từ chối response lớn
B. Giới hạn số byte thực tế khi stream và dừng ngay khi vượt ngưỡng
C. Chỉ giới hạn thời gian đọc response và không cần giới hạn byte
D. Đọc toàn bộ body vào RAM rồi mới kiểm tra kích thước thực tế
Đáp án đúng: B

Một response gzip nhỏ sau giải nén tạo ra nhiều gigabyte dữ liệu. Cách hạn chế resource exhaustion nào phù hợp?
A. Chỉ giới hạn kích thước compressed body trước khi giải nén
B. Tắt timeout đọc vì decompression có thể cần nhiều thời gian
C. Tin Content-Type của máy chủ để xác định dữ liệu có an toàn hay không
D. Giới hạn kích thước sau giải nén, tỷ lệ nén và tài nguyên parser
Đáp án đúng: D

Một request outbound treo khi server đích nhận kết nối nhưng gửi dữ liệu rất chậm. Timeout nào cần phối hợp?
A. Dùng deadline tổng cùng timeout riêng cho DNS, connect, TLS và read
B. Chỉ đặt connect timeout để tránh chờ thiết lập TCP quá lâu
C. Chỉ đặt read timeout và để DNS cùng TLS handshake không giới hạn
D. Đặt timeout rất dài để không hủy response của đối tác hợp lệ
Đáp án đúng: A

Một client tự retry POST sau timeout; server đích có thể đã xử lý lần đầu. Chính sách nào giảm tác dụng phụ?
A. Retry ngay mọi lỗi mạng để tăng khả năng giao dịch hoàn tất
B. Chỉ retry khi status code là 5xx mà không xét tính idempotent
C. Retry không giới hạn với exponential delay để tránh mất request
D. Giới hạn retry và chỉ lặp thao tác an toàn hoặc có idempotency key
Đáp án đúng: D

Một ứng dụng gọi API đối tác bằng service token. Người dùng điều khiển URL đích của request. Cách bảo vệ token nào đúng?
A. Gắn token vào URL để HTTP client quản lý header tự động
B. Dùng token riêng cho từng đối tác và chỉ gửi tới origin đã tin cậy
C. Gửi token cho mọi host rồi dựa vào TLS để bảo vệ bí mật
D. Mã hóa token bằng Base64 trước khi đặt trong request body
Đáp án đúng: B

Một tính năng import tài liệu hỗ trợ scheme ngoài HTTP/HTTPS nhưng không cần các giao thức đó. Cách giảm bề mặt tấn công là gì?
A. Cho phép mọi scheme mà thư viện client hỗ trợ sẵn
B. Allowlist rõ ràng scheme cần thiết và từ chối scheme ngoài phạm vi
C. Chỉ chặn file:// và giữ lại các scheme khác theo mặc định
D. Kiểm tra phần mở rộng URL để suy ra scheme an toàn
Đáp án đúng: B

Một endpoint outbound bị lạm dụng để quét cổng nhiều host nội bộ. Kiểm soát nào hạn chế khả năng dò mạng?
A. Chỉ giới hạn request theo tổng số lần gọi mỗi phút
B. Chỉ ẩn địa chỉ IP đích khỏi response và giữ nguyên khả năng gọi mạng
C. Giới hạn dải đích, port, tốc độ và egress theo workload
D. Chỉ yêu cầu người dùng đăng nhập trước khi gửi URL
Đáp án đúng: C

Một webhook sender nhận response 302 và payload chứa dữ liệu khách hàng có thể bị gửi sang host khác. Cách xử lý nào giảm rò rỉ?
A. Không tự động chuyển payload nhạy cảm sang origin mới nếu chưa được policy cho phép
B. Luôn forward payload và header qua mọi redirect để giao nhận thành công
C. Tắt TLS verification khi redirect để tránh lỗi chứng chỉ đích
D. Chỉ giới hạn redirect tối đa mười hop rồi tiếp tục gửi payload
Đáp án đúng: A

Một hệ thống tích hợp OAuth cho phép tenant nhập issuer URL tùy ý; token request có thể gửi client secret tới host đó. Kiểm soát nào cần có?
A. Chỉ chấp nhận issuer đăng ký trước và allowlist endpoint từ discovery metadata
B. Chỉ kiểm tra HTTPS và certificate hợp lệ cho issuer do tenant nhập
C. Mã hóa client secret trước khi gửi tới endpoint do tenant nhập
D. Tin discovery metadata khi tải qua TLS và cache theo TTL
Đáp án đúng: A

Một nhóm điều tra SSRF cần biết request nào đã truy cập IP nội bộ nhưng log chỉ lưu status code. Telemetry nào hữu ích?
A. Chỉ lưu tổng số outbound request theo phút và response status
B. Ghi correlation ID, hostname chuẩn hóa, IP kết nối và policy decision
C. Ghi nguyên request header cùng body để tái hiện toàn bộ nội dung
D. Chỉ lưu DNS query time và bỏ qua redirect chain cùng workload identity
Đáp án đúng: B

Một worker outbound bị khai thác và attacker muốn dùng nó làm bàn đạp vào hệ thống. Kiến trúc nào giới hạn thiệt hại tốt nhất?
A. Chạy worker với quyền mạng và quyền cloud giống ứng dụng chính
B. Dùng chung secret và filesystem để worker dễ truy cập dữ liệu nghiệp vụ
C. Chỉ tăng logging mức debug để phát hiện hành vi sau khi xảy ra
D. Cô lập worker, giới hạn egress, credential và quyền truy cập tài nguyên
Đáp án đúng: D

Một nền tảng fetch URL phục vụ nhiều tenant cần chính sách outbound nhất quán. Thiết kế nào phù hợp nhất?
A. Mỗi endpoint tự kiểm tra URL, DNS, redirect và TLS theo logic riêng đã triển khai
B. Dùng chung allowlist hostname nhưng không kiểm tra DNS hoặc redirect
C. Chỉ dựa vào firewall để kiểm soát IP đích, bỏ qua xác minh URL ở tầng ứng dụng
D. Policy tập trung cho URL, DNS, IP, redirect và egress theo cùng một chuẩn
Đáp án đúng: D
