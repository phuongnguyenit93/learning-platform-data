Bạn phân biệt at-most-once, at-least-once và exactly-once khi thiết kế một pipeline xử lý Kafka trong Spring như thế nào?
Bạn giải thích vì sao Kafka lưu offset theo consumer group chứ không lưu trạng thái thành công của từng thao tác nghiệp vụ như thế nào?
Bạn mô tả quan hệ giữa topic partition, thứ tự record và consumer group khi ứng dụng Spring Kafka chạy nhiều replica như thế nào?
Bạn phân biệt current position của KafkaConsumer với committed offset và xác định điều gì xảy ra sau khi consumer restart ra sao?
Bạn giải thích vì sao committed offset thường trỏ đến record tiếp theo cần đọc chứ không phải offset của record vừa xử lý như thế nào?
Bạn đánh giá rủi ro commit offset trước khi cập nhật database hoàn tất khi hệ thống yêu cầu không mất dữ liệu như thế nào?
Bạn phân tích hậu quả khi database đã commit nhưng Kafka offset chưa được commit trước khi consumer bị crash ra sao?
Bạn quyết định khi nào chấp nhận xử lý trùng và dùng idempotency thay vì cố tránh mọi lần đọc lại record như thế nào?
Bạn xác định cách dùng record key để giữ thứ tự theo business entity trên một partition mà không giả định có thứ tự toàn topic như thế nào?
Bạn thiết kế consumer xử lý sự kiện thanh toán nhiều lần nhưng không ghi nhận thanh toán trùng khi offset được replay như thế nào?
Bạn phân biệt consumer lag với số record chưa thực sự hoàn tất xử lý nghiệp vụ ở downstream ra sao?
Bạn lựa chọn chiến lược phân vùng topic theo business key để cân bằng thứ tự xử lý và phân phối tải như thế nào?
Bạn đánh giá điều gì xảy ra với ordering khi tăng số partition của một topic đang dùng key-based routing ra sao?
Bạn giải thích vì sao một partition không được xử lý đồng thời bởi nhiều consumer trong cùng một group ở một thời điểm ổn định như thế nào?
Bạn phân tích tình huống số consumer instances lớn hơn số partitions và hệ quả với khả năng mở rộng ra sao?
Bạn phân biệt Kafka acknowledgment của broker đối với producer với acknowledgment của listener đối với consumer offset như thế nào?
Bạn mô tả vai trò của ConcurrentKafkaListenerContainerFactory trong việc chọn AckMode và cấu hình listener containers như thế nào?
Bạn so sánh AckMode.RECORD và AckMode.BATCH theo thời điểm commit, throughput và lượng dữ liệu có thể được đọc lại khi lỗi ra sao?
Bạn phân biệt AckMode.TIME, COUNT và COUNT_TIME theo điều kiện commit offset và khả năng tích tụ record chưa commit như thế nào?
Bạn xác định khi nào sử dụng AckMode.MANUAL và MANUAL_IMMEDIATE thay vì giao container quyết định thời điểm commit như thế nào?
Bạn giải thích ảnh hưởng của việc gọi Acknowledgment.acknowledge trên listener thread và điều kiện áp dụng của các manual ack modes ra sao?
Bạn thiết kế listener chỉ acknowledge sau khi một thao tác nghiệp vụ có kết quả chắc chắn và có chính sách rõ cho trường hợp timeout như thế nào?
Bạn phân tích vì sao acknowledge record trong một nhánh xử lý bất đồng bộ có thể dẫn tới commit quá sớm hoặc sai thứ tự ra sao?
Bạn đánh giá cơ chế asyncAcks của listener container với các acknowledgment không theo thứ tự và những hạn chế cần chú ý như thế nào?
Bạn phân biệt commitSync với commitAsync của Kafka consumer về latency, xử lý lỗi và khả năng quan sát kết quả commit như thế nào?
Bạn xác định cách cấu hình syncCommits trong Spring Kafka và kiểm chứng hành vi khi broker không phản hồi commit ra sao?
Bạn thiết kế chính sách xử lý CommitFailedException hoặc lỗi commit trong lúc group ownership thay đổi như thế nào?
Bạn mô tả tác động của enable.auto.commit khi dùng Spring Kafka listener containers và lý do cần kiểm tra cấu hình thực tế ra sao?
Bạn phân biệt nhận một record, xử lý xong và commit offset thành công trong chu trình poll của Kafka consumer như thế nào?
Bạn xác định khi nào cần dùng Acknowledgment.nack để phát lại phần dữ liệu chưa xử lý và những ràng buộc thread/ack mode liên quan như thế nào?
Bạn phân tích ảnh hưởng của nack trên batch listener đối với phần records đã xử lý và phần records cần đọc lại như thế nào?
Bạn đánh giá trường hợp nào nack không tương thích với cấu hình asyncAcks và cần chọn cách khôi phục khác như thế nào?
Bạn thiết kế listener xử lý 100 records trong một poll khi record thứ 40 thất bại mà không làm mất các record phía sau ra sao?
Bạn xác định rủi ro một listener nuốt exception rồi acknowledge khiến record lỗi không được retry hoặc gửi DLT như thế nào?
Bạn phân biệt lỗi trong record listener với batch listener về granularity của retry và offset recovery ra sao?
Bạn giải thích vai trò của CommonErrorHandler và DefaultErrorHandler trong cơ chế xử lý lỗi của Spring Kafka listener containers như thế nào?
Bạn cấu hình DefaultErrorHandler với FixedBackOff hoặc ExponentialBackOff theo số lần retry và ngân sách xử lý như thế nào?
Bạn phân biệt seek-based recovery với cơ chế giữ records để gửi lại cho listener trong những cấu hình error handler hỗ trợ như thế nào?
Bạn xác định khi nào nên dùng retry ở cấp listener và khi nào retry phải đặt quanh đúng một external HTTP hoặc database operation ra sao?
Bạn đánh giá tác động của blocking retry đối với throughput và head-of-line blocking của partition chứa poison pill như thế nào?
Bạn thiết kế quy tắc phân loại exception có thể retry so với lỗi validation/schema vĩnh viễn trong DefaultErrorHandler như thế nào?
Bạn xác định cách xử lý lỗi timeout mạng khác với lỗi unique constraint khi cả hai cùng xuất hiện trong một listener method như thế nào?
Bạn phân tích vì sao retry vô hạn một record không thể xử lý có thể làm consumer lag tăng không giới hạn như thế nào?
Bạn thiết kế backoff phù hợp với max.poll.interval.ms để một đợt retry dài không làm consumer mất quyền sở hữu partition ra sao?
Bạn phân biệt retry trong memory, seek lại Kafka offset và xuất record ra retry topic về khả năng khôi phục sau process crash như thế nào?
Bạn thiết kế chính sách retry có jitter để nhiều consumer không đồng thời gây quá tải downstream sau khi dịch vụ phục hồi như thế nào?
Bạn đánh giá khi nào nên ngắt retry sớm và chuyển DLT vì lỗi không thể tự hồi phục dù còn ngân sách retry ra sao?
Bạn xác định cách dùng retry listeners hoặc logs để biết số lần một record được thử mà không phơi bày payload nhạy cảm như thế nào?
Bạn phân tích tác động của seek sau exception đối với thứ tự xử lý những records tiếp theo trong cùng partition ra sao?
Bạn thiết kế cơ chế dừng hoặc tạm dừng partition đang lỗi để không gây bão retry nhưng vẫn duy trì heartbeat của consumer như thế nào?
Bạn phân biệt lỗi phát sinh trước khi listener nhận record với lỗi được ném ngay trong code nghiệp vụ của listener như thế nào?
Bạn giải thích vì sao lỗi deserialize key hoặc value cần được xử lý khác với exception trong listener method ra sao?
Bạn cấu hình ErrorHandlingDeserializer để bọc delegate deserializer và đưa thông tin lỗi vào headers phù hợp như thế nào?
Bạn xử lý record có payload JSON sai schema để có thể quarantine hoặc gửi DLT mà không khiến consumer lặp lại lỗi deserialize mãi như thế nào?
Bạn xác định cách tránh ghi raw payload chứa dữ liệu nhạy cảm vào exception headers hoặc monitoring khi có lỗi deserialize ra sao?
Bạn phân biệt lỗi deserialization với lỗi message conversion từ byte payload sang kiểu tham số của @KafkaListener như thế nào?
Bạn thiết kế chính sách tương thích schema khi producer thêm field hoặc đổi kiểu dữ liệu mà các consumer triển khai không đồng thời ra sao?
Bạn đánh giá tác động của trusted packages và type headers khi deserialize message từ producer không hoàn toàn tin cậy như thế nào?
Bạn xử lý record có key hợp lệ nhưng value không đọc được mà vẫn giữ được thông tin topic, partition và offset để điều tra như thế nào?
Bạn thiết kế kiểm thử poison-pill record gây lỗi deserializer để xác nhận container không bị mắc kẹt vĩnh viễn như thế nào?
Bạn giải thích vai trò của DeadLetterPublishingRecoverer trong việc chuyển record hết khả năng xử lý sang Dead Letter Topic như thế nào?
Bạn quyết định chiến lược đặt tên Dead Letter Topic theo source topic và partition để dễ truy vết nhưng không gây xung đột như thế nào?
Bạn thiết kế destination resolver của DeadLetterPublishingRecoverer khi các nhóm lỗi cần các DLT riêng như thế nào?
Bạn xác định khi nào DLT cần số partitions tương ứng với source topic để giữ khả năng gắn record vào partition gốc như thế nào?
Bạn phân biệt publish thành công tới DLT với khẳng định record đã được phục hồi nghiệp vụ như thế nào?
Bạn thiết kế quy tắc commit offset cho source record sau khi recoverer đã chuyển DLT thành công theo loại container và ack mode như thế nào?
Bạn phân tích hậu quả khi DLT broker từ chối publish nhưng error handler vẫn coi record đã được recover như thế nào?
Bạn đánh giá khi nào cần xác nhận kết quả gửi DLT trước khi cho phép tiến consumer offset để tránh mất record ra sao?
Bạn xác định metadata tối thiểu nên giữ trong DLT gồm source topic, partition, offset, exception type và số lần thử như thế nào?
Bạn bảo vệ exception message, stack trace và original headers trong DLT khỏi việc làm lộ token hoặc thông tin người dùng ra sao?
Bạn phân biệt DLT dành cho lỗi không thể xử lý với retry topic dùng để trì hoãn thử lại như thế nào?
Bạn tổ chức thời hạn retention, quota và quyền truy cập cho DLT để không bị đầy hoặc giữ dữ liệu nhạy cảm vô thời hạn ra sao?
Bạn thiết kế quy trình vận hành phân loại, sửa dữ liệu rồi replay một nhóm record từ DLT về luồng xử lý như thế nào?
Bạn xác định cách ngăn replay một record đã được xử lý thành công trước đó tạo side effect trùng như thế nào?
Bạn đánh giá trường hợp schema của consumer đã thay đổi sau nhiều ngày và record DLT cũ không còn deserialize được như thế nào?
Bạn thiết kế cơ chế đánh dấu trạng thái đang điều tra, đã sửa, đã replay hoặc loại bỏ có kiểm soát cho các record lỗi như thế nào?
Bạn phân tích nguyên nhân DLT liên tục tăng dù hệ thống vẫn báo consumer group healthy bằng những dữ liệu nào?
Bạn quyết định lúc nào cần dừng phát lại DLT vì downstream đang gặp sự cố hoặc quy tắc nghiệp vụ đã hết hạn như thế nào?
Bạn giải thích khác biệt giữa non-blocking retry topics của Spring Kafka và retry có backoff ngay trong listener thread như thế nào?
Bạn sử dụng @RetryableTopic hoặc retry topic configuration theo phiên bản Spring Kafka để tách những lần thử lại khỏi partition nguồn như thế nào?
Bạn thiết kế dải retry topics và delay backoff phù hợp với yêu cầu latency và khả năng chịu lỗi của downstream ra sao?
Bạn phân tích vì sao đưa record sang retry topic có thể thay đổi thứ tự xử lý so với các records tiếp theo ở source partition như thế nào?
Bạn xác định các hạn chế của non-blocking retry khi phối hợp với Kafka transactions hoặc một số dạng listener/batch processing như thế nào?
Bạn quyết định khi nào thứ tự theo business key quan trọng hơn lợi ích giảm head-of-line blocking từ non-blocking retry như thế nào?
Bạn kiểm tra số lần thử và original topic headers khi một record đi qua nhiều retry topics trước khi tới DLT như thế nào?
Bạn đánh giá rủi ro tạo quá nhiều retry topics hoặc partitions khiến tăng tải metadata và vận hành cluster như thế nào?
Bạn thiết kế test mô phỏng lần thử đầu lỗi, các lần sau thành công và xác minh record không còn bị chuyển DLT ra sao?
Bạn xử lý trường hợp một retry consumer bị dừng lâu khiến việc retry trễ hơn thời gian sống còn của nghiệp vụ như thế nào?
Bạn phân biệt idempotency ở listener với idempotency của Kafka producer khi retry tạo lại cùng một business event như thế nào?
Bạn giải thích quá trình Kafka consumer group rebalance làm thay đổi quyền sở hữu partitions của các listener như thế nào?
Bạn phân biệt eager rebalance với cooperative rebalance về phạm vi partitions phải thu hồi và tác động tới thời gian dừng xử lý ra sao?
Bạn xác định cách chọn partition assignment strategy theo số consumers, số partitions và yêu cầu hạn chế movement như thế nào?
Bạn phân tích hiện tượng consumer cứ liên tục rebalance dù Kafka cluster vẫn hoạt động bình thường bằng những dấu hiệu nào?
Bạn giải thích mối liên hệ giữa max.poll.interval.ms, thời gian xử lý records và consumer group rebalance như thế nào?
Bạn phân biệt session.timeout.ms, heartbeat.interval.ms và max.poll.interval.ms theo từng kiểu failure mà broker/coordinator phát hiện ra sao?
Bạn thiết kế giới hạn max.poll.records phù hợp khi một record có thể xử lý lâu và consumer phải duy trì poll cadence ra sao?
Bạn đánh giá tác động của listener chờ external API nhiều phút khiến poll loop bị trễ và partitions được chuyển sang consumer khác như thế nào?
Bạn xử lý trường hợp một partition bị revoke giữa lúc business transaction đang chạy để tránh ghi dữ liệu trùng hoặc sai thứ tự ra sao?
Bạn sử dụng ConsumerAwareRebalanceListener để quan sát partitions được assigned, revoked và lost theo những tình huống nào?
Bạn phân biệt callback onPartitionsRevoked với onPartitionsLost về khả năng còn sở hữu partition và rủi ro commit offset như thế nào?
Bạn thiết kế cleanup state theo partition khi consumer mất ownership mà không xóa nhầm trạng thái của business operation đã commit như thế nào?
Bạn xác định khi nào commit offsets trong rebalance callback còn hợp lệ và cách xử lý commit failure do thay đổi generation ra sao?
Bạn đánh giá khả năng static membership bằng group.instance.id giảm rebalance khi container/instance restart ngắn như thế nào?
Bạn phân tích rủi ro hai consumer có cùng group.instance.id trong deployment khiến group bị fencing như thế nào?
Bạn thiết kế rolling deployment consumer instances để giảm tác động rebalance, lag và duplicate processing ra sao?
Bạn xác định cách quan sát số lần rebalance và thời gian partitions không có consumer để biết ảnh hưởng tới SLA như thế nào?
Bạn phân biệt assignment của partitions cho Kafka consumers với concurrency setting của ConcurrentMessageListenerContainer như thế nào?
Bạn thiết kế xử lý stateful theo partition mà không giả định cùng một partition luôn chạy trên cùng thread hoặc pod như thế nào?
Bạn đánh giá khi nào tăng concurrency chỉ làm tăng số consumers nhàn rỗi vì số partitions hiện có không đủ như thế nào?
Bạn xử lý tình huống partition nóng khiến một consumer có lag rất cao trong khi các partitions khác gần như rỗng ra sao?
Bạn xác định cách xử lý một record lỗi đúng lúc rebalance mà không commit offset của những records chưa hoàn tất như thế nào?
Bạn giải thích producer acknowledgment acks=all giúp độ bền ghi dữ liệu và khác biệt với acks=1 hoặc acks=0 như thế nào?
Bạn phân biệt replication factor với min.insync.replicas khi đánh giá điều kiện broker chấp nhận một bản ghi bền vững ra sao?
Bạn xác định vai trò của enable.idempotence trong Kafka producer và những giới hạn của nó đối với duplicate business events như thế nào?
Bạn phân tích các điều kiện cấu hình retries, acks và max.in.flight.requests.per.connection liên quan tới idempotent producer và ordering như thế nào?
Bạn thiết kế KafkaTemplate send có callback hoặc CompletableFuture xử lý lỗi producer mà không coi việc gọi send là đã publish thành công như thế nào?
Bạn phân biệt producer send timeout với việc broker đã ghi record nhưng client không nhận được acknowledgment như thế nào?
Bạn lựa chọn delivery.timeout.ms, request.timeout.ms và retry backoff khi producer có SLA độ trễ cụ thể ra sao?
Bạn xác định cách xử lý lỗi RecordTooLargeException hoặc serialization failure mà không retry vô hạn như lỗi mạng tạm thời như thế nào?
Bạn đánh giá mức độ bảo đảm từ idempotent producer khi application restart rồi phát lại cùng một nghiệp vụ với producer identity khác ra sao?
Bạn phân biệt producer idempotence trong một producer session với exactly-once semantics của transactional Kafka processing như thế nào?
Bạn giải thích transactional.id cho phép broker phát hiện producer generation cũ và fencing zombie producer ra sao?
Bạn thiết kế transactionIdPrefix duy nhất cho các instances dùng Spring Kafka để tránh fencing lẫn nhau như thế nào?
Bạn phân biệt KafkaTransactionManager với transaction manager của JDBC khi service vừa ghi database vừa publish Kafka message như thế nào?
Bạn giải thích quy trình consume-process-produce sử dụng Kafka transaction để ghi output records cùng consumed offsets như thế nào?
Bạn xác định vai trò của sendOffsetsToTransaction và consumer group metadata trong việc bảo vệ consume-process-produce như thế nào?
Bạn phân biệt isolation.level=read_committed với read_uncommitted khi consumer đọc records từ transactional producers ra sao?
Bạn đánh giá vì sao exactly-once của Kafka không tự làm giao dịch cập nhật PostgreSQL và Kafka commit nguyên tử như thế nào?
Bạn thiết kế transactional outbox khi một database update và một Kafka event phải cùng thể hiện một quyết định nghiệp vụ như thế nào?
Bạn phân biệt outbox giảm nguy cơ mất event với cơ chế chống publish hoặc consume trùng khi relay được retry như thế nào?
Bạn quyết định khi nào dùng Kafka transaction thuần và khi nào cần outbox hoặc idempotent consumer để phối hợp với hệ thống bên ngoài như thế nào?
Bạn phân tích thứ tự commit giữa Kafka transaction và database transaction khi hai transaction managers được dùng chung workflow như thế nào?
Bạn xác định hành vi khi Kafka transaction commit thất bại sau khi database transaction đã commit và cách phục hồi an toàn ra sao?
Bạn giải thích vì sao Kafka exactly-once vẫn có thể chạy lại code xử lý record nếu transaction trước bị abort như thế nào?
Bạn thiết kế idempotency key từ event ID và business operation để cập nhật database an toàn trước consumer replay ra sao?
Bạn phân biệt dedup bằng unique constraint trong database với dedup chỉ lưu trong memory của consumer theo khả năng phục hồi như thế nào?
Bạn xử lý tình huống record có cùng event ID nhưng payload khác nhau để phát hiện lỗi dữ liệu thay vì bỏ qua im lặng như thế nào?
Bạn thiết kế bảng processed_events với unique key và transaction chung với business update để đạt hiệu ứng xử lý một lần tại database như thế nào?
Bạn đánh giá ảnh hưởng của retention hoặc TTL của dedup store tới việc replay record Kafka rất cũ như thế nào?
Bạn xác định cách tránh consumer phát side effect như email hoặc HTTP request trước khi Kafka transaction chắc chắn commit như thế nào?
Bạn phân tích sự khác biệt giữa lỗi khi Kafka transaction abort và lỗi sau khi recoverer chuyển record vào DLT như thế nào?
Bạn lựa chọn AfterRollbackProcessor phù hợp cho transactional listener khi một record lỗi cần seek lại hoặc recovery ra sao?
Bạn đánh giá cách DefaultAfterRollbackProcessor phối hợp với retry và dead-letter recovery trong một transactional Kafka listener như thế nào?
Bạn thiết kế kiểm thử transactional consume-process-produce bị crash trước commit để xác minh output và offset không bị commit một phần ra sao?
Bạn phân biệt xử lý offset khi consumer có transaction với manual acknowledgment ngoài transaction trong các cấu hình được hỗ trợ như thế nào?
Bạn đánh giá những yêu cầu phiên bản broker/client và cấu hình Spring Kafka cần xác minh trước khi tuyên bố hệ thống hỗ trợ EOS ra sao?
Bạn giải thích tại sao backpressure trong consumer Kafka thường cần giới hạn lượng việc đang xử lý và tốc độ poll thay vì chỉ tăng threads như thế nào?
Bạn phân biệt pause/resume consumer với stop/start listener container về partition ownership và khả năng duy trì heartbeats ra sao?
Bạn thiết kế cơ chế tạm pause các partitions khi downstream quá tải mà vẫn cho KafkaConsumer tiếp tục poll để duy trì membership như thế nào?
Bạn xác định khi nào có thể dùng pausePartition hoặc resumePartition để cô lập một partition lỗi mà không dừng cả listener ra sao?
Bạn đánh giá tác động của max.poll.records đối với memory, độ trễ xử lý từng batch và số records phải replay khi lỗi như thế nào?
Bạn thiết kế bounded worker queue khi listener giao việc cho thread pool mà không commit offset trước khi việc thực sự hoàn tất ra sao?
Bạn phân tích nguy cơ xử lý song song records cùng partition phá ordering và cách giới hạn concurrency theo key như thế nào?
Bạn quyết định khi nào dùng batch listener để tăng throughput nhưng vẫn cần xử lý lỗi và retry ở mức từng record như thế nào?
Bạn phân biệt Kafka consumer fetch settings với Spring listener concurrency và executor queue về chỗ phát sinh bottleneck như thế nào?
Bạn lựa chọn partition scaling, consumer concurrency hay tăng năng lực downstream khi consumer lag tăng dưới tải ổn định như thế nào?
Bạn đánh giá vì sao không nên tăng max.poll.interval.ms vô hạn để che giấu một nghiệp vụ xử lý chậm ra sao?
Bạn thiết kế backpressure ở producer khi downstream topic hoặc broker có throughput hạn chế để tránh giữ quá nhiều futures trong bộ nhớ như thế nào?
Bạn xác định khi nào nên dùng batching và compression ở producer mà vẫn giữ ngân sách latency của hệ thống như thế nào?
Bạn giải thích các metric consumer lag, records-consumed-rate và records-lag-max phản ánh những khía cạnh vận hành khác nhau như thế nào?
Bạn phân biệt lag tăng do producer traffic với lag tăng do poison pill, rebalance hoặc listener không đủ throughput như thế nào?
Bạn thiết kế dashboard có lag theo partition, thời gian xử lý listener, retry count và tốc độ DLT để phát hiện bất thường ra sao?
Bạn lựa chọn các metric về poll duration, commit latency, rebalance count và consumer heartbeat để chẩn đoán group không ổn định như thế nào?
Bạn xác định các tín hiệu nào cho thấy listener đang bị blocked bởi database connection pool chứ không phải Kafka broker chậm như thế nào?
Bạn phân tích xu hướng retry backlog và DLT publish failures để cảnh báo trước khi mất khả năng phục hồi record ra sao?
Bạn thiết kế alert trên consumer lag có xét traffic, thời gian tăng liên tục và độ ưu tiên nghiệp vụ thay vì ngưỡng cố định như thế nào?
Bạn phân biệt consumer offset bị reset do retention hết hạn với offset bị thay đổi thủ công khi điều tra một đợt replay lớn ra sao?
Bạn giải thích ảnh hưởng của auto.offset.reset=earliest hoặc latest khi group chưa có offset hợp lệ và rủi ro mất lịch sử ra sao?
Bạn xây dựng quy trình reset offsets của một consumer group có kế hoạch dừng consumers, snapshot vị trí và phương án rollback như thế nào?
Bạn xác định cách replay một khoảng offset có giới hạn phục vụ sửa dữ liệu nhưng không ghi lại side effect không idempotent như thế nào?
Bạn thiết kế công cụ vận hành phân biệt replay có chủ đích với consumer tự đọc lại sau crash để không làm nhiễu audit logs như thế nào?
Bạn kiểm soát quyền của operator khi reset offsets hoặc replay DLT để tránh thay đổi dữ liệu production ngoài ý định như thế nào?
Bạn xác định cách log topic, partition, offset, key hash và correlation ID để truy vết record nhưng không để lộ PII như thế nào?
Bạn thiết kế distributed tracing từ producer qua @KafkaListener tới downstream bằng headers được kiểm soát và chính sách bảo vệ context ra sao?
Bạn đánh giá rủi ro tin vào tenant ID hoặc trace metadata trong message headers đến từ nguồn không đáng tin cậy như thế nào?
Bạn phân biệt authentication của client Kafka với authorization tới topic hoặc consumer group khi thiết kế quyền vận hành như thế nào?
Bạn xác định cách triển khai rolling update deserializer và schema registry compatibility để tránh DLT tăng đột biến như thế nào?
Bạn thiết kế readiness và liveness checks cho Kafka consumer sao cho lag tạm thời không gây restart loop làm rebalance nặng hơn như thế nào?
Bạn đánh giá khi nào phải tạm dừng consuming khi downstream mất kết nối và khi nào cần tiếp tục xử lý các partition độc lập ra sao?
Bạn thiết kế graceful shutdown để listener ngừng poll, hoàn tất in-flight records và commit offsets an toàn trong giới hạn thời gian như thế nào?
Bạn phân tích rủi ro Kubernetes termination grace period ngắn hơn thời gian xử lý batch khiến duplicate records tăng như thế nào?
Bạn xác định cách quản lý static membership và transaction ID khi autoscaling hoặc rollback deployment để tránh fencing và rebalance không mong muốn ra sao?
Bạn xây dựng unit test cho listener với ConsumerRecord và Acknowledgment giả lập để xác minh thứ tự ghi dữ liệu và ack như thế nào?
Bạn sử dụng EmbeddedKafka hoặc Kafka Testcontainers để kiểm thử commit offsets và replay thực tế thay vì chỉ mock KafkaTemplate như thế nào?
Bạn thiết kế integration test hai consumer instances cùng group để kiểm chứng partition assignment và rebalance sau khi một instance dừng như thế nào?
Bạn kiểm thử DefaultErrorHandler với record lỗi tạm thời rồi thành công để xác minh số lần xử lý và kết quả commit như thế nào?
Bạn mô phỏng poison-pill record từ ErrorHandlingDeserializer và kiểm tra record đi DLT thay vì kẹt consumer như thế nào?
Bạn kiểm thử DeadLetterPublishingRecoverer khi DLT producer bị lỗi để bảo đảm source record không bị đánh dấu recover thành công sai như thế nào?
Bạn xây dựng test cho @RetryableTopic khi một record đi qua các retry topics nhưng cuối cùng thành công mà không xuất hiện trên DLT ra sao?
Bạn kiểm thử event bị xử lý lặp sau crash với database unique constraint để chứng minh idempotent business update như thế nào?
Bạn tạo test transaction abort khi consume-process-produce để xác minh consumer read_committed không đọc thấy output chưa commit như thế nào?
Bạn kiểm thử lỗi khi Kafka transaction và JDBC transaction có thứ tự commit khác nhau để lộ những cửa sổ không nguyên tử như thế nào?
Bạn thiết kế test duy trì thứ tự per partition khi consumer xử lý batch, retry và rebalance với payload đại diện như thế nào?
Bạn kiểm thử backpressure bằng cách làm downstream chậm và xác minh pause/resume không làm mất partition ownership như thế nào?
Bạn mô phỏng consumer restart khi đã cập nhật database nhưng chưa commit offset và kiểm tra không tạo side effect trùng ra sao?
Bạn xây dựng performance test với nhiều partitions có độ lệch tải cao để phân tích lag distribution và hiệu quả điều chỉnh concurrency như thế nào?
Bạn sử dụng các synchronization primitives hoặc công cụ chờ có điều kiện để kiểm thử async Kafka processing mà không dựa vào Thread.sleep như thế nào?
Bạn chẩn đoán sự cố production khi lag tăng, rebalance liên tục và DLT cùng phát sinh bằng cách ưu tiên các bước kiểm tra nào?
Bạn đề xuất kiến trúc Spring Kafka đáng tin cậy gồm offset control, retry/DLT, rebalance handling, Kafka transactions, idempotent database updates, backpressure và observability như thế nào?
