# Mục tiêu sẵn sàng, bền vững và khôi phục

Trong vận hành Spring Kafka, độ tin cậy cần được xác định bằng kết quả mà hệ thống cung cấp cho nghiệp vụ. Một cụm Kafka có thể vẫn hoạt động nhưng ứng dụng không gửi được bản ghi, consumer có thể vẫn kết nối nhưng độ trễ xử lý tăng liên tục, hoặc dữ liệu đã được broker xác nhận nhưng chưa được hệ thống đích xử lý an toàn. Vì vậy, cần đặt mục tiêu cho toàn bộ luồng dữ liệu từ producer, qua Kafka, đến consumer và dịch vụ phía sau.

Ba mục tiêu nền tảng là **sẵn sàng (availability)**, **bền vững dữ liệu (durability)** và **khả năng khôi phục (recoverability)**. Chúng liên quan chặt chẽ nhưng đo lường những thuộc tính khác nhau:

- Sẵn sàng cho biết hệ thống có thể tiếp nhận và xử lý công việc trong giới hạn thời gian đã cam kết hay không.
- Bền vững cho biết bản ghi đã được xác nhận có còn tồn tại sau những lỗi nằm trong mô hình bảo vệ đã chọn hay không.
- Khả năng khôi phục cho biết đội vận hành có thể đưa dịch vụ và dữ liệu trở lại trạng thái phục vụ nghiệp vụ trong thời gian cho phép hay không.

Không có một cấu hình Spring Kafka duy nhất bảo đảm cả ba mục tiêu. Kết quả phụ thuộc vào topology của Kafka, cấu hình producer và consumer, cách xử lý lỗi của ứng dụng, năng lực hạ tầng, quy trình triển khai và runbook khi có sự cố.

## 1. Xác định mục tiêu ở cấp luồng nghiệp vụ

### 1.1. Sẵn sàng

Một luồng Kafka được xem là sẵn sàng khi producer có thể gửi bản ghi hợp lệ, broker có thể tiếp nhận và lưu bản ghi theo chính sách đã định, và consumer có thể tiếp tục xử lý dữ liệu. Chỉ kiểm tra trạng thái tiến trình hoặc kết nối TCP là chưa đủ. Ví dụ, health check của ứng dụng có thể trả về `UP` trong khi producer liên tục timeout hoặc consumer lag đã vượt ngưỡng nghiệp vụ.

Nên phân biệt ít nhất ba góc nhìn:

1. **Sẵn sàng của nền tảng:** broker có thể bầu leader, phân vùng cần thiết có leader, replica được đồng bộ và các listener đáp ứng yêu cầu kết nối.
2. **Sẵn sàng của ứng dụng:** producer gửi được bản ghi, consumer tham gia group, xử lý được thông điệp và ghi nhận kết quả.
3. **Sẵn sàng của nghiệp vụ:** sự kiện được tiếp nhận và tạo ra kết quả trước hạn nghiệp vụ. Một consumer vẫn chạy nhưng xử lý chậm hơn thời hạn giao dịch có thể được xem là không sẵn sàng theo SLO nghiệp vụ.

Sẵn sàng cũng cần gắn với độ trễ. Một API gửi sự kiện trả về thành công sau vài phút không đáp ứng cùng mục tiêu với API trả về trong vài trăm mili giây. Do đó, ngoài tỷ lệ thành công, hãy theo dõi latency ở các phân vị p50, p95 và p99, cùng tuổi của bản ghi chưa được xử lý.

### 1.2. Bền vững dữ liệu

Bền vững dữ liệu mô tả khả năng giữ lại bản ghi sau khi producer nhận xác nhận. Cần định nghĩa rõ xác nhận đó có ý nghĩa gì. Với Kafka, kết quả phụ thuộc vào:

- Số replica của partition (`replication.factor`).
- Số replica phải ở trạng thái đồng bộ trước khi broker chấp nhận ghi (`min.insync.replicas`).
- Mức xác nhận mà producer yêu cầu (`acks`).
- Cách Kafka bầu leader khi replica mất đồng bộ.
- Vị trí đặt replica, chính sách lưu trữ và tình trạng đĩa của broker.

Ví dụ, producer dùng `acks=all`, topic có replication factor là 3 và broker yêu cầu tối thiểu 2 replica trong ISR. Khi đó, một lần ghi chỉ được xác nhận nếu tất cả replica đang nằm trong ISR đã nhận bản ghi và số replica trong ISR không thấp hơn mức tối thiểu. Cấu hình này giúp chống chịu một số lỗi broker đơn lẻ, nhưng không có nghĩa dữ liệu đã được ghi đồng bộ tới mọi broker trong cụm hoặc đã được sao lưu sang một vùng địa lý khác.

### 1.3. Khả năng khôi phục

Khả năng khôi phục là năng lực đưa hệ thống trở lại trạng thái phục vụ sau lỗi, đồng thời kiểm soát lượng dữ liệu có thể bị mất hoặc phải xử lý lại. Hai chỉ số thường dùng là:

- **RTO (Recovery Time Objective):** khoảng thời gian tối đa được phép để khôi phục dịch vụ sau sự cố.
- **RPO (Recovery Point Objective):** khoảng dữ liệu tối đa có thể mất, tính theo thời gian hoặc theo số sự kiện.

RTO và RPO phải gắn với một kịch bản lỗi cụ thể. RTO cho việc thay thế một broker có thể khác RTO khi mất cả availability zone hoặc mất toàn bộ cluster. RPO của việc mất một replica trong cụm không giống RPO khi mất cả vùng triển khai.

Replication trong cùng cluster giúp duy trì bản sao khi broker gặp sự cố, nhưng không thay thế backup. Nếu một thao tác xóa topic, lỗi ứng dụng hoặc dữ liệu sai được ghi vào tất cả replica, replication có thể sao chép chính thay đổi đó. Muốn khôi phục dữ liệu đã bị xóa hoặc hỏng, cần có nguồn phục hồi độc lập như bản sao cluster, bản xuất dữ liệu, hệ thống lưu trữ gốc hoặc khả năng phát lại sự kiện từ upstream.

## 2. Chuyển mục tiêu thành SLI, SLO và cảnh báo

**SLI (Service Level Indicator)** là chỉ số đo thực tế; **SLO (Service Level Objective)** là mục tiêu nội bộ cho chỉ số đó; **SLA (Service Level Agreement)** là cam kết được thỏa thuận với bên sử dụng dịch vụ. Không nên công bố SLA trước khi đã đo được SLI ổn định và xác định rõ cách tính.

| Mục tiêu | SLI nên theo dõi | Câu hỏi vận hành |
|---|---|---|
| Producer sẵn sàng | Tỷ lệ gửi thành công, số lỗi gửi, timeout, p95/p99 thời gian xác nhận | Ứng dụng có gửi được sự kiện trong thời gian cam kết không? |
| Kafka sẵn sàng | Số partition không có leader, offline partition, under-replicated partition, thời gian phản hồi request | Cụm có thể nhận và phục vụ đọc/ghi theo chính sách không? |
| Consumer sẵn sàng | Tỷ lệ xử lý thành công, processing time, commit failure, số lần rebalance | Consumer có xử lý đều và duy trì được tiến độ không? |
| Luồng dữ liệu đúng hạn | Consumer lag, tuổi của bản ghi cũ nhất chưa xử lý, thời gian từ publish đến xử lý | Sự kiện có đến hệ thống đích trước hạn nghiệp vụ không? |
| Bền vững | ISR size, ISR shrink, under-replicated partition, lỗi ghi, dung lượng và retention | Bản ghi đã xác nhận có được bảo vệ theo failure model không? |
| Khôi phục | RTO thực tế, RPO thực tế, thời gian drain backlog, số bản ghi cần replay hoặc đối soát | Sau sự cố, dịch vụ và dữ liệu trở lại bình thường trong bao lâu? |

Tỷ lệ thành công cần có mẫu số rõ ràng. Ví dụ, không tính các request sai định dạng do client gửi vào như lỗi hạ tầng Kafka nếu SLO chỉ đo khả năng tiếp nhận request hợp lệ. Ngược lại, nếu mục tiêu là trải nghiệm đầu cuối, cần đo cả các lỗi từ dịch vụ downstream khiến sự kiện chưa hoàn tất nghiệp vụ.

Một bộ mục tiêu khởi điểm có thể gồm tỷ lệ gửi thành công theo tháng, p95 thời gian xác nhận, giới hạn tuổi tối đa của sự kiện chưa xử lý, RTO cho lỗi broker và RTO cho lỗi toàn vùng. Các giá trị cụ thể phải được xác định từ yêu cầu nghiệp vụ, tải thực tế, năng lực hạ tầng và kết quả diễn tập. Chẳng hạn, mục tiêu `99,9%` sẵn sàng không có ý nghĩa nếu chưa thống nhất phép đo, cửa sổ thời gian, các trường hợp loại trừ và cách tính thời gian gián đoạn.

Nên đặt ngưỡng cảnh báo dựa trên xu hướng và tác động. Consumer lag tăng liên tục dù vẫn dưới ngưỡng tuyệt đối có thể báo hiệu consumer đang mất khả năng theo kịp tốc độ phát sinh dữ liệu. Một partition under-replicated trong thời gian ngắn khi rolling restart có thể là trạng thái chuyển tiếp; nếu kéo dài hoặc tăng trên nhiều partition, đó là tín hiệu cần xử lý. Cảnh báo cần chỉ ra dịch vụ, cluster, topic, consumer group, mức độ ảnh hưởng và runbook tương ứng.

## 3. Thiết kế theo failure model

Trước khi chọn cấu hình, hãy liệt kê những lỗi hệ thống cần tiếp tục chịu được:

| Kịch bản lỗi | Câu hỏi cần trả lời |
|---|---|
| Producer process dừng hoặc mất mạng | Producer có thể kết nối lại và gửi lại mà không tạo tác động trùng ngoài ý muốn không? |
| Một broker mất đột ngột | Partition có leader khác không? Replica còn lại có đủ ISR để tiếp tục nhận ghi không? |
| Một ổ đĩa hoặc một máy chủ lỗi | Replica khác có đủ dữ liệu và tài nguyên để phục vụ không? |
| Một availability zone mất kết nối | Replica có được phân bố qua các zone độc lập không? Cụm còn đủ ISR không? |
| Consumer dừng giữa lúc xử lý | Offset đã commit ở thời điểm nào? Sự kiện có thể được gửi lại an toàn không? |
| Downstream chậm hoặc ngừng hoạt động | Backlog có được giữ lại không? Consumer có cơ chế backpressure và retry phù hợp không? |
| Ghi nhầm hoặc xóa nhầm dữ liệu | Có bản sao phục hồi độc lập hoặc nguồn để phát lại không? |
| Mất cả cluster hoặc vùng | Quy trình chuyển sang cluster dự phòng có được diễn tập không? |

Không thể tối ưu đồng thời mọi thuộc tính trong mọi tình huống. Ví dụ, `min.insync.replicas=2` cùng `acks=all` có thể từ chối ghi khi ISR chỉ còn một replica. Đây là lựa chọn ưu tiên bảo vệ dữ liệu hơn việc tiếp tục nhận ghi trong trạng thái không đủ bản sao. Nếu hạ ngưỡng để hệ thống tiếp tục ghi, cần chấp nhận và ghi rõ mức rủi ro mất dữ liệu tăng lên.

Hãy xác định ranh giới lỗi độc lập. Ba replica đặt trên cùng một máy chủ hoặc cùng một zone không bảo vệ tốt trước lỗi của máy chủ hoặc zone đó. Với môi trường nhiều zone, dùng rack awareness để Kafka phân bố replica theo rack/zone và xác minh placement thực tế của từng partition.

## 4. Bảo vệ dữ liệu ở phía producer

### 4.1. Cấu hình xác nhận và gửi lại

Với sự kiện quan trọng, cấu hình phổ biến là `acks=all` và bật idempotence cho producer. Idempotent producer giúp Kafka loại bỏ bản ghi trùng do cơ chế retry của cùng producer session theo giao thức hỗ trợ. Nó không tự loại bỏ mọi sự kiện nghiệp vụ trùng, chẳng hạn client gửi cùng một lệnh hai lần hoặc ứng dụng khởi động lại rồi tạo lại một sự kiện mới.

Ví dụ cấu hình trong `application.properties` của Spring Boot:

```properties
spring.kafka.producer.acks=all
spring.kafka.producer.properties[enable.idempotence]=true
spring.kafka.producer.properties[max.in.flight.requests.per.connection]=5
spring.kafka.producer.properties[delivery.timeout.ms]=120000
spring.kafka.producer.properties[request.timeout.ms]=30000
```

Các giá trị timeout trong ví dụ là điểm bắt đầu để thiết kế và cần được điều chỉnh theo latency, timeout của request nghiệp vụ và cấu hình broker. `delivery.timeout.ms` giới hạn tổng thời gian producer cố gắng hoàn tất việc gửi, bao gồm thời gian chờ và retry. Khi hết thời hạn, ứng dụng phải xử lý kết quả thất bại thay vì giả định bản ghi đã được lưu.

Trong Spring Kafka, `KafkaTemplate.send()` là thao tác bất đồng bộ. Việc gọi hàm gửi thành công chỉ cho biết ứng dụng đã khởi tạo việc gửi; kết quả broker xác nhận hoặc lỗi sẽ xuất hiện trong future/callback. Ứng dụng cần quan sát kết quả đó, ghi nhận lỗi có thể hành động và quyết định retry ở tầng phù hợp. Không nên gọi `flush()` sau từng bản ghi nếu không có yêu cầu rõ ràng, vì thao tác này có thể làm giảm batching và throughput.

### 4.2. Idempotence và khóa sự kiện

Producer nên gắn định danh ổn định cho sự kiện, ví dụ `eventId`, `orderId` hoặc một business key. Khóa Kafka (`record key`) quyết định partition mà bản ghi được gửi tới theo partitioner, vì vậy cần chọn khóa phù hợp với thứ tự nghiệp vụ. Các sự kiện cùng một khóa thường đi vào cùng partition và được giữ thứ tự trong partition đó.

Khóa partition không phải cơ chế khử trùng. Nếu cùng một lệnh nghiệp vụ được gửi hai lần, ứng dụng tiêu thụ vẫn có thể nhìn thấy hai bản ghi. Consumer hoặc dịch vụ đích cần dùng event ID để nhận biết sự kiện đã xử lý, ví dụ lưu event ID với ràng buộc duy nhất trong cơ sở dữ liệu.

### 4.3. Giao dịch Kafka

Kafka transactions hỗ trợ ghi nguyên tử nhiều bản ghi Kafka và kết hợp việc đọc offset với việc ghi đầu ra trong một luồng consume-transform-produce. Consumer đọc dữ liệu giao dịch cần dùng `isolation.level=read_committed` để chỉ nhận các giao dịch đã commit. Trong Spring Kafka, cấu hình transaction ID prefix phải duy nhất giữa các instance ứng dụng đang chạy đồng thời để tránh xung đột transactional ID.

Giao dịch Kafka không tự biến thao tác ghi cơ sở dữ liệu, gọi HTTP hoặc gửi email thành một phần của giao dịch Kafka. Nếu listener cập nhật database rồi commit offset Kafka, sự cố giữa hai thao tác vẫn có thể tạo trạng thái không nhất quán. Với luồng tích hợp Kafka và database, cân nhắc transactional outbox ở phía phát sự kiện và inbox/idempotency ở phía nhận. Mô hình này giúp xử lý khoảng trống giữa hai hệ thống bằng cách lưu trạng thái nghiệp vụ và sự kiện trong một giao dịch database, sau đó phát sự kiện có thể retry.

## 5. Bảo vệ dữ liệu ở phía broker

### 5.1. Replication và ISR

Một cấu hình thường dùng cho topic quan trọng trong cluster có ít nhất ba broker độc lập là:

```properties
default.replication.factor=3
min.insync.replicas=2
unclean.leader.election.enable=false
```

Đây là các thiết lập phía broker hoặc topic, không phải thuộc tính của `application.properties` trong ứng dụng Spring Boot. Cần kiểm tra replication factor và min ISR thực tế ở từng topic; giá trị mặc định của cluster không đảm bảo mọi topic hiện có đã dùng đúng chính sách.

- `replication.factor=3` tạo ba bản sao của mỗi partition. Các bản sao nên nằm trên những broker và failure domain khác nhau.
- `min.insync.replicas=2` yêu cầu ít nhất hai replica đồng bộ khi producer dùng `acks=all`.
- `unclean.leader.election.enable=false` tránh bầu một replica đã tụt hậu làm leader trong trường hợp không còn replica đồng bộ. Điều này bảo vệ tính nhất quán dữ liệu tốt hơn, nhưng partition có thể tạm thời không phục vụ nếu không còn ISR đủ điều kiện.

ISR (in-sync replicas) là tập replica đang theo kịp leader theo tiêu chí của Kafka. Theo dõi cả số lượng ISR và các sự kiện ISR shrink/expand. Một partition có replication factor 3 nhưng chỉ còn một replica trong ISR đang có mức bảo vệ thấp hơn cấu hình mong muốn, kể cả khi ứng dụng vẫn đọc được dữ liệu.

### 5.2. Retention và dung lượng

Retention xác định Kafka giữ dữ liệu trong bao lâu hoặc đến giới hạn dung lượng nào. Hãy chọn retention đủ cho thời gian gián đoạn downstream, thời gian điều tra, thời gian khôi phục và khoảng thời gian cần replay. Với topic dùng log compaction, cần hiểu rằng Kafka giữ trạng thái mới nhất theo key theo chính sách compaction; compaction không phải bản sao lưu đầy đủ lịch sử mọi phiên bản.

Ước tính dung lượng phải tính cả tốc độ phát sinh dữ liệu, retention, hệ số replication, overhead của index/segment, mức tăng tải và khoảng trống vận hành. Một phép ước lượng ban đầu cho dung lượng lưu trữ vật lý là:

```text
dung lượng xấp xỉ
  = throughput dữ liệu mỗi giây
  × số giây retention
  × replication factor
  × hệ số dự phòng
```

Đây chỉ là ước lượng sơ bộ. Cần dùng kích thước dữ liệu thực tế sau nén, overhead theo phiên bản/cấu hình, tỷ lệ tăng trưởng, phân bố partition và dung lượng có thể sử dụng trên từng broker. Theo dõi disk usage và tốc độ tăng đĩa; cảnh báo trước khi broker tiến gần giới hạn vận hành.

Replication bảo vệ trước một số lỗi phần cứng, còn retention hỗ trợ đọc lại dữ liệu trong một khoảng thời gian. Cả hai đều không thay thế bản sao lưu độc lập cho lỗi xóa nhầm, ghi sai hoặc mất toàn bộ cluster.

## 6. Đảm bảo consumer xử lý an toàn

### 6.1. Offset và delivery semantics

Offset biểu thị tiến độ đọc của consumer group trên từng partition. Vị trí commit quyết định Kafka bắt đầu giao lại dữ liệu từ đâu sau khi consumer khởi động lại hoặc partition được chuyển sang thành viên khác.

Với xử lý nghiệp vụ cần tránh mất sự kiện, nguyên tắc phổ biến là hoàn tất xử lý rồi mới commit offset. Điều này tạo semantics **at-least-once**: một bản ghi có thể được xử lý lại nếu ứng dụng hoàn thành side effect nhưng dừng trước khi commit offset. Vì vậy, handler cần idempotent hoặc có cơ chế deduplicate.

| Cách xử lý offset | Hành vi khi consumer dừng | Hệ quả |
|---|---|---|
| Commit trước khi xử lý | Kafka có thể không gửi lại bản ghi chưa xử lý xong | Có nguy cơ mất tác động nghiệp vụ; gần với at-most-once |
| Xử lý xong rồi commit | Kafka có thể gửi lại nếu dừng trước commit | Có thể xử lý trùng; at-least-once |
| Giao dịch Kafka kết hợp offset và output Kafka | Offset và bản ghi đầu ra được commit nguyên tử trong Kafka | Có thể đạt exactly-once cho luồng Kafka-to-Kafka trong phạm vi cấu hình giao dịch |

Ví dụ cấu hình consumer:

```properties
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.auto-offset-reset=earliest
spring.kafka.listener.ack-mode=record
```

`enable-auto-commit=false` cho phép Spring Kafka quản lý thời điểm commit theo container acknowledgment mode. `ack-mode=record` commit sau mỗi record đã xử lý thành công; mode này dễ hiểu nhưng có thể tạo thêm chi phí commit so với `BATCH`. Hãy chọn mode dựa trên kích thước batch, yêu cầu throughput và ranh giới xử lý nghiệp vụ. Với manual acknowledgment, chỉ acknowledge sau khi công việc cần thiết đã hoàn tất.

`auto-offset-reset=earliest` chỉ áp dụng khi group chưa có offset hợp lệ hoặc offset hiện tại không còn tồn tại. Nó không có nghĩa mọi lần restart đều đọc lại từ đầu. Dùng `latest` có thể bỏ qua phần dữ liệu cũ khi group chưa có offset; lựa chọn phải phù hợp với cách khởi tạo consumer group và chính sách replay.

Ví dụ listener minh họa xử lý idempotent:

```java
@KafkaListener(topics = "orders", groupId = "billing-service")
public void onOrderCreated(OrderCreated event) {
    // applyOnce kiểm tra eventId và chỉ áp dụng tác động nghiệp vụ một lần.
    billingService.applyOnce(event.eventId(), event);
}
```

`applyOnce` ở đây đại diện cho cơ chế deduplication của ứng dụng, chẳng hạn ghi event ID vào bảng inbox với unique constraint trong cùng giao dịch database với cập nhật nghiệp vụ. Chỉ lưu event ID sau khi cập nhật thành công hoặc thực hiện hai thao tác trong cùng transaction; nếu không, consumer có thể đánh dấu sự kiện đã xử lý trong khi tác động nghiệp vụ chưa được ghi.

### 6.2. Poll, heartbeat và thời gian xử lý

Consumer cần gọi `poll()` đủ thường xuyên để duy trì membership trong group. Nếu xử lý một batch quá lâu, consumer có thể vượt `max.poll.interval.ms`, bị xem là không còn hoạt động và làm phát sinh rebalance. Rebalance liên tục làm giảm throughput và khiến lag tăng.

Các cấu hình cần xem xét cùng nhau:

- `max.poll.records`: số record tối đa trả về trong một lần poll. Batch nhỏ hơn có thể giảm thời gian xử lý mỗi batch nhưng tăng overhead poll/commit.
- `max.poll.interval.ms`: khoảng thời gian tối đa giữa các lần poll. Giá trị phải lớn hơn thời gian xử lý batch ở điều kiện tải cao có dự phòng.
- `session.timeout.ms` và heartbeat: ảnh hưởng đến cách group phát hiện consumer mất kết nối.
- `concurrency` của listener container: số consumer thread trong ứng dụng. Tăng concurrency chỉ có ích khi có đủ partition và downstream đủ năng lực.

Một consumer group không thể xử lý song song nhiều consumer hơn số partition đang được gán cho group tại cùng thời điểm. Nếu cần tăng throughput, cần đánh giá partition count, khả năng xử lý của downstream, thứ tự theo key và giới hạn kết nối trước khi tăng concurrency. Tăng partition có thể ảnh hưởng cách phân phối key và thứ tự giữa các partition, vì vậy cần xem xét trước khi thay đổi topic đang chạy.

Nếu downstream chậm, tránh tăng số consumer một cách mù quáng. Cần áp dụng backpressure, giới hạn concurrency, điều chỉnh batch và bảo vệ downstream khỏi quá tải. Một consumer nhanh hơn không giúp ích nếu database hoặc API phía sau đã chạm giới hạn.

## 7. Retry và Dead Letter Topic

Không phải mọi lỗi xử lý đều có cùng cách khắc phục:

- **Lỗi tạm thời:** timeout database, lỗi mạng hoặc dịch vụ phụ thuộc quá tải. Có thể retry với số lần giới hạn và backoff tăng dần.
- **Lỗi dữ liệu không thể xử lý:** payload sai schema, thiếu trường bắt buộc hoặc giá trị không hợp lệ. Retry liên tục thường không sửa được lỗi; nên chuyển thông điệp sang Dead Letter Topic (DLT) sau chính sách thử lại phù hợp.
- **Lỗi cấu hình hoặc lỗi triển khai:** có thể ảnh hưởng cả partition hoặc toàn bộ consumer. Cần phát hiện nhanh, khôi phục phiên bản/cấu hình và kiểm soát tốc độ retry để tránh tạo thêm tải.

Với Spring Kafka phiên bản có `DefaultErrorHandler`, có thể cấu hình retry hữu hạn và chuyển bản ghi thất bại sang DLT bằng `DeadLetterPublishingRecoverer`. Ví dụ:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(KafkaTemplate<Object, Object> template) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    // 2 lần retry sau lần xử lý đầu tiên, mỗi lần cách nhau 1 giây.
    return new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 2L));
}

@Bean
ConcurrentKafkaListenerContainerFactory<Object, Object> kafkaListenerContainerFactory(
        ConsumerFactory<Object, Object> consumerFactory,
        DefaultErrorHandler kafkaErrorHandler) {
    ConcurrentKafkaListenerContainerFactory<Object, Object> factory =
            new ConcurrentKafkaListenerContainerFactory<>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
```

Trong ví dụ, tổng số lần gọi handler là tối đa ba lần: lần đầu và hai lần retry. Đây là cấu hình minh họa; cần phân loại exception để chọn lỗi nào được retry, điều chỉnh backoff theo thời gian phục hồi của dependency và bảo đảm producer dùng để publish DLT được cấu hình serializer phù hợp.

Khi dùng resolver mặc định của `DeadLetterPublishingRecoverer`, cần kiểm tra quy ước tên DLT và partition đích của phiên bản Spring Kafka đang sử dụng. Nếu giữ nguyên partition nguồn, DLT cần có đủ partition tương ứng. DLT cũng phải có replication, retention, ACL và cảnh báo phù hợp; chuyển được bản ghi vào DLT không có nghĩa sự cố đã được giải quyết.

Một quy trình DLT có trách nhiệm cần lưu lại thông tin nguồn như topic, partition, offset, key, timestamp, exception và event ID. Đội vận hành phải biết ai theo dõi DLT, cách phân loại lỗi, cách sửa dữ liệu hoặc code, cách replay và cách ngăn bản ghi lỗi tạo vòng lặp vô hạn. Khi replay, cần dùng lại định danh sự kiện và bảo đảm consumer đích idempotent.

Spring Kafka cũng hỗ trợ retry topic không chặn luồng chính, chẳng hạn qua `@RetryableTopic`. Cách này có thể giúp partition tiếp tục xử lý các bản ghi khác trong khi một record chờ retry, nhưng có thể làm thay đổi thứ tự xử lý tương đối giữa các sự kiện. Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt theo key, phải đánh giá ảnh hưởng của retry topic và thiết kế luồng xử lý tương ứng.

## 8. Kế hoạch khôi phục theo sự cố

Runbook cần mô tả tín hiệu phát hiện, phạm vi ảnh hưởng, hành động an toàn, người chịu trách nhiệm và điều kiện xác nhận dịch vụ đã phục hồi. Bảng dưới đây là khung tham khảo để xây dựng runbook theo môi trường thực tế.

| Sự cố | Hành động khôi phục chính | Điều cần xác minh sau khôi phục |
|---|---|---|
| Producer mất kết nối hoặc timeout | Kiểm tra DNS, network, TLS/SASL, broker availability và quota; để producer retry trong delivery timeout; xử lý kết quả gửi thất bại ở ứng dụng | Tỷ lệ gửi thành công trở lại bình thường; không có backlog bất thường ở tầng gọi producer; lỗi không bị nuốt bỏ |
| Một broker dừng | Kiểm tra leader election, ISR và replica; khôi phục broker hoặc thay thế node theo runbook | Không còn offline partition; under-replicated partition trở về ngưỡng bình thường; replica đã bắt kịp |
| ISR giảm dưới min ISR | Xác định broker/đĩa/network gây tụt replica; phục hồi replica và theo dõi catch-up | Số ISR đạt chính sách; producer ghi thành công trở lại mà không hạ min ISR tùy tiện |
| Consumer dừng hoặc rebalance liên tục | Kiểm tra exception, thời gian xử lý, poll interval, heartbeat và trạng thái downstream; khởi động lại hoặc rollback bản phát hành lỗi | Group ổn định; commit tiến triển; lag bắt đầu giảm; không có tác động nghiệp vụ trùng chưa được xử lý |
| Downstream quá tải | Giới hạn concurrency, pause hoặc giảm tốc consumer theo cơ chế hỗ trợ; khôi phục năng lực downstream; tăng tốc xử lý dần | Downstream ổn định; backlog giảm; không gây thêm timeout hoặc retry storm |
| Poison message | Sửa nguyên nhân dữ liệu hoặc code; giữ bản ghi cùng metadata; replay có kiểm soát từ DLT | Bản ghi được xử lý; số lượng DLT giảm; replay không tạo side effect trùng |
| Xóa nhầm topic hoặc dữ liệu | Dừng thao tác gây ảnh hưởng; xác định retention và nguồn backup/replica độc lập; khôi phục topic, cấu hình và dữ liệu theo quy trình | Số lượng và phạm vi dữ liệu khôi phục được đối soát; producer/consumer dùng đúng topic và offset |
| Mất cluster hoặc vùng | Kích hoạt kế hoạch DR; chuyển producer/consumer sang cluster dự phòng theo quy trình đã diễn tập; kiểm tra đồng bộ dữ liệu và offset | RTO/RPO thực tế được ghi nhận; luồng đọc/ghi và quyền truy cập hoạt động; dữ liệu được đối soát |

### 8.1. Khôi phục consumer backlog

Sau khi consumer dừng, backlog có thể lớn dù Kafka đã hoạt động bình thường. Điều quan trọng là xác định consumer có thể xử lý nhanh hơn tốc độ sự kiện mới đến hay không.

```text
thời gian drain backlog xấp xỉ
  = số bản ghi tồn đọng
  / (throughput xử lý phục hồi - throughput dữ liệu mới)
```

Ví dụ, backlog có 1.800.000 bản ghi, consumer xử lý được 8.000 bản ghi/giây và producer tiếp tục tạo 2.000 bản ghi/giây. Năng lực xử lý ròng là 6.000 bản ghi/giây, nên thời gian drain lý tưởng khoảng 300 giây. Thời gian thực tế còn phụ thuộc kích thước bản ghi, phân bố key, số partition, latency downstream, retry và rebalance.

Nếu throughput xử lý phục hồi không lớn hơn throughput dữ liệu mới, backlog sẽ không giảm. Khi đó cần tăng năng lực xử lý an toàn, giảm tải đầu vào, hoặc áp dụng phương án nghiệp vụ để xử lý backlog. Chỉ tăng số consumer khi còn partition có thể gán và downstream còn tài nguyên.

### 8.2. Khôi phục cluster hoặc vùng

Kế hoạch DR cần ghi rõ cluster dự phòng, cách đồng bộ topic và dữ liệu, schema/ACL/config cần có, bootstrap server cho từng ứng dụng, cách chuyển traffic, cách xử lý consumer offset và quy trình quay lại cluster chính. Các công nghệ như MirrorMaker 2 hoặc giải pháp liên kết cluster có thể hỗ trợ sao chép dữ liệu, nhưng không nên giả định offset, ACL, schema và cấu hình ứng dụng tự động tương thích hoàn toàn.

Chuyển sang cluster dự phòng có thể tạo ra khoảng trống hoặc trùng lặp tùy cách đồng bộ dữ liệu và offset. Cần đo replication lag, xác định điểm chuyển đổi, kiểm soát producer ghi vào cluster nào và có bước đối soát dữ liệu sau failover. Quay lại cluster chính (failback) cũng cần một quy trình riêng; không nên chỉ đổi bootstrap server trở lại mà chưa xác định hướng dữ liệu và trạng thái offset.

## 9. Quan sát và cảnh báo trong Spring Kafka

Độ tin cậy cần được quan sát từ cả ứng dụng và nền tảng. Spring Boot Actuator cùng Micrometer có thể đưa metric ứng dụng và một số metric Kafka vào hệ thống giám sát; Kafka broker/client cũng cung cấp metric qua JMX hoặc hệ thống exporter tương ứng. Tên metric cụ thể phụ thuộc phiên bản Spring Boot, Spring Kafka, Kafka client và cấu hình registry.

### 9.1. Metric producer

Theo dõi tỷ lệ gửi thành công, số lỗi và timeout, retry rate, request latency, record send rate, batch size và buffer exhaustion. Nếu latency tăng cùng retry rate, cần kiểm tra broker load, network, quota, ISR và kích thước batch. Một producer có thể còn gửi được nhưng latency tăng đủ lớn để làm request nghiệp vụ timeout.

### 9.2. Metric broker

Các tín hiệu quan trọng gồm:

- Offline partitions và số partition không có leader.
- Under-replicated partitions, ISR shrink/expand và replica fetch lag.
- Request latency, request queue, network processor và request handler utilization.
- Disk usage, tốc độ tăng dữ liệu, log directory failure và tình trạng broker.
- Số kết nối, quota throttle và lỗi xác thực/phân quyền.

Offline partition thường cần cảnh báo mức nghiêm trọng vì partition đó không phục vụ bình thường. Under-replicated partition kéo dài cho thấy mức bảo vệ dữ liệu đang thấp hơn chính sách. Cảnh báo dung lượng phải có đủ thời gian để mở rộng đĩa hoặc điều chỉnh tải trước khi broker hết chỗ.

### 9.3. Metric consumer và nghiệp vụ

Theo dõi lag theo partition và group, tuổi của record cũ nhất chưa xử lý, record processing rate, processing latency, commit failure, rebalance rate, số exception và DLT publish rate. Lag chỉ là số lượng bản ghi; với topic có tốc độ thấp, tuổi của record cũ nhất có thể phản ánh tác động nghiệp vụ tốt hơn.

Nên bổ sung metric nghiệp vụ như số đơn hàng đã xử lý, số giao dịch chờ, tỷ lệ sự kiện bị từ chối và thời gian từ lúc phát sinh đến lúc hoàn tất. Dùng event ID hoặc correlation ID trong log để truy vết cùng một sự kiện qua producer, Kafka và consumer. Tránh ghi payload nhạy cảm hoặc toàn bộ nội dung bản ghi vào log nếu không có yêu cầu và kiểm soát phù hợp.

### 9.4. Thiết kế cảnh báo có hành động

Mỗi cảnh báo nên trả lời ba câu hỏi: điều gì đang hỏng, tác động đến dịch vụ nào và người trực cần làm gì tiếp theo. Ví dụ:

- `offline partitions > 0`: xác định topic/partition, broker liên quan và runbook phục hồi leader.
- `under-replicated partitions > 0` kéo dài: kiểm tra broker, disk, network và tốc độ replica catch-up.
- Consumer lag tăng liên tục hoặc tuổi record vượt SLO: xác định group/partition, processing rate và trạng thái downstream.
- DLT tăng đột biến: kiểm tra phiên bản ứng dụng, schema, dependency và nhóm exception.
- Producer timeout tăng: kiểm tra broker latency, ISR, quota và network; đồng thời kiểm tra retry ở caller để tránh retry storm.

Không nên cảnh báo chỉ dựa trên một con số tĩnh nếu trạng thái chuyển tiếp là bình thường. Dùng thời gian duy trì, tốc độ thay đổi, số partition bị ảnh hưởng và SLO nghiệp vụ để giảm cảnh báo nhiễu mà vẫn phát hiện sớm sự cố.

## 10. Quy trình vận hành để giữ mục tiêu ổn định

### 10.1. Triển khai và dừng ứng dụng an toàn

Rolling deployment cần tránh làm mất đồng thời quá nhiều consumer trong cùng group hoặc làm cụm broker mất quorum/ISR cần thiết. Đặt termination grace period đủ cho listener container dừng nhận việc mới, hoàn tất xử lý đang chạy trong giới hạn cho phép và commit offset. Với xử lý kéo dài, cần xác định hành vi khi hết thời gian shutdown để tránh vừa commit vừa tiếp tục side effect ở background.

Thay đổi concurrency, partition count, serializer, schema hoặc cấu hình retry có thể tác động đến thứ tự, throughput và khả năng đọc dữ liệu cũ. Nên triển khai theo từng bước, quan sát metric sau mỗi bước và có phương án rollback. Khi nâng phiên bản Kafka client hoặc Spring Kafka, kiểm tra compatibility và thay đổi mặc định liên quan đến producer, consumer, transaction và error handler.

### 10.2. Quản lý capacity

Capacity planning cần tính cả throughput trung bình, peak traffic, kích thước record, tỷ lệ nén, số partition, replication factor, retention, consumer processing rate và dung lượng downstream. Hãy duy trì headroom để hệ thống hấp thụ tăng tải và phục hồi backlog sau sự cố. Nếu thiết kế chỉ đủ xử lý tải trung bình, một đợt backlog có thể khiến hệ thống không bao giờ bắt kịp producer.

Kiểm tra định kỳ các giới hạn như file descriptor, network bandwidth, disk IOPS, số kết nối, quota, request handler capacity và dung lượng heap. Với ứng dụng Spring, theo dõi thread pool, connection pool của database, thời gian GC và các dependency đồng bộ trong listener. Những giới hạn này có thể làm consumer chậm dù broker vẫn khỏe.

### 10.3. Diễn tập khôi phục

Runbook chỉ đáng tin khi đã được thực hành. Diễn tập theo từng mức lỗi: dừng một consumer, dừng một broker trong môi trường kiểm soát, làm chậm downstream, xử lý poison message, phục hồi dữ liệu từ nguồn backup và failover sang cluster dự phòng. Ghi lại thời điểm phát hiện, thời điểm bắt đầu khôi phục, thời điểm dịch vụ đạt SLO, lượng dữ liệu tồn đọng, số record replay và mọi sai khác sau đối soát.

Sau mỗi lần diễn tập hoặc sự cố thật, cập nhật RTO/RPO đo được, dashboard, cảnh báo, quyền truy cập, danh sách liên hệ và các bước runbook. Nếu kết quả thực tế không đạt mục tiêu, cần điều chỉnh kiến trúc hoặc mục tiêu đã cam kết thay vì chỉ ghi nhận sự cố đã kết thúc.

## 11. Tiêu chí vận hành có thể kiểm chứng

Một hệ thống Spring Kafka chỉ nên được xem là sẵn sàng cho vận hành khi đội phụ trách có thể trả lời và chứng minh được các điểm sau:

1. Đã xác định luồng nghiệp vụ quan trọng, failure model, SLI/SLO, RTO và RPO cho từng kịch bản.
2. Producer có chính sách `acks`, idempotence, timeout và xử lý kết quả gửi rõ ràng; lỗi gửi không bị bỏ qua.
3. Topic quan trọng có replication factor, min ISR, placement và retention phù hợp; có cảnh báo khi mất replica hoặc thiếu dung lượng.
4. Consumer có chiến lược commit offset rõ ràng, xử lý idempotent, kiểm soát thời gian poll và có backpressure khi downstream chậm.
5. Retry có giới hạn; DLT có người theo dõi, retention, cảnh báo và quy trình replay được kiểm soát.
6. Dashboard thể hiện sức khỏe producer, broker, consumer và độ trễ nghiệp vụ; cảnh báo dẫn đến hành động cụ thể.
7. Có nguồn phục hồi độc lập cho tình huống replication không đủ, xóa nhầm hoặc mất cluster; quy trình DR đã được diễn tập.
8. Có quy trình triển khai, shutdown, capacity planning, rollback và đối soát sau khôi phục.

Các tiêu chí này biến mục tiêu độ tin cậy thành trách nhiệm vận hành cụ thể. Khi có số liệu thực tế từ tải production và diễn tập, đội ngũ có thể điều chỉnh SLO, topology, timeout, retention và năng lực xử lý để cân bằng giữa mức sẵn sàng, mức bảo vệ dữ liệu, chi phí và thời gian phục hồi.
