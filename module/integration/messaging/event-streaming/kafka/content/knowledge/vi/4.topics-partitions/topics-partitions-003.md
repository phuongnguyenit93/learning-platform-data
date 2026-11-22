# Phạm vi bảo đảm thứ tự trong một partition

## Mục tiêu bài học

Kafka thường được dùng cho những luồng sự kiện mà thứ tự xử lý có ý nghĩa: đơn hàng được tạo trước khi thanh toán, tài khoản được mở trước khi thay đổi số dư, hoặc một thiết bị gửi các trạng thái theo thời gian. Để thiết kế đúng, cần hiểu chính xác Kafka bảo đảm thứ tự ở đâu và những lớp nào của ứng dụng có thể làm thứ tự đó thay đổi.

Sau bài học, bạn có thể:

- Giải thích thứ tự record theo offset trong một partition và giới hạn của bảo đảm này.
- Phân biệt thứ tự append, thứ tự gửi, timestamp và thứ tự nghiệp vụ.
- Chọn message key để gom sự kiện của cùng một thực thể vào một partition.
- Cấu hình producer để retry không làm đảo thứ tự trong các điều kiện Kafka hỗ trợ.
- Giữ thứ tự khi consumer xử lý song song, retry, commit offset và trải qua rebalance.
- Nhận diện các tình huống không có thứ tự toàn cục giữa nhiều partition.

## 1. Kafka bảo đảm thứ tự ở phạm vi nào?

### 1.1. Một partition là một log có thứ tự

Mỗi partition của Kafka là một log. Broker append record vào log và gán offset cho record. Offset xác định vị trí trong partition đó; record có offset nhỏ hơn đứng trước record có offset lớn hơn trong log.

Ví dụ topic `orders` có hai partition:

```text
Topic: orders

Partition 0                         Partition 1
offset 0  OrderCreated(A)            offset 0  OrderCreated(B)
offset 1  PaymentRequested(A)        offset 1  OrderCreated(C)
offset 2  OrderPaid(A)               offset 2  PaymentRequested(B)
offset 3  OrderShipped(A)            offset 3  OrderCancelled(C)
```

Kafka giữ thứ tự record trong từng partition. Consumer đọc partition 0 sẽ quan sát các record theo thứ tự offset 0, 1, 2, 3; consumer đọc partition 1 cũng quan sát thứ tự offset 0, 1, 2, 3 của partition đó.

### 1.2. Không có thứ tự tổng thể giữa các partition

Không có một offset toàn cục để so sánh record ở partition 0 với record ở partition 1. Kafka có thể phục vụ hai partition song song trên các broker khác nhau; consumer group cũng có thể phân công chúng cho các consumer khác nhau.

Ví dụ, record `OrderPaid(A)` ở partition 0 có thể được consumer xử lý trước `OrderCreated(B)` ở partition 1, dù hai record được producer tạo gần như cùng lúc. Đây không phải vi phạm thứ tự Kafka vì hai record thuộc hai log độc lập.

| Phạm vi | Kafka bảo đảm điều gì? |
|---|---|
| Một partition | Record được lưu và đọc theo thứ tự offset của partition |
| Nhiều partition trong cùng topic | Không có thứ tự tổng thể mặc định giữa các partition |
| Nhiều topic | Không có thứ tự tổng thể mặc định giữa các topic |
| Nhiều cluster | Không có thứ tự chung được Kafka tự động duy trì |

Vì vậy, khi yêu cầu nghiệp vụ nói “sự kiện phải đúng thứ tự”, cần hỏi rõ thứ tự của **đối tượng nào**. Nếu chỉ cần giữ thứ tự các thay đổi của một đơn hàng, một tài khoản hoặc một thiết bị, có thể dùng key để gom các sự kiện của đối tượng đó vào cùng partition. Nếu nghiệp vụ yêu cầu thứ tự toàn bộ hệ thống, cần một cơ chế điều phối hoặc một luồng tuần tự riêng; tăng số consumer không tạo ra thứ tự toàn cục.

### 1.3. Offset là thứ tự log, không phải đồng hồ

Offset tăng theo vị trí append trong một partition. Timestamp là một thông tin khác: nó có thể là CreateTime do producer gửi hoặc LogAppendTime do broker gán theo cấu hình.

Không nên sắp xếp record chỉ dựa vào timestamp rồi kết luận đó là thứ tự Kafka. Hai record có timestamp bằng nhau, timestamp từ các máy có thể lệch nhau, và một sự kiện cũ có thể được gửi đến muộn. Trong một partition, offset mới là căn cứ để xác định thứ tự log.

Offset cũng không phải số thứ tự liên tục mà ứng dụng luôn nhìn thấy. Transaction bị abort, control record, compaction và các quy tắc đọc như `read_committed` có thể khiến consumer quan sát các offset có khoảng cách. Khoảng cách đó không có nghĩa Kafka đã đảo thứ tự.

## 2. Dùng key để giữ thứ tự theo thực thể

### 2.1. Chọn key theo đối tượng cần tuần tự hóa

Producer có thể gửi record với một key. Với partitioner mặc định trong các cấu hình thông thường, key được serialize thành bytes rồi dùng để chọn partition. Các record có cùng key thường được đưa về cùng partition khi topic giữ nguyên số partition và producer dùng cùng quy tắc phân vùng.

Ví dụ với topic `orders`:

```text
key = orderId

OrderCreated(ORD-101)       -> partition 2
PaymentRequested(ORD-101)   -> partition 2
OrderPaid(ORD-101)          -> partition 2
OrderShipped(ORD-101)       -> partition 2

OrderCreated(ORD-202)       -> partition 0
PaymentRequested(ORD-202)   -> partition 0
OrderCancelled(ORD-202)     -> partition 0
```

Các sự kiện của cùng đơn hàng được append vào cùng một log. Các đơn hàng khác nhau vẫn có thể được xử lý song song ở những partition khác nhau.

Một số lựa chọn key thường gặp:

| Luồng dữ liệu | Key phù hợp khi cần thứ tự theo | Điều cần cân nhắc |
|---|---|---|
| `orders` | `orderId` | Một đơn hàng có thể phát sinh nhiều sự kiện |
| `account-transactions` | `accountId` | Mọi thay đổi số dư của tài khoản cần được tuần tự hóa |
| `inventory-events` | `sku` hoặc `warehouseId + sku` | Chọn đúng phạm vi tồn kho cần cập nhật tuần tự |
| `device-telemetry` | `deviceId` | Một thiết bị có thứ tự riêng; tránh một key quá nóng |
| `customer-events` | `customerId` | Chỉ gom theo khách hàng nếu nghiệp vụ thật sự cần thứ tự đó |

Key nên đại diện cho đơn vị cần xử lý tuần tự, không chỉ là trường dễ lấy nhất trong payload. Ví dụ, nếu tồn kho được quản lý theo từng kho và SKU, dùng riêng `sku` có thể gom mọi kho vào một partition; dùng tổ hợp `warehouseId` và `sku` có thể phù hợp hơn nếu mỗi kho có trạng thái độc lập.

### 2.2. Key không phải một khóa toàn cục của Kafka

Kafka không hiểu ngữ nghĩa của key. Kafka chỉ nhận bytes do serializer tạo ra và áp dụng partitioner. Nếu hai producer serialize cùng một ID thành bytes khác nhau, dùng partitioner khác nhau hoặc chọn partition tường minh khác nhau, record có thể không vào cùng partition.

Các trường hợp cần kiểm tra:

- Key có thực sự được đặt trên mọi record liên quan không?
- Các producer có cùng cách serialize key không?
- Producer có dùng cùng partitioner và cấu hình phân vùng không?
- Có nơi nào chỉ định partition trực tiếp, bỏ qua kết quả partitioner không?
- Topic có thay đổi số partition trong thời gian vận hành không?

Nếu key là `null`, producer không có định danh để gom theo thực thể. Partitioner có thể phân phối record theo chiến lược khác, chẳng hạn sticky partitioning để tận dụng batching. Không nên dựa vào việc các record không có key sẽ tình cờ vào cùng partition để bảo đảm thứ tự nghiệp vụ.

### 2.3. Thay đổi số partition có thể thay đổi vị trí của key

Với partitioner mặc định dựa trên hash của key và số partition, việc tăng số partition có thể làm một key được ánh xạ sang partition khác. Các sự kiện cũ của một đơn hàng có thể nằm ở partition cũ trong khi sự kiện mới đi vào partition mới.

Ví dụ minh họa:

```text
Trước khi tăng partition:
  hash(orderId) -> partition 1 trong 3 partition
  OrderCreated -> P1
  OrderPaid    -> P1

Sau khi tăng partition:
  hash(orderId) -> partition 4 trong 6 partition
  OrderShipped -> P4
```

Consumer không có một thứ tự offset chung để ghép `P1` với `P4`. Vì vậy, tăng partition là một thay đổi topology có thể ảnh hưởng đến ordering theo key. Trước khi mở rộng topic, hãy xác định yêu cầu thứ tự, cách partitioner ánh xạ key và chiến lược chuyển đổi dữ liệu.

Nếu cần giữ mapping ổn định lâu dài, có thể cân nhắc partitioner tùy chỉnh, topic/version mới hoặc một quy trình chuyển đổi có kiểm soát. Mỗi cách đều cần được thiết kế và kiểm thử; không nên mặc định rằng partition assignment của key sẽ bất biến sau mọi thay đổi.

### 2.4. Hot key và giới hạn song song

Gom mọi sự kiện của một thực thể vào một partition giúp giữ thứ tự, nhưng cũng giới hạn khả năng xử lý song song của thực thể đó. Một key có lưu lượng rất lớn có thể tạo **hot partition** trong khi các partition khác còn nhàn rỗi.

Ví dụ, nếu mọi giao dịch của một tài khoản trung tâm đều dùng cùng `accountId`, các sự kiện đó phải đi qua một partition để giữ thứ tự. Thêm consumer hoặc tăng số partition không làm cho cùng key được xử lý song song mà vẫn giữ nguyên một chuỗi thứ tự duy nhất.

Đây là một quyết định nghiệp vụ và kiến trúc: giữ thứ tự theo thực thể hay phân tán tải bằng cách chia nhỏ thực thể. Chỉ chia key thành nhiều phần khi nghiệp vụ cho phép các phần đó độc lập; nếu phải hợp nhất lại, cần có quy tắc đồng bộ rõ ràng.

## 3. Giữ thứ tự ở phía producer

Kafka chỉ có thể giữ thứ tự của những record được append vào partition. Producer phải gửi chúng theo đúng thứ tự mong muốn và xử lý retry đúng cách.

### 3.1. Gửi các sự kiện liên quan về cùng partition

Ví dụ producer dùng `orderId` làm key:

```java
ProducerRecord<String, String> created = new ProducerRecord<>(
    "orders", "ORD-101", "{\"eventType\":\"OrderCreated\"}"
);

ProducerRecord<String, String> paid = new ProducerRecord<>(
    "orders", "ORD-101", "{\"eventType\":\"OrderPaid\"}"
);

producer.send(created);
producer.send(paid);
```

Hai record có cùng key nên partitioner mặc định thường chọn cùng partition nếu topology và cấu hình không đổi. Khi đó thứ tự append của chúng trong partition sẽ là căn cứ để consumer đọc.

Tuy nhiên, hai lệnh `send()` không đồng nghĩa ứng dụng đã nhận xác nhận ghi thành công theo thứ tự. `send()` là bất đồng bộ; kết quả được thông báo qua callback hoặc khi ứng dụng chờ `Future`. Nếu ứng dụng cần biết một sự kiện đã được broker chấp nhận trước khi phát sinh sự kiện tiếp theo, cần điều khiển luồng gửi và xác nhận một cách rõ ràng.

### 3.2. Retry và nhiều request đang bay

Producer có thể gửi nhiều batch request mà chưa chờ tất cả phản hồi. Nếu một request thất bại tạm thời và được retry trong khi request sau đã thành công, một số cấu hình producer có thể làm record đến sau được append trước record được retry.

Kafka producer hỗ trợ idempotence để xử lý retry an toàn hơn và duy trì thứ tự trong các điều kiện cấu hình được hỗ trợ. Khi cần ordering, nên bật rõ `enable.idempotence=true` và bảo đảm các cấu hình liên quan tương thích. Với producer idempotent, `acks` phải là `all`, retry phải được bật và `max.in.flight.requests.per.connection` không vượt quá 5. Hãy kiểm tra tài liệu phiên bản Kafka client đang dùng vì cấu hình mặc định và cách xác thực cấu hình có thể khác nhau giữa các phiên bản.

Ví dụ cấu hình:

```java
Properties props = new Properties();
props.put("bootstrap.servers", "localhost:9092");
props.put("key.serializer", "org.apache.kafka.common.serialization.StringSerializer");
props.put("value.serializer", "org.apache.kafka.common.serialization.StringSerializer");

props.put("enable.idempotence", "true");
props.put("acks", "all");
props.put("retries", Integer.toString(Integer.MAX_VALUE));
props.put("max.in.flight.requests.per.connection", "5");
```

Idempotence giúp producer tránh tạo bản ghi trùng do retry trong phạm vi phiên producer và các bảo đảm Kafka hỗ trợ. Nó không tự biến mọi lần publish từ nhiều ứng dụng thành một chuỗi nghiệp vụ duy nhất, cũng không loại bỏ duplicate do ứng dụng chủ động gửi lại cùng một event như một lần gửi mới.

Nếu tắt idempotence, cần đặc biệt cẩn thận với retry và nhiều request in-flight. Khi retry được bật và `max.in.flight.requests.per.connection` lớn hơn 1, lỗi request có thể dẫn đến record bị đảo thứ tự. Đặt tối đa một request in-flight có thể tránh dạng đảo thứ tự này nhưng làm giảm thông lượng; bật idempotence thường là lựa chọn phù hợp hơn khi cần retry và ordering.

### 3.3. Nhiều thread hoặc nhiều producer cùng phát một key

Một producer Java có thể được nhiều thread sử dụng, nhưng điều đó không tạo ra một thứ tự nghiệp vụ rõ ràng giữa hai thread đang chạy đồng thời. Nếu thread A và thread B cùng gửi sự kiện cho `ORD-101`, thứ tự các lời gọi cạnh tranh có thể phụ thuộc lịch thực thi và thời điểm chúng đưa record vào producer.

Ngay cả khi mọi record có cùng key và vào cùng partition, Kafka chỉ ghi nhận thứ tự broker append được. Kafka không biết `OrderCreated` phải đứng trước `OrderPaid` dựa trên ý nghĩa của event type.

Nếu nhiều process hoặc nhiều producer cùng phát sự kiện cho một thực thể, hãy tạo một điểm điều phối thứ tự ở tầng ứng dụng. Một số cách thường dùng:

- Một service sở hữu việc phát event cho từng aggregate.
- Transactional outbox ghi event cùng transaction với thay đổi dữ liệu, sau đó publisher đọc theo sequence của aggregate.
- Gắn `aggregateVersion` hoặc sequence tăng dần vào event để consumer kiểm tra thứ tự.
- Dùng một hàng đợi/actor theo key để tuần tự hóa các thao tác gửi cùng thực thể.

Không nên dựa vào timestamp của máy producer để giải quyết race condition giữa nhiều nguồn phát.

## 4. Giữ thứ tự ở phía consumer

Ngay cả khi record được lưu đúng thứ tự trong partition, consumer vẫn có thể làm các tác vụ nghiệp vụ hoàn tất sai thứ tự nếu ứng dụng xử lý song song không có kiểm soát.

### 4.1. Consumer group phân công partition

Trong cùng một consumer group, tại một thời điểm một partition được gán cho tối đa một consumer member. Một consumer có thể nhận nhiều partition; nhiều consumer trong group có thể xử lý các partition khác nhau song song.

Ví dụ topic có bốn partition và group có hai consumer:

```text
Topic: orders

P0 -----> Consumer A
P1 -----> Consumer A
P2 -----> Consumer B
P3 -----> Consumer B
```

Consumer A có thể đọc tuần tự P0 và P1; Consumer B có thể đọc tuần tự P2 và P3. Không có thứ tự tổng thể giữa P0 và P2. Nếu một partition được chuyển sang consumer khác trong rebalance, ownership thay đổi nhưng log offset của partition vẫn là căn cứ thứ tự.

Tăng số consumer chỉ tăng song song đến giới hạn số partition được gán. Một group có nhiều consumer hơn số partition sẽ có consumer không được gán partition. Điều đó không làm một partition được nhiều consumer cùng xử lý song song trong group.

### 4.2. `poll()` có thứ tự nhưng worker pool có thể làm đảo thứ tự hoàn tất

Kafka consumer trả record theo partition và offset. Nhưng nếu ứng dụng gửi từng record vào một thread pool chung, record sau có thể hoàn thành trước record trước:

```text
Consumer poll:
  P0 offset 10: OrderCreated
  P0 offset 11: PaymentRequested
  P0 offset 12: OrderPaid

Worker pool:
  offset 10 -> xử lý chậm  -> hoàn tất sau cùng
  offset 11 -> xử lý nhanh -> hoàn tất trước
  offset 12 -> xử lý nhanh -> hoàn tất thứ hai
```

Log vẫn đúng thứ tự 10, 11, 12, nhưng side effect ở database hoặc service ngoài có thể xảy ra theo thứ tự 11, 12, 10. Đây là lỗi ở tầng xử lý ứng dụng, không phải lỗi ordering của Kafka.

Các lựa chọn triển khai:

- Xử lý tuần tự từng record trong consumer thread khi thông lượng cho phép.
- Dùng một hàng đợi/worker tuần tự riêng cho mỗi partition.
- Dùng executor theo key để các event cùng thực thể chạy tuần tự, còn key khác chạy song song.
- Nếu xử lý bất đồng bộ, theo dõi offset hoàn tất theo từng partition và chỉ commit đến vị trí liên tục cao nhất đã xử lý xong.

### 4.3. Commit offset sau khi xử lý

Commit offset là ghi nhận tiến độ đọc của consumer group. Thông thường, consumer commit **offset kế tiếp cần đọc**. Nếu ứng dụng commit offset 12 trong khi record ở offset 11 vẫn chưa xử lý xong, khi khởi động lại consumer có thể tiếp tục từ 12 và bỏ qua công việc chưa hoàn tất ở 11.

Khi xử lý tuần tự, cách đơn giản là chỉ commit sau khi record đã được xử lý thành công. Khi xử lý song song, phải theo dõi trạng thái hoàn tất riêng cho từng partition và chỉ commit qua một dãy offset liên tục đã hoàn thành.

Ví dụ:

```text
Partition 0 đã nhận:       10   11   12   13
Đã xử lý xong:             OK   --   OK   OK

Offset 11 chưa xong, nên commit không được vượt qua 11.
Các offset 12 và 13 hoàn tất trước không làm cho offset 11 tự hoàn tất.
```

Quy tắc này giúp tránh bỏ qua record chưa xử lý. Nếu consumer crash sau khi thực hiện side effect nhưng trước khi commit, record có thể được đọc lại; vì vậy side effect vẫn cần idempotent hoặc được phối hợp transaction phù hợp.

### 4.4. Retry có thể chặn hoặc làm thay đổi thứ tự xử lý

Giả sử offset 20 bị lỗi tạm thời, còn offset 21 và 22 đã sẵn sàng. Nếu ứng dụng đưa offset 20 sang một retry topic với thời gian chờ dài rồi tiếp tục xử lý partition gốc, offset 21 và 22 có thể được xử lý trước offset 20.

Có hai chiến lược phổ biến:

| Chiến lược | Cách hoạt động | Tác động đến ordering |
|---|---|---|
| Blocking retry | Tạm dừng partition hoặc không xử lý record tiếp theo cho đến khi record lỗi thành công hoặc có quyết định cuối cùng | Giữ chuỗi xử lý nhưng có thể làm giảm throughput của partition |
| Retry topic / delayed retry | Chuyển record lỗi sang luồng retry và tiếp tục đọc partition gốc | Record sau có thể vượt qua record đang retry |

Nếu thứ tự tuyệt đối theo aggregate là bắt buộc, blocking retry hoặc cơ chế retry theo key có thể phù hợp hơn. Nếu chấp nhận event đến sau được xử lý trước, retry topic có thể tăng khả năng tiếp tục xử lý nhưng consumer phải xử lý version, trạng thái chờ hoặc bù trừ nghiệp vụ.

Dead-letter topic (DLT/DLQ) cũng là một quyết định nghiệp vụ: chuyển record lỗi sang DLT và tiếp tục có nghĩa là luồng chính đã bỏ qua record đó. Cần có quy trình sửa lỗi và replay để khôi phục chuỗi sự kiện khi record lỗi được xử lý lại.

### 4.5. Rebalance và xử lý đang dang dở

Consumer group có thể rebalance khi consumer gia nhập, rời đi, timeout hoặc khi topology thay đổi. Partition được thu hồi từ member cũ và giao cho member mới. Nếu ứng dụng còn xử lý bất đồng bộ record thuộc partition vừa bị thu hồi, side effect có thể tiếp tục chạy trong lúc member mới bắt đầu đọc lại từ offset đã commit.

Để xử lý đúng:

- Theo dõi callback revoke/assign partition và dừng nhận việc mới từ partition bị thu hồi.
- Hoàn tất hoặc hủy có kiểm soát các tác vụ đang chạy trước khi mất quyền sở hữu.
- Commit offset đã xử lý an toàn trước khi partition được giao đi, theo chính sách commit của ứng dụng.
- Đảm bảo side effect idempotent vì record có thể được phát lại sau rebalance hoặc crash.
- Dùng cooperative rebalancing hoặc static membership khi phù hợp với topology, đồng thời vẫn thiết kế cho trường hợp partition chuyển owner.

Không nên coi rebalance là một sự kiện hiếm có thể bỏ qua; nó là một phần bình thường của vòng đời consumer group.

## 5. Timestamp, thứ tự nhân quả và thứ tự nghiệp vụ

### 5.1. Thứ tự append không đồng nghĩa thứ tự sự kiện xảy ra

Kafka giữ thứ tự record được append vào partition. Nó không tự xác định sự kiện nào xảy ra trước trong thế giới nghiệp vụ.

Ví dụ:

- Service A ghi `OrderCreated` vào database lúc 10:00 nhưng publisher bị chậm.
- Service B phát `PaymentReceived` lúc 10:01.
- Do hai producer độc lập, `PaymentReceived` có thể được append trước `OrderCreated` nếu cả hai cùng gửi vào một partition theo thứ tự đến broker.

Kafka sẽ giữ đúng thứ tự append mà broker nhận được. Nếu nghiệp vụ cần thứ tự theo transaction hoặc aggregate, producer phải cung cấp thứ tự đó bằng cơ chế domain như outbox, aggregate version hoặc một publisher có điều phối.

### 5.2. Dùng sequence/version để phát hiện sự kiện sai thứ tự

Một event có thể mang `aggregateVersion` hoặc `sequenceNumber` do ứng dụng cấp:

```json
{
  "eventId": "evt-102",
  "eventType": "OrderPaid",
  "orderId": "ORD-101",
  "aggregateVersion": 2,
  "occurredAt": "2026-11-20T10:01:00+07:00"
}
```

Consumer có thể so sánh version với trạng thái đã xử lý:

- Version bằng version hiện tại cộng một: có thể áp dụng tiếp.
- Version nhỏ hơn hoặc bằng version đã xử lý: có thể là duplicate hoặc event cũ; xử lý theo chính sách dedup.
- Version lớn hơn version mong đợi: có thể thiếu event trước; chờ, retry, lấy snapshot hoặc phát cảnh báo.

Version không thay thế offset. Version diễn tả thứ tự nghiệp vụ của aggregate; offset diễn tả vị trí trong log Kafka. Hai giá trị có thể hữu ích cùng lúc để điều tra lỗi.

### 5.3. Event-time processing

Một số bài toán phân tích cần xử lý theo thời điểm sự kiện xảy ra thay vì thứ tự record đến. Ví dụ tính tổng số giao dịch theo phút hoặc đo nhiệt độ theo thời điểm cảm biến ghi nhận.

Đây là bài toán event time. Hệ thống xử lý stream có thể dùng timestamp extractor, window và watermark để chấp nhận sự kiện đến trễ trong một khoảng thời gian. Watermark là ước lượng tiến độ event time; nó không làm thay đổi thứ tự offset trong Kafka partition.

Nếu ứng dụng cần sắp xếp event theo thời gian, hãy xác định giới hạn chờ sự kiện đến muộn và cách xử lý dữ liệu đến sau watermark. Không thể yêu cầu Kafka tự sắp xếp lại toàn bộ record theo timestamp trên nhiều partition.

## 6. Transactions và giới hạn của ordering

Kafka transactions hỗ trợ ghi nhiều record một cách nguyên tử trong Kafka và phối hợp commit offset khi thực hiện luồng consume-transform-produce. Consumer đặt `isolation.level=read_committed` chỉ đọc các record thuộc transaction đã commit, bỏ qua dữ liệu transaction bị abort.

Transactions giúp tránh để consumer tiếp theo nhìn thấy một phần output chưa hoàn chỉnh của một transaction. Tuy nhiên:

- Transaction không tạo thứ tự tổng thể giữa nhiều partition.
- Transaction không tự bảo đảm side effect trong database hoặc HTTP service bên ngoài được commit cùng Kafka.
- Consumer vẫn có thể xử lý song song sai thứ tự sau khi đọc record.
- Ứng dụng vẫn cần quản lý retry, rebalance, timeout transaction và idempotency ở ranh giới hệ thống ngoài Kafka.

Nếu dùng transaction để đọc từ một topic rồi ghi sang topic khác, hãy thiết kế key và partition đích sao cho các record cần thứ tự được ghi vào cùng partition đích. Transactional atomicity và per-partition ordering giải quyết hai vấn đề khác nhau.

## 7. Ví dụ thiết kế luồng đơn hàng có ordering

Giả sử một đơn hàng có chuỗi trạng thái:

```text
OrderCreated -> PaymentRequested -> OrderPaid -> OrderShipped
```

Yêu cầu là mọi sự kiện của cùng `orderId` phải được xử lý theo thứ tự, trong khi nhiều đơn hàng khác nhau có thể xử lý song song.

### 7.1. Producer

Producer dùng `orderId` làm key, bật idempotence và tránh nhiều publisher cạnh tranh phát event cho cùng một aggregate mà không có sequence/coordination.

```java
Properties props = new Properties();
props.put("bootstrap.servers", "localhost:9092");
props.put("key.serializer", "org.apache.kafka.common.serialization.StringSerializer");
props.put("value.serializer", "org.apache.kafka.common.serialization.StringSerializer");
props.put("enable.idempotence", "true");
props.put("acks", "all");
props.put("retries", Integer.toString(Integer.MAX_VALUE));
props.put("max.in.flight.requests.per.connection", "5");

KafkaProducer<String, String> producer = new KafkaProducer<>(props);

producer.send(new ProducerRecord<>(
    "orders", "ORD-101", "{\"eventType\":\"OrderCreated\",\"version\":1}"
));
producer.send(new ProducerRecord<>(
    "orders", "ORD-101", "{\"eventType\":\"PaymentRequested\",\"version\":2}"
));
producer.send(new ProducerRecord<>(
    "orders", "ORD-101", "{\"eventType\":\"OrderPaid\",\"version\":3}"
));

producer.flush();
producer.close();
```

Ví dụ minh họa cấu hình và key. Trong hệ thống thật, các event nên được tạo từ thay đổi domain có thứ tự, có `eventId` ổn định, version tăng dần và cơ chế publish đáng tin cậy như transactional outbox nếu database là nguồn sự thật.

### 7.2. Consumer xử lý tuần tự

Consumer đơn giản có thể xử lý trực tiếp trong vòng lặp poll để giữ thứ tự của từng partition:

```java
while (running) {
    ConsumerRecords<String, String> records = consumer.poll(Duration.ofMillis(500));

    for (ConsumerRecord<String, String> record : records) {
        try {
            processBusinessEvent(record.key(), record.value());
            // Commit sau khi xử lý thành công theo chính sách của ứng dụng.
        } catch (RetryableException ex) {
            // Dừng/giữ partition theo chiến lược retry để record sau không vượt qua.
            throw ex;
        }
    }

    consumer.commitSync();
}
```

Đây là đoạn mã minh họa luồng điều khiển; phần xử lý exception, pause/resume, shutdown và commit offset cần được hoàn thiện theo ứng dụng. Nếu dùng `commitSync()` sau toàn bộ batch, chỉ nên gọi khi mọi record trước vị trí commit đã xử lý thành công. Không commit vượt qua record còn dang dở.

Khi cần thông lượng cao hơn, có thể chạy nhiều partition song song nhưng vẫn giữ một hàng đợi tuần tự cho mỗi partition. Mỗi hàng đợi bảo đảm record cùng partition được hoàn tất theo thứ tự offset; các partition khác nhau chạy đồng thời.

### 7.3. Kiểm tra thứ tự bằng offset và version

Trong môi trường lab, hãy ghi log tối thiểu các trường:

```text
eventId, orderId, aggregateVersion,
topic, partition, offset, consumerId,
processingStartedAt, processingCompletedAt
```

Với cùng `orderId`, kiểm tra:

1. Các record có cùng partition trong giai đoạn topology không đổi.
2. Offset tăng theo thứ tự record được đọc.
3. `aggregateVersion` tăng theo quy tắc domain.
4. Thời điểm hoàn tất xử lý không đảo thứ tự nếu yêu cầu nghiệp vụ cần xử lý tuần tự.
5. Khi retry/rebalance, không có side effect trùng hoặc commit vượt qua record chưa hoàn tất.

## 8. Checklist thiết kế ordering

Trước khi chọn số partition, key và mô hình consumer, hãy trả lời:

| Câu hỏi | Vì sao cần trả lời? |
|---|---|
| Đơn vị nào cần được xử lý tuần tự: đơn hàng, tài khoản, thiết bị hay toàn hệ thống? | Xác định phạm vi ordering thực sự |
| Key nào đại diện cho đơn vị đó? | Gom record liên quan vào cùng partition |
| Có producer nào khác cũng phát event cho cùng key không? | Phát hiện race giữa nhiều nguồn phát |
| Producer có bật idempotence và cấu hình retry phù hợp không? | Tránh đảo thứ tự do retry trong các điều kiện được hỗ trợ |
| Số partition có thể tăng trong tương lai không? | Đánh giá thay đổi mapping key-partition |
| Consumer có xử lý song song record cùng partition không? | Tránh đảo thứ tự hoàn tất side effect |
| Offset chỉ commit sau khi xử lý liên tục thành công chưa? | Tránh bỏ qua record còn dang dở |
| Retry có chặn partition hay đưa record sang retry topic? | Xác định liệu record sau có thể vượt qua record lỗi |
| Rebalance có dừng tác vụ đang chạy và xử lý duplicate không? | Bảo đảm an toàn khi partition đổi owner |
| Có cần aggregate version/sequence không? | Phát hiện thiếu, trùng hoặc sai thứ tự nghiệp vụ |

## 9. Câu hỏi tự kiểm tra

1. Kafka bảo đảm thứ tự trong phạm vi nào? Vì sao không có thứ tự tổng thể giữa hai partition?
2. Offset và timestamp khác nhau như thế nào khi xác định thứ tự record?
3. Vì sao dùng `orderId` làm key giúp giữ thứ tự các sự kiện của một đơn hàng?
4. Điều gì có thể xảy ra với mapping key-partition khi tăng số partition của topic?
5. Vì sao nhiều thread cùng gửi event cho một key vẫn có thể không tạo ra thứ tự nghiệp vụ mong muốn?
6. Producer idempotence giải quyết vấn đề nào khi retry, và nó không giải quyết vấn đề nào?
7. Vì sao xử lý record song song trong worker pool có thể làm side effect hoàn tất sai thứ tự?
8. Khi offset 11 chưa xử lý xong nhưng offset 12 đã hoàn tất, consumer có được commit qua 12 không? Vì sao?
9. Retry topic có thể làm record sau vượt qua record lỗi như thế nào?
10. `aggregateVersion` bổ sung thông tin gì mà Kafka offset không cung cấp?

## Kết luận

Kafka giữ thứ tự record theo offset trong từng partition. Key giúp đưa các sự kiện của cùng một thực thể vào cùng partition, còn producer idempotence giúp duy trì thứ tự khi retry trong những điều kiện cấu hình phù hợp. Consumer phải xử lý tuần tự theo partition hoặc theo key, commit offset liên tục và thiết kế retry/rebalance có chủ đích. Khi hiểu rõ các ranh giới này, hệ thống có thể vừa xử lý song song giữa các thực thể vừa giữ đúng thứ tự nơi nghiệp vụ yêu cầu.
