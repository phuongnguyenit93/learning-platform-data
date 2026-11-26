Bạn sẽ giải thích vai trò của Spring Kafka trong kiến trúc ứng dụng hướng sự kiện so với việc sử dụng Kafka client trực tiếp như thế nào?
Khi thiết kế luồng sự kiện với Spring Kafka, bạn lựa chọn ranh giới giữa producer, topic và consumer group dựa trên những tiêu chí nào?
Bạn phân tích mối quan hệ giữa topic, partition, offset và consumer group để giải thích khả năng mở rộng của hệ thống như thế nào?
Trong một quy trình cần bảo toàn thứ tự sự kiện của từng đơn hàng, bạn sẽ thiết kế partition key và số partition ra sao?
Những hậu quả kỹ thuật nào có thể phát sinh khi nhiều sự kiện liên quan cùng một thực thể được gửi với các key không nhất quán?
Bạn quyết định khi nào nên dùng topic riêng cho từng loại sự kiện và khi nào nên dùng topic chung chứa nhiều loại sự kiện bằng cách nào?
Bạn sẽ thiết kế khả năng phát lại sự kiện cho một consumer mới mà vẫn tránh gây tác dụng phụ lên nghiệp vụ hiện tại như thế nào?
Retention và log compaction khác nhau ra sao về tác động đến việc đọc lại dữ liệu và thiết kế consumer trong Spring Kafka?
Bạn sẽ giải thích sự khác biệt giữa việc Kafka xác nhận ghi nhận message và việc ứng dụng consumer xử lý nghiệp vụ thành công như thế nào?
Trong những tình huống nào bạn chấp nhận at-most-once, at-least-once hoặc cần xử lý tương đương exactly-once ở cấp nghiệp vụ?
Bạn đánh giá tác động của việc thêm một consumer group mới vào topic đang hoạt động như thế nào?
Bạn thiết kế sự kiện nghiệp vụ chứa những trường dữ liệu nào để consumer ít phụ thuộc vào cấu trúc nội bộ của producer?
Bạn sẽ phân biệt event thông báo một sự việc đã xảy ra với command yêu cầu thực hiện hành động khi thiết kế topic như thế nào?
Khi nhiều hệ thống cùng tiêu thụ một sự kiện, bạn quản lý thay đổi hợp đồng message để tránh làm hỏng consumer cũ ra sao?
Bạn mô tả vòng đời gửi message bằng KafkaTemplate từ lúc tạo ProducerRecord đến khi nhận kết quả gửi bất đồng bộ như thế nào?
ProducerFactory và KafkaTemplate đảm nhận những trách nhiệm khác nhau nào trong cấu hình producer của Spring Kafka?
Khi KafkaTemplate gửi message bất đồng bộ thất bại, bạn phát hiện, ghi nhận và xử lý lỗi ở lớp ứng dụng như thế nào?
Bạn lựa chọn cấu hình acks cho producer dựa trên các yêu cầu độ bền dữ liệu, độ trễ và khả năng chịu lỗi ra sao?
Bạn giải thích quan hệ giữa idempotent producer, retry và khả năng tránh bản ghi trùng tại broker như thế nào?
Những cấu hình producer nào có thể ảnh hưởng đến thứ tự bản ghi khi xảy ra retry và nhiều request đang được gửi đồng thời?
Bạn sẽ điều chỉnh linger.ms, batch.size và compression cho luồng sự kiện lớn với độ trễ chấp nhận được như thế nào?
Khi một tập key được gửi vào topic có phân bố tải mất cân bằng, bạn xác định và cải thiện hiện tượng partition nóng ra sao?
Bạn sẽ lựa chọn gửi message có key hay không có key trong các kịch bản nghiệp vụ khác nhau dựa trên những đánh đổi nào?
Khi cần chọn topic đích theo loại sự kiện, bạn thiết kế lớp producer dùng KafkaTemplate để việc định tuyến dễ kiểm thử ra sao?
Bạn sẽ thêm correlation ID và thông tin truy vết vào Kafka headers ở phía producer như thế nào?
Bạn thiết kế cơ chế xác nhận cho một API HTTP chỉ được coi là thành công sau khi producer nhận được kết quả gửi Kafka ra sao?
Trong trường hợp Kafka broker tạm thời không sẵn sàng, bạn phân biệt lỗi cần retry với lỗi cấu hình producer không thể phục hồi như thế nào?
Bạn sẽ bảo vệ producer khỏi gửi quá tải khi tốc độ tạo sự kiện vượt khả năng tiếp nhận của cụm Kafka ra sao?
Khi nhiều loại payload dùng chung KafkaTemplate, bạn chọn chiến lược serializer và phân tách cấu hình producer như thế nào?
Bạn quản lý vòng đời và tái sử dụng tài nguyên producer trong ứng dụng Spring để tránh chi phí tạo kết nối quá mức ra sao?
Bạn sẽ tổ chức lớp phát sự kiện như thế nào để mã nghiệp vụ không bị phụ thuộc trực tiếp vào KafkaTemplate?
Bạn mô tả cách Spring Kafka tạo listener container và phân phối bản ghi đến phương thức @KafkaListener như thế nào?
Bạn lựa chọn @KafkaListener với record listener hay batch listener dựa trên loại tác vụ và yêu cầu xử lý lỗi ra sao?
ConcurrentKafkaListenerContainerFactory ảnh hưởng đến cấu hình listener, acknowledgment và xử lý lỗi như thế nào?
Bạn xác định id và groupId cho các @KafkaListener để tránh việc consumer vô tình chia sẻ hoặc tách nhóm sai như thế nào?
Khi một phương thức @KafkaListener cần đọc payload, key, partition, offset và headers, bạn tổ chức tham số đầu vào ra sao?
Bạn so sánh việc nhận ConsumerRecord trực tiếp với việc chỉ nhận payload đã chuyển đổi trong @KafkaListener như thế nào?
Các acknowledgment mode của listener container ảnh hưởng đến thời điểm commit offset và nguy cơ đọc lại message như thế nào?
Trong kịch bản xử lý lâu hoặc cần xác nhận sau tác vụ bên ngoài, bạn lựa chọn manual acknowledgment theo tiêu chí nào?
Bạn sẽ giải thích hậu quả của việc commit offset trước khi cập nhật cơ sở dữ liệu hoàn tất như thế nào?
Khi consumer gặp exception trước lúc offset được commit, điều gì quyết định bản ghi có được đọc lại và xử lý tiếp hay không?
Bạn phân tích sự khác biệt giữa xử lý record theo lô và xử lý từng record đối với throughput, thời gian phản hồi và xử lý lỗi ra sao?
Khi một record trong batch bị lỗi, bạn thiết kế chiến lược xác định phần đã xử lý và phần cần đọc lại như thế nào?
Bạn tính toán concurrency của listener dựa trên số partition, số instance ứng dụng và đặc tính xử lý nghiệp vụ ra sao?
Điều gì xảy ra với số consumer đang hoạt động khi concurrency lớn hơn số partition của topic?
Khi consumer group rebalance, bạn bảo vệ công việc đang xử lý dở và hạn chế bản ghi bị xử lý lại ra sao?
Bạn xác định nguyên nhân consumer thường xuyên rời group do thời gian xử lý và cấu hình poll bằng cách nào?
Bạn sẽ phối hợp max.poll.records và max.poll.interval.ms với thời gian xử lý một batch như thế nào?
Trong trường hợp hệ thống phụ thuộc bị quá tải, bạn quyết định pause và resume listener thay vì tiếp tục poll và xử lý theo tiêu chí nào?
Khi một consumer group cần bắt đầu đọc từ đầu hoặc từ cuối topic, bạn giải thích vai trò của offset đã commit và auto.offset.reset như thế nào?
Bạn lựa chọn subscription theo topic so với chỉ định partition cụ thể trong @KafkaListener dựa trên những yêu cầu nào?
Việc tăng số partition trên topic đang chạy có thể ảnh hưởng đến ánh xạ key và bảo toàn thứ tự sự kiện như thế nào?
Bạn sẽ kiểm tra vì sao tăng số instance consumer không làm tăng throughput của một consumer group ra sao?
Bạn thiết kế consumer sao cho có thể xử lý lại cùng một bản ghi mà không tạo ra kết quả nghiệp vụ trùng lặp như thế nào?
Khi producer và consumer dùng các phiên bản schema khác nhau, bạn xác định nguyên nhân lỗi deserialization và hướng tiến hóa schema ra sao?
Bạn lựa chọn JSON, Avro hoặc định dạng message có schema theo những tiêu chí nào về tương thích, hiệu năng và vận hành?
ErrorHandlingDeserializer giúp thay đổi cách lỗi giải mã được đưa vào quy trình xử lý lỗi của Spring Kafka như thế nào?
Bạn sẽ giới hạn kiểu payload được chấp nhận khi deserialization JSON để giảm rủi ro từ dữ liệu không đáng tin cậy ra sao?
Trong topic có log compaction, consumer cần diễn giải bản ghi có giá trị null như thế nào để hỗ trợ sự kiện xóa?
Bạn phân biệt vai trò của serializer, deserializer và message converter trong chuỗi xử lý message của Spring Kafka như thế nào?
Khi producer viết bằng ngôn ngữ khác Java, bạn thiết kế quy ước type information và schema để @KafkaListener đọc message ổn định ra sao?
Bạn sẽ áp dụng chính sách tương thích schema như thế nào để triển khai producer và consumer độc lập theo từng đợt?
Khi payload chứa nhiều phiên bản sự kiện, bạn tổ chức ánh xạ và nâng cấp định dạng trong consumer để tránh trộn logic phiên bản vào nghiệp vụ ra sao?
Bạn phân loại lỗi tạm thời, lỗi dữ liệu vĩnh viễn và lỗi hạ tầng trong listener để chọn phương án phục hồi như thế nào?
DefaultErrorHandler của Spring Kafka tham gia vào quá trình retry và phục hồi record lỗi như thế nào?
Bạn quyết định số lần retry, khoảng nghỉ cố định hay exponential backoff dựa trên đặc điểm của hệ thống phụ thuộc ra sao?
Khi một record luôn gây lỗi, bạn thiết kế dead-letter topic để lưu đủ ngữ cảnh phục vụ điều tra và phát lại như thế nào?
DeadLetterPublishingRecoverer phối hợp với error handler để chuyển record không thể xử lý sang dead-letter topic ra sao?
Bạn so sánh retry trực tiếp trong listener với retry qua các topic riêng theo độ trễ, thứ tự message và tải consumer như thế nào?
Bạn cân nhắc sử dụng @RetryableTopic trong trường hợp nào, và những giới hạn nào cần đánh giá trước khi áp dụng?
Khi retry làm thay đổi thứ tự xử lý các sự kiện cùng key, bạn bảo đảm tính đúng đắn của trạng thái nghiệp vụ như thế nào?
Bạn xây dựng quy trình phát lại message từ dead-letter topic sao cho không tạo vòng lặp lỗi vô hạn ra sao?
Bạn sẽ theo dõi số lần thử, nguyên nhân lỗi ban đầu và lịch sử xử lý message mà không phụ thuộc vào log rời rạc như thế nào?
Khi lỗi deserialization xảy ra trước khi gọi @KafkaListener, bạn cấu hình và kiểm thử tuyến xử lý lỗi ra sao?
Bạn lựa chọn lọc record tại consumer hay chuyển đổi dữ liệu từ producer để tránh xử lý những sự kiện không liên quan như thế nào?
Khi một hệ thống downstream bị gián đoạn dài, bạn kiểm soát retry để tránh làm đầy hàng đợi và gây quá tải cho hệ thống như thế nào?
Bạn giải thích vai trò của KafkaTransactionManager và transaction-capable producer trong một luồng gửi nhiều message như thế nào?
Bạn thiết kế luồng consume-process-produce có transaction để offset đầu vào và kết quả ghi Kafka được phối hợp ra sao?
Consumer với isolation.level=read_committed khác gì khi đọc topic có các bản ghi từ transaction chưa commit hoặc bị abort?
Bạn sẽ làm rõ giới hạn của exactly-once semantics của Kafka đối với việc cập nhật cơ sở dữ liệu hoặc gọi API bên ngoài như thế nào?
Khi một thao tác nghiệp vụ vừa ghi database vừa phát sự kiện Kafka, bạn đánh giá lựa chọn transactional outbox dựa trên những tình huống lỗi nào?
Bạn thiết kế cơ chế chống xử lý trùng bằng event ID và ràng buộc dữ liệu để chịu được redelivery như thế nào?
Trong luồng yêu cầu bảo toàn thứ tự theo key và xử lý song song tốc độ cao, bạn phân bổ công việc giữa partition và thread ra sao?
Khi ứng dụng bị dừng giữa lúc xử lý transaction Kafka, bạn xác minh cơ chế phục hồi và khả năng đọc lại message như thế nào?
Bạn dùng EmbeddedKafka để viết kiểm thử tích hợp cho KafkaTemplate và @KafkaListener với mục tiêu xác minh những hành vi nào?
Khi nào bạn chọn Kafka chạy bằng Testcontainers thay cho broker nhúng để kiểm thử Spring Kafka, và đánh đổi ra sao?
Bạn thiết kế kiểm thử cho retry, backoff và dead-letter topic để chứng minh record lỗi không bị mất như thế nào?
Bạn kiểm thử việc nhiều listener instance cùng xử lý topic có nhiều partition để phát hiện lỗi thứ tự hoặc xử lý trùng ra sao?
Bạn sẽ kiểm thử đường đi của message trong transaction khi có lỗi trước và sau thao tác gửi như thế nào?
Những chỉ số producer và consumer nào bạn theo dõi để phát hiện sớm lỗi gửi, consumer lag và giới hạn throughput?
Bạn sẽ kết hợp Micrometer Observation và thông tin tương quan message để truy vết một sự kiện qua nhiều dịch vụ như thế nào?
Khi cần ghi log lỗi message trong môi trường production, bạn lựa chọn thông tin nào để điều tra mà không làm lộ dữ liệu nhạy cảm?
Bạn xây dựng cảnh báo đối với consumer lag, tốc độ đưa vào dead-letter topic và thời gian xử lý listener như thế nào?
Khi consumer lag tăng liên tục, bạn chẩn đoán nguyên nhân từ partition, concurrency, tốc độ xử lý và broker theo thứ tự nào?
Bạn điều chỉnh cấu hình producer và consumer ra sao khi hệ thống cần throughput cao nhưng vẫn có giới hạn độ trễ nghiêm ngặt?
Khi triển khai phiên bản consumer mới có thay đổi schema, bạn xây dựng kế hoạch rollout và rollback để tránh gián đoạn xử lý như thế nào?
Bạn thiết kế quy trình deploy hoặc scale consumer để hạn chế rebalance kéo dài và giảm nguy cơ xử lý lại record như thế nào?
Một dịch vụ thanh toán đôi lúc tạo hai giao dịch từ cùng một Kafka event, bạn sẽ lần theo offset, commit, retry và idempotency để tìm nguyên nhân như thế nào?
Một topic nhận lượng sự kiện rất lớn nhưng chỉ một partition tăng lag, bạn sẽ phân tích key distribution và đề xuất cách xử lý tình huống đó ra sao?
Sau sự cố broker, producer báo gửi timeout trong khi consumer vẫn nhận được message, bạn xác minh trạng thái gửi và tránh phát sinh sự kiện trùng như thế nào?
Một sự kiện thay đổi trạng thái đơn hàng đến sau sự kiện hủy đơn do retry, bạn thiết kế cách xử lý để trạng thái cuối vẫn đúng như thế nào?
Khi phải chuyển một consumer từ group cũ sang group mới mà không mất khả năng kiểm soát dữ liệu đã xử lý, bạn lập kế hoạch offset và đối soát như thế nào?
Một luồng xử lý tồn kho cần vừa cập nhật database vừa phát sự kiện tiếp theo, bạn đánh giá rủi ro mất đồng bộ và lựa chọn cơ chế bảo đảm nhất quán ra sao?
Khi dead-letter topic tăng đột biến sau một lần triển khai, bạn sẽ ưu tiên những bước điều tra và biện pháp khôi phục nào để hạn chế ảnh hưởng nghiệp vụ?
