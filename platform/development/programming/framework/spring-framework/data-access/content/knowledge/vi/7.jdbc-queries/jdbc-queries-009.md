# Phân trang, sắp xếp tường minh và truy vấn tổng số khi cần

## Mục tiêu của bài

Một API tìm kiếm có thể trả hàng chục nghìn bản ghi, nhưng màn hình chỉ hiển thị 20–50 bản ghi mỗi lượt. Với Spring JDBC, chúng ta cần thiết kế câu SQL lấy **đúng một trang**, có **thứ tự xác định**, đồng thời quyết định **khi nào cần đếm tổng số bản ghi**.

Sau bài học này, bạn cần:

1. Viết đúng `ORDER BY`, `LIMIT`, `OFFSET` và tham số tương ứng trong `JdbcTemplate`.
2. Giải thích vì sao phân trang mà không sắp xếp tường minh, hoặc sắp xếp theo cột không duy nhất, có thể trả trang chập chờn.
3. Tính offset an toàn từ page/size, kiểm tra size tối đa và hiểu trang vượt quá cuối tập dữ liệu.
4. Chỉ chạy `SELECT COUNT(*)` khi giao diện/hợp đồng API thật sự cần `totalElements` hoặc `totalPages`; phân biệt **Page** và **Slice**.
5. Nhận ra chi phí của offset lớn, so sánh với **keyset/cursor pagination**, và hiểu ảnh hưởng của dữ liệu thay đổi giữa các request.
6. Triển khai một ví dụ **Java 17+, Spring JdbcTemplate và H2** hoàn chỉnh, kiểm tra kết quả đầu ra theo dữ liệu mẫu.

Ví dụ sử dụng cú pháp `LIMIT ... OFFSET ...` được H2 và PostgreSQL hỗ trợ. Các DBMS khác có thể dùng `FETCH FIRST`, `OFFSET ... FETCH` hoặc cú pháp tương đương; nguyên tắc phân trang/sắp xếp giữ nguyên, nhưng phải kiểm tra dialect thực tế.

## 1. Vì sao không nên trả toàn bộ kết quả?

Giả sử bảng `tasks` chứa 500.000 nhiệm vụ. Gọi:

```sql
SELECT id, title, created_at
FROM tasks
WHERE tenant_id = 7 AND status = 'OPEN';
```

sẽ yêu cầu database trả toàn bộ dữ liệu thỏa điều kiện. Ngay cả khi database có chỉ mục tốt, đường truyền, JDBC driver, `RowMapper`, bộ nhớ JVM và client đều có thể chịu chi phí lớn. Cách hợp lý cho một bảng phân trang là chỉ lấy các dòng cần hiển thị.

Phân trang phía server không giống việc lấy 500.000 dòng rồi gọi `list.subList(...)` trong Java. Cách làm phía Java vẫn phải tải và ánh xạ toàn bộ kết quả trước khi cắt, nên không giải quyết vấn đề khối lượng dữ liệu.

Cấu trúc truy vấn tối thiểu:

```sql
SELECT id, title, created_at
FROM tasks
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, id DESC
LIMIT ?
OFFSET ?;
```

- `WHERE` giới hạn tập dữ liệu theo tenant, status và các quy tắc quyền truy cập.
- `ORDER BY` quyết định **thứ tự ổn định trong một trạng thái dữ liệu**.
- `LIMIT` là số dòng tối đa trả về.
- `OFFSET` là số dòng đầu tiên trong thứ tự đó được bỏ qua.
- Các dấu `?` là JDBC placeholders cho **giá trị**, được bind bằng `JdbcTemplate`.

Ở đây `id` là khóa chính duy nhất. Nếu nhiều dòng có cùng `created_at`, `id DESC` là tiêu chí phụ để loại bỏ việc tùy ý đảo vị trí giữa những dòng bằng thời gian.

## 2. ORDER BY phải rõ ràng và đủ để phân biệt mọi dòng

### 2.1. Không có ORDER BY thì không có thứ tự cam kết

Một query không chứa `ORDER BY` **không bảo đảm** trả các dòng theo PK, thứ tự chèn hay thứ tự “nhìn thấy ở lần chạy trước”. Database có thể thay đổi execution plan, dùng index khác, chạy song song hoặc sắp dữ liệu vật lý khác đi.

Ví dụ dễ sai:

```sql
SELECT id, title FROM tasks
WHERE tenant_id = 7
LIMIT 10 OFFSET 10;
```

Chỉ có `LIMIT/OFFSET` không xác định 10 dòng nào là “trang 2”. Trong phân trang, cần `ORDER BY` ở truy vấn thực sự được gửi đến DBMS, không chỉ gọi `Collections.sort()` trên mười dòng đã tải về.

### 2.2. Một cột sắp xếp không duy nhất vẫn chưa đủ

Giả sử dữ liệu:

| id | created_at | title |
| ---: | --- | --- |
| 11 | 2025-01-02 09:00:00 | A |
| 12 | 2025-01-02 09:00:00 | B |
| 13 | 2025-01-03 09:00:00 | C |
| 14 | 2025-01-03 09:00:00 | D |
| 15 | 2025-01-04 09:00:00 | E |

Nếu chỉ viết `ORDER BY created_at DESC`, các dòng 13/14 và 11/12 có **khóa sắp xếp bằng nhau**. Thứ tự trong mỗi nhóm hòa có thể thay đổi giữa các lần thực thi, khiến một dòng xuất hiện ở hai trang hoặc bị bỏ lỡ khi ranh giới trang nằm giữa các dòng bằng nhau.

Viết:

```sql
ORDER BY created_at DESC, id DESC
```

sẽ tạo thứ tự tổng quát cho các dòng khi `id` duy nhất. Với thời điểm bằng nhau, `id` quyết định vị trí. Trong ví dụ này `created_at` được khai báo `NOT NULL`; nếu cột sort nullable, cần thống nhất quy tắc NULL và cách diễn đạt `NULLS FIRST/LAST` của DBMS.

**Lưu ý:** Thứ tự xác định **không đồng nghĩa** kết quả nhiều request sẽ cố định nếu dữ liệu bị thêm, xóa, hoặc cập nhật giữa các request. Đây là hai vấn đề khác nhau: *tie-breaking* và *snapshot consistency*.

### 2.3. ASC/DESC, khóa phụ và tính nhất quán

- `ASC`: tăng dần; `DESC`: giảm dần.
- Chọn thứ tự theo nghiệp vụ, ví dụ nhiệm vụ mới nhất trước là `created_at DESC`.
- Bổ sung khóa phụ duy nhất như `id DESC` để ổn định khi timestamp trùng.
- Khi cursor pagination, điều kiện “sau dòng cuối” phải theo **cùng hướng** với `ORDER BY`.
- Nếu người dùng đổi sort từ “mới nhất” sang “cũ nhất”, cursor cũ không còn hợp lệ cho thứ tự mới; cần bắt đầu lại.

Không nên dùng `ORDER BY RANDOM()` cho pagination thông thường; thứ tự ngẫu nhiên thay đổi và thường tốn chi phí.

### 2.4. ORDER BY không thể bind tên cột bằng dấu hỏi

Dấu `?` của prepared statement dành cho **giá trị**, không phải SQL identifier/keyword. Câu kiểu này không chọn cột để sort theo mong muốn:

```sql
-- Sai về ý định: ? không phải tên cột SQL.
SELECT id, title FROM tasks ORDER BY ? LIMIT ?;
```

Với tính năng sort do client chọn, hãy ánh xạ đầu vào vào **danh sách cột và chiều đã cho phép**, rồi lắp cấu trúc `ORDER BY`. Ví dụ Java (đoạn độc lập về xử lý sort, nhưng chưa phải repository):

```java
static String allowedOrderBy(String requestedSort) {
    return switch (requestedSort) {
        case "newest" -> "created_at DESC, id DESC";
        case "oldest" -> "created_at ASC, id ASC";
        case "title" -> "title ASC, id ASC";
        default -> throw new IllegalArgumentException("Unsupported sort");
    };
}
```

Không nối trực tiếp `request.getSort()` vào SQL. Cách dùng allowlist vừa hạn chế SQL injection, vừa đảm bảo mỗi lựa chọn có khóa phụ duy nhất. Nếu sort theo text, collations và tính phân biệt chữ hoa/thường có thể khác giữa các DBMS; cần định nghĩa hành vi mong muốn.

## 3. LIMIT/OFFSET: cách tính một trang

### 3.1. Chọn quy ước page số 0 hay số 1

Trong nhiều API nội bộ hoặc kiểu Spring Data, `page=0` là trang đầu. Gọi `size=3`:

| page (0-based) | size | offset | Lấy |
| ---: | ---: | ---: | --- |
| 0 | 3 | 0 | Dòng thứ 1–3 theo ORDER BY |
| 1 | 3 | 3 | Dòng thứ 4–6 |
| 2 | 3 | 6 | Dòng thứ 7–9 |

Công thức:

```text
offset = page * size
LIMIT size OFFSET offset
```

Nếu API public hiển thị `page=1` cho trang đầu thì dùng `offset = (page - 1) * size` sau khi validate `page >= 1`. **Không trộn hai quy ước** giữa backend và UI; ghi rõ trong API contract.

### 3.2. Validate trước khi gửi SQL

Cần kiểm tra:

- `page >= 0` theo quy ước zero-based.
- `size >= 1` và giới hạn trên hợp lý, ví dụ `size <= 100`.
- Ép kiểu trước khi nhân: `long offset = (long) page * size`; nếu dùng `int` cho phép nhân, hai số đủ lớn có thể overflow rồi thành offset âm.
- Nếu database/driver hoặc chính sách API có giới hạn offset, từ chối giá trị vượt mức được hỗ trợ.
- Với `size + 1` khi triển khai Slice, cần chặn size quá lớn để không overflow; size 1..100 là an toàn.

Lỗi đầu vào nên được trả dạng phù hợp tầng web (thường là HTTP 400 cho tham số không hợp lệ), thay vì để một SQLException khó hiểu từ database.

### 3.3. SQL page có thể trả ít hơn size dòng

`LIMIT 20` nghĩa là “tối đa 20”, không phải “luôn 20”. Nếu query còn 7 dòng ở cuối tập kết quả thì trả 7. Nếu `OFFSET` vượt cuối danh sách thì `query` trả list rỗng; điều đó **không tự có nghĩa tổng kết quả bằng 0**. Muốn biết tổng số, phải có nguồn đếm/metadata tương ứng.

Với `JdbcTemplate`:

```java
List<TaskView> items = jdbc.query(
        """
        SELECT id, title, created_at
        FROM tasks
        WHERE tenant_id = ? AND status = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        TASK_MAPPER,
        tenantId, status, size, offset);
```

Đây là **đoạn trích** giả định các biến và `TASK_MAPPER` có sẵn; chương 8 có chương trình đầy đủ. `query` trả list rỗng khi không có dòng. Không dùng `queryForObject` cho một trang chứa 0..N dòng.

## 4. Truy vấn tổng số: có cần COUNT(*) hay không?

Có hai thông tin khác nhau:

- `items`: dữ liệu của **trang hiện tại**, lấy qua `LIMIT/OFFSET`.
- `totalElements`: tổng số dòng thỏa **toàn bộ điều kiện lọc**, **không áp dụng LIMIT/OFFSET**.

Ví dụ:

```sql
SELECT COUNT(*)
FROM tasks
WHERE tenant_id = ?
  AND status = ?;
```

Trong Java:

```java
Long total = jdbc.queryForObject(
        "SELECT COUNT(*) FROM tasks WHERE tenant_id = ? AND status = ?",
        Long.class,
        tenantId, status);
```

`COUNT(*)` không có `GROUP BY` trả một dòng ngay cả khi không có dữ liệu, với giá trị 0. `Long` không được suy ra từ kiểu `int` của page size; dùng `long/Long` cho tổng vì số dòng có thể vượt 2,1 tỷ. Trong demo, `COUNT(*)` không NULL, nên có thể unbox `Long`; cân nhắc kiểm soát nullable ở các scalar SQL khác.

### 4.1. Khi cần đếm

Count phù hợp khi UI/API phải biết:

- “Có tất cả 6 kết quả”.
- “Trang 1 trên 2 trang”.
- Danh sách số trang cho phép nhảy trực tiếp hoặc nút trang cuối.
- Một báo cáo quản trị cần tổng số bản ghi chính xác theo filter.

Khi đã có `total` và `size > 0`, có thể tính số trang:

```java
long totalPages = total / size + (total % size == 0 ? 0 : 1);
```

Cách này tránh phép cộng `total + size - 1` có thể overflow ở `Long.MAX_VALUE`. Với tổng 0, `totalPages = 0` theo quy ước số trang có dữ liệu; UI có thể chọn hiển thị “0 kết quả” thay vì “trang 1/0”.

### 4.2. Khi không nên đếm trên mọi request

`COUNT(*)` là một truy vấn **riêng**. Với điều kiện lọc phức tạp, phép JOIN, dữ liệu lớn hoặc một số DBMS, nó có thể tiêu tốn CPU/I/O đáng kể. Nếu UI chỉ có **“Xem thêm”** hoặc “Trang tiếp”, có thể bỏ count và dùng **Slice**, lấy `size + 1` dòng:

```sql
SELECT id, title, created_at
FROM tasks
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, id DESC
LIMIT ? OFFSET ?;
```

Bind `limit = size + 1`. Nếu nhận hơn `size` dòng, biết có **ít nhất một dòng tiếp theo** trong trạng thái dữ liệu tại thời điểm query; trả cho client tối đa `size` dòng, cùng cờ `hasNext`. Không gọi thêm `COUNT(*)`.

**Giới hạn:** `hasNext` của Slice không cho biết tổng số trang và không bảo đảm trang tiếp theo vẫn có dòng khi dữ liệu biến động. Nó trả lời một câu hỏi nhẹ hơn count.

### 4.3. COUNT phải dùng đúng cùng điều kiện với danh sách

Sai rất thường gặp:

```sql
-- Danh sách chỉ của tenant hiện tại, có lọc trạng thái:
SELECT id, title
FROM tasks
WHERE tenant_id = ? AND status = 'OPEN'
ORDER BY created_at DESC, id DESC
LIMIT ? OFFSET ?;

-- Đếm sai vì quên tenant hoặc status:
SELECT COUNT(*) FROM tasks;
```

Khi đó số lượng trong UI không khớp với kết quả, và việc đếm không giới hạn theo tenant còn có thể **rò rỉ thông tin số lượng dữ liệu** từ khách hàng khác.

Truy vấn `COUNT(*)` phải giữ **cùng filter nghiệp vụ và quyền truy cập** như truy vấn items: tenant, status, khoảng thời gian, từ khóa tìm kiếm, soft delete, ACL... `ORDER BY` không cần thiết cho count toàn bộ tập; `LIMIT/OFFSET` không được đưa vào count toàn bộ.

Một cách lập kế hoạch tốt là coi “filter” là hợp đồng duy nhất rồi đảm bảo hai câu SQL được thay đổi đồng bộ qua test. Khi điều kiện phức tạp, có thể viết SQL builder có kiểm soát, named parameters hoặc query framework; không ghép dữ liệu người dùng vào chuỗi SQL.

### 4.4. JOIN có thể nhân số dòng đếm

Nếu một nhiệm vụ có nhiều tag, JOIN sang bảng `task_tags` tạo nhiều dòng cho một nhiệm vụ:

```sql
SELECT t.id, t.title
FROM tasks t
JOIN task_tags g ON g.task_id = t.id
WHERE t.tenant_id = ? AND g.name IN (?, ?);
```

Nếu cùng nhiệm vụ có cả hai tag, nó xuất hiện nhiều lần. `COUNT(*)` trên JOIN đếm **số dòng sau JOIN**, không phải số nhiệm vụ khác nhau. Khi contract là “đếm nhiệm vụ duy nhất”, có thể phải dùng:

```sql
SELECT COUNT(DISTINCT t.id)
FROM tasks t
JOIN task_tags g ON g.task_id = t.id
WHERE t.tenant_id = ? AND g.name IN (?, ?);
```

Truy vấn lấy page cũng phải giải quyết duplicate đúng cách (ví dụ dùng `EXISTS`, CTE/subquery chọn id duy nhất, hoặc chiến lược khác). Không chỉ sửa count thành `DISTINCT` trong khi items vẫn hiển thị trùng dòng; đây là vấn đề thiết kế query phải xử lý nhất quán.

Nếu query có `GROUP BY`, `HAVING` hoặc phép tổng hợp trả nhiều nhóm, đếm **số nhóm sau lọc** có thể phải bọc query vào subquery (bỏ phần ORDER BY/LIMIT không cần thiết) rồi `COUNT(*)` ở ngoài. Mục tiêu là đếm **đúng thực thể mà API phân trang**.

## 5. Page và Slice: chọn theo hợp đồng API

| Tiêu chí | Page với count | Slice không count |
| --- | --- | --- |
| Dữ liệu của trang | Truy vấn có `LIMIT/OFFSET` | Truy vấn lấy `size + 1` dòng |
| Số query cho một lượt trong triển khai JDBC điển hình | Hai: page + count | Một: items |
| Có `totalElements` | Có | Không |
| Có `totalPages` | Tính được từ count/size | Không |
| Biết có trang tiếp | Có thể tính từ count (ở cùng thời điểm) | Có thể suy ra từ dòng thứ `size + 1` |
| Giao diện phù hợp | Số trang, tổng kết quả, nút trang cuối | “Xem thêm”, load more, feed |
| Rủi ro/trade-off | Count có thể tốn kém; count và items có thể lệch snapshot | Không có tổng số; offset lớn vẫn có thể tốn kém |

Trong Spring Data có các khái niệm `Page`/`Slice`. Tuy nhiên `JdbcTemplate` **không tự tạo** `Page<T>` hoặc tự chạy count cho bạn từ SQL. Với JDBC thuần, bạn có thể trả các record kết quả như `TaskPage` và `TaskSlice` của ví dụ bên dưới.

Cách dùng phổ biến:

- Màn hình có số trang **và** tổng kết quả: Page + count.
- Infinite scrolling hoặc “Tải thêm”: Slice.
- Xuất báo cáo: chưa chắc cần pagination tương tác; có thể cần streaming/batch riêng.
- Tra cứu lớn theo thời gian có cursor: keyset, không nhất thiết dùng offset.

## 6. Tính nhất quán khi dữ liệu thay đổi

### 6.1. OFFSET có thể bị dịch ranh giới

Giả sử trang đầu trả ID `[105, 104, 103]` theo `ORDER BY created_at DESC, id DESC`, `size=3`. Trước khi client gọi trang tiếp theo, có nhiệm vụ mới `106` được chèn vào đầu danh sách. Khi chạy `OFFSET 3` trên tập mới, trang tiếp theo có thể bắt đầu bằng `103` — trùng một dòng với trang trước.

Ngược lại, nếu một dòng ở đầu danh sách bị xóa hoặc cập nhật để không còn hợp filter, offset có thể khiến client **bỏ lỡ** một dòng.

Điểm quan trọng:

- **Tie-breaker duy nhất** giúp có thứ tự rõ trong một trạng thái dữ liệu.
- Nó **không tự đóng băng tập dữ liệu** qua các request HTTP khác nhau.
- Ứng dụng có thể chấp nhận hiện tượng này cho danh sách thường thay đổi; nếu không, cần mô hình pagination nhất quán hơn.

### 6.2. Page query và COUNT query có thể nhìn thấy snapshot khác nhau

Trong triển khai Page thông thường, `SELECT ... LIMIT/OFFSET` và `SELECT COUNT(*)` là hai statement khác nhau. Nếu dữ liệu thay đổi giữa chúng, trang có thể trả 3 dòng nhưng `total` phản ánh một thời điểm khác. Ngay cả khi gọi trong một transaction, **mức isolation** quyết định liệu hai statement có xem cùng snapshot hay không. Chẳng hạn ở PostgreSQL `READ COMMITTED`, hai `SELECT` trong cùng transaction có thể nhìn snapshot khác nhau; dùng `REPEATABLE READ` cho một transaction nhất định có thể cho snapshot nhất quán hơn trong phạm vi transaction đó, nhưng không giữ snapshot đó qua nhiều HTTP requests độc lập.

Không nên hứa một con số count hoàn toàn ổn định trong danh sách đang được cập nhật liên tục. Nếu chức năng cần đối soát/tính chính xác cao, nên có thiết kế snapshot, mốc dữ liệu hoặc giao dịch tương ứng, và chấp nhận trade-off.

### 6.3. Khi nào dùng keyset/cursor pagination?

Offset lớn như `OFFSET 100000` có thể yêu cầu database duyệt/bỏ qua rất nhiều dòng trước khi trả trang hiện tại. B-tree index phù hợp có thể giúp, nhưng chi phí offset vẫn có thể tăng theo vị trí trang.

**Keyset pagination** không nói “bỏ qua 100.000 dòng”; nó nói “lấy các dòng đứng **sau khóa sắp xếp cuối cùng** của trang trước”.

Với thứ tự `created_at DESC, id DESC` và khóa cuối trang trước là `(lastCreatedAt, lastId)`:

```sql
SELECT id, title, created_at
FROM tasks
WHERE tenant_id = ?
  AND status = ?
  AND (
       created_at < ?
       OR (created_at = ? AND id < ?)
  )
ORDER BY created_at DESC, id DESC
LIMIT ?;
```

Ví dụ trang đầu là `[15, 14, 13]`, trong đó dòng 13 có `created_at = 2025-01-03 09:00:00`. Cursor cho trang tiếp theo là cặp `(2025-01-03 09:00:00, 13)`; query tiếp lấy `[12, 11, 18]`. Dòng 14 cùng thời điểm với 13 nhưng có id lớn hơn, nên đã nằm ở trang trước và không được lấy lại.

Trong một số DBMS như PostgreSQL, có thể so sánh bộ giá trị cho trường hợp không NULL:

```sql
AND (created_at, id) < (?, ?)
```

Nhưng hãy kiểm tra cú pháp và quy tắc kiểu dữ liệu của DBMS đang dùng. Cách dùng hai nhánh `OR` nêu trên minh họa điều kiện tương ứng với sắp xếp DESC trên cả hai cột; khi trộn ASC/DESC hoặc sort có NULL, cần xây logic khác.

**Ưu điểm:** truy vấn theo keyset có cơ hội đọc vùng index sau cursor hiệu quả và giảm rủi ro trùng/bỏ dòng do insert trước cursor.

**Giới hạn:**

- Không tiện nhảy thẳng đến “trang 800” nếu chưa biết cursor tương ứng.
- Cần sắp xếp **xác định**, khóa sort được giữ trong cursor và cùng filter khi tải trang tiếp theo.
- Nếu các giá trị dùng làm sort thay đổi, keyset vẫn có thể bỏ lỡ/lặp bản ghi; không phải snapshot toàn bộ lịch sử.
- Cursor public nên là token opaque chứa giá trị cần thiết, version/sort/filter, kèm kiểm tra chữ ký hoặc cơ chế chống chỉnh sửa nếu không muốn client giả mạo. Không dựa vào cursor để thay thế kiểm tra quyền truy cập/tenant ở SQL.
- Các cột sort có `NULL` cần chính sách và biểu thức keyset rõ ràng.

Trong Spring JDBC, triển khai cursor là một SQL khác có placeholder cho `lastCreatedAt`, `lastId`, không cần thay đổi bản chất `JdbcTemplate.query(...)`.

## 7. Chỉ mục và kế hoạch thực thi phục vụ phân trang

Một query thực tế thường chạy nhiều lần với filter + sort giống nhau:

```sql
SELECT id, title, created_at
FROM tasks
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, id DESC
LIMIT ? OFFSET ?;
```

Với PostgreSQL và dữ liệu đủ lớn, một ứng viên để **đánh giá** là index B-tree:

```sql
CREATE INDEX tasks_tenant_status_created_id_idx
ON tasks (tenant_id, status, created_at DESC, id DESC);
```

Lý do: `tenant_id` và `status` là điều kiện bằng; `created_at DESC, id DESC` khớp thứ tự cần lấy. Index phù hợp có thể giúp database tìm và trả trang mà không phải sort toàn bộ tập kết quả. Nó cũng có thể hỗ trợ điều kiện keyset.

**Nhưng index không phải giải pháp tự động:**

- Bảng nhỏ hoặc điều kiện lấy phần lớn dòng có thể khiến quét tuần tự tốt hơn.
- Query `COUNT(*)` có thể dùng một kế hoạch khác query page; index không bảo đảm count được tính “miễn phí”.
- Chỉ mục gây chi phí lưu trữ và duy trì khi chèn/sửa/xóa.
- Index hỗ trợ sort không loại bỏ hoàn toàn chi phí `OFFSET` lớn.
- Hãy đọc `EXPLAIN`/`EXPLAIN ANALYZE` trên DBMS và dữ liệu phù hợp, xác định row estimate, filter, sort và buffer/I/O trước khi quyết định.

Không bắt buộc tạo index trong ví dụ H2 nhỏ ở phần sau: vài dòng dữ liệu có thể chạy rất nhanh bằng quét bảng và điều đó không phản ánh tình huống production.

## 8. Thực hành chạy được: Spring JDBC + H2 + Java 17

Chương trình sau dùng hai kiểu truy vấn:

1. **Page**: trả items và `COUNT(*)` chính xác theo filter tại thời điểm thực hiện từng statement.
2. **Slice**: lấy thêm một dòng để xác định `hasNext` mà không gọi count.

Đồng thời, nó giải thích vì sao `ORDER BY created_at DESC, id DESC` cho kết quả xác định khi timestamp trùng.

### 8.1. Cấu trúc dự án

```text
jdbc-paging-demo/
├── build.gradle
└── src/main/java/example/JdbcPagingDemo.java
```

### 8.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.JdbcPagingDemo'
}
```

Giả định đã cài Gradle phiên bản hỗ trợ Java 17 hoặc có Gradle Wrapper tương ứng. Cần kết nối Maven Central để tải thư viện khi chưa có cache. Không cần Spring Boot hoặc database server riêng.

### 8.3. File Java hoàn chỉnh

Tạo `src/main/java/example/JdbcPagingDemo.java`:

```java
package example;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration
public class JdbcPagingDemo {
    record TaskView(long id, String title, LocalDateTime createdAt) {}
    record TaskPage(List<TaskView> items, int page, int size, long total) {}
    record TaskSlice(List<TaskView> items, boolean hasNext) {}

    private static final RowMapper<TaskView> TASK_MAPPER =
            (rs, rowNumber) -> new TaskView(
                    rs.getLong("id"),
                    rs.getString("title"),
                    rs.getTimestamp("created_at").toLocalDateTime()
            );

    private static final String PAGE_SQL = """
            SELECT id, title, created_at
            FROM tasks
            WHERE tenant_id = ? AND status = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """;

    private static final String COUNT_SQL = """
            SELECT COUNT(*)
            FROM tasks
            WHERE tenant_id = ? AND status = ?
            """;

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource source = new DriverManagerDataSource();
        source.setDriverClassName("org.h2.Driver");
        source.setUrl("jdbc:h2:mem:paging_demo;DB_CLOSE_DELAY=-1");
        source.setUsername("sa");
        source.setPassword("");
        return source;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    private static void validate(int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "page must be >= 0, size must be 1..100");
        }
    }

    static TaskPage fetchPage(
            JdbcTemplate jdbc, long tenantId, String status,
            int page, int size) {
        validate(page, size);
        long offset = (long) page * size;

        List<TaskView> items = jdbc.query(
                PAGE_SQL, TASK_MAPPER,
                tenantId, status, size, offset);

        Long total = jdbc.queryForObject(
                COUNT_SQL, Long.class, tenantId, status);

        // COUNT(*) without GROUP BY always returns one non-null row.
        return new TaskPage(items, page, size, total);
    }

    static TaskSlice fetchSlice(
            JdbcTemplate jdbc, long tenantId, String status,
            int page, int size) {
        validate(page, size);
        long offset = (long) page * size;

        // Lấy dư 1 dòng thay vì chạy COUNT(*).
        List<TaskView> fetched = jdbc.query(
                PAGE_SQL, TASK_MAPPER,
                tenantId, status, size + 1, offset);

        boolean hasNext = fetched.size() > size;
        List<TaskView> visible = List.copyOf(
                fetched.subList(0, Math.min(size, fetched.size())));
        return new TaskSlice(visible, hasNext);
    }

    static void insert(
            JdbcTemplate jdbc, long id, long tenantId, String status,
            String timestamp, String title) {
        jdbc.update(
                """
                INSERT INTO tasks (id, tenant_id, status, created_at, title)
                VALUES (?, ?, ?, ?, ?)
                """,
                id, tenantId, status,
                Timestamp.valueOf(timestamp), title);
    }

    private static List<Long> ids(List<TaskView> tasks) {
        return tasks.stream().map(TaskView::id).toList();
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                JdbcPagingDemo.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE tasks (
                        id BIGINT PRIMARY KEY,
                        tenant_id BIGINT NOT NULL,
                        status VARCHAR(12) NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        title VARCHAR(40) NOT NULL
                    )
                    """);

            insert(jdbc, 11, 7, "OPEN",   "2025-01-02 09:00:00", "A");
            insert(jdbc, 12, 7, "OPEN",   "2025-01-02 09:00:00", "B");
            insert(jdbc, 13, 7, "OPEN",   "2025-01-03 09:00:00", "C");
            insert(jdbc, 14, 7, "OPEN",   "2025-01-03 09:00:00", "D");
            insert(jdbc, 15, 7, "OPEN",   "2025-01-04 09:00:00", "E");
            insert(jdbc, 16, 7, "CLOSED", "2025-01-05 09:00:00", "F");
            insert(jdbc, 17, 8, "OPEN",   "2025-01-06 09:00:00", "G");
            insert(jdbc, 18, 7, "OPEN",   "2025-01-01 09:00:00", "H");

            TaskPage p0 = fetchPage(jdbc, 7, "OPEN", 0, 3);
            TaskPage p1 = fetchPage(jdbc, 7, "OPEN", 1, 3);
            TaskPage p2 = fetchPage(jdbc, 7, "OPEN", 2, 3);

            System.out.println(
                    "page0=" + ids(p0.items()) + ",total=" + p0.total());
            System.out.println(
                    "page1=" + ids(p1.items()) + ",total=" + p1.total());
            System.out.println(
                    "page2=" + ids(p2.items()) + ",total=" + p2.total());

            TaskSlice s0 = fetchSlice(jdbc, 7, "OPEN", 0, 3);
            TaskSlice s1 = fetchSlice(jdbc, 7, "OPEN", 1, 3);

            System.out.println(
                    "slice0=" + ids(s0.items()) +
                    ",hasNext=" + s0.hasNext());
            System.out.println(
                    "slice1=" + ids(s1.items()) +
                    ",hasNext=" + s1.hasNext());

            long totalPages =
                    p0.total() / p0.size() +
                    (p0.total() % p0.size() == 0 ? 0 : 1);
            System.out.println("totalPages=" + totalPages);
        }
    }
}
```

**Điểm kỹ thuật:**

- `JdbcTemplate.query(...)` nhận các tham số theo đúng thứ tự `tenantId, status, size, offset`, đối ứng các dấu `?` trong `PAGE_SQL`.
- `fetchPage` chạy hai SQL: lấy items và count. `COUNT_SQL` giữ nguyên filter `tenant_id/status`, không có `ORDER BY` hay `LIMIT/OFFSET`.
- `fetchSlice` chỉ chạy query lấy `size + 1` dòng, rồi chỉ trả tối đa `size` dòng cho client.
- `validate` cấm `size=0`, size quá lớn và page âm; `(long) page * size` tránh overflow của phép nhân `int`.
- Hai dòng ID 13 và 14 cùng `created_at`, hai dòng 11 và 12 cũng vậy. Khóa phụ `id DESC` quyết định chính xác thứ tự.
- `DriverManagerDataSource` phù hợp demo, nhưng không dùng làm connection pool production. `DB_CLOSE_DELAY=-1` giữ H2 in-memory tồn tại giữa những lần đóng connection trong một JVM.

### 8.4. Lệnh chạy và stdout

Từ thư mục có `build.gradle`:

```bash
gradle run
```

Nếu dự án có Gradle Wrapper, có thể dùng `./gradlew run` (Linux/macOS) hoặc `gradlew.bat run` (Windows). Gradle sẽ in log build riêng. **Các dòng do chương trình Java in** là:

```text
page0=[15, 14, 13],total=6
page1=[12, 11, 18],total=6
page2=[],total=6
slice0=[15, 14, 13],hasNext=true
slice1=[12, 11, 18],hasNext=false
totalPages=2
```

Giải thích kết quả:

1. Có 8 dòng tổng cộng trong bảng nhưng filter `tenant_id=7 AND status='OPEN'` chỉ chọn **6 dòng**: 11, 12, 13, 14, 15, 18. ID 16 bị loại vì CLOSED; ID 17 bị loại vì tenant 8.
2. Sắp xếp mới nhất trước rồi giảm dần theo ID: `15, 14, 13, 12, 11, 18`.
3. Trang 0, size 3, offset 0 trả `[15,14,13]`; trang 1, offset 3 trả `[12,11,18]`.
4. Trang 2, offset 6 trả rỗng nhưng tổng số **vẫn 6**. `COUNT(*)` không thể lấy từ `items.size()` của trang cuối.
5. Slice 0 lấy tối đa 4 dòng, gặp dòng thứ 4 nên `hasNext=true` nhưng chỉ hiển thị 3. Slice 1 chỉ lấy 3 dòng còn lại, nên `hasNext=false`.
6. `totalPages = 6 / 3 = 2` trang có dữ liệu, theo đánh số 0 và 1.

Không phải bản demo transaction của nhiều truy vấn: hai statement trong `fetchPage` chạy tuần tự, dữ liệu mẫu không thay đổi giữa chúng, nên đầu ra xác định.

## 9. Đóng gói thành API/repository của ứng dụng Spring

### 9.1. Nơi nên đặt logic

Một phân chia trách nhiệm hợp lý:

```text
HTTP controller
  -> validate/canonicalize page, size, sort
  -> application service
     -> TaskRepository
        -> JdbcTemplate.query(...) cho items
        -> JdbcTemplate.queryForObject(...) cho COUNT nếu cần
     -> trả TaskPage / TaskSlice
  -> JSON response
```

Không đặt SQL xây `LIMIT/OFFSET` trong controller. Repository hiểu cột/table/query; service hiểu chính sách nghiệp vụ; controller hiểu HTTP và kiểu tham số đầu vào.

Response kiểu Page có thể là:

```json
{
  "items": [
    {"id": 15, "title": "E"},
    {"id": 14, "title": "D"},
    {"id": 13, "title": "C"}
  ],
  "page": 0,
  "size": 3,
  "totalElements": 6,
  "totalPages": 2
}
```

Response kiểu Slice có thể là:

```json
{
  "items": [
    {"id": 15, "title": "E"},
    {"id": 14, "title": "D"},
    {"id": 13, "title": "C"}
  ],
  "page": 0,
  "size": 3,
  "hasNext": true
}
```

Đây là **mẫu JSON contract**, không phải response được chương trình demo Java tạo tự động. Đừng công bố `totalElements=6` trong Slice nếu chưa thực sự đếm. Nếu API cần count chỉ ở trang đầu, đó là lựa chọn contract cần mô tả rõ thay vì thay đổi âm thầm giữa các request.

### 9.2. API contract cần rõ những gì?

- Page tính từ **0 hay 1**.
- Size mặc định và size tối đa.
- Sort nào được phép và khóa phụ nào giúp ổn định thứ tự.
- Có trả `totalElements`/`totalPages` hay chỉ `hasNext`.
- Cách xử lý page vượt quá cuối tập kết quả: trả empty list, hay quy ước khác.
- Tiêu chí filter theo tenant/user và thời gian được áp dụng nhất quán.
- Độ chính xác/thời điểm của total khi dữ liệu đồng thời thay đổi.
- Với cursor, token có thời hạn/có gắn với filter/sort nào.

Trong hệ thống nhiều tenant, **không bao giờ** tin tenantId do client gửi nếu chưa kiểm tra người dùng được phép truy cập tenant đó. SQL list và count đều phải thực thi scope quyền truy cập tương đương.

### 9.3. Một repository cần xử lý sort do client chọn

Khi cho client chọn `newest` hoặc `oldest`, nên dùng allowlist từ mục 2.4 rồi tạo hai SQL có cấu trúc cố định hoặc dùng một đoạn `ORDER BY` được chọn từ allowlist. Chỉ bind `tenantId`, `status`, `size`, `offset` làm dữ liệu. Không xây nguyên mệnh đề `ORDER BY` từ chuỗi request chưa kiểm tra.

Nếu filter tăng từ hai điều kiện thành nhiều điều kiện tùy chọn, phải giữ đồng bộ logic giữa query items và count. Có thể tách phần filter chung thành hàm xây SQL có kiểm soát hoặc dùng named parameters, nhưng phải test đúng câu SQL sau khi tổ hợp các lựa chọn filter.

## 10. Lỗi và tình huống biên phải thử

| Tình huống | Kỳ vọng/điều cần xem |
| --- | --- |
| `page=0, size=3` | Offset 0, trả tối đa 3 dòng đầu theo thứ tự |
| `page=1, size=3` | Offset 3, trả tối đa 3 dòng kế tiếp |
| Filter không có kết quả | Items rỗng; Page có count = 0; Slice có `hasNext=false` |
| Page vượt cuối | Items rỗng; Page có thể vẫn có `total > 0` |
| `size=0`, âm hoặc quá giới hạn | Trả lỗi validation trước khi gọi JDBC |
| `page < 0` | Trả lỗi validation |
| Hai dòng có cùng timestamp | Khóa phụ unique bảo đảm thứ tự tường minh |
| Sort field không nằm trong allowlist | Từ chối input, không ghép SQL tùy ý |
| Dòng được chèn/xóa giữa hai request | OFFSET có thể trùng/bỏ dòng; đánh giá cursor hoặc snapshot |
| Total query quên tenant/filter | Kết quả sai và có thể lộ thông tin; test list/count cùng scope |
| JOIN tạo duplicate | Đếm thực thể phải xét `DISTINCT`/`EXISTS`/cách trang trên tập unique |
| `OFFSET` rất lớn | Có thể chậm; đọc plan và cân nhắc keyset |
| Dữ liệu đọc trong cùng page thay đổi giữa hai SQL | `items` và `total` có thể phản ánh snapshot khác |

### 10.1. Các bài kiểm thử hữu ích

1. Tạo ít hơn một trang; kiểm tra `items.size()`, `total` và `hasNext`.
2. Tạo đúng một trang; Slice không được báo có trang tiếp.
3. Tạo một dòng nhiều hơn page size; Slice phải báo có trang tiếp.
4. Tạo cặp dòng trùng `created_at`; kiểm tra thứ tự theo `id` và không mất dòng khi chuyển trang.
5. Truy vấn `page=2` khi chỉ có 2 trang, xác nhận items rỗng nhưng total không bằng 0.
6. So danh sách các ID ghép qua các trang với kết quả query không phân trang trên **một tập dữ liệu cố định**; không trùng/không thiếu.
7. Dùng tenant khác và status khác, kiểm tra count không đếm dòng ngoài scope.
8. Thử query sort không được hỗ trợ, size vượt giới hạn, page âm và page quá lớn.
9. Với hệ thực dùng PostgreSQL/MySQL, integration test trên DBMS đó; H2 không mô phỏng mọi khác biệt về NULL sort, execution plan hoặc driver.

## 11. Các hiểu nhầm cần tránh

**“Chỉ cần LIMIT/OFFSET là đã phân trang đúng.”** Sai: cần `ORDER BY` rõ; không có sort thì từng trang không có ý nghĩa ổn định.

**“Đã ORDER BY created_at là thứ tự xác định.”** Chưa chắc: nhiều dòng có cùng thời gian. Thêm khóa phụ unique phù hợp.

**“COUNT(*) luôn miễn phí.”** Sai: count có thể là truy vấn đáng kể, đặc biệt với filter phức tạp và lượng dữ liệu lớn. Chỉ chạy khi contract cần.

**“total = items.size().”** Sai: đó chỉ là số dòng trang hiện tại, không phải tổng toàn bộ dữ liệu phù hợp.

**“Trang rỗng chứng tỏ database không có dữ liệu.”** Sai: offset vượt cuối tập cũng trả trang rỗng.

**“Dấu ? có thể thay ORDER BY bằng tên cột người dùng chọn.”** Sai: placeholder bind dữ liệu, không bind identifier/keyword SQL. Dùng allowlist.

**“Có ORDER BY với PK phụ thì sẽ không bao giờ trùng giữa các request.”** Sai: dữ liệu thay đổi làm offset dịch chuyển; keyset hoặc snapshot có thể phù hợp hơn.

**“Một transaction luôn làm page và count nhìn cùng snapshot.”** Sai trong mọi DBMS/isolation level; phải xét chính sách snapshot cụ thể.

**“Index giải quyết hoàn toàn offset 1.000.000.”** Sai: database vẫn có thể phải di chuyển qua nhiều mục để bỏ qua offset; keyset là lựa chọn khác khi use case phù hợp.

## 12. Câu hỏi tự kiểm tra

1. Với `page=4`, `size=25` và số trang bắt đầu từ 0, offset bằng bao nhiêu? Nếu page bắt đầu từ 1 thì sao?
2. Tại sao `ORDER BY created_at DESC` có thể chưa đủ? Hãy thêm một khóa phụ thích hợp.
3. Nếu `query` trả 0 dòng ở trang 5, tại sao không được tự kết luận `totalElements=0`?
4. Màn hình có nút “Xem thêm” nhưng không hiển thị số trang. Bạn cần `COUNT(*)` không?
5. Nếu `size=20`, Slice cần yêu cầu tối đa bao nhiêu dòng để tính `hasNext`?
6. Vì sao count query và item query phải dùng cùng filter theo tenant và status?
7. Với JOIN tags một-nhiều, `COUNT(*)` và `COUNT(DISTINCT t.id)` khác nhau trong tình huống nào?
8. Khi có insert mới ngay đầu danh sách giữa hai request, offset có thể gây ra lỗi gì?
9. Với `ORDER BY created_at DESC, id DESC`, cursor ở `(T, 42)` thì dòng tiếp theo cần thỏa điều kiện thời gian/id nào?
10. Có thể đưa `request.sort` trực tiếp vào SQL không? Cách làm an toàn hơn là gì?

**Ghi nhớ:** Phân trang JDBC đúng = **filter đúng + ORDER BY tường minh có khóa phụ duy nhất + LIMIT/OFFSET được validate**. Chỉ lấy **COUNT(*)** khi cần tổng số; nếu chỉ cần “có trang tiếp hay không”, lấy **size + 1**. Khi dữ liệu lớn hoặc biến động liên tục, cân nhắc **keyset pagination** và chính sách nhất quán kết quả.

### Tài liệu tra cứu thêm

- Spring Framework: [JDBC core — JdbcTemplate](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html).
- Spring Framework: [JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html).
- PostgreSQL: [LIMIT and OFFSET](https://www.postgresql.org/docs/current/queries-limit.html).
- PostgreSQL: [Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html).
- PostgreSQL: [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
