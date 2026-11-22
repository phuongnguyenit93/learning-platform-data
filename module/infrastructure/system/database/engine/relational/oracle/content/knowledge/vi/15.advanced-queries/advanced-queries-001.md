# Truy vấn cây bằng START WITH và CONNECT BY trong Oracle

Nhiều dữ liệu quan hệ không chỉ là một danh sách hàng độc lập. Chúng mô tả **quan hệ phân cấp**: nhân viên thuộc quản lý, phòng ban có phòng ban cha, danh mục có nhóm và nhóm con, tài khoản có tài khoản cấp trên, hoặc một sản phẩm được cấu thành từ các linh kiện con. Trong mô hình bảng quan hệ, các mối liên hệ này thường được lưu bằng khóa tự tham chiếu (*self-referencing foreign key*): mỗi hàng giữ mã của hàng cha.

Oracle hỗ trợ **hierarchical query** bằng hai mệnh đề `START WITH` và `CONNECT BY`. `START WITH` chọn hàng gốc; `CONNECT BY` mô tả cách đi từ một hàng hiện tại tới hàng con hoặc hàng cha tiếp theo. Từ đó Oracle có thể trả về cây nhiều cấp mà không cần viết một câu JOIN riêng cho từng cấp.

Bài học thuộc chủ đề **Truy vấn nâng cao** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Mô hình cha–con và cách đọc `PRIOR`.
- Chọn gốc bằng `START WITH`, duyệt cây bằng `CONNECT BY`.
- Các pseudocolumn `LEVEL`, `CONNECT_BY_ROOT`, `SYS_CONNECT_BY_PATH`, `CONNECT_BY_ISLEAF` và `CONNECT_BY_ISCYCLE`.
- Sắp xếp nhánh bằng `ORDER SIBLINGS BY`.
- Phân biệt lọc hàng với cắt nhánh, xử lý chu trình bằng `NOCYCLE`.
- Kết hợp JOIN, index, execution plan và bài thực hành SQL.

## 1. Dữ liệu phân cấp trong một bảng quan hệ

Một bảng nhân viên có thể chứa cả thông tin nhân viên và mã quản lý trực tiếp:

| EMPLOYEE_ID | EMPLOYEE_NAME | MANAGER_ID |
| ---: | --- | ---: |
| 1 | An | NULL |
| 2 | Bình | 1 |
| 3 | Chi | 1 |
| 4 | Dũng | 2 |
| 5 | Hà | 2 |
| 6 | Lan | 3 |

`MANAGER_ID` tham chiếu `EMPLOYEE_ID` của người quản lý. Hàng An có `MANAGER_ID IS NULL`, nên An là gốc của cây trong ví dụ. Bình và Chi là con trực tiếp của An; Dũng và Hà là con của Bình; Lan là con của Chi.

~~~mermaid
flowchart TD
    A["An (1)"] --> B["Binh (2)"]
    A --> C["Chi (3)"]
    B --> D["Dung (4)"]
    B --> E["Ha (5)"]
    C --> F["Lan (6)"]
~~~

Quan hệ cha–con được lưu thành các hàng riêng, không lưu nguyên cây trong một cột. Một truy vấn phân cấp tái dựng đường đi dựa trên điều kiện nối giữa khóa của hàng cha và khóa ngoại của hàng con.

### Tạo bảng thực hành

Ví dụ sau dùng schema học tập có quyền `CREATE TABLE` và quota phù hợp:

~~~sql
CREATE TABLE lab_employees_tree (
    employee_id   NUMBER(6) PRIMARY KEY,
    employee_name VARCHAR2(80 CHAR) NOT NULL,
    manager_id    NUMBER(6),
    sort_order    NUMBER(4),
    CONSTRAINT fk_lab_emp_tree_manager
        FOREIGN KEY (manager_id)
        REFERENCES lab_employees_tree (employee_id)
);

INSERT INTO lab_employees_tree VALUES (1, 'An',   NULL, 1);
INSERT INTO lab_employees_tree VALUES (2, 'Binh', 1,    1);
INSERT INTO lab_employees_tree VALUES (3, 'Chi',  1,    2);
INSERT INTO lab_employees_tree VALUES (4, 'Dung', 2,    1);
INSERT INTO lab_employees_tree VALUES (5, 'Ha',   2,    2);
INSERT INTO lab_employees_tree VALUES (6, 'Lan',  3,    1);

COMMIT;
~~~

Đây là khóa ngoại tự tham chiếu: `MANAGER_ID` phải trỏ tới một `EMPLOYEE_ID` có thật hoặc là NULL. Ràng buộc khóa ngoại ngăn tham chiếu tới hàng cha không tồn tại, nhưng **không tự ngăn mọi chu trình phân cấp**. Ví dụ một hàng có thể tham chiếu tới một hàng con của chính nó mà vẫn thỏa FK; cần quy tắc bổ sung hoặc kiểm tra chu trình nếu nghiệp vụ không cho phép.

## 2. Cú pháp START WITH và CONNECT BY

Mẫu cơ bản:

~~~sql
SELECT ...
FROM table_name
START WITH root_condition
CONNECT BY PRIOR parent_key = child_parent_key;
~~~

- `START WITH` xác định một hoặc nhiều hàng bắt đầu (root rows).
- `CONNECT BY` định nghĩa quan hệ giữa hàng hiện tại và hàng tiếp theo trong cây.
- `PRIOR` tham chiếu biểu thức ở **hàng cha hiện tại** trong quá trình duyệt.

Với bảng nhân viên, truy vấn từ quản lý cấp cao xuống nhân viên cấp dưới:

~~~sql
SELECT employee_id,
       employee_name,
       manager_id,
       LEVEL AS tree_level
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

Đọc điều kiện:

`PRIOR employee_id = manager_id`

nghĩa là **employee_id của hàng cha hiện tại bằng manager_id của hàng con kế tiếp**. Oracle tìm các hàng có `MANAGER_ID` bằng `EMPLOYEE_ID` của hàng đang đứng, rồi tiếp tục đi xuống.

Kết quả có các hàng ở nhiều cấp. `LEVEL` cho biết độ sâu: An ở cấp 1, Bình/Chi cấp 2, Dũng/Hà/Lan cấp 3.

### START WITH chọn nhiều gốc

Không bắt buộc cây chỉ có một root. Nếu có nhiều hàng thỏa điều kiện, Oracle bắt đầu một cây từ mỗi hàng:

~~~sql
SELECT employee_id, employee_name, manager_id, LEVEL
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

Nếu bảng có nhiều tổ chức độc lập, mỗi tổ chức có một nhân viên gốc, truy vấn sẽ trả về các cây tương ứng. Có thể chọn một gốc cụ thể:

~~~sql
SELECT employee_id, employee_name, manager_id, LEVEL
FROM lab_employees_tree
START WITH employee_id = 2
CONNECT BY PRIOR employee_id = manager_id;
~~~

Kết quả bắt đầu từ Bình và chỉ chứa nhánh của Bình cùng các hậu duệ. An không xuất hiện vì không nằm trong phạm vi đi xuống từ gốc được chọn.

### Nếu bỏ START WITH thì sao?

Trong một hierarchical query không có `START WITH`, Oracle có thể coi các hàng đủ điều kiện trong nguồn là điểm bắt đầu của quá trình phân cấp. Điều này thường tạo ra nhiều đường đi và nhiều kết quả lặp theo từng gốc hơn mong muốn. Trong truy vấn nghiệp vụ, hãy chỉ rõ root condition để phạm vi cây dễ hiểu và kiểm soát.

## 3. Hiểu chính xác PRIOR và hướng duyệt

`PRIOR` là toán tử một ngôi trong điều kiện `CONNECT BY`. Nó áp dụng cho biểu thức ngay sau nó, và biểu thức đó được lấy từ hàng cha của bước hiện tại.

### Duyệt từ cha xuống con

Với cấu trúc:

~~~sql
CONNECT BY PRIOR employee_id = manager_id
~~~

Oracle lấy `EMPLOYEE_ID` của hàng cha rồi tìm hàng có `MANAGER_ID` bằng giá trị đó. Đây là cách viết phổ biến nhất khi truy vấn từ root xuống các descendant.

### Duyệt từ con lên cha

Nếu bắt đầu tại một nhân viên và muốn lần ngược về người quản lý:

~~~sql
SELECT employee_id,
       employee_name,
       manager_id,
       LEVEL AS distance_from_employee
FROM lab_employees_tree
START WITH employee_id = 4
CONNECT BY PRIOR manager_id = employee_id;
~~~

Ở đây `PRIOR manager_id` lấy mã quản lý của hàng hiện tại; Oracle tìm hàng tiếp theo có `EMPLOYEE_ID` bằng mã đó. Bắt đầu từ Dũng (4), kết quả đi lên Bình (2), rồi An (1).

~~~mermaid
flowchart TD
    A["An (1)"] --> B["Binh (2)"] --> D["Dung (4)"]
    D -. "Truy van nguoc tu Dung" .-> B
    B -. "Tiep tuc len cha" .-> A
~~~

Hai điều kiện `PRIOR` trên **không thể hoán đổi tùy tiện**. Hãy xác định rõ:

1. Hàng nào là gốc?
2. Mỗi bước cần tìm con của hàng hiện tại hay cha của hàng hiện tại?
3. Cột nào chứa khóa định danh của hàng hiện tại?
4. Cột nào chứa khóa tham chiếu tới hàng liên quan?

### PRIOR có thể đặt ở vế khác

Oracle cho phép `PRIOR` đứng trước biểu thức ở một trong hai phía của điều kiện, nhưng ý nghĩa vẫn là biểu thức được đánh giá trên hàng cha. Ví dụ hai cách sau thể hiện cùng quan hệ cha–con:

~~~sql
CONNECT BY PRIOR employee_id = manager_id

CONNECT BY manager_id = PRIOR employee_id
~~~

Viết theo dạng đầu thường dễ đọc hơn vì khóa của cha đứng cạnh `PRIOR`.

### Quan hệ nhiều cột

Nếu khóa định danh là khóa ghép, điều kiện CONNECT BY có thể nối nhiều thành phần:

~~~sql
CONNECT BY PRIOR tenant_id = tenant_id
       AND PRIOR node_id = parent_node_id
~~~

Điều này giúp giới hạn traversal trong cùng tenant. Thiếu một thành phần khóa có thể nối nhầm cây giữa các tenant hoặc tạo đường đi không hợp lệ.

## 4. LEVEL: độ sâu của hàng trong cây

`LEVEL` là pseudocolumn chỉ có ý nghĩa trong hierarchical query:

- Root có `LEVEL = 1`.
- Con trực tiếp của root có `LEVEL = 2`.
- Cháu có `LEVEL = 3`.
- Mỗi bước đi tiếp làm LEVEL tăng một.

Ví dụ hiển thị thụt lề:

~~~sql
SELECT LPAD(' ', 2 * (LEVEL - 1)) || employee_name AS hierarchy_name,
       employee_id,
       manager_id,
       LEVEL
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY sort_order, employee_name;
~~~

`LPAD` tạo khoảng trắng để nhìn thấy cấu trúc. Nó chỉ định dạng kết quả, không làm thay đổi quan hệ cha–con.

### Giới hạn độ sâu

Nếu chỉ cần ba cấp đầu tiên, có thể giới hạn trong điều kiện CONNECT BY:

~~~sql
SELECT employee_id, employee_name, LEVEL
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
       AND LEVEL <= 3;
~~~

Điều kiện này ngăn Oracle mở rộng các nhánh vượt quá cấp 3. Khác với lọc `WHERE LEVEL <= 3` sau khi tạo cây, việc đặt điều kiện ở CONNECT BY có thể dừng traversal ở giới hạn đó. Khi bảng rất sâu, giới hạn độ sâu có thể giảm đáng kể công việc.

## 5. Các pseudocolumn quan trọng

Oracle cung cấp một số pseudocolumn và hàm để lấy thông tin về vị trí của hàng trong cây:

| Thành phần | Trả về | Công dụng |
| --- | --- | --- |
| `LEVEL` | Độ sâu hiện tại, root là 1 | Hiển thị cấp tổ chức, giới hạn độ sâu. |
| `CONNECT_BY_ROOT expr` | Giá trị của biểu thức tại root của nhánh hiện tại | Gắn mỗi hàng với root tương ứng. |
| `SYS_CONNECT_BY_PATH(col, delimiter)` | Chuỗi đường dẫn từ root tới hàng hiện tại | Hiển thị breadcrumb/path. |
| `CONNECT_BY_ISLEAF` | 1 nếu hàng hiện tại là leaf, 0 nếu còn con trong cây kết quả | Tìm nút cuối/nhân viên không quản lý ai. |
| `CONNECT_BY_ISCYCLE` | 1 nếu hàng hiện tại có một child là ancestor của nó, 0 nếu không | Nhận diện cạnh tạo chu trình khi dùng NOCYCLE. |

### CONNECT_BY_ROOT: lấy thông tin từ gốc

Ví dụ mỗi nhân viên cần biết tên quản lý cao nhất của cây:

~~~sql
SELECT employee_id,
       employee_name,
       LEVEL,
       CONNECT_BY_ROOT employee_name AS top_manager
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

Nếu có nhiều root, mỗi hàng descendant sẽ mang giá trị `TOP_MANAGER` của đúng root mà đường đi đó bắt đầu. Điều này hữu ích khi gom nhân sự theo đơn vị cao nhất hoặc xác định nhánh của cây.

### SYS_CONNECT_BY_PATH: tạo đường dẫn

~~~sql
SELECT employee_id,
       employee_name,
       SYS_CONNECT_BY_PATH(employee_name, ' / ') AS org_path
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY sort_order, employee_name;
~~~

Ví dụ đường dẫn:

- ` / An`
- ` / An / Binh`
- ` / An / Binh / Dung`
- ` / An / Chi / Lan`

`SYS_CONNECT_BY_PATH` trả chuỗi biểu diễn đường đi từ root đến hàng hiện tại. Cần chọn delimiter không gây nhầm với nội dung tên; nếu dữ liệu có thể chứa delimiter, nên có quy tắc escape hoặc trả thêm các thành phần riêng.

### CONNECT_BY_ISLEAF: tìm nút lá

~~~sql
SELECT employee_id,
       employee_name,
       LEVEL,
       CONNECT_BY_ISLEAF AS is_leaf
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

Hàng Dũng, Hà và Lan là leaf trong cây ví dụ vì không có nhân viên con được tìm thấy theo điều kiện CONNECT BY. Leaf là khái niệm **theo cây và điều kiện traversal hiện tại**; nếu filter bỏ một số hàng con, một nút có thể trở thành leaf trong kết quả của truy vấn đó dù bảng nguồn vẫn có con khác.

Lọc chỉ lấy leaf:

~~~sql
SELECT employee_id, employee_name
FROM lab_employees_tree
WHERE CONNECT_BY_ISLEAF = 1
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

Các pseudocolumn hierarchical cần được tham chiếu trong query block có mệnh đề START WITH/CONNECT BY tương ứng.

### CONNECT_BY_ISCYCLE: nhận diện chu trình

Khi traversal gặp một hàng có thể tạo đường quay về ancestor, Oracle có thể báo lỗi nếu không bật `NOCYCLE`. Khi dùng `NOCYCLE`, có thể chọn `CONNECT_BY_ISCYCLE` để nhận diện hàng có child là ancestor của nó:

~~~sql
SELECT employee_id,
       employee_name,
       LEVEL,
       CONNECT_BY_ISCYCLE AS cycle_edge
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY NOCYCLE PRIOR employee_id = manager_id;
~~~

Nếu dữ liệu không có chu trình, cột này thường là 0. Nó đánh dấu hàng hiện tại trong traversal có một child trỏ tới ancestor; nó không phải cờ tổng quát “mọi hàng thuộc một thành phần có cycle”.

## 6. Sắp xếp cây bằng ORDER SIBLINGS BY

Một cây có nhiều nhánh cần giữ thứ tự cha–con. `ORDER BY` thông thường sắp xếp toàn bộ kết quả theo các biểu thức được chỉ định, có thể phá vỡ thứ tự hiển thị theo cây.

Dùng `ORDER SIBLINGS BY` để sắp xếp các **hàng cùng cha** mà vẫn giữ thứ tự phân cấp:

~~~sql
SELECT LPAD(' ', 2 * (LEVEL - 1)) || employee_name AS tree_name,
       employee_id,
       manager_id,
       LEVEL
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY sort_order, employee_name;
~~~

`SORT_ORDER` quyết định thứ tự các anh/chị/em cùng cấp; `EMPLOYEE_NAME` là tiêu chí phụ để phá hòa. Oracle vẫn hiển thị con sau cha theo cấu trúc phân cấp.

So sánh:

~~~sql
-- Sắp xếp toàn bộ hàng, không giữ thứ tự cây như yêu cầu trình bày.
SELECT employee_id, employee_name, manager_id, LEVEL
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER BY employee_name;
~~~

Nếu giao diện cần hiển thị cây, thường dùng `ORDER SIBLINGS BY`. Nếu chỉ cần một danh sách phẳng theo một thuộc tính, `ORDER BY` có thể là chủ đích đúng. Dù dùng cách nào, thứ tự kết quả chỉ được đảm bảo khi có mệnh đề sắp xếp.

## 7. WHERE và CONNECT BY: lọc hàng hay cắt nhánh?

Đây là khác biệt rất quan trọng trong hierarchical query. Oracle xử lý truy vấn theo thứ tự khái quát:

1. Xử lý JOIN nếu có.
2. Xác định quan hệ phân cấp theo `CONNECT BY`.
3. Áp dụng các điều kiện `WHERE` lên các hàng kết quả theo quy tắc của hierarchical query.

Điều kiện WHERE lọc từng hàng được trả về; nó **không nhất thiết loại bỏ toàn bộ descendants** của một hàng bị lọc. Nếu mục tiêu là ngăn traversal đi qua một hàng hoặc cắt cả nhánh, điều kiện thường phải được đặt trong CONNECT BY.

Giả sử bảng có thêm cột `ACTIVE_FLAG` và một quản lý bị inactive:

~~~sql
SELECT employee_id, employee_name, manager_id, active_flag, LEVEL
FROM lab_employees_tree
WHERE active_flag = 'Y'
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

Điều kiện WHERE có thể ẩn hàng inactive khỏi output nhưng các descendant của hàng đó vẫn có thể được tìm thấy trong quá trình phân cấp và xuất hiện. Đây là điều bất ngờ nếu người viết nghĩ WHERE sẽ cắt cả nhánh.

Nếu muốn chỉ đi tiếp qua các hàng active:

~~~sql
SELECT employee_id, employee_name, manager_id, active_flag, LEVEL
FROM lab_employees_tree
START WITH manager_id IS NULL
       AND active_flag = 'Y'
CONNECT BY PRIOR employee_id = manager_id
       AND active_flag = 'Y';
~~~

Điều kiện bổ sung trong CONNECT BY kiểm tra hàng con được nối vào nhánh. Điều kiện trong START WITH đồng thời bảo đảm root cũng active.

### Quy tắc quyết định vị trí predicate

| Mục tiêu | Vị trí thường dùng |
| --- | --- |
| Chọn root hợp lệ | `START WITH` |
| Chỉ mở rộng sang child thỏa điều kiện | `CONNECT BY ... AND child_condition` |
| Ẩn một số hàng khỏi output nhưng vẫn cho traversal qua chúng | `WHERE` |
| Giới hạn chiều sâu traversal | Điều kiện trong `CONNECT BY`, ví dụ `LEVEL <= 4` |
| Chỉ hiển thị leaf hoặc root sau khi cây được dựng | `WHERE` kết hợp pseudocolumn phù hợp |

Nếu mục tiêu là “không hiển thị quản lý inactive nhưng vẫn hiển thị nhân viên active bên dưới”, WHERE có thể phù hợp. Nếu mục tiêu là “nhánh của quản lý inactive không được duyệt”, predicate cần cắt traversal trong CONNECT BY. Hãy viết ví dụ nhỏ để xác nhận semantics trước khi áp dụng vào báo cáo quan trọng.

## 8. NOCYCLE và dữ liệu có chu trình

Mô hình cây lý tưởng có một root cho mỗi thành phần và không có đường đi quay về chính nó. Nhưng dữ liệu thực tế có thể chứa cycle do lỗi import, cập nhật khóa cha sai hoặc mô hình thực ra là graph chứ không phải tree.

Ví dụ chu trình:

~~~text
Node 1 -> Node 2 -> Node 3 -> Node 1
~~~

Với truy vấn hierarchical không có `NOCYCLE`, Oracle có thể báo:

`ORA-01436: CONNECT BY loop in user data`

Thêm `NOCYCLE`:

~~~sql
SELECT node_id,
       parent_id,
       LEVEL,
       CONNECT_BY_ISCYCLE AS is_cycle
FROM lab_graph
START WITH node_id = 1
CONNECT BY NOCYCLE PRIOR node_id = parent_id;
~~~

`NOCYCLE` ngăn việc tiếp tục lặp vô hạn qua một chu trình và cho phép truy vấn trả về các hàng có thể duyệt được. Nó **không sửa dữ liệu**, không xóa cạnh sai và không bảo đảm mọi chu trình trong bảng đều được tìm thấy nếu chúng không nằm trong phạm vi traversal từ root đã chọn.

### Bảng lab để thử cycle

Để tạo chu trình, dùng bảng không đặt FK tự tham chiếu (vì mục đích bài tập là cho phép dữ liệu graph bất thường):

~~~sql
CREATE TABLE lab_graph (
    node_id   NUMBER(6) PRIMARY KEY,
    parent_id NUMBER(6),
    node_name VARCHAR2(40 CHAR)
);

INSERT INTO lab_graph VALUES (1, 3, 'One');
INSERT INTO lab_graph VALUES (2, 1, 'Two');
INSERT INTO lab_graph VALUES (3, 2, 'Three');
COMMIT;
~~~

Chạy:

~~~sql
SELECT node_id,
       parent_id,
       node_name,
       LEVEL,
       CONNECT_BY_ISCYCLE AS is_cycle
FROM lab_graph
START WITH node_id = 1
CONNECT BY NOCYCLE PRIOR node_id = parent_id;
~~~

Đường đi từ node 1 có thể đi 1 → 2 → 3; hàng 3 có child là node 1, vốn đã là ancestor. `CONNECT_BY_ISCYCLE` đánh dấu vị trí phát hiện cạnh quay lại đó. Số hàng và cách hiển thị cụ thể nên được quan sát trên phiên bản Oracle đang học.

### Phát hiện dữ liệu cha không tồn tại

Đây không phải cycle, nhưng cũng là lỗi dữ liệu phân cấp:

~~~sql
SELECT c.node_id, c.parent_id
FROM lab_graph c
LEFT JOIN lab_graph p
  ON p.node_id = c.parent_id
WHERE c.parent_id IS NOT NULL
  AND p.node_id IS NULL;
~~~

Truy vấn tìm hàng con tham chiếu tới parent không tồn tại. FK tự tham chiếu có thể ngăn lỗi này nếu được ENABLE và VALIDATE; bảng graph lab không có FK nên có thể kiểm tra bằng SQL.

### Chu trình và mô hình graph

Nếu một node có thể có nhiều parent, dữ liệu không còn là cây đơn giản mà là graph có nhiều đường đi. Hierarchical query có thể trả cùng node nhiều lần theo các đường dẫn khác nhau. `NOCYCLE` xử lý việc lặp đường đi theo ancestor nhưng không biến graph thành tree và không tự chọn một parent đại diện. Cần xác định nghiệp vụ có cho phép nhiều parent, có cần mọi path hay chỉ một path, và có cần deduplicate theo node ID hay không.

## 9. Kết hợp hierarchical query với JOIN

Một hierarchical query có thể JOIN với bảng mô tả, bảng phân quyền hoặc bảng thuộc tính. Oracle xử lý join trước khi áp dụng CONNECT BY; vì vậy join một-nhiều có thể nhân bản hàng đầu vào và làm cây có nhiều đường đi hoặc kết quả bất thường.

Ví dụ mỗi nhân viên có nhiều chứng chỉ. Nếu JOIN nhân viên với chứng chỉ trước khi duyệt cây, một nhân viên có ba chứng chỉ có thể xuất hiện thành ba hàng trong nguồn phân cấp. Cấu trúc cây có thể bị nhân bản.

### Dùng inline view để dựng cây trước

~~~sql
SELECT t.employee_id,
       t.employee_name,
       t.manager_id,
       t.tree_level,
       c.certificate_name
FROM (
    SELECT employee_id,
           employee_name,
           manager_id,
           LEVEL AS tree_level
    FROM lab_employees_tree
    START WITH manager_id IS NULL
    CONNECT BY PRIOR employee_id = manager_id
) t
LEFT JOIN employee_certificates c
  ON c.employee_id = t.employee_id
ORDER BY t.tree_level, t.employee_id;
~~~

Ở đây cây được dựng trong inline view trước, sau đó mới JOIN chứng chỉ. Kết quả cuối vẫn có thể có nhiều hàng cho một nhân viên nếu có nhiều chứng chỉ, nhưng **đường đi phân cấp không bị xây dựng trên nguồn đã nhân bản bởi bảng chứng chỉ**.

Nếu chỉ cần biết nhân viên có chứng chỉ hay không, dùng EXISTS hoặc aggregate để giữ một hàng mỗi nhân viên thay vì JOIN tất cả chứng chỉ.

### Dùng CTE để lọc tập đầu vào

~~~sql
WITH eligible_employees AS (
    SELECT employee_id, employee_name, manager_id, sort_order
    FROM lab_employees_tree
    WHERE employee_id > 0
)
SELECT employee_id, employee_name, manager_id, LEVEL
FROM eligible_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

CTE giúp làm rõ tập dữ liệu được dùng để xây cây. Hãy nhớ predicate trong CTE làm thay đổi nguồn hàng mà CONNECT BY có thể thấy; nếu loại một hàng cha, descendants có thể không còn đường đi từ root trong nguồn đã lọc.

## 10. Hiệu năng và index cho truy vấn phân cấp

Một hierarchical query có thể mở rộng qua nhiều cấp. Chi phí phụ thuộc số root, số con trung bình của mỗi node, độ sâu tối đa, độ rộng hàng và các biểu thức cần tính trên từng đường đi.

### Index trên cột khóa cha

Với điều kiện phổ biến:

~~~sql
CONNECT BY PRIOR employee_id = manager_id
~~~

Oracle cần tìm các hàng con có `MANAGER_ID` bằng `EMPLOYEE_ID` của hàng cha hiện tại. Index trên cột `MANAGER_ID` thường hữu ích:

~~~sql
CREATE INDEX ix_lab_emp_tree_manager
ON lab_employees_tree (manager_id);
~~~

Khóa chính `EMPLOYEE_ID` thường đã có index để tìm một node theo ID, hữu ích cho traversal ngược từ child lên parent. Tuy nhiên, index không bảo đảm query luôn dùng index; optimizer còn xét kích thước bảng, clustering factor, cardinality, stats và số hàng phải đọc.

### Kiểm soát độ sâu và số root

Nếu chỉ cần một nhánh, chọn root cụ thể thay vì khởi tạo mọi root. Nếu nghiệp vụ giới hạn số cấp, đặt điều kiện độ sâu trong CONNECT BY. Điều này giảm số node được mở rộng.

~~~sql
SELECT employee_id, employee_name, LEVEL
FROM lab_employees_tree
START WITH employee_id = :root_employee_id
CONNECT BY PRIOR employee_id = manager_id
       AND LEVEL <= :max_depth;
~~~

Bind `:root_employee_id` và `:max_depth` theo kiểu phù hợp. Giới hạn này là một phần yêu cầu nghiệp vụ; không cắt độ sâu tùy tiện nếu người dùng cần toàn bộ hậu duệ.

### Tránh biểu thức path quá rộng khi không cần

`SYS_CONNECT_BY_PATH` xây chuỗi cho mỗi hàng. Với cây sâu hoặc tên dài, chuỗi path tăng theo độ sâu và tiêu tốn CPU/bộ nhớ. Chỉ chọn path khi giao diện hoặc báo cáo cần nó; nếu chỉ cần node ID và LEVEL, đừng tạo path không cần thiết.

### Đo bằng execution plan

Ví dụ:

~~~sql
SELECT /*+ gather_plan_statistics */
       employee_id,
       employee_name,
       LEVEL
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

Đọc actual plan để xem access path, số hàng thực tế, buffer gets và các operation liên quan hierarchical processing. `EXPLAIN PLAN` chỉ đưa ra kế hoạch ước lượng, không đo số hàng/thời gian/TEMP thực tế. Quyền đọc cursor và thống kê phụ thuộc cấu hình database.

## 11. Khi nào dùng CONNECT BY, khi nào dùng recursive subquery factoring?

`START WITH ... CONNECT BY` là cú pháp Oracle quen thuộc, ngắn gọn cho truy vấn phân cấp theo quan hệ cha–con. Oracle cũng hỗ trợ **recursive subquery factoring** (recursive WITH clause), có thể biểu diễn traversal bằng anchor member và recursive member.

Ví dụ dạng recursive WITH:

~~~sql
WITH org_tree (employee_id, employee_name, manager_id, tree_level) AS (
    SELECT employee_id, employee_name, manager_id, 1
    FROM lab_employees_tree
    WHERE manager_id IS NULL

    UNION ALL

    SELECT child.employee_id,
           child.employee_name,
           child.manager_id,
           parent.tree_level + 1
    FROM lab_employees_tree child
    JOIN org_tree parent
      ON child.manager_id = parent.employee_id
)
SELECT employee_id, employee_name, manager_id, tree_level
FROM org_tree
ORDER BY tree_level, employee_id;
~~~

Recursive WITH thường hữu ích khi cần kết hợp nhiều phép tính/quan hệ trong mỗi vòng lặp hoặc muốn diễn đạt đệ quy theo cấu trúc SQL tổng quát. Oracle còn hỗ trợ các mệnh đề `SEARCH` và `CYCLE` trong recursive subquery factoring theo phiên bản. `CONNECT BY` có các pseudocolumn chuyên dụng như LEVEL, CONNECT_BY_ROOT và SYS_CONNECT_BY_PATH, nên rất tiện cho truy vấn cây truyền thống.

Không có quy tắc một cú pháp luôn nhanh hơn cú pháp kia. Chọn dựa trên yêu cầu, khả năng đọc, phiên bản Oracle, cycle handling và actual plan.

## 12. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Chỉ thấy root, không thấy con | Điều kiện CONNECT BY đặt sai hướng PRIOR hoặc nối sai cột | Kiểm tra `PRIOR parent_key = child_fk`. |
| Duyệt ngược lên quản lý nhưng kết quả đi xuống | PRIOR đặt nhầm phía | Với traversal lên cha, dùng `PRIOR child_parent_key = parent_key` theo mô hình cụ thể. |
| Hàng xuất hiện nhiều lần | Nhiều root/path hoặc nguồn bị nhân bản do JOIN | Xác định graph/tree, root và cardinality; dựng cây trước khi JOIN một-nhiều. |
| Kết quả không theo thứ tự nhánh | Dùng ORDER BY toàn cục hoặc không có ORDER BY | Dùng ORDER SIBLINGS BY khi cần giữ cấu trúc cây. |
| ORA-01436 | Dữ liệu có chu trình trong đường đi | Dùng NOCYCLE để truy vấn an toàn, kiểm tra và sửa dữ liệu cycle theo nghiệp vụ. |
| WHERE ẩn parent nhưng child vẫn xuất hiện | WHERE lọc hàng sau khi cây được dựng | Nếu muốn cắt nhánh, đặt predicate vào CONNECT BY. |
| Cây không có root | Root condition không khớp hoặc dữ liệu có cycle/parent sai | Kiểm tra START WITH, orphan rows và cycle. |
| Truy vấn quá nhiều hàng | Quá nhiều root, độ sâu lớn, quan hệ nhiều-nhiều hoặc thiếu điều kiện | Giới hạn root/độ sâu đúng nghiệp vụ; kiểm tra khóa nối và index. |
| Leaf flag không giống cấu trúc bảng | Leaf được xác định theo cây sau điều kiện traversal | Kiểm tra CONNECT BY predicate và tập nguồn được duyệt. |

## 13. Bài thực hành tổng hợp

Thực hiện trong schema học tập có quyền tạo bảng và quota phù hợp. Các lệnh DDL có implicit commit trong Oracle. Không chạy các lệnh xóa trên bảng nghiệp vụ thật.

### Bước 1: tạo cây tổ chức

~~~sql
CREATE TABLE lab_org_nodes (
    node_id       NUMBER(6) PRIMARY KEY,
    parent_id     NUMBER(6),
    node_name     VARCHAR2(80 CHAR) NOT NULL,
    display_order NUMBER(4),
    CONSTRAINT fk_lab_org_parent
        FOREIGN KEY (parent_id) REFERENCES lab_org_nodes(node_id)
);

INSERT INTO lab_org_nodes VALUES (1, NULL, 'Head Office', 1);
INSERT INTO lab_org_nodes VALUES (2, 1, 'Engineering', 1);
INSERT INTO lab_org_nodes VALUES (3, 1, 'Operations', 2);
INSERT INTO lab_org_nodes VALUES (4, 2, 'Platform', 1);
INSERT INTO lab_org_nodes VALUES (5, 2, 'Applications', 2);
INSERT INTO lab_org_nodes VALUES (6, 3, 'Finance', 1);
INSERT INTO lab_org_nodes VALUES (7, 3, 'Support', 2);
INSERT INTO lab_org_nodes VALUES (8, 5, 'Web Team', 1);
COMMIT;
~~~

### Bước 2: truy vấn toàn bộ cây

~~~sql
SELECT node_id,
       parent_id,
       node_name,
       LEVEL AS tree_level
FROM lab_org_nodes
START WITH parent_id IS NULL
CONNECT BY PRIOR node_id = parent_id
ORDER SIBLINGS BY display_order, node_name;
~~~

Giải thích vì sao `Head Office` ở LEVEL 1, `Engineering` ở LEVEL 2 và `Web Team` ở LEVEL 4.

### Bước 3: chỉ lấy một nhánh

~~~sql
SELECT node_id, parent_id, node_name, LEVEL
FROM lab_org_nodes
START WITH node_id = 2
CONNECT BY PRIOR node_id = parent_id
ORDER SIBLINGS BY display_order;
~~~

Kết quả phải giới hạn ở Engineering và các hậu duệ của nó; Operations không thuộc nhánh.

### Bước 4: lấy root, path và leaf

~~~sql
SELECT node_id,
       node_name,
       CONNECT_BY_ROOT node_name AS root_name,
       SYS_CONNECT_BY_PATH(node_name, ' / ') AS node_path,
       LEVEL,
       CONNECT_BY_ISLEAF AS is_leaf
FROM lab_org_nodes
START WITH parent_id IS NULL
CONNECT BY PRIOR node_id = parent_id
ORDER SIBLINGS BY display_order;
~~~

Xác định những hàng leaf và giải thích vì sao root có thể không phải leaf.

### Bước 5: giới hạn độ sâu

~~~sql
SELECT node_id, node_name, LEVEL
FROM lab_org_nodes
START WITH parent_id IS NULL
CONNECT BY PRIOR node_id = parent_id
       AND LEVEL <= 2
ORDER SIBLINGS BY display_order;
~~~

So sánh với `WHERE LEVEL <= 2` và giải thích khác biệt giữa dừng mở rộng cây và lọc output.

### Bước 6: duyệt từ node lên root

~~~sql
SELECT node_id, node_name, parent_id, LEVEL
FROM lab_org_nodes
START WITH node_id = 8
CONNECT BY PRIOR parent_id = node_id;
~~~

Kết quả đi từ Web Team lên Applications, Engineering rồi Head Office. Giải thích cách đọc `PRIOR parent_id = node_id`.

### Bước 7: kiểm tra orphan và cycle

Bảng lab có FK nên không thể chèn parent không tồn tại trong điều kiện constraint đang ENABLE. Hãy thử kiểm tra orphan bằng LEFT JOIN:

~~~sql
SELECT c.node_id, c.parent_id
FROM lab_org_nodes c
LEFT JOIN lab_org_nodes p
  ON p.node_id = c.parent_id
WHERE c.parent_id IS NOT NULL
  AND p.node_id IS NULL;
~~~

Để thử cycle, dùng riêng bảng `LAB_GRAPH` không có FK như phần NOCYCLE. Ghi nhận kết quả `CONNECT_BY_ISCYCLE` và lý do `NOCYCLE` không tự sửa dữ liệu.

### Bước 8: dọn dữ liệu

~~~sql
DROP TABLE lab_org_nodes PURGE;
~~~

Chỉ chạy nếu bạn đã tạo bảng trong schema thực hành và không cần giữ dữ liệu. Nếu đã tạo `LAB_GRAPH`, chỉ xóa bảng đó khi không còn cần dùng. `PURGE` bỏ qua Recycle Bin; DROP TABLE là DDL, không thể rollback như DML chưa commit.

## 14. Câu hỏi tự kiểm tra

1. **START WITH dùng để làm gì?** Chọn một hoặc nhiều hàng gốc để bắt đầu traversal.
2. **CONNECT BY định nghĩa điều gì?** Quan hệ giữa hàng cha hiện tại và hàng con/cha tiếp theo trong quá trình duyệt.
3. **`PRIOR employee_id = manager_id` có nghĩa gì?** Tìm hàng con có manager_id bằng employee_id của hàng cha hiện tại.
4. **Muốn đi từ nhân viên lên quản lý thì viết thế nào?** Với mô hình này, dùng `PRIOR manager_id = employee_id`.
5. **LEVEL bắt đầu từ mấy?** Root có LEVEL = 1.
6. **CONNECT_BY_ROOT trả về gì?** Giá trị biểu thức tại root của đường đi hiện tại.
7. **SYS_CONNECT_BY_PATH có tác dụng gì?** Tạo chuỗi path từ root đến hàng hiện tại.
8. **CONNECT_BY_ISLEAF = 1 nghĩa là gì?** Hàng hiện tại không có child tiếp theo trong cây theo điều kiện traversal.
9. **CONNECT_BY_ISCYCLE dùng với điều kiện nào?** Dùng trong hierarchical query có NOCYCLE để nhận diện hàng có child là ancestor.
10. **NOCYCLE có sửa dữ liệu sai không?** Không; nó ngăn truy vấn lặp vô hạn và cho phép quan sát đường đi có chu trình.
11. **ORDER BY khác ORDER SIBLINGS BY thế nào?** ORDER BY sắp toàn bộ kết quả; ORDER SIBLINGS BY sắp các anh/chị/em mà vẫn giữ thứ tự cây.
12. **WHERE có tự cắt toàn bộ descendants của hàng bị lọc không?** Không nhất thiết; WHERE lọc hàng output, còn predicate trong CONNECT BY có thể ngăn mở rộng nhánh.
13. **Vì sao JOIN bảng một-nhiều trước CONNECT BY có thể gây nhân bản cây?** JOIN được xử lý trước hierarchical processing nên một node có thể thành nhiều hàng đầu vào.
14. **Index nào thường hữu ích cho duyệt từ cha xuống con?** Index trên cột khóa cha ở hàng con, ví dụ MANAGER_ID.
15. **Khi nào cần cân nhắc recursive WITH?** Khi cần đệ quy linh hoạt hoặc các thao tác trong mỗi vòng lặp phức tạp; CONNECT BY tiện cho cây Oracle truyền thống.

Truy vấn cây trong Oracle cần ba quyết định rõ ràng: **bắt đầu từ đâu, đi theo quan hệ nào và dừng ở điều kiện nào**. `START WITH` chọn gốc, `CONNECT BY` cùng `PRIOR` xác định hướng nối, còn `LEVEL` và các pseudocolumn giúp mô tả vị trí của từng node. Khi dữ liệu có thể chứa cycle, nhiều parent hoặc JOIN một-nhiều, hãy kiểm soát phạm vi traversal và đọc execution plan để tránh kết quả nhân bản hoặc chi phí ngoài dự kiến.
