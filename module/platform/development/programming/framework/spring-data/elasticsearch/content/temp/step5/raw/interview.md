Bạn giải thích Elasticsearch giải quyết bài toán tìm kiếm nào mà truy vấn SQL thông thường khó đáp ứng hiệu quả?
Bạn phân biệt Elasticsearch là search engine với hệ quản trị dữ liệu giao dịch làm nguồn sự thật như thế nào?
Bạn đánh giá khi nào dùng Elasticsearch chỉ làm read model thay vì lưu bản dữ liệu nghiệp vụ duy nhất?
Bạn mô tả sự khác nhau giữa index, document và field trong mô hình Elasticsearch ra sao?
Bạn phân biệt primary shard và replica shard về lưu trữ, tìm kiếm và chịu lỗi như thế nào?
Bạn giải thích việc phân bố document vào shard theo routing key ảnh hưởng đến hiệu năng ra sao?
Bạn lựa chọn số primary shards ban đầu dựa trên dung lượng, tốc độ ghi và truy vấn như thế nào?
Bạn đánh giá rủi ro tạo quá nhiều shards nhỏ trên một cluster có số node hạn chế?
Bạn phân biệt horizontal scaling cho indexing với horizontal scaling cho search workloads như thế nào?
Bạn giải thích vai trò của coordinating node khi một truy vấn tìm kiếm cần đọc nhiều shards?
Bạn mô tả bước query phase và fetch phase trong tìm kiếm phân tán của Elasticsearch ra sao?
Bạn phân biệt khả năng chịu lỗi khi mất replica shard với khi mất toàn bộ bản sao của primary shard như thế nào?
Bạn đánh giá ý nghĩa của trạng thái cluster green, yellow và red đối với ứng dụng Spring Boot?
Bạn thiết kế cơ chế graceful degradation khi Elasticsearch tạm không khả dụng nhưng dữ liệu gốc vẫn còn?
Bạn phân biệt refresh, flush và merge trong vòng đời dữ liệu index như thế nào?
Bạn giải thích vì sao document vừa ghi thành công có thể chưa xuất hiện trong kết quả search ngay lập tức?
Bạn xác định những business operations nào yêu cầu read-after-write và cách cân nhắc chi phí để đáp ứng?
Bạn phân biệt real-time document GET với near-real-time search về khả năng nhìn thấy dữ liệu mới ra sao?
Bạn đánh giá trade-off giữa tốc độ indexing và search latency khi cùng cluster phục vụ hai workload?
Bạn lựa chọn chiến lược lưu trữ dữ liệu lịch sử với index theo thời gian hay index chung dựa trên nhu cầu nào?
Bạn xác định khi nào nên bổ sung Elasticsearch bên cạnh cơ sở dữ liệu quan hệ để phục vụ full-text search?
Bạn thiết kế luồng dữ liệu từ transactional database sang Elasticsearch để tránh Elasticsearch giữ vai trò transaction coordinator như thế nào?
Bạn phân biệt source data và materialized search document khi một index kết hợp dữ liệu từ nhiều bảng ra sao?
Bạn đánh giá cách quản trị độ trễ đồng bộ từ database sang index theo yêu cầu freshness của người dùng?
Bạn xác định những metrics cần theo dõi để biết truy vấn Elasticsearch đã vượt ngân sách độ trễ?
Bạn tổ chức dependency Spring Data Elasticsearch tương thích với Spring Boot và Elasticsearch server theo cách nào?
Bạn phân biệt Spring Data Elasticsearch với Elasticsearch Java client về vai trò mapping và truy vấn ra sao?
Bạn lựa chọn repository abstraction hay ElasticsearchOperations cho một use case tìm kiếm theo tiêu chí nào?
Bạn kiểm tra Spring Boot auto-configuration cung cấp Elasticsearch client và template nào theo phiên bản đang dùng?
Bạn cấu hình danh sách cluster endpoints mà không hardcode địa chỉ node vào business service như thế nào?
Bạn thiết kế cấu hình SSL/TLS cho kết nối Spring Boot tới Elasticsearch production ra sao?
Bạn quản lý API key hoặc service credential để tránh đưa secret vào source code và log như thế nào?
Bạn xác định thời điểm nên dùng nhiều Elasticsearch clients trong cùng ứng dụng theo cluster hoặc quyền truy cập?
Bạn tránh tạo mới HTTP client cho mỗi truy vấn bằng cách tổ chức lifecycle bean như thế nào?
Bạn phân biệt connection timeout, socket timeout và deadline của một yêu cầu tìm kiếm ra sao?
Bạn thiết kế connection pooling và giới hạn requests đồng thời để bảo vệ cluster khi traffic tăng?
Bạn kiểm tra ứng dụng đang kết nối đúng cluster và index alias ở staging hoặc production bằng cách nào?
Bạn quản lý cấu hình index names theo môi trường mà không thay đổi model nghiệp vụ ra sao?
Bạn phân biệt cấu hình dùng cho blocking ElasticsearchOperations với ReactiveElasticsearchOperations về luồng thực thi?
Bạn lựa chọn imperative hoặc reactive Elasticsearch access theo loại Spring web stack nào?
Bạn xác định rủi ro gọi blocking client trên event-loop của WebFlux như thế nào?
Bạn kiểm tra hỗ trợ và giới hạn reactive client trong phiên bản Spring Data Elasticsearch đang triển khai ra sao?
Bạn tổ chức custom client configuration khi cần proxy, certificate authority hoặc authentication đặc thù?
Bạn đo connection pool saturation khác với cluster search latency bằng những tín hiệu nào?
Bạn xử lý thay đổi URL, credentials hoặc certificate khi ứng dụng đang chạy nhiều replica như thế nào?
Bạn đánh giá tác động của retry ở tầng HTTP client khi node Elasticsearch trả 429 hoặc 503?
Bạn xây dựng health check Elasticsearch sao cho không khiến liveness của ứng dụng phụ thuộc vào cluster chung?
Bạn quyết định khi nào không nên chặn startup chỉ vì index tìm kiếm tạm thời chưa sẵn sàng?
Bạn sử dụng @ConfigurationProperties và validation để tránh tên index hoặc timeout cấu hình không hợp lệ như thế nào?
Bạn kiểm tra version compatibility trước khi nâng Spring Data Elasticsearch hoặc Java client theo quy trình nào?
Bạn xác định cách giới hạn quyền của application credential chỉ được truy vấn những indices cần thiết ra sao?
Bạn ánh xạ một Elasticsearch index bằng @Document và Java entity như thế nào?
Bạn phân biệt @Id của Spring Data Elasticsearch với một business identifier trong nguồn dữ liệu gốc?
Bạn quyết định dùng document ID tự sinh hay ID ổn định từ transactional database theo yêu cầu nào?
Bạn thiết kế entity search riêng với JPA entity để tránh rò rỉ cấu trúc persistence như thế nào?
Bạn xác định mapping @Field cho text, keyword, numeric, date và boolean theo mục tiêu truy vấn?
Bạn phân biệt FieldType.Text và FieldType.Keyword về analysis, match và exact filtering như thế nào?
Bạn đánh giá hậu quả khi một trường tên sản phẩm được mapping keyword nhưng API cần tìm kiếm theo từ?
Bạn thiết kế multi-fields để cùng một giá trị hỗ trợ full-text search và sorting/aggregation ra sao?
Bạn lựa chọn index analyzer và search analyzer riêng cho cùng một field dựa trên đặc điểm ngôn ngữ và truy vấn nào?
Bạn kiểm soát định dạng ngày giờ và timezone khi mapping Instant hoặc ZonedDateTime vào date field như thế nào?
Bạn kiểm thử mapping số tiền để không mất precision khi lưu và filter khoảng giá ra sao?
Bạn phân biệt object field với nested field khi document chứa mảng các đối tượng con như thế nào?
Bạn giải thích vì sao truy vấn trên object array có thể match nhầm thuộc tính của hai phần tử khác nhau?
Bạn thiết kế nested mapping khi API cần lọc theo nhiều thuộc tính thuộc cùng một phần tử như thế nào?
Bạn đánh giá chi phí bộ nhớ và số Lucene documents phát sinh khi dùng nested fields nhiều?
Bạn quyết định khi nào nên denormalize dữ liệu liên quan vào một search document thay vì dùng join field?
Bạn phân tích giới hạn của parent-child join so với index document phẳng theo hiệu năng và mô hình cập nhật?
Bạn sử dụng @Setting hoặc cấu hình index settings tùy phiên bản để chỉ định analyzer như thế nào?
Bạn kiểm tra index mapping thực tế có khớp với annotations của entity sau khi triển khai?
Bạn phân biệt dynamic mapping với explicit mapping về tính kiểm soát schema và lỗi kiểu dữ liệu ra sao?
Bạn thiết kế dynamic templates khi một số thuộc tính có tên linh hoạt nhưng cần kiểm soát field types?
Bạn đánh giá nguy cơ mapping explosion khi index nhận dữ liệu JSON có hàng nghìn field keys?
Bạn chọn enabled false hoặc cách giữ dữ liệu không index đối với trường chỉ cần hiển thị như thế nào?
Bạn phân biệt _source với các trường đã index để tìm kiếm, sort hoặc aggregation ra sao?
Bạn thiết kế source filtering để chỉ trả fields cần thiết cho danh sách kết quả như thế nào?
Bạn sử dụng các converter tùy chỉnh khi Java value object không ánh xạ trực tiếp sang Elasticsearch field ra sao?
Bạn kiểm tra round-trip entity conversion cho enum, collection và object lồng nhau như thế nào?
Bạn xác định rủi ro khi thay type của một field trong cùng index sau khi đã có dữ liệu như thế nào?
Bạn xây dựng kế hoạch tạo index mới và reindex khi mapping của field không thể sửa trực tiếp ra sao?
Bạn thiết kế versioned index mapping để nhiều phiên bản ứng dụng cùng đọc được trong rolling deployment?
Bạn phân biệt entity validation trước khi index với mapping validation của Elasticsearch ra sao?
Bạn quản lý một field chứa PII nhưng không được lập chỉ mục hoặc hiển thị trong kết quả như thế nào?
Bạn quyết định có bật lưu _source cho dữ liệu tìm kiếm theo yêu cầu retrieval và bảo mật nào?
Bạn thiết kế document lưu kết quả tổng hợp từ nhiều nguồn mà vẫn có thể cập nhật theo từng business event như thế nào?
Bạn kiểm soát tình huống giá trị null và missing field dẫn đến filter không như người dùng mong đợi ra sao?
Bạn phân biệt repository ElasticsearchRepository với CrudRepository trên database giao dịch về ngữ nghĩa thao tác?
Bạn thiết kế ElasticsearchRepository cho một @Document entity có ID ổn định như thế nào?
Bạn đánh giá khi nào derived query methods phù hợp hơn một query được định nghĩa tường minh?
Bạn kiểm tra tên method repository sinh truy vấn text hoặc term đúng với field mapping như thế nào?
Bạn xử lý một derived query tìm kiếm theo tên nhưng kết quả sai vì analyzer hoặc field type ra sao?
Bạn lựa chọn @Query và câu truy vấn JSON khi repository method name trở nên khó biểu đạt như thế nào?
Bạn kiểm soát input người dùng khi dùng @Query để tránh tạo câu truy vấn nguy hiểm hoặc không hợp lệ ra sao?
Bạn thiết kế repository chỉ expose các truy vấn phù hợp với contract tìm kiếm của ứng dụng như thế nào?
Bạn phân biệt findById với search query về refresh visibility và truy cập document như thế nào?
Bạn thiết kế hành vi khi document không tồn tại nhưng bản ghi gốc vẫn có trong database ra sao?
Bạn quyết định dùng save hay partial update khi document có nhiều trường ít thay đổi theo các tần suất khác nhau?
Bạn đánh giá nguy cơ save một search entity bị thiếu fields làm ghi đè document đầy đủ như thế nào?
Bạn thiết kế idempotent indexing với document ID cố định để message giao lại không tạo bản sao trùng?
Bạn phân biệt deleteById và delete-by-query về độ an toàn, tác động và tải cluster?
Bạn kiểm tra thao tác delete báo thành công nhưng search vẫn trả document trong khoảng refresh delay như thế nào?
Bạn tổ chức service layer để API không phụ thuộc trực tiếp vào loại SearchHits của Spring Data ra sao?
Bạn thiết kế mapping từ search hit về response DTO kèm score và highlight khi cần như thế nào?
Bạn phân biệt SearchHit và SearchHits với danh sách entities thuần trong ElasticsearchOperations ra sao?
Bạn sử dụng SearchPage hoặc các wrapper tương ứng để truyền pagination metadata theo phiên bản hỗ trợ như thế nào?
Bạn kiểm chứng repository query về thứ tự kết quả khi không có sort hoặc score mong muốn ra sao?
Bạn xử lý trường hợp repository method dùng Page nhưng total hits là approximation theo request settings như thế nào?
Bạn xác định chi phí của count query khi UI yêu cầu tổng số kết quả chính xác ra sao?
Bạn đánh giá giới hạn repository abstraction khi cần aggregation, collapse hoặc custom highlighting?
Bạn thiết kế test repository dựa trên Elasticsearch thực để không đánh giá sai query semantics?
Bạn lựa chọn ElasticsearchOperations thay cho repository khi truy vấn cần bool, nested hoặc aggregation phức tạp như thế nào?
Bạn phân biệt thao tác quản lý index qua IndexOperations với thao tác đọc/ghi document qua ElasticsearchOperations ra sao?
Bạn sử dụng indexOps để kiểm tra hoặc tạo index và mapping theo quy trình deployment nào?
Bạn xác định khi nào không được để ứng dụng tự xóa hoặc tạo lại index trong production?
Bạn lựa chọn IndexCoordinates để truy cập index cụ thể hoặc alias phù hợp với từng use case như thế nào?
Bạn xây dựng CriteriaQuery cho filter đơn giản dựa trên field type thực tế ra sao?
Bạn thiết kế NativeQuery cho bool query kết hợp full-text, filter và sort theo những yêu cầu nào?
Bạn kiểm tra API xây NativeQuery tương thích với phiên bản Spring Data Elasticsearch đang sử dụng như thế nào?
Bạn lựa chọn dùng Elasticsearch Java client query DSL khi abstraction Spring Data chưa hỗ trợ một tính năng mới ra sao?
Bạn phân biệt Query object của Spring Data với JSON DSL được Elasticsearch nhận cuối cùng như thế nào?
Bạn ghi lại request query có cấu trúc để debug mà không đưa PII hoặc secret vào log ra sao?
Bạn sử dụng ElasticsearchOperations.search để lấy SearchHits và metadata phù hợp như thế nào?
Bạn xác định khi nào chỉ cần count hoặc exists thay vì search và lấy toàn bộ documents ra sao?
Bạn thiết kế update-by-query cho một chiến dịch sửa dữ liệu mà vẫn kiểm soát số document bị tác động?
Bạn đánh giá vì sao update-by-query có thể gặp version conflicts khi index đang được cập nhật đồng thời?
Bạn lựa chọn reindex API của Elasticsearch hay chạy pipeline từ database gốc để tái dựng một index ra sao?
Bạn thiết kế multi-search khi một trang cần nhiều danh sách kết quả độc lập để giảm overhead như thế nào?
Bạn đánh giá rủi ro gửi hàng trăm subqueries trong một msearch request đối với tài nguyên cluster?
Bạn cấu hình routing theo tenant để giới hạn số shards phải truy vấn và bảo vệ nhất quán ID như thế nào?
Bạn kiểm tra routing khi đọc, ghi và xóa document có được sử dụng nhất quán ra sao?
Bạn phân biệt search across indices với search riêng một alias về scope và quyền dữ liệu như thế nào?
Bạn thiết kế layer chuyển lỗi Elasticsearch thành mã lỗi HTTP phù hợp và thông tin cần retry?
Bạn xử lý index_not_found_exception khác với zero search hits như thế nào?
Bạn đánh giá khi nào nên chuyển sang API tìm kiếm bất đồng bộ để tránh giữ kết nối HTTP quá lâu?
Bạn xác định cách truyền cancellation đến truy vấn search còn chạy khi client đã hủy request?
Bạn phân biệt full-text match query và term query theo cách xử lý tokens như thế nào?
Bạn thiết kế filter chính xác theo keyword thay vì match query cho mã sản phẩm ra sao?
Bạn giải thích tác dụng của bool must, should, filter và must_not lên tập kết quả và score như thế nào?
Bạn quyết định chuyển điều kiện vào filter context để không tính điểm khi nào?
Bạn tổ chức truy vấn có nhiều điều kiện optional mà không làm should thay đổi tập kết quả ngoài ý muốn như thế nào?
Bạn xác định tác động của minimum_should_match khi kết hợp nhiều terms hoặc clauses ra sao?
Bạn phân biệt match, multi_match và match_phrase theo yêu cầu tìm tên hoặc mô tả sản phẩm như thế nào?
Bạn chọn match_phrase khi thứ tự và khoảng cách giữa các từ mang ý nghĩa nghiệp vụ ra sao?
Bạn thiết kế tìm kiếm qua nhiều fields với trọng số tên, thương hiệu và mô tả như thế nào?
Bạn đánh giá nguy cơ dùng wildcard hoặc regexp trên dữ liệu lớn làm chậm truy vấn ra sao?
Bạn lựa chọn prefix, edge n-gram hoặc search-as-you-type cho tính năng autocomplete theo tiêu chí nào?
Bạn phân biệt fuzzy matching với synonym matching khi xử lý lỗi chính tả hoặc tên gọi tương đương như thế nào?
Bạn kiểm soát fuzziness để kết quả tìm kiếm không quá nhiễu với từ ngắn ra sao?
Bạn thiết kế truy vấn range cho giá hoặc thời gian theo đúng numeric/date mapping như thế nào?
Bạn phân biệt exists query với filter theo null trong cách Elasticsearch lưu trường không có giá trị ra sao?
Bạn áp dụng nested query để chỉ match thuộc tính cùng một object con như thế nào?
Bạn xác minh nested query không tạo false positive từ hai object con khác nhau bằng test nào?
Bạn tổ chức filter nhiều tenant và quyền xem dữ liệu trước khi thêm scoring clauses ra sao?
Bạn phân biệt query-time filtering và application post-filtering về rủi ro lộ dữ liệu và phân trang?
Bạn giới hạn những fields client được phép dùng để sort hoặc filter để tránh query abuse như thế nào?
Bạn xây dựng API tìm kiếm hỗn hợp keyword, facets, price range và sort mà vẫn kiểm soát độ phức tạp ra sao?
Bạn xử lý yêu cầu search từ user có ký tự đặc biệt khi dùng query_string so với match query như thế nào?
Bạn đánh giá rủi ro cho phép người dùng gửi thẳng JSON query DSL tới cluster ra sao?
Bạn thiết kế default query khi người dùng không nhập từ khóa nhưng vẫn cần lọc theo trạng thái ra sao?
Bạn phân biệt match_all với term filter trống và những nguy cơ quét dữ liệu ngoài ý muốn như thế nào?
Bạn chọn cách xử lý dấu câu, dấu tiếng Việt và chữ hoa/thường để kết quả tìm kiếm nhất quán?
Bạn giải thích analyzer gồm character filters, tokenizer và token filters hoạt động ở những giai đoạn nào?
Bạn phân biệt index-time analyzer với search-time analyzer trong Elasticsearch như thế nào?
Bạn kiểm tra tokens được sinh bởi analyzer bằng Analyze API và so sánh với query thực tế ra sao?
Bạn thiết kế analyzer cho tiếng Việt có dấu và không dấu dựa trên dữ liệu thử nghiệm như thế nào?
Bạn đánh giá trade-off khi bỏ dấu tiếng Việt đối với recall và những từ khác nghĩa?
Bạn lựa chọn lowercasing hoặc asciifolding khi tên thương hiệu chứa ký tự đặc biệt như thế nào?
Bạn phân biệt tokenization theo khoảng trắng với language-aware analysis trong tìm kiếm đa ngôn ngữ ra sao?
Bạn xử lý synonym rules ở index-time hoặc search-time theo yêu cầu cập nhật từ điển như thế nào?
Bạn đánh giá rủi ro synonym expansion làm tăng false positives cho tên sản phẩm ngắn?
Bạn thiết kế stopword filtering mà không làm mất những cụm từ quan trọng như thế nào?
Bạn xác định trường hợp stemming hữu ích và trường hợp làm mất nghĩa từ chuyên môn ra sao?
Bạn so sánh standard analyzer, custom analyzer và normalizer cho các trường khác nhau như thế nào?
Bạn phân biệt normalizer cho keyword field với analyzer cho text field về token output ra sao?
Bạn xử lý yêu cầu tìm kiếm không phân biệt hoa thường trên keyword field theo mapping nào?
Bạn lựa chọn n-gram hoặc edge n-gram và đánh giá chi phí tăng kích thước index ra sao?
Bạn thiết kế autocomplete tránh đưa một lượng lớn n-gram vào field không cần thiết như thế nào?
Bạn kiểm tra analyzer changes có đòi hỏi reindex hay không theo tính chất thay đổi nào?
Bạn tổ chức A/B test analyzer mới trên bộ truy vấn thực tế trước khi đổi index alias như thế nào?
Bạn xác định cách chọn field boost khi title quan trọng hơn description theo thống kê nào?
Bạn giải thích BM25 ước lượng mức phù hợp văn bản từ term frequency, document frequency và độ dài field như thế nào?
Bạn phân biệt Elasticsearch _score với xác suất khách hàng nhấp hoặc mua một sản phẩm ra sao?
Bạn đánh giá vì sao cùng một query có thể cho score khác giữa indices hoặc shards có thống kê khác nhau?
Bạn thiết kế ranking kết hợp text relevance, độ mới, mức phổ biến và business priority như thế nào?
Bạn kiểm soát tác động của function_score hoặc các scoring functions để tránh một tín hiệu lấn át toàn bộ ranking ra sao?
Bạn quyết định khi nào dùng rescore với cửa sổ top results thay vì tính toán đắt trên mọi document?
Bạn đánh giá chi phí script_score khi nhiều kết quả được chấm điểm theo phép tính tùy chỉnh?
Bạn xây dựng bộ dữ liệu đánh giá ranking có câu truy vấn, nhãn relevance và kết quả mong đợi ra sao?
Bạn dùng precision@K, recall@K, MRR hoặc nDCG để so sánh hai cách xếp hạng như thế nào?
Bạn phân biệt offline relevance metrics với online CTR hoặc conversion trong quyết định release ranking ra sao?
Bạn thiết kế search tuning khi tăng recall lại làm precision của top results giảm như thế nào?
Bạn xử lý kết quả cùng score bằng secondary sort để phân trang ổn định ra sao?
Bạn lựa chọn sort theo _score, giá hoặc ngày cập nhật theo intent của người dùng như thế nào?
Bạn đánh giá memory và disk cost khi sort hoặc aggregate trên keyword fields có cardinality cao?
Bạn thiết kế field collapsing để gộp nhiều biến thể của cùng một sản phẩm theo business ID như thế nào?
Bạn kiểm tra tác động của nested documents tới score của parent search hit như thế nào?
Bạn định nghĩa explain hoặc profile query trong môi trường kiểm thử để hiểu kết quả ranking bất thường ra sao?
Bạn tổ chức highlight cho title hoặc description bằng cấu hình và giới hạn kích thước đầu ra như thế nào?
Bạn ngăn HTML highlight fragment dẫn tới XSS khi hiển thị trên frontend như thế nào?
Bạn thiết kế trường hợp search typo, synonym và phrase query để đánh giá độ phù hợp của analyzer ra sao?
Bạn giải thích aggregation khác với hits list trong đáp ứng nhu cầu analytics và facets như thế nào?
Bạn chọn terms aggregation cho danh sách các thương hiệu phổ biến với những giới hạn nào?
Bạn thiết kế filter aggregation để chỉ tính facets trên tập documents mà người dùng có quyền xem ra sao?
Bạn phân biệt global, filter và post_filter khi xây faceted search với bộ lọc đang được chọn như thế nào?
Bạn xác định tác động của shard_size và size lên độ chính xác của terms aggregation ra sao?
Bạn đánh giá vì sao terms aggregation trên nhiều shards có thể cho count gần đúng trong một số trường hợp?
Bạn chọn cardinality aggregation cho unique users hoặc products khi chấp nhận ước lượng theo điều kiện nào?
Bạn phân biệt exact counting với HyperLogLog-based cardinality estimation về chi phí và độ chính xác?
Bạn thiết kế date_histogram cho số đơn hàng theo ngày mà không sai timezone ra sao?
Bạn dùng histogram hoặc range aggregation để tạo bộ lọc khoảng giá theo dữ liệu như thế nào?
Bạn lựa chọn nested aggregation khi sản phẩm chứa mảng variant với giá riêng như thế nào?
Bạn kiểm tra aggregation trên nested fields không trộn attributes từ các variant khác nhau ra sao?
Bạn thiết kế pipeline aggregation để tính metric từ kết quả nhóm khác theo giới hạn nào?
Bạn xử lý yêu cầu phân trang hàng nghìn bucket với composite aggregation như thế nào?
Bạn phân biệt composite aggregation after_key với search hits search_after ra sao?
Bạn đánh giá chi phí aggregation có cardinality rất cao và thiết kế guardrails như thế nào?
Bạn quyết định cache một kết quả facet hay tính lại theo filter thay đổi theo yêu cầu freshness nào?
Bạn xây dựng hợp đồng API để aggregation count nhất quán với tập kết quả mà UI hiển thị ra sao?
Bạn kiểm thử filters ảnh hưởng đồng thời tới hits và aggregations bằng các trường hợp nào?
Bạn xác định khi nào cần tính trước thống kê trong database hoặc một index riêng thay vì aggregation trực tiếp?
Bạn thiết kế metric tổng hợp cho các trường có missing values mà không làm méo số liệu ra sao?
Bạn theo dõi slow aggregation và shard memory khi một dashboard gửi nhiều truy vấn đồng thời như thế nào?
Bạn phân biệt PageRequest của Spring Data với cơ chế search_after của Elasticsearch khi phân trang sâu ra sao?
Bạn đánh giá giới hạn result window và vì sao from/size không phù hợp để duyệt hàng triệu hits?
Bạn thiết kế cursor pagination dùng search_after và sort keys ổn định như thế nào?
Bạn xác định khi nào cần point-in-time để giảm sai lệch giữa các trang kết quả trong tập dữ liệu đang cập nhật ra sao?
Bạn phân biệt point-in-time với scroll API theo use case duyệt dữ liệu và tài nguyên giữ trên cluster?
Bạn thiết kế endpoint trả next cursor mà không lộ internal index names hoặc thông tin nhạy cảm như thế nào?
Bạn kiểm soát thời gian sống của point-in-time context và xử lý khi cursor đã hết hạn ra sao?
Bạn đánh giá ảnh hưởng của sort field không duy nhất khi search_after được dùng trên dữ liệu phân tán?
Bạn quyết định dùng một tiebreaker ổn định để tránh trùng hoặc bỏ sót hits như thế nào?
Bạn phân biệt tổng số kết quả chính xác với total hits được giới hạn hoặc ước lượng theo query settings?
Bạn chọn kích thước page dựa trên payload trung bình, latency và trải nghiệm frontend như thế nào?
Bạn thiết kế export lớn bằng scroll hoặc search_after thay vì một HTTP response duy nhất ra sao?
Bạn xử lý trường hợp alias chuyển sang index mới trong lúc người dùng đang paging như thế nào?
Bạn kiểm thử pagination trên dữ liệu có nhiều documents cùng giá trị sort như thế nào?
Bạn giải thích refresh policy của Elasticsearch có ảnh hưởng gì tới độ trễ nhìn thấy document sau indexing?
Bạn so sánh refresh mặc định, refresh wait_for và refresh immediate theo throughput và latency như thế nào?
Bạn lựa chọn chính sách refresh khi API tạo sản phẩm cần ngay lập tức tìm thấy bằng tên ra sao?
Bạn đánh giá tác động của việc gọi refresh liên tục sau mỗi document write tới indexing throughput?
Bạn thiết kế bulk indexing với ElasticsearchOperations hoặc client bulk API phù hợp phiên bản như thế nào?
Bạn xác định số documents và kích thước bytes tối ưu cho mỗi bulk request theo đặc điểm cluster ra sao?
Bạn phân biệt batch size quá nhỏ với quá lớn về overhead, memory và nguy cơ timeout?
Bạn kiểm tra kết quả bulk để phát hiện lỗi ở từng item thay vì chỉ tin HTTP status ra sao?
Bạn phân loại bulk item failure có thể retry với mapping error không thể retry như thế nào?
Bạn thiết kế backoff và jitter cho bulk requests bị 429 hoặc resource exhaustion như thế nào?
Bạn ngăn duplicate documents khi bulk retry sau timeout bằng ID ổn định và versioning ra sao?
Bạn kiểm soát số bulk requests đồng thời để không làm cạn write thread pool của cluster?
Bạn xử lý một batch có 10.000 documents nhưng chỉ vài documents lỗi mapping như thế nào?
Bạn thiết kế dead-letter storage cho documents không thể index và quy trình sửa rồi replay ra sao?
Bạn xây dựng checkpoint theo nguồn dữ liệu để tiếp tục indexing sau khi worker restart như thế nào?
Bạn thiết kế reindex toàn bộ dữ liệu mà không gây quá tải transactional database ra sao?
Bạn xác định khi nào nên đọc database theo keyset pagination thay cho offset trong reindex job?
Bạn giữ trạng thái index nhất quán khi dữ liệu nguồn tiếp tục thay đổi trong lúc backfill như thế nào?
Bạn phân biệt xây index mới rồi đổi alias với ghi đè dữ liệu trên index đang phục vụ ra sao?
Bạn thiết kế zero-downtime index migration khi mapping hoặc analyzer thay đổi như thế nào?
Bạn sử dụng read alias và write alias để tách nhiệm vụ truy vấn và ghi dữ liệu trong deployment ra sao?
Bạn kiểm tra điều kiện một write alias trỏ đúng index ghi mong muốn trước khi chạy bulk như thế nào?
Bạn chuyển index alias atomically để hạn chế khoảng thời gian không có index phục vụ như thế nào?
Bạn đánh giá yêu cầu tương thích ứng dụng cũ và mới khi alias chuyển sang mapping phiên bản mới ra sao?
Bạn thiết kế rollback từ index mới về index cũ khi kết quả tìm kiếm không đạt quality gate như thế nào?
Bạn tổ chức schema/index templates và index lifecycle policies theo quy trình phát hành nào?
Bạn phân biệt rollover theo kích thước, tuổi hoặc số documents đối với dữ liệu dạng thời gian như thế nào?
Bạn đánh giá rủi ro xóa index cũ quá sớm trong khi rollback vẫn có thể cần thiết ra sao?
Bạn thiết kế chính sách lưu trữ và xóa documents để đáp ứng TTL nghiệp vụ hoặc retention regulations như thế nào?
Bạn mô tả cách đồng bộ dữ liệu từ PostgreSQL hoặc MySQL sang Elasticsearch qua ứng dụng Spring như thế nào?
Bạn phân biệt đồng bộ trực tiếp khi database transaction commit với event-driven indexing có hàng đợi?
Bạn đánh giá vì sao @Transactional của Spring không tạo transaction nguyên tử giữa RDBMS và Elasticsearch?
Bạn thiết kế transactional outbox để không mất sự kiện cập nhật search index sau database commit ra sao?
Bạn lựa chọn CDC hoặc ứng dụng phát domain events theo yêu cầu vận hành và latency nào?
Bạn xử lý sự kiện duplicate từ Kafka hoặc RabbitMQ để search index không tạo document trùng như thế nào?
Bạn thiết kế event payload mang entity ID, revision và thay đổi cần index để phục vụ idempotency như thế nào?
Bạn xử lý update events đến sai thứ tự để version cũ không ghi đè nội dung mới ra sao?
Bạn dùng external versioning hoặc cơ chế kiểm soát version tương ứng khi cần đồng bộ theo revision nguồn ra sao?
Bạn phân biệt Elasticsearch optimistic concurrency qua seq_no/primary_term với business revision từ database như thế nào?
Bạn quyết định update document theo event delta hay tải lại snapshot mới nhất từ database như thế nào?
Bạn phân tích race condition khi delete event đến trước update event cũ trên cùng document ra sao?
Bạn quản lý soft delete của bản ghi nguồn và xóa document trong index theo quy tắc nào?
Bạn thiết kế cách cập nhật một search document được denormalize từ nhiều bảng liên quan ra sao?
Bạn xử lý cập nhật hàng loạt documents khi thông tin thương hiệu hoặc danh mục được đổi tên ra sao?
Bạn đánh giá chiến lược update-by-query so với phát lại sự kiện cho mỗi document theo tác động nào?
Bạn xác định độ trễ đồng bộ chấp nhận được cho giá, tồn kho và thông tin mô tả sản phẩm?
Bạn thiết kế cơ chế trả freshness metadata cho frontend khi search index có thể chậm hơn database gốc ra sao?
Bạn đối soát số documents và checksum theo từng partition dữ liệu nguồn để phát hiện drift như thế nào?
Bạn thiết kế reconciliation job tìm documents thiếu, thừa hoặc lỗi thời mà không quét toàn bộ cluster liên tục ra sao?
Bạn xử lý Elasticsearch outage kéo dài nhưng database vẫn phát sinh nhiều thay đổi như thế nào?
Bạn lập kế hoạch replay backlog sau khi cluster phục hồi mà không làm nghẽn search traffic ra sao?
Bạn phân biệt lỗi data mapping có tính cố định với lỗi transient network khi xử lý index events ra sao?
Bạn đánh giá khi nào cần reindex hoàn toàn thay vì chỉ khắc phục các events chưa được áp dụng?
Bạn thiết kế API fallback truy vấn database nguồn khi Elasticsearch không khả dụng theo giới hạn nào?
Bạn xác định lúc nào cần cảnh báo về synchronization lag và cách đo lag chính xác ra sao?
Bạn thiết kế cập nhật đồng thời nhiều search aliases hoặc related indices mà không giả định distributed transaction?
Bạn lựa chọn cách giải quyết xung đột giữa hai nguồn dữ liệu cùng cập nhật một search document như thế nào?
Bạn xây dựng audit trail cho từng lần reindex và alias switch để truy được phiên bản dữ liệu ra sao?
Bạn đánh giá tác động của index refresh và replica replication lên freshness sau event indexing như thế nào?
Bạn phân biệt search latency phía Spring mapping với search phase latency trên Elasticsearch cluster ra sao?
Bạn sử dụng Elasticsearch Profile API để tìm những query clauses hoặc collectors gây chậm như thế nào?
Bạn xác định dấu hiệu một truy vấn slow do wildcard, nested hoặc script scoring ra sao?
Bạn đo p50, p95 và p99 search latency theo loại query và kích thước kết quả như thế nào?
Bạn theo dõi indexing throughput, refresh time, merge time và segment count để đánh giá sức khỏe cluster ra sao?
Bạn thiết kế metrics cho bulk rejection, failed items, queue depth và retry attempts như thế nào?
Bạn phân biệt CPU saturation, JVM heap pressure và disk I/O pressure từ số liệu cluster như thế nào?
Bạn nhận diện tác động của fielddata trên text fields so với doc values của keyword fields ra sao?
Bạn kiểm soát memory khi thực hiện high-cardinality terms aggregation hoặc deep sorting như thế nào?
Bạn đánh giá ảnh hưởng của index.mapping.total_fields.limit tới mapping explosion và tính ổn định ra sao?
Bạn lựa chọn index settings cho số replica phù hợp với khả năng chịu lỗi và lượng truy vấn như thế nào?
Bạn phân biệt replica count tăng với số primary shards tăng về thông lượng ghi và truy vấn như thế nào?
Bạn thiết kế shard allocation awareness theo availability zones để tránh mất dữ liệu cùng lúc ra sao?
Bạn đánh giá chi phí relocating shards khi scale cluster hoặc đổi node types ra sao?
Bạn theo dõi disk watermarks và nguy cơ write block khi dung lượng ổ đĩa xuống thấp như thế nào?
Bạn xử lý tình huống indexing bị từ chối do index read-only block gây ra bởi disk threshold ra sao?
Bạn thiết kế backpressure từ cluster search/write queues tới Spring application để giảm overload như thế nào?
Bạn chọn chiến lược giới hạn concurrency và bulk size khi index backlog tăng nhanh ra sao?
Bạn phân biệt lỗi circuit breaker của Elasticsearch với lỗi circuit breaker ở client application như thế nào?
Bạn kiểm soát retry budget để các service không cùng tạo retry storm khi cluster bị chậm?
Bạn đánh giá tác động của large _source documents tới network và response serialization latency như thế nào?
Bạn thiết kế source filtering và field selection để giảm payload của kết quả tìm kiếm ra sao?
Bạn giới hạn số nested documents hoặc nested query clauses nhằm tránh quá tải cluster như thế nào?
Bạn sử dụng request cache hoặc query cache theo những điều kiện và giới hạn nào?
Bạn phân biệt caching ở Elasticsearch với caching ở ứng dụng Spring theo độ mới dữ liệu như thế nào?
Bạn thiết kế benchmark với tập query thực tế và dữ liệu đủ lớn để tránh tối ưu sai workload ra sao?
Bạn đánh giá khi nào nên tách indexing-heavy và search-heavy workloads về tài nguyên hoặc kiến trúc?
Bạn quyết định lúc nào scale thêm nodes so với đổi mapping hoặc query trước khi mở rộng hạ tầng ra sao?
Bạn đặt SLO cho search relevance, availability, latency và indexing freshness dựa trên yêu cầu sản phẩm như thế nào?
Bạn kiểm soát rủi ro API search endpoint bị sử dụng để đọc document thuộc tenant khác như thế nào?
Bạn bắt buộc tenant filter trong mọi Elasticsearch query kể cả aggregation và autocomplete bằng cách nào?
Bạn phân biệt quyền đọc index và quyền quản trị index/mapping trong cấu hình tài khoản ứng dụng như thế nào?
Bạn dùng Elasticsearch API keys hoặc role-based access control để giới hạn scope của ứng dụng ra sao?
Bạn thiết kế authentication và TLS giữa Spring Boot và Elasticsearch mà không ghi secrets trong logs như thế nào?
Bạn xác định nguy cơ cho người dùng gửi trực tiếp Query DSL hoặc script tùy ý vào search API như thế nào?
Bạn giới hạn các fields được phép lọc, sort và aggregate để chống query abuse ra sao?
Bạn xử lý input query chứa wildcard hoặc regex độc hại gây tiêu thụ tài nguyên bất thường như thế nào?
Bạn phân biệt query injection qua chuỗi query_string với việc dùng các query builders được kiểm soát như thế nào?
Bạn che PII trong _source, highlights, slow logs và application traces theo chính sách nào?
Bạn đánh giá khi nào chỉ nên lưu dữ liệu tokenized hoặc masked trong search index thay vì bản gốc ra sao?
Bạn kiểm tra quyền truy cập snapshot repositories và backup chứa dữ liệu nhạy cảm như thế nào?
Bạn thiết kế xóa dữ liệu cá nhân khỏi active indices, replicas, snapshots và backup theo yêu cầu nào?
Bạn quản lý encryption at rest của volumes hoặc managed Elasticsearch theo trách nhiệm vận hành nào?
Bạn phân biệt document-level security của nền tảng Elasticsearch với filter tự áp dụng trong ứng dụng ra sao?
Bạn kiểm thử multi-tenant search không làm lộ document hoặc aggregation count giữa tenants như thế nào?
Bạn thiết kế audit logging cho các truy vấn quản trị hoặc reindex mà không lưu raw user search chứa PII ra sao?
Bạn hạn chế quyền delete-by-query và alias switch chỉ cho các job vận hành được ủy quyền ra sao?
Bạn xây dựng cơ chế phê duyệt trước khi chạy thao tác xóa hoặc reindex ảnh hưởng nhiều indices như thế nào?
Bạn phân biệt security error 403 với index_not_found khi trả lỗi cho API để tránh tiết lộ tên index ra sao?
Bạn kiểm tra Spring Elasticsearch client không gửi API key tới host khác khi cấu hình endpoint bị chuyển hướng như thế nào?
Bạn đánh giá nguy cơ sử dụng wildcard index name trong truy vấn dữ liệu có nhiều tenant?
Bạn thiết kế unit test cho search service bằng fake repository hoặc stubbed ElasticsearchOperations như thế nào?
Bạn phân biệt unit test mapping DTO và integration test analyzer hoặc index mapping thực theo lỗi cần bắt ra sao?
Bạn sử dụng Testcontainers Elasticsearch để chạy repository và ElasticsearchOperations tests như thế nào?
Bạn ghim image version Elasticsearch phù hợp với Spring Data client trong CI theo nguyên tắc nào?
Bạn kiểm tra việc tạo index, settings và mapping trong test khớp quy trình production như thế nào?
Bạn tổ chức fixture documents để mọi test độc lập với thứ tự chạy hoặc trạng thái index tồn tại trước đó ra sao?
Bạn quyết định refresh index trong integration tests để tránh test flaky do near-real-time search như thế nào?
Bạn kiểm thử @Document mapping cho text, keyword, date, nested và multi-fields với Elasticsearch thật như thế nào?
Bạn kiểm thử tokenizer, token filters và cách xử lý tiếng Việt có dấu bằng Analyze API như thế nào?
Bạn xây dựng relevance test từ một tập query và expected ranking thay vì chỉ kiểm tra số hits như thế nào?
Bạn kiểm thử synonym hoặc fuzzy search để không làm xuất hiện kết quả sai nghĩa quá nhiều như thế nào?
Bạn tạo test bool query để phân biệt filter, must, must_not và minimum_should_match ra sao?
Bạn kiểm thử nested query tránh matching chéo giữa hai elements trong cùng array như thế nào?
Bạn kiểm chứng keyword field sort và terms aggregation hoạt động đúng mà không dùng fielddata trên text như thế nào?
Bạn xây dựng integration test faceted search mà hits và aggregation counts sử dụng cùng tenant filters ra sao?
Bạn kiểm tra composite aggregation pagination bằng after_key trên tập bucket lớn như thế nào?
Bạn thử search_after với nhiều hits có cùng sort value để phát hiện trùng hoặc mất kết quả ra sao?
Bạn mô phỏng index được cập nhật giữa hai page requests để kiểm tra tính nhất quán của cursor contract như thế nào?
Bạn kiểm thử point-in-time hết hạn và API trả lỗi có thể phục hồi như thế nào?
Bạn mô phỏng bulk request trả partial failures để xác nhận chỉ retry những items phù hợp ra sao?
Bạn kiểm thử bulk indexing có cùng document ID nhiều lần để bảo đảm idempotency như thế nào?
Bạn xây dựng test update event đến sai thứ tự để chắc rằng document mới không bị ghi đè bởi revision cũ ra sao?
Bạn kiểm thử transactional outbox và indexer restart không bỏ sót thay đổi dữ liệu nguồn như thế nào?
Bạn tạo test reindex sang index mới và alias switch mà không làm gián đoạn search API ra sao?
Bạn đánh giá lúc nào cần test alias rollback sau sự cố search relevance hoặc mapping không tương thích?
Bạn kiểm thử deletion event và reconciler loại bỏ document đã bị xóa khỏi database gốc như thế nào?
Bạn sử dụng fault injection khiến Elasticsearch trả 429, 503 hoặc timeout để kiểm tra retry/backoff như thế nào?
Bạn giới hạn memory của integration test bulk để phát hiện trường hợp gom hàng triệu documents trong heap ra sao?
Bạn chạy load test trên index có shard distribution và dữ liệu gần production để đo p99 latency như thế nào?
Bạn xác định những performance regressions nào cần được chặn trong CI trước khi nâng Elasticsearch hoặc Spring Data?
Bạn phân biệt smoke test của search endpoint với kiểm thử full-text relevance và schema compatibility như thế nào?
Bạn tổ chức Testcontainers startup và cleanup để test suite chạy song song không đụng index names ra sao?
Bạn đánh giá giới hạn của một Elasticsearch Testcontainer đơn node khi cần kiểm thử replica hoặc cluster failover?
Bạn xác định quality gates cho reindex gồm document counts, sample checksums, latency và search relevance như thế nào?
Nếu repository trả kết quả rỗng dù document đã được save thành công, bạn sẽ kiểm tra refresh và index alias ra sao?
Nếu tìm đúng tên sản phẩm không có kết quả nhưng filter theo ID hoạt động, bạn sẽ kiểm tra analyzer và mapping như thế nào?
Nếu tìm tiếng Việt không dấu kém hơn có dấu, bạn sẽ điều tra tokenizer và normalizer bằng Analyze API ra sao?
Nếu terms query lọc mã sản phẩm trả sai kết quả, bạn sẽ kiểm tra keyword subfield và query type nào?
Nếu multi_match đưa mô tả dài lên trên tên chính xác, bạn sẽ điều chỉnh boosting và đánh giá ranking ra sao?
Nếu một truy vấn nested match sai thuộc tính của hai biến thể sản phẩm, bạn sẽ sửa mapping và query thế nào?
Nếu UI hiển thị facet count của tenant khác, bạn sẽ kiểm tra filter context và aggregation query ra sao?
Nếu search_after bị trùng hits khi nhiều documents có cùng ngày cập nhật, bạn sẽ bổ sung tiebreaker như thế nào?
Nếu người dùng yêu cầu nhảy thẳng tới trang thứ 5000, bạn sẽ thiết kế lại pagination API ra sao?
Nếu một trang kết quả mất document sau khi alias được chuyển, bạn sẽ đánh giá point-in-time và phiên bản index như thế nào?
Nếu bulk indexing trả HTTP 200 nhưng nhiều items lỗi mapping, bạn sẽ phát hiện và replay lỗi theo từng item ra sao?
Nếu một batch indexer bị kill giữa chừng, bạn sẽ tiếp tục từ checkpoint mà không tạo documents trùng như thế nào?
Nếu sự kiện cập nhật tồn kho đến sai thứ tự làm dữ liệu cũ ghi đè, bạn sẽ sử dụng source revision ra sao?
Nếu database đã commit nhưng Elasticsearch outage kéo dài, bạn sẽ giữ event backlog và phục hồi index như thế nào?
Nếu dữ liệu trong index khác database mặc dù queue rỗng, bạn sẽ thiết kế công việc reconciliation ra sao?
Nếu mapping thêm một field mới gây lỗi cho client phiên bản cũ, bạn sẽ điều phối index version và rolling deploy ra sao?
Nếu cần đổi analyzer cho trường title đang được tìm kiếm, bạn sẽ xây index mới và alias switch như thế nào?
Nếu cluster báo trạng thái yellow và một replica chưa được gán, bạn sẽ phân tích khả năng chịu lỗi và search availability ra sao?
Nếu một shard bị hot làm p99 latency tăng, bạn sẽ kiểm tra routing, query fanout và shard distribution như thế nào?
Nếu high-cardinality aggregation gây JVM circuit breaker, bạn sẽ giới hạn buckets và điều chỉnh truy vấn ra sao?
Nếu bulk rejections tăng cùng indexing backlog, bạn sẽ giảm concurrency và thay đổi batch size như thế nào?
Nếu index bị chuyển read-only vì disk watermark, bạn sẽ xử lý dung lượng và xác minh index block sau khi phục hồi ra sao?
Nếu Elasticsearch trả 429 khi traffic search tăng, bạn sẽ lựa chọn load shedding và retry policy như thế nào?
Nếu một query_string có wildcard quá rộng làm CPU tăng mạnh, bạn sẽ bổ sung validation và query budget ra sao?
Nếu index không có dữ liệu sau reindex hoàn thành, bạn sẽ kiểm tra source query, mappings, failed bulk items và alias ra sao?
Nếu một document bị xóa khỏi ứng dụng vẫn xuất hiện trong search, bạn sẽ kiểm tra event, refresh và delete pipeline ra sao?
Nếu API search vẫn trả 200 nhưng relevance giảm sau nâng Elasticsearch, bạn sẽ so sánh analyzers và ranking metrics như thế nào?
Nếu ứng dụng WebFlux bị nghẽn khi search nhiều request, bạn sẽ kiểm tra blocking client calls và thread usage ra sao?
Nếu secret của Elasticsearch client bị lộ trong debug logs, bạn sẽ ứng phó sự cố và gia cố observability ra sao?
Nếu Spring Data Elasticsearch upgrade làm NativeQuery không tương thích, bạn sẽ xử lý version API và regression tests ra sao?
Bạn xây dựng runbook khi Elasticsearch cluster bị quá tải, bulk indexing backlog cao, search latency tăng và dữ liệu bắt đầu stale như thế nào?
