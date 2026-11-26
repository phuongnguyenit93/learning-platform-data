Bạn sẽ xây dựng threat model cho một API bằng cách xác định tài sản, tác nhân, trust boundary và luồng dữ liệu như thế nào?
Bạn sẽ kiểm kê endpoint và phương thức HTTP để tìm các bề mặt tấn công bị bỏ sót trong một hệ thống microservices ra sao?
Bạn sẽ phân biệt xác thực danh tính, phân quyền hành động và kiểm soát quyền truy cập dữ liệu trong thiết kế API như thế nào?
Bạn sẽ giải thích vì sao HTTPS và đăng nhập thành công chưa đủ để bảo đảm API an toàn như thế nào?
Bạn sẽ thiết kế chính sách bảo mật riêng theo endpoint, loại tài nguyên và hành động nghiệp vụ dựa trên rủi ro nào?
Bạn sẽ xác định cách áp dụng nguyên tắc deny by default khi một endpoint mới được thêm vào như thế nào?
Bạn sẽ lựa chọn OAuth 2.0 hoặc OpenID Connect theo nhu cầu ủy quyền API và xác thực người dùng ra sao?
Bạn sẽ phân biệt access token, ID token và refresh token về mục đích, nơi sử dụng và vòng đời như thế nào?
Bạn sẽ thiết kế Authorization Code Flow với PKCE cho ứng dụng public client để hạn chế nguy cơ đánh cắp authorization code ra sao?
Bạn sẽ lựa chọn Client Credentials Flow cho giao tiếp service-to-service và quản lý danh tính workload như thế nào?
Bạn sẽ xác định khi nào API key phù hợp và vì sao không nên dùng API key như cơ chế xác thực người dùng đầy đủ ra sao?
Bạn sẽ lưu trữ, hash, giới hạn scope và xoay vòng API key để giảm thiệt hại khi credential bị lộ như thế nào?
Bạn sẽ xác minh JWT bằng cách kiểm tra chữ ký, thuật toán, issuer, audience và thời hạn ra sao?
Bạn sẽ ngăn thuật toán JWT bị hạ cấp hoặc bị chọn sai thông qua header token bằng chính sách nào?
Bạn sẽ xử lý JWKS key rotation và cache public key để vừa xác minh token liên tục vừa thu hồi khóa bị lộ như thế nào?
Bạn sẽ phân biệt token hết hạn, token bị thu hồi và token có chữ ký hợp lệ nhưng không được phép truy cập ra sao?
Bạn sẽ lựa chọn opaque token với introspection thay cho JWT tự xác minh khi cần kiểm soát thu hồi tập trung như thế nào?
Bạn sẽ bảo vệ refresh token bằng rotation, phát hiện reuse và ràng buộc với client ra sao?
Bạn sẽ xác định cách truyền access token để tránh token xuất hiện trong URL, log hoặc browser history như thế nào?
Bạn sẽ thiết kế mTLS cho API nội bộ để xác thực workload và quản lý vòng đời certificate ra sao?
Bạn sẽ phân biệt xác thực ở API gateway với xác thực lại tại service xử lý tài nguyên theo ranh giới tin cậy như thế nào?
Bạn sẽ giải thích lỗi Broken Object Level Authorization khi người dùng thay ID trong request và cách phòng tránh như thế nào?
Bạn sẽ kiểm tra quyền sở hữu hoặc quan hệ truy cập trên từng object trước khi đọc, sửa hay xóa dữ liệu như thế nào?
Bạn sẽ phân biệt quyền theo role, scope, attribute và relationship khi thiết kế authorization cho API ra sao?
Bạn sẽ thiết kế kiểm soát truy cập đa tenant để người dùng không thể đọc hoặc sửa tài nguyên của tenant khác như thế nào?
Bạn sẽ ngăn Broken Function Level Authorization khi endpoint ẩn hoặc HTTP method ít dùng vẫn có thể được gọi trực tiếp ra sao?
Bạn sẽ xử lý Broken Object Property Level Authorization khi API trả về trường nhạy cảm mà người gọi không được phép xem như thế nào?
Bạn sẽ xây dựng allowlist các trường được đọc và ghi để ngăn mass assignment hoặc excessive data exposure ra sao?
Bạn sẽ bảo đảm quyền được kiểm tra lại khi một tác vụ bất đồng bộ thực thi sau thời điểm request ban đầu được chấp nhận ra sao?
Bạn sẽ phân tích race condition hoặc TOCTOU khi quyền sở hữu tài nguyên thay đổi giữa bước kiểm tra và bước cập nhật như thế nào?
Bạn sẽ lựa chọn xử lý quyền tại gateway, service hay tầng truy cập dữ liệu theo từng loại kiểm soát như thế nào?
Bạn sẽ thiết kế validation phía server cho body, query, path parameter và header theo schema như thế nào?
Bạn sẽ phân biệt validation cú pháp, validation ngữ nghĩa và kiểm tra quy tắc nghiệp vụ khi tiếp nhận request ra sao?
Bạn sẽ chuẩn hóa encoding và canonicalization trước khi kiểm tra đầu vào để tránh một giá trị vượt qua bộ lọc nhưng được diễn giải khác ở tầng sau như thế nào?
Bạn sẽ giới hạn content type, kích thước body, độ sâu JSON và số phần tử mảng để giảm nguy cơ parser abuse ra sao?
Bạn sẽ ngăn SQL injection, NoSQL injection và command injection bằng cách kết hợp parameterized query, allowlist và phân quyền như thế nào?
Bạn sẽ phân biệt input validation với output encoding và xác định khi nào cần từng biện pháp trong API trả HTML hoặc nội dung động ra sao?
Bạn sẽ xử lý file upload để kiểm tra kích thước, MIME type, magic bytes, tên file và vị trí lưu trữ an toàn như thế nào?
Bạn sẽ ngăn path traversal khi API nhận tên file hoặc đường dẫn do client cung cấp ra sao?
Bạn sẽ thiết kế SSRF protection khi API tải URL do người dùng gửi bằng allowlist scheme, host và port như thế nào?
Bạn sẽ ngăn SSRF truy cập loopback, private network, link-local và cloud metadata endpoint bằng cách nào?
Bạn sẽ xử lý DNS rebinding và thay đổi IP sau khi resolve hostname để tránh SSRF vượt qua kiểm tra ban đầu như thế nào?
Bạn sẽ kiểm soát redirect trong tính năng fetch URL để không cho phép chuyển hướng từ host được phép sang địa chỉ nội bộ ra sao?
Bạn sẽ lựa chọn egress firewall, isolated network và proxy kiểm soát outbound để bổ sung lớp phòng vệ SSRF như thế nào?
Bạn sẽ giới hạn timeout, số redirect, kích thước phản hồi và loại nội dung khi API gọi URL bên ngoài như thế nào?
Bạn sẽ thiết kế rate limiting theo IP, user, API key, tenant và endpoint để giảm abuse mà không khóa nhầm người dùng hợp lệ ra sao?
Bạn sẽ phân biệt fixed window, sliding window, leaky bucket và token bucket khi lựa chọn thuật toán giới hạn lưu lượng như thế nào?
Bạn sẽ xử lý rate limit phân tán khi nhiều API instance cùng phục vụ một user mà vẫn cần giới hạn nhất quán ra sao?
Bạn sẽ lựa chọn trả HTTP 429, Retry-After và quota metadata để client có thể phục hồi đúng cách như thế nào?
Bạn sẽ kiểm soát concurrent requests, queue length và thời gian xử lý để ngăn một client chiếm hết tài nguyên API ra sao?
Bạn sẽ xác định endpoint nào có nguy cơ tiêu tốn CPU, memory hoặc chi phí bên thứ ba cao để áp dụng quota riêng như thế nào?
Bạn sẽ giới hạn pagination, filter, sort và batch size để truy vấn lớn không làm cạn tài nguyên backend ra sao?
Bạn sẽ bảo vệ API tìm kiếm hoặc GraphQL trước truy vấn quá sâu, quá rộng hay có độ phức tạp tính toán cao như thế nào?
Bạn sẽ thiết kế giới hạn upload, decompression và xử lý archive để phòng tránh payload nén gây tiêu thụ tài nguyên bất thường ra sao?
Bạn sẽ ngăn replay request có tác động tài chính hoặc nghiệp vụ bằng idempotency key, nonce hay timestamp như thế nào?
Bạn sẽ xử lý race condition khi hai request đồng thời đổi trạng thái cùng một đơn hàng hoặc số dư tài khoản ra sao?
Bạn sẽ xác định cách bảo vệ quy trình nhiều bước như đặt hàng, hoàn tiền hoặc đổi quyền khỏi việc gọi sai thứ tự endpoint như thế nào?
Bạn sẽ phát hiện và ngăn automation abuse như tạo tài khoản hàng loạt, vét mã khuyến mại hoặc dò thông tin đăng nhập ra sao?
Bạn sẽ thiết kế kiểm soát CORS theo origin, method và header cụ thể mà không coi CORS là cơ chế xác thực như thế nào?
Bạn sẽ giải thích CSRF có thể xảy ra với API dùng cookie tự động gửi và cách kết hợp SameSite, token hoặc kiểm tra origin ra sao?
Bạn sẽ cấu hình cookie session với Secure, HttpOnly và SameSite theo ngữ cảnh ứng dụng như thế nào?
Bạn sẽ xác định khi nào cần cache-control no-store cho phản hồi chứa dữ liệu nhạy cảm và cách tránh shared cache lưu nhầm ra sao?
Bạn sẽ thiết kế bảo vệ dữ liệu nhạy cảm bằng data minimization, encryption in transit và encryption at rest như thế nào?
Bạn sẽ phân biệt dữ liệu cần che trong response với dữ liệu cần giữ nội bộ để phục vụ audit và điều tra như thế nào?
Bạn sẽ quản lý secrets, signing keys và database credentials cho API bằng secret manager và quy trình rotation ra sao?
Bạn sẽ ngăn token, mật khẩu, PII và payload nhạy cảm xuất hiện trong application log, trace hoặc error message như thế nào?
Bạn sẽ thiết kế error response không tiết lộ stack trace, SQL, đường dẫn nội bộ hoặc trạng thái tài khoản nhạy cảm ra sao?
Bạn sẽ xác định những sự kiện bảo mật nào cần audit như đăng nhập thất bại, truy cập bị từ chối và thay đổi quyền như thế nào?
Bạn sẽ bảo đảm audit log có thể truy nguyên nhưng không thể bị người dùng API sửa hoặc xóa tùy ý ra sao?
Bạn sẽ thiết kế webhook authentication bằng chữ ký HMAC hoặc chữ ký bất đối xứng và xác minh payload theo cách nào?
Bạn sẽ ngăn replay và giả mạo webhook bằng timestamp, nonce, secret rotation và idempotent processing như thế nào?
Bạn sẽ kiểm soát API versioning và deprecation để endpoint cũ không tiếp tục giữ quyền yếu hơn sau khi thay đổi chính sách ra sao?
Bạn sẽ xây dựng bộ kiểm thử âm tính cho BOLA, BFLA và BOPLA bằng cách thay đổi object ID, role và field trong request như thế nào?
Bạn sẽ kết hợp unit test authorization, integration test và contract test để chứng minh mỗi endpoint áp dụng đúng policy ra sao?
Bạn sẽ sử dụng fuzzing và property-based testing để tìm lỗi validation, parser và xử lý dữ liệu bất thường trong API như thế nào?
Bạn sẽ phân biệt SAST, DAST, dependency scanning và penetration testing trong quy trình kiểm tra bảo mật API ra sao?
Bạn sẽ thiết kế test SSRF bao gồm private IP, IPv6, redirect, DNS rebinding và các dạng địa chỉ biểu diễn khác nhau như thế nào?
Bạn sẽ kiểm thử rate limit và quota trong môi trường nhiều instance để phát hiện race condition hoặc bypass ra sao?
Bạn sẽ giám sát tỷ lệ 401, 403, 429, lỗi validation và hành vi truy cập bất thường để phát hiện tấn công như thế nào?
Bạn sẽ thiết kế cảnh báo cho dấu hiệu enumeration object ID, credential stuffing hoặc tăng đột biến request nhạy cảm ra sao?
Bạn sẽ phân biệt lưu lượng tăng hợp lệ với abuse bằng cách kết hợp danh tính, hành vi, endpoint và lịch sử sử dụng như thế nào?
Bạn sẽ thiết kế quy trình ứng phó khi API key hoặc access token bị lộ gồm thu hồi, xoay khóa, điều tra và thông báo ra sao?
Nếu người dùng đã đăng nhập nhưng có thể đọc đơn hàng của người khác bằng cách đổi ID, bạn sẽ xác định và sửa lỗi authorization ở đâu?
Nếu API gateway xác minh JWT thành công nhưng service nội bộ vẫn nhận request không có quyền, bạn sẽ thiết kế lại ranh giới phân quyền ra sao?
Nếu một endpoint tải ảnh từ URL cho phép truy cập địa chỉ metadata của cloud, bạn sẽ khoanh vùng bypass và triển khai phòng vệ SSRF nhiều lớp như thế nào?
Nếu người dùng có thể sửa trường role hoặc tenantId khi cập nhật profile, bạn sẽ ngăn mass assignment và kiểm tra quyền thuộc tính như thế nào?
Nếu nhiều request đồng thời dùng cùng idempotency key nhưng tạo ra hai giao dịch, bạn sẽ sửa thiết kế lưu khóa và tính nguyên tử ra sao?
Nếu CORS chỉ cho phép một origin nhưng API vẫn bị gọi bằng credential của nạn nhân, bạn sẽ kiểm tra CSRF và cơ chế xác thực như thế nào?
Nếu log bảo mật cho thấy tăng mạnh 403 và 404 trên nhiều object ID liên tiếp, bạn sẽ điều tra enumeration và bảo toàn bằng chứng ra sao?
Bạn sẽ thiết kế chương trình bảo mật API đầu cuối cho một hệ thống đa tenant gồm xác thực, phân quyền object và function, validation, SSRF, chống abuse, bảo vệ dữ liệu, kiểm thử và giám sát như thế nào?
