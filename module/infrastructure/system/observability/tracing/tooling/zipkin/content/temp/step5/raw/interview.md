Distributed tracing giải quyết những câu hỏi điều tra nào khi một request đi qua nhiều dịch vụ độc lập?
Bạn phân biệt distributed tracing với logging và metrics dựa trên loại bằng chứng mỗi tín hiệu cung cấp như thế nào?
Bạn mô tả mối quan hệ giữa trace, span và các span con trong một request đi qua gateway, service và database như thế nào?
Bạn giải thích trace ID, span ID và parent span ID giúp tái dựng luồng xử lý phân tán ra sao?
Bạn xác định ranh giới bắt đầu và kết thúc của một span cho HTTP request, database call và tác vụ nền như thế nào?
Bạn lựa chọn tên span để vừa thể hiện thao tác có ý nghĩa vừa tránh tạo quá nhiều tên biến động như thế nào?
Bạn phân biệt span kind CLIENT, SERVER, PRODUCER, CONSUMER và INTERNAL trong mô hình tracing như thế nào?
Bạn diễn giải timestamp, duration, local endpoint và remote endpoint để xác định nơi một thao tác được thực hiện như thế nào?
Bạn phân biệt span annotation với span tag và quyết định loại thông tin nào phù hợp cho từng loại ra sao?
Bạn sử dụng error tag hoặc status của span để phản ánh lỗi kỹ thuật và lỗi nghiệp vụ như thế nào?
Bạn giải thích một trace có thể chứa nhiều nhánh gọi song song và cách xác định quan hệ giữa chúng như thế nào?
Bạn xác định một span chậm có phải nguyên nhân chính làm request chậm hay chỉ là hệ quả của việc chờ downstream như thế nào?
Bạn phân tích critical path trong trace để tìm thành phần quyết định thời gian phản hồi tổng thể ra sao?
Bạn dùng timeline để phân biệt thời gian span thực thi với khoảng chờ giữa các span trong cùng trace như thế nào?
Bạn nhận diện trace không đầy đủ do thiếu instrumentation, mất context hoặc sampling bằng những dấu hiệu nào?
Bạn giải thích kiến trúc tổng thể của Zipkin từ nơi instrument ứng dụng tới collector, storage, query API và giao diện như thế nào?
Bạn phân biệt Zipkin reporter hoặc exporter với Zipkin server về trách nhiệm gửi và tiếp nhận span như thế nào?
Bạn mô tả luồng một span được tạo trong ứng dụng, mã hóa và gửi tới Zipkin collector theo những bước nào?
Bạn lựa chọn triển khai Zipkin server theo mô hình đơn lẻ hay phân tách thành phần dựa trên lưu lượng và yêu cầu sẵn sàng như thế nào?
Bạn xác định phạm vi mạng và quyền truy cập phù hợp cho endpoint tiếp nhận span và API truy vấn của Zipkin như thế nào?
Bạn phân biệt vai trò của collector, storage component và query service trong kiến trúc Zipkin như thế nào?
Bạn lựa chọn storage backend dựa trên khối lượng span, thời gian lưu, khả năng truy vấn và yêu cầu phục hồi ra sao?
Bạn đánh giá giới hạn của lưu trữ in-memory khi dùng Zipkin trong môi trường phát triển hoặc production như thế nào?
Bạn thiết kế dung lượng và retention cho kho trace dựa trên tốc độ ingest, kích thước span và tỷ lệ sampling ra sao?
Bạn kiểm tra Zipkin đã nhận span và lưu thành công bằng những dấu hiệu ở API, log và metric nào?
Bạn phân biệt lỗi ứng dụng không gửi span với lỗi collector từ chối span hoặc lỗi storage không ghi được như thế nào?
Bạn xác định cách kiểm soát kích thước batch và tần suất gửi span để cân bằng độ trễ xuất dữ liệu với hiệu năng ứng dụng ra sao?
Bạn xử lý tình huống Zipkin collector chậm hoặc tạm ngừng nhận dữ liệu để tránh làm nghẽn luồng request nghiệp vụ như thế nào?
Bạn thiết kế nhiều Zipkin server hoặc collector để tăng khả năng tiếp nhận span mà không tạo điểm lỗi đơn ra sao?
Bạn xác định những metric vận hành nào cần theo dõi cho Zipkin server, collector và storage như thế nào?
Bạn phân biệt B3 propagation với W3C Trace Context về định dạng header và khả năng tương tác giữa các hệ thống như thế nào?
Bạn mô tả vai trò của traceparent và tracestate trong W3C Trace Context khi một request đi qua nhiều service như thế nào?
Bạn phân biệt B3 single-header và multi-header propagation và lựa chọn định dạng phù hợp với hệ thống hiện hữu ra sao?
Bạn xử lý một luồng request đi qua service sử dụng B3 và service sử dụng W3C Trace Context để không làm đứt trace như thế nào?
Bạn xác định header propagation nào cần được giữ qua API gateway, reverse proxy và load balancer như thế nào?
Bạn kiểm tra nguyên nhân trace ID bị thay đổi khi request đi qua một proxy hoặc service trung gian bằng cách nào?
Bạn truyền trace context qua message broker khi producer và consumer không xử lý cùng thời điểm như thế nào?
Bạn phân biệt parent-child relationship với span link khi một consumer xử lý message liên quan đến nhiều trace nguồn như thế nào?
Bạn thiết kế propagation cho tác vụ bất đồng bộ hoặc scheduled job không có request HTTP ban đầu ra sao?
Bạn xử lý trường hợp client bên ngoài gửi trace header giả mạo hoặc không hợp lệ để bảo vệ hệ thống như thế nào?
Bạn xác định khi nào nên tiếp tục trace context từ bên ngoài và khi nào nên tạo trace mới tại ranh giới tin cậy như thế nào?
Bạn kiểm tra việc truyền baggage hoặc metadata qua nhiều service để tránh làm lộ thông tin nhạy cảm ra sao?
Bạn phân biệt trace ID với request ID và correlation ID khi thiết kế khả năng tìm kiếm xuyên log và trace như thế nào?
Bạn lựa chọn định dạng propagation để các thư viện Brave, Micrometer Tracing và OpenTelemetry có thể tương tác ra sao?
Bạn sử dụng Zipkin UI để tìm trace theo trace ID, service, operation hoặc thời gian trong một hệ thống có nhiều request như thế nào?
Bạn kết hợp service name, span name, annotation và tag để thu hẹp kết quả tìm trace khi điều tra sự cố như thế nào?
Bạn thiết kế tag có giá trị ổn định để truy vấn trace mà không làm tăng cardinality hoặc lộ dữ liệu nhạy cảm như thế nào?
Bạn xác định cách dùng local endpoint và remote endpoint để nhận diện service nguồn và service đích khi đọc trace như thế nào?
Bạn phân tích một trace có nhiều span lồng nhau để tìm service hoặc dependency làm tăng p99 latency ra sao?
Bạn nhận diện một span bị thiếu hoặc có parent không tồn tại trong trace và xác định nguyên nhân propagation như thế nào?
Bạn điều tra trường hợp trace xuất hiện nhiều root span dù thực tế chỉ có một request xuyên dịch vụ như thế nào?
Bạn phân biệt một service xử lý chậm với một service chỉ chờ kết quả từ downstream bằng cách đọc timeline trace ra sao?
Bạn xác định dấu hiệu retry hoặc gọi lặp một dependency trong trace để đánh giá tác động lên độ trễ như thế nào?
Bạn dùng trace để phát hiện N+1 query, fan-out quá lớn hoặc gọi tuần tự những dependency có thể chạy song song như thế nào?
Bạn kết hợp trace với log có trace ID để đi từ span lỗi tới stack trace và thông tin chi tiết của ứng dụng như thế nào?
Bạn kết hợp trace với metric latency, throughput và error rate để xác định thời điểm bắt đầu sự cố ra sao?
Bạn đối chiếu client span và server span để xác định tầng phát sinh lỗi của một request như thế nào?
Bạn diễn giải trường hợp client span có lỗi nhưng server span không có lỗi để tìm vấn đề ở mạng hoặc gateway ra sao?
Bạn phân tích trace có khoảng trống thời gian lớn giữa hai span để xác định nơi request đang chờ như thế nào?
Bạn kiểm tra tính nhất quán của đồng hồ giữa các máy khi timestamp của span có vẻ chồng lấn hoặc sai thứ tự ra sao?
Bạn xác định những hạn chế của việc dùng duration từ trace khi đồng hồ các node bị lệch như thế nào?
Bạn tích hợp tracing vào ứng dụng Java để theo dõi HTTP server, HTTP client và lời gọi database như thế nào?
Bạn phân biệt cách instrument thủ công và tự động trong ứng dụng Java khi dùng thư viện tracing như thế nào?
Bạn lựa chọn Brave hoặc OpenTelemetry làm nền instrumentation cho một ứng dụng Java dựa trên hệ sinh thái hiện tại ra sao?
Bạn giải thích vai trò của Micrometer Observation và Micrometer Tracing trong việc tạo và truyền span ở Spring Boot như thế nào?
Bạn tích hợp Micrometer Tracing với backend Zipkin trong Spring Boot để xuất trace mà không gắn chặt nghiệp vụ vào Zipkin như thế nào?
Bạn lựa chọn bridge Brave hay OpenTelemetry cho Micrometer Tracing dựa trên khả năng tương thích và hệ sinh thái hiện có như thế nào?
Bạn lựa chọn dependency và cấu hình tracing cho ứng dụng Spring Boot theo phiên bản framework và yêu cầu exporter ra sao?
Bạn kiểm tra trace được tạo tự động cho controller và RestClient hoặc HTTP client sau khi bật instrumentation như thế nào?
Bạn instrument thủ công một đoạn nghiệp vụ Java bằng observation hoặc tracer khi cần thêm span có ý nghĩa như thế nào?
Bạn quyết định thao tác nội bộ nào cần span riêng dựa trên giá trị chẩn đoán và độ phức tạp trace như thế nào?
Bạn truyền context qua executor, CompletableFuture hoặc thread pool trong Java để child span vẫn thuộc đúng trace như thế nào?
Bạn xử lý context bị mất khi một tác vụ chuyển thread hoặc chạy bất đồng bộ trong ứng dụng Spring như thế nào?
Bạn kiểm tra propagation qua Spring MVC, WebFlux hoặc lời gọi gRPC khi các mô hình thực thi khác nhau ra sao?
Bạn cấu hình tracing cho truy vấn JDBC hoặc truy cập database để thể hiện thời gian chờ và lỗi mà không ghi SQL nhạy cảm như thế nào?
Bạn thiết kế span cho thao tác gửi và nhận message trong ứng dụng Spring để nối trace giữa producer và consumer ra sao?
Bạn lựa chọn các tag cho span Java như service, route, status và database operation mà tránh gắn dữ liệu cá nhân như thế nào?
Bạn xác định nguyên nhân trace không xuất hiện trên Zipkin dù ứng dụng Spring Boot vẫn chạy bình thường bằng những bước nào?
Bạn kiểm tra việc cấu hình endpoint Zipkin, batch reporter và kết nối mạng khi span không được xuất ra như thế nào?
Bạn phân biệt lỗi tạo span, lỗi truyền context và lỗi export span khi chẩn đoán tích hợp Java như thế nào?
Bạn đánh giá tác động của instrumentation tự động đến CPU, bộ nhớ, số lượng span và latency của ứng dụng Java ra sao?
Bạn thiết kế kiểm thử tích hợp chứng minh trace xuyên qua hai ứng dụng Spring Boot và xuất hiện đầy đủ trên Zipkin như thế nào?
Bạn tích hợp OpenTelemetry SDK hoặc agent với Zipkin exporter theo kiến trúc nào để gửi span tới Zipkin như thế nào?
Bạn phân biệt Zipkin exporter trực tiếp với việc gửi OTLP tới OpenTelemetry Collector rồi chuyển tiếp sang Zipkin như thế nào?
Bạn lựa chọn nơi thực hiện batching, retry và export timeout khi ứng dụng gửi trace qua Collector hay gửi trực tiếp như thế nào?
Bạn kiểm tra khả năng tương thích giữa semantic conventions của OpenTelemetry và cách Zipkin biểu diễn span, tag hoặc endpoint ra sao?
Bạn xử lý trường hợp một trace được tạo bởi nhiều SDK khác nhau nhưng tên span và attribute không thống nhất như thế nào?
Bạn lựa chọn cách chuyển đổi hoặc chuẩn hóa span trước khi lưu Zipkin mà không làm mất ngữ nghĩa nguồn như thế nào?
Bạn xác định phiên bản giao thức hoặc định dạng span mà ứng dụng và Zipkin server cùng hỗ trợ bằng cách nào?
Bạn kiểm tra một exporter gửi dữ liệu không tương thích hoặc payload lỗi định dạng tới Zipkin collector như thế nào?
Bạn phân biệt lỗi HTTP từ Zipkin collector với lỗi serialize hoặc buffer tại OpenTelemetry SDK như thế nào?
Bạn quyết định lấy mẫu ở SDK, agent hay Collector dựa trên yêu cầu chi phí và khả năng giữ trace lỗi như thế nào?
Bạn so sánh head-based sampling và tail-based sampling về thời điểm quyết định, tài nguyên cần thiết và khả năng giữ trace lỗi như thế nào?
Bạn xác định xác suất sampling cho một dịch vụ dựa trên lưu lượng, ngân sách lưu trữ và mục tiêu quan sát như thế nào?
Bạn đánh giá nguy cơ sampling bỏ sót một lỗi hiếm gặp và cách ưu tiên giữ lại trace có lỗi hoặc độ trễ cao ra sao?
Bạn xác định ảnh hưởng của sampling không nhất quán giữa các service đến khả năng giữ đủ trace xuyên hệ thống như thế nào?
Bạn thiết kế chính sách sampling khác nhau cho endpoint quan trọng, request bình thường và môi trường thử nghiệm ra sao?
Bạn cân bằng tỷ lệ sampling với dung lượng storage, thời gian truy vấn và overhead instrumentation như thế nào?
Bạn sử dụng trace sampling có kiểm soát để giảm chi phí nhưng vẫn giữ được tính đại diện của các nhóm request như thế nào?
Bạn kiểm tra liệu số trace xuất hiện trên Zipkin có phản ánh đúng tỷ lệ sampling cấu hình trong ứng dụng hay không như thế nào?
Bạn xử lý trường hợp trace bị thiếu span do một service lấy mẫu hoặc export theo chính sách khác các service còn lại như thế nào?
Bạn lựa chọn giới hạn số span, kích thước attribute và thời gian export để ngăn trace bất thường gây quá tải như thế nào?
Bạn đánh giá tác động của exporter queue đầy hoặc collector unavailable đến việc mất trace và hoạt động ứng dụng ra sao?
Bạn xác định những thông tin nào trong trace có thể chứa token, email, user ID hoặc dữ liệu nghiệp vụ nhạy cảm như thế nào?
Bạn thiết kế chính sách lọc hoặc redaction span tag, annotation và baggage trước khi dữ liệu được lưu ở Zipkin ra sao?
Bạn tránh ghi URL đầy đủ, query parameter hoặc SQL literal có dữ liệu nhạy cảm vào span như thế nào?
Bạn so sánh redaction tại instrumentation với redaction tại Collector theo ranh giới tin cậy và nguy cơ dữ liệu thô bị lưu tạm như thế nào?
Bạn kiểm soát quyền truy cập Zipkin UI và query API khi trace chứa metadata nội bộ hoặc thông tin người dùng ra sao?
Bạn lựa chọn retention và chính sách xóa trace dựa trên giá trị điều tra, yêu cầu tuân thủ và chi phí lưu trữ như thế nào?
Bạn bảo vệ endpoint nhận span để tránh nguồn không đáng tin gửi trace giả hoặc làm tăng tải collector như thế nào?
Bạn xác định các metric và log cần giám sát để phát hiện Zipkin ingest chậm, storage lỗi hoặc query API suy giảm như thế nào?
Bạn điều tra tình huống Zipkin UI mở được nhưng không tìm thấy trace theo service hoặc khoảng thời gian dự kiến như thế nào?
Bạn phân biệt trace không được gửi, trace bị sampling, trace hết retention và trace không truy vấn được bằng những bằng chứng nào?
Bạn xử lý tình huống Zipkin collector trả lỗi hoặc storage backend hết dung lượng mà không ảnh hưởng request nghiệp vụ ra sao?
Bạn phân tích sự tăng đột biến số span sau một lần nâng cấp instrumentation và xác định nguồn phát sinh như thế nào?
Bạn thiết kế dashboard hoặc quy trình cảnh báo cho tỷ lệ lỗi export, số span nhận được và độ trễ truy vấn của Zipkin như thế nào?
Bạn xây dựng runbook điều tra một request chậm xuyên nhiều service bằng Zipkin, log và metric theo trình tự nào?
Bạn xác lập tiêu chí nghiệm thu end-to-end để chứng minh trace context được truyền đúng, span được lưu và sự cố có thể được điều tra trên Zipkin như thế nào?
