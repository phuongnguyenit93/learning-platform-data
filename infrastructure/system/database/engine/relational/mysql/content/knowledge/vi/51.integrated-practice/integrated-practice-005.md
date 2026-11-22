# Xây dựng upsert có thể thực hiện lại mà không ghi trùng nghiệp vụ

Trong module `DATABASE_MYSQL`, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài thực hành này kết hợp unique key, `INSERT ... ON DUPLICATE KEY UPDATE`, transaction, idempotency key và kiểm thử đồng thời để xây dựng thao tác ghi có thể được gửi lại sau timeout hoặc retry mà không tạo bản ghi hay tác động nghiệp vụ trùng lặp.

Một request có thể đến server nhiều lần vì client timeout dù database đã commit, worker có thể xử lý lại message sau khi restart, hoặc hai instance có thể nhận cùng một lệnh gần như đồng thời. Nếu mỗi lần nhận đều thực hiện `INSERT` hoặc cộng/trừ số lượng, hệ thống có thể tạo dữ liệu trùng hoặc áp dụng nghiệp vụ nhiều lần. Một thao tác idempotent cho cùng một định danh và cùng nội dung đầu vào sẽ cho cùng trạng thái nghiệp vụ cuối cùng khi được thực hiện một lần hay nhiều lần.

`UPSERT` là một kỹ thuật ghi hữu ích, nhưng bản thân cú pháp upsert không tự bảo đảm toàn bộ nghiệp vụ idempotent. Cần xác định khóa nghiệp vụ, nội dung nào được phép cập nhật, cách phát hiện request trùng, cách xử lý payload xung đột và ranh giới transaction.

## 1. Phân biệt upsert, retry và idempotency

- **Upsert:** thử insert; nếu trùng primary key hoặc unique key thì thực hiện nhánh update.
- **Retry:** thực hiện lại một thao tác sau lỗi tạm thời hoặc kết quả không xác định.
- **Idempotency:** bảo đảm việc lặp lại cùng một ý định nghiệp vụ không tạo thêm tác động ngoài mong muốn.

Ví dụ nhập một sản phẩm từ hệ thống kho ngoài:

1. Hệ thống ngoài gửi `sku=SKU-100`, tên và số lượng hiện tại.
2. MySQL chưa có SKU đó nên ứng dụng insert.
3. Nếu SKU đã tồn tại, ứng dụng cập nhật trạng thái theo quy tắc đã định.
4. Nếu cùng message được gửi lại, dữ liệu không được nhân đôi.

Một upsert có thể phù hợp với dữ liệu dạng snapshot, ví dụ ghi đè số lượng hiện tại bằng một giá trị tuyệt đối. Nhưng nếu payload là delta, ví dụ “cộng thêm 5 sản phẩm”, chạy lại câu lệnh `quantity = quantity + 5` sẽ cộng hai lần. Đối với delta, cần deduplicate bằng event ID trong cùng transaction với phép cộng.

## 2. Chọn khóa nghiệp vụ trước khi viết SQL

Khóa nghiệp vụ xác định hai request có mô tả cùng một thực thể hay không. Không dùng tên hiển thị hoặc một trường có thể thay đổi làm khóa nếu nó không duy nhất theo hợp đồng nghiệp vụ.

Ví dụ một sản phẩm được đồng bộ từ nhiều hệ thống:

```sql
CREATE TABLE external_product (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_system VARCHAR(40) NOT NULL,
    external_id VARCHAR(100) NOT NULL,
    sku VARCHAR(80) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    source_updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_product_source_external
        (source_system, external_id),
    UNIQUE KEY uq_product_source_sku
        (source_system, sku)
) ENGINE=InnoDB;
```

`(source_system, external_id)` là định danh bản ghi trong hệ thống nguồn. Unique constraint bảo vệ tính duy nhất ngay cả khi hai request đồng thời đến hai instance ứng dụng. Kiểm tra `SELECT` trước rồi mới `INSERT` không đủ để chống race condition: cả hai request có thể cùng thấy “chưa tồn tại” trước khi một request insert.

Chỉ tạo unique key trên những thuộc tính thực sự phải duy nhất. Nếu có nhiều unique key, phải hiểu rằng `ON DUPLICATE KEY UPDATE` có thể được kích hoạt bởi bất kỳ key nào trong số đó. Nếu hai unique key có thể trùng với hai hàng khác nhau, nhánh update có thể tác động đến hàng không như ứng dụng dự định. Khi nhiều định danh độc lập có thể xung đột, hãy xác định trước quy tắc hợp nhất hoặc tách luồng ghi.

## 3. Cú pháp MySQL INSERT ... ON DUPLICATE KEY UPDATE

MySQL hỗ trợ upsert thông qua `INSERT ... ON DUPLICATE KEY UPDATE`. Khi insert vi phạm primary key hoặc unique index, server chạy phần update thay vì trả lỗi duplicate key thông thường.

Ví dụ với MySQL 8.0.19 trở lên, có thể đặt alias cho hàng đầu vào:

```sql
INSERT INTO external_product (
    source_system,
    external_id,
    sku,
    display_name,
    source_version,
    source_updated_at
)
VALUES (
    'warehouse-a',
    'P-9081',
    'SKU-100',
    'Bàn phím cơ',
    12,
    '2026-11-19 10:30:00.000000'
) AS incoming
ON DUPLICATE KEY UPDATE
    sku = incoming.sku,
    display_name = incoming.display_name,
    source_version = incoming.source_version,
    source_updated_at = incoming.source_updated_at;
```

Alias `incoming` đại diện cho hàng đang được insert. Cú pháp alias hàng đầu vào được hỗ trợ từ MySQL 8.0.19. Hàm `VALUES(column)` từng được dùng để tham chiếu giá trị insert nhưng đã bị deprecated từ MySQL 8.0.20; với phiên bản mới, ưu tiên cú pháp row alias theo tài liệu của phiên bản đang chạy.

Đối với MySQL cũ chưa hỗ trợ alias này, cần dùng cú pháp tương thích của phiên bản đó và có kế hoạch chuyển đổi khi nâng cấp. Không trộn ví dụ cú pháp giữa các phiên bản mà chưa kiểm tra parser và release note.

### Upsert snapshot có thể lặp lại

Nếu đầu vào biểu diễn trạng thái tuyệt đối, gán lại cùng giá trị là thao tác có thể lặp lại:

```sql
INSERT INTO product_stock (
    sku,
    available_quantity,
    source_version
)
VALUES ('SKU-100', 25, 42) AS incoming
ON DUPLICATE KEY UPDATE
    available_quantity = incoming.available_quantity,
    source_version = incoming.source_version;
```

Chạy lại cùng payload không làm số lượng tăng từ 25 lên 50; nó vẫn đặt giá trị thành 25. Đây là đặc tính quan trọng của snapshot upsert.

Tuy nhiên, một message cũ có thể đến sau message mới. Nếu version 41 được xử lý sau version 42, câu lệnh trên sẽ ghi đè trạng thái mới bằng dữ liệu cũ. Cần dùng version nguồn để từ chối cập nhật cũ:

```sql
INSERT INTO product_stock (
    sku,
    available_quantity,
    source_version
)
VALUES ('SKU-100', 25, 42) AS incoming
ON DUPLICATE KEY UPDATE
    available_quantity = IF(
        incoming.source_version > product_stock.source_version,
        incoming.available_quantity,
        product_stock.available_quantity
    ),
    source_version = GREATEST(
        product_stock.source_version,
        incoming.source_version
    );
```

Đặt phép gán `source_version` sau phép gán dữ liệu để điều kiện so sánh dùng version đang có trước khi update. Câu lệnh này bỏ qua snapshot cũ hơn và không thay đổi quantity khi version bằng hoặc thấp hơn. Nếu hai payload có cùng version nhưng nội dung khác nhau, đó là xung đột dữ liệu cần phát hiện và điều tra; không nên âm thầm coi chúng là bản gửi lại hợp lệ.

### Không biến upsert thành phép cộng lặp

Đây là ví dụ không idempotent nếu request có thể được gửi lại:

```sql
INSERT INTO product_stock (sku, available_quantity)
VALUES ('SKU-100', 5) AS incoming
ON DUPLICATE KEY UPDATE
    available_quantity =
        product_stock.available_quantity + incoming.available_quantity;
```

Nếu cùng request chạy hai lần, quantity tăng thêm 10 thay vì 5. Câu lệnh này chỉ đúng nếu mỗi lần chạy chắc chắn đại diện cho một delta mới, và hệ thống có cơ chế ghi nhận từng delta đúng một lần ở cấp nghiệp vụ.

## 4. Những điểm cần cẩn thận với ON DUPLICATE KEY UPDATE

### Bất kỳ unique key nào cũng có thể kích hoạt update

Giả sử bảng có unique key theo email và unique key theo mã khách hàng. Một insert có email của hàng A nhưng customer code của hàng B có thể gặp xung đột không như mong muốn. Với nhiều unique index, MySQL xử lý duplicate như một update theo điều kiện xung đột và chỉ một hàng có thể được cập nhật. Không dùng một câu upsert chung nếu các unique key đại diện cho các thực thể khác nhau.

### Trigger và timestamp

Nhánh duplicate là một thao tác update. Trigger `UPDATE` có thể chạy ngay cả khi giá trị được gán bằng giá trị cũ. Nếu trigger gửi side effect hoặc ghi audit, request lặp có thể tạo thêm tác động. Tránh đặt side effect không idempotent trong trigger của bảng upsert.

Nếu cập nhật `updated_at = CURRENT_TIMESTAMP` mỗi lần duplicate, request lặp vẫn thay đổi timestamp. Nếu timestamp phải phản ánh lần thay đổi dữ liệu thực sự, chỉ cập nhật khi payload mới hơn hoặc có giá trị thay đổi; không dùng thời điểm retry làm thời điểm nghiệp vụ.

### affected rows không phải tín hiệu nghiệp vụ đáng tin cậy

Với `INSERT ... ON DUPLICATE KEY UPDATE`, số dòng bị ảnh hưởng thường là 1 cho insert, 2 cho update và 0 nếu update gán giá trị hiện tại; cờ client `CLIENT_FOUND_ROWS` có thể thay đổi cách báo cáo trường hợp không đổi. Không suy luận “request mới” hay “request trùng” chỉ từ `executeUpdate()` trả về bao nhiêu.

### Auto-increment có thể tạo khoảng trống

Một lần insert thử rồi rơi vào nhánh duplicate có thể làm bộ đếm `AUTO_INCREMENT` tăng. ID tự tăng không được bảo đảm liên tục; không dùng khoảng trống ID để suy ra bản ghi bị mất hoặc request bị lặp.

## 5. INSERT IGNORE và REPLACE không tương đương upsert

| Câu lệnh | Hành vi | Vì sao cần thận trọng |
|---|---|---|
| `INSERT ... ON DUPLICATE KEY UPDATE` | Duplicate key kích hoạt nhánh update được chỉ định. | Phải chọn đúng unique key và viết update theo quy tắc nghiệp vụ. |
| `INSERT IGNORE` | Bỏ qua một số lỗi và có thể chuyển lỗi thành warning hoặc điều chỉnh dữ liệu. | Có thể che lỗi dữ liệu ngoài duplicate key; không phải cách cập nhật hàng đã có. |
| `REPLACE` | Khi xung đột unique key, xóa hàng cũ rồi insert hàng mới. | Có thể kích hoạt delete/insert trigger, ảnh hưởng foreign key, tạo ID mới và thay đổi cột không được gửi. |

Nếu mục tiêu là cập nhật một số cột khi bản ghi đã tồn tại, `ON DUPLICATE KEY UPDATE` diễn đạt rõ hơn. Không dùng `REPLACE` như một cách viết ngắn của upsert trừ khi thực sự muốn semantics delete rồi insert.

## 6. Idempotency key cho request API

Khóa nghiệp vụ giúp nhận diện thực thể, nhưng API thường cần nhận diện một lần yêu cầu cụ thể. Ví dụ khách hàng gửi lệnh tạo thanh toán, client timeout và gửi lại cùng request. Nếu chỉ dựa vào order ID, một đơn hàng có thể có nhiều lần thanh toán hợp lệ hoặc nhiều loại lệnh khác nhau. Idempotency key xác định một ý định request cụ thể trong một phạm vi, thường là tenant hoặc client.

Thiết kế bảng:

```sql
CREATE TABLE api_idempotency (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash BINARY(32) NOT NULL,
    status VARCHAR(16) NOT NULL,
    response_json JSON NULL,
    resource_id BIGINT UNSIGNED NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    completed_at TIMESTAMP(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_idempotency_tenant_key
        (tenant_id, idempotency_key)
) ENGINE=InnoDB;
```

`request_hash` là hash ổn định của nội dung request đã chuẩn hóa. Cùng idempotency key nhưng hash khác nhau phải được coi là xung đột, thường trả HTTP 409 hoặc lỗi nghiệp vụ tương ứng. Không dùng hash để thay thế xác thực request; nó chỉ giúp phát hiện cùng key nhưng payload khác.

### Xử lý trong một transaction

Luồng xử lý:

1. Client gửi idempotency key và payload.
2. Ứng dụng chuẩn hóa request, tính hash và bắt đầu transaction.
3. Ứng dụng insert một hàng `PROCESSING` trong bảng idempotency.
4. Nếu key đã tồn tại, khóa/đọc hàng đó, so sánh hash.
5. Nếu hash khác, trả xung đột; nếu trạng thái `COMPLETED`, trả lại response đã lưu.
6. Nếu request mới, thực hiện thay đổi nghiệp vụ.
7. Lưu response/resource ID và chuyển trạng thái thành `COMPLETED`.
8. Commit cả hàng idempotency và thay đổi nghiệp vụ cùng lúc.

Ví dụ lấy hoặc tạo hàng idempotency trên MySQL 8.0.19 trở lên:

```sql
INSERT INTO api_idempotency (
    tenant_id,
    idempotency_key,
    request_hash,
    status
)
VALUES (?, ?, ?, 'PROCESSING') AS incoming
ON DUPLICATE KEY UPDATE
    id = LAST_INSERT_ID(api_idempotency.id);
```

Sau câu lệnh, đọc hàng bằng unique key trong cùng transaction:

```sql
SELECT id, request_hash, status, response_json, resource_id
FROM api_idempotency
WHERE tenant_id = ?
  AND idempotency_key = ?
FOR UPDATE;
```

`LAST_INSERT_ID(id)` trong nhánh duplicate là một kỹ thuật MySQL để đặt connection-local last insert ID thành ID của hàng đã tồn tại; ví dụ trên vẫn đọc lại bằng unique key để kiểm tra hash và trạng thái. Bảng idempotency không nên có trigger tạo side effect vì nhánh duplicate thực hiện một thao tác update. Nếu muốn lấy ID qua generated keys, phải kiểm thử hành vi với đúng Connector/J version.

Giữ hàng `PROCESSING`, cập nhật nghiệp vụ và đánh dấu `COMPLETED` trong cùng transaction. Vì hàng chưa commit không hiển thị như một kết quả đã hoàn tất đối với transaction khác, request đồng thời cùng key sẽ phải chờ unique-key conflict được giải quyết. Sau khi transaction đầu commit, request sau đọc kết quả đã lưu; nếu transaction đầu rollback, request sau có thể tạo hàng và thực hiện nghiệp vụ. Không commit riêng trạng thái `PROCESSING` trước rồi mới chạy nghiệp vụ nếu không có lease/recovery protocol đầy đủ.

### Kiểm tra hash và trả kết quả cũ

Pseudocode ở tầng service:

```text
begin transaction
insert-or-lock idempotency row by (tenant_id, key)

if stored request_hash != current request_hash:
    rollback
    return conflict

if status == COMPLETED:
    read stored response
    commit
    return stored response

perform business changes
store resource_id and response_json
set status = COMPLETED and completed_at
commit
return stored response
```

Response nên được lưu đủ để trả lại cùng kết quả cho request retry. Không tạo resource mới hoặc gửi message lần nữa khi phát hiện request đã hoàn tất.

## 7. Event ID để chống áp dụng delta hai lần

Với message biểu diễn delta như “trừ 3 sản phẩm” hoặc “cộng 100 điểm”, upsert snapshot không phù hợp. Dùng một bảng inbox/deduplication với unique event ID và ghi nhận event cùng phép cập nhật trong một transaction:

```sql
CREATE TABLE applied_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id CHAR(36) NOT NULL,
    applied_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (consumer_name, event_id)
) ENGINE=InnoDB;
```

Transaction xử lý event:

```text
begin transaction
try insert (consumer_name, event_id) into applied_event
if duplicate key:
    rollback or end without applying business change
else:
    apply quantity = quantity + delta
    commit
```

Ví dụ JDBC:

```java
@Transactional
public void applyStockDelta(StockDelta event) {
    try {
        jdbc.update("""
            INSERT INTO applied_event (consumer_name, event_id)
            VALUES (?, ?)
            """, "inventory-projection", event.eventId());
    } catch (DuplicateKeyException duplicate) {
        return;
    }

    int changed = jdbc.update("""
        UPDATE product_stock
        SET available_quantity = available_quantity + ?
        WHERE sku = ?
        """, event.delta(), event.sku());

    if (changed != 1) {
        throw new IllegalStateException("Unknown SKU: " + event.sku());
    }
}
```

Ví dụ dùng Spring `JdbcTemplate`; exception duplicate cần được xử lý sao cho transaction không bị đánh dấu rollback-only ngoài dự kiến bởi transaction manager/provider. Trong Spring, `DuplicateKeyException` có thể được ném sau khi statement lỗi; với MySQL, transaction thường vẫn có thể tiếp tục, nhưng hành vi rollback-only phụ thuộc cách exception được dịch và ranh giới proxy. Hãy kiểm thử trên stack thực tế. Có thể thay bằng một câu `INSERT ... ON DUPLICATE KEY UPDATE` có cờ kết quả được thiết kế rõ, nhưng không dùng `INSERT IGNORE` nếu nó có thể che lỗi khác.

Quan trọng: insert event ID và cập nhật quantity phải cùng transaction và cùng database. Nếu insert event ID commit trước rồi process dừng trước khi update quantity, lần retry sẽ bị dedupe và mất tác động. Nếu update quantity commit trước rồi mới ghi event ID, retry sẽ cộng lần nữa. Cùng transaction giúp hai thay đổi thành công hoặc rollback cùng nhau.

## 8. Tạo outbox khi upsert tạo ra sự kiện

Nếu upsert dữ liệu nghiệp vụ cần phát sự kiện, ghi outbox trong cùng transaction:

```sql
START TRANSACTION;

INSERT INTO customer_profile (
    source_system,
    external_id,
    display_name,
    source_version
)
VALUES ('crm-a', 'C-100', 'Nguyen An', 8) AS incoming
ON DUPLICATE KEY UPDATE
    display_name = IF(
        incoming.source_version > customer_profile.source_version,
        incoming.display_name,
        customer_profile.display_name
    ),
    source_version = GREATEST(
        customer_profile.source_version,
        incoming.source_version
    );

INSERT INTO outbox_event (
    id, aggregatetype, aggregateid, type, payload
)
VALUES (
    UUID(),
    'Customer',
    'C-100',
    'CustomerSynchronized',
    JSON_OBJECT('sourceVersion', 8)
);

COMMIT;
```

Ví dụ chỉ minh họa transaction boundary. Nếu request được gửi lại, câu lệnh outbox trên sẽ tạo event mới với UUID mới mỗi lần. Nếu sự kiện chỉ cần phát khi dữ liệu thực sự thay đổi, phải xác định rõ nhánh insert/update có thay đổi hay không và dùng một event identity ổn định theo command/version. Không phát một event nghiệp vụ mới cho mỗi lần retry của cùng command.

Một cách thiết kế là lưu `command_id` hoặc `event_id` ổn định trong outbox với unique constraint, hoặc tạo outbox event chỉ sau khi đã xác định request là mới và transaction đang xử lý lần đầu. CDC sẽ phát lại binlog khi phục hồi connector, vì vậy consumer vẫn cần dedupe theo event ID.

## 9. Upsert trong Java với PreparedStatement

Dùng parameter binding để tránh SQL injection và xử lý đúng kiểu dữ liệu:

```java
String sql = """
    INSERT INTO external_product (
        source_system, external_id, sku, display_name,
        source_version, source_updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?) AS incoming
    ON DUPLICATE KEY UPDATE
        sku = IF(
            incoming.source_version > external_product.source_version,
            incoming.sku,
            external_product.sku
        ),
        display_name = IF(
            incoming.source_version > external_product.source_version,
            incoming.display_name,
            external_product.display_name
        ),
        source_updated_at = IF(
            incoming.source_version > external_product.source_version,
            incoming.source_updated_at,
            external_product.source_updated_at
        ),
        source_version = GREATEST(
            external_product.source_version,
            incoming.source_version
        )
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, sourceSystem);
    ps.setString(2, externalId);
    ps.setString(3, sku);
    ps.setString(4, displayName);
    ps.setLong(5, sourceVersion);
    ps.setTimestamp(6, Timestamp.valueOf(sourceUpdatedAt));
    ps.executeUpdate();
}
```

SQL trên giả định Connector/J và MySQL hỗ trợ row alias trong upsert. `sourceVersion` phải là version tăng đơn điệu do nguồn cấp; nếu version có thể reset hoặc chỉ duy nhất trong từng epoch, cần bổ sung source epoch/sequence vào hợp đồng. Câu lệnh bảo vệ khỏi snapshot cũ hơn, nhưng cùng version với payload khác vẫn cần kiểm tra hash/conflict ở tầng ứng dụng.

## 10. Spring Data JPA: save không đồng nghĩa native upsert

`JpaRepository.save()` chọn persist hoặc merge dựa trên trạng thái entity và cách provider nhận diện entity mới. Nó không mặc nhiên sinh ra `INSERT ... ON DUPLICATE KEY UPDATE`. Một luồng “đọc trước, nếu có thì update, không có thì insert” vẫn có race giữa các instance.

Các lựa chọn:

- Dùng unique constraint ở database làm lớp bảo vệ cuối cùng.
- Dùng native query `INSERT ... ON DUPLICATE KEY UPDATE` qua repository hoặc `JdbcTemplate`.
- Dùng transaction và xử lý duplicate-key một cách rõ ràng.
- Với idempotency key, lưu request/result cùng transaction nghiệp vụ.

Ví dụ native query trong Spring Data JPA:

```java
@Modifying
@Query(value = """
    INSERT INTO product_stock (sku, available_quantity, source_version)
    VALUES (:sku, :quantity, :version) AS incoming
    ON DUPLICATE KEY UPDATE
        available_quantity = IF(
            incoming.source_version > product_stock.source_version,
            incoming.available_quantity,
            product_stock.available_quantity
        ),
        source_version = GREATEST(
            product_stock.source_version,
            incoming.source_version
        )
    """, nativeQuery = true)
int upsertSnapshot(
    @Param("sku") String sku,
    @Param("quantity") int quantity,
    @Param("version") long version
);
```

Đây là ví dụ cho MySQL hỗ trợ alias row; cần kiểm tra cú pháp native query và transaction context theo phiên bản Spring Data JPA/Hibernate. Nếu persistence context đã chứa entity tương ứng, native SQL có thể làm entity trong bộ nhớ không còn đồng bộ với database. Cân nhắc `clearAutomatically`, refresh hoặc không giữ entity đó trong cùng persistence context.

## 11. Transaction, isolation và cạnh tranh đồng thời

Unique constraint là cơ chế bảo vệ tính duy nhất ở database. Khi hai transaction cùng insert một khóa nghiệp vụ, InnoDB điều phối xung đột trên unique index; một transaction có thể phải chờ transaction còn lại commit hoặc rollback.

Kịch bản hai request cùng idempotency key:

1. Transaction A insert key K và giữ unique-key lock.
2. Transaction B thử insert key K và phải chờ.
3. Nếu A commit, B đi vào nhánh duplicate và đọc kết quả đã hoàn tất.
4. Nếu A rollback, B có thể insert key K và thực hiện nghiệp vụ.

Điều này chỉ hoạt động đúng nếu request record và thay đổi nghiệp vụ nằm trong cùng transaction. Không dùng `SELECT` không khóa để quyết định “key chưa tồn tại” rồi insert sau đó; giữa hai bước, transaction khác có thể tạo key đó.

`SELECT ... FOR UPDATE` có thể khóa hàng idempotency sau khi đã tồn tại. Unique constraint vẫn cần thiết để xử lý trường hợp hàng chưa tồn tại và hai transaction đồng thời tạo nó. Không dựa vào isolation level đơn lẻ thay cho unique key.

### Transaction ngắn và retry

Không giữ transaction trong khi gọi HTTP hoặc chờ broker. Nếu cần side effect bên ngoài, dùng outbox. Với deadlock hoặc lock wait timeout, rollback toàn bộ unit of work rồi retry theo giới hạn và backoff có jitter. Không chỉ chạy lại statement cuối nếu các statement trước đã thay đổi dữ liệu.

## 12. Kiểm thử tính idempotent

Một bộ test tốt cần kiểm tra cả dữ liệu cuối cùng và số lần tác động nghiệp vụ:

| Kịch bản | Thực hiện | Kết quả mong đợi |
|---|---|---|
| Insert mới | Gửi một khóa nghiệp vụ chưa tồn tại. | Một hàng được tạo. |
| Gửi lại cùng snapshot | Gửi cùng khóa và cùng payload nhiều lần. | Một hàng; trạng thái cuối không đổi. |
| Snapshot cũ đến muộn | Gửi version 12 rồi version 11. | Dữ liệu version 12 vẫn được giữ. |
| Cùng version, payload khác | Gửi cùng key/version nhưng nội dung khác. | Phát hiện xung đột; không âm thầm ghi đè. |
| Hai request cùng key đồng thời | Gửi cùng idempotency key từ hai connection. | Một tác động nghiệp vụ; request còn lại nhận kết quả đã lưu hoặc xử lý sau rollback. |
| Cùng key, payload khác | Dùng lại key với request hash khác. | Trả xung đột, không thực hiện nghiệp vụ lần hai. |
| Delta event phát lại | Gửi cùng event ID hai lần. | Chỉ áp dụng delta một lần. |
| Crash trước commit | Dừng/rollback transaction sau khi ghi idempotency row và business row. | Không có thay đổi nào được commit; retry có thể thực hiện lại. |
| Timeout sau commit | Mô phỏng client không nhận response dù transaction đã commit. | Retry trả response đã lưu, không tạo thêm tác động. |
| Duplicate key khác unique index | Tạo payload trùng unique key không phải khóa nghiệp vụ chính. | Xử lý conflict rõ ràng, không update nhầm hàng. |

Không chỉ assert số dòng trong bảng chính. Hãy kiểm tra outbox event, payment/transfer log, audit row và mọi counter có liên quan. Một hàng chính duy nhất không chứng minh nghiệp vụ chỉ chạy một lần nếu bảng log hoặc side effect đã bị nhân đôi.

## 13. Bài lab với hai session MySQL

Tạo bảng thử nghiệm:

```sql
CREATE TABLE stock_snapshot (
    sku VARCHAR(40) NOT NULL,
    quantity INT NOT NULL,
    source_version BIGINT NOT NULL,
    PRIMARY KEY (sku)
) ENGINE=InnoDB;
```

**Bài A — upsert lặp lại**

Chạy cùng câu lệnh hai lần:

```sql
INSERT INTO stock_snapshot (sku, quantity, source_version)
VALUES ('SKU-01', 20, 10) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = incoming.quantity,
    source_version = incoming.source_version;
```

Kiểm tra:

```sql
SELECT * FROM stock_snapshot WHERE sku = 'SKU-01';
```

Kết quả phải có một hàng và quantity vẫn bằng 20. Thay câu update bằng phép cộng `quantity = stock_snapshot.quantity + incoming.quantity`, chạy hai lần và quan sát kết quả sai để hiểu vì sao delta cần event dedupe.

**Bài B — hai transaction cùng một khóa**

Mở hai session. Session A bắt đầu transaction và upsert một SKU. Giữ transaction chưa commit. Session B chạy upsert cùng SKU và quan sát việc chờ unique-key conflict. Commit Session A, sau đó kiểm tra Session B hoàn tất theo nhánh duplicate. Lặp lại nhưng rollback Session A và quan sát Session B có thể insert.

**Bài C — chống snapshot cũ**

Upsert version 12 với quantity 30, sau đó gửi version 11 với quantity 15. Dùng câu lệnh có điều kiện version ở phần 3. Kiểm tra hàng vẫn giữ quantity 30 và version 12.

## 14. Bài lab Spring Boot tích hợp

Xây dựng API `PUT /inventory/{sku}` nhận `Idempotency-Key` và payload gồm quantity, source version:

1. Tạo migration cho `product_stock` có unique key trên SKU và `api_idempotency` có unique key theo tenant/key.
2. Tạo DTO có validation; chuẩn hóa JSON trước khi tính SHA-256 request hash.
3. Viết service `@Transactional`: lấy/tạo idempotency row, kiểm tra hash, thực hiện upsert snapshot và lưu response.
4. Nếu key đã hoàn tất với cùng hash, trả lại response cũ.
5. Nếu key đã tồn tại nhưng hash khác, trả HTTP 409.
6. Nếu request version thấp hơn version đã lưu, không ghi đè dữ liệu mới.
7. Tạo integration test chạy trên MySQL thật hoặc Testcontainers với hai connection đồng thời.
8. Mô phỏng client timeout sau commit rồi gửi lại request; xác minh response được phát lại và không có bản ghi nghiệp vụ mới.
9. Mô phỏng hai request đồng thời cùng key; xác minh chỉ có một kết quả nghiệp vụ.
10. Nếu API cần phát event, ghi outbox với event ID ổn định trong cùng transaction; kiểm tra CDC/consumer dedupe riêng.
11. Đo lock wait, deadlock, thời gian transaction và tỷ lệ request được phục vụ từ kết quả idempotency cũ.
12. Viết runbook về retention idempotency key, conflict hash, retry và điều tra request trùng.

## 15. Retention và giới hạn của idempotency key

Idempotency key không nên bị xóa ngay sau khi request thành công. Nếu xóa quá sớm, client hoặc message broker có thể gửi lại request cũ sau thời hạn lưu và ứng dụng sẽ coi đó là request mới.

Chính sách retention cần dựa trên:

- Thời gian client có thể retry.
- Thời gian message có thể nằm trong broker hoặc dead-letter queue trước khi replay.
- Thời hạn đối soát và điều tra nghiệp vụ.
- Quy định lưu trữ dữ liệu và quyền riêng tư.
- Khả năng khôi phục từ backup hoặc replay sự kiện.

Với giao dịch tài chính hoặc thao tác không được lặp trong suốt vòng đời nghiệp vụ, unique key ở bảng nghiệp vụ (ví dụ provider transaction ID hoặc payment reference) vẫn cần tồn tại kể cả khi bản ghi idempotency API đã hết hạn. Idempotency key của transport và unique business reference giải quyết hai lớp vấn đề khác nhau.

Không lưu payload nhạy cảm đầy đủ trong bảng idempotency nếu chỉ cần hash và response tối thiểu. Có thể lưu hash, resource ID, mã kết quả và một response đã lọc dữ liệu nhạy cảm. Nếu response phải được phát lại nguyên vẹn, xác định rõ chính sách mã hóa và thời hạn lưu.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Request retry tạo hàng mới | Thiếu unique business key hoặc key không phản ánh đúng danh tính nghiệp vụ. | Thêm unique constraint theo khóa nghiệp vụ ổn định. |
| Quantity tăng nhiều lần | Upsert dùng phép cộng delta mà không deduplicate event ID. | Dùng inbox/applied-event unique key và cập nhật delta cùng transaction. |
| Request cùng key nhưng payload khác vẫn được chấp nhận | Không lưu/so sánh request hash. | So sánh hash và trả conflict khi nội dung khác. |
| Snapshot cũ ghi đè dữ liệu mới | Upsert không kiểm tra source version. | Chỉ áp dụng khi version đầu vào mới hơn; xử lý same-version conflict. |
| Hai request đồng thời tạo duplicate | Chỉ SELECT trước INSERT, không có unique constraint hoặc không xử lý duplicate. | Dùng unique key và transaction; kiểm thử cạnh tranh nhiều connection. |
| Upsert cập nhật nhầm hàng | Có nhiều unique index có thể xung đột với các hàng khác nhau. | Tách định danh, xác minh conflict key hoặc xử lý trước bằng transaction rõ ràng. |
| Retry tạo audit/outbox event trùng | Trigger hoặc code luôn phát event cho nhánh duplicate. | Chỉ tạo event cho command mới/thay đổi thực sự; dùng event ID ổn định và unique constraint. |
| Dùng `REPLACE` làm mất liên kết | `REPLACE` thực hiện delete rồi insert. | Dùng `ON DUPLICATE KEY UPDATE` hoặc transaction nghiệp vụ phù hợp. |
| Số dòng affected rows bị hiểu sai | Kết quả phụ thuộc insert/update/no-op và client flag. | Không dùng affected rows làm idempotency decision; đọc trạng thái bằng key. |
| JPA `save()` vẫn gặp race | `save()` không phải native atomic upsert. | Dùng unique constraint, native upsert hoặc xử lý duplicate trong transaction. |

## 17. Tiêu chí hoàn thành

Bài thực hành đạt yêu cầu khi:

- Khóa nghiệp vụ và unique constraint được xác định rõ.
- Cùng snapshot được gửi nhiều lần không làm thay đổi trạng thái ngoài dự kiến.
- Snapshot cũ không ghi đè snapshot mới.
- Cùng idempotency key và cùng request hash trả lại kết quả cũ.
- Cùng idempotency key nhưng payload khác bị từ chối.
- Delta event được áp dụng tối đa một lần trong database consumer nhờ event ID và transaction.
- Hai request đồng thời không tạo hai tác động nghiệp vụ.
- Retry sau timeout không tạo payment, transfer log hoặc outbox event trùng.
- Mọi side effect ngoài MySQL có idempotency hoặc được phát qua outbox.
- Test chạy trên MySQL tương thích production và kiểm tra cả dữ liệu lẫn log nghiệp vụ.

Sau bài thực hành, người học cần giải thích được vì sao unique constraint là lớp bảo vệ cuối cùng, vì sao upsert snapshot khác upsert delta, vì sao idempotency key cần request hash và retention, và vì sao mọi ghi nhận dedupe phải cùng transaction với thay đổi nghiệp vụ. Đây là nền tảng để xây dựng API, worker và luồng đồng bộ có thể retry mà không ghi trùng nghiệp vụ.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual: INSERT ... ON DUPLICATE KEY UPDATE](https://dev.mysql.com/doc/refman/8.4/en/insert-on-duplicate.html)
- [MySQL 8.4 Reference Manual: InnoDB Locking](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html)
- [MySQL 8.4 Reference Manual: InnoDB and AUTO_INCREMENT Handling](https://dev.mysql.com/doc/refman/8.4/en/innodb-auto-increment-handling.html)
- [Spring Framework Reference: Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/)
