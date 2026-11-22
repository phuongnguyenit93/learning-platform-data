# Thực thi một câu lệnh, nhiều câu lệnh và tệp SQL

Khi thực hành SQL, bạn có thể gửi một câu lệnh riêng lẻ, chạy liên tiếp nhiều câu lệnh trong cửa sổ truy vấn, hoặc lưu cả chuỗi thao tác vào tệp `.sql` để thực thi lại. Cả ba cách đều dùng SQL, nhưng khác nhau ở **đơn vị được gửi đi, cách quản lý thứ tự thực thi, cách xem kết quả và cách xử lý khi có lỗi**.

Bài này sử dụng SQL cơ bản có thể áp dụng trên PostgreSQL, MySQL và SQLite. Các lệnh của từng chương trình khách (client) được ghi rõ để tránh nhầm chúng với cú pháp SQL của máy chủ cơ sở dữ liệu.

## 1. Hiểu đường đi của một câu lệnh SQL

Trong một môi trường thực hành thông thường có ba thành phần:

1. **Trình khách SQL**: cửa sổ Query Editor trong DBeaver, pgAdmin, MySQL Workbench, DB Browser for SQLite; hoặc chương trình dòng lệnh như `psql`, `mysql`, `sqlite3`.
2. **Kết nối và ngữ cảnh**: máy chủ/tệp cơ sở dữ liệu đang kết nối, tài khoản, quyền, database và schema hiện hành (nếu hệ quản trị hỗ trợ schema).
3. **Bộ máy SQL**: nhận câu lệnh, kiểm tra cú pháp/quyền, thực thi và trả kết quả hoặc lỗi về trình khách.

Ví dụ, với câu lệnh:

~~~sql
SELECT 10 + 5 AS ket_qua;
~~~

Trình khách gửi câu lệnh tới bộ máy SQL và hiển thị một hàng có cột `ket_qua` với giá trị `15`. Còn với `INSERT` hoặc `UPDATE`, thông tin dễ thấy nhất thường là số hàng bị ảnh hưởng; với `CREATE TABLE`, chương trình thường hiển thị thông báo thành công.

**Trước khi nhấn Execute, hãy nhìn lại tên kết nối và database đang chọn.** Một câu `UPDATE` hợp lệ có thể thay đổi dữ liệu thật nếu được chạy nhầm môi trường. Các ví dụ bên dưới nên thực hiện trong database thử nghiệm, với tài khoản có quyền phù hợp.

### Khác nhau giữa SQL và lệnh của trình khách

Các câu như `SELECT ...;`, `INSERT ...;` là SQL. Nhưng `\i` của `psql`, `SOURCE` của MySQL CLI và `.read` của SQLite CLI là **lệnh điều khiển của trình khách**, có nhiệm vụ đọc tệp rồi gửi SQL đi. Chúng không chạy trực tiếp trong mọi công cụ SQL.

Ví dụ cách xác nhận ngữ cảnh, tùy hệ quản trị:

| Hệ quản trị | Câu lệnh kiểm tra ngữ cảnh |
| --- | --- |
| PostgreSQL | `SELECT current_database(), current_schema();` |
| MySQL | `SELECT DATABASE();` |
| SQLite | `PRAGMA database_list;` (danh sách database/tệp đang gắn) |

Một database có thể đã tồn tại sẵn do lớp học hoặc người quản trị cấp. Các ví dụ kết nối bên dưới giả định database PostgreSQL/MySQL tên `sql_lab` và tài khoản `learner` đã được chuẩn bị; bạn thay các giá trị này bằng môi trường thực tế của mình.

## 2. Thực thi **một câu lệnh**

Một câu lệnh là một đơn vị SQL hoàn chỉnh. Với phần lớn câu lệnh cơ bản, dấu chấm phẩy `;` đánh dấu điểm kết thúc:

~~~sql
SELECT 'SQL da san sang' AS thong_bao;
~~~

Trong giao diện đồ họa, quy trình phổ biến là mở kết nối, mở SQL Editor, đặt con trỏ trong câu lệnh (hoặc bôi đen đúng câu lệnh) rồi chọn chức năng **Execute statement / Run current statement**. Tên nút và phím tắt khác nhau giữa các phiên bản công cụ; hãy kiểm tra nhãn chức năng trong ứng dụng đang dùng.

Ở cửa sổ lệnh PostgreSQL, chẳng hạn:

~~~text
psql -h localhost -p 5432 -U learner -d sql_lab
~~~

Sau khi kết nối thành công, nhập:

~~~sql
SELECT 2 * 3 AS tich;
~~~

Kết quả mong đợi là một hàng có `tich = 6`. Trong `psql`, nếu chưa kết thúc câu lệnh bằng `;`, chương trình thường tiếp tục chờ phần còn lại của câu lệnh. Một số SQL Editor đồ họa vẫn chạy được câu lệnh đơn khi không có dấu `;`, nhưng thêm dấu này giúp mã dễ chuyển sang chế độ chạy nhiều câu/tệp.

**Một lần thực thi câu lệnh không nhất thiết tương ứng một lần thay đổi dữ liệu.** `SELECT` chủ yếu đọc dữ liệu; `INSERT`, `UPDATE`, `DELETE` có thể thay đổi một hoặc nhiều hàng; lệnh DDL như `CREATE TABLE` thay đổi cấu trúc. Sau khi chạy, quan sát cả bảng kết quả lẫn vùng thông báo/ảnh hưởng hàng.

## 3. Thực thi **nhiều câu lệnh**

Một cửa sổ soạn thảo có thể chứa nhiều câu lệnh, phân tách bằng dấu `;`:

~~~sql
SELECT 1 AS buoc_thu_nhat;
SELECT 2 AS buoc_thu_hai;
SELECT 1 + 2 AS tong;
~~~

Nếu chọn **Execute script / Run all / Execute all statements**, trình khách sẽ xử lý cả ba câu theo thứ tự xuất hiện. Tùy công cụ, kết quả có thể hiện ở nhiều tab, nhiều bảng, hoặc một bảng cuối kèm nhật ký thực thi. Nếu chọn **Execute current statement**, thường chỉ câu đang đặt con trỏ được chạy. Đây là khác biệt quan trọng khi kiểm tra một đoạn SQL dài.

Đối với thao tác có quan hệ phụ thuộc, thứ tự phải hợp lý:

~~~sql
CREATE TABLE execution_lab (
    id INTEGER PRIMARY KEY,
    task_name VARCHAR(80) NOT NULL,
    task_status VARCHAR(12) NOT NULL
);

INSERT INTO execution_lab (id, task_name, task_status)
VALUES
    (101, 'Doc du lieu', 'TODO'),
    (102, 'Kiem tra ket qua', 'TODO');

SELECT id, task_name, task_status
FROM execution_lab
ORDER BY id;

UPDATE execution_lab
SET task_status = 'DONE'
WHERE id = 101;

SELECT id, task_name, task_status
FROM execution_lab
ORDER BY id;
~~~

Khi chạy **một lần trên database thử nghiệm chưa có bảng `execution_lab`**, chuỗi trên tạo bảng, thêm hai hàng, hiển thị trạng thái ban đầu, đổi trạng thái của hàng `101` rồi hiển thị trạng thái cuối. Nếu chọn chạy riêng câu `INSERT` trước khi tạo bảng, bạn sẽ nhận lỗi bảng chưa tồn tại.

Không chạy lại nguyên chuỗi trên một cách vô thức: `CREATE TABLE` sẽ báo bảng đã tồn tại; `INSERT` với cùng ID có thể báo trùng khóa chính. Đây là tính chất của nội dung script, không phải lỗi của nút Execute. Phần thực hành cuối bài hướng dẫn cách chuẩn bị một lần chạy mới.

### Dấu `;` có nghĩa gì?

- Dấu `;` ở **ngoài chuỗi ký tự và chú thích** là dấu kết thúc câu lệnh thông thường.
- Dấu `;` trong chuỗi như `SELECT 'a;b' AS text_value;` không tách câu lệnh ở giữa chuỗi.
- Một vài trình khách/hệ quản trị có quy tắc batch hoặc khối thủ tục riêng. Ví dụ `GO` trong công cụ SQL Server là dấu phân cách batch do công cụ xử lý; `DELIMITER` trong MySQL CLI là lệnh đổi dấu kết thúc khi viết stored procedure/trigger. Không đưa chúng vào tệp SQL dùng chung cho mọi hệ quản trị.

## 4. Lưu chuỗi thao tác thành **tệp SQL**

Tệp `.sql` là một tệp văn bản chứa SQL; bản thân phần mở rộng không khiến tệp tự chạy. Bạn cần dùng trình khách để mở và thực thi nó.

Ví dụ, tạo tệp `lab_execution.sql` bằng một trình soạn thảo văn bản, lưu ở UTF-8, với nội dung:

~~~sql
-- lab_execution.sql
-- Chi chay trong database thuc hanh va tren bang execution_lab.

CREATE TABLE execution_lab (
    id INTEGER PRIMARY KEY,
    task_name VARCHAR(80) NOT NULL,
    task_status VARCHAR(12) NOT NULL
);

INSERT INTO execution_lab (id, task_name, task_status)
VALUES
    (101, 'Doc du lieu', 'TODO'),
    (102, 'Kiem tra ket qua', 'TODO');

-- Xem du lieu truoc khi cap nhat.
SELECT id, task_name, task_status
FROM execution_lab
ORDER BY id;

UPDATE execution_lab
SET task_status = 'DONE'
WHERE id = 101;

-- Xem du lieu sau khi cap nhat.
SELECT id, task_name, task_status
FROM execution_lab
ORDER BY id;
~~~

Cú pháp `--` tạo chú thích đến hết dòng; `/* ... */` tạo chú thích khối. Các chú thích giúp người khác hiểu mục đích, điều kiện chạy và kết quả dự kiến.

Một tệp SQL tốt nên có tên mô tả hành động, thứ tự câu lệnh rõ ràng, dấu `;` đầy đủ, chú thích tại các bước quan trọng và không chứa mật khẩu. Trước khi chạy, kiểm tra đường dẫn tệp, database đích và việc script có được thiết kế để chạy lặp lại hay chỉ chạy một lần.

### Cách chạy tệp theo từng công cụ

| Công cụ | Cách chạy `lab_execution.sql` |
| --- | --- |
| GUI như DBeaver, pgAdmin, MySQL Workbench | Mở tệp trong SQL Editor, kiểm tra kết nối/database rồi chọn chức năng thực thi **toàn bộ script**; cách mở, phím tắt và hỗ trợ nhiều kết quả tùy công cụ. |
| PostgreSQL `psql` đang mở | `\i lab_execution.sql` |
| PostgreSQL từ terminal | `psql -X -v ON_ERROR_STOP=1 -h localhost -U learner -d sql_lab -f lab_execution.sql` |
| MySQL CLI đang mở | `SOURCE lab_execution.sql;` |
| SQLite CLI đang mở | `.read lab_execution.sql` |

Ví dụ với SQLite, có thể mở một tệp database thực hành (nếu chưa tồn tại, SQLite thường tạo tệp mới):

~~~text
sqlite3 practice.db
~~~

Sau đó, tại dấu nhắc `sqlite>`:

~~~text
.read lab_execution.sql
~~~

Lưu ý: `.read` **không** có dấu chấm phẩy kết thúc, vì đó là lệnh của SQLite CLI. Lệnh `\i` của `psql` cũng là lệnh meta của trình khách, không phải một câu SQL. `SOURCE` là lệnh của MySQL CLI; trong SQL Editor khác cần dùng chức năng mở/chạy tệp tương ứng.

Trong terminal dùng Bash hoặc Windows Command Prompt, cũng có thể chuyển nội dung tệp qua stdin, chẳng hạn `mysql -u learner -p sql_lab < lab_execution.sql` hoặc `sqlite3 practice.db < lab_execution.sql`. Cú pháp chuyển hướng `<` này **không được PowerShell 5.1 hỗ trợ theo cùng cách**; khi dùng PowerShell, có thể chọn lệnh đọc tệp ngay bên trong trình khách như trên.

**Đường dẫn là đường dẫn trên máy chạy trình khách.** Nếu terminal đang ở thư mục khác thư mục chứa tệp, hãy chuyển vào thư mục đúng hoặc chỉ rõ đường dẫn đầy đủ. Máy chủ database không tự đọc tệp `.sql` trên máy của bạn chỉ vì bạn nhập tên tệp.

### Vì sao chạy bằng `psql -f` thường có thêm `ON_ERROR_STOP`?

Với `psql`, tùy chọn `-v ON_ERROR_STOP=1` yêu cầu dừng xử lý script khi một câu lệnh phát sinh lỗi. Nó giúp nhận biết lần chạy thất bại trong terminal hoặc công cụ tự động. Tuy nhiên, **dừng ở lỗi không có nghĩa là tự hoàn tác các câu đã thành công trước đó**; điều này còn phụ thuộc chế độ transaction. `-X` tránh nạp file cấu hình `psqlrc` của người dùng, giúp ví dụ có hành vi nhất quán hơn.

## 5. Nhiều câu lệnh có tự động thành một transaction không?

**Không mặc định.** Một tệp chứa 10 câu lệnh là 10 câu lệnh được trình khách xử lý theo cách mà công cụ và kết nối cấu hình. Với chế độ autocommit đang bật, các thay đổi thành công có thể đã được commit trước khi câu tiếp theo gặp lỗi. Khi đó sửa lỗi rồi chạy lại từ đầu dễ gây trùng dữ liệu hoặc lỗi tạo bảng.

Nếu muốn nhiều thao tác dữ liệu cùng thành công hoặc cùng bị hủy, hãy tìm hiểu transaction:

~~~sql
BEGIN;

UPDATE execution_lab
SET task_status = 'DONE'
WHERE id = 101;

UPDATE execution_lab
SET task_status = 'DONE'
WHERE id = 102;

COMMIT;
~~~

Ví dụ trên dùng cú pháp được PostgreSQL và SQLite chấp nhận; với MySQL, có thể mở transaction bằng `START TRANSACTION;`. `COMMIT` xác nhận thay đổi; `ROLLBACK` hủy những thay đổi chưa commit trong transaction khi hệ quản trị và loại câu lệnh cho phép. Không nhập `COMMIT` nếu bạn đang muốn kiểm tra và hoàn tác bằng `ROLLBACK`.

Ví dụ, nếu đang thao tác thủ công:

~~~sql
BEGIN;
UPDATE execution_lab
SET task_status = 'TODO'
WHERE id = 101;

SELECT id, task_status
FROM execution_lab
WHERE id = 101;

ROLLBACK;
~~~

Sau `ROLLBACK`, bản cập nhật thành `TODO` trong ví dụ sẽ không còn được lưu. Nếu bạn chạy script khác trong lúc transaction còn mở, kết quả có thể khác kỳ vọng. Hãy kiểm tra chế độ autocommit và transaction của công cụ.

**Giới hạn cần nhớ:** không phải mọi hệ quản trị và mọi loại câu SQL đều có thể rollback như nhau. Chẳng hạn, nhiều lệnh DDL trên MySQL có thể làm implicit commit; PostgreSQL hỗ trợ transaction cho phần lớn DDL nhưng có lệnh không được chạy trong transaction. SQLite, PostgreSQL và MySQL cũng khác nhau về engine, isolation và lỗi giao dịch. Do đó không mặc định rằng bọc mọi tệp SQL bằng `BEGIN`/`COMMIT` sẽ luôn đảm bảo tính nguyên tử.

Với PostgreSQL, nếu script không tự quản lý transaction và chỉ có các lệnh được phép chạy trong transaction, có thể dùng:

~~~text
psql -X -v ON_ERROR_STOP=1 --single-transaction -U learner -d sql_lab -f lab_execution.sql
~~~

Tùy chọn `--single-transaction` yêu cầu `psql` bọc quá trình chạy tệp trong một transaction. Không áp dụng tùy chọn này một cách máy móc cho tệp có lệnh không được phép trong transaction, hoặc tệp đã tự đặt ranh giới transaction.

## 6. Đọc đúng kết quả và tìm lỗi khi thực thi

Khi chạy một câu hay cả script, nên quan sát bốn loại thông tin: câu nào đang được chạy, kết quả truy vấn, số hàng bị ảnh hưởng và thông báo lỗi/transaction. Một script có thể hiển thị kết quả `SELECT` hợp lý nhưng vẫn thất bại ở câu lệnh tiếp theo.

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/xử lý |
| --- | --- | --- |
| Chỉ thấy kết quả của một câu dù editor có nhiều câu | Đang chọn **Run current statement**, hoặc công cụ chỉ hiển thị một result set | Chọn chức năng chạy script và xem các tab/log kết quả |
| Công cụ tiếp tục chờ, chưa thực thi | Thiếu dấu `;`, dấu nháy hoặc dấu ngoặc chưa đóng | Kiểm tra điểm kết thúc của câu lệnh |
| `Table does not exist` hoặc tên bảng không tìm thấy | Chưa chạy `CREATE TABLE`, nhầm database/schema hoặc viết sai tên | Xem lại kết nối, thứ tự script và tên bảng |
| `Already exists` / lỗi trùng khóa chính | Chạy lại script tạo bảng/chèn hàng với ID cố định | Xác định script có được phép chạy lại không; dọn đúng dữ liệu thử nghiệm trước khi chạy lại |
| Lỗi cú pháp dù SQL có vẻ đúng | Dùng cú pháp thuộc hệ quản trị khác hoặc đưa meta-command vào SQL Editor | Kiểm tra dialect và xem lệnh thuộc SQL hay thuộc client |
| Một số câu thành công, câu sau thất bại | Script không chạy trong một transaction chung hoặc client không dừng ở lỗi | Xem log theo từng câu và kiểm tra phần dữ liệu đã commit |
| Chạy tệp báo không tìm thấy | Đường dẫn tương đối tính theo thư mục làm việc của client hoặc file chưa lưu | Kiểm tra thư mục hiện hành và đường dẫn đầy đủ |
| Chữ tiếng Việt hiển thị sai | Encoding tệp, client hoặc kết nối chưa thống nhất | Lưu UTF-8 và kiểm tra cấu hình mã hóa của công cụ/database |

Với `UPDATE` và `DELETE`, luôn chú ý `WHERE` trước khi chạy. Ví dụ:

~~~sql
-- Chi cap nhat mot dong trong bang thuc hanh.
UPDATE execution_lab
SET task_status = 'DONE'
WHERE id = 101;
~~~

Bỏ `WHERE` sẽ cập nhật **tất cả** hàng trong bảng. Trong môi trường có dữ liệu quan trọng, hãy thử `SELECT ... WHERE ...` để xác nhận đúng tập hàng trước khi thay đổi.

## 7. Bài thực hành có thể tự kiểm chứng

Mục tiêu là thấy rõ ba chế độ: chạy một câu, chạy nhiều câu và chạy tệp.

### Bước 1 — Chạy riêng một câu

Kết nối tới database thực hành và chạy:

~~~sql
SELECT 'Ket noi OK' AS trang_thai;
~~~

Kết quả mong đợi: một hàng chứa `Ket noi OK`. Nếu không chạy được, hãy giải quyết kết nối trước khi chuyển sang bài nhiều câu.

### Bước 2 — Chạy hai câu trong editor

Nhập:

~~~sql
SELECT 100 AS lan_1;
SELECT 200 AS lan_2;
~~~

Lần thứ nhất, đặt con trỏ tại câu đầu và dùng chức năng chạy **câu hiện tại**: kiểm tra xem chỉ có `100` hay không. Lần thứ hai, dùng chức năng chạy **toàn bộ script**: kiểm tra log hoặc các result set xem đã chạy cả `100` và `200` chưa. Từ đây bạn xác định được sự khác nhau giữa hai nút trong chính công cụ đang dùng.

### Bước 3 — Chạy tệp `.sql`

Lưu phần mã ở mục 4 thành `lab_execution.sql` rồi chạy bằng một trong các cách ở bảng công cụ. Lần đầu thực hiện, database thực hành **không được có bảng `execution_lab`** từ lần thử cũ. Chỉ nếu bạn chắc chắn bảng đó là bảng do bài thực hành này tạo và không chứa dữ liệu cần giữ, có thể xóa riêng bảng trước khi chạy lại:

~~~sql
DROP TABLE IF EXISTS execution_lab;
~~~

Lệnh `DROP TABLE` xóa bảng và dữ liệu của bảng; tuyệt đối không dùng nó cho bảng ngoài phạm vi bài thực hành. Sau khi đã xác nhận môi trường thử nghiệm, chạy toàn bộ file một lần.

Kết quả `SELECT` trước `UPDATE`:

| id | task_name | task_status |
| ---: | --- | --- |
| 101 | Doc du lieu | TODO |
| 102 | Kiem tra ket qua | TODO |

Kết quả `SELECT` sau `UPDATE`:

| id | task_name | task_status |
| ---: | --- | --- |
| 101 | Doc du lieu | DONE |
| 102 | Kiem tra ket qua | TODO |

Nếu công cụ chỉ hiển thị tập kết quả cuối, chạy thêm câu sau để xác nhận trạng thái dữ liệu trong database:

~~~sql
SELECT id, task_name, task_status
FROM execution_lab
ORDER BY id;
~~~

### Bước 4 — Thử một lỗi có kiểm soát

Ở database thử nghiệm, sau khi chạy thành công file trên, thử câu:

~~~sql
INSERT INTO execution_lab (id, task_name, task_status)
VALUES (101, 'Dong trung ID', 'TODO');
~~~

Kết quả mong đợi: lỗi **trùng khóa chính**, vì ID `101` đã tồn tại. Quan sát thông báo của công cụ, sau đó chạy `SELECT` xác nhận không có hàng mới mang ID `101` được thêm. Không cần tắt ràng buộc khóa chính để “sửa” lỗi này: ràng buộc đang hoạt động đúng.

## 8. Chọn chế độ thực thi cho đúng mục đích

| Nhu cầu | Cách phù hợp | Điểm cần chú ý |
| --- | --- | --- |
| Kiểm tra nhanh một phép tính hoặc một truy vấn | Chạy một câu lệnh | Chọn đúng đoạn SQL, xem một result set |
| Thử chuỗi tạo bảng → chèn dữ liệu → truy vấn | Chạy nhiều câu trong editor | Thứ tự thực thi và chế độ Run statement/Run script |
| Lưu bài tập để gửi người khác hoặc tái hiện lần sau | Lưu tệp `.sql` | Đường dẫn, encoding, database đích, khả năng chạy lại |
| Chạy nhiều câu có thay đổi dữ liệu liên quan nhau | Dùng transaction khi hệ quản trị hỗ trợ | Autocommit, rollback, giới hạn DDL của từng hệ |
| Chạy tệp từ terminal hoặc quy trình tự động | Dùng CLI như `psql -f` hoặc lệnh đọc tệp tương ứng | Mã lỗi, thông báo lỗi, tùy chọn dừng khi lỗi |

Điều cần nắm vững là: **một câu lệnh** phù hợp để quan sát tác động riêng lẻ; **nhiều câu lệnh** cần kiểm soát thứ tự và cách công cụ hiển thị kết quả; **tệp SQL** giúp lưu và thực thi lại một kịch bản. Trước mỗi lần chạy, xác nhận **đúng kết nối, đúng phần cần chạy, đúng trạng thái dữ liệu ban đầu và đúng kỳ vọng về transaction**.
