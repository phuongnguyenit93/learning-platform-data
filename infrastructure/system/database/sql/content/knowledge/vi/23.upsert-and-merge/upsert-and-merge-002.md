# Khóa xác định xung đột và vai trò của UNIQUE

Trong một hệ thống có thao tác nhập mới và đồng bộ dữ liệu, cùng một khách hàng, sản phẩm hoặc đơn hàng có thể được gửi đến cơ sở dữ liệu nhiều lần. Lần đầu, ta muốn **INSERT**. Những lần sau, nếu bản ghi đã tồn tại, ta có thể muốn **UPDATE**, giữ nguyên hoặc báo lỗi. Mẫu thao tác ấy thường được gọi là **upsert** (*update or insert*); SQL cũng có lệnh **MERGE** để diễn đạt nhiều nhánh xử lý khi ghép nguồn với đích.

Nhưng trước khi hỏi “INSERT hay UPDATE?”, phải trả lời một câu hỏi quan trọng hơn:

> **Dựa vào khóa nào để xác định hai hàng là cùng một thực thể và thực sự xung đột?**

Nếu chọn sai khóa, một yêu cầu cập nhật có thể tạo thêm bản ghi trùng, cập nhật nhầm người, hoặc bị từ chối dù dữ liệu tưởng như hợp lệ. Nếu chỉ kiểm tra xem bản ghi tồn tại bằng SELECT rồi mới INSERT, hai tiến trình chạy đồng thời vẫn có thể tạo ra tình huống đua nhau. Trong các hệ quản trị SQL, **PRIMARY KEY**, **UNIQUE constraint** và **unique index** chính là những cơ chế nền tảng để định nghĩa và thực thi tính duy nhất.

Bài này thuộc chương **Upsert và MERGE** của module **Database SQL**. Trọng tâm là chọn đúng **khóa xác định xung đột**, hiểu vai trò của **UNIQUE** và dùng **ON CONFLICT** trên PostgreSQL. Ví dụ chính sử dụng **PostgreSQL 15 trở lên**, với các bảng tạm độc lập, đồng thời đối chiếu **MySQL**, **SQLite**, **SQL Server** và **Oracle**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **khóa chính kỹ thuật**, **khóa nghiệp vụ**, **khóa ghép** và **conflict target**.
2. Giải thích vì sao **PRIMARY KEY** hoặc **UNIQUE** phải bảo vệ điều kiện xung đột thay vì chỉ dùng SELECT kiểm tra trước.
3. Viết **INSERT ... ON CONFLICT (columns) DO UPDATE/DO NOTHING** đúng theo khóa duy nhất của PostgreSQL.
4. Dùng **ON CONFLICT ON CONSTRAINT constraint_name** khi muốn chỉ rõ ràng buộc được dùng.
5. Hiểu sự khác nhau giữa **UNIQUE(col)**, **UNIQUE(col1, col2)** và **UNIQUE NULLS NOT DISTINCT**.
6. Làm việc với **unique index có biểu thức** và **partial unique index**, kể cả cú pháp suy luận index trong ON CONFLICT.
7. Nhận biết một bảng có **nhiều UNIQUE**: xung đột ở một khóa có thể không được xử lý bởi conflict target đã chọn.
8. Phát hiện **hai hàng cùng khóa trong một batch nguồn** trước khi upsert.
9. Phân biệt điều kiện **ON của MERGE** với cơ chế **UNIQUE** thực thi tính duy nhất của bảng đích.
10. Chọn cách viết phù hợp với tính đồng thời, giá trị NULL, trường hợp soft-delete và phương ngữ SQL.

## 2. "Xung đột" có nghĩa gì trong dữ liệu?

Ví dụ một hệ thống quản lý khách hàng lưu hai loại mã:

- **customer_id**: ID do cơ sở dữ liệu sinh, dùng cho liên kết nội bộ.
- **external_customer_code**: mã do hệ thống đối tác gửi khi đồng bộ.

Khi đối tác gửi lại mã **C-001**, hệ thống có thể cần cập nhật khách hàng C-001 đang có, không tạo một hàng mới chỉ vì lần nhập mới chưa biết customer_id nội bộ.

Nhưng nếu ứng dụng phục vụ nhiều công ty (*tenant*), hai công ty hoàn toàn có thể cùng sử dụng mã **C-001**:

~~~text
tenant_id    external_customer_code    Khách hàng
---------    ----------------------    ----------
1            C-001                     An
2            C-001                     Chi
~~~

Do đó, **external_customer_code một mình không đủ xác định danh tính toàn hệ thống**. Khóa nghiệp vụ phù hợp ở ví dụ này là:

~~~text
(tenant_id, external_customer_code)
~~~

Cần phân biệt những khái niệm:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Primary key** | Định danh duy nhất, không NULL của hàng trong bảng | customer_id |
| **Khóa nghiệp vụ** | Bộ thuộc tính xác định “cùng một đối tượng” theo nghiệp vụ | (tenant_id, external_customer_code) |
| **Unique constraint** | Cấm các tổ hợp giá trị vi phạm quy tắc duy nhất | UNIQUE (tenant_id, external_customer_code) |
| **Unique index** | Cấu trúc chỉ mục duy nhất; có thể thể hiện biểu thức/điều kiện đặc thù | UNIQUE (LOWER(email)) |
| **Conflict target** | Khóa hoặc ràng buộc được nêu cho một thao tác ON CONFLICT | ON CONFLICT (tenant_id, external_customer_code) |
| **MERGE ON** | Điều kiện ghép nguồn và đích để quyết định MATCHED/NOT MATCHED | t.tenant_id = s.tenant_id AND t.code = s.code |

**Khóa nghiệp vụ** là một quyết định về ý nghĩa dữ liệu. **UNIQUE** là cách buộc cơ sở dữ liệu bảo vệ quyết định đó. **Conflict target** là cách một lệnh upsert cụ thể nói rõ nó định xử lý xung đột theo quy tắc duy nhất nào.

## 3. Dữ liệu thực hành PostgreSQL

Tạo bảng khách hàng tạm **demo_customer_registry** có cả khóa chính kỹ thuật và hai ràng buộc UNIQUE.

~~~sql
CREATE TEMP TABLE demo_customer_registry (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_customer_code TEXT NOT NULL,
    display_name TEXT NOT NULL,
    contact_email TEXT,
    modified_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),

    CONSTRAINT uq_demo_customer_tenant_external
        UNIQUE (tenant_id, external_customer_code),
    CONSTRAINT uq_demo_customer_tenant_email
        UNIQUE (tenant_id, contact_email),

    CONSTRAINT ck_demo_customer_code_not_blank
        CHECK (BTRIM(external_customer_code) <> ''),
    CONSTRAINT ck_demo_customer_name_not_blank
        CHECK (BTRIM(display_name) <> '')
);

INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name, contact_email)
VALUES
    (1, 'C-001', 'An',   'an@example.test'),
    (1, 'C-002', 'Binh', NULL),
    (2, 'C-001', 'Chi',  'chi@example.test');
~~~

Kiểm tra:

~~~sql
SELECT
    customer_id,
    tenant_id,
    external_customer_code,
    display_name,
    contact_email
FROM demo_customer_registry
ORDER BY tenant_id, external_customer_code;
~~~

Các hàng ban đầu:

| tenant_id | external_customer_code | display_name | contact_email |
| ---: | --- | --- | --- |
| 1 | C-001 | An | an@example.test |
| 1 | C-002 | Binh | NULL |
| 2 | C-001 | Chi | chi@example.test |

**Hai hàng C-001 ở hai tenant khác nhau đều hợp lệ** vì ràng buộc là duy nhất trên **cặp (tenant_id, external_customer_code)**, không phải trên external_customer_code toàn cục.

> Bảng TEMP chỉ tồn tại trong phiên PostgreSQL hiện tại. Những ví dụ INSERT/UPDATE minh họa sau đây thường được đặt trong **BEGIN ... ROLLBACK** để không làm thay đổi dữ liệu gốc của bài. Hãy chạy mỗi ví dụ sau khi tạo bảng và các hàng mẫu ở trên; những ví dụ được ghi chú “cố ý gây lỗi” không nên chạy lẫn với luồng thao tác sản xuất.

## 4. PRIMARY KEY và UNIQUE có giống nhau không?

**PRIMARY KEY** đảm bảo mỗi hàng có một định danh **duy nhất và không NULL**. PostgreSQL chỉ cho một khai báo PRIMARY KEY của một bảng, nhưng khóa chính có thể gồm nhiều cột.

**UNIQUE** đảm bảo các giá trị hoặc tổ hợp giá trị không trùng theo quy tắc của ràng buộc. Một bảng có thể có **nhiều ràng buộc UNIQUE**. Trong PostgreSQL, ràng buộc UNIQUE thông thường có cách xử lý NULL khác PRIMARY KEY; chi tiết ở phần 10.

So sánh:

| Đặc tính | PRIMARY KEY | UNIQUE |
| --- | --- | --- |
| Tính duy nhất | Có | Có |
| Cho phép NULL | **Không** | Có thể, tùy cột và chế độ NULL |
| Số lần khai báo mỗi bảng | Một PRIMARY KEY | Có thể có nhiều UNIQUE |
| Có thể là nhiều cột | Có | Có |
| Có chỉ mục hỗ trợ trong PostgreSQL | Có, unique B-tree | Có, unique B-tree đối với constraint |
| Dùng làm cơ chế xung đột cho ON CONFLICT | Có | Có, nếu đủ điều kiện làm arbiter |
| Có nhất thiết là khóa được đối tác dùng để đồng bộ? | Không | Không; tùy mô hình nghiệp vụ |

Trong bảng ví dụ, **customer_id** giúp các bảng nội bộ tham chiếu khách hàng. Nhưng tệp do đối tác gửi chỉ biết **tenant_id và external_customer_code**. Upsert theo **customer_id** sẽ không giải được việc “cùng khách hàng từ đối tác đã tồn tại chưa?” nếu nguồn không có customer_id nội bộ.

**Không phải cứ có PRIMARY KEY là nên dùng PRIMARY KEY làm conflict target của mọi luồng nhập.** Hãy chọn khóa đại diện cho **danh tính của đối tượng trong luồng dữ liệu đang xử lý**.

## 5. Cú pháp ON CONFLICT chọn khóa xung đột

Trên PostgreSQL, mẫu upsert cơ bản:

~~~sql
INSERT INTO target_table (key_col, value_col)
VALUES (...)
ON CONFLICT (key_col) DO UPDATE
SET value_col = EXCLUDED.value_col;
~~~

Đây là **mẫu cú pháp**, không phải truy vấn chạy trực tiếp vì target_table và các giá trị đang được rút gọn.

Hai phần cần hiểu:

1. **ON CONFLICT (key_col)**: tìm một **unique index/constraint phù hợp** với khóa được nêu để nhận diện xung đột. PostgreSQL gọi những chỉ mục/ràng buộc được dùng là **arbiter**.
2. **DO UPDATE ...**: khi bản ghi đầu vào gặp xung đột trên arbiter, cập nhật hàng hiện có thay vì báo lỗi trùng khóa.

Với bảng demo, khóa đúng là hai cột:

~~~sql
BEGIN;

INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name, contact_email)
VALUES
    (1, 'C-001', 'An Nguyen', 'an@example.test')
ON CONFLICT (tenant_id, external_customer_code)
DO UPDATE
SET
    display_name = EXCLUDED.display_name,
    contact_email = EXCLUDED.contact_email,
    modified_at = clock_timestamp()
RETURNING
    customer_id,
    tenant_id,
    external_customer_code,
    display_name,
    contact_email;

ROLLBACK;
~~~

Vì đã có hàng **(1, 'C-001')**, PostgreSQL dùng xung đột trên ràng buộc duy nhất của cặp khóa để thực hiện **UPDATE**. **customer_id của khách đang có được giữ nguyên**, không tạo một khách mới.

**EXCLUDED.display_name** và **EXCLUDED.contact_email** là các giá trị từ hàng **được đề xuất INSERT**, chứ không phải từ một bảng tên EXCLUDED trong schema.

**ROLLBACK** ở cuối ví dụ hủy thay đổi thực hành. Nếu thay bằng COMMIT thì tên khách sẽ thực sự được cập nhật trong phiên bảng tạm.

### 5.1. Không có xung đột thì INSERT

~~~sql
BEGIN;

INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name, contact_email)
VALUES
    (2, 'C-002', 'Dung', 'dung@example.test')
ON CONFLICT (tenant_id, external_customer_code)
DO UPDATE
SET display_name = EXCLUDED.display_name
RETURNING tenant_id, external_customer_code, display_name;

ROLLBACK;
~~~

Tuy tenant 1 đã có C-002, **tenant 2 chưa có C-002**, nên câu lệnh thực hiện **INSERT**. Đây là minh chứng rằng conflict target phải xét **đủ các cột của khóa ghép**.

### 5.2. Chọn sai khóa có thể gây lỗi

Nếu viết:

~~~sql
-- Cố ý sai trên bảng demo:
INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name)
VALUES (1, 'C-001', 'An moi')
ON CONFLICT (external_customer_code) DO UPDATE
SET display_name = EXCLUDED.display_name;
~~~

truy vấn **không suy ra được một unique arbiter chỉ trên external_customer_code**, vì bảng chỉ khai báo UNIQUE **(tenant_id, external_customer_code)**. PostgreSQL thường báo:

~~~text
there is no unique or exclusion constraint matching
the ON CONFLICT specification
~~~

Mã SQLSTATE thường gặp là **42P10**. **Không** có chuyện hệ quản trị tự hiểu external_customer_code là đủ duy nhất nhờ một UNIQUE nhiều cột.

Một lỗi khác cũng có thể xảy ra nếu chọn sai thứ tự khóa nghiệp vụ, ví dụ upsert theo một email có thể thay đổi thay vì mã khách ổn định. Trong trường hợp đó, câu SQL có thể chạy thành công nhưng cập nhật **khác thực thể** với dự định của hệ thống.

## 6. Khóa ghép: UNIQUE(a, b) không có nghĩa UNIQUE(a) và UNIQUE(b)

Khóa ghép có hai cột:

~~~sql
CONSTRAINT uq_demo_customer_tenant_external
    UNIQUE (tenant_id, external_customer_code)
~~~

Nghĩa là **không được có hai hàng trùng cả tenant_id lẫn external_customer_code** (theo quy tắc NULL của ràng buộc).

Nó **không yêu cầu**:

- Mọi tenant_id khác nhau.
- Mọi external_customer_code khác nhau trên toàn hệ thống.

Ví dụ hợp lệ:

~~~text
(tenant_id, external_customer_code)
(1, C-001)
(1, C-002)
(2, C-001)
(2, C-002)
~~~

Ví dụ không hợp lệ:

~~~text
(1, C-001)
(1, C-001)  ← trùng toàn bộ cặp khóa
~~~

**Một trường hợp quan trọng trong hệ đa tenant:** nếu vì tiện viết ON CONFLICT mà thêm UNIQUE(external_customer_code) toàn cục, ta sẽ **cấm** hai tenant sử dụng cùng mã C-001, trái với mô hình nghiệp vụ đã xác định.

### 6.1. Đủ thành phần của khóa

Một hệ thống đơn hàng có thể chọn:

~~~text
(tenant_id, source_system, external_order_no)
~~~

vì hai nguồn đối tác khác nhau có thể dùng cùng external_order_no. Nếu bỏ source_system, đơn từ hai nguồn sẽ bị nhận nhầm là một. Nếu bỏ tenant_id, đơn của khách thuê khác nhau có thể bị ghép nhầm.

Khi thiết kế upsert, hãy hỏi:

1. **Ai phát hành mã này?**
2. **Mã này chỉ duy nhất trong phạm vi nào?**
3. **Mã có bị tái sử dụng sau khi xóa hoặc hết hiệu lực không?**
4. **Có cần version, source_system hoặc tenant_id để phân biệt không?**
5. **Những trường nào có thể thay đổi mà không làm đối tượng trở thành đối tượng mới?**

Câu trả lời quyết định thành phần của UNIQUE và conflict target.

## 7. Suy luận unique index hay chỉ định constraint bằng tên?

PostgreSQL hỗ trợ hai cách nêu arbiter cho **ON CONFLICT DO UPDATE**.

### 7.1. Suy luận từ cột hoặc biểu thức

~~~sql
ON CONFLICT (tenant_id, external_customer_code)
DO UPDATE ...
~~~

PostgreSQL tìm **unique index phù hợp** với tập cột/biểu thức được nêu. Đối với unique index bình thường, thứ tự liệt kê cột trong conflict target không nhất thiết phải giống thứ tự định nghĩa index để suy luận được arbiter. Tuy nhiên, để người đọc dễ so sánh với quy tắc nghiệp vụ, nên viết theo thứ tự quen thuộc của ràng buộc.

Suy luận index thuận tiện khi một unique index được thay thế bằng một unique index tương đương theo quy trình migration, vì câu SQL vẫn thể hiện **ý nghĩa khóa** thay vì phụ thuộc vào tên constraint cụ thể.

### 7.2. Chỉ rõ tên ràng buộc

~~~sql
BEGIN;

INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name, contact_email)
VALUES (1, 'C-001', 'An Dieu Chinh', 'an@example.test')
ON CONFLICT ON CONSTRAINT uq_demo_customer_tenant_external
DO UPDATE
SET
    display_name = EXCLUDED.display_name,
    modified_at = clock_timestamp();

ROLLBACK;
~~~

**ON CONSTRAINT uq_demo_customer_tenant_external** tham chiếu **tên ràng buộc UNIQUE được khai báo trong CREATE TABLE**.

Ưu điểm:

- Người đọc biết chính xác ràng buộc nghiệp vụ được chọn.
- Dễ đối chiếu với định nghĩa schema đã quản lý bằng migration.

Điểm cần lưu ý:

- Nếu ràng buộc bị **đổi tên hoặc thay thế**, câu SQL tham chiếu tên cũ phải được cập nhật.
- **Tên một unique index tự tạo không nhất thiết là tên constraint**. Với một partial unique index hoặc expression unique index được tạo trực tiếp bằng CREATE UNIQUE INDEX, thường dùng **suy luận conflict target**, không giả định **ON CONSTRAINT ten_index** sẽ nhận tên index ấy.

### 7.3. Ràng buộc nào có thể làm arbiter?

Trong PostgreSQL, **unique index phù hợp và không trì hoãn kiểm tra (NOT DEFERRABLE)** là cơ chế thông dụng cho ON CONFLICT. PRIMARY KEY và UNIQUE thông thường được hỗ trợ bởi các unique index dạng này.

Một **UNIQUE constraint khai báo DEFERRABLE** không được dùng làm arbiter của ON CONFLICT theo cách thông thường. Cơ chế trì hoãn kiểm tra tính duy nhất đến cuối giao dịch không tương thích với yêu cầu quyết định xung đột ngay trong upsert.

**FOREIGN KEY**, **CHECK** và **NOT NULL** không phải conflict target cho hành vi INSERT-or-UPDATE. Những ràng buộc này vẫn phải được thỏa mãn, nhưng vi phạm chúng không được chuyển thành DO UPDATE chỉ bằng ON CONFLICT.

## 8. DO NOTHING: bỏ qua xung đột theo khóa nào?

PostgreSQL cho phép:

~~~sql
INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name)
VALUES (1, 'C-001', 'An trung')
ON CONFLICT (tenant_id, external_customer_code)
DO NOTHING;
~~~

Nếu khóa này đã tồn tại, câu lệnh **bỏ qua hàng đầu vào** thay vì INSERT hoặc UPDATE. Cách này có thể phù hợp với dữ liệu chỉ được phép thêm mới.

Ngoài ra, riêng **DO NOTHING**, PostgreSQL cho phép **bỏ conflict target**:

~~~sql
INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name, contact_email)
VALUES (1, 'C-099', 'Khach moi', 'an@example.test')
ON CONFLICT DO NOTHING;
~~~

Trong dữ liệu mẫu, tenant 1 đã có **contact_email = 'an@example.test'**. Câu này có thể **bỏ qua hàng** vì vi phạm UNIQUE trên **(tenant_id, contact_email)**, dù external_customer_code C-099 chưa có.

Điều đó khác:

~~~sql
-- Cố ý gây lỗi UNIQUE khác:
ON CONFLICT (tenant_id, external_customer_code) DO NOTHING
~~~

Khi chỉ định target **(tenant_id, external_customer_code)**, xung đột ở unique email **không được nhánh DO NOTHING đã chọn xử lý**; câu INSERT vẫn có thể lỗi vi phạm UNIQUE email.

**Bỏ conflict target với DO NOTHING có thể che giấu một loại xung đột ngoài ý định**, đặc biệt khi bảng có nhiều UNIQUE. Không nên dùng cú pháp này chỉ để “mọi lỗi trùng đều được bỏ qua” mà chưa biết khóa nào đang xung đột.

**DO NOTHING không bỏ qua lỗi FOREIGN KEY, CHECK hoặc NOT NULL**. Nó dành cho những trường hợp xung đột duy nhất phù hợp, không phải một bộ xử lý mọi lỗi dữ liệu.

## 9. Một bảng có nhiều UNIQUE: conflict target không phải giấy phép bỏ qua các ràng buộc khác

Bảng demo có hai UNIQUE nghiệp vụ:

~~~sql
UNIQUE (tenant_id, external_customer_code)
UNIQUE (tenant_id, contact_email)
~~~

Chúng trả lời hai câu hỏi khác nhau:

- Có được phép có **hai khách cùng external code trong một tenant** không? **Không.**
- Có được phép có **hai khách cùng email không NULL trong một tenant** không? **Không**, theo quy tắc ví dụ.

Giả sử nhận yêu cầu:

~~~sql
-- Cố ý gây lỗi: tenant 1 đã có email an@example.test ở C-001.
INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name, contact_email)
VALUES (1, 'C-099', 'Khach khac', 'an@example.test')
ON CONFLICT (tenant_id, external_customer_code)
DO UPDATE
SET display_name = EXCLUDED.display_name;
~~~

C-099 chưa có, vì vậy **không xảy ra xung đột theo conflict target đã chọn** và PostgreSQL thử INSERT. Nhưng email đã thuộc C-001 trong tenant 1, nên **UNIQUE (tenant_id, contact_email)** bị vi phạm. Kết quả là **lỗi UNIQUE**, không tự động cập nhật C-001.

### 9.1. Cả trong nhánh UPDATE, UNIQUE khác vẫn được kiểm tra

Ví dụ muốn cập nhật khách C-002 sang email đang thuộc C-001:

~~~sql
-- Cố ý gây lỗi: UPDATE của C-002 tạo trùng email C-001.
INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name, contact_email)
VALUES (1, 'C-002', 'Binh', 'an@example.test')
ON CONFLICT (tenant_id, external_customer_code)
DO UPDATE
SET contact_email = EXCLUDED.contact_email;
~~~

Lúc này có xung đột đúng target C-002, nên nhánh DO UPDATE được chọn. Tuy nhiên, **giá trị contact_email mới vẫn vi phạm UNIQUE khác**, vì vậy lệnh thất bại. ON CONFLICT **không vô hiệu hóa những ràng buộc còn lại của bảng đích**.

### 9.2. Quy tắc nghiệp vụ cần xác định trước

Nếu nguồn gửi C-099 cùng email C-001, hệ thống phải quyết định:

1. C-099 là khách mới nhưng email nguồn sai → **từ chối và điều tra**.
2. C-099 là mã thay thế cho C-001 → cần **quy trình đổi mã hoặc ánh xạ danh tính**, không tự cập nhật theo email.
3. Nhiều khách được phép dùng chung email → **UNIQUE email có thể không phù hợp**; cần xem lại mô hình.

**Không nên tự đổi conflict target từ external code sang email để làm câu SQL hết lỗi.** Việc đổi khóa upsert có thể làm thay đổi ý nghĩa “cùng khách hàng”.

## 10. NULL và UNIQUE: một nguồn xung đột dễ hiểu nhầm

Trong PostgreSQL, **UNIQUE thông thường coi NULL là khác nhau đối với mục đích kiểm tra duy nhất**. Nói cách khác, một UNIQUE có thể cho phép nhiều hàng cùng có NULL ở cột tham gia ràng buộc.

Ví dụ trong bảng demo:

~~~sql
CONSTRAINT uq_demo_customer_tenant_email
    UNIQUE (tenant_id, contact_email)
~~~

Tenant 1 đã có C-002 với email NULL. Ta vẫn có thể thêm một khách khác cùng tenant cũng có contact_email NULL:

~~~sql
BEGIN;

INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name, contact_email)
VALUES (1, 'C-004', 'Em', NULL);

SELECT tenant_id, external_customer_code, contact_email
FROM demo_customer_registry
WHERE tenant_id = 1
  AND contact_email IS NULL
ORDER BY external_customer_code;

ROLLBACK;
~~~

Trong transaction, truy vấn SELECT có **hai hàng với contact_email NULL**, vì **NULL không được coi là một địa chỉ email thực sự giống nhau** trong quy tắc UNIQUE mặc định.

### 10.1. Khóa ghép có NULL

Với UNIQUE(a,b) mặc định trong PostgreSQL, nếu **một thành phần của tổ hợp là NULL**, nhiều hàng có những thành phần còn lại giống nhau vẫn có thể được phép tồn tại vì các hàng chứa NULL không được coi là trùng để cưỡng chế duy nhất.

Điều này đặc biệt nguy hiểm nếu **external_customer_code cho phép NULL** nhưng người viết upsert lại kỳ vọng NULL sẽ khớp một khách hàng chưa được mã hóa:

~~~text
(tenant_id, external_customer_code)
(1, NULL)
(1, NULL)  ← có thể cùng tồn tại dưới UNIQUE mặc định
~~~

Trong schema chính của bài, **external_customer_code NOT NULL**, nên tình huống đó được chặn ngay tại bảng đích.

### 10.2. PostgreSQL 15+: UNIQUE NULLS NOT DISTINCT

Nếu nghiệp vụ **muốn NULL cũng được xem là trùng** khi kiểm tra UNIQUE, PostgreSQL 15+ hỗ trợ:

~~~sql
CREATE TEMP TABLE demo_external_links (
    tenant_id INTEGER NOT NULL,
    external_ref TEXT,
    note_text TEXT NOT NULL,
    CONSTRAINT uq_demo_external_links
        UNIQUE NULLS NOT DISTINCT (tenant_id, external_ref)
);
~~~

Thử upsert:

~~~sql
INSERT INTO demo_external_links
    (tenant_id, external_ref, note_text)
VALUES (1, NULL, 'Ban ghi dau');

INSERT INTO demo_external_links
    (tenant_id, external_ref, note_text)
VALUES (1, NULL, 'Ban ghi cap nhat')
ON CONFLICT (tenant_id, external_ref)
DO UPDATE
SET note_text = EXCLUDED.note_text;

SELECT tenant_id, external_ref, note_text
FROM demo_external_links;
~~~

Kết quả có **một hàng (1, NULL, 'Ban ghi cap nhat')** vì ràng buộc coi hai NULL ở cùng vị trí là **NOT DISTINCT** cho mục đích duy nhất.

**Cảnh báo về thiết kế:** chỉ chọn NULLS NOT DISTINCT khi hai giá trị thiếu thật sự phải đại diện cho **cùng một khóa nghiệp vụ**. Nếu NULL chỉ có nghĩa “chưa biết mã của khách”, gộp tất cả khách thiếu mã thành một hàng sẽ **sai dữ liệu**. Trong nhiều bài toán, cách tốt hơn là bắt khóa upsert **NOT NULL** và xử lý dòng thiếu khóa ở bước staging.

### 10.3. NULL, chuỗi rỗng và khoảng trắng

~~~text
NULL       → thiếu/không xác định theo mô hình
''         → chuỗi rỗng
'   '      → chuỗi chứa khoảng trắng
~~~

Trong PostgreSQL TEXT, ba giá trị trên không đồng nhất. Một UNIQUE trên TEXT có thể phân biệt chuỗi rỗng với NULL, và có thể coi **'C-001'** khác **' C-001 '** nếu chưa chuẩn hóa.

Vì vậy, ràng buộc UNIQUE chỉ bảo vệ **những giá trị mà cơ sở dữ liệu thực sự nhận được**. Nếu nghiệp vụ yêu cầu bỏ khoảng trắng hoặc không phân biệt hoa/thường, phải đưa quy tắc chuẩn hóa đó vào thiết kế dữ liệu và chỉ mục.

## 11. UNIQUE không tự hiểu C-001 và c-001 là cùng mã

Với cột TEXT và quy tắc so sánh thông thường trên PostgreSQL, các chuỗi có chữ hoa/thường khác nhau có thể được xem là các giá trị khác nhau:

~~~text
C-001
c-001
 C-001
~~~

Nếu nguồn từ đối tác quy định mã không phân biệt hoa/thường và bỏ khoảng trắng hai đầu, hệ thống nên định nghĩa một **dạng chuẩn**:

~~~sql
UPPER(BTRIM(external_customer_code))
~~~

Một hướng thiết kế là **chuẩn hóa ngay trước khi INSERT**, rồi lưu mã đã chuẩn hóa. Hướng khác là **unique expression index**, ví dụ trên LOWER(email) để kiểm soát email không phân biệt chữ hoa/thường theo quy ước cụ thể.

**Lưu ý:** UPPER/LOWER, collation và quy tắc so sánh Unicode có thể khác giữa cấu hình hoặc hệ quản trị. Khi mã là chuỗi nhận dạng có quy tắc nghiêm ngặt, phải xác định rõ phép chuẩn hóa, không dựa vào cảm giác rằng UNIQUE sẽ tự biết hai chuỗi “trông giống nhau”.

## 12. Unique index theo biểu thức: xung đột trên LOWER(email)

Đôi khi bảng cần giữ nguyên giá trị email gốc để hiển thị, nhưng vẫn muốn **không có hai email giống nhau nếu bỏ qua chữ hoa/thường**.

Tạo bảng riêng để không trộn với ràng buộc email của demo_customer_registry:

~~~sql
CREATE TEMP TABLE demo_case_emails (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL,
    contact_name TEXT NOT NULL
);

CREATE UNIQUE INDEX uq_demo_case_emails_lower
    ON demo_case_emails ((LOWER(email)));

INSERT INTO demo_case_emails(email, contact_name)
VALUES ('An@Example.Test', 'An');
~~~

Unique index dùng **LOWER(email)**, nên hai chuỗi:

~~~text
An@Example.Test
an@example.test
~~~

được so sánh qua biểu thức **lower**. Theo quy tắc của index, chúng xung đột.

### 12.1. Upsert theo unique expression index

~~~sql
BEGIN;

INSERT INTO demo_case_emails(email, contact_name)
VALUES ('an@example.test', 'An Moi')
ON CONFLICT ((LOWER(email)))
DO UPDATE
SET
    contact_name = EXCLUDED.contact_name
RETURNING id, email, contact_name;

ROLLBACK;
~~~

**ON CONFLICT ((LOWER(email)))** nêu **biểu thức khóa** để PostgreSQL suy luận unique index tương ứng. Khi gặp xung đột, hàng đang có được UPDATE contact_name. Trong ví dụ, cột email của hàng cũ **không bị thay đổi**, vì SET chỉ cập nhật contact_name.

**Không dùng ON CONSTRAINT uq_demo_case_emails_lower** ở đây: đó là **tên index được tạo trực tiếp**, không phải tên một constraint trong CREATE TABLE.

### 12.2. UNIQUE expression có thay thế chuẩn hóa dữ liệu không?

Nó có thể bảo vệ một quy tắc so sánh cụ thể, nhưng không giải quyết mọi câu hỏi:

- Có bỏ khoảng trắng hai đầu trước khi so sánh không?
- Có so sánh Unicode theo collation nào?
- Email có trường hợp phân biệt chữ hoa/thường theo hợp đồng nguồn không?
- Giá trị NULL được cho phép không?
- Unique toàn hệ thống hay chỉ trong tenant?

Nếu cần theo tenant, một index có thể kết hợp cột và biểu thức:

~~~sql
-- Mẫu thiết kế trên một bảng giả định có tenant_id và email:
CREATE UNIQUE INDEX uq_tenant_email_normalized
    ON tenant_contacts (tenant_id, (LOWER(BTRIM(email))));
~~~

Tương ứng, conflict target phải mô tả đúng **tenant_id và biểu thức lower(trim)**, không phải chỉ email thô.

**Mẫu trên là ý tưởng thiết kế**, không chạy trực tiếp khi chưa có bảng tenant_contacts. Hãy xác định biểu thức chuẩn hóa một lần và sử dụng nhất quán ở nơi nhập, truy vấn và ràng buộc.

## 13. Partial unique index: chỉ một bản ghi đang hoạt động

Một quy tắc nghiệp vụ phổ biến:

> Mỗi khách hàng chỉ có **tối đa một** địa chỉ liên hệ **active** thuộc một loại, nhưng có thể lưu nhiều bản ghi lịch sử **inactive**.

Nếu dùng UNIQUE trên toàn bộ (tenant_id, customer_code), hệ thống sẽ cấm cả việc lưu bản ghi lịch sử. Nếu không có UNIQUE nào, hai bản ghi active có thể cùng tồn tại.

**Partial unique index** giải bài toán **duy nhất trong một tập hàng thỏa điều kiện**.

~~~sql
CREATE TEMP TABLE demo_contact_aliases (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_code TEXT NOT NULL,
    contact_address TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE UNIQUE INDEX uq_demo_active_contact_per_customer
    ON demo_contact_aliases (tenant_id, customer_code)
    WHERE is_active;
~~~

Ý nghĩa index:

- Với những hàng có **is_active = TRUE**, không được có hai hàng trùng **(tenant_id, customer_code)**.
- Với những hàng **is_active = FALSE**, quy tắc index này **không áp dụng**. Có thể có nhiều bản ghi lịch sử trùng cặp khóa.

Đưa một liên hệ active vào bảng:

~~~sql
INSERT INTO demo_contact_aliases
    (tenant_id, customer_code, contact_address, is_active)
VALUES (1, 'C-001', 'old@example.test', TRUE);
~~~

Upsert một liên hệ active khác:

~~~sql
BEGIN;

INSERT INTO demo_contact_aliases
    (tenant_id, customer_code, contact_address, is_active)
VALUES (1, 'C-001', 'new@example.test', TRUE)
ON CONFLICT (tenant_id, customer_code) WHERE is_active
DO UPDATE
SET contact_address = EXCLUDED.contact_address
RETURNING tenant_id, customer_code, contact_address, is_active;

ROLLBACK;
~~~

**WHERE is_active ngay sau conflict target** mô tả **điều kiện của partial unique index** để PostgreSQL có thể suy luận arbiter phù hợp. Đây **không phải** điều kiện lọc hàng nào được UPDATE trong nhánh DO UPDATE; điều kiện lọc UPDATE, nếu có, nằm **sau mệnh đề SET**.

### 13.1. Hai vị trí WHERE khác nhau

~~~sql
ON CONFLICT (tenant_id, customer_code) WHERE is_active
DO UPDATE SET contact_address = EXCLUDED.contact_address
WHERE demo_contact_aliases.contact_address
      IS DISTINCT FROM EXCLUDED.contact_address;
~~~

Trong đó:

1. **WHERE is_active** ở phần conflict target hỗ trợ suy luận **partial unique index**.
2. **WHERE ... IS DISTINCT FROM ...** sau SET quyết định **có thực hiện UPDATE hay không khi đã nhận ra xung đột**.

Hai WHERE không có cùng chức năng. Trường hợp WHERE sau SET là FALSE, câu lệnh **không chuyển thành INSERT**; hàng xung đột có thể được giữ nguyên.

### 13.2. Một index partial không bảo đảm “chính xác một” bản ghi

Ràng buộc unique partial bảo đảm **tối đa một** hàng active cho một khóa. Nó **không bảo đảm luôn có ít nhất một** hàng active.

Nếu nghiệp vụ yêu cầu **mỗi khách luôn phải có một liên hệ active**, cần thêm thiết kế hoặc cơ chế kiểm tra riêng. UNIQUE chỉ chặn **nhiều hơn một**, không bắt buộc tạo ra một hàng khi chưa có.

### 13.3. Soft delete và khóa xung đột

Tương tự, có thể bảo vệ:

~~~sql
CREATE UNIQUE INDEX uq_active_code
    ON business_records (tenant_id, business_code)
    WHERE deleted_at IS NULL;
~~~

Đây là **mẫu trên bảng business_records giả định**. Nó cho phép mã business_code xuất hiện trong các bản ghi đã soft-delete, nhưng chỉ một hàng có deleted_at NULL trên cùng (tenant_id, business_code).

Nếu upsert chỉ những hàng đang còn hiệu lực, conflict target phải tương ứng với quy tắc partial unique. Ngoài ra cần xác định: khi mã đã có ở hàng bị xóa mềm, yêu cầu mới **tạo bản ghi mới** hay **khôi phục hàng cũ**? UNIQUE partial một mình không quyết định chính sách này.

### 13.4. Partial index và non-partial index cùng tồn tại

Nếu bảng còn có một unique index **không có điều kiện** trên cùng cột, PostgreSQL có thể suy luận cả unique index không partial đáp ứng conflict target, ngay cả khi conflict target có WHERE phù hợp với một index partial.

Vì vậy, đừng chỉ nhìn câu:

~~~sql
ON CONFLICT (tenant_id, customer_code) WHERE is_active
~~~

rồi kết luận hệ thống chắc chắn chỉ xét xung đột của các hàng active **nếu schema còn có một quy tắc UNIQUE toàn phần cùng khóa**. Cần kiểm tra **toàn bộ các unique index thực tế** và định nghĩa nghiệp vụ của chúng.

## 14. Vì sao một tên index không luôn dùng được với ON CONSTRAINT?

Trong PostgreSQL có liên hệ nhưng không đồng nhất hoàn toàn giữa **constraint** và **index**.

Ví dụ:

~~~sql
ALTER TABLE demo_customer_registry
ADD CONSTRAINT uq_demo_other_field UNIQUE (...);
~~~

Trong ngữ cảnh bảng có cột phù hợp, thao tác trên tạo **unique constraint** và PostgreSQL có index hỗ trợ nó. Đây là cú pháp **minh họa**, vì dấu ba chấm chưa chỉ cột thực tế.

Ngược lại:

~~~sql
CREATE UNIQUE INDEX uq_demo_active_contact_per_customer
    ON demo_contact_aliases (tenant_id, customer_code)
    WHERE is_active;
~~~

định nghĩa một **unique index có điều kiện**, không phải một unique constraint thông thường có thể tham chiếu bằng **ON CONSTRAINT**.

Bởi vậy:

| Schema | Cách nêu arbiter thường dùng |
| --- | --- |
| UNIQUE (tenant_id, external_customer_code) có tên constraint | ON CONFLICT (tenant_id, external_customer_code) hoặc ON CONSTRAINT ten_constraint |
| PRIMARY KEY(customer_id) | ON CONFLICT (customer_id) hoặc ON CONSTRAINT tên PRIMARY KEY |
| CREATE UNIQUE INDEX trên LOWER(email) | ON CONFLICT ((LOWER(email))) |
| CREATE UNIQUE INDEX ... WHERE is_active | ON CONFLICT (columns) WHERE is_active |

**Không phải cứ thấy chữ UNIQUE trong tên một index là có thể viết ON CONSTRAINT tên_index.**

## 15. Trường hợp deferrable UNIQUE

PostgreSQL cho phép một số ràng buộc UNIQUE được khai báo **DEFERRABLE**, nghĩa là việc kiểm tra có thể được trì hoãn theo cơ chế transaction.

~~~sql
CREATE TEMP TABLE demo_deferred_codes (
    id INTEGER PRIMARY KEY,
    ref_code TEXT,
    CONSTRAINT uq_demo_deferred_ref
        UNIQUE (ref_code) DEFERRABLE INITIALLY DEFERRED
);
~~~

Loại ràng buộc này hữu ích cho một số phép thay đổi dữ liệu phức tạp, nhưng **không phải arbiter hợp lệ cho ON CONFLICT** của PostgreSQL.

Ví dụ ý định sau không phải một thiết kế upsert phù hợp:

~~~sql
-- Không dùng làm mẫu hợp lệ:
INSERT INTO demo_deferred_codes(id, ref_code)
VALUES (1, 'X')
ON CONFLICT (ref_code) DO UPDATE
SET id = EXCLUDED.id;
~~~

**Upsert cần quyết định ngay hàng nào đang xung đột** để thực hiện INSERT hoặc UPDATE. Nếu UNIQUE được trì hoãn kiểm tra đến thời điểm khác, PostgreSQL không hỗ trợ dùng nó làm conflict arbiter.

Khi một trường là khóa đồng bộ, nên cân nhắc liệu nó cần một **UNIQUE NOT DEFERRABLE** riêng phù hợp với thao tác upsert, hoặc thiết kế lại quy trình cập nhật có khóa/transaction tương ứng. Không tùy tiện bỏ DEFERRABLE khỏi một schema hiện tại nếu các quy trình khác đang cần nó.

## 16. Cùng một batch đầu vào có nhiều hàng trùng khóa

Cho dù bảng đích có UNIQUE đúng, **một câu INSERT ... ON CONFLICT DO UPDATE với nhiều hàng nguồn cùng khóa** vẫn có vấn đề.

Giả sử dữ liệu đầu vào gồm:

~~~text
source_row_no  tenant_id  external_code  name
-------------  ---------  -------------  ----
1              1          C-050          Nam
2              1          C-050          Nam Updated
~~~

Nếu gửi cả hai hàng trong **một** câu INSERT với cùng conflict target:

~~~sql
-- Cố ý gây lỗi trong PostgreSQL: hai nguồn cùng một khóa.
INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name)
VALUES
    (1, 'C-050', 'Nam'),
    (1, 'C-050', 'Nam Updated')
ON CONFLICT (tenant_id, external_customer_code)
DO UPDATE
SET display_name = EXCLUDED.display_name;
~~~

PostgreSQL **không cho một câu ON CONFLICT DO UPDATE tác động cùng một hàng đích nhiều lần**; có thể báo lỗi cardinality violation với SQLSTATE **21000**. Trường hợp nguồn có hai hàng cùng khóa cần được xử lý **trước khi gửi vào upsert**.

### 16.1. Kiểm tra duplicate trước khi upsert

~~~sql
WITH incoming(source_row_no, tenant_id, external_code, display_name) AS (
    VALUES
        (1, 1, 'C-050'::TEXT, 'Nam'::TEXT),
        (2, 1, 'C-050'::TEXT, 'Nam Updated'::TEXT),
        (3, 2, 'C-050'::TEXT, 'Chi'::TEXT)
)
SELECT tenant_id, external_code, COUNT(*) AS occurrences
FROM incoming
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1
ORDER BY tenant_id, external_code;
~~~

Kết quả có một cặp bị trùng: **tenant 1, C-050**, occurrences = 2. **Tenant 2, C-050 không trùng** với tenant 1 vì khóa định danh bao gồm tenant_id.

### 16.2. Nếu nghiệp vụ cho phép “hàng mới nhất thắng”

Muốn chọn đúng một hàng nguồn cho mỗi khóa, cần **quy tắc phá hòa**. Giả sử thứ tự tăng source_row_no tương ứng bản ghi đến sau được ưu tiên:

~~~sql
WITH
    incoming(source_row_no, tenant_id, external_code, display_name) AS (
        VALUES
            (1, 1, 'C-050'::TEXT, 'Nam'::TEXT),
            (2, 1, 'C-050'::TEXT, 'Nam Updated'::TEXT),
            (3, 2, 'C-050'::TEXT, 'Chi'::TEXT)
    ),
    ranked AS (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY tenant_id, external_code
                ORDER BY source_row_no DESC
            ) AS rn
        FROM incoming
    )
SELECT tenant_id, external_code, display_name
FROM ranked
WHERE rn = 1
ORDER BY tenant_id, external_code;
~~~

Kết quả giữ:

~~~text
(1, C-050, Nam Updated)
(2, C-050, Chi)
~~~

Nếu source_row_no không phải thứ tự nghiệp vụ, dùng **source_version**, **source_updated_at** hoặc trường ưu tiên thực sự đáng tin. Không dùng ROW_NUMBER với ORDER BY tùy ý chỉ để câu UPSERT chạy thành công.

### 16.3. CTE nguồn đã chọn có thể ghép vào INSERT

~~~sql
BEGIN;

WITH
    incoming(source_row_no, tenant_id, external_code, display_name) AS (
        VALUES
            (1, 1, 'C-050'::TEXT, 'Nam'::TEXT),
            (2, 1, 'C-050'::TEXT, 'Nam Updated'::TEXT),
            (3, 2, 'C-050'::TEXT, 'Chi'::TEXT)
    ),
    ranked AS (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY tenant_id, external_code
                   ORDER BY source_row_no DESC
               ) AS rn
        FROM incoming
    )
INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name)
SELECT tenant_id, external_code, display_name
FROM ranked
WHERE rn = 1
ON CONFLICT (tenant_id, external_customer_code)
DO UPDATE
SET display_name = EXCLUDED.display_name
RETURNING tenant_id, external_customer_code, display_name;

ROLLBACK;
~~~

Điều quan trọng là **một dòng nguồn trên mỗi khóa xung đột trước khi INSERT**. Đây không phải công việc mà UNIQUE của bảng đích tự quyết định thay nghiệp vụ.

## 17. UNIQUE là hàng rào bảo vệ cạnh tranh đồng thời

Một cách viết dễ gặp nhưng không an toàn khi có nhiều tiến trình:

~~~text
Worker A                         Worker B
--------                         --------
SELECT thấy C-900 chưa có       SELECT thấy C-900 chưa có
        |                               |
        v                               v
INSERT C-900                    INSERT C-900
~~~

Nếu bảng **không có UNIQUE trên khóa nghiệp vụ**, cả hai INSERT có thể thành công, tạo **hai hàng cùng khách**.

Nếu bảng có UNIQUE, ít nhất một thao tác sẽ phải xử lý xung đột theo cơ chế của cơ sở dữ liệu. Tùy câu SQL, hệ quản trị có thể:

- Báo lỗi vi phạm UNIQUE.
- Bỏ qua hàng bằng DO NOTHING.
- Thực hiện UPDATE qua ON CONFLICT DO UPDATE.

Trong PostgreSQL, với **INSERT ... ON CONFLICT DO UPDATE** và một arbiter hợp lệ, cơ chế này cho phép xử lý INSERT/UPDATE **có tính nguyên tử đối với xung đột mục tiêu**, kể cả khi nhiều transaction đồng thời cố ghi cùng khóa (các lỗi độc lập vẫn có thể xảy ra).

### 17.1. Vì sao SELECT ... WHERE NOT EXISTS chưa đủ?

Một câu viết kiểu:

~~~sql
INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name)
SELECT 1, 'C-900', 'Khach moi'
WHERE NOT EXISTS (
    SELECT 1
    FROM demo_customer_registry
    WHERE tenant_id = 1
      AND external_customer_code = 'C-900'
);
~~~

chỉ kiểm tra trên dữ liệu mà transaction **nhìn thấy ở thời điểm câu SELECT thực thi**. Hai giao dịch đồng thời có thể đều quan sát “chưa có” trước khi bên nào ghi xong.

Với UNIQUE ở bảng đích, một INSERT trùng vẫn bị chặn. Nhưng **NOT EXISTS không thay thế UNIQUE** để bảo đảm duy nhất.

**Nguyên tắc:** kiểm tra trước có thể dùng để đưa thông báo thân thiện, nhưng **ràng buộc UNIQUE tại cơ sở dữ liệu là lớp cưỡng chế cuối cùng** cho tính duy nhất khi có nhiều writer.

### 17.2. ON CONFLICT không giải quyết mọi vấn đề concurrency

Ví dụ hai batch cùng cập nhật C-001:

- Batch A muốn display_name = 'An A'.
- Batch B muốn display_name = 'An B'.

UNIQUE bảo đảm chỉ có **một hàng C-001**, nhưng không tự quyết định **giá trị phiên bản nào là đúng**. Nếu chỉ UPDATE vô điều kiện, kết quả phụ thuộc thứ tự cập nhật/commit và những transaction liên quan.

Với dữ liệu đồng bộ có phiên bản, có thể thêm **source_version** và điều kiện UPDATE theo version:

~~~sql
-- Mẫu trên bảng giả định có cột source_version:
ON CONFLICT (tenant_id, external_customer_code)
DO UPDATE
SET
    display_name = EXCLUDED.display_name,
    source_version = EXCLUDED.source_version
WHERE target_table.source_version < EXCLUDED.source_version
~~~

Đoạn trên là **mẫu ý tưởng**, chưa phải câu chạy trực tiếp, vì demo_customer_registry không có source_version và tên target_table chỉ là ký hiệu. Khi triển khai, cần thiết kế kiểu version, nguồn có quyền cập nhật và quy tắc xử lý phiên bản bằng nhau.

**UNIQUE trả lời “có một hàng hay nhiều hàng?”; chính sách phiên bản trả lời “hàng ấy mang dữ liệu của lần cập nhật nào?”**

## 18. ON CONFLICT ... DO UPDATE WHERE không tạo nhánh INSERT thứ hai

Khi đã xác định xung đột, bạn có thể muốn **không UPDATE nếu dữ liệu giống hệt**:

~~~sql
BEGIN;

INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name, contact_email)
VALUES
    (1, 'C-001', 'An', 'an@example.test')
ON CONFLICT (tenant_id, external_customer_code)
DO UPDATE
SET
    display_name = EXCLUDED.display_name,
    contact_email = EXCLUDED.contact_email,
    modified_at = clock_timestamp()
WHERE (
    demo_customer_registry.display_name,
    demo_customer_registry.contact_email
) IS DISTINCT FROM (
    EXCLUDED.display_name,
    EXCLUDED.contact_email
)
RETURNING customer_id, tenant_id, external_customer_code;

ROLLBACK;
~~~

Với dữ liệu ban đầu, hai giá trị nguồn và đích giống nhau, nên điều kiện **IS DISTINCT FROM** là FALSE. PostgreSQL có thể nhận diện/khóa hàng xung đột nhưng **không thực hiện UPDATE**; **RETURNING không trả hàng không được INSERT hoặc UPDATE**.

Điểm quan trọng:

- Conflict target vẫn là **(tenant_id, external_customer_code)**.
- WHERE **sau SET** chỉ quyết định **UPDATE hay bỏ qua cập nhật**.
- Nếu UPDATE không được thực hiện, cơ sở dữ liệu **không quay lại thử INSERT hàng có khóa trùng**.
- Không nên dùng việc RETURNING rỗng mà không xét ngữ cảnh để suy ra dữ liệu đầu vào “chưa từng tồn tại”.

Mẫu này hữu ích để giảm các lần ghi/updated_at không cần thiết trong luồng đồng bộ lặp lại.

## 19. Thế nào là một conflict target hợp lệ?

Xét các trường hợp PostgreSQL sau:

| Conflict target | Cần có gì ở bảng đích? | Kết quả kỳ vọng |
| --- | --- | --- |
| **(customer_id)** | PRIMARY KEY hoặc UNIQUE hợp lệ trên customer_id | Có thể dùng làm arbiter |
| **(tenant_id, external_customer_code)** | UNIQUE hợp lệ trên cặp khóa này | Có thể dùng làm arbiter |
| **(external_customer_code)** | UNIQUE riêng trên external_customer_code | Không hợp lệ nếu chỉ có UNIQUE(tenant_id, code) |
| **ON CONSTRAINT uq_demo_customer_tenant_external** | Constraint tên đó tồn tại và có thể làm arbiter | Có thể dùng |
| **((LOWER(email)))** | Unique expression index tương ứng | Có thể suy luận index |
| **(tenant_id, code) WHERE active** | Unique partial index tương ứng hoặc index phù hợp khác | Có thể suy luận nếu điều kiện phù hợp |
| **(price)** mà bảng chỉ có CHECK(price > 0) | Không có arbiter duy nhất trên price | Không hợp lệ cho DO UPDATE |

Trong PostgreSQL, **DO UPDATE yêu cầu một conflict target**, trong khi **DO NOTHING có thể bỏ conflict target** để bỏ qua những xung đột duy nhất được hỗ trợ.

Một index bình thường không có UNIQUE, ví dụ:

~~~sql
CREATE INDEX idx_demo_customer_code_lookup
ON demo_customer_registry(external_customer_code);
~~~

chỉ hỗ trợ tra cứu; nó **không chứng minh external_customer_code là duy nhất**, nên không dùng làm arbiter cho ON CONFLICT DO UPDATE chỉ trên cột đó.

**Chỉ mục để tăng tốc tra cứu** và **chỉ mục duy nhất để cưỡng chế khóa** là hai mục đích khác nhau.

## 20. UNIQUE được tạo sau khi đã có dữ liệu trùng: chuyện gì xảy ra?

Giả sử một bảng lịch sử chưa có UNIQUE và đã tồn tại:

~~~text
tenant_id  external_code  display_name
1          C-001          An
1          C-001          An Nguyen
1          C-002          Binh
~~~

Nếu chạy:

~~~sql
-- Minh họa trên bảng giả định historical_customers:
ALTER TABLE historical_customers
ADD CONSTRAINT uq_hist_tenant_code
UNIQUE (tenant_id, external_code);
~~~

cơ sở dữ liệu sẽ phải kiểm tra dữ liệu có thỏa quy tắc duy nhất hay không. Nếu hai hàng (1, C-001) vẫn tồn tại, thao tác tạo ràng buộc có thể **thất bại**, vì UNIQUE không thể “hợp thức hóa” dữ liệu trùng đã có.

### 20.1. Phát hiện duplicate trước migration

~~~sql
-- Áp dụng cho một bảng thực tế trước khi thêm UNIQUE.
SELECT
    tenant_id,
    external_code,
    COUNT(*) AS duplicate_count
FROM historical_customers
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, tenant_id, external_code;
~~~

Nếu khóa thực cần chuẩn hóa:

~~~sql
SELECT
    tenant_id,
    UPPER(BTRIM(external_code)) AS normalized_code,
    COUNT(*) AS duplicate_count
FROM historical_customers
GROUP BY tenant_id, UPPER(BTRIM(external_code))
HAVING COUNT(*) > 1;
~~~

Truy vấn thứ hai giúp phát hiện cả những bản ghi **không trùng về chuỗi thô nhưng sẽ trùng sau chuẩn hóa**.

### 20.2. Một lộ trình migration an toàn về ý nghĩa

1. Xác định **khóa nghiệp vụ chính xác**, kể cả tenant và hệ thống nguồn.
2. Thống kê trùng khóa hiện có và những trường hợp NULL.
3. Chọn quy tắc xử lý mỗi nhóm trùng: **gộp hồ sơ, giữ bản mới nhất, đánh dấu lịch sử, từ chối và điều tra**.
4. Cập nhật tham chiếu FK và các hệ thống liên quan nếu gộp bản ghi.
5. Chuẩn hóa dữ liệu theo quy tắc sẽ được lưu/đánh chỉ mục.
6. Thêm UNIQUE bằng quy trình migration phù hợp quy mô và yêu cầu khóa bảng.
7. Triển khai upsert dùng đúng conflict target và kiểm tra luồng nhập hiện hữu.

Không nên dùng **DELETE tùy ý** để xóa những hàng trùng chỉ nhằm tạo được UNIQUE: một hàng tưởng là bản sao có thể được các đơn hàng hoặc dữ liệu khác tham chiếu.

## 21. Phân biệt MERGE ON với UNIQUE của bảng đích

**MERGE** có thể chọn nhánh theo quan hệ ghép giữa nguồn và đích:

~~~sql
MERGE INTO target AS t
USING source AS s
ON t.business_key = s.business_key
WHEN MATCHED THEN
    UPDATE SET ...
WHEN NOT MATCHED THEN
    INSERT (...) VALUES (...);
~~~

Đây là **khung cú pháp**, không phải câu SQL chạy trực tiếp. Trong MERGE:

- **ON** xác định hàng nguồn nào **khớp với hàng đích**.
- **WHEN MATCHED** thường xử lý cập nhật hoặc các hành động được hệ hỗ trợ.
- **WHEN NOT MATCHED** thường xử lý chèn mới.

Điều kiện **ON** không tự biến những cột đang so sánh thành một **ràng buộc UNIQUE**. Nếu bảng đích cho phép nhiều hàng cùng business_key, một hàng nguồn có thể khớp nhiều hàng đích, gây xử lý mơ hồ hoặc cập nhật nhiều đối tượng không mong muốn, tùy câu lệnh và hệ quản trị.

### 21.1. PostgreSQL 15+: ví dụ MERGE theo khóa ghép

~~~sql
BEGIN;

MERGE INTO demo_customer_registry AS t
USING (
    VALUES
        (1, 'C-001'::TEXT, 'An Moi'::TEXT,
            'an@example.test'::TEXT),
        (3, 'C-010'::TEXT, 'Lan'::TEXT,
            'lan@example.test'::TEXT)
) AS s(tenant_id, external_customer_code, display_name, contact_email)
ON t.tenant_id = s.tenant_id
   AND t.external_customer_code = s.external_customer_code
WHEN MATCHED THEN
    UPDATE SET
        display_name = s.display_name,
        contact_email = s.contact_email,
        modified_at = clock_timestamp()
WHEN NOT MATCHED THEN
    INSERT
        (tenant_id, external_customer_code, display_name, contact_email)
    VALUES
        (s.tenant_id, s.external_customer_code,
         s.display_name, s.contact_email);

ROLLBACK;
~~~

Kết quả logic:

- Nguồn **(1, C-001)** khớp hàng có sẵn → UPDATE.
- Nguồn **(3, C-010)** chưa có trong đích → INSERT.

**UNIQUE (tenant_id, external_customer_code)** ở bảng đích vẫn là ràng buộc bảo vệ tính duy nhất. MERGE phải được thiết kế để nguồn có khóa rõ và không tạo nhiều tác động không mong muốn lên cùng hàng.

### 21.2. ON nên diễn đạt danh tính, không trộn tùy ý điều kiện lọc

Giả sử thêm vào MERGE ON:

~~~sql
AND t.display_name = s.display_name
~~~

Khi nguồn muốn đổi display_name, hàng cũ có cùng mã nhưng tên khác sẽ **không còn MATCHED theo ON**, nên nhánh NOT MATCHED có thể thử INSERT một hàng trùng khóa và bị UNIQUE từ chối.

Điều này chứng minh:

**MERGE ON nên biểu diễn quan hệ nhận dạng hàng nguồn–đích**. Điều kiện quyết định có UPDATE một trường hay không nên nằm ở **nhánh WHEN MATCHED có điều kiện phù hợp**, thay vì làm thay đổi ý nghĩa “cùng một khách hàng” trong ON.

### 21.3. MERGE có khác ON CONFLICT trong tình huống đồng thời không?

Có. Trong PostgreSQL, **INSERT ... ON CONFLICT DO UPDATE** được thiết kế với cơ chế arbiter duy nhất và bảo đảm nguyên tử INSERT/UPDATE đối với xung đột mục tiêu trong những điều kiện được hỗ trợ.

**MERGE** xác định MATCHED/NOT MATCHED theo một quan hệ ghép và có những khác biệt về cách xử lý đồng thời, nên **không nên giả định mọi bảo đảm của ON CONFLICT tự áp dụng cho MERGE**. Nếu có cạnh tranh ghi, vẫn cần UNIQUE, transaction, cơ chế retry/khóa và hiểu hành vi của phiên bản RDBMS cụ thể.

### 21.4. Nguồn MERGE trùng khóa cũng cần được chuẩn hóa

Nếu một batch nguồn chứa **hai hàng cùng (tenant_id, external_customer_code)**, MERGE không tự chọn hàng đúng. Tùy trạng thái đích và hệ quản trị, có thể gặp lỗi nhiều lần tác động cùng hàng hoặc lỗi UNIQUE trong nhánh INSERT.

**Deduplicate theo quy tắc nghiệp vụ trước MERGE**, giống như trước ON CONFLICT DO UPDATE.

## 22. ON CONFLICT và MERGE: chọn theo yêu cầu

| Khía cạnh | PostgreSQL INSERT ... ON CONFLICT | MERGE |
| --- | --- | --- |
| Mục tiêu chính | INSERT hoặc xử lý xung đột UNIQUE | Đồng bộ theo các nhánh MATCHED/NOT MATCHED |
| Xác định bản ghi trùng | **Unique arbiter** từ cột/biểu thức/constraint | Điều kiện **ON** giữa nguồn và đích |
| Cần UNIQUE cho nhánh update theo xung đột? | Cần arbiter phù hợp | ON không tự tạo UNIQUE; bảng đích vẫn cần bảo vệ theo nghiệp vụ |
| Xử lý nhiều unique index | Conflict target có thể chỉ xử lý một loại xung đột | Các UNIQUE của đích vẫn có thể từ chối thao tác |
| Dữ liệu nguồn trùng khóa | Cần dedup; DO UPDATE có thể lỗi cardinality | Cần dedup; kết quả/lỗi phụ thuộc trường hợp |
| Điều kiện phức tạp | Có thể dùng DO UPDATE ... WHERE | Có nhiều nhánh WHEN, tùy phương ngữ |
| Phù hợp | Nhận bản ghi mới hoặc cập nhật theo khóa nghiệp vụ đã được UNIQUE | Đồng bộ nhiều nhánh theo quy tắc nguồn–đích |

Không có công thức “MERGE luôn tốt hơn UPSERT” hoặc ngược lại. Nếu chỉ cần **INSERT/UPDATE trên một UNIQUE key**, ON CONFLICT của PostgreSQL thường ngắn và rõ. Nếu cần nhiều hành động và điều kiện ghép phức tạp, MERGE có thể thuận tiện nhưng đòi hỏi kiểm soát ý nghĩa khóa và đồng thời cẩn thận.

## 23. Kiểm tra schema: UNIQUE đang nằm ở đâu?

Khi kế thừa một ứng dụng, đừng đoán khóa từ tên cột. Hãy kiểm tra **DDL** hoặc metadata của bảng.

Trong PostgreSQL, có thể xem constraint của bảng tạm bằng catalog:

~~~sql
SELECT
    conname AS constraint_name,
    contype AS constraint_type,
    pg_get_constraintdef(oid) AS constraint_definition
FROM pg_constraint
WHERE conrelid = 'demo_customer_registry'::REGCLASS
ORDER BY conname;
~~~

Mã contype thường gặp:

- **p**: primary key.
- **u**: unique.
- **f**: foreign key.
- **c**: check.

Để xem index có UNIQUE và định nghĩa thực tế:

~~~sql
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = ANY (current_schemas(TRUE))
  AND tablename = 'demo_customer_registry'
ORDER BY indexname;
~~~

Với bảng tạm, schema thực tế có thể có tên dạng **pg_temp_N**, nên cách lọc metadata theo schema cần phù hợp với phiên kết nối. Những truy vấn catalog ở trên giúp nhận diện **các UNIQUE/PRIMARY KEY hiện có**; nếu bảng được đặt trong schema khác hoặc có tên đã qualify, hãy dùng đúng định danh bảng.

### 23.1. EXPLAIN không thay đọc ràng buộc

Trong PostgreSQL, EXPLAIN có thể cho biết chỉ mục arbiter trong kế hoạch INSERT ... ON CONFLICT, nhưng **chỉ khi câu lệnh được phân tích hợp lệ**. Không thể dùng EXPLAIN làm bằng chứng một cột “đáng lẽ duy nhất” nếu schema không có UNIQUE tương ứng.

**EXPLAIN ANALYZE trên INSERT/UPDATE thực sự thực thi DML**, có thể thay đổi dữ liệu; chỉ thử có kiểm soát và dùng transaction ROLLBACK khi cần quan sát trong môi trường thực hành.

## 24. Lưu ý về phạm vi khóa và soft delete

Chọn conflict target thường phải thống nhất với **cách dữ liệu được xem là đang tồn tại**.

### 24.1. Cùng mã sau khi xóa mềm

Giả sử bảng products có:

~~~text
tenant_id  product_code  deleted_at
1          P-100         2026-01-01
~~~

Khi nhập một sản phẩm mới P-100:

- Với **UNIQUE(tenant_id, product_code) toàn phần**, hàng đã xóa mềm vẫn chiếm khóa, nên upsert sẽ nhận diện xung đột với chính hàng đó.
- Với **unique partial WHERE deleted_at IS NULL**, hàng đã xóa mềm không nằm trong tập duy nhất của hàng đang hoạt động; có thể thêm hàng P-100 active mới.

Hai lựa chọn có ý nghĩa khác nhau:

| Quy tắc | Hậu quả |
| --- | --- |
| Không bao giờ tái sử dụng product_code trong tenant | UNIQUE toàn phần phù hợp |
| Cho phép mã xuất hiện lại sau soft-delete | Partial UNIQUE trên hàng active có thể phù hợp |
| Muốn khôi phục bản ghi cũ thay vì tạo mới | Cần quy trình tìm/restore, không chỉ INSERT |

Một bảng có thể có lịch sử nhiều dòng cùng mã khi inactive, nhưng chỉ một active theo index partial. Cần quyết định **các khóa ngoại hoặc liên kết khác trỏ tới bản ghi vật lý nào** nếu cùng mã có nhiều thế hệ.

### 24.2. Thêm status vào UNIQUE không tự tương đương partial unique

Một giải pháp dễ viết:

~~~sql
UNIQUE (tenant_id, product_code, status)
~~~

cấm **hai hàng cùng status** cho một mã, bao gồm cả những hàng lịch sử ở status 'archived'. Nếu nghiệp vụ muốn nhiều bản ghi archived nhưng chỉ một active, UNIQUE có status như một thành phần **không tương đương** partial UNIQUE **WHERE status = 'active'**.

Chọn ràng buộc theo **tập hàng cần phải duy nhất**, không chỉ theo các trường hiện diện trong bảng.

## 25. Khi có nhiều khóa ứng viên, chọn khóa cho từng luồng

Một bảng khách hàng có thể có:

~~~text
customer_id                  PK nội bộ
(tenant_id, external_code)  UNIQUE của đối tác
(tenant_id, email)          UNIQUE của chính sách tài khoản
~~~

Nhưng mỗi luồng có định danh khác nhau:

| Luồng | Khóa nên ưu tiên nhận dạng | Lý do |
| --- | --- | --- |
| Đối tác đồng bộ khách từ API | (tenant_id, external_code) | Đây là định danh ổn định do nguồn phát hành |
| Ứng dụng nội bộ cập nhật bằng customer_id | customer_id | Ứng dụng biết chính xác khóa nội bộ |
| Đăng ký tài khoản bằng email | Theo chính sách email/tài khoản | Có thể cần UNIQUE email chuẩn hóa nhưng phải xét email có đổi được không |
| Nhập batch khách hàng chưa có mã ổn định | **Chưa đủ thông tin để upsert an toàn** | Phải cấp định danh hoặc đưa vào hàng chờ đối soát |

Không nên coi **email**, **số điện thoại**, **tên** hay **ngày sinh** luôn là khóa định danh bền vững. Chúng có thể thay đổi, bị chia sẻ hoặc thiếu giá trị. Nếu nghiệp vụ dùng chúng để nhận dạng, cần cơ chế xác minh và xử lý trường hợp đổi/thu hồi giá trị.

### 25.1. Tránh sử dụng khóa được sinh mới mỗi lần import

Nếu mỗi lần nhận một khách lại sinh customer_id mới rồi INSERT:

~~~text
Lần 1: C-001 → customer_id 100
Lần 2: C-001 → customer_id 315
~~~

thì khóa chính kỹ thuật vẫn duy nhất, nhưng đã có **hai hàng đại diện cùng khách**. UNIQUE trên customer_id không ngăn được lỗi này, vì các customer_id khác nhau.

Giải pháp là có **UNIQUE trên khóa nghiệp vụ thực sự** và dùng khóa đó làm conflict target khi nhập từ nguồn tương ứng.

## 26. Khác biệt giữa các phương ngữ SQL

Khái niệm **khóa trùng và UNIQUE** được dùng rộng rãi, nhưng mỗi hệ quản trị có cách upsert, xử lý NULL và suy luận khóa riêng.

| Hệ quản trị | Cách upsert phổ biến | Cách chọn khóa xung đột |
| --- | --- | --- |
| **PostgreSQL 15+** | INSERT ... ON CONFLICT ... DO UPDATE/DO NOTHING; MERGE | ON CONFLICT suy luận unique index hoặc ON CONSTRAINT; MERGE dùng ON |
| **SQLite hiện đại** | INSERT ... ON CONFLICT ... DO UPDATE/DO NOTHING | Cột/biểu thức/partial unique index hoặc constraint duy nhất phù hợp |
| **MySQL 8.0** | INSERT ... ON DUPLICATE KEY UPDATE | Phản ứng với xung đột **PRIMARY KEY hoặc UNIQUE**; không chọn một conflict target như PostgreSQL |
| **SQL Server** | MERGE hoặc UPDATE rồi INSERT trong transaction | MERGE ON xác định match; UNIQUE index/constraint bảo vệ tính duy nhất |
| **Oracle Database** | MERGE; INSERT/UPDATE theo transaction | MERGE ON xác định match; unique constraint/index vẫn kiểm tra dữ liệu đích |

### 26.1. PostgreSQL: target rõ ràng

~~~sql
INSERT INTO demo_customer_registry
    (tenant_id, external_customer_code, display_name)
VALUES (1, 'C-001', 'An Moi')
ON CONFLICT (tenant_id, external_customer_code)
DO UPDATE
SET display_name = EXCLUDED.display_name;
~~~

Đây là cách chỉ rõ khóa theo **cặp cột**. PostgreSQL cũng hỗ trợ index suy luận từ biểu thức và điều kiện partial phù hợp.

### 26.2. MySQL: không có conflict target tương tự

Trong MySQL:

~~~sql
-- Ví dụ MySQL với bảng customers giả định.
INSERT INTO customers
    (tenant_id, external_customer_code, display_name)
VALUES (1, 'C-001', 'An Moi')
ON DUPLICATE KEY UPDATE
    display_name = 'An Moi';
~~~

MySQL xử lý khi có xung đột **PRIMARY KEY hoặc UNIQUE** của bảng. Không có cú pháp chọn chính xác **(tenant_id, external_customer_code)** bằng cùng hình thức **ON CONFLICT (...)** như PostgreSQL.

Nếu bảng có **nhiều UNIQUE** và hàng INSERT vi phạm nhiều khóa khác nhau, việc xác định hàng nào được UPDATE có thể gây kết quả ngoài mong muốn. MySQL cảnh báo cần thận trọng khi dùng ON DUPLICATE KEY UPDATE trên bảng có nhiều unique indexes.

**Không tự port ON CONFLICT (tenant_id, code)** thành ON DUPLICATE KEY UPDATE rồi giả định chỉ UNIQUE của hai cột đó sẽ là cơ chế nhận dạng. Cần thiết kế schema và thử xung đột trên tất cả các UNIQUE liên quan.

MySQL cũng thường cho phép nhiều giá trị NULL trong UNIQUE index, nhưng chi tiết so sánh chuỗi có thể phụ thuộc collation đã chọn.

### 26.3. SQLite: gần PostgreSQL nhưng không đồng nhất hoàn toàn

SQLite hỗ trợ UPSERT:

~~~sql
-- Bảng customers là giả định trên SQLite.
INSERT INTO customers
    (tenant_id, external_customer_code, display_name)
VALUES (1, 'C-001', 'An Moi')
ON CONFLICT(tenant_id, external_customer_code)
DO UPDATE SET display_name = excluded.display_name;
~~~

Nhìn gần giống PostgreSQL, nhưng cú pháp xử lý nhiều ON CONFLICT, biểu thức, partial index, collation và những hạn chế cụ thể phải theo **phiên bản SQLite**.

Khi dùng **INSERT ... SELECT ... ON CONFLICT**, SQLite có một điểm mơ hồ phân tích cú pháp trong một số trường hợp. Một mẫu có thể cần **WHERE TRUE** ở cuối SELECT để phân biệt phần ON của JOIN với ON CONFLICT:

~~~sql
INSERT INTO customers
    (tenant_id, external_customer_code, display_name)
SELECT tenant_id, external_customer_code, display_name
FROM incoming_customers
WHERE TRUE
ON CONFLICT(tenant_id, external_customer_code)
DO UPDATE SET display_name = excluded.display_name;
~~~

Đây là chi tiết SQLite, không phải quy tắc bắt buộc của PostgreSQL. SQLite cũng có cách xử lý NULL/UNIQUE và collation cần kiểm chứng theo schema thực tế.

### 26.4. SQL Server: UNIQUE và MERGE ON là hai phần riêng

~~~sql
-- Minh họa SQL Server với bảng dbo.customers và nguồn dbo.incoming.
MERGE dbo.customers AS t
USING dbo.incoming AS s
ON t.tenant_id = s.tenant_id
   AND t.external_customer_code = s.external_customer_code
WHEN MATCHED THEN
    UPDATE SET t.display_name = s.display_name
WHEN NOT MATCHED BY TARGET THEN
    INSERT (tenant_id, external_customer_code, display_name)
    VALUES (s.tenant_id, s.external_customer_code, s.display_name);
~~~

Điều kiện ON xác định bản ghi khớp. **UNIQUE(tenant_id, external_customer_code)** trên bảng đích nên được thiết kế riêng để cưỡng chế tính duy nhất. SQL Server có những vấn đề concurrency và hành vi MERGE cần đánh giá kỹ; tùy hệ thống, cách UPDATE rồi INSERT với khóa/cô lập phù hợp có thể dễ kiểm soát hơn.

**Khác biệt về NULL đáng chú ý:** SQL Server thường có cách thực thi UNIQUE với NULL khác PostgreSQL mặc định; ví dụ UNIQUE đơn cột có thể chỉ cho một NULL theo cơ chế SQL Server. Không port giả định “UNIQUE luôn cho nhiều NULL” qua mọi hệ.

### 26.5. Oracle: MERGE và ràng buộc độc lập

~~~sql
-- Minh họa Oracle với bảng đích/nguồn giả định.
MERGE INTO customers t
USING incoming_customers s
ON (t.tenant_id = s.tenant_id
    AND t.external_customer_code = s.external_customer_code)
WHEN MATCHED THEN
    UPDATE SET t.display_name = s.display_name
WHEN NOT MATCHED THEN
    INSERT (tenant_id, external_customer_code, display_name)
    VALUES (s.tenant_id, s.external_customer_code, s.display_name);
~~~

MERGE ON biểu diễn điều kiện khớp; các UNIQUE/PRIMARY KEY ở đích vẫn bảo vệ dữ liệu. Nguồn trùng khóa có thể làm MERGE thất bại hoặc tác động không mong muốn, nên cần chuẩn hóa nguồn trước. Cú pháp và khả năng MERGE phụ thuộc phiên bản Oracle.

**Kết luận khi chuyển hệ:** trước tiên xác định **mô hình danh tính và ràng buộc UNIQUE tương đương**, sau đó mới viết lại cú pháp upsert. Không chuyển câu SQL bằng cách thay mỗi tên từ khóa.

## 27. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ có PRIMARY KEY(customer_id) nhưng import theo external_code | Mỗi lần import dễ tạo customer_id mới và khách trùng | UNIQUE trên khóa nghiệp vụ, upsert theo khóa đó |
| Chọn UNIQUE(external_code) toàn hệ đa tenant | Hai tenant không thể dùng chung mã | Dùng UNIQUE(tenant_id, external_code) |
| Viết ON CONFLICT(external_code) khi chỉ có UNIQUE(tenant_id, external_code) | Không tìm được unique arbiter | Nêu đủ khóa ghép |
| Coi INDEX thường như UNIQUE | Không cưỡng chế tính duy nhất | Tạo đúng UNIQUE index/constraint |
| Nghĩ DO NOTHING không target chỉ bỏ xung đột mã đối tác | Có thể bỏ cả hàng vì UNIQUE khác, chẳng hạn email | Chỉ rõ target khi cần kiểm soát loại xung đột |
| Có nhiều UNIQUE và tưởng ON CONFLICT xử lý mọi vi phạm | Xung đột UNIQUE ngoài target vẫn lỗi | Kiểm tra tất cả constraint, xử lý theo nghiệp vụ |
| Trộn email làm khóa định danh bất biến | Email thay đổi/chia sẻ gây cập nhật sai | Chọn định danh ổn định hoặc quy trình xác thực |
| Tin UNIQUE mặc định chặn nhiều NULL trên PostgreSQL | Nhiều hàng NULL vẫn tồn tại | NOT NULL hoặc NULLS NOT DISTINCT nếu đúng nghiệp vụ |
| Dùng NULLS NOT DISTINCT để gộp mọi khách thiếu mã | Nhiều khách bị nhận nhầm là một | Không dùng NULL như danh tính nếu chưa xác định |
| Quên chuẩn hóa mã trước UNIQUE | 'C-001' và ' c-001 ' có thể cùng tồn tại | Chuẩn hóa/collation/unique expression index |
| Dùng ON CONSTRAINT với tên partial unique index | Index không phải một constraint được đặt tên theo cách đó | Suy luận bằng target cột + predicate |
| Quên predicate khi upsert theo partial index | Không tìm được arbiter hoặc dùng sai quy tắc | Nêu WHERE trong conflict target phù hợp |
| Coi UNIQUE partial bảo đảm phải có một active | UNIQUE chỉ bảo đảm tối đa một | Thêm kiểm soát tồn tại nếu cần |
| Dùng DEFERRABLE UNIQUE làm arbiter | PostgreSQL không hỗ trợ theo cách đó | Thiết kế unique không deferrable hoặc quy trình khác |
| Một INSERT nguồn có hai hàng trùng khóa | DO UPDATE có thể lỗi cardinality | Deduplicate/kiểm soát batch trước |
| ROW_NUMBER phá hòa tùy ý để né trùng | Chọn nhầm phiên bản bản ghi | Dùng thứ tự ưu tiên nghiệp vụ |
| SELECT NOT EXISTS rồi INSERT không có UNIQUE | Race condition với writer khác | UNIQUE + ON CONFLICT/transaction phù hợp |
| Tin UNIQUE tự xác định bản cập nhật mới nhất | Batch cũ có thể ghi đè batch mới | source_version/effective_at và điều kiện UPDATE |
| Đưa điều kiện thay đổi dữ liệu vào MERGE ON | MATCHED thành NOT MATCHED rồi vi phạm UNIQUE | ON chỉ nêu danh tính, lọc trong nhánh phù hợp |
| Nghĩ MERGE ON thay thế UNIQUE | Bảng đích vẫn có thể lưu bản ghi trùng | Cưỡng chế UNIQUE trên khóa nghiệp vụ |
| Tạo UNIQUE mới trên dữ liệu cũ chưa xử lý trùng | Migration thất bại | Kiểm tra/gộp dữ liệu theo chính sách trước |
| Dùng IS DISTINCT FROM sau DO UPDATE SET rồi tưởng hàng được INSERT | Hàng xung đột không được INSERT khi WHERE UPDATE FALSE | Hiểu rõ thứ tự quyết định nhánh |

## 28. Bài tập thực hành

Sử dụng bảng tạm **demo_customer_registry** ở phần 3; khi cần thay dữ liệu hãy dùng **BEGIN ... ROLLBACK** hoặc tạo bảng riêng để bảo toàn ví dụ gốc.

1. Liệt kê tất cả PRIMARY KEY và UNIQUE của demo_customer_registry. Khóa chính kỹ thuật khác khóa nghiệp vụ thế nào?
2. Giải thích vì sao **(1, C-001)** và **(2, C-001)** được phép cùng tồn tại.
3. Viết INSERT cho **(1, C-001)** bằng ON CONFLICT (tenant_id, external_customer_code) để cập nhật display_name.
4. Viết INSERT cho **(2, C-002)** bằng cùng conflict target. Nó INSERT hay UPDATE? Vì sao?
5. Thử mô tả lỗi khi dùng ON CONFLICT (external_customer_code) trên bảng mẫu. PostgreSQL thiếu loại ràng buộc nào?
6. Viết lại bài 3 bằng **ON CONFLICT ON CONSTRAINT uq_demo_customer_tenant_external**.
7. So sánh **ON CONFLICT (tenant_id, external_customer_code) DO NOTHING** với **ON CONFLICT DO NOTHING** trong một tình huống email trùng nhưng code không trùng.
8. Viết một hàng có code mới **C-099** nhưng dùng email an@example.test của tenant 1. Dự đoán ràng buộc nào sẽ từ chối.
9. Viết một hàng trùng code C-002 và update email thành an@example.test. Giải thích vì sao UPDATE sau xung đột vẫn có thể lỗi.
10. Trong transaction thực hành, thêm khách C-004 với contact_email NULL vào tenant 1. Có được phép không? Liên hệ với UNIQUE mặc định.
11. Tạo bảng có **UNIQUE NULLS NOT DISTINCT (tenant_id, external_ref)** trên PostgreSQL 15+. Upsert hai hàng cùng tenant có external_ref NULL; quan sát kết quả.
12. Giải thích vì sao một khóa nghiệp vụ **không nên cho NULL** nếu NULL chỉ có nghĩa “chưa biết khách nào”.
13. Tạo **unique expression index trên LOWER(email)**, sau đó dùng ON CONFLICT ((LOWER(email))) để cập nhật contact_name.
14. Giả sử mã nguồn ' c-001 ' và 'C-001' phải được coi là một. Hãy đề xuất quy tắc chuẩn hóa và vị trí cưỡng chế UNIQUE.
15. Tạo partial unique index **WHERE is_active**. Có được phép lưu nhiều hàng inactive cùng (tenant_id, customer_code) không?
16. Upsert theo partial unique index bằng **ON CONFLICT (tenant_id, customer_code) WHERE is_active DO UPDATE**. Phân biệt WHERE này với WHERE sau SET.
17. Giải thích vì sao UNIQUE(tenant_id, code, status) không tương đương UNIQUE(tenant_id, code) WHERE status = 'active'.
18. Tạo hai hàng nguồn cùng **(1, C-050)** trong một INSERT ... ON CONFLICT DO UPDATE. Dự đoán lỗi có thể xảy ra.
19. Dùng ROW_NUMBER chọn hàng cuối cho mỗi (tenant_id, external_code), rồi chỉ upsert những hàng có rn = 1. Vì sao cần chính sách rõ về “hàng cuối”?
20. Mô tả hai transaction cùng SELECT thấy C-900 chưa có rồi INSERT. Ràng buộc nào bảo vệ khỏi bản ghi trùng?
21. Viết DO UPDATE ... WHERE IS DISTINCT FROM để tránh cập nhật khi dữ liệu không đổi. Khi điều kiện WHERE là FALSE, có thực hiện INSERT không?
22. Viết MERGE theo khóa ghép trên bảng giả định. Điều gì xảy ra nếu thêm điều kiện **display_name bằng nhau** vào ON trong khi đang muốn đổi tên?
23. Dùng một bảng chưa có UNIQUE chứa hai hàng trùng (tenant_id, external_code), viết GROUP BY/HAVING để tìm nhóm trùng trước khi migration.
24. Đề xuất chính sách xử lý các hàng trùng nếu một trong hai đang được đơn hàng khác tham chiếu.
25. So sánh việc dùng ON CONFLICT của PostgreSQL với ON DUPLICATE KEY UPDATE của MySQL khi bảng có hai UNIQUE khác nhau.
26. Trên SQL Server, giải thích vì sao MERGE ON cần biểu diễn khóa nghiệp vụ nhưng vẫn cần UNIQUE ở bảng đích.
27. Với nghiệp vụ soft delete, mô tả trường hợp nên dùng UNIQUE toàn phần và trường hợp nên dùng partial unique index.
28. Nếu hai batch cập nhật cùng khách nhưng source_version khác nhau, hãy thiết kế quy tắc không để dữ liệu cũ ghi đè dữ liệu mới.

### Câu hỏi tự kiểm tra

**Câu 1.** Một bảng đã có PRIMARY KEY(customer_id) thì upsert theo (tenant_id, external_customer_code) tự động xử lý trùng mã nghiệp vụ không?

**Đáp án:** **Không.** Cần một unique arbiter tương ứng với khóa nghiệp vụ, ví dụ UNIQUE(tenant_id, external_customer_code).

**Câu 2.** UNIQUE(tenant_id, external_code) có bắt mọi external_code phải khác nhau trên toàn bảng không?

**Đáp án:** **Không.** Chỉ tổ hợp hai cột phải duy nhất; các tenant khác nhau có thể dùng cùng external_code.

**Câu 3.** ON CONFLICT DO UPDATE xử lý được lỗi FOREIGN KEY hoặc CHECK không?

**Đáp án:** **Không.** Đó không phải những ràng buộc làm arbiter cho upsert. Vi phạm chúng vẫn có thể khiến lệnh lỗi.

**Câu 4.** Nếu dùng ON CONFLICT (tenant_id, code) mà hàng mới không trùng code nhưng trùng một UNIQUE email, hệ thống tự UPDATE hàng trùng email không?

**Đáp án:** **Không.** Xung đột ở unique email nằm ngoài conflict target được chọn, nên câu lệnh có thể lỗi.

**Câu 5.** PostgreSQL UNIQUE(email) mặc định có cho phép hai hàng email NULL không?

**Đáp án:** **Có**, nếu cột được phép NULL. PostgreSQL 15+ có UNIQUE NULLS NOT DISTINCT khi nghiệp vụ muốn NULL cũng bị coi là trùng.

**Câu 6.** Có thể dùng ON CONSTRAINT với tên một partial unique index được tạo bằng CREATE UNIQUE INDEX không?

**Đáp án:** **Không nên giả định được.** ON CONSTRAINT tham chiếu constraint, còn partial unique index cần conflict target phù hợp để suy luận.

**Câu 7.** Tại sao hai hàng nguồn có cùng khóa trong một lệnh ON CONFLICT DO UPDATE là vấn đề?

**Đáp án:** PostgreSQL không cho một lệnh DO UPDATE tác động cùng một hàng đích nhiều lần; cần xử lý trùng trong batch trước khi upsert.

**Câu 8.** MERGE ON t.code = s.code có tự tạo UNIQUE(code) ở đích không?

**Đáp án:** **Không.** ON chỉ định cách ghép nguồn–đích; tính duy nhất phải được bảo vệ riêng bằng UNIQUE/PRIMARY KEY phù hợp.

**Câu 9.** UNIQUE có bảo đảm batch mới nhất luôn thắng khi nhiều worker cùng cập nhật không?

**Đáp án:** **Không.** Nó giữ một hàng trên khóa, nhưng cần chính sách version/thời điểm và điều kiện UPDATE để quyết định nội dung nào được chấp nhận.

## 29. Ghi nhớ cốt lõi

**Upsert chỉ đúng khi khóa dùng để xác định xung đột thật sự đại diện cho danh tính nghiệp vụ.** Một PRIMARY KEY kỹ thuật không tự giải quyết việc đồng bộ từ mã ngoài; một UNIQUE trên một cột không đủ nếu danh tính thực tế phụ thuộc nhiều cột; và một điều kiện MERGE ON không tự tạo ra tính duy nhất trong bảng đích.

Trong PostgreSQL, **INSERT ... ON CONFLICT DO UPDATE** dựa trên **unique arbiter** phù hợp. Có thể chỉ rõ cột, biểu thức, predicate của partial unique index hoặc tên constraint khi hỗ trợ. **Mọi UNIQUE khác của bảng đích vẫn có hiệu lực**, nên xử lý trùng theo một khóa không có nghĩa mọi kiểu trùng đều được tự động giải quyết.

Hãy luôn xem xét **NULL**, chuẩn hóa mã, phạm vi tenant, lịch sử soft-delete, dữ liệu nguồn có duplicate và tình huống nhiều transaction cùng ghi. Với dữ liệu nhập theo batch, kiểm soát **một hàng nguồn trên mỗi khóa** trước khi gửi UPSERT hoặc MERGE. Với hệ nhiều writer, đặt **UNIQUE tại cơ sở dữ liệu** thay vì chỉ kiểm tra tồn tại ở ứng dụng.

Quy tắc ngắn gọn để nhớ:

~~~text
Định nghĩa danh tính nghiệp vụ
            ↓
Chọn khóa đơn hoặc khóa ghép
            ↓
Ràng buộc UNIQUE / PRIMARY KEY / unique index phù hợp
            ↓
Lọc, chuẩn hóa và xử lý trùng trong nguồn
            ↓
UPSERT / MERGE theo đúng khóa
            ↓
Kiểm tra những UNIQUE khác, NULL, concurrency và version
~~~

**UNIQUE là hàng rào thực thi tính duy nhất; conflict target là cách câu lệnh chọn hàng rào dùng để xử lý xung đột; còn nghiệp vụ quyết định hàng rào ấy phải đại diện cho điều gì.**
