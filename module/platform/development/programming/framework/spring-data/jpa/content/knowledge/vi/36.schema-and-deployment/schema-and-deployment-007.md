# Backfill dữ liệu và chiến lược thay đổi schema nhiều bước

Khi một ứng dụng Spring Data JPA cần đổi cấu trúc bảng đang chứa dữ liệu lớn, việc sửa schema và triển khai code trong một lần có thể làm ứng dụng cũ không tương thích, khóa bảng lâu hoặc khiến dữ liệu mới và cũ không đồng nhất. Một cách an toàn hơn là chia thay đổi thành nhiều bước nhỏ, giữ cho các phiên bản ứng dụng đang chạy đồng thời vẫn đọc/ghi được dữ liệu trong giai đoạn chuyển tiếp.

Chiến lược thường dùng là **Expand – Migrate – Contract**:

1. **Expand:** mở rộng schema theo hướng tương thích ngược, thường bằng cách thêm cột/bảng mới mà chưa xóa cấu trúc cũ.
2. **Migrate:** triển khai code tương thích, backfill dữ liệu cũ theo từng lô, kiểm chứng dữ liệu và chuyển dần luồng đọc sang cấu trúc mới.
3. **Contract:** sau khi không còn code phụ thuộc schema cũ và đã hết thời gian rollback, loại bỏ cột/bảng cũ trong một lần triển khai riêng.

Backfill là quá trình chuyển đổi hoặc bổ sung dữ liệu đã tồn tại để đáp ứng schema/mô hình mới. Nó cần có thể chạy lại, theo dõi tiến độ, giới hạn tác động lên database và kiểm chứng được kết quả.

## 1. Vì sao cần thay đổi schema nhiều bước?

Giả sử bảng `orders` hiện có cột `customer_name`. Ứng dụng muốn đổi sang cột `customer_display_name` để thể hiện rõ mục đích và chuẩn hóa mô hình dữ liệu.

Nếu triển khai code mới chỉ đọc/ghi `customer_display_name` rồi đồng thời đổi tên hoặc xóa `customer_name`, các instance ứng dụng cũ trong quá trình rolling deployment có thể vẫn truy cập cột cũ và phát sinh lỗi SQL. Nếu backfill hàng triệu dòng trong cùng một migration transaction, thời gian khóa, log transaction, replication lag và khả năng rollback có thể trở thành vấn đề.

Thay đổi nhiều bước giải quyết các rủi ro này bằng cách duy trì một khoảng thời gian schema có thể phục vụ cả code cũ lẫn code mới.

Các mục tiêu chính:

- Phiên bản ứng dụng cũ vẫn hoạt động trong lúc phiên bản mới được triển khai.
- Dữ liệu mới được ghi theo quy tắc nhất quán trong giai đoạn chuyển tiếp.
- Dữ liệu cũ được chuyển đổi theo lô, có checkpoint và có thể retry.
- Có số liệu để xác nhận backfill đã hoàn tất và dữ liệu đúng.
- Việc xóa cấu trúc cũ chỉ diễn ra khi không còn consumer phụ thuộc.

## 2. Mô hình Expand – Migrate – Contract

| Giai đoạn | Schema | Ứng dụng | Dữ liệu |
|---|---|---|---|
| Trước thay đổi | Chỉ có cột cũ | Đọc/ghi cột cũ | Dữ liệu hiện hữu |
| Expand | Thêm cột mới, giữ cột cũ | Phiên bản cũ vẫn chạy | Cột mới có thể còn NULL |
| Migrate – tương thích | Giữ cả hai cột | Code mới ghi đồng thời hai cột, ban đầu vẫn đọc cột cũ | Backfill dữ liệu cũ theo lô |
| Migrate – chuyển đọc | Giữ cả hai cột | Code mới đọc cột mới, tiếp tục ghi cả hai trong thời gian rollback | Đối chiếu dữ liệu và theo dõi sai lệch |
| Contract | Sau cùng mới xóa cột cũ | Code không còn tham chiếu cột cũ | Schema chỉ còn cấu trúc mới |

Trình tự này có một điều kiện quan trọng: trước khi backfill hoàn tất, mọi writer đang hoạt động phải tuân theo quy tắc đồng bộ. Nếu một instance cũ chỉ ghi cột `customer_name` sau khi hàng đó đã được backfill, cột mới có thể trở nên lỗi thời. Có thể giải quyết bằng cách chờ tất cả writer cũ được thay thế, dùng dual-write trong ứng dụng, hoặc dùng trigger tạm thời nếu không thể nâng cấp tất cả writer cùng lúc.

## 3. Ví dụ thay đổi cột theo từng lần triển khai

### 3.1. Expand: thêm cột mới

Dùng migration có version để thêm cột nullable:

```sql
ALTER TABLE orders
ADD COLUMN customer_display_name VARCHAR(200);
```

Giữ nguyên `customer_name`. Chưa thêm `NOT NULL` nếu dữ liệu cũ chưa được backfill và chưa xác định cách xử lý giá trị thiếu.

Đây là ví dụ SQL minh họa; cú pháp, thời gian khóa và khả năng thực hiện online phụ thuộc hệ quản trị cơ sở dữ liệu. Với bảng lớn, cần kiểm tra tài liệu DDL của database đang dùng và thử trên dữ liệu có quy mô tương đương production.

Trong Spring Boot, có thể quản lý schema bằng Flyway hoặc Liquibase. Ví dụ file Flyway:

```text
src/main/resources/db/migration/
  V042__add_customer_display_name.sql
```

Ứng dụng cũ thường có thể tiếp tục chạy nếu chỉ thêm một cột nullable mà code cũ không biết đến. Tuy nhiên, vẫn phải kiểm tra các câu `SELECT *`, stored procedure, view, trigger, replication consumer và code phụ thuộc thứ tự cột.

### 3.2. Migrate: triển khai dual-write

Sau khi schema mới tồn tại ở mọi môi trường, triển khai phiên bản ứng dụng có thể ghi cả hai cột. Trong giai đoạn đầu, tiếp tục đọc cột cũ để việc chuyển đổi không phụ thuộc vào backfill đã hoàn tất hay chưa.

Entity có thể ánh xạ cả hai trường trong giai đoạn chuyển tiếp:

```java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    private Long id;

    @Column(name = "customer_name")
    private String legacyCustomerName;

    @Column(name = "customer_display_name")
    private String customerDisplayName;

    public void changeCustomerDisplayName(String value) {
        this.legacyCustomerName = value;
        this.customerDisplayName = value;
    }
}
```

Đặt quy tắc đồng bộ trong một phương thức nghiệp vụ hoặc mapper dùng chung để tránh các luồng ghi quên cập nhật một trong hai trường. Nếu giá trị mới cần được chuẩn hóa, hãy dùng cùng một hàm chuyển đổi cho cả luồng ghi mới và backfill.

Nếu còn instance cũ chỉ ghi cột cũ, dual-write của phiên bản mới chưa đủ để bảo đảm nhất quán. Hãy chờ rollout hoàn tất trước khi backfill, hoặc triển khai một cơ chế đồng bộ tương thích ở database. Không chuyển luồng đọc sang cột mới khi vẫn còn writer có thể chỉ cập nhật cột cũ.

### 3.3. Backfill: chuyển dữ liệu đã tồn tại

Sau khi các writer tương thích đã được triển khai, backfill những hàng chưa có giá trị mới. Ví dụ, nếu phép chuyển đổi chỉ là sao chép:

```sql
UPDATE orders
SET customer_display_name = customer_name
WHERE customer_display_name IS NULL;
```

Với bảng nhỏ, một câu lệnh có thể đủ. Với bảng lớn, không nên mặc định chạy một câu UPDATE khổng lồ. Hãy chia thành batch nhỏ để mỗi batch có transaction ngắn và có thể retry.

### 3.4. Chuyển đọc sang cột mới

Khi backfill hoàn tất và dữ liệu được kiểm chứng, triển khai phiên bản ứng dụng đọc `customer_display_name`. Trong khoảng thời gian rollback, tiếp tục ghi cả hai cột để phiên bản cũ vẫn có dữ liệu nếu cần quay lại.

Sau khi mọi instance, worker, báo cáo và tích hợp đều không còn đọc/ghi cột cũ, kết thúc dual-write và chuẩn bị contract.

### 3.5. Contract: xóa cột cũ

Chỉ xóa cột cũ sau khi:

- Không còn instance ứng dụng cũ.
- Worker, scheduled job, script, báo cáo và hệ thống tích hợp đã chuyển sang schema mới.
- Đã hết thời gian rollback cần giữ cột cũ.
- Dữ liệu mới đã được kiểm chứng và có phương án phục hồi phù hợp.
- Đã kiểm tra view, index, constraint, trigger và foreign key phụ thuộc cột cũ.

Migration contract có thể là:

```sql
ALTER TABLE orders
DROP COLUMN customer_name;
```

Đây là bước phá hủy khả năng đọc dữ liệu cũ của code cũ. Không gộp bước này vào migration expand hoặc backfill. Triển khai contract riêng giúp giữ một cửa sổ tương thích và giảm rủi ro khi rollback.

## 4. Backfill theo batch, keyset và checkpoint

### 4.1. Vì sao cần chia batch?

Một transaction cập nhật quá nhiều hàng có thể:

- Giữ row lock lâu và làm request nghiệp vụ chờ.
- Tạo transaction log/WAL lớn, tăng replication lag.
- Giữ undo/version record lâu và làm tăng áp lực vacuum/cleanup tùy database.
- Tăng bộ nhớ nếu tải toàn bộ entity vào persistence context.
- Khi thất bại, phải rollback một lượng công việc lớn.
- Làm khó việc tiếp tục từ vị trí đã hoàn tất.

Chia batch giúp giới hạn số hàng mỗi transaction, điều chỉnh tốc độ theo tải database và retry từng phần.

Kích thước batch không có một giá trị đúng cho mọi hệ thống. Có thể bắt đầu với vài trăm hoặc vài nghìn hàng, đo thời gian transaction, lock wait, CPU, I/O và replication lag, sau đó điều chỉnh. Batch quá nhỏ tạo nhiều round-trip và commit; batch quá lớn lại làm transaction dài.

### 4.2. Ưu tiên keyset thay cho OFFSET

Với bảng lớn, phân trang bằng `OFFSET` ngày càng tốn kém vì database phải bỏ qua các hàng trước vị trí yêu cầu. Dùng khóa tăng dần hoặc khóa ổn định để tiếp tục từ giá trị cuối cùng đã xử lý.

Ví dụ truy vấn chọn ID theo keyset, cú pháp `LIMIT` dưới đây phù hợp với PostgreSQL và một số database khác; hãy điều chỉnh theo dialect:

```sql
SELECT id
FROM orders
WHERE id > :lastId
  AND id <= :upperBound
  AND customer_display_name IS NULL
ORDER BY id
LIMIT :batchSize;
```

Sau khi lấy được danh sách ID, cập nhật đúng nhóm đó:

```sql
UPDATE orders
SET customer_display_name = customer_name
WHERE id IN (:ids)
  AND customer_display_name IS NULL;
```

Điều kiện `customer_display_name IS NULL` giúp thao tác idempotent: chạy lại batch không ghi đè giá trị mới đã được ứng dụng dual-write. `NamedParameterJdbcTemplate` có thể mở rộng collection `:ids` thành danh sách bind parameter. Kích thước batch cần nằm trong giới hạn bind parameter của database/driver.

Nếu dữ liệu nguồn có thể NULL, cần xác định rõ NULL là giá trị hợp lệ hay là dữ liệu lỗi. Nếu NULL hợp lệ, không thể dùng riêng trạng thái cột đích NULL để kết luận backfill chưa xử lý; hãy dùng checkpoint hoặc cột trạng thái chuyển đổi và quy tắc kiểm chứng riêng.

### 4.3. Lưu checkpoint cùng transaction với batch

Một bảng checkpoint có thể lưu tiến độ của từng migration job:

```sql
CREATE TABLE migration_checkpoint (
    job_name VARCHAR(100) PRIMARY KEY,
    last_processed_id BIGINT NOT NULL,
    upper_bound_id BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

Trong mỗi batch:

1. Đọc checkpoint hiện tại.
2. Chọn nhóm ID tiếp theo.
3. Cập nhật dữ liệu trong batch.
4. Cập nhật `last_processed_id` tới ID cuối cùng đã chọn.
5. Commit cập nhật dữ liệu và checkpoint trong cùng transaction.

Nếu transaction rollback, cả dữ liệu và checkpoint đều quay về trạng thái trước batch. Khi job chạy lại, nó có thể xử lý lại batch chưa commit. Nếu checkpoint được ghi ở transaction khác, có thể xảy ra trường hợp checkpoint tiến lên nhưng dữ liệu chưa được cập nhật, làm bỏ sót bản ghi.

Cần khóa hoặc điều phối checkpoint nếu có nhiều worker chạy cùng một job. Nếu muốn chia việc cho nhiều worker, thiết kế claim/lease hoặc cơ chế khóa hàng riêng; không để nhiều worker cùng tiến một checkpoint đơn giản mà không có đồng bộ.

### 4.4. Ví dụ service xử lý một chunk

Ví dụ sau dùng `NamedParameterJdbcTemplate` và giả định database hỗ trợ cú pháp `LIMIT`. Đây là đoạn minh họa cho một phương thức chunk, không phải lớp hoàn chỉnh:

```java
@Service
public class OrderBackfillChunkService {

    private final NamedParameterJdbcTemplate jdbc;

    public OrderBackfillChunkService(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public ChunkResult process(
            long lastId,
            long upperBoundId,
            int batchSize) {

        var parameters = new MapSqlParameterSource()
                .addValue("lastId", lastId)
                .addValue("upperBound", upperBoundId)
                .addValue("batchSize", batchSize);

        List<Long> ids = jdbc.query("""
                SELECT id
                FROM orders
                WHERE id > :lastId
                  AND id <= :upperBound
                  AND customer_display_name IS NULL
                ORDER BY id
                LIMIT :batchSize
                """,
                parameters,
                (rs, rowNum) -> rs.getLong("id"));

        if (ids.isEmpty()) {
            return new ChunkResult(lastId, 0, true);
        }

        int updated = jdbc.update("""
                UPDATE orders
                SET customer_display_name = customer_name
                WHERE id IN (:ids)
                  AND customer_display_name IS NULL
                """,
                new MapSqlParameterSource("ids", ids));

        long nextId = ids.get(ids.size() - 1);

        // Cập nhật checkpoint trong cùng transaction tại đây.
        // Nếu cập nhật checkpoint lỗi, thay đổi dữ liệu của chunk cũng rollback.

        return new ChunkResult(nextId, updated, false);
    }

    public record ChunkResult(
            long lastProcessedId,
            int updatedRows,
            boolean finished
    ) {}
}
```

Orchestrator gọi phương thức chunk qua một Spring bean khác để mỗi lần xử lý có transaction riêng. Tránh gọi một phương thức `@Transactional` khác trong cùng object qua self-invocation vì lời gọi nội bộ không đi qua proxy transaction mặc định của Spring.

Ví dụ trên bỏ qua phần lưu/khóa checkpoint để làm rõ ranh giới chunk. Trong triển khai thực tế, hãy cập nhật checkpoint cùng transaction với câu UPDATE. Nếu `ids` rỗng, cần thực hiện bước xác minh cuối cùng trước khi đánh dấu job hoàn tất.

### 4.5. Chọn high-water mark và xử lý bản ghi phát sinh đồng thời

Khi bắt đầu job, có thể ghi lại `upper_bound_id` là ID lớn nhất trong tập dữ liệu cần backfill. Điều này giúp job có phạm vi hữu hạn và không chạy mãi khi ứng dụng tiếp tục tạo bản ghi mới.

Tuy nhiên, sequence/identity có thể được cấp trước khi transaction insert commit. Một transaction tạo ID nhỏ hơn high-water mark có thể commit muộn sau khi backfill đã đi qua vị trí đó. Vì vậy:

- Ứng dụng mới phải dual-write để bản ghi tạo mới luôn có cả hai giá trị.
- Sau lượt keyset chính, chạy một lượt reconciliation tìm các hàng còn thiếu trong phạm vi.
- Kiểm tra các bản ghi có thời điểm commit muộn hoặc nguồn dữ liệu thay đổi trong lúc backfill.
- Không đánh dấu hoàn tất chỉ vì cursor đã vượt high-water mark; phải dựa trên điều kiện dữ liệu đã được xác minh.

Nếu dùng nhiều worker, database có thể hỗ trợ `FOR UPDATE SKIP LOCKED` để các worker claim các hàng khác nhau. Đây là cú pháp phụ thuộc database và cần có chiến lược checkpoint/lease tương ứng.

## 5. Tính idempotent, retry và xử lý lỗi

Một backfill an toàn cần có thể chạy lại mà không làm hỏng dữ liệu đã chuyển đổi. Một số nguyên tắc:

- Chỉ cập nhật hàng chưa được chuyển đổi hoặc hàng được xác định rõ là cần sửa.
- Không ghi đè giá trị mới do ứng dụng tạo trong giai đoạn dual-write.
- Dùng phép chuyển đổi xác định được: cùng dữ liệu đầu vào phải tạo cùng kết quả.
- Commit dữ liệu và checkpoint cùng transaction.
- Ghi nhận số hàng đọc, số hàng cập nhật, số hàng bỏ qua và lỗi.
- Có giới hạn retry và phân loại lỗi tạm thời/lỗi dữ liệu.
- Lưu ID bản ghi lỗi để xử lý riêng, không bỏ qua âm thầm.

Nếu một batch thất bại vì deadlock hoặc lock timeout, có thể retry transaction của batch theo chính sách có backoff. Không retry vô hạn với lỗi schema, lỗi chuyển đổi hoặc dữ liệu không hợp lệ. Khi lỗi lặp lại, dừng job hoặc đưa bản ghi vào danh sách lỗi để người vận hành quyết định.

Đối với phép chuyển đổi phức tạp, hãy lưu thêm version của thuật toán hoặc mã migration. Khi logic chuyển đổi thay đổi, cần biết bản ghi nào đã được xử lý bằng phiên bản nào và có cần chạy lại hay không.

## 6. Đồng bộ dữ liệu khi ứng dụng vẫn đang hoạt động

Backfill thường chạy trong lúc hệ thống vẫn nhận request. Điều đó tạo ra cạnh tranh giữa job và ứng dụng.

Ví dụ, job đọc `customer_name = 'An'`, trong khi request cập nhật thành `'Anh An'`. Nếu job ghi giá trị cũ sau request, cột mới có thể bị ghi đè sai.

Một số biện pháp:

1. **Dual-write trước khi backfill:** code mới ghi cả cột cũ và cột mới trong cùng transaction.
2. **Conditional update:** backfill chỉ ghi khi cột mới vẫn NULL, tránh ghi đè giá trị mới đã có.
3. **Thứ tự triển khai rõ ràng:** chờ tất cả writer cũ được nâng cấp hoặc có trigger đồng bộ trước khi chuyển đọc.
4. **Reconciliation:** sau backfill, quét các hàng còn thiếu hoặc không khớp theo quy tắc chuyển đổi.
5. **Optimistic locking hoặc điều kiện version:** dùng khi phép chuyển đổi cần phát hiện dữ liệu thay đổi đồng thời thay vì âm thầm ghi đè.
6. **Rate limit:** giảm tốc độ job khi database có tải cao hoặc replication lag tăng.

Không dùng một transaction duy nhất cho toàn bộ backfill chỉ để tránh cạnh tranh. Transaction dài làm tăng thời gian giữ lock và có thể gây ảnh hưởng lớn hơn. Chọn batch nhỏ, kiểm soát thứ tự ghi và dùng điều kiện cập nhật phù hợp.

## 7. Kiểm chứng dữ liệu sau backfill

Không chỉ dựa vào log “job completed”. Cần kiểm chứng dữ liệu theo các bất biến đã định nghĩa.

Với ví dụ sao chép cột:

```sql
-- Số hàng còn thiếu giá trị mới
SELECT COUNT(*)
FROM orders
WHERE customer_name IS NOT NULL
  AND customer_display_name IS NULL;

-- Số hàng có giá trị không khớp
SELECT COUNT(*)
FROM orders
WHERE customer_display_name IS DISTINCT FROM customer_name;
```

`IS DISTINCT FROM` là cú pháp PostgreSQL giúp so sánh NULL an toàn; database khác có thể cần biểu thức tương đương. Nếu phép chuyển đổi có chuẩn hóa, thay điều kiện so sánh bằng quy tắc nghiệp vụ, ví dụ `LOWER(TRIM(customer_name))`.

Các bước kiểm chứng có thể gồm:

- Tổng số bản ghi thuộc phạm vi cần backfill.
- Số hàng đã chuyển đổi, còn thiếu và bị lỗi.
- Đối chiếu giá trị cũ/mới theo quy tắc chuyển đổi.
- Kiểm tra bản ghi trùng, khóa ngoại và uniqueness.
- Lấy mẫu một số bản ghi để kiểm tra thủ công.
- Kiểm tra các writer đang hoạt động có tiếp tục tạo dữ liệu hợp lệ.
- Theo dõi sai lệch trong một khoảng thời gian trước khi chuyển đọc.

Nếu có NULL hợp lệ, phải tách “đã xử lý và kết quả NULL” khỏi “chưa xử lý”. Có thể dùng checkpoint theo ID, bảng trạng thái hoặc cột đánh dấu migration để phân biệt.

## 8. Thêm constraint sau khi dữ liệu đã sẵn sàng

Một cột mới thường được thêm nullable để không phá code cũ. Chỉ thêm `NOT NULL`, unique constraint hoặc foreign key sau khi backfill và kiểm chứng dữ liệu.

Ví dụ:

```sql
ALTER TABLE orders
ALTER COLUMN customer_display_name SET NOT NULL;
```

Cú pháp trên là PostgreSQL. Với database khác, cú pháp và mức khóa có thể khác. Một số hệ quản trị hỗ trợ thêm constraint ở trạng thái chưa validate rồi xác minh riêng để giảm tác động lên bảng đang hoạt động. Hãy kiểm tra khả năng online DDL và thời gian khóa trong database mục tiêu.

Trước khi thêm constraint:

- Xác nhận không còn NULL ngoài trường hợp được phép.
- Kiểm tra dữ liệu trùng trước unique constraint.
- Kiểm tra bản ghi mồ côi trước foreign key.
- Xác định default có ý nghĩa nghiệp vụ hay chỉ che giấu dữ liệu thiếu.
- Đánh giá lock, index build và replication lag.
- Triển khai constraint sau khi mọi writer đã tuân thủ quy tắc mới.

Không thêm default tùy tiện chỉ để migration qua được. Một giá trị mặc định giả có thể khiến dữ liệu nhìn hợp lệ nhưng sai nghiệp vụ.

## 9. Tổ chức migration với Flyway hoặc Liquibase

Flyway và Liquibase phù hợp để quản lý các thay đổi schema có version và lịch sử triển khai. Có thể tách các bước thành nhiều migration:

```text
V042__expand_add_customer_display_name.sql
V043__add_backfill_checkpoint_table.sql
V044__add_indexes_for_backfill.sql
V050__contract_drop_customer_name.sql
```

Các file migration nên tập trung vào thay đổi schema nhỏ, có thể dự đoán và chạy theo thứ tự. Backfill hàng triệu bản ghi thường phù hợp hơn với một job riêng có checkpoint, metric, retry và khả năng tạm dừng/tiếp tục, thay vì một migration chạy lâu khi ứng dụng khởi động.

Có thể dùng Flyway/Liquibase để tạo bảng checkpoint hoặc đánh dấu phiên bản logic backfill. Job chỉ chạy sau khi migration expand đã được áp dụng. Contract migration được triển khai ở release sau, khi đã xác nhận không còn dependency.

Trong production, nên quản lý schema bằng migration có kiểm soát và đặt Hibernate ở chế độ xác minh mapping, ví dụ:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

Không dựa vào `ddl-auto=update` để thực hiện thay đổi schema quan trọng ở production. Hibernate không thay thế quy trình expand/backfill/validate/contract.

Lưu ý rằng DDL có thể commit ngầm hoặc không rollback được tùy database. Không giả định mọi câu lệnh schema đều nằm trong một transaction có thể rollback. Hãy thử migration trên đúng loại database và version đang vận hành.

## 10. Backfill bằng JDBC hay JPA?

| Cách làm | Ưu điểm | Hạn chế |
|---|---|---|
| JPA entity theo batch | Tận dụng mapping, converter, lifecycle callback và validation của ứng dụng | Tốn bộ nhớ persistence context; xử lý từng entity có thể chậm |
| JDBC/NamedParameterJdbcTemplate | SQL trực tiếp, cập nhật hàng loạt hiệu quả và kiểm soát chính xác | Bỏ qua entity listener, dirty checking, cascade và auditing tự động |
| Stored procedure | Có thể xử lý gần database và giảm round-trip | Logic phụ thuộc database, khó kiểm thử/di chuyển hơn |
| Spring Batch | Có chunk, checkpoint, retry, skip và job metadata | Cần thiết kế job/step và vận hành thêm |

Nếu backfill bằng JDBC, hãy chủ động quyết định các trường audit và version. Câu UPDATE trực tiếp không tự gọi `@PreUpdate`, `AuditingEntityListener` hoặc tăng `@Version`. Nếu cần ghi nhận actor kỹ thuật, hãy truyền rõ giá trị như `migration:customer-display-name`; nếu đây chỉ là chuyển đổi kỹ thuật không được coi là cập nhật nghiệp vụ, hãy thống nhất chính sách có giữ nguyên `updated_at` hay không.

JDBC cũng không đồng bộ persistence context đang mở. Nếu cùng transaction có entity đã tải trước đó, hãy flush thay đổi JPA cần giữ trước bulk SQL rồi refresh/clear entity phù hợp. Sau khi cập nhật ngoài Hibernate, cân nhắc evict L2/query cache liên quan nếu ứng dụng dùng cache.

## 11. Rollback và kế hoạch phục hồi

Rollback code không đồng nghĩa rollback dữ liệu. Sau khi backfill, cột mới đã có dữ liệu; sau khi code mới bắt đầu ghi dữ liệu mới, cột cũ có thể cần được đồng bộ để phiên bản cũ đọc được.

Trong giai đoạn tương thích:

- Giữ cột cũ và mới.
- Tiếp tục dual-write trong cửa sổ rollback.
- Không drop cột cũ cùng release chuyển đọc.
- Giữ lại checkpoint và log backfill để biết phạm vi đã xử lý.
- Chuẩn bị cách đối chiếu hoặc khôi phục nếu phép chuyển đổi sai.

Nếu đã chạy contract và xóa cột cũ, rollback cần restore schema và có thể cần khôi phục dữ liệu từ backup hoặc tái tạo từ cột mới. Không giả định migration drop column có thể đảo ngược mà không mất dữ liệu.

Với phép chuyển đổi một chiều hoặc mất thông tin, hãy lưu snapshot, export hoặc bảng staging trước khi thay đổi. Xác định rõ ai phê duyệt bước contract và tiêu chí nào cho phép thực hiện.

## 12. Vận hành và giám sát job backfill

Một job production nên cung cấp tối thiểu:

- Tên job, version thuật toán và mã lần chạy.
- Upper bound, last processed ID và trạng thái hiện tại.
- Tổng số hàng dự kiến, đã xử lý, cập nhật, bỏ qua và lỗi.
- Thời gian mỗi batch, throughput và số lần retry.
- Lock wait, deadlock, CPU/I/O và replication lag.
- Thời điểm bắt đầu/kết thúc, người hoặc service account khởi chạy.
- Cơ chế pause/resume/cancel có kiểm soát.

Nên chạy thử trên staging với bản sao dữ liệu gần thực tế. Khi production tải cao, giảm batch size hoặc tạm dừng theo ngưỡng. Job cần có giới hạn thời gian và cảnh báo nếu tiến độ không tăng hoặc số lỗi vượt ngưỡng.

Đừng để job chạy song song ngoài ý muốn. Dùng lock/lease hoặc cơ chế điều phối để bảo đảm chỉ một runner sở hữu checkpoint, trừ khi thiết kế đã hỗ trợ nhiều worker.

## 13. Kiểm thử chiến lược thay đổi schema

Một quy trình kiểm thử đầy đủ nên bao gồm:

1. **Migration từ schema cũ:** dựng database ở version trước và chạy expand migration.
2. **Tương thích ứng dụng cũ:** xác nhận code cũ vẫn đọc/ghi được khi cột mới đã xuất hiện.
3. **Rolling deployment:** kiểm thử phiên bản cũ và mới cùng tồn tại, đặc biệt là các writer.
4. **Dual-write:** xác nhận một thao tác cập nhật giữ hai cột đồng nhất.
5. **Backfill idempotent:** chạy cùng batch hai lần và xác nhận lần hai không phá dữ liệu đã đúng.
6. **Restart/resume:** dừng job giữa chừng, khởi động lại và xác nhận checkpoint tiếp tục đúng.
7. **Concurrent writes:** cập nhật bản ghi trong lúc backfill và xác nhận không ghi đè giá trị mới.
8. **Data validation:** kiểm tra NULL, mismatch, uniqueness, foreign key và bản ghi lỗi.
9. **Contract:** chỉ thử xóa cột sau khi code cũ và các consumer cũ đã được loại bỏ.
10. **Rollback:** thử quay lại phiên bản ứng dụng trước trong khi schema còn giữ tương thích.

Nên dùng database cùng loại với production trong integration test. H2 hoặc database in-memory có thể khác về DDL, lock, isolation, index và cú pháp SQL; test qua H2 không đủ để chứng minh migration sẽ an toàn trên PostgreSQL/MySQL/Oracle thực tế.

## 14. Lỗi thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Xóa/đổi tên cột ngay trong cùng release code | Instance cũ lỗi khi truy cập schema | Dùng expand trước, contract sau |
| Backfill trước khi mọi writer tương thích | Cột mới có thể lỗi thời sau khi writer cũ cập nhật cột cũ | Chờ rollout writer hoặc dùng cơ chế đồng bộ tạm |
| Chạy một UPDATE cho toàn bảng lớn | Lock/log/replication lag và rollback lớn | Chia batch, commit từng chunk |
| Dùng OFFSET cho bảng lớn | Các trang sau ngày càng tốn kém | Dùng keyset theo khóa ổn định |
| Ghi checkpoint riêng transaction | Tiến độ có thể vượt dữ liệu chưa commit | Ghi checkpoint cùng transaction của chunk |
| Retry không idempotent | Dữ liệu bị ghi đè hoặc nhân đôi | Conditional update và khóa đối chiếu ổn định |
| Chỉ nhìn log hoàn tất | Bản ghi lỗi hoặc NULL vẫn còn | Chạy reconciliation và truy vấn kiểm chứng |
| Thêm NOT NULL trước backfill | Migration hoặc writer cũ thất bại | Thêm nullable, backfill, validate rồi thêm constraint |
| Dùng ddl-auto=update cho production | Thay đổi schema khó kiểm soát | Dùng Flyway/Liquibase |
| Drop cột trước khi hết rollback window | Không thể quay lại code cũ an toàn | Tách contract thành release riêng |

## 15. Checklist trước khi triển khai

- [ ] Đã xác định schema cũ, schema đích và phép chuyển đổi dữ liệu.
- [ ] Expand migration chỉ thêm cấu trúc tương thích, chưa xóa cột cũ.
- [ ] Đã xác định mọi writer/reader: web app, worker, scheduler, báo cáo, script và hệ thống ngoài.
- [ ] Có kế hoạch dual-write hoặc cơ chế đồng bộ tương thích.
- [ ] Backfill có batch size, keyset, upper bound và checkpoint.
- [ ] Cập nhật dữ liệu và checkpoint cùng transaction.
- [ ] Điều kiện cập nhật idempotent, không ghi đè dữ liệu mới.
- [ ] Có retry/backoff, giới hạn lỗi và khả năng resume.
- [ ] Có reconciliation và truy vấn kiểm chứng dữ liệu.
- [ ] Đã đánh giá index, lock, transaction log, replication lag và online DDL.
- [ ] Đã quyết định xử lý audit field, `@Version`, cache và persistence context khi dùng JDBC.
- [ ] Đã thử migration, backfill, restart và rollback trên database tương đương production.
- [ ] Contract chỉ được thực hiện sau khi không còn consumer schema cũ và hết cửa sổ rollback.

Thay đổi schema nhiều bước giúp ứng dụng duy trì hoạt động trong khi dữ liệu được chuyển đổi. Expand tạo cấu trúc mới tương thích, migrate triển khai dual-write và backfill theo batch có checkpoint, còn contract chỉ xóa cấu trúc cũ sau khi đã kiểm chứng và hết nhu cầu rollback. Thiết kế backfill idempotent, có thể tiếp tục sau lỗi và được kiểm tra bằng bất biến dữ liệu là nền tảng để triển khai an toàn trên bảng lớn.