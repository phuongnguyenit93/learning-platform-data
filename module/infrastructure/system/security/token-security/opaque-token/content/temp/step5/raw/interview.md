Bạn giải thích opaque access token là gì và vì sao resource server không nên tự diễn giải nội dung token?
Opaque access token khác JWT ở cấu trúc, khả năng kiểm chứng và cách resource server xác minh như thế nào?
Trong những bối cảnh nào authorization server nên phát hành opaque token thay vì JWT tự chứa claim?
Bạn phân biệt opaque access token, reference token và refresh token như thế nào?
Những lợi ích về quyền riêng tư và kiểm soát tập trung nào có thể đạt được khi dùng opaque token?
Những đánh đổi về độ trễ và tính sẵn sàng nào xuất hiện khi resource server phải gọi introspection endpoint?
Bạn xác định độ dài và entropy của opaque token ra sao để giảm nguy cơ đoán trúng hoặc dò quét?
Vì sao token cần được tạo từ bộ sinh số ngẫu nhiên mật mã thay vì UUID hoặc giá trị dễ dự đoán trong một số thiết kế?
Bạn thiết kế cách bảo đảm token không trùng lặp khi authorization server chạy trên nhiều node hoặc region như thế nào?
Bạn lựa chọn định dạng token có thể truyền an toàn trong HTTP header mà không làm lộ thông tin nội bộ ra sao?
Authorization server có thể lưu token theo dạng hash như thế nào để giảm tác động nếu kho dữ liệu token bị đọc trái phép?
Những chỉ mục nào cần có để tra cứu token hiệu quả mà không lưu plaintext token làm khóa tra cứu?
Bạn thiết kế vòng đời token từ phát hành, kích hoạt, hết hạn, thu hồi đến xóa metadata như thế nào?
Những khác biệt nào cần xử lý giữa access token và refresh token khi lưu trữ, sử dụng và thu hồi?
Resource server lấy opaque token từ request theo quy ước nào và cần xử lý ra sao khi token bị thiếu hoặc sai định dạng?
Bạn mô tả luồng introspection giữa resource server và authorization server theo OAuth 2.0 như thế nào?
RFC 7662 định nghĩa mục đích của introspection endpoint và trường `active` trong phản hồi ra sao?
Vì sao `active: true` chưa đủ để kết luận một request được phép thực hiện mọi hành động trên tài nguyên?
Những trường nào trong introspection response thường hữu ích cho quyết định authorization tại resource server?
Resource server nên xử lý thế nào khi introspection response không có `scope`, `aud` hoặc `exp` mà policy yêu cầu?
`token_type_hint` trong yêu cầu introspection có ý nghĩa gì và vì sao server không nên xem nó là bằng chứng về loại token?
Resource server cần xác thực với introspection endpoint bằng cơ chế nào và vì sao không nên để endpoint này public?
Bạn phân tách credential gọi introspection giữa các resource server như thế nào để giới hạn blast radius?
Những biện pháp nào bảo vệ introspection request và response trên đường truyền khỏi nghe lén hoặc sửa đổi?
Bạn áp dụng least privilege cho quyền introspect như thế nào khi nhiều API và dịch vụ cùng dùng một authorization server?
Vì sao không nên ghi opaque token nguyên giá trị vào application log, audit log hoặc distributed trace?
Bạn thiết kế cơ chế che token trong reverse proxy, gateway và hệ thống quan sát như thế nào?
Resource server nên kiểm tra issuer và audience trong introspection response ra sao trước khi chấp nhận token?
Bạn xử lý audience khi một access token được cấp cho nhiều resource server như thế nào để tránh token substitution?
Bạn ánh xạ scope trong introspection response sang quyền trên endpoint và hành động nghiệp vụ như thế nào?
Vì sao resource server cần kiểm tra cả client identity lẫn subject khi quyết định quyền truy cập?
Bạn phân biệt token đại diện cho client với token đại diện cho người dùng trong trường `sub` và `client_id` như thế nào?
Resource server nên diễn giải `exp`, `iat` và `nbf` ra sao khi đánh giá hiệu lực token?
Bạn xử lý sai lệch đồng hồ giữa authorization server và resource server như thế nào mà không kéo dài hiệu lực token quá mức?
Những rủi ro nào phát sinh nếu resource server chỉ kiểm tra `active` mà bỏ qua scope, audience và ngữ cảnh request?
Bạn thiết kế positive caching cho introspection response như thế nào để cân bằng hiệu năng với tốc độ thu hồi token?
TTL của cache introspection nên phụ thuộc vào những yếu tố nào như `exp`, mức nhạy cảm và yêu cầu revocation?
Bạn tính toán giới hạn độ trễ thu hồi tối đa khi resource server cache kết quả introspection ra sao?
Vì sao cache key không nên chứa nguyên opaque token và có thể thay bằng định danh dẫn xuất nào?
Bạn đồng bộ hoặc vô hiệu hóa cache introspection giữa nhiều instance resource server như thế nào khi token bị revoke?
Negative caching cho token không hợp lệ giúp giảm tải introspection ra sao và cần giới hạn thời gian thế nào?
Bạn xử lý trường hợp cache vẫn ghi nhận token active sau khi authorization server đã thu hồi token như thế nào?
Khi introspection endpoint tạm thời không khả dụng, resource server nên lựa chọn fail closed hay dùng kết quả cache còn hạn dựa trên tiêu chí nào?
Bạn cấu hình timeout, connection pool và circuit breaker cho lời gọi introspection như thế nào để tránh làm nghẽn request API?
Retry introspection request cần tuân theo nguyên tắc nào để không tạo retry storm khi authorization server quá tải?
Bạn giới hạn tốc độ introspection theo resource server, client hoặc token như thế nào để chống lạm dụng endpoint?
Những chỉ số và log nào giúp theo dõi độ trễ, tỷ lệ lỗi, cache hit và tải của introspection mà không lộ token?
Bạn thiết kế high availability cho introspection endpoint và kho trạng thái token như thế nào?
Những vấn đề nhất quán nào có thể xuất hiện khi trạng thái token được replicate giữa nhiều region?
Bạn bảo đảm việc phát hành và thu hồi token không tạo ra khoảng thời gian mà các region đưa ra quyết định trái ngược ra sao?
OAuth 2.0 token revocation endpoint liên hệ với introspection như thế nào trong quy trình thu hồi opaque token?
Bạn phân biệt expire, revoke và disable một token hoặc client trong mô hình opaque token như thế nào?
Khi người dùng đăng xuất hoặc quản trị viên khóa tài khoản, những access token liên quan cần bị vô hiệu hóa theo chính sách nào?
Bạn xử lý refresh token rotation và phát hiện refresh token reuse như thế nào khi access token là opaque?
Vì sao thu hồi token ở authorization server chưa chắc làm mất hiệu lực ngay tại resource server đang cache kết quả?
Bạn thiết kế chính sách thời hạn access token theo loại client, mức nhạy cảm và khả năng introspection như thế nào?
Những rủi ro bearer-token nào vẫn tồn tại với opaque token và có thể giảm bằng mTLS hoặc DPoP ra sao?
Bạn ràng buộc opaque access token với client certificate hoặc proof-of-possession như thế nào để hạn chế replay?
Bạn phân tích nguy cơ token bị đánh cắp qua browser storage, cookie, URL hoặc header và chọn cách truyền phù hợp ra sao?
Trong ứng dụng trình duyệt, khi access token được giữ trong cookie, bạn xử lý CSRF và thuộc tính cookie như thế nào?
Bạn kiểm soát việc introspection response tiết lộ username, subject, scope hoặc metadata nhạy cảm cho resource server ra sao?
Những trường hợp nào nên trả về `active: false` và làm thế nào để tránh tiết lộ lý do token không hợp lệ cho caller không tin cậy?
Bạn kiểm thử introspection cho token hợp lệ, hết hạn, bị revoke, sai audience và sai client như thế nào?
Bạn kiểm thử hành vi cache khi token vừa được phát hành, vừa bị thu hồi hoặc vừa hết hạn ra sao?
Bạn xây dựng kiểm thử chịu lỗi cho timeout, lỗi xác thực introspection, HTTP 5xx và authorization server mất kết nối như thế nào?
Bạn so sánh chi phí vận hành opaque token với JWT khi số lượng resource server và lưu lượng API tăng mạnh?
Bạn lập kế hoạch chuyển từ JWT sang opaque token mà vẫn duy trì tương thích giữa client, gateway và resource server như thế nào?
Những tiêu chí nào giúp quyết định một API nên introspect mỗi request, cache kết quả hay dùng một mô hình kết hợp?
Bạn điều tra tình huống token được introspection là active nhưng API vẫn trả 401 hoặc 403 theo một quy trình nào?
Bạn phân biệt lỗi token không hợp lệ, lỗi introspection dependency và lỗi authorization tại resource server như thế nào?
