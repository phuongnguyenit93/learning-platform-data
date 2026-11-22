# Kiểm thử hồi quy truy vấn và dữ liệu đầu ra sau thay đổi lược đồ

Một thay đổi schema có thể làm hỏng ứng dụng theo nhiều cách: câu SQL không còn chạy, JOIN nhân bản hàng, tổng tiền thay đổi, NULL được xử lý khác, kiểu dữ liệu bị chuyển đổi, API đổi tên trường hoặc truy vấn chậm đi. Vì vậy, kiểm thử migration không dừng ở việc xác nhận lệnh ALTER TABLE thành công.

**Kiểm thử hồi quy truy vấn** xác nhận các truy vấn và hành vi dữ liệu mà ứng dụng đang dựa vào vẫn đúng sau thay đổi. **Kiểm thử dữ liệu đầu ra** xác nhận result set có đúng cấu trúc, số hàng, giá trị, kiểu, nullability, thứ tự và ý nghĩa nghiệp vụ đã cam kết.

Bài học thuộc **Database SQL → Kiểm thử và gỡ lỗi → Kiểm thử hồi quy truy vấn và dữ liệu đầu ra sau thay đổi lược đồ**. Nội dung hướng dẫn cách lập danh mục phụ thuộc, định nghĩa output contract, tạo fixture và expected result, chạy kiểm thử trước/sau migration, kiểm tra schema và dữ liệu backfill, bảo đảm tương thích khi deploy nhiều phiên bản, kiểm thử hiệu năng và tích hợp vào CI.

## 1. Tại sao cần regression test sau schema change?

Schema là hợp đồng giữa database và các consumer: API, repository, ORM, báo cáo, ETL, job nền, stored procedure và hệ thống khác. Một thay đổi có thể không gây lỗi cú pháp nhưng vẫn thay đổi kết quả.

Ví dụ, trước đây mỗi đơn hàng có một cột tổng tiền:

~~~sql
CREATE TABLE don_hang (
    id BIGINT PRIMARY KEY,
    khach_hang_id BIGINT NOT NULL,
    tong_tien DECIMAL(12,2) NOT NULL,
    trang_thai VARCHAR(20) NOT NULL
);
~~~

Sau đó hệ thống tách thanh toán thành bảng riêng để hỗ trợ trả nhiều lần:

~~~sql
CREATE TABLE thanh_toan (
    id BIGINT PRIMARY KEY,
    don_hang_id BIGINT NOT NULL REFERENCES don_hang(id),
    so_tien DECIMAL(12,2) NOT NULL,
    trang_thai VARCHAR(20) NOT NULL
);
~~~

Truy vấn cũ vẫn chạy, nhưng JOIN đơn hàng với thanh toán có thể trả nhiều hàng cho một đơn. Một phép SUM khác có thể cộng trùng tiền đơn hàng hoặc tính cả giao dịch thất bại.

Các dạng hồi quy:

- **Cú pháp:** truy vấn không còn chạy do bảng, cột, kiểu hoặc hàm thay đổi.
- **Cấu trúc kết quả:** tên cột, alias, thứ tự, kiểu, precision, scale hoặc nullability đổi.
- **Giá trị:** tổng tiền, ngày tháng, trạng thái hoặc phép tính sai.
- **Cardinality:** số hàng thay đổi do JOIN, lọc, quan hệ 1-n hoặc dữ liệu backfill.
- **Ngữ nghĩa:** giá trị vẫn hợp lệ về kiểu nhưng ý nghĩa nghiệp vụ thay đổi.
- **Tương thích:** ứng dụng cũ không làm việc với schema mới trong giai đoạn rolling deployment.
- **Hiệu năng:** query vẫn đúng nhưng chậm, scan nhiều hàng hoặc vượt timeout.
- **Dữ liệu lịch sử:** backfill làm mất, nhân bản hoặc chuyển sai dữ liệu cũ.

Migration thành công chỉ chứng minh DDL đã chạy. Nó không chứng minh consumer vẫn nhận đúng dữ liệu.

## 2. Các lớp kiểm thử cần có

| Lớp | Điều cần xác nhận | Ví dụ |
| --- | --- | --- |
| Schema contract | Cấu trúc mới đúng | Cột, kiểu, default, FK, index |
| Migration | Dữ liệu cũ được chuyển đúng | Backfill, count, checksum |
| Query regression | SQL cũ/mới chạy đúng | SELECT, JOIN, CTE, view |
| Output contract | Result set đúng shape | Alias, type, nullability |
| Data correctness | Giá trị đúng | Tổng tiền, số đơn, trạng thái |
| Compatibility | App và schema tương thích | App cũ với schema expand |
| Performance | Không suy giảm ngoài ngưỡng | Latency, reads, plan |
| End-to-end | Luồng nghiệp vụ vẫn đúng | Tạo đơn rồi xem báo cáo |

Không một lớp đơn lẻ thay thế được lớp còn lại. Schema metadata đúng không chứng minh dữ liệu đúng; một snapshot output đúng không chứng minh mọi truy vấn khác còn tương thích.

## 3. Lập danh mục truy vấn và consumer bị ảnh hưởng

Trước khi sửa schema, tìm mọi nơi phụ thuộc vào đối tượng sắp thay đổi:

- SQL trong repository, service và query builder.
- ORM entity, mapping, relationship và generated query.
- View, materialized view, stored procedure, function và trigger.
- API response, export, báo cáo và dashboard.
- Scheduled job, ETL, import/export và reconciliation.
- Consumer hoặc service khác dùng chung database.
- Script vận hành, migration, seed và công cụ hỗ trợ.
- Index, constraint, generated column, permission và role liên quan.

Tìm kiếm văn bản trong repository là bước hữu ích nhưng không đủ nếu SQL được sinh động, nằm trong database object hoặc công cụ BI bên ngoài.

### 3.1. Ma trận phụ thuộc

Ví dụ thay đổi cách tính tổng tiền đơn:

| Thành phần | Query/object | Phụ thuộc | Rủi ro |
| --- | --- | --- | --- |
| API chi tiết | getOrder | tong_tien | Giá trị và kiểu response |
| API danh sách | listOrders | JOIN thanh toán | Nhân bản đơn |
| Báo cáo ngày | revenueByDay | SUM | Double count |
| Export | exportOrders | Alias cột | Header và thứ tự |
| View | v_don_hang | Cột cũ | View invalid |
| Job đối soát | reconcile | Thanh toán/hoàn tiền | Chênh lệch |
| ORM | Order entity | Mapping | Null hoặc type conversion |

Mỗi mục nên ghi owner, input, schema dependency, output contract, trường hợp biên, tần suất, mức độ ảnh hưởng và test hiện có.

### 3.2. Xếp mức độ rủi ro

Ưu tiên kiểm thử sâu cho:
1. Số dư, thanh toán, tồn kho, quyền và trạng thái nghiệp vụ.
2. Truy vấn dùng chung bởi nhiều consumer.
3. Query tổng hợp tiền hoặc đếm đối tượng.
4. JOIN qua quan hệ vừa thay đổi.
5. Dynamic SQL, view, procedure và ORM mapping.
6. Báo cáo ảnh hưởng quyết định vận hành.

Có thể chạy smoke test trên toàn bộ danh mục và test sâu theo rủi ro. Không dùng mức ưu tiên làm lý do bỏ qua kiểm tra truy vấn ít quan trọng.

## 4. Định nghĩa output contract trước khi viết test

Output contract mô tả điều consumer được phép kỳ vọng từ truy vấn:

- Tên và alias từng cột.
- Thứ tự cột nếu consumer dùng ordinal.
- Kiểu SQL, precision, scale, length.
- Nullability.
- Số hàng và tính duy nhất của khóa.
- Thứ tự hàng nếu có cam kết.
- Quy tắc rounding và đơn vị.
- Time zone, độ chính xác timestamp.
- Collation và quy tắc so sánh chuỗi.
- Cách biểu diễn status, boolean, JSON.
- Ý nghĩa của NULL, default và field bị bỏ qua.

Ví dụ contract cho API đơn hàng:

~~~text
order_id       : integer 64-bit, không NULL
customer_name  : string, không NULL
total_amount   : decimal(14,2), không NULL
paid_amount    : decimal(14,2), không NULL
balance_due    : decimal(14,2), không NULL
created_at     : timestamp UTC
status         : giá trị thuộc tập trạng thái được công bố
~~~

Đừng chỉ ghi “trả về danh sách đơn hàng”. Hãy nêu kiểu, nullability và ý nghĩa của từng trường.

### 4.1. Alias và thứ tự cột

Đổi truy vấn từ:

~~~sql
SELECT SUM(so_tien)
FROM thanh_toan;
~~~

sang:

~~~sql
SELECT SUM(so_tien) AS tong_da_thanh_toan
FROM thanh_toan;
~~~

có thể ảnh hưởng mapper, JSON serializer, export hoặc code đọc cột theo tên. Alias tường minh nên là một phần của contract.

Thứ tự hàng chỉ được bảo đảm khi có ORDER BY. Nếu cần kết quả ổn định, thêm khóa duy nhất làm tie-break:

~~~sql
SELECT id, tao_luc
FROM don_hang
ORDER BY tao_luc, id;
~~~

Nếu thứ tự không phải contract, test nên so sánh theo khóa thay vì dựa vào thứ tự tình cờ của execution plan.

## 5. Thiết kế fixture có chủ đích

Fixture là dữ liệu được tạo để kích hoạt các nhánh logic. Bộ fixture nhỏ nhưng có cấu trúc tốt thường hữu ích hơn một bản sao dữ liệu lớn khó hiểu.

Ví dụ cho đơn hàng và thanh toán:

| Đơn | Chi tiết | Thanh toán | Trạng thái |
| --- | --- | --- | --- |
| 101 | Hai dòng hàng | Đã trả đủ | PAID |
| 102 | Một dòng hàng | Không có | UNPAID |
| 103 | Ba dòng hàng | Trả một phần | PARTIAL |
| 104 | Không có dòng hàng | Không có | DRAFT |
| 105 | Một dòng hàng | Đã trả rồi hoàn tiền | REFUNDED |
| 106 | Hai dòng hàng | Hai lần thanh toán | PAID |

Các trường hợp nên có:
- Không có hàng liên quan, một hàng con và nhiều hàng con.
- Hai hàng có cùng sort key.
- NULL, default, chuỗi rỗng và số 0.
- Decimal có scale, giá trị sát precision tối đa.
- Ngày ở biên ngày/tháng/năm và DST nếu có.
- Chuỗi hoa/thường, dấu tiếng Việt và Unicode.
- Bản ghi xóa mềm.
- Orphan legacy nếu cần kiểm tra xử lý dữ liệu cũ.
- Duplicate key và constraint violation.
- Trạng thái cũ cần backfill.
- Dữ liệu sát giới hạn kiểu hoặc độ dài.

### 5.1. ID fixture ổn định

Dùng ID cố định dễ đọc như 9101, 9102 hoặc UUID xác định. Tránh giả định sequence luôn bắt đầu ở 1 nếu test chạy song song hoặc DB không reset.

Nếu ID được sinh tự động, lấy generated key từ INSERT hoặc truy vấn lại bằng natural key.

### 5.2. Test độc lập

Mỗi test nên tự tạo fixture cần thiết hoặc dùng fixture dùng chung được kiểm soát. Không để test B phụ thuộc test A đã chạy trước.

Mô hình:

~~~text
Arrange: tạo fixture và trạng thái DB
Act: chạy query hoặc nghiệp vụ
Assert: kiểm tra shape, values và invariants
Cleanup: rollback hoặc xóa fixture
~~~

Rollback hữu ích khi mọi thao tác nằm trên cùng transaction/connection. Nó không dọn được dữ liệu do code mở connection khác commit, side effect ngoài DB, hoặc mọi loại DDL ở mọi DBMS.

## 6. Xây dựng expected result độc lập

Expected result là oracle mà test dùng để so sánh. Nó phải độc lập với logic đang được kiểm thử.

Có thể tạo expected từ:
- Tính thủ công trên fixture nhỏ.
- Bảng expected viết tường minh.
- Công thức nghiệp vụ độc lập.
- Snapshot baseline đã được review.
- Invariant luôn đúng theo domain.

Ví dụ fixture:

| Đơn | Dòng hàng | Đơn giá | Số lượng | Tổng kỳ vọng |
| --- | ---: | ---: | ---: | ---: |
| 101 | 2 | 50.00 | 2 | 100.00 |
| 101 | 3 | 25.00 | 4 | 100.00 |
| **Tổng** | | | | **200.00** |

Expected có thể ghi rõ `Decimal("200.00")`. Không copy nguyên JOIN và SUM đang test để tạo expected vì hai bên có thể mắc cùng một lỗi.

### 6.1. Snapshot/golden test

Golden test lưu output đã được xác nhận và so sánh output mới với snapshot. Phù hợp với báo cáo hoặc kết quả cấu trúc lớn.

Rủi ro:
- Snapshot có thể chứa dữ liệu nhạy cảm.
- Diff lớn khó review.
- Người sửa có thể cập nhật snapshot chỉ để CI xanh.
- Một snapshot không thể đại diện mọi input.

Snapshot cần được review như code và gắn với schema/dialect/version phù hợp.

### 6.2. Invariant

Invariant là điều kiện phải luôn đúng:
- Tổng phân bổ bằng tổng header theo quy tắc rounding.
- Không có order_id trùng trong kết quả một hàng mỗi đơn.
- Số lượng tồn không âm nếu domain yêu cầu.
- Mọi child row có parent hợp lệ.
- Tổng số dư trước/sau chuyển nội bộ không đổi.
- Không có trạng thái kết thúc không hợp lệ.

Invariant thường phát hiện lỗi mà snapshot nhỏ không bao phủ.

## 7. Chạy baseline và candidate trước/sau migration

Có thể tạo hai database độc lập từ cùng schema cũ và cùng fixture:

~~~mermaid
flowchart TD
    A["Schema cũ + fixture"] --> B["Baseline database"]
    A --> C["Candidate database"]
    C --> D["Chạy migration"]
    B --> E["Chạy query baseline"]
    D --> F["Chạy query mới"]
    E --> G["Chuẩn hóa kết quả"]
    F --> H["Chuẩn hóa kết quả"]
    G --> I["So sánh contract và invariant"]
    H --> I
    I --> J["Đánh giá diff và performance"]
~~~

Baseline và candidate phải biểu diễn cùng trạng thái logic. Nếu fixture khác nhau, diff không cho biết migration có gây lỗi hay không.

Quy trình:
1. Tạo DB ở version cũ.
2. Nạp fixture có các trường hợp biên.
3. Chạy query baseline và lưu kết quả cần thiết.
4. Tạo candidate từ cùng trạng thái.
5. Chạy migration.
6. Kiểm tra schema và backfill.
7. Chạy query regression.
8. So sánh shape, values và invariant.
9. Chạy compatibility/performance checks.

Nếu output thay đổi có chủ đích, expected phải được cập nhật theo quyết định nghiệp vụ được review, không phải tự động chấp nhận mọi diff.

## 8. Kiểm tra schema contract

Sau migration, kiểm tra:
- Table/view tồn tại.
- Column name, type, precision, scale và length.
- NULL/NOT NULL, default.
- Primary key, unique, FK, check.
- Index và thứ tự cột.
- Generated/identity.
- Charset/collation.
- View/procedure signature.
- Permission và ownership.

### 8.1. PostgreSQL

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default,
    numeric_precision,
    numeric_scale,
    character_maximum_length
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'don_hang'
ORDER BY ordinal_position;
~~~

Kiểm tra constraint:

~~~sql
SELECT
    tc.constraint_name,
    tc.constraint_type,
    kcu.column_name,
    ccu.table_name AS referenced_table,
    ccu.column_name AS referenced_column
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
  ON tc.constraint_schema = kcu.constraint_schema
 AND tc.constraint_name = kcu.constraint_name
LEFT JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_schema = ccu.constraint_schema
 AND tc.constraint_name = ccu.constraint_name
WHERE tc.table_schema = 'public'
  AND tc.table_name = 'don_hang';
~~~

### 8.2. MySQL

~~~sql
SHOW CREATE TABLE don_hang;

SELECT
    column_name,
    column_type,
    is_nullable,
    column_default,
    extra
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'don_hang'
ORDER BY ordinal_position;
~~~

### 8.3. SQL Server

~~~sql
SELECT
    c.name AS column_name,
    t.name AS data_type,
    c.max_length,
    c.precision,
    c.scale,
    c.is_nullable,
    dc.definition AS default_definition
FROM sys.columns c
JOIN sys.types t ON c.user_type_id = t.user_type_id
LEFT JOIN sys.default_constraints dc
  ON c.default_object_id = dc.object_id
WHERE c.object_id = OBJECT_ID('dbo.DonHang')
ORDER BY c.column_id;
~~~

### 8.4. Oracle

~~~sql
SELECT
    column_name,
    data_type,
    data_length,
    data_precision,
    data_scale,
    nullable,
    data_default
FROM user_tab_columns
WHERE table_name = 'DON_HANG'
ORDER BY column_id;
~~~

### 8.5. SQLite

~~~sql
PRAGMA table_info('don_hang');
PRAGMA foreign_key_list('don_hang');
PRAGMA index_list('don_hang');
~~~

SQLite foreign key enforcement cần được bật đúng trên từng connection bằng cấu hình phù hợp. Không giả định chỉ khai báo FK là mọi connection đều đang enforce nếu cấu hình chưa bật.

### 8.6. So sánh theo hợp đồng logic

Kiểu vật lý có thể khác giữa DBMS: integer/bigint, boolean, timestamp, numeric. Khi hỗ trợ nhiều dialect, kiểm tra theo hợp đồng logic và adapter cho từng DBMS, không ép tên type vật lý phải giống nhau.

## 9. Kiểm thử dữ liệu sau backfill

Schema migration có thể thêm cột, đổi kiểu, tách bảng hoặc chuẩn hóa dữ liệu. Phải kiểm tra dữ liệu cũ đã chuyển đúng.

Ví dụ từ tổng tiền đơn sang bảng thanh toán:

~~~sql
CREATE TABLE thanh_toan (
    id BIGINT PRIMARY KEY,
    don_hang_id BIGINT NOT NULL REFERENCES don_hang(id),
    so_tien DECIMAL(14,2) NOT NULL,
    trang_thai VARCHAR(30) NOT NULL
);
~~~

Nếu migration tạo một giao dịch khởi tạo cho mỗi đơn, cần xác định rõ đơn nháp, thanh toán thất bại, hoàn tiền và partial payment được biểu diễn thế nào. Không mặc định tổng mọi giao dịch bằng số tiền đã thanh toán.

### 9.1. Đếm và đối chiếu khóa

~~~sql
SELECT COUNT(*) AS so_don
FROM don_hang;

SELECT COUNT(DISTINCT don_hang_id) AS so_don_co_thanh_toan
FROM thanh_toan;
~~~

Hai số này không nhất thiết bằng nhau nếu đơn nháp chưa có thanh toán. Expected phải theo nghiệp vụ.

### 9.2. Tìm orphan

~~~sql
SELECT t.*
FROM thanh_toan t
LEFT JOIN don_hang d ON d.id = t.don_hang_id
WHERE d.id IS NULL;
~~~

Nếu FK bắt buộc và dữ liệu phải sạch, expected là 0 hàng.

### 9.3. Kiểm tra dữ liệu không bị nhân bản

~~~sql
SELECT don_hang_id, COUNT(*)
FROM thanh_toan
GROUP BY don_hang_id
HAVING COUNT(*) > 1;
~~~

Kết quả có thể hợp lệ khi hỗ trợ nhiều lần thanh toán. Test phải so sánh với quy tắc mới, không mặc định mỗi đơn chỉ có một thanh toán.

### 9.4. Đối soát số tiền

~~~sql
SELECT
    d.id,
    d.tong_tien,
    COALESCE(
        SUM(
            CASE
                WHEN t.trang_thai = 'THANH_CONG'
                THEN t.so_tien
                ELSE 0
            END
        ),
        0
    ) AS da_thanh_toan
FROM don_hang d
LEFT JOIN thanh_toan t ON t.don_hang_id = d.id
GROUP BY d.id, d.tong_tien;
~~~

Đây là ví dụ minh họa. Rule thật phải xác định hoàn tiền, hủy giao dịch, phí, discount, currency và rounding.

Count bằng nhau không chứng minh dữ liệu đúng. Nên so sánh khóa nghiệp vụ, checksum/aggregate theo partition và các invariant quan trọng.

## 10. Kiểm thử JOIN và cardinality

Thay đổi quan hệ từ 1-1 sang 1-n là nguồn hồi quy phổ biến.

~~~sql
SELECT d.id, d.tong_tien, t.trang_thai
FROM don_hang d
LEFT JOIN thanh_toan t ON t.don_hang_id = d.id;
~~~

Nếu mỗi đơn có nhiều thanh toán, truy vấn trả nhiều hàng cho một đơn. Điều đó có thể đúng với màn hình giao dịch nhưng sai với API cam kết một hàng mỗi đơn.

### 10.1. Đếm hàng sau JOIN

~~~sql
SELECT
    COUNT(*) AS so_hang_join,
    COUNT(DISTINCT d.id) AS so_don
FROM don_hang d
LEFT JOIN thanh_toan t ON t.don_hang_id = d.id;
~~~

Nếu số hàng JOIN lớn hơn số đơn, có nhân bản do quan hệ 1-n. Test cần xác nhận cardinality theo contract.

### 10.2. Tổng hợp bảng con trước khi JOIN

~~~sql
WITH tong_thanh_toan AS (
    SELECT
        don_hang_id,
        SUM(so_tien) AS tong_da_thanh_toan
    FROM thanh_toan
    WHERE trang_thai = 'THANH_CONG'
    GROUP BY don_hang_id
)
SELECT
    d.id,
    d.tong_tien,
    COALESCE(t.tong_da_thanh_toan, 0) AS tong_da_thanh_toan
FROM don_hang d
LEFT JOIN tong_thanh_toan t
  ON t.don_hang_id = d.id;
~~~

Test nên có đơn không thanh toán, một thanh toán, nhiều thanh toán, một giao dịch thành công và một thất bại, cùng trường hợp hoàn tiền.

## 11. Kiểm thử NULL, default, decimal, timestamp và collation

### 11.1. NULL khác 0 và chuỗi rỗng

~~~sql
SELECT
    COUNT(*) AS tong_hang,
    COUNT(ghi_chu) AS so_hang_co_ghi_chu,
    SUM(so_tien) AS tong_tien
FROM don_hang;
~~~

COUNT(*) đếm tất cả hàng; COUNT(cột) bỏ qua NULL. Thêm default/backfill có thể thay đổi kết quả các phép đếm và tổng hợp.

Test phải phân biệt SQL NULL, số 0, chuỗi rỗng, JSON null và key không xuất hiện trong JSON nếu các trạng thái đó có ý nghĩa khác nhau.

### 11.2. Default và dữ liệu cũ

Thêm cột có DEFAULT có semantics lưu trữ và backfill khác nhau tùy DBMS/version. Kiểm tra:
- Giá trị nhìn thấy của hàng cũ.
- INSERT mới bỏ qua cột.
- INSERT ghi rõ NULL.
- UPDATE không chạm cột.
- Migration chạy lại hoặc resume nếu có thể.

### 11.3. DECIMAL và floating point

Với tiền tệ:
- Kiểm tra precision/scale sau migration.
- Giá trị sát giới hạn.
- Rounding và overflow.
- Driver map sang Decimal/BigDecimal.
- Không chuyển sang float rồi so sánh equality tuyệt đối.

### 11.4. Timestamp và timezone

Kiểm tra timezone, độ chính xác, biên ngày, DST nếu có, và cách serialize. Chuẩn hóa về cùng timezone/precision theo contract trước khi so sánh.

### 11.5. Collation và Unicode

Đổi collation có thể ảnh hưởng ORDER BY, GROUP BY, DISTINCT, so sánh và unique key. Fixture nên có chữ hoa/thường, dấu tiếng Việt, Unicode normalization, khoảng trắng và chuỗi gần giống.

## 12. Kiểm thử aggregate và window

Các query tổng hợp có thể vẫn chạy nhưng sai do JOIN mới hoặc dữ liệu bị nhân bản.

Các assertion hữu ích:
- Tổng chi tiết khớp tổng header theo rule.
- COUNT DISTINCT khóa bằng số thực thể mong đợi.
- Không thiếu hoặc dư nhóm.
- Subtotal NULL được phân biệt với NULL thật khi dùng ROLLUP.
- Ranking giữ ties đúng.
- Running total không thay đổi do frame mặc định.
- Top-N đúng semantics: đúng N hàng hay N mức hạng.

Ví dụ:

~~~sql
SELECT
    khach_hang_id,
    SUM(tong_tien) AS tong
FROM don_hang
WHERE trang_thai <> 'HUY'
GROUP BY khach_hang_id;
~~~

Truy vấn chỉ trả khách có đơn. Nếu API cần khách không đơn với tổng 0, phải bắt đầu từ bảng khách hàng và LEFT JOIN kết quả tổng hợp. Test cần có khách không đơn.

## 13. Kiểm thử từ database tới output ứng dụng

Result set được driver map sang kiểu ứng dụng rồi serializer chuyển thành JSON, CSV hoặc event:

~~~text
Database row
   ↓
Driver values + metadata
   ↓
Repository / ORM mapping
   ↓
Service transformation
   ↓
API DTO / CSV / event
   ↓
Consumer
~~~

Một BIGINT có thể thành long, integer hoặc string. DECIMAL có thể thành Decimal/BigDecimal, string hoặc floating point. Timestamp có thể mất timezone/precision khi serialize.

### 13.1. Repository tests

Kiểm tra SQL, row count, values, driver types, NULL, generated key và alias mapping.

### 13.2. API tests

Kiểm tra JSON key, number/string/boolean, null vs omitted, date format, pagination, sorting và precision tiền. Xác nhận field cũ có còn được công bố trong giai đoạn tương thích hay không.

### 13.3. Export/report tests

Kiểm tra header, thứ tự cột nếu có contract, UTF-8, decimal/date format, subtotal, CSV escaping, row count và tổng tiền.

Không cần lặp toàn bộ mọi assertion ở mọi tầng. Kết hợp repository tests với một số end-to-end tests để xác nhận mapping thật.

## 14. Tương thích trong rolling deployment

Ứng dụng và schema thường không được deploy cùng lúc. Có thể tồn tại app cũ, app mới, worker chạy lâu và consumer ngoài chưa nâng cấp.

### 14.1. Expand-contract

Một cách triển khai thay đổi phá vỡ tương thích theo nhiều bước:

1. **Expand:** thêm cột/bảng mới, giữ cấu trúc cũ.
2. Deploy app tương thích với schema mở rộng.
3. Ghi đồng bộ hai cấu trúc nếu cần và có kiểm soát.
4. Backfill dữ liệu cũ theo batch.
5. Đối soát old/new.
6. Chuyển consumer sang cấu trúc mới.
7. Theo dõi không còn consumer cũ.
8. **Contract:** bỏ cấu trúc cũ ở một lần release sau.

~~~mermaid
flowchart TD
    A["Schema cũ + app cũ"] --> B["Expand: thêm cấu trúc mới"]
    B --> C["Deploy app tương thích"]
    C --> D["Backfill dữ liệu cũ"]
    D --> E["Đối soát old và new"]
    E --> F["Chuyển consumer sang schema mới"]
    F --> G["Theo dõi consumer cũ"]
    G --> H["Contract: bỏ cấu trúc cũ"]
~~~

### 14.2. Ma trận tương thích

| Ứng dụng | Schema cũ | Schema expand | Schema contract |
| --- | --- | --- | --- |
| App cũ | Phải chạy | Phải chạy nếu nằm trong cửa sổ tương thích | Không kỳ vọng chạy |
| App chuyển tiếp | Theo thiết kế | Phải chạy | Tùy phiên bản |
| App mới | Nếu có hỗ trợ | Phải chạy | Phải chạy |

Không phải mọi cặp version đều cần hỗ trợ. Ghi rõ deployment strategy và thời gian tồn tại của từng phiên bản.

### 14.3. Backfill cần test riêng

Kiểm tra batch boundary, resume sau lỗi, chạy lại an toàn, số hàng, checksum, NULL/legacy, trigger/audit side effects, lock contention và tương tác với ghi mới trong lúc backfill.

## 15. Migration test trên dữ liệu cũ

Test chỉ tạo schema rỗng không đại diện production. Cần dựng DB từ migration lịch sử tới version đang được hỗ trợ, nạp fixture hoặc bản sao đã ẩn danh, rồi nâng cấp.

Các bước:
1. Tạo database từ version cũ.
2. Nạp dữ liệu đại diện.
3. Chụp count và tổng kiểm tra.
4. Chạy migration theo thứ tự thực tế.
5. Kiểm tra schema và migration history.
6. Đối soát dữ liệu mới.
7. Chạy query regression suite.
8. Chạy compatibility/performance tests.

Nếu production có thể ở version N-3, hãy test đường nâng cấp từ N-3, không chỉ từ N.

### 15.1. Recovery

Kiểm thử:
- Migration lỗi giữa chừng.
- Retry migration.
- Migration đã áp dụng một phần.
- Restore backup.
- Forward-fix.
- Thời gian lock và maintenance window.
- Khả năng resume backfill.

Không phải migration phá hủy dữ liệu nào cũng rollback được. Đối với thay đổi không thể đảo ngược, recovery plan có thể cần backup và forward-fix.

## 16. DDL và transaction khác nhau giữa DBMS

Không giả định mọi DDL được rollback giống nhau:

- PostgreSQL hỗ trợ nhiều DDL transactional, nhưng có lệnh không được phép trong transaction block.
- MySQL có nhiều DDL implicit commit; atomic DDL ở version mới không có nghĩa mọi chuỗi DDL có thể rollback như DML transaction.
- Oracle nhiều DDL implicit commit.
- SQL Server hỗ trợ transaction cho nhiều DDL nhưng có ngoại lệ.
- SQLite hỗ trợ transactional schema changes trong nhiều trường hợp, tùy lệnh và version.

Migration framework có thể chia transaction theo dialect. Test phải dùng DBMS/version/config giống môi trường thực tế.

## 17. Isolation, cleanup và test chạy song song

### 17.1. Chiến lược cleanup

- Transaction rollback: nhanh nếu mọi thay đổi nằm cùng connection/transaction.
- Truncate/delete fixture: cần xét FK, trigger và sequence.
- Database/schema riêng cho suite: cô lập tốt.
- Container mới cho CI job: giảm state leak.
- Schema riêng mỗi worker: phù hợp chạy song song nếu DBMS hỗ trợ.

### 17.2. Test song song

Hai test dùng chung ID hoặc truncate cùng bảng sẽ đụng nhau. Có thể:
- Namespace ID/tenant theo test run.
- DB/schema riêng.
- Không dùng chung mutable connection.
- Seed fixture có run ID.
- Dùng lock khi tài nguyên thật sự cần chia sẻ.

Không dùng database production cho regression tests. Dữ liệu production-like phải được ẩn danh và giới hạn quyền truy cập.

## 18. Ví dụ integration test với Python, pytest và psycopg

Ví dụ giả định schema test đã migrate và có bảng don_hang, thanh_toan. Tên cột cần điều chỉnh theo dự án.

~~~python
from decimal import Decimal
import os

import psycopg
import pytest


@pytest.fixture
def conn():
    dsn = os.environ["TEST_DATABASE_URL"]
    connection = psycopg.connect(dsn)
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def test_tong_thanh_toan_moi_don(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO don_hang (id, tong_tien)
            VALUES (9101, 200.00), (9102, 100.00)
            """
        )

        cur.execute(
            """
            INSERT INTO thanh_toan
                (id, don_hang_id, so_tien, trang_thai)
            VALUES
                (9201, 9101, 50.00, 'THANH_CONG'),
                (9202, 9101, 150.00, 'THANH_CONG'),
                (9203, 9102, 30.00, 'THAT_BAI')
            """
        )

        cur.execute(
            """
            SELECT
                d.id,
                COALESCE(
                    SUM(
                        CASE
                            WHEN t.trang_thai = 'THANH_CONG'
                            THEN t.so_tien
                            ELSE 0
                        END
                    ),
                    0
                ) AS da_thanh_toan
            FROM don_hang d
            LEFT JOIN thanh_toan t ON t.don_hang_id = d.id
            WHERE d.id IN (9101, 9102)
            GROUP BY d.id
            ORDER BY d.id
            """
        )
        actual = cur.fetchall()

    expected = [
        (9101, Decimal("200.00")),
        (9102, Decimal("0")),
    ]
    assert actual == expected
~~~

Test có đơn nhiều thanh toán và đơn chỉ có giao dịch thất bại; so sánh Decimal thay vì float. Rollback fixture hoạt động vì INSERT và SELECT dùng cùng connection. Nếu code được test mở connection khác và commit, fixture rollback không dọn được dữ liệu đó.

### 18.1. Kiểm tra schema metadata

~~~python
def test_schema_don_hang(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable,
                   numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'don_hang'
            ORDER BY ordinal_position
            """
        )
        columns = cur.fetchall()

    by_name = {row[0]: row[1:] for row in columns}
    assert "id" in by_name
    assert "tong_tien" in by_name
    assert by_name["tong_tien"][0] == "numeric"
    assert by_name["tong_tien"][1] == "NO"
~~~

Schema test không thay query test. Cột có kiểu đúng vẫn có thể chứa dữ liệu sai hoặc JOIN sai.

## 19. So sánh output ổn định

### 19.1. Thứ tự

Nếu thứ tự là contract, assert nguyên thứ tự và bảo đảm query có ORDER BY đủ tie-break. Nếu thứ tự không phải contract, so sánh theo khóa:

~~~python
actual_by_id = sorted(actual, key=lambda row: row["id"])
expected_by_id = sorted(expected, key=lambda row: row["id"])
assert actual_by_id == expected_by_id
~~~

### 19.2. Decimal

~~~python
from decimal import Decimal

assert actual_amount == Decimal("200.00")
~~~

Nếu scale là một phần contract, kiểm tra cả metadata hoặc format serialization. Không chuyển Decimal sang float rồi so sánh tuyệt đối.

### 19.3. NULL

Phân biệt SQL NULL, 0, chuỗi rỗng, JSON null và key không xuất hiện. Mapper có thể làm các trường hợp này giống nhau nếu không test rõ.

### 19.4. Timestamp

Chuẩn hóa timezone và precision theo contract. Không cắt millisecond nếu API cam kết microsecond.

### 19.5. Floating point

Nếu domain dùng số gần đúng, dùng tolerance có cơ sở:

~~~python
assert abs(actual - expected) <= tolerance
~~~

Tolerance phải dựa trên độ lớn và độ chính xác nghiệp vụ, không nới rộng chỉ để test pass.

## 20. Property-based và metamorphic testing

Fixture cố định kiểm tra ví dụ cụ thể. Property-based testing sinh nhiều input để kiểm tra invariant tổng quát.

Ví dụ:
- Tổng dòng hàng bằng tổng header theo công thức.
- Số lượng tồn không âm.
- Đảo thứ tự dữ liệu đầu vào không đổi tổng.
- Thêm giao dịch thất bại không làm tăng số đã thanh toán thành công.
- Chia thanh toán thành hai phần có tổng bằng nhau không đổi paid amount.
- Thêm khách không có đơn không làm đổi doanh thu tổng.

Metamorphic testing kiểm tra quan hệ giữa hai lần chạy:
1. Chạy query trên fixture S.
2. Thêm một đơn 10.00 cho khách A.
3. Chạy lại.
4. Tổng khách A tăng đúng 10.00; khách khác không đổi.

### 20.1. Query kiểm tra invariant

~~~sql
-- Tìm khóa đơn bị trùng trong tập cần duy nhất.
SELECT id, COUNT(*)
FROM don_hang
GROUP BY id
HAVING COUNT(*) > 1;

-- Tìm thanh toán mồ côi.
SELECT t.id
FROM thanh_toan t
LEFT JOIN don_hang d ON d.id = t.don_hang_id
WHERE d.id IS NULL;

-- Tìm số tiền âm nếu domain cấm.
SELECT id, tong_tien
FROM don_hang
WHERE tong_tien < 0;
~~~

Expected có thể là 0 hàng, nhưng chỉ khi rule nghiệp vụ thực sự cấm các trường hợp đó. Ví dụ credit note có thể hợp lệ với số âm.

## 21. Differential testing cho nhiều DBMS

Nếu ứng dụng hỗ trợ nhiều DBMS, chạy cùng logic nghiệp vụ trên từng dialect và so sánh kết quả đã chuẩn hóa.

Cần chuẩn hóa:
- Integer/decimal/date/time.
- Boolean representation.
- NULL ordering.
- Collation.
- JSON representation.
- Error code/class theo adapter.
- Metadata name/type nếu dialect khác nhau.

~~~text
Business test case
       |
       +-- PostgreSQL adapter --> PostgreSQL test DB
       |
       +-- MySQL adapter -------> MySQL test DB
       |
       +-- SQL Server adapter --> SQL Server test DB
       |
       +-- Oracle adapter ------> Oracle test DB
       |
       +-- SQLite adapter ------> SQLite test DB
       |
       v
Normalize by output contract
       |
       v
Compare values and invariants
~~~

Không phải extension nào cũng cần có trên mọi DBMS. Test phải ghi rõ feature vendor-specific và fallback portable.

## 22. Kiểm thử view, procedure, trigger và ORM

Schema change có thể làm object phụ thuộc invalid hoặc vẫn chạy nhưng giữ logic cũ.

Kiểm tra:
- View compile và trả đúng cột/giá trị.
- Materialized view được refresh đúng thời điểm.
- Stored procedure/function signature.
- Trigger không ghi trùng hoặc bỏ audit.
- Permission và ownership.
- Dependency chain.
- View không còn tham chiếu cột cũ.
- ORM mapping và generated SQL phản ánh schema mới.

Metadata tồn tại chưa chứng minh nội dung đúng. Hãy chạy object với fixture và assert output.

## 23. Performance regression

Query có thể đúng nhưng chậm hơn vì:
- Index bị bỏ hoặc không còn phù hợp.
- Implicit cast do kiểu mới.
- Statistics lỗi thời.
- JOIN cardinality tăng.
- Predicate không còn sargable.
- Sort/hash spill ra disk.
- Partition pruning không còn hoạt động.
- CTE/view materialize ngoài dự kiến.
- Phân bố dữ liệu mới khác trước.

### 23.1. Benchmark có kiểm soát

- Dùng dataset đủ lớn và phân bố gần thực tế.
- So sánh cùng input và cùng trạng thái dữ liệu.
- Warm-up khi cần.
- Lặp nhiều lần, xem median và percentile.
- Phân biệt cold cache/warm cache.
- Ghi DBMS version, config, hardware và concurrency.
- Không benchmark nặng trên production.

### 23.2. Execution plan

PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    khach_hang_id,
    SUM(tong_tien)
FROM don_hang
WHERE tao_luc >= DATE '2026-01-01'
GROUP BY khach_hang_id;
~~~

EXPLAIN ANALYZE thực thi truy vấn; chỉ dùng trên môi trường an toàn nếu query có side effect.

SQL Server có Actual Execution Plan và `SET STATISTICS IO, TIME ON`. MySQL có EXPLAIN ANALYZE ở version hỗ trợ. Oracle có execution plan và SQL Monitor tùy cấu hình/license. SQLite có EXPLAIN QUERY PLAN.

Không assert toàn bộ plan text vì optimizer có thể đổi plan hợp lệ theo version/statistics. Dùng latency budget và guardrail có ý nghĩa như tránh full scan bảng lớn trong luồng nhạy cảm, cardinality bất thường hoặc spill.

### 23.3. Performance budget

| Query | Dataset | p95 mục tiêu ví dụ | Guardrail |
| --- | --- | --- | --- |
| getOrder | 1 triệu đơn | dưới 100 ms | Tra theo PK |
| listOrders | 1 triệu đơn | dưới 300 ms | Pagination và index |
| revenueByDay | 12 tháng | dưới 2 s | Không nhân bản khi JOIN |
| customerBalance | 10 triệu ledger rows | dưới 500 ms | Index theo customer/time |

Đây là ví dụ, không phải chuẩn chung. Ngưỡng thật phải dựa trên SLO và môi trường.

## 24. CI/CD cho query regression

~~~mermaid
flowchart TD
    A["Pull request"] --> B["Build application"]
    B --> C["Start isolated test DB"]
    C --> D["Run migrations from supported version"]
    D --> E["Schema contract tests"]
    E --> F["Load fixtures"]
    F --> G["Query regression suite"]
    G --> H["Data invariants and API tests"]
    H --> I["Performance smoke checks"]
    I --> J["Save sanitized reports"]
~~~

Có thể chia pipeline:
- Fast tests cho mỗi pull request.
- Migration integration tests từ version cũ.
- Compatibility tests cho app/schema trong giai đoạn expand.
- Data reconciliation trên bản sao đã ẩn danh.
- Performance tests định kỳ hoặc trước release.
- Production smoke checks chỉ đọc sau deploy.

### 24.1. Pin DBMS version và config

Test trên version khác production có thể bỏ sót semantics. Pin image/version, extension, encoding, timezone, collation và config quan trọng. Nếu hỗ trợ nhiều major version, chạy ma trận CI có chủ đích.

### 24.2. Container database

Service container hoặc Testcontainers giúp tạo DB riêng cho job. Pin image tag, health check, charset, timezone, extension và config. Image mặc định không nhất thiết giống production.

### 24.3. Artifact

Có thể lưu migration version, DBMS version, test name, sanitized expected/actual diff, query fingerprint, timing và fixture version. Không lưu credential, connection string có mật khẩu hoặc dữ liệu cá nhân nguyên bản.

## 25. Quản lý baseline và expected result

Khi nghiệp vụ thay đổi hợp lệ, expected result cũng có thể phải thay đổi. Quy trình:
1. Xác định test và output nào đổi.
2. Đối chiếu spec/ticket hoặc quyết định nghiệp vụ.
3. Tạo fixture tái hiện thay đổi.
4. Tính expected độc lập.
5. Cập nhật snapshot/expected.
6. Review diff và output contract.
7. Giữ test cho hành vi cũ vẫn còn hiệu lực.
8. Ghi version/schema mà baseline áp dụng.

Không cập nhật snapshot chỉ để CI xanh. Nếu không giải thích được diff, điều tra trước.

Có thể version hóa fixture/snapshot theo schema version hoặc dialect. Không dùng một snapshot chung cho mọi DBMS nếu biểu diễn hợp lệ khác nhau.

## 26. Điều tra khi regression test thất bại

Nguyên nhân có thể là migration chạy sai thứ tự, fixture sai, cột cũ còn trong query, JOIN nhân bản, backfill thiếu, timezone/locale khác, cache chưa refresh, mapping sai hoặc DBMS config không giống production.

Quy trình:
1. Xác nhận DBMS/version và migration version.
2. Chạy lại test đơn lẻ với fixture cố định.
3. Kiểm tra migration history và schema metadata.
4. So sánh actual/expected theo khóa nghiệp vụ.
5. Phân loại sai khác: schema, type, value, cardinality, order hoặc performance.
6. Kiểm tra backfill, FK, unique và index.
7. Xem execution plan nếu liên quan hiệu năng.
8. Reproduce trên cùng dialect/version/config.
9. Sửa nguyên nhân và thêm test cho trường hợp vừa phát hiện.

Diff hữu ích nên chỉ ra khóa cụ thể:

~~~text
Query: listOrdersForCustomer
Migration: 042 -> 043

Expected rows: 2
Actual rows:   3

Unexpected:
  order_id=101, payment_id=9202

Contract:
  One row per order

Observed:
  JOIN now returns one row per payment

Result:
  FAIL: output cardinality changed
~~~

Thông báo theo khóa giúp xác định nguyên nhân nhanh hơn một blob JSON lớn.

## 27. Checklist regression test sau schema change

### Trước migration

- Đã lập danh mục query, view, procedure, job, API và report phụ thuộc?
- Đã định nghĩa output contract?
- Có fixture cho 0-1-n, NULL, duplicate và dữ liệu biên?
- Expected result có độc lập?
- Đã xác định thay đổi chủ đích?
- DBMS/version có giống production?

### Sau migration

- Migration history đúng version?
- Table/column/type/default/nullability đúng?
- PK/FK/unique/check/index đúng?
- Dữ liệu cũ backfill đầy đủ?
- Không có orphan/duplicate ngoài mong đợi?
- Query còn compile và chạy?
- Output names/types/nullability đúng?
- Row count và cardinality đúng?
- Tổng, count, ranking, date/time và NULL đúng?
- API/ORM/export mapping đúng?
- View/procedure/trigger/permission còn hoạt động?
- App cũ/mới tương thích trong cửa sổ deploy?

### Trước deploy

- Query regression suite pass?
- Invariant và reconciliation pass?
- Performance smoke không vượt budget?
- Có recovery/forward-fix plan?
- CI artifact không chứa bí mật?
- Có metrics/logs để phát hiện lỗi sau deploy?

## 28. Nguyên tắc thực hành

- **Test hợp đồng, không chỉ test câu SQL.** Query chạy được chưa chứng minh consumer nhận đúng shape và ý nghĩa.
- **Fixture phải làm lộ quan hệ.** Nhiều hàng con, không có hàng con, NULL và duplicate giúp phát hiện lỗi JOIN/aggregate.
- **Expected phải độc lập.** Không dùng lại logic đang test để tự tạo kết quả chuẩn.
- **Thứ tự chỉ là contract khi có ORDER BY.** Nếu thứ tự quan trọng, định nghĩa tie-break.
- **Migration phải chạy trên dữ liệu cũ.** Schema trống không đại diện production.
- **Kiểm tra compatibility.** Rolling deployment có thể có nhiều app version cùng tồn tại.
- **Hiệu năng là hành vi vận hành.** Query đúng nhưng vượt SLO vẫn là regression.
- **Snapshot cần review.** Snapshot không thay thế spec nghiệp vụ.
- **Test từng dialect.** Cú pháp giống nhau không bảo đảm semantics giống nhau.

## 29. Tài liệu tham khảo chính thức

Đối chiếu theo DBMS, driver và migration framework đang dùng:

- **PostgreSQL:** [Information Schema](https://www.postgresql.org/docs/current/information-schema.html), [System Catalogs](https://www.postgresql.org/docs/current/catalogs.html), [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html), [Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html).
- **MySQL:** [INFORMATION_SCHEMA](https://dev.mysql.com/doc/refman/8.4/en/information-schema.html), [SHOW CREATE TABLE](https://dev.mysql.com/doc/refman/8.4/en/show-create-table.html), [EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html).
- **SQL Server:** [Catalog Views](https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/catalog-views-transact-sql), [sys.columns](https://learn.microsoft.com/en-us/sql/relational-databases/system-catalog-views/sys-columns-transact-sql), [Execution Plans](https://learn.microsoft.com/en-us/sql/relational-databases/performance/execution-plans).
- **Oracle:** [Data Dictionary Views](https://docs.oracle.com/en/database/oracle/oracle-database/23/refrn/data-dictionary-views.html), [DBMS_METADATA](https://docs.oracle.com/en/database/oracle/oracle-database/23/arpls/DBMS_METADATA.html), [Execution Plans](https://docs.oracle.com/en/database/oracle/oracle-database/23/tgsql/generating-and-displaying-execution-plans.html).
- **SQLite:** [PRAGMA](https://www.sqlite.org/pragma.html), [EXPLAIN QUERY PLAN](https://www.sqlite.org/eqp.html), [Foreign Key Support](https://www.sqlite.org/foreignkeys.html).
- **Python:** [pytest fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html), [psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).
- **Migration frameworks:** [Flyway](https://documentation.red-gate.com/flyway), [Liquibase](https://docs.liquibase.com/).

## 30. Kết luận

Kiểm thử hồi quy sau thay đổi lược đồ cần chứng minh ba điều:

1. **Schema đúng hợp đồng:** bảng, cột, kiểu, constraint, index và object phụ thuộc được tạo đúng.
2. **Dữ liệu và query đúng:** migration không làm mất/nhân bản dữ liệu; SQL trả đúng shape, giá trị, cardinality, NULL và thứ tự đã cam kết.
3. **Ứng dụng vận hành đúng:** mapping, API, job, báo cáo và các version tương thích; hiệu năng nằm trong giới hạn chấp nhận.

Một quy trình vững chắc bắt đầu từ danh mục phụ thuộc, output contract, fixture có chủ đích và expected result độc lập. Sau đó dựng DB ở version cũ, chạy migration, kiểm tra schema, chạy query regression, đối soát invariant, kiểm tra compatibility và performance trong CI.

Điều cần bảo vệ khi schema thay đổi là **ý nghĩa dữ liệu mà các consumer đang dựa vào**. Regression test biến ý nghĩa đó thành hợp đồng có thể chạy tự động và phát hiện khác biệt trước khi chúng tới production.
