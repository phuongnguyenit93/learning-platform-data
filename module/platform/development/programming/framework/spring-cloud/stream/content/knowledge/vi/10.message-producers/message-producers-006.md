# Điều khiển tách phần tử bằng thuộc tính splittable

Trong Spring Cloud Stream, một nguồn phát có thể trả về một luồng hữu hạn gồm nhiều phần tử. Ví dụ, một lần truy vấn kho dữ liệu có thể trả về danh sách các sự kiện đơn hàng đang chờ gửi. Khi dùng reactive supplier `Supplier<Flux<T>>`, framework cần biết mỗi phần tử trong luồng sẽ trở thành một message riêng hay toàn bộ luồng được chuyển tiếp như một đơn vị. Thuộc tính `splittable` của `@PollableBean` điều khiển quyết định này.

Mặc định, `splittable` là `true`: Spring Cloud Stream tách luồng và gửi từng phần tử thành một message riêng. Đặt `splittable = false` sẽ yêu cầu framework giữ nguyên `Flux` được trả về, không thực hiện bước tách phần tử. Thuộc tính này hữu ích khi xây dựng nguồn phát reactive có dữ liệu hữu hạn được lấy theo từng đợt, nhưng cần hiểu đúng phạm vi của nó để tránh nhầm với partitioning, batching hoặc việc tạo một payload dạng danh sách.

## 1. Bối cảnh: Supplier reactive có dữ liệu hữu hạn

Một `Supplier<T>` thông thường được framework gọi theo cơ chế poller. Mỗi lần gọi, supplier trả về một giá trị và giá trị đó được phát ra binding đầu ra.

```java
@Bean
Supplier<OrderEvent> orderEvent() {
    return () -> new OrderEvent("order-1001");
}
```

Reactive supplier có kiểu `Supplier<Flux<T>>` và trả về một publisher. Với supplier đại diện cho luồng liên tục, framework thường gọi `get()` một lần để nhận luồng và đăng ký xử lý các phần tử mà luồng phát ra. Đây là cách phù hợp cho nguồn dữ liệu sống liên tục.

Một trường hợp khác là supplier truy vấn dữ liệu hữu hạn theo từng đợt, chẳng hạn lấy các bản ghi trong bảng outbox hoặc các đơn hàng đang chờ phát. Khi đó supplier cần được gọi định kỳ để lấy đợt dữ liệu tiếp theo. Spring Cloud Function cung cấp annotation `@PollableBean` để đánh dấu supplier reactive hữu hạn cần được poll lại. Spring Cloud Stream sử dụng thông tin này trong quá trình tạo nguồn và xử lý kết quả.

Ví dụ một lần truy vấn trả về ba sự kiện:

```java
Flux<OrderEvent> events = Flux.just(
    new OrderEvent("order-1001"),
    new OrderEvent("order-1002"),
    new OrderEvent("order-1003")
);
```

Nếu luồng này được phát theo cách tách phần tử, framework gửi ba message riêng. Nếu không tách, framework chuyển tiếp `Flux` như một luồng chưa được tách. Quyết định đó được biểu diễn bằng thuộc tính `splittable`.

## 2. Vai trò của @PollableBean và splittable

Trong các phiên bản Spring Cloud Function hiện đại, `@PollableBean` thuộc package:

```java
import org.springframework.cloud.function.context.PollableBean;
```

Đây là annotation đánh dấu một bean supplier reactive hữu hạn cần được gọi theo poller. Nó đóng vai trò metadata để các thành phần tích hợp như Spring Cloud Stream áp dụng cơ chế polling và xử lý kết quả.

Thuộc tính `splittable` quyết định framework có tách các phần tử trong kết quả reactive hay không:

| Cấu hình | Hành vi |
|---|---|
| `@PollableBean` | Mặc định `splittable = true` |
| `@PollableBean(splittable = true)` | Mỗi phần tử của luồng được phát thành một message riêng |
| `@PollableBean(splittable = false)` | Không thực hiện bước tách; giữ nguyên `Flux` được supplier trả về cho đường xử lý tiếp theo |

Có thể khai báo rõ `true` dù đây là giá trị mặc định. Cách viết tường minh giúp người đọc hiểu rằng mỗi phần tử là một đơn vị message độc lập.

Điểm cần nhớ là `splittable` là thuộc tính của annotation `@PollableBean`, không phải một binding property trong `application.yml`. Không cấu hình nó bằng cách tự thêm khóa như `spring.cloud.stream.bindings.output.splittable`.

Spring Cloud Function cung cấp annotation để đánh dấu supplier. Bản thân annotation không thực hiện việc poll hoặc phát message; framework tích hợp như Spring Cloud Stream đảm nhiệm các hành vi đó. Vì vậy, nếu chỉ gọi supplier trực tiếp trong unit test, kết quả nhận được vẫn là `Flux`; bước tách phần tử cần được kiểm tra ở tầng tích hợp.

## 3. Tách luồng thành từng message với splittable = true

Giả sử một dịch vụ định kỳ truy vấn các sự kiện đơn hàng đang chờ gửi. Mỗi sự kiện cần được gửi riêng để consumer có thể xử lý, retry và theo dõi độc lập.

```java
@Configuration
public class PendingOrderSource {

    @PollableBean(splittable = true)
    public Supplier<Flux<OrderEvent>> pendingOrderEvents(
            OrderRepository repository) {

        return () -> Flux.fromIterable(
            repository.findPendingEvents()
        );
    }
}
```

Ví dụ giả định `findPendingEvents()` trả về một danh sách hữu hạn các `OrderEvent`. Mỗi lần poll, supplier truy vấn danh sách mới và chuyển danh sách thành `Flux`.

Khi `splittable = true`, nếu truy vấn trả về ba phần tử thì kết quả được tách như sau:

```text
Một lần poll
    |
    v
Flux<OrderEvent>
    |
    +-- OrderEvent(order-1001) --> Message 1
    |
    +-- OrderEvent(order-1002) --> Message 2
    |
    +-- OrderEvent(order-1003) --> Message 3
```

Mỗi message đi qua output binding như một đơn vị dữ liệu riêng. Ví dụ cấu hình binding:

```yaml
spring:
  cloud:
    function:
      definition: pendingOrderEvents
    stream:
      bindings:
        pendingOrderEvents-out-0:
          destination: orders.pending
          content-type: application/json
  integration:
    poller:
      fixed-delay: 5000
```

Binding `pendingOrderEvents-out-0` kết nối nguồn phát với destination `orders.pending`. Cấu hình `fixed-delay` đặt khoảng chờ giữa các lần poll theo mili giây; giá trị 5000 tương ứng năm giây. Cấu hình poller điều khiển thời điểm gọi supplier, còn `splittable` điều khiển cách xử lý luồng mà supplier trả về. Hai thiết lập có trách nhiệm khác nhau.

Với ba phần tử trong một lần poll và chế độ tách được bật, framework tạo ba lần phát message. Nếu lần poll tiếp theo trả về hai phần tử, lần đó tạo thêm hai message. Số message phụ thuộc số phần tử thực tế mà supplier trả về trong từng lần poll.

## 4. Giữ nguyên luồng với splittable = false

Có những trường hợp tầng xử lý tiếp theo cần nhận luồng reactive như một đơn vị để tiếp tục áp dụng phép biến đổi hoặc điều phối riêng. Khi đó có thể đặt `splittable = false`:

```java
@Configuration
public class PendingOrderBatchSource {

    @PollableBean(splittable = false)
    public Supplier<Flux<OrderEvent>> pendingOrderBatch(
            OrderRepository repository) {

        return () -> Flux.fromIterable(
            repository.findPendingEvents()
        );
    }
}
```

Với cấu hình này, framework không tách các phần tử của `Flux` thành các message riêng ở bước xử lý đó. Supplier trả về luồng reactive nguyên vẹn cho đường xử lý tiếp theo.

Cần phân biệt việc giữ nguyên `Flux` với việc tạo một message có payload là `List<OrderEvent>`. `splittable = false` không tự gom các phần tử thành danh sách, không tạo batch DTO và cũng không định nghĩa định dạng wire để broker serialize một đối tượng `Flux`. Nếu mục tiêu là gửi một bản tin duy nhất chứa toàn bộ danh sách, hãy tạo một kiểu payload batch rõ ràng, chẳng hạn `OrderEventBatch` chứa `List<OrderEvent>`, rồi phát kiểu payload đó bằng một nguồn phù hợp. Chỉ dùng `splittable = false` khi đường xử lý phía sau thực sự cần nhận luồng reactive chưa tách và các thành phần tiếp theo hỗ trợ cách biểu diễn đó.

Ví dụ một kiểu payload batch tường minh:

```java
public record OrderEventBatch(
    String batchId,
    List<OrderEvent> events
) {}
```

Một supplier phát `OrderEventBatch` sẽ phát một object batch theo hợp đồng ứng dụng. Đây là cách thể hiện rõ ràng khi producer và consumer cần trao đổi cả đợt dữ liệu trong một payload.

## 5. So sánh hai chế độ qua cùng một dữ liệu

Giả sử supplier trả về:

```java
return () -> Flux.just(
    new OrderEvent("order-1001"),
    new OrderEvent("order-1002"),
    new OrderEvent("order-1003")
);
```

Kết quả ở mức xử lý luồng:

| Tiêu chí | `splittable = true` | `splittable = false` |
|---|---|---|
| Tách phần tử | Có | Không |
| Số message riêng được tạo bởi bước split | Một message cho mỗi phần tử | Không tạo message riêng cho từng phần tử ở bước split |
| Đơn vị xử lý tiếp theo | Từng phần tử | Luồng `Flux` nguyên vẹn |
| Consumer nhận từng sự kiện riêng | Phù hợp | Không phải hành vi mà cấu hình này yêu cầu |
| Trường hợp sử dụng | Phát sự kiện độc lập | Tầng xử lý tiếp theo cần luồng reactive chưa tách |

Khi chọn chế độ, hãy bắt đầu từ hợp đồng đầu ra mà consumer mong đợi. Nếu consumer nhận `OrderEvent` và xử lý từng đơn hàng, chọn chế độ tách. Nếu ứng dụng có một pipeline reactive khác cần xử lý toàn bộ publisher, có thể giữ luồng chưa tách và xác minh kiểu dữ liệu mà từng bước tiếp theo hỗ trợ.

## 6. splittable không phải partitioning hoặc batching

Ba khái niệm này giải quyết các vấn đề khác nhau.

### Splitting

Splitting biến một luồng gồm nhiều phần tử thành các message riêng. Ví dụ một `Flux<OrderEvent>` có ba phần tử được tách thành ba message. Mục đích là xác định ranh giới message ở tầng ứng dụng.

### Partitioning

Partitioning quyết định message được ghi vào partition nào của broker. Với Kafka, partition key có thể giúp các sự kiện cùng một khóa đi vào cùng partition để duy trì thứ tự trong phạm vi partition. Partitioning không tạo thêm message từ một phần tử và cũng không thay đổi số phần tử của `Flux`.

### Batching

Batching gom nhiều phần tử thành một nhóm dữ liệu được xử lý hoặc gửi theo cơ chế batch. Một batch payload thường cần hợp đồng rõ ràng, chẳng hạn `OrderEventBatch`. Batching có thể giảm số lần gửi nhưng consumer cần hiểu cấu trúc batch và xử lý các phần tử bên trong.

| Cơ chế | Câu hỏi được giải quyết | Ví dụ |
|---|---|---|
| Splitting | Một luồng nhiều phần tử được chuyển thành bao nhiêu message? | Ba phần tử thành ba message |
| Partitioning | Mỗi message được định tuyến tới partition nào? | Cùng order key vào cùng Kafka partition |
| Batching | Nhiều phần tử được gom thành đơn vị dữ liệu nào? | Một batch chứa danh sách 100 sự kiện |

Không dùng `splittable` để thay thế cấu hình partition key hoặc để bật batching. Nếu cần cả ba, hãy thiết kế từng bước rõ ràng và kiểm tra kết quả cuối cùng trên broker.

## 7. Chọn splittable theo yêu cầu xử lý sự kiện

Chế độ tách thường phù hợp khi:

- Mỗi phần tử là một sự kiện nghiệp vụ độc lập.
- Consumer có thể xử lý từng sự kiện mà không cần biết các sự kiện khác trong cùng lần poll.
- Muốn theo dõi, retry hoặc đưa từng message lỗi vào DLQ theo đơn vị sự kiện.
- Muốn broker phân phối từng message cho các consumer theo consumer group và partition.
- Mỗi sự kiện có ID, schema hoặc metadata riêng.

Giữ luồng chưa tách phù hợp khi:

- Thành phần tiếp theo cần thao tác trên toàn bộ publisher.
- Pipeline reactive sẽ tiếp tục lọc, biến đổi hoặc kết hợp dữ liệu trước khi tạo ranh giới message.
- Đường xử lý có hỗ trợ rõ kiểu dữ liệu được giữ nguyên.
- Ứng dụng có chiến lược riêng để chuyển luồng thành payload có thể gửi.

Nếu consumer cuối cùng cần một message cho mỗi phần tử, nên tách ở đúng ranh giới trước output binding. Nếu consumer cần một payload batch, hãy biểu diễn batch thành kiểu dữ liệu cụ thể và kiểm thử serialization thay vì kỳ vọng thuộc tính `splittable` tự tạo ra batch.

## 8. Polling, kích thước luồng và trạng thái dữ liệu

Một pollable supplier thường được gọi định kỳ. Nếu mỗi lần gọi truy vấn dữ liệu từ database, cần kiểm soát số bản ghi trả về và trạng thái của từng bản ghi.

Một số nguyên tắc vận hành:

- Trả về một luồng hữu hạn cho mỗi lần poll. Không dùng `@PollableBean` cho một publisher vô hạn cần được đăng ký một lần như nguồn reactive liên tục.
- Giới hạn số bản ghi mỗi lần truy vấn để tránh tạo một luồng quá lớn trong bộ nhớ.
- Có chiến lược đánh dấu bản ghi đã được claim, đã phát hoặc cần phát lại. Nếu không, các lần poll có thể phát lại cùng dữ liệu.
- Dùng event ID ổn định để consumer có thể nhận diện sự kiện đã xử lý.
- Đảm bảo consumer idempotent vì message có thể được giao lại sau lỗi hoặc khi trạng thái phát chưa được ghi nhận.
- Theo dõi thời gian truy vấn, số phần tử mỗi lần poll, số message phát thành công và số lỗi.

Không nên giả định một lần poll cùng nhiều phần tử tạo thành một giao dịch nguyên tử. Khi từng phần tử được phát riêng, lỗi ở một phần tử có thể có phạm vi xử lý khác với các phần tử đã gửi thành công. Việc retry, xác nhận và DLQ phụ thuộc binder, broker và cấu hình error handling. Nếu nghiệp vụ yêu cầu tất cả bản ghi trong một đợt phải thành công hoặc thất bại cùng nhau, cần thiết kế giao dịch hoặc cơ chế điều phối phù hợp thay vì dựa vào `splittable`.

## 9. Kiểm thử hành vi tách phần tử

Nên kiểm thử ở hai cấp.

### Unit test cho supplier

Unit test xác minh supplier trả về luồng hữu hạn với đúng phần tử và đúng thứ tự:

```java
@Test
void supplierReturnsPendingOrderEvents() {
    Supplier<Flux<OrderEvent>> supplier =
        () -> Flux.just(
            new OrderEvent("order-1001"),
            new OrderEvent("order-1002")
        );

    StepVerifier.create(supplier.get())
        .expectNextMatches(event ->
            event.orderId().equals("order-1001"))
        .expectNextMatches(event ->
            event.orderId().equals("order-1002"))
        .verifyComplete();
}
```

Test này chỉ xác minh nội dung supplier trả về. Nó không chứng minh framework đã áp dụng `splittable`.

### Integration test với Spring Cloud Stream Test Binder

Dùng Test Binder để khởi động Spring context, đăng ký pollable supplier và kiểm tra message đi qua output binding. Với `splittable = true`, gửi một luồng có ba phần tử rồi xác minh có ba message riêng với payload tương ứng. Với `splittable = false`, xác minh pipeline nhận được luồng chưa tách theo cách ứng dụng thiết kế.

Khi kiểm thử poller, nên kiểm soát thời gian và số lần gọi supplier để test ổn định. Có thể dùng cấu hình delay riêng trong test hoặc chủ động gọi thành phần phù hợp nếu phiên bản framework hỗ trợ. Tránh để test phụ thuộc vào lịch poll mặc định dài hoặc không xác định.

Test Binder kiểm tra wiring và hành vi framework trong bộ nhớ. Nếu cần xác minh serializer, số record thực tế, header mapping, partition key hoặc xác nhận giao nhận, bổ sung integration test với Kafka, RabbitMQ hoặc Pulsar tương ứng.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Supplier reactive chỉ chạy một lần | Supplier không được đánh dấu là pollable, nên framework xem nó là nguồn reactive liên tục | Dùng `@PollableBean` cho supplier tạo luồng hữu hạn cần poll định kỳ |
| Mỗi phần tử được gửi thành message riêng ngoài dự kiến | `splittable` mặc định là `true` | Đặt `splittable = false` nếu pipeline cần giữ nguyên luồng |
| Consumer mong một batch nhưng nhận nhiều message | Đang bật tách phần tử | Tạo batch payload rõ ràng hoặc thiết kế lại pipeline |
| Consumer không xử lý được Flux chưa tách | Đường xử lý tiếp theo mong payload từng phần tử hoặc không hỗ trợ publisher | Dùng chế độ tách hoặc thêm bước chuyển đổi phù hợp |
| Dữ liệu bị phát lặp ở các lần poll | Truy vấn lại cùng bản ghi hoặc trạng thái claim/checkpoint chưa đúng | Quản lý trạng thái phát và thiết kế idempotency |
| Test supplier đúng nhưng số message sai | Unit test chưa chạy qua post-processor và binder | Thêm integration test với Test Binder |

## 11. Khác biệt tên annotation giữa các phiên bản

Tên annotation có thể khác theo dòng Spring Cloud Function:

- Các phiên bản cũ sử dụng `@PollableSupplier`.
- Các phiên bản mới sử dụng `@PollableBean` trong package `org.springframework.cloud.function.context`.

Khi làm việc với dự án, hãy dùng Spring Boot và Spring Cloud release train tương thích, sau đó kiểm tra dependency Spring Cloud Function thực tế để chọn annotation đúng. Không trộn ví dụ của hai thế hệ API trong cùng một ứng dụng.

Trong ví dụ hiện đại, `@PollableBean(splittable = true)` hoặc `@PollableBean(splittable = false)` là cách thể hiện trực tiếp ý định. Cơ chế poller và xử lý đầu ra vẫn do Spring Cloud Stream cùng binder đảm nhiệm.

## 12. Checklist trước khi triển khai

- Xác nhận supplier trả về dữ liệu hữu hạn hay luồng liên tục.
- Dùng `@PollableBean` cho reactive supplier hữu hạn cần được poll lại.
- Chọn `splittable = true` nếu mỗi phần tử phải trở thành một message riêng.
- Chọn `splittable = false` chỉ khi đường xử lý tiếp theo cần giữ nguyên `Flux`.
- Không nhầm splitting với partitioning hoặc batching.
- Cấu hình poller riêng cho tần suất truy vấn dữ liệu.
- Giới hạn kích thước mỗi lần poll và kiểm soát trạng thái bản ghi.
- Thiết kế event ID, retry và idempotency để xử lý giao lại.
- Kiểm thử supplier, số message sau khi split và hành vi của binder.
- Xác minh bằng broker thật nếu phụ thuộc serialization, partition hoặc delivery guarantee.

## 13. Tài liệu tham khảo

- [Spring Cloud Stream Reference — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html), mục Suppliers (Sources).
- [Spring Cloud Function Reference — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html), mục Supplier.

Thuộc tính `splittable` giúp xác định ranh giới message khi một pollable reactive supplier trả về nhiều phần tử. Chế độ mặc định tách từng phần tử thành message riêng; chế độ tắt tách giữ nguyên luồng reactive cho bước xử lý tiếp theo. Chọn đúng chế độ theo hợp đồng đầu ra sẽ giúp producer phát sự kiện nhất quán và consumer xử lý đúng đơn vị dữ liệu mà ứng dụng mong đợi.

