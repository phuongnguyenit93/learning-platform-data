# LEVEL, PRIOR, CONNECT_BY_ROOT và SYS_CONNECT_BY_PATH

Trong nhiều hệ thống, dữ liệu có cấu trúc phân cấp: nhân viên báo cáo cho quản lý, danh mục có nhóm cha và nhóm con, tài khoản có tài khoản cấp trên, hoặc một sản phẩm có nhiều cấp phân loại. Dữ liệu thường được lưu trong **một bảng có khóa tự tham chiếu**: mỗi hàng giữ mã của chính nó và mã hàng cha.

Oracle Database hỗ trợ **hierarchical query** để duyệt quan hệ cha-con trực tiếp trong SQL. Bốn thành phần quan trọng là:

- `LEVEL`: cho biết độ sâu của hàng trong cây kết quả.
- `PRIOR`: chỉ ra biểu thức được lấy từ hàng cha ở bước duyệt.
- `CONNECT_BY_ROOT`: lấy giá trị của hàng gốc và hiển thị trên các hàng hậu duệ.
- `SYS_CONNECT_BY_PATH`: tạo chuỗi đường dẫn từ gốc tới hàng hiện tại.

Bài học sử dụng mô hình nhân viên–quản lý để giải thích cách Oracle xây dựng cây, cách chọn hướng duyệt, cách đọc độ sâu và đường dẫn, cũng như xử lý nhiều gốc, chu trình, lọc dữ liệu và thứ tự hiển thị.

## 1. Quan hệ phân cấp được lưu trong một bảng

Giả sử bảng `EMPLOYEES` có cấu trúc:

| Cột | Ý nghĩa |
|---|---|
| `EMPLOYEE_ID` | Mã nhân viên, khóa chính |
| `EMPLOYEE_NAME` | Tên nhân viên |
| `MANAGER_ID` | Mã người quản lý, tham chiếu `EMPLOYEE_ID` của cùng bảng |
| `DEPARTMENT_ID` | Mã phòng ban |
| `STATUS` | Trạng thái nhân viên |

Quan hệ cha-con được biểu diễn như sau:

~~~text
EMPLOYEE_ID = 100  (CEO, MANAGER_ID = NULL)
    |
    +-- EMPLOYEE_ID = 110  (VP, MANAGER_ID = 100)
    |       |
    |       +-- EMPLOYEE_ID = 111  (Manager, MANAGER_ID = 110)
    |       |       |
    |       |       +-- EMPLOYEE_ID = 112  (Staff, MANAGER_ID = 111)
    |       |
    |       +-- EMPLOYEE_ID = 113  (Staff, MANAGER_ID = 110)
    |
    +-- EMPLOYEE_ID = 120  (VP, MANAGER_ID = 100)
            |
            +-- EMPLOYEE_ID = 121  (Manager, MANAGER_ID = 120)
~~~

Trong mô hình này, một hàng là **con** nếu `MANAGER_ID` của nó bằng `EMPLOYEE_ID` của hàng cha. Cột `MANAGER_ID` có thể NULL ở hàng gốc vì CEO không có quản lý trong phạm vi cây đang xét.

Quan hệ này thường được gọi là *self-referencing relationship* hoặc quan hệ tự tham chiếu. Nó không bắt buộc phải có đúng một cây duy nhất: một bảng có thể chứa nhiều gốc, nhiều nhánh, hoặc dữ liệu lỗi tạo chu trình.

## 2. Chuẩn bị bảng thực hành

Trong schema thực hành được phép tạo bảng, chạy DDL sau một lần:

~~~sql
CREATE TABLE lab_employees (
    employee_id    NUMBER(6) PRIMARY KEY,
    employee_name  VARCHAR2(60 CHAR) NOT NULL,
    manager_id     NUMBER(6),
    department_id  NUMBER(4),
    status         VARCHAR2(12 CHAR) DEFAULT 'ACTIVE' NOT NULL,
    CONSTRAINT fk_lab_emp_manager
        FOREIGN KEY (manager_id)
        REFERENCES lab_employees (employee_id)
);
~~~

Khóa ngoại tự tham chiếu giúp ngăn một số giá trị `MANAGER_ID` trỏ tới nhân viên không tồn tại. Nó không tự ngăn chu trình như A quản lý B, B quản lý A; việc tránh chu trình cần quy tắc bổ sung ở nghiệp vụ hoặc logic kiểm tra.

Nạp dữ liệu mẫu:

~~~sql
INSERT ALL
    INTO lab_employees VALUES (100, 'An - CEO',       NULL, 10, 'ACTIVE')
    INTO lab_employees VALUES (110, 'Binh - VP',      100, 10, 'ACTIVE')
    INTO lab_employees VALUES (120, 'Chi - VP',       100, 20, 'ACTIVE')
    INTO lab_employees VALUES (111, 'Dung - Manager', 110, 10, 'ACTIVE')
    INTO lab_employees VALUES (113, 'Giang - Staff',  110, 10, 'ACTIVE')
    INTO lab_employees VALUES (121, 'Hanh - Manager',120, 20, 'ACTIVE')
    INTO lab_employees VALUES (112, 'Khanh - Staff',  111, 10, 'ACTIVE')
    INTO lab_employees VALUES (122, 'Lan - Staff',   121, 20, 'INACTIVE')
    INTO lab_employees VALUES (200, 'Minh - Director',NULL, 30, 'ACTIVE')
    INTO lab_employees VALUES (210, 'Nam - Manager',  200, 30, 'ACTIVE')
SELECT 1 FROM dual;

COMMIT;
~~~

Hai hàng `100` và `200` là hai gốc độc lập. Cây của `100` thuộc phòng ban 10/20; cây của `200` thuộc phòng ban 30. Một hierarchical query có thể trả về **rừng cây** (*forest*) gồm nhiều gốc.

Kiểm tra dữ liệu nguồn:

~~~sql
SELECT employee_id, employee_name, manager_id,
       department_id, status
FROM lab_employees
ORDER BY employee_id;
~~~

## 3. Khung cú pháp hierarchical query

Mẫu thường gặp:

~~~sql
SELECT select_list
FROM table_name
START WITH root_condition
CONNECT BY [NOCYCLE] parent_child_condition
ORDER SIBLINGS BY sibling_sort_expression;
~~~

Các phần:

| Thành phần | Vai trò |
|---|---|
| `START WITH` | Chọn hàng bắt đầu, tức các gốc của mỗi nhánh được duyệt |
| `CONNECT BY` | Xác định cách nối hàng hiện tại với hàng cha/con ở bước kế tiếp |
| `PRIOR` | Chỉ định biểu thức lấy từ hàng cha trong điều kiện phân cấp |
| `NOCYCLE` | Cho phép truy vấn dừng nhánh khi phát hiện chu trình thay vì báo lỗi chu trình |
| `LEVEL` | Pseudocolumn cho độ sâu của hàng trong cây kết quả |
| `ORDER SIBLINGS BY` | Sắp xếp các hàng cùng cha mà vẫn giữ thứ tự phân cấp |

Ví dụ đầu tiên:

~~~sql
SELECT LEVEL AS tree_level,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_id;
~~~

Kết quả đi từ nhân viên không có quản lý tới các cấp bên dưới. `START WITH` xác định các gốc; `CONNECT BY` tìm các hàng có `MANAGER_ID` bằng `EMPLOYEE_ID` của hàng cha trước đó.

Nếu bỏ `START WITH`, Oracle xem mọi hàng phù hợp trong nguồn là điểm bắt đầu của hierarchical query. Trong phần lớn bài toán cây cha-con, nên chỉ định gốc rõ ràng để tránh tạo các nhánh lặp hoặc kết quả không như ý.

## 4. LEVEL: độ sâu của hàng trong cây

`LEVEL` là pseudocolumn Oracle chỉ dùng trong hierarchical query:

- Gốc bắt đầu ở `LEVEL = 1`.
- Con trực tiếp của gốc ở `LEVEL = 2`.
- Cháu ở `LEVEL = 3`.
- Mỗi lần đi thêm một cạnh xuống dưới, giá trị LEVEL tăng 1.

Ví dụ:

~~~sql
SELECT LEVEL AS tree_level,
       employee_id,
       employee_name
FROM lab_employees
START WITH employee_id = 100
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_id;
~~~

Kết quả dự kiến:

| TREE_LEVEL | EMPLOYEE_ID | EMPLOYEE_NAME |
|---:|---:|---|
| 1 | 100 | An - CEO |
| 2 | 110 | Binh - VP |
| 3 | 111 | Dung - Manager |
| 4 | 112 | Khanh - Staff |
| 3 | 113 | Giang - Staff |
| 2 | 120 | Chi - VP |
| 3 | 121 | Hanh - Manager |
| 4 | 122 | Lan - Staff |

Thứ tự anh em trong cùng một cấp phụ thuộc cách sắp xếp. `ORDER SIBLINGS BY employee_id` đảm bảo các anh em được sắp theo mã nhưng vẫn giữ cha trước con.

### 4.1 Chỉ lấy một số cấp

Nếu chỉ cần gốc và hai cấp con:

~~~sql
SELECT LEVEL AS tree_level,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH employee_id = 100
CONNECT BY PRIOR employee_id = manager_id
       AND LEVEL <= 3
ORDER SIBLINGS BY employee_id;
~~~

Điều kiện độ sâu trong `CONNECT BY` ngăn Oracle mở rộng nhánh vượt quá cấp 3. Có thể dùng `WHERE LEVEL <= 3` để lọc các hàng kết quả theo độ sâu; khi cần giới hạn **quá trình mở rộng cây**, đặt điều kiện thích hợp trong `CONNECT BY` giúp ý định rõ ràng hơn.

### 4.2 LEVEL không phải cột lưu trong bảng

`TREE_LEVEL` trong kết quả không đến từ một cột vật lý. Nó được Oracle tính trong lúc duyệt cây. Vì vậy:

- Không cần thêm cột `LEVEL` vào bảng.
- Cùng một hàng vật lý có thể xuất hiện ở độ sâu khác nhau nếu có nhiều đường dẫn hợp lệ tới nó.
- Nếu thay đổi gốc hoặc điều kiện `CONNECT BY`, giá trị LEVEL có thể thay đổi mà dữ liệu bảng không đổi.

## 5. PRIOR: xác định hàng cha và hàng con

`PRIOR` là toán tử một ngôi dùng trong điều kiện `CONNECT BY`. Biểu thức ngay sau `PRIOR` được đánh giá từ **hàng cha ở bước trước**; phần còn lại được đánh giá trên ứng viên hàng hiện tại (hàng con trong hướng duyệt từ trên xuống).

### 5.1 Duyệt từ quản lý xuống nhân viên

~~~sql
SELECT LEVEL,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH employee_id = 100
CONNECT BY PRIOR employee_id = manager_id;
~~~

Đọc điều kiện:

~~~sql
PRIOR employee_id = manager_id
~~~

- `PRIOR employee_id`: mã nhân viên của hàng cha.
- `manager_id`: mã quản lý của hàng ứng viên.
- Hàng ứng viên là con nếu `manager_id` của nó bằng `employee_id` của hàng cha.

Do đó cây đi theo hướng:

~~~text
100 -> 110 -> 111 -> 112
100 -> 110 -> 113
100 -> 120 -> 121 -> 122
~~~

Đây là hướng phổ biến khi hiển thị sơ đồ tổ chức từ CEO xuống nhân viên.

### 5.2 Duyệt từ nhân viên lên quản lý

Nếu bắt đầu ở nhân viên `112` và muốn đi ngược lên chuỗi quản lý:

~~~sql
SELECT LEVEL,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH employee_id = 112
CONNECT BY PRIOR manager_id = employee_id;
~~~

Đọc điều kiện theo hướng ngược:

- `PRIOR manager_id`: mã quản lý của hàng hiện tại ở bước trước.
- `employee_id`: mã nhân viên của hàng ứng viên tiếp theo.
- Oracle tìm hàng có `EMPLOYEE_ID` bằng `MANAGER_ID` của hàng trước, tức đi lên cấp cha.

Đường kết quả bắt đầu tại nhân viên 112, rồi tới 111, 110 và 100. `LEVEL = 1` lúc này là nhân viên 112 vì đó là gốc của **truy vấn đang chạy**, dù trong sơ đồ tổ chức toàn công ty đây không phải CEO.

### 5.3 Vị trí PRIOR quyết định hướng duyệt

| Điều kiện | Cách đọc | Hướng thường dùng |
|---|---|---|
| `PRIOR employee_id = manager_id` | ID cha bằng MANAGER_ID của hàng con | Từ quản lý xuống nhân viên |
| `PRIOR manager_id = employee_id` | MANAGER_ID của hàng hiện tại bằng ID của hàng cha tiếp theo | Từ nhân viên lên quản lý |

Có thể đặt `PRIOR` ở vế phải:

~~~sql
CONNECT BY manager_id = PRIOR employee_id
~~~

Điều này tương đương về ý nghĩa với `CONNECT BY PRIOR employee_id = manager_id`. Vị trí đặt toán tử không thay đổi quan hệ nếu hai vế được giữ đúng.

### 5.4 PRIOR có thể áp dụng cho biểu thức

`PRIOR` không chỉ áp dụng cho một cột đơn:

~~~sql
CONNECT BY PRIOR department_id = department_id
       AND PRIOR employee_id = manager_id
~~~

Tuy nhiên, khi ghép theo nhiều thuộc tính, phải bảo đảm quan hệ thực sự xác định đúng cha-con. Nếu chỉ so sánh `DEPARTMENT_ID`, các nhân viên cùng phòng ban có thể bị nối chéo thành nhiều nhánh sai. Với mô hình nhân viên–quản lý, `EMPLOYEE_ID` và `MANAGER_ID` mới là quan hệ định danh chính.

## 6. START WITH: chọn gốc của cây

`START WITH` xác định hàng hoặc tập hàng bắt đầu. Mỗi hàng thỏa điều kiện có thể tạo một cây riêng.

### 6.1 Bắt đầu từ tất cả nhân viên không có quản lý

~~~sql
SELECT LEVEL,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_id;
~~~

Truy vấn này tạo một rừng gồm cây gốc 100 và 200. Đây thường là cách lấy toàn bộ sơ đồ tổ chức nếu dữ liệu bảo đảm mọi nhánh đều nối tới một nhân viên gốc.

### 6.2 Bắt đầu từ một nhân viên cụ thể

~~~sql
SELECT LEVEL,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH employee_id = 110
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_id;
~~~

Kết quả chỉ chứa nhánh của VP 110 và các cấp bên dưới. Nhân viên 120 và cây của họ không được duyệt vì không phải hậu duệ của gốc 110.

### 6.3 Nhiều gốc theo điều kiện

~~~sql
SELECT LEVEL,
       employee_id,
       employee_name,
       department_id
FROM lab_employees
START WITH manager_id IS NULL
       AND status = 'ACTIVE'
CONNECT BY PRIOR employee_id = manager_id;
~~~

Điều kiện `START WITH` có thể chứa nhiều điều kiện. Trong ví dụ, chỉ các nhân viên ACTIVE không có quản lý mới là gốc. Nếu một nhánh có gốc INACTIVE, nhánh đó không được khởi tạo từ hàng gốc này.

## 7. CONNECT_BY_ROOT: lấy giá trị ở gốc cho mọi hậu duệ

`CONNECT_BY_ROOT` là toán tử một ngôi trong hierarchical query. Nó trả về giá trị của biểu thức tại **hàng gốc của đường dẫn hiện tại**, dù hàng kết quả đang ở cấp nào.

Ví dụ:

~~~sql
SELECT LEVEL,
       employee_id,
       employee_name,
       CONNECT_BY_ROOT employee_id AS root_employee_id,
       CONNECT_BY_ROOT employee_name AS root_employee_name
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_id;
~~~

Kết quả minh họa:

| LEVEL | EMPLOYEE_ID | EMPLOYEE_NAME | ROOT_EMPLOYEE_ID | ROOT_EMPLOYEE_NAME |
|---:|---:|---|---:|---|
| 1 | 100 | An - CEO | 100 | An - CEO |
| 2 | 110 | Binh - VP | 100 | An - CEO |
| 3 | 111 | Dung - Manager | 100 | An - CEO |
| 4 | 112 | Khanh - Staff | 100 | An - CEO |
| 3 | 113 | Giang - Staff | 100 | An - CEO |
| 2 | 120 | Chi - VP | 100 | An - CEO |
| 3 | 121 | Hanh - Manager | 100 | An - CEO |
| 4 | 122 | Lan - Staff | 100 | An - CEO |
| 1 | 200 | Minh - Director | 200 | Minh - Director |
| 2 | 210 | Nam - Manager | 200 | Minh - Director |

`ROOT_EMPLOYEE_ID` giúp biết mỗi hàng thuộc cây gốc nào. Điều này rất hữu ích khi:

- Một truy vấn trả về nhiều cây.
- Cần tổng hợp theo lãnh đạo gốc.
- Cần xác định nguồn gốc của từng hàng hậu duệ.
- Cần hiển thị tên đơn vị cấp cao nhất cạnh từng nhân viên.

### 7.1 CONNECT_BY_ROOT khác PRIOR

Hai thành phần này có mục đích khác nhau:

| Thành phần | Giá trị được lấy | Phạm vi |
|---|---|---|
| `PRIOR employee_id` trong CONNECT BY | Cột của hàng cha ở bước duyệt hiện tại | Một bước quan hệ cha-con |
| `CONNECT_BY_ROOT employee_id` | Cột của hàng gốc của đường dẫn hiện tại | Toàn bộ đường dẫn từ gốc tới hàng đang xét |

`PRIOR` trả lời “hàng cha ngay trước là ai?”. `CONNECT_BY_ROOT` trả lời “đường dẫn này bắt đầu từ gốc nào?”.

### 7.2 Dùng CONNECT_BY_ROOT với thuộc tính khác

~~~sql
SELECT employee_id,
       employee_name,
       department_id,
       CONNECT_BY_ROOT department_id AS root_department_id
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

Trong ví dụ, mỗi hàng mang giá trị `DEPARTMENT_ID` của gốc. Hãy lưu ý đây là **giá trị tại hàng gốc**, không phải giá trị phòng ban của hàng hiện tại. Nếu các nhân viên được chuyển phòng ban nhưng quan hệ quản lý chưa đổi, hai giá trị có thể khác nhau.

`CONNECT_BY_ROOT` không được dùng trong điều kiện `START WITH` hoặc `CONNECT BY`. Nó là toán tử lấy giá trị gốc trong phần biểu thức của hierarchical query, không phải toán tử xác định quan hệ cha-con.

## 8. SYS_CONNECT_BY_PATH: tạo đường dẫn từ gốc đến hàng hiện tại

`SYS_CONNECT_BY_PATH(column, separator)` tạo một chuỗi thể hiện đường dẫn từ hàng gốc tới hàng đang xét. Tham số đầu là biểu thức ký tự cần nối; tham số thứ hai là dấu phân cách.

~~~sql
SELECT LEVEL,
       employee_id,
       employee_name,
       SYS_CONNECT_BY_PATH(employee_name, ' / ') AS employee_path
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_id;
~~~

Ví dụ một số đường dẫn:

~~~text
 / An - CEO
 / An - CEO / Binh - VP
 / An - CEO / Binh - VP / Dung - Manager
 / An - CEO / Binh - VP / Dung - Manager / Khanh - Staff
 / An - CEO / Chi - VP / Hanh - Manager / Lan - Staff
~~~

Đường dẫn chứa các giá trị từ root tới node hiện tại, theo đúng hướng truy vấn. Dấu phân cách được đặt giữa các cấp; ở kết quả gốc, đường dẫn bắt đầu bằng separator rồi đến giá trị gốc.

### 8.1 Đường dẫn bằng mã thay vì tên

Tên có thể trùng hoặc thay đổi. Nếu muốn đường dẫn ổn định hơn:

~~~sql
SELECT employee_id,
       SYS_CONNECT_BY_PATH(TO_CHAR(employee_id), '/') AS id_path
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

Ví dụ:

~~~text
/100
/100/110
/100/110/111
/100/110/111/112
~~~

`TO_CHAR` chuyển mã số sang biểu thức ký tự để xây dựng đường dẫn. Nếu cần lưu hoặc so sánh path, hãy xác định quy tắc định dạng ID ổn định, tránh định dạng số phụ thuộc NLS.

### 8.2 Kết hợp LEVEL, root và path

Một truy vấn thường dùng trong báo cáo cây:

~~~sql
SELECT LEVEL AS tree_level,
       employee_id,
       employee_name,
       manager_id,
       CONNECT_BY_ROOT employee_id AS root_id,
       SYS_CONNECT_BY_PATH(
           employee_name,
           ' > '
       ) AS hierarchy_path
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_name;
~~~

Ba cột bổ sung trả lời ba câu hỏi:

- `TREE_LEVEL`: đang ở cấp nào?
- `ROOT_ID`: cây này bắt đầu từ nhân viên nào?
- `HIERARCHY_PATH`: đường đi từ gốc tới nhân viên hiện tại gồm những ai?

Đây là tổ hợp hữu ích cho báo cáo phân cấp, export danh mục, hiển thị breadcrumb hoặc kiểm tra đường đi của một node.

### 8.3 Path là VARCHAR2, không phải CLOB vô hạn

`SYS_CONNECT_BY_PATH` trả về chuỗi kiểu `VARCHAR2` trong character set tương ứng. Đường dẫn rất sâu hoặc tên node rất dài có thể vượt giới hạn biểu thức chuỗi SQL của môi trường, phụ thuộc `MAX_STRING_SIZE` và character set. Không nên coi path là một trường văn bản không giới hạn.

Nếu path phục vụ hiển thị, giới hạn độ sâu/độ dài và xác định cách xử lý khi quá dài. Nếu cần lưu nội dung đường dẫn cực lớn, phải thiết kế một cơ chế khác phù hợp; không giả định hàm này tự trả về `CLOB`.

### 8.4 Separator có thể xuất hiện trong dữ liệu

Nếu tên nhân viên có chứa `' / '`, chuỗi path có thể trở nên mơ hồ khi phân tích ngược. Có thể chọn delimiter ít có khả năng xuất hiện, chuẩn hóa/escape giá trị trước khi ghép hoặc lưu đường dẫn theo cấu trúc riêng. `SYS_CONNECT_BY_PATH` là công cụ tạo chuỗi để đọc; nó không tự mã hóa delimiter thành một định dạng serialization an toàn.

## 9. ORDER SIBLINGS BY: sắp xếp anh em mà không phá cây

Trong hierarchical query, nếu cần sắp xếp các hàng cùng cha, dùng:

~~~sql
ORDER SIBLINGS BY employee_name
~~~

Ví dụ:

~~~sql
SELECT LEVEL,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_name;
~~~

Oracle sắp xếp các hàng anh em dưới cùng một cha theo tên, trong khi vẫn giữ cấu trúc cha trước con. Không dùng `ORDER BY employee_name` thông thường nếu mục tiêu là giữ thứ tự phân cấp; một `ORDER BY` cuối truy vấn có thể sắp xếp lại toàn bộ tập kết quả và làm cây khó đọc.

Có thể sắp xếp theo nhiều tiêu chí:

~~~sql
ORDER SIBLINGS BY status, employee_name
~~~

Khi cần ưu tiên ACTIVE trước INACTIVE trong cùng một nhánh, có thể dùng biểu thức:

~~~sql
ORDER SIBLINGS BY
    CASE WHEN status = 'ACTIVE' THEN 1 ELSE 2 END,
    employee_name
~~~

Thứ tự anh em chỉ ảnh hưởng cách hiển thị, không thay đổi quan hệ cha-con hoặc giá trị `LEVEL`.

## 10. Lọc dữ liệu trong hierarchical query

Vị trí của điều kiện lọc có ảnh hưởng tới cách cây được mở rộng.

### 10.1 WHERE lọc hàng kết quả

~~~sql
SELECT LEVEL,
       employee_id,
       employee_name,
       status
FROM lab_employees
WHERE status = 'ACTIVE'
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

Điều kiện `WHERE` lọc các hàng kết quả sau khi Oracle đã xác định quan hệ phân cấp. Một hàng INACTIVE có thể bị loại khỏi kết quả nhưng các hậu duệ của nó vẫn có thể được tìm thấy theo quan hệ cha-con nếu các hậu duệ tự thỏa điều kiện `WHERE`.

Ví dụ nhân viên 121 ACTIVE nhưng nhân viên 122 INACTIVE: với điều kiện `WHERE status = 'ACTIVE'`, 122 bị ẩn, còn các hàng ACTIVE ở dưới một node bị ẩn vẫn có thể xuất hiện theo cấu trúc cây.

### 10.2 CONNECT BY giới hạn quá trình mở rộng nhánh

Nếu muốn chỉ đi qua các nhân viên ACTIVE:

~~~sql
SELECT LEVEL,
       employee_id,
       employee_name,
       status
FROM lab_employees
START WITH manager_id IS NULL
       AND status = 'ACTIVE'
CONNECT BY PRIOR employee_id = manager_id
       AND status = 'ACTIVE';
~~~

Điều kiện trạng thái ở `CONNECT BY` giới hạn hàng ứng viên được nối vào cây. Nếu một nhân viên INACTIVE nằm giữa nhánh, Oracle không mở rộng qua hàng đó theo điều kiện này; hậu duệ phía dưới có thể không được duyệt.

| Vị trí điều kiện | Tác động chính |
|---|---|
| `START WITH` | Chọn node nào được làm gốc |
| `CONNECT BY` | Quyết định quan hệ nào được mở rộng, node con nào được nối vào cây |
| `WHERE` | Lọc hàng trong kết quả sau khi cây được xây dựng; không mặc định xóa toàn bộ hậu duệ của hàng bị lọc |

Đây là khác biệt quan trọng khi viết báo cáo tổ chức: “chỉ hiển thị nhân viên ACTIVE” khác với “chỉ duyệt qua các nhánh mà mọi cấp đều ACTIVE”.

### 10.3 Lọc theo LEVEL

Có thể chỉ lấy các cấp từ 2 trở đi:

~~~sql
SELECT LEVEL,
       employee_id,
       employee_name
FROM lab_employees
WHERE LEVEL >= 2
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

Gốc bị lọc khỏi kết quả nhưng các hàng con vẫn có thể xuất hiện. Nếu muốn giới hạn độ sâu duyệt, dùng điều kiện trong `CONNECT BY` thay vì chỉ lọc hàng cuối.

## 11. NOCYCLE và phát hiện chu trình

Dữ liệu phân cấp đúng thường không có chu trình: một nhân viên không thể là tổ tiên của chính mình. Nhưng dữ liệu có thể bị lỗi do cập nhật quản lý, import hoặc quy trình đồng bộ. Ví dụ:

~~~text
EMPLOYEE 300 -> MANAGER 310
EMPLOYEE 310 -> MANAGER 300
~~~

Hai hàng tạo chu trình. Nếu truy vấn đi theo quan hệ cha-con mà không có xử lý, Oracle có thể báo:

~~~text
ORA-01436: CONNECT BY loop in user data
~~~

### 11.1 Dùng NOCYCLE để tránh lỗi do loop

~~~sql
SELECT LEVEL,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY NOCYCLE PRIOR employee_id = manager_id;
~~~

`NOCYCLE` yêu cầu Oracle không tiếp tục đi vào vòng lặp gây chu trình. Truy vấn có thể trả kết quả thay vì dừng bằng lỗi loop; tuy nhiên, **không có nghĩa dữ liệu đã được sửa**. Chu trình vẫn là vấn đề chất lượng dữ liệu cần điều tra.

### 11.2 CONNECT_BY_ISCYCLE nhận diện hàng gây vòng lặp

Trong hierarchical query có `NOCYCLE`, pseudocolumn `CONNECT_BY_ISCYCLE` trả:

- `1` nếu hàng hiện tại có một hàng con là tổ tiên của nó, tức phát hiện cạnh tạo chu trình theo phép duyệt.
- `0` nếu không phải trường hợp đó.

Ví dụ:

~~~sql
SELECT LEVEL,
       employee_id,
       manager_id,
       CONNECT_BY_ISCYCLE AS is_cycle
FROM lab_employees
START WITH employee_id = 300
CONNECT BY NOCYCLE PRIOR employee_id = manager_id;
~~~

Ví dụ này chỉ có ý nghĩa khi dữ liệu thực sự có chu trình reachable từ gốc 300. Nếu không có hàng 300 hoặc không có đường dẫn chu trình, kết quả không minh họa được chu trình. Trong môi trường thực hành riêng, có thể tạo bảng thử không có foreign key để mô phỏng dữ liệu lỗi; không cố phá quan hệ ở bảng nghiệp vụ.

### 11.3 NOCYCLE không thay thế kiểm tra dữ liệu

Sau khi tìm thấy cycle, cần:

1. Xác định các mã node tham gia chu trình.
2. Xác định nguồn tạo dữ liệu sai: thao tác cập nhật, import hay đồng bộ.
3. Chọn quy tắc nghiệp vụ để sửa quan hệ cha-con.
4. Kiểm tra lại toàn bộ cây, không chỉ một gốc.

`NOCYCLE` hữu ích để chẩn đoán hoặc bảo vệ truy vấn khỏi lỗi loop, nhưng nếu chỉ âm thầm dùng nó trong báo cáo thì dữ liệu tổ chức sai có thể tiếp tục tồn tại.

## 12. Nhiều gốc và một node có thể xuất hiện nhiều lần

Với dữ liệu mẫu, hai gốc 100 và 200 tạo hai cây. `CONNECT_BY_ROOT` phân biệt nguồn gốc:

~~~sql
SELECT CONNECT_BY_ROOT employee_id AS root_id,
       LEVEL,
       employee_id,
       employee_name
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

Trong mô hình một cha duy nhất, mỗi nhân viên thường thuộc một cây. Nhưng một hierarchical query tổng quát có thể tạo **nhiều đường dẫn tới cùng một hàng** nếu quan hệ ghép cho phép một node có nhiều cha hoặc điều kiện `CONNECT BY` không xác định quan hệ duy nhất. Khi đó:

- Cùng một `EMPLOYEE_ID` có thể xuất hiện nhiều hàng.
- Mỗi lần xuất hiện có thể có `LEVEL` khác nhau.
- `CONNECT_BY_ROOT` và `SYS_CONNECT_BY_PATH` có thể khác nhau theo từng đường dẫn.

Đừng mặc định hierarchical query luôn trả một hàng duy nhất cho mỗi khóa chính. Nó trả **các lần xuất hiện theo đường dẫn được duyệt**. Nếu dữ liệu thực sự là đồ thị nhiều cha, cần xác định rõ có muốn liệt kê tất cả đường dẫn hay chỉ một đường.

## 13. Kết hợp CONNECT_BY_ROOT và SYS_CONNECT_BY_PATH trong báo cáo

Một truy vấn đầy đủ:

~~~sql
SELECT CONNECT_BY_ROOT employee_id AS root_id,
       CONNECT_BY_ROOT employee_name AS root_name,
       LEVEL AS depth,
       employee_id,
       manager_id,
       employee_name,
       SYS_CONNECT_BY_PATH(employee_name, ' / ') AS full_path
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_name;
~~~

Kết quả cung cấp:

| Cột | Dùng để |
|---|---|
| `ROOT_ID` | Định danh cây gốc |
| `ROOT_NAME` | Tên người đứng đầu cây |
| `DEPTH` | Cấp của node trong cây |
| `EMPLOYEE_ID` | Node hiện tại |
| `MANAGER_ID` | Quan hệ cha lưu trong bảng |
| `FULL_PATH` | Chuỗi đường dẫn từ root tới node hiện tại |

### 13.1 Tổng hợp số nhân viên theo gốc

Có thể bọc hierarchical query trong CTE rồi tổng hợp:

~~~sql
WITH employee_tree AS (
    SELECT CONNECT_BY_ROOT employee_id AS root_id,
           employee_id,
           LEVEL AS depth
    FROM lab_employees
    START WITH manager_id IS NULL
    CONNECT BY PRIOR employee_id = manager_id
)
SELECT root_id,
       COUNT(*) AS nodes_in_tree,
       MAX(depth) AS maximum_depth
FROM employee_tree
GROUP BY root_id
ORDER BY root_id;
~~~

Kết quả đếm số lần xuất hiện node trong mỗi cây và độ sâu lớn nhất. Với mô hình một cha duy nhất và không có cycle, `COUNT(*)` tương ứng số nhân viên trong cây. Nếu điều kiện nối tạo nhiều đường dẫn, cùng node có thể được đếm nhiều lần; lúc đó phải xác định muốn đếm **đường dẫn** hay **node duy nhất**.

Nếu cần đếm node duy nhất theo gốc:

~~~sql
COUNT(DISTINCT employee_id)
~~~

nhưng chỉ dùng cách này khi định nghĩa nghiệp vụ thật sự là số nhân viên duy nhất thuộc cây đó.

### 13.2 Tìm tất cả nhân viên dưới một lãnh đạo

~~~sql
SELECT LEVEL,
       employee_id,
       employee_name,
       CONNECT_BY_ROOT employee_name AS selected_root,
       SYS_CONNECT_BY_PATH(employee_id, '/') AS id_path
FROM lab_employees
START WITH employee_id = :manager_id
CONNECT BY PRIOR employee_id = manager_id;
~~~

Bind `:manager_id` cho phép ứng dụng chọn node gốc. Nếu dùng JDBC, bind mã số bằng `setLong`/`setBigDecimal` phù hợp; không nối chuỗi ID trực tiếp vào SQL.

## 14. Điều kiện JOIN và hierarchical query

Hierarchical query có thể kết hợp dữ liệu từ nhiều bảng, nhưng cần hiểu Oracle xử lý join và cây theo thứ tự. Ở mức khái quát, Oracle:

1. Xử lý các phép JOIN trong nguồn truy vấn.
2. Xây dựng quan hệ phân cấp theo `START WITH` và `CONNECT BY`.
3. Áp dụng các điều kiện `WHERE` còn lại để lọc hàng kết quả.

Ví dụ:

~~~sql
SELECT LEVEL,
       e.employee_id,
       e.employee_name,
       d.department_name
FROM lab_employees e
LEFT JOIN departments d
  ON d.department_id = e.department_id
START WITH e.manager_id IS NULL
CONNECT BY PRIOR e.employee_id = e.manager_id
ORDER SIBLINGS BY e.employee_name;
~~~

Hierarchical query vẫn duyệt theo quan hệ nhân viên–quản lý; tên phòng ban chỉ là thuộc tính bổ sung. Nếu JOIN tạo nhiều hàng cho một nhân viên, cây có thể bị nhân bản hoặc đường dẫn lặp. Hãy xác nhận quan hệ JOIN là một-một hoặc nhiều-một theo đúng grain trước khi đưa nó vào nguồn hierarchical query.

Nếu chỉ cần thuộc tính tra cứu của node, một cách rõ ràng khác là xây cây trước trong CTE rồi JOIN kết quả với bảng tra cứu sau:

~~~sql
WITH employee_tree AS (
    SELECT LEVEL AS depth,
           employee_id,
           manager_id,
           CONNECT_BY_ROOT employee_id AS root_id
    FROM lab_employees
    START WITH manager_id IS NULL
    CONNECT BY PRIOR employee_id = manager_id
)
SELECT t.depth,
       t.root_id,
       t.employee_id,
       d.department_name
FROM employee_tree t
LEFT JOIN departments d
  ON d.department_id = (
      SELECT e.department_id
      FROM lab_employees e
      WHERE e.employee_id = t.employee_id
  );
~~~

Đây là minh họa cách tách bước, không phải mẫu tối ưu bắt buộc; trong hệ thống thật có thể đưa `DEPARTMENT_ID` trực tiếp vào CTE để tránh truy vấn con. Điều quan trọng là không để JOIN làm thay đổi quan hệ cha-con hoặc tạo thêm đường dẫn không mong muốn.

## 15. Điều kiện phiên bản và khả năng tương thích

`LEVEL`, `PRIOR`, `CONNECT_BY_ROOT` và `SYS_CONNECT_BY_PATH` là các thành phần của hierarchical query Oracle đã có từ lâu và được hỗ trợ trong các release Oracle phổ biến, gồm 11g và 19c. Tuy vậy, khi dùng các tính năng liên quan khác như recursive subquery factoring, cú pháp và giới hạn có thể phụ thuộc phiên bản.

Kiểm tra phiên bản server:

~~~sql
SELECT banner
FROM v$version;
~~~

Hoặc nếu được cấp quyền:

~~~sql
SELECT instance_name, version
FROM v$instance;
~~~

Xác nhận đúng PDB/service:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

Không suy ra phiên bản Oracle Database từ phiên bản SQL Developer, SQLcl hoặc JDBC driver. Client mới vẫn có thể kết nối server cũ.

### 15.1 Hierarchical query và recursive subquery factoring

Oracle cũng hỗ trợ recursive subquery factoring với CTE đệ quy trong các phiên bản phù hợp. Hai cách có thể giải quyết một số bài toán cây nhưng không đồng nhất:

| Hierarchical query | Recursive subquery factoring |
|---|---|
| Dùng `START WITH` và `CONNECT BY` | Dùng `WITH ... AS (...)` có nhánh anchor và nhánh recursive |
| Có pseudocolumn `LEVEL` | Có thể tự tạo cột depth trong CTE |
| Có `PRIOR` để tham chiếu hàng cha | Điều kiện recursive join tham chiếu alias CTE |
| Có `CONNECT_BY_ROOT` và `SYS_CONNECT_BY_PATH` | Thường tự mang root/path trong cột CTE |
| Có `NOCYCLE` và pseudocolumn liên quan | Có cú pháp/qui tắc cycle riêng theo phiên bản |

Khi bảo trì hệ thống dùng `CONNECT BY`, không cần viết lại chỉ vì có CTE đệ quy. Chọn cách diễn đạt phù hợp với phiên bản, độ phức tạp và khả năng bảo trì.

## 16. Lỗi và tình huống thường gặp

| Lỗi/triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `ORA-01436: CONNECT BY loop in user data` | Dữ liệu tạo chu trình trong quan hệ phân cấp | Kiểm tra chuỗi cha-con; dùng `NOCYCLE` để điều tra và sửa dữ liệu |
| Truy vấn không trả hàng | `START WITH` không khớp gốc hoặc điều kiện `CONNECT BY` đặt sai hướng | Chạy riêng điều kiện root, kiểm tra khóa cha-con |
| Chỉ có gốc, không có con | Đảo vế `PRIOR` hoặc dữ liệu MANAGER_ID không khớp | Xác nhận `PRIOR employee_id = manager_id` cho hướng xuống |
| Cây có nhánh lặp | JOIN nhân bản nguồn hoặc một node có nhiều đường dẫn | Kiểm tra grain, quan hệ nhiều-nhiều và điều kiện nối |
| Hàng con vẫn xuất hiện khi cha bị lọc khỏi kết quả | Predicate đặt trong `WHERE` lọc từng hàng, không cắt toàn nhánh | Đặt điều kiện giới hạn nhánh trong `CONNECT BY` khi đúng nghiệp vụ |
| Đường dẫn quá dài | `SYS_CONNECT_BY_PATH` trả VARCHAR2 và vượt giới hạn biểu thức | Giới hạn depth/độ dài, cân nhắc cách biểu diễn khác |
| Path khó phân tích | Giá trị node chứa chính separator | Chọn delimiter phù hợp hoặc escape dữ liệu |
| Thứ tự cây bị phá | Dùng `ORDER BY` thông thường | Dùng `ORDER SIBLINGS BY` khi muốn sắp xếp anh em |
| CONNECT_BY_ROOT không được chấp nhận ở điều kiện | Toán tử bị giới hạn trong `START WITH`/`CONNECT BY` | Dùng nó trong biểu thức SELECT thích hợp |
| LEVEL không như dự kiến | Chọn gốc khác hoặc có nhiều gốc | Nhớ LEVEL bắt đầu bằng 1 tại gốc của truy vấn |
| Hàng trùng khi một node có nhiều cha | Hierarchical query trả theo từng đường dẫn | Phân biệt số node duy nhất với số đường dẫn |
| Cây biến mất sau khi thêm điều kiện status | Điều kiện đặt ở CONNECT BY khiến nhánh không mở rộng | Xác định muốn ẩn hàng hay cắt nhánh |

## 17. Bài thực hành tự kiểm tra

Sử dụng bảng `LAB_EMPLOYEES` đã tạo ở phần 2. Các bài tập không yêu cầu tạo thêm dữ liệu nghiệp vụ.

### Bài 1 — Duyệt toàn bộ sơ đồ

Viết truy vấn:

- Bắt đầu từ mọi hàng `MANAGER_ID IS NULL`.
- Duyệt từ quản lý xuống nhân viên.
- Hiển thị `LEVEL`, mã nhân viên, mã quản lý và tên.
- Sắp xếp anh em theo `EMPLOYEE_NAME`.

Giải thích vì sao gốc 100 và 200 đều xuất hiện ở LEVEL 1.

### Bài 2 — Đổi hướng PRIOR

Bắt đầu tại `EMPLOYEE_ID = 112` và đi ngược lên CEO. Viết điều kiện `CONNECT BY` phù hợp. Ghi lại thứ tự hàng và LEVEL. Vì sao nhân viên 112 có LEVEL 1 dù không phải gốc tổ chức?

### Bài 3 — Hiển thị root

Thêm `CONNECT_BY_ROOT employee_id` và `CONNECT_BY_ROOT employee_name`. Xác định mọi nhân viên dưới gốc 100 mang cùng root nào; nhân viên 210 thuộc root nào?

### Bài 4 — Tạo path

Dùng `SYS_CONNECT_BY_PATH(employee_name, ' / ')` để tạo đường dẫn. Sau đó thay tên bằng mã số đã `TO_CHAR`. So sánh path dễ đọc và path ổn định hơn khi tên thay đổi.

### Bài 5 — Giới hạn độ sâu

Chỉ duyệt tối đa 3 cấp tính cả gốc. Viết điều kiện trong `CONNECT BY`. Viết thêm biến thể `WHERE LEVEL <= 3` và mô tả khác biệt khi lọc hàng.

### Bài 6 — Lọc ACTIVE

So sánh hai truy vấn:

~~~sql
WHERE status = 'ACTIVE'
~~~

và:

~~~sql
CONNECT BY PRIOR employee_id = manager_id
       AND status = 'ACTIVE'
~~~

Nhân viên 122 INACTIVE bị xử lý như thế nào? Nếu có nhân viên ACTIVE ở dưới một quản lý INACTIVE, hàng đó có được duyệt trong từng trường hợp không?

### Bài 7 — Tạo nhiều cây

Dùng `START WITH manager_id IS NULL` và thêm `CONNECT_BY_ROOT` để nhóm nhân viên theo lãnh đạo gốc. Đếm số node và độ sâu lớn nhất của mỗi cây.

### Bài 8 — Sắp xếp anh em

Thử `ORDER SIBLINGS BY employee_name` rồi so sánh với `ORDER BY employee_name`. Vì sao cách thứ hai có thể làm cha-con không còn nằm theo thứ tự dễ đọc?

### Bài 9 — Chu trình

Trong bảng thực hành riêng không có foreign key, tạo một chu trình hai node. Quan sát lỗi khi chạy hierarchical query bình thường; sau đó thêm `NOCYCLE` và `CONNECT_BY_ISCYCLE`. Giải thích tại sao truy vấn chạy được không có nghĩa dữ liệu đã hợp lệ.

### Bài 10 — Đếm node duy nhất hay đường dẫn?

Giả sử một danh mục cho phép một node có hai cha. Giải thích vì sao cùng một node có thể xuất hiện hai lần trong kết quả hierarchical query và khi nào nên dùng `COUNT(*)` so với `COUNT(DISTINCT node_id)`.

## 18. Ghi nhớ

| Thành phần | Câu hỏi nó trả lời | Cách dùng |
|---|---|---|
| `START WITH` | Bắt đầu duyệt từ hàng nào? | Chọn gốc hoặc nhiều gốc |
| `CONNECT BY` | Quan hệ cha-con được xác định ra sao? | Viết điều kiện mở rộng cây |
| `PRIOR` | Biểu thức nào lấy từ hàng cha? | `PRIOR parent_id = child_parent_id` theo hướng duyệt |
| `LEVEL` | Hàng đang ở độ sâu nào? | Gốc 1, con 2, cháu 3... |
| `CONNECT_BY_ROOT` | Đường dẫn bắt đầu từ node nào? | Lấy giá trị của root cho mọi hàng trong cây |
| `SYS_CONNECT_BY_PATH` | Đường đi từ root tới node là gì? | Ghép giá trị các cấp thành chuỗi |
| `ORDER SIBLINGS BY` | Sắp xếp anh em thế nào mà vẫn giữ cây? | Sắp xếp các node cùng cha |
| `NOCYCLE` | Làm sao tránh truy vấn dừng vì loop? | Bỏ qua nhánh tạo cycle và điều tra dữ liệu |
| `CONNECT_BY_ISCYCLE` | Hàng hiện tại có cạnh dẫn tới tổ tiên không? | Phát hiện chu trình trong truy vấn NOCYCLE |

Khi viết hierarchical query, hãy xác định **gốc**, **hướng duyệt**, **quan hệ cha-con**, rồi mới chọn cách hiển thị. `LEVEL` mô tả độ sâu; `PRIOR` điều khiển quan hệ ở từng bước; `CONNECT_BY_ROOT` giữ thông tin của gốc; `SYS_CONNECT_BY_PATH` tạo đường dẫn. Kết hợp đúng bốn thành phần này với `ORDER SIBLINGS BY`, điều kiện lọc phù hợp và `NOCYCLE` khi cần sẽ giúp truy vấn cây rõ ràng, dễ kiểm tra và tránh nhầm lẫn giữa một node, một nhánh và toàn bộ rừng cây.
