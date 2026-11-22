# Cộng trừ ngày giờ, khoảng thời gian và quy tắc cuối tháng

Trong Oracle Database, tính toán ngày giờ không đơn giản chỉ là cộng một con số vào một cột. **Cộng một ngày, cộng 24 giờ và cộng một tháng lịch** có thể mang ý nghĩa khác nhau. Điều này đặc biệt quan trọng ở ngày cuối tháng, năm nhuận, thời điểm có phần giây, múi giờ và khi dữ liệu được nhập bằng chuỗi chịu ảnh hưởng bởi thiết lập NLS.

Ví dụ: một hợp đồng bắt đầu ngày **31/01/2024** và có thời hạn **1 tháng**. Thời điểm hết hạn nên là ngày 29/02/2024, ngày 02/03/2024 hay một ngày khác? Câu trả lời phụ thuộc **quy tắc nghiệp vụ** và **phép toán Oracle được chọn**. Trong khi đó, một công việc bắt đầu lúc **23:45**, chạy 30 phút, có thể tính bằng khoảng ngày–giây mà không cần quy tắc cuối tháng.

Bài học làm rõ cách dùng **DATE**, **TIMESTAMP**, hai loại **INTERVAL**, **ADD_MONTHS**, **LAST_DAY**, **MONTHS_BETWEEN**, **TRUNC**, **EXTRACT** và các nguyên tắc NLS khi thực hiện phép toán ngày giờ.

## 1. Chọn đúng kiểu dữ liệu trước khi tính

| Kiểu dữ liệu Oracle | Nội dung lưu trữ/biểu diễn | Bài toán phù hợp |
| --- | --- | --- |
| **DATE** | Năm, tháng, ngày, giờ, phút, giây; không có phần giây phân số hoặc thông tin múi giờ | Ngày tạo đơn, ngày nghiệp vụ, thời điểm chỉ cần độ chính xác đến giây |
| **TIMESTAMP(p)** | Ngày và giờ cùng phần giây phân số, không kèm múi giờ | Thời điểm ghi log hoặc đo xử lý nội bộ cần mili giây |
| **TIMESTAMP WITH TIME ZONE** | Thời điểm có thông tin múi giờ/độ lệch theo biểu diễn được hỗ trợ | Sự kiện xảy ra tại các múi giờ khác nhau |
| **TIMESTAMP WITH LOCAL TIME ZONE** | Giá trị được chuẩn hóa theo múi giờ database và hiển thị theo múi giờ phiên | Dữ liệu thời điểm có cách hiển thị tùy session |
| **INTERVAL YEAR TO MONTH** | Độ dài theo năm và tháng lịch | Chu kỳ hợp đồng, gia hạn theo tháng |
| **INTERVAL DAY TO SECOND** | Độ dài theo ngày, giờ, phút, giây và phần giây | Thời lượng thực thi, độ trễ, cửa sổ 90 phút |
| **NUMBER** | Số, chỉ có ý nghĩa thời gian khi đơn vị được xác định | Hiệu của hai giá trị DATE tính theo số ngày, số tháng cấu hình |

Một **thời điểm** cho biết *khi nào*, còn một **khoảng thời gian** cho biết *bao lâu*. Trong Oracle, **DATE - DATE** cho kết quả là một số ngày dạng NUMBER, trong khi **TIMESTAMP - TIMESTAMP** cho kết quả thuộc họ **INTERVAL DAY TO SECOND**.

~~~text
Ngày/giờ bắt đầu              Phép toán                      Kết quả
---------------------         -------------------------      ---------------------
2024-01-15                    + 1 tháng lịch                 2024-02-15
2024-01-31                    + 1 tháng bằng ADD_MONTHS      2024-02-29
2024-02-28 23:30:00           + 90 phút                     2024-02-29 01:00:00
2024-03-01 12:00:00           - 2024-02-29 12:00:00         1 ngày
~~~

Các kết quả ví dụ theo **lịch Gregorian**, trên dữ liệu không mang múi giờ, và không giả định thay đổi NLS_CALENDAR khỏi cấu hình Gregorian thông thường.

## 2. Oracle DATE cộng và trừ NUMBER

Kiểu **DATE** của Oracle lưu đến độ chính xác giây, dù cách hiển thị mặc định có thể chỉ có ngày. Khi cộng hoặc trừ một **NUMBER** với DATE, số đó được hiểu theo **đơn vị ngày**.

### 2.1. Cộng ngày nguyên

~~~sql
SELECT DATE '2024-02-28' + 1 AS ngay_sau
FROM dual;

SELECT DATE '2024-03-01' - 2 AS hai_ngay_truoc
FROM dual;
~~~

Kết quả lần lượt tương ứng **29/02/2024** và **28/02/2024**. Oracle xử lý lịch năm nhuận; không cần viết mã tự quyết định tháng 2 có 28 hay 29 ngày.

### 2.2. Cộng giờ, phút và giây bằng phần của ngày

~~~sql
SELECT DATE '2024-02-28' + (6 / 24) AS sau_sau_gio
FROM dual;

SELECT DATE '2024-02-28' + (90 / 1440) AS sau_chin_muoi_phut
FROM dual;

SELECT DATE '2024-02-28' + (45 / 86400) AS sau_bon_muoi_lam_giay
FROM dual;
~~~

Các quy đổi đến từ:

- **1 ngày = 24 giờ**.
- **1 ngày = 1.440 phút**.
- **1 ngày = 86.400 giây**.

Vì **DATE chỉ lưu thời gian đến giây**, cách cộng phân số ngày không phù hợp khi cần giữ chính xác phần mili giây hay micro giây. Khi diễn tả thời lượng có phần giây, nên dùng TIMESTAMP và INTERVAL DAY TO SECOND.

Công thức **1 ngày = 24 giờ** trong ví dụ là phép toán ngày giờ không mang múi giờ. Với nghiệp vụ theo giờ địa phương có chuyển đổi giờ mùa hè (DST), cần xét kiểu dữ liệu có múi giờ và quy tắc thời gian thực tế; không áp dụng đơn giản công thức này cho mọi bối cảnh.

### 2.3. Trừ hai DATE: kết quả là số ngày

~~~sql
SELECT DATE '2024-03-02' - DATE '2024-02-29' AS so_ngay
FROM dual;

SELECT (
    TO_DATE('2024-03-01 09:30:00', 'YYYY-MM-DD HH24:MI:SS')
    - TO_DATE('2024-03-01 08:00:00', 'YYYY-MM-DD HH24:MI:SS')
) * 24 * 60 AS so_phut
FROM dual;
~~~

Truy vấn đầu trả **2 ngày**; truy vấn sau trả **90 phút**. Đặt ngoặc quanh phép trừ giúp người đọc thấy NUMBER trả ra là **số ngày**, rồi mới quy đổi sang đơn vị cần thiết.

Nếu kết quả âm, thời điểm bên trái sớm hơn thời điểm bên phải:

~~~sql
SELECT DATE '2024-03-01' - DATE '2024-03-05' AS chenhlech_am
FROM dual;
~~~

Kết quả là **-4**, không phải NULL hoặc một lỗi.

### 2.4. DATE literal tránh phụ thuộc định dạng phiên

~~~sql
SELECT DATE '2024-02-29' AS ngay_nhuan
FROM dual;
~~~

Cú pháp **DATE 'YYYY-MM-DD'** tạo một DATE literal có ngày rõ ràng và giờ ở 00:00:00, không cần dựa vào NLS_DATE_FORMAT để phân tích chuỗi đầu vào.

Nhược điểm là literal DATE chỉ biểu diễn phần ngày. Khi cần cả thời gian, có thể dùng TO_DATE với format model tường minh hoặc TIMESTAMP literal tương ứng.

## 3. TIMESTAMP và INTERVAL DAY TO SECOND

**TIMESTAMP** lưu phần giây phân số. **INTERVAL DAY TO SECOND** diễn tả một khoảng theo ngày, giờ, phút, giây và phần giây. Kết hợp chúng để thể hiện độ trễ hoặc thời lượng theo đơn vị rõ ràng.

### 3.1. Cộng và trừ khoảng thời gian

~~~sql
SELECT TIMESTAMP '2024-02-28 23:30:00.000'
       + INTERVAL '0 01:30:00.250' DAY TO SECOND(3)
       AS ket_thuc
FROM dual;

SELECT TIMESTAMP '2024-03-01 10:00:00'
       - INTERVAL '45' MINUTE
       AS tru_bon_muoi_lam_phut
FROM dual;
~~~

Kết quả ví dụ đầu là **2024-02-29 01:00:00.250**; ví dụ hai là **2024-03-01 09:15:00**. Các phép toán tôn trọng ranh giới ngày/tháng/năm mà không cần tự tính bằng chuỗi.

### 3.2. Những dạng literal thường gặp

~~~sql
SELECT INTERVAL '2' DAY AS hai_ngay,
       INTERVAL '5' HOUR AS nam_gio,
       INTERVAL '90' MINUTE AS chin_muoi_phut,
       INTERVAL '1 02:03:04.125' DAY TO SECOND(3) AS mot_ngay_hai_gio
FROM dual;
~~~

Dạng **DAY TO SECOND** có trường ngày đứng đầu và các trường con phải nằm trong miền hợp lệ, ví dụ giờ trong một ngày ở dạng đầy đủ là 0–23. Muốn tạo khoảng từ **90 giờ** hoặc **150 phút** đầu vào, hàm NUMTODSINTERVAL thường thuận tiện hơn việc xây literal chứa thành phần giờ/phút vượt giới hạn.

### 3.3. NUMTODSINTERVAL cho giá trị được tính hoặc bind

~~~sql
SELECT TIMESTAMP '2024-02-28 23:30:00'
       + NUMTODSINTERVAL(90, 'MINUTE') AS ket_thuc
FROM dual;

SELECT TIMESTAMP '2024-01-01 08:00:00.000'
       + NUMTODSINTERVAL(1.25, 'SECOND') AS sau_mot_phay_hai_lam_giay
FROM dual;
~~~

Hàm **NUMTODSINTERVAL** nhận số và một trong những đơn vị như DAY, HOUR, MINUTE, SECOND rồi trả INTERVAL DAY TO SECOND. Nó có ích khi một ứng dụng Java truyền số timeout, duration hoặc độ trễ vào SQL bằng bind variable.

### 3.4. Trừ hai TIMESTAMP

~~~sql
SELECT TIMESTAMP '2024-03-01 01:00:00.125'
       - TIMESTAMP '2024-02-28 23:59:59.000'
       AS thoi_luong
FROM dual;
~~~

Kết quả là một **INTERVAL DAY TO SECOND** tương ứng **1 ngày, 1 giờ, 0 phút và 1,125 giây**. Không thể coi trực tiếp giá trị interval này là NUMBER ngày như kết quả DATE - DATE.

Muốn lấy tổng giây của một interval, tách các thành phần bằng EXTRACT:

~~~sql
WITH khoang AS (
    SELECT TIMESTAMP '2024-03-01 01:00:00.125'
           - TIMESTAMP '2024-02-28 23:59:59.000'
           AS dt
    FROM dual
)
SELECT EXTRACT(DAY FROM dt) * 86400
       + EXTRACT(HOUR FROM dt) * 3600
       + EXTRACT(MINUTE FROM dt) * 60
       + EXTRACT(SECOND FROM dt) AS tong_giay
FROM khoang;
~~~

Tổng số giây bằng **90.001,125** đối với hai mốc đã chọn (1 ngày + 1 giờ + 1,125 giây). Đây là phép quy đổi từ phần của interval sang tổng giây, không tự động tính theo múi giờ hoặc các biến cố DST nếu dữ liệu đầu vào không có múi giờ.

### 3.5. Phân biệt phép toán với DATE và TIMESTAMP

| Biểu thức | Dạng kết quả thường dùng để xử lý | Cần chú ý |
| --- | --- | --- |
| **DATE + NUMBER** | Giá trị ngày/giờ | NUMBER là số ngày |
| **DATE - DATE** | NUMBER | Số ngày, có thể âm hoặc có phần thập phân |
| **TIMESTAMP - TIMESTAMP** | INTERVAL DAY TO SECOND | Khoảng thời gian với phần giây |
| **TIMESTAMP + INTERVAL DAY TO SECOND** | Giá trị ngày/giờ sau dịch chuyển | Giữ ý nghĩa ngày, giờ, phút, giây rõ ràng |
| **DATE/TIMESTAMP + INTERVAL YEAR TO MONTH** | Thời điểm dịch theo lịch năm–tháng | Phải xét ngày cuối tháng không tồn tại |

Khi thiết kế JDBC, không mặc định mọi hiệu thời gian đều đọc về kiểu Java **long** hoặc **double**. Cần biết Oracle trả NUMBER hay INTERVAL, và dùng driver hoặc phép chuyển đổi SQL phù hợp.

## 4. INTERVAL YEAR TO MONTH và tính theo tháng lịch

**INTERVAL YEAR TO MONTH** mô tả số năm và tháng, ví dụ 1 năm 6 tháng. Khác với số ngày hoặc giây, **độ dài thực tế của một tháng phụ thuộc tháng/năm trên lịch**.

~~~sql
SELECT INTERVAL '1-6' YEAR TO MONTH AS mot_nam_sau_thang
FROM dual;

SELECT NUMTOYMINTERVAL(18, 'MONTH') AS muoi_tam_thang
FROM dual;
~~~

Hai biểu thức đều biểu thị khoảng tương đương **18 tháng lịch**. Tuy nhiên, trong phép cộng với ngày, hiệu ứng lên ngày cuối cùng còn phụ thuộc ngày bắt đầu và toán tử/hàm chọn để xử lý ngày không tồn tại.

Ví dụ không đi qua ngày biên:

~~~sql
SELECT DATE '2024-01-15' + INTERVAL '1' MONTH AS thang_sau
FROM dual;

SELECT TIMESTAMP '2024-01-15 10:30:00'
       + INTERVAL '1-2' YEAR TO MONTH AS sau_mot_nam_hai_thang
FROM dual;
~~~

Kết quả lịch tương ứng là **15/02/2024** và **15/03/2025 10:30:00**. Với ngày bắt đầu có mặt ở tháng đích, phép cộng theo tháng thường dễ hiểu. Nhưng với ngày 29, 30 hoặc 31, cần xem quy tắc cuối tháng.

## 5. Quy tắc cuối tháng: ADD_MONTHS khác cộng INTERVAL

Đây là phần dễ gây lỗi nghiệp vụ nhất khi gia hạn hợp đồng, tính ngày đáo hạn hoặc lập lịch định kỳ.

### 5.1. ADD_MONTHS xử lý ngày cuối tháng như thế nào?

Hàm **ADD_MONTHS(date, n)** dịch chuyển một giá trị DATE thêm hoặc bớt **n tháng lịch**. Theo quy tắc Oracle:

- Nếu ngày đầu vào là **ngày cuối tháng**, kết quả là **ngày cuối tháng của tháng đích**.
- Nếu tháng đích có **ít ngày hơn số ngày trong tháng đầu vào**, kết quả cũng được đưa về **ngày cuối tháng đích**.
- Trong các trường hợp còn lại, Oracle giữ **số ngày trong tháng** tương ứng.
- Phần giờ/phút/giây của DATE đầu vào được giữ theo phép cộng tháng, với giới hạn và ngữ nghĩa của DATE.
- Hàm ADD_MONTHS trả kiểu **DATE**.

~~~sql
SELECT TO_CHAR(
           ADD_MONTHS(DATE '2024-01-31', 1),
           'YYYY-MM-DD'
       ) AS tu_31_thang_1
FROM dual;

SELECT TO_CHAR(
           ADD_MONTHS(DATE '2024-01-30', 1),
           'YYYY-MM-DD'
       ) AS tu_30_thang_1
FROM dual;

SELECT TO_CHAR(
           ADD_MONTHS(DATE '2024-02-29', 12),
           'YYYY-MM-DD'
       ) AS tu_29_thang_2
FROM dual;
~~~

Kết quả với lịch Gregorian:

| Phép tính | Kết quả | Giải thích |
| --- | --- | --- |
| **ADD_MONTHS(31/01/2024, 1)** | 29/02/2024 | Nguồn là cuối tháng, tháng đích có 29 ngày |
| **ADD_MONTHS(30/01/2024, 1)** | 29/02/2024 | Ngày 30 không tồn tại trong tháng 2 |
| **ADD_MONTHS(29/02/2024, 12)** | 28/02/2025 | Nguồn là cuối tháng; tháng 2 năm 2025 có 28 ngày |
| **ADD_MONTHS(15/01/2024, 1)** | 15/02/2024 | Ngày 15 tồn tại ở tháng đích |
| **ADD_MONTHS(31/03/2024, -1)** | 29/02/2024 | Lùi từ cuối tháng 3 sang cuối tháng 2 của năm nhuận |

**Quy tắc ngày cuối tháng trong Oracle ADD_MONTHS là một quyết định của hàm**, không tự động trở thành quy tắc chuẩn của mọi hợp đồng. Có nghiệp vụ muốn giữ vị trí cuối tháng; có nghiệp vụ muốn cố định ngày 30 hoặc ngày 31 khi có thể; có nghiệp vụ muốn hết hạn trước một ngày. Cần chốt chính sách trước khi lập trình.

### 5.2. Cộng INTERVAL '1' MONTH có thể phát sinh lỗi

~~~sql
-- Ví dụ minh họa lỗi ngày không tồn tại.
SELECT DATE '2024-01-31' + INTERVAL '1' MONTH AS ket_qua
FROM dual;
~~~

Khi cộng tháng kiểu này, ngày **31/02/2024** không tồn tại nên Oracle có thể báo **ORA-01839: date not valid for month specified**. Đây là khác biệt thực tế giữa phép cộng **INTERVAL YEAR TO MONTH** và **ADD_MONTHS** ở ngày biên.

Vì vậy, với yêu cầu “luôn trả một ngày cuối tháng hợp lệ” khi cộng tháng, ADD_MONTHS là lựa chọn cần cân nhắc. Với mô hình yêu cầu bảo toàn số ngày và báo lỗi nếu ngày đích không tồn tại, phép cộng INTERVAL có ngữ nghĩa khác.

### 5.3. Lấy ngày cuối tháng bằng LAST_DAY

~~~sql
SELECT TO_CHAR(
           LAST_DAY(DATE '2024-02-10'),
           'YYYY-MM-DD'
       ) AS cuoi_thang_hai
FROM dual;

SELECT TO_CHAR(
           LAST_DAY(DATE '2025-02-10'),
           'YYYY-MM-DD'
       ) AS cuoi_thang_hai_khong_nhuan
FROM dual;
~~~

Kết quả lần lượt là **2024-02-29** và **2025-02-28**. LAST_DAY trả DATE tương ứng ngày cuối tháng đang chứa ngày đầu vào, giữ ngữ nghĩa thời gian của DATE.

Để lấy **ngày cuối của tháng sau**, có thể kết hợp:

~~~sql
SELECT LAST_DAY(
           ADD_MONTHS(DATE '2024-01-15', 1)
       ) AS cuoi_thang_sau
FROM dual;
~~~

Kết quả là **29/02/2024**.

**LAST_DAY** và **ADD_MONTHS** sử dụng khái niệm tháng theo tham số **NLS_CALENDAR** của phiên Oracle. Những ví dụ trên giả định lịch Gregorian. Trong môi trường sử dụng lịch khác, phải kiểm tra NLS_CALENDAR thay vì mặc định mọi phiên đều dùng một quy tắc tháng.

### 5.4. Cộng tháng nhiều lần không luôn bằng cộng một lần

Một vấn đề ít hiển nhiên: **ADD_MONTHS không luôn có tính kết hợp theo cách ứng dụng kỳ vọng** khi đi qua ngày cuối tháng.

~~~sql
SELECT TO_CHAR(
           ADD_MONTHS(
               ADD_MONTHS(DATE '2024-01-30', 1),
               1
           ),
           'YYYY-MM-DD'
       ) AS cong_tung_thang,

       TO_CHAR(
           ADD_MONTHS(DATE '2024-01-30', 2),
           'YYYY-MM-DD'
       ) AS cong_hai_thang_mot_lan
FROM dual;
~~~

Kết quả:

- **Cộng từng tháng:** 30/01 → 29/02 → **31/03/2024**. Sau bước đầu, 29/02 là ngày cuối tháng nên bước tiếp theo tiếp tục “bám cuối tháng”.
- **Cộng hai tháng một lần:** 30/01 → **30/03/2024**, vì tháng 3 có ngày 30.

Điều này rất quan trọng với lịch thanh toán. Nếu tính kỳ tiếp theo từ **ngày của kỳ trước**, một lịch có thể dịch về cuối tháng. Nếu tính từ **ngày gốc + n tháng**, lịch có thể giữ ngày gốc khi tháng đích hỗ trợ.

**Không có cách nào tự động đúng cho mọi nghiệp vụ.** Ví dụ:

- **Giữ nguyên ngày gốc khi có thể:** mỗi kỳ tính ADD_MONTHS(ngày_bắt_đầu, số_tháng_đã_qua).
- **Giữ ngày cuối tháng:** xác định hợp đồng thuộc loại end-of-month rồi luôn áp dụng quy tắc cuối tháng.
- **Dựa trên kỳ trước:** chấp nhận khả năng lịch dịch về cuối tháng khi kỳ trung gian là ngày cuối tháng.
- **Ngày hết hạn trước ngày kỷ niệm:** có thể còn cần trừ một ngày, theo chính sách hợp đồng.

### 5.5. Thiết kế lịch định kỳ có mốc gốc

Với hợp đồng bắt đầu ngày **30/01/2024**, chu kỳ một tháng, truy vấn sau tạo các mốc theo **ngày bắt đầu gốc**:

~~~sql
WITH moc AS (
    SELECT DATE '2024-01-30' AS ngay_goc
    FROM dual
)
SELECT LEVEL AS ky_so,
       TO_CHAR(
           ADD_MONTHS(ngay_goc, LEVEL),
           'YYYY-MM-DD'
       ) AS ngay_den_han
FROM moc
CONNECT BY LEVEL <= 4
ORDER BY ky_so;
~~~

Kết quả minh họa:

| Kỳ | Ngày đến hạn tính từ gốc |
| --- | --- |
| 1 | 2024-02-29 |
| 2 | 2024-03-30 |
| 3 | 2024-04-30 |
| 4 | 2024-05-30 |

Câu SQL tính **ADD_MONTHS(ngay_goc, n)**, không lấy ngày tháng trước làm đầu vào cho tháng tiếp theo. Nếu yêu cầu phải **luôn là ngày cuối tháng**, cách tạo lịch sẽ khác.

## 6. MONTHS_BETWEEN: hiệu theo tháng không phải số ngày chia 30

Hàm **MONTHS_BETWEEN(date1, date2)** trả **NUMBER** biểu thị chênh lệch theo tháng giữa hai DATE. Đây không phải INTERVAL YEAR TO MONTH, và phần thập phân không được tính bằng cách chia số ngày thực tế cho độ dài tháng tương ứng trong mọi trường hợp.

Theo quy tắc Oracle:

- Nếu hai ngày có cùng số ngày trong tháng hoặc **đều là ngày cuối tháng**, kết quả là **số tháng nguyên**.
- Với các trường hợp khác, phần lẻ được tính trên cơ sở **tháng 31 ngày**, đồng thời có thể xét phần thời gian trong ngày.
- Ngữ nghĩa tháng liên quan đến **NLS_CALENDAR** của phiên.

~~~sql
SELECT MONTHS_BETWEEN(
           DATE '2024-02-29',
           DATE '2024-01-31'
       ) AS so_thang_cuoi_thang
FROM dual;

SELECT MONTHS_BETWEEN(
           DATE '2024-04-15',
           DATE '2024-01-15'
       ) AS so_thang_cung_ngay
FROM dual;
~~~

Hai kết quả lần lượt là **1** và **3**. Dù khoảng từ 31/01 đến 29/02 có 29 ngày, MONTHS_BETWEEN trả 1 vì cả hai đều là ngày cuối tháng.

Với các ngày không đồng nhất, ví dụ ngày 10 đến ngày 21, hàm có thể trả số tháng phân số. Nếu hệ thống cần “số tháng tròn đã qua”, “tuổi theo tháng” hoặc “số kỳ hoàn tất”, cần nêu rõ cách làm tròn/truncation và xét ngày cuối tháng. Không nên trực tiếp dùng MONTHS_BETWEEN rồi làm tròn tùy tiện.

### 6.1. Hiệu số ngày và hiệu tháng là hai phép đo khác nhau

~~~sql
SELECT DATE '2024-03-31' - DATE '2024-02-29' AS so_ngay,
       MONTHS_BETWEEN(
           DATE '2024-03-31',
           DATE '2024-02-29'
       ) AS so_thang
FROM dual;
~~~

Với lịch Gregorian, kết quả là **31 ngày** nhưng **1 tháng**. Điều này không mâu thuẫn: phép trừ DATE đo số ngày, còn MONTHS_BETWEEN đo chênh lệch lịch theo quy tắc riêng.

## 7. TRUNC và ROUND: chuẩn hóa về ranh giới ngày/tháng

Oracle cung cấp **TRUNC(date, format)** để bỏ các phần thời gian nhỏ hơn một đơn vị và **ROUND(date, format)** để làm tròn theo ranh giới tương ứng.

### 7.1. Cắt phần giờ để so sánh theo ngày

~~~sql
SELECT TO_CHAR(
           TRUNC(
               TO_DATE('2024-03-15 16:45:30',
                       'YYYY-MM-DD HH24:MI:SS')
           ),
           'YYYY-MM-DD HH24:MI:SS'
       ) AS dau_ngay
FROM dual;
~~~

Kết quả **2024-03-15 00:00:00**. Dùng TRUNC khi cần chuẩn hóa một DATE có thời gian về đầu ngày, chẳng hạn khi lưu mốc báo cáo.

### 7.2. Đầu tháng và đầu năm

~~~sql
SELECT TO_CHAR(
           TRUNC(DATE '2024-03-19', 'MM'),
           'YYYY-MM-DD'
       ) AS dau_thang,

       TO_CHAR(
           TRUNC(DATE '2024-03-19', 'YYYY'),
           'YYYY-MM-DD'
       ) AS dau_nam
FROM dual;
~~~

Kết quả lần lượt là **2024-03-01** và **2024-01-01**. Có thể tìm đầu tháng tiếp theo:

~~~sql
SELECT ADD_MONTHS(
           TRUNC(DATE '2024-03-19', 'MM'),
           1
       ) AS dau_thang_ke_tiep
FROM dual;
~~~

### 7.3. ROUND không phải TRUNC

~~~sql
SELECT TO_CHAR(
           ROUND(
               TO_DATE('2024-03-15 16:00:00',
                       'YYYY-MM-DD HH24:MI:SS')
           ),
           'YYYY-MM-DD HH24:MI:SS'
       ) AS ngay_duoc_lam_tron
FROM dual;
~~~

Với ROUND theo ngày mặc định, thời điểm **16:00** nằm sau ngưỡng giữa ngày, nên kết quả được làm tròn về **00:00 ngày kế tiếp**. Trong khi đó TRUNC về **00:00 cùng ngày**.

Với báo cáo lọc dữ liệu, TRUNC thường dùng để xác định mốc thời gian; ROUND phù hợp khi thực sự muốn làm tròn. Nhưng có một lưu ý quan trọng về hiệu năng: đặt TRUNC trực tiếp lên cột trong điều kiện WHERE có thể làm thay đổi khả năng sử dụng index thông thường. Khi truy vấn một khoảng ngày, thường dễ tối ưu hơn bằng **điều kiện khoảng nửa kín**.

## 8. Truy vấn theo ngày bằng khoảng nửa kín

Một lỗi phổ biến khi lọc ngày có phần giờ là:

~~~sql
-- Có thể bỏ sót hàng trong ngày 31/03 sau 00:00:00.
SELECT *
FROM don_hang
WHERE ngay_dat BETWEEN DATE '2024-03-01'
                   AND DATE '2024-03-31';
~~~

Vì literal DATE ở hai đầu là **00:00:00**, truy vấn trên có thể bỏ sót các đơn hàng trong ngày 31/03 từ 00:00:01 trở đi.

Cách diễn đạt rõ ràng hơn:

~~~sql
SELECT *
FROM don_hang
WHERE ngay_dat >= DATE '2024-03-01'
  AND ngay_dat <  DATE '2024-04-01';
~~~

Phạm vi **[01/03, 01/04)** gồm mọi thời điểm từ đầu ngày 01/03 đến ngay trước ngày 01/04. Nó áp dụng được cả khi cột có phần giây của TIMESTAMP (với literal/cast phù hợp) mà không phải tự tạo giá trị 23:59:59.999...

Để chọn tháng theo một ngày đầu vào, xác định đầu tháng và đầu tháng kế tiếp:

~~~sql
SELECT *
FROM don_hang
WHERE ngay_dat >= TRUNC(DATE '2024-03-19', 'MM')
  AND ngay_dat <  ADD_MONTHS(
                        TRUNC(DATE '2024-03-19', 'MM'),
                        1
                   );
~~~

Tương tự, khi lọc một ngày:

~~~sql
SELECT *
FROM don_hang
WHERE ngay_dat >= DATE '2024-03-15'
  AND ngay_dat <  DATE '2024-03-16';
~~~

Sử dụng khoảng nửa kín giúp giữ ngữ nghĩa chính xác với dữ liệu có giờ và thường tạo điều kiện thuận lợi hơn cho index trên cột thời gian so với việc bọc cột bằng hàm, dù plan cuối cùng do optimizer quyết định.

## 9. NLS ảnh hưởng việc nhập và hiển thị ngày giờ

**NLS (National Language Support)** điều khiển nhiều thiết lập quốc tế hóa của phiên Oracle, bao gồm định dạng ngày, ngôn ngữ tên tháng và các quy tắc lịch. Tính toán với giá trị DATE/TIMESTAMP có kiểu dữ liệu rõ ràng sẽ ổn định hơn so với phép tính dựa trên chuỗi được parse ngầm.

### 9.1. NLS_DATE_FORMAT

Các session có thể đặt định dạng hiển thị/nhập ngày mặc định khác nhau. Ví dụ, cùng một DATE có thể được hiển thị:

~~~text
15-MAR-24
2024-03-15
15/03/2024
~~~

Cả ba chuỗi có thể đại diện cùng một giá trị DATE. Định dạng hiển thị **không thay đổi giá trị ngày lưu trong cột**.

Có thể xem một số thiết lập của phiên:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_CALENDAR',
    'NLS_TERRITORY'
)
ORDER BY parameter;
~~~

Không nên căn cứ vào dữ liệu được in ra trên giao diện để suy ra giá trị thời gian thật nếu chưa biết format.

### 9.2. Tránh implicit conversion

Ví dụ dễ lỗi:

~~~sql
-- Không an toàn nếu không biết NLS_DATE_FORMAT của session.
SELECT *
FROM don_hang
WHERE ngay_dat = '03/04/2024';
~~~

Chuỗi **03/04/2024** có thể được hiểu theo định dạng ngày/tháng hoặc tháng/ngày trong những môi trường khác nhau, hoặc không parse được.

Ưu tiên:

~~~sql
SELECT *
FROM don_hang
WHERE ngay_dat >= DATE '2024-04-03'
  AND ngay_dat <  DATE '2024-04-04';
~~~

Hoặc khi đầu vào phải là chuỗi có giờ:

~~~sql
SELECT TO_DATE(
           '2024-04-03 14:05:06',
           'YYYY-MM-DD HH24:MI:SS'
       ) AS thoi_diem
FROM dual;
~~~

Trong ứng dụng Java, nên **bind bằng kiểu ngày/giờ phù hợp** thay vì ghép chuỗi rồi phụ thuộc NLS của kết nối.

### 9.3. TO_CHAR và TO_DATE với format tường minh

~~~sql
SELECT TO_CHAR(
           DATE '2024-02-29',
           'YYYY-MM-DD'
       ) AS ngay_iso
FROM dual;

SELECT TO_CHAR(
           TIMESTAMP '2024-02-29 23:59:59.125',
           'YYYY-MM-DD HH24:MI:SS.FF3'
       ) AS thoi_diem_chi_tiet
FROM dual;
~~~

TO_CHAR phục vụ trình bày; TO_DATE/TO_TIMESTAMP dùng khi thực sự cần parse chuỗi về kiểu ngày giờ. Các format element như **YYYY, MM, DD, HH24, MI, SS, FF3** phải được chọn đúng theo kiểu dữ liệu.

Tên tháng bằng chữ chịu ảnh hưởng bởi **NLS_DATE_LANGUAGE**. Khi cần xử lý chuỗi tên tháng tiếng Anh một cách có chủ đích:

~~~sql
SELECT TO_DATE(
           '15-MAR-2024',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=ENGLISH'
       ) AS ngay_co_ten_thang
FROM dual;
~~~

Những format dùng số như **YYYY-MM-DD** thường đơn giản và ít phụ thuộc ngôn ngữ hơn.

### 9.4. NLS_CALENDAR và quy tắc tháng

**ADD_MONTHS**, **LAST_DAY** và **MONTHS_BETWEEN** dựa vào khái niệm tháng của thiết lập **NLS_CALENDAR**. Các ví dụ trong bài dùng lịch Gregorian. Nếu ứng dụng kết nối bằng nhiều session khác nhau nhưng cho phép cấu hình NLS_CALENDAR khác nhau, kết quả thao tác theo tháng có thể không đồng nhất với giả định của nghiệp vụ.

Ngược lại, **TRUNC(date, 'MM')** sử dụng quy tắc lịch Gregorian theo ngữ nghĩa được Oracle định nghĩa, và không đơn giản là dùng cùng quy tắc tháng theo NLS_CALENDAR. Vì vậy không nên suy luận mọi hàm với tham số MM đều có ngữ nghĩa lịch hoàn toàn giống nhau khi thay đổi NLS_CALENDAR.

Với hệ thống cần kết quả đồng nhất qua nhiều môi trường, hãy xác định quy tắc lịch được chấp nhận, cấu hình session một cách có kiểm soát và kiểm thử trên môi trường Oracle thực tế.

## 10. SYSDATE, CURRENT_DATE và mốc thời gian hệ thống

Khi tính toán so với “hiện tại”, cần biết nguồn thời gian và múi giờ của hàm:

| Hàm | Ý nghĩa chính | Chú ý |
| --- | --- | --- |
| **SYSDATE** | Ngày/giờ hiện tại của máy chủ database dưới dạng DATE | Không lưu phần giây phân số, không mang múi giờ trong giá trị DATE |
| **SYSTIMESTAMP** | Timestamp hiện tại của máy chủ database kèm thông tin múi giờ | Hữu ích khi cần độ chính xác và offset |
| **CURRENT_DATE** | Ngày/giờ hiện tại theo múi giờ của session, trả DATE | Có thể khác SYSDATE khi session và máy chủ khác múi giờ |
| **CURRENT_TIMESTAMP** | Timestamp hiện tại theo múi giờ session | Thích hợp khi cần giữ thông tin múi giờ của session |
| **LOCALTIMESTAMP** | Timestamp hiện tại theo múi giờ session nhưng không mang thông tin múi giờ | Không thay thế giá trị tuyệt đối có offset |

~~~sql
SELECT SYSDATE,
       SYSTIMESTAMP,
       CURRENT_DATE,
       CURRENT_TIMESTAMP,
       LOCALTIMESTAMP
FROM dual;
~~~

Không kỳ vọng các giá trị trả về bằng nhau về kiểu và định dạng. Với ứng dụng chạy trên nhiều vùng địa lý, cần thống nhất một mô hình thời điểm và múi giờ thay vì trộn giờ server, giờ session và giờ trình duyệt.

## 11. Timestamp có múi giờ và chuyển giờ mùa hè

Một tháng lịch, một ngày lịch và một khoảng 24 giờ là những đại lượng có thể khác nhau khi vận hành theo **múi giờ địa phương có DST**:

- Lịch họp “09:00 giờ địa phương mỗi ngày” đòi hỏi giữ giờ dân sự địa phương theo vùng giờ.
- Một tác vụ “chạy tiếp sau đúng 24 giờ đã trôi qua” đòi hỏi ngữ nghĩa thời lượng đã trôi qua.
- “Ngày cuối tháng 23:59 theo múi giờ khách hàng” đòi hỏi xác định múi giờ trước khi so sánh với thời điểm tuyệt đối.

**TIMESTAMP** thông thường không có múi giờ nên một giá trị như **2024-03-31 02:30:00** không tự cho biết đó là thời điểm hợp lệ ở vùng nào. Với một số vùng, giờ đó có thể bị bỏ qua hoặc xuất hiện hai lần do DST.

Nếu cần mô tả một thời điểm thuộc vùng giờ cụ thể, cân nhắc **TIMESTAMP WITH TIME ZONE** và quy tắc hiển thị/so sánh phù hợp. Không tự động thay “một tháng” thành “30 ngày” hay “một ngày lịch” thành “24 giờ” khi yêu cầu liên quan đến múi giờ và lịch dân sự.

Trong một ứng dụng Java, cần phân biệt:

- **LocalDate**: ngày lịch không có giờ và múi giờ.
- **LocalDateTime**: ngày/giờ địa phương, không tự biểu thị một thời điểm toàn cục.
- **Instant**: thời điểm trên trục thời gian UTC.
- **OffsetDateTime / ZonedDateTime**: thời điểm có offset hoặc vùng giờ và các quy tắc liên quan.
- **Period**: khoảng theo năm/tháng/ngày lịch.
- **Duration**: khoảng theo giây/nano giây.

Kiểu Oracle và kiểu Java cần được chọn từ **ý nghĩa nghiệp vụ**, không chỉ từ độ dài chuỗi ngày giờ trong payload.

## 12. Bộ dữ liệu mẫu để luyện DATE, TIMESTAMP và cuối tháng

Thực hành trong **schema Oracle riêng**, có quyền tạo bảng và không chứa dữ liệu nghiệp vụ thật. Dùng mã và mốc ngày cố định để có thể dự đoán kết quả.

### 12.1. Tạo bảng

~~~sql
CREATE TABLE lich_gia_han_demo (
    ma_lich           NUMBER(5)
                      CONSTRAINT pk_lich_gia_han_demo PRIMARY KEY,
    ten_lich          VARCHAR2(100 CHAR) NOT NULL,
    ngay_bat_dau      DATE NOT NULL,
    thoi_diem_xu_ly   TIMESTAMP(3),
    chu_ky_thang      NUMBER(3) NOT NULL,
    thoi_luong_xu_ly  INTERVAL DAY(3) TO SECOND(3),
    CONSTRAINT ck_chu_ky_thang
        CHECK (chu_ky_thang BETWEEN 1 AND 36)
);
~~~

Trong bảng:

- **NGAY_BAT_DAU** là ngày hợp đồng/kỳ theo kiểu DATE.
- **THOI_DIEM_XU_LY** là mốc chạy tác vụ với mili giây.
- **CHU_KY_THANG** là số tháng lịch nguyên cho ADD_MONTHS.
- **THOI_LUONG_XU_LY** là duration theo ngày/giờ/phút/giây.
- Giá trị **NULL** ở hai cột tùy chọn có nghĩa chưa có thời điểm/thời lượng, khác duration bằng 0.

### 12.2. Nạp dữ liệu

~~~sql
INSERT INTO lich_gia_han_demo
    (ma_lich, ten_lich, ngay_bat_dau,
     thoi_diem_xu_ly, chu_ky_thang, thoi_luong_xu_ly)
VALUES (
    101,
    'Bat dau cuoi thang 1',
    DATE '2024-01-31',
    TIMESTAMP '2024-01-31 22:40:00.000',
    1,
    INTERVAL '0 02:30:00.250' DAY TO SECOND(3)
);

INSERT INTO lich_gia_han_demo
    (ma_lich, ten_lich, ngay_bat_dau,
     thoi_diem_xu_ly, chu_ky_thang, thoi_luong_xu_ly)
VALUES (
    102,
    'Bat dau ngay 30',
    DATE '2024-01-30',
    TIMESTAMP '2024-01-30 10:00:00.000',
    1,
    INTERVAL '0 01:00:00.000' DAY TO SECOND(3)
);

INSERT INTO lich_gia_han_demo
    (ma_lich, ten_lich, ngay_bat_dau,
     thoi_diem_xu_ly, chu_ky_thang, thoi_luong_xu_ly)
VALUES (
    103,
    'Bat dau ngay nhuan',
    DATE '2024-02-29',
    TIMESTAMP '2024-02-29 23:59:00.000',
    12,
    INTERVAL '0 00:02:00.000' DAY TO SECOND(3)
);

INSERT INTO lich_gia_han_demo
    (ma_lich, ten_lich, ngay_bat_dau,
     thoi_diem_xu_ly, chu_ky_thang, thoi_luong_xu_ly)
VALUES (
    104,
    'Chua co thoi diem xu ly',
    DATE '2024-03-15',
    NULL,
    2,
    NULL
);

INSERT INTO lich_gia_han_demo
    (ma_lich, ten_lich, ngay_bat_dau,
     thoi_diem_xu_ly, chu_ky_thang, thoi_luong_xu_ly)
VALUES (
    105,
    'Chuyen giao nam moi',
    DATE '2024-12-31',
    TIMESTAMP '2024-12-31 23:45:00.000',
    1,
    INTERVAL '0 00:30:00.000' DAY TO SECOND(3)
);

COMMIT;
~~~

Các ngày được chọn có chủ ý: cuối tháng 1, ngày 30 trước tháng 2, ngày nhuận, ngày bình thường và đêm giao thừa.

### 12.3. Tính ngày gia hạn theo tháng

~~~sql
SELECT ma_lich,
       TO_CHAR(ngay_bat_dau, 'YYYY-MM-DD') AS ngay_goc,
       chu_ky_thang,
       TO_CHAR(
           ADD_MONTHS(ngay_bat_dau, chu_ky_thang),
           'YYYY-MM-DD'
       ) AS ngay_gia_han
FROM lich_gia_han_demo
ORDER BY ma_lich;
~~~

Kết quả dự kiến theo lịch Gregorian:

| Mã | Ngày gốc | Chu kỳ | Ngày gia hạn |
| --- | --- | ---: | --- |
| 101 | 2024-01-31 | 1 | 2024-02-29 |
| 102 | 2024-01-30 | 1 | 2024-02-29 |
| 103 | 2024-02-29 | 12 | 2025-02-28 |
| 104 | 2024-03-15 | 2 | 2024-05-15 |
| 105 | 2024-12-31 | 1 | 2025-01-31 |

Hàng **101** và **102** có cùng kết quả tháng sau nhưng xuất phát từ hai ngày khác nhau. Điều này minh họa quy tắc tháng đích không đủ ngày.

### 12.4. Tính thời điểm kết thúc xử lý

~~~sql
SELECT ma_lich,
       TO_CHAR(
           thoi_diem_xu_ly,
           'YYYY-MM-DD HH24:MI:SS.FF3'
       ) AS bat_dau_xu_ly,
       TO_CHAR(
           thoi_diem_xu_ly + thoi_luong_xu_ly,
           'YYYY-MM-DD HH24:MI:SS.FF3'
       ) AS ket_thuc_xu_ly
FROM lich_gia_han_demo
ORDER BY ma_lich;
~~~

Kết quả:

| Mã | Thời điểm kết thúc |
| --- | --- |
| 101 | **2024-02-01 01:10:00.250** |
| 102 | **2024-01-30 11:00:00.000** |
| 103 | **2024-03-01 00:01:00.000** |
| 104 | **NULL** |
| 105 | **2025-01-01 00:15:00.000** |

Ví dụ 101 chứng minh cộng 2 giờ 30 phút có thể bước qua ngày mới. Ví dụ 103 bước qua ranh giới ngày nhuận; ví dụ 105 bước qua năm mới. Hàng 104 là dữ liệu chưa biết, không thể mặc định kết thúc ngay thời điểm bắt đầu.

### 12.5. Phân biệt NULL và khoảng bằng 0

~~~sql
SELECT ma_lich
FROM lich_gia_han_demo
WHERE thoi_luong_xu_ly IS NULL;
~~~

Trả mã **104**. Nếu cần tìm khoảng thời gian bằng 0, truy vấn là:

~~~sql
SELECT ma_lich
FROM lich_gia_han_demo
WHERE thoi_luong_xu_ly = INTERVAL '0' SECOND;
~~~

Bộ dữ liệu trên không có hàng nào có duration bằng 0; đó là trạng thái khác với giá trị NULL. Khi xây dựng báo cáo cần giữ sự phân biệt trừ khi đặc tả nghiệp vụ yêu cầu quy đổi.

### 12.6. Lọc những lịch bắt đầu trong tháng 2 năm nhuận

~~~sql
SELECT ma_lich, ten_lich
FROM lich_gia_han_demo
WHERE ngay_bat_dau >= DATE '2024-02-01'
  AND ngay_bat_dau <  DATE '2024-03-01';
~~~

Kết quả **103**. Dùng khoảng nửa kín giúp câu SQL đúng kể cả khi NGAY_BAT_DAU có giờ/phút/giây.

### 12.7. Tính các kỳ dựa trên ngày gốc

~~~sql
SELECT l.ma_lich,
       ky.so_ky,
       TO_CHAR(
           ADD_MONTHS(l.ngay_bat_dau,
                      l.chu_ky_thang * ky.so_ky),
           'YYYY-MM-DD'
       ) AS ngay_ky
FROM lich_gia_han_demo l
CROSS JOIN (
    SELECT LEVEL AS so_ky
    FROM dual
    CONNECT BY LEVEL <= 3
) ky
WHERE l.ma_lich = 102
ORDER BY ky.so_ky;
~~~

Với mã **102**, chu kỳ 1 tháng và ngày gốc 30/01/2024, kết quả là:

| Kỳ | Ngày |
| --- | --- |
| 1 | 2024-02-29 |
| 2 | 2024-03-30 |
| 3 | 2024-04-30 |

Truy vấn tính trực tiếp từ ngày gốc. Nếu lấy ngày kỳ trước cộng thêm một tháng, kết quả kỳ 2 có thể thành **31/03**. Phải chọn mô hình lịch từ yêu cầu kinh doanh.

### 12.8. Dọn dữ liệu thực hành

Khi chắc chắn đây là bảng sandbox được phép xóa:

~~~sql
DROP TABLE lich_gia_han_demo PURGE;
~~~

**PURGE** tránh đưa bảng vào recycle bin theo hành vi thông thường; không dùng câu lệnh này trên bảng nghiệp vụ. DDL có quy tắc implicit commit riêng nên không được coi là thao tác rollback giống DELETE thông thường.

## 13. Ứng dụng Java: tính ở đâu và truyền dữ liệu thế nào?

Có hai hướng thường gặp:

1. **Tính toán trong Oracle** khi ngày gốc, chu kỳ và dữ liệu nghiệp vụ đã nằm trong database, đặc biệt khi một câu SQL có thể xử lý nhiều hàng nhất quán.
2. **Tính toán trong Java** với các kiểu **java.time** nếu ứng dụng sở hữu quy tắc lịch và cần phối hợp nhiều hệ thống. Khi đó phải xác định chính xác sự tương đương giữa quy tắc Java và Oracle.

### 13.1. JDBC: bind ngày/giờ có kiểu rõ ràng

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Date;
import java.time.LocalDate;
import javax.sql.DataSource;

public final class LichGiaHanRepository {
    private final DataSource dataSource;

    public LichGiaHanRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public LocalDate tinhNgayGiaHan(LocalDate ngayGoc, int soThang)
            throws SQLException {
        String sql = """
            SELECT ADD_MONTHS(?, ?) AS ngay_gia_han
            FROM dual
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setDate(1, Date.valueOf(ngayGoc));
            statement.setInt(2, soThang);

            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    throw new SQLException("No result from ADD_MONTHS");
                }
                return rows.getDate("NGAY_GIA_HAN").toLocalDate();
            }
        }
    }
}
~~~

**PreparedStatement** giúp truyền dữ liệu độc lập với cú pháp SQL, tránh ghép chuỗi ngày tháng vào câu truy vấn và giảm phụ thuộc NLS khi driver gửi giá trị có kiểu. Ví dụ dùng **java.sql.Date** vì đầu vào chỉ là ngày lịch, không cần giờ/múi giờ.

Một lưu ý quan trọng: **LocalDate.plusMonths** của Java thường xử lý ngày đích không tồn tại bằng cách đưa về ngày cuối tháng hợp lệ, nhưng quy tắc “bám cuối tháng” cho những trường hợp ngày gốc đã là ngày cuối tháng có thể **khác ADD_MONTHS**. Ví dụ ngày **28/02/2023** là ngày cuối tháng; ADD_MONTHS thêm một tháng đưa tới **31/03/2023**, trong khi cách cộng LocalDate.plusMonths(1) thường cho **28/03/2023**. Nếu kết quả Java và Oracle phải giống nhau, cần định nghĩa rõ quy tắc nghiệp vụ và kiểm thử các ngày cuối tháng.

### 13.2. Không tự động đổi Period thành Duration

Trong Java:

- **Period.ofMonths(1)** biểu diễn một tháng lịch.
- **Duration.ofDays(30)** biểu diễn đúng 30 ngày theo mô hình duration.
- **Duration.ofHours(24)** biểu diễn 24 giờ.

Chúng không thể thay thế cho nhau chỉ vì trong một vài lần thử đều ra cùng ngày. Khi tính lịch gia hạn nên giữ **số tháng**, còn khi tính thời lượng xử lý nên giữ **số giây/mili giây**.

Nếu driver không có ánh xạ trực tiếp thuận tiện từ java.time.Duration sang Oracle INTERVAL DAY TO SECOND, có thể bind giá trị giây và dùng **NUMTODSINTERVAL(?, 'SECOND')**. Với số tháng, dùng **NUMTOYMINTERVAL(?, 'MONTH')** hoặc **ADD_MONTHS(?, ?)** tùy mục tiêu.

## 14. Lỗi điển hình khi tính ngày giờ

| Hiện tượng | Nguyên nhân phổ biến | Hướng xử lý |
| --- | --- | --- |
| Cộng một tháng từ 31/01 báo lỗi | Phép cộng INTERVAL tạo ngày không tồn tại | Xác định quy tắc nghiệp vụ; xem ADD_MONTHS khi cần đưa về cuối tháng |
| Cộng tháng theo từng kỳ cho kết quả khác cộng từ ngày gốc | Hiệu ứng bám cuối tháng của ADD_MONTHS | Quy định rõ tính từ kỳ trước hay từ ngày gốc |
| Lọc BETWEEN đến ngày 31/03 nhưng thiếu một số đơn ngày 31 | Biên trên DATE literal là 00:00:00 | Dùng >= đầu ngày và < đầu ngày kế tiếp |
| DATE - DATE trả số không phải interval | Oracle quy định hiệu DATE là NUMBER ngày | Quy đổi đơn vị rõ ràng hoặc CAST thành TIMESTAMP trước khi trừ |
| Hai môi trường cùng chuỗi ngày nhưng ra kết quả khác | NLS_DATE_FORMAT/NLS_DATE_LANGUAGE và implicit conversion | Dùng DATE/TIMESTAMP literal, bind hoặc format tường minh |
| ADD_MONTHS/LAST_DAY khác mong đợi ở hệ thống đa lịch | NLS_CALENDAR khác quy tắc giả định | Kiểm tra và thống nhất chính sách lịch |
| Kết quả qua DST lệch một giờ | Nhầm ngày lịch với duration tuyệt đối hoặc bỏ mất múi giờ | Chọn đúng kiểu TIMESTAMP WITH TIME ZONE và quy tắc lịch |
| Chênh lệch lớn giữa SYSDATE và CURRENT_DATE | Múi giờ server và session khác nhau | Xác định nguồn thời gian chuẩn của ứng dụng |
| TIMESTAMP bị mất mili giây | Chuyển sang DATE hoặc dùng format không có FF | Giữ TIMESTAMP và precision phù hợp |
| Ngày trong Java lệch so với Oracle sau cộng tháng | Quy tắc cuối tháng giữa LocalDate.plusMonths và ADD_MONTHS khác nhau | Kiểm thử ngày 28/29/30/31 và chuẩn hóa nghiệp vụ |
| Lấy LAST_DAY rồi coi là cuối ngày 23:59:59 | LAST_DAY trả DATE với phần thời gian liên quan đến đầu vào, không tự dựng cuối ngày | Lọc bằng khoảng nửa kín thay vì dựng giây cuối |
| Truy vấn chậm khi đặt TRUNC trực tiếp lên cột có index | Hàm trên cột có thể thay đổi khả năng truy cập index thường | Dùng range predicate hoặc index phù hợp khi cần |

Trong hệ thống thực tế, cách sửa phải dựa trên **ngữ nghĩa dữ liệu và kế hoạch truy vấn**, không chỉ thay hàm cho đến khi một ví dụ có kết quả mong muốn.

## 15. Bài tập tự luyện

1. Giải thích vì sao **DATE '2024-02-29' + 1** hợp lệ và có kết quả ngày nào.
2. Viết câu SQL tính **90 phút** sau thời điểm **2024-02-28 23:30:00** bằng NUMTODSINTERVAL.
3. Trừ hai DATE là **2024-03-02** và **2024-02-29**, xác định kiểu dữ liệu và đơn vị của kết quả.
4. Trừ hai TIMESTAMP có phần mili giây và đổi interval kết quả sang tổng giây bằng EXTRACT.
5. So sánh **ADD_MONTHS(DATE '2024-01-31', 1)** với **DATE '2024-01-31' + INTERVAL '1' MONTH**. Tại sao hành vi khác?
6. Vì sao **ADD_MONTHS(ADD_MONTHS(DATE '2024-01-30', 1), 1)** khác **ADD_MONTHS(DATE '2024-01-30', 2)**?
7. Một lịch cần luôn đến hạn vào **ngày cuối tháng**. Hãy nêu cách sử dụng LAST_DAY và ADD_MONTHS để tạo ba kỳ kế tiếp từ ngày 31/01/2024.
8. Dùng MONTHS_BETWEEN tính khoảng cách giữa **29/02/2024** và **31/01/2024**. Tại sao không cần chia hiệu số ngày cho 30?
9. Viết truy vấn tìm mọi đơn trong **tháng 3/2024** mà không bỏ sót bản ghi có giờ vào ngày 31.
10. Nêu khác biệt giữa TRUNC và ROUND đối với DATE có thời gian **16:00:00**.
11. Làm thế nào để hiển thị cùng một DATE thành chuỗi **YYYY-MM-DD** bất kể NLS_DATE_FORMAT?
12. Khi dùng tên tháng dạng chữ, vì sao cần quan tâm NLS_DATE_LANGUAGE?
13. Tại sao ADD_MONTHS, LAST_DAY và TRUNC(..., 'MM') cần được kiểm tra riêng khi ứng dụng cho phép thay đổi NLS_CALENDAR?
14. Phân biệt SYSDATE với CURRENT_DATE nếu database server và ứng dụng dùng múi giờ khác nhau.
15. Với một yêu cầu “chạy lúc 09:00 theo giờ địa phương mỗi ngày”, vì sao phải phân biệt ngày lịch và 24 giờ tuyệt đối?
16. Cho hợp đồng bắt đầu **28/02/2023**, hãy so sánh ngữ nghĩa cộng tháng của Oracle ADD_MONTHS với Java LocalDate.plusMonths; chọn quy tắc nào cho nghiệp vụ bảo hành?
17. Viết SQL tìm những hàng trong bảng LICH_GIA_HAN_DEMO có thời điểm kết thúc xử lý nằm sang **ngày tiếp theo**.
18. Tại sao một thời lượng chưa biết (NULL) không được mặc định lưu là khoảng bằng 0?

**Cộng trừ ngày giờ trong Oracle phải bắt đầu từ đơn vị và quy tắc lịch**: NUMBER cộng vào DATE đại diện số ngày, INTERVAL DAY TO SECOND dùng cho thời lượng ngày–giây, còn INTERVAL YEAR TO MONTH và ADD_MONTHS dùng cho tháng lịch với khác biệt quan trọng tại ngày cuối tháng. Hiểu LAST_DAY, MONTHS_BETWEEN, TRUNC và NLS giúp viết truy vấn nhất quán, trong khi các giới hạn về múi giờ và DATE/TIMESTAMP đảm bảo kết quả đúng với ý nghĩa nghiệp vụ thay vì chỉ đúng ở vài bộ dữ liệu mẫu.
