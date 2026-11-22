# Luồng cập nhật aggregate theo mô hình lưu toàn bộ trạng thái

Trong **Spring Data Relational JDBC**, một lần gọi `repository.save(aggregate)` được hiểu là lưu trạng thái của **toàn bộ aggregate** tại thời điểm gọi. Framework không duy trì persistence context để theo dõi từng field đã thay đổi như JPA/Hibernate dirty checking. Ứng dụng thường đọc aggregate, thay đổi object trong bộ nhớ rồi gửi lại root cho repository để lưu.

Điều này ảnh hưởng trực tiếp đến cách viết service và API cập nhật:

- Cần làm việc với trạng thái đầy đủ của aggregate root và các entity con thuộc nó.
- Một property bị bỏ qua hoặc đặt thành `null` có thể mang ý nghĩa xóa/loại bỏ dữ liệu con.
- Các entity con được lưu theo vòng đời aggregate; khi cập nhật aggregate hiện hữu, Spring Data JDBC có thể xóa rồi chèn lại các hàng con thay vì phát hiện chính xác từng child đã thay đổi.
- Tham chiếu đến aggregate khác không nằm trong vòng đời xóa/chèn lại của root.
- Nếu nhiều request có thể cập nhật cùng aggregate, cần xem xét optimistic locking để tránh ghi đè dữ liệu mới bằng một object cũ.

Bài học này giải thích luồng lưu mới/cập nhật, cách các quan hệ trong aggregate được xử lý, cách thiết kế thao tác cập nhật an toàn và các tác động đến transaction, hiệu năng cùng tính nhất quán.

## 1. Aggregate là đơn vị ghi dữ liệu

Một aggregate có một **aggregate root** làm điểm truy cập chính. Ví dụ:

```text
PurchaseOrder (aggregate root)
  ├── id
  ├── orderNumber
  ├── status
  ├── shippingAddress (embedded value)
  └── lines (owned child collection)
        ├── OrderLine
        ├── OrderLine
        └── OrderLine

Customer (aggregate khác)
  └── được tham chiếu bằng customerId
```

`PurchaseOrder` sở hữu các `OrderLine` vì dòng hàng có ý nghĩa trong phạm vi đơn hàng và được thêm, sửa, xóa thông qua đơn hàng. `Customer` là aggregate khác: nó có vòng đời độc lập và có thể được nhiều đơn hàng tham chiếu.

Quy tắc quan trọng của Spring Data JDBC là thao tác lưu đi qua root. Khi gọi `save` trên root, framework lưu trạng thái của aggregate root cùng các entity con thuộc aggregate theo mapping. Nó không tự động tải và lưu toàn bộ object graph chỉ vì Java class có một field tham chiếu đến một đối tượng khác.

## 2. Spring Data JDBC không dùng dirty checking

Trong JPA, một entity được quản lý trong persistence context có thể được theo dõi thay đổi; khi transaction kết thúc, ORM có thể chỉ phát câu UPDATE cho những property thay đổi. Spring Data JDBC có mô hình khác:

| Khía cạnh | Spring Data JDBC | JPA/Hibernate thông thường |
| --- | --- | --- |
| Persistence context quản lý entity | Không duy trì một persistence context kiểu JPA | Có persistence context |
| Theo dõi thay đổi từng property | Không có dirty checking tự động | Có thể theo dõi thay đổi entity được quản lý |
| Cách ứng dụng ghi | Gọi repository để lưu aggregate state | Thay đổi managed entity rồi flush/commit hoặc gọi persist/merge |
| Vòng đời entity con | Theo aggregate root và mapping relational | Theo cascade/orphan removal và mapping JPA được cấu hình |
| Tải dữ liệu | Repository trả về object đã materialize; không có lazy-loading proxy graph kiểu JPA mặc định | Có thể lazy/eager theo mapping và persistence context |

Vì vậy, đừng áp dụng suy nghĩ "chỉ sửa một field thì framework chỉ cập nhật một field" cho `save` trong Spring Data JDBC. Với một aggregate hiện hữu, root được cập nhật và các entity được tham chiếu bên trong aggregate được đồng bộ theo mô hình lưu của Spring Data JDBC.

### 2.1. Ví dụ một aggregate

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String orderNumber;
    private String status;

    @MappedCollection(idColumn = "purchase_order_id")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderNumber) {
        this.orderNumber = orderNumber;
        this.status = "DRAFT";
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getStatus() {
        return status;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }

    public void confirm() {
        if (lines.isEmpty()) {
            throw new IllegalStateException("An order needs at least one line");
        }
        this.status = "CONFIRMED";
    }

    public void addLine(String sku, int quantity, BigDecimal unitPrice) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        lines.add(new OrderLine(sku, quantity, unitPrice));
    }

    public void removeLine(String sku) {
        lines.removeIf(line -> line.sku().equals(sku));
    }
}

public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice
) {}
```

Ví dụ dùng `List` làm collection owned child. Trong ứng dụng thực tế, cần bổ sung constructor/factory, validation và quy tắc cập nhật giá/quantity phù hợp domain. `getLines()` trả bản sao không sửa được để tránh code bên ngoài tùy ý thay đổi collection mà bỏ qua các phương thức nghiệp vụ.

Repository chỉ cần khai báo cho root:

```java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

Không cần một repository riêng cho `OrderLine` nếu nó chỉ là child thuộc aggregate `PurchaseOrder`.

## 3. Luồng lưu aggregate mới

Với một aggregate mới, framework nhận diện entity là mới theo chiến lược xác định trạng thái mới (thường dựa trên ID null, hoặc version null khi dùng version property). Với ID do database sinh, object mới thường để `id = null`:

```java
PurchaseOrder order = new PurchaseOrder("PO-2026-100");
order.addLine("SKU-CHAIR", 2, new BigDecimal("125.00"));
order.addLine("SKU-DESK", 1, new BigDecimal("450.00"));

PurchaseOrder saved = repository.save(order);
```

Luồng khái niệm:

```text
Object mới (id chưa có)
        │
        ▼
repository.save(root)
        │
        ├── INSERT aggregate root
        │       └── nhận ID do database sinh
        │
        └── INSERT các owned child
                ├── gắn back-reference tới root ID
                └── lưu trạng thái từng child
```

Thứ tự và câu SQL cụ thể do Spring Data JDBC cùng dialect/driver quyết định, nhưng child cần nhận được khóa root để ghi quan hệ. Nếu child dùng khóa ngoại tới root, root phải có ID trước khi child được ghi.

Với entity immutable hoặc có ID/version được framework điền, đối tượng trả về từ `save` có thể chứa giá trị mới mà object đầu vào chưa có. Vì vậy, nên sử dụng **giá trị trả về**:

```java
PurchaseOrder saved = repository.save(order);
Long orderId = saved.getId();
Long version = saved.getVersion();
```

Đừng mặc định object truyền vào luôn được mutate tại chỗ để nhận ID/version.

## 4. Luồng cập nhật aggregate hiện hữu

Khi aggregate đã tồn tại, ứng dụng thường đọc nó trước:

```java
PurchaseOrder order = repository.findById(orderId)
        .orElseThrow();

order.confirm();
PurchaseOrder saved = repository.save(order);
```

Spring Data JDBC không giữ snapshot managed entity để so sánh field nào đã đổi. Khi lưu một aggregate hiện hữu, mô hình persistence truyền thống của Spring Data JDBC là:

1. Cập nhật hàng aggregate root theo ID và version nếu có.
2. Xóa các entity con được lưu trữ bên trong aggregate.
3. Chèn lại các entity con đang có trong trạng thái aggregate được gửi vào.

Đây là mô tả khái niệm về việc đồng bộ aggregate; SQL và thứ tự lệnh cụ thể phụ thuộc mapping, dialect và phiên bản framework. Điểm quan trọng là **không nên dựa vào giả định Spring chỉ phát UPDATE cho child đã thay đổi**.

Ví dụ:

```text
Trạng thái trong database:
PurchaseOrder #42
  status = DRAFT
  lines = [A, B, C]

Object trong ứng dụng được sửa:
PurchaseOrder #42
  status = CONFIRMED
  lines = [A, C, D]

repository.save(order)
        │
        ▼
Đồng bộ trạng thái aggregate:
  - update root #42
  - thay thế tập child cũ bằng tập child hiện tại [A, C, D]
```

Đối với child, Spring Data JDBC có thể xóa hàng cũ và insert lại hàng hiện tại, bao gồm cả child có dữ liệu không đổi. Do đó, nếu child có ID được tham chiếu từ bên ngoài, trigger, audit record hoặc quan hệ ngoài aggregate, cần đánh giá lại thiết kế. Owned child nên thực sự phụ thuộc vòng đời root.

## 5. Tác động khi thêm, sửa và xóa child

Giả sử aggregate có collection `lines`:

| Thay đổi trong object trước khi save | Kết quả mong muốn của aggregate | Điều cần hiểu |
| --- | --- | --- |
| Thêm một `OrderLine` | Child mới xuất hiện trong aggregate | Tập child hiện tại được lưu cùng root |
| Sửa quantity của một line | Giá trị mới được lưu | Không giả định chỉ một cột của một child được UPDATE |
| Xóa một line khỏi collection | Child không còn thuộc aggregate | Hàng child tương ứng bị loại khỏi trạng thái được lưu |
| Gửi collection rỗng | Aggregate không còn child nào | Có thể xóa toàn bộ hàng child thuộc collection |
| Gửi root với child property `null` | Không có child tương ứng | Có thể xóa dữ liệu con cũ; phải phân biệt với request PATCH thiếu field |

Đây là lý do không nên tạo một object root "một phần" chỉ có ID và vài field rồi gọi `save` để cập nhật một field. Ví dụ:

Mã giả dưới đây minh họa object chỉ chứa một phần trạng thái:

```text
partialOrder = object chỉ có id và status = "CANCELLED"
repository.save(partialOrder)
```

Nếu các property khác không được khôi phục từ database, giá trị null/collection rỗng có thể được coi là trạng thái cần lưu. Điều đó có thể ghi đè dữ liệu root hoặc loại bỏ toàn bộ child. Với aggregate có nhiều quan hệ, tác động càng lớn.

**Cách thông thường an toàn hơn:** đọc aggregate hiện tại, kiểm tra quyền và điều kiện nghiệp vụ, áp dụng thay đổi lên object đầy đủ rồi lưu root.

## 6. Thiết kế service theo read-modify-save

Một service có thể đóng gói toàn bộ quy trình:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder confirm(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order not found"));

        order.confirm();

        return repository.save(order);
    }

    @Transactional
    public PurchaseOrder addLine(
            Long orderId,
            String sku,
            int quantity,
            BigDecimal unitPrice) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order not found"));

        order.addLine(sku, quantity, unitPrice);

        return repository.save(order);
    }
}
```

Service này:

- Đọc aggregate đầy đủ qua root repository.
- Thực hiện hành vi domain thay vì để controller sửa trực tiếp field.
- Lưu trạng thái mới qua root.
- Dùng transaction boundary để thao tác đọc/sửa/ghi và các bước liên quan có thể cùng một transaction.

Với một thao tác repository riêng lẻ, repository có transaction behavior mặc định theo Spring Data. Đặt `@Transactional` ở service hữu ích khi quy trình nghiệp vụ gồm nhiều lệnh và phải cùng commit/rollback. Transaction không thay thế optimistic locking: hai transaction vẫn có thể cùng đọc một version cũ.

## 7. PATCH API và nguy cơ vô tình xóa child

REST API thường phân biệt:

- **PUT:** client gửi biểu diễn đầy đủ của tài nguyên theo hợp đồng endpoint.
- **PATCH:** client chỉ gửi những trường muốn thay đổi.

Một request PATCH không có trường `lines` thường có nghĩa "không thay đổi danh sách dòng hàng". Nhưng nếu deserializer biến trường bị thiếu thành `null`, rồi ứng dụng tạo một aggregate mới từ DTO và gọi `save`, trạng thái đó có thể bị hiểu thành "không còn dòng hàng".

Ví dụ DTO patch nên giữ được sự khác biệt giữa:

1. Field không xuất hiện trong JSON.
2. Field xuất hiện với giá trị `null`.
3. Field xuất hiện với một danh sách rỗng.
4. Field xuất hiện với một danh sách phần tử.

Không phải mọi DTO hoặc thư viện JSON tự phân biệt được bốn trường hợp này. Cần chọn kiểu dữ liệu/representation phù hợp, ví dụ wrapper có trạng thái presence, JsonNode hoặc một patch model chuyên biệt.

Luồng xử lý PATCH:

```text
HTTP PATCH
    │
    ▼
Parse patch với trạng thái presence rõ ràng
    │
    ▼
Load aggregate hiện tại qua repository
    │
    ▼
Chỉ áp dụng các trường được yêu cầu thay đổi
    │
    ▼
Kiểm tra invariant và quyền nghiệp vụ
    │
    ▼
repository.save(aggregate đầy đủ)
    │
    ▼
Commit transaction
```

Không biến một PATCH nhỏ thành thao tác thay thế toàn bộ aggregate bằng object rỗng/không đầy đủ.

## 8. Optimistic locking với @Version

Giả sử hai request cùng cập nhật đơn hàng:

1. Request A đọc version `5`.
2. Request B cũng đọc version `5`.
3. A lưu thành công, version tăng lên `6`.
4. B vẫn giữ object version `5` và cố lưu.

Nếu không có cơ chế phát hiện cạnh tranh, thao tác sau có thể ghi đè trạng thái mới bằng snapshot cũ. Spring Data JDBC hỗ trợ **optimistic locking** bằng property đánh dấu `@Version`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;
}
```

Framework sử dụng version khi cập nhật để bảo đảm hàng root vẫn ở version mà object đã đọc. Về ý tưởng, câu lệnh có điều kiện tương tự:

```sql
UPDATE purchase_order
SET status = ?, version = version + 1
WHERE id = ? AND version = ?;
```

SQL trên chỉ minh họa nguyên lý; câu lệnh thực tế có thể thêm cột và cú pháp theo dialect. Nếu không có hàng nào được cập nhật do version đã đổi, Spring Data JDBC báo lỗi optimistic locking (thuộc nhóm `OptimisticLockingFailureException` của Spring).

### 8.1. Version bảo vệ điều gì?

`@Version` trên aggregate root bảo vệ cập nhật aggregate qua root: hai transaction không thể âm thầm cùng ghi thành công dựa trên cùng một version cũ. Khi cập nhật root không khớp version, thao tác lưu thất bại và transaction rollback, bao gồm các thay đổi child trong cùng transaction.

Các lưu ý:

- Để framework quản lý version; không tự tăng version trong business code.
- Trả lỗi xung đột phù hợp cho client, thường yêu cầu tải trạng thái mới và quyết định áp dụng lại thay đổi.
- Không tự động retry một command nghiệp vụ không idempotent nếu chưa hiểu tác động.
- Mọi đường ghi phải tuân thủ cùng cơ chế. SQL trực tiếp cập nhật child hoặc root mà không tăng version có thể phá vỡ giả định concurrency.
- Version không thay thế transaction, constraint hoặc validation nghiệp vụ.

## 9. Tham chiếu đến aggregate khác không bị thay thế như owned child

Một root có thể lưu ID của aggregate khác:

```java
import org.springframework.data.jdbc.core.mapping.AggregateReference;

private AggregateReference<Customer, Long> customer;
```

`AggregateReference` thể hiện quan hệ giữa hai aggregate độc lập. Khi lưu `PurchaseOrder`, Spring Data JDBC lưu giá trị tham chiếu ID theo mapping; nó không xóa/chèn lại toàn bộ aggregate `Customer`.

| Kiểu dữ liệu trong root | Ý nghĩa | Khi save root |
| --- | --- | --- |
| Owned child entity qua `@MappedCollection` | Thành phần thuộc vòng đời root | Được lưu cùng aggregate; các hàng child có thể bị thay thế |
| Embedded value qua `@Embedded` | Giá trị nằm trong hàng root | Các cột embedded được lưu như trạng thái root |
| `AggregateReference<Customer, Long>` | Tham chiếu tới aggregate độc lập | Lưu ID tham chiếu; không cascade lưu aggregate kia |
| ID scalar như `Long customerId` | Giá trị ID do ứng dụng quản lý | Lưu scalar; ứng dụng tự chịu trách nhiệm kiểm tra tham chiếu nếu cần |

Không nhúng một object aggregate độc lập vào root như owned child chỉ vì muốn đọc được thông tin liên quan. Việc xác định đúng ranh giới giúp tránh xóa nhầm dữ liệu và tránh aggregate quá lớn.

## 10. Vì sao không nên để aggregate quá lớn?

Vì mô hình lưu theo aggregate state, một aggregate có hàng nghìn child có thể khiến thao tác save:

- Phải xử lý nhiều hàng child.
- Xóa và insert lại một tập lớn các hàng tham chiếu.
- Giữ transaction và connection lâu hơn.
- Tăng lock, log ghi, tải database và khả năng xung đột version.
- Làm việc cập nhật một field root trở nên đắt hơn mức mong đợi.

Ví dụ, một đơn hàng có 5 dòng hàng là aggregate nhỏ và dễ quản lý. Một tài khoản có hàng triệu bản ghi lịch sử giao dịch không nên chứa toàn bộ lịch sử như một collection owned child được thay thế mỗi lần save tài khoản. Lịch sử có thể là aggregate riêng, được tham chiếu bằng ID hoặc truy vấn qua repository riêng.

Thiết kế aggregate nên cân bằng:

- Những dữ liệu nào cần thay đổi nguyên tử cùng nhau?
- Những đối tượng nào có vòng đời phụ thuộc root?
- Tập child tối đa có giới hạn tự nhiên không?
- Những phần nào được truy cập/cập nhật độc lập?
- Có thể dùng value object embedded, bảng child hoặc aggregate riêng?

Đừng chia aggregate chỉ để giảm số hàng một cách máy móc; ranh giới phải phản ánh consistency boundary của nghiệp vụ.

## 11. Khi nào dùng custom SQL thay vì save toàn bộ aggregate?

Một số tác vụ cập nhật một giá trị đơn lẻ trên lượng dữ liệu lớn có thể phù hợp với câu lệnh SQL chuyên biệt:

```java
@Modifying
@Query("""
    UPDATE purchase_order
    SET status = :status
    WHERE id = :id
    """)
int updateStatus(@Param("id") Long id, @Param("status") String status);
```

Đây là ví dụ minh họa cho một modifying query trong repository; cú pháp annotation/import cần theo phiên bản Spring Data Relational cụ thể. Custom SQL/`JdbcTemplate` có thể tránh phải load và lưu toàn bộ aggregate, nhưng **bỏ qua aggregate persistence lifecycle**:

- Không tự động đồng bộ child collection.
- Không tự chạy domain method hoặc validation của aggregate.
- Có thể không cập nhật version theo cách mà các thao tác `save` mong đợi.
- Không tự động thực hiện domain event hoặc side effect mà service thông thường chạy.

Nếu dùng custom update, phải tự đảm bảo transaction, optimistic locking/version, validation, constraint và tính nhất quán với mọi đường ghi khác. Đặc biệt, một câu SQL cập nhật trực tiếp root nhưng không tăng version có thể khiến một aggregate snapshot cũ sau đó ghi đè thay đổi.

Chọn custom SQL khi có lý do rõ ràng như bulk update, báo cáo hoặc thao tác chuyên biệt đã được thiết kế. Đừng dùng nó như một cách né tránh việc xác định aggregate boundary.

## 12. Lỗi và tình huống thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Gọi save với object chỉ có ID và một field làm mất dữ liệu khác | Đang lưu partial object như toàn bộ aggregate | Load aggregate hiện tại, áp dụng thay đổi rồi save |
| Danh sách child biến mất sau PATCH | DTO không phân biệt field bị thiếu, null và danh sách rỗng | Thiết kế patch model giữ presence; chỉ thay collection khi client yêu cầu |
| Child được insert lại dù không đổi | Cách đồng bộ aggregate của Spring Data JDBC | Không dựa vào dirty checking; xem lại child identity, trigger và aggregate size |
| Có hai request ghi đè nhau | Thiếu version hoặc một đường ghi bypass version | Dùng `@Version` và đồng bộ mọi đường cập nhật |
| Lỗi optimistic locking | Object dựa trên version cũ | Tải lại, xử lý xung đột và áp dụng lại command có kiểm soát |
| Save root không lưu aggregate được tham chiếu | Nhầm external aggregate với owned child | Dùng `AggregateReference` cho ID; lưu aggregate kia qua repository riêng |
| Transaction vẫn để lại dữ liệu dở dang | Các lệnh nằm ở transaction khác nhau hoặc dùng connection ngoài Spring | Đặt transaction boundary ở service và dùng hạ tầng Spring-managed |
| Save chậm khi aggregate lớn | Quá nhiều child cần đồng bộ | Đánh giá ranh giới aggregate, kích thước child và mô hình truy cập |

Khi debug, hãy xem object đầy đủ trước save, version hiện tại, SQL được thực thi, số hàng bị ảnh hưởng và exception gốc. Đừng chỉ nhìn một câu UPDATE root để kết luận toàn bộ aggregate đã được lưu đúng.

## 13. Bài tập thực hành

**Bài 1 — Lưu mới.** Tạo một `PurchaseOrder` cùng hai `OrderLine`, gọi `save` và kiểm tra root ID cùng các khóa ngoại child trong database.

**Bài 2 — Cập nhật root.** Đọc đơn hàng, thay `status` rồi lưu. Quan sát các câu SQL root/child và xác nhận framework không cần dirty checking để lưu aggregate.

**Bài 3 — Thay đổi collection.** Thêm một dòng, sửa một dòng và xóa một dòng. So sánh trạng thái database trước/sau; quan sát chiến lược đồng bộ child.

**Bài 4 — PATCH.** Tạo DTO có thể phân biệt field `lines` không xuất hiện, `null`, danh sách rỗng và danh sách có phần tử. Đảm bảo PATCH chỉ thay collection khi hợp đồng API yêu cầu.

**Bài 5 — Concurrent update.** Bật `@Version`. Cho hai transaction cùng đọc một aggregate, lưu transaction thứ nhất, rồi thử lưu object cũ ở transaction thứ hai. Quan sát optimistic locking failure.

**Bài 6 — Aggregate boundary.** Thêm `AggregateReference<Customer, Long>` vào đơn hàng. Lưu/cập nhật đơn hàng và xác nhận khách hàng không bị lưu/xóa theo vòng đời owned child.

### Tài liệu tham khảo

- [Spring Data Relational — JDBC Aggregate Persistence](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): cách Spring Data JDBC lưu aggregate, entity mới và entity hiện hữu.
- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): entity references, aggregate references và mapping quan hệ.
- [Spring Data Relational — Optimistic Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html#jdbc.optimistic-locking): version property và xử lý cập nhật đồng thời.
