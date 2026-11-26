Bạn sẽ giải thích API key nhận diện client và kiểm soát quyền gọi API như thế nào, đồng thời nêu rõ những điều nó không chứng minh về danh tính người dùng?
Bạn sẽ phân biệt API key với mật khẩu người dùng, session cookie, OAuth access token và client certificate theo mục đích xác thực ra sao?
Bạn sẽ xác định trường hợp nào API key phù hợp cho tích hợp máy-với-máy và trường hợp nào cần OAuth hoặc mTLS như thế nào?
Bạn sẽ xây dựng threat model cho API key bằng cách xác định nơi tạo, lưu, truyền, sử dụng và những nơi khóa có thể bị lộ ra sao?
Bạn sẽ thiết kế định dạng API key có entropy đủ lớn, dễ nhận diện phiên bản và không để lộ thông tin bí mật trong phần định danh như thế nào?
Bạn sẽ lựa chọn khóa ngẫu nhiên opaque hay token có cấu trúc theo nhu cầu tra cứu, vận hành và thu hồi ra sao?
Bạn sẽ tạo API key bằng bộ sinh số ngẫu nhiên mật mã và kiểm soát chất lượng entropy như thế nào?
Bạn sẽ thiết kế key identifier hoặc prefix để tra cứu bản ghi khóa mà không phải lưu toàn bộ secret dạng rõ ra sao?
Bạn sẽ hiển thị secret API key cho người dùng đúng một lần và xử lý trường hợp họ làm mất khóa như thế nào?
Bạn sẽ phân biệt API key công khai dùng để nhận diện ứng dụng với secret key có khả năng cấp quyền truy cập như thế nào?
Bạn sẽ lưu API key trong cơ sở dữ liệu bằng hash hoặc HMAC có khóa thay vì lưu plaintext ra sao?
Bạn sẽ lựa chọn thuật toán hash phù hợp cho secret API key có entropy cao và đánh giá vai trò của salt hoặc pepper như thế nào?
Bạn sẽ xác minh API key bằng cách tra cứu identifier, tính hash và so sánh an toàn để hạn chế timing leak ra sao?
Bạn sẽ thiết kế schema lưu khóa gồm owner, trạng thái, scope, quota, thời hạn và metadata kiểm toán như thế nào?
Bạn sẽ xác định cách phân biệt khóa đang hoạt động, chờ kích hoạt, hết hạn, bị thu hồi và bị khóa tạm thời ra sao?
Bạn sẽ truyền API key qua HTTP header theo chuẩn và tránh đặt secret trong URL query string như thế nào?
Bạn sẽ giải thích vì sao API key phải được bảo vệ bằng TLS và những rủi ro còn lại khi TLS đã được bật ra sao?
Bạn sẽ xử lý trường hợp reverse proxy hoặc API gateway ghi lại header chứa API key vào access log như thế nào?
Bạn sẽ ngăn API key xuất hiện trong browser history, analytics, referrer, crash report và thông báo lỗi ra sao?
Bạn sẽ lựa chọn lưu API key ở secret manager, vault hoặc hệ thống quản lý cấu hình theo loại workload như thế nào?
Bạn sẽ đánh giá rủi ro lưu API key trong source code, file .env, container image hoặc CI build log ra sao?
Bạn sẽ thiết kế cấp phát API key theo client, ứng dụng, môi trường và mục đích sử dụng như thế nào?
Bạn sẽ phân biệt API key của developer cá nhân với key của service account trong quản lý quyền và trách nhiệm ra sao?
Bạn sẽ giới hạn số lượng key được cấp cho một client và xây dựng quy trình phê duyệt key có quyền cao như thế nào?
Bạn sẽ gắn API key với owner, tenant và môi trường để tránh dùng nhầm khóa staging cho production ra sao?
Bạn sẽ thiết kế scope API key theo resource và action thay vì cấp quyền truy cập toàn bộ API như thế nào?
Bạn sẽ phân biệt scope, role và quota trong chính sách sử dụng API key ra sao?
Bạn sẽ kiểm tra scope của API key tại gateway và service đích để tránh endpoint nhạy cảm chỉ dựa vào việc khóa hợp lệ như thế nào?
Bạn sẽ ngăn một API key đọc hoặc sửa tài nguyên thuộc tenant khác bằng cách kết hợp client identity và object-level authorization ra sao?
Bạn sẽ xác định cách áp dụng quyền chỉ đọc, quyền ghi và quyền quản trị cho các key khác nhau như thế nào?
Bạn sẽ xử lý một API key có nhiều scope nhưng một endpoint chỉ cho phép một tập con quyền cụ thể ra sao?
Bạn sẽ thiết kế quota theo key, client, tenant và endpoint để kiểm soát mức tiêu thụ API như thế nào?
Bạn sẽ phân biệt rate limit theo thời gian với quota tích lũy theo ngày hoặc tháng trong chính sách API key ra sao?
Bạn sẽ chọn thuật toán token bucket hoặc sliding window cho rate limiting và giải thích cách xử lý request vượt ngưỡng như thế nào?
Bạn sẽ triển khai rate limiting phân tán khi nhiều gateway replica cùng xác minh một API key như thế nào?
Bạn sẽ lựa chọn phản hồi 429, Retry-After và thông tin quota còn lại để client tự điều chỉnh lưu lượng ra sao?
Bạn sẽ ngăn một client chia nhỏ lưu lượng qua nhiều API key để né quota tổng của tenant như thế nào?
Bạn sẽ thiết kế giới hạn concurrency, payload size và chi phí xử lý cho key gọi endpoint nặng ra sao?
Bạn sẽ lựa chọn API key hay HMAC request signing khi cần phát hiện nội dung request bị sửa đổi trên đường truyền như thế nào?
Bạn sẽ phân biệt API key bearer với chữ ký HMAC có timestamp và nonce về khả năng chống giả mạo và replay ra sao?
Bạn sẽ đánh giá rủi ro replay khi API key bị sao chép và thiết kế idempotency hoặc cơ chế chống replay cho thao tác nhạy cảm như thế nào?
Bạn sẽ tổ chức xoay vòng API key định kỳ mà không làm gián đoạn client đang hoạt động ra sao?
Bạn sẽ thiết kế giai đoạn overlap giữa key cũ và key mới cùng thời hạn kết thúc rõ ràng như thế nào?
Bạn sẽ xác minh client đã chuyển sang key mới trước khi thu hồi key cũ bằng telemetry và báo cáo nào?
Bạn sẽ phân biệt rotation chủ động, rotation theo sự kiện rò rỉ và thay thế key do thay đổi nhân sự như thế nào?
Bạn sẽ thu hồi API key tức thời trên nhiều gateway replica và service cache như thế nào?
Bạn sẽ xử lý độ trễ đồng bộ trạng thái thu hồi khi gateway cache kết quả xác minh API key ra sao?
Bạn sẽ thiết kế thời hạn hiệu lực và chính sách hết hạn cho key theo mức độ nhạy cảm của quyền được cấp như thế nào?
Bạn sẽ lựa chọn khóa tạm thời, khóa dùng một lần hoặc key có giới hạn IP/network theo đặc điểm tích hợp nào?
Bạn sẽ xác định khi nào cần khóa khẩn cấp một client và cách giảm ảnh hưởng đến các client hợp lệ khác như thế nào?
Bạn sẽ thiết kế API quản trị để tạo, xem metadata, xoay vòng và thu hồi key mà không bao giờ trả lại secret cũ ra sao?
Bạn sẽ phân quyền thao tác quản lý key để người dùng chỉ có thể quản lý key thuộc tổ chức hoặc ứng dụng của họ như thế nào?
Bạn sẽ bảo vệ endpoint cấp phát API key trước CSRF, privilege escalation và lạm dụng tạo khóa hàng loạt ra sao?
Bạn sẽ lựa chọn cơ chế xác thực bổ sung hoặc phê duyệt hai người cho việc cấp key có quyền quản trị như thế nào?
Bạn sẽ phân biệt key xác thực client với quyền của user cuối cùng khi một ứng dụng dùng chung API key phục vụ nhiều người dùng ra sao?
Bạn sẽ kết hợp API key với OAuth hoặc user authentication để vừa nhận diện ứng dụng vừa phân quyền người dùng như thế nào?
Bạn sẽ đánh giá nguy cơ một API key bị nhúng trong ứng dụng mobile hoặc frontend JavaScript và cách giảm thiểu ra sao?
Bạn sẽ ngăn key dùng trong CI/CD bị lộ qua log, artifact, biến môi trường hoặc cache build như thế nào?
Bạn sẽ bảo vệ API key trong Kubernetes bằng Secret, workload identity và quyền truy cập service account ra sao?
Bạn sẽ quản lý API key khi service chạy trên nhiều cloud hoặc môi trường hybrid mà không sao chép secret thủ công như thế nào?
Bạn sẽ thiết kế API gateway để xác minh key, áp dụng scope, quota và chuyển metadata client tới backend một cách an toàn ra sao?
Bạn sẽ xác định backend có nên tự xác minh API key hay tin kết quả gateway dựa trên ranh giới mạng và mô hình đe dọa nào?
Bạn sẽ ngăn client giả mạo header nội bộ như X-Consumer-ID hoặc X-API-Key-Owner khi gateway chuyển tiếp request như thế nào?
Bạn sẽ xử lý trường hợp request đi thẳng đến backend bỏ qua gateway và vượt qua kiểm soát API key ra sao?
Bạn sẽ thiết kế cache xác minh API key để giảm tải database mà vẫn đáp ứng yêu cầu thu hồi nhanh như thế nào?
Bạn sẽ đánh giá tác động của cache TTL, negative caching và cache invalidation đến bảo mật key ra sao?
Bạn sẽ xử lý khi dịch vụ quản lý key hoặc database xác minh tạm thời không khả dụng theo nguyên tắc fail-open hay fail-closed như thế nào?
Bạn sẽ phân biệt lỗi key không hợp lệ, key hết hạn, key bị thu hồi và thiếu scope mà không tiết lộ quá nhiều thông tin cho client ra sao?
Bạn sẽ thiết kế audit log cho việc tạo, xem metadata, rotation, revoke và sử dụng API key như thế nào?
Bạn sẽ ghi nhận last-used time, source IP, endpoint và client identity mà không ghi lại secret vào telemetry ra sao?
Bạn sẽ phát hiện dấu hiệu key bị chia sẻ hoặc sử dụng từ vị trí, thiết bị hay mẫu lưu lượng bất thường như thế nào?
Bạn sẽ xây dựng cảnh báo khi một key đột ngột tăng request, gọi endpoint nhạy cảm hoặc phát sinh lỗi xác thực hàng loạt ra sao?
Bạn sẽ phân biệt key bị lộ với client hợp lệ tăng tải bằng cách kết hợp hành vi, lịch sử và ngữ cảnh mạng như thế nào?
Bạn sẽ thiết kế quy trình ứng phó khi API key xuất hiện trong Git repository, ticket, chat hoặc log tập trung ra sao?
Bạn sẽ xác định phạm vi ảnh hưởng của một key bị lộ bằng audit trail, request history và quan hệ giữa key với tenant như thế nào?
Bạn sẽ phối hợp thu hồi khóa, cấp khóa thay thế, rà soát truy cập và thông báo cho owner sau sự cố ra sao?
Bạn sẽ tìm và xóa các bản sao API key đã bị lộ khỏi log, artifact, backup hoặc hệ thống theo dõi theo quy trình nào?
Bạn sẽ kiểm thử API key authentication gồm key hợp lệ, sai, hết hạn, bị thu hồi, thiếu scope và vượt quota như thế nào?
Bạn sẽ xây dựng kiểm thử bảo đảm key của tenant này không thể truy cập dữ liệu của tenant khác bằng cách nào?
Bạn sẽ kiểm thử rotation và revoke trên nhiều gateway replica để xác nhận key cũ bị từ chối trong giới hạn thời gian nào?
Bạn sẽ kiểm tra timing behavior, cache và xử lý lỗi để giảm nguy cơ dò tìm key hợp lệ như thế nào?
Bạn sẽ thiết kế kiểm thử tải cho xác minh key và rate limit để tìm điểm nghẽn khi số client tăng như thế nào?
Bạn sẽ đo tỷ lệ xác thực thành công, key bị từ chối, quota exceeded và thời gian xác minh để đánh giá vận hành ra sao?
Bạn sẽ xây dựng chính sách migration từ một API key dùng chung sang key riêng theo client và scope tối thiểu như thế nào?
Bạn sẽ đề xuất vòng đời quản trị API key đầu cuối cho nền tảng đa tenant gồm cấp phát, lưu trữ, xác minh, quota, rotation, thu hồi và ứng phó rò rỉ như thế nào?
