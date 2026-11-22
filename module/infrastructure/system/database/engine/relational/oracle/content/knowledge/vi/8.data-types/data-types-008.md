# INTERVAL YEAR TO MONTH và INTERVAL DAY TO SECOND

Trong Oracle Database, hai kiểu dữ liệu **INTERVAL YEAR TO MONTH** và **INTERVAL DAY TO SECOND** dùng để biểu diễn **khoảng thời gian** thay vì một thời điểm cụ thể. Chúng phù hợp khi mô tả một hợp đồng có chu kỳ 18 tháng, một công việc kéo dài 2 ngày 3 giờ, một phiên chạy mất 90,5 giây hoặc thời hạn cần cộng thêm vào một ngày/giờ bắt đầu.

Điểm quan trọng là Oracle **tách khoảng thời gian lịch (năm, tháng)** khỏi **khoảng thời gian theo ngày, giờ, phút, giây**. Một tháng không có số ngày cố định, nên hai nhóm khoảng thời gian này không thể mặc nhiên quy đổi cho nhau. Hiểu sự khác nhau giúp tránh lỗi khi tính hạn hợp đồng, lịch gia hạn, thời lượng xử lý, thời điểm hết hạn hoặc các kết quả phép trừ ngày/giờ.

## 1. INTERVAL khác DATE và TIMESTAMP như thế nào?

| Kiểu Oracle | Diễn tả | Ví dụ ý nghĩa |
| --- | --- | --- |
| **DATE** | Một ngày/giờ; Oracle DATE còn chứa giờ, phút, giây | Đơn hàng được tạo lúc 09:30:00 ngày 15/01/2024 |
| **TIMESTAMP** | Một ngày/giờ với phần giây phân số; có các biến thể có múi giờ | Thời điểm log sự kiện 09:30:00.125 |
| **INTERVAL YEAR TO MONTH** | Độ dài theo đơn vị năm và tháng | Chu kỳ gia hạn 1 năm 6 tháng |
| **INTERVAL DAY TO SECOND** | Độ dài theo ngày, giờ, phút, giây và phần giây | Công việc hoàn tất sau 1 ngày 2 giờ 30 phút |
| **NUMBER** | Đại lượng số học, chỉ mang ý nghĩa thời gian khi có quy ước rõ | Số phút cấu hình là 90 hoặc hiệu DATE trừ DATE tính theo ngày |

Một **thời điểm** trả lời “khi nào?”, trong khi một **interval** trả lời “bao lâu?” hoặc “dịch chuyển lịch bao nhiêu?”. Các thao tác phổ biến là cộng một interval vào DATE/TIMESTAMP để tìm thời điểm khác, trừ hai thời điểm để tính khoảng cách, hoặc so sánh hai interval cùng nhóm.

~~~text
TIMESTAMP bắt đầu              + INTERVAL DAY TO SECOND
2024-05-10 08:00:00             + 0 ngày 02:30:00
                 |
                 v
TIMESTAMP kết thúc
2024-05-10 10:30:00

DATE bắt đầu                    + INTERVAL YEAR TO MONTH
2024-01-15                     + 0 năm 3 tháng
                 |
                 v
DATE kết thúc
2024-04-15
~~~

Dù đều diễn tả “thời gian”, **INTERVAL YEAR TO MONTH không thể mặc định tương đương một số giây cố định**, còn **INTERVAL DAY TO SECOND không phải cách nêu số tháng lịch**. Ví dụ, tháng 2 năm nhuận có 29 ngày, trong khi tháng 3 có 31 ngày.

## 2. INTERVAL YEAR TO MONTH: số năm và số tháng

### 2.1. Cấu trúc và ý nghĩa

Kiểu này chứa hai trường:

- **YEAR**: số năm của khoảng thời gian.
- **MONTH**: số tháng còn lại trong thành phần của khoảng thời gian khi biểu diễn dưới dạng YEAR TO MONTH.

Khai báo một cột:

~~~sql
CREATE TABLE hop_dong_demo (
    ma_hop_dong NUMBER(6) PRIMARY KEY,
    chu_ky      INTERVAL YEAR(3) TO MONTH NOT NULL
);
~~~

Trong **YEAR(3)**, số 3 là **độ chính xác của trường năm đứng đầu** (*leading field precision*): cho phép tối đa ba chữ số năm ở phần leading của khoảng thời gian. Đây không phải “ba chữ số thập phân”. Cột có thể lưu khoảng thời gian như 1 năm 6 tháng hoặc 125 năm 11 tháng trong giới hạn phù hợp.

Cú pháp kiểu đầy đủ:

~~~sql
INTERVAL YEAR [(year_precision)] TO MONTH
~~~

Khi không chỉ định, **year_precision mặc định là 2**. Trong Oracle, giới hạn precision của leading field thuộc khoảng được hỗ trợ đến 9 chữ số. Cần chọn precision dựa trên miền dữ liệu: hợp đồng dài vài tháng khác với một tập dữ liệu mô phỏng hàng trăm năm.

### 2.2. Literal YEAR TO MONTH

~~~sql
-- 1 năm 6 tháng
SELECT INTERVAL '1-6' YEAR TO MONTH AS chu_ky
FROM dual;

-- 3 năm, không thêm tháng
SELECT INTERVAL '3' YEAR AS ba_nam
FROM dual;

-- 9 tháng
SELECT INTERVAL '9' MONTH AS chin_thang
FROM dual;

-- 123 năm 11 tháng: cần độ chính xác năm ít nhất 3
SELECT INTERVAL '123-11' YEAR(3) TO MONTH AS ky_dai
FROM dual;

-- Khoảng âm: lùi 6 tháng
SELECT -INTERVAL '6' MONTH AS lui_sau_thang
FROM dual;
~~~

Các dạng **YEAR**, **MONTH**, **YEAR TO MONTH** đều tạo giá trị thuộc nhóm interval năm–tháng, với độ chính xác/biểu diễn tương ứng.

Đối với literal dạng YEAR TO MONTH, thành phần tháng phía sau dấu nối là **0–11**. Muốn biểu diễn 14 tháng, có thể ghi **1 năm 2 tháng** hoặc dùng hàm nhận số tháng để Oracle chuẩn hóa:

~~~sql
SELECT INTERVAL '1-2' YEAR TO MONTH AS mot_nam_hai_thang
FROM dual;

SELECT NUMTOYMINTERVAL(14, 'MONTH') AS muoi_bon_thang
FROM dual;
~~~

Không dùng literal dạng **INTERVAL '1-14' YEAR TO MONTH** để diễn tả 1 năm 14 tháng; thành phần tháng 14 vượt phạm vi hợp lệ của dạng YEAR TO MONTH. Giống như tháng trong lịch, phần trường con phải tuân theo miền giá trị của nó.

### 2.3. Dương, âm và số 0

~~~sql
SELECT INTERVAL '0-0' YEAR TO MONTH AS khong_thang,
       INTERVAL '2-3' YEAR TO MONTH AS hai_nam_ba_thang,
       -INTERVAL '2-3' YEAR TO MONTH AS am_hai_nam_ba_thang
FROM dual;
~~~

Dấu âm áp dụng cho **toàn khoảng thời gian**, không phải phép trừ năm rồi cộng tháng độc lập. Khi giao diện cần hiển thị hoặc xử lý dấu, nên xác định quy ước rõ ràng: số tháng tổng có dấu hay cặp năm/tháng có dấu, tránh tự tách chuỗi ký tự hiển thị theo định dạng phụ thuộc client.

### 2.4. Các bài toán phù hợp

- Chu kỳ gia hạn: 1 tháng, 6 tháng, 1 năm.
- Tuổi hoặc thời hạn được định nghĩa theo **lịch năm–tháng**.
- Thời gian bảo hành hoặc thời hạn hợp đồng, khi quy tắc nghiệp vụ sử dụng tháng lịch.
- Công việc định kỳ diễn ra “sau N tháng”, không phải “sau N × 30 ngày”.

Lưu ý: một hợp đồng “hết hạn sau một tháng” cần quy định cụ thể cách xử lý **ngày cuối tháng**, không thể chỉ chọn kiểu interval là đủ để giải quyết toàn bộ ngữ nghĩa nghiệp vụ.

## 3. INTERVAL DAY TO SECOND: ngày, giờ, phút, giây

### 3.1. Cấu trúc và độ chính xác

Kiểu này biểu diễn khoảng thời gian theo các trường **DAY, HOUR, MINUTE, SECOND**, trong đó SECOND có thể chứa phần giây phân số.

~~~sql
CREATE TABLE cong_viec_demo (
    ma_cong_viec NUMBER(6) PRIMARY KEY,
    thoi_luong   INTERVAL DAY(3) TO SECOND(3) NOT NULL
);
~~~

Với **DAY(3) TO SECOND(3)**:

- **DAY(3)**: trường ngày đứng đầu có tối đa ba chữ số.
- **SECOND(3)**: phần giây phân số có độ chính xác ba chữ số, tương ứng mức mili giây.
- Các thành phần giờ, phút, giây phải nằm trong phạm vi hợp lệ của cấu trúc interval; ngày là trường leading nên có thể lớn hơn một ngày.

Cú pháp đầy đủ:

~~~sql
INTERVAL DAY [(day_precision)] TO SECOND [(fractional_seconds_precision)]
~~~

Giá trị mặc định thường gặp là **DAY(2)** và **SECOND(6)** khi không chỉ định precision. Trong Oracle, cả leading precision và fractional seconds precision có thể được khai báo đến giới hạn 9. Nếu ứng dụng đo thời gian ở mức mili giây, **SECOND(3)** dễ thể hiện mong muốn hơn kiểu có nhiều chữ số phân số không cần thiết.

### 3.2. Literal DAY TO SECOND

~~~sql
-- 1 ngày, 2 giờ, 3 phút, 4 giây và 125 mili giây
SELECT INTERVAL '1 02:03:04.125' DAY TO SECOND(3) AS khoang_1
FROM dual;

-- 3 ngày
SELECT INTERVAL '3' DAY AS ba_ngay
FROM dual;

-- 5 giờ
SELECT INTERVAL '5' HOUR AS nam_gio
FROM dual;

-- 90 phút
SELECT INTERVAL '90' MINUTE AS chin_muoi_phut
FROM dual;

-- 30.250 giây
SELECT INTERVAL '30.250' SECOND(3) AS ba_muoi_giay
FROM dual;

-- 123 ngày cần leading precision đủ lớn
SELECT INTERVAL '123 04:05:06.789' DAY(3) TO SECOND(3) AS khoang_dai
FROM dual;
~~~

Các literal với trường bắt đầu là HOUR, MINUTE hoặc SECOND vẫn thuộc họ **INTERVAL DAY TO SECOND**. Khi dùng dạng **DAY TO SECOND**, trường ngày đứng đầu có thể chứa nhiều ngày, còn thành phần giờ thường trong phạm vi 0–23, phút và giây trong phạm vi 0–59 trước phần giây phân số.

Không viết **INTERVAL '1 25:00:00' DAY TO SECOND** nếu ý định là 1 ngày 25 giờ. Hãy chuẩn hóa thành 2 ngày 1 giờ hoặc dùng **NUMTODSINTERVAL(25, 'HOUR')** để Oracle tính toán khoảng tương đương.

### 3.3. Phần giây phân số

~~~sql
SELECT INTERVAL '0 00:00:01.250' DAY TO SECOND(3) AS mot_phay_hai_lam_giay
FROM dual;

SELECT INTERVAL '0 00:00:01.123456' DAY TO SECOND(6) AS vi_giay
FROM dual;

SELECT INTERVAL '0 00:00:01.123456789' DAY TO SECOND(9) AS nano_giay
FROM dual;
~~~

Độ chính xác lưu trữ là đặc tính kiểu dữ liệu/giá trị Oracle. Nó **không chứng minh thiết bị đo, đồng hồ hệ điều hành hoặc sự kiện thực tế có độ chính xác đến nano giây**. Nếu hệ thống đầu vào chỉ ghi thời gian đến mili giây, khai báo SECOND(9) không tự tạo thêm thông tin thực.

### 3.4. Khoảng âm, bằng 0 và chưa biết

~~~sql
SELECT -INTERVAL '0 00:15:00' DAY TO SECOND AS cham_hon_15_phut
FROM dual;

SELECT INTERVAL '0 00:00:00' DAY TO SECOND AS bang_khong
FROM dual;
~~~

**NULL** nghĩa là khoảng thời gian chưa được cung cấp hoặc không xác định theo mô hình dữ liệu; **INTERVAL 0** nghĩa là biết chắc thời lượng bằng không. Hai trường hợp phải được xử lý khác nhau trong phép tính và báo cáo.

## 4. So sánh trực tiếp hai nhóm INTERVAL

| Tiêu chí | INTERVAL YEAR TO MONTH | INTERVAL DAY TO SECOND |
| --- | --- | --- |
| Đơn vị | Năm, tháng | Ngày, giờ, phút, giây, phần giây |
| Đặc tính | Khoảng lịch | Khoảng có thể quy về tổng giây, theo đơn vị ngày 24 giờ |
| Ví dụ | 1 năm 6 tháng | 2 ngày 3 giờ 15 phút |
| Cột | INTERVAL YEAR(3) TO MONTH | INTERVAL DAY(4) TO SECOND(3) |
| Literal | INTERVAL '1-6' YEAR TO MONTH | INTERVAL '2 03:15:00' DAY TO SECOND |
| Hàm nhận số | NUMTOYMINTERVAL | NUMTODSINTERVAL |
| Hàm chuyển chuỗi | TO_YMINTERVAL | TO_DSINTERVAL |
| Phép cộng điển hình | TIMESTAMP + chu kỳ tháng | TIMESTAMP + thời lượng xử lý |
| Vấn đề đặc trưng | Ngày cuối tháng, năm nhuận | Độ chính xác phần giây, duration và múi giờ |

Không có một quy tắc tổng quát rằng **1 tháng = 30 ngày** hoặc **1 năm = 365 ngày**. Những quy đổi như vậy chỉ được áp dụng khi nghiệp vụ tự định nghĩa một quy ước đặc biệt, không phải ngữ nghĩa mặc định của Oracle interval.

## 5. Cộng, trừ INTERVAL với DATE và TIMESTAMP

### 5.1. Cộng khoảng năm–tháng vào thời điểm

~~~sql
SELECT DATE '2024-01-15' + INTERVAL '2' MONTH AS sau_hai_thang
FROM dual;

SELECT TIMESTAMP '2024-01-15 09:30:00'
       + INTERVAL '1-6' YEAR TO MONTH AS sau_mot_nam_sau_thang
FROM dual;
~~~

Ở ví dụ đầu, ngày được dịch từ **15/01/2024** đến **15/03/2024**. Ví dụ hai dịch theo lịch thêm 1 năm 6 tháng, trong khi giữ phần giờ tương ứng khi ngày kết quả hợp lệ.

### 5.2. Bẫy ngày cuối tháng: INTERVAL khác ADD_MONTHS

Xét ngày 31/01/2024:

~~~sql
-- Cố ý minh họa tình huống lỗi ngày không tồn tại:
SELECT DATE '2024-01-31' + INTERVAL '1' MONTH AS ngay_moi
FROM dual;
~~~

Ngày **31/02/2024** không tồn tại. Trong trường hợp này, phép cộng kiểu INTERVAL YEAR TO MONTH có thể phát sinh lỗi ngày không hợp lệ, chẳng hạn **ORA-01839**.

Oracle có hàm **ADD_MONTHS** với quy tắc xử lý cuối tháng riêng:

~~~sql
SELECT ADD_MONTHS(DATE '2024-01-31', 1) AS ngay_het_han
FROM dual;
~~~

Kết quả là **29/02/2024** vì 2024 là năm nhuận và hàm xử lý theo quy tắc cuối tháng. Tương tự, thêm 12 tháng vào ngày 29/02/2024 bằng ADD_MONTHS đưa về ngày cuối tháng 2 của năm 2025 theo quy tắc của hàm.

**Không coi phép cộng INTERVAL '1' MONTH và ADD_MONTHS(..., 1) luôn tương đương ở ngày biên.** Nếu xử lý chu kỳ thanh toán, hạn hợp đồng, lịch gửi thông báo hoặc gia hạn, hãy quy định rõ việc xử lý ngày cuối tháng và chọn cơ chế phù hợp.

### 5.3. Cộng khoảng ngày–giây

~~~sql
SELECT TIMESTAMP '2024-02-28 23:59:30.000'
       + INTERVAL '0 00:01:00.250' DAY TO SECOND(3) AS sau_mot_phut
FROM dual;
~~~

Kết quả theo giá trị timestamp không múi giờ là **2024-02-29 00:00:30.250**. Khoảng DAY TO SECOND cho phép diễn tả chính xác hơn việc cộng một số ngày thập phân vào DATE khi có giờ, phút, giây phân số.

~~~sql
SELECT TIMESTAMP '2024-03-10 10:00:00'
       - INTERVAL '45' MINUTE AS tru_bon_muoi_lam_phut
FROM dual;
~~~

Có thể sử dụng dấu âm trước literal hoặc toán tử trừ giữa thời điểm và khoảng. Đặc biệt, **TIMESTAMP không nên được xử lý bằng cách cộng số nguyên như DATE cộng số ngày**. Hãy sử dụng interval để nêu đơn vị của khoảng thời gian.

### 5.4. Phép trừ DATE và TIMESTAMP khác nhau

~~~sql
-- DATE trừ DATE trả NUMBER với đơn vị ngày.
SELECT DATE '2024-03-02' - DATE '2024-03-01' AS so_ngay
FROM dual;

-- TIMESTAMP trừ TIMESTAMP trả INTERVAL DAY TO SECOND.
SELECT TIMESTAMP '2024-03-02 01:30:00'
       - TIMESTAMP '2024-03-01 00:00:00' AS khoang_thoi_gian
FROM dual;
~~~

Câu thứ nhất trả **NUMBER = 1**. Câu thứ hai trả khoảng tương đương **1 ngày 1 giờ 30 phút**. Đây là một khác biệt lớn khi thiết kế câu SQL tính độ trễ:

- Với hai DATE, hiệu trả về số ngày, có thể có phần thập phân do giờ/phút/giây.
- Với hai TIMESTAMP, hiệu là một giá trị INTERVAL DAY TO SECOND, có thể EXTRACT ngày, giờ, phút, giây.
- Với dữ liệu hỗn hợp DATE và TIMESTAMP, nên ép kiểu một cách tường minh nếu muốn kiểm soát kiểu kết quả.

Ví dụ ép DATE thành TIMESTAMP:

~~~sql
SELECT CAST(DATE '2024-03-02' AS TIMESTAMP)
       - CAST(DATE '2024-03-01' AS TIMESTAMP) AS khoang_ngay
FROM dual;
~~~

### 5.5. Lưu ý về múi giờ và giờ mùa hè

**TIMESTAMP** thông thường không mang thông tin múi giờ; **TIMESTAMP WITH TIME ZONE** và **TIMESTAMP WITH LOCAL TIME ZONE** có ngữ nghĩa lưu trữ/chuyển đổi khác. Khi cộng khoảng thời gian vào dữ liệu có múi giờ và qua thời điểm đổi giờ mùa hè (DST), cần xác định rõ mong muốn:

- “Sau đúng 24 giờ đã trôi qua” có thể khác với “cùng giờ địa phương của ngày lịch tiếp theo”.
- “Gia hạn sau một tháng” khác với “sau 30 ngày × 24 giờ”.
- Kết quả có thể chịu tác động của quy tắc múi giờ, kiểu timestamp, phiên làm việc và chính sách chuyển giờ.

Không dùng ví dụ TIMESTAMP không múi giờ để suy ra hành vi DST của ứng dụng thực tế. Khi nghiệp vụ nhạy cảm múi giờ, thử trực tiếp với kiểu timestamp và vùng giờ được triển khai.

## 6. Hàm tạo và chuyển đổi INTERVAL

Oracle cung cấp những hàm hữu ích khi đầu vào là số hoặc chuỗi thay vì một literal viết cố định trong SQL.

### 6.1. NUMTOYMINTERVAL: số năm/tháng sang YEAR TO MONTH

~~~sql
SELECT NUMTOYMINTERVAL(18, 'MONTH') AS ky_mot_nam_sau_thang
FROM dual;

SELECT NUMTOYMINTERVAL(2, 'YEAR') AS ky_hai_nam
FROM dual;
~~~

Hàm nhận **NUMBER** và đơn vị như YEAR hoặc MONTH, trả giá trị INTERVAL YEAR TO MONTH. Khi số tháng là 18, Oracle biểu diễn khoảng tương đương 1 năm 6 tháng. Hàm này phù hợp khi số tháng nhận từ cột cấu hình hoặc bind variable Java.

### 6.2. NUMTODSINTERVAL: số ngày/giờ/phút/giây

~~~sql
SELECT NUMTODSINTERVAL(90, 'MINUTE') AS chin_muoi_phut
FROM dual;

SELECT NUMTODSINTERVAL(1.25, 'DAY') AS mot_phay_hai_lam_ngay
FROM dual;

SELECT NUMTODSINTERVAL(5400.125, 'SECOND') AS nam_nghin_bon_tram_giay
FROM dual;
~~~

Các đơn vị thường dùng gồm **DAY, HOUR, MINUTE, SECOND**. Số đầu vào có thể là giá trị phân số khi ngữ nghĩa phù hợp, ví dụ 1.25 ngày hoặc 5400.125 giây.

Hàm tạo interval từ số an toàn và rõ nghĩa hơn ghép các giá trị bên ngoài vào một chuỗi literal chưa được kiểm tra.

### 6.3. TO_YMINTERVAL và TO_DSINTERVAL

~~~sql
SELECT TO_YMINTERVAL('01-06') AS ky_mot_nam_sau_thang
FROM dual;

SELECT TO_DSINTERVAL('1 02:03:04.125') AS khoang_ngay_gio
FROM dual;
~~~

Hai hàm chuyển chuỗi có định dạng phù hợp thành interval tương ứng. Đầu vào phải đúng cú pháp. Đừng dùng cách cắt chuỗi tự viết để giả định mọi output interval luôn có chính xác một độ rộng ký tự giữa các driver và phiên bản.

### 6.4. Hàm gần giống nhưng có ngữ nghĩa khác

| Hàm/phép toán | Kết quả | Khác biệt |
| --- | --- | --- |
| **ADD_MONTHS(date, n)** | DATE | Có quy tắc riêng về cuối tháng |
| **MONTHS_BETWEEN(date1, date2)** | NUMBER | Trả chênh lệch theo số tháng có thể có phần phân số, không phải trực tiếp INTERVAL YEAR TO MONTH |
| **DATE - DATE** | NUMBER | Số ngày chênh lệch |
| **TIMESTAMP - TIMESTAMP** | INTERVAL DAY TO SECOND | Khoảng thời gian có thành phần ngày–giây |
| **NUMTOYMINTERVAL(n, unit)** | INTERVAL YEAR TO MONTH | Từ số tháng hoặc năm |
| **NUMTODSINTERVAL(n, unit)** | INTERVAL DAY TO SECOND | Từ số ngày, giờ, phút, giây |

Tính “tuổi theo năm/tháng”, “số tháng giữa hai ngày” hoặc “sau n tháng lịch” phải dựa trên quy tắc nghiệp vụ cụ thể; việc có sẵn kiểu INTERVAL không tự động quyết định cách làm tròn tuổi hay phân bổ ngày cuối tháng.

## 7. Trích xuất và tính toán từ INTERVAL

### 7.1. EXTRACT từng trường

Hàm **EXTRACT** giúp lấy thành phần của interval:

~~~sql
SELECT EXTRACT(YEAR FROM INTERVAL '2-9' YEAR TO MONTH) AS so_nam,
       EXTRACT(MONTH FROM INTERVAL '2-9' YEAR TO MONTH) AS so_thang
FROM dual;

SELECT EXTRACT(DAY FROM
           INTERVAL '3 04:05:06.125' DAY TO SECOND(3)) AS ngay,
       EXTRACT(HOUR FROM
           INTERVAL '3 04:05:06.125' DAY TO SECOND(3)) AS gio,
       EXTRACT(MINUTE FROM
           INTERVAL '3 04:05:06.125' DAY TO SECOND(3)) AS phut,
       EXTRACT(SECOND FROM
           INTERVAL '3 04:05:06.125' DAY TO SECOND(3)) AS giay
FROM dual;
~~~

Ví dụ đầu trả **2 năm** và **9 tháng**. Ví dụ sau trả **3 ngày, 4 giờ, 5 phút và 6.125 giây**. Trường SECOND có thể là số có phần thập phân. Không cố EXTRACT YEAR từ DAY TO SECOND hoặc EXTRACT DAY từ YEAR TO MONTH vì hai nhóm interval mang các trường khác nhau.

### 7.2. Quy đổi trong cùng nhóm khoảng thời gian

Một khoảng YEAR TO MONTH có thể quy về tổng tháng:

~~~sql
SELECT EXTRACT(YEAR FROM INTERVAL '2-9' YEAR TO MONTH) * 12
       + EXTRACT(MONTH FROM INTERVAL '2-9' YEAR TO MONTH)
       AS tong_thang
FROM dual;
~~~

Kết quả **33 tháng**. Cách này hữu ích để so sánh chu kỳ hoặc xuất dữ liệu cho hệ thống chỉ hiểu số tháng.

Khoảng DAY TO SECOND có thể quy về tổng giây:

~~~sql
SELECT EXTRACT(DAY FROM
           INTERVAL '1 02:03:04.125' DAY TO SECOND(3)) * 86400
       + EXTRACT(HOUR FROM
           INTERVAL '1 02:03:04.125' DAY TO SECOND(3)) * 3600
       + EXTRACT(MINUTE FROM
           INTERVAL '1 02:03:04.125' DAY TO SECOND(3)) * 60
       + EXTRACT(SECOND FROM
           INTERVAL '1 02:03:04.125' DAY TO SECOND(3))
       AS tong_giay
FROM dual;
~~~

Kết quả **93784.125 giây**. Công thức theo 24 giờ/ngày tương ứng với thành phần khoảng thời gian DAY TO SECOND, và không phải phép quy đổi tháng lịch ra giây. Với interval âm, cần hiểu biểu diễn dấu và thử tương ứng thay vì ghép chuỗi từ các trường.

### 7.3. So sánh và cộng trừ interval

~~~sql
-- Cùng nhóm YEAR TO MONTH
SELECT CASE
         WHEN INTERVAL '1-0' YEAR TO MONTH
              > INTERVAL '9' MONTH
         THEN 'Dai hon'
         ELSE 'Khong dai hon'
       END AS so_sanh_thang
FROM dual;

-- Cùng nhóm DAY TO SECOND
SELECT INTERVAL '1 02:00:00' DAY TO SECOND
       + INTERVAL '0 03:30:00' DAY TO SECOND AS tong_thoi_luong
FROM dual;
~~~

Câu thứ nhất cho biết 1 năm **dài hơn 9 tháng theo số tháng lịch**. Câu thứ hai trả khoảng tương đương **1 ngày 5 giờ 30 phút**.

Không áp dụng trực tiếp cùng một phép so sánh kiểu “1 tháng > 30 ngày” cho YEAR TO MONTH và DAY TO SECOND vì không có ánh xạ toàn cục giữa hai miền. Nếu thực sự cần so sánh, phải đưa chúng về **một mốc thời gian và một quy tắc lịch cụ thể**, rồi so sánh các thời điểm kết quả.

## 8. Thiết kế cột và dữ liệu mẫu Oracle

Ví dụ bảng lịch công việc thể hiện **chu kỳ theo tháng** và **thời lượng theo ngày–giây** là hai thuộc tính khác nhau:

~~~sql
CREATE TABLE lich_dinh_ky (
    ma_lich       NUMBER(6) CONSTRAINT pk_lich_dinh_ky PRIMARY KEY,
    ten_cong_viec VARCHAR2(100 CHAR) NOT NULL,
    bat_dau       TIMESTAMP(3) NOT NULL,
    chu_ky        INTERVAL YEAR(3) TO MONTH,
    thoi_luong    INTERVAL DAY(3) TO SECOND(3)
);
~~~

Ở đây:

- **BAT_DAU** là một thời điểm bắt đầu, có mili giây.
- **CHU_KY** cho biết sau bao nhiêu năm/tháng lịch sẽ có lần lặp kế tiếp.
- **THOI_LUONG** cho biết lần thực hiện công việc cần bao lâu.
- Cột CHU_KY hoặc THOI_LUONG được phép **NULL** khi thuộc tính chưa xác định hoặc không áp dụng, tùy ý nghĩa nghiệp vụ.

### 8.1. Nạp dữ liệu mẫu

~~~sql
INSERT INTO lich_dinh_ky
    (ma_lich, ten_cong_viec, bat_dau, chu_ky, thoi_luong)
VALUES (
    1, 'Gia han hang thang',
    TIMESTAMP '2024-01-15 09:30:00.000',
    INTERVAL '0-1' YEAR TO MONTH,
    INTERVAL '0 01:30:00.000' DAY TO SECOND(3)
);

INSERT INTO lich_dinh_ky
    (ma_lich, ten_cong_viec, bat_dau, chu_ky, thoi_luong)
VALUES (
    2, 'Bao tri qua ngay nhuan',
    TIMESTAMP '2024-02-28 23:59:30.000',
    INTERVAL '1-0' YEAR TO MONTH,
    INTERVAL '1 00:00:45.125' DAY TO SECOND(3)
);

INSERT INTO lich_dinh_ky
    (ma_lich, ten_cong_viec, bat_dau, chu_ky, thoi_luong)
VALUES (
    3, 'Cong viec mot lan',
    TIMESTAMP '2024-06-01 08:00:00.000',
    NULL,
    INTERVAL '0 00:00:00.000' DAY TO SECOND(3)
);

INSERT INTO lich_dinh_ky
    (ma_lich, ten_cong_viec, bat_dau, chu_ky, thoi_luong)
VALUES (
    4, 'Chua uoc luong thoi gian',
    TIMESTAMP '2024-07-01 08:00:00.000',
    INTERVAL '0-6' YEAR TO MONTH,
    NULL
);

COMMIT;
~~~

Chủ ý của bộ dữ liệu:

| Mã | Chu kỳ | Thời lượng | Ca thực hành |
| --- | --- | --- | --- |
| 1 | 1 tháng | 1 giờ 30 phút | Chu kỳ lịch và duration khác nhau |
| 2 | 1 năm | 1 ngày 45.125 giây | Đi qua ngày nhuận và có phần giây phân số |
| 3 | NULL | 0 giây | Không có chu kỳ nhưng thời lượng đã biết bằng 0 |
| 4 | 6 tháng | NULL | Có chu kỳ nhưng thời lượng chưa biết |

### 8.2. Tính lần lặp và thời điểm kết thúc

~~~sql
SELECT ma_lich,
       ten_cong_viec,
       TO_CHAR(
           bat_dau,
           'YYYY-MM-DD HH24:MI:SS.FF3'
       ) AS bat_dau_text,
       bat_dau + chu_ky AS lan_lap_ke_tiep,
       bat_dau + thoi_luong AS thoi_diem_ket_thuc
FROM lich_dinh_ky
ORDER BY ma_lich;
~~~

Với mã 1, lần lặp tiếp theo là **15/02/2024 09:30:00**, còn thời điểm kết thúc lần chạy là **15/01/2024 11:00:00**. Với mã 2, thời lượng đẩy kết thúc sang **01/03/2024 00:00:15.125** vì năm 2024 có ngày 29/02. Cột kết quả phép cộng với **NULL** vẫn là NULL; Oracle không tự thay bằng thời lượng 0.

Khi hiển thị các cột timestamp, định dạng của SQL client có thể phụ thuộc NLS và cấu hình giao diện. Dùng **TO_CHAR(..., 'YYYY-MM-DD HH24:MI:SS.FF3')** khi cần đối chiếu chuỗi hiển thị ổn định.

### 8.3. Tìm công việc có thời lượng vượt ngưỡng

~~~sql
SELECT ma_lich, ten_cong_viec
FROM lich_dinh_ky
WHERE thoi_luong > NUMTODSINTERVAL(90, 'MINUTE')
ORDER BY ma_lich;
~~~

Mã **2** có thời lượng dài hơn 90 phút. Mã 1 bằng đúng 90 phút nên không thỏa dấu **>**; mã 3 bằng 0; mã 4 có NULL nên không thỏa điều kiện WHERE.

Muốn tìm công việc có chu kỳ từ 6 tháng trở lên:

~~~sql
SELECT ma_lich, ten_cong_viec
FROM lich_dinh_ky
WHERE chu_ky >= NUMTOYMINTERVAL(6, 'MONTH')
ORDER BY ma_lich;
~~~

Kết quả gồm **2** và **4**. Hai truy vấn cho thấy cách so sánh đúng theo loại interval của cột.

### 8.4. Tính tổng số tháng và tổng số giây

~~~sql
SELECT ma_lich,
       EXTRACT(YEAR FROM chu_ky) * 12
         + EXTRACT(MONTH FROM chu_ky) AS tong_thang,
       EXTRACT(DAY FROM thoi_luong) * 86400
         + EXTRACT(HOUR FROM thoi_luong) * 3600
         + EXTRACT(MINUTE FROM thoi_luong) * 60
         + EXTRACT(SECOND FROM thoi_luong) AS tong_giay
FROM lich_dinh_ky
ORDER BY ma_lich;
~~~

| Mã | Tổng tháng | Tổng giây |
| --- | ---: | ---: |
| 1 | 1 | 5400 |
| 2 | 12 | 86445.125 |
| 3 | NULL | 0 |
| 4 | 6 | NULL |

Khi nghiệp vụ cần hiển thị **NULL thành 0**, có thể sử dụng **COALESCE** hoặc **NVL** ở tầng trình bày. Không nên áp dụng chuyển đổi đó mặc định nếu “chưa biết” và “bằng 0” mang ý nghĩa khác nhau.

### 8.5. Ràng buộc miền giá trị

Oracle cho phép interval âm. Nhưng thời lượng thực hiện một công việc thường không được âm, còn độ lệch so với hạn chuẩn có thể âm hoặc dương. Đây là **quy tắc nghiệp vụ**, không phải quy định chung của kiểu dữ liệu.

Với một bảng mà thời lượng tuyệt đối không được âm, có thể bổ sung điều kiện dạng:

~~~sql
ALTER TABLE lich_dinh_ky
ADD CONSTRAINT ck_lich_thoi_luong_khong_am
CHECK (
    thoi_luong IS NULL
    OR thoi_luong >= INTERVAL '0' SECOND
);
~~~

Đặt **NOT NULL** riêng nếu một cột bắt buộc có dữ liệu. Trong Oracle, CHECK không tự từ chối NULL nếu điều kiện trả UNKNOWN; cần phân biệt điều kiện miền giá trị và tính bắt buộc của cột.

## 9. PL/SQL với biến INTERVAL

PL/SQL có thể khai báo biến interval, dùng trong tính toán hoặc nhận kết quả từ SQL.

~~~sql
SET SERVEROUTPUT ON

DECLARE
    v_bat_dau  TIMESTAMP(3) :=
        TIMESTAMP '2024-04-01 08:00:00.000';

    v_chu_ky   INTERVAL YEAR(3) TO MONTH :=
        INTERVAL '1-6' YEAR TO MONTH;

    v_thoi_gian INTERVAL DAY(3) TO SECOND(3) :=
        INTERVAL '0 01:30:30.500' DAY TO SECOND(3);

    v_lap_lai  TIMESTAMP(3);
    v_ket_thuc TIMESTAMP(3);
BEGIN
    v_lap_lai  := v_bat_dau + v_chu_ky;
    v_ket_thuc := v_bat_dau + v_thoi_gian;

    DBMS_OUTPUT.PUT_LINE(
        'Lap lai: ' ||
        TO_CHAR(v_lap_lai, 'YYYY-MM-DD HH24:MI:SS.FF3')
    );

    DBMS_OUTPUT.PUT_LINE(
        'Ket thuc: ' ||
        TO_CHAR(v_ket_thuc, 'YYYY-MM-DD HH24:MI:SS.FF3')
    );
END;
/
~~~

Về ý nghĩa, lần lặp tiếp theo là **01/10/2025 08:00:00.000**, còn kết thúc công việc là **01/04/2024 09:30:30.500**. Dấu **/** cuối khối là lệnh gửi block đi thực thi của công cụ như SQL*Plus/SQLcl; để thấy DBMS_OUTPUT cần bật hiển thị đầu ra tương ứng.

Không cần dùng vòng lặp PL/SQL để cộng thêm từng giây khi Oracle đã có phép toán interval; dùng biểu thức có kiểu dữ liệu phù hợp rõ ràng và dễ kiểm soát hơn.

## 10. Ứng dụng Java/JDBC truyền và nhận INTERVAL

Ở phía Java, cần phân biệt biểu diễn nghiệp vụ **Period** và **Duration** với loại interval của Oracle:

| Java | Ý nghĩa | Liên hệ Oracle |
| --- | --- | --- |
| **java.time.Period** | Khoảng theo năm, tháng và ngày của lịch ISO | Phần năm–tháng có thể tương ứng YEAR TO MONTH nếu không sử dụng thành phần ngày |
| **java.time.Duration** | Khoảng thời gian theo giây và nano giây | Phù hợp về ý nghĩa với DAY TO SECOND |
| **java.time.LocalDateTime** | Ngày/giờ địa phương, không mang múi giờ | Thường được dùng cho cột TIMESTAMP không múi giờ |
| **java.time.Instant / OffsetDateTime** | Thời điểm thực và độ lệch múi giờ | Cần chọn đúng kiểu Oracle có ngữ nghĩa múi giờ và cách JDBC binding |

**Không mặc định JDBC chuẩn bảo đảm ánh xạ trực tiếp mọi trường hợp** giữa Oracle INTERVAL và **java.time.Period/Duration**. Hỗ trợ đọc/ghi trực tiếp bằng **setObject/getObject** phụ thuộc phiên bản Oracle JDBC Driver và loại Java được driver hỗ trợ. Có thể gặp những lớp biểu diễn riêng của Oracle. Khi muốn giảm phụ thuộc vào API đặc thù của driver, một phương án rõ ràng là **bind số tháng hoặc số giây và tạo interval bằng hàm SQL**.

### 10.1. Ví dụ INSERT qua PreparedStatement

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import javax.sql.DataSource;

public final class LichRepository {
    private final DataSource dataSource;

    public LichRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void themLich() throws SQLException {
        String sql = """
            INSERT INTO lich_dinh_ky
                (ma_lich, ten_cong_viec, bat_dau, chu_ky, thoi_luong)
            VALUES (
                ?, ?, ?,
                NUMTOYMINTERVAL(?, 'MONTH'),
                NUMTODSINTERVAL(?, 'SECOND')
            )
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setLong(1, 10L);
            statement.setString(2, "Cong viec tu ung dung Java");
            statement.setTimestamp(
                3,
                Timestamp.valueOf(
                    LocalDateTime.of(2024, 7, 1, 9, 0, 0)
                )
            );
            statement.setInt(4, 18); // 18 thang = 1 nam 6 thang
            statement.setBigDecimal(
                5,
                new BigDecimal("5400.125") // 1 gio 30 phut 0.125 giay
            );

            statement.executeUpdate();
        }
    }
}
~~~

**PreparedStatement** gửi tham số tách khỏi cấu trúc câu SQL, phù hợp cho dữ liệu đầu vào và tránh ghép chuỗi SQL thiếu an toàn. Hàm **NUMTOYMINTERVAL** nhận giá trị tháng, còn **NUMTODSINTERVAL** nhận số giây. Việc chọn **BigDecimal** giúp biểu diễn số giây có phần thập phân rõ ràng hơn việc coi mọi phép toán thập phân là số thực nhị phân.

Ví dụ giả định bảng đã được tạo, Oracle JDBC Driver được cấu hình, DataSource hoạt động và tài khoản có quyền INSERT. Giao dịch và commit do cấu hình DataSource/framework quyết định; trong ứng dụng Spring có quản lý transaction, không nên trộn tùy tiện commit thủ công với transaction do Spring sở hữu.

### 10.2. Ví dụ đọc về tổng tháng và tổng giây

Để tránh phụ thuộc cách driver hiện thực class interval, có thể để Oracle chuyển các interval thành những đại lượng số với đơn vị rõ ràng:

~~~sql
SELECT ma_lich,
       EXTRACT(YEAR FROM chu_ky) * 12
           + EXTRACT(MONTH FROM chu_ky) AS total_months,
       EXTRACT(DAY FROM thoi_luong) * 86400
           + EXTRACT(HOUR FROM thoi_luong) * 3600
           + EXTRACT(MINUTE FROM thoi_luong) * 60
           + EXTRACT(SECOND FROM thoi_luong) AS total_seconds
FROM lich_dinh_ky
WHERE ma_lich = :ma_lich;
~~~

Trong JDBC chuẩn, tham số tên **:ma_lich** thường được thay bằng dấu **?** trong **PreparedStatement**, sau đó gán ID bằng setLong. Giá trị **TOTAL_MONTHS** có thể được diễn giải thành số tháng, còn **TOTAL_SECONDS** có thể đọc bằng getBigDecimal để giữ phần giây phân số. Khi chuyển sang **Duration**, phải xác định quy tắc làm tròn và số chữ số nano giây muốn giữ; khi chuyển sang **Period**, không tự đưa thành phần ngày vào một cột Oracle chỉ chứa YEAR TO MONTH.

### 10.3. Đừng thay tháng bằng số giây trong Java

Một lỗi thường gặp là biểu diễn chu kỳ **Period.ofMonths(1)** bằng **Duration.ofDays(30)** rồi gửi vào DAY TO SECOND. Hai khoảng này không tương đương trong lịch. Nếu hệ thống tính thời hạn một tháng, nên bảo toàn số tháng và áp dụng quy tắc cuối tháng ở nơi xử lý nghiệp vụ. Nếu hệ thống đo latency, thời gian chạy job hoặc thời gian chờ, dùng duration theo giây thường tự nhiên hơn.

## 11. Các giá trị biên và lỗi thường gặp

### 11.1. Leading precision quá nhỏ

~~~sql
-- DAY mặc định có leading precision 2:
-- giá trị 123 ngày vượt quá độ dài trường ngày mặc định.
SELECT INTERVAL '123' DAY AS khoang_qua_lon
FROM dual;

-- Chỉ định DAY(3) cho 123 ngày.
SELECT INTERVAL '123' DAY(3) AS khoang_hop_le
FROM dual;
~~~

Cần phân biệt **độ chính xác của trường đầu** với **độ chính xác của giây phân số**. DAY(3) không có nghĩa thời lượng dài 3 ngày; nó cho phép phần ngày có đến ba chữ số.

### 11.2. Thành phần con vượt miền hợp lệ

~~~sql
-- Không hợp lệ vì thành phần MONTH trong YEAR TO MONTH là 12.
SELECT INTERVAL '1-12' YEAR TO MONTH
FROM dual;

-- Hợp lệ: tổng cộng 24 tháng.
SELECT NUMTOYMINTERVAL(24, 'MONTH')
FROM dual;
~~~

Tương tự, với literal DAY TO SECOND ở dạng có đầy đủ thành phần, giờ/phút/giây phải hợp lệ. Nếu đầu vào là tổng số phút 150 hoặc số giây 90000, **NUMTODSINTERVAL** thích hợp để Oracle chuyển đổi và chuẩn hóa.

### 11.3. Thay đổi kiểu dữ liệu không mong muốn

~~~sql
SELECT DATE '2024-05-02'
       - DATE '2024-05-01' AS hieu_number
FROM dual;

SELECT TIMESTAMP '2024-05-02 00:00:00'
       - TIMESTAMP '2024-05-01 00:00:00' AS hieu_interval
FROM dual;
~~~

Không viết code ứng dụng giả định hai truy vấn trả cùng một loại JDBC object. Đọc metadata kiểu kết quả hoặc quy đổi rõ ràng ngay trong câu SQL.

### 11.4. NULL khác 0

~~~sql
-- Thời lượng chưa biết.
SELECT ma_lich
FROM lich_dinh_ky
WHERE thoi_luong IS NULL;

-- Thời lượng đã biết và bằng 0.
SELECT ma_lich
FROM lich_dinh_ky
WHERE thoi_luong = INTERVAL '0' SECOND;
~~~

Theo seed dữ liệu, truy vấn đầu trả **4**, truy vấn sau trả **3**. So sánh **= NULL** không hoạt động như mong muốn trong SQL; phải dùng **IS NULL**.

### 11.5. Định dạng nhập/hiển thị không giống kiểu dữ liệu

Một cột INTERVAL được Oracle lưu với kiểu khoảng thời gian, không phải chỉ là chuỗi như **'1-6'** hoặc **'1 02:03:04'**. Cách client in giá trị interval có thể có dấu, các số 0 đệm và số chữ số khác nhau tùy precision, công cụ hoặc driver. Không nên dựa vào định dạng text ngẫu nhiên của giao diện để phân tích dữ liệu trong Java.

Nếu cần dữ liệu trao đổi giữa hệ thống theo JSON hoặc API, hãy **công bố quy ước có đơn vị**: ví dụ totalMonths = 18, totalSeconds = 5400.125 hoặc một định dạng chuỗi duration được hai bên thỏa thuận. Tránh trường tên **duration = 18** mà không nói rõ 18 tháng, ngày, giây hay mili giây.

### 11.6. Khoảng thời gian âm và quy tắc nghiệp vụ

Oracle cho phép interval âm, hữu ích khi mô tả độ lệch như “trễ 15 phút” hoặc “lùi ba tháng”. Tuy nhiên, khoảng thời gian **thực hiện một công việc** hoặc **thời hạn cam kết không âm** có thể cần CHECK ở schema. Đừng tự động cấm mọi interval âm chỉ vì muốn ngăn một trường hợp nghiệp vụ; cột biểu diễn độ lệch có thể cần cả hai dấu.

### 11.7. Chu kỳ tháng và DST

Không thay **INTERVAL '1' MONTH** thành một lượng ngày cố định. Khi tính trên TIMESTAMP có múi giờ, cũng không giả định “thêm một ngày lịch địa phương” có cùng ngữ nghĩa với “thêm đúng 24 giờ” tại thời điểm chuyển DST. Dữ liệu lịch định kỳ và duration xử lý có thể cần mô hình riêng để bảo toàn mục tiêu nghiệp vụ.

## 12. Lựa chọn kiểu dữ liệu trong thiết kế hệ thống

| Yêu cầu | Kiểu/cách tiếp cận nên cân nhắc | Lý do |
| --- | --- | --- |
| Gia hạn hợp đồng mỗi 6 tháng | INTERVAL YEAR TO MONTH hoặc số tháng có quy tắc rõ | Dựa trên lịch tháng |
| Bảo hành 2 năm | INTERVAL YEAR TO MONTH | Đơn vị năm–tháng đúng nghiệp vụ |
| Thời lượng chạy job 12.345 giây | INTERVAL DAY TO SECOND hoặc số giây có precision rõ | Duration với phần giây |
| Timeout kết nối 5 giây | Thường số mili giây/giây theo cấu hình API; khi lưu trong DB có thể dùng DAY TO SECOND | Cần bảo toàn đơn vị và phân biệt với thời điểm |
| Chênh lệch giữa hai TIMESTAMP | INTERVAL DAY TO SECOND | Phép trừ timestamp trả interval |
| Thời điểm bắt đầu/kết thúc | TIMESTAMP hoặc biến thể có múi giờ | Đây là thời điểm, không phải khoảng |
| Thời hạn theo ngày cuối tháng | ADD_MONTHS hoặc quy tắc lịch được định nghĩa | Phải xử lý ngày cuối tháng/năm nhuận |
| API gửi số tháng và giây từ Java | Bind số và dùng NUMTOYMINTERVAL/NUMTODSINTERVAL | Tách dữ liệu khỏi cấu trúc SQL |
| Không biết khoảng thời gian | NULL theo mô hình | Không được tùy tiện thay bằng interval 0 |

Thiết kế còn cần xét precision, miền giá trị, quyền hạn, thống nhất múi giờ, cách làm tròn và số liệu đầu vào. Cùng tên “duration” trong code có thể biểu diễn một **khoảng tháng lịch** hoặc **số giây thực thi**; mô hình dữ liệu nên làm rõ sự khác biệt.

## 13. Bài tập tự luyện

1. Viết literal Oracle biểu diễn **2 năm 7 tháng**, sau đó dùng EXTRACT tính tổng số tháng. Kết quả là bao nhiêu?
2. Tạo interval **1 ngày 4 giờ 5 phút 6.250 giây** với DAY(3) TO SECOND(3), rồi tính tổng số giây.
3. Vì sao cột INTERVAL YEAR TO MONTH không phù hợp nếu yêu cầu nghiệp vụ là “chạy một tác vụ tối đa 45 giây”?
4. Viết SQL tìm thời điểm sau **90 phút** kể từ TIMESTAMP '2024-02-29 23:30:00'. Kết quả rơi vào ngày nào?
5. Phân biệt **DATE - DATE** và **TIMESTAMP - TIMESTAMP** về kiểu trả về và ý nghĩa đơn vị.
6. Thử cộng INTERVAL '1' MONTH vào DATE '2024-01-31', sau đó thử ADD_MONTHS với cùng ngày. Giải thích khác biệt về ngày cuối tháng.
7. Viết truy vấn tìm những công việc có chu kỳ **ít nhất 12 tháng**, chỉ dùng dữ liệu bảng LICH_DINH_KY.
8. Viết truy vấn phân biệt thời lượng **bằng 0** và thời lượng **chưa biết** trong bảng mẫu.
9. Nếu Java nhận số tháng từ người dùng và số giây từ một bộ đo, nên dùng hai hàm tạo interval nào để đưa dữ liệu vào Oracle?
10. Tại sao không được tự quy đổi 1 tháng thành 30 ngày khi xử lý hợp đồng có thể bắt đầu ở ngày 31/01?
11. Trong một API, nếu muốn trả duration ra JSON, tại sao cần ghi rõ đơn vị của giá trị thay vì chỉ trả số?
12. Nếu dữ liệu có múi giờ và lịch định kỳ xảy ra lúc 09:00 địa phương, cần đặt những câu hỏi nào trước khi cộng DAY TO SECOND qua giai đoạn đổi giờ mùa hè?

**INTERVAL YEAR TO MONTH** diễn tả sự dịch chuyển theo **lịch năm–tháng**; **INTERVAL DAY TO SECOND** diễn tả **thời lượng theo ngày–giây**, có thể bao gồm phần giây phân số. Hai kiểu giúp SQL và PL/SQL diễn đạt trực tiếp đơn vị thời gian, nhưng không thay thế quy tắc nghiệp vụ về ngày cuối tháng, thời điểm, múi giờ hoặc đơn vị số liệu trao đổi với Java. Khi chọn đúng kiểu và precision, việc tính toán và kiểm tra dữ liệu trong Oracle sẽ rõ nghĩa, nhất quán và ít phụ thuộc vào các phép quy đổi ngầm.
