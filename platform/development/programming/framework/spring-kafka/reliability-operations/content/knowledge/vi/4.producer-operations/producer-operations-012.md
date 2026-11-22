# Producer fencing và zombie instance

Trong một hệ thống Spring Kafka chạy nhiều replica, có thể xảy ra tình huống một instance cũ bị mất kết nối hoặc bị treo nhưng chưa thực sự dừng. Trong lúc đó, hệ thống khởi động instance thay thế để tiếp tục xử lý. Khi instance cũ hoạt động trở lại, cả hai có thể cùng cố ghi dữ liệu bằng danh tính producer mà hệ thống xem là một logical producer. Kafka giải quyết tình huống này bằng **producer fencing**.

Producer fencing dùng `transactional.id` và producer epoch để bảo đảm chỉ phiên producer mới nhất sở hữu một transactional identity được phép tiếp tục thao tác transactional trên Kafka. Nó là cơ chế quan trọng trong luồng consume-process-produce có transaction, đặc biệt khi ứng dụng restart, failover hoặc chuyển quyền sở hữu giữa các instance.

## 1. Zombie instance là gì?

Zombie instance là một tiến trình cũ vẫn còn khả năng thực thi sau khi hệ thống đã quyết định thay thế hoặc thu hồi quyền sở hữu của nó. Tiến trình đó có thể bị treo do pause dài, mất mạng, lỗi điều phối container hoặc bị cô lập khỏi control plane. Sau đó nó tiếp tục chạy khi instance mới đã nhận nhiệm vụ.

Ví dụ, một dịch vụ xử lý đơn hàng chỉ nên có một producer chủ động phát sự kiện cho một logical worker:

```text
Thời điểm 1: worker-A đang hoạt động

        worker-A  ---- ghi transaction ----> Kafka

Thời điểm 2: worker-A bị pause/mất mạng; hệ thống khởi động worker-B

        worker-A  .... không phản hồi ....
        worker-B  ---- nhận quyền sở hữu ----> Kafka

Thời điểm 3: worker-A sống lại

        worker-A  ---- cố ghi tiếp ----------> Kafka
        worker-B  ---- đang là owner --------> Kafka
```

Nếu không có cơ chế fencing, worker-A có thể tiếp tục gửi dữ liệu dù worker-B đã nhận nhiệm vụ. Điều này tạo ra hai tiến trình cùng hành động như một producer logic, gây khó khăn cho việc bảo đảm thứ tự và tính nguyên tử của các transaction.

Zombie không nhất thiết là một process đã chết. Điểm quan trọng là nó đã mất quyền sở hữu theo quyết định của hệ thống nhưng vẫn có thể thực thi một phần công việc.

## 2. Kafka fencing hoạt động bằng transactional.id và epoch

Một transactional producer được cấu hình với `transactional.id`. Khi producer khởi tạo transaction support, nó đăng ký với transaction coordinator của Kafka thông qua `InitProducerId`. Coordinator cấp hoặc khôi phục producer identity và gắn một **epoch** với identity đó.

Epoch là số thế hệ của producer. Khi một producer mới khởi tạo với cùng `transactional.id`, coordinator tăng epoch và cấp quyền cho thế hệ mới. Các request transactional đến từ producer cũ mang epoch thấp hơn sẽ bị broker từ chối vì producer đó đã bị fence.

```text
transactional.id = orders-worker-0

1. worker-A gọi InitProducerId
   Kafka cấp producerId=P, epoch=4

2. worker-A bị pause; worker-B khởi tạo cùng transactional.id
   Kafka giữ logical producer identity và tăng epoch lên 5

3. worker-B gửi và commit transaction với epoch=5
   -> được chấp nhận

4. worker-A hoạt động trở lại và gửi/commit với epoch=4
   -> bị fence, broker từ chối
```

Nhờ đó, Kafka chỉ chấp nhận thao tác của epoch hiện hành cho transactional identity đó. Các thao tác thuộc transaction cũ chưa commit không thể được worker-A hoàn tất sau khi worker-B đã lấy quyền sở hữu. Consumer dùng `isolation.level=read_committed` sẽ không đọc các record thuộc transaction đã bị abort.

Producer fencing không xóa các record đã commit trước đó. Nó ngăn producer cũ tiếp tục thao tác với identity đã bị thế hệ mới chiếm quyền; transaction đang mở có thể bị abort hoặc được coordinator xử lý theo trạng thái transaction.

## 3. Vì sao fencing cần thiết cho transaction?

Kafka transaction có thể kết hợp việc ghi nhiều record output và commit offset input thành một đơn vị nguyên tử. Nhưng tính nguyên tử đó cần một producer có quyền sở hữu hợp lệ. Nếu hai phiên producer cùng có thể commit cho một logical identity, hệ thống sẽ không có ranh giới rõ ràng giữa owner cũ và owner mới.

Fencing tạo ra ranh giới thế hệ:

- Producer mới khởi tạo cùng `transactional.id` sẽ chiếm quyền bằng epoch mới.
- Producer cũ không thể tiếp tục gửi hoặc commit transaction bằng epoch đã lỗi thời.
- Transaction chưa commit của producer cũ không được consumer `read_committed` xem là dữ liệu đã commit.
- Producer mới có thể tiếp tục công việc với cùng logical identity sau khi quyền sở hữu được chuyển giao.

Điều này đặc biệt hữu ích khi ứng dụng restart hoặc failover. Nếu một transaction đang mở bị bỏ lại bởi phiên trước, coordinator có thể xác định trạng thái của nó khi producer mới khởi tạo cùng transactional identity.

Fencing cũng giúp phát hiện lỗi cấu hình: nếu hai instance đang hoạt động vô tình dùng cùng một transactional identity, một instance có thể liên tục fence instance còn lại. Đây thường là dấu hiệu cần sửa cách cấp identity hoặc cách triển khai replica.

## 4. Phân biệt transactional.id, producerId, epoch và idempotence

Các khái niệm này liên quan nhưng không thay thế nhau:

| Thành phần | Vai trò |
|---|---|
| `transactional.id` | Danh tính ổn định của một logical transactional producer; được dùng để coordinator nhận diện producer qua các phiên. |
| `producerId` | ID nội bộ Kafka gán cho producer để quản lý sequence và transaction. |
| `epoch` | Số thế hệ của producer identity; epoch mới làm mất hiệu lực các request từ epoch cũ. |
| Idempotent producer | Dùng producer ID và sequence để chống duplicate do retry ở tầng gửi trong một producer session. |
| Producer fencing | Thu hồi quyền của producer cũ khi một producer mới khởi tạo cùng `transactional.id`. |

Idempotence không tự giải quyết split-brain giữa hai instance. Hai instance có thể là hai producer độc lập với hai producer ID khác nhau; idempotence của từng producer không biết rằng chúng đang cùng đại diện cho một logical worker. Fencing dựa trên `transactional.id` mới giải quyết quyền sở hữu giữa các thế hệ của cùng identity.

Ngược lại, fencing cũng không thay thế idempotence. Producer transactional vẫn cần các bảo đảm gửi phù hợp để xử lý retry ở tầng producer. Khi dùng transaction, Kafka client thường yêu cầu cấu hình producer tương thích với idempotence; hãy để Spring Kafka và Kafka client áp dụng các mặc định tương thích của phiên bản đang dùng, hoặc kiểm tra các thuộc tính producer nếu bạn override cấu hình.

## 5. Cấp transactional.id đúng cách trong Spring Kafka

Spring Kafka thường cấu hình `transaction-id-prefix` trên producer. `DefaultKafkaProducerFactory` sử dụng prefix và suffix để tạo transactional ID cho các producer mà factory quản lý. Suffix cho phép một ứng dụng có nhiều producer transactional đồng thời mà không phải tự tạo một ID cho từng lần gửi.

Ví dụ cấu hình Spring Boot:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${APP_INSTANCE_ID:local}-
      acks: all
    consumer:
      properties:
        isolation.level: read_committed
```

Trong môi trường phát triển một process, giá trị `local` có thể đủ. Trong môi trường nhiều replica, `APP_INSTANCE_ID` phải được cấp theo chiến lược định danh của hệ thống. Không để tất cả replica cùng dùng giá trị mặc định `local`.

Ví dụ với hai replica active-active:

```text
Replica 0: APP_INSTANCE_ID=orders-worker-0
           transactional.id có prefix orders-worker-0-

Replica 1: APP_INSTANCE_ID=orders-worker-1
           transactional.id có prefix orders-worker-1-
```

Mỗi replica có prefix riêng nên không fence nhầm producer của replica khác. Trong mỗi replica, factory quản lý suffix cho các transactional producer được tạo đồng thời.

### 5.1 Chọn identity theo mô hình triển khai

Quy tắc quan trọng là: **các producer có thể hoạt động đồng thời phải có transactional ID khác nhau; các thế hệ thay thế của cùng một logical producer cần dùng lại identity nếu muốn fencing lẫn nhau.**

| Mô hình | Cách cấp identity | Lý do |
|---|---|---|
| Active-active, nhiều replica cùng xử lý độc lập | Mỗi replica có một prefix riêng, duy nhất khi đang chạy | Các replica không được fence lẫn nhau. |
| Active-passive, chỉ một owner cho một logical worker | Instance thay thế dùng lại prefix ổn định của logical worker | Instance mới sẽ fence phiên cũ nếu phiên cũ vẫn còn sống. |
| StatefulSet hoặc worker theo shard có ordinal ổn định | Dùng ordinal/shard làm một phần identity | Khi thay thế replica cùng slot, identity vẫn được tái sử dụng; các slot khác nhau vẫn riêng biệt. |
| Pod có tên ngẫu nhiên mỗi lần deploy | Tên pod mới tạo identity mới | Tránh va chạm nhưng không tự fence pod cũ; cần cơ chế điều phối để bảo đảm pod cũ đã mất quyền. |

Không dùng một prefix chung cho tất cả replica active-active. Nếu `orders-worker-0` và `orders-worker-1` cùng khởi tạo một transactional ID, chúng có thể liên tục fence nhau, gây transaction abort và lỗi xử lý.

Ở chiều ngược lại, nếu một logical worker active-passive luôn tạo prefix ngẫu nhiên mới mỗi lần restart, instance mới không dùng cùng transactional identity với instance cũ. Khi đó Kafka không thể dùng lần khởi tạo identity mới để fence phiên cũ. Nếu zombie vẫn có thể truy cập Kafka, cần một cơ chế ownership khác hoặc một identity ổn định cho logical worker.

### 5.2 Identity phải duy nhất trong phạm vi producer đang hoạt động

Đặt `APP_INSTANCE_ID` theo một nguồn định danh có chủ đích, ví dụ:

- StatefulSet ordinal kết hợp tên ứng dụng và môi trường.
- Logical shard ID được cấp bởi scheduler.
- Instance slot ổn định do nền tảng triển khai quản lý.
- ID riêng cho từng replica active-active.

Không dùng các giá trị như `localhost`, `default` hoặc một biến môi trường giống nhau trên mọi replica trong production. Cũng không tự tạo random prefix ở mỗi lần khởi động nếu mục tiêu là để phiên mới fence phiên cũ của cùng logical worker.

Nếu cùng một ứng dụng có nhiều `ProducerFactory` transactional độc lập, cần bảo đảm các dải transactional ID mà chúng tạo ra không giao nhau. Với cấu hình thông thường, nên dùng factory được quản lý thống nhất và để Spring Kafka cấp suffix. Khi tự cấu hình suffix strategy hoặc cache, phải bảo đảm đủ producer slot cho mức concurrency thực tế và không tái sử dụng suffix đang được một transaction khác giữ.

## 6. Kết hợp fencing với listener transaction

Trong mô hình consume-transform-produce, `KafkaTemplate` và listener container cần tham gia cùng một transaction thông qua cùng `ProducerFactory`. Producer fencing bảo vệ quyền sở hữu transactional producer; listener container vẫn chịu trách nhiệm điều phối offset đầu vào.

Một cấu hình Spring Kafka điển hình bật transaction qua `transaction-id-prefix`, sau đó gắn `KafkaTransactionManager` được tạo từ producer factory tương ứng vào listener container. Ví dụ phần khai báo transaction manager:

```java
@Bean
KafkaTransactionManager<String, Object> kafkaTransactionManager(
        ProducerFactory<String, Object> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
```

Listener dùng `KafkaTemplate` được tạo từ cùng producer factory đó:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        containerFactory = "orderListenerContainerFactory")
public void onOrder(ConsumerRecord<String, Order> record) {
    EnrichedOrder result = processor.enrich(record.value());
    kafkaTemplate.send("orders.enriched", record.key(), result);
}
```

Khi container bắt đầu transaction, producer transactional được lấy từ factory. Nếu một phiên mới khởi tạo cùng transactional ID và tăng epoch, thao tác tiếp theo của producer cũ sẽ bị broker từ chối. Lỗi fencing có thể xuất hiện khi gửi hoặc khi commit transaction, tùy thời điểm broker phát hiện epoch cũ.

`read_committed` ở consumer downstream bảo đảm chỉ đọc record thuộc transaction đã commit. Thuộc tính này không tự bật fencing; nó quy định consumer nhìn thấy trạng thái transaction như thế nào. Producer identity và transaction coordinator mới là phần thực hiện fencing.

## 7. Nhận biết lỗi producer bị fence

Khi producer cũ tiếp tục hoạt động sau khi identity đã được producer mới chiếm quyền, Kafka client có thể trả về các lỗi như:

- `ProducerFencedException` — producer bị một producer khác có cùng `transactional.id` fence.
- `InvalidProducerEpochException` — request mang epoch không còn hợp lệ đối với producer identity.

Lỗi có thể xuất hiện trong lúc gửi record, commit hoặc abort transaction. Vì vậy log của ứng dụng có thể cho thấy listener xử lý nghiệp vụ xong nhưng transaction không thể commit.

Đây là lỗi ownership mang tính fatal đối với producer session cũ. Không nên retry vô hạn trên cùng producer như với lỗi mạng tạm thời. Producer cũ đã mất quyền sở hữu; cần đóng session cũ và để tiến trình đúng quyền sở hữu tiếp tục. Trong Spring Kafka, cần xem log của listener container, transaction manager và producer factory để xác định lỗi xuất hiện ở bước nào.

Một số dấu hiệu vận hành cần chú ý:

- `ProducerFencedException` hoặc `InvalidProducerEpochException` xuất hiện lặp lại.
- Transaction abort tăng đột ngột khi rollout hoặc scale replica.
- Một số listener container liên tục restart hoặc không thể commit transaction.
- Hai pod cùng báo đang xử lý một logical worker/shard.
- Cấu hình `APP_INSTANCE_ID` giống nhau giữa nhiều replica hoặc thay đổi ngoài dự kiến sau restart.

Đừng chỉ tăng retry count khi gặp fencing. Retry có thể làm log dày hơn nhưng không khôi phục quyền sở hữu cho producer cũ. Trước hết cần xác định instance nào phải là owner và sửa cách cấp identity hoặc cách chuyển quyền.

## 8. Quy trình điều tra khi xảy ra fencing

Khi phát hiện lỗi, có thể điều tra theo thứ tự sau:

1. **Xác định transactional ID bị ảnh hưởng.** Lấy prefix, suffix và instance ID từ cấu hình hoặc log producer. Không suy đoán chỉ từ tên deployment.
2. **Liệt kê các instance đang chạy.** Đối chiếu pod/process, replica, shard hoặc logical worker đang giữ cùng identity.
3. **Kiểm tra thời điểm triển khai.** So sánh thời điểm rollout, restart, autoscaling, node pause hoặc failover với thời điểm xuất hiện lỗi.
4. **Xác định owner mong muốn.** Với active-active, mỗi replica cần identity riêng. Với active-passive, chỉ một instance được phép sở hữu identity tại một thời điểm.
5. **Loại bỏ phiên cũ khỏi đường xử lý.** Nếu instance cũ là zombie, dừng hoặc cô lập nó để tránh tiếp tục chạy nghiệp vụ ngoài Kafka.
6. **Sửa nguồn cấp identity.** Bảo đảm prefix duy nhất giữa các replica đồng thời và ổn định qua restart của cùng logical owner khi cần fencing.
7. **Theo dõi transaction sau khi khôi phục.** Xác nhận lỗi fencing và transaction abort trở về mức bình thường, consumer lag giảm và output chỉ chứa transaction đã commit khi đọc bằng `read_committed`.

Trong quá trình điều tra, giữ lại timestamp, instance ID, transactional ID, topic, partition, offset và exception. Các thông tin này giúp liên hệ lỗi producer với một lần rollout hoặc một lần chuyển quyền cụ thể.

## 9. Fencing không bảo vệ tác dụng phụ bên ngoài Kafka

Kafka chỉ fence các thao tác của producer trên Kafka. Nếu zombie instance đã gọi HTTP API, gửi email hoặc ghi database trước khi bị fence, Kafka không thể tự thu hồi tác dụng phụ đó. Ví dụ:

```text
worker-A: gọi payment API thành công
worker-A: bị pause trước khi commit Kafka transaction
worker-B: nhận cùng transactional.id và fence worker-A
worker-A: sống lại, Kafka từ chối commit transaction cũ

Kết quả: Kafka transaction của A không commit,
         nhưng payment API có thể đã được thực hiện.
```

Vì vậy, nếu processor có tác dụng phụ ngoài Kafka, cần thêm bảo vệ ở hệ thống đích:

- Dùng idempotency key ổn định, chẳng hạn event ID hoặc order ID, để API không thực hiện cùng một yêu cầu hai lần.
- Dùng unique constraint hoặc bảng deduplication trong database để ngăn áp dụng một event nhiều lần.
- Dùng transactional outbox khi thay đổi database và phát sự kiện cần được ghi nhận nhất quán.
- Với tài nguyên cần một owner duy nhất, dùng lease hoặc fencing token do hệ thống điều phối cấp và để chính storage/API kiểm tra token trước khi chấp nhận thao tác.

Một lease hết hạn chỉ là tín hiệu về quyền sở hữu. Nếu tiến trình cũ vẫn có thể gửi lệnh đến storage, storage cần kiểm tra fencing token hoặc cơ chế tương đương để từ chối lệnh từ owner cũ. Việc chỉ dừng heartbeat ở application không bảo đảm zombie không còn khả năng gây tác dụng phụ.

## 10. Phân biệt producer fencing với consumer fencing

Kafka có nhiều cơ chế ngăn một thành viên cũ tiếp tục thao tác sau khi quyền sở hữu đã thay đổi. Producer fencing và consumer group fencing giải quyết hai phạm vi khác nhau:

| Cơ chế | Đối tượng | Dấu hiệu thường gặp | Mục đích |
|---|---|---|---|
| Producer fencing | Transactional producer dùng `transactional.id` | `ProducerFencedException`, `InvalidProducerEpochException` | Chặn producer thuộc epoch cũ sau khi một producer mới chiếm cùng identity. |
| Consumer group generation/offset fencing | Consumer group member và offset commit | Lỗi commit do generation/member không còn hợp lệ | Chặn consumer cũ commit offset sau khi group rebalance hoặc quyền thành viên thay đổi. |
| Static membership fencing | Consumer dùng `group.instance.id` | `FencedInstanceIdException` | Chặn một consumer trùng static member identity trong cùng group. |

Không sửa `transaction-id-prefix` để xử lý lỗi consumer group, và cũng không sửa `group.instance.id` để xử lý `ProducerFencedException`. Hãy đọc đúng exception và xác định thành phần phát sinh lỗi.

## 11. Kiểm thử hành vi fencing

Kiểm thử tích hợp với Kafka broker giúp xác nhận ứng dụng phản ứng đúng khi một producer bị thay thế. Một kịch bản cơ bản có thể dùng hai transactional producer được cấu hình cùng `transactional.id`:

1. Khởi tạo producer A với identity `fencing-test-worker` và bắt đầu transaction.
2. Khởi tạo producer B với cùng identity. Việc khởi tạo B làm epoch hiện hành tăng lên.
3. Thử gửi hoặc commit bằng producer A; xác nhận client nhận lỗi fencing hoặc lỗi epoch không hợp lệ.
4. Gửi và commit transaction bằng producer B.
5. Đọc topic bằng consumer `read_committed`; xác nhận chỉ thấy record thuộc transaction đã commit.

Khi viết integration test, cần kiểm soát thời điểm khởi tạo và thao tác của hai producer để tránh race condition. Đóng producer và dọn topic sau test. Không dùng hai producer cùng transactional ID trong test chạy song song nếu chúng không chủ đích kiểm tra fencing.

Ngoài test ở cấp Kafka client, nên có kiểm thử triển khai cho cấu hình identity:

- Hai replica active-active nhận prefix khác nhau.
- Restart một replica dùng lại identity của logical slot tương ứng.
- Rollout không khiến mọi replica dùng chung prefix.
- Khi một phiên bị fence, listener không tiếp tục coi transaction đó là thành công.
- Downstream dùng `read_committed` không nhìn thấy output của transaction bị abort.

Các bài test này kiểm tra cả cơ chế broker lẫn cách nền tảng cấp instance identity cho Spring Kafka.

## 12. Các lỗi cấu hình thường gặp

- **Dùng cùng `transaction-id-prefix` cho tất cả replica:** các producer tranh cùng identity và liên tục fence nhau.
- **Dùng prefix ngẫu nhiên cho mọi lần restart của một logical worker:** instance mới không dùng lại identity cũ nên không fence được phiên cũ qua transactional ID.
- **Dùng một prefix chung cho nhiều `ProducerFactory` độc lập:** các suffix có thể xung đột nếu factory không phối hợp việc cấp identity.
- **Retry `ProducerFencedException` vô hạn:** producer cũ đã mất quyền sở hữu; retry không giải quyết được nguyên nhân.
- **Nhầm producer fencing với consumer group fencing:** dẫn đến sửa sai cấu hình và bỏ sót owner thực sự.
- **Cho rằng fencing rollback được database hoặc HTTP:** tác dụng phụ ngoài Kafka vẫn cần idempotency hoặc fencing ở hệ thống đích.
- **Cho rằng `read_committed` tự fence producer:** isolation level chỉ điều khiển dữ liệu consumer quan sát; nó không cấp quyền cho producer.
- **Rollout hai instance cùng giữ một logical identity mà không có kế hoạch chuyển quyền:** instance mới có thể fence instance cũ ngay khi khởi tạo, làm transaction đang chạy thất bại trong thời gian chuyển giao.

## 13. Checklist vận hành cho producer fencing

Trước khi triển khai transactional producer, hãy xác định:

- Mỗi logical producer là gì: một replica, một shard, một worker slot hay một singleton service?
- Những instance nào được phép chạy đồng thời và identity nào phải duy nhất giữa chúng?
- Khi restart hoặc failover, instance mới có cần dùng lại identity của logical owner cũ để fence zombie không?
- Nền tảng có bảo đảm dừng instance cũ trước khi instance mới nhận việc không?
- `KafkaTemplate` và listener container có dùng producer factory phù hợp với transaction manager không?
- Consumer downstream có dùng `read_committed` khi cần loại bỏ record từ transaction chưa commit hoặc đã abort không?
- Database và API bên ngoài có idempotency key hoặc fencing token riêng không?
- Log có đủ instance ID, transactional ID, topic, partition, offset và exception để điều tra không?

Producer fencing là lớp bảo vệ quyền sở hữu ở phía Kafka. Thiết kế tốt bắt đầu từ việc định nghĩa logical producer, cấp transactional ID đúng với topology triển khai, và có quy trình chuyển owner rõ ràng. Khi kết hợp với idempotency ở các hệ thống bên ngoài, ứng dụng có thể xử lý restart, failover và zombie instance mà không để phiên producer cũ tiếp tục commit dữ liệu Kafka.
