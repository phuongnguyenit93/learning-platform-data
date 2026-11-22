# Đọc kết quả dạng bảng, số hàng ảnh hưởng và thông báo lỗi trong SQL

Khi thực hành SQL, viết được câu lệnh mới là bước đầu. Bước tiếp theo là **đọc đúng phản hồi của hệ quản trị cơ sở dữ liệu**: bảng kết quả đang cho biết điều gì, thông báo “3 rows affected” có nghĩa ra sao, và khi xuất hiện lỗi thì nên bắt đầu kiểm tra ở đâu.

Một công cụ SQL (chẳng hạn cửa sổ truy vấn của PostgreSQL, pgAdmin, DBeaver, MySQL Workbench hay một giao diện học SQL trực tuyến) thường hiển thị đồng thời nhiều loại thông tin:

- **Bảng kết quả (result grid/result set)**: các cột và dòng được trả về khi truy vấn dữ liệu.
- **Số hàng ảnh hưởng (rows affected/row count)**: số bản ghi chịu tác động của một thao tác ghi, tùy hệ quản trị và loại lệnh.
- **Thông báo thực thi (messages/status)**: lệnh chạy thành công hay thất bại, thời gian thực thi, số dòng trả về, cảnh báo hoặc thông tin giao dịch.
- **Thông báo lỗi (error/diagnostic)**: loại lỗi, vị trí, đối tượng liên quan và mã lỗi nếu được cung cấp.

Bài học dùng **PostgreSQL** để minh họa các câu lệnh có thể thực hành. Ý tưởng đọc kết quả áp dụng cho SQL nói chung, nhưng câu chữ thông báo, cách đếm hàng bị tác động, mã lỗi và bố cục giao diện có thể khác giữa PostgreSQL, MySQL, SQL Server, Oracle, SQLite và từng phần mềm khách.

## 1. Một câu SQL có thể tạo ra nhiều loại phản hồi

Hãy phân biệt ba câu hỏi:

| Câu hỏi | Nơi thường tìm đáp án | Ví dụ |
|---|---|---|
| **Cơ sở dữ liệu trả về dữ liệu gì?** | Tab Results / Data / Result Grid | Bảng tên và điểm của 3 học viên |
| **Lệnh đã tác động đến bao nhiêu dòng?** | Status / Messages / hàng trạng thái | `UPDATE 1`, “1 row affected” |
| **Lệnh có thực thi thành công không?** | Messages / Error / log thực thi | “Query completed”, `ERROR: ...` |

Không phải lệnh nào cũng cho cả ba loại thông tin:

- `SELECT` thường cho **bảng kết quả**; có thể đi kèm số dòng kết quả và thời gian chạy.
- `INSERT`, `UPDATE`, `DELETE` thường cho **số hàng bị tác động**. Nếu dùng tính năng `RETURNING` của PostgreSQL, chúng còn có thể trả về bảng kết quả.
- `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` thường chỉ cho **trạng thái hoàn thành** hoặc thông báo DDL, không phải bảng dữ liệu.
- Lệnh sai có thể chỉ cho **thông báo lỗi**, không cho kết quả hợp lệ của lệnh đó.

Ví dụ, “Query executed successfully” xác nhận câu lệnh được xử lý mà không gặp lỗi được báo. Nó **không tự chứng minh** rằng có bản ghi được thêm, sửa hoặc xóa. Muốn biết tác động thật sự, cần đọc row count và kiểm tra dữ liệu hoặc trạng thái giao dịch khi cần.

~~~mermaid
flowchart TD
    A["Thực thi câu SQL"] --> B{"Có lỗi?"}
    B -->|Có| E["Đọc thông báo lỗi, mã lỗi, vị trí, chi tiết"]
    B -->|Không| C{"Loại câu lệnh?"}
    C -->|SELECT| D["Đọc cột, dòng, giá trị NULL, số dòng kết quả"]
    C -->|INSERT / UPDATE / DELETE| F["Đọc số hàng ảnh hưởng; xem RETURNING nếu có"]
    C -->|DDL / giao dịch| G["Đọc trạng thái và thông báo"]
    D --> H["Đối chiếu với mục tiêu truy vấn"]
    F --> H
    G --> H
    E --> I["Sửa nguyên nhân rồi thực thi lại phù hợp"]
~~~

## 2. Chuẩn bị môi trường thực hành an toàn

Ta sẽ dùng một bảng tạm để không ảnh hưởng đến dữ liệu nghiệp vụ. Với PostgreSQL, `TEMP TABLE` tồn tại trong **phiên kết nối hiện tại**. Hãy chạy các lệnh trong **cùng một connection/session**; nếu công cụ mở kết nối mới, bảng tạm có thể không còn nhìn thấy. Nếu làm trong môi trường học SQL không hỗ trợ bảng tạm, có thể tạo một bảng thường trong cơ sở dữ liệu thử nghiệm và dọn dẹp sau.

### 2.1. Tạo bảng và dữ liệu mẫu

Thực thi hai câu sau theo thứ tự:

~~~sql
CREATE TEMP TABLE doc_ket_qua_demo (
    id INTEGER PRIMARY KEY,
    ten VARCHAR(50) NOT NULL,
    diem INTEGER NOT NULL CHECK (diem BETWEEN 0 AND 100),
    ghi_chu TEXT
);

INSERT INTO doc_ket_qua_demo (id, ten, diem, ghi_chu)
VALUES
    (1, 'An',   80, NULL),
    (2, 'Bình',  0,  ''),
    (3, 'Chi',  90, 'Cần ôn thêm');
~~~

Nếu thành công, PostgreSQL có thể phản hồi tương tự:

~~~text
CREATE TABLE
INSERT 0 3
~~~

Ở đây, `INSERT 0 3` là **command tag** theo cách PostgreSQL hiển thị: số cuối cùng là **3 dòng được chèn**; số `0` ở giữa thuộc trường OID lịch sử, **không có nghĩa là 0 dòng đã chèn**. Nhiều giao diện khác rút gọn thành “3 rows affected” hoặc “3 rows inserted”.

Đối với `CREATE TABLE`, thông báo “CREATE TABLE” xác nhận tạo bảng thành công. Nó không cho biết bảng có bao nhiêu dòng. Trước khi `INSERT`, bảng mới tạo đang rỗng.

### 2.2. Quan sát bảng bằng SELECT

~~~sql
SELECT id, ten, diem, ghi_chu
FROM doc_ket_qua_demo
ORDER BY id;
~~~

Bảng kết quả mong đợi:

| id | ten | diem | ghi_chu |
|---:|---|---:|---|
| 1 | An | 80 | NULL |
| 2 | Bình | 0 | '' (chuỗi rỗng) |
| 3 | Chi | 90 | Cần ôn thêm |

Các công cụ có thể hiển thị `NULL` bằng chữ `NULL`, ô trống hoặc ký hiệu riêng. Giá trị `''` cũng có thể hiện như một ô trống, nhưng **NULL và chuỗi rỗng không giống nhau**. Cột `diem` của Bình là **số 0**, cũng khác NULL.

`ORDER BY id` giúp thứ tự kết quả xác định. **Không có `ORDER BY`, SQL không bảo đảm thứ tự các dòng** ngay cả khi giao diện vô tình hiển thị theo thứ tự vừa chèn.

## 3. Đọc bảng kết quả của SELECT

Một result grid cần được hiểu theo cả **cột, dòng và giá trị**, không chỉ nhìn số dòng ở cuối cửa sổ.

### 3.1. Cột cho biết dữ liệu nào đang được chọn

~~~sql
SELECT
    ten AS hoc_vien,
    diem AS diem_hien_tai
FROM doc_ket_qua_demo
ORDER BY diem DESC, id;
~~~

| hoc_vien | diem_hien_tai |
|---|---:|
| Chi | 90 |
| An | 80 |
| Bình | 0 |

`AS` đổi tên **cột trong kết quả truy vấn**, không đổi tên cột thật trong bảng. Vì vậy, nếu thấy `hoc_vien` thay cho `ten`, hãy nhìn danh sách cột ở `SELECT` trước khi cho rằng cấu trúc bảng đã thay đổi.

Khi JOIN nhiều bảng, các cột có thể cùng tên `id`, `name`... Hãy đặt bí danh rõ ràng như `khach_hang_id`, `don_hang_id` để đọc kết quả dễ hơn.

### 3.2. Mỗi dòng biểu diễn một bản ghi hoặc một tổ hợp kết quả

~~~sql
SELECT id, ten
FROM doc_ket_qua_demo
WHERE diem >= 80
ORDER BY id;
~~~

Kết quả có hai dòng: An và Chi. Một dòng của result grid ở đây tương ứng với **một bản ghi thỏa điều kiện**. Khi JOIN, GROUP BY hoặc dùng biểu thức tổng hợp, một dòng có thể đại diện cho **một nhóm** hoặc **một tổ hợp nhiều bản ghi**.

Ví dụ, câu dưới đây trả về **một dòng** với giá trị `3`:

~~~sql
SELECT COUNT(*) AS tong_so_hoc_vien
FROM doc_ket_qua_demo;
~~~

| tong_so_hoc_vien |
|---:|
| 3 |

Điểm dễ nhầm: result grid có **1 dòng**, nhưng giá trị được tính là **3 bản ghi**. Vì thế, “1 row returned” trên giao diện không mâu thuẫn với `COUNT(*) = 3`.

### 3.3. SELECT không trả dòng nào vẫn có thể thành công

~~~sql
SELECT id, ten
FROM doc_ket_qua_demo
WHERE diem > 100;
~~~

Vì ràng buộc chỉ cho phép điểm từ 0 đến 100, truy vấn không có dòng thỏa điều kiện. Công cụ thường hiển thị tên cột nhưng **0 rows**, “No rows returned”, “Empty result set” hoặc bảng rỗng.

Điều này **không phải lỗi SQL**. Câu lệnh hợp lệ và đã chạy, chỉ là không có dữ liệu phù hợp. Ngược lại:

~~~sql
SELECT COUNT(*) AS so_hoc_vien_diem_tren_100
FROM doc_ket_qua_demo
WHERE diem > 100;
~~~

cho **một dòng** chứa giá trị `0`. Hai kết quả trên trả lời hai câu hỏi khác nhau: danh sách bản ghi và số lượng bản ghi.

### 3.4. Đọc NULL, chuỗi rỗng và các kiểu dữ liệu

Để thấy rõ sự khác biệt:

~~~sql
SELECT
    id,
    ten,
    ghi_chu,
    ghi_chu IS NULL AS la_null,
    ghi_chu = '' AS la_chuoi_rong
FROM doc_ket_qua_demo
ORDER BY id;
~~~

| id | ten | ghi_chu | la_null | la_chuoi_rong |
|---:|---|---|---|---|
| 1 | An | NULL | true | NULL |
| 2 | Bình | '' | false | true |
| 3 | Chi | Cần ôn thêm | false | false |

Trong SQL, phép so sánh thông thường với NULL có thể trả về giá trị logic **UNKNOWN**, thường được giao diện biểu diễn bằng NULL. Muốn kiểm tra NULL phải dùng `IS NULL` hoặc `IS NOT NULL`, không dùng `= NULL`.

Tùy phần mềm, kết quả còn có thể tự định dạng ngày tháng, thời gian, số thập phân, ký tự Unicode hoặc Boolean. Khi một giá trị trông bất thường, cần phân biệt **giá trị thật trong cơ sở dữ liệu** với **cách giao diện định dạng hoặc cắt ngắn để hiển thị**.

### 3.5. Số dòng nhìn thấy chưa chắc là tổng số dòng có trong bảng

Một số SQL client chỉ tải trang đầu, ví dụ 200 hoặc 500 dòng, rồi tải tiếp khi cuộn. Các con số sau đây khác nhau:

- **Số dòng thực tế trong bảng**: có thể đo bằng `SELECT COUNT(*) FROM ten_bang` khi cần.
- **Số dòng thỏa điều kiện truy vấn**: phụ thuộc `WHERE`, `JOIN`, `GROUP BY`, `DISTINCT`, ...
- **Số dòng truy vấn trả về**: có thể bị giới hạn bởi `LIMIT`/`FETCH`.
- **Số dòng giao diện đã tải/đang hiển thị**: có thể bị giới hạn bởi phân trang của client.

Ví dụ:

~~~sql
SELECT id, ten
FROM doc_ket_qua_demo
ORDER BY id
LIMIT 2;
~~~

trả 2 dòng, dù bảng mẫu có 3 dòng. Vì có `LIMIT 2`, không thể suy ra bảng chỉ có 2 bản ghi. Nếu giao diện có phân trang, hãy kiểm tra nhãn “fetched”, “visible”, “total” hoặc cấu hình giới hạn kết quả trước khi kết luận.

### 3.6. Đọc đúng khi có nhiều câu SELECT hoặc nhiều bộ kết quả

Nếu chạy cả một script:

~~~sql
SELECT COUNT(*) AS tong_so FROM doc_ket_qua_demo;

SELECT ten, diem
FROM doc_ket_qua_demo
ORDER BY id;
~~~

một số công cụ tạo **hai tab kết quả**; công cụ khác chỉ hiện kết quả cuối hoặc có bảng lịch sử cho từng statement. Luôn nhìn **câu lệnh/tab hiện được chọn** trước khi đánh giá dữ liệu.

Nếu chỉ bôi đen một phần SQL rồi nhấn chạy, nhiều client chỉ thực thi phần được chọn. Số dòng và bảng kết quả phản ánh **lệnh thực sự đã chạy**, không nhất thiết phản ánh toàn bộ văn bản đang thấy trong editor.

## 4. Đọc số hàng ảnh hưởng (Rows affected)

“Số hàng ảnh hưởng” thường gắn với thao tác thay đổi dữ liệu:

| Lệnh | Câu hỏi row count trả lời |
|---|---|
| `INSERT` | Có bao nhiêu dòng được chèn vào bảng đích? |
| `UPDATE` | Có bao nhiêu dòng thuộc tập được cập nhật theo quy tắc đếm của hệ quản trị? |
| `DELETE` | Có bao nhiêu dòng bị xóa bởi câu lệnh? |
| `MERGE` / UPSERT | Có bao nhiêu dòng được thêm hoặc tác động theo nhánh xử lý, tùy cách hệ quản trị báo cáo? |
| `SELECT` | Chủ yếu trả về dữ liệu; “rows returned/fetched” không phải số bản ghi bị thay đổi |
| `CREATE TABLE` | Thường trả về trạng thái DDL, không có ý nghĩa “số hàng cập nhật” như UPDATE |

**Cần phân biệt “rows returned” và “rows affected”.** Một câu SELECT trả 3 dòng không làm 3 dòng đó bị thay đổi; ngược lại, một lệnh UPDATE có thể tác động 3 dòng mà không trả về bảng kết quả nào.

### 4.1. INSERT: thêm bao nhiêu dòng?

Câu `INSERT` dữ liệu mẫu đã tạo 3 dòng và có thể báo:

~~~text
INSERT 0 3
-- Hoặc: 3 rows affected
~~~

Nếu dùng tính năng bỏ qua xung đột của PostgreSQL, lệnh có thể thành công mà không thêm dòng nào:

~~~sql
INSERT INTO doc_ket_qua_demo (id, ten, diem)
VALUES (1, 'An khác', 75)
ON CONFLICT (id) DO NOTHING;
~~~

Vì `id = 1` đã có, PostgreSQL phản hồi `INSERT 0 0`. Nghĩa là **0 dòng được thêm**, không phải thất bại. `ON CONFLICT` là cú pháp PostgreSQL; hệ khác có cách UPSERT khác.

### 4.2. UPDATE: có bao nhiêu dòng được cập nhật?

~~~sql
UPDATE doc_ket_qua_demo
SET diem = 85
WHERE id = 1;
~~~

Thông báo PostgreSQL:

~~~text
UPDATE 1
~~~

Một dòng khớp điều kiện và được cập nhật. Đọc lại để biết **giá trị mới**:

~~~sql
SELECT id, ten, diem
FROM doc_ket_qua_demo
WHERE id = 1;
~~~

| id | ten | diem |
|---:|---|---:|
| 1 | An | 85 |

Để so sánh, câu sau hợp lệ nhưng không tìm thấy dòng nào:

~~~sql
UPDATE doc_ket_qua_demo
SET diem = 70
WHERE id = 999;
~~~

Thông báo `UPDATE 0` nghĩa là **không có dòng nào được cập nhật**, không phải lỗi cú pháp. Cần kiểm tra `WHERE`, dữ liệu thực tế và điều kiện JOIN (nếu UPDATE dùng liên kết bảng).

Một điểm tinh tế: trong PostgreSQL, `UPDATE` có thể đếm cả dòng đã khớp mà giá trị đặt lại **bằng giá trị đang có**:

~~~sql
UPDATE doc_ket_qua_demo
SET diem = diem
WHERE id = 1;
-- PostgreSQL: UPDATE 1
~~~

Do đó, row count **không phải bằng chứng số giá trị nghiệp vụ thực sự đã thay đổi**. MySQL còn có thể phân biệt “Rows matched” với “Changed”, tùy client và chế độ kết nối. Hãy xem chính xác nhãn mà công cụ sử dụng.

### 4.3. DELETE: đã xóa bao nhiêu dòng?

~~~sql
DELETE FROM doc_ket_qua_demo
WHERE id = 2;
~~~

Thông báo:

~~~text
DELETE 1
~~~

Bản ghi của Bình đã bị xóa. Câu truy vấn kiểm tra:

~~~sql
SELECT id, ten, diem
FROM doc_ket_qua_demo
ORDER BY id;
~~~

| id | ten | diem |
|---:|---|---:|
| 1 | An | 85 |
| 3 | Chi | 90 |

Nếu `DELETE` trả 0, có thể không còn dòng phù hợp. **Thiếu `WHERE` ở UPDATE/DELETE có thể tác động toàn bộ bảng**; đối với bảng thật, hãy kiểm tra điều kiện và phạm vi dữ liệu trước khi chạy.

### 4.4. RETURNING: lệnh ghi cũng có thể cho ra bảng

PostgreSQL cho phép xem trực tiếp bản ghi được cập nhật:

~~~sql
UPDATE doc_ket_qua_demo
SET diem = 88
WHERE id = 3
RETURNING id, ten, diem;
~~~

Lệnh này cập nhật một dòng và đồng thời trả về bảng:

| id | ten | diem |
|---:|---|---:|
| 3 | Chi | 88 |

Công cụ có thể hiển thị cả result grid và một thông báo `UPDATE 1`. Bảng một dòng ở đây là **dữ liệu RETURNING**, còn `UPDATE 1` là **số dòng cập nhật**; dù cùng bằng 1 trong ví dụ, hai thông tin có mục đích khác nhau.

`RETURNING` còn hữu ích cho `INSERT` và `DELETE` trong PostgreSQL. Cách hỗ trợ hoặc cú pháp ở hệ quản trị khác có thể khác.

### 4.5. Row count có giới hạn ý nghĩa

Đừng mặc định row count là “tổng số thay đổi trong toàn cơ sở dữ liệu”. Chẳng hạn, một `DELETE` ở bảng cha có thể gây ra thao tác cascade theo FK hoặc kích hoạt trigger. Thông báo của câu lệnh chính **không nhất thiết liệt kê riêng mọi thay đổi gián tiếp**. Tương tự, cập nhật không có lỗi không có nghĩa đã được `COMMIT`: giao dịch vẫn có thể bị `ROLLBACK`.

Cách đọc chính xác là: “Công cụ báo số dòng chịu tác động **theo quy tắc của câu lệnh và hệ quản trị này**”, sau đó xác minh kết quả cần thiết.

## 5. Đọc thông báo trạng thái, thời gian và cảnh báo

Một vùng Messages/Output thường có nội dung như:

~~~text
CREATE TABLE
INSERT 0 3
SELECT 2
UPDATE 1
DELETE 1
Query executed successfully. Execution time: 12 ms.
~~~

Đây là **ví dụ cách một số client có thể tổng hợp thông tin**, không phải định dạng chung bắt buộc. Chẳng hạn, `psql` thường in hàng dữ liệu kèm dòng `(2 rows)` thay vì hiện command tag “SELECT 2” như một số API; công cụ đồ họa có thể gộp thời gian chạy và thời gian tải dữ liệu.

Khi đọc trạng thái, chú ý:

- **Thành công**: lệnh đã được máy chủ chấp nhận, nhưng cần đọc row count hoặc grid để hiểu tác động.
- **Thời gian thực thi**: có thể gồm thời gian trên máy chủ, thời gian truyền dữ liệu và thời gian client tải/hiển thị; không phải các công cụ đều đo cùng một thứ.
- **Cảnh báo (warning/notice)**: có thể cung cấp thông tin quan trọng dù câu lệnh vẫn hoàn thành; đọc phần chi tiết nếu có.
- **Nhiều statement**: mỗi statement có thể có thông báo riêng; dòng cuối cùng không mô tả đầy đủ các lệnh trước.
- **COMMIT/ROLLBACK**: thông báo giao dịch quyết định thay đổi có được giữ lại hay bị hoàn tác.

Đối với `CREATE TABLE` và các lệnh DDL, đừng suy diễn “0 rows affected” thành “tạo bảng thất bại”. Hãy kiểm tra trạng thái DDL hoặc truy vấn danh mục hệ thống khi cần biết đối tượng đã tồn tại chưa.

## 6. Đọc thông báo lỗi theo cấu trúc

Một thông báo lỗi tốt thường chứa nhiều dữ kiện hơn một dòng chữ đỏ. Ví dụ, khi cố chèn lại khóa chính `id = 1`:

~~~sql
-- Chạy riêng lẻ để quan sát lỗi, không chạy trong giao dịch dài.
INSERT INTO doc_ket_qua_demo (id, ten, diem)
VALUES (1, 'An trùng', 75);
~~~

PostgreSQL có thể báo tương tự:

~~~text
ERROR: duplicate key value violates unique constraint "doc_ket_qua_demo_pkey"
DETAIL: Key (id)=(1) already exists.
SQLSTATE: 23505
~~~

Dòng `SQLSTATE: 23505` thể hiện mã lỗi PostgreSQL **nếu client có hiển thị SQLSTATE**. `psql` mặc định không luôn in mã này; giao diện hoặc cấu hình “verbose errors” có thể hiển thị.

Hãy tách thông báo thành từng phần:

| Thành phần | Ví dụ | Cách hiểu |
|---|---|---|
| Loại lỗi / thông điệp | `duplicate key value violates unique constraint` | Vi phạm quy tắc duy nhất |
| Tên đối tượng/ràng buộc | `doc_ket_qua_demo_pkey` | Ràng buộc bị vi phạm |
| Chi tiết | `Key (id)=(1) already exists` | Dữ liệu cụ thể gây xung đột |
| SQLSTATE / error code | `23505` | Mã phân loại, hữu ích khi tra cứu |
| Vị trí dòng/cột | `LINE 2`, `Position: 17` | Vị trí máy chủ hoặc client chỉ ra, thường hữu ích với lỗi cú pháp |

Thông báo lỗi không nhất thiết chứa tất cả các trường trên; một số client chỉ hiện tóm tắt, còn phần đầy đủ nằm trong nút “Details”, “Show error”, “Log” hoặc cửa sổ Output.

### 6.1. Lỗi cú pháp: SQL chưa đúng ngữ pháp

~~~sql
SELEC id, ten FROM doc_ket_qua_demo;
~~~

Trong PostgreSQL, lỗi có thể giống:

~~~text
ERROR: syntax error at or near "SELEC"
SQLSTATE: 42601
~~~

Cách xử lý: xem từ khóa bị gõ sai, thiếu dấu phẩy, ngoặc, dấu nháy hoặc mệnh đề đặt sai vị trí. Vị trí được báo là **nơi bộ phân tích cú pháp phát hiện vấn đề**, đôi khi lỗi thật bắt đầu ngay trước vị trí đó.

### 6.2. Lỗi không tìm thấy bảng hoặc cột

~~~sql
SELECT * FROM bang_khong_ton_tai;
~~~

Thông báo ví dụ:

~~~text
ERROR: relation "bang_khong_ton_tai" does not exist
SQLSTATE: 42P01
~~~

Hãy kiểm tra tên bảng, schema, chữ hoa/chữ thường có đặt dấu nháy, cơ sở dữ liệu đang kết nối và phiên làm việc. Trong bài này, **bảng tạm biến mất sau khi phiên kết nối kết thúc**; mở tab mới sử dụng kết nối khác có thể gây lỗi dù trước đó đã tạo bảng thành công.

Tương tự, lỗi cột không tồn tại thường do gõ sai tên cột, dùng alias không đúng hoặc tham chiếu một cột không có trong bảng hiện hành. Không nên lập tức tạo bảng/cột mới nếu trước hết chưa xác nhận connection và schema.

### 6.3. Lỗi dữ liệu không thỏa ràng buộc

Bảng mẫu có ràng buộc `diem BETWEEN 0 AND 100`:

~~~sql
INSERT INTO doc_ket_qua_demo (id, ten, diem)
VALUES (4, 'Dũng', 150);
~~~

PostgreSQL báo vi phạm `CHECK`, mã SQLSTATE thường là `23514`. Dòng `id = 4` **không được thêm** bởi lệnh thất bại này.

Một ví dụ khác:

~~~sql
INSERT INTO doc_ket_qua_demo (id, ten, diem)
VALUES (5, NULL, 70);
~~~

Cột `ten` được định nghĩa `NOT NULL`, nên lệnh bị từ chối (SQLSTATE `23502` trong PostgreSQL). Các loại ràng buộc hay gặp khác là khóa ngoại `FOREIGN KEY` (SQLSTATE `23503` trong PostgreSQL) và duy nhất `UNIQUE` (SQLSTATE `23505`).

Khi gặp loại lỗi này, không nên “sửa” bằng cách bỏ ràng buộc ngay. Hãy kiểm tra dữ liệu đầu vào và quy tắc của bảng: ràng buộc có thể đang ngăn dữ liệu không hợp lệ.

### 6.4. Lỗi kiểu dữ liệu hoặc chuyển đổi

~~~sql
SELECT CAST('khong-phai-so' AS INTEGER);
~~~

Máy chủ sẽ không thể chuyển chuỗi này thành số nguyên; PostgreSQL thường trả SQLSTATE `22P02` (invalid text representation). Đọc thông tin giá trị được chuyển đổi, loại dữ liệu đích và vị trí biểu thức. Sự khác biệt dấu thập phân, ngày/tháng, định dạng chuỗi trong file nhập cũng có thể gây lỗi chuyển đổi.

### 6.5. Lỗi quyền, kết nối và giới hạn tài nguyên

Không phải lỗi nào cũng do cú pháp:

| Nhóm lỗi | Dấu hiệu có thể gặp | Hướng kiểm tra đầu tiên |
|---|---|---|
| Thiếu quyền | “permission denied” | User đang đăng nhập, quyền SELECT/INSERT/UPDATE/DELETE trên đối tượng |
| Sai kết nối | “connection refused”, “database does not exist” | Máy chủ, cổng, tên database, trạng thái dịch vụ và mạng |
| Hết thời gian | “statement timeout”, “query cancelled” | Truy vấn có quá chậm, bị người dùng hủy hay bị giới hạn thời gian |
| Bế tắc/khóa | “deadlock detected”, “lock timeout” | Các giao dịch cạnh tranh dữ liệu, thứ tự thao tác và thời điểm giữ khóa |
| Trạng thái giao dịch lỗi | “current transaction is aborted” | Một lệnh trước đó trong cùng transaction đã thất bại |

Các lỗi trên có cách xử lý khác nhau. Trước khi chạy lại lệnh ghi, cần xác định lần trước có thực sự bị từ chối hay kết quả đã ghi thành công nhưng client chỉ mất kết nối khi nhận phản hồi. Chạy lại `INSERT` không có biện pháp chống lặp có thể dẫn đến dữ liệu trùng hoặc lỗi khóa chính.

### 6.6. Đừng chỉ đọc dòng lỗi cuối

Một lỗi có thể kéo theo nhiều thông báo. Ví dụ, khi chạy nhiều lệnh trong một transaction PostgreSQL, lệnh đầu sai ràng buộc, các lệnh sau có thể đều báo transaction đã lỗi. Trong tình huống đó, thông báo “current transaction is aborted” là **hậu quả**, còn lỗi ràng buộc ở lệnh trước mới là **nguyên nhân khởi đầu**. Hãy đọc log từ lần thất bại đầu tiên của chuỗi lệnh.

## 7. Giao dịch: rows affected không đồng nghĩa với đã lưu vĩnh viễn

Một lệnh `UPDATE 1` có thể hoàn thành nhưng bị hoàn tác nếu nằm trong transaction chưa được `COMMIT`.

Sau các ví dụ ở phần 4, điểm của An đang là 85. Thực hiện tuần tự các lệnh sau trong **cùng kết nối**, khi không có transaction khác đang mở:

~~~sql
BEGIN;

UPDATE doc_ket_qua_demo
SET diem = 60
WHERE id = 1;

SELECT id, ten, diem
FROM doc_ket_qua_demo
WHERE id = 1;

ROLLBACK;

SELECT id, ten, diem
FROM doc_ket_qua_demo
WHERE id = 1;
~~~

Phản hồi theo trình tự:

1. `BEGIN`: bắt đầu transaction.
2. `UPDATE 1`: cập nhật một dòng **trong transaction hiện tại**.
3. `SELECT` đầu: hiển thị `An | 60`, vì chính transaction đó nhìn thấy thay đổi của mình.
4. `ROLLBACK`: hoàn tác thay đổi chưa commit.
5. `SELECT` cuối: hiển thị `An | 85`.

Đọc row count mà bỏ qua `ROLLBACK` sẽ dẫn đến kết luận sai rằng dữ liệu đã lưu thành 60. Muốn lưu, dùng `COMMIT` khi thay đổi hợp lệ; muốn hủy, dùng `ROLLBACK`.

Các SQL client có thể bật **autocommit** mặc định (mỗi statement thành công được commit ngay) hoặc yêu cầu commit thủ công. Hãy kiểm tra chế độ kết nối; nếu đang dùng transaction thủ công, đọc rõ trạng thái “pending transaction”, “Commit”, “Rollback” của client trước khi đóng phiên.

### 7.1. Điều gì xảy ra nếu có lỗi trong transaction?

Trên PostgreSQL, một câu SQL gây lỗi thường làm transaction hiện tại chuyển sang trạng thái **aborted**. Những lệnh kế tiếp sẽ tiếp tục thất bại cho đến khi `ROLLBACK` (hoặc rollback tới savepoint thích hợp).

~~~sql
BEGIN;

-- Cố ý sai: id = 1 đã tồn tại.
INSERT INTO doc_ket_qua_demo (id, ten, diem)
VALUES (1, 'Trùng khóa', 50);

-- Nếu chạy tiếp trong cùng transaction, SELECT cũng có thể báo:
-- current transaction is aborted, commands ignored until end of transaction block

ROLLBACK;
~~~

Nếu đã chạy một câu thất bại bên trong transaction, hãy xử lý transaction trước khi thử lại. Thực hành nhiều ví dụ lỗi trong một script lớn có thể làm bạn nhầm lỗi hiện tại với hậu quả của lỗi trước.

## 8. Một quy trình đọc kết quả khi thực hành

Khi vừa bấm Run/Execute, có thể làm theo thứ tự sau.

**Bước 1 — Xác định lệnh thực sự đã chạy.** Nhìn đoạn SQL được chọn, statement hiện tại, connection/database và tab kết quả. Với script có nhiều câu, kiểm tra xem công cụ thực thi một câu hay toàn bộ script.

**Bước 2 — Xác định lệnh có lỗi không.** Nếu có dấu đỏ hoặc thông báo thất bại, mở chi tiết và tìm **lỗi gốc đầu tiên**, đối tượng, vị trí, SQLSTATE. Đừng suy diễn từ một bảng kết quả cũ còn nằm trên giao diện.

**Bước 3 — Nếu là SELECT, đọc grid.** Kiểm tra tên cột, kiểu dữ liệu, số dòng trả về, NULL, điều kiện lọc, sắp xếp và phân trang. So sánh với câu hỏi mà truy vấn cần trả lời.

**Bước 4 — Nếu là INSERT/UPDATE/DELETE, đọc row count.** “0 rows affected” có thể là kết quả hợp lệ nhưng bất ngờ; kiểm tra `WHERE` và ràng buộc. Với lệnh thay đổi dữ liệu, đọc lại một vùng dữ liệu có chọn lọc hoặc dùng `RETURNING` khi hỗ trợ.

**Bước 5 — Kiểm tra giao dịch.** Dữ liệu vừa thay đổi đã được commit, đang chờ commit hay đã rollback? Hãy phân biệt phản hồi của statement với trạng thái lưu cuối cùng.

**Bước 6 — Ghi lại bằng chứng thực hành.** Với một bài tập, nên lưu câu SQL, bảng kết quả hoặc thông báo quan trọng, số dòng và một lời giải thích ngắn. Một ảnh chỉ chụp “Success” thường chưa đủ để chứng minh kết quả dữ liệu.

Ví dụ cách ghi nhận:

~~~text
Mục tiêu: tăng điểm An từ 80 lên 85
SQL: UPDATE doc_ket_qua_demo SET diem = 85 WHERE id = 1;
Trạng thái: thành công
Rows affected: 1
Kiểm tra SELECT: id=1, ten='An', diem=85
Giao dịch: đã commit (nếu client dùng autocommit)
~~~

Nếu lệnh thực thi trong transaction chưa commit, ghi rõ “chưa commit” thay vì khẳng định dữ liệu đã được lưu bền vững.

## 9. Những tình huống dễ hiểu nhầm

| Điều bạn nhìn thấy | Kết luận sai dễ mắc | Cách hiểu / kiểm tra đúng |
|---|---|---|
| SELECT báo “3 rows” | 3 dòng đã bị cập nhật | Đây là 3 **dòng kết quả được trả về** |
| SELECT hiển thị bảng rỗng | SQL chạy lỗi | Truy vấn có thể thành công nhưng không có dòng thỏa `WHERE` |
| `COUNT(*)` ra 0 | SELECT trả về 0 dòng | SELECT tổng hợp thường trả **1 dòng có giá trị 0** |
| UPDATE báo 0 rows affected | UPDATE bị lỗi | Không có dòng phù hợp, hoặc quy tắc đếm của hệ quản trị dẫn đến 0 |
| UPDATE báo 1 | Giá trị chắc chắn đã đổi | Có thể gán lại giá trị cũ; cần kiểm tra nội dung và cách DBMS đếm |
| INSERT báo `INSERT 0 3` | Chỉ có 0 dòng được thêm | Với PostgreSQL, số cuối là **3 dòng được chèn** |
| Kết quả grid chỉ hiển thị 100 dòng | Bảng có đúng 100 dòng | Client có thể chỉ fetch/hiển thị trang đầu |
| Ô ghi chú trống | Giá trị chắc chắn là NULL | Có thể là chuỗi rỗng hoặc cách hiển thị của client |
| Dữ liệu vừa SELECT thấy giá trị mới | Đã lưu vĩnh viễn | Có thể vẫn ở trong transaction và bị rollback |
| Lỗi “relation does not exist” với TEMP TABLE | Phải tạo bảng thường | Có thể đã đổi kết nối, làm mất bảng tạm |
| Nhiều lỗi liên tiếp trong transaction | Mỗi câu lệnh đều sai độc lập | Có thể một lỗi đầu tiên làm transaction aborted |
| DDL báo 0 rows affected | CREATE TABLE không thành công | DDL được đánh giá qua trạng thái tạo đối tượng, không qua row count kiểu UPDATE |

## 10. Bài tập thực hành và lời giải

Các bài tập bên dưới giả định bạn đã chạy đến hết phần 7 và đang dùng đúng phiên chứa bảng tạm. Khi ấy còn hai dòng:

| id | ten | diem | ghi_chu |
|---:|---|---:|---|
| 1 | An | 85 | NULL |
| 3 | Chi | 88 | Cần ôn thêm |

Nếu đã ngắt kết nối hoặc tự sửa dữ liệu theo hướng khác, hãy tạo lại bảng tạm trong một phiên mới rồi điều chỉnh dữ liệu mẫu về trạng thái trên trước khi so sánh đáp án.

### Bài 1. Phân biệt số dòng kết quả và tổng số bản ghi

Dự đoán số dòng hiển thị ở hai lệnh:

~~~sql
SELECT id
FROM doc_ket_qua_demo
WHERE diem > 90;

SELECT COUNT(*) AS so_hang
FROM doc_ket_qua_demo
WHERE diem > 90;
~~~

**Đáp án:** Câu đầu trả **0 dòng**, câu sau trả **1 dòng có giá trị 0**. Cả hai câu hợp lệ và không thay đổi bảng.

### Bài 2. Dự đoán số hàng ảnh hưởng

~~~sql
UPDATE doc_ket_qua_demo
SET diem = 95
WHERE id IN (1, 3);
~~~

**Đáp án:** PostgreSQL báo `UPDATE 2`. Hai dòng cùng thỏa điều kiện; đọc lại `SELECT id, diem FROM doc_ket_qua_demo ORDER BY id` sẽ thấy điểm của An và Chi đều là 95. Nếu đang bật autocommit thì thay đổi thường được commit ngay; trong transaction thủ công phải xét lệnh COMMIT/ROLLBACK.

### Bài 3. Nhận diện lỗi ràng buộc

~~~sql
INSERT INTO doc_ket_qua_demo (id, ten, diem)
VALUES (4, 'Dũng', -5);
~~~

**Đáp án:** Lệnh bị từ chối vì `diem` vi phạm `CHECK (diem BETWEEN 0 AND 100)`. Kết quả không phải “thêm 1 dòng có điểm -5”; đây là **lỗi**, không phải một lần INSERT thành công. Hãy đọc phần DETAIL/ràng buộc của thông báo thay vì bỏ qua lỗi.

### Bài 4. Phân biệt một lỗi cú pháp với một kết quả rỗng

Xét hai trường hợp:

~~~sql
-- Trường hợp A:
SELECT ten FROM doc_ket_qua_demo WHERE id = 999;

-- Trường hợp B (gõ sai từ khóa):
SELEC ten FROM doc_ket_qua_demo WHERE id = 1;
~~~

**Đáp án:** Trường hợp A thực thi thành công và trả **0 dòng**; trường hợp B gây **lỗi cú pháp**. Cần nhìn trạng thái thực thi, không thể chỉ dựa vào việc “không thấy tên nào trong bảng kết quả”.

### Bài 5. Tự đánh giá bằng chứng sau DELETE

Nếu chạy:

~~~sql
BEGIN;
DELETE FROM doc_ket_qua_demo WHERE id = 1;
ROLLBACK;
~~~

bạn có thể thấy thông báo `DELETE 1`. Hỏi: “Sau khi kết thúc giao dịch, An còn trong bảng không?”

**Đáp án:** **Còn**. `DELETE 1` xác nhận một dòng bị xóa **trong transaction**, nhưng `ROLLBACK` đã hoàn tác thao tác đó. Đọc lại bằng `SELECT` sau rollback sẽ thấy An; đây là ví dụ điển hình cho việc không được suy ra trạng thái dữ liệu cuối cùng chỉ từ thông báo rows affected.

## 11. Ghi nhớ khi đọc kết quả SQL

Một phản hồi SQL chỉ có ý nghĩa khi đặt trong **ngữ cảnh câu lệnh vừa chạy**.

- Với `SELECT`, đọc **các cột, các dòng, giá trị và số dòng trả về**; nhớ phân biệt bảng rỗng, NULL và giá trị 0.
- Với `INSERT`, `UPDATE`, `DELETE`, đọc **số hàng ảnh hưởng**, rồi đối chiếu với điều kiện và dữ liệu cần thay đổi.
- Với `CREATE TABLE` hoặc lệnh DDL khác, đọc **thông báo hoàn thành và đối tượng được tạo/sửa**.
- Khi lỗi, tìm **lỗi gốc, thông điệp, ràng buộc, vị trí và mã lỗi** trước khi chạy lại.
- Khi sử dụng transaction, phân biệt **lệnh đã thực thi** với **thay đổi đã được commit**.

Thói quen này giúp bạn biết một câu SQL có thực sự trả lời đúng câu hỏi hay chưa, giải thích được vì sao “0 rows affected” có thể hợp lệ và tìm nguyên nhân sự cố nhanh hơn khi thực hành với cơ sở dữ liệu.
