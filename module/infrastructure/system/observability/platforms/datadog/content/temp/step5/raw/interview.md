Bạn mô tả Datadog giúp quan sát toàn bộ hạ tầng và ứng dụng qua những loại telemetry nào?
Bạn phân biệt mục đích sử dụng metrics, logs và APM traces khi điều tra một sự cố như thế nào?
Bạn xác định nhu cầu quan sát quan trọng nhất của một dịch vụ trước khi kết nối Datadog bằng cách nào?
Bạn chọn tín hiệu nào để giám sát độ sẵn sàng, độ trễ, tỷ lệ lỗi và tình trạng bão hòa của ứng dụng ra sao?
Bạn đánh giá lợi ích và giới hạn của việc dùng một nền tảng quan sát tập trung cho nhiều đội như thế nào?
Bạn mô tả luồng dữ liệu từ ứng dụng và máy chủ qua Datadog Agent đến các màn hình quan sát như thế nào?
Bạn phân biệt trách nhiệm của Agent, thư viện tracing và những integration do Datadog cung cấp ra sao?
Bạn xác định loại dữ liệu nào cần gửi liên tục và loại nào chỉ cần thu thập khi chẩn đoán sâu như thế nào?
Bạn thiết kế mô hình tổ chức dữ liệu Datadog cho nhiều môi trường và nhóm phát triển như thế nào?
Bạn xác định những yêu cầu về bảo mật, quyền riêng tư và chi phí trước khi bật thu thập telemetry ra sao?
Bạn đánh giá mức độ phụ thuộc vào một nhà cung cấp quan sát khi ứng dụng được instrument trực tiếp như thế nào?
Bạn lựa chọn cách tích hợp OpenTelemetry với Datadog theo khả năng tương thích và vận hành ra sao?
Bạn giải thích vì sao dashboard đẹp chưa đủ để chứng minh ứng dụng có khả năng quan sát tốt như thế nào?
Bạn xác định các chỉ tiêu đo thành công của việc triển khai Datadog trong một nhóm vận hành ra sao?
Bạn lên kế hoạch đưa Datadog vào hệ thống hiện có theo từng dịch vụ mà tránh mất tín hiệu quan trọng như thế nào?
Bạn xác định site và vùng nhận dữ liệu Datadog phù hợp với tổ chức trước khi cấu hình Agent như thế nào?
Bạn phân biệt API key dùng để nạp dữ liệu với application key dùng cho các thao tác API được cấp quyền ra sao?
Bạn bảo vệ các khóa tích hợp Datadog trong secret manager và pipeline triển khai như thế nào?
Bạn kiểm tra một Agent đã khởi động, được xác thực và gửi telemetry thành công bằng cách nào?
Bạn lựa chọn cách cài Datadog Agent trên máy ảo Linux, Windows hoặc máy chủ bare metal như thế nào?
Bạn giải thích tác dụng của cấu hình host identity khi nhiều máy cùng gửi dữ liệu về Datadog ra sao?
Bạn xác định nguyên nhân hai host khác nhau bị hiển thị như một host do trùng hostname bằng cách nào?
Bạn đánh giá ảnh hưởng của phiên bản Agent và phiên bản hệ điều hành tới khả năng thu thập như thế nào?
Bạn tổ chức cấu hình Agent theo môi trường mà tránh nhúng khóa bí mật vào repository ra sao?
Bạn kiểm tra trạng thái và lỗi cấu hình của Agent qua lệnh chẩn đoán hoặc log bằng cách nào?
Bạn phân biệt lỗi Agent không thu được dữ liệu với lỗi Agent có dữ liệu nhưng không gửi được về Datadog ra sao?
Bạn xác định kết nối outbound, DNS, proxy và TLS nào cần kiểm tra khi Agent không gửi được telemetry như thế nào?
Bạn thiết kế chính sách cập nhật Agent có thể rollback khi phiên bản mới gây thiếu metric như thế nào?
Bạn kiểm soát tài nguyên CPU, RAM và mạng tiêu thụ bởi Agent trên máy chủ nhỏ ra sao?
Bạn phân biệt các chỉ số hệ thống do Agent thu với custom metrics do ứng dụng tự gửi như thế nào?
Bạn xác định integration có sẵn nào phù hợp cho database, message broker hoặc web server trước khi viết collector riêng ra sao?
Bạn triển khai và kiểm chứng một integration check thu được các chỉ số quan trọng như thế nào?
Bạn kiểm tra vì sao integration đã bật nhưng không hiện metric theo tên mong đợi bằng cách nào?
Bạn đánh giá quyền truy cập tối thiểu mà Agent cần để đọc chỉ số của database hoặc service ra sao?
Bạn tổ chức kiểm thử thay đổi cấu hình integration trên staging trước khi áp dụng cho production như thế nào?
Bạn thu thập log và metric từ container có vòng đời ngắn mà vẫn gắn đúng thông tin service như thế nào?
Bạn lựa chọn cách triển khai Datadog Agent dạng DaemonSet trên Kubernetes dựa trên đặc điểm cluster ra sao?
Bạn phân biệt vai trò Agent trên node với những thành phần thu thập metadata cấp cluster của Datadog như thế nào?
Bạn kiểm tra quyền RBAC và khả năng phát hiện workload khi dữ liệu Kubernetes thiếu nhãn hoặc metric như thế nào?
Bạn xác định ảnh hưởng của node autoscaling và pod rescheduling đến việc nhận diện thực thể trên Datadog ra sao?
Bạn lựa chọn cách gắn tag Kubernetes cluster, namespace, workload và pod sao cho phục vụ lọc dữ liệu như thế nào?
Bạn kiểm tra trường hợp một pod đã bị xóa nhưng vẫn xuất hiện trong dữ liệu lịch sử như thế nào?
Bạn thiết kế thu thập telemetry từ ứng dụng chạy trên serverless hoặc dịch vụ managed theo giới hạn từng môi trường ra sao?
Bạn xác định khác biệt giữa theo dõi máy chủ và theo dõi container khi triển khai microservices như thế nào?
Bạn đánh giá khi nào cần bật thêm runtime metrics cho JVM để hiểu nguyên nhân hiệu năng ứng dụng ra sao?
Bạn tổ chức health check cho chính pipeline thu thập để không nhầm thiếu dữ liệu với dịch vụ khỏe mạnh như thế nào?
Bạn xác định dấu hiệu một Agent bị quá tải bởi lượng log tăng đột biến bằng cách nào?
Bạn lựa chọn các mức giảm dữ liệu tại Agent trước khi truyền lên Datadog để bảo vệ băng thông ra sao?
Bạn thiết kế quy trình bàn giao cấu hình Agent và integration khi ứng dụng chuyển sang đội vận hành khác như thế nào?
Bạn giải thích sự khác nhau giữa gauge, count, rate và distribution khi gửi metric lên Datadog như thế nào?
Bạn lựa chọn loại metric phù hợp để đo số request, số job đang chạy và thời lượng xử lý ra sao?
Bạn phân biệt metric hệ thống với business metric khi thiết kế bộ chỉ số theo dõi nghiệp vụ như thế nào?
Bạn xác định ý nghĩa của các phép aggregate theo thời gian và theo nhóm tag trong một truy vấn metric ra sao?
Bạn chọn sum, avg, min, max hoặc percentiles theo câu hỏi vận hành nào?
Bạn xây dựng truy vấn so sánh CPU, bộ nhớ và I/O giữa nhiều host thuộc cùng dịch vụ như thế nào?
Bạn nhận diện lý do trung bình CPU của cụm che giấu một instance đang quá tải ra sao?
Bạn tính tỷ lệ lỗi từ counter thành công và thất bại mà tránh nhầm giữa số tích lũy với tốc độ như thế nào?
Bạn kiểm tra dữ liệu metric có khoảng trống do mất kết nối Agent hay do không phát sinh sự kiện ra sao?
Bạn xác định khi nào cần dùng metric có interval thích hợp để tránh nhiễu trong biểu đồ ra sao?
Bạn phân biệt tốc độ thay đổi metric với giá trị hiện tại khi chọn truy vấn để tạo cảnh báo như thế nào?
Bạn đánh giá tác động của rollup và độ phân giải dữ liệu lịch sử tới việc xem lại một đợt lỗi ngắn ra sao?
Bạn sử dụng Metrics Explorer để xác định metric có tồn tại và những tag nào đang gắn với nó như thế nào?
Bạn kiểm tra tên metric và đơn vị đo khi dữ liệu do nhiều nhóm gửi lên không nhất quán ra sao?
Bạn thiết kế custom metric cho một chỉ số nghiệp vụ mà không tạo một chuỗi riêng cho mỗi giao dịch như thế nào?
Bạn phân tích tác động của số tổ hợp tag đến cardinality và chi phí custom metrics như thế nào?
Bạn lựa chọn các chiều tag cần giữ để có thể phân tích theo service, region hoặc tenant ra sao?
Bạn kiểm tra vì sao một metric xuất hiện trên host nhưng không xuất hiện khi lọc theo service như thế nào?
Bạn sử dụng tag filtering và group-by để tìm một khu vực gây lỗi mà không phải xem từng host ra sao?
Bạn phân biệt metric chưa được instrument với metric bị bỏ do cấu hình thu thập bằng cách nào?
Bạn xác định khi nào nên tổng hợp metric trước khi gửi nhằm giảm chi phí nhưng vẫn giữ khả năng điều tra ra sao?
Bạn lựa chọn metric distribution cho bài toán phân vị latency qua nhiều instance dựa trên yêu cầu nào?
Bạn phân biệt độ trễ p95 của từng host với p95 tổng thể của service khi đánh giá trải nghiệm người dùng như thế nào?
Bạn xác định tác động của sampling hoặc giới hạn thu thập đến sự tin cậy của metric nghiệp vụ ra sao?
Bạn kết hợp metric với sự kiện triển khai để xác định thời điểm chất lượng dịch vụ bắt đầu thay đổi như thế nào?
Bạn kiểm tra sai lệch đồng hồ hoặc tần suất gửi khi biểu đồ metric có điểm dữ liệu bất thường ra sao?
Bạn thiết kế dashboard theo dõi xu hướng dung lượng hoặc hàng đợi từ metric phù hợp như thế nào?
Bạn xác định những chỉ số saturation cần ưu tiên khi ứng dụng chậm nhưng CPU vẫn thấp ra sao?
Bạn lựa chọn nhãn env, service và version theo quy ước unified service tagging của Datadog như thế nào?
Bạn kiểm tra cùng một service bị tách thành nhiều tên trên Datadog do tag không nhất quán ra sao?
Bạn thiết kế chiến lược tag chung cho host, container, logs và traces để có thể tương quan dữ liệu như thế nào?
Bạn phân biệt tag gắn tại Agent với attribute do ứng dụng gửi theo từng telemetry event ra sao?
Bạn xác định những tag nào có thể thay đổi thường xuyên và có nguy cơ làm tăng cardinality ra sao?
Bạn đánh giá rủi ro gắn user ID, session ID hoặc URL đầy đủ vào mọi metric như thế nào?
Bạn kiểm soát quy ước tag theo team, cost center và environment để hỗ trợ phân bổ trách nhiệm ra sao?
Bạn tổ chức kiểm tra chất lượng tag trong CI/CD hoặc khi nhận bàn giao dịch vụ như thế nào?
Bạn xử lý việc đổi tên service khi các dashboard và monitor cũ vẫn tham chiếu tên trước đó như thế nào?
Bạn xác định mức độ chi tiết tag tối thiểu để phục vụ điều tra đa vùng nhưng không tạo chi phí quá lớn như thế nào?
Bạn mô tả luồng thu thập log từ ứng dụng qua Agent hoặc pipeline đến hệ thống tìm kiếm Datadog như thế nào?
Bạn lựa chọn phương án thu log từ file, stdout container hoặc tích hợp cloud theo điều kiện vận hành ra sao?
Bạn thiết kế structured logging để các trường thời gian, severity, service và request ID có thể tìm kiếm như thế nào?
Bạn xác định các bước parsing log văn bản để trích xuất status code, endpoint và thời lượng ra sao?
Bạn kiểm tra một log pipeline có parse timestamp chính xác trong các múi giờ khác nhau bằng cách nào?
Bạn phân biệt log ingestion với log indexing và ảnh hưởng của từng bước lên khả năng tìm kiếm ra sao?
Bạn lựa chọn log nào cần được index để phục vụ điều tra thường xuyên và log nào chỉ cần lưu trữ dài hạn như thế nào?
Bạn thiết kế exclusion filter dựa trên giá trị điều tra mà tránh loại mất những log lỗi hiếm gặp ra sao?
Bạn đánh giá rủi ro sampling log truy cập khiến không thể tái hiện một giao dịch cụ thể như thế nào?
Bạn kiểm tra vì sao Agent thu được log nhưng log không xuất hiện trong kết quả tìm kiếm đã lọc ra sao?
Bạn sử dụng Live Tail và tìm kiếm log lịch sử cho những mục tiêu điều tra khác nhau như thế nào?
Bạn lựa chọn các facet và measure từ log attribute để hỗ trợ phân tích nhanh như thế nào?
Bạn xây dựng truy vấn tìm tất cả log ERROR của một service trong khoảng thời gian triển khai ra sao?
Bạn lọc log theo trace ID, host, pod và version để khoanh vùng sự cố như thế nào?
Bạn kiểm tra nguyên nhân trường severity không được chuẩn hóa nên log lỗi không nằm trong bộ lọc mong đợi ra sao?
Bạn thiết kế log pipeline để biến đổi trường nhạy cảm trước khi dữ liệu được lưu hoặc index như thế nào?
Bạn xác định dữ liệu nào phải redaction như token, mật khẩu, email hoặc số định danh trước khi đưa lên Datadog ra sao?
Bạn tổ chức retention theo mức độ quan trọng của log và yêu cầu tuân thủ như thế nào?
Bạn đánh giá khả năng lưu trữ, khôi phục hoặc truy vấn lại log cũ theo gói tính năng đang sử dụng ra sao?
Bạn phát hiện log tăng đột biến do vòng lặp retry hoặc thay đổi mức log bằng những chỉ số nào?
Bạn thiết kế cảnh báo dựa trên số lượng log lỗi mà tránh bị nhiễu khi lưu lượng tổng tăng mạnh ra sao?
Bạn phân biệt log không xuất hiện do ứng dụng không ghi với log bị chặn trong pipeline bằng cách nào?
Bạn kiểm tra log duplication khi cùng một container được thu bởi nhiều agent hoặc nhiều nguồn như thế nào?
Bạn sử dụng pattern hoặc grouping của log để tìm lỗi mới xuất hiện sau một release ra sao?
Bạn xây dựng quy trình điều tra một lỗi 500 từ log proxy đến log ứng dụng và database như thế nào?
Bạn đánh giá vì sao một thông báo lỗi trong log chưa đủ để kết luận nguyên nhân gốc ra sao?
Bạn kết hợp log với chỉ số CPU, memory hoặc queue depth để bác bỏ giả thuyết quá tải như thế nào?
Bạn xác định các trường correlation cần có để liên kết logs với APM traces ra sao?
Bạn thiết kế log pipeline hỗ trợ nhiều ngôn ngữ ứng dụng mà vẫn thống nhất các trường chính như thế nào?
Bạn phân tích trường hợp log có timestamp đúng nhưng xuất hiện trễ nhiều phút so với thời điểm sự kiện như thế nào?
Bạn chọn ngưỡng và mức lấy mẫu log để vừa giữ khả năng xử lý sự cố vừa kiểm soát chi phí như thế nào?
Bạn giải thích APM của Datadog mô hình hóa service, trace và span để theo dõi một request như thế nào?
Bạn xác định các service cần đưa vào APM trước tiên từ kiến trúc phụ thuộc ứng dụng ra sao?
Bạn lựa chọn thư viện tracing hoặc auto-instrumentation thích hợp cho Java/Spring Boot theo khả năng phiên bản như thế nào?
Bạn cấu hình tên service, environment và version trong tracer để liên kết deployment với trace ra sao?
Bạn kiểm tra một ứng dụng đã bật APM nhưng không xuất hiện trên trang service của Datadog bằng cách nào?
Bạn phân biệt lỗi tracer không khởi tạo với lỗi Agent không nhận hoặc không gửi trace như thế nào?
Bạn mô tả cách trace context được truyền khi một request HTTP đi qua nhiều dịch vụ ra sao?
Bạn kiểm tra một downstream service tạo trace mới thay vì nối vào trace upstream bằng những dấu hiệu nào?
Bạn lựa chọn định dạng propagation tương thích khi hệ thống kết hợp Datadog tracer với OpenTelemetry như thế nào?
Bạn kiểm tra trace bị đứt khi đi qua message broker hoặc tác vụ bất đồng bộ như thế nào?
Bạn giải thích sự khác nhau giữa root span, child span và service entry span qua một request ra sao?
Bạn xác định span nào đang đóng góp nhiều nhất vào latency end-to-end bằng cách đọc waterfall view như thế nào?
Bạn phân biệt thời gian thực thi bên trong service với thời gian chờ một dịch vụ downstream như thế nào?
Bạn xác định nguyên nhân thời lượng trace tăng do nhiều lời gọi nối tiếp hoặc retry qua các span ra sao?
Bạn phân tích trường hợp trace có những khoảng trống không được instrument trong luồng xử lý như thế nào?
Bạn tạo custom span cho một bước nghiệp vụ quan trọng mà tránh trùng lặp với auto-instrumentation ra sao?
Bạn lựa chọn span tag mô tả truy vấn hoặc endpoint nhưng không chứa dữ liệu nhạy cảm như thế nào?
Bạn đánh giá nguy cơ gắn tham số URL động hoặc order ID vào resource name của span như thế nào?
Bạn phân biệt trace sampling, ingestion và retention khi giải thích vì sao một trace không còn tìm thấy ra sao?
Bạn xác định chính sách giữ trace lỗi hoặc trace chậm phù hợp trong giới hạn lưu trữ và chi phí như thế nào?
Bạn kiểm tra vì sao trace lỗi hiếm gặp không được tìm thấy dù service còn phát metric lỗi như thế nào?
Bạn giải thích tại sao APM trace metrics vẫn có thể phản ánh lưu lượng khác với số trace được giữ để tìm kiếm ra sao?
Bạn lựa chọn chỉ số request rate, error rate và latency trên màn hình APM Service theo mục tiêu nào?
Bạn phân tích tài nguyên service nào có p99 latency xấu nhưng p50 vẫn bình thường như thế nào?
Bạn xác định cách xem phụ thuộc giữa service và database qua service map hoặc trace graph ra sao?
Bạn kiểm tra vì sao một service được hiển thị thành nhiều node do cấu hình tên không nhất quán như thế nào?
Bạn truy vấn các trace thuộc một phiên bản triển khai cụ thể để kiểm tra hồi quy hiệu năng như thế nào?
Bạn sử dụng trace search hoặc trace analytics để tìm request có thời gian xử lý bất thường ra sao?
Bạn so sánh trace của request thành công và thất bại để xác định bước xử lý khác biệt như thế nào?
Bạn phân tích lỗi database trong APM khi thời gian query tăng nhưng network latency ổn định ra sao?
Bạn phân biệt thời gian chờ connection pool với thời gian thực thi truy vấn database bằng những tín hiệu nào?
Bạn xác định khi nào cần kết hợp APM với database monitoring thay vì suy đoán nguyên nhân từ span SQL ra sao?
Bạn kiểm tra APM instrumentation có tăng độ trễ hoặc CPU ứng dụng bằng cách đo trước và sau như thế nào?
Bạn thiết kế phương án tắt tạm một loại instrumentation gây overhead mà vẫn giữ trace cốt lõi ra sao?
Bạn kiểm tra trace liên tục thiếu một service khi chỉ một nhóm instance sử dụng phiên bản Agent cũ như thế nào?
Bạn xác định cách phân biệt sự cố thực tế với lỗi lệch đồng hồ giữa host khi waterfall hiển thị thứ tự bất thường ra sao?
Bạn đánh giá khả năng dùng Error Tracking hoặc nhóm lỗi APM để ưu tiên vấn đề mới phát sinh như thế nào?
Bạn thiết kế quy trình chuyển từ cảnh báo latency tới một trace cụ thể và log liên quan như thế nào?
Bạn xác định khi nào cần thêm Continuous Profiler hoặc công cụ profiler tương đương để tìm điểm nóng CPU ra sao?
Bạn phân biệt một span dài do logic nghiệp vụ với span dài do chờ lock hoặc downstream như thế nào?
Bạn kiểm tra việc ghi nhận exception trong APM có đủ message và stack trace mà không lộ dữ liệu riêng tư như thế nào?
Bạn lựa chọn cách xác minh một bản sửa lỗi bằng so sánh APM trước và sau triển khai như thế nào?
Bạn thiết kế trang tổng quan liên kết số liệu host, container, APM và log của cùng một service ra sao?
Bạn giải thích cách unified service tagging hỗ trợ chuyển giữa metrics, logs và traces trong cùng một luồng điều tra như thế nào?
Bạn kiểm tra vì sao log của một request có trace ID nhưng Datadog không mở được trace tương ứng ra sao?
Bạn xác định các điều kiện instrumentation để log correlation tự động hoạt động trong ứng dụng Java như thế nào?
Bạn thiết kế quy ước correlation ID khi một nghiệp vụ kéo dài vượt quá vòng đời một trace riêng lẻ như thế nào?
Bạn phân biệt mã request của ứng dụng với trace ID để tránh dùng một định danh cho sai mục đích ra sao?
Bạn so sánh tín hiệu từ RUM hoặc synthetic test với APM để xác định độ trễ nằm phía client hay server như thế nào?
Bạn lựa chọn khi nào cần một synthetic check để bổ sung cho metric chỉ được tạo khi có người dùng thực ra sao?
Bạn xác định lý do synthetic probe thất bại ở một khu vực dù APM của backend vẫn bình thường như thế nào?
Bạn đánh giá những phần của luồng người dùng chưa được quan sát nếu chỉ triển khai Agent tại backend ra sao?
Bạn thiết kế truy vấn liên kết lỗi 5xx ở gateway với trace và log của backend để chứng minh nguyên nhân như thế nào?
Bạn xây dựng phương pháp so sánh tỷ lệ lỗi trước và sau một deployment dùng event marker và service version ra sao?
Bạn xác định khi nào tag sai làm các tín hiệu của cùng một service bị phân tán thành nhiều nhóm như thế nào?
Bạn tổ chức một phiên điều tra sự cố bắt đầu từ monitor rồi đi đến dashboard, trace và log bằng cách nào?
Bạn chọn widget time series, toplist, query value hoặc heatmap cho những câu hỏi quan sát khác nhau như thế nào?
Bạn thiết kế dashboard cho một service theo RED metrics và các dependency chính ra sao?
Bạn xây dựng dashboard hạ tầng theo USE metrics để phát hiện giới hạn tài nguyên như thế nào?
Bạn lựa chọn thứ tự hiển thị các widget để người trực nhanh chóng nhận diện ảnh hưởng người dùng ra sao?
Bạn dùng template variables để chuyển dashboard giữa environment, region hoặc service như thế nào?
Bạn kiểm tra một widget không có dữ liệu khi đổi template variable do tag mismatch bằng cách nào?
Bạn phân biệt dashboard phục vụ trực ca với dashboard phục vụ capacity planning theo nội dung và thời gian hiển thị ra sao?
Bạn xây dựng một dashboard nhiều tầng từ chỉ tiêu tổng thể xuống host hoặc endpoint gây lỗi như thế nào?
Bạn lựa chọn thang đo, đơn vị và rollup cho biểu đồ để tránh diễn giải sai xu hướng như thế nào?
Bạn xác định vì sao hai widget dùng cùng metric nhưng trả kết quả khác nhau do phép tổng hợp ra sao?
Bạn thêm deploy event hoặc annotation vào dashboard để liên kết chỉ số suy giảm với thay đổi hệ thống như thế nào?
Bạn tổ chức quyền chỉnh sửa dashboard để tránh một thay đổi vô tình ảnh hưởng cả đội vận hành ra sao?
Bạn quản lý dashboard dưới dạng cấu hình có version và review trước khi áp dụng bằng cách nào?
Bạn thiết kế dashboard theo team ownership mà vẫn cho phép nhóm khác dễ dàng tái sử dụng như thế nào?
Bạn quyết định khi nào nên dùng notebook điều tra sự cố thay vì chỉnh sửa dashboard cố định ra sao?
Bạn xây dựng một câu chuyện điều tra từ log, trace và biểu đồ trong một tài liệu sự cố như thế nào?
Bạn đo mức hữu ích của dashboard bằng thời gian phát hiện và xác nhận nguyên nhân sự cố như thế nào?
Bạn xác định dashboard không cần cảnh báo riêng khi nào và tín hiệu nào phải chuyển thành monitor ra sao?
Bạn thiết kế monitor dựa trên metric threshold để phát hiện tình trạng ảnh hưởng người dùng như thế nào?
Bạn phân biệt monitor metric, log, APM hoặc composite theo loại tín hiệu và mục tiêu xử lý ra sao?
Bạn lựa chọn ngưỡng cảnh báo từ baseline thực tế thay vì một con số tùy ý như thế nào?
Bạn xác định thời gian evaluation window phù hợp khi traffic biến động mạnh theo giờ ra sao?
Bạn phân biệt alert khi vượt ngưỡng tức thời với alert yêu cầu sự cố kéo dài trong một khoảng thời gian như thế nào?
Bạn kiểm tra ảnh hưởng của các tùy chọn yêu cầu đủ dữ liệu trong cửa sổ đánh giá đến cảnh báo ra sao?
Bạn thiết kế no-data alert cho một host hoặc service mà không nhầm với workload không có traffic như thế nào?
Bạn phân biệt trạng thái No Data với trạng thái OK khi một metric không còn được gửi lên ra sao?
Bạn thiết kế monitor cho các host mới vừa khởi tạo để tránh alert giả trong giai đoạn warm-up như thế nào?
Bạn giải thích tác động của evaluation delay khi telemetry gửi trễ từ cloud integration như thế nào?
Bạn xác định khi nào cần cảnh báo dựa trên anomaly hoặc outlier thay cho static threshold như thế nào?
Bạn kiểm tra một thuật toán phát hiện bất thường có phù hợp với traffic có tính mùa vụ bằng cách nào?
Bạn lựa chọn forecast monitor khi muốn dự báo hết dung lượng trong một khoảng thời gian vận hành ra sao?
Bạn phân biệt monitor theo từng nhóm tag với monitor tổng hợp toàn service khi cần xác định phạm vi ảnh hưởng như thế nào?
Bạn đánh giá nguy cơ tạo quá nhiều alert instance khi group by một tag có cardinality cao ra sao?
Bạn thiết kế message của monitor có triệu chứng, phạm vi, dashboard và runbook liên quan như thế nào?
Bạn gán severity, team ownership và môi trường vào monitor để phân tuyến người nhận như thế nào?
Bạn tổ chức thông báo qua email, chat hoặc hệ thống on-call để không gửi trùng nhiều kênh ngoài ý muốn ra sao?
Bạn lựa chọn thời điểm gửi nhắc lại khi monitor chưa được xử lý nhưng tránh tạo alert fatigue như thế nào?
Bạn phân biệt downtime hoặc mute có kế hoạch với việc xóa bỏ hẳn một monitor không còn cần thiết như thế nào?
Bạn xây dựng quy trình đặt downtime trong lúc triển khai nhưng không che các sự cố ngoài phạm vi như thế nào?
Bạn thiết kế composite monitor để kết hợp tín hiệu phụ trợ và giảm cảnh báo không thể hành động ra sao?
Bạn đánh giá vì sao một composite monitor có thể bỏ sót sự cố nếu điều kiện phụ trợ không còn dữ liệu như thế nào?
Bạn kiểm tra một monitor chuyển trạng thái bất thường do thay đổi tag hoặc mất nguồn metric như thế nào?
Bạn phân tích lý do monitor firing liên tục gần ngưỡng và quyết định điều chỉnh hysteresis hoặc thời gian đánh giá ra sao?
Bạn thiết kế monitor về tỷ lệ lỗi có điều kiện lưu lượng tối thiểu để tránh nhiễu ở endpoint ít truy cập như thế nào?
Bạn xác định khi nào một alert cần đánh thức người trực và khi nào chỉ nên tạo ticket để xử lý sau ra sao?
Bạn đánh giá chất lượng bộ monitor qua false positive, false negative và số lần có hành động xử lý như thế nào?
Bạn tổ chức kiểm thử monitor trên dữ liệu lịch sử hoặc môi trường thử nghiệm trước khi bật cảnh báo production như thế nào?
Bạn xác định ảnh hưởng của lỗi kết nối nguồn telemetry lên trạng thái monitor và cách phát hiện điểm mù ra sao?
Bạn lập runbook cho tình huống monitor báo độ trễ cao nhưng các metrics hạ tầng vẫn trong ngưỡng như thế nào?
Bạn thiết kế SLI availability hoặc latency từ dữ liệu request phù hợp với phạm vi trách nhiệm của dịch vụ như thế nào?
Bạn chuyển cam kết SLO thành một monitor dựa trên tốc độ tiêu thụ error budget như thế nào?
Bạn phân biệt giám sát giá trị SLI hiện tại với giám sát error budget burn rate theo mức độ khẩn cấp ra sao?
Bạn lựa chọn cửa sổ ngắn và dài để phát hiện cả sự cố nghiêm trọng lẫn suy giảm kéo dài như thế nào?
Bạn kiểm tra tính đúng đắn của tử số và mẫu số trong SLI khi một số request bị loại khỏi phạm vi như thế nào?
Bạn đánh giá hạn chế của SLO dựa trên dữ liệu có sampling hoặc thiếu metric như thế nào?
Bạn tổ chức dashboard SLO theo service và environment để không trộn production với staging ra sao?
Bạn xác định khi nào giảm tốc độ release dựa trên error budget mà vẫn xét các yếu tố nghiệp vụ ra sao?
Bạn phân biệt SLO theo metric và SLO theo monitor để chọn mô hình phù hợp như thế nào?
Bạn thiết kế cảnh báo theo nhóm người dùng hoặc region khi SLO tổng thể có thể che mất sự cố cục bộ ra sao?
Bạn kiểm tra tính nhất quán giữa SLO hiển thị và cảnh báo đang gửi tới người trực bằng cách nào?
Bạn đánh giá việc thay đổi định nghĩa SLO giữa kỳ ảnh hưởng tới khả năng so sánh lịch sử như thế nào?
Bạn xác định các yếu tố chi phối chi phí Datadog theo host, custom metrics, log ingestion và index, APM hoặc sản phẩm khác ra sao?
Bạn phân biệt chi phí thu thập log với chi phí index và lưu giữ log khi tối ưu ngân sách như thế nào?
Bạn kiểm tra usage hoặc billing dashboard để phát hiện nguồn phát sinh chi phí tăng đột biến bằng cách nào?
Bạn xác định nhóm tag nào làm tăng mạnh cardinality của custom metrics trước khi bật thêm instrumentation ra sao?
Bạn lựa chọn giữ, giảm hoặc loại bỏ các dimensions của metric dựa trên giá trị điều tra như thế nào?
Bạn đánh giá các cơ chế kiểm soát cardinality hoặc volume của metrics theo gói dịch vụ đang dùng ra sao?
Bạn quyết định mức retention và exclusion filter của logs dựa trên yêu cầu điều tra và tuân thủ như thế nào?
Bạn xác định dịch vụ nào đang phát log quá chi tiết trong giờ cao điểm và cách giảm tải ra sao?
Bạn cân bằng trace sampling với nhu cầu tìm request lỗi hiếm gặp và chi phí APM như thế nào?
Bạn kiểm tra sự khác nhau giữa số trace ingest và số trace có thể tìm kiếm lại khi xem usage ra sao?
Bạn xác định các monitor, dashboard hoặc integration không còn sử dụng để giảm công sức bảo trì như thế nào?
Bạn thiết kế ngân sách quan sát theo team hoặc service để người sở hữu hiểu chi phí telemetry ra sao?
Bạn đánh giá tác động của bật thêm RUM, Synthetics hoặc Profiling đến tổng chi phí bằng cách nào?
Bạn tổ chức thí nghiệm giảm telemetry volume để đo phần chi phí tiết kiệm và phần khả năng chẩn đoán mất đi ra sao?
Bạn thiết kế quy trình theo dõi chi phí sau mỗi release lớn để phát hiện logging hoặc tagging bất thường như thế nào?
Bạn xác định dữ liệu cần được che giấu trước khi gửi vào Datadog theo yêu cầu bảo vệ thông tin như thế nào?
Bạn quản lý quyền xem log và trace chứa nội dung nhạy cảm theo vai trò người dùng như thế nào?
Bạn phân biệt API key, application key và quyền người dùng khi cấp quyền tích hợp automation ra sao?
Bạn tổ chức vòng đời tạo, xoay vòng và thu hồi khóa Datadog mà không làm gián đoạn thu thập như thế nào?
Bạn xác định nguy cơ rò dữ liệu qua tag, URL, SQL statement hoặc span metadata bằng những kiểm tra nào?
Bạn thiết kế chính sách phân quyền dashboard, monitor và công cụ quản trị cho các đội khác nhau ra sao?
Bạn kiểm tra các thay đổi cấu hình quan trọng trong audit trail hoặc cơ chế ghi nhận tương đương như thế nào?
Bạn đánh giá yêu cầu lưu trữ và vị trí xử lý dữ liệu trước khi chọn Datadog site cho tổ chức ra sao?
Bạn thiết kế kiểm soát truy cập tổ chức qua SSO và các vai trò phù hợp với nhu cầu vận hành như thế nào?
Bạn lập chính sách chỉ sử dụng dữ liệu giả lập khi thử nghiệm pipeline log chứa thông tin khách hàng như thế nào?
Bạn quản lý dashboard và monitor qua API hoặc Infrastructure as Code để bảo đảm thay đổi có thể review như thế nào?
Bạn kiểm tra một cấu hình Datadog được tạo tự động có idempotent khi triển khai lại hay không ra sao?
Bạn thiết kế pipeline CI/CD kiểm tra cú pháp, quyền và phạm vi ảnh hưởng trước khi thay đổi monitor như thế nào?
Bạn xác định cách đồng bộ dashboard và monitor giữa staging và production mà không nhầm thẻ môi trường như thế nào?
Bạn tổ chức kiểm thử một monitor mới qua nhóm nhỏ trước khi mở thông báo cho đội trực ra sao?
Bạn xây dựng phương án rollback khi thay đổi monitor gây ra hàng loạt cảnh báo giả như thế nào?
Bạn quản lý lịch sử và người phê duyệt thay đổi retention, sampling hoặc tag pipeline như thế nào?
Bạn thiết kế quy trình kiểm tra sau triển khai để xác minh telemetry của phiên bản ứng dụng mới vẫn đầy đủ ra sao?
Bạn xác định tín hiệu nào chứng minh một integration bị mất dữ liệu sau khi cập nhật Agent như thế nào?
Bạn thiết kế ứng phó khi Datadog không nhận telemetry tạm thời mà các dịch vụ production vẫn hoạt động như thế nào?
Bạn phân biệt sự cố của nền tảng quan sát với sự cố thực sự của ứng dụng bằng những nguồn độc lập nào?
Bạn điều tra tình huống dashboard không còn metric sau deploy nhưng người dùng vẫn truy cập thành công như thế nào?
Bạn xác định nguyên nhân log xuất hiện trong Live Tail nhưng không có trong kết quả tìm kiếm lịch sử ra sao?
Bạn phân tích trường hợp APM báo tỷ lệ lỗi tăng nhưng log ERROR không tăng tương ứng bằng cách nào?
Bạn xử lý một đợt tăng p99 latency bằng cách tìm endpoint, version và dependency có ảnh hưởng lớn nhất như thế nào?
Bạn so sánh một trace nhanh và một trace chậm cùng endpoint để xác định điểm nghẽn như thế nào?
Bạn xác định request bị mất trace context khi đi qua hàng đợi hoặc callback bất đồng bộ như thế nào?
Bạn kiểm tra nguyên nhân một monitor báo No Data do Agent mất kết nối thay vì dịch vụ dừng như thế nào?
Bạn xây dựng timeline từ deploy event, metric, log và APM trace cho một sự cố production ra sao?
Bạn thiết kế quy trình điều tra khi chỉ một region có lỗi 5xx mà dashboard tổng thể vẫn khỏe như thế nào?
Bạn xác định lúc nào nên kiểm tra synthetic probe hoặc trải nghiệm phía người dùng thay vì chỉ dựa trên backend APM ra sao?
Bạn đánh giá rủi ro chỉnh sửa monitor trong lúc sự cố đang diễn ra và cách ghi nhận thay đổi như thế nào?
Bạn tổ chức postmortem dựa trên dữ liệu Datadog để chuyển kết quả điều tra thành hành động phòng ngừa ra sao?
Bạn xác định bộ tiêu chí nghiệm thu Datadog dựa trên độ bao phủ telemetry, khả năng tương quan, thời gian phát hiện, chi phí và bảo mật như thế nào?
