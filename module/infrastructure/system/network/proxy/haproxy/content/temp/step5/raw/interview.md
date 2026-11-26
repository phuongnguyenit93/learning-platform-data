HAProxy giải quyết những nhu cầu nào khi được đặt trước nhiều máy chủ ứng dụng trong hệ thống có lưu lượng cao?
Bạn phân biệt forward proxy, reverse proxy và bộ cân bằng tải dựa trên hướng kết nối và trách nhiệm của từng thành phần như thế nào?
Bạn mô tả đường đi của một yêu cầu từ client qua HAProxy đến backend rồi quay lại như thế nào?
HAProxy xử lý kết nối ở chế độ TCP và chế độ HTTP khác nhau về thông tin có thể kiểm tra và thao tác như thế nào?
Bạn chọn chế độ TCP thay vì HTTP trong những trường hợp triển khai nào?
Bạn giải thích vai trò của các phần global, defaults, frontend, backend và listen trong tệp cấu hình HAProxy như thế nào?
Bạn tổ chức nhiều frontend và backend để phục vụ nhiều tên miền hoặc dịch vụ bằng một cụm HAProxy ra sao?
Những tiêu chí nào giúp bạn quyết định đặt cấu hình trong defaults hay ghi riêng tại frontend hoặc backend?
Bạn cấu hình bind trên địa chỉ IP, cổng và giao thức phù hợp với mô hình mạng triển khai ra sao?
Bạn kiểm tra một cấu hình HAProxy trước khi đưa vào vận hành để phát hiện lỗi cú pháp và tham chiếu backend không hợp lệ như thế nào?
Bạn diễn giải thứ tự và phạm vi tác động của các quy tắc trong frontend khi một request đi qua HAProxy ra sao?
ACL trong HAProxy dùng những loại dữ liệu đầu vào và toán tử so khớp nào để đưa ra quyết định định tuyến?
Bạn thiết kế ACL để định tuyến theo Host header, path, phương thức HTTP hoặc một header nghiệp vụ như thế nào?
Bạn lựa chọn use_backend và default_backend khi nhiều điều kiện định tuyến có thể cùng đúng như thế nào?
Bạn kiểm soát thứ tự các quy tắc ACL và use_backend để tránh request bị chuyển tới nhầm dịch vụ ra sao?
Bạn xây dựng quy tắc tách lưu lượng theo phiên bản API hoặc tenant mà vẫn giữ cấu hình dễ đọc và kiểm thử như thế nào?
Bạn dùng map file để quản lý nhiều cặp hostname hoặc đường dẫn và backend thay vì viết quá nhiều ACL như thế nào?
Bạn xử lý tình huống Host header hoặc path được chuẩn hóa khác kỳ vọng khiến ACL không khớp như thế nào?
Bạn xác minh một frontend đang hoạt động nhưng request trả mã lỗi vì không có backend hợp lệ bằng những kiểm tra nào?
Bạn phân biệt chặn request tại HAProxy với trả lỗi từ ứng dụng backend thông qua log và response như thế nào?
Bạn dùng các quy tắc thay đổi URI hoặc header để chuyển tiếp đúng hợp đồng HTTP mà backend mong đợi ra sao?
Bạn thiết lập thông tin X-Forwarded-For hoặc Forwarded để ứng dụng biết địa chỉ client thật mà tránh tin header giả mạo như thế nào?
Bạn lựa chọn dùng PROXY protocol để chuyển thông tin kết nối tới backend TCP khi nào và kiểm tra tính tương thích ra sao?
Bạn xác định có nên giữ nguyên Host header hay thay thế bằng tên backend dựa trên yêu cầu định tuyến nào?
Bạn thiết kế quy tắc redirect HTTP sang HTTPS sao cho không tạo vòng lặp khi HAProxy nằm sau một proxy khác như thế nào?
Bạn đánh giá những tác động của rewrite và redirect đến SEO, cache và hành vi client API ra sao?
Bạn so sánh thuật toán roundrobin, leastconn và source hashing dựa trên đặc điểm thời gian xử lý request và phân bố tải như thế nào?
Bạn chọn thuật toán cân bằng tải cho hệ thống có nhiều kết nối dài thay vì nhiều request ngắn như thế nào?
Bạn sử dụng trọng số của server để phân chia lưu lượng khi các backend có năng lực xử lý không đồng đều ra sao?
Bạn điều chỉnh trọng số và trạng thái của backend để triển khai canary hoặc chuyển dần lưu lượng như thế nào?
Bạn đánh giá tác động của việc thêm hoặc bớt backend lên phân phối request và tính ổn định của phiên làm việc ra sao?
Khi nhiều backend đều khỏe nhưng một backend liên tục quá tải, bạn thu thập những bằng chứng nào trước khi chỉnh thuật toán?
Keep-alive và connection reuse ảnh hưởng thế nào đến việc phân phối kết nối và request HTTP giữa các backend?
Bạn xác định giới hạn số kết nối tới từng backend để không tạo quá nhiều request chờ xử lý như thế nào?
Bạn sử dụng server backup hoặc các nhóm backend dự phòng để xử lý khi backend chính ngừng hoạt động ra sao?
Bạn thiết lập slowstart hoặc cơ chế tăng dần lưu lượng cho backend vừa phục hồi nhằm tránh quá tải đột ngột như thế nào?
Bạn phân biệt tình huống cần session persistence với tình huống ứng dụng có thể vận hành stateless như thế nào?
Bạn sử dụng cookie persistence để giữ một phiên HTTP trên backend đã chọn như thế nào?
Bạn đánh giá rủi ro của source-based persistence khi nhiều người dùng cùng đi qua NAT hoặc proxy như thế nào?
Bạn chọn stick-table và khóa định danh phù hợp để duy trì phiên hoặc theo dõi hoạt động client như thế nào?
Bạn giải quyết tình huống backend chứa trạng thái phiên bị loại khỏi pool nhưng client vẫn gửi cookie cũ ra sao?
Bạn kiểm tra liệu session persistence có làm phân phối tải mất cân bằng và tạo điểm nóng hay không bằng cách nào?
Health check chủ động giúp HAProxy quyết định một server có sẵn sàng nhận lưu lượng như thế nào?
Bạn chọn health check TCP hay HTTP dựa trên mức độ kiểm chứng sức khỏe ứng dụng mong muốn ra sao?
Bạn thiết kế endpoint health check để phản ánh khả năng xử lý thực tế nhưng không tạo tải không cần thiết như thế nào?
Bạn cấu hình kỳ kiểm tra, ngưỡng lỗi và ngưỡng phục hồi để cân bằng phát hiện nhanh với nguy cơ dao động trạng thái ra sao?
Bạn phân biệt health check chủ động và theo dõi lỗi từ lưu lượng thực khi đánh giá tình trạng một backend như thế nào?
Bạn điều tra tình huống health check báo khỏe nhưng request thực tế vẫn trả lỗi 5xx như thế nào?
Bạn phân biệt lỗi DNS, lỗi kết nối TCP, lỗi TLS handshake, lỗi timeout và lỗi HTTP status khi health check thất bại ra sao?
Bạn sử dụng resolver hoặc cơ chế cập nhật địa chỉ server khi backend có IP thay đổi thường xuyên như thế nào?
Bạn kiểm tra rủi ro DNS cache hoặc thay đổi DNS chậm làm lưu lượng tiếp tục đến địa chỉ cũ ra sao?
Bạn thực hiện kiểm thử failover để xác định thời gian loại backend lỗi và thời gian đưa backend phục hồi trở lại pool như thế nào?
Bạn quyết định điểm kết thúc TLS tại HAProxy hay tại backend dựa trên yêu cầu bảo mật và quan sát lưu lượng nào?
Bạn triển khai nhiều chứng chỉ cho nhiều tên miền trên cùng listener TLS bằng SNI như thế nào?
Bạn xây dựng quy trình gia hạn và thay chứng chỉ TLS để không làm gián đoạn kết nối mới ra sao?
Bạn lựa chọn phiên bản TLS và bộ thuật toán mã hóa nhằm cân bằng tương thích client với yêu cầu bảo mật như thế nào?
Bạn xác minh chứng chỉ của backend khi HAProxy dùng HTTPS tới upstream bằng những tiêu chí nào?
Bạn xác định khi nào nên sử dụng mTLS giữa các thành phần và cách kiểm tra danh tính hai đầu kết nối ra sao?
Bạn đánh giá chi phí CPU do TLS handshake và ảnh hưởng của connection reuse đến thông lượng như thế nào?
Bạn phân biệt xử lý HTTP/1.1, HTTP/2 và các kết nối TCP thuần trong HAProxy khi thiết kế frontend như thế nào?
Bạn chọn timeout connect, timeout client và timeout server theo SLA và hành vi truy vấn backend như thế nào?
Bạn phân biệt lỗi timeout khi chờ kết nối tới backend với lỗi timeout trong lúc chờ response như thế nào?
Bạn điều chỉnh timeout cho WebSocket hoặc kết nối lâu dài sao cho không ngắt phiên hoạt động hợp lệ ra sao?
Bạn kiểm soát số kết nối tối đa tại HAProxy và ở từng backend theo khả năng tài nguyên như thế nào?
Bạn phân tích hiện tượng request bị xếp hàng khi backend hết chỗ và các dấu hiệu cho thấy hàng đợi kéo dài như thế nào?
Bạn đặt giới hạn thời gian chờ hàng đợi để ứng dụng từ chối sớm khi không còn khả năng phục vụ ra sao?
Bạn chọn các cấu hình retry và redispatch khi backend lỗi nhằm tăng tính sẵn sàng mà tránh lặp tác dụng phụ ra sao?
Bạn phân biệt retry an toàn cho yêu cầu idempotent và rủi ro khi retry POST đã được backend xử lý một phần như thế nào?
Bạn phát hiện retry storm khi nhiều client và HAProxy đồng thời thử lại trong lúc backend quá tải như thế nào?
Bạn xác định khi nào cần giới hạn tốc độ request theo địa chỉ client hoặc mã định danh nghiệp vụ ra sao?
Bạn xây dựng stick-table để theo dõi tần suất request hoặc số kết nối và áp dụng ACL giới hạn lưu lượng như thế nào?
Bạn cân nhắc nguy cơ giới hạn theo IP làm ảnh hưởng nhiều client dùng chung NAT và đề xuất khóa phù hợp ra sao?
Bạn xử lý các trường hợp burst hợp lệ, client lỗi và lưu lượng bất thường khi thiết kế chính sách rate limit như thế nào?
Bạn phối hợp giới hạn request tại HAProxy với giới hạn tài nguyên ở backend như thế nào để tránh quá tải dây chuyền?
Bạn triển khai chính sách từ chối sớm khi backend quá tải mà vẫn trả response HTTP có ý nghĩa cho client ra sao?
Bạn kiểm soát các header đầu vào, kích thước request và hành vi bất thường để giảm nguy cơ lạm dụng proxy như thế nào?
Bạn cấu hình log HTTP và log TCP để có đủ dữ liệu chẩn đoán mà không làm lộ cookie hoặc thông tin xác thực ra sao?
Bạn giải thích ý nghĩa của thời gian xếp hàng, thời gian kết nối backend, thời gian nhận response và tổng thời gian request trong log HAProxy như thế nào?
Bạn phân biệt mã trạng thái HTTP do HAProxy tạo với mã do backend trả về trong log như thế nào?
Bạn sử dụng termination state và thông tin retry trong log để suy ra kết nối bị kết thúc ở giai đoạn nào ra sao?
Bạn thiết kế log format hoặc log JSON để liên kết request ID giữa proxy và ứng dụng backend như thế nào?
Bạn lựa chọn những metric nào về request rate, active connections, backend queue, response codes và health check cho dashboard?
Bạn sử dụng statistics page, Runtime API hoặc metrics exporter để quan sát và điều chỉnh trạng thái backend như thế nào?
Bạn xác định các dấu hiệu nào cho thấy lỗi 502, 503 hoặc 504 xuất phát từ HAProxy thay vì từ ứng dụng?
Khi một API tăng p99 latency nhưng tỷ lệ lỗi thấp, bạn điều tra từ hàng đợi, TLS, kết nối và backend theo thứ tự nào?
Bạn phân biệt HAProxy hết tài nguyên CPU, RAM hoặc file descriptor với backend bị nghẽn bằng những phép đo nào?
Bạn tính toán năng lực xử lý tổng thể khi có nhiều HAProxy instance cùng phân phối tải tới một nhóm backend như thế nào?
Bạn tổ chức nhiều HAProxy instance trước backend để giảm điểm lỗi đơn và bảo đảm khả năng chuyển đổi khi proxy chết ra sao?
Bạn kết hợp health check của bộ cân bằng tải phía trước hoặc cơ chế IP ảo với HAProxy để xử lý failover như thế nào?
Bạn cân nhắc khi nào cần đồng bộ trạng thái stick-table giữa các HAProxy instance và rủi ro nếu trạng thái bị lệch ra sao?
Bạn triển khai thay đổi cấu hình hoặc reload HAProxy sao cho hạn chế gián đoạn các kết nối đang xử lý như thế nào?
Bạn kiểm tra cấu hình mới, chứng chỉ và kết quả định tuyến trước khi reload HAProxy ở production như thế nào?
Bạn xác định các bước rollback khi cấu hình ACL mới làm request chuyển sai backend ra sao?
Bạn kiểm soát phân quyền file cấu hình, chứng chỉ và Runtime API để tránh thay đổi proxy trái phép như thế nào?
Bạn quản lý cấu hình HAProxy qua Git và pipeline triển khai với các kiểm tra tự động theo cách nào?
Bạn thiết kế thử nghiệm tải để đo thông lượng TCP, request HTTP, p95/p99 latency và mức tiêu thụ tài nguyên của HAProxy ra sao?
Bạn kiểm tra tình huống backend chập chờn, tăng độ trễ hoặc mất kết nối hoàn toàn để xác nhận hành vi proxy như thế nào?
Bạn trình bày một phương án cải thiện tính sẵn sàng sau sự cố dựa trên log, metric, kết quả health check và kết quả kiểm thử ra sao?
