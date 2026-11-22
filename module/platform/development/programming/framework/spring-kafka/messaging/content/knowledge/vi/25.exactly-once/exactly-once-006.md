# EOSMode và phiên bản client

Exactly-once semantics (EOS) trong Spring Kafka giúp một luồng consume-process-produce ghi kết quả Kafka và xác nhận offset đầu vào như một đơn vị transaction. Khi transaction commit, output record và offset được commit cùng nhau; khi transaction abort, cả output lẫn offset đều không được xem là đã commit. Consumer dùng `read_committed` chỉ đọc các record thuộc transaction đã commit.

Khả năng này phụ thuộc vào phiên bản Kafka broker, thư viện `kafka-clients` và Spring Kafka. Spring Kafka cung cấp hai mô hình lịch sử là `EOSMode.V1` và `EOSMode.V2`. Chọn đúng mode và đúng phiên bản client giúp tránh cấu hình không tương thích, đồng thời xác định cách producer được cấp phát và cách broker fencing một consumer cũ sau rebalance.

## 1. EOS bảo đảm điều gì?

Trong một listener consume-transform-produce, ứng dụng đọc một record đầu vào, xử lý và gửi một hoặc nhiều record đầu ra. Nếu chỉ gửi output rồi commit offset bằng hai thao tác độc lập, có thể xảy ra:

- Output đã được ghi nhưng offset đầu vào chưa commit; khi consumer đọc lại, output có thể bị ghi lần nữa.
- Offset đầu vào đã commit nhưng output chưa được ghi; sự kiện đầu vào bị bỏ qua dù kết quả chưa tồn tại.

Kafka transaction gộp việc publish output và việc ghi offset của consumer vào cùng một transaction Kafka. Khi transaction commit, cả hai cùng có hiệu lực. Khi transaction abort, consumer đọc lại record đầu vào và output của transaction bị abort không được consumer `read_committed` nhìn thấy.

```text
Consumer poll input record
          |
          v
Begin Kafka transaction
          |
          v
Process record -> KafkaTemplate.send(output)
          |
          v
Send input offset to transaction
          |
          v
Commit transaction
     /          \
  success       abort
    |              |
output + offset   output và offset không commit
đều commit        input có thể được đọc lại
```

EOS bảo vệ luồng dữ liệu bên trong Kafka. Nó không tự động làm cho thao tác gọi REST, gửi email hoặc cập nhật database quan hệ trở thành exactly-once. Những side effect bên ngoài Kafka vẫn cần idempotency, outbox hoặc một cơ chế phối hợp riêng.

## 2. EOSMode V1 và V2 khác nhau thế nào?

`EOSMode` mô tả cách Spring Kafka tạo và fencing transactional producer trong listener container.

| Đặc điểm | EOSMode.V1 | EOSMode.V2 |
| --- | --- | --- |
| Mô hình fencing | Dùng transactional producer gắn với từng partition được xử lý | Dùng consumer group metadata để broker fencing producer cũ khi group thay đổi |
| Phạm vi producer | Có thể cần producer theo partition | Có thể tái sử dụng producer theo listener thread |
| Khả năng mở rộng | Nhiều producer hơn khi có nhiều partition | Giảm số producer và phù hợp hơn với concurrency cao |
| Yêu cầu broker | Kafka hỗ trợ transaction, từ 0.11.0.0 | Kafka 2.5.0 trở lên, có hỗ trợ KIP-447 |
| Trạng thái trong Spring Kafka | Mô hình tương thích cũ; đã bị deprecated ở các dòng mới hơn | Mô hình hiện đại; là mode duy nhất trong Spring Kafka 3.0 trở lên |

V1 dùng transactional ID riêng theo group/topic/partition để bảo đảm chỉ producer đang sở hữu partition mới có thể hoàn tất transaction của partition đó. Cách này có thể tạo nhiều producer khi ứng dụng có nhiều partition.

V2 tận dụng thay đổi trong Kafka 2.5 (KIP-447): producer gửi consumer group metadata khi đưa offset vào transaction. Broker có thể phát hiện producer thuộc một consumer generation cũ và fencing nó. Nhờ vậy Spring Kafka có thể dùng producer theo listener thread thay vì cần một producer riêng cho mỗi partition.

Với dự án mới, nên dùng EOS V2 trên broker tương thích. Không nên chọn V1 chỉ vì một ví dụ cũ đang dùng mode đó; cần xác định phiên bản Spring Kafka và broker thật sự đang chạy.

## 3. Quan hệ giữa Spring Kafka, kafka-clients và broker

Ba phiên bản cần được xem xét riêng:

- **Spring Kafka:** cung cấp listener container, transaction manager, producer factory và cách tích hợp EOS.
- **Kafka client (`kafka-clients`):** thư viện Java mà Spring Kafka dùng để giao tiếp với broker; API và giao thức client phải hỗ trợ cơ chế EOS được chọn.
- **Kafka broker:** cụm Kafka phải hỗ trợ transaction và các giao thức fencing/consumer group metadata tương ứng.

Các mốc quan trọng:

| Mốc | Ý nghĩa |
| --- | --- |
| Kafka 0.11.0.0 | Ra mắt transactional producer và idempotent producer; là nền tảng cho EOS V1 |
| Kafka 2.5.0 | Bổ sung thay đổi giao thức cần cho EOS V2 (KIP-447) |
| Kafka Java client 2.5.0 | Có API consumer group metadata cần để gửi offset vào transaction theo EOS V2 |
| Spring Kafka 2.5 | Bổ sung hỗ trợ EOS V2 để tận dụng broker Kafka 2.5+ |
| Spring Kafka 2.8 | EOS V1 được đánh dấu deprecated; V2 là hướng dùng được khuyến nghị |
| Spring Kafka 3.0+ | Chỉ còn EOS V2; cần broker Kafka 2.5+ |

Mốc broker tối thiểu cho V2 không có nghĩa mọi phiên bản `kafka-clients` đều có thể dùng với mọi Spring Kafka. Hãy dùng phiên bản `kafka-clients` được Spring Kafka hoặc Spring Boot dependency management quản lý. Nếu override thủ công, phải kiểm tra ma trận tương thích của đúng release Spring Kafka, client và broker. Tránh nâng riêng `kafka-clients` lên một major version không được Spring Kafka hiện tại hỗ trợ.

Với EOS V1, broker phải hỗ trợ transaction (Kafka 0.11.0.0 trở lên). Với EOS V2, broker và Kafka Java client cần từ 2.5.0 trở lên để hỗ trợ consumer group metadata trong transaction. Đây là mức tối thiểu cho tính năng; phiên bản client thực tế vẫn phải nằm trong phạm vi được release Spring Kafka đang dùng hỗ trợ. Dùng client version do BOM của framework quản lý sẽ an toàn hơn việc chỉ chọn client theo phiên bản broker.

## 4. Cấu hình transactional producer trong Spring Boot

Để dùng Kafka transaction, producer cần `transactional.id`. Khi sử dụng Spring Boot, có thể cấu hình transaction ID prefix:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${HOSTNAME:local}-orders-
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      properties:
        isolation.level: read_committed
```

`transaction-id-prefix` cho phép Spring Kafka tạo transactional ID riêng cho từng producer được cấp từ factory. Prefix phải duy nhất giữa các instance ứng dụng đang chạy đồng thời. Nếu hai instance dùng cùng prefix và tạo producer có cùng suffix, chúng có thể fencing lẫn nhau và gây lỗi transaction.

Khi prefix được cấu hình, Spring Boot có thể tự cấu hình `DefaultKafkaProducerFactory` ở chế độ transaction và cung cấp `KafkaTransactionManager` cho producer factory đó. Hãy kiểm tra cấu hình thực tế nếu ứng dụng tự khai báo producer factory hoặc transaction manager.

`acks=all` và idempotence giúp producer bảo đảm độ tin cậy khi gửi; transactional producer còn cần cấu hình transaction ID. Khi `transactional.id` được thiết lập, Kafka producer yêu cầu idempotence và các thiết lập tương thích. Nên để client áp dụng mặc định tương thích hoặc cấu hình theo tài liệu phiên bản client thay vì override các giá trị xung đột.

Consumer `read_committed` chỉ đọc record đã commit. Nếu consumer dùng `read_uncommitted`, nó có thể nhìn thấy record từ transaction bị abort, làm mất ý nghĩa của EOS ở phía đọc.

## 5. Chọn EOSMode trên listener container

Trong những phiên bản Spring Kafka còn cho phép cấu hình cả hai mode, EOS mode thuộc `ContainerProperties` của listener container. Ví dụ cấu hình V2:

```java
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.listener.ContainerProperties;

factory.getContainerProperties()
        .setEosMode(ContainerProperties.EOSMode.V2);
```

Với Spring Kafka 3.0 trở lên, V2 là mode duy nhất nên không cần chọn V1/V2 để chuyển đổi. API cấu hình mode có thể thay đổi theo major version; khi nâng cấp, hãy kiểm tra Javadoc của `ContainerProperties` trong đúng dependency thay vì sao chép đoạn code từ tài liệu của release khác.

Trong nhiều ứng dụng Spring Boot, chỉ cần cấu hình transaction ID prefix để kích hoạt Kafka transaction cho listener container. Nếu ứng dụng có factory riêng, cần bảo đảm factory sử dụng producer factory/transaction manager đã cấu hình transaction và container có transaction manager phù hợp.

## 6. Producer và listener tham gia cùng Kafka transaction

Khi listener container được cấu hình transaction, container bắt đầu Kafka transaction trước khi gọi listener. Các lệnh `KafkaTemplate.send()` bên trong listener tham gia transaction đang mở. Sau khi listener kết thúc thành công, container gửi offset đầu vào vào transaction rồi commit. Nếu listener ném exception, transaction bị abort và record đầu vào có thể được giao lại.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
class PaymentEventListener {

    private final KafkaTemplate<String, PaymentAccepted> kafkaTemplate;

    PaymentEventListener(
            KafkaTemplate<String, PaymentAccepted> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(topics = "payment-requests")
    public void onPayment(PaymentRequest request) {
        PaymentAccepted result = process(request);
        kafkaTemplate.send(
                "payment-events",
                request.paymentId(),
                result);
    }
}
```

Ví dụ giả định listener container đã được cấu hình transaction và `KafkaTemplate` dùng cùng producer factory. Không tự gọi `executeInTransaction()` bên trong một listener đã có transaction đang hoạt động trừ khi cần transaction độc lập và hiểu rõ semantics; transaction lồng nhau không tự tạo một transaction phân tán.

Trong record listener, transaction thường gắn với lần gọi listener cho record. Với batch listener, ranh giới transaction gắn với lần gọi listener cho batch. Cần chọn listener mode và acknowledgment phù hợp với yêu cầu xử lý.

## 7. EOS V2, concurrency và fencing

Trong môi trường nhiều consumer instance, rebalance có thể chuyển partition từ consumer cũ sang consumer mới. Một consumer cũ có thể vẫn đang chạy tác vụ sau khi đã mất quyền sở hữu partition. Nếu nó tiếp tục commit transaction, dữ liệu có thể xung đột với consumer mới.

V2 dùng consumer group metadata khi gửi offset vào transaction. Broker kiểm tra generation và member metadata; producer cũ bị fencing nếu không còn đại diện cho consumer hợp lệ của group. Điều này hỗ trợ concurrency và rebalance mà không cần transactional producer riêng cho từng partition.

Prefix transaction ID phải duy nhất theo instance ứng dụng. Bên trong một instance, Spring Kafka quản lý suffix cho các producer theo thread. Khi triển khai nhiều replica, hãy tạo prefix khác nhau cho từng replica, ví dụ dựa trên hostname hoặc pod identity. Prefix phải ổn định trong vòng đời instance nhưng không được trùng giữa các instance đang hoạt động.

Fencing exception có thể xuất hiện khi một producer cũ bị thay thế, prefix bị trùng hoặc transaction ID bị tái sử dụng sai cách. Hãy xem log transaction coordinator, consumer group rebalance và cấu hình transaction ID để phân biệt fencing dự kiến với lỗi cấu hình.

## 8. Những gì EOS không bao phủ

EOS trong Kafka không tự bảo đảm exactly-once cho mọi side effect trong listener. Ví dụ, listener cập nhật database rồi gửi Kafka trong cùng Kafka transaction: nếu Kafka transaction abort, database transaction không tự rollback trừ khi có cơ chế phối hợp transaction riêng. Listener có thể được gọi lại và cập nhật database lần nữa.

| Tác vụ | EOS Kafka bảo vệ? | Cách xử lý bổ sung |
| --- | --- | --- |
| Gửi output record sang Kafka | Có, nếu gửi trong transaction của listener | Dùng `KafkaTemplate` cùng producer factory/transaction |
| Commit offset đầu vào | Có, khi container gửi offset vào cùng Kafka transaction | Cấu hình listener container transaction |
| Chỉ đọc record đã commit | Có, với `isolation.level=read_committed` | Cấu hình consumer isolation |
| Cập nhật database quan hệ | Không tự động | Outbox, idempotency hoặc distributed transaction được thiết kế rõ ràng |
| Gọi REST, gửi email hoặc thao tác filesystem | Không | Idempotency key, outbox hoặc quy trình bù |

Nếu listener cần cập nhật database và phát Kafka event, Transactional Outbox thường là lựa chọn thực tế. Nếu consumer cần cập nhật database từ một sự kiện Kafka, hãy ghi event ID đã xử lý và thay đổi nghiệp vụ trong cùng database transaction để chống giao lặp.

## 9. Lưu ý khi nâng cấp phiên bản

Khi nâng Spring Kafka hoặc Kafka client, cần kiểm tra các điểm sau:

1. Xác định phiên bản Spring Boot và Spring Kafka thực tế; không suy ra chỉ từ phiên bản broker.
2. Kiểm tra phiên bản `kafka-clients` được BOM quản lý và tránh override không có lý do.
3. Xác minh broker tối thiểu: EOS V1 cần broker hỗ trợ transaction từ 0.11; EOS V2 cần broker 2.5+.
4. Nếu nâng lên Spring Kafka 3.0+, bỏ cấu hình V1 và xác minh toàn bộ broker hỗ trợ V2.
5. Kiểm tra transaction ID prefix duy nhất trên mọi replica.
6. Xác minh consumer dùng `read_committed` nếu cần ẩn record từ transaction abort.
7. Kiểm tra quyền ACL cho transactional ID và topic; broker phải cho phép producer sử dụng transaction.
8. Kiểm thử rebalance, producer fencing và transaction abort trên môi trường tương tự production.

Không nâng riêng client jar để giải quyết một lỗi EOS trước khi kiểm tra phiên bản Spring Kafka, broker và dependency management. Lệch version có thể tạo lỗi API hoặc giao thức khó chẩn đoán hơn vấn đề ban đầu.

## 10. Kiểm thử EOSMode và tương thích client

Một bài kiểm thử tích hợp nên chứng minh output và offset có cùng kết quả commit:

- Gửi một input record và xác minh listener publish đúng output record.
- Làm listener ném exception sau khi đã gọi `KafkaTemplate.send()`; xác minh output transaction bị abort và consumer `read_committed` không đọc thấy output đó.
- Xác minh input offset chưa được commit trong transaction abort và record được giao lại.
- Cho listener chạy thành công; xác minh output xuất hiện và input offset được commit cùng transaction.
- Thực hiện rebalance khi listener đang xử lý; xác minh producer cũ bị fencing và không thể commit transaction sau khi mất quyền sở hữu.
- Chạy consumer với `read_uncommitted` trong môi trường test để thấy khác biệt, sau đó bảo đảm cấu hình production là `read_committed`.
- Kiểm tra transaction ID prefix trên nhiều instance không bị trùng.

Ngoài kết quả functional, cần theo dõi số transaction commit/abort, producer fencing, transaction timeout, lỗi coordinator và thời gian xử lý transaction. Transaction timeout quá ngắn có thể làm giao dịch bị abort khi listener xử lý lâu; quá dài có thể giữ tài nguyên và làm chậm phục hồi.

## 11. Checklist triển khai

- [ ] Đã xác định rõ phiên bản Spring Kafka, `kafka-clients` và broker.
- [ ] EOS V2 chỉ được dùng khi broker từ Kafka 2.5 trở lên.
- [ ] Spring Kafka 3.0+ được cấu hình theo EOS V2; không còn phụ thuộc V1.
- [ ] `transaction-id-prefix` được cấu hình và duy nhất giữa các instance.
- [ ] Producer factory và listener container thực sự tham gia Kafka transaction.
- [ ] `KafkaTemplate` trong listener dùng đúng producer factory để tham gia transaction đang mở.
- [ ] Consumer dùng `isolation.level=read_committed` khi cần chỉ đọc record đã commit.
- [ ] ACL transactional ID và topic cho phép producer commit transaction.
- [ ] Side effect ngoài Kafka có idempotency hoặc cơ chế Outbox/phối hợp riêng.
- [ ] Đã kiểm thử commit, abort, redelivery, rebalance và fencing.

`EOSMode` quyết định cách Spring Kafka quản lý producer và fencing trong listener container; phiên bản broker và `kafka-clients` quyết định giao thức cần thiết có được hỗ trợ hay không. Dùng EOS V2 trên broker Kafka 2.5+, giữ client version theo dependency management của Spring Kafka và cấu hình consumer `read_committed` là nền tảng cho luồng consume-process-produce exactly-once trong Kafka. Các thay đổi bên ngoài Kafka vẫn cần một thiết kế nhất quán riêng.
