# ON, USING và rủi ro của NATURAL JOIN trong PostgreSQL

## 1. Khi kết hợp hai bảng, điều kiện nối quan trọng hơn cú pháp ngắn

Trong cơ sở dữ liệu quan hệ, thông tin thường được chia thành nhiều bảng để tránh lặp lại dữ liệu và giữ tính toàn vẹn. Ví dụ, bảng `teams` lưu thông tin nhóm làm việc, còn bảng `members` lưu thành viên và mã nhóm mà mỗi người tham gia. Muốn hiển thị tên thành viên kèm tên nhóm, ta phải **JOIN** hai bảng.

PostgreSQL cung cấp nhiều cách chỉ định điều kiện JOIN:

- **`ON`**: viết biểu thức điều kiện nối một cách tường minh, chẳng hạn `ON m.team_id = t.team_id`.
- **`USING`**: viết danh sách những cột **trùng tên ở hai phía** để nối theo phép bằng, chẳng hạn `USING (team_id)`.
- **`NATURAL JOIN`**: không viết danh sách cột; PostgreSQL **tự chọn toàn bộ cột có cùng tên** ở cả hai phía làm điều kiện bằng nhau.

Thoạt nhìn, `NATURAL JOIN` ngắn và tiện. Nhưng chính tính năng “tự tìm cột” khiến câu truy vấn dễ **thay đổi ý nghĩa mà không báo lỗi khi schema phát triển**.

Xem ba cách viết:

```sql
-- Cách 1: rõ điều kiện.
SELECT m.member_name, t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id;

-- Cách 2: ngắn gọn khi tên khóa ở hai bảng giống nhau.
SELECT m.member_name, t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);

-- Cách 3: tự động nối theo TẤT CẢ cột trùng tên.
SELECT member_name, team_name
FROM join_lab.members
NATURAL JOIN join_lab.teams;
```

Hai truy vấn đầu thường tương đương về **hàng được nối** trong ví dụ này. Truy vấn thứ ba có thể cho kết quả khác vì hai bảng còn cùng một cột tên `status` nhưng mang **ý nghĩa nghiệp vụ khác nhau**.

> **Nguyên tắc thực hành:** ưu tiên `JOIN ... ON` khi muốn mô tả điều kiện rõ ràng; dùng `JOIN ... USING` khi thực sự muốn nối theo các cột cùng tên; tránh `NATURAL JOIN` trong SQL ứng dụng cần ổn định lâu dài.

Bài học sẽ giải thích không chỉ hàng nào được chọn, mà còn **số lượng cột đầu ra**, **NULL**, **LEFT/FULL JOIN**, **khóa ghép**, **schema drift** và cách nhận biết kết quả sai.

## 2. Kiến thức nền: JOIN xử lý điều gì?

Xét hai tập dữ liệu:

```text
teams
+---------+-----------+
| team_id | team_name |
+---------+-----------+
| 10      | Core      |
| 20      | Analytics |
+---------+-----------+

members
+-----------+-------------+---------+
| member_id | member_name | team_id |
+-----------+-------------+---------+
| 101       | An          | 10      |
| 102       | Bình        | 10      |
| 103       | Chi         | 20      |
+-----------+-------------+---------+
```

Nếu chạy:

```sql
SELECT m.member_name, t.team_name
FROM members AS m
JOIN teams AS t
    ON m.team_id = t.team_id;
```

ta muốn kết quả:

```text
An   | Core
Bình | Core
Chi  | Analytics
```

Điều kiện nối `m.team_id = t.team_id` xác định **cặp hàng nào từ hai bảng liên quan với nhau**.

Không phải tất cả JOIN đều giống nhau:

| Loại JOIN | Những hàng nào được giữ? |
| --- | --- |
| `INNER JOIN` hoặc `JOIN` | Chỉ những cặp hàng khớp điều kiện nối |
| `LEFT [OUTER] JOIN` | Giữ mọi hàng bên trái; phía phải không khớp được điền NULL |
| `RIGHT [OUTER] JOIN` | Giữ mọi hàng bên phải; phía trái không khớp được điền NULL |
| `FULL [OUTER] JOIN` | Giữ các hàng khớp và cả những hàng không khớp từ hai phía |
| `CROSS JOIN` | Tích Descartes: mọi cặp hàng trái-phải |
| `NATURAL JOIN` | Không phải loại giữ hàng độc lập; là cách **tự xác định cột nối**, thường ngầm hiểu `NATURAL INNER JOIN` |

`ON` và `USING` có thể đi cùng `INNER`, `LEFT`, `RIGHT` hoặc `FULL`. Ngược lại, `NATURAL` có thể đi cùng các kiểu JOIN đó nhưng PostgreSQL tự suy luận những cột phải so sánh, dẫn đến rủi ro.

Trong bài, từ **khớp** nghĩa là biểu thức điều kiện nối cho kết quả `TRUE`. Nếu điều kiện là `FALSE` hoặc `UNKNOWN` vì NULL, hai hàng **không khớp** trong JOIN thông thường.

## 3. Tạo bộ dữ liệu PostgreSQL để thực hành

Các ví dụ dùng schema `join_lab` trong một database thử nghiệm riêng. Bạn cần quyền tạo schema, bảng và chèn dữ liệu. Không thực thi câu lệnh DDL minh họa trên database production.

### 3.1. Bảng nhóm: `teams`

```sql
CREATE SCHEMA IF NOT EXISTS join_lab;

CREATE TABLE join_lab.teams (
    team_id bigint PRIMARY KEY,
    team_name text NOT NULL,
    status text NOT NULL CHECK (
        status IN ('ACTIVE', 'INACTIVE')
    ),
    created_at date NOT NULL
);
```

Mỗi nhóm có mã duy nhất `team_id`. Cột `status` cho biết **nhóm** còn đang hoạt động hay đã ngừng hoạt động.

### 3.2. Bảng thành viên: `members`

```sql
CREATE TABLE join_lab.members (
    member_id bigint PRIMARY KEY,
    member_name text NOT NULL,
    team_id bigint REFERENCES join_lab.teams(team_id),
    status text NOT NULL CHECK (
        status IN ('ACTIVE', 'INACTIVE')
    ),
    joined_at date NOT NULL
);
```

Cột `team_id` ở bảng `members` là khóa ngoại tham chiếu `teams.team_id`. Nó được phép NULL, dùng để biểu thị thành viên chưa được phân vào nhóm.

Cột `members.status` biểu thị **trạng thái của thành viên**, không phải trạng thái nhóm.

Đây chính là yếu tố quan trọng: **hai bảng có cùng tên cột `status`, nhưng không có yêu cầu rằng hai giá trị phải bằng nhau**.

### 3.3. Nạp dữ liệu

```sql
INSERT INTO join_lab.teams
    (team_id, team_name, status, created_at)
VALUES
    (10, 'Core',      'ACTIVE',   DATE '2026-01-10'),
    (20, 'Analytics', 'ACTIVE',   DATE '2026-02-01'),
    (30, 'Archive',   'INACTIVE', DATE '2025-06-01'),
    (40, 'Support',   'ACTIVE',   DATE '2026-03-15');

INSERT INTO join_lab.members
    (member_id, member_name, team_id, status, joined_at)
VALUES
    (101, 'An',    10,   'ACTIVE',   DATE '2026-01-15'),
    (102, 'Bình',  10,   'INACTIVE', DATE '2026-02-12'),
    (103, 'Chi',   20,   'ACTIVE',   DATE '2026-03-10'),
    (104, 'Dung',  30,   'ACTIVE',   DATE '2026-04-01'),
    (105, 'Em',    30,   'INACTIVE', DATE '2025-07-20'),
    (106, 'Phúc',  NULL, 'ACTIVE',   DATE '2026-05-05'),
    (107, 'Giang', 20,   'ACTIVE',   DATE '2026-06-12');
```

Dữ liệu minh họa:

**Bảng `teams`**

| team_id | team_name | status |
| ---: | --- | --- |
| 10 | Core | ACTIVE |
| 20 | Analytics | ACTIVE |
| 30 | Archive | INACTIVE |
| 40 | Support | ACTIVE |

**Bảng `members`**

| member_id | member_name | team_id | status |
| ---: | --- | ---: | --- |
| 101 | An | 10 | ACTIVE |
| 102 | Bình | 10 | INACTIVE |
| 103 | Chi | 20 | ACTIVE |
| 104 | Dung | 30 | ACTIVE |
| 105 | Em | 30 | INACTIVE |
| 106 | Phúc | NULL | ACTIVE |
| 107 | Giang | 20 | ACTIVE |

Quan sát trước khi JOIN:

- Nhóm 10 có An và Bình, nhưng Bình đang `INACTIVE`.
- Nhóm 30 đã `INACTIVE`, nhưng Dung vẫn có trạng thái thành viên `ACTIVE`.
- Phúc chưa có `team_id`.
- Nhóm 40 không có thành viên nào.

Những tình huống này giúp nhận ra sự khác nhau giữa điều kiện nối đúng theo **mã nhóm** và việc vô tình nối thêm theo `status`.

## 4. `JOIN ... ON`: mô tả điều kiện nối tường minh

### 4.1. Cú pháp cơ bản

```sql
SELECT ...
FROM left_table AS l
JOIN right_table AS r
    ON l.join_key = r.join_key;
```

Trong PostgreSQL, `JOIN` viết không kèm loại thường có nghĩa là `INNER JOIN`.

Ví dụ:

```sql
SELECT
    m.member_id,
    m.member_name,
    m.team_id,
    t.team_name
FROM join_lab.members AS m
INNER JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
ORDER BY m.member_id;
```

Kết quả:

| member_id | member_name | team_id | team_name |
| ---: | --- | ---: | --- |
| 101 | An | 10 | Core |
| 102 | Bình | 10 | Core |
| 103 | Chi | 20 | Analytics |
| 104 | Dung | 30 | Archive |
| 105 | Em | 30 | Archive |
| 107 | Giang | 20 | Analytics |

Phúc (106) không xuất hiện vì `m.team_id` của Phúc là NULL, không bằng mã nhóm nào theo phép `=`.

**Điểm mấu chốt:** câu `ON m.team_id = t.team_id` chỉ so sánh mã nhóm. Nó **không** yêu cầu `m.status` phải bằng `t.status`.

### 4.2. `ON` không đòi hai cột có cùng tên

Nếu một hệ thống có `users.department_id` và `departments.id`, bạn viết:

```sql
SELECT ...
FROM users AS u
JOIN departments AS d
    ON u.department_id = d.id;
```

`USING (department_id)` không áp dụng được nếu bảng `departments` không có cột tên `department_id`. Trong trường hợp đó, `ON` là cách diễn đạt rõ ràng.

### 4.3. `ON` có thể chứa nhiều điều kiện

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
   AND t.status = 'ACTIVE'
ORDER BY m.member_id;
```

Với INNER JOIN, kết quả gồm `101, 102, 103, 107`. Thành viên Dung và Em thuộc nhóm Archive không hoạt động nên không khớp điều kiện thứ hai.

Đây là điều kiện **chủ động**: chỉ nối thành viên với **nhóm đang hoạt động**.

Không nên nhầm nó với:

```sql
ON m.team_id = t.team_id
AND m.status = t.status
```

Điều kiện sau yêu cầu hai **trạng thái khác ý nghĩa** phải bằng nhau, có thể làm mất những hàng hợp lệ.

### 4.4. `ON` hỗ trợ các biểu thức khác ngoài bằng nhau

Trong một bài toán có yêu cầu nghiệp vụ rõ, `ON` có thể dùng:

```sql
ON a.value < b.limit_value
```

hoặc:

```sql
ON a.key IS NOT DISTINCT FROM b.key
```

hoặc kết hợp nhiều phép so sánh. Không phải mọi điều kiện như vậy đều có thể viết bằng `USING`, vì `USING` chỉ tạo điều kiện bằng nhau trên các **cột có cùng tên**.

Đối với những phép nối khác bằng, phải cẩn trọng về **số hàng sinh ra**, điều kiện NULL và hiệu năng; một phép nối theo khoảng có thể tạo nhiều kết quả cho mỗi hàng.

## 5. `JOIN ... USING`: viết gọn khi tên khóa giống nhau

### 5.1. Cú pháp

```sql
SELECT ...
FROM left_table
JOIN right_table
    USING (shared_column);
```

Đây là cách viết ngắn khi **cả hai phía đều có cột cùng tên** và ý định là nối bằng nhau.

Trong bảng ví dụ:

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id)
ORDER BY m.member_id;
```

Các thành viên trả về vẫn là `101, 102, 103, 104, 105, 107`, giống cách viết `ON m.team_id = t.team_id`.

### 5.2. `USING (team_id)` tương ứng điều kiện nào?

Với hai bảng ví dụ, ta có thể hiểu:

```sql
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id)
```

có điều kiện khớp hàng tương đương:

```sql
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
```

**Nhưng hai dạng không tạo cùng bộ cột với `SELECT *`.** Đây là khác biệt quan trọng sẽ được giải thích ở phần tiếp theo.

### 5.3. `USING` không tự nối cột khác trùng tên

Bảng `members` và `teams` có hai cột cùng tên: `team_id` và `status`.

Khi viết:

```sql
USING (team_id)
```

PostgreSQL chỉ dùng **`team_id`** làm điều kiện JOIN. Nó **không tự thêm** `status`.

Nếu chủ động viết:

```sql
USING (team_id, status)
```

thì cả hai cột được dùng làm điều kiện. Điều đó giống yêu cầu:

```sql
ON m.team_id = t.team_id
AND m.status = t.status
```

Trong dữ liệu ví dụ, điều kiện nối thêm theo `status` sẽ loại Bình (102) và Dung (104) mặc dù họ có mã nhóm hợp lệ.

Do đó, `USING` an toàn hơn `NATURAL JOIN` ở chỗ **danh sách cột được chỉ rõ**; nhưng nó vẫn có thể sai nếu người viết chọn nhầm cột.

## 6. Khác biệt lớn nhất giữa `ON` và `USING` khi `SELECT *`

Hãy xem cấu trúc hai bảng:

```text
members:
member_id | member_name | team_id | status | joined_at

teams:
team_id | team_name | status | created_at
```

### 6.1. `SELECT *` với `ON` giữ cả hai cột khóa

```sql
SELECT *
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
ORDER BY m.member_id;
```

Danh sách cột đầu ra về khái niệm:

```text
member_id
member_name
m.team_id
m.status
joined_at
t.team_id
team_name
t.status
created_at
```

Vì `SELECT *` lấy tất cả cột từ hai phía, cột `team_id` xuất hiện **hai lần**, cũng như `status`.

Điều này có thể gây bất tiện cho công cụ đọc kết quả theo **tên cột**: hai cột cùng nhãn khó phân biệt khi ánh xạ sang JSON/map. Không nên xây API dựa vào `SELECT *` của một JOIN có cột trùng tên.

### 6.2. `SELECT *` với `USING` gộp cột khóa

```sql
SELECT *
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id)
ORDER BY m.member_id;
```

Danh sách cột đầu ra về khái niệm:

```text
team_id           <-- cột kết quả được gộp theo USING
member_id
member_name
m.status
joined_at
team_name
t.status
created_at
```

`USING (team_id)` **không** xuất hai cột `team_id` riêng trong `SELECT *`. Nó tạo **một cột kết quả** cho tên `team_id`, thường được đặt trước các cột còn lại.

Còn `status` không nằm trong danh sách `USING` nên vẫn xuất hiện từ **cả hai phía**.

### 6.3. Thứ tự cột của `USING`

Với `JOIN ... USING (key_a, key_b)`, `SELECT *` thông thường có thứ tự:

1. Các cột trong `USING` theo thứ tự được liệt kê.
2. Những cột còn lại từ phía trái.
3. Những cột còn lại từ phía phải.

Vì vậy, không nên coi `USING` chỉ là “viết ngắn hơn `ON`”: nó còn **thay đổi hình dạng kết quả** khi người dùng lấy nhiều cột.

### 6.4. Dùng `SELECT` tường minh để chủ động hợp đồng đầu ra

Một cách viết rõ ràng:

```sql
SELECT
    m.member_id,
    m.member_name,
    m.team_id AS assigned_team_id,
    m.status AS member_status,
    t.team_name,
    t.status AS team_status
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
ORDER BY m.member_id;
```

Hoặc với `USING`:

```sql
SELECT
    team_id,
    m.member_id,
    m.member_name,
    m.status AS member_status,
    t.team_name,
    t.status AS team_status
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id)
ORDER BY m.member_id;
```

Đầu ra tự mô tả, ổn định hơn và dễ xử lý trong ứng dụng. Với nhiều cột mới được thêm vào bảng, truy vấn vẫn không vô tình thêm trường dữ liệu vào API chỉ vì dùng `SELECT *`.

## 7. Tham chiếu cột sau `USING` và trường hợp tên cột mơ hồ

### 7.1. Cột đã gộp có thể tham chiếu không cần tên bảng

```sql
SELECT
    team_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id)
ORDER BY team_id, m.member_name;
```

`team_id` là cột chung trong kết quả của JOIN nên bạn có thể tham chiếu trực tiếp bằng tên không định danh bảng.

### 7.2. Cột trùng tên nhưng không nằm trong `USING` vẫn mơ hồ

Sai:

```sql
-- status có ở cả members và teams:
SELECT status
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);
```

PostgreSQL không biết người viết muốn `m.status` hay `t.status`; nó có thể báo lỗi **column reference "status" is ambiguous**.

Đúng:

```sql
SELECT
    m.status AS member_status,
    t.status AS team_status
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);
```

**Quy tắc:** sau khi JOIN, hãy dùng alias và tên cột đầy đủ cho những cột có khả năng trùng nhau. `USING` chỉ giải quyết các cột **được liệt kê**.

### 7.3. Vẫn có thể cần tham chiếu từng phía

Trong nhiều trường hợp, PostgreSQL cho phép tham chiếu có định danh vào các cột nguồn của điều kiện `USING`, ví dụ `m.team_id` và `t.team_id`, khi hai alias bảng vẫn còn trong phạm vi truy vấn. Điều này đặc biệt hữu ích để phân biệt hành vi của `LEFT` hoặc `FULL JOIN`.

Tuy nhiên, nếu mục tiêu là một khóa đã được gộp trong kết quả, dùng `team_id` không định danh thường rõ ràng hơn, còn nếu cần biết giá trị của **từng phía** thì nên viết `ON` và alias tường minh.

## 8. `NATURAL JOIN` hoạt động thế nào?

### 8.1. PostgreSQL tự chọn tất cả tên cột chung

Dạng:

```sql
SELECT ...
FROM left_table
NATURAL JOIN right_table;
```

tương đương về việc chọn điều kiện nối với `USING` được PostgreSQL tự xây từ **toàn bộ tên cột xuất hiện ở cả hai phía**.

Trong ví dụ `members` và `teams`, danh sách tên chung là:

- `team_id`
- `status`

Do đó:

```sql
SELECT member_id, member_name, team_name
FROM join_lab.members
NATURAL JOIN join_lab.teams
ORDER BY member_id;
```

gần tương đương:

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id, status)
ORDER BY m.member_id;
```

**Chú ý:** `status` được tự thêm vào điều kiện mặc dù trạng thái thành viên **không phải** trạng thái nhóm.

### 8.2. Kết quả thực tế khác `ON` và `USING (team_id)`

Với điều kiện chỉ nối theo `team_id`:

| member_id | member_name | team_name | member_status | team_status |
| ---: | --- | --- | --- | --- |
| 101 | An | Core | ACTIVE | ACTIVE |
| 102 | Bình | Core | INACTIVE | ACTIVE |
| 103 | Chi | Analytics | ACTIVE | ACTIVE |
| 104 | Dung | Archive | ACTIVE | INACTIVE |
| 105 | Em | Archive | INACTIVE | INACTIVE |
| 107 | Giang | Analytics | ACTIVE | ACTIVE |

Với `NATURAL JOIN`, PostgreSQL yêu cầu đồng thời:

```text
m.team_id = t.team_id
AND
m.status = t.status
```

Vì thế kết quả chỉ còn:

| member_id | member_name | team_name |
| ---: | --- | --- |
| 101 | An | Core |
| 103 | Chi | Analytics |
| 105 | Em | Archive |
| 107 | Giang | Analytics |

Bình (102) và Dung (104) bị loại **không phải vì họ không có nhóm**, mà vì giá trị trạng thái của họ không giống trạng thái nhóm.

Đây là lỗi nguy hiểm: truy vấn **vẫn đúng cú pháp, vẫn chạy thành công, nhưng trả dữ liệu thiếu**.

### 8.3. `NATURAL JOIN` không hiểu ý nghĩa nghiệp vụ

PostgreSQL không biết `members.status` là trạng thái nhân sự còn `teams.status` là trạng thái nhóm. Nó chỉ thấy **tên cột giống nhau**.

Những tên thường gây vô tình khớp:

- `status`
- `name`
- `code`
- `created_at`
- `updated_at`
- `id`
- `type`
- `version`

Một cột `updated_at` ở hai bảng thường là timestamp độc lập, không nên tự trở thành điều kiện nối bằng nhau.

**Không suy luận rằng “tên giống nhau” đồng nghĩa với “khóa quan hệ”.** Khóa nối phải đến từ mô hình dữ liệu, ràng buộc khóa ngoại và ý định nghiệp vụ.

## 9. Rủi ro lớn nhất: `NATURAL JOIN` thay đổi kết quả khi schema đổi

Giả sử ban đầu hai bảng chỉ có một cột chung:

```text
employees(employee_id, department_id, employee_name)
departments(department_id, department_name)
```

Lúc này:

```sql
FROM employees NATURAL JOIN departments
```

có thể cho kết quả mong muốn vì `department_id` là tên cột chung duy nhất.

Sau một đợt phát triển, nhóm thêm:

```text
employees.status
departments.status
```

Câu SQL `NATURAL JOIN` **không đổi một chữ nào**, nhưng PostgreSQL bắt đầu nối thêm theo `status`.

### 9.1. Minh họa schema drift bằng CTE, không sửa bảng thật

**Trước khi thêm cột trùng tên:**

```sql
WITH
left_data(key_id, left_label) AS (
    VALUES
        (1, 'L1'),
        (2, 'L2')
),
right_data(key_id, right_label) AS (
    VALUES
        (1, 'R1'),
        (2, 'R2')
)
SELECT *
FROM left_data
NATURAL JOIN right_data
ORDER BY key_id;
```

Hai phía chỉ có tên chung `key_id`, nên kết quả có cả khóa `1` và `2`.

**Sau khi hai phía cùng xuất hiện cột `flag`:**

```sql
WITH
left_data(key_id, flag, left_label) AS (
    VALUES
        (1, 'ENABLED', 'L1'),
        (2, 'ENABLED', 'L2')
),
right_data(key_id, flag, right_label) AS (
    VALUES
        (1, 'DISABLED', 'R1'),
        (2, 'ENABLED',  'R2')
)
SELECT *
FROM left_data
NATURAL JOIN right_data
ORDER BY key_id;
```

Bây giờ `NATURAL JOIN` tự so sánh **cả `key_id` và `flag`**. Hàng có khóa 1 không còn khớp; chỉ còn khóa 2.

Điều đáng lo là truy vấn không báo “schema thay đổi”; nó âm thầm đổi tập kết quả. Nếu query dùng để tính báo cáo doanh thu hoặc đối chiếu dữ liệu, sai sót có thể khó phát hiện.

### 9.2. Vì sao `USING` hoặc `ON` ổn định hơn?

Với cùng ví dụ:

```sql
SELECT *
FROM left_data AS l
JOIN right_data AS r
    USING (key_id);
```

hoặc:

```sql
SELECT *
FROM left_data AS l
JOIN right_data AS r
    ON l.key_id = r.key_id;
```

Hai truy vấn giữ nguyên điều kiện nối theo `key_id` dù có thêm `flag`.

Có thể `SELECT *` thay đổi số cột sau khi schema đổi, nhưng **điều kiện tạo cặp hàng không tự đổi**.

Để giữ ổn định cả schema đầu ra, hãy dùng **danh sách cột SELECT tường minh** thay cho `*`.

### 9.3. Thêm cột chung có thể gây lỗi thay vì chỉ lọc sai

Nếu hai cột mới trùng tên nhưng có **kiểu dữ liệu không tương thích cho phép bằng**, `NATURAL JOIN` còn có thể gây lỗi giải quyết toán tử hoặc kiểu, dù truy vấn từng hoạt động.

Như vậy schema drift có hai lớp rủi ro:

1. **Sai ngữ nghĩa im lặng** nếu các kiểu có thể so sánh.
2. **Lỗi lúc chạy** nếu điều kiện mới không hợp lệ.

Cả hai đều là lý do tránh `NATURAL JOIN` trong những ứng dụng cần hợp đồng SQL ổn định.

## 10. Trường hợp không có cột trùng tên: NATURAL trở thành CROSS JOIN

Một tình huống rất nguy hiểm nữa: hai bảng không có tên cột chung.

```sql
WITH
left_data(left_id, left_value) AS (
    VALUES
        (1, 'A'),
        (2, 'B')
),
right_data(right_id, right_value) AS (
    VALUES
        (10, 'X'),
        (20, 'Y'),
        (30, 'Z')
)
SELECT *
FROM left_data
NATURAL JOIN right_data
ORDER BY left_id, right_id;
```

Vì không có cột chung để tạo điều kiện bằng, `NATURAL JOIN` hoạt động như **`CROSS JOIN`**: mỗi hàng trái kết hợp với mọi hàng phải.

Bên trái có 2 hàng, bên phải có 3 hàng, kết quả có:

```text
2 x 3 = 6 hàng
```

Kết quả:

| left_id | left_value | right_id | right_value |
| ---: | --- | ---: | --- |
| 1 | A | 10 | X |
| 1 | A | 20 | Y |
| 1 | A | 30 | Z |
| 2 | B | 10 | X |
| 2 | B | 20 | Y |
| 2 | B | 30 | Z |

Nếu bên trái có 100.000 hàng và bên phải có 50.000 hàng, tích Descartes có thể tạo đến **5 tỷ cặp hàng** trước khi các xử lý khác được xét. Điều này có thể làm query rất chậm và ngốn tài nguyên.

### 10.1. Phân biệt CROSS JOIN có chủ đích

```sql
SELECT *
FROM left_data
CROSS JOIN right_data;
```

Dùng `CROSS JOIN` khi **thực sự muốn mọi tổ hợp**, chẳng hạn tạo mọi cặp kích cỡ × màu sắc từ hai bảng nhỏ. Nó rõ ràng về ý định.

Dùng `NATURAL JOIN` mà tình cờ không có tên cột trùng là cách tạo tích Descartes **ngoài dự kiến**.

### 10.2. Vì sao đây là lỗi ngược với thêm cột?

Khi thêm cột chung, `NATURAL JOIN` có thể **lọc quá nhiều**.

Khi xóa hoặc đổi tên cột chung, `NATURAL JOIN` có thể **giảm điều kiện nối** và tạo **quá nhiều hàng**.

Điều kiện nối vì thế không ổn định trước cả việc **thêm** lẫn **bớt/đổi tên** cột.

## 11. `LEFT JOIN ... ON`: giữ mọi hàng ở phía trái

### 11.1. Lấy cả thành viên chưa có nhóm

```sql
SELECT
    m.member_id,
    m.member_name,
    m.team_id,
    t.team_name
FROM join_lab.members AS m
LEFT JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
ORDER BY m.member_id;
```

Kết quả:

| member_id | member_name | team_id | team_name |
| ---: | --- | ---: | --- |
| 101 | An | 10 | Core |
| 102 | Bình | 10 | Core |
| 103 | Chi | 20 | Analytics |
| 104 | Dung | 30 | Archive |
| 105 | Em | 30 | Archive |
| 106 | Phúc | NULL | NULL |
| 107 | Giang | 20 | Analytics |

`LEFT JOIN` giữ thành viên Phúc dù `team_id` chưa được gán. Vì không có hàng `teams` khớp, cột `t.team_name` được điền NULL.

### 11.2. Dùng `USING` với LEFT JOIN

```sql
SELECT
    m.member_id,
    m.member_name,
    team_id,
    t.team_name
FROM join_lab.members AS m
LEFT JOIN join_lab.teams AS t
    USING (team_id)
ORDER BY m.member_id;
```

Kết quả về các hàng và giá trị hiển thị giống truy vấn trước.

Đối với `LEFT JOIN ... USING (team_id)`, cột `team_id` được gộp trong output **ưu tiên giá trị phía trái**. Với các hàng khớp, hai mã nhóm bằng nhau; với hàng không khớp, giá trị vẫn đến từ bên trái.

Điều này quan trọng khi bạn mở rộng sang `RIGHT` hoặc `FULL JOIN`.

## 12. Vị trí điều kiện: `ON` khác `WHERE` với OUTER JOIN

Đây là một lỗi phổ biến kể cả khi sử dụng `ON` đúng cách.

Yêu cầu: “Hiển thị **mọi thành viên**, và chỉ kèm thông tin nhóm **nếu nhóm đang ACTIVE**”.

Đúng:

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name,
    t.status AS team_status
FROM join_lab.members AS m
LEFT JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
   AND t.status = 'ACTIVE'
ORDER BY m.member_id;
```

Các thành viên ở nhóm Archive (104, 105) và thành viên không có nhóm (106) **vẫn xuất hiện**, nhưng cột phía nhóm là NULL nếu không có nhóm ACTIVE phù hợp.

Nếu chuyển điều kiện vào `WHERE`:

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name,
    t.status AS team_status
FROM join_lab.members AS m
LEFT JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
WHERE t.status = 'ACTIVE'
ORDER BY m.member_id;
```

truy vấn chỉ giữ `101, 102, 103, 107`. Những hàng không khớp có `t.status = NULL`, nên điều kiện `WHERE t.status = 'ACTIVE'` cho UNKNOWN và bị loại.

**Khác biệt ngữ nghĩa:**

- Điều kiện trong `ON` quyết định **hàng nào được ghép**, trước khi tạo các hàng NULL mở rộng của outer join.
- Điều kiện trong `WHERE` lọc **kết quả JOIN**, có thể loại những hàng không khớp mà `LEFT JOIN` vốn được dùng để giữ.

Với `INNER JOIN`, nhiều điều kiện có thể di chuyển giữa `ON` và `WHERE` mà không đổi tập kết quả. **Không suy rộng điều đó sang outer join.**

## 13. `USING` trong `RIGHT JOIN` và `FULL JOIN`

`USING` không chỉ dùng với INNER JOIN.

### 13.1. RIGHT JOIN: giữ bên phải

Nếu muốn giữ mọi nhóm, kể cả nhóm Support chưa có thành viên:

```sql
SELECT
    t.team_id,
    t.team_name,
    m.member_id,
    m.member_name
FROM join_lab.members AS m
RIGHT JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
ORDER BY t.team_id, m.member_id;
```

Nhóm 40 vẫn xuất hiện với `member_id = NULL` và `member_name = NULL`.

Có thể viết tương đương bằng cách đảo hướng bảng:

```sql
SELECT
    t.team_id,
    t.team_name,
    m.member_id,
    m.member_name
FROM join_lab.teams AS t
LEFT JOIN join_lab.members AS m
    ON m.team_id = t.team_id
ORDER BY t.team_id, m.member_id;
```

Nhiều nhóm phát triển ưu tiên `LEFT JOIN` vì luồng đọc “giữ bảng chính bên trái” dễ theo dõi; `RIGHT JOIN` vẫn là cú pháp hợp lệ.

### 13.2. FULL JOIN: giữ cả hai phía

Dùng hai tập dữ liệu đơn giản để quan sát:

```sql
WITH
left_side(team_id, left_value) AS (
    VALUES
        (1, 'L1'),
        (2, 'L2')
),
right_side(team_id, right_value) AS (
    VALUES
        (2, 'R2'),
        (3, 'R3')
)
SELECT
    team_id,
    left_value,
    right_value
FROM left_side
FULL JOIN right_side
    USING (team_id)
ORDER BY team_id;
```

Kết quả:

| team_id | left_value | right_value |
| ---: | --- | --- |
| 1 | L1 | NULL |
| 2 | L2 | R2 |
| 3 | NULL | R3 |

Cột `team_id` duy nhất trong output `USING` thể hiện khóa của hàng **từ bên có dữ liệu**:

- Khóa 1: chỉ bên trái, nên `team_id = 1`.
- Khóa 2: hai bên khớp, đều có giá trị 2.
- Khóa 3: chỉ bên phải, nên `team_id = 3`.

Về mặt giá trị, cột gộp trong `FULL JOIN ... USING` có thể hiểu giống:

```sql
COALESCE(left_side.team_id, right_side.team_id)
```

Đối với các hàng khớp bằng `=`, hai giá trị khóa bằng nhau; với hàng không khớp một phía, bên còn lại là NULL.

### 13.3. Nếu dùng `FULL JOIN ... ON`

```sql
WITH
left_side(team_id, left_value) AS (
    VALUES (1, 'L1'), (2, 'L2')
),
right_side(team_id, right_value) AS (
    VALUES (2, 'R2'), (3, 'R3')
)
SELECT
    COALESCE(l.team_id, r.team_id) AS team_id,
    l.team_id AS left_team_id,
    r.team_id AS right_team_id,
    l.left_value,
    r.right_value
FROM left_side AS l
FULL JOIN right_side AS r
    ON l.team_id = r.team_id
ORDER BY team_id;
```

Ở đây `ON` giữ **hai cột khóa nguồn** độc lập trong `SELECT`, và người viết quyết định gộp hay không bằng `COALESCE`.

Đây là lý do `ON` đôi khi rõ ràng hơn `USING` trong báo cáo **đối soát**, nơi cần biết khóa chỉ có bên trái, chỉ có bên phải hay có ở cả hai.

## 14. `NATURAL LEFT JOIN` cũng có rủi ro

Không chỉ `NATURAL INNER JOIN`: PostgreSQL cho phép các biến thể như:

```sql
SELECT ...
FROM left_table
NATURAL LEFT JOIN right_table;
```

Ý nghĩa là `LEFT JOIN` nhưng điều kiện nối vẫn được suy ra từ **mọi cột trùng tên**.

Trong bộ mẫu, nếu viết:

```sql
SELECT
    member_id,
    member_name,
    team_name
FROM join_lab.members
NATURAL LEFT JOIN join_lab.teams
ORDER BY member_id;
```

thì PostgreSQL vẫn giữ mọi thành viên bên trái, **nhưng** Bình (102) và Dung (104) không khớp vì status khác. Họ sẽ hiện `team_name = NULL` dù `team_id` của họ tồn tại trong bảng nhóm.

Đây là lỗi dễ bị hiểu nhầm thành “khóa ngoại bị mất” hoặc “dữ liệu nhóm chưa đồng bộ”, trong khi vấn đề thực tế là `NATURAL` đã thêm điều kiện sai.

Sự khác biệt:

- `NATURAL INNER JOIN` thường làm **mất hàng**.
- `NATURAL LEFT JOIN` có thể giữ hàng nhưng **làm mất thông tin phía phải** một cách âm thầm.

**Không có kiểu outer join nào tự khắc phục rủi ro của `NATURAL`.**

## 15. So sánh khi khóa JOIN có NULL

### 15.1. `=` không coi hai NULL là bằng nhau

Trong PostgreSQL:

```sql
SELECT
    NULL::integer = NULL::integer AS normal_equality,
    NULL::integer IS NOT DISTINCT FROM NULL::integer
        AS null_safe_equality;
```

`normal_equality` là NULL (UNKNOWN); `null_safe_equality` là TRUE.

Vì `USING (team_id)` và `NATURAL JOIN` dựa trên phép bằng thông thường cho các cột tương ứng, **hai hàng có khóa NULL không tự khớp nhau**.

### 15.2. JOIN NULL-safe khi nghiệp vụ thật sự cần

Giả sử bảng dữ liệu thô có hai khóa nullable và bạn muốn coi “cả hai cùng NULL” là cùng nhóm theo một quy tắc đặc biệt:

```sql
WITH
a(key_value, left_note) AS (
    VALUES
        (1::integer, 'A1'),
        (NULL::integer, 'A_NULL')
),
b(key_value, right_note) AS (
    VALUES
        (1::integer, 'B1'),
        (NULL::integer, 'B_NULL')
)
SELECT
    a.key_value AS left_key,
    b.key_value AS right_key,
    a.left_note,
    b.right_note
FROM a
JOIN b
    ON a.key_value IS NOT DISTINCT FROM b.key_value
ORDER BY a.left_note;
```

Kết quả có cả cặp `1–1` và cặp `NULL–NULL`.

`USING (key_value)` **không** viết được điều kiện NULL-safe này vì nó chỉ dùng phép bằng theo quy tắc tiêu chuẩn.

**Cảnh báo:** nếu có nhiều hàng NULL ở cả hai bảng, null-safe join có thể tạo **nhiều tổ hợp NULL–NULL**, dẫn đến số hàng tăng mạnh. Không dùng nó chỉ để “sửa” việc INNER JOIN bỏ qua giá trị chưa có; cần xác định NULL có thật sự mang ý nghĩa một khóa chung hay không.

### 15.3. Outer join vẫn giữ hàng không khớp

Với `LEFT JOIN`, hàng trái có khóa NULL vẫn được giữ nhưng không có giá trị phía phải. Nếu yêu cầu là “hiển thị cả thành viên chưa có nhóm”, `LEFT JOIN` là lựa chọn phù hợp hơn việc biến NULL thành một giá trị mã nhóm giả.

## 16. JOIN nhiều cột: `ON` và `USING` với khóa ghép

Trong hệ thống đa tenant, một ID có thể chỉ duy nhất **trong phạm vi tenant**, không duy nhất toàn database.

Ví dụ:

```text
invoices
tenant_id | invoice_id | issued_date
----------+------------+------------
1         | 500        | ...
2         | 500        | ...
1         | 501        | ...

invoice_lines
tenant_id | invoice_id | line_no | quantity
----------+------------+---------+---------
1         | 500        | 1       | 2
2         | 500        | 1       | 3
1         | 501        | 1       | 1
```

### 16.1. Tạo khóa chính và khóa ngoại ghép

```sql
CREATE TABLE join_lab.invoices (
    tenant_id integer NOT NULL,
    invoice_id bigint NOT NULL,
    issued_date date NOT NULL,
    PRIMARY KEY (tenant_id, invoice_id)
);

CREATE TABLE join_lab.invoice_lines (
    tenant_id integer NOT NULL,
    invoice_id bigint NOT NULL,
    line_no integer NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (tenant_id, invoice_id, line_no),
    FOREIGN KEY (tenant_id, invoice_id)
        REFERENCES join_lab.invoices (tenant_id, invoice_id)
);
```

Nạp dữ liệu:

```sql
INSERT INTO join_lab.invoices
    (tenant_id, invoice_id, issued_date)
VALUES
    (1, 500, DATE '2026-10-01'),
    (2, 500, DATE '2026-10-02'),
    (1, 501, DATE '2026-10-03');

INSERT INTO join_lab.invoice_lines
    (tenant_id, invoice_id, line_no, quantity)
VALUES
    (1, 500, 1, 2),
    (2, 500, 1, 3),
    (1, 501, 1, 1);
```

### 16.2. JOIN theo đúng hai cột khóa

Với `ON`:

```sql
SELECT
    l.tenant_id,
    l.invoice_id,
    l.line_no,
    l.quantity,
    i.issued_date
FROM join_lab.invoice_lines AS l
JOIN join_lab.invoices AS i
    ON l.tenant_id = i.tenant_id
   AND l.invoice_id = i.invoice_id
ORDER BY l.tenant_id, l.invoice_id, l.line_no;
```

Với `USING`:

```sql
SELECT
    tenant_id,
    invoice_id,
    l.line_no,
    l.quantity,
    i.issued_date
FROM join_lab.invoice_lines AS l
JOIN join_lab.invoices AS i
    USING (tenant_id, invoice_id)
ORDER BY tenant_id, invoice_id, l.line_no;
```

Cả hai trả đúng ba hàng:

| tenant_id | invoice_id | line_no | quantity |
| ---: | ---: | ---: | ---: |
| 1 | 500 | 1 | 2 |
| 1 | 501 | 1 | 1 |
| 2 | 500 | 1 | 3 |

### 16.3. Thiếu một phần khóa có thể nối chéo tenant

Sai:

```sql
SELECT
    l.tenant_id AS line_tenant,
    i.tenant_id AS invoice_tenant,
    l.invoice_id,
    l.quantity
FROM join_lab.invoice_lines AS l
JOIN join_lab.invoices AS i
    ON l.invoice_id = i.invoice_id
ORDER BY l.invoice_id, line_tenant, invoice_tenant;
```

Với `invoice_id = 500` tồn tại ở cả tenant 1 và 2, mỗi dòng invoice line mang ID 500 có thể khớp cả **hai invoice**, tạo ra **bốn cặp** thay vì hai cặp đúng. Cộng với invoice 501, tổng thành năm hàng.

Một phần kết quả sai:

```text
line_tenant = 1, invoice_tenant = 2, invoice_id = 500
line_tenant = 2, invoice_tenant = 1, invoice_id = 500
```

Đây không chỉ là “bị trùng dữ liệu”, mà có thể trở thành lỗi **lộ dữ liệu giữa tenant** hoặc sai báo cáo tiền nếu điều kiện xác thực/lọc tenant không được thiết kế đầy đủ.

`USING (tenant_id, invoice_id)` giúp viết ngắn điều kiện khóa ghép, nhưng **vẫn phải ghi đủ mọi thành phần khóa**. `USING (invoice_id)` cũng sai ngữ nghĩa như `ON l.invoice_id = i.invoice_id` trong ví dụ này.

## 17. JOIN nhiều bảng và phạm vi của `USING`

Khi nối ba bảng trở lên, việc dùng nhiều `JOIN ... USING` có thể gọn nhưng cũng cần nhận thức **kết quả trung gian**.

Giả sử có các quan hệ:

```text
orders(order_id, customer_id, created_at)
customers(customer_id, customer_name)
payments(payment_id, order_id, state)
```

Một truy vấn mẫu:

```sql
SELECT
    order_id,
    customer_id,
    c.customer_name,
    p.payment_id
FROM orders AS o
JOIN customers AS c
    USING (customer_id)
LEFT JOIN payments AS p
    USING (order_id);
```

Ý định là:

1. Nối `orders` với `customers` bằng `customer_id`.
2. Nối kết quả đó với `payments` bằng `order_id`.
3. Giữ đơn chưa có payment nhờ `LEFT JOIN`.

Các bảng `orders`, `customers`, `payments` trong đoạn này là **lược đồ minh họa**, chưa được tạo trong bộ lab; muốn chạy cần tạo chúng hoặc đổi sang schema thực tế.

### 17.1. Cột chung của kết quả trung gian

Khi viết nhiều `USING`, tên cột dùng ở bước sau có thể xuất phát từ **kết quả JOIN đã gộp trước đó**, không chỉ từ một bảng gốc. Cần tránh suy luận dựa vào `SELECT *` ở chuỗi JOIN dài.

### 17.2. NATURAL JOIN nhiều bảng càng khó kiểm soát

Nếu đổi từng bước thành `NATURAL JOIN`, mỗi lần JOIN PostgreSQL sẽ tự xác định những cột trùng tên giữa **kết quả bên trái hiện tại** và quan hệ bên phải. Một cột `status` hoặc `created_at` vô tình giống nhau có thể xuất hiện ở nhiều mức.

Đó là lý do một chuỗi `NATURAL JOIN` trong hệ thống đang phát triển rất khó duy trì: lập trình viên phải hiểu **tất cả tên cột** của toàn bộ các bảng và kết quả trung gian, kể cả khi schema đổi sau này.

## 18. Cardinality: vì sao JOIN có thể tăng số hàng?

Một JOIN không tự bảo đảm “mỗi thành viên chỉ có một hàng” nếu quan hệ phía phải có nhiều hàng cùng khóa.

Trong bộ mẫu, `teams.team_id` là PRIMARY KEY nên mỗi `member.team_id` có tối đa một nhóm khớp. Điều đó giữ kết quả INNER JOIN theo team_id không nhân đôi một thành viên.

Nhưng hãy xem bảng một-nhiều:

```text
team_id = 10
  -> An
  -> Bình

team_id = 20
  -> Chi
  -> Giang
```

Một query từ `teams` JOIN `members` trả **một hàng cho mỗi thành viên**, không phải một hàng cho mỗi nhóm.

### 18.1. Đếm thành viên theo nhóm

```sql
SELECT
    t.team_id,
    t.team_name,
    COUNT(m.member_id) AS member_count
FROM join_lab.teams AS t
LEFT JOIN join_lab.members AS m
    USING (team_id)
GROUP BY t.team_id, t.team_name
ORDER BY t.team_id;
```

Kết quả:

| team_id | team_name | member_count |
| ---: | --- | ---: |
| 10 | Core | 2 |
| 20 | Analytics | 2 |
| 30 | Archive | 2 |
| 40 | Support | 0 |

`COUNT(m.member_id)` là 0 cho nhóm Support vì không có thành viên khớp; cột `m.member_id` của hàng mở rộng bởi LEFT JOIN là NULL.

### 18.2. Tại sao `COUNT(*)` có thể sai ở LEFT JOIN?

```sql
SELECT
    t.team_id,
    COUNT(*) AS row_count,
    COUNT(m.member_id) AS member_count
FROM join_lab.teams AS t
LEFT JOIN join_lab.members AS m
    USING (team_id)
GROUP BY t.team_id
ORDER BY t.team_id;
```

Với nhóm Support, `COUNT(*) = 1` vì LEFT JOIN vẫn tạo **một hàng** cho nhóm không có thành viên; còn `COUNT(m.member_id) = 0`.

Khi viết báo cáo tổng hợp, phải hiểu **mỗi hàng JOIN đại diện điều gì**, không dùng `COUNT(*)` một cách máy móc.

### 18.3. `DISTINCT` không chữa điều kiện JOIN sai

Nếu JOIN sai và tạo nhiều cặp hàng, thêm:

```sql
SELECT DISTINCT ...
```

có thể làm ít hàng hơn, nhưng **không bảo đảm sửa ý nghĩa của các phép ghép**. Đặc biệt trong tổng hợp tiền, doanh thu đã bị nhân đôi trước khi `DISTINCT` bên ngoài xuất hiện có thể vẫn sai.

Phải sửa **điều kiện khóa** hoặc **mô hình quan hệ** trước, thay vì dùng `DISTINCT` để che nguyên nhân.

## 19. `USING`, `ON` và truy vấn chống khớp (*anti-join*)

Một mục tiêu phổ biến: tìm các nhóm **chưa có thành viên**.

### 19.1. LEFT JOIN + IS NULL

```sql
SELECT
    t.team_id,
    t.team_name
FROM join_lab.teams AS t
LEFT JOIN join_lab.members AS m
    ON m.team_id = t.team_id
WHERE m.member_id IS NULL
ORDER BY t.team_id;
```

Kết quả: nhóm `40 - Support`.

Điều kiện `m.member_id IS NULL` nhận diện những hàng không có thành viên, vì `m.member_id` là PRIMARY KEY, không thể NULL ở hàng thật.

### 19.2. Dùng `USING`

```sql
SELECT
    t.team_id,
    t.team_name
FROM join_lab.teams AS t
LEFT JOIN join_lab.members AS m
    USING (team_id)
WHERE m.member_id IS NULL
ORDER BY t.team_id;
```

Kết quả giống truy vấn trước.

### 19.3. Dùng `NOT EXISTS`

```sql
SELECT
    t.team_id,
    t.team_name
FROM join_lab.teams AS t
WHERE NOT EXISTS (
    SELECT 1
    FROM join_lab.members AS m
    WHERE m.team_id = t.team_id
)
ORDER BY t.team_id;
```

Truy vấn này cũng tìm nhóm 40. `NOT EXISTS` thường biểu diễn rất rõ ý định “không có hàng liên quan”.

Khi điều kiện chống khớp phức tạp hoặc phía phải có cột nullable, cần chọn đúng cột để kiểm tra `IS NULL` nếu dùng LEFT JOIN; `NOT EXISTS` có thể giúp tránh một số lỗi đó. Không khẳng định một cách viết luôn nhanh hơn: cần xem kế hoạch thực tế.

## 20. `ON` với biểu thức và khóa khác tên: vì sao không cố dùng `USING`?

`USING` chỉ thích hợp khi hai bên có **cột cùng tên** và điều kiện cần là **bằng nhau**. Có nhiều bài toán cần `ON`.

### 20.1. Tên khóa khác nhau

```sql
-- Ví dụ schema minh họa:
SELECT
    o.order_id,
    c.display_name
FROM orders AS o
JOIN customers AS c
    ON o.customer_id = c.id;
```

`USING (customer_id)` sẽ không đúng nếu `customers` chỉ có `id`.

### 20.2. Nối theo khoảng thời gian

Giả sử một bảng chứa các khoảng hiệu lực của chính sách:

```sql
-- Minh họa lược đồ khác, không thuộc bộ lab đã tạo:
SELECT
    e.event_id,
    p.policy_name
FROM events AS e
JOIN policies AS p
    ON e.occurred_at >= p.valid_from
   AND e.occurred_at <  p.valid_to;
```

Điều kiện nối là khoảng nửa mở, không phải phép bằng trên cột cùng tên; `ON` là cách diễn đạt thích hợp.

Nếu các khoảng hiệu lực bị chồng lấn, một sự kiện có thể khớp nhiều policy, tạo nhiều hàng. Cần kiểm tra toàn vẹn dữ liệu, không chỉ đổi cú pháp JOIN.

### 20.3. Nối theo nhiều biểu thức

Trong một số hệ thống kế thừa, giá trị khóa được lưu dưới dạng text và cần chuyển kiểu. Có thể gặp:

```sql
-- Chỉ minh họa ý tưởng: cần đảm bảo dữ liệu hợp lệ trước cast.
ON a.raw_id::bigint = b.id
```

`USING` không cho phép viết biểu thức cast tùy ý trong danh sách cột. Tuy nhiên, việc cast trên dữ liệu thô có thể gây lỗi hoặc ảnh hưởng index; tốt hơn nên sửa kiểu lưu trữ hoặc chuẩn hóa trước nếu có thể.

### 20.4. Tránh viết điều kiện “luôn đúng” để nối bằng mọi giá

```sql
ON TRUE
```

có thể tạo hành vi gần với tích Descartes (tùy loại JOIN), chỉ thích hợp khi thực sự được yêu cầu. Nếu muốn mọi tổ hợp, `CROSS JOIN` giúp ý định rõ ràng hơn.

## 21. Những câu JOIN cùng ý định nhưng khác danh sách cột

Để ghi nhớ, hãy so sánh:

### 21.1. `ON`

```sql
SELECT *
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id;
```

- Hàng khớp theo `team_id`.
- `SELECT *` xuất **hai cột `team_id`** và hai cột `status`.
- Mã nhóm của từng phía còn nguyên trong kết quả.

### 21.2. `USING`

```sql
SELECT *
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);
```

- Hàng khớp theo `team_id`.
- `SELECT *` xuất **một cột `team_id`**.
- `status` vẫn xuất hai lần vì không nằm trong `USING`.

### 21.3. `NATURAL JOIN`

```sql
SELECT *
FROM join_lab.members
NATURAL JOIN join_lab.teams;
```

- Hàng khớp theo **cả `team_id` và `status`**.
- `SELECT *` gộp cả hai cột chung thành mỗi tên một cột.
- Khi schema xuất hiện thêm tên chung, điều kiện JOIN và hình dạng kết quả có thể đổi.

### 21.4. Bảng tóm tắt

| Tiêu chí | `ON` | `USING` | `NATURAL JOIN` |
| --- | --- | --- | --- |
| Ai chọn cột/biểu thức nối? | Lập trình viên | Lập trình viên chọn tên cột | PostgreSQL tự tìm tên chung |
| Hỗ trợ khóa khác tên? | Có | Không | Không có danh sách điều khiển |
| Hỗ trợ biểu thức khác `=`? | Có | Không | Không |
| Tự thêm cột trùng tên vào điều kiện? | Không | Không | **Có** |
| `SELECT *` gộp cột khóa? | Không | Có, theo danh sách USING | Có, theo mọi cột chung |
| Câu JOIN đổi nghĩa khi thêm cột cùng tên? | Không tự đổi điều kiện | Không tự đổi danh sách | **Có thể** |
| Tương thích nhiều loại OUTER JOIN? | Có | Có | Có |
| Phù hợp code production lâu dài? | **Rất phù hợp** | Phù hợp khi được kiểm soát | **Nên tránh** |

## 22. Performance: `ON` và `USING` có khác nhau về tốc độ không?

Khi hai biểu thức thực sự cùng ngữ nghĩa:

```sql
JOIN teams AS t
    ON m.team_id = t.team_id
```

và:

```sql
JOIN teams AS t
    USING (team_id)
```

PostgreSQL thường có thể tối ưu thành **cùng điều kiện equijoin**. Không nên chọn `USING` chỉ vì suy đoán nó nhanh hơn `ON`.

Trọng tâm hiệu năng là:

- Khóa nối và **kiểu dữ liệu** có phù hợp không?
- Có index phù hợp không?
- Thống kê về số hàng và phân bố khóa có chính xác không?
- JOIN tạo bao nhiêu hàng?
- PostgreSQL chọn `Nested Loop`, `Hash Join` hay `Merge Join`?
- Điều kiện lọc có giúp giảm dữ liệu trước hoặc trong JOIN không?
- Có làm phép cast/hàm lên khóa khiến index khó sử dụng không?

### 22.1. Index trên khóa chính và khóa ngoại

Trong ví dụ:

```sql
CREATE TABLE join_lab.teams (
    team_id bigint PRIMARY KEY,
    ...
);
```

`PRIMARY KEY` tự tạo index phù hợp trên `teams.team_id`.

Nhưng ràng buộc:

```sql
team_id bigint REFERENCES join_lab.teams(team_id)
```

**không tự động tạo index trên `members.team_id`** chỉ vì đó là khóa ngoại. Với bảng lớn và JOIN/lọc thường xuyên theo mã nhóm, có thể cân nhắc:

```sql
CREATE INDEX idx_members_team_id
ON join_lab.members (team_id);
```

Index làm tăng chi phí lưu trữ/bảo trì khi ghi; hãy đánh giá dựa trên workload. Với bảng ví dụ rất nhỏ, query planner có thể dùng sequential scan và đó là lựa chọn hợp lý.

### 22.2. Xem kế hoạch bằng `EXPLAIN`

```sql
EXPLAIN
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id;
```

Kế hoạch có thể cho thấy các node như:

- `Hash Join`: xây bảng băm cho một phía và dò phía còn lại.
- `Merge Join`: nối hai nguồn được sắp theo khóa.
- `Nested Loop`: xét các hàng của một phía và tìm hàng khớp ở phía kia, có thể dùng index.

Cùng truy vấn viết bằng `USING (team_id)` có khả năng có kế hoạch rất gần hoặc giống nhau khi điều kiện tương đương. Không có bảo đảm planner luôn chọn cùng kế hoạch trong mọi hoàn cảnh vì thống kê, các thuộc tính khác của câu SELECT và cấu hình cũng ảnh hưởng.

### 22.3. Đừng dùng `EXPLAIN ANALYZE` bừa bãi với câu ghi

`EXPLAIN (ANALYZE, BUFFERS)` **thực thi câu SQL** để đo. Khi đi kèm `UPDATE`, `DELETE` hoặc các câu có tác dụng phụ, nó có thể thay đổi dữ liệu. Với ví dụ SELECT ở đây dễ thử hơn, nhưng trong production vẫn cần cân nhắc tải truy vấn, quyền và tính nhạy cảm của dữ liệu.

### 22.4. Join sai có thể “nhanh hơn” vì trả thiếu dữ liệu

`NATURAL JOIN` trong bộ mẫu trả ít hàng hơn `JOIN ... ON team_id`. Nếu đo thời gian và thấy nó nhanh hơn, điều đó không chứng minh cú pháp tốt hơn: nó đang **thực thi điều kiện khác** và bỏ sót các hàng hợp lệ.

**So sánh hiệu năng chỉ có ý nghĩa khi hai truy vấn tương đương về kết quả và đáp ứng cùng yêu cầu nghiệp vụ.**

## 23. Thiết kế SQL dễ duy trì và tránh rủi ro schema drift

### 23.1. Dùng alias ngắn nhưng có nghĩa

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id;
```

Alias `m` và `t` giúp biểu thức `ON` ngắn mà vẫn thể hiện rõ cột thuộc bảng nào.

### 23.2. Không dùng `SELECT *` làm hợp đồng API

Một phiên bản API đọc kết quả JOIN rồi chuyển thành JSON có thể bị ảnh hưởng khi bảng thêm cột trùng tên hoặc `USING` gộp cột. Hãy liệt kê cột và đặt alias rõ:

```sql
SELECT
    m.member_id,
    m.member_name,
    m.status AS member_status,
    t.team_id,
    t.team_name,
    t.status AS team_status
FROM join_lab.members AS m
LEFT JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
ORDER BY m.member_id;
```

Với `LEFT JOIN`, các cột nhóm của người chưa được phân nhóm có thể NULL; ứng dụng phải hiểu đây là “không có hàng khớp” chứ không phải một nhóm tên rỗng.

### 23.3. Chọn cột khóa từ mô hình quan hệ

Đừng tìm tên cột nào trùng rồi nối thử. Hãy nhìn:

- Primary key của bảng đích.
- Foreign key từ bảng nguồn.
- Khóa ghép gồm những cột nào.
- Có quan hệ một-nhiều, nhiều-nhiều hay một-một.
- Có tenant/bối cảnh hoặc thời điểm hiệu lực cần thêm vào điều kiện không.

Trong bảng mẫu, `members.team_id` → `teams.team_id` là quan hệ đúng. `members.status` không phải foreign key đến `teams.status`, nên không thuộc điều kiện nối mặc định.

### 23.4. Thiết kế migration và review JOIN

Trong review SQL, với mỗi JOIN hãy hỏi:

1. Điều kiện nối có ghi đủ thành phần khóa không?
2. Cột nào có thể NULL?
3. Số lượng hàng mong đợi là bao nhiêu?
4. Có bảng nào có nhiều hàng trên cùng khóa không?
5. Với OUTER JOIN, điều kiện ở `ON` hay `WHERE` có đúng ý định?
6. Có dùng `NATURAL` hoặc `SELECT *` khiến schema đổi làm kết quả thay đổi không?
7. Các cột trùng tên có thật sự cùng ý nghĩa không?

Nếu không thể trả lời các câu hỏi này, rất có thể JOIN chưa được mô tả đủ rõ.

## 24. Những lỗi JOIN thường gặp

| Tình huống | Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- | --- |
| `NATURAL JOIN` trên bảng có `status` trùng tên | Mất một số hàng | Nối thêm theo status | Dùng `ON`/`USING` liệt kê đúng khóa |
| Thêm cột trùng tên sau migration | Query cũ trả kết quả khác | NATURAL tự đổi điều kiện | Tránh NATURAL trong code bền vững |
| Không có cột chung với NATURAL | Số hàng tăng mạnh | Tích Descartes | Chỉ định `ON`/`USING` hoặc CROSS có chủ đích |
| `SELECT *` với ON | Hai cột ID cùng tên | ON không gộp output | SELECT cột tường minh và alias |
| `SELECT *` với USING | Một cột khóa thay vì hai | USING gộp khóa | Nắm hợp đồng output |
| `SELECT status` sau USING(team_id) | Ambiguous column | Hai bảng vẫn có status | `m.status` và `t.status` |
| `USING (status)` không đúng khóa | Sai cặp hàng | Tên chung không mang quan hệ | Dùng khóa ngoại thật |
| JOIN bỏ Phúc không có team | Thiếu hàng 106 | INNER JOIN không giữ hàng không khớp | LEFT JOIN nếu cần mọi member |
| LEFT JOIN nhưng WHERE cột phải | Hàng không khớp biến mất | WHERE loại NULL | Đặt điều kiện vào ON khi cần giữ trái |
| FULL JOIN dùng khóa chỉ từ một phía | Mất khóa ở hàng chỉ có bên kia | Hai cột khóa riêng | USING hoặc COALESCE hai phía |
| JOIN thiếu tenant_id | Ghép hóa đơn tenant khác | Thiếu một phần khóa ghép | ON hai cột / USING hai cột |
| JOIN trả nhiều hàng hơn mong đợi | Đếm và tổng bị nhân | Quan hệ một-nhiều hoặc khóa không duy nhất | Xem cardinality, khóa và phép tổng hợp |
| COUNT(*) ở LEFT JOIN nhóm rỗng = 1 | Số lượng sai | Hàng NULL-extended vẫn là một hàng | `COUNT(right.pk)` |
| Hai khóa NULL không khớp | Không có cặp dự kiến | `NULL = NULL` là UNKNOWN | Kiểm tra nghiệp vụ; chỉ dùng null-safe ON khi đúng |
| Tạo index rồi plan vẫn Seq Scan | Tưởng index không hiệu quả | Bảng quá nhỏ, cost model | Đo dữ liệu thực, EXPLAIN |
| Nối bằng tên hiển thị | Có thể ghép nhầm người | Tên không phải khóa duy nhất | JOIN bằng ID/foreign key |
| Dùng DISTINCT để che nhân đôi | Tổng có thể vẫn sai | JOIN sai nghĩa | Sửa điều kiện JOIN trước |

## 25. Bài tập thực hành có đáp án

Dùng hai bảng `join_lab.members` và `join_lab.teams` đã tạo ở phần đầu. Những bài về khóa ghép dùng thêm `join_lab.invoices` và `join_lab.invoice_lines`.

### Bài 1. Nối thành viên với tên nhóm bằng `ON`

Viết truy vấn lấy `member_id`, `member_name` và `team_name` của các thành viên có nhóm.

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
ORDER BY m.member_id;
```

**Đáp án:** `101, 102, 103, 104, 105, 107`. Phúc (106) chưa có nhóm nên không khớp INNER JOIN.

### Bài 2. Viết lại bằng `USING`

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id)
ORDER BY m.member_id;
```

**Đáp án:** cùng sáu thành viên như Bài 1 vì cả hai đều nối theo `team_id`.

### Bài 3. Vì sao `NATURAL JOIN` chỉ còn bốn thành viên?

```sql
SELECT
    member_id,
    member_name,
    team_name
FROM join_lab.members
NATURAL JOIN join_lab.teams
ORDER BY member_id;
```

**Đáp án:** vì hai bảng có chung cả `team_id` và `status`. `NATURAL JOIN` tự yêu cầu cùng cả hai giá trị, loại Bình (102) và Dung (104). Kết quả `101, 103, 105, 107`.

### Bài 4. Chỉ định rõ cả hai điều kiện bằng `ON`

Viết biểu thức nối tương đương với NATURAL JOIN ở schema hiện tại.

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
   AND m.status = t.status
ORDER BY m.member_id;
```

**Đáp án:** cũng cho `101, 103, 105, 107`. Nhưng không có nghĩa điều kiện bổ sung này đúng nghiệp vụ.

### Bài 5. `SELECT *` có mấy cột `team_id`?

```sql
SELECT *
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    ON m.team_id = t.team_id;
```

```sql
SELECT *
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);
```

**Đáp án:** câu đầu có **hai cột `team_id`** trong kết quả, câu sau có **một cột `team_id`**. Hai bảng vẫn có `status` riêng; `USING(team_id)` không gộp chúng.

### Bài 6. Xử lý cột `status` bị mơ hồ

Truy vấn sau có vấn đề gì?

```sql
SELECT status
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);
```

**Đáp án:** `status` tồn tại trong cả hai bảng và không nằm trong danh sách `USING`, nên tham chiếu không định danh là mơ hồ. Sửa bằng `m.status AS member_status` và `t.status AS team_status`.

### Bài 7. Lấy mọi thành viên kể cả người chưa có nhóm

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
LEFT JOIN join_lab.teams AS t
    USING (team_id)
ORDER BY m.member_id;
```

**Đáp án:** đủ bảy thành viên. Phúc có `team_name = NULL`.

### Bài 8. Giữ mọi thành viên, chỉ hiển thị nhóm ACTIVE nếu có

```sql
SELECT
    m.member_id,
    m.member_name,
    t.team_name
FROM join_lab.members AS m
LEFT JOIN join_lab.teams AS t
    ON m.team_id = t.team_id
   AND t.status = 'ACTIVE'
ORDER BY m.member_id;
```

**Đáp án:** vẫn có bảy hàng thành viên; nhóm của Dung và Em không khớp do Archive INACTIVE nên `team_name` là NULL; Phúc cũng không có nhóm.

### Bài 9. Tìm nhóm chưa có thành viên

```sql
SELECT
    t.team_id,
    t.team_name
FROM join_lab.teams AS t
LEFT JOIN join_lab.members AS m
    USING (team_id)
WHERE m.member_id IS NULL
ORDER BY t.team_id;
```

**Đáp án:** nhóm Support, mã 40.

### Bài 10. Đếm số thành viên mỗi nhóm, kể cả nhóm rỗng

```sql
SELECT
    t.team_id,
    t.team_name,
    COUNT(m.member_id) AS member_count
FROM join_lab.teams AS t
LEFT JOIN join_lab.members AS m
    USING (team_id)
GROUP BY t.team_id, t.team_name
ORDER BY t.team_id;
```

**Đáp án:** Core 2, Analytics 2, Archive 2, Support 0. Dùng `COUNT(m.member_id)` thay cho `COUNT(*)` để nhóm không thành viên có 0.

### Bài 11. JOIN hóa đơn đa tenant bằng khóa ghép

```sql
SELECT
    tenant_id,
    invoice_id,
    l.line_no,
    l.quantity
FROM join_lab.invoice_lines AS l
JOIN join_lab.invoices AS i
    USING (tenant_id, invoice_id)
ORDER BY tenant_id, invoice_id, l.line_no;
```

**Đáp án:** ba hàng, không có cặp invoice của tenant khác. Nếu chỉ nối `invoice_id`, giá trị 500 trùng ở tenant 1 và 2 gây nhân đôi sai.

### Bài 12. `NATURAL JOIN` không có cột chung

Hai bảng có 4 và 5 hàng, không có tên cột nào chung. `NATURAL JOIN` dự kiến có bao nhiêu hàng?

**Đáp án:** `4 × 5 = 20`, vì điều kiện tự suy ra rỗng dẫn đến tích Descartes giống CROSS JOIN.

### Bài 13. Thêm `status` vào hai bảng trước đó chỉ có chung `id`

Điều gì xảy ra với truy vấn `NATURAL JOIN` đang chạy?

**Đáp án:** PostgreSQL bắt đầu so sánh cả `id` và `status`. Những cặp cùng id nhưng khác status có thể biến mất. Truy vấn có thể vẫn chạy, khiến lỗi khó phát hiện.

### Bài 14. Hai khóa NULL có khớp với `USING` không?

```sql
WITH
a(k) AS (VALUES (NULL::integer)),
b(k) AS (VALUES (NULL::integer))
SELECT *
FROM a JOIN b USING (k);
```

**Đáp án:** không có hàng. `NULL = NULL` là UNKNOWN, không phải TRUE.

### Bài 15. Muốn NULL khớp NULL phải dùng gì?

```sql
WITH
a(k) AS (VALUES (NULL::integer)),
b(k) AS (VALUES (NULL::integer))
SELECT a.k, b.k
FROM a
JOIN b
    ON a.k IS NOT DISTINCT FROM b.k;
```

**Đáp án:** truy vấn tạo một cặp hàng NULL–NULL. Chỉ áp dụng khi nghiệp vụ thật sự coi hai NULL là tương đương về khóa.

### Bài 16. Vì sao NATURAL LEFT JOIN có thể trả đủ thành viên nhưng thiếu tên nhóm?

**Đáp án:** outer join vẫn giữ hàng bên trái, nhưng NATURAL tự nối thêm các cột trùng tên, như `status`. Khi trạng thái khác nhau, phần dữ liệu nhóm không khớp và trở thành NULL.

### Bài 17. `FULL JOIN ... USING` gộp khóa thế nào?

```sql
WITH
a(k, v) AS (VALUES (1, 'A1'), (2, 'A2')),
b(k, w) AS (VALUES (2, 'B2'), (3, 'B3'))
SELECT k, v, w
FROM a FULL JOIN b USING (k)
ORDER BY k;
```

**Đáp án:** kết quả có khóa 1, 2, 3; khóa 1 chỉ có `v`, khóa 3 chỉ có `w`, khóa 2 có cả hai. Cột `k` là khóa được gộp, tương tự `COALESCE(a.k,b.k)` trong trường hợp này.

### Bài 18. Dùng `WHERE` hay `ON` để lọc team ACTIVE trong LEFT JOIN?

Yêu cầu: “mọi thành viên, nhưng chỉ ghép thông tin nhóm ACTIVE”.

**Đáp án:** đặt `t.status = 'ACTIVE'` **trong `ON`**. Nếu đặt vào `WHERE`, các thành viên không khớp hoặc thuộc nhóm INACTIVE có thể bị loại.

### Bài 19. `JOIN ... USING` có nhanh hơn `JOIN ... ON` không?

**Đáp án:** khi cùng tạo điều kiện equijoin, PostgreSQL thường tối ưu tương đương. Tốc độ phụ thuộc chỉ mục, dữ liệu, thống kê, số hàng và kế hoạch thực thi; cú pháp ngắn hơn không tự nhanh hơn.

### Bài 20. Lỗi “column reference is ambiguous” sau JOIN

```sql
SELECT team_id, status
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);
```

**Đáp án:** `team_id` đã được gộp theo USING, còn `status` vẫn có hai cột. Sửa:

```sql
SELECT
    team_id,
    m.status AS member_status,
    t.status AS team_status
FROM join_lab.members AS m
JOIN join_lab.teams AS t
    USING (team_id);
```

### Bài 21. Phát hiện lỗi JOIN nhân hàng

Một bảng invoice có hai tenant cùng mã 500. Query JOIN lines với invoices chỉ theo invoice_id khiến một dòng xuất hiện hai lần.

**Đáp án:** điều kiện thiếu `tenant_id`. Viết `ON l.tenant_id = i.tenant_id AND l.invoice_id = i.invoice_id` hoặc `USING (tenant_id, invoice_id)`.

### Bài 22. Có nên dùng `SELECT DISTINCT` để sửa NATURAL JOIN thiếu hàng?

**Đáp án:** không. `DISTINCT` loại các hàng trùng trong kết quả; nó không khôi phục những hàng bị NATURAL JOIN loại vì điều kiện ghép sai. Phải viết lại điều kiện JOIN.

## 26. Checklist review SQL có JOIN

Trước khi chấp nhận một câu JOIN vào ứng dụng, hãy xác nhận:

| Câu hỏi | Vì sao phải kiểm tra? |
| --- | --- |
| Hai bảng liên quan bằng khóa nào? | Không dùng tên cột trùng làm suy luận nghiệp vụ |
| Khóa có một hay nhiều cột? | Tránh JOIN thiếu khóa tenant/composite |
| Tên cột ở hai phía có giống nhau? | Quyết định nên dùng `USING` hay `ON` |
| Có dùng `NATURAL JOIN` không? | Rủi ro tự thêm/bỏ điều kiện khi schema đổi |
| Có những cột trùng tên không phải khóa? | Nhất là `status`, `type`, `created_at` |
| Khóa có thể NULL không? | `=` không ghép hai NULL |
| Cần giữ hàng không khớp bên nào? | Chọn INNER/LEFT/RIGHT/FULL đúng |
| Điều kiện lọc phía phải outer join đặt ở đâu? | `WHERE` có thể xóa hàng NULL-extended |
| Mỗi khóa có bao nhiêu hàng ở phía kia? | Dự đoán cardinality, tránh nhân hàng |
| `SELECT *` có thể gây trùng hoặc gộp cột? | Giữ hợp đồng API/serialization ổn định |
| Có yêu cầu xem khóa từng bên trong FULL JOIN? | `ON` + alias có thể rõ hơn USING |
| Có index trên khóa ngoại cần thiết không? | FK không tự tạo index ở phía tham chiếu |
| Truy vấn được chạy trên dữ liệu lớn chưa? | Kiểm tra EXPLAIN và đo thực tế |
| Migration có thể thêm cột trùng tên không? | Tránh schema drift, đặc biệt NATURAL |
| Kết quả có được kiểm tra bằng ca dữ liệu biên không? | Test hàng không khớp, NULL, trùng khóa, trạng thái khác nhau |

Một truy vấn JOIN tốt không chỉ trả đúng dữ liệu ở bộ mẫu hiện tại, mà còn có **ý nghĩa rõ ràng và ổn định khi dữ liệu tăng, nghiệp vụ phát triển và schema thay đổi**.

## 27. Tổng kết

PostgreSQL có ba cách phổ biến để diễn đạt điều kiện kết hợp dữ liệu:

1. **`JOIN ... ON`** là cách đầy đủ và tường minh nhất. Nó hỗ trợ khóa khác tên, điều kiện nhiều cột, biểu thức phức tạp và so sánh khác phép bằng. Với `SELECT *`, các cột từ cả hai phía được giữ lại, kể cả khi trùng tên.
2. **`JOIN ... USING (col1, col2)`** ngắn gọn khi tên khóa giống nhau. Nó chỉ nối theo **các cột được liệt kê** và gộp mỗi cột khóa chung thành một cột kết quả trong `SELECT *`.
3. **`NATURAL JOIN`** tự sử dụng **tất cả** cột có cùng tên làm điều kiện nối, kể cả những cột không liên quan về nghiệp vụ. Điều này có thể âm thầm thay đổi kết quả khi bảng thêm, đổi tên hoặc bỏ cột.
4. **NATURAL không có cột chung có thể trở thành tích Descartes**, khiến số lượng hàng tăng mạnh ngoài dự kiến.
5. **NATURAL có nhiều cột chung có thể lọc sai**: một tên `status` vô tình giống nhau đủ làm mất hàng hợp lệ hoặc làm phần bảng phải trở thành NULL trong `NATURAL LEFT JOIN`.
6. **`ON` và `USING` có thể cho cùng hàng nhưng khác cấu trúc cột đầu ra**. Vì vậy nên liệt kê cột `SELECT` và đặt alias rõ ràng trong code ứng dụng.
7. **Với outer join, `ON` và `WHERE` không thể hoán đổi tùy tiện**: điều kiện `WHERE` trên bảng phải có thể loại những hàng mà LEFT JOIN cần giữ.
8. **Khóa ghép phải JOIN đủ thành phần**, nhất là khi có `tenant_id` và một mã chỉ duy nhất trong tenant. Không sửa kết quả nhân đôi bằng `DISTINCT` khi điều kiện khóa chưa đúng.
9. **`NULL = NULL` không phải TRUE**, nên `USING` và NATURAL không ghép hai khóa NULL với nhau; chỉ dùng điều kiện null-safe trong `ON` khi nghiệp vụ yêu cầu rõ.
10. **Hiệu năng đến từ điều kiện đúng, index và kế hoạch phù hợp**, không phải từ việc chọn cú pháp ngắn nhất.

**Quy tắc dễ nhớ:** nếu điều kiện quan hệ cần được hiểu và bảo trì qua nhiều năm, **viết rõ nó bằng `ON`**; nếu hai bảng có đúng tên khóa chung và muốn output gọn, **dùng `USING`**; **tránh `NATURAL JOIN`** vì tên cột không phải hợp đồng thể hiện quan hệ nghiệp vụ.
