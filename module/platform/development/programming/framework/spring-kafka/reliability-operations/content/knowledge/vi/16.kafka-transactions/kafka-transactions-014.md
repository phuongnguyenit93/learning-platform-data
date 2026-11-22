# Producer fencing trong transaction

Khi chạy Kafka transaction, Spring Kafka không chỉ cần bảo đảm việc ghi record và commit offset là nguyên tử; hệ thống còn phải xác định **producer nào đang có quyền đại diện cho một transactional identity**. Nếu một instance cũ bị treo, mất kết nối hoặc bị thay thế nhưng sau đó hoạt động trở lại, nó có thể tiếp tục gửi request như thể vẫn là owner. Kafka sử dụng **producer fencing** để ngăn một phiên producer đã lỗi thời tiếp tục commit transaction bằng danh tính đã được phiên mới tiếp quản.

Cơ chế này đặc biệt quan trọng ở hệ thống chạy nhiều replica, consumer group thường xuyên rebalance, rollout liên tục hoặc có luồng **read → process → write** sử dụng Kafka transaction. Tuy nhiên, fencing dựa trên `transactional.id` không tự giải quyết mọi tình huống zombie consumer; cần phân biệt producer epoch, consumer group ownership và các tác dụng phụ bên ngoài Kafka.

## 1. Producer fencing bảo vệ điều gì?

Một transactional producer có `transactional.id`. Broker Kafka sử dụng identity này để quản lý vòng đời transaction và cấp một **producer ID/epoch** cho phiên producer hiện hành. Khi producer khác khởi tạo cùng `transactional.id`, transaction coordinator xác lập thế hệ mới; các request thuộc thế hệ trước không còn hợp lệ.

~~~text
                transactional.id = inventory-worker-0

Instance A: Producer A ---------------------> Kafka transaction coordinator
                  epoch = 12                  (owner thế hệ cũ)
                      |
                  mạng bị gián đoạn
                      |
Instance B: Producer B ---------------------> Kafka transaction coordinator
                  epoch = 13                  (owner thế hệ mới)
                      |
                      +---- ghi + commit thành công
                      
Instance A: sống lại, cố gửi/commit bằng epoch = 12
                      |
                      +---- broker từ chối: producer đã bị fence
~~~

Nếu không có ranh giới thế hệ, hai phiên cùng sử dụng logical identity có thể tạo **split-brain**, tức cùng tin rằng mình đang được phép xử lý một công việc duy nhất. Fencing chặn phiên cũ ở tầng Kafka, kể cả khi tiến trình cũ chưa thực sự thoát.

Điểm cần nhớ: Kafka fencing áp dụng cho các thao tác Kafka của transactional producer mang identity bị thay thế. Nó **không tự hủy một HTTP request hay rollback một database transaction** đã thực hiện trước đó.

## 2. transactional.id, producerId và epoch

Các khái niệm thường xuất hiện cùng nhau nhưng không thể thay thế:

| Khái niệm | Vai trò |
|---|---|
| `transactional.id` | Danh tính logic ổn định của transactional producer; broker dùng để theo dõi vòng đời transaction qua các phiên producer. |
| Producer ID (PID) | Danh tính Kafka cấp cho producer để quản lý sequence và transaction. |
| Producer epoch | Thế hệ của PID/transactional identity; request với thế hệ không còn hợp lệ bị từ chối. |
| Transaction coordinator | Broker điều phối trạng thái transaction, producer identity và commit/abort. |
| Idempotent producer | Chống duplicate phát sinh do retry gửi record trong phạm vi producer ID/sequence. |
| Producer fencing | Ngăn producer phiên cũ tiếp tục thao tác sau khi identity của nó được producer mới tiếp quản. |

Ở cấp giao thức, producer gọi `initTransactions()`, làm việc với transaction coordinator thông qua cơ chế như `InitProducerId`. Với transactional ID đã tồn tại, Kafka có thể cấp thế hệ mới, làm mất hiệu lực những request đến từ thế hệ cũ. Ứng dụng **không tự đặt epoch** bằng cấu hình Spring.

Ví dụ diễn tiến:

1. Producer A khởi tạo `transactional.id=orders-shard-3`, nhận thế hệ hiện hành.
2. A bắt đầu transaction và gửi output, nhưng tạm mất kết nối trước khi commit.
3. Producer B khởi tạo với **cùng** `transactional.id` và chiếm thế hệ mới; coordinator xử lý transaction còn dở của phiên cũ theo giao thức.
4. B có thể bắt đầu transaction của mình sau khi quá trình khởi tạo hợp lệ hoàn tất.
5. A hoạt động trở lại; broker phát hiện request A dùng thế hệ cũ và từ chối.
6. A phải ngừng dùng producer session đã bị fence; không thể chỉ gọi lại `commitTransaction()` để giành quyền.

Producer fencing không xóa hay đảo ngược các transaction **đã commit hợp lệ** trước khi bị fence. Mục đích của nó là từ chối những thao tác không còn quyền thực hiện.

## 3. Vì sao fencing cần thiết khi Kafka transaction bị gián đoạn?

Kafka transaction có thể bao gồm nhiều record output và offset input consumer group. Khi toàn bộ Kafka work nằm trong cùng transaction:

~~~text
Consumer poll orders.in
         |
         v
Kafka transaction bắt đầu
         |
         +---- xử lý nghiệp vụ
         +---- send orders.out
         +---- send input offset vào transaction
         |
         +---- commit transaction
                  |
                  +---- output được commit
                  +---- offset được commit
~~~

Nếu producer của transaction đó đã bị một phiên mới fence trước lúc commit, phiên cũ **không được quyền hoàn tất transaction**. Với consumer downstream dùng `isolation.level=read_committed`, các record thuộc transaction chưa commit hoặc bị abort không được coi là dữ liệu đã commit để chuyển tới ứng dụng.

Trường hợp ngược lại — producer phiên cũ vẫn được commit dù owner mới đã chạy — có thể gây ra output từ hai phiên cùng đại diện cho một logical task. Producer epoch được dùng để bảo vệ ranh giới này.

Tuy nhiên, **exactly-once trong Kafka** chỉ áp dụng trong những ranh giới cụ thể: transactional output Kafka và consumer offset được đưa vào cùng transaction, cộng với cách đọc phù hợp. Fencing tự nó không bảo đảm mỗi lời gọi listener chỉ diễn ra một lần; listener có thể được gọi lại sau rollback hoặc rebalance.

## 4. Luồng read-process-write của Spring Kafka

Trong Spring Kafka, listener container có thể mở transaction trước khi gọi listener. `KafkaTemplate` tham gia transaction do container quản lý khi được cấu hình trên producer factory tương thích.

Ví dụ listener:

~~~java
@Component
public class OrderProcessorListener {

    private final KafkaTemplate<String, ProcessedOrder> kafkaTemplate;
    private final OrderService orderService;

    public OrderProcessorListener(
            KafkaTemplate<String, ProcessedOrder> kafkaTemplate,
            OrderService orderService) {
        this.kafkaTemplate = kafkaTemplate;
        this.orderService = orderService;
    }

    @KafkaListener(
            topics = "orders.in",
            groupId = "orders-processor")
    public void onOrder(ConsumerRecord<String, Order> record) {
        ProcessedOrder result = orderService.transform(record.value());
        kafkaTemplate.send("orders.out", record.key(), result);
    }
}
~~~

Với **transactional listener container** và KafkaTemplate được phối hợp đúng:

- Container bắt đầu transaction trước lần xử lý.
- Listener gửi output qua KafkaTemplate tham gia transaction hiện tại.
- Container gửi offset input vào transaction sau khi xử lý phù hợp.
- Thành công thì output và offset Kafka cùng commit.
- Exception khiến transaction rollback; record có thể được xử lý lại theo cơ chế recovery.
- Nếu producer bị fence, transaction cũ không thể commit hợp lệ; container cần xử lý lỗi ở cấp transaction/producer.

Nếu listener được tạo bằng một container **không** bật transaction, đoạn Java trên không tự có atomic read-process-write. Chỉ dùng tên `KafkaTemplate` hoặc chỉ bật idempotence ở producer không đồng nghĩa Kafka transaction đã được thiết lập.

## 5. Cấu hình Spring Boot: transaction-id-prefix

Spring Boot có thể bật Kafka transaction cho producer bằng `transaction-id-prefix`. Khi autoconfiguration phù hợp, Boot cung cấp `KafkaTransactionManager` và tích hợp với listener container mặc định.

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      transaction-id-prefix: "${APP_INSTANCE_ID:local}-orders-tx-"
      acks: all
    consumer:
      group-id: orders-processor
      enable-auto-commit: false
      properties:
        isolation.level: read_committed
~~~

Trong môi trường local một instance, prefix `local-orders-tx-` có thể tiện cho thử nghiệm. **Không để cùng giá trị mặc định này ở tất cả production replica.** Mỗi replica đồng thời cần không gian transactional ID riêng nếu chúng không cố ý đại diện cho cùng logical producer.

`DefaultKafkaProducerFactory` của Spring Kafka sử dụng prefix cùng suffix để tạo transactional ID cho những producer mà factory quản lý. Cách cấp suffix, cache và giới hạn số producer đồng thời phụ thuộc phiên bản và cấu hình factory. Vì vậy, cần bảo đảm không có hai factory/replica đang hoạt động cùng tạo ra một transactional ID đầy đủ.

Consumer downstream cần `read_committed` nếu yêu cầu không đọc record thuộc transaction bị abort. Đây là cấu hình **cách đọc**, không phải công tắc bật fencing.

### 5.1. Tạo transaction manager với factory tùy chỉnh

Khi ứng dụng không dùng hoàn toàn cấu hình mặc định của Boot, có thể khai báo manager:

~~~java
@Bean
KafkaTransactionManager<String, ProcessedOrder> kafkaTransactionManager(
        ProducerFactory<String, ProcessedOrder> producerFactory) {
    return new KafkaTransactionManager<>(producerFactory);
}
~~~

Listener container phải dùng transaction manager này, còn KafkaTemplate cần được tạo từ producer factory phù hợp để tham gia cùng transaction. Một số phiên bản Spring Kafka dùng API `setKafkaAwareTransactionManager(...)` để cấu hình container, trong khi API các phiên bản trước có thể khác; hãy sử dụng API đúng với dependency đang triển khai.

Không tạo hai producer factory có transactional ID trùng nhau nhưng quản lý transaction độc lập rồi giả định framework tự đồng bộ quyền sở hữu giữa chúng.

## 6. Cấp transactional ID khi chạy nhiều replica

Đây là nguồn phát sinh lỗi fencing phổ biến nhất trong Spring Kafka. Phải phân biệt **producer đồng thời** với **producer thay thế**.

| Mô hình | Quy tắc identity | Ý nghĩa |
|---|---|---|
| Active-active, nhiều instance xử lý độc lập | Prefix riêng cho từng instance đang hoạt động | Tránh các instance fence nhầm nhau. |
| Một logical worker có phiên thay thế | Identity ổn định cho chính logical worker khi muốn producer mới fence phiên cũ | Khi cùng ID được khởi tạo lại, phiên cũ mất quyền. |
| Một cluster có nhiều shard ổn định | Gắn identity với shard hoặc worker slot theo chính sách điều phối | Các shard tách biệt; phiên mới thay thế shard có thể dùng lại identity. |
| Pod được cấp ID ngẫu nhiên mỗi lần restart | Identity mới không trùng instance cũ | Tránh collision nhưng **không tự fence zombie** bằng cùng transactional ID; cần bảo vệ quyền sở hữu bằng cơ chế khác. |

Ví dụ hai replica active-active:

~~~text
Replica A:
  APP_INSTANCE_ID=orders-a
  transaction-id-prefix=orders-a-orders-tx-

Replica B:
  APP_INSTANCE_ID=orders-b
  transaction-id-prefix=orders-b-orders-tx-
~~~

Các prefix không giao nhau. Khi A và B cùng chạy, mỗi instance có thể dùng Kafka transaction của chính mình mà không fence producer của instance còn lại.

Với một **active-passive slot** mà chỉ một instance được phép đại diện cho slot đó, phiên thay thế có thể được thiết kế dùng lại identity ổn định của slot. Lúc đó producer mới có thể fence producer cũ **nếu chúng thực sự khởi tạo cùng transactional ID đầy đủ**. Tuy nhiên, chỉ đặt chung một prefix chưa đủ nếu hai process tạo ra các suffix khác nhau. Cần hiểu cách factory quản lý suffix và có cơ chế điều phối ownership ở tầng ứng dụng/orchestrator.

Đặc biệt tránh việc cả một cụm active-active dùng cùng prefix `orders-tx-`: với các factory có suffix trùng nhau, những producer sẽ giành transactional identity của nhau. Triệu chứng có thể là transaction bị abort, listener lỗi trong rollout và các instance liên tục restart.

## 7. Producer fencing và zombie consumer không hoàn toàn giống nhau

Một **zombie producer** là producer session mất quyền hợp lệ với transactional identity nhưng vẫn cố ghi/commit. Một **zombie consumer** là member cũ đã mất quyền sở hữu partition sau rebalance nhưng vẫn tiếp tục xử lý work đã nhận.

Hai cơ chế khác nhau:

1. **Transactional-ID fencing**: một producer mới dùng cùng `transactional.id` làm epoch cũ mất hiệu lực.
2. **Consumer-group fencing/ownership**: Kafka consumer group quản lý generation, member metadata và partition assignment. Những thao tác offset không còn hợp lệ có thể bị từ chối theo trạng thái group hiện tại.

Trong mô hình exactly-once mới của Kafka/Spring Kafka (thường gọi là **EOS V2**, liên quan KIP-447), consumer group metadata tham gia vào quá trình gửi offset của consumer group vào Kafka transaction. Điều này giúp broker kiểm tra ownership của consumer khi commit transactional offsets; ứng dụng không nhất thiết dùng cùng `transactional.id` trên những replica khác nhau để fence zombie consumer. Vì vậy, Spring Kafka khuyến nghị **transactional ID prefix duy nhất trên mỗi instance hoạt động** trong cấu hình EOS hiện hành.

Không được hiểu rằng `transactional.id` khác nhau tự động ngăn một instance cũ gọi database/API sau rebalance. Kafka bảo vệ offset và transaction theo cơ chế của Kafka, nhưng ngoài Kafka vẫn cần idempotency hoặc fencing token ở hệ thống đích nếu có yêu cầu single-owner mạnh.

### 7.1. Phân biệt các exception

| Exception/tình huống | Phạm vi | Ý nghĩa chính |
|---|---|---|
| `ProducerFencedException` | Transactional producer | Producer không còn quyền tiếp tục thao tác với transactional identity. |
| `InvalidProducerEpochException` | Kafka producer request | Epoch đi kèm request không còn hợp lệ. |
| `FencedInstanceIdException` | Static consumer group membership | Có sự xung đột hoặc thay thế member với `group.instance.id` trong consumer group. |
| Lỗi commit do group generation/member không hợp lệ | Consumer group/offset | Consumer không còn quyền commit offset như member hiện tại. |

Không sửa `transaction-id-prefix` để giải quyết mọi lỗi consumer group. Ngược lại, không sửa `group.instance.id` khi lỗi thực tế là hai transactional producers dùng cùng identity.

## 8. Một kịch bản fencing trong rollout

Giả sử deployment active-passive muốn bảo đảm chỉ một logical worker phát output.

~~~text
T0: Instance A xử lý order-100, transaction TA đang mở
T1: A bị pause dài, hệ thống khởi động instance B thay thế
T2: B lấy quyền với cùng transactional identity
T3: Coordinator cấp epoch mới, phiên A bị fence
T4: B xử lý record và commit transaction TB thành công
T5: A hoạt động lại, cố commit TA
T6: Broker từ chối TA; A nhận lỗi producer bị fence
~~~

Kết quả trong Kafka:

- TA không thể được A commit hợp lệ sau khi đã bị fence.
- TB có thể commit nếu B đáp ứng các điều kiện transaction/group ownership.
- Consumer `read_committed` không coi output TA bị abort là dữ liệu đã commit.
- Record đã xử lý nhưng input offset chưa được commit có thể được giao lại.
- Nếu A từng gọi API ngoài Kafka trước T1, API đó **không tự rollback** vì producer bị fence.

Trong active-active, hai instance hợp lệ **không nên** dùng chung transactional identity. Việc dùng identity riêng cùng Kafka consumer group metadata là mô hình khác với việc một singleton owner được thay thế bằng phiên mới có cùng identity.

## 9. Xử lý ProducerFencedException thế nào?

`ProducerFencedException` thường là lỗi **fatal đối với producer session đã bị fence**. Không xử lý nó như một timeout có thể retry vô hạn trên cùng object `KafkaProducer`.

Các bước xử lý đúng về mặt nguyên tắc:

1. Để transaction/container biết lỗi; không bắt rồi coi record đã thành công.
2. Không cố tiếp tục `send()` hoặc `commitTransaction()` trên producer cũ đã mất quyền.
3. Đóng/loại bỏ producer session lỗi theo cách framework quản lý.
4. Xác định instance nào đang là owner hợp lệ của transactional identity.
5. Tìm nguyên nhân duplicate identity, rebalance, rolling restart hoặc cấu hình producer factory.
6. Cho hệ thống hợp lệ khởi tạo producer session/transaction mới theo lifecycle chuẩn.
7. Xác nhận output và input offsets chỉ được commit bằng các transaction hợp lệ.

Không tự gọi `abortTransaction()` liên tục trên producer đã ở trạng thái fatal rồi hy vọng quay về trạng thái sử dụng bình thường. Kafka producer API phân biệt lỗi có thể phục hồi và lỗi fatal; với fencing, producer cũ phải ngừng được sử dụng.

### 9.1. Spring Kafka listener container

Một số phiên bản Spring Kafka hỗ trợ `ContainerProperties.setStopContainerWhenFenced(true)`. Khi bật tùy chọn này, container có thể dừng khi phát hiện producer fenced thay vì tiếp tục vòng xử lý. Đây là lựa chọn đáng cân nhắc nếu fencing đồng nghĩa instance đã mất quyền sở hữu và cần được orchestration thay thế/điều tra.

~~~java
factory.getContainerProperties().setStopContainerWhenFenced(true);
~~~

Cần xác định tác động của việc container dừng: deployment có restart policy hay cảnh báo không, consumer lag sẽ được ai tiếp quản, và instance cũ còn đang chạy những tác vụ ngoài Kafka nào? Tùy chọn này không giải quyết collision ở cấp cấu hình và không thay thế việc bảo đảm prefix duy nhất.

Việc container dừng, publish event lifecycle hay ném exception cụ thể có thể khác theo phiên bản Spring Kafka; nên dựa vào các log và kết quả integration test của phiên bản hiện tại.

## 10. Vì sao không retry ngay trên producer cũ?

Khi request bị từ chối vì epoch cũ, gửi lại cùng request với cùng producer session không tạo ra epoch hợp lệ. Đó không phải dạng lỗi mạng tạm thời mà client chỉ cần retry là hết.

So sánh:

| Loại lỗi | Hướng xử lý |
|---|---|
| Broker leader tạm thay đổi | Kafka client có thể retry theo cơ chế producer nếu còn trong giới hạn hợp lệ. |
| Request timeout chưa rõ kết quả | Xem semantics idempotence/transaction và timeout; không tự giả định kết quả đã thất bại hoàn toàn. |
| Transaction timeout | Transaction không còn hợp lệ; xử lý abort/khởi tạo transaction theo trạng thái producer. |
| Producer fenced | Producer session cũ đã mất quyền; cần ngừng dùng session và xác minh owner. |
| Deserialization/business error | Error handler hoặc AfterRollbackProcessor xử lý record, không đồng nghĩa producer đã bị fence. |

Nếu cố retry bằng cách tạo producer mới với **cùng transactional ID trên mỗi instance đang chạy**, hệ thống có thể rơi vào vòng lặp hai instance fence lẫn nhau. Phải sửa ownership/cấu hình thay vì chỉ tăng backoff.

## 11. Transaction timeout khác fencing

Kafka có những timeout ảnh hưởng transaction và producer:

- `transaction.timeout.ms`: giới hạn thời gian một transaction được mở; transaction coordinator có thể abort khi quá hạn.
- `delivery.timeout.ms`, `request.timeout.ms`: các ràng buộc truyền/gửi request của producer.
- `transactional.id.expiration.ms` ở broker: một transactional identity không được sử dụng trong một khoảng thời gian dài có thể hết hạn theo chính sách broker.
- Thời gian cache/độ tuổi producer ở Spring Kafka: có thể ảnh hưởng lúc một producer cached được tái sử dụng.

Một transaction bị timeout không nhất thiết là do producer khác fence. Ngược lại, producer bị fence có thể xảy ra ngay khi phiên mới cùng identity được khởi tạo, dù transaction cũ chưa đạt transaction timeout.

Đừng tăng transaction timeout để “chữa” cấu hình cùng `transactional.id` giữa các replica. Hai vấn đề khác nhau và cần chẩn đoán riêng.

### 11.1. Producer cache và maxAge

Spring Kafka có thể cache transactional producers để tái sử dụng. Nếu producer idle lâu trong cache, broker có thể hết hạn transactional identity trước khi client sử dụng lại nó. Một số phiên bản `DefaultKafkaProducerFactory` hỗ trợ `setMaxAge(Duration)` để thay thế producer cached trước khi đạt ngưỡng hết hạn phù hợp.

~~~java
defaultKafkaProducerFactory.setMaxAge(Duration.ofDays(3));
~~~

Giá trị trên chỉ minh họa. Đặt max age theo cấu hình broker và hành vi tải thật, với ngưỡng an toàn thấp hơn thời gian broker cho phép identity tồn tại khi idle. Không mặc định rằng broker nào cũng sử dụng cùng thời gian expiration.

`maxAge` giúp kiểm soát vòng đời producer cached; nó **không khắc phục** hai instance đồng thời dùng cùng transactional ID hay zombie ngoài Kafka.

## 12. Exactly-once, idempotence và fencing

Ba cơ chế thường bị nhầm:

- **Producer idempotence**: giúp loại bỏ duplicate do producer retry gửi record với sequence phù hợp.
- **Kafka transaction**: gom nhiều output record và transactional input offset thành đơn vị commit/abort nguyên tử.
- **Producer fencing**: loại bỏ khả năng commit của producer session đã lỗi thời đối với cùng transactional identity.

Ví dụ, idempotent producer có thể tránh ghi trùng do timeout khi gửi batch; nhưng nếu hai ứng dụng độc lập mỗi ứng dụng có producer ID khác nhau cùng tạo sự kiện nghiệp vụ trùng nhau, idempotence không nhận biết chúng là duplicate logic.

Tương tự, Kafka transaction không có nghĩa business logic sẽ không bị chạy lại. Sau rollback/rebalance, listener có thể xử lý cùng event thêm lần nữa. Những tác dụng phụ bên ngoài Kafka cần xử lý trùng theo event ID hoặc khóa nghiệp vụ.

Với `read_committed`, consumer chỉ thấy record transaction đã commit; đây là isolation level cho consumer, **không phải** phương pháp fence producer.

## 13. Tác dụng phụ ngoài Kafka: khoảng trống của fencing

Giả sử listener gọi một cổng thanh toán, rồi gửi event kết quả vào Kafka transaction.

~~~text
A nhận PaymentRequested
A gọi payment API -> thành công, tiền đã được thu
A mất kết nối với Kafka
B thay thế A và producer A bị fence
A cố commit Kafka transaction -> bị từ chối
B đọc lại PaymentRequested -> có thể gọi payment API lần nữa
~~~

Fencing bảo vệ việc commit Kafka của A, nhưng không đảo ngược việc thu tiền đầu tiên. Nếu B gọi lại API thiếu idempotency key, có nguy cơ thu tiền hai lần.

Các biện pháp cần thiết tùy nghiệp vụ:

- Dùng **idempotency key** ổn định từ event/order/payment ID cho API bên ngoài.
- Dùng unique constraint và trạng thái xử lý trong database để chống duplicate.
- Dùng transactional outbox khi cần lưu thay đổi database rồi phát Kafka event đáng tin cậy.
- Dùng saga/compensation khi nhiều hệ thống tham gia một nghiệp vụ không thể commit bằng cùng transaction.
- Với tài nguyên yêu cầu single-owner nghiêm ngặt, dùng lease và **fencing token** được storage/API kiểm tra trước khi chấp nhận thao tác.

Kafka producer epoch không tự động được kiểm tra bởi database hoặc HTTP server. Nếu hệ thống đích không hiểu epoch đó, nó không thể dựa vào producer fencing để từ chối lệnh của zombie.

## 14. Quan sát lỗi fencing trong production

Các dấu hiệu đáng theo dõi:

| Tín hiệu | Khả năng liên quan |
|---|---|
| `ProducerFencedException` tăng khi rollout | Trùng transactional ID hoặc owner mới đã thay phiên cũ. |
| `InvalidProducerEpochException` | Request mang epoch không còn hợp lệ. |
| Transaction abort/commit failure tăng | Lỗi transaction, fencing hoặc hạ tầng cần phân loại thêm. |
| Consumer group rebalance dày đặc | Instance churn, quá tải, session/poll issue. |
| Một số replica liên tục dừng container | Có thể đang bị fence hoặc cấu hình stop khi fenced. |
| Producer transaction init chậm | Coordinator, transaction state hoặc broker health có vấn đề. |
| Consumer lag tăng trong lúc rollout | Transaction rollback lặp hoặc member group không ổn định. |

Log hữu ích nên có:

- Application/service/environment, pod hoặc instance ID.
- Transactional ID prefix và full transactional ID khi có thể lấy từ log/client.
- Topic, partition, offset input và event ID.
- Consumer group ID, member metadata khi phù hợp.
- Thời điểm init transaction, commit/rollback và exception class.
- Thời điểm deployment/rebalance/instance restart.

Không nên ghi dữ liệu nhạy cảm hay toàn payload chỉ để điều tra. Với metric, tránh nhãn có cardinality quá cao như transaction ID chứa suffix thay đổi liên tục nếu hệ thống monitoring không chịu được.

### 14.1. Quy trình chẩn đoán

1. **Đọc exception chính xác**: producer fenced, invalid epoch hay lỗi consumer membership?
2. **Tìm transactional ID bị ảnh hưởng**: xác định prefix và suffix thực tế.
3. **Liệt kê những instance đang chạy**: có hai producer cùng dùng full transactional ID không?
4. **Xem thời điểm rollout/restart**: sự cố có trùng lúc overlap replica hoặc failover không?
5. **Kiểm tra consumer group ownership**: partition vừa rebalance hay member cũ còn xử lý?
6. **Xem producer cache/expiration**: có idle transaction producer lâu hơn chính sách broker không?
7. **Kiểm tra commit/abort và DLT**: transaction nào hợp lệ, offset nào đã commit, output nào nhìn thấy ở `read_committed`?
8. **Sửa nguồn cấp identity hoặc quy trình handover**: tránh retry vô hạn trên session mất quyền.
9. **Giám sát sau khôi phục**: lỗi fencing giảm, consumer lag phục hồi, không xuất hiện output ngoài dự kiến.

## 15. Kiểm thử producer fencing bằng hai producer

Integration test với broker thật có thể tạo hai transactional producers dùng cùng identity. Ví dụ Kafka client Java sau đây minh họa cách phiên mới fence phiên cũ:

~~~java
Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
props.put(ProducerConfig.TRANSACTIONAL_ID_CONFIG, "fencing-integration-test");

try (KafkaProducer<String, String> producerA = new KafkaProducer<>(props);
     KafkaProducer<String, String> producerB = new KafkaProducer<>(props)) {

    producerA.initTransactions();
    producerA.beginTransaction();
    producerA.send(new ProducerRecord<>("fencing-test", "key", "from-A")).get();

    // Khởi tạo B với cùng transactional.id: B trở thành thế hệ mới.
    producerB.initTransactions();
    producerB.beginTransaction();
    producerB.send(new ProducerRecord<>("fencing-test", "key", "from-B")).get();
    producerB.commitTransaction();

    // A đã mất quyền; commit của A không còn hợp lệ.
    try {
        producerA.commitTransaction();
        throw new AssertionError("Expected producer A to be fenced");
    } catch (ProducerFencedException expected) {
        // Không sử dụng lại producer A cho transaction khác.
    }
}
~~~

Ở các phiên bản/client và đường đi giao thức khác nhau, exception được bọc hoặc lộ diện dưới một loại Kafka exception liên quan epoch. Bài test nên xác nhận **phiên A không thể commit**, không chỉ phụ thuộc chính xác một tên class khi exception có thể được wrap. Ví dụ trên cần topic `fencing-test` đã tồn tại, broker có hỗ trợ transaction và timeout test hữu hạn.

Dùng consumer cấu hình `read_committed` để xác nhận output từ transaction A chưa commit không được giao như dữ liệu hợp lệ, còn output từ B có thể được đọc sau khi commit.

### 15.1. Các tình huống kiểm thử Spring Kafka

Ngoài test Kafka client, kiểm thử tích hợp nên bao gồm:

1. Hai replica active-active có prefix khác nhau; cả hai xử lý/commit transaction bình thường.
2. Hai replica cố ý có prefix/suffix trùng; một phiên bị fence, log và alert xuất hiện.
3. Restart một logical worker có identity ổn định; phiên cũ không thể commit sau handover.
4. Listener phát output rồi ném exception; downstream `read_committed` không đọc output của transaction bị rollback.
5. Consumer rebalance khi listener đang xử lý; kiểm tra transactional offset commit và redelivery.
6. Bật `stopContainerWhenFenced` nếu có hỗ trợ; xác nhận container dừng và hạ tầng quan sát đúng trạng thái.
7. Cached producer idle dài; kiểm tra `maxAge` và chính sách broker trong môi trường kiểm thử đại diện.
8. API ngoài Kafka thành công trước khi transaction rollback; xác nhận idempotency key ngăn double side effect.
9. DLT/recovery transactional khi record liên tục lỗi; xác nhận recovered offset và DLT output nhất quán.

Hãy dùng latch/điều kiện xác nhận transaction, offset và exception thay vì sleep cố định. Test producer fencing cần dọn producer/topic và không dùng identity trùng với các test khác đang chạy song song.

## 16. Các sai lầm cấu hình thường gặp

- **Dùng cùng `transaction-id-prefix` cho mọi replica active-active** khiến producer của các instance fence lẫn nhau.
- **Hiểu rằng prefix giống nhau luôn chắc chắn fence zombie** trong khi suffix thực tế có thể khác.
- **Cấp random prefix mỗi restart rồi chờ same-ID fencing**: producer mới không cùng identity với producer cũ.
- **Retry `ProducerFencedException` trên chính producer đã bị fence** mà không xử lý quyền sở hữu.
- **Xem transaction timeout như fencing** và tăng timeout thay vì sửa collision.
- **Cho rằng producer fencing tự ngăn mọi zombie consumer** mà bỏ qua group generation/transactional offset metadata.
- **Quên bật listener transaction manager** nhưng kỳ vọng offset input và Kafka output commit nguyên tử.
- **Đọc output bằng `read_uncommitted` trong test** rồi kết luận transaction bị rollback vẫn commit thành công.
- **Cho rằng Kafka fencing rollback được database/API**; tác dụng phụ ngoài Kafka vẫn phải chống trùng.
- **Bỏ qua producer cache expiration** khi thấy producer idle lâu rồi xuất hiện lỗi bất thường.
- **Chỉ tăng retry/backoff khi rollout** mà không xem full transactional ID và cách cấp identity.
- **Không đo lỗi fencing theo instance** khiến khó phân biệt một zombie bị loại đúng với hệ thống đang split-brain.

## 17. Checklist thiết kế transaction an toàn

Trước khi đưa Spring Kafka transactional listeners lên production, hãy xác định:

- Logical producer là gì: một instance, một shard hay một singleton task?
- Những producer nào được chạy **đồng thời** và do đó phải có transactional ID khác nhau?
- Khi thay owner, có cần reuse full transactional ID để fence producer phiên trước không?
- Spring Kafka factory có thể tạo bao nhiêu suffix/producer session đồng thời?
- Consumer group metadata và phiên bản EOS đang dùng bảo vệ stale ownership thế nào?
- Listener và KafkaTemplate có thực sự ở cùng transaction context?
- Input offsets có được gửi vào transaction trước khi commit output không?
- Downstream có dùng `isolation.level=read_committed` khi cần?
- Fencing exception được log, cảnh báo và xử lý như lỗi fatal của session cũ hay chưa?
- Có policy kiểm soát transaction timeout, cache max age và shutdown?
- Database/API ngoài Kafka có idempotency key, outbox hoặc fencing token riêng không?
- Có integration test cho handover, rollback, redelivery và producer fencing không?

**Producer fencing trong transaction** là cơ chế xác lập ai còn quyền commit vào Kafka khi một logical producer được thay thế. Cấu hình đúng bắt đầu từ việc phân biệt transactional identity với consumer group ownership, cấp prefix/suffix phù hợp topology và để Spring Kafka quản lý ranh giới transaction. Khi kết hợp với việc đọc `read_committed`, recovery sau rollback, observability và idempotency ngoài Kafka, hệ thống có thể chịu được restart, rebalance và zombie instance mà không để producer phiên cũ tiếp tục ghi/commit trái quyền.
