# Auto commit và rủi ro xử lý chưa xong

## 1. Commit offset và auto commit là gì?

Kafka lưu record trong topic theo từng partition. Consumer đọc record và theo dõi vị trí đã xử lý bằng offset. Khi consumer commit offset, nó lưu vị trí tiếp theo cần đọc cho tổ hợp consumer group, topic và partition.

Ví dụ, sau khi xử lý record có offset `40`, consumer thường commit `41`. Khi consumer khởi động lại, group có thể tiếp tục đọc từ offset đã commit nếu offset đó còn hợp lệ.

Kafka hỗ trợ hai cách quản lý commit phổ biến:

- **Auto commit:** Kafka consumer client tự động commit offset theo chu kỳ cấu hình. Client không biết listener đã hoàn tất nghiệp vụ hay chưa.
- **Commit do ứng dụng/container quản lý:** ứng dụng hoặc Spring Kafka listener container quyết định thời điểm commit dựa trên kết quả xử lý, ack mode hoặc lời gọi acknowledgment.

Auto commit có thể giảm mã quản lý offset, nhưng tạo rủi ro khi tiến độ commit không gắn với thời điểm xử lý nghiệp vụ hoàn tất.

## 2. Cách auto commit hoạt động

Khi `enable.auto.commit=true`, Kafka consumer tự động commit offset theo chu kỳ `auto.commit.interval.ms`. Offset phản ánh vị trí đọc của consumer, được tiến lên khi `poll()` trả về record; nó không phải tín hiệu xác nhận rằng listener đã hoàn tất từng record. Thời điểm commit thực tế gắn với vòng poll và cơ chế của Kafka client, không gắn với kết quả nghiệp vụ.

Một lần `poll()` có thể trả về nhiều record từ nhiều partition. Offset được theo dõi riêng cho từng partition. Ví dụ một poll trả về:

| Partition | Record nhận được | Offset tiếp theo tương ứng |
|---|---|---:|
| P0 | 40, 41, 42 | 43 |
| P1 | 18, 19 | 20 |

Nếu auto commit lưu các offset này, group có thể tiếp tục từ P0 offset 43 và P1 offset 20. Nếu ứng dụng tiếp tục poll trong khi công việc của poll trước vẫn đang chạy bất đồng bộ, offset có thể tiến qua những record chưa xử lý xong. Kafka không biết trạng thái hoàn tất của từng tác vụ nghiệp vụ.

`auto.commit.interval.ms` điều khiển khoảng thời gian giữa các lần auto commit. Thuộc tính này chỉ có ý nghĩa khi `enable.auto.commit=true`; tăng hoặc giảm interval không làm cho auto commit chờ listener hoàn tất.

~~~mermaid
flowchart TD
    A["Consumer poll()"] --> B["Nhận record từ các partition"]
    B --> C["Ứng dụng xử lý record"]
    B --> D["Vòng poll tiếp tục; auto commit theo chu kỳ"]
    C --> E{"Xử lý đã hoàn tất?"}
    E -->|Chưa| F["Có thể phát sinh lỗi hoặc dừng tiến trình"]
    D --> G["Offset đã được lưu"]
    F --> H["Khởi động lại consumer"]
    G --> H
    H --> I["Tiếp tục sau offset đã commit"]
    I --> J["Record chưa xử lý có thể bị bỏ qua"]
~~~

Điểm cốt lõi: auto commit xác nhận vị trí đọc của consumer client, không xác nhận rằng side effect nghiệp vụ đã hoàn tất.

## 3. Rủi ro mất xử lý khi commit quá sớm

Giả sử consumer nhận ba record liên tiếp trong cùng partition:

| Offset | Công việc | Trạng thái |
|---:|---|---|
| 40 | Cập nhật projection cho đơn hàng A | Hoàn tất |
| 41 | Cập nhật projection cho đơn hàng B | Đang xử lý |
| 42 | Cập nhật projection cho đơn hàng C | Chưa xử lý |

Nếu ứng dụng xử lý các record bất đồng bộ rồi tiếp tục poll, auto commit có thể lưu offset tiếp theo là `43` trong khi công việc cho record 41 và 42 vẫn chưa hoàn tất. Nếu consumer gặp sự cố sau commit, group khởi động lại từ offset 43 và hai record đó không được giao lại theo tiến độ đã commit. Với vòng poll xử lý đồng bộ, ứng dụng thường hoàn tất batch trước lần poll tiếp theo; nếu dừng trước khi commit, record có thể được đọc lại. Vì thế rủi ro bỏ sót đặc biệt rõ khi ứng dụng không chờ tác vụ xử lý của poll trước.

Đây là tình huống at-most-once đối với phần công việc chưa hoàn tất: offset đã tiến lên trước khi nghiệp vụ bền vững. Hậu quả có thể là dữ liệu projection thiếu, đơn hàng chưa được cập nhật hoặc một bước xử lý nghiệp vụ không bao giờ chạy.

Rủi ro đặc biệt đáng chú ý khi:

- Một record giữa batch ném exception.
- Ứng dụng tiếp tục poll trong khi tác vụ xử lý của poll trước vẫn chạy bất đồng bộ.
- Một poll chứa nhiều record được đưa sang executor/queue nhưng ứng dụng không chờ toàn bộ công việc hoàn tất.
- Một record giữa batch ném exception và luồng tiêu thụ tiếp tục tiến lên mà không xử lý offset lỗi theo chính sách phù hợp.
- Tiến trình bị kill hoặc máy chủ mất điện khi công việc vẫn đang chạy.
- Listener đẩy công việc sang thread nền rồi trả về ngay.
- Ứng dụng tiếp tục poll trong khi tác vụ xử lý của poll trước vẫn chạy bất đồng bộ.
- Một poll chứa nhiều record được đưa sang executor/queue nhưng ứng dụng không chờ toàn bộ công việc hoàn tất.
- Một record trong poll thất bại nhưng consumer vẫn tiếp tục tiến vị trí đọc mà không retry/seek hoặc phục hồi record đó đúng cách.
- Tiến trình bị kill hoặc máy chủ mất điện sau khi offset đã được commit nhưng trước khi công việc nền hoàn tất.
- Listener đẩy công việc sang thread nền rồi trả về ngay.

Auto commit không phân biệt record đã xử lý thành công, đang xử lý hay chưa được bắt đầu. Vì thế, không nên bật auto commit cho luồng nghiệp vụ cần bảo đảm xử lý hoàn tất trước khi xác nhận offset.

## 4. Rủi ro xử lý trùng khi commit quá muộn

Auto commit cũng có thể tạo ra tình huống ngược lại. Ứng dụng đã xử lý thành công record và ghi dữ liệu xuống database, nhưng consumer dừng trước khi offset mới được commit.

Ví dụ:

1. Consumer nhận record offset 40.
2. Ứng dụng cập nhật database thành công.
3. Tiến trình dừng trước lần auto commit tiếp theo.
4. Consumer khởi động lại từ offset cũ.
5. Record offset 40 được nhận và xử lý lại.

Khi đó side effect có thể xảy ra hai lần. Đây là rủi ro at-least-once: record được giao lại để tránh mất dữ liệu, nhưng ứng dụng phải chịu được duplicate.

| Thời điểm dừng | Trạng thái offset | Hệ quả có thể xảy ra |
|---|---|---|
| Sau khi commit, trước khi xử lý xong | Offset đã tiến lên | Bỏ qua phần xử lý chưa hoàn tất |
| Sau khi xử lý xong, trước khi commit | Offset chưa tiến lên | Record được nhận lại, có thể xử lý trùng |
| Sau khi xử lý và commit thành công | Offset đã tiến lên | Group tiếp tục từ record kế tiếp |

Do đó, auto commit không bảo đảm exactly-once. Tùy thời điểm sự cố, ứng dụng có thể mất phần xử lý chưa xong hoặc thực hiện lại side effect đã hoàn tất.

## 5. Auto commit trong Kafka client thuần và Spring Kafka

Cần phân biệt mặc định của Kafka consumer client với cách Spring Kafka listener container quản lý offset.

Với `KafkaConsumer` được tạo trực tiếp, thuộc tính `enable.auto.commit` của Kafka client mặc định là `true`. Khi dùng Spring Kafka listener container, từ Spring Kafka 2.3 trở lên, container tự đặt auto commit thành `false` nếu ứng dụng không khai báo rõ thuộc tính này. Container dùng cơ chế commit riêng dựa trên `AckMode`.

Nếu ứng dụng chủ động cấu hình `enable.auto.commit=true`, Kafka client vẫn commit theo cơ chế và nhịp poll riêng của nó; việc commit không dựa trên kết quả xử lý của listener. Đặc biệt, nếu listener đưa công việc sang executor rồi trả về hoặc ứng dụng tiếp tục poll khi tác vụ trước chưa xong, vị trí consumer có thể tiến lên trước tiến độ nghiệp vụ. Điều này xung đột với mục tiêu để container xác nhận offset theo kết quả listener.

Ví dụ cấu hình có rủi ro:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-processor
      enable-auto-commit: true
      properties:
        auto.commit.interval.ms: 1000
~~~

Với cấu hình trên, client được phép auto commit theo chu kỳ một giây. Khoảng thời gian ngắn không làm tăng độ an toàn. Rủi ro bỏ sót xuất hiện rõ khi ứng dụng tiếp tục poll hoặc tiến vị trí đọc trong lúc công việc của record trước vẫn chưa hoàn tất; một listener đồng bộ chặn consumer thread cho đến khi xử lý xong có hành vi khác với listener đưa tác vụ sang nền rồi trả về.

Với listener container, hãy để container quản lý commit:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-processor
      enable-auto-commit: false
      auto-offset-reset: earliest
    listener:
      type: single
      ack-mode: record
~~~

Trong cấu hình này:

- `enable-auto-commit: false` tắt auto commit của Kafka client.
- `ack-mode: record` yêu cầu container commit sau khi từng record listener xử lý thành công.
- `auto-offset-reset: earliest` chỉ quyết định vị trí bắt đầu khi group chưa có offset hợp lệ; không ghi đè offset đã commit.

Nếu muốn xử lý và xác nhận theo cả poll, có thể dùng `ack-mode: batch`. Đây là chế độ mặc định phổ biến của Spring Kafka listener container. Chọn `record` khi cần commit sát từng record; chọn `batch` khi chấp nhận xác nhận sau khi toàn bộ record của lần poll được xử lý thành công.

## 6. Cấu hình commit an toàn bằng AckMode

Khi `enable.auto.commit=false`, Spring Kafka listener container quản lý thời điểm commit. Các chế độ thường gặp:

| AckMode | Khi nào container xác nhận offset? | Lưu ý |
|---|---|---|
| `RECORD` | Sau mỗi record listener xử lý thành công | Dành cho record listener |
| `BATCH` | Sau khi xử lý thành công các record của một lần poll | Phù hợp xử lý theo poll; là mặc định phổ biến |
| `TIME` | Khi đạt khoảng thời gian cấu hình và có offset cần commit | Gom commit theo thời gian |
| `COUNT` | Khi đạt số record cấu hình | Gom commit theo số lượng |
| `COUNT_TIME` | Khi đạt ngưỡng số record hoặc thời gian | Kết hợp hai điều kiện |
| `MANUAL` | Sau khi listener gọi `acknowledge()`; container thực hiện commit theo chu kỳ | Ứng dụng chủ động xác nhận |
| `MANUAL_IMMEDIATE` | Commit ngay khi `acknowledge()` được gọi trên consumer thread | Cần kiểm soát thread gọi acknowledgment |

Với `RECORD`, listener phải hoàn tất công việc đồng bộ rồi trả về. Nếu listener ném exception, error handler xử lý retry hoặc recovery; container không xem lần gọi đó là thành công.

Ví dụ listener:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderProjectionListener {

    private final OrderProjectionService orderProjectionService;

    public OrderProjectionListener(
            OrderProjectionService orderProjectionService) {
        this.orderProjectionService = orderProjectionService;
    }

    @KafkaListener(
        topics = "orders",
        groupId = "order-processor"
    )
    public void handle(OrderCreatedEvent event) {
        // Chỉ trả về sau khi thao tác nghiệp vụ hoàn tất.
        orderProjectionService.apply(event);
    }
}
~~~

Nếu nghiệp vụ cần tự quyết định thời điểm xác nhận, có thể dùng manual acknowledgment:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
public class ManualOrderListener {

    @KafkaListener(
        topics = "orders",
        groupId = "manual-order-processor"
    )
    public void handle(
            OrderCreatedEvent event,
            Acknowledgment acknowledgment) {

        orderService.apply(event);
        acknowledgment.acknowledge();
    }
}
~~~

Listener manual cần dùng container factory có ack mode `MANUAL` hoặc `MANUAL_IMMEDIATE`, đồng thời giữ `enable.auto.commit=false`. Chỉ gọi `acknowledge()` sau khi công việc cần bảo đảm đã hoàn tất.

## 7. Listener bất đồng bộ có thể commit quá sớm

Một lỗi thường gặp là listener chỉ đưa sự kiện vào executor hoặc queue rồi trả về:

~~~java
@KafkaListener(topics = "orders", groupId = "order-processor")
public void handle(OrderCreatedEvent event) {
    executor.submit(() -> orderService.apply(event));
    // Listener đã trả về dù công việc nền chưa hoàn tất.
}
~~~

Với container-managed acknowledgment, phương thức listener trả về bình thường có thể khiến container xác nhận offset theo ack mode. Công việc nền có thể thất bại sau đó, trong khi record đã được commit.

Nếu cần xử lý bất đồng bộ, phải thiết kế vòng đời acknowledgment rõ ràng. Một lựa chọn là dùng manual acknowledgment và chỉ ack sau khi tác vụ hoàn tất; nhưng cần tuân thủ yêu cầu thread của `MANUAL_IMMEDIATE`, cấu hình `asyncAcks` nếu dùng acknowledgment ngoài thứ tự, và xử lý trường hợp consumer bị dừng trong lúc tác vụ nền vẫn chạy. Không giữ consumer thread hoặc commit offset tùy tiện từ callback.

Trong nhiều ứng dụng, cách đơn giản và dễ kiểm soát hơn là hoàn tất xử lý nghiệp vụ trong listener trước khi trả về. Nếu cần tăng throughput, hãy scale concurrency/partition hoặc chuyển sang một mô hình worker bền vững có lưu trạng thái.

## 8. Commit offset không phải transaction database

`AckMode` chỉ điều khiển tiến độ Kafka. Nó không tự tạo giao dịch nguyên tử giữa commit offset và cập nhật database.

Hai tình huống cần xử lý:

- Database commit thành công nhưng consumer dừng trước khi commit offset: record có thể được giao lại.
- Offset được commit trước khi database hoàn tất: record có thể bị bỏ qua dù thay đổi nghiệp vụ chưa được lưu.

Với consumer cần ghi database, nên thiết kế idempotent. Một cách phổ biến là đưa `eventId` duy nhất vào payload và lưu ID đã xử lý cùng thay đổi nghiệp vụ trong cùng database transaction. Nếu event ID đã tồn tại, consumer bỏ qua tác động lặp.

~~~java
@Transactional
public void applyOnce(OrderCreatedEvent event) {
    if (processedEventRepository.existsById(event.eventId())) {
        return;
    }

    orderProjectionRepository.apply(event);
    processedEventRepository.save(
        new ProcessedEvent(event.eventId())
    );
}
~~~

Trong thực tế, cần bảo vệ tính duy nhất bằng unique constraint ở database thay vì chỉ dựa vào thao tác `exists` vì nhiều consumer hoặc retry có thể chạy đồng thời.

Nếu cần bảo đảm thay đổi database và việc phát sự kiện Kafka được ghi nhận cùng nhau, hãy tìm hiểu Transactional Outbox. Nếu consumer cần phối hợp xử lý Kafka và database, có thể dùng Inbox hoặc transaction phù hợp. Không coi auto commit là cơ chế transaction cho dữ liệu nghiệp vụ.

## 9. Kiểm thử và quan sát rủi ro auto commit

Nên kiểm thử các cửa sổ lỗi thay vì chỉ xác minh listener được gọi:

| Kịch bản | Điều cần quan sát |
|---|---|
| Consumer tiếp tục poll trong khi tác vụ của poll trước chưa hoàn tất | Offset có thể tiến lên trước khi nghiệp vụ hoàn tất |
| Listener ném exception giữa các record của poll | Xác minh record lỗi có bị bỏ qua do offset đã commit hay không |
| Tiến trình dừng sau khi ghi database nhưng trước commit | Record có được giao lại và nghiệp vụ có xử lý duplicate an toàn không |
| Manual acknowledgment chỉ gọi sau khi xử lý xong | Offset không tiến lên trước khi acknowledgment được gọi |
| Error handler retry rồi thành công | Offset được xác nhận sau khi xử lý/recovery theo cấu hình |

Có thể dùng Embedded Kafka hoặc Testcontainers, gửi record có `eventId` riêng và cố ý làm listener chậm hoặc ném exception. Dừng rồi khởi động lại consumer, sau đó kiểm tra:

- Committed offset của từng partition.
- Record nào được giao lại.
- Số lần side effect được thực hiện.
- Consumer lag và log của error handler.

Dùng Kafka CLI để kiểm tra tiến độ group:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group order-processor
~~~

Trong production, theo dõi consumer lag, thời gian xử lý listener, commit latency, số lần retry và lỗi listener. Nếu auto commit được bật ngoài dự kiến, cần phát hiện qua cấu hình thực tế và log khởi tạo consumer.

## 10. Checklist tránh xử lý chưa xong nhưng đã commit

- [ ] Hiểu khác biệt giữa Kafka client thuần và Spring Kafka listener container.
- [ ] Với listener container, giữ `enable.auto.commit=false`.
- [ ] Chọn `AckMode.RECORD`, `BATCH` hoặc manual acknowledgment theo cách xử lý.
- [ ] Chỉ xác nhận offset sau khi nghiệp vụ cần bảo đảm đã hoàn tất.
- [ ] Không submit tác vụ nền rồi trả về mà không quản lý acknowledgment.
- [ ] Phân biệt mất xử lý do commit sớm và duplicate do xử lý xong nhưng chưa commit.
- [ ] Thiết kế idempotent bằng event ID và unique constraint khi ghi database.
- [ ] Không nhầm commit offset với database transaction hoặc exactly-once.
- [ ] Kiểm thử listener chậm, exception, restart và recovery.
- [ ] Theo dõi committed offset, consumer lag và thời gian xử lý.

Auto commit tiện cho consumer đơn giản nhưng không biết công việc nghiệp vụ đã hoàn tất hay chưa. Với ứng dụng Spring Kafka sử dụng `@KafkaListener`, nên tắt auto commit và để listener container quản lý offset theo `AckMode`. Khi kết hợp xử lý đồng bộ hoặc acknowledgment có kiểm soát, error handler và nghiệp vụ idempotent, ứng dụng sẽ giảm rủi ro bỏ qua công việc chưa xong và xử lý trùng khi consumer khởi động lại.
