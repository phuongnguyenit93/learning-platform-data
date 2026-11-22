# FIRST_VALUE, LAST_VALUE, NTH_VALUE và phạm vi cửa sổ

`FIRST_VALUE()`, `LAST_VALUE()` và `NTH_VALUE()` lấy giá trị từ một hàng trong cửa sổ, dựa trên thứ tự và phạm vi frame được khai báo. Chúng không gom nhiều hàng thành một hàng như `MIN()` hoặc `MAX()` trong truy vấn aggregate; mỗi hàng đầu vào vẫn được giữ lại và nhận thêm giá trị được tra từ frame của chính nó.

Điểm dễ gây nhầm lẫn nhất là **window frame**. Nếu có `ORDER BY` nhưng bỏ qua frame, MySQL mặc định dùng `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Vì vậy `LAST_VALUE()` thường trả về giá trị ở cuối frame hiện tại, không phải giá trị cuối cùng của toàn partition. Muốn lấy giá trị cuối toàn partition, phải mở rộng frame tới `UNBOUNDED FOLLOWING`.

Trong module `DATABASE_MYSQL`, các hàm này hữu ích khi cần gắn giá trị đầu/cuối của một nhóm vào từng hàng, lấy phần tử thứ N theo thứ tự, so sánh trạng thái hiện tại với mốc đầu/cuối hoặc xây dựng báo cáo theo thời gian. Bài học tập trung vào cách chọn frame đúng, xử lý hàng đồng hạng và NULL, đồng thời kiểm chứng kết quả trước khi dùng trong báo cáo.

## 1. Ba thành phần của một window specification

Một window specification thường có ba phần:

```sql
function_name(expression) OVER (
    PARTITION BY partition_columns
    ORDER BY ordering_columns
    frame_clause
)
```

- `PARTITION BY` chia dữ liệu thành các nhóm độc lập. Mỗi hàm cửa sổ được tính riêng trong từng partition.
- `ORDER BY` xác định thứ tự hàng trong partition. Nó quyết định hàng nào là đầu tiên, cuối cùng hoặc thứ N.
- `frame_clause` xác định phần hàng thuộc cửa sổ của từng hàng hiện tại. Đây là yếu tố đặc biệt quan trọng với `FIRST_VALUE()`, `LAST_VALUE()` và `NTH_VALUE()`.

Nếu bỏ `PARTITION BY`, toàn bộ tập kết quả thuộc một partition. Nếu bỏ `ORDER BY`, không có thứ tự nghiệp vụ đáng tin cậy để xác định đầu, cuối hay vị trí thứ N. Nếu bỏ frame, MySQL áp dụng frame mặc định theo quy tắc của window specification.

## 2. Chuẩn bị dữ liệu thực hành

Tạo bảng điểm theo nhóm và thời điểm ghi nhận. Mỗi hàng có `id` duy nhất để làm tie-breaker khi nhiều sự kiện có cùng thời gian.

```sql
CREATE TABLE employee_scores (
    id BIGINT UNSIGNED NOT NULL,
    team VARCHAR(30) NOT NULL,
    scored_at DATETIME NOT NULL,
    score DECIMAL(6,2) NULL,
    PRIMARY KEY (id),
    KEY idx_employee_scores_team_time (team, scored_at, id)
) ENGINE=InnoDB;

INSERT INTO employee_scores (id, team, scored_at, score)
VALUES
    (1, 'Alpha', '2026-01-01 09:00:00', 10.00),
    (2, 'Alpha', '2026-01-02 09:00:00', 20.00),
    (3, 'Alpha', '2026-01-03 09:00:00', 30.00),
    (4, 'Alpha', '2026-01-04 09:00:00', 40.00),
    (5, 'Beta',  '2026-01-01 09:00:00', NULL),
    (6, 'Beta',  '2026-01-02 09:00:00',  7.00),
    (7, 'Beta',  '2026-01-03 09:00:00', 11.00);
```

Mỗi team có nhiều sự kiện theo thời gian. Team `Beta` có điểm đầu tiên là NULL để quan sát quy tắc xử lý NULL của các hàm value window.

Kiểm tra dữ liệu:

```sql
SELECT id, team, scored_at, score
FROM employee_scores
ORDER BY team, scored_at, id;
```

## 3. `FIRST_VALUE()` lấy giá trị đầu tiên trong frame

Cú pháp cơ bản:

```sql
FIRST_VALUE(expression) OVER (window_specification)
```

`FIRST_VALUE()` trả về giá trị của biểu thức ở hàng đầu tiên trong frame hiện tại, theo thứ tự của window `ORDER BY`.

Ví dụ lấy điểm đầu tiên của mỗi team và hiển thị trên mọi hàng:

```sql
SELECT
    id,
    team,
    scored_at,
    score,
    FIRST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_score_in_team
FROM employee_scores
ORDER BY team, scored_at, id;
```

Frame bao phủ toàn partition nên mọi hàng của cùng team nhận cùng `first_score_in_team`. Với `Alpha`, kết quả là `10.00`; với `Beta`, kết quả là NULL vì hàng đầu tiên của team đó có `score` NULL.

### FIRST_VALUE với frame chạy từ đầu đến hàng hiện tại

Nếu frame là:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

frame bắt đầu ở đầu partition và kết thúc tại hàng hiện tại. `FIRST_VALUE()` vẫn trả về giá trị đầu tiên của partition cho mọi hàng sau đó, miễn frame không loại hàng đầu tiên.

```sql
SELECT
    id,
    team,
    score,
    FIRST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS first_score_so_far
FROM employee_scores
ORDER BY team, scored_at, id;
```

Nếu frame bắt đầu sau hàng đầu partition, ví dụ `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`, giá trị đầu tiên sẽ là hàng đầu trong frame trượt đó, không còn nhất thiết là hàng đầu toàn partition.

## 4. `LAST_VALUE()` và bẫy frame mặc định

Cú pháp:

```sql
LAST_VALUE(expression) OVER (window_specification)
```

`LAST_VALUE()` trả về giá trị của biểu thức ở hàng cuối cùng trong frame hiện tại. Nó không mặc định có nghĩa là “hàng cuối cùng của partition”.

Với `ORDER BY` và không khai báo frame, MySQL dùng frame mặc định:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Nếu thứ tự là duy nhất, frame kết thúc ở hàng hiện tại. Khi đó `LAST_VALUE(score)` thường bằng `score` của chính hàng đó. Đây là nguyên nhân phổ biến khiến kết quả khác mong đợi.

### So sánh default frame với full-partition frame

```sql
SELECT
    id,
    team,
    scored_at,
    score,
    LAST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
    ) AS last_value_default,
    LAST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_value_in_team
FROM employee_scores
ORDER BY team, scored_at, id;
```

Hai cột có ý nghĩa khác nhau:

- `last_value_default`: giá trị ở cuối frame mặc định, với khóa sắp xếp duy nhất thường là giá trị của hàng hiện tại.
- `last_value_in_team`: giá trị ở hàng cuối cùng của toàn partition; mọi hàng trong team nhận cùng kết quả.

Với `Alpha`, `last_value_in_team` là `40.00`. Với `Beta`, nó là `11.00`. Dòng Beta đầu tiên vẫn có `last_value_default = NULL` do giá trị của hàng hiện tại là NULL, trong khi `last_value_in_team = 11.00`.

### Frame lấy giá trị cuối tính đến hiện tại

Nếu mục tiêu là lấy giá trị cuối của frame chạy từ đầu tới hàng hiện tại, hãy khai báo tường minh:

```sql
LAST_VALUE(score) OVER (
    PARTITION BY team
    ORDER BY scored_at, id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Với thứ tự duy nhất, kết quả sẽ là giá trị của hàng hiện tại. Dù kết quả trông đơn giản, khai báo frame rõ ràng giúp người đọc hiểu đây là phép tính theo prefix và tránh phụ thuộc vào default frame.

## 5. `NTH_VALUE()` lấy giá trị ở vị trí thứ N trong frame

Cú pháp:

```sql
NTH_VALUE(expression, N) OVER (window_specification)
```

`NTH_VALUE()` trả về biểu thức tại hàng thứ `N` trong frame hiện tại, theo thứ tự `ORDER BY`. `N` là số nguyên dương. Vị trí được đếm từ đầu frame, không phải từ đầu partition nếu frame bắt đầu ở giữa partition.

Ví dụ lấy điểm thứ hai của mỗi team trên toàn partition:

```sql
SELECT
    id,
    team,
    scored_at,
    score,
    NTH_VALUE(score, 2) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS second_score_in_team
FROM employee_scores
ORDER BY team, scored_at, id;
```

Với `Alpha`, giá trị thứ hai là `20.00`; với `Beta`, giá trị thứ hai là `7.00`. Do frame bao phủ toàn partition, kết quả được lặp lại trên mọi hàng của team.

### NTH_VALUE với frame mặc định

Nếu bỏ frame và có `ORDER BY`, frame mặc định chỉ đi từ đầu partition đến hàng hiện tại (bao gồm các peer của hàng hiện tại theo RANGE). Ở những hàng mà frame chưa có đủ `N` hàng, `NTH_VALUE()` trả về NULL.

```sql
SELECT
    id,
    team,
    score,
    NTH_VALUE(score, 2) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
    ) AS second_value_so_far
FROM employee_scores
ORDER BY team, scored_at, id;
```

Ở hàng đầu tiên của mỗi team, frame mới có một hàng nên không có vị trí thứ hai; kết quả là NULL. Từ hàng thứ hai trở đi, vị trí thứ hai đã có mặt và kết quả là giá trị của hàng thứ hai trong partition.

NULL từ `NTH_VALUE()` có thể có hai nguyên nhân: frame chưa đủ N hàng, hoặc hàng thứ N tồn tại nhưng biểu thức tại hàng đó là NULL. Nếu cần phân biệt, kiểm tra số hàng bằng `COUNT(*) OVER (...)` với cùng `PARTITION BY`, `ORDER BY` và frame như `NTH_VALUE()`; nếu số hàng trong frame nhỏ hơn N thì vị trí chưa tồn tại, còn nếu đủ N thì giá trị NULL đến từ biểu thức ở hàng thứ N.

## 6. Frame toàn partition, frame chạy và frame trượt

Frame quyết định những hàng mà hàm được phép nhìn thấy. Ba mẫu thường dùng:

| Frame | Ý nghĩa |
|---|---|
| `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` | Toàn bộ partition. |
| `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | Từ đầu partition đến hàng hiện tại. |
| `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` | Hàng hiện tại và tối đa hai hàng trước đó. |
| `ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING` | Từ hàng hiện tại tới cuối partition. |

Ví dụ lấy phần tử đầu và cuối trong frame trượt ba hàng:

```sql
SELECT
    id,
    team,
    scored_at,
    score,
    FIRST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS first_in_last_three_rows,
    LAST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_in_last_three_rows,
    NTH_VALUE(score, 2) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS second_in_last_three_rows
FROM employee_scores
ORDER BY team, scored_at, id;
```

Khi frame có ít hơn ba hàng ở đầu partition, nó chỉ chứa những hàng hiện có. `NTH_VALUE(score, 2)` vẫn NULL cho đến khi frame có ít nhất hai hàng; nếu hàng thứ hai có score NULL, kết quả cũng NULL.

## 7. `ROWS` và `RANGE` khác nhau như thế nào?

MySQL hỗ trợ hai đơn vị frame chính:

- `ROWS`: tính frame theo số hàng vật lý trước/sau hàng hiện tại trong thứ tự cửa sổ.
- `RANGE`: tính frame theo giá trị của biểu thức `ORDER BY`; các hàng có cùng giá trị sắp xếp là peers và cùng thuộc frame khi biên là `CURRENT ROW`.

Với frame unbounded, hai đơn vị thường cho kết quả tương tự khi thứ tự là duy nhất. Khác biệt dễ thấy nhất xuất hiện ở frame có biên `CURRENT ROW` và nhiều hàng đồng hạng.

### Fixture có hai hàng cùng thời điểm

```sql
CREATE TABLE score_events_tied (
    id BIGINT UNSIGNED NOT NULL,
    team VARCHAR(30) NOT NULL,
    scored_at DATETIME NOT NULL,
    score DECIMAL(6,2) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO score_events_tied (id, team, scored_at, score)
VALUES
    (1, 'Gamma', '2026-02-01 09:00:00', 10.00),
    (2, 'Gamma', '2026-02-01 09:00:00', 20.00),
    (3, 'Gamma', '2026-02-02 09:00:00', 30.00);
```

So sánh số hàng tích lũy:

```sql
SELECT
    id,
    scored_at,
    score,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY scored_at
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS range_rows,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY scored_at
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS rows_rows
FROM score_events_tied
ORDER BY scored_at, id;
```

Với `RANGE`, hai hàng có cùng `scored_at` là peers nên cả hai nhìn thấy frame gồm hai hàng đầu tiên; `range_rows` của cả hai bằng 2. Với `ROWS`, frame tăng theo vị trí từng hàng; hai hàng đồng thời có thể nhận 1 và 2 theo thứ tự nội bộ mà window engine chọn. Vì `ORDER BY scored_at` không xác định thứ tự giữa hai hàng cùng thời gian, không được dựa vào hàng nào nhận giá trị 1 hay 2.

Nếu muốn thứ tự ổn định theo từng hàng, thêm tie-breaker duy nhất:

```sql
ORDER BY scored_at, id
```

Nhưng khi thêm `id`, hai hàng không còn là peers theo toàn bộ biểu thức ORDER BY. Hãy chọn `ROWS` hay `RANGE` theo đúng ý nghĩa nghiệp vụ, không chỉ theo kết quả mong muốn của một bộ dữ liệu hiện tại.

## 8. Frame mặc định của MySQL

Khi có `ORDER BY` và không khai báo frame, MySQL mặc định:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Khi không có `ORDER BY` và không khai báo frame, frame mặc định bao phủ toàn partition:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
```

Đó là lý do cùng một `LAST_VALUE()` có thể cho kết quả khác nhau chỉ vì thêm `ORDER BY`. Không có `ORDER BY`, khái niệm đầu/cuối không có thứ tự nghiệp vụ xác định; dù frame bao phủ toàn partition, hàng được coi là đầu/cuối vẫn không ổn định.

Thực hành tốt:

1. Luôn viết `ORDER BY` có tie-breaker ổn định khi cần xác định vị trí hàng.
2. Viết frame tường minh cho `LAST_VALUE()` và `NTH_VALUE()` nếu mục tiêu là toàn partition.
3. Viết frame tường minh cho frame chạy hoặc frame trượt.
4. Không dựa vào thứ tự vật lý, primary key hoặc thứ tự insert nếu chúng không được nêu trong window `ORDER BY`.

## 9. Hàng đồng hạng và tính xác định của kết quả

`ORDER BY scored_at` có thể để nhiều hàng có cùng thời điểm. Trong trường hợp đó, MySQL biết chúng là peers nhưng không có quy tắc xác định thứ tự tương đối giữa chúng nếu không có thêm cột sắp xếp.

Với `FIRST_VALUE()` hoặc `LAST_VALUE()`, nếu frame bắt đầu/kết thúc tại một peer group có nhiều hàng, giá trị được lấy phụ thuộc hàng nào được coi là đầu/cuối trong thứ tự đó. Với `NTH_VALUE()`, vị trí thứ N cũng có thể không ổn định nếu nhiều hàng đồng hạng nằm quanh vị trí cần lấy.

Ví dụ nên dùng:

```sql
ORDER BY scored_at, id
```

Trong đó `id` là khóa duy nhất. Nếu nghiệp vụ yêu cầu đồng hạng thực sự, không thêm tie-breaker vào cửa sổ chỉ để ép mỗi hàng có thứ tự riêng; thay vào đó, định nghĩa rõ cách chọn một đại diện trong nhóm peers hoặc chấp nhận kết quả theo peer semantics.

Window `ORDER BY` chỉ xác định thứ tự dùng để tính hàm. Nó không bảo đảm thứ tự cuối cùng của kết quả SELECT. Nếu giao diện cần kết quả có thứ tự, thêm `ORDER BY` ở query block ngoài cùng.

## 10. NULL và null treatment

Các hàm `FIRST_VALUE()`, `LAST_VALUE()` và `NTH_VALUE()` tôn trọng NULL (`RESPECT NULLS`) theo mặc định. Nếu hàng đầu tiên của frame có expression NULL, `FIRST_VALUE()` trả về NULL. Nếu hàng cuối cùng có expression NULL, `LAST_VALUE()` trả về NULL. Nếu vị trí thứ N chứa NULL, `NTH_VALUE()` cũng trả về NULL.

MySQL chỉ hỗ trợ `RESPECT NULLS`; tùy chọn `IGNORE NULLS` không được hỗ trợ. Không thể thêm `IGNORE NULLS` để yêu cầu hàm tự bỏ qua các hàng NULL.

Có thể viết `RESPECT NULLS` tường minh; nếu bỏ phần này, đó vẫn là hành vi mặc định:

```sql
SELECT
    id,
    team,
    FIRST_VALUE(score) RESPECT NULLS OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_score
FROM employee_scores
ORDER BY team, scored_at, id;
```

Ví dụ kiểm tra:

```sql
SELECT
    id,
    team,
    score,
    FIRST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_score_respecting_null,
    LAST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_score_respecting_null
FROM employee_scores
ORDER BY team, scored_at, id;
```

Với team Beta, first score là NULL vì sự kiện đầu tiên có score NULL; last score là 11.00. Không nhầm NULL với 0 hoặc với “không có hàng trong frame”.

### Nếu nghiệp vụ cần giá trị không NULL đầu tiên/cuối cùng

Vì `IGNORE NULLS` không được hỗ trợ, có thể lọc các hàng NULL trong một query block riêng nếu mục tiêu là tìm một giá trị không NULL đại diện cho toàn partition:

```sql
WITH ranked_non_null AS (
    SELECT
        team,
        score,
        scored_at,
        id,
        ROW_NUMBER() OVER (
            PARTITION BY team
            ORDER BY scored_at, id
        ) AS rn_first,
        ROW_NUMBER() OVER (
            PARTITION BY team
            ORDER BY scored_at DESC, id DESC
        ) AS rn_last
    FROM employee_scores
    WHERE score IS NOT NULL
)
SELECT
    team,
    MAX(CASE WHEN rn_first = 1 THEN score END) AS first_non_null_score,
    MAX(CASE WHEN rn_last = 1 THEN score END) AS last_non_null_score
FROM ranked_non_null
GROUP BY team;
```

Ví dụ này trả về điểm không NULL đầu tiên và cuối cùng theo thời gian cho mỗi team. Nó không tương đương hoàn toàn với `FIRST_VALUE IGNORE NULLS` hoặc `LAST_VALUE IGNORE NULLS` trên từng frame chạy; nếu cần giá trị không NULL gần nhất tại mỗi hàng, phải định nghĩa rõ frame và xây dựng truy vấn riêng phù hợp.

## 11. `NTH_VALUE()` và hướng FROM FIRST/FROM LAST

Về ý nghĩa, `NTH_VALUE(expr, N)` lấy vị trí thứ N tính từ đầu frame. MySQL hỗ trợ cách đếm từ đầu (`FROM FIRST`, cũng là mặc định); `FROM LAST` không được hỗ trợ. Nếu muốn đếm từ cuối, đảo chiều thứ tự trong window:

```sql
SELECT
    id,
    team,
    score,
    NTH_VALUE(score, 2) OVER (
        PARTITION BY team
        ORDER BY scored_at DESC, id DESC
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS second_score_from_latest
FROM employee_scores
ORDER BY team, scored_at, id;
```

Frame vẫn bao phủ toàn partition, nhưng thứ tự đã đảo nên hàng thứ hai từ đầu trong thứ tự giảm dần chính là phần tử thứ hai từ cuối theo thứ tự tăng dần.

Không nhầm `NTH_VALUE()` với `ROW_NUMBER() = N`:

- `NTH_VALUE()` trả về một giá trị và có thể lặp lại trên nhiều hàng.
- `ROW_NUMBER()` gắn số thứ tự cho từng hàng.
- `NTH_VALUE()` phụ thuộc frame; `ROW_NUMBER()` phụ thuộc partition/order và không dùng frame.

Nếu chỉ cần lọc ra đúng hàng thứ N, dùng `ROW_NUMBER()` trong CTE hoặc derived table thường rõ nghĩa hơn.

## 12. So sánh value window functions với MIN/MAX

`FIRST_VALUE()` không đồng nghĩa `MIN()`, và `LAST_VALUE()` không đồng nghĩa `MAX()`.

Ví dụ:

```sql
SELECT
    id,
    team,
    scored_at,
    score,
    FIRST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_by_time,
    MIN(score) OVER (
        PARTITION BY team
    ) AS minimum_score,
    LAST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_by_time,
    MAX(score) OVER (
        PARTITION BY team
    ) AS maximum_score
FROM employee_scores
ORDER BY team, scored_at, id;
```

- `FIRST_VALUE` lấy điểm ở sự kiện đầu tiên theo thời gian, kể cả khi điểm đó không phải nhỏ nhất.
- `MIN` lấy giá trị số nhỏ nhất, không quan tâm thứ tự thời gian.
- `LAST_VALUE` lấy điểm ở sự kiện cuối cùng theo thời gian, kể cả khi điểm đó không phải lớn nhất.
- `MAX` lấy giá trị số lớn nhất, không quan tâm thứ tự thời gian.

Chọn hàm theo câu hỏi nghiệp vụ: “giá trị ở sự kiện đầu/cuối” dùng value function; “giá trị nhỏ nhất/lớn nhất” dùng aggregate.

## 13. Kết hợp nhiều value functions trong cùng một truy vấn

Một báo cáo có thể cần điểm đầu, điểm thứ hai và điểm cuối của từng team:

```sql
SELECT
    id,
    team,
    scored_at,
    score,
    FIRST_VALUE(score) OVER w_full AS first_score,
    NTH_VALUE(score, 2) OVER w_full AS second_score,
    LAST_VALUE(score) OVER w_full AS last_score
FROM employee_scores
WINDOW w_full AS (
    PARTITION BY team
    ORDER BY scored_at, id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
ORDER BY team, scored_at, id;
```

Named window `w_full` giúp tránh lặp lại partition, ordering và frame. Cả ba hàm dùng cùng một định nghĩa nên kết quả dễ so sánh. Nếu một hàm cần frame khác, khai báo window riêng thay vì cố dùng chung một frame không phù hợp.

## 14. Lọc theo kết quả window function

Window function được tính sau các bước lọc hàng của query block. Không thể dùng alias của window function trực tiếp trong `WHERE` cùng cấp:

```sql
-- Không hợp lệ trong cùng query block:
-- SELECT ..., ROW_NUMBER() OVER (...) AS rn
-- FROM employee_scores
-- WHERE rn = 1;
```

Hãy bọc trong CTE hoặc derived table:

```sql
WITH team_endpoints AS (
    SELECT
        id,
        team,
        scored_at,
        score,
        FIRST_VALUE(score) OVER (
            PARTITION BY team
            ORDER BY scored_at, id
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) AS first_score,
        LAST_VALUE(score) OVER (
            PARTITION BY team
            ORDER BY scored_at, id
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) AS last_score,
        ROW_NUMBER() OVER (
            PARTITION BY team
            ORDER BY scored_at DESC, id DESC
        ) AS latest_row_number
    FROM employee_scores
)
SELECT team, first_score, last_score
FROM team_endpoints
WHERE latest_row_number = 1;
```

Truy vấn ngoài chỉ giữ hàng mới nhất của mỗi team, đồng thời lấy hai giá trị đầu/cuối đã tính trong partition. Cách này cũng giúp tránh lặp lại các biểu thức window trong phần lọc.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ `LAST_VALUE()` luôn lấy cuối partition | Kết quả thường chỉ là hàng hiện tại khi dùng default frame | Khai báo `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`. |
| Bỏ `ORDER BY` khi cần đầu/cuối/thứ N | Thứ tự không xác định | Sắp xếp theo cột nghiệp vụ và thêm tie-breaker duy nhất. |
| Dùng `ORDER BY` không duy nhất | Kết quả ở các peer có thể không ổn định | Thêm khóa duy nhất nếu cần thứ tự từng hàng. |
| Nhầm `RANGE` với `ROWS` | Frame peer và frame theo số hàng khác nhau | Chọn đơn vị frame theo semantics cần thiết. |
| Dùng `NTH_VALUE()` mà không kiểm tra frame | Kết quả NULL ở đầu partition hoặc khi frame thiếu N hàng | Mở frame phù hợp hoặc kiểm tra số hàng trong frame. |
| Coi NULL từ `NTH_VALUE()` luôn là thiếu hàng | Bỏ sót trường hợp hàng thứ N tồn tại nhưng expression NULL | Kiểm tra cả frame row count và giá trị expression. |
| Mong `IGNORE NULLS` hoạt động trong MySQL | Truy vấn không được hỗ trợ | Dùng `RESPECT NULLS` hoặc xây dựng query riêng cho logic bỏ NULL. |
| Dùng `FROM LAST` trong `NTH_VALUE()` | Không tương thích MySQL | Đảo chiều `ORDER BY` và dùng cách đếm mặc định từ đầu. |
| Dùng `MIN()` thay `FIRST_VALUE()` | Lấy giá trị nhỏ nhất thay vì giá trị ở hàng đầu | Phân biệt thứ tự hàng với thứ tự giá trị. |
| Nghĩ window ORDER BY sắp xếp output cuối | Client nhận hàng theo thứ tự không cam kết | Thêm `ORDER BY` ở query block ngoài cùng. |
| Dùng window alias trong WHERE cùng cấp | Lỗi do thứ tự xử lý SQL | Bọc truy vấn trong CTE hoặc derived table. |

## 16. Hiệu năng và kiểm tra kế hoạch

Value window functions cần biết partition, thứ tự và frame. Tùy frame và kế hoạch, MySQL có thể cần sắp xếp hoặc lưu tạm các hàng của partition. Full-partition frame với `UNBOUNDED FOLLOWING` có thể cần xử lý tới cuối partition trước khi xác định giá trị cuối cho các hàng đầu.

Window functions được hỗ trợ trong MySQL 8.0 trở lên; MySQL 5.7 không hỗ trợ cú pháp `OVER (...)`. Kiểm tra phiên bản trước khi triển khai:

```sql
SELECT VERSION();
```

Các nguyên tắc thực tế:

1. Chỉ chọn cột cần thiết trong query block có window function.
2. Giảm số hàng đầu vào bằng điều kiện lọc đúng nghiệp vụ trước khi tính window.
3. Dùng `PARTITION BY` phù hợp để không xử lý toàn bảng như một partition nếu không cần.
4. Dùng thứ tự ổn định, nhưng tránh thêm cột làm thay đổi peer semantics khi nghiệp vụ cần nhóm đồng hạng.
5. Đánh giá index theo thứ tự `(partition_columns, order_columns)`; index có thể giúp truy cập/sắp xếp nhưng không bảo đảm loại bỏ mọi bước sort/materialization.
6. Không tính cùng một cửa sổ lặp lại ở nhiều query block nếu có thể dùng named window hoặc CTE hợp lý.
7. Đo bằng `EXPLAIN` và dữ liệu gần thực tế.

Với bảng thực hành, index `(team, scored_at, id)` phù hợp với partition theo team và thứ tự thời gian/id. Kiểm tra truy vấn:

```sql
EXPLAIN
SELECT
    id,
    team,
    scored_at,
    score,
    LAST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_score
FROM employee_scores;
```

Nếu phiên bản hỗ trợ, `EXPLAIN ANALYZE` có thể cho biết thời gian thực tế của các iterator nhưng sẽ thực thi truy vấn. Dùng trên môi trường an toàn nếu partition lớn hoặc query có thể tiêu tốn nhiều tài nguyên.

## 17. Bài tập thực hành

### Bài tập A — FIRST_VALUE và LAST_VALUE

1. Tạo bảng `employee_scores` và nạp fixture.
2. Tính `FIRST_VALUE(score)` theo từng team.
3. Chạy `LAST_VALUE(score)` không khai báo frame.
4. Chạy lại với full-partition frame.
5. Giải thích vì sao hai kết quả LAST_VALUE khác nhau.

### Bài tập B — NTH_VALUE và frame

1. Tính `NTH_VALUE(score, 2)` trên toàn partition.
2. Bỏ frame để dùng default frame.
3. Tính `NTH_VALUE(score, 3)` trong frame trượt ba hàng.
4. Quan sát kết quả NULL ở đầu partition.
5. Phân biệt NULL do thiếu hàng thứ N với NULL ở giá trị hàng thứ N.

### Bài tập C — ROWS và RANGE

1. Tạo `score_events_tied` có hai hàng cùng thời điểm.
2. So sánh frame tích lũy dùng `ROWS` và `RANGE`.
3. Quan sát peer group và kết quả không xác định khi thiếu tie-breaker.
4. Thêm `id` vào ORDER BY và giải thích peer group thay đổi.

### Bài tập D — NULL và phần tử từ cuối

1. Quan sát `FIRST_VALUE()` và `LAST_VALUE()` trên team Beta.
2. Thử dùng `RESPECT NULLS` nếu muốn viết tường minh.
3. Xác nhận `IGNORE NULLS` không được MySQL hỗ trợ.
4. Dùng `ROW_NUMBER()` trên tập đã lọc NULL để lấy first/last non-null.
5. Dùng NTH_VALUE với ORDER BY giảm dần để lấy phần tử thứ hai từ cuối.

### Bài tập E — Báo cáo và hiệu năng

1. Tạo named window cho toàn partition.
2. Tính điểm đầu, điểm thứ hai và điểm cuối trong cùng truy vấn.
3. Lọc hàng cuối cùng bằng CTE và `ROW_NUMBER()`.
4. Chạy `EXPLAIN` với index `(team, scored_at, id)`.
5. Ghi nhận khác biệt giữa kết quả, số hàng xử lý và chi phí khi thay frame.

Bạn hoàn thành bài khi có thể giải thích frame của từng hàng, tránh bẫy `LAST_VALUE()` mặc định, chọn đúng `ROWS`/`RANGE`, xử lý peer và NULL có chủ đích, đồng thời dùng `NTH_VALUE()` đúng vị trí trong frame.

## 18. Nguyên tắc cần ghi nhớ

- `FIRST_VALUE()`, `LAST_VALUE()` và `NTH_VALUE()` đọc giá trị từ frame hiện tại; chúng không gom partition thành một hàng.
- `PARTITION BY` chia nhóm, `ORDER BY` xác định thứ tự, frame xác định những hàng hàm được phép nhìn thấy.
- Với `ORDER BY` và không khai báo frame, MySQL mặc định `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.
- `LAST_VALUE()` vì thế thường trả về giá trị cuối frame hiện tại; dùng `UNBOUNDED FOLLOWING` nếu cần cuối partition.
- `NTH_VALUE(expr, N)` đếm vị trí từ đầu frame; nếu frame chưa có N hàng hoặc giá trị ở vị trí đó là NULL, kết quả là NULL.
- `ROWS` đếm hàng theo vị trí; `RANGE` bao gồm peer rows có cùng giá trị ORDER BY tại biên CURRENT ROW.
- Thêm tie-breaker duy nhất khi cần kết quả ổn định cho từng hàng; không thêm nếu nó làm thay đổi ý nghĩa peer group.
- MySQL hỗ trợ `RESPECT NULLS`; `IGNORE NULLS` và `NTH_VALUE ... FROM LAST` không được hỗ trợ.
- Muốn đếm NTH từ cuối, đảo thứ tự ORDER BY và dùng NTH_VALUE từ đầu.
- `FIRST_VALUE` không phải `MIN`, `LAST_VALUE` không phải `MAX`; chọn theo thứ tự hàng hay độ lớn giá trị.
- Window ORDER BY không sắp xếp kết quả cuối; dùng ORDER BY ngoài cùng khi cần.
- Dùng CTE/derived table để lọc kết quả window và `EXPLAIN` để kiểm tra chi phí.

Khi xác định đúng partition, thứ tự và frame, ba hàm value window giúp truy vấn lấy mốc đầu, mốc cuối và phần tử thứ N một cách nhất quán. Việc viết frame tường minh, xử lý peer/NULL có chủ đích và kiểm tra kế hoạch thực thi sẽ giúp báo cáo phản ánh đúng dữ liệu khi số hàng và độ phức tạp tăng lên.
