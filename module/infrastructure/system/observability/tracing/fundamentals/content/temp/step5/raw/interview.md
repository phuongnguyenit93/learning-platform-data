Distributed tracing giải quyết những vấn đề nào khi một request đi qua nhiều tiến trình và dịch vụ độc lập?
Bạn sẽ phân biệt distributed tracing với logging và metrics về loại câu hỏi mà mỗi tín hiệu trả lời như thế nào?
Bạn sẽ mô tả cách một trace thể hiện hành trình của request từ gateway qua các service đến database ra sao?
Bạn sẽ giải thích trace, span, trace ID và span ID bằng một ví dụ xử lý đơn hàng như thế nào?
Bạn sẽ xác định ranh giới phù hợp để bắt đầu và kết thúc một trace trong ứng dụng như thế nào?
Bạn sẽ phân biệt một thao tác nghiệp vụ lớn với các span kỹ thuật mô tả những bước thực thi bên trong ra sao?
Bạn sẽ xác định khi nào một span nên đại diện cho server request, client call, database operation hoặc tác vụ nội bộ như thế nào?
Bạn sẽ mô tả quan hệ cha-con giữa các span và ý nghĩa của parent span ID trong trace như thế nào?
Bạn sẽ phân biệt trace có cấu trúc cây với những quan hệ nhân quả phức tạp cần span link ra sao?
Bạn sẽ giải thích vì sao trace ID giống nhau chưa đủ để chứng minh các span có quan hệ cha-con đúng?
Bạn sẽ xác định một trace hoàn chỉnh cần những thông tin nào để có thể phân tích đường đi và thời gian xử lý?
Bạn sẽ đánh giá rủi ro khi một request tạo quá nhiều span nhỏ khiến trace khó đọc và tốn tài nguyên như thế nào?
Bạn sẽ lựa chọn mức chi tiết span phù hợp giữa khả năng chẩn đoán và chi phí thu thập ra sao?
Bạn sẽ phân biệt thời gian của span với thời gian chờ giữa hai span liên tiếp khi đọc trace như thế nào?
Bạn sẽ giải thích span duration và self time khác nhau trong việc tìm bước xử lý tốn thời gian ra sao?
Bạn sẽ xác định những giới hạn của việc cộng duration các span lồng nhau để suy ra tổng thời gian request như thế nào?
Bạn sẽ phân tích trace có nhiều nhánh gọi song song và xác định nhánh quyết định thời gian hoàn thành ra sao?
Bạn sẽ mô tả cách span event ghi lại một mốc quan trọng bên trong span mà không cần tạo span con như thế nào?
Bạn sẽ phân biệt span attributes, span events và resource attributes theo phạm vi thông tin như thế nào?
Bạn sẽ lựa chọn thuộc tính nào cần gắn vào span để điều tra lỗi mà không đưa quá nhiều dữ liệu vào trace ra sao?
Bạn sẽ giải thích span status và status description giúp biểu diễn kết quả xử lý như thế nào?
Bạn sẽ phân biệt lỗi nghiệp vụ được xử lý bình thường với lỗi kỹ thuật cần đánh dấu span error như thế nào?
Bạn sẽ quyết định khi nào ghi exception event và khi nào chỉ cập nhật trạng thái span để tránh dữ liệu trùng lặp ra sao?
Bạn sẽ phân tích ảnh hưởng của việc kết thúc span quá sớm hoặc quá muộn đến cách diễn giải latency như thế nào?
Bạn sẽ xử lý một span bị bỏ quên không end khi tác vụ bất đồng bộ kết thúc bằng cách nào?
Bạn sẽ mô tả context chứa những thông tin nào để liên kết span hiện tại với thao tác tiếp theo như thế nào?
Bạn sẽ phân biệt current span với span đã được tạo nhưng không còn là span hiện hành ra sao?
Bạn sẽ giải thích context propagation giúp giữ quan hệ trace khi request chuyển qua thread hoặc tiến trình khác như thế nào?
Bạn sẽ xác định điểm nào trong luồng xử lý cần extract context đến và inject context đi như thế nào?
Bạn sẽ mô tả cách trace context được truyền qua HTTP header giữa hai service như thế nào?
Bạn sẽ giải thích vai trò của W3C Trace Context và cấu trúc header traceparent trong liên kết trace ra sao?
Bạn sẽ phân biệt trace ID, parent ID và trace flags trong traceparent như thế nào?
Bạn sẽ mô tả vai trò của tracestate khi nhiều hệ thống tracing cần truyền thêm thông tin tương thích như thế nào?
Bạn sẽ xử lý request đến không có trace context bằng cách tạo trace gốc như thế nào?
Bạn sẽ quyết định cách xử lý khi traceparent sai định dạng hoặc chứa ID không hợp lệ ra sao?
Bạn sẽ phân tích vì sao một proxy hoặc gateway có thể làm đứt trace nếu không chuyển tiếp đúng các header như thế nào?
Bạn sẽ phân biệt propagation qua HTTP với propagation qua gRPC metadata hoặc message headers như thế nào?
Bạn sẽ thiết kế liên kết trace khi producer gửi message và consumer xử lý message ở thời điểm khác ra sao?
Bạn sẽ chọn quan hệ parent-child hay span link khi một message được tạo từ nhiều hoạt động trước đó như thế nào?
Bạn sẽ xử lý context khi một message được retry hoặc đưa vào dead-letter queue mà vẫn giữ được khả năng truy dấu ra sao?
Bạn sẽ mô tả cách liên kết trace của một tác vụ nền không có request HTTP cha như thế nào?
Bạn sẽ phân biệt trace context với correlation ID nghiệp vụ trong một quy trình có nhiều lần retry ra sao?
Bạn sẽ giải thích baggage dùng để truyền metadata xuyên dịch vụ và khác span attributes như thế nào?
Bạn sẽ xác định loại thông tin nào không nên đưa vào baggage vì giới hạn kích thước hoặc quyền riêng tư ra sao?
Bạn sẽ kiểm soát baggage từ client bên ngoài để tránh dữ liệu không tin cậy lan truyền sâu vào hệ thống như thế nào?
Bạn sẽ chẩn đoán trường hợp trace ID thay đổi giữa hai service dù request vẫn thành công bằng cách nào?
Bạn sẽ kiểm tra khả năng propagation khi ứng dụng chuyển từ xử lý đồng bộ sang Executor hoặc CompletableFuture như thế nào?
Bạn sẽ giải thích vì sao ThreadLocal không tự động bảo đảm context đúng khi thread pool tái sử dụng thread ra sao?
Bạn sẽ thiết kế kiểm tra để phát hiện trace context bị rò rỉ từ request trước sang request tiếp theo như thế nào?
Bạn sẽ mô tả các thành phần API, SDK và instrumentation của OpenTelemetry trong một ứng dụng như thế nào?
Bạn sẽ phân biệt instrumentation tự động và instrumentation thủ công theo phạm vi quan sát và khả năng tùy biến ra sao?
Bạn sẽ lựa chọn thư viện hoặc framework cần instrument trước để thu được trace có giá trị cho một ứng dụng Java như thế nào?
Bạn sẽ xác định khi nào cần tạo span thủ công cho logic nghiệp vụ thay vì chỉ dựa vào auto instrumentation ra sao?
Bạn sẽ giải thích vai trò của Tracer và Span trong API OpenTelemetry như thế nào?
Bạn sẽ thiết kế cách tạo span với tên, kind, attributes và status phù hợp cho một thao tác gọi dịch vụ bên ngoài ra sao?
Bạn sẽ phân biệt các span kind như server, client, producer, consumer và internal theo ý nghĩa của chúng như thế nào?
Bạn sẽ lựa chọn semantic conventions để đặt tên span và thuộc tính thống nhất giữa các dịch vụ ra sao?
Bạn sẽ giải thích Resource trong OpenTelemetry giúp nhận diện service, instance và môi trường chạy như thế nào?
Bạn sẽ phân biệt Resource attributes với span attributes khi quyết định đặt service.name, deployment.environment và endpoint ra sao?
Bạn sẽ xác định những thuộc tính nào có thể dùng để lọc trace nhưng dễ gây cardinality hoặc lộ dữ liệu nếu ghi quá chi tiết?
Bạn sẽ tổ chức cấu hình OpenTelemetry SDK để ứng dụng tạo span nhưng không phụ thuộc trực tiếp vào một backend cụ thể như thế nào?
Bạn sẽ mô tả vai trò của sampler, processor và exporter trong vòng đời dữ liệu span như thế nào?
Bạn sẽ phân biệt BatchSpanProcessor và SimpleSpanProcessor theo hành vi export và ảnh hưởng hiệu năng ra sao?
Bạn sẽ lựa chọn cấu hình batch, queue và timeout export dựa trên lưu lượng trace và giới hạn tài nguyên như thế nào?
Bạn sẽ xử lý trường hợp exporter không kết nối được backend mà không làm request nghiệp vụ thất bại theo cách nào?
Bạn sẽ xác định những metric hoặc log nào cần theo dõi để phát hiện span bị drop trước khi export ra sao?
Bạn sẽ mô tả đường đi của trace từ OpenTelemetry SDK qua OTLP đến OpenTelemetry Collector và backend như thế nào?
Bạn sẽ phân biệt receiver, processor và exporter trong OpenTelemetry Collector theo trách nhiệm xử lý ra sao?
Bạn sẽ quyết định khi nào nên dùng collector agent gần ứng dụng và khi nào cần gateway tập trung như thế nào?
Bạn sẽ thiết kế pipeline Collector có nhiều processor để bổ sung resource, lọc dữ liệu và batch trước khi export ra sao?
Bạn sẽ đánh giá rủi ro khi Collector gateway trở thành điểm nghẽn hoặc điểm lỗi tập trung như thế nào?
Bạn sẽ bảo vệ OTLP endpoint bằng TLS, xác thực và phân quyền theo ranh giới mạng nào?
Bạn sẽ lựa chọn OTLP qua gRPC hay HTTP theo yêu cầu hạ tầng và khả năng tương thích client như thế nào?
Bạn sẽ kiểm tra sự khác nhau giữa lỗi tạo span, lỗi gửi OTLP và lỗi backend lưu hoặc hiển thị trace ra sao?
Bạn sẽ xử lý thay đổi schema hoặc semantic conventions khi các service triển khai phiên bản khác nhau như thế nào?
Bạn sẽ xác định cấu hình nào thuộc SDK, cấu hình nào thuộc Collector và cấu hình nào thuộc backend trong quá trình vận hành ra sao?
Bạn sẽ phân biệt head-based sampling và tail-based sampling theo thời điểm đưa ra quyết định như thế nào?
Bạn sẽ giải thích parent-based sampling giúp giữ quyết định sampling nhất quán qua các service như thế nào?
Bạn sẽ lựa chọn tỷ lệ sampling ban đầu dựa trên lưu lượng, ngân sách lưu trữ và nhu cầu điều tra ra sao?
Bạn sẽ đánh giá hạn chế của head sampling khi lỗi chỉ xuất hiện ở cuối một trace dài như thế nào?
Bạn sẽ mô tả tail sampling giữ lại trace dựa trên latency, status hoặc thuộc tính sau khi đã nhận đủ span ra sao?
Bạn sẽ xác định thời gian chờ và bộ nhớ cần thiết để tail sampler nhận các span của cùng một trace như thế nào?
Bạn sẽ phân tích điều gì xảy ra khi các span của một trace đến collector không cùng thời điểm hoặc bị phân tán qua nhiều collector ra sao?
Bạn sẽ thiết kế định tuyến để các span cùng trace đến đúng tail sampling instance bằng cách nào?
Bạn sẽ lựa chọn chính sách giữ trace lỗi hiếm gặp mà không phải lưu toàn bộ trace thành công như thế nào?
Bạn sẽ kết hợp sampling theo tỷ lệ với chính sách giữ lỗi hoặc latency cao để cân bằng chi phí và khả năng điều tra ra sao?
Bạn sẽ phân biệt việc trace không xuất hiện do sampling với việc trace bị mất do propagation hoặc exporter lỗi như thế nào?
Bạn sẽ đánh giá ảnh hưởng của sampling đến tính đại diện khi tính tỷ lệ lỗi hoặc latency từ dữ liệu trace như thế nào?
Bạn sẽ xác định giới hạn khi dùng trace samples để suy ra tổng số request của dịch vụ ra sao?
Bạn sẽ kiểm tra cấu hình sampler khi upstream đã quyết định không sample nhưng downstream muốn giữ trace lỗi như thế nào?
Bạn sẽ lựa chọn thuộc tính nào có thể được đánh giá tại thời điểm head sampling và thuộc tính nào chỉ biết sau khi request kết thúc?
Bạn sẽ giải thích vì sao trace được sample cần giữ các span liên quan để tránh hiển thị cây trace bị thiếu như thế nào?
Bạn sẽ thiết kế cách theo dõi số trace được nhận, giữ lại, loại bỏ và export trong từng chính sách sampling ra sao?
Bạn sẽ phân tích tác động của sampling thay đổi theo môi trường đến khả năng so sánh trace giữa staging và production như thế nào?
Bạn sẽ mô tả cách đọc waterfall view để tìm span chiếm phần lớn thời gian của một request như thế nào?
Bạn sẽ phân biệt latency ở client, server và tổng thời gian end-to-end khi nhiều service gọi lồng nhau ra sao?
Bạn sẽ tìm nguyên nhân một request chậm do downstream service, database hoặc queue bằng dữ liệu trace như thế nào?
Bạn sẽ nhận diện thời gian chờ không được biểu diễn thành span và ảnh hưởng đến phân tích latency ra sao?
Bạn sẽ phân tích một trace có nhiều lời gọi song song và xác định dependency làm chậm thời gian hoàn thành như thế nào?
Bạn sẽ phân biệt latency tăng ở mọi request với latency chỉ tăng ở một route hoặc một dependency như thế nào?
Bạn sẽ xác định dấu hiệu retry hoặc gọi lặp một dependency trong trace và đánh giá tác động của chúng ra sao?
Bạn sẽ phân tích trace có span client thành công nhưng span server không xuất hiện bằng những giả thuyết nào?
Bạn sẽ tìm lỗi do timeout, cancellation hoặc connection pool trong chuỗi span của một request như thế nào?
Bạn sẽ phân biệt lỗi trả về từ ứng dụng với lỗi do proxy hoặc gateway tạo ra qua span attributes và status ra sao?
Bạn sẽ sử dụng span events và exception details để xác định vị trí lỗi mà không dựa hoàn toàn vào stack trace như thế nào?
Bạn sẽ phân tích trace có thời gian span con lớn hơn span cha hoặc timestamp không hợp lý bằng cách nào?
Bạn sẽ đánh giá ảnh hưởng của đồng hồ giữa các máy không đồng bộ đến thứ tự và thời lượng span như thế nào?
Bạn sẽ phân biệt khoảng trống giữa các span với thời gian thực thi của một span khi đọc trace như thế nào?
Bạn sẽ kết hợp trace với access log và metrics để xác nhận sự cố ảnh hưởng nhiều request hay chỉ một request như thế nào?
Bạn sẽ sử dụng trace ID để tìm log liên quan mà không biến trace ID thành metric label ra sao?
Bạn sẽ xác định những trường hợp trace không đủ dữ liệu để kết luận nguyên nhân gốc và cần bổ sung instrumentation ở đâu?
Bạn sẽ phân tích trace của một request thanh toán thất bại nhưng không có span nào báo lỗi bằng những hướng điều tra nào?
Bạn sẽ điều tra tình huống P99 latency tăng nhưng phần lớn trace mẫu vẫn có thời gian bình thường như thế nào?
Bạn sẽ phân biệt một dependency chậm thực sự với thời gian chờ do client-side queue hoặc connection pool như thế nào?
Bạn sẽ xác định các điểm fan-out và fan-in trong trace để tìm nhánh có lỗi hoặc chậm bất thường ra sao?
Bạn sẽ xây dựng quy trình điều tra từ một SLO latency bị vi phạm đến trace đại diện và span gây chậm như thế nào?
Bạn sẽ lựa chọn cách đặt span name để hỗ trợ nhóm theo operation mà không đưa ID động vào tên span ra sao?
Bạn sẽ giải thích vì sao span name hoặc attributes chứa URL đầy đủ có thể gây cardinality và lộ thông tin như thế nào?
Bạn sẽ đánh giá việc ghi request body, query parameters hoặc user identifier vào span attributes theo nguyên tắc tối thiểu dữ liệu ra sao?
Bạn sẽ thiết kế chính sách lọc hoặc redact dữ liệu nhạy cảm trước khi trace được export khỏi ứng dụng như thế nào?
Bạn sẽ kiểm soát quyền truy cập trace theo service, tenant và môi trường để tránh lộ thông tin giữa khách hàng ra sao?
Bạn sẽ xác định thời hạn lưu trace phù hợp với mục tiêu điều tra, chi phí và nghĩa vụ bảo vệ dữ liệu như thế nào?
Bạn sẽ đánh giá nguy cơ baggage truyền dữ liệu cá nhân hoặc secret qua nhiều trust boundary như thế nào?
Bạn sẽ thiết kế cách giới hạn kích thước span attributes và events để tránh một trace chiếm quá nhiều tài nguyên ra sao?
Bạn sẽ lựa chọn dữ liệu nào cần giữ đầy đủ cho security investigation và dữ liệu nào có thể sampling theo tỷ lệ như thế nào?
Bạn sẽ đánh giá rủi ro khi người dùng bên ngoài tự gửi trace context nhằm gây nhầm lẫn hoặc làm tăng chi phí tracing ra sao?
Bạn sẽ bảo vệ OTLP exporter và collector khỏi việc nhận trace giả mạo hoặc lưu lượng quá mức như thế nào?
Bạn sẽ phân tích mối quan hệ giữa tỷ lệ sampling, số span trung bình mỗi trace và chi phí ingest như thế nào?
Bạn sẽ dự báo chi phí lưu trace khi số request tăng gấp đôi nhưng tỷ lệ sampling không đổi ra sao?
Bạn sẽ xác định metric nào cần theo dõi để biết instrumentation tạo quá nhiều span hoặc event không cần thiết như thế nào?
Bạn sẽ cân nhắc giảm sampling hay giảm độ chi tiết instrumentation khi ngân sách tracing bị vượt như thế nào?
Bạn sẽ tổ chức retention theo độ tuổi, trạng thái lỗi hoặc mức độ quan trọng của trace ra sao?
Bạn sẽ thiết kế dashboard theo dõi số trace, span, kích thước export, queue backlog và lỗi collector như thế nào?
Bạn sẽ xác định ngưỡng cảnh báo cho dropped spans hoặc exporter failures dựa trên mức ảnh hưởng vận hành ra sao?
Bạn sẽ mô tả cách kiểm tra một trace bị thiếu span do collector queue đầy hoặc backend từ chối dữ liệu như thế nào?
Bạn sẽ instrument một endpoint mới và xác minh trace xuyên qua gateway, application, database và downstream service bằng cách nào?
Bạn sẽ thiết kế bài kiểm thử xác nhận trace ID và parent-child relation được giữ đúng qua HTTP call như thế nào?
Bạn sẽ kiểm thử propagation qua message broker khi producer và consumer chạy ở hai tiến trình độc lập ra sao?
Bạn sẽ tạo kịch bản test song song nhiều request để phát hiện context bị lẫn giữa các trace như thế nào?
Bạn sẽ xác minh sampler giữ lại trace có lỗi nhưng loại bớt trace thành công theo đúng chính sách như thế nào?
Bạn sẽ kiểm thử tail sampling khi span đến muộn hoặc một số span bị mất bằng những tình huống nào?
Bạn sẽ kiểm tra exporter timeout và collector restart để xác định khả năng mất dữ liệu trace ra sao?
Bạn sẽ phân biệt lỗi cấu hình instrumentation với lỗi backend query khi trace không hiển thị trong giao diện như thế nào?
Bạn sẽ thiết kế phép thử tải để đo overhead CPU, bộ nhớ và latency do tracing instrumentation gây ra ra sao?
Bạn sẽ kiểm tra thay đổi semantic conventions sau nâng cấp thư viện để dashboard và truy vấn trace không bị sai như thế nào?
Bạn sẽ xây dựng quy trình rollout instrumentation theo canary để tránh tăng đột ngột chi phí hoặc giảm hiệu năng ra sao?
Bạn sẽ đặt tiêu chí rollback khi bản phát hành mới làm tăng span volume hoặc tạo trace không đầy đủ như thế nào?
Bạn sẽ xác định các thành phần cần giám sát độc lập để tracing vẫn có thể báo lỗi khi chính pipeline tracing gặp sự cố ra sao?
Bạn sẽ tổ chức runbook điều tra khi trace không liên tục, span bị thiếu hoặc latency không hợp lý như thế nào?
Bạn sẽ đánh giá chất lượng tracing bằng những tiêu chí nào về độ bao phủ, tính liên kết, độ chính xác, quyền riêng tư và chi phí trước khi triển khai production?
