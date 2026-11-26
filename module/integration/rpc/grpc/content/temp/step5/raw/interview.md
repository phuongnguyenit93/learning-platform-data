Trong những tình huống nào bạn sẽ chọn gRPC thay cho REST/JSON khi thiết kế giao tiếp giữa các dịch vụ?
Những đánh đổi chính về hiệu năng, khả năng quan sát và khả năng tương thích khi áp dụng gRPC là gì?
Vì sao cách tiếp cận contract-first có ý nghĩa đối với các nhóm cùng phát triển một hệ thống gRPC?
HTTP/2 multiplexing ảnh hưởng thế nào đến việc thực hiện đồng thời nhiều lời gọi RPC trên một kết nối?
Headers, data frames và trailers của HTTP/2 tham gia vào vòng đời một lời gọi gRPC như thế nào?
Kết nối HTTP/2 lâu dài có những lợi ích và rủi ro gì trong môi trường microservices?
Protocol Buffers giúp giảm chi phí truyền tải và tuần tự hóa so với JSON trong những điều kiện nào?
Những hạn chế nào của định dạng nhị phân Protocol Buffers cần được cân nhắc khi gỡ lỗi hệ thống?
Bạn sẽ phân tích những thành phần nào khi độ trễ của một lời gọi gRPC cao bất thường?
Khi nào yêu cầu nghiệp vụ phù hợp với RPC đồng bộ và khi nào nên cân nhắc giao tiếp bất đồng bộ qua hàng đợi?
Bạn sẽ tổ chức các file .proto như thế nào để nhiều dịch vụ có thể chia sẻ hợp đồng mà vẫn quản lý được phiên bản?
Các khai báo package, java_package và java_outer_classname trong .proto ảnh hưởng thế nào đến mã Java được sinh ra?
Tùy chọn java_multiple_files thay đổi cách tổ chức các lớp Java được sinh từ .proto như thế nào?
Vì sao số hiệu field trong Protocol Buffers cần được quản lý ổn định qua các phiên bản?
Bạn sẽ bổ sung một field mới vào message đang được nhiều phiên bản client sử dụng như thế nào?
Khi xóa một field khỏi message, bạn sẽ dùng reserved để phòng tránh rủi ro gì?
Bạn phân biệt field không được gửi với field có giá trị mặc định trong proto3 bằng cách nào?
Trong tình huống nào oneof là lựa chọn phù hợp để biểu diễn nhiều dạng dữ liệu loại trừ nhau?
Bạn xử lý thế nào khi client cũ nhận một giá trị enum mới từ server?
Bạn sẽ quyết định dùng repeated field hay map field dựa trên yêu cầu truy cập dữ liệu nào?
Khi nào nên sử dụng các kiểu Timestamp và Duration chuẩn thay vì tự khai báo chuỗi thời gian?
Bạn sẽ thiết kế message lồng nhau ra sao để tránh hợp đồng khó tái sử dụng hoặc khó tiến hóa?
Một khai báo service và rpc trong .proto xác định những phần nào của hợp đồng giữa client và server?
Bạn so sánh cách lựa chọn unary, server streaming, client streaming và bidirectional streaming cho các bài toán thực tế như thế nào?
Bạn sẽ đặt tên và phân chia các RPC method như thế nào để phản ánh rõ ranh giới nghiệp vụ?
Bạn sẽ quản lý version của API gRPC như thế nào khi phải hỗ trợ nhiều thế hệ client?
Các nguyên tắc nào giúp một hợp đồng .proto có thể tương tác ổn định giữa Java và các ngôn ngữ khác?
Bạn sẽ kiểm tra tính hợp lệ của dữ liệu đầu vào ở ranh giới gRPC như thế nào khi schema chưa biểu diễn đủ quy tắc nghiệp vụ?
Bạn ánh xạ message Protocol Buffers sang mô hình domain của Java như thế nào để tránh phụ thuộc lan rộng?
Những thay đổi schema nào giữ được khả năng tương thích wire format nhưng vẫn có thể làm thay đổi ý nghĩa nghiệp vụ?
Bạn xác định và xử lý một thay đổi phá vỡ tương thích của .proto trước khi triển khai như thế nào?
Bạn sẽ cấu hình quy trình sinh mã Java từ .proto trong Maven hoặc Gradle để bảo đảm build có thể lặp lại như thế nào?
Những loại mã sinh ra từ khai báo message và service hỗ trợ việc xây dựng gRPC client và server ra sao?
Bạn chọn blocking stub, async stub hoặc future stub trong gRPC Java dựa trên đặc điểm lời gọi nào?
Bạn triển khai phần xử lý một RPC method trong server Java như thế nào để tách vận chuyển khỏi nghiệp vụ?
Bạn sẽ cấu hình ManagedChannel cho client Java như thế nào để kết nối tới đúng đích và sử dụng transport phù hợp?
Vì sao vòng đời của ManagedChannel cần được quản lý thay vì khởi tạo một kết nối mới cho mỗi request?
Bạn sẽ truyền deadline và các tùy chọn theo từng lời gọi thông qua stub hoặc call options như thế nào?
Client interceptor và server interceptor phù hợp với những trách nhiệm xuyên suốt nào?
Bạn thiết kế cơ chế truyền metadata qua nhiều dịch vụ gRPC như thế nào để giữ được ngữ cảnh yêu cầu?
Bạn sẽ chọn executor và cách xử lý bất đồng bộ nào để tránh chặn các luồng thực thi quan trọng của gRPC Java?
Những lưu ý nào về tính an toàn luồng khi nhiều request dùng chung channel, stub hoặc đối tượng xử lý stream?
Bạn mô tả vòng đời của một unary RPC từ lúc client gửi request đến khi nhận response hoặc lỗi như thế nào?
Khi một unary RPC gọi xuống cơ sở dữ liệu và dịch vụ khác, bạn sẽ phân bổ thời gian thực thi như thế nào?
Bạn sẽ trả về lỗi xác thực dữ liệu đầu vào cho client mà không làm lộ chi tiết triển khai nội bộ như thế nào?
Khi số lượng unary call tăng đột biến, bạn xác định giới hạn tài nguyên và điểm nghẽn nào trước tiên?
Bạn sẽ chọn server streaming thay cho nhiều unary call trong một tình huống nào và vì sao?
Bạn thiết kế client streaming như thế nào khi cần gửi nhiều bản ghi rồi nhận một kết quả tổng hợp?
Bạn thiết kế bidirectional streaming như thế nào cho hai phía trao đổi sự kiện liên tục và độc lập?
Thứ tự message trong từng chiều của một stream ảnh hưởng thế nào đến cách xử lý nghiệp vụ?
Half-close trong client streaming hoặc bidirectional streaming có ý nghĩa gì đối với quá trình kết thúc gửi dữ liệu?
Bạn phân biệt vai trò của onNext, onError và onCompleted trong việc quản lý một stream như thế nào?
Bạn sẽ ngăn việc phát nhiều tín hiệu kết thúc hoặc phát message sau khi stream đã đóng bằng cách nào?
Khi nhiều luồng ứng dụng cùng tạo dữ liệu cho một stream, bạn sẽ đồng bộ hoạt động ghi ra sao?
Bạn phát hiện và xử lý stream sống lâu nhưng không còn dữ liệu hữu ích như thế nào?
Sau khi kết nối bidirectional streaming bị gián đoạn, bạn thiết kế cơ chế tái kết nối ở mức ứng dụng như thế nào?
Với dữ liệu lớn, bạn cân nhắc chia thành nhiều message streaming thay vì gửi một unary message lớn dựa trên yếu tố nào?
Bạn sẽ bảo toàn quyền truy cập và ngữ cảnh xác thực trong một stream kéo dài như thế nào?
Bạn thiết kế checkpoint hoặc resume token như thế nào nếu client cần tiếp tục xử lý stream sau khi mất kết nối?
Khi xử lý streaming theo pipeline, bạn sẽ quyết định vị trí thực hiện biến đổi dữ liệu và phát kết quả như thế nào?
Khi producer gửi nhanh hơn consumer, dữ liệu bị đệm ở những tầng nào và rủi ro bộ nhớ là gì?
Bạn sẽ sử dụng cơ chế điều tiết yêu cầu message của gRPC Java như thế nào để kiểm soát tốc độ nhận?
Bạn xác định khi nào một bên của stream đã sẵn sàng nhận thêm dữ liệu bằng cách nào?
Bạn kiểm chứng backpressure hoạt động hiệu quả ra sao trong trường hợp client rất chậm?
Deadline trong gRPC có ý nghĩa gì đối với giới hạn thời gian xử lý một request?
Bạn sẽ lan truyền deadline từ service đầu vào qua các lời gọi gRPC hạ nguồn như thế nào?
Bạn phân biệt deadline tuyệt đối với timeout tương đối ra sao khi thiết kế một chuỗi RPC?
Khi request đi qua nhiều dịch vụ, bạn sẽ phân bổ ngân sách thời gian còn lại như thế nào?
Khi deadline hết hạn trong lúc server vẫn đang tính toán, bạn sẽ xử lý công việc còn dang dở thế nào?
Client hủy lời gọi gRPC thì server nên nhận biết và phản ứng với tín hiệu hủy ra sao?
Bạn sẽ giải phóng các tài nguyên bên ngoài khi một RPC hoặc stream bị hủy như thế nào?
Bạn chọn mã trạng thái gRPC phù hợp dựa trên loại lỗi và khả năng client khắc phục như thế nào?
Bạn phân biệt INVALID_ARGUMENT với FAILED_PRECONDITION trong các lỗi nghiệp vụ như thế nào?
Trong những tình huống nào UNAVAILABLE và DEADLINE_EXCEEDED cần được xử lý khác nhau ở client?
Bạn sẽ chuyển ngoại lệ nội bộ thành trạng thái gRPC như thế nào để tránh lộ thông tin nhạy cảm?
Khi client cần biết nhiều chi tiết lỗi có cấu trúc, bạn sẽ thiết kế hợp đồng báo lỗi như thế nào?
Trailers và metadata hỗ trợ truyền thông tin chẩn đoán lỗi trong gRPC như thế nào?
Bạn thiết kế client Java xử lý trạng thái lỗi ra sao để phân biệt lỗi có thể thử lại với lỗi phải sửa yêu cầu?
Những điều kiện nào cho phép một RPC được thử lại an toàn sau lỗi tạm thời?
Bạn sẽ cấu hình retry policy cho gRPC client như thế nào để phù hợp với đặc tính của từng RPC method?
Tính idempotent của một RPC ảnh hưởng thế nào đến quyết định bật tự động retry?
Bạn sẽ ngăn việc tạo giao dịch trùng lặp khi request đã xử lý thành công nhưng response bị mất như thế nào?
Exponential backoff và jitter giúp hạn chế những hiện tượng nào khi nhiều client cùng retry?
Bạn sẽ giới hạn số lần thử và ngân sách retry như thế nào để tránh làm quá tải hệ thống hạ nguồn?
Per-attempt timeout tương tác với deadline tổng của một RPC như thế nào?
Trong trường hợp nào hedging có thể cải thiện độ trễ và có những chi phí nào cần kiểm soát?
Bạn sẽ phối hợp retry với circuit breaker hoặc cơ chế ngắt tải như thế nào khi một dependency bị lỗi kéo dài?
Bạn nhận diện và ngăn chặn retry storm giữa nhiều tầng microservices bằng những tín hiệu nào?
TLS bảo vệ những phần nào của giao tiếp gRPC và bạn sẽ cấu hình kênh bảo mật ở hai đầu như thế nào?
mTLS khác TLS một chiều ở cơ chế xác thực danh tính các bên như thế nào?
Bạn sẽ quản lý trust store và chuỗi chứng chỉ ra sao khi các dịch vụ thuộc nhiều miền tin cậy?
Bạn sẽ xoay vòng chứng chỉ TLS/mTLS trong hệ thống đang hoạt động như thế nào để giảm gián đoạn kết nối?
Bạn thiết kế xác thực bằng token hoặc call credentials trong gRPC Java như thế nào?
Bạn sẽ phân biệt xác thực danh tính dịch vụ với phân quyền thực hiện từng RPC method như thế nào?
Metadata hoặc access token có thể bị rò rỉ ở những chỗ nào và bạn sẽ giảm thiểu rủi ro ra sao?
Bạn kiểm soát quyền truy cập thế nào khi danh tính hoặc quyền của client thay đổi trong một stream dài hạn?
Bạn sẽ giới hạn kích thước message và tốc độ gọi để bảo vệ server khỏi việc tiêu thụ tài nguyên quá mức như thế nào?
Bạn sẽ đưa chính sách bảo mật vào interceptor hoặc lớp nghiệp vụ theo tiêu chí nào?
Client-side load balancing trong gRPC khác việc cân bằng tải ở proxy hoặc L4 load balancer như thế nào?
Bạn lựa chọn chiến lược pick-first hoặc round-robin dựa trên dạng lưu lượng và topology nào?
DNS hoặc service discovery ảnh hưởng như thế nào đến khả năng client nhìn thấy các instance server mới?
Một proxy không hỗ trợ đầy đủ HTTP/2 hoặc streaming có thể gây những lỗi gì và bạn sẽ chẩn đoán ra sao?
Bạn sẽ kết hợp health checking với cân bằng tải như thế nào để tránh gửi request tới instance chưa sẵn sàng?
Bạn xử lý graceful shutdown của server ra sao để các RPC đang chạy có cơ hội hoàn tất?
Những vấn đề nào phát sinh khi cân bằng tải các bidirectional stream tồn tại rất lâu?
Bạn sẽ thiết kế phương án chuyển vùng hoặc tránh instance lỗi như thế nào khi một cụm gRPC suy giảm?
Bạn chọn các chỉ số nào để theo dõi lưu lượng, lỗi, thời gian đáp ứng và tài nguyên của dịch vụ gRPC?
Bạn phân tích độ trễ p50, p95 và p99 của gRPC như thế nào để phát hiện vấn đề mà giá trị trung bình che khuất?
Bạn sẽ truyền trace context qua các RPC để quan sát một request xuyên nhiều dịch vụ như thế nào?
Bạn liên kết log của client và server trong cùng một lời gọi gRPC bằng thông tin tương quan nào?
Bạn ghi log request và lỗi thế nào để vừa hỗ trợ chẩn đoán vừa hạn chế lộ dữ liệu nhạy cảm?
Bạn sẽ viết kiểm thử đơn vị cho lớp xử lý nghiệp vụ của một gRPC service mà không phụ thuộc mạng như thế nào?
Kiểm thử bằng in-process server và channel giúp xác minh hành vi gRPC Java trong những trường hợp nào?
Bạn sẽ kiểm thử cả bốn kiểu RPC để bảo đảm thứ tự message, tín hiệu kết thúc và trạng thái lỗi như thế nào?
Bạn thiết kế kiểm thử tích hợp giữa hai dịch vụ gRPC thật như thế nào để kiểm tra cả serialization và networking?
Bạn sẽ đưa TLS/mTLS và xác thực client vào kiểm thử tích hợp như thế nào?
Bạn mô phỏng mất kết nối, server chậm và deadline hết hạn như thế nào để kiểm tra khả năng phục hồi?
Bạn sẽ tự động phát hiện thay đổi .proto phá vỡ tương thích trong quy trình CI như thế nào?
Bạn kiểm thử khả năng tương thích giữa client phiên bản cũ và server phiên bản mới như thế nào?
Bạn xây dựng kịch bản kiểm thử tải cho unary và streaming như thế nào để đo throughput, latency và mức dùng bộ nhớ?
Bạn sẽ kiểm tra việc dừng hoặc triển khai lại server có làm mất dữ liệu của các stream đang hoạt động hay không như thế nào?
Khi triển khai phiên bản mới theo từng đợt, bạn sẽ phát hiện và xử lý vấn đề tương thích giao thức như thế nào?
Nếu phải thiết kế giao tiếp thời gian thực giữa dịch vụ đơn hàng và dịch vụ vận chuyển, bạn sẽ chọn kiểu RPC và cơ chế xử lý lỗi nào?
Nếu một dịch vụ thanh toán dùng unary RPC nhưng client thường gặp timeout, bạn sẽ điều tra và bảo đảm không ghi nhận giao dịch hai lần như thế nào?
Nếu một hệ thống dùng bidirectional streaming để trao đổi hàng nghìn sự kiện mỗi giây, bạn sẽ thiết kế backpressure, deadline và khả năng phục hồi ra sao?
