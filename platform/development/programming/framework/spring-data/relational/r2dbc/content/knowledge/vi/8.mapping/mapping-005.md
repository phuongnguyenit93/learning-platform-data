# Bỏ qua thuộc tính không lưu trữ bằng @Transient

Trong Spring Data Relational R2DBC, một entity có thể chứa cả dữ liệu được lưu trong database và dữ liệu chỉ có ý nghĩa trong bộ nhớ của ứng dụng. Ví dụ, `Order` có thể có `id`, `total` và `status` là các thuộc tính lưu trữ, đồng thời có `displayStatus` hoặc `canCancel` được tính từ những thuộc tính đó để phục vụ giao diện. Nếu một thuộc tính không đại diện cho cột dữ liệu cần đọc hoặc ghi, có thể đánh dấu nó bằng `@Transient` của Spring Data để loại nó khỏi mapping persistence.

`@Transient` giúp Spring Data biết rằng thuộc tính đó không thuộc mô hình dữ liệu quan hệ của entity. Khi lưu hoặc đọc entity qua repository và `R2dbcEntityTemplate`, mapping layer bỏ qua thuộc tính này. Ứng dụng vẫn có thể sử dụng thuộc tính trong Java như bình thường, tính toán giá trị, gán dữ liệu bổ sung hoặc trả nó trong response nếu serializer cho phép.

## 1. Vì sao cần @Transient?

Một lớp entity thường phục vụ nhiều nhu cầu trong ứng dụng: lưu trữ dữ liệu, tính toán trạng thái, hiển thị thông tin và trao đổi dữ liệu giữa các tầng. Không phải thuộc tính nào trong lớp cũng cần có một cột tương ứng trong database.

Ví dụ, một đơn hàng có thể có:

- `id`: mã định danh được lưu trong bảng.
- `total`: tổng tiền được lưu trong bảng.
- `status`: trạng thái nghiệp vụ được lưu trong bảng.
- `displayStatus`: nhãn trạng thái thân thiện được tính từ `status`.
- `canCancel`: cờ cho biết người dùng hiện tại có thể hủy đơn hàng hay không, được tính từ trạng thái và quyền của người dùng.
- `formattedTotal`: chuỗi tiền tệ để hiển thị, được tạo từ `total` và locale.

Ba thuộc tính cuối có thể thay đổi theo ngữ cảnh hoặc được tính từ dữ liệu khác. Nếu để Spring Data xem chúng là thuộc tính persistent, mapping có thể tìm cách ánh xạ chúng vào cột hoặc đưa chúng vào quá trình ghi dữ liệu. Điều đó có thể dẫn đến lỗi thiếu cột, lỗi SQL hoặc mô hình entity không phản ánh đúng schema.

`@Transient` đánh dấu rõ ranh giới: thuộc tính vẫn tồn tại trong object Java, nhưng không tham gia mapping lưu trữ của Spring Data.

## 2. Import đúng annotation

Với Spring Data Relational R2DBC, dùng annotation:

```java
import org.springframework.data.annotation.Transient;
```

Không nhầm annotation này với:

```java
import jakarta.persistence.Transient;
```

`jakarta.persistence.Transient` thuộc Jakarta Persistence/JPA. Spring Data R2DBC sử dụng mapping metadata của Spring Data Relational, vì vậy nên dùng annotation `org.springframework.data.annotation.Transient` cho entity R2DBC.

Hai annotation có cùng tên ngắn nhưng thuộc hai hệ persistence khác nhau. IDE có thể tự import nhầm nếu dự án đồng thời có dependency JPA. Hãy kiểm tra dòng `import` khi tạo annotation.

## 3. Ví dụ entity có thuộc tính transient

Giả sử bảng `purchase_order` chỉ lưu các cột `id`, `total` và `status`. Ứng dụng muốn bổ sung `displayStatus` để hiển thị trạng thái dễ đọc.

```java
import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private BigDecimal total;

    private String status;

    @Transient
    private String displayStatus;

    public PurchaseOrder() {
    }

    public PurchaseOrder(Long id, BigDecimal total, String status) {
        this.id = id;
        this.total = total;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getDisplayStatus() {
        return displayStatus;
    }

    public void setDisplayStatus(String displayStatus) {
        this.displayStatus = displayStatus;
    }
}
```

`id`, `total` và `status` là các thuộc tính persistent. `displayStatus` vẫn có getter và setter để service hoặc tầng trình bày có thể sử dụng, nhưng Spring Data Relational bỏ qua nó trong mapping entity.

Entity này không yêu cầu bảng có cột `display_status`. Annotation `@Transient` cũng không tạo hoặc xóa cột trong database; schema vẫn được quản lý bởi migration hoặc công cụ DDL riêng của dự án.

## 4. Điều gì xảy ra khi đọc và ghi entity?

`@Transient` tác động đến mapping của Spring Data Relational. Nó không xóa thuộc tính khỏi object và không ngăn Java code đọc hoặc ghi giá trị của thuộc tính đó.

### 4.1. Khi INSERT hoặc UPDATE

Khi lưu `PurchaseOrder` bằng reactive repository:

```java
public interface PurchaseOrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {
}
```

Ví dụ:

```java
PurchaseOrder order = new PurchaseOrder(
    null,
    new BigDecimal("125000.00"),
    "PAID"
);
order.setDisplayStatus("Đã thanh toán");

Mono<PurchaseOrder> saved = purchaseOrderRepository.save(order);
```

Spring Data Relational sử dụng các thuộc tính persistent để tạo thao tác lưu. `displayStatus` không được đưa vào danh sách cột INSERT hoặc UPDATE. Database không cần có cột tương ứng với thuộc tính đó.

Nếu một thuộc tính phải được lưu nhưng bị đánh dấu `@Transient`, giá trị của nó sẽ không được lưu qua mapping này. Khi đó cần bỏ annotation hoặc thiết kế lại mapping/schema.

### 4.2. Khi SELECT và materialize entity

Khi đọc entity:

```java
Mono<PurchaseOrder> order = purchaseOrderRepository.findById(100L);
```

Spring Data đọc các cột persistent và tạo object `PurchaseOrder`. `displayStatus` không được lấy từ một cột database thông qua entity mapping. Giá trị của nó sẽ ở trạng thái mặc định hoặc do constructor/cách khởi tạo của ứng dụng thiết lập.

Nếu cần hiển thị nhãn, hãy tính sau khi đọc:

```java
Mono<PurchaseOrder> findOrderForDisplay(Long id) {
    return purchaseOrderRepository.findById(id)
        .map(order -> {
            order.setDisplayStatus(switch (order.getStatus()) {
                case "NEW" -> "Mới tạo";
                case "PAID" -> "Đã thanh toán";
                case "CANCELLED" -> "Đã hủy";
                default -> "Không xác định";
            });
            return order;
        });
}
```

Giá trị transient được bổ sung trong bộ nhớ sau khi entity được đọc. Khi entity được lưu lại, `displayStatus` vẫn không được ghi xuống database.

### 4.3. Sơ đồ vòng đời

```text
Database row
     |
     | SELECT các cột persistent
     v
Spring Data Relational mapping
     |
     | Tạo entity, bỏ qua @Transient
     v
PurchaseOrder trong bộ nhớ
     |
     | Service tính displayStatus
     v
Entity đã được enrich
     |
     | INSERT/UPDATE chỉ thuộc tính persistent
     v
Database row (không có displayStatus)
```

Điểm quan trọng là thuộc tính transient có thể có giá trị trong object sau khi service enrich, nhưng mapping persistence không lưu giá trị đó.

## 5. Các trường hợp sử dụng phổ biến

### 5.1. Thuộc tính tính toán từ dữ liệu persistent

Một thuộc tính có thể được suy ra từ những cột đã có:

```java
@Transient
private BigDecimal taxAmount;

public BigDecimal getTaxAmount() {
    if (total == null) {
        return null;
    }
    return total.multiply(new BigDecimal("0.10"));
}
```

Nếu giá trị luôn có thể tính từ `total`, có thể không cần field `taxAmount` riêng. Getter tính toán giúp tránh lưu trạng thái dư thừa trong object. Nếu cần cache kết quả hoặc gán từ một dịch vụ khác, field transient có thể phù hợp hơn.

### 5.2. Thuộc tính phục vụ giao diện

Ví dụ `displayStatus`, `formattedTotal`, `thumbnailUrl` hoặc `shortDescription` chỉ phục vụ trình bày. Những giá trị này có thể phụ thuộc locale, múi giờ hoặc cấu hình người dùng, do đó không nhất thiết là dữ liệu lưu trữ.

### 5.3. Kết quả bổ sung từ dịch vụ khác

Một entity có thể được enrich bằng dữ liệu từ một service khác, ví dụ:

```java
@Transient
private String shippingEstimate;

@Transient
private boolean eligibleForPromotion;
```

`shippingEstimate` có thể đến từ dịch vụ vận chuyển; `eligibleForPromotion` có thể phụ thuộc chương trình khuyến mại đang hoạt động. Những giá trị này không thuộc bảng đơn hàng nên không nên bị ghi vào bảng đó một cách vô tình.

### 5.4. Cờ tạm thời trong một use case

Một thuộc tính như `selected`, `expanded` hoặc `validationMessage` có thể hữu ích trong một luồng xử lý hoặc một màn hình. Nếu đặt trên entity, hãy đánh dấu transient để Spring Data không coi đó là dữ liệu của bảng.

Tuy nhiên, nếu thuộc tính chỉ phục vụ một API response, DTO riêng thường là lựa chọn rõ ràng hơn. Entity nên tập trung vào dữ liệu và hành vi gắn với mô hình persistence; DTO có thể chứa dữ liệu trình bày hoặc kết quả tổng hợp theo use case.

## 6. @Transient không đồng nghĩa với một cột read-only

`@Transient` có nghĩa thuộc tính bị loại khỏi mapping persistence. Nếu database có một cột cần đọc nhưng ứng dụng không được ghi vào cột đó, đó là yêu cầu khác.

Spring Data Relational cung cấp `@ReadOnlyProperty` cho trường hợp thuộc tính được đọc từ database nhưng không được ghi bởi mapping layer, tùy theo khả năng của phiên bản đang dùng:

```java
import org.springframework.data.annotation.ReadOnlyProperty;

@ReadOnlyProperty
private Instant createdAt;
```

So sánh:

| Annotation | Đọc từ database | Ghi vào database | Trường hợp sử dụng |
|---|---|---|---|
| `@Transient` | Không qua mapping property đó | Không | Giá trị chỉ tồn tại trong bộ nhớ hoặc được tính/enrich |
| `@ReadOnlyProperty` | Có | Không | Cột do database quản lý hoặc chỉ cho phép đọc qua mapping |
| Thuộc tính persistent thông thường | Có | Có theo thao tác mapping | Dữ liệu ứng dụng lưu trữ bình thường |

Ví dụ, `created_at` có thể do database tự sinh và ứng dụng chỉ đọc. Trong khi đó `displayStatus` có thể được tính từ `status` và không có cột trong bảng. Hai trường hợp không nên dùng chung `@Transient`.

Nếu dùng `@ReadOnlyProperty`, hãy xác nhận database thực sự tạo/cập nhật cột đó và driver/mapping có thể đọc nó. Annotation không tự tạo giá trị ở phía database.

## 7. Phân biệt với các cơ chế khác có tên Transient

Trong một dự án Java, có thể gặp nhiều cơ chế có ý nghĩa gần nhau nhưng phạm vi khác nhau.

| Cơ chế | Phạm vi tác động | Ý nghĩa |
|---|---|---|
| `org.springframework.data.annotation.Transient` | Spring Data mapping | Bỏ qua thuộc tính trong mapping persistence của Spring Data |
| `jakarta.persistence.Transient` | JPA | Đánh dấu thuộc tính không persistent trong JPA |
| Từ khóa Java `transient` | Java serialization và modifier của field | Ảnh hưởng đến cơ chế serialization Java; không nên dùng thay annotation Spring Data nếu mục tiêu là cấu hình mapping R2DBC rõ ràng |
| `@JsonIgnore` của Jackson | JSON serialization/deserialization | Ẩn hoặc bỏ qua thuộc tính khi xử lý JSON theo cấu hình Jackson |

Các cơ chế trên không tự thay thế lẫn nhau. Một thuộc tính có thể bị loại khỏi persistence mapping nhưng vẫn xuất hiện trong JSON, hoặc ngược lại.

Ví dụ, `@Transient` không tự ngăn Jackson serialize getter `getDisplayStatus()`. Nếu API không được phép trả trường đó, cần thiết kế DTO response hoặc dùng annotation/cấu hình serialization phù hợp. Ngược lại, `@JsonIgnore` không khiến Spring Data Relational bỏ qua một cột khi lưu entity.

## 8. Truy vấn theo thuộc tính transient

Vì thuộc tính `@Transient` không phải persistent property, Spring Data không thể coi nó là cột trong bảng khi tạo truy vấn theo tên thuộc tính.

Ví dụ, nếu `displayStatus` được tính từ `status`, không nên tạo derived query như:

```java
// Không phù hợp: displayStatus không phải thuộc tính persistent.
Flux<PurchaseOrder> findByDisplayStatus(String displayStatus);
```

Thay vào đó, truy vấn theo thuộc tính nguồn:

```java
Flux<PurchaseOrder> findByStatus(String status);
```

Hoặc viết SQL/`@Query` dựa trên cột thật:

```java
@Query("""
    SELECT id, total, status
    FROM purchase_order
    WHERE status = :status
    """)
Flux<PurchaseOrder> findByStoredStatus(String status);
```

Nếu giá trị cần lọc là biểu thức phức tạp, hãy biểu diễn biểu thức đó trong SQL hoặc tạo một cột/view phù hợp ở database nếu nghiệp vụ và hiệu năng yêu cầu. Không thể lọc trực tiếp ở database theo một giá trị chỉ tồn tại trong bộ nhớ mà chưa có biểu thức hoặc dữ liệu tương ứng trong database.

## 9. @Transient và truy vấn SQL tùy chỉnh

`@Transient` điều khiển mapping của Spring Data Relational. Nó không điều khiển database engine và không thay đổi câu SQL viết tay.

Khi sử dụng `DatabaseClient`, ứng dụng tự quyết định cột nào được SELECT và cách ánh xạ hàng:

```java
databaseClient.sql("""
        SELECT id, total, status
        FROM purchase_order
        WHERE id = :id
        """)
    .bind("id", id)
    .map((row, metadata) -> {
        PurchaseOrder order = new PurchaseOrder(
            row.get("id", Long.class),
            row.get("total", BigDecimal.class),
            row.get("status", String.class)
        );
        order.setDisplayStatus("Đang xử lý");
        return order;
    })
    .one();
```

Trong đoạn code trên, `displayStatus` được gán vì mapper do ứng dụng viết trực tiếp. Annotation `@Transient` không ngăn mapper Java gọi setter. Khi dùng `DatabaseClient`, trách nhiệm ánh xạ thuộc về callback `map(...)`; annotation không tự thực hiện hoặc cấm thao tác gán trong code thủ công.

Tương tự, nếu viết SQL `INSERT` hoặc `UPDATE` thủ công và tự đưa một tên cột vào câu lệnh, database sẽ xử lý câu SQL đó theo schema. `@Transient` không sửa câu SQL. Nếu cột không tồn tại, câu lệnh vẫn lỗi như bình thường.

## 10. Constructor và quá trình tạo entity

Spring Data có thể sử dụng constructor hoặc factory method để tạo entity khi đọc dữ liệu. Với thuộc tính transient, cần thiết kế constructor dựa trên dữ liệu thực sự được đọc từ database.

Ví dụ nên giữ constructor chính tập trung vào các thuộc tính persistent:

```java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private BigDecimal total;

    private String status;

    @Transient
    private String displayStatus;

    public PurchaseOrder(Long id, BigDecimal total, String status) {
        this.id = id;
        this.total = total;
        this.status = status;
    }
}
```

Constructor không yêu cầu `displayStatus` vì database không cung cấp giá trị này. Sau khi entity được materialize, service có thể tính hoặc gán thuộc tính transient.

Nếu một constructor yêu cầu tham số mà không có dữ liệu tương ứng trong kết quả persistence, quá trình materialization có thể không hoạt động như mong đợi hoặc nhận giá trị mặc định tùy cách mapping và phiên bản. Tránh buộc constructor persistence phải nhận dữ liệu chỉ có trong bộ nhớ. Nếu cần nhiều cách tạo object, có thể dùng constructor phù hợp và `@PersistenceCreator` cho constructor mà Spring Data nên sử dụng.

Với entity immutable hoặc Java record, cần cân nhắc kỹ vì các thuộc tính transient không thể được gán sau khi tạo nếu không có cơ chế khởi tạo phù hợp. Trong trường hợp dữ liệu trình bày được bổ sung sau khi đọc, DTO thường đơn giản hơn việc làm entity immutable chứa nhiều giá trị ngoài persistence.

## 11. Enrich dữ liệu transient ở service layer

Một cách dễ kiểm soát là để repository đọc entity persistent, sau đó service tính các thuộc tính tạm thời:

```java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    public Mono<PurchaseOrder> findForDisplay(Long id) {
        return repository.findById(id)
            .map(this::enrich);
    }

    private PurchaseOrder enrich(PurchaseOrder order) {
        String label = switch (order.getStatus()) {
            case "NEW" -> "Mới tạo";
            case "PAID" -> "Đã thanh toán";
            case "CANCELLED" -> "Đã hủy";
            default -> "Không xác định";
        };

        order.setDisplayStatus(label);
        return order;
    }
}
```

Với một thuộc tính đơn giản và chỉ phụ thuộc vào entity, có thể tính trực tiếp trong getter. Với dữ liệu cần gọi dịch vụ khác, nên compose publisher thay vì chặn thread:

```java
public Mono<OrderView> findOrderView(Long id) {
    return repository.findById(id)
        .flatMap(order -> shippingClient.estimate(order.getId())
            .map(estimate -> new OrderView(
                order.getId(),
                order.getTotal(),
                order.getStatus(),
                estimate
            )));
}
```

Trong ví dụ thứ hai, `OrderView` là DTO dành cho use case. Đây thường là lựa chọn tốt hơn việc nhồi nhiều dữ liệu từ dịch vụ ngoài vào entity persistence, đặc biệt khi dữ liệu enrich có vòng đời hoặc nguồn cập nhật riêng.

Nếu cần tự động enrich sau mỗi lần entity được chuyển đổi, Spring Data có các entity callback như callback sau khi convert. Callback cần được triển khai theo API reactive và phiên bản Spring Data đang dùng; hãy giữ callback ngắn, không chặn I/O và cân nhắc chi phí nếu nó chạy cho mọi entity được đọc. Với logic chỉ phục vụ một endpoint, service layer thường dễ hiểu và dễ kiểm thử hơn.

## 12. Kiểm thử thuộc tính @Transient

Kiểm thử nên chứng minh hai điều: thuộc tính vẫn dùng được trong object Java và mapping persistence không lưu/đọc nó như một cột.

### 12.1. Kiểm thử hành vi object

Có thể kiểm tra getter/setter của thuộc tính transient như các thuộc tính Java thông thường:

```java
PurchaseOrder order = new PurchaseOrder(
    10L,
    new BigDecimal("125000.00"),
    "PAID"
);

order.setDisplayStatus("Đã thanh toán");

assertEquals("Đã thanh toán", order.getDisplayStatus());
```

`@Transient` không làm mất khả năng lưu giá trị vào field trong bộ nhớ.

### 12.2. Kiểm thử tích hợp với repository

Một kiểm thử tích hợp có thể lưu entity, đọc lại rồi xác nhận các thuộc tính persistent được giữ và thuộc tính transient không được phục hồi từ database:

```java
StepVerifier.create(
        purchaseOrderRepository.save(order)
            .flatMap(saved -> purchaseOrderRepository.findById(saved.getId()))
    )
    .assertNext(reloaded -> {
        assertEquals(order.getTotal(), reloaded.getTotal());
        assertEquals(order.getStatus(), reloaded.getStatus());
        assertNull(reloaded.getDisplayStatus());
    })
    .verifyComplete();
```

Ví dụ giả định `displayStatus` không được khởi tạo tự động trong constructor. Test thực tế cần dùng database và schema tương thích với dự án, đồng thời xác nhận rằng bảng không cần cột `display_status`.

### 12.3. Kiểm thử SQL tùy chỉnh

Nếu mapper `DatabaseClient` chủ động gán thuộc tính transient, cần kiểm thử riêng mapper đó. `@Transient` không chặn code mapper thủ công nên kết quả có thể khác với entity được đọc bằng repository.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Import nhầm `jakarta.persistence.Transient` | Spring Data Relational có thể không áp dụng annotation theo mong đợi | Dùng `org.springframework.data.annotation.Transient` |
| Cho rằng `@Transient` xóa field khỏi object | Code không hiểu vì sao getter/setter vẫn hoạt động | Nhớ rằng annotation chỉ điều khiển mapping persistence |
| Mong thuộc tính transient được lưu khi gọi `save()` | Giá trị bị bỏ qua khi ghi | Bỏ annotation hoặc dùng cột persistent nếu cần lưu |
| Mong database trả giá trị transient khi SELECT | Giá trị mặc định hoặc do code khởi tạo được giữ lại | Tính/enrich sau khi đọc hoặc dùng DTO projection |
| Dùng transient property trong derived query | Không có cột persistent tương ứng để tạo điều kiện SQL | Truy vấn theo field nguồn hoặc biểu thức SQL |
| Dùng `@Transient` cho cột database chỉ đọc | Mapping không đọc cả cột | Cân nhắc `@ReadOnlyProperty` nếu phù hợp |
| Nghĩ `@Transient` ẩn field khỏi JSON | Serializer vẫn có thể gọi getter và serialize field | Dùng DTO hoặc cấu hình Jackson riêng |
| Nghĩ `@Transient` sửa SQL viết tay | SQL thủ công vẫn chạy theo nội dung được gửi | Sửa câu SQL và mapper một cách tường minh |
| Đưa giá trị transient bắt buộc vào constructor persistence | Materialization có thể thiếu dữ liệu để tạo object | Dựa constructor vào thuộc tính persistent, enrich sau |
| Đưa dữ liệu từ nhiều dịch vụ vào entity | Entity bị gắn với một use case và khó tái sử dụng | Tạo DTO/view model ở service layer |

## 14. Khi nào nên dùng DTO thay cho @Transient?

`@Transient` hữu ích khi một thuộc tính tạm thời thực sự thuộc về cách ứng dụng sử dụng entity. Tuy nhiên, không nên xem entity là nơi chứa mọi dữ liệu cần trả về API.

Hãy cân nhắc DTO khi:

- Dữ liệu bổ sung chỉ phục vụ một endpoint hoặc một màn hình.
- Dữ liệu đến từ nhiều bảng, dịch vụ hoặc nguồn bên ngoài.
- Cấu trúc response khác đáng kể so với entity database.
- Cần kiểm soát chính xác field nào được serialize ra ngoài.
- Một thuộc tính phụ thuộc người dùng hiện tại, locale, quyền hoặc thời điểm xử lý.
- Cần tránh làm entity persistence thay đổi theo yêu cầu trình bày.

Ví dụ:

```java
public record PurchaseOrderView(
    Long id,
    BigDecimal total,
    String status,
    String displayStatus,
    boolean canCancel
) {}
```

Service có thể ánh xạ entity sang view:

```java
Mono<PurchaseOrderView> findView(Long id, UserContext user) {
    return repository.findById(id)
        .map(order -> new PurchaseOrderView(
            order.getId(),
            order.getTotal(),
            order.getStatus(),
            toDisplayStatus(order.getStatus()),
            canCancel(order, user)
        ));
}
```

Ở đây, `canCancel` phụ thuộc người dùng hiện tại nên không nên lưu vào bảng đơn hàng và cũng không nhất thiết phải là field trên entity. DTO thể hiện rõ rằng đây là dữ liệu của một response cụ thể.

## 15. Nguyên tắc sử dụng

- Dùng `org.springframework.data.annotation.Transient` cho thuộc tính không tham gia mapping Spring Data Relational.
- Đặt annotation trên đúng field hoặc property mà mapping đang sử dụng; kiểm tra access strategy của entity.
- Giữ constructor persistence tập trung vào các thuộc tính có thể được materialize từ database.
- Tính hoặc enrich giá trị transient sau khi đọc nếu nó phụ thuộc dữ liệu runtime.
- Không dùng transient property làm cột trong derived query.
- Phân biệt `@Transient` với `@ReadOnlyProperty`: một bên bị bỏ qua trong mapping, bên kia có thể đọc nhưng không ghi.
- Phân biệt annotation Spring Data với annotation JPA, Java `transient` và `@JsonIgnore`.
- Nhớ rằng `DatabaseClient` với mapper thủ công không tự áp dụng quy tắc `@Transient` cho code Java do bạn viết.
- Dùng DTO khi dữ liệu bổ sung chỉ phục vụ một use case hoặc phụ thuộc ngữ cảnh người dùng.
- Kiểm thử bằng repository trên database tương thích để xác nhận hành vi đọc/ghi thực tế.

`@Transient` là cách khai báo rõ một thuộc tính thuộc về object trong bộ nhớ nhưng không thuộc mô hình lưu trữ của Spring Data Relational. Dùng đúng annotation và hiểu phạm vi tác động của nó giúp entity bám sát schema, tránh SQL tham chiếu đến cột không tồn tại, đồng thời vẫn cho phép ứng dụng bổ sung các giá trị tính toán hoặc dữ liệu runtime khi cần.
