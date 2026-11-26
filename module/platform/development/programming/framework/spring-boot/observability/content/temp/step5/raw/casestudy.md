Một dịch vụ đặt hàng dùng Spring Boot Actuator để kiểm tra sức khỏe nhưng khi đơn hàng xử lý chậm đội trực chỉ thấy trạng thái UP mà không có dữ liệu về độ trễ từng bước.
Một nhóm tích hợp Micrometer Observation vào luồng duyệt đơn nhưng không đăng ký cơ chế thu nhận tín hiệu phù hợp, khiến các observation được tạo mà dashboard không có metric mong đợi.
Ứng dụng thanh toán tạo Observation cho từng yêu cầu nhưng quên kết thúc vòng đời khi nhánh xử lý ném exception, khiến các phép đo thời gian không được ghi đầy đủ.
Một hệ thống nhận sự kiện từ broker mở Observation ở bước tiêu thụ nhưng khi xử lý lỗi lại giữ scope trên thread tái sử dụng, khiến log sự kiện tiếp theo mang ngữ cảnh cũ.
Một nhóm tạo Observation thủ công bên trong phương thức đã có instrumentation tự động, khiến cùng lời gọi HTTP được thống kê thành hai đoạn đo trùng mục đích.
Một ứng dụng có nhiều ObservationHandler cùng quan tâm một sự kiện, nhưng đội phát triển không phân biệt handler cho metric với handler cho trace và cho rằng mỗi handler đều sinh cùng loại dữ liệu.
Một dịch vụ sử dụng ObservationRegistry mặc định không được cấu hình như môi trường production, khiến bài test tạo Observation thành công nhưng không xác minh được tín hiệu nào được xuất.
Hệ thống đặt tên Observation theo mã giao dịch cụ thể của khách hàng, khiến số tên phép đo tăng theo số đơn hàng thay vì đại diện một loại thao tác ổn định.
Một nhóm thêm contextual name cho Observation dựa trên dữ liệu cá nhân của người gọi, khiến thông tin nhận diện khách hàng xuất hiện trong giao diện trace không được cấp quyền phù hợp.
Một ứng dụng xử lý tác vụ nền ghi nhận start và stop của Observation ở những nhánh khác nhau, nhưng khi yêu cầu bị hủy giữa chừng đoạn thời gian đo kéo dài bất thường.
Dịch vụ soạn báo cáo dùng cùng một tên Observation cho bước đọc database và bước gửi email, khiến đồ thị thời gian không phân biệt được hai loại công việc có đặc tính rất khác.
Một nhóm muốn đo thời gian lấy thông tin sản phẩm bằng Observation nhưng chỉ đặt đoạn đo quanh thao tác chuyển đổi DTO, khiến dashboard bỏ qua thời gian chờ API đối tác.
Một ứng dụng tạo các Observation lồng nhau cho quy trình thanh toán, nhưng mối quan hệ cha con không xuất hiện trong trace vì phần ngữ cảnh đang hoạt động không được giữ đúng phạm vi.
Hệ thống gom metric từ một số service nhưng mỗi service dùng tên Observation khác nhau cho cùng thao tác kiểm tra tồn, khiến biểu đồ tổng hợp không so sánh được.
Một nhóm thay đổi tên và các khóa tag của Observation sau deploy mà không chuyển đổi dashboard, khiến cảnh báo SLA cũ không nhận dữ liệu dù các request vẫn đang được xử lý.
Dịch vụ vận chuyển đánh dấu lỗi nghiệp vụ bị từ chối như một exception kỹ thuật trong Observation, khiến tỷ lệ lỗi hệ thống bị tăng bởi các yêu cầu hợp lệ không được duyệt.
Một API chuyển ngoại lệ thành HTTP 200 với body báo thất bại nhưng Observation chỉ thấy trạng thái thành công, khiến đội vận hành không nhận ra số lượng xử lý nghiệp vụ lỗi.
Một ứng dụng thêm convention tùy chỉnh cho Observation nhưng convention toàn cục đã định nghĩa tên tương tự, khiến một số đường đo mang tập thuộc tính khác nhau giữa các môi trường.
Đội phát triển gắn annotation quan sát cho nhiều phương thức nội bộ rất nhỏ, khiến số đoạn đo tăng mạnh và chi phí thu thập lớn hơn giá trị chẩn đoán thu được.
Một service bắt đầu Observation trước khi request vào hàng đợi xử lý nhưng dừng khi task được nhận, khiến thời gian chờ thực thi phía sau không có trong metric độ trễ.
Hệ thống tạo một Observation cho toàn bộ batch gồm hàng nghìn bản ghi, khiến các bản ghi lỗi riêng lẻ khó được liên kết với nguyên nhân của một lần chạy dài.
Một nhóm định nghĩa ObservationFilter để bổ sung metadata cho mọi yêu cầu, nhưng bộ lọc đưa thêm địa chỉ email người dùng vào thuộc tính và phát tán dữ liệu nhạy cảm.
Một ứng dụng khởi tạo Observation trong callback của thư viện cũ, nhưng callback có thể được gọi đồng thời nhiều lần và nhóm chưa xác minh phạm vi ngữ cảnh mỗi lần gọi.
Một API quản lý kho đã có observation tự động cho HTTP server nhưng đội tích hợp lại đo latency chỉ bằng log thủ công, khiến hai nguồn số liệu có cách xác định điểm bắt đầu khác nhau.
Một hệ thống so sánh thời gian xử lý từ Observation với duration trong access log, nhưng một bên chỉ đo controller còn bên kia tính cả xử lý filter và serializing response.
Một nhóm đưa MeterRegistry vào service mà quên cấu hình registry xuất dữ liệu, khiến các counter thay đổi trong tiến trình nhưng hệ thống giám sát trung tâm không nhìn thấy.
Ứng dụng bán vé dùng Counter để đo số lượt truy cập đang diễn ra, khiến đồ thị chỉ tăng liên tục và không cho biết có bao nhiêu request còn hoạt động tại một thời điểm.
Một dịch vụ đo số request hoàn tất bằng Counter nhưng tăng cả khi retry nội bộ, khiến dashboard đánh giá lượng giao dịch khách hàng cao hơn số yêu cầu duy nhất.
Một nhóm dùng Gauge dựa trên một đối tượng tạm thời không còn được giữ tham chiếu, khiến giá trị hàng đợi thỉnh thoảng biến mất hoặc không cập nhật như mong đợi.
Hệ thống dùng Timer đo thời gian gọi API ngoài nhưng trộn cả lời gọi nhanh và timeout rất dài, khiến giá trị trung bình che giấu nhóm khách thường xuyên chờ quá SLA.
Một đội đặt tên metric Timer theo đường dẫn URL chứa mã đơn hàng, khiến mỗi request tạo chuỗi thời gian mới và server giám sát tăng bộ nhớ nhanh.
Một ứng dụng đo kích thước file đầu vào bằng DistributionSummary nhưng lại hiển thị đơn vị giống milliseconds, khiến báo cáo cho người vận hành diễn giải sai quy mô dữ liệu.
Một job nhập dữ liệu dùng LongTaskTimer cho tác vụ kéo dài hàng giờ, nhưng dashboard chỉ hiển thị Counter đếm lần hoàn tất và bỏ qua thời lượng các tác vụ vẫn đang chạy quá hạn.
Nền tảng thương mại điện tử dùng cùng tên metric cho thời gian response và số byte, khiến dữ liệu từ hai loại phép đo không thể được nhóm đúng trong backend metrics.
Một dịch vụ ghi lượng request bằng counter tăng ở lớp controller, nhưng lỗi xảy ra trong security filter trước controller nên nhiều request bị từ chối không được đếm.
Một ứng dụng đo active connection pool bằng Gauge nhưng lại thống kê tổng kết nối từng được tạo, khiến đội trực không phát hiện pool đã hết kết nối khả dụng.
Đội phát triển thu thập JVM heap metrics nhưng bỏ qua direct memory và native allocation, khiến container bị dừng vì vượt giới hạn bộ nhớ dù biểu đồ heap vẫn thấp.
Một hệ thống chỉ theo dõi CPU trung bình của pod, trong khi một vài thread thực thi bị tắc trên lock khiến throughput giảm dù CPU còn dư.
Một ứng dụng có pool thực thi bất đồng bộ nhưng không có metric queue depth, khiến yêu cầu chờ hàng phút vẫn được báo là hệ thống không quá tải.
Một nhóm đặt alert dựa trên tổng số HTTP 500 nhưng không theo lưu lượng, khiến giờ cao điểm tạo nhiều cảnh báo dù tỷ lệ lỗi giữ nguyên như trước.
Một dịch vụ chỉ theo dõi tỷ lệ request thành công nhưng không đo thời gian chờ kết nối database, khiến sự cố pool cạn được phát hiện sau khi người dùng bắt đầu timeout.
Một backend monitoring dùng histogram của latency từ một service nhưng service khác chỉ xuất Timer count và sum, khiến phân tích p95 toàn hệ thống không đủ dữ liệu cần thiết.
Một nhóm bật histogram cho tất cả Timer với nhiều tổ hợp tag, khiến kích thước scrape tăng mạnh và bộ lưu trữ metrics chịu áp lực ngoài dự kiến.
Một hệ thống đặt SLO ở 200 milliseconds nhưng dải bucket histogram thiếu độ phân giải quanh ngưỡng này, khiến đánh giá tỷ lệ request đạt mục tiêu thiếu chính xác.
Ứng dụng gửi số liệu latency qua nhiều instance rồi tính trung bình các p99 của từng instance, khiến giá trị báo cáo toàn cụm không phản ánh phân bố request thực tế.
Một dịch vụ đo metric từ quá trình khởi động nhưng backend chỉ bắt đầu scrape sau khi ứng dụng ready, khiến những lần startup thất bại không xuất hiện trong chuỗi thời gian.
Một đội vận hành xem tăng Counter trong vòng một phút nhưng không xét việc pod restart đặt lại số đếm, khiến đồ thị đôi khi thể hiện lưu lượng âm hoặc giảm bất thường.
Một ứng dụng có metric trạng thái hàng đợi chỉ cập nhật mỗi phút, nhưng dashboard áp dụng cách tính tốc độ của Counter khiến giá trị Gauge được diễn giải thành số sự kiện mới.
Nền tảng học trực tuyến gắn label cho số request theo mã người dùng, khiến cardinality tăng đến hàng triệu tổ hợp trong một ngày kiểm tra tải.
Một dịch vụ đặt tag theo URL thô bao gồm query string và token, khiến metrics vừa bùng nổ số series vừa làm lộ dữ liệu đáng lẽ không được thu thập.
Một hệ thống thêm tên exception kèm thông báo lỗi vào low-cardinality key, khiến mỗi lỗi SQL khác nhau tạo nhãn mới và backend khó tổng hợp nguyên nhân.
Một nhóm dùng mã phiên đăng nhập làm metric tag để dễ lọc theo khách, nhưng chỉ số kết nối tăng số series liên tục trong khi nhu cầu vận hành chỉ cần nhóm theo tenant.
Một ứng dụng đặt tenant ID làm nhãn metrics và số tenant tăng nhanh sau khi mở rộng sản phẩm, khiến dung lượng lưu trữ tăng khác xa dự toán ban đầu.
Một service gắn đường dẫn HTTP nguyên bản có UUID lên Timer, khiến API cùng một route có hàng chục nghìn chuỗi metric khác nhau trên Prometheus.
Một đội muốn biết phản hồi chậm theo nhóm endpoint nhưng tag lại gắn tên controller Java, khiến sau refactor tên class dashboard thể hiện như các API vừa xuất hiện mới.
Một ứng dụng gắn tên nghiệp vụ vào low-cardinality keys và email vào high-cardinality keys của Observation, nhưng đội vận hành tìm email trong metrics mà không xét dữ liệu trace.
Một dịch vụ gắn nhãn vùng dữ liệu theo tên datacenter cố định nhưng có hai giá trị viết hoa khác nhau, khiến cùng khu vực bị chia thành hai series trong dashboard.
Một nhóm thêm nhãn error=true cho mọi lỗi ngoại lệ, nhưng những trường hợp trả HTTP 4xx hợp lệ không có cách phân biệt lỗi do client với sự cố phía server.
Ứng dụng tài chính dùng mã hợp đồng như tag trên DistributionSummary, khiến hệ thống thu thập tạo thêm hàng loạt chuỗi khi dữ liệu lịch sử được xử lý.
Một hệ thống tạo metrics riêng cho từng mã sự kiện nghiệp vụ nhưng danh sách mã được sinh động từ đối tác, khiến số series tăng đột ngột sau một lần tích hợp.
Một đội áp dụng MeterFilter để giảm cardinality nhưng vô tình loại bỏ tag môi trường, khiến dữ liệu staging và production bị gộp chung khi phân tích.
Một ứng dụng muốn hạn chế số tag value cho cùng một meter nhưng chính sách lọc đã làm mất khả năng phân biệt các nhóm lỗi quan trọng khi sự cố xảy ra.
Một dịch vụ đặt tên tag khác giữa bản Java và bản Node của hệ thống, khiến dashboard chung không thể nhóm các kết quả đo cùng loại theo trạng thái HTTP.
Nền tảng streaming gắn partition ID làm metric tag khi số partition tăng, khiến mỗi lần mở rộng cụm tạo thêm tập series khiến truy vấn quan sát chậm hơn.
Một nhóm xuất metric với nhãn phiên bản build chính xác đến commit, khiến các phiên bản vừa deploy đều sinh series mới và tăng chi phí lưu trữ qua nhiều đợt phát hành.
Một ứng dụng thêm nhãn endpoint trên metric global nhưng một số điểm đo không có nhãn này, khiến biểu đồ so sánh tỷ lệ lỗi theo endpoint bỏ sót dữ liệu.
Một service giám sát cơ sở dữ liệu bằng meter tùy chỉnh giữ tham chiếu đến client đã đóng, khiến dashboard tiếp tục hiển thị giá trị cũ dù pool hiện tại hoạt động khác.
Một hệ thống triển khai MeterBinder cho thư viện nội bộ nhưng đăng ký nhiều lần qua các bean cấu hình, khiến số liệu được đo lặp hoặc trùng meter ID.
Một ứng dụng log lỗi của đơn hàng dưới dạng văn bản tự do không có mã tương quan, khiến đội hỗ trợ không tìm được trace tương ứng của cùng request.
Một nhóm bật log ở mức DEBUG khi đang điều tra lỗi HTTP nhưng ghi đầy đủ Authorization header, khiến token thật xuất hiện trong nền tảng tổng hợp log.
Một dịch vụ đặt trace ID vào MDC cho HTTP request nhưng không xóa sau khi xử lý lỗi, khiến thread tiếp tục phục vụ request khác với mã trace cũ.
Ứng dụng xử lý bất đồng bộ trên Executor nhưng không chuyển ngữ cảnh quan sát, khiến log ở tác vụ nền thiếu trace ID dù log controller có đủ thông tin.
Một hệ thống dùng JSON structured logging nhưng service A đặt khóa traceId còn service B đặt trace_id, khiến truy vấn tập trung không liên kết được cùng dấu vết.
Một nhóm ghi exception stack trace ở controller và tầng service rồi thêm log ở global handler, khiến cùng một lỗi bị thống kê như nhiều sự cố độc lập.
Một ứng dụng ghi log tạo hóa đơn thành công trước khi transaction thực sự commit, khiến đội vận hành nhận thông tin trái ngược giữa log và trạng thái database.
Một service chạy trong Kubernetes ghi log ra file cục bộ thay vì stdout được collector thu thập, khiến lỗi xảy ra ngay trước khi pod restart không còn dữ liệu điều tra.
Một đội đặt mức log TRACE cho package HTTP client trong production, khiến số lượng log quá lớn ảnh hưởng I/O và đẩy nhanh thời gian hết dung lượng lưu trữ.
Một ứng dụng hiển thị user ID và email trong message log để tra cứu lỗi, nhưng đội bảo mật phát hiện hệ thống log không có quyền truy cập tương ứng với dữ liệu cá nhân.
Một nhóm dùng trường timestamp không có timezone trong log từ nhiều vùng, khiến chuỗi thao tác của cùng giao dịch bị sắp xếp sai thứ tự thời gian.
Một service log thời gian xử lý bằng đồng hồ hệ thống nhưng request trải qua thay đổi đồng hồ máy chủ, khiến giá trị duration đôi khi âm hoặc không ổn định.
Một ứng dụng có logger bất đồng bộ nhưng hàng đợi log không đủ lớn khi xảy ra lỗi hàng loạt, khiến những dòng cần nhất cho điều tra bị mất.
Một hệ thống che toàn bộ body request trong log để bảo mật nhưng cũng không lưu mã lỗi nghiệp vụ, khiến khi kiểm tra giao dịch thất bại không có đủ dấu hiệu để phân loại.
Một đội trực truy vấn log theo mã phiên của khách nhưng hệ thống tracing chỉ gắn trace ID, khiến việc liên kết yêu cầu hỗ trợ với nguyên nhân kỹ thuật rất tốn thời gian.
Một dịch vụ trả lỗi cho người dùng nhưng global exception handler chỉ log nội dung exception mà không lưu request path hay trạng thái HTTP, khiến phân tích tỷ lệ lỗi bị thiếu ngữ cảnh.
Một ứng dụng dùng Logback cấu hình riêng trên production nhưng môi trường test lại dùng định dạng mặc định, khiến bộ phân tích log của CI không phát hiện sai định dạng trước deploy.
Một hệ thống lưu log toàn bộ dữ liệu kết quả từ AI và dịch vụ tài chính, khiến thời gian lưu giữ và truy cập log vượt chính sách quản trị thông tin của doanh nghiệp.
Một nhóm đặt correlation ID tự sinh và trace ID ở hai trường log không liên hệ, khiến cùng request có nhiều định danh nhưng không có quy tắc truy vết thống nhất.
Một dịch vụ dùng MDC cho mã tenant nhưng không giữ ngữ cảnh qua CompletableFuture, khiến log của nhánh ghi nền thiếu tenant ID và khó xác định dữ liệu bị ảnh hưởng.
Một hệ thống bổ sung Micrometer Tracing Bridge nhưng không có exporter phù hợp trong môi trường chạy, khiến các span xuất hiện trong tiến trình nhưng không đến nền tảng tracing.
Một ứng dụng tạo trace cho request HTTP vào nhưng không instrument HTTP client gọi dịch vụ khác, khiến trace kết thúc ở biên ứng dụng và không chỉ rõ đoạn chờ mạng.
Một đội gọi RestClient tới hệ thống kho bằng builder tự khởi tạo thay vì bean đã có instrumentation, khiến outbound span biến mất dù các request inbound vẫn có trace.
Một ứng dụng gọi WebClient ở pipeline reactive nhưng tạo client không qua cấu hình quan sát chung, khiến các lần gọi ngoài không xuất hiện dưới trace của request gốc.
Một service nhận header traceparent nhưng code gateway xóa header này trước khi chuyển tiếp, khiến mỗi dịch vụ tạo trace mới và mất liên kết giữa các bước.
Một nhóm dùng hai chuẩn truyền trace context khác nhau giữa gateway và backend, khiến span của mỗi phía vẫn được xuất nhưng không thuộc cùng một trace.
Ứng dụng dịch vụ công gửi request sang hệ thống thanh toán qua HTTP và có tracing, nhưng response timeout xảy ra trước khi span nhận thông tin kết thúc nên đồ thị chưa thể hiện đủ lỗi.
Một ứng dụng nhận message từ Kafka nhưng không trích xuất propagation context từ headers, khiến công việc tiêu thụ bản tin xuất hiện như một trace độc lập với bên phát.
Một nhóm truyền trace context qua message broker nhưng vô tình phát lại cùng headers cho batch mới, khiến các bản tin khác giao dịch bị gán sai mối quan hệ trace.
Một hệ thống gọi API ngoài sau khi tiếp nhận message, nhưng cả inbound và outbound được instrument trong những ngữ cảnh khác nhau khiến không liên kết được một chuỗi xử lý.
Một service có middleware tùy chỉnh tạo span mới cho từng thao tác, nhưng không thiết lập đúng parent context nên các span nằm ngang thay vì thể hiện cấu trúc phụ thuộc.
Một ứng dụng xử lý song song hai lời gọi HTTP nhưng sử dụng cùng mutable span context sai cách, khiến log của bước này mang thông tin của lời gọi còn lại.
Một nhóm đặt toàn bộ thông tin chi tiết đơn hàng vào span attributes, khiến tracing backend chứa dữ liệu nhạy cảm và payload vượt giới hạn được cho phép.
Một ứng dụng tạo span name chứa customer ID thay vì tên thao tác ổn định, khiến giao diện truy vấn trace khó nhóm cùng loại giao dịch theo điểm nghẽn.
Một dịch vụ ghép nhiều request của cùng khách vào một trace duy nhất quá lâu, khiến dấu vết trở nên khổng lồ và quan hệ nhân quả giữa các yêu cầu không còn rõ.
Một nhóm dựa vào trace để biết số giao dịch đã hoàn thành, nhưng sampling chỉ giữ một phần request nên số trace thấp hơn tổng giao dịch thực tế.
Một ứng dụng dùng span status mặc định cho lỗi nghiệp vụ được xử lý, khiến dashboard chỉ hiển thị request thành công dù nhiều đơn hàng bị từ chối theo chính sách.
Một service hoàn tất thao tác thanh toán rồi ném ngoại lệ ở bước ghi log, khiến span ghi ERROR dù tác dụng phụ quan trọng đã thực hiện thành công trước đó.
Một nhóm tạo span thủ công trên lời gọi đã được instrument tự động, khiến cây trace có hai đoạn trùng thời gian và người phân tích khó xác định đâu là chi phí thực tế.
Một ứng dụng hiển thị trace qua nhiều microservice nhưng đồng hồ giữa các node lệch nhau đáng kể, khiến thứ tự các span trên timeline khó phản ánh thứ tự công việc.
Một service nhận trace context từ nguồn bên ngoài không đáng tin cậy, nhưng hệ thống lại coi baggage do caller gửi là bằng chứng xác thực người dùng hiện tại.
Một nhóm không truyền trace flags qua gateway, khiến quyết định sampling của trace không thống nhất giữa các dịch vụ và cây trace có thể thiếu đoạn.
Một ứng dụng nhận request từ mobile rồi gọi nhiều backend song song, nhưng chỉ có trace của backend trả cuối được ghi vào log tổng hợp và bỏ qua lỗi của nhánh khác.
Một nhóm gắn thông tin giao dịch vào baggage để mang qua các service, nhưng baggage chứa quá nhiều trường khiến kích thước HTTP headers tăng và bị proxy từ chối.
Một hệ thống dùng baggage cho tenant ID nhưng không kiểm soát trust boundary, khiến giá trị do người gọi tự đặt bị sử dụng như thông tin phân quyền nội bộ.
Một ứng dụng Spring MVC dùng ThreadLocal cho trace ID nhưng chuyển xử lý sang @Async, khiến thread mới không nhận ngữ cảnh quan sát đã tạo ở controller.
Một dịch vụ Reactor sử dụng publishOn chuyển scheduler, nhưng log trong operator phía sau không có trace ID nếu ngữ cảnh quan sát không được truyền phù hợp.
Một nhóm dùng WebFlux và Reactor Context để mang thông tin truy vết, nhưng một callback được thực thi ngoài subscription chain không nhận metadata như các operator khác.
Một ứng dụng đặt MDC trên thread HTTP ban đầu rồi chạy CompletableFuture trên ForkJoinPool, khiến các log bước thực thi nền xuất hiện mà không có định danh giao dịch.
Một dịch vụ tạo ExecutorService bằng tay ngoài cấu hình instrumentation của ứng dụng, khiến span trong các task không được gắn vào trace cha của request.
Một nhóm thêm ContextSnapshot khi gửi tác vụ nền nhưng chụp ngữ cảnh sau khi scope gốc đã đóng, khiến trace ID truyền tới worker không phải của yêu cầu mong đợi.
Một hệ thống điều phối nhiều task độc lập qua thread pool dùng chung nhưng tái sử dụng context không đúng cách, khiến trace ID từ task trước xuất hiện trong task kế tiếp.
Một ứng dụng xử lý sự kiện bằng @Scheduled ngoài HTTP request, nhưng đội vận hành vẫn kỳ vọng có parent span từ một phiên người dùng trước đó và hiểu sai nguồn gốc trace.
Một service nhận callback từ SDK thanh toán trên thread do SDK tạo, khiến thông tin trace của request tạo thanh toán không tự xuất hiện trong phần xử lý callback.
Một nhóm sử dụng Kotlin coroutine trong ứng dụng Spring Boot nhưng không có bridge propagation đầy đủ, khiến trace bị ngắt sau khi coroutine chuyển dispatcher.
Một ứng dụng có nhiều request đồng thời qua Reactor và đọc dữ liệu MDC không tương thích với context reactive, khiến log đôi khi gắn nhầm mã giao dịch giữa người dùng.
Một nhóm chuyển từ RestTemplate sang WebClient để tăng concurrency, nhưng công cụ giám sát vẫn giả định mỗi trace tồn tại trên một thread và không liên kết được các đoạn bất đồng bộ.
Một hệ thống phát sự kiện tới hàng chục consumer sau một thao tác, nhưng chỉ dùng parent-child span mà không diễn đạt được những mối liên hệ bất đồng bộ quan trọng giữa các trace.
Một ứng dụng truyền metadata truy vết qua HTTP headers nhưng quên chuyển qua hệ thống retry queue, khiến bản tin được xử lý lần thứ hai không liên kết với thao tác ban đầu.
Một đội gửi context qua gRPC nhưng chỉ instrument HTTP gateway, khiến lời gọi RPC ở giữa hai service không xuất hiện trong đường đi giao dịch.
Một ứng dụng gọi tác vụ nền sau khi trả HTTP response và giữ nguyên scope quan sát đã đóng, khiến việc ghi nhận span của tác vụ nền có thời gian và parent không chính xác.
Một nhóm đưa correlation ID tùy biến vào baggage và metric tags, khiến dữ liệu có cardinality cao xuất hiện trong cả telemetry lưu lâu dài.
Một dịch vụ xử lý hàng loạt bản ghi trong một transaction chung, nhưng gắn từng item làm một span con có kích thước rất lớn khiến trace backend cắt bớt đoạn quan trọng.
Một hệ thống dùng OpenTelemetry Protocol exporter gửi spans ra collector nhưng cấu hình endpoint nhầm port nhận metrics, khiến dữ liệu tracing không đến được backend.
Một ứng dụng gửi metrics qua OTLP trong khi dashboard Prometheus chỉ scrape endpoint Actuator, khiến chỉ một phần metric xuất hiện và đội trực không hiểu hai đường thu thập khác nhau.
Một nhóm cấu hình exporter Prometheus trên service nhưng không cho phép truy cập endpoint metrics qua security rule, khiến scraper liên tục nhận HTTP 403.
Một hệ thống expose endpoint metrics của Actuator nhưng dùng reverse proxy đổi path, khiến cấu hình scrape tiếp tục gọi URL cũ và mất toàn bộ số liệu sau deploy.
Một ứng dụng gửi traces đến OpenTelemetry Collector qua mạng riêng nhưng môi trường production chặn egress, khiến phần nghiệp vụ vẫn hoạt động còn tracing hoàn toàn im lặng.
Một nhóm export telemetry theo chu kỳ quá dày trên nhiều instance, khiến số lượt gửi tăng mạnh và collector bị quá tải ngay sau khi mở rộng cụm.
Một dịch vụ cấu hình timeout exporter quá ngắn so với độ trễ liên vùng, khiến batch dữ liệu bị thất bại liên tục dù backend quan sát vẫn sẵn sàng.
Một ứng dụng cấu hình endpoint collector bằng biến môi trường nhưng sai giao thức gRPC so với HTTP/protobuf, khiến telemetry không được chấp nhận dù host và port có thể kết nối.
Một ứng dụng đăng ký meter tùy chỉnh trực tiếp vào registry Prometheus trong khi dashboard thứ hai đọc OTLP registry khác, khiến cùng thao tác có số liệu khác nhau trên hai hệ thống.
Một hệ thống chạy Prometheus scrape mỗi phút nhưng alert yêu cầu phản ứng trong vài giây, khiến lỗi tăng đột ngột không được phát hiện đủ sớm.
Một ứng dụng có nhiều instance tự đăng ký cùng nhãn instance, khiến sau khi tổng hợp backend metrics không phân biệt được node nào đang lỗi.
Một nhóm sử dụng push exporter cho metric nhưng vẫn đặt quy tắc Prometheus scrape giống mô hình pull, khiến báo cáo số liệu giữa hai luồng dễ đếm lặp.
Một dịch vụ được nâng cấp và đổi resource attribute service.name, khiến dữ liệu metric và trace mới nằm ở một tên service khác với dashboard vận hành cũ.
Một hệ thống chạy trên nhiều cluster nhưng không gắn environment và cluster labels nhất quán, khiến số liệu production bị trộn với staging trong biểu đồ lỗi.
Một ứng dụng exporter bị lỗi tạm thời nhưng hàng đợi telemetry không có giới hạn, khiến dữ liệu chưa gửi tích lũy và gây áp lực bộ nhớ lên ứng dụng nghiệp vụ.
Một nhóm cắt giảm chi phí collector bằng cách rút ngắn thời gian lưu trace, nhưng đội điều tra chỉ nhận khiếu nại sau vài ngày và không còn dấu vết liên quan.
Một hệ thống cấu hình retention metrics ngắn hơn chu kỳ chạy job theo tháng, khiến nhóm kinh doanh không thể đối chiếu latency ở hai kỳ cao điểm.
Một service xuất logs và traces tới hai nền tảng khác nhau nhưng sử dụng định dạng trace ID không nhất quán, khiến liên kết nhấn từ log sang trace không mở đúng kết quả.
Một ứng dụng khai báo instrumentation chung trong starter nội bộ nhưng chỉ một môi trường có đầy đủ tracing bridge và exporter, khiến cùng phiên bản code tạo telemetry rất khác nhau.
Một nhóm đặt sampling probability rất thấp trong môi trường ít traffic, khiến các giao dịch lỗi hiếm gặp không có trace nào để điều tra dù metrics cho thấy sự cố.
Một dịch vụ bật sampling mọi request khi traffic tăng đột biến, khiến chi phí lưu trace và tài nguyên exporter vượt khả năng collector đang cấp phát.
Một ứng dụng có gateway lấy mẫu trace ở đầu luồng nhưng backend tiếp tục quyết định sampling độc lập, khiến cây trace thiếu những service đã thực thi trên cùng giao dịch.
Một nhóm muốn phân tích các request chậm qua tail sampling ở collector nhưng exporter đã loại hầu hết spans trước đó, khiến collector không có dữ liệu để lựa chọn.
Một hệ thống dùng tail sampling để chọn trace lỗi nhưng collector không giữ đủ dữ liệu trong thời gian chờ quyết định, khiến các request kéo dài bị thiếu span cuối.
Một dịch vụ dùng sampling dựa trên trạng thái lỗi nhưng quyết định ở lúc bắt đầu request, khiến nhiều giao dịch thất bại ở cuối không được giữ lại như nhóm vận hành kỳ vọng.
Một nhóm gắn sampling rate vào dashboard tỷ lệ lỗi mà không phân biệt trace được lấy mẫu với metric đếm đầy đủ, khiến báo cáo có vẻ mâu thuẫn giữa hai nguồn.
Một hệ thống điều phối nhiều microservice có service trung gian lưu lượng rất cao, khiến việc lấy mẫu không cùng tỷ lệ theo từng hop làm phân tích tỷ trọng latency bị lệch.
Một ứng dụng cần giữ trace cho các giao dịch giá trị cao, nhưng chính sách sampling chỉ nhìn URL chung nên bỏ qua một phần giao dịch cần điều tra kiểm toán.
Một nhóm để tracing sampling ở mức development trong production, khiến số span tăng theo số request và độ trễ exporter ảnh hưởng tài nguyên máy chủ.
Một service có batch job chạy ban đêm rất dài nhưng dùng sampling tối ưu cho HTTP ngắn, khiến khi một job lỗi toàn bộ chuỗi bước quan trọng không có trace.
Một hệ thống muốn kiểm tra tần suất retry của API bên ngoài nhưng chỉ dùng trace đã sample, khiến số lần gọi lại trong báo cáo thấp hơn số thực tế.
Một nhóm đo tác động overhead của tracing chỉ trong môi trường test ít traffic, khiến production với nhiều span và tag có độ trễ cao hơn kết quả benchmark.
Một ứng dụng có collector nằm ở vùng khác và network latency tăng, khiến batch span được gửi trễ và trace chưa xuất hiện khi đội trực bắt đầu xử lý cảnh báo.
Một nhóm dùng trace exemplar liên kết điểm histogram latency tới trace cụ thể, nhưng khi sampling không giữ được trace đích liên kết từ biểu đồ không mở được chi tiết.
Một dịch vụ dùng dữ liệu trace để tính p95 HTTP theo từng endpoint, nhưng tỷ lệ lấy mẫu thay đổi giữa hai đợt deploy khiến so sánh chất lượng bị sai.
Một hệ thống bán vé thấy tỷ lệ HTTP 500 tăng trong metric nhưng không có log mang trace ID cho các lỗi này, khiến ba tín hiệu quan sát không liên kết được.
Một ứng dụng có request latency p99 cao nhưng trace sampled chủ yếu là request nhanh, khiến đội phân tích tập trung vào code bình thường mà bỏ qua điểm nghẽn thực.
Một nhóm nhìn trace cho thấy thời gian chờ database lâu nhưng metric pool connections ổn định, khiến giả thuyết cạn kết nối không phù hợp với biểu hiện đang quan sát.
Một dịch vụ báo timeout ở HTTP client và log có DNS error nhưng dashboard chỉ hiển thị trạng thái HTTP inbound, khiến đội trực phải xác định lớp lỗi từ các nguồn khác nhau.
Một ứng dụng có latency tăng sau phát hành mới nhưng metric theo version build bị thiếu trên một số instance, khiến đội không biết đợt deploy nào tạo ra hồi quy.
Một nhóm phân tích lỗi thanh toán bằng log trong một vùng và trace trong vùng khác, nhưng đồng hồ các node chênh nhau làm khó sắp xếp các sự kiện theo thời gian.
Một hệ thống xử lý order nhanh nhưng thông báo cho khách đến muộn vì backlog message broker, khiến trace HTTP thành công không phản ánh thời gian hoàn tất nghiệp vụ đầu cuối.
Một ứng dụng có queue depth tăng và CPU thấp, nhưng trace một request chỉ chứa phần tính toán mà không có đoạn đo thời gian chờ trong hàng đợi.
Một dịch vụ triển khai @Observed cho bước tính phí nhưng instrumentation metrics hiện có cũng đo cùng thao tác, khiến dashboard có hai số latency khác nhau về phạm vi đo.
Một nhóm xác định lỗi chỉ trên HTTP status code và bỏ qua exception được xử lý nội bộ, khiến metrics báo thành công trong khi log ghi một loạt fallback.
Một hệ thống có spike memory và GC pause cùng lúc p95 latency tăng, nhưng đội chỉ nhìn CPU nên chẩn đoán sai nguyên nhân là database chậm.
Một ứng dụng sử dụng histogram buckets khác nhau giữa các replica cùng service, khiến phép tổng hợp phân bố latency theo toàn bộ deployment không đáng tin cậy.
Một dịch vụ chuyển toàn bộ logs từ dạng text sang JSON nhưng dashboard chưa đổi cách parse, khiến các trường error type và trace ID biến mất khỏi truy vấn điều tra.
Một nhóm cần phân tích sự cố của tenant cụ thể nhưng không được phép lưu tenant ID trực tiếp trên metrics, khiến thiết kế correlation giữa log và trace phải đáp ứng cả quyền riêng tư.
Một hệ thống có metric số retry tăng nhưng logs chỉ ghi lỗi cuối cùng, khiến đội không biết các lần thử trước đó là timeout, rate limit hay lỗi xác thực.
Một ứng dụng thấy error rate tăng sau khi bật fallback cache nhưng request vẫn trả 200, khiến chỉ số HTTP không biểu diễn rõ chất lượng dữ liệu thực tế.
Một nhóm theo dõi request duration của API nhưng quên tách thời gian serialization response rất lớn, khiến tối ưu database không cải thiện latency của khách hàng.
Một dịch vụ xử lý hàng loạt thông điệp nhưng chỉ có metric số message nhận, khiến bản tin thất bại rồi được phát lại bị tính như sự kiện mới và làm sai báo cáo throughput.
Một ứng dụng xuất metrics đầy đủ nhưng tất cả trace có service.name giống nhau, khiến cây trace nhiều service trở nên khó phân biệt điểm thực thi.
Một nhóm bật debug logging khi hệ thống lỗi nhưng collector bị quá tải và drop logs, khiến khoảng thời gian sự cố nghiêm trọng lại thiếu dấu vết đầy đủ nhất.
Một ứng dụng vẫn hoạt động khi collector tạm ngừng nhưng exporter giữ batch telemetry quá lâu, khiến memory tăng và tác động ngược đến hiệu năng nghiệp vụ.
Một hệ thống có alert tỷ lệ lỗi dựa trên metric lấy dữ liệu chậm, khiến đội trực nhận cảnh báo sau khi khách đã bị ảnh hưởng trong khoảng thời gian dài.
Một nhóm xây dashboard tổng số request và latency mà không tách theo route, khiến một endpoint ít dùng nhưng rất chậm bị che trong số liệu trung bình toàn API.
Một ứng dụng ghi đủ span của request và database nhưng không ghi trạng thái retry, khiến khi nhìn trace có nhiều span giống nhau đội không biết đó là gọi lặp hay thao tác song song.
Một nhóm tạo quy tắc alert dựa trên p95 nhưng chưa xét lưu lượng nhỏ, khiến một request rất chậm ở thời điểm ít traffic làm cảnh báo tăng giảm thất thường.
Một ứng dụng chạy nhiều instance có metric lỗi từ một node lỗi cấu hình, nhưng biểu đồ tổng hợp không gắn node khiến đội khó khoanh vùng bản triển khai bị hỏng.
Một dịch vụ sử dụng sampling thấp và không có request ID riêng trong log, khiến đội hỗ trợ không thể truy ra giao dịch cụ thể mà người dùng báo lỗi.
Một nhóm vận hành đổi collector mà không thử tương thích định dạng resource attributes, khiến các báo cáo theo vùng và service bị phân tách sau khi chuyển nền tảng.
Một ứng dụng xử lý thông tin y tế ghi mã bệnh án trong log, span và tag, khiến cùng dữ liệu nhạy cảm bị sao chép sang nhiều hệ thống quan sát có vòng đời lưu trữ khác nhau.
Một đội kiểm thử chỉ assert endpoint HTTP trả 200 nhưng không xác minh metric và trace, khiến một bản refactor làm mất toàn bộ instrumentation mà suite vẫn pass.
Một ứng dụng dùng MockMvc kiểm tra controller nhưng không có cấu hình ObservationRegistry như production, khiến kết quả test không phản ánh những span được tạo khi chạy thực tế.
Một nhóm viết test cho MeterRegistry trong bộ nhớ nhưng chỉ kiểm tra tên meter, khiến lỗi gắn tag sai trạng thái HTTP vẫn lọt qua kiểm thử.
Một hệ thống dùng StepVerifier để kiểm tra pipeline Reactor nhưng chưa xác minh context propagation sau publishOn, khiến production mất trace ID dù dữ liệu nghiệp vụ vẫn đúng.
Một bài test tracing dùng ID cố định cho mọi request và chạy tuần tự, khiến lỗi lẫn ngữ cảnh giữa các request đồng thời không được phát hiện.
Một ứng dụng mô phỏng collector luôn nhận dữ liệu thành công, khiến các lỗi mạng và chính sách retry của exporter chỉ bộc lộ khi triển khai production.
Một nhóm chạy test có sampler luôn giữ tất cả trace, nhưng môi trường production lấy mẫu thấp khiến đường link từ log sang trace không luôn có dữ liệu.
Một hệ thống kiểm thử phát thông điệp Kafka rồi nhận ở consumer, nhưng chỉ assert payload và không kiểm tra headers nên lỗi propagation context bị bỏ qua.
Một dịch vụ có bài test HTTP client với mock server nhưng client được tạo thủ công ngoài builder đã instrument, khiến thiếu outbound span mà không có assertion phát hiện.
Một nhóm kiểm thử Spring Boot Actuator với quyền quản trị nhưng không kiểm tra tài khoản thường, khiến endpoint metrics nhạy cảm bị expose ngoài chính sách cho phép.
Một ứng dụng chỉ benchmark latency khi không bật exporter, khiến chi phí thực thi quan sát dưới tải thật không được tính vào ngân sách hiệu năng.
Một bộ kiểm thử observability dùng số lượng span cố định làm điều kiện pass, khiến thay đổi instrumentation hợp lệ làm test báo lỗi dù quan hệ trace quan trọng vẫn đúng.
Một nhóm kiểm tra log correlation chỉ trên thread HTTP ban đầu, khiến mất MDC sau @Async không được nhận ra cho tới khi tác vụ nền thất bại thật.
Một dịch vụ thử tính cardinality với vài mã khách hàng cố định, khiến rủi ro hàng triệu series sau khi mở rộng người dùng không được cảnh báo trước deploy.
Một hệ thống xây tập dữ liệu chuẩn để phát hiện hồi quy latency nhưng không cố định phiên bản cấu hình histogram, khiến các phép đo trước và sau không còn so sánh trực tiếp.
Một ứng dụng tạo alert số lỗi trong CI nhưng không mô phỏng pod restart, khiến việc xử lý Counter reset sai dẫn đến cảnh báo âm hoặc mất tín hiệu ở production.
Một nhóm kiểm tra kết nối OTLP tới collector nhưng không xác minh telemetry được lưu và truy vấn trong backend, khiến mạng thông suốt vẫn bị coi nhầm là hệ thống quan sát hoạt động đầy đủ.
Một dịch vụ tính tỷ lệ lỗi bằng query metrics nhưng test không bao gồm trường hợp endpoint không có traffic, khiến cảnh báo hiển thị giá trị vô nghĩa khi mới deploy.
Một nhóm cải tiến dashboard theo phản hồi sự cố nhưng không giữ cách đối chiếu giữa trace, log và metric qua cùng deployment, khiến việc điều tra một giao dịch sau này khó tái hiện.
