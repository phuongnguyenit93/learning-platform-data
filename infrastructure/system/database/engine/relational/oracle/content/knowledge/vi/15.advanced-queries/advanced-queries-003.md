# Phát hiện vòng lặp bằng NOCYCLE và CONNECT_BY_ISCYCLE trong Oracle Database
Oracle Database hỗ trợ truy vấn phân cấp (*hierarchical query*) để duyệt dữ liệu cha–con như sơ đồ nhân viên–quản lý, danh mục nhiều cấp, cây thư mục hoặc cấu trúc tổ chức. Một vấn đề nguy hiểm là **vòng lặp (cycle/loop)**: đi theo quan hệ cha–con rồi quay lại một hàng đã xuất hiện trước đó trên cùng đường đi.

Ví dụ, Alice quản lý Bob, Bob quản lý Carol, nhưng Carol lại được khai báo là quản lý của Alice. Đường đi Alice → Bob → Carol → Alice tạo thành chu trình. Nếu truy vấn phân cấp tiếp tục duyệt, Oracle có thể báo lỗi:

```text
ORA-01436: CONNECT BY loop in user data
```

Oracle cung cấp hai thành phần để xử lý:
- **`NOCYCLE`** cho phép truy vấn trả về các hàng dù dữ liệu có vòng lặp, đồng thời ngăn một nhánh tiếp tục mở rộng qua cạnh làm khép vòng.
- **`CONNECT_BY_ISCYCLE`** là pseudocolumn trả về 1 nếu hàng hiện tại có một hàng con đã xuất hiện trong đường đi tổ tiên; ngược lại trả về 0. Pseudocolumn này chỉ hợp lệ khi `NOCYCLE` được chỉ định trong `CONNECT BY`.

`NOCYCLE` giúp truy vấn không dừng vì lỗi vòng lặp; `CONNECT_BY_ISCYCLE` giúp xác định vị trí cần điều tra. **Hai thành phần này không sửa dữ liệu** và không bảo đảm toàn bộ mô hình phân cấp đã hợp lệ.

## 1. Vòng lặp trong dữ liệu phân cấp

### 1.1. Cấu trúc cha–con bình thường

Một bảng nhân viên có thể lưu mã người quản lý trong mỗi hàng:

```text
EMP_ID  EMP_NAME  MANAGER_ID
------  --------  ----------
1       Alice     NULL
2       Bob       1
3       Carol     1
4       David     2
```

Sơ đồ:

```text
             Alice (1)
             /      \
          Bob (2)  Carol (3)
            |
         David (4)
```

Alice là nút gốc; Bob và Carol là cấp dưới trực tiếp; David báo cáo cho Bob. Đường đi từ quản lý xuống nhân viên không quay lại một hàng đã đi qua.

### 1.2. Vòng lặp gián tiếp

Dữ liệu sai có thể là:

| EMP_ID | EMP_NAME | MANAGER_ID |
| ---: | --- | ---: |
| 1 | Alice | 3 |
| 2 | Bob | 1 |
| 3 | Carol | 2 |

Khi duyệt từ quản lý xuống cấp dưới:

```text
Alice (1)
   |
   v
Bob (2)
   |
   v
Carol (3)
   |
   +----------> Alice (1)
```

Chu trình gồm ba hàng. Vòng lặp cũng có thể chỉ gồm một hàng tự tham chiếu hoặc nhiều hàng hơn.

Phân biệt:
- **Self-loop:** hàng A trỏ về chính A.
- **Cycle nhiều nút:** A → B → C → A.
- **Nhiều nhánh:** một nút được tiếp cận từ các nhánh khác nhau; điều đó không tự động là cycle.
- **Dữ liệu mồ côi:** khóa cha được tham chiếu không tồn tại; đây là lỗi khác với cycle.

### 1.3. Vì sao khóa ngoại không ngăn được cycle?

Một self-referencing foreign key bảo đảm `MANAGER_ID` khác NULL phải trỏ tới một nhân viên tồn tại khi constraint được bật và kiểm tra. Nhưng FK không phân tích đường đi:

```text
1 -> 2 -> 3 -> 1
```

Mọi mã quản lý trong chu trình đều có thể tồn tại, vì vậy FK vẫn hợp lệ. Muốn bảo đảm cấu trúc không có chu trình cần logic kiểm tra phân cấp hoặc quy trình nghiệp vụ riêng.

## 2. Cú pháp hierarchical query và NOCYCLE

### 2.1. Cấu trúc tổng quát

```sql
SELECT ...
FROM   table_name
[WHERE row_filter]
[START WITH root_condition]
CONNECT BY [NOCYCLE] parent_child_condition
[ORDER SIBLINGS BY sort_expression];
```

- `START WITH` chọn hàng bắt đầu (root hoặc seed).
- `CONNECT BY` mô tả quan hệ giữa hàng hiện tại và hàng kế tiếp.
- `PRIOR` chỉ định biểu thức lấy từ hàng cha ở bước trước.
- `NOCYCLE` cho phép phát hiện và dừng nhánh gây lặp.
- `ORDER SIBLINGS BY` sắp xếp các hàng cùng cấp dưới một cha mà vẫn giữ thứ tự phân cấp.

### 2.2. Duyệt từ quản lý xuống nhân viên

```sql
SELECT emp_id,
       emp_name,
       manager_id,
       LEVEL AS hierarchy_level
FROM   employees
START WITH manager_id IS NULL
CONNECT BY PRIOR emp_id = manager_id;
```

Điều kiện `PRIOR emp_id = manager_id` có nghĩa: mã nhân viên ở hàng cha bằng mã quản lý ở hàng con. Oracle tìm những nhân viên có `MANAGER_ID` bằng `EMP_ID` của hàng hiện tại.

### 2.3. Duyệt từ nhân viên lên người quản lý

```sql
SELECT emp_id,
       emp_name,
       manager_id,
       LEVEL AS hierarchy_level
FROM   employees
START WITH emp_id = :employee_id
CONNECT BY PRIOR manager_id = emp_id;
```

Ở đây truy vấn đi theo chiều ngược lại: lấy manager_id của hàng hiện tại rồi tìm hàng có emp_id tương ứng. Chiều duyệt làm thay đổi tổ tiên trên đường đi và có thể làm thay đổi hàng được đánh dấu cycle.

### 2.4. Thêm NOCYCLE

```sql
SELECT emp_id,
       emp_name,
       manager_id,
       LEVEL AS hierarchy_level
FROM   employees
START WITH emp_id = :start_employee
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;
```

`NOCYCLE` được đặt ngay sau `CONNECT BY`. Nó cho phép Oracle trả về phần phân cấp có thể duyệt được mà không tiếp tục lặp trên một đường đi đã gặp chu trình. Nó chỉ điều khiển truy vấn, không cập nhật `MANAGER_ID`, xóa hàng hay sửa quan hệ cha–con.

## 3. CONNECT_BY_ISCYCLE

### 3.1. Cú pháp và ý nghĩa

`CONNECT_BY_ISCYCLE` là pseudocolumn, không có tham số:

```sql
SELECT emp_id,
       emp_name,
       LEVEL AS hierarchy_level,
       CONNECT_BY_ISCYCLE AS cycle_flag
FROM   employees
START WITH emp_id = :start_employee
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;
```

| CYCLE_FLAG | Ý nghĩa |
| ---: | --- |
| 0 | Hàng hiện tại không có hàng con là tổ tiên trên đường đi |
| 1 | Hàng hiện tại có ít nhất một hàng con đã xuất hiện trong đường đi tổ tiên; đi tiếp sẽ tạo cycle |

**Pseudocolumn này yêu cầu `NOCYCLE` trong mệnh đề `CONNECT BY`.** Không dùng `CONNECT_BY_ISCYCLE` trong một hierarchical query không có `NOCYCLE`.

### 3.2. Hàng nào được đánh dấu?

Giả sử đường đi đang duyệt là:

```text
1 -> 2 -> 3
```

Hàng 3 có một hàng con là 1. Nhưng 1 đã là tổ tiên của 3 trong đường đi hiện tại. Do đó hàng 3 được đánh dấu `CONNECT_BY_ISCYCLE=1`. Oracle không cần trả hàng 1 thêm lần nữa để báo vòng lặp.

Điểm cần nhớ:
- Hàng được đánh dấu là **hàng hiện tại ngay trước cạnh khép vòng**.
- Hàng tổ tiên bị lặp lại không được đưa vào nhánh như một lần xuất hiện mới.
- Cycle được xét theo đường đi hiện tại, không đơn giản là một ID từng xuất hiện ở bất kỳ nhánh nào.

### 3.3. NOCYCLE và CONNECT_BY_ISCYCLE phối hợp

`NOCYCLE` cho phép hierarchical query tiếp tục và dừng nhánh ở điểm lặp; `CONNECT_BY_ISCYCLE` cung cấp cờ để nhận biết hàng hiện tại có cạnh con quay về tổ tiên. Kết hợp chúng giúp truy vấn vừa trả dữ liệu hữu ích vừa cho biết nơi cần kiểm tra.


## 4. Thực hành: tạo dữ liệu có cycle

### 4.1. Tạo bảng tự tham chiếu

Tạo bảng demo riêng trong schema học tập:

```sql
CREATE TABLE demo_org_employees (
    emp_id     NUMBER(10) PRIMARY KEY,
    emp_name   VARCHAR2(100) NOT NULL,
    manager_id NUMBER(10),
    CONSTRAINT fk_demo_org_manager
        FOREIGN KEY (manager_id)
        REFERENCES demo_org_employees(emp_id)
);
```

FK tự tham chiếu cho phép manager NULL, nhưng manager khác NULL phải tồn tại. FK không kiểm tra chu trình nhiều hàng.

### 4.2. Thêm các hàng trước, sau đó tạo quan hệ

Thêm các hàng với manager NULL trước để đáp ứng FK:

```sql
INSERT INTO demo_org_employees VALUES (1, 'Alice', NULL);
INSERT INTO demo_org_employees VALUES (2, 'Bob',   NULL);
INSERT INTO demo_org_employees VALUES (3, 'Carol', NULL);
INSERT INTO demo_org_employees VALUES (4, 'David', NULL);
COMMIT;
```

Sau đó cập nhật quan hệ:

```sql
UPDATE demo_org_employees SET manager_id = 3 WHERE emp_id = 1;
UPDATE demo_org_employees SET manager_id = 1 WHERE emp_id = 2;
UPDATE demo_org_employees SET manager_id = 2 WHERE emp_id = 3;
UPDATE demo_org_employees SET manager_id = 1 WHERE emp_id = 4;
COMMIT;
```

Bảng lúc này:

| EMP_ID | EMP_NAME | MANAGER_ID |
| ---: | --- | ---: |
| 1 | Alice | 3 |
| 2 | Bob | 1 |
| 3 | Carol | 2 |
| 4 | David | 1 |

Alice, Bob và Carol tạo thành chu trình; David là cấp dưới của Alice.

### 4.3. Truy vấn không có NOCYCLE

Trong môi trường demo, chạy:

```sql
SELECT emp_id,
       emp_name,
       manager_id,
       LEVEL AS hierarchy_level
FROM   demo_org_employees
START WITH emp_id = 1
CONNECT BY PRIOR emp_id = manager_id;
```

Đường đi Alice → Bob → Carol → Alice tạo loop. Oracle có thể báo:

```text
ORA-01436: CONNECT BY loop in user data
```

### 4.4. Truy vấn có NOCYCLE và CONNECT_BY_ISCYCLE

```sql
SELECT emp_id,
       emp_name,
       manager_id,
       LEVEL AS hierarchy_level,
       CONNECT_BY_ISCYCLE AS cycle_flag,
       SYS_CONNECT_BY_PATH(TO_CHAR(emp_id), '/') AS id_path
FROM   demo_org_employees
START WITH emp_id = 1
CONNECT BY NOCYCLE PRIOR emp_id = manager_id
ORDER SIBLINGS BY emp_id;
```

Kết quả minh họa:

| EMP_ID | EMP_NAME | MANAGER_ID | HIERARCHY_LEVEL | CYCLE_FLAG | ID_PATH |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | Alice | 3 | 1 | 0 | /1 |
| 2 | Bob | 1 | 2 | 0 | /1/2 |
| 3 | Carol | 2 | 3 | 1 | /1/2/3 |
| 4 | David | 1 | 2 | 0 | /1/4 |

Carol có hàng con Alice, mà Alice đã nằm trong path `/1/2/3`; vì vậy Carol có cờ 1. Nhánh David được duyệt riêng và không tạo cycle.

`SYS_CONNECT_BY_PATH` tạo đường dẫn từ root đến hàng hiện tại, hữu ích khi điều tra. Path dài trên bảng lớn có thể làm tăng chi phí và lượng dữ liệu trả về.

### 4.5. Hàng hiện tại và cạnh gây vòng lặp

Trong ví dụ, Carol (3) là hàng được đánh dấu. Cạnh tiếp theo theo điều kiện phân cấp sẽ đi từ Carol về Alice (1). Vì Alice đã là tổ tiên, cạnh Carol → Alice khép vòng.

Không nên hiểu cờ 1 là Carol tự tham chiếu chính nó. Cần kiểm tra các hàng con của Carol và đường dẫn tổ tiên để biết cạnh nào gây loop.


## 5. Truy vết cạnh khép vòng

### 5.1. Lọc các hàng có cycle flag

Đưa hierarchical query vào CTE rồi lọc ở truy vấn ngoài:

```sql
WITH hierarchy_rows AS (
    SELECT emp_id,
           emp_name,
           manager_id,
           LEVEL AS hierarchy_level,
           CONNECT_BY_ISCYCLE AS cycle_flag,
           SYS_CONNECT_BY_PATH(TO_CHAR(emp_id), '/') AS id_path
    FROM   demo_org_employees
    START WITH emp_id = 1
    CONNECT BY NOCYCLE PRIOR emp_id = manager_id
)
SELECT emp_id,
       emp_name,
       manager_id,
       hierarchy_level,
       id_path
FROM   hierarchy_rows
WHERE  cycle_flag = 1;
```

Truy vấn trả về hàng hiện tại có hàng con là tổ tiên trên path. Cách tách CTE giúp phần duyệt cây và phần báo cáo dễ đọc hơn.

### 5.2. Tìm hàng con là tổ tiên

Với khóa ID là số nguyên và dấu / không xuất hiện trong ID, có thể dùng path để xác định cạnh khép vòng:

```sql
WITH hierarchy_rows AS (
    SELECT emp_id,
           emp_name,
           manager_id,
           CONNECT_BY_ISCYCLE AS cycle_flag,
           SYS_CONNECT_BY_PATH(TO_CHAR(emp_id), '/') AS id_path
    FROM   demo_org_employees
    START WITH emp_id = 1
    CONNECT BY NOCYCLE PRIOR emp_id = manager_id
)
SELECT h.emp_id AS current_employee,
       h.emp_name AS current_name,
       child.emp_id AS ancestor_employee,
       child.emp_name AS ancestor_name,
       h.id_path
FROM   hierarchy_rows h
JOIN   demo_org_employees child
       ON child.manager_id = h.emp_id
WHERE  h.cycle_flag = 1
AND    INSTR(
         h.id_path || '/',
         '/' || TO_CHAR(child.emp_id) || '/'
       ) > 0;
```

Kết quả:

| CURRENT_EMPLOYEE | CURRENT_NAME | ANCESTOR_EMPLOYEE | ANCESTOR_NAME | ID_PATH |
| ---: | --- | ---: | --- | --- |
| 3 | Carol | 1 | Alice | /1/2/3 |

Điều kiện `INSTR` kiểm tra ID của hàng con có xuất hiện trong path hay không. Dấu `/` ở hai phía giúp tránh nhầm ID 1 với ID 11. Đây là truy vấn minh họa cho khóa số; nếu khóa là chuỗi có thể chứa delimiter, phải mã hóa hoặc chọn cách so sánh phù hợp.

### 5.3. Dùng CONNECT_BY_ROOT

`CONNECT_BY_ROOT expression` trả về giá trị của biểu thức tại hàng gốc của đường đi:

```sql
SELECT CONNECT_BY_ROOT emp_id AS root_emp_id,
       emp_id,
       emp_name,
       LEVEL AS hierarchy_level,
       CONNECT_BY_ISCYCLE AS cycle_flag
FROM   demo_org_employees
START WITH emp_id = 1
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;
```

Khi truy vấn có nhiều seed, pseudocolumn này giúp xác định mỗi hàng thuộc đường đi bắt đầu từ root nào.

### 5.4. Cycle flag không phải danh sách mọi lỗi trong bảng

`CONNECT_BY_ISCYCLE` chỉ nhận biết hàng con đã là tổ tiên trên đường đi đang duyệt. Nó không tự liệt kê mọi chu trình trong schema, các thành phần không thể đi tới từ START WITH, mọi cạnh sai, mọi dữ liệu mồ côi hoặc các hàng trùng xuất hiện ở những path khác nhau.

Phải xác định phạm vi seed và hướng duyệt trước khi kết luận kết quả đã bao phủ toàn bộ dữ liệu.

## 6. START WITH và phạm vi phát hiện

### 6.1. Chỉ duyệt các nhánh đi tới từ seed

Truy vấn:

```sql
SELECT emp_id,
       emp_name,
       CONNECT_BY_ISCYCLE AS cycle_flag
FROM   demo_org_employees
START WITH manager_id IS NULL
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;
```

Dữ liệu demo sau khi tạo cycle không còn hàng nào có `MANAGER_ID IS NULL`, nên truy vấn có thể trả 0 hàng. Điều đó **không chứng minh bảng không có cycle**; không có seed nào thỏa START WITH để bắt đầu duyệt.

Nếu biết một hàng thuộc thành phần lỗi, có thể dùng nó làm seed bằng điều kiện `START WITH emp_id = 1`.

### 6.2. Không có START WITH

Khi bỏ `START WITH`, Oracle xem tất cả hàng là root của hierarchical query. Cách này có thể giúp điều tra những thành phần không có root tự nhiên:

```sql
SELECT emp_id,
       LEVEL AS hierarchy_level,
       CONNECT_BY_ISCYCLE AS cycle_flag,
       SYS_CONNECT_BY_PATH(TO_CHAR(emp_id), '/') AS id_path
FROM   demo_org_employees
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;
```

Truy vấn có thể tạo nhiều path từ nhiều điểm bắt đầu và lặp lại các hàng trong những đường đi khác nhau. Chỉ dùng trên phạm vi dữ liệu kiểm soát; không xem đây là truy vấn báo cáo thông thường cho bảng lớn.

### 6.3. Chiều duyệt thay đổi kết quả

Duyệt từ quản lý xuống nhân viên:

```sql
CONNECT BY NOCYCLE PRIOR emp_id = manager_id
```

Duyệt từ nhân viên lên quản lý:

```sql
CONNECT BY NOCYCLE PRIOR manager_id = emp_id
```

Tổ tiên trên mỗi đường đi khác nhau, do đó hàng có `CONNECT_BY_ISCYCLE=1` cũng có thể khác. Luôn đọc điều kiện PRIOR để hiểu chiều duyệt.

### 6.4. Vị trí WHERE trong hierarchical query

Oracle xử lý join trước, sau đó xác định hierarchy bằng START WITH/CONNECT BY, rồi áp dụng điều kiện WHERE theo quy tắc hierarchical query. WHERE không nhất thiết cắt cả nhánh trước khi cây được tạo.

Nếu một điều kiện quyết định hàng nào được phép tham gia vào quan hệ cha–con, hãy cân nhắc đặt điều kiện trong `CONNECT BY` hoặc lọc nguồn bằng inline view trước khi duyệt. Không giả định WHERE luôn ngăn Oracle đi xuyên qua một hàng bị lọc.


## 7. Cycle khác các vấn đề dữ liệu khác

| Trường hợp | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Self-loop | A trỏ manager về A | Một hàng tự tham chiếu |
| Cycle nhiều nút | A → B → C → A | Đường đi quay lại tổ tiên |
| Dữ liệu mồ côi | manager_id trỏ đến ID không tồn tại | Tham chiếu không hợp lệ |
| Nhiều hàng con | Một manager có 20 nhân viên | Quan hệ 1:N bình thường |
| Nhiều path | Một nút có thể đến từ các nhánh khác nhau | Không nhất thiết là cycle |

Self-referencing FK có thể ngăn dữ liệu mồ côi nhưng không ngăn cycle nhiều nút. Một nút được tiếp cận từ hai nhánh khác nhau không tự động là cycle; phải trùng với tổ tiên trên cùng đường đi.

## 8. Sửa dữ liệu sau khi phát hiện cycle

### 8.1. Xác minh trước khi cập nhật

Không xóa hàng có cycle flag chỉ vì nó được đánh dấu. Hàng đó có thể là nhân viên hợp lệ; quan hệ manager hoặc cạnh từ một hàng con mới là dữ liệu sai.

Quy trình:
1. Lưu lại đường đi và các hàng liên quan.
2. Xác định cạnh khép vòng.
3. Xác minh quan hệ đúng với chủ sở hữu nghiệp vụ.
4. Sửa đúng quan hệ sai trong transaction được kiểm soát.
5. Chạy lại truy vấn phân cấp trên phạm vi phù hợp.
6. Xác nhận không còn cycle và dữ liệu vẫn đúng nghiệp vụ.

### 8.2. Sửa dữ liệu demo

Nếu quy tắc nghiệp vụ xác nhận Alice phải là root, có thể đặt manager của Alice về NULL:

```sql
UPDATE demo_org_employees
SET manager_id = NULL
WHERE emp_id = 1;

COMMIT;
```

Cây sau khi sửa:

```text
Alice (1)
  |
  +---- Bob (2)
  |       |
  |       +---- Carol (3)
  |
  +---- David (4)
```

Đây chỉ là phương án đúng theo giả định Alice là root. Trong hệ thống thật, người có thẩm quyền phải xác nhận quan hệ đúng; không tự đặt NULL chỉ để truy vấn hết lỗi.

### 8.3. Kiểm tra lại

```sql
SELECT emp_id,
       emp_name,
       manager_id,
       LEVEL AS hierarchy_level,
       CONNECT_BY_ISCYCLE AS cycle_flag,
       SYS_CONNECT_BY_PATH(TO_CHAR(emp_id), '/') AS id_path
FROM   demo_org_employees
START WITH manager_id IS NULL
CONNECT BY NOCYCLE PRIOR emp_id = manager_id
ORDER SIBLINGS BY emp_id;
```

Với dữ liệu đã sửa, Alice là root; Bob và David là cấp dưới trực tiếp; Carol là cấp dưới của Bob. Các hàng trong cây này có cycle flag bằng 0. Nếu có thành phần chu trình rời rạc khác, START WITH manager_id IS NULL có thể không tìm thấy nó.

## 9. Ngăn tạo cycle khi đổi manager

### 9.1. Nguyên tắc

Giả sử muốn đổi manager của nhân viên `:emp_id` sang `:new_manager_id`. Thay đổi sẽ tạo cycle nếu manager mới chính là nhân viên đó hoặc nằm trong nhánh cấp dưới của nhân viên đó.

Ví dụ:
- Bob đang là cấp dưới của Alice.
- Không thể đặt Alice báo cáo cho Bob mà vẫn giữ Bob báo cáo cho Alice.
- Việc đó tạo Alice → Bob → Alice.

### 9.2. Tìm nhánh cấp dưới hiện tại

```sql
SELECT emp_id,
       emp_name,
       LEVEL AS hierarchy_level
FROM   demo_org_employees
START WITH emp_id = :emp_id
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;
```

Tập kết quả chứa nhân viên mục tiêu và các cấp dưới có thể đi tới từ nhân viên đó theo quan hệ hiện tại. Nếu `:new_manager_id` xuất hiện trong tập này, việc gán người đó làm manager mới có thể tạo vòng lặp.

Kiểm tra:

```sql
SELECT COUNT(*) AS would_create_cycle
FROM (
    SELECT emp_id
    FROM   demo_org_employees
    START WITH emp_id = :emp_id
    CONNECT BY NOCYCLE PRIOR emp_id = manager_id
) descendants
WHERE descendants.emp_id = :new_manager_id;
```

Count lớn hơn 0 nghĩa là manager mới nằm trong nhánh cấp dưới hiện tại. Đây là kiểm tra logic minh họa; ứng dụng còn cần kiểm tra manager tồn tại, cycle cũ, quyền và thay đổi đồng thời.

### 9.3. Self-reference trực tiếp

Điều kiện `:new_manager_id <> :emp_id` ngăn một nhân viên tự quản lý chính mình, nhưng không ngăn cycle nhiều hàng. Vẫn cần kiểm tra đường đi.

### 9.4. Cẩn trọng với giao dịch đồng thời

Một SELECT kiểm tra trước UPDATE có thể không đủ nếu nhiều session đồng thời thay đổi quan hệ. Hai transaction có thể cùng kiểm tra trên trạng thái cũ, rồi cập nhật tạo ra chu trình mới.

Hệ thống thật cần đồng bộ thao tác thay đổi cây bằng transaction, khóa phù hợp hoặc cơ chế nghiệp vụ đảm bảo tuần tự hóa các thay đổi liên quan. Cách triển khai phụ thuộc schema và mức concurrency.


## 13. Bài thực hành

Các bài tập sử dụng `DEMO_ORG_EMPLOYEES` đã tạo ở phần 4.

### Bài 1 — Duyệt cây sau khi sửa

Sau khi Alice là root:

```sql
SELECT emp_id,
       emp_name,
       manager_id,
       LEVEL AS hierarchy_level
FROM   demo_org_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR emp_id = manager_id
ORDER SIBLINGS BY emp_id;
```

Kỳ vọng: Alice level 1; Bob và David level 2; Carol level 3.

### Bài 2 — Tạo lại cycle

```sql
UPDATE demo_org_employees SET manager_id = 3 WHERE emp_id = 1;
UPDATE demo_org_employees SET manager_id = 1 WHERE emp_id = 2;
UPDATE demo_org_employees SET manager_id = 2 WHERE emp_id = 3;
COMMIT;
```

Chạy truy vấn không NOCYCLE để quan sát ORA-01436, rồi chạy lại với NOCYCLE.

### Bài 3 — Đánh dấu hàng trước cạnh khép vòng

```sql
SELECT emp_id,
       emp_name,
       LEVEL,
       CONNECT_BY_ISCYCLE AS cycle_flag
FROM   demo_org_employees
START WITH emp_id = 1
CONNECT BY NOCYCLE PRIOR emp_id = manager_id
ORDER SIBLINGS BY emp_id;
```

Kỳ vọng: Carol (3) có cycle flag 1.

### Bài 4 — Lọc cycle flag bằng CTE

```sql
WITH h AS (
    SELECT emp_id,
           emp_name,
           manager_id,
           LEVEL AS hierarchy_level,
           CONNECT_BY_ISCYCLE AS cycle_flag,
           SYS_CONNECT_BY_PATH(TO_CHAR(emp_id), '/') AS id_path
    FROM   demo_org_employees
    START WITH emp_id = 1
    CONNECT BY NOCYCLE PRIOR emp_id = manager_id
)
SELECT emp_id,
       emp_name,
       manager_id,
       hierarchy_level,
       id_path
FROM   h
WHERE  cycle_flag = 1;
```

Kỳ vọng: hàng Carol với path `/1/2/3`.

### Bài 5 — Tìm hàng con là tổ tiên

Dùng truy vấn ở mục 5.2. Kỳ vọng cạnh khép vòng là Carol → Alice.

### Bài 6 — Kiểm tra START WITH

```sql
SELECT emp_id,
       CONNECT_BY_ISCYCLE
FROM   demo_org_employees
START WITH manager_id IS NULL
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;
```

Kỳ vọng: không có hàng khi thành phần cycle không có root manager NULL. Kết quả rỗng không chứng minh bảng không có cycle.

### Bài 7 — Điều tra từ mọi seed

Bỏ START WITH và quan sát các path khác nhau. Chỉ chạy trên bảng demo nhỏ vì kết quả có thể lặp lại nhiều đường đi.

### Bài 8 — Sửa cycle

Nếu Alice phải là root:

```sql
UPDATE demo_org_employees
SET manager_id = NULL
WHERE emp_id = 1;
COMMIT;
```

Chạy lại truy vấn từ root và xác nhận cycle flag bằng 0 trong cây đó.

### Bài 9 — Tự tham chiếu

Trong schema demo, thử đặt manager_id bằng chính emp_id, quan sát NOCYCLE, sau đó sửa lại dữ liệu. Không chạy trên bảng nghiệp vụ.

### Bài 10 — Kiểm tra FK

```sql
SELECT constraint_name,
       constraint_type,
       status,
       validated
FROM   user_constraints
WHERE  table_name = 'DEMO_ORG_EMPLOYEES'
ORDER  BY constraint_name;
```

Xác nhận PK và FK tự tham chiếu; giải thích vì sao FK vẫn cho phép cycle nhiều hàng.

## 14. Những nhầm lẫn thường gặp

**“NOCYCLE sửa dữ liệu sai.”** Không. Nó chỉ điều khiển cách truy vấn dừng nhánh gây lặp.

**“CONNECT_BY_ISCYCLE đánh dấu hàng lặp lại.”** Nó đánh dấu hàng hiện tại có một hàng con là tổ tiên trên đường đi.

**“Cycle flag bằng 1 nghĩa là hàng đó tự quản lý chính nó.”** Không. Chu trình có thể gồm nhiều hàng.

**“Có self-referencing FK thì không thể có cycle.”** FK chỉ bảo đảm khóa cha tồn tại; nó không kiểm tra đường đi.

**“START WITH manager_id IS NULL không trả hàng nghĩa là không có cycle.”** Không. Thành phần cycle có thể không có root tự nhiên.

**“NOCYCLE loại bỏ mọi dòng trùng.”** Không. Nó ngăn lặp trên cùng path, không loại các path khác nhau.

**“CONNECT_BY_ISCYCLE dùng được không cần NOCYCLE.”** Không. Pseudocolumn này yêu cầu NOCYCLE.

**“DISTINCT có thể sửa lỗi ORA-01436.”** Không. DISTINCT không thay thế NOCYCLE và không sửa quan hệ.

**“Chiều duyệt không ảnh hưởng hàng được đánh dấu.”** Không đúng. Hướng PRIOR và seed xác định đường đi tổ tiên.

**“WHERE luôn lọc trước CONNECT BY.”** Không nên giả định vậy; hierarchical query có thứ tự xử lý riêng.

## 15. Câu hỏi tự kiểm tra

1. Cycle trong dữ liệu phân cấp là gì?
2. Self-loop khác cycle nhiều hàng thế nào?
3. `CONNECT BY PRIOR emp_id = manager_id` duyệt theo hướng nào?
4. NOCYCLE có thay đổi dữ liệu trong bảng không?
5. CONNECT_BY_ISCYCLE=1 đánh dấu hàng hiện tại hay hàng tổ tiên được lặp?
6. Vì sao pseudocolumn này yêu cầu NOCYCLE?
7. Với đường đi 1 → 2 → 3 → 1, hàng nào được đánh dấu khi duyệt từ 1 xuống?
8. START WITH manager_id IS NULL có thể bỏ sót trường hợp nào?
9. Nếu bỏ START WITH, Oracle xem các hàng như thế nào?
10. Vì sao NOCYCLE không tương đương DISTINCT?
11. FK tự tham chiếu bảo vệ điều gì và không bảo vệ điều gì?
12. SYS_CONNECT_BY_PATH hỗ trợ điều tra như thế nào?
13. Làm sao xác định hàng con khép vòng từ hàng cycle flag?
14. Đổi chiều duyệt có thể đổi hàng được đánh dấu không?
15. Vì sao không nên sửa manager_id chỉ dựa vào hàng được đánh dấu?
16. Vì sao kiểm tra trước UPDATE cần tính đến transaction đồng thời?
17. Cycle khác dữ liệu mồ côi như thế nào?
18. Một nút xuất hiện ở hai nhánh có luôn là cycle không?
19. ORDER SIBLINGS BY khác ORDER BY ở điểm nào?
20. Sau khi sửa dữ liệu cần kiểm tra lại điều gì?

**Gợi ý đáp án:**

1. Đường đi cha–con quay lại hàng đã xuất hiện trong cùng path.
2. Self-loop là một hàng trỏ về chính nó; cycle nhiều hàng đi qua các hàng trung gian.
3. Từ cha xuống con.
4. Không.
5. Hàng hiện tại có con là tổ tiên.
6. Oracle yêu cầu NOCYCLE khi dùng pseudocolumn.
7. Hàng 3, vì con tiếp theo là 1 đã là tổ tiên.
8. Thành phần chu trình không có hàng nào có manager NULL.
9. Mọi hàng có thể được xem là root.
10. NOCYCLE ngăn lặp trên path; DISTINCT loại hàng trùng theo output.
11. FK bảo đảm khóa cha tồn tại; không bảo đảm đồ thị không có cycle.
12. Tạo đường dẫn từ root đến hàng hiện tại.
13. Join hàng con trực tiếp và kiểm tra ID có xuất hiện trong path không.
14. Có; chiều duyệt làm thay đổi đường đi tổ tiên.
15. Hàng được đánh dấu là nút trước cạnh khép vòng; quan hệ sai cần được xác minh.
16. Hai transaction có thể cùng kiểm tra trên trạng thái cũ rồi tạo cycle khi cập nhật.
17. Cycle quay lại tổ tiên; dữ liệu mồ côi trỏ tới khóa không tồn tại.
18. Không; phải nằm trong cùng đường đi tổ tiên mới là cycle.
19. ORDER SIBLINGS BY sắp xếp anh em trong cây; ORDER BY có thể sắp phẳng kết quả.
20. Kiểm tra toàn bộ phạm vi seed cần thiết, không chỉ một root, và xác nhận quan hệ nghiệp vụ đúng.

## 16. Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — Hierarchical Queries](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Hierarchical-Queries.html): START WITH, CONNECT BY và NOCYCLE.
- [Oracle Database SQL Language Reference — Hierarchical Query Pseudocolumns](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Hierarchical-Query-Pseudocolumns.html): LEVEL, CONNECT_BY_ISCYCLE, CONNECT_BY_ISLEAF và CONNECT_BY_ROOT.
- [Oracle Database SQL Language Reference — SYS_CONNECT_BY_PATH](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SYS_CONNECT_BY_PATH.html): tạo đường dẫn phân cấp.
- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): cú pháp SELECT và hierarchical query.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): mô hình quan hệ, constraint và toàn vẹn dữ liệu.
- [Oracle Database Error Messages](https://docs.oracle.com/en/database/oracle/oracle-database/19/errmg/): tra cứu thông báo lỗi Oracle, bao gồm ORA-01436.

Khi điều tra dữ liệu phân cấp, hãy xác định chiều `PRIOR`, chọn seed phù hợp bằng `START WITH`, thêm `NOCYCLE` để truy vấn không dừng vì loop và dùng `CONNECT_BY_ISCYCLE` để tìm hàng ngay trước cạnh khép vòng. Sau đó truy vết đường đi, xác minh quan hệ đúng với nghiệp vụ và sửa có kiểm soát. **NOCYCLE là công cụ giúp truy vấn và phát hiện vòng lặp; tính toàn vẹn cuối cùng vẫn phải được bảo đảm bằng dữ liệu và quy trình cập nhật đúng.**


## 10. Các pseudocolumn phân cấp liên quan

| Pseudocolumn | Ý nghĩa |
| --- | --- |
| `LEVEL` | Độ sâu của hàng trong cây; root là level 1 |
| `CONNECT_BY_ISCYCLE` | 1 nếu hàng hiện tại có con là tổ tiên; cần NOCYCLE |
| `CONNECT_BY_ISLEAF` | 1 nếu hàng hiện tại là leaf theo điều kiện CONNECT BY |
| `CONNECT_BY_ROOT expression` | Giá trị biểu thức ở hàng root của đường đi |

`SYS_CONNECT_BY_PATH(column, delimiter)` tạo đường dẫn từ root đến hàng hiện tại, hữu ích để điều tra và hiển thị breadcrumb.

`ORDER SIBLINGS BY` sắp xếp các hàng cùng cha mà vẫn giữ cấu trúc cây. `ORDER BY` thông thường có thể sắp phẳng toàn bộ kết quả và làm mất cách trình bày theo nhánh mong muốn.

Không nhầm:
- `CONNECT_BY_ISCYCLE` phát hiện cạnh sẽ quay về tổ tiên.
- `CONNECT_BY_ISLEAF` cho biết hàng có con theo điều kiện CONNECT BY hay không.
- `LEVEL` cho biết độ sâu, không phải số lượng chu trình.

## 11. Hiệu năng và vận hành

### 11.1. NOCYCLE vẫn phải duyệt dữ liệu

`NOCYCLE` không làm hierarchical query miễn phí. Oracle vẫn tìm các hàng con và theo dõi đường đi để phát hiện lặp.

Với mô hình nhân viên, index trên `MANAGER_ID` có thể hỗ trợ tìm cấp dưới khi duyệt từ quản lý xuống. Với khóa ghép, index cần phù hợp với các thành phần trong điều kiện CONNECT BY. Hãy kiểm tra workload, thống kê và execution plan trước khi tạo index.

### 11.2. NOCYCLE không loại duplicate path

Nếu một hàng có thể được tiếp cận qua nhiều đường đi khác nhau, nó vẫn có thể xuất hiện nhiều lần trong kết quả. NOCYCLE chỉ ngăn lặp tổ tiên trên cùng path; nó không phải DISTINCT toàn cục.

Không thêm DISTINCT máy móc để che kết quả nhiều dòng. Trước tiên phải hiểu mô hình quan hệ và cardinality.

### 11.3. Điều kiện CONNECT BY phải đầy đủ

Nếu khóa phân cấp là khóa ghép, cần so khớp đầy đủ các thành phần định danh:

```sql
CONNECT BY NOCYCLE
       PRIOR tenant_id = tenant_id
   AND PRIOR node_code = parent_node_code
```

Đây là khung minh họa; tên cột và chiều quan hệ phải khớp schema thật. Bỏ sót tenant hoặc thành phần khóa có thể nối chéo dữ liệu và tạo đường đi giả.

### 11.4. Xem execution plan

```sql
EXPLAIN PLAN FOR
SELECT emp_id,
       emp_name,
       LEVEL,
       CONNECT_BY_ISCYCLE
FROM   demo_org_employees
START WITH emp_id = 1
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` cho kế hoạch ước lượng. Khi điều tra truy vấn thực tế, cần xem cursor plan và runtime statistics phù hợp. Không suy hiệu năng production từ bảng demo rất nhỏ.

### 11.5. Tránh broad diagnostic tùy tiện

Bỏ `START WITH` hoặc lấy mọi hàng làm root có thể tạo nhiều path và tăng số hàng trung gian. Trên bảng lớn, giới hạn phạm vi theo schema/tenant/đối tượng, dùng seed nghi vấn, theo dõi execution plan và tránh trả path dài nếu chỉ cần cycle flag.

## 12. Quy trình điều tra cycle trong hệ thống thật

1. **Xác định quan hệ:** cột nào định danh nút, cột nào tham chiếu cha, chiều duyệt mong muốn.
2. **Kiểm tra constraint:** FK có ENABLE/VALIDATE không; dữ liệu mồ côi có thể tồn tại không.
3. **Chọn seed:** root hợp lệ, đối tượng báo lỗi hoặc một nút thuộc thành phần nghi vấn.
4. **Chạy với NOCYCLE:** lấy LEVEL và CONNECT_BY_ISCYCLE.
5. **Ghi lại path:** dùng SYS_CONNECT_BY_PATH khi cần truy vết.
6. **Tìm cạnh khép vòng:** kiểm tra hàng con của hàng được đánh dấu có phải tổ tiên trong path không.
7. **Xác minh nghiệp vụ:** xác định quan hệ đúng.
8. **Sửa có kiểm soát:** cập nhật cạnh sai trong transaction/audit phù hợp.
9. **Chạy lại truy vấn:** xác nhận không còn cycle trong phạm vi cần kiểm tra.
10. **Ngăn tái diễn:** kiểm tra trước khi đổi quan hệ và đồng bộ các cập nhật đồng thời.

### 12.1. Xem dữ liệu trước khi sửa

```sql
SELECT emp_id,
       emp_name,
       manager_id
FROM   demo_org_employees
WHERE  emp_id IN (1, 2, 3);
```

Đây là truy vấn đọc. Với dữ liệu thật, lưu lịch sử theo chính sách audit/backup; không chỉ dựa vào kết quả trên màn hình.

### 12.2. Dùng transaction cho DML

```sql
SAVEPOINT before_cycle_fix;

UPDATE demo_org_employees
SET manager_id = NULL
WHERE emp_id = 1;

-- Chạy lại hierarchical query để kiểm tra.

-- Chỉ COMMIT sau khi xác nhận quan hệ đúng.
-- Nếu cần hủy thay đổi demo:
ROLLBACK TO before_cycle_fix;
```

`SAVEPOINT` và `ROLLBACK TO` áp dụng cho DML chưa commit. Không chạy DDL giữa các bước nếu đang dựa vào savepoint vì DDL Oracle có implicit commit.
