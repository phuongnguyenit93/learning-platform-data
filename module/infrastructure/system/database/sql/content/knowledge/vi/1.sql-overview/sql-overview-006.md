# Vai trò của DDL, DML, truy vấn, điều khiển giao dịch và phân quyền trong SQL

SQL (Structured Query Language) là ngôn ngữ dùng để làm việc với hệ quản trị cơ sở dữ liệu quan hệ (RDBMS) như PostgreSQL, MySQL, SQL Server và Oracle Database. Khi nói đến SQL, nhiều người nghĩ ngay đến câu lệnh `SELECT`. Trên thực tế, một ứng dụng cần SQL để **định nghĩa cấu trúc dữ liệu, ghi và sửa dữ liệu, đọc thông tin, bảo đảm nhiều thay đổi đi cùng nhau, và kiểm soát ai được thực hiện thao tác nào**.

Năm nhóm chức năng thường được dùng để giải thích các vai trò đó là DDL, DML, truy vấn (thường gọi DQL), điều khiển giao dịch (TCL) và phân quyền (DCL). Đây là cách phân loại phục vụ học tập; một số tài liệu gộp `SELECT` vào DML hoặc phân loại các lệnh quản trị khác nhau tùy hệ quản trị. **Điều quan trọng là hiểu tác dụng của câu lệnh, không chỉ ghi nhớ tên nhóm.**

## 1. Năm nhóm lệnh giải quyết năm nhu cầu khác nhau

| Nhóm | Tên đầy đủ | Câu hỏi được giải quyết | Lệnh tiêu biểu |
| --- | --- | --- | --- |
| **DDL** | Data Definition Language | Dữ liệu được tổ chức và ràng buộc ra sao? | `CREATE`, `ALTER`, `DROP`, `TRUNCATE` |
| **DML** | Data Manipulation Language | Dữ liệu trong bảng được thêm, đổi, xóa thế nào? | `INSERT`, `UPDATE`, `DELETE` |
| **Truy vấn / DQL** | Data Query Language | Làm sao lấy những dòng, cột và kết quả tổng hợp cần thiết? | `SELECT` (cùng `WHERE`, `JOIN`, `GROUP BY`, ...) |
| **TCL** | Transaction Control Language | Nhiều thay đổi cần thành công hoặc thất bại cùng nhau như thế nào? | `BEGIN` / `START TRANSACTION`, `COMMIT`, `ROLLBACK`, `SAVEPOINT` |
| **DCL** | Data Control Language | Người dùng hoặc vai trò nào được đọc hay thay đổi đối tượng nào? | `GRANT`, `REVOKE` |

Có thể hình dung vòng đời của một ứng dụng bán hàng:

1. Người phát triển dùng **DDL** tạo bảng sản phẩm, đơn hàng và quy tắc toàn vẹn dữ liệu.
2. Ứng dụng dùng **truy vấn** để hiển thị sản phẩm còn hàng, tìm kiếm và thống kê.
3. Khi khách mua, ứng dụng dùng **DML** giảm tồn kho và thêm đơn hàng.
4. **TCL** gói các thay đổi trên thành một giao dịch để tránh trường hợp đã trừ kho nhưng chưa lưu đơn.
5. **DCL** cho ứng dụng quyền thao tác cần thiết, trong khi tài khoản báo cáo chỉ có quyền đọc.

Các nhóm này phối hợp với nhau; chúng không phải năm loại cơ sở dữ liệu riêng biệt.

## 2. DDL: Định nghĩa cấu trúc và quy tắc của dữ liệu

DDL tác động chủ yếu đến **lược đồ** (*schema*): bảng, cột, kiểu dữ liệu, khóa, ràng buộc, chỉ mục và một số đối tượng cơ sở dữ liệu khác.

### 2.1. Tạo bảng bằng CREATE

Ví dụ sau dùng cú pháp **PostgreSQL** để minh họa xuyên suốt bài. Tên bảng và cột không dấu giúp câu lệnh dễ dùng trong nhiều công cụ. Một số chi tiết như `GENERATED ALWAYS AS IDENTITY`, `TIMESTAMPTZ` và cú pháp quản trị quyền có thể khác ở MySQL, SQL Server hoặc Oracle.

~~~sql
CREATE TABLE san_pham (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ten VARCHAR(120) NOT NULL,
    gia NUMERIC(12, 2) NOT NULL CHECK (gia >= 0),
    ton_kho INTEGER NOT NULL DEFAULT 0 CHECK (ton_kho >= 0)
);

CREATE TABLE don_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    san_pham_id BIGINT NOT NULL REFERENCES san_pham(id),
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    thoi_diem TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Lệnh này không chỉ tạo chỗ lưu dữ liệu. Nó còn diễn đạt các quy tắc:

- `PRIMARY KEY`: mỗi sản phẩm hoặc đơn hàng có một định danh duy nhất.
- `NOT NULL`: cột bắt buộc phải có giá trị khác `NULL`.
- `CHECK (gia >= 0)`, `CHECK (ton_kho >= 0)`: không cho lưu giá hoặc tồn kho âm.
- `DEFAULT`: cấp giá trị mặc định khi câu lệnh chèn không cung cấp cột đó.
- `REFERENCES san_pham(id)`: đơn hàng phải tham chiếu đến một sản phẩm tồn tại (*foreign key*).

Những ràng buộc này được kiểm tra ngay tại cơ sở dữ liệu, vì vậy vẫn có tác dụng khi dữ liệu được ghi từ ứng dụng khác, script nhập liệu hoặc công cụ quản trị.

### 2.2. Thay đổi và loại bỏ cấu trúc

~~~sql
-- Bổ sung trạng thái bán hàng cho bảng đã có.
ALTER TABLE san_pham
ADD COLUMN dang_ban BOOLEAN NOT NULL DEFAULT TRUE;

-- Ví dụ xóa một bảng khi thực sự không còn cần tới nó.
-- DROP TABLE don_hang;
~~~

`ALTER TABLE` giúp cập nhật cấu trúc đang tồn tại; `DROP TABLE` loại bỏ chính bảng đó. Lệnh `DROP` có thể làm mất dữ liệu và ảnh hưởng các đối tượng đang phụ thuộc vào bảng, nên thay đổi cấu trúc trong ứng dụng thực tế thường được quản lý qua **migration có phiên bản**, kiểm tra quan hệ phụ thuộc và sao lưu thích hợp.

`TRUNCATE TABLE san_pham` có mục đích khác: xóa toàn bộ dòng của bảng nhưng giữ cấu trúc. Không nên coi `TRUNCATE` là một `DELETE` có điều kiện, vì nó không hỗ trợ `WHERE` và có những quy tắc riêng về khóa, khóa ngoại, bộ đếm định danh và giao dịch tùy hệ quản trị.

**Ranh giới của DDL:** DDL quyết định *dữ liệu có thể được lưu dưới hình dạng nào*; DDL tự nó không phải thao tác tạo một đơn hàng mới hay hiển thị danh sách sản phẩm.

## 3. DML: Thay đổi các dòng dữ liệu

Sau khi bảng đã được định nghĩa, DML xử lý các bản ghi bên trong bảng. Ba thao tác cơ bản là thêm, sửa và xóa.

### 3.1. INSERT: thêm dữ liệu

~~~sql
INSERT INTO san_pham (ten, gia, ton_kho)
VALUES
    ('Ban phim', 450000.00, 12),
    ('Chuot', 250000.00, 20);
~~~

Mỗi bộ giá trị tạo một dòng mới. Cột `id` dùng cơ chế sinh tự động, còn `dang_ban` và các cột có `DEFAULT` nhận giá trị mặc định nếu không được cung cấp. Ví dụ phía dưới giả định đây là hai sản phẩm đầu tiên trong bảng mới tạo, tương ứng `id = 1` và `id = 2`. Trong ứng dụng thực tế nên lấy mã định danh mà cơ sở dữ liệu trả về thay vì giả định giá trị của bộ đếm.

### 3.2. UPDATE: thay đổi dữ liệu có sẵn

~~~sql
UPDATE san_pham
SET gia = 430000.00
WHERE id = 1;
~~~

`UPDATE` có thể thay đổi nhiều cột hoặc nhiều dòng. Điều kiện `WHERE` quyết định **dòng nào** được cập nhật. Nếu bỏ `WHERE`, mọi dòng trong bảng có thể bị đổi giá. Một cách làm an toàn là xác nhận điều kiện và số dòng bị ảnh hưởng, đặc biệt trong thao tác có tác động lớn.

### 3.3. DELETE: xóa dòng

~~~sql
-- Xóa một đơn hàng theo định danh cụ thể, nếu đơn hàng đó tồn tại.
DELETE FROM don_hang
WHERE id = 42;
~~~

`DELETE` xóa các dòng phù hợp điều kiện và vẫn giữ bảng cùng định nghĩa cột. Nếu bỏ `WHERE`, lệnh có thể xóa toàn bộ dòng. Khóa ngoại có thể ngăn xóa một sản phẩm còn được đơn hàng tham chiếu, trừ khi thiết kế quan hệ quy định hành vi xóa liên đới phù hợp.

### 3.4. Phân biệt INSERT, UPDATE, DELETE với DDL

| Mục đích | Lệnh phù hợp | Điều bị tác động |
| --- | --- | --- |
| Tạo bảng `san_pham` | `CREATE TABLE` | Cấu trúc |
| Thêm sản phẩm mới | `INSERT INTO` | Dòng dữ liệu |
| Sửa giá một sản phẩm | `UPDATE ... WHERE` | Dòng dữ liệu |
| Xóa một đơn hàng | `DELETE ... WHERE` | Dòng dữ liệu |
| Thêm cột `dang_ban` | `ALTER TABLE` | Cấu trúc |
| Xóa cả bảng và định nghĩa của nó | `DROP TABLE` | Cấu trúc và dữ liệu của bảng |

Về bản chất, DML làm thay đổi **trạng thái dữ liệu**. Câu lệnh thành công về cú pháp chưa chắc đúng về nghiệp vụ; ví dụ, trừ tồn kho mà không kiểm tra số lượng còn lại vẫn có thể gây sai lệch. Ta cần kết hợp DML với ràng buộc, điều kiện và giao dịch.

## 4. Truy vấn: Biến dữ liệu lưu trữ thành thông tin cần dùng

Truy vấn thường bắt đầu bằng `SELECT`. Nó cho phép lấy cột, lọc dòng, kết hợp bảng, sắp xếp và tính kết quả tổng hợp. Ở mức nhập môn, `SELECT` là thao tác **đọc**; không phải mọi câu lệnh có chữ `SELECT` đều hoàn toàn không có tác động, chẳng hạn truy vấn khóa dòng bằng `FOR UPDATE` hoặc gọi hàm có tác dụng phụ.

### 4.1. Chọn cột, lọc và sắp xếp

~~~sql
SELECT id, ten, gia, ton_kho
FROM san_pham
WHERE dang_ban = TRUE
  AND ton_kho > 0
ORDER BY gia DESC, id ASC;
~~~

Ý nghĩa các thành phần:

- `SELECT`: xác định cột hoặc biểu thức muốn trả về.
- `FROM`: chỉ nguồn dữ liệu.
- `WHERE`: chỉ giữ những dòng thỏa điều kiện.
- `ORDER BY`: xác định thứ tự kết quả, ở đây giá giảm dần rồi mã tăng dần.

Không có `ORDER BY` thì **không được giả định thứ tự các dòng** luôn giống nhau, dù chạy thử nhiều lần thấy thứ tự có vẻ ổn định.

### 4.2. Kết hợp bảng với JOIN

~~~sql
SELECT
    dh.id AS ma_don_hang,
    sp.ten AS ten_san_pham,
    dh.so_luong,
    dh.thoi_diem
FROM don_hang AS dh
JOIN san_pham AS sp
    ON sp.id = dh.san_pham_id
ORDER BY dh.thoi_diem DESC, dh.id DESC;
~~~

Bảng `don_hang` lưu mã sản phẩm; bảng `san_pham` lưu tên sản phẩm. `JOIN` dùng mối quan hệ khóa ngoại để trình bày thông tin từ cả hai bảng trong một kết quả. `INNER JOIN` (viết ngắn `JOIN`) chỉ trả về các cặp dòng khớp điều kiện kết nối; `LEFT JOIN` có thể giữ cả dòng bên trái chưa có dòng khớp bên phải.

### 4.3. Thống kê với GROUP BY và HAVING

~~~sql
SELECT
    sp.id,
    sp.ten,
    SUM(dh.so_luong) AS tong_so_luong_dat
FROM san_pham AS sp
JOIN don_hang AS dh
    ON dh.san_pham_id = sp.id
GROUP BY sp.id, sp.ten
HAVING SUM(dh.so_luong) >= 2
ORDER BY tong_so_luong_dat DESC, sp.id ASC;
~~~

`GROUP BY` gom các đơn theo sản phẩm; `SUM` tính tổng số lượng trong từng nhóm; `HAVING` lọc **sau khi tổng hợp**. Trong khi đó, `WHERE` lọc các dòng đầu vào **trước khi nhóm**. Với `JOIN` ở ví dụ này, sản phẩm chưa từng có đơn hàng sẽ không xuất hiện; muốn kể cả sản phẩm chưa bán cần thiết kế truy vấn `LEFT JOIN` phù hợp.

Truy vấn còn được dùng để phân trang, kiểm tra dữ liệu trước khi sửa, xây dựng dashboard và phục vụ báo cáo. Việc chọn đúng cột, tạo chỉ mục phù hợp, đọc kế hoạch thực thi và giới hạn lượng dữ liệu trả về trở nên quan trọng khi bảng lớn; SQL mô tả **kết quả cần lấy**, còn bộ tối ưu hóa của hệ quản trị quyết định cách thực hiện.

## 5. Điều khiển giao dịch: Giữ các thay đổi liên quan nhất quán

Một **giao dịch** (*transaction*) là một đơn vị công việc gồm một hoặc nhiều câu lệnh. Khi đặt chúng trong cùng giao dịch, hệ quản trị có thể xác nhận toàn bộ bằng `COMMIT` hoặc hủy các thay đổi chưa xác nhận bằng `ROLLBACK`.

### 5.1. Vì sao một đơn hàng cần transaction?

Khi khách mua hai bàn phím, hệ thống cần **giảm tồn kho** và **thêm đơn hàng**. Nếu chỉ thao tác đầu thành công, dữ liệu đã bị trừ hàng nhưng không có đơn tương ứng. Giao dịch giúp hai thao tác cùng được xác nhận.

~~~sql
BEGIN;

UPDATE san_pham
SET ton_kho = ton_kho - 2
WHERE id = 1
  AND ton_kho >= 2;

-- Ứng dụng PHẢI kiểm tra số dòng UPDATE: phải đúng 1.
-- Nếu là 0 (sản phẩm không tồn tại hoặc không đủ hàng): ROLLBACK.
-- Chỉ khi là 1 mới tiếp tục:

INSERT INTO don_hang (san_pham_id, so_luong)
VALUES (1, 2);

COMMIT;
~~~

Đoạn trên minh họa **luồng điều khiển của ứng dụng**, không phải một khối SQL tự quyết định khi nào bỏ qua `INSERT`. Phần mềm gọi câu lệnh `UPDATE`, đọc số dòng bị ảnh hưởng do driver trả về, rồi mới quyết định chạy `INSERT` và `COMMIT` hay chạy `ROLLBACK`. Nếu `INSERT` lỗi, ứng dụng cũng cần `ROLLBACK`. Nhờ điều kiện `ton_kho >= 2` nằm ngay trong `UPDATE`, việc kiểm tra và trừ kho diễn ra trong một thao tác cập nhật có khóa đồng thời của cơ sở dữ liệu, thay vì đọc số tồn rồi tùy tiện trừ ở hai câu lệnh rời.

Không thể dùng `COMMIT` để sửa một nghiệp vụ vốn sai. Ví dụ, nếu ứng dụng quên kiểm tra số dòng cập nhật và vẫn lưu đơn khi hết hàng, giao dịch vẫn có thể được commit một cách hợp lệ về mặt cơ sở dữ liệu. **TCL bảo đảm ranh giới giao dịch, còn điều kiện nghiệp vụ và ràng buộc bảo đảm nội dung được phép ghi.**

### 5.2. COMMIT, ROLLBACK và SAVEPOINT

- `BEGIN` (hoặc `START TRANSACTION` theo hệ quản trị): mở giao dịch tường minh.
- `COMMIT`: xác nhận thay đổi trong giao dịch; các phiên khác sẽ thấy chúng theo quy tắc cô lập tương ứng.
- `ROLLBACK`: hủy các thay đổi chưa commit của giao dịch.
- `SAVEPOINT`: đặt mốc để quay lui một phần thao tác trước khi quyết định commit toàn bộ.

~~~sql
BEGIN;

UPDATE san_pham
SET gia = gia + 10000
WHERE id = 1;

SAVEPOINT truoc_thu_nghiem;

UPDATE san_pham
SET ton_kho = ton_kho + 5
WHERE id = 2;

ROLLBACK TO SAVEPOINT truoc_thu_nghiem;
-- Việc tăng tồn kho sản phẩm 2 bị hoàn tác;
-- việc tăng giá sản phẩm 1 vẫn còn trong transaction.

COMMIT;
~~~

Sau `COMMIT`, `ROLLBACK` trong một giao dịch mới không thể tự động hoàn tác commit đã xảy ra. Muốn đảo ngược một thay đổi đã xác nhận cần giao dịch bù, khôi phục dữ liệu hoặc một cơ chế phục hồi phù hợp.

### 5.3. ACID giải thích độ tin cậy của giao dịch

| Thuộc tính | Ý nghĩa | Liên hệ ví dụ |
| --- | --- | --- |
| **Atomicity** — tính nguyên tử | Các thay đổi thuộc giao dịch được commit cùng nhau hoặc bị rollback cùng nhau. | Không để trạng thái đã trừ kho nhưng chưa lưu đơn nếu xử lý lỗi đúng. |
| **Consistency** — tính nhất quán | Giao dịch đưa dữ liệu từ trạng thái hợp lệ này sang trạng thái hợp lệ khác theo các ràng buộc đã được định nghĩa. | Khóa ngoại và `CHECK` tiếp tục được thỏa mãn; quy tắc nghiệp vụ vẫn phải được lập trình đúng. |
| **Isolation** — tính cô lập | Các giao dịch đồng thời tương tác theo mức cô lập mà hệ quản trị cung cấp. | Hai khách cùng đặt mua không được xử lý bằng cách đọc tồn kho cũ rồi ghi đè tùy tiện. |
| **Durability** — tính bền vững | Dữ liệu đã commit phải được hệ quản trị giữ bền vững theo cam kết lưu trữ và cấu hình của nó. | Đơn đã được xác nhận vẫn được bảo toàn sau sự cố mà cơ chế phục hồi của hệ quản trị hỗ trợ. |

Các mức cô lập thường được nhắc tới gồm `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE` (và trong SQL chuẩn có `READ UNCOMMITTED`). Mức cô lập cao hơn có thể giảm một số bất thường đồng thời nhưng thường kéo theo chi phí chờ, khóa hoặc khả năng phải chạy lại giao dịch. Chi tiết hành vi khác nhau giữa các hệ quản trị.

**Lưu ý khi vận hành:** nhiều kết nối chạy chế độ *autocommit*, nghĩa là mỗi câu lệnh có thể tự commit nếu không mở giao dịch tường minh. Ngoài ra, một số hệ quản trị tự commit trước hoặc sau một số lệnh DDL; ví dụ PostgreSQL hỗ trợ rollback nhiều lệnh DDL thông thường, còn MySQL có nhiều lệnh DDL gây implicit commit. Vì vậy không được mặc định rằng mọi loại câu lệnh đều rollback giống nhau trên mọi DBMS.

## 6. Phân quyền: Giới hạn ai được làm gì

Nếu DDL nói cấu trúc cho phép điều gì và DML nói dữ liệu thay đổi thế nào, **DCL xác định chủ thể nào được phép thực hiện thao tác trên từng đối tượng**. Chủ thể thường là user hoặc role; quyền có thể gồm `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `REFERENCES` và các quyền riêng của từng hệ quản trị.

### 6.1. GRANT và REVOKE

Trong PostgreSQL, giả sử người quản trị đã có quyền tạo và quản lý vai trò:

~~~sql
-- Tạo role dùng chung cho việc đọc báo cáo.
CREATE ROLE vai_tro_bao_cao;

-- Cho phép truy cập schema chứa bảng (khi cần).
GRANT USAGE ON SCHEMA public TO vai_tro_bao_cao;

-- Cho phép đọc bảng sản phẩm, không cấp quyền ghi.
GRANT SELECT ON TABLE san_pham TO vai_tro_bao_cao;

-- Khi cần thu hồi quyền đọc đã cấp trực tiếp:
REVOKE SELECT ON TABLE san_pham FROM vai_tro_bao_cao;
~~~

`CREATE ROLE` là lệnh quản trị/định nghĩa đối tượng bảo mật, còn cặp `GRANT`–`REVOKE` minh họa rõ chức năng của DCL. Role ở ví dụ không tự đăng nhập được; để một tài khoản thực sự sử dụng quyền, người quản trị còn phải gán role cho tài khoản theo cơ chế của hệ quản trị. Quyền hiệu lực có thể đến từ nhiều role, quyền sở hữu hoặc các nguồn cấp khác, nên `REVOKE` một quyền cấp trực tiếp **không bảo đảm** chủ thể không còn quyền đó từ mọi nguồn.

Một mô hình phân quyền thường gặp:

| Chủ thể | Công việc | Quyền nên cân nhắc |
| --- | --- | --- |
| Tài khoản ứng dụng bán hàng | Đọc sản phẩm, ghi đơn và cập nhật tồn kho | `SELECT` và các quyền DML cần thiết trên đúng bảng |
| Tài khoản báo cáo | Đọc để tính chỉ số | `SELECT` trên các bảng hoặc view được cho phép |
| Công cụ migration | Nâng cấp schema có kiểm soát | Quyền DDL phù hợp trên phạm vi triển khai |
| Quản trị cơ sở dữ liệu | Quản lý vai trò, cấu hình và vận hành | Các quyền quản trị cần thiết, dùng có kiểm soát |

Nguyên tắc **đặc quyền tối thiểu** (*least privilege*) giúp giới hạn thiệt hại nếu thông tin đăng nhập bị lộ hoặc ứng dụng có lỗi. Quyền trong DB không thay thế kiểm tra người dùng ở tầng ứng dụng, kiểm soát quyền trên từng dòng (nếu cần), hay truy vấn tham số hóa để chống SQL injection. Cú pháp cấp quyền ở từng DBMS có thể khác PostgreSQL; các lệnh cũng cần được thực thi bởi chủ thể đang có quyền cấp/thu hồi tương ứng.

## 7. Khi nào dùng nhóm lệnh nào trong một yêu cầu thực tế?

Xét tính năng “khách đặt mua sản phẩm”:

~~~mermaid
flowchart TD
    A["Thiết kế bảng sản phẩm và đơn hàng"] --> B["DDL: CREATE TABLE, ràng buộc"]
    B --> C["DCL: cấp quyền cần thiết cho ứng dụng"]
    C --> D["Truy vấn: SELECT sản phẩm còn hàng"]
    D --> E["TCL: BEGIN"]
    E --> F["DML: UPDATE tồn kho có điều kiện"]
    F --> G{"Đã cập nhật đúng 1 dòng?"}
    G -->|Không| H["TCL: ROLLBACK"]
    G -->|Có| I["DML: INSERT đơn hàng"]
    I --> J{"Ghi đơn thành công?"}
    J -->|Không| H
    J -->|Có| K["TCL: COMMIT"]
    K --> L["Truy vấn: SELECT chi tiết đơn"]
~~~

Sơ đồ cho thấy vai trò của từng nhóm lệnh theo **thời điểm sử dụng**:

- **Thiết kế hoặc thay đổi mô hình dữ liệu:** dùng DDL, thường trong migration.
- **Lấy dữ liệu cho màn hình, API, báo cáo:** dùng truy vấn.
- **Tạo, sửa, xóa bản ghi theo sự kiện nghiệp vụ:** dùng DML.
- **Phối hợp nhiều lệnh ghi có yêu cầu cùng thành công:** dùng TCL và xử lý lỗi.
- **Cho phép từng tài khoản hoặc role thực hiện đúng tác vụ:** dùng DCL trong khâu cấu hình bảo mật/vận hành.

DDL và DCL thường xuất hiện ở quá trình triển khai/quản trị, trong khi truy vấn và DML xuất hiện thường xuyên trong luồng chạy ứng dụng. TCL chủ yếu bao quanh những đơn vị công việc cần tính nguyên tử. Đây là thói quen thiết kế, không phải giới hạn cứng của SQL.

## 8. Những nhầm lẫn dễ gặp

| Nhận định dễ nhầm | Hiểu đúng |
| --- | --- |
| “SQL chỉ là SELECT.” | SQL cũng mô tả schema, thay đổi dữ liệu, xử lý giao dịch và quyền truy cập. |
| “SELECT luôn là một nhóm độc lập với DML.” | “DQL” hữu ích khi học, nhưng một số tài liệu xếp `SELECT` trong phạm vi DML. |
| “DELETE và DROP TABLE giống nhau.” | `DELETE` xóa dòng; `DROP TABLE` xóa đối tượng bảng. |
| “UPDATE không có WHERE chỉ sửa một dòng.” | Nếu không có điều kiện, `UPDATE` có thể tác động tất cả dòng. |
| “Dùng transaction thì logic nghiệp vụ tự đúng.” | Transaction giữ ranh giới commit/rollback; ứng dụng vẫn phải kiểm tra điều kiện và ràng buộc. |
| “Có COMMIT là vẫn có thể ROLLBACK lúc nào cũng được.” | `ROLLBACK` chỉ hoàn tác phần chưa commit trong giao dịch hiện hành. |
| “GRANT SELECT giúp tài khoản có mọi quyền.” | `SELECT` chỉ là một quyền trên đối tượng; quyền ghi và quyền ở schema có thể tách biệt. |
| “Quy tắc transaction/DDL giống nhau ở mọi DBMS.” | Hành vi autocommit, implicit commit, isolation và cú pháp có khác biệt theo DBMS. |

## 9. Tự kiểm tra hiểu biết

Hãy thử xác định nhóm lệnh chính trước khi xem lời giải:

1. Cần bổ sung cột `mo_ta` cho bảng sản phẩm.
2. Cần hiển thị năm sản phẩm có giá cao nhất.
3. Cần tăng tồn kho của một sản phẩm thêm mười đơn vị.
4. Cần ghi đồng thời hóa đơn và dòng chi tiết hóa đơn; nếu một bước lỗi thì hủy cả hai.
5. Cần cho tài khoản phân tích được xem bảng doanh thu nhưng không được xóa dữ liệu.

**Đáp án gợi ý:**

1. **DDL** — `ALTER TABLE ... ADD COLUMN`.
2. **Truy vấn** — `SELECT ... ORDER BY gia DESC LIMIT 5` (ví dụ cú pháp PostgreSQL).
3. **DML** — `UPDATE ... SET ton_kho = ton_kho + 10 WHERE ...`.
4. **TCL kết hợp DML** — mở giao dịch, ghi các bảng bằng DML, `COMMIT` khi tất cả thành công hoặc `ROLLBACK` khi có lỗi.
5. **DCL** — cấp `SELECT` trên đúng bảng/view báo cáo cho role phân tích; không cấp quyền `DELETE`.

Điểm mấu chốt là mỗi nhóm SQL chịu trách nhiệm cho **một phần khác nhau của tính đúng đắn của hệ thống**: DDL tạo cấu trúc và ràng buộc; DML thay đổi dữ liệu; truy vấn biến dữ liệu thành kết quả đọc được; TCL kiểm soát ranh giới xác nhận thay đổi; DCL giới hạn quyền truy cập. Một ứng dụng quan hệ đáng tin cậy thường cần phối hợp cả năm.
