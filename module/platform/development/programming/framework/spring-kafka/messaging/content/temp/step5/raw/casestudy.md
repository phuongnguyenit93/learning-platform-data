Một nền tảng thương mại điện tử phát sự kiện đặt hàng qua KafkaTemplate nhưng chỉ ghi nhận việc gọi send thành công, khiến API báo đã giao sự kiện dù broker từ chối lưu bản ghi.
Nhóm xử lý thanh toán gửi thông điệp bằng KafkaTemplate rồi chặn Future để chờ ACK ngay trong thread HTTP, khiến độ trễ API tăng mạnh khi broker mất ổn định.
Ứng dụng tạo KafkaTemplate mới cho mỗi lần gửi hóa đơn thay vì dùng bean Spring quản lý, khiến số kết nối producer và tài nguyên hệ thống tăng theo lưu lượng.
Đội dùng KafkaTemplate gửi dữ liệu không có key cho sự kiện cùng một khách hàng, khiến các lần thay đổi trạng thái được phân bố vào những partition khác nhau và không giữ thứ tự.
Một service đặt orderId làm Kafka record key nhưng hệ thống có một khách tạo hàng triệu đơn và consumer cần xử lý theo customerId, khiến thứ tự theo khách không được bảo đảm.
Nhóm đổi chiến lược tính key từ accountId sang transactionId giữa đợt triển khai, khiến sự kiện của cùng một tài khoản đi sang partition khác và có thể xử lý lệch thứ tự.
Ứng dụng mở rộng số partition của topic đơn hàng đang dùng key hash, khiến những sự kiện mới của cùng key có thể vào partition khác với dữ liệu cũ trong quá trình chuyển đổi.
Đội chọn một key hằng số cho toàn bộ sự kiện nhập kho để giữ thứ tự, khiến mọi record rơi vào một partition và phần lớn consumer trong group không có việc.
Một service gửi sự kiện khuyến mãi bằng KafkaTemplate nhưng thiếu topic trong cấu hình production, khiến lệnh gửi thất bại vì broker không cho phép tự tạo topic.
Nhóm tạo topic với một partition để đơn giản hóa xử lý nhưng lưu lượng tăng gấp mười, khiến một consumer duy nhất thành nút thắt của toàn bộ pipeline.
Ứng dụng có topic chứa dữ liệu theo vùng nhưng message không mang tenantId hoặc region, khiến consumer không thể xác định nơi lưu dữ liệu phù hợp khi nhận record.
Đội phát sự kiện vào topic public có ACL quá rộng, khiến một nhóm dịch vụ không liên quan có thể đọc thông tin đặt hàng từ Kafka.
Một service dùng tên topic phụ thuộc profile nhưng một pod nhận profile sai, khiến chỉ pod đó phát sự kiện thanh toán sang topic staging.
Nhóm gửi thông điệp có payload nhạy cảm lên topic lưu giữ lâu nhưng không xác định retention policy, khiến dữ liệu cá nhân tồn tại ngoài thời gian được phép.
Ứng dụng cấu hình retention.ms ngắn hơn thời gian một consumer có thể ngừng bảo trì, khiến sau khi khởi động lại consumer không thể đọc những record đã hết hạn.
Đội bật cleanup.policy=compact cho topic lịch sử thanh toán cần mọi sự kiện, khiến các bản ghi cũ cùng key bị dọn và báo cáo audit không thể tái dựng đủ giao dịch.
Một service dùng log-compacted topic để đồng bộ trạng thái khách nhưng gửi mỗi bản cập nhật với key ngẫu nhiên, khiến compaction không giữ được một bản cuối trên từng khách.
Nhóm phát Kafka tombstone để xóa trạng thái sản phẩm nhưng consumer JSON cũ không xử lý value null, khiến luồng đồng bộ bị lỗi khi nhận sự kiện xóa.
Ứng dụng dựa vào timestamp record để tính tuổi đơn nhưng một số producer đặt CreateTime theo đồng hồ lệch, khiến cửa sổ tổng hợp xác định sai ngày kinh doanh.
Đội đặt message key bằng email khách hàng cho dễ tra cứu, khiến thông tin định danh xuất hiện trong log broker và metadata công cụ vận hành.
Một service chuyển topic từ ba sang mười hai partition nhưng chưa đánh giá giới hạn connection tới database, khiến nhiều consumer song song tạo áp lực ghi vượt khả năng xử lý.
Nhóm triển khai topic có replication factor thấp trên cluster production, khiến lỗi mất broker gây gián đoạn ghi dù ứng dụng producer vẫn còn chạy.
Ứng dụng đặt min.insync.replicas cao hơn số replica đang hoạt động sau sự cố, khiến producer với acks=all không thể ghi dù leader của partition vẫn sẵn sàng.
Đội dùng acks=0 để giảm độ trễ cho sự kiện xác nhận thanh toán, khiến producer không thể biết bản ghi đã được broker lưu khi đường mạng lỗi.
Một service chỉ dùng acks=1 cho dữ liệu đối soát tài chính, khiến leader báo thành công nhưng một sự cố trước khi replica đồng bộ làm mất sự kiện vừa ghi.
Nhóm bật acks=all cho producer nhưng thiếu cơ chế phản ánh lỗi gửi tới hệ thống nghiệp vụ, khiến khách nhận HTTP 200 dù KafkaTemplate callback ghi thất bại.
Ứng dụng cấu hình retries cao trên producer nhưng idempotence bị vô hiệu hóa, khiến một số sự kiện được ghi trùng sau khi phản hồi ACK của broker bị mất.
Đội bật enable.idempotence nhưng nghiệp vụ tạo paymentId mới ở mỗi retry HTTP, khiến Kafka producer không ngăn được hai giao dịch khác nhau về mặt message.
Một service giảm max.in.flight.requests.per.connection để giữ thứ tự nhưng không đo thông lượng, khiến đường phát sự kiện tồn kho chậm đáng kể khi tải cao.
Nhóm thay đổi max.in.flight cùng cơ chế retry không phù hợp, khiến record được gửi lại có thể xuất hiện sau record mới của cùng partition trong trường hợp lỗi.
Ứng dụng đặt linger.ms rất lớn để gom batch nhưng traffic thưa, khiến sự kiện đặt hàng phải chờ lâu trước khi producer gửi ra broker.
Đội tăng batch.size để tối ưu throughput nhưng payload thường chỉ vài chục byte, khiến chi phí bộ nhớ producer tăng mà băng thông không cải thiện tương ứng.
Một service cấu hình buffer.memory quá thấp so với tốc độ tạo sự kiện, khiến KafkaTemplate send bị chờ hoặc ném lỗi khi broker phản hồi chậm.
Nhóm đặt delivery.timeout.ms ngắn hơn thời gian retry thực tế mong muốn, khiến producer ngừng cố gắng gửi ngay trong đợt broker failover.
Ứng dụng không giới hạn kích thước sự kiện ảnh sản phẩm đính kèm, khiến producer bị từ chối vì record vượt max.request.size dù consumer đã xử lý payload lớn được.
Đội tăng max.request.size ở producer nhưng broker và consumer còn giới hạn message size thấp hơn, khiến upload lớn vẫn không đi hết pipeline.
Một service nén sự kiện bằng gzip nhưng dữ liệu nguồn vốn đã được nén, khiến CPU tăng mà kích thước mạng giảm không đáng kể.
Nhóm đổi compression.type của producer nhưng broker cluster có tài nguyên CPU hạn chế, khiến throughput giảm mạnh khi nhiều topic cùng tăng tải.
Ứng dụng gửi record với header schemaVersion nhưng một đường KafkaTemplate phụ bỏ qua header này, khiến consumer không biết cách deserialize sự kiện từ batch.
Đội phát Message<?> qua Spring Messaging và mong Kafka headers được map nguyên trạng, nhưng header tùy biến bị lọc trong quá trình mapping khiến traceId biến mất.
Một service dùng KafkaHeaders.TOPIC từ dữ liệu đầu vào không tin cậy để xác định nơi gửi, khiến client có thể điều hướng payload tới topic ngoài hợp đồng.
Nhóm đặt KafkaHeaders.KEY dưới dạng object tùy biến mà key serializer không hỗ trợ, khiến một tỷ lệ request chỉ lỗi khi key có kiểu mới.
Ứng dụng muốn gửi payload theo từng partition cụ thể nhưng metadata partition chỉ hợp lệ với cấu hình topic trước khi mở rộng, khiến các record bị từ chối sau migration.
Đội gửi thông điệp tới partition cố định để tách khách VIP nhưng consumer group mới thay đổi cách phân công, khiến tải bị dồn vào một consumer riêng.
Một service phát sự kiện sản phẩm từ hai luồng Java khác nhau nhưng không chuẩn hóa version trước khi gửi, khiến cùng topic có hai cấu trúc message không tương thích.
Nhóm gọi flush sau mỗi KafkaTemplate.send để chắc chắn gửi xong, khiến lợi ích batch và throughput của producer bị giảm khi nhập dữ liệu lớn.
Ứng dụng gọi KafkaTemplate.sendDefault từ một service nhưng cấu hình default topic khác nhau giữa môi trường test và production, khiến sự kiện đến sai đích.
Đội dùng KafkaTemplate.send theo batch gồm hàng nghìn record nhưng không theo dõi từng kết quả Future, khiến một phần gửi lỗi bị báo như toàn bộ lô thành công.
Một service ghi database rồi gửi Kafka event ở hai bước tách rời, khiến database commit thành công nhưng broker gián đoạn và hệ thống ngoài không nhận được thay đổi.
Nhóm phát Kafka event trước khi transaction SQL commit, khiến consumer nhìn thấy đơn hàng chưa tồn tại rồi retry vô hạn khi transaction cuối cùng rollback.
Ứng dụng dùng transactional KafkaTemplate cho một nghiệp vụ có side effect HTTP ngoài Kafka, khiến khi transaction Kafka rollback đối tác vẫn nhận lệnh đã gửi.
Đội cấu hình transactionIdPrefix trùng giữa nhiều instance Spring Kafka, khiến producer của một pod bị producer ở pod khác fencing khi scale lên.
Một service dùng transaction Kafka dài bao gồm gọi dịch vụ ngoài, khiến transaction timeout và commit thất bại khi đối tác phản hồi chậm.
Nhóm định dùng KafkaTemplate.executeInTransaction cho mọi lệnh ghi nhưng một phương thức được gọi qua KafkaTemplate thường, khiến chỉ một phần event tham gia transaction.
Ứng dụng dùng KafkaTransactionManager cho một pipeline đọc-xử lý-ghi nhưng consumer offset được commit độc lập ngoài giao dịch, khiến xử lý lại không như giả định.
Đội quảng bá exactly-once cho một luồng Kafka-to-database nhưng chỉ có transaction Kafka, khiến thao tác SQL vẫn có thể bị ghi trùng khi consumer bị redeliver.
Một service cập nhật tài khoản trong database rồi publish vào Kafka từ một listener, khiến sự cố giữa commit SQL và gửi event làm hai hệ thống mất đồng bộ.
Nhóm dùng transactional producer nhưng code bắt exception rồi bỏ qua, khiến quy trình nghiệp vụ tưởng đã commit dù Kafka transaction bị abort.
Ứng dụng bật isolation.level=read_uncommitted cho consumer sự kiện giao dịch, khiến các bản ghi từ Kafka transaction đã abort vẫn được xử lý.
Đội chuyển consumer sang read_committed nhưng một pipeline latency nhạy cảm không tính thời gian đợi các transaction đang mở, khiến sự kiện xuất hiện muộn hơn dự kiến.
Một service có retry lỗi producer sau transaction timeout nhưng dùng cùng business command không có idempotency key, khiến yêu cầu được xử lý hai lần ở hệ thống đích.
Nhóm cấu hình DefaultKafkaProducerFactory hỗ trợ transaction nhưng số concurrent KafkaTemplate calls vượt tài nguyên producer sẵn có, khiến đường gửi gặp chờ đợi tăng.
Ứng dụng sử dụng producer transactional ID có tiền tố không ổn định qua restart, khiến việc nhận diện producer cũ và vận hành EOS gặp khó trong quá trình failover.
Đội phối hợp Kafka transaction với JDBC transaction và dựa vào một local transaction manager để bảo đảm atomicity cả hai nguồn, khiến suy luận commit khi lỗi không đúng.
Một service dùng outbox table để phát đơn hàng nhưng dispatcher có thể gửi event rồi crash trước khi đánh dấu đã gửi, khiến downstream nhận lại event sau restart.
Nhóm ghi outbox cùng transaction tạo đơn nhưng payload thiếu version, khiến consumer mới không thể phân biệt các schema từ hai bản ứng dụng đang rollout.
Ứng dụng áp idempotent consumer trên Kafka record offset nhưng muốn xử lý lại cùng sự kiện ở topic mới, khiến logic nhận diện trùng không tương thích khi sao chép dữ liệu.
Đội đánh dấu đã xử lý event vào database trước khi thực hiện side effect, khiến khi gửi email thất bại retry bỏ qua email chưa từng gửi thành công.
Một service dùng idempotency key chỉ là partition offset nhưng topic được tái tạo và offset bắt đầu lại, khiến event mới bị coi là bản cũ khi nạp lại.
Nhóm sử dụng transaction xử lý nhiều record nhưng một record hỏng làm toàn bộ batch rollback lặp, khiến những record hợp lệ bị kẹt sau bản ghi lỗi.
Ứng dụng nhận Kafka record kiểu PaymentCreated nhưng producer gửi sự kiện bù trừ khác trên cùng topic, khiến consumer chỉ xử lý một loại và bỏ sót trạng thái hoàn tiền.
Đội dùng @KafkaListener với một topic nhập hàng nhưng topic chưa tồn tại khi startup, khiến container listener không khởi chạy như mong đợi trong cluster không cho auto-create.
Một service khai báo @KafkaListener với groupId tĩnh được sao chép từ ứng dụng thanh toán, khiến hai dịch vụ không liên quan cạnh tranh partition và mỗi bên mất một phần sự kiện.
Nhóm triển khai hai instance cùng consumer group để tăng thông lượng nhưng topic chỉ có một partition, khiến instance thứ hai luôn idle dù CPU còn thừa.
Ứng dụng cần hai nghiệp vụ độc lập cùng nhận mọi event nhưng cấu hình chung group.id, khiến mỗi event chỉ được một nghiệp vụ xử lý thay vì cả hai.
Đội tạo group.id mới cho bản canary của service gửi email, khiến cùng sự kiện được cả canary và production xử lý và khách nhận hai email.
Một service đổi consumer group ID khi deploy mà không đặt auto.offset.reset phù hợp, khiến bản mới bắt đầu đọc từ cuối và bỏ qua toàn bộ lịch sử cần tái xử lý.
Nhóm cấu hình auto.offset.reset=earliest và dùng groupId ngẫu nhiên mỗi lần startup, khiến service đọc lại hàng triệu sự kiện cũ sau mỗi restart.
Ứng dụng bật auto.offset.reset=latest cho dịch vụ vừa thêm và nghĩ sẽ nhận được dữ liệu lịch sử, khiến tất cả record trước thời điểm consumer được tạo bị bỏ qua.
Đội tăng concurrency của @KafkaListener vượt số partition topic, khiến nhiều child containers không được gán partition và việc tăng thread không cải thiện throughput.
Một service gắn hai @KafkaListener vào cùng group với các handler làm việc khác nhau, khiến dữ liệu được phân phối ngẫu nhiên giữa hai logic xử lý.
Nhóm dùng topicPatterns để subscribe nhiều topic nhưng schema payload khác nhau, khiến một consumer nhận loại event không phù hợp và lỗi deserialize.
Ứng dụng dùng @KafkaListener nhận ConsumerRecord nhưng một refactor sang nhận payload DTO trực tiếp làm mất header partition/offset mà audit đang cần.
Đội chuyển từ record listener sang batch listener mà không thay logic xử lý lỗi, khiến một bản ghi lỗi làm cả batch bị retry và side effect các bản trước lặp lại.
Một service sử dụng @KafkaHandler trong class-level @KafkaListener để dispatch nhiều event types nhưng type header không được producer cũ gửi, khiến method handler không chọn được.
Nhóm dùng @Payload và @Header để nhận record nhưng key từ đối tác có thể null, khiến một tham số bắt buộc trong listener gây lỗi conversion chỉ với record hợp lệ.
Ứng dụng khai báo listener parameter là String trong khi value deserializer trả DTO Java, khiến container ném lỗi method argument conversion trước khi logic nghiệp vụ chạy.
Đội bắt RuntimeException trong @KafkaListener rồi ghi log mà không throw lại, khiến container coi record hoàn tất và không kích hoạt retry hoặc DLT.
Một service nhận event không hợp lệ trong listener nhưng ném unchecked exception chung, khiến cùng record bị xử lý lại liên tục và ngăn tiến độ partition.
Nhóm đặt ConsumerFactory riêng với group.id khác nhưng container factory của listener vẫn dùng bean mặc định, khiến cấu hình kiểm thử được nhưng production đọc sai group.
Ứng dụng xử lý nhiều record trong @KafkaListener rồi trả về void mà không xác nhận kết quả từng record, khiến giám sát không thấy những mục bị bỏ qua do business validation.
Đội dùng @KafkaListener đọc topic có khóa khách hàng nhưng chuyển record sang thread pool khác không giữ thứ tự theo partition, khiến cập nhật địa chỉ cũ ghi đè cập nhật mới.
Một service cấu hình asyncAcks cho manual acknowledgment nhưng xử lý kết quả ở worker chậm, khiến commit offset bị trì hoãn và các message khác trong partition chờ theo.
Nhóm gọi acknowledgment.acknowledge ngay khi enqueue record vào memory queue, khiến pod restart trước khi worker xử lý làm mất record nghiệp vụ dù offset đã commit.
Ứng dụng dùng manual acknowledgment sau khi ghi database nhưng việc ghi audit ngoài transaction thất bại, khiến offset commit không phản ánh trạng thái nghiệp vụ đầy đủ.
Đội dùng AckMode.RECORD và kỳ vọng offset được lưu bền ngay lập tức ở mỗi record, khiến khi broker mất kết nối có thể xảy ra redelivery ngoài suy đoán.
Một service chọn AckMode.BATCH nhưng handler xử lý lô dữ liệu lâu, khiến số record có nguy cơ bị xử lý lại khi ứng dụng crash trước lần commit tăng lên.
Nhóm đặt enable.auto.commit=true song song với chiến lược acknowledgment của Spring listener container, khiến offset có thể được commit trước khi xử lý nghiệp vụ hoàn tất.
Ứng dụng dùng consumer.commitSync thủ công trong @KafkaListener nhưng container cũng quản lý commit, khiến vòng đời offset khó đối soát khi exception xảy ra.
Đội chọn commitAsync để giảm latency nhưng không theo dõi lỗi callback, khiến offset không được ghi bền và consumer đọc lại dữ liệu sau rebalance.
Một service xử lý record xong rồi commit offset, nhưng client gọi cơ sở dữ liệu gặp timeout sau khi server đã commit, khiến Kafka redelivery tạo bản ghi nghiệp vụ trùng.
Nhóm tăng max.poll.records để lấy batch lớn nhưng mỗi record gọi API đối tác chậm, khiến khoảng cách giữa các lần poll vượt max.poll.interval.ms và group rebalance.
Ứng dụng đặt max.poll.interval.ms rất thấp so với thời gian import một file lớn, khiến partition được gán lại khi listener vẫn còn xử lý record cũ.
Đội cấu hình session.timeout.ms không phù hợp với network jitter, khiến consumer bị rời group nhiều lần trong đợt tải cao và liên tục mất partition.
Một service triển khai consumer xử lý blocking quá lâu khiến heartbeat không đủ theo cấu hình, khiến broker/coordinator kích hoạt rebalance không cần thiết.
Nhóm dùng consumer.pause để giảm áp lực khi database chậm nhưng không có cơ chế resume khi database phục hồi, khiến lag tăng không giới hạn dù ứng dụng vẫn khỏe.
Ứng dụng dùng seekToCurrent theo logic cũ nhưng đổi Spring Kafka error handler ở phiên bản mới, khiến offset sau lỗi không còn được xử lý như code test trước đó giả định.
Đội cho phép consumer gọi seek về offset cũ khi có yêu cầu hỗ trợ, khiến bản ghi đã tạo side effect được xử lý lại mà không có cơ chế chống trùng.
Một service thực hiện seek theo timestamp để chạy lại dữ liệu nhưng một số partition không có bản ghi đúng thời điểm, khiến khoảng dữ liệu được replay không đồng nhất giữa partitions.
Nhóm triển khai replay toàn bộ topic bằng group mới nhưng DLT consumer vẫn dùng group cũ và cấu hình khác, khiến những record lỗi có hành vi không giống live processing.
Ứng dụng phụ thuộc offset commit để báo số đơn hoàn tất, nhưng một số record bị lọc và vẫn commit, khiến count xử lý thực khác số lượng record đã đọc.
Đội dùng group.id chia sẻ giữa môi trường staging và production trên cùng cluster, khiến hai môi trường tranh nhau phân vùng và dữ liệu thật bị xử lý ở môi trường test.
Một service chạy listener trên nhiều pods nhưng giữ singleton state không được cô lập theo partition, khiến xử lý song song làm sai bộ đếm tồn kho.
Nhóm tăng @KafkaListener concurrency để đáp ứng traffic nhưng một bảng SQL duy nhất bị lock contention, khiến tỉ lệ transaction rollback tăng thay vì throughput.
Ứng dụng có topic với key=accountId và một partition quá nóng do tài khoản lớn, khiến độ trễ của các tài khoản cùng partition tăng dù consumer group còn nhiều instance.
Đội chuyển từ range assignor sang cooperative sticky assignor nhưng quy trình shutdown chưa phù hợp, khiến việc thu hồi partition có nhiều bước xử lý đang chạy cần được đánh giá lại.
Một service dùng static membership group.instance.id giống nhau trên mọi pod, khiến các instance fencing nhau và chỉ một consumer duy trì phiên hoạt động.
Nhóm cho group.instance.id thay đổi mỗi lần container khởi động dù muốn static membership, khiến các lần deploy vẫn tạo rebalance thường xuyên.
Ứng dụng không xử lý ConsumerRebalanceListener khi partition bị revoke, khiến dữ liệu đệm chưa flush bị bỏ khi quyền sở hữu partition chuyển sang pod khác.
Đội dùng rebalance callback thực hiện truy vấn database dài, khiến các consumer trong group chờ đồng bộ và ứng dụng tăng lag sau scale-out.
Một service giữ cache địa phương theo partition nhưng không xóa state khi partition bị revoke, khiến instance nhận partition mới còn dùng dữ liệu từ chủ cũ.
Nhóm theo dõi lag toàn consumer group nhưng không xem partition lag, khiến một partition nóng tồn hàng triệu records bị che bởi trung bình toàn topic.
Ứng dụng dùng ConcurrentMessageListenerContainer với concurrency lớn nhưng một listener gọi thư viện không thread-safe, khiến dữ liệu event bị trộn khi xử lý đồng thời.
Đội xử lý record theo key bằng CompletableFuture trong listener mà không đợi hoàn thành, khiến offset được commit khi các cập nhật cùng khách còn chưa xong.
Một service xử lý nhiều partitions đồng thời nhưng service gọi API ngoài có quota một luồng, khiến nhiều child consumers liên tục nhận lỗi rate limit.
Nhóm dùng Kafka record timestamp làm thời điểm phát sinh nghiệp vụ nhưng event có thể được ghi muộn sau network partition, khiến báo cáo tuần tự theo thời gian bị sai.
Ứng dụng định sắp xếp toàn bộ giao dịch theo offset nhưng dữ liệu nằm nhiều partitions, khiến bộ tổng hợp giả định một trật tự toàn cục không tồn tại.
Đội dùng offset số nhỏ để xem record luôn cũ hơn nhưng topic đã được truncate/recreate, khiến idempotency theo offset không còn bảo đảm tính duy nhất.
Một service dùng @KafkaListener nhận key null cho trạng thái tài khoản nhưng dự kiến mọi cập nhật một account được cùng partition, khiến thứ tự xử lý không đúng hợp đồng.
Nhóm phát record thay đổi nhiều bảng trong một transaction SQL nhưng key mỗi event khác nhau, khiến consumer không thể dựa vào partition ordering để khôi phục thứ tự commit.
Ứng dụng cần đọc trạng thái cuối nhưng topic compacted vẫn có các bản ghi cũ chưa được dọn ngay, khiến consumer phải xử lý nhiều cập nhật trước khi dựng state mới.
Đội dùng Kafka Streams-like mental model cho Spring Kafka record listener nhưng chưa có state store bền, khiến bước tổng hợp trong memory mất tiến độ sau restart.
Một service tạo dữ liệu sự kiện JSON bằng StringSerializer nhưng consumer dùng JsonDeserializer<OrderEvent>, khiến deserialization lỗi trước khi @KafkaListener được gọi.
Nhóm đổi từ JSON sang Avro cho topic thanh toán mà không tách version/topic, khiến một nhóm consumer cũ không hiểu dữ liệu vừa được phát.
Ứng dụng dùng Jackson JsonSerializer mặc định nhưng service downstream đòi một custom property name, khiến chỉ event có field mới bị deserialize sai.
Đội cấu hình JsonDeserializer trusted.packages quá hẹp cho class sự kiện mới, khiến listener từ chối payload dù JSON hợp lệ và tên topic đúng.
Một service dùng trusted.packages=* để xử lý nhanh lỗi type metadata nhưng message đến từ nguồn không đáng tin, khiến phạm vi lớp được chấp nhận quá rộng.
Nhóm thay tên Java package của Event DTO nhưng vẫn phát JSON type headers cũ, khiến deserializer ở consumer mới không tìm thấy class theo metadata.
Ứng dụng có producer gửi type headers theo Java class nội bộ nhưng consumer viết ngôn ngữ khác không hiểu type mapping đó, khiến hợp đồng topic phụ thuộc chi tiết triển khai Java.
Đội cấu hình JsonDeserializer với removeTypeHeaders nhưng một downstream listener phụ thuộc header loại message, khiến việc chuyển đổi làm mất tín hiệu dispatch.
Một service dùng ErrorHandlingDeserializer để bắt record hỏng nhưng error handler không nhận đúng exception metadata, khiến những bản ghi không thể deserialize vẫn kẹt ở offset hiện tại.
Nhóm sử dụng value.deserializer trực tiếp khi gặp malformed JSON, khiến exception xảy ra trước listener và chính sách retry nghiệp vụ không xử lý được record như dự kiến.
Ứng dụng gửi event giá sản phẩm dưới dạng double trong JSON nhưng consumer dùng BigDecimal cho phép đối soát, khiến kết quả làm tròn sai ở những giao dịch có nhiều chữ số thập phân.
Đội thay định dạng date từ ISO-8601 sang epoch milliseconds mà không cập nhật schema contract, khiến consumer cũ hiểu timestamp sai tại thời điểm chuyển phiên bản.
Một service thêm field bắt buộc để xác thực sự kiện nhưng các record lịch sử không có field này, khiến chạy replay bị lỗi ở cả những event từng được chấp nhận.
Nhóm dùng một topic cho nhiều loại event với cùng JSON serializer nhưng không có discriminator, khiến @KafkaHandler không phân biệt lệnh tạo và lệnh hủy đơn.
Ứng dụng sử dụng Schema Registry cho Avro nhưng client production không truy cập được registry, khiến producer không thể serialize record đầu tiên dù broker vẫn khỏe.
Đội đổi Avro schema xóa field cũ không có default, khiến consumer dùng schema đọc phiên bản mới thất bại trong rolling deployment.
Một service có schema compatibility policy BACKWARD nhưng muốn khôi phục dữ liệu do client rất cũ ghi, khiến khả năng đọc tất cả lịch sử cần được đánh giá riêng với bản liền trước.
Nhóm sử dụng Protobuf serializer với schema registry nhưng class sinh mã giữa producer/consumer khác phiên bản, khiến cùng topic có các field không được hiểu giống nhau.
Ứng dụng nhận JSON record key là UUID nhưng KeyDeserializer vẫn là StringDeserializer, khiến hàm phân vùng theo key được consumer diễn giải khác với logic nghiệp vụ.
Đội gửi null value làm tombstone cho topic compacted nhưng listener method yêu cầu payload non-null, khiến sự kiện xóa không được áp dụng trong cache.
Một service dùng @Payload(required=false) nhận tombstone nhưng logic nghiệp vụ lại dựa vào payload để lấy customerId, khiến không biết thực thể nào cần xóa nếu bỏ qua record key.
Nhóm triển khai converter StringJsonMessageConverter cho một listener factory nhưng listener khác dùng consumer factory không qua converter, khiến cùng DTO được xử lý khác nhau theo endpoint.
Ứng dụng đổi serializer value sang ByteArraySerializer trong một nhánh producer nhưng consumer mặc định JSON, khiến những sự kiện từ nhánh này bị gửi DLT hàng loạt.
Đội dùng Kafka header contentType để chọn converter nhưng một producer ngoài Spring không gửi header, khiến consumer áp dụng định dạng mặc định sai.
Một service gửi record vượt max.partition.fetch.bytes trên consumer nhưng nhóm chỉ tăng producer max.request.size, khiến một partition xử lý chậm hoặc gặp lỗi fetch bất thường.
Nhóm bật compression trên Kafka producer nhưng bài kiểm thử deserialize chỉ dùng uncompressed payload thủ công, khiến sai khác giữa client thật và mock chưa được kiểm chứng.
Ứng dụng log toàn bộ JSON event khi deserialize thất bại, khiến các trường địa chỉ và số tài khoản đi vào kho logs không có chính sách lưu giữ tương ứng.
Đội nhận event từ tenant khác qua shared topic nhưng chỉ dựa vào type header để chấp nhận, khiến một payload hợp kiểu vẫn vượt ranh giới phân quyền nghiệp vụ.
Một service sử dụng DefaultErrorHandler cho @KafkaListener nhưng backoff không có giới hạn phù hợp, khiến một record sai schema chặn partition suốt ca vận hành.
Nhóm cấu hình FixedBackOff với số lần thử nhỏ cho lỗi mạng tạm thời kéo dài vài phút, khiến nhiều giao dịch hợp lệ bị đưa vào DLT trước khi dịch vụ ngoài phục hồi.
Ứng dụng dùng ExponentialBackOff dài ngay trong listener nhưng max.poll.interval.ms không phù hợp, khiến retry kéo dài gây rebalance liên tục.
Đội triển khai DeadLetterPublishingRecoverer nhưng topic DLT không tồn tại hoặc producer không có ACL ghi, khiến xử lý record lỗi tiếp tục thất bại sau khi đã hết retry.
Một service gửi record lỗi vào DLT cùng partition số với source topic nhưng DLT có ít partition hơn, khiến recoverer không publish được cho những partition cao.
Nhóm tiêu thụ từ topic orders.DLT nhưng payload từ lỗi deserialization không theo kiểu OrderEvent như listener thông thường, khiến quy trình phục hồi lại thất bại.
Ứng dụng ghi record vào DLT sau lỗi nghiệp vụ nhưng không giữ original topic, partition, offset trong headers, khiến đội vận hành khó đối soát nguồn gốc.
Đội tự publish lỗi vào dead-letter topic rồi vẫn throw exception từ listener, khiến cùng record có thể được gửi DLT nhiều lần sau các vòng retry.
Một service DLT consumer tự động retry vô hạn mà không có can thiệp cho dữ liệu sai vĩnh viễn, khiến topic lỗi trở thành vòng lặp xử lý không có điểm dừng.
Nhóm cấu hình retry theo exception type nhưng RuntimeException do lỗi validation được coi là retriable, khiến một payload sai lặp hàng chục lần trước DLT.
Ứng dụng dùng DefaultErrorHandler cho lỗi timeout nhưng không phân biệt timeout sau khi downstream đã commit, khiến lần retry tạo nghiệp vụ trùng.
Đội có Recoverer trả thành công sau khi log message lỗi nhưng không lưu DLT/audit, khiến offset được commit và record mất khả năng phục hồi.
Một service dùng @RetryableTopic để tạo non-blocking retry topics nhưng nghiệp vụ yêu cầu giữ thứ tự cập nhật cùng accountId, khiến event mới vượt event cũ đang chờ retry.
Nhóm bật @RetryableTopic cho consumer chạy transaction nhưng chưa đánh giá sự tương thích giữa non-blocking retry và container transaction, khiến hợp đồng xử lý lỗi không rõ.
Ứng dụng cấu hình retry topic theo số lần thử nhưng các topic delay chưa được tạo ở production, khiến deployment startup thất bại hoặc retry không tiến hành.
Đội dùng @DltHandler cho bản ghi không thể xử lý nhưng method chỉ chấp nhận DTO đã deserialize, khiến payload bytes gây lỗi lần đầu tiếp tục không được phục hồi.
Một service thực thi @DltHandler để gửi email hỗ trợ nhưng handler lỗi vì hệ thống email đang down, khiến record vẫn mắc kẹt ở dead-letter processing.
Nhóm tạo nhiều @KafkaListener độc lập cùng tên retry topic trong một ứng dụng nhưng không phân biệt group, khiến sự kiện lỗi từ hai nghiệp vụ bị tiêu thụ nhầm.
Ứng dụng áp RetryListener để ghi lần thử nhưng traceId từ Kafka headers không được truyền vào MDC của retry callback, khiến các lần thử của cùng event bị tách khỏi trace.
Đội cấu hình CommonErrorHandler toàn ứng dụng cho cả record và batch listeners nhưng phương thức xử lý partial batch failure không tương đương, khiến nhiều record đã xử lý bị replay.
Một service dùng BatchListenerFailedException chỉ định index bị lỗi nhưng dữ liệu đã được xử lý song song ngoài thứ tự, khiến index không còn phản ánh đúng vị trí chưa hoàn tất.
Nhóm chạy batch listener, bắt lỗi record thứ ba rồi commit cả batch thay vì những phần đã thực sự xử lý, khiến hai record cuối bị mất mà không đi DLT.
Ứng dụng sử dụng AfterRollbackProcessor khi transaction abort nhưng recovery path không idempotent, khiến một record có thể tạo nhiều thông báo vận hành trong các lần rollback.
Đội áp retry cho tất cả lỗi gồm authorization từ broker và validation của record, khiến hệ thống tiêu tốn tài nguyên vào các lỗi không thể tự hồi phục.
Một service chuyển event từ DLT về topic chính sau khi sửa bug nhưng không kiểm soát số lần replay, khiến cùng bản ghi được phát lại nhiều lần và ghi trùng.
Nhóm khôi phục batch từ DLT nhưng source topic đã đổi schema, khiến record cũ không còn có thể đi qua listener mới mà thiếu quá trình tương thích.
Ứng dụng đặt retention của DLT quá ngắn so với quy trình phê duyệt xử lý sự cố, khiến bản ghi lỗi bị xóa trước khi kỹ sư có thể điều tra.
Đội dùng chung DLT cho các tenant khác nhau nhưng công cụ support không giới hạn quyền theo tenant, khiến người trực có thể xem dữ liệu của khách khác.
Một service gửi lỗi xuống DLT rồi ghi thành công nghiệp vụ vào dashboard, khiến tỷ lệ xử lý thực tế bị báo cao dù nhiều đơn chưa được hoàn tất.
Nhóm đặt recoverer vào topic DLT trên cluster khác nhưng không có giám sát tình trạng cross-cluster network, khiến lỗi mạng làm mất khả năng xử lý cuối cùng.
Ứng dụng giới hạn retry theo số attempts nhưng một lần khởi động lại ứng dụng làm logic đọc retry state khác nhau, khiến số lần thử nghiệp vụ vượt chính sách.
Đội dùng blocking retries lâu cho một hot partition, khiến mọi record hợp lệ đứng sau lỗi đầu tiên bị tăng lag dù cluster còn nhiều consumer rảnh.
Một service áp retry theo ngày cho sự kiện giá chứng khoán nhưng dữ liệu đã mất giá trị nghiệp vụ sau vài phút, khiến record đến muộn gây cập nhật sai.
Nhóm tạo quy trình hỗ trợ manual replay nhưng không ghi who/when/reason vào audit, khiến sau sự cố không thể giải thích vì sao một order được xử lý lại.
Ứng dụng cần bù trừ khi gửi DLT nhưng error handler chỉ lưu bản gốc, khiến trạng thái database còn đang ở bước xử lý dở mà chưa có tác vụ khôi phục.
Đội thiết kế consumer cho cơ chế at-least-once delivery nhưng chỉ bật idempotent producer, khiến side effect tại database vẫn có thể lặp lại khi offset commit thất bại.
Một service dùng KafkaTransactionManager cho listener đọc và KafkaTemplate ghi kết quả nhưng offset của consumer không được đưa vào transaction như team kỳ vọng, khiến record có nguy cơ bị gửi lại.
Nhóm tạo transactional listener nhưng gửi một response Kafka bằng producer không transactional, khiến output đã phát vẫn tồn tại sau khi input transaction abort.
Ứng dụng đổi transactionIdPrefix khi rolling deploy nhưng dùng cùng worker identity ở nhiều pod, khiến producer fencing xuất hiện khi bản cũ và mới chạy chồng.
Đội xử lý Kafka-to-Kafka bằng transaction nhưng producer không có ACL Write trên topic kết quả, khiến transaction liên tục abort và record đầu vào được giao lại trong lúc sự cố phân quyền chưa được khắc phục.
Một service cập nhật bảng tài khoản bằng JDBC bên trong @KafkaListener transactional Kafka, khiến Kafka transaction rollback không tự rollback SQL nếu ranh giới giao dịch khác.
Nhóm dùng ChainedKafkaTransactionManager kiểu cũ trong ứng dụng nâng Spring Kafka nhưng chưa đánh giá quy tắc commit giữa Kafka và database, khiến lỗi ở transaction thứ hai tạo trạng thái lệch.
Ứng dụng bật Kafka EOS cho một batch gồm nhiều records nhưng một thành phần ghi file bên ngoài, khiến dữ liệu file không được thu hồi khi Kafka transaction thất bại.
Đội khai báo isolation.level=read_committed nhưng consumer offset lag tăng khi một producer giữ transaction mở quá lâu, khiến dashboard báo consumer chậm dù xử lý đủ nhanh.
Một service retry sau ProducerFencedException như lỗi mạng thông thường, khiến transactional producer tiếp tục không thể ghi mà recovery không chuyển sang instance hợp lệ.
Nhóm gặp InvalidProducerEpochException khi thay đổi thành viên cluster nhưng chỉ ghi log và tiếp tục gửi record trong cùng transaction, khiến các lần commit sau tiếp tục thất bại.
Ứng dụng tạo transaction chứa nhiều nghìn messages trong thời gian dài, khiến broker giữ trạng thái transaction lớn và độ trễ đọc committed tăng.
Đội đặt transaction.timeout.ms cao hơn transaction.max.timeout.ms broker cho phép, khiến producer transactional không khởi tạo được sau đợt thay cấu hình.
Một service dùng Spring @Transactional cho phương thức gọi KafkaTemplate nhưng transaction manager được chọn là JDBC, khiến nhóm tưởng event tự động tham gia Kafka transaction.
Nhóm xử lý sự kiện nghiệp vụ bằng một database và Kafka, nhưng một lỗi gửi event ở bước cuối được catch rồi bỏ qua, khiến API trả thành công dù hệ thống ngoài chưa đồng bộ.
Ứng dụng dùng outbox bảo đảm sự kiện có thể phát lại nhưng consumer không idempotent khi đọc event, khiến retry outbox tạo thêm hóa đơn.
Đội xử lý đúng một lần trong Kafka nội bộ nhưng hệ thống email đối tác không có idempotency, khiến khách vẫn nhận hai email khi mạng lỗi và job retry.
Một service chạy nhiều threads xử lý cùng một tài khoản từ các partitions khác nhau, khiến optimistic locking liên tục conflict và rollback dù Kafka producer đã idempotent.
Nhóm đặt transaction boundary quanh quá trình xử lý streaming batch rất dài, khiến consumer vượt poll interval và group rebalance trước khi commit.
Ứng dụng muốn bảo đảm thứ tự các sự kiện AccountDebited và AccountCredited nhưng phát chúng lên hai topic riêng, khiến consumer không có trật tự liên topic để dựa vào.
Đội dùng transactional Kafka producer phát nhiều topic nhưng một client cần đọc cả hai ở hai consumer groups khác nhau, khiến góc nhìn dữ liệu ở ứng dụng đích không đồng thời như giả định.
Một service coi successful send result metadata là dấu hiệu Kafka transaction đã commit, khiến dashboard công bố event trước khi transaction hoàn tất.
Nhóm chạy chuỗi thanh toán qua Kafka với yêu cầu chống trùng, nhưng business event ID không được lưu vào cơ sở dữ liệu consumer, khiến crash sau commit tạo side effect hai lần.
Ứng dụng gọi KafkaTemplate.send trong một method non-transactional từ luồng async, khiến thao tác không nằm trong Kafka transaction của listener ở thread ban đầu.
Đội đánh dấu offset đã xử lý trong Redis với TTL ngắn nhưng sự kiện có thể được replay sau nhiều tuần, khiến những transaction cũ không còn được nhận diện là trùng.
Một service dùng dedup key chỉ là orderId nhưng cùng order có nhiều event hợp lệ Create/Paid/Refunded, khiến những trạng thái sau bị loại nhầm.
Nhóm nhận cùng event từ topic chính và topic replay cùng lúc nhưng không có eventId toàn cục, khiến database nhận hai cập nhật trùng trong ca khôi phục.
Ứng dụng cần bù trừ khi consumer gặp lỗi giữa hai bước, nhưng Kafka transaction chỉ đảm bảo output và offset, khiến một dịch vụ HTTP ngoài đã xử lý bước trước không được tự thu hồi.
Đội xây luồng chính sách tiền tệ dựa vào Kafka timestamp nhưng sự kiện đến muộn sau retry, khiến thứ tự business event time và partition append time không trùng.
Một service gửi cả command lẫn event vào cùng topic và cùng consumer group, khiến khi command được retry tự động event mới tiếp tục chờ không được xử lý.
Nhóm chỉ dùng số offset làm version của bản ghi trong database, khiến dữ liệu từ partition khác có offset thấp bị coi như cập nhật cũ dù thực tế mới hơn.
Ứng dụng nhận message lớn qua Kafka và xử lý JSON bằng parser giữ toàn bộ object, khiến heap tăng đột biến khi nhiều listeners chạy đồng thời.
Đội tăng fetch.max.bytes để tăng throughput nhưng RAM consumer bị giới hạn, khiến khi group có nhiều partitions một lần poll vượt ngân sách bộ nhớ.
Một service để max.partition.fetch.bytes quá nhỏ với record lớn, khiến việc đọc những message lớn cần kiểm tra lại hành vi fetch và giới hạn tài nguyên.
Nhóm đặt fetch.min.bytes cao để tối ưu network nhưng topic traffic thấp, khiến consumer đợi lâu trước khi nhận các sự kiện cần xử lý gần thời gian thực.
Ứng dụng cấu hình fetch.max.wait.ms quá dài cho hệ thống báo động, khiến alert quan trọng bị trì hoãn dù broker đã có record nhỏ chờ đọc.
Đội bật batch listener để giảm chi phí database nhưng API ngoài yêu cầu xử lý từng event ngay, khiến latency của record đầu tăng do chờ gom lô.
Một service có @KafkaListener concurrency bằng hai mươi nhưng MySQL chỉ cho phép mười connections, khiến phần lớn threads bị chặn khi lấy connection.
Nhóm xử lý sự kiện video lớn và tăng số partitions nhưng KafkaTemplate producer buffer.memory không đổi, khiến burst publishing tiếp tục vượt giới hạn buffer.
Ứng dụng có consumer chậm do tính toán PDF đồng bộ trong listener, khiến lag tăng mà CPU broker gần như không sử dụng.
Đội xây consumer chạy trên Kubernetes nhưng resource CPU limits thấp, khiến heartbeat/rebalance và xử lý record bị ảnh hưởng khi container bị throttling.
Một service đặt partition.assignment.strategy khác nhau giữa các thành viên group khi rolling deploy, khiến group không ổn định cho đến khi tất cả pod dùng cấu hình tương thích.
Nhóm dùng client.id trùng nhau cho tất cả producers, khiến metrics và logs không phân biệt instance gây timeout khi broker quá tải.
Ứng dụng chạy Kafka producer trên một pod có lỗi DNS thoáng qua nhưng không giám sát metadata refresh, khiến các send bị đợi hàng chục giây khi cluster thay leader.
Đội thay đổi bootstrap.servers sang một broker nội bộ duy nhất, khiến khi broker đó mất mạng những pod mới không lấy được metadata dù cluster còn healthy.
Một service thiết lập security.protocol=PLAINTEXT cho môi trường production yêu cầu SSL, khiến KafkaTemplate không kết nối được ngay trong quá trình publish đầu tiên.
Nhóm xoay chứng chỉ TLS của broker nhưng producer container còn truststore cũ, khiến các kết nối Kafka mới liên tục lỗi handshake trong khi những pod cũ vẫn hoạt động.
Ứng dụng dùng SASL/SCRAM credentials chung cho staging và production, khiến người có quyền truy cập thử nghiệm có thể đọc topic dữ liệu thật.
Đội cấp ACL Read cho consumer group nhưng quên Read cho topic, khiến @KafkaListener khởi động được context Spring nhưng không thể fetch records.
Một service có quyền Write topic chính nhưng không có quyền DLT, khiến error recovery thất bại đúng lúc có record hỏng cần lưu để xử lý sau.
Nhóm sử dụng wildcard ACL quá rộng cho producer chung, khiến một service bị lộ credential có thể publish message vào topic thanh toán của ứng dụng khác.
Ứng dụng gắn tenantId vào Kafka header và dùng nó để quyết định quyền truy cập dữ liệu, khiến một producer không đáng tin có thể giả mạo tenant trong record.
Đội gửi JWT toàn bộ trong Kafka headers để phục vụ downstream nhưng consumer group có quyền đọc topic không phù hợp, khiến token người dùng bị phát tán vượt phạm vi.
Một service log ConsumerRecord bao gồm value JSON và tất cả headers khi retry, khiến số tài khoản, email và token bị lưu vào log giám sát.
Nhóm dùng message key là số điện thoại khách và hiển thị key trong metrics label, khiến thông tin cá nhân xuất hiện trong hệ thống observability.
Ứng dụng phát record nội bộ có schema chứa dữ liệu sức khỏe lên topic được dùng chung nhiều team, khiến quyền đọc không phản ánh mức nhạy cảm mới của payload.
Đội dùng serializer tùy biến để mã hóa payload nhưng key vẫn chứa định danh khách ở dạng rõ, khiến metadata topic tiếp tục bộc lộ thông tin không cần thiết.
Một service muốn chuyển consumer sang cluster khác nhưng replication tool chưa đồng bộ hết offsets, khiến nhóm không biết cần bắt đầu lại ở vị trí nào mà không làm mất dữ liệu.
Nhóm chuẩn bị chuyển Kafka topics sang cluster mới nhưng producer ghi song song hai nơi mà không có định danh sự kiện chung, khiến consumer có thể xử lý cùng giao dịch hai lần.
Ứng dụng bật cluster failover bằng đổi bootstrap.servers nhưng transactional producer IDs tại cluster mới khác, khiến tính đúng đắn của transaction liên cluster cần được xác định lại.
Đội dùng MirrorMaker để nhân bản event sang region dự phòng nhưng consumer ở region đó dùng offset của cluster gốc, khiến tiến độ đọc sau failover không tương ứng.
Một service nhận event từ hai cluster Kafka khác nhau cho cùng đơn hàng nhưng không có global ordering/idempotency, khiến bản cập nhật cũ ghi đè bản mới.
Nhóm triển khai producer retries trong thời gian failover nhưng không đặt giới hạn queue publish, khiến backlog trong memory tăng tới lúc pod bị OOM.
Ứng dụng gửi sự kiện cho hơn một triệu khách khi ra mắt sản phẩm nhưng topic chỉ có vài partitions, khiến consumer lag và thời gian kích hoạt thông báo kéo dài hàng giờ.
Đội đặt quota publish theo client.id nhưng nhiều producers dùng chung ID, khiến lưu lượng của một service quan trọng bị throttling bởi workload khác.
Một service đọc topic compacted để dựng cache khởi tạo nhưng thời gian bootstrap lâu hơn readiness timeout, khiến pod bị restart trước khi cache sẵn sàng.
Nhóm ghi last processed timestamp vào database ở cuối batch nhưng chưa ghi offset theo cách nhất quán, khiến báo cáo lag tự xây không phản ánh đúng tiến độ Kafka.
Ứng dụng theo dõi consumer lag toàn group mà không cảnh báo bản ghi lỗi trên DLT, khiến service trông đã bắt kịp trong khi nhiều đơn chưa được xử lý thành công.
Đội chỉ đo số record @KafkaListener nhận mỗi giây nhưng không đo số record xử lý thành công, khiến retry và filtering làm báo cáo throughput bị thổi phồng.
Một service dùng Micrometer metrics cho KafkaTemplate nhưng tất cả producers mang cùng tag topic=unknown, khiến nhóm trực không xác định topic đang bị chậm.
Nhóm gắn orderId làm metric label cho mỗi Kafka send, khiến cardinality tăng hàng triệu time series và backend metrics bị quá tải.
Ứng dụng kết nối OpenTelemetry tracing từ HTTP đến Kafka producer nhưng không chuyển traceparent headers sang consumer, khiến một giao dịch bị chia thành hai trace.
Đội theo dõi latency bằng thời điểm Kafka producer bắt đầu send nhưng không đo thời gian record chờ trong topic, khiến SLA end-to-end bị đánh giá thấp.
Một service đo timestamp của Kafka record và thời gian xử lý nhưng broker dùng LogAppendTime còn producer dùng CreateTime, khiến biểu đồ lag có lúc âm.
Nhóm triển khai cảnh báo khi group lag tăng nhưng không xem rebalance frequency, khiến nguyên nhân root-cause về group membership bị bỏ qua trong ca sự cố.
Ứng dụng theo dõi producer send error count nhưng không phân biệt retriable broker errors và serialization errors, khiến on-call retry sai loại sự cố.
Đội viết dashboard DLT chỉ thống kê số record nhưng không phân loại original topic và exception class, khiến lỗi schema rollout bị che trong nhóm lỗi chung.
Một service có retry topics với hàng chục nghìn record chờ và báo main topic lag gần 0, khiến dashboard cho rằng xử lý đã kịp trong khi dữ liệu nghiệp vụ chưa được hoàn tất.
Nhóm duy trì Kafka logs với debug bật và producer payload lớn, khiến disk hệ thống log bị đầy trước khi có cảnh báo Kafka broker storage.
Ứng dụng dùng Spring Kafka Observation cho một listener nhưng một listener khác cấu hình factory riêng không bật, khiến trace của một nhánh nghiệp vụ bị mất.
Đội vận hành phát hiện consumer group rebalance liên tục nhưng logs không có client.id/instance ID, khiến không xác định được pod gây mất heartbeat.
Một service có consumer pause khi database lỗi nhưng dashboard chỉ theo dõi broker availability, khiến Kafka còn khỏe mà luồng nghiệp vụ đứng yên không phát cảnh báo.
Nhóm đặt retry delay tăng dần nhưng không gắn attempt number vào audit, khiến khách nhìn thấy cùng event có nhiều kết quả mà đội hỗ trợ không tìm được nguyên nhân.
Ứng dụng cần đối soát số payment events được publish với số bản ghi SQL, nhưng không có business eventId chung nên không xác minh được event thất lạc sau sự cố.
Đội đo publish throughput bằng số lần KafkaTemplate.send được gọi mà không tính callback failure, khiến tỷ lệ gửi thành công bị báo cao hơn thực tế.
Một service gắn headers correlationId từ HTTP request nhưng một batch publisher chạy từ scheduler không có request context, khiến sự kiện batch thiếu định danh để điều tra.
Nhóm tạo KafkaProducerListener để ghi audit send failures nhưng callback ném exception, khiến đường thông báo lỗi producer không được giám sát như thiết kế.
Ứng dụng nhận lỗi authentication Kafka sau credential rotation nhưng metrics chỉ phân loại send timeout, khiến kỹ sư tăng broker capacity thay vì sửa chứng thực.
Đội chạy unit test @KafkaListener bằng gọi trực tiếp method Java, khiến lỗi container startup, deserializer, groupId và offset acknowledgment không được phát hiện.
Một service mock KafkaTemplate.send trả Future đã hoàn tất nhưng không mô phỏng failure sau khi broker nhận record, khiến logic retry HTTP không được thử về idempotency.
Nhóm dùng @EmbeddedKafka kiểm tra producer/consumer nhưng test không có security và TLS như production, khiến lỗi SASL handshake bị bỏ qua trước release.
Ứng dụng chạy Testcontainers Kafka và topic auto-create, trong khi production cấm tự tạo topic, khiến một consumer mới chỉ thất bại khi deploy thật.
Đội test gửi một event với một partition và một consumer nhưng production chạy nhiều partitions/concurrency, khiến sai thứ tự per-customer không được phát hiện.
Một service test consumer group bằng một instance duy nhất nhưng không khởi chạy hai instances để kiểm tra rebalance khi pod rời nhóm đột ngột.
Nhóm tạo test KafkaTemplate chỉ xác nhận record có mặt trong topic nhưng không assert key/partition, khiến thay đổi key dẫn tới ordering regression mà CI vẫn xanh.
Ứng dụng kiểm thử JSON serialization với DTO hiện tại nhưng không đọc lại bản ghi từ schema cũ, khiến các events còn trong topic sau deploy không deserialize được.
Đội test JsonDeserializer trên event hợp lệ nhưng không gửi malformed bytes, khiến ErrorHandlingDeserializer và DLT recovery chưa được kiểm chứng.
Một service kiểm thử DefaultErrorHandler bằng RuntimeException giả nhưng không mô phỏng lỗi từ deserializer xảy ra trước listener, khiến một poison pill làm kẹt partition thật.
Nhóm chạy bài test retry với một lỗi transient duy nhất nhưng chưa thử số lần thất bại vượt giới hạn, khiến record không được chuyển DLT sau khi hết attempts.
Ứng dụng test DeadLetterPublishingRecoverer với DLT có cùng partitions như source nhưng production DLT cấu hình ít partitions hơn, khiến chỉ vài source partitions không thể recover.
Đội thử @RetryableTopic bằng một listener thành công ngay lần thứ hai nhưng không kiểm tra event mới vượt event cũ đang retry, khiến thứ tự cập nhật không được bảo đảm.
Một service unit test manual acknowledgment bằng mock nhưng không kill process giữa side effect và commit, khiến redelivery sau crash chưa được đánh giá.
Nhóm kiểm thử AckMode.BATCH với toàn bộ records hợp lệ nhưng không ném exception ở phần tử thứ ba, khiến cơ chế replay một phần lô chưa được chứng minh.
Ứng dụng test consumer pause/resume chỉ khi không có records, khiến trường hợp backlog và concurrent pending acknowledgments chưa được mô phỏng.
Đội chạy integration tests với hai consumers trong cùng group nhưng không kiểm tra static membership duplicate ID, khiến cấu hình group.instance.id giống nhau qua các pods chưa bị phát hiện.
Một service test transactional KafkaTemplate với send thành công nhưng không ép transaction abort giữa nhiều records, khiến read_committed contract chưa được xác nhận.
Nhóm kiểm thử KafkaTransactionManager trong isolation nhưng không có JDBC side effect, khiến suy luận exactly-once Kafka-to-database chưa được thử.
Ứng dụng dùng Testcontainers Kafka để thử replay nhưng tạo topic mới cho mọi bài test, khiến hành vi offset reset của group đã có lịch sử chưa được kiểm tra.
Đội kiểm tra kết quả listener bằng lệnh gọi đồng bộ nhưng không chờ offset commit thật, khiến kiểm thử đôi lúc PASS dù consumer sẽ redeliver sau restart.
Một service test DLT consumer với payload DTO bình thường nhưng trong production DLT chứa raw bytes từ deserialization failure, khiến handler không đọc được record cần cứu.
Nhóm mô phỏng producer timeout bằng Future exception nhưng không kiểm tra trạng thái database sau khi broker đã có thể ghi, khiến code retry tạo event trùng.
Ứng dụng benchmark Kafka producer với record vài byte nhưng production dùng JSON lớn kèm headers, khiến thông số throughput không dự đoán được áp lực bộ nhớ thực.
Đội thử consumer xử lý nhanh trong local Docker nhưng không dùng downstream database latency production, khiến max.poll.interval.ms quá ngắn chỉ lộ ra khi tải cao.
Một service kiểm tra Kafka callback thành công nhưng không mô phỏng broker leader failover, khiến producer retry và acks assumptions chưa được chứng minh.
Nhóm nâng Spring Kafka version đồng thời đổi container factory nhưng integration tests chỉ mock KafkaConsumer, khiến thay đổi error handler và acknowledgment semantics không được phát hiện.
Ứng dụng cần chứng minh duplicate event không làm tăng số dư nhưng suite chỉ chạy một record cho mỗi orderId, khiến yêu cầu idempotency không được chứng minh.
Đội muốn xác minh ordering sau thay đổi số partitions nhưng test không phát event của cùng key trước và sau partition expansion, khiến trạng thái bị ghi lùi ở production.
Một service kiểm thử consumer DLT replay khi không có traffic khác nhưng không thử concurrent live processing, khiến record cũ có thể ghi đè record mới trong ca khôi phục.
Nhóm đo SLA từ lúc KafkaTemplate gửi đến khi @KafkaListener commit nhưng không tính các records nằm trên retry topics, khiến báo cáo thời gian xử lý thực bị thấp giả.
Ứng dụng cần chứng minh trạng thái đơn hàng không mất khi broker, database và consumer thay nhau lỗi, nhưng tài liệu hiện chỉ dựa trên ACK của producer mà không có kiểm thử khôi phục end-to-end.
