# IGNORE NULLS, RESPECT NULLS và lấp dữ liệu theo chuỗi trong Oracle

Trong dữ liệu thời gian, cảm biến có thể không gửi được một lần đo; hệ thống bán hàng có thể thiếu doanh thu ở một ngày; bảng trạng thái có thể chỉ ghi khi giá trị thay đổi. Vì vậy, một chuỗi dữ liệu thường có những hàng mà giá trị đo lường là NULL. Khi phân tích, câu hỏi không chỉ là “giá trị nào đang thiếu?” mà còn là **khi tính từ hàng trước hoặc hàng sau, Oracle có nên dừng ở NULL hay bỏ qua nó để tìm giá trị khác NULL tiếp theo?**

Oracle cung cấp hai tùy chọn xử lý NULL cho một số hàm phân tích: **RESPECT NULLS** và **IGNORE NULLS**. RESPECT NULLS giữ nguyên NULL trong quá trình tìm vị trí; IGNORE NULLS bỏ qua các giá trị NULL của biểu thức đang xét khi xác định giá trị thứ nhất, cuối cùng, trước đó hoặc tiếp theo. Hai tùy chọn này đặc biệt hữu ích với LAG, LEAD, FIRST_VALUE và LAST_VALUE, từ đó có thể xây dựng kỹ thuật **lấp dữ liệu theo chuỗi** (*data imputation*, *forward fill*, *backfill*).

Bài học thuộc chủ đề **Hàm phân tích** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Ý nghĩa và mặc định của RESPECT NULLS/IGNORE NULLS.
- Cách các hàm phân tích tìm giá trị khi gặp NULL.
- Lấp giá trị theo chiều tiến (forward fill) và chiều lùi (backfill).
- Xử lý chuỗi có nhiều nhóm, nhiều thời điểm trùng nhau và khoảng thời gian bị thiếu.
- Phân biệt carry-forward với nội suy tuyến tính.
- Các lưu ý về window frame, thứ tự xác định, chất lượng dữ liệu và hiệu năng.

## 1. NULL trong chuỗi dữ liệu có thể mang nhiều ý nghĩa

Một hàng có giá trị NULL không nhất thiết có nghĩa là số đo bằng 0. Nó có thể đại diện cho:

- Thiết bị không gửi dữ liệu trong kỳ.
- Giá trị chưa được thu thập hoặc chưa được nhập.
- Trường không áp dụng cho bản ghi đó.
- Một sự kiện đã xảy ra nhưng không có giá trị đo.
- Dữ liệu bị loại trong quá trình kiểm tra chất lượng.

Ví dụ chuỗi nhiệt độ:

| SENSOR_ID | MEASURED_AT | TEMPERATURE |
| ---: | --- | ---: |
| 7 | 09:00 | 24.5 |
| 7 | 10:00 | NULL |
| 7 | 11:00 | NULL |
| 7 | 12:00 | 25.2 |
| 7 | 13:00 | NULL |

Nếu báo cáo cần hiển thị “giá trị gần nhất đã biết”, ta có thể điền 24.5 cho 10:00 và 11:00, rồi điền 25.2 cho 13:00. Nhưng đây là một **quy tắc nghiệp vụ**: nó giả định giá trị gần nhất vẫn có thể đại diện cho thời điểm đang thiếu.

Với dữ liệu trạng thái (ví dụ trạng thái thiết bị chỉ ghi khi thay đổi), forward fill thường phù hợp vì trạng thái trước tiếp tục có hiệu lực cho đến khi có sự kiện mới. Với nhiệt độ, giá cổ phiếu hoặc lượng mưa, mang giá trị cũ sang tương lai có thể gây sai lệch. Trước khi lấp, phải xác định ý nghĩa của NULL và chính sách thời hạn hiệu lực.

## 2. RESPECT NULLS và IGNORE NULLS là gì?

Một số hàm phân tích Oracle cho phép chỉ định cách xử lý NULL trong biểu thức được xét:

- **RESPECT NULLS**: không bỏ qua giá trị NULL. Nếu vị trí cần lấy chứa NULL, kết quả của hàm có thể là NULL.
- **IGNORE NULLS**: bỏ qua những hàng mà biểu thức đầu vào là NULL khi tìm vị trí cần lấy; hàm tiếp tục tìm giá trị khác NULL.

Với các hàm hỗ trợ tùy chọn này, RESPECT NULLS là mặc định nếu không ghi rõ. Viết tường minh có thể giúp người đọc hiểu chính sách NULL:

~~~sql
LAG(measurement) RESPECT NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY measured_at, reading_id
)
~~~

So sánh:

~~~sql
LAG(measurement) IGNORE NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY measured_at, reading_id
)
~~~

Biểu thức thứ nhất lấy giá trị của hàng liền trước theo thứ tự, kể cả khi giá trị đó NULL. Biểu thức thứ hai tìm giá trị khác NULL gần nhất trước hàng hiện tại.

### Hàm nào hỗ trợ?

Trong Oracle, tùy chọn NULL treatment được hỗ trợ bởi một số hàm analytic, phổ biến nhất:

| Hàm | RESPECT NULLS | IGNORE NULLS | Ý nghĩa khi IGNORE |
| --- | --- | --- | --- |
| LAG | Có | Có | Tìm giá trị khác NULL ở phía trước hàng hiện tại. |
| LEAD | Có | Có | Tìm giá trị khác NULL ở phía sau hàng hiện tại. |
| FIRST_VALUE | Có | Có | Lấy giá trị khác NULL đầu tiên trong frame. |
| LAST_VALUE | Có | Có | Lấy giá trị khác NULL cuối cùng trong frame. |
| NTH_VALUE | Có | Có | Lấy giá trị khác NULL thứ N trong frame theo hướng FIRST/LAST. |

Không phải mọi hàm analytic đều nhận mệnh đề IGNORE NULLS. Chỉ dùng nó với các hàm có cú pháp hỗ trợ trong phiên bản Oracle đang chạy.

### NULL treatment không thay đổi dữ liệu gốc

IGNORE NULLS chỉ điều khiển cách hàm phân tích tìm giá trị. Nó không:

- UPDATE cột trong bảng.
- Xóa hàng có NULL.
- Biến NULL thành 0.
- Tạo thêm hàng cho thời điểm chưa tồn tại.
- Chứng minh giá trị được lấp là giá trị thực tế đã đo.

Kết quả vẫn là một biểu thức trong tập kết quả SELECT. Nếu cần lưu dữ liệu đã lấp, phải thực hiện một bước DML riêng sau khi xác nhận chính sách và dữ liệu đích.

## 3. RESPECT NULLS: giữ nguyên vị trí NULL

Giả sử chuỗi được sắp theo thời gian:

| SEQ_NO | VALUE |
| ---: | ---: |
| 1 | 10 |
| 2 | NULL |
| 3 | 30 |
| 4 | NULL |
| 5 | 50 |

Truy vấn:

~~~sql
SELECT seq_no,
       value,
       LAG(value) RESPECT NULLS OVER (
           ORDER BY seq_no
       ) AS previous_value
FROM lab_sequence
ORDER BY seq_no;
~~~

Kết quả:

| SEQ_NO | VALUE | PREVIOUS_VALUE |
| ---: | ---: | ---: |
| 1 | 10 | NULL |
| 2 | NULL | 10 |
| 3 | 30 | NULL |
| 4 | NULL | 30 |
| 5 | 50 | NULL |

LAG lấy đúng hàng đứng trước. Ở hàng 3, hàng trước có VALUE NULL, vì vậy kết quả là NULL; hàm không tiếp tục lùi về hàng 1.

Đây là hành vi phù hợp khi **vị trí hàng** mang ý nghĩa và NULL phải được giữ nguyên. Ví dụ, cần biết lần ghi liền trước có dữ liệu hay không, hoặc muốn phát hiện khoảng trống giữa hai sự kiện.

## 4. IGNORE NULLS: tìm giá trị khác NULL gần nhất

Dùng cùng dữ liệu nhưng đổi sang:

~~~sql
SELECT seq_no,
       value,
       LAG(value) IGNORE NULLS OVER (
           ORDER BY seq_no
       ) AS previous_non_null
FROM lab_sequence
ORDER BY seq_no;
~~~

Kết quả:

| SEQ_NO | VALUE | PREVIOUS_NON_NULL |
| ---: | ---: | ---: |
| 1 | 10 | NULL |
| 2 | NULL | 10 |
| 3 | 30 | 10 |
| 4 | NULL | 30 |
| 5 | 50 | 30 |

Ở hàng 3, LAG IGNORE NULLS bỏ qua hàng 2 vì VALUE NULL và tìm hàng 1 có giá trị 10. Ở hàng 5, hàm bỏ qua hàng 4 để tìm giá trị 30 ở hàng 3.

### Offset đếm giá trị phù hợp

Với IGNORE NULLS, offset được tính trên những giá trị không NULL được xét, không đơn thuần là số hàng vật lý:

~~~sql
LAG(value, 2) IGNORE NULLS OVER (
    ORDER BY seq_no
)
~~~

Biểu thức này tìm giá trị khác NULL thứ hai ở phía trước hàng hiện tại. Nếu dùng RESPECT NULLS, offset 2 có nghĩa là hàng đứng cách hai vị trí theo thứ tự, kể cả khi biểu thức ở hàng đó là NULL.

### Default của LAG/LEAD không phải giá trị thay thế NULL ở mọi trường hợp

Cú pháp:

~~~sql
LAG(value_expr [, offset [, default_value]])
    [{RESPECT | IGNORE} NULLS]
    OVER (analytic_clause)
~~~

Default chỉ được dùng khi không có hàng ở offset tương ứng theo cách tìm đã chọn. Nó không có nghĩa “nếu giá trị hàng được tìm thấy là NULL thì thay bằng default”.

~~~sql
SELECT seq_no,
       value,
       LAG(value, 1, -1) RESPECT NULLS OVER (
           ORDER BY seq_no
       ) AS previous_respect,
       LAG(value, 1, -1) IGNORE NULLS OVER (
           ORDER BY seq_no
       ) AS previous_ignore
FROM lab_sequence
ORDER BY seq_no;
~~~

- Ở hàng đầu tiên, không có hàng trước nên cả hai biểu thức dùng default -1.
- Ở hàng 3, hàng trước có giá trị NULL: RESPECT trả NULL; IGNORE tiếp tục tìm giá trị 10.
- Default không được dùng ở hàng 3 trong trường hợp RESPECT vì hàng trước **có tồn tại**, chỉ là giá trị của nó NULL.

Điểm này thường bị nhầm với NVL(LAG(...), default). Hai cách không tương đương:

~~~sql
NVL(
    LAG(value) RESPECT NULLS OVER (ORDER BY seq_no),
    -1
)
~~~

NVL thay mọi kết quả NULL, kể cả NULL do hàng trước thực sự có giá trị NULL; default trong LAG chỉ xử lý trường hợp không có hàng ở offset.

## 5. FIRST_VALUE và LAST_VALUE với IGNORE NULLS

FIRST_VALUE và LAST_VALUE tìm giá trị đầu tiên/cuối cùng trong **window frame** của hàng hiện tại. Khi kết hợp IGNORE NULLS, chúng bỏ qua giá trị NULL trong frame.

### FIRST_VALUE

~~~sql
FIRST_VALUE(measurement) IGNORE NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY measured_at, reading_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
~~~

Biểu thức trả giá trị khác NULL đầu tiên của toàn partition và lặp nó trên các hàng trong partition. Nếu không có giá trị khác NULL, kết quả vẫn NULL.

### LAST_VALUE

~~~sql
LAST_VALUE(measurement) IGNORE NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY measured_at, reading_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
~~~

Biểu thức trả giá trị khác NULL cuối cùng của toàn partition. Nếu chỉ muốn giá trị khác NULL gần nhất **tính đến hàng hiện tại**, cần giới hạn frame kết thúc ở current row:

~~~sql
LAST_VALUE(measurement) IGNORE NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY measured_at, reading_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Đây là cấu trúc quan trọng nhất để forward fill.

### Vì sao phải chỉ rõ frame?

Khi một analytic function có ORDER BY mà không chỉ định frame, nhiều hàm dùng frame mặc định tương đương:

`RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`

LAST_VALUE vì thế có thể chỉ nhìn đến hàng hiện tại/peer hiện tại, thay vì toàn bộ partition. Ngược lại, nếu cần forward fill, frame kết thúc ở CURRENT ROW là chủ đích; nếu muốn giá trị cuối toàn partition, phải cho frame tới UNBOUNDED FOLLOWING.

Không dựa vào frame mặc định trong báo cáo quan trọng. Viết rõ ROWS/RANGE và hai biên frame để người đọc biết chính xác cửa sổ được xét.

## 6. Forward fill: lấp NULL bằng giá trị khác NULL gần nhất phía trước

Forward fill (còn gọi là *last observation carried forward*, LOCF) dùng giá trị hợp lệ gần nhất trước đó để lấp hàng hiện tại. Với một chuỗi được sắp theo thời gian, công thức cốt lõi là:

~~~sql
LAST_VALUE(value) IGNORE NULLS OVER (
    PARTITION BY series_id
    ORDER BY event_time, event_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Ví dụ bảng cảm biến:

| SENSOR_ID | READING_ID | READING_TIME | MEASURE |
| ---: | ---: | --- | ---: |
| 7 | 1 | 09:00 | 24.5 |
| 7 | 2 | 10:00 | NULL |
| 7 | 3 | 11:00 | NULL |
| 7 | 4 | 12:00 | 25.2 |
| 7 | 5 | 13:00 | NULL |

~~~sql
SELECT sensor_id,
       reading_id,
       reading_time,
       measure,
       LAST_VALUE(measure) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS measure_filled
FROM lab_sensor_readings
ORDER BY sensor_id, reading_time, reading_id;
~~~

Kết quả:

| READING_TIME | MEASURE | MEASURE_FILLED |
| --- | ---: | ---: |
| 09:00 | 24.5 | 24.5 |
| 10:00 | NULL | 24.5 |
| 11:00 | NULL | 24.5 |
| 12:00 | 25.2 | 25.2 |
| 13:00 | NULL | 25.2 |

Ở mỗi hàng, frame gồm từ đầu partition đến hàng hiện tại. LAST_VALUE IGNORE NULLS chọn giá trị đo khác NULL gần nhất trong frame.

### Forward fill không thể lấp các NULL đứng đầu chuỗi

Nếu partition bắt đầu bằng:

| SEQ_NO | VALUE |
| ---: | ---: |
| 1 | NULL |
| 2 | NULL |
| 3 | 15 |
| 4 | NULL |

Ở hàng 1 và 2 không có giá trị khác NULL nào ở phía trước. Forward fill đúng nghĩa sẽ trả NULL cho hai hàng đó; từ hàng 3 trở đi có thể lấp bằng 15. Không nên tự động lấy giá trị tương lai nếu nghiệp vụ yêu cầu chỉ carry-forward.

## 7. Backfill: lấp NULL bằng giá trị khác NULL gần nhất phía sau

Backfill dùng giá trị tương lai đầu tiên khác NULL để lấp hàng đang thiếu. Công thức:

~~~sql
FIRST_VALUE(value) IGNORE NULLS OVER (
    PARTITION BY series_id
    ORDER BY event_time, event_id
    ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
)
~~~

~~~sql
SELECT sensor_id,
       reading_id,
       reading_time,
       measure,
       FIRST_VALUE(measure) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
           ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
       ) AS measure_backfilled
FROM lab_sensor_readings
ORDER BY sensor_id, reading_time, reading_id;
~~~

Với chuỗi 24.5, NULL, NULL, 25.2, NULL, kết quả backfill là:

| READING_TIME | MEASURE | MEASURE_BACKFILLED |
| --- | ---: | ---: |
| 09:00 | 24.5 | 24.5 |
| 10:00 | NULL | 25.2 |
| 11:00 | NULL | 25.2 |
| 12:00 | 25.2 | 25.2 |
| 13:00 | NULL | NULL |

Các hàng NULL cuối chuỗi không có giá trị tương lai khác NULL nên vẫn NULL. Đây là đặc tính đúng của backfill.

| Kỹ thuật | Hàm thường dùng | Frame | Giá trị được chọn |
| --- | --- | --- | --- |
| Forward fill | LAST_VALUE IGNORE NULLS | UNBOUNDED PRECEDING đến CURRENT ROW | Giá trị hợp lệ gần nhất ở quá khứ hoặc hiện tại |
| Backfill | FIRST_VALUE IGNORE NULLS | CURRENT ROW đến UNBOUNDED FOLLOWING | Giá trị hợp lệ gần nhất ở tương lai hoặc hiện tại |
| Giá trị đầu tiên toàn chuỗi | FIRST_VALUE IGNORE NULLS | Toàn partition | Giá trị khác NULL đầu tiên |
| Giá trị cuối cùng toàn chuỗi | LAST_VALUE IGNORE NULLS | Toàn partition | Giá trị khác NULL cuối cùng |

## 8. Lấp cả NULL đầu chuỗi và NULL ở giữa/cuối

Một chính sách phổ biến là **ưu tiên giá trị quá khứ**, nhưng nếu chưa có giá trị quá khứ thì dùng giá trị tương lai đầu tiên. Có thể kết hợp forward fill và backfill:

~~~sql
WITH filled_candidates AS (
    SELECT sensor_id,
           reading_id,
           reading_time,
           measure,
           LAST_VALUE(measure) IGNORE NULLS OVER (
               PARTITION BY sensor_id
               ORDER BY reading_time, reading_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS previous_measure,
           FIRST_VALUE(measure) IGNORE NULLS OVER (
               PARTITION BY sensor_id
               ORDER BY reading_time, reading_id
               ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
           ) AS next_measure
    FROM lab_sensor_readings
)
SELECT sensor_id,
       reading_id,
       reading_time,
       measure,
       COALESCE(previous_measure, next_measure) AS measure_filled
FROM filled_candidates
ORDER BY sensor_id, reading_time, reading_id;
~~~

COALESCE ưu tiên `previous_measure`. Chỉ khi không có giá trị quá khứ khác NULL, biểu thức mới dùng `next_measure`. Do đó:

- NULL đứng đầu chuỗi được backfill bằng giá trị khác NULL đầu tiên phía sau.
- NULL ở giữa chuỗi được forward fill từ giá trị gần nhất phía trước.
- NULL cuối chuỗi được forward fill từ giá trị gần nhất phía trước.
- Nếu toàn partition đều NULL, kết quả vẫn NULL.

Đây là **quy tắc ưu tiên quá khứ**, không phải chọn giá trị gần nhất theo khoảng cách thời gian. Nếu hàng thiếu nằm giữa hai điểm cách nhau không đều, giá trị quá khứ có thể xa hơn giá trị tương lai. Khi cần nearest-neighbor theo thời gian, phải tính cả khoảng cách trước/sau rồi so sánh.

## 9. Lấp dữ liệu theo nhiều chuỗi độc lập

Khi có nhiều sensor, khách hàng hoặc tài khoản, luôn xác định partition key để không mang dữ liệu của chuỗi này sang chuỗi khác:

~~~sql
LAST_VALUE(measure) IGNORE NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY reading_time, reading_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Nếu bỏ PARTITION BY sensor_id, Oracle có thể lấy giá trị khác NULL từ sensor khác trong cùng thứ tự toàn cục. Kết quả sẽ sai về nghiệp vụ dù cú pháp hợp lệ.

Ví dụ có thêm khu vực và thiết bị:

~~~sql
LAST_VALUE(measure) IGNORE NULLS OVER (
    PARTITION BY site_id, sensor_id
    ORDER BY reading_time, reading_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Chọn đủ các cột định danh chuỗi. Nếu SENSOR_ID chỉ duy nhất trong từng site, partition theo sensor đơn lẻ sẽ trộn dữ liệu giữa các site.

## 10. Thứ tự phải xác định: ORDER BY và ROWS

Forward fill/backfill phụ thuộc thứ tự. Nếu hai hàng có cùng timestamp, chỉ sắp theo timestamp có thể không xác định hàng nào đứng trước:

~~~sql
ORDER BY reading_time
~~~

Nếu hai lần đo cùng READING_TIME, Oracle có thể xử lý thứ tự peer theo cách không ổn định giữa các lần chạy/plan. Hãy thêm khóa phân biệt:

~~~sql
ORDER BY reading_time, reading_id
~~~

### Vì sao thường nên dùng ROWS?

Với ORDER BY mà không chỉ định frame, frame mặc định cho nhiều hàm analytic là RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW. RANGE coi các hàng có cùng giá trị sort là peers. Trong dữ liệu có timestamp trùng nhau, các hàng peer có thể cùng nằm trong frame hiện tại.

Forward fill thường cần một thứ tự hàng xác định, vì vậy nên viết:

~~~sql
LAST_VALUE(measure) IGNORE NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY reading_time, reading_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

ROWS cùng tie-breaker làm rõ thứ tự logic trong chuỗi. Nếu nghiệp vụ muốn mọi bản ghi cùng timestamp được coi là một mốc và cùng nhận một giá trị, có thể thiết kế theo RANGE hoặc tổng hợp về một hàng mỗi timestamp trước; đừng để frame mặc định quyết định thay bạn.

### Thời gian trùng và quy tắc nghiệp vụ

Nếu cùng một sensor có hai phép đo tại đúng một thời điểm, hãy quyết định:

- Giữ cả hai và xếp thứ tự bằng READING_ID/sequence?
- Gộp thành một giá trị (AVG, MAX, ưu tiên nguồn)?
- Chọn bản ghi mới nhất theo INGESTED_AT?
- Xem chúng là peers và cùng thuộc một frame?

Không có một tie-breaker kỹ thuật nào tự xác định đúng nghiệp vụ. Khóa phụ chỉ làm thứ tự ổn định sau khi quy tắc ưu tiên đã được chọn.

## 11. IGNORE NULLS không tự tạo hàng cho thời điểm bị thiếu

Một điểm rất quan trọng: IGNORE NULLS chỉ bỏ qua giá trị NULL trên **các hàng đang có**. Nếu bảng không có hàng lúc 10:00, analytic function không thể tự tạo ra một hàng 10:00 để lấp.

Giả sử dữ liệu chỉ có:

| READING_TIME | MEASURE |
| --- | ---: |
| 09:00 | 24.5 |
| 12:00 | 25.2 |

Không có hàng 10:00 và 11:00, vì vậy forward fill trên bảng gốc chỉ trả hai hàng 09:00 và 12:00. Muốn tạo chuỗi theo từng giờ, phải tạo **time spine/calendar** trước rồi LEFT JOIN dữ liệu đo.

### Tạo time spine bằng CONNECT BY

Ví dụ sinh 24 mốc giờ từ ngày bắt đầu:

~~~sql
SELECT DATE '2026-01-01' + (LEVEL - 1) / 24 AS hour_start
FROM dual
CONNECT BY LEVEL <= 24;
~~~

DATE trong Oracle có thể cộng số ngày; 1/24 là một giờ. Với lịch lớn, nhiều sensor hoặc nhiều múi giờ, nên dùng bảng calendar/time dimension được quản lý thay vì sinh chuỗi vô hạn trong mỗi truy vấn.

### Ghép time spine với dữ liệu

Giả sử bảng LAB_SENSOR_READINGS có tối đa một bản ghi cho mỗi sensor và giờ:

~~~sql
WITH hours AS (
    SELECT DATE '2026-01-01' + (LEVEL - 1) / 24 AS hour_start
    FROM dual
    CONNECT BY LEVEL <= 24
),
sensor_list AS (
    SELECT DISTINCT sensor_id
    FROM lab_sensor_readings
),
dense_series AS (
    SELECT s.sensor_id,
           h.hour_start,
           r.reading_id,
           r.measure
    FROM sensor_list s
    CROSS JOIN hours h
    LEFT JOIN lab_sensor_readings r
      ON r.sensor_id = s.sensor_id
     AND r.reading_time = h.hour_start
)
SELECT sensor_id,
       hour_start,
       measure,
       LAST_VALUE(measure) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY hour_start
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS measure_filled
FROM dense_series
ORDER BY sensor_id, hour_start;
~~~

Đoạn SQL minh họa yêu cầu dữ liệu nguồn đã chuẩn hóa về đúng mốc giờ. Nếu có nhiều reading trong cùng một giờ, cần aggregate hoặc chọn một reading đại diện trước khi JOIN để không nhân bản time spine. Cũng cần tạo danh sách sensor theo phạm vi báo cáo mong muốn; lấy DISTINCT từ bảng readings sẽ không bao gồm sensor chưa từng gửi dữ liệu.

## 12. Carry-forward khác nội suy tuyến tính

Forward fill mang giá trị trước đó sang thời điểm thiếu. Nó không tính giá trị trung gian. Ví dụ:

| THỜI ĐIỂM | GIÁ TRỊ ĐÃ BIẾT |
| --- | ---: |
| 09:00 | 10 |
| 10:00 | NULL |
| 11:00 | 30 |

Forward fill cho 10:00 giá trị 10. Backfill cho 10:00 giá trị 30. **Nội suy tuyến tính** giả định thay đổi đều giữa hai điểm đã biết và cho giá trị 20 tại 10:00.

Với một cột DATE và giá trị số, có thể lấy hàng khác NULL gần nhất trước/sau bằng LAST_VALUE/FIRST_VALUE rồi tính tỷ lệ thời gian:

~~~sql
WITH neighbors AS (
    SELECT series_id,
           sample_id,
           sample_time,
           value,
           LAST_VALUE(value) IGNORE NULLS OVER (
               PARTITION BY series_id
               ORDER BY sample_time, sample_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS prev_value,
           LAST_VALUE(
               CASE WHEN value IS NOT NULL THEN sample_time END
           ) IGNORE NULLS OVER (
               PARTITION BY series_id
               ORDER BY sample_time, sample_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS prev_time,
           FIRST_VALUE(value) IGNORE NULLS OVER (
               PARTITION BY series_id
               ORDER BY sample_time, sample_id
               ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
           ) AS next_value,
           FIRST_VALUE(
               CASE WHEN value IS NOT NULL THEN sample_time END
           ) IGNORE NULLS OVER (
               PARTITION BY series_id
               ORDER BY sample_time, sample_id
               ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
           ) AS next_time
    FROM lab_series
)
SELECT series_id,
       sample_id,
       sample_time,
       value,
       CASE
         WHEN value IS NOT NULL THEN value
         WHEN prev_value IS NOT NULL
          AND next_value IS NOT NULL
          AND next_time > prev_time
         THEN prev_value
              + (next_value - prev_value)
                * ((sample_time - prev_time)
                   / NULLIF(next_time - prev_time, 0))
         ELSE NULL
       END AS interpolated_value
FROM neighbors
ORDER BY series_id, sample_time, sample_id;
~~~

Trong ví dụ này SAMPLE_TIME là kiểu DATE; phép trừ hai DATE trả số ngày. Công thức tính tỷ lệ khoảng thời gian đã đi qua giữa hai điểm đo hợp lệ. Với TIMESTAMP, phép trừ trả interval và cần chuyển đổi interval sang đơn vị số phù hợp trước khi áp dụng công thức.

Nội suy tuyến tính chỉ hợp lý nếu đại lượng có thể được giả định biến đổi gần tuyến tính trong khoảng trống. Nó không phù hợp tự động cho trạng thái rời rạc, sự kiện, số dư chịu giao dịch, hoặc chuỗi có bước nhảy. Với các trường hợp đó, forward fill, backfill, giá trị mặc định hoặc để NULL có thể đúng hơn.

## 13. Lấp có giới hạn thời gian hiệu lực

Một giá trị cũ không nên được mang sang vô hạn. Ví dụ cảm biến báo 24.5 lúc 09:00, sau đó mất kết nối cả ngày; điền 24.5 cho 23:00 có thể tạo dữ liệu sai.

Có thể mang theo timestamp của giá trị gần nhất:

~~~sql
WITH carried AS (
    SELECT sensor_id,
           reading_id,
           reading_time,
           measure,
           LAST_VALUE(measure) IGNORE NULLS OVER (
               PARTITION BY sensor_id
               ORDER BY reading_time, reading_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS previous_measure,
           LAST_VALUE(
               CASE WHEN measure IS NOT NULL THEN reading_time END
           ) IGNORE NULLS OVER (
               PARTITION BY sensor_id
               ORDER BY reading_time, reading_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS previous_measure_time
    FROM lab_sensor_readings
)
SELECT sensor_id,
       reading_id,
       reading_time,
       measure,
       CASE
         WHEN measure IS NOT NULL THEN measure
         WHEN reading_time - previous_measure_time <= 1/24
         THEN previous_measure
         ELSE NULL
       END AS measure_filled_max_1_hour
FROM carried;
~~~

Ở đây chỉ forward fill nếu lần đo hợp lệ gần nhất cách thời điểm hiện tại không quá một giờ. 1/24 ngày tương đương một giờ đối với Oracle DATE arithmetic. Nếu cột dùng TIMESTAMP, hãy tính chênh lệch interval theo đơn vị thích hợp.

Điều kiện thời hạn giúp tránh mang trạng thái cũ quá xa. Giá trị giới hạn phải xuất phát từ nghiệp vụ hoặc đặc tính thiết bị, không chọn tùy tiện.

## 14. Lưu kết quả lấp vào bảng

Các truy vấn analytic ở trên chỉ trả kết quả đã lấp. Nếu muốn lưu, nên bắt đầu bằng SELECT/CTE để xem trước hàng nào sẽ thay đổi. Sau khi xác nhận quy tắc, có thể dùng MERGE hoặc UPDATE theo khóa duy nhất.

Ví dụ bảng đích có READING_ID là primary key và chỉ cập nhật các hàng đang NULL:

~~~sql
MERGE INTO lab_sensor_readings target
USING (
    SELECT reading_id,
           LAST_VALUE(measure) IGNORE NULLS OVER (
               PARTITION BY sensor_id
               ORDER BY reading_time, reading_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS filled_measure
    FROM lab_sensor_readings
) source
ON (target.reading_id = source.reading_id)
WHEN MATCHED THEN
    UPDATE SET target.measure = source.filled_measure
    WHERE target.measure IS NULL
      AND source.filled_measure IS NOT NULL;
~~~

Đây là ví dụ forward fill và sẽ ghi giá trị quá khứ vào các hàng NULL đủ điều kiện. Trước khi chạy trên dữ liệu thật:

1. Chạy SELECT cùng CTE để xem số hàng và giá trị dự kiến.
2. Xác nhận khóa JOIN là duy nhất, tránh một target match nhiều source rows.
3. Xác định có cần giới hạn tuổi của giá trị được mang sang không.
4. Lưu lại nguồn gốc/nhật ký nếu cần truy vết dữ liệu được suy diễn.
5. Chạy trong transaction và quy trình triển khai có kiểm soát; xác nhận số hàng cập nhật trước khi commit.

Không ghi đè các giá trị đo thật đã có. Điều kiện TARGET.MEASURE IS NULL bảo vệ những hàng hiện có giá trị, nhưng vẫn cần kiểm tra concurrency và chính sách ghi dữ liệu của ứng dụng.

## 15. Hiệu năng và execution plan

IGNORE NULLS không tự làm truy vấn nhanh hơn. Chi phí chủ yếu phụ thuộc số hàng, số partition, thứ tự cần sắp xếp, frame và lượng dữ liệu phải giữ trong workarea.

Các yếu tố cần chú ý:

- **Số hàng đầu vào:** analytic chạy trên tập hàng sau WHERE/GROUP BY/HAVING của query block.
- **Kích thước partition:** một partition rất lớn có thể cần nhiều bộ nhớ và công việc sắp xếp.
- **ORDER BY:** Oracle có thể cần tổ chức hàng theo partition key và sort key.
- **Frame:** frame toàn partition hoặc cần nhìn về phía sau có thể cần giữ/truy cập thêm hàng.
- **Nhiều analytic khác thứ tự:** các hàm có partition/order giống nhau có thể dùng chung thứ tự; specification khác nhau có thể cần thêm sort.
- **PGA và TEMP:** workarea không đủ có thể spill xuống temporary tablespace.

### Quan sát actual plan

~~~sql
SELECT /*+ gather_plan_statistics */
       sensor_id,
       reading_time,
       measure,
       LAST_VALUE(measure) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS filled_measure
FROM lab_sensor_readings;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

Quan sát operation liên quan window/sort, số hàng thực tế, buffer gets, physical reads và thông tin TEMP/workarea nếu có. ALLSTATS LAST cần thống kê thực thi được thu thập, ví dụ hint GATHER_PLAN_STATISTICS hoặc cấu hình phù hợp. Quyền xem cursor/plan phụ thuộc user và cấu hình database.

EXPLAIN PLAN chỉ cung cấp plan ước lượng; nó không thực thi câu truy vấn để đo thời gian, số hàng thực tế hoặc TEMP đã dùng.

### Index có thể hỗ trợ nhưng không bảo đảm bỏ sort

Index trên các cột partition/order có thể hữu ích trong một số truy vấn. Với chuỗi cảm biến, index như:

~~~sql
CREATE INDEX ix_lab_sensor_time
ON lab_sensor_readings (sensor_id, reading_time, reading_id);
~~~

có thể hỗ trợ truy cập theo sensor và thứ tự thời gian. Tuy nhiên, optimizer vẫn cân nhắc full scan, clustering factor, số hàng, số cột cần lấy và cost của việc đọc index. Không tạo index chỉ dựa vào cú pháp analytic; hãy đo actual plan trên dữ liệu đại diện.

## 16. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| LAG trả NULL dù phía trước có giá trị hợp lệ xa hơn | Dùng RESPECT NULLS hoặc mặc định | Dùng IGNORE NULLS nếu muốn bỏ qua NULL. |
| LAG IGNORE NULLS lấy giá trị xa hơn một hàng | Offset đếm giá trị khác NULL | Đây là hành vi đúng; kiểm tra mục tiêu là offset hàng hay offset giá trị hợp lệ. |
| Default của LAG không thay NULL ở hàng trước | Hàng ở offset tồn tại nhưng expression của nó NULL | Dùng IGNORE NULLS hoặc NVL nếu chính sách muốn thay mọi kết quả NULL. |
| Forward fill không lấp NULL đầu chuỗi | Không có giá trị khác NULL ở phía trước | Chấp nhận NULL, hoặc thêm backfill nếu nghiệp vụ cho phép. |
| Backfill không lấp NULL cuối chuỗi | Không có giá trị khác NULL phía sau | Chấp nhận NULL hoặc dùng forward fill. |
| LAST_VALUE chỉ trả giá trị hiện tại | Frame kết thúc ở CURRENT ROW hoặc frame mặc định | Xác định rõ frame; forward fill cần UNBOUNDED PRECEDING đến CURRENT ROW. |
| Dữ liệu giữa chuỗi được điền sai thứ tự | ORDER BY không có tie-breaker | Thêm khóa duy nhất và quy tắc xử lý timestamp trùng. |
| Giá trị sensor này lan sang sensor khác | Thiếu PARTITION BY đầy đủ | Partition theo toàn bộ khóa định danh chuỗi. |
| Thời điểm không có hàng vẫn biến mất | IGNORE NULLS không tạo hàng mới | Sinh calendar/time spine rồi LEFT JOIN nguồn trước khi lấp. |
| Giá trị cũ bị kéo dài quá lâu | Forward fill không có giới hạn hiệu lực | Mang theo timestamp của giá trị nguồn và áp dụng max-age. |
| Kết quả được tính nhưng bảng không đổi | Analytic SELECT không sửa dữ liệu | Dùng DML riêng sau khi preview và xác nhận chính sách. |
| TEMP tăng khi chạy chuỗi lớn | Sort/window workarea không đủ memory | Kiểm tra actual plan, số hàng, partition, PGA/TEMP và workload đồng thời. |

## 17. Bài thực hành tổng hợp

Thực hiện trong schema học tập có quyền CREATE TABLE và quota phù hợp. DDL có implicit commit trong Oracle; không chạy trên bảng nghiệp vụ thật.

### Bước 1: tạo chuỗi đo

~~~sql
CREATE TABLE lab_sensor_readings (
    reading_id   NUMBER(8) PRIMARY KEY,
    sensor_id    NUMBER(8) NOT NULL,
    reading_time DATE NOT NULL,
    measure      NUMBER(10,2)
);

INSERT INTO lab_sensor_readings VALUES
    (1, 7, TO_DATE('2026-01-01 09:00', 'YYYY-MM-DD HH24:MI'), 24.5);
INSERT INTO lab_sensor_readings VALUES
    (2, 7, TO_DATE('2026-01-01 10:00', 'YYYY-MM-DD HH24:MI'), NULL);
INSERT INTO lab_sensor_readings VALUES
    (3, 7, TO_DATE('2026-01-01 11:00', 'YYYY-MM-DD HH24:MI'), NULL);
INSERT INTO lab_sensor_readings VALUES
    (4, 7, TO_DATE('2026-01-01 12:00', 'YYYY-MM-DD HH24:MI'), 25.2);
INSERT INTO lab_sensor_readings VALUES
    (5, 7, TO_DATE('2026-01-01 13:00', 'YYYY-MM-DD HH24:MI'), NULL);
INSERT INTO lab_sensor_readings VALUES
    (6, 8, TO_DATE('2026-01-01 09:00', 'YYYY-MM-DD HH24:MI'), NULL);
INSERT INTO lab_sensor_readings VALUES
    (7, 8, TO_DATE('2026-01-01 10:00', 'YYYY-MM-DD HH24:MI'), 18.0);
INSERT INTO lab_sensor_readings VALUES
    (8, 8, TO_DATE('2026-01-01 11:00', 'YYYY-MM-DD HH24:MI'), NULL);
COMMIT;
~~~

### Bước 2: so sánh RESPECT và IGNORE

~~~sql
SELECT sensor_id,
       reading_id,
       measure,
       LAG(measure) RESPECT NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
       ) AS lag_respect,
       LAG(measure) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
       ) AS lag_ignore
FROM lab_sensor_readings
ORDER BY sensor_id, reading_time, reading_id;
~~~

Tập trung vào sensor 7 tại hàng 3 và hàng 5. Giải thích vì sao hai cột LAG khác nhau.

### Bước 3: forward fill

~~~sql
SELECT sensor_id,
       reading_time,
       measure,
       LAST_VALUE(measure) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS forward_filled
FROM lab_sensor_readings
ORDER BY sensor_id, reading_time, reading_id;
~~~

Quan sát sensor 8: hàng đầu tiên vẫn NULL vì chưa có giá trị trước đó.

### Bước 4: backfill

~~~sql
SELECT sensor_id,
       reading_time,
       measure,
       FIRST_VALUE(measure) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
           ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
       ) AS backfilled
FROM lab_sensor_readings
ORDER BY sensor_id, reading_time, reading_id;
~~~

Quan sát sensor 7 tại 10:00 và 11:00; giá trị phía sau đầu tiên là 25.2. Hàng cuối 13:00 vẫn NULL vì không còn giá trị tương lai.

### Bước 5: kết hợp forward fill và backfill

~~~sql
WITH candidates AS (
    SELECT sensor_id,
           reading_id,
           reading_time,
           measure,
           LAST_VALUE(measure) IGNORE NULLS OVER (
               PARTITION BY sensor_id
               ORDER BY reading_time, reading_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
           ) AS prev_value,
           FIRST_VALUE(measure) IGNORE NULLS OVER (
               PARTITION BY sensor_id
               ORDER BY reading_time, reading_id
               ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
           ) AS next_value
    FROM lab_sensor_readings
)
SELECT sensor_id,
       reading_id,
       reading_time,
       measure,
       COALESCE(prev_value, next_value) AS filled_value
FROM candidates
ORDER BY sensor_id, reading_time, reading_id;
~~~

Giải thích chính sách ưu tiên giá trị trước và cách xử lý partition toàn NULL.

### Bước 6: quan sát default của LAG

~~~sql
SELECT reading_id,
       measure,
       LAG(measure, 1, -1) RESPECT NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
       ) AS lag_respect_default,
       LAG(measure, 1, -1) IGNORE NULLS OVER (
           PARTITION BY sensor_id
           ORDER BY reading_time, reading_id
       ) AS lag_ignore_default
FROM lab_sensor_readings
ORDER BY sensor_id, reading_time, reading_id;
~~~

Phân biệt trường hợp không có hàng trước với trường hợp hàng trước tồn tại nhưng có MEASURE NULL.

### Bước 7: dọn dữ liệu

~~~sql
DROP TABLE lab_sensor_readings PURGE;
~~~

Chỉ chạy khi đã hoàn thành bài và không cần giữ dữ liệu. PURGE bỏ qua Recycle Bin; DROP TABLE là DDL và không thể rollback như DML chưa commit.

## 18. Câu hỏi tự kiểm tra

1. **RESPECT NULLS có ý nghĩa gì?** Giữ NULL khi xác định vị trí; nếu hàng được chọn có expression NULL, kết quả có thể NULL.
2. **IGNORE NULLS có ý nghĩa gì?** Bỏ qua hàng có expression NULL khi tìm giá trị theo offset/vị trí trong phạm vi hàm.
3. **Tùy chọn mặc định là gì?** RESPECT NULLS đối với các hàm hỗ trợ NULL treatment.
4. **LAG IGNORE NULLS khác LAG RESPECT NULLS thế nào?** Một bên tìm giá trị khác NULL trước đó; bên kia lấy đúng hàng trước, kể cả giá trị NULL.
5. **Default của LAG được dùng khi nào?** Khi không có hàng ở offset tương ứng theo cách tìm đã chọn, không phải cứ giá trị expression là NULL.
6. **Hàm nào thường dùng để forward fill?** LAST_VALUE(expr) IGNORE NULLS với frame từ UNBOUNDED PRECEDING tới CURRENT ROW.
7. **Hàm nào thường dùng để backfill?** FIRST_VALUE(expr) IGNORE NULLS với frame từ CURRENT ROW tới UNBOUNDED FOLLOWING.
8. **Vì sao phải PARTITION BY sensor_id?** Để không mang giá trị của sensor khác sang chuỗi hiện tại.
9. **Vì sao cần tie-breaker trong ORDER BY?** Để xác định thứ tự giữa các hàng có cùng timestamp.
10. **ROWS khác RANGE thế nào?** ROWS theo vị trí hàng; RANGE theo giá trị sort và bao gồm peers.
11. **IGNORE NULLS có tạo hàng cho timestamp không tồn tại không?** Không; cần time spine/calendar và LEFT JOIN trước.
12. **Forward fill có tương đương nội suy tuyến tính không?** Không; forward fill giữ giá trị trước, nội suy tính giá trị trung gian từ hai điểm.
13. **Làm sao giới hạn tuổi của giá trị được mang sang?** Mang theo timestamp của giá trị khác NULL gần nhất và so sánh khoảng cách với ngưỡng nghiệp vụ.
14. **IGNORE NULLS có UPDATE bảng không?** Không; nó chỉ tính giá trị trong SELECT. Cần DML riêng nếu muốn lưu.
15. **Khi nào không nên forward fill?** Khi giá trị cũ không còn đại diện cho trạng thái hiện tại hoặc việc lấp làm sai ý nghĩa đo lường.

Khi dùng RESPECT NULLS và IGNORE NULLS, hãy xác định trước NULL là một trạng thái cần giữ hay một khoảng trống cần bỏ qua khi tìm giá trị. Với lấp dữ liệu theo chuỗi, phải chọn đúng partition, thứ tự ổn định và frame tường minh. Forward fill, backfill và nội suy là ba chính sách khác nhau; chúng có thể cho kết quả khác nhau dù dùng cùng dữ liệu. Chỉ lấp khi quy tắc nghiệp vụ cho phép, và lưu dấu nguồn gốc nếu giá trị suy diễn được dùng cho báo cáo hoặc quyết định quan trọng.
