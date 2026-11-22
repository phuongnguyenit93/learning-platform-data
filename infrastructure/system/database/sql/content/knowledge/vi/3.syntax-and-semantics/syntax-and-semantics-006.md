# Bí danh bảng, bí danh cột và thời điểm có thể sử dụng trong SQL

> **Chủ đề:** Database SQL → Cú pháp và ngữ nghĩa  
> **Trọng tâm:** Hiểu hai loại bí danh (alias) trong SQL, phạm vi nhìn thấy của chúng và lý do một bí danh dùng được ở mệnh đề này nhưng có thể bị từ chối ở mệnh đề khác.

## 1. Mục tiêu bài học

Sau khi học, bạn có thể:

- Phân biệt **bí danh bảng (table alias)** với **bí danh cột (column alias)** và biết chúng có thay đổi cấu trúc dữ liệu thật hay không.
- Đặt bí danh bằng cú pháp rõ ràng, dùng bí danh để viết JOIN, truy vấn tự nối bảng, truy vấn con và báo cáo.
- Giải thích được **thời điểm** và **phạm vi** một bí danh có thể được tham chiếu: FROM, JOIN ... ON, WHERE, GROUP BY, HAVING, SELECT và ORDER BY.
- Nhận diện lỗi dùng bí danh cột quá sớm, xung đột tên, bí danh ngoài phạm vi và khác biệt giữa các phương ngữ SQL.
- Biết viết lại truy vấn bằng biểu thức gốc, truy vấn con hoặc CTE khi cần sử dụng lại kết quả đã đặt tên.
- Phân biệt thứ tự **xử lý logic** của câu truy vấn với thứ tự thực thi vật lý mà bộ tối ưu truy vấn có thể chọn.

## 2. Bí danh (alias) là gì?

**Bí danh** là tên tạm thời mà người viết SQL đặt cho một bảng, nguồn dữ liệu trung gian hoặc biểu thức cột **trong phạm vi một câu truy vấn**.

Hãy hình dung bảng lưu trong cơ sở dữ liệu có tên đầy đủ là **khach_hang**, nhưng khi JOIN nhiều bảng bạn muốn gọi ngắn gọn là **k**. Hoặc cột **tong_tien** được tính thành một chỉ số báo cáo có tên **doanh_thu**. Đó là hai ứng dụng khác nhau của alias.

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang AS ten_hien_thi
FROM khach_hang AS k;
~~~

Ở đây:

- **k** là bí danh bảng cho **khach_hang**.
- **ten_hien_thi** là bí danh cột cho biểu thức **k.ten_khach_hang**.
- **AS** thể hiện rõ ý định đặt bí danh.
- Truy vấn không đổi tên bảng **khach_hang** hoặc cột **ten_khach_hang** trong cơ sở dữ liệu.

**Bí danh khác với đổi tên dữ liệu thật.** Việc đổi tên bảng/cột trong lược đồ thường cần DDL như ALTER TABLE, với cú pháp theo từng hệ quản trị; còn alias chỉ có ý nghĩa trong câu SQL hoặc đối tượng truy vấn mà nó được định nghĩa.

### 2.1. Mô hình dữ liệu dùng xuyên suốt

Giả sử cơ sở dữ liệu bán hàng có:

**Bảng khach_hang**

| ma_khach_hang | ten_khach_hang | thanh_pho |
|---:|---|---|
| 1 | An | Hà Nội |
| 2 | Bình | TP.HCM |
| 3 | Chi | Đà Nẵng |

**Bảng don_hang**

| ma_don_hang | ma_khach_hang | trang_thai | tong_tien |
|---:|---:|---|---:|
| 101 | 1 | PAID | 200000 |
| 102 | 1 | CANCELLED | 900000 |
| 103 | 2 | PAID | 300000 |
| 104 | 2 | PAID | 100000 |

Các giá trị chỉ phục vụ ví dụ; không cần tạo dữ liệu trong hệ quản trị thật để hiểu bài. Khách hàng Chi chưa có đơn hàng.

## 3. Bí danh bảng: đặt tên cho một nguồn dữ liệu trong FROM

### 3.1. Cú pháp cơ bản

Hai cách viết thường gặp là:

~~~sql
SELECT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang AS k;
~~~

~~~sql
SELECT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang k;
~~~

Khi truy vấn nhiều bảng, người ta thường chọn bí danh ngắn, dễ hiểu:

~~~sql
SELECT
    k.ten_khach_hang,
    d.ma_don_hang,
    d.tong_tien
FROM khach_hang k
JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang;
~~~

**k** chỉ hàng hiện xét từ bảng khách hàng; **d** chỉ hàng từ bảng đơn hàng. Việc ghi **d.ma_khach_hang = k.ma_khach_hang** cho biết rõ hai cột cùng tên thuộc hai nguồn khác nhau.

Một số DBMS có khác biệt về từ khóa AS khi đặt bí danh bảng. Chẳng hạn Oracle Database ở các phiên bản truyền thống dùng dạng **FROM khach_hang k**; PostgreSQL, MySQL, SQL Server và SQLite thường chấp nhận cả **FROM khach_hang AS k**. Khi muốn viết SQL đa hệ, phải kiểm tra DBMS và phiên bản mục tiêu, đặc biệt với cú pháp DDL hoặc DML.

### 3.2. Dùng tên bảng gốc sau khi đã đặt bí danh?

Xem truy vấn:

~~~sql
SELECT khach_hang.ten_khach_hang
FROM khach_hang k;
~~~

Ở nhiều DBMS, truy vấn này lỗi vì **khach_hang** trong FROM đã được khai báo với tên tham chiếu **k**. Từ thời điểm đó, phần còn lại của query block phải tham chiếu nguồn tương ứng qua **k**.

Cách viết đúng và nhất quán:

~~~sql
SELECT k.ten_khach_hang
FROM khach_hang k;
~~~

Điều này không có nghĩa bảng vật lý đổi tên. Chỉ có **tên được dùng để tham chiếu nguồn trong query block** đã thay đổi.

**Quy tắc thực hành:** một khi đã khai báo alias cho bảng, hãy dùng alias đó nhất quán để định tính mọi cột cần làm rõ.

### 3.3. Khi nào dùng alias bảng?

Bí danh bảng đặc biệt có ích khi:

- JOIN nhiều bảng có tên cột giống nhau, ví dụ **ma_khach_hang** xuất hiện ở cả hai bảng.
- Cần viết SQL gọn mà vẫn rõ nguồn của từng cột.
- Một bảng xuất hiện nhiều lần trong cùng truy vấn, chẳng hạn bảng nhân viên liên kết với chính nó.
- Dùng bảng dẫn xuất (derived table), CTE hoặc truy vấn có tương quan (correlated subquery).

Kể cả khi chỉ đọc một bảng, dùng alias vẫn hợp lệ:

~~~sql
SELECT k.*
FROM khach_hang k
WHERE k.thanh_pho = 'Hà Nội';
~~~

**k.\*** chọn các cột từ nguồn k. Trong dự án thật, liệt kê rõ các cột cần thiết thường dễ duy trì hơn dùng SELECT * vì cấu trúc bảng có thể thay đổi.

## 4. Bí danh cột: đặt tên cho giá trị kết quả

### 4.1. Đổi tiêu đề cột đầu ra

~~~sql
SELECT
    ma_khach_hang AS ma,
    ten_khach_hang AS ho_ten,
    thanh_pho AS dia_chi_thanh_pho
FROM khach_hang;
~~~

Kết quả sẽ có tên cột đầu ra là **ma**, **ho_ten**, **dia_chi_thanh_pho**. Các cột gốc trong bảng vẫn giữ tên cũ.

Nhiều DBMS cho phép bỏ AS:

~~~sql
SELECT
    ma_khach_hang ma,
    ten_khach_hang ho_ten
FROM khach_hang;
~~~

Tuy nhiên, **AS** giúp người đọc phân biệt alias với các thành phần khác của biểu thức và thường là lựa chọn rõ ràng khi viết bí danh cột.

### 4.2. Đặt tên cho biểu thức tính toán

~~~sql
SELECT
    d.ma_don_hang,
    d.tong_tien,
    d.tong_tien * 0.10 AS phi_dich_vu,
    d.tong_tien * 1.10 AS tong_sau_phi
FROM don_hang d;
~~~

Tên **phi_dich_vu** và **tong_sau_phi** là tên cột trong kết quả. Không có cột vật lý nào tự động được thêm vào bảng **don_hang**.

### 4.3. Đặt tên cho giá trị tổng hợp

~~~sql
SELECT
    d.ma_khach_hang,
    COUNT(*) AS so_don_hang,
    SUM(d.tong_tien) AS tong_gia_tri
FROM don_hang d
WHERE d.trang_thai = 'PAID'
GROUP BY d.ma_khach_hang;
~~~

Kết quả theo dữ liệu ví dụ:

| ma_khach_hang | so_don_hang | tong_gia_tri |
|---:|---:|---:|
| 1 | 1 | 200000 |
| 2 | 2 | 400000 |

Đặt alias cho các biểu thức tổng hợp giúp lớp ứng dụng hoặc màn hình báo cáo đọc kết quả dễ hơn. Nhưng **tên đầu ra không tự động trở thành một biến có thể gọi ở mọi mệnh đề bên trong cùng query block**.

## 5. “Thời điểm có thể sử dụng” nghĩa là gì?

SQL là **ngôn ngữ khai báo**: người viết mô tả kết quả mong muốn; DBMS quyết định cách lấy dữ liệu. Vì vậy, thứ tự chữ viết trong câu lệnh không đồng nghĩa với thứ tự xử lý logic.

Ví dụ, **SELECT** xuất hiện đầu câu, nhưng về mặt mô hình logic, DBMS cần xác định nguồn dữ liệu và lọc dòng trước khi có danh sách cột kết quả.

Một trình tự tư duy thường dùng là:

~~~text
1. FROM: xác định nguồn dữ liệu, bí danh bảng
2. JOIN / ON: kết hợp nguồn, xét điều kiện nối
3. WHERE: lọc từng dòng trước khi gom nhóm
4. GROUP BY: phân chia nhóm
5. HAVING: lọc nhóm
6. SELECT: tạo các biểu thức và tên cột đầu ra
7. DISTINCT: loại dòng kết quả trùng lặp (nếu có)
8. ORDER BY: sắp xếp kết quả
9. OFFSET / FETCH hoặc LIMIT: bỏ qua, giới hạn số dòng (nếu có)
~~~

Đây là **mô hình xử lý logic để hiểu phạm vi tham chiếu** chứ không phải mô tả từng thao tác vật lý của động cơ truy vấn. Hàm cửa sổ (window function), các thao tác tập hợp như UNION, truy vấn con và từng phương ngữ có quy tắc chi tiết riêng; bộ tối ưu có thể đổi thứ tự tính toán nội bộ miễn vẫn đáp ứng ngữ nghĩa của câu lệnh.

**Hệ quả quan trọng:**

- **Bí danh bảng** được khai báo trong FROM, nên có thể dùng ở những mệnh đề tiếp theo thuộc phạm vi của nguồn đó, như ON, WHERE, GROUP BY, HAVING, SELECT và ORDER BY.
- **Bí danh cột** được tạo cho đầu ra của SELECT. Trong cùng query block, nó thường dùng được trong ORDER BY, nhưng **không thể mặc nhiên sử dụng ở WHERE, JOIN ... ON, GROUP BY, HAVING hoặc biểu thức SELECT khác**.
- Các DBMS có **phần mở rộng** cho phép dùng alias cột ở một số mệnh đề sớm hơn. Những phần mở rộng này cần được xem là hành vi theo phương ngữ, không nên dùng khi yêu cầu khả chuyển.

### 5.1. Bảng ghi nhớ nhanh

| Mệnh đề | Dùng bí danh bảng đã khai báo và đang trong phạm vi? | Dùng bí danh cột từ chính SELECT? |
|---|---|---|
| FROM | Khai báo tại đây; có quy tắc riêng giữa các nguồn cùng FROM | Không |
| JOIN ... ON | Có, với các nguồn nằm trong phạm vi của JOIN đang xét | Thông thường không |
| WHERE | Có | Thông thường không |
| GROUP BY | Có | Tùy DBMS/phiên bản; không giả định được |
| HAVING | Có | Tùy DBMS; không giả định được |
| SELECT | Có | Thông thường không dùng alias vừa khai báo để tính cột khác cùng danh sách |
| ORDER BY | Có | Có, nếu là tên đầu ra không gây xung đột và phù hợp cú pháp DBMS |
| Truy vấn ngoài bao truy vấn con | Chỉ thấy các cột/nguồn được đưa ra từ truy vấn con | Có thể dùng như tên cột của nguồn truy vấn con |

Chú ý cụm **“cùng query block”**. Một alias cột không dùng được ở WHERE của chính SELECT có thể dùng bình thường ở WHERE của **truy vấn bao ngoài**, sau khi kết quả truy vấn bên trong trở thành một nguồn dữ liệu.

## 6. Vì sao alias cột thường không dùng trong WHERE?

Đây là lỗi rất thường gặp:

~~~sql
-- Thường lỗi: tong_sau_phi chưa phải tên cột đầu vào của WHERE.
SELECT
    d.ma_don_hang,
    d.tong_tien * 1.10 AS tong_sau_phi
FROM don_hang d
WHERE tong_sau_phi >= 330000;
~~~

**WHERE** lọc dòng ở mô hình logic trước khi các alias đầu ra của SELECT được xác định. PostgreSQL, MySQL, SQL Server và Oracle Database thông thường không cho phép tham chiếu alias SELECT kiểu này.

Có ít nhất ba cách viết lại hợp lệ theo ý định.

### Cách 1: Lặp lại biểu thức ở WHERE

~~~sql
SELECT
    d.ma_don_hang,
    d.tong_tien * 1.10 AS tong_sau_phi
FROM don_hang d
WHERE d.tong_tien * 1.10 >= 330000;
~~~

Dễ hiểu với biểu thức ngắn. Tuy nhiên, nếu biểu thức phức tạp, việc lặp lại làm mã khó bảo trì; đặc biệt không nên lặp máy móc các biểu thức không có tính ổn định hoặc có tác động phụ.

### Cách 2: Dùng bảng dẫn xuất (derived table)

~~~sql
SELECT
    x.ma_don_hang,
    x.tong_sau_phi
FROM (
    SELECT
        d.ma_don_hang,
        d.tong_tien * 1.10 AS tong_sau_phi
    FROM don_hang d
) x
WHERE x.tong_sau_phi >= 330000;
~~~

Ở query block **bên trong**, **tong_sau_phi** là alias cột đầu ra. Khi cả kết quả bên trong trở thành nguồn **x** trong FROM của query block **bên ngoài**, **x.tong_sau_phi** đã là một cột đầu vào hợp lệ đối với WHERE bên ngoài.

### Cách 3: Dùng CTE (Common Table Expression)

~~~sql
WITH gia_tri_sau_phi AS (
    SELECT
        d.ma_don_hang,
        d.tong_tien * 1.10 AS tong_sau_phi
    FROM don_hang d
)
SELECT
    g.ma_don_hang,
    g.tong_sau_phi
FROM gia_tri_sau_phi g
WHERE g.tong_sau_phi >= 330000;
~~~

CTE giúp đặt tên cho tập kết quả trung gian, thuận tiện khi truy vấn có nhiều bước. **Tên CTE** và **alias cột bên trong CTE** là hai khái niệm liên quan nhưng không đồng nhất: CTE tạo một nguồn dữ liệu có thể tham chiếu từ query block tiếp theo.

**Đừng hiểu CTE luôn thực thi hoặc lưu dữ liệu trung gian trước rồi mới tới truy vấn ngoài.** Bộ tối ưu có thể inline, vật chất hóa hoặc lập kế hoạch khác nhau theo DBMS và phiên bản. CTE ở đây chủ yếu giúp diễn đạt phạm vi tên một cách rõ ràng.

### Một ngoại lệ dễ gây nhầm: SQLite

SQLite cho phép tham chiếu alias SELECT trong WHERE và một số biểu thức ON như một phần mở rộng, nhưng đây không phải cách viết SQL có tính khả chuyển cao. Nếu tên alias trùng tên cột gốc, quy tắc phân giải tên còn có thể khiến kết quả bất ngờ. Với bài SQL đa DBMS, hãy dùng biểu thức gốc hoặc truy vấn con/CTE như trên.

## 7. GROUP BY: alias cột có thể dùng hay không?

Xét yêu cầu chia các đơn hàng thành hai nhóm theo giá trị rồi đếm số đơn ở từng nhóm.

Một cách viết dễ đọc nhưng **phụ thuộc phương ngữ** là:

~~~sql
SELECT
    CASE
        WHEN d.tong_tien >= 300000 THEN 'LON'
        ELSE 'NHO'
    END AS nhom_gia,
    COUNT(*) AS so_don
FROM don_hang d
GROUP BY nhom_gia;
~~~

Một số DBMS, ví dụ PostgreSQL và MySQL ở các phiên bản phổ biến, chấp nhận GROUP BY theo alias cột. Nhưng SQL Server và Oracle Database ở các phiên bản cũ như Oracle 19c không cho phép cách tham chiếu này trong GROUP BY. Các bản Oracle mới hơn có bổ sung hỗ trợ nhất định; cần đối chiếu phiên bản thực tế.

Để giảm phụ thuộc, lặp lại **biểu thức phân nhóm**:

~~~sql
SELECT
    CASE
        WHEN d.tong_tien >= 300000 THEN 'LON'
        ELSE 'NHO'
    END AS nhom_gia,
    COUNT(*) AS so_don
FROM don_hang d
GROUP BY
    CASE
        WHEN d.tong_tien >= 300000 THEN 'LON'
        ELSE 'NHO'
    END;
~~~

Trong tình huống biểu thức dài, có thể tính nó ở một query block trước rồi nhóm ở query block ngoài:

~~~sql
WITH don_duoc_phan_nhom AS (
    SELECT
        d.ma_don_hang,
        CASE
            WHEN d.tong_tien >= 300000 THEN 'LON'
            ELSE 'NHO'
        END AS nhom_gia
    FROM don_hang d
)
SELECT
    x.nhom_gia,
    COUNT(*) AS so_don
FROM don_duoc_phan_nhom x
GROUP BY x.nhom_gia
ORDER BY x.nhom_gia;
~~~

Với dữ liệu mẫu, nhóm **LON** có hai đơn (102, 103); nhóm **NHO** có hai đơn (101, 104). Nếu muốn chỉ đếm đơn thanh toán, phải thêm WHERE trạng thái **PAID** trong CTE; điều kiện này thuộc yêu cầu nghiệp vụ, không phải quy tắc alias.

### GROUP BY theo vị trí cột

Có DBMS cho phép:

~~~sql
SELECT
    d.ma_khach_hang,
    COUNT(*) AS so_don
FROM don_hang d
GROUP BY 1;
~~~

Ở đây, số **1** có thể được hiểu là biểu thức thứ nhất trong danh sách SELECT, nhưng **không phải mọi hệ** đều cho cách này, và ý nghĩa của số có thể khác theo sản phẩm. Ngoài vấn đề khả chuyển, thêm hoặc đổi thứ tự cột SELECT sẽ làm GROUP BY dễ bị sai. Với nội dung cần bảo trì, ưu tiên tên cột hoặc biểu thức rõ ràng.

## 8. HAVING: alias tổng hợp không luôn dùng được

**HAVING** lọc **nhóm** sau GROUP BY trong mô hình logic. Câu hỏi thường gặp là liệu có thể dùng alias **so_don** tại HAVING hay không.

~~~sql
-- Phụ thuộc DBMS: có hệ không chấp nhận so_don ở HAVING.
SELECT
    d.ma_khach_hang,
    COUNT(*) AS so_don
FROM don_hang d
GROUP BY d.ma_khach_hang
HAVING so_don >= 2;
~~~

MySQL và SQLite có những trường hợp cho phép dùng alias đầu ra trong HAVING. PostgreSQL, SQL Server và nhiều phiên bản Oracle không cho phép cách này trong một truy vấn thông thường.

Để viết rộng rãi hơn, dùng hàm tổng hợp trực tiếp:

~~~sql
SELECT
    d.ma_khach_hang,
    COUNT(*) AS so_don
FROM don_hang d
GROUP BY d.ma_khach_hang
HAVING COUNT(*) >= 2;
~~~

Nếu nghiệp vụ cần lọc một kết quả tổng hợp nhiều bước, có thể đặt phép nhóm ở CTE rồi lọc alias ở WHERE của query block bên ngoài:

~~~sql
WITH thong_ke_khach AS (
    SELECT
        d.ma_khach_hang,
        COUNT(*) AS so_don
    FROM don_hang d
    GROUP BY d.ma_khach_hang
)
SELECT t.ma_khach_hang, t.so_don
FROM thong_ke_khach t
WHERE t.so_don >= 2;
~~~

Trong hai cách, điều kiện số đơn từ 2 trở lên phải được hiểu đúng là lọc sau khi đếm; chỉ khác ở nơi biểu thức được đặt và cách quản lý tên.

**Phân biệt WHERE và HAVING:**

- WHERE chọn **dòng đầu vào** cho phép nhóm.
- HAVING chọn **nhóm đầu ra** sau phép nhóm.
- Alias cột đầu ra của SELECT trong cùng query block không làm thay đổi quy tắc đó.

## 9. ORDER BY: nơi alias cột được dùng phổ biến nhất

Ví dụ:

~~~sql
SELECT
    d.ma_don_hang,
    d.tong_tien * 1.10 AS tong_sau_phi
FROM don_hang d
ORDER BY tong_sau_phi DESC;
~~~

Vì ORDER BY sắp xếp kết quả đầu ra, nhiều DBMS cho phép dùng **tong_sau_phi** ngay trong ORDER BY của query block định nghĩa nó.

Tương tự với hàm tổng hợp:

~~~sql
SELECT
    d.ma_khach_hang,
    SUM(d.tong_tien) AS tong_chi
FROM don_hang d
WHERE d.trang_thai = 'PAID'
GROUP BY d.ma_khach_hang
ORDER BY tong_chi DESC, d.ma_khach_hang ASC;
~~~

Ở đây, **tong_chi** là alias cột kết quả của phép SUM. Phần ORDER BY vẫn hợp lệ khi GROUP BY không cho dùng alias đó, vì hai mệnh đề có quy tắc khác nhau.

### 9.1. Alias trong biểu thức ORDER BY phức tạp

Một số DBMS cho phép alias đầu ra chỉ khi dùng như một tên riêng lẻ trong ORDER BY, nhưng không cho dùng nó bên trong một biểu thức mới. Ví dụ, với PostgreSQL, hãy phân biệt:

~~~sql
-- Phù hợp:
SELECT d.tong_tien * 1.10 AS tong_sau_phi
FROM don_hang d
ORDER BY tong_sau_phi;
~~~

~~~sql
-- Có thể lỗi trong PostgreSQL:
SELECT d.tong_tien * 1.10 AS tong_sau_phi
FROM don_hang d
ORDER BY tong_sau_phi + 1000;
~~~

Nếu cần sắp xếp theo một biểu thức tiếp theo của alias, hãy tính ở bảng dẫn xuất/CTE, rồi dùng cột đầu vào của query block ngoài, hoặc viết toàn bộ biểu thức rõ ràng trong ORDER BY.

### 9.2. Khi tên alias trùng với tên cột đầu vào

Giả sử bảng có cột gốc **tong_tien** nhưng truy vấn đặt alias **tong_tien** cho một biểu thức khác:

~~~sql
SELECT
    d.tong_tien * 1.10 AS tong_tien
FROM don_hang d
ORDER BY tong_tien;
~~~

Trong một số DBMS, **ORDER BY tong_tien** được ưu tiên hiểu là cột đầu ra, trong khi tại GROUP BY, cùng tên đó có thể được ưu tiên hiểu là cột đầu vào. Đây là nguyên nhân gây lỗi hoặc hành vi khác nhau giữa các hệ.

Để tránh nhập nhằng, **không tái sử dụng tên cột có sẵn làm alias cho một biểu thức có ý nghĩa khác**. Đặt alias mới như **tong_sau_phi** và định tính cột gốc khi cần bằng **d.tong_tien**.

### 9.3. ORDER BY không bảo đảm tính ổn định nếu thiếu khóa phụ

Nếu nhiều đơn có **tong_sau_phi** bằng nhau, thứ tự giữa những đơn đó vẫn có thể thay đổi. Với báo cáo hoặc phân trang cần thứ tự nhất quán:

~~~sql
SELECT
    d.ma_don_hang,
    d.tong_tien * 1.10 AS tong_sau_phi
FROM don_hang d
ORDER BY tong_sau_phi DESC, d.ma_don_hang ASC;
~~~

**ma_don_hang** đóng vai trò tiêu chí sắp xếp phụ, giả sử là khóa duy nhất.

## 10. Alias cột có dùng lại được ngay trong chính SELECT không?

Thử viết:

~~~sql
-- Thường không hợp lệ: ten_cong_phi không phải tên đã có để tham chiếu.
SELECT
    d.tong_tien * 0.10 AS tien_cong_phi,
    d.tong_tien + tien_cong_phi AS can_thanh_toan
FROM don_hang d;
~~~

Nhiều DBMS không xử lý danh sách SELECT như một chuỗi câu lệnh gán biến từ trái sang phải. Bí danh **tien_cong_phi** không tự trở thành tên có thể dùng trong biểu thức SELECT kế tiếp.

Cách đơn giản:

~~~sql
SELECT
    d.tong_tien * 0.10 AS tien_cong_phi,
    d.tong_tien + d.tong_tien * 0.10 AS can_thanh_toan
FROM don_hang d;
~~~

Nếu biểu thức dài, cho nó thành một cột của truy vấn bên trong:

~~~sql
WITH gia_tri_phi AS (
    SELECT
        d.ma_don_hang,
        d.tong_tien,
        d.tong_tien * 0.10 AS tien_cong_phi
    FROM don_hang d
)
SELECT
    g.ma_don_hang,
    g.tien_cong_phi,
    g.tong_tien + g.tien_cong_phi AS can_thanh_toan
FROM gia_tri_phi g;
~~~

Hành vi của các phần mở rộng ngôn ngữ có thể khác nhau. Khi muốn viết SQL dễ chuyển giữa các hệ, **không dựa vào khả năng tái sử dụng alias cột ngay trong SELECT đã định nghĩa nó**.

## 11. Phạm vi (scope) của alias bảng

### 11.1. Alias bảng không tồn tại ngoài câu truy vấn khai báo

~~~sql
SELECT k.ma_khach_hang
FROM khach_hang k;
~~~

Một câu SELECT độc lập tiếp theo không tự nhận biết **k**:

~~~sql
-- Không có FROM khach_hang k nên k không được khai báo tại query block này.
SELECT k.ten_khach_hang
FROM khach_hang;
~~~

Hãy hiểu alias như **tên cục bộ trong một query block**, không như biến toàn cục hoặc tên bảng mới.

### 11.2. Alias trong JOIN phải được khai báo đúng nguồn

~~~sql
SELECT
    k.ten_khach_hang,
    d.ma_don_hang
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang;
~~~

Điều kiện ON có thể tham chiếu **k** và **d** vì chúng thuộc các đầu vào của JOIN đang xét.

Không nên dùng alias của bảng chưa nằm trong phạm vi của biểu thức JOIN hiện tại:

~~~sql
-- Ví dụ sai ý định: ở ON đầu tiên, p chưa được đưa vào JOIN.
SELECT
    k.ten_khach_hang
FROM khach_hang k
JOIN don_hang d
    ON d.ma_khach_hang = p.ma_khach_hang
JOIN phieu_van_chuyen p
    ON p.ma_don_hang = d.ma_don_hang;
~~~

Giả sử bảng **phieu_van_chuyen** tồn tại và có các cột nêu trên. **p** được khai báo ở JOIN sau, không thuộc hai nguồn của JOIN trước. Cách sửa là chuyển điều kiện về đúng JOIN và nguồn tương ứng:

~~~sql
SELECT
    k.ten_khach_hang
FROM khach_hang k
JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
JOIN phieu_van_chuyen p
    ON p.ma_don_hang = d.ma_don_hang
WHERE p.ma_khach_hang = k.ma_khach_hang;
~~~

Ví dụ này minh họa phạm vi tên, không nhằm khuyến nghị lược đồ **phieu_van_chuyen** phải lưu cột **ma_khach_hang**.

### 11.3. Tự JOIN một bảng: bắt buộc phân biệt hai vai trò

Giả sử bảng **nhan_vien(ma_nhan_vien, ho_ten, ma_quan_ly)** có cột ma_quan_ly tham chiếu ma_nhan_vien.

~~~sql
SELECT
    nv.ho_ten AS nhan_vien,
    ql.ho_ten AS quan_ly
FROM nhan_vien nv
LEFT JOIN nhan_vien ql
    ON nv.ma_quan_ly = ql.ma_nhan_vien;
~~~

Bảng **nhan_vien** xuất hiện hai lần, với hai vai trò khác nhau:

- **nv** đại diện cho nhân viên đang xét.
- **ql** đại diện cho người quản lý được liên kết.
- **nv.ho_ten** và **ql.ho_ten** cùng bắt nguồn từ một cột vật lý, nhưng thuộc **hai lần tham chiếu khác nhau**.

Nếu không đặt alias riêng, SQL sẽ không có cách rõ ràng để phân biệt hai vai trò này trong điều kiện JOIN.

### 11.4. Truy vấn con có tương quan: tham chiếu alias bên ngoài

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang
FROM khach_hang k
WHERE EXISTS (
    SELECT 1
    FROM don_hang d
    WHERE d.ma_khach_hang = k.ma_khach_hang
      AND d.trang_thai = 'PAID'
);
~~~

Truy vấn con có thể tham chiếu **k.ma_khach_hang** từ query block bên ngoài. Đây là **correlated subquery**: điều kiện bên trong có tham chiếu đến từng dòng của truy vấn ngoài.

- **k** thuộc query block ngoài, được nhìn thấy trong truy vấn con ở phạm vi cho phép.
- **d** được khai báo trong truy vấn con, không thể tự động dùng từ SELECT bên ngoài.
- Hai alias này là **bí danh bảng**, khác với alias cột đầu ra.

Không nên đặt trùng alias bảng ở các mức lồng nhau nếu không thật sự cần, vì dễ che khuất (shadow) tên của nguồn bên ngoài và khiến người đọc hiểu nhầm điều kiện tương quan.

### 11.5. Truy vấn con ở FROM: cần phân biệt với correlated subquery

Một bảng dẫn xuất được khai báo trong FROM thường cần một alias để truy vấn ngoài tham chiếu:

~~~sql
SELECT
    t.ma_khach_hang,
    t.tong_chi
FROM (
    SELECT
        d.ma_khach_hang,
        SUM(d.tong_tien) AS tong_chi
    FROM don_hang d
    WHERE d.trang_thai = 'PAID'
    GROUP BY d.ma_khach_hang
) t
WHERE t.tong_chi >= 300000;
~~~

Tại đây:

- Alias bảng **d** chỉ tồn tại trong truy vấn con.
- Alias cột **tong_chi** là một cột trong kết quả của truy vấn con.
- Alias bảng **t** đưa kết quả con vào phạm vi truy vấn ngoài.
- Truy vấn ngoài dùng **t.tong_chi**, không thể dùng **d.tong_tien** vì d nằm ngoài phạm vi.

Một điểm sâu hơn: truy vấn con đứng trong FROM **không tự động** được phép tham chiếu alias của nguồn đứng bên cạnh trong cùng FROM trên mọi DBMS. Cơ chế tham chiếu dạng này thường dùng **LATERAL** hoặc **APPLY**, với cú pháp và khả năng hỗ trợ khác nhau. Đừng nhầm nó với truy vấn con trong WHERE ... EXISTS, nơi tham chiếu tương quan tới query block ngoài là cách viết phổ biến.

## 12. CTE, tên bảng và bí danh: ba lớp tên khác nhau

Xét ví dụ:

~~~sql
WITH don_da_thanh_toan AS (
    SELECT
        d.ma_khach_hang,
        SUM(d.tong_tien) AS tong_chi
    FROM don_hang d
    WHERE d.trang_thai = 'PAID'
    GROUP BY d.ma_khach_hang
)
SELECT
    k.ten_khach_hang,
    t.tong_chi AS doanh_so
FROM khach_hang k
JOIN don_da_thanh_toan t
    ON t.ma_khach_hang = k.ma_khach_hang
ORDER BY doanh_so DESC, k.ma_khach_hang;
~~~

Phân biệt:

| Tên | Loại | Ý nghĩa và phạm vi |
|---|---|---|
| **don_hang** | Tên bảng vật lý | Nguồn dữ liệu thật trong cơ sở dữ liệu |
| **d** | Bí danh bảng | Tên tham chiếu don_hang ở query block trong CTE |
| **tong_chi** | Bí danh cột | Tên cột kết quả của phép SUM trong CTE |
| **don_da_thanh_toan** | Tên CTE | Tên tập kết quả trung gian khả dụng ở query block sau WITH |
| **t** | Bí danh nguồn CTE | Tên tham chiếu nguồn CTE trong FROM ngoài |
| **doanh_so** | Bí danh cột | Tên đầu ra của t.tong_chi trong SELECT ngoài |

Tại WHERE của truy vấn ngoài (nếu thêm), **t.tong_chi** hợp lệ vì là **cột đầu vào đến từ nguồn t**; còn **doanh_so** không nên sử dụng ở WHERE của chính truy vấn ngoài vì đó chỉ là alias vừa được đặt trong danh sách SELECT ngoài.

Nhiều người mới học nhầm rằng “nếu bí danh cột không dùng được ở WHERE thì tại sao t.tong_chi lại dùng được?”. Đó là hai query block khác nhau: **tong_chi đã trở thành cột của kết quả con trước khi truy vấn ngoài tham chiếu nó**.

## 13. Khác biệt phương ngữ về sử dụng alias cột

Bảng sau phản ánh **các cách dùng thường gặp trong một query block thông thường**, với alias không trùng tên cột đầu vào. Nó nhằm giúp đọc và chuyển câu lệnh giữa hệ quản trị, không thay cho tài liệu theo phiên bản.

| DBMS | Alias SELECT trong WHERE | Alias SELECT trong GROUP BY | Alias SELECT trong HAVING | Alias SELECT trong ORDER BY |
|---|---|---|---|---|
| PostgreSQL | Không | Có, với giới hạn phân giải tên | Không | Có |
| MySQL | Không | Có | Có | Có |
| SQL Server (T-SQL) | Không | Không | Không | Có |
| Oracle Database 19c | Không | Không | Không | Có |
| SQLite | Có như phần mở rộng | Có | Có trong ngữ cảnh phù hợp | Có |

**Ghi chú về phiên bản và trường hợp đặc biệt:**

1. **Oracle Database** có thay đổi khả năng tham chiếu alias trong GROUP BY ở các bản mới như dòng 23c/23ai. Khi học hoặc bảo trì ứng dụng, hãy đối chiếu tài liệu đúng bản Oracle triển khai thay vì suy ra từ bảng mô tả Oracle 19c.
2. **SQLite** chấp nhận alias trong WHERE là một phần mở rộng thuận tiện nhưng có thể tạo khác biệt khi chuyển sang DBMS khác.
3. **MySQL** cho phép alias SELECT trong HAVING, nhưng không cho ở WHERE thông thường. Không nên suy từ việc một alias dùng được trong HAVING rằng nó có thể dùng ở bất kỳ mệnh đề nào.
4. Quy tắc **ưu tiên tên cột đầu vào so với tên alias đầu ra** khác nhau tùy mệnh đề và DBMS, nhất là ở GROUP BY, ORDER BY và HAVING.
5. Những cú pháp liên quan **hàm cửa sổ, DISTINCT, truy vấn tập hợp và tên định danh phân cách** có ràng buộc bổ sung.

**Cách viết dễ chuyển hơn:** lấy FROM/JOIN làm nơi đặt alias bảng; tạo alias cột trong SELECT; dùng alias cột ở ORDER BY khi rõ ràng; còn WHERE, GROUP BY và HAVING thì sử dụng cột/biểu thức đầu vào hoặc đưa kết quả tính toán sang query block riêng.

## 14. Những lỗi phân giải tên thường gặp

### 14.1. Không định tính cột trùng tên giữa hai bảng

~~~sql
-- Dễ lỗi: ma_khach_hang có trong cả hai bảng.
SELECT ma_khach_hang
FROM khach_hang k
JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang;
~~~

Sửa:

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    d.ma_don_hang
FROM khach_hang k
JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang;
~~~

### 14.2. Đặt tên alias trùng nhau

~~~sql
-- Hai nguồn cùng bí danh k trong một FROM sẽ gây nhập nhằng/lỗi.
SELECT k.ma_khach_hang
FROM khach_hang k
JOIN don_hang k
    ON k.ma_khach_hang = k.ma_khach_hang;
~~~

Sửa bằng hai alias khác nhau:

~~~sql
SELECT k.ma_khach_hang, d.ma_don_hang
FROM khach_hang k
JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang;
~~~

Tương tự, đặt cùng tên alias cho hai cột đầu ra có thể được một số DBMS chấp nhận nhưng làm kết quả khó dùng và ORDER BY có thể nhập nhằng:

~~~sql
-- Không nên vì tên đầu ra bị trùng:
SELECT
    d.ma_don_hang AS gia_tri,
    d.tong_tien AS gia_tri
FROM don_hang d;
~~~

### 14.3. Bí danh cột trùng từ khóa hoặc có dấu cách

~~~sql
-- Tên cột hiển thị có khoảng trắng có thể cần dấu nháy theo DBMS.
SELECT d.tong_tien AS "Tổng tiền"
FROM don_hang d;
~~~

Dấu nháy kép là cú pháp định danh có trong SQL chuẩn, nhưng hệ quản trị có quy ước riêng: PostgreSQL/Oracle thường dùng dấu nháy kép; SQL Server cũng có thể dùng dấu ngoặc vuông; MySQL mặc định dùng dấu backtick và có chế độ ANSI_QUOTES.

Khi viết SQL phục vụ nhiều DBMS, ưu tiên alias đơn giản như:

~~~sql
SELECT d.tong_tien AS tong_tien_hien_thi
FROM don_hang d;
~~~

Với tên hiển thị thân thiện cho người dùng như “Tổng tiền”, ứng dụng có thể chuyển tên ở tầng giao diện thay vì phụ thuộc định danh SQL đặc biệt.

### 14.4. Tưởng alias là biến để tái sử dụng vô hạn

~~~sql
-- Không portable, thường lỗi:
SELECT
    tong_tien * 1.10 AS tong_sau_phi
FROM don_hang
WHERE tong_sau_phi >= 300000
GROUP BY tong_sau_phi
HAVING tong_sau_phi > 500000;
~~~

Truy vấn này còn mâu thuẫn về việc vừa SELECT giá trị hàng vừa GROUP BY/HAVING theo kết quả mà không nói rõ yêu cầu tổng hợp. Hãy xác định **đang lọc từng dòng hay lọc nhóm**, rồi chọn biểu thức hoặc query block phù hợp. Không thể sửa vấn đề chỉ bằng cách thêm AS.

### 14.5. Dùng alias bên trong ORDER BY của hàm cửa sổ

~~~sql
-- Thường không thể dùng alias tong_chi ngay trong OVER(...) cùng SELECT:
SELECT
    d.tong_tien * 1.10 AS tong_sau_phi,
    ROW_NUMBER() OVER (
        ORDER BY tong_sau_phi DESC
    ) AS thu_hang
FROM don_hang d;
~~~

**ORDER BY trong OVER(...)** xác định thứ tự cho một hàm cửa sổ; nó **không phải** ORDER BY cuối của toàn truy vấn. Không nên suy rằng quy tắc alias của ORDER BY cuối sẽ áp dụng bên trong mọi biểu thức OVER.

Cách viết rõ ràng:

~~~sql
WITH don_sau_phi AS (
    SELECT
        d.ma_don_hang,
        d.tong_tien * 1.10 AS tong_sau_phi
    FROM don_hang d
)
SELECT
    x.ma_don_hang,
    x.tong_sau_phi,
    ROW_NUMBER() OVER (
        ORDER BY x.tong_sau_phi DESC, x.ma_don_hang ASC
    ) AS thu_hang
FROM don_sau_phi x;
~~~

Nếu kết quả cuối còn cần hiển thị đúng thứ tự xếp hạng, thêm **ORDER BY thu_hang** tại cuối câu SELECT ngoài; thứ tự trong OVER không tự cam kết thứ tự xuất kết quả toàn truy vấn.

## 15. Alias khi dùng UNION và các truy vấn tập hợp

Giả sử cần gộp danh sách mã khách hàng xuất hiện từ hai nguồn:

~~~sql
SELECT
    k.ma_khach_hang AS ma
FROM khach_hang k
WHERE k.thanh_pho = 'Hà Nội'

UNION

SELECT
    d.ma_khach_hang AS ma_don
FROM don_hang d
WHERE d.trang_thai = 'PAID'

ORDER BY ma;
~~~

Trong nhiều DBMS, **tên cột kết quả của UNION được xác định từ nhánh SELECT đầu tiên**, vì vậy ORDER BY ở ngoài cùng thường tham chiếu tên đầu ra **ma**, không phải tên **ma_don** ở nhánh thứ hai. Một số hệ còn giới hạn biểu thức ORDER BY sau UNION.

Khi cần áp dụng phép tính hoặc điều kiện phức tạp lên kết quả đã gộp, có thể đặt toàn bộ truy vấn tập hợp trong CTE:

~~~sql
WITH danh_sach_ma AS (
    SELECT k.ma_khach_hang AS ma
    FROM khach_hang k
    WHERE k.thanh_pho = 'Hà Nội'

    UNION

    SELECT d.ma_khach_hang AS ma
    FROM don_hang d
    WHERE d.trang_thai = 'PAID'
)
SELECT ds.ma
FROM danh_sach_ma ds
WHERE ds.ma >= 1
ORDER BY ds.ma;
~~~

Bí danh đầu ra của từng nhánh SELECT và tên cột của kết quả tập hợp cần được hiểu trong đúng phạm vi của chúng; không nên áp dụng máy móc quy tắc ORDER BY của một SELECT đơn lẻ cho mọi dạng truy vấn tập hợp.

## 16. Lựa chọn alias dễ đọc và dễ bảo trì

| Tình huống | Cách đặt nên ưu tiên | Lý do |
|---|---|---|
| JOIN hai bảng đơn giản | **k** cho khach_hang, **d** cho don_hang | Ngắn mà rõ vai trò khi câu lệnh nhỏ |
| Nhiều bảng tên gần giống | **don**, **ct**, **sp** hoặc tên rõ hơn | Giảm nhầm các chữ viết tắt |
| Tự JOIN bảng nhân viên | **nv**, **ql** | Phản ánh vai trò của từng lần tham chiếu |
| Biểu thức tính phí | **tien_phi**, **tong_sau_phi** | Nêu ý nghĩa nghiệp vụ, phân biệt dữ liệu gốc |
| Phép tổng hợp | **so_don**, **doanh_thu** | Giúp đọc kết quả và ORDER BY |
| Truy vấn con tổng hợp | **thong_ke**, **tong_theo_khach** | Dễ hiểu khi đọc query block ngoài |
| Alias tham chiếu động từ người dùng | Chỉ dùng tên từ danh sách cho phép đã kiểm soát | Giá trị tham số SQL không thay thế trực tiếp tên định danh |

Một số lưu ý thêm:

- Alias quá ngắn như **a**, **b**, **c** khó hiểu khi truy vấn có nhiều bảng; ưu tiên tên thể hiện vai trò.
- Alias quá dài làm mọi dòng SQL cồng kềnh. Cân bằng độ ngắn và ý nghĩa.
- Hạn chế tên trùng từ khóa (SELECT, ORDER, GROUP...), trùng tên cột gốc nhưng khác ý nghĩa hoặc chỉ khác chữ hoa/chữ thường.
- Không dựa vào kiểu viết hoa/thường hoặc dấu nháy đặc thù khi chưa xác định DBMS mục tiêu.
- **Alias không phải nơi lưu dữ liệu**, nên không dùng alias như giải pháp thay thế cho cột được tính và lưu có chủ đích trong lược đồ.

## 17. Ví dụ tổng hợp: truy vấn báo cáo đúng phạm vi alias

Yêu cầu: “Liệt kê mọi khách hàng đang trong hệ thống, tổng số đơn đã thanh toán và tổng tiền đã thanh toán; kể cả người chưa có đơn. Chỉ hiển thị khách có tổng tiền từ 200.000 trở lên, sắp xếp tổng tiền giảm dần.”

Một cách viết rõ về phạm vi:

~~~sql
WITH tong_hop AS (
    SELECT
        k.ma_khach_hang,
        k.ten_khach_hang,
        COUNT(d.ma_don_hang) AS so_don_da_thanh_toan,
        COALESCE(SUM(d.tong_tien), 0) AS tong_chi
    FROM khach_hang k
    LEFT JOIN don_hang d
        ON d.ma_khach_hang = k.ma_khach_hang
       AND d.trang_thai = 'PAID'
    GROUP BY
        k.ma_khach_hang,
        k.ten_khach_hang
)
SELECT
    t.ma_khach_hang,
    t.ten_khach_hang,
    t.so_don_da_thanh_toan,
    t.tong_chi AS doanh_thu
FROM tong_hop t
WHERE t.tong_chi >= 200000
ORDER BY doanh_thu DESC, t.ma_khach_hang ASC;
~~~

Kết quả theo dữ liệu mẫu:

| ma_khach_hang | ten_khach_hang | so_don_da_thanh_toan | doanh_thu |
|---:|---|---:|---:|
| 2 | Bình | 2 | 400000 |
| 1 | An | 1 | 200000 |

Phân tích từng tên:

1. **k** và **d** là alias bảng, có hiệu lực trong SELECT của CTE **tong_hop**.
2. **so_don_da_thanh_toan** và **tong_chi** được tạo ở SELECT trong CTE, thành cột của nguồn **tong_hop**.
3. **t** là alias bảng cho nguồn **tong_hop** trong query block ngoài.
4. **t.tong_chi** có thể dùng ở WHERE ngoài vì đây đã là cột đầu vào của nguồn t.
5. **doanh_thu** được định nghĩa trong SELECT ngoài và dùng ở ORDER BY ngoài.
6. Điều kiện **d.trang_thai = 'PAID'** ở ON của LEFT JOIN bảo toàn khách chưa có đơn thanh toán trước khi lọc tổng tiền ở truy vấn ngoài.
7. Khách Chi không xuất hiện vì tổng tiền 0 thấp hơn 200.000; nếu bỏ điều kiện WHERE ngoài, Chi vẫn có mặt với **so_don_da_thanh_toan = 0** và **tong_chi = 0**.

Có thể viết báo cáo này bằng HAVING với biểu thức SUM/COALESCE nếu không cần một query block trung gian. CTE ở đây giúp làm rõ **thời điểm một tên kết quả trở thành cột đầu vào của truy vấn ngoài**.

## 18. Bài tập tự luyện

### Bài 1: Xác định loại bí danh

Cho truy vấn:

~~~sql
SELECT
    k.ten_khach_hang AS nguoi_mua,
    d.tong_tien AS gia_tri_don
FROM khach_hang k
JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang;
~~~

Hãy chỉ ra bí danh bảng, bí danh cột và tên bảng thật.

<details>
<summary>Đáp án gợi ý</summary>

- Bí danh bảng: **k**, **d**.
- Bí danh cột: **nguoi_mua**, **gia_tri_don**.
- Bảng thật: **khach_hang**, **don_hang**.
- Không có bảng/cột vật lý nào bị đổi tên.

</details>

### Bài 2: Sửa lỗi alias trong WHERE

Sửa truy vấn sau để có thể lọc đơn có tổng sau phí trên 500.000:

~~~sql
SELECT
    ma_don_hang,
    tong_tien * 1.05 AS tong_sau_phi
FROM don_hang
WHERE tong_sau_phi > 500000;
~~~

<details>
<summary>Đáp án gợi ý</summary>

Cách ngắn nhất:

~~~sql
SELECT
    ma_don_hang,
    tong_tien * 1.05 AS tong_sau_phi
FROM don_hang
WHERE tong_tien * 1.05 > 500000;
~~~

Hoặc dùng CTE tạo cột **tong_sau_phi** trước, rồi lọc ở SELECT bên ngoài.

</details>

### Bài 3: GROUP BY và HAVING

Cho truy vấn:

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang
HAVING so_don >= 2;
~~~

Câu lệnh có bảo đảm chạy được trên SQL Server và PostgreSQL không? Viết phiên bản dễ chuyển hệ hơn.

<details>
<summary>Đáp án gợi ý</summary>

Không nên giả định **so_don** ở HAVING được hỗ trợ trên SQL Server hoặc PostgreSQL. Viết lại:

~~~sql
SELECT
    ma_khach_hang,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY ma_khach_hang
HAVING COUNT(*) >= 2;
~~~

</details>

### Bài 4: Phạm vi truy vấn con

Đoạn nào trong truy vấn dưới đây tạo alias được nhìn thấy từ truy vấn ngoài?

~~~sql
SELECT x.ma_khach_hang, x.tong_chi
FROM (
    SELECT
        d.ma_khach_hang,
        SUM(d.tong_tien) AS tong_chi
    FROM don_hang d
    GROUP BY d.ma_khach_hang
) x
WHERE x.tong_chi > 100000;
~~~

Truy vấn ngoài có thể sử dụng **d.tong_tien** trong WHERE không?

<details>
<summary>Đáp án gợi ý</summary>

**x** là alias của kết quả truy vấn con trong FROM; **x.ma_khach_hang** và **x.tong_chi** là hai cột mà truy vấn con đưa ra. **d** chỉ tồn tại trong truy vấn con nên WHERE ngoài không thể dùng d.tong_tien.

</details>

### Bài 5: Alias bảng trong tự JOIN

Bảng **nhan_vien** chứa mã nhân viên và mã quản lý. Hãy viết truy vấn hiển thị tên nhân viên và tên quản lý.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
SELECT
    nv.ho_ten AS ten_nhan_vien,
    ql.ho_ten AS ten_quan_ly
FROM nhan_vien nv
LEFT JOIN nhan_vien ql
    ON ql.ma_nhan_vien = nv.ma_quan_ly;
~~~

Hai alias **nv** và **ql** đại diện cho hai vai trò của cùng một bảng.

</details>

### Bài 6: Phân biệt ORDER BY cuối và ORDER BY trong OVER

Vì sao đoạn này không nên sử dụng alias **tong_sau_phi** bên trong OVER?

~~~sql
SELECT
    tong_tien * 1.10 AS tong_sau_phi,
    ROW_NUMBER() OVER (ORDER BY tong_sau_phi DESC) AS stt
FROM don_hang;
~~~

<details>
<summary>Đáp án gợi ý</summary>

ORDER BY trong OVER thuộc biểu thức hàm cửa sổ được tính ở SELECT; nó không tuân theo quy tắc tham chiếu alias đầu ra của ORDER BY cuối. Hãy lặp lại biểu thức trong OVER hoặc tính **tong_sau_phi** ở CTE/truy vấn con rồi dùng tên cột đầu vào đó ở query block ngoài.

</details>

## 19. Ghi nhớ cốt lõi

- **Bí danh bảng** đặt tên cho **nguồn dữ liệu** trong FROM; **bí danh cột** đặt tên cho **giá trị đầu ra** của SELECT.
- Bí danh **không đổi tên dữ liệu vật lý** và chỉ tồn tại trong **phạm vi câu truy vấn/query block** liên quan.
- Alias bảng thường được dùng ở ON, WHERE, GROUP BY, HAVING, SELECT và ORDER BY khi nguồn đã được khai báo và nằm trong phạm vi tham chiếu.
- Alias cột của **chính SELECT** thường dùng được trong ORDER BY cuối, nhưng việc dùng ở WHERE, GROUP BY, HAVING, JOIN ... ON và biểu thức SELECT khác phụ thuộc quy tắc riêng. Đặc biệt **WHERE không nên dùng alias SELECT mới tạo** nếu cần tính khả chuyển.
- Khi cần dùng alias cột để tiếp tục tính toán hoặc lọc, hãy **đưa biểu thức sang truy vấn con/CTE**, để alias trở thành cột đầu vào của query block bên ngoài.
- Thứ tự **xử lý logic** giúp giải thích khả năng tham chiếu alias, nhưng không phải thứ tự thực thi vật lý mà DBMS chắc chắn áp dụng.
- Đối với SQL đa hệ, tránh **tên trùng**, **tên mơ hồ**, **dấu nháy đặc thù** và việc dựa vào những ngoại lệ alias của riêng một phương ngữ.

**Tài liệu để tra cứu khi áp dụng thực tế:** phần về SELECT, tên đầu ra, GROUP BY, HAVING, ORDER BY, subquery và table reference trong tài liệu SQL chính thức của PostgreSQL, MySQL, Microsoft SQL Server (Transact-SQL), Oracle Database và SQLite. Hãy kiểm tra đúng **phiên bản** và **cấu hình** đang dùng, vì mức hỗ trợ alias không hoàn toàn đồng nhất giữa các hệ quản trị.
