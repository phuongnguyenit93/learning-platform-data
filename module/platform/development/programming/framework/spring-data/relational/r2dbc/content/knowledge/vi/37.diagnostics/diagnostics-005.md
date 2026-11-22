# `save` thực hiện insert hoặc update khác dự kiến

Trong Spring Data R2DBC, `repository.save(entity)` không có nghĩa là database tự tìm một hàng trùng rồi quyết định insert hay update. Spring Data xác định trạng thái mới/cũ của entity trước, sau đó chọn thao tác insert hoặc update tương ứng. Vì vậy, nếu `save` tạo hàng mới trong khi bạn nghĩ đang cập nhật, hoặc chạy update trong khi bạn nghĩ đang insert, nguyên nhân thường nằm ở cách Spring Data nhận diện entity, giá trị `@Id`, thuộc tính `@Version`, hoặc hợp đồng `Persistable.isNew()`.

Điểm quan trọng là `save` không phải một lệnh upsert dựa trên mọi unique key. Nó cũng không tự thực hiện dirty checking như JPA. Hãy kiểm tra trạng thái entity ngay trước khi gọi `save`, xem SQL thực tế được gửi, và dùng entity mà publisher trả về sau khi insert nếu ID được database sinh.

## 1. `save` chọn insert hay update như thế nào?

Với repository reactive của Spring Data Relational, `save` thường dựa trên thông tin entity có mới hay không:

```java
return entityInformation.isNew(entity)
    ? entityOperations.insert(entity)
    : entityOperations.update(entity);
```

Đây là cách diễn đạt logic lựa chọn. Chi tiết triển khai nội bộ phụ thuộc phiên bản Spring Data, nhưng nguyên tắc cần hiểu là: trạng thái entity được quyết định trước khi thực hiện câu SQL.

```mermaid
flowchart TD
    A[repository.save(entity)] --> B{Entity được xem là new?}
    B -->|Yes| C[INSERT]
    B -->|No| D[UPDATE]
    C --> E[Database sinh ID nếu được cấu hình]
    E --> F[Publisher trả entity đã lưu]
    D --> G[UPDATE theo ID và version nếu có]
    G --> H[Publisher trả entity đã cập nhật hoặc lỗi]
```

Spring Data không nhất thiết chạy `SELECT` để kiểm tra hàng có tồn tại trước mỗi lần save. Việc phân loại new/existing dựa trên metadata và trạng thái của object, không phải một truy vấn dò database theo unique business key.

## 2. Thứ tự nhận diện entity mới

Các chiến lược phổ biến của Spring Data Relational có thể hiểu theo thứ tự sau:

1. Nếu entity triển khai `Persistable`, Spring Data dùng `isNew()` do entity cung cấp.
2. Nếu không, nếu entity có thuộc tính `@Version`, giá trị version được dùng để xác định trạng thái mới/cũ.
3. Nếu không có version property, Spring Data kiểm tra ID: ID null thường có nghĩa entity mới; ID primitive có giá trị mặc định như `0` có thể được xem là mới.

Vì vậy, không nên chỉ nhìn `id` mà kết luận insert/update nếu entity có `@Version` hoặc triển khai `Persistable`.

| Cấu hình entity | Trạng thái thường được nhận diện |
|---|---|
| Không có `@Version`, `Long id == null` | New → insert |
| Không có `@Version`, `Long id != null` | Existing → update |
| Có `@Version Long version == null` | New → insert |
| Có `@Version Long version != null` | Existing → update |
| Có `@Version long version == 0` | New → insert theo quy tắc primitive version |
| Triển khai `Persistable`, `isNew() == true` | New → insert |
| Triển khai `Persistable`, `isNew() == false` | Existing → update |

Với kiểu wrapper như `Long`, giá trị `0L` vẫn là một giá trị không null. Nếu dùng `@Version Long`, không nên khởi tạo version của entity mới thành `0L` nếu muốn Spring Data nhận diện nó là mới; thường để `null` và để framework quản lý version. Với primitive `long`, giá trị 0 có thể được coi là trạng thái mới.

## 3. `@Id` quyết định entity nào được nhận diện là có ID

Spring Data Relational dùng annotation `org.springframework.data.annotation.Id` để xác định thuộc tính định danh của entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;
    private String email;
}
```

Khi `id == null`, entity thường được xem là mới nếu không có chiến lược version hoặc `Persistable` ghi đè. Khi `id` có giá trị, entity thường được xem là đã tồn tại và `save` chọn update.

Hãy kiểm tra import của `@Id`. Với Spring Data R2DBC, dùng `org.springframework.data.annotation.Id`. Không mặc định rằng annotation `@Id` của một thư viện khác có cùng ý nghĩa đối với mapping metadata của Spring Data.

Nếu entity không có thuộc tính được Spring Data nhận diện là ID, mapping hoặc thao tác lưu có thể thất bại hoặc không hành xử như bạn dự kiến. Đừng suy luận trạng thái entity từ một field tên `id` nếu field đó không được ánh xạ làm identifier.

## 4. Lỗi thường gặp: ID được gán sẵn làm `save` chạy UPDATE

Giả sử ứng dụng nhập dữ liệu từ hệ thống khác và tự gán ID:

```java
Customer customer = new Customer(
    9001L,
    "An Nguyen",
    "an@example.test"
);

return customerRepository.save(customer);
```

Nếu entity không có `@Version` và không triển khai `Persistable`, ID `9001L` không null khiến Spring Data thường xem entity là existing. `save` chọn update.

Điều này có thể gây bất ngờ nếu mục tiêu của bạn là insert một hàng mới với ID được cấp từ hệ thống ngoài. Hãy chọn rõ ý định:

- Nếu muốn update hàng `9001`, dùng `save` với entity existing.
- Nếu muốn insert một hàng mới với ID được gán sẵn, dùng thao tác insert tường minh hoặc chiến lược `Persistable.isNew()` phù hợp.
- Nếu muốn insert-or-update theo business key, triển khai upsert theo dialect/SQL hoặc một workflow kiểm tra conflict có transaction phù hợp.

Không đổi ID thành null chỉ để ép insert nếu ID đó là khóa nghiệp vụ bắt buộc. Việc bỏ ID có thể khiến database sinh một ID khác hoặc làm mất liên kết với hệ thống nguồn.

## 5. Lỗi thường gặp: ID null nhưng version đã có giá trị

Khi entity có `@Version`, version có thể được ưu tiên để xác định trạng thái mới/cũ. Ví dụ:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version = 0L;

    private String name;
}
```

`version` là wrapper `Long` và đã được gán giá trị không null. Theo chiến lược nhận diện dựa trên version, entity có thể bị xem là existing dù `id` đang null. Kết quả là Spring Data đi theo nhánh update, dẫn đến lỗi hoặc SQL không khớp với ý định insert.

Với version wrapper, để entity mới có version null:

```java
@Version
private Long version;
```

Để Spring Data quản lý version khi insert/update. Không tự gán version ban đầu nếu chưa hiểu rõ quy tắc new-state của phiên bản framework đang dùng.

## 6. Lỗi thường gặp: version không được reset khi tạo entity mới

Một factory hoặc mapper có thể copy version từ object nguồn:

```java
Customer newCustomer = new Customer();
newCustomer.setId(null);
newCustomer.setVersion(source.getVersion());
newCustomer.setName(source.getName());
```

Nếu `source.getVersion()` khác null, entity mới có thể bị nhận diện là existing. Khi tạo entity mới từ request/DTO, chỉ copy các trường nghiệp vụ được phép; không copy ID hoặc version persistence từ entity cũ nếu không có chủ đích.

Nên có factory rõ nghĩa:

```java
public static Customer newCustomer(String name, String email) {
    Customer customer = new Customer();
    customer.setName(name);
    customer.setEmail(email);
    // id và version giữ trạng thái new theo mapping strategy.
    return customer;
}
```

Đối với update, tải entity hiện tại hoặc nhận một command có ID/version rõ ràng rồi áp dụng thay đổi theo quy tắc nghiệp vụ.

## 7. `@Version` ảnh hưởng cả new-state và optimistic locking

`@Version` có hai vai trò liên quan:

- Tham gia xác định entity mới/cũ.
- Bảo vệ update khỏi ghi đè thay đổi của transaction khác bằng optimistic locking.

Ví dụ:

```java
@Table("inventory_item")
public class InventoryItem {

    @Id
    private Long id;

    @Version
    private Long version;

    private String sku;
    private Integer availableQuantity;
}
```

Khi insert, framework khởi tạo version theo semantics của Spring Data Relational/driver. Khi update, câu lệnh thường dùng ID và version hiện tại trong điều kiện, đồng thời tăng version.

SQL khái niệm:

```sql
UPDATE inventory_item
SET available_quantity = :quantity,
    version = :nextVersion
WHERE id = :id
  AND version = :currentVersion;
```

Nếu không có hàng nào khớp vì entity đã stale hoặc hàng bị xóa, Spring Data có thể phát `OptimisticLockingFailureException` thay vì âm thầm ghi đè. Chi tiết SQL/version increment do framework và dialect quản lý; không tự tăng version trước khi gọi `save` trừ khi ứng dụng có lý do rõ.

## 8. Lỗi thường gặp: `Persistable.isNew()` trả sai

Entity có thể triển khai `Persistable<ID>` để tự quyết định trạng thái new:

```java
import org.springframework.data.domain.Persistable;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;

public class ImportedCustomer implements Persistable<String> {

    @Id
    private String id;

    private String displayName;

    @Transient
    private boolean newEntity;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        this.newEntity = false;
    }
}
```

Đây là ví dụ về cơ chế; constructor/factory của ứng dụng phải đặt `newEntity` đúng cho object mới và object được đọc từ database. Sau khi insert thành công, trạng thái cần chuyển sang existing trước lần save tiếp theo. Có thể thực hiện bằng lifecycle callback phù hợp hoặc cập nhật trạng thái trên entity được trả về nếu entity mutable.

Hai lỗi đối nghịch có thể xảy ra:

- `isNew()` luôn trả `true`: mỗi lần save đều chọn insert, có thể gây duplicate key.
- `isNew()` luôn trả `false`: entity mới bị đưa vào nhánh update, có thể không tạo hàng.

Không triển khai `Persistable` chỉ để né một lỗi mapping mà chưa xác định rõ lifecycle. Nếu không cần chiến lược tùy chỉnh, để Spring Data dựa vào ID/version thường đơn giản hơn.

## 9. `Persistable` và `@Version` không nên mâu thuẫn

Khi entity triển khai `Persistable`, `isNew()` trở thành hợp đồng quan trọng mà ứng dụng chịu trách nhiệm. Hãy tránh để `isNew()` trả một trạng thái không phù hợp với ID/version hiện tại.

Ví dụ không nhất quán:

- Entity đã được lưu, ID đã có và version đã tăng, nhưng `isNew()` vẫn true.
- Entity vừa được tạo với ID gán sẵn, nhưng `isNew()` false dù muốn insert.
- Object được load từ database nhưng factory khởi tạo `newEntity = true`.

Hãy xác định các đường tạo object:

| Nguồn tạo entity | Trạng thái cần có |
|---|---|
| Factory tạo mới cho insert | New |
| Entity đọc từ repository/database | Existing |
| DTO chuyển thành entity để update | Existing theo ID/version đã xác thực |
| Dữ liệu import có ID gán sẵn cần insert | New theo chiến lược được thiết kế rõ |
| Entity vừa insert thành công | Existing cho lần lưu tiếp theo |

Nếu có nhiều đường tạo entity, test riêng từng factory/mapper để không vô tình gán sai trạng thái.

## 10. `save` không phải UPSERT theo unique business key

Giả sử bảng có unique key `email`:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL
);
```

Ứng dụng tạo entity mới với `id == null`, nhưng email đã tồn tại:

```java
Customer customer = new Customer(null, "an@example.test", "An Updated");
return customerRepository.save(customer);
```

Spring Data vẫn có thể chọn insert vì ID cho thấy entity mới. Database sau đó từ chối insert do unique constraint. `save` không tự tìm theo email để chuyển thành update.

Ngược lại, nếu entity có ID không null nhưng hàng đó không tồn tại, `save` chọn update; nó không tự fallback sang insert chỉ vì update không tìm thấy hàng.

| Trạng thái entity | Database | Hành vi mong đợi của `save` |
|---|---|---|
| New, ID null | Business key chưa tồn tại | Insert |
| New, ID null | Business key đã tồn tại | Insert và có thể nhận unique violation |
| Existing, ID có giá trị | Hàng tồn tại | Update |
| Existing, ID có giá trị | Hàng không tồn tại | Update không khớp; có thể phát optimistic locking error nếu có version |

Nếu yêu cầu là “nếu email tồn tại thì cập nhật, nếu chưa có thì tạo”, hãy thiết kế upsert theo unique key. Cú pháp có thể khác giữa PostgreSQL (`ON CONFLICT`), MySQL (`ON DUPLICATE KEY UPDATE`) và SQL Server/Oracle (`MERGE` hoặc giải pháp phù hợp). Cần kiểm tra concurrency và trả về generated values theo dialect.

## 11. `save` không thực hiện dirty checking như JPA

Spring Data R2DBC thuộc Spring Data Relational, không có persistence context kiểu JPA để theo dõi mọi thay đổi field trên entity đã được load.

Khi gọi `save(entity)` với entity existing, framework thực hiện update theo mapping metadata. Không nên giả định nó chỉ update các field đã thay đổi. Các thuộc tính persistent khác trong entity có thể được đưa vào câu update theo chiến lược mapping.

Ví dụ nguy hiểm:

```java
Customer partial = new Customer();
partial.setId(10L);
partial.setDisplayName("New name");
// email không được gán, nên vẫn null.

return customerRepository.save(partial);
```

Nếu entity được nhận diện là existing, update có thể ghi `email = NULL` thay vì giữ nguyên email cũ. Đây không phải partial update an toàn.

Đối với update một phần, có thể:

- Tải entity hiện tại rồi thay đổi field cần cập nhật và save.
- Dùng `R2dbcEntityTemplate.update(...).matching(...).apply(...)` với các cột cụ thể.
- Dùng `DatabaseClient` viết `UPDATE` chỉ thay đổi những cột cần thiết.
- Dùng command DTO biểu diễn rõ field được phép thay đổi.

Không dùng entity thiếu dữ liệu như một patch DTO rồi gọi `save` nếu không muốn các cột null bị ghi xuống database.

## 12. Entity immutable: phải dùng giá trị mà `save` trả về

Với entity immutable hoặc Java record, Spring Data có thể tạo instance mới chứa ID được database sinh thay vì thay đổi object ban đầu.

Ví dụ:

```java
@Table("purchase_order")
public record PurchaseOrder(
    @Id Long id,
    String orderNo,
    String status
) {}
```

Lưu entity mới:

```java
PurchaseOrder input = new PurchaseOrder(null, "ORD-100", "NEW");

return orderRepository.save(input)
    .flatMap(saved -> {
        // saved.id() có thể đã có generated ID.
        return orderRepository.findById(saved.id());
    });
```

Không bỏ qua giá trị được phát ra:

```java
// Không nên nếu cần ID do database sinh.
orderRepository.save(input).thenReturn(input);
```

`input` vẫn có thể có `id == null` vì record không thay đổi được. Hãy tiếp tục dùng `saved` được phát ra từ publisher.

## 13. Reactive publisher là lazy: subscription có thể thực thi SQL

Các thao tác R2DBC thường được thực hiện khi publisher được subscribe. Chỉ tạo `Mono` từ `save` không có nghĩa SQL đã chạy:

```java
Mono<Customer> saveOperation = customerRepository.save(customer);
```

Nếu publisher không được subscribe, thao tác có thể chưa được thực hiện. Ngược lại, mỗi subscription vào một publisher cold có thể chạy lại thao tác:

```java
Mono<Customer> saveOperation = customerRepository.save(newCustomer);

// Hai nhánh subscribe độc lập có thể thực hiện thao tác lưu hai lần.
return Mono.zip(saveOperation, saveOperation);
```

Đừng tái sử dụng một publisher ghi theo cách vô tình tạo nhiều subscription. Hãy điều phối trong một reactive chain:

```java
return customerRepository.save(newCustomer)
    .flatMap(saved -> sendWelcomeEvent(saved).thenReturn(saved));
```

Nếu cần chia sẻ một kết quả đã thực thi cho nhiều consumer, hãy thiết kế sharing/caching có chủ đích và hiểu lifecycle của publisher. Không dùng `subscribe()` thủ công trong service để “ép” save chạy rồi tiếp tục xử lý bằng một chain khác.

## 14. Vì sao một entity có thể INSERT nhiều lần?

Các nguyên nhân thường gặp:

- ID vẫn null vì entity immutable ban đầu không nhận generated ID.
- Mỗi request tạo một instance mới với ID null.
- `Persistable.isNew()` luôn trả true.
- `@Version` wrapper luôn null do mapper không gán version sau khi load.
- Cùng publisher save được subscribe nhiều lần.
- Retry lặp insert sau timeout mà không có idempotency.
- Mapper tạo entity mới thay vì cập nhật entity existing.

Ví dụ retry insert sau timeout:

1. Database đã insert và commit.
2. Response bị mất khi connection đứt.
3. Ứng dụng thấy lỗi và retry với entity vẫn ID null.
4. Lần retry chọn insert lần nữa.
5. Unique business key có thể chặn duplicate, hoặc hàng duplicate được tạo nếu không có constraint.

Đối với thao tác ghi có thể gặp commit outcome không xác định, dùng idempotency key hoặc unique business key để xác định một yêu cầu chỉ được áp dụng một lần theo hợp đồng nghiệp vụ.

## 15. Vì sao một entity có thể UPDATE khi bạn muốn INSERT?

Các nguyên nhân thường gặp:

- ID được gán sẵn và khác null.
- `@Version` wrapper đã có giá trị khác null.
- `Persistable.isNew()` trả false.
- Entity được map từ DTO cũ mang theo ID/version.
- Primitive ID/version có giá trị không đúng kỳ vọng.
- Factory tạo entity mới nhưng copy persistence metadata từ object đã lưu.
- Dùng nhầm entity đã được load từ database khi mục tiêu là tạo bản ghi mới.

Để insert rõ ràng, dùng thao tác insert tường minh khi API phù hợp. Đừng xóa ID/version tùy tiện trên entity existing vì có thể làm mất quan hệ hoặc phá optimistic locking.

## 16. Vì sao UPDATE không thay đổi hàng nào?

Nếu `save` chọn update nhưng không có hàng phù hợp, hãy kiểm tra:

- ID có đúng không và có trỏ tới database/schema/table hiện tại không?
- Entity có version stale không?
- Hàng đã bị xóa bởi transaction khác không?
- `@Table`/`@Column` có ánh xạ đúng tên object không?
- ConnectionFactory có trỏ nhầm môi trường/tenant không?
- Query update có điều kiện optimistic version hay điều kiện tùy chỉnh nào?

Với entity có `@Version`, cập nhật không khớp ID/version thường được biểu diễn bằng `OptimisticLockingFailureException` để báo xung đột. Với entity không version, không nên giả định Spring Data luôn phát hiện mọi trường hợp stale theo cùng cách. Nếu cần biết chính xác số hàng bị ảnh hưởng, dùng update query/`DatabaseClient` và kiểm tra `rowsUpdated()` hoặc thiết kế concurrency control rõ ràng.

## 17. Phân biệt optimistic locking failure với database error khác

`OptimisticLockingFailureException` thường cho biết update/delete không khớp trạng thái version mà ứng dụng đang giữ. Đây không giống:

- `DuplicateKeyException`: vi phạm unique key.
- `DataIntegrityViolationException`: vi phạm constraint.
- `TransientDataAccessResourceException`: lỗi tài nguyên có thể tạm thời.
- `R2dbcTimeoutException`: thao tác vượt timeout.
- `BadSqlGrammarException`: câu SQL không hợp lệ.
- Authentication/authorization failure: thông tin xác thực hoặc quyền không đúng.

Không retry tất cả exception theo cùng một cách. Optimistic conflict thường cần đọc lại dữ liệu và xử lý theo nghiệp vụ; unique conflict có thể là request trùng; connection failure có thể retry nếu operation idempotent.

## 18. `@Id` và generated ID: kiểm tra mapping

Với ID do database sinh, entity mới thường để ID null:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String email;
    private String displayName;
}
```

Schema có identity/auto-increment phù hợp database. Khi insert thành công, Spring Data và R2DBC driver cần hỗ trợ lấy generated value và gán vào entity kết quả.

Không mặc định annotation JPA `@GeneratedValue` là cơ chế cần dùng cho Spring Data R2DBC. Spring Data Relational có quy tắc mapping/generated identifier riêng theo dialect. Kiểm tra tài liệu phiên bản và database driver.

Nếu ID không được trả về:

- Kiểm tra cột database có identity/sequence/default không.
- Kiểm tra `@Id` được đặt đúng field.
- Kiểm tra driver có hỗ trợ generated values theo đường insert đang dùng.
- Kiểm tra entity type và mapping constructor/wither.
- Kiểm tra code có dùng entity trả về từ `save` không.

## 19. Assigned ID và generated ID là hai chiến lược khác nhau

Không nên trộn hai chiến lược trong cùng một entity mà không định nghĩa quy tắc:

| Chiến lược | ID trước insert | Trạng thái new | Lưu ý |
|---|---|---|---|
| Database-generated ID | null | New theo ID/version | Database tạo ID; dùng entity trả về |
| Application-assigned ID | Có giá trị | Cần chiến lược newness phù hợp | ID có sẵn không đồng nghĩa hàng đã tồn tại |
| Imported ID cần giữ nguyên | Có giá trị | Có thể dùng `Persistable.isNew()` hoặc insert explicit | Bảo đảm duplicate ID được xử lý đúng |
| Existing entity | Có giá trị | Existing | Update theo ID/version |

Nếu một hệ thống dùng ID UUID do application tạo, ID luôn có giá trị ngay cả trước insert. Khi đó, chỉ dựa vào `id == null` không đủ để nhận diện new. Có thể dùng `Persistable` với lifecycle đúng, version property theo quy tắc Spring Data, hoặc gọi insert tường minh.

## 20. Sử dụng `Persistable` cho ID được gán từ ứng dụng

Khi ID được tạo trước khi lưu và bạn vẫn muốn dùng `repository.save`, `Persistable` cho phép mô tả trạng thái entity:

```java
public class ExternalRecord implements Persistable<UUID> {

    @Id
    private UUID id;

    @Transient
    private boolean newEntity;

    public ExternalRecord(UUID id) {
        this.id = id;
        this.newEntity = true;
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        this.newEntity = false;
    }
}
```

Sau khi insert thành công, trạng thái cần chuyển sang false:

```java
return externalRecordRepository.save(record)
    .doOnNext(ExternalRecord::markPersisted);
```

Ví dụ này giả định entity mutable và method được gọi trên instance được trả về. Với entity immutable, hãy biểu diễn trạng thái bằng factory/constructor/callback phù hợp thay vì thay đổi object. Entity được đọc từ database cũng phải được khởi tạo với `newEntity = false`; nếu constructor persistence luôn đánh dấu true, lần save tiếp theo sẽ lại insert.

`@Transient` bảo đảm cờ trạng thái này không trở thành cột database. Hãy kiểm thử cả đường tạo mới, save thành công, load lại và save lần tiếp theo.

## 21. Dùng thao tác INSERT/UPDATE tường minh khi ý định phải rõ

Nếu use case biết chắc cần insert, dùng API insert tường minh của `R2dbcEntityTemplate` hoặc SQL insert qua `DatabaseClient`, thay vì để trạng thái object quyết định:

```java
return r2dbcEntityTemplate.insert(ExternalRecord.class)
    .using(record);
```

API cụ thể có thể khác nhẹ theo phiên bản Spring Data Relational; kiểm tra signature của `R2dbcEntityTemplate` trong dự án. Insert tường minh sẽ không biến thành update chỉ vì ID có giá trị.

Nếu cần update một số cột:

```java
return r2dbcEntityTemplate.update(Customer.class)
    .matching(Query.query(Criteria.where("id").is(customerId)))
    .apply(Update.update("displayName", newName));
```

Đây là ví dụ update theo mapping metadata. Cần kiểm tra property name và API theo version. Với update nhiều cột hoặc điều kiện phức tạp, `DatabaseClient` cho phép viết SQL tường minh và kiểm tra số hàng bị ảnh hưởng.

Thao tác tường minh làm rõ ý định của use case:

- Insert: phải tạo hàng mới; duplicate ID/unique key là lỗi.
- Update: phải thay đổi hàng hiện có; nếu không có hàng phù hợp, ứng dụng xử lý theo hợp đồng.
- Upsert: cần hành vi insert-or-update rõ theo unique key và dialect.

## 22. `DatabaseClient` không dùng entity new-state detection

Khi gọi SQL trực tiếp:

```java
databaseClient.sql("""
        INSERT INTO customer(email, display_name)
        VALUES (:email, :displayName)
        """)
    .bind("email", email)
    .bind("displayName", displayName)
    .fetch()
    .rowsUpdated();
```

Ứng dụng đã quyết định rõ INSERT trong câu SQL. `Persistable.isNew()`, `@Version` và logic `repository.save` không tự chuyển câu lệnh này thành update.

Tương tự, một câu `UPDATE` qua `DatabaseClient` không tự thực hiện optimistic locking chỉ vì DTO/entity có `@Version`. Nếu cần version check, hãy đưa version vào điều kiện SQL và tăng version tường minh, hoặc dùng API entity operation có hỗ trợ optimistic locking theo mapping.

Đây là lý do cần phân biệt lỗi do `save` với lỗi do custom SQL. Không áp dụng giả định của Repository cho mọi đường ghi R2DBC.

## 23. `saveAll` cũng áp dụng new-state cho từng entity

`saveAll` không phải lúc nào cũng là một câu SQL bulk insert/update duy nhất. Framework có thể xử lý các entity theo trạng thái mới/cũ và driver/dialect có cách thực thi riêng.

Nếu một collection có entity ID null, entity ID gán sẵn, entity version khác nhau hoặc `Persistable.isNew()` không nhất quán, một batch save có thể trộn insert và update ngoài dự kiến.

Trước khi gọi `saveAll`, hãy kiểm tra:

- Tất cả entity có cùng chiến lược ID/newness không?
- Có entity nào đã được lưu trước đó không?
- `Persistable.isNew()` có đúng cho từng object không?
- Có unique business key bị trùng trong batch không?
- Driver/database hỗ trợ batch/generated key theo cách nào?
- Một lỗi ở giữa batch ảnh hưởng transaction ra sao?

Nếu use case cần bulk insert thuần, hãy cân nhắc API insert/batch rõ ràng và test trên database/driver mục tiêu. Không giả định `saveAll` luôn có hiệu năng hoặc atomicity giống một bulk SQL duy nhất.

## 24. Transaction và trạng thái entity sau lỗi

Nếu insert/update nằm trong reactive transaction và một bước sau đó thất bại, transaction có thể rollback. Tuy nhiên, object Java trong memory có thể đã được cập nhật ID/version bởi framework hoặc callback trước khi transaction kết thúc.

Điều đó có nghĩa trạng thái object sau lỗi không nhất thiết phản ánh trạng thái database. Ví dụ entity mutable đã nhận generated ID nhưng transaction sau đó rollback; ID trong object vẫn có thể tồn tại dù hàng không còn trong database.

Không tái sử dụng mù quáng entity từ transaction thất bại. Hãy đọc lại trạng thái cần thiết hoặc tạo một command/aggregate mới dựa trên dữ liệu đã xác minh. Với thao tác ghi có retry, ưu tiên idempotency key và transaction mới.

## 25. Một publisher `save` được retry có thể insert lặp

Ví dụ:

```java
return customerRepository.save(new Customer(null, email, name))
    .retryWhen(Retry.max(2));
```

Nếu lỗi xảy ra sau khi database commit nhưng trước khi client nhận response, lần retry có thể tạo một entity mới vẫn có ID null và chọn insert lần nữa. `retryWhen` không biết commit đã xảy ra hay chưa.

Đối với read, retry transient error thường ít rủi ro hơn. Với write, hãy:

- Dùng idempotency key hoặc unique business key.
- Tra cứu operation đã hoàn tất trước khi lặp lại.
- Retry toàn transaction mới, không retry statement trong transaction hỏng.
- Chỉ retry lỗi được phân loại transient.
- Giới hạn attempt, dùng backoff/jitter và deadline.

Không retry mọi exception từ `save`. Unique violation, validation failure hoặc lỗi mapping không được sửa bằng cách gửi lại cùng câu lệnh.

## 26. Chẩn đoán SQL thực tế mà `save` gửi đi

Khi kết quả khác dự kiến, log SQL/instrumentation là bằng chứng quan trọng. Hãy xác định:

1. Spring Data gửi `INSERT` hay `UPDATE`?
2. Bảng/schema được nhắm tới là gì?
3. Cột ID có được đưa vào INSERT không?
4. UPDATE có điều kiện `WHERE id = ...` và version không?
5. Các cột nào được cập nhật, có cột null ngoài ý muốn không?
6. Database trả rows updated, generated ID hoặc constraint error nào?
7. Có bao nhiêu lần subscription/SQL execution cho một request?

Có thể dùng logging của driver, datasource/R2DBC proxy hoặc instrumentation phù hợp. Cấu hình logging phụ thuộc driver và Spring version. Chỉ bật ở môi trường phát triển/test hoặc dùng sampling/redaction trong production; không log password và dữ liệu nhạy cảm trong bind parameter.

## 27. Kiểm tra entity ngay trước khi save

Tạm thời log trạng thái không nhạy cảm ngay trước thao tác:

```java
log.debug("Saving customer: id={}, version={}, isNew={}",
    customer.getId(),
    customer.getVersion(),
    customer instanceof Persistable<?> persistable
        ? persistable.isNew()
        : "not-persistable");
```

Nếu entity không triển khai `Persistable`, vẫn cần xem version property và ID. Có thể viết helper chỉ dùng trong test/debug để hiển thị trạng thái theo chiến lược của entity; không gọi một API nội bộ không ổn định của framework trong production chỉ để log.

Đối với dữ liệu nhạy cảm, không log email, tên hoặc payload; chỉ log ID kỹ thuật/correlation ID đã được phép.

## 28. Kiểm tra mapping table, schema và ConnectionFactory

Đôi khi SQL đúng nhánh nhưng bạn đang nhìn nhầm database/table:

- `@Table` trỏ tới tên bảng khác với bảng đang kiểm tra.
- `schema` mặc định hoặc `search_path` làm query chạy vào schema khác.
- Repository dùng `ConnectionFactory` của test/tenant/database khác.
- Profile Spring Boot đang hoạt động khác môi trường dự kiến.
- Database URL trỏ tới read replica hoặc cluster endpoint không đúng.
- Migration tạo một bảng khác tên hoặc ở schema khác.

Hãy kiểm tra endpoint, database, schema và table thực tế của connection. Không log credential; chỉ log host/database/schema ở mức đã redaction và phù hợp chính sách.

## 29. Phân biệt `save` update toàn entity với partial update

Nếu bạn muốn thay đổi một cột, không nên dựng một entity chỉ có ID và field đó rồi save nếu các field còn lại có thể null.

Ví dụ update trạng thái:

```java
public Mono<Integer> updateStatus(Long id, String status) {
    return databaseClient.sql("""
            UPDATE purchase_order
            SET status = :status
            WHERE id = :id
            """)
        .bind("status", status)
        .bind("id", id)
        .fetch()
        .rowsUpdated()
        .map(Long::intValue);
}
```

Kiểu trả về `rowsUpdated()` có thể là `Mono<Long>` tùy phiên bản Spring; ví dụ chuyển sang `Integer` chỉ để minh họa và nên giữ `Long` nếu có khả năng cập nhật nhiều hàng. Có thể dùng `Mono<Long>` trực tiếp:

```java
public Mono<Long> updateStatus(Long id, String status) {
    return databaseClient.sql("""
            UPDATE purchase_order
            SET status = :status
            WHERE id = :id
            """)
        .bind("status", status)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
```

Khi `rowsUpdated == 0`, service có thể trả not found hoặc conflict theo hợp đồng. Nếu cần optimistic locking, thêm `AND version = :version` và tăng version trong cùng câu lệnh.

## 30. Ví dụ optimistic update tường minh

```sql
UPDATE inventory_item
SET available_quantity = :quantity,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
```

Ứng dụng kiểm tra số hàng bị ảnh hưởng:

```java
return databaseClient.sql(UPDATE_INVENTORY_SQL)
    .bind("quantity", newQuantity)
    .bind("id", id)
    .bind("expectedVersion", expectedVersion)
    .fetch()
    .rowsUpdated()
    .flatMap(updated -> updated == 1
        ? Mono.empty()
        : Mono.error(new OptimisticLockingFailureException(
            "Inventory item changed or no longer exists")));
```

Đây là custom SQL, nên ứng dụng tự quản lý version increment và xử lý zero rows. Nếu dùng Repository/Template entity operation có `@Version`, Spring Data có thể thực hiện cơ chế optimistic locking thay cho bạn.

## 31. Kiểm thử insert/update theo new-state

Integration test trên database thật nên có các trường hợp:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Entity ID null, không version | Insert và nhận ID |
| Entity mới có version null | Insert và nhận version khởi tạo |
| Entity có ID từ database | Update hàng tương ứng |
| Entity có ID gán sẵn nhưng cần insert | Insert tường minh hoặc `Persistable.isNew() == true` |
| `Persistable.isNew() == true` | Insert |
| `Persistable.isNew() == false` | Update |
| Version stale | Optimistic locking failure |
| ID existing nhưng hàng đã xóa | Xử lý zero-row/version failure theo mapping |
| Business key trùng nhưng ID null | Unique constraint error, không tự upsert |
| Immutable entity được insert | Dùng entity trả về với generated ID |

Ví dụ test insert rồi update:

```java
@Test
void savesNewEntityThenUpdatesReturnedEntity() {
    Customer input = new Customer(null, "An", "an-" + UUID.randomUUID() + "@example.test");

    StepVerifier.create(customerRepository.save(input)
            .flatMap(saved -> {
                assertThat(saved.getId()).isNotNull();
                saved.setName("An Updated");
                return customerRepository.save(saved);
            })
            .flatMap(updated -> customerRepository.findById(updated.getId())))
        .assertNext(found -> assertThat(found.getName()).isEqualTo("An Updated"))
        .verifyComplete();
}
```

Test này dùng entity mutable để minh họa; với immutable entity, tạo instance mới từ `saved` hoặc dùng `withName(...)` rồi tiếp tục với giá trị trả về.

## 32. Kiểm thử `Persistable` lifecycle

Nếu dùng `Persistable`, cần kiểm tra cả trạng thái trước và sau insert:

1. Factory tạo mới trả `isNew() == true`.
2. Save chọn insert và database tạo hàng.
3. Entity trả về có ID hợp lệ.
4. Trạng thái được chuyển thành existing sau insert.
5. Save lần tiếp theo chọn update.
6. Entity được load từ database có `isNew() == false`.

Nếu test chỉ xác nhận lần insert đầu tiên, lỗi `isNew()` luôn true có thể bị bỏ sót và chỉ xuất hiện khi lưu entity lần thứ hai.

## 33. Kiểm thử subscription và retry

Với publisher ghi, test cần xác nhận số lần SQL execution:

- Một subscription thực hiện một lần lưu theo hợp đồng.
- Không vô tình subscribe cùng cold publisher ở nhiều nhánh.
- Retry chỉ xảy ra với lỗi được phân loại transient.
- Retry ghi dùng idempotency key và không tạo duplicate.
- Lỗi sau commit nhưng trước response được mô phỏng bằng fault injection nếu nghiệp vụ cần kiểm chứng.

Không dùng `StepVerifier` để subscribe nhiều lần vào cùng publisher nếu mục tiêu là kiểm tra một lần save. Mỗi `StepVerifier.create(...)` sẽ subscribe publisher; hãy tạo publisher mới hoặc cache có chủ đích cho từng kịch bản.

## 34. Những nguyên nhân khác khiến kết quả có vẻ ngược dự kiến

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Gọi save nhưng không có SQL | Publisher chưa được subscribe | Theo dõi reactive chain và terminal subscriber |
| SQL insert chạy hai lần | Publisher cold được subscribe nhiều lần hoặc retry | Đếm query execution, xem operator/retry |
| Save insert dù ID đã có | Version null hoặc `Persistable.isNew()` true | Kiểm tra thứ tự new-state detection |
| Save update dù ID null | Version wrapper khác null hoặc `Persistable.isNew()` false | Kiểm tra version và custom newness |
| Save update sai hàng | ID được map sai hoặc repository trỏ nhầm schema/database | Kiểm tra `@Id`, SQL và ConnectionFactory |
| Update ghi null vào cột khác | Dùng partial entity rồi save | Tải entity đầy đủ hoặc dùng partial update |
| Duplicate key khi insert | Business key đã tồn tại; save không phải upsert | Dùng unique key/upsert có chủ đích |
| Update không ảnh hưởng hàng | ID sai, hàng đã xóa hoặc version stale | Kiểm tra rows updated và optimistic locking |
| ID không xuất hiện sau insert | Không dùng entity trả về hoặc driver/generated mapping sai | Kiểm tra generated values và immutable mapping |
| Batch save có cả insert và update | New-state khác nhau giữa các entity | Kiểm tra ID/version/isNew từng phần tử |
| Save sau load lại thành insert | `Persistable.isNew()` hoặc version bị khởi tạo sai | Kiểm tra mapping constructor và lifecycle flag |

## 35. Quy trình chẩn đoán nhanh

Khi `save` chạy insert/update khác dự kiến, thực hiện theo thứ tự:

**Bước 1 — Xác nhận entity thực tế.** Ghi nhận ID, version và `isNew()` ngay trước khi subscribe.

**Bước 2 — Kiểm tra mapping metadata.** Xác nhận đúng `@Id`, `@Version`, `@Table`, schema và column mapping.

**Bước 3 — Xác định chiến lược newness.** Kiểm tra entity có `Persistable` không; nếu không, xem version trước ID.

**Bước 4 — Xem SQL thực tế.** Xác nhận Spring Data gửi INSERT hay UPDATE, điều kiện WHERE và cột được ghi.

**Bước 5 — Kiểm tra dữ liệu database.** Xác nhận hàng có tồn tại trong đúng database/schema/table và unique key nào đang áp dụng.

**Bước 6 — Kiểm tra giá trị trả về.** Dùng entity phát ra từ `save`, đặc biệt khi ID/version được sinh hoặc thay đổi.

**Bước 7 — Kiểm tra reactive subscription.** Xác nhận publisher chỉ được subscribe theo số lần mong đợi và retry có chủ đích.

**Bước 8 — Xác định transaction outcome.** Nếu có lỗi connection/timeout, kiểm tra commit uncertainty và không retry ghi mù.

**Bước 9 — Chọn API đúng ý định.** Dùng insert/update tường minh hoặc upsert theo business key nếu `save` không diễn đạt đúng use case.

**Bước 10 — Thêm regression test.** Kiểm thử new/existing, assigned/generated ID, version, immutable entity và retry trên database thật.

## 36. Kết luận

Trong Spring Data R2DBC, `save` chọn INSERT hay UPDATE dựa trên trạng thái new/existing của entity. Nếu entity triển khai `Persistable`, `isNew()` quyết định; nếu không, `@Version` có thể được kiểm tra trước ID; khi không có version, ID thường quyết định. Vì vậy, ID gán sẵn, version wrapper được khởi tạo sai, cờ `isNew()` không chuyển trạng thái hoặc mapper làm mất ID đều có thể khiến thao tác khác dự kiến.

`save` không phải upsert theo unique business key và không thực hiện dirty checking như JPA. Với entity immutable hoặc ID do database sinh, hãy dùng entity được publisher trả về. Với update một phần, dùng API update tường minh thay vì save một object thiếu field. Khi cần insert, update hoặc upsert có semantics rõ ràng, chọn đúng API/SQL cho ý định đó. Kết hợp kiểm tra SQL thực tế, new-state, transaction và subscription sẽ giúp xác định chính xác nguyên nhân thay vì suy đoán từ tên method `save`.
