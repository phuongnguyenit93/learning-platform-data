# Callback, auditing và optimistic locking khi bỏ qua quy trình lưu aggregate

Trong **Spring Data Relational JDBC**, gọi `repository.save(aggregate)` hoặc dùng `JdbcAggregateTemplate` sẽ đi qua cơ chế lưu aggregate của Spring Data. Cơ chế này hiểu mapping của aggregate root, xử lý các entity con, áp dụng entity callbacks, auditing và optimistic locking theo cấu hình.

Khi cần một thao tác ghi hẹp, ứng dụng có thể dùng `@Modifying @Query`, `JdbcTemplate`, `NamedParameterJdbcTemplate` hoặc JDBC trực tiếp. Những đường ghi này thực thi DML ở mức SQL và **không tự chạy quy trình lưu aggregate**. Vì vậy, callback có thể không được gọi, các trường audit không tự cập nhật và `@Version` không tự kiểm tra/xác thực phiên bản.

Đây là khác biệt quan trọng khi tối ưu các lệnh cập nhật nhỏ. Một câu `UPDATE` trực tiếp có thể hiệu quả, nhưng người viết lệnh phải chủ động giữ các quy tắc mà aggregate save trước đó đảm nhiệm: cập nhật audit, kiểm tra version, bảo toàn invariant, transaction và các tác động phụ cần thiết.

## 1. Hai đường ghi dữ liệu khác nhau

Giả sử một đơn hàng có mã, trạng thái, thời gian cập nhật và version. Ứng dụng có thể ghi qua repository:

```java
PurchaseOrder order = orders.findById(orderId)
        .orElseThrow();

order.markAsPaid();

orders.save(order);
```

Hoặc cập nhật trực tiếp một cột:

```java
jdbcTemplate.update(
        "UPDATE orders SET status = ? WHERE id = ?",
        "PAID",
        orderId
);
```

Hai đoạn code đều có thể thay đổi cột `status`, nhưng đường đi bên trong khác nhau.

```mermaid
flowchart TD
    A[Application service]
    A --> B[repository.save / JdbcAggregateTemplate]
    A --> C[@Modifying @Query / JdbcTemplate / JDBC]

    B --> D[Aggregate mapping]
    D --> E[Entity callbacks]
    E --> F[Auditing callback]
    F --> G[Optimistic version check]
    G --> H[SQL for root and dependent entities]
    H --> I[(Database)]

    C --> J[Execute explicit SQL]
    J --> I

    C -. no automatic aggregate lifecycle .-> K[Caller owns audit, version and invariants]
```

| Khả năng | Aggregate-aware save | Direct DML |
|---|---|---|
| Ánh xạ aggregate root | Có | Không tự động |
| Xử lý `@MappedCollection` | Theo aggregate mapping | Chỉ khi SQL/FK được viết để làm việc đó |
| Entity callbacks | Có trong lifecycle operation tương ứng | Không tự động |
| Auditing annotations | Được auditing infrastructure xử lý khi callback chạy | Không tự động |
| `@Version` optimistic locking | Được Spring Data JDBC quản lý | Phải tự thêm version predicate và tăng version |
| Domain methods/invariant | Có thể được áp dụng trước khi save | Không tự chạy |
| SQL cụ thể | Framework tạo theo mapping | Người viết kiểm soát trực tiếp |

Direct DML không phải lúc nào cũng sai. Nó phù hợp với các lệnh cập nhật đơn giản, batch, counter hoặc trạng thái có phạm vi rõ. Điều cần tránh là giả định các tiện ích của aggregate save vẫn tự hoạt động sau khi chuyển sang đường SQL trực tiếp.

## 2. Entity callbacks trong Spring Data JDBC

Entity callback là điểm mở rộng cho phép chạy logic tại các giai đoạn của lifecycle mapping/persistence. Chúng hữu ích khi cần chuẩn hóa dữ liệu, bổ sung metadata hoặc phản ứng trước/sau thao tác lưu và đọc aggregate.

Các callback thường gặp trong Spring Data Relational gồm:

| Callback | Thời điểm khái quát | Mục đích thường dùng |
|---|---|---|
| `BeforeConvertCallback` | Trước khi aggregate được chuyển thành dạng relational | Chuẩn hóa hoặc bổ sung giá trị trước conversion |
| `BeforeSaveCallback` | Trước khi aggregate change được ghi xuống database | Điều chỉnh dữ liệu hoặc quan sát aggregate change |
| `AfterSaveCallback` | Sau khi aggregate được lưu | Thực hiện xử lý sau khi save thành công |
| `AfterConvertCallback` | Sau khi dữ liệu relational được chuyển thành object | Hoàn thiện object sau conversion |

Tên callback và chữ ký chi tiết cần khớp phiên bản Spring Data Relational trong dự án. Các callback được quản lý bởi Spring Data khi ứng dụng sử dụng đường mapping/persistence tương ứng, ví dụ repository aggregate hoặc `JdbcAggregateTemplate`.

### 2.1. Ví dụ BeforeConvertCallback

Giả sử mã đơn hàng cần được chuẩn hóa trước khi lưu. Có thể đặt logic kỹ thuật này trong callback:

```java
@Component
public class OrderCodeCallback
        implements BeforeConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeConvert(PurchaseOrder aggregate) {
        String normalized = aggregate.getOrderCode()
                .trim()
                .toUpperCase(Locale.ROOT);

        return aggregate.withOrderCode(normalized);
    }
}
```

Ví dụ giả định `PurchaseOrder` là immutable và có method `withOrderCode(...)`. Với class mutable, callback có thể điều chỉnh object rồi trả lại instance đó.

Khi lưu bằng repository, callback có thể được gọi trong lifecycle trước conversion. Nhưng nếu service thay bằng:

```java
jdbcTemplate.update(
        "UPDATE orders SET order_code = ? WHERE id = ?",
        rawOrderCode,
        orderId
);
```

thì `BeforeConvertCallback` không được gọi. SQL ghi đúng giá trị `rawOrderCode` đã truyền vào. Nếu normalization vẫn là yêu cầu, direct-write path phải chuẩn hóa trước khi bind tham số hoặc dùng một cơ chế database có chủ đích.

### 2.2. Ví dụ BeforeSaveCallback

`BeforeSaveCallback` được dùng khi cần can thiệp ở giai đoạn trước khi ghi aggregate change. Callback này có thể nhận aggregate và thông tin thay đổi relational tùy phiên bản API.

Minh họa dạng callback:

```java
@Component
public class OrderBeforeSaveCallback
        implements BeforeSaveCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeSave(
            PurchaseOrder aggregate,
            AggregateChange<PurchaseOrder> change
    ) {
        // Có thể kiểm tra hoặc bổ sung dữ liệu phù hợp với persistence.
        return aggregate;
    }
}
```

Callback thực tế cần import interface và kiểu `AggregateChange` từ package của Spring Data Relational tương ứng với phiên bản đang dùng. Hãy kiểm tra API của dependency trong dự án trước khi chép nguyên ví dụ vào source.

Điều quan trọng trong bài này: callback chỉ có cơ hội chạy khi lệnh đi qua lifecycle mà Spring Data quản lý. Một câu `UPDATE` bằng `JdbcTemplate` không tạo `AggregateChange` và không gọi callback chỉ vì nó dùng cùng `DataSource`.

### 2.3. Callback không thay thế domain method

Callback thích hợp cho logic kỹ thuật hoặc cross-cutting như chuẩn hóa, gắn metadata và quan sát lifecycle. Quy tắc nghiệp vụ quan trọng nên được đặt trong domain method hoặc application service để mọi đường ghi có thể chủ động sử dụng.

Ví dụ, quy tắc “chỉ đơn hàng ở trạng thái `NEW` mới được chuyển sang `PAID`” nên nằm trong hành vi domain:

```java
public void markAsPaid() {
    if (status != OrderStatus.NEW) {
        throw new IllegalStateException(
                "Only NEW orders can be paid"
        );
    }

    this.status = OrderStatus.PAID;
}
```

Nếu direct SQL cập nhật `status` mà không kiểm tra trạng thái hiện tại, nó có thể bỏ qua invariant này. Khi cần ghi trực tiếp, phải đưa điều kiện nghiệp vụ vào câu lệnh hoặc gọi một service kiểm tra trước khi ghi.

### 2.4. Callback khác với database trigger

Callback chạy trong ứng dụng Spring Data. Database trigger chạy bên trong database khi DML phù hợp xảy ra.

| Đặc điểm | Entity callback | Database trigger |
|---|---|---|
| Chạy ở đâu | Application process | Database server |
| Cần Spring Data lifecycle | Có | Không |
| Được kích hoạt bởi JdbcTemplate | Không tự động | Có, nếu DML khớp trigger |
| Biết domain object | Có thể nhận aggregate/object | Chỉ thấy hàng/cột và ngữ cảnh DB |
| Phù hợp | Logic gắn với mapping/domain application | Quy tắc dữ liệu ở tầng DB, audit đa ứng dụng |

Một trigger có thể bảo đảm audit cho cả Spring Data và SQL trực tiếp, nhưng phải thiết kế để không xung đột với auditing callback của ứng dụng. Tránh để cả hai tầng cùng ghi cùng một trường theo những quy tắc khác nhau.

## 3. Auditing trong Spring Data JDBC

Auditing giúp tự động ghi nhận ai tạo/sửa dữ liệu và thời điểm tạo/sửa. Spring Data Relational cung cấp các annotation phổ biến:

- `@CreatedBy`: người tạo.
- `@CreatedDate`: thời điểm tạo.
- `@LastModifiedBy`: người sửa gần nhất.
- `@LastModifiedDate`: thời điểm sửa gần nhất.

Để bật auditing cho Spring Data JDBC, cấu hình `@EnableJdbcAuditing` và cung cấp `AuditorAware` nếu cần lưu người thực hiện.

### 3.1. Khai báo audit fields trên aggregate

Ví dụ:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @Version
    private Long version;
}
```

Các annotation thuộc `org.springframework.data.annotation`. Chúng đánh dấu metadata cho auditing và optimistic locking; tên cột database cần khớp naming strategy hoặc được cấu hình bằng `@Column`.

Schema minh họa:

```sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status VARCHAR(30) NOT NULL,
    created_by VARCHAR(120),
    created_at TIMESTAMP,
    last_modified_by VARCHAR(120),
    last_modified_at TIMESTAMP,
    version BIGINT NOT NULL
);
```

### 3.2. Bật auditing và cung cấp AuditorAware

Cấu hình minh họa:

```java
@Configuration
@EnableJdbcAuditing
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware(CurrentActor currentActor) {
        return () -> Optional.ofNullable(currentActor.username());
    }
}
```

`CurrentActor` đại diện cho thành phần ứng dụng lấy người dùng hiện tại từ ngữ cảnh xác thực. Đây là ví dụ minh họa; trong ứng dụng thật, hãy lấy actor từ nguồn tin cậy của server như security context hoặc service identity, không nhận tùy ý tên người dùng do client gửi lên.

Auditing infrastructure sử dụng `AuditorAware` để điền các trường người tạo/người sửa khi lifecycle auditing được kích hoạt.

Nếu không cần lưu người thực hiện, có thể chỉ bật date auditing và bỏ qua auditor provider theo cấu hình được phiên bản hỗ trợ. Nếu cần `@CreatedBy` hoặc `@LastModifiedBy`, cần có cách cung cấp auditor phù hợp.

### 3.3. Auditing hoạt động trên aggregate save

Khi aggregate được lưu qua Spring Data JDBC, auditing callback có thể điền các giá trị:

- Khi insert, `createdAt`/`createdBy` ghi nhận thông tin tạo.
- Khi cập nhật, `lastModifiedAt`/`lastModifiedBy` ghi nhận lần sửa gần nhất.
- Các trường created thường được giữ nguyên qua những lần update tiếp theo.

Cách điền cụ thể phụ thuộc cấu hình auditing, `modifyOnCreate`, kiểu ngày giờ và mapping của entity. Hãy kiểm tra cấu hình dự án nếu cần quy tắc chính xác về lần tạo đầu tiên.

### 3.4. Direct SQL không tự điền audit fields

Giả sử code chuyển từ:

```java
orders.save(order);
```

sang:

```java
jdbcTemplate.update(
        "UPDATE orders SET status = ? WHERE id = ?",
        "PAID",
        orderId
);
```

Câu lệnh SQL chỉ cập nhật `status`. Nó không tự biết `@LastModifiedDate`, `@LastModifiedBy` hay `AuditorAware`. Các giá trị audit sẽ giữ nguyên trừ khi SQL, trigger hoặc một cơ chế khác cập nhật chúng.

Nếu direct write là đường đi được chủ động thiết kế, hãy bind thông tin audit rõ ràng:

```sql
UPDATE orders
SET status = :status,
    last_modified_at = :modifiedAt,
    last_modified_by = :modifiedBy
WHERE id = :id;
```

Trong đó `modifiedAt` nên được lấy từ `Clock` hoặc time provider của ứng dụng; `modifiedBy` lấy từ actor đáng tin cậy. Không cập nhật `created_at` và `created_by` trong thao tác sửa thông thường.

### 3.5. Chọn một nguồn chịu trách nhiệm ghi audit

Có hai cách phổ biến:

**Ứng dụng quản lý audit:** aggregate save dùng auditing callback; direct DML phải tự bind audit fields. Cách này giữ logic audit trong code nhưng yêu cầu mọi đường ghi tuân thủ cùng quy tắc.

**Database quản lý audit:** trigger hoặc stored procedure cập nhật audit columns. Cách này bao phủ nhiều client truy cập database, nhưng actor/time cần được truyền vào session hoặc tham số theo một giao ước an toàn.

Không nên vừa để auditing callback ghi một giá trị, vừa để trigger ghi đè giá trị khác mà không có quy tắc rõ ràng. Hãy xác định một nguồn có thẩm quyền cho từng audit field.

## 4. Optimistic locking với @Version

Optimistic locking phát hiện hai transaction cùng sửa một aggregate dựa trên version. Nó giúp tránh tình huống một bản ghi đã được cập nhật bởi người khác nhưng một object cũ vẫn ghi đè dữ liệu mới.

Trong Spring Data JDBC, đánh dấu một property bằng `@Version`:

```java
import org.springframework.data.annotation.Version;

@Table("orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;

    @Version
    private Long version;
}
```

Schema có cột version:

```sql
ALTER TABLE orders
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
```

Spring Data JDBC sử dụng version hiện tại trong điều kiện update và tăng version khi ghi thành công.

### 4.1. Cách version bảo vệ update

Giả sử một order có:

| id | status | version |
|---:|---|---:|
| 101 | NEW | 4 |

Hai request A và B cùng đọc version 4.

- Request A đổi status và save thành công; version thành 5.
- Request B vẫn giữ object với version 4.
- Khi B save, điều kiện version 4 không còn khớp.
- Spring Data JDBC phát hiện không có hàng được cập nhật theo version mong đợi và báo optimistic locking failure.

SQL minh họa về ngữ nghĩa:

```sql
UPDATE orders
SET status = ?,
    version = 5
WHERE id = 101
  AND version = 4;
```

Câu lệnh chỉ cập nhật được hàng nếu ID và version đều khớp. Nếu version đã là 5, câu lệnh không cập nhật hàng nào.

### 4.2. Exception khi có xung đột

Khi optimistic locking phát hiện dữ liệu đã được thay đổi bởi transaction khác, Spring Data JDBC báo lỗi thuộc nhóm `OptimisticLockingFailureException` của Spring DAO.

Ứng dụng có thể xử lý theo use case:

- Báo cho client rằng dữ liệu đã thay đổi và yêu cầu tải lại.
- Tải aggregate mới rồi yêu cầu người dùng áp dụng lại thay đổi.
- Thực hiện retry có kiểm soát nếu thao tác có thể tính lại an toàn.
- Ghi log/metric để theo dõi tần suất conflict.

Không nên tự động retry mù quáng một thao tác nghiệp vụ có side effect. Ví dụ thanh toán, gửi thông báo hoặc trừ tồn kho cần idempotency và quy tắc nghiệp vụ rõ ràng.

### 4.3. Version cũng liên quan đến delete

Khi xóa aggregate có version, Spring Data JDBC có thể dùng version để kiểm tra object có còn là phiên bản hiện tại hay không. Nếu ứng dụng xóa bằng SQL trực tiếp, database không tự đọc annotation `@Version`.

Nếu cần direct delete có optimistic locking, câu lệnh phải kiểm tra version:

```sql
DELETE FROM orders
WHERE id = :id
  AND version = :expectedVersion;
```

Với bảng dependent, còn phải quyết định cách xóa child và bảo toàn foreign key trong cùng transaction. Nếu dùng FK `ON DELETE CASCADE`, database có thể dọn dependent rows; nếu không, phải xóa child theo đúng thứ tự. Không được cho rằng `@Version` tự áp dụng lên câu DELETE trực tiếp.

## 5. Vì sao direct DML bỏ qua optimistic locking?

Một câu SQL như:

```sql
UPDATE orders
SET status = 'PAID'
WHERE id = 101;
```

chỉ kiểm tra ID. Nó không kiểm tra version mà object trước đó đã đọc. Nếu request khác vừa thay đổi cùng order, câu lệnh vẫn có thể ghi đè trạng thái mới.

`@Version` là metadata mà Spring Data JDBC sử dụng trong aggregate-aware persistence. Database không tự biết class Java có annotation này. Khi bỏ qua repository save, bạn phải mang version protocol vào câu SQL.

### 5.1. Ví dụ lỗi lost update

Giả sử:

| Thời điểm | Request A | Request B | Database |
|---|---|---|---|
| T1 | Đọc version 7 | | version 7 |
| T2 | | Đọc version 7 | version 7 |
| T3 | Cập nhật địa chỉ, save | | version 8 |
| T4 | | Direct UPDATE trạng thái chỉ theo ID | B ghi trên dữ liệu version 8 mà không kiểm tra version 7 |
| T5 | | | Thay đổi của A có thể bị ghi đè hoặc kết hợp ngoài dự kiến |

Nếu B dùng điều kiện `WHERE id = ? AND version = 7`, câu UPDATE của B sẽ không tác động hàng nào sau khi A đã tăng version lên 8. B có thể nhận biết conflict qua update count bằng 0.

### 5.2. Direct update phải kiểm tra và tăng version

Một lệnh cập nhật an toàn hơn:

```sql
UPDATE orders
SET status = :status,
    last_modified_at = :modifiedAt,
    last_modified_by = :modifiedBy,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
```

Ba việc diễn ra trong một statement:

1. Chỉ cập nhật nếu version còn đúng như caller đã đọc.
2. Ghi trạng thái mới.
3. Tăng version để các writer tiếp theo nhận biết dữ liệu đã thay đổi.

Nếu không tăng version, một aggregate cũ có thể tiếp tục save với version cũ và không phát hiện direct update vừa xảy ra.

### 5.3. Kiểm tra update count

Với `JdbcTemplate`, kết quả trả về là số hàng được cập nhật:

```java
int updated = jdbcTemplate.update(sql, parameters);

if (updated == 0) {
    throw new OptimisticLockingFailureException(
            "Order was changed or no longer exists"
    );
}
```

Nếu `updated == 1`, thao tác đã cập nhật đúng một hàng. Nếu bằng 0, có thể order không tồn tại hoặc version không khớp. Nếu cần phân biệt hai trường hợp, thực hiện truy vấn kiểm tra bổ sung trong transaction phù hợp.

Không dựa vào exception tự động của Spring Data JDBC cho câu `JdbcTemplate.update(...)`; direct DML cần tự diễn giải update count và tạo lỗi ứng dụng phù hợp.

## 6. Một direct update hoàn chỉnh có audit và version

Ví dụ service dùng `NamedParameterJdbcTemplate`:

```java
@Service
public class OrderCommandService {

    private final NamedParameterJdbcTemplate jdbc;
    private final Clock clock;
    private final CurrentActor currentActor;

    public OrderCommandService(
            NamedParameterJdbcTemplate jdbc,
            Clock clock,
            CurrentActor currentActor
    ) {
        this.jdbc = jdbc;
        this.clock = clock;
        this.currentActor = currentActor;
    }

    @Transactional
    public void changeStatus(
            long orderId,
            long expectedVersion,
            String newStatus
    ) {
        Instant now = clock.instant();
        String actor = currentActor.username();

        String sql = """
            UPDATE orders
            SET status = :status,
                last_modified_at = :modifiedAt,
                last_modified_by = :modifiedBy,
                version = version + 1
            WHERE id = :id
              AND version = :expectedVersion
            """;

        var parameters = new MapSqlParameterSource()
                .addValue("status", newStatus)
                .addValue("modifiedAt", Timestamp.from(now))
                .addValue("modifiedBy", actor)
                .addValue("id", orderId)
                .addValue("expectedVersion", expectedVersion);

        int updated = jdbc.update(sql, parameters);

        if (updated != 1) {
            throw new OptimisticLockingFailureException(
                    "Order changed or does not exist: " + orderId
            );
        }
    }
}
```

Ví dụ này minh họa ba trách nhiệm của direct-write path:

- Lấy thời điểm và actor từ thành phần ứng dụng tin cậy.
- Cập nhật audit columns.
- Dùng version predicate và tăng version nguyên tử.

`Clock`, `CurrentActor`, exception handling và kiểu timestamp cần điều chỉnh theo ứng dụng. `@Transactional` giúp statement tham gia transaction Spring nếu template và transaction manager dùng cùng DataSource.

Nếu câu lệnh thay đổi child table thay vì root table, cần bảo vệ version của aggregate root nữa. Một cách là tăng version root bằng điều kiện `WHERE id = :id AND version = :expectedVersion` trước khi cập nhật child, trong cùng transaction. Nếu update child thất bại, transaction rollback cả lần tăng version. Mọi writer thay đổi aggregate đều phải tuân theo cùng giao ước version.

## 7. Direct update trên child collection: bảo vệ version của root

Giả sử `OrderLine` được quản lý bởi `PurchaseOrder` qua `@MappedCollection`. Nếu một command cập nhật trực tiếp bảng `order_lines`, chỉ tăng version của child hoặc bỏ qua version root có thể không bảo vệ aggregate snapshot đã được tải trước đó.

Ví dụ một transaction khác đã đọc aggregate version 10. Direct SQL cập nhật một dòng hàng nhưng không tăng `orders.version`. Sau đó transaction cũ save aggregate với version 10; Spring Data JDBC vẫn có thể xem version root là hợp lệ và đồng bộ collection theo trạng thái cũ.

Để tránh điều đó, direct child write cần phối hợp version ở root:

```sql
BEGIN;

UPDATE orders
SET version = version + 1,
    last_modified_at = :modifiedAt,
    last_modified_by = :modifiedBy
WHERE id = :orderId
  AND version = :expectedVersion;

-- Chỉ tiếp tục nếu UPDATE root tác động đúng một hàng.

UPDATE order_lines
SET quantity = :quantity
WHERE id = :lineId
  AND order_id = :orderId;

COMMIT;
```

Đây là SQL minh họa cho một transaction có kiểm tra kết quả từng statement. Nếu update root không tác động đúng một hàng, phải dừng và rollback. Nếu update child không tác động đúng một hàng, cần xử lý lỗi theo nghiệp vụ và rollback version bump.

Tuy nhiên, nếu child thường xuyên được cập nhật độc lập, đó có thể là dấu hiệu `OrderLine` cần aggregate boundary riêng. Đừng duy trì nhiều đường ghi vào child của cùng aggregate nếu không có quy tắc version thống nhất.

## 8. @Modifying @Query cũng là direct DML

Direct write không chỉ là `JdbcTemplate`. Spring Data JDBC có thể dùng `@Modifying` cùng `@Query` để thực hiện UPDATE/DELETE tường minh.

Ví dụ:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Modifying
    @Query("""
        UPDATE orders
        SET status = :status
        WHERE id = :id
        """)
    int updateStatusDirectly(
            @Param("id") Long id,
            @Param("status") String status
    );
}
```

Method này yêu cầu database thực thi SQL trực tiếp. Nó không tương đương với việc tải `PurchaseOrder`, gọi domain method rồi `save(...)`.

Nếu dùng kiểu query này trong ứng dụng production, cần tự cân nhắc:

- Audit columns có phải cập nhật không?
- Có phải kiểm tra và tăng version không?
- Có cần điều kiện trạng thái hiện tại để bảo vệ invariant không?
- Có child rows hoặc bảng phụ cần cập nhật cùng transaction không?
- Có domain event/outbox nào cần ghi không?
- Return count được xử lý như thế nào nếu không có hàng phù hợp?

Có thể thêm version và audit vào câu SQL:

```sql
UPDATE orders
SET status = :status,
    last_modified_at = :modifiedAt,
    last_modified_by = :modifiedBy,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
```

Tên annotation và cách khai báo tham số cần khớp phiên bản Spring Data JDBC. Điều quan trọng là DML vẫn do câu SQL quyết định; annotation không tự bổ sung auditing hoặc version protocol cho nội dung SQL.

## 9. Khi nào nên dùng aggregate save, khi nào direct write?

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Thay đổi trạng thái cần kiểm tra domain invariant | Load aggregate, gọi domain method, save | Giữ domain behavior và lifecycle |
| Cập nhật một counter đơn giản, độc lập | Direct SQL có version/audit phù hợp | Tránh load/save toàn aggregate |
| Batch cập nhật nhiều hàng theo điều kiện | SQL/batch operation có chủ đích | Giảm round trip và kiểm soát hiệu năng |
| Thay đổi một child trong aggregate nhỏ | Aggregate save | Giữ thao tác trong ranh giới aggregate |
| Child collection rất lớn và thường cập nhật từng phần | Xem lại aggregate boundary; có thể tách child thành root | Tránh ghi lại collection lớn |
| Cần auditing callback và callback logic | Aggregate-aware save | Callback được gọi trong lifecycle |
| Cần query command đặc thù nhưng vẫn giữ version | `@Modifying`/JdbcTemplate với version predicate tự viết | Direct DML có thể an toàn nếu tuân thủ giao ước |
| Cần xóa root cùng child | Repository aggregate delete hoặc SQL/FK policy rõ ràng | Direct DELETE không tự đọc `@MappedCollection` |

Không có quy tắc “luôn dùng repository” hoặc “luôn dùng SQL trực tiếp”. Hãy chọn theo ranh giới nghiệp vụ, kích thước aggregate và các bảo đảm mà use case cần.

## 10. Domain events, outbox và side effects

Entity callbacks, auditing và optimistic locking không phải toàn bộ side effects của một thao tác nghiệp vụ.

Ví dụ khi đơn hàng chuyển sang `PAID`, ứng dụng có thể cần:

- Ghi trạng thái đơn hàng.
- Ghi audit actor/time.
- Tăng version.
- Ghi một domain event hoặc outbox message.
- Gửi thông báo sau khi transaction commit.

Nếu chỉ chạy một direct UPDATE, các bước còn lại không tự xảy ra. Nếu chúng là yêu cầu nghiệp vụ, cần tổ chức một application service điều phối tất cả trong transaction phù hợp.

### 10.1. Transactional outbox

Nếu cần phát event bền vững cùng thay đổi database, có thể ghi outbox row trong cùng transaction:

```sql
UPDATE orders
SET status = :status,
    version = version + 1,
    last_modified_at = :modifiedAt,
    last_modified_by = :modifiedBy
WHERE id = :id
  AND version = :expectedVersion;

INSERT INTO outbox_events (
    aggregate_type,
    aggregate_id,
    event_type,
    payload,
    created_at
)
VALUES (
    'PurchaseOrder',
    :id,
    'OrderStatusChanged',
    :payload,
    :modifiedAt
);
```

Trong code, chỉ insert outbox khi update order thành công đúng một hàng. Hai thao tác phải cùng transaction. Một publisher riêng sẽ gửi outbox sau đó và đánh dấu đã xử lý theo chiến lược retry/idempotency.

Không gửi message ra broker trước khi transaction commit rồi giả định database rollback có thể thu hồi message. Transaction database không rollback side effect bên ngoài.

### 10.2. Callback không phải event bus cho mọi đường ghi

Nếu ứng dụng dựa vào `AfterSaveCallback` hoặc application event được phát từ aggregate persistence, direct SQL sẽ bỏ qua đường phát đó. Nếu event phải được phát cho mọi writer, hãy dùng một cơ chế chung mà tất cả writer gọi, hoặc đặt logic audit/outbox ở database/service boundary phù hợp.

## 11. Những rủi ro khi trộn nhiều đường ghi

Khi cùng một bảng được ghi qua repository và direct SQL, các writer phải chia sẻ một hợp đồng.

| Rủi ro | Ví dụ | Biện pháp |
|---|---|---|
| Audit bị thiếu | JdbcTemplate chỉ update status | Ghi audit fields hoặc dùng DB trigger thống nhất |
| Lost update | Direct UPDATE chỉ lọc theo ID | Dùng `WHERE id = ? AND version = ?`, tăng version |
| Aggregate cũ ghi đè dữ liệu | Direct child update không tăng root version | Tăng version root trong cùng transaction |
| Bỏ qua domain invariant | SQL chuyển trạng thái không hợp lệ | Kiểm tra qua domain service hoặc điều kiện SQL |
| Child không được đồng bộ | Direct delete root nhưng không xử lý collection | Repository aggregate delete hoặc FK/SQL cleanup |
| Callback không chạy | Direct DML bỏ qua mapping lifecycle | Đưa logic cần thiết vào service/SQL rõ ràng |
| Audit ghi hai lần | Callback và trigger cùng cập nhật | Chọn một nguồn chịu trách nhiệm |
| Event bị mất | Direct update không ghi outbox | Ghi outbox cùng transaction |
| Timestamp không nhất quán | Callback dùng Clock, SQL dùng DB time | Chọn một nguồn thời gian hoặc quy tắc chuyển đổi rõ |
| Version không đồng bộ | Có writer tăng version, có writer bỏ qua | Bắt buộc mọi đường ghi tuân thủ version protocol |

Đặc biệt, optimistic locking chỉ có ý nghĩa khi **mọi đường ghi có khả năng xung đột đều tham gia cùng version protocol**. Chỉ gắn `@Version` lên class không bảo vệ những câu SQL bỏ qua cột version.

## 12. Kiểm thử callback, auditing và optimistic locking

Nên kiểm thử bằng database integration test vì các hành vi này phụ thuộc mapping, transaction và SQL thực tế.

### 12.1. Kiểm tra auditing qua repository

Tạo một aggregate mới rồi save. Xác nhận:

- `createdAt` và `createdBy` được điền.
- `lastModifiedAt` và `lastModifiedBy` có giá trị theo cấu hình.
- Sau lần save tiếp theo, created fields được giữ nguyên.
- Modified fields thay đổi theo thời điểm/actor mới.

Trong test, có thể cung cấp `AuditorAware` cố định để kết quả xác định, thay vì phụ thuộc người dùng đang đăng nhập.

### 12.2. Kiểm tra direct DML không tự chạy callback

Có thể tạo callback đếm số lần được gọi trong test:

```java
@Component
public class CallbackCounter
        implements BeforeConvertCallback<PurchaseOrder> {

    private final AtomicInteger calls = new AtomicInteger();

    @Override
    public PurchaseOrder onBeforeConvert(PurchaseOrder aggregate) {
        calls.incrementAndGet();
        return aggregate;
    }

    public int count() {
        return calls.get();
    }

    public void reset() {
        calls.set(0);
    }
}
```

Sau khi reset counter:

- Gọi repository `save(...)` và xác nhận callback được gọi theo lifecycle.
- Gọi `JdbcTemplate.update(...)` và xác nhận callback counter không tăng.
- Kiểm tra audit columns sau direct DML; nếu SQL không cập nhật chúng, giá trị sẽ không tự thay đổi.

Ví dụ counter là test instrumentation. Không dùng một singleton counter trong production để điều khiển nghiệp vụ.

### 12.3. Kiểm tra optimistic locking

Kịch bản:

1. Tải cùng một aggregate hai lần để có hai object cùng version.
2. Save object thứ nhất.
3. Save object thứ hai.
4. Xác nhận lần save thứ hai phát sinh optimistic locking failure.

### 12.4. Kiểm tra direct update với version predicate

Tạo row version 5, chạy direct UPDATE với expected version 5:

- Update count phải bằng 1.
- Version mới phải là 6.
- Chạy lại với expected version 5 phải có update count bằng 0.
- Một aggregate đã tải ở version 5 trước đó phải không thể save thành công sau direct update nếu save đi qua `@Version`.

Đồng thời kiểm tra audit fields và transaction rollback khi update count không đúng.

## 13. Checklist trước khi đưa direct write vào production

Trước khi thay aggregate save bằng direct DML, hãy trả lời rõ các câu hỏi sau:

1. **Invariant:** SQL có bảo đảm điều kiện domain trước khi thay đổi không?
2. **Callback:** Có logic callback nào mà đường mới cần thực hiện lại không?
3. **Auditing:** Ai ghi `last_modified_at` và `last_modified_by`?
4. **Version:** Câu SQL có lọc theo version cũ và tăng version mới không?
5. **Child:** Có dependent rows nào cần cập nhật/xóa cùng root không?
6. **Transaction:** Các statement liên quan có cùng transaction không?
7. **Event/outbox:** Có side effect nào cần ghi cùng transaction không?
8. **Concurrency:** Tất cả writer khác có tuân thủ cùng version protocol không?
9. **Return value:** Update count 0 hoặc nhiều hơn 1 được xử lý ra sao?
10. **Testing:** Có integration test cho stale version, audit và rollback không?

## 14. Nguyên tắc ghi nhớ

- Repository aggregate save và `JdbcAggregateTemplate` đi qua lifecycle Spring Data JDBC; direct SQL qua `@Modifying`, `JdbcTemplate` hoặc JDBC không tự chạy lifecycle đó.
- Entity callbacks như `BeforeConvertCallback` và `BeforeSaveCallback` chỉ được gọi trong các thao tác mapping/persistence tương ứng.
- Auditing annotations `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, `@LastModifiedDate` cần auditing infrastructure; direct DML phải tự ghi audit hoặc dựa trên database mechanism đã thống nhất.
- `@Version` không được database tự nhận biết. Spring Data JDBC dùng nó trong aggregate-aware save/delete; direct DML phải kiểm tra version cũ và tăng version mới bằng SQL.
- Với direct update child, cần phối hợp version của aggregate root để stale aggregate snapshot không thể ghi đè thay đổi.
- Domain invariant, callback side effects, outbox và transaction không tự xuất hiện khi chỉ chạy một câu UPDATE.
- Nếu nhiều đường ghi cùng tồn tại, tất cả phải tuân thủ cùng giao ước audit, version và ownership.

Direct SQL là công cụ hữu ích cho thao tác ghi hẹp và tối ưu hiệu năng. Hãy giữ rõ ranh giới: Spring Data JDBC chỉ có thể tự áp dụng callback, auditing và optimistic locking khi thao tác đi qua lifecycle mà nó quản lý. Khi bỏ qua aggregate save, hãy đưa các bảo đảm cần thiết vào service và câu SQL một cách tường minh, rồi kiểm thử concurrency và audit trên database thực tế.
