# Phân biệt dấu vết lần sửa gần nhất với lịch sử thay đổi đầy đủ

## 1. Hai câu hỏi khác nhau về cùng một bản ghi

Trong chương **Auditing** của module **SPRING_DATA_COMMONS**, các abstraction auditing giúp ứng dụng gắn thông tin người thực hiện và thời gian vào dữ liệu được lưu. Tuy nhiên, cần phân biệt hai câu hỏi:

1. **Ai sửa bản ghi này gần nhất, vào lúc nào?**
2. **Bản ghi này đã thay đổi qua những bước nào, mỗi bước đổi gì, do ai và vì sao?**

Các field như `lastModifiedBy` và `lastModifiedAt` chủ yếu trả lời câu hỏi thứ nhất. Câu hỏi thứ hai cần một cơ chế lưu lịch sử có phạm vi và hợp đồng rõ ràng.

Ví dụ, một đơn hàng đang có:

~~~text
status         = CANCELLED
lastModifiedBy = user:42
lastModifiedAt = 2026-03-10T09:30:00Z
~~~

Từ ba giá trị này, chưa thể biết:

- Trạng thái trước khi hủy là gì.
- Ai đã phê duyệt đơn hàng trước đó.
- Đơn hàng từng được sửa bao nhiêu lần.
- Người hủy nhập lý do gì.
- Có lần thử cập nhật nào bị từ chối hay không.
- Việc hủy có phát sinh từ giao diện, tác vụ nền hay một luồng tích hợp.

Một bản ghi hiện tại có thể là kết quả của nhiều chuỗi thay đổi khác nhau. Muốn phân biệt các chuỗi đó, hệ thống phải lưu thêm bằng chứng về từng thay đổi cần theo dõi.

## 2. Auditing của Spring Data thường bổ sung metadata hiện tại

Spring Data Commons cung cấp các annotation và abstraction dùng chung cho auditing. Việc bật auditing, điểm gọi callback hoặc listener và khả năng hỗ trợ cụ thể thuộc module lưu trữ được sử dụng.

Các annotation thường gặp:

| Annotation | Ý nghĩa thường dùng | Có tự lưu mọi giá trị cũ không? |
| --- | --- | --- |
| `@CreatedBy` | Người thực hiện khi bản ghi được tạo | Không |
| `@CreatedDate` | Thời điểm bản ghi được tạo | Không |
| `@LastModifiedBy` | Người thực hiện trong lần xử lý sửa gần nhất qua auditing | Không |
| `@LastModifiedDate` | Thời điểm trong lần xử lý sửa gần nhất qua auditing | Không |

`AuditorAware<T>` cung cấp danh tính cho hạ tầng auditing đồng bộ. `DateTimeProvider` cung cấp thời gian. Chúng là nguồn metadata, không phải một kho chứa các phiên bản trước đây của entity.

Ví dụ, nếu `lastModifiedBy` lần lượt nhận ba giá trị:

~~~text
user:10 → user:18 → user:42
~~~

thì field hiện tại thường chỉ giữ `user:42`. Hai giá trị trước không tự được chuyển sang một bảng lịch sử nhờ annotation đó.

Tương tự, một class nhúng chứa bốn field audit giúp tổ chức metadata trong model. Việc nhúng metadata không tự tạo thêm lịch sử.

### 2.1. Từ “audit” không có một nghĩa duy nhất

Trong trao đổi kỹ thuật, “audit” có thể chỉ:

- Metadata tạo và sửa trên bản ghi hiện tại.
- Một bảng lưu các lần đổi trạng thái nghiệp vụ.
- Các revision của entity.
- Nhật ký đăng nhập, truy cập và thao tác bị từ chối.
- Một luồng thay đổi lấy từ database.

Vì vậy, yêu cầu “bật audit cho đơn hàng” còn thiếu thông tin. Cần chuyển nó thành câu hỏi cụ thể, chẳng hạn: “Lưu người và thời điểm sửa gần nhất” hoặc “Lưu mọi lần chuyển trạng thái đã commit, kèm trạng thái trước, sau và lý do”.

### 2.2. Giới hạn của một lần “sửa gần nhất”

Metadata phản ánh đường ghi thực tế có tích hợp auditing. Không nên diễn giải nó thành lời bảo đảm rằng mọi thay đổi trong database đều đã được ghi nhận.

Ví dụ, một lệnh bulk update, native SQL, script vận hành hoặc thao tác trực tiếp qua driver có thể không đi qua cùng callback hay listener của entity.

Ngoài ra, thời điểm auditing lấy timestamp không tự đồng nghĩa thời điểm transaction commit. `lastModifiedAt` cũng không tự chứng minh rằng người dùng đã thay đổi một field nghiệp vụ cụ thể.

## 3. Quan sát một chuỗi thay đổi

Giả sử hệ thống thực hiện các thao tác sau và mỗi thao tác đều commit thành công:

| Mốc | Người thực hiện | Thao tác | Trạng thái sau thao tác |
| --- | --- | --- | --- |
| t0 | user:10 | Tạo đơn hàng | DRAFT |
| t1 | user:18 | Duyệt đơn hàng | APPROVED |
| t2 | user:18 | Đổi địa chỉ giao hàng | APPROVED |
| t3 | user:42 | Hủy do khách yêu cầu | CANCELLED |

Nếu chỉ có bản ghi hiện tại và metadata audit, sau t3 ta có thể thấy:

~~~text
id             = 501
status         = CANCELLED
createdBy      = user:10
createdAt      = t0
lastModifiedBy = user:42
lastModifiedAt = t3
~~~

Thông tin về t1 và t2 không xuất hiện trong các field này.

Một bảng lịch sử nghiệp vụ có thể lưu:

| orderId | action | before | after | actorId | occurredAt | reason |
| --- | --- | --- | --- | --- | --- | --- |
| 501 | CREATE | — | DRAFT | user:10 | t0 | Tạo đơn mới |
| 501 | APPROVE | DRAFT | APPROVED | user:18 | t1 | Đã xác nhận điều kiện bán |
| 501 | CHANGE_ADDRESS | Địa chỉ A | Địa chỉ B | user:18 | t2 | Khách đổi điểm nhận |
| 501 | CANCEL | APPROVED | CANCELLED | user:42 | t3 | Khách yêu cầu hủy |

Đây là một ví dụ về cấu trúc thông tin, không phải một bảng tự được Spring Data Commons sinh ra.

Nếu hệ thống chỉ lưu các lần chuyển trạng thái, sự kiện đổi địa chỉ ở t2 sẽ không có trong lịch sử đó. Muốn gọi lịch sử là “đầy đủ”, phải nói rõ nó đầy đủ đối với loại thay đổi nào.

## 4. Ba lớp dữ liệu thường cùng tồn tại

~~~mermaid
flowchart LR
    A["Lệnh nghiệp vụ"] --> B["Kiểm tra quyền và quy tắc"]
    B --> C["Trạng thái hiện tại"]
    C --> D["Metadata tạo và sửa"]
    B --> E["Lịch sử thay đổi đã chấp nhận"]
    A --> F["Nhật ký vận hành hoặc bảo mật theo yêu cầu"]
~~~

Các lớp này có mục đích riêng:

| Lớp | Nội dung điển hình | Câu hỏi phù hợp |
| --- | --- | --- |
| Trạng thái hiện tại | Giá trị đang có hiệu lực | Đơn hàng hiện ở trạng thái nào? |
| Metadata audit hiện tại | Người tạo, thời gian tạo, người sửa gần nhất, thời gian sửa gần nhất | Ai chạm vào bản ghi gần nhất? |
| Lịch sử thay đổi | Các lần thay đổi trong phạm vi được theo dõi | Trước đây đơn hàng đã ở những trạng thái nào? |
| Nhật ký thao tác hoặc bảo mật | Yêu cầu, kết quả, lỗi hoặc thao tác bị từ chối theo chính sách | Ai đã thử thực hiện hành động này? |

Một yêu cầu bị từ chối do thiếu quyền không tạo ra trạng thái mới của đơn hàng. Nếu cần lưu lần thử đó, phải có một hợp đồng nhật ký phù hợp; không thể suy nó ra từ bảng trạng thái hiện tại hoặc chỉ từ lịch sử các thay đổi đã commit.

## 5. Chọn cơ chế theo câu hỏi cần trả lời

| Cơ chế | Điểm mạnh | Giới hạn cần hiểu |
| --- | --- | --- |
| Field auditing của Spring Data | Metadata tạo và sửa trên entity | Không tự lưu giá trị trước và toàn bộ chuỗi thay đổi |
| Bảng lịch sử nghiệp vụ | Ghi hành động, lý do, actor và dữ liệu liên quan theo ngôn ngữ nghiệp vụ | Phải thiết kế và bao phủ các đường thay đổi đã cam kết |
| Revision của ORM, chẳng hạn Hibernate Envers trong hệ sinh thái JPA | Theo dõi phiên bản của các entity hoặc thuộc tính được cấu hình audit | Phụ thuộc cấu hình và đường ghi được cơ chế đó hỗ trợ; không tự có lý do nghiệp vụ |
| CDC từ database | Quan sát thay đổi dữ liệu theo khả năng của database và connector | Danh tính người dùng ứng dụng, ý định và lý do thường cần bổ sung; dữ liệu trước thay đổi phụ thuộc cấu hình |
| Trigger hoặc khả năng temporal của database | Đặt cơ chế theo dõi gần nơi dữ liệu thay đổi | Phụ thuộc database, cấu hình và cách truyền ngữ cảnh từ ứng dụng |
| Event sourcing | Dùng chuỗi event làm nguồn sự thật để xây dựng trạng thái | Là một lựa chọn kiến trúc; cần thiết kế event, tương thích schema và quá trình dựng lại trạng thái |
| Application log | Hỗ trợ chẩn đoán và tương quan xử lý | Muốn dùng làm hồ sơ lịch sử phải thiết kế thêm độ bền, cấu trúc, lưu giữ và truy vấn |

Không có lựa chọn nào tự trả lời tất cả câu hỏi chỉ nhờ tên gọi. Ví dụ, CDC có thể cho biết một cột đổi từ A sang B, nhưng database có thể chỉ thấy tài khoản kết nối dùng chung thay vì người dùng cuối.

Ngược lại, một bảng event nghiệp vụ mô tả tốt “khách yêu cầu hủy” nhưng có thể không bao phủ một script SQL thay đổi trực tiếp địa chỉ.

## 6. Xác định hợp đồng của lịch sử trước khi viết code

Một hợp đồng hữu ích nên nêu rõ:

1. **Phạm vi:** entity nào, field nào, loại thao tác nào được lưu.
2. **Kết quả được ghi nhận:** thay đổi đã commit, lần thử thao tác hay cả hai.
3. **Ngữ cảnh:** actor, thời điểm, nguồn thao tác, lý do và mã tương quan nào cần có.
4. **Thứ tự:** theo từng entity, transaction hay một luồng xử lý cụ thể.
5. **Độ bền:** dữ liệu lịch sử được commit và lưu giữ như thế nào.
6. **Cách đọc:** cần timeline, so sánh hai phiên bản hay phục dựng trạng thái ở một mốc.

Ví dụ hợp đồng hẹp nhưng rõ:

> Với mọi lần chuyển trạng thái đơn hàng qua application service và commit thành công, lưu trạng thái trước, trạng thái sau, actor, lý do và thời điểm xử lý trong cùng transaction với bản ghi đơn hàng.

Hợp đồng này chưa tuyên bố ghi mọi field của đơn hàng, mọi thao tác SQL ngoài ứng dụng hoặc mọi lần truy cập. Phạm vi cụ thể giúp thiết kế đúng và kiểm chứng được.

## 7. Ví dụ JPA: bản ghi hiện tại vẫn cần metadata audit

Ví dụ dưới đây minh họa một ứng dụng **Spring Data JPA** sử dụng Jakarta Persistence. Phần cấu hình datasource, quét entity và repository thuộc ứng dụng sử dụng ví dụ.

Các public type được đặt trong các file Java riêng. Mục tiêu là minh họa sự kết hợp giữa metadata hiện tại và lịch sử chuyển trạng thái, không phải cung cấp một ứng dụng chạy độc lập.

### 7.1. Trạng thái nghiệp vụ

~~~java
public enum OrderStatus {
    DRAFT,
    APPROVED,
    CANCELLED
}
~~~

### 7.2. Entity hiện tại

~~~java
import java.time.Instant;

import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@Table(name = "sales_order")
@EntityListeners(AuditingEntityListener.class)
public class OrderRecord {

    @Id
    @GeneratedValue
    private Long id;

    @Version
    private Long version;

    @Enumerated(EnumType.STRING)
    private OrderStatus status = OrderStatus.DRAFT;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    protected OrderRecord() {
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void changeStatus(OrderStatus next) {
        boolean allowed =
                (status == OrderStatus.DRAFT
                        && (next == OrderStatus.APPROVED
                            || next == OrderStatus.CANCELLED))
                || (status == OrderStatus.APPROVED
                        && next == OrderStatus.CANCELLED);

        if (!allowed) {
            throw new IllegalStateException(
                    "Unsupported status transition");
        }

        status = next;
    }
}
~~~

`@Version` phục vụ kiểm soát cập nhật đồng thời. Nó không tự tạo một kho chứa phiên bản cũ.

Ngay cả khi giá trị version tăng từ 5 lên 6, bản ghi hiện tại vẫn không tự chứa dữ liệu của version 5. Version cũng không phải timestamp và không cho biết người thực hiện hay lý do thay đổi.

### 7.3. Nguồn actor và thời gian

Ứng dụng cung cấp một abstraction cho danh tính đang thực hiện thao tác:

~~~java
public interface CurrentActor {

    String requireActorId();
}
~~~

Implementation phải lấy danh tính từ ngữ cảnh đã xác thực hoặc ngữ cảnh tác vụ hệ thống đáng tin cậy. Ví dụ có thể dùng `user:42` hoặc `system:order-expiry-job` theo quy ước của ứng dụng.

Không lấy `actorId` do client tự khai trong request body rồi coi đó là bằng chứng danh tính.

Cấu hình auditing minh họa:

~~~java
import java.time.Clock;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(
        auditorAwareRef = "currentAuditor",
        dateTimeProviderRef = "auditDateTimeProvider")
public class OrderAuditingConfiguration {

    @Bean
    public Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    public AuditorAware<String> currentAuditor(
            CurrentActor actor) {

        return () -> Optional.of(actor.requireActorId());
    }

    @Bean
    public DateTimeProvider auditDateTimeProvider(
            Clock clock) {

        return () -> Optional.of(clock.instant());
    }
}
~~~

Ví dụ giả định có một bean `CurrentActor` hợp lệ và một bean `Clock` phù hợp để inject. Nếu ứng dụng có nhiều clock, cần chọn dependency bằng qualifier hoặc cấu hình tương ứng.

`requireActorId()` có hợp đồng trả danh tính hợp lệ hoặc báo lỗi. Nếu ứng dụng cho phép thao tác không có actor, phải thiết kế rõ cách biểu diễn trường hợp đó thay vì âm thầm giả danh một người dùng hệ thống.

## 8. Một entity khác lưu từng lần chuyển trạng thái

Lịch sử cần một bản ghi riêng cho mỗi thay đổi trong phạm vi đã chọn:

~~~java
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_status_change")
public class OrderStatusChange {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private Long orderId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus beforeStatus;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus afterStatus;

    @Column(nullable = false)
    private String actorId;

    @Column(nullable = false)
    private Instant occurredAt;

    @Column(nullable = false, length = 1000)
    private String reason;

    private String requestId;

    protected OrderStatusChange() {
    }

    public OrderStatusChange(
            Long orderId,
            OrderStatus beforeStatus,
            OrderStatus afterStatus,
            String actorId,
            Instant occurredAt,
            String reason,
            String requestId) {

        this.orderId = orderId;
        this.beforeStatus = beforeStatus;
        this.afterStatus = afterStatus;
        this.actorId = actorId;
        this.occurredAt = occurredAt;
        this.reason = reason;
        this.requestId = requestId;
    }
}
~~~

Ở đây, `occurredAt` có nghĩa là thời điểm ứng dụng ghi nhận việc chuyển trạng thái. Nó không được định nghĩa là thời điểm database commit.

Entity lịch sử dùng giá trị actor và thời gian tường minh vì chúng là nội dung của sự kiện nghiệp vụ đang được lưu. Chỉ gắn `@CreatedDate` lên một bảng lịch sử không tự xác định được trạng thái trước, trạng thái sau hoặc lý do.

`orderId` được biểu diễn như một định danh scalar để ví dụ không vô tình gắn vòng đời lịch sử với cascade xóa của entity hiện tại. Trong thiết kế thực tế, vẫn phải quyết định rõ foreign key, chính sách xóa và khả năng đọc lịch sử sau khi bản ghi chính bị xóa.

Không có setter công khai giúp hạn chế sửa nhầm qua model này, nhưng chưa tạo ra bảo đảm bất biến ở database. Quyền ghi, API và chính sách lưu giữ vẫn cần phù hợp với yêu cầu lịch sử.

## 9. Ghi trạng thái và lịch sử trong cùng transaction

Repository minh họa:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderRecord, Long> {
}
~~~

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderStatusChangeRepository
        extends JpaRepository<OrderStatusChange, Long> {
}
~~~

Application service thực hiện một thay đổi và lưu thông tin tương ứng:

~~~java
import java.time.Clock;
import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final OrderStatusChangeRepository changes;
    private final CurrentActor currentActor;
    private final Clock clock;

    public OrderService(
            OrderRepository orders,
            OrderStatusChangeRepository changes,
            CurrentActor currentActor,
            Clock clock) {

        this.orders = orders;
        this.changes = changes;
        this.currentActor = currentActor;
        this.clock = clock;
    }

    @Transactional
    public void changeStatus(
            Long orderId,
            OrderStatus target,
            String reason,
            String requestId) {

        Objects.requireNonNull(target, "target");

        if (reason == null || reason.isBlank()
                || reason.length() > 1000) {
            throw new IllegalArgumentException(
                    "A reason of 1 to 1000 characters is required");
        }

        String actorId = currentActor.requireActorId();
        if (actorId == null || actorId.isBlank()) {
            throw new IllegalStateException(
                    "An authenticated actor is required");
        }

        OrderRecord order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found"));

        OrderStatus before = order.getStatus();

        if (before == target) {
            return;
        }

        order.changeStatus(target);

        // Flush kiểm tra việc cập nhật và optimistic locking.
        // Transaction tại đây vẫn chưa commit.
        orders.flush();

        changes.save(new OrderStatusChange(
                orderId,
                before,
                target,
                actorId,
                clock.instant(),
                reason,
                requestId));
    }
}
~~~

Ví dụ giả định các repository dùng cùng database và cùng transaction manager, service được gọi qua cơ chế transaction của Spring, và kiểm tra quyền nghiệp vụ đã được áp dụng tại ranh giới phù hợp của ứng dụng.

`OrderRecord` được tải trong transaction và đang được JPA quản lý. Việc đổi field được ghi qua dirty checking; không cần gọi lại `save` chỉ để làm entity đang managed trở nên managed.

### 9.1. Điều gì được bảo đảm bởi thiết kế transaction này?

Nếu transaction commit thành công, cập nhật trạng thái và bản ghi lịch sử được lưu cùng nhau trong phạm vi database đó.

Nếu việc lưu lịch sử thất bại và transaction rollback, cập nhật trạng thái trong cùng transaction cũng phải rollback. Một lần `flush()` thành công trước đó không biến cập nhật thành dữ liệu đã commit độc lập.

Nếu optimistic locking phát hiện xung đột, transaction thay đổi này không được coi là một thay đổi thành công. Lịch sử của transaction bị rollback cũng không được xuất hiện như một thay đổi đã commit.

Những kết luận trên phụ thuộc việc transaction thực sự được cấu hình đúng và lỗi không bị xử lý theo cách làm thay đổi quy tắc rollback. Chúng không tự mở rộng sang một database thứ hai hoặc một lời gọi mạng.

### 9.2. Timestamp lịch sử có bằng lastModifiedAt không?

Không nhất thiết. Auditing lấy thời gian ở điểm lifecycle của nó; service lấy thời gian khi tạo bản ghi lịch sử. Cùng dùng một `Clock` không có nghĩa hai lần đọc trả cùng một Instant.

Nếu nghiệp vụ cần một timestamp chung cho cả thay đổi và metadata, phải thiết kế nguồn thời gian theo phạm vi thao tác và nối nó vào đúng các thành phần sử dụng. Không nên mặc định có sự bằng nhau tuyệt đối.

### 9.3. Những gì ví dụ chủ động quy định

- Chỉ ghi lịch sử **chuyển trạng thái**.
- Gọi lại với trạng thái hiện tại không tạo bản ghi lịch sử mới.
- Chuyển trạng thái không hợp lệ phát sinh lỗi.
- `requestId` dùng để tương quan xử lý; chưa được thiết kế thành khóa idempotency.
- Danh tính actor phải ổn định trong ngữ cảnh một thao tác.

Nếu muốn ghi cả các lần yêu cầu trùng, các lần bị từ chối hoặc các lần retry, cần một mô hình ghi nhận phù hợp với các kết quả đó. Không nên trộn chúng với các thay đổi đã commit mà thiếu field phân biệt.

## 10. Lịch sử phải bao phủ các đường ghi đã cam kết

Một application service đúng chưa đủ nếu các đường khác vẫn có thể thay đổi dữ liệu ngoài hợp đồng.

| Đường thay đổi | Câu hỏi cần đặt ra |
| --- | --- |
| API thông thường | Có đi qua service ghi lịch sử không? |
| Tác vụ nền | Có actor hệ thống và cùng quy tắc lịch sử không? |
| Import hoặc đồng bộ dữ liệu | Có phân biệt thời điểm sự kiện gốc với thời điểm nhập không? |
| Bulk update | Có bỏ qua entity auditing và logic ghi lịch sử của service không? |
| Native SQL hoặc driver trực tiếp | Cơ chế nào ghi nhận những thay đổi này? |
| Migration hoặc sửa dữ liệu vận hành | Có lưu mục đích, người thực hiện và phạm vi thay đổi theo yêu cầu không? |
| Xóa dữ liệu | Lịch sử có còn tồn tại và có đủ dữ liệu cần đọc lại không? |

Ví dụ, nếu một bulk update chuyển hàng nghìn đơn sang `CANCELLED` mà không đi qua `OrderService`, bảng `order_status_change` trong ví dụ không tự được điền.

Có thể chọn hạn chế các đường ghi, mở rộng service ghi lịch sử, hoặc bổ sung cơ chế ở ORM/database theo nhu cầu. Điều cần giữ là một hợp đồng có thể kiểm chứng cho toàn bộ phạm vi đã hứa.

### 10.1. Xóa mềm và xóa cứng

Xóa mềm giữ lại bản ghi hiện tại với một dấu hiệu như `deleted = true`. Nếu dấu hiệu đó bị bật rồi tắt nhiều lần, chỉ giữ giá trị hiện tại vẫn không cho biết toàn bộ chuỗi xóa và khôi phục.

Xóa cứng loại bỏ bản ghi chính. Nếu lịch sử bị cascade delete cùng bản ghi đó, hệ thống có thể mất đúng thông tin cần tra cứu sau khi xóa.

Muốn đọc lại trạng thái trước xóa, chỉ lưu một event `DELETE` với ID có thể chưa đủ. Cần xác định phải giữ những field nào, snapshot nào hoặc revision nào theo hợp đồng và thời hạn lưu giữ.

## 11. “Đầy đủ” còn phụ thuộc mức chi tiết

### 11.1. Lưu snapshot

Mỗi lần ghi lưu một ảnh chụp của các field được theo dõi.

Ưu điểm là đọc một phiên bản tương đối trực tiếp. Đổi lại, dữ liệu có thể lặp lại nhiều và schema lịch sử phải được hiểu khi model thay đổi.

Một snapshot không chứa địa chỉ sẽ không giúp phục dựng địa chỉ cũ, dù các field khác được lưu đầy đủ.

### 11.2. Lưu phần thay đổi

Mỗi bản ghi lưu field đã thay đổi và giá trị trước, sau.

~~~text
entityId = 501
field    = shippingAddress
before   = Address A
after    = Address B
~~~

Cách này mô tả khác biệt trực tiếp, nhưng cần quy tắc cho null, collection, giá trị bị che, thay đổi kiểu dữ liệu và thứ tự áp dụng.

Chỉ so sánh object trước và sau ở một lớp không có đủ ngữ cảnh có thể ghi nhận sai hoặc thiếu thay đổi, nhất là với quan hệ và giá trị được database sinh ra.

### 11.3. Lưu event nghiệp vụ

Ví dụ `OrderApproved`, `ShippingAddressChanged`, `OrderCancelled` diễn tả ý nghĩa hành động.

Event có thể chứa lý do và ngữ cảnh mà một phép so sánh cột không suy ra được. Tuy nhiên, event chỉ phục dựng được những gì hợp đồng dữ liệu của nó cho phép.

Ghi một số event bên cạnh bảng hiện tại chưa tự biến hệ thống thành event sourcing. Với event sourcing, chuỗi event được thiết kế làm nguồn sự thật; trạng thái được dựng từ chuỗi đó theo các quy tắc tương ứng.

### 11.4. Một transaction có thể chứa nhiều thay đổi

Giả sử trong một transaction, code đổi một field từ A sang B rồi từ B sang C trước khi persistence thực hiện ghi cuối cùng.

- Một cơ chế theo dõi trạng thái được lưu có thể chỉ quan sát A sang C.
- Logic ghi event ở từng bước có thể lưu cả A sang B và B sang C.

Không nên yêu cầu hai mô hình tự có cùng mức chi tiết. Cần quyết định hệ thống quan tâm các bước nghiệp vụ được chấp nhận hay chỉ trạng thái bền vững cuối cùng của transaction.

## 12. Actor, thời gian và thứ tự là ba khái niệm khác nhau

### 12.1. Danh tính ổn định

Lưu `actorId` ổn định thường phù hợp hơn việc chỉ lưu tên hiển thị. Tên có thể đổi hoặc không còn tồn tại sau này.

Nếu cần tái hiện tên tại thời điểm thao tác, có thể lưu thêm một snapshot tên theo chính sách dữ liệu. Không nên chỉ dựa vào join với hồ sơ người dùng hiện tại rồi coi đó là thông tin lịch sử tại thời điểm xảy ra sự kiện.

### 12.2. Các loại thời gian

Phân biệt:

- **Thời gian sự kiện nghiệp vụ:** hành động gốc được xác định là xảy ra lúc nào.
- **Thời gian xử lý:** ứng dụng tiếp nhận hoặc xử lý hành động lúc nào.
- **Thời gian lưu nhận:** hệ thống lịch sử lưu được bản ghi lúc nào.
- **Thời gian commit:** transaction hoàn tất lúc nào theo cơ chế liên quan.

Với dữ liệu nhập trễ từ hệ thống khác, các mốc này có thể cách xa nhau. Một field `timestamp` không có định nghĩa sẽ gây nhầm khi truy vấn timeline.

### 12.3. Timestamp không phải thứ tự duy nhất

Hai thay đổi có thể có cùng timestamp do độ chính xác lưu trữ. Đồng hồ ở các máy cũng có thể lệch hoặc được điều chỉnh.

Vì vậy, không dùng riêng `lastModifiedAt` hoặc `occurredAt` để chứng minh thứ tự tuyệt đối của mọi thay đổi.

Nếu cần thứ tự theo từng entity, có thể thiết kế sequence hoặc revision tương ứng và xử lý đồng thời rõ ràng. Một ID được sinh ở database có thể giúp phân biệt bản ghi, nhưng không nên tự suy thứ tự commit toàn cục chỉ từ giá trị ID.

`@Version` hỗ trợ phát hiện cập nhật đồng thời trên entity theo cơ chế của store. Muốn dùng version làm thông tin tương quan với lịch sử, phải lưu và kiểm chứng quy tắc ánh xạ đó một cách tường minh.

## 13. Đưa lịch sử sang hệ thống khác cần xử lý ranh giới commit

Giả sử ứng dụng cập nhật database rồi gửi một thông điệp sang hệ thống lưu lịch sử bên ngoài:

~~~text
1. Cập nhật đơn hàng.
2. Commit database.
3. Gửi thông điệp lịch sử.
~~~

Nếu tiến trình dừng giữa bước 2 và 3, dữ liệu hiện tại đã đổi nhưng thông điệp chưa được gửi.

Đổi thứ tự gửi trước commit lại có rủi ro hệ thống bên ngoài nhận một thay đổi mà transaction chính sau đó rollback.

Một callback sau commit giúp chọn thời điểm xử lý, nhưng tự nó không tạo ra một bản ghi giao việc bền vững để phục hồi khi tiến trình lỗi.

Mẫu **transactional outbox** giải quyết ranh giới này bằng cách lưu dữ liệu hiện tại và bản ghi cần phát trong cùng local transaction. Một tiến trình riêng đọc outbox rồi gửi đi.

Các điểm vẫn phải thiết kế:

- Retry khi gửi thất bại.
- Nhận diện thông điệp trùng bằng event ID hoặc cơ chế tương ứng.
- Thứ tự cần giữ theo entity hoặc luồng.
- Theo dõi độ trễ và các bản ghi chưa được xử lý.
- Khả năng đọc lịch sử khi hệ thống nhận đang cập nhật chậm.

Outbox không tự bảo đảm việc gửi và xử lý chỉ xảy ra đúng một lần ở mọi thành phần. Consumer cần có chiến lược idempotency phù hợp.

Nếu chỉ cần lịch sử trong cùng database, không nhất thiết phải thêm một pipeline thông điệp. Chọn ranh giới lưu trữ theo nhu cầu thực tế.

## 14. Bất biến, sửa sai và dữ liệu nhạy cảm

Một bảng được quy ước chỉ thêm bản ghi giúp giữ diễn biến, nhưng quy ước trong Java chưa ngăn được người có quyền SQL sửa hoặc xóa trực tiếp.

Tùy yêu cầu, cần kết hợp quyền truy cập, hạn chế API cập nhật lịch sử, kiểm soát vận hành và chính sách lưu giữ. Không nên gọi dữ liệu là “không thể bị can thiệp” chỉ vì entity không có setter.

Nếu lịch sử ghi sai một chi tiết nghiệp vụ, có thể cần một bản ghi hiệu chỉnh tham chiếu đến bản ghi cũ, thay vì sửa âm thầm rồi làm mất dấu vết sửa sai. Quy tắc cụ thể phụ thuộc hợp đồng của hệ thống.

Không tự động sao chép mọi field vào lịch sử. Ví dụ, không cần giữ mật khẩu, token hoặc bí mật xác thực cũ để chứng minh người dùng đã thay đổi cấu hình.

Với dữ liệu cá nhân, cần xác định field được lưu, quyền xem, thời hạn lưu giữ và cách xử lý yêu cầu xóa hoặc ẩn dữ liệu. Một bảng lịch sử nhân bản toàn bộ dữ liệu chính sẽ mở rộng cả phạm vi dữ liệu cần quản lý.

## 15. Đọc lịch sử khác với đọc entity hiện tại

Repository của entity hiện tại phục vụ trạng thái đang có hiệu lực. Repository lịch sử phục vụ timeline hoặc dữ liệu ở các mốc trước đó.

### 15.1. Phân trang và sắp xếp

Khi hiển thị timeline, cần một thứ tự xác định, chẳng hạn theo `occurredAt` và một khóa phân biệt phù hợp.

Chỉ sort theo timestamp có thể khiến các dòng cùng mốc xuất hiện theo thứ tự không ổn định. Với lịch sử lớn và có bản ghi mới liên tục, lựa chọn phân trang theo offset hay cursor phải phù hợp với yêu cầu đọc.

Thứ tự hiển thị ổn định giúp giao diện nhất quán; nó vẫn không tự là bằng chứng thứ tự commit tuyệt đối.

### 15.2. Projection

Một projection cho timeline có thể chỉ lấy action, actor, thời gian và phần mô tả thay đổi để giảm lượng dữ liệu trả về.

Projection chỉ chọn dữ liệu đã tồn tại trong kho nguồn. Nó không tạo lại các phiên bản cũ đã bị ghi đè trên bản ghi hiện tại.

Tương tự, derived query hoặc Query by Example không thể tìm một trạng thái trước đây nếu hệ thống chưa từng lưu trạng thái đó trong một nguồn lịch sử có thể truy vấn.

### 15.3. Truy vấn “trạng thái tại thời điểm T”

Một danh sách các lần đổi trạng thái có thể đủ để xác định trạng thái theo hợp đồng của timeline đó. Nó chưa chắc đủ để dựng toàn bộ địa chỉ, giá tiền và các dòng hàng tại T.

Muốn phục dựng một entity hoàn chỉnh, cần baseline, dữ liệu thay đổi bao phủ đủ field, thứ tự áp dụng và quy tắc khi schema phát triển. Nếu dùng revision hoặc snapshot, cũng cần hiểu phạm vi dữ liệu mà cơ chế đó thực sự lưu.

## 16. Áp dụng đúng giới hạn của từng store

Spring Data Commons cung cấp abstraction chung, nhưng không phải một hệ thống lịch sử dữ liệu dùng thống nhất cho mọi store.

| Phạm vi | Điều cần kiểm tra |
| --- | --- |
| Spring Data JPA | Listener auditing, flush, transaction, optimistic locking và đường bulk/native update |
| Spring Data MongoDB | Callback auditing, khả năng transaction trong cấu hình đang dùng và cách lưu lịch sử giữa các document |
| Spring Data JDBC | Ranh giới aggregate, đường ghi và khả năng lưu lịch sử trong transaction tương ứng |
| Spring Data R2DBC | Callback reactive, transaction reactive và việc truyền actor trong ngữ cảnh xử lý |
| Store khác | Auditing có được hỗ trợ ở đường ghi đang dùng không; khả năng transaction và lịch sử cụ thể là gì |

Ví dụ JPA dùng `orders.flush()` ở trên không phải một công thức chuyển nguyên xi sang mọi module.

Trong xử lý reactive, cũng không nên mặc định danh tính nằm trong một `ThreadLocal` sẽ luôn có mặt ở điểm lấy auditor. Ngữ cảnh actor và việc thực thi pipeline phải được thiết kế theo hạ tầng reactive tương ứng.

## 17. Các tình huống cần kiểm chứng

Bảng sau là tiêu chí thiết kế kiểm thử cho cơ chế lịch sử, không phải báo cáo rằng các kiểm thử đã được chạy:

| Tình huống | Kết quả cần kiểm chứng theo hợp đồng mẫu |
| --- | --- |
| Một lần chuyển trạng thái hợp lệ commit thành công | Có trạng thái mới và đúng một bản ghi lịch sử tương ứng |
| Hai lần chuyển trạng thái thành công nối tiếp | Giữ được cả hai bản ghi lịch sử, metadata hiện tại phản ánh lần cuối |
| Lưu lịch sử thất bại | Transaction rollback, trạng thái chính không được commit riêng |
| Cập nhật entity xung đột version | Không có lịch sử đã commit cho transaction cập nhật thất bại |
| Yêu cầu giữ nguyên trạng thái | Không thêm bản ghi theo quy tắc no-op của ví dụ |
| Chuyển trạng thái không hợp lệ | Không có thay đổi trạng thái đã commit; nhật ký lần thử tùy hợp đồng riêng |
| Xóa hoặc khôi phục bản ghi | Lịch sử được giữ và truy cập theo chính sách đã xác định |
| Tác vụ nền thực hiện thay đổi | Actor hệ thống được ghi đúng, không mượn danh người dùng cũ |
| Đường bulk update hoặc import | Có bằng chứng nó nằm trong hoặc ngoài phạm vi lịch sử đã công bố |
| Hai bản ghi lịch sử cùng timestamp | Truy vấn timeline có thứ tự phân biệt theo thiết kế |
| Outbox gửi lại một event | Consumer xử lý trùng theo quy tắc idempotency |

Đối với transaction và optimistic locking, cần kiểm chứng qua đường persistence thực tế phù hợp. Một mock repository chỉ trả object không đủ chứng minh tính nguyên tử của các lần ghi trong database.

Để kiểm thử thời gian, có thể inject clock xác định. Tuy nhiên, clock chỉ kiểm soát những thành phần thực sự sử dụng nó; không tự kiểm soát timestamp do database hoặc hệ thống bên ngoài sinh ra.

## 18. Những kết luận dễ nhầm

**“Có bốn annotation auditing là có lịch sử đầy đủ.”**

Các annotation cung cấp metadata tạo và sửa. Muốn giữ các giá trị trước và chuỗi thay đổi, cần một cơ chế lịch sử riêng phù hợp.

**“Version tăng nên có thể đọc lại version cũ.”**

Version trên entity hiện tại phục vụ cơ chế cập nhật đồng thời. Đọc lại phiên bản cũ cần dữ liệu lịch sử đã được lưu.

**“Có log là luôn biết dữ liệu trước đây.”**

Chỉ biết được nếu log thực sự chứa đủ dữ liệu, được lưu bền vững, giữ đủ lâu và có thể truy vấn theo hợp đồng cần dùng.

**“Sử dụng Envers hoặc CDC thì mọi loại thay đổi và mọi lý do đều tự có.”**

Phải đối chiếu phạm vi theo dõi, đường ghi, cấu hình và dữ liệu ngữ cảnh. Lý do nghiệp vụ không tự xuất hiện từ một thay đổi cột.

**“Chỉ thêm bảng history vào service là toàn hệ thống đã được bao phủ.”**

Cần kiểm tra cả tác vụ nền, import, bulk update, SQL trực tiếp, migration và các đường xóa trong phạm vi đã cam kết.

**“Metadata sửa gần nhất không còn cần khi đã có history.”**

Metadata vẫn hữu ích cho màn hình danh sách, truy vấn vận hành và hiển thị nhanh. Lịch sử phục vụ các câu hỏi về diễn biến, phiên bản và ngữ cảnh thay đổi.

## 19. Tự kiểm tra kiến thức

1. Một đơn hàng có `lastModifiedBy = user:42`. Có thể suy ra mọi người từng sửa đơn hàng không? Vì sao?
2. Nếu chỉ lưu các lần chuyển trạng thái, hệ thống có phục dựng được địa chỉ giao hàng cũ không?
3. Tại sao `@Version` không thay thế bảng revision hoặc lịch sử?
4. Nếu cập nhật trạng thái commit trước rồi mới gửi thông điệp lịch sử, điểm mất dữ liệu nằm ở đâu?
5. Vì sao lỗi lưu lịch sử trong cùng transaction cần làm thay đổi chính rollback theo hợp đồng mẫu?
6. Một thao tác bị từ chối cần nằm trong lịch sử trạng thái đã commit hay một loại nhật ký khác?
7. Tại sao timestamp giống nhau không nhất thiết là hai bản ghi trùng?
8. Khi chuyển từ JPA sang một store khác, những giả định nào về auditing và transaction phải được kiểm tra lại?

Điểm cần giữ khi thiết kế repository và auditing là xác định câu hỏi dữ liệu trước: metadata hiện tại cho biết dấu vết tạo và sửa gần nhất; lịch sử cần lưu riêng những thay đổi mà hệ thống cam kết có thể giải thích hoặc phục dựng về sau.
