# Event cho mọi thao tác

Application event giúp các module Spring Modulith thông báo một sự thật nghiệp vụ đã xảy ra mà không cần gọi trực tiếp từng consumer. Tuy nhiên, việc biến mọi thao tác thành event là một anti-pattern. Nếu mỗi lần đọc, ghi, đổi một field hoặc gọi một method đều phát event, hệ thống sẽ có nhiều thông điệp hơn nhưng không nhất thiết có thêm giá trị nghiệp vụ. Các module khó hiểu ai chịu trách nhiệm, consumer phải xử lý quá nhiều chi tiết và việc theo dõi một quy trình trở nên phức tạp.

Event nên được dùng khi một fact có ý nghĩa với domain đã xảy ra và có thể có những thành phần khác cần phản ứng độc lập. Command dùng để yêu cầu một hành động. Query dùng để đọc dữ liệu. Lời gọi method trong cùng một module vẫn là cách phù hợp cho các bước triển khai nội bộ. Chọn đúng cơ chế giao tiếp giúp giữ ranh giới module rõ ràng và giảm số luồng bất đồng bộ không cần thiết.

## 1. Anti-pattern là gì?

“Event cho mọi thao tác” xuất hiện khi nhóm phát event cho gần như mọi hoạt động của ứng dụng, bất kể hoạt động đó có ý nghĩa nghiệp vụ hay không. Ví dụ:

- Phát `OrderEntityLoaded` mỗi khi repository đọc một đơn hàng.
- Phát `OrderFieldChanged` cho từng field được cập nhật, kể cả field kỹ thuật.
- Phát `OrderSaveStarted`, `OrderSaveFinished` và `OrderRepositoryCalled` cho luồng CRUD thông thường.
- Dùng event để yêu cầu một module khác thực hiện ngay một hành động cần kết quả đồng bộ.
- Tạo event riêng cho mỗi method nội bộ chỉ để tránh một lời gọi method trực tiếp.
- Phát event cho các thay đổi trung gian chưa được commit hoặc chưa trở thành fact nghiệp vụ.

Những event này làm tăng số lượng hợp đồng phải duy trì, tăng số listener và tạo thêm các điểm lỗi. Một thao tác đơn giản có thể sinh ra chuỗi event khó lần theo, trong khi consumer không biết event nào biểu diễn kết quả nghiệp vụ thực sự.

## 2. Phân biệt command, event và lời gọi nội bộ

Ba cách giao tiếp có vai trò khác nhau:

| Cơ chế | Ý nghĩa | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- | --- |
| Method call | Một thành phần yêu cầu thành phần khác trong cùng luồng thực thi làm việc. | “Hãy chạy bước này và trả kết quả cho tôi.” | `inventory.reserve(orderId)` |
| Command | Một yêu cầu có chủ đích để một thành phần sở hữu xử lý. | “Hãy thực hiện hành động này.” | `ReserveInventory` |
| Event | Một fact đã xảy ra và được công bố cho các consumer quan tâm. | “Điều gì đã xảy ra?” | `InventoryReserved` |
| Query | Yêu cầu lấy dữ liệu mà không chủ đích thay đổi trạng thái. | “Dữ liệu hiện tại là gì?” | `FindAvailableInventory` |

Ví dụ luồng đặt hàng:

```text
PlaceOrder (command)
    -> OrderManagement kiểm tra và lưu đơn
    -> OrderPlaced (event)
    -> Inventory listener giữ hàng
    -> Notification listener gửi xác nhận
```

`PlaceOrder` yêu cầu tạo đơn. `OrderPlaced` chỉ được phát khi đơn thực sự đã được tạo thành công theo transaction nghiệp vụ. `ReserveInventory` nếu cần một yêu cầu có đích nhận rõ ràng thì là command; `InventoryReserved` là fact được phát sau khi việc giữ hàng thành công.

Không dùng event để thay thế method call hoặc command chỉ vì event có vẻ làm các module ít phụ thuộc hơn. Nếu caller cần biết kết quả ngay để quyết định bước tiếp theo, một API hoặc command có phản hồi rõ ràng thường phù hợp hơn.

## 3. Dấu hiệu nhận biết event đang bị lạm dụng

Một số dấu hiệu có thể quan sát trong codebase:

- Tên event kết thúc bằng `Started`, `Called`, `Loaded`, `Saved` hoặc `Updated` nhưng không mô tả fact domain rõ ràng.
- Mỗi repository method hoặc setter đều phát event.
- Một event chỉ có một listener duy nhất và listener đó luôn được gọi như một bước bắt buộc, đồng bộ trong mọi luồng.
- Consumer phải gọi ngược producer để hỏi event có nghĩa gì hoặc tải lại toàn bộ trạng thái chỉ vì payload quá nghèo nàn.
- Một thao tác nghiệp vụ đơn giản tạo ra nhiều event trung gian không có consumer độc lập.
- Các listener phát event tiếp nối chỉ để gọi lại đúng module nguồn hoặc chuyển tiếp một method call.
- Người vận hành khó xác định event nào là kết quả nghiệp vụ, event nào chỉ là log hoặc thông báo kỹ thuật.
- Test cần chờ nhiều event không mang ý nghĩa để xác minh một use case đơn giản.

Không phải mọi dấu hiệu đều chứng minh thiết kế sai. Một event có một consumer vẫn có thể có ý nghĩa nếu consumer thuộc module khác và producer không cần biết consumer đó. Ngược lại, nhiều listener không làm một event trở nên đúng nếu event chỉ mô tả một thay đổi kỹ thuật không có giá trị với domain.

## 4. Vì sao phát event cho mọi thao tác gây hại?

### Tăng coupling qua hợp đồng

Mỗi event là một hợp đồng mà producer và consumer phải hiểu. Khi event mô tả chi tiết nội bộ như `OrderFieldChanged`, consumer có thể bắt đầu phụ thuộc vào tên field, cấu trúc entity hoặc cách lưu dữ liệu. Producer khó refactor vì mọi thay đổi nội bộ có thể trở thành thay đổi contract.

### Tăng số lượng luồng bất đồng bộ

Mỗi listener thêm một điểm thực thi, transaction, retry và khả năng thất bại. Khi một thao tác đơn giản phát nhiều event, hệ thống phải quản lý nhiều publication hơn, tăng backlog và chi phí quan sát.

### Khó bảo đảm thứ tự và nhất quán

Event listener có thể chạy sau commit và bất đồng bộ. Nếu mỗi field change tạo một event, consumer có thể nhận các thay đổi theo thứ tự khác nhau hoặc chỉ nhận một phần khi có lỗi. Consumer phải tự dựng lại trạng thái trung gian mà domain không hề muốn công bố.

### Khó xử lý duplicate và retry

Số lượng event lớn làm tăng số publication có thể được giao lại. Nếu mỗi event gây tác dụng phụ, consumer phải có idempotency và versioning cho nhiều luồng nhỏ không cần thiết.

### Khó quan sát và kiểm thử

Log, trace, metric và test phải xử lý nhiều event hơn. Một test tạo đơn có thể phải chờ `OrderCreated`, `OrderSaved`, `OrderStatusChanged`, `OrderAuditUpdated` và `OrderRepositoryCompleted` dù chỉ cần xác minh một fact `OrderPlaced`.

### Tạo chi phí vận hành không tương xứng

Event registry, broker, topic, schema, retention, retry và DLT đều có chi phí. Tăng số event làm tăng dung lượng, số consumer, quyền truy cập và số tình huống cần xử lý khi deploy.

## 5. Chỉ phát event cho fact có ý nghĩa nghiệp vụ

Một event phù hợp thường đáp ứng các câu hỏi:

1. Có điều gì có ý nghĩa trong domain đã xảy ra không?
2. Fact này có thể được module khác hoặc hệ thống ngoài quan tâm độc lập không?
3. Consumer có thể phản ứng dựa trên hợp đồng ổn định mà không cần biết chi tiết nội bộ producer không?
4. Fact có ranh giới rõ, thời điểm xảy ra rõ và dữ liệu cần thiết để diễn giải không?
5. Nếu không có consumer hôm nay, event vẫn có ý nghĩa trong domain hoặc có khả năng mở rộng hợp lý không?

Ví dụ event có ý nghĩa:

| Event | Fact được mô tả |
| --- | --- |
| `OrderPlaced` | Đơn hàng đã được đặt và chấp nhận. |
| `PaymentCaptured` | Khoản thanh toán đã được thu thành công. |
| `ShipmentDispatched` | Hàng đã được bàn giao cho đơn vị vận chuyển. |
| `SubscriptionCancelled` | Đăng ký đã được hủy hợp lệ. |
| `InventoryReserved` | Số lượng hàng đã được giữ cho một yêu cầu cụ thể. |

Ví dụ thường không nên công bố như domain event:

| Tên | Vì sao không phù hợp |
| --- | --- |
| `OrderEntityLoaded` | Chi tiết đọc dữ liệu nội bộ, không phải fact nghiệp vụ. |
| `OrderRepositorySaved` | Lộ implementation persistence. |
| `OrderNameFieldSet` | Thay đổi một field không nhất thiết có ý nghĩa độc lập. |
| `OrderHandlerStarted` | Mốc thực thi kỹ thuật; phù hợp với log/trace. |
| `OrderMapperInvoked` | Chi tiết triển khai không nên trở thành contract. |

Mốc kỹ thuật vẫn có thể được quan sát bằng log, metric hoặc trace. Không cần biến mọi mốc quan sát thành application event.

## 6. Ví dụ anti-pattern: event hóa từng thao tác CRUD

Giả sử module `orders` có use case đổi địa chỉ giao hàng. Một thiết kế quá chi tiết có thể phát event ở từng bước:

```java
@Transactional
public void changeShippingAddress(UUID orderId, Address address) {
    events.publishEvent(new OrderChangeStarted(orderId));

    Order order = orders.findById(orderId).orElseThrow();
    events.publishEvent(new OrderLoaded(orderId));

    order.setShippingAddress(address);
    events.publishEvent(new OrderAddressFieldChanged(orderId, address));

    orders.save(order);
    events.publishEvent(new OrderSaved(orderId));
    events.publishEvent(new OrderChangeFinished(orderId));
}
```

Các event trên mô tả tiến trình triển khai, không phải tất cả đều là fact mà module khác cần. Consumer có thể vô tình phụ thuộc vào trình tự repository load/save và cấu trúc entity.

Một thiết kế rõ hơn:

```java
@Transactional
public void changeShippingAddress(UUID orderId, Address address) {
    Order order = orders.findById(orderId).orElseThrow();
    order.changeShippingAddress(address);
    orders.save(order);

    events.publishEvent(new OrderShippingAddressChanged(
            order.getId(),
            order.getShippingAddress(),
            order.getVersion()));
}
```

`OrderShippingAddressChanged` là event nếu việc đổi địa chỉ là fact nghiệp vụ mà consumer cần quan tâm, chẳng hạn module vận chuyển cập nhật thông tin giao hàng hoặc module audit nghiệp vụ ghi nhận thay đổi. Nếu không có consumer độc lập và thay đổi chỉ là một bước nội bộ, có thể không cần phát event.

Việc lưu entity không tự động có nghĩa phải phát `OrderSaved`. Hãy phát event theo hành vi domain, không theo từng thao tác persistence.

## 7. Ví dụ anti-pattern: dùng event như lời gọi method từ xa

Một luồng thường gặp là phát event `CalculateShippingCost` rồi chờ listener trả `ShippingCostCalculated` để tiếp tục tạo đơn. Nếu caller cần kết quả ngay và không có workflow bất đồng bộ, đây có thể là một lời gọi API bị biến thành event một cách không cần thiết.

```java
// Thiết kế dễ gây phức tạp nếu caller luôn phải chờ phản hồi ngay.
events.publishEvent(new CalculateShippingCost(orderId));
// Sau đó chờ một event phản hồi để tiếp tục cùng request.
```

Nếu module cần tính phí và phải có kết quả trước khi tạo đơn, hãy gọi API công khai của module tính phí hoặc một domain service phù hợp:

```java
ShippingQuote quote = shippingPricing.calculateQuote(request);
Order order = orderManagement.placeOrder(command, quote);
```

Event phù hợp hơn khi việc tính toán hoặc phản ứng có thể diễn ra độc lập sau một fact đã xảy ra, và caller không cần kết quả đó để hoàn tất transaction hiện tại.

Có những workflow bất đồng bộ thực sự cần command/message và phản hồi tương quan. Khi đó, hãy thiết kế rõ command ID, correlation ID, trạng thái workflow, timeout và compensation. Đừng giả vờ đó là một domain event thông thường.

## 8. Đừng phát event cho trạng thái trung gian chưa commit

Nếu transaction nguồn rollback, event mô tả fact chưa thực sự xảy ra không nên được consumer xử lý như một thay đổi đã hoàn tất. Với Spring Modulith, listener cần chạy sau commit có thể dùng `@ApplicationModuleListener`.

```java
@Transactional
public UUID placeOrder(PlaceOrder command) {
    Order order = orders.save(Order.create(command));
    events.publishEvent(new OrderPlaced(order.getId(), order.getVersion()));
    return order.getId();
}

@ApplicationModuleListener
void on(OrderPlaced event) {
    inventory.reserveFor(event.orderId());
}
```

Ví dụ minh họa: event được phát trong transaction nguồn, listener được xử lý sau commit theo semantics của `@ApplicationModuleListener`. Nếu transaction nguồn rollback, publication được đăng ký trong transaction đó không trở thành công việc đã commit để listener xử lý.

Không phát `OrderPlaced` ngay khi bắt đầu xử lý command rồi sau đó mới kiểm tra tồn kho hoặc điều kiện nghiệp vụ. Chỉ phát fact khi điều kiện để tuyên bố fact đó đã xảy ra được đáp ứng.

## 9. Chọn mức độ chi tiết phù hợp cho event

Event không nên quá rộng đến mức consumer không biết điều gì thay đổi, nhưng cũng không nên quá nhỏ đến mức mỗi field tạo một hợp đồng riêng.

Ví dụ với đơn hàng:

| Thay đổi | Event phù hợp khi có ý nghĩa độc lập |
| --- | --- |
| Đơn hàng được tạo | `OrderPlaced` |
| Địa chỉ giao hàng đổi | `OrderShippingAddressChanged` |
| Thanh toán được thu | `PaymentCaptured` |
| Đơn hàng bị hủy | `OrderCancelled` |
| Field ghi chú nội bộ đổi | Có thể chỉ là thay đổi nội bộ, không cần event. |
| Cột `updated_at` được cập nhật | Không phải fact nghiệp vụ độc lập. |

Hãy chọn granularity dựa trên consumer và ý nghĩa domain. Nếu một event tổng quát `OrderUpdated` buộc consumer tải lại toàn bộ đơn để đoán thay đổi gì, event có thể quá rộng. Nếu mỗi field đều có event riêng nhưng không có consumer độc lập, event có thể quá nhỏ.

Một event có thể mang snapshot đủ để consumer thực hiện phản ứng mà không phải truy cập entity nội bộ. Tuy nhiên, không cần đưa toàn bộ aggregate vào payload nếu consumer chỉ cần một số trường ổn định.

## 10. Không biến event thành thông báo log/audit cho mọi dòng code

Audit nghiệp vụ và log kỹ thuật có mục tiêu khác nhau:

- Log ghi nhận mốc thực thi, exception, latency, trace và thông tin chẩn đoán.
- Audit record lưu ai đã thực hiện hành động nào, khi nào và dữ liệu nào thay đổi theo yêu cầu kiểm toán.
- Domain event mô tả fact nghiệp vụ mà các consumer có thể phản ứng.

Không cần phát application event cho `RepositoryMethodEntered` hoặc `MapperCompleted` chỉ để có log. Dùng structured logging và tracing để quan sát các bước kỹ thuật. Nếu cần audit, thiết kế audit record với retention, quyền truy cập và tính toàn vẹn phù hợp.

Một domain event có thể đồng thời được lưu làm audit history nếu semantics và chính sách lưu trữ phù hợp, nhưng không nên mặc định mọi log đều phải trở thành event hoặc mọi event đều là audit record đầy đủ.

## 11. Event nhiều listener không có nghĩa là phải phát event cho mọi thay đổi

Một event có nhiều consumer độc lập là trường hợp sử dụng tự nhiên của event-driven design. Ví dụ, `OrderPlaced` có thể được inventory, billing, notification và analytics lắng nghe. Producer không cần biết các listener này.

Tuy nhiên, không nên tạo event chỉ để có thể nói rằng hệ thống “event-driven”. Nếu không có consumer độc lập, event không biểu diễn một fact có ý nghĩa và caller cần phản hồi ngay, method call hoặc command có thể đơn giản hơn.

Một listener duy nhất cũng không tự động là sai. Listener có thể thuộc module khác, có vòng đời độc lập hoặc cần xử lý sau commit. Câu hỏi quan trọng là ranh giới và semantics, không phải số lượng listener.

## 12. Hệ quả lên Event Publication Registry và retry

Spring Modulith có thể theo dõi publication tới transactional listener bằng Event Publication Registry. Mỗi listener được theo dõi có thể có publication riêng. Khi số event tăng vì mọi thao tác đều được event hóa, registry phải quản lý nhiều publication hơn và các trạng thái pending/retry cũng tăng.

Hệ quả vận hành:

- Nhiều publication record hơn và tăng chi phí lưu trữ.
- Nhiều listener execution và transaction hơn.
- Tăng số publication có thể thất bại hoặc cần resubmit.
- Backlog khó ưu tiên nếu phần lớn event chỉ mô tả thao tác kỹ thuật.
- Khó phân biệt lỗi nghiệp vụ quan trọng với lỗi của event không có giá trị.

Giảm event không cần thiết giúp registry tập trung vào các fact và phản ứng thực sự quan trọng. Với event vẫn cần giữ, listener cần idempotent vì publication có thể được xử lý lại.

Không dùng registry như một queue tùy ý cho mọi lệnh. Registry theo dõi việc giao event tới transactional listener; nó không thay thế command queue, workflow engine hoặc event store.

## 13. Tác động tới schema và khả năng tương thích

Mỗi event được công bố có thể trở thành contract mà consumer phải hỗ trợ qua nhiều phiên bản ứng dụng. Nếu phát event cho từng field hoặc chi tiết persistence, một thay đổi schema database có thể buộc producer phải thay đổi nhiều event và consumer.

Để giảm coupling:

- Đặt tên theo fact nghiệp vụ, không theo tên cột hoặc entity.
- Dùng payload DTO bất biến, không truyền JPA entity.
- Chỉ đưa field consumer cần và có ý nghĩa ổn định.
- Giữ event type độc lập với Java package và broker topic.
- Version schema khi thay đổi không tương thích.
- Có kế hoạch upcast/replay nếu cần đọc event lịch sử.

Không tăng schema version chỉ vì refactor nội bộ. Ngược lại, thay đổi ý nghĩa field dù giữ nguyên tên cũng có thể là breaking change. Contract cần được đánh giá theo semantics chứ không chỉ theo kiểu dữ liệu.

## 14. Chọn giao tiếp phù hợp trong Spring Modulith

Một số câu hỏi giúp chọn đúng cơ chế:

| Nhu cầu | Cơ chế phù hợp thường gặp |
| --- | --- |
| Gọi logic trong cùng module và cần kết quả ngay | Method call/service nội bộ. |
| Gọi API module khác và cần kết quả ngay | Public API của module. |
| Yêu cầu module khác thực hiện một hành động có đích nhận rõ | Command/API hoặc workflow phù hợp. |
| Thông báo một fact đã xảy ra cho các module độc lập | Application event. |
| Xử lý sau commit và theo dõi publication | `@ApplicationModuleListener` cùng Event Publication Registry. |
| Đưa fact ra hệ thống ngoài | Event externalization, ví dụ `@Externalized` với adapter đã cấu hình. |
| Ghi log/trace thao tác kỹ thuật | Logging, metrics và tracing. |
| Lưu lịch sử audit có yêu cầu riêng | Audit model/store được thiết kế rõ. |

Không có một cơ chế duy nhất phù hợp cho mọi giao tiếp. Chọn dựa trên nhu cầu phản hồi, quyền sở hữu dữ liệu, transaction, delivery semantics và mức độ độc lập của consumer.

## 15. Cách refactor khi hệ thống đã có quá nhiều event

Không nên xóa hàng loạt event mà chưa kiểm kê consumer. Một event có thể đã trở thành contract ngoài ứng dụng hoặc được dùng trong replay.

Một quy trình refactor có kiểm soát:

1. Liệt kê event type, producer, listener, consumer bên ngoài và mục đích của từng event.
2. Phân loại event thành domain fact, integration event, command bị đặt nhầm tên, audit hoặc telemetry.
3. Xác định event trùng nghĩa, event không có consumer và event chỉ mô tả chi tiết triển khai.
4. Kiểm tra event nào đã được externalize, lưu lịch sử hoặc có publication pending.
5. Gộp hoặc thay event chỉ khi có contract thay thế rõ ràng và consumer đã được chuyển đổi.
6. Dùng compatibility window để hỗ trợ consumer cũ nếu wire contract thay đổi.
7. Ngừng phát event cũ sau khi đã xác nhận không còn consumer/replay cần nó.
8. Xóa code và schema cũ sau khi hết thời hạn tương thích và rollback.

Với event nội bộ chưa được sử dụng bên ngoài, refactor có thể đơn giản hơn nhưng vẫn cần kiểm tra listener và test. Với event đã phát ra broker, phải xem xét retention, retry topic, DLT và dữ liệu lịch sử trước khi ngừng hỗ trợ.

## 16. Ví dụ thiết kế cân bằng

Use case thay đổi địa chỉ giao hàng có thể được triển khai như sau:

```java
public record OrderShippingAddressChanged(
        UUID eventId,
        UUID orderId,
        AddressSnapshot newAddress,
        long aggregateVersion,
        Instant occurredAt) {
}

@Service
class OrderManagementImpl implements OrderManagement {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    @Transactional
    public void changeShippingAddress(UUID orderId, Address address) {
        Order order = orders.findById(orderId).orElseThrow();
        order.changeShippingAddress(address);
        orders.save(order);

        events.publishEvent(new OrderShippingAddressChanged(
                UUID.randomUUID(),
                order.getId(),
                AddressSnapshot.from(order.getShippingAddress()),
                order.getVersion(),
                Instant.now()));
    }
}

@Component
class ShippingAddressProjection {

    @ApplicationModuleListener
    void on(OrderShippingAddressChanged event) {
        // Cập nhật read model mà module này sở hữu.
    }
}
```

Đây là ví dụ minh họa. Chỉ phát `OrderShippingAddressChanged` nếu module khác thực sự cần phản ứng với thay đổi này. Nếu địa chỉ chỉ được sửa như một chi tiết nội bộ không có consumer độc lập, bỏ event và giữ thao tác trong module `orders`.

Khi phát event, payload chỉ chứa snapshot cần thiết, có event ID và aggregate version. Listener chạy sau commit theo semantics của `@ApplicationModuleListener`; consumer cần idempotency và xử lý version nếu có thể nhận duplicate hoặc event sai thứ tự.

## 17. Câu hỏi review trước khi thêm event

Trước khi thêm một event mới, reviewer có thể hỏi:

- Tên event đang mô tả fact nào đã xảy ra?
- Fact có ý nghĩa với domain hay chỉ là một bước kỹ thuật?
- Module nào sở hữu fact và contract?
- Consumer cần nhận thông tin này để làm gì?
- Consumer có thể xử lý độc lập sau commit không?
- Caller có thực sự cần kết quả đồng bộ không?
- Payload có đủ dữ liệu nhưng không lộ entity nội bộ không?
- Event có cần externalize hoặc lưu lịch sử không?
- Có quy tắc idempotency, ordering, retry và versioning phù hợp không?
- Nếu không phát event, một method call hoặc log có giải quyết đơn giản hơn không?

Nếu không thể trả lời rõ event biểu diễn fact nào hoặc consumer cần phản ứng gì, hãy xem lại thiết kế trước khi thêm contract mới.

## 18. Những sai lầm thường gặp

- Phát event cho mọi lần đọc/ghi repository.
- Tạo event cho từng field hoặc setter dù không có ý nghĩa nghiệp vụ độc lập.
- Dùng event để gọi một module và chờ kết quả ngay trong cùng request.
- Phát event cho trạng thái trung gian trước khi transaction commit.
- Đặt tên event theo class, table, method hoặc công nghệ vận chuyển.
- Dùng event làm log kỹ thuật hoặc audit mà không có yêu cầu contract tương ứng.
- Gộp nhiều command vào một event chung chung để giảm số type.
- Cho rằng một listener nghĩa là event không cần thiết hoặc nhiều listener nghĩa là event luôn đúng.
- Không tính đến duplicate, retry, ordering và schema compatibility.
- Xóa event đã externalize mà không kiểm tra consumer, retention và replay.

## Checklist tránh event cho mọi thao tác

- [ ] Event mô tả fact nghiệp vụ đã xảy ra, không mô tả method/repository call.
- [ ] Command, query và event được phân biệt rõ.
- [ ] Caller dùng method/API khi cần kết quả đồng bộ.
- [ ] Chỉ phát event khi có consumer hoặc giá trị domain rõ ràng.
- [ ] Event không phản ánh từng field/persistence detail không cần thiết.
- [ ] Event được phát ở ranh giới transaction phù hợp.
- [ ] Payload là contract ổn định, không chứa entity nội bộ.
- [ ] Consumer có idempotency và quy tắc version/order khi cần.
- [ ] Log, metric và trace được dùng cho mốc kỹ thuật thay vì phát event cho mọi bước.
- [ ] Event externalized có schema, compatibility và lifecycle được tài liệu hóa.
- [ ] Refactor event cũ có kiểm kê consumer, pending publication và dữ liệu lịch sử.

Application event tạo giá trị khi nó công bố một fact nghiệp vụ có ý nghĩa và cho phép consumer phản ứng độc lập. Giữ event ở đúng ranh giới đó giúp Spring Modulith duy trì module ít phụ thuộc, giảm số publication phải vận hành và làm cho contract dễ hiểu, dễ kiểm thử và dễ thay đổi hơn.
