# Vai trò message broker

## Vì sao hệ thống cần message broker?

Trong một ứng dụng Spring Modulith, các module có thể giao tiếp bằng application event. Module Orders phát OrderConfirmed; module Fulfillment và Notification lắng nghe sự kiện đó để thực hiện công việc riêng. Cách tổ chức này giảm phụ thuộc trực tiếp giữa module phát và module nhận.

Khi một sự kiện cần đến ứng dụng khác hoặc một tiến trình chạy độc lập, application event trong bộ nhớ của ứng dụng không đủ. Hai ứng dụng không chia sẻ cùng ApplicationContext và có thể chạy, dừng hoặc triển khai ở các thời điểm khác nhau. Message broker cung cấp một điểm trung gian để producer gửi message và consumer nhận message qua một giao thức được hỗ trợ.

Message broker là hạ tầng nhận, lưu giữ hoặc chuyển tiếp message giữa các thành phần. Tùy sản phẩm và cấu hình, broker có thể cung cấp hàng đợi, luồng sự kiện, định tuyến, phân phối tới nhiều consumer, xác nhận nhận message và lưu trữ message trong một khoảng thời gian.

Ví dụ, khi đơn hàng được xác nhận:

~~~mermaid
flowchart LR
    O[Orders module] -->|OrderConfirmed| A[Spring Modulith externalization adapter]
    A -->|publish| B[(Message broker)]
    B --> F[Fulfillment service]
    B --> N[Notification service]
    B --> D[Data platform]
~~~

Module Orders chỉ phát ra sự kiện theo hợp đồng nghiệp vụ. Adapter chuyển sự kiện ra broker. Các consumer nhận message theo nhu cầu và nhịp xử lý riêng. Producer không cần gọi trực tiếp từng consumer hoặc biết consumer đang chạy ở máy nào.

## Những vai trò chính của message broker

### Tách producer khỏi consumer

Broker tạo ranh giới giao tiếp giữa bên gửi và bên nhận. Producer cần biết destination và hợp đồng message; nó không cần giữ kết nối trực tiếp tới từng consumer.

Điều này giúp:

- Thêm consumer mới mà không phải sửa logic nghiệp vụ của producer.
- Triển khai hoặc mở rộng consumer độc lập.
- Cho phép producer và consumer dùng các tiến trình, máy chủ hoặc công nghệ khác nhau.
- Giảm ảnh hưởng khi một consumer tạm thời không hoạt động.

Mức độ tách rời còn phụ thuộc hợp đồng message. Nếu consumer phải biết chi tiết class nội bộ, package Java hoặc cấu trúc database của producer, hai bên vẫn bị phụ thuộc dù đã dùng broker. Event đưa ra ngoài nên thể hiện dữ liệu nghiệp vụ ổn định, có phiên bản và không mang theo object persistence nội bộ.

### Đệm tải và hấp thụ chênh lệch tốc độ

Producer và consumer thường có tốc độ xử lý khác nhau. Broker có thể giữ message trong lúc consumer bận, giúp producer tiếp tục công việc trong giới hạn dung lượng và chính sách của broker.

Ví dụ, Orders có thể phát nhiều OrderConfirmed trong một đợt khuyến mại, trong khi Fulfillment chỉ xử lý được một lượng đơn hàng nhất định mỗi giây. Queue hoặc log của broker giữ lại phần message chưa được tiêu thụ để consumer xử lý dần.

Broker không tạo năng lực xử lý vô hạn. Khi tốc độ phát liên tục cao hơn tốc độ tiêu thụ, backlog tăng và có thể chạm giới hạn dung lượng, retention hoặc quota. Hệ thống cần theo dõi độ trễ, lượng message chờ và khả năng mở rộng consumer.

### Phân phối một sự kiện tới nhiều hệ thống

Một sự kiện nghiệp vụ có thể hữu ích cho nhiều mục đích. OrderConfirmed có thể được Fulfillment dùng để chuẩn bị giao hàng, Notification dùng để gửi email, còn Data Platform dùng để cập nhật mô hình phân tích.

Broker hỗ trợ mô hình publish/subscribe hoặc các cơ chế subscription tương đương. Mỗi consumer độc lập có thể nhận bản sao message theo cấu hình của broker. Với queue cạnh tranh, nhiều instance của cùng một consumer có thể chia nhau xử lý message để tăng throughput.

Cần phân biệt hai nhu cầu:

- Nhiều instance cùng một consumer chia tải: chúng thường thuộc cùng consumer group hoặc cùng queue.
- Nhiều hệ thống độc lập đều cần nhận mọi message: mỗi hệ thống cần subscription, queue hoặc consumer group riêng theo semantics của broker.

Nếu các hệ thống độc lập dùng chung một queue cạnh tranh, một message thường chỉ được giao cho một consumer trong nhóm, thay vì được phát riêng cho tất cả hệ thống.

### Định tuyến message

Broker có thể định tuyến message theo destination, routing key, binding, topic hoặc subscription. Nhờ vậy, producer có thể công bố message vào một luồng logic; broker quyết định queue hoặc consumer nào nhận được message dựa trên cấu hình.

Ví dụ với RabbitMQ, exchange nhận message và routing key rồi so khớp với binding để chọn queue. Với Kafka, producer gửi message tới topic và message key có thể được dùng để chọn partition.

Định tuyến giúp phân nhóm message, nhưng không thay thế việc thiết kế hợp đồng event. Consumer vẫn phải kiểm tra event type, phiên bản payload và điều kiện nghiệp vụ trước khi xử lý.

### Lưu giữ message và hỗ trợ phục hồi

Một số broker lưu message bền vững để consumer có thể tiếp tục sau khi khởi động lại hoặc để consumer mới đọc lại dữ liệu trong giới hạn retention. Cơ chế này khác nhau giữa queue broker và log-based broker.

Khả năng phục hồi phụ thuộc cấu hình cụ thể như:

- Message có được ghi xuống storage bền vững không.
- Queue hoặc topic có replication và chính sách xác nhận phù hợp không.
- Broker xác nhận producer ở thời điểm nào.
- Message được giữ đến khi consumer acknowledge hay hết thời gian retention.
- Consumer offset hoặc trạng thái acknowledgement được lưu ra sao.

Không nên mặc định rằng message đã được gửi đến broker thì chắc chắn tồn tại vĩnh viễn. Durability là kết quả của loại broker, cấu hình, replication, storage và quy trình vận hành.

## Broker khác application event và Event Publication Registry thế nào?

Ba thành phần này nằm ở các ranh giới khác nhau:

| Thành phần | Vai trò | Phạm vi |
|---|---|---|
| Application event | Biểu diễn một sự kiện trong ứng dụng | Giao tiếp giữa các thành phần trong ApplicationContext |
| Event Publication Registry | Ghi nhận publication cần được xử lý và trạng thái hoàn tất của listener được theo dõi | Theo dõi vòng đời publication trong ứng dụng |
| Message broker | Nhận, lưu giữ, định tuyến và chuyển message giữa các tiến trình | Giao tiếp qua hạ tầng messaging |

Spring Modulith cung cấp Event Publication Registry để theo dõi việc xử lý application event của các listener được quản lý. Với cấu hình persistence phù hợp, publication có thể được lưu bền vững và phục hồi khi ứng dụng khởi động lại.

Khi event được đánh dấu để externalize, cơ chế externalization cùng adapter tương ứng chuyển event ra broker. Registry giúp ứng dụng theo dõi bước publication trong vòng đời listener; broker quản lý message sau khi nhận theo semantics riêng của nó.

Có thể nhìn độ tin cậy thành hai chặng:

1. **Ứng dụng đến broker:** ứng dụng cần ghi nhận publication, gửi message và xử lý lỗi nếu broker chưa nhận thành công. Event Publication Registry hỗ trợ theo dõi publication của listener externalization.
2. **Broker đến consumer:** broker giao message cho consumer và quản lý acknowledgement, offset hoặc trạng thái message theo cơ chế của broker. Consumer phải xử lý thành công và xác nhận theo đúng semantics.

Một chặng thành công không tự động chứng minh chặng còn lại đã hoàn tất. Ví dụ, broker đã nhận message không có nghĩa Fulfillment đã xử lý xong; consumer đã xử lý message cũng không có nghĩa một dịch vụ downstream mà consumer gọi đã hoàn tất mọi tác động bên ngoài.

## Vai trò của adapter trong Spring Modulith

Adapter là lớp kết nối giữa mô hình application event của Spring Modulith và API messaging của broker. Nó chuyển đổi thông tin sự kiện sang dạng message mà integration có thể gửi, đồng thời áp dụng các quy tắc target, routing key, header và serialization mà cấu hình hỗ trợ.

Luồng khái niệm:

~~~mermaid
sequenceDiagram
    participant S as Spring Modulith
    participant R as Event Publication Registry
    participant A as Broker adapter
    participant B as Message broker
    participant C as Consumer

    S->>R: Ghi nhận publication trong transaction
    R->>A: Externalize event
    A->>B: Gửi message và metadata
    B-->>A: Xác nhận theo giao thức
    A-->>R: Hoàn tất bước externalization
    B->>C: Giao message
    C->>C: Xử lý nghiệp vụ
    C-->>B: Acknowledge hoặc commit offset
~~~

Sơ đồ mô tả các trách nhiệm ở mức khái niệm. Thời điểm và cách cập nhật publication phụ thuộc adapter, transaction và phiên bản Spring Modulith đang sử dụng.

Một adapter thường phải giải quyết các việc sau:

- Chọn event nào được externalize.
- Xác định target và routing metadata.
- Chuyển event thành message payload.
- Gắn header như event type, content type hoặc correlation metadata nếu integration hỗ trợ.
- Gọi API producer của broker.
- Chuyển lỗi gửi message thành trạng thái lỗi có thể quan sát và xử lý lại.
- Phối hợp với publication registry để hoàn tất hoặc giữ lại publication theo kết quả gửi.

Không nên tự giả định mọi adapter đều hỗ trợ cùng một header, serializer, routing option hoặc delivery guarantee. Hãy kiểm tra integration module và phiên bản cụ thể mà ứng dụng đang dùng.

## Chọn loại broker theo nhu cầu giao tiếp

Không có một broker phù hợp cho mọi trường hợp. Hãy bắt đầu từ mô hình xử lý và yêu cầu vận hành.

| Nhu cầu | Kiểu giải pháp thường phù hợp | Điểm cần cân nhắc |
|---|---|---|
| Công việc cần được một worker trong nhóm lấy xử lý | Queue-based messaging | Acknowledgement, retry, dead-letter và độ dài queue |
| Phát luồng sự kiện có thể đọc lại trong thời gian retention | Distributed event log | Partition, offset, retention, replication và consumer lag |
| Định tuyến linh hoạt tới nhiều queue theo key hoặc pattern | Exchange-based messaging | Exchange type, routing key, binding và topology |
| Tích hợp qua chuẩn messaging doanh nghiệp | JMS provider | Broker provider, transaction và semantics của destination |

Ví dụ:

- Kafka thường được dùng như một distributed event log, phù hợp với luồng sự kiện có nhiều consumer độc lập, khả năng đọc lại và xử lý theo partition.
- RabbitMQ thường được dùng cho queue và exchange-based routing, phù hợp với công việc cần định tuyến tới queue, acknowledgement và các kiểu trao đổi message.
- Một JMS provider có thể phù hợp với hệ thống đã chuẩn hóa trên JMS API và cần tích hợp với hạ tầng messaging tương ứng.

Đây là các đặc điểm khái quát. Cấu hình, phiên bản, plugin, topology và yêu cầu vận hành có thể làm thay đổi lựa chọn phù hợp.

## Delivery semantics: at-most-once, at-least-once và exactly-once

Broker và adapter cần có chính sách giao message rõ ràng.

- **At-most-once:** message có thể bị mất nhưng không được giao lại theo chính sách đó. Phù hợp với dữ liệu có thể bỏ qua hoặc hệ thống chấp nhận mất message.
- **At-least-once:** message được giao lại cho đến khi đạt điều kiện xác nhận hoặc chính sách retry kết thúc. Consumer có thể nhận trùng và phải idempotent.
- **Exactly-once:** một số broker cung cấp bảo đảm exactly-once trong phạm vi giao thức, transaction hoặc luồng xử lý được hỗ trợ. Bảo đảm đó không tự mở rộng sang mọi database và API bên ngoài mà consumer gọi.

Trong hệ thống nghiệp vụ, at-least-once cùng consumer idempotent thường là cách tiếp cận thực tế. Consumer có thể lưu event ID đã xử lý trong cùng transaction với thay đổi nghiệp vụ. Với API bên ngoài, truyền idempotency key nếu hệ thống đích hỗ trợ.

Không nên chỉ dựa vào việc broker có producer idempotence hoặc transaction để tuyên bố toàn bộ nghiệp vụ là exactly-once. Nếu consumer cập nhật database rồi gọi API thanh toán, broker không thể tự tạo transaction nguyên tử bao trùm cả hai hệ thống.

## Acknowledgement, retry và dead-letter

Broker cần biết message đã được consumer xử lý hay chưa. Tùy giao thức:

- Queue-based broker thường dùng acknowledgement để xác nhận message đã xử lý.
- Kafka consumer thường commit offset để ghi nhận vị trí đã xử lý.
- Một số hệ thống hỗ trợ negative acknowledgement, visibility timeout hoặc redelivery.

Khi consumer lỗi tạm thời, message có thể được thử lại. Retry nên có backoff và giới hạn phù hợp để tránh một message lỗi chiếm hết tài nguyên. Khi lỗi không thể tự phục hồi, dead-letter queue hoặc cơ chế quarantine giúp giữ message để điều tra.

| Tình huống | Cách xử lý nên cân nhắc |
|---|---|
| Broker tạm thời không sẵn sàng | Retry gửi từ phía publisher/adapter |
| Consumer tạm thời lỗi | Redelivery hoặc retry có backoff |
| Payload không deserialize được | Quarantine/dead-letter và điều tra schema |
| Dữ liệu nghiệp vụ không hợp lệ | Đưa vào luồng xử lý lỗi có kiểm soát |
| Message bị giao trùng | Consumer idempotency |
| Consumer xử lý quá chậm | Tăng năng lực consumer hoặc điều chỉnh partition/queue theo giới hạn |

Retry không thay thế xử lý lỗi. Cần lưu nguyên nhân, correlation ID, event ID và số lần thử để đội vận hành biết vì sao message bị giữ hoặc chuyển sang dead-letter.

## Ordering và partition

Thứ tự xử lý là thuộc tính có phạm vi. Kafka thường duy trì thứ tự trong một partition; message key giúp các event cùng aggregate đi cùng partition theo partitioner. Không có thứ tự toàn cục giữa mọi partition.

RabbitMQ có thể duy trì thứ tự enqueue/delivery trong các điều kiện nhất định, nhưng nhiều consumer, redelivery, priority hoặc topology phức tạp có thể làm thứ tự quan sát ở phía ứng dụng khác đi. Không nên coi thứ tự message là bảo đảm nghiệp vụ nếu chưa xác định rõ broker và cấu hình.

Nếu các event của cùng aggregate phải được xử lý tuần tự:

1. Dùng aggregate ID làm key nếu broker hỗ trợ partition theo key.
2. Giữ các event của aggregate trên cùng partition hoặc queue phù hợp.
3. Tránh xử lý song song nhiều event cùng aggregate nếu nghiệp vụ không cho phép.
4. Xử lý redelivery và event đến trễ.
5. Dùng version hoặc sequence của aggregate để phát hiện event cũ hoặc thiếu thứ tự.

Nếu nghiệp vụ không cần thứ tự toàn cục, đừng ép mọi message vào một partition hoặc một consumer đơn lẻ vì điều đó giới hạn throughput.

## Backpressure và kiểm soát backlog

Broker giúp hấp thụ chênh lệch tốc độ trong giới hạn tài nguyên. Backpressure là cách hệ thống phản ứng khi consumer không theo kịp producer.

Các dấu hiệu cần theo dõi:

- Queue depth hoặc số record chưa tiêu thụ.
- Consumer lag theo partition hoặc subscription.
- Tuổi của message cũ nhất.
- Tốc độ publish so với tốc độ xử lý.
- Số lần redelivery và dead-letter.
- Dung lượng storage và tỷ lệ sử dụng quota.

Khi backlog tăng, có thể tăng số consumer nếu broker và nghiệp vụ cho phép, tối ưu thời gian xử lý, tăng partition trong kế hoạch có kiểm soát hoặc giảm tốc độ producer. Tăng consumer không luôn giúp ích: với Kafka, số consumer hữu ích trong một group bị giới hạn bởi số partition; với queue broker, consumer quá nhiều có thể gây tranh chấp tài nguyên hoặc làm hệ thống downstream quá tải.

Nếu consumer gọi database hoặc API có giới hạn tải, cần đặt concurrency, batch size và prefetch phù hợp. Broker chỉ chuyển áp lực sang hàng đợi; nó không loại bỏ giới hạn của hệ thống đích.

## Serialization và hợp đồng message

Message phải có định dạng mà consumer có thể đọc độc lập với mã nguồn producer. Không nên gửi object Java nội bộ với giả định mọi consumer dùng cùng classpath hoặc cùng phiên bản ứng dụng.

Một hợp đồng message thường cần:

- Event type ổn định.
- Schema hoặc phiên bản payload.
- Event ID và thời điểm phát.
- Aggregate ID hoặc correlation metadata nếu cần.
- Content type và encoding.
- Quy tắc tương thích khi thêm, đổi hoặc bỏ field.

Ưu tiên schema rõ ràng và serialization có kiểm soát. Nếu dùng JSON, hãy xác định cách biểu diễn ngày giờ, số thập phân, enum và trường nullable. Nếu dùng schema registry hoặc định dạng nhị phân, cần quy trình quản lý schema và tương thích consumer.

Không đưa entity ORM, lazy proxy hoặc toàn bộ object graph vào payload. Event nên là hợp đồng dữ liệu có chủ đích, đủ cho consumer thực hiện công việc của mình và tránh phụ thuộc cấu trúc lưu trữ của producer.

## Bảo mật khi kết nối broker

Broker thường là điểm giao tiếp giữa nhiều ứng dụng và miền nghiệp vụ. Cấu hình bảo mật cần bao phủ cả kết nối lẫn quyền trên destination.

- Dùng TLS khi kết nối qua mạng không tin cậy hoặc theo chính sách hạ tầng.
- Dùng thông tin xác thực từ secret management, không commit credential vào repository.
- Cấp quyền publish và subscribe theo nguyên tắc tối thiểu.
- Tách destination theo môi trường và giới hạn quyền giữa môi trường.
- Tránh đưa dữ liệu nhạy cảm vào routing key, header hoặc log.
- Có chính sách xoay vòng credential và thu hồi quyền khi ứng dụng ngừng sử dụng.

Nếu nhiều ứng dụng cùng dùng một broker, phân quyền theo topic, exchange, queue hoặc namespace giúp giảm nguy cơ một producer gửi nhầm luồng dữ liệu của hệ thống khác.

## Kiểm thử broker và adapter

Kiểm thử nên chia theo trách nhiệm để dễ xác định lỗi:

| Cấp kiểm thử | Nội dung |
|---|---|
| Unit test publisher | Nghiệp vụ phát đúng event với payload mong đợi |
| Unit test mapping | Target, routing key và metadata được tính đúng |
| Test publication registry | Publication được ghi nhận, hoàn tất hoặc giữ lại theo kết quả listener |
| Adapter integration test | Adapter gửi message đúng destination và serialization |
| Broker integration test | Routing, partition, acknowledgement và redelivery hoạt động như cấu hình |
| Consumer test | Consumer xử lý payload, duplicate và lỗi một cách an toàn |
| Contract test | Producer và consumer tương thích với schema đã công bố |

Có thể dùng broker container hoặc môi trường test chuyên dụng để kiểm tra hành vi thực tế. Test chỉ mock producer không chứng minh message đã được broker nhận, route tới đúng queue hoặc có thể đọc lại sau restart.

Với test bất đồng bộ, chờ điều kiện hoàn tất bằng cơ chế có giới hạn thời gian thay vì sleep cố định. Dọn queue, topic hoặc consumer group test sau khi chạy để các lần test độc lập.

## Quan sát từ ứng dụng tới broker và consumer

Cần nối được dấu vết từ lúc nghiệp vụ phát event đến lúc consumer xử lý. Các trường hữu ích gồm:

- Event ID và event type.
- Target logic và destination vật lý.
- Routing key hoặc message key ở dạng an toàn.
- Correlation ID và trace ID.
- Thời điểm publish, broker acknowledgement và consumer processing.
- Publication còn pending, retry hoặc lỗi trong Event Publication Registry.
- Queue depth, consumer lag, redelivery và dead-letter count ở broker.

Đặt tên metric theo hệ thống quan sát đang dùng và tránh tạo metric label có cardinality không giới hạn như event ID hoặc order ID. Những giá trị này phù hợp hơn trong log hoặc trace.

Khi event không tới consumer, lần theo từng chặng: publisher có phát event không; registry có ghi nhận publication không; adapter có gửi thành công không; broker có nhận và route message không; consumer có subscription đúng không; consumer có acknowledge hoặc commit offset không.

## Quy trình thiết kế tích hợp qua broker

Khi đưa một event của Spring Modulith ra hệ thống khác, hãy xác định:

1. Event có thực sự cần đi qua ranh giới tiến trình hay có thể xử lý nội bộ?
2. Hệ thống consumer cần queue công việc hay cần một luồng sự kiện có thể đọc lại?
3. Broker destination, target và routing key được đặt tên theo hợp đồng nào?
4. Adapter nào phù hợp với broker và phiên bản Spring Modulith đang dùng?
5. Event Publication Registry được cấu hình persistence và transaction ra sao?
6. Delivery semantics, acknowledgement, retry và dead-letter được thiết kế thế nào?
7. Consumer có idempotent và có xử lý thứ tự theo aggregate không?
8. Schema, bảo mật, retention, quota và quan sát được quản lý ra sao?

Message broker tạo một ranh giới giao tiếp linh hoạt giữa các ứng dụng. Khi kết hợp hợp đồng event ổn định, adapter phù hợp, publication registry, chính sách giao nhận và consumer idempotent, hệ thống có thể mở rộng giao tiếp mà vẫn kiểm soát được lỗi, tải và vòng đời message.

## Tài liệu tham khảo

- Spring Modulith Reference — Working with Application Events, phần Event Externalization: https://docs.spring.io/spring-modulith/reference/events.html
- Apache Kafka Documentation — Introduction: https://kafka.apache.org/documentation/
- RabbitMQ Documentation — AMQP Concepts: https://www.rabbitmq.com/tutorials/amqp-concepts
