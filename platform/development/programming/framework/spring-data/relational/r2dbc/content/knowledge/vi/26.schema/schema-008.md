# Thay đổi schema tương thích khi nhiều phiên bản ứng dụng cùng chạy

Trong hệ thống Spring Data Relational R2DBC, việc triển khai ứng dụng thường không diễn ra đồng thời trên tất cả instance. Khi rolling deployment, blue-green deployment hoặc autoscaling, phiên bản cũ và phiên bản mới có thể cùng truy cập một database trong một khoảng thời gian. Vì vậy, một migration schema phải tương thích với cả hai phiên bản trong suốt giai đoạn chuyển tiếp.

Ví dụ, phiên bản cũ đọc và ghi cột `full_name`, trong khi phiên bản mới muốn chuyển sang `display_name`. Nếu migration đổi tên cột ngay lập tức, instance cũ vẫn đang chạy sẽ phát sinh lỗi SQL. Nếu xóa cột cũ trước khi mọi instance mới chuyển sang dùng cột mới, một request đang chạy hoặc một worker cũ có thể thất bại.

Chiến lược phổ biến là **expand-contract**: mở rộng schema theo cách tương thích ngược, triển khai code có thể hoạt động với schema chuyển tiếp, di chuyển dữ liệu và traffic, rồi mới thu hẹp schema sau khi chắc chắn không còn consumer cũ. Mục tiêu là để mỗi bước triển khai đều có một trạng thái database mà tất cả phiên bản ứng dụng đang hoạt động đều hiểu được.

## 1. Vì sao nhiều phiên bản cùng chạy làm migration khó hơn?

Một triển khai rolling thường có trình tự như sau:

```text
Thời điểm T0: chỉ có application v1
    |
    v
T1: bắt đầu triển khai v2
    |  v1 và v2 cùng chạy
    |
    v
T2: một phần instance đã là v2, phần còn lại là v1
    |  cả hai cùng đọc/ghi database
    |
    v
T3: toàn bộ instance web đã là v2
    |  worker, consumer, scheduled job có thể vẫn là v1
    |
    v
T4: mọi consumer cũ đã được thay thế hoặc dừng
    |
    v
T5: có thể loại bỏ schema cũ sau khi xác nhận an toàn
```

Trong giai đoạn T1–T3, database có thể nhận các câu SQL từ nhiều phiên bản code:

- Code cũ có thể INSERT mà không biết cột mới tồn tại.
- Code mới có thể đọc cột mới trong khi dữ liệu cũ chưa được backfill.
- Code cũ có thể tiếp tục ghi cột cũ sau khi code mới đã ghi cột mới.
- Một worker cũ chạy lâu có thể ghi dữ liệu sau khi web instance đã được nâng cấp.
- Một transaction bắt đầu trước khi deploy có thể hoàn tất sau khi migration hoặc traffic switch diễn ra.
- Một consumer message có thể dùng schema hoặc payload cũ lâu hơn vòng đời HTTP request.

Do đó, “đã deploy xong v2” không nhất thiết có nghĩa là mọi code cũ đã ngừng truy cập database. Cần kiểm kê cả web instance, background worker, scheduler, consumer, batch job, script quản trị và các ứng dụng khác dùng chung schema.

## 2. Nguyên tắc expand-contract

Expand-contract chia một thay đổi phá vỡ tương thích thành các bước nhỏ, trong đó mỗi bước giữ schema và code tương thích với phiên bản đang chạy.

<text weight="semibold">Giai đoạn Expand</text>

- Thêm cột, bảng, index hoặc cấu trúc mới theo cách code cũ vẫn hoạt động.
- Triển khai code mới có khả năng đọc/ghi schema cũ và mới trong thời gian chuyển tiếp.
- Backfill dữ liệu cũ sang cấu trúc mới theo batch.
- Chuyển việc đọc và ghi sang cấu trúc mới sau khi dữ liệu đã sẵn sàng.

<text weight="semibold">Giai đoạn Contract</text>

- Xác nhận không còn instance, worker hoặc job nào cần cấu trúc cũ.
- Ngừng ghi cấu trúc cũ và quan sát trong một khoảng thời gian phù hợp.
- Xóa cột/bảng/index cũ hoặc siết constraint khi đã an toàn.

Ví dụ đổi `full_name` thành `display_name`:

```text
Schema ban đầu
  customer.full_name
        |
        v
EXPAND: thêm customer.display_name (nullable)
  full_name       display_name
  v1 đọc/ghi      v2 có thể ghi cả hai
        |
        v
BACKFILL: copy full_name -> display_name
        |
        v
SWITCH: v2 đọc display_name, tiếp tục dual-write tạm thời
        |
        v
DRAIN: dừng toàn bộ v1 và các consumer còn dùng full_name
        |
        v
CONTRACT: ngừng ghi rồi xóa full_name
```

Điểm quan trọng là không gộp “thêm cấu trúc mới” và “xóa cấu trúc cũ” vào cùng một migration trước khi code đã chuyển hoàn toàn.

## 3. Tương thích schema giữa phiên bản cũ và mới

Một thay đổi chỉ an toàn khi code đang chạy có thể tiếp tục thực hiện các thao tác cần thiết trên schema sau migration. Có thể dùng ma trận sau để đánh giá:

| Trạng thái schema | Application v1 | Application v2 |
|---|---|---|
| Schema cũ | Hoạt động bình thường | Có thể chưa chạy được nếu v2 yêu cầu cột mới |
| Schema đã expand, giữ cột cũ và thêm cột mới | Phải tiếp tục hoạt động | Phải hoạt động với dữ liệu mới/cũ |
| Schema đang dual-write/backfill | Được phép ghi cấu trúc cũ | Đọc/ghi theo chiến lược chuyển tiếp |
| Schema đã contract, bỏ cột cũ | Không còn tương thích | Hoạt động theo schema mới |

Vì vậy, trình tự triển khai thường là migration expand trước, sau đó mới deploy application v2. Migration expand không được yêu cầu v1 phải biết cột mới. Bước contract chỉ được thực hiện sau khi v1 không còn được phép chạy.

### 3.1. Tương thích ngược và tương thích xuôi

- **Tương thích ngược:** code mới có thể hoạt động với schema cũ hoặc dữ liệu cũ trong giai đoạn chuyển tiếp.
- **Tương thích xuôi:** code cũ vẫn hoạt động khi schema đã được mở rộng bởi migration mới.

Trong rolling deployment, tương thích xuôi của schema expand thường đặc biệt quan trọng vì code cũ vẫn còn chạy. Code mới cũng cần có khả năng xử lý hàng cũ chưa được backfill.

Không phải thay đổi nào cũng cần cả hai hướng trong mọi thời điểm, nhưng cần biết rõ phiên bản nào đang truy cập schema nào trước khi triển khai.

## 4. Thêm cột mới một cách an toàn

Giả sử cần thêm `display_name` vào bảng `customer`, trong khi phiên bản cũ chỉ biết `name`.

Migration expand có thể thêm cột nullable:

```sql
ALTER TABLE customer
ADD COLUMN display_name VARCHAR(200);
```

Việc thêm cột nullable thường ít gây ảnh hưởng đến code cũ vì các câu INSERT không chỉ định cột mới vẫn có thể chạy và cột mới nhận NULL. Tuy nhiên, mức độ khóa, thời gian DDL và tác động vật lý phụ thuộc database, phiên bản và kích thước bảng. Cần kiểm tra tài liệu của hệ quản trị mục tiêu.

Code mới cần xử lý dữ liệu chưa có `display_name`:

```java
public String effectiveDisplayName(Customer customer) {
    if (customer.getDisplayName() != null) {
        return customer.getDisplayName();
    }

    return customer.getName();
}
```

Trong giai đoạn chuyển tiếp, có thể đọc cột mới nếu có giá trị, nếu không thì fallback về cột cũ. Sau khi backfill hoàn tất và mọi writer đã ghi cột mới, code có thể ngừng fallback.

### 4.1. Cẩn thận với DEFAULT và INSERT của phiên bản cũ

Có thể thêm cột với default:

```sql
ALTER TABLE customer
ADD COLUMN active BOOLEAN DEFAULT TRUE;
```

Nhưng cần phân biệt:

- Cột không xuất hiện trong danh sách INSERT: database có thể áp dụng default.
- INSERT gửi rõ `active = NULL`: default thông thường không thay thế explicit NULL.
- ORM có thể sinh SQL bao gồm cột mới với giá trị null hoặc không bao gồm cột tùy mapping và cấu hình.

Vì vậy, không giả định thêm default sẽ tự động xử lý mọi INSERT từ code cũ hoặc mới. Hãy kiểm tra SQL thực tế của Spring Data R2DBC, mapping entity và hành vi database.

### 4.2. Không thêm NOT NULL ngay nếu dữ liệu cũ chưa có giá trị

Migration sau có thể thất bại nếu bảng đã có hàng và cột mới không có giá trị mặc định hợp lệ:

```sql
ALTER TABLE customer
ADD COLUMN display_name VARCHAR(200) NOT NULL;
```

Trình tự an toàn hơn:

1. Thêm cột nullable.
2. Deploy code có thể ghi cột mới và đọc fallback.
3. Backfill tất cả hàng cũ.
4. Kiểm tra không còn NULL và xác nhận mọi writer đã ghi cột mới.
5. Thêm `NOT NULL` trong migration riêng.

Ví dụ kiểm tra dữ liệu trước khi siết constraint:

```sql
SELECT COUNT(*)
FROM customer
WHERE display_name IS NULL;
```

Chỉ tiếp tục khi kết quả và quy tắc nghiệp vụ đã được xác nhận. Với bảng lớn, việc thêm constraint có thể cần chiến lược riêng để tránh khóa kéo dài.

## 5. Đổi tên cột bằng hai cột tạm thời

Đổi tên trực tiếp thường là thay đổi phá vỡ tương thích:

```sql
ALTER TABLE customer RENAME COLUMN name TO display_name;
```

Sau câu lệnh này, phiên bản cũ vẫn truy vấn `name` sẽ lỗi. Dùng expand-contract:

### Bước 1: thêm cột mới

```sql
ALTER TABLE customer
ADD COLUMN display_name VARCHAR(200);
```

Code v1 tiếp tục đọc/ghi `name` như trước.

### Bước 2: triển khai code tương thích chuyển tiếp

Code v2 có thể ghi cả hai cột trong một khoảng thời gian:

```java
Mono<Customer> renameCustomer(Long id, String newName) {
    return databaseClient.sql("""
            UPDATE customer
            SET name = :name,
                display_name = :displayName
            WHERE id = :id
            """)
        .bind("name", newName)
        .bind("displayName", newName)
        .bind("id", id)
        .fetch()
        .rowsUpdated()
        .then(customerRepository.findById(id));
}
```

Ví dụ dùng SQL tường minh để minh họa dual-write. Trong code thực tế, cần xử lý trường hợp `rowsUpdated()` bằng 0, mapping cột, transaction và các thao tác ghi khác để bảo đảm hai cột luôn nhất quán.

### Bước 3: backfill dữ liệu cũ

```sql
UPDATE customer
SET display_name = name
WHERE display_name IS NULL;
```

Với bảng lớn, không chạy một UPDATE khổng lồ nếu nó tạo transaction, lock hoặc log quá lớn. Chia theo khoảng ID hoặc batch có checkpoint; chi tiết ở phần backfill.

### Bước 4: chuyển đọc sang cột mới

Sau khi dữ liệu đã được backfill và dual-write ổn định, v2 đọc `display_name`. Trong giai đoạn v1 còn chạy, v2 vẫn có thể cần tiếp tục ghi `name` để v1 đọc được các giá trị mới.

### Bước 5: dừng code cũ và contract

Chỉ sau khi mọi v1 instance, worker, consumer và job đã được dừng hoặc nâng cấp, ngừng ghi `name`. Quan sát thêm trong khoảng thời gian phù hợp rồi mới xóa:

```sql
ALTER TABLE customer DROP COLUMN name;
```

Xóa cột là bước phá vỡ tương thích và thường khó rollback nếu dữ liệu cũ không còn được giữ ở nơi khác. Thực hiện trong release riêng.

## 6. Dual-read và dual-write cần có quy tắc rõ ràng

Trong thời gian chuyển tiếp, ứng dụng có thể phải đọc và ghi hai biểu diễn.

### 6.1. Dual-read

Code mới đọc cột mới trước, fallback sang cột cũ:

```java
String displayName = customer.getDisplayName() != null
    ? customer.getDisplayName()
    : customer.getName();
```

Điều này hỗ trợ dữ liệu cũ chưa backfill. Tuy nhiên, fallback có thể che giấu việc backfill chưa hoàn tất. Hãy đo số hàng còn fallback và đặt điều kiện dừng rõ ràng.

### 6.2. Dual-write

Code mới ghi cùng một giá trị vào cả cột mới và cột cũ:

```sql
UPDATE customer
SET name = :value,
    display_name = :value
WHERE id = :id;
```

Hai cột nên được cập nhật trong cùng statement hoặc transaction để tránh trạng thái chỉ một cột được ghi. Nếu có nhiều writer, tất cả writer cần tuân thủ chiến lược hoặc phải có cơ chế đồng bộ khác.

### 6.3. Tránh hai nguồn dữ liệu cùng là nguồn sự thật

Dual-write chỉ là cầu nối trong giai đoạn chuyển đổi. Cần chỉ định cột nào là nguồn sự thật ở từng giai đoạn và ai được phép ghi.

Nếu v1 chỉ ghi `name`, v2 chỉ ghi `display_name`, hai cột có thể lệch nhau. Nếu v2 ghi cả hai nhưng một worker cũ tiếp tục ghi `name`, giá trị mới ở `display_name` có thể không còn phản ánh `name`. Hãy giữ dual-write ở mọi writer có thể thay đổi dữ liệu hoặc ngăn writer cũ trước khi chuyển nguồn sự thật.

Với thay đổi phức tạp, có thể dùng trigger database để đồng bộ tạm thời, nhưng trigger tạo thêm logic ẩn và phụ thuộc dialect. Nếu dùng, phải ghi nhận rõ thời điểm bật/tắt, kiểm thử với mọi writer và loại bỏ trigger sau contract.

## 7. Thay đổi kiểu dữ liệu

Thay đổi kiểu cột trực tiếp có thể làm code cũ không đọc được hoặc khiến database phải chuyển đổi dữ liệu trong một thao tác khóa dài.

Ví dụ chuyển `customer_code` từ số sang chuỗi để hỗ trợ tiền tố:

```sql
ALTER TABLE customer
ALTER COLUMN customer_code TYPE VARCHAR(40);
```

Đây là cú pháp phụ thuộc database và có thể gây rewrite/lock. Với thay đổi có nguy cơ không tương thích, hãy dùng cột mới:

```sql
ALTER TABLE customer
ADD COLUMN customer_code_v2 VARCHAR(40);
```

Trình tự:

1. Thêm cột mới với kiểu đích.
2. Deploy code có thể ghi cả kiểu cũ và mới.
3. Backfill bằng phép chuyển đổi đã xác định.
4. Kiểm tra các giá trị không chuyển đổi được, tràn số, mất độ chính xác hoặc thay đổi định dạng.
5. Chuyển đọc sang cột mới.
6. Dừng writer cũ và ngừng ghi cột cũ.
7. Contract bằng cách xóa cột cũ ở release sau.

Không dùng ép kiểu đơn giản nếu chuyển đổi có thể mất dữ liệu. Hãy xác định cách xử lý giá trị không hợp lệ và có báo cáo số hàng chuyển đổi thất bại.

### 7.1. Thay đổi precision/scale của số

Chuyển `DECIMAL(10,2)` sang `DECIMAL(18,4)` có thể làm thay đổi quy tắc làm tròn và cách Java `BigDecimal` được dùng. Kiểm tra:

- Dữ liệu cũ có thể biểu diễn chính xác trong kiểu mới không.
- Code cũ có giả định scale cố định không.
- Code mới có đọc được giá trị được ghi bởi code cũ không.
- Các phép tính, so sánh và báo cáo có dùng cùng rounding mode không.

### 7.2. Thay đổi thời gian và timezone

Chuyển giữa timestamp không timezone, timestamp có timezone hoặc epoch number có thể làm thay đổi cách diễn giải thời điểm. Hãy thống nhất quy ước UTC, mapping Java (`Instant`, `OffsetDateTime`, `LocalDateTime`) và semantics database trước khi migration.

Không chỉ đổi kiểu cột mà không kiểm tra dữ liệu thực tế và timezone của session/driver.

## 8. Thêm giá trị enum hoặc trạng thái mới

Thay đổi enum thường bị xem nhẹ vì không cần đổi nhiều cột. Nhưng code cũ có thể không parse được giá trị mới.

Giả sử database có trạng thái `PENDING`, `PAID`, `CANCELLED`; phiên bản mới thêm `REFUNDING`.

Nếu v2 ghi `REFUNDING` trong khi v1 vẫn đọc cùng bảng và dùng:

```java
OrderStatus.valueOf(row.get("status", String.class));
```

v1 có thể ném `IllegalArgumentException` khi gặp giá trị chưa biết.

Trình tự an toàn:

1. Triển khai code đọc có khả năng xử lý giá trị chưa biết, ví dụ trạng thái `UNKNOWN` hoặc fallback có kiểm soát.
2. Chờ tất cả reader cũ đã được nâng cấp.
3. Bắt đầu ghi giá trị enum mới.
4. Theo dõi các reader và consumer có thể nhận giá trị mới.

Với enum native của database, thêm enum value có cú pháp và giới hạn riêng theo hệ quản trị. Với cột `VARCHAR`, việc thêm giá trị thường không cần DDL nhưng vẫn là thay đổi hợp đồng dữ liệu giữa các phiên bản code.

Không chỉ kiểm tra ứng dụng web. Message consumer, reporting job và batch export cũng có thể deserialize enum.

## 9. Thêm constraint theo từng giai đoạn

Constraint mới có thể làm code cũ không ghi được dữ liệu. Ví dụ thêm `NOT NULL`, `CHECK`, foreign key hoặc unique constraint trong khi các writer cũ chưa đáp ứng quy tắc.

Trình tự chung:

1. Đưa code mới có khả năng ghi dữ liệu thỏa constraint.
2. Backfill hoặc sửa dữ liệu hiện có.
3. Kiểm tra không còn hàng vi phạm.
4. Thêm constraint hoặc validate constraint đã tạo trước đó.
5. Theo dõi lỗi ghi sau khi constraint được bật.

### 9.1. PostgreSQL: NOT VALID và VALIDATE CONSTRAINT

PostgreSQL hỗ trợ tạo một số constraint như foreign key hoặc check ở trạng thái `NOT VALID`, sau đó validate dữ liệu hiện có bằng lệnh riêng:

```sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customer(id)
NOT VALID;

ALTER TABLE orders
VALIDATE CONSTRAINT fk_orders_customer;
```

Constraint `NOT VALID` vẫn được áp dụng cho dữ liệu mới/được cập nhật theo semantics của PostgreSQL, trong khi việc kiểm tra toàn bộ dữ liệu cũ được tách riêng. Cú pháp này không portable; hãy dùng đúng chiến lược của database mục tiêu.

### 9.2. Unique constraint cần xử lý duplicate trước

Trước khi tạo unique index/constraint, tìm dữ liệu trùng:

```sql
SELECT email, COUNT(*)
FROM customer
GROUP BY email
HAVING COUNT(*) > 1;
```

Nếu có duplicate, phải xử lý theo nghiệp vụ trước. Với bảng lớn, PostgreSQL hỗ trợ tạo unique index concurrently, nhưng quá trình có thể thất bại nếu có duplicate mới phát sinh trong lúc tạo. Cần có kế hoạch kiểm tra và xử lý trạng thái index sau migration.

## 10. Thêm index mà không làm gián đoạn ghi

Index mới có thể cần thiết trước khi triển khai code sử dụng truy vấn mới. Tuy nhiên, việc tạo index trên bảng lớn có thể chiếm tài nguyên, chặn ghi hoặc kéo dài migration tùy database.

Ví dụ PostgreSQL:

```sql
CREATE INDEX CONCURRENTLY idx_orders_customer_created
ON orders(customer_id, created_at DESC);
```

`CONCURRENTLY` là cú pháp PostgreSQL và có ràng buộc riêng, ví dụ không chạy bên trong transaction block thông thường. Migration tool phải được cấu hình phù hợp nếu dùng câu lệnh này. Database khác có thể có tùy chọn online index creation hoặc cơ chế khác.

Một quy trình triển khai index:

1. Xác định query plan và lý do cần index.
2. Kiểm tra kích thước bảng, dung lượng và tải I/O.
3. Tạo index theo cơ chế ít blocking mà database hỗ trợ.
4. Xác nhận index hợp lệ và optimizer sử dụng khi phù hợp.
5. Sau đó mới triển khai code phụ thuộc hiệu năng của index.

Index có thể thêm trước code mới nếu nó không thay đổi semantics truy vấn cũ. Không xóa index cũ ngay khi code mới được deploy; hãy quan sát query workload và xác nhận không còn truy vấn cần nó.

## 11. Backfill dữ liệu lớn theo batch

Backfill là quá trình điền dữ liệu cho cột mới hoặc chuyển dữ liệu sang cấu trúc mới. Với bảng nhỏ, một UPDATE có thể đủ. Với bảng lớn, một transaction khổng lồ có thể tạo lock, transaction log/WAL lớn, tăng replication lag và ảnh hưởng workload online.

Ví dụ SQL đơn giản:

```sql
UPDATE customer
SET display_name = name
WHERE display_name IS NULL;
```

Với bảng lớn, có thể chia theo khoảng ID:

```sql
UPDATE customer
SET display_name = name
WHERE id > :fromId
  AND id <= :toId
  AND display_name IS NULL;
```

Worker thực hiện nhiều batch nhỏ, mỗi batch commit riêng theo thiết kế. Cần lưu checkpoint hoặc xác định cursor để có thể tiếp tục sau khi process dừng.

### 11.1. Backfill idempotent

Một backfill nên có thể chạy lại mà không làm hỏng dữ liệu đã chuyển. Điều kiện:

```sql
WHERE display_name IS NULL
```

giúp chỉ điền các hàng chưa có giá trị. Tuy nhiên, nếu cột nguồn `name` có thể thay đổi trong khi backfill, cần quy tắc xác định giá trị nào thắng.

Các lựa chọn:

- Dual-write đảm bảo mọi thay đổi mới cập nhật cả hai cột trong cùng transaction.
- Backfill dùng version hoặc timestamp để không ghi đè giá trị mới hơn.
- Tạm ngăn thay đổi đối với một nhóm dữ liệu trong thời gian chuyển đổi nếu nghiệp vụ cho phép.
- Chạy reconciliation sau backfill để tìm các hàng lệch.

### 11.2. Dùng batch reactive có giới hạn

Có thể đọc một batch ID, cập nhật theo batch rồi chuyển sang batch tiếp theo. Ví dụ minh họa bằng R2dbcEntityTemplate:

```java
Flux<Long> backfillBatch(List<Long> ids) {
    if (ids.isEmpty()) {
        return Flux.empty();
    }

    Query query = Query.query(Criteria.where("id").in(ids)
        .and("displayName").isNull());

    Update update = Update.empty()
        .set("displayName", "<giá trị được tính theo từng hàng>");

    // Minh họa: nếu giá trị đích khác nhau theo từng hàng,
    // đọc và cập nhật theo từng entity hoặc dùng SQL batch phù hợp.
    return Flux.fromIterable(ids);
}
```

Đoạn code trên chỉ minh họa việc giới hạn batch; `Update.set` một giá trị chung không phù hợp nếu mỗi hàng cần copy giá trị riêng từ cột nguồn. Trong thực tế, có thể dùng SQL `UPDATE ... SET new_col = old_col` theo khoảng ID hoặc một câu lệnh database-specific để cập nhật theo hàng. Không tải toàn bộ bảng vào heap chỉ để backfill.

Với R2DBC, pipeline worker có thể dùng `buffer(batchSize)` và `concatMap` để giới hạn công việc đang chạy:

```java
sourceOfIdRanges
    .concatMap(this::backfillRange)
    .then();
```

Nếu cần concurrency, đặt giới hạn rõ ràng và đo tải database. Backfill nên có rate limit, timeout, checkpoint và khả năng pause/resume.

### 11.3. Theo dõi tiến độ và chất lượng dữ liệu

Theo dõi:

- Tổng số hàng dự kiến và số hàng đã xử lý.
- Số hàng còn NULL ở cột mới.
- Số hàng không chuyển đổi được.
- Số hàng có giá trị cũ/mới không khớp.
- Thời gian mỗi batch và số lần retry.
- Lock wait, I/O, CPU và replication lag.
- Tỷ lệ lỗi từ các request online trong khi backfill.

Không coi việc worker kết thúc không lỗi là bằng chứng dữ liệu đã chuyển đúng. Cần truy vấn đối soát và điều kiện hoàn tất rõ ràng.

## 12. Migration phải được điều phối riêng với rolling deployment

Không nên để mọi application instance tự chạy cùng một migration tùy tiện khi chúng khởi động đồng thời. Migration tool có thể có schema history và lock để tránh chạy lặp, nhưng cần hiểu cách nó phối hợp với nhiều instance và transaction.

Các lựa chọn phổ biến:

- Chạy Flyway hoặc Liquibase trong một deployment/job migration riêng trước khi rollout application.
- Chỉ định một migration runner duy nhất trong pipeline release.
- Nếu migration chạy lúc startup, xác nhận tool có lock và cấu hình phù hợp với nhiều instance, đồng thời bảo đảm DDL an toàn cho phiên bản cũ.

Spring Data R2DBC không bắt buộc phải dùng một migration tool cụ thể. Flyway thường dùng JDBC để quản lý migration trong nhiều cấu hình Spring Boot; nếu ứng dụng chỉ có R2DBC, có thể cần thêm JDBC driver/connection cho migration hoặc chọn công cụ hỗ trợ database/migration strategy phù hợp. Liquibase cũng có các cách chạy dựa trên JDBC hoặc tích hợp tùy phiên bản. Hãy phân biệt migration schema với data access runtime R2DBC.

### 12.1. Migration versioned và bất biến

Các migration đã áp dụng nên được xem là bất biến. Thay đổi migration đã chạy trên môi trường thật có thể làm lịch sử schema giữa các môi trường lệch nhau. Tạo migration mới cho bước tiếp theo thay vì sửa file cũ đã được áp dụng.

Ví dụ thứ tự migration:

```text
V101__add_display_name.sql
V102__backfill_display_name.sql       (nếu quy mô và cách chạy phù hợp)
V103__add_display_name_constraint.sql
V104__drop_legacy_name.sql            (sau giai đoạn contract)
```

Với backfill lớn, thường nên chạy worker/job riêng thay vì nhét một thao tác kéo dài vào migration startup. DDL và data migration có thể cần cơ chế retry, checkpoint và quan sát khác nhau.

### 12.2. Không để application mới phụ thuộc migration chưa hoàn tất

Nếu migration backfill là một job dài, code mới phải biết dữ liệu chưa hoàn chỉnh và xử lý fallback. Không rollout code đọc cột mới như thể mọi hàng đã có giá trị trước khi xác nhận backfill hoàn tất.

## 13. Thay đổi schema ảnh hưởng tới mapping Spring Data R2DBC

Spring Data Relational ánh xạ property entity sang cột theo metadata và annotation. Khi schema chuyển tiếp có cả cột cũ và mới, cần xác định entity version nào được dùng ở mỗi giai đoạn.

Ví dụ entity v2:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("name")
    private String legacyName;

    @Column("display_name")
    private String displayName;
}
```

Mapping này cho phép code v2 truy cập cả hai cột trong thời gian chuyển tiếp. Nếu entity v1 chỉ có `name`, việc thêm cột mới không làm nó tự động biết cột đó. Điều này thường ổn nếu cột mới nullable và câu INSERT cũ không bắt buộc phải cung cấp giá trị.

### 13.1. SELECT * có thể làm thay đổi mapping

Với raw SQL và DTO mapper, tránh phụ thuộc không cần thiết vào thứ tự cột hoặc số lượng cột:

```sql
SELECT id, name, display_name
FROM customer
WHERE id = :id;
```

Đặt danh sách cột và alias rõ ràng giúp mapper ổn định khi schema thêm cột. Với `SELECT *`, số cột có thể thay đổi sau migration; mapper dựa vào index hoặc giả định metadata cố định có thể gặp lỗi.

### 13.2. Insert/update SQL tùy chỉnh phải được cập nhật có chủ đích

Một câu INSERT liệt kê cột tường minh thường tương thích hơn khi thêm cột nullable:

```sql
INSERT INTO customer(name, email)
VALUES (:name, :email);
```

Code cũ tiếp tục chạy vì không chỉ định cột mới. Nếu cột mới có default, database có thể áp dụng default. Nếu cột mới được đặt NOT NULL mà không có default phù hợp, câu INSERT cũ sẽ lỗi.

Với code mới dual-write:

```sql
INSERT INTO customer(name, display_name, email)
VALUES (:name, :displayName, :email);
```

Hãy tìm tất cả raw SQL, stored procedure, view và batch job có thao tác trên bảng trước khi contract cột cũ.

## 14. Xử lý xóa cột và bảng an toàn

Drop column/table là bước contract có tính phá hủy. Trước khi thực hiện, cần xác nhận:

- Không còn instance ứng dụng nào đọc hoặc ghi cột/bảng.
- Không còn worker, scheduler, consumer hoặc script cũ.
- Không còn view, stored procedure, trigger, report hoặc ETL phụ thuộc.
- Không còn dashboard hoặc ad hoc query cần dữ liệu cũ.
- Backfill và reconciliation đã hoàn tất.
- Có backup/khả năng phục hồi theo chính sách.
- Đã qua khoảng thời gian quan sát đủ để phát hiện consumer chạy theo lịch dài.
- Có kế hoạch rollback ứng dụng và dữ liệu phù hợp.

Nếu chưa chắc, có thể ngừng ghi cột cũ trước, theo dõi query/audit/metrics, rồi mới drop trong release sau. Tách hành động ngừng sử dụng khỏi hành động xóa giúp có thời gian phát hiện dependency bị bỏ sót.

### 14.1. Không thể rollback ứng dụng cũ sau khi contract

Sau khi cột cũ bị xóa, rollback binary về phiên bản cũ có thể khiến ứng dụng lỗi ngay. Vì vậy, contract thường là bước cuối và chỉ được thực hiện sau khi:

- Khoảng rollback về phiên bản cũ đã kết thúc.
- Có bản release mới tương thích với schema hiện tại.
- Đã xác nhận mọi consumer cũ không còn cần cột.
- Có phương án phục hồi dữ liệu nếu cần.

Rollback ứng dụng và rollback schema là hai việc khác nhau. Một migration đã xóa cột không nhất thiết có thể rollback bằng một câu `ADD COLUMN`, vì dữ liệu cũ đã bị mất.

## 15. Rolling deployment và thứ tự release

Một release schema/app thường có thứ tự như sau:

| Bước | Schema | Application | Mục tiêu |
|---|---|---|---|
| 0 | Chỉ có cấu trúc cũ | v1 | Trạng thái ban đầu |
| 1 | Expand: thêm cột/bảng/index mới, giữ cấu trúc cũ | v1 | v1 vẫn chạy bình thường |
| 2 | Schema chuyển tiếp | v1 và v2 | v2 tương thích với v1 và dữ liệu cũ |
| 3 | Schema chuyển tiếp | v2, backfill chạy | Dữ liệu mới được đồng bộ |
| 4 | Schema chuyển tiếp | chỉ v2 và các worker đã nâng cấp | Chuyển đọc/ghi sang cấu trúc mới |
| 5 | Schema chuyển tiếp, cấu trúc cũ không còn được dùng | v2 | Quan sát, xác nhận không còn dependency |
| 6 | Contract: bỏ cấu trúc cũ/siết constraint | v2 | Hoàn tất thay đổi |

Nếu cần rollback ở bước 2 hoặc 3, v1 vẫn có thể chạy vì schema cũ còn tồn tại. Nếu rollback sau bước 6, v1 có thể không tương thích; phải triển khai một phiên bản sửa lỗi vẫn hiểu schema mới hoặc phục hồi schema/dữ liệu theo kế hoạch.

## 16. Thay đổi schema và message/event giữa các dịch vụ

Không chỉ database schema mới cần tương thích. Nếu ứng dụng phát event hoặc message chứa cấu trúc thay đổi, consumer cũ cũng có thể còn chạy.

Các nguyên tắc tương tự:

- Thêm field optional trước khi yêu cầu mọi producer gửi field đó.
- Consumer cũ phải bỏ qua field không biết nếu format hỗ trợ.
- Producer mới không phát enum/value mới trước khi consumer cũ có thể xử lý.
- Đổi tên field bằng cách thêm field mới, phát cả hai trong giai đoạn chuyển tiếp, rồi ngừng field cũ.
- Dùng schema registry/versioning nếu hệ thống có hợp đồng message được quản lý.

Một worker cũ có thể đọc message mới nhiều giờ sau khi deploy. Hãy xét retention, retry queue và dead-letter queue khi quyết định thời điểm contract.

## 17. Kiểm thử migration tương thích nhiều phiên bản

Kiểm thử migration chỉ chạy từ schema trống chưa đủ. Hãy xác nhận schema cũ, schema chuyển tiếp và schema sau contract đều được xử lý đúng theo giai đoạn.

Các kiểm thử nên có:

### 17.1. Migration từ phiên bản schema trước

- Khởi tạo database bằng migration hiện tại trước thay đổi.
- Nạp dữ liệu đại diện, bao gồm NULL, giá trị biên và dữ liệu lớn.
- Chạy migration expand.
- Xác nhận code cũ vẫn SELECT/INSERT/UPDATE được.
- Xác nhận code mới đọc được cả hàng đã backfill và hàng chưa backfill.

### 17.2. Kiểm thử coexistence v1/v2

- Chạy hai phiên bản code trên cùng database chuyển tiếp.
- Cho v1 ghi dữ liệu rồi xác nhận v2 đọc được.
- Cho v2 ghi trong giai đoạn dual-write rồi xác nhận v1 đọc được.
- Chạy cập nhật đồng thời và xác nhận hai biểu diễn không lệch.
- Kiểm tra enum/status mới chưa được ghi khi reader cũ chưa sẵn sàng.

### 17.3. Kiểm thử backfill và contract

- Backfill có thể chạy lại mà không tạo sai dữ liệu.
- Worker dừng giữa batch có thể resume từ checkpoint.
- Đối soát số hàng và giá trị cũ/mới.
- Contract chỉ chạy khi điều kiện dependency đã được xác nhận.
- Code v2 hoạt động sau khi cột cũ bị xóa.
- Migration failure không để schema ở trạng thái không thể nhận diện.

### 17.4. Kiểm thử tải và locking

- Đo thời gian DDL trên dữ liệu có kích thước gần production.
- Theo dõi lock wait và thời gian chặn request.
- Chạy backfill trong khi traffic đọc/ghi vẫn hoạt động.
- Xác nhận pool R2DBC và replication không bị quá tải.
- Kiểm tra rollback hoặc resume sau timeout/disconnect.

Không chỉ mock repository. Cần integration test với đúng database và R2DBC driver, vì DDL locking, default, unique/foreign key validation và SQL dialect phụ thuộc hệ quản trị.

## 18. Quan sát và điều kiện cho phép chuyển sang contract

Không nên xóa cấu trúc cũ chỉ dựa vào việc deploy pipeline báo thành công. Hãy đặt các điều kiện có thể đo được:

- Số instance theo phiên bản: không còn v1.
- Số worker/consumer theo phiên bản: không còn process cũ.
- Thời điểm cuối cùng cột cũ được ghi.
- Số hàng còn thiếu giá trị ở cột mới bằng 0 hoặc nằm trong ngoại lệ đã phê duyệt.
- Số hàng có giá trị cũ/mới không khớp bằng 0 hoặc đã được xử lý.
- Không còn truy vấn SQL hoặc metric truy cập cột cũ.
- Backfill đã hoàn tất và checkpoint được xác nhận.
- Tỷ lệ lỗi mapping/query không tăng.
- Đã qua ít nhất một chu kỳ của scheduled job/consumer dài hạn có liên quan.

Ví dụ truy vấn đối soát:

```sql
SELECT COUNT(*)
FROM customer
WHERE display_name IS NULL;
```

Và kiểm tra dữ liệu lệch:

```sql
SELECT COUNT(*)
FROM customer
WHERE display_name IS DISTINCT FROM name;
```

`IS DISTINCT FROM` là cú pháp PostgreSQL và một số database khác có thể không hỗ trợ. Hãy viết phép so sánh tương đương theo dialect mục tiêu, bao gồm xử lý NULL rõ ràng.

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Rename/drop cột ngay trong migration đầu tiên | Instance cũ lỗi khi tiếp tục chạy | Expand-contract qua nhiều release |
| Thêm cột NOT NULL khi hàng cũ chưa có giá trị | Migration hoặc INSERT từ code cũ thất bại | Thêm nullable, backfill, xác nhận rồi siết constraint |
| Giả định DEFAULT thay thế explicit NULL | Dữ liệu mới vẫn có thể là NULL | Kiểm tra SQL do ORM sinh và semantics database |
| Deploy code mới trước migration expand | Code mới truy vấn cột chưa tồn tại | Chạy migration expand trước rollout |
| Chỉ nâng cấp web instance, quên worker/consumer | Process cũ tiếp tục truy cập schema cũ | Kiểm kê mọi consumer và lịch chạy |
| Chuyển đọc sang cột mới trước backfill | Request trả dữ liệu thiếu | Fallback và chỉ switch khi dữ liệu đã sẵn sàng |
| Dual-write nhưng chỉ ở một writer | Worker cũ làm hai cột lệch nhau | Liệt kê mọi writer, đồng bộ hoặc dừng writer cũ |
| Backfill một transaction khổng lồ | Lock, WAL/log và replication lag tăng | Chia batch, checkpoint và rate limit |
| Backfill không idempotent | Retry có thể ghi đè dữ liệu mới | Thiết kế điều kiện update/version và reconciliation |
| Thêm enum mới trước khi reader cũ hiểu | Reader cũ lỗi parse | Nâng cấp reader trước, writer sau |
| Tạo index blocking trên bảng lớn | Request ghi bị chặn hoặc migration kéo dài | Dùng online/concurrent index theo database |
| Để mọi pod cùng chạy migration | Tranh chấp lock hoặc migration startup khó kiểm soát | Job migration riêng hoặc tool có coordination rõ |
| Sửa migration đã chạy | Schema history giữa môi trường lệch nhau | Tạo migration mới, giữ migration đã áp dụng bất biến |
| Contract ngay sau khi deploy v2 | Không còn thời gian rollback về v1 | Tách contract release sau khi hết rollback window |
| Chỉ test schema trống | Không phát hiện dữ liệu cũ và coexistence lỗi | Test upgrade từ schema/data trước đó và hai phiên bản |

## 20. Quy trình triển khai một thay đổi schema tương thích

Khi cần đổi bảng/cột trong môi trường nhiều instance, hãy thực hiện theo trình tự:

1. **Liệt kê consumer:** web instance, worker, scheduler, message consumer, script, report và ứng dụng khác.
2. **Xác định hợp đồng cũ/mới:** câu SQL, entity mapping, giá trị enum, nullability và constraint.
3. **Thiết kế trạng thái chuyển tiếp:** bảo đảm schema expand vẫn cho phép code cũ và mới cùng chạy.
4. **Chạy migration expand:** thêm cấu trúc mới theo cách additive; tránh drop/rename trực tiếp.
5. **Deploy code tương thích:** đọc fallback hoặc dual-write theo chiến lược rõ ràng.
6. **Backfill dữ liệu:** chạy theo batch, có checkpoint, idempotency và rate limit.
7. **Đối soát:** kiểm tra NULL, mismatch, số hàng và lỗi chuyển đổi.
8. **Switch traffic/read path:** chuyển code mới sang nguồn dữ liệu mới khi đã sẵn sàng.
9. **Drain consumer cũ:** chờ instance, worker, job và message cũ hoàn tất hoặc nâng cấp.
10. **Ngừng ghi cấu trúc cũ:** quan sát truy cập và xác nhận không còn dependency.
11. **Contract trong release riêng:** xóa cột/bảng/index cũ hoặc siết constraint.
12. **Kiểm thử và quan sát sau triển khai:** theo dõi query failure, lock, pool, backfill và data consistency.

## 21. Nguyên tắc cần nhớ

- Trong rolling deployment, nhiều phiên bản code có thể truy cập cùng schema cùng lúc.
- Migration phải tương thích với mọi writer/reader đang hoạt động, kể cả worker và consumer chạy lâu.
- Dùng expand-contract: thêm cấu trúc mới, triển khai code tương thích, backfill, chuyển traffic, rồi mới xóa cấu trúc cũ.
- Thêm cột nullable trước; backfill và xác nhận dữ liệu rồi mới thêm `NOT NULL`.
- Đừng giả định database default xử lý explicit NULL hoặc mọi SQL do ORM sinh.
- Đổi tên cột/kiểu dữ liệu bằng cột mới và dual-read/dual-write có thời hạn khi cần.
- Chỉ một nguồn sự thật được xác định ở từng giai đoạn; dual-write phải bao phủ mọi writer.
- Nâng cấp reader trước khi producer bắt đầu ghi enum hoặc trạng thái mới.
- Thêm constraint/index theo chiến lược phù hợp với database và kích thước bảng.
- Backfill theo batch hữu hạn, idempotent, có checkpoint, rate limit và reconciliation.
- Điều phối migration riêng hoặc dùng migration tool có lock/coordination rõ ràng.
- Giữ migration đã áp dụng bất biến; tạo migration mới cho thay đổi tiếp theo.
- Không contract trước khi mọi instance, worker, consumer và job cũ đã được drain.
- Contract thường là bước không thể rollback về binary cũ; hãy giữ khoảng quan sát và rollback window.
- Kiểm thử schema cũ, schema chuyển tiếp, coexistence nhiều phiên bản, backfill và schema sau contract trên database/driver mục tiêu.

Thay đổi schema an toàn trong môi trường nhiều phiên bản không chỉ là viết một câu DDL đúng cú pháp. Nó là quá trình phối hợp schema, code, dữ liệu và vòng đời của mọi consumer. Expand-contract giúp mỗi bước triển khai giữ được khả năng hoạt động của phiên bản đang chạy, còn backfill có kiểm soát, điều kiện contract đo được và migration được điều phối rõ ràng giúp tránh downtime và mất dữ liệu khi hệ thống tiếp tục phục vụ traffic.
