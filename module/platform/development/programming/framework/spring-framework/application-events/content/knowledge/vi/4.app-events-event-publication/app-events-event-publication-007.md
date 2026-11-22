# Phát event sau khi hoàn tất thay đổi trạng thái

Khi một nghiệp vụ thay đổi trạng thái, event nên mô tả **một chuyển đổi trạng thái đã thực sự xảy ra**. Vì vậy, ứng dụng cần cập nhật trạng thái trước, xác định chuyển đổi có hợp lệ và có thay đổi hay không, rồi mới phát event tương ứng.

Trong Spring Framework, `ApplicationEventPublisher.publishEvent(...)` chuyển một object đến hệ thống listener trong ApplicationContext. Lời gọi này không tự hiểu transaction nghiệp vụ hoặc tự chờ database commit. Nếu trạng thái được lưu trong database bằng transaction, cần phân biệt thời điểm code thay đổi entity, thời điểm SQL được flush và thời điểm transaction commit. Khi listener phải chạy sau commit, dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` hoặc phát event từ một lớp điều phối sau khi lời gọi transaction đã hoàn tất.

## 1. Nguyên tắc: event phải phản ánh thay đổi đã xảy ra

Giả sử đơn hàng chuyển từ `PENDING` sang `PAID`. Một event phù hợp là `OrderStatusChanged`, chứa đơn hàng nào đã đổi, trạng thái trước đó và trạng thái mới.

Luồng xử lý hợp lý:

1. Đọc trạng thái hiện tại từ nguồn dữ liệu có thẩm quyền.
2. Kiểm tra chuyển đổi có hợp lệ theo quy tắc nghiệp vụ.
3. Nếu trạng thái mới giống trạng thái hiện tại, kết thúc mà không phát event.
4. Thực hiện thay đổi trạng thái.
5. Lưu thay đổi theo ranh giới transaction của nghiệp vụ.
6. Phát hoặc dispatch event tại thời điểm phù hợp với yêu cầu nhất quán.
7. Listener xử lý các tác vụ phụ như audit, cập nhật projection hoặc gửi thông báo.

Điểm cốt lõi là **không phát event “đã chuyển trạng thái” trước khi chuyển đổi thực sự được chấp nhận**. Nếu validation thất bại, entity không thay đổi hoặc transaction rollback, hệ thống không được để các listener hiểu nhầm rằng trạng thái mới đã có hiệu lực.

### Command và event có ý nghĩa khác nhau

- Command là yêu cầu thực hiện một hành động, ví dụ `ChangeOrderStatus`.
- Event là sự kiện đã xảy ra, ví dụ `OrderStatusChanged`.

Command có thể bị từ chối vì trạng thái hiện tại không cho phép chuyển đổi. Event chỉ nên được phát sau khi quy tắc nghiệp vụ đã chấp nhận và trạng thái đã được thay đổi theo mô hình dữ liệu.

Tên event thường dùng thì quá khứ hoặc diễn đạt kết quả: `OrderPaid`, `OrderStatusChanged`, `AccountSuspended`. Tên command diễn đạt ý định: `PayOrder`, `ChangeOrderStatus`, `SuspendAccount`.

## 2. “Đã đổi trạng thái” và “đã commit” không giống nhau

Với dữ liệu trong bộ nhớ, câu lệnh gán có thể làm trạng thái mới nhìn thấy ngay trong object. Với dữ liệu database, có nhiều mốc khác nhau:

| Mốc | Điều gì đã xảy ra? | Có thể khẳng định transaction đã thành công? |
|---|---|---|
| Thay đổi object/entity | Giá trị trong object Java đã đổi | Chưa |
| Gọi `repository.save(...)` | Spring Data đã nhận yêu cầu lưu; entity có thể được quản lý bởi persistence context | Chưa |
| SQL flush | SQL đã được gửi đến database trong transaction | Chưa |
| Transaction commit | Database xác nhận transaction hoàn tất theo transaction manager | Có, đối với transaction đó |
| Listener `AFTER_COMMIT` chạy | Listener được gọi sau khi transaction commit thành công | Transaction gốc đã commit |

Một lỗi thường gặp là nghĩ rằng `repository.save()` hoặc `saveAndFlush()` đồng nghĩa với commit. Trong một transaction đang hoạt động, flush chỉ đồng bộ thay đổi xuống database; transaction vẫn có thể rollback sau đó.

Ví dụ:

~~~java
@Transactional
public void markPaid(String orderId) {
    Order order = repository.findById(orderId).orElseThrow();
    order.markPaid();

    repository.saveAndFlush(order);
    publisher.publishEvent(new OrderStatusChanged(orderId, "PENDING", "PAID"));
    // Transaction vẫn chưa commit tại đây.
}
~~~

Đoạn code trên gọi `publishEvent` sau khi entity đổi và SQL có thể đã flush, nhưng listener `@EventListener` đồng bộ thông thường vẫn có thể chạy trước commit. Nếu sau đó transaction rollback, listener đã nhìn thấy một event mô tả trạng thái không được lưu bền vững.

Do đó, phải chọn thời điểm theo điều listener cần biết: chỉ cần biết object đã được đổi trong luồng hiện tại, hay phải chắc chắn database đã commit.

## 3. Phát event sau khi thay đổi trong bộ nhớ

Với một ứng dụng không dùng transaction database cho thao tác này, có thể cập nhật trạng thái trước rồi publish event ngay sau đó. Ví dụ sau dùng một store trong bộ nhớ để minh họa đúng thứ tự thao tác:

~~~java
package com.example.events;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@SpringBootApplication
public class StateChangeEventDemo {
    public static void main(String[] args) {
        SpringApplication.run(StateChangeEventDemo.class, args);
    }

    @Bean
    CommandLineRunner demo(OrderService service) {
        return args -> {
            service.register("O-100", "PENDING");
            service.changeStatus("O-100", "PAID");
            service.changeStatus("O-100", "PAID");
        };
    }
}

record OrderStatusChanged(
        String orderId,
        String previousStatus,
        String newStatus
) {}

@Service
class OrderService {
    private final Map<String, String> statuses = new ConcurrentHashMap<>();
    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void register(String orderId, String initialStatus) {
        statuses.put(orderId, initialStatus);
    }

    public synchronized void changeStatus(String orderId, String newStatus) {
        String previousStatus = statuses.get(orderId);

        if (previousStatus == null) {
            throw new IllegalArgumentException("Unknown order: " + orderId);
        }

        if (newStatus == null) {
            throw new IllegalArgumentException("newStatus must not be null");
        }

        if (previousStatus.equals(newStatus)) {
            System.out.println("Service: no state change for " + orderId);
            return;
        }

        // Hoàn tất thay đổi trạng thái trước khi publish.
        statuses.put(orderId, newStatus);

        publisher.publishEvent(new OrderStatusChanged(
                orderId,
                previousStatus,
                newStatus
        ));

        System.out.println(
                "Service: status is now " + statuses.get(orderId)
        );
    }
}

@Component
class OrderStatusListener {
    @EventListener
    public void onStatusChanged(OrderStatusChanged event) {
        System.out.println(
                "Listener: " + event.orderId()
                        + " " + event.previousStatus()
                        + " -> " + event.newStatus()
        );
    }
}
~~~

Output do ví dụ tạo ra:

~~~text
Listener: O-100 PENDING -> PAID
Service: status is now PAID
Service: no state change for O-100
~~~

Giải thích:

1. Service đăng ký đơn hàng ở trạng thái `PENDING`.
2. Lần chuyển sang `PAID` cập nhật map trước, rồi mới gọi `publishEvent`.
3. Listener nhận snapshot gồm trạng thái cũ và mới.
4. Vì multicaster đồng bộ mặc định, listener chạy xong trước dòng log tiếp theo của service.
5. Lần gọi thứ hai yêu cầu trạng thái `PAID` trong khi trạng thái hiện tại đã là `PAID`; service không phát event lần nữa.

Ví dụ này chạy độc lập với Java 17+ và dependency `spring-boot-starter`. Có thể chạy bằng Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Đây là ví dụ về thứ tự cập nhật object trong bộ nhớ. `ConcurrentHashMap` không cung cấp transaction database, lưu trữ bền vững hay cơ chế bảo vệ một chuyển đổi nhiều bước như aggregate thực tế. Phương thức `changeStatus` được đồng bộ hóa để việc đọc trạng thái, kiểm tra no-op và cập nhật trong ví dụ đơn giản này diễn ra tuần tự. Trong hệ thống có database, cần dùng transaction và cơ chế sau commit khi listener phụ thuộc trạng thái đã commit.

## 4. Dùng @TransactionalEventListener để listener chạy sau commit

Khi thay đổi trạng thái được lưu trong database, cách phổ biến là publish event trong transaction sau khi aggregate đã thay đổi, rồi dùng `@TransactionalEventListener` để trì hoãn listener đến phase phù hợp.

Đoạn code dưới đây là fragment, giả định dự án đã có entity `Order`, `OrderRepository`, enum `OrderStatus`, transaction manager và record `OrderStatusChanged` dạng đơn giản ở ví dụ trước. Các kiểu domain này được lược bỏ để tập trung vào ranh giới transaction:

~~~java
@Service
class OrderService {
    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    OrderService(
            OrderRepository repository,
            ApplicationEventPublisher publisher
    ) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public void changeStatus(String orderId, OrderStatus newStatus) {
        Order order = repository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown order: " + orderId
                ));

        OrderStatus previousStatus = order.getStatus();

        if (previousStatus == newStatus) {
            return;
        }

        order.changeStatus(newStatus);
        repository.save(order);

        publisher.publishEvent(new OrderStatusChanged(
                orderId,
                previousStatus.name(),
                newStatus.name()
        ));
    }
}
~~~

Listener chỉ chạy sau khi transaction commit:

~~~java
@Component
class OrderStatusListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderStatusChanged event) {
        System.out.println(
                "Committed status change: " + event.orderId()
                        + " -> " + event.newStatus()
        );
    }
}
~~~

Cách hoạt động:

1. Spring mở transaction cho lời gọi `changeStatus` thông qua transaction proxy.
2. Service đọc trạng thái, kiểm tra quy tắc và cập nhật aggregate.
3. Service publish event trong khi transaction đang hoạt động.
4. Spring ghi nhận event cho transactional listener.
5. Khi transaction commit thành công, listener ở phase `AFTER_COMMIT` được gọi.
6. Nếu transaction rollback, listener `AFTER_COMMIT` không chạy.

Tên annotation có chữ “EventListener”, nhưng ở đây publisher vẫn gọi `publishEvent` trong transaction. Điều được trì hoãn là **việc thực thi listener** đến sau commit. Cách này giúp listener chỉ xử lý event khi thay đổi trạng thái đã commit thành công.

Các phase có thể dùng:

| Phase | Thời điểm listener chạy |
|---|---|
| `BEFORE_COMMIT` | Trước khi transaction commit |
| `AFTER_COMMIT` | Sau khi transaction commit thành công; đây là mặc định |
| `AFTER_ROLLBACK` | Sau khi transaction rollback |
| `AFTER_COMPLETION` | Sau khi transaction hoàn tất, dù commit hay rollback |

Nếu event được phát khi không có transaction đang hoạt động, transactional listener mặc định không chạy. Có thể bật `fallbackExecution = true`, nhưng chỉ nên dùng khi việc chạy listener ngoài transaction là đúng với nghiệp vụ:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true
)
public void afterCommitOrWithoutTransaction(OrderStatusChanged event) {
    // Chỉ dùng fallback nếu chấp nhận cả trường hợp không có transaction.
}
~~~

Không bật fallback chỉ để “listener lúc nào cũng chạy” nếu nghiệp vụ đòi hỏi trạng thái database đã commit. Khi không có transaction, không tồn tại mốc commit để xác nhận.

## 5. Phân biệt phát event sau transaction và listener sau commit

Có hai cách tổ chức có thể đều bảo đảm listener thường được gọi sau khi transaction gốc hoàn tất, nhưng ranh giới code khác nhau.

### Cách A: Publish trong transaction, listener dùng AFTER_COMMIT

~~~java
@Transactional
public void changeStatus(String orderId, OrderStatus newStatus) {
    // Đọc, validate, thay đổi và lưu trạng thái.
    publisher.publishEvent(event);
}
~~~

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void handle(OrderStatusChanged event) {
    // Chỉ chạy sau commit.
}
~~~

Ưu điểm là event được gắn với transaction đang thực hiện thay đổi. Spring chỉ gọi listener ở phase đã chọn khi transaction hoàn tất tương ứng. Đây thường là cách rõ ràng khi event là kết quả của một thao tác transaction.

### Cách B: Publish sau khi phương thức transaction đã trả về

Có thể tách phần ghi trạng thái và phần phát event thành hai bean/lớp:

~~~java
import java.util.Optional;

@Service
class OrderStatusCommand {
    private final OrderRepository repository;

    OrderStatusCommand(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Optional<OrderStatusChanged> changeStatus(
            String orderId,
            OrderStatus newStatus
    ) {
        Order order = repository.findById(orderId).orElseThrow();
        OrderStatus previous = order.getStatus();

        if (previous == newStatus) {
            return Optional.empty();
        }

        order.changeStatus(newStatus);
        repository.save(order);

        return Optional.of(new OrderStatusChanged(
                orderId, previous.name(), newStatus.name()
        ));
    }
}

@Service
class OrderStatusApplicationService {
    private final OrderStatusCommand command;
    private final ApplicationEventPublisher publisher;

    OrderStatusApplicationService(
            OrderStatusCommand command,
            ApplicationEventPublisher publisher
    ) {
        this.command = command;
        this.publisher = publisher;
    }

    public void changeStatus(String orderId, OrderStatus newStatus) {
        Optional<OrderStatusChanged> event = command.changeStatus(orderId, newStatus);

        // Lời gọi qua Spring proxy đã trả về sau khi transaction commit.
        event.ifPresent(publisher::publishEvent);
    }
}
~~~

Ở cách này, `OrderStatusApplicationService` gọi một bean khác có phương thức `@Transactional`. Khi lời gọi qua proxy trả về bình thường và không tham gia một transaction bên ngoài dài hơn, transaction do phương thức đó quản lý đã kết thúc; sau đó lớp điều phối mới publish event.

Cần giữ hai class ở các bean riêng để lời gọi đi qua Spring proxy. Nếu một method trong cùng object gọi trực tiếp method `@Transactional` khác (self-invocation), transaction proxy có thể không được áp dụng như mong đợi.

Cách B dễ đọc khi muốn thể hiện rõ ranh giới “ghi xong rồi mới publish” ở tầng điều phối. Tuy nhiên, vẫn tồn tại khoảng thời gian giữa database commit và lời gọi publish. Nếu tiến trình dừng trong khoảng đó, trạng thái đã commit nhưng event có thể chưa được phát. Vì vậy cách này không tự tạo bảo đảm giao nhận bền vững.

## 6. Chỉ phát event khi trạng thái thực sự thay đổi

Một event trạng thái nên đại diện cho một lần chuyển đổi có ý nghĩa. Nếu yêu cầu đặt trạng thái mới bằng trạng thái hiện tại, thông thường không nên phát lại cùng event.

Ví dụ:

~~~java
OrderStatus previous = order.getStatus();

if (previous == requestedStatus) {
    return;
}

order.changeStatus(requestedStatus);
publisher.publishEvent(new OrderStatusChanged(
        order.getId(),
        previous,
        requestedStatus
));
~~~

Kiểm tra no-op giúp tránh:

- Gửi email hoặc thông báo lặp.
- Tạo nhiều bản ghi audit giống nhau.
- Cập nhật projection không cần thiết.
- Kích hoạt các listener downstream nhiều lần.
- Tạo event chain không có chuyển đổi nghiệp vụ mới.

Không phải mọi nghiệp vụ đều coi trạng thái giống nhau là no-op. Một số hệ thống có lệnh “xác nhận lại” hoặc cần ghi nhận một hành động lặp như một sự kiện riêng. Khi đó, event phải biểu diễn đúng hành động đó, chẳng hạn `PaymentConfirmationRequestedAgain`, thay vì giả vờ rằng trạng thái đã chuyển đổi lần nữa.

## 7. Payload event nên chứa gì?

Event được xử lý sau thời điểm thay đổi trạng thái nên mang dữ liệu đủ để listener hiểu chính xác chuyển đổi đã xảy ra.

Một payload thường gồm:

| Trường | Mục đích |
|---|---|
| `eventId` | Định danh duy nhất, hỗ trợ idempotency và truy vết |
| `aggregateId` | Định danh entity/aggregate đã thay đổi |
| `previousStatus` | Trạng thái trước chuyển đổi |
| `newStatus` | Trạng thái sau chuyển đổi |
| `aggregateVersion` | Phiên bản aggregate sau khi thay đổi |
| `occurredAt` | Thời điểm nghiệp vụ xảy ra |
| `actorId` | Người hoặc hệ thống tạo chuyển đổi, nếu phù hợp |
| `correlationId` | Liên kết event với request/workflow lớn hơn |

Ưu tiên payload bất biến như Java record. Đoạn dưới đây là một phiên bản giàu metadata thay thế record `OrderStatusChanged` đơn giản đã dùng ở các ví dụ trước; trong code thật chỉ khai báo một record với cấu trúc được chọn, không khai báo đồng thời hai record cùng tên:

~~~java
import java.time.Instant;
import java.util.UUID;

record OrderStatusChanged(
        UUID eventId,
        String orderId,
        String previousStatus,
        String newStatus,
        long aggregateVersion,
        Instant occurredAt
) {}
~~~

Không nên đưa trực tiếp JPA entity vào event. Entity có thể tiếp tục bị sửa, chứa quan hệ lazy, phụ thuộc persistence context hoặc làm listener đọc một trạng thái khác với snapshot tại thời điểm chuyển đổi.

Nếu listener cần trạng thái chính xác tại thời điểm event xảy ra, hãy truyền snapshot cần thiết. Nếu listener cần trạng thái hiện tại nhất, hãy truyền định danh và đọc lại từ nguồn dữ liệu có thẩm quyền. Hai cách có ý nghĩa khác nhau khi có nhiều chuyển đổi liên tiếp.

## 8. Nhiều thay đổi trạng thái và thứ tự event

Một aggregate có thể chuyển trạng thái nhiều lần:

~~~text
PENDING → CONFIRMED → SHIPPED → DELIVERED
~~~

Mỗi lần chuyển đổi thành công tạo một event riêng:

~~~text
OrderConfirmed
OrderShipped
OrderDelivered
~~~

Nếu event được phát đồng bộ trong một tiến trình, listener thường nhận theo thứ tự dispatch của luồng đó. Nhưng khi dùng async executor, nhiều thread hoặc broker, thứ tự hoàn tất có thể khác thứ tự phát.

Ví dụ listener xử lý `OrderConfirmed` mất 500 ms, còn listener xử lý `OrderShipped` chỉ mất 50 ms. Hai listener async có thể hoàn tất ngược thứ tự. Nếu thứ tự có ý nghĩa nghiệp vụ, hãy:

- Gắn `aggregateVersion` hoặc sequence number vào event.
- Kiểm tra version trước khi áp dụng projection.
- Phân vùng/partition theo aggregate key nếu dùng broker hỗ trợ ordering theo partition.
- Không giả định `@Order` điều khiển thứ tự giữa các task chạy async.
- Xử lý event đến muộn hoặc trùng theo chính sách rõ ràng.

Nếu consumer nhận version 8 trước version 7, consumer có thể từ chối, lưu chờ hoặc đọc lại trạng thái mới nhất tùy yêu cầu. Không nên áp dụng mù mọi event đến mà không kiểm tra thứ tự nếu projection phụ thuộc chuyển đổi tuần tự.

## 9. Listener sau commit có thể lỗi; database không tự rollback

`AFTER_COMMIT` bảo đảm thời điểm gọi listener sau khi transaction gốc commit thành công. Nó không biến phần xử lý listener thành một phần có thể rollback cùng transaction gốc.

Ví dụ:

1. Đơn hàng chuyển sang `PAID` và database commit.
2. Listener sau commit gọi dịch vụ gửi email.
3. Dịch vụ email timeout hoặc listener ném exception.

Trạng thái đơn hàng vẫn đã commit. Việc gửi email thất bại không thể làm database quay lại trạng thái `PENDING` bằng cách rollback transaction đã kết thúc.

Vì vậy, listener sau commit nên có:

- Logging đủ event ID, aggregate ID và trạng thái chuyển đổi.
- Retry có giới hạn nếu tác vụ có thể thử lại an toàn.
- Idempotency để không gửi thông báo hoặc tạo tác động lặp.
- Theo dõi lỗi cuối cùng và cơ chế xử lý thủ công nếu nghiệp vụ yêu cầu.
- Transaction mới nếu listener cần ghi thêm dữ liệu database sau commit.

Đối với công việc phụ có thể bỏ qua, ghi log và chấp nhận mất có thể đủ. Với công việc quan trọng, cần cơ chế lưu trữ bền vững thay vì chỉ dựa vào listener trong bộ nhớ.

## 10. Khi cần bảo đảm không mất event: Transactional Outbox

Có một khoảng trống cố hữu khi ghi database rồi publish event riêng:

~~~text
Database COMMIT thành công
        |
        | tiến trình có thể dừng ở đây
        v
publishEvent / gửi message
~~~

Nếu ứng dụng dừng sau commit nhưng trước publish, trạng thái đã thay đổi mà listener hoặc dịch vụ downstream không nhận được event.

Transactional Outbox giải quyết bằng cách lưu ý định phát event trong cùng transaction với thay đổi nghiệp vụ:

1. Cập nhật trạng thái đơn hàng.
2. Ghi một bản ghi outbox chứa event ID, aggregate ID, loại event, payload và thời điểm tạo.
3. Commit cả thay đổi trạng thái và bản ghi outbox trong cùng transaction.
4. Một relay đọc các bản ghi outbox chưa gửi và publish sang broker.
5. Relay đánh dấu đã gửi sau khi nhận xác nhận theo chính sách đã chọn.

Nếu transaction rollback, cả trạng thái và bản ghi outbox đều rollback. Nếu transaction commit, bản ghi outbox tồn tại để relay tiếp tục gửi kể cả khi tiến trình ứng dụng khởi động lại.

Relay có thể gửi lặp nếu broker đã nhận message nhưng ứng dụng chưa kịp ghi nhận trạng thái đã gửi. Vì vậy, consumer vẫn cần idempotent, thường dựa trên `eventId`.

Có thể dùng Spring Application Event để đánh thức relay sau commit, nhưng bản ghi outbox mới là nguồn dữ liệu bền vững. Không nên dùng event trong bộ nhớ làm bản sao duy nhất của outbox.

## 11. Những hiểu nhầm thường gặp

- **Gọi `save()` nghĩa là đã commit.** Sai. Trong transaction, commit xảy ra khi transaction manager hoàn tất; save/flush chưa đủ.
- **Đổi field rồi publish ở bất kỳ vị trí nào cũng đúng.** Sai. Listener có thể chạy trước khi validation hoặc transaction hoàn tất.
- **Dùng `@TransactionalEventListener(AFTER_COMMIT)` nghĩa là event được lưu bền vững.** Sai. Nó trì hoãn listener đến sau commit, nhưng không lưu event để replay sau crash.
- **Transaction rollback thì mọi tác động listener tự rollback.** Sai. Tác động ngoài database hoặc listener đã chạy trước commit không tự được hoàn tác.
- **Phát event mỗi lần nhận cùng trạng thái mới.** Thường tạo thông báo và tác động lặp; hãy xác định rõ no-op hay một hành động lặp có ý nghĩa.
- **Listener async luôn hoàn tất theo thứ tự publish.** Sai. Executor có thể xử lý và hoàn tất các task theo thứ tự khác.
- **Listener sau commit lỗi thì database tự quay lại.** Sai. Transaction gốc đã commit.
- **Chỉ cần publish sau khi phương thức transaction trả về là không thể mất event.** Sai. Tiến trình vẫn có thể dừng giữa commit và publish; cần outbox khi yêu cầu độ bền cao.

## 12. Checklist trước khi phát event

- [ ] Đã đọc trạng thái hiện tại từ nguồn dữ liệu có thẩm quyền?
- [ ] Chuyển đổi mới đã qua validation nghiệp vụ?
- [ ] Trạng thái đã được cập nhật trước khi tạo event?
- [ ] Có xử lý trường hợp trạng thái mới giống trạng thái hiện tại?
- [ ] Đã phân biệt thay đổi object, flush và commit?
- [ ] Listener cần chạy ngay sau mutation hay chỉ sau transaction commit?
- [ ] Nếu dùng `@TransactionalEventListener`, event được publish trong transaction phù hợp?
- [ ] Có hiểu hành vi khi không có transaction và `fallbackExecution`?
- [ ] Payload có trạng thái cũ/mới, ID/version và dữ liệu snapshot cần thiết?
- [ ] Listener async có kiểm soát thứ tự, lỗi và idempotency?
- [ ] Nếu listener thất bại sau commit, có cách retry hoặc xử lý lỗi?
- [ ] Nếu không được phép mất event, đã dùng outbox hoặc cơ chế lưu trữ bền vững?

Spring Application Events phù hợp để thông báo cho các thành phần trong cùng ứng dụng sau một chuyển đổi trạng thái. Hãy tạo event sau khi nghiệp vụ chấp nhận thay đổi, chọn thời điểm listener theo ranh giới commit, và dùng payload bất biến thể hiện rõ trạng thái trước/sau. Khi cần bảo đảm event không bị mất giữa database commit và dispatch, hãy lưu event cùng transaction bằng Transactional Outbox.
