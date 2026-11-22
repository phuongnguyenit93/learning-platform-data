# Nhiều listener dùng cùng retry topic

Trong Spring Kafka, **non-blocking retry** chuyển record xử lý thất bại sang một hoặc nhiều retry topic để consumer của topic chính tiếp tục đọc những record khác. Một listener container khác sẽ đọc retry topic khi record đủ điều kiện thử lại. Cơ chế này thường được khai báo bằng `@RetryableTopic` hoặc một `RetryTopicConfiguration` phù hợp.

Khi **nhiều `@KafkaListener` cùng tiêu thụ một topic nguồn**, việc dùng chung tên retry topic có thể dẫn đến các hành vi không mong muốn: record của luồng nghiệp vụ A được chuyển tới listener B, cùng record được nhiều consumer group xử lý lại, hoặc DLT của hai luồng bị trộn lẫn. Đây là vấn đề của **topology, định danh topic và consumer group**, không chỉ là lựa chọn thời gian backoff.

Để vận hành bền vững, cần phân biệt ba tình huống: nhiều instance của *cùng một listener logic* để chia tải; nhiều listener có *nghiệp vụ độc lập* cùng đọc topic chính; và nhiều listener *chủ động dùng chung* một hàng đợi retry do kiến trúc tự thiết kế. Mỗi tình huống yêu cầu ranh giới topic và group khác nhau.

## 1. Retry topic hoạt động như thế nào?

Với non-blocking retry, khi listener xử lý record thất bại, Spring Kafka có thể publish record sang retry topic và để consumer chính xử lý record tiếp theo. Retry consumer nhận record, kiểm tra thời điểm được phép retry, rồi đưa record tới listener tương ứng khi đến hạn. Nếu số lần thử đã hết hoặc exception không retryable, record có thể đi tới Dead Letter Topic (DLT).

```text
orders (topic chính)
   |
   v
@KafkaListener xử lý nghiệp vụ
   |
   +---- thành công --------> hoàn tất, tiến offset nguồn
   |
   +---- lỗi retryable ----> orders-retry-... 
                                  |
                                  v
                            retry listener
                                  |
                     +------------+-------------+
                     |                          |
                  thành công                 tiếp tục lỗi
                     |                          |
                  hoàn tất                retry tiếp / DLT
```

Tên topic thực tế phụ thuộc retry topic suffix, backoff, số lần retry, suffixing strategy và cơ chế tái sử dụng retry topic của phiên bản Spring Kafka đang dùng. `orders-retry-...` ở sơ đồ chỉ là tên minh họa, không phải cam kết một chuỗi tên cố định.

Retry topic vẫn là **topic Kafka bình thường**. Nó có partition, retention, replication, ACL và các consumer group với committed offset riêng. Bản thân Kafka không biết record thuộc về Java method hay bean listener nào. Việc đưa record đến đúng nơi xử lý là trách nhiệm của cấu hình retry topology.

## 2. Ba kiểu “nhiều listener” cần phân biệt

| Tình huống | Chủ đích | Thiết kế retry thường phù hợp |
|---|---|---|
| Nhiều instance của cùng service và cùng listener logic | Cùng group chia partition để tăng throughput | Các instance dùng chung topology retry của cùng một luồng; Kafka phân phối partition theo group |
| Hai listener nghiệp vụ độc lập cùng subscribe một topic nguồn | Mỗi nghiệp vụ cần nhận và xử lý toàn bộ event | Dùng group ID độc lập và retry/DLT topic được tách cho từng nghiệp vụ |
| Hai listener khác nhau nhưng cùng group nguồn | Chia tải hoặc chia partition giữa hai handler | Cần bảo đảm handler tương đương về nghiệp vụ; nếu không, bản ghi sẽ chỉ đến một trong các handler và dễ gây sai kết quả |
| Nhiều handler cùng muốn xử lý một retry topic thủ công | Chủ động gom xử lý retry vào một đầu mối | Thiết kế dispatcher/owner duy nhất hoặc routing tường minh; không dựa vào sự trùng tên do `@RetryableTopic` tự tạo |

Ví dụ `billing-service` và `audit-service` cùng đọc `orders` nhưng phục vụ hai mục đích: billing tạo giao dịch, audit lưu lịch sử. Chúng phải có group ID khác nhau để mỗi dịch vụ đọc được toàn bộ event. Nếu chúng cũng cùng subscribe một retry topic, mỗi group có thể đọc **cả các record retry của dịch vụ còn lại**.

Ngược lại, nếu nhiều bản sao của `billing-service` dùng cùng group và cùng retry topology, đó thường là cách phân tải hợp lệ: mỗi partition của một retry topic được giao cho một member trong group retry tương ứng. Các instance phải dùng cùng code, schema và chính sách xử lý tương thích.

## 3. Vì sao hai `@RetryableTopic` có thể đụng tên?

Theo cách tạo topology tự động, Spring Kafka xây tên các retry topic từ topic chính cùng các hậu tố hoặc thông tin backoff. Nếu hai listener cùng subscribe `orders` và dùng cấu hình retry có hậu tố giống nhau, các topic mà framework muốn tạo hoặc subscribe có thể trùng tên.

Ví dụ minh họa tình huống không an toàn:

```java
@RetryableTopic(attempts = "4", backoff = @Backoff(delay = 1_000))
@KafkaListener(topics = "orders", groupId = "billing-service")
public void bill(OrderEvent event) {
    billingService.process(event);
}

@RetryableTopic(attempts = "4", backoff = @Backoff(delay = 1_000))
@KafkaListener(topics = "orders", groupId = "audit-service")
public void audit(OrderEvent event) {
    auditService.archive(event);
}
```

Hai listener có group ID khác nhau nên cả hai đọc topic `orders` độc lập. Tuy nhiên, nếu topology retry được tạo với cùng tên retry/DLT topic, chúng có thể cùng trỏ tới những topic phụ đó. Khi đó:

1. Billing xử lý lỗi và publish bản ghi sang retry topic có tên chung.
2. Retry consumer của billing đọc bản ghi bằng group retry của billing.
3. Retry consumer của audit, nếu subscribe cùng retry topic nhưng là một group khác, cũng có thể đọc bản ghi này.
4. Cả hai luồng xử lý có thể chạy những side effect khác nhau trên một bản ghi chỉ được dự định retry cho billing.

Nếu các retry consumer cùng group, Kafka chia partition cho các member, nhưng không bảo đảm record được giao đến **đúng listener nghiệp vụ đã tạo lần retry**. Khi khác nhóm consumer nhưng cùng topic, record có thể được xử lý nhiều lần bởi các nghiệp vụ không liên quan. Cả hai kiểu sai đều đáng tránh.

**Tách group ID của topic chính là điều kiện cần cho hai nghiệp vụ độc lập, nhưng chưa đủ để cô lập retry topic.** Cần tách tên và ownership của retry/DLT topology tương ứng.

## 4. Cô lập retry và DLT bằng hậu tố riêng

Với nhiều listener độc lập trên cùng topic nguồn, cách rõ ràng là đặt `retryTopicSuffix` và `dltTopicSuffix` **khác nhau cho từng luồng nghiệp vụ**. Khi đó, mỗi listener có cây retry/DLT riêng, dù chúng cùng đọc `orders`.

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0),
        retryTopicSuffix = "-billing-retry",
        dltTopicSuffix = "-billing-dlt",
        autoCreateTopics = "false")
@KafkaListener(
        id = "billingOrdersListener",
        topics = "orders",
        groupId = "billing-service")
public void bill(OrderEvent event) {
    billingService.processIdempotently(event);
}
```

Listener audit dùng hậu tố khác:

```java
@RetryableTopic(
        attempts = "3",
        backoff = @Backoff(delay = 2_000),
        retryTopicSuffix = "-audit-retry",
        dltTopicSuffix = "-audit-dlt",
        autoCreateTopics = "false")
@KafkaListener(
        id = "auditOrdersListener",
        topics = "orders",
        groupId = "audit-service")
public void audit(OrderEvent event) {
    auditService.archiveIdempotently(event);
}
```

Với cấu hình minh họa, topology có thể được hình dung:

```text
                       +--> billing-service
                       |      |
                       |      +--> orders-billing-retry[-...]
                       |      |           |
orders ----------------+      |           +--> orders-billing-dlt
                       |      |
                       +--> audit-service
                              |
                              +--> orders-audit-retry[-...]
                                          |
                                          +--> orders-audit-dlt
```

Các tên có `[-...]` biểu thị framework có thể thêm phần xác định delay/index. Tên cuối cùng cần được xác minh từ cấu hình và danh sách topic thực tế trước khi provision. Hai tập topic phụ phải **không giao nhau**.

`autoCreateTopics = "false"` trong ví dụ thể hiện mô hình provisioning topic có kiểm soát; các retry/DLT topic phải được tạo trước với tên và partition phù hợp. Nếu không có provisioning ngoài ứng dụng, cần thiết kế cơ chế tạo topic theo quy trình triển khai. Không chỉ sao chép ví dụ rồi kỳ vọng retry topic tự xuất hiện.

## 5. Consumer group không thay thế việc tách topic

Kafka lưu committed offset theo từng cặp **group ID + topic-partition**. Nếu hai group đọc cùng retry topic, chúng tiến offset độc lập; bản ghi vẫn còn đó để cả hai group cùng nhận.

| Retry topic | Group của consumer | Hành vi Kafka |
|---|---|---|
| `orders-shared-retry` | `billing-retry-group` | Nhận record trong topic theo offset riêng của billing |
| `orders-shared-retry` | `audit-retry-group` | Cũng nhận record trong topic theo offset riêng của audit |
| `orders-shared-retry` | Hai consumer cùng `shared-retry-group` | Các consumer chia partition, mỗi record được giao cho tối đa một consumer trong group tại một thời điểm |

Tình huống hai group khác nhau có thể gây **fan-out không mong muốn**. Tình huống cùng group có thể gây **định tuyến nhầm handler** nếu consumer không tương đương về nghiệp vụ. Việc chỉ đổi `group.id` không thể biến một retry topic chung thành kênh riêng cho mỗi listener.

Trong các phiên bản Spring Kafka hỗ trợ non-blocking retry, framework tạo các listener container và group ID phù hợp cho những topic được tạo ra. Cách đặt group ID cụ thể có thể phụ thuộc cấu hình listener và framework version; cần kiểm tra log startup và trạng thái consumer group thay vì giả định retry group ID luôn giống main group ID.

Khi hai nghiệp vụ cần xử lý toàn bộ event gốc, chúng phải có **main group ID độc lập**. Khi chúng cần retry độc lập, chúng cũng phải có **topic retry/DLT độc lập**. Hai quyết định bổ sung cho nhau.

## 6. Nhiều instance của cùng listener: khi nào dùng chung là đúng?

Không phải mọi trường hợp dùng chung retry topic đều có vấn đề. Một service chạy nhiều instance với cùng cấu hình listener và cùng một nhóm xử lý có thể dùng chung retry topology để tăng năng lực xử lý.

Ví dụ:

```text
orders
   |
   +--> billing instance A --+
   |                         |
   +--> billing instance B --+--> cùng group billing-service
                             |
                             v
                      retry topic của billing
                             |
                     +-------+-------+
                     |               |
                 retry A         retry B
                 cùng group retry của billing
```

Các instance phải triển khai cùng logic hoặc logic tương thích. Kafka chia partition giữa các consumer trong cùng group; không cần tạo hậu tố retry riêng cho từng pod/instance. Nếu tạo một retry topic riêng cho mỗi pod, ứng dụng có thể phát sinh quá nhiều topic, khó scale và khó giữ tiến độ khi pod bị thay thế.

Cần phân biệt **nhiều replica của cùng luồng** với **nhiều nghiệp vụ độc lập**. Chỉ trường hợp thứ hai mới cần tách retry topology theo tên nghiệp vụ, không phải theo số instance đang chạy.

## 7. Ranh giới ownership khi chủ động dùng chung retry topic

Đôi khi kiến trúc muốn dùng một retry queue chung cho nhiều loại event hoặc nhiều producer nghiệp vụ, ví dụ một dịch vụ xử lý lỗi tập trung. Điều này chỉ an toàn khi có **đầu mối tiêu thụ được chỉ định** và hợp đồng định tuyến rõ ràng.

Một thiết kế chủ động có thể gồm:

```text
orders / payments / shipments
            |
            v
  service phát record cần retry
            |
            v
     shared-retry topic
            |
            v
    shared-retry-dispatcher
            |
    +-------+--------+
    |       |        |
  order   payment  shipment
 handler  handler   handler
```

Ở mô hình này, dispatcher phải biết loại message, phiên bản schema, nghiệp vụ sở hữu và quy tắc retry. Nó cũng phải có idempotency, retry budget, cơ chế đặt lịch nếu cần trì hoãn, DLT và quan sát theo từng loại record. **Một `@KafkaListener` đọc topic dùng chung không tự có cơ chế trì hoãn non-blocking retry của `@RetryableTopic`**; phải sử dụng đúng retry-topic infrastructure hoặc tự xây dựng scheduler/consumer pause logic.

Không nên đạt mục tiêu dùng chung bằng cách để nhiều annotation `@RetryableTopic` vô tình tạo trùng tên và hy vọng framework tự định tuyến theo listener ID. Kafka topic không lưu thông tin “method nào phải nhận record” như một bảo đảm định tuyến độc lập.

Với hai luồng có retry policy, schema, transaction boundary hoặc owner khác nhau, tách topic thường dễ vận hành và an toàn hơn gom chung. Chỉ gom khi có lý do rõ về kiến trúc và quyền sở hữu xử lý.

## 8. DLT cũng phải được cô lập phù hợp

Nhiều nhóm phát hiện được xung đột retry topic nhưng vẫn để mặc định cùng một DLT. Điều này có thể khiến record thất bại từ nhiều luồng đổ chung vào nơi điều tra, khó xác định owner và chính sách replay.

Ví dụ billing và audit dùng retry suffix khác nhau nhưng cùng DLT `orders-dlt`:

```text
orders-billing-retry-* ----+
                           +----> orders-dlt
orders-audit-retry-* -------+
```

Nếu mỗi listener có DLT consumer của riêng mình trên cùng topic với group khác nhau, cả hai có thể đọc tất cả record DLT. Nếu cùng group, chúng chia nhau record mà không bảo đảm owner đúng. Điều này lặp lại vấn đề của retry topic.

Nên chọn một trong hai phương án:

1. **DLT riêng theo nghiệp vụ:** `orders-billing-dlt`, `orders-audit-dlt`, có consumer/runbook/replay process riêng.
2. **DLT tập trung có chủ đích:** một chủ sở hữu chung nhận toàn bộ record, phân loại bằng header hoặc envelope ổn định và chịu trách nhiệm routing/replay.

Không dùng DLT chung chỉ để giảm số topic mà chưa giải quyết quyền truy cập dữ liệu, retention, schema compatibility, replay và trách nhiệm xử lý sự cố.

## 9. Tên topic, số lần thử và chiến lược tái sử dụng

`@RetryableTopic` không nhất thiết tạo đúng một retry topic cho mọi lần retry. Số retry topic phụ thuộc lịch backoff và chiến lược đặt hậu tố/tái sử dụng. Với exponential backoff, framework có thể tạo nhiều topic theo delay. Với fixed delay, tùy phiên bản và cấu hình reuse strategy, một số lần retry có thể dùng chung một retry topic của **cùng một topology**.

Hai khái niệm không nên nhầm:

- **Tái sử dụng retry topic bên trong một topology:** nhiều lần thử của cùng listener logic dùng lại topic theo retry framework configuration.
- **Dùng chung retry topic giữa hai listener nghiệp vụ độc lập:** hai listener khác owner hoặc group vô tình subscribe/publish chung tên topic.

Chiến lược thứ nhất có thể là một tối ưu hợp lệ của Spring Kafka. Chiến lược thứ hai đòi hỏi thiết kế rõ ràng vì có nguy cơ crosstalk. `retryTopicSuffix` phải được chọn sao cho không đụng tên giữa các topology, kể cả khi cùng delay hoặc cùng số attempts.

Nên ghi lại bản đồ tên topic thực tế sau khi ứng dụng khởi động hoặc sau bước provisioning. Đừng chỉ dựa vào `@RetryableTopic(attempts = "4")` để đoán có bao nhiêu topic hoặc chúng được đặt tên ra sao.

## 10. Partition, ordering và độ trễ

Retry topics thường cần có số partition phù hợp với cách framework publish record lỗi và cách listener tiêu thụ. Nếu đích retry/DLT giữ nguyên partition gốc, topic đích phải có đủ partition để nhận partition đó. Khi topic nguồn tăng partition, các topic phụ cũng có thể cần được cập nhật theo thiết kế.

**Non-blocking retry có thể thay đổi thứ tự xử lý.** Khi một record được chuyển sang retry topic để chờ, listener của topic chính có thể xử lý record tiếp theo trước khi record lỗi được retry. Đối với nghiệp vụ phụ thuộc thứ tự theo key, như cập nhật số dư hoặc trạng thái đơn hàng, cần xem xét liệu out-of-order có được chấp nhận hay không.

Ví dụ:

```text
orders partition 0:
  offset 100: OrderConfirmed  --> lỗi, chuyển retry topic
  offset 101: OrderCancelled  --> xử lý thành công ở topic chính

Sau đó:
  retry offset 100 chạy lại
```

Nếu `OrderCancelled` phải chạy sau `OrderConfirmed`, việc dùng retry topic có thể phá vỡ invariant nghiệp vụ. Tách retry topic theo listener **không khắc phục ordering**. Cần thiết kế state transition idempotent, version checking, hoặc chọn blocking retry nếu thứ tự nghiêm ngặt là yêu cầu bắt buộc.

Ngoài ra, mỗi listener độc lập có lịch retry và backlog riêng. Khi billing bị outage, retry backlog của billing có thể tăng mà audit vẫn hoạt động bình thường. Việc cô lập topic giúp phân biệt áp lực tải, nhưng vẫn phải cân nhắc tổng số retry consumer, kết nối broker, partition và tài nguyên cluster.

## 11. Error classification và DLT handler theo từng luồng

Hai nghiệp vụ có thể phân loại cùng một exception khác nhau. Ví dụ lỗi từ một payment gateway có thể retryable với billing nhưng không liên quan tới audit. Nếu chúng dùng chung retry chain, policy và owner dễ bị nhập nhằng.

Với `@RetryableTopic`, có thể khai báo exclusion riêng theo listener:

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000),
        exclude = {
                InvalidBillingPayloadException.class,
                UnsupportedBillingVersionException.class
        },
        retryTopicSuffix = "-billing-retry",
        dltTopicSuffix = "-billing-dlt")
@KafkaListener(topics = "orders", groupId = "billing-service")
public void consumeBilling(OrderEvent event) {
    billingService.processIdempotently(event);
}
```

Đối với audit, exception classification và backoff có thể khác. Tách topology giúp mỗi nhóm có quyền điều chỉnh retry budget, chính sách DLT và runbook mà không gây ảnh hưởng trực tiếp tới nhóm khác.

Nếu cấu hình `@DltHandler`, cần kiểm tra handler thực tế được gắn với topology nào. Không giả định rằng chỉ vì có method `@DltHandler` trong cùng ứng dụng, record DLT từ các listener khác nhau sẽ luôn tự được định tuyến đến đúng handler khi topic name bị trùng.

## 12. Cấu hình topic provisioning và giới hạn tài nguyên

Tách retry/DLT topic theo nghiệp vụ làm tăng số lượng topic và partition. Đó là chi phí cần tính toán, không phải lý do để cố tình chia sẻ sai topology.

Giả sử có 8 luồng độc lập, mỗi luồng dùng một topic nguồn 12 partition, ba retry topic và một DLT. Nếu mỗi topic phụ cũng có 12 partition, tổng partition phụ sẽ là:

```text
8 luồng × (3 retry + 1 DLT) × 12 partition
= 384 partition phụ
```

Con số chỉ minh họa; số retry topic thật phụ thuộc cấu hình backoff/reuse. Khi lập kế hoạch phải tính cả replication, số replica vật lý, file handle, memory và network của broker. Có thể giảm số retry topic bằng chiến lược phù hợp, nhưng phải giữ ranh giới xử lý độc lập.

Nên provision topic qua IaC hoặc quy trình vận hành rõ ràng, cùng các thông số:

| Thuộc tính | Điều cần quyết định |
|---|---|
| Partition count | Mức song song và ánh xạ partition nguồn/đích |
| Replication factor | Khả năng chịu lỗi broker |
| `min.insync.replicas` | Yêu cầu độ bền khi producer dùng `acks=all` |
| Retention | Thời gian cần giữ record retry/DLT trong sự cố và điều tra |
| ACL | Service nào được publish/consume topic của từng luồng |
| Monitoring | Lag, tốc độ retry, lỗi publish, backlog DLT và tuổi record |

Nếu dùng `autoCreateTopics = "false"`, toàn bộ topic tương ứng phải tồn tại trước khi listener nhận traffic. Nếu dùng auto creation, phải kiểm tra cấu hình topic được tạo trong môi trường production, không mặc định các giá trị broker là phù hợp cho sự kiện quan trọng.

## 13. Quan sát: xác định record đang ở topology nào

Trong hệ thống có nhiều listener đọc cùng topic chính, metric ở mức topic chính không đủ cho biết retry của nghiệp vụ nào đang lỗi. Cần quan sát theo từng listener ID, group ID, retry topic và DLT.

Các tín hiệu nên thu thập:

- Số record được publish vào retry topic của từng luồng.
- Consumer lag và độ tuổi record chờ trên retry topic.
- Tỷ lệ thành công/thất bại của từng retry attempt và thời gian chờ thực tế.
- Số record vào DLT theo nghiệp vụ, exception class và schema version.
- Lỗi publish retry/DLT: timeout, authorization, serializer và partition mapping.
- Rebalance, số consumer retry, committed offset và tình trạng pause/resume.
- Chênh lệch giữa số record nguồn bị lỗi và số record được recovered thành công.

Một log phục vụ điều tra nên có `eventId`, topic gốc, partition, offset, listener ID hoặc owner, retry topic hiện tại, attempt, exception và destination. Không cần đưa event ID vào metric label vì cardinality quá cao. Nếu nhiều topology có cùng tên topic phụ, log khó phân biệt owner hơn; đó là tín hiệu cấu hình đáng kiểm tra.

Sơ đồ dashboard thường hữu ích:

```text
Orders event pipeline
  billing-service:
    main lag  | billing retry lag | billing DLT count
  audit-service:
    main lag  | audit retry lag   | audit DLT count
```

Nhờ cô lập tên topic, đội vận hành có thể tạm dừng hoặc sửa một luồng mà không phải động tới backlog retry của luồng khác.

## 14. Các tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Billing lỗi nhưng audit cũng nhận record retry của billing | Hai listener dùng cùng retry topic với group khác nhau | Đặt `retryTopicSuffix` riêng cho từng nghiệp vụ; kiểm tra các consumer đang subscribe topic phụ |
| Record retry được xử lý bởi sai method | Các listener khác logic dùng cùng retry topic và cùng group | Tách topology; không để group assignment thay cho routing nghiệp vụ |
| Một record xuất hiện ở hai DLT consumer | DLT name trùng, hai group đọc độc lập | Tách `dltTopicSuffix` hoặc chỉ định một DLT owner/dispatcher chung |
| Listener không nhận được retry sau deploy | Retry topic chưa được provision, ACL sai hoặc subscription/topic name không khớp | Kiểm tra topic thực tế, group, ACL và retry topic infrastructure |
| Nhiều topic phụ được tạo hơn dự kiến | Backoff/suffixing strategy hoặc reuse strategy tạo nhiều retry topic | Lập bảng tên topic và partition cho từng topology, đánh giá cấu hình reuse |
| Retry thành công nhưng side effect trùng | Record có thể được redeliver sau crash/rebalance; consumer khác group cùng đọc retry topic | Thiết kế idempotency và xác minh topic/group ownership |
| Audit bắt đầu xử lý không đúng thứ tự | Record cũ nằm ở retry topic trong khi record mới chạy qua main topic | Kiểm tra yêu cầu ordering; cân nhắc blocking retry hoặc version check |
| Một luồng bị nghẽn làm tăng tải toàn cluster | Retry storm, quá nhiều retry consumer hoặc DLT publisher gặp lỗi | Giới hạn backoff/attempt, giám sát capacity và dùng cơ chế giảm tải |

Khi điều tra sự cố, xác nhận **topic thực tế đang được publish và subscribe**, không chỉ thông số annotation trên source code. Hai annotation trông khác nhau vẫn có thể tạo trùng tên topic sau khi áp dụng suffixing strategy; ngược lại, một annotation có thể tạo nhiều topic retry mà tên không hiển thị đầy đủ trong code.

## 15. Cách triển khai an toàn khi thêm listener mới

Giả sử một ứng dụng đang có listener billing và muốn bổ sung listener fraud detection cũng đọc `orders`. Quy trình triển khai an toàn nên gồm:

1. Xác định fraud cần nhận **toàn bộ** event hay chia tải với billing. Nếu cần toàn bộ, dùng `group.id` riêng.
2. Xác định retry/backoff, exception classification và DLT owner của fraud.
3. Chọn `retryTopicSuffix` và `dltTopicSuffix` riêng, không đụng billing và các luồng đã tồn tại.
4. Xác định tên retry topic thực tế theo phiên bản Spring Kafka, lịch backoff và suffixing strategy.
5. Provision các topic phụ với partition, replication, retention và ACL phù hợp.
6. Gắn listener ID rõ ràng, bảo đảm framework tạo đúng retry/DLT consumer topology.
7. Dùng dữ liệu kiểm thử để làm lỗi chỉ ở billing, xác nhận audit/fraud không nhận record retry của billing.
8. Làm lỗi chỉ ở fraud, xác nhận record chỉ đi qua retry/DLT của fraud.
9. Kiểm tra committed offset, duplicate/idempotency, restart và rebalance của từng group.
10. Triển khai từng bước, quan sát lag và DLT rate theo luồng rồi mới tăng traffic.

Trong kiểm thử, nên dùng record có event ID và nguồn rõ ràng. Chỉ nhìn thấy retry topic có record là chưa đủ; cần xác nhận **listener nào thực sự xử lý record** và **có bao nhiêu lần side effect được thực hiện**.

## 16. Những nguyên tắc cốt lõi

1. Retry topic là topic Kafka bình thường; bản thân broker không biết listener method nào sở hữu record.
2. Nhiều replica cùng một listener logic có thể chia sẻ topology retry; không tạo suffix riêng theo pod.
3. Nhiều listener nghiệp vụ độc lập trên cùng topic chính thường phải có group ID riêng **và** retry/DLT topic riêng.
4. Đừng coi group ID riêng là đủ để cách ly record khi hai group vẫn đọc chung retry topic.
5. Đặt hậu tố retry và DLT duy nhất theo nghiệp vụ qua `retryTopicSuffix` và `dltTopicSuffix`.
6. Xác minh tên topic thực tế vì backoff, suffixing strategy và topic reuse có thể thay đổi topology được tạo.
7. Nếu thật sự dùng chung retry topic, cần một thiết kế dispatcher/ownership rõ ràng và cơ chế trì hoãn phù hợp, không phụ thuộc vào trùng tên tình cờ.
8. Non-blocking retry có thể làm thay đổi thứ tự xử lý; vẫn cần idempotency, schema compatibility và kiểm soát side effect.
9. Provision retry/DLT topic và giám sát theo từng luồng, không chỉ theo topic nguồn.
10. Kiểm thử crosstalk giữa các listener trước khi rollout để tránh record bị xử lý bởi sai nghiệp vụ hoặc bị replay ngoài ý muốn.

**Kết luận:** “Nhiều listener dùng cùng retry topic” không phải lúc nào cũng sai: nhiều bản sao của cùng một listener logic có thể chia sẻ retry topology để mở rộng. Nhưng khi các listener có nghiệp vụ hoặc consumer group độc lập, dùng chung retry topic do đụng tên dễ dẫn đến đọc chéo, xử lý trùng và DLT không rõ chủ sở hữu. Cách vận hành ổn định là định nghĩa rõ phạm vi mỗi luồng, đặt hậu tố retry/DLT riêng khi cần và xác nhận topology thực tế bằng kiểm thử cùng quan sát production.
