Fluentd giải quyết những nhu cầu nào khi ứng dụng và hạ tầng phát sinh log với định dạng, tốc độ và đích lưu trữ khác nhau?
Bạn sẽ mô tả luồng một sự kiện đi qua source, parser, filter, tag, buffer và output của Fluentd như thế nào?
Bạn sẽ phân biệt Fluentd với thư viện ghi log trong ứng dụng và hệ thống lưu trữ log tập trung theo trách nhiệm ra sao?
Bạn sẽ so sánh Fluentd với Fluent Bit khi cần lựa chọn agent thu thập và aggregator log như thế nào?
Bạn sẽ xác định khi nào cần một Fluentd aggregator trung tâm thay vì gửi trực tiếp từ từng ứng dụng đến backend ra sao?
Bạn sẽ phân biệt log record, event time và tag trong mô hình event của Fluentd như thế nào?
Bạn sẽ thiết kế pipeline log đáp ứng mục tiêu không mất dữ liệu, độ trễ chấp nhận được và chi phí vận hành ra sao?
Bạn sẽ xác định các nguồn log quan trọng và chủ sở hữu của chúng trước khi triển khai Fluentd như thế nào?
Bạn sẽ lựa chọn nơi đặt Fluentd trong kiến trúc có nhiều namespace Kubernetes và backend log ở cluster khác ra sao?
Bạn sẽ mô tả những tình huống cần tách pipeline log vận hành khỏi pipeline log kiểm toán như thế nào?
Bạn sẽ phân biệt nhu cầu parsing, enrichment, filtering và routing qua ví dụ một access log HTTP ra sao?
Khi log đầu vào tăng đột biến nhanh hơn khả năng tiếp nhận của backend, bạn sẽ đánh giá hành vi của Fluentd ra sao?
Bạn sẽ xác định các giới hạn của pipeline Fluentd khi cần bảo đảm thứ tự sự kiện toàn cục như thế nào?
Bạn sẽ giải thích cấu trúc các khối source, filter, match và label trong tệp cấu hình Fluentd như thế nào?
Bạn sẽ phân biệt tham số @type của plugin với các thuộc tính cấu hình riêng của từng plugin ra sao?
Bạn sẽ tổ chức nhiều tệp cấu hình bằng cơ chế include mà vẫn kiểm soát thứ tự và phạm vi áp dụng như thế nào?
Bạn sẽ xác định cách kiểm tra cú pháp và khả năng nạp cấu hình trước khi khởi động Fluentd production ra sao?
Bạn sẽ thiết kế quy ước đặt tên source, tag và output để nhiều đội cùng vận hành pipeline như thế nào?
Bạn sẽ giải thích các dấu wildcard trong tag pattern ảnh hưởng đến việc chọn khối match như thế nào?
Bạn sẽ phân tích vì sao thứ tự các khối match có thể làm một route dự kiến không bao giờ được sử dụng ra sao?
Bạn sẽ xác định khi nào nên dùng label để cô lập một nhóm rule và tránh ảnh hưởng các nguồn log khác như thế nào?
Bạn sẽ mô tả luồng sự kiện qua các label và cơ chế chuyển tiếp giữa nhánh xử lý như thế nào?
Bạn sẽ kiểm soát cấu hình nguồn và routing trong môi trường GitOps hoặc CI/CD bằng cách nào?
Bạn sẽ phát hiện xung đột giữa hai khối filter hoặc match cùng áp dụng cho một loại tag như thế nào?
Bạn sẽ quản lý cấu hình riêng theo development, staging và production mà không nhân bản quá nhiều tệp ra sao?
Bạn sẽ đánh giá sự khác biệt giữa cấu hình mặc định của plugin và cấu hình được khai báo tường minh khi kiểm thử ra sao?
Bạn sẽ sử dụng các tham số hệ thống của Fluentd để đặt mức log, thư mục làm việc và hành vi xử lý lỗi như thế nào?
Bạn sẽ xác định lợi ích và rủi ro của việc dùng nhiều worker process cho một Fluentd instance như thế nào?
Bạn sẽ kiểm tra plugin nào hỗ trợ multi-worker trước khi thay đổi số worker bằng cách nào?
Bạn sẽ mô tả vai trò của source plugin khi đọc file, nhận sự kiện qua mạng hoặc thu log từ dịch vụ khác ra sao?
Bạn sẽ chọn input tail hay forward khi ứng dụng ghi ra file so với gửi event trực tiếp như thế nào?
Bạn sẽ thiết kế source tail cho nhiều file log có tên thay đổi sau log rotation ra sao?
Bạn sẽ giải thích vai trò của position file trong việc theo dõi offset đã đọc của tail source như thế nào?
Bạn sẽ xác định vị trí lưu position file để Fluentd có thể tiếp tục sau khi container khởi động lại ra sao?
Bạn sẽ phân tích nguy cơ mất hoặc đọc trùng log khi position file bị mất, hỏng hoặc dùng chung giữa nhiều input như thế nào?
Bạn sẽ xử lý trường hợp ứng dụng đổi tên file đang ghi trong lúc Fluentd tail theo dõi log như thế nào?
Bạn sẽ phân biệt cơ chế log rotation kiểu rename với copytruncate và ảnh hưởng tới việc đọc log ra sao?
Bạn sẽ kiểm tra tác động của read_from_head khi lần đầu triển khai tail source trên thư mục có log cũ như thế nào?
Bạn sẽ giới hạn những file được theo dõi bằng path pattern và loại trừ file không cần thiết ra sao?
Bạn sẽ nhận diện rủi ro khi quyền đọc file và thư mục không đủ cho Fluentd trong container như thế nào?
Bạn sẽ kiểm soát việc một file bị hai Fluentd instance cùng tail và gửi bản ghi trùng ra sao?
Bạn sẽ giải thích cách source forward nhận dữ liệu theo giao thức Fluentd Forward từ agent khác như thế nào?
Bạn sẽ xác định cơ chế xác thực và bảo vệ kết nối khi dùng forward input qua mạng không hoàn toàn tin cậy ra sao?
Bạn sẽ kiểm thử trường hợp Fluentd aggregator tạm thời không nhận kết nối từ forward agent như thế nào?
Bạn sẽ lựa chọn cách tiếp nhận log từ ứng dụng phát JSON qua stdout trong Docker hoặc Kubernetes ra sao?
Bạn sẽ mô tả yêu cầu đọc file log container của runtime và phân biệt phần metadata bao ngoài với nội dung log thực tế như thế nào?
Bạn sẽ phân tích sự khác biệt giữa thu thập từ file log container và nhận trực tiếp qua network output của ứng dụng ra sao?
Bạn sẽ thiết kế cách thu thập log từ một ứng dụng ghi nhiều file theo ngày mà không bỏ sót log khi chuyển ngày như thế nào?
Bạn sẽ phân biệt trường hợp một dòng văn bản thô với một event đã parse thành record có cấu trúc ra sao?
Bạn sẽ lựa chọn parser JSON hay regexp cho log của ứng dụng theo khả năng duy trì schema và mức độ biến động như thế nào?
Bạn sẽ giải thích nhiệm vụ của parser plugin khi biến một dòng access log thành các trường có tên và kiểu dữ liệu ra sao?
Bạn sẽ thiết kế biểu thức regexp có nhóm tên để tách timestamp, method, path, status và latency từ một access log như thế nào?
Bạn sẽ kiểm tra biểu thức regexp có khớp nhầm khi URI hoặc user agent chứa dấu cách và ký tự đặc biệt ra sao?
Bạn sẽ xử lý log có nhiều định dạng trên cùng source mà vẫn tránh rơi vào trạng thái parse thất bại hàng loạt như thế nào?
Bạn sẽ xác định khác biệt giữa parse tại source và dùng parser filter trên trường message đã có như thế nào?
Bạn sẽ thiết kế cách giữ bản ghi gốc khi parser không nhận diện được định dạng để còn điều tra như thế nào?
Bạn sẽ xác định cách định tuyến record không parse được sang nơi chẩn đoán riêng mà không làm mất log quan trọng ra sao?
Bạn sẽ phân biệt event time lấy từ bản ghi với thời điểm Fluentd nhận dữ liệu khi cấu hình parser như thế nào?
Bạn sẽ thiết kế time_key và time_format để diễn giải timestamp có timezone của log ứng dụng ra sao?
Bạn sẽ phát hiện sự cố do dùng sai timezone hoặc độ chính xác milliseconds so với seconds khi parse event time như thế nào?
Bạn sẽ lựa chọn giữ hay bỏ trường timestamp gốc sau parsing dựa trên nhu cầu kiểm toán như thế nào?
Bạn sẽ kiểm tra ảnh hưởng của trường dữ liệu sai kiểu, chẳng hạn status dạng chuỗi thay vì số, đối với backend ra sao?
Bạn sẽ thiết kế cơ chế chuẩn hóa các trường chung như service, environment, severity và request_id khi nhiều nguồn log khác nhau ra sao?
Bạn sẽ phân tích vì sao không nên ghi toàn bộ log như một chuỗi message nếu backend cần tìm kiếm theo thuộc tính?
Bạn sẽ xác định parser có vô tình loại bỏ trường quan trọng khi record JSON chứa nested object hoặc array như thế nào?
Bạn sẽ đánh giá yêu cầu escape dấu nháy, backslash và Unicode khi log đi qua nhiều lớp encoding như thế nào?
Bạn sẽ thiết kế bước kiểm thử parser với dòng hợp lệ, dòng thiếu trường và dòng sai định dạng như thế nào?
Bạn sẽ giải thích vì sao stack trace và các log đa dòng không thể luôn xử lý đúng bằng cách xem từng dòng là một event độc lập?
Bạn sẽ lựa chọn multiline parser khi log Java exception có dòng mở đầu và nhiều dòng stack trace như thế nào?
Bạn sẽ xác định biểu thức nhận diện dòng đầu của một sự kiện đa dòng theo format cụ thể ra sao?
Bạn sẽ kiểm tra nguy cơ gộp nhầm hai exception khác nhau khi dòng bắt đầu event không được nhận diện chính xác như thế nào?
Bạn sẽ thiết kế cơ chế hoàn tất một record multiline khi sự kiện cuối cùng không có dòng mở đầu tiếp theo ra sao?
Bạn sẽ phân tích ảnh hưởng của flush timeout đối với việc gộp multiline log và độ trễ xuất event như thế nào?
Bạn sẽ xác định giới hạn kích thước record multiline để tránh một exception quá dài làm tăng áp lực bộ nhớ ra sao?
Bạn sẽ xử lý trường hợp ứng dụng ghi xen kẽ log của nhiều request vào cùng một stream như thế nào?
Bạn sẽ phân biệt log đa dòng nguyên bản với các mảnh partial log do container runtime tạo khi một record quá dài ra sao?
Bạn sẽ đánh giá khi nào cần plugin concat hoặc cơ chế ghép partial record thay vì multiline parser như thế nào?
Bạn sẽ giữ nguyên các thông tin nhận dạng stream hoặc container khi ghép các mảnh log như thế nào?
Bạn sẽ kiểm tra log gồm stack trace có ký tự xuống dòng trong JSON để tránh ghép hai lần ra sao?
Bạn sẽ kiểm thử multiline parser bằng dữ liệu có exception lồng nhau và log INFO chen giữa như thế nào?
Bạn sẽ phân tích hậu quả của việc gộp sai multiline log lên thứ tự thời gian và khả năng tìm lỗi trong backend ra sao?
Bạn sẽ thiết kế chiến lược fallback khi parser multiline không thể xác định ranh giới event một cách chắc chắn như thế nào?
Bạn sẽ giải thích sự khác biệt giữa filter plugin và match output trong quá trình biến đổi hoặc chuyển tiếp event ra sao?
Bạn sẽ lựa chọn record_transformer hay cơ chế enrichment khác để thêm metadata ứng dụng theo những tiêu chí nào?
Bạn sẽ thiết kế filter thêm service name, cluster, namespace và environment mà không ghi đè dữ liệu đáng tin cậy như thế nào?
Bạn sẽ xác định thuộc tính nào nên lấy từ Kubernetes metadata thay vì tin vào thông tin do ứng dụng gửi ra sao?
Bạn sẽ kiểm tra tình huống metadata enrichment thất bại vì API Kubernetes không truy cập được như thế nào?
Bạn sẽ đánh giá tác động của việc tra cứu metadata cho từng event đến hiệu năng của Fluentd ra sao?
Bạn sẽ phân biệt filter grep giữ hoặc loại record theo điều kiện với filter parser trích xuất trường như thế nào?
Bạn sẽ thiết kế điều kiện bỏ log health check thành công nhưng giữ lại log health check thất bại ra sao?
Bạn sẽ xác định khi nào nên loại debug log tại ứng dụng thay vì đợi tới filter của Fluentd mới loại bỏ như thế nào?
Bạn sẽ tổ chức nhiều filter theo trình tự parse, normalize, enrich và redact để không phát tán dữ liệu nhạy cảm ra sao?
Bạn sẽ phân tích rủi ro khi một filter xóa trường đang được route hoặc output sử dụng như thế nào?
Bạn sẽ xử lý sự kiện thiếu trường bắt buộc mà không tạo vòng lặp lỗi trong pipeline ra sao?
Bạn sẽ thiết kế filter loại bỏ token, password, cookie hoặc thông tin cá nhân khỏi log trước khi output như thế nào?
Bạn sẽ phân biệt che trường dữ liệu có cấu trúc với redaction trên message tự do và giới hạn của mỗi phương pháp ra sao?
Bạn sẽ kiểm tra trường hợp secret nằm trong nested JSON hoặc stack trace mà rule redact đơn giản không phát hiện ra như thế nào?
Bạn sẽ xác định cách giảm cardinality của trường nhãn khi routing hoặc indexing log trong backend ra sao?
Bạn sẽ chọn cơ chế giữ record gốc ở môi trường thử nghiệm để kiểm chứng transform mà không lưu dữ liệu production nhạy cảm như thế nào?
Bạn sẽ đánh giá sự khác nhau giữa loại bỏ record hoàn toàn và chuyển record sang route riêng để điều tra như thế nào?
Bạn sẽ tổ chức kiểm thử thứ tự các filter để xác minh trường dữ liệu không bị biến đổi ngoài dự kiến ra sao?
Bạn sẽ mô tả tag được gắn tại source và tác động của tag đến việc chọn route trong Fluentd như thế nào?
Bạn sẽ phân biệt tag pattern với giá trị một field trong record khi thiết kế đường đi của log ra sao?
Bạn sẽ thiết kế tag naming để tách ứng dụng, mức độ nhạy cảm và môi trường mà không tạo vô số pattern khó quản lý như thế nào?
Bạn sẽ giải thích cách <match> chọn output dựa trên tag và vì sao thứ tự khai báo cần được xem xét?
Bạn sẽ lựa chọn cách cấu hình một tag match rộng và những tag match đặc biệt để tránh nuốt mất sự kiện như thế nào?
Bạn sẽ phân biệt route tới một output với nhu cầu gửi cùng event tới nhiều output bằng plugin copy như thế nào?
Bạn sẽ kiểm soát việc một nhánh output thành công nhưng nhánh khác thất bại trong mô hình fan-out như thế nào?
Bạn sẽ xác định khi nào dùng rewrite_tag_filter để đổi hướng xử lý thay vì sửa một field trong record ra sao?
Bạn sẽ thiết kế route riêng cho security log và application log theo yêu cầu retention và quyền truy cập như thế nào?
Bạn sẽ dùng label và relabel để xây dựng pipeline con có trách nhiệm rõ ràng như thế nào?
Bạn sẽ phát hiện một cấu hình route tạo vòng lặp gắn lại tag hoặc chuyển qua label lặp vô hạn bằng cách nào?
Bạn sẽ lựa chọn default route hoặc xử lý unmatched tag để phát hiện log bị thất lạc do cấu hình như thế nào?
Bạn sẽ kiểm tra tính đúng đắn của routing khi một service đổi tag sau nâng cấp mà destination không được cập nhật ra sao?
Bạn sẽ thiết kế routing theo backend, khu vực hoặc tenant mà không để log của khách hàng này đi vào kho khách hàng khác như thế nào?
Bạn sẽ phân biệt route theo điều kiện trong record với route hoàn toàn dựa trên tag theo khả năng cấu hình ra sao?
Bạn sẽ kiểm chứng event được gửi đúng một hoặc nhiều đích theo chủ đích bằng phương án test nào?
Bạn sẽ giải thích buffer trong Fluentd làm gì khi output plugin gửi dữ liệu đến backend chậm hơn tốc độ nhận ra sao?
Bạn sẽ phân biệt buffer memory và file về tốc độ, độ bền và hành vi khi tiến trình restart như thế nào?
Bạn sẽ lựa chọn file buffer cho pipeline quan trọng theo các yêu cầu dung lượng ổ đĩa và khả năng phục hồi nào?
Bạn sẽ xác định buffer path phải được lưu ở đâu trong Docker hoặc Kubernetes để không mất khi container thay thế ra sao?
Bạn sẽ phân biệt staging chunk và queued chunk trong vòng đời ghi, flush và retry của Fluentd như thế nào?
Bạn sẽ giải thích chunk key ảnh hưởng đến cách phân nhóm event theo tag, thời gian hoặc trường dữ liệu như thế nào?
Bạn sẽ cân nhắc rủi ro tạo quá nhiều buffer chunk khi dùng một field có cardinality cao làm chunk key ra sao?
Bạn sẽ lựa chọn chunk_limit_size và total_limit_size dựa trên lưu lượng, backend throughput và dung lượng còn trống như thế nào?
Bạn sẽ phân tích hậu quả của việc buffer đầy khi output vẫn không thể gửi dữ liệu ra sao?
Bạn sẽ lựa chọn overflow_action theo mục tiêu ưu tiên bảo toàn dữ liệu hay khả dụng của pipeline bằng tiêu chí nào?
Trong điều kiện nào việc chặn đầu vào khi buffer đầy có thể gây backpressure lên ứng dụng hoặc agent upstream?
Bạn sẽ thiết kế flush mode và flush interval để cân bằng độ trễ log với số lần ghi ra backend ra sao?
Bạn sẽ đánh giá tác động của flush_thread_count đến throughput, CPU và số kết nối với backend như thế nào?
Bạn sẽ phân biệt timekey, timekey_wait và timekey_use_utc trong cấu hình chunk theo thời gian như thế nào?
Bạn sẽ phân tích hành vi log đến muộn khi buffer được chia theo cửa sổ thời gian cố định như thế nào?
Bạn sẽ lựa chọn giới hạn số chunk đồng thời và cấu hình flush phù hợp khi mỗi phút nhận hàng triệu event như thế nào?
Bạn sẽ theo dõi các chỉ số queued chunks, buffer bytes và flush errors để nhận biết nghẽn trước khi mất dữ liệu như thế nào?
Bạn sẽ kiểm thử khả năng phục hồi của file buffer khi Fluentd bị kill trong lúc chunk đang được ghi ra sao?
Bạn sẽ đánh giá tác động của ổ đĩa chậm, đầy hoặc quyền truy cập sai lên file buffer như thế nào?
Bạn sẽ thiết kế quy trình kiểm tra và xử lý file buffer tồn đọng mà không xóa dữ liệu chưa được gửi như thế nào?
Bạn sẽ giải thích cơ chế retry của Fluentd khi output tạm thời thất bại và sự khác biệt giữa lỗi tạm thời với lỗi không thể phục hồi như thế nào?
Bạn sẽ lựa chọn retry backoff và giới hạn thời gian retry để tránh dồn tải lên backend vừa phục hồi ra sao?
Bạn sẽ phân tích tác động của retry jitter khi hàng trăm Fluentd agent cùng kết nối trở lại backend như thế nào?
Bạn sẽ xác định khi nào retry vô hạn có thể dẫn đến đầy đĩa và cần một chiến lược xử lý khác ra sao?
Bạn sẽ đánh giá lợi ích và giới hạn của secondary output khi destination chính không thể nhận dữ liệu như thế nào?
Bạn sẽ thiết kế đường dự phòng ghi log ra file hoặc object storage khi backend tìm kiếm bị gián đoạn ra sao?
Bạn sẽ phân biệt lỗi parse không phục hồi được với lỗi kết nối output có thể retry trong đường xử lý event như thế nào?
Bạn sẽ xử lý các record không thể gửi do schema không tương thích mà không làm kẹt toàn bộ buffer ra sao?
Vì sao cơ chế at-least-once có thể tạo bản ghi trùng khi backend đã nhận dữ liệu nhưng Fluentd không nhận được xác nhận?
Bạn sẽ đánh giá các bảo đảm giao nhận thực tế của Fluentd và từng output plugin dựa trên những điều kiện nào?
Bạn sẽ thiết kế deduplication ở downstream dựa trên event ID hoặc khóa phù hợp khi retry làm gửi trùng như thế nào?
Bạn sẽ kiểm thử tình huống backend trả lỗi 429 hoặc 503 để xác minh hành vi retry và backlog như thế nào?
Bạn sẽ phân tích nguy cơ giữ file buffer quá lâu khiến dữ liệu cũ được gửi lại sau khi retention hoặc schema backend thay đổi ra sao?
Bạn sẽ xác định cách phân biệt log bị mất ở source, bị bỏ bởi filter và đang chờ trong buffer khi số lượng event giảm như thế nào?
Bạn sẽ lập kịch bản mất kết nối output dài hơn dung lượng buffer dự kiến để đo giới hạn chịu lỗi như thế nào?
Bạn sẽ mô tả vai trò output plugin trong việc biến event Fluentd thành định dạng backend nhận được ra sao?
Bạn sẽ lựa chọn output tới hệ thống tìm kiếm, message broker hay object storage theo nhu cầu truy vấn và độ bền như thế nào?
Bạn sẽ thiết kế mapping tên index, topic hoặc object key từ tag và metadata mà không tạo phân mảnh lưu trữ quá mức ra sao?
Bạn sẽ xác định điều kiện nào cần nén, batch hoặc giới hạn kích thước gửi trên mỗi lần flush để cải thiện throughput như thế nào?
Bạn sẽ kiểm tra quyền ghi, TLS và thông tin xác thực khi output không kết nối được backend bằng những bước nào?
Bạn sẽ quản lý secret cho output plugin bằng cơ chế cấu hình bảo mật thay vì đưa trực tiếp vào repository ra sao?
Bạn sẽ đánh giá nguy cơ để plugin debug hoặc log lỗi output in ra nội dung record nhạy cảm như thế nào?
Bạn sẽ phân biệt sai định dạng payload ở output với dữ liệu nguồn sai khi backend từ chối ingest ra sao?
Bạn sẽ xây dựng quy trình chuyển đổi backend đích mà không bỏ sót log hoặc đẩy trùng quá nhiều event như thế nào?
Bạn sẽ xác định cách xác minh dữ liệu đã có ở backend sau một đợt flush mà không chỉ dựa vào trạng thái process còn chạy?
Bạn sẽ phân biệt khả năng tra cứu log trong backend với tính đầy đủ dữ liệu đã được Fluentd chuyển đến như thế nào?
Bạn sẽ triển khai Fluentd dưới dạng DaemonSet trên Kubernetes trong những điều kiện nào?
Bạn sẽ phân biệt vai trò của Fluentd DaemonSet trên node với Fluentd Deployment làm aggregator như thế nào?
Bạn sẽ thiết kế hostPath mount cho log container và position file theo yêu cầu bảo mật, quyền truy cập và độ bền ra sao?
Bạn sẽ xác định các quyền RBAC cần thiết cho Kubernetes metadata enrichment mà không cấp quyền quá rộng như thế nào?
Bạn sẽ xử lý thay đổi vị trí log của container runtime hoặc cấu trúc CRI log khi nâng cấp Kubernetes ra sao?
Bạn sẽ đánh giá ảnh hưởng của việc ứng dụng ghi JSON qua stdout so với log đa dòng tới cách cấu hình parser như thế nào?
Bạn sẽ phân biệt log của Pod đang chạy, Pod vừa bị xóa và file log cũ sau node rotation khi thu thập ra sao?
Bạn sẽ thiết kế resource requests và limits cho Fluentd DaemonSet để tránh ảnh hưởng workload trên node như thế nào?
Bạn sẽ phân tích hậu quả khi Fluentd bị OOMKilled trong lúc file buffer hoặc position file chưa đồng bộ như thế nào?
Bạn sẽ xác định vì sao một số node không thu được log sau khi DaemonSet rollout bằng các phép kiểm tra nào?
Bạn sẽ tổ chức rolling update Fluentd trên cluster nhiều node để giảm khoảng trống thu thập như thế nào?
Bạn sẽ lựa chọn persistent volume hoặc cách lưu buffer khác cho Fluentd aggregator trong Kubernetes ra sao?
Bạn sẽ kiểm tra kết nối giữa Fluentd agent và aggregator khi NetworkPolicy hoặc service discovery thay đổi như thế nào?
Bạn sẽ đánh giá vai trò của readiness và liveness probe đối với Fluentd khi backend output tạm thời gián đoạn ra sao?
Bạn sẽ thiết kế graceful shutdown để flush hoặc giữ lại buffer khi Pod Fluentd bị kết thúc như thế nào?
Bạn sẽ xử lý yêu cầu cấu hình reload khi cần thay parser hoặc route mà không làm mất các event đang chờ như thế nào?
Bạn sẽ triển khai Fluentd trong Docker Compose để thực hành tail file, parsing và gửi log ra backend bằng những bước nào?
Bạn sẽ phân biệt các thư mục trong container cần lưu bền vững với dữ liệu tạm có thể bỏ khi restart ra sao?
Bạn sẽ xác định cách cô lập Fluentd của các tenant trong Kubernetes nếu có yêu cầu lưu log riêng ra sao?
Bạn sẽ bảo đảm Fluentd chỉ đọc file và API cần thiết theo nguyên tắc least privilege như thế nào?
Bạn sẽ phân tích rủi ro khi cho Fluentd chạy quyền root hoặc mount toàn bộ filesystem của node ra sao?
Bạn sẽ xây dựng kịch bản kiểm tra một Pod khởi động lại liên tục nhưng các log trước khi restart vẫn được thu thập như thế nào?
Bạn sẽ lựa chọn các metric nội bộ và log nào của Fluentd cần giám sát liên tục trong production?
Bạn sẽ mô tả cách dùng monitor_agent hoặc endpoint metric để xem trạng thái buffer, input và output ra sao?
Bạn sẽ phân biệt lưu lượng event vào, số event được filter và lượng event xuất thành công khi đánh giá pipeline như thế nào?
Bạn sẽ thiết kế dashboard đo input rate, output rate, queued chunks, retry count và buffer usage như thế nào?
Bạn sẽ xác định các dấu hiệu output đang chậm hơn input từ xu hướng kích thước queue và độ trễ ingest ra sao?
Bạn sẽ đo end-to-end lag từ event time ở ứng dụng đến lúc log có thể truy vấn trong backend như thế nào?
Bạn sẽ phân biệt trễ do parser multiline đang đợi hoàn tất event với trễ do buffer chưa flush ra sao?
Bạn sẽ sử dụng những số liệu nào để tìm plugin hoặc stage tiêu tốn CPU lớn nhất trong Fluentd?
Bạn sẽ phân tích nguyên nhân memory tăng khi số tag hoặc chunk key có nhiều giá trị không kiểm soát như thế nào?
Bạn sẽ xác định một regex parser kém hiệu năng gây nghẽn thông lượng bằng thử nghiệm nào?
Bạn sẽ quyết định tăng số worker hay phân tán lưu lượng qua nhiều aggregator theo các giới hạn tài nguyên nào?
Bạn sẽ đánh giá ảnh hưởng của mức log nội bộ Fluentd tới chi phí và khả năng chẩn đoán chính Fluentd như thế nào?
Bạn sẽ thiết kế alert khi file buffer sắp đầy hoặc retry diễn ra kéo dài nhưng log vẫn có vẻ được nhận bình thường như thế nào?
Bạn sẽ đặt ngưỡng cảnh báo sự chênh lệch giữa đầu vào và đầu ra dựa trên tốc độ lọc hợp lệ và yêu cầu giao nhận như thế nào?
Bạn sẽ phân biệt sự cố Fluentd không đọc được log với ứng dụng thật sự ngừng tạo log như thế nào?
Bạn sẽ kiểm tra vị trí lỗi khi log không xuất hiện trong backend từ source path, parser, tag, route, buffer đến output như thế nào?
Bạn sẽ phân tích tình huống log ở một node bị mất sau log rotation nhưng các node khác vẫn thu thập bình thường ra sao?
Bạn sẽ xác định nguyên nhân log bị nhân đôi sau khi thay đổi pos_file, tail source hoặc số replica như thế nào?
Bạn sẽ chẩn đoán một stack trace Java bị tách thành nhiều record trong backend bằng những kiểm tra nào?
Bạn sẽ xử lý tình huống Fluentd báo parse error tăng đột ngột sau khi ứng dụng đổi định dạng timestamp như thế nào?
Bạn sẽ phân biệt lỗi SSL handshake đến output với lỗi xác thực hoặc quyền ghi ở backend ra sao?
Bạn sẽ xác định nguyên nhân file buffer vẫn tăng dù backend có khả năng ghi và network latency thấp như thế nào?
Bạn sẽ kiểm tra rủi ro của việc cấu hình filter loại bỏ nhầm security log trước khi điều tra sự cố ra sao?
Bạn sẽ xây dựng bộ dữ liệu test cho log JSON, access log, log malformed và stack trace nhiều dòng như thế nào?
Bạn sẽ thiết kế phép thử unit hoặc integration cho parser và route bằng event đầu vào và đầu ra kỳ vọng ra sao?
Bạn sẽ xác minh tag routing đến đúng destination trong kịch bản nhiều service và môi trường bằng cách nào?
Bạn sẽ chạy thử cấu hình Fluentd với backend giả để kiểm tra buffer, retry và failover mà không đụng dữ liệu production như thế nào?
Bạn sẽ kiểm thử khả năng phục hồi log sau khi kill Fluentd và khởi động lại với file buffer còn nguyên như thế nào?
Bạn sẽ thiết kế thử nghiệm mất kết nối aggregator để đo số event bị mất, bị trùng và thời gian phục hồi ra sao?
Bạn sẽ xác định cách đo tác động tài nguyên của parser và filter lên Pod Fluentd khi log volume tăng gấp nhiều lần như thế nào?
Bạn sẽ kiểm thử redaction bằng dữ liệu giả chứa token, email và thông tin nhạy cảm trong log nhiều dòng ra sao?
Bạn sẽ so sánh tổng event ở nguồn và ở backend để đánh giá tính đầy đủ mà vẫn xét đến filter, retry và log rotation như thế nào?
Bạn sẽ tổ chức quy trình review plugin và nâng cấp phiên bản Fluentd để tránh cấu hình không tương thích ra sao?
Bạn sẽ đánh giá rủi ro bảo mật và nguồn cung plugin bên thứ ba trước khi cài thêm vào image Fluentd như thế nào?
Bạn sẽ thiết kế rollout canary cho cấu hình parser hoặc output mới và tiêu chí rollback khi pipeline chậm đi như thế nào?
Bạn sẽ lưu lại bằng chứng kiểm thử và thay đổi cấu hình Fluentd nhằm phục vụ điều tra lỗi vận hành như thế nào?
Bạn sẽ thiết kế runbook cho tình huống buffer đầy, retry liên tục hoặc log mất sau restart gồm những bước xác minh nào?
Bạn sẽ đánh giá các tiêu chí nghiệm thu về tính đầy đủ, độ trễ, bảo mật, khả năng phục hồi và chi phí trước khi đưa pipeline Fluentd vào production như thế nào?
