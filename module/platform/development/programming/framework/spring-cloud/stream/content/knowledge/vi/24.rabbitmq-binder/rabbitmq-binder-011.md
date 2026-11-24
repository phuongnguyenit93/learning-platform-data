# Phân vùng ứng dụng và single-active-consumer

RabbitMQ Binder của Spring Cloud Stream có thể phân phối message theo partition để tăng khả năng xử lý song song. Ở phía consumer, ứng dụng khai báo binding được phân vùng, tổng số instance và chỉ số của instance hiện tại. RabbitMQ còn có tính năng **single-active-consumer (SAC)**: nhiều consumer có thể đăng ký trên cùng một queue nhưng broker chỉ cho một consumer hoạt động tại một thời điểm; các consumer còn lại chờ làm dự phòng.

Partitioning và single-active-consumer giải quyết hai vấn đề khác nhau. Partitioning chia một luồng thành nhiều phần để nhiều instance xử lý song song. SAC giới hạn một queue chỉ có một consumer đang nhận message, đồng thời cho phép broker chuyển vai trò active khi consumer đó mất kết nối. Có thể kết hợp chúng khi cần xử lý song song giữa các partition nhưng chỉ một consumer hoạt động trên từng queue partition.

Bài thuộc chương **RabbitMQ Binder** của module `SPRING_CLOUD_STREAM`. Nội dung tập trung vào mô hình hàm `Supplier`/`Function`/`Consumer`, `partitionKeyExpression`, `partitionCount`, `partitioned`, `instanceCount`, `instanceIndex` và queue argument `x-single-active-consumer`, cùng thứ tự message, concurrency, failover và vận hành.

## 1. Phân vùng và single-active-consumer khác nhau thế nào?

Hai cơ chế thường được dùng cùng nhau nhưng có mục tiêu riêng:

| Cơ chế | Chia tải như thế nào? | Mục tiêu chính | Phạm vi |
|---|---|---|---|
| Partitioning | Chọn partition dựa trên khóa của message rồi định tuyến vào queue tương ứng | Tăng song song và giữ các message cùng khóa trong cùng partition | Toàn luồng được chia thành nhiều partition |
| Single-active-consumer | Nhiều consumer đăng ký trên một queue, broker chỉ giao message cho một consumer active | Có một consumer nhận message tại một thời điểm và có consumer standby để failover | Một queue |
| Concurrency | Một instance chạy nhiều consumer/listener hoặc nhiều tác vụ xử lý | Tăng số xử lý đồng thời trong một tiến trình | Một instance ứng dụng |

Partitioning không tự bảo đảm chỉ có một consumer hoạt động trên một queue. SAC không tự chia message theo khóa hoặc tạo thêm partition. Concurrency cũng không thay thế `instanceCount` hay số partition.

```text
Partitioning: chia luồng thành nhiều queue

orders.events
     |
     +---- partition 0 ----> queue P0 ----> instance xử lý P0
     |
     +---- partition 1 ----> queue P1 ----> instance xử lý P1
     |
     +---- partition 2 ----> queue P2 ----> instance xử lý P2

SAC trên một queue:

queue P0
   |
   +---- consumer A (ACTIVE) <---- nhận message
   |
   +---- consumer B (STANDBY)
   |
   +---- consumer C (STANDBY)
```

Trong ví dụ kết hợp, mỗi queue partition có thể có một consumer active. Các partition khác nhau vẫn có thể xử lý đồng thời, còn các consumer đăng ký cùng một queue partition đóng vai trò dự phòng cho nhau.

## 2. Partition key giữ các message liên quan cùng luồng

Partitioning thường dựa trên một khóa nghiệp vụ như `orderId`, `accountId` hoặc `customerId`. Producer tính partition từ khóa đó để các message có cùng khóa được đưa vào cùng partition.

Ví dụ, nếu dùng `accountId` làm khóa:

| Message | `accountId` | Partition |
|---|---|---:|
| AccountOpened | `A-100` | 0 |
| DepositRecorded | `A-100` | 0 |
| WithdrawalRecorded | `A-100` | 0 |
| AccountOpened | `B-200` | 2 |
| DepositRecorded | `B-200` | 2 |

Các sự kiện của cùng một tài khoản đi qua cùng partition, nhờ đó có thể xử lý theo thứ tự trong phạm vi partition nếu consumer xử lý tuần tự. Các tài khoản khác nhau có thể được xử lý song song trên các partition khác.

Khóa cần ổn định và phản ánh đúng ranh giới thứ tự nghiệp vụ. Dùng `eventId` làm partition key thường phân tán từng message riêng lẻ và không giữ các sự kiện của cùng aggregate trong cùng partition.

## 3. Cấu hình partition ở producer

Spring Cloud Stream cung cấp các thuộc tính producer chung để chọn partition key và số partition. Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
```

`partition-key-expression` lấy `orderId` từ payload. `partition-count: 6` khai báo số partition mà producer sử dụng để tính toán phân vùng. Với RabbitMQ Binder, partition được triển khai bằng topology exchange/queue và routing do binder quản lý; không nên giả định tên queue vật lý hoặc routing key nội bộ nếu chưa kiểm tra phiên bản binder.

Nếu muốn dùng bean để tính partition key hoặc chọn partition, có thể cấu hình `partitionKeyExtractorName` hoặc `partitionSelectorName` theo API Spring Cloud Stream. Chỉ dùng một chiến lược rõ ràng cho từng binding; tránh để producer và consumer triển khai hai quy tắc phân vùng khác nhau.

## 4. Cấu hình consumer partitioned

Consumer binding cần khai báo `partitioned: true`. Ứng dụng cũng cần biết tổng số instance và chỉ số của instance hiện tại:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      instance-count: ${INSTANCE_COUNT:3}
      instance-index: ${INSTANCE_INDEX:0}
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processing
          consumer:
            partitioned: true
```

Ý nghĩa:

- `partitioned: true` bật chế độ consumer partition-aware cho binding.
- `instance-count` là tổng số instance ứng dụng tham gia xử lý luồng.
- `instance-index` là chỉ số của instance hiện tại, thường bắt đầu từ `0`.
- `group` xác định nhóm consumer logic dùng chung topology/queue theo binder.

Với ba instance, các giá trị hợp lệ là `instanceCount = 3` và các `instanceIndex` lần lượt là `0`, `1`, `2`. Tất cả instance phải dùng cùng `instanceCount`, còn mỗi instance có index riêng. Index phải thỏa điều kiện:

\[
0 \leq instanceIndex < instanceCount
\]

Các thuộc tính `instance-count` và `instance-index` nằm dưới `spring.cloud.stream`, không đặt bên trong `consumer` của binding. Chúng mô tả instance ứng dụng, không phải số partition và cũng không phải số thread xử lý.

## 5. Gán index cho các replica

Với ba replica:

```text
Replica A:
  INSTANCE_COUNT=3
  INSTANCE_INDEX=0

Replica B:
  INSTANCE_COUNT=3
  INSTANCE_INDEX=1

Replica C:
  INSTANCE_COUNT=3
  INSTANCE_INDEX=2
```

Các replica của cùng một consumer logic phải dùng cùng `group`, cùng destination và cùng `instanceCount`. Nếu tất cả replica cùng dùng index `0`, binder không thể phân biệt các instance theo mô hình partition đã khai báo. Nếu count khác nhau, mỗi instance có thể tính toán hoặc đăng ký queue partition không nhất quán.

Trong Kubernetes, StatefulSet ordinal có thể được ánh xạ sang `INSTANCE_INDEX`. Với Deployment có tên pod thay đổi, cần một cơ chế cấp index duy nhất cho từng replica. Không nên dùng giá trị mặc định `0` cho tất cả pod production.

`instanceCount` là số instance ứng dụng, không phải `partitionCount`. Ví dụ sáu partition và ba instance có thể cho phép mỗi instance xử lý nhiều partition. Nếu số instance lớn hơn số partition, có thể có instance không được gán partition. Khả năng gán thực tế phụ thuộc cách Rabbit binder tạo và liên kết queue.

## 6. RabbitMQ single-active-consumer là gì?

Single-active-consumer là tính năng của RabbitMQ được bật trên queue bằng queue argument:

```text
x-single-active-consumer = true
```

Khi queue có nhiều consumer đăng ký, RabbitMQ chỉ chọn một consumer active để nhận message. Những consumer còn lại ở trạng thái standby. Khi consumer active bị hủy, mất channel hoặc mất connection, broker chọn một consumer standby khác làm active.

Điểm quan trọng:

- SAC áp dụng cho từng queue, không phải toàn bộ exchange hoặc toàn cluster.
- Có thể có nhiều consumer connection trên cùng queue, nhưng chỉ một consumer active nhận message tại một thời điểm.
- Consumer standby không nhận message cho đến khi được broker thăng cấp.
- Khi active consumer mất kết nối, message chưa acknowledgement có thể được requeue và giao lại.
- SAC không tạo bản sao message cho từng consumer; các consumer cùng queue vẫn thuộc một nhóm competing consumers.

Tính năng này phù hợp khi cần một consumer xử lý queue tại một thời điểm nhưng vẫn muốn có replica dự phòng để tiếp quản nhanh khi active consumer gặp sự cố.

## 7. Cấu hình single-active-consumer với RabbitMQ Binder

Các phiên bản RabbitMQ Binder có hỗ trợ thuộc tính `singleActiveConsumer` cho consumer binding có thể ánh xạ cấu hình này sang queue argument `x-single-active-consumer`:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processing
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              single-active-consumer: true
              concurrency: 1
```

`single-active-consumer` là thuộc tính riêng của RabbitMQ Binder, không phải thuộc tính generic áp dụng cho Kafka hoặc Pulsar. Cần kiểm tra phiên bản Spring Cloud Stream Rabbit binder đang dùng có hỗ trợ thuộc tính này và cách nó áp dụng cho queue thường hoặc queue partition hay không.

Nếu topology được provision bên ngoài, queue phải được khai báo với `x-single-active-consumer=true` trước khi consumer kết nối. Binder và hệ thống provisioning phải thống nhất queue argument. RabbitMQ không cho phép redeclare cùng một queue với các thuộc tính không tương thích; bật SAC sau khi queue đã tồn tại mà không migration có thể làm ứng dụng lỗi khi khai báo topology.

`concurrency: 1` trong ví dụ giới hạn số consumer được tạo bởi mỗi instance ở mức một. Để có failover, cần nhiều replica cùng đăng ký trên cùng queue. Nếu chỉ có một consumer duy nhất, SAC không có consumer standby để tiếp quản.

## 8. SAC khác với exclusive consumer

Không nhầm single-active-consumer với consumer `exclusive`:

| Tiêu chí | Single-active-consumer | Exclusive consumer |
|---|---|---|
| Cách khai báo | Queue argument `x-single-active-consumer=true` | Consumer đăng ký với cờ exclusive |
| Nhiều consumer đăng ký | Được phép; một active, các consumer còn lại standby | Consumer khác có thể bị từ chối khi queue đã có exclusive consumer |
| Failover | Broker tự chọn consumer standby tiếp theo | Không phải mô hình standby consumer tương đương SAC |
| Phạm vi | Queue | Lần đăng ký consumer trên queue |
| Mục tiêu | Một consumer active có dự phòng | Độc quyền đăng ký consumer |

SAC thường phù hợp hơn khi muốn nhiều replica cùng chờ trên một queue và broker tự động chuyển active role. Exclusive consumer phù hợp với yêu cầu độc quyền kết nối trong một số tình huống khác, nhưng không nên dùng thay cho SAC nếu cần failover tự động giữa các replica standby.

## 9. Kết hợp partitioning với SAC

Có thể thiết kế một queue cho mỗi partition và bật SAC trên từng queue. Khi đó:

- Producer dùng partition key để đưa message vào một partition.
- Consumer deployment có nhiều instance để xử lý các partition khác nhau.
- SAC giới hạn mỗi queue partition chỉ có một consumer active.
- Consumer standby có thể tiếp quản queue partition khi active consumer mất kết nối, nếu topology cho phép nhiều consumer đăng ký trên cùng queue.

```text
                         orders.events
                              |
                  partition key = orderId
                              |
          +-------------------+-------------------+
          |                   |                   |
          v                   v                   v
       Queue P0            Queue P1            Queue P2
          |                   |                   |
       SAC P0              SAC P1              SAC P2
      /      \            /      \            /      \
   active  standby      active  standby      active  standby
     |                   |                   |
  Worker A            Worker B            Worker C
```

Sơ đồ minh họa một consumer active trên mỗi queue. Ba partition vẫn có thể được xử lý song song. Nếu queue partition chỉ được gán cho đúng một instance và không có consumer standby nào khác đăng ký vào queue đó, SAC không tạo ra failover bổ sung. Cần kiểm tra queue topology và cách binder gán partition trước khi kết luận SAC đang bảo vệ instance nào.

Không giả định bật `single-active-consumer` trên binding partitioned sẽ tự động tạo mọi topology standby cần thiết. Integration test với đúng phiên bản binder phải xác nhận các consumer đăng ký vào queue nào và broker chọn active consumer ra sao.

## 10. Partitioning và SAC ảnh hưởng đến thứ tự message

Partitioning giúp giữ các message cùng key trong cùng partition nếu producer dùng một quy tắc ổn định. SAC giúp chỉ một consumer active nhận message từ queue đó. Kết hợp hai cơ chế có thể tạo điều kiện tốt cho xử lý tuần tự theo key, nhưng chưa đủ để bảo đảm thứ tự hoàn tất nghiệp vụ.

Thứ tự có thể bị phá vỡ nếu:

- Consumer xử lý nhiều message song song trong cùng instance.
- Handler chuyển công việc sang thread pool bất đồng bộ rồi acknowledgement không theo thứ tự.
- Retry một message lâu trong khi các message tiếp theo đã được giao.
- Nhiều routing key đưa các message liên quan vào các partition khác nhau.
- Producer thay đổi partition key hoặc số partition giữa vòng đời dữ liệu.

Nếu cần thứ tự nghiêm ngặt trên một queue, thường phải giới hạn concurrency bằng `1`, xử lý tuần tự và chọn prefetch phù hợp. Nếu cần thứ tự theo aggregate, dùng partition key theo aggregate ID và bảo đảm các tác vụ trong cùng partition được xử lý tuần tự. SAC không tự sửa logic bất đồng bộ bên trong handler.

## 11. SAC không phải cơ chế exactly-once

Khi active consumer bị ngắt kết nối, message đã giao nhưng chưa được acknowledgement có thể được RabbitMQ giao lại cho consumer mới. Consumer mới có thể nhận một message mà consumer cũ đã thực hiện một phần tác động nghiệp vụ.

Ví dụ:

1. Consumer A nhận `OrderPlaced`.
2. Consumer A ghi tồn kho vào database.
3. Consumer A mất kết nối trước khi ack.
4. RabbitMQ chuyển active role sang consumer B.
5. Message chưa ack được giao lại cho B.

Consumer B cần idempotency theo `eventId` hoặc inbox table để tránh trừ tồn kho lần nữa. SAC cải thiện mô hình active/standby và failover; nó không thay thế acknowledgement, transaction hoặc deduplication.

## 12. Queue durability và single-active-consumer

SAC là queue argument, còn durability quyết định queue có tồn tại sau khi broker restart hay không. Hai thuộc tính giải quyết hai vấn đề khác nhau:

| Thuộc tính | Câu hỏi được giải quyết |
|---|---|
| `durable` | Queue có tồn tại sau broker restart không? |
| Persistent message | Message có được lưu bền vững theo cơ chế broker không? |
| `x-single-active-consumer` | Trong các consumer đăng ký trên queue, ai được nhận message tại một thời điểm? |
| `prefetch` | Broker có thể giao trước bao nhiêu message chưa ack cho consumer? |
| `acknowledgeMode` | Consumer xác nhận message đã xử lý theo cách nào? |

Queue durable không tự làm message persistent. SAC cũng không bảo đảm message tồn tại sau khi broker restart. Cần kết hợp queue durability, message delivery mode, publisher confirms, acknowledgement và loại queue/policy phù hợp với yêu cầu độ bền.

## 13. Scaling partitioned consumer

Giả sử producer tạo sáu partition và consumer deployment có ba instance. Cấu hình cần thống nhất:

```text
partitionCount = 6
instanceCount  = 3

Instance 0: instanceIndex = 0
Instance 1: instanceIndex = 1
Instance 2: instanceIndex = 2
```

Khi scale từ ba lên bốn instance, cần cập nhật `instanceCount` đồng nhất và cấp index `0`, `1`, `2`, `3`. Không để một số replica dùng count `3` và replica khác dùng count `4` trong trạng thái ổn định. Cách chuyển đổi cần phối hợp với topology queue và binder để tránh partition không có consumer hoặc hai instance cùng nhận một partition ngoài dự kiến.

SAC không làm thay đổi `partitionCount` hoặc `instanceCount`. Nó chỉ ảnh hưởng consumer đang active trên từng queue. Nếu muốn tăng throughput, cần đánh giá số partition, key distribution, số instance và khả năng xử lý; tăng standby consumer không tự tăng throughput của một queue SAC.

## 14. Khi nào chọn partitioning?

Chọn partitioning khi:

- Luồng có nhiều key độc lập và cần xử lý song song.
- Cần giữ các message của cùng đơn hàng/tài khoản/khách hàng trên cùng luồng xử lý.
- Một consumer instance không đủ throughput.
- Muốn scale theo số partition và số instance.
- Có thể xác định một partition key ổn định từ payload/header.

Không nên partition chỉ để tăng số queue nếu dữ liệu cần thứ tự toàn cục hoặc số key rất ít và bị lệch tải. Một key nóng có thể khiến một partition quá tải dù các partition khác nhàn rỗi.

## 15. Khi nào chọn single-active-consumer?

Chọn SAC khi:

- Một queue cần chỉ có một consumer nhận message tại một thời điểm.
- Cần một consumer standby để tiếp quản khi active consumer dừng.
- Muốn hạn chế xử lý song song trên cùng queue.
- Cần đơn giản hóa thứ tự giao message trong một queue, đồng thời có thể chấp nhận throughput thấp hơn.
- Nhiều replica cùng đăng ký queue và broker cần chọn active consumer.

Không dùng SAC với kỳ vọng tự tăng throughput. Nếu chỉ có một queue và một active consumer, năng lực xử lý của queue bị giới hạn bởi consumer active đó. Thêm standby consumer cải thiện khả năng sẵn sàng nhưng không làm nhiều consumer xử lý đồng thời.

## 16. Khi nào kết hợp cả hai?

Kết hợp partitioning và SAC khi:

- Cần song song giữa các partition.
- Mỗi partition cần một consumer active tại một thời điểm.
- Cần replica dự phòng cho từng queue partition.
- Có thể triển khai và kiểm soát topology queue/consumer phù hợp.

Ví dụ hệ thống xử lý tài khoản ngân hàng có sáu partition theo `accountId`. Mỗi partition queue có một active consumer để xử lý các sự kiện theo thứ tự, đồng thời có standby consumer để tiếp quản khi active bị lỗi. Cần bảo đảm các consumer standby thực sự đăng ký vào cùng queue partition và không phá vỡ quy tắc `instanceIndex` của binder.

Nếu mục tiêu chỉ là có một consumer duy nhất cho toàn bộ luồng và failover giữa replica, một queue với SAC có thể đủ. Nếu mục tiêu là throughput cao và không cần single-active, partitioning với nhiều consumer active có thể phù hợp hơn.

## 17. Các lỗi cấu hình thường gặp

| Tình huống | Hệ quả | Cách khắc phục |
|---|---|---|
| `instanceIndex` trùng giữa replica | Các instance không được phân biệt đúng trong mô hình partitioned | Cấp index duy nhất trong khoảng hợp lệ |
| `instanceCount` không nhất quán | Các replica có cách nhìn khác nhau về topology | Đồng nhất count trên toàn nhóm |
| Producer và consumer khác partition count | Message có thể định tuyến đến queue không được consumer dự kiến nhận | Đồng bộ partition topology và kiểm tra broker |
| Dùng `eventId` làm partition key | Sự kiện cùng aggregate có thể nằm ở nhiều partition | Dùng aggregate key như `orderId` hoặc `accountId` |
| Bật SAC nhưng chỉ có một consumer | Không có standby để failover | Triển khai nhiều consumer cùng đăng ký queue |
| Bật SAC trên queue đã tồn tại với argument khác | Queue redeclare có thể thất bại | Provision/migrate queue với argument thống nhất |
| Nhầm SAC với exclusive consumer | Consumer dự phòng không thể đăng ký như dự kiến | Dùng queue argument SAC và kiểm tra subscription |
| Tăng concurrency nhưng kỳ vọng một active consumer | Nhiều tác vụ có thể chạy đồng thời bên trong handler | Giới hạn concurrency và xử lý tuần tự khi cần |
| Cho rằng SAC bảo đảm exactly-once | Duplicate vẫn xảy ra sau mất kết nối trước ack | Dùng event ID và idempotency |
| Đổi partition count không có kế hoạch | Key có thể ánh xạ sang partition khác; thứ tự chuyển tiếp khó kiểm soát | Lập migration và kiểm thử dữ liệu đang chờ |

## 18. Kiểm thử partitioning và SAC

Kiểm thử cần chạy với RabbitMQ thật hoặc môi trường tương thích vì queue argument và hành vi active/standby do broker quyết định.

| Kịch bản | Cách kiểm thử | Kết quả cần xác minh |
|---|---|---|
| Partition key ổn định | Gửi nhiều event cùng `orderId` | Các event cùng key được định tuyến vào cùng partition theo cấu hình |
| Nhiều partition | Gửi event với nhiều key | Message được phân bố qua các partition queue |
| Nhiều instance | Count `3`, index `0`, `1`, `2` | Instance nhận đúng phần partition được binder gán |
| Index trùng | Hai instance cùng index | Validation/deployment phát hiện cấu hình sai |
| SAC với hai consumer | Hai consumer đăng ký cùng queue có SAC | Chỉ một consumer active nhận message |
| Active consumer dừng | Đóng connection/channel của active | Broker promote một consumer standby |
| Message chưa ack | Dừng active sau khi nhận nhưng trước ack | Message được giao lại; consumer xử lý duplicate an toàn |
| SAC và concurrency | Thử concurrency lớn hơn 1 | Xác minh active consumer và thứ tự hoàn tất thực tế |
| Partition + SAC | Nhiều queue partition, mỗi queue có nhiều consumer | Một active consumer trên từng queue và song song giữa queue |
| Queue argument không khớp | Khởi động binder với SAC khác topology hiện có | Xác minh lỗi declaration và quy trình migration |
| Scale up/down | Thay instanceCount và index | Không bỏ sót partition hoặc tạo xung đột consumer |

Test binder kiểm tra được function/binding ở tầng Spring, nhưng không mô phỏng đầy đủ thuật toán SAC của RabbitMQ. Dùng RabbitMQ Management UI/API để kiểm tra queue arguments, consumer active và trạng thái standby; dùng integration test để xác nhận failover và redelivery.

## 19. Quan sát và vận hành

Theo dõi các chỉ số:

- Số partition queue và phân bố message theo partition.
- Số consumer đăng ký trên mỗi queue.
- Consumer nào đang active và consumer nào standby.
- Thời gian failover từ active sang standby.
- Số message redelivered và số lần xử lý duplicate.
- Queue backlog, tuổi message cũ nhất và tốc độ xử lý.
- Consumer concurrency, prefetch và thời gian xử lý handler.
- Số lỗi declaration do queue argument hoặc topology không tương thích.

Log nên có event ID, partition key, destination, group, instance index và queue logic nếu binder cung cấp. Không dùng event ID làm metric label có cardinality cao. Cảnh báo khi một queue partition không có active consumer, standby không được đăng ký, backlog tăng kéo dài hoặc failover thường xuyên.

## 20. Quy trình triển khai

1. Xác định aggregate key cần giữ thứ tự, ví dụ `orderId` hoặc `accountId`.
2. Chọn `partitionCount` theo throughput và số queue có thể vận hành.
3. Cấu hình producer `partition-key-expression` và `partition-count`.
4. Cấu hình consumer `partitioned: true`.
5. Đặt `instanceCount` bằng tổng số instance tham gia và cấp `instanceIndex` duy nhất.
6. Chọn có cần SAC trên từng queue hay không; xác định mục tiêu failover/ordering.
7. Nếu dùng SAC, xác nhận Rabbit binder hỗ trợ `singleActiveConsumer` hoặc provision queue với `x-single-active-consumer=true`.
8. Bảo đảm nhiều consumer standby thực sự đăng ký trên cùng queue cần failover.
9. Điều chỉnh concurrency, prefetch và acknowledgement theo yêu cầu thứ tự.
10. Thiết kế idempotency để xử lý message redelivery sau failover.
11. Kiểm thử partition assignment, active consumer, failover, scale và duplicate trên RabbitMQ.
12. Theo dõi backlog, active/standby state và thời gian phục hồi trong production.

## 21. Tự kiểm tra

- [ ] Phân biệt partitioning với single-active-consumer.
- [ ] Giải thích được vai trò của partition key và `partitionCount`.
- [ ] Cấu hình được `consumer.partitioned`, `instanceCount` và `instanceIndex`.
- [ ] Biết các replica cùng consumer logic cần dùng chung group.
- [ ] Giải thích được queue argument `x-single-active-consumer`.
- [ ] Phân biệt SAC với exclusive consumer.
- [ ] Hiểu SAC chỉ cho một consumer active trên mỗi queue và có standby để failover.
- [ ] Giải thích được cách kết hợp partition queue với SAC.
- [ ] Nhận diện được ảnh hưởng của concurrency, prefetch và retry đến thứ tự xử lý.
- [ ] Hiểu failover vẫn có thể dẫn đến redelivery và cần idempotency.
- [ ] Thiết kế được integration test trên RabbitMQ cho partition assignment và SAC.

## Kết luận

Partitioning chia luồng message theo khóa thành nhiều queue/partition để tăng song song và giữ các message cùng aggregate trên cùng luồng. Consumer dùng `partitioned`, `instanceCount` và `instanceIndex` để tham gia mô hình phân vùng của RabbitMQ Binder. Single-active-consumer là tính năng queue của RabbitMQ: nhiều consumer đăng ký nhưng chỉ một consumer active nhận message, các consumer khác chờ failover. Có thể kết hợp hai cơ chế để xử lý song song giữa các partition và duy trì một consumer active trên từng queue. SAC không tự bảo đảm thứ tự hoàn tất hoặc exactly-once; cần điều chỉnh concurrency/prefetch, acknowledgement và idempotency, đồng thời kiểm thử topology thực tế với đúng phiên bản Rabbit binder và RabbitMQ.
