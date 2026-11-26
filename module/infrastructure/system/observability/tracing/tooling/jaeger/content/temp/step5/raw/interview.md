Bạn sẽ giải thích tracing phân tán giúp giải quyết những câu hỏi vận hành nào mà metrics và logs riêng lẻ khó trả lời?
Bạn sẽ mô tả một trace, span, parent span và trace context qua ví dụ request đi qua nhiều microservice như thế nào?
Bạn sẽ phân biệt trace ID, span ID và parent span ID trong quá trình liên kết các bước xử lý ra sao?
Bạn sẽ giải thích quan hệ giữa thời gian bắt đầu, thời lượng và thứ tự span khi nhiều service xử lý song song như thế nào?
Bạn sẽ phân biệt span event, span attribute và span link theo mục đích mô tả hoạt động ra sao?
Bạn sẽ xác định khi nào nên tạo span con và khi nào nên dùng span link cho tác vụ bất đồng bộ như thế nào?
Bạn sẽ giải thích resource attributes và instrumentation scope giúp nhận diện nguồn phát trace ra sao?
Bạn sẽ phân biệt service name, operation name và span name khi tổ chức dữ liệu tracing như thế nào?
Bạn sẽ lựa chọn những thuộc tính cần ghi cho một span HTTP mà không làm tăng chi phí hoặc lộ dữ liệu nhạy cảm ra sao?
Bạn sẽ phân biệt trạng thái span error với HTTP status code và exception event trong quá trình phân tích lỗi như thế nào?
Bạn sẽ giải thích context propagation qua HTTP, gRPC và message broker ảnh hưởng đến tính liên tục của trace ra sao?
Bạn sẽ kiểm tra vì sao trace bị tách thành nhiều phần khi một service không truyền tiếp trace context như thế nào?
Bạn sẽ xác định tác động của clock skew giữa các host đến việc diễn giải thứ tự và thời lượng span ra sao?
Bạn sẽ phân tích một trace có nhiều nhánh song song để tìm critical path gây chậm request như thế nào?
Bạn sẽ phân biệt tổng thời lượng trace với tổng các span duration khi các lời gọi diễn ra đồng thời ra sao?
Bạn sẽ lựa chọn mức độ instrumentation cho một hệ thống nhiều service để cân bằng khả năng quan sát và overhead như thế nào?
Bạn sẽ xác định những luồng nghiệp vụ nào cần trace end-to-end trước khi triển khai Jaeger ra sao?
Bạn sẽ thiết kế quy ước tên service và operation nhất quán giữa các nhóm phát triển như thế nào?
Bạn sẽ xác định các SLI về độ trễ và tỷ lệ lỗi có thể được hỗ trợ bởi dữ liệu trace ra sao?
Bạn sẽ giải thích Jaeger v2 đảm nhiệm vai trò gì trong kiến trúc observability dựa trên OpenTelemetry như thế nào?
Bạn sẽ phân biệt Jaeger với OpenTelemetry SDK và OpenTelemetry Collector về trách nhiệm thu thập, xử lý và truy vấn trace ra sao?
Bạn sẽ mô tả kiến trúc Jaeger v2 dựa trên các thành phần pipeline kiểu OpenTelemetry Collector như thế nào?
Bạn sẽ phân biệt receiver, processor, exporter và extension trong pipeline Jaeger v2 theo vai trò xử lý ra sao?
Bạn sẽ mô tả luồng trace từ ứng dụng qua OTLP receiver, các processor và exporter đến storage như thế nào?
Bạn sẽ xác định receiver, processor, exporter và cấu hình storage nào cần có để pipeline Jaeger v2 tiếp nhận và lưu trace?
Bạn sẽ kiểm tra pipeline traces đã liên kết đúng OTLP receiver, các processor và đích lưu trữ như thế nào?
Bạn sẽ lựa chọn cách chia pipeline theo nguồn dữ liệu, môi trường hoặc mức tin cậy để cô lập xử lý như thế nào?
Bạn sẽ thiết kế một pipeline có nhiều receiver nhưng cùng dùng processor và exporter mà vẫn tránh cấu hình trùng lặp ra sao?
Bạn sẽ xác định khi nào cần nhiều pipeline traces riêng thay vì dồn mọi nguồn vào một pipeline chung như thế nào?
Bạn sẽ kiểm tra tham chiếu component không tồn tại hoặc component không được đưa vào pipeline bằng cách nào?
Bạn sẽ xác minh cấu hình Jaeger v2 hợp lệ trước khi triển khai bằng công cụ và quy trình nào?
Bạn sẽ phân tích tác động khi một processor được dùng chung bởi nhiều pipeline có yêu cầu xử lý khác nhau ra sao?
Bạn sẽ tổ chức extension cho health check, telemetry nội bộ hoặc quản lý cấu hình trong Jaeger v2 như thế nào?
Bạn sẽ lựa chọn cách nạp cấu hình và quản lý biến môi trường để không để lộ thông tin xác thực ra sao?
Bạn sẽ thiết kế quy trình thay đổi cấu hình pipeline có kiểm thử, canary và rollback như thế nào?
Bạn sẽ xác định những khác biệt kiến trúc cần lưu ý khi chuyển từ Jaeger v1 sang Jaeger v2 ra sao?
Bạn sẽ lập kế hoạch migration từ hệ thống Jaeger cũ sang Jaeger v2 để không mất khả năng nhận trace trong thời gian chuyển đổi như thế nào?
Bạn sẽ đánh giá khả năng tương thích giữa phiên bản Jaeger v2, OpenTelemetry Collector components và storage backend bằng tiêu chí nào?
Bạn sẽ xử lý trường hợp một component từng có trong bản cũ không còn được hỗ trợ trong cấu hình mới như thế nào?
Bạn sẽ xây dựng bộ kiểm tra hồi quy cho cấu hình pipeline, giao thức OTLP và hành vi lưu trữ khi nâng cấp Jaeger v2 như thế nào?
Bạn sẽ mô tả quá trình ứng dụng gửi trace đến Jaeger v2 qua OTLP gRPC hoặc OTLP HTTP như thế nào?
Bạn sẽ phân biệt endpoint OTLP gRPC và OTLP HTTP về cổng, transport và cách cấu hình client ra sao?
Bạn sẽ xác định cách kiểm tra ứng dụng đang gửi trace đúng endpoint, protocol và encoding như thế nào?
Bạn sẽ phân tích lỗi kết nối khi ứng dụng dùng OTLP gRPC nhưng receiver chỉ được cấu hình cho HTTP ra sao?
Bạn sẽ kiểm tra TLS, certificate và authentication khi ứng dụng ngoài cluster gửi trace đến Jaeger v2 như thế nào?
Bạn sẽ lựa chọn mTLS cho luồng OTLP giữa các workload theo ranh giới tin cậy nào?
Bạn sẽ thiết kế receiver chỉ chấp nhận trace từ workload được phép thay vì mở endpoint OTLP công khai ra sao?
Bạn sẽ phân biệt lỗi DNS, TCP connect, TLS handshake và lỗi OTLP response khi trace không đến Jaeger như thế nào?
Bạn sẽ kiểm tra giới hạn kích thước request và batch khi ứng dụng gửi nhiều span trong một lần export ra sao?
Bạn sẽ xác định tác động của exporter timeout và retry trong SDK đến nguy cơ mất hoặc gửi trùng span như thế nào?
Bạn sẽ lựa chọn batch processor và timeout phù hợp với lưu lượng trace và mục tiêu độ trễ ingest ra sao?
Bạn sẽ thiết kế memory limiter hoặc cơ chế điều tiết để bảo vệ Jaeger v2 khi trace tăng đột biến như thế nào?
Bạn sẽ kiểm tra dấu hiệu receiver từ chối dữ liệu do quá tải bằng metric và log nào?
Bạn sẽ phân biệt số span ứng dụng tạo ra với số span Jaeger v2 thực sự nhận và lưu được như thế nào?
Bạn sẽ lựa chọn cách xử lý resource attributes để chuẩn hóa service.name và deployment.environment trước khi lưu ra sao?
Bạn sẽ xác định cách lọc span hoặc attributes không cần thiết mà không làm mất bằng chứng điều tra như thế nào?
Bạn sẽ thiết kế pipeline tách trace theo tenant hoặc môi trường để tránh ghi nhầm dữ liệu giữa các nhóm ra sao?
Bạn sẽ xử lý trace đến từ nhiều SDK với semantic conventions hoặc tên thuộc tính khác nhau như thế nào?
Bạn sẽ xác định cách chuyển tiếp OTLP đến nhiều backend mà vẫn kiểm soát quyền chia sẻ dữ liệu ra sao?
Bạn sẽ giải thích vai trò của storage backend trong Jaeger v2 và các yêu cầu về ghi, truy vấn và lưu giữ trace như thế nào?
Bạn sẽ lựa chọn storage backend cho Jaeger v2 dựa trên ingest rate, query workload, retention và năng lực vận hành ra sao?
Bạn sẽ phân biệt storage phục vụ truy vấn trace gần đây với kho lưu trữ dài hạn khi thiết kế kiến trúc như thế nào?
Bạn sẽ ước tính dung lượng lưu trữ từ số span mỗi giây, kích thước span trung bình và thời gian retention ra sao?
Bạn sẽ đánh giá tác động của số lượng span attributes và events đến kích thước dữ liệu lưu trữ như thế nào?
Bạn sẽ lựa chọn các thuộc tính cần lập chỉ mục để hỗ trợ tìm kiếm trace và kiểm soát chi phí storage như thế nào?
Bạn sẽ phân biệt tìm kiếm theo trace ID với tìm kiếm theo service, operation, tag và thời gian trong Jaeger như thế nào?
Bạn sẽ thiết kế retention khác nhau cho trace lỗi, trace thông thường và dữ liệu phục vụ kiểm toán ra sao?
Bạn sẽ xác định giới hạn của việc tăng retention trong khi ingest rate và dung lượng storage không đổi như thế nào?
Bạn sẽ lựa chọn cơ chế xóa dữ liệu cũ để tuân thủ retention mà không làm truy vấn hoặc ghi dữ liệu bị gián đoạn ra sao?
Bạn sẽ kiểm tra tình trạng storage backend khi trace ingest thành công ở receiver nhưng không xuất hiện trong truy vấn như thế nào?
Bạn sẽ phân biệt lỗi index, lỗi mapping, lỗi kết nối và lỗi quyền ghi khi Jaeger không lưu được trace ra sao?
Bạn sẽ theo dõi queue hoặc batch backlog để xác định storage đang nhận dữ liệu chậm hơn tốc độ ingest như thế nào?
Bạn sẽ xác định thời điểm cần mở rộng storage, tăng năng lực ghi hay tối ưu kích thước span dựa trên metric nào?
Bạn sẽ đánh giá tác động của replica và sharding đến khả năng sẵn sàng cũng như chi phí lưu trữ trace ra sao?
Bạn sẽ thiết kế backup và restore cho storage backend để đáp ứng RPO và RTO của dữ liệu tracing như thế nào?
Bạn sẽ kiểm thử khôi phục storage để xác minh trace cũ vẫn tìm kiếm được sau khi restore ra sao?
Bạn sẽ lựa chọn cơ chế xác thực và phân quyền giữa Jaeger v2 và storage backend theo nguyên tắc tối thiểu như thế nào?
Bạn sẽ bảo vệ dữ liệu trace trên đường truyền và khi lưu trữ bằng những lớp kiểm soát nào?
Bạn sẽ xác định PII hoặc secrets có thể xuất hiện trong span attributes, events và exception messages như thế nào?
Bạn sẽ thiết kế bước redaction hoặc filtering trước storage để tránh lưu dữ liệu nhạy cảm ra sao?
Bạn sẽ phân biệt mã hóa dữ liệu với loại bỏ dữ liệu nhạy cảm khỏi trace về mục tiêu bảo vệ như thế nào?
Bạn sẽ kiểm soát quyền truy cập Jaeger Query UI và API theo service, tenant hoặc nhóm vận hành như thế nào?
Bạn sẽ đánh giá nguy cơ một người dùng có thể tìm trace chứa thông tin khách hàng ngoài phạm vi được phép ra sao?
Bạn sẽ tổ chức audit truy vấn và thao tác quản trị đối với dữ liệu trace nhạy cảm như thế nào?
Bạn sẽ xác định những dữ liệu nào nên loại bỏ trước khi chia sẻ trace với nhà cung cấp hoặc nhóm hỗ trợ bên ngoài ra sao?
Bạn sẽ thiết kế quy trình thu hồi credential nếu endpoint OTLP hoặc storage secret bị lộ như thế nào?
Bạn sẽ giải thích head sampling khác tail sampling về thời điểm quyết định giữ trace và yêu cầu dữ liệu như thế nào?
Bạn sẽ lựa chọn tỷ lệ head sampling dựa trên lưu lượng, chi phí và mục tiêu điều tra ra sao?
Bạn sẽ phân biệt probabilistic sampling và rate-limiting sampling khi cần kiểm soát lượng trace như thế nào?
Bạn sẽ xác định các rủi ro khi sampling ở SDK khiến trace bị thiếu span do các service dùng cấu hình khác nhau ra sao?
Bạn sẽ thiết kế tail sampling để ưu tiên trace có lỗi hoặc latency vượt ngưỡng như thế nào?
Bạn sẽ giải thích vì sao tail sampling cần gom các span của cùng trace trước khi đưa ra quyết định như thế nào?
Bạn sẽ đánh giá ảnh hưởng của trace timeout và decision wait duration đến khả năng giữ đủ span trong tail sampling ra sao?
Bạn sẽ phân tích vì sao tail sampling có thể quyết định sai khi các span của cùng trace được phân phối đến nhiều collector replica khác nhau?
Bạn sẽ tổ chức routing theo trace ID để các span cùng trace đến đúng nơi thực hiện tail sampling ra sao?
Bạn sẽ lựa chọn chính sách giữ trace lỗi, trace chậm và một mẫu trace thành công để hỗ trợ nhiều mục tiêu vận hành như thế nào?
Bạn sẽ đo tỷ lệ trace bị drop do sampling và phân biệt với trace mất do lỗi exporter ra sao?
Bạn sẽ kiểm tra vì sao trace lỗi không được giữ lại dù policy tail sampling đã cấu hình như thế nào?
Bạn sẽ cân bằng chi phí lưu trữ với nhu cầu phân tích hiếm gặp khi sampling rate thay đổi theo tải ra sao?
Bạn sẽ đánh giá sampling làm thay đổi độ chính xác của service dependency graph và thống kê tần suất gọi giữa các service ra sao?
Bạn sẽ xác định cách phối hợp sampling ở SDK, collector gateway và backend để không vô tình sampling nhiều lần ra sao?
Bạn sẽ sử dụng Jaeger Query UI để tìm trace theo service, operation, thời gian và tag như thế nào?
Bạn sẽ phân tích một trace có thời lượng cao để tìm span chậm nhất và phân biệt thời gian chờ với thời gian xử lý ra sao?
Bạn sẽ xác định span lỗi đầu tiên trong một trace có nhiều service cùng trả lỗi như thế nào?
Bạn sẽ phân biệt span cha chậm vì chờ span con với span cha tự xử lý chậm qua timeline ra sao?
Bạn sẽ sử dụng span tags và events để xác định loại lỗi mà không cần đọc toàn bộ log ứng dụng như thế nào?
Bạn sẽ giải thích vì sao trace duration có thể lớn hơn tổng thời gian CPU thực tế của các service như thế nào?
Bạn sẽ xác định critical path khi một request gọi song song nhiều service và chỉ một nhánh chậm ra sao?
Bạn sẽ so sánh nhiều trace của cùng operation để nhận diện thay đổi về latency sau một lần deploy như thế nào?
Bạn sẽ sử dụng trace search để khoanh vùng lỗi theo version hoặc deployment environment ra sao?
Bạn sẽ chẩn đoán giới hạn tìm kiếm theo tag khi thuộc tính chưa được index hoặc storage backend không hỗ trợ truy vấn đó ra sao?
Bạn sẽ xác định cách phân biệt trace bị lỗi ở client, gateway, service trung gian hay database bằng span status và quan hệ cha con ra sao?
Bạn sẽ phân tích các span có khoảng trống thời gian lớn để tìm bước chờ queue hoặc retry bị thiếu instrumentation như thế nào?
Bạn sẽ nhận diện N+1 calls hoặc fan-out quá rộng qua nhiều span cùng loại trong một trace như thế nào?
Bạn sẽ xác định service downstream gây tail latency bằng cách so sánh duration và dependency trong nhiều trace ra sao?
Bạn sẽ sử dụng service dependency graph để phát hiện service gọi nhầm đích hoặc phát sinh vòng phụ thuộc như thế nào?
Bạn sẽ giải thích cách dữ liệu trace được tổng hợp thành service dependency graph và những giới hạn khi trace bị sampling ra sao?
Bạn sẽ phân biệt dependency graph suy ra từ trace với sơ đồ kiến trúc được khai báo thủ công như thế nào?
Bạn sẽ kết hợp trace với logs và metrics để chuyển từ cảnh báo latency đến nguyên nhân gốc ra sao?
Bạn sẽ liên kết trace ID trong log với kết quả truy vấn Jaeger để điều tra một request cụ thể như thế nào?
Bạn sẽ đối chiếu p99 latency từ metrics với trace mẫu để xác định service gây chậm ra sao?
Bạn sẽ xác định thời điểm cần bổ sung instrumentation khi trace không có span cho một đoạn xử lý quan trọng như thế nào?
Bạn sẽ đánh giá ảnh hưởng của trace attributes thiếu hoặc đặt tên không nhất quán đến khả năng truy vấn ra sao?
Bạn sẽ tổ chức dashboard hoặc liên kết từ hệ thống giám sát sang Jaeger để người trực dễ mở trace liên quan như thế nào?
Bạn sẽ lựa chọn mô hình triển khai Jaeger v2 dạng Deployment, StatefulSet hoặc tách riêng ingest và query theo yêu cầu vận hành nào?
Bạn sẽ xác định những thành phần nào cần scale ngang khi ingest trace tăng nhưng truy vấn vẫn ở mức thấp ra sao?
Bạn sẽ thiết kế Kubernetes Service và ingress để ứng dụng trong cluster gửi OTLP đến Jaeger v2 như thế nào?
Bạn sẽ cấu hình network policy để chỉ workload được phép mới gửi trace vào OTLP receiver ra sao?
Bạn sẽ xác định RBAC tối thiểu khi Jaeger cần đọc metadata Kubernetes hoặc được triển khai qua operator như thế nào?
Bạn sẽ quản lý cấu hình Jaeger v2 bằng ConfigMap, Secret và GitOps để có thể review và rollback ra sao?
Bạn sẽ thiết kế readiness và liveness probe cho Jaeger v2 để không restart thành phần chỉ vì storage tạm chậm như thế nào?
Bạn sẽ phân biệt health của receiver, exporter và query service khi Kubernetes chỉ báo Pod đang Running ra sao?
Bạn sẽ lập kế hoạch rolling upgrade Jaeger v2 mà vẫn duy trì tiếp nhận trace từ các ứng dụng đang hoạt động như thế nào?
Bạn sẽ đánh giá tương thích cấu hình và storage schema khi nâng cấp Jaeger v2 giữa các phiên bản ra sao?
Bạn sẽ xác định nhu cầu autoscaling collector dựa trên ingest rate và query service dựa trên tải truy vấn như thế nào?
Bạn sẽ kiểm soát resource requests và limits để Jaeger không tranh chấp CPU hoặc bộ nhớ với workload ứng dụng ra sao?
Bạn sẽ phân tích tác động của node failure hoặc availability zone failure đến collector, query và storage như thế nào?
Bạn sẽ thiết kế multi-cluster tracing để trace từ nhiều Kubernetes cluster được tìm kiếm thống nhất mà vẫn phân biệt nguồn ra sao?
Bạn sẽ xác định cách đưa trace từ workload ngoài Kubernetes vào Jaeger gateway một cách an toàn như thế nào?
Bạn sẽ lựa chọn giữa một Jaeger backend dùng chung và nhiều backend theo tenant hoặc môi trường dựa trên tiêu chí nào?
Bạn sẽ thiết kế network và authentication cho Query UI khi người dùng truy cập từ ngoài cluster như thế nào?
Bạn sẽ tự giám sát Jaeger v2 bằng những metric nào về receiver, exporter, queue, storage và query latency ra sao?
Bạn sẽ xây dựng dashboard theo received spans, exported spans, dropped spans và storage errors để theo dõi độ đầy đủ dữ liệu như thế nào?
Bạn sẽ phân biệt số span nhận vào với số span ghi thành công khi kiểm tra tình trạng pipeline ra sao?
Bạn sẽ xác định nguyên nhân exporter retry tăng cao bằng cách đối chiếu metric nội bộ, log và trạng thái storage như thế nào?
Bạn sẽ phát hiện tình trạng query chậm do storage hay do truy vấn quá rộng bằng những chỉ số nào?
Bạn sẽ đo ingest latency từ lúc ứng dụng kết thúc span đến khi trace có thể tìm thấy trong Jaeger như thế nào?
Bạn sẽ kiểm tra connection pool, thread pool và truy vấn storage khi Jaeger Query trả kết quả chậm dưới tải cao như thế nào?
Bạn sẽ đánh giá ảnh hưởng của truy vấn tìm kiếm thời gian rộng và nhiều tag đến tài nguyên backend như thế nào?
Bạn sẽ tìm nguyên nhân service dependency graph thiếu một quan hệ gọi dù các service vẫn trao đổi request bình thường như thế nào?
Bạn sẽ kiểm tra log nội bộ Jaeger v2 để phân biệt lỗi cấu hình component với lỗi kết nối storage như thế nào?
Bạn sẽ thiết kế cảnh báo khi received spans cao nhưng exported spans giảm hoặc dropped spans tăng ra sao?
Bạn sẽ lập thử nghiệm tải để xác định ngưỡng ingest và query throughput của Jaeger mà không gây ảnh hưởng production như thế nào?
Bạn sẽ kiểm chứng dữ liệu trace sau khi khôi phục storage hoặc chuyển backend mà không dựa duy nhất vào trạng thái Pod healthy ra sao?
Bạn sẽ chọn những chỉ số nào để so sánh trước và sau khi tối ưu sampling, qua đó xác minh các trace quan trọng vẫn được giữ lại?
Bạn sẽ phân tích hiện tượng Jaeger Query UI hoạt động nhưng kết quả tìm kiếm luôn rỗng bằng cách kiểm tra ingest, storage và time range ra sao?
Nếu ứng dụng gửi OTLP thành công nhưng Jaeger không tìm thấy trace, bạn sẽ lần theo receiver, processor, exporter và storage như thế nào?
Nếu một trace chỉ có span của service đầu tiên, bạn sẽ kiểm tra context propagation và cấu hình exporter ở các service sau ra sao?
Nếu trace xuất hiện trong Jaeger nhưng thiếu span của một nhánh xử lý bất đồng bộ, bạn sẽ điều tra message headers, sampling và consumer instrumentation như thế nào?
Nếu số received spans tăng nhưng exported spans đứng yên, bạn sẽ kiểm tra queue, memory limiter, exporter và storage theo thứ tự nào?
Nếu tail sampling loại bỏ trace lỗi dù span cuối cùng có error status, bạn sẽ kiểm tra routing theo trace ID và decision wait ra sao?
Nếu query theo service trả kết quả nhưng query theo tag không tìm thấy trace, bạn sẽ kiểm tra index, mapping và thuộc tính thực tế như thế nào?
Nếu Jaeger v2 bị tăng RAM và query latency sau khi tăng retention, bạn sẽ phân tích ingest volume, storage và index strategy ra sao?
Nếu rolling upgrade làm trace bị chia thành nhiều phần hoặc mất span, bạn sẽ kiểm tra tương thích context, sampling và endpoint như thế nào?
Nếu một backend storage tạm ngừng hoạt động, bạn sẽ đánh giá khả năng buffer, retry và giới hạn mất trace bằng phép thử nào?
Bạn sẽ đề xuất kiến trúc Jaeger v2 cho hệ thống microservices trên Kubernetes gồm OTLP ingestion, sampling, storage, query, bảo mật và tự giám sát như thế nào?
