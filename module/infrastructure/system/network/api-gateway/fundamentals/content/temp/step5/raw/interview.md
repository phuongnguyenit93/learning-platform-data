Bạn sẽ giải thích API Gateway giải quyết những vấn đề nào khi một ứng dụng có nhiều backend service?
Bạn sẽ xác định tiêu chí nào để quyết định một hệ thống có cần API Gateway hay có thể để client gọi trực tiếp backend?
Bạn sẽ phân biệt vai trò của API Gateway, reverse proxy, load balancer và ingress controller trong một kiến trúc dịch vụ như thế nào?
Bạn sẽ mô tả đường đi của một HTTP request từ client qua gateway đến backend và quay lại như thế nào?
Bạn sẽ phân chia trách nhiệm giữa API Gateway, backend và client theo nguyên tắc nào để tránh trùng lặp logic nghiệp vụ?
Bạn sẽ lựa chọn điểm triển khai gateway phù hợp giữa vùng biên mạng, mạng nội bộ và cụm dịch vụ dựa trên yêu cầu nào?
Bạn sẽ so sánh mô hình một gateway dùng chung và nhiều gateway theo miền nghiệp vụ về quản trị và mức cô lập sự cố như thế nào?
Bạn sẽ phân biệt API Gateway và Backend for Frontend khi phục vụ web, mobile và đối tác bên ngoài ra sao?
Bạn sẽ đánh giá lợi ích và rủi ro của việc tập trung chính sách truy cập tại một gateway như thế nào?
Những tiêu chí nào giúp bạn quyết định xử lý nào thuộc backend và xử lý nào thuộc gateway để giữ ranh giới trách nhiệm rõ ràng?
Bạn sẽ thiết kế sơ đồ luồng request với các bước định tuyến, xác thực, giới hạn lưu lượng và gọi backend như thế nào?
Bạn sẽ xác định các mục tiêu độ trễ, thông lượng và khả năng sẵn sàng cho gateway dựa trên yêu cầu dịch vụ ra sao?
Bạn sẽ thiết kế quy tắc định tuyến dựa trên HTTP method và URL path cho nhiều backend như thế nào?
Bạn sẽ xử lý trường hợp hai quy tắc route cùng khớp một request để tránh chuyển sai backend như thế nào?
Bạn sẽ xây dựng quy tắc định tuyến có xét host, header và query parameter trong trường hợp nào?
Bạn sẽ dùng tiền tố đường dẫn để tách các API theo miền nghiệp vụ và thực hiện path rewriting như thế nào?
Bạn sẽ kiểm tra một phép đổi đường dẫn ở gateway có làm sai route, tham số hoặc encoding tại backend ra sao?
Bạn sẽ bảo toàn query string, path parameter và HTTP method khi gateway chuyển tiếp request như thế nào?
Bạn sẽ lựa chọn chính sách giữ nguyên hoặc thay đổi Host header khi backend yêu cầu virtual host khác nhau ra sao?
Bạn sẽ quản lý các header như X-Forwarded-For, Forwarded và X-Request-ID để truyền đúng thông tin request như thế nào?
Bạn sẽ xác định ranh giới tin cậy của các forwarded headers để tránh client giả mạo địa chỉ IP như thế nào?
Bạn sẽ cấu hình chuyển tiếp HTTPS và HTTP/2 từ client đến gateway hoặc backend theo các điều kiện nào?
Bạn sẽ quyết định nơi kết thúc TLS và nơi mã hóa lại kết nối trong hệ thống dựa trên yêu cầu bảo mật như thế nào?
Bạn sẽ thiết kế redirect và xử lý URL công khai khi gateway đứng sau một reverse proxy khác ra sao?
Bạn sẽ kiểm thử các route khi backend có đường dẫn chứa dấu cách, ký tự Unicode hoặc mã hóa phần trăm như thế nào?
Bạn sẽ tổ chức route cho API phiên bản v1 và v2 để hỗ trợ chuyển đổi dần cho các client cũ như thế nào?
Bạn sẽ lựa chọn cách định tuyến theo path, hostname hoặc header cho nhiều phiên bản API dựa trên tiêu chí nào?
Bạn sẽ xử lý route không tồn tại và quyết định nội dung phản hồi HTTP 404 ở gateway như thế nào?
Bạn sẽ thiết kế quy tắc route để tránh vô tình công khai endpoint quản trị hoặc endpoint chỉ dành cho mạng nội bộ ra sao?
Bạn sẽ dùng service discovery hoặc cấu hình tĩnh để tìm địa chỉ backend dựa trên đặc điểm thay đổi của hệ thống như thế nào?
Bạn sẽ thực hiện thay đổi route trong môi trường đang có lưu lượng mà không gây gián đoạn như thế nào?
Bạn sẽ thiết kế quy trình kiểm tra cấu hình route và phát hiện xung đột trước khi triển khai như thế nào?
Bạn sẽ xác định những header request hoặc response nào cần được thêm, xóa hay chuẩn hóa tại gateway dựa trên hợp đồng API ra sao?
Bạn sẽ đánh giá khi nào nên biến đổi request body tại gateway và chi phí xử lý phát sinh ra sao?
Bạn sẽ đảm bảo Content-Type, Content-Length và transfer encoding nhất quán khi gateway chuyển tiếp request body như thế nào?
Bạn sẽ xử lý response compression và các header cache để tránh trả nội dung sai cho client ra sao?
Bạn sẽ thiết kế chính sách CORS tại gateway cho nhiều frontend origin mà vẫn giới hạn quyền truy cập như thế nào?
Bạn sẽ phân biệt CORS preflight với việc kiểm tra quyền ở backend để xử lý yêu cầu OPTIONS ra sao?
Bạn sẽ bảo vệ thông tin nhạy cảm trong header, query string và body khi gateway ghi log hoặc biến đổi request như thế nào?
Bạn sẽ thiết kế ánh xạ mã lỗi từ backend ra response bên ngoài mà vẫn giữ được ý nghĩa và khả năng gỡ lỗi như thế nào?
Bạn sẽ quyết định lúc nào gateway được phép chuẩn hóa response và lúc nào nên giữ nguyên hợp đồng API của backend ra sao?
Bạn sẽ hạn chế ảnh hưởng đến độ trễ khi thực hiện nhiều bước biến đổi request và response trên đường đi như thế nào?
Bạn sẽ phân biệt authentication và authorization tại gateway bằng một yêu cầu truy cập tài nguyên cụ thể như thế nào?
Bạn sẽ lựa chọn cơ chế xác thực API key, JWT, session cookie hoặc mutual TLS theo đối tượng client ra sao?
Bạn sẽ kiểm tra chữ ký, issuer, audience và thời hạn của JWT trước khi chuyển tiếp request như thế nào?
Bạn sẽ xử lý token hết hạn, token chưa có hiệu lực hoặc token có thuật toán không được phép như thế nào?
Bạn sẽ thiết kế tích hợp với nhà cung cấp OAuth 2.0 hoặc OpenID Connect để xác minh danh tính client ra sao?
Bạn sẽ xác định những kiểm tra quyền nào có thể thực hiện ở gateway và những kiểm tra quyền nào phải do backend quyết định?
Bạn sẽ truyền identity và claims đã xác thực đến backend mà không cho client tự giả mạo các header tin cậy như thế nào?
Bạn sẽ chọn chính sách từ chối mặc định và cấp quyền theo scope hoặc role ở gateway như thế nào?
Bạn sẽ bảo vệ endpoint public khác với endpoint dành cho nội bộ hoặc đối tác theo các chính sách nào?
Bạn sẽ thiết kế quản lý vòng đời API key bao gồm cấp phát, giới hạn quyền, thu hồi và luân chuyển như thế nào?
Bạn sẽ xác định rủi ro của việc để gateway gửi token gốc của người dùng sang mọi backend như thế nào?
Bạn sẽ triển khai xác thực giữa gateway và backend để ngăn truy cập trực tiếp bỏ qua gateway ra sao?
Bạn sẽ kiểm soát quyền truy cập trong trường hợp backend được gọi cả qua gateway lẫn từ dịch vụ nội bộ như thế nào?
Bạn sẽ cấu hình giới hạn kích thước request, header và body để giảm nguy cơ quá tải hoặc tấn công như thế nào?
Bạn sẽ giải thích vai trò của WAF và các biện pháp lọc request tại gateway trong bảo vệ hệ thống như thế nào?
Bạn sẽ thiết kế cách phát hiện và xử lý header không hợp lệ, request smuggling hoặc đường dẫn bất thường ra sao?
Bạn sẽ triển khai chính sách TLS certificate và xoay vòng chứng chỉ ở gateway để tránh hết hạn như thế nào?
Bạn sẽ quản lý bí mật xác thực và cấu hình nhạy cảm của gateway qua nhiều môi trường như thế nào?
Bạn sẽ xác định dấu hiệu nào để phân biệt truy cập không được xác thực với truy cập không đủ quyền khi trả HTTP 401 hoặc 403?
Bạn sẽ giải thích sự khác nhau giữa rate limiting, throttling và quota trong quản lý lưu lượng API như thế nào?
Bạn sẽ chọn đơn vị giới hạn theo IP, API key, tài khoản hoặc tenant dựa trên rủi ro và mô hình kinh doanh ra sao?
Bạn sẽ xây dựng chính sách rate limit riêng cho endpoint đọc dữ liệu và endpoint ghi tốn tài nguyên như thế nào?
Bạn sẽ so sánh fixed window, sliding window và token bucket về độ chính xác, chi phí và hành vi khi lưu lượng tăng đột biến như thế nào?
Bạn sẽ thiết kế chính sách token bucket để vừa cho phép burst ngắn vừa duy trì tốc độ truy cập trung bình ra sao?
Bạn sẽ tránh hiện tượng nhiều request cùng vượt giới hạn tại ranh giới cửa sổ thời gian như thế nào?
Bạn sẽ duy trì bộ đếm rate limit nhất quán khi gateway chạy nhiều instance như thế nào?
Bạn sẽ phân tích đánh đổi giữa rate limit cục bộ và rate limit phân tán khi bộ lưu trạng thái gặp sự cố ra sao?
Bạn sẽ trả mã HTTP 429 và thông tin Retry-After cho client bị giới hạn lưu lượng như thế nào?
Bạn sẽ thiết kế chính sách quota theo ngày hoặc tháng mà vẫn xử lý đúng trường hợp reset và thay đổi gói dịch vụ ra sao?
Bạn sẽ phân biệt chính sách bảo vệ tài nguyên backend và chính sách bảo đảm công bằng giữa các tenant như thế nào?
Bạn sẽ giảm nguy cơ một client độc chiếm kết nối hoặc tài nguyên xử lý của gateway bằng những giới hạn nào?
Bạn sẽ kết hợp giới hạn concurrency và rate limit để bảo vệ backend có thời gian xử lý dài ra sao?
Bạn sẽ kiểm thử chính sách rate limiting với các kịch bản burst, nhiều client và nhiều instance gateway như thế nào?
Bạn sẽ quyết định cách xử lý khi hệ thống lưu trạng thái rate limiting không khả dụng mà vẫn cân bằng an toàn và tính sẵn sàng ra sao?
Bạn sẽ chọn thuật toán round robin, least connections hoặc weighted load balancing cho nhóm backend dựa trên tải thực tế như thế nào?
Bạn sẽ cấu hình health check để tránh gửi request đến backend không còn phục vụ được như thế nào?
Bạn sẽ phân biệt liveness và readiness khi quyết định backend nào đủ điều kiện nhận lưu lượng ra sao?
Bạn sẽ điều chỉnh timeout và ngưỡng health check để tránh loại bỏ backend chỉ vì chậm tạm thời như thế nào?
Bạn sẽ thiết kế load balancing theo khả năng xử lý khác nhau của các backend như thế nào?
Bạn sẽ xử lý tình huống một backend liên tục trở lại và rời khỏi nhóm endpoint khỏe mạnh ra sao?
Bạn sẽ phân tích ảnh hưởng của session affinity đến phân phối tải, khả năng mở rộng và phục hồi lỗi như thế nào?
Bạn sẽ chọn cách xử lý kết nối dài, WebSocket hoặc HTTP streaming khi gateway cần định tuyến và cân bằng tải ra sao?
Bạn sẽ kiểm tra tác động của connection pooling và keep-alive giữa gateway với backend lên độ trễ như thế nào?
Bạn sẽ điều chỉnh giới hạn kết nối đồng thời đến từng backend để tránh quá tải như thế nào?
Bạn sẽ thiết kế gateway có nhiều instance và tránh điểm lỗi đơn trong chính gateway như thế nào?
Bạn sẽ đánh giá ảnh hưởng của service discovery cập nhật chậm đến định tuyến khi backend được triển khai liên tục ra sao?
Bạn sẽ giải thích sự khác nhau giữa timeout kết nối, timeout chờ phản hồi và timeout tổng request như thế nào?
Bạn sẽ xây dựng timeout budget xuyên qua gateway và backend để tránh yêu cầu kéo dài vượt SLA ra sao?
Bạn sẽ xác định trường hợp nào nên retry request khi gặp lỗi mạng hoặc HTTP 5xx mà không tạo tác dụng phụ ngoài ý muốn?
Bạn sẽ thiết kế retry policy dựa trên HTTP method, tính idempotent và giới hạn số lần thử như thế nào?
Bạn sẽ phối hợp retry với backoff và jitter để tránh tạo thêm tải lên backend đang gặp sự cố ra sao?
Bạn sẽ phân biệt lỗi trả từ backend, lỗi kết nối đến backend và lỗi phát sinh tại gateway trong phản hồi cho client ra sao?
Bạn sẽ lựa chọn cách sử dụng circuit breaker nhằm ngăn lỗi lan rộng từ một backend không ổn định như thế nào?
Bạn sẽ giải thích trạng thái open, half-open và closed của circuit breaker qua một tình huống lỗi thực tế như thế nào?
Bạn sẽ thiết kế fallback response mà vẫn tránh che giấu lỗi nghiệp vụ hoặc trả dữ liệu sai như thế nào?
Bạn sẽ giới hạn hàng đợi và áp dụng load shedding khi tổng số request vượt năng lực phục vụ ra sao?
Bạn sẽ phát hiện retry storm và đưa ra cơ chế giảm số lần gọi lại khi nhiều client cùng retry như thế nào?
Bạn sẽ định nghĩa hành vi của gateway khi backend chậm, không phản hồi hoặc trả lỗi từng phần như thế nào?
Bạn sẽ lựa chọn cách xử lý khi một request đã gửi đến backend nhưng gateway bị timeout trước khi nhận kết quả ra sao?
Bạn sẽ thiết kế chiến lược bảo vệ luồng ghi quan trọng khi gateway bị restart hoặc client mất kết nối như thế nào?
Bạn sẽ tổ chức cấu hình canary routing để chỉ một phần lưu lượng được chuyển sang backend phiên bản mới như thế nào?
Bạn sẽ phân biệt canary deployment và blue-green deployment khi thực hiện thay đổi route qua gateway ra sao?
Bạn sẽ thiết kế rollback nhanh các thay đổi chính sách gateway sau khi tỷ lệ lỗi tăng như thế nào?
Bạn sẽ sử dụng correlation ID và distributed tracing để theo dấu một request xuyên qua gateway và nhiều backend ra sao?
Bạn sẽ theo dõi latency của gateway và backend riêng biệt để xác định nơi phát sinh độ trễ như thế nào?
Bạn sẽ lựa chọn các metric request rate, error rate, latency percentile và saturation để đánh giá gateway ra sao?
Bạn sẽ xây dựng dashboard phân tách mã HTTP 4xx, 5xx và lỗi kết nối theo route hoặc upstream như thế nào?
Bạn sẽ đánh giá vì sao độ trễ trung bình thấp nhưng p95 hoặc p99 của gateway tăng cao như thế nào?
Bạn sẽ giới hạn số lượng nhãn metric để tránh cardinality quá cao khi theo dõi từng route và client như thế nào?
Bạn sẽ thiết kế access log đủ thông tin gỡ lỗi nhưng không làm lộ token, dữ liệu cá nhân hoặc nội dung nhạy cảm ra sao?
Bạn sẽ thiết lập sampling cho distributed tracing để vừa kiểm soát chi phí vừa giữ được dấu vết của request lỗi như thế nào?
Bạn sẽ phân biệt các chỉ số lỗi do gateway trả và lỗi thực sự xảy ra tại backend để tránh cảnh báo sai như thế nào?
Bạn sẽ xác định ngưỡng cảnh báo cho tỷ lệ HTTP 5xx, timeout và latency dựa trên SLO của API ra sao?
Bạn sẽ thiết kế thử nghiệm tải để xác định điểm nghẽn CPU, kết nối, TLS hoặc network I/O trên gateway như thế nào?
Bạn sẽ dự đoán nhu cầu mở rộng số instance gateway theo lưu lượng đỉnh và giới hạn tài nguyên như thế nào?
Bạn sẽ quản lý cấu hình route, authentication và rate limit dưới dạng phiên bản để có thể review và rollback như thế nào?
Bạn sẽ xây dựng quy trình kiểm tra tự động để phát hiện route mâu thuẫn và chính sách thiếu xác thực trước khi triển khai ra sao?
Bạn sẽ tổ chức thay đổi cấu hình gateway giữa dev, staging và production mà vẫn giữ các chính sách cốt lõi như thế nào?
Bạn sẽ phân quyền nhóm vận hành và nhóm phát triển khi mỗi bên cần thay đổi các loại chính sách gateway khác nhau ra sao?
Bạn sẽ xây dựng tài liệu hợp đồng API và thông báo thay đổi route hoặc rate limit cho client như thế nào?
Bạn sẽ theo dõi khả năng tương thích của gateway với HTTP clients khi nâng cấp phiên bản hoặc thay đổi cấu hình TLS ra sao?
Nếu một route mới vô tình chuyển request có chứa thông tin nhạy cảm đến sai backend, bạn sẽ điều tra và ngăn tái diễn như thế nào?
Nếu một API trả HTTP 503 trong khi các backend vẫn báo healthy, bạn sẽ kiểm tra những lớp nào để tìm nguyên nhân?
Nếu lưu lượng tăng đột biến khiến gateway trả HTTP 429 cho khách hàng quan trọng, bạn sẽ đánh giá lại chính sách giới hạn như thế nào?
Nếu mọi request qua gateway chậm hơn nhiều so với gọi trực tiếp backend, bạn sẽ thiết lập trình tự chẩn đoán như thế nào?
Nếu backend xử lý thành công lệnh thanh toán nhưng gateway timeout và client retry, bạn sẽ thiết kế cơ chế ngăn thanh toán trùng ra sao?
Nếu một tenant làm quá tải endpoint dùng chung, bạn sẽ phân chia quota, giới hạn concurrency và bảo vệ các tenant khác như thế nào?
Bạn sẽ đề xuất thiết kế API Gateway cho nền tảng thương mại điện tử có web, mobile và đối tác, với yêu cầu xác thực, rate limiting, khả năng mở rộng và quan sát lỗi như thế nào?
