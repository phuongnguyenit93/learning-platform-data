# EntityListener, Bean Validation và giới hạn xử lý trong callback

## 1. Lifecycle callback trong JPA

Entity có vòng đời được quản lý bởi persistence context: được tạo mới, lưu, cập nhật, xóa và tải từ database. JPA cung cấp lifecycle callback để chạy một đoạn xử lý nhỏ tại các thời điểm đó. Callback có thể được khai báo trực tiếp trong Entity hoặc tách thành một lớp listener bằng `@EntityListeners`.

Các annotation callback thường dùng:

| Callback | Thời điểm |
| --- | --- |
| `@PrePersist` | Trước khi Entity được insert |
| `@PostPersist` | Sau khi thao tác insert đã được thực hiện |
| `@PreUpdate` | Trước khi Entity được update |
| `@PostUpdate` | Sau khi thao tác update đã được thực hiện |
| `@PreRemove` | Trước khi Entity bị xóa |
| `@PostRemove` | Sau khi thao tác delete đã được thực hiện |
| `@PostLoad` | Sau khi Entity được tải hoặc refresh từ database |

`@PostPersist`, `@PostUpdate` và `@PostRemove` không có nghĩa transaction đã commit. Transaction vẫn có thể rollback sau callback. Đây là điểm quan trọng khi quyết định có được gửi email, gọi API hoặc phát message từ callback hay không.

## 2. Entity callback và EntityListener khác nhau thế nào?

Callback khai báo trực tiếp trong Entity là phương án đơn giản cho xử lý ngắn và chỉ liên quan đến chính Entity đó:

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    private Instant updatedAt;

    @PreUpdate
    void updateTimestamp() {
        updatedAt = Instant.now();
    }
}
```

Khi logic được dùng chung hoặc muốn tách trách nhiệm khỏi Entity, có thể tạo listener:

```java
@Entity
@EntityListeners(PurchaseOrderAuditListener.class)
public class PurchaseOrder {
    @Id
    private Long id;

    private Instant createdAt;
    private Instant updatedAt;

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }

    public void setUpdatedAt(Instant updatedAt) {
        this.updatedAt = updatedAt;
    }
}
```

```java
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import java.time.Instant;

public class PurchaseOrderAuditListener {
    @PrePersist
    public void beforeInsert(PurchaseOrder order) {
        Instant now = Instant.now();
        order.setCreatedAt(now);
        order.setUpdatedAt(now);
    }

    @PreUpdate
    public void beforeUpdate(PurchaseOrder order) {
        order.setUpdatedAt(Instant.now());
    }
}
```

Phương thức callback trong Entity có dạng `void method()` không tham số. Phương thức trong EntityListener có dạng `void method(EntityType entity)` hoặc nhận `Object`. Listener cần constructor không tham số theo hợp đồng JPA; các callback method nên là instance method `void` và không khai báo tham số bổ sung. Ví dụ trên dùng kiểu cụ thể `PurchaseOrder` để dễ đọc.

Listener có thể gắn trên Entity hoặc mapped superclass. Khi dùng nhiều listener, thứ tự callback có quy tắc theo cấu hình listener và hierarchy; không nên dựa vào thứ tự ngẫu nhiên giữa các listener để tạo phụ thuộc nghiệp vụ.

## 3. Callback phù hợp với loại công việc nào?

Callback phù hợp với các tác vụ kỹ thuật ngắn, xác định và gắn trực tiếp với trạng thái của chính Entity:

- Gán timestamp `createdAt` khi tạo mới.
- Cập nhật `updatedAt` khi có thay đổi.
- Chuẩn hóa một trường đơn giản trước khi ghi, nếu quy tắc đó không cần truy cập dữ liệu khác.
- Tính giá trị dẫn xuất đơn giản từ các trường hiện có của cùng Entity.
- Ghi nhận một giá trị kỹ thuật cục bộ mà mọi đường persist/update đều phải tuân theo.

Callback không phải nơi điều phối nghiệp vụ. Không nên dùng nó để truy vấn repository, kiểm tra hạn mức bằng cách đọc Entity khác, gọi dịch vụ từ xa, gửi email, publish message, ghi file hoặc thực hiện tác vụ lâu. Những công việc đó cần chạy ở service/application layer hoặc qua cơ chế sự kiện phù hợp.

## 4. Giới hạn quan trọng của callback

JPA đặt ra giới hạn để callback không làm thay đổi khó dự đoán trạng thái persistence context. Trong callback, chỉ nên thay đổi trạng thái không phải quan hệ của chính Entity đang được callback xử lý.

Các giới hạn cần nhớ:

1. Không gọi `EntityManager` hoặc `Query` để truy vấn hay thay đổi dữ liệu khác từ callback.
2. Không truy cập các instance Entity khác trong persistence context.
3. Không thay đổi quan hệ với Entity khác, chẳng hạn thêm/xóa phần tử trong collection hoặc thay đổi thuộc tính ManyToOne.
4. Không thực hiện logic phụ thuộc vào thứ tự flush, thứ tự callback hoặc việc một thao tác SQL đã được commit.
5. Không thực hiện I/O, gọi HTTP, gửi email hoặc publish message trực tiếp trong callback.

JPA cho phép callback thay đổi trạng thái không phải quan hệ của chính Entity đang được xử lý, ví dụ cập nhật `updatedAt`. Hãy giữ callback ngắn, không có side effect bên ngoài và không phụ thuộc vào truy vấn khác.

Nếu callback ném unchecked exception, thao tác persistence có thể thất bại và transaction đang tham gia sẽ bị rollback theo quy tắc transaction. Không nuốt lỗi rồi tiếp tục như thể Entity đã lưu thành công; hãy để lỗi được xử lý ở tầng gọi phù hợp.

## 5. Vì sao không gửi message ở @PostPersist?

`@PostPersist` chạy sau khi lệnh insert đã được thực hiện, nhưng transaction chưa chắc đã commit. Nếu callback gửi email hoặc message ngay lúc này, database có thể rollback sau đó trong khi hệ thống bên ngoài đã nhận thông báo về một bản ghi không tồn tại.

Ví dụ luồng không an toàn:

```text
persist Entity
    -> @PostPersist
        -> gửi message ra broker
    -> transaction rollback

Broker đã nhận message nhưng dữ liệu database không được commit.
```

Nếu cần thực hiện side effect sau khi commit, service có thể publish một application event trong transaction và xử lý bằng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. Listener này chạy sau khi transaction commit thành công:

```java
public record PurchaseOrderCreated(Long orderId) {
}
```

```java
@Service
public class PurchaseOrderService {
    private final ApplicationEventPublisher events;

    public PurchaseOrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public Long create(PurchaseOrder order) {
        repository.save(order);
        events.publishEvent(new PurchaseOrderCreated(order.getId()));
        return order.getId();
    }
}
```

```java
@Component
public class PurchaseOrderNotificationListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(PurchaseOrderCreated event) {
        // Gửi thông báo hoặc gọi dịch vụ ngoài sau khi transaction commit.
    }
}
```

Đây là ví dụ minh họa; cần inject repository và các dependency thực tế. `AFTER_COMMIT` tránh gửi thông báo khi transaction rollback, nhưng event trong bộ nhớ không phải hàng đợi bền vững. Nếu tiến trình dừng ngay sau commit trước khi listener hoàn tất, thông báo có thể bị mất. Với tích hợp cần độ tin cậy cao, dùng transactional outbox: ghi event vào bảng outbox trong cùng transaction với dữ liệu nghiệp vụ, sau đó một worker đọc và gửi event có retry/idempotency.

## 6. Bean Validation là gì?

Jakarta Bean Validation cung cấp annotation để mô tả các ràng buộc trên dữ liệu. Một số constraint thường dùng:

| Annotation | Ý nghĩa |
| --- | --- |
| `@NotNull` | Giá trị không được null |
| `@NotBlank` | Chuỗi không null và phải có ký tự không phải khoảng trắng |
| `@NotEmpty` | Chuỗi/collection/map không được rỗng |
| `@Size(min, max)` | Giới hạn độ dài hoặc số phần tử |
| `@Positive` | Số phải lớn hơn 0 |
| `@PositiveOrZero` | Số phải lớn hơn hoặc bằng 0 |
| `@Email` | Giá trị phải phù hợp định dạng email mà provider kiểm tra |

Ví dụ đặt constraint trên Entity:

```java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Size(max = 40)
    @Column(name = "order_number", nullable = false, length = 40)
    private String orderNumber;

    @NotNull
    @Positive
    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount;
}
```

`@NotBlank` và `@Size` là constraint của Bean Validation. `@Column(nullable = false, length = 40)` là metadata mapping/schema của JPA. Hai loại annotation giải quyết các tầng khác nhau: Bean Validation kiểm tra object trước khi ghi; database constraint bảo vệ dữ liệu ở tầng lưu trữ.

`@Column(nullable = false)` không tự thay thế `@NotNull`, và `@NotNull` cũng không tự tạo NOT NULL constraint trong schema. Với migration-managed schema, phải tạo constraint bằng migration.

## 7. Bean Validation được kích hoạt khi nào trong JPA?

Khi có Bean Validation provider trên classpath và JPA validation mode cho phép, JPA tích hợp validation trong các lifecycle event. Ở chế độ mặc định `AUTO`, provider thường được sử dụng nếu có sẵn. Có thể thêm dependency `spring-boot-starter-validation` trong Spring Boot để có implementation như Hibernate Validator.

Thông thường, nhóm `jakarta.validation.groups.Default` được kiểm tra ở các thời điểm pre-persist và pre-update. Vì vậy khi persist Entity mới hoặc flush một Entity có thay đổi, constraint có thể được kiểm tra trước thao tác insert/update. JPA không mặc định validate trước remove.

Validation mode có các giá trị:

- `AUTO`: tự dùng Bean Validation nếu provider có sẵn.
- `CALLBACK`: yêu cầu tích hợp validation callback.
- `NONE`: tắt tích hợp validation của JPA.

Có thể cấu hình rõ trong persistence unit properties nếu dự án cần:

```yaml
spring:
  jpa:
    properties:
      jakarta.persistence.validation.mode: callback
```

Không cần đặt `CALLBACK` trong mọi ứng dụng. Với Spring Boot, dependency validation và chế độ mặc định AUTO thường đủ. Nếu dự án đã cấu hình validation groups riêng, cần kiểm tra đúng group được kích hoạt ở từng lifecycle event.

Khi constraint vi phạm trong lúc JPA validation, provider ném `jakarta.validation.ConstraintViolationException`; thao tác persist/update không thành công và transaction thường bị rollback. Hãy bắt lỗi ở tầng service/API để chuyển thành phản hồi phù hợp, không tiếp tục coi dữ liệu đã lưu.

## 8. Validation ở API và validation khi persist là hai lớp

Ở tầng HTTP, validate request DTO giúp trả lỗi sớm, gần với đầu vào người dùng:

```java
public record CreatePurchaseOrderRequest(
    @NotBlank @Size(max = 40) String orderNumber,
    @NotNull @Positive BigDecimal totalAmount
) {
}
```

```java
@RestController
@RequestMapping("/purchase-orders")
public class PurchaseOrderController {
    private final PurchaseOrderService service;

    public PurchaseOrderController(PurchaseOrderService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreatePurchaseOrderRequest request) {
        service.create(request);
        return ResponseEntity.accepted().build();
    }
}
```

`@Valid` kích hoạt kiểm tra DTO ở tầng web. Nếu DTO có object lồng nhau, đặt `@Valid` trên thuộc tính lồng để cascade validation. Service cũng có thể dùng `@Validated` và constraint trên tham số phương thức khi cần method validation.

Validation DTO và validation Entity có mục tiêu khác nhau. DTO kiểm tra hợp đồng API; Entity kiểm tra trạng thái được lưu dù thao tác đến từ REST, message consumer, batch import hay job. Không nên chỉ dựa vào controller validation vì các đường ghi khác có thể bỏ qua controller.

## 9. @Valid không phải cascade của JPA

Hai cơ chế có tên gần nhau nhưng độc lập:

| Cơ chế | Mục đích |
| --- | --- |
| Bean Validation `@Valid` | Kiểm tra đệ quy các object liên quan theo constraint |
| JPA `cascade = PERSIST/MERGE/REMOVE/...` | Lan truyền thao tác persistence tới Entity liên quan |

Ví dụ, đặt `@Valid` trên quan hệ có thể khiến constraint của Entity liên quan được kiểm tra khi validation cascade diễn ra. Nó không tự persist Entity đó. Ngược lại, `cascade = PERSIST` không có nghĩa các constraint của mọi object lồng nhau sẽ tự được kiểm tra nếu không có cấu hình cascade validation phù hợp.

Không dùng `@Valid` như cách thay thế cascade persist, và không dùng `CascadeType.ALL` như cách thay thế Bean Validation.

## 10. EntityListener và Bean Validation phối hợp thế nào?

EntityListener có thể chuẩn hóa hoặc gán giá trị kỹ thuật trước khi ghi; Bean Validation kiểm tra các constraint theo lifecycle validation. Tuy nhiên, không nên thiết kế correctness phụ thuộc vào thứ tự giữa callback tự viết và Bean Validation listener nếu thứ tự đó không được kiểm soát rõ.

Ví dụ, listener có thể gán timestamp:

```java
public class PurchaseOrderTimestampListener {
    @PrePersist
    public void beforeInsert(PurchaseOrder order) {
        Instant now = Instant.now();
        order.setCreatedAt(now);
        order.setUpdatedAt(now);
    }

    @PreUpdate
    public void beforeUpdate(PurchaseOrder order) {
        order.setUpdatedAt(Instant.now());
    }
}
```

Nếu một trường được tạo trong callback là bắt buộc, hãy đảm bảo giá trị được khởi tạo chắc chắn trước khi validation chạy; có thể khởi tạo trong constructor/factory hoặc service thay vì phụ thuộc vào thứ tự callback. Không dùng callback để truy vấn dữ liệu khác nhằm quyết định giá trị.

## 11. Giới hạn của validation và callback với bulk DML

Bulk JPQL `UPDATE`/`DELETE` và native SQL chạy trực tiếp trên database, bỏ qua vòng đời từng Entity. Vì vậy chúng không kích hoạt lifecycle callback trên mỗi Entity, không chạy JPA Bean Validation cho từng hàng và không đồng bộ tự động các Entity đang nằm trong persistence context.

Ví dụ:

```java
@Modifying
@Query("update PurchaseOrder p set p.status = :status where p.id = :id")
int updateStatus(Long id, String status);
```

Đây là bulk update; `@PreUpdate`, `@PostUpdate` và validation trên Entity không được gọi cho từng hàng bị cập nhật. Nếu cần đảm bảo invariant, phải kiểm tra dữ liệu trước khi chạy bulk query, bổ sung constraint phù hợp ở database và cân nhắc clear/refresh persistence context sau thao tác.

Bulk operation thường hữu ích khi cập nhật nhiều hàng, nhưng nó bỏ qua cascade và callback của Entity. Không dùng bulk DML khi nghiệp vụ phụ thuộc vào logic được thực thi trong callback hoặc dirty checking từng Entity.

## 12. Những việc không nên làm trong callback

- Không gọi repository hoặc EntityManager để đọc/ghi Entity khác.
- Không thay đổi quan hệ hoặc collection của Entity khác trong persistence context.
- Không gọi API từ xa, gửi email, publish message hoặc ghi file.
- Không thực hiện công việc nặng, xử lý batch lớn hoặc chờ I/O.
- Không phụ thuộc vào việc `@PostPersist`/`@PostUpdate` có nghĩa transaction đã commit.
- Không giả định Spring dependency injection hoạt động trong listener theo mọi JPA provider; cần xác minh tích hợp nếu thật sự dùng injection.

Giữ callback ngắn và xác định. Logic nghiệp vụ nhiều bước thuộc service/domain layer; side effect cần sau commit dùng transactional event, còn tích hợp cần bảo đảm không mất sự kiện nên dùng outbox.

## 13. Lỗi thường gặp và cách điều tra

**Validation không chạy khi lưu Entity.** Kiểm tra `spring-boot-starter-validation`, provider có trên classpath, validation mode không phải NONE và thao tác có đi qua JPA persist/update không.

**API trả lỗi validation nhưng batch import vẫn lưu dữ liệu sai.** Batch import có thể không đi qua controller. Giữ constraint trên Entity/domain và kiểm tra cả đường import; bulk SQL vẫn cần validation riêng hoặc constraint database.

**Callback timestamp không được cập nhật.** Kiểm tra Entity có thực sự dirty và có phát sinh update không. `@PreUpdate` không phải hook chạy mỗi lần gọi setter; nó gắn với thao tác update của provider.

**Gửi message dù transaction rollback.** Không gửi từ `@PostPersist`/`@PostUpdate`; chuyển sang `AFTER_COMMIT` hoặc transactional outbox.

**Dữ liệu quan hệ sai sau callback.** Kiểm tra callback có sửa association hay truy vấn Entity khác không; chuyển logic đó sang service và cập nhật owning side đúng chỗ.

**Constraint database vẫn lỗi dù Bean Validation đã pass.** Kiểm tra race condition, constraint unique/FK/check, dữ liệu ghi từ client khác và khác biệt giữa validation rule với schema. Database constraint vẫn là lớp bảo vệ cuối cùng.

## 14. Checklist thiết kế

- Dùng callback cho tác vụ ngắn, kỹ thuật và chỉ sửa non-relationship state của Entity hiện tại.
- Dùng EntityListener khi cần tách callback khỏi Entity hoặc tái sử dụng.
- Dùng Bean Validation để kiểm tra dữ liệu ở API và khi persist/update.
- Phân biệt `@Valid` với JPA cascade.
- Đồng bộ constraint Bean Validation với NOT NULL, CHECK, UNIQUE và FK trong schema.
- Không đặt truy vấn, side effect bên ngoài hoặc xử lý nặng trong callback.
- Nhớ bulk JPQL/native DML bỏ qua callback và JPA Bean Validation.
- Dùng `AFTER_COMMIT` cho tác vụ sau commit; dùng outbox nếu cần bảo đảm giao sự kiện.

EntityListener và Bean Validation bổ sung cho nhau: listener xử lý các thay đổi kỹ thuật nhỏ theo lifecycle, còn validation bảo vệ trạng thái dữ liệu. Hiểu giới hạn callback và các đường ghi bỏ qua lifecycle giúp ứng dụng giữ dữ liệu nhất quán mà không tạo side effect khó kiểm soát.