# Ràng buộc nhiều cột và thứ tự cột trong khóa tham chiếu

Trong **Database SQL**, một ràng buộc không nhất thiết chỉ liên quan đến một cột. Nhiều bảng dùng **cặp hoặc bộ nhiều giá trị** để xác định một bản ghi: mã đơn hàng chỉ duy nhất trong một cửa hàng, mã dự án chỉ duy nhất trong một tổ chức, hay số dòng hóa đơn chỉ duy nhất trong một hóa đơn. Khi đó, `PRIMARY KEY`, `UNIQUE` và `FOREIGN KEY` có thể gồm **nhiều cột**.

Điểm đặc biệt quan trọng với **khóa ngoại nhiều cột** (composite foreign key) là **thứ tự các cột xác định cách ghép từng giá trị ở bảng con với từng giá trị ở bảng cha**. Nếu đảo thứ tự ở một vế mà không đảo tương ứng ở vế kia, câu SQL có thể bị từ chối; nguy hiểm hơn, khi các cột có kiểu tương thích, một ràng buộc sai vẫn có thể được tạo và kiểm tra **sai quan hệ nghiệp vụ**.

Bài học trình bày cách khai báo ràng buộc nhiều cột, ánh xạ vị trí giữa hai bảng, xử lý `NULL`, tác động của thứ tự lên chỉ mục và những khác biệt khi thực hành trên các hệ quản trị SQL.

## 1. Khi nào cần ràng buộc nhiều cột?

Xét một ứng dụng quản lý nhiều tổ chức (**tenant**). Mỗi tổ chức có các dự án riêng:

| tenant_id | project_code | project_name |
| ---: | --- | --- |
| 10 | APP | Ứng dụng khách hàng |
| 10 | OPS | Hệ thống vận hành |
| 20 | APP | Ứng dụng nội bộ |

`project_code = 'APP'` xuất hiện ở hai tenant khác nhau. Quy tắc nghiệp vụ là:

- Một tenant không được có hai dự án **cùng mã**.
- Hai tenant khác nhau **được phép** dùng cùng mã dự án.
- Mỗi công việc (task) phải trỏ đến dự án thuộc **đúng tenant**.

Vì vậy, `project_code` riêng lẻ không xác định một dự án trên toàn hệ thống. Cặp `(tenant_id, project_code)` mới xác định được dự án theo quy tắc này.

Có thể biểu diễn quan hệ:

```text
PROJECTS (bảng cha)
+-----------+--------------+---------------------+
| tenant_id | project_code | project_name        |
+-----------+--------------+---------------------+
|        10 | APP          | Ứng dụng khách hàng |
|        10 | OPS          | Hệ thống vận hành   |
|        20 | APP          | Ứng dụng nội bộ     |
+-----------+--------------+---------------------+
      ^            ^
      |            |
      |            |  Mỗi task phải khớp CẢ HAI giá trị
      |            |
TASKS (bảng con)
+---------+-----------+--------------+----------------+
| task_id | tenant_id | project_code | title          |
+---------+-----------+--------------+----------------+
|       1 |        10 | APP          | Thiết kế UI    |
|       2 |        20 | APP          | Kiểm thử API   |
+---------+-----------+--------------+----------------+
```

Một khóa ngoại chỉ tham chiếu `project_code` sẽ không biểu diễn đúng quan hệ giữa task và dự án trong thiết kế này. Ta cần khóa ngoại từ **cặp cột ở bảng con** đến **cặp cột tương ứng ở bảng cha**.

## 2. Phân biệt PRIMARY KEY, UNIQUE, FOREIGN KEY và CHECK nhiều cột

| Ràng buộc | Có thể gồm nhiều cột? | Điều được bảo đảm |
| --- | --- | --- |
| `PRIMARY KEY (a, b)` | Có | Bộ `(a, b)` phân biệt từng dòng; các cột khóa chính không được `NULL` |
| `UNIQUE (a, b)` | Có | Không trùng cùng một **tổ hợp giá trị** theo quy tắc bằng nhau/`NULL` của DBMS |
| `FOREIGN KEY (x, y) REFERENCES parent(a, b)` | Có | Bộ `(x, y)` ở bảng con phải tham chiếu đến một bộ `(a, b)` hợp lệ ở bảng cha, trừ các trường hợp `NULL` được cho phép |
| `CHECK (a <= b)` | Có thể tham chiếu nhiều cột | Điều kiện trên **một dòng** phải không bị đánh giá là `FALSE`; `UNKNOWN` do `NULL` thường vẫn được chấp nhận |
| `NOT NULL` | Khai báo theo từng cột | Cột đó bắt buộc có giá trị; thường kết hợp nhiều khai báo `NOT NULL` trong một bảng |

**Phân biệt hai ý nghĩa của “nhiều cột”:**

- `UNIQUE (tenant_id, project_code)` kiểm tra **tổ hợp giá trị giữa các dòng**.
- `CHECK (start_date <= end_date)` kiểm tra **quan hệ giữa hai giá trị trong cùng một dòng**.

`CHECK` không thay cho `UNIQUE` nếu yêu cầu là “không được có hai dòng trùng cặp mã”, và `UNIQUE` không thay cho `FOREIGN KEY` nếu yêu cầu là “cặp mã phải tồn tại trong bảng cha”.

## 3. Khóa chính nhiều cột: tính duy nhất thuộc về cả bộ giá trị

Trên PostgreSQL, có thể khai báo khóa chính nhiều cột ngay lúc tạo bảng:

```sql
CREATE TABLE projects (
    tenant_id    BIGINT NOT NULL,
    project_code VARCHAR(20) NOT NULL,
    project_name VARCHAR(100) NOT NULL,

    CONSTRAINT pk_projects
        PRIMARY KEY (tenant_id, project_code)
);
```

Ràng buộc `pk_projects` kiểm tra **cặp** `(tenant_id, project_code)`. Với dữ liệu mẫu:

```sql
INSERT INTO projects (tenant_id, project_code, project_name)
VALUES
    (10, 'APP', 'Ứng dụng khách hàng'),
    (10, 'OPS', 'Hệ thống vận hành'),
    (20, 'APP', 'Ứng dụng nội bộ');
```

Các dòng này hợp lệ vì không có hai dòng cùng cả `tenant_id` lẫn `project_code`.

Ngược lại:

```sql
-- Dự kiến bị từ chối: (10, 'APP') đã tồn tại.
INSERT INTO projects (tenant_id, project_code, project_name)
VALUES (10, 'APP', 'Dự án trùng mã');
```

**Không phải từng cột đều duy nhất.** `tenant_id = 10` xuất hiện ở nhiều dòng, và `project_code = 'APP'` cũng xuất hiện ở nhiều dòng. Khóa chỉ yêu cầu **toàn bộ cặp không được trùng**.

### Khóa chính nhiều cột có phải lựa chọn duy nhất?

Không. Một mô hình khác dùng khóa chính đơn `project_id` và đặt `UNIQUE` trên cặp mang ý nghĩa nghiệp vụ:

```sql
-- PostgreSQL: phương án THAY THẾ cho bảng projects ở trên,
-- không chạy đè lên bảng projects đã tạo.
CREATE TABLE projects_with_id (
    project_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    project_code VARCHAR(20) NOT NULL,
    project_name VARCHAR(100) NOT NULL,

    CONSTRAINT uq_projects_with_id_tenant_code
        UNIQUE (tenant_id, project_code)
);
```

Trong mô hình này:

- `project_id` là **khóa chính thay thế (surrogate key)**.
- Cặp `(tenant_id, project_code)` vẫn duy nhất và là **khóa ứng viên** có thể dùng làm đích khóa ngoại nếu DBMS hỗ trợ tham chiếu đến `UNIQUE`.
- Một bảng con có thể tham chiếu `project_id` hoặc tham chiếu cặp `(tenant_id, project_code)`, tùy quy tắc toàn vẹn cần bảo vệ.

Nếu ứng dụng nhiều tenant chỉ dùng `project_id` mà không đồng thời ràng buộc tenant của task với tenant của project, phải bảo đảm tính nhất quán tenant bằng thiết kế khác. Một lựa chọn là khóa ngoại kép `(tenant_id, project_id)` tham chiếu một `UNIQUE (tenant_id, project_id)` ở bảng cha.

## 4. UNIQUE nhiều cột: không trùng tổ hợp, nhưng cần hiểu NULL

Ví dụ bảng khách hàng trong từng tenant:

```sql
CREATE TABLE customer_accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id  BIGINT NOT NULL,
    username   VARCHAR(60) NOT NULL,

    CONSTRAINT uq_customer_accounts_tenant_username
        UNIQUE (tenant_id, username)
);
```

Ràng buộc cho phép hai tenant cùng có username `'lan'`, nhưng không cho phép hai tài khoản trong **cùng tenant** có cùng username theo cách so sánh chuỗi của hệ quản trị và collation đang dùng.

```sql
INSERT INTO customer_accounts (tenant_id, username)
VALUES (10, 'lan'), (20, 'lan');

-- Dự kiến lỗi trùng cặp (tenant_id, username):
INSERT INTO customer_accounts (tenant_id, username)
VALUES (10, 'lan');
```

### UNIQUE nhiều cột có NULL

Không nên giả định `UNIQUE (a, b)` luôn ngăn mọi dòng có `NULL` trong tổ hợp. Các DBMS có **quy tắc `NULL` trong unique constraint khác nhau**. Chẳng hạn PostgreSQL mặc định cho phép nhiều dòng trùng các thành phần khác khi thành phần còn lại là `NULL`; PostgreSQL 15+ còn có cú pháp `UNIQUE NULLS NOT DISTINCT` để thay đổi hành vi đó. SQL Server có quy tắc unique index riêng đối với `NULL`; MySQL, SQLite và Oracle cũng cần xét theo engine và loại ràng buộc.

Nếu một bộ mã dùng để **định danh bản ghi hoặc làm khóa tham chiếu**, thiết kế thường rõ ràng hơn khi đặt từng cột bắt buộc là `NOT NULL`, tránh tình trạng bộ khóa chỉ được cung cấp một phần. `PRIMARY KEY` tự mang yêu cầu không `NULL` cho các cột khóa.

## 5. FOREIGN KEY nhiều cột: các vị trí được ghép theo thứ tự khai báo

Đây là quy tắc quan trọng nhất của bài:

```sql
FOREIGN KEY (child_col_1, child_col_2)
REFERENCES parent (parent_col_1, parent_col_2)
```

Nó có nghĩa:

| Vị trí | Cột bên bảng con | Cột bên bảng cha | Ý nghĩa |
| ---: | --- | --- | --- |
| 1 | `child_col_1` | `parent_col_1` | So sánh giá trị ở vị trí đầu |
| 2 | `child_col_2` | `parent_col_2` | So sánh giá trị ở vị trí thứ hai |

DBMS không tự ghép cột vì **tên giống nhau** hay vì “hiểu” ý nghĩa nghiệp vụ. Danh sách cột ở hai bên là **hai danh sách có thứ tự**.

Với bảng `projects` có khóa chính `(tenant_id, project_code)`, bảng `tasks` cần khai báo:

```sql
CREATE TABLE tasks (
    task_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    project_code VARCHAR(20) NOT NULL,
    title        VARCHAR(200) NOT NULL,

    CONSTRAINT fk_tasks_projects
        FOREIGN KEY (tenant_id, project_code)
        REFERENCES projects (tenant_id, project_code)
);
```

Ánh xạ cụ thể là:

```text
tasks.tenant_id     ──────> projects.tenant_id
tasks.project_code  ──────> projects.project_code

                 Cùng một dòng projects
                 phải khớp cả hai giá trị.
```

Ví dụ:

```sql
INSERT INTO tasks (tenant_id, project_code, title)
VALUES
    (10, 'APP', 'Thiết kế giao diện'),
    (20, 'APP', 'Kiểm thử dịch vụ');

-- Dự kiến lỗi FK: tenant 20 không có project 'OPS'.
-- Dự án (10, 'OPS') KHÔNG làm cho (20, 'OPS') hợp lệ.
INSERT INTO tasks (tenant_id, project_code, title)
VALUES (20, 'OPS', 'Triển khai vận hành');
```

Một khóa ngoại hai cột kiểm tra **một bộ giá trị trong cùng dòng của bảng cha**. Không đủ để `tenant_id = 20` tồn tại ở một dòng bất kỳ và `project_code = 'OPS'` tồn tại ở một dòng bất kỳ khác: cả hai phải khớp cùng một bản ghi `projects`.

### Nếu không ghi danh sách cột bên bảng cha

Trong DBMS hỗ trợ cú pháp tham chiếu khóa chính mặc định, có thể viết:

```sql
-- PostgreSQL: sử dụng PRIMARY KEY của bảng cha.
FOREIGN KEY (tenant_id, project_code)
REFERENCES projects
```

Khi đó DBMS lấy **các cột khóa chính** của `projects` theo thứ tự định nghĩa khóa chính. Với `PRIMARY KEY (tenant_id, project_code)`, danh sách hai cột bên con như trên là phù hợp.

Để người đọc dễ kiểm tra cặp ánh xạ trong code review và tránh nhầm khi có nhiều khóa ứng viên, việc **ghi rõ danh sách cột tham chiếu** thường hữu ích. Nếu không chỉ định, không được tự hiểu rằng engine sẽ chọn một `UNIQUE` tùy ý; thông thường nó chọn **PRIMARY KEY** của bảng cha.

## 6. Đảo vị trí một bên có thể tạo khóa ngoại sai mà vẫn hợp lệ về cú pháp

Giả sử hai cột cùng kiểu số:

```sql
CREATE TABLE departments_demo (
    company_id    BIGINT NOT NULL,
    department_id BIGINT NOT NULL,

    PRIMARY KEY (company_id, department_id)
);
```

Cách khai báo **đúng theo nghiệp vụ** ở bảng nhân viên:

```sql
FOREIGN KEY (company_id, department_id)
REFERENCES departments_demo (company_id, department_id)
```

Nhưng xem cách khai báo **sai** sau:

```sql
-- SAI Ý NGHĨA: hai cột bên con bị đảo thứ tự.
FOREIGN KEY (department_id, company_id)
REFERENCES departments_demo (company_id, department_id)
```

Hai cột bên con đều là `BIGINT`, nên DBMS có thể chấp nhận kiểu dữ liệu và khóa cha, nhưng ánh xạ thành:

```text
child.department_id  ──────> parent.company_id
child.company_id     ──────> parent.department_id
```

Nếu bảng cha có cặp `(company_id = 1, department_id = 7)`, thì một dòng con với `(company_id = 7, department_id = 1)` có thể thỏa **ràng buộc bị đảo**: giá trị `department_id = 1` ghép vào `company_id = 1`, còn `company_id = 7` ghép vào `department_id = 7`. Nhưng theo quan hệ nghiệp vụ cần bảo vệ, công ty 7, phòng ban 1 lại **không có bản ghi cha tương ứng**.

Như vậy, một FK tạo thành công **không bảo đảm danh sách cột đã đúng ý nghĩa**. Khi xem `FOREIGN KEY (...) REFERENCES ... (...)`, hãy đối chiếu từng cặp cùng vị trí từ trái sang phải.

Nếu muốn đổi thứ tự cột bên con vì một lý do trình bày, phải đổi **cả thứ tự bên cha tương ứng** và bảo đảm DBMS chấp nhận khóa tham chiếu theo cấu hình mới. Cách dễ kiểm tra và dễ chuyển giữa DBMS nhất thường là **giữ thứ tự cùng ý nghĩa và cùng với khóa ứng viên bên cha**.

## 7. Điều kiện để tạo khóa ngoại nhiều cột

Một FK nhiều cột cần đáp ứng đồng thời các điều kiện về cấu trúc, không chỉ có cú pháp `REFERENCES`:

1. **Số lượng cột hai bên phải tương ứng.** FK hai cột không thể tham chiếu danh sách ba cột hoặc một cột.
2. **Kiểu dữ liệu và quy tắc so sánh phải tương thích** theo DBMS. Có hệ còn xét chính xác kiểu, độ dài, charset/collation, signedness hoặc kiểu tham số.
3. **Các cột được tham chiếu phải tạo thành khóa hợp lệ** (thường là `PRIMARY KEY` hoặc `UNIQUE`/unique index phù hợp). Đây là điều kiện toàn vẹn quan hệ cốt lõi. Một số engine/phiên bản có ngoại lệ với index không unique, nhưng không nên dùng ngoại lệ đó trong thiết kế SQL có thể chuyển hệ.
4. **Quy tắc thứ tự và index phải thỏa DBMS.** Một số hệ yêu cầu danh sách đích phù hợp thứ tự khóa/index tham chiếu. Để dễ đọc và tương thích, nên liệt kê cột đích theo **đúng thứ tự khóa ứng viên đã khai báo**.
5. **Không được có dữ liệu con vi phạm** khi thêm FK vào bảng đã có dữ liệu, trừ khi DBMS hỗ trợ trạng thái chưa kiểm tra theo một quy trình migration có chủ đích.
6. **Quyền truy cập và engine phải cho phép tạo FK.** Một số hệ cần quyền `REFERENCES`; trong MySQL, lựa chọn storage engine và kiểu index cũng có ảnh hưởng.

Ví dụ sai số lượng cột:

```sql
-- SAI: 2 cột con, nhưng chỉ 1 cột đích.
FOREIGN KEY (tenant_id, project_code)
REFERENCES projects (tenant_id)
```

Ví dụ thiếu tính duy nhất:

```sql
-- KHÔNG ĐỦ nếu bảng cha chỉ có PK (tenant_id, project_code):
FOREIGN KEY (project_code)
REFERENCES projects (project_code)
```

Trong mô hình ví dụ, `project_code` lặp lại giữa các tenant. Không thể dùng riêng nó để xác định duy nhất bản ghi cha.

### Khóa ngoại có thể tham chiếu UNIQUE thay vì PRIMARY KEY

Giả sử bảng cha có khóa đơn `project_id` nhưng vẫn cần kiểm tra cặp mã nghiệp vụ:

```sql
CREATE TABLE projects_with_id (
    project_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    project_code VARCHAR(20) NOT NULL,

    CONSTRAINT uq_projects_tenant_code
        UNIQUE (tenant_id, project_code)
);

CREATE TABLE tasks_with_code (
    task_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    project_code VARCHAR(20) NOT NULL,

    CONSTRAINT fk_tasks_with_code_projects
        FOREIGN KEY (tenant_id, project_code)
        REFERENCES projects_with_id (tenant_id, project_code)
);
```

Đây là cú pháp PostgreSQL hợp lệ: khóa ngoại tham chiếu **khóa ứng viên UNIQUE nhiều cột**. Cả hai trường `tenant_id` và `project_code` đều là `NOT NULL` trong ví dụ để cặp giá trị bắt buộc đầy đủ.

## 8. NULL trong khóa ngoại nhiều cột: MATCH SIMPLE và MATCH FULL

Nếu một hoặc nhiều cột bên con cho phép `NULL`, cần chú ý rằng “tổ hợp khóa ngoại” có thể **chưa được cung cấp đầy đủ**.

Trong SQL, quy tắc mặc định thường là **`MATCH SIMPLE`**:

- Khi **mọi thành phần FK khác `NULL`**, DBMS kiểm tra có một bộ giá trị cha tương ứng.
- Khi **ít nhất một thành phần FK là `NULL`**, kiểm tra tham chiếu của bộ đó được bỏ qua.

Ví dụ: `(tenant_id = 10, project_code = NULL)` thường **không bị từ chối bởi FK kiểu MATCH SIMPLE** chỉ vì không có dự án tương ứng. Dòng con được hiểu là chưa có đủ khóa tham chiếu.

Với ứng dụng không cho phép task tồn tại khi chưa biết dự án, nên khai báo:

```sql
tenant_id    BIGINT NOT NULL,
project_code VARCHAR(20) NOT NULL
```

và đặt khóa ngoại trên cặp đó. `NOT NULL` bổ sung yêu cầu “phải cung cấp đủ cặp khóa”; FK bổ sung yêu cầu “cặp đó phải tồn tại ở bảng cha”.

### MATCH FULL trong PostgreSQL

PostgreSQL hỗ trợ `MATCH FULL` để **không cho phép khóa ngoại chỉ có một phần NULL**:

```sql
-- PostgreSQL:
CREATE TABLE optional_project_links (
    link_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT,
    project_code VARCHAR(20),

    CONSTRAINT fk_optional_project_links
        FOREIGN KEY (tenant_id, project_code)
        REFERENCES projects (tenant_id, project_code)
        MATCH FULL
);
```

Với ràng buộc này:

| Bộ FK bên con | MATCH SIMPLE | MATCH FULL |
| --- | --- | --- |
| `(10, 'APP')` | Phải tìm thấy cha phù hợp | Phải tìm thấy cha phù hợp |
| `(10, NULL)` | Được miễn kiểm tra tham chiếu | **Không hợp lệ** |
| `(NULL, 'APP')` | Được miễn kiểm tra tham chiếu | **Không hợp lệ** |
| `(NULL, NULL)` | Được miễn kiểm tra tham chiếu | Được phép nếu cột không `NOT NULL` |

`MATCH FULL` **không thay cho `NOT NULL`**: nó vẫn cho phép trường hợp cả bộ tham chiếu đều `NULL`. Hãy chọn theo nghiệp vụ:

- Task **bắt buộc** thuộc dự án: dùng `NOT NULL` trên từng thành phần FK.
- Tham chiếu dự án **hoặc đầy đủ hoặc hoàn toàn chưa có**: cân nhắc `MATCH FULL` ở DBMS có hỗ trợ.
- Cho phép nhập từng phần thông tin theo từng giai đoạn: có thể dùng mô hình khác hoặc kiểm soát riêng; không vô tình dựa vào mặc định `MATCH SIMPLE`.

**Khác biệt DBMS:** không phải mọi hệ hỗ trợ thực thi `MATCH FULL` giống PostgreSQL. Ví dụ SQLite chỉ thực thi quy tắc kiểu `MATCH SIMPLE` cho FK dù có cú pháp `MATCH` trong định nghĩa; MySQL/MariaDB, SQL Server và Oracle cần kiểm tra riêng khả năng hỗ trợ và ngữ nghĩa, không sao chép `MATCH FULL` từ PostgreSQL rồi mặc nhiên kỳ vọng kết quả như nhau.

## 9. ON DELETE, ON UPDATE với khóa ngoại gồm nhiều cột

Khóa ngoại nhiều cột vẫn có hành vi tham chiếu khi bảng cha bị xóa hoặc khóa cha bị thay đổi. Tùy DBMS, có thể chọn hành động như:

| Hành động | Ý nghĩa điển hình |
| --- | --- |
| `NO ACTION` | Không cho phép thay đổi/xóa làm vi phạm FK tại thời điểm ràng buộc được kiểm tra |
| `RESTRICT` | Chặn thao tác gây vi phạm; thời điểm kiểm tra có thể khác `NO ACTION` ở hệ hỗ trợ deferrable |
| `ON DELETE CASCADE` | Khi xóa bản ghi cha, xóa các bản ghi con đang tham chiếu |
| `ON UPDATE CASCADE` | Khi bộ giá trị khóa cha thay đổi, cập nhật các giá trị FK liên quan ở bản ghi con |
| `ON DELETE SET NULL` | Khi xóa cha, đặt các thành phần FK bên con thành `NULL` theo quy tắc DBMS |

Ví dụ PostgreSQL:

```sql
CREATE TABLE tasks_cascade_demo (
    task_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    project_code VARCHAR(20) NOT NULL,

    CONSTRAINT fk_tasks_cascade_demo_projects
        FOREIGN KEY (tenant_id, project_code)
        REFERENCES projects (tenant_id, project_code)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);
```

Nếu `projects` đổi cặp `(10, 'APP')` thành `(10, 'WEB')`, `ON UPDATE CASCADE` có thể cập nhật các cặp FK trong `tasks_cascade_demo` đang trỏ tới dự án đó. Nếu xóa dự án, `ON DELETE CASCADE` có thể xóa luôn các task liên quan. Đây là lựa chọn nghiệp vụ **có ảnh hưởng đến dữ liệu**, không nên bật chỉ để câu DDL chạy được.

**Thận trọng với `SET NULL`:** nếu mọi cột FK được khai báo `NOT NULL` thì thao tác đặt `NULL` lên các cột đó sẽ không thành công. Không mặc nhiên kết hợp `ON DELETE SET NULL` với FK bắt buộc. Một số DBMS hỗ trợ chọn tập con cột khi dùng `SET NULL`, nhưng đây là cú pháp đặc thù và cần kiểm tra riêng.

### Không đồng nhất “khóa nhiều cột” với “cập nhật khóa thường xuyên”

Nếu `tenant_id` hoặc `project_code` thường xuyên đổi theo dữ liệu nghiệp vụ, các FK đa cột có thể phải cập nhật nhiều bảng con. Khi đó cần cân nhắc có dùng khóa định danh bất biến như `project_id` làm PK hay không, đồng thời **vẫn giữ ràng buộc nhất quán tenant** ở những quan hệ cần giới hạn theo tenant.

## 10. Thứ tự cột trong khóa UNIQUE/PRIMARY KEY ảnh hưởng thế nào đến index?

Về **quy tắc duy nhất của các bộ giá trị khác NULL**, `UNIQUE (a, b)` và `UNIQUE (b, a)` đều ngăn hai dòng có cùng cặp giá trị `a` và `b`. Nhưng thứ tự vẫn quan trọng khi DBMS tạo hoặc sử dụng **chỉ mục nhiều cột (composite index)**.

Với chỉ mục B-tree theo thứ tự `(tenant_id, project_code)`, dữ liệu được tổ chức chủ yếu theo `tenant_id`, sau đó theo `project_code` trong phạm vi cùng tenant. Vì vậy, các truy vấn bắt đầu bằng điều kiện trên `tenant_id` thường có lợi:

```sql
-- Có thể tận dụng thứ tự khóa (tenant_id, project_code):
SELECT *
FROM projects
WHERE tenant_id = 10;

SELECT *
FROM projects
WHERE tenant_id = 10
  AND project_code = 'APP';

SELECT *
FROM projects
WHERE tenant_id = 10
ORDER BY project_code;
```

Ngược lại:

```sql
-- Chỉ lọc cột đứng sau trong chỉ mục (tenant_id, project_code):
SELECT *
FROM projects
WHERE project_code = 'APP';
```

Một chỉ mục sắp theo `(project_code, tenant_id)` có thể phục vụ dạng truy vấn này thuận lợi hơn. Tùy engine, phân bố dữ liệu và bộ tối ưu, chỉ mục `(tenant_id, project_code)` vẫn **có thể** được dùng trong một số trường hợp; đừng diễn đạt máy móc rằng lọc cột thứ hai thì chỉ mục “không bao giờ dùng được”.

| Khía cạnh | `(tenant_id, project_code)` | `(project_code, tenant_id)` |
| --- | --- | --- |
| Kiểm tra trùng **cặp đã biết đầy đủ** | Cùng ý nghĩa duy nhất cơ bản | Cùng ý nghĩa duy nhất cơ bản |
| Lọc theo `tenant_id` | Thường phù hợp hơn với prefix chỉ mục | Có thể ít phù hợp hơn |
| Lọc theo `project_code` | Có thể ít phù hợp hơn | Thường phù hợp hơn |
| Thứ tự `ORDER BY tenant_id, project_code` | Thường phù hợp hơn với chỉ mục | Không có cùng thứ tự sắp xếp |
| Dùng làm đích FK | Cần đáp ứng quy tắc DBMS về khóa/index được tham chiếu | Cần xét cụ thể thứ tự và khóa/index |

**Hai câu hỏi phải tách ra:**

1. **Thứ tự ánh xạ trong FK:** phải ghép đúng từng cột con với cột cha **cùng vị trí**.
2. **Thứ tự tạo index của khóa cha/con:** ảnh hưởng cách tìm kiếm, sắp xếp, kiểm tra constraint và kế hoạch truy vấn.

Đừng đảo thứ tự danh sách FK để “tối ưu index” khi chưa xem xét toàn bộ ánh xạ và yêu cầu DBMS.

### Index bên bảng con

Nhiều DBMS tự có chỉ mục cho `PRIMARY KEY` và `UNIQUE` ở bảng cha, nhưng **không phải DBMS nào cũng tự tạo index cho cột FK bên bảng con**.

Ví dụ PostgreSQL: FK trên `tasks(tenant_id, project_code)` **không tự tạo index cho bảng con**. Nếu dữ liệu lớn và thường tra cứu task theo dự án, có thể thêm:

```sql
CREATE INDEX ix_tasks_tenant_project
ON tasks (tenant_id, project_code);
```

Index này có thể giúp truy vấn con theo cặp khóa và giảm chi phí tìm các dòng con liên quan khi sửa/xóa khóa cha. MySQL/InnoDB có cơ chế bảo đảm index phù hợp cho FK, có thể tự tạo nếu thiếu; cần xem index thực tế để tránh tạo trùng. Ở SQL Server, SQLite và Oracle cũng nên đánh giá index phía con theo nhu cầu truy vấn và hành vi khóa, thay vì đoán rằng FK tự động tạo index.

Không tạo mọi tổ hợp index chỉ vì bảng có nhiều cột: index cũng tiêu tốn bộ nhớ và chi phí cập nhật. Hãy chọn dựa trên điều kiện `WHERE`/`JOIN` phổ biến, kích thước bảng và `EXPLAIN`/execution plan khi cần.

## 11. Thực hành đầy đủ trên PostgreSQL

Phần này sử dụng **PostgreSQL** trong một database thực hành. Dùng các tên `sql98_...` để tách khỏi bảng nghiệp vụ thực. Mọi ví dụ được trình bày theo thứ tự; tránh chạy lại `CREATE TABLE` nếu các bảng đã tồn tại.

### 11.1. Tạo bảng cha và bảng con

```sql
CREATE TABLE sql98_tenants (
    tenant_id   BIGINT PRIMARY KEY,
    tenant_name VARCHAR(100) NOT NULL
);

CREATE TABLE sql98_projects (
    tenant_id    BIGINT NOT NULL,
    project_code VARCHAR(20) NOT NULL,
    project_name VARCHAR(100) NOT NULL,

    CONSTRAINT pk_sql98_projects
        PRIMARY KEY (tenant_id, project_code),

    CONSTRAINT fk_sql98_projects_tenants
        FOREIGN KEY (tenant_id)
        REFERENCES sql98_tenants (tenant_id)
);

CREATE TABLE sql98_tasks (
    task_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    project_code VARCHAR(20) NOT NULL,
    task_title   VARCHAR(200) NOT NULL,

    CONSTRAINT fk_sql98_tasks_projects
        FOREIGN KEY (tenant_id, project_code)
        REFERENCES sql98_projects (tenant_id, project_code)
);
```

Lưu ý ba cấp liên hệ:

- `sql98_tenants` có PK đơn `tenant_id`.
- `sql98_projects` có PK kép `(tenant_id, project_code)` và FK đơn đến `sql98_tenants`.
- `sql98_tasks` có PK đơn `task_id` và FK kép đến `sql98_projects`.

### 11.2. Ghi dữ liệu hợp lệ

```sql
INSERT INTO sql98_tenants (tenant_id, tenant_name)
VALUES
    (10, 'Nhóm A'),
    (20, 'Nhóm B');

INSERT INTO sql98_projects (tenant_id, project_code, project_name)
VALUES
    (10, 'APP', 'Ứng dụng khách hàng'),
    (10, 'OPS', 'Hệ thống vận hành'),
    (20, 'APP', 'Ứng dụng nội bộ');

INSERT INTO sql98_tasks (tenant_id, project_code, task_title)
VALUES
    (10, 'APP', 'Thiết kế UI'),
    (10, 'OPS', 'Theo dõi vận hành'),
    (20, 'APP', 'Kiểm thử API');
```

Đọc quan hệ theo đủ hai cột:

```sql
SELECT
    t.task_id,
    t.tenant_id,
    t.project_code,
    p.project_name,
    t.task_title
FROM sql98_tasks AS t
JOIN sql98_projects AS p
  ON p.tenant_id = t.tenant_id
 AND p.project_code = t.project_code
ORDER BY t.task_id;
```

Phần `ON` phải kiểm tra **cả hai điều kiện**. Nếu chỉ nối bằng `project_code`, task của tenant 10 có thể ghép nhầm với dự án `APP` của tenant 20, làm phát sinh dòng trùng hoặc dữ liệu sai tenant.

### 11.3. Thử tình huống vi phạm

Chạy từng lệnh dưới đây **độc lập trong môi trường thử nghiệm**. Chúng được thiết kế để gây lỗi constraint; nếu đang ở trong transaction PostgreSQL, sau một lỗi có thể phải `ROLLBACK` trước khi thực hiện câu khác.

```sql
-- Bị từ chối vì cặp (20, 'OPS') không có trong sql98_projects.
INSERT INTO sql98_tasks (tenant_id, project_code, task_title)
VALUES (20, 'OPS', 'Task tham chiếu sai tenant');

-- Bị từ chối vì PK kép (10, 'APP') đã tồn tại.
INSERT INTO sql98_projects (tenant_id, project_code, project_name)
VALUES (10, 'APP', 'Dự án trùng mã');
```

Nếu muốn xác nhận hai cột FK thực sự bắt buộc, thử riêng:

```sql
-- Bị từ chối vì tenant_id là NOT NULL.
INSERT INTO sql98_tasks (tenant_id, project_code, task_title)
VALUES (NULL, 'APP', 'Thiếu tenant');

-- Bị từ chối vì project_code là NOT NULL.
INSERT INTO sql98_tasks (tenant_id, project_code, task_title)
VALUES (10, NULL, 'Thiếu mã dự án');
```

Trường hợp cuối cho thấy `NOT NULL` cần thiết khi nghiệp vụ không cho phép một phần khóa tham chiếu bị thiếu.

### 11.4. Xem định nghĩa constraint thực tế

PostgreSQL lưu metadata constraint trong `pg_constraint`. Truy vấn sau hiển thị ràng buộc của bảng con theo định nghĩa mà PostgreSQL đang thực thi:

```sql
SELECT
    conname AS constraint_name,
    contype AS constraint_type,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'sql98_tasks'::regclass
ORDER BY conname;
```

Kỳ vọng thấy FK tương ứng:

```text
FOREIGN KEY (tenant_id, project_code)
REFERENCES sql98_projects(tenant_id, project_code)
```

Đừng chỉ đọc tên constraint; phải **kiểm tra hai danh sách cột ở hai vế** và hành động `ON DELETE`/`ON UPDATE` nếu có.

Để liệt kê cả PK của bảng cha:

```sql
SELECT
    conname,
    contype,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'sql98_projects'::regclass
ORDER BY conname;
```

### 11.5. Xem kế hoạch truy vấn và quyết định index

Tạo index trên FK con khi muốn quan sát kế hoạch tìm task theo dự án:

```sql
CREATE INDEX ix_sql98_tasks_tenant_project
ON sql98_tasks (tenant_id, project_code);

EXPLAIN
SELECT *
FROM sql98_tasks
WHERE tenant_id = 10
  AND project_code = 'APP';
```

Vì bảng mẫu rất nhỏ, PostgreSQL **có thể vẫn chọn quét tuần tự**. Đây là lựa chọn bình thường của bộ tối ưu, không chứng tỏ index sai. Ở bảng lớn, cần xem thống kê, phân bố dữ liệu và kế hoạch thực tế.

### 11.6. Dọn dữ liệu thực hành

Chỉ chạy khi ba bảng và index đều do chính bạn tạo cho bài này:

```sql
DROP TABLE sql98_tasks;
DROP TABLE sql98_projects;
DROP TABLE sql98_tenants;
```

Xóa bảng con trước bảng cha giúp tránh vi phạm liên kết khi dọn dẹp. Index được tạo cho `sql98_tasks` sẽ bị xóa cùng bảng. Không sử dụng `CASCADE` một cách tùy tiện trên database có đối tượng dùng chung.

## 12. Khác biệt cần lưu ý giữa các DBMS

Cú pháp `FOREIGN KEY (a, b) REFERENCES parent(x, y)` rất phổ biến, nhưng điều kiện index, kiểu cột, `NULL` và chính sách kiểm tra khác nhau.

| DBMS | Điểm cần chú ý khi dùng khóa nhiều cột |
| --- | --- |
| **PostgreSQL** | PK/UNIQUE nhiều cột; FK đa cột; hỗ trợ `MATCH FULL` và deferrable constraint ở những trường hợp phù hợp; FK con không tự có index. |
| **MySQL / MariaDB (InnoDB)** | FK phụ thuộc engine/index và tính tương thích kiểu, charset/collation; index trên bảng con phải phù hợp; khả năng tham chiếu khóa không unique và các hạn chế khác thay đổi theo engine/phiên bản, nên ưu tiên PK/UNIQUE chuẩn. |
| **SQL Server** | Hỗ trợ PK/UNIQUE/FK nhiều cột; cặp cột đích phải là khóa ứng viên/index unique được chấp nhận; có thể xem ánh xạ vị trí trong `sys.foreign_key_columns`; FK con không mặc nhiên có index riêng. |
| **SQLite** | Bật `PRAGMA foreign_keys = ON` **trên từng kết nối** để thực thi FK; khóa cha phải là PK hoặc UNIQUE phù hợp, bao gồm điều kiện collation; có thể xem từng cặp cột qua `PRAGMA foreign_key_list(...)`. |
| **Oracle Database** | Hỗ trợ PK/UNIQUE/FK nhiều cột; tra cứu bằng `USER_CONSTRAINTS`/`USER_CONS_COLUMNS`; việc tạo FK không đồng nghĩa luôn có index phù hợp ở bảng con. |

### PostgreSQL: ALTER TABLE để thêm FK vào bảng có sẵn

```sql
ALTER TABLE tasks
ADD CONSTRAINT fk_tasks_projects
FOREIGN KEY (tenant_id, project_code)
REFERENCES projects (tenant_id, project_code);
```

Trước khi thêm constraint, cần chắc chắn **mọi cặp đã tồn tại ở bảng con** đều khớp bảng cha hoặc thuộc trường hợp `NULL` hợp lệ. PostgreSQL hỗ trợ cách thêm FK `NOT VALID` rồi `VALIDATE CONSTRAINT` cho một số migration trên dữ liệu lớn, nhưng đây là lựa chọn quản trị cần quy trình kiểm tra riêng, không có nghĩa FK luôn được phép bỏ qua dữ liệu cũ.

### MySQL/MariaDB: nhớ xác định engine và index

Ví dụ cú pháp InnoDB phổ biến:

```sql
CREATE TABLE project_codes (
    tenant_id    BIGINT NOT NULL,
    project_code VARCHAR(20) NOT NULL,
    PRIMARY KEY (tenant_id, project_code)
) ENGINE=InnoDB;

CREATE TABLE project_tasks (
    task_id      BIGINT NOT NULL PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    project_code VARCHAR(20) NOT NULL,
    CONSTRAINT fk_project_tasks_codes
        FOREIGN KEY (tenant_id, project_code)
        REFERENCES project_codes (tenant_id, project_code)
) ENGINE=InnoDB;
```

Cần bảo đảm kiểu của từng cặp cột tương thích, đặc biệt **signed/unsigned** đối với số nguyên và charset/collation đối với cột chuỗi. MySQL và MariaDB không phải một phiên bản chung; kiểm tra chính tài liệu engine/phiên bản đang dùng nếu thiết kế có điều kiện đặc biệt.

### SQLite: bật kiểm tra FK và xem thứ tự cột

```sql
-- SQLite, ngoài transaction đang chạy:
PRAGMA foreign_keys = ON;

CREATE TABLE parent_pairs (
    tenant_id INTEGER NOT NULL,
    project_no INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, project_no)
);

CREATE TABLE child_pairs (
    task_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    project_no INTEGER NOT NULL,
    FOREIGN KEY (tenant_id, project_no)
        REFERENCES parent_pairs (tenant_id, project_no)
);

PRAGMA foreign_key_list('child_pairs');
```

Kết quả `PRAGMA foreign_key_list` có thông tin `seq`, `from` và `to` để quan sát **thứ tự ghép từng cột**. `PRAGMA foreign_keys = ON` nên được thiết lập khi mở kết nối và trước transaction nếu ứng dụng cần kiểm tra FK; trên nhiều bản SQLite, việc thay đổi thiết lập này khi transaction đang chạy không có hiệu lực như mong đợi.

### SQL Server: quan sát ánh xạ cột trong catalog

```sql
-- SQL Server: xem cặp cột của các FOREIGN KEY.
SELECT
    fk.name AS fk_name,
    fkc.constraint_column_id AS ordinal_position,
    pc.name AS parent_side_column,
    rc.name AS referenced_side_column
FROM sys.foreign_keys AS fk
JOIN sys.foreign_key_columns AS fkc
  ON fkc.constraint_object_id = fk.object_id
JOIN sys.columns AS pc
  ON pc.object_id = fkc.parent_object_id
 AND pc.column_id = fkc.parent_column_id
JOIN sys.columns AS rc
  ON rc.object_id = fkc.referenced_object_id
 AND rc.column_id = fkc.referenced_column_id
WHERE fk.parent_object_id = OBJECT_ID(N'dbo.project_tasks')
ORDER BY fk.name, fkc.constraint_column_id;
```

Tên `parent_side_column` ở truy vấn metadata này chỉ **cột của bảng chứa FK** (con theo cách gọi quan hệ), còn `referenced_side_column` là cột của bảng được tham chiếu (cha). Cách đặt tên trong system catalog dễ gây nhầm với khái niệm “bảng cha/bảng con” của nghiệp vụ.

### Oracle: xem thứ tự constraint trong metadata

```sql
-- Oracle Database: cột của constraint trong schema đang đăng nhập.
SELECT
    constraint_name,
    table_name,
    column_name,
    position
FROM user_cons_columns
WHERE constraint_name IN ('FK_PROJECT_TASKS_CODES', 'PK_PROJECT_CODES')
ORDER BY constraint_name, position;
```

Tên constraint không đặt trong dấu nháy thường được lưu ở dạng chữ hoa. Nếu cần xem FK tham chiếu constraint nào của bảng cha, tra cứu thêm `USER_CONSTRAINTS.R_CONSTRAINT_NAME` và loại ràng buộc `R`.

## 13. Thiết kế khóa nhiều cột: thứ tự, miền duy nhất và tenant isolation

Chọn khóa nhiều cột nên dựa vào **miền duy nhất của dữ liệu**, không chỉ dựa vào việc cột nào xuất hiện trong giao diện.

### Ví dụ 1 — Mã hóa đơn chỉ duy nhất trong cửa hàng

```sql
CREATE TABLE store_invoices (
    store_id   BIGINT NOT NULL,
    invoice_no VARCHAR(30) NOT NULL,
    issued_at  DATE NOT NULL,
    PRIMARY KEY (store_id, invoice_no)
);
```

Bảng dòng hóa đơn nên tham chiếu cặp `(store_id, invoice_no)`, để hóa đơn `INV-001` ở cửa hàng 1 không bị nhầm với hóa đơn cùng số ở cửa hàng 2.

### Ví dụ 2 — Dòng hóa đơn có số thứ tự theo từng hóa đơn

```sql
CREATE TABLE invoice_lines (
    store_id   BIGINT NOT NULL,
    invoice_no VARCHAR(30) NOT NULL,
    line_no    INTEGER NOT NULL,
    item_name  VARCHAR(100) NOT NULL,

    CONSTRAINT pk_invoice_lines
        PRIMARY KEY (store_id, invoice_no, line_no),

    CONSTRAINT fk_invoice_lines_invoice
        FOREIGN KEY (store_id, invoice_no)
        REFERENCES store_invoices (store_id, invoice_no)
);
```

Bảng con có **khóa chính ba cột**, trong khi **khóa ngoại chỉ gồm hai cột**. Không có quy tắc nào bắt buộc PK của bảng con và FK của chính bảng đó phải cùng số cột: chúng đảm nhận **hai chức năng khác nhau**.

### Ví dụ 3 — Có surrogate key vẫn cần bảo vệ tính nhất quán tenant

Giả sử `projects` có `project_id` duy nhất toàn cục, còn `tasks` cũng lưu `tenant_id`. Nếu FK chỉ là:

```sql
FOREIGN KEY (project_id) REFERENCES projects(project_id)
```

thì FK **chỉ chứng minh project tồn tại**; nó không kiểm tra `tasks.tenant_id = projects.tenant_id`.

Muốn cưỡng chế đồng thời cả hai điều kiện ngay tại DB, bảng `projects` có thể khai báo `UNIQUE (tenant_id, project_id)`, còn bảng `tasks` khai báo:

```sql
FOREIGN KEY (tenant_id, project_id)
REFERENCES projects (tenant_id, project_id)
```

Lúc đó task chỉ hợp lệ nếu **project_id tồn tại dưới đúng tenant_id**. Đây là một ứng dụng thực tế của FK nhiều cột để tránh tham chiếu chéo tenant.

## 14. Lưu ý khi thay đổi schema hoặc thứ tự cột

Nếu bảng đang hoạt động cần thêm một cột vào khóa, đổi thứ tự khóa hoặc chuyển từ FK đơn sang FK kép, đây không còn là việc sửa danh sách cột cho đẹp:

- **Dữ liệu cũ:** tìm những dòng con không có bộ khóa cha tương ứng theo định nghĩa mới.
- **Ràng buộc khóa cha:** phải có PK/UNIQUE hợp lệ cho bộ cột được tham chiếu; có thể cần tạo constraint hoặc index mới.
- **Mã ứng dụng:** cập nhật JOIN, INSERT, UPDATE, DELETE, ORM mapping và dữ liệu giao tiếp giữa các hệ.
- **`NULL`:** quyết định mỗi cột có bắt buộc hay không; cần xét `MATCH SIMPLE`/`MATCH FULL` nếu môi trường hỗ trợ.
- **Thao tác ON DELETE/UPDATE:** xem chính sách cascade, restrict, set null theo quan hệ mới.
- **Index và hiệu năng:** xem thứ tự cột theo truy vấn thực tế, tránh index trùng.
- **Thứ tự triển khai:** nếu cần chuyển tiếp giữa phiên bản ứng dụng cũ/mới, chuẩn bị migration nhiều giai đoạn; không drop constraint cũ trước khi tính toàn vẹn mới sẵn sàng.
- **DDL và khóa:** khả năng lock, transaction/rollback và mức online phụ thuộc DBMS.

Trong code review, một biểu mẫu ngắn thường rất hữu ích:

```text
Bảng cha:
Khóa ứng viên cha (theo thứ tự): (________, ________)
Bảng con:
FK con (theo thứ tự):          (________, ________)
Ánh xạ 1: child.________ -> parent.________
Ánh xạ 2: child.________ -> parent.________
Cả hai cột con NOT NULL?:
Có cho phép bộ FK thiếu một phần?:
ON DELETE / ON UPDATE:
Index phía con:
Truy vấn JOIN dùng đủ cột?:
```

Khi sửa quan hệ nhiều cột, nên kiểm tra trực tiếp metadata constraint để xác nhận **vị trí từng cột**, không chỉ nhìn tên ràng buộc như `fk_tasks_projects`.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| FK trỏ dự án sai tenant nhưng vẫn được tạo | Cột cùng kiểu đã bị đảo thứ tự ở vế con | Đối chiếu từng cặp theo vị trí trong FK và kiểm tra dữ liệu |
| Lỗi số lượng cột FK/PK không khớp | FK liệt kê 2 cột, đích chỉ có 1 hoặc 3 | Sửa danh sách đích đúng với khóa ứng viên tương ứng |
| “No unique constraint matching” hoặc lỗi khóa tham chiếu | Bảng cha chưa có PK/UNIQUE hợp lệ trên bộ cột được chọn | Tạo khóa ứng viên đúng và xử lý dữ liệu trùng trước |
| Lỗi khác biệt kiểu hoặc collation | Các cột ở cùng vị trí không tương thích theo DBMS | Đồng bộ định nghĩa kiểu và charset/collation cần thiết |
| Dòng con có FK `(10, NULL)` vẫn được chèn | `MATCH SIMPLE` miễn kiểm tra nếu một thành phần thiếu | Đặt `NOT NULL` nếu bắt buộc đủ; cân nhắc `MATCH FULL` nếu hỗ trợ |
| FK tạo được nhưng JOIN trả dư dòng | JOIN bỏ sót một thành phần của khóa | Viết đủ điều kiện `ON` theo cặp FK |
| Lọc theo cột thứ hai của index nhiều cột bị chậm | Index có thứ tự cột chưa phù hợp truy vấn | Xem `EXPLAIN` và cân nhắc index theo nhu cầu lọc thực tế |
| Xóa cha làm mất nhiều dòng con | Đã khai báo `ON DELETE CASCADE` | Xem lại chính sách xóa theo nghiệp vụ |
| Thêm FK vào bảng cũ thất bại | Có các bộ giá trị con mồ côi hoặc thiếu khóa cha | Khảo sát, sửa dữ liệu trước khi thêm/validate constraint |
| Cùng câu SQL chạy khác trên SQLite/MySQL/PostgreSQL | Khác quy tắc FK, index, `MATCH` và cấu hình engine | Ghi rõ DBMS, phiên bản, cấu hình và truy vấn metadata |

## 16. Bài tập vận dụng

### Bài 1 — Dự đoán tính hợp lệ của tổ hợp

Bảng cha `projects` có PK `(tenant_id, project_code)` và các dòng `(1,'A')`, `(1,'B')`, `(2,'A')`. Bảng con có FK kép tương ứng, cả hai cột `NOT NULL`.

Cho biết từng bộ FK sau hợp lệ hay bị từ chối:

1. `(1,'A')`
2. `(2,'B')`
3. `(2,'A')`
4. `(3,'A')`
5. `(1,'B')`

**Gợi ý:** kiểm tra **cả cặp trong cùng dòng cha**, không kiểm tra từng cột độc lập.

### Bài 2 — Phát hiện lỗi đảo cột

Cho bảng cha:

```sql
CREATE TABLE warehouse_bins (
    warehouse_id BIGINT NOT NULL,
    bin_no       BIGINT NOT NULL,
    PRIMARY KEY (warehouse_id, bin_no)
);
```

Một bảng con định nghĩa:

```sql
FOREIGN KEY (bin_no, warehouse_id)
REFERENCES warehouse_bins (warehouse_id, bin_no)
```

Hãy viết hai cặp ánh xạ do DBMS thực sự kiểm tra và sửa FK đúng theo nghiệp vụ.

### Bài 3 — Phân biệt UNIQUE và FOREIGN KEY

Một bảng `users` cần cho phép username trùng giữa các tenant, nhưng không được trùng trong cùng tenant. Bảng `login_events` cần trỏ tới người dùng qua `(tenant_id, username)`. Hãy xác định ràng buộc nên có ở **cả hai bảng**, kèm yêu cầu `NULL` phù hợp.

### Bài 4 — Phân tích NULL

Một FK hai cột dùng `MATCH SIMPLE`. Vì sao bộ `(10, NULL)` có thể được chèn dù không có bản ghi cha? Nếu nghiệp vụ cho phép “hoặc cả bộ chưa có, hoặc cả bộ đã có”, cấu hình PostgreSQL nào thích hợp? Nếu nghiệp vụ **bắt buộc** có dự án, cần thêm gì?

### Bài 5 — Thứ tự index

Bảng `invoice_lines` thường được truy vấn:

```sql
SELECT *
FROM invoice_lines
WHERE store_id = 7
  AND invoice_no = 'INV-01';

SELECT *
FROM invoice_lines
WHERE store_id = 7;
```

Giữa index `(store_id, invoice_no)` và `(invoice_no, store_id)`, thứ tự nào thường phù hợp hơn với cả hai kiểu lọc? Tại sao việc chọn thứ tự index khác với việc được phép đảo tùy tiện thứ tự ở một vế FK?

### Bài 6 — JOIN nhiều cột

Bảng `employees` có `company_id` và `department_id`; bảng `departments` có PK `(company_id, department_id)`. Hãy viết `JOIN` đúng và giải thích nguy cơ khi chỉ nối bằng `department_id`.

### Đáp án tham khảo

1. Hợp lệ: `(1,'A')`, `(2,'A')`, `(1,'B')`. Không hợp lệ: `(2,'B')` và `(3,'A')`.
2. FK sai đang ghép `child.bin_no -> parent.warehouse_id` và `child.warehouse_id -> parent.bin_no`. Cần dùng `FOREIGN KEY (warehouse_id, bin_no) REFERENCES warehouse_bins(warehouse_id, bin_no)`.
3. Bảng `users` có `UNIQUE (tenant_id, username)` hoặc PK kép tương ứng; `login_events` có FK `(tenant_id, username)` trỏ tới cặp đó. Các trường dùng để xác định người dùng nên `NOT NULL` khi sự kiện bắt buộc có người dùng.
4. `MATCH SIMPLE` bỏ qua kiểm tra bộ tham chiếu nếu bất kỳ cột nào là `NULL`. PostgreSQL `MATCH FULL` chặn bộ thiếu một phần; `NOT NULL` trên từng cột đảm bảo bộ luôn được cung cấp đầy đủ.
5. `(store_id, invoice_no)` thường phù hợp hơn vì cả hai truy vấn đều lọc theo cột đầu `store_id`. Trong FK, thứ tự là **ánh xạ quan hệ theo từng vị trí**, không đơn thuần là gợi ý tối ưu.
6. `JOIN departments d ON d.company_id = e.company_id AND d.department_id = e.department_id`. Chỉ nối `department_id` có thể ghép nhân viên với phòng ban cùng số ở công ty khác.

Điều cần giữ vững khi sử dụng ràng buộc nhiều cột là: **PK/UNIQUE xác định tính duy nhất của cả bộ giá trị; FK kiểm tra đúng bộ giá trị đó ở bảng cha; thứ tự các cột trong FK quyết định phép ghép theo vị trí**. Sau khi khai báo, hãy quan sát metadata và thử các bộ giá trị hợp lệ/không hợp lệ để biết database đang bảo vệ đúng quan hệ dự kiến.
