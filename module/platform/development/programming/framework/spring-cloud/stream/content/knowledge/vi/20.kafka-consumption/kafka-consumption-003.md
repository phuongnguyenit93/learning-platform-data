# startOffset, offset đã lưu và chính sách khi chưa có offset

Kafka lưu message trong topic theo partition và theo dõi vị trí tiêu thụ bằng offset. Mỗi consumer group có tiến độ riêng trên từng partition. Khi ứng dụng Spring Cloud Stream khởi động, Kafka binder phải quyết định consumer bắt đầu từ vị trí nào: tiếp tục từ offset đã commit, đọc từ đầu phần dữ liệu còn lưu hay bỏ qua dữ liệu cũ để nhận message mới.

Ba khái niệm thường bị nhầm lẫn là `startOffset`, committed offset và `resetOffsets`. `startOffset` chọn vị trí khởi đầu khi group chưa có offset hợp lệ; committed offset thể hiện tiến độ đã lưu của group; `resetOffsets` yêu cầu binder bỏ qua tiến độ hiện có và áp dụng lại chính sách bắt đầu. Hiểu đúng thứ tự ưu tiên này giúp tránh đọc lại toàn bộ topic ngoài ý muốn hoặc bỏ qua các message cần xử lý.

Bài học tập trung vào Kafka message-channel binder của Spring Cloud Stream, cách cấu hình group và offset, hành vi khi chưa có offset, offset hết hạn, replay và kiểm thử sau khi reset.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích offset là vị trí đọc theo từng Kafka partition.
- Phân biệt committed offset với vị trí hiện tại của consumer.
- Hiểu `startOffset: earliest` và `startOffset: latest`.
- Giải thích sự khác nhau giữa consumer có group tường minh và anonymous group.
- Cấu hình `startOffset` và `resetOffsets` đúng binding của Kafka binder.
- Nhận biết khi nào `auto.offset.reset` của Kafka client được áp dụng.
- Xử lý tình huống offset chưa tồn tại, hết hạn hoặc nằm ngoài dữ liệu còn lưu.
- Chọn cách replay an toàn bằng group mới, reset có kiểm soát hoặc rebalance listener.
- Kiểm thử hành vi khởi động lần đầu và khởi động lại bằng Kafka broker thực tế.

## 1. Offset là gì?

Kafka lưu record trong từng partition. Mỗi record trong partition có một số offset tăng dần. Offset là vị trí của record trong partition, không phải số thứ tự toàn cục của topic.

Ví dụ topic `orders` có ba partition:

| Partition | Các offset minh họa |
|---|---|
| orders-0 | 0, 1, 2, 3, 4, ... |
| orders-1 | 0, 1, 2, 3, ... |
| orders-2 | 0, 1, 2, 3, 4, 5, ... |

Consumer group có thể đang đọc partition 0 ở vị trí 4, partition 1 ở vị trí 2 và partition 2 ở vị trí 5. Vì vậy, không có một offset duy nhất đại diện cho toàn topic.

Trong Kafka, committed offset thường là vị trí tiếp theo mà consumer cần đọc. Nếu consumer xử lý record có offset 12 và commit offset 13, lần khởi động sau sẽ tiếp tục từ record offset 13. Cách diễn giải này giúp tránh nhầm lẫn giữa offset của record cuối đã xử lý và giá trị offset được lưu.

### Current position và committed offset

- **Current position:** vị trí hiện tại của consumer trong lúc đang chạy. Consumer có thể đã poll và xử lý một số record nhưng chưa commit.
- **Committed offset:** vị trí tiến độ được lưu bền vững cho consumer group. Sau restart hoặc rebalance, consumer có thể tiếp tục từ vị trí này.
- **Log end offset:** vị trí cuối của dữ liệu đã ghi trong partition; nó cho biết điểm cuối hiện tại của log, không phải vị trí consumer đã xử lý.
- **Log start offset:** vị trí đầu tiên còn được giữ trong partition; dữ liệu trước vị trí này có thể đã bị retention hoặc compaction loại bỏ.

~~~mermaid
flowchart LR
    A["Log start offset"] --> B["Committed offset"]
    B --> C["Current consumer position"]
    C --> D["Log end offset"]
    style B stroke-width:3px
~~~

Committed offset có thể thấp hơn current position khi consumer đang xử lý nhưng chưa commit. Nếu process dừng trước commit, một số record đã xử lý có thể được đọc lại. Nếu commit quá sớm trước khi xử lý xong, record có thể bị bỏ qua sau restart.

## 2. Committed offset được lưu theo consumer group

Kafka lưu tiến độ của group trong nội bộ cluster, thường qua topic nội bộ `__consumer_offsets`. Mỗi group có offset riêng cho từng topic partition. Hai group khác nhau có thể đọc cùng topic độc lập và có tiến độ khác nhau.

Ví dụ:

| Consumer group | orders-0 | orders-1 |
|---|---:|---:|
| order-processor | 120 | 95 |
| order-audit | 80 | 140 |
| order-reporting | 150 | 150 |

Nếu `order-processor` khởi động lại, nó tiếp tục từ committed offset của chính group đó. Việc `order-audit` đã đọc tới offset cao hơn không làm thay đổi tiến độ của `order-processor`.

Trong Spring Cloud Stream, group được khai báo ở binding:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
~~~

Binding có group tường minh tạo một consumer group có danh tính ổn định. Nếu không khai báo `group`, binder tạo anonymous consumer group. Anonymous group phù hợp với một số trường hợp tiêu thụ độc lập, nhưng không nên dùng khi cần một danh tính group ổn định để theo dõi tiến độ lâu dài hoặc triển khai nhiều instance cùng chia tải.

### Vì sao group ảnh hưởng đến vị trí bắt đầu?

Khi group chưa có committed offset, Kafka cần một chính sách để quyết định đọc từ đâu. Spring Cloud Stream Kafka binder cung cấp `startOffset` và có mặc định khác nhau giữa binding có group tường minh và anonymous binding:

- Binding có `group` tường minh mặc định bắt đầu từ `earliest`.
- Binding anonymous mặc định bắt đầu từ `latest`.

Có thể ghi đè mặc định này bằng `startOffset`. Khi group đã có committed offset hợp lệ, offset đã lưu được ưu tiên và `startOffset` không kéo consumer về đầu topic.

## 3. startOffset: earliest và latest

Kafka binder hỗ trợ hai giá trị cho `startOffset`:

- `earliest`: bắt đầu từ offset sớm nhất còn có thể đọc trong mỗi partition được gán.
- `latest`: bắt đầu từ điểm cuối hiện tại của partition và nhận các record được ghi sau vị trí đó.

Ví dụ cấu hình đọc từ đầu phần dữ liệu còn lưu:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              startOffset: earliest
~~~

Ví dụ cấu hình chỉ nhận message mới khi group chưa có offset hợp lệ:

~~~yaml
spring:
  cloud:
    function:
      definition: monitorEvents
    stream:
      bindings:
        monitorEvents-in-0:
          destination: system-events
          group: live-monitor
      kafka:
        bindings:
          monitorEvents-in-0:
            consumer:
              startOffset: latest
~~~

### earliest không có nghĩa là offset 0 luôn tồn tại

`earliest` là vị trí sớm nhất còn có trong log tại thời điểm consumer cần bắt đầu. Nếu topic đã áp dụng retention và xóa record cũ, consumer không thể đọc lại phần dữ liệu đã bị xóa. Với topic compacted, Kafka có thể loại bỏ các bản ghi cũ của cùng key và giữ lại giá trị mới nhất theo chính sách compaction. Vì vậy, `earliest` không đồng nghĩa với toàn bộ lịch sử từng được ghi.

### latest có thể bỏ qua dữ liệu đã tồn tại

Nếu group mới được cấu hình `latest`, consumer đặt vị trí bắt đầu tại cuối log hiện tại. Những record đã tồn tại trước thời điểm chọn vị trí đó sẽ không được đọc bởi group mới. Đây là lựa chọn phù hợp cho giám sát sự kiện phát sinh trong lúc ứng dụng chạy, nhưng không phù hợp nếu consumer cần xử lý toàn bộ dữ liệu lịch sử.

## 4. Thứ tự ưu tiên: committed offset và startOffset

Khi ứng dụng khởi động, Kafka binder xác định vị trí theo group và trạng thái offset:

1. Nếu group có committed offset hợp lệ cho partition, consumer tiếp tục từ offset đã lưu.
2. Nếu group chưa có offset cho partition, binder áp dụng chính sách bắt đầu: `startOffset` hoặc mặc định tương ứng.
3. Nếu offset đã lưu không còn nằm trong phạm vi log hiện có, Kafka cần xử lý tình huống offset out of range theo chính sách reset của consumer/binder.
4. Nếu `resetOffsets: true`, binder bỏ qua committed offset hiện có và áp dụng `startOffset` cho các partition được gán theo semantics của binder.

Bảng tóm tắt:

| Trạng thái group/partition | resetOffsets | Vị trí bắt đầu |
|---|---|---|
| Có committed offset hợp lệ | false | Tiếp tục từ offset đã commit |
| Chưa có committed offset | false | Theo startOffset hoặc mặc định |
| Offset đã hết hạn/mất | false | Theo chính sách reset khi không có offset hợp lệ |
| Có committed offset hợp lệ | true | Bỏ qua offset cũ, áp dụng startOffset |
| Group mới, chưa từng đọc | true | Áp dụng startOffset như lần đầu |

Đây là điểm quan trọng nhất: chỉ đặt `startOffset: earliest` không có nghĩa consumer luôn đọc lại từ đầu mỗi lần khởi động. Nếu group có offset đã commit, binder tiếp tục từ offset đó trừ khi có yêu cầu reset.

## 5. Cấu hình resetOffsets

`resetOffsets` là thuộc tính riêng của Kafka binder. Mặc định là `false`. Khi đặt `true`, binder bỏ qua các committed offset hiện có và áp dụng vị trí `startOffset`, tương tự như thể binding chưa từng tiêu thụ topic.

Ví dụ yêu cầu đọc lại từ đầu mỗi lần binding khởi động:

~~~yaml
spring:
  cloud:
    function:
      definition: rebuildOrderIndex
    stream:
      bindings:
        rebuildOrderIndex-in-0:
          destination: orders
          group: order-index-rebuild
      kafka:
        bindings:
          rebuildOrderIndex-in-0:
            consumer:
              startOffset: earliest
              resetOffsets: true
~~~

Ví dụ bắt đầu ở cuối log khi ứng dụng được khởi động:

~~~yaml
spring:
  cloud:
    function:
      definition: liveEventMonitor
    stream:
      bindings:
        liveEventMonitor-in-0:
          destination: system-events
          group: live-event-monitor
      kafka:
        bindings:
          liveEventMonitor-in-0:
            consumer:
              startOffset: latest
              resetOffsets: true
~~~

Với `resetOffsets: true`, mỗi lần binding khởi động, committed offset đang có bị bỏ qua. Do đó, cấu hình `earliest` có thể khiến ứng dụng đọc lại nhiều dữ liệu và lặp tác dụng phụ; cấu hình `latest` có thể bỏ qua dữ liệu đang tồn tại. Chỉ dùng khi đã có kế hoạch rõ ràng về replay, idempotency và ảnh hưởng tới consumer group.

Khi rebalance xảy ra sau lần gán partition ban đầu, binder thực hiện seek theo chính sách reset trên những partition mới được gán mà chưa được gán trong lần đầu. Hành vi này cần được tính đến khi scale instance hoặc thay đổi assignment.

### Không kết hợp resetOffsets với KafkaBindingRebalanceListener

Nếu ứng dụng cung cấp bean `KafkaBindingRebalanceListener` để tự điều khiển seek offset, không đặt `resetOffsets: true`. Hai cơ chế cùng điều khiển vị trí đọc và binder không cho phép kết hợp cấu hình này. Với listener, hãy giữ `resetOffsets: false` và thực hiện seek theo logic của listener.

## 6. Chính sách khi chưa có offset: auto.offset.reset

Kafka client có thuộc tính native `auto.offset.reset` để quyết định hành vi khi không tìm thấy offset hợp lệ hoặc offset đã nằm ngoài phạm vi log. Các giá trị thường gặp:

| Giá trị Kafka client | Hành vi |
|---|---|
| `earliest` | Đọc từ offset sớm nhất còn có |
| `latest` | Đọc từ cuối log, chờ record mới |
| `none` | Ném lỗi nếu không tìm thấy offset hợp lệ |

Spring Cloud Stream Kafka binder cung cấp thuộc tính cấp binder `startOffset` với hai giá trị `earliest` và `latest`. Binder mặc định chọn `earliest` cho group tường minh và `latest` cho anonymous group. Khi cấu hình `startOffset`, dùng property binder thay vì mặc định suy đoán từ Kafka client.

Nếu cần hành vi fail-fast tương ứng `auto.offset.reset=none`, cần xem xét cấu hình Kafka consumer native và cách binder thiết lập `startOffset` trong phiên bản đang dùng. Không cấu hình đồng thời nhiều thuộc tính reset với giả định rằng chúng luôn có cùng độ ưu tiên. Kiểm thử group mới, offset hết hạn và offset out of range để xác nhận hành vi thực tế.

Ví dụ cấu hình Kafka consumer native:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              configuration:
                auto.offset.reset: none
~~~

Đoạn cấu hình minh họa cách truyền thuộc tính Kafka client qua binder. Nếu đồng thời cấu hình `startOffset`, giá trị do binder áp dụng có thể chi phối hành vi khi khởi tạo; hãy tránh đặt hai chính sách mâu thuẫn. Với ứng dụng cần fail-fast, xác minh cấu hình sau khi binder tạo consumer và kiểm thử trên đúng phiên bản.

## 7. Anonymous group và group tường minh

Khi không khai báo `group`, Spring Cloud Stream Kafka binder tạo anonymous consumer group. Binder tạo group ID nội bộ để consumer hoạt động; ứng dụng không có một tên group ổn định được quản lý trực tiếp như trường hợp group tường minh.

Đặc điểm thường gặp:

- Anonymous group mặc định dùng `latest` khi không có offset.
- Các ứng dụng độc lập có thể nhận dữ liệu riêng thay vì chia tải cùng một group có tên.
- Không nên dựa vào anonymous group để duy trì tiến độ tiêu thụ lâu dài giữa các lần triển khai.
- Khi cần chia partition giữa nhiều instance, khai báo cùng một group tường minh cho các instance của cùng ứng dụng.

Ví dụ group tường minh:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
~~~

Ba replica của ứng dụng cùng dùng binding này và cùng group `inventory` sẽ tham gia cùng consumer group. Kafka phân phối partition cho các member. Nếu dùng group khác, consumer group đó có tiến độ riêng và có thể đọc lại topic độc lập.

Không nhầm số replica với số group. Scale số instance trong cùng group không tạo thêm một bản sao xử lý độc lập của toàn topic; các instance chia nhau partition. Muốn một ứng dụng khác đọc toàn bộ event độc lập, ứng dụng đó cần group riêng.

## 8. Offset có thể hết hạn hoặc không còn hợp lệ

Committed offset không nhất thiết tồn tại mãi mãi. Kafka broker có chính sách retention cho offset group. Với các broker Kafka hiện đại và cấu hình mặc định phổ biến, offset của group không còn member có thể hết hạn sau khoảng bảy ngày; giá trị cụ thể phụ thuộc `offsets.retention.minutes` và cấu hình broker.

Ngoài hết hạn, offset đã commit có thể không còn nằm trong phạm vi log do topic retention hoặc thao tác quản trị. Khi đó, consumer cần chính sách reset để chọn vị trí mới.

Các tình huống cần chú ý:

- Consumer group không có member trong thời gian dài.
- Topic retention xóa các record cũ.
- Topic bị xóa rồi tạo lại với cùng tên.
- Partition bị thay đổi hoặc dữ liệu được tái tạo.
- Consumer lưu offset quá cũ so với log start offset hiện tại.

Khi không còn committed offset hợp lệ, `startOffset` hoặc `auto.offset.reset` lại trở nên quan trọng. Hãy quan sát log của consumer và broker để phân biệt group mới với offset hết hạn hoặc out of range.

## 9. Ví dụ cấu hình ba chính sách khởi đầu

### Group nghiệp vụ cần xử lý lịch sử

Dùng group tường minh và `earliest` để lần đầu đọc từ dữ liệu còn lưu:

~~~yaml
spring:
  cloud:
    function:
      definition: orderProjection
    stream:
      bindings:
        orderProjection-in-0:
          destination: orders
          group: order-projection
      kafka:
        bindings:
          orderProjection-in-0:
            consumer:
              startOffset: earliest
              resetOffsets: false
~~~

Sau lần xử lý đầu tiên, Kafka lưu committed offset. Khi ứng dụng khởi động lại, nó tiếp tục từ offset đã commit thay vì quay lại đầu topic.

### Consumer chỉ quan tâm dữ liệu mới

Dùng `latest` cho group mới:

~~~yaml
spring:
  cloud:
    function:
      definition: liveDashboard
    stream:
      bindings:
        liveDashboard-in-0:
          destination: system-events
          group: live-dashboard
      kafka:
        bindings:
          liveDashboard-in-0:
            consumer:
              startOffset: latest
              resetOffsets: false
~~~

Group mới bắt đầu từ cuối log. Khi đã có committed offset, restart tiếp tục từ offset đã lưu.

### Chủ động đọc lại từ đầu

Dùng `resetOffsets: true` cùng `earliest` khi đã chuẩn bị cho replay:

~~~yaml
spring:
  cloud:
    function:
      definition: rebuildOrderProjection
    stream:
      bindings:
        rebuildOrderProjection-in-0:
          destination: orders
          group: order-projection-rebuild
      kafka:
        bindings:
          rebuildOrderProjection-in-0:
            consumer:
              startOffset: earliest
              resetOffsets: true
~~~

Nên dùng group riêng cho một lần dựng lại projection để không làm thay đổi tiến độ của consumer production đang chạy. Khi projection đã dựng xong, có thể chuyển traffic hoặc áp dụng chiến lược đồng bộ phù hợp.

## 10. Seek tới offset tùy ý

`startOffset` chỉ chọn `earliest` hoặc `latest`; nó không chọn được một số offset cụ thể như 1200. Nếu cần bắt đầu từ một offset tùy ý hoặc từ timestamp, Kafka binder hỗ trợ `KafkaBindingRebalanceListener` để ứng dụng thực hiện seek khi partition được gán.

Listener được gọi trong quá trình assignment/rebalance và có thể truy cập consumer cùng danh sách partition được gán. Ứng dụng có thể gọi API seek phù hợp cho từng partition sau khi xác định vị trí mong muốn.

Nguyên tắc cấu hình:

- Cung cấp một bean triển khai `KafkaBindingRebalanceListener`.
- Đặt `resetOffsets: false`.
- Chỉ seek trên các partition phù hợp, thường là assignment ban đầu hoặc những partition mới được giao.
- Xác định rõ hành vi khi partition được gán lại sau rebalance.
- Không seek tùy tiện về phía trước nếu chưa xác minh message trước đó đã được xử lý.
- Ghi log partition, offset trước và sau seek để có thể kiểm toán.

Không thực hiện seek đồng thời với cơ chế `resetOffsets: true`. Nếu cần replay một phạm vi cụ thể, cân nhắc dùng consumer group riêng để thử trước, tránh thay đổi tiến độ của group production.

## 11. Phân biệt Kafka message-channel binder và Kafka Streams binder

Spring Cloud Stream có hai cách tích hợp Kafka phổ biến: message-channel binder và Kafka Streams binder. Không nên áp dụng máy móc cùng một chính sách offset cho cả hai.

Với Kafka message-channel binder:

- Consumer binding dùng `startOffset` và `resetOffsets`.
- Explicit group mặc định `earliest`, anonymous group mặc định `latest`.
- `resetOffsets: true` có thể bỏ qua committed offset theo semantics binder.
- `KafkaBindingRebalanceListener` có thể điều khiển seek tùy ý.

Với Kafka Streams binder:

- `startOffset` được cấu hình theo từng binding Kafka Streams.
- Mặc định thường là `earliest` cho consumer mới.
- Có thể đặt `latest` theo binding nếu ứng dụng chỉ cần dữ liệu mới.
- `resetOffsets` của message-channel binder không có tác dụng với Kafka Streams binder.

Ví dụ cấu hình startOffset cho Kafka Streams binding:

~~~yaml
spring:
  cloud:
    function:
      definition: analyzeOrders
    stream:
      kafka:
        streams:
          bindings:
            analyzeOrders-in-0:
              consumer:
                startOffset: latest
~~~

Kafka Streams còn có state store, changelog và processing guarantee riêng. Nếu reset input offset nhưng giữ state store cũ, trạng thái kết quả có thể không tương ứng với dữ liệu đã đọc lại. Khi cần tái dựng state, phải lập kế hoạch cho cả input offsets và state stores; không chỉ thay `startOffset`.

## 12. Kiểm tra offset và tiến độ consumer

Để hiểu consumer đang ở đâu, cần quan sát cả committed offset, log end offset và consumer lag. Lag thường được tính từ log end offset trừ committed offset theo từng partition, với cách hiển thị cụ thể phụ thuộc công cụ.

Các lệnh Kafka CLI hữu ích:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-processor
~~~

Lệnh trên hiển thị partition assignment, current offset, log end offset và lag của group.

Để kiểm tra group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
~~~

Để xem topic có bao nhiêu partition:

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders
~~~

Không nên dùng lệnh reset offset trực tiếp trên group production khi consumer đang hoạt động mà không có kế hoạch phối hợp. Trước khi thay đổi, ghi lại offset hiện tại, dừng hoặc điều phối consumer, xác định phạm vi partition và chuẩn bị cách khôi phục.

## 13. Replay bằng group mới hay reset group hiện tại?

Hai cách có tác động khác nhau:

| Cách replay | Ưu điểm | Rủi ro / lưu ý |
|---|---|---|
| Tạo group mới với earliest | Không thay đổi offset của group production | Tốn thêm tài nguyên; side effect vẫn cần idempotency |
| Reset group hiện tại về earliest | Có thể tái xử lý bằng cùng group | Consumer production có thể đọc lại lượng lớn dữ liệu |
| Dùng resetOffsets=true | Binder áp dụng startOffset thay cho offset đã commit | Có thể lặp hoặc bỏ qua message ngoài dự kiến mỗi lần khởi động |
| Dùng rebalance listener seek offset cụ thể | Kiểm soát được vị trí bắt đầu | Cần xử lý assignment/rebalance cẩn thận |

Nếu mục tiêu là dựng lại một projection, group mới thường dễ cô lập hơn. Nếu mục tiêu là khôi phục chính group production, cần dừng consumer hoặc điều phối thay đổi offset có kế hoạch, xác nhận idempotency và theo dõi lag sau khi chạy lại.

Replay không chỉ là quyết định kỹ thuật về offset. Nó có thể gửi lại email, tạo lại giao dịch hoặc cập nhật dữ liệu lần nữa. Consumer cần idempotent và có quy trình kiểm soát tác dụng phụ.

## 14. Kiểm thử startOffset và committed offset

Một bộ kiểm thử cần bao phủ nhiều lần khởi động với cùng group:

### Kiểm thử lần đầu với explicit group

1. Tạo topic có một số record đã tồn tại.
2. Cấu hình group tường minh và `startOffset: earliest`.
3. Khởi động consumer.
4. Xác minh consumer đọc từ offset sớm nhất còn lưu.
5. Chờ xử lý thành công và xác minh committed offset được ghi.

### Kiểm thử restart với committed offset

1. Dừng consumer sau khi một phần dữ liệu được xử lý và commit.
2. Ghi thêm record mới.
3. Khởi động lại cùng group.
4. Xác minh consumer tiếp tục từ committed offset.
5. Xác minh `startOffset: earliest` không làm consumer quay lại đầu topic khi offset đã lưu còn hợp lệ.

### Kiểm thử resetOffsets

1. Tạo committed offset ở giữa topic.
2. Cấu hình `startOffset: earliest` và `resetOffsets: true`.
3. Khởi động binding theo kế hoạch thử nghiệm.
4. Xác minh binder bỏ qua offset cũ và seek về đầu phần dữ liệu còn lưu.
5. Xác minh consumer có thể đọc lại record đã xử lý; kiểm tra idempotency.

### Kiểm thử offset không còn hợp lệ

- Để group không hoạt động đủ lâu theo offset retention đã cấu hình hoặc mô phỏng group mới.
- Thay đổi retention của topic trong môi trường kiểm thử để offset cũ nằm ngoài log.
- Xác minh consumer áp dụng chính sách reset dự kiến.
- Ghi lại log và committed offset mới.

Không chờ bảy ngày trong test tự động. Có thể dùng broker test với cấu hình retention nhỏ hoặc tạo group mới để kiểm tra đường đi không có offset.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Consumer không đọc message cũ | Group mới dùng `latest` hoặc anonymous group | Khai báo group và `startOffset: earliest` |
| Đổi startOffset nhưng consumer vẫn tiếp tục từ offset cũ | Group có committed offset hợp lệ | Dùng group mới hoặc resetOffsets có kiểm soát |
| Consumer đọc lại toàn bộ topic sau restart | `resetOffsets: true` hoặc group mới | Kiểm tra reset policy và group ID |
| Consumer bỏ qua record đã tồn tại | Group mới dùng `latest` | Dùng `earliest` nếu cần lịch sử |
| Consumer bắt đầu từ offset không tồn tại | Topic retention hoặc offset out of range | Kiểm tra log start offset và reset policy |
| Anonymous consumer không giữ tiến độ như mong đợi | Group ID do binder tạo không ổn định theo mục tiêu vận hành | Dùng group tường minh |
| Replay làm side effect lặp | Consumer không idempotent | Dùng event ID, inbox hoặc idempotency key |
| ResetOffsets không hoạt động với Kafka Streams | Đang dùng Kafka Streams binder | Cấu hình startOffset theo Kafka Streams binding |
| Seek tùy ý xung đột reset | Cấu hình listener cùng resetOffsets=true | Đặt resetOffsets=false và quản lý seek trong listener |
| Consumer lag tăng sau khi đổi offset | Consumer đang đọc lại lượng lớn dữ liệu | Theo dõi throughput, scale có kiểm soát và kiểm tra tác động replay |

Khi chẩn đoán, kiểm tra lần lượt group ID, committed offset từng partition, startOffset, resetOffsets, log start/end offset và binder đang dùng. Không suy ra vị trí đọc chỉ từ YAML mà không kiểm tra offset thực tế trên broker.

## 16. Bài thực hành: xây dựng consumer có chính sách offset rõ ràng

Tạo consumer `processOrder` đọc topic `orders`:

1. Khai báo function `processOrder` nhận sự kiện đơn hàng.
2. Cấu hình destination `orders` và group `order-processor`.
3. Đặt `startOffset: earliest` cho lần khởi động đầu.
4. Gửi một số message trước khi consumer chạy.
5. Khởi động consumer và xác minh đọc dữ liệu đã có.
6. Dừng consumer sau khi một phần record được commit.
7. Gửi thêm message rồi khởi động lại cùng group.
8. Xác minh consumer tiếp tục từ committed offset, không quay lại đầu topic.
9. Tạo group mới `order-rebuild` và cấu hình `earliest`; xác minh group mới đọc lịch sử độc lập.
10. Thử `latest` với group mới và xác minh record cũ không được đọc.
11. Trong môi trường test, bật `resetOffsets: true` và xác minh offset hiện có bị bỏ qua.
12. Dùng `kafka-consumer-groups --describe` để đối chiếu current offset, log end offset và lag.
13. Kiểm tra duplicate side effect khi replay và xác minh consumer idempotent.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Group identity | Group tường minh ổn định |
| Initial position | earliest/latest đúng yêu cầu |
| Stored offset | Restart tiếp tục từ committed offset |
| resetOffsets | Chỉ bật khi có kế hoạch reset/replay |
| Offset retention | Biết hành vi khi offset hết hạn |
| Out-of-range | Có chính sách khi offset không còn trong log |
| Replay | Phạm vi và group replay được kiểm soát |
| Idempotency | Xử lý lại không lặp side effect |
| Observability | Đọc được offset và lag theo partition |
| Binder type | Phân biệt message-channel và Kafka Streams binder |

## Kết luận

`startOffset` quyết định vị trí khởi đầu khi consumer group chưa có committed offset hợp lệ; offset đã lưu của group được ưu tiên khi còn hợp lệ. Với Kafka message-channel binder, group tường minh mặc định dùng `earliest`, anonymous group mặc định dùng `latest`. `resetOffsets: true` yêu cầu binder bỏ qua committed offset và áp dụng lại startOffset, vì vậy có thể gây replay hoặc bỏ qua dữ liệu.

Hãy khai báo group ổn định cho consumer nghiệp vụ, chọn earliest/latest theo yêu cầu, chỉ reset khi đã chuẩn bị idempotency và kế hoạch vận hành, đồng thời kiểm tra offset/lag thực tế trên từng partition. Nếu cần seek tới offset tùy ý, dùng KafkaBindingRebalanceListener với resetOffsets tắt. Phân biệt message-channel binder với Kafka Streams binder để không áp dụng sai cấu hình.

## Tài liệu tham khảo

- [Spring Cloud Stream Kafka Binder – Resetting Offsets](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_overview.html)
- [Spring Cloud Stream Kafka Binder – Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/configuration-options.html)
- [Apache Kafka – Consumer Configs: auto.offset.reset](https://kafka.apache.org/documentation/#consumerconfigs_auto.offset.reset)
- [Apache Kafka – Consumer Groups](https://kafka.apache.org/documentation/#intro_consumers)

