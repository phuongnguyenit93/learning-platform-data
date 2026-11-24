# Giữ hàm không trạng thái và tránh trạng thái dùng chung không an toàn

Trong Spring Cloud Stream, `Supplier`, `Function` và `Consumer` thường được đăng ký thành các bean Spring rồi nối với broker thông qua binding. Một bean Spring thông thường có phạm vi singleton: cùng một đối tượng có thể phục vụ nhiều lần gọi trong suốt vòng đời ứng dụng. Tùy binder, số luồng tiêu thụ và cách triển khai, nhiều thông điệp có thể được xử lý đồng thời. Vì vậy, hàm xử lý sự kiện nên giữ dữ liệu của từng lần gọi trong biến cục bộ, tránh lưu dữ liệu nghiệp vụ có thể thay đổi vào field dùng chung.

Thiết kế không trạng thái giúp một thông điệp có thể được xử lý độc lập, dễ kiểm thử và mở rộng bằng cách tăng số consumer hoặc instance. Khi nghiệp vụ thực sự cần trạng thái qua nhiều thông điệp, trạng thái đó cần có chủ sở hữu và cơ chế cập nhật rõ ràng, chẳng hạn cơ sở dữ liệu giao dịch hoặc state store của Kafka Streams. Một field Java được chia sẻ trong bộ nhớ không tự trở thành kho trạng thái an toàn cho hệ thống phân tán.

## 1. Hiểu đúng về hàm không trạng thái

Một hàm xử lý sự kiện có thể được xem là không trạng thái khi kết quả và tác động của một lần gọi không phụ thuộc vào dữ liệu tạm thời được giữ lại từ lần gọi trước trong chính đối tượng hàm. Hàm đọc thông điệp đầu vào, thực hiện quy tắc nghiệp vụ và trả kết quả hoặc tạo tác động qua một thành phần có trách nhiệm lưu trữ riêng.

Ví dụ, hàm kiểm tra đơn hàng có thể nhận `OrderCreated`, kiểm tra số tiền và danh sách mặt hàng, sau đó tạo `OrderValidated`. Mọi dữ liệu cần cho lần xử lý đều nằm trong thông điệp hoặc được đọc từ dịch vụ phụ thuộc:

```java
public record OrderCreated(
        String eventId,
        String orderId,
        BigDecimal total,
        List<OrderItem> items) {}

public record OrderValidated(
        String eventId,
        String orderId,
        BigDecimal total) {}

@Bean
Function<OrderCreated, OrderValidated> validateOrder(OrderPolicy policy) {
    return event -> {
        policy.validate(event);
        return new OrderValidated(
                event.eventId(),
                event.orderId(),
                event.total());
    };
}
```

Hàm không giữ `event` trong field để dùng ở lần gọi kế tiếp. Mỗi lời gọi có biến `event` riêng. Đối tượng `OrderPolicy` được inject cũng cần có hợp đồng an toàn khi được nhiều luồng sử dụng: ưu tiên dịch vụ không giữ dữ liệu thay đổi theo yêu cầu, hoặc dịch vụ quản lý trạng thái qua kho dữ liệu có kiểm soát đồng thời.

Trong mô hình hàm của Spring Cloud Stream, các vai trò cơ bản gồm:

| Kiểu hàm | Cách sử dụng không trạng thái |
|---|---|
| `Supplier<T>` | Tạo một thông điệp mới từ nguồn dữ liệu hoặc thời điểm hiện tại; không dựa vào bộ đếm mutable trong field để tạo nội dung |
| `Function<T, R>` | Chuyển đổi một thông điệp thành kết quả; dữ liệu trung gian thuộc về lần gọi hiện tại |
| `Consumer<T>` | Thực hiện tác động cho thông điệp; trạng thái lâu dài được lưu qua repository hoặc dịch vụ chuyên trách |

Một `Supplier` tạo heartbeat có thể sinh thời điểm và mã định danh mới cho mỗi lần phát:

```java
public record Heartbeat(Instant emittedAt, UUID eventId) {}

@Bean
Supplier<Heartbeat> heartbeat() {
    return () -> new Heartbeat(Instant.now(), UUID.randomUUID());
}
```

Việc dùng đồng hồ và bộ sinh UUID không đòi hỏi giữ một biến nghiệp vụ dùng chung. Nếu cần số thứ tự tăng liên tục qua lần khởi động lại hoặc giữa nhiều instance, hãy dùng cơ chế cấp số có tính duy nhất và đồng bộ phù hợp, không dùng `int counter` trong bean.

## 2. Vì sao trạng thái dùng chung dễ gây lỗi?

Spring quản lý bean theo phạm vi singleton mặc định. Khi một hàm được đăng ký làm bean, binder có thể gọi cùng đối tượng đó từ các luồng xử lý khác nhau. Mức đồng thời phụ thuộc cấu hình binder, số partition, số consumer, số instance và cách ứng dụng triển khai. Không nên giả định mỗi thông điệp có một bản sao bean riêng hoặc mọi lời gọi luôn tuần tự.

Ví dụ sau có lỗi tranh chấp dữ liệu:

```java
@Bean
Consumer<OrderCreated> unsafeOrderHandler() {
    List<String> processedOrders = new ArrayList<>();

    return event -> {
        processedOrders.add(event.orderId());
        System.out.println("Processed: " + processedOrders.size());
    };
}
```

`ArrayList` không được thiết kế cho nhiều luồng ghi đồng thời. Hai lời gọi có thể cùng thay đổi cấu trúc bên trong, dẫn tới dữ liệu thiếu, trạng thái không nhất quán hoặc lỗi khi truy cập. Kể cả khi thay bằng `Collections.synchronizedList`, danh sách đó vẫn chỉ tồn tại trong một tiến trình, không có tính bền vững và không phối hợp được với instance khác.

**Lưu ý:** Một biến được khai báo bên trong phương thức tạo bean nhưng được lambda giữ lại vẫn là trạng thái sống cùng đối tượng lambda. Đặt biến vào bên trong hàm khởi tạo bean không biến nó thành biến cục bộ của từng lần xử lý.

Các kiểu trạng thái dùng chung thường gây vấn đề gồm:

- `ArrayList`, `HashMap`, `HashSet` hoặc object mutable được nhiều lời gọi cập nhật.
- Bộ đếm, tổng tiền hoặc số lượng tồn kho lưu trong field hay biến `static`.
- Một `DateFormat`, builder hoặc đối tượng thư viện không an toàn luồng được tái sử dụng.
- Cache không có giới hạn, chính sách hết hạn, đồng bộ và quy tắc vô hiệu hóa rõ ràng.
- Một payload mutable được lưu lại rồi thay đổi trong khi luồng khác vẫn đang sử dụng.

Các lỗi này có thể khó tái hiện ở máy phát triển vì chỉ xuất hiện khi tải tăng, nhiều partition được xử lý song song hoặc ứng dụng chạy nhiều instance.

## 3. Tổ chức dữ liệu theo phạm vi sở hữu

Hãy xác định dữ liệu thuộc phạm vi nào trước khi chọn nơi lưu:

| Phạm vi dữ liệu | Ví dụ | Nơi phù hợp |
|---|---|---|
| Một lần gọi | Payload, kết quả kiểm tra, biến tạm | Biến cục bộ trong lambda hoặc phương thức được gọi |
| Một thông điệp cần truyền qua các bước | `eventId`, `orderId`, `occurredAt`, dữ liệu nghiệp vụ | Payload bất biến và header có hợp đồng rõ |
| Trạng thái nghiệp vụ lâu dài | Tồn kho, trạng thái đơn hàng, dấu đã xử lý | Database hoặc dịch vụ lưu trữ có giao dịch và kiểm soát đồng thời |
| Trạng thái tổng hợp theo luồng | Tổng số đơn theo khách hàng, cửa sổ số liệu | Kafka Streams state store hoặc công cụ xử lý trạng thái phù hợp |
| Dữ liệu phụ trợ có thể tái tạo | Metadata tham chiếu, cấu hình ít thay đổi | Cache có giới hạn, chính sách hết hạn và quy tắc đồng bộ rõ ràng |

### 3.1. Giữ dữ liệu của mỗi lần gọi trong biến cục bộ

Biến cục bộ được tạo trong thân hàm cho mỗi lần thực thi. Khi không đưa tham chiếu mutable đó ra ngoài hoặc chia sẻ cho luồng khác, mỗi lần gọi có vùng dữ liệu riêng:

```java
@Bean
Function<OrderCreated, OrderValidated> validateOrder(OrderPolicy policy) {
    return event -> {
        BigDecimal normalizedTotal = event.total().setScale(2, RoundingMode.HALF_UP);
        List<OrderItem> validItems = event.items().stream()
                .filter(item -> item.quantity() > 0)
                .toList();

        policy.validate(normalizedTotal, validItems);

        return new OrderValidated(
                event.eventId(),
                event.orderId(),
                normalizedTotal);
    };
}
```

Danh sách được tạo từ stream là kết quả dùng cho lần gọi hiện tại. Không gán danh sách đó vào field của bean hoặc trả một tham chiếu mutable dùng chung cho nhiều consumer. Cần nhớ rằng biến local chỉ an toàn theo phạm vi nếu các object mà nó trỏ tới không đồng thời bị sửa bởi nơi khác.

### 3.2. Ưu tiên payload bất biến

Payload bất biến giúp giảm nguy cơ một bước xử lý thay đổi dữ liệu mà bước khác đang đọc. Java `record` phù hợp với nhiều message DTO vì các thành phần được gán khi tạo đối tượng và không có setter:

```java
public record OrderItem(String productId, int quantity) {}

public record OrderCreated(
        String eventId,
        String orderId,
        List<OrderItem> items) {

    public OrderCreated {
        items = List.copyOf(items);
    }
}
```

`record` chỉ bảo đảm bất biến nông. Nếu một thành phần bên trong là object mutable, thành phần đó vẫn có thể bị thay đổi qua tham chiếu khác. Trong ví dụ, `List.copyOf` tạo danh sách không thể sửa qua API `List`, và `OrderItem` là record chỉ chứa giá trị bất biến. Với payload lồng sâu, cần sao chép hoặc dùng kiểu dữ liệu bất biến ở các cấp phù hợp.

Không sửa trực tiếp message nhận vào để gắn kết quả xử lý. Hãy tạo message đầu ra mới hoặc dùng một kiểu dữ liệu kết quả riêng, giúp hợp đồng đầu vào và đầu ra rõ ràng.

### 3.3. Dùng dependency có hợp đồng an toàn luồng

Bean được inject vào hàm có thể là singleton giống như hàm. Điều đó không có nghĩa mọi dependency đều không an toàn; nó có nghĩa nhóm phải hiểu hợp đồng sử dụng của chúng.

- Các service stateless thường điều phối lời gọi tới repository hoặc client có quản lý kết nối.
- Spring Data repository và transaction manager được thiết kế để dùng qua cơ chế quản lý của Spring, nhưng ranh giới giao dịch và cách cập nhật dữ liệu vẫn cần được thiết kế đúng.
- Đối tượng tự viết có field mutable cần đồng bộ hóa hoặc được thay bằng thiết kế không chia sẻ trạng thái.
- Không giữ `EntityManager`, JDBC connection hoặc transaction context trong field để tái sử dụng qua nhiều lần gọi; để Spring quản lý phạm vi tài nguyên.

Ví dụ, consumer có thể gọi một service xử lý giao dịch thay vì giữ bản đồ tồn kho trong bean:

```java
@Bean
Consumer<OrderCreated> reserveInventory(InventoryService inventoryService) {
    return event -> inventoryService.reserve(event);
}
```

Service phải kiểm soát cập nhật tồn kho trong kho dữ liệu, chẳng hạn bằng câu lệnh cập nhật có điều kiện, khóa phù hợp hoặc optimistic locking. Việc chuyển logic sang một service khác không tự làm cho logic an toàn; điều quan trọng là nơi sở hữu trạng thái và cách xử lý cạnh tranh được xác định rõ.

## 4. Không dùng bộ đếm trong bộ nhớ làm trạng thái nghiệp vụ

Một ví dụ dễ gặp là đếm số thông điệp đã xử lý:

```java
@Bean
Consumer<OrderCreated> unsafeCounter() {
    AtomicInteger count = new AtomicInteger();

    return event -> {
        int current = count.incrementAndGet();
        System.out.println("Processed orders: " + current);
    };
}
```

`AtomicInteger` giúp thao tác tăng có tính nguyên tử trong một tiến trình, nhưng nó không giải quyết các vấn đề sau:

- Khi ứng dụng khởi động lại, giá trị quay về ban đầu.
- Nhiều instance có các bộ đếm khác nhau và không có tổng số nhất quán.
- Retry hoặc giao lại message có thể tăng bộ đếm lần nữa.
- Giá trị không gắn với giao dịch nghiệp vụ và không thể dùng làm bằng chứng đã xử lý.

Nếu chỉ dùng để tạo số liệu chẩn đoán cục bộ, hãy dùng metrics system phù hợp và chấp nhận đúng phạm vi của metric. Nếu cần thống kê nghiệp vụ, hãy ghi nhận bằng cơ chế lưu trữ có định danh, chống trùng và chính sách tổng hợp rõ ràng. Không lấy một biến đếm trong bean làm nguồn dữ liệu chính thức.

## 5. Cập nhật trạng thái lâu dài một cách an toàn

Nhiều nghiệp vụ cần nhớ kết quả của thông điệp trước đó. Ví dụ, khi nhận `OrderCreated`, dịch vụ kho phải trừ hoặc giữ số lượng tồn kho. Trạng thái tồn kho cần tồn tại qua lần khởi động lại và phải được cập nhật chính xác khi hai đơn hàng cùng yêu cầu một sản phẩm.

Một cách tiếp cận là đưa thao tác vào service có transaction và lưu dấu `eventId` đã xử lý trong cùng ranh giới giao dịch:

```java
@Service
public class InventoryService {
    private final ProcessedEventRepository processedEvents;
    private final InventoryRepository inventory;

    public InventoryService(
            ProcessedEventRepository processedEvents,
            InventoryRepository inventory) {
        this.processedEvents = processedEvents;
        this.inventory = inventory;
    }

    @Transactional
    public void reserve(OrderCreated event) {
        if (processedEvents.existsById(event.eventId())) {
            return;
        }

        for (OrderItem item : event.items()) {
            int updated = inventory.reserveIfAvailable(
                    item.productId(), item.quantity());
            if (updated != 1) {
                throw new InsufficientInventoryException(item.productId());
            }
        }

        processedEvents.save(new ProcessedEvent(event.eventId()));
    }
}
```

Trong ví dụ, `reserveIfAvailable` nên thực hiện cập nhật có điều kiện ở database, ví dụ chỉ giảm tồn kho khi `available_quantity >= requested_quantity`, và trả về số dòng đã cập nhật. Bảng lưu `ProcessedEvent` cần ràng buộc duy nhất trên `eventId`. Việc kiểm tra và ghi dấu phải được bảo vệ trong cùng giao dịch; chỉ gọi `existsById` trước rồi ghi sau mà không có ràng buộc duy nhất vẫn có thể gặp race condition khi hai consumer xử lý cùng một sự kiện đồng thời.

Khi hai thông điệp khác nhau cùng cập nhật một sản phẩm, database cần giải quyết cạnh tranh bằng khóa, cập nhật nguyên tử, optimistic locking hoặc cơ chế phù hợp với mô hình dữ liệu. Nếu transaction thất bại, thay đổi tồn kho và dấu xử lý phải cùng rollback để thông điệp có thể được thử lại an toàn.

Idempotency ở tầng nghiệp vụ đặc biệt quan trọng vì message broker có thể giao lại thông điệp sau timeout, restart hoặc lỗi xác nhận. Việc giữ trạng thái trong database không tự bảo đảm exactly-once; ứng dụng vẫn cần định danh sự kiện, ràng buộc dữ liệu và chính sách retry đúng.

## 6. Khi cần trạng thái theo luồng, dùng công cụ có mô hình trạng thái

Không phải mọi phép tính đều có thể xử lý độc lập trên từng message. Ví dụ, hệ thống cần đếm số đơn theo khách hàng, tính tổng doanh thu theo cửa sổ thời gian hoặc duy trì số dư tổng hợp theo khóa. Nếu trạng thái được lưu trong một `HashMap` field của function bean, trạng thái chỉ nằm trong một instance và mất khi tiến trình dừng.

Với luồng Kafka cần trạng thái theo key, Kafka Streams cung cấp các phép biến đổi có state store và cơ chế khôi phục trạng thái. Kafka Streams binder của Spring Cloud Stream cho phép khai báo hàm dùng kiểu `KStream` hoặc `KTable`, tách biệt với function thuần xử lý từng message:

```java
@Bean
Function<KStream<String, OrderEvent>, KStream<String, Long>> orderCountByCustomer() {
    return events -> events
            .groupByKey()
            .count(Materialized.as("orders-count-by-customer"))
            .toStream();
}
```

Trong ví dụ, key của record phải là mã khách hàng nếu muốn đếm theo khách hàng. `count` duy trì kết quả qua state store có tên `orders-count-by-customer`; Kafka Streams quản lý changelog để khôi phục state khi task được khởi động lại hoặc chuyển sang instance khác. Cần cấu hình đúng key, partition, serde và topology. Nếu key không đúng hoặc dữ liệu cùng khách hàng nằm ở partition khác nhau, kết quả tổng hợp có thể không phản ánh đúng phạm vi mong muốn.

State store không phải một bản đồ Java toàn cục. Nó thuộc topology/task, được gắn với partition và có cơ chế phục hồi. Nhóm cần theo dõi dung lượng lưu trữ, changelog, thời gian phục hồi và thay đổi topology khi triển khai. Với RabbitMQ hoặc Pulsar, hãy chọn mô hình xử lý có trạng thái tương ứng với nền tảng đang dùng; không thể mang nguyên cơ chế state store Kafka Streams sang binder khác.

## 7. Những cách “làm cho thread-safe” chưa giải quyết đúng bài toán

Một số cách sửa có thể loại bỏ một lỗi tranh chấp nhưng vẫn không giải quyết vấn đề sở hữu trạng thái:

| Cách làm | Giới hạn còn lại |
|---|---|
| Thay `HashMap` bằng `ConcurrentHashMap` | An toàn hơn cho thao tác map trong một JVM, nhưng dữ liệu không bền vững và không đồng bộ giữa nhiều instance |
| Bọc collection bằng `synchronized` | Có thể giảm race condition trong một tiến trình nhưng tạo điểm nghẽn và không bảo vệ giao dịch với database/broker |
| Dùng `AtomicInteger` cho số lượng tồn kho | Chỉ nguyên tử trong bộ nhớ một tiến trình; không bảo đảm cập nhật đồng thời giữa instance hoặc qua restart |
| Dùng `ThreadLocal` | Gắn dữ liệu với thread, trong khi thread được tái sử dụng; không phù hợp để lưu trạng thái nghiệp vụ hoặc truyền ngữ cảnh bất đồng bộ |
| Dùng `static` field | Chia sẻ trong classloader hiện tại, không chia sẻ an toàn giữa nhiều tiến trình và khó kiểm thử cô lập |
| Giảm concurrency về một | Có thể che triệu chứng trong môi trường nhỏ, giảm thông lượng và không bảo vệ khi chạy nhiều instance |

Các cấu trúc đồng bộ và cache thread-safe vẫn hữu ích cho dữ liệu phụ trợ có phạm vi rõ, chẳng hạn cache cấu hình bất biến. Nhưng nếu dữ liệu có ý nghĩa nghiệp vụ, cần tồn tại qua restart hoặc được nhiều instance cập nhật, hãy chuyển nó sang nơi lưu trữ phù hợp.

## 8. Kiểm thử tính độc lập và an toàn đồng thời

Kiểm thử đơn vị cho từng hàm cần xác nhận cùng một đầu vào luôn tạo kết quả như mong đợi và không phụ thuộc thứ tự gọi trước đó. Một cách đơn giản là gọi hàm nhiều lần với dữ liệu khác nhau rồi gọi lại dữ liệu đầu tiên để phát hiện dữ liệu cũ bị giữ lại:

```java
@Test
void validationDoesNotLeakDataBetweenInvocations() {
    Function<OrderCreated, OrderValidated> function =
            validateOrder(new DefaultOrderPolicy());

    OrderValidated first = function.apply(order("evt-1", "ord-1"));
    OrderValidated second = function.apply(order("evt-2", "ord-2"));
    OrderValidated firstAgain = function.apply(order("evt-1", "ord-1"));

    assertThat(first.orderId()).isEqualTo("ord-1");
    assertThat(second.orderId()).isEqualTo("ord-2");
    assertThat(firstAgain).isEqualTo(first);
}
```

Với service cập nhật database, kiểm thử tích hợp cần bao gồm hai consumer đồng thời xử lý các đơn hàng tranh cùng lượng tồn kho, cùng một `eventId` được giao lại, transaction rollback và ứng dụng khởi động lại. Kết quả cần bảo đảm không âm tồn kho, không ghi nhận cùng một sự kiện hai lần và không mất dấu xử lý khi transaction thất bại.

Với Kafka Streams, kiểm thử thêm việc khôi phục state store, phân công lại partition, dữ liệu đến trễ và thay đổi số partition. Với binder thông thường, cần kiểm thử ở concurrency mà môi trường triển khai thực sự sử dụng; kiểm thử đơn luồng không đủ để phát hiện mọi race condition.

## 9. Quy tắc thiết kế trước khi triển khai

- [ ] Bean `Supplier`, `Function` và `Consumer` không giữ payload hoặc dữ liệu nghiệp vụ của từng message trong field mutable.
- [ ] Các dependency singleton được kiểm tra về tính an toàn khi nhiều luồng gọi đồng thời.
- [ ] Payload ưu tiên kiểu bất biến; collection và object lồng nhau không bị chia sẻ để sửa đổi.
- [ ] Biến tạm của một lần xử lý nằm trong phạm vi lời gọi và không thoát sang tác vụ bất đồng bộ không kiểm soát.
- [ ] Trạng thái nghiệp vụ được lưu ở database hoặc dịch vụ có hợp đồng cập nhật đồng thời rõ ràng.
- [ ] Consumer có idempotency theo `eventId` và ràng buộc duy nhất ở nơi lưu dấu xử lý.
- [ ] Trạng thái tổng hợp theo luồng dùng state store hoặc nền tảng có cơ chế phục hồi phù hợp.
- [ ] Không dùng `static`, `ThreadLocal`, bộ đếm hoặc collection trong bộ nhớ làm nguồn trạng thái nghiệp vụ lâu dài.
- [ ] Có kiểm thử lặp thông điệp, đồng thời, rollback và restart theo yêu cầu của luồng.

Hàm không trạng thái là lựa chọn tốt cho phần lớn bước biến đổi và định tuyến sự kiện trong Spring Cloud Stream vì mỗi thông điệp có thể được xử lý độc lập và mở rộng theo năng lực consumer. Khi nghiệp vụ cần ghi nhớ dữ liệu, hãy đưa trạng thái vào thành phần có trách nhiệm lưu trữ, đồng bộ và phục hồi. Cách phân chia này giúp tránh lỗi do bean singleton bị nhiều luồng cùng sửa, đồng thời làm rõ tính nhất quán và khả năng khôi phục của toàn bộ luồng sự kiện.
