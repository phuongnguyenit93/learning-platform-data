# Tạo thông điệp định kỳ bằng Supplier

Không phải message nào cũng xuất hiện sau một request từ người dùng hoặc sau khi một dịch vụ khác gửi sự kiện. Nhiều hệ thống cần tự phát thông điệp theo chu kỳ: heartbeat để báo tiến trình còn hoạt động, snapshot tồn kho mỗi vài phút, số liệu tổng hợp theo khoảng thời gian hoặc trạng thái thiết bị được lấy từ nguồn dữ liệu định kỳ. Trong Spring Cloud Stream, một hàm `Supplier<T>` có thể tạo payload và để framework gọi hàm theo lịch polling, sau đó gửi kết quả qua binding đầu ra.

`Supplier` là điểm bắt đầu của một luồng message do chính ứng dụng tạo ra. Nó không có binding đầu vào; mỗi lần được gọi, hàm cung cấp một giá trị cho binding đầu ra. Poller quyết định nhịp gọi. Binder kết nối binding với broker như Kafka, RabbitMQ hoặc Pulsar. Để dùng mô hình này đúng cách, cần phân biệt thời điểm tạo message, nhịp polling và thời điểm broker xác nhận việc gửi.

Bài thuộc chương **Nguồn phát** của module `SPRING_CLOUD_STREAM`, nơi ứng dụng sử dụng mô hình hàm `Supplier`/`Function`/`Consumer`, binding và binder để xử lý sự kiện. Nội dung tập trung vào việc tạo message định kỳ bằng một supplier đồng bộ, cấu hình poller, tạo payload có định danh và vận hành an toàn khi ứng dụng có nhiều instance.

## 1. Supplier làm gì trong luồng message?

Trong Java, `Supplier<T>` là một functional interface có phương thức `get()` trả về một giá trị kiểu `T` và không nhận tham số đầu vào. Spring Cloud Stream có thể dùng bean supplier làm nguồn phát message. Với supplier đồng bộ, framework gọi `get()` theo cơ chế polling; giá trị trả về được chuyển thành message và gửi tới binding đầu ra.

```text
Poller của Spring
      |
      | gọi theo chu kỳ
      v
Supplier<T>.get()
      |
      | trả về payload T
      v
Message conversion / output binding
      |
      v
Binder
      |
      v
Kafka / RabbitMQ / Pulsar
```

Ví dụ, dịch vụ giám sát muốn phát một heartbeat mỗi 5 giây. Supplier tạo đối tượng `Heartbeat` chứa mã dịch vụ, thời điểm tạo và số thứ tự cục bộ. Spring Cloud Stream serialize payload theo content type của binding rồi chuyển cho binder gửi tới destination đã cấu hình.

Supplier phù hợp khi ứng dụng chủ động tạo dữ liệu theo nhịp đều đặn. Nếu message chỉ phát sinh khi một nghiệp vụ xảy ra, chẳng hạn đơn hàng vừa được tạo, hãy phát message từ luồng xử lý nghiệp vụ hoặc dùng một cơ chế phát sự kiện theo sự kiện thực tế thay vì polling vô ích.

## 2. Khai báo Supplier bằng bean

Một supplier thường được khai báo bằng `@Bean` trong lớp cấu hình Spring. Ví dụ:

```java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record Heartbeat(
    String service,
    long sequence,
    Instant generatedAt
) {}

@Configuration
class HeartbeatProducer {

    @Bean
    Supplier<Heartbeat> heartbeatSupplier() {
        AtomicLong sequence = new AtomicLong();

        return () -> new Heartbeat(
            "order-service",
            sequence.incrementAndGet(),
            Instant.now()
        );
    }
}
```

Spring Cloud Stream nhận diện bean `heartbeatSupplier` là nguồn phát. Binding đầu ra mặc định được đặt tên theo quy ước:

```text
heartbeatSupplier-out-0
```

Hậu tố `out-0` biểu thị đầu ra thứ nhất của hàm. Supplier không có binding `in-0` vì không nhận message từ broker. Mỗi lần poller gọi `get()`, ví dụ trên tạo một heartbeat mới với thời gian hiện tại và tăng sequence trong bộ nhớ của instance.

`AtomicLong` bảo vệ thao tác tăng số trong trường hợp bean được gọi từ nhiều thread. Tuy nhiên, sequence này chỉ có ý nghĩa trong vòng đời của một instance: nó trở về giá trị ban đầu khi ứng dụng khởi động lại và mỗi replica có bộ đếm riêng. Không dùng bộ đếm trong bộ nhớ làm định danh duy nhất toàn hệ thống. Nếu cần định danh sự kiện ổn định, hãy dùng UUID hoặc ID được cấp từ một nguồn bền vững phù hợp.

## 3. Cấu hình binding đầu ra

Supplier cần một binding đầu ra được nối với destination. Ví dụ cấu hình phát heartbeat dưới dạng JSON:

```yaml
spring:
  cloud:
    function:
      definition: heartbeatSupplier
    stream:
      bindings:
        heartbeatSupplier-out-0:
          destination: system.heartbeat
          content-type: application/json
```

Các thành phần trong cấu hình:

- `spring.cloud.function.definition` chọn bean hàm sẽ được kích hoạt.
- `heartbeatSupplier-out-0` là binding đầu ra mặc định của supplier.
- `destination` là tên đích logic mà binder ánh xạ sang tài nguyên broker.
- `content-type: application/json` cho biết payload được serialize thành JSON.

Với Kafka, destination thường là topic. Với RabbitMQ, output binding thường publish đến exchange và routing topology quyết định queue nào nhận message. Với Pulsar, destination là topic. Logic tạo payload trong supplier có thể giữ nguyên khi thay binder, nhưng tài nguyên vật lý, quyền truy cập và cấu hình kết nối vẫn cần phù hợp với broker.

Không cần tạo một `MessageChannel` thủ công cho trường hợp function thông thường. Spring Cloud Stream suy ra binding từ tên bean và vai trò hàm. Hãy kiểm tra tên binding thực tế khi đổi tên bean vì cấu hình cũ có thể không còn khớp.

## 4. Điều khiển nhịp phát bằng poller

Supplier đồng bộ được gọi bởi poller. Có thể cấu hình khoảng chờ và độ trễ ban đầu ở nhánh `spring.cloud.stream.poller`:

```yaml
spring:
  cloud:
    function:
      definition: heartbeatSupplier
    stream:
      poller:
        initial-delay: 1000
        fixed-delay: 5000
      bindings:
        heartbeatSupplier-out-0:
          destination: system.heartbeat
          content-type: application/json
```

Trong ví dụ:

- `initial-delay: 1000` trì hoãn lần poll đầu tiên khoảng 1.000 mili giây sau khi poller được khởi chạy.
- `fixed-delay: 5000` đặt khoảng nghỉ 5.000 mili giây giữa các lần thực thi poll theo cấu hình.

Đơn vị của các thuộc tính poller này là mili giây. Giá trị mặc định nếu không cấu hình phụ thuộc phiên bản và cấu hình Spring Integration/Spring Cloud Stream; hãy khai báo tường minh khi nhịp phát là một yêu cầu nghiệp vụ hoặc vận hành.

`fixed-delay` không có nghĩa là đồng hồ phát chính xác vào các mốc 00, 05, 10, 15 giây. Với fixed delay, khoảng chờ được tính giữa các lần thực thi; thời gian chạy của lần poll trước cũng ảnh hưởng thời điểm message tiếp theo được tạo. Nếu cần lịch theo giờ lịch, ví dụ đúng 09:00 mỗi ngày theo múi giờ cụ thể, hãy dùng cơ chế lập lịch chuyên dụng như Spring Scheduling hoặc Quartz rồi chủ động phát message qua output binding phù hợp.

### Chọn khoảng polling

| Nhu cầu | Khoảng polling tham khảo | Lưu ý |
|---|---:|---|
| Heartbeat giám sát | Vài giây đến vài chục giây | Cân bằng độ nhạy phát hiện sự cố với lượng message |
| Snapshot số liệu | Vài phút | Tính chi phí truy vấn và độ trễ dữ liệu |
| Tổng hợp trạng thái định kỳ | Vài phút hoặc lâu hơn | Chỉ phát khi có thay đổi nếu nghiệp vụ cho phép |
| Đọc nguồn dữ liệu bên ngoài | Theo giới hạn API hoặc hệ thống nguồn | Tránh polling nhanh hơn năng lực nguồn |

Không có một chu kỳ phù hợp cho mọi ứng dụng. Polling quá dày làm tăng tải lên producer, broker và consumer. Polling quá thưa khiến dữ liệu đến chậm hoặc giám sát phát hiện sự cố muộn.

## 5. Supplier tạo payload mới ở mỗi lần gọi

Supplier nên trả về một payload đại diện cho một lần phát. Ví dụ snapshot tồn kho:

```java
import java.time.Instant;
import java.util.List;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;

record StockItem(String sku, int available) {}

record StockSnapshot(
    Instant capturedAt,
    List<StockItem> items
) {}

@Bean
Supplier<StockSnapshot> stockSnapshotSupplier(InventoryReader inventory) {
    return () -> new StockSnapshot(
        Instant.now(),
        inventory.readCurrentStock()
    );
}
```

Mỗi lần supplier được gọi, ứng dụng đọc dữ liệu hiện tại và tạo snapshot mới. Trong triển khai thực tế, `InventoryReader` là một bean nghiệp vụ do ứng dụng cung cấp. Cần xem xét thời gian truy vấn, kích thước payload, transaction đọc và khả năng nguồn dữ liệu thay đổi trong lúc lấy snapshot.

Nếu thao tác đọc nguồn mất nhiều thời gian hơn khoảng polling, các lần thực thi có thể bị trễ tùy scheduler và cấu hình. Không nên tự tạo thread mới trong mỗi lần gọi supplier. Hãy dùng cơ chế thực thi có giới hạn, timeout và backpressure phù hợp nếu nguồn dữ liệu có độ trễ không ổn định.

## 6. Không có dữ liệu mới thì xử lý thế nào?

Supplier có thể trả về `null` để biểu thị rằng lần poll hiện tại không tạo message. Ví dụ chỉ phát snapshot khi có thay đổi:

```java
@Bean
Supplier<StockSnapshot> changedStockSupplier(InventoryReader inventory) {
    return () -> inventory.readChangedStockSnapshot()
        .orElse(null);
}
```

Ở đây `readChangedStockSnapshot()` trả về `Optional<StockSnapshot>`. Nếu không có dữ liệu mới, supplier trả về `null` và lần poll đó không phát payload. Cần xác nhận hành vi này với kiểu supplier và phiên bản framework đang dùng; không trả về một đối tượng rỗng nếu consumer có thể hiểu nhầm đó là snapshot hợp lệ.

Nếu cần phát một thông điệp trạng thái “không có thay đổi”, hãy biểu diễn rõ điều đó trong schema, chẳng hạn `changeCount: 0` và `capturedAt`, thay vì dùng `null`. Nếu không muốn phát message khi nguồn không thay đổi, `null` phù hợp hơn.

## 7. Gửi Message có headers

Supplier có thể trả về `Message<T>` khi cần tự đặt headers như event type, correlation ID hoặc event ID:

```java
import java.time.Instant;
import java.util.UUID;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record Heartbeat(String service, Instant generatedAt) {}

@Bean
Supplier<Message<Heartbeat>> heartbeatMessageSupplier() {
    return () -> MessageBuilder
        .withPayload(new Heartbeat("order-service", Instant.now()))
        .setHeader("eventId", UUID.randomUUID().toString())
        .setHeader("eventType", "ServiceHeartbeat")
        .build();
}
```

Payload chứa dữ liệu nghiệp vụ; headers mang metadata phục vụ định tuyến, truy vết hoặc xử lý. Không nên đưa mọi metadata vào JSON payload nếu consumer chỉ cần chúng như thuộc tính vận chuyển. Cũng cần kiểm tra header nào được binder hỗ trợ và header nào được ánh xạ qua broker, vì không phải mọi broker đều giữ mọi header theo cùng một cách.

Nếu dùng `Message<T>`, vẫn cần cấu hình content type cho binding output. Định dạng payload và metadata message là hai khái niệm riêng. Không đưa dữ liệu bí mật vào header vì header cũng có thể được ghi log hoặc chuyển qua các hệ thống trung gian.

## 8. Supplier nhiều instance và nguy cơ phát trùng

Khi triển khai ứng dụng thành nhiều replica, mỗi instance thường có bean supplier và poller riêng. Nếu có 3 replica, cả 3 có thể gọi supplier theo lịch và phát heartbeat hoặc snapshot. Điều này có thể là chủ đích nếu muốn mỗi instance tự báo tình trạng của nó; nhưng có thể là lỗi nếu chỉ muốn một snapshot toàn hệ thống mỗi chu kỳ.

```text
Replica A -- Supplier + poller --+
Replica B -- Supplier + poller --+--> destination: system.heartbeat
Replica C -- Supplier + poller --+
```

Hãy xác định đơn vị phát:

- **Theo instance:** mỗi replica phát heartbeat riêng, payload có `instanceId` để phân biệt.
- **Theo ứng dụng:** chỉ một instance đại diện phát snapshot chung.
- **Theo phân vùng dữ liệu:** mỗi instance phát dữ liệu của một vùng hoặc một tập key riêng.

Nếu chỉ một instance được phép phát, có thể dùng leader election, distributed lock hoặc một scheduler chuyên trách chạy một replica. Cần xử lý tình huống leader thay đổi và lease hết hạn để tránh hai instance cùng phát trong khoảng chuyển giao.

Consumer cũng nên idempotent nếu một message có thể được gửi lại. `eventId` duy nhất giúp nhận diện bản phát; với snapshot theo chu kỳ, có thể dùng cặp `sourceId` và `capturedAt` hoặc một `snapshotId` ổn định theo kỳ. Không dùng timestamp đơn lẻ làm khóa duy nhất nếu độ chính xác thời gian hoặc đồng hồ giữa các máy không được bảo đảm.

## 9. Thời gian, định danh và khả năng phát lại

Một message định kỳ nên chứa đủ thông tin để consumer hiểu nó đại diện cho thời điểm nào:

```json
{
  "eventId": "e7a2d1f2-5b93-4c51-9a2a-9c15b4c1c1e2",
  "eventType": "StockSnapshotCreated",
  "source": "warehouse-service",
  "capturedAt": "2026-11-24T08:30:00Z",
  "schemaVersion": 1,
  "items": [
    { "sku": "COFFEE-01", "available": 42 },
    { "sku": "TEA-03", "available": 18 }
  ]
}
```

Nên phân biệt:

- `capturedAt`: thời điểm dữ liệu được đọc hoặc snapshot được tạo.
- Thời điểm publish: thời điểm producer gửi message đến broker; có thể khác thời điểm capture.
- Thời điểm xử lý: thời điểm consumer nhận và xử lý message; có thể muộn hơn do backlog.

Nếu consumer dùng snapshot để cập nhật trạng thái hiện tại, nó cần tránh áp dụng snapshot cũ sau snapshot mới hơn. Có thể so sánh `capturedAt`, sequence theo nguồn hoặc version snapshot. Nếu dữ liệu được chia theo nhiều partition hoặc nhiều instance, cần định nghĩa thứ tự trong phạm vi từng nguồn hoặc từng aggregate.

Polling không tự tạo lịch sử bền vững. Khi ứng dụng dừng, các lần poll dự kiến trong khoảng dừng không tự động được phát bù khi ứng dụng chạy lại. Nếu yêu cầu nghiệp vụ cần ghi nhận mọi kỳ đã đến hạn, hãy lưu lịch thực thi hoặc kỳ cần phát trong database và thiết kế quy trình catch-up rõ ràng.

## 10. Lỗi khi supplier tạo hoặc gửi message

Có thể xảy ra lỗi ở nhiều giai đoạn:

| Giai đoạn | Ví dụ | Cách xử lý |
|---|---|---|
| Lấy dữ liệu | Database timeout, API nguồn không phản hồi | Timeout, giới hạn retry, circuit breaker và metric lỗi nguồn |
| Tạo payload | Dữ liệu thiếu hoặc vi phạm schema | Validate trước khi trả về message; ghi log theo event ID nếu có |
| Serialize | Kiểu dữ liệu không được converter hỗ trợ | Kiểm tra content type, kiểu Java và converter |
| Publish | Broker mất kết nối hoặc từ chối publish | Dựa vào binder/client retry và chính sách lỗi producer; không giả định message đã được ghi |
| Consumer xử lý | Payload hợp lệ về JSON nhưng sai nghiệp vụ | Consumer validation, retry có giới hạn và DLQ phù hợp |

Không nên bắt mọi exception trong supplier rồi trả về `null` một cách im lặng. Làm như vậy có thể biến lỗi nguồn dữ liệu thành một lần poll “không có message”, khiến hệ thống mất dấu sự cố. Hãy phân biệt không có dữ liệu mới với không thể lấy dữ liệu.

Với lỗi tạm thời, có thể dùng retry có backoff tại tầng gọi nguồn dữ liệu. Tuy nhiên, thời gian retry cần tính vào chu kỳ polling và timeout triển khai. Nếu supplier bị block quá lâu, poller có thể không chạy đúng nhịp dự kiến. Với lỗi vĩnh viễn như cấu hình sai hoặc schema không hợp lệ, cần log rõ và phát cảnh báo.

## 11. Không nhầm polling với lịch nghiệp vụ chính xác

Polling là cách framework hỏi supplier theo một khoảng thời gian. Nó phù hợp với tác vụ “kiểm tra xem đã có dữ liệu cần phát chưa” hoặc “tạo heartbeat theo nhịp gần đúng”. Polling không phải bộ lập lịch bền vững đảm bảo một lần phát đúng một thời điểm trên đồng hồ.

| Yêu cầu | Cách tiếp cận |
|---|---|
| Phát heartbeat mỗi vài giây | Supplier đồng bộ với poller fixed delay |
| Đọc dữ liệu mới từ bảng theo chu kỳ | Supplier gọi service/repository với truy vấn có giới hạn |
| Phát báo cáo lúc 08:00 mỗi ngày | Scheduler theo cron hoặc Quartz với múi giờ và chính sách catch-up rõ ràng |
| Đảm bảo một lần phát cho mỗi kỳ nghiệp vụ | Lưu kỳ phát và trạng thái trong database, dùng khóa duy nhất/outbox |
| Phát ngay khi một nghiệp vụ hoàn tất | Phát sự kiện từ luồng nghiệp vụ hoặc output của Function |

Nếu lịch phát có ý nghĩa tài chính hoặc pháp lý, không nên dựa riêng vào poller trong bộ nhớ. Hãy lưu lịch, lần thực thi và kết quả phát để có thể đối soát sau restart.

## 12. Kiểm thử Supplier định kỳ

Nên kiểm thử supplier ở cả mức hàm và mức tích hợp:

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Supplier tạo payload | Gọi `get()` trực tiếp trong unit test | Payload có đúng trường, thời gian và định danh |
| Poller chạy theo cấu hình | Khởi động context với poller và output test binding | Số lần gọi phù hợp với khoảng thời gian kiểm thử |
| Không có dữ liệu mới | Supplier trả về `null` | Không phát message rỗng ngoài ý muốn |
| Nguồn dữ liệu lỗi | Cho repository ném exception | Lỗi được ghi nhận và quan sát, không bị hiểu thành không có dữ liệu |
| Broker không khả dụng | Dừng broker hoặc chặn kết nối | Publish failure được phát hiện theo cơ chế binder/client |
| Nhiều replica | Chạy nhiều instance thử nghiệm | Xác nhận số lượng producer theo thiết kế, không phát trùng ngoài ý muốn |
| Restart | Dừng rồi khởi động lại ứng dụng | Hiểu rõ sequence, lịch polling và kỳ dữ liệu có bị reset hoặc bỏ lỡ không |

Ví dụ unit test cho supplier:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;

class HeartbeatProducerTest {

    @Test
    void createsHeartbeatWithIncreasingSequence() {
        var supplier = new HeartbeatProducer().heartbeatSupplier();

        Heartbeat first = supplier.get();
        Heartbeat second = supplier.get();

        assertEquals(1, first.sequence());
        assertEquals(2, second.sequence());
        assertNotNull(first.generatedAt());
    }
}
```

Unit test trên kiểm tra logic tạo payload; nó không xác nhận poller thực sự chạy theo lịch hay binder gửi message đến broker. Integration test cần kiểm tra binding `heartbeatSupplier-out-0`, destination và content type bằng test binder hoặc broker phù hợp.

## 13. Quan sát và vận hành

Một supplier định kỳ nên có metric và log đủ để trả lời các câu hỏi:

- Lần poll gần nhất bắt đầu và hoàn tất lúc nào?
- Bao nhiêu lần poll tạo message, bao nhiêu lần không có dữ liệu mới?
- Thời gian lấy dữ liệu trung bình và lớn nhất là bao nhiêu?
- Có bao nhiêu lần lỗi đọc nguồn, serialize hoặc publish?
- Message được tạo có tuổi bao lâu khi consumer xử lý?
- Mỗi instance phát bao nhiêu message trong một khoảng thời gian?
- Có kỳ phát nào bị bỏ lỡ sau khi ứng dụng restart không?

Log nên có `eventId`, `source`, `capturedAt` và `instanceId` khi có thể. Tránh ghi toàn bộ payload nếu nó chứa dữ liệu nhạy cảm. Metric nên dùng nhãn có cardinality giới hạn; không đưa UUID hoặc order ID làm label metric.

Với heartbeat, consumer giám sát nên đánh giá thời gian từ heartbeat gần nhất theo `instanceId`. Không nên chỉ dựa vào số lượng message trung bình của toàn destination vì một instance có thể ngừng phát trong khi các instance khác vẫn hoạt động.

## 14. Quy trình triển khai đề xuất

Khi xây dựng một nguồn phát định kỳ bằng Supplier:

1. Xác định dữ liệu cần phát và lý do cần phát theo chu kỳ.
2. Chọn kiểu payload và schema; thêm event ID, source ID và thời gian tạo phù hợp.
3. Khai báo bean `Supplier<T>` có logic tạo một message cho mỗi lần gọi.
4. Chọn binding đầu ra theo tên `<functionName>-out-0` và cấu hình destination/content type.
5. Đặt `initial-delay` và `fixed-delay` theo độ trễ cho phép, chi phí truy vấn và năng lực broker.
6. Xác định ứng dụng chạy một replica hay nhiều replica; chọn phát theo instance, theo ứng dụng hoặc theo phân vùng.
7. Thiết kế idempotency, sequence/version và chính sách catch-up nếu có yêu cầu không bỏ lỡ kỳ phát.
8. Xử lý riêng trường hợp không có dữ liệu và trường hợp lỗi nguồn dữ liệu.
9. Kiểm thử poller, binder, broker, restart và triển khai nhiều instance.
10. Theo dõi tần suất poll, thời gian tạo payload, publish failure và độ trễ phía consumer.

## 15. Tự kiểm tra

- [ ] Giải thích được vì sao `Supplier<T>` phù hợp để tạo message mà ứng dụng chủ động phát.
- [ ] Xác định được binding đầu ra mặc định `<functionName>-out-0`.
- [ ] Cấu hình được `initial-delay` và `fixed-delay` cho poller.
- [ ] Phân biệt polling theo fixed delay với lịch theo giờ lịch hoặc cron.
- [ ] Biết cách trả về payload mới, `Message<T>` có headers hoặc `null` khi không có dữ liệu.
- [ ] Nhận diện được rủi ro nhiều replica cùng phát message.
- [ ] Thiết kế được event ID, source ID và thời gian để xử lý trùng lặp hoặc dữ liệu cũ.
- [ ] Phân biệt lỗi lấy dữ liệu, lỗi serialize và lỗi publish.
- [ ] Biết kiểm thử supplier riêng với kiểm thử poller/binding tích hợp.

## Kết luận

`Supplier<T>` cho phép ứng dụng chủ động tạo message mà không cần binding đầu vào. Với supplier đồng bộ, poller gọi hàm theo chu kỳ; kết quả được serialize theo content type và gửi qua binding đầu ra `<functionName>-out-0`. Cấu hình `initial-delay` và `fixed-delay` giúp điều khiển thời điểm bắt đầu và nhịp polling. Khi triển khai, cần tính đến thời gian lấy dữ liệu, lỗi publish, nhiều replica, định danh sự kiện và việc ứng dụng dừng hoặc khởi động lại. Nếu yêu cầu là lịch nghiệp vụ chính xác hoặc không được bỏ lỡ bất kỳ kỳ nào, hãy bổ sung scheduler bền vững và lưu trạng thái thực thi thay vì chỉ dựa vào poller trong bộ nhớ.
