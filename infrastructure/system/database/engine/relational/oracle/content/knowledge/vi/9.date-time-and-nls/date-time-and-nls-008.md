# Lọc theo khoảng thời gian nửa mở và tránh mất dữ liệu trong ngày

Khi người dùng yêu cầu “hiển thị **tất cả giao dịch ngày 14/11/2026**”, câu SQL có vẻ đơn giản nhưng rất dễ bỏ sót dữ liệu. Trong Oracle Database, cột ngày giờ thường chứa cả giờ, phút, giây, phần giây lẻ, thậm chí thông tin múi giờ. Người dùng nghĩ về **một ngày lịch**, còn database so sánh **những giá trị thời gian cụ thể**. Nhầm lẫn hai khái niệm này khiến báo cáo thiếu bản ghi cuối ngày, đếm trùng đầu ngày hôm sau hoặc lệch ngày theo múi giờ.

Giải pháp bền vững là dùng **khoảng nửa mở** (*half-open interval*): bao gồm mốc bắt đầu và loại trừ mốc kết thúc.

~~~sql
WHERE created_at >= :start_inclusive
  AND created_at <  :end_exclusive
~~~

Đối với ngày 14/11/2026, đặt mốc đầu là **14/11/2026 lúc 00:00** và mốc cuối là **15/11/2026 lúc 00:00**, theo đúng múi giờ nghiệp vụ. Bài học giải thích lý do, những cách viết dễ sai, cách tính ranh giới cho DATE/TIMESTAMP, các kiểu có múi giờ, NLS, DST, index/partition pruning và những bài thực hành có thể tự chạy trên Oracle.

## 1. Oracle DATE không chỉ là ngày lịch

Trong nhiều ngôn ngữ lập trình, kiểu `LocalDate` biểu diễn ngày mà không có giờ. Nhưng **Oracle `DATE` lưu cả năm, tháng, ngày, giờ, phút và giây**. Giá trị:

~~~text
2026-11-14 09:15:30
~~~

vẫn là một giá trị Oracle DATE hợp lệ. Nếu SQL Developer, SQL*Plus hoặc ứng dụng chỉ in `14-NOV-26`, điều đó thường phản ánh **định dạng hiển thị**, không có nghĩa giờ đã bị loại bỏ.

Ví dụ:

~~~sql
SELECT TO_CHAR(
         TO_DATE('2026-11-14 09:15:30',
                 'YYYY-MM-DD HH24:MI:SS'),
         'YYYY-MM-DD HH24:MI:SS'
       ) AS full_datetime
FROM dual;
~~~

Kết quả biểu diễn đầy đủ là `2026-11-14 09:15:30`.

Giả sử bảng `ORDERS` có cột `CREATED_AT DATE`:

| Mã đơn | CREATED_AT | Thuộc ngày 14/11? |
|---|---|---|
| A | 2026-11-13 23:59:59 | Không |
| B | 2026-11-14 00:00:00 | Có |
| C | 2026-11-14 09:15:30 | Có |
| D | 2026-11-14 23:59:59 | Có |
| E | 2026-11-15 00:00:00 | Không |

Truy vấn sau **không** lấy đủ ngày:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at = DATE '2026-11-14';
~~~

Lý do: literal `DATE '2026-11-14'` có phần thời gian **00:00:00**. Phép bằng chỉ khớp đúng thời điểm đầu ngày, tức hàng B trong ví dụ, không khớp hàng C và D.

Truy vấn đúng:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';
~~~

Câu này lấy B, C và D, loại A và E. Nó không cần làm tròn từng giá trị DATE hoặc đoán “thời điểm cuối ngày”.

## 2. Khoảng nửa mở: bao gồm đầu, loại trừ cuối

Ký hiệu toán học của khoảng nửa mở là:

\[
[s,e)=\{t\mid s\le t<e\}
\]

Trong đó `s` là mốc đầu được tính vào khoảng, còn `e` là mốc cuối **không được tính vào**.

~~~text
13/11 23:59:59    14/11 00:00:00                  15/11 00:00:00
       |                 [===============================)
    loại trừ           bao gồm                      loại trừ
                     toàn bộ ngày 14/11
~~~

Trong SQL, dùng hai phép so sánh:

~~~sql
WHERE datetime_column >= :start_value
  AND datetime_column <  :next_start_value
~~~

### 2.1 Tránh bỏ sót phần giây cuối ngày

Oracle `TIMESTAMP(6)` có thể chứa các giá trị:

~~~text
2026-11-14 23:59:59.000001
2026-11-14 23:59:59.123456
2026-11-14 23:59:59.999999
~~~

Tất cả đều thuộc ngày 14/11. Mốc cuối `2026-11-14 23:59:59` **không bao phủ** các phần giây lẻ đó. Ngược lại, mốc `< 2026-11-15 00:00:00` lấy được tất cả mà không phải biết precision của cột là 3, 6 hay 9.

### 2.2 Không đếm trùng tại ranh giới

Hai kỳ liền nhau:

~~~text
Ngày 14: [14/11 00:00, 15/11 00:00)
Ngày 15: [15/11 00:00, 16/11 00:00)
~~~

Một bản ghi đúng `15/11 00:00:00` **chỉ** thuộc ngày 15. Hai khoảng không chồng nhau và ghép lại không tạo khoảng trống.

Tính chất tổng quát:

\[
[a,b)\cup[b,c)=[a,c)
\]

Điều này quan trọng cho các báo cáo ngày, kỳ kế toán, chia lô ETL, giới hạn truy vấn theo partition và các API đọc dữ liệu theo cửa sổ thời gian.

### 2.3 Không phải đoán thời điểm cuối cùng

Không có một chuỗi kết thúc kiểu `23:59:59.999` phù hợp với mọi cột:

- `DATE` có precision đến giây.
- `TIMESTAMP(3)` có phần mili giây.
- `TIMESTAMP(6)` có phần micro giây.
- `TIMESTAMP(9)` có thể biểu diễn phần nano giây.

Khoảng nửa mở ổn định ngay cả khi schema tăng độ chính xác từ TIMESTAMP(3) lên TIMESTAMP(6).

## 3. Những cách viết sai hoặc dễ lỗi

### 3.1 Phép bằng với ngày

~~~sql
-- Sai nếu muốn lấy mọi thời điểm trong ngày.
WHERE created_at = DATE '2026-11-14'
~~~

Với DATE, câu này chỉ lấy đúng 00:00:00. Với TIMESTAMP, nó cũng không có ý nghĩa “tất cả những hàng cùng ngày”.

### 3.2 BETWEEN với mốc cuối 23:59:59

~~~sql
-- Dễ bỏ các bản ghi có phần giây lẻ trong giây cuối.
WHERE occurred_at BETWEEN
      TIMESTAMP '2026-11-14 00:00:00'
  AND TIMESTAMP '2026-11-14 23:59:59'
~~~

`BETWEEN a AND b` bao gồm **cả hai đầu**. Mốc trên tương đương đúng `23:59:59.000000`, không phải tất cả giá trị đến trước 00:00 của ngày tiếp theo.

Với DATE chỉ chính xác đến giây, mốc 23:59:59 có thể đủ theo tình huống hiện tại. Tuy nhiên nếu sau này đổi cột sang TIMESTAMP, logic không còn đúng. Mẫu nửa mở không phụ thuộc precision nên thường đáng dùng ngay từ đầu.

### 3.3 BETWEEN với mốc đầu ngày hôm sau

~~~sql
-- Có thể lấy thừa bản ghi đúng 00:00 ngày 15.
WHERE occurred_at BETWEEN
      DATE '2026-11-14'
  AND DATE '2026-11-15'
~~~

Bản ghi đúng `15/11 00:00:00` bị tính vào ngày 14 vì BETWEEN bao gồm mốc cuối. Nếu truy vấn ngày 15 cũng lấy bản ghi đó thì tổng nhiều ngày bị **double count**.

### 3.4 Đặt “tick cuối” bằng tay

~~~sql
-- Gắn logic vào giả định về precision.
WHERE occurred_at <=
      TIMESTAMP '2026-11-14 23:59:59.999999'
~~~

Câu này không bao phủ một cách tổng quát mọi TIMESTAMP có precision cao hơn. Ngoài ra, đổi sang kiểu có timezone lại xuất hiện thêm vấn đề ranh giới ngày địa phương. Hãy dùng mốc đầu ngày kế tiếp với dấu `<`.

### 3.5 Lọc bằng chuỗi phụ thuộc NLS

~~~sql
-- Không nên, vì chuỗi không có kiểu DATE rõ ràng.
WHERE created_at >= '14/11/2026'
  AND created_at <  '15/11/2026'
~~~

Oracle có thể áp dụng chuyển kiểu ngầm theo `NLS_DATE_FORMAT` của session. Kết quả có thể khác giữa hai môi trường hoặc xảy ra lỗi parse.

### 3.6 Áp dụng TRUNC hay TO_CHAR trực tiếp lên cột

~~~sql
WHERE TRUNC(created_at) = DATE '2026-11-14'
~~~

Đây có thể là phép lọc đúng về **ngày lịch** cho DATE/TIMESTAMP không zone trong ngữ cảnh phù hợp. Tuy nhiên, khi có B-tree index trên chính `CREATED_AT`, việc gọi hàm trên cột có thể làm đường truy cập kém thuận lợi hơn so với hai ranh giới trực tiếp. Dùng function-based index có thể thay đổi điều đó, nhưng là quyết định tối ưu riêng.

Một cách khác thường kém phù hợp:

~~~sql
WHERE TO_CHAR(created_at, 'YYYY-MM-DD') = '2026-11-14'
~~~

Lọc bằng chuỗi buộc phải chú ý đến chuyển đổi và có thể hạn chế index cột gốc. Nếu mục tiêu chỉ là xem hoặc nhóm ngày, `TO_CHAR` vẫn hữu ích; nhưng với predicate chính, thường nên so sánh **cùng kiểu temporal**.

## 4. Cách lọc đúng với DATE

Một ngày cụ thể:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';
~~~

Literal `DATE 'YYYY-MM-DD'` là cách viết độc lập với định dạng ngày mặc định của session.

### 4.1 Ngày được gửi dưới dạng bind parameter

Trong ứng dụng, hai tham số được tính trước:

~~~text
:day_start      = DATE 2026-11-14 00:00:00
:next_day_start = DATE 2026-11-15 00:00:00
~~~

SQL:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= :day_start
  AND created_at <  :next_day_start;
~~~

Các tham số cần được **bind đúng kiểu DATE**, không truyền dưới dạng chuỗi rồi hy vọng Oracle tự chuyển.

### 4.2 Nếu input có cả giờ nhưng chỉ quan tâm ngày

Giả sử `:p_datetime` là DATE có giờ 15:20:00 của ngày cần tìm. Có thể đặt hàm ở **phía tham số**:

~~~sql
WHERE created_at >= TRUNC(:p_datetime)
  AND created_at <  TRUNC(:p_datetime) + 1
~~~

Với DATE, `TRUNC(:p_datetime)` trả về đầu ngày và `+1` cho ngày kế tiếp. Hàm không được áp lên mọi hàng của cột `CREATED_AT`, nên thường thuận lợi hơn cho index thường. Chỉ dùng khi date parameter đúng kiểu và đúng múi giờ/quy ước nghiệp vụ.

## 5. Cách lọc đúng với TIMESTAMP

`TIMESTAMP(p)` có phần giây nhưng **không chứa time zone**. Ví dụ:

~~~sql
CREATE TABLE telemetry_event (
    event_id    NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    occurred_at TIMESTAMP(6) NOT NULL
);
~~~

Lọc toàn bộ ngày 14/11:

~~~sql
SELECT event_id, occurred_at
FROM telemetry_event
WHERE occurred_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND occurred_at <  TIMESTAMP '2026-11-15 00:00:00';
~~~

Các giá trị `2026-11-14 00:00:00.000000`, `2026-11-14 13:00:00.123456` và `2026-11-14 23:59:59.999999` đều khớp. Giá trị đúng nửa đêm 15/11 không khớp.

Nếu input đến dưới dạng chuỗi rõ format:

~~~sql
WHERE occurred_at >= TO_TIMESTAMP(
        '2026-11-14 00:00:00',
        'YYYY-MM-DD HH24:MI:SS'
      )
  AND occurred_at < TO_TIMESTAMP(
        '2026-11-15 00:00:00',
        'YYYY-MM-DD HH24:MI:SS'
      )
~~~

Trong ứng dụng thật, nên bind temporal parameter đúng loại. Ví dụ chuỗi cố định ở trên chỉ dùng để minh họa cách parsing.

**Điểm quan trọng:** TIMESTAMP không tự biết giá trị là UTC, giờ Việt Nam hay giờ chi nhánh. Nếu cột được **quy ước lưu UTC**, SQL trên lọc **ngày UTC**. Muốn lọc ngày địa phương, phải đổi ranh giới của ngày địa phương sang UTC trước.

## 6. Tính ranh giới tuần, tháng, quý, năm

Khoảng nửa mở không giới hạn ở một ngày. Với bất kỳ kỳ thời gian nào, hãy chọn **đầu kỳ** và **đầu kỳ kế tiếp**.

### 6.1 Tuần

Giả sử tuần nghiệp vụ từ 09/11/2026 đến trước 16/11/2026:

~~~sql
WHERE created_at >= DATE '2026-11-09'
  AND created_at <  DATE '2026-11-16'
~~~

Tùy nghiệp vụ, tuần có thể bắt đầu thứ Hai, Chủ nhật hoặc một mốc khác. `TRUNC(date,'IW')` thể hiện tuần ISO; các format ngày/tuần khác có thể phụ thuộc NLS. Hãy xác định quy ước báo cáo trước khi tính ranh giới.

### 6.2 Tháng

Lọc toàn tháng 11/2026:

~~~sql
WHERE created_at >= DATE '2026-11-01'
  AND created_at <  DATE '2026-12-01'
~~~

Nếu tham số `:p_day` là DATE và cần tháng chứa nó:

~~~sql
WHERE created_at >= TRUNC(:p_day, 'MM')
  AND created_at <  ADD_MONTHS(TRUNC(:p_day, 'MM'), 1)
~~~

Không dùng `+30` hoặc `+31` để xác định tháng tiếp theo: số ngày các tháng khác nhau.

### 6.3 Quý

Ví dụ quý IV/2026:

~~~sql
WHERE created_at >= DATE '2026-10-01'
  AND created_at <  DATE '2027-01-01'
~~~

Với một DATE bất kỳ thuộc quý:

~~~sql
WHERE created_at >= TRUNC(:p_day, 'Q')
  AND created_at <  ADD_MONTHS(TRUNC(:p_day, 'Q'), 3)
~~~

### 6.4 Năm và năm nhuận

Toàn năm 2024:

~~~sql
WHERE created_at >= DATE '2024-01-01'
  AND created_at <  DATE '2025-01-01'
~~~

Không cần tự tính năm có 365 hay 366 ngày, vì hai mốc **đầu năm** đã được chỉ rõ. Ngày 29/02/2024 nằm tự nhiên trong khoảng.

Với tham số:

~~~sql
WHERE created_at >= TRUNC(:p_year_date, 'YYYY')
  AND created_at <  ADD_MONTHS(TRUNC(:p_year_date, 'YYYY'), 12)
~~~

### 6.5 Cửa sổ giờ tùy ý

Một ca bắt đầu 09:00 và kết thúc trước 12:30:

~~~sql
WHERE created_at >= TO_DATE(
        '2026-11-14 09:00:00',
        'YYYY-MM-DD HH24:MI:SS'
      )
  AND created_at < TO_DATE(
        '2026-11-14 12:30:00',
        'YYYY-MM-DD HH24:MI:SS'
      )
~~~

Đối với hai ca liên tiếp, dùng 12:30 làm **mốc cuối loại trừ** của ca đầu và **mốc đầu bao gồm** của ca sau để không tính trùng.

## 7. NLS: format ngày không phải giá trị ngày

Những tham số Oracle thường gặp:

| Tham số | Vai trò |
|---|---|
| `NLS_DATE_FORMAT` | Format mặc định khi chuyển/hiển thị DATE trong nhiều ngữ cảnh |
| `NLS_TIMESTAMP_FORMAT` | Format mặc định cho TIMESTAMP |
| `NLS_TIMESTAMP_TZ_FORMAT` | Format mặc định cho timestamp có time zone |
| `NLS_DATE_LANGUAGE` | Ngôn ngữ tên ngày/tháng trong các format liên quan |
| `NLS_TERRITORY` | Các quy ước vùng và format mặc định trong một số trường hợp |

Một cột DATE có thể hiển thị là `14-NOV-26` ở session này và `2026-11-14 09:15:30` ở session khác. Đó có thể chỉ là khác format **của cùng giá trị**.

### 7.1 Tránh implicit conversion

Không nên:

~~~sql
WHERE created_at >= '14/11/2026'
~~~

Nên dùng:

~~~sql
WHERE created_at >= DATE '2026-11-14'
~~~

hoặc:

~~~sql
WHERE created_at >= TO_DATE('2026-11-14', 'YYYY-MM-DD')
~~~

### 7.2 Format model khi có giờ

~~~sql
SELECT TO_DATE(
         '2026-11-14 23:59:59',
         'YYYY-MM-DD HH24:MI:SS'
       ) AS parsed_date
FROM dual;
~~~

Các ký hiệu dễ nhầm:

- `YYYY`: năm; `MM`: **tháng**; `DD`: ngày.
- `HH24`: giờ 24 giờ; `MI`: **phút**; `SS`: giây.
- `FFn`: phần giây cho TIMESTAMP, ví dụ `FF6`.
- `TZH:TZM`: offset giờ/phút của kiểu có timezone.
- `TZR`: time zone region.

Không nhầm `MM` (tháng) với `MI` (phút).

### 7.3 Không dùng TO_CHAR để khắc phục dữ liệu ngày sai

`TO_CHAR` tạo **chuỗi để hiển thị**; nó không làm DATE/TIMESTAMP trong table mất hoặc thêm zone. Dùng `TO_CHAR` để debug giờ đầy đủ:

~~~sql
SELECT order_id,
       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS full_time
FROM orders
WHERE order_id = :p_order_id;
~~~

Nhưng để lọc theo khoảng, nên giữ cột ở dạng datetime gốc và truyền hai ranh giới cùng semantics.

## 8. Ngày UTC và ngày địa phương là hai bài toán khác nhau

Giả sử sự kiện có thời điểm tuyệt đối:

~~~text
2026-11-14 20:00:00 UTC
 = 2026-11-15 03:00:00 +07:00 (Việt Nam)
~~~

Sự kiện thuộc **ngày 14 theo UTC** nhưng thuộc **ngày 15 theo Việt Nam**. Cả hai cách nhóm có thể đúng, tùy báo cáo đang hỏi ngày nào.

### 8.1 Hai ranh giới ngày Việt Nam

Ngày 14/11/2026 theo `Asia/Ho_Chi_Minh` được mô tả bằng:

~~~text
Từ: 2026-11-14 00:00:00 +07:00
Đến trước: 2026-11-15 00:00:00 +07:00
~~~

Tương đương UTC:

~~~text
Từ: 2026-11-13 17:00:00 UTC
Đến trước: 2026-11-14 17:00:00 UTC
~~~

Nếu `OCCURRED_AT_UTC` là TIMESTAMP **quy ước lưu giá trị UTC, không có zone trong kiểu**, lọc ngày Việt Nam như sau:

~~~sql
WHERE occurred_at_utc >= TIMESTAMP '2026-11-13 17:00:00'
  AND occurred_at_utc <  TIMESTAMP '2026-11-14 17:00:00'
~~~

Không dùng hai nửa đêm UTC của ngày 14 nếu người dùng hỏi ngày Việt Nam.

### 8.2 Offset khác region

`+07:00` là một **UTC offset**. `Asia/Ho_Chi_Minh` là một **time zone region** có quy tắc theo lịch sử. Một offset không xác định duy nhất region, cũng không mang quy tắc DST tương lai của những vùng áp dụng DST.

Trước khi lọc, phải xác định:

1. Ngày theo **UTC**, múi giờ của người dùng, chi nhánh, hay múi giờ chuẩn doanh nghiệp?
2. Cột lưu **instant** có zone thật, hay TIMESTAMP thuần đang được quy ước là UTC?
3. Ngày nghiệp vụ bắt đầu lúc 00:00 hay một thời điểm khác như 06:00?

Khoảng nửa mở chỉ chính xác khi **hai ranh giới đã được tính theo đúng định nghĩa kỳ**.

## 9. TIMESTAMP WITH TIME ZONE: dựng hai mốc theo region

Giả sử bảng:

~~~sql
CREATE TABLE global_events (
    event_id    NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    occurred_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    event_name  VARCHAR2(80) NOT NULL
);
~~~

Nếu muốn lọc tất cả các instants thuộc ngày 14/11/2026 tại Việt Nam:

~~~sql
SELECT event_id, occurred_at, event_name
FROM global_events
WHERE occurred_at >= FROM_TZ(
        TIMESTAMP '2026-11-14 00:00:00',
        'Asia/Ho_Chi_Minh'
      )
  AND occurred_at < FROM_TZ(
        TIMESTAMP '2026-11-15 00:00:00',
        'Asia/Ho_Chi_Minh'
      );
~~~

`FROM_TZ` nhận TIMESTAMP không có zone và **gắn thông tin region/offset để tạo TSTZ**. Hai mốc local midnight tương ứng với hai instants cụ thể, được Oracle so sánh với các giá trị TSTZ của cột.

### 9.1 Giữ cột gốc trong predicate

Có thể hiển thị các sự kiện theo giờ Việt Nam bằng:

~~~sql
SELECT event_id,
       TO_CHAR(
         occurred_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
         'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
       ) AS vietnam_time
FROM global_events;
~~~

Nhưng với **lọc dữ liệu**, thường thuận lợi hơn nếu tạo hai bound TSTZ ở phía tham số rồi so sánh trực tiếp `OCCURRED_AT`, thay vì chuyển zone và format thành chuỗi cho từng hàng.

### 9.2 Dùng offset rõ khi biết chính xác hai offset

~~~sql
WHERE occurred_at >= TO_TIMESTAMP_TZ(
        '2026-11-14 00:00:00 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
  AND occurred_at < TO_TIMESTAMP_TZ(
        '2026-11-15 00:00:00 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
~~~

Ở Việt Nam ví dụ này có ranh giới đúng. Với một region đổi DST, không tự suy rằng offset của **hai nửa đêm** giống nhau; dùng region để Oracle áp dụng quy tắc thích hợp.

### 9.3 TSTZ khác TIMESTAMP thuần

`TIMESTAMP` chỉ có thành phần ngày-giờ, không biết nó thuộc zone nào. `TIMESTAMP WITH TIME ZONE` mang thông tin cần để xác định instant theo offset/region. Hai biểu diễn `09:30 +07:00` và `02:30 +00:00` có thể chỉ cùng instant, trong khi hai giá trị TIMESTAMP thuần `09:30` và `02:30` thì khác nhau.

## 10. TIMESTAMP WITH LOCAL TIME ZONE và SESSIONTIMEZONE

`TIMESTAMP WITH LOCAL TIME ZONE` (TSLTZ) chuẩn hóa giá trị khi lưu và **hiển thị theo SESSIONTIMEZONE** khi đọc; nó không giữ zone gốc riêng cho từng hàng.

Kiểm tra:

~~~sql
SELECT DBTIMEZONE AS db_timezone,
       SESSIONTIMEZONE AS session_timezone
FROM dual;
~~~

Một event duy nhất có thể hiển thị 09:30 trong session UTC+7 và 02:30 trong session UTC. Nếu ứng dụng sử dụng connection pool có session timezone khác nhau, báo cáo nhóm theo ngày có thể khác nhau mà không có bản ghi nào thực sự bị thay đổi.

Đối với một cột TSLTZ và yêu cầu ngày Việt Nam, có thể biểu diễn hai mốc là TSTZ:

~~~sql
SELECT event_id, occurred_at
FROM local_events
WHERE occurred_at >= FROM_TZ(
        TIMESTAMP '2026-11-14 00:00:00',
        'Asia/Ho_Chi_Minh'
      )
  AND occurred_at < FROM_TZ(
        TIMESTAMP '2026-11-15 00:00:00',
        'Asia/Ho_Chi_Minh'
      );
~~~

Ở đây giả định `LOCAL_EVENTS.OCCURRED_AT` là TSLTZ và Oracle chuyển kiểu so sánh theo ngữ nghĩa có zone. Trong ứng dụng thật cần bảo đảm kiểu bind/driver và thông số session được kiểm soát. Không mặc định ngày của session trùng ngày của chi nhánh.

### 10.1 Vì sao TRUNC(TSLTZ) cần thận trọng?

Một biểu thức như:

~~~sql
WHERE TRUNC(occurred_at) = DATE '2026-11-14'
~~~

không cho biết rõ **ngày theo region nào**. TSLTZ có semantics hiển thị theo session nên kết quả dựa trên ngày đã được diễn giải có thể khác giữa hai session. Hãy xác định region nghiệp vụ và tính hai mốc theo region đó.

## 11. DST: một ngày có thể dài 23 hoặc 25 giờ

Một số region áp dụng **Daylight Saving Time (DST)**. Đồng hồ địa phương có thể nhảy tới một giờ sau hoặc lùi lại một giờ, khiến một ngày lịch không tương đương đúng 24 giờ tuyệt đối.

Ví dụ quy tắc thường áp dụng tại `America/New_York` trong năm 2026:

~~~text
Ngày 08/03/2026: chuyển sang DST
  đầu ngày 08/03: offset -05:00
  đầu ngày 09/03: offset -04:00
  khoảng tuyệt đối từ midnight đến midnight = 23 giờ

Ngày 01/11/2026: kết thúc DST
  đầu ngày 01/11: offset -04:00
  đầu ngày 02/11: offset -05:00
  khoảng tuyệt đối từ midnight đến midnight = 25 giờ
~~~

Vì vậy không nên viết:

~~~text
endInstant = startInstant + 24 hours
~~~

cho một **ngày lịch** tại region có DST.

### 11.1 Ngày chuyển sang DST: 23 giờ

~~~sql
WHERE occurred_at >= FROM_TZ(
        TIMESTAMP '2026-03-08 00:00:00',
        'America/New_York'
      )
  AND occurred_at < FROM_TZ(
        TIMESTAMP '2026-03-09 00:00:00',
        'America/New_York'
      )
~~~

Hai mốc tương ứng UTC `2026-03-08 05:00` và `2026-03-09 04:00` theo quy tắc timezone của ví dụ, cách nhau 23 giờ.

### 11.2 Ngày lùi đồng hồ: 25 giờ

~~~sql
WHERE occurred_at >= FROM_TZ(
        TIMESTAMP '2026-11-01 00:00:00',
        'America/New_York'
      )
  AND occurred_at < FROM_TZ(
        TIMESTAMP '2026-11-02 00:00:00',
        'America/New_York'
      )
~~~

Hai mốc tương ứng UTC `2026-11-01 04:00` và `2026-11-02 05:00`, cách nhau 25 giờ. Giờ địa phương khoảng 01:00–02:00 có thể lặp lại, nhưng **hai instants khác nhau** đều nằm trong khoảng ngày đó.

### 11.3 Không chỉ có DST

Quy tắc timezone có thể thay đổi do luật địa phương và Oracle time zone file. Một số mốc local hiếm gặp có thể mơ hồ hoặc không tồn tại. Khi thiết kế lịch quan trọng, cần có chính sách cho những trường hợp này và kiểm soát phiên bản dữ liệu timezone của ứng dụng/database.

Nguyên tắc vẫn là **xác định đầu ngày theo region, rồi xác định đầu ngày tiếp theo theo chính region đó**. Không giả định mọi ngày chứa đúng 86.400 giây.

## 12. Optimizer, index range scan và partition pruning

Khoảng nửa mở không chỉ đúng về logic mà còn thường dễ tối ưu với **index trên cột ngày giờ gốc**.

Ví dụ bảng `ORDERS` có B-tree index:

~~~sql
CREATE INDEX idx_orders_created_at
ON orders (created_at);

SELECT order_id, created_at
FROM orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';
~~~

Khi điều kiện đủ chọn lọc, Oracle có thể sử dụng **index range scan** để tìm các khóa giữa hai mốc. Nhưng nếu truy vấn lấy phần lớn bảng, optimizer có thể chọn full table scan; không có một quy tắc “có range predicate thì luôn dùng index”.

### 12.1 Vì sao TRUNC trên cột có thể tốn kém?

~~~sql
WHERE TRUNC(created_at) = DATE '2026-11-14'
~~~

Điều kiện này yêu cầu xét giá trị của một **biểu thức trên cột**. Index thường trên `CREATED_AT` không phải index trên `TRUNC(CREATED_AT)`. Có thể có function-based index hoặc các tối ưu khác, nhưng việc giữ cột gốc trong hai phép so sánh thường dễ tận dụng đường truy cập phổ biến:

~~~sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
~~~

### 12.2 Composite index với khách hàng và thời gian

Nếu thường lọc theo một khách hàng:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = :p_customer_id
  AND created_at >= :p_start
  AND created_at <  :p_end
ORDER BY created_at, order_id;
~~~

Một index có thể cân nhắc:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at, order_id);
~~~

Điều kiện bằng trên `CUSTOMER_ID` và range trên `CREATED_AT` phù hợp với cấu trúc một số đường truy cập của index này. Tuy vậy, độ chọn lọc, DML overhead, kích thước index và plan thực tế mới quyết định nó có đáng tạo hay không.

### 12.3 Partition pruning

Nếu bảng được phân vùng theo thời gian (ví dụ theo tháng), predicate:

~~~sql
WHERE sold_at >= DATE '2026-11-01'
  AND sold_at <  DATE '2026-12-01'
~~~

có thể giúp optimizer loại các partition không giao với khoảng yêu cầu, nếu partition key và thiết kế tương ứng. Ngược lại, việc chuyển cột qua biểu thức phức tạp hoặc khác semantics có thể ảnh hưởng pruning.

### 12.4 Xem execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT order_id
FROM orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` là một kế hoạch **dự kiến**, không phải phép đo tốc độ hay số hàng thực tế. Khi tuning, nên so sánh actual execution plan, access predicates, filter predicates, partition pruning và các chỉ số I/O/CPU ở dữ liệu, load tương tự production.

## 13. Batch và incremental sync: half-open là cần nhưng chưa đủ

Batch xử lý log theo các cửa sổ:

~~~text
Batch 1: [10:00, 10:05)
Batch 2: [10:05, 10:10)
Batch 3: [10:10, 10:15)
~~~

Event đúng `10:05:00` chỉ nằm trong batch 2. Cách chia này tránh đếm trùng tại mốc chung.

Tuy nhiên, **commit muộn** có thể làm batch mất dữ liệu dù predicate dùng khoảng nửa mở đúng:

1. Giao dịch T1 insert hàng có `EVENT_TIME = 10:04:59` nhưng chưa commit.
2. Lúc 10:05:01, batch 1 đọc [10:00,10:05), không thấy T1 vì chưa commit.
3. Batch 1 ghi nhận cửa sổ đã xử lý xong.
4. T1 commit lúc 10:05:03.
5. Batch 2 đọc [10:05,10:10), không lấy T1 vì event time nằm trước 10:05.

Hàng đó bị bỏ sót do dùng **event time** như một mốc bảo đảm **commit order**. Phép so sánh ranh giới không sai.

### 13.1 Phương án cần cân nhắc

- **CDC (Change Data Capture)** hoặc log-based replication dựa trên thay đổi/commit order như SCN khi cần không bỏ sót dữ liệu đã commit.
- Chạy cửa sổ có **độ trễ dự phòng** hoặc quét lại khoảng gần nhất, kết hợp **idempotent upsert** để không tạo trùng khi retry.
- Dùng khóa ổn định hoặc event ID để chống xử lý trùng.
- Khi nhiều sự kiện có cùng timestamp, dùng thêm khóa phụ hoặc checkpoint phù hợp.
- Phân biệt thời điểm event được tạo ở thiết bị với thời điểm được database commit.

Đây là lý do một báo cáo ngày thông thường và một pipeline đồng bộ chính xác cao tuy đều dùng half-open intervals nhưng có yêu cầu consistency khác nhau.

## 14. Giao diện chọn ngày và API: biến ngày inclusive thành end exclusive

Một biểu mẫu báo cáo hiển thị:

~~~text
Từ ngày: 01/11/2026
Đến hết ngày: 14/11/2026
~~~

Người dùng thường hiểu **cả ngày 14 được tính vào**. Backend cần chuyển ngữ nghĩa này thành:

~~~text
startInclusive = 2026-11-01 00:00
endExclusive   = 2026-11-15 00:00
~~~

Sau đó SQL:

~~~sql
WHERE created_at >= :start_inclusive
  AND created_at <  :end_exclusive
~~~

Đây là chuẩn hóa điều kiện chứ không phải thay đổi ý định của người dùng.

### 14.1 Đặt tên tham số rõ nghĩa

Một API có thể nhận:

~~~json
{
  "businessDate": "2026-11-14",
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

Backend xác định đầu ngày và đầu ngày tiếp theo theo zone này. Hoặc với API yêu cầu hai instants rõ:

~~~json
{
  "startInclusive": "2026-11-13T17:00:00Z",
  "endExclusive": "2026-11-14T17:00:00Z"
}
~~~

Đó là khoảng UTC tương ứng ngày 14/11 tại Việt Nam. Hợp đồng API phải làm rõ end **exclusive**, precision và time zone.

### 14.2 Java: tính hai mốc theo region

Trong Java có thể dùng `java.time`:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalDate day = LocalDate.of(2026, 11, 14);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime localStart = day.atStartOfDay(zone);
ZonedDateTime localNextStart = day.plusDays(1).atStartOfDay(zone);

Instant startInstant = localStart.toInstant();
Instant endInstant = localNextStart.toInstant();

// Chọn các hàng có startInstant <= eventInstant < endInstant.
~~~

Đặc biệt, biểu thức `day.plusDays(1).atStartOfDay(zone)` **khác** với việc cộng cứng 24 giờ vào instant start ở ngày có DST.

### 14.3 Bind qua JDBC

SQL dùng placeholders:

~~~sql
SELECT event_id, occurred_at
FROM global_events
WHERE occurred_at >= ?
  AND occurred_at < ?
ORDER BY occurred_at, event_id
~~~

Với cột TSTZ và Oracle JDBC driver hỗ trợ `OffsetDateTime`, ứng dụng có thể bind hai ranh giới dưới dạng UTC offset:

~~~java
import java.sql.PreparedStatement;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

OffsetDateTime startUtc = startInstant.atOffset(ZoneOffset.UTC);
OffsetDateTime endUtc = endInstant.atOffset(ZoneOffset.UTC);

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, startUtc);
    ps.setObject(2, endUtc);
    // Xử lý ResultSet theo ứng dụng.
}
~~~

Đoạn này minh họa cách bind; `connection`, `sql`, `startInstant` và `endInstant` là các biến đã được khởi tạo ở phần chương trình bao quanh. Mapping thực tế còn phụ thuộc phiên bản driver Oracle và kiểu cột. Với `DATE`/`TIMESTAMP` **không có zone**, phải chuyển sang kiểu và quy ước lưu trữ phù hợp, không tự giả định driver hiểu mọi giá trị là UTC.

Không nối chuỗi ngày của người dùng trực tiếp vào SQL, vừa khó kiểm soát NLS/format vừa tạo rủi ro injection.

## 15. Các định nghĩa ngày đặc biệt trong nghiệp vụ

### 15.1 Ngày kinh doanh bắt đầu 06:00

Nhà máy hoặc khách sạn có thể định nghĩa ngày kinh doanh từ 06:00 sáng đến trước 06:00 sáng hôm sau. Khoảng nửa mở vẫn là giải pháp:

~~~sql
WHERE occurred_at >= FROM_TZ(
        TIMESTAMP '2026-11-14 06:00:00',
        'Asia/Ho_Chi_Minh'
      )
  AND occurred_at < FROM_TZ(
        TIMESTAMP '2026-11-15 06:00:00',
        'Asia/Ho_Chi_Minh'
      )
~~~

Không tự dùng 00:00 nếu đơn vị đã quy định ngày kinh doanh bắt đầu 06:00.

### 15.2 Ngày theo chi nhánh và ngày chuẩn công ty

Một công ty có chi nhánh tại Việt Nam và New York có thể có ba loại báo cáo:

- Doanh thu theo **ngày địa phương của từng chi nhánh**.
- Doanh thu theo **ngày UTC** để đối soát kỹ thuật.
- Doanh thu theo **ngày chuẩn trụ sở**.

Ba cách nhóm có thể đưa một số giao dịch gần nửa đêm vào các ngày khác nhau. Chỉ thay dấu toán tử trong SQL không giải quyết sai lệch nếu chưa thống nhất định nghĩa “ngày”.

### 15.3 Dữ liệu NULL

Với `OCCURRED_AT IS NULL`, cả `>= start` và `< end` đều không trả TRUE, nên hàng không lọt vào kết quả. Nếu nghiệp vụ cần thấy những hàng chưa có thời điểm, phải xử lý NULL riêng. Không tự coi NULL là ngày 00:00 hoặc mốc nhỏ nhất.

### 15.4 “24 giờ gần nhất” khác “hôm qua”

`Last 24 hours` là một khoảng theo **duration** tính từ instant hiện tại. `Yesterday` là một **ngày lịch** theo một timezone. Chúng khác nhau ngay cả ở Việt Nam và càng khác quanh ngày DST.

Nếu yêu cầu “24 giờ gần nhất”, có thể dùng khoảng từ instant hiện tại lùi 24 giờ đến hiện tại. Nếu yêu cầu “hôm qua theo New York”, phải lấy đầu ngày hôm qua và đầu ngày hôm nay theo New York.

## 16. Bài lab: chứng minh hàng cuối ngày bị bỏ sót

Thực hành trong **schema lab riêng** được phép tạo bảng. Không chạy DDL trên schema nghiệp vụ. `CREATE TABLE` là DDL có implicit commit.

### 16.1 Tạo bảng

~~~sql
CREATE TABLE half_open_lab (
    event_id    NUMBER PRIMARY KEY,
    event_name  VARCHAR2(40) NOT NULL,
    date_at     DATE NOT NULL,
    ts_at       TIMESTAMP(6) NOT NULL
);
~~~

### 16.2 Nạp dữ liệu ở các mốc ranh giới

~~~sql
INSERT INTO half_open_lab VALUES (
    1, 'BEFORE_DAY',
    TO_DATE('2026-11-13 23:59:59', 'YYYY-MM-DD HH24:MI:SS'),
    TIMESTAMP '2026-11-13 23:59:59.999999'
);

INSERT INTO half_open_lab VALUES (
    2, 'START_DAY',
    TO_DATE('2026-11-14 00:00:00', 'YYYY-MM-DD HH24:MI:SS'),
    TIMESTAMP '2026-11-14 00:00:00.000000'
);

INSERT INTO half_open_lab VALUES (
    3, 'MIDDLE_DAY',
    TO_DATE('2026-11-14 13:15:20', 'YYYY-MM-DD HH24:MI:SS'),
    TIMESTAMP '2026-11-14 13:15:20.123456'
);

INSERT INTO half_open_lab VALUES (
    4, 'LAST_SECOND',
    TO_DATE('2026-11-14 23:59:59', 'YYYY-MM-DD HH24:MI:SS'),
    TIMESTAMP '2026-11-14 23:59:59.000000'
);

INSERT INTO half_open_lab VALUES (
    5, 'LAST_FRACTION',
    TO_DATE('2026-11-14 23:59:59', 'YYYY-MM-DD HH24:MI:SS'),
    TIMESTAMP '2026-11-14 23:59:59.999999'
);

INSERT INTO half_open_lab VALUES (
    6, 'NEXT_DAY',
    TO_DATE('2026-11-15 00:00:00', 'YYYY-MM-DD HH24:MI:SS'),
    TIMESTAMP '2026-11-15 00:00:00.000000'
);

COMMIT;
~~~

### 16.3 Thử truy vấn bằng DATE equality

~~~sql
SELECT event_id, event_name
FROM half_open_lab
WHERE date_at = DATE '2026-11-14'
ORDER BY event_id;
~~~

Kỳ vọng chỉ lấy `START_DAY`, do giá trị chính xác bằng đầu ngày.

### 16.4 Thử truy vấn bằng BETWEEN

~~~sql
SELECT event_id, event_name
FROM half_open_lab
WHERE ts_at BETWEEN
      TIMESTAMP '2026-11-14 00:00:00'
  AND TIMESTAMP '2026-11-14 23:59:59'
ORDER BY event_id;
~~~

Kỳ vọng lấy `START_DAY`, `MIDDLE_DAY`, `LAST_SECOND` nhưng **bỏ `LAST_FRACTION`**.

### 16.5 Thử truy vấn nửa mở

~~~sql
SELECT event_id,
       event_name,
       TO_CHAR(ts_at, 'YYYY-MM-DD HH24:MI:SS.FF6') AS time_text
FROM half_open_lab
WHERE ts_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND ts_at <  TIMESTAMP '2026-11-15 00:00:00'
ORDER BY event_id;
~~~

Kỳ vọng lấy **bốn hàng**: `START_DAY`, `MIDDLE_DAY`, `LAST_SECOND`, `LAST_FRACTION`. Không lấy `BEFORE_DAY` hoặc `NEXT_DAY`.

Thử cùng logic trên DATE:

~~~sql
SELECT event_id, event_name
FROM half_open_lab
WHERE date_at >= DATE '2026-11-14'
  AND date_at <  DATE '2026-11-15'
ORDER BY event_id;
~~~

Kết quả cũng là bốn hàng.

### 16.6 Chia hai ngày không chồng nhau

~~~sql
SELECT 'DAY_14' AS day_label, COUNT(*) AS event_count
FROM half_open_lab
WHERE ts_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND ts_at <  TIMESTAMP '2026-11-15 00:00:00'

UNION ALL

SELECT 'DAY_15' AS day_label, COUNT(*) AS event_count
FROM half_open_lab
WHERE ts_at >= TIMESTAMP '2026-11-15 00:00:00'
  AND ts_at <  TIMESTAMP '2026-11-16 00:00:00';
~~~

Kết quả dự kiến:

| DAY_LABEL | EVENT_COUNT |
|---|---:|
| DAY_14 | 4 |
| DAY_15 | 1 |

Hàng `NEXT_DAY` thuộc ngày 15 đúng một lần; hàng `BEFORE_DAY` không thuộc hai khoảng.

### 16.7 So sánh hai predicate khi có index

Trong lab có thể tạo:

~~~sql
CREATE INDEX idx_half_open_lab_ts ON half_open_lab(ts_at);
~~~

Rồi xem kế hoạch dự kiến của hai cách:

~~~sql
EXPLAIN PLAN FOR
SELECT event_id
FROM half_open_lab
WHERE ts_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND ts_at <  TIMESTAMP '2026-11-15 00:00:00';

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

và:

~~~sql
EXPLAIN PLAN FOR
SELECT event_id
FROM half_open_lab
WHERE TRUNC(ts_at) = DATE '2026-11-14';

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Vì lab có rất ít hàng, Oracle có thể chọn full table scan cho cả hai. Điều đó không chứng minh rằng half-open range kém: để so sánh access path cần dữ liệu đủ lớn, thống kê và workload thực tế.

## 17. Checklist khi báo cáo thiếu dữ liệu cuối ngày

| Câu hỏi | Cách kiểm tra | Rủi ro được phát hiện |
|---|---|---|
| Cột là DATE, TIMESTAMP, TSTZ hay TSLTZ? | `USER_TAB_COLUMNS.DATA_TYPE` | Đoán sai precision hoặc semantics zone |
| Cột thật sự có giờ hay phần giây không? | `TO_CHAR` với format đầy đủ | Nhầm DATE với kiểu chỉ ngày |
| Predicate dùng `=`, `BETWEEN` hay `[start,end)`? | Đọc SQL và bind values thực tế | Bỏ cuối ngày, tính trùng đầu ngày sau |
| Bind parameter có đúng kiểu không? | Kiểm tra JDBC/ORM mapping | Implicit conversion, phụ thuộc NLS |
| “Ngày” thuộc timezone nào? | Xác nhận yêu cầu báo cáo/API | UTC khác ngày địa phương |
| Session timezone có ổn định không? | `SESSIONTIMEZONE` với TSLTZ | Kết quả khác giữa session |
| Region có chuyển DST không? | Time zone rules theo ngày mục tiêu | Ngày chỉ có 23 hoặc 25 giờ |
| Dữ liệu có commit muộn không? | Kiểm tra transaction/CDC pipeline | Batch đúng biên vẫn bỏ sự kiện |
| Cột có index/partition phù hợp không? | Execution plan | Truy vấn chậm dù logic đúng |
| Có NULL hoặc dữ liệu cũ khác quy ước? | Kiểm kê schema và lịch sử migration | Bản ghi không thể lọc theo giả định hiện tại |

SQL kiểm tra kiểu cột trong schema hiện tại:

~~~sql
SELECT column_name,
       data_type,
       data_scale,
       nullable
FROM user_tab_columns
WHERE table_name = 'ORDERS'
ORDER BY column_id;
~~~

SQL xem đầy đủ giờ ở cột DATE:

~~~sql
SELECT order_id,
       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS full_created_at
FROM orders
WHERE order_id = :p_order_id;
~~~

SQL xem phần giây ở TIMESTAMP:

~~~sql
SELECT event_id,
       TO_CHAR(occurred_at, 'YYYY-MM-DD HH24:MI:SS.FF6') AS full_ts
FROM telemetry_event
WHERE event_id = :p_event_id;
~~~

Các câu `TO_CHAR` này để **quan sát**, không phải thay thế predicate dạng half-open.

## 18. Câu hỏi tự luyện

**Câu 1.** Cột `PAID_AT` là `TIMESTAMP(3)` và có hàng `2026-11-14 23:59:59.500`. Điều kiện `BETWEEN 00:00:00 AND 23:59:59` có lấy hàng không?

*Gợi ý:* Không. Mốc cuối là `23:59:59.000`. Viết `PAID_AT >= start AND PAID_AT < next_start`.

**Câu 2.** Báo cáo tháng 11 dùng `BETWEEN 01/11 00:00 AND 01/12 00:00`; báo cáo tháng 12 dùng `BETWEEN 01/12 00:00 AND 01/01 00:00`. Hàng đúng 01/12 00:00 bị tính mấy lần?

*Gợi ý:* Hai lần. Dùng khoảng nửa mở để mỗi mốc chung chỉ thuộc tháng kế tiếp.

**Câu 3.** Event xảy ra lúc `2026-11-14 20:00 UTC`. Nó thuộc ngày nào ở Việt Nam?

*Gợi ý:* 03:00 ngày 15/11 theo UTC+7; không thuộc ngày 14 theo Việt Nam.

**Câu 4.** Người dùng yêu cầu ngày 08/03/2026 tại New York; backend lấy đầu ngày rồi cộng đúng 24 giờ UTC. Sai ở đâu?

*Gợi ý:* Đây là ngày chuyển DST, dài 23 giờ theo quy tắc của region. Cần hai mốc nửa đêm **địa phương** ngày 08/03 và 09/03.

**Câu 5.** Một batch dùng đúng khoảng `[10:00,10:05)` nhưng bỏ event có EVENT_TIME=10:04:59, commit lúc 10:05:03. Tại sao?

*Gợi ý:* Event chưa visible tại thời điểm batch quét và commit sau checkpoint; half-open range không giải quyết commit-late. Cần CDC/SCN hoặc cơ chế bù, idempotency.

**Câu 6.** Hai cách `TRUNC(CREATED_AT) = DATE '2026-11-14'` và `CREATED_AT >= DATE '2026-11-14' AND CREATED_AT < DATE '2026-11-15'` có thể cùng kết quả nhưng khác gì về đường truy cập?

*Gợi ý:* Cách thứ hai dùng trực tiếp cột, thường thuận lợi hơn cho B-tree index thường và partition pruning; plan cụ thể do optimizer quyết định.

**Câu 7.** Nếu dữ liệu có timezone và ngày nghiệp vụ bắt đầu 06:00, có nên dùng hai mốc nửa đêm không?

*Gợi ý:* Không. Dùng [06:00 ngày hiện tại, 06:00 ngày kế tiếp) theo đúng region nghiệp vụ.

## 19. Những ngộ nhận cần tránh

**“Oracle DATE chỉ chứa ngày.”** Sai: DATE có cả giờ, phút, giây; giao diện chỉ hiện ngày không làm mất phần giờ đã lưu.

**“BETWEEN tự hiểu hết ngày.”** Sai: nó so sánh hai giá trị cụ thể và bao gồm cả mốc trên. Với TIMESTAMP, mốc 23:59:59 không bao phủ phần giây lẻ cuối ngày.

**“Dùng <= đầu ngày sau là an toàn.”** Sai: hàng đúng đầu ngày sau bị tính thừa và có thể trùng trong kỳ kế tiếp. Hãy dùng dấu nhỏ hơn `<`.

**“Cứ đặt 23:59:59.999999 là đủ.”** Không chắc: precision có thể khác, ngày theo region có DST, và cách viết khó bảo trì. Dùng đầu kỳ sau loại trừ.

**“TRUNC(cột) lúc nào cũng full scan.”** Không nhất thiết: function-based index và optimizer có thể xử lý khác. Nhưng half-open range trực tiếp trên cột thường đơn giản và linh hoạt hơn.

**“Chỉ cần thay NLS_DATE_FORMAT.”** Sai: NLS chỉ giải quyết format/implicit parsing, không sửa logic equality hay BETWEEN.

**“Một ngày lúc nào cũng 24 giờ.”** Sai trong nhiều region có DST. Một ngày lịch phải được xác định qua hai ranh giới local theo region tương ứng.

**“Dùng half-open thì đồng bộ chắc chắn không mất dữ liệu.”** Không đúng nếu có commit trễ, event time không đáng tin cậy hoặc checkpoint chưa xử lý retry/idempotency.

**“Ngày UTC và ngày theo chi nhánh là giống nhau.”** Không đúng với các event gần ranh giới UTC và với ngày dài/ngắn do DST.

## 20. Tổng kết

Quy tắc chuẩn để lọc một ngày hoặc một kỳ trong Oracle:

~~~sql
WHERE datetime_column >= :start_inclusive
  AND datetime_column <  :end_exclusive
~~~

Đặt **`end_exclusive` là đầu kỳ tiếp theo** theo đúng định nghĩa thời gian nghiệp vụ. Với ngày 14/11/2026 và cột DATE/TIMESTAMP theo cùng quy ước local, dùng khoảng từ **14/11 00:00** đến trước **15/11 00:00**. Cách viết này không bỏ sót bản ghi cuối ngày dù có phần giây lẻ, không đếm trùng đầu ngày sau và thường thuận lợi cho index/partition pruning hơn việc áp hàm lên cột.

Để thực sự đúng trên toàn hệ thống, còn ba điều cần đảm bảo: **kiểu tham số và cách parsing không phụ thuộc NLS**; **ranh giới được tính ở đúng timezone/region, kể cả DST**; và **batch theo timestamp có cơ chế xử lý dữ liệu đến hoặc commit muộn**. Khoảng nửa mở là quy ước nhỏ nhưng giúp tránh một lớp lỗi dữ liệu đặc biệt khó phát hiện trong báo cáo và xử lý dữ liệu Oracle.
