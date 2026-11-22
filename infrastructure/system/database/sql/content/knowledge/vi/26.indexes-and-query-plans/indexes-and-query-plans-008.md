# Điều kiện thuận lợi cho chỉ mục và chuyển đổi ngầm trên cột trong SQL

> **Module:** Database SQL  
> **Chương:** Chỉ mục và kế hoạch  
> **Bài học:** Điều kiện thuận lợi cho chỉ mục và chuyển đổi ngầm trên cột

Một chỉ mục (index) có thể giúp cơ sở dữ liệu tìm hàng nhanh hơn rất nhiều so với việc đọc cả bảng. Nhưng **có chỉ mục không có nghĩa mọi câu SQL lọc theo cột đó đều sử dụng chỉ mục hiệu quả**. Câu lệnh có thể viết một điều kiện không thuận lợi cho chỉ mục, chẳng hạn lấy năm bằng một hàm trên cột thời gian hoặc so một cột văn bản với tham số số khiến hệ quản trị **chuyển đổi kiểu dữ liệu ngầm trên từng giá trị của cột**. Khi ấy, cơ sở dữ liệu có thể phải đọc và chuyển đổi rất nhiều hàng trước khi biết hàng nào phù hợp.

Bài học này tập trung vào hai kỹ năng gắn liền nhau:

1. **Viết điều kiện thân thiện với chỉ mục**: giúp bộ tối ưu nhận ra điều kiện tra cứu trực tiếp hoặc khoảng giá trị trên khóa được đánh chỉ mục.
2. **Nhận ra và kiểm soát chuyển đổi ngầm (implicit conversion)**: biết đối tượng nào được chuyển kiểu — cột, hằng số, tham số, hay cả biểu thức — và việc đó ảnh hưởng đến kết quả, lỗi, chi phí CPU, chỉ mục và kế hoạch thực thi ra sao.

Đây là chủ đề **vừa về tính đúng dữ liệu, vừa về hiệu năng**. Một phép so sánh chuỗi với số không chỉ có thể làm mất index seek mà còn có thể gộp những mã vốn khác nhau như 00123 và 123.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích ý nghĩa gần đúng của **SARGable** (*Search ARGument able*) và phân biệt điều kiện hỗ trợ tra cứu chỉ mục với điều kiện phải lọc sau khi đọc.
- Biết vì sao biểu thức **trực tiếp trên cột đã lập chỉ mục** thường có lợi hơn hàm hoặc phép tính bao quanh cột.
- Viết lại điều kiện lọc ngày, số, chuỗi và khoảng giá trị theo dạng thích hợp cho B-tree.
- Nhận biết khi nào **CAST, CONVERT, TO_CHAR, TO_NUMBER, LOWER, UPPER, DATE, YEAR, COALESCE** làm thay đổi khả năng sử dụng chỉ mục thông thường.
- Phân biệt **ép kiểu ở phía tham số/hằng số** và **ép kiểu ở phía cột**.
- Hiểu thứ tự ưu tiên kiểu dữ liệu, kiểu của bind parameter, collation, NULL và timezone có thể thay đổi cách SQL được thực thi.
- Không dùng một quy tắc cứng như “cứ có CAST là không dùng được index”; thay bằng quan sát **kế hoạch thực thi** và hiểu ngữ nghĩa.
- Phân biệt **index seek / range scan**, **index scan** và **full table scan**, đồng thời hiểu chỉ mục không phải lúc nào cũng là kế hoạch rẻ nhất.
- Xử lý truy vấn **LIKE prefix**, điều kiện OR, IN, BETWEEN, IS NULL, JOIN và composite index.
- Sử dụng **expression index, function-based index, generated/computed column index** khi không thể tránh biểu thức trên cột.
- Đọc dấu hiệu chuyển đổi ngầm và sử dụng chỉ mục trong PostgreSQL, SQL Server, MySQL, Oracle và SQLite.
- Sử dụng tham số đúng kiểu trong Java/JDBC, tránh lỗi dữ liệu và kế hoạch bị ảnh hưởng bởi kiểu bind.
- Thiết kế kiểm thử hiệu năng và tính đúng khi sửa điều kiện SQL.

## 2. Mô hình dữ liệu thực hành

Giả sử hệ thống thương mại có hai bảng:

~~~sql
CREATE TABLE khach_hang (
    ma_khach          VARCHAR(30) PRIMARY KEY,
    email             VARCHAR(200),
    ten_hien_thi      VARCHAR(100),
    trang_thai        VARCHAR(20) NOT NULL,
    ngay_dang_ky      TIMESTAMP NOT NULL,
    tenant_id         VARCHAR(20) NOT NULL
);

CREATE TABLE don_hang (
    ma_don            BIGINT PRIMARY KEY,
    ma_khach          VARCHAR(30) NOT NULL,
    tenant_id         VARCHAR(20) NOT NULL,
    ngay_dat          TIMESTAMP NOT NULL,
    tong_tien         DECIMAL(14, 2) NOT NULL,
    trang_thai        VARCHAR(20) NOT NULL,
    FOREIGN KEY (ma_khach) REFERENCES khach_hang(ma_khach)
);
~~~

Một vài chỉ mục minh họa:

~~~sql
CREATE INDEX idx_kh_email
ON khach_hang (email);

CREATE INDEX idx_kh_tenant_ngay
ON khach_hang (tenant_id, ngay_dang_ky);

CREATE INDEX idx_dh_ngay
ON don_hang (ngay_dat);

CREATE INDEX idx_dh_khach_ngay
ON don_hang (ma_khach, ngay_dat);

CREATE INDEX idx_dh_tenant_status_date
ON don_hang (tenant_id, trang_thai, ngay_dat);
~~~

Định nghĩa CREATE INDEX trên là mẫu khái niệm tương đối phổ biến. Các DBMS khác nhau về kiểu dữ liệu, collation, key length, index method, cú pháp schema và các tính năng bổ sung.

Giả sử có các hàng đơn hàng:

| ma_don | ma_khach | tenant_id | ngay_dat | tong_tien | trang_thai |
|---:|---|---|---|---:|---|
| 1001 | C001 | T1 | 2026-10-03 09:15:00 | 250000 | MOI |
| 1002 | C002 | T1 | 2026-10-03 16:40:00 | 300000 | DA_GIAO |
| 1003 | C001 | T1 | 2026-10-04 00:00:00 | 90000 | MOI |
| 1004 | C003 | T2 | 2026-10-05 12:00:00 | 500000 | DA_GIAO |
| 1005 | C004 | T1 | 2026-11-01 08:00:00 | 100000 | HUY |

Các ví dụ sẽ dùng dữ liệu để minh họa **ngữ nghĩa**, không khẳng định kế hoạch chạy cụ thể nếu không có thống kê thực, số dòng, phiên bản và cấu hình DBMS. Bất cứ kế hoạch nào được đề xuất đều là **khả năng để kiểm chứng bằng EXPLAIN**, không phải đo đạc đã thực hiện.

## 3. Vì sao chỉ mục có thể giúp tìm hàng nhanh?

Với B-tree index trên **don_hang.ngay_dat**, hệ quản trị có thể duyệt cấu trúc chỉ mục để đến các giá trị trong một khoảng:

~~~sql
SELECT ma_don, ngay_dat, tong_tien
FROM don_hang
WHERE ngay_dat >= :bat_dau
  AND ngay_dat < :ket_thuc;
~~~

Nếu khoảng có ít hàng so với bảng lớn, việc tìm vị trí bắt đầu rồi quét đến giá trị kết thúc có thể rẻ hơn đọc cả bảng.

Có thể hình dung:

~~~text
INDEX theo ngay_dat:
2026-09-30 ...
2026-10-01 ...
2026-10-03 09:15  -> đơn 1001
2026-10-03 16:40  -> đơn 1002
2026-10-04 00:00  -> đơn 1003
2026-10-05 ...
2026-11-01 ...

Tra cứu từ >= 2026-10-03
Dừng trước >= 2026-10-04
~~~

Cơ sở dữ liệu vẫn có thể phải truy cập bảng gốc để lấy cột không nằm trong chỉ mục, hoặc dùng **index-only/covering** khi đủ điều kiện. Hiệu quả phụ thuộc số hàng, độ phân tán, độ chọn lọc, độ rộng dữ liệu, cache, thống kê và chi phí đọc.

### 3.1. Seek/range và scan là khái niệm kế hoạch

- **Index seek / index range scan**: tìm vùng khóa phù hợp rồi lấy các mục trong vùng.
- **Index scan**: duyệt nhiều hoặc toàn bộ mục chỉ mục và áp điều kiện.
- **Table/heap/clustered scan**: đọc nhiều hoặc toàn bộ bảng theo cấu trúc lưu trữ tương ứng.
- **Residual filter/predicate**: điều kiện kiểm tra sau khi đã lấy các mục ứng viên bằng một phần khóa.

Tên operator và mức độ sử dụng chỉ mục khác giữa DBMS; đừng dựa chỉ vào chữ “index” xuất hiện trong execution plan để kết luận truy vấn đã tra cứu tối ưu.

### 3.2. Một index scan không phải lúc nào cũng xấu

Nếu cần lấy 80% bảng, scan tuần tự có thể rẻ hơn hàng trăm nghìn lần tìm hàng theo chỉ mục. Một chỉ mục hẹp vẫn có thể hữu ích cho quét, sắp xếp hoặc chỉ trả các cột cần thiết.

**Mục tiêu là kế hoạch có chi phí thực tế thấp và kết quả đúng, không phải ép mọi câu lệnh thành index seek.**

## 4. SARGable là gì?

SARGable là cách nói thông dụng cho điều kiện mà bộ tối ưu có thể dùng làm **search argument** để giới hạn tra cứu theo cấu trúc chỉ mục, thay vì phải đánh giá một hàm cho từng giá trị cột trước khi biết vị trí cần tìm.

Ví dụ thường thuận lợi:

~~~sql
WHERE ngay_dat >= :start_time
  AND ngay_dat < :end_time
~~~

Truy vấn cần xem lại:

~~~sql
WHERE EXTRACT(YEAR FROM ngay_dat) = 2026
~~~

hoặc ở SQL Server:

~~~sql
WHERE YEAR(ngay_dat) = 2026
~~~

Trong những dạng sau, một hàm được áp lên cột ngay_dat. Một B-tree index thông thường trên giá trị gốc ngay_dat không nhất thiết cung cấp trực tiếp một dải khóa **theo kết quả YEAR**. Có thể dùng chỉ mục biểu thức nếu đã tạo đúng, hoặc bộ tối ưu có khả năng biến đổi đặc biệt theo phiên bản.

### 4.1. Quy tắc thiết kế thực dụng

Với B-tree thông thường:

> Ưu tiên để **cột đã lập chỉ mục đứng nguyên dạng** trong điều kiện so sánh, còn biến đổi hằng số/tham số ở phía đối diện khi an toàn về ngữ nghĩa.

Các dạng hay gặp:

~~~sql
cot = :value
cot > :lower
cot >= :lower AND cot < :upper
cot BETWEEN :a AND :b
cot IS NULL
cot IN (:a, :b, :c)
~~~

Tuy nhiên, việc một predicate có dạng trên vẫn **không bảo đảm** DBMS dùng index; đặc biệt khi kiểu dữ liệu, collation, thống kê, selectivity hoặc bố cục composite index không thuận lợi.

### 4.2. SARGability không phải một “luật cú pháp” tuyệt đối

Một số DBMS có thể:
- Đưa biến đổi từ cột sang tham số.
- Nhận diện phạm vi từ biểu thức đơn giản.
- Sử dụng function-based/expression index.
- Áp một **seek predicate** rồi đánh giá phần chuyển đổi như residual predicate.
- Dùng skip scan, bitmap, adaptive plan hoặc scan do ước tính chi phí.

Vì thế, câu đúng là **“biểu thức trên cột thường có nguy cơ khiến chỉ mục gốc khó được dùng cho tra cứu”**, không phải “bất kỳ hàm/CAST nào trên cột chắc chắn gây full table scan”.

## 5. Bảng ví dụ: điều kiện thuận lợi và điều kiện cần cân nhắc

| Ý định | Dạng thường thuận lợi | Dạng có thể bất lợi cho chỉ mục gốc |
|---|---|---|
| Lọc ngày trong một ngày | ngay_dat >= start AND ngay_dat < next_day | DATE(ngay_dat) = target_date |
| Lọc năm | ngay_dat >= start_of_year AND ngay_dat < start_of_next_year | YEAR(ngay_dat) = target_year |
| Lọc số ID | ma_don = numeric_parameter | CAST(ma_don AS VARCHAR) = text_parameter |
| So mã văn bản | ma_khach = text_parameter | CAST(ma_khach AS INTEGER) = numeric_parameter |
| Tên không phân biệt hoa/thường | Dùng collation/index phù hợp hoặc expression index | LOWER(ten) = LOWER(:input) khi chỉ có index thường |
| Tiền trên ngưỡng | tong_tien >= :min_amount | ROUND(tong_tien, 0) >= :min_amount |
| Kiểm tra prefix | email LIKE 'sale%' khi index/collation hỗ trợ | email LIKE '%sale' |
| Giá trị có NULL | email IS NULL, tùy index DBMS | COALESCE(email,'') = '' khi chỉ có index email gốc |
| Lọc trạng thái | trang_thai = 'MOI' | UPPER(trang_thai) = 'MOI' nếu cột đã chuẩn hóa |
| Lọc theo timestamp theo giờ địa phương | Hai instant ranh giới chuyển sẵn | Hàm chuyển timezone cho từng hàng trong WHERE |

Bảng chỉ nêu **mẫu thường gặp**, không thể thay thế EXPLAIN trên dữ liệu thật.

## 6. Hàm trên cột thời gian: từ DATE/YEAR sang khoảng nửa mở

Bài toán: lấy đơn trong ngày 03/10/2026.

Dạng có thể làm mất cơ hội dùng index trên **ngay_dat**:

**MySQL hoặc SQLite** với cột phù hợp:

~~~sql
SELECT ma_don
FROM don_hang
WHERE DATE(ngay_dat) = '2026-10-03';
~~~

**SQL Server:**

~~~sql
SELECT ma_don
FROM don_hang
WHERE CONVERT(date, ngay_dat) = '2026-10-03';
~~~

**PostgreSQL** với kiểu timestamp:

~~~sql
SELECT ma_don
FROM don_hang
WHERE ngay_dat::date = DATE '2026-10-03';
~~~

Trong mỗi dạng, có chuyển đổi từ cột timestamp sang giá trị ngày. Có DBMS/kiểu index có tối ưu đặc biệt, nhưng không nên mặc định B-tree index trên timestamp có thể seek lý tưởng.

### 6.1. Viết lại thành khoảng [start,end)

~~~sql
SELECT ma_don, ngay_dat
FROM don_hang
WHERE ngay_dat >= :start_of_day
  AND ngay_dat < :start_of_next_day;
~~~

Với start = 2026-10-03 00:00:00, end = 2026-10-04 00:00:00:

- Đơn 1001 được chọn.
- Đơn 1002 được chọn.
- Đơn 1003 đúng 00:00 ngày 04/10 **không** được chọn.

Đây là điều kiện thuận lợi cho B-tree trên ngay_dat vì nó mô tả một dải giá trị trực tiếp.

### 6.2. Vì sao không dùng đến 23:59:59?

~~~sql
WHERE ngay_dat BETWEEN '2026-10-03 00:00:00'
                  AND '2026-10-03 23:59:59'
~~~

có thể bỏ sót thời điểm có phần giây trong khoảng 23:59:59.000... đến ngay trước 00:00:00 của ngày kế tiếp.

BETWEEN bao gồm **cả hai cận**, nên cũng có nguy cơ chồng biên nếu sử dụng thời điểm kết thúc không chính xác.

### 6.3. Múi giờ và DST

Nếu ngay_dat lưu **instant/UTC** nhưng người dùng muốn đơn theo **ngày lịch địa phương**, hãy xác định hai mốc đầu ngày trong múi giờ nghiệp vụ, chuyển chúng sang kiểu và timezone của cột, rồi lọc theo khoảng đó.

Không phải mọi ngày địa phương dài đúng 24 giờ khi có chuyển giờ mùa hè. Trong những vùng có DST, cộng 24 giờ UTC vào một mốc có thể khác “đầu ngày kế tiếp” theo giờ địa phương.

### 6.4. Năm, tháng, giờ

Muốn lấy đơn trong năm 2026:

~~~sql
WHERE ngay_dat >= :start_2026
  AND ngay_dat < :start_2027
~~~

Muốn lấy đơn tháng 10/2026:

~~~sql
WHERE ngay_dat >= :start_october
  AND ngay_dat < :start_november
~~~

Nếu bắt buộc truy vấn nhiều lần theo năm/tháng trích từ cột, cân nhắc **generated column/index on expression** theo DBMS, nhưng phải hiểu semantic timezone trước.

## 7. Phép toán số học quanh cột

Giả sử có B-tree index trên tong_tien.

Dạng cần xem lại:

~~~sql
SELECT ma_don
FROM don_hang
WHERE tong_tien + 10000 > 500000;
~~~

Một cách biến đổi toán học:

~~~sql
WHERE tong_tien > 490000
~~~

giữ cột trực tiếp hơn.

Tương tự:

~~~sql
WHERE tong_tien * 2 >= 200000
~~~

có thể tương đương:

~~~sql
WHERE tong_tien >= 100000
~~~

**nếu** kiểu dữ liệu, NULL, precision, overflow và quy tắc toán học trong DBMS cho phép tương đương.

### 7.1. Không viết lại toán học mù quáng

Các tình huống dễ sai:

- Chia cho số âm làm **đảo chiều** bất đẳng thức.
- Chia cho 0 không hợp lệ.
- Phép tính số nguyên và phép chia nguyên.
- DECIMAL rounding và overflow.
- FLOAT/DOUBLE chứa giá trị đặc biệt hoặc sai số.
- Hàm ROUND/TRUNC làm mất thông tin.
- NULL làm điều kiện trở thành UNKNOWN.

Ví dụ:

~~~sql
WHERE tong_tien / 3 = 100000
~~~

không được tự sửa thành **tong_tien = 300000** nếu phép chia dùng kiểu nguyên, truncation hoặc quy tắc làm tròn khác.

### 7.2. Phép tính trên tham số thường phù hợp hơn

~~~sql
WHERE tong_tien >= :base_price * 1.10
~~~

để cột không bị bọc hàm, nhưng vẫn phải bảo đảm kiểu tham số và tính chính xác. Với số tiền, hãy dùng DECIMAL/NUMERIC đúng precision và scale.

## 8. Chuyển đổi ngầm là gì?

**Implicit conversion** xảy ra khi SQL chứa các toán hạng có kiểu không hoàn toàn phù hợp, và DBMS quyết định chuyển một hoặc nhiều toán hạng sang kiểu khác để thực hiện phép so sánh/tính toán.

Ví dụ ý tưởng:

~~~sql
SELECT *
FROM don_hang
WHERE ma_don = '1001';
~~~

Cột **ma_don** là BIGINT, nhưng hằng '1001' là dạng chuỗi. DBMS có thể suy luận hoặc chuyển hằng chuỗi sang số, hoặc xử lý theo quy tắc operator typing riêng, để so sánh với BIGINT.

Nếu hệ chuyển **hằng** sang số:

~~~text
ma_don (BIGINT) = CAST('1001' AS BIGINT)
~~~

thì chỉ mục BIGINT trên ma_don vẫn có cơ hội được tra cứu trực tiếp.

Nhưng nếu hệ phải chuyển **cột** sang chuỗi:

~~~text
CAST(ma_don AS VARCHAR) = '1001'
~~~

thì không còn so sánh trực tiếp khóa BIGINT trong index thường, có nguy cơ không dùng được seek đơn giản.

### 8.1. Không tự khẳng định hướng chuyển kiểu

**Hướng chuyển đổi không được quyết định chỉ bằng việc cột ở bên trái dấu bằng.** Nó phụ thuộc:

- Quy tắc ưu tiên kiểu dữ liệu (type precedence).
- Quy tắc chọn operator và implicit cast.
- Kiểu chính xác của cột.
- Kiểu hằng, expression hoặc bind parameter.
- Collation, precision, scale và độ dài.
- DBMS, phiên bản và cấu hình.

Trong một hệ, so cột text với số có thể chuyển text của cột sang số; trong hệ khác có thể từ chối vì không có toán tử so sánh hợp lệ hoặc áp quy tắc affinity khác.

### 8.2. Rủi ro lớn nhất ở phía cột

Nếu mỗi giá trị cột phải được CAST trước khi so, engine có thể cần:

1. Đọc nhiều hoặc toàn bộ giá trị ứng viên.
2. Chuyển kiểu từng giá trị.
3. Xử lý lỗi trên dữ liệu không chuyển được.
4. So sánh kết quả sau chuyển kiểu.
5. Lọc hàng phù hợp.

Không chỉ tốn CPU, nó còn có thể khiến **thứ tự của giá trị chuyển kiểu khác thứ tự khóa lưu trong index**, nên không thể suy ra một khoảng khóa gốc.

## 9. Cột văn bản chứa mã nhưng so với số

Giả sử bảng:

~~~sql
CREATE TABLE ma_thanh_vien (
    ma_the VARCHAR(20) PRIMARY KEY,
    ten VARCHAR(100)
);
~~~

Dữ liệu:

| ma_the | ten |
|---|---|
| 00123 | Huy |
| 123 | Lan |
| 000123 | Mai |
| AB123 | An |

Nếu so:

~~~sql
WHERE ma_the = 123
~~~

trong DBMS chuyển giá trị văn bản của cột sang số, các chuỗi 00123, 123, 000123 có thể cùng giá trị số **123**; AB123 có thể gây lỗi hoặc tạo cảnh báo/chuyển đổi đặc biệt.

Nhưng với business key dạng mã:

~~~sql
WHERE ma_the = '00123'
~~~

có ý nghĩa chính xác hơn: chỉ mã 00123. **Mã định danh có số 0 đầu hoặc ký tự chữ không nên được coi là số học chỉ vì trông giống số.**

### 9.1. Tác động tới chỉ mục

Nếu index lưu thứ tự chuỗi, chuyển toàn bộ **ma_the** sang số có thể phá khả năng seek theo thứ tự chuỗi. Đây là ví dụ vừa gây **đúng/sai dữ liệu**, vừa ảnh hưởng hiệu năng.

### 9.2. Không CAST hàng loạt dữ liệu bẩn để “chữa” query

~~~sql
WHERE CAST(ma_the AS BIGINT) = 123
~~~

có thể lỗi với AB123 và không còn phân biệt các mã có số 0 đầu. Giải pháp đúng là **định nghĩa kiểu dữ liệu phù hợp nghiệp vụ** và **bind tham số cùng kiểu**, không bắt mọi giá trị cột đi qua CAST.

## 10. Lựa chọn phía ép kiểu: tham số so với cột

Một mục tiêu thực dụng:

~~~sql
WHERE cot_so = CAST(:input_as_text AS BIGINT)
~~~

thường rõ hơn việc:

~~~sql
WHERE CAST(cot_so AS VARCHAR(30)) = :input_as_text
~~~

khi muốn tìm giá trị số và **biết chắc input hợp lệ để CAST sang số**.

Tuy nhiên, phải xác định:

- Input xấu sẽ báo lỗi theo ngữ nghĩa nào?
- BIGINT có đủ miền giá trị không?
- Parameter/driver có thể bind BIGINT trực tiếp không?
- Có mất số 0 đầu hoặc đơn vị không?
- Query đang so ID số hay mã văn bản?
- DBMS có tự chuyển input hợp lệ và vẫn seek được không?

**Cách tốt nhất thường là bind đúng kiểu ngay từ tầng ứng dụng**, thay vì gửi mọi thứ dưới dạng chuỗi rồi mong DBMS sửa.

### 10.1. Cột có kiểu đúng mà tham số sai

Nếu don_hang.ma_don là BIGINT, ở Java/JDBC:

~~~java
ps.setLong(1, 1001L);
~~~

thường hợp lý hơn:

~~~java
ps.setString(1, "1001");
~~~

vì bind string có thể khiến driver/server quyết định chuyển kiểu ngoài ý muốn. Một số hệ vẫn tối ưu tốt, nhưng việc tự chuyển không giúp mã nguồn rõ nghĩa hơn.

### 10.2. Ngược lại: mã là VARCHAR thì bind VARCHAR

Nếu ma_the là VARCHAR(20), nên dùng:

~~~java
ps.setString(1, "00123");
~~~

không dùng:

~~~java
ps.setLong(1, 123L);
~~~

vì 00123 và 123 có thể là hai mã khác nhau.

## 11. SQL Server: CONVERT_IMPLICIT và data type precedence

Trong SQL Server, **type precedence** ảnh hưởng tới phía được chuyển kiểu.

Một ví dụ nổi bật: cột VARCHAR chứa mã được so với tham số **INT**. SQL Server có thể chọn chuyển **giá trị cột VARCHAR sang INT**, vì INT có thứ tự ưu tiên kiểu cao hơn VARCHAR trong quy tắc chuyển đổi phù hợp.

~~~sql
-- ma_the là VARCHAR; @id là INT:
SELECT ma_the
FROM dbo.ma_thanh_vien
WHERE ma_the = @id;
~~~

Plan có thể biểu hiện ý tưởng:

~~~text
CONVERT_IMPLICIT(int, ma_the, ...)
~~~

và điều kiện tìm kiếm theo index VARCHAR có thể bị suy giảm, đồng thời dữ liệu không chuyển được có thể gây lỗi.

### 11.1. Khớp kiểu tham số

~~~sql
DECLARE @id VARCHAR(20) = '00123';

SELECT ma_the
FROM dbo.ma_thanh_vien
WHERE ma_the = @id;
~~~

giúp tránh chuyển cột mã sang số và giữ ý nghĩa mã có số 0 đầu.

### 11.2. VARCHAR so với NVARCHAR

SQL Server có hai họ kiểu chuỗi phổ biến:

- **VARCHAR** với quy tắc collation/encoding.
- **NVARCHAR** cho Unicode.

Nếu cột indexed là VARCHAR nhưng tham số NVARCHAR, SQL Server có thể chèn CONVERT_IMPLICIT cho phía cột theo quy tắc ưu tiên, ảnh hưởng khả năng sử dụng index. **Không phải mọi trường hợp đều mất index seek**: có các tối ưu phụ thuộc collation/loại so sánh và kế hoạch.

Không chuyển toàn bộ ứng dụng sang VARCHAR chỉ để tránh warning. Với Unicode và tiếng Việt, hãy thiết kế kiểu cột đúng yêu cầu, rồi bind **kiểu nhất quán** và kiểm tra plan thực tế.

### 11.3. Xem dấu hiệu trong execution plan

Trong **actual execution plan** của SQL Server có thể thấy:

- **CONVERT_IMPLICIT** trong Scalar Operator.
- **Seek Predicate** so với **Predicate** (residual).
- Cảnh báo **PlanAffectingConvert** hoặc loại cảnh báo liên quan.
- Index Seek, Index Scan, Clustered Index Scan.
- Estimated vs Actual Rows và số reads.

Một CONVERT_IMPLICIT xuất hiện không tự chứng minh chậm; phải xem nó nằm ở phía nào, có làm thay đổi cách truy cập index hay ước lượng cardinality không, và chênh lệch chi phí đo được.

### 11.4. SARGable không giải quyết hết parameter sniffing

SQL Server có thể tạo kế hoạch dựa vào giá trị tham số lúc compile rồi tái sử dụng cho giá trị có độ chọn lọc khác. Đây là vấn đề **parameter sniffing/plan caching** khác với implicit conversion. Một câu WHERE đúng kiểu vẫn có thể dùng kế hoạch không tốt nếu dữ liệu bị lệch; cần phân tích thống kê và plan reuse riêng.

## 12. PostgreSQL: operator typing, literal không kiểu và explicit cast

PostgreSQL thường có hệ thống kiểu mạnh, lựa chọn toán tử và quy tắc suy luận kiểu tương đối chặt chẽ.

Ví dụ:

~~~sql
SELECT ma_don
FROM don_hang
WHERE ma_don = 1001;
~~~

cột BIGINT so với literal số có thể được giải quyết thành operator phù hợp.

Với literal văn bản chưa có kiểu cố định trong nhiều ngữ cảnh:

~~~sql
WHERE ma_don = '1001'
~~~

PostgreSQL thường suy ra kiểu phù hợp từ cột hoặc operator, nhưng không đồng nghĩa một **tham số đã bind kiểu TEXT/VARCHAR** luôn có thể so trực tiếp với BIGINT.

### 12.1. TEXT parameter và BIGINT

Một câu truy vấn nhận parameter đã được khai báo là text có thể cần cast tường minh:

~~~sql
WHERE ma_don = CAST(:ma AS BIGINT)
~~~

thay vì:

~~~sql
WHERE CAST(ma_don AS TEXT) = :ma
~~~

vì mục tiêu là so số BIGINT, giữ cột không biến đổi và kiểm tra đầu vào hợp lệ.

Nếu ứng dụng đã biết ma_don là BIGINT, tốt hơn bind tham số BIGINT từ đầu.

### 12.2. PostgreSQL không tự ép mọi kiểu để “cho chạy”

Một số phép so giữa số và TEXT đã định kiểu có thể **báo lỗi operator does not exist** thay vì âm thầm chuyển toàn cột. Khác với SQL Server/Oracle/MySQL, không nên suy ra PostgreSQL luôn tự CAST cột văn bản sang số.

### 12.3. LIKE prefix và collation

B-tree index thông thường trên text có thể hỗ trợ một số phép LIKE prefix, nhưng với collation không phải C, PostgreSQL có thể cần **text_pattern_ops/varchar_pattern_ops** hoặc cấu hình/index khác để đạt hiệu quả, tùy kiểu/collation và phiên bản.

Ví dụ:

~~~sql
CREATE INDEX idx_kh_email_pattern
ON khach_hang (email varchar_pattern_ops);
~~~

Cú pháp trên hướng tới cột VARCHAR ở PostgreSQL. Với TEXT có operator class khác. Chỉ tạo khi có nhu cầu và sau khi phân tích plan.

### 12.4. EXPLAIN

~~~sql
EXPLAIN
SELECT ma_don
FROM don_hang
WHERE ma_don = 1001;
~~~

Có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ma_don
FROM don_hang
WHERE ngay_dat >= TIMESTAMP '2026-10-03 00:00:00'
  AND ngay_dat < TIMESTAMP '2026-10-04 00:00:00';
~~~

EXPLAIN không ANALYZE cho kế hoạch ước lượng; EXPLAIN ANALYZE **thực thi truy vấn** để đo. Với câu DML, ANALYZE có thể **thực sự thay đổi dữ liệu** nếu không có giao dịch/rollback phù hợp; không chạy bừa trên production.

## 13. MySQL: so chuỗi với số có thể đổi cả ngữ nghĩa và kế hoạch

MySQL có cơ chế chuyển kiểu linh hoạt trong phép so sánh.

Nếu cột mã là VARCHAR nhưng điều kiện dùng số:

~~~sql
SELECT ma_the
FROM ma_thanh_vien
WHERE ma_the = 123;
~~~

MySQL có thể chuyển giá trị chuỗi và số về cách so sánh dạng số, làm các chuỗi như '00123' và '123' có thể bị coi tương đương. Một index chuỗi có thể không được sử dụng hiệu quả cho tra cứu này vì so sánh không theo thứ tự chuỗi lưu trong index.

**Nên dùng đúng kiểu mã:**

~~~sql
SELECT ma_the
FROM ma_thanh_vien
WHERE ma_the = '00123';
~~~

### 13.1. Không quy kết mọi phép so số với chuỗi đều chậm

Nếu cột số được so với literal chuỗi số hợp lệ:

~~~sql
WHERE ma_don = '1001'
~~~

MySQL có thể chuyển literal sang số và dùng index của cột số. Đó là lý do quan trọng phải phân biệt **phía cột** và **phía hằng/parameter** được chuyển.

Dẫu vậy, để rõ nghĩa và tránh dữ liệu không hợp lệ, vẫn nên bind số đúng kiểu thay vì phụ thuộc implicit conversion.

### 13.2. EXPLAIN MySQL

~~~sql
EXPLAIN
SELECT ma_don
FROM don_hang
WHERE ngay_dat >= '2026-10-03 00:00:00'
  AND ngay_dat < '2026-10-04 00:00:00';
~~~

Những cột cần xem gồm:

- **type / access type** như const, ref, range, index, ALL.
- **possible_keys**, **key** thực sự được chọn.
- **rows** và **filtered** ước lượng.
- **Extra**, ví dụ Using where, Using index, Using filesort.
- Khi hỗ trợ, EXPLAIN ANALYZE để quan sát số liệu thực.

**Using index** thường liên quan covering index, không tự đồng nghĩa với index seek/range access tối ưu.

### 13.3. SQL mode, dữ liệu bẩn và lỗi

MySQL có những hành vi chuyển đổi và cảnh báo/lỗi phụ thuộc SQL mode, loại câu lệnh và ngữ cảnh. Không dựa vào việc một truy vấn SELECT “có vẻ chuyển được” để quyết định mọi chuỗi mã đều an toàn khi so bằng số.

## 14. Oracle Database: implicit conversion và NLS

Oracle có các quy tắc chuyển kiểu ngầm khi so dữ liệu.

Một tình huống điển hình: cột **VARCHAR2** chứa mã hoặc số dạng text nhưng tham số **NUMBER**. Oracle có thể dùng **TO_NUMBER** trên phía cột để so với số:

~~~sql
SELECT ma_the
FROM ma_thanh_vien
WHERE ma_the = :numeric_bind;
~~~

Nếu cột chứa dữ liệu không chuyển được, có thể gặp lỗi kiểu **ORA-01722: invalid number** trong những ngữ cảnh phù hợp. Và một B-tree index thường trên VARCHAR2 không tự tương đương index trên TO_NUMBER(ma_the).

### 14.1. Bind đúng kiểu nếu cột là mã

~~~sql
WHERE ma_the = :text_bind
~~~

với bind text hợp lệ giúp giữ đúng semantics chuỗi. Nếu mục tiêu thật sự là số, schema nên dùng NUMBER hoặc thiết kế cột số riêng với validation, thay vì TO_NUMBER mọi mã tại lúc truy vấn.

### 14.2. Ngày giờ và NLS_DATE_FORMAT

Không nên phụ thuộc việc Oracle tự hiểu:

~~~sql
WHERE ngay_dat = '03/10/2026'
~~~

vì định dạng có thể phụ thuộc cài đặt phiên **NLS_DATE_FORMAT** và không tương đương với toàn ngày nếu ngay_dat có thành phần giờ.

Với DATE và timestamp, dùng **date/timestamp literal hoặc bind đúng kiểu**, cộng khoảng [start,next_start):

~~~sql
WHERE ngay_dat >= DATE '2026-10-03'
  AND ngay_dat < DATE '2026-10-04'
~~~

Đây là ví dụ dành cho kiểu và ngữ cảnh Oracle phù hợp. Nếu cột có timezone, dùng bind/kiểu tương thích và chuyển mốc đúng timezone.

### 14.3. Hàm trên cột và function-based index

Oracle hỗ trợ **function-based index**:

~~~sql
CREATE INDEX idx_kh_lower_email
ON khach_hang (LOWER(email));
~~~

Khi truy vấn:

~~~sql
WHERE LOWER(email) = LOWER(:email)
~~~

index biểu thức có thể giúp nếu điều kiện, kiểu và kế hoạch phù hợp. Index biểu thức **không thay thế việc hiểu collation/normalization**, và hàm được lập chỉ mục phải tuân thủ những quy tắc determinism của Oracle.

### 14.4. Đọc kế hoạch

Oracle thường dùng EXPLAIN PLAN và DBMS_XPLAN, hoặc dữ liệu cursor plan để xem **INDEX RANGE SCAN**, **TABLE ACCESS FULL**, predicates và implicit functions. Tùy ngữ cảnh, kế hoạch chỉ ước lượng có thể khác kế hoạch thực; hãy dùng công cụ quan sát thực tế và bind variables phù hợp.

## 15. SQLite: type affinity, biểu thức và EXPLAIN QUERY PLAN

SQLite khác các DBMS kiểu tĩnh truyền thống ở hệ thống **storage class / type affinity**.

Ví dụ cột khai báo TEXT/VARCHAR có thể được xử lý so sánh dựa trên affinity, và giá trị được lưu có thể mang kiểu nội tại khác nhau. Do đó việc so cột với tham số số cần được **kiểm tra đúng semantics SQLite**, không áp nguyên xi bảng ưu tiên kiểu của SQL Server.

### 15.1. Chỉ mục và biểu thức

SQLite có thể dùng index cột cho điều kiện thông thường:

~~~sql
SELECT *
FROM khach_hang
WHERE email = ?;
~~~

Nhưng:

~~~sql
SELECT *
FROM khach_hang
WHERE LOWER(email) = LOWER(?);
~~~

không tự dùng cùng B-tree index thường trên email theo cách như truy vấn bằng trực tiếp. Có thể tạo **expression index** nếu hàm được phép/deterministic:

~~~sql
CREATE INDEX idx_kh_lower_email_sqlite
ON khach_hang (LOWER(email));
~~~

Hãy bảo đảm biểu thức query tương ứng với expression index theo quy tắc SQLite; optimizer không tự chứng minh mọi biểu thức tương đương đại số.

### 15.2. EXPLAIN QUERY PLAN

~~~sql
EXPLAIN QUERY PLAN
SELECT *
FROM khach_hang
WHERE email = ?;
~~~

Kết quả có thể mô tả **SEARCH ... USING INDEX** hoặc **SCAN**. Đây là công cụ để quan sát hành vi tối ưu, không phải cam kết truy vấn sẽ luôn chọn cùng kế hoạch khi dữ liệu, thống kê hoặc phiên bản thay đổi.

### 15.3. LIKE và collation ở SQLite

Khả năng dùng B-tree index cho **LIKE 'abc%'** trong SQLite có điều kiện cụ thể về **collation**, cách LIKE so chữ hoa/thường, pattern và cách tham số được biết tại thời điểm lập kế hoạch. Không kết luận mọi LIKE prefix đều seek được. Với các ứng dụng đa ngôn ngữ, xử lý Unicode của built-in LOWER/LIKE và extension ICU cần được xem riêng.

## 16. Cột string: LIKE prefix và ký tự đại diện

Giả sử index trên email.

Điều kiện:

~~~sql
WHERE email LIKE 'sales%'
~~~

có thể quy về một **dải prefix** của chuỗi, tùy collation và DBMS, nên có cơ hội dùng index.

Nhưng:

~~~sql
WHERE email LIKE '%sales'
~~~

hay:

~~~sql
WHERE email LIKE '%sales%'
~~~

bắt đầu bằng wildcard. Một B-tree index trên chuỗi đầy đủ thường không thể xác định một dải khóa liên tục cho “chứa sales ở bất kỳ vị trí nào”.

### 16.1. Prefix không đồng nghĩa chắc chắn sử dụng B-tree

Phụ thuộc:

- Collation/case sensitivity.
- Operator class hoặc index collation.
- Pattern literal hay parameter.
- Escape syntax và wildcard.
- Thống kê về phân bố prefix.
- Độ chọn lọc của prefix.
- DBMS/phiên bản.

### 16.2. Tìm kiếm chứa chuỗi ở giữa cần công cụ khác

Nếu bài toán thực sự là “email chứa chuỗi” hoặc “tên chứa từ”, cân nhắc:

- Full-text search theo DBMS khi tìm từ/cụm từ.
- Trigram index trên PostgreSQL với extension phù hợp.
- Search index/ngram/khả năng chuyên biệt của DBMS.
- Search engine khi yêu cầu phù hợp.

Đừng cố biến mọi truy vấn **LIKE '%abc%'** thành một B-tree seek bằng lời hứa kỹ thuật không có cơ sở.

### 16.3. Escape wildcard do người dùng nhập

Dấu **%** và **_** trong LIKE là ký tự đại diện. Nếu người dùng muốn tìm **literal underscore**, cần escape theo cú pháp phù hợp:

~~~sql
WHERE email LIKE :pattern ESCAPE '!'
~~~

Ví dụ pattern có thể xây từ prefix đã escape để dấu % ở cuối là wildcard mong muốn, còn %/_ trong dữ liệu nhập được escape bằng '!'.

Cách escape cụ thể và dấu escape phải phù hợp DBMS, đồng thời dùng bind parameter để tránh SQL injection. **Escape wildcard** và **tham số hóa SQL** giải quyết hai vấn đề khác nhau.

## 17. LOWER/UPPER và collation

Muốn tìm email không phân biệt chữ hoa/thường:

~~~sql
WHERE LOWER(email) = LOWER(:input_email)
~~~

có vẻ tiện, nhưng một index thường trên email **không đồng nghĩa** index trên LOWER(email).

Các phương án:

1. Thiết kế **collation case-insensitive** phù hợp, tạo index theo collation đó.
2. Dùng **expression/function-based index** trên LOWER(email).
3. Lưu cột **email_normalized** với canonicalization được kiểm soát, lập index trên cột đó.
4. Sử dụng loại dữ liệu/cơ chế chuyên biệt nếu DBMS cung cấp.

### 17.1. Case-insensitive không có nghĩa accent-insensitive

Trong tiếng Việt, so sánh **Hòa** và **Hoa** có được coi bằng nhau hay không còn phụ thuộc collation và yêu cầu nghiệp vụ. LOWER không tự giải quyết mọi vấn đề Unicode normalization, dấu và so sánh quốc tế.

### 17.2. Chọn một quy tắc và dùng nhất quán

Nếu ứng dụng ghi email_normalized = LOWER(email) bằng một thư viện Unicode nhưng truy vấn dùng LOWER khác ở DB, kết quả có thể khác trong trường hợp đặc biệt. Cần xác định canonicalization và xử lý dữ liệu toàn vẹn.

### 17.3. Đừng làm thay đổi semantics vì hiệu năng

Không được đổi **WHERE email = :email** sang **LOWER(email) = LOWER(:email)** chỉ để “tìm được nhiều hơn” nếu email/username có chính sách phân biệt hoa thường. Trước hết phải xác định yêu cầu đúng.

## 18. COALESCE, ISNULL, NVL trên cột

Ví dụ:

~~~sql
WHERE COALESCE(trang_thai, 'MOI') = 'MOI'
~~~

Nếu chỉ có index trên trang_thai, điều kiện này bao quanh cột bằng hàm, có thể không dùng được index gốc như một so sánh trực tiếp. Có thể diễn đạt:

~~~sql
WHERE trang_thai = 'MOI'
   OR trang_thai IS NULL
~~~

**khi đúng yêu cầu**: NULL được xem như MOI.

Tùy DBMS, OR có thể được tối ưu bằng nhiều index probe, bitmap index operation hoặc scan; việc viết lại không bảo đảm nhanh hơn. Hãy kiểm tra plan.

### 18.1. Không phải mọi COALESCE đều đổi được đơn giản

~~~sql
WHERE COALESCE(so_luong, 0) > 5
~~~

nếu so_luong NULL được coi là 0, thì điều kiện này tương đương:

~~~sql
WHERE so_luong > 5
~~~

vì NULL không thỏa >5 trong cả hai trường hợp. Nhưng:

~~~sql
WHERE COALESCE(so_luong, 0) >= 0
~~~

**không tương đương** với so_luong >= 0: nhánh đầu **bao gồm NULL**, nhánh sau bỏ NULL.

Cần suy luận logic ba giá trị trước khi sửa WHERE chỉ để cải thiện chỉ mục.

### 18.2. NULL và index theo DBMS

Một số B-tree index hỗ trợ tra cứu **IS NULL** tốt; PostgreSQL, SQL Server, MySQL và SQLite có hành vi tương ứng theo cấu hình. **Oracle B-tree thường không lưu entry khi mọi cột của khóa index là NULL**, nên một index chỉ có cột nullable không nhất thiết hỗ trợ tìm toàn bộ NULL; index ghép/function-based có thể thay đổi tình hình.

Không khẳng định **IS NULL luôn không dùng được index** hoặc **IS NULL luôn rất nhanh**.

## 19. CAST/CONVERT bao quanh cột và phía tham số

Ba dạng khác nhau:

**A — Cột không bị biến đổi:**

~~~sql
WHERE ma_don = :numeric_id
~~~

**B — Chuyển kiểu tham số/hằng:**

~~~sql
WHERE ma_don = CAST(:text_id AS BIGINT)
~~~

**C — Chuyển kiểu cột:**

~~~sql
WHERE CAST(ma_don AS VARCHAR(30)) = :text_id
~~~

Với index trên BIGINT ma_don, A thường rõ ràng nhất, B có cơ hội giữ tra cứu khóa gốc nếu kiểu/giá trị hợp lệ, còn C thường bất lợi vì biểu thức được áp trên từng giá trị cột.

### 19.1. Khi phải CAST cột vì mô hình dữ liệu

Nếu dữ liệu cũ lưu các số trong VARCHAR và ứng dụng phải lọc số học, có thể:

- Làm sạch dữ liệu và migrate sang kiểu số thực sự.
- Thêm cột số đã kiểm soát, tạo index.
- Dùng computed/generated expression index theo DBMS.
- Tạm dùng TRY_CAST/TRY_CONVERT nếu hệ hỗ trợ, nhận biết nó có thể cần quét và vẫn có logic bỏ/giữ giá trị không chuyển được.

Không tự CAST cột VARCHAR có chứa mã định danh sang số nếu nghiệp vụ phải giữ số 0 đầu.

### 19.2. TRY_CAST không tự làm điều kiện SARGable

SQL Server hỗ trợ TRY_CONVERT/TRY_CAST; chúng giúp trả NULL thay vì lỗi cho nhiều trường hợp chuyển kiểu không hợp lệ. Nhưng:

~~~sql
WHERE TRY_CONVERT(BIGINT, ma_the) = 123
~~~

vẫn là **biểu thức trên cột** và vẫn so theo nghĩa số, không tương đương tìm chính xác mã '00123'. Muốn tối ưu có thể cần indexed computed column được định nghĩa thích hợp, cùng chính sách dữ liệu rõ.

## 20. Kiểu dữ liệu trong JOIN quan trọng không kém WHERE

Giả sử:

~~~sql
SELECT *
FROM don_hang d
JOIN khach_hang k
  ON d.ma_khach = k.ma_khach;
~~~

Nếu hai cột cùng VARCHAR với collation tương thích và có chỉ mục phù hợp, optimizer có nhiều lựa chọn join.

Nhưng nếu một bảng lưu ma_khach là BIGINT, bảng kia lưu VARCHAR, DBMS phải xử lý khác kiểu hoặc báo lỗi:

~~~sql
ON d.ma_khach_so = k.ma_khach_text
~~~

Có thể phát sinh chuyển kiểu trên một phía, làm index seek theo khóa JOIN khó hơn hoặc gây lỗi giá trị không chuyển được.

### 20.1. Giải pháp thiết kế là nhất quán schema

**Khóa chính và khóa ngoại tham chiếu nên có kiểu, miền giá trị và quy tắc so sánh tương thích.** Một join giữa BIGINT và VARCHAR vốn biểu thị cùng ID thường cho thấy schema/import đang chưa chuẩn hóa.

### 20.2. JOIN nhiều hàng và ước lượng

Chuyển kiểu có thể ảnh hưởng **ước lượng cardinality**, làm optimizer chọn nested loops thay vì hash join hoặc ngược lại. Nhưng không phải mọi chuyển kiểu đều phá lựa chọn join; phải đọc số hàng ước lượng/thực tế và toán tử trong plan.

### 20.3. Không chỉ tối ưu join predicate

Nếu SELECT trả quá nhiều cột hoặc join tạo hàng triệu tổ hợp vì thiếu khóa, sửa CAST không cứu được tính đúng. Cần kiểm tra quan hệ và uniqueness trước.

## 21. Composite index và thứ tự cột

Giả sử:

~~~sql
CREATE INDEX idx_dh_tenant_status_date
ON don_hang (tenant_id, trang_thai, ngay_dat);
~~~

Một truy vấn phù hợp:

~~~sql
SELECT ma_don, ngay_dat
FROM don_hang
WHERE tenant_id = :tenant
  AND trang_thai = 'MOI'
  AND ngay_dat >= :start_time
  AND ngay_dat < :end_time;
~~~

Có hai điều kiện **bằng** trên hai cột dẫn đầu, sau đó là **khoảng** trên cột thứ ba. Đây là mẫu thường thuận lợi cho B-tree index ghép.

### 21.1. Equality prefix rồi range

Quy tắc thực hành thường gặp:

- Với chỉ mục (A,B,C), lọc **A=... AND B=... AND C BETWEEN ...** thường có khả năng dùng dải khóa hẹp.
- Lọc **A=... AND C BETWEEN ...** nhưng bỏ B có thể không tận dụng C để giới hạn một dải liên tục theo cùng cách.
- Lọc chỉ **C=...** thường ít phù hợp với thứ tự index (A,B,C), dù một số DBMS có skip scan hoặc tối ưu khác.

### 21.2. Không phải mọi cột trong WHERE đều thành seek predicate

Một query dùng index ghép vẫn có thể áp **trang_thai** như residual filter nếu không sử dụng đủ prefix hoặc khi chuyển kiểu. Xem phần **Index Cond/Seek Predicates** so với **Filter/Predicate** trong plan.

### 21.3. Trình tự điều kiện trong văn bản WHERE ít quan trọng hơn thứ tự cột index

~~~sql
WHERE ngay_dat >= :start_time
  AND trang_thai = 'MOI'
  AND tenant_id = :tenant
~~~

về mặt logic tương đương với thứ tự đảo trong ví dụ trước. Thứ tự bạn viết AND thường không phải yếu tố quyết định vị trí khóa trong index; chính **định nghĩa index và kế hoạch optimizer** mới quan trọng.

### 21.4. Cân nhắc ORDER BY

Nếu muốn:

~~~sql
WHERE tenant_id = :tenant
  AND trang_thai = 'MOI'
ORDER BY ngay_dat;
~~~

index (tenant_id,trang_thai,ngay_dat) có thể hỗ trợ thứ tự theo ngay_dat sau khi cố định hai cột đầu, giảm nhu cầu sort, nhưng còn phụ thuộc collation, chiều sort, cột trả về và kế hoạch.

## 22. Selectivity và statistics: SARGable vẫn có thể scan

Giả sử 99,9% đơn hàng có trang_thai='DA_GIAO'. Truy vấn:

~~~sql
WHERE trang_thai = 'DA_GIAO'
~~~

là điều kiện trực tiếp trên cột, về hình thức thuận lợi cho index. Nhưng nếu nó trả gần cả bảng, đọc nhiều hàng qua index rồi lookup có thể đắt hơn scan.

Ngược lại:

~~~sql
WHERE trang_thai = 'HUY'
~~~

nếu chỉ 0,1% hàng, index trên trang_thai có thể có ích hơn.

### 22.1. Thống kê giúp tối ưu hóa

Optimizer có thể dùng:

- Tổng số hàng.
- Số giá trị phân biệt (NDV).
- Histogram/phân bố tần suất.
- Tương quan giữa các cột.
- Thống kê index/table.
- Số hàng ước lượng sau từng điều kiện.

Nếu thống kê cũ hoặc dữ liệu rất lệch, kế hoạch có thể không tốt ngay cả khi WHERE hoàn toàn SARGable.

### 22.2. Không tạo index theo mọi điều kiện

Mỗi index tốn:

- Dung lượng.
- Chi phí INSERT/UPDATE/DELETE.
- Công bảo trì và thống kê.
- Nguy cơ optimizer phải lựa chọn giữa nhiều index tương tự.

Tạo index phải dựa trên **truy vấn trọng yếu và đo lường**, không phải một công thức “mỗi cột WHERE một index”.

## 23. Covering index và index-only scan

Một chỉ mục có thể đáp ứng cả lọc lẫn các cột cần trả nếu nó chứa đủ thông tin.

Ví dụ:

~~~sql
SELECT ma_khach, ngay_dat
FROM don_hang
WHERE ma_khach = :ma
  AND ngay_dat >= :start_time
  AND ngay_dat < :end_time;
~~~

Với index (ma_khach,ngay_dat), các cột SELECT đều nằm trong key, có thể là ứng viên cho index-only/covering execution.

Nhưng điều kiện thực tế khác nhau:

- PostgreSQL index-only scan còn phụ thuộc **visibility map/MVCC**.
- SQL Server có **INCLUDE columns** và clustered key/lookup semantics.
- MySQL/InnoDB secondary indexes kèm primary key theo cấu trúc, nhưng “Using index” cần xem đủ cột.
- Oracle có index access và table access by rowid.
- SQLite có **COVERING INDEX** trong plan.

Việc query chỉ chọn cột trong index **không bảo đảm** máy sẽ không cần truy cập dữ liệu nền trong mọi hệ.

## 24. Function-based/expression indexes: khi biểu thức thật sự cần thiết

Nếu nhu cầu nghiệp vụ liên tục truy vấn theo **LOWER(email)** hoặc **DATE(ngay_dat)**, có thể lập chỉ mục **trên chính biểu thức**, thay vì buộc mọi truy vấn thay đổi ý nghĩa.

### 24.1. PostgreSQL expression index

~~~sql
CREATE INDEX idx_kh_lower_email_pg
ON khach_hang ((LOWER(email)));
~~~

Truy vấn:

~~~sql
SELECT ma_khach
FROM khach_hang
WHERE LOWER(email) = LOWER(:email);
~~~

có thể dùng expression index nếu optimizer thấy có lợi.

### 24.2. Oracle function-based index

~~~sql
CREATE INDEX idx_kh_lower_email_ora
ON khach_hang (LOWER(email));
~~~

Oracle có cơ chế function-based index với điều kiện hàm/cấu hình phù hợp.

### 24.3. SQLite expression index

~~~sql
CREATE INDEX idx_kh_lower_email_sqlite
ON khach_hang (LOWER(email));
~~~

SQLite chú ý **sự tương ứng biểu thức** giữa WHERE và định nghĩa index và giới hạn đối với hàm không deterministic.

### 24.4. MySQL functional index hoặc generated column

MySQL 8.0.13+ hỗ trợ functional key parts trong các điều kiện nhất định:

~~~sql
CREATE INDEX idx_kh_lower_email_mysql
ON khach_hang ((LOWER(email)));
~~~

Ngoài ra có thể dùng generated column rồi lập chỉ mục. Cần kiểm tra hạn chế phiên bản, kiểu kết quả biểu thức, collation và index key length.

### 24.5. SQL Server computed column index

SQL Server thường dùng **computed column** (và index) với biểu thức đáp ứng tính determinism, precision, SET options và điều kiện được yêu cầu:

~~~sql
ALTER TABLE dbo.khach_hang
ADD email_lower AS LOWER(email);

CREATE INDEX idx_kh_email_lower
ON dbo.khach_hang (email_lower);
~~~

Không phải mọi biểu thức computed column đều indexable. Khi query dùng LOWER(email), việc optimizer khớp biểu thức với computed index phụ thuộc quy tắc/phiên bản/cấu hình; truy vấn trực tiếp theo email_lower thường dễ kiểm soát hơn ở những trường hợp cần thiết.

### 24.6. Giá phải trả

Expression/function index cần được duy trì khi dữ liệu thay đổi. Nó có thể tốn dung lượng, CPU, memory, và dễ mang semantics phụ thuộc collation/timezone/hàm. Không thêm chỉ mục biểu thức chỉ vì một truy vấn viết chưa tối ưu.

## 25. Generated column để lưu dạng chuẩn hóa

Một cách khác là tạo **cột chuẩn hóa**:

~~~text
email            = 'Sales@Example.com'
email_search_key = 'sales@example.com'
~~~

Sau đó:

~~~sql
WHERE email_search_key = :normalized_email
~~~

và lập index trên email_search_key.

Ưu điểm:
- Cột dùng trong WHERE là cột trực tiếp.
- Có thể tạo constraint/index cho dạng chuẩn.
- Tách chính sách canonicalization khỏi mỗi truy vấn.

Nhược điểm:
- Cần duy trì nhất quán.
- Generated/computed syntax và hàm deterministic khác theo DBMS.
- Chuẩn hóa case/Unicode phải phù hợp yêu cầu.
- Nếu dùng cột thường do ứng dụng cập nhật, có nguy cơ email thay đổi nhưng email_search_key chưa đổi.

**Một cột chuẩn hóa là lựa chọn mô hình dữ liệu**, không chỉ mẹo tăng tốc.

## 26. LIKE, index và chuẩn hóa văn bản đa ngôn ngữ

Trong dữ liệu tiếng Việt, so sánh chữ hoa/thường, dấu và Unicode normalization có thể phức tạp:

~~~text
Hoa
Hòa
HOA
Hoà
~~~

Không thể mặc định LOWER hoặc collation case-insensitive sẽ giải quyết cả phân biệt dấu, cách mã hóa Unicode và quy tắc ngôn ngữ.

### 26.1. Hệ quả hiệu năng

Nếu query dùng:

~~~sql
WHERE LOWER(ten_hien_thi) LIKE 'hoa%'
~~~

index B-tree trên ten_hien_thi thường không trực tiếp là index trên LOWER(ten_hien_thi).

Có thể cần:
- Expression index trên LOWER(ten_hien_thi).
- Collation phù hợp.
- Pattern operator class chuyên biệt.
- Full-text/trigram/ngram tùy nhu cầu.

### 26.2. Hệ quả tính đúng

Nếu yêu cầu tìm đúng mã phân biệt chữ hoa, việc chuyển LOWER toàn bộ cột là **sai nghiệp vụ**. Hãy xác định **case-sensitive vs insensitive**, **accent-sensitive vs insensitive**, normalization và thứ tự so sánh trước khi tối ưu.

## 27. Implicit conversion có thể xuất hiện ở ORDER BY và GROUP BY

Không chỉ WHERE/JOIN mới chuyển kiểu.

Ví dụ một cột version lưu VARCHAR có giá trị:

~~~text
2
9
10
100
~~~

Nếu ORDER BY phiên bản như chuỗi:

~~~sql
ORDER BY version_text DESC
~~~

thứ tự có thể là dạng từ điển, không phải số học. Nếu dùng CAST trong ORDER BY:

~~~sql
ORDER BY CAST(version_text AS INTEGER) DESC
~~~

kết quả theo số đúng hơn khi mọi chuỗi hợp lệ, nhưng index thường trên version_text không nhất thiết cung cấp thứ tự kết quả số.

Giải pháp lâu dài: lưu version bằng kiểu **INTEGER/BIGINT** hoặc có cột số chuẩn hóa và index phù hợp.

### 27.1. Không giả định CAST giúp sửa dữ liệu bẩn

Nếu có 'v10', 'unknown', chuỗi rỗng hoặc số vượt giới hạn, CAST có thể lỗi. Phải có chính sách validate/reject hoặc parse dữ liệu hợp lệ, không chỉ áp CAST lúc ORDER BY.

### 27.2. GROUP BY trên biểu thức

~~~sql
GROUP BY DATE(ngay_dat)
~~~

có thể hữu ích về nghiệp vụ nhưng việc nhóm theo DATE trên hàng triệu timestamp cần tính toán/sort/hash. Expression index hoặc cột ngày phát sinh có thể giúp một số kế hoạch, nhưng không phải mọi GROUP BY sẽ tự trở thành seek/range.

## 28. OR và IN: không phải cứ OR là không dùng index

Giả sử:

~~~sql
WHERE trang_thai = 'MOI'
   OR trang_thai = 'HUY'
~~~

có thể tương đương về logic với:

~~~sql
WHERE trang_thai IN ('MOI', 'HUY')
~~~

Nếu trang_thai không NULL, cả hai chọn cùng hai giá trị. Với NULL, cả hai vẫn không chọn hàng NULL theo logic thông thường.

Một số DBMS có thể tối ưu OR bằng **multiple index probes, bitmap, index union hoặc scan**; IN thường biểu đạt tập giá trị bằng gọn hơn. Không kết luận OR luôn gây full scan.

### 28.1. OR trên hai cột khác nhau

~~~sql
WHERE ma_khach = :ma
   OR trang_thai = 'HUY'
~~~

có thể cần hai index hoặc plan tổng hợp nhiều kết quả. Nếu một nhánh lọc quá rộng, optimizer có thể chọn scan.

### 28.2. Viết UNION ALL phải chú ý trùng hàng

Thay OR bằng UNION ALL ở hai truy vấn **có thể tạo hàng trùng** nếu một hàng thỏa cả hai điều kiện. UNION lại có thể tốn công loại trùng. Chỉ viết lại khi đã chứng minh **tương đương ngữ nghĩa** và đo lợi ích thực.

## 29. NOT EQUAL, NOT LIKE và điều kiện phủ định

~~~sql
WHERE trang_thai <> 'HUY'
~~~

có thể trả phần lớn bảng; dù là biểu thức trực tiếp trên cột, một index seek không nhất thiết hiệu quả.

~~~sql
WHERE email NOT LIKE 'test%'
~~~

cũng có thể cần quét nhiều vùng vì tập giá trị “không bắt đầu bằng test” thường rất rộng.

Nếu nghiệp vụ chỉ quan tâm vài trạng thái, có thể dùng tập rõ:

~~~sql
WHERE trang_thai IN ('MOI', 'DA_GIAO')
~~~

**chỉ khi** đúng cùng yêu cầu; không được thay bỏ HUY bằng một danh sách không đầy đủ nếu có trạng thái mới.

### 29.1. NOT IN và NULL

~~~sql
WHERE ma_khach NOT IN (SELECT ma_khach FROM danh_sach_cam)
~~~

có thể có kết quả bất ngờ nếu subquery chứa NULL. Dùng NOT EXISTS đúng tương quan khi nghĩa là “không có bản ghi tương ứng”. Đây là vấn đề **logic dữ liệu** trước khi nói tới index.

## 30. BETWEEN, cận khoảng và NULL

BETWEEN bao gồm hai cận:

~~~sql
WHERE tong_tien BETWEEN 100000 AND 200000
~~~

tương đương về logic:

~~~sql
WHERE tong_tien >= 100000
  AND tong_tien <= 200000
~~~

trong những ngữ cảnh kiểu và NULL tương thích.

Với timestamp, khi phân đoạn ngày nên dùng **cận trên loại trừ** để không bỏ sót phần giây hoặc đếm trùng ranh giới.

### 30.1. Giá trị biên ảnh hưởng kế hoạch

Nếu khoảng rộng gần cả bảng, một index range scan có thể không phải lựa chọn tốt. Khoảng hẹp thường có lợi hơn. Hãy so **estimated rows** và **actual rows** sau khi thay đổi predicate.

### 30.2. Không chuyển cột sang kiểu ngày chỉ để loại giờ

~~~sql
WHERE CAST(ngay_dat AS DATE) = :d
~~~

có thể mang nghĩa đúng trên một số DBMS, nhưng thường kém khả chuyển và có nguy cơ ảnh hưởng index. Hãy dùng hai mốc timestamp đúng timezone nếu đó là ý nghĩa mong muốn.

## 31. LIKE số, mã điện thoại và dẫn đầu bằng số 0

Mã bưu chính, số điện thoại, số tài khoản hoặc mã nhân viên có thể chứa ký tự số nhưng bản chất là **identifier**, không phải đại lượng số học.

Ví dụ:

~~~text
00001234
01234
+84123456789
AB0123
~~~

Lưu các giá trị này thành INTEGER/BIGINT sẽ làm mất định dạng hoặc không thể lưu ký tự. So chúng bằng parameter số có thể gây implicit conversion không đúng.

Nếu dữ liệu được lưu VARCHAR:

~~~sql
WHERE so_dien_thoai = :phone_text
~~~

và bind string với normalization được kiểm soát.

Nếu cần tìm prefix:

~~~sql
WHERE so_dien_thoai LIKE :prefix_pattern
~~~

với pattern được dựng/escape đúng. Không dùng **CAST(so_dien_thoai AS BIGINT)** để “giúp chỉ mục nhanh hơn”, vì đó là thay đổi nghĩa dữ liệu.

## 32. Parameterization từ Java/JDBC

Ví dụ tìm đơn theo khóa BIGINT và khoảng timestamp:

~~~java
String sql = """
    SELECT ma_don, ngay_dat, tong_tien
    FROM don_hang
    WHERE ma_don = ?
      AND ngay_dat >= ?
      AND ngay_dat < ?
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setLong(1, 1001L);
    ps.setTimestamp(2, Timestamp.valueOf(
        "2026-10-03 00:00:00"
    ));
    ps.setTimestamp(3, Timestamp.valueOf(
        "2026-10-04 00:00:00"
    ));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("ma_don"));
        }
    }
}
~~~

Đây là ví dụ cho cột TIMESTAMP không kèm timezone và quy tắc mốc đã xác định. Ứng dụng thật nên sử dụng kiểu **LocalDate/LocalDateTime/Instant/OffsetDateTime** phù hợp driver và schema, cùng timezone nghiệp vụ rõ ràng, thay vì phụ thuộc parse timestamp dạng chuỗi.

### 32.1. Bind đúng kiểu

| Cột DB | Kiểu bind/JDBC gợi ý | Tránh |
|---|---|---|
| BIGINT ma_don | setLong | setString cho ID số khi không cần |
| VARCHAR ma_khach | setString | setLong vì mã có thể có số 0 đầu |
| DECIMAL tong_tien | setBigDecimal | setDouble khi cần tiền chính xác |
| DATE | setDate / LocalDate theo driver | chuỗi ngày phụ thuộc locale |
| TIMESTAMP | setTimestamp / kiểu thời gian tương thích | ghép chuỗi datetime |
| BOOLEAN/bit | setBoolean theo DBMS | gửi text 'true' không kiểm soát |

### 32.2. PreparedStatement không bảo đảm tự chọn index

Tham số hóa:
- Giúp chống SQL injection.
- Giúp rõ kiểu dữ liệu.
- Giảm lỗi escape/format.
- Có thể hỗ trợ plan reuse.

Nhưng vẫn cần index phù hợp, thống kê, chọn lọc và điều kiện SARGable. Driver có thể ánh xạ kiểu Java sang kiểu SQL khác với bạn dự đoán; nên kiểm tra kiểu bind trong môi trường thật.

### 32.3. Một ví dụ sai kiểu về mã

~~~java
String sql = "SELECT * FROM ma_thanh_vien WHERE ma_the = ?";
ps.setLong(1, 123L);
~~~

Nếu người dùng muốn mã **00123**, đoạn trên làm mất số 0 đầu ngay trước khi gửi SQL. Không có index nào cứu được sai nghĩa này. Phải dùng:

~~~java
ps.setString(1, "00123");
~~~

## 33. Kế hoạch thực thi: phương pháp đánh giá

Không nên kết luận chỉ từ việc SQL trông “đẹp”. Hãy khảo sát:

1. **Lấy truy vấn thật** và tham số đại diện.
2. **Xác nhận schema và kiểu cột, loại index**, collation, constraint.
3. **Xem EXPLAIN/actual plan** trước thay đổi.
4. Tìm **seek/range predicate**, residual filters, implicit casts và access path.
5. Đo **rows read/returned, logical reads, CPU, elapsed time** trong điều kiện tương đương.
6. Viết lại predicate hoặc sửa kiểu bind, không làm đổi nghiệp vụ.
7. Chạy kế hoạch sau thay đổi với dữ liệu/tham số giống nhau.
8. Kiểm tra kết quả và trường hợp biên, không chỉ tốc độ.
9. Đánh giá ảnh hưởng với tham số có độ chọn lọc khác.
10. Chỉ sau đó cân nhắc thêm/thay index.

### 33.1. Những dấu hiệu thường thấy

**PostgreSQL:**
- Index Cond vs Filter.
- Index Scan, Index Only Scan, Bitmap Index Scan, Seq Scan.
- Estimated vs Actual Rows.
- Buffers, planning/execution time.

**MySQL:**
- type: const, ref, range, index, ALL.
- possible_keys, key, rows, filtered.
- EXPLAIN ANALYZE trên phiên bản hỗ trợ.

**SQL Server:**
- Index Seek, Index Scan, Clustered Index Scan.
- Seek Predicates vs Predicate.
- CONVERT_IMPLICIT, PlanAffectingConvert warning.
- Estimated/Actual Row Count, logical reads, CPU.

**Oracle:**
- INDEX RANGE SCAN, INDEX UNIQUE SCAN, TABLE ACCESS FULL.
- Predicate Information với functions/conversions.
- DBMS_XPLAN và số liệu thực khi có quyền/công cụ.

**SQLite:**
- EXPLAIN QUERY PLAN với SEARCH/SCAN/USING INDEX/COVERING INDEX.

### 33.2. Đừng đo riêng một lần chạy

Cache có thể khiến lần chạy thứ hai nhanh hơn, plan caching và parameter sniffing ảnh hưởng kết quả, concurrent workloads thay đổi độ trễ, dữ liệu và statistics có thể không đồng nhất. Nên so nhiều lần và dùng chỉ số thích hợp, ưu tiên truy vấn đại diện cho workload thật.

### 33.3. EXPLAIN ANALYZE thực thi lệnh

Đặc biệt với UPDATE/DELETE/INSERT, những hình thức **ANALYZE** thực thi câu lệnh có thể thay đổi dữ liệu. Không thực hiện trên production một cách tùy tiện; nếu phải thử DML, dùng môi trường thử nghiệm hoặc giao dịch rollback được hỗ trợ và hiểu side effects ngoài giao dịch.

## 34. Trường hợp khó: index có mà optimizer vẫn bỏ qua

### 34.1. Bảng quá nhỏ

Bảng 100 dòng: đọc cả bảng có thể rẻ hơn seek và lookup.

### 34.2. Tỷ lệ kết quả quá lớn

Điều kiện chọn 80% hàng: scan có thể tốt hơn.

### 34.3. Thống kê lỗi thời

Ước lượng 10 hàng trong khi thực tế 1 triệu hàng, optimizer có thể chọn nested loops/index lookup không phù hợp.

### 34.4. Index có thứ tự cột không khớp

WHERE chỉ lọc ngày_dat nhưng index dẫn đầu bằng tenant_id,trang_thai.

### 34.5. Cột trả về quá nhiều

~~~sql
SELECT *
~~~

lấy nhiều cột ngoài index, tạo chi phí lookup. Nhưng không được tùy ý bỏ các cột ứng dụng thực sự cần.

### 34.6. Chuyển kiểu/collation khác

CAST ngầm trên cột hoặc so collation không tương thích có thể làm index predicate kém hiệu quả.

### 34.7. Hàm hoặc wildcard đầu chuỗi

YEAR(ngay_dat), LOWER(email), LIKE '%abc%' không tương ứng trực tiếp với index gốc.

### 34.8. Parallelism và memory

Bộ tối ưu có thể chọn parallel scan/hash join vì tổng chi phí thấp hơn hàng loạt seeks.

**Cần tách vấn đề “không SARGable” khỏi vấn đề “optimizer cố ý không chọn index dù có thể seek”.**

## 35. Partial/filtered indexes và điều kiện khớp

Trong nhiều ứng dụng, bảng có cột **deleted_at** hoặc **trang_thai**; truy vấn thường chỉ xét hàng đang hoạt động.

PostgreSQL có **partial index**:

~~~sql
CREATE INDEX idx_dh_moi_pg
ON don_hang (tenant_id, ngay_dat)
WHERE trang_thai = 'MOI';
~~~

Query:

~~~sql
WHERE tenant_id = :tenant
  AND trang_thai = 'MOI'
  AND ngay_dat >= :start_time
  AND ngay_dat < :end_time
~~~

có thể dùng partial index khi planner chứng minh predicate query bao hàm điều kiện index, với chú ý việc chứng minh phụ thuộc dạng predicate và parameterization.

SQL Server có **filtered index** với quy tắc riêng. SQLite cũng có partial index. MySQL không có một cơ chế partial index tổng quát tương đương cú pháp trên. Oracle có những mẫu function-based index/thiết kế thay thế tùy mục tiêu.

### 35.1. Điều kiện SQL cần tương thích

Nếu index chỉ chứa trang_thai='MOI' mà query dùng trạng thái tham số không rõ ở plan compile, optimizer có thể không chứng minh nó luôn nằm trong vùng index. Đây là lý do có trường hợp literal và parameter cho kế hoạch khác, ngay cả khi ở runtime tham số là 'MOI'.

### 35.2. Không đánh đổi khả chuyển

Mỗi DBMS có một cơ chế khác nhau. Nếu ứng dụng cần đa DB, có thể chọn index phổ thông và tối ưu riêng theo môi trường, thay vì cố dùng partial index bằng cú pháp không hỗ trợ.

## 36. Partition pruning và conversion

Nếu bảng don_hang được partition theo ngay_dat, điều kiện:

~~~sql
WHERE ngay_dat >= :start_time
  AND ngay_dat < :end_time
~~~

có thể giúp optimizer loại bỏ những partition ngoài khoảng, tùy thiết kế partition và DBMS.

Nhưng:

~~~sql
WHERE DATE(ngay_dat) = :day
~~~

hoặc implicit conversion trên partition key có thể làm pruning khó hơn, tương tự vấn đề index seek.

Có những DBMS tối ưu được expression/partition bounds chuyên biệt, nên phải xem plan. **Partition pruning không đồng nghĩa index seek**: một partition có thể vẫn bị scan.

## 37. Sắp xếp số dưới dạng chuỗi: một ví dụ kết quả sai

Giả sử:

~~~text
order_id_text
1
2
10
20
100
~~~

Nếu ORDER BY theo văn bản tăng dần:

~~~sql
ORDER BY order_id_text
~~~

thứ tự có thể là:

~~~text
1, 10, 100, 2, 20
~~~

Trong khi theo số học:

~~~text
1, 2, 10, 20, 100
~~~

Không nên chữa bằng CAST mỗi query mãi mãi khi đây thực sự là ID số. Cần migrate/chuẩn hóa kiểu dữ liệu và index phù hợp.

Nhưng nếu order_id_text là **mã có ý nghĩa độ dài và số 0 đầu**, thứ tự từ điển có thể là đúng. **Kiểu dữ liệu và nhu cầu nghiệp vụ quyết định**, không phải chỉ vì tất cả ký tự là chữ số.

## 38. So kiểu DECIMAL, FLOAT và giá trị tiền

Cột:

~~~sql
tong_tien DECIMAL(14, 2)
~~~

nên so với decimal parameter đúng kiểu:

~~~sql
WHERE tong_tien >= :threshold_decimal
~~~

Nếu parameter là DOUBLE/FLOAT, có thể xảy ra chuyển kiểu và sai số nhị phân. Một số DBMS dùng kiểu ưu tiên làm cột DECIMAL bị chuyển sang kiểu approximate trong biểu thức, làm thay đổi kết quả/khả năng tối ưu.

**Đừng gửi giá tiền từ Java bằng double nếu yêu cầu chính xác.** Dùng BigDecimal và setBigDecimal với scale/phương pháp rounding đã thống nhất.

### 38.1. Một cận 100.00 khác 99.995

Nếu nguồn input có nhiều chữ số sau dấu thập phân hơn cột, DBMS có thể round hoặc cast khác nhau, làm điều kiện biên không giống dự định. Validate input và đặt kiểu/scale rõ.

### 38.2. Không chỉ đo plan, còn phải so kết quả

Sau khi đổi kiểu bind từ FLOAT sang DECIMAL, kế hoạch có thể tốt hơn hoặc khác, nhưng quan trọng là những đơn có tong_tien **đúng biên** được xử lý theo cùng chính sách.

## 39. Dữ liệu và index của cột boolean/trạng thái ít giá trị

Nếu trang_thai có năm giá trị và phần lớn đơn là DA_GIAO, chỉ mục riêng trên trang_thai không phải lúc nào cũng hữu ích.

Nhưng trong index ghép:

~~~sql
(tenant_id, trang_thai, ngay_dat)
~~~

cột trang_thai có thể hữu ích khi kết hợp với tenant và khoảng ngày. Cũng có thể dùng partial index cho một trạng thái hiếm trên DBMS hỗ trợ.

### 39.1. Low cardinality không đồng nghĩa không bao giờ index

Nếu truy vấn chủ yếu lấy 0,01% hàng trạng thái MOI của một tenant cụ thể, một index phù hợp có thể rất giá trị. Ngược lại, nếu lọc trạng thái hiếm nhưng SELECT trả cột rộng và phải truy cập nhiều trang ngẫu nhiên, kế hoạch thực tế cần đo.

## 40. Cách sửa từng tình huống thường gặp

| Tình huống | Dạng cần xem | Cách sửa thường nên thử |
|---|---|---|
| Trích ngày từ timestamp | DATE(ngay_dat)=:d | Lọc [start,next_day) |
| Trích năm | YEAR(ngay_dat)=2026 | Lọc [2026-01-01,2027-01-01) |
| Mã VARCHAR so số | ma_the=123 | Bind text '00123' đúng mã |
| BIGINT so text | ma_don=:text_id | Bind BIGINT hoặc cast parameter |
| Nối chữ hoa | LOWER(email)=LOWER(:email) | Case-insensitive collation/expression index |
| Phép cộng trên cột | tong_tien+10000>500000 | tong_tien>490000 khi tương đương |
| Giá trị mặc định NULL | COALESCE(x,0)>=0 | x>=0 OR x IS NULL nếu đúng nghĩa |
| Chuỗi chứa ở giữa | LIKE '%abc%' | Full-text/trigram/search index phù hợp |
| JOIN key khác kiểu | bigint_key=text_key | Chuẩn hóa schema/typed staging |
| Xếp số lưu text | ORDER BY CAST(version AS INT) | Cột version numeric/index phù hợp |
| Cột có timezone transform | DATE(convert_tz(ts,...))=:d | Tính ranh giới instant từ ứng dụng |
| Composite index lệch prefix | WHERE C=:c với index(A,B,C) | Thiết kế index theo workload |
| Nhiều hàng trả về | WHERE status='DONE' trên 99% bảng | Chấp nhận scan hoặc lọc hẹp hơn nếu đúng |
| Param VARCHAR/NVARCHAR lệch | Indexed VARCHAR so NVARCHAR | Căn kiểu cột/bind, kiểm tra collation/plan |
| Implicit decimal→float | DECIMAL so FLOAT | Bind Decimal/BigDecimal chính xác |
| Query dùng function thường xuyên | LOWER(col)=... | Expression/generated/computed index |
| Chỉ index nullable cột ở Oracle | col IS NULL | Xem cấu trúc B-tree NULL, expression/composite |
| Partition key bị bọc hàm | CAST(partition_key AS ...) | Predicate trực tiếp cùng kiểu |

Đây là **ý tưởng để kiểm chứng**, không phải một bảng hứa chắc kế hoạch nào sẽ xuất hiện.

## 41. Sai lầm phổ biến khi nói về SARGability

1. **“Cứ có index là DBMS phải dùng.”** Sai: optimizer chọn theo chi phí.
2. **“Cứ thấy Index Scan là chậm.”** Sai: scan có thể tối ưu cho tập lớn/covering.
3. **“Mọi hàm trên cột chắc chắn full scan.”** Quá tuyệt đối; có expression index và nhận diện đặc biệt.
4. **“Implicit conversion luôn chuyển cột.”** Sai: có thể chuyển literal/parameter hoặc không có chuyển kiểu hợp lệ.
5. **“Cột bên trái dấu bằng sẽ không bị CAST.”** Sai: type precedence không phụ thuộc vị trí văn bản đơn giản.
6. **“Số nào cũng có thể gửi String.”** Không nên: semantics và plan có thể đổi.
7. **“Mã gồm toàn chữ số thì nên lưu INT.”** Không khi mã có số 0 đầu/ý nghĩa định danh.
8. **“LIKE 'abc%' luôn seek.”** Phụ thuộc collation, operator class, pattern và kế hoạch.
9. **“IS NULL không bao giờ dùng index.”** Sai ở nhiều hệ; Oracle có ngoại lệ quan trọng về all-null B-tree entries.
10. **“Mọi hàm LOWER giống nhau ở mọi ngôn ngữ.”** Sai: Unicode/collation và case folding phức tạp.
11. **“Viết lại x + 1 = 5 thành x = 4 luôn hợp lệ.”** Chỉ khi kiểu/overflow/NULL và quy tắc toán học bảo đảm.
12. **“EXPLAIN chỉ để nhìn có chữ INDEX.”** Cần đọc seek predicate, residual filter và số hàng.
13. **“Cứ thêm index cho mọi cột WHERE.”** Gây chi phí ghi/bảo trì.
14. **“Chỉ cần tối ưu WHERE, không cần xét SELECT *.”** Số cột trả về/lookup có thể chi phối chi phí.
15. **“YEAR(timestamp) và khoảng UTC đều đúng như nhau.”** Có thể khác do timezone/ngày địa phương.
16. **“Đổi kiểu bind không thể đổi kết quả.”** Có thể đổi do số 0 đầu, FLOAT/DECIMAL, collation.
17. **“Tối ưu cho tham số điển hình là đủ.”** Dữ liệu skew và plan caching có thể khiến trường hợp khác xấu.
18. **“Chuyển kiểu trong JOIN chỉ ảnh hưởng tốc độ.”** Còn có lỗi dữ liệu, sai match và cardinality.
19. **“EXPLAIN ANALYZE DML chỉ mô phỏng.”** Nhiều DBMS thực thi thao tác thật.
20. **“SARGable nghĩa chắc chắn nhanh.”** Đây chỉ là điều kiện hữu ích, không phải kết quả đo hiệu năng.

## 42. Bộ ca kiểm thử cho điều kiện và chuyển kiểu

| Trường hợp | Điều cần kiểm tra |
|---|---|
| Numeric ID với bind BIGINT | Trả đúng hàng, access path phù hợp |
| Numeric ID với bind String | Có conversion/lỗi/kế hoạch khác không |
| VARCHAR mã '00123' | Không trộn với '123' |
| VARCHAR mã chứa chữ | Không gây lỗi ép số không mong muốn |
| Timestamp đúng đầu ngày | Được chọn bởi cận >= |
| Timestamp đúng đầu ngày kế tiếp | Không được chọn bởi cận < |
| Timestamp có micro/nanoseconds | Không bị bỏ sót cuối ngày |
| Múi giờ khác UTC | Mốc địa phương đúng |
| Ngày DST | Hai mốc theo calendar, không cộng cứng 24 giờ |
| NULL trong điều kiện | Logic UNKNOWN đúng |
| COALESCE với NULL | Viết lại có giữ kết quả không |
| DECIMAL đúng ngưỡng | Không lệch do FLOAT |
| LIKE prefix | Collation và index phù hợp |
| LIKE chứa wildcard do user nhập | Escape literal %/_ đúng |
| LOWER với tiếng Việt | Không gộp/bỏ dấu sai |
| JOIN cột khác kiểu | So được và không lỗi dữ liệu |
| ORDER BY numeric-as-text | Thứ tự theo nghĩa mong muốn |
| Index ghép đủ leading keys | Seek/range có khả năng |
| Bỏ cột dẫn đầu | Kế hoạch có thể thay đổi |
| Status có 99% cùng giá trị | Scan có thể hợp lý |
| Status rất hiếm | Index có thể hữu ích |
| Index-only query | Không đọc bảng nền khi điều kiện hệ cho phép |
| Function-based index | Query expression khớp index |
| Partial index và param | Planner có chứng minh predicate không |
| Partition pruning | Chỉ đọc partition cần thiết |
| Tài khoản/driver khác | Kiểu bind và plan nhất quán |
| Data lớn vs nhỏ | Không kết luận từ vài dòng test |
| Stats cũ vs mới | Kế hoạch khác hay không |
| Prepared plan với tham số lệch | Không phụ thuộc duy nhất một giá trị |
| DML EXPLAIN ANALYZE | Không làm thay đổi production ngoài ý muốn |

## 43. Bài tập thực hành có đáp án

Các bài tập dùng bảng và chỉ mục ở phần 2 hoặc bảng giả lập được mô tả trong câu hỏi. Mỗi bài độc lập; không yêu cầu chạy trên production.

### Bài 1 — Định nghĩa SARGable

Giải thích vì sao WHERE ngay_dat >= :a AND ngay_dat < :b thường có lợi hơn WHERE DATE(ngay_dat)=:d khi đã có B-tree index trên ngay_dat.

<details>
<summary>Đáp án</summary>

Điều kiện khoảng so trực tiếp trên giá trị timestamp của cột, nên optimizer có cơ hội tìm dải khóa trong B-tree. DATE(ngay_dat) áp hàm trên cột, index thường theo timestamp không nhất thiết có thứ tự theo kết quả DATE. Có thể dùng expression index hoặc tối ưu đặc biệt, nên phải kiểm tra plan.

</details>

### Bài 2 — Lọc một ngày

Viết WHERE cho đơn trong ngày 03/10/2026 bằng khoảng nửa mở.

<details>
<summary>Đáp án</summary>

~~~sql
WHERE ngay_dat >= :start_of_oct_03
  AND ngay_dat < :start_of_oct_04
~~~

Hai tham số phải là timestamp đúng đầu ngày theo timezone/kiểu dữ liệu được dùng.

</details>

### Bài 3 — Cận cuối ngày

Vì sao BETWEEN '2026-10-03 00:00:00' AND '2026-10-03 23:59:59' có thể bỏ sót đơn?

<details>
<summary>Đáp án</summary>

Vì timestamp có thể có phần giây sau 23:59:59. Dùng cận trên loại trừ đầu ngày 04/10.

</details>

### Bài 4 — Lọc năm

Viết lại điều kiện YEAR(ngay_dat)=2026 theo khoảng thời gian.

<details>
<summary>Đáp án</summary>

~~~sql
WHERE ngay_dat >= :start_2026
  AND ngay_dat < :start_2027
~~~

Phải xác định năm theo múi giờ nghiệp vụ nếu timestamp lưu UTC.

</details>

### Bài 5 — Phép cộng trên cột

Viết lại tong_tien + 10000 > 500000 thành điều kiện trực tiếp trên cột trong miền DECIMAL bình thường.

<details>
<summary>Đáp án</summary>

~~~sql
WHERE tong_tien > 490000
~~~

Cần bảo đảm tính tương đương về kiểu, overflow và NULL trong ứng dụng thực.

</details>

### Bài 6 — Không thay đổi ngữ nghĩa mã

Bảng ma_the VARCHAR có '00123' và '123'. Vì sao WHERE ma_the = 123 có thể nguy hiểm?

<details>
<summary>Đáp án</summary>

Một số DBMS có thể chuyển mã sang số, coi hai mã cùng giá trị 123, làm mất số 0 đầu và có thể ảnh hưởng index. Dùng WHERE ma_the = '00123' và bind text đúng kiểu.

</details>

### Bài 7 — Phía chuyển kiểu

Với cột BIGINT có index và input String '1001', hai dạng sau khác nhau ra sao?

~~~sql
WHERE ma_don = CAST(:id AS BIGINT)
WHERE CAST(ma_don AS VARCHAR(30)) = :id
~~~

<details>
<summary>Đáp án</summary>

Dạng đầu giữ cột BIGINT nguyên dạng, chuyển input sang số. Dạng sau áp CAST lên cột, thường bất lợi cho index BIGINT và có thể thay đổi quy tắc so chuỗi. Tốt nhất bind BIGINT trực tiếp khi đây là ID số.

</details>

### Bài 8 — JDBC bind

Cột ma_don BIGINT nên dùng setLong hay setString?

<details>
<summary>Đáp án</summary>

Thông thường **setLong** cho ID số BIGINT. setString có thể khiến implicit conversion/suy kiểu ngoài ý muốn.

</details>

### Bài 9 — Identifier dạng chuỗi

Cột ma_the VARCHAR có mã 00123 nên dùng ps.setLong(123) hay ps.setString("00123")?

<details>
<summary>Đáp án</summary>

**setString("00123")**, vì đó là mã định danh và số 0 đầu mang ý nghĩa.

</details>

### Bài 10 — SQL Server CONVERT_IMPLICIT

Điều gì đáng chú ý nếu execution plan có CONVERT_IMPLICIT(int, ma_the, ...) ở phía cột VARCHAR được index?

<details>
<summary>Đáp án</summary>

Cột có thể bị chuyển sang INT cho từng hàng, gây rủi ro lỗi với mã không phải số, đổi semantics và ảnh hưởng seek/ước lượng. Cần so kiểu bind với định nghĩa cột, đọc seek vs residual predicate và đo actual plan. Không kết luận chỉ từ một warning.

</details>

### Bài 11 — SQL Server Unicode parameter

Vì sao VARCHAR indexed column so với NVARCHAR parameter cần kiểm tra plan?

<details>
<summary>Đáp án</summary>

Type precedence/collation có thể dẫn tới chuyển kiểu, ảnh hưởng cách dùng index. Một số trường hợp SQL Server vẫn seek được; cần xem CONVERT_IMPLICIT và actual plan, không mặc định luôn full scan.

</details>

### Bài 12 — PostgreSQL text bind vs BIGINT

Vì sao parameter đã được định kiểu TEXT không luôn so trực tiếp với BIGINT giống một literal chưa định kiểu?

<details>
<summary>Đáp án</summary>

PostgreSQL có giải quyết operator và suy kiểu cho literal chưa có kiểu, nhưng không cung cấp mọi implicit cast giữa các kiểu đã định. Có thể cần bind BIGINT hoặc CAST parameter sang BIGINT, không CAST cột BIGINT sang TEXT tùy tiện.

</details>

### Bài 13 — MySQL chuỗi so với số

Vì sao WHERE ma_the = 123 trên cột VARCHAR có thể trả nhiều mã khác nhau?

<details>
<summary>Đáp án</summary>

MySQL có thể dùng quy tắc so sánh dạng số, khiến '00123' và '123' cùng được coi là 123. Không được dựa vào phép so này để tìm mã định danh duy nhất.

</details>

### Bài 14 — Oracle mã văn bản

Nếu cột VARCHAR2 có 'AB123' nhưng so với NUMBER bind, rủi ro gì?

<details>
<summary>Đáp án</summary>

Oracle có thể chuyển VARCHAR2 sang NUMBER ở phía cột và gặp **ORA-01722 invalid number**. Nên bind text nếu cột là mã; nếu giá trị thật sự là số, thiết kế schema/validation phù hợp.

</details>

### Bài 15 — Oracle ngày giờ

Vì sao WHERE ngay_dat = '03/10/2026' có thể không an toàn trên Oracle?

<details>
<summary>Đáp án</summary>

Vì implicit date conversion có thể phụ thuộc NLS_DATE_FORMAT và so bằng một DATE chứa giờ có thể không lấy đủ một ngày. Dùng typed bind/date literal và khoảng [start,next_day).

</details>

### Bài 16 — SQLite EXPLAIN

Lệnh gì giúp xem SQLite có dùng index cho câu SELECT không?

<details>
<summary>Đáp án</summary>

~~~sql
EXPLAIN QUERY PLAN
SELECT *
FROM khach_hang
WHERE email = ?;
~~~

Đọc SEARCH/SCAN và index được dùng.

</details>

### Bài 17 — LIKE prefix

So sánh khả năng dùng B-tree với LIKE 'sale%' và LIKE '%sale%'.

<details>
<summary>Đáp án</summary>

LIKE 'sale%' có khả năng dùng dải prefix theo quy tắc collation/index của DBMS. LIKE '%sale%' thường không có prefix cố định nên B-tree thông thường khó seek trực tiếp. Không phải mọi DBMS/index đều tối ưu LIKE prefix trong mọi collation.

</details>

### Bài 18 — LIKE và wildcard nhập từ người dùng

Nếu người dùng muốn tìm literal '_' trong email, có nên ghép trực tiếp '_' vào LIKE không?

<details>
<summary>Đáp án</summary>

Không. '_' là wildcard một ký tự. Cần escape wildcard theo cú pháp DBMS và bind tham số, đồng thời tránh SQL injection.

</details>

### Bài 19 — LOWER(email)

Index trên email có tự động tương đương index trên LOWER(email) không?

<details>
<summary>Đáp án</summary>

**Không.** Có thể cần expression/function-based index, computed/generated column hoặc collation case-insensitive phù hợp.

</details>

### Bài 20 — Collation tiếng Việt

LOWER có tự bảo đảm “Hòa” và “Hoa” so bằng nhau không?

<details>
<summary>Đáp án</summary>

**Không.** LOWER chỉ xử lý case theo quy tắc hệ; accent sensitivity, Unicode normalization và collation là vấn đề riêng. Phải định nghĩa nghiệp vụ trước khi thiết kế index.

</details>

### Bài 21 — COALESCE với NULL

Điều kiện COALESCE(so_luong,0)>=0 có tương đương so_luong>=0 không?

<details>
<summary>Đáp án</summary>

**Không.** Khi so_luong NULL, COALESCE cho 0 và điều kiện TRUE, còn so_luong>=0 trả UNKNOWN. Muốn tương đương:

~~~sql
WHERE so_luong >= 0
   OR so_luong IS NULL
~~~

theo ngữ nghĩa NULL được xem 0.

</details>

### Bài 22 — Oracle IS NULL

Vì sao không thể khẳng định index B-tree một cột nullable trong Oracle luôn hỗ trợ WHERE col IS NULL?

<details>
<summary>Đáp án</summary>

Oracle B-tree thường không lưu index entry khi **mọi cột khóa đều NULL**. Với index chỉ một cột nullable, các hàng col NULL có thể vắng khỏi index; composite/function-based index có thể thay đổi khả năng xử lý.

</details>

### Bài 23 — JOIN lệch kiểu

Một bảng lưu customer_id BIGINT, bảng khác lưu customer_id VARCHAR. Tác động nào có thể xảy ra khi JOIN?

<details>
<summary>Đáp án</summary>

Có thể phát sinh implicit conversion hoặc lỗi operator, ảnh hưởng hiệu quả index, ước lượng cardinality và thậm chí kết quả match. Nên chuẩn hóa kiểu khóa tham chiếu từ schema/staging.

</details>

### Bài 24 — Composite index

Cho index (tenant_id,trang_thai,ngay_dat). Query nào phù hợp hơn?

A. Chỉ WHERE ngay_dat BETWEEN :a AND :b.  
B. WHERE tenant_id=:tenant AND trang_thai='MOI' AND ngay_dat>=:a AND ngay_dat<:b.

<details>
<summary>Đáp án</summary>

**B** thường phù hợp hơn với prefix của B-tree: hai equality conditions rồi range trên cột thứ ba. Nhưng kế hoạch vẫn phụ thuộc thống kê, dữ liệu và DBMS.

</details>

### Bài 25 — Index prefix

Với index(A,B,C), WHERE A=:a AND C=:c có chắc dùng được C như một dải seek hẹp không?

<details>
<summary>Đáp án</summary>

**Không chắc.** Thiếu điều kiện B có thể khiến C chỉ là residual filter hoặc cần tối ưu đặc biệt như skip scan. Phải xem access path của DBMS.

</details>

### Bài 26 — Trình tự AND

Đảo thứ tự các điều kiện AND trong văn bản WHERE có phải cách chính để tối ưu composite index không?

<details>
<summary>Đáp án</summary>

**Không.** Thứ tự cột index, khả năng optimizer nhận predicate, kiểu dữ liệu, selectivity và statistics quan trọng hơn trình tự viết AND.

</details>

### Bài 27 — Selectivity

Nếu WHERE trang_thai='DA_GIAO' trả 99% bảng, index scan/seek có nhất thiết nhanh hơn table scan không?

<details>
<summary>Đáp án</summary>

**Không.** Đọc phần lớn bảng qua index rồi lookup có thể đắt hơn scan tuần tự. Optimizer có thể đúng khi chọn scan.

</details>

### Bài 28 — Index covering

Vì sao SELECT các cột nằm hết trong index có thể rẻ hơn SELECT *?

<details>
<summary>Đáp án</summary>

Có thể tránh hoặc giảm lookup bảng nền nhờ covering/index-only path, nhưng chi tiết còn phụ thuộc MVCC, cấu trúc index và DBMS. Không được bỏ cột ứng dụng cần chỉ để giảm chi phí.

</details>

### Bài 29 — Function-based index

Viết một expression index PostgreSQL để tối ưu điều kiện LOWER(email)=LOWER(:email).

<details>
<summary>Đáp án</summary>

~~~sql
CREATE INDEX idx_kh_lower_email
ON khach_hang ((LOWER(email)));
~~~

Truy vấn vẫn cần đúng expression, kiểu/collation và optimizer phải thấy có lợi.

</details>

### Bài 30 — SQL Server computed column

SQL Server thường dùng cơ chế gì để index trên LOWER(email) nếu không dùng index expression trực tiếp như PostgreSQL?

<details>
<summary>Đáp án</summary>

Dùng **computed column** đáp ứng điều kiện indexability và index trên cột tính toán đó, ví dụ:

~~~sql
ALTER TABLE dbo.khach_hang
ADD email_lower AS LOWER(email);

CREATE INDEX idx_lower_email
ON dbo.khach_hang (email_lower);
~~~

Cần kiểm tra determinism, precision, SET options và tương thích phiên bản.

</details>

### Bài 31 — Partial index

Với PostgreSQL partial index WHERE trang_thai='MOI', một truy vấn dùng trang_thai=:param có luôn tận dụng index nếu runtime param='MOI' không?

<details>
<summary>Đáp án</summary>

**Không bảo đảm.** Planner cần chứng minh predicate của query phù hợp điều kiện partial index tại lúc lập kế hoạch; tham số chưa biết/generic plan có thể cản việc chứng minh.

</details>

### Bài 32 — Partition pruning

Cột ngay_dat là partition key. Vì sao DATE(ngay_dat)=:d có thể kém thuận lợi hơn so khoảng timestamp?

<details>
<summary>Đáp án</summary>

Biểu thức trên partition key có thể làm khó suy ra partition bounds; khoảng trực tiếp thường tạo cơ hội pruning rõ hơn. Một số DBMS nhận diện phép biến đổi đặc biệt, nên cần xem plan.

</details>

### Bài 33 — Plan không dùng index

Query WHERE ma_don=:id đã SARGable nhưng optimizer chọn scan. Có phải SQL chắc chắn sai?

<details>
<summary>Đáp án</summary>

**Không.** Bảng nhỏ, tỷ lệ kết quả lớn, thống kê, chi phí lookup hoặc kế hoạch song song có thể khiến scan rẻ hơn. Cần xem actual rows/reads và đo trước khi sửa.

</details>

### Bài 34 — EXPLAIN ANALYZE

Vì sao không nên chạy EXPLAIN ANALYZE UPDATE tùy tiện trên production?

<details>
<summary>Đáp án</summary>

Trong nhiều DBMS, ANALYZE **thực sự thực thi DML**, có thể thay đổi dữ liệu. Chỉ thử trên môi trường an toàn hoặc transaction có kiểm soát và hiểu side effects.

</details>

### Bài 35 — Kiểu tiền

Một cột DECIMAL(14,2) nên bind từ Java bằng BigDecimal hay double khi cần số tiền chính xác?

<details>
<summary>Đáp án</summary>

**BigDecimal / setBigDecimal** thường phù hợp. Double có sai số biểu diễn nhị phân và có thể dẫn tới chuyển kiểu không mong muốn trong so sánh.

</details>

### Bài 36 — Tổng hợp tối ưu

Một truy vấn tìm đơn của tenant T1 trong ngày 03/10/2026 và trạng thái MOI. Có index (tenant_id,trang_thai,ngay_dat). Viết WHERE thân thiện với index và giải thích vì sao.

<details>
<summary>Đáp án</summary>

~~~sql
SELECT ma_don, ngay_dat
FROM don_hang
WHERE tenant_id = :tenant_id
  AND trang_thai = 'MOI'
  AND ngay_dat >= :start_of_oct_03
  AND ngay_dat < :start_of_oct_04;
~~~

Hai điều kiện bằng trên các cột đầu index, sau đó khoảng trên ngay_dat, không có DATE(ngay_dat), giúp optimizer có cơ hội tra cứu B-tree theo prefix. Mốc thời gian và kiểu bind phải đúng timezone/schema; kế hoạch thực tế cần kiểm tra bằng EXPLAIN.

</details>

### Bài 37 — Phân biệt sai nghĩa và sai plan

Cột ma_the VARCHAR có 00123 và 123. Khi WHERE ma_the=123 vô tình trả hai hàng, đây chỉ là vấn đề hiệu năng hay còn là vấn đề tính đúng?

<details>
<summary>Đáp án</summary>

Là **cả hai**: chuyển mã thành số có thể làm hai mã khác nhau cùng bằng 123 và giảm khả năng index seek theo chuỗi. Việc sửa đúng phải bắt đầu từ xác định mã là VARCHAR và bind '00123' chính xác.

</details>

### Bài 38 — Một quyết định thiết kế

Ứng dụng thường xuyên tìm nhân viên theo UPPER(ten_hien_thi). Có nên ngay lập tức tạo function index không?

<details>
<summary>Đáp án</summary>

Không nhất thiết. Đầu tiên xác nhận quy tắc tìm kiếm hoa/thường, dấu, Unicode/collation và độ chọn lọc. Sau đó xem EXPLAIN; nếu cần có thể tạo expression index, generated/computed column hoặc chọn collation/search index phù hợp, cân nhắc chi phí ghi.

</details>

## 44. Tình huống thực tế: từ một truy vấn chậm tới thiết kế phù hợp

Giả sử ứng dụng có bảng don_hang hàng chục triệu dòng và câu SQL:

~~~sql
SELECT ma_don, ma_khach, ngay_dat, tong_tien
FROM don_hang
WHERE tenant_id = :tenant
  AND trang_thai = :status
  AND DATE(ngay_dat) = :day;
~~~

Ứng dụng cũng bind :tenant bằng String, :status bằng String, còn :day bằng String có định dạng tự tạo.

### 44.1. Phân tích theo thứ tự

**Tầng ngữ nghĩa**

- Tenant đã lấy từ ngữ cảnh xác thực đúng chưa?
- Trạng thái có được chuẩn hóa không?
- Người dùng muốn ngày theo timezone nào?
- Giá trị ở đầu/cuối ngày được tính chính xác chưa?

**Tầng dữ liệu**

- Cột tenant_id/trang_thai là VARCHAR hay loại khác?
- ngay_dat là TIMESTAMP, TIMESTAMP WITH TIME ZONE, DATETIME hay loại khác?
- Mã khóa liên kết, tenant, collation có nhất quán không?

**Tầng chỉ mục**

- Index (tenant_id,trang_thai,ngay_dat) có tồn tại không?
- Stats đã được cập nhật?
- Tỷ lệ kết quả của tenant/status/day là bao nhiêu?

**Tầng truy vấn**

- DATE(ngay_dat) tạo biểu thức trên cột.
- Bind :day dạng text có thể gây chuyển kiểu phụ thuộc DBMS/NLS/locale.
- SELECT nhiều cột có thể cần lookup.

### 44.2. Viết lại

~~~sql
SELECT ma_don, ma_khach, ngay_dat, tong_tien
FROM don_hang
WHERE tenant_id = :tenant
  AND trang_thai = :status
  AND ngay_dat >= :start_time
  AND ngay_dat < :end_time;
~~~

Ở Java, tính **start_time/end_time** theo calendar ngày địa phương rồi chuyển sang kiểu thời gian tương thích cột; bind đúng kiểu thay vì chuỗi ngày.

### 44.3. Kiểm tra kế hoạch

So kế hoạch trước/sau về:
- Index được chọn.
- Index Cond/Seek Predicates.
- Residual DATE conversion có còn không.
- Rows read và rows returned.
- Logical reads/CPU/time.
- Khả năng dùng prefix của composite index.

### 44.4. Kiểm tra lại kết quả

- Đơn đúng 00:00 ngày đang xem được chọn.
- Đơn cuối ngày có phần giây được chọn.
- Đơn đúng 00:00 ngày kế tiếp bị loại.
- Tenant khác không bị trả.
- Status khác không bị trả.
- Tác dụng khi DST/timezone khác.
- Các giá trị NULL và tham số không hợp lệ được xử lý theo chính sách.

**Không tuyên bố truy vấn “nhanh gấp X lần” khi chưa thực sự đo.** Một rewrite hợp lý là bước mở cơ hội tối ưu, không phải lời hứa về kết quả trên mọi hệ.

## 45. Tổng kết cốt lõi

1. **SARGable** là khả năng điều kiện hỗ trợ DBMS dùng search argument để tra cứu index; nó không có nghĩa optimizer chắc chắn chọn index.
2. Với B-tree thường, ưu tiên điều kiện **so trực tiếp cột với hằng/parameter tương thích**, đặc biệt equality và khoảng [start,end).
3. Hàm **DATE/YEAR/LOWER/UPPER/COALESCE/CAST** trên cột có thể cản index gốc, trừ khi optimizer có biến đổi đặc biệt hoặc có expression index thích hợp.
4. **Implicit conversion không luôn ở phía cột**. Phải xét kiểu cột, literal, bind, type precedence/operator resolution, collation và DBMS.
5. Conversion trên **cột indexed** thường rủi ro hơn conversion ở phía tham số vì có thể cần biến đổi nhiều giá trị và làm thứ tự chỉ mục không còn phù hợp phép so.
6. **Mã định danh** như 00123, số điện thoại và mã bưu chính không tự là số; bind sai kiểu có thể làm **sai dữ liệu**, không chỉ chậm.
7. Cột **BIGINT** nên nhận tham số số đúng kiểu; cột **VARCHAR** biểu thị mã nên nhận text; tiền **DECIMAL** nên dùng BigDecimal.
8. **SQL Server CONVERT_IMPLICIT**, **MySQL numeric-string comparison**, **Oracle TO_NUMBER/NLS**, **PostgreSQL operator typing**, **SQLite affinity** có các quy tắc khác nhau; không sao chép một giả định giữa hệ.
9. Lọc timestamp theo **khoảng nửa mở** thường rõ về ngữ nghĩa và thuận lợi cho index; phải chuẩn hóa timezone/DST đúng.
10. **LIKE 'abc%'** có thể tận dụng prefix index trong điều kiện phù hợp; **LIKE '%abc%'** thường cần công cụ tìm kiếm khác nếu dữ liệu lớn.
11. Index **ghép** chịu ảnh hưởng lớn của thứ tự cột: equality trên prefix, rồi range là mẫu đáng thử.
12. **Statistics, selectivity, covering index, lookup cost, partition pruning và plan caching** cũng quyết định kết quả; một điều kiện SARGable vẫn có thể scan.
13. Nếu biểu thức trên cột là nhu cầu thật, cân nhắc **function-based/expression index** hoặc **generated/computed column**, không chỉ sửa SQL bằng mẹo.
14. **EXPLAIN/actual plan** và đo logical reads/rows là cơ sở đánh giá; tuyệt đối không coi kế hoạch tưởng tượng là benchmark.
15. Mỗi rewrite phải giữ **tính đúng ở NULL, giá trị biên, timezone, collation, scale, overflow và ID có số 0 đầu**.
16. Tư duy tốt là hỏi **cột đã lập chỉ mục có bị biến đổi trước khi so không; điều kiện tạo được vùng khóa nào; kiểu bind có khớp cột không; và plan thực tế đã chứng minh điều đó chưa?**

### Tài liệu tham khảo chính thức nên dùng

Đối chiếu **đúng DBMS và phiên bản** khi triển khai:

- **PostgreSQL Documentation:** Indexes, Indexes on Expressions, Index Types, Operator Classes, Collation, EXPLAIN, Statistics Used by the Planner, Type Conversion.
- **Microsoft Learn — SQL Server:** Data Type Precedence, CAST and CONVERT, Implicit Conversions, Execution Plans, Seek Predicates, Index Architecture, Computed Column Indexes, Parameter Sniffing.
- **MySQL Reference Manual:** Type Conversion in Expression Evaluation, EXPLAIN, Range Optimization, Functional Key Parts, Generated Column Indexes, Comparison Functions and Operators.
- **Oracle Database SQL Language Reference / Performance Tuning Guide:** Data Type Comparison Rules, Implicit Conversion, Function-Based Indexes, SQL Tuning, EXPLAIN PLAN and DBMS_XPLAN.
- **SQLite Documentation:** Datatypes In SQLite, Comparison Expressions, EXPLAIN QUERY PLAN, Indexes On Expressions, Query Planner, LIKE Optimization.
- **Java JDBC:** PreparedStatement, typed setters, temporal types and BigDecimal.

**Thông điệp cuối cùng:** Một chỉ mục chỉ phát huy tác dụng khi **cách lưu khóa**, **cách viết điều kiện**, **kiểu dữ liệu của tham số** và **kế hoạch mà optimizer chọn** phối hợp đúng với nhau. Hãy tối ưu bằng truy vấn rõ nghĩa, tránh chuyển đổi ngầm không cần thiết và xác minh bằng execution plan — đồng thời luôn bảo toàn kết quả nghiệp vụ.
