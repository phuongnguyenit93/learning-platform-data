Bạn đánh giá khi nào Elasticsearch phù hợp hơn cơ sở dữ liệu quan hệ cho nhu cầu truy vấn của một ứng dụng như thế nào?
Bạn giải thích mối quan hệ giữa document, index, field và shard trong Elasticsearch ra sao?
Bạn mô tả vai trò của inverted index đối với tìm kiếm toàn văn bằng ví dụ nghiệp vụ nào?
Bạn phân biệt mục tiêu tìm kiếm toàn văn với tra cứu chính xác và phân tích tổng hợp dữ liệu như thế nào?
Bạn xác định nguồn dữ liệu gốc và vai trò của Elasticsearch trong kiến trúc tìm kiếm ra sao?
Bạn diễn giải tính gần thời gian thực của Elasticsearch và hệ quả đối với ứng dụng cần đọc ngay sau khi ghi như thế nào?
Bạn phân biệt thao tác refresh, flush và lưu bền dữ liệu theo những bảo đảm nào?
Bạn thiết kế quy tắc đặt tên index, alias và data stream để dễ quản trị theo môi trường như thế nào?
Bạn cân nhắc một index chung với nhiều index theo tenant hoặc loại dữ liệu trên những tiêu chí nào?
Bạn xác định mức chi tiết của mỗi document từ yêu cầu truy vấn và cập nhật như thế nào?
Bạn thiết kế ID document để tránh ghi trùng khi đồng bộ từ một hệ thống nguồn ra sao?
Bạn xử lý quan hệ một-nhiều khi biểu diễn dữ liệu bằng document Elasticsearch như thế nào?
Bạn đánh giá ưu và nhược điểm của nhúng dữ liệu so với tách document khi dữ liệu thay đổi thường xuyên ra sao?
Bạn quyết định dùng mapping tường minh hay dynamic mapping dựa trên những rủi ro nào?
Bạn kiểm tra kiểu dữ liệu được suy diễn tự động trước khi đưa dữ liệu vào production như thế nào?
Bạn thiết kế dynamic template để kiểm soát các trường mới xuất hiện ra sao?
Bạn chọn kiểu text hay keyword cho một trường dựa trên truy vấn cần hỗ trợ như thế nào?
Bạn dùng multi-fields để hỗ trợ vừa tìm kiếm toàn văn vừa sắp xếp hoặc tổng hợp trên cùng dữ liệu ra sao?
Bạn lựa chọn kiểu số nguyên, số thực hoặc scaled_float cho giá và điểm số dựa trên tiêu chí nào?
Bạn thiết kế trường date khi dữ liệu đến từ nhiều nguồn có định dạng và múi giờ khác nhau như thế nào?
Bạn mô hình hóa trường boolean, IP và các giá trị phân loại để giảm lỗi truy vấn ra sao?
Bạn chọn kiểu object, nested hoặc flattened khi document chứa mảng đối tượng như thế nào?
Bạn chứng minh nguy cơ ghép nhầm các phần tử trong mảng object khi truy vấn như thế nào?
Bạn thiết kế truy vấn nested để bảo đảm các điều kiện cùng thuộc một phần tử mảng ra sao?
Bạn nhận diện rủi ro tăng số lượng field quá mức do JSON có cấu trúc động như thế nào?
Bạn xử lý các field có giá trị null, rỗng hoặc vắng mặt để bộ lọc trả đúng kết quả ra sao?
Bạn cân nhắc bật hoặc tắt indexing và doc_values cho từng field dựa trên nhu cầu nào?
Bạn lựa chọn lưu _source và các field được lưu riêng khi cần truy xuất hoặc hiển thị kết quả như thế nào?
Bạn sử dụng runtime fields khi cần thêm logic truy vấn mà chưa thay đổi dữ liệu đã index ra sao?
Bạn đánh giá chi phí truy vấn của runtime fields so với việc tính sẵn giá trị lúc ingest như thế nào?
Bạn tổ chức index template và component template để các index mới tuân thủ cùng quy ước ra sao?
Bạn thay đổi mapping của một field đã có dữ liệu khi kiểu cũ không còn phù hợp bằng cách nào?
Bạn lập kế hoạch reindex có khả năng kiểm tra đối chiếu và chuyển đổi alias an toàn ra sao?
Bạn thiết kế quy trình phát hành phiên bản mapping khi nhiều ứng dụng đang sử dụng index như thế nào?
Bạn giải thích quá trình analyzer biến văn bản đầu vào thành token trong tìm kiếm ra sao?
Bạn phân biệt character filter, tokenizer và token filter khi thiết kế analyzer như thế nào?
Bạn chọn analyzer cho nội dung tiếng Việt có dấu, không dấu và nhiều cách viết tên riêng ra sao?
Bạn xử lý văn bản đa ngôn ngữ khi mỗi ngôn ngữ cần quy tắc phân tích khác nhau như thế nào?
Bạn đánh giá ảnh hưởng của lowercase, asciifolding và chuẩn hóa Unicode đến kết quả tìm kiếm ra sao?
Bạn dùng stemming và stop words trong trường hợp nào để không làm mất ý nghĩa nghiệp vụ?
Bạn xây dựng quy tắc đồng nghĩa để tăng recall mà không tạo quá nhiều kết quả sai như thế nào?
Bạn phân biệt index-time analyzer với search-time analyzer và lý do cần tách chúng ra sao?
Bạn kiểm thử token sinh ra bằng công cụ analyze trước khi áp dụng analyzer tùy chỉnh như thế nào?
Bạn thiết kế autocomplete bằng edge n-gram, search_as_you_type hoặc completion suggester theo tiêu chí nào?
Bạn cân nhắc n-gram ở thời điểm index so với các truy vấn prefix lúc tìm kiếm ra sao?
Bạn phòng tránh việc wildcard hoặc regexp query gây tăng độ trễ trên dữ liệu lớn bằng cách nào?
Bạn lựa chọn normalizer cho trường keyword cần tìm kiếm không phân biệt hoa thường ra sao?
Bạn thiết kế chức năng tìm kiếm tên người hoặc sản phẩm khi lỗi chính tả xuất hiện thường xuyên như thế nào?
Bạn xử lý thay đổi bộ từ đồng nghĩa khi index đã chứa hàng triệu document ra sao?
Bạn giải thích cấu trúc Query DSL để xây dựng yêu cầu tìm kiếm có nhiều điều kiện như thế nào?
Bạn phân biệt term query và match query theo cách Elasticsearch xử lý dữ liệu tìm kiếm ra sao?
Bạn chọn match_phrase, match hay multi_match để hỗ trợ các kiểu tìm kiếm nội dung như thế nào?
Bạn kết hợp must, should, filter và must_not trong bool query theo mục tiêu truy vấn ra sao?
Bạn xác định minimum_should_match cho yêu cầu tìm kiếm nhiều từ với độ linh hoạt khác nhau như thế nào?
Bạn tách điều kiện lọc không cần tính điểm khỏi điều kiện ảnh hưởng độ liên quan ra sao?
Bạn thiết kế truy vấn có khoảng giá, trạng thái, thời gian và từ khóa mà vẫn giữ hiệu năng như thế nào?
Bạn xử lý truy vấn theo field lồng nhau với điều kiện lọc nhiều thuộc tính trong một nested document ra sao?
Bạn xác định khi nào truy vấn exists có thể phản ánh sai ý nghĩa của dữ liệu thiếu hoặc rỗng?
Bạn thiết kế lọc dữ liệu theo khu vực bằng geo_point và các truy vấn địa lý như thế nào?
Bạn lựa chọn sắp xếp theo điểm liên quan, thời gian hay tín hiệu nghiệp vụ trong từng màn hình tìm kiếm ra sao?
Bạn giải thích tác động của BM25 và thống kê tần suất từ tới thứ tự kết quả như thế nào?
Bạn đánh giá sự khác biệt giữa độ chính xác và độ bao phủ khi điều chỉnh truy vấn tìm kiếm ra sao?
Bạn áp dụng boosting cho field tiêu đề, mô tả và thẻ nội dung dựa trên những quan sát nào?
Bạn dùng function_score hoặc các cách điều chỉnh điểm để kết hợp độ liên quan với độ phổ biến ra sao?
Bạn hạn chế một tín hiệu kinh doanh lấn át độ liên quan văn bản bằng cách nào?
Bạn dùng explain để tìm hiểu vì sao một document được xếp hạng cao hơn document khác như thế nào?
Bạn tổ chức bộ truy vấn đánh giá relevance với ví dụ đúng, sai và kỳ vọng xếp hạng ra sao?
Bạn chọn các thước đo như precision, recall, MRR hoặc NDCG để đánh giá chất lượng tìm kiếm như thế nào?
Bạn phân tích trường hợp kết quả đứng đầu sai dù người dùng nhập chính xác tên sản phẩm ra sao?
Bạn thiết kế chiến lược xử lý truy vấn không trả kết quả và gợi ý mở rộng phạm vi tìm kiếm như thế nào?
Bạn dùng highlighting để hiển thị đoạn khớp và tránh ảnh hưởng đến hiệu năng truy vấn ra sao?
Bạn chọn suggesters phù hợp với gợi ý sửa chính tả hoặc gợi ý cụm từ như thế nào?
Bạn phân biệt các chiến lược phân trang from/size và search_after khi số kết quả lớn ra sao?
Bạn phối hợp point in time với search_after để phân trang ổn định khi dữ liệu được cập nhật liên tục như thế nào?
Bạn giải quyết việc document đổi thứ tự giữa hai lần lấy trang kết quả bằng cách nào?
Bạn xác định trường hợp sử dụng scroll hoặc phương án đọc dữ liệu hàng loạt thay vì phân trang giao diện như thế nào?
Bạn hạn chế số lượng kết quả và trường trả về để giảm băng thông và thời gian phản hồi như thế nào?
Bạn sử dụng profiling để xác định phần truy vấn hoặc aggregation chiếm nhiều tài nguyên ra sao?
Bạn phân tích một truy vấn có điểm số đúng nhưng độ trễ tăng mạnh sau khi dữ liệu lớn lên như thế nào?
Bạn thiết kế bộ lọc và sắp xếp có thể tái sử dụng mà không vô tình thay đổi ngữ nghĩa tìm kiếm ra sao?
Bạn sử dụng aggregations để chuyển kết quả tìm kiếm thành số liệu thống kê theo yêu cầu nghiệp vụ như thế nào?
Bạn phân biệt bucket aggregation, metric aggregation và pipeline aggregation qua các bài toán nào?
Bạn thiết kế terms aggregation khi field có rất nhiều giá trị phân biệt như thế nào?
Bạn nhận diện sai số hoặc kết quả thiếu trong terms aggregation phân tán trên nhiều shard ra sao?
Bạn chọn composite aggregation khi cần duyệt đầy đủ nhiều nhóm kết quả như thế nào?
Bạn sử dụng date_histogram để thống kê theo ngày, tuần hoặc tháng có xét múi giờ ra sao?
Bạn thiết kế bộ lọc faceted search khi người dùng liên tục chọn và bỏ chọn các thuộc tính như thế nào?
Bạn phân biệt cardinality aggregation với việc đếm giá trị phân biệt chính xác trong trường hợp nào?
Bạn đánh giá sai số chấp nhận được khi ước lượng số lượng người dùng hoặc sản phẩm duy nhất ra sao?
Bạn sử dụng percentiles và histogram để quan sát phân phối thay vì chỉ trung bình như thế nào?
Bạn thiết kế một báo cáo kết hợp các nhóm và phép tính dẫn xuất bằng pipeline aggregation ra sao?
Bạn kiểm tra sự khác biệt giữa tổng hợp trên document gốc và nested document như thế nào?
Bạn lựa chọn top_hits hoặc top_metrics để lấy đại diện của một nhóm dựa trên nhu cầu nào?
Bạn kiểm soát giới hạn bucket, bộ nhớ và thời gian thực thi của aggregation phức tạp ra sao?
Bạn quyết định khi nào nên tính trước kết quả phân tích hoặc dùng index chuyên biệt cho báo cáo như thế nào?
Bạn thiết kế ingest pipeline để chuẩn hóa và làm sạch document trước khi index như thế nào?
Bạn lựa chọn các bước gán trường, chuyển kiểu, xử lý lỗi và loại bỏ dữ liệu nhạy cảm trong ingest pipeline ra sao?
Bạn xử lý document lỗi định dạng khi nạp dữ liệu hàng loạt mà không làm mất khả năng truy vết như thế nào?
Bạn thiết kế bulk indexing với kích thước batch và số luồng phù hợp theo những tín hiệu nào?
Bạn đánh giá tác động của refresh interval và replica lên tốc độ nạp dữ liệu như thế nào?
Bạn xử lý một phần thao tác Bulk thành công và một phần thất bại như thế nào?
Bạn xây dựng đồng bộ tăng dần từ cơ sở dữ liệu nguồn sang Elasticsearch bằng cách nào?
Bạn giải quyết sự kiện cập nhật đến sai thứ tự khi hai bản ghi cùng một document được xử lý song song ra sao?
Bạn lựa chọn update, upsert hay ghi đè document khi nhận sự kiện thay đổi dữ liệu như thế nào?
Bạn sử dụng cơ chế kiểm soát phiên bản hoặc optimistic concurrency để tránh ghi đè dữ liệu mới bằng cách nào?
Bạn thiết kế quy trình kiểm tra độ lệch giữa dữ liệu nguồn và index tìm kiếm ra sao?
Bạn xác định thời điểm và cách xóa document khi nguồn đã xóa hoặc vô hiệu hóa bản ghi như thế nào?
Bạn đánh giá chi phí cập nhật thường xuyên các document chứa nhiều đối tượng lồng nhau ra sao?
Bạn thiết kế ánh xạ dữ liệu sản phẩm có nhiều biến thể, mức giá và tồn kho thay đổi nhanh như thế nào?
Bạn xác định mức độ chấp nhận dữ liệu cũ trong kết quả tìm kiếm khi pipeline đồng bộ bị chậm ra sao?
Bạn phân biệt tìm kiếm từ khóa với tìm kiếm ngữ nghĩa bằng vector theo những trường hợp nào?
Bạn xác định cách tạo embedding cho tiêu đề, mô tả và nội dung dài của document ra sao?
Bạn chọn độ đo tương đồng vector dựa trên mô hình embedding và yêu cầu ứng dụng như thế nào?
Bạn thiết kế mapping vector với số chiều và cách tổ chức metadata phù hợp ra sao?
Bạn giải thích đánh đổi giữa tìm kiếm vector chính xác và approximate k-nearest neighbors như thế nào?
Bạn đánh giá ảnh hưởng của số lượng vector và cấu trúc chỉ mục gần đúng đến bộ nhớ và độ trễ ra sao?
Bạn kết hợp điều kiện lọc metadata với truy vấn kNN để tránh trả kết quả ngoài phạm vi như thế nào?
Bạn xây dựng hybrid search kết hợp truy vấn lexical và vector như thế nào?
Bạn điều chỉnh trọng số hoặc dùng phương pháp hợp nhất thứ hạng để kết hợp hai nhóm kết quả ra sao?
Bạn thiết kế quy trình đánh giá offline cho tìm kiếm ngữ nghĩa bằng bộ câu hỏi thực tế như thế nào?
Bạn kiểm tra tác động của embedding sai ngôn ngữ hoặc sai miền dữ liệu lên chất lượng tìm kiếm ra sao?
Bạn lên phương án tái tạo embedding và chuyển đổi index khi thay đổi mô hình vector như thế nào?
Bạn cân nhắc chi phí lưu trữ vector, nạp dữ liệu và truy vấn khi tăng số chiều như thế nào?
Bạn xử lý trường hợp truy vấn có nhiều từ khóa định danh mà tìm kiếm vector trả về kết quả kém chính xác ra sao?
Bạn tổ chức bước reranking cho tập ứng viên nhỏ và đánh giá ảnh hưởng đến độ trễ như thế nào?
Bạn quyết định khi nào nên ưu tiên lexical search, vector search hoặc hybrid search theo hành vi người dùng ra sao?
Bạn lựa chọn số primary shard ban đầu dựa trên dung lượng, tốc độ tăng dữ liệu và đặc điểm truy vấn như thế nào?
Bạn giải thích vai trò của replica trong tính sẵn sàng và mở rộng đọc như thế nào?
Bạn diễn giải các trạng thái sức khỏe green, yellow và red của cluster và hành động phù hợp ra sao?
Bạn kiểm tra lý do một shard không được phân bổ bằng các thông tin vận hành nào?
Bạn đánh giá tình huống quá nhiều shard nhỏ và tác động đến heap, metadata và hiệu năng ra sao?
Bạn lựa chọn data tier và chính sách phân bổ shard phù hợp với vòng đời dữ liệu như thế nào?
Bạn thiết kế rollover cho index sự kiện theo kích thước, số document hoặc thời gian như thế nào?
Bạn tổ chức index lifecycle management để dữ liệu cũ chuyển tầng hoặc bị xóa đúng hạn ra sao?
Bạn cân nhắc dùng data stream so với index thông thường cho dữ liệu chuỗi thời gian như thế nào?
Bạn kiểm tra việc ILM bị kẹt và xác định bước xử lý an toàn ra sao?
Bạn chọn chiến lược scale up hay scale out khi khối lượng tìm kiếm tăng như thế nào?
Bạn tìm nguyên nhân một node dùng CPU cao dù tổng tải toàn cluster không đổi bằng cách nào?
Bạn đánh giá tác động của segment merge lên tốc độ ghi, I/O và latency tìm kiếm như thế nào?
Bạn kiểm soát bộ nhớ JVM heap, filesystem cache và circuit breaker để tránh lỗi quá tải ra sao?
Bạn phân tích kết quả slow log và các chỉ số search thread pool để tìm truy vấn gây nghẽn như thế nào?
Bạn phát hiện hotspot do routing hoặc phân bố shard không đều bằng cách nào?
Bạn thiết kế shard routing cho dữ liệu nhiều tenant và cân nhắc rủi ro khi một tenant tăng trưởng đột biến ra sao?
Bạn lựa chọn giới hạn tài nguyên và cơ chế từ chối truy vấn quá nặng khi hệ thống quá tải như thế nào?
Bạn lập kế hoạch snapshot repository và lịch sao lưu đáp ứng mục tiêu phục hồi như thế nào?
Bạn kiểm chứng snapshot và thực hành restore để bảo đảm có thể khôi phục index sau sự cố ra sao?
Bạn xây dựng phương án khôi phục khi một số shard mất dữ liệu và cluster cần đưa dịch vụ hoạt động trở lại như thế nào?
Bạn lập kế hoạch nâng cấp phiên bản Elasticsearch có kiểm tra tương thích index, client và plugin ra sao?
Bạn đánh giá rủi ro của việc chạy reindex hoặc thay đổi alias khi cluster đang chịu tải lớn như thế nào?
Bạn thiết kế xác thực, TLS và phân quyền truy cập Elasticsearch cho các ứng dụng khác nhau như thế nào?
Bạn phân biệt quyền đọc document, quản lý index và quản trị cluster khi cấp role như thế nào?
Bạn áp dụng cơ chế giới hạn truy cập theo document hoặc field cho dữ liệu nhiều đối tượng sử dụng ra sao?
Bạn xử lý dữ liệu cá nhân cần xóa khỏi index, snapshot và hệ thống nguồn theo chính sách nào?
Bạn hạn chế việc lộ thông tin qua truy vấn, log và kết quả highlight bằng cách nào?
Bạn bảo vệ cụm Elasticsearch trước truy vấn tự do hoặc yêu cầu aggregation quá lớn từ người dùng như thế nào?
Bạn lựa chọn cách kết nối Java API Client và cấu hình endpoint, chứng chỉ cùng thông tin xác thực như thế nào?
Bạn xử lý phiên bản Elasticsearch server và Java client để tránh lỗi tương thích như thế nào?
Bạn tổ chức lớp truy cập Elasticsearch trong ứng dụng Java để tách truy vấn tìm kiếm khỏi nghiệp vụ ra sao?
Bạn chọn Spring Data Elasticsearch repositories hoặc client trực tiếp dựa trên độ phức tạp truy vấn như thế nào?
Bạn ánh xạ entity Java với mapping index mà vẫn kiểm soát phiên bản và các trường bổ sung ra sao?
Bạn xây dựng bool query, sorting và aggregation từ đầu vào người dùng bằng Java như thế nào?
Bạn xử lý timeout, retry và thất bại một phần khi Java client gửi yêu cầu đến cluster ra sao?
Bạn tích hợp Bulk API trong ứng dụng Java và quản lý backpressure cùng retry như thế nào?
Bạn thiết kế kiểm thử tích hợp có dữ liệu và mapping thật để kiểm tra độ liên quan truy vấn ra sao?
Bạn thu thập trace và metrics từ ứng dụng Java để phân biệt chậm do client, mạng hay Elasticsearch như thế nào?
Bạn kiểm chứng hiệu năng tìm kiếm bằng dữ liệu đại diện và kế hoạch tải trước khi đưa vào production như thế nào?
Bạn phân tích nguyên nhân thời gian tìm kiếm tăng sau khi thêm nhiều bộ lọc và aggregation như thế nào?
Bạn đưa ra lộ trình điều tra khi một truy vấn có kết quả khác nhau giữa môi trường thử nghiệm và production ra sao?
Bạn thiết kế tìm kiếm thương mại điện tử có bộ lọc biến thể, sắp xếp giá và xếp hạng sản phẩm như thế nào?
Bạn thiết kế tìm kiếm tài liệu nội bộ có phân quyền truy cập, đồng nghĩa và gợi ý truy vấn như thế nào?
Bạn triển khai tìm kiếm nhật ký sự kiện theo thời gian với chính sách lưu trữ và giới hạn chi phí như thế nào?
Bạn chọn tiêu chí nào để chứng minh một hệ thống Elasticsearch vừa trả kết quả liên quan vừa đạt yêu cầu vận hành và bảo mật?
