# auto.offset.reset

## 1. Vai trò của auto.offset.reset

`auto.offset.reset` là cấu hình của Kafka consumer, quyết định consumer bắt đầu đọc ở đâu khi Kafka không có committed offset hợp lệ cho một partition. Trong Spring Kafka, cấu hình này thường được khai báo qua `spring.kafka.consumer.auto-offset-reset`.

Thiết lập này chỉ được dùng khi consumer cần xác định vị trí đọc ban đầu hoặc phải khôi phục vị trí đọc vì offset hiện tại không còn hợp lệ. Nó không phải lệnh xóa offset, không phải cơ chế commit offset và cũng không tự đưa một consumer group về đầu topic mỗi lần ứng dụng khởi động.

Các giá trị thường dùng:

- `earliest`: bắt đầu từ offset sớm nhất hiện còn được giữ trong partition.
- `latest`: bắt đầu từ cuối log tại thời điểm consumer cần xác định vị trí đọc.
- `none`: không tự chọn vị trí; phát sinh lỗi nếu không tìm được offset hợp lệ.

Một số Kafka client phiên bản mới còn hỗ trợ chính sách theo thời lượng như `by_duration:<duration>`. Tính năng và cú pháp phụ thuộc phiên bản Kafka client; cần kiểm tra tài liệu đúng phiên bản trước khi dùng.

Trong vận hành, lựa chọn này ảnh hưởng trực tiếp đến việc một consumer group có đọc lại dữ liệu cũ, bỏ qua phần dữ liệu lịch sử hay dừng lại để yêu cầu người vận hành xử lý offset.

## 2. Hiểu committed offset trước khi chọn chính sách

### 2.1. Offset là vị trí đọc tiếp theo

Mỗi partition có log riêng và offset tăng dần. Consumer group lưu committed offset riêng cho từng topic-partition trong Kafka, thường được quản lý qua topic nội bộ `__consumer_offsets`.

Committed offset biểu thị vị trí tiếp theo mà group sẽ đọc. Ví dụ, nếu group đã xử lý record offset 14 và commit offset 15, lần đọc tiếp theo bắt đầu từ offset 15.

~~~text
Partition orders-0

Offset:       10   11   12   13   14   15   16   17
Record:       A    B    C    D    E    F    G    H
                                      ^
                         committed offset = 15
                         record tiếp theo sẽ đọc: 15
~~~

Vì committed offset là vị trí tiếp theo, nó không phải offset của record cuối cùng đã xử lý. Sự khác biệt này quan trọng khi điều tra lag, đặt lại offset hoặc so sánh với log start/end offset.

### 2.2. Offset thuộc về consumer group

Kafka lưu tiến độ theo tổ hợp:

- Consumer group ID.
- Topic.
- Partition.

Hai group khác nhau có thể đọc cùng topic từ các vị trí khác nhau. Ví dụ, `billing-service` có thể đã đọc đến offset 500 của `orders-0`, trong khi `analytics-service` mới đọc đến offset 120.

Nếu đổi `group.id` của ứng dụng, Kafka xem đó là một group khác. Group mới thường chưa có committed offset nên `auto.offset.reset` được dùng để xác định vị trí bắt đầu. Đây là lý do một thay đổi group ID có thể khiến ứng dụng đọc lại nhiều dữ liệu hoặc bắt đầu từ cuối log.

Không nên dùng chung group ID cho hai luồng xử lý cần tiến độ độc lập. Ngược lại, các instance của cùng một dịch vụ thường dùng chung group ID để chia nhau partition và phối hợp tiến độ.

## 3. Khi nào auto.offset.reset được áp dụng?

Có ba tình huống chính.

### 3.1. Group chưa có committed offset

Khi consumer group lần đầu đọc một topic, hoặc group chưa từng commit offset cho một partition, Kafka không có vị trí đã lưu để tiếp tục. Consumer dùng `auto.offset.reset` để chọn vị trí khởi đầu.

Ví dụ:

- Một group mới đọc topic `orders`.
- Group cũ được đổi sang group ID mới.
- Ứng dụng bắt đầu đọc một topic mới.
- Một partition mới được thêm vào topic và group chưa có offset cho partition đó.

Nếu cấu hình `earliest`, consumer đọc từ dữ liệu sớm nhất còn được giữ. Nếu cấu hình `latest`, consumer bắt đầu ở cuối log và chờ record mới. Nếu cấu hình `none`, consumer báo lỗi vì không có offset để sử dụng.

### 3.2. Committed offset không còn nằm trong log

Giả sử group đã commit offset 20, nhưng topic có retention và broker đã xóa các record cũ, khiến log start offset của partition tăng lên 30. Consumer không thể tiếp tục đọc từ offset 20 vì dữ liệu ở vị trí đó đã không còn.

Kafka báo tình trạng offset ngoài phạm vi hiện có (offset out of range). Chính sách `auto.offset.reset` được dùng để xác định vị trí mới:

- `earliest`: chuyển đến log start offset hiện tại, ví dụ 30.
- `latest`: chuyển đến log end offset hiện tại.
- `none`: phát sinh lỗi để ứng dụng hoặc người vận hành quyết định.

Điều này có nghĩa `earliest` không bảo đảm đọc từ offset 0. Nếu retention đã xóa phần đầu log, offset sớm nhất có thể là 30, 500 hoặc một giá trị khác. Với topic compacted, log cũng có thể có khoảng trống offset do compaction loại bỏ record cũ.

### 3.3. Offset không còn hợp lệ sau thay đổi dữ liệu partition

Một số tình huống bất thường như truncation hoặc thay đổi trạng thái log có thể khiến committed offset vượt quá log end offset hiện tại. Khi consumer không thể sử dụng offset đã lưu, chính sách reset cũng có thể được áp dụng.

Không nên xem việc reset tự động là cách sửa mọi sự cố dữ liệu. Nếu offset bất ngờ vượt ngoài phạm vi, cần kiểm tra trạng thái leader, replica, log truncation, retention và lịch sử vận hành trước khi chấp nhận vị trí mới.

### 3.4. Khi nào cấu hình không được áp dụng?

Nếu group đã có committed offset hợp lệ, consumer tiếp tục từ offset đó. Ví dụ group đã commit offset 150 thì thay đổi `auto.offset.reset` từ `latest` sang `earliest` không làm consumer quay về đầu topic; nó vẫn tiếp tục từ offset 150.

Nếu ứng dụng gọi `seek()` hoặc một cơ chế điều khiển vị trí đọc tường minh, vị trí được chỉ định có thể thay thế quyết định tự động. Cấu hình reset chủ yếu là chính sách dự phòng khi consumer không có vị trí ban đầu hợp lệ.

## 4. So sánh earliest, latest và none

| Giá trị | Vị trí bắt đầu | Tác động thường gặp | Trường hợp phù hợp |
|---|---|---|---|
| `earliest` | Offset sớm nhất còn được giữ | Có thể đọc lại dữ liệu lịch sử và tạo tải lớn lúc khởi động | Consumer mới cần xây dựng trạng thái từ lịch sử |
| `latest` | Cuối log tại thời điểm reset | Bỏ qua phần dữ liệu lịch sử hiện có, chỉ nhận dữ liệu mới sau vị trí bắt đầu | Luồng chỉ quan tâm sự kiện mới phát sinh |
| `none` | Không tự chọn vị trí | Consumer báo lỗi nếu thiếu offset hợp lệ | Muốn phát hiện cấu hình hoặc provisioning offset bị thiếu |

### 4.1. earliest: ưu tiên không bỏ qua lịch sử còn lưu

`earliest` yêu cầu consumer bắt đầu từ vị trí sớm nhất mà broker còn giữ trong partition. Đây thường là lựa chọn phù hợp cho một consumer group mới cần đọc lại toàn bộ dữ liệu lịch sử còn tồn tại, ví dụ xây dựng read model hoặc đồng bộ dữ liệu từ event log.

Tuy nhiên, `earliest` không phải cơ chế replay mỗi lần restart. Nếu group đã commit offset, consumer vẫn tiếp tục từ offset đó. Nó chỉ bắt đầu từ đầu log còn lưu khi không có offset hợp lệ.

Rủi ro vận hành là group mới có thể phải xử lý một lượng lớn record. Nếu downstream có giới hạn throughput, consumer lag có thể tăng cao và ảnh hưởng hệ thống. Cần ước lượng lượng dữ liệu, tốc độ xử lý, retention và năng lực database trước khi tạo group mới với `earliest`.

### 4.2. latest: chỉ nhận dữ liệu sau vị trí hiện tại

`latest` đặt vị trí ban đầu ở cuối log tại thời điểm reset. Các record đã tồn tại trước vị trí đó không được group mới đọc lại.

Đây là lựa chọn phù hợp với một số luồng chỉ quan tâm sự kiện mới, chẳng hạn một consumer nhận telemetry mới phát sinh mà không cần xử lý lịch sử. Nhưng với nghiệp vụ thanh toán, đơn hàng hoặc cập nhật trạng thái cần đầy đủ dữ liệu, dùng `latest` cho group chưa có offset có thể làm mất cơ hội xử lý các event cũ còn lưu.

`latest` cũng không có nghĩa consumer luôn nhảy đến cuối log. Sau khi group đã có committed offset hợp lệ, consumer tiếp tục từ offset đã commit và đọc các record tiếp theo như bình thường.

Khi group nhận partition mới hoặc bị mất offset, `latest` có thể khiến phần record đang tồn tại trên partition đó không được đọc. Cần đánh giá kỹ khi mở rộng số partition của topic hoặc thay đổi group ID.

### 4.3. none: yêu cầu vị trí đọc phải được cung cấp

`none` yêu cầu Kafka không tự chọn offset nếu không có committed offset hợp lệ. Consumer sẽ phát sinh lỗi, thường là `NoOffsetForPartitionException` trong trường hợp không có offset ban đầu.

Chính sách này hữu ích khi quy trình triển khai yêu cầu group phải được khởi tạo hoặc đặt offset trước khi chạy. Nó giúp phát hiện sớm một group ID mới bị cấu hình nhầm thay vì âm thầm đọc từ đầu hoặc bỏ qua dữ liệu cũ.

Đổi lại, nếu vận hành thêm partition mà chưa có offset cho partition mới, hoặc offset hết hạn do group ngừng hoạt động lâu, consumer có thể dừng với lỗi. Cần có quy trình provisioning offset và giám sát lỗi khởi tạo.

## 5. Ví dụ minh họa cách chọn offset

Giả sử partition `orders-0` có log start offset là 40 và log end offset là 100. Group `billing-service` chưa có committed offset cho partition này.

~~~text
Log start                                                   Log end
    40  41  42  43  44  ...  96  97  98  99
     |                               |
     +-- earliest                    +-- latest
~~~

| Cấu hình | Vị trí consumer bắt đầu | Record có thể đọc tiếp |
|---|---:|---|
| `earliest` | 40 | 40, 41, 42, ... |
| `latest` | 100 | Record mới được ghi từ vị trí 100 trở đi |
| `none` | Không có vị trí tự động | Phát sinh lỗi vì group chưa có offset |

Nếu group đã commit offset 75, cả ba cấu hình đều không làm thay đổi vị trí đọc hợp lệ đó. Consumer tiếp tục từ 75.

Nếu retention xóa record đến mức log start offset tăng lên 80 trong khi group vẫn giữ committed offset 75, offset 75 không còn khả dụng. Lúc này:

- `earliest` chuyển đến 80.
- `latest` chuyển đến log end hiện tại.
- `none` báo lỗi.

Đây là điểm cốt lõi khi đọc cấu hình: chính sách chỉ can thiệp khi cần khởi tạo hoặc khôi phục vị trí đọc, không thay thế committed offset hợp lệ.

## 6. Cấu hình trong Spring Boot và Spring Kafka

### 6.1. Khai báo bằng application.yml

Ví dụ consumer group cần xử lý dữ liệu lịch sử còn lưu:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: billing-service
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.events
    listener:
      ack-mode: record
~~~

Thuộc tính Spring Boot `auto-offset-reset` được ánh xạ sang cấu hình Kafka client `auto.offset.reset`. Giá trị có thể được khai báo là `earliest`, `latest` hoặc `none` tùy chính sách của ứng dụng.

Trong ví dụ:

- `group-id` xác định namespace lưu tiến độ đọc.
- `auto-offset-reset` quyết định cách khởi tạo khi group thiếu offset hợp lệ.
- `enable-auto-commit: false` để Spring listener container quản lý commit theo acknowledgment mode.
- `ack-mode: record` yêu cầu commit tiến độ theo từng record sau khi listener xử lý thành công.

Hai thuộc tính `auto-offset-reset` và `enable-auto-commit` giải quyết hai vấn đề khác nhau. Một thuộc tính chọn vị trí ban đầu; thuộc tính còn lại kiểm soát cách offset được commit trong quá trình xử lý.

### 6.2. Khai báo bằng properties

Nếu dùng file `application.properties`:

~~~properties
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.consumer.group-id=billing-service
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.listener.ack-mode=record
~~~

Nếu cấu hình trực tiếp Kafka consumer factory, key của Kafka client là `auto.offset.reset`:

~~~java
Map<String, Object> consumerProperties = new HashMap<>();

consumerProperties.put(
    ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
consumerProperties.put(
    ConsumerConfig.GROUP_ID_CONFIG,
    "billing-service"
);
consumerProperties.put(
    ConsumerConfig.AUTO_OFFSET_RESET_CONFIG,
    "earliest"
);
consumerProperties.put(
    ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG,
    false
);

ConsumerFactory<String, OrderCreated> consumerFactory =
    new DefaultKafkaConsumerFactory<>(consumerProperties);
~~~

`ConsumerConfig.AUTO_OFFSET_RESET_CONFIG` giúp tránh gõ sai tên property khi cấu hình Java. Cần bảo đảm consumer factory thực sự được listener container sử dụng; tạo một factory nhưng không gắn nó vào container sẽ không thay đổi hành vi consumer.

### 6.3. Ghi đè group ID ở @KafkaListener

Một listener có thể khai báo group ID trực tiếp:

~~~java
@KafkaListener(
    topics = "orders",
    groupId = "billing-service"
)
public void onOrderCreated(OrderCreated event) {
    billingService.process(event);
}
~~~

Khi annotation chỉ định `groupId`, listener sử dụng group đó theo cấu hình annotation. Nếu nhiều listener có group ID khác nhau, mỗi group có committed offset độc lập và `auto.offset.reset` được áp dụng riêng cho từng group-partition khi cần.

Trước khi đổi group ID, cần xác định đó là thay đổi chủ đích hay lỗi cấu hình. Một lỗi đánh máy trong group ID có thể tạo group mới và khiến `earliest` đọc lại lịch sử hoặc `latest` bỏ qua phần lịch sử còn lưu.

## 7. auto.offset.reset khác gì với commit offset?

Hai cơ chế thường bị nhầm lẫn:

| Cơ chế | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| `auto.offset.reset` | Nếu không có vị trí đọc hợp lệ, nên bắt đầu ở đâu? | `earliest` hoặc `latest` |
| Commit offset | Group đã xử lý đến đâu và lần tiếp theo đọc từ đâu? | Commit offset 101 để lần sau đọc từ 101 |
| `enable.auto.commit` | Kafka client có tự commit offset theo chu kỳ hay không? | `false` để container điều phối |
| Acknowledgment mode | Spring listener container commit theo record, batch hay thao tác acknowledge thủ công? | `RECORD`, `BATCH`, `MANUAL` |

Ví dụ listener xử lý record offset 25 rồi commit offset 26. Khi ứng dụng khởi động lại, consumer đọc tiếp từ 26 dù cấu hình `auto.offset.reset=earliest`. Nó không quay lại offset 0 hoặc log start offset.

Nếu listener xử lý thành công side effect nhưng ứng dụng dừng trước khi commit, record có thể được giao lại. Đó là vấn đề delivery semantics và idempotency, không phải lỗi của `auto.offset.reset`.

Ngược lại, nếu offset đã commit bị retention xóa khỏi log, consumer không thể tiếp tục từ vị trí cũ. Khi đó reset policy mới quyết định cách khôi phục.

## 8. Quan hệ với retention và log compaction

### 8.1. Retention theo thời gian hoặc dung lượng

Kafka có thể xóa segment cũ theo `retention.ms` hoặc `retention.bytes`. Khi record đầu log bị xóa, log start offset tăng lên. Consumer group đang bị lag lâu có thể giữ committed offset thấp hơn log start offset.

Ví dụ:

~~~text
Trước retention:
log start = 0
committed offset = 20
log end = 100

Sau retention:
log start = 50
committed offset = 20
log end = 150

Offset 20 không còn trong log.
~~~

Nếu consumer quay lại sau khi retention đã xóa offset 20, `earliest` sẽ đưa nó đến 50, không thể khôi phục record 20 đến 49 từ topic đó. `latest` sẽ bỏ qua phần log còn lại đến vị trí cuối. `none` dừng để yêu cầu quyết định thủ công.

Do đó, retention phải dài hơn khoảng thời gian tối đa mà consumer có thể ngừng hoạt động hoặc bị lag nếu nghiệp vụ cần bảo đảm đọc hết dữ liệu.

### 8.2. Log compaction

Với topic có `cleanup.policy=compact`, Kafka giữ lại giá trị mới nhất theo key trong log compacted và có thể xóa record cũ hơn. Offset vẫn tăng theo lịch sử append; offset sớm nhất còn khả dụng không nhất thiết là 0 và các offset có thể không liên tục.

`earliest` trên topic compacted có nghĩa bắt đầu từ offset sớm nhất còn tồn tại, không có nghĩa khôi phục mọi phiên bản lịch sử của mỗi key. Nếu cần replay toàn bộ lịch sử sự kiện, topic compacted có thể không đáp ứng yêu cầu đó.

### 8.3. Offset retention của consumer group

Ngoài retention record của topic, broker còn có chính sách giữ committed offset của group. Nếu một group không hoạt động trong thời gian dài và offset của nó hết hạn theo cấu hình broker như `offsets.retention.minutes`, lần khởi động sau có thể không còn offset đã commit.

Khi đó `auto.offset.reset` có thể được áp dụng dù group ID vẫn giống trước đây. Điều này đặc biệt quan trọng với consumer chạy theo lịch, job batch hoặc dịch vụ có thể ngừng nhiều tuần.

Cần phân biệt:

- Topic retention quyết định record nào còn tồn tại để consumer đọc.
- Offset retention quyết định broker còn nhớ tiến độ đã commit của group hay không.

Cả hai đều có thể ảnh hưởng vị trí đọc sau khi consumer quay lại.

## 9. Những tình huống vận hành quan trọng

| Tình huống | Tác động của auto.offset.reset | Cần chú ý |
|---|---|---|
| Group mới | Chọn vị trí đầu tiên cho partition | `earliest` replay lịch sử còn lưu; `latest` bỏ qua lịch sử |
| Đổi group ID | Group mới không có offset cũ | Kiểm tra thay đổi có chủ đích không |
| Thêm partition | Group chưa có offset cho partition mới | Chính sách reset áp dụng cho partition mới |
| Consumer lag vượt retention | Committed offset có thể nằm trước log start | `earliest` chỉ đọc từ dữ liệu còn lại |
| Offset group hết hạn | Group có thể mất committed offset | Reset policy được dùng lại |
| Partition bị truncation | Offset có thể vượt log end | Điều tra replica và trạng thái log |
| Dùng `none` | Consumer báo lỗi khi thiếu offset | Cần quy trình khởi tạo offset rõ ràng |

### 9.1. Thêm partition cho topic

Giả sử topic `orders` ban đầu có 3 partition và consumer group đã commit offset cho cả ba. Sau đó topic được mở rộng thành 5 partition. Hai partition mới chưa có committed offset của group.

Với `earliest`, consumer có thể đọc các record đã tồn tại trên hai partition mới từ log start. Với `latest`, consumer bắt đầu từ cuối log của hai partition mới. Với `none`, việc thiếu offset có thể làm consumer phát sinh lỗi.

Đây là lý do thay đổi partition count cần đi kèm kế hoạch consumer. Nếu dữ liệu mới được ghi vào partition mới ngay sau khi mở rộng, chính sách reset sẽ quyết định group có đọc những record đã có trước khi nó bắt đầu tiêu thụ partition hay không.

### 9.2. Thay đổi group ID khi triển khai

Thay đổi group ID thường tạo một tiến độ đọc hoàn toàn mới. Nếu vô tình đổi tên group trong cấu hình môi trường, ứng dụng có thể:

- Đọc lại nhiều event nếu reset là `earliest`.
- Bỏ qua dữ liệu lịch sử nếu reset là `latest`.
- Không khởi động được nếu reset là `none`.

Khi đổi group ID, phải xác định mục đích là tạo một consumer độc lập hay tiếp tục tiến độ của group cũ. Nếu muốn tiếp tục, cần giữ group ID hoặc chủ động chuyển offset bằng quy trình quản trị phù hợp.

## 10. Đặt lại offset chủ động khác với auto.offset.reset

Nếu group đã có committed offset hợp lệ và người vận hành muốn replay, đổi `auto.offset.reset` không có tác dụng. Cần thực hiện thao tác reset offset có chủ đích cho group.

Kafka cung cấp công cụ `kafka-consumer-groups.sh` để xem và reset offset. Ví dụ xem tiến độ:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --describe
~~~

Ví dụ xem trước việc đưa group về đầu topic `orders`:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Sau khi kiểm tra phạm vi và xác nhận đây là thay đổi có chủ đích, có thể thực thi bằng `--execute` thay cho `--dry-run`:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --execute
~~~

Trước khi reset:

1. Xác nhận đúng cluster, group ID, topic và partition.
2. Dừng hoặc bảo đảm group không có consumer active đang xử lý.
3. Chạy `--dry-run` để xem offset dự kiến.
4. Ước lượng tác động replay đến database và downstream.
5. Lưu lại offset hiện tại để có thể đối chiếu hoặc khôi phục.
6. Chỉ thực thi sau khi đã xác định rõ phạm vi dữ liệu cần đọc lại.

Các công cụ Kafka có thể yêu cầu group không hoạt động để reset offset. Cú pháp tùy phiên bản Kafka; kiểm tra trợ giúp của binary đang triển khai. Với thao tác tự động hóa, có thể dùng AdminClient để thay đổi consumer group offsets, nhưng vẫn phải quản lý trạng thái group và phạm vi partition cẩn thận.

Reset offset chủ động là thao tác quản trị tiến độ. `auto.offset.reset` chỉ là chính sách dự phòng khi consumer không có offset hợp lệ.

## 11. Rủi ro dữ liệu khi chọn sai chính sách

### 11.1. Dùng latest cho consumer cần lịch sử

Một group mới dùng `latest` sẽ bắt đầu ở cuối log. Nếu topic đang chứa các đơn hàng chưa được billing xử lý, group có thể bỏ qua các event đó và chỉ nhận event mới. Hệ thống downstream có thể thiếu dữ liệu mà không có lỗi xử lý record, vì consumer đã chọn vị trí bắt đầu hợp lệ theo cấu hình.

Với luồng nghiệp vụ phải xử lý đầy đủ event, `earliest` hoặc một quy trình khởi tạo offset có kiểm soát thường phù hợp hơn. Cần đánh giá khả năng replay và idempotency để tránh tạo side effect trùng.

### 11.2. Dùng earliest cho consumer chỉ cần dữ liệu mới

Một consumer telemetry mới có thể chỉ cần dữ liệu phát sinh sau thời điểm triển khai. Nếu dùng `earliest`, consumer sẽ đọc toàn bộ dữ liệu còn lưu, có thể gây tải lớn và tăng lag trong khi lịch sử không có giá trị cho use case đó.

Trong trường hợp này `latest` có thể phù hợp, miễn là nghiệp vụ chấp nhận bỏ qua record lịch sử trước vị trí khởi tạo.

### 11.3. Dùng none mà không có quy trình provisioning

`none` giúp phát hiện group thiếu offset, nhưng nếu quy trình triển khai không khởi tạo offset trước thì consumer có thể dừng ngay khi nhận partition. Điều này thường xuất hiện khi group ID thay đổi, offset hết hạn hoặc topic được thêm partition.

Chọn `none` cần đi cùng bước provision/reset offset và cảnh báo rõ ràng khi gặp `NoOffsetForPartitionException`.

### 11.4. Replay có thể tạo duplicate

Khi `earliest` được dùng cho group mới hoặc sau khi offset mất, record cũ có thể được xử lý lại. Nếu listener đã từng tạo side effect ở hệ thống khác bằng một group ID trước đó, việc tạo group mới không tự ngăn duplicate ở nghiệp vụ.

Dùng event ID ổn định, unique constraint, inbox table hoặc thao tác upsert idempotent để kiểm soát side effect. Không dựa vào offset của group như một khóa idempotency toàn cục, vì offset chỉ có ý nghĩa trong partition và group.

## 12. Theo dõi và chẩn đoán vị trí đọc

Để xác định vì sao consumer bắt đầu ở một vị trí cụ thể, theo dõi các thông tin:

| Thông tin | Ý nghĩa |
|---|---|
| Group ID | Namespace lưu tiến độ |
| Topic và partition | Phạm vi offset đang xem |
| Committed offset | Vị trí tiếp theo group đã lưu |
| Log start offset | Offset sớm nhất broker còn giữ |
| Log end offset | Vị trí cuối log, tức vị trí tiếp theo sau record mới nhất |
| Consumer position | Vị trí consumer hiện đang đọc trong phiên |
| Consumer lag | Khoảng cách giữa log end và tiến độ consumer theo cách hệ thống giám sát tính toán |

Có thể dùng lệnh describe để xem trạng thái group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group billing-service \
  --describe
~~~

Khi cần điều tra:

- Nếu committed offset tồn tại và hợp lệ, kiểm tra vì sao consumer chưa tiến lên; không thay đổi reset policy trước khi hiểu nguyên nhân.
- Nếu committed offset thấp hơn log start, kiểm tra retention và thời gian group bị dừng.
- Nếu không có committed offset, kiểm tra group ID, offset retention, partition mới và reset policy.
- Nếu committed offset vượt log end, kiểm tra log truncation, leader election và lịch sử thay đổi cụm.
- Nếu group dùng `none` và không có offset, kiểm tra quy trình provision hoặc thao tác reset.

Consumer lag thường được tính từ log end offset trừ đi committed offset. Khi offset bị reset, lag có thể thay đổi đột ngột. Đó có thể là hành vi đúng theo chính sách, nhưng cần log và cảnh báo để phân biệt với việc consumer đột ngột mất tiến độ.

Không nên chỉ xem lag tổng. Một partition có thể bị mất offset hoặc bị nghẽn trong khi các partition khác vẫn hoạt động bình thường. Luôn kiểm tra theo partition.

## 13. Kiểm thử auto.offset.reset

Có thể kiểm thử chính sách reset trên một topic thử nghiệm và group ID riêng để không tác động tiến độ của group đang chạy.

Một kịch bản cơ bản:

1. Tạo topic thử nghiệm có một partition.
2. Gửi một số record với key/value dễ nhận diện.
3. Khởi chạy consumer bằng group ID mới và cấu hình `earliest`.
4. Xác nhận consumer đọc record cũ còn lưu.
5. Khởi chạy consumer khác với group ID mới và cấu hình `latest`.
6. Xác nhận consumer không đọc phần lịch sử đã có và nhận record được gửi sau khi nó bắt đầu.
7. Thử `none` với một group ID chưa có offset và xác nhận consumer báo lỗi thiếu offset.
8. Kiểm tra committed offset bằng công cụ consumer group sau khi xử lý.

Để kiểm thử tình huống retention, cần cấu hình retention ngắn trên topic thử nghiệm, ghi record, commit offset rồi chờ broker xóa segment phù hợp. Sau đó khởi chạy lại consumer và quan sát hành vi khi committed offset không còn nằm trong log. Thời điểm xóa phụ thuộc segment roll và cơ chế retention, vì vậy không nên giả định record biến mất chính xác ngay khi hết thời gian cấu hình.

Khi kiểm thử group đã có offset hợp lệ, đổi cấu hình từ `latest` sang `earliest` rồi restart. Consumer phải tiếp tục từ committed offset hiện tại; đây là phép thử quan trọng để chứng minh cấu hình không tự reset group mỗi lần khởi động.

## 14. Nguyên tắc lựa chọn trong production

- Xác định consumer có cần đọc lịch sử hay chỉ nhận event mới trước khi chọn policy.
- Giữ group ID ổn định nếu muốn tiếp tục tiến độ đã commit.
- Dùng `earliest` khi group mới phải đọc dữ liệu lịch sử còn lưu và downstream chịu được tải replay.
- Dùng `latest` khi bỏ qua lịch sử là hành vi được nghiệp vụ chấp nhận.
- Dùng `none` khi offset phải được provision rõ ràng và muốn fail fast nếu thiếu.
- Kiểm tra retention của topic và retention của committed offset để tránh group quay lại sau thời gian dài mà mất tiến độ.
- Khi thêm partition, đánh giá cách reset policy áp dụng cho partition mới.
- Không dùng thay đổi `auto.offset.reset` để reset một group đang có offset hợp lệ; dùng quy trình quản trị offset có dry-run.
- Chuẩn bị idempotency cho listener nếu replay có thể lặp side effect.
- Theo dõi committed offset, log start/end, consumer lag và lỗi offset out of range theo từng partition.

`auto.offset.reset` là chính sách quyết định cách consumer khởi tạo hoặc khôi phục vị trí đọc khi không thể dùng committed offset. Chọn đúng giá trị giúp kiểm soát việc đọc lịch sử, tránh bỏ qua event quan trọng và làm cho hành vi khởi động của consumer có thể dự đoán được.
