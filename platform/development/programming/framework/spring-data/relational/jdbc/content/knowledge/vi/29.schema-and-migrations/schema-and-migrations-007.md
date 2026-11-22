# Kiểm soát schema cũ, giá trị mặc định và backfill dữ liệu

## 1. Thay đổi schema khi hệ thống đã có dữ liệu

Một ứng dụng Spring Data JDBC thường bắt đầu với schema tương đối nhỏ: bảng aggregate root, bảng con, khóa chính và một số index. Khi sản phẩm phát triển, model và database phải thay đổi theo:

- Thêm cột mới cho một thuộc tính.
- Đổi tên hoặc đổi kiểu cột.
- Tách một trường thành nhiều trường.
- Thêm bảng hoặc quan hệ mới.
- Thêm constraint, index hoặc giá trị mặc định.
- Chuyển dữ liệu lịch sử sang cấu trúc mới.

Thay đổi một class Java thường đơn giản hơn thay đổi schema đang chứa hàng triệu bản ghi và đang được nhiều phiên bản ứng dụng sử dụng. Trong lúc triển khai, có thể đồng thời tồn tại phiên bản ứng dụng cũ, phiên bản mới, batch job chưa cập nhật và dữ liệu lịch sử chưa có giá trị cho cột mới.

Vì vậy, schema migration cần kiểm soát cả cấu trúc và dữ liệu. Bài này tập trung vào ba vấn đề gắn liền với nhau: duy trì khả năng tương thích với schema cũ, chọn đúng nơi đặt giá trị mặc định và backfill dữ liệu lịch sử một cách an toàn.

## 2. Schema migration và trách nhiệm của ứng dụng

Schema là hợp đồng giữa ứng dụng và database. Trong Spring Data JDBC, mapping entity/aggregate dựa trên tên bảng, tên cột, kiểu dữ liệu, khóa và quan hệ đã khai báo. Khi schema thay đổi mà mapping không thay đổi tương ứng, lỗi có thể xuất hiện lúc đọc hoặc ghi:

- Câu SELECT tham chiếu cột không còn tồn tại.
- INSERT/UPDATE ghi vào cột có kiểu không tương thích.
- Cột mới có NOT NULL nhưng dữ liệu insert không cung cấp giá trị.
- Entity mới đọc cột nullable nhưng code giả định luôn có giá trị.
- Foreign key hoặc unique constraint từ chối dữ liệu đang được ghi.

Không nên để từng instance ứng dụng tự tạo hoặc sửa schema trong môi trường production. Hãy quản lý schema bằng migration có phiên bản và chạy theo một quy trình triển khai rõ ràng.

Các công cụ thường dùng:

- **Flyway:** quản lý migration theo phiên bản hoặc migration lặp lại; thường lưu lịch sử trong bảng schema history.
- **Liquibase:** mô tả thay đổi schema bằng changeset và theo dõi changeset đã áp dụng.
- **SQL migration riêng:** có thể phù hợp với hệ thống nhỏ, nhưng vẫn cần version, lịch sử, thứ tự và quy trình chạy nhất quán.

Chọn một công cụ làm nguồn quản lý schema chính. Tránh để Flyway, Liquibase, script thủ công và cấu hình tự tạo schema cùng thay đổi một database mà không có quy ước phối hợp.

## 3. Migration phải được version hóa và có thể truy vết

Với Flyway, migration dạng SQL thường có tên theo quy ước version, ví dụ:

~~~text
src/main/resources/db/migration/
  V001__create_customer.sql
  V002__add_customer_status.sql
  V003__add_customer_audit_columns.sql
~~~

Ví dụ migration:

~~~sql
ALTER TABLE customers
ADD COLUMN status VARCHAR(20);
~~~

Với Liquibase, thay đổi được mô tả trong changeset và được ghi nhận trong bảng lịch sử do Liquibase quản lý.

Các nguyên tắc quan trọng:

1. Mỗi migration versioned đã chạy ở môi trường dùng chung phải được coi là bất biến.
2. Muốn sửa schema sau đó, tạo migration mới thay vì sửa migration cũ đã áp dụng.
3. Đặt tên migration mô tả thay đổi và giữ thứ tự rõ ràng.
4. Kiểm tra migration trên database cùng loại và phiên bản gần production.
5. Biết rõ migration nào chạy trước khi ứng dụng mới khởi động.
6. Ghi nhận migration có thể rollback hay chỉ có thể tiến về phía trước bằng migration bù.

Nhiều DDL không có cùng semantics transaction trên mọi database. Một số engine hỗ trợ transactional DDL cho một số lệnh; một số lệnh khác có thể commit ngầm, khóa bảng hoặc yêu cầu quy trình riêng. Không mặc định rằng một migration chứa nhiều DDL sẽ luôn rollback toàn bộ nếu câu lệnh cuối thất bại.

## 4. Tương thích ngược khi triển khai nhiều phiên bản ứng dụng

Trong rolling deployment, phiên bản cũ và mới có thể cùng chạy trong một khoảng thời gian. Một migration an toàn cần xem xét cả hai phiên bản.

Ví dụ, ứng dụng hiện lưu tên đầy đủ trong cột `full_name`. Phiên bản mới muốn tách thành `given_name` và `family_name`.

Nếu đổi tên cột ngay và xóa `full_name`, instance cũ vẫn đang chạy sẽ lỗi khi truy vấn hoặc ghi dữ liệu. Nếu deploy code mới trước khi thêm cột, instance mới lại lỗi vì schema chưa có cột.

Giải pháp thường dùng là **expand-migrate-contract**:

~~~text
Giai đoạn 1: EXPAND
  Thêm cột mới hoặc bảng mới theo cách tương thích ngược.
  Giữ nguyên cột cũ.

Giai đoạn 2: MIGRATE
  Deploy code hiểu cả schema cũ và mới.
  Backfill dữ liệu lịch sử.
  Chuyển dần đọc/ghi sang cấu trúc mới.

Giai đoạn 3: CONTRACT
  Xác nhận không còn instance/job dùng cấu trúc cũ.
  Ngừng ghi cột cũ.
  Xóa cột hoặc constraint cũ trong migration riêng.
~~~

### 4.1. Expand

Thêm hai cột mới dưới dạng nullable:

~~~sql
ALTER TABLE customers
ADD COLUMN given_name VARCHAR(100);

ALTER TABLE customers
ADD COLUMN family_name VARCHAR(100);
~~~

Ứng dụng cũ vẫn có thể tiếp tục dùng `full_name`. Schema mới có thêm cột nhưng chưa bắt buộc code cũ biết chúng tồn tại.

Trước khi thêm cột, hãy kiểm tra:

- Tên cột không xung đột với mapping hoặc từ khóa database.
- Kiểu và độ dài phù hợp dữ liệu thực tế.
- DDL có khóa hoặc rebuild bảng hay không.
- Index mới có thể tạo online/concurrently không.
- Database có đủ dung lượng và log/replication capacity cho thay đổi không.

### 4.2. Deploy code tương thích

Phiên bản trung gian có thể đọc cấu trúc mới nếu đã backfill, nhưng trong giai đoạn chuyển tiếp cần xử lý hàng chưa backfill:

~~~java
public String displayName(Customer customer) {
    if (customer.givenName() != null
            && customer.familyName() != null) {
        return customer.givenName() + " " + customer.familyName();
    }

    return customer.fullName();
}
~~~

Đây chỉ là ví dụ logic fallback. Nếu phiên bản cũ vẫn ghi `full_name`, phiên bản mới cần có chiến lược giữ dữ liệu mới đồng bộ:

- Tạm thời ghi cả cột cũ và cột mới.
- Dùng trigger database trong giai đoạn chuyển tiếp.
- Hoặc kiểm soát thời điểm chuyển writer để không có phiên bản cũ tiếp tục ghi.

Chọn một nguồn dữ liệu có thẩm quyền cho từng giai đoạn. Dual-write có thể tạo bất nhất nếu một lần ghi cập nhật được cột này nhưng thất bại ở cột kia; nếu dual-write trong cùng database transaction, bảo đảm cả hai cột cùng commit/rollback.

### 4.3. Contract

Chỉ xóa `full_name` sau khi:

- Không còn instance ứng dụng cũ.
- Batch job, scheduled task, consumer và công cụ vận hành đã được cập nhật.
- Không còn query, view, report hoặc integration phụ thuộc cột cũ.
- Dữ liệu mới đã được backfill và xác minh.
- Có kế hoạch khôi phục nếu phát hiện phụ thuộc bị bỏ sót.

Việc xóa cột nên là một migration riêng, sau giai đoạn chuyển tiếp. Không gộp thêm cột, backfill, chuyển code và xóa cột cũ thành một bước triển khai không thể quan sát.

## 5. Thêm cột mới vào bảng đã có dữ liệu

Giả sử bảng `customers` đã có nhiều triệu hàng và cần thêm cột `preferred_language`.

### 5.1. Thêm nullable column trước

~~~sql
ALTER TABLE customers
ADD COLUMN preferred_language VARCHAR(10);
~~~

Đây thường là cách an toàn để mở rộng schema vì hàng cũ có thể giữ giá trị NULL trong giai đoạn đầu. Code mới phải chấp nhận NULL cho tới khi backfill xong.

Không nên lập tức thêm `NOT NULL` nếu chưa biết database sẽ xử lý các hàng cũ thế nào và ứng dụng có thể cung cấp giá trị cho mọi đường ghi hay chưa.

### 5.2. Backfill dữ liệu cũ

Nếu có thể suy ra ngôn ngữ từ một trường cũ hoặc quy tắc nghiệp vụ, chạy backfill có kiểm soát. Nếu không thể suy ra, hãy quyết định giá trị fallback với chủ sở hữu nghiệp vụ. Không tự chọn một giá trị tùy tiện chỉ để thỏa constraint.

Ví dụ:

~~~sql
UPDATE customers
SET preferred_language = 'vi'
WHERE preferred_language IS NULL;
~~~

Với bảng nhỏ, câu lệnh đơn giản có thể đủ. Với bảng lớn, một UPDATE duy nhất có thể tạo transaction dài, giữ lock lâu, sinh nhiều WAL/redo log và ảnh hưởng replication. Khi đó nên chia thành batch.

### 5.3. Cập nhật code để luôn ghi giá trị

Sau khi cột đã tồn tại, phiên bản ứng dụng mới phải bảo đảm mọi đường tạo customer đều có giá trị:

- API tạo mới.
- Import file.
- Consumer xử lý message.
- Batch job.
- Script quản trị.
- Test fixture hoặc dữ liệu seed.

Chỉ cập nhật controller không đủ nếu còn một writer khác tạo hàng.

### 5.4. Thêm NOT NULL sau khi dữ liệu đã đầy đủ

Sau backfill và khi mọi writer đã cung cấp giá trị, kiểm tra:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE preferred_language IS NULL;
~~~

Chỉ khi kết quả bằng 0 và các writer mới không tạo thêm NULL, mới cân nhắc:

~~~sql
ALTER TABLE customers
ALTER COLUMN preferred_language SET NOT NULL;
~~~

Cú pháp ALTER COLUMN khác nhau theo database. Trước khi chạy trên bảng lớn, kiểm tra cách engine xác thực constraint và thời gian khóa bảng. Có database hỗ trợ thêm constraint ở trạng thái chưa validate rồi xác thực riêng; có database yêu cầu scan hoặc lock khác.

## 6. Giá trị mặc định ở database và ở ứng dụng

Giá trị mặc định có thể được thiết lập ở hai tầng. Chúng giải quyết hai nhu cầu khác nhau.

### 6.1. Database DEFAULT

Ví dụ:

~~~sql
ALTER TABLE customers
ADD COLUMN status VARCHAR(20) DEFAULT 'ACTIVE';
~~~

Database default áp dụng khi câu INSERT bỏ qua cột hoặc chỉ định từ khóa `DEFAULT` cho cột đó. Nếu câu INSERT nêu cột và truyền SQL `NULL`, database thường lưu NULL thay vì dùng default.

Ví dụ:

~~~sql
-- Database dùng default ACTIVE cho status.
INSERT INTO customers (id, name)
VALUES (101, 'An');

-- Giá trị NULL được truyền tường minh; DEFAULT không tự thay thế NULL.
INSERT INTO customers (id, name, status)
VALUES (102, 'Binh', NULL);
~~~

Database default hữu ích khi:

- Nhiều ứng dụng hoặc script cùng ghi một bảng.
- Cần bảo vệ giá trị mặc định ở tầng database.
- Một writer cũ không biết cột mới và bỏ qua cột đó trong INSERT.
- Dữ liệu được ghi trực tiếp từ công cụ vận hành hoặc batch khác.

### 6.2. Giá trị mặc định ở Java/domain model

Ứng dụng có thể gán mặc định khi tạo object:

~~~java
public record Customer(
        Long id,
        String name,
        String status
) {
    public static Customer register(Long id, String name) {
        return new Customer(id, name, "ACTIVE");
    }
}
~~~

Application/domain default hữu ích khi:

- Quy tắc mặc định là một phần của nghiệp vụ.
- Code cần biết giá trị ngay trước khi lưu.
- Cần kiểm tra hoặc tính toán dựa trên giá trị mặc định.
- Muốn domain object hợp lệ ngay khi được tạo.

Không nên dựa vào database default để thay thế domain behavior nếu ứng dụng cần sử dụng giá trị trước khi ghi. Ngược lại, Java default không bảo vệ các writer khác ngoài ứng dụng đó.

### 6.3. Không giả định Java null sẽ kích hoạt database DEFAULT

Đây là điểm quan trọng khi dùng Spring Data JDBC. Nếu câu INSERT được tạo có cột `status` và bind giá trị Java `null`, database nhận SQL NULL; default của cột không nhất thiết được áp dụng.

Ví dụ SQL có hai semantics khác nhau:

~~~sql
INSERT INTO customers (id, name)
VALUES (?, ?);

INSERT INTO customers (id, name, status)
VALUES (?, ?, NULL);
~~~

Ở câu đầu, database có thể dùng default của `status`. Ở câu thứ hai, `status` được truyền NULL.

Với generated SQL của Spring Data JDBC, hãy kiểm tra mapping và câu SQL thực tế trên phiên bản đang dùng. Không suy luận rằng thuộc tính Java null đồng nghĩa với việc framework bỏ qua cột. Nếu cần database default, có thể:

- Gán giá trị mặc định trong domain trước khi save.
- Dùng câu SQL tùy chỉnh có chủ đích bỏ cột hoặc dùng từ khóa DEFAULT.
- Thiết kế một insert path riêng phù hợp với schema.

Đừng thêm default ở database rồi để model và application logic giả định một giá trị khác. Hai tầng phải có một chính sách nhất quán.

## 7. DEFAULT có tự backfill hàng cũ không?

Không nên giả định việc thêm cột có DEFAULT luôn tạo ra cùng một kết quả vật lý và vận hành trên mọi database.

Khi thêm cột mới, database có thể:

- Hiển thị default cho hàng cũ theo cơ chế metadata.
- Ghi giá trị default vào các hàng cũ bằng thao tác rewrite.
- Thực hiện DDL cần scan hoặc lock bảng.
- Có hành vi phụ thuộc phiên bản database và loại default.

Ngay cả khi database cho phép thêm `NOT NULL DEFAULT ...` trong một lệnh ngắn, chi phí và semantics vẫn phụ thuộc engine/version. Một default hằng số có thể được tối ưu khác với default biểu thức động như timestamp.

Với bảng lớn, hãy tách câu hỏi thành hai phần:

1. Làm sao thêm cột với mức ảnh hưởng schema thấp nhất?
2. Làm sao tạo giá trị đúng cho dữ liệu lịch sử và xác minh kết quả?

Nếu dữ liệu cũ cần giá trị được tính từ nhiều cột, không thể dùng một default hằng số để thay thế backfill nghiệp vụ.

## 8. Backfill là gì và khi nào cần?

Backfill là quá trình bổ sung hoặc chuyển đổi dữ liệu đã tồn tại để đáp ứng schema/model mới.

Ví dụ:

- Thêm `normalized_email` và tính từ `email` cũ.
- Tách `full_name` thành `given_name` và `family_name`.
- Chuyển mã trạng thái số sang chuỗi.
- Điền `created_at` cho các hàng lịch sử.
- Tạo bảng mới từ dữ liệu đang nằm trong cột JSON cũ.
- Gán foreign key mới dựa trên quan hệ đã tồn tại.

Backfill không chỉ là UPDATE hàng loạt. Một backfill an toàn cần xác định:

- Nguồn dữ liệu chuẩn.
- Công thức chuyển đổi.
- Giá trị nào được xem là thiếu.
- Có thể chạy lại không.
- Cách xử lý dữ liệu lỗi hoặc không thể suy ra.
- Cách phối hợp với writer đang hoạt động.
- Cách đo tiến độ và xác minh kết quả.

## 9. Thiết kế backfill idempotent

Một backfill idempotent có thể chạy lại mà không làm hỏng dữ liệu hoặc tạo tác dụng phụ lặp. Điều này quan trọng vì job có thể dừng giữa chừng, timeout hoặc được chạy lại sau sự cố.

Ví dụ backfill email chuẩn hóa:

~~~sql
UPDATE customers
SET normalized_email = LOWER(TRIM(email))
WHERE normalized_email IS NULL
  AND email IS NOT NULL;
~~~

Điều kiện `normalized_email IS NULL` giúp bỏ qua những hàng đã được xử lý hoặc đã được writer mới gán giá trị.

Nếu cần cập nhật lại khi nguồn thay đổi, quy tắc phải khác và cần kiểm soát xung đột rõ ràng. Không bỏ điều kiện chỉ để “đảm bảo tất cả hàng được ghi lại”, vì có thể ghi đè giá trị mới do ứng dụng tạo ra.

### 9.1. Idempotence không có nghĩa là bỏ qua mọi lỗi

Nếu một email không hợp lệ hoặc dữ liệu cũ không thể tách tên, đừng âm thầm gán một giá trị sai. Có thể:

- Ghi hàng lỗi vào bảng exception/quarantine.
- Lưu ID và lý do để xử lý thủ công.
- Đánh dấu trạng thái backfill riêng.
- Sửa nguồn dữ liệu rồi chạy lại.

Một job có thể chạy lại an toàn nhưng vẫn phải làm lộ dữ liệu không thể chuyển đổi.

### 9.2. Xử lý giá trị NULL có chủ đích

Không phải mọi NULL đều có nghĩa “chưa backfill”. Nếu NULL là một trạng thái nghiệp vụ hợp lệ, dùng một cột trạng thái hoặc marker riêng để phân biệt:

~~~text
backfill_status:
  PENDING
  COMPLETED
  NEEDS_REVIEW
~~~

Không dùng NULL vừa để biểu diễn “chưa xử lý” vừa để biểu diễn “người dùng chưa cung cấp giá trị” nếu hai trạng thái có ý nghĩa khác nhau.

## 10. Chia backfill thành batch

Với bảng lớn, tránh một transaction khổng lồ nếu không cần atomicity cho toàn bộ bảng. Có thể xử lý theo batch và commit từng lô.

### 10.1. Keyset pagination theo khóa chính

Giả sử bảng có ID tăng dần. Lấy một nhóm ID sau checkpoint:

~~~sql
SELECT id
FROM customers
WHERE id > :last_id
ORDER BY id
LIMIT :batch_size;
~~~

Sau đó cập nhật nhóm đó:

~~~sql
UPDATE customers
SET normalized_email = LOWER(TRIM(email))
WHERE id > :last_id
  AND id <= :batch_end_id
  AND normalized_email IS NULL
  AND email IS NOT NULL;
~~~

Keyset pagination dựa trên giá trị khóa cuối cùng đã xử lý, tránh chi phí OFFSET tăng dần và tránh việc vị trí hàng bị dịch chuyển làm bỏ sót hoặc lặp hàng khi dữ liệu thay đổi.

`LIMIT` và cú pháp bind parameter phụ thuộc database. Có thể lấy danh sách ID trong ứng dụng rồi dùng batch update, hoặc dùng CTE/update theo cú pháp engine hỗ trợ.

### 10.2. Mỗi batch là một transaction ngắn

Ví dụ service xử lý một batch:

~~~java
@Service
public class CustomerBackfillWriter {

    private final JdbcTemplate jdbc;

    public CustomerBackfillWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public int backfillRange(long firstId, long lastId) {
        return jdbc.update("""
                UPDATE customers
                SET normalized_email = LOWER(TRIM(email))
                WHERE id >= ?
                  AND id <= ?
                  AND normalized_email IS NULL
                  AND email IS NOT NULL
                """,
                firstId,
                lastId
        );
    }
}
~~~

Một coordinator gọi writer theo từng range. Vì `backfillRange` nằm ở bean khác và được gọi qua proxy, mỗi lần gọi có thể là một transaction riêng. Sau mỗi batch commit, coordinator cập nhật checkpoint.

Không đặt một transaction bao ngoài toàn bộ job nếu mục tiêu là commit từng batch; transaction ngoài với propagation `REQUIRED` có thể khiến các method con tham gia cùng một transaction dài.

### 10.3. Lưu checkpoint

Có thể lưu checkpoint trong bảng job:

~~~sql
CREATE TABLE migration_job_checkpoint (
    job_name VARCHAR(100) PRIMARY KEY,
    last_processed_id BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

Sau một batch thành công, cập nhật `last_processed_id`. Nếu process dừng, lần chạy tiếp theo tiếp tục từ checkpoint.

Checkpoint nên được commit nhất quán với batch đã hoàn tất. Nếu checkpoint commit trước dữ liệu, job có thể bỏ qua hàng chưa backfill. Nếu dữ liệu commit trước checkpoint, job có thể xử lý lại một batch; điều này an toàn khi backfill idempotent.

## 11. Backfill trong lúc ứng dụng vẫn ghi dữ liệu

Đây thường là phần khó nhất. Giả sử job đang backfill `normalized_email` từ `email`, trong khi ứng dụng mới tiếp tục cập nhật `email`.

Có thể xảy ra:

1. Job đọc email cũ.
2. Người dùng đổi email.
3. Ứng dụng cập nhật email mới.
4. Job ghi normalized email tính từ email cũ.

Kết quả là hai cột không đồng bộ.

Một số chiến lược:

### Chiến lược A — Writer mới cập nhật cả hai cột

Phiên bản ứng dụng tương thích ghi `email` và `normalized_email` trong cùng transaction. Backfill chỉ xử lý những hàng `normalized_email IS NULL`. Writer mới đã ghi giá trị sẽ không bị job ghi đè.

Đây là cách đơn giản nếu mọi writer cũ đã được dừng hoặc không thể tạo hàng thiếu cột mới.

### Chiến lược B — Trigger tạm thời

Database trigger có thể duy trì cột mới khi bất kỳ writer nào cập nhật cột cũ. Trigger hữu ích khi có nhiều writer hoặc không thể deploy đồng thời, nhưng làm logic ghi phân tán giữa ứng dụng và database. Cần migration rõ ràng để thêm và gỡ trigger.

### Chiến lược C — Quiesce writer

Tạm dừng ghi dữ liệu trong một cửa sổ bảo trì, backfill, xác minh rồi bật lại writer. Cách này dễ hiểu nhưng có thể không đáp ứng yêu cầu availability.

### Chiến lược D — Đồng bộ theo version hoặc timestamp

Backfill có thể đọc một version nguồn và chỉ ghi kết quả nếu version chưa đổi:

~~~sql
UPDATE customers
SET normalized_email = :computed_value
WHERE id = :id
  AND source_version = :version_read;
~~~

Nếu nguồn đã thay đổi, câu lệnh cập nhật 0 hàng và job phải đọc lại. Cách này cần cột version hoặc cơ chế nhận biết thay đổi đáng tin cậy.

Không có một chiến lược phù hợp cho mọi hệ thống. Hãy chọn dựa trên số lượng writer, khả năng dừng writer, yêu cầu availability và mức nhất quán cần đạt.

## 12. Backfill quan hệ và khóa ngoại mới

Một migration có thể thêm foreign key mới cho bảng đã có dữ liệu. Ví dụ trước đây đơn hàng lưu mã khách hàng dạng text, giờ muốn tham chiếu `customers.id`.

Quy trình thường gồm:

1. Thêm cột `customer_id` nullable.
2. Deploy code mới có thể ghi `customer_id` và vẫn hiểu dữ liệu cũ.
3. Backfill `customer_id` bằng cách tra cứu khóa cũ.
4. Kiểm tra các hàng không tìm được customer.
5. Kiểm tra không còn NULL hoặc orphan.
6. Thêm foreign key constraint.
7. Chuyển đọc sang quan hệ mới.
8. Sau thời gian tương thích, xóa cột cũ nếu không còn dùng.

Trước khi thêm constraint:

~~~sql
SELECT COUNT(*)
FROM purchase_orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

Kết quả phải bằng 0 trước khi thêm foreign key nếu schema không cho phép orphan.

Nếu database hỗ trợ thêm constraint chưa validate rồi xác thực riêng, có thể dùng chiến lược đó để giảm thời gian khóa. Cú pháp và lợi ích phụ thuộc engine; không sao chép cú pháp PostgreSQL sang database khác.

## 13. Index và constraint trong migration lớn

Thêm index cho bảng lớn có thể ảnh hưởng writer đang hoạt động. Hãy kiểm tra:

- Database có hỗ trợ tạo index concurrently/online không.
- Lệnh đó có được phép chạy trong transaction migration không.
- Có thể khóa ghi hoặc đọc trong bao lâu.
- Dung lượng index và temporary space có đủ không.
- Index có thực sự cần thiết cho query mới không.

Constraint mới cũng cần kiểm tra dữ liệu hiện có. Ví dụ thêm unique constraint:

~~~sql
SELECT normalized_email, COUNT(*)
FROM customers
WHERE normalized_email IS NOT NULL
GROUP BY normalized_email
HAVING COUNT(*) > 1;
~~~

Nếu backfill tạo ra các giá trị trùng, thêm unique constraint sẽ thất bại. Cần xác định quy tắc xử lý duplicate trước khi migration contract.

Không thêm constraint chỉ để migration thành công bằng cách xóa dữ liệu lỗi một cách tùy tiện. Hãy giữ báo cáo các hàng cần sửa và có quyết định nghiệp vụ cho từng trường hợp.

## 14. Kiểm soát thời gian, giá trị và tính xác định của backfill

Một backfill cần có kết quả lặp lại và giải thích được. Chú ý:

- **Timestamp:** chọn timezone và nguồn thời gian rõ ràng; không trộn local time với UTC.
- **Chuỗi:** xác định trim, Unicode normalization, collation và quy tắc chữ hoa/thường.
- **Tiền tệ:** không dùng floating point cho phép tính tiền; xác định scale và rounding.
- **Enum/status:** có mapping rõ giữa mã cũ và trạng thái mới; không map giá trị không biết thành một trạng thái hợp lệ giả.
- **JSON:** xác định schema version và cách xử lý field thiếu/sai kiểu.
- **ID/foreign key:** kiểm tra uniqueness và orphan trước khi thêm constraint.
- **NULL:** phân biệt dữ liệu thiếu, chưa xử lý và giá trị nghiệp vụ thực sự null.

Nếu công thức backfill phụ thuộc dữ liệu bên ngoài đang thay đổi, hãy snapshot nguồn hoặc lưu version để có thể tái tạo kết quả.

## 15. Quan sát và vận hành backfill

Đừng chạy job lớn mà không có cách biết nó đang tiến triển hay bị kẹt.

Các số liệu nên theo dõi:

- Tổng số hàng dự kiến.
- Số hàng đã xử lý.
- Số hàng còn thiếu giá trị.
- Số hàng không thể chuyển đổi.
- Tốc độ hàng/giây hoặc thời gian mỗi batch.
- Thời gian transaction và lock wait.
- CPU, I/O, log/WAL/redo và replication lag.
- Số lần retry và lỗi theo loại.

Nên log theo batch với checkpoint/range, không log toàn bộ dữ liệu cá nhân hoặc payload nhạy cảm. Có thể thêm chế độ dry-run để đếm số hàng đủ điều kiện và số hàng lỗi trước khi ghi.

### 15.1. Throttle và dừng an toàn

Job backfill nên có khả năng:

- Điều chỉnh batch size.
- Nghỉ giữa các batch nếu database chịu tải cao.
- Tạm dừng và tiếp tục từ checkpoint.
- Giới hạn số retry.
- Dừng khi lỗi vượt ngưỡng.
- Chạy lại một range đã xử lý mà không làm hỏng dữ liệu.

Không dùng batch size cố định cho mọi database và mọi bảng. Đo trên môi trường gần production rồi điều chỉnh.

## 16. Kiểm tra schema cũ và phát hiện drift

Migration history cho biết công cụ migration đã chạy những changeset nào; nó không luôn chứng minh schema vật lý hoàn toàn đúng với kỳ vọng.

Schema drift có thể xuất hiện khi:

- DBA thay đổi thủ công.
- Một script ngoài quy trình thêm hoặc xóa cột.
- Migration chạy một phần trên database không hỗ trợ transactional DDL cho lệnh đó.
- Môi trường staging và production có phiên bản database khác nhau.
- Một hotfix được áp dụng nhưng không ghi thành migration.

Các bước kiểm tra:

1. Kiểm tra lịch sử migration của từng môi trường.
2. So sánh metadata schema thực tế với schema mong đợi.
3. Kiểm tra cột, kiểu, nullable, default, index, constraint và trigger.
4. Chạy query kiểm tra dữ liệu NULL, duplicate và orphan.
5. Kiểm tra SQL thực tế mà mapping Spring Data JDBC phát ra.
6. Ghi mọi thay đổi thủ công thành migration có thể truy vết nếu cần giữ chúng.

Không sửa trực tiếp bảng lịch sử Flyway/Liquibase để che lỗi drift. Hãy dùng quy trình repair/clear/mark phù hợp với công cụ và chỉ sau khi hiểu trạng thái database thực tế.

## 17. Kiểm thử migration và code mapping

Một migration chỉ chạy thành công trên database rỗng chưa chứng minh nó an toàn cho production. Nên kiểm thử ít nhất:

### 17.1. Database mới

- Chạy toàn bộ migration từ đầu.
- Khởi động ứng dụng mới.
- Tạo, đọc, cập nhật và xóa aggregate quan trọng.
- Xác nhận default, constraint và index như dự kiến.

### 17.2. Nâng cấp từ schema cũ

- Tạo database ở version trước migration.
- Nạp dữ liệu đại diện, bao gồm NULL, duplicate và dữ liệu biên.
- Chạy migration mới.
- Chạy backfill.
- Xác minh giá trị chuyển đổi và constraint.
- Khởi động code mới và thực hiện luồng ghi/đọc.

### 17.3. Tương thích khi rolling deployment

- Kiểm tra code cũ có chạy trên schema sau expand không.
- Kiểm tra code mới xử lý được hàng chưa backfill.
- Kiểm tra writer cũ có làm phát sinh hàng thiếu dữ liệu mới không.
- Chỉ thực hiện contract khi mọi writer cũ đã được loại bỏ.

### 17.4. Test trên database gần production

H2 hữu ích cho test nhanh, nhưng không thay thế database production khi cần xác minh:

- DDL lock và transactional DDL.
- Default khi thêm cột.
- Cú pháp update/batch/index.
- Constraint validation.
- Collation, timezone và kiểu dữ liệu.
- Execution plan và hiệu năng backfill.

Dùng Testcontainers hoặc môi trường integration tương ứng nếu migration phụ thuộc semantics riêng của database.

## 18. Ví dụ hoàn chỉnh: tách full_name thành given_name và family_name

Giả sử schema cũ:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL
);
~~~

Mục tiêu là dùng hai cột mới nhưng vẫn triển khai không downtime.

### Bước 1 — Expand

Migration mới thêm cột nullable:

~~~sql
ALTER TABLE customers
ADD COLUMN given_name VARCHAR(100);

ALTER TABLE customers
ADD COLUMN family_name VARCHAR(100);
~~~

Giữ `full_name` để code cũ còn hoạt động.

### Bước 2 — Deploy code tương thích

Phiên bản mới:

- Có thể đọc hai cột mới nếu đã có dữ liệu.
- Fallback sang `full_name` cho hàng chưa backfill.
- Khi tạo hoặc sửa tên, ghi đồng bộ cột cũ và cột mới trong cùng transaction.
- Không giả định mọi tên đều có thể tách chính xác bằng cách lấy từ đầu tiên và phần còn lại.

Quy tắc tách tên cần được chủ sở hữu nghiệp vụ xác nhận vì tên người có thể có nhiều thành phần, thứ tự và quy ước khác nhau.

### Bước 3 — Backfill theo batch

Nếu dữ liệu đã có một quy tắc tách được xác nhận, chạy job theo ID range. Chỉ cập nhật hàng chưa có giá trị mới và lưu checkpoint.

~~~sql
UPDATE customers
SET given_name = :given_name,
    family_name = :family_name
WHERE id = :id
  AND given_name IS NULL
  AND family_name IS NULL;
~~~

Những hàng không thể tách chắc chắn được ghi vào danh sách cần review, không tự đoán.

### Bước 4 — Xác minh

~~~sql
SELECT COUNT(*)
FROM customers
WHERE given_name IS NULL
   OR family_name IS NULL;
~~~

Đếm cả hàng cần review và phân loại chúng. Kiểm tra thêm các hàng có hai cột mới nhưng không khớp nguồn cũ theo quy tắc đã thống nhất.

### Bước 5 — Chuyển read path

Deploy phiên bản đọc `given_name` và `family_name` làm nguồn chuẩn. Giữ fallback trong khoảng tương thích nếu vẫn còn job hoặc instance cũ.

### Bước 6 — Contract

Sau khi xác nhận không còn code dùng `full_name`, tạo migration riêng để xóa cột cũ. Nếu cần rollback ứng dụng, phải hiểu rằng sau khi xóa cột cũ, phiên bản cũ không thể chạy lại an toàn nếu không có migration khôi phục hoặc chiến lược tương thích.

## 19. Checklist triển khai schema migration và backfill

Trước khi triển khai:

- [ ] Xác định database engine và version production.
- [ ] Xác định tất cả writer, reader, job và integration đang dùng bảng.
- [ ] Tạo migration versioned, không sửa migration đã chạy.
- [ ] Kiểm tra tác động DDL, lock, rewrite bảng và replication.
- [ ] Thêm cột mới theo cách tương thích ngược.
- [ ] Xác định giá trị mặc định ở application và database; bảo đảm chúng thống nhất.
- [ ] Kiểm tra INSERT có bỏ cột hay bind NULL.
- [ ] Viết backfill idempotent và có checkpoint.
- [ ] Chia batch và đặt transaction boundary phù hợp.
- [ ] Xử lý writer đang chạy trong thời gian backfill.
- [ ] Kiểm tra NULL, duplicate, orphan và dữ liệu không thể chuyển đổi.
- [ ] Chỉ thêm NOT NULL/unique/foreign key sau khi dữ liệu đạt điều kiện.
- [ ] Kiểm thử schema mới và nâng cấp từ schema cũ.
- [ ] Chỉ xóa cấu trúc cũ sau khi mọi consumer đã chuyển đổi.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Instance cũ lỗi sau khi deploy schema mới | Migration xóa/đổi cột trước khi code cũ ngừng chạy | Dùng expand-migrate-contract và giữ cấu trúc cũ trong giai đoạn chuyển tiếp. |
| Insert mới vi phạm NOT NULL | Code hoặc writer khác không cung cấp cột mới | Thêm nullable trước, cập nhật mọi writer, backfill rồi mới siết constraint. |
| Database DEFAULT không được dùng | SQL INSERT nêu cột và truyền NULL tường minh | Bỏ cột khỏi INSERT hoặc dùng DEFAULT; kiểm tra SQL Spring Data JDBC tạo ra. |
| Hàng lịch sử vẫn NULL sau khi thêm DEFAULT | Giả định sai về hành vi ALTER TABLE của database | Chạy backfill riêng và xác minh trên đúng engine/version. |
| Backfill ghi đè dữ liệu mới | Job cập nhật mọi hàng trong khi ứng dụng vẫn ghi | Dùng predicate như target IS NULL, version check, dual-write hoặc trigger. |
| Job xử lý trùng hoặc bỏ sót hàng | Dùng OFFSET trên bảng thay đổi hoặc checkpoint sai | Dùng keyset theo khóa ổn định và checkpoint commit nhất quán. |
| Backfill làm database chậm | Một transaction lớn, batch quá lớn hoặc thiếu index | Chia batch, throttle, theo dõi lock/I/O và điều chỉnh kế hoạch. |
| Thêm constraint thất bại | Còn NULL, duplicate hoặc orphan | Chạy query kiểm tra và xử lý dữ liệu trước khi thêm constraint. |
| Migration staging chạy nhưng production thất bại | Khác database version, dữ liệu hoặc semantics DDL | Test upgrade từ snapshot dữ liệu gần production và kiểm tra engine/version. |
| Rollback ứng dụng không dùng được schema | Đã contract cấu trúc cũ quá sớm | Trì hoãn contract; chuẩn bị migration khôi phục hoặc forward-fix. |

## 21. Bài tập tự thực hành

**Bài tập 1 — Thêm cột mới.** Thêm `preferred_language` vào bảng customer đang có dữ liệu. Deploy code chấp nhận NULL, backfill giá trị lịch sử và sau đó thêm NOT NULL.

**Bài tập 2 — So sánh DEFAULT và NULL.** Chạy hai câu INSERT: một câu bỏ qua cột có default và một câu truyền NULL tường minh. Quan sát kết quả trên database đang dùng.

**Bài tập 3 — Kiểm tra Spring Data JDBC.** Tạo entity có thuộc tính nullable và database column có default. Lưu object với thuộc tính null, bật log SQL và xác định framework có bỏ cột hay bind NULL.

**Bài tập 4 — Backfill idempotent.** Viết job chuẩn hóa email theo ID range, chỉ cập nhật hàng chưa có normalized value. Chạy job hai lần và xác nhận kết quả không đổi.

**Bài tập 5 — Checkpoint và resume.** Làm job dừng sau một vài batch. Khởi động lại từ checkpoint và xác nhận không bỏ sót hàng.

**Bài tập 6 — Writer đồng thời.** Trong lúc backfill, cập nhật nguồn từ một transaction khác. Thử predicate target IS NULL và version check để tránh ghi đè dữ liệu mới.

**Bài tập 7 — Expand-migrate-contract.** Tạo migration thêm cột mới, deploy code dual-write, backfill, chuyển read path rồi xóa cột cũ bằng migration riêng.

**Bài tập 8 — Constraint.** Backfill một foreign key mới. Viết query tìm orphan và chỉ thêm foreign key constraint sau khi dữ liệu đã hợp lệ.

## 22. Ghi nhớ

Schema migration trong hệ thống đang chạy phải tương thích với các phiên bản ứng dụng và dữ liệu tồn tại. Dùng migration có version, giữ migration đã áp dụng bất biến và triển khai thay đổi phá vỡ tương thích theo ba giai đoạn expand, migrate và contract.

Database DEFAULT chỉ được áp dụng khi INSERT bỏ qua cột hoặc yêu cầu DEFAULT; truyền NULL tường minh không có nghĩa là dùng default. Giá trị mặc định ở domain giúp ứng dụng có object hợp lệ, còn default ở database bảo vệ các writer bỏ qua cột. Hai chính sách phải thống nhất. Khi dùng Spring Data JDBC, hãy kiểm tra SQL được tạo thay vì giả định thuộc tính Java null sẽ khiến cột bị bỏ khỏi INSERT.

Backfill cần công thức xác định, idempotence, batch size phù hợp, transaction ngắn, checkpoint và cách phối hợp với writer đang hoạt động. Xác minh NULL, duplicate, orphan và dữ liệu không thể chuyển đổi trước khi thêm constraint. Chỉ xóa schema cũ khi tất cả instance, job và integration đã chuyển sang cấu trúc mới.

### Tài liệu tham khảo

- [Spring Boot – Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Flyway – Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations)
- [Liquibase – Changesets](https://docs.liquibase.com/concepts/changelogs/changeset.html)
- [PostgreSQL – ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html)
- [MySQL – ALTER TABLE Statement](https://dev.mysql.com/doc/refman/8.4/en/alter-table.html)
