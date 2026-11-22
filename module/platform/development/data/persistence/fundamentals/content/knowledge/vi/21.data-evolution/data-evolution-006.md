# Bổ sung dữ liệu còn thiếu bằng backfill có kiểm soát

Một hệ thống Java đã lưu hàng triệu đơn hàng trước khi bổ sung trường `country_code_normalized` phục vụ tính phí vận chuyển. Các đơn mới có thể ghi trường này ngay, nhưng dữ liệu cũ vẫn chứa `NULL`. Nếu ứng dụng chuyển sang giả định tất cả bản ghi đều đã có mã quốc gia chuẩn, việc tính phí có thể sai hoặc truy vấn gặp lỗi. Chạy một câu `UPDATE` lớn để điền toàn bộ dữ liệu có vẻ đơn giản, nhưng nó có thể giữ khóa lâu, tạo nhiều WAL, làm chậm database, xung đột với các request đang ghi và thất bại giữa chừng.

**Backfill** là quá trình bổ sung hoặc tính lại dữ liệu đã tồn tại nhằm đưa các bản ghi cũ về cấu trúc/ngữ nghĩa mới. **Backfill có kiểm soát** không chỉ là chạy script: nó cần kế hoạch tương thích khi triển khai, giới hạn tải, điều kiện ghi chống ghi đè, tiến độ có thể tiếp tục, đo lường kết quả và phương án dừng/khôi phục.

Bài này thuộc chương **Tiến hóa dữ liệu** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Người học sử dụng kiến thức về Java persistence, schema, truy vấn/chỉ mục, transaction, cô lập, kiểm soát đồng thời và độ bền để xây dựng một quy trình backfill an toàn trong lúc ứng dụng vẫn phục vụ người dùng.

**Nguyên tắc xuyên suốt:** Backfill phải **an toàn khi chạy lại, an toàn khi chạy song song với writer hiện tại, có thể dừng/tiếp tục và chứng minh được dữ liệu sau cùng phù hợp quy tắc miền**. Việc một job chạy hết danh sách ID không tự chứng minh toàn bộ dữ liệu đã đúng.

## 1. Khi nào cần backfill?

Các tình huống thường gặp:

| Thay đổi dữ liệu | Trạng thái ban đầu | Mục tiêu của backfill | Rủi ro đáng chú ý |
| --- | --- | --- | --- |
| Thêm trường bắt buộc | `country_code_normalized` mới là `NULL` trên đơn cũ | Điền từ nguồn dữ liệu đáng tin cậy | Không thể suy ra giá trị ở một số đơn |
| Thay đổi định dạng | Số điện thoại có nhiều kiểu | Chuẩn hóa theo quy tắc đã thống nhất | Mất dấu `+` hoặc mã vùng, ghi sai số |
| Đổi kiểu dữ liệu | Số tiền đang là chuỗi/float | Chuyển sang decimal hoặc đơn vị nhỏ nhất | Làm tròn và đơn vị tiền tệ |
| Thêm dữ liệu dẫn xuất | Tổng tiền đã lưu, thiếu breakdown | Tính lại theo quy tắc nghiệp vụ | Dữ liệu nguồn đã thay đổi sau lúc đọc |
| Tách/gộp bảng | Profile đang trong một bảng cũ | Chuyển nội dung sang cấu trúc mới | Đồng bộ giữa hai cấu trúc trong giai đoạn chuyển tiếp |
| Tạo read model/search index | Nguồn sự thật đã có dữ liệu | Điền projection/index ban đầu | Event mới đến trong lúc backfill |
| Thêm mã định danh chuẩn | Bản ghi cũ chỉ có legacy ID | Bổ sung mapping và khóa tham chiếu | Trùng định danh, tính duy nhất |

Backfill **khác** với cập nhật nghiệp vụ hằng ngày: nó đụng đến lượng lớn dữ liệu lịch sử, nhiều hàng có thể không đáp ứng giả định mới và quá trình phải cùng tồn tại với traffic online.

Backfill cũng **khác schema migration** dù thường đi cùng nhau. Migration có thể thêm cột hoặc constraint; backfill **điền nội dung** của cột/collection. Tạo cột thành công không có nghĩa dữ liệu lịch sử đã được chuyển.

## 2. Mẫu expand → backfill → validate → contract

Một cách tiến hóa an toàn thường chia thành các giai đoạn có thể triển khai độc lập:

~~~mermaid
flowchart TD
    A[Expand: thêm schema mới tương thích] --> B[Deploy writer mới: luôn ghi trường mới]
    B --> C[Backfill dữ liệu cũ theo lô]
    C --> D[Validate: độ phủ, quy tắc và sai lệch]
    D --> E[Deploy reader chuyển sang dữ liệu mới]
    E --> F[Contract: ràng buộc/loại bỏ cơ chế cũ khi đã an toàn]
~~~

**Expand:** thêm trường mới ở trạng thái nullable/optional để phiên bản ứng dụng cũ và mới vẫn hoạt động. Không thêm ngay ràng buộc `NOT NULL` nếu dữ liệu cũ còn thiếu.

**Writer mới:** mọi đường ghi đơn hàng phải cập nhật dữ liệu mới khi tạo hoặc sửa nguồn có liên quan. Đây là bước then chốt để **ngừng phát sinh nợ dữ liệu mới** trong lúc job đang chạy.

**Backfill:** xử lý bản ghi còn thiếu theo từng batch nhỏ, kiểm tra dữ liệu nguồn và điều kiện ghi ở thời điểm cập nhật.

**Validate:** đếm bản ghi thiếu, đối chiếu mẫu, kiểm tra dữ liệu sai/nghi vấn và xác nhận mọi writer đang tuân thủ quy tắc mới.

**Chuyển reader:** chỉ chuyển các use case sang yêu cầu cột mới khi chính sách dữ liệu thiếu đã rõ; có thể cần giai đoạn fallback có kiểm soát.

**Contract:** thêm constraint, bỏ fallback/cột cũ hoặc xóa mã chuyển tiếp sau khi đã chứng minh an toàn. Không nhất thiết phải làm tất cả trong một lần deploy.

### Tại sao phải sửa writer trước?

Nếu backfill điền xong đến ID 1.000.000 nhưng ứng dụng cũ vẫn tạo một đơn `country_code_normalized = NULL` ở ID 1.000.001, việc chuyển reader hoặc thêm `NOT NULL` sẽ thất bại. Với kiến trúc nhiều instance, phải kiểm tra mọi **phiên bản service, job batch, import và consumer** có thể ghi dữ liệu, không chỉ một API.

## 3. Định nghĩa nguồn dữ liệu và quy tắc chuyển đổi

Ví dụ xuyên suốt bài:

~~~text
orders
  id BIGINT
  shipping_country_raw TEXT
  country_code_normalized VARCHAR(2)  -- cột mới
  row_version BIGINT
~~~

Giả định `shipping_country_raw` trên phần lớn bản ghi chứa mã quốc gia dạng hai chữ cái, nhưng có thể có khoảng trắng, chữ thường hoặc dữ liệu không đúng quy ước. Mục tiêu là:

- `" vn "` → `"VN"`;
- `"us"` → `"US"`;
- `NULL`, chuỗi rỗng, `"unknown"` hoặc ký hiệu không hợp lệ → **không đoán bừa**, đưa vào danh sách cần xử lý;
- các mã hai chữ cái chỉ được chấp nhận sau khi kiểm tra với danh sách mã quốc gia được ứng dụng hỗ trợ, không chỉ kiểm tra đúng hai ký tự.

Quy tắc chuyển đổi cần được **đóng phiên bản** và có thể kiểm thử. Nếu ngày mai định nghĩa mapping thay đổi, một batch chạy lại không được tùy ý ghi lại dữ liệu vốn đã được xác nhận theo quy tắc cũ mà không có kế hoạch nâng cấp riêng.

### Câu hỏi trước khi chạy

1. Có **nguồn sự thật** nào đủ để tính giá trị mới cho tất cả bản ghi không?
2. Dữ liệu cũ có mang ngữ nghĩa lịch sử khác hiện tại không? Ví dụ địa chỉ cũ không thể suy chính xác từ profile khách hàng bây giờ.
3. Giá trị mới là **snapshot lịch sử** hay **trường dẫn xuất luôn phải đồng bộ** với nguồn?
4. Có những trường hợp không thể tự động chuyển đổi không, ai phê duyệt sửa?
5. Dữ liệu liên quan đến tiền, quyền truy cập, danh tính hoặc pháp lý có yêu cầu đối soát riêng không?

Nếu không đủ dữ liệu, nên tạo trạng thái `UNKNOWN` có định nghĩa rõ hoặc giữ `NULL` để triage thay vì điền mặc định “cho hết NULL” rồi làm sai nghiệp vụ. **Đạt 100% non-null không đồng nghĩa đạt 100% dữ liệu đúng**.

## 4. Expand schema PostgreSQL trước khi chạy

Ví dụ PostgreSQL, giả định bảng `orders` đã có `id`, `shipping_country_raw` và `row_version`, trong đó mọi writer hiện hữu đều tăng `row_version` khi sửa dữ liệu liên quan:

~~~sql
ALTER TABLE orders
    ADD COLUMN country_code_normalized VARCHAR(2);

-- Ràng buộc này chỉ kiểm tra hình dạng; danh sách mã hợp lệ
-- phải được kiểm tra bằng dữ liệu chuẩn/logic nghiệp vụ.
ALTER TABLE orders
    ADD CONSTRAINT orders_country_code_shape
    CHECK (
        country_code_normalized IS NULL
        OR country_code_normalized ~ '^[A-Z]{2}$'
    ) NOT VALID;
~~~

`NOT VALID` trong PostgreSQL cho phép thêm một số constraint dạng `CHECK`/foreign key mà **không xác thực ngay tất cả hàng cũ**; các ghi mới vẫn phải tuân thủ constraint theo cơ chế của DB. Sau backfill có thể chạy `VALIDATE CONSTRAINT` khi phù hợp. Không đánh đồng `NOT VALID` với “constraint bị tắt”.

**Không thêm ngay `NOT NULL`** nếu còn bản ghi cũ thiếu; đồng thời không tự coi `ALTER TABLE` là hoạt động không khóa. DDL có thể cần khóa metadata hoặc scan, tùy loại thao tác, phiên bản PostgreSQL và tải thực tế. Với bảng lớn, cần kế hoạch migration và quan sát lock wait; có thể dùng `lock_timeout` cho những bước nhạy cảm.

Nếu cần index phục vụ truy vấn hoặc lọc các hàng thiếu, có thể cân nhắc một index từng phần:

~~~sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    orders_missing_country_code_idx
ON orders (id)
WHERE country_code_normalized IS NULL;
~~~

`CREATE INDEX CONCURRENTLY` được thiết kế giảm chặn ghi so với cách tạo index thông thường, nhưng vẫn tốn I/O/CPU và có giới hạn vận hành. Trong PostgreSQL, **không chạy `CREATE INDEX CONCURRENTLY` bên trong transaction block**. Chỉ tạo khi plan và workload cho thấy index có ích; ví dụ quét toàn bộ PK từng batch có thể không cần index này.

## 5. Đổi writer để chặn dữ liệu thiếu phát sinh thêm

Sau expand, ứng dụng mới nên ghi đồng thời trường nguồn và trường chuẩn hóa **trong cùng transaction**. Ví dụ khi người dùng đổi quốc gia giao hàng:

~~~java
String source = input.countryCode();
String normalized = normalizeCountry(source);
if (normalized == null) {
    throw new IllegalArgumentException("Mã quốc gia không hợp lệ");
}

try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE orders " +
        "SET shipping_country_raw = ?, " +
        "country_code_normalized = ?, " +
        "row_version = row_version + 1 " +
        "WHERE id = ? AND row_version = ?")) {
    ps.setString(1, source);
    ps.setString(2, normalized);
    ps.setLong(3, orderId);
    ps.setLong(4, expectedVersion);
    if (ps.executeUpdate() != 1) {
        throw new OptimisticLockException("Order đã thay đổi");
    }
}
~~~

`normalizeCountry` và `OptimisticLockException` trong đoạn trên là các hàm/kiểu do ứng dụng định nghĩa. Trong một service thật, câu SQL là một phần transaction do tầng ứng dụng hoặc transaction manager quản lý.

**Quan trọng:** nếu writer đổi `shipping_country_raw` nhưng không đổi/clear `country_code_normalized`, trường dẫn xuất có thể **sai mà không còn NULL**. Backfill chỉ tìm `country_code_normalized IS NULL` sẽ **không** phát hiện loại lỗi này. Phải bảo đảm mọi writer giữ cặp trường nhất quán, hoặc thiết kế constraint/generated column/trigger khi phù hợp với ngữ nghĩa và hiệu năng.

Nếu có nhiều phiên bản Java đang chạy đồng thời, giai đoạn compatibility có thể cần đọc cả hai trường, nhưng không được chuyển sang bắt buộc trường mới cho tới khi ứng dụng cũ đã ngừng ghi sai.

## 6. Tại sao một UPDATE toàn bảng có thể gây sự cố?

Cách nhìn quá đơn giản:

~~~sql
UPDATE orders
SET country_code_normalized = upper(trim(shipping_country_raw))
WHERE country_code_normalized IS NULL;
~~~

Vấn đề của câu lệnh lớn trên bảng có hàng chục triệu dòng:

- Transaction có thể chạy lâu và giữ các hàng đã cập nhật bị khóa đến commit; writer online phải chờ hoặc phát sinh deadlock.
- Sinh nhiều WAL/redo, tăng I/O, replication lag, áp lực disk, vacuum và chi phí recovery.
- Nếu lỗi gần cuối, rollback lượng lớn thay đổi; lần chạy sau lại làm từ đầu.
- Việc chuyển đổi không kiểm tra mã hợp lệ, có thể ghi các giá trị không có ý nghĩa.
- Nếu source đổi trong khi job chạy, thao tác có thể ghi bản dẫn xuất của dữ liệu không còn mới.
- Job rất khó tạm dừng có kiểm soát vì một transaction đang xử lý nhiều dữ liệu.

Không phải mọi backfill đều cần Java worker: một SQL set-based theo batch là đủ nếu phép chuyển đổi có thể diễn đạt đúng và DB chịu được tải. Điểm quyết định là **kích thước đơn vị commit, tính đúng đắn và khả năng điều tiết**, không phải công cụ viết bằng ngôn ngữ nào.

## 7. Chia lô: batch, keyset và ranh giới commit

Mẫu phổ biến là duyệt theo **khóa ổn định**:

~~~sql
SELECT id, shipping_country_raw, row_version
FROM orders
WHERE id > :lastId
  AND id <= :maxId
ORDER BY id
LIMIT :batchSize;
~~~

Sau khi đọc một batch, worker tính giá trị mới, thực hiện các cập nhật có điều kiện rồi **commit batch**. Tăng `lastId` theo ID cuối **đã duyệt**, không phải chỉ theo số hàng cập nhật thành công.

| Kỹ thuật | Đặc điểm | Lưu ý |
| --- | --- | --- |
| **Một UPDATE toàn bảng** | Ít code, có thể rất hiệu quả trên tập nhỏ | Transaction/lock/WAL lớn nếu khối lượng lớn |
| **OFFSET/LIMIT** | Dễ viết | Offset lớn có thể chậm; hàng bị thêm/xóa dễ làm thay đổi vị trí |
| **Keyset theo ID** | Chi phí tương đối ổn định theo khóa; dễ checkpoint | ID phải có thứ tự ổn định, cần xử lý insert/update đến muộn |
| **Range partition** | Nhiều worker độc lập theo vùng ID/partition | Dễ lệch tải, phải chặn trùng và quan sát từng vùng |
| **FOR UPDATE SKIP LOCKED** | Nhiều worker claim hàng cạnh tranh ít chặn nhau | Phải có giao thức claim/commit và tránh liên tục bỏ qua hàng bị khóa |

**Batch size** là giới hạn số hàng **quét/xử lý** trong một transaction, không tự là giới hạn thời gian. Nếu một hàng rất nặng hoặc DB đang chịu lock wait, batch 100 vẫn có thể chạy lâu. Cần đo **thời gian mỗi transaction**, lock wait, WAL và ảnh hưởng đến request thật.

Không tăng batch size chỉ để “cho nhanh” khi database đang trễ; mục tiêu của backfill online thường là **tiến độ ổn định trong ngân sách tải**, không phải sử dụng hết tài nguyên DB.

### Chốt high-water mark

Nếu liên tục có insert, một vòng quét `WHERE id > lastId` có thể không bao giờ bắt kịp. Có thể chốt:

~~~sql
SELECT COALESCE(MAX(id), 0) AS max_id
FROM orders;
~~~

Job duyệt `id <= max_id` của thời điểm bắt đầu; **writer mới** chịu trách nhiệm điền cột mới cho bản ghi được tạo sau đó. Cần lưu `max_id` cùng checkpoint. Đây là mốc xử lý, **không** phải snapshot nguyên tử của toàn bộ dữ liệu tại một thời điểm nếu các hàng vẫn có thể thay đổi. Cuối job cần chạy validation/reconciliation sweep để tìm trường hợp thiếu hoặc lệch còn sót.

## 8. Điều kiện ghi: không ghi đè dữ liệu do người dùng vừa sửa

Race nguy hiểm:

~~~mermaid
sequenceDiagram
    participant B as Backfill worker
    participant DB as Database
    participant A as API writer
    B->>DB: SELECT id=42 raw='vn', version=7
    DB-->>B: Dữ liệu cũ
    A->>DB: UPDATE raw='us', normalized='US', version=8
    A->>DB: COMMIT
    B->>DB: UPDATE normalized='VN' WHERE id=42
    Note over DB: Sai nếu UPDATE không có điều kiện nguồn/version
~~~

Worker không được dùng một `UPDATE ... WHERE id = ?` mù. Hãy **compare-and-set (CAS)** với điều kiện cột còn thiếu và phiên bản/source chưa đổi:

~~~sql
UPDATE orders
SET country_code_normalized = :normalized,
    row_version = row_version + 1
WHERE id = :id
  AND country_code_normalized IS NULL
  AND row_version = :versionObserved
  AND shipping_country_raw IS NOT DISTINCT FROM :rawObserved;
~~~

Trong PostgreSQL, `IS NOT DISTINCT FROM` là phép so sánh xem cả hai bên có cùng giá trị, **bao gồm trường hợp cả hai là NULL**. Với dữ liệu raw hợp lệ không NULL, có thể dùng `=`; cú pháp phía trên làm ý định rõ khi chuyển đổi nullable.

Nếu affected rows = `1`, worker đã cập nhật bản ghi thỏa điều kiện ở thời điểm câu SQL thực thi. Nếu = `0`, **không tự coi là lỗi nghiêm trọng**: có thể request online đã sửa hàng, người khác đã backfill hoặc bản ghi đã bị xóa. Worker ghi metric `conflict/skipped`; reconciliation pass đánh giá lại sau.

Trong isolation/engine khác, DB có thể báo lỗi serialization/deadlock thay vì trả 0 dòng; retry **transaction mới** theo chính sách, không chỉ lặp câu lệnh trên trạng thái cũ.

**Lưu ý với ORM `@Version`:** nếu writer dùng JPA optimistic locking dựa vào `row_version`, câu SQL native của backfill phải tuân theo chính sách tăng version. Nếu không, entity đã được đọc trước đó có thể ghi đè dữ liệu backfill. Việc tăng version khi backfill cũng có thể tạo thêm conflict ở traffic online; cần tính toán trade-off và theo dõi.

## 9. Tính lũy đẳng (idempotent) và chạy lại sau crash

Một backfill an toàn khi chạy lại cần đạt tính chất:

> Nếu batch đã commit nhưng worker crash trước khi ghi tiến độ, chạy lại batch đó không làm đổi dữ liệu đã đúng thành sai hoặc nhân đôi tác động.

Ví dụ điều kiện `country_code_normalized IS NULL` khiến một hàng đã cập nhật thành `"VN"` không bị viết lại vô hạn. Nếu cần tính lại những hàng có giá trị sai, phải định nghĩa một **correction job** riêng có điều kiện/phiên bản rõ, không tùy ý bỏ điều kiện.

Với bài toán cộng dồn, cần tránh:

~~~sql
-- Nguy hiểm nếu chạy lại do crash/retry:
UPDATE accounts SET reward_points = reward_points + 100
WHERE customer_id = :id;
~~~

Thay vào đó, dùng một giá trị **đích xác định** hoặc một marker/idempotency key trong **cùng transaction** với phép cộng:

~~~sql
-- Ví dụ: trạng thái mong muốn được tính từ nguồn có thẩm quyền.
UPDATE accounts
SET reward_points_v2 = :derivedTotal
WHERE customer_id = :id
  AND reward_points_v2 IS NULL;
~~~

Nếu tính toán phụ thuộc nhiều bảng đang đổi, phải chọn cơ chế snapshot/version/transaction phù hợp. **Idempotency của câu UPDATE đơn** không tự bảo vệ kết quả tính từ một snapshot sai.

### Checkpoint là tối ưu tiếp tục, không phải bằng chứng hoàn tất

Một bảng tiến độ:

~~~sql
CREATE TABLE backfill_progress (
    job_name   VARCHAR(120) PRIMARY KEY,
    last_id    BIGINT NOT NULL DEFAULT 0,
    max_id     BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (last_id >= 0),
    CHECK (max_id >= 0),
    CHECK (last_id <= max_id)
);
~~~

Khởi tạo một lần, chốt `max_id` tại thời điểm bắt đầu:

~~~sql
INSERT INTO backfill_progress(job_name, last_id, max_id)
SELECT 'orders-country-v1', 0, COALESCE(MAX(id), 0)
FROM orders
ON CONFLICT (job_name) DO NOTHING;
~~~

Nếu lưu `last_id` **cùng transaction** với các cập nhật của batch thì khi commit, tiến độ và dữ liệu thuộc batch cùng có hiệu lực; nếu rollback, cả hai không tiến. Nếu lưu checkpoint **sau commit ở một transaction khác**, việc crash giữa hai lần commit có thể khiến batch được chạy lại — do đó thao tác ghi phải idempotent.

Trong cả hai cách, việc `last_id = max_id` chỉ chứng minh **đã duyệt tới mốc**, không chứng minh mọi hàng đã chuyển thành công, nhất là các hàng có nguồn không hợp lệ hoặc bị CAS conflict.

## 10. Ví dụ Java/JDBC: worker quét theo keyset, commit mỗi batch

Ví dụ dưới đây triển khai một vòng backfill trên PostgreSQL. Nó tập trung vào transaction và concurrency, **không** phải một framework job scheduling hoàn chỉnh.

Giả định:

- `orders(id BIGINT PRIMARY KEY, shipping_country_raw TEXT, country_code_normalized VARCHAR(2), row_version BIGINT NOT NULL)`;
- `backfill_progress` đã được khởi tạo theo phần 9;
- mọi API writer liên quan đều tăng `row_version` và ghi/clear cột mới đúng cách;
- job chỉ xử lý các mã quốc gia hợp lệ theo danh sách cho phép ở ví dụ; dữ liệu không hợp lệ cần triage;
- chạy với transaction isolation `READ COMMITTED` để câu cập nhật kiểm tra điều kiện hiện tại; adapter dùng cùng một connection cho các bước trong batch.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import javax.sql.DataSource;

public final class CountryBackfillWorker {
    private static final String JOB = "orders-country-v1";
    private static final Set<String> SUPPORTED = Set.of("VN", "US", "SG");
    private final DataSource dataSource;

    private record Progress(long lastId, long maxId) {}
    private record Candidate(
            long id, String raw, String normalized, long rowVersion) {}

    public CountryBackfillWorker(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    // Trả số hàng đã quét. Trả 0 khi đã hết phạm vi id <= maxId.
    public int processBatch(int limit) throws SQLException {
        if (limit <= 0 || limit > 500) {
            throw new IllegalArgumentException("limit phải từ 1 đến 500");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setTransactionIsolation(
                    Connection.TRANSACTION_READ_COMMITTED);
            connection.setAutoCommit(false);
            try {
                // Khóa dòng checkpoint để không có hai worker cùng
                // tiến con trỏ của đúng job này trong một thời điểm.
                Progress progress = lockProgress(connection);
                if (progress.lastId() >= progress.maxId()) {
                    connection.commit();
                    return 0;
                }

                List<Candidate> batch = loadBatch(
                        connection, progress.lastId(),
                        progress.maxId(), limit);
                if (batch.isEmpty()) {
                    saveProgress(connection, progress.maxId());
                    connection.commit();
                    return 0;
                }

                long lastSeenId = progress.lastId();
                for (Candidate row : batch) {
                    lastSeenId = row.id();
                    if (row.normalized() != null) {
                        continue; // Đã có dữ liệu ở cột mới.
                    }
                    String value = normalizeCountry(row.raw());
                    if (value == null) {
                        // Ghi nhận metric/quarantine ở hệ thống thực tế.
                        // Không đoán mã cho dữ liệu thiếu/không hợp lệ.
                        continue;
                    }
                    // 0 dòng = đã đổi do concurrent writer hoặc
                    // đã được backfill; reconciliation sẽ quét lại.
                    updateIfUnchanged(connection, row, value);
                }

                // Checkpoint và các UPDATE thuộc cùng transaction.
                saveProgress(connection, lastSeenId);
                connection.commit();
                return batch.size();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

    private Progress lockProgress(Connection c) throws SQLException {
        String sql = "SELECT last_id, max_id FROM backfill_progress " +
                "WHERE job_name = ? FOR UPDATE";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setString(1, JOB);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new IllegalStateException(
                            "Chưa khởi tạo checkpoint cho " + JOB);
                }
                return new Progress(
                        rs.getLong("last_id"), rs.getLong("max_id"));
            }
        }
    }

    private List<Candidate> loadBatch(
            Connection c, long lastId, long maxId, int limit)
            throws SQLException {
        String sql = "SELECT id, shipping_country_raw, " +
                "country_code_normalized, row_version FROM orders " +
                "WHERE id > ? AND id <= ? ORDER BY id LIMIT ?";
        List<Candidate> results = new ArrayList<>();
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, lastId);
            ps.setLong(2, maxId);
            ps.setInt(3, limit);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    results.add(new Candidate(
                            rs.getLong("id"),
                            rs.getString("shipping_country_raw"),
                            rs.getString("country_code_normalized"),
                            rs.getLong("row_version")));
                }
            }
        }
        return results;
    }

    private int updateIfUnchanged(
            Connection c, Candidate row, String value)
            throws SQLException {
        String sql = "UPDATE orders " +
                "SET country_code_normalized = ?, " +
                "row_version = row_version + 1 " +
                "WHERE id = ? AND row_version = ? " +
                "AND country_code_normalized IS NULL " +
                "AND shipping_country_raw IS NOT DISTINCT FROM ?";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setString(1, value);
            ps.setLong(2, row.id());
            ps.setLong(3, row.rowVersion());
            ps.setString(4, row.raw()); // Chỉ gọi với raw hợp lệ.
            return ps.executeUpdate();
        }
    }

    private void saveProgress(Connection c, long lastId)
            throws SQLException {
        String sql = "UPDATE backfill_progress " +
                "SET last_id = ?, updated_at = CURRENT_TIMESTAMP " +
                "WHERE job_name = ?";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, lastId);
            ps.setString(2, JOB);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Không lưu được checkpoint");
            }
        }
    }

    private static String normalizeCountry(String raw) {
        if (raw == null) {
            return null;
        }
        String code = raw.strip().toUpperCase(Locale.ROOT);
        return SUPPORTED.contains(code) ? code : null;
    }
}
~~~

Một bộ điều phối riêng (scheduler, worker process hoặc lệnh vận hành có kiểm soát) có thể gọi `processBatch(200)` lặp lại, giới hạn tốc độ và dừng khi trả 0. Mẫu trên **không tự chạy nền**, không thực thi trên dữ liệu thực và không thay thế quy trình phê duyệt thay đổi production.

### Điều gì được bảo vệ trong đoạn mã?

1. **Một transaction cho mỗi batch:** lỗi giữa chừng rollback toàn bộ các cập nhật và checkpoint của batch.
2. **Khóa checkpoint `FOR UPDATE`:** nếu hai worker cùng chạy một `JOB`, chỉ một worker tiến con trỏ tại một thời điểm; worker kia có thể phải đợi. Đây là cách đơn giản cho một job, **không phải kiến trúc parallel backfill tối ưu**.
3. **Keyset theo ID:** không dùng offset tăng dần. Batch đọc cả hàng đã có dữ liệu mới để bảo đảm con trỏ tiến theo thứ tự ID ổn định.
4. **CAS trước khi ghi:** nếu API thay đổi hàng sau khi worker đọc, `row_version` hoặc cột nguồn không khớp và UPDATE không thành công; worker không ghi đè người dùng.
5. **Bỏ qua dữ liệu không đủ điều kiện:** nguồn sai được giữ nguyên để triage, không gán bừa.
6. **Idempotency:** chạy lại không thay những hàng đã có `country_code_normalized`; chưa có giá trị thì chỉ ghi khi dữ liệu nguồn vẫn như lúc đọc.

### Giới hạn của ví dụ

- `SUPPORTED` chỉ liệt kê ba quốc gia để minh họa, **không phải danh sách ISO đầy đủ**. Trong ứng dụng thật cần dùng danh mục mã được quản lý và kiểm thử.
- Job chưa ghi chi tiết từng hàng lỗi vào bảng quarantine, chưa có backoff/rate limiter, chưa phân loại deadlock/serialization, chưa có kill switch và chưa hỗ trợ sharding. Các phần sau giải thích yêu cầu vận hành.
- Khi một hàng bị CAS conflict hoặc dữ liệu không hợp lệ, con trỏ vẫn tiến. **Bắt buộc có vòng reconciliation** sau job để kiểm tra các hàng bỏ qua.
- `row_version` tăng do cập nhật trường dẫn xuất có thể khiến request JPA optimistic locking gặp conflict; cần xem xét và đo tải.
- Checkpoint lock được giữ trong suốt batch. Nếu batch lâu, worker khác cùng job bị chờ; không nên giữ lock qua HTTP hoặc I/O ngoài DB.
- Một lỗi commit do mất kết nối có thể có kết quả **không rõ**; sau đó đọc lại checkpoint và dữ liệu bằng kết nối mới trước khi tiếp tục. Không suy từ ngoại lệ rằng DB chắc chắn rollback.

## 11. SQL set-based theo batch khi phép chuyển đổi nằm trong DB

Không phải lúc nào cũng cần tải dữ liệu sang Java. Nếu quy tắc chuyển đổi đơn giản và được DB hỗ trợ, có thể cập nhật theo ID range hoặc một tập ID giới hạn:

~~~sql
WITH candidates AS (
    SELECT id
    FROM orders
    WHERE country_code_normalized IS NULL
      AND shipping_country_raw IS NOT NULL
      AND upper(btrim(shipping_country_raw)) IN ('VN', 'US', 'SG')
    ORDER BY id
    LIMIT 200
    FOR UPDATE SKIP LOCKED
)
UPDATE orders o
SET country_code_normalized = upper(btrim(o.shipping_country_raw)),
    row_version = o.row_version + 1
FROM candidates c
WHERE o.id = c.id
  AND o.country_code_normalized IS NULL
RETURNING o.id;
~~~

Đây là một ví dụ PostgreSQL, chạy trong **transaction ngắn riêng của mỗi batch**. `FOR UPDATE SKIP LOCKED` giúp tránh chờ hàng đang bị transaction khác giữ, phù hợp với nhiều worker khi thiết kế được cơ chế quét/hoàn tất. Tuy nhiên:

- Không dùng `SKIP LOCKED` rồi kết luận “hết hàng” nếu một số hàng vẫn đang bị khóa hoặc còn dữ liệu invalid; cần reconciliation.
- Mỗi transaction sau có thể quét lại các hàng không đủ điều kiện; chú ý index/query plan.
- Nếu dùng CTE với `FOR UPDATE`, DB sẽ khóa các hàng đã chọn trong thời gian transaction. Không nên giữ transaction mở khi sleep hoặc gọi API.
- Nếu writer khác không tăng `row_version` hoặc thay đổi quy tắc giữa chừng, vẫn có nguy cơ dữ liệu dẫn xuất sai.
- Lệnh trên dùng chính giá trị nguồn của hàng tại thời điểm UPDATE; với thao tác một hàng PostgreSQL bảo đảm điều kiện khóa/ghi theo semantics tương ứng, nhưng **không** bảo vệ một tính toán phụ thuộc nhiều bảng không thuộc cùng điều kiện transaction.

Chọn SQL set-based nếu hợp logic; chọn Java nếu chuyển đổi phức tạp hoặc cần thư viện chuẩn hóa miền, nhưng cả hai phải có cùng yêu cầu **đúng đắn và giới hạn tải**.

## 12. Điều tiết tốc độ và giới hạn tác động lên production

Mục tiêu không phải “chạy xong nhanh nhất có thể” mà là **hoàn thành trong cửa sổ vận hành mà không phá SLO của ứng dụng**.

Các nút điều chỉnh:

| Tham số | Tác dụng | Rủi ro khi đặt quá cao |
| --- | --- | --- |
| `batchSize` | Số hàng duyệt/ghi mỗi commit | Transaction dài, nhiều lock/WAL |
| `maxWorkers` | Số batch chạy đồng thời | Hot rows, pool/CPU/I/O contention |
| `sleepBetweenBatches` | Giảm áp lực trung bình | Backfill kéo dài nhưng ổn định hơn |
| `statement_timeout` | Chặn query chạy quá lâu | Batch rollback thường xuyên nếu đặt quá thấp |
| `lock_timeout` | Tránh chờ khóa quá lâu | Nhiều batch cần retry khi đang bận |
| `connection pool quota` | Giới hạn tài nguyên job | Worker chờ pool, ảnh hưởng latency của chính job |
| `max WAL/replica lag` | Điểm tạm dừng bảo vệ replication | Cần quan sát từ DB/monitoring |

Ví dụ chính sách khởi đầu **chỉ để thử nghiệm, không phải mặc định chung**:

~~~text
batchSize = 200
maxWorkers = 1
sleepBetweenBatches = 100-300 ms có jitter
pause nếu p99 latency ứng dụng vượt ngân sách
pause nếu replication lag hoặc disk/WAL vượt ngưỡng vận hành
~~~

Đo latency và lock wait thực tế rồi tăng tốc từ từ. Với hàng lớn hoặc index phức tạp, 200 hàng cũng có thể là quá nhiều. Khi job đang chạy, phải có **kill switch** để dừng nhận batch mới, không kill bừa một transaction quan trọng đang ở thời điểm commit mà không hiểu kết quả.

## 13. Xử lý lỗi, retry và checkpoint sau lỗi

Một batch có thể gặp:

- **Lock timeout/deadlock:** transaction bị hủy, có thể retry **toàn batch** trong transaction mới với backoff.
- **Serialization failure:** đọc lại tiến độ và dữ liệu trong transaction mới, không cố dùng trạng thái cũ.
- **Mất kết nối trước khi gửi ghi:** có thể retry theo hợp đồng; vẫn phải kiểm tra có lệnh nào đã gửi không.
- **Mất kết nối ở commit:** kết quả chưa rõ, **đọc lại checkpoint và bản ghi đã ghi** bằng connection mới trước khi quyết định.
- **Data validation failure:** không retry vô hạn; ghi nhận record vào danh sách cần triage hoặc sửa quy tắc/chất lượng nguồn.
- **Disk đầy/WAL tăng mạnh/replica chậm:** tạm dừng job và xử lý năng lực hạ tầng, không tăng retry.

Một thuật toán retry đúng hướng:

~~~text
for attempt in 1..maxAttempts:
    begin new transaction
    lock/read checkpoint
    load current rows
    transform and conditional update
    save checkpoint in same transaction
    commit

    on transient conflict/deadlock:
        rollback if possible
        backoff + jitter
        retry with NEW transaction and fresh reads

    on unknown commit outcome:
        reconnect and inspect persisted checkpoint/data
        continue from persisted state, never assume rollback

    on invalid source:
        record for triage; move on according to policy
~~~

**Không retry cả job vô hạn** khi lỗi do schema mismatch, quyền DB, dữ liệu không hợp lệ hoặc tài nguyên hạ tầng cạn. Việc phân loại lỗi JDBC theo SQLState/vendor code cần gắn với database cụ thể; không chỉ tìm chuỗi “timeout” trong message.

## 14. Dữ liệu nguồn có thể đổi trong lúc backfill

Có ba nhóm yêu cầu khác nhau:

1. **Trường dẫn xuất từ chính hàng đó**, như `country_code_normalized` từ `shipping_country_raw`. CAS trên `row_version`/source thường đủ để tránh ghi dữ liệu từ snapshot cũ.
2. **Trường dẫn xuất từ nhiều bảng**, như tổng tiền đơn từ `order_lines`, thuế và khuyến mãi. Cần snapshot/transaction phù hợp hoặc một version của aggregate, vì một hàng có thể đổi giữa các lần đọc.
3. **Trường lấy từ hệ thống khác**, như enrichment địa chỉ từ external API. Kết quả có thể chậm, lỗi hoặc thay đổi giữa lúc xử lý; phải có request ID, giới hạn tải, cache phiên bản nguồn, retry và quy tắc không ghi đè.

Ví dụ nguy hiểm:

~~~text
Backfill đọc order_lines của order #42 tại T1
API thay đổi quantity của order #42 và commit tại T2
Backfill ghi order.total_v2 từ số lượng cũ tại T3
~~~

Nếu chỉ kiểm tra `order.id` mà không có aggregate version hoặc transaction phù hợp, dữ liệu vẫn sai. Một cách là duy trì `order_version` tăng khi **bất kỳ phần dữ liệu liên quan tới tổng tiền** thay đổi, đọc snapshot cùng version và CAS lúc ghi. Một cách khác là tính/ghi từ database trong transaction và khóa/ràng buộc phù hợp. **Không dùng isolation level như một câu thần chú**: cần chỉ rõ bất biến, nguồn dữ liệu nào được đồng bộ và điều kiện ghi.

### Concurrent delete, insert và reparent

- Hàng bị xóa sau khi worker đọc: `UPDATE` trả 0; kiểm tra lại theo chính sách.
- Hàng mới xuất hiện với ID **lớn hơn high-water mark**: writer mới phải tự điền cột; validation phát hiện nếu không.
- Import dữ liệu cũ với ID **thấp hơn cursor đã đi qua**: một vòng keyset không tự quay lại; phải có reconciliation sweep hoặc policy chặn kiểu import đó.
- Khóa định danh bị tái sử dụng: cần generation/version hoặc chính sách ID ổn định, tránh dữ liệu bị gán nhầm thực thể.

## 15. Reconciliation pass: hoàn tất phải chứng minh bằng dữ liệu

Sau khi worker báo đã đến `max_id`, phải kiểm tra **toàn bộ phạm vi cần chuyển đổi**, không chỉ các hàng job đã cập nhật:

~~~sql
-- Số hàng vẫn thiếu giá trị mới.
SELECT COUNT(*) AS missing_count
FROM orders
WHERE country_code_normalized IS NULL;

-- Trường hợp source hợp lệ về mã được hỗ trợ
-- nhưng target vẫn NULL: có thể retry/reconciliation.
SELECT COUNT(*) AS retryable_missing
FROM orders
WHERE country_code_normalized IS NULL
  AND upper(btrim(shipping_country_raw)) IN ('VN', 'US', 'SG');

-- Hàng đã có giá trị nhưng không khớp source hiện tại.
SELECT id, shipping_country_raw, country_code_normalized
FROM orders
WHERE country_code_normalized IS NOT NULL
  AND upper(btrim(shipping_country_raw)) IN ('VN', 'US', 'SG')
  AND country_code_normalized
      IS DISTINCT FROM upper(btrim(shipping_country_raw))
ORDER BY id
LIMIT 100;
~~~

**Lưu ý:** `upper(btrim(NULL))` là `NULL`; SQL cần tách rõ “source không hợp lệ/NULL” khỏi “target thiếu vì chưa chạy”. Truy vấn toàn bảng có thể đắt, nên bố trí thời điểm đo, index hoặc thực hiện kiểm tra theo partition/sampling trước, nhưng **không thay kiểm chứng cuối cùng bằng ước lượng mẫu** nếu chuẩn chất lượng đòi kiểm tra toàn bộ.

Những nhóm cần triage:

| Nhóm | Ví dụ | Hành động |
| --- | --- | --- |
| **Đúng và đã điền** | `raw=' vn '`, `normalized='VN'` | Không sửa thêm |
| **Thiếu nhưng có thể tính** | `raw='SG'`, `normalized=NULL` | Reconciliation backfill lại có CAS |
| **Thiếu và nguồn không hợp lệ** | `raw='unknown'` | Tìm nguồn khác/duyệt thủ công, không đoán |
| **Có giá trị nhưng sai** | `raw='US'`, `normalized='VN'` | Điều tra writer/race; sửa bằng job kiểm soát riêng |
| **Nguồn mới được thêm sau mốc quét** | `id > max_id` và target thiếu | Sửa writer, chạy sweep |
| **Đã xóa hoặc ẩn** | Bản ghi không còn cần chuyển đổi | Áp dụng đúng chính sách lưu trữ/xóa |

Có thể chạy **nhiều pass**: pass đầu điền dữ liệu rõ ràng, pass sau xử lý conflict hoặc dữ liệu newly arrived, pass cuối xác minh completeness. Một pass được checkpoint đầy đủ không phải chứng nhận kết thúc migration.

## 16. Validation và ràng buộc schema sau backfill

Khi dữ liệu đã đạt điều kiện, có thể nâng ràng buộc theo từng bước:

~~~sql
-- Kiểm tra lại constraint hình dạng đã thêm theo NOT VALID.
ALTER TABLE orders
    VALIDATE CONSTRAINT orders_country_code_shape;

-- Chỉ áp dụng khi đã chắc chắn không còn NULL
-- trong phạm vi cần bắt buộc và mọi writer đều tuân thủ.
ALTER TABLE orders
    ALTER COLUMN country_code_normalized SET NOT NULL;
~~~

**Thận trọng:** `SET NOT NULL` có thể cần quét bảng/khóa tùy PostgreSQL version và constraint có sẵn; lên lịch riêng, đo trên staging tương đương và dùng migration có kiểm soát. Một số cách tối ưu dựa trên `CHECK ... IS NOT NULL` đã validate có thể giúp giảm scan trong các phiên bản/cấu hình hỗ trợ, nhưng không nên giả định mọi phiên bản DB giống nhau.

Thêm constraint quá sớm có thể gây lỗi ghi ở các instance ứng dụng chưa được triển khai đầy đủ. Ngược lại, giữ hai cách ghi cũ/mới vô hạn tạo nợ kỹ thuật. **Contract phase** chỉ bắt đầu khi writer, backfill, validation và kế hoạch rollback đều sẵn sàng.

Ngoài `NOT NULL`, nếu chuyển dữ liệu đòi hỏi tính duy nhất, có thể cần thêm unique constraint/index sau khi loại bỏ duplicate. Không nên dùng một giá trị mặc định giống nhau cho mọi hàng để “làm sạch NULL” khi uniqueness có ý nghĩa nghiệp vụ.

## 17. Triển khai thay đổi ứng dụng Java an toàn

Một trình tự release minh họa:

| Pha | Database | Writer Java | Reader Java | Backfill |
| --- | --- | --- | --- | --- |
| **A. Hiện trạng** | Chỉ dữ liệu cũ | Ghi trường cũ | Đọc trường cũ | Chưa chạy |
| **B. Expand** | Thêm cột nullable | Vẫn tương thích | Vẫn đọc trường cũ | Chưa chạy |
| **C. Dual write nội bộ một DB** | Cột mới tồn tại | Ghi cả hai trường trong cùng transaction | Có thể fallback từ trường cũ | Bắt đầu sau khi xác nhận writer đã triển khai |
| **D. Backfill** | Cột cũ và mới | Tiếp tục ghi đúng cả hai | Chịu dữ liệu mới còn thiếu theo policy | Batch + checkpoint + rate limit |
| **E. Verify / switch read** | Dữ liệu đầy đủ và đã đối soát | Duy trì ghi cột mới | Đọc cột mới là nguồn được ưu tiên | Reconciliation |
| **F. Contract** | Constraint và bỏ schema cũ nếu phù hợp | Chỉ ghi mô hình mới | Chỉ đọc mô hình mới | Job đã dừng |

Ở giai đoạn C, “dual write” cả hai cột **trong một transaction cùng database** có thể nguyên tử. Nếu chuyển dữ liệu từ PostgreSQL sang một kho khác, hai hệ có commit độc lập: cần thiết kế **outbox/CDC, consumer idempotent, ordering và reconciliation**; không thể coi hai lời gọi ghi là atomically coordinated chỉ vì nằm trong cùng phương thức Java.

Nếu dữ liệu cũ là một phần của hợp đồng API, cần lên kế hoạch tương thích nhiều phiên bản client, không chỉ schema DB.

### Feature flag và rollback

Nên có flag riêng cho:

- Có ghi trường mới hay không (chỉ tắt khi đã đánh giá hệ quả dữ liệu phát sinh).
- Reader có ưu tiên trường mới hay còn fallback.
- Backfill worker có được nhận batch mới không.

Rollback ứng dụng từ reader mới về reader cũ thường có thể làm nhanh khi schema cũ còn tồn tại. Nhưng **rollback dữ liệu backfill không đơn giản là chạy `UPDATE field = NULL`**, vì field mới có thể đã được sử dụng bởi bản ghi mới và các writer đã ghi giá trị hợp lệ. Hãy ưu tiên migration **tiến lên**, dùng backup/restore hoặc correction job khi cần, tránh xóa hàng loạt giá trị tốt.

## 18. Backfill trên nhiều database, shard hoặc search index

Khi phạm vi không nằm trong một DB:

- **Sharding:** checkpoint và high-water mark theo từng shard/partition; giới hạn tải theo shard để tránh hot spot, tránh dùng một cursor toàn cục giả định thứ tự tuyệt đối.
- **Multi-tenant:** tách tiến độ theo tenant hoặc nhóm tenant; áp dụng isolation/quyền truy cập và không trộn dữ liệu tenant trong cache/checkpoint.
- **Document store:** dùng bulk update hoặc cursor có checkpoint phù hợp; kiểm tra atomicity theo document và CAS/etag/version.
- **Search index/read model:** full backfill có thể mất nhiều giờ, trong lúc dữ liệu mới vẫn thay đổi. Cần thiết kế thứ tự snapshot + change stream/outbox/CDC, checkpoint theo offset/version và đổi alias chỉ sau validation.
- **External enrichment:** quản lý quota/429, timeout, rate limit, dữ liệu cá nhân và sự chấp thuận dùng nguồn; lưu trạng thái `PENDING/FAILED/VERIFIED` để đối soát.

Ví dụ nếu đang lập một search index mới: chỉ quét toàn bộ database rồi chuyển đọc sang index **chưa chắc đã đúng**, vì các cập nhật xảy ra sau khi hàng đó được quét nhưng trước khi index sẵn sàng có thể bị bỏ sót. Cần ghi nhận hoặc tái phát luồng thay đổi trong thời gian backfill và giải quyết **thứ tự event/version** trước khi switch traffic.

## 19. Quan sát: đo tiến độ, ảnh hưởng và chất lượng

Không nên đánh giá job bằng log “processed 1 million rows” rồi kết luận thành công. Một dashboard tối thiểu:

| Chỉ số | Ý nghĩa |
| --- | --- |
| `backfill_scanned_rows_total` | Đã duyệt bao nhiêu hàng |
| `backfill_updated_rows_total` | Bao nhiêu hàng thực sự cập nhật |
| `backfill_skipped_existing_total` | Bao nhiêu hàng đã có target |
| `backfill_invalid_source_total` | Bao nhiêu hàng không thể tính đúng |
| `backfill_conflict_total` | Số lần CAS không khớp vì dữ liệu thay đổi |
| `backfill_retry_total` | Retry do deadlock/serialization/timeout |
| `backfill_batch_duration` p95/p99 | Transaction có giữ tài nguyên quá lâu không |
| `backfill_checkpoint_last_id` / `max_id` | Tiến độ duyệt của từng job/shard |
| `backfill_missing_count` | Số hàng còn thiếu sau reconciliation |
| `backfill_mismatch_count` | Số hàng có giá trị dẫn xuất khác nguồn |
| `db_lock_wait`, `wal_rate`, `replica_lag` | Ảnh hưởng của backfill lên hạ tầng |
| Latency/error rate API production | Job có làm hỏng SLO người dùng không |

Tiến độ tính theo `last_id / max_id` là **ước lượng vị trí khóa**, không chính xác là phần trăm hàng đã xử lý khi ID có khoảng trống lớn. Nên kết hợp số hàng đã duyệt, số hàng còn thiếu, tốc độ và chất lượng.

Đừng dùng raw order ID, email, tenant ID hay tên cá nhân làm label metric cardinality cao. Log lỗi cần có job name, checkpoint, loại lỗi, batch ID và correlation ID, nhưng không ghi dữ liệu nhạy cảm không cần thiết.

## 20. Kiểm thử trước khi chạy trên dữ liệu thật

| Trường hợp | Kỳ vọng |
| --- | --- |
| Cột mới NULL, source hợp lệ | Điền giá trị chuẩn và tăng revision đúng quy tắc |
| Cột mới đã có giá trị | Không ghi đè khi chỉ backfill dữ liệu thiếu |
| Source trống/không hợp lệ | Bỏ qua/triage, không tự tạo mã giả |
| Job chạy lại cùng batch | Không nhân đôi side effect và không làm sai dữ liệu |
| Crash trước commit batch | Dữ liệu/tiến độ cùng rollback |
| Crash sau commit batch | Checkpoint tồn tại; restart không ghi lại sai |
| Source đổi sau SELECT trước UPDATE | CAS trả 0 hoặc xung đột; không ghi giá trị cũ |
| Hai worker cùng job | Checkpoint lock/lease ngăn tiến độ chồng chéo theo thiết kế |
| Một hàng bị xóa trong lúc chạy | Bị bỏ qua, không tái tạo dữ liệu đã xóa |
| Có insert mới sau high-water mark | Writer mới điền đúng; validation kiểm tra |
| Một import thêm ID dưới checkpoint | Reconciliation phát hiện hàng bỏ qua |
| Một số hàng đổi source nhưng target không đổi | Mismatch query phát hiện writer sai |
| Batch gây nhiều WAL/replica lag | Rate limiter hoặc kill switch tạm dừng |
| Mất kết nối lúc commit | Job kiểm tra checkpoint/data, không kết luận rollback chắc chắn |
| Thay đổi mapping version giữa hai lần chạy | Không âm thầm ghi đè ngoài chính sách migration |

### Test cạnh tranh hai transaction độc lập

1. Database ban đầu có `order.id=42, raw='vn', normalized=NULL, version=7`.
2. Transaction A (backfill) đọc hàng và **tạm dừng trước UPDATE** bằng latch/barrier ở test.
3. Transaction B (API) cập nhật `raw='us', normalized='US', version=8` rồi commit.
4. Cho A tiếp tục chạy CAS với `expectedVersion=7`; kết quả phải `0` hoặc một lỗi đồng thời phù hợp.
5. Xác nhận DB cuối cùng giữ `raw='us', normalized='US'`; backfill không làm nó thành `'VN'`.

Không chỉ dùng `Thread.sleep()` để hy vọng race xảy ra. Integration test nên dùng loại DB và isolation gần production; mock Repository không kiểm chứng được locking, affected row count và thứ tự commit thật.

### Kiểm thử chất lượng mapping

Test các giá trị `"vn"`, `" VN "`, `"us"`, `NULL`, `""`, `"??"` và mã chưa hỗ trợ. Với dữ liệu tiền, ngày giờ hoặc định danh, bổ sung test rounding, timezone/DST, Unicode, overflow và bảo đảm không mất độ chính xác. Một bug mapping có thể lan qua hàng triệu record nên phải có dữ liệu mẫu đại diện và được phê duyệt trước khi chạy diện rộng.

## 21. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Thêm `NOT NULL` trước khi dữ liệu cũ được điền | Deployment/ghi mới lỗi | Expand nullable, backfill/validate rồi contract |
| Chạy một `UPDATE` toàn bảng không giới hạn | Khóa lâu, WAL lớn, rollback tốn kém | Batch/transaction ngắn, rate limit và quan sát |
| Dùng `OFFSET` tăng dần trên tập thay đổi liên tục | Bỏ sót/trùng và query chậm | Keyset/partition/checkpoint |
| Chỉ đổi backfill, quên sửa API writer | NULL tiếp tục phát sinh | Deploy writer mới và xác minh mọi đường ghi |
| Ghi giá trị từ snapshot cũ bằng `UPDATE WHERE id` | Ghi đè sửa đổi đồng thời | CAS theo version/source và điều kiện cột còn thiếu |
| Tăng checkpoint dù một hàng invalid rồi tuyên bố đã đủ | Bản ghi bị bỏ qua không được xử lý | Triage và reconciliation pass |
| Thấy `row count=0` thì retry vô hạn cùng dữ liệu | Hàng đã đổi, tạo contention | Đọc lại, phân loại conflict, retry có giới hạn |
| Dùng giá trị mặc định “UNKNOWN” không có ngữ nghĩa | Dữ liệu có vẻ đầy đủ nhưng sai | Rõ chính sách nullable/unknown và phê duyệt |
| Không chốt mốc quét nhưng insert liên tục | Job không có điểm dừng rõ | High-water mark + writer mới + sweep |
| Coi checkpoint là kiểm chứng dữ liệu | Không thấy mismatch/invalid | Validation đầy đủ sau job |
| Chạy song song nhiều worker không có claim/shard rule | Cập nhật trùng, khóa tranh chấp | Checkpoint lock, lease hoặc partition ownership |
| Chạy index concurrent trong transaction | Lỗi DDL PostgreSQL | Thực hiện ở migration phù hợp ngoài transaction |
| Dùng `@Version` JPA nhưng native backfill không tăng version | Entity cũ có thể ghi đè target | Tuân thủ optimistic-lock contract |
| Tắt writer hoặc rollback dữ liệu bằng cách xóa cột mới | Mất dữ liệu đã hợp lệ | Kế hoạch rollback ứng dụng và correction tiến lên |
| Chỉ nhìn throughput, không theo dõi API latency | Backfill làm hỏng trải nghiệm người dùng | Ngân sách tài nguyên và kill switch |

## 22. Bài tập thực hành: backfill mã quốc gia cho đơn hàng

Giả sử bảng có 5 triệu đơn, bạn cần bổ sung `country_code_normalized` trong khi API vẫn ghi 300 đơn/giây. Dữ liệu ban đầu:

| id | shipping_country_raw | country_code_normalized | row_version |
| ---: | --- | --- | ---: |
| 10 | `vn` | `NULL` | 2 |
| 11 | ` US ` | `NULL` | 8 |
| 12 | `unknown` | `NULL` | 3 |
| 13 | `SG` | `SG` | 5 |
| 14 | `vn` | `NULL` | 7 |

Một worker đọc id 14 ở `row_version=7`. Ngay sau đó API đổi `shipping_country_raw` thành `"US"`, đặt `country_code_normalized='US'` và tăng version lên 8.

**Câu hỏi:**

1. Bạn triển khai schema và writer theo thứ tự nào để cột mới không tiếp tục phát sinh NULL?
2. Nếu backfill dùng `UPDATE ... WHERE id=14`, dữ liệu cuối có thể sai ra sao?
3. Viết điều kiện `WHERE` để backfill không ghi đè update mới từ API.
4. Tại sao checkpoint đã qua id 12 vẫn chưa có nghĩa backfill xong?
5. Có nên gán id 12 thành `"VN"` vì hệ thống hoạt động tại Việt Nam không?
6. Nếu backfill crash ngay sau commit batch nhưng trước khi log tiến độ ra file ngoài DB, cần làm gì để chạy lại an toàn?
7. Nếu replication lag tăng mạnh và API p99 vượt ngưỡng, nên tăng batch size để chạy cho xong hay tạm dừng?
8. Sau khi job đi đến max ID, bạn đo gì trước khi thêm `NOT NULL`?

**Gợi ý lời giải:** Expand nullable, triển khai mọi writer ghi hai trường đúng trong cùng transaction, rồi mới backfill. Lệnh `WHERE id=14` có thể ghi `VN` đè lên `US`; dùng điều kiện `country_code_normalized IS NULL AND row_version=7` và so nguồn quan sát được. Id 12 không thể tự tính nên phải triage. Checkpoint chỉ là vị trí duyệt; dùng transaction/checkpoint bền vững và update idempotent để retry. Khi hệ thống chịu tải quá mức, **giảm tốc hoặc tạm dừng** và điều tra. Cuối cùng kiểm tra missing, invalid, mismatch, writer consistency và constraint trước khi chuyển reader/bắt buộc cột.

## 23. Checklist trước khi ký duyệt backfill

1. **Phạm vi:** liệt kê bảng/collection, số lượng hàng, phần trăm thiếu và kiểu dữ liệu lỗi.
2. **Nguồn sự thật:** biết mỗi giá trị mới được tính từ đâu và quy tắc chuyển đổi nào được phê duyệt.
3. **Tương thích deploy:** đã expand schema, mọi writer ghi đúng, reader chưa đòi hỏi trường mới quá sớm.
4. **Backfill contract:** thao tác ghi idempotent, CAS/điều kiện nguồn và version, transaction đúng phạm vi.
5. **Checkpoint:** có high-water mark, cách lưu tiến độ bền vững và cách chạy lại sau lỗi commit không rõ.
6. **Điều tiết:** batch size, parallelism, lock/statement timeout, rate limiting, stop/pause/resume.
7. **Quan sát:** scanned/updated/skipped/conflict/invalid và p95/p99 API, WAL, disk, replica lag.
8. **Dữ liệu ngoại lệ:** có danh sách triage/quarantine, chủ sở hữu xử lý và chính sách giá trị unknown.
9. **Validation:** kiểm tra missing/mismatch/constraint, không chỉ nhìn checkpoint hoặc tổng số dòng scan.
10. **Khôi phục:** có feature flag cho reader/job, bản sao lưu/rollback ứng dụng, quy trình correction tiến lên.
11. **Test:** đã thử race giữa writer và backfill, restart, commit outcome không rõ và nhiều worker.
12. **Contract phase:** chỉ thêm `NOT NULL`/unique constraint hoặc xóa cột cũ sau khi xác nhận dữ liệu và writer đáp ứng.

**Kết luận:** Backfill có kiểm soát là **một tiến trình tiến hóa dữ liệu trực tuyến**, không chỉ một script `UPDATE`. Muốn an toàn, hãy chuyển writer trước để không tạo thêm dữ liệu thiếu, quét theo lô với checkpoint, kiểm tra điều kiện ghi để không ghi đè concurrent update, giới hạn tải và quan sát chất lượng. Chỉ công nhận hoàn thành khi **reconciliation và validation** cho thấy dữ liệu đạt ngữ nghĩa đã định; sau đó mới siết constraint và loại bỏ đường tương thích cũ.
