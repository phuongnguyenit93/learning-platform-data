# Phối hợp thay đổi schema với phát hành liên tục

Trong hệ thống phát hành liên tục, nhiều phiên bản ứng dụng có thể cùng tồn tại trong một khoảng thời gian. Khi triển khai rolling update, một số instance vẫn chạy code cũ trong khi instance mới đã bắt đầu nhận request. Worker nền, message consumer và tác vụ batch cũng có thể chạy độc lập với vòng đời của HTTP service. Vì vậy, thay đổi schema database phải tương thích với các phiên bản ứng dụng đang hoạt động trong suốt quá trình rollout.

Với Spring Data R2DBC, mapping entity, câu query, converter và repository đều phụ thuộc schema hiện tại. Một migration đổi tên hoặc xóa cột ngay khi code mới được phát hành có thể làm instance cũ lỗi; ngược lại, code mới đọc một cột chưa được tạo cũng có thể thất bại trước khi migration hoàn tất. Giải pháp phổ biến là triển khai schema theo từng bước tương thích, thường gọi là *expand-and-contract*: mở rộng schema trước, phát hành code có thể làm việc với cả cấu trúc cũ và mới, chuyển dữ liệu/traffic, rồi mới loại bỏ cấu trúc cũ sau khi không còn consumer sử dụng.

Mục tiêu của quy trình này là giữ ứng dụng hoạt động trong khi schema tiến hóa, giảm thời gian downtime, cho phép rollback ứng dụng trong cửa sổ triển khai và làm cho migration có thể quan sát, kiểm thử và kiểm soát.

## 1. Vì sao thay đổi schema cần phối hợp với release?

Một release thường gồm ít nhất hai thay đổi độc lập:

- Thay đổi database: thêm/xóa cột, bảng, index, constraint, kiểu dữ liệu hoặc chuyển đổi dữ liệu.
- Thay đổi ứng dụng: entity mapping, repository query, DTO, business logic và cách ghi/đọc dữ liệu.

Nếu hai thay đổi không tương thích được triển khai cùng một thời điểm nguyên tử, rolling deployment tạo ra khoảng thời gian mà code và schema không khớp.

Ví dụ một ứng dụng cũ đang chạy query:

```sql
SELECT id, full_name
FROM customers
WHERE id = :id
```

Release mới muốn đổi `full_name` thành `display_name`. Nếu migration đổi tên cột ngay trước khi instance mới được triển khai, các instance cũ vẫn query `full_name` và bắt đầu lỗi. Nếu triển khai code mới trước, instance mới query `display_name` trong khi cột chưa tồn tại và cũng lỗi.

Rolling update còn làm cho hai phiên bản cùng hoạt động:

```text
Thời gian  ---------------------------------------------------->

Database:  [schema cũ] ---- [mở rộng schema] -------------------

App v1:    [v1 v1 v1 v1 v1] [v1 v1] [drain] --------------------
App v2:                      [v2] [v2 v2 v2 v2 v2] ------------

Trong vùng rollout, cả v1 và v2 đều phải chạy được trên schema.
```

Không thể giả định mọi instance được thay thế cùng một mili giây. Cũng không thể giả định rollback chỉ là đưa container cũ lên lại; schema đã thay đổi có thể khiến code cũ không còn chạy được.

### 1.1. Các nguồn consumer cần tính đến

Khi lập kế hoạch schema migration, hãy kiểm kê mọi thành phần truy cập database:

- HTTP application instances.
- Reactive message consumers và scheduled jobs.
- Batch jobs hoặc data pipelines.
- Admin tools, reporting services và ứng dụng khác dùng chung database.
- Các phiên bản ứng dụng cũ còn sống trong quá trình rollout.
- Script vận hành hoặc tích hợp ngoài có query trực tiếp.

Một cột chỉ an toàn để xóa khi tất cả consumer đã ngừng dùng nó, không chỉ khi HTTP deployment chính đã hoàn tất.

## 2. Nguyên tắc tương thích trong rolling deployment

Một migration an toàn thường cần giữ schema tương thích với cả code trước và sau release trong một khoảng thời gian.

| Thay đổi | Rủi ro khi triển khai trực tiếp | Cách tiếp cận an toàn thường dùng |
|---|---|---|
| Thêm cột nullable | Code cũ thường bỏ qua cột mới; code mới có thể cần giá trị | Thêm cột trước, triển khai code tương thích, sau đó backfill và thêm constraint nếu cần |
| Thêm bảng | Ít ảnh hưởng code cũ nếu chưa có truy cập | Tạo bảng trước khi code mới sử dụng |
| Thêm index | Có thể khóa hoặc làm tăng tải khi tạo | Dùng phương thức online/concurrent nếu database hỗ trợ |
| Thêm giá trị enum/constraint | Code cũ có thể không hiểu giá trị mới | Mở rộng consumer trước khi bắt đầu ghi giá trị mới |
| Đổi tên cột | Code cũ hoặc mới sẽ không tìm thấy tên còn lại | Thêm cột mới, dual-write/backfill, chuyển read, rồi xóa cột cũ ở release sau |
| Xóa cột | Code cũ có thể vẫn query hoặc ghi cột | Ngừng dùng cột, triển khai toàn bộ consumer, rồi mới drop |
| Đổi kiểu dữ liệu | Conversion có thể mất dữ liệu hoặc query lỗi | Tạo cột mới, chuyển đổi theo batch, xác minh rồi chuyển ứng dụng |
| Thay đổi semantics | Cấu trúc vẫn hợp lệ nhưng dữ liệu được hiểu khác | Version hóa logic, dual-read/dual-write có kiểm soát và chuyển đổi từng bước |

Quy tắc quan trọng là **thay đổi phá vỡ tương thích cần được tách thành nhiều release**. Nếu không thể giữ tương thích, cần một cửa sổ maintenance có downtime được chấp thuận và có quy trình dừng traffic, drain connection, migration và khởi động lại rõ ràng.

## 3. Mẫu Expand-and-Contract

Expand-and-contract chia một thay đổi phá vỡ thành các bước nhỏ, mỗi bước vẫn tương thích với phiên bản đang chạy.

```text
1. EXPAND
   Thêm cấu trúc mới, giữ cấu trúc cũ.
       |
       v
2. COMPATIBLE RELEASE
   Deploy code có thể đọc/ghi schema cũ và mới.
       |
       v
3. BACKFILL / VERIFY
   Chuyển dữ liệu cũ sang cấu trúc mới, kiểm tra kết quả.
       |
       v
4. SWITCH OVER
   Chuyển đọc/ghi chính sang cấu trúc mới.
       |
       v
5. CONTRACT
   Chờ mọi consumer cũ được drain, rồi bỏ cấu trúc cũ.
```

Không nhất thiết mọi thay đổi đều cần dual-write. Thêm một cột độc lập có thể chỉ cần expand rồi deploy. Nhưng với rename, split/merge field hoặc thay đổi kiểu dữ liệu, các bước trung gian giúp tránh việc một phiên bản ghi dữ liệu mà phiên bản khác không thể đọc.

### 3.1. Giai đoạn Expand

Thêm schema mới nhưng chưa xóa hoặc đổi tên cấu trúc cũ. Ví dụ đổi `full_name` thành `display_name`:

```sql
ALTER TABLE customers
ADD COLUMN display_name VARCHAR(160);
```

Ở bước này:

- Code cũ vẫn dùng `full_name`.
- Code mới chưa được phép giả định `display_name` đã chứa dữ liệu.
- Không đặt `NOT NULL` ngay nếu các hàng cũ chưa có giá trị.
- Không drop hoặc rename cột cũ.
- Nếu cần index/constraint, đánh giá cách tạo online để giảm lock.

### 3.2. Giai đoạn Compatible Release

Triển khai code có thể làm việc với cả schema cũ và mới. Một cách là ghi cả hai cột trong thời gian chuyển tiếp:

```sql
UPDATE customers
SET full_name = :name,
    display_name = :name
WHERE id = :id;
```

Với Spring Data R2DBC, có thể ánh xạ cả hai property tạm thời hoặc dùng một custom repository để dual-write. Code mới vẫn cần giữ `full_name` đồng bộ để instance cũ tiếp tục đọc được dữ liệu vừa ghi.

Không triển khai code chỉ ghi `display_name` trong khi instance cũ còn đọc `full_name`, trừ khi đã chứng minh mọi đường ghi đều cập nhật cột cũ bằng trigger hoặc cơ chế tương đương.

### 3.3. Giai đoạn Backfill

Chuyển dữ liệu cũ sang cột mới theo batch:

```sql
UPDATE customers
SET display_name = full_name
WHERE display_name IS NULL;
```

Với bảng lớn, không chạy một transaction khổng lồ nếu điều đó tạo lock, WAL/redo log lớn hoặc ảnh hưởng replication. Chia thành batch theo khóa chính, giới hạn concurrency và theo dõi tiến độ. Backfill cần idempotent: chạy lại không làm sai dữ liệu đã chuyển.

### 3.4. Giai đoạn Switch Over

Sau khi backfill hoàn tất và dữ liệu được xác minh, chuyển code đọc từ `display_name`. Trong một khoảng thời gian, có thể tiếp tục ghi cả hai cột để giữ rollback window. Sau khi mọi instance cũ đã được drain và code mới ổn định, có thể phát hành một release ngừng ghi `full_name`.

### 3.5. Giai đoạn Contract

Chỉ khi không còn code, job, report hoặc integration nào dùng `full_name`, mới drop cột cũ:

```sql
ALTER TABLE customers DROP COLUMN full_name;
```

Đây là bước phá vỡ tương thích. Nó nên nằm trong một migration/release riêng sau khi rollback window của phiên bản phụ thuộc cột cũ đã kết thúc.

## 4. Ví dụ rename cột với Spring Data R2DBC

Giả sử entity cũ:

```java
@Table("customers")
public record CustomerEntity(
        @Id Long id,
        @Column("full_name") String fullName
) {
}
```

Mục tiêu là chuyển sang:

```java
@Table("customers")
public record CustomerEntity(
        @Id Long id,
        @Column("display_name") String displayName
) {
}
```

Không nên chỉ đổi annotation và deploy cùng lúc với `ALTER TABLE ... RENAME COLUMN`. Trong rolling deployment, instance cũ sẽ tiếp tục truy cập `full_name`.

### 4.1. Release A: mở rộng schema

Migration thêm cột mới nullable:

```sql
ALTER TABLE customers
ADD COLUMN display_name VARCHAR(160);
```

Entity cũ vẫn chạy bình thường vì nó không cần biết cột mới.

### 4.2. Release B: code tương thích hai cột

Tạm thời biểu diễn cả hai property:

```java
@Table("customers")
public record CustomerEntity(
        @Id Long id,
        @Column("full_name") String fullName,
        @Column("display_name") String displayName
) {
}
```

Service hoặc custom repository bảo đảm cả hai cột được ghi cùng giá trị. Khi đọc, ưu tiên giá trị mới nếu đã có, nhưng vẫn có thể fallback sang cột cũ trong thời gian backfill:

```java
String effectiveName = displayName != null ? displayName : fullName;
```

Nếu dùng `save(entity)` với entity mapping cả hai property, cần bảo đảm các đường update không ghi null vào cột còn lại. Với logic dual-write quan trọng, một custom SQL update tường minh thường dễ kiểm soát hơn việc dựa vào object có nhiều trường nullable.

### 4.3. Backfill dữ liệu

Chạy migration/backfill theo batch cho các hàng có `display_name IS NULL`. Xác minh không còn hàng cần chuyển và kiểm tra hai cột khớp nhau trong phạm vi dữ liệu được phép.

### 4.4. Release C: chuyển đọc sang cột mới

Code mới chỉ đọc `display_name`, nhưng vẫn ghi cả hai cột trong thời gian rollback. Khi mọi instance và worker đã dùng release mới, theo dõi log/query để xác nhận không còn truy cập cột cũ.

### 4.5. Release D: ngừng ghi cột cũ

Triển khai code chỉ ghi `display_name`. Giữ cột `full_name` thêm một cửa sổ an toàn nếu rollback vẫn có thể xảy ra; nếu rollback về code cũ, code cũ sẽ cần `full_name` có dữ liệu mới nhất. Có thể giữ dual-write lâu hơn hoặc quyết định rollback sau giai đoạn này chỉ thực hiện bằng forward fix.

### 4.6. Release E: contract

Sau khi cửa sổ rollback đóng, drop `full_name` và loại property cũ khỏi entity. Không gộp bước drop vào cùng release đầu tiên chuyển đọc, vì điều đó làm mất khả năng chạy lại phiên bản cũ khi cần.

## 5. Thêm cột, constraint và index theo cách an toàn

Không phải mọi DDL đều có cùng tác động lên workload. Một lệnh thêm cột nullable có thể nhanh, trong khi tạo index trên bảng lớn hoặc thêm constraint cần quét dữ liệu có thể gây tải và lock.

### 5.1. Thêm cột nullable trước

Khi thêm thuộc tính mới:

```sql
ALTER TABLE orders ADD COLUMN source_channel VARCHAR(30);
```

Đây thường là bước expand ít phá vỡ hơn so với thêm `NOT NULL` ngay. Code cũ bỏ qua cột mới; code mới cần xử lý null cho dữ liệu chưa backfill.

Nếu database có cách thêm cột với default nhanh hoặc metadata-only, hành vi phụ thuộc phiên bản server. Không suy rộng từ một database sang hệ quản trị khác. Đọc tài liệu DDL và đo trên dữ liệu đại diện.

### 5.2. Thêm NOT NULL sau khi backfill

Quy trình thường là:

1. Thêm cột nullable.
2. Deploy code ghi giá trị cho bản ghi mới.
3. Backfill bản ghi cũ theo batch.
4. Kiểm tra không còn null.
5. Thêm constraint `NOT NULL` trong một migration riêng.

```sql
ALTER TABLE orders
ALTER COLUMN source_channel SET NOT NULL;
```

Cú pháp và mức lock phụ thuộc database. Với PostgreSQL, có thể dùng constraint/check validation theo giai đoạn cho một số loại ràng buộc; với hệ quản trị khác, cách triển khai khác nhau. Kiểm tra tài liệu và lock behavior trước khi áp dụng trên bảng lớn.

### 5.3. Tạo index online/concurrently

Index có thể cải thiện query mới nhưng tạo index trên bảng lớn có thể khóa ghi hoặc làm tăng I/O. PostgreSQL hỗ trợ `CREATE INDEX CONCURRENTLY`:

```sql
CREATE INDEX CONCURRENTLY idx_orders_source_channel
ON orders(source_channel);
```

Lệnh này có giới hạn riêng, ví dụ không chạy bên trong transaction block thông thường. Migration tool cần được cấu hình để chạy migration đó ngoài transaction nếu database yêu cầu. `CREATE INDEX CONCURRENTLY` là cú pháp PostgreSQL, không phải portable SQL.

Trên database khác, tìm cơ chế online index tương ứng. Nếu không có, đánh giá maintenance window, lock và tác động lên production trước khi triển khai.

### 5.4. Thêm unique constraint theo giai đoạn

Nếu cần đảm bảo giá trị mới là duy nhất, đừng thêm constraint trước khi kiểm tra dữ liệu hiện tại. Hãy tìm và xử lý duplicate, tạo unique index theo phương thức phù hợp, rồi gắn constraint nếu database hỗ trợ. Trong thời gian chuyển đổi, code vẫn phải xử lý race condition và unique violation vì kiểm tra tồn tại ở ứng dụng không thay thế constraint database.

## 6. Thay đổi kiểu dữ liệu mà không làm gián đoạn ứng dụng

Đổi kiểu trực tiếp có thể làm mất dữ liệu, khóa bảng hoặc khiến phiên bản cũ không đọc được giá trị mới. Với thay đổi lớn, dùng cột mới:

1. Thêm cột mới với kiểu đích.
2. Deploy code có thể đọc/ghi cả cột cũ và mới.
3. Backfill bằng conversion có kiểm soát.
4. So sánh dữ liệu cũ và mới, xử lý giá trị không convert được.
5. Chuyển read path sang cột mới.
6. Ngừng ghi cột cũ sau khi mọi consumer đã nâng cấp.
7. Drop cột cũ trong release sau.

Ví dụ chuyển `phone_number` từ integer sang text để giữ số 0 đầu và ký tự định dạng:

```sql
ALTER TABLE customers ADD COLUMN phone_number_text VARCHAR(40);
```

Backfill cần quy tắc rõ ràng. Nếu cột cũ đã lưu số nguyên, các số 0 đầu đã mất và không thể khôi phục chỉ bằng cast. Cần dữ liệu nguồn hoặc quy tắc nghiệp vụ để tái tạo. Đây là lý do cần phân tích semantics trước khi viết migration.

## 7. Backfill dữ liệu lớn bằng batch

Backfill là công việc chuyển dữ liệu hiện hữu sang cấu trúc mới. Trên bảng lớn, không nên giữ một transaction khổng lồ hoặc tải toàn bộ ID vào bộ nhớ.

### 7.1. Dùng keyset theo khóa chính

Có thể xử lý từng nhóm ID:

```sql
SELECT id
FROM customers
WHERE id > :lastId
  AND display_name IS NULL
ORDER BY id
LIMIT :batchSize;
```

Sau khi xử lý batch, cập nhật cursor `lastId` bằng ID cuối cùng. Keyset tránh offset lớn và cho phép tiếp tục từ checkpoint nếu job dừng.

### 7.2. Update theo batch

Với mỗi batch, có thể dùng update theo tập ID hoặc update range:

```sql
UPDATE customers
SET display_name = full_name
WHERE id > :fromId
  AND id <= :toId
  AND display_name IS NULL;
```

Predicate `display_name IS NULL` giúp job idempotent: nếu batch chạy lại, các hàng đã được chuyển không bị ghi đè. Nếu có concurrent writer, cần xác định quy tắc ai thắng và tránh backfill ghi đè dữ liệu mới hơn.

### 7.3. Thực hiện reactive với concurrency hữu hạn

Ví dụ minh họa một job đọc batch rồi cập nhật:

```java
Flux<Long> loadIdsAfter(long lastId, int batchSize) {
    return databaseClient.sql("""
            SELECT id
            FROM customers
            WHERE id > :lastId
              AND display_name IS NULL
            ORDER BY id
            LIMIT :batchSize
            """)
            .bind("lastId", lastId)
            .bind("batchSize", batchSize)
            .map((row, metadata) -> row.get("id", Long.class))
            .all();
}
```

Với batch ID, có thể dùng query update theo `IN` hoặc chia range. Nếu mỗi batch là một transaction riêng, dùng `concatMap` để xử lý tuần tự hoặc `flatMap` với concurrency nhỏ được cấu hình rõ:

```java
Flux.fromIterable(batches)
        .concatMap(this::migrateBatch);
```

Không dùng `flatMap` không giới hạn cho hàng triệu bản ghi. Backfill có thể cạnh tranh connection với traffic ứng dụng và làm tăng latency production.

### 7.4. Checkpoint, retry và idempotency

Lưu checkpoint sau khi batch commit thành công. Nếu job bị dừng, có thể tiếp tục từ checkpoint hoặc quét lại theo predicate idempotent. Không cập nhật checkpoint trước khi transaction dữ liệu hoàn tất, nếu không job có thể bỏ qua một batch chưa được commit.

Retry chỉ áp dụng cho lỗi tạm thời và cần giới hạn. Một batch update có thể được chạy lại nếu câu lệnh idempotent. Với chuyển đổi không idempotent, cần lưu trạng thái xử lý hoặc thiết kế thao tác có thể nhận biết batch đã hoàn thành.

### 7.5. Điều tiết tải

Theo dõi query latency, active connections, lock wait, replication lag, CPU và I/O. Có thể giới hạn batch size, concurrency hoặc tạm dừng job khi traffic ứng dụng tăng. Backfill nên có khả năng pause/resume và không giữ transaction lâu.

## 8. Migration có tương thích không đồng nghĩa migration không có lock

Một migration có thể tương thích với code cũ nhưng vẫn gây gián đoạn do DDL lock hoặc tải I/O. Cần đánh giá riêng:

- Thời gian giữ lock và loại lock.
- Bảng có đang nhận ghi liên tục không?
- DDL có quét toàn bảng hoặc rewrite dữ liệu không?
- Migration có chạy trong transaction không?
- Có thể hủy migration an toàn không?
- Replication lag và WAL/redo log tăng ra sao?
- Có cần chạy trên replica hoặc maintenance window không?

Tính tương thích ứng dụng và tác động vận hành là hai tiêu chí khác nhau. Một `ALTER TABLE` không làm code cũ lỗi vẫn có thể chờ lock lâu hoặc chặn traffic nếu database phải rewrite bảng.

### 8.1. Lock timeout và statement timeout

Với database hỗ trợ, đặt timeout phù hợp cho migration để tránh chờ lock vô hạn. Ví dụ PostgreSQL có `lock_timeout` và `statement_timeout`. Giá trị cụ thể phụ thuộc quy trình release và thời gian cho phép. Nếu migration không lấy được lock trong giới hạn, thường tốt hơn là fail sớm và thử lại theo quy trình có kiểm soát thay vì giữ hàng đợi DDL kéo dài.

### 8.2. Migration transactional hay non-transactional

Không phải mọi DDL đều chạy được trong transaction ở mọi database. Một số lệnh như tạo index concurrently của PostgreSQL không thể chạy trong transaction block thông thường; một số database có implicit commit cho DDL. Migration tool cần cấu hình đúng cho từng migration.

Không giả định rollback transaction sẽ đảo ngược mọi DDL. Xác nhận semantics của database và migration tool trước khi đưa migration vào production.

## 9. Điều phối migration với nhiều application instances

Nếu mọi replica cùng chạy migration lúc startup, nhiều instance có thể cùng cố thay đổi schema. Migration tool thường có locking/version table để ngăn chạy trùng, nhưng vẫn cần xác nhận cơ chế đó, quyền database và cách ứng dụng khởi động khi migration thất bại.

### 9.1. Dùng migration job riêng

Một quy trình thường dễ kiểm soát là chạy migration như một bước deployment độc lập:

```text
Build artifact
     |
     v
Run migration job (one controlled runner)
     |
     v
Verify schema version / health
     |
     v
Deploy application replicas
     |
     v
Observe rollout and traffic
```

Job riêng giúp biết migration thành công trước khi rollout code phụ thuộc schema. Nó cũng tách quyền DDL khỏi quyền runtime của ứng dụng. Tuy nhiên, migration job phải chạy đúng database, đúng release artifact và có log/exit status rõ ràng.

### 9.2. Migration lock

Flyway/Liquibase và một số công cụ khác có cơ chế lock hoặc metadata table để tránh hai runner cùng áp dụng migration. Hãy kiểm tra cách lock hoạt động, thời gian chờ và hành vi khi process chết giữa migration. Không tự tạo một cơ chế lock song song nếu công cụ đã có, trừ khi có yêu cầu cụ thể.

### 9.3. Một nguồn quản lý schema

Không để mỗi application instance tự chạy một tập DDL tùy biến, đồng thời có migration job khác chạy migration chính. Chọn một nguồn quản lý schema và một quy trình áp dụng rõ ràng. Application startup có thể kiểm tra schema version hoặc khả năng truy cập, nhưng không nhất thiết phải sở hữu quyền DDL.

### 9.4. Quyền database tách biệt

Trong môi trường production, có thể cấp quyền DDL cho migration runner và chỉ cấp quyền DML cần thiết cho application runtime. Điều này giảm rủi ro ứng dụng vô tình thay đổi schema. Cấu hình role phải tính đến nhu cầu tạo temp table, sequence, function hoặc các quyền đặc thù mà workload thực sự dùng.

## 10. Flyway/Liquibase và ứng dụng R2DBC

Spring Data R2DBC dùng reactive `ConnectionFactory` cho thao tác runtime. Một số migration tool phổ biến vẫn dùng JDBC `DataSource` để chạy DDL. Vì vậy, một ứng dụng R2DBC có thể cần cả JDBC driver và cấu hình migration connection riêng.

Ví dụ về cách tách trách nhiệm:

- Migration job: kết nối JDBC tới database, áp dụng versioned migration.
- Runtime service: kết nối R2DBC tới cùng database, thực hiện query reactive.

Không giả định `spring.r2dbc.url` tự động được migration tool sử dụng. Hãy kiểm tra URL, credentials, schema và thứ tự chạy của từng công cụ.

### 10.1. Migration chạy trước application rollout

Với expand migration, pipeline có thể chạy migration trước rồi deploy code tương thích. Nếu migration job thất bại, dừng rollout và giữ phiên bản ứng dụng hiện tại. Vì migration expand phải tương thích ngược, ứng dụng cũ vẫn hoạt động trên schema đã mở rộng.

### 10.2. Contract migration chạy sau rollout

Migration drop cột hoặc constraint cũ nên chạy sau khi phiên bản không còn dùng cấu trúc đó đã được triển khai và mọi consumer cũ đã dừng. Không gắn contract migration vào cùng startup của release chuyển read path nếu rollback vẫn cần schema cũ.

## 11. Readiness, health check và schema compatibility

Ứng dụng mới không nên nhận traffic trước khi schema cần thiết đã sẵn sàng. Pipeline deployment có thể chờ migration job thành công trước khi rollout. Ngoài ra, readiness check có thể xác nhận database truy cập được và các bảng/cột thiết yếu tồn tại.

Không nhất thiết phải chạy query kiểm tra toàn bộ schema trong mỗi health probe. Kiểm tra quá nặng hoặc quá thường xuyên có thể làm tăng tải. Một schema compatibility check có thể chạy lúc startup hoặc trong deployment validation.

### 11.1. Liveness và readiness khác nhau

- **Liveness:** process còn sống và không bị treo nghiêm trọng.
- **Readiness:** instance có đủ điều kiện nhận traffic, bao gồm dependency cần thiết.

Database tạm thời không sẵn sàng có thể làm readiness fail nhưng không nhất thiết nên làm liveness fail khiến orchestrator restart liên tục. Chọn chính sách theo khả năng tự phục hồi và kiến trúc ứng dụng.

### 11.2. Schema version check

Migration tool thường lưu version đã áp dụng. Deployment pipeline có thể đọc version đó và xác nhận nằm trong khoảng code hiện tại hỗ trợ. Một cách tiếp cận là khai báo schema compatibility range trong release metadata hoặc kiểm tra một tập feature/cột bắt buộc.

Không chỉ so sánh một số version lớn nếu migrations có nhánh hoặc feature khác nhau. Điều cần xác nhận là schema thực tế đáp ứng contract của binary đang chạy.

## 12. Rollback ứng dụng và rollback schema

Rollback ứng dụng và rollback database không có cùng độ an toàn.

- **Application rollback:** triển khai lại binary/container trước đó.
- **Schema rollback:** đảo ngược migration hoặc khôi phục dữ liệu/schema cũ.
- **Forward fix:** phát hành migration/code mới để sửa trạng thái hiện tại.

Với expand-and-contract, schema mở rộng thường cho phép application rollback trong giai đoạn tương thích. Sau khi contract đã drop cột cũ hoặc thay đổi dữ liệu không thể đảo ngược, rollback code cũ có thể không còn khả thi.

### 12.1. Không tự động chạy down migration sau khi app rollback

Một down migration có thể xóa dữ liệu mới hoặc phá vỡ phiên bản khác vẫn đang chạy. Việc rollback schema cần được đánh giá riêng, có backup/restore strategy và hiểu rõ dữ liệu có thể mất.

### 12.2. Giữ rollback window

Sau khi deploy code mới:

1. Theo dõi error rate, query failure, latency và dữ liệu.
2. Giữ cột/structure cũ trong khoảng rollback đã xác định.
3. Chỉ ngừng dual-write khi đã chấp nhận không rollback về phiên bản cũ theo cách đơn giản.
4. Chỉ drop cấu trúc cũ khi rollback window kết thúc và mọi consumer đã được nâng cấp.

### 12.3. Backup và phục hồi

Với migration có nguy cơ mất dữ liệu, cần backup phù hợp, kiểm tra restore và có kế hoạch point-in-time recovery nếu database hỗ trợ. Backup chưa được thử restore không phải bằng chứng rằng có thể phục hồi trong thời gian yêu cầu.

## 13. Feature flag và chuyển traffic

Feature flag có thể tách thời điểm deploy code khỏi thời điểm bật logic mới. Ví dụ code đã hỗ trợ `display_name` nhưng vẫn đọc `full_name` cho đến khi backfill hoàn tất.

Một rollout có thể:

1. Deploy code tương thích hai schema.
2. Chạy backfill.
3. Xác minh dữ liệu.
4. Bật flag để đọc cột mới cho một nhóm traffic.
5. Quan sát kết quả và mở rộng dần.
6. Sau khi ổn định, chuyển toàn bộ traffic.
7. Ngừng sử dụng cột cũ ở release tiếp theo.

Flag không thay thế schema compatibility. Nếu code mới chỉ hoạt động khi cột mới tồn tại, migration vẫn phải chạy trước khi bật flag hoặc trước khi code khởi tạo query phụ thuộc cột đó.

### 13.1. Flag phải có kế hoạch loại bỏ

Flag chuyển tiếp nếu để tồn tại lâu sẽ làm tăng nhánh logic và khó biết cột nào còn được dùng. Gắn owner, điều kiện hoàn tất và release dự kiến xóa flag. Contract migration chỉ chạy sau khi flag đã được chuyển hoàn toàn và các consumer cũ không còn hoạt động.

## 14. Kiểm thử migration và compatibility trong CI/CD

Một pipeline tốt kiểm tra không chỉ code mới với schema mới mà cả các tổ hợp tương thích cần thiết trong rollout.

### 14.1. Test migration từ database rỗng

Khởi tạo database mới, chạy toàn bộ migration và kiểm tra schema cuối. Điều này phát hiện migration thiếu file hoặc phụ thuộc trạng thái thủ công.

### 14.2. Test upgrade từ schema phiên bản trước

Tạo database bằng migration của release trước, nạp dữ liệu đại diện, sau đó chạy migration mới. Xác nhận dữ liệu được giữ/chuyển đúng và query mới hoạt động.

### 14.3. Test old code với expanded schema

Nếu có thể, chạy integration test của binary cũ trên schema sau expand. Đây là kiểm tra trực tiếp rằng migration chưa phá vỡ phiên bản đang chạy trong rolling deployment.

### 14.4. Test new code với expanded schema

Chạy integration test của binary mới trên schema sau expand trước khi contract. Kiểm tra dual-write, fallback read, null handling và query projection.

### 14.5. Test contract sau khi ngừng dùng cột cũ

Chạy bộ test của phiên bản mới nhất trên schema sau contract. Đồng thời kiểm tra không còn query, mapping, job hoặc report nào tham chiếu cột cũ.

### 14.6. Test backfill và resume

Kiểm tra:

- Chạy backfill nhiều lần không làm sai dữ liệu.
- Job có thể tiếp tục sau checkpoint.
- Hàng được cập nhật đồng thời không bị backfill ghi đè sai.
- Batch lỗi không làm checkpoint vượt qua dữ liệu chưa commit.
- Tốc độ backfill không làm pool hoặc database quá tải.

### 14.7. Test trên database mục tiêu

Dùng Testcontainers hoặc môi trường integration phù hợp với database production. H2 không thay thế được test lock, DDL, data type, generated values và transaction semantics của hệ quản trị thật.

## 15. Ví dụ pipeline phát hành

Một release thay `full_name` bằng `display_name` có thể được chia như sau:

| Giai đoạn | Database | Ứng dụng | Điều kiện chuyển tiếp |
|---|---|---|---|
| Release A | Thêm `display_name` nullable | v1 tiếp tục dùng `full_name` | Migration thành công, v1 vẫn healthy |
| Release B | Giữ cả hai cột | v2 đọc cũ/mới và dual-write | Tất cả instance/worker v2 đã rollout |
| Backfill | Copy dữ liệu cũ sang mới | Backfill job chạy batch | Không còn null/mismatch theo quy tắc |
| Release C | Giữ cả hai cột | v3 đọc mới, vẫn dual-write | Metrics/query xác nhận read path mới ổn định |
| Release D | Giữ cột cũ tạm thời | v4 chỉ ghi mới | Không còn rollback về code cần cột cũ |
| Release E | Drop cột cũ | v5 chỉ dùng cột mới | Không consumer nào còn tham chiếu cột cũ |

Tên release chỉ minh họa. Có thể gộp hoặc tách giai đoạn tùy mức độ rủi ro, nhưng không bỏ qua khoảng tương thích khi các phiên bản cùng hoạt động.

## 16. Theo dõi sau migration và rollout

Trong và sau release, cần quan sát cả application lẫn database:

- Tỷ lệ lỗi query và exception mapping.
- Các lỗi “column/table does not exist” hoặc lỗi conversion.
- p95/p99 query latency và HTTP latency.
- Connection pool active, idle, pending và acquire timeout.
- Lock wait, deadlock, long-running transaction.
- Replication lag, WAL/redo log và disk usage.
- Số hàng còn null hoặc chưa backfill.
- Chênh lệch giữa cột cũ và mới trong giai đoạn dual-write.
- Tỷ lệ request dùng feature flag mới.
- Log từ migration runner và schema version hiện tại.

Tạo cảnh báo cho điều kiện có thể làm rollout không an toàn. Không chỉ nhìn vào việc deployment tool báo tất cả pod đã Ready; query có thể lỗi chỉ khi một endpoint hiếm được gọi.

### 16.1. Theo dõi query cũ

Trước contract, cần bằng chứng rằng không còn query dùng cột cũ. Có thể dùng query logs, database statement statistics, tracing, application metrics hoặc tìm kiếm trong tất cả repository/job/report. Cần lưu ý prepared statement hoặc worker chạy dài có thể còn tồn tại qua thời điểm rollout; xác nhận chúng đã được drain hoặc reconnect theo chính sách.

### 16.2. Xác minh dữ liệu trước khi contract

Đừng chỉ kiểm tra số hàng đã backfill. So sánh dữ liệu theo quy tắc domain:

- Tổng số bản ghi.
- Số bản ghi null ở cột mới.
- Số giá trị khác nhau giữa cột cũ và cột mới.
- Các trường hợp conversion bị mất thông tin.
- Các ràng buộc uniqueness/foreign key/check cần áp dụng.

Với dữ liệu nhạy cảm hoặc khối lượng lớn, dùng truy vấn kiểm tra theo batch hoặc checksum phù hợp, tránh tạo một query quét nặng trong giờ cao điểm.

## 17. R2DBC-specific considerations

R2DBC không làm thay đổi nguyên tắc expand-and-contract, nhưng có một số điểm cần quan tâm ở runtime reactive.

### 17.1. Entity mapping phải tương thích với schema đang có

Spring Data R2DBC sử dụng metadata entity để tạo select/insert/update. Nếu thêm property vào entity trước khi cột tồn tại, query sinh ra có thể tham chiếu cột chưa được tạo. Nếu drop cột trước khi loại property khỏi entity, query cũng có thể lỗi.

Vì vậy, thứ tự an toàn thường là:

1. Thêm cột ở database.
2. Sau đó mới deploy entity mapping có property mới.
3. Chuyển read/write path.
4. Xóa property khỏi code trước khi drop cột ở database.

Nếu property được ánh xạ bằng `@ReadOnlyProperty`, `@Transient` hoặc projection tùy chỉnh, hãy kiểm tra SQL thực tế; annotation không tự làm cho cột chưa tồn tại trở nên an toàn.

### 17.2. Custom query cần được cập nhật theo từng bước

Repository `@Query`, `DatabaseClient` và custom repository có thể tham chiếu tên cột trực tiếp. Tìm kiếm source code không đủ nếu còn query được lưu trong view, stored function, reporting tool hoặc job bên ngoài. Hãy lập danh sách query consumer trước khi contract.

### 17.3. Reactive backfill cần kiểm soát concurrency

Backfill qua R2DBC có thể dùng `Flux` để xử lý batch, nhưng không nên phát hàng nghìn update song song. Dùng `concatMap` hoặc `flatMap` với concurrency hữu hạn, chia transaction theo batch và theo dõi pool. Mỗi batch nên commit nhanh và có thể retry an toàn.

### 17.4. Transaction reactive và migration DDL

Migration tool có thể dùng JDBC trong khi ứng dụng runtime dùng R2DBC. Không giả định transaction của migration và transaction ứng dụng là cùng một transaction hoặc cùng connection. Deployment orchestration phải bảo đảm migration hoàn tất trước khi code phụ thuộc schema nhận traffic.

### 17.5. Connection pool và schema change

Sau DDL, connection đã mở thường tiếp tục được sử dụng, nhưng hành vi prepared statement cache, server-side plan và metadata cache phụ thuộc driver/database. Nếu schema change làm query cũ hoặc prepared statement không còn hợp lệ, cần theo dõi lỗi và xác nhận driver xử lý plan invalidation. Không restart mọi instance chỉ để che lỗi schema; hãy hiểu cơ chế và triển khai theo kế hoạch.

## 18. Những lỗi thường gặp

### Đổi tên hoặc drop cột trong cùng release đầu tiên

Instance cũ có thể vẫn query cột cũ trong rolling deployment. Tách thành expand, chuyển code và contract.

### Deploy code mới trước khi schema được mở rộng

Entity/query mới tham chiếu cột chưa tồn tại. Chạy expand migration trước khi rollout code phụ thuộc cột.

### Thêm NOT NULL khi dữ liệu cũ chưa được backfill

Migration có thể thất bại hoặc khóa bảng. Thêm nullable, backfill, xác minh rồi mới thêm constraint.

### Backfill một transaction quá lớn

Có thể giữ lock lâu, tăng log, ảnh hưởng replication và làm chậm production. Chia batch, checkpoint và điều tiết tải.

### Dual-write nhưng không xử lý concurrent update

Backfill có thể ghi đè dữ liệu mới nếu không có predicate hoặc quy tắc đồng bộ. Thiết kế idempotent và xác định nguồn dữ liệu chính.

### Chạy migration từ mọi replica startup

Nhiều instance có thể tranh lock hoặc tạo trạng thái khó quan sát. Ưu tiên migration job có điều phối rõ hoặc xác nhận lock semantics của công cụ.

### Contract ngay sau khi pod mới Ready

Worker, consumer, batch hoặc phiên bản cũ có thể còn chạy. Xác nhận tất cả consumer đã drain và rollback window đã kết thúc.

### Dùng down migration để rollback dữ liệu đã chuyển

Down migration có thể mất dữ liệu hoặc không đảo ngược được. Ưu tiên forward fix; chỉ rollback schema khi đã hiểu tác động và có kế hoạch phục hồi.

### Không kiểm tra lock behavior của DDL

Migration tương thích vẫn có thể khóa bảng hoặc tạo tải lớn. Kiểm tra tài liệu database, thử trên dữ liệu đại diện và đặt timeout phù hợp.

### Giả định mọi migration chạy trong transaction

DDL transaction semantics khác nhau giữa database và từng câu lệnh. Xác nhận migration tool có hỗ trợ transaction cho migration đó.

### Không kiểm thử code cũ trên schema mở rộng

Code mới pass không chứng minh instance cũ vẫn hoạt động. Thêm compatibility test cho binary cũ nếu rolling deployment yêu cầu.

## 19. Quy trình phối hợp schema và release

1. Liệt kê mọi consumer của bảng/cột bị thay đổi, gồm HTTP instance, worker và hệ thống ngoài.
2. Phân loại thay đổi là additive hay breaking; đánh giá DDL lock, rewrite và khả năng mất dữ liệu.
3. Thiết kế expand schema sao cho phiên bản đang chạy tiếp tục hoạt động.
4. Tạo migration có version, có thể quan sát và có quy tắc transaction/lock phù hợp database.
5. Chạy migration trong CI trên database rỗng và schema phiên bản trước.
6. Triển khai expand migration bằng một migration runner có điều phối.
7. Deploy code tương thích với cả schema cũ và mới.
8. Chạy backfill theo batch, idempotent, có checkpoint và concurrency giới hạn.
9. Xác minh số hàng, null, mismatch và constraint trước khi chuyển read path.
10. Bật feature flag hoặc chuyển traffic dần nếu thay đổi có rủi ro.
11. Theo dõi lỗi, latency, pool, lock và dữ liệu trong rollback window.
12. Drain toàn bộ instance, worker và consumer cũ.
13. Ngừng dual-write và xác nhận không còn query tham chiếu cấu trúc cũ.
14. Chạy contract migration trong release riêng.
15. Cập nhật entity, query, migration history và tài liệu vận hành; giữ forward recovery plan.

## 20. Checklist trước khi phát hành

- [ ] Đã xác định mọi ứng dụng/job/worker đang sử dụng schema bị thay đổi.
- [ ] Đã đánh giá tương thích của schema với phiên bản ứng dụng cũ và mới.
- [ ] Migration expand không drop/rename cấu trúc cũ trong lúc consumer còn dùng.
- [ ] DDL đã được đánh giá lock, rewrite, transaction và tác động replication.
- [ ] Migration được chạy bởi runner có điều phối và có log/exit status rõ.
- [ ] Quyền DDL và quyền runtime được phân tách phù hợp.
- [ ] Code mới xử lý null/giá trị chưa backfill trong giai đoạn chuyển tiếp.
- [ ] Dual-write hoặc compatibility logic có quy tắc rõ và có test.
- [ ] Backfill idempotent, theo batch, có checkpoint và giới hạn concurrency.
- [ ] Có cách xác minh dữ liệu trước khi switch read path.
- [ ] Feature flag có owner và kế hoạch loại bỏ nếu được sử dụng.
- [ ] CI test migration từ database rỗng và từ schema trước.
- [ ] Có test code cũ trên expanded schema và code mới trên schema tương ứng.
- [ ] Readiness/rollout chỉ cho traffic vào sau khi schema cần thiết sẵn sàng.
- [ ] Rollback window và điều kiện contract được xác định.
- [ ] Backup/restore hoặc forward-fix strategy phù hợp với mức rủi ro.
- [ ] Không còn consumer tham chiếu cột/bảng sắp bị xóa.
- [ ] Contract migration nằm trong release riêng sau khi consumer cũ được drain.

Phối hợp schema với continuous release là bài toán tương thích theo thời gian, không chỉ là thứ tự chạy một file SQL. Khi dùng expand-and-contract, giữ schema cũ và mới cùng tồn tại đủ lâu, backfill theo batch, xác minh dữ liệu, chuyển code rồi mới contract, ứng dụng Spring Data R2DBC có thể tiếp tục phục vụ traffic trong rolling deployment. Migration cần được điều phối riêng, kiểm thử trên database thật và theo dõi về lock, latency, pool cùng dữ liệu để release có thể tiến lên hoặc phục hồi theo một kế hoạch rõ ràng.
