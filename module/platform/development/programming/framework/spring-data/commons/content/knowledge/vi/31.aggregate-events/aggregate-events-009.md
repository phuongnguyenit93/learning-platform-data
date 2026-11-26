# @TransactionalEventListener và thời điểm sau commit

Một sự kiện `OrderConfirmed` có thể được công bố khi application service vẫn đang thực hiện giao dịch. Nếu listener gửi email ngay tại thời điểm đó, khách hàng có thể nhận được thư xác nhận trong khi giao dịch sau đó rollback.

`@TransactionalEventListener` cho phép gắn việc xử lý sự kiện với một giai đoạn của giao dịch. Với `AFTER_COMMIT`, listener chỉ được xử lý sau khi giao dịch mà nó tham gia đã commit thành công. Đây là một công cụ điều khiển **thời điểm thực thi**, không phải một hàng đợi thông điệp bền vững.

Bài học thuộc chương **Sự kiện aggregate**, module **SPRING_DATA_COMMONS**. Nội dung kết nối các sự kiện từ aggregate root với repository, CRUD và hạ tầng giao dịch của Spring; đồng thời chỉ rõ những bảo đảm phụ thuộc store, transaction manager và cách ứng dụng điều phối use case.

## 1. Tại sao công bố sự kiện chưa đủ?

Xét một use case xác nhận đơn hàng:

```text
Bắt đầu transaction
    Nạp đơn hàng
    order.confirm(...)
    repository.save(order)
    Công bố OrderConfirmed
    Thực hiện thêm một thao tác ghi
    Thao tác ghi thất bại
Rollback
```

Nếu một `@EventListener` thông thường gửi email ngay khi sự kiện được công bố, email có thể đã ra khỏi hệ thống trước khi thao tác ghi cuối thất bại.

Có ba mốc khác nhau:

| Mốc | Điều đã xảy ra | Điều chưa thể suy ra |
| --- | --- | --- |
| Aggregate ghi nhận sự kiện | Mô hình đã chấp nhận một chuyển đổi trong bộ nhớ | Dữ liệu đã commit |
| Sự kiện được công bố | Hạ tầng sự kiện đã tiếp nhận lời gọi publication | Giao dịch sẽ thành công |
| Giao dịch commit thành công | Thay đổi được commit theo hợp đồng của tài nguyên giao dịch | Hệ thống bên ngoài đã nhận thông báo |

Listener sau commit phù hợp khi phản ứng chỉ có ý nghĩa nếu dữ liệu đã được commit. Nó không sửa được một mô hình miền sai, không thay invariant của aggregate và không thêm transaction cho một store chưa có cấu hình hỗ trợ.

### 1.1. Sự kiện miền vẫn được tạo ở hành vi nghiệp vụ

Aggregate có thể làm như sau:

```java
public void confirm(Instant now) {
    checkConfirmationRules();
    status = Status.CONFIRMED;
    registerEvent(new OrderConfirmed(
            UUID.randomUUID(), id, now
    ));
}
```

Đây là đoạn mã minh họa trong một root kế thừa `AbstractAggregateRoot`; `checkConfirmationRules`, `status` và `id` thuộc mô hình ứng dụng.

Việc chọn `AFTER_COMMIT` là quyết định của phía xử lý. Không cần chuyển toàn bộ hành vi `confirm` vào listener sau commit. Quy tắc xác nhận và chuyển trạng thái vẫn phải diễn ra trong đường thực hiện nghiệp vụ trước khi lưu.

## 2. Spring Data Commons nối với Spring transaction như thế nào?

Hai nhóm API giữ trách nhiệm riêng:

| API | Thuộc về | Vai trò |
| --- | --- | --- |
| `@DomainEvents` | Spring Data Commons | Cung cấp các sự kiện của aggregate |
| `@AfterDomainEventPublication` | Spring Data Commons | Dọn sự kiện sau publication |
| `AbstractAggregateRoot` | Spring Data Commons | Hỗ trợ ghi nhận và quản lý sự kiện tạm |
| `ApplicationEventPublisher` | Spring Framework | Công bố sự kiện ứng dụng |
| `@EventListener` | Spring Framework | Đăng ký listener ứng dụng thông thường |
| `@TransactionalEventListener` | Spring Framework | Đăng ký xử lý theo giai đoạn giao dịch |

`@TransactionalEventListener` không phải một annotation chỉ dành cho Spring Data. Nó cũng có thể tiếp nhận sự kiện được công bố trực tiếp qua `ApplicationEventPublisher`.

Với aggregate events, một luồng điển hình là:

```text
Hành vi trên aggregate
        |
        v
Danh sách sự kiện chờ công bố
        |
        v
Lời gọi repository được hỗ trợ, đi qua proxy Spring Data
        |
        v
ApplicationEventPublisher
        |
        v
Đăng ký xử lý với transaction đang hiện hành
        |
        v
Xử lý ở phase đã chọn
```

Danh sách sự kiện trong aggregate và phần đăng ký callback của giao dịch đều là trạng thái trong bộ nhớ. Không bên nào tự trở thành log sự kiện bền vững.

### 2.1. Publication và dọn danh sách có thể xảy ra trước commit

Sau khi công bố các sự kiện, Spring Data có thể gọi phương thức được đánh dấu `@AfterDomainEventPublication` để dọn danh sách trong aggregate. Trong khi đó, listener giao dịch đã đăng ký chờ giao dịch hoàn tất.

Vì vậy:

- Danh sách đã rỗng không có nghĩa giao dịch đã commit.
- Dọn danh sách không hủy callback đã được đăng ký cho sự kiện.
- Rollback có thể khiến listener `AFTER_COMMIT` không chạy, dù callback dọn sự kiện đã chạy.
- Không dùng danh sách chờ trong aggregate như một cơ chế retry sau khi tiến trình dừng.

### 2.2. Repository không tự quyết định phase của listener

Repository có thể tạo ra điểm publication, nhưng listener chọn phase thông qua annotation của nó. Một sự kiện có thể được nhiều listener tiếp nhận với các phase khác nhau.

Nếu cần một transaction bao quanh cả thay đổi nghiệp vụ và publication, application service nên thiết lập ranh giới rõ ràng. Không mặc định rằng transaction riêng của một phương thức repository luôn bao trùm mọi interceptor hoặc mọi đoạn mã công bố sự kiện trong ứng dụng.

## 3. Các phase của @TransactionalEventListener

Annotation thuộc package:

```java
org.springframework.transaction.event.TransactionalEventListener
```

Các phase được khai báo bằng `TransactionPhase`:

| Phase | Thời điểm xử lý | Cách hiểu thực tế |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi giao dịch commit | Vẫn có thể ảnh hưởng việc commit nếu xử lý thất bại theo quy tắc giao dịch |
| `AFTER_COMMIT` | Sau khi commit thành công | Không chạy cho một giao dịch đã rollback |
| `AFTER_ROLLBACK` | Sau khi rollback | Quan sát hoặc xử lý tình huống giao dịch thất bại |
| `AFTER_COMPLETION` | Sau khi hoàn tất, gồm commit và rollback | Không tự phân biệt thành công chỉ từ việc listener đã được gọi |

`AFTER_COMMIT` là phase mặc định của `@TransactionalEventListener`. Viết phase tường minh thường giúp người đọc hiểu ngay ý định:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
```

### 3.1. BEFORE_COMMIT vẫn chưa phải thành công bền vững

Một listener `BEFORE_COMMIT` có thể chạy thành công nhưng bước commit sau đó vẫn lỗi, chẳng hạn do xung đột hoặc lỗi tài nguyên.

Do đó, không gửi một tác động ngoài không thể thu hồi rồi coi việc listener trước commit hoàn tất là bằng chứng giao dịch chắc chắn thành công.

Nếu listener ghi thêm dữ liệu cần nguyên tử với dữ liệu chính, nó phải thực sự tham gia transaction hiện tại và dùng tài nguyên có thể tham gia transaction đó. Phase trước commit không tự tạo tính nguyên tử giữa nhiều cơ sở dữ liệu.

### 3.2. AFTER_COMMIT không có nghĩa sau khi trả HTTP response

Trong luồng imperative thông dụng, listener giao dịch không có `@Async` chạy trên luồng đang hoàn tất transaction. Service proxy có thể còn đang hoàn tất lời gọi trong lúc listener sau commit được xử lý.

Vì vậy, listener chậm có thể kéo dài thời gian phản hồi của request. Những mốc sau không đồng nhất:

```text
Database commit thành công
Listener sau commit được xử lý
Lời gọi service trả về
HTTP response được gửi xong
```

`AFTER_COMMIT` chỉ ràng buộc với mốc giao dịch. Nó không cam kết HTTP response đã được gửi hoặc người dùng đã nhìn thấy kết quả.

### 3.3. Chi tiết callback cần phân biệt

Trong cơ chế transaction synchronization của Spring, listener phase `AFTER_COMMIT` được thực hiện theo chuỗi xử lý sau khi giao dịch hoàn tất thành công. Không nên đồng nhất nó với việc tự viết một callback `TransactionSynchronization.afterCommit()` và suy ra mọi chi tiết xử lý exception giống hệt nhau.

Ở mức thiết kế ứng dụng, kết luận quan trọng là: khi listener này chạy, commit của giao dịch nguồn đã thành công; một lỗi mới không thể rollback giao dịch đã commit.

## 4. Ví dụ listener tối thiểu

Một sự kiện bất biến có thể được khai báo:

```java
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {
}
```

`occurredAt` là thời điểm nghiệp vụ được ghi nhận, không tự trở thành thời điểm commit.

Listener:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderAfterCommitListener {

    private static final Logger log =
            LoggerFactory.getLogger(OrderAfterCommitListener.class);

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderConfirmed event) {
        log.info("Committed order: orderId={}, eventId={}",
                event.orderId(), event.eventId());
    }
}
```

Điều kiện cần:

1. Listener là bean được Spring quản lý và được hạ tầng event listener phát hiện.
2. Sự kiện được công bố qua hạ tầng Spring phù hợp.
3. Tại lúc publication, có một transaction phù hợp để đăng ký callback, trừ khi đã chủ động bật fallback.
4. Transaction đó commit thành công.

Log trong ví dụ chỉ giúp quan sát thời điểm. Nó không phải bằng chứng rằng một email hoặc thông điệp tích hợp đã được giao nhận bền vững.

## 5. Ranh giới giao dịch và trường hợp không có transaction

### 5.1. Đặt transaction ở application service

Với mô hình `PurchaseOrder` có hành vi `confirm` và khả năng ghi nhận aggregate events, service có thể điều phối như sau:

```java
import java.time.Clock;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ConfirmOrderService {

    private final PurchaseOrderRepository orders;
    private final Clock clock;

    public ConfirmOrderService(PurchaseOrderRepository orders, Clock clock) {
        this.orders = orders;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId
                ));

        order.confirm(clock.instant());
        orders.save(order);
    }
}
```

`PurchaseOrderRepository` là repository của mô hình, còn mapping `PurchaseOrder`, bean `Clock` và transaction manager cần được cấu hình cho store của dự án. Ví dụ tập trung vào ranh giới điều phối, không khai báo lại toàn bộ entity.

Với đường repository hỗ trợ aggregate events, publication xảy ra trong phạm vi use case này. Nếu tự công bố một sự kiện bằng `ApplicationEventPublisher`, cũng cần đặt lời gọi trong transaction mà listener phải gắn vào.

Không vừa để Spring Data công bố sự kiện của aggregate, vừa tự `publishEvent` cùng sự kiện trong service mà không có lý do rõ ràng. Hai lời gọi publication có thể tạo hai lần xử lý.

### 5.2. Annotation chỉ có tác dụng khi lời gọi đi qua hạ tầng đúng

Trong chế độ proxy giao dịch thông dụng, một phương thức có `@Transactional` chưa đủ nếu nó được gọi trực tiếp từ một phương thức khác của cùng instance theo cách bỏ qua proxy.

Ví dụ cần xem lại:

```java
public void process(UUID orderId) {
    this.confirm(orderId);
}

@Transactional
public void confirm(UUID orderId) {
    // Mong đợi transaction được mở, nhưng self-invocation có thể bỏ qua proxy.
}
```

Nếu không có transaction khác bao quanh, listener có thể không đăng ký được phase và bị bỏ qua theo cấu hình mặc định.

Cũng cần kiểm tra khi service được tự tạo bằng `new`, transaction manager không đúng hoặc publication nằm sau khi lời gọi transactional service đã trả về. Annotation trên một phương thức không kéo dài transaction sang các đoạn mã chạy sau lời gọi đó.

### 5.3. `fallbackExecution` không tạo một commit giả

Mặc định, khi không có transaction phù hợp, `@TransactionalEventListener` không thực thi listener.

Có thể chủ động khai báo:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true
)
public void on(OrderConfirmed event) {
    // Khi không có transaction, đây là xử lý fallback tại publication.
}
```

Với `fallbackExecution = true`, nếu không có transaction để đăng ký, listener có thể chạy ngay theo đường fallback. Khi đó không có commit nào để chờ.

| Transaction tại publication | Fallback | Hành vi đối với listener AFTER_COMMIT |
| --- | --- | --- |
| Có transaction phù hợp, sau đó commit | `false` hoặc `true` | Xử lý sau commit |
| Có transaction phù hợp, sau đó rollback | `false` hoặc `true` | Không xử lý ở phase AFTER_COMMIT |
| Không có transaction phù hợp | `false` | Bỏ qua listener |
| Không có transaction phù hợp | `true` | Xử lý fallback, không có bảo đảm sau commit |

Không bật fallback chỉ để làm listener xuất hiện trở lại mà chưa tìm nguyên nhân transaction bị thiếu. Nếu hành vi nghiệp vụ bắt buộc chỉ được chạy sau commit, fallback có thể làm thay đổi chính hợp đồng cần giữ.

### 5.4. Listener gắn với transaction nào?

Trong mô hình imperative, việc đăng ký gắn với transaction hiện hành tại thời điểm publication, không dựa vào tên entity hoặc nội dung sự kiện.

| Cách điều phối | Ý nghĩa cần hiểu |
| --- | --- |
| `REQUIRED` tham gia transaction ngoài | Listener chờ kết quả transaction vật lý đang tham gia |
| Một service `REQUIRES_NEW` công bố sự kiện | Listener gắn với transaction mới đó |
| Transaction ngoài rollback sau khi transaction mới đã commit | Không hoàn tác được commit và phản ứng sau commit của transaction mới |
| `NESTED` dùng savepoint khi được hỗ trợ | Không mặc định việc kết thúc một scope nested là một commit vật lý độc lập |

Nếu cần phân biệt nhiều ranh giới transaction, phải thể hiện chúng trong thiết kế service. Không suy ra rằng mọi listener có cùng tên phase sẽ đợi cùng một commit toàn cục.

## 6. Ghi dữ liệu từ listener sau commit

### 6.1. Tại sao chỉ gọi repository có thể gây hiểu nhầm?

Sau commit, một số tài nguyên của transaction có thể còn được gắn với luồng trong giai đoạn callback và dọn dẹp. Việc vẫn đọc được dữ liệu hoặc vẫn nhìn thấy persistence context không chứng minh transaction cũ còn có thể commit thêm lần nữa.

Vì vậy, nếu listener `AFTER_COMMIT` cần ghi dữ liệu mới, không dựa vào một transaction mặc định `REQUIRED` rồi giả định lệnh ghi sẽ trở thành một phần của giao dịch vừa hoàn tất.

Với một tác vụ ghi độc lập sau commit, một lựa chọn thường dùng là gọi một bean khác có phương thức `@Transactional(propagation = REQUIRES_NEW)`.

### 6.2. Ví dụ JDBC với một transaction mới

Giả sử dự án dùng JDBC và có bảng quan sát xác nhận:

```sql
create table order_confirmation_audit (
    event_id varchar(36) primary key,
    order_id varchar(36) not null
);
```

Bảng này chỉ minh họa một tác vụ ghi bổ sung độc lập. Nếu bản ghi audit là yêu cầu bắt buộc phải nguyên tử với thay đổi đơn hàng, hãy đưa nó vào transaction chính hoặc một thiết kế lưu bền vững thích hợp ngay từ đầu.

Writer:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ConfirmationAuditWriter {

    private final JdbcTemplate jdbc;

    public ConfirmationAuditWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(OrderConfirmed event) {
        jdbc.update("""
                insert into order_confirmation_audit(event_id, order_id)
                values (?, ?)
                """,
                event.eventId().toString(),
                event.orderId().toString());
    }
}
```

Thay listener quan sát ở mục 4 bằng một listener gọi writer:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderAfterCommitListener {

    private final ConfirmationAuditWriter writer;

    public OrderAfterCommitListener(ConfirmationAuditWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderConfirmed event) {
        writer.record(event);
    }
}
```

Ví dụ giả định `JdbcTemplate` và transaction manager cùng quản lý đúng `DataSource`; đây là lựa chọn riêng cho JDBC. Nếu dự án có nhiều transaction manager, cần chọn manager phù hợp trong annotation thay vì dựa vào một mặc định không rõ ràng.

Điểm quan trọng là lời gọi `writer.record` đi qua một bean/proxy khác. Đặt `REQUIRES_NEW` trên một phương thức rồi gọi bằng `this.record(...)` có thể không tạo transaction mới trong chế độ proxy.

### 6.3. Hai transaction có hai kết quả độc lập

```text
T1: lưu đơn hàng ----- commit thành công
                              |
                              v
T2: ghi audit mới ---- commit hoặc rollback riêng
```

Nếu T2 thất bại, đơn hàng đã commit trong T1 vẫn tồn tại. Đây là kết quả của thiết kế hai transaction, không phải một lỗi rollback cần sửa bằng cách ném exception mạnh hơn.

Khóa chính `event_id` ngăn tạo hai hàng có cùng ID, nhưng ví dụ chưa triển khai đầy đủ chính sách xử lý bản trùng. Nếu gửi lại cùng sự kiện, câu lệnh insert có thể lỗi do ràng buộc. Muốn coi bản trùng là đã xử lý, phải thiết kế thao tác ghi và cách xử lý xung đột đúng theo store; không chỉ bắt exception rồi tiếp tục một transaction đã bị đánh dấu lỗi.

Khi mở transaction mới trong lúc tài nguyên transaction ngoài chưa được dọn hết, ứng dụng có thể cần thêm connection. Cần tính đến connection pool và tải đồng thời khi chọn mô hình này.

## 7. Lỗi, latency và bất đồng bộ

### 7.1. Lỗi sau commit không đảo ngược dữ liệu đã commit

Xét thứ tự:

```text
Commit đơn hàng thành công
Gọi listener AFTER_COMMIT
Dịch vụ gửi thông báo lỗi
```

Kết quả là đơn hàng đã được xác nhận bền vững nhưng phản ứng bổ sung chưa hoàn tất.

Không mô tả tình huống này là toàn bộ use case đã rollback. Cũng không mặc định mọi exception từ listener sau commit sẽ được truyền nguyên vẹn về HTTP caller. Với đường callback sau completion thông dụng, lỗi có thể được hạ tầng ghi log thay vì làm lời gọi nghiệp vụ thất bại theo cách mong đợi; cấu hình và cách thực thi cần được quan sát trong dự án.

Ứng dụng cần quyết định rõ:

- Phản ứng thất bại có được bỏ qua không?
- Có trạng thái pending hoặc bản ghi công việc để xử lý lại không?
- Ai theo dõi lỗi và retry?
- Khi client thử lại command, có làm lặp tác động không?

### 7.2. `@Async` thay đổi nơi chạy, không thêm độ bền

Có thể kết hợp:

```java
@Async
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderConfirmed event) {
    // Chạy trên executor đã cấu hình.
}
```

Ứng dụng cần cấu hình hỗ trợ async và executor phù hợp. Trong cách dùng này, việc lên lịch listener gắn với phase sau commit, còn phần việc được thực thi trên luồng khác.

Hệ quả:

- Transaction gắn với luồng nguồn không tự truyền sang luồng async.
- Security context, tenant context hoặc MDC cần một chiến lược truyền riêng khi cần dùng.
- Với phương thức async trả `void`, lỗi thường được xử lý qua cơ chế lỗi async thay vì được ném về người công bố sự kiện.
- Tiến trình dừng hoặc tác vụ không vào được executor vẫn có thể làm mất công việc nếu chưa có lưu trữ bền vững.

Không truyền một entity managed cho listener async rồi giả định lazy association sẽ còn truy cập được. Hãy dùng payload có chủ đích và transaction riêng cho các thao tác cần thiết.

### 7.3. Thứ tự listener không phải quy trình bền vững

`@Order` có thể hỗ trợ thứ tự gọi listener trong phạm vi hạ tầng tương ứng. Nó không cung cấp thứ tự hoàn thành giữa các tác vụ async, không tạo transaction chung và không bảo đảm một listener sau luôn quan sát được thành công của listener trước.

Nếu bước B bắt buộc chỉ được thực hiện sau khi bước A hoàn tất bền vững, nên mô hình hóa quan hệ đó bằng một luồng điều phối hoặc trạng thái công việc rõ ràng. Không dựa hoàn toàn vào thứ tự annotation.

## 8. AFTER_COMMIT và cửa sổ mất thông báo

### 8.1. Commit thành công chưa bảo đảm phản ứng được thực hiện

Một sự kiện chỉ giữ trong bộ nhớ có thể gặp các cửa sổ lỗi:

| Thời điểm tiến trình dừng | Trạng thái có thể xảy ra |
| --- | --- |
| Trước khi giao dịch nguồn commit | Giao dịch chưa có một kết quả commit thành công được ứng dụng xác nhận |
| Sau commit, trước khi listener hoàn tất | Dữ liệu chính đã commit nhưng phản ứng có thể chưa xảy ra |
| Sau khi bên ngoài nhận thông báo, trước khi ghi nhận kết quả gửi | Lần xử lý lại có thể tạo bản trùng |

Không thể đóng các cửa sổ này chỉ bằng cách đổi `@EventListener` thành `@TransactionalEventListener` hoặc thêm `@Async`.

Nếu phản ứng là thông báo phụ có thể tái tạo từ dữ liệu hiện tại, ứng dụng có thể chấp nhận một chính sách đơn giản. Nếu thông điệp bắt buộc phải được gửi, cần lưu ý định gửi bền vững.

### 8.2. Transactional outbox lưu ý định trước commit

Một thiết kế thường dùng:

```text
T1:
    Ghi thay đổi PurchaseOrder
    Ghi bản ghi outbox tương ứng
    Commit cả hai trong cùng transaction có hiệu lực
                         |
                         v
Relay:
    Đọc bản ghi chưa gửi
    Gửi message
    Ghi nhận tiến độ theo chính sách retry
                         |
                         v
Consumer:
    Xử lý có kiểm soát bản trùng
```

Nếu outbox được ghi cùng transaction với aggregate trên tài nguyên hỗ trợ, hệ thống có một dấu vết bền vững để tiếp tục gửi sau khi tiến trình khởi động lại.

Có thể chuyển domain event thành bản ghi outbox bằng xử lý đồng bộ trong transaction nguồn, hoặc bằng cơ chế trước commit được thiết kế và kiểm chứng phù hợp. Điều kiện quyết định là thao tác ghi outbox thực sự tham gia cùng transaction với dữ liệu chính.

Không ghi bản ghi outbox lần đầu ở `AFTER_COMMIT` rồi gọi đó là nguyên tử với cập nhật đơn hàng. Giữa commit đơn hàng và thao tác ghi outbox vẫn có một khoảng trống.

Listener sau commit có thể đóng vai trò đánh thức relay để giảm độ trễ, trong khi relay vẫn phải có cách tìm lại các bản ghi pending nếu tín hiệu đánh thức bị mất.

### 8.3. Phân biệt hai loại retry

| Loại retry | Câu hỏi cần xử lý |
| --- | --- |
| Client gọi lại command xác nhận đơn | Làm sao trả kết quả phù hợp mà không xác nhận hai lần? |
| Relay hoặc consumer xử lý lại một event | Làm sao tránh lặp tác động của cùng một sự kiện? |

Event ID hỗ trợ nhận diện một lần phát sinh. Nó không tự cung cấp command idempotency và cũng không tự làm consumer trở nên idempotent.

Khi retry gửi cùng một thông điệp, cần giữ định danh ổn định thay vì tạo một event ID mới cho mỗi lần gửi. Nếu consumer lưu dấu đã xử lý, việc lưu dấu và thay đổi trạng thái của consumer phải có ranh giới nguyên tử phù hợp.

Outbox và idempotency giúp xây dựng độ tin cậy; không nên suy ra một bảo đảm xử lý đúng một lần trên toàn hệ thống chỉ từ các annotation sự kiện.

## 9. Payload, kho dữ liệu và reactive context

### 9.1. Payload nên giữ đúng ý nghĩa tại thời điểm phát sinh

Một listener sau commit có thể chạy muộn hơn publication. Nếu sự kiện giữ tham chiếu tới một object mutable, dữ liệu mà listener nhìn thấy có thể đã thay đổi.

Nên cân nhắc:

- Dùng định danh và các kiểu giá trị bất biến.
- Tạo snapshot cho dữ liệu cần phản ánh đúng thời điểm nghiệp vụ.
- Không giữ toàn bộ entity chỉ để thuận tiện truy cập field.
- Không tự động đưa dữ liệu nhạy cảm vào payload.
- Chỉ thêm tenant, correlation ID hoặc version khi có nguồn cấp và hợp đồng sử dụng rõ ràng.

Nếu event chỉ chứa ID và listener đọc lại entity, hãy chấp nhận rằng đó là trạng thái tại lúc đọc, có thể đã bao gồm thay đổi từ một transaction khác sau sự kiện.

Event được tạo trước commit cũng không tự được bổ sung ID, version hoặc timestamp do store sinh ra sau này. Các metadata đó cần một chiến lược tạo và ánh xạ rõ ràng.

### 9.2. Sau `save` hoặc `flush` chưa phải sau commit

Trong JPA, `save`, dirty checking, flush và transaction commit là các mốc khác nhau. Một câu lệnh đã được gửi xuống cơ sở dữ liệu vẫn có thể thuộc một transaction sẽ rollback.

Với store khác, ý nghĩa của thao tác ghi và phạm vi transaction có thể khác. Spring Data Commons chia sẻ abstraction repository, nhưng không áp đặt một mô hình transaction giống nhau cho mọi kho dữ liệu.

Ngoài ra, cập nhật bằng SQL trực tiếp, bulk update hoặc client riêng có thể bỏ qua cơ chế aggregate events. Khi đó, không có sự kiện để `@TransactionalEventListener` tự khám phá từ thay đổi trong cơ sở dữ liệu.

Nếu ứng dụng cần sự kiện cho những đường ghi đó, phải có một thiết kế publication hoặc một cơ chế theo dõi thay đổi riêng.

### 9.3. Reactive không dựa vào giả định thread-bound

Mô hình imperative thường gắn transaction với luồng hiện tại. Reactive transaction sử dụng context của pipeline thay vì chỉ dựa vào `ThreadLocal`.

Trong các phiên bản Spring có hỗ trợ transactional event cho reactive, sự kiện cần mang hoặc được công bố cùng transaction context theo hợp đồng tương ứng. Spring có helper `TransactionalEventPublisher` cho nhu cầu này.

Không lấy nguyên ví dụ JDBC đồng bộ rồi suy ra nó giữ đúng context khi chuyển sang repository reactive. Cần xác định phiên bản Spring, reactive transaction manager, cách publication tham gia pipeline và nơi xử lý lỗi.

Tương tự, tenant hoặc security metadata phải được lấy từ context đúng trước khi tạo payload; không giả định listener trên một luồng khác sẽ đọc được dữ liệu của luồng ban đầu.

## 10. Kiểm chứng thời điểm thực thi

Các đoạn mã trong phần này là gợi ý cho bài thực hành. Cần chạy với cấu hình transaction và dependency thực tế của dự án; việc ghi tài liệu không thay thế kiểm thử tích hợp.

### 10.1. Tách kiểm tra listener và kiểm tra tích hợp aggregate

Có hai câu hỏi khác nhau:

1. Khi một sự kiện được công bố trong transaction, listener có chạy đúng phase không?
2. Khi gọi repository trong use case, Spring Data có công bố đúng sự kiện của aggregate không?

Có thể kiểm tra câu hỏi thứ nhất bằng publication trực tiếp để quan sát phase. Sau đó cần một bài kiểm tra qua application service và repository để xác minh cả đường aggregate events.

Chỉ kiểm tra publication trực tiếp chưa chứng minh rằng bulk update hoặc repository fragment của ứng dụng đã phát sự kiện đúng.

### 10.2. Dùng transaction có thể điều khiển

Ví dụ minh họa với `TransactionTemplate` và một probe đồng bộ chỉ dùng trong test:

```java
probe.reset();

transactionTemplate.executeWithoutResult(status -> {
    publisher.publishEvent(event);

    // Transaction vẫn đang mở.
    assertEquals(0, probe.count());
});

// TransactionTemplate đã hoàn tất commit và callback đồng bộ.
assertEquals(1, probe.count());
```

Trong ví dụ, `probe` là bean kiểm tra có listener `AFTER_COMMIT` tăng bộ đếm, còn `publisher` là `ApplicationEventPublisher`. Các assertion thuộc thư viện kiểm tra của dự án.

Trường hợp rollback:

```java
probe.reset();

transactionTemplate.executeWithoutResult(status -> {
    publisher.publishEvent(event);
    status.setRollbackOnly();
});

assertEquals(0, probe.count());
```

Điều kiện quan trọng: ví dụ cần kiểm soát được transaction vật lý. Nếu test đang có một transaction ngoài và template chỉ tham gia nó, việc template trả về chưa chắc là lúc commit thật.

Vì vậy, với dạng kiểm tra trên, tránh một test transaction bao ngoài không chủ đích, hoặc cấu hình propagation để ranh giới cần quan sát thực sự được hoàn tất.

### 10.3. Cẩn thận với test mặc định rollback

Một test tích hợp có `@Transactional` thường được thiết lập rollback sau khi test kết thúc. Listener `AFTER_COMMIT` sẽ không chạy như một luồng commit thành công chỉ vì repository đã được gọi bên trong test.

Có thể dùng một test không có transaction bao ngoài, điều khiển transaction tường minh, hoặc dùng công cụ quản lý test transaction phù hợp. Nếu test thực sự commit dữ liệu, cũng cần có cách cô lập và dọn dữ liệu kiểm tra.

Nếu listener dùng `@Async`, assertion ngay sau commit chưa chắc đã nhìn thấy kết quả. Cần chờ có giới hạn theo trạng thái quan sát được và báo lỗi rõ ràng khi hết hạn, thay vì thêm một thời gian ngủ cố định rồi coi kết quả là bảo đảm.

### 10.4. Ma trận hành vi cần quan sát

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| Publication trong transaction rồi commit | Listener AFTER_COMMIT xử lý sau commit |
| Publication trong transaction rồi rollback | Listener AFTER_COMMIT không xử lý |
| Publication ngoài transaction, fallback mặc định | Listener bị bỏ qua |
| Publication ngoài transaction, fallback bật | Listener chạy theo đường fallback |
| Listener sau commit ném exception | Transaction nguồn vẫn đã commit; lỗi được quan sát theo hạ tầng thực tế |
| Listener gọi writer REQUIRES_NEW thành công | Dữ liệu bổ sung commit trong transaction riêng |
| Writer REQUIRES_NEW thất bại | Không hoàn tác dữ liệu đã commit của transaction nguồn |
| Ghi entity bằng đường bỏ qua aggregate events | Không giả định listener sẽ tự được gọi |
| Hai lần publication của cùng event | Không giả định Spring tự loại bản trùng |
| Tiến trình dừng sau commit | Công việc cần tin cậy có thể phục hồi từ dữ liệu bền vững đã thiết kế |

Để xác minh dữ liệu đã commit, nên đọc bằng một ranh giới truy cập độc lập thích hợp. Việc nhìn thấy cùng object trong persistence context chưa đủ để chứng minh trạng thái bền vững.

## 11. Chẩn đoán các hiểu nhầm thường gặp

| Hiện tượng | Nguyên nhân cần xem | Hướng xử lý |
| --- | --- | --- |
| Listener không chạy | Không có transaction tại publication, fallback mặc định tắt | Kiểm tra ranh giới service và proxy giao dịch |
| Có `@Transactional` nhưng vẫn không có callback | Self-invocation, bean tự tạo hoặc chọn sai manager | Kiểm tra đường gọi thực tế và cấu hình manager |
| Test gọi save nhưng listener sau commit không chạy | Test transaction bị rollback hoặc chưa kết thúc | Điều khiển một commit thật trong bài kiểm tra |
| Request vẫn chậm | Listener sau commit còn chạy đồng bộ | Đo thời gian xử lý; chọn async hoặc công việc bền vững nếu cần |
| Ghi từ listener nhưng không thấy dữ liệu như mong đợi | Dựa vào tài nguyên của transaction đã hoàn tất | Dùng một transaction mới có chủ đích qua proxy phù hợp |
| Listener lỗi nhưng đơn hàng vẫn tồn tại | Lỗi xảy ra sau commit | Theo dõi lỗi và xử lý lại; không kỳ vọng rollback transaction cũ |
| Bật fallback làm listener chạy ngoài transaction | Đây là ý nghĩa của fallback | Chỉ bật nếu hành vi ngoài transaction được chấp nhận |
| Email hoặc message bị mất | Publication/callback chỉ ở trong bộ nhớ | Lưu ý định xử lý bền vững và thiết kế retry |
| Consumer xử lý hai lần | Publication lặp hoặc delivery có retry | Giữ event ID và thiết kế idempotency |
| Async không đọc được tenant hoặc lazy field | Context không được truyền hoặc entity đã tách khỏi phiên | Dùng payload và context có chủ đích |

Khi chẩn đoán, ghi nhận event ID, aggregate ID và các mốc publication/commit/handler. Không log toàn bộ payload hoặc dữ liệu xác thực chỉ để chứng minh listener có chạy.

## 12. Chọn cách xử lý theo yêu cầu

| Yêu cầu | Hướng thiết kế |
| --- | --- |
| Giữ invariant khi xác nhận đơn | Kiểm tra trong hành vi aggregate và use case trước commit |
| Ghi dữ liệu phải nguyên tử với đơn hàng | Tham gia transaction nguồn trên tài nguyên hỗ trợ |
| Quan sát một giao dịch đã commit | Listener AFTER_COMMIT |
| Ghi bổ sung độc lập sau commit | AFTER_COMMIT gọi một transaction mới phù hợp |
| Giảm thời gian xử lý trên luồng request | Chọn async hoặc worker theo yêu cầu; xét riêng độ bền |
| Bắt buộc cuối cùng phải gửi thông điệp | Lưu ý định bền vững, chẳng hạn outbox, cùng retry và idempotency |
| Theo dõi rollback | AFTER_ROLLBACK, không diễn giải như sự kiện nghiệp vụ thành công |

Không cần đưa mọi phản ứng vào listener. Một chuỗi xử lý bắt buộc, có phụ thuộc kết quả rõ ràng, có thể được điều phối trực tiếp trong service hoặc một workflow thích hợp.

## 13. Bài thực hành

1. Tạo use case xác nhận đơn với repository phù hợp và transaction bao quanh service.
2. Ghi nhận `OrderConfirmed` từ aggregate; thêm listener AFTER_COMMIT chỉ ghi nhận event ID.
3. Quan sát sự khác nhau giữa commit thành công và rollback sau publication.
4. Công bố ngoài transaction để so sánh `fallbackExecution = false` và `true`.
5. Thêm writer REQUIRES_NEW; gây lỗi ở writer và kiểm tra rằng trạng thái đơn đã commit vẫn tồn tại.
6. Mô tả điều gì xảy ra nếu tiến trình dừng sau commit nhưng trước listener; đề xuất nơi lưu công việc pending.
7. Kiểm tra đường ghi tùy biến của repository có còn công bố aggregate events hay không.

Trả lời được ba câu hỏi cho mỗi phản ứng: **nó chạy sau mốc nào, thất bại ảnh hưởng dữ liệu nào, và ai chịu trách nhiệm thử lại?**

## 14. Điểm cần ghi nhớ

- `@TransactionalEventListener` gắn xử lý với lifecycle của transaction; AFTER_COMMIT là phase mặc định.
- Publication phải xảy ra trong một transaction phù hợp nếu muốn giữ hợp đồng sau commit.
- `fallbackExecution = true` cho phép xử lý ngoài transaction, không tạo một bảo đảm commit mới.
- Listener sau commit thông thường vẫn có thể chạy đồng bộ và làm tăng latency.
- Ghi dữ liệu sau commit cần một ranh giới giao dịch thích hợp; REQUIRES_NEW qua bean khác là một lựa chọn thường dùng.
- Exception sau commit không rollback được transaction nguồn đã thành công.
- Async, thứ tự listener và danh sách sự kiện trong aggregate không thay thế lưu trữ bền vững.
- Khi việc giao nhận là bắt buộc, cần thiết kế outbox hoặc cơ chế tương ứng cùng retry, theo dõi lỗi và idempotency.
- Hành vi cuối cùng phải được đối chiếu với repository method, store, transaction manager và context thực tế của ứng dụng.