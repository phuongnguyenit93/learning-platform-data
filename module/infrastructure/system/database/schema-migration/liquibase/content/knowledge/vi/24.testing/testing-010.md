# Tạo bộ dữ liệu đại diện cho bảng lớn và trường hợp biên

Một migration có thể chạy đúng với vài chục hàng mẫu nhưng thất bại khi áp dụng lên bảng production có hàng triệu hoặc hàng trăm triệu bản ghi. Dữ liệu thực tế thường có phân bố lệch, nhiều giá trị NULL, khóa ngoại tập trung vào một số khách hàng lớn, chuỗi có độ dài rất khác nhau, bản ghi cũ từ nhiều năm trước và những giá trị ngoại lệ mà fixture đơn giản không có. Nếu bộ dữ liệu kiểm thử không phản ánh những đặc điểm này, nhóm có thể đánh giá thấp thời gian backfill, bỏ sót lỗi constraint, không phát hiện tràn kiểu dữ liệu hoặc không nhìn thấy lock kéo dài.

Bài học thuộc chương **Kiểm thử** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Bài này trình bày cách thiết kế bộ dữ liệu đại diện cho bảng lớn và trường hợp biên để kiểm thử changeset DDL/DML, backfill, constraint, index, nâng cấp từ phiên bản cũ và hiệu năng migration. Trọng tâm là hiểu dữ liệu trước khi sinh fixture, mô phỏng đúng phân bố và quan hệ, tạo dữ liệu tổng hợp có thể tái lập, kiểm tra các giá trị ở biên và lưu bằng chứng để những lần chạy sau có thể so sánh.

Sau bài học, bạn có thể:

1. Xác định những đặc điểm dữ liệu ảnh hưởng đến migration và hiệu năng.
2. Phân biệt bộ dữ liệu smoke, functional, representative và scale/performance.
3. Thiết kế fixture giữ được cardinality, skew, correlation, độ dài và phân bố thời gian.
4. Tạo dữ liệu tổng hợp có seed cố định và bảo toàn referential integrity.
5. Bao phủ NULL, empty, boundary, duplicate, Unicode, timezone và giá trị legacy bất thường.
6. Dùng dữ liệu đại diện để kiểm tra backfill, constraint, index, rollback và idempotency.
7. Đánh giá quy mô, thời gian chạy, lock, I/O và tác động tới ứng dụng.
8. Tổ chức fixture an toàn, version hóa và tái lập trong CI/CD.

## 1. Vì sao dữ liệu mẫu nhỏ thường gây hiểu lầm?

Giả sử một changeset thêm cột mới rồi backfill dữ liệu cho bảng orders. Với 100 hàng, câu lệnh UPDATE có thể hoàn tất trong vài mili giây. Nhưng trên production, bảng có 80 triệu hàng, nhiều hàng đã bị soft-delete, một số order có payload JSON lớn và các bản ghi tập trung vào vài tenant lớn. Cùng một câu lệnh có thể tạo transaction kéo dài, tăng WAL/redo, giữ lock lâu và làm replication lag.

Một fixture nhỏ thường không thể hiện:

- Quy mô và tốc độ tăng trưởng của bảng.
- Phân bố giá trị, cardinality và skew.
- Tương quan giữa các cột.
- Tỷ lệ NULL, empty và dữ liệu ngoại lệ.
- Số lượng bản ghi liên quan trên mỗi khóa ngoại.
- Độ dài chuỗi, kích thước JSON/BLOB và dữ liệu lớn.
- Phân bố thời gian, dữ liệu cũ và dữ liệu mới.
- Tính tập trung truy cập vào tenant hoặc partition.
- Các index, constraint và trạng thái dữ liệu lịch sử.

Một bộ fixture tốt không nhất thiết sao chép toàn bộ production. Nó cần tái hiện những thuộc tính có ảnh hưởng tới logic migration và hành vi DBMS.

### 1.1. Tính đại diện không đồng nghĩa với dữ liệu giống từng hàng

Mục tiêu của dữ liệu tổng hợp là giữ những đặc điểm quan trọng, ví dụ:

- Tỷ lệ NULL của cột legacy.
- Tỷ lệ trạng thái A/I/U/unknown.
- Phân bố số order trên mỗi customer.
- Phần trăm tenant lớn và tenant nhỏ.
- Độ dài median, p95 và maximum của chuỗi.
- Tỷ lệ dữ liệu cũ hơn một mốc thời gian.
- Số lượng duplicate hoặc giá trị không hợp lệ cần kiểm tra.
- Tỷ lệ bản ghi có quan hệ nhiều cấp.

Không cần giữ tên, email hoặc giá trị nhận diện thật nếu chúng không ảnh hưởng đến bài test. Với nhiều migration, một fixture tổng hợp có phân bố đúng còn hữu ích hơn bản sao dữ liệu production đã bị xáo trộn hoặc ẩn danh hóa sai cách.

## 2. Bắt đầu bằng profiling dữ liệu

Trước khi tạo fixture, hãy xác định các thuộc tính của bảng nguồn. Nếu có thể, profiling trên snapshot đã được phê duyệt hoặc dữ liệu tổng hợp có đặc điểm tương đương. Không truy cập hoặc xuất dữ liệu nhạy cảm vượt phạm vi quyền được cấp.

Một profile hữu ích thường gồm:

| Nhóm | Chỉ số cần xem |
|---|---|
| Quy mô | Tổng số hàng, kích thước bảng, kích thước index |
| Cardinality | Số giá trị phân biệt của từng cột |
| Nullability | Tỷ lệ NULL và empty |
| Phân bố | Tần suất theo trạng thái, tenant, loại bản ghi |
| Skew | Top key có số hàng lớn nhất và tỷ trọng của chúng |
| Độ dài | Min, median, p95, p99, max của chuỗi/payload |
| Thời gian | Min/max timestamp, phân bố theo ngày/tháng/năm |
| Quan hệ | Số hàng con trên mỗi khóa cha, orphan count |
| Tính duy nhất | Duplicate theo khóa nghiệp vụ |
| Chất lượng | Giá trị sai định dạng, legacy code và ngoại lệ |

### 2.1. Đếm tổng số hàng và dung lượng

Ví dụ PostgreSQL:

~~~sql
SELECT COUNT(*) AS total_rows
FROM app.orders;
~~~

Dung lượng bảng và index có thể được kiểm tra bằng các hàm catalog của PostgreSQL:

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('app.orders')) AS table_size,
    pg_size_pretty(pg_indexes_size('app.orders')) AS indexes_size,
    pg_size_pretty(pg_total_relation_size('app.orders')) AS total_size;
~~~

Đây là truy vấn PostgreSQL. DBMS khác có catalog và hàm đo kích thước riêng. Dung lượng không chỉ phụ thuộc số hàng mà còn phụ thuộc datatype, row format, fill factor, compression và index.

### 2.2. Profiling NULL và cardinality

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(status) AS non_null_status,
    COUNT(*) - COUNT(status) AS null_status,
    COUNT(DISTINCT status) AS distinct_status
FROM app.orders;
~~~

Tỷ lệ NULL:

~~~sql
SELECT
    100.0 * SUM(CASE WHEN status IS NULL THEN 1 ELSE 0 END)
      / NULLIF(COUNT(*), 0) AS null_percent
FROM app.orders;
~~~

Tỷ lệ cần được tính trên đúng tập dữ liệu liên quan. Nếu migration chỉ tác động bản ghi active, profile toàn bảng có thể che giấu phân bố riêng của tập đó.

### 2.3. Profiling phân bố giá trị

~~~sql
SELECT
    status,
    COUNT(*) AS row_count,
    100.0 * COUNT(*) / SUM(COUNT(*)) OVER () AS percentage
FROM app.orders
GROUP BY status
ORDER BY row_count DESC;
~~~

Kết quả giúp xác định fixture cần bao nhiêu hàng cho từng trạng thái. Không nên sinh đều các trạng thái nếu production có 95% ACTIVE, 4% INACTIVE và 1% UNKNOWN, trừ khi bài test chủ đích kiểm tra từng nhánh với tỷ lệ cân bằng.

## 3. Cardinality, skew và tương quan giữa các cột

Ba thuộc tính này thường ảnh hưởng mạnh đến query plan, index và thời gian migration.

**Cardinality** là số lượng giá trị phân biệt. Cột status có cardinality thấp; customer_id có thể có cardinality cao.

**Skew** là mức độ phân bố không đồng đều. Một tenant có thể chiếm 40% dữ liệu trong khi hàng nghìn tenant còn lại chia nhau 60%.

**Correlation** là quan hệ giữa các cột. Ví dụ đơn hàng của tenant lớn có thể tập trung trong vài tháng gần đây; trạng thái CANCELLED có thể thường xuất hiện ở đơn cũ.

Nếu fixture tạo customer_id đồng đều và timestamp ngẫu nhiên độc lập, nó có thể làm mất skew/correlation và tạo query plan khác production.

### 3.1. Ví dụ phân bố tenant

Một hệ thống SaaS có 10.000 tenant:

- 8.000 tenant nhỏ, mỗi tenant có vài trăm hàng.
- 1.900 tenant trung bình, mỗi tenant có vài chục nghìn hàng.
- 100 tenant lớn, mỗi tenant có hàng triệu hàng.

Nếu sinh 10.000 tenant với số order bằng nhau, fixture không phản ánh workload thực. Nên tạo các nhóm tenant theo quy mô và giữ tỷ trọng tổng hàng tương ứng.

### 3.2. Đo top key

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS row_count
FROM app.orders
GROUP BY tenant_id
ORDER BY row_count DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Cú pháp giới hạn số hàng khác nhau theo DBMS; PostgreSQL có thể dùng LIMIT. Dữ liệu fixture nên có một số tenant hot key với tỷ lệ tương đương, vì backfill hoặc index theo tenant có thể bị skew.

### 3.3. Giữ tương quan

Ví dụ phân bố trạng thái theo thời gian:

~~~sql
SELECT
    DATE_TRUNC('month', created_at) AS month_bucket,
    status,
    COUNT(*) AS row_count
FROM app.orders
GROUP BY DATE_TRUNC('month', created_at), status
ORDER BY month_bucket, status;
~~~

Đây là cú pháp PostgreSQL. Nếu trạng thái và thời gian có tương quan, fixture cần giữ quan hệ này. Việc lấy ngẫu nhiên độc lập từng cột có thể tạo ra những tổ hợp hiếm gặp trong production hoặc bỏ mất tổ hợp quan trọng.

## 4. Chọn cấp độ dữ liệu theo mục tiêu test

Không phải mọi pipeline đều cần dựng hàng chục triệu bản ghi. Hãy chia fixture thành các cấp:

| Cấp độ | Quy mô tham khảo | Mục tiêu | Thời điểm |
|---|---:|---|---|
| Smoke | Vài chục đến vài trăm hàng | Xác nhận migration cơ bản chạy | Mỗi commit |
| Functional | Vài nghìn đến vài chục nghìn hàng | Mapping, constraint, edge cases | Pull request |
| Representative | Tỷ lệ và phân bố gần production, quy mô vừa/lớn | Query plan, backfill, skew | CI tích hợp/nightly |
| Scale/performance | Hàng triệu hoặc quy mô theo mục tiêu vận hành | Thời gian, lock, I/O, replication | Trước release hoặc theo lịch |

Các con số chỉ là ví dụ. Chọn quy mô dựa trên DBMS, giới hạn runner, thời gian CI và rủi ro migration.

### 4.1. Tách fixture theo mục tiêu

Có thể tổ chức dữ liệu thành các nhóm:

- baseline: dữ liệu hợp lệ tối thiểu.
- representative: phân bố gần workload thật.
- edge-cases: NULL, duplicate, boundary và malformed values.
- scale: dữ liệu lớn để đo hiệu năng.
- concurrency: dữ liệu có hot key hoặc cùng partition để tạo contention.
- legacy: dữ liệu được tạo theo schema/release cũ.

Không trộn tất cả vào một file seed duy nhất nếu việc chọn bộ dữ liệu khác nhau theo test sẽ khó kiểm soát.

## 5. Thiết kế ma trận trường hợp biên

Bảng lớn thường có nhiều trường hợp biên hơn một bảng mới tạo. Hãy lập ma trận theo datatype và quy tắc nghiệp vụ.

| Nhóm | Trường hợp cần có |
|---|---|
| NULL/empty | NULL, chuỗi rỗng, khoảng trắng |
| Số nguyên | Min, max, âm, 0, vượt giới hạn |
| Decimal | Precision/scale tối đa, rounding, overflow |
| Chuỗi | Rỗng, độ dài 1, max length, vượt max |
| Unicode | Dấu tiếng Việt, ký tự kết hợp, emoji nếu hỗ trợ |
| Thời gian | Biên ngày, năm nhuận, timezone, DST |
| Khóa | Duplicate, key lớn, key có khoảng trống |
| Quan hệ | Parent-child, orphan, nhiều con trên một cha |
| JSON/BLOB | Empty, payload lớn, cấu trúc lồng sâu |
| Legacy | Mã cũ, giá trị không biết, format cũ |
| Trạng thái | Active, inactive, deleted, archived |
| Đồng thời | Hàng mới/đang sửa trong lúc backfill |

Không nhất thiết đưa mọi trường hợp vào cùng một fixture. Có thể tách test case riêng để xác định rõ dữ liệu nào khiến migration pass hoặc fail.

## 6. NULL, empty và giá trị mặc định

NULL, chuỗi rỗng và khoảng trắng không tương đương nhau.

| Giá trị nguồn | Ý nghĩa có thể có | Rủi ro khi migrate |
|---|---|---|
| NULL | Chưa biết/chưa nhập | Backfill bỏ sót |
| Chuỗi rỗng | Đã nhập chuỗi rỗng | Mapping khác NULL |
| Khoảng trắng | Chỉ có whitespace | Trim hoặc validation |
| N/A | Mã quy ước | Cần mapping rõ |
| unknown | Giá trị legacy | Khác biệt hoa/thường |

Khi thêm NOT NULL, fixture phải có NULL để xác minh backfill hoặc default. Khi chuẩn hóa chuỗi, phải kiểm tra empty và whitespace riêng.

Ví dụ thống kê:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(CASE WHEN legacy_code IS NULL THEN 1 ELSE 0 END) AS null_rows,
    SUM(CASE WHEN legacy_code = '' THEN 1 ELSE 0 END) AS empty_rows,
    SUM(CASE WHEN TRIM(legacy_code) = '' THEN 1 ELSE 0 END) AS blank_rows
FROM app.customer;
~~~

Cần lưu ý biểu thức TRIM và cách DBMS xử lý chuỗi rỗng có thể khác nhau. Oracle xem chuỗi rỗng trong VARCHAR2 như NULL; fixture cho Oracle cần phản ánh semantics đó.

### 6.1. Test default có phân biệt insert và existing rows

Thêm DEFAULT cho cột không phải lúc nào cũng đồng nghĩa các hàng cũ nhận giá trị đó theo cùng cách trên mọi DBMS và change type. Kiểm tra riêng:

- Giá trị của hàng hiện có sau migration.
- Giá trị khi insert mới bỏ qua cột.
- Giá trị khi insert truyền NULL tường minh.
- Hành vi của ứng dụng/ORM.
- Default expression có phụ thuộc thời gian hoặc sequence không.

Không chỉ assert column_default trong catalog.

## 7. Giá trị số và biên datatype

Đổi kiểu hoặc thêm constraint số học cần fixture có giá trị ở biên:

- Số nguyên nhỏ nhất/lớn nhất.
- Giá trị âm, 0 và dương.
- Decimal có đủ precision và scale.
- Giá trị có nhiều chữ số thập phân.
- Giá trị vượt precision.
- Giá trị có thể gây overflow khi nhân/chia.
- Giá trị NULL.
- Giá trị được lưu như chuỗi nhưng không phải số.

Ví dụ cột decimal(12,2) có giới hạn số chữ số tổng và số chữ số sau dấu thập phân. Test cần bao phủ giá trị hợp lệ gần biên và giá trị vượt biên để xác nhận DBMS từ chối hoặc chuyển đổi theo đúng quy tắc.

### 7.1. Không tự ý làm tròn dữ liệu

Nếu migration chuyển decimal sang integer hoặc scale nhỏ hơn, cần định nghĩa chính sách:

- Làm tròn half-up, half-even hay truncate?
- Có lưu phần dư không?
- Có từ chối giá trị không thể biểu diễn?
- Có ảnh hưởng tổng tiền và đối soát không?

Fixture nên có các giá trị ngay dưới, đúng tại và ngay trên ngưỡng làm tròn. So sánh tổng trước/sau để phát hiện sai lệch.

## 8. Độ dài chuỗi, Unicode và collation

Với VARCHAR/NVARCHAR, fixture nên có:

- Chuỗi rỗng.
- Một ký tự.
- Chuỗi đúng giới hạn.
- Chuỗi vượt giới hạn một ký tự.
- Tiếng Việt có dấu.
- Ký tự Unicode ngoài BMP nếu DBMS hỗ trợ.
- Ký tự tổ hợp và ký tự dựng sẵn.
- Khoảng trắng đầu/cuối.
- Chữ hoa/thường.
- Chuỗi có dấu nháy hoặc ký tự escape.

Ví dụ dữ liệu minh họa:

~~~sql
INSERT INTO app.customer_test (id, display_name)
VALUES
    (1, 'An'),
    (2, 'Nguyễn Thị Ánh'),
    (3, 'Ánh'),
    (4, 'Tên có khoảng trắng  '),
    (5, 'Customer Unicode');
~~~

Các literal Unicode và kiểu chuỗi phụ thuộc DBMS/encoding. Hãy xác minh collation, normalization và JDBC driver. Hai chuỗi nhìn giống nhau có thể khác chuỗi code point; một phép so sánh có thể coi chúng bằng nhau hoặc khác nhau tùy collation.

### 8.1. Trường hợp vượt max length

Không chỉ tạo chuỗi có độ dài tối đa. Cần một test riêng với chuỗi dài hơn giới hạn để xác định hành vi mong đợi: migration phải dừng, dữ liệu phải được rút gọn theo quy tắc hay phải chuyển sang datatype lớn hơn.

Không dùng LEFT/SUBSTRING để cắt dữ liệu âm thầm nếu nghiệp vụ chưa phê duyệt mất thông tin.

## 9. Timestamp, timezone và dữ liệu lịch sử

Migration liên quan ngày giờ dễ lỗi khi dữ liệu cũ có nhiều timezone hoặc quy ước lưu khác nhau.

Fixture nên có:

- Thời điểm sát nửa đêm UTC.
- Thời điểm sát ranh giới ngày theo timezone nghiệp vụ.
- Ngày đầu/cuối tháng.
- Năm nhuận và ngày 29/02.
- Thời điểm chuyển DST nếu DBMS/application dùng timezone có DST.
- Timestamp có và không có timezone.
- Dữ liệu rất cũ và tương lai ngoài dự kiến.
- NULL và default timestamp.
- Giá trị có độ chính xác mili/micro/nano giây.

### 9.1. Không giả định timestamp không timezone là UTC

Kiểu timestamp và cách JDBC driver chuyển đổi phụ thuộc DBMS và datatype. Cần ghi rõ hợp đồng:

- Lưu instant UTC hay local date-time?
- Timezone nghiệp vụ là gì?
- Ứng dụng gửi offset hay local time?
- Migration chuyển đổi timezone hay chỉ đổi datatype?
- Có làm thay đổi ngày hiển thị theo người dùng không?

Test cùng một instant qua DBMS, JDBC và ứng dụng để xác minh không bị lệch giờ.

### 9.2. Dữ liệu lịch sử có phân bố thời gian

Nếu production chứa dữ liệu 5 năm nhưng fixture chỉ có 1 ngày, migration có thể không gặp partition cũ, index cũ hoặc giá trị theo quy tắc nghiệp vụ đã thay đổi theo thời gian. Tạo dữ liệu theo các giai đoạn release, không chỉ rải timestamp ngẫu nhiên.

## 10. Khóa chính, khóa ngoại và quan hệ dữ liệu

Dữ liệu đại diện phải giữ quan hệ thực tế giữa bảng cha và bảng con.

~~~text
tenant
  └── customer
        └── orders
              └── order_items
                    └── product
~~~

Một fixture chỉ sinh orders mà không có parent hợp lệ sẽ không chạy được khi có foreign key. Ngược lại, nếu chỉ sinh mỗi customer một order, test sẽ bỏ qua trường hợp một customer có hàng chục nghìn order.

Cần bao phủ:

- Parent không có child.
- Parent có một child.
- Parent có rất nhiều child.
- Child tham chiếu đúng parent.
- Orphan legacy nếu nguồn có và migration phải xử lý.
- Khóa ngoại NULL nếu cho phép.
- Duplicate business key.
- Quan hệ vòng hoặc dependency nhiều cấp nếu có.

### 10.1. Sinh dữ liệu theo thứ tự dependency

Khi có foreign key, thường tạo parent trước rồi tạo child. Nếu cần mô phỏng orphan legacy, phải thực hiện trong fixture riêng với constraint được kiểm soát, hoặc tạo dữ liệu trước khi constraint được thêm theo đúng baseline test.

Không tắt constraint một cách toàn cục rồi quên bật lại. Test phải xác minh trạng thái constraint sau setup.

### 10.2. Kiểm tra orphan

~~~sql
SELECT c.customer_id, COUNT(*) AS orphan_rows
FROM app.orders c
LEFT JOIN app.customer p ON p.id = c.customer_id
WHERE c.customer_id IS NOT NULL
  AND p.id IS NULL
GROUP BY c.customer_id;
~~~

Kết quả phải rỗng nếu invariant yêu cầu mọi order có customer hợp lệ. Nếu fixture cố tình có orphan để test cleanup, kết quả mong đợi phải được ghi rõ.

## 11. Duplicate và uniqueness

Bảng lớn có thể chứa duplicate do dữ liệu lịch sử, import hoặc quy tắc unique trước đây chưa được áp dụng. Khi thêm unique constraint/index, fixture cần có:

- Khóa hoàn toàn duy nhất.
- Duplicate chính xác.
- Duplicate sau normalize/trim/lowercase.
- NULL trong cột unique.
- Duplicate chỉ khác hoa/thường.
- Duplicate theo composite key.
- Duplicate trong một tenant nhưng hợp lệ ở tenant khác nếu uniqueness scoped theo tenant.

Ví dụ:

~~~sql
SELECT tenant_id, LOWER(TRIM(email)), COUNT(*)
FROM app.customer
GROUP BY tenant_id, LOWER(TRIM(email))
HAVING COUNT(*) > 1;
~~~

Nếu migration tạo unique index trên biểu thức hoặc normalized key, test phải kiểm tra duplicate theo đúng biểu thức đó. Đếm duplicate trên raw column có thể bỏ sót.

### 11.1. Không xóa duplicate tự động trong fixture chung

Một test riêng có thể xác minh migration phát hiện duplicate và dừng. Một test khác có thể xác minh quy trình dedup đã được phê duyệt. Giữ hai trường hợp riêng để tránh fixture bị làm sạch trước khi test lỗi chạy.

## 12. Dữ liệu legacy không hợp lệ và chính sách xử lý

Dữ liệu cũ thường chứa mã không còn được ứng dụng hiện tại tạo ra:

- Status code đã ngừng dùng.
- Currency code sai hoặc chưa chuẩn hóa.
- Email sai định dạng.
- Mã quốc gia cũ.
- Chuỗi có ký tự điều khiển.
- ID tham chiếu không còn tồn tại.
- Giá trị số lưu trong text có dấu phân cách cục bộ.
- Dữ liệu bị truncate từ lần import trước.

Migration cần một chính sách cho từng nhóm:

| Chính sách | Hành vi | Khi phù hợp |
|---|---|---|
| HALT | Dừng migration nếu có giá trị không hợp lệ | Không thể tự suy ra cách sửa |
| MAP | Ánh xạ về giá trị chuẩn | Có quy tắc nghiệp vụ rõ |
| QUARANTINE | Chuyển bản ghi sang vùng xử lý riêng | Cần người kiểm tra |
| PRESERVE | Giữ dữ liệu cũ trong cột/archive | Cần khả năng đối chiếu |
| DROP | Loại bỏ dữ liệu | Chỉ khi được phê duyệt rõ và có bằng chứng |

Không để CASE ELSE tự động đổi mọi giá trị lạ thành UNKNOWN mà không có thống kê. Nếu chọn mapping fallback, phải đếm số hàng bị fallback và lưu bằng chứng.

## 13. JSON, XML, BLOB và payload lớn

Nếu bảng có cột JSON/XML hoặc dữ liệu nhị phân, fixture nên bao phủ:

- NULL.
- Empty document hoặc empty object/array.
- Payload nhỏ.
- Payload lớn gần giới hạn.
- Cấu trúc lồng sâu.
- Mảng rỗng và mảng nhiều phần tử.
- Trường thiếu, trường null và trường có giá trị.
- Unicode trong key/value.
- JSON không hợp lệ nếu dữ liệu legacy có thể chứa text chưa validate.
- Binary có kích thước và nội dung biên.

Ví dụ JSON:

~~~json
{
  "status": "ACTIVE",
  "metadata": {
    "source": "legacy-import",
    "tags": [],
    "optionalValue": null
  },
  "items": [
    {"code": "A", "quantity": 1},
    {"code": "B", "quantity": 999999}
  ]
}
~~~

Đây là dữ liệu minh họa. Cần kiểm tra kiểu JSON/JSONB/XML thực tế và cách DBMS validate. Nếu migration trích trường JSON sang cột riêng, fixture cần có trường thiếu, null, sai kiểu và giá trị vượt độ dài.

### 13.1. Payload lớn có thể làm thay đổi hiệu năng

Tạo vài hàng JSON rất lớn có thể hữu ích để test boundary, nhưng không đại diện cho phân bố kích thước toàn bảng. Kết hợp nhiều kích thước theo tỷ lệ: phần lớn payload nhỏ, một nhóm trung bình và một tỷ lệ nhỏ rất lớn nếu production có phân bố như vậy.

## 14. Soft delete, archive và partition

Nhiều hệ thống không xóa hàng ngay mà dùng deleted_at, is_deleted hoặc trạng thái archive. Migration cần xác định phạm vi:

- Có backfill cả hàng đã xóa mềm không?
- Hàng archived có nằm trong partition khác?
- Constraint có áp dụng cho deleted rows không?
- Unique index có predicate chỉ trên active rows không?
- Có dữ liệu retention hết hạn không?
- Partition cũ có cùng schema với partition mới không?

Fixture nên có active, soft-deleted, archived và expired records. Nếu chỉ tạo hàng active, test có thể bỏ sót điều kiện WHERE hoặc partial index.

### 14.1. Partitioned table

Với bảng partition theo ngày/tenant/region, kiểm tra:

- Partition hiện tại và partition cũ.
- Partition rỗng.
- Partition có dữ liệu lớn.
- Boundary của partition.
- Partition thiếu hoặc lệch schema.
- Index local/global theo DBMS.
- Dữ liệu nằm đúng partition.
- Migration áp dụng tới mọi partition theo hành vi DBMS.

Test một partition không chứng minh toàn bộ partitioned table đã được xử lý đúng.

## 15. Thiết kế quy mô bảng và phân bố dữ liệu

Không chỉ chọn một con số total_rows. Hãy xác định profile:

~~~text
Table: app.orders
Total rows: 20,000,000
Tenants: 10,000
Largest tenant share: 18%
NULL status: 2.5%
Legacy status values: A=72%, I=21%, U=5%, other=2%
Rows older than 3 years: 35%
Payload p50: 300 bytes
Payload p95: 4 KB
Payload p99: 32 KB
Maximum payload: 1 MB
Soft-deleted rows: 8%
~~~

Các con số trên chỉ là ví dụ. Profile thực tế cần lấy từ nguồn được phép hoặc được domain owner xác nhận.

Một bộ scale test có thể giảm tổng quy mô nhưng giữ tỷ lệ và một số hot key quan trọng. Tuy nhiên, một số hiện tượng chỉ xuất hiện ở quy mô thật, ví dụ B-tree depth, autovacuum, checkpoint, WAL volume và partition count. Đối với migration rủi ro cao, cần test trên quy mô gần production hoặc môi trường benchmark riêng.

### 15.1. Chọn số lượng hàng theo mục tiêu

- Test logic: đủ hàng để có mọi nhánh mapping.
- Test index: đủ cardinality và skew để planner có thống kê có ý nghĩa.
- Test backfill: đủ hàng để thấy batch/transaction behavior.
- Test lock: đủ workload cạnh tranh và query dài.
- Test storage: đủ payload và index để ước lượng dung lượng.
- Test partition: đủ partition cũ/mới và boundary.

Không chọn quy mô chỉ để CI chạy nhanh nếu mục tiêu là đánh giá performance.

## 16. Sinh dữ liệu tổng hợp có thể tái lập

Một fixture nên deterministic: cùng seed và cùng phiên bản generator sẽ tạo cùng dữ liệu hoặc cùng đặc điểm dữ liệu được cam kết.

Điều này giúp:

- So sánh kết quả giữa các commit.
- Điều tra lỗi có thể tái hiện.
- Đối chiếu thời gian migration.
- Phát hiện regression.
- Không phụ thuộc dữ liệu ngẫu nhiên thay đổi mỗi lần chạy.

Ghi nhận:

- Seed.
- Phiên bản generator.
- Quy tắc phân bố.
- Số lượng hàng.
- DBMS/version.
- Thứ tự tạo dữ liệu.
- Fixture version/hash.
- Các tham số thay đổi theo job.

### 16.1. Dùng seed cố định

Nếu dùng hàm random, truyền seed cố định hoặc tạo giá trị từ khóa hàng bằng hàm deterministic. Tránh gọi random không kiểm soát trong SQL/Java test data builder.

Nếu thứ tự sinh dữ liệu có thể thay đổi theo parallelism, không chỉ dựa vào một global random sequence. Có thể derive giá trị từ primary key để một hàng luôn nhận cùng dữ liệu.

### 16.2. Tách seed dữ liệu khỏi changeset production

Dữ liệu test nên được nạp bởi test fixture/setup riêng, không trộn vào changelog production nếu không phải dữ liệu tham chiếu thật sự cần triển khai.

Ví dụ cấu trúc:

~~~text
src/test/resources/
  db/
    baseline/
      release-2.4/
    fixtures/
      representative/
      edge-cases/
      scale/
    assertions/
      orders-after-migration.sql
~~~

Đường dẫn chỉ là gợi ý. Dữ liệu fixture không được include nhầm vào root changelog production.

## 17. Ví dụ sinh dữ liệu lớn bằng PostgreSQL

PostgreSQL có generate_series để tạo tập số liên tiếp. Ví dụ dưới đây tạo orders với phân bố status, tenant và timestamp xác định theo ID:

~~~sql
INSERT INTO app.orders (
    id,
    tenant_id,
    legacy_status,
    created_at,
    amount
)
SELECT
    n,
    CASE
        WHEN n % 100 < 18 THEN 1
        ELSE 2 + (n % 9999)
    END,
    CASE
        WHEN n % 100 < 72 THEN 'A'
        WHEN n % 100 < 93 THEN 'I'
        WHEN n % 100 < 98 THEN 'U'
        ELSE 'X'
    END,
    TIMESTAMP '2020-01-01 00:00:00'
        + (n % 2200) * INTERVAL '1 day',
    ((n % 1000000)::numeric / 100)::numeric(12,2)
FROM generate_series(1, 1000000) AS n;
~~~

Đây là ví dụ minh họa, không phải phân bố chung cho mọi hệ thống. Cần kiểm tra:

- Tenant 1 có thực sự nhận tỷ trọng mong muốn không.
- Phân bố status có đúng phần trăm đã định không.
- Timestamp có phản ánh phân bố production hay chỉ chu kỳ lặp.
- Amount có tạo giá trị âm/biên cần test không.
- Các khóa ngoại có tồn tại.
- ID không xung đột với fixture baseline.

Ví dụ dùng modulo để tạo phân bố xác định; nó phù hợp cho fixture lặp lại nhưng không tạo phân bố ngẫu nhiên độc lập. Nếu cần mô phỏng heavy-tail chính xác hơn, dùng bảng phân phối hoặc hàm mapping được kiểm tra riêng.

### 17.1. Tạo parent trước child

Ví dụ tạo tenant:

~~~sql
INSERT INTO app.tenant (id, name)
SELECT n, 'tenant-' || n
FROM generate_series(1, 10000) AS n;
~~~

Sau đó mới insert orders tham chiếu tenant_id. Nếu một số tenant hot key có số hàng lớn, generator phải giữ tỷ trọng đó thay vì chia đều.

### 17.2. Tránh tạo dữ liệu vô tình trùng khóa

Trước khi chạy fixture, xác định vùng ID dành riêng cho test. Có thể dùng dải ID riêng hoặc schema/database test mới. Không dùng ID ngẫu nhiên có thể trùng với dữ liệu baseline.

## 18. Sinh dữ liệu theo phân bố có trọng số

Một cách dễ kiểm soát là tạo bảng profile hoặc mapping để mỗi nhóm có số hàng xác định.

Ví dụ profile tenant:

~~~text
group       tenant_count     orders_per_tenant
small       8000             100
medium      1900             10000
large       100              1000000
~~~

Quy mô này rất lớn; khi test cục bộ có thể scale theo hệ số nhưng giữ tỷ lệ. Ghi rõ scale factor để không nhầm số liệu benchmark.

Có thể tạo một bảng fixture_profile trong database test hoặc cấu hình generator. Không đưa profile thử nghiệm vào schema production.

### 18.1. Giữ skew ở mức có chủ đích

Không nên chỉ có một tenant khổng lồ nếu production có nhiều hot tenant. Hãy tạo vài mức quy mô và kiểm tra top-N distribution sau khi seed.

### 18.2. Giữ tương quan thời gian

Ví dụ tenant lớn có dữ liệu mới nhiều hơn tenant nhỏ. Nếu profile tạo tenant_id và created_at độc lập, query theo tenant/time có thể có cardinality và selectivity khác production. Generator nên có quy tắc tương quan được mô tả và assertion kiểm tra.

## 19. Bộ dữ liệu trường hợp biên riêng

Không nên cố đưa mọi trường hợp lỗi vào bộ representative dataset, vì một số test cần migration dừng có chủ đích.

Có thể tổ chức:

| Fixture | Nội dung | Kỳ vọng |
|---|---|---|
| valid-minimal | Dữ liệu hợp lệ tối thiểu | Migration pass |
| representative | Phân bố gần production | Migration pass và invariant đạt |
| boundary-values | Min/max/length/precision/time | Kết quả đúng tại biên |
| invalid-legacy | Mã không hợp lệ, orphan, duplicate | HALT hoặc quarantine theo policy |
| nullable-mix | NULL, empty, whitespace | Mapping chính xác |
| large-payload | JSON/BLOB lớn | Không truncate/timeout ngoài dự kiến |
| high-skew | Hot tenant/key | Performance và query plan |
| concurrent-write | Hàng thay đổi trong backfill | Consistency theo thiết kế |

Tách fixture theo expected outcome giúp CI biết test nào pass khi migration thành công và test nào pass khi migration chủ động từ chối dữ liệu.

## 20. Kiểm thử migration trên fixture lớn

Một quy trình kiểm thử có thể thực hiện:

1. Tạo database test đúng DBMS/version.
2. Dựng schema baseline từ artifact release nguồn.
3. Nạp fixture representative và edge cases.
4. Xác minh profile trước migration.
5. Chạy Liquibase validate.
6. Chạy status và review update-sql.
7. Đo thời gian, lock và tài nguyên.
8. Chạy update.
9. Xác minh schema, dữ liệu và DATABASECHANGELOG.
10. Chạy test ứng dụng hoặc query nghiệp vụ.
11. Chạy rollback/recovery trên database disposable nếu phù hợp.
12. Lưu profile, seed, log và metrics.

### 20.1. Kiểm tra trước migration

Lưu số hàng, phân bố trạng thái, NULL count, duplicate count, orphan count và checksum/summary dữ liệu nếu phù hợp.

Ví dụ:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(status) AS non_null_status,
    COUNT(DISTINCT tenant_id) AS tenant_count,
    MIN(created_at) AS oldest_order,
    MAX(created_at) AS newest_order
FROM app.orders;
~~~

Không nhất thiết lưu từng giá trị dữ liệu. Có thể lưu aggregate để so sánh và bảo vệ quyền riêng tư.

### 20.2. Kiểm tra sau migration

Chạy cùng profile query sau migration và so sánh theo invariant:

- Tổng số hàng có thay đổi ngoài dự kiến không?
- Mapping status có đúng không?
- Có hàng NULL không được xử lý?
- Duplicate/orphan có tăng không?
- Cột mới có đúng datatype/nullability/default?
- Index/constraint đã ở trạng thái hợp lệ?
- Có changeset nào bị MARK_RAN ngoài dự kiến?

Không so sánh mọi aggregate theo kiểu phải bằng tuyệt đối nếu migration có chủ đích thay đổi dữ liệu; hãy định nghĩa expected delta.

## 21. Kiểm tra tính toàn vẹn bằng invariant

Một invariant mô tả điều phải luôn đúng sau migration.

Ví dụ:

- Mỗi order tham chiếu một tenant tồn tại.
- status thuộc tập giá trị được cho phép.
- Tổng số hàng không giảm ngoài tập được phê duyệt.
- amount nằm trong precision/scale hợp lệ.
- Không có duplicate theo business key.
- created_at không bị thay đổi khi migration không liên quan thời gian.
- Tổng tiền theo tenant không thay đổi ngoài quy tắc rounding được duyệt.

Ví dụ assertion:

~~~sql
SELECT COUNT(*) AS invalid_status_rows
FROM app.orders
WHERE status IS NULL
   OR status NOT IN ('ACTIVE', 'INACTIVE', 'UNKNOWN');
~~~

~~~sql
SELECT COUNT(*) AS orphan_rows
FROM app.orders o
LEFT JOIN app.tenant t ON t.id = o.tenant_id
WHERE t.id IS NULL;
~~~

Kỳ vọng thường là 0, nhưng cần ghi rõ nếu fixture cố ý có ngoại lệ.

### 21.1. Đối chiếu tổng hợp

Với migration đổi kiểu hoặc backfill tiền, có thể so sánh tổng theo nhóm:

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM app.orders
GROUP BY tenant_id;
~~~

Nếu dữ liệu được chuyển đổi có chủ đích, xác định cách tính expected total trước. So sánh tổng toàn bảng có thể che lỗi bù trừ giữa hai nhóm; nên đối chiếu theo tenant, trạng thái hoặc khoảng thời gian.

## 22. Đánh giá hiệu năng migration

Bộ dữ liệu lớn giúp đo:

- Tổng thời gian update.
- Thời gian từng changeset.
- Số hàng đọc/ghi.
- Lock wait và thời gian giữ lock.
- WAL/redo/transaction log.
- CPU, memory, disk I/O và temp space.
- Replication lag.
- Query latency của ứng dụng.
- Dung lượng table/index trước và sau.

### 22.1. Đo thời gian theo changeset

Log Liquibase có thể cho biết thời gian tổng thể và changeset. Nếu cần đo chi tiết hơn, pipeline có thể ghi timestamp trước/sau từng giai đoạn hoặc dùng telemetry DBMS.

Không chỉ so sánh thời gian tổng nếu một changeset tăng đột biến nhưng các bước khác giảm.

### 22.2. Không dùng một con số benchmark làm cam kết production

Thời gian phụ thuộc CPU, storage, cache, concurrent workload, DBMS config, statistics, network và replication. Benchmark trên máy developer không thể đại diện production nếu hạ tầng khác đáng kể.

Dùng benchmark để so sánh tương đối giữa các commit trong môi trường cố định; trước phát hành lớn cần xác nhận trên môi trường có đặc điểm gần mục tiêu.

## 23. Kiểm tra index và query plan với phân bố thật

Một index có thể có vẻ hữu ích trên dữ liệu đều nhưng không giúp nhiều khi một giá trị chiếm 99% bảng. Ngược lại, một index composite có thể cần thứ tự cột phù hợp với query workload.

Với PostgreSQL, có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM app.orders
WHERE tenant_id = 1
  AND status = 'ACTIVE';
~~~

EXPLAIN ANALYZE thực thi query; chỉ dùng trên database test hoặc truy vấn đã được đánh giá an toàn. Kết quả phụ thuộc statistics và cache. Sau khi seed dữ liệu lớn, cập nhật statistics theo quy trình DBMS trước khi so sánh plan.

Không suy ra index hiệu quả chỉ từ việc object tồn tại.

## 24. Dữ liệu đồng thời thay đổi trong khi migration

Production không phải ảnh chụp tĩnh. Ứng dụng có thể tiếp tục insert/update trong lúc backfill.

Fixture concurrency cần mô phỏng:

- Hàng mới được insert sau khi backfill bắt đầu.
- Hàng đang được cập nhật cùng lúc.
- Hai transaction cùng sửa một khóa.
- Tenant hot key tạo contention.
- Batch chạy song song với query ứng dụng.
- Hàng bị soft-delete giữa hai bước.
- Retry xử lý lại một batch đã hoàn thành.

Mục tiêu là xác minh migration không bỏ sót hoặc ghi đè dữ liệu mới ngoài thiết kế.

### 24.1. Kiểm tra điểm chốt và batch boundary

Nếu backfill theo ID range, fixture cần có:

- ID liên tục.
- ID có khoảng trống lớn.
- ID được sinh sau khi job bắt đầu.
- Hàng đã xóa.
- Một batch rỗng.
- Batch cuối nhỏ hơn batch size.
- Một hàng lỗi khiến batch fail.

Không giả định ID luôn liên tục hoặc timestamp tăng đơn điệu nếu hệ thống không bảo đảm điều đó.

## 25. Bộ dữ liệu cho partition và bảng lịch sử

Với bảng partitioned hoặc bảng lưu lịch sử, fixture nên có:

- Partition mới nhất.
- Partition cũ nhất còn retention.
- Partition rỗng.
- Partition có nhiều hàng.
- Hàng ở sát boundary.
- Hàng có timestamp NULL nếu schema cho phép.
- Partition thiếu hoặc chưa được tạo nếu cần test failure.
- Schema/index khác biệt do lịch sử nâng cấp.

Nếu migration chỉ chạy trên partition hiện tại nhưng production có partition cũ, dữ liệu cũ có thể bị bỏ qua. Test cần xác minh phạm vi DDL/DML thực tế của DBMS.

## 26. Quản lý fixture và quyền riêng tư

Dữ liệu production có thể chứa PII, thông tin tài chính hoặc bí mật kinh doanh. Không sao chép vào CI chỉ vì muốn có dữ liệu giống thật.

Ưu tiên:

1. Dữ liệu tổng hợp deterministic.
2. Snapshot đã được phê duyệt và ẩn danh hóa.
3. Mẫu dữ liệu giảm thiểu có kiểm soát.
4. Fixture nghiệp vụ được domain owner xác nhận.

Ẩn danh hóa phải giữ những đặc điểm cần test nhưng không thể khôi phục danh tính. Một phép thay email bằng chuỗi giả đơn giản có thể làm mất phân bố độ dài, duplicate, domain phổ biến và quan hệ giữa các bảng.

### 26.1. Bảo toàn quan hệ khi ẩn danh

Nếu đổi customer_id hoặc email, phải áp dụng mapping nhất quán ở mọi bảng liên quan. Nếu mỗi bảng thay giá trị độc lập, foreign key và join sẽ hỏng.

Có thể dùng tokenization deterministic cho khóa test, nhưng mapping phải được bảo vệ và không dùng chung secret production. Không đưa mapping có thể đảo ngược vào repository.

### 26.2. Không lưu dữ liệu nhạy cảm trong log

Log test nên ghi aggregate, số lượng và kết quả assertion. Tránh in toàn bộ row, email, token, địa chỉ hoặc payload cá nhân. Nếu cần giữ sample để điều tra, dùng kho có quyền truy cập và retention phù hợp.

## 27. Version hóa và tái tạo fixture

Fixture cũng là một phần của test contract. Khi thay đổi generator, kết quả benchmark có thể thay đổi dù migration không đổi.

Nên version hóa:

- Generator source hoặc seed scripts.
- Fixture profile.
- Seed và tham số.
- Schema baseline version.
- DBMS/version.
- Expected assertions.
- Hash của artifact fixture nếu được lưu riêng.

Khi sửa fixture, ghi rõ lý do và ảnh hưởng. Không thay phân bố để làm test pass mà không cập nhật tiêu chí.

### 27.1. Fixture phải tương thích với baseline

Một fixture dành cho release cũ cần được nạp sau khi dựng đúng schema nguồn. Fixture của schema hiện tại có thể tham chiếu cột chưa tồn tại trong baseline cũ.

Có thể duy trì fixture theo phiên bản nguồn:

~~~text
fixtures/
  release-2.4/
    customer-legacy.sql
    orders-legacy.sql
  release-2.5/
    customer-legacy.sql
    orders-legacy.sql
  current/
    representative.sql
    edge-cases.sql
~~~

Đây là cấu trúc minh họa. Tránh nhân bản fixture không cần thiết; dùng dữ liệu chung và adapter riêng khi schema giữa các release khác nhau.

## 28. Dọn dẹp và cô lập database test

Bộ dữ liệu lớn có thể chiếm nhiều dung lượng và thời gian. Cần thiết kế lifecycle:

- Database/schema riêng cho mỗi CI job.
- Không chia sẻ DATABASECHANGELOGLOCK giữa các job.
- Gắn fixture với pipeline run ID.
- Cleanup sau khi đã lưu log và metrics.
- Có TTL cho database test bị bỏ quên.
- Không cleanup database đang được dùng để điều tra failure.
- Không dùng production database làm nơi seed hoặc thử rollback.

Nếu dùng schema riêng trong cùng database, xác minh metadata table, sequence, role và object names cũng được cô lập. Chỉ đổi default schema không đủ nếu hai job vẫn dùng chung metadata lock.

## 29. Tích hợp fixture với kiểm thử Liquibase

Một luồng upgrade test có thể như sau:

~~~text
1. Start DBMS container ở version đã pin.
2. Tạo database/schema test.
3. Chạy changelog của release nguồn.
4. Nạp legacy fixture.
5. Chạy profile assertions trước migration.
6. Chạy Liquibase validate và status.
7. Sinh update-sql để review.
8. Chạy update.
9. Chạy schema/data assertions sau migration.
10. Chạy query ứng dụng hoặc Spring Boot integration test.
11. Thu thập timing/lock/DBMS metrics.
12. Lưu artifact, log, fixture profile và kết quả.
13. Hủy database test sau khi lưu bằng chứng.
~~~

Đối với test failure case, dùng database disposable riêng và xác minh migration dừng theo kỳ vọng. Không để test chủ động làm hỏng schema dùng chung.

### 29.1. Không seed fixture bằng changeset production ngoài chủ đích

Dữ liệu tham chiếu thực sự cần có trong production có thể được quản lý bằng Liquibase. Nhưng dữ liệu kiểm thử quy mô lớn và dữ liệu lỗi không nên bị include vào root changelog production.

Tách test setup khỏi migration artifact giúp tránh vô tình triển khai hàng triệu hàng giả hoặc dữ liệu không hợp lệ lên production.

## 30. Ví dụ test backfill với dữ liệu đại diện

Giả sử bảng orders có legacy_status và migration thêm status mới. Bộ dữ liệu nên chứa:

- 70% A.
- 20% I.
- 5% U.
- 2% NULL.
- 2% empty/whitespace.
- 1% giá trị không nhận diện.

Đây là profile minh họa. Test cần ghi rõ chính sách cho empty/whitespace và unknown.

Sau migration, kiểm tra mapping:

~~~sql
SELECT legacy_status, status, COUNT(*) AS row_count
FROM app.orders
GROUP BY legacy_status, status
ORDER BY legacy_status, status;
~~~

Kiểm tra số hàng chưa chuyển đổi:

~~~sql
SELECT COUNT(*) AS missing_status
FROM app.orders
WHERE status IS NULL;
~~~

Kiểm tra trạng thái ngoài tập cho phép:

~~~sql
SELECT COUNT(*) AS invalid_status
FROM app.orders
WHERE status NOT IN ('ACTIVE', 'INACTIVE', 'UNKNOWN');
~~~

Cần chú ý SQL three-valued logic: điều kiện NOT IN không bắt hàng NULL theo cách nhiều người kỳ vọng. Vì vậy nên kiểm tra NULL riêng hoặc viết điều kiện bao gồm status IS NULL.

### 30.1. Kiểm tra số hàng fallback

Nếu unknown được ánh xạ sang UNKNOWN, đếm riêng số hàng fallback và so với expected count. Nếu số lượng tăng đột biến, migration có thể đang âm thầm nuốt dữ liệu bất thường.

## 31. Lỗi thường gặp khi thiết kế fixture

| Hiện tượng | Nguyên nhân | Cách cải thiện |
|---|---|---|
| Migration nhanh ở test, chậm ở production | Fixture quá nhỏ | Thêm representative/scale dataset |
| Index test pass nhưng production query chậm | Thiếu skew/cardinality thực | Giữ phân bố và cập nhật statistics |
| NOT NULL fail trên production | Fixture không có NULL | Bổ sung NULL và kiểm tra backfill |
| Unique index fail | Fixture không có duplicate | Tạo duplicate theo business key/normalized key |
| Cast thất bại | Không có legacy value sai format | Thêm giá trị malformed và boundary |
| Dữ liệu sau migration sai ngày | Fixture chỉ dùng UTC đơn giản | Test timezone, DST và ranh giới ngày |
| Foreign key fail | Sinh child trước parent hoặc thiếu quan hệ | Tạo dependency graph và fixture nhất quán |
| Backfill bỏ sót hàng | ID range giả định liên tục | Thêm gap, late insert và deleted rows |
| Performance không tái lập | Seed/random thay đổi | Dùng deterministic seed và version generator |
| Benchmark dao động | Cache, statistics, hạ tầng khác nhau | Cố định môi trường và đo nhiều lần |
| Test lộ dữ liệu cá nhân | Copy production không kiểm soát | Synthetic data hoặc anonymization |
| Fixture production bị triển khai | Seed test nằm trong root changelog | Tách test resources khỏi changelog deploy |
| CI hết dung lượng | Scale fixture không có cleanup | Database/job isolation và TTL |
| Test chỉ kiểm tra số hàng | Bỏ sót mapping sai nhưng count bằng nhau | So sánh invariant theo nhóm và khóa |
| Ẩn danh làm mất skew | Thay giá trị ngẫu nhiên độc lập | Tokenize deterministic và giữ phân bố |
| Partition cũ không được test | Chỉ tạo partition mới nhất | Bổ sung partition boundary/legacy |
| Test pass bằng H2 nhưng fail DBMS đích | Khác dialect/locking/transaction | Test DBMS/version thật |
| Unknown bị ánh xạ âm thầm | CASE ELSE không có assertion | Đếm fallback và định nghĩa policy |

## 32. Checklist tạo bộ dữ liệu đại diện cho bảng lớn

- [ ] Đã xác định mục tiêu test: logic, upgrade, performance, lock hay concurrency.
- [ ] Đã profiling tổng hàng và dung lượng bảng/index.
- [ ] Đã đo cardinality và tỷ lệ NULL.
- [ ] Đã xác định skew và top hot keys/tenants.
- [ ] Đã kiểm tra tương quan giữa trạng thái, thời gian và tenant.
- [ ] Đã ghi min/median/p95/p99/max cho cột độ dài lớn.
- [ ] Có dữ liệu cũ, mới và phân bố thời gian đại diện.
- [ ] Có NULL, empty, whitespace và default cases.
- [ ] Có min/max, overflow, precision và scale boundary.
- [ ] Có Unicode, collation và chuỗi sát/vượt max length.
- [ ] Có timezone, DST, leap day và timestamp boundary khi liên quan.
- [ ] Có duplicate theo raw và normalized business key.
- [ ] Có parent-child, orphan và fan-out lớn.
- [ ] Có soft-delete, archive và partition cũ/mới nếu liên quan.
- [ ] Có JSON/XML/BLOB nhỏ, lớn và cấu trúc biên.
- [ ] Có legacy code hợp lệ, unknown và malformed.
- [ ] Generator deterministic và có seed/version.
- [ ] Fixture không chứa dữ liệu nhạy cảm chưa được phê duyệt.
- [ ] Dữ liệu tổng hợp giữ referential integrity theo mục tiêu.
- [ ] Có profile assertions trước và sau migration.
- [ ] Có invariant để kiểm tra mapping và bảo toàn dữ liệu.
- [ ] Có scale test phù hợp với kích thước bảng mục tiêu.
- [ ] Có test concurrent write/batch boundary khi migration chạy online.
- [ ] Test dùng DBMS/version và driver phù hợp.
- [ ] Fixture được tách khỏi root changelog production.
- [ ] Database test được cô lập và cleanup có kiểm soát.
- [ ] Lưu fixture version, seed, DBMS version, metrics và kết quả.
- [ ] Không dùng một aggregate duy nhất để kết luận dữ liệu đúng.

## 33. Câu hỏi tự kiểm tra

**1. Vì sao 1.000 hàng hợp lệ không đủ để kiểm tra migration trên bảng 100 triệu hàng?**

Vì nó không phản ánh thời gian scan/update, lock, WAL/redo, I/O, index, skew và phân bố dữ liệu ở quy mô lớn.

**2. Cardinality và skew khác nhau thế nào?**

Cardinality là số giá trị phân biệt; skew mô tả mức độ phân bố không đều giữa các giá trị.

**3. Vì sao phải giữ tương quan giữa tenant và timestamp?**

Vì query selectivity, phân bố dữ liệu và workload có thể phụ thuộc đồng thời vào hai cột; sinh độc lập có thể làm sai query plan và hiệu năng.

**4. NULL, empty và whitespace có nên gộp làm một không?**

Không mặc định. Chúng có semantics khác nhau và có thể được xử lý khác trong SQL, DBMS và ứng dụng.

**5. Dữ liệu tổng hợp deterministic có lợi ích gì?**

Cùng seed và generator giúp tái lập lỗi, so sánh benchmark và phát hiện regression.

**6. Vì sao cần test duplicate sau normalize?**

Unique index hoặc constraint có thể áp dụng trên biểu thức LOWER/TRIM, khiến các giá trị khác raw text trở thành duplicate.

**7. Có nên dùng dữ liệu production trong CI?**

Chỉ khi được phê duyệt, bảo vệ và ẩn danh hóa phù hợp. Ưu tiên synthetic data có phân bố đại diện.

**8. Vì sao cần fixture cho partition cũ?**

Migration có thể bỏ sót partition cũ hoặc gặp schema/index khác biệt theo lịch sử.

**9. Tại sao chỉ so sánh COUNT(*) là chưa đủ?**

Số hàng có thể giữ nguyên trong khi mapping sai, dữ liệu bị tráo hoặc một nhóm bị mất và nhóm khác bị nhân đôi.

**10. Fixture test nên được include trong changelog production không?**

Không, trừ dữ liệu tham chiếu thực sự thuộc sản phẩm. Test seed và edge cases cần được tách khỏi artifact triển khai.

**11. Khi nào cần scale/performance test?**

Khi migration scan/backfill bảng lớn, tạo index/constraint, thay datatype, giữ lock hoặc có nguy cơ ảnh hưởng replication và query latency.

**12. Cần lưu bằng chứng gì để tái lập test?**

DBMS/version, schema baseline, fixture profile, seed, generator version, artifact Liquibase, metrics và kết quả assertions.

**Kết luận:** Bộ dữ liệu tốt cho kiểm thử Liquibase phải phản ánh những thuộc tính quyết định kết quả migration: quy mô, cardinality, skew, tương quan, quan hệ, dữ liệu lịch sử và các giá trị biên. Hãy profiling trước khi sinh dữ liệu, tách smoke/functional/representative/scale fixtures, dùng seed deterministic, giữ referential integrity và kiểm tra NULL, duplicate, datatype, Unicode, thời gian cùng payload lớn. Sau migration, xác minh invariant theo nhóm dữ liệu, schema, history và hiệu năng thay vì chỉ so sánh tổng số hàng. Khi fixture được version hóa, cô lập khỏi changelog production và có thể tái tạo, nhóm sẽ phát hiện sớm lỗi chỉ xuất hiện trên bảng lớn và có bằng chứng đáng tin cậy trước khi phát hành.

