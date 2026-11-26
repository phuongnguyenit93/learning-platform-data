# Bổ sung callback, auditing và sự kiện sau commit

## 1. Mục tiêu của bài thực hành

Một repository lưu được dữ liệu mới chỉ đáp ứng một phần yêu cầu của ứng dụng. Trong thực tế, thao tác xác nhận đơn hàng còn cần chuẩn hóa dữ liệu, ghi lại ai thay đổi đối tượng và kích hoạt tác vụ sau khi transaction thành công.

Bài thực hành thuộc chương **Thực hành tổng hợp** của **SPRING_DATA_COMMONS**. Ta kết hợp abstraction repository, cơ chế callback, auditing và domain event để trả lời ba câu hỏi:

- Dữ liệu cần được chuẩn hóa ở thời điểm nào?
- Ai tạo hoặc sửa aggregate, vào thời điểm nào?
- Khi nào có thể coi dữ liệu đã commit để thực hiện tác vụ tiếp theo?

Spring Data Commons cung cấp nhiều abstraction dùng chung cho các store, nhưng việc tích hợp callback và auditing phụ thuộc vào từng module lưu trữ. Ví dụ chính trong bài chọn **Spring Data JDBC, luồng imperative và transaction do Spring quản lý**. Không suy rộng chữ ký callback JDBC sang JPA, MongoDB hoặc R2DBC.

Kết quả mong muốn là một luồng xác nhận đơn hàng có thể giải thích được khi commit, rollback và khi listener gặp lỗi. Bài cũng phân biệt cơ chế gọi listener sau commit trong tiến trình với cơ chế giao sự kiện bền vững bằng outbox.

## 2. Tình huống và các bất biến cần giữ

Giả sử ứng dụng quản lý `PurchaseOrder` với hai trạng thái:

```text
DRAFT --confirm()--> CONFIRMED
```

Ta đặt ra các quy tắc:

1. Mã tham chiếu được bỏ khoảng trắng ở hai đầu và chuyển thành chữ hoa trước khi chuyển aggregate thành dữ liệu lưu trữ.
2. Khi tạo mới, ghi người tạo và thời điểm tạo.
3. Khi cập nhật, giữ metadata tạo và cập nhật metadata sửa.
4. Chỉ một chuyển trạng thái hợp lệ mới tạo sự kiện `OrderConfirmed`.
5. Bộ nhận sự kiện sau commit không được ghi nhận đơn xác nhận nếu transaction rollback.
6. Tác vụ bên ngoài có yêu cầu giao nhận tin cậy phải có cơ chế bền vững riêng.

Trong bài, callback xử lý chuẩn hóa biểu diễn; aggregate giữ quy tắc chuyển trạng thái; auditing quản lý metadata; transaction quyết định commit; listener phản ứng với sự kiện. Mỗi cơ chế có một trách nhiệm cụ thể.

| Cơ chế | Trách nhiệm trong bài | Điều không thể suy ra từ cơ chế đó |
| --- | --- | --- |
| Callback trước chuyển đổi | Chuẩn hóa mã tham chiếu | Dữ liệu đã được commit |
| Auditing | Ghi người và thời điểm tạo/sửa | Có lịch sử đầy đủ của mọi phiên bản dữ liệu |
| Phương thức domain | Kiểm soát chuyển trạng thái | Mọi thay đổi đều đã được lưu |
| Domain event | Biểu diễn việc có ý nghĩa nghiệp vụ | Sự kiện đã được gửi đến broker |
| Listener `AFTER_COMMIT` | Chạy khi transaction phát sự kiện đã commit | Có retry, lưu bền hoặc giao đúng một lần |
| Outbox | Ghi ý định phát sự kiện cùng transaction dữ liệu | Consumer không bao giờ nhận trùng |

## 3. Kiến trúc tối thiểu và phạm vi store

Luồng chính của bài:

```text
OrderCommandService.confirm(id)
    |
    | mở hoặc tham gia transaction
    v
Repository.findById(id)
    |
    v
PurchaseOrder.confirm(clock) -> đăng ký OrderConfirmed
    |
    v
Repository.save(order)
    |
    +--> callback chuẩn hóa + auditing theo pipeline của JDBC
    +--> ghi dữ liệu
    +--> repository công bố domain event trong transaction hiện tại
    |
    v
Transaction commit
    |
    v
@TransactionalEventListener(AFTER_COMMIT)
    |
    v
Bộ ghi nhận trong bộ nhớ dùng cho bài thực hành
```

Sơ đồ không quy định một thứ tự tổng quát giữa mọi callback, mọi module auditing và mọi sự kiện của tất cả store. Thứ tự chi tiết phải theo pipeline và cấu hình của module cụ thể. Ví dụ được thiết kế để callback chuẩn hóa và auditing không phụ thuộc vào thứ tự tương đối giữa chúng.

Các khác biệt cần biết khi áp dụng sang store khác:

| Store | Callback và auditing cần xem |
| --- | --- |
| Spring Data JDBC | Callback của Spring Data Relational/JDBC và `@EnableJdbcAuditing` |
| Spring Data MongoDB | Callback MongoDB có ngữ cảnh riêng, ví dụ collection; bật auditing MongoDB tương ứng |
| Spring Data JPA | Lifecycle callback của JPA, `AuditingEntityListener` và `@EnableJpaAuditing`; không lấy callback JDBC gắn vào entity JPA |
| Spring Data R2DBC | Pipeline reactive, callback reactive và cơ chế auditor reactive tương ứng |

`EntityCallback` là abstraction dùng chung, không có nghĩa mọi interface callback sẽ được mọi repository tự động gọi. Tương tự, chỉ thêm `@CreatedDate` lên một field chưa đủ nếu auditing chưa được tích hợp và bật cho store đó.

## 4. Mô hình aggregate và domain event

### 4.1. Sự kiện chứa dữ liệu bất biến

Sự kiện nên mang snapshot nhỏ, đủ cho consumer, thay vì giữ tham chiếu tới aggregate có thể tiếp tục bị thay đổi.

```java
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        Long orderId,
        String reference,
        Instant occurredAt) {
}
```

`eventId` nhận diện một sự kiện cụ thể; `orderId` nhận diện aggregate. `occurredAt` là thời điểm nghiệp vụ đăng ký sự kiện, không phải timestamp commit do cơ sở dữ liệu xác nhận.

Sự kiện không mang toàn bộ entity, security context hoặc một đối tượng persistence đang sống. Điều này giúp listener dễ kiểm thử và giảm phụ thuộc vào cách store materialize dữ liệu.

### 4.2. Aggregate dùng AbstractAggregateRoot

Các đoạn mã sau thuộc cùng một ví dụ; mỗi public type được đặt trong file Java tương ứng khi triển khai. Phần cấu hình datasource, dependency và khởi tạo schema thuộc dự án thực hành.

```java
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.domain.AbstractAggregateRoot;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder
        extends AbstractAggregateRoot<PurchaseOrder> {

    @Id
    private Long id;

    @Version
    private Long version;

    private String reference;
    private OrderStatus status;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    protected PurchaseOrder() {
        // Constructor để mapping tạo đối tượng rồi gán các field.
    }

    public static PurchaseOrder draft(String reference) {
        PurchaseOrder order = new PurchaseOrder();
        order.reference = reference;
        order.status = OrderStatus.DRAFT;
        return order;
    }

    public void confirm(Clock clock) {
        if (id == null) {
            throw new IllegalStateException(
                    "Phải lưu đơn nháp trước khi xác nhận");
        }
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Chỉ đơn nháp mới được xác nhận");
        }

        status = OrderStatus.CONFIRMED;

        registerEvent(new OrderConfirmed(
                UUID.randomUUID(),
                id,
                reference,
                clock.instant()));
    }

    void normalizeReference(String normalizedReference) {
        this.reference = normalizedReference;
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public String getReference() { return reference; }
    public OrderStatus getStatus() { return status; }
    public String getCreatedBy() { return createdBy; }
    public Instant getCreatedAt() { return createdAt; }
    public String getLastModifiedBy() { return lastModifiedBy; }
    public Instant getLastModifiedAt() { return lastModifiedAt; }
}
```

```java
public enum OrderStatus {
    DRAFT,
    CONFIRMED
}
```

Ở đây, `AbstractAggregateRoot` hỗ trợ giữ danh sách domain event và cung cấp các hook để repository công bố rồi dọn danh sách đó. Nó không tự lưu aggregate và không tự tạo transaction.

Bài tách bước tạo đơn nháp và bước xác nhận để `orderId` đã tồn tại khi tạo sự kiện. Nếu hệ thống phát sự kiện ngay lúc tạo aggregate với ID sinh từ database, cần thiết kế rõ thời điểm có ID hoặc sử dụng một định danh nghiệp vụ được cấp trước. Không mặc định rằng giá trị ID trong event tạo trước `save` sẽ tự được sửa sau khi insert.

`@Version` hỗ trợ optimistic locking trong store tương ứng. Với trường hợp hai transaction cùng đọc đơn nháp, nó giúp phát hiện cập nhật dựa trên phiên bản cũ. Đây là một phần bảo vệ cạnh tranh dữ liệu; listener không thay thế được kiểm soát này.

### 4.3. Schema minh họa

Ví dụ schema cho H2 với chiến lược tên cột gạch dưới mặc định:

```sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT,
    reference VARCHAR(80) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_modified_by VARCHAR(100) NOT NULL,
    last_modified_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

DDL thực tế phải theo dialect và naming strategy của ứng dụng. Ràng buộc `UNIQUE` vẫn cần thiết: callback chuẩn hóa không thể bảo đảm hai transaction đồng thời sẽ không tạo cùng một mã tham chiếu.

## 5. Bổ sung callback chuẩn hóa trước khi lưu

Với Spring Data JDBC, có thể dùng `BeforeConvertCallback` để xử lý aggregate trước bước chuyển sang biểu diễn lưu trữ:

```java
import java.util.Locale;

import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class NormalizeOrderReference
        implements BeforeConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeConvert(PurchaseOrder order) {
        String raw = order.getReference();

        if (raw == null) {
            throw new IllegalArgumentException(
                    "Mã tham chiếu không được null");
        }

        String normalized = raw.trim().toUpperCase(Locale.ROOT);

        if (normalized.isEmpty() || normalized.length() > 80) {
            throw new IllegalArgumentException(
                    "Mã tham chiếu phải có từ 1 đến 80 ký tự");
        }

        order.normalizeReference(normalized);
        return order;
    }
}
```

Với dữ liệu đầu vào `"  po-2026-001  "`, mã được lưu là `"PO-2026-001"`. Dùng `Locale.ROOT` để phép chuyển hoa không phụ thuộc locale mặc định của máy chạy.

Phép chuẩn hóa này có tính lặp ổn định: áp dụng nhiều lần vẫn cho cùng kết quả. Thuộc tính đó phù hợp với một callback có thể chạy ở nhiều lần lưu.

### 5.1. Giới hạn trách nhiệm của callback

Callback trả lại aggregate để pipeline tiếp tục. Nếu callback ném exception trong luồng transaction đang xét, thao tác lưu không hoàn tất bình thường; exception cần được truyền ra để transaction được xử lý theo quy tắc rollback.

Không gọi lại `repository.save(order)` bên trong callback này. Làm vậy có thể tạo đệ quy, gọi auditing nhiều lần hoặc phát sinh một luồng lưu khó kiểm soát. Cũng không gọi dịch vụ ngoài ở đây vì transaction có thể rollback sau khi callback đã chạy.

Nếu có nhiều callback cùng sửa một thuộc tính, cần thiết kế và kiểm thử thứ tự bằng cơ chế ordering được hỗ trợ. Không giả định thứ tự khai báo bean là thứ tự thực thi.

### 5.2. Callback không bao phủ mọi đường ghi

Callback của Spring Data JDBC chỉ tham gia các thao tác đi qua pipeline hỗ trợ nó. Câu SQL chạy trực tiếp, một công cụ sửa database hoặc một đường cập nhật tùy chỉnh có thể bỏ qua callback.

Do đó:

- Bất biến nghiệp vụ quan trọng vẫn cần nằm trong domain/service phù hợp.
- Ràng buộc cấu trúc quan trọng vẫn cần được bảo vệ ở database.
- Mọi đường ghi ngoài repository phải được đánh giá riêng.

Trong bài, callback xử lý biểu diễn chuẩn của mã; aggregate xử lý tính hợp lệ của chuyển trạng thái. Không dồn toàn bộ nghiệp vụ vào một hook persistence.

## 6. Bật auditing có thể kiểm thử

### 6.1. Cấu hình cho Spring Data JDBC

```java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing(
        auditorAwareRef = "orderAuditor",
        dateTimeProviderRef = "orderDateTimeProvider",
        modifyOnCreate = true)
public class OrderAuditConfiguration {

    @Bean
    Clock orderClock() {
        return Clock.systemUTC();
    }

    @Bean
    AuditorAware<String> orderAuditor() {
        // Danh tính cố định để bài thực hành có dữ liệu xác định.
        return () -> Optional.of("capstone-user");
    }

    @Bean
    DateTimeProvider orderDateTimeProvider(Clock orderClock) {
        return () -> Optional.of(orderClock.instant());
    }
}
```

Danh tính cố định chỉ phục vụ ví dụ. Trong ứng dụng có người dùng, `AuditorAware<String>` phải lấy định danh đã được xác thực từ ngữ cảnh đáng tin cậy. Không lấy người sửa trực tiếp từ một field do client tự gửi.

Tác vụ nền có thể dùng một danh tính hệ thống được quy định rõ. Việc không tìm thấy auditor cần có chính sách nhất quán: từ chối lệnh, cho phép thiếu metadata, hay gán một danh tính hệ thống trong đúng ngữ cảnh. Không tùy tiện coi mọi request không có người dùng là tác vụ hệ thống.

Với schema minh họa có `NOT NULL`, các lần ghi hợp lệ phải có auditor. Trả `Optional.empty()` không tự tạo một danh tính mặc định.

### 6.2. Ý nghĩa bốn trường audit

| Field | Khi tạo mới | Khi cập nhật |
| --- | --- | --- |
| `createdBy` | Ghi auditor tạo | Giữ nguyên |
| `createdAt` | Ghi thời điểm tạo | Giữ nguyên |
| `lastModifiedBy` | Được ghi trong ví dụ vì `modifyOnCreate = true` | Ghi auditor sửa |
| `lastModifiedAt` | Được ghi trong ví dụ vì `modifyOnCreate = true` | Ghi thời điểm sửa |

Cần phân biệt “mới hay đã tồn tại” với việc một field ID có giá trị hay không trong mọi tình huống. Spring Data có cơ chế xác định trạng thái mới, có thể xét version hoặc `Persistable` tùy mô hình và store. Ví dụ dùng `Long id` và `Long version` để đi theo cơ chế mapping/version thông thường của JDBC.

Không cho client gán lại `createdBy` hoặc `createdAt` khi cập nhật. DTO nhận lệnh chỉ nên chứa dữ liệu mà người gọi được phép thay đổi; service tải aggregate hiện tại rồi thực hiện lệnh.

### 6.3. Auditing không phải lịch sử thay đổi đầy đủ

Bốn field audit chỉ cho biết metadata tạo và lần sửa gần nhất của trạng thái hiện tại. Chúng không lưu mọi giá trị cũ, mọi lần chuyển trạng thái hoặc đầy đủ bằng chứng của một quy trình phê duyệt.

Nếu cần lịch sử bất biến, phải thiết kế bảng lịch sử, change log hoặc cơ chế chuyên biệt. Domain event cũng chỉ trở thành lịch sử bền vững khi được lưu bằng một thiết kế có chủ đích.

Thời điểm do `DateTimeProvider` cung cấp là thời điểm auditing chạy. Nó không phải cam kết rằng database commit đúng thời điểm đó. Hai transaction có thể có timestamp audit theo một thứ tự nhưng commit theo thứ tự khác.

## 7. Repository và transaction ở lớp service

```java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

Service xác định ranh giới transaction:

```java
import java.time.Clock;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCommandService {

    private final PurchaseOrderRepository orders;
    private final Clock clock;

    public OrderCommandService(
            PurchaseOrderRepository orders,
            Clock clock) {
        this.orders = orders;
        this.clock = clock;
    }

    @Transactional
    public PurchaseOrder createDraft(String reference) {
        return orders.save(PurchaseOrder.draft(reference));
    }

    @Transactional
    public PurchaseOrder confirm(Long orderId) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Không tìm thấy đơn"));

        order.confirm(clock);
        return orders.save(order);
    }
}
```

Với JDBC, không giả định rằng tải đối tượng rồi sửa field là database tự được cập nhật nhờ dirty checking. Lệnh `save` ở cuối là một phần rõ ràng của luồng lưu.

Luôn sử dụng kết quả trả về của `save` khi cần trạng thái sau lưu. Tùy mapping và callback, instance trả về có thể chứa ID, version hoặc metadata đã được cập nhật.

Trong ví dụ, service được gọi qua Spring proxy và dùng transaction manager phù hợp với datasource JDBC. Tự gọi một phương thức `@Transactional` từ phương thức khác trên cùng instance không tự tạo thêm ranh giới transaction theo cơ chế proxy thông thường.

### 7.1. Ai công bố domain event?

`registerEvent` chỉ đăng ký sự kiện trong aggregate. Khi phương thức repository được hỗ trợ như `save` hoặc `saveAll` xử lý aggregate, hạ tầng repository nhận diện các hook domain event để công bố chúng qua cơ chế application event của Spring.

Có thể tự định nghĩa hook bằng `@DomainEvents` và `@AfterDomainEventPublication`; ví dụ dùng `AbstractAggregateRoot` để có sẵn cách đăng ký và dọn danh sách.

Cần ghi nhớ các giới hạn:

- Sửa đối tượng trong bộ nhớ không tự công bố sự kiện.
- Gọi một phương thức domain rồi không `save` không kích hoạt cơ chế repository trong ví dụ.
- Đường SQL tùy chỉnh không tự nhận danh sách sự kiện của aggregate.
- Không coi `deleteById` là một cam kết công bố domain event của aggregate; phương thức đó không nhận aggregate chứa các sự kiện cần phát.
- Khi viết repository implementation riêng hoặc dùng phương thức ghi khác, phải kiểm tra điểm tích hợp event thực tế.

Ranh giới transaction ở service giúp sự kiện từ `save` được công bố trong transaction nghiệp vụ đang hoạt động. Không dựa vào suy đoán về thứ tự các interceptor khi chỉ gọi repository rời rạc rồi mong listener chắc chắn gắn với một transaction phù hợp.

### 7.2. Công bố sự kiện và commit là hai thời điểm

Trong luồng này, repository công bố `OrderConfirmed` trước khi transaction service kết thúc. Một listener thông thường dùng `@EventListener`, với cấu hình xử lý đồng bộ mặc định, có thể chạy ngay ở thời điểm đó.

Vì thế, nhận được application event không chứng minh transaction đã commit. Một exception ở bước tiếp theo vẫn có thể làm transaction rollback.

Để trì hoãn phần phản ứng đến khi commit thành công, dùng transactional event listener với phase phù hợp.

## 8. Listener chỉ ghi nhận sau commit

Để quan sát chính xác thời điểm chạy, bài dùng một bộ ghi nhận trong bộ nhớ. Nó không gửi email hay gọi broker:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderCommitProbe {

    private final List<OrderConfirmed> observed =
            new CopyOnWriteArrayList<>();

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderConfirmed event) {
        observed.add(event);
    }

    public List<OrderConfirmed> snapshot() {
        return List.copyOf(observed);
    }

    public void clear() {
        observed.clear();
    }
}
```

`OrderCommitProbe` là công cụ quan sát cho bài lab, không phải nơi lưu lịch sử nghiệp vụ. Danh sách mất khi tiến trình dừng.

Trong cấu hình imperative đồng bộ đang xét:

1. Aggregate đăng ký sự kiện.
2. Repository lưu và công bố sự kiện khi transaction còn hoạt động.
3. Spring gắn việc xử lý của transactional listener với transaction đó.
4. Khi transaction commit thành công, phương thức `afterCommit` mới ghi nhận sự kiện.
5. Khi rollback, phương thức `afterCommit` không chạy.

### 8.1. Phân biệt các phase

| Phase | Thời điểm và ý nghĩa |
| --- | --- |
| `BEFORE_COMMIT` | Xử lý trước commit; transaction vẫn có thể thất bại |
| `AFTER_COMMIT` | Xử lý sau khi transaction đã commit thành công |
| `AFTER_ROLLBACK` | Xử lý khi transaction đã rollback |
| `AFTER_COMPLETION` | Xử lý sau khi transaction kết thúc theo cả hai kết quả |

Không dùng `AFTER_COMPLETION` để suy ra thao tác nghiệp vụ thành công. Cũng không dùng callback mang tên “after save” làm bằng chứng commit: hoàn thành một bước lưu vẫn có thể nằm trong transaction chưa kết thúc.

### 8.2. Không có transaction thì sao?

Mặc định, `@TransactionalEventListener` không xử lý sự kiện được phát khi không có transaction thích hợp để gắn vào. Thuộc tính `fallbackExecution` có thể thay đổi hành vi này, nhưng bật nó không tạo ra một transaction mới và không cung cấp ý nghĩa “đợi commit” cho sự kiện vốn không có transaction.

Vì vậy, bài giữ mặc định và kiểm soát ranh giới transaction tại service. Khi thấy domain event đã được công bố nhưng probe không nhận, cần kiểm tra transaction thực tế trước khi thay cấu hình listener.

### 8.3. Dữ liệu audit trong event có thể chưa là trạng thái cuối

Trong ví dụ, `OrderConfirmed` được tạo trước `save`, nên không sao chép `lastModifiedAt` được auditing cập nhật trong lúc lưu. Event chỉ chứa các dữ liệu đã được xác định tại thời điểm domain method chạy.

Nếu consumer cần metadata sau lưu, phải thiết kế thời điểm tạo snapshot thích hợp. Không giữ entity mutable trong event để “đến lúc listener chạy thì đọc giá trị mới”; cách đó tạo phụ thuộc ngầm vào vòng đời đối tượng.

Với đơn được tải từ database trong luồng xác nhận, mã tham chiếu đã được chuẩn hóa khi tạo nháp. Ví dụ không hỗ trợ thay mã đồng thời với xác nhận. Nếu bổ sung chức năng đó, cần chuẩn hóa trước khi chụp snapshot hoặc thiết kế lại dữ liệu sự kiện để tránh lệch giữa event và dữ liệu lưu.

## 9. Kiểm thử tích hợp: quan sát bên trong và sau transaction

Các test sau cần Spring Boot, Spring Data JDBC, một datasource kiểm thử như H2, schema ở mục 4 và các bean đã trình bày. Chúng là mã hướng dẫn để triển khai trong dự án thực hành.

Điểm quan trọng là **không đặt `@Transactional` lên toàn bộ test class** trong ví dụ này. Nhiều test transactional mặc định rollback vào cuối test, khiến listener `AFTER_COMMIT` không chạy hoặc chưa chạy ở thời điểm assertion.

Ta dùng `TransactionTemplate` để biết chính xác khi transaction đã kết thúc, và một `Clock` kiểm soát được để tránh phụ thuộc thời gian máy chạy.

### 9.1. Clock kiểm thử

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

final class MutableTestClock extends Clock {

    private Instant current;

    MutableTestClock(Instant initial) {
        this.current = initial;
    }

    void setInstant(Instant value) {
        this.current = value;
    }

    @Override
    public ZoneId getZone() {
        return ZoneOffset.UTC;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        return Clock.fixed(current, zone);
    }

    @Override
    public Instant instant() {
        return current;
    }
}
```

Clock này phục vụ test chạy tuần tự. `withZone` trả một snapshot cố định; test bên dưới chỉ sử dụng `instant()`. Không dùng nó làm đồng hồ có thể điều khiển chung cho môi trường production.

### 9.2. Commit thành công và rollback

```java
import java.time.Instant;
import java.util.Locale;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Import(OrderLifecycleIntegrationTest.TestTimeConfiguration.class)
class OrderLifecycleIntegrationTest {

    private static final Instant T0 =
            Instant.parse("2026-01-10T08:00:00Z");
    private static final Instant T1 =
            Instant.parse("2026-01-10T09:00:00Z");

    @Autowired OrderCommandService commands;
    @Autowired PurchaseOrderRepository orders;
    @Autowired OrderCommitProbe probe;
    @Autowired PlatformTransactionManager transactionManager;
    @Autowired MutableTestClock clock;

    @BeforeEach
    void resetObservation() {
        clock.setInstant(T0);
        probe.clear();
    }

    @Test
    void confirmsOnlyAfterCommitAndPreservesCreationMetadata() {
        String raw = "  po-" + UUID.randomUUID() + "  ";
        PurchaseOrder draft = commands.createDraft(raw);
        Long id = draft.getId();

        assertThat(draft.getReference())
                .isEqualTo(raw.trim().toUpperCase(Locale.ROOT));
        assertThat(draft.getCreatedBy()).isEqualTo("capstone-user");
        assertThat(draft.getCreatedAt()).isEqualTo(T0);
        assertThat(draft.getLastModifiedAt()).isEqualTo(T0);
        assertThat(probe.snapshot()).isEmpty();

        clock.setInstant(T1);
        TransactionTemplate tx =
                new TransactionTemplate(transactionManager);

        tx.executeWithoutResult(status -> {
            commands.confirm(id);

            // save đã trả về, nhưng transaction ngoài chưa commit.
            assertThat(probe.snapshot()).isEmpty();
        });

        PurchaseOrder saved = orders.findById(id).orElseThrow();

        assertThat(saved.getStatus()).isEqualTo(OrderStatus.CONFIRMED);
        assertThat(saved.getCreatedBy()).isEqualTo("capstone-user");
        assertThat(saved.getCreatedAt()).isEqualTo(T0);
        assertThat(saved.getLastModifiedBy()).isEqualTo("capstone-user");
        assertThat(saved.getLastModifiedAt()).isEqualTo(T1);
        assertThat(saved.getVersion()).isNotEqualTo(draft.getVersion());

        assertThat(probe.snapshot()).hasSize(1);
        OrderConfirmed event = probe.snapshot().get(0);
        assertThat(event.eventId()).isNotNull();
        assertThat(event.orderId()).isEqualTo(id);
        assertThat(event.reference()).isEqualTo(saved.getReference());
        assertThat(event.occurredAt()).isEqualTo(T1);
    }

    @Test
    void rollbackKeepsDraftAndDoesNotNotifyAfterCommit() {
        PurchaseOrder draft =
                commands.createDraft("po-" + UUID.randomUUID());
        Long id = draft.getId();
        Long originalVersion = draft.getVersion();

        clock.setInstant(T1);
        TransactionTemplate tx =
                new TransactionTemplate(transactionManager);

        tx.executeWithoutResult(status -> {
            commands.confirm(id);
            assertThat(probe.snapshot()).isEmpty();
            status.setRollbackOnly();
        });

        PurchaseOrder reloaded = orders.findById(id).orElseThrow();

        assertThat(reloaded.getStatus()).isEqualTo(OrderStatus.DRAFT);
        assertThat(reloaded.getVersion()).isEqualTo(originalVersion);
        assertThat(reloaded.getCreatedAt()).isEqualTo(T0);
        assertThat(reloaded.getLastModifiedAt()).isEqualTo(T0);
        assertThat(probe.snapshot()).isEmpty();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestTimeConfiguration {

        @Bean
        @Primary
        MutableTestClock controlledClock() {
            return new MutableTestClock(T0);
        }
    }
}
```

`commands.createDraft` được gọi qua proxy và hoàn thành transaction tạo nháp trước khi bước xác nhận bắt đầu. Trong khối `TransactionTemplate`, phương thức `confirm` tham gia transaction đang có theo propagation mặc định. Sau khi khối kết thúc bình thường, ta mới kiểm tra kết quả sau commit.

Hai clock bean tồn tại trong test, nhưng `@Primary` chọn clock kiểm soát được cho các injection theo kiểu `Clock`. Context thực hành này giả định chỉ có một transaction manager phù hợp; dự án nhiều datasource phải chọn đúng manager thay vì dựa vào injection mơ hồ.

Không so sánh các object Java cũ để xác định rollback có thành công không. Test tải lại dữ liệu từ repository sau transaction để quan sát trạng thái database.

### 9.3. Các trường hợp cần bổ sung khi mở rộng bài

| Trường hợp | Kết quả cần kiểm chứng |
| --- | --- |
| Mã tham chiếu chỉ có khoảng trắng | Lệnh lưu thất bại, không có dòng hợp lệ mới |
| Hai mã khác nhau trước chuẩn hóa nhưng trùng sau chuẩn hóa | Ràng buộc unique phát hiện xung đột |
| Xác nhận lần hai | Domain từ chối, không phát thêm sự kiện xác nhận hợp lệ |
| Hai transaction cùng xác nhận một version | Optimistic locking ngăn cập nhật dựa trên version cũ |
| Auditor thay đổi giữa tạo và sửa | Giữ người tạo, cập nhật người sửa |
| Ghi bằng SQL trực tiếp | Không mặc định có callback và audit như repository |
| Phát sự kiện ngoài transaction | Listener mặc định không chạy |
| Listener gặp lỗi sau commit | Dữ liệu nghiệp vụ vẫn đã commit |
| Restart tiến trình | Dữ liệu trong probe không còn; không được coi là lịch sử bền vững |

Không dùng `sleep` để chờ listener trong cấu hình đồng bộ của bài. Cần kiểm soát ranh giới transaction. Nếu chủ động chuyển sang bất đồng bộ, test phải có cơ chế đợi có giới hạn phù hợp với mô hình đó.

## 10. Rollback không tua ngược đối tượng Java

Có một chi tiết dễ bỏ sót: transaction quản lý tài nguyên như connection database, không tự phục hồi mọi field của object Java.

Trong luồng xác nhận rồi rollback:

- Database trở lại trạng thái đơn nháp.
- Instance trong bộ nhớ có thể vẫn mang trạng thái `CONFIRMED`.
- Danh sách domain event có thể đã được dọn sau bước công bố.
- Listener `AFTER_COMMIT` không được gọi vì transaction rollback.

`@AfterDomainEventPublication` nói về việc công bố sự kiện, không nói về việc commit. Không dùng hook này làm nơi đánh dấu “đã giao thành công” cho một thông điệp bên ngoài.

Nếu muốn thử lại sau rollback, nên bắt đầu transaction mới, tải lại aggregate và thực hiện lại lệnh theo trạng thái hiện tại. Không lưu lại nguyên instance cũ rồi cho rằng database sẽ tự đồng bộ mọi thông tin hoặc danh sách sự kiện sẽ tự xuất hiện lại.

Việc thử lại cũng phải phân biệt lỗi có thể retry, như một số xung đột tạm thời, với lỗi nghiệp vụ, như đơn đã được xác nhận. Retry không được biến một lệnh không hợp lệ thành nhiều tác dụng phụ.

## 11. Lỗi sau commit và các giới hạn vận hành

### 11.1. Listener thất bại không đảo ngược commit

Giả sử sau commit, listener gọi một hệ thống thông báo và hệ thống đó đang không hoạt động. Transaction dữ liệu đã hoàn tất; exception trong listener không thể làm đơn hàng trở lại trạng thái nháp.

Cách exception được log hoặc được phản ánh ra bên gọi phụ thuộc đường xử lý và cấu hình cụ thể. Không thiết kế API với giả định “listener lỗi thì chắc chắn mọi thay đổi trước đó rollback”.

Điều này còn liên quan đến retry từ client. Nếu client nhận một lỗi ở ranh giới phản hồi và gửi lại lệnh, đơn có thể đã được xác nhận. Hệ thống cần xác định hành vi cho lệnh lặp và có cơ chế tra cứu kết quả phù hợp.

### 11.2. Muốn ghi database trong AFTER_COMMIT

Ở thời điểm callback sau commit chạy, một số tài nguyên transaction vẫn có thể còn được gắn với luồng cho đến khi hoàn tất cleanup. Không dựa vào việc “vẫn nhìn thấy connection” để cho rằng một lệnh ghi mới sẽ được commit như một transaction mới.

Nếu tác vụ sau commit cần ghi database độc lập, một phương án là gọi một bean khác có phương thức `@Transactional(propagation = Propagation.REQUIRES_NEW)`, đi qua Spring proxy và dùng đúng transaction manager.

Đó là transaction độc lập:

- Thành công hay thất bại của nó không đổi kết quả commit trước đó.
- Nó có thể thất bại sau khi đơn hàng đã được xác nhận.
- Nó không khép được khoảng trống nếu tiến trình dừng giữa commit đơn hàng và việc ghi tiếp theo.

Vì thế, ghi một bản tin outbox trong `AFTER_COMMIT` bằng transaction mới không mang lại tính nguyên tử với lần cập nhật đơn hàng trước đó.

### 11.3. Async chỉ thay đổi cách thực thi

Thêm `@Async` có thể chuyển công việc sang executor khi được cấu hình phù hợp. Nó không tự cung cấp kho sự kiện, retry bền vững, thứ tự xử lý toàn cục hoặc chống gửi trùng.

Ngữ cảnh transaction và các dữ liệu theo luồng không tự trở thành ngữ cảnh của worker thread. Vì vậy, sự kiện nên chứa dữ liệu cần thiết, thay vì để listener đọc auditor từ request hoặc security context đã kết thúc.

Không mặc định rằng thứ tự đăng ký listener là thứ tự hoàn thành của các tác vụ bất đồng bộ. Nếu nghiệp vụ có yêu cầu thứ tự, cần thiết kế cơ chế bảo đảm riêng.

### 11.4. Khoảng trống khi tiến trình dừng

Một timeline có thể xảy ra:

```text
T1: cập nhật đơn hàng
T2: database commit thành công
T3: tiến trình dừng trước khi listener gửi thông báo
T4: ứng dụng khởi động lại
```

Database có đơn đã xác nhận, nhưng application event nằm trong bộ nhớ không còn. Listener sau commit trong một tiến trình không tự phát lại sự kiện sau restart.

Đây là lý do cần phân biệt yêu cầu “chạy sau commit nếu tiến trình còn hoạt động” với yêu cầu “cuối cùng phải giao được sự kiện”.

## 12. Nâng cấp bài thực hành bằng transactional outbox

Nếu yêu cầu nghiệp vụ cần giao thông điệp đáng tin cậy, có thể lưu ý định phát sự kiện cùng transaction cập nhật aggregate.

Mô hình đơn giản:

```text
Transaction nghiệp vụ dùng cùng database và transaction manager:
    UPDATE purchase_order ...
    INSERT INTO order_outbox(event_id, aggregate_id, payload, ...)
    COMMIT

Dispatcher:
    đọc bản tin outbox chưa xử lý
    gửi đến đích
    đánh dấu hoặc cập nhật trạng thái xử lý
    thử lại khi lỗi

Consumer:
    nhận thông điệp
    kiểm tra event_id đã xử lý
    thực hiện tác dụng nghiệp vụ một cách idempotent
```

Tính chất quan trọng là dòng outbox được ghi trong **cùng transaction dữ liệu** với cập nhật đơn. Hai thao tác cùng thành công hoặc cùng rollback trong phạm vi transaction đó. Ghi vào hai database bằng hai local transaction riêng không tự có tính chất này.

Có thể tạo dòng outbox trực tiếp trong application service hoặc qua một cơ chế xử lý sự kiện đồng bộ được thiết kế để vẫn tham gia transaction. Nếu dùng listener để ghi outbox, phải xác nhận đúng phase, đúng transaction manager và đường rollback. Không chuyển việc ghi outbox sang `AFTER_COMMIT` rồi coi nó là nguyên tử với dữ liệu nghiệp vụ.

Outbox thường cần các thông tin:

| Trường | Vai trò |
| --- | --- |
| `event_id` | Định danh ổn định của bản tin qua các lần gửi lại |
| `aggregate_id` | Đối tượng nghiệp vụ liên quan |
| `event_type` | Loại sự kiện và quy ước giải mã |
| `payload` | Snapshot dữ liệu cần giao |
| `occurred_at` | Thời điểm sự kiện nghiệp vụ |
| Trạng thái/lần thử/thời điểm thử tiếp | Theo dõi quá trình giao nhận |

Dispatcher có thể gửi thành công rồi dừng trước khi đánh dấu đã gửi. Khi khởi động lại, nó gửi lại cùng một sự kiện. Vì vậy, thiết kế thực tế thường phải chấp nhận giao lặp và có cơ chế idempotency; không chỉ thêm một cờ `sent` rồi tuyên bố giao đúng một lần.

Với consumer có dữ liệu riêng, việc ghi nhận `event_id` đã xử lý và thay đổi nghiệp vụ của consumer nên được phối hợp nguyên tử khi có thể. Với tác dụng phụ bên ngoài như email hoặc thanh toán, cần xem khả năng hỗ trợ idempotency của chính hệ thống đích.

Trong biến thể outbox, listener sau commit có thể dùng để đánh thức dispatcher nhằm giảm độ trễ. Việc quét lại outbox vẫn là cơ chế phục hồi nếu tín hiệu đánh thức bị mất.

## 13. Đọc kết quả và chẩn đoán theo triệu chứng

| Triệu chứng | Điểm cần kiểm tra |
| --- | --- |
| Callback không chạy | Đúng interface của store chưa, có đăng ký bean chưa, thao tác có đi qua pipeline repository không |
| Callback chạy nhiều lần ngoài dự kiến | Có tự gọi `save` trong callback hoặc lưu aggregate lặp trong cùng luồng không |
| Audit luôn null | Đã bật auditing đúng store, field có mapping được, provider có trả giá trị không |
| Người tạo bị thay đổi khi sửa | Có nhận audit field từ client, dựng lại aggregate sai hoặc xác định trạng thái mới sai không |
| Thời điểm audit và event không trùng | Chúng được lấy ở các thời điểm và có ý nghĩa khác nhau; kiểm tra clock và thời điểm snapshot |
| Event đã đăng ký nhưng không công bố | Có gọi phương thức repository tích hợp domain event không |
| Event được công bố nhưng probe rỗng | Transaction có đang hoạt động, có rollback hoặc chưa kết thúc không |
| Listener chạy dù thao tác sau đó rollback | Có dùng `@EventListener` thường hoặc phase trước commit không |
| Database rollback nhưng object vẫn CONFIRMED | Đang quan sát object trong bộ nhớ thay vì tải lại dữ liệu |
| Bảng phụ không có bản ghi sau listener | Kiểm tra ranh giới transaction mới và lỗi sau commit; không dựa vào tài nguyên còn gắn với luồng |
| Mất thông báo sau restart | Application event chưa có kho bền vững; cân nhắc outbox |
| Nhận thông báo trùng | Kiểm tra retry, định danh sự kiện và idempotency của consumer |

Khi chẩn đoán, nên ghi log có `orderId`, `eventId`, loại sự kiện và giai đoạn xử lý. Không lấy số lần callback chạy làm số transaction commit. Không lấy số lần listener được gọi làm bằng chứng hệ thống bên ngoài đã hoàn thành tác dụng nghiệp vụ.

## 14. Điều chỉnh cho reactive và các module khác

Khi chuyển bài sang MongoDB hoặc JPA, giữ nguyên cách phân chia trách nhiệm nhưng thay điểm tích hợp callback và auditing theo store. Ví dụ, JPA có cơ chế lifecycle và auditing listener riêng; việc gọi phương thức domain cũng phải được phối hợp với điểm công bố sự kiện của repository.

Với R2DBC hoặc một pipeline reactive:

- Dùng callback và auditor reactive phù hợp.
- Không gọi `block()` chỉ để tái sử dụng callback imperative.
- Transaction context của reactive pipeline khác mô hình transaction gắn với thread của ví dụ JDBC.
- Việc đưa sự kiện vào transactional listener phải dùng cơ chế hỗ trợ và truyền ngữ cảnh đúng của hệ reactive đang dùng.

Một method trả về kiểu reactive không tự biến các đoạn mã imperative trong bài thành reactive. Tương tự, một callback dùng chung tên khái niệm không đồng nghĩa có cùng chữ ký hoặc cùng thời điểm thực thi.

## 15. Tiêu chí hoàn thành bài thực hành

Khi triển khai bài vào dự án, cần chứng minh được các hành vi sau:

1. Lưu đơn nháp chuẩn hóa được mã và ghi đủ metadata tạo.
2. Xác nhận đơn cập nhật trạng thái, version và metadata sửa.
3. Metadata tạo được giữ nguyên sau cập nhật.
4. Trong transaction đang mở, probe chưa ghi nhận sự kiện sau commit.
5. Sau commit, probe ghi đúng một sự kiện cho lần chuyển trạng thái hợp lệ trong tình huống kiểm thử.
6. Sau rollback, database vẫn là đơn nháp và probe không có sự kiện xác nhận.
7. Xác nhận lại một đơn đã xác nhận bị xử lý theo quy tắc domain.
8. Có giải thích riêng cho lỗi sau commit, mất tiến trình và khả năng giao trùng.
9. Nếu cần giao sự kiện bền vững, dòng outbox được ghi cùng transaction nghiệp vụ và dispatcher có cơ chế thử lại.
10. Mỗi điểm tích hợp callback/auditing được chọn theo đúng store thay vì suy từ abstraction Commons.

Qua bài này, repository trở thành một phần của luồng nghiệp vụ có ranh giới rõ ràng: callback chuẩn bị dữ liệu, auditing bổ sung metadata, aggregate ghi nhận sự kiện và transaction quyết định kết quả lưu. Listener sau commit phản ứng với kết quả đã commit; độ tin cậy giao nhận dài hạn cần được thiết kế thêm bằng cơ chế lưu bền và xử lý lặp.
