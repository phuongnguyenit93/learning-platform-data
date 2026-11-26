Bạn phân biệt observability với monitoring truyền thống dựa trên khả năng trả lời những câu hỏi nào về trạng thái hệ thống?
Bạn đánh giá khi nào một hệ thống có nhiều dashboard nhưng vẫn khó điều tra sự cố như thế nào?
Ba loại tín hiệu metrics, logs và traces phản ánh những góc nhìn khác nhau nào của cùng một yêu cầu?
Profiling bổ sung bằng chứng gì mà metrics, logs và traces thường chưa chỉ ra được?
Những câu hỏi vận hành nào giúp bạn quyết định nên thu thập metrics, logs, traces hay profiling?
Bạn phân biệt dữ liệu telemetry với hiểu biết có thể hành động từ dữ liệu đó qua ví dụ thực tế như thế nào?
Bạn xây dựng bức tranh đường đi của một request qua client, gateway, service và database dựa trên các loại tín hiệu nào?
Bạn nhận diện những giới hạn của việc chỉ quan sát tài nguyên hạ tầng khi người dùng báo API chậm ra sao?
Bạn định nghĩa sự khác nhau giữa triệu chứng, tác động đến người dùng và nguyên nhân gốc của sự cố như thế nào?
Bạn xác lập ranh giới trách nhiệm thu thập telemetry giữa ứng dụng, thư viện, runtime và hạ tầng như thế nào?
Bạn ưu tiên mục tiêu khả dụng, hiệu năng và tính đúng đắn khi thiết kế observability cho một dịch vụ mới ra sao?
Bạn cân bằng độ chi tiết của telemetry với chi phí lưu trữ, truyền tải và xử lý như thế nào?
Bạn lập sơ đồ các thành phần phát sinh, truyền, biến đổi, lưu trữ và truy vấn telemetry trong một hệ thống như thế nào?
Bạn phân biệt instrumentation tự động và instrumentation thủ công dựa trên phạm vi thông tin cần thu thập như thế nào?
Bạn lựa chọn các quy ước tên, đơn vị và thuộc tính telemetry để nhiều nhóm có thể hiểu cùng một ý nghĩa như thế nào?
Bạn thiết kế chiến lược gắn service name, environment, region và version để tìm kiếm telemetry xuyên hệ thống ra sao?
Bạn xác định khi nào một trường dữ liệu nên là metric label, log field hoặc span attribute dựa trên mục tiêu truy vấn như thế nào?
Bạn phân tích sự khác nhau giữa tính mới, độ chính xác và độ đầy đủ của telemetry khi hệ thống đang quá tải như thế nào?
Bạn thiết kế cách truyền telemetry bất đồng bộ để giảm tác động của hệ thống quan sát đến luồng xử lý nghiệp vụ ra sao?
Bạn xử lý tình huống backend observability ngừng hoạt động mà ứng dụng vẫn phải tiếp tục phục vụ như thế nào?
Bạn đánh giá các rủi ro từ clock skew, dữ liệu đến trễ và thứ tự sự kiện khi ghép telemetry từ nhiều máy như thế nào?
Bạn xác định quy tắc lưu giữ và phân quyền telemetry dựa trên nhu cầu điều tra, chi phí và độ nhạy dữ liệu ra sao?
Bạn phân biệt counter, gauge và histogram theo đại lượng đo, cách cập nhật và cách diễn giải như thế nào?
Vì sao bạn chọn counter để ghi nhận số request hoặc lỗi rồi tính tỷ lệ khi truy vấn thay vì lưu sẵn tỷ lệ trong ứng dụng?
Bạn thiết kế gauge cho số kết nối đang hoạt động hoặc độ sâu hàng đợi để tránh hiểu nhầm một giá trị tức thời như thế nào?
Bạn sử dụng histogram để quan sát phân bố độ trễ thay vì chỉ đo thời gian trung bình như thế nào?
Bạn giải thích sự khác nhau giữa p50, p95, p99 và giá trị trung bình trong bối cảnh API chịu tải như thế nào?
Bạn xác định những label nào có ích khi chia metric theo service, route, status code và environment ra sao?
Vì sao đưa user ID, request ID hoặc giá trị không giới hạn vào metric label có thể gây vấn đề cardinality?
Bạn lựa chọn bucket histogram hoặc cấu hình phân bố phù hợp với SLO độ trễ như thế nào?
Bạn phân biệt throughput, request rate, latency và error rate khi đánh giá một dịch vụ như thế nào?
Bạn áp dụng phương pháp RED để chọn metric cho một API hướng request như thế nào?
Bạn áp dụng phương pháp USE để tìm bottleneck ở CPU, bộ nhớ, thiết bị lưu trữ hoặc kết nối ra sao?
Bạn so sánh RED, USE và bốn golden signals trong việc quan sát lớp ứng dụng và lớp hạ tầng như thế nào?
Bạn chọn SLI nào để đo chất lượng trải nghiệm người dùng thay vì chỉ phản ánh trạng thái máy chủ ra sao?
Bạn thiết lập SLO và error budget từ các metric đáng tin cậy theo mục tiêu nghiệp vụ như thế nào?
Bạn phân tích một sự cố có CPU thấp nhưng p99 latency tăng bằng cách kết hợp metric nào?
Bạn phân biệt lỗi do traffic spike với lỗi do năng lực phục vụ giảm từ các đường biểu diễn metric như thế nào?
Bạn đánh giá ảnh hưởng của scrape interval, aggregation window và tốc độ cập nhật đến kết luận từ đồ thị ra sao?
Bạn lý giải nguyên nhân một đồ thị counter giảm đột ngột sau khi ứng dụng restart như thế nào?
Bạn kiểm tra sự phù hợp giữa đơn vị metric, tỷ lệ chuyển đổi và phép tổng hợp trong dashboard như thế nào?
Bạn nhận diện hiện tượng metric mất mẫu hoặc xuất hiện khoảng trống dữ liệu để tránh coi không có dữ liệu là không có lỗi ra sao?
Bạn phân tích tác động của việc gom metric theo instance hoặc service đối với khả năng tìm một Pod lỗi như thế nào?
Bạn sử dụng metric và exemplar để liên kết một điểm độ trễ bất thường với trace cụ thể như thế nào?
Bạn xác định nguồn tạo metric phù hợp khi cùng một request được đo tại client, gateway và backend như thế nào?
Bạn mô tả một log có cấu trúc cần chứa những trường nào để hỗ trợ điều tra thay vì chỉ là câu thông báo tự do?
Bạn lựa chọn mức log DEBUG, INFO, WARN và ERROR theo ngữ nghĩa sự kiện và khả năng hành động như thế nào?
Bạn phân biệt log nghiệp vụ, log truy cập và log lỗi kỹ thuật theo mục tiêu tìm kiếm và phân tích như thế nào?
Bạn thiết kế quy ước event name và thông điệp log để không phụ thuộc vào câu chữ thay đổi liên tục như thế nào?
Bạn bổ sung correlation ID, trace ID và service metadata vào log để theo dõi cùng một request ra sao?
Bạn bố trí điểm ghi log nào trong vòng đời một tác vụ bất đồng bộ để theo dõi nhận, xử lý và hoàn tất công việc?
Bạn tránh ghi trùng một lỗi ở nhiều tầng mà vẫn giữ đủ ngữ cảnh điều tra bằng chiến lược nào?
Bạn cân nhắc mức độ chi tiết của stack trace, exception type và nguyên nhân lồng nhau trong log như thế nào?
Bạn xử lý các trường hợp log bị ghi sai định dạng, thiếu timestamp hoặc thiếu field quan trọng ra sao?
Bạn thiết kế vòng đời thu thập log từ container tới agent, pipeline và kho truy vấn trung tâm như thế nào?
Bạn phân biệt lỗi ứng dụng không phát log với lỗi pipeline làm thất lạc log thông qua những kiểm chứng nào?
Bạn đánh giá tác động của buffering, batching và backpressure lên độ trễ xuất hiện log khi hệ thống quá tải ra sao?
Bạn bảo vệ thông tin xác thực, dữ liệu cá nhân và payload nhạy cảm trước khi log được lưu trữ như thế nào?
Bạn xác định chính sách che giấu hoặc băm dữ liệu nào vẫn giữ khả năng chẩn đoán nhưng giảm rủi ro lộ thông tin ra sao?
Bạn xây dựng câu truy vấn log để phân biệt lỗi lặp lại tại một instance với lỗi xuất hiện trên toàn dịch vụ như thế nào?
Bạn đối chiếu log theo mốc triển khai và phiên bản ứng dụng để phát hiện hồi quy sau phát hành ra sao?
Bạn sử dụng log để giải thích một lần request thất bại nhưng không coi mọi dòng ERROR là một sự cố như thế nào?
Những tiêu chí nào khiến bạn chuyển một mẫu log lặp lại thành metric hoặc cảnh báo tổng hợp?
Bạn so sánh trace phân tán với tập hợp các log riêng lẻ khi điều tra request qua nhiều microservice như thế nào?
Bạn phân biệt trace, span, parent span và child span bằng cách mô tả một luồng gọi nhiều dịch vụ như thế nào?
Bạn xác định ranh giới span cho HTTP request, database query, message processing và thao tác nội bộ như thế nào?
Bạn diễn giải span name, timestamp, duration, attributes, events và status để hiểu một thao tác như thế nào?
Bạn mô tả việc lan truyền trace context qua HTTP hoặc gRPC giữa các service như thế nào?
Bạn xử lý việc truyền trace context qua queue khi producer và consumer hoạt động không đồng thời ra sao?
Bạn phân biệt quan hệ parent-child với span link khi một tác vụ nhận dữ liệu từ nhiều nguồn như thế nào?
Bạn xác định trường hợp trace bị đứt đoạn do không truyền context, sampling hoặc thư viện không được instrument như thế nào?
Bạn kiểm tra nguy cơ tạo trace mới ngoài ý muốn khi request đi qua gateway, worker hoặc callback ra sao?
Bạn lựa chọn thông tin span attribute nào để giải thích lỗi mà không đưa dữ liệu nhạy cảm hoặc giá trị có cardinality lớn vào trace?
Bạn phân tích critical path của một trace để xác định bước làm tăng thời gian phản hồi tổng thể như thế nào?
Bạn phân biệt thời gian thực thi tại một service với thời gian chờ mạng hoặc downstream trong waterfall trace như thế nào?
Bạn sử dụng trace để nhận diện N+1 query hoặc quá nhiều lời gọi nhỏ giữa các service như thế nào?
Bạn giải thích vì sao một span chậm chưa chắc là nguyên nhân gốc khiến toàn bộ request chậm như thế nào?
Bạn chọn head-based sampling hay tail-based sampling dựa trên nhu cầu giữ lại trace lỗi hoặc trace hiếm như thế nào?
Bạn đánh giá đánh đổi giữa tỷ lệ sampling, tính đại diện dữ liệu và chi phí thu thập trace ra sao?
Bạn xử lý tình huống số liệu latency trong trace sample khác metric tổng hợp do cách lấy mẫu như thế nào?
Bạn thiết kế cách điều tra trace có lỗi nhưng log cùng trace không xuất hiện hoặc không đủ ngữ cảnh như thế nào?
Bạn phân biệt CPU profiling, wall-time profiling, heap profiling và allocation profiling theo loại bottleneck có thể phát hiện như thế nào?
Khi metric cho thấy CPU cao nhưng trace chưa giải thích được nguyên nhân, bạn quyết định profiling ở đâu và theo cách nào?
Bạn phân tích flame graph để nhận diện hàm tiêu tốn thời gian CPU hoặc thời gian chờ theo luồng gọi như thế nào?
Bạn phân biệt inclusive time và self time trong kết quả profiling để tránh tối ưu sai vị trí ra sao?
Bạn kiểm tra memory allocation rate và heap retention để phân biệt cấp phát nhiều với rò rỉ bộ nhớ như thế nào?
Bạn sử dụng profiling để xác định hoạt động serialization, compression hoặc garbage collection làm chậm dịch vụ ra sao?
Bạn đánh giá độ nhiễu và overhead của sampling profiler so với instrumentation profiler như thế nào?
Bạn thiết kế thử nghiệm profiling trên môi trường gần production mà vẫn bảo vệ dữ liệu và giới hạn tác động như thế nào?
Bạn liên hệ thời điểm CPU spike trong metric với một flame graph hoặc profile tại cùng giai đoạn như thế nào?
Bạn giải thích vì sao tối ưu một hàm chiếm nhiều CPU không luôn cải thiện p99 latency của người dùng ra sao?
Bạn xây dựng cơ chế truyền correlation ID hoặc trace ID giữa log, metric exemplar và trace qua các tầng ứng dụng như thế nào?
Bạn sử dụng resource attributes để phân biệt môi trường, phiên bản, node và instance khi ghép các nguồn telemetry như thế nào?
Bạn lựa chọn OpenTelemetry hoặc chuẩn instrumentation chung để giảm khác biệt giữa các ngôn ngữ và dịch vụ như thế nào?
Bạn mô tả vai trò của Collector trong nhận, xử lý, lọc, batch và xuất telemetry tới backend như thế nào?
Bạn thiết kế pipeline telemetry chịu lỗi khi backend nhận chậm hoặc một exporter không khả dụng ra sao?
Bạn xác định những trường nào cần chuẩn hóa giữa log, metric và trace để việc chuyển ngữ cảnh trên dashboard nhất quán?
Bạn kiểm tra ảnh hưởng của timestamp, timezone và lệch đồng hồ trước khi kết luận hai sự kiện có quan hệ nhân quả như thế nào?
Bạn phân biệt correlation và causation khi hai metric cùng tăng trong thời gian xảy ra sự cố như thế nào?
Bạn xử lý trường hợp một nguồn telemetry cho thấy thành công trong khi nguồn khác ghi nhận thất bại bằng quy trình đối chiếu nào?
Bạn tìm cách liên kết một trace chậm với metric kết nối database và log timeout ở cùng thời điểm như thế nào?
Bạn xác định khi nào cần tăng tạm thời mức log hoặc tỷ lệ sampling để thu thập đủ bằng chứng điều tra ra sao?
Bạn xây dựng dashboard tổng quan dịch vụ từ traffic, errors, latency và saturation với cấu trúc nào để dễ phát hiện bất thường?
Bạn thiết kế dashboard chi tiết cho một API để truy từ mức service xuống route, instance và dependency như thế nào?
Bạn lựa chọn khoảng thời gian, độ phân giải và đơn vị trên biểu đồ để tránh hiểu nhầm xu hướng như thế nào?
Bạn thể hiện baseline, SLO và thời điểm deployment trên dashboard để phân biệt biến động bình thường với hồi quy ra sao?
Bạn tránh dashboard có quá nhiều biểu đồ nhưng thiếu ngữ cảnh hành động bằng cách ưu tiên thông tin nào?
Bạn xây dựng liên kết từ một panel metric đến log query hoặc trace liên quan như thế nào?
Bạn lựa chọn tiêu chí cảnh báo dựa trên tác động người dùng thay vì chỉ dựa vào vượt một ngưỡng CPU như thế nào?
Bạn phân biệt alert cần đánh thức on-call với alert dùng để theo dõi xu hướng hoặc tạo ticket như thế nào?
Bạn sử dụng thời gian duy trì điều kiện và ngưỡng phù hợp để hạn chế alert flapping ra sao?
Bạn phân biệt triệu chứng gốc và các cảnh báo thứ cấp để giảm alert storm trong sự cố dây chuyền như thế nào?
Bạn đưa những ngữ cảnh nào vào thông báo cảnh báo để người xử lý nhanh chóng truy cập dashboard và runbook?
Bạn đánh giá chất lượng cảnh báo qua độ chính xác, thời gian phát hiện, tỷ lệ nhiễu và khả năng hành động như thế nào?
Bạn xây dựng quy trình phát hiện, khoanh vùng, đặt giả thuyết và kiểm chứng nguyên nhân sự cố từ telemetry như thế nào?
Bạn ưu tiên bằng chứng nào khi người dùng báo chậm nhưng dashboard tổng quan không có cảnh báo nào?
Bạn phân biệt hệ thống bị lỗi diện rộng với chỉ một tenant hoặc một phiên bản bị ảnh hưởng bằng cách phân tách telemetry ra sao?
Bạn điều tra một lần tăng lỗi 5xx ngay sau deployment bằng log, trace và metric theo thứ tự nào?
Bạn kiểm tra giả thuyết database là bottleneck khi trace cho thấy nhiều service cùng chờ downstream như thế nào?
Bạn kết hợp metric saturation, log retry và trace call graph để phát hiện retry storm như thế nào?
Bạn xác định dấu hiệu telemetry thiếu, không tin cậy hoặc bị sampling khiến một giả thuyết không đủ bằng chứng ra sao?
Bạn lưu lại timeline, tác động, bằng chứng và nguyên nhân xác nhận sau sự cố để phục vụ postmortem như thế nào?
Bạn đo lường hiệu quả thay đổi sau khắc phục bằng so sánh trước và sau trên cùng bộ metric và workload như thế nào?
Bạn đánh giá chi phí observability theo mức thu thập, retention, cardinality và tần suất truy vấn để điều chỉnh mà không mất khả năng điều tra ra sao?
Bạn xây dựng tiêu chí nghiệm thu hệ thống observability để chứng minh đội vận hành có thể phát hiện, giải thích và phục hồi sau một sự cố mô phỏng như thế nào?
