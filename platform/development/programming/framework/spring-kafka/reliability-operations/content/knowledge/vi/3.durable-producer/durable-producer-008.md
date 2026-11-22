# max.in.flight.requests.per.connection

Trong Kafka producer, **max.in.flight.requests.per.connection** giới hạn số request đã được gửi đến một broker nhưng vẫn chưa nhận response trên cùng một kết nối mạng. Thuộc tính này quyết định mức độ producer có thể gửi request nối tiếp mà không phải chờ từng acknowledgement. Nó ảnh hưởng trực tiếp đến khả năng tận dụng network round trip, throughput, độ trễ, và thứ tự record khi producer phải retry.

Với Spring Kafka, đây là thuộc tính của Apache Kafka producer bên dưới **KafkaTemplate**. Spring Kafka không thay đổi ý nghĩa của nó: ứng dụng gọi **KafkaTemplate.send()**, producer gom record thành batch và gửi ProduceRequest đến broker. Giới hạn in-flight được áp dụng ở tầng kết nối giữa producer và từng broker.

## 1. In-flight request là gì?

Một request trở thành in-flight khi producer đã gửi request qua kết nối đến broker và đang chờ response. Khi broker phản hồi, request đó không còn chiếm một vị trí in-flight. Nếu giới hạn là 5, producer có thể có tối đa năm request chưa được xác nhận trên một kết nối broker tại cùng thời điểm.

Ví dụ với giá trị bằng 1:

~~~text
Producer                         Broker
   |                               |
   |------ Request A ------------->|
   |                               |
   |       chờ response            |
   |<----- Response A -------------|
   |                               |
   |------ Request B ------------->|
   |                               |
   |       chờ response            |
   |<----- Response B -------------|
~~~

Producer chỉ gửi request tiếp theo trên kết nối đó sau khi request đang chờ nhận response. Cách này tạo luồng gửi tuần tự, nhưng mỗi request phải chịu một vòng chờ mạng trước khi request sau được gửi.

Với giá trị bằng 5:

~~~text
Producer                         Broker
   |                               |
   |------ Request A ------------->|
   |------ Request B ------------->|
   |------ Request C ------------->|
   |------ Request D ------------->|
   |------ Request E ------------->|
   |                               |
   |<----- Response B -------------|
   |<----- Response A -------------|
   |<----- Response D -------------|
   |<----- Response C -------------|
   |<----- Response E -------------|
~~~

Producer có thể gửi nhiều request trước khi nhận response của request đầu tiên. Các response có thể đến ở thời điểm khác nhau. Pipelining này giúp producer tận dụng thời gian mạng và broker đang xử lý request, đặc biệt khi độ trễ giữa ứng dụng và broker cao.

Giới hạn được tính riêng cho mỗi kết nối đến broker. Nó không phải một giới hạn tổng số request của toàn cluster. Nếu producer có kết nối đến nhiều broker, mỗi kết nối có giới hạn riêng. Nó cũng không phải số record, số partition hay số lần gọi **KafkaTemplate.send()** được phép chạy đồng thời.

Một ProduceRequest có thể chứa batch của một hoặc nhiều partition do broker đó làm leader. Vì vậy, một in-flight request không tương đương một record. Một lời gọi **send()** cũng không nhất thiết tạo ngay một request riêng: producer có thể đợi gom nhiều record vào batch trước khi gửi.

## 2. Thuộc tính này phối hợp với batching như thế nào?

Kafka producer có nhiều cơ chế điều khiển việc gửi dữ liệu. Cần phân biệt **max.in.flight.requests.per.connection** với các thuộc tính gom batch:

| Thuộc tính | Điều khiển | Tác động chính |
|---|---|---|
| **batch.size** | Kích thước mục tiêu của batch cho mỗi partition | Batch lớn có thể tăng hiệu quả nén và throughput, nhưng có thể cần thêm thời gian hoặc bộ nhớ để lấp đầy. |
| **linger.ms** | Thời gian producer chờ thêm record trước khi gửi batch | Tăng cơ hội gom batch, đổi lại thêm một phần độ trễ. |
| **buffer.memory** | Bộ nhớ producer dùng để giữ record đang chờ gửi | Quyết định sức chứa của các batch đang chờ. |
| **max.in.flight.requests.per.connection** | Số request đã gửi nhưng chưa nhận response trên mỗi kết nối broker | Điều khiển mức pipelining của các request trên mạng. |

**batch.size** và **linger.ms** quyết định khi nào producer có đủ dữ liệu để tạo request. **max.in.flight.requests.per.connection** quyết định có thể gửi bao nhiêu request mà chưa cần chờ phản hồi của broker.

Do đó, tăng **max.in.flight.requests.per.connection** không tự làm batch lớn hơn. Nếu batch nhỏ, producer có thể gửi nhiều request nhỏ hơn. Ngược lại, batch lớn không có nghĩa producer chỉ có một request đang chờ.

**KafkaTemplate.send()** là API bất đồng bộ, nhưng điều đó không có nghĩa mọi lần gọi **send()** đều tương ứng với một request mạng độc lập đang bay. Các record được giữ trong accumulator, phân batch theo partition và gửi đến broker theo lịch của producer.

Khi số request in-flight đạt giới hạn, sender phải chờ response giải phóng một vị trí trước khi gửi thêm request trên kết nối đó. Trong thời gian chờ, các batch tiếp tục nằm trong producer. Nếu ứng dụng tạo dữ liệu nhanh hơn khả năng broker tiếp nhận, buffer có thể tăng dần; khi bộ nhớ producer cạn, lời gọi **send()** có thể phải chờ cấp phát buffer và cuối cùng timeout theo **max.block.ms**.

## 3. Vì sao giới hạn in-flight có thể ảnh hưởng đến thứ tự?

Kafka giữ thứ tự record trong từng partition. Tuy nhiên, khi producer cho phép nhiều request cùng in-flight và phải retry, thứ tự append vào log có thể thay đổi nếu idempotence không được bật.

Giả sử producer gửi hai batch liên tiếp cho cùng một partition:

1. Request A chứa batch A được gửi đến broker.
2. Request B chứa batch B được gửi trước khi producer nhận response của A.
3. Broker xử lý B thành công, nhưng request A gặp lỗi tạm thời và cần retry.
4. Nếu producer không dùng idempotence, lần retry A có thể đến broker sau khi B đã được ghi.
5. Log của partition có thể chứa B trước A, dù ứng dụng gửi A trước B.

Minh họa:

~~~text
Thứ tự ứng dụng:       A  ->  B

Lần gửi ban đầu:       A  ->  B
Phản hồi:              A lỗi, B thành công
Retry khi không
có idempotence:        B  ->  A (retry)

Thứ tự có thể thấy
trong partition:       B  ->  A
~~~

Đây là lý do tài liệu Kafka cảnh báo rằng khi retry được bật và **max.in.flight.requests.per.connection** lớn hơn 1, record có thể bị sắp xếp lại nếu idempotence tắt.

Đặt giá trị bằng 1 giới hạn một request chưa được xác nhận trên mỗi kết nối. Khi request A cần retry, request B chưa được gửi trên kết nối đó; producer phải xử lý A trước khi có thể gửi request tiếp theo. Cách này tránh kiểu đảo thứ tự do nhiều request đang bay cùng lúc, nhưng có thể giảm đáng kể throughput.

Giới hạn này không tạo ra thứ tự toàn cục:

- Kafka chỉ giữ thứ tự trong một partition.
- Hai partition khác nhau không có thứ tự chung được bảo đảm.
- Hai producer độc lập có thể ghi vào cùng partition; thuộc tính của một producer không điều phối thứ tự giữa các producer.
- Nếu ứng dụng tự gọi **send()** lại để phát một event nghiệp vụ lần thứ hai, đó là lần gửi mới và không được xem là retry nội bộ của cùng request.

Nếu thứ tự nghiệp vụ quan trọng, hãy dùng key ổn định, chẳng hạn **orderId**, để các record của cùng một đơn hàng đi vào cùng partition. Sau đó cấu hình idempotence để retry của producer không làm đảo thứ tự các batch trong phạm vi producer đó.

## 4. Idempotent producer cho phép pipelining mà vẫn giữ thứ tự

Idempotent producer giải quyết rủi ro bản sao và sắp xếp lại do retry nội bộ của producer. Kafka cấp producer ID và dùng sequence number cho các batch theo từng partition. Broker dựa trên thông tin này để nhận diện batch lặp và kiểm soát thứ tự sequence.

Khi một request bị mất response, producer có thể gửi lại batch với cùng thông tin sequence. Broker nhận diện đây là lần retry của batch trước, thay vì ghi thêm một bản sao như một batch mới. Sequence number cũng giúp broker phát hiện batch đến sai thứ tự.

Khi idempotence được bật, Kafka cho phép tối đa năm request in-flight trên mỗi kết nối:

~~~properties
enable.idempotence=true
max.in.flight.requests.per.connection=5
acks=all
~~~

Với cấu hình tương thích này, producer có thể giữ nhiều request đang chờ để đạt throughput tốt hơn mà vẫn duy trì thứ tự trong partition khi retry. Không cần đặt **max.in.flight.requests.per.connection=1** chỉ để bảo vệ thứ tự nếu producer đang dùng idempotence và client hỗ trợ cấu hình này.

Khi idempotence bật, các điều kiện cấu hình quan trọng gồm:

- **acks=all**.
- **retries** lớn hơn 0; nên để producer retry trong giới hạn **delivery.timeout.ms**.
- **max.in.flight.requests.per.connection** không lớn hơn 5.

Nếu bật idempotence tường minh nhưng cấu hình các thuộc tính không tương thích, Kafka producer có thể từ chối khởi tạo bằng lỗi cấu hình. Hãy kiểm tra log khởi tạo producer thay vì cho rằng client tự điều chỉnh mọi giá trị.

Trong các Kafka client hiện đại, idempotence thường được bật mặc định. Tuy nhiên, hành vi mặc định phụ thuộc phiên bản client và có thể bị thay đổi bởi các thuộc tính cấu hình khác. Nên đặt **enable.idempotence=true** tường minh cho producer cần độ tin cậy và kiểm tra phiên bản Kafka client mà Spring Kafka thực sự sử dụng.

### Idempotence không giải quyết mọi trường hợp gửi trùng

Idempotence bảo vệ retry nội bộ của cùng producer session. Nó không tự nhận diện hai lần gửi độc lập có cùng nội dung hoặc cùng event ID.

Ví dụ, ứng dụng xử lý một HTTP request hai lần và gọi **KafkaTemplate.send()** hai lần. Hai lần gọi đó có thể tạo hai record hợp lệ trong Kafka, kể cả khi idempotence đang bật. Tương tự, nếu ứng dụng tự gửi lại record sau khi future báo lỗi không rõ kết quả, lần gọi mới có thể tạo một record khác.

Đối với chống trùng ở cấp nghiệp vụ, hãy tạo event ID ổn định, lưu trạng thái phát event bền vững khi cần, và thiết kế consumer idempotent. Idempotence của producer và idempotency của nghiệp vụ giải quyết hai lớp vấn đề khác nhau.

## 5. Giá trị mặc định và giới hạn

Kafka producer thường có giá trị mặc định:

~~~properties
max.in.flight.requests.per.connection=5
~~~

Giá trị hợp lệ phải là số nguyên dương. Khi idempotence bật, giá trị tối đa được hỗ trợ là 5. Với idempotence tắt, client có thể cho phép giá trị lớn hơn, nhưng retry khi có nhiều request in-flight có thể làm thay đổi thứ tự record.

| Giá trị | Hành vi | Khi cân nhắc |
|---|---|---|
| **1** | Mỗi kết nối chỉ có một request chưa được xác nhận | Cần tuần tự hóa request trên kết nối và chấp nhận giảm throughput; thường là lựa chọn khi không dùng idempotence nhưng vẫn cần tránh đảo thứ tự do retry. |
| **2 đến 4** | Cho phép một lượng pipelining vừa phải | Có thể thử nghiệm khi muốn cân bằng giữa số request đang chờ và khả năng sử dụng mạng. |
| **5** | Cho phép đến năm request in-flight trên mỗi kết nối | Giá trị phổ biến, tương thích với idempotent producer và thường là điểm bắt đầu hợp lý. |
| **Lớn hơn 5** | Có thể được chấp nhận khi idempotence tắt | Không dùng với idempotence; cần hiểu rõ rủi ro thứ tự khi retry và chỉ cân nhắc sau khi đo tải. |

Không nên hạ xuống 1 theo thói quen. Nếu producer đã bật idempotence, giá trị 5 vừa cho phép pipelining vừa giữ thứ tự trong phạm vi bảo đảm của Kafka producer. Đặt 1 có thể làm mỗi broker connection phải chờ một vòng response trước khi gửi request tiếp theo, khiến độ trễ mạng chi phối throughput.

Ngược lại, cũng không nên tăng giá trị tùy tiện. Nếu idempotence bật, cấu hình lớn hơn 5 không tương thích. Nếu idempotence tắt, nhiều request in-flight cộng với retry có thể làm record đảo thứ tự trong partition.

## 6. Cấu hình trong Spring Boot và Spring Kafka

**max.in.flight.requests.per.connection** là Kafka client property. Spring Boot chuyển các property bổ sung trong **spring.kafka.producer.properties** xuống producer của Apache Kafka.

Ví dụ trong **application.yml**:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      retries: 2147483647
      properties:
        "[enable.idempotence]": true
        "[max.in.flight.requests.per.connection]": 5
        "[delivery.timeout.ms]": 120000
        "[request.timeout.ms]": 30000
~~~

Các key có dấu ngoặc vuông giúp Spring Boot giữ nguyên tên property Kafka có dấu chấm khi bind vào map. Có thể khai báo tương đương trong **application.properties**:

~~~properties
spring.kafka.producer.acks=all
spring.kafka.producer.retries=2147483647
spring.kafka.producer.properties[enable.idempotence]=true
spring.kafka.producer.properties[max.in.flight.requests.per.connection]=5
spring.kafka.producer.properties[delivery.timeout.ms]=120000
spring.kafka.producer.properties[request.timeout.ms]=30000
~~~

Ý nghĩa của cấu hình:

- **acks=all**: chờ acknowledgement từ các replica hiện thuộc ISR.
- **enable.idempotence=true**: chống bản sao phát sinh do retry nội bộ của producer và bảo vệ thứ tự batch trong giới hạn được hỗ trợ.
- **max.in.flight.requests.per.connection=5**: cho phép tối đa năm request chưa nhận response trên mỗi kết nối broker.
- **retries**: cho phép producer thử lại các lỗi có thể retry; **delivery.timeout.ms** vẫn giới hạn tổng thời gian giao record.
- **request.timeout.ms**: giới hạn thời gian chờ response của một request.
- **delivery.timeout.ms**: giới hạn tổng thời gian producer cố gắng giao record, bao gồm chờ gom batch, request và retry.

Các giá trị timeout trong ví dụ chỉ là điểm khởi đầu. Cần điều chỉnh theo độ trễ mạng, thời gian phục hồi broker và SLO của hệ thống. **max.in.flight.requests.per.connection** không thay thế timeout và cũng không quyết định producer sẽ retry trong bao lâu.

Nếu tạo producer bằng Java configuration thay vì Spring Boot auto-configuration, có thể truyền trực tiếp property của Kafka client:

~~~java
Map<String, Object> producerProps = new HashMap<>();
producerProps.put(
        ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
        "localhost:9092");
producerProps.put(
        ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG,
        true);
producerProps.put(
        ProducerConfig.MAX_IN_FLIGHT_REQUESTS_PER_CONNECTION,
        5);
producerProps.put(
        ProducerConfig.ACKS_CONFIG,
        "all");

ProducerFactory<String, String> producerFactory =
        new DefaultKafkaProducerFactory<>(producerProps);

KafkaTemplate<String, String> kafkaTemplate =
        new KafkaTemplate<>(producerFactory);
~~~

Đoạn mã minh họa cách đặt thuộc tính cho producer factory. Trong ứng dụng thực tế, cần bổ sung serializer, bootstrap servers, bảo mật và các property phù hợp với môi trường.

### Khi producer dùng transaction

Transactional producer của Kafka cũng dựa trên idempotence. Khi Spring Kafka cấu hình **transaction-id-prefix**, producer được tạo với transactional ID và cơ chế idempotence được sử dụng. Khi đó, vẫn phải giữ **max.in.flight.requests.per.connection** không lớn hơn 5.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-instance-a-
      acks: all
      properties:
        "[max.in.flight.requests.per.connection]": 5
~~~

Prefix cần tạo transactional ID riêng cho mỗi instance ứng dụng chạy đồng thời. Thuộc tính in-flight chỉ điều khiển số request đang chờ; nó không tự tạo transaction, không commit transaction và không thay thế cấu hình transaction manager.

## 7. Chọn giá trị theo yêu cầu

### Trường hợp thông thường: idempotence bật

Với producer nghiệp vụ hiện đại, bắt đầu bằng **enable.idempotence=true** và **max.in.flight.requests.per.connection=5**. Đây là lựa chọn cân bằng: producer có thể gửi nhiều request trên một kết nối, giảm thời gian chờ round trip và vẫn giữ thứ tự batch trong partition khi retry.

Không cần giảm xuống 1 chỉ vì hệ thống yêu cầu các sự kiện cùng key phải theo thứ tự. Hãy đảm bảo các sự kiện có cùng key được định tuyến vào cùng partition, đồng thời giữ idempotence bật.

### Trường hợp không bật idempotence

Nếu idempotence bị tắt, hãy xem xét mối quan hệ giữa retry và thứ tự:

- Nếu retries bằng 0, producer không retry các request lỗi; rủi ro đảo thứ tự do retry không xuất hiện, nhưng record có thể không được giao sau một lỗi tạm thời.
- Nếu retries lớn hơn 0 và giá trị in-flight lớn hơn 1, record có thể bị sắp xếp lại trong partition khi request trước cần retry.
- Nếu cần giữ thứ tự trong trường hợp retry mà không bật idempotence, đặt giá trị bằng 1 sẽ tuần tự hóa request trên kết nối, nhưng phải chấp nhận throughput thấp hơn.

Nếu có thể, hãy bật idempotence thay vì dựa vào **max.in.flight.requests.per.connection=1** để bù cho việc tắt idempotence. Idempotence xử lý cả duplicate do retry và thứ tự sequence, đồng thời cho phép pipelining.

### Trường hợp cần throughput cao

Với độ trễ mạng cao, chỉ cho một request in-flight có thể khiến kết nối thường xuyên rảnh trong khi producer chờ broker. Cho phép nhiều request in-flight giúp che giấu một phần thời gian round trip. Tuy nhiên, throughput cuối cùng còn phụ thuộc số partition, batch size, linger, compression, tốc độ broker, replication, disk và network.

Không thể kết luận rằng tăng giá trị từ 1 lên 5 sẽ tăng throughput đúng năm lần. Các request có thể có kích thước khác nhau, broker có thể là nút thắt, và producer có thể bị giới hạn bởi serialization hoặc buffer.

Hãy đo ở tải gần production:

1. Giữ nguyên số partition, replication, payload và tốc độ phát record.
2. So sánh giá trị 1 và 5 khi idempotence bật.
3. Theo dõi throughput, p95/p99 latency, request latency, retry rate và buffer wait.
4. Kiểm tra hành vi khi broker leader thay đổi hoặc mạng có độ trễ/lỗi tạm thời.
5. Chọn giá trị đáp ứng SLO với tài nguyên hợp lý.

## 8. Tác động đến độ trễ và backpressure

Giá trị thấp làm giảm số request đang chờ, nhưng cũng giảm mức độ tận dụng kết nối. Nếu broker phản hồi chậm, producer phải đợi response trước khi gửi thêm request. Một request bị chậm có thể khiến các batch tiếp theo chờ phía producer dù chúng đã sẵn sàng.

Giá trị cao cho phép producer tiếp tục gửi request trong lúc các request trước đang được xử lý. Điều này thường hữu ích khi network round trip là một phần đáng kể của thời gian gửi. Tuy nhiên, nó không làm broker xử lý nhanh hơn và không loại bỏ giới hạn tài nguyên của broker.

Khi producer tạo record nhanh hơn tốc độ broker xử lý:

1. Các request đang in-flight chiếm các vị trí cho phép.
2. Các batch mới tích tụ trong accumulator khi chưa thể gửi.
3. Buffer producer tăng mức sử dụng.
4. Khi buffer không còn đủ chỗ, **send()** có thể chờ cấp phát buffer trong giới hạn **max.block.ms**.
5. Nếu không lấy được buffer đúng hạn, ứng dụng có thể nhận **TimeoutException**.

Vì vậy, tăng giới hạn in-flight không phải cách chữa mọi vấn đề nghẽn. Cần kiểm tra broker latency, batch size, compression, số partition, buffer memory, tốc độ phát và thời gian chờ cấp phát buffer.

## 9. Theo dõi khi chạy production

Khi điều chỉnh **max.in.flight.requests.per.connection**, cần theo dõi các chỉ số thể hiện cả khả năng gửi và mức độ chờ:

| Chỉ số | Ý nghĩa khi điều tra |
|---|---|
| **requests-in-flight** (nếu client/exporter cung cấp theo node) | Số request đang chờ response trên kết nối đến broker. |
| Request latency trung bình và tối đa | Thời gian broker phản hồi request; latency cao có thể làm các vị trí in-flight bị chiếm lâu. |
| Record send rate / byte rate | Tốc độ producer gửi record và dung lượng. |
| Record retry rate | Tần suất producer phải retry; tăng đột ngột có thể báo hiệu broker hoặc mạng không ổn định. |
| Record error rate | Tỷ lệ gửi thất bại cuối cùng. |
| Record queue time | Thời gian record chờ trong producer trước khi gửi. |
| Buffer pool wait time | Thời gian producer phải chờ buffer, thường hữu ích khi có backpressure. |
| Batch size và compression rate | Cho biết hiệu quả gom batch và nén. |

Tên metric và cách exporter hiển thị có thể khác theo phiên bản Kafka client và hệ thống quan sát. Hãy đối chiếu metric thực tế của client đang chạy, không giả định mọi exporter đều công bố cùng một tên.

Một số dấu hiệu và hướng điều tra:

- Throughput thấp, request latency cao, **max.in.flight** đặt bằng 1: thử nghiệm giá trị 5 khi idempotence bật để đánh giá lợi ích pipelining.
- Retry rate tăng và request latency tăng: điều tra broker, leader election, network và replication trước khi tăng giới hạn.
- Buffer wait tăng: producer đang chịu backpressure; kiểm tra tốc độ gửi, broker capacity và batch configuration.
- Producer khởi tạo thất bại sau khi đổi property: kiểm tra **enable.idempotence**, **acks**, **retries** và giới hạn tối đa 5.
- Record bị đảo thứ tự: xác minh idempotence có thực sự bật, có application-level resend hay nhiều producer cùng ghi partition hay không.

## 10. Những hiểu nhầm thường gặp

**Giá trị 5 có nghĩa chỉ gửi năm record cùng lúc.** Không đúng. Đây là số request chưa nhận response trên mỗi kết nối broker. Một request có thể chứa nhiều record trong nhiều batch.

**Giá trị 5 là giới hạn tổng request của toàn cluster.** Không đúng. Giới hạn được áp dụng riêng trên từng kết nối broker.

**KafkaTemplate.send() bất đồng bộ nên không cần quan tâm giới hạn in-flight.** Không đúng. API bất đồng bộ giúp caller không phải chờ kết quả ngay, còn Kafka producer vẫn phải quản lý số request đang chờ trên từng kết nối.

**Đặt bằng 1 luôn là cách tốt nhất để giữ thứ tự.** Không đúng. Nó tuần tự hóa request trên kết nối nhưng có thể làm throughput giảm. Khi idempotence bật, giá trị đến 5 vẫn hỗ trợ giữ thứ tự trong phạm vi producer.

**Đặt lớn hơn 5 luôn tăng throughput.** Không đúng. Khi idempotence bật, giá trị lớn hơn 5 không tương thích. Khi idempotence tắt, retry có thể làm đảo thứ tự; broker hoặc network cũng có thể là nút thắt.

**Idempotence ngăn mọi lần gửi trùng.** Không đúng. Nó ngăn bản sao do retry nội bộ của producer, không nhận diện hai lần gọi **send()** độc lập cho cùng một sự kiện nghiệp vụ.

**Thuộc tính này tạo thứ tự giữa các partition.** Không đúng. Kafka chỉ bảo đảm thứ tự trong một partition. Cần chọn key phù hợp cho các record phải theo thứ tự.

## 11. Quy trình cấu hình và kiểm tra

Khi thêm producer hoặc điều chỉnh cấu hình hiện có, có thể làm theo trình tự sau:

1. Xác định phiên bản Kafka client mà Spring Kafka đang sử dụng, vì mặc định idempotence và một số chi tiết cấu hình phụ thuộc phiên bản.
2. Xác định liệu producer có cần retry và giữ thứ tự record trong cùng partition hay không.
3. Bật **enable.idempotence=true** cho producer cần độ tin cậy.
4. Đặt **acks=all**, cho phép retry và giữ **max.in.flight.requests.per.connection** trong khoảng từ 1 đến 5.
5. Bắt đầu với giá trị 5 nếu không có lý do đo được để giảm xuống.
6. Đảm bảo các record cần thứ tự dùng cùng key và được định tuyến vào cùng partition.
7. Kiểm tra producer khởi tạo thành công và không có lỗi cấu hình tương thích.
8. Đo throughput, latency, retry và buffer wait ở tải đại diện.
9. Kiểm tra hành vi khi broker tạm thời mất kết nối hoặc leader được bầu lại.
10. Ghi lại giá trị cuối cùng cùng lý do lựa chọn để vận hành có thể giải thích và tái tạo cấu hình.

**max.in.flight.requests.per.connection** là một nút điều chỉnh pipelining của producer. Giá trị 5 thường phù hợp với idempotent producer hiện đại: nó tận dụng kết nối tốt hơn giá trị 1 mà vẫn duy trì thứ tự trong phạm vi Kafka producer. Chỉ giảm giá trị khi kết quả đo hoặc yêu cầu vận hành cho thấy lợi ích cụ thể; đồng thời luôn xem xét idempotence, retry và key/partition như một nhóm cấu hình liên quan.
