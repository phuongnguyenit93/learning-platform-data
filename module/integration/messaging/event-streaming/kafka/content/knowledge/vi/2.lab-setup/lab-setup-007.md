# Gửi và đọc bản ghi đầu tiên bằng console producer, console consumer

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, từ topic, partition, offset, producer và consumer group đến replication, KRaft, Java/Spring Kafka, retry, ordering, giao dịch, Kafka Connect/Streams và vận hành cụm. Bài thực hành này giúp bạn gửi và đọc bản ghi đầu tiên bằng các công cụ dòng lệnh có sẵn trong Apache Kafka. Đây là cách nhanh để kiểm tra kết nối đến broker và quan sát luồng dữ liệu trước khi viết ứng dụng Java.

Bạn sẽ tạo một topic, mở consumer, gửi một số record bằng producer, đọc lại dữ liệu bằng một consumer group khác và quan sát key, partition cùng offset.

## 1. Mục tiêu thực hành

Sau bài này, bạn có thể:

- Kiểm tra Kafka broker có thể truy cập từ máy đang chạy lệnh hay không.
- Tạo và xem thông tin một topic bằng Kafka CLI.
- Dùng console producer gửi record vào topic.
- Dùng console consumer đọc record từ topic.
- Giải thích vì sao nên khởi động consumer trước khi gửi record trong lần thử đầu tiên.
- Dùng consumer group mới để đọc lại các record còn được lưu.
- Quan sát key, partition và offset của record.
- Nhận biết một số lỗi thường gặp khi kết nối và chạy thử Kafka CLI.

## 2. Chuẩn bị môi trường

Bài thực hành giả định bạn đã có một Kafka cluster đang chạy và máy hiện tại có bộ công cụ dòng lệnh của Apache Kafka. Nếu bạn vừa hoàn thành phần cài đặt môi trường, hãy sử dụng địa chỉ bootstrap server đã cấu hình ở bước đó.

Ví dụ trong bài dùng:

- Bootstrap server: **localhost:9092**
- Topic: **first-events**
- Consumer group: **first-events-reader**
- Một partition để dễ quan sát thứ tự record.
- Replication factor bằng 1, phù hợp với cluster Kafka chỉ có một broker trong môi trường thực hành.

Nếu broker của bạn dùng địa chỉ hoặc cổng khác, hãy thay **localhost:9092** trong các lệnh bằng địa chỉ bootstrap server thực tế. Khi chạy Kafka trong Docker, địa chỉ từ máy host có thể khác địa chỉ mà container sử dụng; hãy chọn listener được công bố cho đúng nơi bạn chạy CLI.

### 2.1. Xác định thư mục Kafka CLI

Các lệnh trong bài nằm trong thư mục **bin** của bản phân phối Kafka.

Trên Linux hoặc macOS, dùng các script có đuôi **.sh**:

- **bin/kafka-topics.sh**
- **bin/kafka-console-producer.sh**
- **bin/kafka-console-consumer.sh**
- **bin/kafka-broker-api-versions.sh**

Trên Windows PowerShell, dùng các file **.bat** trong **bin\windows**:

- **.\bin\windows\kafka-topics.bat**
- **.\bin\windows\kafka-console-producer.bat**
- **.\bin\windows\kafka-console-consumer.bat**
- **.\bin\windows\kafka-broker-api-versions.bat**

Mở terminal tại thư mục gốc của bản Kafka đã giải nén để có thể chạy các đường dẫn trên. Nếu bạn đã thêm thư mục script vào PATH, có thể gọi trực tiếp tên lệnh.

### 2.2. Kiểm tra broker

Trên Linux hoặc macOS:

~~~bash
bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092
~~~

Trên Windows PowerShell:

~~~powershell
.\bin\windows\kafka-broker-api-versions.bat --bootstrap-server localhost:9092
~~~

Nếu kết nối thành công, CLI sẽ hiển thị thông tin API mà broker hỗ trợ. Nội dung cụ thể phụ thuộc phiên bản Kafka và cấu hình cluster.

Lệnh này là phép kiểm tra nhanh kết nối từ CLI đến broker. Nếu không kết nối được, hãy kiểm tra broker đã khởi động, bootstrap server có đúng không và listener có thể truy cập từ terminal hiện tại hay không. Với cluster có bật TLS hoặc SASL, client còn cần cấu hình bảo mật phù hợp.

## 3. Luồng dữ liệu trong bài thực hành

Các công cụ console đóng vai trò producer và consumer độc lập. Producer ghi record vào topic; broker lưu record trong partition; consumer đọc record theo tiến độ của consumer group.

~~~mermaid
flowchart LR
    P[Console Producer] -->|Gửi record| T[(Topic: first-events)]
    T --> B[Partition 0]
    B --> C[Console Consumer]
    C --> G[Consumer group: first-events-reader]
~~~

Trong bài này, topic có một partition nên tất cả record được ghi vào cùng một log. Điều đó giúp ta dễ quan sát thứ tự ghi và đọc. Trong hệ thống thực tế có nhiều partition, thứ tự được bảo đảm trong từng partition; không có một thứ tự tổng thể mặc định giữa tất cả partition.

## 4. Tạo topic đầu tiên

Topic là tên logic đại diện cho một luồng record. Trước khi gửi dữ liệu, ta tạo topic **first-events**.

### 4.1. Tạo topic trên Linux hoặc macOS

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic first-events --partitions 1 --replication-factor 1
~~~

### 4.2. Tạo topic trên Windows PowerShell

~~~powershell
.\bin\windows\kafka-topics.bat --bootstrap-server localhost:9092 --create --topic first-events --partitions 1 --replication-factor 1
~~~

Trong lệnh trên:

| Tham số | Ý nghĩa |
|---|---|
| **--bootstrap-server** | Địa chỉ để CLI tìm và kết nối Kafka cluster. |
| **--create** | Yêu cầu tạo topic. |
| **--topic** | Tên topic cần tạo. |
| **--partitions 1** | Tạo một partition. |
| **--replication-factor 1** | Lưu một bản sao của partition. |

Replication factor bằng 1 phù hợp với cluster chỉ có một broker. Nếu cluster có nhiều broker, bạn có thể chọn replication factor lớn hơn, nhưng giá trị đó không được vượt quá số broker có thể lưu replica. Môi trường production thường cần replication factor và cấu hình ISR phù hợp với yêu cầu sẵn sàng; bài lab này chỉ tập trung vào việc gửi và đọc record.

Nếu lệnh báo topic đã tồn tại, không cần tạo lại. Hãy dùng lệnh mô tả topic ở phần tiếp theo để kiểm tra cấu hình hiện tại.

### 4.3. Liệt kê và mô tả topic

Liệt kê các topic:

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
~~~

Mô tả topic vừa tạo:

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic first-events
~~~

Trên Windows, thay **bin/kafka-topics.sh** bằng **.\bin\windows\kafka-topics.bat**.

Kết quả mô tả cho biết topic có bao nhiêu partition và replication factor. Với cấu hình của bài lab, bạn sẽ thấy một partition có ID là **0**. Các trường **Leader**, **Replicas** và **Isr** cho biết broker giữ replica và trạng thái replica đồng bộ. ID broker và một số trường có thể khác nhau giữa các môi trường.

## 5. Mở console consumer để đọc record

Consumer là ứng dụng đọc record từ topic. Mở **terminal thứ nhất** và chạy consumer trước khi gửi dữ liệu.

Linux hoặc macOS:

~~~bash
bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic first-events --group first-events-reader
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-console-consumer.bat --bootstrap-server localhost:9092 --topic first-events --group first-events-reader
~~~

Terminal sẽ chờ record mới. Khi chưa có dữ liệu, việc không thấy dòng output là bình thường.

Ta truyền **--group first-events-reader** để consumer tham gia một consumer group có tên rõ ràng. Kafka quản lý tiến độ đọc theo group và partition. Nếu bạn dừng rồi chạy lại consumer với cùng group, nó sẽ tiếp tục theo offset đã commit của group theo cấu hình consumer.

Hãy giữ terminal này mở. Ta sẽ gửi record từ terminal thứ hai.

## 6. Gửi record bằng console producer

Mở **terminal thứ hai**, tại thư mục Kafka, chạy producer.

Linux hoặc macOS:

~~~bash
bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic first-events
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-console-producer.bat --bootstrap-server localhost:9092 --topic first-events
~~~

Sau khi producer sẵn sàng, nhập từng dòng sau và nhấn Enter sau mỗi dòng:

~~~text
OrderCreated orderId=ORD-1001
PaymentAuthorized orderId=ORD-1001
OrderCreated orderId=ORD-1002
~~~

Mỗi dòng được gửi là một record. Console producer mặc định dùng nội dung dòng nhập làm value dạng chuỗi; ở bước này record chưa có key do ta chưa bật chế độ phân tích key.

Quay lại terminal consumer. Bạn sẽ thấy các value vừa gửi lần lượt xuất hiện:

~~~text
OrderCreated orderId=ORD-1001
PaymentAuthorized orderId=ORD-1001
OrderCreated orderId=ORD-1002
~~~

Nếu consumer đang chạy và topic có một partition, bạn có thể quan sát các record theo thứ tự chúng được ghi vào partition đó. Khi đã gửi xong, nhấn **Ctrl+C** ở terminal producer để kết thúc producer. Consumer vẫn tiếp tục chờ record mới; nhấn **Ctrl+C** ở terminal consumer khi muốn dừng.

**Điểm cần nhớ:** nhấn Enter trong console producer sẽ gửi một record. Một lần chạy producer có thể gửi nhiều record liên tiếp. Đừng nhập dòng trống nếu bạn không có ý định gửi một record có value rỗng.

## 7. Đọc lại các record đã gửi

Kafka lưu record theo chính sách retention của topic. Consumer group có thể đọc record còn được lưu ngay cả khi producer đã kết thúc.

Để xem lại từ đầu một cách dễ dự đoán, hãy dùng **consumer group mới** và thêm **--from-beginning**.

Linux hoặc macOS:

~~~bash
bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic first-events --group first-events-replay --from-beginning
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-console-consumer.bat --bootstrap-server localhost:9092 --topic first-events --group first-events-replay --from-beginning
~~~

Consumer group **first-events-replay** chưa có offset đã commit, vì vậy nó có thể bắt đầu đọc từ record sớm nhất còn được lưu trong topic. Bạn sẽ thấy lại ba record đã gửi.

Lưu ý quan trọng: **--from-beginning** thiết lập hành vi khi group chưa có offset hợp lệ. Nếu group đã có offset được commit, consumer sẽ tiếp tục từ tiến độ đã lưu; thêm tùy chọn này không tự động tua một group đang hoạt động về đầu topic. Dùng một group ID mới cho lần đọc lại trong bài lab này giúp tránh nhầm lẫn với tiến độ của group cũ.

Đây là điểm khác biệt quan trọng giữa Kafka và mô hình hàng đợi thường xóa message sau khi consumer xác nhận. Trong Kafka, consumer group quản lý offset riêng, còn record tiếp tục được lưu theo retention hoặc log compaction.

## 8. Quan sát key, partition và offset

Ở các bước trước, producer chỉ gửi value. Trong thực tế, record thường có cả key và value. Key có thể được dùng để định tuyến record đến partition, ví dụ các sự kiện của cùng một đơn hàng dùng **orderId** làm key.

### 8.1. Gửi record có key

Khởi động producer với hai thuộc tính:

- **parse.key=true**: yêu cầu producer phân tích key từ nội dung dòng.
- **key.separator=:**: dùng dấu hai chấm để phân tách key và value.

Linux hoặc macOS:

~~~bash
bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic first-events --property parse.key=true --property key.separator=:
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-console-producer.bat --bootstrap-server localhost:9092 --topic first-events --property parse.key=true --property key.separator=:
~~~

Nhập các dòng:

~~~text
ORD-1001:OrderShipped
ORD-1002:OrderCreated
ORD-1001:DeliveryUpdated
~~~

Với định dạng trên, phần trước dấu **:** là key và phần sau dấu **:** là value. Ví dụ, record đầu tiên có key **ORD-1001** và value **OrderShipped**.

### 8.2. In key và metadata khi đọc

Dùng một consumer group mới để đọc từ đầu và hiển thị key, partition, offset cùng timestamp:

Linux hoặc macOS:

~~~bash
bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic first-events --group first-events-inspector --from-beginning --property print.key=true --property print.partition=true --property print.offset=true --property print.timestamp=true
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-console-consumer.bat --bootstrap-server localhost:9092 --topic first-events --group first-events-inspector --from-beginning --property print.key=true --property print.partition=true --property print.offset=true --property print.timestamp=true
~~~

Kết quả hiển thị sẽ có thêm metadata. Cách định dạng chính xác phụ thuộc phiên bản Kafka, nhưng bạn có thể nhận diện:

- **Key:** giá trị producer dùng để định danh hoặc định tuyến record.
- **Value:** nội dung sự kiện được gửi.
- **Partition:** partition chứa record.
- **Offset:** vị trí record trong partition đó.
- **Timestamp:** timestamp được gắn cho record theo cấu hình producer/topic.

Trong bài này topic chỉ có một partition, nên các record đều thuộc partition **0** và offset tăng theo thứ tự ghi. Offset bắt đầu từ vị trí hiện tại của log; nếu topic đã từng có dữ liệu hoặc đã được sử dụng trước đó, giá trị bạn quan sát có thể khác ví dụ.

Key không phải là ID duy nhất của record và Kafka không tự kiểm tra tính duy nhất của key. Nhiều record có thể dùng cùng key. Khi dùng partitioner mặc định với key khác null, các record có cùng key thường được định tuyến đến cùng partition. Vì thế, chọn **orderId** làm key giúp các sự kiện của một đơn hàng có cơ hội giữ thứ tự trong cùng partition.

## 9. Thử nghiệm consumer group độc lập

Một topic có thể được nhiều consumer group đọc độc lập. Để quan sát, mở hai terminal và chạy hai consumer với hai group ID khác nhau, mỗi group đều dùng **--from-beginning**:

~~~bash
bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic first-events --group inventory-lab --from-beginning
~~~

~~~bash
bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic first-events --group analytics-lab --from-beginning
~~~

Cả hai consumer group đều có thể nhận các record còn được lưu trong topic. Khi bạn gửi thêm một record từ producer, cả hai group có thể đọc record đó theo tiến độ riêng của mình.

Điều này khác với việc chạy hai consumer cùng một group. Consumer trong cùng group chia nhau các partition để xử lý tải; các group khác nhau có offset độc lập và mỗi group có thể đọc cùng luồng dữ liệu cho một mục đích riêng.

## 10. Các lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| **Connection to node -1 could not be established** | Broker chưa chạy, sai địa chỉ bootstrap server hoặc listener không truy cập được từ máy hiện tại. | Kiểm tra tiến trình broker, cổng và địa chỉ listener; chạy lại lệnh **kafka-broker-api-versions**. |
| **TopicExistsException** | Topic đã tồn tại. | Dùng **kafka-topics --describe** để xem topic hiện tại thay vì tạo lại. |
| **InvalidReplicationFactorException** | Replication factor lớn hơn số broker có thể lưu replica. | Với cluster một broker, dùng **--replication-factor 1**. |
| Consumer không in record nào | Consumer đang chờ record mới, sai topic/broker, hoặc group đã có offset ở cuối log. | Kiểm tra topic, gửi record mới khi consumer đang chạy hoặc dùng group mới với **--from-beginning**. |
| Không thể xác thực hoặc bị từ chối quyền | Cluster bật SASL/TLS/ACL nhưng CLI chưa có cấu hình phù hợp hoặc principal thiếu quyền. | Dùng cấu hình client đúng với cluster và kiểm tra quyền đọc/ghi topic. |
| Producer gửi được nhưng consumer không đọc được | Consumer đang dùng group khác tiến độ, sai topic, hoặc quyền đọc không đủ. | Xác minh bootstrap server, topic, group ID và quyền ACL của consumer. |

Một số điểm cần kiểm tra theo thứ tự khi CLI không hoạt động:

1. Broker đã khởi động và trạng thái cluster bình thường.
2. Địa chỉ bootstrap server đúng với môi trường đang chạy CLI.
3. Topic tồn tại và có partition leader.
4. Producer có quyền ghi topic.
5. Consumer có quyền đọc topic và sử dụng consumer group.
6. Consumer có đang đọc từ offset hiện tại hay cần group mới để phát lại dữ liệu.

Nếu Kafka chạy trong Docker, cần phân biệt địa chỉ bên trong network Docker với địa chỉ publish ra máy host. Một broker có thể nhận kết nối ban đầu nhưng sau đó trả về địa chỉ advertised listener mà client không truy cập được. Khi đó, hãy kiểm tra cấu hình listener/advertised listener trong phần thiết lập cluster.

## 11. Bài tập củng cố

Thực hiện lại quy trình với topic **orders-lab**:

1. Tạo topic có một partition và replication factor phù hợp với số broker của môi trường.
2. Mở consumer group **orders-reader** trước khi gửi dữ liệu.
3. Gửi ít nhất ba record, trong đó có hai record cùng key **ORD-2001**.
4. Dùng consumer group mới **orders-replay** để đọc lại từ đầu.
5. Bật **print.key**, **print.partition** và **print.offset** để quan sát metadata.
6. Mở thêm consumer group **orders-analytics** và xác nhận group này cũng đọc được các record.
7. Ghi lại kết quả: topic có bao nhiêu partition, mỗi record có key/value nào và offset của chúng là bao nhiêu.

Câu hỏi tự kiểm tra:

1. Vì sao nên mở consumer trước khi gửi record trong lần thử đầu tiên?
2. Một dòng nhập trong console producer tương ứng với bao nhiêu record?
3. **--from-beginning** có luôn tua một consumer group đã chạy về đầu topic không?
4. Vì sao hai consumer group khác nhau có thể đọc cùng một record?
5. Nếu hai record có cùng key, key có bảo đảm chúng được đưa vào cùng partition không?
6. Offset có ý nghĩa trong phạm vi topic hay partition?
7. Nếu topic chỉ có một partition, giới hạn song song của một consumer group là gì?
8. Vì sao replication factor bằng 1 chỉ phù hợp với bài lab một broker, không cung cấp khả năng chịu lỗi broker?

## 12. Kết quả mong đợi

Bạn hoàn thành bài thực hành khi có thể xác nhận các điểm sau:

- Kafka CLI kết nối được đến bootstrap server.
- Topic **first-events** đã tồn tại và có partition như cấu hình.
- Console producer gửi được nhiều record.
- Console consumer nhận được value của record.
- Một consumer group mới có thể đọc lại các record còn được lưu bằng **--from-beginning**.
- Bạn quan sát được key, partition và offset bằng các thuộc tính in metadata.
- Bạn giải thích được sự độc lập về offset giữa các consumer group.

Console producer và console consumer là công cụ kiểm tra nhanh luồng dữ liệu, rất hữu ích khi học Kafka hoặc chẩn đoán kết nối. Trong ứng dụng thực tế, producer và consumer sẽ được triển khai bằng thư viện client như Java Kafka Client hoặc Spring Kafka. Các vấn đề về serializer, schema, retry, commit offset, idempotency, ordering và giao dịch sẽ được xử lý trong những bài tiếp theo của module KAFKA.

