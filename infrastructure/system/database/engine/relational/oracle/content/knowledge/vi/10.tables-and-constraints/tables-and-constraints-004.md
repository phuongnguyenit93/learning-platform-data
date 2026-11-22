# FOREIGN KEY, quan hệ cha con và lựa chọn hành vi khi xóa trong Oracle Database

Trong cơ sở dữ liệu quan hệ, bảng `ORDERS` thường có một cột `CUSTOMER_ID` để chỉ khách hàng đã tạo đơn hàng. Một đơn hàng không nên tham chiếu đến khách hàng không tồn tại; đồng thời, nếu khách hàng bị xóa thì dữ liệu đơn hàng sẽ được xử lý thế nào? **`FOREIGN KEY` (khóa ngoại)** là ràng buộc Oracle Database dùng để bảo vệ những mối quan hệ đó.

Ba cách xử lý phổ biến khi xóa một hàng **bảng cha** trong Oracle là:

- **Mặc định — ngăn xóa khi còn hàng con tham chiếu:** Oracle từ chối thao tác xóa cha nếu hành động đó vi phạm khóa ngoại.
- **`ON DELETE CASCADE`:** xóa cha kéo theo việc xóa những hàng con tham chiếu.
- **`ON DELETE SET NULL`:** xóa cha giữ lại những hàng con nhưng đặt cột khóa ngoại tương ứng về `NULL`.

Đây là quyết định thiết kế dữ liệu, không đơn thuần là lựa chọn cú pháp. Nếu dùng `CASCADE` cho quan hệ khách hàng → hóa đơn, một lệnh `DELETE` sai có thể xóa cả lịch sử giao dịch. Nếu dùng `SET NULL` cho thông tin bắt buộc phải có cha, ứng dụng sẽ gặp lỗi hoặc dữ liệu mất ngữ cảnh. Bài học này giải thích cách khai báo, kiểm thử và chọn hành vi phù hợp trong Oracle Database.

> Ví dụ dùng bảng có tiền tố `DEMO_` và giả định một schema/PDB thực hành. Các lệnh `CREATE TABLE`, `INSERT`, `DELETE`, `ALTER TABLE` làm thay đổi dữ liệu hoặc cấu trúc; không chạy nguyên văn trên schema sản xuất. Oracle DDL thường thực hiện implicit commit, nên không nên xem `ROLLBACK` là cách hoàn tác toàn bộ các thao tác tạo/sửa bảng.

## 1. Quan hệ cha con trong cơ sở dữ liệu quan hệ

### 1.1. Parent table và child table là gì?

Xét mô hình khách hàng và đơn hàng:

```text
        DEMO_CUSTOMERS (bảng cha)
        +-------------+-----------+
        | CUSTOMER_ID | FULL_NAME |
        +-------------+-----------+
        | 1           | An        |
        | 2           | Bình      |
        +-------------+-----------+
              |
              | 1 khách hàng có nhiều đơn hàng
              |
              v
        DEMO_ORDERS (bảng con)
        +----------+-------------+--------------+
        | ORDER_ID | CUSTOMER_ID | TOTAL_AMOUNT |
        +----------+-------------+--------------+
        | 101      | 1           | 150000       |
        | 102      | 1           | 200000       |
        | 103      | 2           | 70000        |
        +----------+-------------+--------------+
```

- **Parent (cha):** `DEMO_CUSTOMERS`, có khóa chính `CUSTOMER_ID`.
- **Child (con):** `DEMO_ORDERS`, có khóa ngoại `CUSTOMER_ID` tham chiếu khóa của `DEMO_CUSTOMERS`.
- **Quan hệ một-nhiều (1:N):** một khách hàng có thể có nhiều đơn hàng; mỗi đơn hàng trong mô hình này liên kết với một khách hàng.
- **Tham chiếu hợp lệ:** `DEMO_ORDERS.CUSTOMER_ID = 1` hợp lệ khi có `DEMO_CUSTOMERS.CUSTOMER_ID = 1`.

Một hàng con có giá trị khóa ngoại khác `NULL` phải tham chiếu đến **giá trị khóa cha có thật** khi ràng buộc được kiểm tra. Nếu không, Oracle từ chối thao tác gây vi phạm, trừ những tình huống đặc biệt như constraint được hoãn kiểm tra hoặc bị vô hiệu hóa theo cấu hình quản trị.

### 1.2. Primary key, unique key và foreign key khác nhau

| Loại ràng buộc | Đặt trên bảng | Ý nghĩa |
| --- | --- | --- |
| `PRIMARY KEY` | Thường là bảng cha; cũng có thể ở bảng con | Định danh duy nhất từng hàng, các cột khóa không được `NULL` |
| `UNIQUE` | Có thể là bảng cha hoặc bảng con | Bảo đảm tính duy nhất theo quy tắc của Oracle; có thể dùng làm khóa được tham chiếu |
| `FOREIGN KEY` | Bảng con | Bảo đảm các giá trị khóa ngoại hợp lệ với khóa cha được tham chiếu |

Trong Oracle, khóa ngoại phải tham chiếu đến một khóa **`PRIMARY KEY` hoặc `UNIQUE` được xác định bằng constraint phù hợp** ở bảng cha. Không đủ để cột cha “trông có vẻ không trùng” hoặc chỉ được ứng dụng tự kiểm tra.

Khóa ngoại **không làm giá trị ở bảng con trở thành duy nhất**. Nhiều đơn hàng có thể cùng `CUSTOMER_ID=1`. Nếu muốn quan hệ một-một (1:1), có thể cần thêm `UNIQUE` trên cột khóa ngoại phía con và các điều kiện `NULL` thích hợp.

### 1.3. FOREIGN KEY kiểm tra hai hướng tác động

Khi thao tác với bảng **con**:

- `INSERT` hàng con có khóa ngoại trỏ tới cha chưa tồn tại: bị chặn.
- `UPDATE` khóa ngoại của hàng con sang giá trị không tồn tại ở cha: bị chặn.
- `DELETE` hàng con: thường được phép, không tự động xóa cha.

Khi thao tác với bảng **cha**:

- `DELETE` cha khi không còn con liên quan: thường được phép.
- `DELETE` cha khi còn con: phụ thuộc chính sách `ON DELETE` của khóa ngoại.
- `UPDATE` cột khóa cha đang được con tham chiếu: có thể bị chặn nếu tạo ra tham chiếu không hợp lệ; Oracle không cung cấp cú pháp `ON UPDATE CASCADE` trực tiếp giống một số hệ quản trị khác.

Trong tất cả trường hợp, quyền truy cập, các ràng buộc khác, trigger, trạng thái transaction và những điều kiện vận hành cũng có thể khiến thao tác thất bại.

## 2. Tạo khóa ngoại cơ bản trong Oracle

### 2.1. Tạo bảng cha có PRIMARY KEY

```sql
CREATE TABLE demo_customers (
    customer_id NUMBER(10) NOT NULL,
    full_name   VARCHAR2(100) NOT NULL,
    CONSTRAINT pk_demo_customers PRIMARY KEY (customer_id)
);
```

Tên `PK_DEMO_CUSTOMERS` giúp nhận diện ràng buộc khi đọc metadata và các thông báo lỗi. Nếu không đặt tên constraint, Oracle có thể tạo tên hệ thống như `SYS_C...`, khó liên hệ với nghiệp vụ.

### 2.2. Tạo bảng con có FOREIGN KEY

```sql
CREATE TABLE demo_orders (
    order_id     NUMBER(10) NOT NULL,
    customer_id  NUMBER(10) NOT NULL,
    total_amount NUMBER(12,2) NOT NULL,
    CONSTRAINT pk_demo_orders PRIMARY KEY (order_id),
    CONSTRAINT fk_demo_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_customers (customer_id)
);
```

Trong cú pháp:

- `FOREIGN KEY (customer_id)`: cột phía bảng **con**.
- `REFERENCES demo_customers(customer_id)`: bảng và cột khóa phía **cha**.
- Không có `ON DELETE ...`: hành vi xóa cha mặc định là **không cho phép xóa nếu còn con tham chiếu**.
- `customer_id NUMBER(10) NOT NULL`: một đơn hàng trong ví dụ bắt buộc thuộc về một khách hàng.

Cột ở phía con và phía cha phải có kiểu dữ liệu tương thích cho ràng buộc, và các cột được tham chiếu phải tạo thành khóa cha phù hợp. Oracle còn cho phép tham chiếu đến khóa duy nhất nhiều cột; ví dụ composite key được trình bày phía sau.

### 2.3. Dạng khai báo inline

Khi khóa ngoại chỉ có một cột, Oracle cũng hỗ trợ khai báo theo cấu trúc inline trong `CREATE TABLE`:

```sql
CREATE TABLE demo_order_notes (
    note_id    NUMBER(10) PRIMARY KEY,
    order_id   NUMBER(10)
               CONSTRAINT fk_demo_note_order
               REFERENCES demo_orders(order_id),
    note_text  VARCHAR2(200)
);
```

Dạng inline ngắn hơn cho trường hợp một cột. Với khóa ngoại **nhiều cột**, thường khai báo out-of-line bằng `CONSTRAINT ... FOREIGN KEY (col1, col2) REFERENCES ...`.

### 2.4. Thêm khóa ngoại sau khi bảng đã tồn tại

Nếu bảng đã được tạo mà chưa có ràng buộc, dùng `ALTER TABLE ... ADD CONSTRAINT`:

```sql
ALTER TABLE demo_orders
    ADD CONSTRAINT fk_demo_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_customers (customer_id);
```

**Lưu ý:** đây là cú pháp minh họa cho trường hợp bảng con **chưa có** constraint cùng tên. Nếu đã chạy mục 2.2 thì ràng buộc đã tồn tại; không chạy lại `ADD CONSTRAINT`. Với bảng đã có dữ liệu, Oracle có thể kiểm tra các dòng hiện hữu khi bật constraint theo trạng thái `VALIDATE`, và sẽ báo lỗi nếu có dữ liệu vi phạm.

Không cần tạo khóa ngoại ở cả hai bảng: ràng buộc nằm trên **bảng con**, nhưng vẫn kiểm soát những thay đổi đối với khóa được tham chiếu ở **bảng cha**.

## 3. Hành vi mặc định: chặn xóa cha nếu còn con

### 3.1. Chuẩn bị dữ liệu

Với hai bảng ở mục 2, chạy:

```sql
INSERT INTO demo_customers (customer_id, full_name)
VALUES (1, 'An');

INSERT INTO demo_customers (customer_id, full_name)
VALUES (2, 'Binh');

INSERT INTO demo_orders (order_id, customer_id, total_amount)
VALUES (101, 1, 150000);

INSERT INTO demo_orders (order_id, customer_id, total_amount)
VALUES (102, 1, 200000);

INSERT INTO demo_orders (order_id, customer_id, total_amount)
VALUES (103, 2, 70000);

COMMIT;
```

Bây giờ hai đơn hàng 101, 102 cùng tham chiếu khách hàng 1.

### 3.2. Xóa cha sẽ bị từ chối

```sql
DELETE FROM demo_customers
WHERE customer_id = 1;
```

Khi constraint mặc định đang được bật và kiểm tra ngay, Oracle báo lỗi dạng:

```text
ORA-02292: integrity constraint (SCHEMA.FK_DEMO_ORDERS_CUSTOMER)
           violated - child record found
```

Phần `SCHEMA` là tên schema thực tế trong thông báo. Ý nghĩa lỗi: Oracle tìm thấy ít nhất một hàng con tham chiếu đến khóa cha sắp bị xóa. Không có hàng cha nào bị xóa bởi câu lệnh thất bại đó.

Đây là cơ chế bảo vệ **referential integrity — tính toàn vẹn tham chiếu**: không tạo các đơn hàng với `CUSTOMER_ID=1` mà không còn khách hàng 1.

### 3.3. Muốn xóa cha, hãy xử lý con trước

Một lựa chọn nghiệp vụ là xóa có kiểm soát:

```sql
SAVEPOINT before_demo_delete;

DELETE FROM demo_orders
WHERE customer_id = 1;

DELETE FROM demo_customers
WHERE customer_id = 1;

-- Kiểm tra sau hai lệnh DELETE, trước khi COMMIT.
SELECT *
FROM demo_customers
ORDER BY customer_id;

SELECT *
FROM demo_orders
ORDER BY order_id;

-- Hoàn tác các DELETE trong bài thử.
ROLLBACK TO before_demo_delete;
```

Ở thời điểm trước `ROLLBACK`, các đơn hàng 101 và 102 đã bị xóa, rồi mới có thể xóa khách hàng 1. `ROLLBACK TO before_demo_delete` đưa các thay đổi DML phát sinh sau savepoint trở lại, nếu không có thao tác DDL/COMMIT chen vào.

**Thứ tự thao tác quan trọng** trong mô hình ràng buộc kiểm tra ngay: xử lý **con trước, cha sau**. Nếu nghiệp vụ yêu cầu giữ đơn hàng, không nên tùy tiện xóa chúng; có thể cần chính sách khác hoặc không cho xóa khách hàng.

### 3.4. Vì sao không có ON DELETE RESTRICT trong cú pháp Oracle?

Một số hệ quản trị cơ sở dữ liệu cho phép ghi `ON DELETE RESTRICT` hoặc `ON DELETE NO ACTION`. Với constraint `FOREIGN KEY` trong Oracle SQL, cú pháp hành vi xóa được hỗ trợ là:

- Không khai báo `ON DELETE`: dùng hành vi mặc định chặn xóa cha khi tồn tại con vi phạm.
- `ON DELETE CASCADE`.
- `ON DELETE SET NULL`.

Không nên sao chép nguyên `ON DELETE RESTRICT`, `NO ACTION` hoặc `SET DEFAULT` từ cú pháp của hệ quản trị khác vào `CREATE TABLE` Oracle và kỳ vọng nó được chấp nhận.

Trong cách giải thích ở mức nghiệp vụ, hành vi mặc định thường được gọi là “restrict/no action”, nhưng đó **không phải keyword cần viết thêm** trong câu lệnh Oracle.

## 4. ON DELETE CASCADE: xóa cha kéo theo xóa con

### 4.1. Cách khai báo

Ví dụ các phòng ban và nhân viên theo một chính sách **xóa phòng ban kéo theo xóa các dòng nhân viên mẫu** (chỉ phù hợp cho dữ liệu demo, không mặc định là thiết kế tốt cho hồ sơ nhân sự):

```sql
CREATE TABLE demo_departments (
    department_id NUMBER(10) PRIMARY KEY,
    department_name VARCHAR2(100) NOT NULL
);

CREATE TABLE demo_department_members (
    member_id NUMBER(10) PRIMARY KEY,
    department_id NUMBER(10) NOT NULL,
    member_label VARCHAR2(100) NOT NULL,
    CONSTRAINT fk_demo_member_department
        FOREIGN KEY (department_id)
        REFERENCES demo_departments(department_id)
        ON DELETE CASCADE
);
```

Nhìn vào cuối định nghĩa khóa ngoại:

```sql
ON DELETE CASCADE
```

Nó áp dụng khi **xóa hàng cha** khỏi `DEMO_DEPARTMENTS`; những hàng `DEMO_DEPARTMENT_MEMBERS` tham chiếu đến cha đó sẽ được Oracle xóa theo.

### 4.2. Thử thao tác xóa

```sql
INSERT INTO demo_departments VALUES (10, 'Research');
INSERT INTO demo_departments VALUES (20, 'Support');

INSERT INTO demo_department_members VALUES (1001, 10, 'Member A');
INSERT INTO demo_department_members VALUES (1002, 10, 'Member B');
INSERT INTO demo_department_members VALUES (1003, 20, 'Member C');

COMMIT;

SAVEPOINT before_cascade;

DELETE FROM demo_departments
WHERE department_id = 10;

SELECT member_id, department_id, member_label
FROM demo_department_members
ORDER BY member_id;

ROLLBACK TO before_cascade;
```

Sau lệnh `DELETE`, trong cùng transaction, các dòng thành viên **1001** và **1002** biến mất vì tham chiếu phòng ban 10; thành viên **1003** thuộc phòng ban 20 vẫn còn. Sau `ROLLBACK TO before_cascade`, dữ liệu trở lại như trước bài thử.

Hệ quả quan trọng:

> Với `ON DELETE CASCADE`, một lệnh `DELETE FROM parent ...` có thể xóa **nhiều hàng ở bảng con** mặc dù câu lệnh không viết trực tiếp `DELETE FROM child`.

### 4.3. Cascading có thể đi qua nhiều cấp

Xét cấu trúc:

```text
DEMO_CUSTOMERS
     |
     | FK của ORDERS: ON DELETE CASCADE
     v
DEMO_ORDERS
     |
     | FK của ORDER_ITEMS: ON DELETE CASCADE
     v
DEMO_ORDER_ITEMS
```

Nếu cả hai khóa ngoại đều dùng `ON DELETE CASCADE`, xóa một customer có thể làm xóa các orders của customer đó, rồi xóa tiếp các order items của những orders này.

Một ví dụ DDL độc lập để minh họa chuỗi (sử dụng tên bảng khác nhằm tránh thay đổi bảng đã tạo trước):

```sql
CREATE TABLE demo_sales_customers (
    customer_id NUMBER PRIMARY KEY
);

CREATE TABLE demo_sales_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    CONSTRAINT fk_demo_sales_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_sales_customers(customer_id)
        ON DELETE CASCADE
);

CREATE TABLE demo_sales_order_items (
    item_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    quantity NUMBER NOT NULL,
    CONSTRAINT fk_demo_sales_item_order
        FOREIGN KEY (order_id)
        REFERENCES demo_sales_orders(order_id)
        ON DELETE CASCADE
);
```

Với thiết kế này, nếu xóa một hàng `DEMO_SALES_CUSTOMERS` đã có dữ liệu con, các đơn hàng và dòng chi tiết liên quan cũng có thể bị xóa.

Tính năng này thuận tiện cho dữ liệu **thực sự phụ thuộc vòng đời vào cha** như các dòng chi tiết thuộc một bản ghi tạm. Tuy nhiên, với hóa đơn, nhật ký thanh toán hoặc dữ liệu cần lưu trữ theo luật/chính sách, xóa dây chuyền có thể không phù hợp.

### 4.4. Những tác động vận hành của CASCADE

Dùng `CASCADE` cần chú ý:

- **Số lượng hàng bị ảnh hưởng:** số hàng con có thể lớn hơn nhiều so với số hàng cha mà ứng dụng chủ động xóa.
- **Redo và undo:** Oracle cần ghi nhận các thay đổi để phục hồi/rollback; một thao tác xóa lớn có thể tốn I/O và không gian undo.
- **Khóa và giao dịch đồng thời:** các hàng và cấu trúc liên quan phải được bảo vệ theo cơ chế concurrency của Oracle.
- **Trigger:** DML liên quan có thể kích hoạt các trigger áp dụng theo quy tắc của Oracle, tạo thêm logic nghiệp vụ/tác dụng phụ.
- **Chuỗi phụ thuộc:** cần xét toàn bộ cây khóa ngoại chứ không chỉ một bảng con trực tiếp.
- **Thời gian thực thi:** một lần xóa cha đơn giản về SQL không đồng nghĩa chi phí database nhỏ.

Nếu dữ liệu được bảo vệ bởi yêu cầu audit, retention hoặc phục hồi nghiệp vụ, hãy thiết kế rõ cách xóa, lưu trữ hoặc vô hiệu hóa logic (soft delete) thay vì dùng CASCADE chỉ vì câu lệnh ngắn.

### 4.5. CASCADE không có nghĩa xóa cha khi xóa con

`ON DELETE CASCADE` hoạt động theo hướng:

```text
DELETE parent  --->  Oracle DELETE các child tham chiếu
DELETE child   -X->  Không tự DELETE parent
```

Nếu xóa một dòng `DEMO_DEPARTMENT_MEMBERS`, phòng ban tương ứng vẫn còn. Khóa ngoại không có cơ chế “dọn cha không còn con” tự động.

## 5. ON DELETE SET NULL: giữ con và bỏ liên kết cha

### 5.1. Mô hình phù hợp

Giả sử một tác vụ có thể được gắn với một dự án, nhưng vẫn có ý nghĩa nếu dự án bị xóa. Khi đó bảng `DEMO_TASKS` có thể cho phép `PROJECT_ID` bằng `NULL`.

```sql
CREATE TABLE demo_projects (
    project_id NUMBER(10) PRIMARY KEY,
    project_name VARCHAR2(100) NOT NULL
);

CREATE TABLE demo_tasks (
    task_id NUMBER(10) PRIMARY KEY,
    project_id NUMBER(10),
    task_title VARCHAR2(150) NOT NULL,
    CONSTRAINT fk_demo_task_project
        FOREIGN KEY (project_id)
        REFERENCES demo_projects(project_id)
        ON DELETE SET NULL
);
```

Lưu ý: `PROJECT_ID` **không được khai báo `NOT NULL`**. Nếu muốn Oracle đặt nó về `NULL` khi xóa cha, cột cần cho phép trạng thái đó.

### 5.2. Thử xóa dự án

```sql
INSERT INTO demo_projects (project_id, project_name)
VALUES (50, 'Internal Portal');

INSERT INTO demo_tasks (task_id, project_id, task_title)
VALUES (501, 50, 'Write documentation');

INSERT INTO demo_tasks (task_id, project_id, task_title)
VALUES (502, 50, 'Review UI');

COMMIT;

SAVEPOINT before_set_null;

DELETE FROM demo_projects
WHERE project_id = 50;

SELECT task_id, project_id, task_title
FROM demo_tasks
ORDER BY task_id;

ROLLBACK TO before_set_null;
```

Sau khi xóa cha và trước khi rollback:

```text
TASK_ID  PROJECT_ID  TASK_TITLE
-------  ----------  -------------------
501      NULL        Write documentation
502      NULL        Review UI
```

Hai hàng tác vụ **không bị xóa**; Oracle chỉ cập nhật khóa ngoại `PROJECT_ID` thành `NULL`. Sau rollback, dự án và các liên kết được khôi phục trong transaction thực hành.

### 5.3. SET NULL có nghĩa nghiệp vụ gì?

`NULL` trong cột khóa ngoại có thể biểu diễn:

- Tác vụ chưa được phân dự án.
- Mối liên hệ không còn áp dụng.
- Cha cũ đã bị xóa và yêu cầu hệ thống giữ lại dữ liệu con.

Nhưng `NULL` **không nói rõ nguyên nhân**, cũng không giữ lại ID/tên của cha đã xóa. Nếu cần biết trước đây task thuộc dự án nào, nên lưu lịch sử hoặc audit bằng thiết kế riêng.

Không nên dùng `SET NULL` trong mô hình mà một hàng con **bắt buộc luôn thuộc cha**, ví dụ khoản thanh toán phải gắn một hóa đơn hợp lệ theo quy tắc nghiệp vụ.

### 5.4. Nếu khóa ngoại là NOT NULL?

Giả sử `DEMO_TASKS.PROJECT_ID` được khai báo `NOT NULL` mà FK vẫn là `ON DELETE SET NULL`. Khi xóa một dự án đang có task, Oracle phải đặt `PROJECT_ID` về `NULL` để đáp ứng chính sách FK, nhưng điều đó vi phạm ràng buộc `NOT NULL`.

Kết quả là thao tác **có thể thất bại do vi phạm ràng buộc null** (chẳng hạn `ORA-01407`) thay vì thành công. Khi thiết kế, hành vi `SET NULL` cần nhất quán với toàn bộ `NOT NULL`, `CHECK` và các ràng buộc khác trên bảng con.

### 5.5. SET NULL khác dữ liệu mồ côi

Một hàng con có `PROJECT_ID=NULL` **không phải tham chiếu sai đến một cha không tồn tại** theo ngữ nghĩa SQL của một FK đơn cột cho phép NULL. Nó đơn giản là **không có liên kết cha**.

Ngược lại, một hàng con có `PROJECT_ID=50` khi không còn `DEMO_PROJECTS.PROJECT_ID=50` là một tham chiếu không hợp lệ nếu constraint được bật và kiểm tra.

Sự khác nhau này quan trọng trong báo cáo:

```sql
SELECT COUNT(*) AS unassigned_tasks
FROM demo_tasks
WHERE project_id IS NULL;
```

Câu truy vấn trên đếm task không có project liên kết; không tự khẳng định chúng “sai dữ liệu”.

## 6. So sánh ba lựa chọn ON DELETE

| Tiêu chí | Mặc định (không khai báo ON DELETE) | `ON DELETE CASCADE` | `ON DELETE SET NULL` |
| --- | --- | --- | --- |
| Khi cha không có con | Xóa cha | Xóa cha | Xóa cha |
| Khi cha còn con | **Chặn xóa cha** nếu tạo vi phạm FK | **Xóa các con liên quan**, rồi xóa cha | **Giữ các con**, đặt FK về `NULL` |
| Dữ liệu con còn tồn tại? | Có, vì lệnh xóa cha thất bại | Không còn các con tham chiếu cha bị xóa | Có |
| Cột FK cần nullable? | Không bắt buộc | Không bắt buộc | **Có**, nếu cần xóa cha khi còn con |
| Nguy cơ nghiệp vụ | Không thể xóa cha trước khi xử lý con | Xóa dây chuyền, có thể mất dữ liệu quan trọng | Mất liên kết lịch sử, phải hiểu ngữ nghĩa `NULL` |
| Tình huống phù hợp | Đơn hàng/hóa đơn cần bảo toàn tham chiếu | Dữ liệu phụ thuộc hoàn toàn vào cha | Liên kết tùy chọn, con vẫn có ý nghĩa độc lập |

### 6.1. Cách chọn theo quan hệ nghiệp vụ

**Chọn mặc định** nếu hàng con **không thể tồn tại hợp lệ khi thiếu hàng cha**, và việc xóa cha phải được người dùng hoặc workflow quản lý rõ ràng. Ví dụ: không cho xóa khách hàng khi còn hợp đồng đang có hiệu lực.

**Chọn `CASCADE`** nếu hàng con thật sự là **một phần của vòng đời hàng cha** và không có giá trị khi cha biến mất. Ví dụ: các dòng cấu hình tạm, dòng chi tiết của một bản ghi nháp (khi chính sách xóa dữ liệu cho phép).

**Chọn `SET NULL`** nếu con có thể tiếp tục tồn tại **không gắn với cha**, và ứng dụng chấp nhận trạng thái chưa phân công/không liên kết. Ví dụ: task có thể tiếp tục tồn tại sau khi dự án thử nghiệm bị xóa.

**Không chọn hành vi theo thói quen.** Cần hỏi: nếu người dùng xóa cha, dữ liệu con có còn phải truy xuất phục vụ báo cáo, kiểm toán, đối soát hay yêu cầu pháp lý hay không?

### 6.2. Nếu không muốn xóa dữ liệu vật lý?

Một số nghiệp vụ chỉ muốn ngừng sử dụng hàng cha mà vẫn giữ lịch sử. Có thể thiết kế **soft delete**:

```sql
ALTER TABLE demo_customers
ADD (is_active CHAR(1) DEFAULT 'Y' NOT NULL);

ALTER TABLE demo_customers
ADD CONSTRAINT chk_demo_customer_active
    CHECK (is_active IN ('Y', 'N'));
```

Sau đó thay thao tác xóa vật lý bằng cập nhật trạng thái:

```sql
UPDATE demo_customers
SET is_active = 'N'
WHERE customer_id = 1;
```

Cách này giữ nguyên hàng cha và tham chiếu FK. Tuy nhiên, ứng dụng phải thống nhất cách lọc/hiển thị dữ liệu đã ngừng hoạt động, xử lý uniqueness và chính sách lưu trữ. Soft delete là thiết kế nghiệp vụ riêng, **không phải một tùy chọn `ON DELETE` của Oracle**.

## 7. Khóa ngoại với NULL và khóa ghép

### 7.1. FOREIGN KEY có thể cho phép NULL

Xét một bảng con:

```sql
CREATE TABLE demo_optional_contacts (
    contact_id   NUMBER PRIMARY KEY,
    customer_id  NUMBER,
    contact_name VARCHAR2(100),
    CONSTRAINT fk_demo_contact_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_customers(customer_id)
);
```

Vì `CUSTOMER_ID` không có `NOT NULL`, các giá trị sau về mặt khóa ngoại có thể hợp lệ:

- `CUSTOMER_ID = 1` khi có hàng cha 1.
- `CUSTOMER_ID = 2` khi có hàng cha 2.
- `CUSTOMER_ID = NULL` khi contact chưa được gắn với customer.

Giá trị `CUSTOMER_ID = 9999` không được chấp nhận nếu không có cha 9999, khi constraint bật và kiểm tra ngay.

Nếu nghiệp vụ đòi một contact luôn phải thuộc customer, khai báo thêm `NOT NULL` cho cột con.

### 7.2. Composite foreign key (khóa ngoại nhiều cột)

Một số bảng dùng khóa cha nhiều cột, ví dụ mã kho hàng chỉ duy nhất trong từng vùng:

```sql
CREATE TABLE demo_warehouses (
    region_id     NUMBER(10) NOT NULL,
    warehouse_id  NUMBER(10) NOT NULL,
    warehouse_name VARCHAR2(100),
    CONSTRAINT pk_demo_warehouses
        PRIMARY KEY (region_id, warehouse_id)
);

CREATE TABLE demo_stock_moves (
    move_id      NUMBER(10) PRIMARY KEY,
    region_id    NUMBER(10),
    warehouse_id NUMBER(10),
    quantity     NUMBER(10) NOT NULL,
    CONSTRAINT fk_demo_move_warehouse
        FOREIGN KEY (region_id, warehouse_id)
        REFERENCES demo_warehouses(region_id, warehouse_id)
        ON DELETE SET NULL
);
```

Với khóa ghép, **thứ tự các cột con phải tương ứng với thứ tự các cột của khóa cha**. Một giá trị vùng + mã kho được kiểm tra theo cặp, không phải hai ràng buộc độc lập.

### 7.3. Khóa ghép có thành phần NULL

Trong Oracle, với composite foreign key, nếu **một hoặc nhiều thành phần khóa ngoại là `NULL`**, cơ chế kiểm tra tham chiếu có quy tắc xử lý khác với trường hợp tất cả thành phần khác `NULL`. Vì vậy, một tổ hợp có một phần null có thể không yêu cầu tìm đủ một hàng cha khớp như cặp khóa hoàn chỉnh.

Nếu nghiệp vụ yêu cầu **hoặc cả hai cột đều có giá trị, hoặc cả hai cùng NULL**, có thể bổ sung ràng buộc:

```sql
ALTER TABLE demo_stock_moves
ADD CONSTRAINT chk_demo_warehouse_pair
CHECK (
    (region_id IS NULL AND warehouse_id IS NULL)
    OR
    (region_id IS NOT NULL AND warehouse_id IS NOT NULL)
);
```

Khi dùng `ON DELETE SET NULL` cho khóa ghép, cần bảo đảm các cột FK chấp nhận null theo kết quả mong muốn, và cân nhắc rằng việc null hóa một phần hay toàn bộ liên kết phải phù hợp mô hình dữ liệu.

### 7.4. Khóa ngoại tự tham chiếu

Một bảng có thể là **cha và con của chính nó**, ví dụ nhân viên có mã người quản lý:

```sql
CREATE TABLE demo_org_units (
    unit_id        NUMBER PRIMARY KEY,
    parent_unit_id NUMBER,
    unit_name      VARCHAR2(100) NOT NULL,
    CONSTRAINT fk_demo_org_parent
        FOREIGN KEY (parent_unit_id)
        REFERENCES demo_org_units(unit_id)
        ON DELETE SET NULL
);
```

Trong ví dụ này, xóa đơn vị cha có thể khiến các đơn vị con trực tiếp mất liên kết cha và được giữ lại. Nếu chọn `CASCADE` cho quan hệ phân cấp, phải cân nhắc tác động xóa dây chuyền đối với toàn cây.

Khóa ngoại tự tham chiếu tự nó **không ngăn mọi chu trình logic** phức tạp trong cấu trúc phân cấp. Nếu ứng dụng yêu cầu đồ thị không có chu trình (acyclic), có thể cần kiểm tra bổ sung trong tầng nghiệp vụ hoặc cơ chế được thiết kế riêng.

## 8. Lỗi Oracle thường gặp với FOREIGN KEY

### 8.1. ORA-02291: parent key not found

Ví dụ:

```sql
INSERT INTO demo_orders (order_id, customer_id, total_amount)
VALUES (104, 9999, 100000);
```

Nếu không có customer 9999, Oracle thông thường báo:

```text
ORA-02291: integrity constraint (...) violated - parent key not found
```

**Ý nghĩa:** hàng con được thêm hoặc cập nhật với khóa ngoại không có cha hợp lệ.

Hướng xử lý:

1. Xác minh `CUSTOMER_ID` có đúng giá trị được gửi hay không.
2. Xác minh hàng cha tồn tại trong **đúng schema/PDB**.
3. Nếu đang trong transaction, xem thứ tự tạo cha/con và trạng thái commit/visibility.
4. Không tắt FK chỉ để làm cho một dòng sai vượt qua bước kiểm tra.

### 8.2. ORA-02292: child record found

Ví dụ:

```sql
DELETE FROM demo_customers WHERE customer_id = 1;
```

Khi còn đơn hàng trỏ về customer 1 và FK mặc định đang có hiệu lực:

```text
ORA-02292: integrity constraint (...) violated - child record found
```

**Ý nghĩa:** một hoặc nhiều hàng con còn tham chiếu khóa cha đang bị xóa/sửa.

Hướng xử lý:

1. Tìm đúng constraint được nêu trong lỗi.
2. Truy vấn metadata để biết bảng con và cột FK.
3. Kiểm tra các hàng con thực tế.
4. Chọn chính sách nghiệp vụ: giữ cha, xử lý con có kiểm soát, hoặc thiết kế lại hành vi `ON DELETE` khi thật sự cần.

Không nên xem `ORA-02292` như một lỗi hệ thống cần “tắt đi” bằng `DISABLE CONSTRAINT`. Đây thường là dấu hiệu cơ chế bảo vệ dữ liệu đang hoạt động đúng.

### 8.3. ORA-02270: no matching unique or primary key

Lỗi này có thể xuất hiện khi tạo FK tham chiếu đến cột hoặc bộ cột cha **không được bảo vệ bởi ràng buộc `PRIMARY KEY` hoặc `UNIQUE` phù hợp**.

Ví dụ bảng cha có cột `CATEGORY_NAME` nhưng không có `UNIQUE`, rồi bảng con tham chiếu đến cột đó. Dù ứng dụng tin rằng tên category không trùng, Oracle không có khóa cha hợp lệ để ràng buộc.

Giải pháp là xác định candidate key đúng, tạo constraint cha phù hợp nếu dữ liệu hiện hữu đáp ứng tính duy nhất, rồi mới tạo FK.

### 8.4. ORA-02298 khi bật kiểm tra dữ liệu cũ

Nếu một bảng con đã chứa các giá trị tham chiếu không hợp lệ vì constraint trước đó bị vô hiệu hóa hoặc chưa validate, việc bật `ENABLE VALIDATE` có thể thất bại:

```text
ORA-02298: cannot validate (...) - parent keys not found
```

Cần xác định và xử lý các hàng con không có cha theo chính sách dữ liệu, không giả định rằng thêm FK sẽ tự động sửa dữ liệu cũ.

### 8.5. Lỗi khác không nhất thiết do FK

Một thao tác `ON DELETE SET NULL` có thể gặp lỗi vì cột con `NOT NULL`, trigger, CHECK constraint hoặc điều kiện storage/transaction. Khi thấy câu lệnh `DELETE` thất bại, cần đọc **mã lỗi thực tế**, tên constraint và log phù hợp; không quy mọi lỗi xóa cha về `ORA-02292`.

## 9. Tác động của FOREIGN KEY tới hiệu năng và khóa

### 9.1. Oracle không tự tạo index trên cột khóa ngoại

Khi khai báo:

```sql
CONSTRAINT fk_demo_orders_customer
FOREIGN KEY (customer_id)
REFERENCES demo_customers(customer_id)
```

Oracle **không mặc định tự tạo một index trên `DEMO_ORDERS.CUSTOMER_ID` chỉ vì có FK**. Trong nhiều workload, DBA sẽ cân nhắc thêm index:

```sql
CREATE INDEX idx_demo_orders_customer
ON demo_orders(customer_id);
```

Index này có thể giúp:

- Tìm các hàng con của một hàng cha, ví dụ `WHERE customer_id = :id`.
- Kiểm tra tham chiếu khi xóa cha hoặc sửa khóa cha.
- Giảm rủi ro quét bảng con và tình trạng tranh chấp/locking không cần thiết trong các workload đồng thời.
- Hỗ trợ truy vấn join cha–con khi optimizer đánh giá index có lợi.

Tuy vậy, **không phải mọi FK đều bắt buộc phải có index riêng**. Nếu bảng con rất nhỏ, ít cập nhật, hoặc đã có composite index với khóa ngoại nằm ở phần đầu phù hợp, index mới có thể không mang lại lợi ích đáng kể và còn làm tăng chi phí `INSERT`/`UPDATE`/`DELETE`.

### 9.2. Thiếu index FK có thể ảnh hưởng concurrency

Trong một số trường hợp Oracle cần bảo vệ tính toàn vẹn khi thao tác với khóa cha, việc không có index phù hợp trên child FK có thể dẫn đến công việc kiểm tra tốn kém hoặc lock trên bảng con gây tranh chấp với các transaction khác.

Ví dụ:

- Transaction A chuẩn bị xóa một customer.
- Transaction B đang ghi thêm nhiều orders trong child table.
- Oracle cần bảo đảm việc kiểm tra/duy trì FK nhất quán giữa hai transaction.

Thời gian chờ cụ thể phụ thuộc Oracle release, loại DML, chỉ mục, isolation và mức tải. Không nên kết luận một câu `DELETE` chậm chỉ từ việc “FK chưa có index”; hãy quan sát execution plan, wait events, locking và dữ liệu thực tế.

### 9.3. Cascade delete có thể xóa rất nhiều hàng

`ON DELETE CASCADE` có thể mở rộng thao tác xóa từ một hàng cha thành hàng nghìn hoặc hàng triệu hàng con. Khi đó:

- Tạo thêm **undo/redo** và I/O.
- Có thể kéo dài giao dịch và thời gian giữ lock.
- Có thể gây khó khăn cho việc phục hồi ở cấp nghiệp vụ nếu xóa nhầm.
- Tác động tới trigger, materialized view log, đồng bộ và các tác vụ liên quan tùy cấu hình.

Với dữ liệu lớn, cần có chiến lược bảo trì và kiểm tra mức độ ảnh hưởng trước khi xóa. Tránh thực thi một thao tác xóa dây chuyền trên production chỉ vì cú pháp SQL có vẻ đơn giản.

### 9.4. Query đếm con trước khi xóa

Để biết phạm vi bị ảnh hưởng với một khách hàng:

```sql
SELECT customer_id, COUNT(*) AS order_count
FROM demo_orders
WHERE customer_id = 1
GROUP BY customer_id;
```

Với nhiều cấp quan hệ, cần đếm cả bảng con ở tầng tiếp theo. Kết quả đếm tại một thời điểm **không bảo đảm số lượng khi xóa thực tế sẽ y hệt**, vì session khác có thể tiếp tục ghi dữ liệu. Nếu thao tác quan trọng, nên có quy trình transaction và điều kiện khóa/đồng thời rõ ràng.

## 10. Foreign key, transaction và DEFERRABLE

### 10.1. Thông thường Oracle kiểm tra ngay

Constraint được tạo không có tùy chọn đặc biệt thường là **`NOT DEFERRABLE`**: Oracle kiểm tra tính hợp lệ tại thời điểm thao tác, theo quy tắc thực thi của constraint.

Ví dụ cố chèn đơn hàng trỏ tới customer chưa tồn tại:

```sql
INSERT INTO demo_orders (order_id, customer_id, total_amount)
VALUES (105, 500, 250000);
```

Lệnh có thể bị từ chối ngay vì không có customer 500. Dù ứng dụng dự định chèn customer 500 trong câu SQL tiếp theo, FK thông thường không cho tạm tồn tại tham chiếu sai.

### 10.2. DEFERRABLE cho phép trì hoãn kiểm tra phù hợp

Đối với những luồng nhập dữ liệu phức tạp, Oracle hỗ trợ khai báo constraint **`DEFERRABLE`**, cho phép trì hoãn việc kiểm tra đến thời điểm commit khi transaction đặt constraint ở trạng thái deferred.

Ví dụ với một cặp bảng riêng cho bài học:

```sql
CREATE TABLE demo_import_parents (
    parent_id NUMBER PRIMARY KEY
);

CREATE TABLE demo_import_children (
    child_id NUMBER PRIMARY KEY,
    parent_id NUMBER NOT NULL,
    CONSTRAINT fk_demo_import_parent
        FOREIGN KEY (parent_id)
        REFERENCES demo_import_parents(parent_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
```

Trong transaction có thể đổi chế độ kiểm tra với một constraint đã khai báo deferrable:

```sql
SET CONSTRAINTS fk_demo_import_parent DEFERRED;

INSERT INTO demo_import_children (child_id, parent_id)
VALUES (1, 900);

INSERT INTO demo_import_parents (parent_id)
VALUES (900);

COMMIT;
```

Vì hàng cha được thêm **trước COMMIT**, trạng thái cuối của transaction có thể thỏa FK khi kiểm tra deferred. Nếu đến lúc commit mà vẫn thiếu cha, Oracle sẽ báo lỗi và transaction cần được xử lý theo quy tắc hiện hành; không nên coi hoãn kiểm tra là bỏ qua constraint.

**Chú ý:** một constraint khai báo `NOT DEFERRABLE` không thể tùy tiện chuyển thành deferred chỉ bằng `SET CONSTRAINTS`. Việc chọn deferrability là một phần của thiết kế ràng buộc.

### 10.3. DEFERRABLE không thay thế ON DELETE CASCADE

Hai lựa chọn giải quyết hai câu hỏi khác nhau:

- **`ON DELETE CASCADE` / `SET NULL`:** khi xóa cha thì Oracle xử lý các con như thế nào?
- **`DEFERRABLE`:** thời điểm ràng buộc được kiểm tra có thể dời tới commit hay không?

Đừng dùng `DEFERRABLE` để suy ra hành vi xóa dây chuyền. Và đừng dùng `CASCADE` để suy ra constraint có thể tạm vi phạm đến commit.

### 10.4. DDL có implicit commit

Các lệnh tạo/bỏ/sửa constraint bằng `CREATE TABLE` và `ALTER TABLE` là **DDL**. Oracle thường thực hiện implicit commit trước/sau các DDL thành công. Vì vậy:

- `ROLLBACK` có thể hoàn tác `INSERT`/`UPDATE`/`DELETE` chưa commit.
- `ROLLBACK` **không phải phương án hoàn tác `CREATE TABLE`/`ALTER TABLE`** đã thực hiện.
- Khi thực hành, tách rõ khâu tạo schema khỏi khâu thử transaction và savepoint.

Đây là lý do các ví dụ trong bài tạo bảng trước, rồi mới dùng `SAVEPOINT` và `ROLLBACK TO` để quan sát hành vi xóa trên dữ liệu mẫu.

## 11. Xem metadata khóa ngoại qua các dictionary views

Các truy vấn sau là **read-only**. Nên thực hiện trong đúng PDB/schema; quyền đọc metadata phụ thuộc tài khoản. Một số view hữu ích:

| View | Mục đích |
| --- | --- |
| `USER_CONSTRAINTS` | Ràng buộc của schema đang kết nối |
| `USER_CONS_COLUMNS` | Các cột tham gia constraint của schema hiện tại |
| `ALL_CONSTRAINTS` | Metadata ràng buộc mà user được quyền xem |
| `ALL_CONS_COLUMNS` | Metadata cột constraint tương ứng |
| `DBA_CONSTRAINTS` / `DBA_CONS_COLUMNS` | Metadata rộng trong container hiện tại với quyền quản trị |
| `CDB_CONSTRAINTS` | Tra cứu metadata constraint theo containers khi có quyền tại root |

### 11.1. Liệt kê các FK của schema hiện tại

```sql
SELECT constraint_name,
       table_name,
       r_constraint_name,
       delete_rule,
       status,
       validated,
       deferrable,
       deferred
FROM   user_constraints
WHERE  constraint_type = 'R'
ORDER  BY table_name, constraint_name;
```

Các cột quan trọng:

- `CONSTRAINT_TYPE='R'`: Referential integrity constraint — khóa ngoại.
- `TABLE_NAME`: tên **bảng con** có FK.
- `R_CONSTRAINT_NAME`: tên constraint khóa cha được tham chiếu (`PRIMARY KEY` hoặc `UNIQUE`), không phải tên bảng cha.
- `DELETE_RULE`: thường là `NO ACTION`, `CASCADE` hoặc `SET NULL` theo metadata Oracle. **`NO ACTION` trong metadata không có nghĩa keyword `ON DELETE NO ACTION` được hỗ trợ trong cú pháp tạo FK.**
- `STATUS`: `ENABLED` hoặc `DISABLED`.
- `VALIDATED`: thể hiện trạng thái xác minh dữ liệu theo constraint.
- `DEFERRABLE` và `DEFERRED`: phản ánh khả năng hoãn và trạng thái mặc định kiểm tra.

### 11.2. Ghép child table với parent table

Với metadata có thể xem qua `ALL_CONSTRAINTS`:

```sql
SELECT child.owner           AS child_owner,
       child.table_name      AS child_table,
       child.constraint_name AS foreign_key_name,
       parent.owner          AS parent_owner,
       parent.table_name     AS parent_table,
       child.delete_rule,
       child.status
FROM   all_constraints child
JOIN   all_constraints parent
       ON parent.owner = child.r_owner
      AND parent.constraint_name = child.r_constraint_name
WHERE  child.constraint_type = 'R'
AND    child.owner = USER
ORDER  BY child.table_name, child.constraint_name;
```

Điều kiện join dùng `R_OWNER` và `R_CONSTRAINT_NAME` để xác định **constraint khóa cha**, vì một FK tham chiếu đến PK/UK constraint của bảng cha.

Nếu query không thấy bảng liên quan, có thể do user đang ở sai schema/PDB hoặc không có quyền nhìn metadata; không nên kết luận toàn database không tồn tại FK.

### 11.3. Xem cột tương ứng giữa child và parent

```sql
SELECT child.owner           AS child_owner,
       child.table_name      AS child_table,
       child_col.column_name AS child_column,
       parent.owner          AS parent_owner,
       parent.table_name     AS parent_table,
       parent_col.column_name AS parent_column,
       child_col.position    AS key_position,
       child.delete_rule
FROM   all_constraints child
JOIN   all_cons_columns child_col
       ON child_col.owner = child.owner
      AND child_col.constraint_name = child.constraint_name
JOIN   all_constraints parent
       ON parent.owner = child.r_owner
      AND parent.constraint_name = child.r_constraint_name
JOIN   all_cons_columns parent_col
       ON parent_col.owner = parent.owner
      AND parent_col.constraint_name = parent.constraint_name
      AND parent_col.position = child_col.position
WHERE  child.constraint_type = 'R'
AND    child.owner = USER
ORDER  BY child.table_name,
          child.constraint_name,
          child_col.position;
```

Truy vấn này đặc biệt hữu ích với **composite FK**: `POSITION` giúp xác định từng cặp cột con–cha theo đúng thứ tự. Khi có nhiều FK trên cùng một bảng con, phải phân biệt theo `CONSTRAINT_NAME`, không chỉ theo `TABLE_NAME`.

### 11.4. Phân biệt trạng thái ENABLE/DISABLE và VALIDATE/NOVALIDATE

Trong quản trị dữ liệu, Oracle có những trạng thái constraint như:

- **`ENABLE VALIDATE`:** constraint được bật và dữ liệu hiện có được xác minh phù hợp; các thao tác mới cũng phải tuân thủ.
- **`ENABLE NOVALIDATE`:** Oracle có thể không xác minh toàn bộ dữ liệu cũ theo cách của VALIDATE, nhưng kiểm soát các thao tác mới theo quy tắc của chế độ này.
- **`DISABLE`:** constraint không thực thi theo cách của constraint đang bật; có thể tạo điều kiện cho dữ liệu tham chiếu không hợp lệ nếu quy trình không kiểm soát.

Không được suy rằng tất cả dữ liệu hiện hữu đều hợp lệ chỉ vì `STATUS='ENABLED'`; cần xem `VALIDATED` và bối cảnh quản trị. Càng không nên tự bật/tắt FK ở production để tránh một lỗi dữ liệu nghiệp vụ.

## 12. Sửa hành vi xóa của FK đã tồn tại

### 12.1. Có thể ALTER trực tiếp ON DELETE không?

Trong thực hành Oracle, muốn chuyển từ hành vi mặc định sang `ON DELETE CASCADE` hoặc `SET NULL`, cách rõ ràng là **bỏ constraint FK cũ rồi tạo constraint mới với lựa chọn mong muốn**. Không coi `ON DELETE` là một thuộc tính có thể tùy ý sửa trực tiếp trên constraint bằng một câu `ALTER CONSTRAINT ... ON DELETE ...`.

Ví dụ **chỉ mang tính minh họa** trên bảng `DEMO_ORDERS`:

```sql
-- Thao tác DDL: chỉ thực hiện sau khi đánh giá dữ liệu,
-- ràng buộc, ứng dụng và việc xóa dây chuyền.
ALTER TABLE demo_orders
    DROP CONSTRAINT fk_demo_orders_customer;

ALTER TABLE demo_orders
    ADD CONSTRAINT fk_demo_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_customers(customer_id)
        ON DELETE CASCADE;
```

Sau câu lệnh này, xóa customer có đơn hàng sẽ thay đổi hành vi rõ rệt so với ví dụ ban đầu. **Không chạy các câu lệnh đó chỉ để xử lý `ORA-02292`** nếu chưa thống nhất chính sách xóa với chủ sở hữu dữ liệu.

### 12.2. Trước khi đổi chính sách cần đánh giá gì?

1. **Mối quan hệ nghiệp vụ:** hàng con có còn giá trị độc lập khi cha bị xóa không?
2. **Dữ liệu hiện hữu:** có vi phạm khóa ngoại hay dữ liệu lỗi cần sửa trước khi validate không?
3. **Tác động dây chuyền:** các bảng con của bảng con có tiếp tục cascade hay bị chặn không?
4. **Quyền và lịch sử:** có phải lưu dữ liệu theo quy định kiểm toán, thuế, hợp đồng hoặc bảo mật không?
5. **Tải và transaction:** khối lượng rows, undo/redo, thời gian chạy và lock.
6. **Index:** các cột child FK đã có index phù hợp chưa?
7. **Khả năng phục hồi:** backup, flashback và quy trình khôi phục nếu thao tác xóa nhầm.
8. **Thời điểm triển khai:** DDL có implicit commit và có thể làm ứng dụng đang chạy chịu ảnh hưởng.

Khi thay constraint, phải rà soát các thuộc tính đã có như tên constraint, deferrability, trạng thái validate, quyền truy cập và các dependency; không chỉ sao chép phần `FOREIGN KEY ... REFERENCES` rồi bỏ quên đặc tính quan trọng.

## 13. Quy trình xử lý yêu cầu xóa cha trong ứng dụng

Một API có thao tác “Xóa khách hàng” nên biết database đang áp dụng chính sách nào trước khi gọi `DELETE`.

### 13.1. Với hành vi mặc định

Một luồng nghiệp vụ có thể như sau:

```text
[User yêu cầu xóa Customer]
            |
            v
[Kiểm tra hợp đồng/đơn hàng liên quan]
            |
      +-----+------+
      |            |
    Có con       Không con
      |            |
      v            v
[Chặn và báo]  [DELETE Customer]
      |            |
      +-----+------+
            |
          [Phản hồi]
```

Ngay cả khi ứng dụng đếm và thấy không có con, session khác vẫn có thể ghi dữ liệu mới trước thời điểm `DELETE`. **Constraint trong database là tuyến bảo vệ cuối cùng** trước race condition; ứng dụng cần bắt `ORA-02292` và phản hồi theo ngôn ngữ nghiệp vụ.

### 13.2. Với CASCADE

API phải thể hiện rõ rằng xóa cha có thể xóa con. Nếu có nhiều cấp, cân nhắc:

- Hiển thị hoặc tính trước số lượng dữ liệu có khả năng bị xóa.
- Xác nhận quyền thao tác phù hợp với mức ảnh hưởng.
- Chạy trong transaction được quản lý và theo dõi thời gian/khối lượng.
- Ghi nhận audit theo yêu cầu.
- Xác định xử lý lỗi và phương án rollback nếu transaction thất bại.

Không thể dựa vào một câu `DELETE` thành công để biết đầy đủ những tác dụng phụ nếu schema có nhiều ràng buộc, trigger và logic khác; cần đọc thiết kế dữ liệu thực tế.

### 13.3. Với SET NULL

API và giao diện cần chấp nhận rằng sau khi xóa cha:

- Hàng con còn tồn tại.
- Cột khóa ngoại chuyển thành `NULL`.
- Các truy vấn `INNER JOIN` giữa con và cha có thể không còn hiển thị những con chưa gắn cha.
- Báo cáo muốn thấy các hàng con đó có thể cần `LEFT JOIN` và xử lý `NULL`.

Ví dụ:

```sql
SELECT t.task_id,
       t.task_title,
       p.project_name
FROM demo_tasks t
LEFT JOIN demo_projects p
       ON p.project_id = t.project_id
ORDER BY t.task_id;
```

Khi `PROJECT_ID` là `NULL`, `PROJECT_NAME` cũng có thể là `NULL` trong kết quả `LEFT JOIN`, nhưng bản ghi task vẫn xuất hiện.

## 14. Bài thực hành: thử từng chính sách xóa

Mục tiêu là quan sát trực tiếp sự khác biệt giữa ba kiểu xử lý **trong một schema học tập**, không chỉnh sửa dữ liệu sản xuất. Các bảng ở mục 2, 4 và 5 cần được tạo trước khi làm phần tương ứng.

### Bài 1 — Mặc định: cha bị chặn

1. Tạo `DEMO_CUSTOMERS` và `DEMO_ORDERS` với FK không có `ON DELETE`.
2. Thêm một customer 1 và hai orders tham chiếu customer đó.
3. Thử `DELETE FROM demo_customers WHERE customer_id = 1`.
4. Quan sát `ORA-02292` và kiểm tra cả cha lẫn con vẫn còn.

Câu lệnh quan sát:

```sql
SELECT customer_id, COUNT(*) AS order_count
FROM demo_orders
WHERE customer_id = 1
GROUP BY customer_id;
```

**Câu hỏi:** Vì sao xóa một customer khác không có order lại có thể thành công? Vì không còn tham chiếu con cần bảo vệ.

### Bài 2 — CASCADE: cha xóa thì con bị xóa

Dùng `DEMO_DEPARTMENTS` và `DEMO_DEPARTMENT_MEMBERS`:

```sql
SAVEPOINT test_cascade;

DELETE FROM demo_departments
WHERE department_id = 10;

SELECT *
FROM demo_department_members
WHERE department_id = 10;

ROLLBACK TO test_cascade;
```

**Kỳ vọng:** sau `DELETE`, không còn thành viên có `DEPARTMENT_ID=10`; sau rollback, các thành viên trở lại.

### Bài 3 — SET NULL: con được giữ lại

Dùng `DEMO_PROJECTS` và `DEMO_TASKS`:

```sql
SAVEPOINT test_set_null;

DELETE FROM demo_projects
WHERE project_id = 50;

SELECT task_id, project_id
FROM demo_tasks
WHERE task_id IN (501, 502)
ORDER BY task_id;

ROLLBACK TO test_set_null;
```

**Kỳ vọng:** `PROJECT_ID` của task 501 và 502 tạm thành `NULL`; sau rollback chúng trở lại giá trị 50.

### Bài 4 — Truy vấn metadata

Sau khi đã tạo các constraint:

```sql
SELECT table_name,
       constraint_name,
       delete_rule
FROM user_constraints
WHERE constraint_type = 'R'
AND   table_name IN (
        'DEMO_ORDERS',
        'DEMO_DEPARTMENT_MEMBERS',
        'DEMO_TASKS'
      )
ORDER BY table_name;
```

**Mục tiêu:** so sánh `DELETE_RULE` của ba FK. Oracle có thể hiển thị `NO ACTION` cho hành vi mặc định, `CASCADE` và `SET NULL` cho hai cấu hình tường minh.

### Bài 5 — Kiểm tra FK không tự tạo index

Truy vấn metadata các index của bảng con:

```sql
SELECT index_name, table_name, uniqueness
FROM user_indexes
WHERE table_name = 'DEMO_ORDERS'
ORDER BY index_name;
```

Sự hiện diện của index phục vụ `PRIMARY KEY (ORDER_ID)` **không có nghĩa** cột `CUSTOMER_ID` đã được index. Muốn biết index chứa cột nào, xem `USER_IND_COLUMNS`:

```sql
SELECT index_name,
       column_name,
       column_position
FROM user_ind_columns
WHERE table_name = 'DEMO_ORDERS'
ORDER BY index_name, column_position;
```

Đây là truy vấn quan sát; không cần tự tạo index trên mọi FK trong bài thử nếu chưa có mục tiêu đo hiệu năng cụ thể.

## 15. Những nhầm lẫn phổ biến

**“Có FOREIGN KEY nghĩa là Oracle sẽ tự xóa hàng con khi xóa cha.”**  
Không. Oracle chỉ xóa con theo chính sách `ON DELETE CASCADE`. Nếu không khai báo `ON DELETE`, thao tác xóa cha khi còn con thường bị chặn.

**“ON DELETE CASCADE có thể tự xóa parent khi xóa child.”**  
Không. Hành vi cascade áp dụng khi **xóa cha**. Xóa con không dẫn đến xóa cha.

**“SET NULL vẫn chạy dù FK column là NOT NULL.”**  
Không thể coi vậy. Nếu Oracle phải đặt FK về null nhưng `NOT NULL` ngăn điều đó, thao tác xóa sẽ thất bại theo ràng buộc liên quan.

**“FOREIGN KEY tự tạo index trên cột con.”**  
Không. Oracle yêu cầu ràng buộc khóa cha thích hợp nhưng không tự động tạo index trên mọi child FK. DBA cần đánh giá index dựa trên workload.

**“Một FOREIGN KEY bảo đảm child column không trùng.”**  
Không. Nhiều con có thể cùng tham chiếu một cha. Dùng `UNIQUE` nếu nghiệp vụ yêu cầu mỗi giá trị xuất hiện tối đa một lần trong bảng con.

**“Có thể viết ON UPDATE CASCADE giống ON DELETE CASCADE.”**  
Oracle SQL không cung cấp tùy chọn `ON UPDATE CASCADE` cho FK. Nên ưu tiên khóa cha ổn định và thiết kế quy trình thay đổi khóa riêng nếu thực sự cần.

**“ORA-02292 là lỗi kỹ thuật cần DISABLE constraint.”**  
Không. Đây thường là thông báo một hành vi xóa đang vi phạm thiết kế dữ liệu. Cần xử lý quan hệ cha–con hoặc quy trình nghiệp vụ thay vì vô hiệu hóa cơ chế bảo vệ.

**“Dùng SET NULL sẽ giữ lại quan hệ lịch sử.”**  
Không. SET NULL **bỏ liên kết hiện tại**. Nếu cần lịch sử cha trước khi xóa, phải lưu riêng thông tin đó theo thiết kế nghiệp vụ.

**“DELETE cha thành công thì số hàng xóa bằng số hàng Oracle hiển thị trong một câu SQL DELETE.”**  
Không thể dựa vào một con số đơn lẻ để biết toàn bộ tác động qua cascade. Cần đánh giá các FK nhiều cấp, trigger và logic liên quan.

**“Đã kiểm tra con ở ứng dụng thì không cần FOREIGN KEY.”**  
Không. Các transaction đồng thời, script quản trị và đường ghi dữ liệu khác có thể bỏ qua logic ứng dụng. Ràng buộc database vẫn là cơ chế bảo vệ toàn vẹn quan trọng.

## 16. Câu hỏi tự kiểm tra

### Câu 1 — Ý nghĩa quan hệ

Bảng `ORDERS` có `CUSTOMER_ID` trỏ tới khóa chính bảng `CUSTOMERS`. Bảng nào là parent, bảng nào là child? Một customer có thể có nhiều orders không?

**Gợi ý:** `CUSTOMERS` là parent; `ORDERS` là child; nhiều orders có thể cùng `CUSTOMER_ID` vì FK không áp đặt uniqueness ở bảng con.

### Câu 2 — Hành vi mặc định

Với FK không khai báo `ON DELETE`, Oracle xử lý thế nào nếu thực hiện `DELETE` một customer đang có orders?

**Gợi ý:** Theo cơ chế kiểm tra thông thường, Oracle chặn xóa và có thể báo `ORA-02292`.

### Câu 3 — CASCADE

Khóa ngoại trên `ORDER_ITEMS.ORDER_ID` khai báo `ON DELETE CASCADE` tham chiếu `ORDERS.ORDER_ID`. Khi xóa một order, các order items liên quan xảy ra điều gì?

**Gợi ý:** Những dòng con tham chiếu order bị xóa theo hành vi cascade. Điều đó không có nghĩa xóa một item sẽ xóa order.

### Câu 4 — SET NULL

Nếu bảng `TASKS` cần tồn tại sau khi bảng `PROJECTS` xóa một project, nên cân nhắc `ON DELETE SET NULL` hay `CASCADE`? Cột `TASKS.PROJECT_ID` cần đáp ứng điều kiện gì?

**Gợi ý:** `SET NULL`, nếu ngữ nghĩa nghiệp vụ cho phép task không gắn project; cột FK phải chấp nhận `NULL` để xóa cha đang có con thành công.

### Câu 5 — Lỗi ORA-02291

Một câu `INSERT INTO ORDERS(..., CUSTOMER_ID=999)` lỗi `ORA-02291`. Cần kiểm tra điều gì trước tiên?

**Gợi ý:** Hàng cha có khóa customer 999 có tồn tại ở đúng schema/PDB không; thao tác tạo cha/con có đúng thứ tự và transaction không.

### Câu 6 — Lỗi ORA-02292

Một câu `DELETE FROM CUSTOMERS WHERE ID=1` lỗi `ORA-02292`. Có nên tắt ngay FK để cho xóa không?

**Gợi ý:** Không. Xác định bảng con và chính sách nghiệp vụ, sau đó quyết định giữ cha hoặc xử lý các hàng con có kiểm soát.

### Câu 7 — Composite FK

Một FK tham chiếu khóa ghép `(REGION_ID, WAREHOUSE_ID)`. Tại sao truy vấn metadata cần `POSITION` để ghép cột con với cột cha?

**Gợi ý:** Các thành phần khóa phải được đối chiếu đúng vị trí trong bộ cột, không chỉ ghép theo tên bảng hoặc constraint.

### Câu 8 — Index

Có một FK trên `ORDERS.CUSTOMER_ID`. Có thể khẳng định Oracle đã tạo index trên cột này chưa? Khi nào index hữu ích?

**Gợi ý:** Không. Cần kiểm tra `USER_IND_COLUMNS`; index có thể hữu ích với các truy vấn tìm order theo customer và kiểm tra/xóa khóa cha trong workload đồng thời.

### Câu 9 — DEFERRABLE

`ON DELETE CASCADE` và `DEFERRABLE` có cùng ý nghĩa không?

**Gợi ý:** Không. Cascade xác định hành động đối với con khi xóa cha; deferrable liên quan đến thời điểm kiểm tra ràng buộc.

### Câu 10 — Quy tắc nghiệp vụ

Hệ thống tài chính phải giữ hóa đơn bảy năm sau khi khách hàng ngừng sử dụng. Có nên đặt `ON DELETE CASCADE` từ customer sang invoices chỉ để đơn giản hóa thao tác xóa không?

**Gợi ý:** Không nên mặc định. Cần thiết kế lưu trữ, trạng thái ngừng hoạt động, xóa dữ liệu theo thời hạn và quyền truy cập phù hợp, giữ nguyên toàn vẹn tham chiếu.

### Câu 11 — NULL và khóa ngoại

Một hàng child có `PARENT_ID = NULL` nhưng FK cho phép NULL. Đây có phải luôn là một tham chiếu hỏng không?

**Gợi ý:** Không. Với FK đơn cột nullable, NULL biểu thị không có giá trị tham chiếu; khác với một ID không-null mà bảng cha không chứa.

### Câu 12 — Đọc DELETE_RULE

Trong `USER_CONSTRAINTS`, một FK có `DELETE_RULE='NO ACTION'`. Điều đó có nghĩa khi tạo lại FK phải thêm `ON DELETE NO ACTION` không?

**Gợi ý:** Không. Đây là giá trị metadata mô tả hành vi mặc định; cú pháp Oracle khi tạo FK có thể đơn giản là không khai báo `ON DELETE`.

## 17. Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html): khai báo khóa chính, khóa duy nhất, khóa ngoại và hành vi `ON DELETE`.
- [Oracle Database SQL Language Reference — constraint](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/constraint.html): các loại ràng buộc, cú pháp `references_clause`, `ON DELETE CASCADE` và `SET NULL`, `DEFERRABLE`.
- [Oracle Database SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): thêm, bỏ và quản lý constraint sau khi bảng đã tồn tại.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): cơ sở dữ liệu quan hệ, các loại constraints và tính toàn vẹn tham chiếu.
- [Oracle Database Reference — USER_CONSTRAINTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_CONSTRAINTS.html): metadata ràng buộc và `DELETE_RULE` (tham khảo view tương ứng theo phạm vi user).
- [Oracle Database Reference — ALL_CONSTRAINTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_CONSTRAINTS.html): tên, loại, trạng thái và liên kết đến constraint cha.
- [Oracle Database Reference — ALL_CONS_COLUMNS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_CONS_COLUMNS.html): xác định các cột tham gia FK/PK/UK và thứ tự `POSITION`.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): quản trị constraints, data dictionary và vận hành schema.

Khi thiết kế quan hệ cha con trong Oracle, hãy bắt đầu từ **quy tắc dữ liệu**: con có bắt buộc phải có cha không, có được tồn tại sau khi cha mất không, và có được phép xóa dây chuyền không? Sau đó mới chọn **hành vi mặc định**, **`ON DELETE CASCADE`** hoặc **`ON DELETE SET NULL`**. Kết hợp kiểm tra constraint metadata, index phù hợp và quản lý transaction để những thao tác xóa vừa đúng nghiệp vụ vừa giữ tính toàn vẹn dữ liệu.
