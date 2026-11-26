Bạn sẽ xác định những vấn đề nào của hệ thống nhiều dịch vụ khiến cần triển khai logging tập trung?
Bạn sẽ phác thảo đường đi của một sự kiện log từ ứng dụng đến dashboard khi dùng Elasticsearch, Logstash, Beats hoặc Elastic Agent và Kibana như thế nào?
Bạn sẽ phân biệt trách nhiệm thu thập, biến đổi, lưu trữ, tìm kiếm và trực quan hóa giữa các thành phần của ELK Stack ra sao?
Bạn sẽ lựa chọn kiến trúc đưa log trực tiếp vào Elasticsearch hay đi qua Logstash dựa trên yêu cầu nào?
Bạn sẽ so sánh mô hình ELK với việc chỉ lưu log trên từng server về khả năng điều tra và chi phí vận hành như thế nào?
Bạn sẽ xác định ranh giới trách nhiệm giữa ứng dụng phát log, agent thu thập và pipeline chuẩn hóa như thế nào?
Bạn sẽ thiết kế luồng dữ liệu khi nguồn log đến từ ứng dụng Java, reverse proxy, hệ điều hành và container ra sao?
Bạn sẽ phân biệt log, metric và trace để tránh dùng Elasticsearch như nơi lưu mọi dữ liệu observability một cách thiếu kiểm soát như thế nào?
Bạn sẽ xác định SLA về độ trễ xuất hiện log, khả năng truy vấn và thời gian lưu giữ trước khi thiết kế hệ thống như thế nào?
Bạn sẽ tính toán lượng dữ liệu log sinh ra mỗi ngày từ số request, kích thước sự kiện và tỷ lệ log theo mức severity ra sao?
Bạn sẽ đánh giá sự đánh đổi giữa việc ghi log chi tiết và chi phí CPU, I/O, mạng, lưu trữ bằng cách nào?
Bạn sẽ xác định các tình huống nên dùng Beats, Elastic Agent hoặc bộ thu thập trung gian khác như thế nào?
Bạn sẽ lựa chọn vị trí đặt agent trên host, trong container hoặc theo node Kubernetes dựa trên nguồn log như thế nào?
Bạn sẽ mô tả cách Filebeat theo dõi file log được nối thêm và duy trì vị trí đọc giữa các lần khởi động ra sao?
Bạn sẽ điều tra vì sao agent đọc lại log từ đầu hoặc bỏ sót dòng sau khi file bị rotate như thế nào?
Bạn sẽ chọn cơ chế phát hiện file mới, rename hoặc truncate để thu thập log từ ứng dụng có log rotation như thế nào?
Bạn sẽ phân biệt thu thập từ file, stdout của container và syslog qua các rủi ro mất dữ liệu ra sao?
Bạn sẽ xử lý log nhiều dòng của Java stack trace để giữ mỗi exception thành một sự kiện có ngữ cảnh như thế nào?
Bạn sẽ thiết kế quy tắc multiline khi một sự kiện có nhiều dòng nhưng không phải dòng nào cũng bắt đầu bằng timestamp ra sao?
Bạn sẽ kiểm tra vì sao stack trace bị tách thành hàng chục document và gây khó tìm kiếm như thế nào?
Bạn sẽ tổ chức thu thập log từ nhiều container trong cùng Pod mà vẫn xác định đúng tên container và namespace ra sao?
Bạn sẽ dùng metadata Kubernetes như pod, node, namespace và labels để hỗ trợ khoanh vùng sự cố như thế nào?
Bạn sẽ hạn chế việc sao chép toàn bộ Kubernetes labels vào mỗi log khi có nguy cơ tăng kích thước hoặc cardinality như thế nào?
Bạn sẽ xác định trường hợp agent có thể thu thập log của Pod đã bị xóa và những giới hạn về thời gian tồn tại file ra sao?
Bạn sẽ đánh giá cách sử dụng Elastic Agent và Fleet để quản lý cấu hình thu thập trên nhiều máy như thế nào?
Bạn sẽ kiểm soát việc thay đổi agent policy để tránh đồng loạt làm ngừng thu thập log của cả một nhóm máy ra sao?
Bạn sẽ phân biệt quản lý agent tập trung và quản lý cấu hình thủ công theo file về khả năng audit và rollback như thế nào?
Bạn sẽ xác định dấu hiệu agent còn chạy nhưng không còn gửi được log đến đích bằng metric hoặc log nào?
Bạn sẽ kiểm tra kết nối mạng, chứng chỉ và quyền xác thực khi agent không thể gửi dữ liệu vào pipeline như thế nào?
Bạn sẽ tổ chức retry ở agent để đối phó lỗi mạng ngắn hạn mà không tạo lượng dữ liệu gửi lặp quá lớn ra sao?
Bạn sẽ lựa chọn kích thước batch và số worker gửi dữ liệu từ agent theo tải và năng lực hệ thống nhận như thế nào?
Bạn sẽ tính toán bộ đệm cần thiết khi Elasticsearch tạm không nhận ghi trong một khoảng thời gian dự kiến ra sao?
Bạn sẽ giải thích cấu trúc input, filter và output của một Logstash pipeline bằng luồng log ứng dụng cụ thể như thế nào?
Bạn sẽ lựa chọn plugin input và output dựa trên giao thức truyền và yêu cầu bảo đảm dữ liệu như thế nào?
Bạn sẽ thiết kế nhiều Logstash pipeline để cách ly log hệ thống khỏi log ứng dụng có định dạng phức tạp ra sao?
Bạn sẽ giải thích cách pipeline worker, batch size và queue ảnh hưởng đến thông lượng Logstash như thế nào?
Bạn sẽ xác định điểm nghẽn khi CPU Logstash cao nhưng tốc độ ingest vào Elasticsearch vẫn thấp ra sao?
Bạn sẽ phân biệt grok và dissect theo cấu trúc log đầu vào và chi phí xử lý như thế nào?
Bạn sẽ thiết kế pattern grok để trích xuất method, path, status và duration từ access log như thế nào?
Bạn sẽ xác định vì sao pattern grok không khớp cho một nhóm sự kiện và xử lý log chưa parse được ra sao?
Bạn sẽ dùng field dành cho lỗi parse hoặc tag đánh dấu thất bại để giữ lại sự kiện phục vụ điều tra như thế nào?
Bạn sẽ chuyển đổi trường kiểu chuỗi thành số hoặc boolean mà vẫn xử lý được các bản ghi lỗi định dạng ra sao?
Bạn sẽ chuẩn hóa timestamp từ nhiều nguồn có múi giờ khác nhau để truy vấn thống nhất như thế nào?
Bạn sẽ phân biệt thời điểm sự kiện xảy ra, thời điểm agent đọc và thời điểm Elasticsearch ingest để đo độ trễ pipeline ra sao?
Bạn sẽ lựa chọn cách xử lý timestamp thiếu timezone hoặc đồng hồ nguồn lệch khiến log xuất hiện sai vị trí thời gian như thế nào?
Bạn sẽ kết hợp mutate, date và các bước biến đổi cần thiết mà không làm mất thông tin gốc của sự kiện ra sao?
Bạn sẽ dùng enrichment như geo-IP hoặc thông tin dịch vụ bổ sung vào log và đánh giá độ tin cậy của dữ liệu ra sao?
Bạn sẽ dựa trên tiêu chí nào để loại bỏ field thừa trước khi lập chỉ mục mà không làm mất bằng chứng cần điều tra?
Bạn sẽ quyết định lọc bỏ log mức DEBUG ở agent, Logstash hay tầng ứng dụng theo mục tiêu tiết kiệm và điều tra ra sao?
Bạn sẽ so sánh khả năng parse ở Elasticsearch ingest pipeline và ở Logstash khi cần chọn vị trí chuẩn hóa log như thế nào?
Bạn sẽ phân chia quy tắc biến đổi giữa agent, Logstash và ingest node để tránh parse lặp lại như thế nào?
Bạn sẽ xây dựng quy trình thử nghiệm parser trên bộ log mẫu có cả trường hợp hợp lệ và không hợp lệ ra sao?
Bạn sẽ quản lý version của pipeline khi nhiều phiên bản ứng dụng phát log theo định dạng khác nhau như thế nào?
Bạn sẽ sử dụng cấu trúc JSON logging từ ứng dụng để giảm độ phức tạp parser so với văn bản tự do ra sao?
Bạn sẽ chọn các trường cần chuẩn hóa theo Elastic Common Schema để tìm kiếm log liên dịch vụ như thế nào?
Bạn sẽ ánh xạ tên trường ứng dụng như requestId, traceId và userAgent vào cấu trúc thống nhất mà vẫn giữ ý nghĩa ra sao?
Bạn sẽ phân biệt field text và keyword trong Elasticsearch khi cần vừa tìm nội dung vừa nhóm theo giá trị chính xác như thế nào?
Bạn sẽ xác định loại dữ liệu thích hợp cho IP, timestamp, số nguyên và thời gian xử lý trong mapping ra sao?
Bạn sẽ xử lý trường có kiểu dữ liệu thay đổi giữa các nguồn để tránh mapping conflict như thế nào?
Bạn sẽ đánh giá nguy cơ dynamic mapping tạo quá nhiều field khi log chứa JSON có khóa do người dùng kiểm soát ra sao?
Bạn sẽ thiết kế index template hoặc component template để kiểm soát mapping và setting nhất quán như thế nào?
Bạn sẽ giải thích data stream phù hợp với dữ liệu log theo thời gian và khác index đơn lẻ ra sao?
Bạn sẽ xác định cách đặt tên data stream theo loại dữ liệu, namespace và môi trường mà không tăng số lượng stream quá mức như thế nào?
Bạn sẽ mô tả quan hệ giữa data stream, write index và backing indices khi có rollover như thế nào?
Bạn sẽ sử dụng ingestion pipeline để gắn hoặc chuẩn hóa dữ liệu trước khi Elasticsearch lập chỉ mục ra sao?
Bạn sẽ xử lý một document lỗi mapping ra sao để tránh cả batch ingest bị gửi lại và thất bại liên tục?
Bạn sẽ thiết kế quy trình cách ly document lỗi vào nơi xử lý riêng để có thể kiểm tra và nạp lại sau khi sửa như thế nào?
Bạn sẽ phân biệt at-least-once delivery với exactly-once processing và nguy cơ log trùng khi agent hoặc pipeline retry ra sao?
Bạn sẽ xác định chiến lược document ID hoặc deduplication thích hợp khi một số log bị gửi lại nhiều lần như thế nào?
Bạn sẽ đánh giá những rủi ro của việc dùng timestamp và message làm document ID đối với các sự kiện giống nhau như thế nào?
Bạn sẽ triển khai persistent queue trong Logstash để giảm nguy cơ mất log khi pipeline hoặc Elasticsearch tạm ngừng như thế nào?
Bạn sẽ so sánh queue trong bộ nhớ với persistent queue về thông lượng, độ bền và chi phí I/O ra sao?
Bạn sẽ xác định trường hợp dead letter queue hỗ trợ điều tra document không thể ghi vào Elasticsearch như thế nào?
Bạn sẽ kiểm tra điểm nghẽn ở agent, queue, filter hay output khi tốc độ log đầu vào vượt tốc độ ingest như thế nào?
Bạn sẽ nhận biết backpressure lan từ Elasticsearch về Logstash và agent bằng những chỉ số nào?
Bạn sẽ thiết kế điều kiện mở rộng ngang Logstash mà vẫn cân nhắc thứ tự và khả năng phân phối sự kiện ra sao?
Bạn sẽ xác định giới hạn lưu log tại nguồn khi một cluster Elasticsearch không khả dụng trong thời gian dài như thế nào?
Bạn sẽ kiểm tra việc Logstash restart giữa lúc xử lý batch có thể gây mất hoặc lặp log theo cấu hình queue ra sao?
Bạn sẽ lập kế hoạch khôi phục và phát lại log từ file hoặc message broker sau khi pipeline bị lỗi nhiều giờ như thế nào?
Bạn sẽ xây dựng phép đo end-to-end về số lượng sự kiện nhận, xử lý thành công, bị loại và bị lỗi như thế nào?
Bạn sẽ xác định giới hạn độ trễ ingest chấp nhận được cho log phục vụ cảnh báo sự cố thời gian gần thực ra sao?
Bạn sẽ phân biệt Elasticsearch node, cluster, index, shard và replica qua sơ đồ lưu trữ log như thế nào?
Bạn sẽ giải thích inverted index giúp tìm kiếm log theo từ khóa nhanh nhưng tạo chi phí ingest và lưu trữ ra sao?
Bạn sẽ lựa chọn số primary shard khi dự kiến lượng log và tốc độ tăng trưởng theo thời gian như thế nào?
Bạn sẽ phân tích tác động của quá nhiều shard nhỏ đến heap, cluster state và thời gian truy vấn ra sao?
Bạn sẽ đánh giá sự đánh đổi giữa số replica, khả năng đọc và chi phí lưu trữ cho log nghiệp vụ như thế nào?
Bạn sẽ kiểm tra shard allocation khi cluster ở trạng thái yellow hoặc red và xác định mức ảnh hưởng đến truy vấn như thế nào?
Bạn sẽ đọc thông tin cluster health, index health và node statistics để khoanh vùng nút thắt ra sao?
Bạn sẽ phân biệt heap pressure, CPU saturation và disk I/O bottleneck của Elasticsearch bằng metric nào?
Bạn sẽ giải thích tác động của refresh interval đến độ trễ xuất hiện log trong tìm kiếm và chi phí ghi như thế nào?
Bạn sẽ xác định khi nào cần thay đổi batch ingest hoặc refresh interval để giảm nghẽn ghi mà vẫn đáp ứng yêu cầu tìm kiếm ra sao?
Bạn sẽ phân tích vai trò của Lucene segments và merge trong chi phí CPU, đĩa và truy vấn log như thế nào?
Bạn sẽ đánh giá ảnh hưởng của high-cardinality fields, aggregation và wildcard search lên hiệu năng Elasticsearch ra sao?
Bạn sẽ xác định nguyên nhân indexing pressure hoặc bulk rejection khi lượng log tăng đột biến như thế nào?
Bạn sẽ xử lý tình huống disk watermark ngăn cấp phát shard hoặc ghi dữ liệu mới bằng trình tự nào?
Bạn sẽ phân biệt lỗi index read-only do ngưỡng dung lượng đĩa với lỗi phân quyền ghi vào Elasticsearch như thế nào?
Bạn sẽ kiểm tra sự cố một node rời cluster và khả năng replica tiếp tục phục vụ tìm kiếm như thế nào?
Bạn sẽ thiết kế nguyên tắc phân bố node và shard qua nhiều availability zone để hạn chế mất dữ liệu log ra sao?
Bạn sẽ xác định lúc nào cần tăng dung lượng, giảm retention hoặc tối ưu mapping thay vì chỉ bổ sung node như thế nào?
Bạn sẽ mô tả vòng đời log từ ghi mới, ít truy cập, lưu trữ dài hạn đến xóa theo chính sách như thế nào?
Bạn sẽ thiết kế index lifecycle management cho log có nhu cầu lưu giữ khác nhau theo môi trường và mức quan trọng ra sao?
Bạn sẽ lựa chọn điều kiện rollover theo tuổi, kích thước hoặc số document cho một data stream nhiều lưu lượng như thế nào?
Bạn sẽ phân biệt xóa dữ liệu theo vòng đời index với xóa từng document về chi phí và tính kiểm soát như thế nào?
Bạn sẽ cân nhắc hot, warm, cold và frozen tiers theo tần suất truy vấn và giới hạn chi phí ra sao?
Bạn sẽ đánh giá lợi ích và giới hạn của searchable snapshot khi cần truy vấn log lịch sử ít được truy cập ra sao?
Bạn sẽ xác định yêu cầu lưu trữ bắt buộc của log audit khác với log debug trong chính sách retention ra sao?
Bạn sẽ dự đoán dung lượng ổ đĩa từ ingest rate, số replica, retention và hệ số overhead bằng cách nào?
Bạn sẽ đo tỷ lệ nén hoặc kích thước trung bình của document để cải thiện dự báo lưu trữ như thế nào?
Bạn sẽ phân biệt index template, ILM policy và snapshot policy trong việc quản lý vòng đời dữ liệu như thế nào?
Bạn sẽ xây dựng chiến lược snapshot Elasticsearch để khôi phục log khi mất node hoặc thao tác xóa nhầm ra sao?
Bạn sẽ kiểm thử restore từ snapshot để xác nhận index, mapping và khả năng tìm kiếm còn chính xác như thế nào?
Bạn sẽ xác định RPO và RTO cho nền tảng logging khi nó chỉ hỗ trợ điều tra so với khi nó giữ log tuân thủ bắt buộc ra sao?
Bạn sẽ kiểm soát việc xóa dữ liệu theo thời hạn pháp lý trong khi vẫn giữ bằng chứng phục vụ điều tra hợp lệ như thế nào?
Bạn sẽ thiết kế giải pháp sao lưu hoặc lưu bản gốc khi việc chuẩn hóa log có thể làm mất thông tin cần kiểm toán như thế nào?
Bạn sẽ so sánh tìm kiếm full-text, exact-match và filter trên Elasticsearch qua một vụ điều tra request lỗi như thế nào?
Bạn sẽ sử dụng Kibana Discover để lọc log theo thời gian, service và trace ID nhằm tìm sự kiện liên quan ra sao?
Bạn sẽ kiểm tra time field và timezone của Kibana ra sao khi một sự kiện không xuất hiện trong khoảng thời gian mong đợi?
Bạn sẽ tạo data view cho một hoặc nhiều data stream mà vẫn tránh truy vấn nhầm dữ liệu từ môi trường khác ra sao?
Bạn sẽ phân biệt việc tìm theo từ khóa với lọc chính xác trên field keyword để tránh kết quả không mong đợi như thế nào?
Bạn sẽ xây dựng truy vấn KQL để lọc theo severity, service.name và giá trị HTTP status như thế nào?
Bạn sẽ phân biệt khả năng của KQL với truy vấn Elasticsearch Query DSL khi cần diễn đạt điều kiện phức tạp ra sao?
Bạn sẽ kiểm tra phiên bản và tính năng được hỗ trợ trước khi chọn ES|QL hoặc ngôn ngữ truy vấn khác như thế nào?
Bạn sẽ thiết kế truy vấn tổng hợp số lỗi theo thời gian và nhóm theo service để phát hiện đợt tăng bất thường ra sao?
Bạn sẽ lựa chọn biểu đồ đường, bảng, histogram hoặc heatmap theo câu hỏi điều tra vận hành nào?
Bạn sẽ tạo dashboard về lưu lượng log, tỷ lệ lỗi, top exception và thời gian ingest cho nhiều service như thế nào?
Bạn sẽ phân biệt số lượng document log với số request thực tế khi một request có thể sinh nhiều bản ghi ra sao?
Bạn sẽ tránh kết luận sai rằng tỷ lệ lỗi tăng chỉ vì lượng log mức ERROR tăng sau thay đổi cấu hình ghi log như thế nào?
Bạn sẽ xác định field nào cần dùng cho aggregation để không chạy phân nhóm tốn kém trên nội dung text dài ra sao?
Bạn sẽ xử lý dashboard chậm do khoảng thời gian quá rộng, số lượng shard lớn hoặc aggregation phức tạp như thế nào?
Bạn sẽ thiết kế saved searches hoặc dashboard có bộ lọc theo namespace và phiên bản triển khai để hỗ trợ on-call ra sao?
Bạn sẽ kiểm tra truy vấn Kibana không trả kết quả vì data view, quyền truy cập, time filter hay pipeline ingest bằng thứ tự nào?
Bạn sẽ liên kết trace ID, request ID và log context để đi từ một HTTP 500 tại gateway đến lỗi gốc trong backend như thế nào?
Bạn sẽ cấu hình cảnh báo từ log trên Kibana hoặc hệ thống tương đương theo điều kiện và cửa sổ thời gian nào?
Bạn sẽ xác định cách giảm cảnh báo trùng hoặc false positive khi một exception xuất hiện trong nhiều lượt retry như thế nào?
Bạn sẽ đánh giá độ trễ cảnh báo từ log khi pipeline bị backlog và dữ liệu tới muộn ra sao?
Bạn sẽ tổ chức quyền xem dashboard và quyền truy cập log thô khác nhau giữa nhóm vận hành, phát triển và kiểm toán như thế nào?
Bạn sẽ phân biệt bảo vệ kết nối bằng TLS với xác thực và phân quyền các thành phần trong ELK Stack như thế nào?
Bạn sẽ thiết kế quyền tối thiểu cho agent chỉ được ghi dữ liệu cần thiết mà không được đọc hoặc xóa index khác ra sao?
Bạn sẽ phân quyền Elasticsearch theo index hoặc data stream để tách log của các nhóm ứng dụng như thế nào?
Bạn sẽ xác định những loại dữ liệu nhạy cảm nào không nên xuất hiện trong log như token, mật khẩu hoặc thông tin cá nhân?
Bạn sẽ chọn xử lý xóa hoặc che dữ liệu nhạy cảm ở ứng dụng, agent hay pipeline ingest dựa trên ranh giới tin cậy nào?
Bạn sẽ kiểm thử bộ lọc masking để bảo đảm không làm lộ secret trong URL query, header hoặc exception message như thế nào?
Bạn sẽ phân tích rủi ro khi log raw đã chứa dữ liệu nhạy cảm trước khi pipeline mới tiến hành masking ra sao?
Bạn sẽ thiết kế bảo vệ dữ liệu log trên đường truyền và trên ổ đĩa theo chính sách bảo mật doanh nghiệp như thế nào?
Bạn sẽ tổ chức rotate API key, certificate và thông tin xác thực của agent hoặc Logstash mà không gián đoạn ingest như thế nào?
Bạn sẽ audit những thao tác tìm kiếm, thay đổi policy và xóa dữ liệu log quan trọng bằng cơ chế nào?
Bạn sẽ phân tích cách chống log injection hoặc dữ liệu log giả mạo làm sai lệch dashboard và kết quả điều tra như thế nào?
Bạn sẽ đánh giá rủi ro truy vấn log chứa thông tin nội bộ bị chia sẻ qua dashboard hoặc saved search không đúng quyền ra sao?
Bạn sẽ giữ tính toàn vẹn và khả năng truy nguyên nguồn log phục vụ kiểm toán hoặc điều tra an ninh như thế nào?
Bạn sẽ quản lý quyền của Kibana Spaces và role để tránh lẫn log production với môi trường test ra sao?
Bạn sẽ xác định mức độ cần mã hóa, xóa dữ liệu và thời gian lưu giữ log theo chính sách pháp lý hoặc nội bộ như thế nào?
Bạn sẽ thiết kế theo dõi độ khỏe của Elasticsearch, Logstash, agent và Kibana để phát hiện nơi làm mất hoặc chậm log như thế nào?
Bạn sẽ chọn metric ingest rate, queue depth, failed events và indexing latency để xây dựng dashboard sức khỏe pipeline ra sao?
Bạn sẽ phân biệt sự cố pipeline mất log với sự cố Kibana chưa hiển thị log bằng phương pháp đo ở từng điểm nào?
Bạn sẽ đối chiếu counter, queue metric và log lỗi qua từng thành phần để tìm nơi thất thoát sự kiện trước Elasticsearch ra sao?
Bạn sẽ điều tra một pipeline đột nhiên tăng độ trễ khi Logstash filter có pattern regex tốn CPU ra sao?
Bạn sẽ kiểm tra sự kiện bị index sai ngày làm dữ liệu xuất hiện ở index không mong đợi như thế nào?
Bạn sẽ xử lý sự kiện timestamp tương lai hoặc quá khứ bất thường mà không làm sai kết quả cảnh báo ra sao?
Bạn sẽ kiểm tra mapping conflict sau khi ứng dụng triển khai schema log mới và lên kế hoạch sửa an toàn như thế nào?
Bạn sẽ nhận biết Elasticsearch bị quá tải do search query trong lúc cần ưu tiên ingest log mới bằng những chỉ số nào?
Bạn sẽ đánh giá tác động của dashboard truy vấn quá nhiều khoảng thời gian dài lên tài nguyên cluster ra sao?
Bạn sẽ chọn quy trình canary cho thay đổi agent policy, Logstash filter hoặc index template nhằm hạn chế lỗi diện rộng như thế nào?
Bạn sẽ xác định cách rollback parser hoặc pipeline khi bản cập nhật làm tăng tỷ lệ document thất bại ra sao?
Bạn sẽ tổ chức kiểm thử tải bằng log mô phỏng để đo thông lượng ingest, queue growth và tài nguyên Elasticsearch ra sao?
Bạn sẽ kiểm tra rằng một bản sửa pipeline vừa khôi phục ingest vừa không tạo document trùng bằng cách nào?
Bạn sẽ xây dựng checklist nghiệm thu hệ thống logging tập trung từ tính đầy đủ, độ trễ, truy vấn đến bảo mật và khôi phục như thế nào?
Nếu agent vẫn healthy nhưng log của một ứng dụng mất từ 30 phút trước, bạn sẽ lần theo file source, registry và đường ingest ra sao?
Nếu stack trace Java bị tách thành nhiều document rời rạc, bạn sẽ điều chỉnh multiline parsing và kiểm tra kết quả như thế nào?
Nếu Logstash queue tăng liên tục trong khi Elasticsearch cluster vẫn green, bạn sẽ khoanh vùng filter, output và tốc độ index ra sao?
Nếu Elasticsearch chuyển sang read-only sau khi ổ đĩa gần đầy, bạn sẽ xử lý an toàn và ngăn sự cố tái diễn như thế nào?
Nếu một thay đổi mapping gây lỗi ingest chỉ cho một phiên bản service, bạn sẽ giữ log, sửa schema và nạp lại dữ liệu ra sao?
Nếu Kibana không thấy log của Pod mới dù agent đã gửi sự kiện, bạn sẽ kiểm tra data stream, time filter và quyền truy cập như thế nào?
Nếu log chứa access token bị phát tán vào Elasticsearch, bạn sẽ phối hợp thu hồi secret, hạn chế truy cập và xử lý dữ liệu tồn tại như thế nào?
Nếu truy vấn Kibana đột nhiên chậm vào giờ cao điểm, bạn sẽ phân biệt quá tải search, merge, shard count và disk I/O ra sao?
Nếu chỉ log ERROR bị thiếu trong khi INFO vẫn tới bình thường, bạn sẽ kiểm tra logic lọc ở ứng dụng, agent và Logstash theo thứ tự nào?
Nếu cluster gặp sự cố mất một vùng trong khi cần giữ khả năng truy vấn log phục vụ ứng cứu, bạn sẽ lựa chọn replication và khôi phục như thế nào?
Bạn sẽ đề xuất kiến trúc ELK Stack cho nền tảng microservices chạy trên Kubernetes với yêu cầu tìm kiếm nhanh, chi phí hợp lý, retention khác nhau và khả năng khôi phục sự cố như thế nào?
