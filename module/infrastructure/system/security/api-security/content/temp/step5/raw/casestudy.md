Một API quản lý đơn hàng yêu cầu bearer token hợp lệ nhưng người dùng chỉ cần thay orderId trong URL là đọc được đơn của khách hàng khác; hãy phân tích ranh giới giữa xác thực và kiểm tra quyền trên từng object.
Một endpoint cập nhật hồ sơ cho phép client gửi thêm trường role, tenantId và accountStatus dù giao diện không hiển thị các trường này; hãy đánh giá nguy cơ mass assignment và quyền ghi theo thuộc tính.
Một API quản trị được ẩn khỏi tài liệu OpenAPI nhưng vẫn có thể gọi trực tiếp bằng HTTP method PUT từ tài khoản người dùng thông thường; hãy phân tích lỗi phân quyền chức năng và cách kiểm tra toàn bộ endpoint.
Một dịch vụ đa tenant xác minh JWT đúng chữ ký và audience nhưng truy vấn database chỉ lọc theo resource ID, khiến người dùng tenant A truy cập dữ liệu tenant B; hãy xác định điểm thiếu tenant isolation.
API gateway xác minh access token và chuyển tiếp X-User-Role do client gửi lên, trong khi service nội bộ tin header này để cấp quyền xóa tài nguyên; hãy phân tích nguy cơ giả mạo identity qua trust boundary.
Sau khi identity provider xoay JWKS key, một số API instance vẫn chấp nhận token ký bằng key cũ đã bị thu hồi do cache public key không đồng nhất; hãy đánh giá hành vi rotation và thu hồi trên toàn cụm.
Một API nhận JWT có thuật toán nằm trong header token và chấp nhận cấu hình thuật toán không được chính sách cho phép; hãy phân tích nguy cơ algorithm confusion hoặc downgrade.
Một access token hợp lệ về chữ ký và thời hạn vẫn được dùng sau khi người dùng bị khóa tài khoản vì API không kiểm tra trạng thái thu hồi hoặc phiên; hãy đánh giá lựa chọn JWT self-validation và introspection.
Một service-to-service API chỉ kiểm tra client_id mà không kiểm tra scope hoặc audience, khiến credential của một dịch vụ đọc được dữ liệu ngoài phạm vi; hãy phân tích thiết kế workload identity và quyền tối thiểu.
Một API key dùng chung cho tất cả đối tác bị lộ trong log của một nhà cung cấp, nhưng đội vận hành không thể xác định client nào đã thực hiện request hoặc thu hồi riêng credential; hãy đánh giá cách cấp phát và quản lý vòng đời key.
Một API tải báo cáo theo reportId kiểm tra quyền ở endpoint xem metadata nhưng endpoint tải file lại chỉ kiểm tra đăng nhập; hãy phân tích sự không nhất quán giữa các thao tác trên cùng object.
Một endpoint tìm kiếm trả về email, số điện thoại và internal flags trong JSON dù người gọi chỉ cần tên hiển thị; hãy xác định nguy cơ excessive data exposure và quyền đọc từng field.
Một API batch cho phép gửi danh sách hàng nghìn userId và chỉ kiểm tra quyền trên phần tử đầu tiên, khiến các object khác tenant vẫn được trả về; hãy phân tích cách kiểm soát authorization cho bulk operations.
Một tác vụ export được xếp hàng sau khi người dùng có quyền khởi tạo, nhưng quyền truy cập bị thu hồi trước lúc worker chạy và worker vẫn xuất dữ liệu; hãy đánh giá authorization tại thời điểm thực thi bất đồng bộ.
Một endpoint chuyển quyền sở hữu tài nguyên kiểm tra owner trước khi cập nhật trong transaction riêng, tạo khoảng thời gian để một request đồng thời thay owner; hãy phân tích TOCTOU và tính nguyên tử của kiểm tra cùng cập nhật.
Một API cập nhật trạng thái đơn hàng cho phép client gửi trực tiếp trạng thái Delivered dù quy trình chưa thanh toán hoặc chưa xuất kho; hãy xác định thiếu kiểm soát state transition và business authorization.
Một endpoint thay đổi email yêu cầu access token nhưng không yêu cầu xác minh lại danh tính hoặc xác thực tăng cường, dẫn đến kẻ chiếm phiên đổi địa chỉ khôi phục; hãy đánh giá step-up authentication cho thao tác nhạy cảm.
Một API nhận JSON và deserialize trực tiếp vào domain entity, khiến client có thể sửa trường internalPrice và approvalStatus ngoài hợp đồng; hãy phân tích validation schema và allowlist field.
Một endpoint lọc dữ liệu ghép chuỗi sort column từ query parameter vào câu SQL, tạo ra truy vấn ngoài dự kiến dù giá trị filter đã được parameterize; hãy đánh giá kiểm soát identifier động.
Một API tìm kiếm tài liệu dùng NoSQL query object trực tiếp từ request body, cho phép client gửi toán tử truy vấn thay vì giá trị tìm kiếm đơn giản; hãy phân tích NoSQL injection và schema validation.
Một endpoint nhận URL callback và gọi HTTP client tới địa chỉ do người dùng chỉ định; kẻ tấn công cung cấp địa chỉ loopback để truy cập trang quản trị nội bộ; hãy đánh giá SSRF.
Một tính năng import ảnh chỉ kiểm tra hostname trước khi tải, nhưng DNS trả về private IP sau khi kiểm tra và thay đổi ở lần resolve tiếp theo; hãy phân tích DNS rebinding và xác minh địa chỉ đích.
Một API fetch URL cho phép redirect tự động, khiến URL công khai chuyển hướng tới cloud metadata endpoint dù hostname ban đầu nằm trong allowlist; hãy đánh giá redirect policy và kiểm tra từng hop.
Một API kiểm tra thumbnail chặn IPv4 private nhưng không xử lý IPv6 loopback, IPv4-mapped IPv6 và các dạng biểu diễn IP khác; hãy phân tích bypass SSRF qua địa chỉ thay thế.
Một service xử lý webhook gọi URL phản hồi do tenant cấu hình và cho phép port bất kỳ, gây truy cập tới dịch vụ nội bộ trong mạng; hãy đánh giá allowlist scheme, host, port và egress controls.
Một endpoint proxy ảnh không giới hạn thời gian kết nối, số redirect hoặc kích thước phản hồi, khiến một URL chậm giữ worker và tải dữ liệu lớn vào bộ nhớ; hãy phân tích SSRF kết hợp resource exhaustion.
Một API cho phép người dùng upload file rồi server giải nén archive, trong đó tên entry chứa đường dẫn đi ra ngoài thư mục đích; hãy đánh giá path traversal trong quá trình giải nén.
Một endpoint nhận XML từ đối tác và parser mặc định cho phép external entity, khiến request có thể đọc tài nguyên cục bộ hoặc gọi URL nội bộ; hãy phân tích cấu hình parser và XXE.
Một API nhận JSON lồng sâu và mảng rất lớn, khiến CPU tăng mạnh và bộ nhớ cạn dù tổng request rate không cao; hãy xác định giới hạn kích thước, độ sâu và số phần tử cần áp dụng.
Một endpoint báo cáo cho phép tùy ý kết hợp nhiều bộ lọc và sort, tạo truy vấn database quét hàng triệu bản ghi trong một request; hãy đánh giá query cost control, timeout và quota theo endpoint.
Một API GraphQL cho phép nested query sâu và alias lặp hàng trăm lần, khiến một request tiêu tốn CPU và số lần truy vấn rất lớn; hãy phân tích query depth, complexity và batching limits.
Một endpoint export không giới hạn pagination size và cho phép client yêu cầu toàn bộ dữ liệu trong một response, gây tăng heap và timeout ở database; hãy xác định giới hạn pagination và streaming.
Một khách hàng tự động retry khi timeout, nhưng API tạo thanh toán mới mỗi lần vì không lưu idempotency key nguyên tử; hãy phân tích duplicate side effect và cách xác định kết quả của request lặp.
Một API áp dụng rate limit chỉ theo IP, khiến attacker phân tán request qua nhiều proxy để vượt quota trong khi người dùng chung NAT bị khóa nhầm; hãy đánh giá rate limit theo danh tính, tenant và hành vi.
Một cụm API có nhiều instance nhưng mỗi instance giữ bộ đếm rate limit trong RAM riêng, cho phép client vượt giới hạn bằng cách phân phối request qua load balancer; hãy phân tích consistency và atomicity của distributed limiter.
Một endpoint gửi SMS OTP không giới hạn số lần gửi theo tài khoản và số điện thoại, gây chi phí tăng đột biến và làm phiền người dùng; hãy xác định quota, cooldown và phát hiện abuse.
Một API tạo tài khoản chấp nhận nhiều request đồng thời với cùng email vì kiểm tra tồn tại và insert không nằm trong ràng buộc nguyên tử; hãy phân tích race condition và chống automation abuse.
Một API CORS phản hồi Access-Control-Allow-Origin bằng giá trị Origin nhận được và bật credentials cho mọi request, khiến trang web không tin cậy có thể đọc dữ liệu phiên; hãy đánh giá cấu hình CORS và CSRF.
Một API dùng cookie session cho thao tác chuyển tiền nhưng không kiểm tra CSRF token hoặc Origin, khiến trình duyệt gửi request từ trang bên ngoài; hãy phân tích CSRF protection.
Một API trả dữ liệu cá nhân với Cache-Control mặc định, và reverse proxy dùng shared cache phục vụ response của một người dùng cho người khác; hãy đánh giá cache key và chính sách no-store.
Một API trả lỗi validation có kèm SQL statement, filesystem path và stack trace, giúp người gọi suy ra cấu trúc nội bộ; hãy phân tích error handling và information disclosure.
Access log ghi nguyên Authorization header, query string và request body, khiến access token và dữ liệu cá nhân xuất hiện trong hệ thống log tập trung; hãy đánh giá redaction và kiểm soát truy cập log.
Một webhook endpoint chỉ kiểm tra nguồn IP nhưng không xác minh chữ ký payload, cho phép request giả mạo sự kiện thanh toán từ Internet; hãy phân tích xác thực nguồn và toàn vẹn nội dung webhook.
Một webhook có chữ ký hợp lệ nhưng không kiểm tra timestamp hoặc event ID đã xử lý, khiến cùng một sự kiện hoàn tiền được gửi lại nhiều lần; hãy đánh giá replay protection và idempotent consumer.
Một API gateway xác thực token nhưng service backend vẫn có thể được truy cập trực tiếp từ mạng nội bộ mà không có authentication; hãy phân tích bypass gateway và xác thực tại service.
Một phiên bản API cũ vẫn hoạt động sau khi chính sách quyền mới được áp dụng cho phiên bản mới, cho phép client gọi endpoint legacy để lấy dữ liệu rộng hơn; hãy đánh giá versioning và deprecation security.
Một API file download kiểm tra quyền ở bước tạo link nhưng URL ký có thời hạn quá dài và không ràng buộc với người nhận, khiến link bị chia sẻ tiếp tục tải được; hãy phân tích quyền truy cập và vòng đời signed URL.
Một API đa tenant dùng tenantId từ request header để chọn schema database nhưng không xác minh tenant đó thuộc danh tính đã xác thực; hãy xác định nguy cơ tenant context spoofing.
Một API nội bộ tin X-Forwarded-For do mọi client gửi lên để áp dụng IP allowlist, khiến attacker tự đặt địa chỉ IP của mạng tin cậy; hãy phân tích proxy trust configuration.
Một dịch vụ API không ghi audit event cho thao tác đọc dữ liệu nhạy cảm, khiến đội bảo mật không thể xác định phạm vi truy cập sau khi phát hiện token bị lộ; hãy đánh giá thiết kế audit và điều tra.
Một hệ thống chỉ cảnh báo theo số lượng HTTP 401 tổng thể, không phân tách client, endpoint hoặc tenant, khiến credential stuffing quy mô nhỏ trên nhiều tài khoản không bị phát hiện; hãy thiết kế quan sát và phát hiện hành vi bất thường.
Một đợt phát hành mới thay đổi authorization middleware nhưng chỉ chạy happy-path tests, khiến quyền truy cập object và field bị mở rộng ngoài ý muốn; hãy đánh giá kiểm thử âm tính BOLA, BFLA và BOPLA.
Một cuộc kiểm thử bảo mật phát hiện SSRF chỉ khi URL dùng IPv4 dạng chuẩn, trong khi các dạng IPv6, redirect và DNS rebinding chưa được kiểm tra; hãy xây dựng phạm vi kiểm thử và tiêu chí xác minh phòng vệ.
Một sự cố API bị khai thác đồng thời qua token bị lộ, quyền object sai và endpoint export không giới hạn; hãy lập cách khoanh vùng ảnh hưởng, thu hồi credential, bảo toàn bằng chứng và xác minh khắc phục nhiều lớp.
