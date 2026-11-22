# Tạo topic và kiểm tra metadata bằng công cụ dòng lệnh

Topic là nơi Kafka lưu trữ một luồng record. Trước khi producer gửi sự kiện hoặc consumer đọc dữ liệu, người vận hành thường cần tạo topic với số partition và replication factor phù hợp, sau đó kiểm tra metadata để xác nhận topic đã được tạo đúng.

Trong bài thực hành này, bạn dùng các công cụ dòng lệnh đi kèm bản phân phối Apache Kafka. Các lệnh sử dụng `--bootstrap-server`, phù hợp với cụm Kafka hiện đại chạy KRaft. Bạn sẽ tạo topic `orders`, xem số partition, leader, replica và ISR, rồi đọc cấu hình topic.

## 1. Chuẩn bị kết nối tới cụm Kafka

Giả sử Kafka đang chạy trên máy cục bộ và broker có thể truy cập tại `localhost:9092`. Nếu cụm của bạn dùng địa chỉ khác, hãy thay giá trị này trong các lệnh bên dưới bằng một bootstrap server có thể truy cập.

`--bootstrap-server` chỉ cần một hoặc vài địa chỉ broker để client khởi đầu kết nối và lấy metadata cụm. Sau khi kết nối, Kafka client biết các broker và partition leader cần thiết. Đây không nhất thiết là danh sách đầy đủ tất cả broker trong cụm.

Mở terminal tại thư mục cài đặt Kafka hoặc dùng đường dẫn đầy đủ đến thư mục `bin`:

**Linux/macOS:**

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

**Windows PowerShell:**

```powershell
.\bin\windows\kafka-topics.bat --bootstrap-server localhost:9092 --list
```

Nếu lệnh chạy thành công, công cụ có thể trả về danh sách topic hiện có; danh sách rỗng cũng có thể là kết quả hợp lệ khi cụm chưa có topic do người dùng tạo. Nếu không kết nối được, kiểm tra broker đã khởi động, địa chỉ và cổng listener, firewall, cũng như cấu hình advertised listener mà client cần truy cập.

Với cụm có xác thực hoặc TLS, truyền file cấu hình client bằng `--command-config`, ví dụ:

```bash
bin/kafka-topics.sh --bootstrap-server kafka.example.internal:9093 \
  --command-config client.properties --list
```

File `client.properties` cần chứa các thiết lập bảo mật phù hợp với cụm, chẳng hạn security protocol, cơ chế SASL hoặc truststore. Không đưa mật khẩu trực tiếp vào lịch sử shell hoặc chia sẻ file cấu hình chứa bí mật.

## 2. Tạo topic

Tạo topic `orders` với ba partition và replication factor bằng một:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --if-not-exists \
  --topic orders \
  --partitions 3 \
  --replication-factor 1
```

Trên Windows, thay `bin/kafka-topics.sh` bằng `bin\windows\kafka-topics.bat` và có thể viết lệnh trên một dòng trong PowerShell:

```powershell
.\bin\windows\kafka-topics.bat --bootstrap-server localhost:9092 --create --if-not-exists --topic orders --partitions 3 --replication-factor 1
```

Ý nghĩa các tùy chọn:

| Tùy chọn | Ý nghĩa |
|---|---|
| `--bootstrap-server` | Địa chỉ broker dùng để khởi đầu kết nối và truy vấn metadata |
| `--create` | Yêu cầu tạo topic |
| `--if-not-exists` | Không báo lỗi chỉ vì topic đã tồn tại; không tự cập nhật cấu hình topic cũ |
| `--topic orders` | Tên topic cần tạo |
| `--partitions 3` | Tạo ba partition: 0, 1 và 2 |
| `--replication-factor 1` | Mỗi partition có một bản sao |

Replication factor phải nhỏ hơn hoặc bằng số broker đủ điều kiện nhận replica trong cụm. Cấu hình trên phù hợp với cụm thực hành chỉ có một broker. Trong cụm ba broker, bạn có thể dùng replication factor bằng ba để mỗi partition có ba bản sao trên các broker khác nhau:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --if-not-exists \
  --topic payments \
  --partitions 6 \
  --replication-factor 3
```

Ví dụ thứ hai chỉ thành công khi cụm có đủ broker phù hợp và có thể phân bổ các replica theo yêu cầu. Tăng replication factor giúp tăng khả năng chịu lỗi của dữ liệu, nhưng cũng tăng dung lượng lưu trữ và lưu lượng sao chép. Replication factor bằng một không có bản sao dự phòng nếu broker duy nhất gặp sự cố.

### Chọn số partition

Partition là đơn vị lưu trữ và xử lý song song của topic. Số partition ảnh hưởng đến khả năng mở rộng consumer group và cách phân phối tải. Trong một consumer group, tại một thời điểm, mỗi partition được gán cho tối đa một consumer trong group đó; vì vậy số consumer xử lý song song hữu ích bị giới hạn bởi số partition được gán.

Không nên chọn số partition chỉ dựa trên số consumer dự kiến. Hãy tính đến throughput cần đạt, kích thước record, số broker, dung lượng đĩa, chi phí mở file và metadata, cách chọn key, cũng như khả năng tăng trưởng. Quá nhiều partition có thể làm tăng chi phí vận hành và thời gian phục hồi hoặc rebalance.

## 3. Liệt kê và mô tả topic

Liệt kê topic trong cụm:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Kiểm tra metadata của topic vừa tạo:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic orders
```

Kết quả thường có một dòng tổng quan topic và một dòng cho mỗi partition. Ví dụ minh họa trên cụm một broker:

```text
Topic: orders  TopicId: ...  PartitionCount: 3  ReplicationFactor: 1  Configs: ...
  Topic: orders  Partition: 0  Leader: 1  Replicas: 1  Isr: 1
  Topic: orders  Partition: 1  Leader: 1  Replicas: 1  Isr: 1
  Topic: orders  Partition: 2  Leader: 1  Replicas: 1  Isr: 1
```

Topic ID là định danh nội bộ của topic; giá trị thực tế do cụm tạo. Broker ID `1` trong ví dụ cũng chỉ là minh họa, không phải ID bắt buộc của mọi cụm.

Các trường quan trọng:

| Trường | Cách đọc |
|---|---|
| `Topic` | Tên topic |
| `TopicId` | Định danh duy nhất của topic trong cụm |
| `PartitionCount` | Tổng số partition của topic |
| `ReplicationFactor` | Số replica được cấu hình cho mỗi partition |
| `Partition` | ID của partition; thường bắt đầu từ 0 |
| `Leader` | Broker hiện giữ vai trò leader của partition; client gửi request ghi và đọc tới leader theo giao thức Kafka |
| `Replicas` | Danh sách broker được phân công lưu replica của partition |
| `Isr` | Danh sách replica đang nằm trong In-Sync Replicas, tức các replica theo kịp leader theo tiêu chí đồng bộ của Kafka |

Leader là điểm điều phối chính cho partition. Replica follower lấy dữ liệu từ leader. ISR biểu thị các replica đủ đồng bộ để được xem xét trong các quyết định liên quan đến độ bền dữ liệu và bầu chọn leader. Khi mọi replica đều khỏe, danh sách `Isr` thường chứa đầy đủ các broker trong `Replicas`.

Nếu `Replicas` có ba broker nhưng `Isr` chỉ có hai, một replica có thể đang chậm hoặc không khả dụng. Nếu `Leader` hiển thị `-1`, partition hiện không có leader khả dụng. Hãy kiểm tra trạng thái broker, log broker, kết nối giữa các broker và tình trạng sao chép trước khi đưa topic vào sử dụng.

## 4. Kiểm tra trạng thái replica

Có thể yêu cầu công cụ chỉ hiển thị partition đang thiếu replica đồng bộ:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --under-replicated-partitions
```

Để tìm partition không có leader khả dụng:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --unavailable-partitions
```

Hai truy vấn này hữu ích khi kiểm tra sức khỏe cụm. Nếu không có kết quả, không có partition phù hợp với bộ lọc tại thời điểm truy vấn. Trên cụm một broker với replication factor bằng một, việc `Isr` có một broker chỉ xác nhận replica duy nhất đang đồng bộ; nó không chứng minh cụm có khả năng chịu lỗi broker.

## 5. Đọc cấu hình topic

Metadata mô tả partition và replica. Cấu hình topic như thời gian lưu trữ hoặc chính sách dọn dẹp được truy vấn riêng bằng `kafka-configs`:

```bash
bin/kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name orders --describe
```

Lệnh này hiển thị các cấu hình được đặt riêng cho topic. Một số cấu hình có thể không xuất hiện vì topic đang kế thừa giá trị mặc định từ broker. Muốn xem một giá trị hiệu lực, cần xét cả cấu hình topic và mặc định broker tương ứng.

Ví dụ, đặt thời gian lưu trữ của topic thành bảy ngày:

```bash
bin/kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name orders \
  --alter --add-config retention.ms=604800000
```

Đọc lại cấu hình để xác nhận:

```bash
bin/kafka-configs.sh --bootstrap-server localhost:9092 \
  --entity-type topics --entity-name orders --describe
```

`retention.ms` điều khiển thời gian lưu record theo chính sách retention của topic; nó không phải cam kết rằng dữ liệu sẽ bị xóa đúng tại thời điểm đủ bảy ngày. Việc dọn segment diễn ra theo chu kỳ và phụ thuộc điều kiện lưu trữ của broker. Không đặt retention thấp trong môi trường có yêu cầu lưu trữ dài hạn nếu chưa xác nhận tác động.

## 6. Tăng số partition khi cần

Kafka cho phép tăng số partition của topic bằng lệnh alter:

```bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --alter --topic orders --partitions 6
```

Giá trị mới phải lớn hơn số partition hiện tại. Lệnh này tăng số partition lên sáu; không thể dùng lệnh này để giảm số partition. Việc tăng partition cũng không tự động phân phối lại các record cũ sang partition mới.

Nếu ứng dụng dùng key để chọn partition, thay đổi số partition có thể làm thay đổi partition đích của một key khi producer tính toán lại phép ánh xạ. Điều này ảnh hưởng đến thứ tự tương đối của các sự kiện cùng key qua thời điểm thay đổi. Hãy đánh giá tác động đến ordering, consumer và dữ liệu trước khi tăng partition của topic đang hoạt động.

## 7. Metadata topic trong cụm KRaft

Trong chế độ KRaft, Kafka dùng controller quorum để quản lý metadata cụm thay cho ZooKeeper. Lệnh `kafka-topics --describe` truy vấn metadata topic qua broker; người vận hành không cần truyền địa chỉ ZooKeeper cho các lệnh trong bài này.

Nếu cần kiểm tra riêng trạng thái metadata quorum của cụm KRaft, có thể dùng công cụ `kafka-metadata-quorum` trong các phiên bản Kafka hỗ trợ:

```bash
bin/kafka-metadata-quorum.sh --bootstrap-server localhost:9092 describe --status
```

Lệnh này cung cấp trạng thái quorum metadata, chẳng hạn leader và thông tin đồng bộ của voter. Đây là trạng thái của lớp quản lý metadata KRaft, khác với metadata partition của topic được hiển thị bằng `kafka-topics --describe`. Nếu phiên bản Kafka đang dùng chưa cung cấp công cụ hoặc cú pháp này, hãy tham khảo tài liệu đi kèm đúng phiên bản.

## 8. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `Connection to node ... could not be established` hoặc timeout | Broker chưa chạy, sai địa chỉ/cổng, listener không truy cập được | Kiểm tra tiến trình broker, listener, advertised listener, firewall và kết nối mạng |
| `TopicExistsException` | Topic cùng tên đã tồn tại | Dùng `--list` và `--describe`; kiểm tra topic hiện tại có đúng cấu hình mong muốn không |
| `InvalidReplicationFactorException` | Replication factor lớn hơn số broker có thể nhận replica | Kiểm tra số broker đang hoạt động và giảm replication factor cho môi trường thực hành nhỏ |
| `TopicAuthorizationException` hoặc lỗi authorization | Principal chưa có quyền tạo hoặc mô tả topic | Kiểm tra ACL/chính sách quyền và file cấu hình client |
| Partition không có leader hoặc ISR thiếu replica | Broker lỗi, replica chậm hoặc mất kết nối | Kiểm tra trạng thái broker, log, network và quá trình đồng bộ replica |
| Topic tồn tại nhưng cấu hình không như lệnh tạo mong muốn | Đã dùng `--if-not-exists`; lệnh không cập nhật topic có sẵn | Dùng `kafka-configs --describe` và thay đổi có chủ đích bằng `--alter` |

Khi thao tác với cụm dùng xác thực, hãy giữ nguyên `--command-config client.properties` trong các lệnh tương ứng. Nếu một broker trong danh sách bootstrap có thể truy cập nhưng các broker được quảng bá qua metadata không truy cập được, kiểm tra `advertised.listeners`; đây là lỗi thường gặp khi chạy Kafka trong container hoặc trên máy ảo.

## 9. Bài thực hành và tiêu chí hoàn thành

Thực hiện lần lượt các thao tác sau trên cụm Kafka của bạn:

1. Kết nối bằng `--bootstrap-server` và liệt kê topic hiện có.
2. Tạo topic `orders` với ba partition. Dùng replication factor phù hợp với số broker trong cụm.
3. Chạy `--describe --topic orders` và ghi lại `TopicId`, `PartitionCount`, `ReplicationFactor`, `Leader`, `Replicas` và `Isr`.
4. Chạy lệnh `--describe --under-replicated-partitions` và `--describe --unavailable-partitions`; giải thích kết quả nhận được.
5. Dùng `kafka-configs --describe` để xem cấu hình topic. Đặt `retention.ms` trong môi trường thực hành rồi đọc lại để xác nhận.
6. Nếu môi trường cho phép, tăng số partition và mô tả điều gì thay đổi trong metadata.
7. Nếu cụm chạy KRaft và phiên bản hỗ trợ, kiểm tra metadata quorum bằng `kafka-metadata-quorum --describe --status`.

Bạn hoàn thành bài khi có thể tạo topic bằng CLI, giải thích được số partition và replication factor, đọc đúng leader/replicas/ISR trong kết quả describe, phân biệt metadata topic với metadata quorum KRaft và xác minh được cấu hình topic sau khi thay đổi.

Các lệnh trong bài dùng cú pháp CLI phổ biến của Kafka hiện đại. Tên tùy chọn, đầu ra và công cụ sẵn có có thể thay đổi theo phiên bản; khi kết quả khác ví dụ, hãy ưu tiên trợ giúp `--help` và tài liệu của đúng bản phân phối Kafka đang chạy.
