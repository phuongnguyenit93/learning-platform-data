# SQL là gì, giải quyết vấn đề nào và được dùng ở đâu?

Khi một ứng dụng chỉ có vài thông tin, ta có thể ghi chúng vào một tệp hoặc bảng tính. Nhưng hãy tưởng tượng một website bán hàng có hàng triệu khách hàng, đơn hàng liên tục được tạo, nhiều nhân viên cùng cập nhật trạng thái, và bộ phận kinh doanh cần xem doanh thu từng ngày. Lúc này, ứng dụng phải **lưu dữ liệu có tổ chức, tìm đúng thông tin, giữ dữ liệu nhất quán và cho nhiều người sử dụng đồng thời**.

**SQL (Structured Query Language — ngôn ngữ truy vấn có cấu trúc)** là ngôn ngữ tiêu chuẩn được dùng để làm việc với dữ liệu trong các hệ quản trị cơ sở dữ liệu quan hệ. SQL giúp mô tả *dữ liệu nào cần lấy hoặc thay đổi*; hệ quản trị cơ sở dữ liệu chịu trách nhiệm thực hiện yêu cầu đó.

Sau bài này, bạn sẽ hiểu SQL là gì, cách SQL liên hệ với cơ sở dữ liệu quan hệ, những vấn đề thực tế mà SQL giải quyết, các câu lệnh cơ bản và những tình huống thường dùng SQL trong hệ thống phần mềm.

## 1. Phân biệt SQL, cơ sở dữ liệu và hệ quản trị cơ sở dữ liệu

Ba khái niệm thường đi cùng nhau nhưng có vai trò khác nhau:

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **Cơ sở dữ liệu (database)** | Tập hợp dữ liệu được tổ chức để lưu trữ và sử dụng | Dữ liệu khách hàng, đơn hàng, sản phẩm của một cửa hàng |
| **Hệ quản trị cơ sở dữ liệu (DBMS)** | Phần mềm quản lý việc lưu trữ, truy cập, cập nhật, bảo vệ và phục hồi dữ liệu | PostgreSQL, MySQL, SQLite, Microsoft SQL Server, Oracle Database |
| **SQL** | Ngôn ngữ gửi yêu cầu đến DBMS: tạo cấu trúc, đọc, thêm, sửa, xóa và kiểm soát dữ liệu | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `CREATE TABLE` |

Phần lớn các hệ quản trị vừa nêu là **hệ quản trị cơ sở dữ liệu quan hệ (RDBMS)**. Chúng tổ chức dữ liệu chủ yếu dưới dạng những **bảng (table)** gồm **cột (column)** và **hàng (row)**. Các bảng có thể liên kết với nhau thông qua khóa.

Ví dụ: bảng `khach_hang` lưu thông tin khách; bảng `don_hang` lưu đơn hàng và chứa mã khách tương ứng. Thay vì lặp lại tên, email của khách trong từng đơn, ứng dụng lưu mã khách để liên kết dữ liệu giữa hai bảng.

Luồng tương tác điển hình:

```text
Người dùng
   │ thao tác trên website/app
   ▼
Ứng dụng (ví dụ Java/Spring Boot)
   │ gửi câu lệnh SQL qua driver/kết nối cơ sở dữ liệu
   ▼
Hệ quản trị CSDL (PostgreSQL, MySQL, ...)
   │ kiểm tra quyền, lập kế hoạch và thực thi
   ▼
Các bảng dữ liệu được lưu trữ
   │ trả kết quả hoặc trạng thái thực hiện
   ▼
Ứng dụng hiển thị thông tin cho người dùng
```

**Điểm cần nhớ:** SQL không phải một cơ sở dữ liệu hay một chương trình máy chủ. SQL là ngôn ngữ; DBMS là phần mềm hiểu và thực thi ngôn ngữ ấy. PostgreSQL và MySQL đều dùng SQL, nhưng có thể khác nhau về cú pháp mở rộng, kiểu dữ liệu và tính năng.

## 2. SQL giải quyết những vấn đề nào?

### 2.1. Lưu trữ dữ liệu có cấu trúc và có liên hệ

Một hệ thống cần biết mỗi đơn hàng thuộc khách nào, mỗi dòng chi tiết đơn hàng thuộc đơn nào và sản phẩm nào. Khi tổ chức thành các bảng có khóa, dữ liệu dễ liên kết và kiểm soát hơn so với việc lưu một danh sách lớn chứa nhiều thông tin lặp lại.

Ví dụ quan hệ đơn giản:

```text
khach_hang                                don_hang
┌──────────┬───────┐                     ┌────────┬──────────┬───────────┐
│ ma_khach │ ten   │                     │ ma_don │ ma_khach │ tong_tien │
├──────────┼───────┤                     ├────────┼──────────┼───────────┤
│        1 │ An    │───┐                 │    101 │        1 │    120000 │
│        2 │ Bình  │   └───────────────► │    102 │        1 │     80000 │
│        3 │ Chi   │                     │    103 │        2 │    250000 │
└──────────┴───────┘                     │    104 │        3 │     50000 │
                                       └────────┴──────────┴───────────┘
```

`khach_hang.ma_khach` là **khóa chính (primary key)**, nhận diện duy nhất một khách hàng. `don_hang.ma_khach` là **khóa ngoại (foreign key)**, tham chiếu đến khách hàng đã tồn tại. Một khách hàng có thể có nhiều đơn hàng: đây là quan hệ **một–nhiều**.

### 2.2. Tìm, lọc và tổng hợp dữ liệu nhanh theo nhu cầu

Ứng dụng thường không cần đọc tất cả dữ liệu. Người dùng có thể hỏi:

- Những đơn hàng nào đã thanh toán?
- Đơn hàng của khách An có tổng giá trị bao nhiêu?
- Mỗi khách đã mua bao nhiêu đơn trong tháng?
- Sản phẩm nào có doanh thu cao nhất?

SQL cung cấp những phép toán như **lọc (`WHERE`)**, **sắp xếp (`ORDER BY`)**, **nối bảng (`JOIN`)** và **tổng hợp (`COUNT`, `SUM`, `AVG`, ...)**. DBMS lựa chọn cách thực thi dựa trên cấu trúc bảng, chỉ mục, thống kê và dữ liệu thực tế. Vì vậy, câu truy vấn đúng và thiết kế cơ sở dữ liệu phù hợp có thể xử lý lượng dữ liệu lớn mà ứng dụng không phải tải toàn bộ bảng về bộ nhớ để tự tính.

### 2.3. Bảo đảm tính toàn vẹn của dữ liệu

Một dữ liệu có ý nghĩa phải tuân theo các quy tắc. Ví dụ:

- Mỗi khách hàng có mã định danh riêng: `PRIMARY KEY`.
- Email không được trùng khi có giá trị: `UNIQUE`.
- Tên khách hàng bắt buộc phải có: `NOT NULL`.
- Tổng tiền không được âm: `CHECK (tong_tien >= 0)`.
- Đơn hàng phải tham chiếu đến một khách có thật: `FOREIGN KEY`.

Các **ràng buộc (constraints)** này được DBMS kiểm tra khi dữ liệu được ghi, giúp tránh sai lệch ngay cả khi có nhiều ứng dụng cùng kết nối. Ví dụ, nếu `ma_khach = 999` không tồn tại, một lệnh thêm đơn hàng tham chiếu đến mã đó sẽ bị từ chối khi ràng buộc khóa ngoại được thực thi.

### 2.4. Giữ nhiều thao tác liên quan được nhất quán

Trong chuyển tiền, trừ tiền ở tài khoản A nhưng chưa cộng vào tài khoản B là trạng thái sai. **Giao dịch (transaction)** cho phép nhóm nhiều thao tác thành một đơn vị: hoặc toàn bộ được xác nhận bằng `COMMIT`, hoặc thay đổi chưa xác nhận được hủy bằng `ROLLBACK`.

Các hệ quản trị quan hệ thường cung cấp những đặc tính **ACID** để hỗ trợ tính đúng đắn của giao dịch:

| Đặc tính | Ý nghĩa cơ bản |
|---|---|
| Atomicity — tính nguyên tử | Một giao dịch hoàn thành trọn vẹn hoặc được hủy |
| Consistency — tính nhất quán | Giao dịch hợp lệ duy trì các ràng buộc của dữ liệu |
| Isolation — tính cô lập | Các giao dịch đồng thời được kiểm soát để tránh can thiệp ngoài ý muốn |
| Durability — tính bền vững | Thay đổi đã được xác nhận được lưu bền vững theo bảo đảm của DBMS |

Mức cô lập, cơ chế khóa và hành vi khi có lỗi khác nhau giữa các DBMS và cấu hình. Giao dịch không tự sửa được mọi lỗi trong logic nghiệp vụ; ứng dụng vẫn cần thiết kế và xử lý lỗi đúng.

### 2.5. Phục vụ nhiều người dùng và bảo vệ quyền truy cập

Website bán hàng, ứng dụng ngân hàng hay hệ thống đặt vé có thể có nhiều người đọc và ghi dữ liệu cùng lúc. DBMS hỗ trợ quản lý kết nối, xử lý tranh chấp, giao dịch, sao lưu và phục hồi. SQL còn có các lệnh phân quyền như `GRANT` và `REVOKE` trong những DBMS hỗ trợ.

Ứng dụng không nên cho người dùng nhập câu SQL tùy ý hoặc ghép trực tiếp giá trị đầu vào vào câu lệnh. Khi nhận giá trị từ biểu mẫu hay API, nên dùng **truy vấn có tham số (parameterized query / prepared statement)** để hạn chế SQL injection, đồng thời cấp tài khoản DB quyền tối thiểu cần thiết.

## 3. Ví dụ từ đầu: quản lý khách hàng và đơn hàng bằng SQL

Các ví dụ dưới đây dùng cú pháp SQL thông dụng, có thể chạy với ít hoặc không cần chỉnh sửa trên nhiều RDBMS. Tên bảng/cột không dấu để dễ sử dụng trong môi trường lập trình. Để thực hành, hãy chạy các lệnh theo thứ tự trong một cơ sở dữ liệu thử nghiệm.

### 3.1. Tạo bảng và xác định mối quan hệ

```sql
CREATE TABLE khach_hang (
    ma_khach INTEGER PRIMARY KEY,
    ten VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE
);

CREATE TABLE don_hang (
    ma_don INTEGER PRIMARY KEY,
    ma_khach INTEGER NOT NULL,
    tong_tien DECIMAL(12, 2) NOT NULL CHECK (tong_tien >= 0),
    trang_thai VARCHAR(30) NOT NULL,
    FOREIGN KEY (ma_khach) REFERENCES khach_hang(ma_khach)
);
```

`CREATE TABLE` định nghĩa **schema** (cấu trúc bảng), kiểu dữ liệu và ràng buộc. Cột `tong_tien` dùng `DECIMAL` để biểu diễn số tiền chính xác theo chữ số thập phân, tránh sai số nhị phân của kiểu số thực dấu phẩy động. Ví dụ này tập trung vào hai bảng; hệ thống thực tế còn cần bảng sản phẩm, chi tiết đơn, thanh toán, lịch sử trạng thái, v.v.

### 3.2. Thêm dữ liệu

```sql
INSERT INTO khach_hang (ma_khach, ten, email)
VALUES
    (1, 'An',   'an@example.com'),
    (2, 'Bình', 'binh@example.com'),
    (3, 'Chi',  'chi@example.com');

INSERT INTO don_hang (ma_don, ma_khach, tong_tien, trang_thai)
VALUES
    (101, 1, 120000, 'DA_THANH_TOAN'),
    (102, 1,  80000, 'CHO_THANH_TOAN'),
    (103, 2, 250000, 'DA_THANH_TOAN'),
    (104, 3,  50000, 'DA_THANH_TOAN');
```

`INSERT INTO` thêm hàng mới. Mỗi đơn hàng dùng `ma_khach` để chỉ ra khách sở hữu; không phải sao chép tên và email khách sang bảng đơn hàng.

### 3.3. Đọc và lọc dữ liệu

```sql
SELECT ma_don, ma_khach, tong_tien
FROM don_hang
WHERE trang_thai = 'DA_THANH_TOAN'
ORDER BY tong_tien DESC;
```

Kết quả dự kiến với dữ liệu trên:

| ma_don | ma_khach | tong_tien |
|---:|---:|---:|
| 103 | 2 | 250000.00 |
| 101 | 1 | 120000.00 |
| 104 | 3 | 50000.00 |

- `SELECT` chỉ định các cột cần lấy; `FROM` chỉ định bảng nguồn.
- `WHERE` giữ lại các hàng thỏa điều kiện; `=` so sánh giá trị, còn `AND`/`OR` kết hợp điều kiện.
- `ORDER BY ... DESC` sắp xếp từ lớn đến nhỏ (`ASC` là tăng dần).

SQL là ngôn ngữ **khai báo (declarative)**: câu lệnh nêu kết quả mong muốn, còn DBMS quyết định nên đọc bảng, dùng chỉ mục và thực hiện các phép toán theo thứ tự nào để trả kết quả.

### 3.4. Kết hợp hai bảng bằng `JOIN`

```sql
SELECT k.ten, d.ma_don, d.tong_tien
FROM khach_hang AS k
JOIN don_hang AS d ON d.ma_khach = k.ma_khach
WHERE d.trang_thai = 'DA_THANH_TOAN'
ORDER BY d.ma_don;
```

| ten | ma_don | tong_tien |
|---|---:|---:|
| An | 101 | 120000.00 |
| Bình | 103 | 250000.00 |
| Chi | 104 | 50000.00 |

`k` và `d` là **bí danh bảng (alias)**. `JOIN ... ON` ghép các hàng có cùng mã khách. Trong ví dụ này, `JOIN` mặc định là `INNER JOIN`: chỉ các cặp hàng khớp nhau được trả về. Khi cần giữ cả khách chưa có đơn, có thể tìm hiểu `LEFT JOIN` ở bài về nối bảng.

### 3.5. Thống kê bằng `GROUP BY`

```sql
SELECT
    k.ten,
    COUNT(*) AS so_don_da_thanh_toan,
    SUM(d.tong_tien) AS tong_da_chi
FROM khach_hang AS k
JOIN don_hang AS d ON d.ma_khach = k.ma_khach
WHERE d.trang_thai = 'DA_THANH_TOAN'
GROUP BY k.ma_khach, k.ten
ORDER BY tong_da_chi DESC;
```

| ten | so_don_da_thanh_toan | tong_da_chi |
|---|---:|---:|
| Bình | 1 | 250000.00 |
| An | 1 | 120000.00 |
| Chi | 1 | 50000.00 |

`GROUP BY` gom các hàng theo khóa nhóm; `COUNT(*)` đếm số hàng trong nhóm, `SUM` cộng tổng tiền. Điều kiện `WHERE` được áp dụng **trước** khi nhóm, nên đơn hàng đang chờ thanh toán không góp vào tổng. Kết quả này là một dạng dữ liệu báo cáo, không cần viết vòng lặp qua từng đơn hàng trong ứng dụng.

### 3.6. Cập nhật và xóa dữ liệu

Giả sử đơn 102 vừa được thanh toán:

```sql
UPDATE don_hang
SET trang_thai = 'DA_THANH_TOAN'
WHERE ma_don = 102;
```

Nếu cần xóa một đơn thử nghiệm đã được xác định đúng:

```sql
DELETE FROM don_hang
WHERE ma_don = 102;
```

Hai lệnh này minh họa hai **thao tác độc lập**: sau `UPDATE`, hãy kiểm tra dữ liệu trước khi quyết định có thực hiện ví dụ `DELETE` hay không. Trong môi trường thật, nhiều nghiệp vụ giữ lịch sử đơn hàng và dùng trạng thái hủy thay vì xóa vật lý. **Luôn cân nhắc điều kiện `WHERE` khi dùng `UPDATE`/`DELETE`**: bỏ điều kiện có thể tác động lên toàn bộ bảng.

### 3.7. Nhóm thay đổi trong một giao dịch

Giả sử muốn cập nhật hai đơn trong cùng một lần xử lý và chỉ xác nhận khi cả hai thao tác thành công:

```sql
BEGIN;

UPDATE don_hang
SET trang_thai = 'DA_THANH_TOAN'
WHERE ma_don = 101;

UPDATE don_hang
SET trang_thai = 'DA_THANH_TOAN'
WHERE ma_don = 102;

COMMIT;
```

Nếu xảy ra lỗi **trước khi `COMMIT`**, ứng dụng có thể dùng `ROLLBACK` để hủy các thay đổi chưa xác nhận. Lưu ý: câu lệnh bắt đầu giao dịch và hành vi tự động xác nhận có thể khác theo DBMS và công cụ đang sử dụng (ví dụ, một số hệ dùng `START TRANSACTION`); hãy kiểm tra chế độ transaction/autocommit của môi trường thực hành.

## 4. Những nhóm câu lệnh SQL thường gặp

| Nhóm thường gọi | Mục đích | Câu lệnh tiêu biểu |
|---|---|---|
| **DDL** — Data Definition Language | Định nghĩa hoặc thay đổi cấu trúc đối tượng cơ sở dữ liệu | `CREATE`, `ALTER`, `DROP` |
| **DML** — Data Manipulation Language | Thêm, cập nhật, xóa dữ liệu | `INSERT`, `UPDATE`, `DELETE` |
| **DQL** — Data Query Language | Truy vấn dữ liệu (cách phân nhóm phổ biến trong tài liệu nhập môn) | `SELECT` |
| **TCL** — Transaction Control Language | Điều khiển giao dịch | `COMMIT`, `ROLLBACK`, `SAVEPOINT` |
| **DCL** — Data Control Language | Quản lý quyền truy cập | `GRANT`, `REVOKE` |

Đây là **cách phân loại phục vụ học tập**, không phải mọi tài liệu hay DBMS đều dùng ranh giới nhóm hoàn toàn giống nhau. Khi mới học, `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `CREATE TABLE`, `JOIN` và `GROUP BY` là các thành phần cần hiểu trước.

## 5. SQL được sử dụng ở đâu?

| Bối cảnh | Dữ liệu thường lưu | Truy vấn/nghiệp vụ tiêu biểu |
|---|---|---|
| **Thương mại điện tử** | Khách hàng, sản phẩm, kho hàng, đơn hàng | Tìm đơn theo khách, cập nhật tồn kho, thống kê doanh thu |
| **Ngân hàng và tài chính** | Tài khoản, số dư, giao dịch, lịch sử thanh toán | Tra cứu giao dịch, ghi nhận thay đổi theo giao dịch nhất quán |
| **Đặt chỗ và vận chuyển** | Chuyến đi, vé, vị trí, lịch trình | Kiểm tra chỗ trống, đặt chỗ, theo dõi đơn giao hàng |
| **Giáo dục** | Học viên, khóa học, đăng ký, kết quả | Liệt kê học viên của một lớp, tính điểm trung bình |
| **Y tế và hành chính** | Hồ sơ, lịch hẹn, hóa đơn | Tra cứu hồ sơ theo quyền được cấp, tạo báo cáo |
| **Phân tích dữ liệu, BI và data warehouse** | Dữ liệu tổng hợp từ nhiều nguồn | Tổng doanh thu theo tháng, phân khúc khách hàng, dashboard |
| **Ứng dụng desktop/mobile và thiết bị** | Dữ liệu cục bộ, bộ nhớ đệm, danh mục | Đọc/ghi dữ liệu tại máy bằng cơ sở dữ liệu nhúng như SQLite |

Trong hệ thống backend, SQL thường nằm **sau lớp API hoặc dịch vụ**. Ví dụ, người dùng gọi API `GET /orders?status=paid`; chương trình Java nhận yêu cầu, kiểm tra quyền truy cập, tạo truy vấn có tham số, thực thi qua **JDBC**, một thư viện truy cập dữ liệu hoặc ORM như **JPA/Hibernate**, rồi trả kết quả JSON. ORM có thể sinh SQL thay cho lập trình viên, nhưng hiểu SQL vẫn cần để thiết kế dữ liệu, kiểm tra truy vấn, tối ưu hiệu năng và xử lý lỗi.

SQL còn được sử dụng trực tiếp bởi nhà phân tích dữ liệu trong các công cụ truy vấn và nền tảng phân tích. Ở đó, mục tiêu có thể là đọc và tổng hợp lượng dữ liệu lớn; ở ứng dụng giao dịch, mục tiêu thường là ghi nhận chính xác thay đổi của từng nghiệp vụ. Cùng là SQL nhưng cách thiết kế hệ thống và tối ưu có thể khác nhau.

## 6. SQL có phải lúc nào cũng là lựa chọn phù hợp nhất?

SQL đặc biệt hữu ích khi dữ liệu có cấu trúc tương đối rõ, có quan hệ giữa nhiều thực thể, cần truy vấn kết hợp, có ràng buộc dữ liệu và/hoặc có giao dịch quan trọng. Tuy nhiên, lựa chọn công nghệ lưu trữ còn phụ thuộc nhu cầu thực tế.

| Giải pháp | Phù hợp khi | Giới hạn cần cân nhắc |
|---|---|---|
| **Bảng tính (Excel/Google Sheets)** | Nhập và phân tích thủ công dữ liệu nhỏ, cộng tác đơn giản | Khó kiểm soát giao dịch, quan hệ và tải đồng thời của ứng dụng lớn |
| **Tệp JSON/CSV** | Trao đổi, xuất/nhập hoặc lưu cấu hình và dữ liệu đơn giản | Không tự cung cấp truy vấn quan hệ, chỉ mục và quản lý giao dịch như RDBMS |
| **RDBMS dùng SQL** | Hệ thống nghiệp vụ có bảng liên kết, truy vấn đa dạng và yêu cầu tính toàn vẹn | Cần thiết kế schema, vận hành và tối ưu phù hợp |
| **Cơ sở dữ liệu NoSQL** | Một số nhu cầu tài liệu linh hoạt, key–value, đồ thị hoặc phân tán chuyên biệt | Mô hình truy vấn, giao dịch và bảo đảm nhất quán tùy từng sản phẩm; không thể đánh đồng tất cả NoSQL |

"SQL hay NoSQL" không phải quyết định tuyệt đối. Một sản phẩm có thể dùng RDBMS cho đơn hàng, hệ tìm kiếm cho tìm kiếm văn bản và bộ nhớ đệm key–value cho dữ liệu truy cập thường xuyên. Một số hệ thống không quan hệ cũng hỗ trợ ngôn ngữ truy vấn giống SQL; ngược lại, các RDBMS hiện đại có thể lưu và truy vấn JSON.

Ngoài ra, **SQL không tự động làm mọi truy vấn nhanh**. Truy vấn thiếu điều kiện, nối bảng sai, chỉ mục không phù hợp hoặc thiết kế dữ liệu kém có thể gây tốn tài nguyên. Chỉ mục (index) giúp DBMS tìm một số dữ liệu nhanh hơn, nhưng chiếm dung lượng và có chi phí khi cập nhật. Tối ưu cần căn cứ dữ liệu, mẫu truy vấn và kế hoạch thực thi thực tế.

## 7. Những hiểu lầm thường gặp khi mới học SQL

**"SQL chỉ dùng để đọc dữ liệu."** Không đúng. Ngoài `SELECT`, SQL còn định nghĩa bảng, ghi thay đổi, điều khiển giao dịch và quản lý quyền theo tính năng DBMS.

**"Biết SQL tức là biết quản trị PostgreSQL/MySQL."** SQL là một phần quan trọng. Quản trị DBMS còn gồm cấu hình, sao lưu, phục hồi, giám sát, phân quyền, vận hành và xử lý sự cố.

**"Mọi hệ quản trị đều dùng SQL giống hệt nhau."** Có một phần cú pháp tiêu chuẩn chung, nhưng kiểu dữ liệu, cách phân trang (`LIMIT`, `FETCH FIRST`, ...), hàm xử lý ngày giờ, tự tăng khóa và những tính năng chuyên biệt có thể khác nhau. Khi dùng một DBMS cụ thể, hãy đối chiếu tài liệu của hệ đó.

**"Mỗi bảng SQL phải độc lập, không liên quan bảng khác."** Ngược lại, khả năng diễn tả quan hệ qua khóa và truy vấn `JOIN` là thế mạnh cốt lõi của mô hình quan hệ.

**"Dữ liệu trống luôn bằng chuỗi rỗng hoặc số 0."** Trong SQL, `NULL` biểu thị giá trị thiếu/chưa biết hoặc không áp dụng, khác với `''` và `0`. Muốn kiểm tra `NULL`, dùng `IS NULL` hoặc `IS NOT NULL`, không dùng `= NULL`.

**"Một câu lệnh `SELECT` luôn trả kết quả theo thứ tự được lưu."** Bảng quan hệ không bảo đảm thứ tự các hàng trong kết quả khi không có `ORDER BY`. Nếu giao diện yêu cầu thứ tự ổn định, câu truy vấn phải quy định cách sắp xếp phù hợp.

## 8. Từ nhận diện bài toán đến viết truy vấn

Khi đối mặt một yêu cầu dữ liệu, có thể suy nghĩ theo trình tự sau:

1. **Xác định đối tượng**: hệ thống quản lý khách hàng, đơn hàng, sản phẩm hay thông tin gì?
2. **Xác định thuộc tính và quan hệ**: mỗi đối tượng cần cột nào, khóa chính gì và liên kết đến đối tượng nào?
3. **Xác định quy tắc đúng đắn**: giá trị bắt buộc, duy nhất, quan hệ hợp lệ, thao tác nào cần chung giao dịch?
4. **Diễn đạt câu hỏi dữ liệu**: cần lấy cột nào (`SELECT`), từ bảng nào (`FROM`/`JOIN`), lọc ra sao (`WHERE`), có cần thống kê (`GROUP BY`) hoặc sắp xếp (`ORDER BY`)?
5. **Đặt trong ngữ cảnh ứng dụng**: ai được phép xem/sửa, có dữ liệu đầu vào nào cần tham số hóa, kết quả sẽ được hiển thị hay dùng để xử lý nghiệp vụ?

Ví dụ câu hỏi *"Khách hàng nào đã có đơn thanh toán trên 100.000 đồng?"* có thể chuyển thành truy vấn:

```sql
SELECT DISTINCT k.ma_khach, k.ten
FROM khach_hang AS k
JOIN don_hang AS d ON d.ma_khach = k.ma_khach
WHERE d.trang_thai = 'DA_THANH_TOAN'
  AND d.tong_tien > 100000
ORDER BY k.ma_khach;
```

Với dữ liệu ban đầu, kết quả là **An** và **Bình**. `DISTINCT` giúp mỗi khách chỉ xuất hiện một lần ngay cả khi họ có nhiều đơn thỏa điều kiện. Đây là tư duy nền tảng khi học SQL: chuyển một câu hỏi nghiệp vụ thành thao tác trên các tập dữ liệu có cấu trúc.

## 9. Tự kiểm tra kiến thức

**Câu 1.** Một cơ sở dữ liệu lưu khách hàng và đơn hàng. Vì sao nên để đơn hàng tham chiếu đến mã khách thay vì chép lại toàn bộ tên và email trong mọi đơn?

Gợi ý: nghĩ đến thông tin trùng lặp, việc sửa email và khả năng bảo đảm đơn hàng thuộc một khách hợp lệ.

**Câu 2.** Một cửa hàng muốn hiển thị các đơn chưa thanh toán theo tổng tiền giảm dần. Trong `SELECT`, bạn sẽ kết hợp những mệnh đề nào?

Gợi ý: `FROM don_hang`, `WHERE trang_thai = 'CHO_THANH_TOAN'`, `ORDER BY tong_tien DESC`.

**Câu 3.** Một thao tác gồm trừ tồn kho và tạo bản ghi thanh toán. Nếu bước thứ hai thất bại, cơ chế nào giúp tránh chỉ thực hiện một nửa thay đổi?

Đáp án định hướng: đặt các thay đổi cần nhất quán trong một **transaction** và xử lý `COMMIT`/`ROLLBACK` đúng cách, đồng thời kiểm soát lỗi và truy cập đồng thời.

**Câu 4.** Java/Spring Boot gửi `SELECT` đến PostgreSQL; trong ba thành phần *ứng dụng, SQL, PostgreSQL*, thành phần nào thực thi truy vấn và quản lý dữ liệu?

Đáp án: **PostgreSQL** là DBMS thực thi SQL và quản lý dữ liệu. Ứng dụng gửi yêu cầu và xử lý kết quả; SQL là ngôn ngữ của yêu cầu đó.

## Kết luận

SQL là ngôn ngữ cốt lõi để **định nghĩa, truy vấn và thay đổi dữ liệu có cấu trúc** trong cơ sở dữ liệu quan hệ. SQL giúp các ứng dụng tìm thông tin, kết hợp nhiều bảng, lập báo cáo, áp dụng ràng buộc và phối hợp thay đổi qua giao dịch. Nó xuất hiện trong backend, hệ thống nghiệp vụ, báo cáo, phân tích dữ liệu và cả cơ sở dữ liệu nhúng.

Điểm bắt đầu quan trọng nhất là phân biệt **ngôn ngữ SQL** với **phần mềm DBMS**, hiểu dữ liệu được tổ chức thành **bảng, hàng, cột và khóa**, rồi tập diễn đạt câu hỏi thực tế bằng `SELECT`, `WHERE`, `JOIN` và `GROUP BY`. Các bài tiếp theo có thể đi sâu vào thiết kế bảng, truy vấn nâng cao, giao dịch, chỉ mục và tối ưu hiệu năng.
