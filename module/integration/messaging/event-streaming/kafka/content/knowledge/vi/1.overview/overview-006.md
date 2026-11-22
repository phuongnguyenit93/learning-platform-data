# Khi nào nên dùng Kafka và khi nào nên chọn giải pháp khác

Apache Kafka là nền tảng event streaming phù hợp khi hệ thống cần ghi nhận luồng sự kiện bền vững, xử lý lượng dữ liệu lớn, cho phép nhiều ứng dụng tiêu thụ độc lập và có khả năng đọc lại dữ liệu trong một khoảng thời gian. Tuy nhiên, Kafka không phải lựa chọn mặc định cho mọi giao tiếp giữa các dịch vụ. Một API HTTP, hàng đợi công việc, cơ sở dữ liệu có outbox, dịch vụ pub/sub được quản lý hoặc một hệ thống lập lịch có thể giải quyết bài toán đơn giản hơn với chi phí vận hành thấp hơn.

Trong module KAFKA, bạn sẽ học cách xây dựng event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện bằng Java/Spring Kafka; xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams; rồi giám sát, tối ưu và phục hồi cụm. Trước khi học cách vận hành các thành phần đó, cần biết khi nào kiến trúc Kafka thực sự phù hợp và khi nào nên chọn giải pháp khác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt event streaming với request-response, message queue và pub/sub đơn giản.
- Nhận diện các dấu hiệu cho thấy Kafka mang lại giá trị rõ rệt.
- So sánh Kafka với HTTP/gRPC, RabbitMQ, dịch vụ queue/pub-sub được quản lý, Redis Streams, NATS và CDC.
- Chọn giải pháp dựa trên độ bền dữ liệu, khả năng replay, fan-out, thứ tự, độ trễ, thông lượng và chi phí vận hành.
- Phân tích một tình huống nghiệp vụ và đề xuất kiến trúc phù hợp.
- Nhận biết các trường hợp dùng Kafka quá mức hoặc dùng Kafka sai mô hình.

## 2. Bắt đầu từ bài toán giao tiếp

Trước khi chọn công nghệ, hãy trả lời câu hỏi: các thành phần trong hệ thống cần trao đổi điều gì?

Có ba mô hình giao tiếp thường gặp:

1. **Request-response:** một thành phần gọi thành phần khác và cần nhận kết quả để tiếp tục. Ví dụ, API đặt hàng gọi dịch vụ tính thuế và cần số tiền thuế ngay trong cùng yêu cầu.
2. **Work queue:** một thành phần giao một công việc cho worker xử lý. Mỗi công việc thường cần được một worker nhận và xác nhận hoàn thành. Ví dụ, tạo ảnh thumbnail hoặc gửi một email.
3. **Event streaming:** một thành phần công bố sự kiện đã xảy ra; một hoặc nhiều thành phần khác tự quyết định đọc, xử lý và có thể đọc lại sự kiện. Ví dụ, Order Service công bố OrderCreated để hệ thống kho, thanh toán, phân tích và thông báo cùng sử dụng.

Các mô hình có thể kết hợp trong một hệ thống. Một API có thể trả lời người dùng bằng HTTP, ghi sự kiện vào outbox trong cùng giao dịch cơ sở dữ liệu, sau đó một tiến trình phát sự kiện sang Kafka. Không cần ép toàn bộ giao tiếp vào một công nghệ duy nhất.

### 2.1. Kafka cung cấp mô hình log sự kiện

Kafka lưu record theo topic và partition. Producer ghi record nối tiếp vào log của partition; mỗi record có offset. Consumer đọc record theo offset và quản lý vị trí đọc của mình thông qua offset đã commit.

Một số đặc điểm làm Kafka khác với hàng đợi truyền thống:

- Record được giữ lại theo chính sách retention hoặc log compaction, không bị xóa chỉ vì một consumer đã đọc hoặc xác nhận xử lý.
- Nhiều consumer group có thể đọc cùng một topic độc lập. Mỗi group có offset riêng.
- Một consumer group chia các partition cho các consumer trong group để xử lý song song. Trong một group, một partition tại một thời điểm chỉ được gán cho tối đa một consumer.
- Thứ tự được bảo đảm trong từng partition. Nếu cần thứ tự theo một thực thể, producer thường dùng key ổn định để các sự kiện của thực thể đó đi vào cùng partition.
- Consumer có thể đọc lại dữ liệu còn trong thời hạn lưu giữ bằng cách thay đổi offset hoặc tạo group mới.

Ví dụ, topic orders chứa các sự kiện đơn hàng. Order Service ghi OrderCreated. Inventory Service, Billing Service và Analytics Service là ba consumer group khác nhau. Mỗi group có thể đọc cùng luồng sự kiện theo tốc độ riêng; việc Billing Service đã đọc một record không làm record biến mất trước khi Analytics Service đọc.

~~~mermaid
flowchart LR
    P["Order Service<br/>Producer"] --> T[("Topic: orders")]
    T --> I["Inventory group"]
    T --> B["Billing group"]
    T --> A["Analytics group"]
    I --> IDB[("Inventory DB")]
    B --> BDB[("Billing DB")]
    A --> WH[("Analytics warehouse")]
~~~

Kafka phù hợp với mô hình này vì sự kiện có thể được chia sẻ giữa nhiều hệ thống, mỗi hệ thống có tiến độ xử lý riêng và dữ liệu có thể được đọc lại trong thời gian retention.

### 2.2. Hàng đợi công việc có vòng đời khác

Trong một work queue truyền thống, một message thường được giao cho một worker; sau khi worker xác nhận, message được loại khỏi hàng đợi. Nếu worker lỗi trước khi xác nhận, message có thể được giao lại. Broker thường cung cấp các tính năng như routing key, priority, delayed delivery, dead-letter queue và acknowledgement theo từng message.

Kafka có thể được dùng để phân phối công việc, nhưng cơ chế xử lý khác. Consumer đọc theo offset của partition; commit offset thường xác nhận tiến độ của một đoạn log, không phải xóa riêng từng record. Retry và xử lý lỗi cần được thiết kế với partition ordering, offset commit, retry topic hoặc cơ chế tương ứng. Vì thế, nếu yêu cầu cốt lõi là giao từng công việc, xác nhận từng message, định tuyến linh hoạt và trì hoãn từng công việc, một hệ thống queue chuyên dụng có thể phù hợp hơn.

## 3. Khi nào Kafka là lựa chọn phù hợp?

Kafka thường đáng cân nhắc khi nhiều điều kiện sau cùng xuất hiện.

### 3.1. Có luồng sự kiện liên tục và thông lượng đáng kể

Hệ thống tạo ra nhiều sự kiện trong thời gian dài, ví dụ clickstream, telemetry, giao dịch, trạng thái thiết bị, nhật ký ứng dụng hoặc sự kiện nghiệp vụ. Kafka ghi dữ liệu theo log partition và mở rộng khả năng xử lý bằng cách tăng partition, broker và consumer song song.

Không có một ngưỡng số record mỗi giây cố định để quyết định dùng Kafka. Một ứng dụng có vài trăm sự kiện mỗi giây vẫn có thể cần Kafka nếu yêu cầu replay và nhiều consumer rất quan trọng. Ngược lại, hàng triệu record mỗi ngày chưa tự động chứng minh Kafka là cần thiết nếu chỉ có một tác vụ đơn giản và không cần giữ lịch sử.

Hãy đánh giá thông lượng trung bình và đỉnh, kích thước record, số partition, thời gian lưu giữ, số consumer group, tốc độ tăng dữ liệu và khả năng chịu tải của hệ thống đích. Thông lượng không nên là tiêu chí duy nhất.

### 3.2. Nhiều hệ thống cần sử dụng cùng một sự kiện

Một sự kiện có thể phục vụ nhiều mục đích. Ví dụ OrderCreated có thể được dùng bởi:

- Inventory Service để giữ hàng.
- Payment Service để khởi tạo thanh toán.
- Notification Service để gửi thông báo.
- Analytics Service để cập nhật báo cáo.
- Fraud Detection để đánh giá rủi ro.

Các consumer group có thể phát triển và triển khai độc lập. Producer không cần biết tất cả consumer hiện tại là ai. Khi thêm một consumer group mới, nhóm đó có thể đọc dữ liệu còn lưu trong topic theo chính sách offset của mình.

Đây là giá trị lớn của event streaming trong kiến trúc nhiều dịch vụ: producer công bố sự kiện nghiệp vụ, còn các hệ thống tiêu thụ độc lập với nhau về thời gian triển khai và tốc độ xử lý.

### 3.3. Cần đọc lại dữ liệu để phục hồi hoặc xây dựng chức năng mới

Replay hữu ích khi:

- Một consumer bị lỗi trong vài giờ và cần xử lý bù.
- Một dịch vụ mới cần xây dựng trạng thái từ các sự kiện đã phát sinh.
- Logic xử lý được sửa và cần chạy lại trên dữ liệu cũ.
- Một pipeline phân tích cần tái tạo dữ liệu trong một khoảng thời gian.
- Một consumer group bị mất trạng thái cục bộ và cần khôi phục từ luồng sự kiện.

Khả năng replay phụ thuộc vào retention, offset, schema và khả năng xử lý lặp an toàn của ứng dụng. Kafka không lưu dữ liệu vô thời hạn theo mặc định. Nếu record đã hết hạn retention hoặc bị loại theo chính sách compaction, consumer không thể replay phần dữ liệu đã mất từ topic đó.

Cũng cần phân biệt event log với hệ thống lưu trữ hồ sơ nghiệp vụ. Nếu pháp lý hoặc nghiệp vụ yêu cầu lưu trữ dài hạn, tra cứu chính xác hoặc chống sửa đổi, cần thiết kế chính sách archive, backup, kiểm soát truy cập và lưu trữ chuyên dụng. Không nên mặc định một topic Kafka là kho lưu trữ tuân thủ mọi yêu cầu.

### 3.4. Cần tách producer khỏi thời điểm xử lý của consumer

Producer có thể ghi sự kiện ngay cả khi một consumer đang tạm dừng, miễn là cụm còn khả năng nhận ghi theo cấu hình. Consumer có thể xử lý sau, theo tốc độ của nó. Điều này giúp các dịch vụ ít phụ thuộc vào trạng thái tức thời của nhau.

Tuy nhiên, Kafka không làm cho mọi lỗi downstream tự biến mất. Nếu consumer chậm hơn tốc độ phát sinh sự kiện trong thời gian dài, consumer lag và lượng dữ liệu tồn đọng sẽ tăng. Cần có cảnh báo, năng lực xử lý đủ lớn và kế hoạch khi dữ liệu tồn đọng vượt giới hạn thời gian hoặc dung lượng.

### 3.5. Cần thứ tự theo từng thực thể

Kafka bảo đảm thứ tự record trong một partition. Nếu tất cả sự kiện của cùng một order được ghi vào cùng partition, consumer có thể quan sát chúng theo thứ tự đã ghi trong partition đó.

Ví dụ:

~~~text
key = orderId

OrderCreated(order-123)
PaymentAuthorized(order-123)
OrderPacked(order-123)
OrderShipped(order-123)
~~~

Khi các record cùng key được ánh xạ nhất quán vào một partition, thứ tự của chúng được giữ trong partition. Điều này hữu ích với trạng thái đơn hàng, tài khoản, thiết bị hoặc một thực thể có vòng đời.

Kafka không cung cấp thứ tự toàn cục giữa các partition. Nếu một nghiệp vụ yêu cầu mọi sự kiện của mọi khách hàng phải theo một thứ tự duy nhất, một partition duy nhất có thể tạo nút thắt về thông lượng và khả năng song song. Hãy xác định chính xác phạm vi thứ tự cần bảo đảm trước khi thiết kế key và partition.

### 3.6. Cần xử lý luồng và tích hợp hệ sinh thái

Kafka có hệ sinh thái phù hợp cho luồng dữ liệu: Kafka Connect hỗ trợ kết nối nguồn/đích; Kafka Streams hỗ trợ xử lý, kết hợp, tổng hợp và quản lý trạng thái trên luồng; các ứng dụng Java/Spring Kafka có thể tích hợp trực tiếp với producer, consumer và transaction.

Khi cần chuyển dữ liệu từ cơ sở dữ liệu sang nhiều hệ thống, CDC có thể đưa thay đổi dữ liệu vào Kafka. Khi cần tổng hợp sự kiện theo thời gian hoặc kết hợp nhiều luồng, Kafka Streams có thể giảm nhu cầu tự xây dựng một hệ thống xử lý stream từ đầu.

Hệ sinh thái này có giá trị khi tổ chức thật sự cần pipeline dữ liệu lâu dài. Nếu chỉ cần một lần gọi API hoặc một job nhỏ, thêm Kafka Connect, Streams và schema infrastructure có thể tạo thêm gánh nặng.

## 4. Khi nào nên chọn giải pháp khác?

### 4.1. Cần kết quả ngay trong cùng một yêu cầu: HTTP hoặc gRPC

Nếu một dịch vụ cần câu trả lời để quyết định kết quả trả cho người dùng, request-response thường là lựa chọn trực tiếp nhất.

Ví dụ: Checkout Service cần xác minh địa chỉ giao hàng hoặc tính phí vận chuyển trước khi trả tổng tiền. Gọi HTTP/gRPC giúp nhận kết quả ngay, có thể đặt timeout, deadline và xử lý lỗi theo yêu cầu.

Kafka không phải lựa chọn tự nhiên cho request-response đồng bộ vì producer ghi record và consumer xử lý bất đồng bộ. Có thể xây dựng request-reply qua Kafka bằng correlation ID, reply topic và timeout, nhưng mô hình đó tăng độ phức tạp và không thay thế được lợi ích của một API đồng bộ khi người gọi thực sự cần câu trả lời tức thời.

Có thể kết hợp hai mô hình: API đồng bộ xử lý bước cần phản hồi nhanh, sau đó công bố sự kiện để các dịch vụ khác xử lý nền.

### 4.2. Cần hàng đợi tác vụ với xác nhận từng message: RabbitMQ hoặc queue service

RabbitMQ hoặc dịch vụ queue được quản lý thường phù hợp khi mỗi message đại diện cho một công việc cần một worker nhận và xác nhận hoàn thành.

Ví dụ: gửi email, tạo thumbnail, xử lý hóa đơn PDF, gửi webhook hoặc chạy một tác vụ có thời gian trì hoãn. Các tính năng thường quan trọng là:

- Acknowledgement theo từng message.
- Routing theo exchange, binding hoặc routing key.
- Priority hoặc delayed delivery.
- Dead-letter exchange/queue.
- Giới hạn số message đang xử lý và điều phối worker.

Kafka có thể triển khai các workflow tương tự, nhưng cần thiết kế retry topic, dead-letter topic, offset commit và thứ tự trong partition. Nếu hệ thống chủ yếu cần một work queue với nhiều quy tắc phân phối, RabbitMQ hoặc queue service thường dễ diễn đạt ý định hơn.

### 4.3. Muốn queue được quản lý và không muốn vận hành cụm: dịch vụ cloud queue

Nếu tổ chức chạy trên cloud và muốn giảm công việc quản trị broker, có thể chọn dịch vụ như Amazon SQS, Google Cloud Tasks hoặc Azure Service Bus tùy nền tảng và yêu cầu.

Các dịch vụ này thường cung cấp queue, retry, visibility timeout, dead-letter queue, quyền truy cập và khả năng mở rộng do nhà cung cấp quản lý. Chúng phù hợp với tác vụ bất đồng bộ, tích hợp ứng dụng và workload không cần một event log dùng chung để replay dài hạn.

Nếu cần fan-out, có thể kết hợp dịch vụ notification/pub-sub với queue riêng cho từng subscriber. Cần xem xét giới hạn kích thước message, retention, thứ tự, throughput, chi phí theo request và mức độ phụ thuộc vào nhà cung cấp.

### 4.4. Cần luồng nhỏ, nhẹ hoặc giao tiếp thời gian thực đơn giản: Redis Streams hoặc NATS

Redis Streams có thể phù hợp với luồng dữ liệu ở quy mô vừa phải khi hệ thống đã dùng Redis và muốn tận dụng consumer group, stream entry ID và cơ chế pending entry. Tuy nhiên, cần hiểu chính sách persistence, replication, memory, retention và giới hạn vận hành của Redis trong triển khai cụ thể.

NATS phù hợp với giao tiếp message nhẹ, độ trễ thấp và mô hình pub/sub linh hoạt. NATS JetStream bổ sung persistence và khả năng lưu/đọc lại message. Đây có thể là lựa chọn tốt cho hệ thống cần messaging nhẹ hoặc kết nối dịch vụ, tùy vào yêu cầu replay, retention, ordering và quy mô.

Không nên chọn chỉ dựa vào benchmark độ trễ. Hãy so sánh cách hệ thống xử lý consumer chậm, mất kết nối, replay, replication, xác nhận, phân quyền và vận hành khi có sự cố.

### 4.5. Cần lưu trạng thái hiện tại: cơ sở dữ liệu

Nếu câu hỏi chính là “trạng thái đơn hàng hiện tại là gì?” hoặc “số dư tài khoản hiện tại bao nhiêu?”, cơ sở dữ liệu thường là nguồn truy vấn phù hợp. Kafka lưu luồng sự kiện và có thể giúp cập nhật các read model, nhưng không thay thế trực tiếp truy vấn có điều kiện, transaction và constraint của cơ sở dữ liệu.

Một kiến trúc thường gặp là:

- Database lưu trạng thái nghiệp vụ và bảo đảm ràng buộc giao dịch.
- Outbox ghi sự kiện cần phát trong cùng transaction với thay đổi nghiệp vụ.
- CDC hoặc outbox relay chuyển sự kiện sang Kafka.
- Consumer cập nhật read model, cache hoặc hệ thống downstream.

Không nên dùng Kafka làm nơi duy nhất để thay thế cơ sở dữ liệu quan hệ nếu ứng dụng cần transaction nhiều bản ghi, truy vấn tùy ý, join, constraint và cập nhật trạng thái có điều kiện.

### 4.6. Cần đưa thay đổi cơ sở dữ liệu thành sự kiện: CDC

Nếu yêu cầu là chuyển các thay đổi insert/update/delete từ database vào luồng sự kiện, CDC như Debezium có thể phù hợp. CDC đọc transaction log của database và phát thay đổi ra Kafka hoặc đích khác.

CDC hữu ích khi cần đồng bộ dữ liệu, xây dựng search index, cập nhật cache, tạo data lake hoặc tích hợp hệ thống cũ. Nó giúp tránh polling bảng liên tục và có thể giữ thứ tự thay đổi theo cơ chế của nguồn.

Tuy nhiên, CDC không tự động thay thế sự kiện nghiệp vụ. Một row update có thể chỉ cho biết cột nào đã đổi; nó không nhất thiết thể hiện ý nghĩa nghiệp vụ như OrderApproved hoặc PaymentSettled. Nếu consumer cần ngữ nghĩa nghiệp vụ, hãy thiết kế domain event rõ ràng hoặc xây dựng lớp chuyển đổi phù hợp. Cũng cần hiểu snapshot ban đầu, schema evolution, delete/tombstone và khả năng xử lý lại.

### 4.7. Chỉ cần chạy định kỳ: scheduler hoặc batch

Nếu dữ liệu chỉ cần xử lý mỗi giờ, mỗi đêm hoặc theo lịch cố định, cron, scheduler, workflow engine hoặc batch job có thể đơn giản hơn Kafka.

Ví dụ, báo cáo doanh thu chạy lúc 02:00 mỗi ngày có thể đọc dữ liệu từ database hoặc data warehouse. Không cần đưa từng thay đổi nhỏ vào Kafka nếu không có nhu cầu streaming hoặc độ trễ gần thời gian thực.

Nếu tác vụ định kỳ cần phản ứng với sự kiện mới ngay khi chúng xuất hiện, có thể dùng Kafka để kích hoạt pipeline, sau đó scheduler đảm nhiệm các bước tổng hợp theo lịch. Chọn theo yêu cầu thời gian thực và độ phức tạp thật sự.

## 5. Bảng so sánh nhanh

Bảng dưới đây là hướng dẫn chọn mô hình ở mức khái quát. Tính năng cụ thể phụ thuộc phiên bản, dịch vụ được chọn và cách cấu hình.

| Nhu cầu chính | Lựa chọn thường phù hợp | Vì sao |
|---|---|---|
| Cần câu trả lời ngay | HTTP/REST hoặc gRPC | Request-response rõ ràng, timeout và phản hồi trực tiếp |
| Phân phối công việc cho worker, xác nhận từng message | RabbitMQ, SQS, Azure Service Bus | Queue semantics, acknowledgement và retry phù hợp |
| Event log bền vững, nhiều consumer group, replay | Kafka | Consumer độc lập, offset riêng và retention |
| Pub/sub nhẹ, độ trễ thấp | NATS hoặc dịch vụ pub/sub | Giao tiếp message nhẹ, ít thành phần vận hành hơn trong một số trường hợp |
| Luồng nhỏ trong hệ thống đã dùng Redis | Redis Streams | Tận dụng hạ tầng Redis và consumer group |
| Phát thay đổi từ database | CDC như Debezium | Đọc transaction log và đưa thay đổi vào pipeline |
| Lưu trạng thái, truy vấn và transaction nghiệp vụ | Database | Constraint, query và transaction phù hợp |
| Xử lý theo lịch | Scheduler hoặc batch | Đơn giản hơn khi không cần streaming liên tục |

Không có công nghệ nào thắng ở mọi tiêu chí. Một lựa chọn phù hợp cần giải quyết yêu cầu quan trọng nhất với độ phức tạp chấp nhận được.

## 6. Ma trận quyết định theo yêu cầu

Hãy đánh giá các tiêu chí sau cho từng hệ thống:

| Tiêu chí | Câu hỏi cần trả lời | Ý nghĩa với lựa chọn |
|---|---|---|
| Replay | Có cần đọc lại sự kiện sau khi consumer đã xử lý không? | Nhu cầu replay mạnh là lý do quan trọng để chọn Kafka hoặc event log tương tự |
| Fan-out | Có nhiều hệ thống tiêu thụ cùng một sự kiện với tiến độ riêng không? | Kafka và pub/sub phù hợp khi nhiều subscriber độc lập |
| Acknowledgement | Cần xác nhận từng message hay commit tiến độ theo partition? | Queue truyền thống thường tự nhiên hơn với xác nhận từng công việc |
| Ordering | Thứ tự cần bảo đảm toàn cục, theo key hay không cần? | Kafka bảo đảm thứ tự trong partition; phải thiết kế key và partition |
| Latency | Có cần phản hồi đồng bộ trong vài mili giây hoặc giây không? | HTTP/gRPC phù hợp hơn khi caller phải chờ kết quả |
| Throughput | Tải trung bình, đỉnh và kích thước payload là bao nhiêu? | Dùng số liệu đo được để thiết kế partition, broker và so sánh chi phí |
| Retention | Dữ liệu cần được giữ bao lâu và ai có quyền replay? | Kafka cần chính sách retention, dung lượng, archive và kiểm soát truy cập |
| Routing | Có nhiều quy tắc định tuyến, priority hoặc delay theo message không? | RabbitMQ hoặc queue service có thể phù hợp hơn |
| Operations | Đội ngũ có thể vận hành, giám sát và khôi phục nền tảng không? | Managed service có thể giảm gánh nặng; Kafka tự quản trị đòi hỏi năng lực cụm |
| Consistency | Thay đổi database và sự kiện phải nhất quán ra sao? | Cân nhắc outbox/CDC và idempotency thay vì chỉ gửi sự kiện sau commit |

Một cách ra quyết định thực tế là xếp hạng ba yêu cầu quan trọng nhất, sau đó xác định các yêu cầu bắt buộc. Ví dụ, nếu replay và nhiều consumer group là bắt buộc, Kafka có lợi thế. Nếu acknowledgement theo từng công việc và delayed delivery là bắt buộc, hãy ưu tiên queue chuyên dụng. Nếu cần kết quả trước khi trả HTTP response, hãy giữ request-response cho bước đó.

## 7. Cây quyết định chọn công nghệ

~~~mermaid
flowchart TD
    A["Bắt đầu: xác định kiểu giao tiếp"] --> B{"Caller cần kết quả ngay?"}
    B -->|Có| C["HTTP / REST / gRPC"]
    B -->|Không| D{"Mỗi message là một công việc<br/>cần ack riêng, routing hoặc delay?"}
    D -->|Có| E["RabbitMQ / SQS / Service Bus"]
    D -->|Không| F{"Nhiều consumer độc lập<br/>cần replay luồng dữ liệu?"}
    F -->|Có| G["Đánh giá Kafka hoặc event log tương tự"]
    F -->|Không| H{"Chỉ cần pub/sub nhẹ<br/>hoặc message độ trễ thấp?"}
    H -->|Có| I["NATS / dịch vụ pub-sub / Redis Streams"]
    H -->|Không| J{"Nguồn là thay đổi database?"}
    J -->|Có| K["CDC / Outbox, có thể đẩy vào Kafka"]
    J -->|Không| L{"Chỉ xử lý theo lịch?"}
    L -->|Có| M["Scheduler / Batch"]
    L -->|Không| N["Đánh giá database hoặc mô hình tích hợp đơn giản"]
~~~

Cây quyết định giúp thu hẹp lựa chọn, không thay thế việc kiểm chứng bằng thử nghiệm tải, kiểm thử lỗi và đánh giá chi phí vận hành.

## 8. Các tình huống thực tế

### 8.1. Nền tảng thương mại điện tử phát sự kiện đơn hàng

**Bối cảnh:** Một đơn hàng mới cần cập nhật kho, thanh toán, thông báo và phân tích.

**Lựa chọn:** Kafka phù hợp nếu các consumer cần tiến độ độc lập, có thể triển khai riêng và cần đọc lại sự kiện để phục hồi hoặc xây dựng pipeline mới.

**Thiết kế gợi ý:**

- Order Service ghi đơn hàng và bản ghi outbox trong cùng transaction database.
- Outbox relay hoặc CDC phát OrderCreated vào topic orders.
- Inventory, Payment, Notification và Analytics dùng consumer group riêng.
- Record dùng orderId làm key nếu cần giữ thứ tự sự kiện theo đơn hàng.
- Consumer xử lý idempotent để chịu được việc nhận lại record.

**Điểm cần chú ý:** Kafka không làm cho transaction database và việc gửi message tự động trở thành một transaction duy nhất. Outbox/CDC giúp tránh tình huống database commit thành công nhưng producer không phát được sự kiện. Consumer vẫn cần xử lý lặp an toàn.

### 8.2. Tạo thumbnail sau khi người dùng tải ảnh

**Bối cảnh:** Một API nhận ảnh, sau đó cần một worker tạo nhiều kích thước thumbnail. Công việc có thể retry và đưa vào dead-letter queue nếu thất bại.

**Lựa chọn:** SQS, RabbitMQ hoặc queue service thường phù hợp hơn nếu mỗi ảnh là một công việc độc lập, cần acknowledgement riêng, retry và delay. Payload nên chứa object key hoặc URL tham chiếu; không nhất thiết truyền nội dung ảnh qua message.

**Khi Kafka có thể phù hợp:** Nếu sự kiện ImageUploaded đồng thời cần được nhiều pipeline tiêu thụ, ví dụ kiểm duyệt, phân tích, lập chỉ mục và xử lý ảnh, và tổ chức muốn lưu luồng sự kiện để replay. Khi đó có thể phát event vào Kafka, còn một queue riêng phân phối công việc thumbnail nếu semantics của tác vụ yêu cầu.

### 8.3. Dịch vụ cần lấy trạng thái tồn kho để trả API

**Bối cảnh:** Checkout Service cần biết tồn kho hiện tại trước khi chấp nhận đơn hàng.

**Lựa chọn:** HTTP/gRPC tới Inventory Service hoặc đọc một read model phù hợp. Caller cần phản hồi ngay để quyết định có tiếp tục checkout hay không.

Kafka có thể giúp cập nhật read model tồn kho theo sự kiện, nhưng không nên bắt caller gửi request rồi chờ một consumer đọc Kafka và trả lời nếu một API đồng bộ giải quyết trực tiếp hơn.

### 8.4. Thu thập telemetry từ hàng nghìn thiết bị

**Bối cảnh:** Thiết bị gửi nhiệt độ, trạng thái và chỉ số theo chu kỳ. Nhiều hệ thống cần tiêu thụ dữ liệu để cảnh báo, lưu trữ, phân tích và phát hiện bất thường.

**Lựa chọn:** Kafka đáng cân nhắc khi luồng liên tục, thông lượng cao, cần nhiều consumer và replay. Cần thiết kế key theo deviceId hoặc nhóm thiết bị, số partition, retention, compression và năng lực downstream.

Nếu hệ thống nhỏ, cần message nhẹ với độ trễ rất thấp hoặc đội ngũ không muốn vận hành cụm event log, NATS hoặc dịch vụ IoT/pub-sub được quản lý có thể hợp lý hơn.

### 8.5. Đồng bộ dữ liệu từ hệ thống cũ

**Bối cảnh:** Một hệ thống cũ lưu khách hàng trong relational database. Search Service và Data Warehouse cần nhận thay đổi gần thời gian thực.

**Lựa chọn:** CDC có thể đọc transaction log, đưa thay đổi vào Kafka rồi phân phối tới các consumer. Nếu chỉ cần đồng bộ một bảng nhỏ theo lịch, batch hoặc cơ chế replication của database có thể đơn giản hơn.

**Điểm cần chú ý:** Phải xử lý snapshot ban đầu, schema thay đổi, delete, thứ tự cập nhật và khả năng consumer nhận lại record. Thay đổi row không tự động tương đương một domain event có ngữ nghĩa rõ ràng.

### 8.6. Gửi email theo lịch hoặc sau một khoảng trì hoãn

**Bối cảnh:** Người dùng yêu cầu gửi email sau 24 giờ nếu chưa hoàn tất thanh toán.

**Lựa chọn:** Scheduler, workflow engine hoặc queue hỗ trợ delayed delivery thường phù hợp hơn. Tác vụ cần thời điểm chạy, hủy hoặc cập nhật lịch và kiểm tra điều kiện trước khi thực hiện.

Có thể dùng Kafka để phát sự kiện PaymentReminderScheduled cho nhiều hệ thống, nhưng việc lập lịch chính xác và quản lý trạng thái chờ thường cần một thành phần scheduler/workflow chuyên trách.

## 9. Chi phí và trách nhiệm khi chọn Kafka

Kafka cung cấp nhiều khả năng, nhưng những khả năng đó đi kèm trách nhiệm thiết kế và vận hành. Trước khi chọn, hãy tính cả chi phí nền tảng và chi phí tổ chức.

### 9.1. Chi phí hạ tầng

Cần dự toán:

- Dung lượng log theo thông lượng ghi, kích thước record và thời gian retention.
- Số bản sao dữ liệu theo replication factor.
- CPU, RAM, disk throughput và network bandwidth.
- Số partition và số connection từ client.
- Băng thông replication giữa broker và vùng lỗi.
- Chi phí lưu trữ dài hạn hoặc archive nếu cần giữ dữ liệu lâu hơn retention online.

Ví dụ, nếu topic nhận 20 MB/s và giữ dữ liệu trong 24 giờ, dung lượng dữ liệu thô trước replication xấp xỉ 1,728 GB mỗi ngày. Với replication factor bằng 3, tổng dung lượng replica thô xấp xỉ 5,184 GB mỗi ngày, chưa tính overhead, index, khoảng trống vận hành và tăng trưởng. Đây chỉ là ước tính sơ bộ; cần dùng kích thước thực tế, compression, retention và dung lượng khả dụng để lập kế hoạch.

### 9.2. Chi phí vận hành

Một cụm Kafka tự quản trị cần có năng lực:

- Cài đặt, cấu hình và nâng cấp broker/controller.
- Thiết kế KRaft quorum, broker placement, listener và bảo mật.
- Theo dõi ISR, under-replicated partition, offline partition và consumer lag.
- Quản lý topic, partition, retention, replication và reassignment.
- Xử lý disk full, broker failure, controller quorum failure và network partition.
- Kiểm soát ACL, TLS, xác thực, schema và quyền replay.
- Kiểm thử backup, restore, disaster recovery và quy trình ứng cứu.

Dịch vụ Kafka được quản lý có thể giảm một phần việc quản trị hạ tầng, nhưng vẫn cần quản lý topic, schema, consumer, phân quyền, chi phí, capacity và chất lượng dữ liệu.

### 9.3. Chi phí phát triển và thay đổi dữ liệu

Event streaming làm producer và consumer ít phụ thuộc trực tiếp hơn, nhưng hợp đồng sự kiện trở thành một giao diện dài hạn. Cần quy định:

- Tên event và ý nghĩa nghiệp vụ.
- Key, partitioning và quy tắc ordering.
- Schema, versioning và tương thích ngược/tiến.
- Trường bắt buộc, timestamp, correlation ID và trace context.
- Chính sách retention, replay và quyền truy cập.
- Cách xử lý duplicate, poison message, retry và dead-letter.
- Cách thay đổi hoặc ngừng sử dụng một event.

Không có quản trị schema và quyền sở hữu topic, một nền tảng Kafka có thể trở thành nơi các dịch vụ phát dữ liệu không nhất quán, khó hiểu và khó thay đổi.

## 10. Những hiểu nhầm dễ dẫn tới lựa chọn sai

### “Kafka nhanh nên mọi message đều phải đi qua Kafka”

Hiệu năng chỉ là một phần của bài toán. Nếu một API cần câu trả lời ngay, HTTP/gRPC có thể rõ ràng và đơn giản hơn. Nếu một công việc cần acknowledgement riêng và delayed delivery, queue chuyên dụng có thể phù hợp hơn.

### “Kafka là queue và record sẽ biến mất khi consumer xử lý xong”

Kafka giữ record theo retention hoặc compaction. Consumer commit offset để lưu tiến độ đọc; thao tác này không xóa record khỏi topic. Các consumer group khác vẫn có thể đọc cùng dữ liệu.

### “Có thể tăng số consumer để tăng tốc bất kỳ topic nào”

Số consumer hoạt động song song trong một group bị giới hạn bởi số partition được gán. Nếu topic có ba partition, group có mười consumer thì tối đa ba consumer có partition trong cùng thời điểm theo assignment đó. Tăng partition có thể tăng song song nhưng ảnh hưởng tới thứ tự, phân bố key, metadata và chi phí vận hành.

### “Kafka bảo đảm thứ tự của mọi sự kiện”

Kafka chỉ bảo đảm thứ tự trong một partition. Muốn thứ tự theo thực thể, cần chọn key và thiết kế partitioning. Không nên tuyên bố thứ tự toàn cục khi dữ liệu nằm trên nhiều partition.

### “Kafka bảo đảm exactly-once cho toàn bộ nghiệp vụ”

Kafka hỗ trợ idempotent producer và transaction để cung cấp các bảo đảm nhất định trong luồng Kafka-to-Kafka. Khi consumer gọi API bên ngoài hoặc cập nhật database, cần thiết kế idempotency, transaction boundary, outbox/inbox hoặc cơ chế phối hợp phù hợp. Không thể mặc định mọi side effect bên ngoài được thực hiện đúng một lần chỉ nhờ cấu hình Kafka.

### “Có Kafka là không cần database”

Kafka là event log và nền tảng streaming. Database vẫn cần cho trạng thái nghiệp vụ, constraint, transaction và truy vấn. Một số kiến trúc có thể xây dựng state store từ event log, nhưng đó là quyết định thiết kế riêng, không phải lý do để loại bỏ database một cách mặc định.

### “Dùng Kafka thì không cần xử lý lỗi consumer”

Consumer vẫn có thể lỗi do dữ liệu sai, schema không tương thích, downstream ngừng hoạt động, timeout hoặc lỗi nghiệp vụ. Cần thiết kế retry có giới hạn, dead-letter, quan sát lag và cách xử lý record độc hại. Retry không kiểm soát có thể làm chậm cả partition hoặc tạo vòng lặp lỗi.

## 11. Quy trình chọn giải pháp cho một dự án Java/Spring

Khi thiết kế một luồng tích hợp mới, có thể dùng quy trình sau.

**Bước 1: Mô tả sự kiện hoặc công việc.** Ghi rõ điều gì đã xảy ra, ai phát sinh, ai cần xử lý và kết quả có cần trả về ngay hay không. Phân biệt event (sự kiện đã xảy ra) với command (yêu cầu một hành động).

**Bước 2: Xác định vòng đời dữ liệu.** Dữ liệu cần tồn tại bao lâu? Có cần replay? Ai được phép đọc lại? Có cần archive hoặc xóa theo chính sách? Một message có thể được nhiều nhóm tiêu thụ hay chỉ một worker?

**Bước 3: Đặt yêu cầu thứ tự và xác nhận.** Cần thứ tự theo orderId, accountId hay toàn hệ thống? Cần ack từng công việc, commit theo partition hay không cần xác nhận? Điều gì xảy ra khi consumer xử lý xong nhưng lỗi trước khi commit?

**Bước 4: Ước lượng tải và độ trễ.** Đo thông lượng trung bình, đỉnh, kích thước payload, số consumer, tốc độ tăng dữ liệu và thời gian phản hồi mục tiêu. Dùng dữ liệu thật hoặc thử nghiệm đại diện.

**Bước 5: Đánh giá năng lực vận hành.** Ai chịu trách nhiệm theo dõi, nâng cấp, bảo mật, backup, khôi phục và ứng cứu? Nếu không có năng lực vận hành cụm, cân nhắc managed Kafka hoặc một dịch vụ đơn giản hơn.

**Bước 6: So sánh ít nhất hai phương án.** Ví dụ Kafka với RabbitMQ; Kafka với SQS; Kafka với HTTP + outbox; hoặc Kafka với CDC. Ghi lại yêu cầu nào mỗi phương án đáp ứng, phần nào phải tự xây dựng và chi phí vận hành.

**Bước 7: Kiểm chứng bằng prototype.** Thử tải đỉnh, consumer chậm, restart, duplicate, retry, schema thay đổi, mất kết nối và phục hồi. Đừng chỉ đo throughput trong trường hợp mọi thành phần đều khỏe.

**Bước 8: Ghi lại quyết định kiến trúc.** Lưu lý do chọn, giả định, giới hạn, tiêu chí đo lường và điều kiện xem xét lại. Khi tải, số consumer hoặc yêu cầu nghiệp vụ thay đổi, quyết định có thể cần được đánh giá lại.

## 12. Ví dụ lựa chọn trong ứng dụng Spring

Giả sử một hệ thống quản lý đơn hàng cần ba luồng giao tiếp:

| Luồng | Nhu cầu | Thiết kế đề xuất |
|---|---|---|
| Checkout hỏi Inventory còn hàng không | Cần kết quả trước khi trả API | HTTP/gRPC |
| OrderCreated được kho, thanh toán và phân tích sử dụng | Nhiều consumer độc lập, cần replay | Kafka |
| Tạo hóa đơn PDF và retry khi lỗi | Một công việc, ack riêng, dead-letter | RabbitMQ hoặc queue service |

Một hệ thống thực tế có thể dùng cả ba. Điều đó không làm kiến trúc kém nhất quán; mỗi công nghệ đang phục vụ một kiểu giao tiếp khác nhau.

Nếu chọn Kafka cho OrderCreated, ứng dụng Spring có thể cấu hình producer/consumer theo các nguyên tắc sau:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.example.internal:9092
      - kafka-2.example.internal:9092
    producer:
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      group-id: inventory-service
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Đây là cấu hình minh họa, không phải cấu hình production hoàn chỉnh. Cần bổ sung xác thực, TLS, timeout, retry, serializer/deserializer, error handler, transaction nếu dùng và các thiết lập phù hợp với phiên bản Spring Kafka/Kafka client. Phía topic/broker cũng cần replication, min.insync.replicas, retention, ACL và giám sát.

Trong consumer, hãy thiết kế thao tác nghiệp vụ idempotent. Ví dụ, khi xử lý OrderCreated, Inventory Service có thể lưu eventId hoặc orderId đã xử lý trong transaction database. Nếu record được đọc lại sau restart hoặc rebalance, ứng dụng kiểm tra dấu vết xử lý để tránh giữ hàng hai lần. Cách triển khai cụ thể cần đảm bảo việc ghi dấu và cập nhật tồn kho nằm trong cùng transaction database.

## 13. Checklist trước khi quyết định dùng Kafka

Có thể xem Kafka là ứng viên mạnh khi phần lớn câu trả lời sau là “Có”:

- Nhiều ứng dụng cần tiêu thụ cùng một luồng sự kiện với tiến độ riêng.
- Cần giữ dữ liệu trong một khoảng thời gian và đọc lại khi phục hồi hoặc phát triển consumer mới.
- Luồng dữ liệu liên tục, có thông lượng hoặc khả năng mở rộng đáng kể.
- Có thể xác định partition key và phạm vi ordering rõ ràng.
- Xử lý bất đồng bộ là phù hợp với nghiệp vụ.
- Đội ngũ có khả năng vận hành Kafka hoặc có dịch vụ được quản lý phù hợp.
- Có kế hoạch cho schema, idempotency, retry, dead-letter, bảo mật và quan sát.
- Chi phí hạ tầng và vận hành tương xứng với giá trị replay, fan-out và streaming.

Hãy cân nhắc giải pháp khác nếu yêu cầu cốt lõi là phản hồi đồng bộ, queue công việc với acknowledgement/routing/delay theo từng message, xử lý định kỳ đơn giản hoặc chỉ lưu/truy vấn trạng thái hiện tại. Nếu có cả hai nhóm yêu cầu, kết hợp các công nghệ theo ranh giới nghiệp vụ thường là lựa chọn hợp lý.

## 14. Tự kiểm tra

**Câu 1.** Yếu tố nào tạo nên lợi thế nổi bật của Kafka khi nhiều dịch vụ cần cùng một sự kiện?

**Đáp án:** Nhiều consumer group có thể đọc cùng topic với offset và tiến độ độc lập. Record được giữ theo retention/compaction nên một consumer không xóa dữ liệu của consumer khác.

**Câu 2.** Vì sao Kafka thường không phải lựa chọn đầu tiên cho một API cần phản hồi ngay?

**Đáp án:** Kafka được thiết kế cho ghi và đọc luồng sự kiện bất đồng bộ. Request-response HTTP/gRPC thể hiện trực tiếp việc caller gửi yêu cầu và chờ kết quả, với timeout và phản hồi rõ ràng.

**Câu 3.** Một hệ thống cần giao từng công việc cho worker, xác nhận riêng, retry và delayed delivery. Nên đánh giá loại giải pháp nào trước?

**Đáp án:** RabbitMQ hoặc dịch vụ queue như SQS/Azure Service Bus. Chúng thường cung cấp semantics queue và các tính năng phân phối công việc phù hợp hơn.

**Câu 4.** Kafka bảo đảm thứ tự trong phạm vi nào?

**Đáp án:** Trong một partition. Muốn giữ thứ tự theo một thực thể như orderId, producer cần chọn key và partitioning phù hợp để các sự kiện liên quan đi vào cùng partition.

**Câu 5.** Consumer commit offset có làm record bị xóa khỏi topic không?

**Đáp án:** Không. Commit offset lưu tiến độ đọc của consumer group. Record được giữ hoặc loại bỏ theo retention và compaction policy của topic.

**Câu 6.** Nếu database và Kafka phải phản ánh cùng một thay đổi nghiệp vụ, vì sao nên xem xét outbox hoặc CDC?

**Đáp án:** Ghi database rồi gửi Kafka bằng hai thao tác độc lập có thể tạo khoảng hở: database commit nhưng publish thất bại, hoặc publish thành công nhưng transaction database rollback. Outbox/CDC giúp chuyển thay đổi một cách đáng tin cậy hơn; consumer vẫn cần idempotency.

**Câu 7.** Kafka có thay thế database nghiệp vụ không?

**Đáp án:** Không theo mặc định. Kafka lưu luồng sự kiện; database đảm nhiệm trạng thái, constraint, transaction và truy vấn. Chúng thường bổ trợ nhau.

---

Quyết định dùng Kafka nên bắt đầu từ nhu cầu về luồng sự kiện, replay, fan-out, ordering và năng lực vận hành. Khi những yêu cầu đó quan trọng, Kafka có thể trở thành nền tảng chung cho nhiều pipeline. Khi bài toán chỉ cần một lời gọi đồng bộ, một công việc có xác nhận riêng hoặc một lịch chạy định kỳ, giải pháp chuyên biệt thường đơn giản và dễ vận hành hơn.

