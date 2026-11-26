Bạn giải thích event streaming là gì và những yêu cầu nghiệp vụ nào khiến Apache Kafka phù hợp hơn giao tiếp request-response trực tiếp?
Bạn mô tả các thành phần broker, topic, partition, producer và consumer trong kiến trúc Apache Kafka như thế nào?
Bạn phân biệt message queue truyền thống với distributed event log của Kafka về cách lưu trữ và đọc lại sự kiện ra sao?
Bạn sẽ xác định ranh giới của một event và nội dung payload từ một thay đổi nghiệp vụ như tạo đơn hàng thế nào?
Bạn lựa chọn tên topic và quy ước đặt tên sự kiện để các nhóm phát triển hiểu thống nhất ra sao?
Bạn quyết định dùng chung topic hay tách topic theo loại sự kiện, vòng đời và yêu cầu truy cập bằng tiêu chí nào?
Bạn giải thích cách một topic được chia thành partition và tác động của lựa chọn này đến khả năng mở rộng ra sao?
Bạn phân biệt offset trong partition với mã định danh sự kiện nghiệp vụ như thế nào?
Bạn giải thích thứ tự sự kiện được Kafka bảo đảm trong phạm vi nào và điều gì xảy ra khi một topic có nhiều partition?
Bạn lựa chọn message key như thế nào để các thay đổi của cùng một đơn hàng được xử lý theo thứ tự?
Bạn xử lý hiện tượng dữ liệu phân bố không đều giữa các partition khi có một số key xuất hiện quá thường xuyên ra sao?
Bạn sẽ cân nhắc những yếu tố nào khi chọn số partition ban đầu cho một topic mới?
Bạn phân tích những thay đổi về ánh xạ key sang partition và thứ tự xử lý có thể xảy ra sau khi tăng số partition ra sao?
Bạn phân biệt retention theo thời gian, retention theo dung lượng và log compaction trong Kafka như thế nào?
Bạn chọn chính sách lưu giữ sự kiện nào khi cần phát lại dữ liệu nhiều ngày so với topic chỉ giữ trạng thái mới nhất?
Bạn giải thích ý nghĩa của tombstone record trong topic compacted và cách consumer nên diễn giải nó ra sao?
Bạn dự đoán điều gì xảy ra khi consumer cần đọc một offset đã bị Kafka xóa do chính sách retention?
Bạn phân biệt vị trí offset đã ghi nhận, offset đã commit và offset mới nhất của partition khi theo dõi consumer ra sao?
Bạn giải thích consumer group giúp chia tải xử lý và quan hệ giữa số consumer với số partition như thế nào?
Bạn thiết kế hai nhóm consumer độc lập cùng đọc một topic để phục vụ hai nghiệp vụ khác nhau ra sao?
Bạn phân tích vì sao một consumer group có thể xuất hiện consumer không được gán partition và cách xử lý thế nào?
Bạn mô tả quá trình consumer group rebalance khi thêm hoặc mất một instance consumer như thế nào?
Bạn so sánh eager rebalance và cooperative rebalance về gián đoạn xử lý và khả năng chuyển giao partition ra sao?
Bạn giải thích static membership có thể giúp một nhóm consumer hoạt động ổn định hơn trong trường hợp khởi động lại như thế nào?
Bạn phân biệt auto offset commit và manual offset commit về nguy cơ xử lý trùng hoặc mất sự kiện ra sao?
Bạn quyết định thời điểm commit offset khi xử lý sự kiện cần ghi dữ liệu xuống hệ thống ngoài như thế nào?
Bạn sẽ phục hồi một consumer sau khi tiến trình chết giữa lúc xử lý bản ghi và trước khi commit offset ra sao?
Bạn giải thích ý nghĩa của auto.offset.reset và cách lựa chọn earliest hay latest cho consumer group mới như thế nào?
Bạn xây dựng cách phát lại sự kiện từ một khoảng thời gian hoặc offset cụ thể mà không ảnh hưởng consumer group đang chạy ra sao?
Bạn phân biệt tác động của session.timeout.ms, heartbeat và max.poll.interval.ms lên hành vi consumer như thế nào?
Bạn điều chỉnh max.poll.records và chu kỳ poll ra sao khi bước xử lý sự kiện có thời gian biến động lớn?
Bạn thiết kế consumer vừa xử lý công việc chậm vừa duy trì membership ổn định trong group bằng cách nào?
Bạn mô tả cách Kafka lưu bản sao partition và bầu leader để duy trì khả năng phục vụ khi broker gặp sự cố như thế nào?
Bạn giải thích vai trò của leader, follower và in-sync replica trong quá trình producer ghi một sự kiện ra sao?
Bạn lựa chọn replication factor dựa trên yêu cầu chịu lỗi và chi phí tài nguyên theo những tiêu chí nào?
Bạn giải thích mối liên hệ giữa acks=all, min.insync.replicas và khả năng mất dữ liệu khi có broker lỗi như thế nào?
Bạn phân biệt việc replica bị chậm với việc replica rời khỏi tập ISR và hệ quả vận hành ra sao?
Bạn đánh giá rủi ro của unclean leader election đối với tính sẵn sàng và độ bền dữ liệu như thế nào?
Bạn mô tả vai trò của KRaft controller quorum trong quản lý metadata và điều phối cụm Kafka như thế nào?
Bạn giải thích sự khác biệt về kiến trúc quản lý metadata giữa Kafka dùng ZooKeeper và Kafka dùng KRaft ra sao?
Bạn thiết kế triển khai các controller trong KRaft để tránh mất quorum khi một máy hoặc vùng hạ tầng gặp sự cố như thế nào?
Bạn phân biệt vai trò controller và broker trong một cụm KRaft và cân nhắc khi nào nên tách chúng ra sao?
Bạn sẽ kiểm tra những thành phần nào khi cụm Kafka còn broker hoạt động nhưng thao tác thay đổi metadata bị gián đoạn?
Bạn phân tích đường đi của một bản ghi từ producer đến leader partition, các replica và consumer như thế nào?
Bạn lựa chọn producer acks, retries và delivery.timeout.ms để cân bằng độ trễ với độ tin cậy ghi dữ liệu ra sao?
Bạn giải thích idempotent producer ngăn bản ghi trùng do retry trong phạm vi nào và còn những trường hợp trùng nào cần xử lý?
Bạn phân tích ảnh hưởng của max.in.flight.requests.per.connection và retry đến thứ tự bản ghi do producer gửi như thế nào?
Bạn lựa chọn linger.ms, batch.size và compression.type để tối ưu throughput với latency theo nhu cầu nghiệp vụ ra sao?
Bạn quyết định cách xử lý callback thành công hoặc thất bại khi producer gửi sự kiện bất đồng bộ như thế nào?
Bạn phân biệt lỗi producer có thể retry với lỗi cấu hình hoặc serialization không nên retry bằng những tiêu chí nào?
Bạn thiết kế cơ chế chặn hoặc giảm tốc độ producer khi broker hay consumer không theo kịp lượng sự kiện như thế nào?
Bạn giải thích tác động của message size lớn lên producer, broker, consumer và hiệu năng toàn hệ thống ra sao?
Bạn sẽ xử lý sự kiện chứa payload quá lớn bằng lựa chọn mô hình dữ liệu hoặc phương án lưu trữ nào?
Bạn lựa chọn JSON, Avro hoặc Protobuf để biểu diễn event dựa trên schema, chi phí truyền và nhu cầu tương thích như thế nào?
Bạn sử dụng Schema Registry và schema ID để producer và consumer hiểu cấu trúc dữ liệu cùng một cách ra sao?
Bạn phân biệt các chiến lược tương thích backward, forward và full khi schema sự kiện thay đổi như thế nào?
Bạn tổ chức quá trình thay đổi schema để consumer phiên bản cũ vẫn đọc được sự kiện mới như thế nào?
Bạn xử lý trường mới bắt buộc hoặc thay đổi kiểu dữ liệu trong event mà không làm gián đoạn consumer ra sao?
Bạn xây dựng event contract gồm những trường metadata nào để hỗ trợ truy vết, phiên bản hóa và xử lý lặp?
Bạn phân biệt event time, producer timestamp và thời điểm consumer xử lý khi đánh giá độ trễ luồng sự kiện ra sao?
Bạn thiết kế cơ chế tạo định danh sự kiện và phát hiện duplicate khi nguồn nghiệp vụ có thể phát cùng một thay đổi nhiều lần như thế nào?
Bạn so sánh ngữ nghĩa at-most-once, at-least-once và exactly-once khi xây dựng một luồng Kafka như thế nào?
Bạn giải thích phạm vi nguyên tử của Kafka transaction khi ghi vào nhiều partition và đưa offset của consumer vào cùng giao dịch ra sao?
Bạn phân tích vai trò của transactional.id và fencing khi một producer cũ hoạt động lại sau khi đã có producer thay thế như thế nào?
Bạn phân biệt dữ liệu mà consumer với isolation.level=read_committed và read_uncommitted có thể nhìn thấy trong Kafka transaction như thế nào?
Bạn thiết kế luồng consume-transform-produce có transaction để kết quả và offset đầu vào đồng bộ với nhau ra sao?
Bạn đánh giá ranh giới bảo đảm exactly-once khi một consumer còn gọi API hoặc cập nhật cơ sở dữ liệu ngoài Kafka như thế nào?
Bạn thiết kế idempotency tại hệ thống đích để giảm tác động của sự kiện bị phát lại trong luồng thanh toán ra sao?
Bạn chọn retry ngay trong listener, retry topic hay dead-letter topic khi xử lý lỗi sự kiện dựa trên những đánh đổi nào?
Bạn thiết kế chính sách retry và backoff để sự kiện lỗi tạm thời không tạo vòng lặp gây quá tải ra sao?
Bạn quyết định cách giữ thứ tự theo key khi một bản ghi bị chuyển sang retry topic trong khi bản ghi mới tiếp tục đến như thế nào?
Bạn định nghĩa thông tin lỗi và metadata cần lưu ở dead-letter topic để có thể điều tra và phát lại bản ghi như thế nào?
Bạn xây dựng quy trình xử lý bản ghi không thể deserialize để consumer vẫn tiếp tục xử lý các bản ghi hợp lệ ra sao?
Bạn thiết kế cơ chế phát lại sự kiện từ dead-letter topic mà không tạo thêm bản ghi trùng hoặc làm mất thứ tự nghiệp vụ như thế nào?
Bạn giải thích sự khác nhau giữa reprocess toàn bộ topic và retry một bản ghi thất bại bằng ví dụ nào?
Bạn thiết kế ứng dụng Java sử dụng KafkaProducer và KafkaConsumer theo vòng đời khởi tạo, gửi, poll và đóng tài nguyên ra sao?
Bạn sử dụng KafkaTemplate trong Spring Kafka để gửi event kèm key, header và xử lý kết quả bất đồng bộ như thế nào?
Bạn cấu hình Spring Kafka @KafkaListener và consumer group để các instance ứng dụng cùng chia tải như thế nào?
Bạn lựa chọn các chế độ acknowledgment trong Spring Kafka theo thời điểm xác nhận hoàn thành nghiệp vụ ra sao?
Bạn sử dụng CommonErrorHandler hoặc cơ chế tương đương của Spring Kafka để xử lý lỗi tạm thời và lỗi vĩnh viễn như thế nào?
Bạn thiết kế listener có xử lý timeout và ngoại lệ để không chặn vô thời hạn một partition ra sao?
Bạn sẽ kiểm thử luồng producer-consumer trong Java hoặc Spring Kafka bằng Embedded Kafka hay Testcontainers như thế nào?
Bạn xây dựng kiểm thử tích hợp nào để chứng minh xử lý trùng, retry và commit offset cho một listener?
Bạn kiểm tra hành vi ứng dụng khi consumer bị rebalance giữa lúc đang xử lý bản ghi bằng kịch bản nào?
Bạn giải thích Kafka Connect giúp tích hợp nguồn và đích dữ liệu khác gì so với tự viết producer hoặc consumer ra sao?
Bạn phân biệt source connector và sink connector qua ví dụ đồng bộ dữ liệu giữa cơ sở dữ liệu và Kafka như thế nào?
Bạn thiết kế cấu hình task, converter và Single Message Transform trong Kafka Connect dựa trên nhu cầu đồng bộ ra sao?
Bạn giải thích cách Kafka Connect quản lý offset và phục hồi task sau khi connector worker bị khởi động lại như thế nào?
Bạn xử lý tình huống sink connector ghi thất bại một phần batch để tránh bỏ sót hoặc nhân đôi dữ liệu đích như thế nào?
Bạn sẽ giám sát trạng thái connector, task và dead-letter queue để nhận biết pipeline tích hợp đang gặp lỗi ra sao?
Bạn phân biệt Kafka Connect và Kafka Streams trong trường hợp cần biến đổi hoặc làm giàu sự kiện như thế nào?
Bạn giải thích KStream và KTable biểu diễn dữ liệu có ý nghĩa khác nhau như thế nào trong Kafka Streams?
Bạn sử dụng khóa bản ghi và repartition khi thực hiện groupBy hoặc join trong Kafka Streams theo nguyên tắc nào?
Bạn thiết kế một phép join giữa hai luồng sự kiện với khoảng thời gian cho phép bằng cách nào?
Bạn giải thích cách window và grace period xử lý sự kiện đến muộn trong Kafka Streams ra sao?
Bạn sử dụng state store, changelog topic và standby task để khôi phục trạng thái xử lý sau khi instance hỏng như thế nào?
Bạn thiết kế phép tổng hợp theo cửa sổ để kết quả cập nhật đúng khi sự kiện đến muộn hoặc đến sai thứ tự ra sao?
Bạn phân biệt xử lý event time và wall-clock time khi xây dựng một ứng dụng Kafka Streams như thế nào?
Bạn giải thích Kafka Streams xử lý topology, task và local state khi ứng dụng tăng số instance như thế nào?
Bạn sẽ kiểm tra điều gì khi một phép join cho ra ít kết quả hơn dự kiến dù dữ liệu đầu vào vẫn đầy đủ?
Bạn lựa chọn metrics nào để theo dõi consumer lag, tốc độ vào ra, tốc độ lỗi và độ trễ xử lý theo nhu cầu nghiệp vụ?
Bạn phân biệt lag theo offset với độ trễ thời gian thực của sự kiện và đánh giá cả hai như thế nào?
Bạn xác định nguyên nhân consumer lag tăng do producer tăng tải, consumer chậm hay rebalance liên tục bằng cách nào?
Bạn theo dõi những dấu hiệu nào về disk, network, request latency, under-replicated partition và offline partition để phát hiện broker quá tải?
Bạn thiết kế cảnh báo cho replication và KRaft quorum để phát hiện nguy cơ mất tính sẵn sàng trước khi xảy ra sự cố như thế nào?
Bạn sẽ xử lý khi một broker bị mất kết nối và các partition phải chuyển leader để dịch vụ tiếp tục hoạt động ra sao?
Bạn đề xuất trình tự kiểm tra và khôi phục khi một partition không còn đủ replica đồng bộ để nhận ghi mới như thế nào?
Bạn lập kế hoạch tăng broker và di chuyển partition để phân phối lại tải mà hạn chế ảnh hưởng đến producer và consumer ra sao?
Bạn đánh giá tác động của việc thay đổi số partition đến key ordering, consumer assignment và dữ liệu đang lưu như thế nào?
Bạn xác định kích thước cụm Kafka và dung lượng lưu trữ cần thiết từ tốc độ sự kiện, retention và replication factor ra sao?
Bạn dùng quota producer hoặc consumer để tránh một nhóm ứng dụng chiếm hết tài nguyên của cụm như thế nào?
Bạn triển khai TLS, SASL và ACL để producer, consumer và connector chỉ được phép truy cập tài nguyên cần thiết ra sao?
Bạn bảo vệ thông tin cá nhân trong message payload, log và dead-letter topic bằng những biện pháp nào?
Bạn thiết kế cơ chế theo dõi trace ID hoặc correlation ID xuyên suốt producer, Kafka và consumer như thế nào?
Bạn xây dựng kế hoạch backup, khôi phục và sao chép dữ liệu sang cụm dự phòng dựa trên mục tiêu RPO và RTO ra sao?
Bạn lựa chọn MirrorMaker 2 hoặc cơ chế đồng bộ liên cụm theo yêu cầu phục hồi thảm họa và độ trễ như thế nào?
Bạn phân tích những vấn đề về offset, trùng lặp và thứ tự sự kiện khi chuyển consumer sang một cụm Kafka dự phòng ra sao?
Bạn lên kế hoạch nâng cấp phiên bản Kafka, broker và client để giảm nguy cơ gián đoạn dịch vụ như thế nào?
Bạn sẽ xử lý sự cố consumer group liên tục rebalance sau một đợt triển khai mới theo trình tự điều tra nào?
Khi nhiều đơn hàng được cập nhật liên tục và người dùng nhận thông báo sai thứ tự, bạn sẽ kiểm tra key, partition, retry và consumer như thế nào?
Khi hệ thống báo đơn hàng đã thanh toán nhưng sự kiện cập nhật tồn kho không xuất hiện ở đích, bạn truy vết và đối soát luồng Kafka bằng cách nào?
Nếu cần xây dựng hệ thống sự kiện bán hàng với Java/Spring Kafka và khả năng phát lại, bạn sẽ đưa ra thiết kế topic, key, retry, kiểm thử và giám sát ra sao?
