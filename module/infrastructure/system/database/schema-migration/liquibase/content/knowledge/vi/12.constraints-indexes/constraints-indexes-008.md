# Chỉ mục ghép, thứ tự cột và khác biệt theo hệ quản trị

## 1. Mục tiêu: thiết kế chỉ mục theo truy vấn thực tế, không chỉ theo tên cột

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, người học quản lý thay đổi schema và dữ liệu bằng Liquibase qua changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời thực hành kiểm chứng migration, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Ở chương **Khóa và chỉ mục**, một kỹ năng quan trọng là thiết kế **chỉ mục ghép** (*composite/multicolumn index*): một chỉ mục sử dụng nhiều cột làm khóa tra cứu, chẳng hạn `(tenant_id, processing_state, created_at)`.

Tạo chỉ mục ghép không phải chỉ chọn ba cột thường gặp rồi đặt chúng vào một danh sách. **Thứ tự cột trong khóa chỉ mục ảnh hưởng đến khả năng lọc, sắp xếp, giới hạn kết quả và chi phí thực thi**. Đồng thời, PostgreSQL, MySQL/InnoDB, SQL Server và Oracle có những khác biệt đáng kể về kiểu chỉ mục, cách sử dụng cột thứ hai/thứ ba, included columns, filtered/partial index, NULL, DDL online và cú pháp của trình tối ưu truy vấn.

Sau bài học, bạn cần làm được:

1. Giải thích cách chỉ mục B-tree ghép sắp xếp khóa và vì sao thứ tự cột quan trọng.
2. Chọn thứ tự cột dựa trên các điều kiện bằng, điều kiện khoảng, `ORDER BY`, `LIMIT` và pattern truy vấn thay vì chỉ dựa vào độ phân biệt (*selectivity*) của từng cột.
3. Phân biệt chỉ mục ghép với nhiều chỉ mục đơn, chỉ mục phủ (*covering*) và ràng buộc `UNIQUE` nhiều cột.
4. Nhận diện những khác biệt theo DBMS trước khi chuyển SQL/index definition giữa các môi trường.
5. Viết changeset Liquibase tạo/xóa chỉ mục, kiểm chứng SQL sinh ra, đo query plan và đánh giá rollback cùng tác động vận hành.

## 2. Mô hình B-tree ghép: thứ tự từ điển của các khóa

Giả sử có bảng `purchase_order`:

```sql
CREATE TABLE purchase_order (
    id               BIGINT PRIMARY KEY,
    tenant_id        BIGINT NOT NULL,
    processing_state VARCHAR(24) NOT NULL,
    customer_id      BIGINT NOT NULL,
    created_at       TIMESTAMP NOT NULL,
    total_amount     DECIMAL(18, 2) NOT NULL
);
```

Truy vấn thường gặp:

```sql
SELECT id, created_at, total_amount
FROM purchase_order
WHERE tenant_id = 42
  AND processing_state = 'PENDING'
ORDER BY created_at DESC
LIMIT 50;
```

Với chỉ mục B-tree ghép `(tenant_id, processing_state, created_at DESC)`, có thể hình dung các khóa được sắp xếp theo thứ tự:

1. Trước hết theo `tenant_id`.
2. Trong mỗi nhóm tenant, tiếp tục theo `processing_state`.
3. Trong mỗi nhóm tenant + state, tiếp tục theo `created_at`, giảm dần như đã khai báo.

Sơ đồ khái niệm:

```text
tenant_id  processing_state  created_at
42         COMPLETED         2026-11-18 08:00
42         PENDING           2026-11-19 17:00  <-- bắt đầu nhóm cần đọc
42         PENDING           2026-11-19 15:00
42         PENDING           2026-11-19 14:00
42         PENDING           2026-11-18 10:00
43         PENDING           2026-11-19 16:00
```

Đây chỉ là cách minh họa thứ tự logic; cấu trúc trang và cách DBMS mã hóa khóa thực tế phức tạp hơn. Trình tối ưu có thể tìm nhanh một đoạn khóa phù hợp với tenant + state, duyệt theo thời gian và dừng sớm khi đủ 50 dòng. Như vậy, cùng một chỉ mục có thể hỗ trợ cả **lọc** và **sắp xếp**. Nhưng việc có thực sự chọn nó hay không phụ thuộc thống kê, số dòng, các cột cần lấy và chi phí thực tế.

### 2.1. Nguyên tắc tiền tố trái (*leftmost prefix*)

Đối với một chỉ mục B-tree điển hình `(a, b, c)`:

| Điều kiện truy vấn | Mức độ phù hợp theo tiền tố |
|---|---|
| `a = ?` | Thường tìm hiệu quả theo cột đầu |
| `a = ? AND b = ?` | Thường tìm hiệu quả theo hai cột đầu |
| `a = ? AND b = ? AND c = ?` | Có thể tận dụng cả ba khóa |
| `b = ?`, không có điều kiện trên `a` | Thường không có đoạn tiền tố liên tục để tìm kiếm đơn giản |
| `a = ? AND c = ?`, bỏ qua `b` | Có thể thu hẹp theo `a`; `c` có thể hỗ trợ lọc nhưng không mặc nhiên thu hẹp phạm vi tìm kiếm như khi có `b` |
| `a > ? AND b = ?` | Điều kiện khoảng ở `a` thường giới hạn khả năng dùng các khóa phía sau để thu hẹp vùng tìm kiếm |

Đây là **mô hình tư duy**, không phải một quy tắc tuyệt đối cho mọi optimizer. Chẳng hạn, PostgreSQL ở một số phiên bản/đường thực thi có cơ chế *skip scan*; MySQL có thể sử dụng các phương án *index skip scan* khi đủ điều kiện; một DBMS cũng có thể chọn index scan toàn bộ hoặc kết hợp nhiều chỉ mục. Việc một truy vấn thiếu cột trái nhất **không đồng nghĩa chắc chắn DBMS không thể đụng tới chỉ mục đó**, nhưng thường làm giảm hiệu quả của kiểu tìm kiếm có đoạn khóa liên tục.

### 2.2. Chỉ mục `(a, b)` không đồng nghĩa `(b, a)`

Hai chỉ mục này có thể biểu đạt cùng cặp cột nhưng không thay thế lẫn nhau:

```sql
-- Hai thiết kế KHÁC NHAU về thứ tự tra cứu
CREATE INDEX idx_order_tenant_state
    ON purchase_order (tenant_id, processing_state);

CREATE INDEX idx_order_state_tenant
    ON purchase_order (processing_state, tenant_id);
```

Nếu phần lớn truy vấn luôn có `tenant_id = ?`, thiết kế tenant trước có lợi thế về tiền tố cho các truy vấn chỉ lọc theo tenant. Nếu chỉ có `processing_state = ?`, chỉ mục state trước có tiền tố phù hợp hơn. Với truy vấn có **cả hai điều kiện bằng**, optimizer thường có thể tận dụng cả hai khóa bất kể thứ tự; lúc đó sự khác biệt thể hiện rõ hơn ở các truy vấn phụ, thống kê, kích thước, cách sắp xếp và các cột tiếp theo.

**Kết luận:** quyết định thứ tự dựa trên **tập truy vấn cần phục vụ**, không chỉ một câu SQL được chọn làm ví dụ.

## 3. Chọn thứ tự cột: điều kiện bằng, khoảng, sắp xếp

### 3.1. Những cột được so sánh bằng

Các điều kiện như `tenant_id = 42` hoặc `processing_state = 'PENDING'` thường phù hợp khi đứng ở đầu chỉ mục. Nếu nhiều cột cùng dùng điều kiện bằng, có thể xem chúng như một nhóm tiền tố cần thiết. Thứ tự **giữa** các cột bằng không thể được quyết định chỉ bằng một quy tắc “cột nhiều giá trị khác nhau nhất luôn đứng trước”.

Ví dụ:

```sql
SELECT id, created_at
FROM purchase_order
WHERE tenant_id = 42
  AND processing_state = 'PENDING';
```

Cả `(tenant_id, processing_state)` lẫn `(processing_state, tenant_id)` đều có thể hỗ trợ hai điều kiện bằng. Nhưng nếu hệ thống đa tenant bắt buộc mọi API lọc tenant và có nhiều màn hình **không truyền state**, `tenant_id` nên được cân nhắc làm tiền tố chính. Nếu hệ thống thường thống kê theo `processing_state` trên tất cả tenant, cần đo thêm nhu cầu hoặc một cấu trúc chỉ mục riêng.

### 3.2. Điều kiện khoảng (*range*) và vị trí các cột phía sau

Xem truy vấn:

```sql
SELECT id, created_at
FROM purchase_order
WHERE tenant_id = 42
  AND created_at >= '2026-11-01'
  AND created_at <  '2026-12-01'
  AND processing_state = 'PENDING';
```

Hai ứng viên:

```text
I1 = (tenant_id, processing_state, created_at)
I2 = (tenant_id, created_at, processing_state)
```

Với I1, hai điều kiện bằng trên `tenant_id` và `processing_state` giúp xác định đoạn khóa; `created_at` tiếp tục giới hạn khoảng trong nhóm đó. Với I2, `tenant_id` xác định nhóm trước, `created_at` giới hạn khoảng; điều kiện `processing_state` đứng sau khóa khoảng có thể vẫn được xử lý ở tầng index hoặc filter, nhưng thường không tạo một đoạn liên tục hẹp bằng thiết kế I1 đối với đúng truy vấn này.

Ngược lại, với truy vấn **không có state**:

```sql
SELECT id, created_at
FROM purchase_order
WHERE tenant_id = 42
  AND created_at >= '2026-11-01'
  AND created_at <  '2026-12-01';
```

I2 thường có tiền tố tốt hơn. Vì thế, trong quyết định thực tế, cần đối chiếu **tần suất và độ quan trọng của từng truy vấn**. Không tồn tại một thứ tự cột tối ưu cho mọi câu SQL có cùng ba cột.

### 3.3. `ORDER BY` và `LIMIT`: tối ưu cả lọc lẫn thứ tự kết quả

Một ví dụ quan trọng trong hệ thống giao dịch:

```sql
SELECT id, created_at, total_amount
FROM purchase_order
WHERE tenant_id = 42
  AND processing_state = 'PENDING'
ORDER BY created_at DESC
LIMIT 50;
```

Chỉ mục `(tenant_id, processing_state, created_at DESC)` có thể đáp ứng điều kiện bằng trên hai cột đầu và cho phép duyệt kết quả đã có thứ tự cần thiết. So với dùng chỉ mục chỉ trên `(tenant_id, processing_state)` rồi sắp xếp tất cả bản ghi phù hợp, đây có thể là khác biệt hiệu năng lớn nếu mỗi tenant có nhiều đơn hàng.

Nhưng nếu truy vấn còn cần `ORDER BY created_at DESC, id DESC` để phân trang ổn định, việc thêm `id` vào khóa chỉ mục có thể hữu ích:

```text
(tenant_id, processing_state, created_at DESC, id DESC)
```

Lý do: nếu nhiều hàng có cùng `created_at`, chỉ sắp xếp theo timestamp không tạo thứ tự tổng thể ổn định. Thêm khóa duy nhất `id` làm thứ tự rõ ràng, hữu ích cho *keyset pagination*. Cần kiểm tra `id` có nằm trong khóa phụ của secondary index theo DBMS hay không và optimizer có khai thác được chiều sắp xếp mong muốn; không mặc định cột PK được lưu ngầm đồng nghĩa với mọi dạng `ORDER BY` đã được hỗ trợ.

### 3.4. Chiều tăng/giảm và truy vấn sắp xếp hỗn hợp

`ASC` và `DESC` ảnh hưởng đến thứ tự khóa của một số loại index. Nhiều DBMS có thể quét B-tree theo hai chiều. Vì vậy, một index chỉ có `(created_at ASC)` đôi khi vẫn phục vụ `ORDER BY created_at DESC` bằng cách quét ngược.

Với **nhiều cột có chiều hỗn hợp**, vấn đề phức tạp hơn:

```sql
ORDER BY created_at DESC, id ASC
```

Chỉ mục có khóa `(created_at DESC, id ASC)` có thể hữu ích hơn loại có cùng chiều cho cả hai, nếu điều kiện lọc và tiền tố cho phép. Một index `(created_at ASC, id ASC)` khi quét ngược cho thứ tự `DESC, DESC`, không phải `DESC, ASC`. Hỗ trợ khóa giảm dần và tối ưu sắp xếp hỗn hợp khác nhau theo DBMS/phiên bản; không chỉ dựa vào cú pháp DDL mà phải xem kế hoạch thực thi.

### 3.5. `GROUP BY`, `JOIN` và mẫu truy vấn có điều kiện động

Chỉ mục ghép còn có thể giúp truy vấn tổng hợp hoặc join khi thứ tự khóa phù hợp:

```sql
SELECT tenant_id, processing_state, COUNT(*)
FROM purchase_order
WHERE tenant_id = 42
GROUP BY tenant_id, processing_state;
```

Với nhóm theo các cột ở tiền tố, DBMS có thể tận dụng thứ tự của index thay cho một phần chi phí sắp xếp; điều này không bảo đảm optimizer sẽ luôn bỏ `Sort` hoặc `HashAggregate`. Trong join, cột được tra cứu bởi khóa ngoại như `(tenant_id, customer_id)` cũng có thể là ứng viên cho index riêng khi workload cần tìm đơn hàng của một khách hàng trong một tenant.

Nếu API cho phép nhiều tổ hợp filter tùy chọn, một index ghép dài không đảm bảo tối ưu tất cả tổ hợp. Có lúc cần một số index có mục đích rõ, đôi khi chỉ mục đơn kết hợp bitmap/index merge cũng đủ. **Không nên sinh tự động một chỉ mục cho mọi tổ hợp cột**: số lượng tăng rất nhanh và gây chi phí ghi, dung lượng, bảo trì.

## 4. Selectivity, phân bố dữ liệu và optimizer

### 4.1. Độ phân biệt không đủ để quyết định thứ tự cột

*Selectivity* cho biết điều kiện lọc thu hẹp tập dữ liệu nhiều hay ít. Ví dụ:

- `tenant_id` có thể có hàng nghìn giá trị và tenant phân bố không đều.
- `processing_state` chỉ có vài giá trị nhưng trạng thái `PENDING` có thể chiếm 1% hoặc 80% tùy giai đoạn.
- `created_at` có nhiều giá trị khác nhau nhưng điều kiện một tháng có thể trả về một lượng lớn bản ghi.

Quy tắc “cột selectivity cao nhất phải đứng đầu” dễ bị áp dụng sai. Với điều kiện bằng cho nhiều cột, thứ tự cột còn phục vụ những truy vấn **thiếu một phần điều kiện**, thứ tự `ORDER BY`, khóa khoảng và đặc điểm vật lý của index. Ngoài ra, optimizer dùng các thống kê và mô hình ước lượng riêng; dữ liệu lệch mạnh giữa tenant có thể khiến một query plan tốt cho tenant nhỏ trở nên kém hiệu quả với tenant lớn.

### 4.2. Khi nào DBMS bỏ qua chỉ mục?

Ngay cả khi có index phù hợp, database có thể chọn quét bảng nếu:

1. Truy vấn trả về phần lớn số dòng, khiến việc đọc qua index và quay lại bảng đắt hơn.
2. Cần lấy nhiều cột không nằm trong index; chi phí lookup tăng.
3. Thống kê cũ hoặc không phản ánh tương quan giữa các cột.
4. Hàm hoặc phép biến đổi trên cột làm điều kiện không dùng được cách tìm kiếm B-tree thông thường.
5. Điều kiện quá rộng, bảng quá nhỏ hoặc dữ liệu lưu trữ theo cấu trúc khác.

Ví dụ không tối ưu cho index trên `created_at`:

```sql
WHERE DATE(created_at) = DATE '2026-11-19'
```

Thường nên viết điều kiện khoảng trên giá trị cột gốc:

```sql
WHERE created_at >= TIMESTAMP '2026-11-19 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-20 00:00:00'
```

Việc chuyển đổi phải tôn trọng múi giờ, kiểu dữ liệu và quy tắc nghiệp vụ. Một số DBMS còn hỗ trợ expression/function-based index để tăng tốc chính biểu thức có hàm; lúc đó thiết kế lại query không phải lựa chọn duy nhất.

### 4.3. Thống kê đa cột

Hai cột có thể tương quan cao: một trạng thái chỉ xuất hiện ở một số tenant hoặc một nhóm khách hàng chỉ có mặt trong một vùng thời gian. Nếu optimizer ước lượng độ chọn lọc độc lập, nó có thể dự đoán sai số dòng.

PostgreSQL hỗ trợ extended statistics trong các trường hợp thích hợp; SQL Server có statistics và mô hình cardinality riêng; MySQL/Oracle có thống kê/histogram cùng cơ chế ước lượng khác nhau. Việc bổ sung một index không nhất thiết chữa được thống kê sai. Khi query plan bất thường, hãy xem số dòng **ước lượng so với thực tế**, độ mới của thống kê, tham số được bind và đặc tính dữ liệu, không chỉ số lượng index.

## 5. Covering index, included columns và chi phí đánh đổi

### 5.1. Covering không phải một kiểu index duy nhất

Một chỉ mục được gọi là *covering* cho một truy vấn khi nó có đủ dữ liệu cần thiết để DBMS có thể trả kết quả mà không cần tra bảng chính đối với mọi dòng (tùy cơ chế lưu trữ và điều kiện visibility). Ví dụ:

```sql
SELECT created_at, total_amount
FROM purchase_order
WHERE tenant_id = 42 AND processing_state = 'PENDING'
ORDER BY created_at DESC
LIMIT 50;
```

Nếu index có các khóa `tenant_id, processing_state, created_at` nhưng **không có** `total_amount`, DBMS có thể phải tra lại bảng để lấy số tiền. Một số hệ quản trị cho phép đưa `total_amount` thành **included/non-key column**: cột được lưu cùng index ở phần thích hợp nhưng không tham gia so sánh thứ tự khóa. Cơ chế này có thể giảm lookup và giữ khóa index gọn hơn so với đưa mọi cột vào key.

### 5.2. Key column và included column khác nhau

| Loại cột | Vai trò chính | Có quyết định thứ tự khóa? |
|---|---|---|
| Key column | Tìm kiếm, giới hạn vùng quét, thứ tự, uniqueness | Có |
| Included/non-key column | Cung cấp thêm dữ liệu để query được phục vụ từ index | Thông thường không |

Không có nghĩa included column luôn tốt: index vẫn lớn hơn, tăng lượng ghi và có thể giảm mật độ trang. Thêm các cột dữ liệu rộng như mô tả dài hoặc JSON có thể làm index phình to, thậm chí vượt giới hạn hệ quản trị. Đừng gắn tất cả cột `SELECT` vào mọi index chỉ để đạt “index-only scan”.

### 5.3. Khác biệt khi index “phủ” truy vấn

- **PostgreSQL:** B-tree hỗ trợ `INCLUDE` trong các phiên bản phù hợp. Một `Index Only Scan` còn phụ thuộc trạng thái visibility map của heap; “đủ cột trong index” không bảo đảm không có lần đọc heap nào.
- **SQL Server:** nonclustered index có thể khai báo `INCLUDE`; nếu thiếu cột, kế hoạch có thể xuất hiện `Key Lookup` hoặc `RID Lookup`. Các cột khóa clustered index có thể hiện diện ở cấu trúc nonclustered theo cơ chế SQL Server.
- **MySQL/InnoDB:** không có cú pháp `INCLUDE` tương đương cho secondary B-tree index theo kiểu SQL Server. Một secondary index của InnoDB chứa khóa primary key phục vụ tìm về row; `EXPLAIN` có thể báo `Using index` cho covering query. Đây không phải là khả năng included columns tùy ý.
- **Oracle:** có index B-tree ghép và nhiều cấu trúc/chiến lược index khác; đừng sao chép cú pháp `INCLUDE` của PostgreSQL/SQL Server sang Oracle mà giả định khả dụng. Covering query có thể tận dụng các cột khóa phù hợp, nhưng đánh đổi kích thước và khả năng khai thác vẫn cần đo.

## 6. Chỉ mục ghép để bảo đảm tính duy nhất

Chỉ mục ghép không chỉ phục vụ đọc. Một unique constraint hoặc unique index nhiều cột có thể biểu đạt quy tắc nghiệp vụ:

> Trong một tenant, mã đơn hàng do đối tác cung cấp không được trùng; giữa hai tenant thì có thể giống nhau.

```text
UNIQUE(tenant_id, external_order_id)
```

Các hàng `(42, 'PO-100')` và `(43, 'PO-100')` cùng tồn tại được, nhưng thêm một hàng thứ hai `(42, 'PO-100')` phải bị từ chối nếu ràng buộc đang có hiệu lực. Đây là quy tắc **toàn vẹn dữ liệu** chứ không chỉ là tối ưu hóa truy vấn.

Ví dụ Liquibase:

```yaml
databaseChangeLog:
  - changeSet:
      id: order-unique-tenant-external-id
      author: database-team
      changes:
        - addUniqueConstraint:
            tableName: purchase_order
            columnNames: tenant_id, external_order_id
            constraintName: uk_order_tenant_external_id
      rollback:
        - dropUniqueConstraint:
            tableName: purchase_order
            constraintName: uk_order_tenant_external_id
```

Đoạn ví dụ giả định cột `external_order_id` đã tồn tại. Trước khi tạo constraint, phải kiểm tra dữ liệu trùng:

```sql
SELECT tenant_id, external_order_id, COUNT(*) AS duplicate_count
FROM purchase_order
GROUP BY tenant_id, external_order_id
HAVING COUNT(*) > 1;
```

**Lưu ý NULL:** cách unique constraint xử lý nhiều hàng có giá trị `NULL` không hoàn toàn giống nhau giữa các DBMS và đôi khi có tùy chọn mới theo phiên bản. Nếu quy tắc nghiệp vụ không chấp nhận giá trị trống, hãy xem xét `NOT NULL` riêng; đừng suy rằng `UNIQUE` tự cấm mọi `NULL`.

Về logic uniqueness, `(a, b)` và `(b, a)` thường kiểm soát cùng tập cặp giá trị khi các cột không có `NULL`, nhưng **thứ tự khóa index bên dưới** vẫn tác động đến truy vấn. Ngoài ra, DBMS có thể tự tạo hoặc tận dụng index khi thêm constraint; không nên vô tình tạo thêm index trùng khóa mà chưa kiểm tra metadata.

## 7. Khác biệt theo hệ quản trị: cùng ý tưởng, khác năng lực

Các so sánh sau tập trung vào B-tree thông dụng và cách dùng thường gặp. Chi tiết phải được xác minh với đúng **DBMS, phiên bản, storage engine, edition và trình điều khiển** trong hệ thống:

| Khía cạnh | PostgreSQL | MySQL / InnoDB | SQL Server | Oracle Database |
|---|---|---|---|---|
| Chỉ mục ghép kiểu B-tree | Có | Có | Có | Có |
| Thứ tự khóa tăng/giảm | Hỗ trợ khóa `ASC`/`DESC`, các lựa chọn thứ tự `NULL` | Chỉ mục descending thực sự ở các phiên bản MySQL hiện đại; phiên bản cũ có khác biệt | Hỗ trợ `ASC`/`DESC` | Hỗ trợ index descending/các biến thể phụ thuộc phiên bản |
| Cột phủ không làm key | Có `INCLUDE` trên các loại index/phiên bản phù hợp | Không có `INCLUDE` tương đương trên secondary index thường dùng; PK được lưu trong secondary index InnoDB | Có `INCLUDE` cho nonclustered index | Dùng thiết kế index khác; không mặc định có cú pháp `INCLUDE` tương đương |
| Chỉ mục có predicate | Có partial index bằng `WHERE` | Không có filtered/partial index bằng `WHERE` tương đương trực tiếp | Có filtered index bằng `WHERE` với các giới hạn | Có thể dùng function-based index/giải pháp khác theo yêu cầu; không dùng nguyên cú pháp PostgreSQL |
| Tạo index giảm gián đoạn | Có `CREATE INDEX CONCURRENTLY` với ràng buộc riêng | Các cơ chế online DDL/algorithm/lock tùy phiên bản và thao tác | Tùy chọn `ONLINE` phụ thuộc phiên bản/edition/loại index | Tùy chọn online index build tùy phiên bản/edition/loại thao tác |
| Kế hoạch kiểm tra | `EXPLAIN`, `EXPLAIN (ANALYZE, BUFFERS)` | `EXPLAIN`, `EXPLAIN ANALYZE` ở phiên bản hỗ trợ | Estimated/actual execution plan, `STATISTICS IO` | `EXPLAIN PLAN`, `DBMS_XPLAN` |

### 7.1. PostgreSQL: partial, INCLUDE, sort direction và CONCURRENTLY

Ví dụ tối ưu truy vấn lấy danh sách đơn hàng đang chờ xử lý của từng tenant, đồng thời lấy `total_amount`:

```sql
CREATE INDEX idx_order_pending_tenant_time
ON purchase_order (tenant_id, created_at DESC, id DESC)
INCLUDE (total_amount)
WHERE processing_state = 'PENDING';
```

Đây là một **partial index**: chỉ các hàng thỏa predicate `processing_state = 'PENDING'` được đưa vào index. Nó có thể nhỏ hơn index toàn bảng và rất hiệu quả cho truy vấn phù hợp. Nhưng nếu truy vấn tìm trạng thái `COMPLETED`, index này không giúp theo cùng cách. Query planner cũng phải chứng minh rằng điều kiện query hàm ý predicate của partial index; với câu SQL parameterized, đặc biệt generic plan, khả năng nhận ra predicate có thể khác khi giá trị state chỉ xuất hiện ở tham số.

**`INCLUDE (total_amount)`** bổ sung dữ liệu không tham gia thứ tự key. `id DESC` tạo thứ tự phụ ổn định cho nhiều bản ghi có cùng timestamp. Đây là ví dụ dùng SQL riêng của PostgreSQL, **không phải DDL portable** cho mọi DBMS.

Khi tạo index trên bảng lớn mà cần giảm thời gian chặn thao tác ghi, PostgreSQL có:

```sql
CREATE INDEX CONCURRENTLY idx_order_tenant_state_time
ON purchase_order (tenant_id, processing_state, created_at DESC);
```

Tùy chọn `CONCURRENTLY` **không được chạy trong transaction block**, mất thêm thời gian/tài nguyên và có các tình huống thất bại để lại index `INVALID`. Nếu sử dụng qua Liquibase, phải kiểm tra cách đánh dấu changeset, `runInTransaction: false`, quyền kết nối và cách xử lý index không hợp lệ trước khi retry. Tránh gộp nhiều câu SQL rủi ro cao vào một changeset không có transaction.

### 7.2. MySQL / InnoDB: secondary index và quy tắc cột đầu

Ví dụ:

```sql
CREATE INDEX idx_order_tenant_state_time
ON purchase_order (tenant_id, processing_state, created_at DESC);
```

Ở MySQL 8.x, thứ tự giảm dần của key được hỗ trợ cho loại index phù hợp, nhưng hành vi của bản MySQL cũ hoặc MariaDB có thể khác. Khi đánh giá kế hoạch, xem `EXPLAIN`/`EXPLAIN ANALYZE`, các trường về key, rows, extra, filesort, index condition và số hàng thực tế. `Using index` thường gợi ý một đường đọc dữ liệu được phủ bởi index; `Using index condition` (index condition pushdown) là cơ chế khác.

Secondary index InnoDB mang theo giá trị primary key để định vị hàng trong clustered index. Điều này có lợi cho truy vấn chỉ lấy PK và các cột key, nhưng không tương đương khả năng thêm cột `INCLUDE` tùy ý như PostgreSQL/SQL Server.

MySQL còn có **prefix index** trên một phần giá trị chuỗi, chẳng hạn `email(20)`. *Prefix index theo số ký tự* là khái niệm khác với *leftmost prefix của chỉ mục ghép*. Dùng prefix index cần cân nhắc độ phân biệt và giới hạn của phép so sánh; không thể suy rằng chỉ mục trên 20 ký tự đầu hỗ trợ mọi truy vấn giống index trên toàn bộ cột.

Về vận hành, `ALTER TABLE`/online DDL trong MySQL có nhiều chế độ và giới hạn (metadata lock vẫn có thể xuất hiện). Không mặc định `CREATE INDEX` sẽ không khóa hay không làm chậm ghi trong mọi hoàn cảnh; kiểm tra engine, phiên bản, `ALGORITHM` và `LOCK` áp dụng được.

### 7.3. SQL Server: nonclustered index, INCLUDE và filtered index

Ví dụ SQL Server (dùng schema `dbo`):

```sql
CREATE NONCLUSTERED INDEX ix_order_tenant_state_time
ON dbo.purchase_order (tenant_id, processing_state, created_at DESC)
INCLUDE (total_amount);
```

SQL Server phân biệt clustered và nonclustered index; index nonclustered có thể mang khóa clustered để định vị hàng. Cột thêm bằng `INCLUDE` không quyết định thứ tự khóa nhưng có thể tránh `Key Lookup` nếu query được phủ. Tuy nhiên, thêm included columns cũng tăng chi phí ghi và kích thước index.

Một **filtered index** được khai báo với predicate:

```sql
CREATE NONCLUSTERED INDEX ix_order_pending_by_tenant
ON dbo.purchase_order (tenant_id, created_at DESC)
INCLUDE (total_amount)
WHERE processing_state = 'PENDING';
```

Filtered index cũng có giới hạn về biểu thức và khả năng optimizer suy ra predicate. Query dùng tham số có thể xuất hiện vấn đề plan reuse/parameter sniffing; cần kiểm tra kế hoạch thực tế. Tùy chọn `ONLINE = ON` không mặc nhiên có trong mọi edition, phiên bản, cấu trúc index và thao tác; hãy đối chiếu tài liệu SQL Server đích.

### 7.4. Oracle: index ghép, function-based index và NULL

Oracle hỗ trợ composite B-tree index, nhưng optimizer, cách lưu khóa, thống kê, giới hạn về độ dài khóa và lựa chọn index vật lý khác PostgreSQL, MySQL và SQL Server. Trong Oracle B-tree thông thường, **những hàng có toàn bộ các cột khóa index là NULL không được đưa vào index**, một khác biệt đáng chú ý so với nhiều DBMS khác. Với index nhiều cột, hàng có ít nhất một cột khóa không NULL có thể được lưu; cần đánh giá khi dùng predicate `IS NULL`.

Đối với truy vấn trên biểu thức như `UPPER(customer_code)`, Oracle có function-based index phù hợp khi định nghĩa và điều kiện đủ cho optimizer. Không cố viết cú pháp partial index PostgreSQL `WHERE ...` y nguyên sang Oracle; có những kỹ thuật khác, chẳng hạn function-based expressions cho một số nhu cầu chọn lọc hàng.

Tùy chọn online index creation, index compression và các loại index có thể giúp cải thiện vận hành nhưng phụ thuộc phiên bản, edition, cấu trúc và workload. Vì vậy cần review theo hệ quản trị thực tế thay vì dùng một changeset raw SQL chung cho cả bốn DBMS.

## 8. Định nghĩa chỉ mục ghép bằng Liquibase

### 8.1. Changeset `createIndex` dạng khai báo

Với một chỉ mục B-tree phổ thông, sử dụng `createIndex` để Liquibase sinh SQL tương ứng cho DBMS được hỗ trợ:

```yaml
databaseChangeLog:
  - changeSet:
      id: order-index-001-tenant-state-created
      author: database-team
      changes:
        - createIndex:
            indexName: idx_order_tenant_state_time
            tableName: purchase_order
            columns:
              - column:
                  name: tenant_id
              - column:
                  name: processing_state
              - column:
                  name: created_at
                  descending: true
      rollback:
        - dropIndex:
            indexName: idx_order_tenant_state_time
            tableName: purchase_order
```

**Thứ tự các phần tử `column` ở trên chính là thứ tự khóa mong muốn.** Thuộc tính `descending` phải được kiểm tra theo phiên bản Liquibase và DBMS; nếu DBMS không hỗ trợ hoặc diễn giải khác, không xem việc parse YAML thành công là bằng chứng SQL đã tối ưu đúng thứ tự.

`createIndex` không tạo bảng và không tự tạo dữ liệu. Bảng `purchase_order` cùng các cột liên quan phải tồn tại trước khi index được xây dựng. Chỉ mục tạo sau một migration thêm cột nên nằm trong changeset riêng với thứ tự nạp rõ ràng và điều kiện thực thi phù hợp.

### 8.2. Nhiều mục tiêu cần nhiều index, không phải một index khổng lồ

Giả sử có hai workload:

```sql
-- Q1: Đơn hàng chờ xử lý theo thời gian của một tenant
SELECT id, created_at
FROM purchase_order
WHERE tenant_id = 42 AND processing_state = 'PENDING'
ORDER BY created_at DESC
LIMIT 50;

-- Q2: Tìm các đơn hàng của một khách hàng trong tenant
SELECT id, created_at
FROM purchase_order
WHERE tenant_id = 42 AND customer_id = 1002
ORDER BY created_at DESC;
```

Ứng viên cho Q1: `(tenant_id, processing_state, created_at DESC)`. Ứng viên cho Q2: `(tenant_id, customer_id, created_at DESC)`. Gộp tất cả vào `(tenant_id, processing_state, customer_id, created_at)` có thể khiến Q2 không tận dụng tiền tố sau `tenant_id` vì nó không lọc `processing_state`.

Đây là ví dụ hai index **có cơ sở workload**; không có nghĩa nhất thiết phải tạo cả hai. Cần đo tần suất truy vấn, chi phí scan/lookup, kích thước, tỷ lệ đọc-ghi, thống kê và khả năng sử dụng index khác đã tồn tại trước khi quyết định.

### 8.3. Kiểm soát DBMS-specific SQL

Một số tính năng như `INCLUDE`, partial/filtered index hoặc `CREATE INDEX CONCURRENTLY` không thể kỳ vọng `createIndex` thuần tự động chuyển ngữ nghĩa giống nhau cho mọi DBMS. Khi cần dùng SQL đặc thù PostgreSQL:

```yaml
databaseChangeLog:
  - changeSet:
      id: order-index-002-pg-concurrently
      author: database-team
      dbms: postgresql
      runInTransaction: false
      changes:
        - sql:
            sql: >
              CREATE INDEX CONCURRENTLY idx_order_tenant_time_pg
              ON purchase_order (tenant_id, created_at DESC)
      rollback:
        - sql:
            sql: >
              DROP INDEX CONCURRENTLY IF EXISTS
              idx_order_tenant_time_pg
```

Ví dụ này **chỉ dành cho PostgreSQL** và dùng cú pháp cần chạy ngoài transaction block. Hãy giữ một changeset `runInTransaction: false` thật nhỏ, kiểm tra SQL và việc auto-commit của môi trường CLI/Spring Boot thực tế. Nếu build index thất bại, cần kiểm tra metadata xem index có còn tồn tại ở trạng thái không hợp lệ hay không; không chạy retry một cách mù quáng. Thao tác `DROP INDEX CONCURRENTLY` cũng có giới hạn riêng của PostgreSQL và cần kiểm tra trong rollback thực tế.

Tương tự, chỉ mục `INCLUDE` của SQL Server hay filtered index cũng nên được khai báo bằng SQL chuyên biệt kèm `dbms` và kế hoạch rollback phù hợp nếu Liquibase version đang dùng không biểu đạt đầy đủ bằng change type chuẩn. Không nên nhét nhiều biến thể DBMS vào một câu SQL “dùng chung” khiến pipeline chỉ phát hiện khác biệt khi lên production.

### 8.4. `unique: true` và `addUniqueConstraint` không hoàn toàn thay thế nhau

`createIndex` có thể tạo unique index bằng thuộc tính thích hợp trong các DBMS được hỗ trợ, trong khi `addUniqueConstraint` mô tả ràng buộc tính duy nhất theo mô hình schema. Nhiều DBMS sử dụng index để thực thi unique constraint, nhưng cách quản lý tên, metadata, phụ thuộc của khóa ngoại và khả năng rollback/online DDL có thể khác.

Khi mục tiêu chính là **bất biến nghiệp vụ**, `addUniqueConstraint` thường làm ý định rõ hơn. Khi mục tiêu là **một thiết kế truy vấn cụ thể**, `createIndex` phù hợp. Phải kiểm tra xem ràng buộc đã tạo index tương đương hay chưa để tránh nhân đôi index tốn chi phí ghi và dung lượng.

## 9. Migration an toàn: tạo index không có nghĩa là miễn phí

### 9.1. Tác động vận hành

Đối với bảng có hàng chục triệu dòng, tạo composite index có thể:

- Quét dữ liệu, sắp xếp khóa, sử dụng CPU, I/O và vùng lưu trữ tạm.
- Tăng WAL/redo/log và độ trễ replication.
- Giữ hoặc chờ lock theo cơ chế DBMS; online/concurrent DDL vẫn có giới hạn.
- Làm chậm các lệnh `INSERT`, `UPDATE`, `DELETE` vì index mới phải được duy trì.
- Kéo dài backup, tăng bộ nhớ cache cần thiết hoặc ảnh hưởng chiến lược bảo trì thống kê.

Một index giúp giảm chi phí đọc ở Q1 nhưng có thể gây tổng chi phí âm nếu workload chủ yếu ghi và truy vấn Q1 rất hiếm. Do đó cần chốt **mục tiêu đo được** trước khi tạo index: chẳng hạn p95 latency của truy vấn danh sách, số trang đọc, số lần sort hoặc tổng thời gian CPU mỗi ngày.

### 9.2. Trình tự triển khai khuyến nghị

1. Thu thập query thực tế, tần suất và số lượng hàng tại các tenant đại diện.
2. Ghi nhận query plan/latency/IO **trước** thay đổi, cả trường hợp giá trị phổ biến lẫn hiếm.
3. Đề xuất khóa và thứ tự cột của index; rà soát chỉ mục/ràng buộc đã tồn tại.
4. Tạo changeset Liquibase với tên index rõ, `id`/`author` ổn định, kiểm tra `dbms` và rollback.
5. Chạy `validate` và `update-sql` trên DBMS mục tiêu; đánh giá cú pháp DDL, locking/online options.
6. Chạy migration trên bản sao dữ liệu đại diện hoặc môi trường staging gần production; đo thời gian build, lock wait, tài nguyên.
7. Kiểm tra query plan và số đo **sau** thay đổi, không chỉ thông báo “index created”.
8. Lên lịch production có kiểm soát; theo dõi tiến trình build, replica lag, ứng dụng và giới hạn rollback.
9. Đối chiếu metadata index thật và `DATABASECHANGELOG`; giữ changeset đã triển khai bất biến.

Đối với index lớn, có thể cần một migration job riêng thay vì để nhiều replica Spring Boot đồng thời cố chạy index build khi ứng dụng khởi động. Liquibase `DATABASECHANGELOGLOCK` điều phối runner dùng chung metadata, nhưng **không loại bỏ lock của DBMS đối với ứng dụng** và không làm index build nhanh hơn.

### 9.3. Rollback: `dropIndex` có thể đúng về schema nhưng chưa chắc an toàn vận hành

Trong ví dụ `createIndex`, rollback có thể là `dropIndex`. Thao tác này không trực tiếp xóa dữ liệu bảng, nhưng có thể làm hiệu năng suy giảm đột ngột nếu truy vấn đã phụ thuộc index mới hoặc nếu unique index đang đảm bảo bất biến dữ liệu. Nếu index phục vụ ràng buộc `UNIQUE`, việc loại bỏ nó còn có thể làm thay đổi quyền được phép ghi dữ liệu trùng.

Trước rollback production, xác minh:

- Index có đang làm nền cho constraint hoặc đối tượng phụ thuộc khác không?
- Các query plan quan trọng sẽ thay đổi như thế nào khi bỏ index?
- `DROP INDEX` có bị khóa/chờ lâu hay cần cơ chế online/concurrent riêng không?
- DBMS đang dùng có cú pháp khác cho index gắn constraint không?

Không sửa changeset đã chạy để đổi thứ tự cột cho một index. Nếu cần thiết kế khác, tạo **changeset mới** tạo index thay thế, kiểm chứng workload rồi thêm changeset loại index cũ khi an toàn. Cách này giữ checksum/lịch sử minh bạch và dễ kiểm soát trong CI/CD.

## 10. Đo bằng kế hoạch thực thi, không suy đoán từ lý thuyết

### 10.1. PostgreSQL

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, total_amount
FROM purchase_order
WHERE tenant_id = 42
  AND processing_state = 'PENDING'
ORDER BY created_at DESC
LIMIT 50;
```

Quan sát các node `Index Scan`, `Index Only Scan`, `Bitmap Index Scan`, `Sort`, `Limit`; so sánh số dòng ước lượng và thực tế, số buffer hit/read, thời gian đọc và thời gian sort. Chú ý `EXPLAIN ANALYZE` **thực thi truy vấn**; với `SELECT` chủ yếu đọc dữ liệu, nhưng nếu áp dụng cho câu lệnh ghi thì có thể gây thay đổi dữ liệu. Chỉ chạy câu DML qua công cụ đo trong môi trường phù hợp với kiểm soát transaction.

### 10.2. MySQL

```sql
EXPLAIN
SELECT id, created_at
FROM purchase_order
WHERE tenant_id = 42 AND processing_state = 'PENDING'
ORDER BY created_at DESC
LIMIT 50;
```

Xem `key` đang chọn, `key_len`, `rows`, `filtered` và `Extra` (ví dụ `Using filesort`, `Using index`, `Using index condition`). `EXPLAIN ANALYZE` nếu phiên bản hỗ trợ sẽ thực thi truy vấn và đo theo cách của MySQL. Không dùng duy nhất một phần tử `Extra` để kết luận index đang tối ưu toàn bộ query; phải xem tổng thể số dòng và chi phí.

### 10.3. SQL Server và Oracle

Với SQL Server, dùng estimated/actual execution plan và đo `STATISTICS IO`/`STATISTICS TIME` trong môi trường kiểm thử. Quan sát `Index Seek` so với `Index Scan`, `Key Lookup`, `Sort`, số lần đọc logic và chênh lệch estimated/actual rows. `Index Seek` không bảo đảm luôn nhanh hơn `Index Scan` nếu lookup lặp lại quá nhiều.

Với Oracle, kết hợp `EXPLAIN PLAN`, `DBMS_XPLAN` và thống kê thực thi nếu được phép; xem các thao tác `INDEX RANGE SCAN`, `INDEX FULL SCAN`, `TABLE ACCESS BY INDEX ROWID`, chi phí sắp xếp và cardinality. Tên node không tương đương từng chữ với PostgreSQL hay SQL Server; hãy đối chiếu ý nghĩa và số đo theo DBMS.

### 10.4. Một phép thử đúng cần có hai loại dữ liệu

**Dữ liệu điển hình** cho workload hàng ngày và **dữ liệu cực trị** (tenant rất lớn, trạng thái rất phổ biến, khoảng thời gian rất dài). Một index có thể tốt cho 99% tenant nhỏ nhưng gây kế hoạch kém ở tenant chiếm 40% số bản ghi.

Nếu workload sử dụng truy vấn tham số hóa, prepared statements và cache plan có thể ảnh hưởng lựa chọn index. Khi so sánh hiệu năng, giữ ổn định phiên bản DBMS, dữ liệu, thống kê, query text, giá trị tham số, cơ chế plan cache và tải hệ thống ở mức có thể. Chỉ kết luận sau khi đo các tiêu chí gắn với mục tiêu ban đầu.

## 11. Tình huống xuyên suốt: dashboard đơn hàng đa tenant

Giả sử dashboard có ba endpoint:

| Endpoint | Điều kiện chính | Thứ tự mong muốn |
|---|---|---|
| A. Hàng đợi | `tenant_id = ? AND processing_state = 'PENDING'` | `created_at DESC, id DESC` |
| B. Lịch sử tenant | `tenant_id = ? AND created_at >= ? AND created_at < ?` | `created_at DESC, id DESC` |
| C. Đơn hàng của khách | `tenant_id = ? AND customer_id = ?` | `created_at DESC, id DESC` |

Ba chỉ mục ứng viên:

```text
IA = (tenant_id, processing_state, created_at DESC, id DESC)
IB = (tenant_id, created_at DESC, id DESC)
IC = (tenant_id, customer_id, created_at DESC, id DESC)
```

**Phân tích:**

- IA có tiền tố hữu ích cho A. Nó không lý tưởng cho B nếu B không có điều kiện `processing_state`, vì các dòng trong một tenant còn phân nhóm theo state trước khi sắp xếp thời gian.
- IB phù hợp B và có thể hỗ trợ các query chỉ theo tenant và thời gian. Với A, IB có thể phải đọc rồi loại nhiều hàng không phải `PENDING`; chi phí tùy tỷ lệ trạng thái.
- IC có tiền tố phù hợp C, nhưng đối với A nó thiếu điều kiện trên `customer_id`, không phải index thay thế trực tiếp.

Nếu A là endpoint hot path còn B/C ít quan trọng, có thể ưu tiên IA và đo xem IB/IC có cần thật không. Nếu trạng thái `PENDING` cực hiếm và DBMS hỗ trợ partial/filtered index, một index chỉ chứa `PENDING` có thể đáng cân nhắc, đổi lại tính portable thấp hơn. Nếu workload ghi rất lớn, giữ cả ba có thể làm tăng write amplification vượt lợi ích đọc. Mọi quyết định đều cần dữ liệu và query plan.

**Kịch bản triển khai Liquibase:** tạo IA bằng `createIndex`; chạy `validate` và `update-sql` cho PostgreSQL/MySQL/SQL Server/Oracle mục tiêu; sau đó chạy trên staging với số hàng đại diện, đo A/B/C trước và sau. Nếu cần IB/IC, tạo changeset mới với lý do workload rõ. Không sửa changeset IA đã triển khai để “nhét” thêm cột vì sẽ ảnh hưởng checksum và lịch sử. Với index SQL đặc thù, dùng `dbms` để tránh gửi cú pháp không tương thích xuống DBMS khác.

## 12. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Index có đủ ba cột thì thứ tự không quan trọng” | Thứ tự ảnh hưởng tiền tố tìm kiếm, khoảng khóa và khả năng phục vụ `ORDER BY` |
| “Luôn đặt cột selectivity cao nhất đầu tiên” | Phải xét cả nhóm equality, range, order và các query thiếu cột; selectivity chỉ là một phần |
| “Thiếu cột đầu tiên thì DBMS tuyệt đối không dùng index” | Một số optimizer có skip scan, full index scan hoặc phương án khác, nhưng thường kém seek theo tiền tố |
| “Hai index đơn luôn tương đương một index ghép” | Index merge/bitmap có chi phí và không mặc nhiên giữ thứ tự khóa kết hợp như composite index |
| “Có index thì không cần sort” | Cần thỏa điều kiện thứ tự khóa, hướng sort, các predicate và lựa chọn optimizer |
| “INCLUDE làm cột trở thành một phần của thứ tự key” | Included columns thường không tham gia thứ tự tìm kiếm |
| “Index-only/covering luôn không đọc bảng” | PostgreSQL có điều kiện visibility; DBMS khác có cơ chế lookup và storage khác |
| “Index càng nhiều, SELECT càng nhanh mà không có giá phải trả” | Index làm tăng dung lượng, chi phí ghi, khóa và thời gian bảo trì |
| “UNIQUE có cùng hành vi NULL ở mọi DBMS” | Quy tắc NULL/unique khác theo hệ quản trị và phiên bản |
| “`createIndex` trên Liquibase tạo ra DDL online giống nhau ở mọi DBMS” | Online/concurrent DDL và partial/include index là khả năng đặc thù cần kiểm tra |
| “Tạo index thành công tức là truy vấn đã tối ưu” | Phải xem actual plan, số trang đọc, số hàng, latency và tác động workload |
| “Có thể đổi thứ tự cột trong changeset đã chạy” | Nên dùng changeset mới thay thế, giữ nguyên lịch sử và checksum đã triển khai |

## 13. Checklist thiết kế và kiểm chứng chỉ mục ghép

- [ ] Có danh sách SQL thực tế và tần suất truy vấn, không chỉ danh sách cột trong bảng.
- [ ] Xác định nhóm điều kiện bằng, điều kiện khoảng, `ORDER BY`, `LIMIT`, `GROUP BY`/`JOIN` và tham số tùy chọn.
- [ ] Đánh giá các truy vấn thiếu một phần tiền tố; không nhầm `(a,b)` với `(b,a)`.
- [ ] Xác định mục tiêu: tối ưu đọc, tính duy nhất, covering, lọc subset hay hỗ trợ thứ tự phân trang.
- [ ] Đánh giá các cột khóa `ASC`/`DESC` và thứ tự ổn định khi có timestamp trùng.
- [ ] Kiểm tra selectivity thực tế và skew giữa các tenant, thống kê đa cột và cardinality estimation.
- [ ] Rà soát index/unique constraint hiện hữu để tránh tạo index dư hoặc cùng tiền tố không mang lại lợi ích.
- [ ] Xem xét `INCLUDE` và partial/filtered index chỉ trên DBMS/phiên bản hỗ trợ; không giả định portable.
- [ ] Kiểm tra xử lý `NULL`, collation, kiểu dữ liệu và giới hạn key length trên DBMS mục tiêu.
- [ ] Với bảng lớn, đánh giá transaction/DDL lock, online/concurrent build, dung lượng, replication lag và failure recovery.
- [ ] Changeset Liquibase có `id`/`author` ổn định, tên index rõ, đúng thứ tự `column`, rollback được review.
- [ ] Chạy `validate`, `status --verbose`, `update-sql` và thử migration trên database staging có dữ liệu đại diện.
- [ ] Đo plan và IO/latency trước-sau với tham số phổ biến lẫn cực trị; không chỉ quan sát “Index Scan”/“Index Seek”.
- [ ] Xác minh index thực tế, constraint liên quan và lịch sử `DATABASECHANGELOG`; không sửa changeset đã chạy.
- [ ] Spring Boot và CI/CD dùng cùng changelog artifact, DBMS đích và quy trình migration phù hợp, tránh index build khi nhiều replica khởi động cùng lúc.

**Tóm lại:** chỉ mục ghép là công cụ kết hợp **lọc, sắp xếp và đôi khi tính duy nhất**. Thứ tự cột phải được suy ra từ workload và xác minh bằng kế hoạch thực thi, không chỉ từ độ phân biệt của từng cột. PostgreSQL, MySQL/InnoDB, SQL Server và Oracle có khác biệt về key ordering, included columns, partial/filtered index, NULL và online DDL; vì vậy changeset Liquibase cần phân biệt phần khai báo portable với SQL đặc thù DBMS. Khi kết hợp thiết kế đúng, kiểm chứng SQL, đo hiệu năng, rollback có chủ đích và lịch sử triển khai nhất quán, `DATABASE_SCHEMA_MIGRATION_LIQUIBASE` có thể quản lý index an toàn cùng các thay đổi schema khác trong nhiều môi trường.
