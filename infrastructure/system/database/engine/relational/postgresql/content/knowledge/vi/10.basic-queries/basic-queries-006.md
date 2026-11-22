# ORDER BY, nhiều khóa sắp xếp và NULLS FIRST hoặc LAST trong PostgreSQL

## 1. Vì sao cần hiểu ORDER BY thay vì chỉ thêm một dòng SQL?

Trong ứng dụng, người dùng thường yêu cầu dữ liệu xuất hiện theo một thứ tự rõ ràng:

- Danh sách phiếu hỗ trợ: **ưu tiên cao trước**, phiếu cũ trước hoặc mới trước theo quy tắc nghiệp vụ.
- Danh sách hóa đơn: **ngày phát hành mới nhất trước**, nếu trùng ngày thì sắp theo mã hóa đơn.
- Bảng xếp hạng: **điểm cao nhất trước**, nếu cùng điểm thì dùng thời gian và ID để phân định.
- Danh sách công việc: **hạn hoàn thành gần nhất trước**, còn những công việc chưa có hạn thì để cuối.
- Trang tìm kiếm: sắp ổn định khi người dùng chuyển từ trang 1 sang trang 2.

PostgreSQL dùng mệnh đề **`ORDER BY`** để yêu cầu thứ tự các dòng trong **kết quả truy vấn**. Khi cần sắp theo nhiều tiêu chí, ta khai báo **nhiều khóa sắp xếp**, mỗi khóa có thể có chiều `ASC` hoặc `DESC` và vị trí của giá trị `NULL`.

Ví dụ:

```sql
SELECT ticket_id, team, priority, created_at
FROM sort_lab.tickets
ORDER BY
    team ASC,
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id ASC;
```

Câu SQL này thể hiện bốn tầng quy tắc. Trong từng `team`:

1. Ưu tiên `1` trước `2`, `3`; phiếu chưa có `priority` ở cuối.
2. Nếu cùng ưu tiên, phiếu mới hơn đứng trước.
3. Nếu vẫn trùng thời gian, ID nhỏ hơn đứng trước.

Điểm quan trọng: **Không có `ORDER BY` ở truy vấn cuối cùng thì PostgreSQL không cam kết thứ tự trả về**. Thấy kết quả tình cờ theo ID hoặc thứ tự chèn trên dữ liệu mẫu không phải một bảo đảm của SQL.

Sau bài, bạn sẽ biết cách:

1. Dùng `ORDER BY` với `ASC`, `DESC`, biểu thức, bí danh và nhiều khóa.
2. Giải thích chính xác mặc định `NULLS FIRST`/`NULLS LAST` trong PostgreSQL.
3. Tạo thứ tự **xác định hoàn toàn** bằng tie-breaker, đặc biệt trước khi dùng `LIMIT`, `OFFSET`.
4. Sắp xếp theo thứ tự nghiệp vụ riêng, xử lý chuỗi, chữ hoa/thường và collation.
5. Phân biệt thứ tự kết quả ngoài với thứ tự trong `DISTINCT ON`, window function và aggregate.
6. Đọc `EXPLAIN`, hiểu khi nào B-tree index hỗ trợ tránh một bước sort.
7. Thiết kế keyset pagination và nhận diện vấn đề với khóa nullable.
8. Tránh những lỗi SQL thường gặp khi sắp xếp và phân trang.

> Những lệnh tạo bảng/chèn dữ liệu trong bài chỉ thực hiện trên **database thực hành**. Trên hệ thống thật, hãy chạy các truy vấn đọc với phạm vi và quyền phù hợp, không thêm chỉ mục tùy tiện.

---

## 2. Chuẩn bị dữ liệu mẫu để thực hành

Dùng một schema độc lập để tránh nhầm với bảng nghiệp vụ có sẵn:

```sql
CREATE SCHEMA IF NOT EXISTS sort_lab;

CREATE TABLE sort_lab.tickets (
    ticket_id INTEGER PRIMARY KEY,
    team TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('NEW', 'OPEN', 'RESOLVED')),
    priority SMALLINT CHECK (priority BETWEEN 1 AND 3),
    score NUMERIC(5,2),
    assigned_to TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    due_at TIMESTAMPTZ
);
```

Quy ước của bộ dữ liệu:

- `priority = 1`: ưu tiên cao nhất; `2`: trung bình; `3`: thấp.
- `priority IS NULL`: chưa được phân loại.
- `score` có thể chưa được chấm.
- `assigned_to` có thể chưa có người phụ trách.
- `due_at` có thể chưa có hạn hoàn thành.
- `created_at` là một mốc thời gian, lưu bằng `TIMESTAMPTZ`.

Chú ý: `CHECK (priority BETWEEN 1 AND 3)` **không cấm NULL**. Trong PostgreSQL, một `CHECK` không bị vi phạm nếu kết quả là `TRUE` hoặc `UNKNOWN`; vì vậy cột nullable cần được xử lý rõ trong truy vấn.

Nạp 12 phiếu:

```sql
INSERT INTO sort_lab.tickets
    (ticket_id, team, status, priority, score,
     assigned_to, created_at, due_at)
VALUES
    (101, 'Support', 'OPEN', 1, 90, 'An',
     TIMESTAMPTZ '2026-02-01 09:00:00+07',
     TIMESTAMPTZ '2026-02-03 09:00:00+07'),

    (102, 'Support', 'OPEN', 1, 90, 'Bình',
     TIMESTAMPTZ '2026-02-01 09:00:00+07', NULL),

    (103, 'Support', 'NEW', 2, 80, NULL,
     TIMESTAMPTZ '2026-02-01 10:00:00+07',
     TIMESTAMPTZ '2026-02-03 17:00:00+07'),

    (104, 'Billing', 'OPEN', 1, 95, 'Chi',
     TIMESTAMPTZ '2026-02-02 08:00:00+07',
     TIMESTAMPTZ '2026-02-04 12:00:00+07'),

    (105, 'Billing', 'RESOLVED', 3, 70, 'An',
     TIMESTAMPTZ '2026-02-02 09:00:00+07', NULL),

    (106, 'Support', 'OPEN', 2, 80, 'Bình',
     TIMESTAMPTZ '2026-02-01 10:00:00+07',
     TIMESTAMPTZ '2026-02-05 10:00:00+07'),

    (107, 'Sales', 'NEW', NULL, NULL, NULL,
     TIMESTAMPTZ '2026-02-03 09:00:00+07', NULL),

    (108, 'Sales', 'OPEN', 3, 70, 'Chi',
     TIMESTAMPTZ '2026-02-03 11:00:00+07',
     TIMESTAMPTZ '2026-02-06 14:00:00+07'),

    (109, 'Billing', 'NEW', NULL, 80, 'An',
     TIMESTAMPTZ '2026-02-04 10:00:00+07',
     TIMESTAMPTZ '2026-02-04 18:00:00+07'),

    (110, 'Support', 'RESOLVED', 3, NULL, 'An',
     TIMESTAMPTZ '2026-02-04 10:00:00+07',
     TIMESTAMPTZ '2026-02-07 12:00:00+07'),

    (111, 'Sales', 'OPEN', 1, 95, 'Bình',
     TIMESTAMPTZ '2026-02-05 08:00:00+07', NULL),

    (112, 'Support', 'NEW', 2, 80, 'Chi',
     TIMESTAMPTZ '2026-02-05 09:00:00+07',
     TIMESTAMPTZ '2026-02-06 16:00:00+07');
```

Kiểm tra:

```sql
SELECT COUNT(*) AS number_of_tickets
FROM sort_lab.tickets;
```

Kỳ vọng `12` nếu chỉ nạp một lần.

**Lưu ý về môi trường:** câu `CREATE TABLE` không có `IF NOT EXISTS`. Nếu đã tạo bảng ở lần chạy trước, hãy dùng database/schema lab sạch hoặc xử lý dữ liệu thử nghiệm theo quy trình được phép; không xóa bảng lạ chỉ để chạy lại ví dụ.

### 2.1. Xem dữ liệu có trật tự rõ ràng

```sql
SELECT
    ticket_id,
    team,
    status,
    priority,
    created_at
FROM sort_lab.tickets
ORDER BY ticket_id;
```

Với `ORDER BY ticket_id`, kết quả được yêu cầu tăng dần theo ID. Đây là cách đọc dữ liệu mẫu dễ đối chiếu, **không phải bằng chứng rằng bảng PostgreSQL tự lưu cố định theo thứ tự ID**.

## 3. Cú pháp ORDER BY tổng quát

Cú pháp rút gọn:

```sql
SELECT expression_or_columns
FROM relation
WHERE condition
ORDER BY
    sort_expression_1 [ASC | DESC] [NULLS FIRST | NULLS LAST],
    sort_expression_2 [ASC | DESC] [NULLS FIRST | NULLS LAST],
    ...
LIMIT number;
```

Ví dụ:

```sql
SELECT ticket_id, priority, created_at
FROM sort_lab.tickets
ORDER BY priority ASC NULLS LAST, created_at DESC, ticket_id ASC
LIMIT 10;
```

Đặc điểm:

- `ORDER BY` có thể gồm **một hoặc nhiều** biểu thức.
- Các khóa được xét **từ trái sang phải**.
- `ASC` nghĩa là tăng dần; `DESC` nghĩa là giảm dần.
- Không viết chiều thì PostgreSQL mặc định `ASC`.
- `NULLS FIRST` và `NULLS LAST` kiểm soát vị trí `NULL` **cho từng khóa riêng**.
- Có thể thêm **khóa phá hòa (tie-breaker)** để tránh nhiều hàng có cùng bộ khóa.
- `ORDER BY` chỉ đảm bảo **thứ tự xuất kết quả** của truy vấn tương ứng. Nó không đặt một thứ tự vật lý vĩnh viễn cho bảng.

### 3.1. Đơn giản nhất: tăng dần

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
WHERE priority IS NOT NULL
ORDER BY priority;
```

Tương đương:

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
WHERE priority IS NOT NULL
ORDER BY priority ASC;
```

Do nhiều phiếu có cùng mức ưu tiên, thứ tự **giữa những phiếu cùng priority chưa được bảo đảm**.

Nếu muốn rõ ràng:

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
WHERE priority IS NOT NULL
ORDER BY priority ASC, ticket_id ASC;
```

### 3.2. Giảm dần

```sql
SELECT ticket_id, score
FROM sort_lab.tickets
WHERE score IS NOT NULL
ORDER BY score DESC, ticket_id ASC;
```

Các điểm 95 xuất hiện trước 90, 80, 70. Khi hai hàng cùng điểm, ID nhỏ hơn đứng trước.

Từ `DESC` chỉ đảo chiều khóa **ngay trước nó**, không mặc định đảo các khóa còn lại.

### 3.3. ORDER BY không thay đổi dữ liệu trong bảng

```sql
SELECT ticket_id, created_at
FROM sort_lab.tickets
ORDER BY created_at DESC;
```

Câu này không ghi dữ liệu, không tự `UPDATE`, không sắp xếp lại hàng trên đĩa. PostgreSQL chọn một kế hoạch truy vấn trả hàng theo thứ tự được yêu cầu, có thể dùng index hoặc một thao tác sort.

Không sử dụng `ORDER BY` như một biện pháp “lưu dữ liệu có thứ tự” vĩnh viễn.

## 4. ORDER BY với nhiều khóa: quy tắc từ trái sang phải

Giả sử cần danh sách theo:

1. Team tăng dần theo quy tắc chuỗi/collation.
2. Trong team, ưu tiên cao (`1`) đứng trước.
3. Trong cùng mức ưu tiên, phiếu mới hơn đứng trước.
4. Nếu trùng cả ba, ID nhỏ hơn trước.

```sql
SELECT
    ticket_id,
    team,
    priority,
    created_at
FROM sort_lab.tickets
ORDER BY
    team ASC,
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id ASC;
```

Diễn giải:

```text
team
  ├── Billing
  │     ├── priority 1
  │     ├── priority 3
  │     └── priority NULL
  ├── Sales
  │     ├── priority 1
  │     ├── priority 3
  │     └── priority NULL
  └── Support
        ├── priority 1
        ├── priority 2
        └── priority 3
```

Sơ đồ là thứ tự nhóm mang tính minh họa trong collation thông thường của dữ liệu mẫu; so sánh các chuỗi khác có thể phụ thuộc collation.

### 4.1. Chỉ dùng khóa thứ hai khi khóa thứ nhất bằng nhau

Trong:

```sql
ORDER BY team ASC, priority ASC
```

PostgreSQL **không** so `priority` trên toàn bảng trước, rồi mới so team. Nó so `team` trước; **chỉ những hàng có cùng team** mới được phân định bởi priority.

Tương tự:

```sql
ORDER BY priority ASC, created_at DESC
```

khác hoàn toàn:

```sql
ORDER BY created_at DESC, priority ASC
```

Vế trái thể hiện **thứ tự ưu tiên của các quy tắc**.

### 4.2. Chiều sắp xếp khai báo riêng cho từng khóa

```sql
ORDER BY team ASC, priority DESC, ticket_id ASC
```

nghĩa là:

- Team tăng dần.
- Trong team, số priority **lớn hơn** trước.
- Khi trùng team và priority, ID nhỏ hơn trước.

Lưu ý hệ thống mẫu định nghĩa priority số **1 là cao nhất**, nên `DESC` đặt ưu tiên thấp (`3`) trước. Cú pháp đúng chưa chắc đúng nghiệp vụ: phải xem **giá trị và định nghĩa của cột**.

### 4.3. Cách nghĩ bằng phép so sánh từ điển

ORDER BY nhiều cột tương tự so sánh các cặp/tập giá trị theo thứ tự từ điển:

```text
(team, priority, created_at, ticket_id)
```

Khi so hai hàng:

1. Nếu team khác nhau, chỉ cần team.
2. Nếu team bằng, so priority.
3. Nếu cùng priority, so created_at theo chiều đã chỉ định.
4. Nếu tiếp tục bằng, so ticket_id.

Khóa cuối là một ID duy nhất giúp đạt thứ tự xác định hoàn toàn.

### 4.4. Tập con thực hành có thứ tự có thể kiểm chứng

```sql
SELECT ticket_id, priority, created_at
FROM sort_lab.tickets
WHERE team = 'Support'
  AND priority IS NOT NULL
ORDER BY priority ASC, created_at DESC, ticket_id ASC;
```

Trong dữ liệu mẫu, thứ tự ID là:

```text
101, 102, 112, 103, 106, 110
```

Giải thích:

- Priority 1: `101`, `102` cùng timestamp, ID nhỏ hơn trước.
- Priority 2: `112` mới nhất, tiếp theo `103`, `106` cùng timestamp (ID 103 trước).
- Priority 3: `110`.

Đây là ví dụ cho thấy khóa thứ ba và thứ tư có tác dụng **phá hòa**.

## 5. NULL là gì trong sắp xếp PostgreSQL?

### 5.1. SQL NULL không phải 0 hay chuỗi rỗng

Một phiếu có:

```text
priority = NULL
```

nghĩa là chưa biết hoặc chưa gán ưu tiên, không phải `priority=0`, `priority=3` hoặc `priority=''`.

Khi sắp xếp, PostgreSQL cần quyết định những giá trị NULL nằm ở đâu. Điều đó được điều khiển bằng:

```sql
NULLS FIRST
NULLS LAST
```

### 5.2. Mặc định của PostgreSQL

Với PostgreSQL, thứ tự mặc định là:

| Cú pháp | Xếp NULL theo mặc định |
|---|---|
| `ORDER BY x` | `ASC NULLS LAST` |
| `ORDER BY x ASC` | `NULLS LAST` |
| `ORDER BY x DESC` | `NULLS FIRST` |
| `ORDER BY x ASC NULLS FIRST` | NULL đầu |
| `ORDER BY x ASC NULLS LAST` | NULL cuối |
| `ORDER BY x DESC NULLS FIRST` | NULL đầu |
| `ORDER BY x DESC NULLS LAST` | NULL cuối |

**Quy tắc dễ nhớ của PostgreSQL:** trong so sánh ORDER BY mặc định, NULL được xử lý như giá trị **lớn hơn các giá trị không NULL**. Bởi vậy tăng dần thì NULL ở cuối, giảm dần thì NULL ở đầu.

Đây là **hành vi của PostgreSQL**, không nên suy luận rằng mọi DBMS đều có cùng mặc định. Nếu tính nhất quán giữa nhiều hệ CSDL hoặc sự rõ ràng cho người đọc là quan trọng, hãy **viết tường minh**.

### 5.3. Quan sát bốn kiểu sắp xếp

Chọn bốn phiếu có priority lần lượt 1, 2, 3 và NULL:

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
WHERE ticket_id IN (101, 103, 105, 107)
ORDER BY priority ASC NULLS LAST, ticket_id;
```

Kết quả ưu tiên:

```text
ticket_id | priority
----------+---------
101       | 1
103       | 2
105       | 3
107       | NULL
```

Tăng dần, NULL lên đầu:

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
WHERE ticket_id IN (101, 103, 105, 107)
ORDER BY priority ASC NULLS FIRST, ticket_id;
```

Thứ tự ID:

```text
107, 101, 103, 105
```

Giảm dần, NULL lên đầu:

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
WHERE ticket_id IN (101, 103, 105, 107)
ORDER BY priority DESC NULLS FIRST, ticket_id;
```

Thứ tự ID:

```text
107, 105, 103, 101
```

Giảm dần, NULL xuống cuối:

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
WHERE ticket_id IN (101, 103, 105, 107)
ORDER BY priority DESC NULLS LAST, ticket_id;
```

Thứ tự ID:

```text
105, 103, 101, 107
```

### 5.4. Tình huống nghiệp vụ thường gặp

Danh sách hạn hoàn thành gần nhất trước, phiếu chưa có hạn cuối danh sách:

```sql
SELECT ticket_id, due_at
FROM sort_lab.tickets
ORDER BY due_at ASC NULLS LAST, ticket_id ASC;
```

Bảng điểm từ cao xuống thấp, chưa có điểm ở cuối:

```sql
SELECT ticket_id, score
FROM sort_lab.tickets
ORDER BY score DESC NULLS LAST, ticket_id ASC;
```

Bảng ưu tiên những phiếu chưa được phân loại để nhân viên triage trước:

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
ORDER BY priority ASC NULLS FIRST, ticket_id ASC;
```

`NULLS FIRST/LAST` **không làm thay đổi** giá trị NULL trong bảng và **không loại bỏ** hàng NULL khỏi kết quả; nó chỉ quyết định vị trí tương đối của chúng.

## 6. NULLS FIRST/LAST áp dụng riêng cho từng khóa

Xét:

```sql
SELECT
    ticket_id,
    team,
    priority,
    due_at
FROM sort_lab.tickets
ORDER BY
    team ASC,
    priority ASC NULLS LAST,
    due_at ASC NULLS LAST,
    ticket_id ASC;
```

Có hai cột nullable: `priority` và `due_at`.

Quy trình sắp xếp:

1. Phân nhóm thứ tự theo team.
2. Trong mỗi team, phiếu priority 1, 2, 3 trước, NULL sau.
3. Trong cùng priority, những hạn gần nhất trước, chưa có hạn sau.
4. Trong những hàng vẫn bằng nhau, dùng ID.

**Một `NULLS LAST` ở cuối chỉ ảnh hưởng đến khóa ngay trước nó.**

Ví dụ sau:

```sql
ORDER BY priority DESC NULLS LAST, due_at ASC NULLS FIRST
```

có nghĩa **priority NULL cuối mỗi nhóm theo khóa trước**, nhưng với những hàng có cùng priority, due_at NULL lại ở **đầu nhóm con**. Không có quy tắc "NULL luôn cuối toàn bộ danh sách" áp dụng chung cho mọi khóa.

### 6.1. NULL và tie-breaker

Nhiều hàng có `priority NULL`. Vì chúng cùng giá trị NULL để phân nhóm sort theo key đó, các khóa sau mới quyết định thứ tự của chúng.

```sql
SELECT ticket_id, priority, created_at
FROM sort_lab.tickets
ORDER BY
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id DESC;
```

Trong nhóm priority NULL, phiếu `109` và `107` được sắp bởi `created_at` giảm dần. Nếu hai phiếu trùng timestamp, ID mới là khóa phá hòa cuối.

### 6.2. CASE để xếp NULL không giống COALESCE

Một cách thay thế là:

```sql
ORDER BY priority IS NULL ASC, priority ASC, ticket_id ASC
```

Trong PostgreSQL, biểu thức boolean sắp tăng dần đặt `FALSE` trước `TRUE`, nên `priority IS NULL` đưa các hàng **không NULL** trước hàng NULL. Sau đó so priority.

Nhưng:

```sql
ORDER BY COALESCE(priority, 999)
```

thay NULL bằng giá trị thay thế **trong biểu thức sắp xếp**. Điều này có thể có hiệu ứng phụ:

- Nếu một ngày priority hợp lệ có giá trị 999, NULL và 999 trở thành **bằng nhau** ở khóa biểu thức.
- Kiểu dữ liệu và phép so sánh của biểu thức có thể khác cột gốc.
- Index trên cột `priority` không nhất thiết giúp `ORDER BY COALESCE(priority,999)` giống như index cho `ORDER BY priority`.
- Người đọc có thể nhầm giá trị ưu tiên được thay thực sự trong bảng.

Khi chỉ cần vị trí NULL, **`NULLS FIRST/LAST` thường rõ hơn**. Dùng `COALESCE` khi thay thế NULL bằng một giá trị cụ thể là chủ đích của nghiệp vụ, chẳng hạn “điểm chưa chấm được xử lý như 0 trong bảng xếp hạng”, và phải ghi rõ.

## 7. ORDER BY với biểu thức tính toán

PostgreSQL cho phép ORDER BY theo biểu thức, không chỉ tên cột.

### 7.1. Theo độ dài chuỗi

```sql
SELECT ticket_id, team, length(team) AS team_name_length
FROM sort_lab.tickets
ORDER BY length(team) DESC, team ASC, ticket_id ASC;
```

Sắp tên team dài hơn trước; nếu cùng độ dài, theo tên; cuối cùng ID.

### 7.2. Theo kết quả CASE

Giả sử thứ tự nghiệp vụ về trạng thái là:

1. `OPEN` — cần xử lý.
2. `NEW` — mới tạo.
3. `RESOLVED` — đã hoàn tất.

Thứ tự chữ cái thường **không** thể hiện chính sách này. Dùng:

```sql
SELECT ticket_id, status, priority
FROM sort_lab.tickets
ORDER BY
    CASE status
        WHEN 'OPEN' THEN 1
        WHEN 'NEW' THEN 2
        WHEN 'RESOLVED' THEN 3
        ELSE 4
    END ASC,
    priority ASC NULLS LAST,
    ticket_id ASC;
```

Dấu `ELSE 4` giúp biểu thức có hành vi dự phòng nếu hệ thống thay đổi danh sách trạng thái. Trong schema lab có `CHECK` giới hạn ba trạng thái, nhưng SQL dùng trong ứng dụng có thể cần phòng cho dữ liệu từ những nguồn khác.

### 7.3. Theo phép tính số học

```sql
SELECT
    ticket_id,
    score,
    COALESCE(score, 0) * 1.2 AS weighted_score
FROM sort_lab.tickets
ORDER BY weighted_score DESC, ticket_id ASC;
```

Câu này dùng một công thức giả định. `weighted_score` là bí danh của kết quả tính toán; nó **không phải cột vật lý**, trừ khi schema định nghĩa cột riêng.

Nếu score NULL không nên được hiểu là 0, thay vì `COALESCE` nên sắp trực tiếp:

```sql
ORDER BY score DESC NULLS LAST, ticket_id ASC
```

### 7.4. Theo ngày từ TIMESTAMPTZ

Nếu cần nhóm/sắp theo **ngày ở Việt Nam**:

```sql
SELECT
    ticket_id,
    created_at,
    (created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS created_day_vn
FROM sort_lab.tickets
ORDER BY created_day_vn DESC, created_at DESC, ticket_id DESC;
```

`TIMESTAMPTZ` là một mốc thời gian; hiển thị và việc ép thành ngày có thể phụ thuộc múi giờ. Dùng `AT TIME ZONE` rõ ràng khi “ngày” có nghĩa theo một vùng địa lý cụ thể.

Lưu ý: nếu chỉ `ORDER BY created_day_vn DESC`, các phiếu trong **cùng ngày** có thể đổi vị trí không xác định; thêm `created_at` và `ticket_id` để phá hòa.

## 8. Bí danh SELECT, số thứ tự cột và tên cột trong ORDER BY

### 8.1. Dùng alias

```sql
SELECT
    ticket_id,
    COALESCE(score, 0) AS effective_score
FROM sort_lab.tickets
ORDER BY effective_score DESC, ticket_id ASC;
```

Trong `ORDER BY`, PostgreSQL cho phép tham chiếu một tên cột kết quả như `effective_score`.

Điều này giúp không cần lặp biểu thức dài. Nhưng cần lưu ý ngữ nghĩa: **một alias đầu ra dùng làm khóa đơn giản** được hiểu là output column; nếu muốn biểu thức phức tạp dựa trên alias, đôi khi cần lặp biểu thức hoặc bọc truy vấn trong subquery.

Ví dụ rõ ràng với subquery:

```sql
SELECT ticket_id, effective_score
FROM (
    SELECT
        ticket_id,
        COALESCE(score, 0) AS effective_score
    FROM sort_lab.tickets
) AS t
ORDER BY effective_score * 2 DESC, ticket_id ASC;
```

### 8.2. Dùng vị trí cột kết quả

PostgreSQL cho phép:

```sql
SELECT
    team,
    priority,
    ticket_id
FROM sort_lab.tickets
ORDER BY 1 ASC, 2 ASC NULLS LAST, 3 ASC;
```

Ở đây:

- `1` là cột kết quả thứ nhất (`team`).
- `2` là cột thứ hai (`priority`).
- `3` là cột thứ ba (`ticket_id`).

Nhưng nếu người khác đổi thứ tự cột trong `SELECT`, câu SQL sẽ đổi ngữ nghĩa sort mà có thể không báo lỗi. Vì vậy với code ứng dụng và tài liệu, **nên ưu tiên tên hoặc biểu thức rõ ràng**.

### 8.3. Cẩn thận với tên trùng bí danh

```sql
SELECT score AS priority
FROM sort_lab.tickets
ORDER BY priority DESC;
```

Khi dùng `priority` là một **output column name đứng riêng** trong `ORDER BY`, PostgreSQL có quy tắc phân giải tên ưu tiên output column khi có xung đột. Nó có thể sắp theo alias của `score`, không theo cột đầu vào `priority` như người đọc tưởng.

Để tránh nhập nhằng, dùng qualifier hoặc alias khác:

```sql
SELECT t.score AS reported_score, t.priority
FROM sort_lab.tickets AS t
ORDER BY t.priority ASC NULLS LAST, t.ticket_id;
```

Trong ví dụ nếu `ticket_id` không được chọn, PostgreSQL vẫn có thể dùng cột nguồn trong ORDER BY cho `SELECT` thông thường; với `SELECT DISTINCT` có những hạn chế khác sẽ nói ở phần sau.

## 9. Sắp xếp chuỗi: collation, chữ hoa/thường và dấu tiếng Việt

### 9.1. Thứ tự chuỗi phụ thuộc quy tắc so sánh

Các giá trị:

```text
An
Bình
Chi
Ánh
anh
```

không phải lúc nào có cùng thứ tự ở mọi database. PostgreSQL dựa vào **collation** của biểu thức và cấu hình locale/ICU/libc phù hợp.

```sql
SELECT ticket_id, assigned_to
FROM sort_lab.tickets
ORDER BY assigned_to ASC NULLS LAST, ticket_id ASC;
```

Truy vấn có thứ tự xác định theo collation của cột, nhưng **vị trí tương đối của những chuỗi khác nhau có thể đổi khi dùng collation khác**.

### 9.2. Chọn collation tường minh

Collation `"C"` là lựa chọn phổ biến có sẵn:

```sql
SELECT ticket_id, assigned_to
FROM sort_lab.tickets
ORDER BY assigned_to COLLATE "C" ASC NULLS LAST, ticket_id ASC;
```

`"C"` dùng quy tắc so sánh mang tính byte/đơn giản, thích hợp trong một số bài kiểm tra kỹ thuật, **không phải mặc định là thứ tự chữ cái tự nhiên đối với tiếng Việt**.

Với sản phẩm hướng người dùng, cần xác định collation phù hợp ngôn ngữ, locale và phiên bản PostgreSQL. Collation ICU có thể được tạo/quản lý nếu hạ tầng hỗ trợ; đừng tự đặt tên một collation tiếng Việt chưa tồn tại trong database.

### 9.3. Sắp không phân biệt hoa/thường

```sql
SELECT ticket_id, assigned_to
FROM sort_lab.tickets
ORDER BY lower(assigned_to) ASC NULLS LAST, ticket_id ASC;
```

Ở đây `lower(assigned_to)` biến tên thành dạng chữ thường trước khi so sánh theo collation phù hợp. Điều này giúp giảm một số khác biệt hoa/thường, nhưng không giải quyết **mọi** quy tắc tiếng Việt, Unicode normalization hoặc tương đương dấu.

Thêm `ticket_id` vì nhiều tên sau `lower()` có thể tạo ra cùng khóa sort.

### 9.4. Sắp số lưu dưới dạng TEXT

Nếu cột chứa chuỗi:

```text
'2', '10', '100'
```

sắp theo text/collation có thể cho kết quả khác **sắp số học**. Không thể dùng `ORDER BY text_col` rồi mặc định được 2, 10, 100 theo giá trị số.

Nếu dữ liệu thực sự là số, **lưu dưới kiểu số** như `INTEGER` hoặc `NUMERIC`. Nếu buộc phải chuyển khi đọc, cần đảm bảo các chuỗi hợp lệ:

```sql
-- Chỉ dùng nếu mọi giá trị code_text có thể ép thành integer.
SELECT code_text
FROM some_table
ORDER BY code_text::integer ASC;
```

Trên dữ liệu không sạch, cast sai sẽ gây lỗi. Đó là vấn đề kiểu dữ liệu, không thể giải quyết đơn thuần bằng `NULLS LAST`.

### 9.5. Collation có thể tạo những khóa bằng nhau

Một số cách so sánh/collation có thể xem các chuỗi khác nhau là tương đương ở mức sort. Khi cần thứ tự ổn định, thêm ID duy nhất:

```sql
ORDER BY lower(assigned_to) ASC NULLS LAST, ticket_id ASC
```

Tính duy nhất của `ticket_id` giúp phá hòa ngay cả khi collation/cách chuẩn hóa làm nhiều tên có cùng khóa.

## 10. Tie-breaker: cách tạo thứ tự xác định hoàn toàn

### 10.1. Vấn đề khi nhiều hàng có cùng khóa

Câu:

```sql
SELECT ticket_id, score
FROM sort_lab.tickets
ORDER BY score DESC NULLS LAST;
```

đảm bảo điểm cao trước, NULL ở cuối. Nhưng cả `104` và `111` đều có `score=95`, nhiều phiếu có `score=80`. **Thứ tự của các hàng đồng điểm không được SQL bảo đảm**.

Hai lần chạy có thể tình cờ cùng kết quả, nhưng thay index, phiên bản PostgreSQL, kế hoạch thực thi, parallelism hoặc dữ liệu vẫn có thể làm thứ tự đồng điểm khác nhau.

### 10.2. Thêm khóa duy nhất

```sql
SELECT ticket_id, score
FROM sort_lab.tickets
ORDER BY score DESC NULLS LAST, ticket_id ASC;
```

Vì `ticket_id` là `PRIMARY KEY`, không có hai hàng cùng ID. Tổ hợp hai khóa tạo thứ tự xác định hoàn toàn cho tập hàng.

Nếu muốn “phiếu mới trước” khi bằng điểm:

```sql
ORDER BY
    score DESC NULLS LAST,
    created_at DESC,
    ticket_id DESC;
```

Ở đây `created_at` có thể trùng, nhưng `ticket_id` giải quyết trường hợp cuối cùng.

### 10.3. Không bắt buộc tie-breaker là PK đơn cột

Một bảng có PK ghép `(tenant_id, sku)` có thể dùng:

```sql
ORDER BY
    price DESC,
    tenant_id ASC,
    sku ASC;
```

miễn tổ hợp các khóa cuối cùng giúp phân định duy nhất hàng trong tập dữ liệu liên quan.

Một **timestamp** hoặc một cột `status` không mặc định là duy nhất. Nếu hệ thống cho phép hai sự kiện cùng mili giây, `ORDER BY created_at DESC` vẫn có tie.

### 10.4. Khi nào tie-breaker đặc biệt cần thiết?

- Phân trang `LIMIT`/`OFFSET`.
- Keyset/cursor pagination.
- Xuất báo cáo cần tái lập kết quả.
- Chọn “phiếu mới nhất của mỗi nhóm” bằng `DISTINCT ON`.
- Xếp hạng có yêu cầu thứ tự row cụ thể.
- Test tự động so sánh danh sách nhiều lần.
- API cho phép sort nhiều cột.

## 11. ORDER BY cùng LIMIT và OFFSET

### 11.1. Phân trang cơ bản

```sql
SELECT
    ticket_id, team, priority, created_at
FROM sort_lab.tickets
ORDER BY created_at DESC, ticket_id DESC
LIMIT 5 OFFSET 0;
```

Trang 1 lấy tối đa năm phiếu mới nhất.

```sql
SELECT
    ticket_id, team, priority, created_at
FROM sort_lab.tickets
ORDER BY created_at DESC, ticket_id DESC
LIMIT 5 OFFSET 5;
```

Trang 2 bỏ qua năm phiếu đầu theo **cùng một thứ tự**.

Thường quy đổi:

```text
OFFSET = (page_number - 1) × page_size
```

với `page_number` bắt đầu từ 1.

### 11.2. Nếu bỏ ORDER BY sẽ ra sao?

```sql
SELECT *
FROM sort_lab.tickets
LIMIT 5 OFFSET 5;
```

Không có nghĩa “hàng thứ 6 đến 10 theo lúc chèn”. PostgreSQL có quyền trả một tập con theo kế hoạch hiện tại và thay đổi thứ tự ở lần khác. **Mọi phân trang có ý nghĩa phải chỉ rõ ORDER BY.**

### 11.3. Nếu ORDER BY còn tie thì sao?

```sql
ORDER BY created_at DESC
LIMIT 5 OFFSET 5
```

Hai hàng có cùng `created_at` ở ranh giới trang có thể đổi thứ tự tương đối. Kết quả trang 1 và trang 2 không ổn định ngay cả khi dữ liệu chưa đổi, vì thứ tự không xác định giữa các tie.

Nên thêm:

```sql
ORDER BY created_at DESC, ticket_id DESC
```

### 11.4. Tie-breaker không giải quyết mọi vấn đề cập nhật đồng thời

Giả sử người dùng xem trang 1 lúc `t1`, rồi có phiếu mới được chèn trước khi họ xem trang 2 ở `t2`. Với `OFFSET`, vị trí các dòng có thể bị đẩy xuống; một số dòng có thể **lặp lại hoặc bị bỏ qua** giữa các lần yêu cầu.

Tie-breaker giải quyết **thứ tự của dữ liệu tại một snapshot**, nhưng không tự giữ snapshot giữa hai HTTP requests. Nếu cần phân trang nhất quán khi dữ liệu thay đổi, xem xét keyset pagination, snapshot/transaction semantics và yêu cầu sản phẩm.

### 11.5. OFFSET lớn có thể tốn kém

```sql
LIMIT 50 OFFSET 500000
```

có thể khiến PostgreSQL phải duyệt/bỏ qua rất nhiều hàng trước khi trả 50 hàng cần thiết, dù có index hỗ trợ. Đối với danh sách rất dài, **keyset/cursor pagination** thường đáng cân nhắc hơn.

## 12. Keyset pagination: tiếp tục sau khóa của hàng cuối

### 12.1. Trường hợp thuận lợi: hai khóa DESC, không NULL

Giả sử API sắp:

```sql
ORDER BY created_at DESC, ticket_id DESC
```

và trả 5 hàng/trang.

Trang đầu:

```sql
SELECT
    ticket_id, created_at, status
FROM sort_lab.tickets
ORDER BY created_at DESC, ticket_id DESC
LIMIT 5;
```

Client ghi lại khóa `(created_at, ticket_id)` của **hàng cuối cùng** trong trang vừa nhận.

Trang tiếp theo yêu cầu những hàng có bộ khóa **nhỏ hơn** theo cùng thứ tự từ điển:

```sql
SELECT
    ticket_id, created_at, status
FROM sort_lab.tickets
WHERE (created_at, ticket_id)
    < (TIMESTAMPTZ '2026-02-03 11:00:00+07', 108)
ORDER BY created_at DESC, ticket_id DESC
LIMIT 5;
```

Cặp cursor trong ví dụ là **giá trị minh họa**. Trong ứng dụng, phải dùng **giá trị hàng cuối thực tế** thay vì hardcode.

Vì cả hai cột không NULL và đều DESC, phép so sánh tuple `<` khớp ý tưởng “đi tiếp về phía các giá trị cũ hơn/nhỏ hơn”. Thêm ID độc nhất giải quyết tie cùng timestamp.

### 12.2. SQL row comparison có quy tắc NULL riêng

```sql
(created_at, ticket_id) < (:cursor_created_at, :cursor_id)
```

hoạt động thuận lợi khi cả hai trường không NULL và cùng hướng. Nếu khóa có `NULL`, SQL row comparison có thể trả **UNKNOWN**, không tương đương tự động với `NULLS LAST` trong ORDER BY.

Nếu sắp theo nhiều chiều hỗn hợp hoặc dùng `NULLS FIRST/LAST`, không thể chỉ đổi hết thành một phép tuple `<`/`>` rồi tin kết quả đúng.

### 12.3. Keyset với priority ASC NULLS LAST

Giả sử thứ tự:

```sql
ORDER BY
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id DESC
```

Ta cần hai tình huống.

**Trường hợp A — cursor cuối có `priority` không NULL**, với tham số `:last_priority`, `:last_created_at`, `:last_id`:

```sql
SELECT ticket_id, priority, created_at
FROM sort_lab.tickets
WHERE
    priority > :last_priority
    OR (
        priority = :last_priority
        AND (created_at, ticket_id)
            < (:last_created_at, :last_id)
    )
    OR priority IS NULL
ORDER BY
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id DESC
LIMIT 5;
```

Giải thích:

- Bắt đầu bằng các mức priority **lớn hơn** (vì đang ASC).
- Nếu priority bằng, chỉ lấy hàng có timestamp/ID **cũ hơn** theo hai khóa DESC.
- Những hàng priority NULL luôn **đứng sau** mọi priority không NULL, nên thuộc phần còn lại.

**Trường hợp B — cursor cuối có `priority IS NULL`:**

```sql
SELECT ticket_id, priority, created_at
FROM sort_lab.tickets
WHERE priority IS NULL
  AND (created_at, ticket_id)
      < (:last_created_at, :last_id)
ORDER BY
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id DESC
LIMIT 5;
```

Khi đã đi vào nhóm NULL cuối cùng, chỉ tiếp tục trong nhóm NULL.

Các ví dụ này giả định `created_at` và `ticket_id` **không NULL**, đúng với schema lab; nếu chính các khóa phá hòa cũng nullable, phải mở rộng logic.

Để dùng trong ứng dụng thật, cần parameter binding qua driver/API, không ghép các tham số thành SQL bằng chuỗi từ input người dùng.

### 12.4. Keyset không phải snapshot lịch sử tuyệt đối

Nếu sau trang trước một hàng đổi `priority` hoặc `created_at`, nó có thể di chuyển qua vị trí cursor. Keyset giảm chi phí/hiện tượng dịch trang so với OFFSET trong nhiều trường hợp, nhưng **không tạo ra snapshot bất biến qua nhiều request**. Hãy cân nhắc chính sách dữ liệu thay đổi và tính nhất quán yêu cầu của API.

## 13. Sắp xếp khi dùng DISTINCT

### 13.1. SELECT DISTINCT và ORDER BY

Truy vấn:

```sql
SELECT DISTINCT status
FROM sort_lab.tickets
ORDER BY status ASC;
```

hợp lệ: `status` được chọn ra và dùng làm khóa sort.

Trong PostgreSQL, với `SELECT DISTINCT`, biểu thức `ORDER BY` phải thỏa yêu cầu liên quan đến **danh sách kết quả được chọn**; không tùy ý sắp distinct status theo một cột không có trong output mà mỗi status lại có nhiều giá trị.

Ví dụ ý định:

```sql
-- Không phải cách hợp lệ để chọn duy nhất status
-- rồi tùy ý sắp theo từng created_at của các dòng nguồn:
SELECT DISTINCT status
FROM sort_lab.tickets
ORDER BY created_at DESC;
```

Vì một status có nhiều `created_at`, cần xác định **quy tắc tổng hợp**: lấy ngày mới nhất, ngày cũ nhất hay thứ tự nghiệp vụ?

Cách rõ ràng:

```sql
SELECT
    status,
    MAX(created_at) AS last_created_at
FROM sort_lab.tickets
GROUP BY status
ORDER BY last_created_at DESC, status ASC;
```

### 13.2. DISTINCT ON là tính năng PostgreSQL

Nếu muốn **một phiếu mới nhất cho mỗi team**, dùng `DISTINCT ON`:

```sql
SELECT DISTINCT ON (team)
    team,
    ticket_id,
    created_at,
    status
FROM sort_lab.tickets
ORDER BY
    team ASC,
    created_at DESC,
    ticket_id DESC;
```

`DISTINCT ON (team)` giữ **hàng đầu tiên** của từng nhóm team theo thứ tự `ORDER BY`.

Quy tắc PostgreSQL: các biểu thức trong `DISTINCT ON` phải **khớp với các biểu thức ORDER BY ở phần đầu** theo yêu cầu của cú pháp; sau đó mới dùng khóa khác để chọn hàng muốn giữ.

Nếu chỉ:

```sql
SELECT DISTINCT ON (team) ...
FROM sort_lab.tickets;
```

mà thiếu thứ tự chọn trong nhóm, “hàng đầu tiên” không có quy tắc mong muốn ổn định.

### 13.3. Chọn mới nhất mỗi nhóm rồi sắp toàn kết quả theo thời gian

Một vấn đề tinh tế: truy vấn `DISTINCT ON (team)` ở trên có `ORDER BY team` để đáp ứng việc chọn từng nhóm, nên **toàn kết quả** được sắp theo team, không phải ngày mới nhất toàn cục.

Để chọn trước rồi sắp ngoài:

```sql
SELECT
    team, ticket_id, created_at, status
FROM (
    SELECT DISTINCT ON (team)
        team, ticket_id, created_at, status
    FROM sort_lab.tickets
    ORDER BY team, created_at DESC, ticket_id DESC
) AS latest_per_team
ORDER BY created_at DESC, ticket_id DESC;
```

**Hai `ORDER BY` có hai nhiệm vụ khác nhau**:

- ORDER BY bên trong quyết định **hàng được giữ cho từng team**.
- ORDER BY ngoài quyết định **thứ tự danh sách cuối**.

Đây là ví dụ quan trọng cho sự khác biệt giữa **thứ tự phục vụ phép tính trung gian** và **thứ tự hiển thị cuối cùng**.

## 14. ORDER BY trong window functions khác ORDER BY kết quả ngoài

### 14.1. ROW_NUMBER theo từng team

```sql
SELECT
    ticket_id,
    team,
    priority,
    created_at,
    ROW_NUMBER() OVER (
        PARTITION BY team
        ORDER BY
            priority ASC NULLS LAST,
            created_at DESC,
            ticket_id ASC
    ) AS row_in_team
FROM sort_lab.tickets
ORDER BY team ASC, row_in_team ASC;
```

Trong `OVER (...)`:

- `PARTITION BY team` chia các nhóm team cho phép tính window.
- `ORDER BY priority, created_at, ticket_id` quyết định **thứ tự đánh số trong từng nhóm**.
- `ROW_NUMBER()` tạo số thứ tự 1, 2, 3... theo các khóa window.

Còn `ORDER BY team, row_in_team` ở cuối mới quyết định **cách kết quả được trả ra cho client**.

### 14.2. Thiếu ORDER BY ngoài

```sql
SELECT
    ticket_id,
    ROW_NUMBER() OVER (ORDER BY created_at DESC, ticket_id DESC) AS rn
FROM sort_lab.tickets;
```

Window `ORDER BY` định nghĩa cách tính `rn`, nhưng không nên coi nó là **bảo đảm về thứ tự hàng được hiển thị cuối** nếu không có `ORDER BY` ngoài.

Muốn chắc chắn:

```sql
SELECT
    ticket_id,
    ROW_NUMBER() OVER (ORDER BY created_at DESC, ticket_id DESC) AS rn
FROM sort_lab.tickets
ORDER BY rn;
```

### 14.3. RANK, DENSE_RANK và tie

Nếu dùng:

```sql
RANK() OVER (ORDER BY score DESC NULLS LAST)
```

những phiếu cùng `score` được coi là cùng **peer group** và có thể nhận cùng rank. Nếu thêm `ticket_id` vào chính `ORDER BY` của window rank, các peer có thể bị phân tách khiến rank khác nhau.

Vì thế cần phân biệt:

- **Xếp hạng điểm:** giữ tie theo score trong window.
- **Thứ tự hiển thị ổn định:** thêm `ticket_id` vào ORDER BY **ngoài**.

Ví dụ:

```sql
SELECT
    ticket_id,
    score,
    RANK() OVER (
        ORDER BY score DESC NULLS LAST
    ) AS score_rank
FROM sort_lab.tickets
ORDER BY
    score DESC NULLS LAST,
    ticket_id ASC;
```

Những phiếu cùng score vẫn nhận cùng rank, nhưng thứ tự giữa chúng trong kết quả đã được định rõ.

## 15. ORDER BY bên trong aggregate

### 15.1. array_agg theo thứ tự mong muốn

PostgreSQL cho phép:

```sql
SELECT
    team,
    array_agg(
        ticket_id
        ORDER BY created_at DESC, ticket_id DESC
    ) AS ticket_ids_newest_first
FROM sort_lab.tickets
GROUP BY team
ORDER BY team ASC;
```

`ORDER BY` **bên trong `array_agg`** quy định thứ tự phần tử trong mảng của từng team.

`ORDER BY team` **bên ngoài** quy định thứ tự các dòng team.

Hai loại thứ tự độc lập. Nếu bỏ `ORDER BY` bên trong aggregate, không nên trông chờ các phần tử của `array_agg` theo thứ tự lúc chèn hoặc theo thứ tự index.

### 15.2. json_agg hoặc string_agg

Ví dụ:

```sql
SELECT
    team,
    string_agg(
        ticket_id::text,
        ', ' ORDER BY created_at DESC, ticket_id DESC
    ) AS ticket_id_list
FROM sort_lab.tickets
GROUP BY team
ORDER BY team;
```

Với `string_agg`, thứ tự các phần tử **có ý nghĩa**: chuỗi kết quả khác nhau nếu input đi theo thứ tự khác.

### 15.3. Không nhầm với GROUP BY

```sql
GROUP BY team
```

gom hàng theo team để aggregate; bản thân nó **không cam kết thứ tự của các nhóm trả ra**.

Nếu muốn nhóm theo chữ cái:

```sql
GROUP BY team
ORDER BY team ASC
```

Nếu muốn nhóm có nhiều phiếu nhất trước:

```sql
SELECT team, COUNT(*) AS ticket_count
FROM sort_lab.tickets
GROUP BY team
ORDER BY ticket_count DESC, team ASC;
```

`team ASC` là tie-breaker khi hai team có cùng `ticket_count`.

## 16. ORDER BY trong subquery, CTE và view

### 16.1. ORDER BY trong subquery không thay thế ORDER BY ngoài

```sql
SELECT *
FROM (
    SELECT ticket_id, created_at
    FROM sort_lab.tickets
    ORDER BY created_at DESC
) AS ordered_input;
```

Đừng dựa vào thứ tự của subquery để cam kết kết quả ngoài ở mọi trường hợp. Các phép xử lý ở mức ngoài như JOIN, aggregation hay parallel execution có thể ảnh hưởng thứ tự hàng cuối cùng.

Nếu client cần thứ tự:

```sql
SELECT *
FROM (
    SELECT ticket_id, created_at
    FROM sort_lab.tickets
) AS t
ORDER BY created_at DESC, ticket_id DESC;
```

### 16.2. Subquery ORDER BY LIMIT có vai trò chọn tập con

```sql
SELECT *
FROM (
    SELECT ticket_id, created_at, team
    FROM sort_lab.tickets
    ORDER BY created_at DESC, ticket_id DESC
    LIMIT 5
) AS latest_five
ORDER BY team ASC, ticket_id ASC;
```

Ở đây:

- **ORDER BY trong** cùng `LIMIT 5` xác định **năm phiếu mới nhất**.
- **ORDER BY ngoài** sắp **năm phiếu đó theo team** để hiển thị.

Hai bước có mục tiêu khác nhau. Không thể bỏ ORDER BY trong mà vẫn đảm bảo đã chọn đúng năm phiếu mới nhất.

### 16.3. View không tự biến thứ tự thành contract

Nếu một view được định nghĩa từ truy vấn có sắp xếp, ứng dụng vẫn nên khai báo `ORDER BY` ở **truy vấn dùng view** khi thứ tự kết quả là một phần của API.

Ví dụ:

```sql
SELECT ticket_id, created_at
FROM some_view
ORDER BY created_at DESC, ticket_id DESC;
```

Không dùng thứ tự tình cờ trong view làm cơ sở kiểm thử giao diện.

### 16.4. UNION và ORDER BY

Sau `UNION`, `INTERSECT`, `EXCEPT`, PostgreSQL áp dụng những giới hạn đối với biểu thức trong `ORDER BY` của kết quả tổng hợp. Thông thường dùng **tên hoặc vị trí output column**:

```sql
SELECT ticket_id, team
FROM sort_lab.tickets
WHERE team = 'Support'

UNION ALL

SELECT ticket_id, team
FROM sort_lab.tickets
WHERE team = 'Billing'

ORDER BY team, ticket_id;
```

Nếu muốn sắp bằng biểu thức phức tạp trên kết quả set operation, có thể bọc trong subquery:

```sql
SELECT *
FROM (
    SELECT ticket_id, team
    FROM sort_lab.tickets
    WHERE team = 'Support'

    UNION ALL

    SELECT ticket_id, team
    FROM sort_lab.tickets
    WHERE team = 'Billing'
) AS combined
ORDER BY lower(team), ticket_id;
```

Cách này làm rõ tầng xử lý và tránh giả định mọi biểu thức sắp xếp luôn được cho phép trực tiếp sau set operation.

## 17. ORDER BY liên quan thế nào tới B-tree index?

### 17.1. PostgreSQL có hai cách phổ biến để trả dữ liệu theo thứ tự

Với câu:

```sql
SELECT ticket_id, priority, created_at
FROM sort_lab.tickets
WHERE team = 'Support'
ORDER BY priority ASC NULLS LAST, created_at DESC, ticket_id ASC
LIMIT 10;
```

PostgreSQL có thể:

1. Đọc những dòng phù hợp rồi chạy một **Sort** (có thể dùng biến thể tối ưu cho LIMIT).
2. Đọc theo **thứ tự index B-tree thích hợp**, có thể tránh bước Sort riêng.

Lựa chọn của planner phụ thuộc index, bộ lọc, dữ liệu, thống kê, chi phí heap access, LIMIT và tài nguyên. **Có index không có nghĩa PostgreSQL bắt buộc sử dụng index.**

### 17.2. Tạo composite index khớp truy vấn

Trên **lab**, có thể thử:

```sql
CREATE INDEX ix_tickets_team_priority_created_id
ON sort_lab.tickets (
    team ASC,
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id ASC
);
```

Với filter `team = 'Support'`, thứ tự còn lại trong index có thể phù hợp:

```text
priority ASC NULLS LAST
created_at DESC
ticket_id ASC
```

Nên query ở đầu phần này có cơ hội đọc theo thứ tự mong muốn.

Tại sao index bắt đầu bằng `team`? Vì truy vấn lọc `WHERE team = ...` và sau đó sắp theo các khóa còn lại. Nhưng nếu workload chủ yếu sắp **toàn bảng không lọc team**, index này chưa chắc là lựa chọn tốt nhất.

### 17.3. B-tree forward và backward scan

Một B-tree index có thể được quét theo hướng thuận hoặc ngược. Ví dụ index:

```sql
CREATE INDEX ix_tickets_created_id
ON sort_lab.tickets (created_at ASC, ticket_id ASC);
```

có thể hỗ trợ một số trường hợp:

```sql
ORDER BY created_at ASC, ticket_id ASC
```

và quét ngược cho:

```sql
ORDER BY created_at DESC, ticket_id DESC
```

Nhưng với **hướng hỗn hợp**:

```sql
ORDER BY created_at DESC, ticket_id ASC
```

một index cùng chiều cho cả hai cột không tự động đáp ứng hoàn hảo chỉ bằng quét ngược. Khi cần, tạo index có định nghĩa hướng hỗn hợp phù hợp sau khi đo tải.

Khi có `NULLS FIRST/LAST`, quét ngược cũng đảo cách đặt NULL theo thứ tự index. Vì vậy chiều và NULL placement trong định nghĩa index có ý nghĩa vật lý.

### 17.4. Index hỗ trợ sort nhưng vẫn có thể phải đọc heap

Một index trên các khóa sort có thể giảm công việc sắp xếp, nhưng query còn chọn `status`, `score`, `assigned_to`. Nếu chúng không nằm trong index theo cách truy vấn có thể sử dụng, PostgreSQL vẫn cần truy cập heap để lấy dữ liệu.

Index Only Scan cũng cần xét Visibility Map để đảm bảo MVCC, nên tên `Index Only Scan` không cam kết mọi truy vấn đều không đọc heap.

### 17.5. Sort theo biểu thức và expression index

Nếu workload thường:

```sql
ORDER BY lower(assigned_to) ASC NULLS LAST, ticket_id
```

thì một B-tree index chỉ trên `assigned_to` chưa chắc thỏa thứ tự của **biểu thức `lower(assigned_to)`**. Có thể cân nhắc expression index:

```sql
CREATE INDEX ix_tickets_assignee_normalized
ON sort_lab.tickets (
    lower(assigned_to) ASC NULLS LAST,
    ticket_id ASC
);
```

Chỉ thêm khi có nhu cầu đủ lớn. Index trên biểu thức làm tăng chi phí INSERT/UPDATE và cần đúng quy tắc collation/so sánh của câu truy vấn.

### 17.6. Index không thay thế ORDER BY trong code ứng dụng

Ngay cả khi planner thường dùng một index và kết quả **có vẻ** ổn định, SQL không có `ORDER BY` vẫn không cam kết thứ tự kết quả.

Viết yêu cầu thứ tự trong SQL:

```sql
SELECT ...
FROM ...
ORDER BY ...
```

rồi dùng index để **tối ưu cách đáp ứng yêu cầu đó**, không phải ngược lại.

## 18. EXPLAIN: đọc kế hoạch sắp xếp

### 18.1. EXPLAIN chỉ đưa kế hoạch dự kiến

```sql
EXPLAIN
SELECT ticket_id, team, priority, created_at
FROM sort_lab.tickets
WHERE team = 'Support'
ORDER BY priority ASC NULLS LAST, created_at DESC, ticket_id
LIMIT 5;
```

Bạn có thể gặp:

| Node | Vai trò |
|---|---|
| `Seq Scan` | Đọc tuần tự bảng |
| `Index Scan` | Dùng index để tìm/đọc dòng |
| `Index Only Scan` | Có thể đọc từ index khi điều kiện cho phép |
| `Sort` | Sắp tập hàng theo khóa được yêu cầu |
| `Incremental Sort` | Tận dụng input đã có thứ tự theo tiền tố một số khóa |
| `Limit` | Chỉ trả số hàng tối đa theo LIMIT |
| `Gather Merge` | Hợp nhất đầu ra từ worker theo thứ tự trong kế hoạch parallel phù hợp |

Trong node `Sort` thường có `Sort Key`:

```text
Sort Key: priority, created_at DESC, ticket_id
```

Phải so xem khóa sort có đúng **chiều, NULL placement và tie-breaker** được yêu cầu không.

### 18.2. EXPLAIN ANALYZE thực thi câu SQL

Trên database lab:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ticket_id, team, priority, created_at
FROM sort_lab.tickets
WHERE team = 'Support'
ORDER BY priority ASC NULLS LAST, created_at DESC, ticket_id
LIMIT 5;
```

`ANALYZE` khiến truy vấn **thực sự chạy** để thu thời gian và số dòng, khác `EXPLAIN` không có `ANALYZE`.

Đối với `SELECT` trên bộ dữ liệu 12 hàng, thực hành tương đối nhẹ. Trên production, một `SELECT` phải sort hàng triệu dòng vẫn có thể tốn CPU, I/O và ảnh hưởng hệ thống; không chạy tùy ý chỉ vì truy vấn là read-only.

### 18.3. Các chiến lược sort

Trong kế hoạch thực tế có thể thấy:

- `Sort Method: quicksort`: dữ liệu sort trong bộ nhớ theo một phương án phổ biến.
- `Sort Method: top-N heapsort`: tối ưu cho trường hợp chỉ cần một số hàng đầu với LIMIT thích hợp.
- `Sort Method: external merge`, kèm dữ liệu đĩa: sort lớn cần dùng file tạm.
- `Incremental Sort`: tận dụng input đã được sắp theo một **tiền tố khóa** rồi chỉ sort thêm trong nhóm.

Tên method và việc xuất hiện trong plan không phải cam kết cố định; planner/executor có thể lựa chọn khác theo phiên bản, thống kê và truy vấn.

### 18.4. LIMIT không đảm bảo đọc ít dữ liệu

```sql
SELECT ticket_id, score
FROM sort_lab.tickets
ORDER BY score DESC NULLS LAST, ticket_id
LIMIT 10;
```

Chỉ trả tối đa 10 hàng, nhưng PostgreSQL có thể phải kiểm tra nhiều hàng để biết **10 hàng có score cao nhất** nếu không có đường truy cập hỗ trợ.

Câu `LIMIT 10` tự thân **không** có nghĩa “chỉ đọc đúng 10 hàng”.

### 18.5. work_mem và sort lớn

PostgreSQL sử dụng `work_mem` như một ngân sách cho các thao tác executor như sort/hash theo các quy tắc riêng; không nên hiểu nó là “RAM tổng cho cả PostgreSQL”.

Nếu sort lớn hơn ngân sách hoặc cách thực thi đòi file tạm, PostgreSQL có thể spill xuống đĩa. Nhưng tăng `work_mem` toàn server không nhất thiết an toàn, vì **một truy vấn có thể có nhiều node** và nhiều truy vấn chạy đồng thời.

Muốn điều tra:

1. Xem `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường phù hợp.
2. Kiểm tra sort method, memory/temp data.
3. Xem có index/filter nào giúp tránh sort không.
4. Nếu cần thử `work_mem`, dùng phạm vi hẹp trong lab/session thay vì thay toàn server.
5. Đo đồng thời, CPU, memory và I/O trước khi triển khai.

Ví dụ chỉ trên lab:

```sql
BEGIN;

SET LOCAL work_mem = '16MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT ticket_id, created_at
FROM sort_lab.tickets
ORDER BY created_at DESC, ticket_id DESC;

ROLLBACK;
```

Câu này minh họa `SET LOCAL` trong transaction. Nó không chứng minh `16MB` là cấu hình phù hợp cho production.

## 19. ORDER BY và dữ liệu NULL trong B-tree index

### 19.1. NULL placement được lưu trong định nghĩa index

Ví dụ:

```sql
CREATE INDEX ix_tickets_due_nulls_last
ON sort_lab.tickets (
    due_at ASC NULLS LAST,
    ticket_id ASC
);
```

Index có thể hỗ trợ:

```sql
SELECT ticket_id, due_at
FROM sort_lab.tickets
ORDER BY due_at ASC NULLS LAST, ticket_id ASC;
```

Bởi vì định nghĩa thứ tự index khớp khóa sắp xếp của truy vấn.

### 19.2. Đảo chiều không phải lúc nào khớp mong muốn

Nếu quét ngược index trên:

```text
due_at ASC NULLS LAST
```

thì chiều đối ứng là:

```text
due_at DESC NULLS FIRST
```

Nhưng ứng dụng có thể yêu cầu:

```sql
ORDER BY due_at DESC NULLS LAST
```

Đó là **quy tắc khác**. Cần xem liệu planner có đường truy cập phù hợp, phải sort thêm hay nên có index khác nếu workload xứng đáng.

### 19.3. NULLS FIRST/LAST trên cột thứ hai

Index:

```sql
CREATE INDEX ix_tickets_team_due
ON sort_lab.tickets (
    team ASC,
    due_at ASC NULLS LAST,
    ticket_id ASC
);
```

có thể phù hợp:

```sql
WHERE team = 'Support'
ORDER BY due_at ASC NULLS LAST, ticket_id ASC
```

nhưng không tương đương tự động với:

```sql
ORDER BY team ASC, due_at DESC NULLS LAST, ticket_id ASC
```

vì khóa thứ hai đã đổi chiều. Hãy xét thứ tự **từng cột** chứ không chỉ một chữ `DESC` trong câu SQL.

## 20. Khi nào ORDER BY có thể gây lỗi hoặc kết quả ngoài ý muốn?

### 20.1. Sắp theo tên cột không tồn tại

```sql
SELECT ticket_id
FROM sort_lab.tickets
ORDER BY no_such_column;
```

PostgreSQL báo lỗi vì tên cột không tồn tại trong phạm vi truy vấn.

### 20.2. Sắp theo loại dữ liệu không có toán tử so sánh phù hợp

Các kiểu dữ liệu PostgreSQL có những toán tử và operator classes khác nhau. Không phải mọi giá trị phức tạp đều sắp trực tiếp như `INTEGER` hay `TEXT`.

Với JSONB, nếu mục đích là sắp theo một trường JSON cụ thể, nên trích giá trị và ép đúng kiểu phù hợp, đồng thời xử lý missing/NULL.

Ví dụ hình thức khi có bảng JSONB `events(payload)`:

```sql
SELECT payload
FROM events
ORDER BY (payload ->> 'amount')::numeric DESC NULLS LAST;
```

Chỉ dùng nếu các giá trị `amount` không NULL đều ép được sang numeric. Nếu có chuỗi không phải số, câu cast có thể lỗi. Câu SQL này là ví dụ riêng, **không yêu cầu có bảng `events` trong lab**.

### 20.3. Sắp theo biểu thức nhưng quên phép chuyển kiểu

```sql
ORDER BY text_number
```

là sắp theo **text**, không phải giá trị số. Cần lưu đúng kiểu hoặc dùng cast có kiểm soát.

### 20.4. Không cố định thứ tự khi bằng khóa chính

```sql
ORDER BY status ASC
```

chỉ nhóm/sắp theo status; hàng cùng status không có thứ tự hoàn toàn xác định. Thêm ngày và ID nếu nghiệp vụ đòi ổn định.

### 20.5. Coi NULLS LAST là WHERE IS NOT NULL

```sql
ORDER BY due_at NULLS LAST
```

không loại những phiếu chưa có hạn. Nếu muốn loại:

```sql
WHERE due_at IS NOT NULL
ORDER BY due_at ASC;
```

Nếu muốn **giữ mọi phiếu nhưng NULL ở cuối**, dùng `NULLS LAST`.

### 20.6. Dùng ORDER BY random() cho API lớn

```sql
SELECT ticket_id
FROM sort_lab.tickets
ORDER BY random()
LIMIT 3;
```

Có thể dùng để lấy một tập mẫu ngẫu nhiên **nhỏ và không đòi tái lập**. Nhưng thường cần tính random/sort cho nhiều hàng, tốn tài nguyên trên bảng lớn. Nó cũng **không tạo thứ tự ổn định để phân trang**.

Nếu cần mẫu ngẫu nhiên có thể tái lập hoặc sampling quy mô lớn, cần thiết kế phương án riêng (ví dụ sampling theo khóa/hash/những cơ chế phù hợp), không dùng `ORDER BY random()` tùy tiện trên hàng triệu dòng.

### 20.7. Nhầm thứ tự giữa các transaction

Một kết quả `ORDER BY` có thứ tự xác định trên **các hàng được nhìn thấy bởi snapshot/truy vấn đó**. Khi transaction khác thêm/sửa/xóa hàng, lần đọc sau có thể có tập dữ liệu khác.

Tie-breaker giúp thứ tự của cùng tập dữ liệu không nhập nhằng; nó không khóa bảng và không làm dữ liệu bất biến.

## 21. Các tình huống thực tế: viết ORDER BY đúng nghiệp vụ

### 21.1. Danh sách công việc ưu tiên cao, hạn gần trước

Yêu cầu:

- Phiếu có priority `1` trước `2` trước `3`.
- Phiếu chưa được phân loại để **cuối**.
- Trong cùng priority, hạn gần nhất trước; chưa có hạn cuối nhóm.
- Nếu bằng hạn, phiếu mới tạo trước.
- Sau cùng dùng ID giảm dần.

```sql
SELECT
    ticket_id, priority, due_at, created_at
FROM sort_lab.tickets
WHERE status <> 'RESOLVED'
ORDER BY
    priority ASC NULLS LAST,
    due_at ASC NULLS LAST,
    created_at DESC,
    ticket_id DESC;
```

Điều kiện `WHERE` loại phiếu resolved **trước khi sắp kết quả**; không làm thay đổi nghĩa của NULL placement.

### 21.2. Danh sách khách hàng: người chưa được giao việc trước

Yêu cầu:

- Phiếu chưa có `assigned_to` lên đầu.
- Các phiếu đã có người phụ trách sắp theo tên người.
- Trong mỗi người, phiếu mới trước.

```sql
SELECT ticket_id, assigned_to, created_at
FROM sort_lab.tickets
ORDER BY
    assigned_to ASC NULLS FIRST,
    created_at DESC,
    ticket_id DESC;
```

Khi `assigned_to` NULL, các hàng thuộc nhóm đầu; thứ tự nội nhóm theo created_at và ticket_id.

### 21.3. Dashboard điểm: điểm cao trước, chưa chấm cuối

```sql
SELECT ticket_id, score, created_at
FROM sort_lab.tickets
ORDER BY
    score DESC NULLS LAST,
    created_at ASC,
    ticket_id ASC;
```

`created_at ASC` ở đây ưu tiên phiếu cũ hơn khi cùng điểm. Nếu sản phẩm yêu cầu phiếu mới trước, đổi thành `DESC`.

### 21.4. Quản trị đa tenant với mã chứng từ

Giả sử có bảng:

```text
invoices(tenant_id, issued_at, invoice_no, invoice_id)
```

Yêu cầu mỗi tenant xem hóa đơn mới trước, cùng ngày theo mã chứng từ tăng dần:

```sql
SELECT tenant_id, issued_at, invoice_no, invoice_id
FROM invoices
WHERE tenant_id = :tenant_id
ORDER BY issued_at DESC, invoice_no ASC, invoice_id ASC;
```

Đây là ví dụ cú pháp API, không phải bảng đã tạo trong lab. `invoice_id` đóng vai trò tie-breaker nếu mã có thể trùng trong một phạm vi ngày hoặc dữ liệu.

### 21.5. Danh sách theo lịch sử và trạng thái tùy biến

```sql
SELECT ticket_id, status, priority, created_at
FROM sort_lab.tickets
ORDER BY
    CASE status
        WHEN 'OPEN' THEN 1
        WHEN 'NEW' THEN 2
        WHEN 'RESOLVED' THEN 3
        ELSE 4
    END,
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id DESC;
```

Nếu API thường xuyên dùng kiểu sắp xếp này trên bảng lớn, có thể đo chi phí của expression sort và cân nhắc index expression/chiến lược thiết kế. Không thêm index trước khi có bằng chứng về workload.

## 22. Bảng ghi nhớ nhanh

| Mục đích | ORDER BY gợi ý | Lưu ý |
|---|---|---|
| Mã tăng dần | `ORDER BY id ASC` | Không có NULL nếu id là PK |
| Mới nhất trước | `ORDER BY created_at DESC, id DESC` | ID phá hòa nếu cùng timestamp |
| Điểm cao trước, chưa chấm cuối | `ORDER BY score DESC NULLS LAST, id` | `DESC` mặc định lại đặt NULL đầu |
| Hạn gần trước, chưa có hạn cuối | `ORDER BY due_at ASC NULLS LAST, id` | NULLS LAST tường minh |
| Chưa phân loại trước | `ORDER BY priority ASC NULLS FIRST, id` | NULL không phải priority 0 |
| Nhiều khóa trái sang phải | `ORDER BY team, priority, id` | Khóa sau chỉ dùng nếu khóa trước bằng |
| Trạng thái nghiệp vụ | `ORDER BY CASE ... END, id` | Không tin thứ tự chữ cái |
| Không phân biệt hoa/thường | `ORDER BY lower(name), id` | Vẫn phụ thuộc collation/Unicode |
| Giới hạn trang | `ORDER BY created_at DESC, id DESC LIMIT 20` | Thứ tự phải ổn định |
| Lấy mới nhất mỗi nhóm | `DISTINCT ON (team) ... ORDER BY team, created_at DESC, id DESC` | ORDER BY đầu phải phù hợp DISTINCT ON |
| Xếp hạng cùng điểm | `RANK() OVER (ORDER BY score DESC NULLS LAST)` | Thêm id vào ORDER BY ngoài nếu cần ổn định |
| Mảng theo thứ tự | `array_agg(id ORDER BY created_at DESC, id DESC)` | Sort bên trong aggregate |
| Theo tenant và SKU | `ORDER BY tenant_id ASC, sku ASC` | Có thể tận dụng index B-tree phù hợp |

## 23. Quy trình kiểm tra một ORDER BY trên dữ liệu thật

Một quy trình đơn giản:

~~~mermaid
flowchart TD
    A["Xác định thứ tự nghiệp vụ"] --> B["Liệt kê các khóa theo độ ưu tiên"]
    B --> C["Quyết định ASC/DESC cho từng khóa"]
    C --> D["Xác định vị trí NULL mỗi khóa"]
    D --> E["Thêm tie-breaker duy nhất"]
    E --> F["Kiểm thử các dòng có khóa bằng nhau/NULL"]
    F --> G{"Có LIMIT/OFFSET hay cursor?"}
    G -- "Có" --> H["Kiểm tra phân trang và cạnh tranh dữ liệu"]
    G -- "Không" --> I["Kiểm tra thứ tự kết quả"]
    H --> I
    I --> J["EXPLAIN và kiểm tra index khi bảng lớn"]
~~~

Các câu hỏi cần trả lời trước khi hoàn tất:

1. **Cột đầu tiên là tiêu chí quan trọng nhất chưa?**
2. `ASC` hoặc `DESC` có đúng nghĩa nghiệp vụ của cột chưa (priority 1 cao hay thấp)?
3. Nếu cột nullable, cần `NULLS FIRST` hay `NULLS LAST`?
4. Khi hai hàng có cùng khóa, tie-breaker cuối có phân định duy nhất không?
5. Có yêu cầu về chữ hoa/thường, dấu tiếng Việt hoặc collation không?
6. Có đang dùng `LIMIT/OFFSET` và đòi kết quả ổn định không?
7. Nếu cần cursor, các khóa nullable/hướng hỗn hợp đã được xử lý chưa?
8. Nếu sort nằm trong window/aggregate/subquery, kết quả cuối có `ORDER BY` riêng không?
9. Dữ liệu lớn có cần index hỗ trợ không? Có index nào đang tồn tại?
10. Thao tác sort có làm tiêu hao CPU, RAM, I/O hoặc file tạm không?

## 24. Bài tập thực hành

Các bài sau sử dụng `sort_lab.tickets`. Không cần lệnh ghi bổ sung.

### Bài 1 — Tăng dần cơ bản

Viết truy vấn trả `ticket_id`, `priority`, sắp priority tăng dần. Các phiếu priority NULL cần nằm cuối; ID tăng dần khi cùng priority.

### Bài 2 — DESC và NULL

Giải thích vì sao:

```sql
ORDER BY score DESC
```

trong PostgreSQL **không** đặt tất cả điểm chưa chấm ở cuối. Viết cách sửa để điểm cao nhất trước, NULL cuối, ID nhỏ trước khi bằng điểm.

### Bài 3 — Nhiều khóa sắp xếp

Sắp phiếu theo team tăng dần, trạng thái tăng dần, trong mỗi team/status thì phiếu mới hơn trước. Thêm một khóa để kết quả xác định hoàn toàn.

### Bài 4 — Ưu tiên nghiệp vụ và NULL

Dùng `priority` với quy tắc số 1 cao nhất, 3 thấp nhất, NULL là chưa phân loại. Viết truy vấn ưu tiên cao trước, NULL cuối, sau đó hạn gần trước, NULL cuối, cuối cùng ID tăng dần.

### Bài 5 — Tập con có thể kiểm chứng

Chỉ xét ticket ID 101, 103, 105 và 107. Với:

```sql
ORDER BY priority DESC NULLS LAST, ticket_id
```

thứ tự ticket ID là gì?

### Bài 6 — Thứ tự trạng thái tùy biến

Yêu cầu `OPEN` trước `NEW`, `RESOLVED` cuối; trong mỗi trạng thái, score cao trước, NULL cuối; trong cùng score, ID tăng dần. Dùng `CASE`.

### Bài 7 — Chữ hoa/thường

Sắp các phiếu theo tên người phụ trách không phân biệt hoa/thường, các phiếu chưa được giao ở cuối, ID tăng dần nếu tên bằng nhau.

### Bài 8 — LIMIT/OFFSET

Lấy năm phiếu mới nhất (trang 1), rồi năm phiếu tiếp theo (trang 2), với thứ tự ổn định ngay cả khi nhiều phiếu trùng timestamp.

### Bài 9 — Keyset DESC

Truy vấn dùng `ORDER BY created_at DESC, ticket_id DESC` trả trang đầu. Hãy viết điều kiện cursor để lấy trang kế tiếp sau cặp `(created_at, ticket_id)` của hàng cuối.

### Bài 10 — Keyset với NULL

Với:

```sql
ORDER BY priority ASC NULLS LAST,
         created_at DESC,
         ticket_id DESC
```

vì sao không thể dùng một phép tuple `<` duy nhất cho mọi cursor nếu `priority` có thể NULL? Nêu hướng giải cho cursor NULL và không NULL.

### Bài 11 — DISTINCT ON

Chọn phiếu mới nhất của từng team, với ID giảm dần khi trùng timestamp. Sau đó hiển thị **các phiếu được chọn** theo created_at mới nhất trên toàn kết quả.

### Bài 12 — Window function

Tính `ROW_NUMBER()` trong từng team, ưu tiên priority 1 trước, NULL cuối, mới nhất trước, ID giảm dần. Sắp kết quả cuối theo team và số thứ tự vừa tính.

### Bài 13 — Aggregate có thứ tự

Viết truy vấn trả từng team cùng mảng ID phiếu theo `created_at DESC, ticket_id DESC`; sắp các team theo tên.

### Bài 14 — Chỉ mục hỗ trợ

Viết định nghĩa B-tree index có thể hỗ trợ:

```sql
WHERE team = 'Support'
ORDER BY priority ASC NULLS LAST,
         created_at DESC,
         ticket_id ASC
LIMIT 20;
```

Giải thích vì sao planner vẫn có thể chọn Seq Scan trên bộ dữ liệu 12 hàng.

### Bài 15 — Mô tả EXPLAIN

Một `EXPLAIN ANALYZE` cho thấy `Sort Method: external merge`. Điều này gợi ý điều gì? Nêu ba hướng điều tra trước khi tăng `work_mem` toàn server.

### Bài 16 — ORDER BY ở nhiều tầng

Một query dùng `DISTINCT ON(team)` để lấy hàng mới nhất theo team, rồi muốn kết quả toàn bộ sắp theo score giảm dần NULL cuối. Cần mấy tầng ORDER BY và vì sao?

### Bài 17 — ORDER BY không phải xác thực dữ liệu

Người dùng muốn “đẩy ticket không có hạn ra cuối”. Khi nào chỉ dùng `NULLS LAST`, khi nào thêm `WHERE due_at IS NOT NULL`?

### Bài 18 — Thứ tự hiển thị và index

Một index trên `created_at DESC` đang tồn tại và câu `SELECT * FROM tickets` có vẻ luôn ra mới nhất trước. Có thể bỏ `ORDER BY created_at DESC` trong API không? Tại sao?

## 25. Gợi ý lời giải

### Bài 1

```sql
SELECT ticket_id, priority
FROM sort_lab.tickets
ORDER BY priority ASC NULLS LAST, ticket_id ASC;
```

### Bài 2

PostgreSQL mặc định `DESC NULLS FIRST`, do đó NULL lên đầu. Sửa:

```sql
SELECT ticket_id, score
FROM sort_lab.tickets
ORDER BY score DESC NULLS LAST, ticket_id ASC;
```

### Bài 3

```sql
SELECT ticket_id, team, status, created_at
FROM sort_lab.tickets
ORDER BY
    team ASC,
    status ASC,
    created_at DESC,
    ticket_id ASC;
```

Ở ví dụ này `status` là text nên thứ tự giữa các trạng thái là thứ tự collation, không phải thứ tự ưu tiên nghiệp vụ tùy biến.

### Bài 4

```sql
SELECT ticket_id, priority, due_at
FROM sort_lab.tickets
ORDER BY
    priority ASC NULLS LAST,
    due_at ASC NULLS LAST,
    ticket_id ASC;
```

Hai `NULLS LAST` có ý nghĩa khác nhau: một cho priority, một cho due_at trong nhóm cùng priority.

### Bài 5

Thứ tự:

```text
105, 103, 101, 107
```

Vì priority 3, 2, 1, NULL; `NULLS LAST` ghi đè mặc định NULLS FIRST của DESC.

### Bài 6

```sql
SELECT ticket_id, status, score
FROM sort_lab.tickets
ORDER BY
    CASE status
        WHEN 'OPEN' THEN 1
        WHEN 'NEW' THEN 2
        WHEN 'RESOLVED' THEN 3
        ELSE 4
    END ASC,
    score DESC NULLS LAST,
    ticket_id ASC;
```

### Bài 7

```sql
SELECT ticket_id, assigned_to
FROM sort_lab.tickets
ORDER BY lower(assigned_to) ASC NULLS LAST, ticket_id ASC;
```

`lower()` giải quyết một phần chuyện hoa/thường; collation vẫn ảnh hưởng quy tắc so sánh chuỗi.

### Bài 8

Trang 1:

```sql
SELECT ticket_id, created_at
FROM sort_lab.tickets
ORDER BY created_at DESC, ticket_id DESC
LIMIT 5 OFFSET 0;
```

Trang 2:

```sql
SELECT ticket_id, created_at
FROM sort_lab.tickets
ORDER BY created_at DESC, ticket_id DESC
LIMIT 5 OFFSET 5;
```

Thêm ID giúp phá hòa cùng timestamp. Nếu dữ liệu thay đổi giữa hai request, OFFSET vẫn có thể làm xuất hiện dòng lặp hoặc bỏ sót.

### Bài 9

Dùng hai khóa cùng DESC, đều không NULL:

```sql
SELECT ticket_id, created_at
FROM sort_lab.tickets
WHERE (created_at, ticket_id)
    < (:last_created_at, :last_id)
ORDER BY created_at DESC, ticket_id DESC
LIMIT 5;
```

Các placeholder phải được bind bằng driver, không ghép chuỗi SQL trực tiếp.

### Bài 10

SQL tuple comparison với NULL có thể trả `UNKNOWN`, không tự tái hiện logic `NULLS LAST`. Khi cursor priority không NULL, lấy priority lớn hơn, cùng priority với khóa thời gian/ID ở sau và toàn bộ priority NULL. Khi cursor priority NULL, chỉ lấy các hàng priority NULL đứng sau cursor theo hai khóa còn lại. Có thể viết hai nhánh SQL như phần 12.3.

### Bài 11

```sql
SELECT team, ticket_id, created_at, status
FROM (
    SELECT DISTINCT ON (team)
        team, ticket_id, created_at, status
    FROM sort_lab.tickets
    ORDER BY team, created_at DESC, ticket_id DESC
) AS latest
ORDER BY created_at DESC, ticket_id DESC;
```

ORDER BY trong chọn hàng mới nhất từng nhóm; ORDER BY ngoài điều khiển thứ tự toàn kết quả.

### Bài 12

```sql
SELECT
    ticket_id,
    team,
    priority,
    ROW_NUMBER() OVER (
        PARTITION BY team
        ORDER BY
            priority ASC NULLS LAST,
            created_at DESC,
            ticket_id DESC
    ) AS rn
FROM sort_lab.tickets
ORDER BY team ASC, rn ASC;
```

### Bài 13

```sql
SELECT
    team,
    array_agg(
        ticket_id
        ORDER BY created_at DESC, ticket_id DESC
    ) AS ticket_ids
FROM sort_lab.tickets
GROUP BY team
ORDER BY team ASC;
```

### Bài 14

```sql
CREATE INDEX ix_tickets_support_sort
ON sort_lab.tickets (
    team ASC,
    priority ASC NULLS LAST,
    created_at DESC,
    ticket_id ASC
);
```

Planner có thể chọn Seq Scan vì bảng rất nhỏ, chi phí đọc vài hàng thấp hơn đi qua index. Index không bắt buộc được dùng.

### Bài 15

`external merge` gợi ý sort cần dùng lưu trữ tạm trên đĩa thay vì xử lý toàn bộ trong bộ nhớ. Nên điều tra: số hàng/cột đưa vào sort, filter và LIMIT có thể đẩy sớm không, index nào hỗ trợ thứ tự, kích thước row và concurrency. Chỉ cân nhắc tăng `work_mem` sau khi đo memory/temp I/O phù hợp.

### Bài 16

Cần hai tầng:

1. `DISTINCT ON(team)` cùng `ORDER BY team, created_at DESC, ticket_id DESC` để chọn phiếu mới nhất trong nhóm.
2. Truy vấn ngoài `ORDER BY score DESC NULLS LAST, ticket_id ASC` để hiển thị các phiếu đã chọn.

### Bài 17

Dùng `ORDER BY due_at ASC NULLS LAST` khi vẫn muốn **giữ cả phiếu chưa có hạn** nhưng để cuối. Dùng `WHERE due_at IS NOT NULL` khi yêu cầu thực sự là **chỉ hiển thị phiếu đã có hạn**.

### Bài 18

Không. Index có thể ảnh hưởng kế hoạch đọc nhưng không cam kết thứ tự kết quả của SQL nếu không có `ORDER BY`. Planner có thể chọn scan khác, dùng parallelism hoặc thay đổi kế hoạch khi dữ liệu lớn lên. API phải khai báo thứ tự tường minh.

## 26. Kết luận

`ORDER BY` là **hợp đồng thứ tự của kết quả truy vấn**, không phải thứ tự vật lý cố định của bảng. Khi có nhiều khóa, PostgreSQL so sánh **từ trái sang phải**; mỗi khóa có chiều `ASC`/`DESC` và vị trí NULL riêng.

Những điểm cần nhớ:

- **Không có `ORDER BY` thì không có bảo đảm về thứ tự.**
- PostgreSQL mặc định **`ASC NULLS LAST`** và **`DESC NULLS FIRST`**.
- Viết `NULLS FIRST/LAST` rõ ràng khi nghiệp vụ yêu cầu, đặc biệt với `DESC`.
- Dùng **khóa phá hòa duy nhất** để có thứ tự ổn định, nhất là trước `LIMIT`, `OFFSET` hoặc cursor pagination.
- `DISTINCT ON`, window functions và aggregates có thể có ORDER BY **phục vụ tính toán riêng**; thứ tự trả về cuối cùng vẫn cần xem ở tầng ngoài.
- B-tree index có thể giúp PostgreSQL trả hàng theo thứ tự mà không sort riêng, nhưng **thứ tự cột, chiều, NULL placement, filter và thống kê** quyết định khả năng sử dụng.
- `EXPLAIN` giúp kiểm tra kế hoạch; `EXPLAIN ANALYZE` thực thi truy vấn để đo, cần dùng đúng môi trường.
- Khi có nhiều request phân trang, tie-breaker giải quyết tính xác định của thứ tự nhưng **không thay thế snapshot/concurrency policy**.

Cách xây một truy vấn sắp xếp đáng tin cậy là: **đặt đúng khóa quan trọng nhất trước → chọn chiều cho từng khóa → xác định hành vi NULL → thêm tie-breaker → kiểm tra phân trang → đo kế hoạch trên dữ liệu đại diện**.
