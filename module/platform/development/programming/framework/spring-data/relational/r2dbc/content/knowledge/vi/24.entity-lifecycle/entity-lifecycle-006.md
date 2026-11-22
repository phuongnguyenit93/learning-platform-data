# Trả về thực thể mới trong callback khi mô hình bất biến

Trong Spring Data Relational R2DBC, entity callback cho phép can thiệp vào vòng đời lưu và đọc entity. Khi mô hình domain bất biến (immutable), callback không thể thay đổi trực tiếp thuộc tính của object hiện tại. Thay vào đó, callback tạo một instance mới chứa giá trị đã cập nhật rồi trả instance đó qua publisher. Spring Data tiếp tục pipeline persistence với entity được callback trả về.

Cách làm này phù hợp với Java record, lớp có field `final`, constructor đầy đủ, Lombok `@With` hoặc mô hình dùng phương thức `with...` để tạo bản sao. Điểm quan trọng là callback phải trả về publisher phát ra entity mới; chỉ tạo bản sao rồi bỏ qua giá trị trả về sẽ không thay đổi dữ liệu mà Spring Data xử lý.

## 1. Mô hình bất biến trong ứng dụng Spring Data Relational

Một object bất biến không cho phép thay đổi trạng thái sau khi được tạo. Thay vì setter như `setCreatedAt(...)`, object cung cấp constructor hoặc phương thức tạo bản sao với một giá trị mới.

Ví dụ entity mutable:

```java
public class PurchaseOrder {
    private Long id;
    private Instant createdAt;

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }
}
```

Với entity mutable, callback có thể thay đổi object hiện tại. Tuy nhiên, cách này làm trạng thái object thay đổi tại một điểm trong pipeline mà caller có thể không nhận ra.

Entity bất biến biểu diễn cùng dữ liệu bằng field không thay đổi và constructor:

```java
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        Instant createdAt,
        String createdBy
) {
}
```

Record không có setter. Khi cần gán `createdAt`, ứng dụng tạo một `PurchaseOrder` khác:

```java
PurchaseOrder updated = new PurchaseOrder(
        order.id(),
        order.orderNumber(),
        createdAt,
        order.createdBy()
);
```

Instance cũ vẫn giữ nguyên giá trị. Instance mới chứa trạng thái cần được lưu. Đây là cách làm rõ ràng cho callback và giúp tránh việc một tham chiếu đang được dùng ở nơi khác bất ngờ thay đổi.

## 2. Vì sao callback cần trả về entity mới?

Callback là một phần của chuỗi thao tác persistence. Spring Data gọi callback tại một điểm trong vòng đời, nhận entity callback phát ra rồi dùng kết quả đó cho bước tiếp theo.

Với mô hình bất biến, callback không thể gọi setter. Nó phải:

1. Nhận entity hiện tại.
2. Xác định giá trị cần bổ sung hoặc thay đổi.
3. Tạo instance mới bằng constructor, `with...` hoặc `copy`.
4. Trả instance mới trong `Mono`/`Publisher`.

Ví dụ về nguyên tắc:

```java
return Mono.just(entity.withCreatedAt(clock.instant()));
```

Không đủ nếu chỉ tạo bản sao mà không trả nó:

```java
entity.withCreatedAt(clock.instant());
return Mono.just(entity); // Bản sao đã tạo bị bỏ đi.
```

Vì object ban đầu không bị thay đổi, dòng code thứ hai trả lại entity cũ. Giá trị mới không đi tiếp vào pipeline mapping và persistence.

## 3. Vị trí callback trong vòng đời lưu entity

Spring Data R2DBC có các callback ở những giai đoạn khác nhau. Tên và chi tiết API cần đối chiếu với phiên bản Spring Data đang dùng, nhưng luồng khái niệm khi ghi thường như sau:

```mermaid
flowchart TD
    A[Repository save(entity)] --> B[BeforeConvert callback]
    B --> C[Convert entity to OutboundRow]
    C --> D[BeforeSave callback]
    D --> E[Execute INSERT or UPDATE]
    E --> F[Map generated values if any]
    F --> G[AfterSave callback]
    G --> H[Emit saved entity]
```

`BeforeConvertCallback` được gọi trước khi entity được chuyển thành dữ liệu ghi (`OutboundRow`). Đây thường là vị trí phù hợp để tạo một entity bất biến mới khi muốn giá trị mới được đưa vào mapping và SQL.

`BeforeSaveCallback` được gọi sau khi Spring Data đã chuyển entity thành `OutboundRow`. Callback này hữu ích khi cần xem hoặc điều chỉnh dữ liệu ghi ở mức row. Nếu thay đổi một thuộc tính trong một instance bất biến mới tại giai đoạn này, cần chú ý `OutboundRow` đã được tạo từ entity trước đó; không nên giả định chỉ trả instance mới là row sẽ tự động được ánh xạ lại. Nếu mục tiêu là thay đổi thuộc tính entity trước khi ghi, ưu tiên `BeforeConvertCallback`.

`AfterSaveCallback` chạy sau thao tác ghi. Nó có thể tạo một entity kết quả mới để phát tiếp cho caller, nhưng không thể dùng thay cho callback trước khi convert để thay đổi giá trị đã được ghi vào database.

## 4. Dùng `BeforeConvertCallback` với Java record

Giả sử mọi đơn hàng mới cần có thời điểm tạo nếu caller chưa cung cấp. Dùng `Clock` thay vì gọi trực tiếp `Instant.now()` giúp kiểm soát thời gian trong test.

Entity:

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        Instant createdAt,
        String createdBy
) {

    public PurchaseOrder withCreatedAt(Instant value) {
        return new PurchaseOrder(id, orderNumber, value, createdBy);
    }
}
```

Callback reactive:

```java
import java.time.Clock;
import org.reactivestreams.Publisher;
import org.springframework.data.relational.core.sql.SqlIdentifier;
import org.springframework.data.r2dbc.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class PurchaseOrderTimestampCallback
        implements BeforeConvertCallback<PurchaseOrder> {

    private final Clock clock;

    public PurchaseOrderTimestampCallback(Clock clock) {
        this.clock = clock;
    }

    @Override
    public Publisher<PurchaseOrder> onBeforeConvert(
            PurchaseOrder entity,
            SqlIdentifier table) {

        if (entity.createdAt() != null) {
            return Mono.just(entity);
        }

        PurchaseOrder updated = entity.withCreatedAt(clock.instant());
        return Mono.just(updated);
    }
}
```

Callback nhận entity, tạo một record mới nếu `createdAt` chưa có và phát instance đó. Nếu entity đã có thời điểm tạo, callback phát lại chính instance hiện tại. Cả hai nhánh đều phát đúng một entity khác null.

Ví dụ minh họa reactive callback của Spring Data R2DBC. Package và chữ ký callback cần khớp với phiên bản Spring Data R2DBC trong dự án; ở các phiên bản có thay đổi API, hãy dùng interface callback tương ứng nhưng giữ nguyên nguyên tắc trả về publisher chứa entity.

## 5. Cấu hình `Clock`

Đăng ký `Clock` thành bean để callback có thể inject:

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Trong production, `Clock.systemUTC()` cung cấp thời điểm hiện tại theo UTC. Trong test, có thể thay bằng `Clock.fixed(...)` để kết quả xác định:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-15T08:00:00Z"),
        ZoneOffset.UTC
);
```

Không nên tạo `Clock.systemDefaultZone()` riêng ở nhiều nơi nếu ứng dụng cần semantics UTC nhất quán. Một bean `Clock` giúp mọi callback và service dùng chung chính sách thời gian.

## 6. Dùng phương thức `with...` để tạo bản sao

Với lớp Java thông thường, có thể tự viết phương thức `with...`:

```java
public final class PurchaseOrder {

    private final Long id;
    private final String orderNumber;
    private final Instant createdAt;

    public PurchaseOrder(Long id, String orderNumber, Instant createdAt) {
        this.id = id;
        this.orderNumber = orderNumber;
        this.createdAt = createdAt;
    }

    public PurchaseOrder withCreatedAt(Instant value) {
        return new PurchaseOrder(id, orderNumber, value);
    }

    public PurchaseOrder withId(Long value) {
        return new PurchaseOrder(value, orderNumber, createdAt);
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Mỗi phương thức `with...` trả một object mới, giữ nguyên các thuộc tính khác và thay đúng thuộc tính được yêu cầu. Đây là kỹ thuật hữu ích khi callback chỉ cần thay đổi một hoặc một vài trường.

Nếu lớp có nhiều thuộc tính, việc tự viết constructor trong từng `with...` có thể dài. Có thể dùng record, Lombok `@With` hoặc một thư viện/kiểu dữ liệu immutable phù hợp với codebase. Dù dùng công cụ nào, hãy xác minh phương thức tạo bản sao giữ nguyên toàn bộ thuộc tính không thay đổi.

## 7. Dùng Lombok `@With`

Lombok có thể sinh phương thức `with...` cho field final:

```java
import lombok.With;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@With
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private final Long id;

    private final String orderNumber;

    private final Instant createdAt;

    public PurchaseOrder(Long id, String orderNumber, Instant createdAt) {
        this.id = id;
        this.orderNumber = orderNumber;
        this.createdAt = createdAt;
    }

    public Long getId() { return id; }
    public String getOrderNumber() { return orderNumber; }
    public Instant getCreatedAt() { return createdAt; }
}
```

Sau khi annotation processing chạy, Lombok sinh phương thức tương tự `withCreatedAt(Instant value)` và trả instance mới. Callback có thể dùng:

```java
PurchaseOrder updated = entity.withCreatedAt(clock.instant());
return Mono.just(updated);
```

`@With` không tự làm cho mọi thành phần của object graph bất biến. Nếu field chứa một `List` mutable, bản sao có thể vẫn chia sẻ cùng list. Hãy dùng collection immutable hoặc defensive copy nếu domain yêu cầu bất biến sâu (deep immutability).

## 8. Dùng Kotlin data class

Với Kotlin, `data class` cung cấp `copy(...)` để tạo instance mới:

```kotlin
@Table("purchase_order")
data class PurchaseOrder(
    @Id val id: Long? = null,
    val orderNumber: String,
    val createdAt: Instant? = null,
    val createdBy: String? = null
)
```

Khi cần bổ sung thời điểm tạo:

```kotlin
val updated = entity.copy(createdAt = clock.instant())
```

Trong callback Kotlin, trả `Mono.just(updated)` hoặc publisher tương ứng. `copy` giữ các thuộc tính không được chỉ định và tạo một instance khác. Tương tự Java record, cần bảo đảm các thuộc tính bên trong không tham chiếu tới collection mutable nếu muốn bất biến sâu.

## 9. Callback không được bỏ qua entity mới

Một lỗi thường gặp là tạo bản sao nhưng không dùng nó:

```java
@Override
public Publisher<PurchaseOrder> onBeforeConvert(
        PurchaseOrder entity,
        SqlIdentifier table) {

    entity.withCreatedAt(clock.instant());
    return Mono.just(entity);
}
```

`withCreatedAt` trả instance mới nhưng kết quả bị bỏ qua. Vì entity gốc bất biến, `createdAt` của nó vẫn giữ nguyên. Callback phải trả về giá trị do `withCreatedAt` tạo:

```java
@Override
public Publisher<PurchaseOrder> onBeforeConvert(
        PurchaseOrder entity,
        SqlIdentifier table) {

    return Mono.just(entity.withCreatedAt(clock.instant()));
}
```

Một lỗi khác là callback trả publisher rỗng khi không cần thay đổi:

```java
if (entity.createdAt() != null) {
    return Mono.empty(); // Không có nghĩa là “giữ entity hiện tại”.
}
```

`Mono.empty()` không phát entity để pipeline persistence tiếp tục. Nếu không cần thay đổi, trả `Mono.just(entity)`. Chỉ dùng empty khi hợp đồng callback và use case thực sự muốn không phát kết quả; đối với callback tiền xử lý entity cần được lưu, empty thường làm thao tác lưu không tiếp tục như mong đợi.

## 10. `BeforeConvertCallback` phù hợp khi thay đổi thuộc tính entity

Giả sử cần chuẩn hóa mã đơn hàng trước khi ghi. Giá trị mới phải đi vào `OutboundRow`, vì vậy hãy tạo entity mới ở giai đoạn trước convert:

```java
@Component
public class OrderNumberCallback
        implements BeforeConvertCallback<PurchaseOrder> {

    @Override
    public Publisher<PurchaseOrder> onBeforeConvert(
            PurchaseOrder entity,
            SqlIdentifier table) {

        String normalized = entity.orderNumber().trim().toUpperCase(Locale.ROOT);

        if (normalized.equals(entity.orderNumber())) {
            return Mono.just(entity);
        }

        return Mono.just(entity.withOrderNumber(normalized));
    }
}
```

Ở đây `withOrderNumber` là phương thức tạo bản sao được bổ sung trong entity. Khi callback phát entity mới, Spring Data chuyển instance đó thành row và ghi giá trị đã chuẩn hóa.

Callback chỉ nên thực hiện chuẩn hóa thuộc về quy tắc persistence hoặc một chính sách dùng chung. Quy tắc nghiệp vụ quan trọng như kiểm tra mã đơn hàng có hợp lệ hay không vẫn nên nằm trong domain/service để có thể được áp dụng cả khi object không đi qua repository.

## 11. `BeforeSaveCallback` và `OutboundRow`

`BeforeSaveCallback` được gọi sau bước chuyển entity thành `OutboundRow`. Callback thường nhận cả entity và row:

```java
// Chữ ký minh họa của reactive callback trong Spring Data R2DBC.
Publisher<PurchaseOrder> onBeforeSave(
        PurchaseOrder entity,
        OutboundRow row,
        SqlIdentifier table);
```

Ở giai đoạn này có thể cần thay đổi giá trị row trực tiếp, ví dụ thêm một cột audit do database ghi. Vì row đã được tạo từ entity, hãy phân biệt hai mục tiêu:

- Muốn thay đổi thuộc tính entity và để Spring Data ánh xạ lại trước khi ghi: dùng `BeforeConvertCallback`.
- Muốn điều chỉnh giá trị SQL trong `OutboundRow` sau khi mapping: cập nhật row theo API `OutboundRow`/`Parameter` của phiên bản đang dùng.

Nếu callback `BeforeSave` trả về một entity immutable mới, giá trị trả về có thể được dùng ở bước sau/caller theo hợp đồng callback, nhưng không nên giả định các thay đổi trong instance đó tự động được phản ánh ngược vào `OutboundRow` đã tạo. Khi cần dữ liệu SQL thay đổi, phải thay đổi row hoặc thực hiện ở giai đoạn trước convert.

Không nên dùng `BeforeSaveCallback` để làm cùng một việc với `BeforeConvertCallback` rồi kỳ vọng entity được remap tự động. Chọn callback dựa trên thời điểm dữ liệu cần được thay đổi.

## 12. `AfterSaveCallback` không thay đổi dữ liệu đã ghi

Sau khi database thực hiện insert/update, `AfterSaveCallback` có thể tạo một entity mới để bổ sung thông tin cho kết quả được phát ra:

```java
// Minh họa ý tưởng: tạo một instance kết quả mới sau khi lưu.
PurchaseOrder result = entity.withPersistenceStatus("SAVED");
return Mono.just(result);
```

Giá trị chỉ được thêm vào object kết quả sau thao tác SQL. Nếu `persistenceStatus` không phải cột lưu trong database, điều này có thể phù hợp để làm giàu kết quả. Nếu đó là một cột cần ghi, phải thiết lập trước khi convert hoặc cập nhật row trong callback thích hợp.

Không dùng callback sau save để tạo một giá trị mà database cần lưu trong cùng câu insert; thời điểm đó câu lệnh đã được thực thi.

## 13. Nhận ID database sinh trong mô hình bất biến

Với khóa chính do database sinh, entity mới thường có `id == null`. Sau insert, Spring Data nhận generated value và tạo entity kết quả có ID. Với mô hình bất biến, instance trả về có thể khác instance đầu vào.

```java
PurchaseOrder order = new PurchaseOrder(
        null,
        "PO-2026-001",
        clock.instant(),
        "system"
);

return purchaseOrderRepository.save(order)
        .map(saved -> saved.id());
```

Hãy đọc ID từ `saved`, entity được phát ra bởi `save()`. Không đọc `order.id()` ngay sau khi gọi `save`, vì object đầu vào không nhất thiết được mutate. Việc persistence hoàn tất và generated ID được ánh xạ xảy ra trong publisher.

Nếu cần tạo dữ liệu con, dùng ID của entity đã lưu trong `flatMap`:

```java
return purchaseOrderRepository.save(order)
        .flatMap(saved -> lineRepository.saveAll(
                        lines.stream()
                                .map(line -> line.withOrderId(saved.id()))
                                .toList())
                .thenReturn(saved));
```

Nếu các thao tác cha/con phải nguyên tử, hãy đặt toàn bộ pipeline trong cùng transaction reactive. Không gọi `subscribe()` riêng cho bước lưu con vì sẽ tách nó khỏi luồng lỗi và transaction của thao tác tạo cha.

## 14. Spring Data có thể tạo bản sao entity immutable như thế nào?

Spring Data Relational sử dụng metadata mapping và cơ chế tạo instance dựa trên constructor/property access. Với entity immutable, framework có thể tạo một instance mới khi cần áp dụng giá trị như generated ID hoặc version. Các mô hình hỗ trợ có thể bao gồm:

- Constructor được nhận diện làm persistence constructor.
- Java record với canonical constructor.
- Kotlin data class với constructor phù hợp.
- Property có wither/creator để tạo instance mới khi một giá trị được cập nhật.
- Cấu trúc immutable được Spring Data hỗ trợ theo mapping metadata của phiên bản tương ứng.

Vì vậy, không nên dựa vào việc Spring Data sẽ thay đổi field final hoặc mutate object gốc. Hãy luôn dùng entity được phát ra từ publisher `save()` làm kết quả của thao tác.

Nếu constructor mapping không rõ ràng, hãy cung cấp một persistence constructor duy nhất hoặc đánh dấu constructor phù hợp bằng `@PersistenceCreator` khi cần. Tên tham số constructor cần tương ứng property và metadata mapping. Với Java class, cấu hình giữ tên tham số (`-parameters`) có thể cần thiết tùy cách mapping.

## 15. Callback có phải nơi phù hợp cho mọi logic không?

Callback thích hợp cho logic gắn với vòng đời persistence và cần được áp dụng nhất quán khi entity đi qua Spring Data repository/template. Ví dụ:

- Bổ sung audit metadata dùng chung.
- Chuẩn hóa trường lưu trữ trước khi convert.
- Tạo một giá trị kỹ thuật cần có trước khi ghi.
- Áp dụng quy tắc persistence dùng chung cho một loại entity.

Callback không phải nơi phù hợp cho mọi quy tắc nghiệp vụ:

- Không nên ẩn một workflow dài hoặc gọi nhiều dịch vụ bên ngoài trong callback.
- Không nên gọi HTTP blocking hoặc `block()` trong reactive callback.
- Không nên dùng callback để thay thế validation tại API/domain.
- Không nên dùng callback để điều phối transaction giữa nhiều aggregate mà service cần kiểm soát rõ ràng.
- Không nên đặt logic chỉ cần chạy ở một use case cụ thể vào callback toàn cục cho mọi lần lưu entity.

Callback reactive nên thực hiện công việc non-blocking. Nếu cần truy vấn database bổ sung, phải cân nhắc vòng đời, số truy vấn và khả năng lặp lại; callback có thể được gọi trong nhiều đường lưu và không nên tạo side effect khó kiểm soát.

## 16. Callback được gọi khi nào?

Callback được thực thi trong pipeline persistence, không phải ngay khi tạo entity hoặc gọi phương thức repository nếu publisher chưa được subscribe. Ví dụ:

```java
Mono<PurchaseOrder> saved = purchaseOrderRepository.save(order);
```

Đoạn code trên mô tả publisher. Khi publisher được subscribe, Spring Data mới thực hiện thao tác và gọi callback theo lifecycle tương ứng.

Điều này có nghĩa:

- Không đặt side effect bắt buộc ở ngoài publisher rồi kỳ vọng nó chạy khi `save()` được gọi.
- Callback có thể được gọi lại nếu publisher được subscribe nhiều lần, tùy cách pipeline được tạo và dùng.
- Không chia sẻ mutable state trong callback giữa nhiều request đồng thời.
- Dùng `Clock`, service stateless hoặc dependency thread-safe thay vì biến instance có thể thay đổi.
- Nếu callback cần tạo một giá trị ngẫu nhiên hoặc mã nghiệp vụ, cân nhắc tạo ở service/domain để bảo đảm một lần tạo ý định chỉ sinh một giá trị, nhất là khi có retry.

Ví dụ, nếu callback tạo UUID mỗi lần được gọi và một publisher bị subscribe lại, giá trị có thể khác giữa các lần. Nếu UUID là định danh nghiệp vụ cần ổn định qua retry, hãy tạo nó ở command/service hoặc dùng idempotency key, không phụ thuộc vào callback được gọi bao nhiêu lần.

## 17. Không gọi `block()` hoặc `subscribe()` trong callback

Reactive callback phải trả publisher để Spring Data nối vào pipeline. Không tự subscribe bên trong callback:

```java
@Override
public Publisher<PurchaseOrder> onBeforeConvert(
        PurchaseOrder entity,
        SqlIdentifier table) {

    auditRepository.save(...).subscribe(); // Không nên
    return Mono.just(entity);
}
```

Đoạn code này tạo một luồng phụ không được chờ, không được kết hợp lỗi và có thể chạy ngoài transaction của thao tác lưu entity. Callback có thể hoàn tất trước khi audit save xong.

Nếu callback thực sự cần một publisher phụ thuộc, hãy nối bằng `flatMap` hoặc `thenReturn`:

```java
return auditRepository.findPolicyFor(entity.orderNumber())
        .map(policy -> entity.withPolicyCode(policy.code()));
```

Tuy nhiên, hãy cân nhắc việc callback truy vấn database có tạo thêm N+1 query hoặc vòng phụ thuộc persistence hay không. Với logic cần nhiều thao tác, service thường là nơi dễ kiểm soát hơn.

## 18. Kết hợp callback với auditing

Spring Data Relational hỗ trợ auditing để tự động ghi nhận thời điểm tạo/cập nhật và người thực hiện. Với R2DBC, cấu hình auditing phù hợp có thể dùng `@EnableR2dbcAuditing` cùng các annotation như `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy` và `@LastModifiedBy`.

Ví dụ entity:

```java
@Table("purchase_order")
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        @CreatedDate Instant createdAt,
        @LastModifiedDate Instant modifiedAt,
        @CreatedBy String createdBy,
        @LastModifiedBy String modifiedBy
) {
}
```

Auditing infrastructure có thể cập nhật giá trị trên entity thông qua cơ chế mapping hỗ trợ immutable instance. Vì vậy, trước khi viết callback riêng để gán `createdAt` hoặc `modifiedAt`, hãy kiểm tra auditing đã đáp ứng yêu cầu chưa. Tránh có hai cơ chế cùng ghi một trường với thứ tự không rõ ràng.

Để auditing biết người dùng hiện tại, cần cung cấp `ReactiveAuditorAware<T>` phù hợp nếu ứng dụng dùng reactive security context. Auditor provider phải đọc context reactive đúng cách, không dùng ThreadLocal/blocking theo giả định của ứng dụng imperative.

## 19. Thứ tự nhiều callback

Một entity có thể đi qua nhiều callback cùng loại. Khi thứ tự có ý nghĩa, cần cấu hình thứ tự thực thi theo cơ chế callback của phiên bản Spring Data và Spring Framework đang dùng, ví dụ `Ordered` hoặc `@Order` khi được hỗ trợ.

Không nên để hai callback cùng ghi một thuộc tính mà không có quy ước. Ví dụ một callback chuẩn hóa mã đơn hàng và một callback khác tạo hash từ mã đơn hàng: nếu hash chạy trước chuẩn hóa, hash có thể phản ánh giá trị cũ.

Có thể gom các bước phụ thuộc nhau vào một callback rõ ràng hoặc quy định thứ tự tường minh. Dù chọn cách nào, mỗi callback immutable phải trả về entity mới của bước hiện tại để callback kế tiếp nhận được trạng thái đã cập nhật.

## 20. Kiểm thử callback độc lập

Callback có thể được kiểm thử như một thành phần Java thông thường bằng cách gọi phương thức và kiểm tra publisher phát entity mới:

```java
class PurchaseOrderTimestampCallbackTest {

    private final Instant fixedInstant =
            Instant.parse("2026-01-15T08:00:00Z");

    private final Clock clock = Clock.fixed(fixedInstant, ZoneOffset.UTC);

    private final PurchaseOrderTimestampCallback callback =
            new PurchaseOrderTimestampCallback(clock);

    @Test
    void returnsNewEntityWithCreatedAtWhenMissing() {
        PurchaseOrder original = new PurchaseOrder(
                null, "PO-1", null, "system");

        StepVerifier.create(callback.onBeforeConvert(
                        original, SqlIdentifier.unquoted("purchase_order")))
                .assertNext(updated -> {
                    assertThat(updated.createdAt()).isEqualTo(fixedInstant);
                    assertThat(updated).isNotSameAs(original);
                    assertThat(original.createdAt()).isNull();
                })
                .verifyComplete();
    }

    @Test
    void returnsOriginalEntityWhenValueAlreadyExists() {
        PurchaseOrder original = new PurchaseOrder(
                null, "PO-1", fixedInstant, "system");

        StepVerifier.create(callback.onBeforeConvert(
                        original, SqlIdentifier.unquoted("purchase_order")))
                .expectNextSame(original)
                .verifyComplete();
    }
}
```

Test giả định callback và API `SqlIdentifier` của phiên bản đang dùng có chữ ký như ví dụ. Nếu package hoặc factory method khác, điều chỉnh import theo dependency dự án; mục tiêu kiểm thử vẫn là xác minh entity mới được phát, entity gốc không bị thay đổi và nhánh không đổi trả entity hợp lệ.

## 21. Integration test qua repository

Unit test callback không chứng minh Spring Data đã đăng ký callback hoặc dùng entity callback trả về để tạo SQL. Cần có integration test với repository và database R2DBC tương thích:

```java
@Test
void saveUsesEntityReturnedByBeforeConvertCallback() {
    PurchaseOrder input = new PurchaseOrder(
            null, "PO-1", null, "system");

    StepVerifier.create(purchaseOrderRepository.save(input))
            .assertNext(saved -> {
                assertThat(saved.id()).isNotNull();
                assertThat(saved.createdAt()).isNotNull();
            })
            .verifyComplete();

    assertThat(input.createdAt()).isNull();
}
```

Test này minh họa các điều cần kiểm tra: callback đã được đăng ký, giá trị được bổ sung trước khi mapping, database lưu thành công, ID được sinh và entity kết quả có giá trị mới. Trong test thực tế, nên đọc lại hàng bằng ID để xác nhận giá trị `created_at` thực sự được ghi.

```java
StepVerifier.create(purchaseOrderRepository.save(input)
                .flatMap(saved -> purchaseOrderRepository.findById(saved.id())))
        .assertNext(loaded -> {
            assertThat(loaded.createdAt()).isNotNull();
            assertThat(loaded.orderNumber()).isEqualTo("PO-1");
        })
        .verifyComplete();
```

Chạy integration test với database/driver thực tế hoặc môi trường tương thích. H2 và một database khác có thể có khác biệt về generated ID, timestamp và mapping.

## 22. Kiểm tra entity callback có được đăng ký hay không

Nếu callback không chạy, kiểm tra các điểm sau:

- Callback được đăng ký thành Spring bean, ví dụ bằng `@Component` hoặc `@Bean`.
- Package callback nằm trong vùng component scan của ứng dụng.
- Generic type của callback khớp đúng entity được lưu.
- Repository/template đang dùng thuộc Spring Data R2DBC, không phải một đường ghi SQL trực tiếp bỏ qua entity lifecycle.
- Callback interface và package đúng với phiên bản Spring Data trong dependency.
- Publisher callback được trả về và không bị bỏ qua bằng `subscribe()` nội bộ.
- Publisher của thao tác `save()` thực sự được subscribe.

Các lệnh `DatabaseClient` hoặc R2DBC SPI viết SQL trực tiếp không tự chạy entity callbacks của Spring Data vì chúng không đi qua entity mapping lifecycle tương ứng. Nếu cần cùng một logic cho cả repository và SQL trực tiếp, hãy chuyển logic dùng chung thành service/factory hoặc áp dụng ở tầng database phù hợp thay vì dựa riêng vào callback.

## 23. Xử lý lỗi trong callback

Callback có thể phát lỗi nếu dữ liệu không hợp lệ hoặc một dependency cần thiết thất bại. Trong reactive callback, có thể trả `Mono.error(...)`:

```java
if (entity.orderNumber() == null || entity.orderNumber().isBlank()) {
    return Mono.error(new InvalidOrderNumberException());
}

return Mono.just(entity);
```

Lỗi sẽ đi tiếp qua publisher `save()` và có thể làm transaction rollback nếu thao tác nằm trong transaction. Không chuyển lỗi thành `Mono.empty()` để giả vờ callback đã hoàn tất; empty không có nghĩa là “bỏ qua thay đổi”.

Không bắt mọi exception rồi trả entity cũ. Cách đó có thể làm thao tác ghi tiếp tục với dữ liệu thiếu audit hoặc chưa chuẩn hóa. Chỉ dùng fallback nếu nghiệp vụ cho phép và fallback được xác định rõ.

## 24. Tránh side effect không lũy đẳng trong callback

Callback có thể được thực thi trong các lần subscribe hoặc retry khác nhau. Nếu callback gửi email, gọi dịch vụ ngoài, tăng bộ đếm hoặc tạo một giao dịch tài chính, thao tác retry có thể lặp side effect.

Callback nên tập trung vào biến đổi entity/row có thể kiểm soát. Với side effect cần phát sau khi commit, hãy dùng transaction và Transactional Outbox. Với giá trị định danh hoặc idempotency key cần ổn định, hãy tạo ở service/command trước khi lưu và giữ nguyên qua retry.

Ví dụ không nên:

```java
return emailClient.sendOrderCreated(entity).thenReturn(entity);
```

Nếu callback được gọi lại, email có thể được gửi lại. Thay vào đó, lưu một outbox event cùng transaction với entity, rồi để worker gửi email và xử lý delivery lặp bằng idempotency.

## 25. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tạo entity mới nhưng không trả về | Spring Data tiếp tục với entity cũ | Trả `Mono.just(updated)` |
| Cố gọi setter trên record/field final | Không biên dịch hoặc phá vỡ mô hình bất biến | Dùng constructor, `with...` hoặc `copy` |
| Trả `Mono.empty()` khi không cần thay đổi | Pipeline có thể không phát entity để tiếp tục lưu | Trả `Mono.just(entity)` |
| Trả null thay vì publisher | Vi phạm hợp đồng reactive và phát sinh lỗi | Trả publisher hợp lệ |
| Dùng `BeforeSave` để thay thuộc tính nhưng không sửa row | Entity mới và dữ liệu SQL có thể không đồng bộ | Dùng `BeforeConvert` hoặc cập nhật `OutboundRow` đúng cách |
| Dùng `AfterSave` để thay giá trị cần ghi | Database đã thực thi câu lệnh trước callback | Chuyển thay đổi sang callback trước convert |
| Đọc ID từ entity đầu vào sau `save()` | ID có thể vẫn null với entity immutable | Dùng entity được publisher `save()` phát ra |
| Gọi `subscribe()` trong callback | Tách công việc phụ khỏi transaction và lỗi | Nối publisher bằng `flatMap`/`then` |
| Gọi I/O blocking trong callback reactive | Chặn thread xử lý và giảm khả năng mở rộng | Dùng API non-blocking hoặc chuyển logic sang service phù hợp |
| Hai callback ghi cùng thuộc tính không có thứ tự | Kết quả phụ thuộc thứ tự thực thi | Hợp nhất logic hoặc cấu hình thứ tự tường minh |
| Dựa vào callback cho mọi đường ghi | SQL trực tiếp có thể bỏ qua callback | Dùng service/factory hoặc áp dụng logic ở tầng phù hợp |
| Callback tạo side effect bên ngoài | Retry có thể gửi lặp hoặc giao dịch trùng | Dùng outbox và consumer lũy đẳng |

## 26. Quy trình thiết kế callback cho entity immutable

Khi cần bổ sung hoặc chuẩn hóa dữ liệu trong vòng đời lưu entity, thực hiện theo trình tự:

1. Xác định giá trị nào cần được thay đổi và có phải là dữ liệu phải ghi xuống database hay chỉ làm giàu kết quả.
2. Nếu cần thay đổi trước mapping, chọn `BeforeConvertCallback`.
3. Nếu cần chỉnh giá trị SQL sau mapping, chọn `BeforeSaveCallback` và cập nhật `OutboundRow` theo API phiên bản tương ứng.
4. Nếu chỉ cần thay đổi entity được phát ra sau thao tác ghi, cân nhắc `AfterSaveCallback`.
5. Dùng constructor, record, `with...`, Lombok `@With` hoặc Kotlin `copy` để tạo instance mới.
6. Trả instance mới bằng `Mono.just(updated)`; nếu không thay đổi, trả `Mono.just(entity)`.
7. Inject dependency stateless như `Clock`; tránh mutable state và I/O blocking.
8. Đăng ký callback thành bean và xác nhận generic type khớp entity.
9. Dùng entity được phát ra từ `repository.save()` để nhận ID và trạng thái cuối cùng.
10. Kiểm thử callback độc lập và integration test qua repository với database tương thích.

## 27. Nguyên tắc thực hành

- Với entity immutable, không mutate object; tạo instance mới và trả nó qua callback publisher.
- Dùng `BeforeConvertCallback` khi giá trị mới phải tham gia entity-to-row mapping.
- Dùng `BeforeSaveCallback` cho thay đổi ở mức `OutboundRow`; không giả định entity copy được remap tự động.
- Dùng `AfterSaveCallback` để làm giàu kết quả sau khi SQL đã thực thi, không để thay thế dữ liệu cần ghi.
- Dùng Java record, constructor, `with...`, Lombok `@With` hoặc Kotlin `copy` để tạo bản sao rõ ràng.
- Trả `Mono.just(entity)` khi không có thay đổi; không dùng `Mono.empty()` như một cách giữ nguyên entity.
- Không bỏ qua giá trị trả về của `with...` hoặc `copy`.
- Không gọi `block()`/`subscribe()` trong reactive callback; nối publisher vào pipeline.
- Không thực hiện side effect không lũy đẳng hoặc gọi dịch vụ blocking trong callback.
- Dùng `Clock` có thể inject để tạo thời gian ổn định và kiểm thử được.
- Đọc ID và trạng thái cuối từ entity được phát ra bởi `save()`, không giả định object đầu vào đã bị thay đổi.
- Kiểm tra callback được đăng ký và đường ghi thực sự đi qua Spring Data entity mapping.
- Kiểm thử cả instance trả về, object đầu vào không đổi và giá trị thực tế trong database.

## 28. Kết luận

Với mô hình bất biến, callback của Spring Data Relational R2DBC cần tạo một entity mới thay vì thay đổi object hiện tại. Callback phải phát instance mới qua publisher để Spring Data dùng kết quả đó ở bước tiếp theo. `BeforeConvertCallback` thường là điểm phù hợp khi giá trị mới phải được chuyển thành cột database; `BeforeSaveCallback` làm việc ở giai đoạn `OutboundRow` đã được tạo, còn `AfterSaveCallback` chỉ có thể làm giàu kết quả sau khi SQL đã chạy.

Java record, constructor, phương thức `with...`, Lombok `@With` và Kotlin `copy` đều hỗ trợ cách tạo bản sao rõ ràng. Khi lưu, hãy dùng entity mà `save()` phát ra để nhận generated ID hoặc trạng thái cuối cùng. Giữ callback reactive, không block hoặc subscribe rời rạc, tránh side effect lặp và kiểm thử cả callback lẫn kết quả lưu thực tế sẽ giúp vòng đời entity immutable nhất quán và dễ dự đoán.
