# Literal ngày giờ và mẫu định dạng (format model) tường minh trong Oracle

## 1. Vì sao phải viết ngày giờ một cách tường minh?

Ngày giờ là dữ liệu xuất hiện trong đơn hàng, giao dịch, lịch hẹn, log và báo cáo. Một hệ thống có người dùng ở nhiều quốc gia có thể nhận các giá trị giống nhau về mặt văn bản nhưng khác nhau về ý nghĩa: `03/04/2026` là **ngày 3 tháng 4** theo cách viết `DD/MM/YYYY`, nhưng lại là **ngày 4 tháng 3** nếu chương trình hiểu theo `MM/DD/YYYY`.

Oracle Database phân biệt rõ **giá trị ngày giờ có kiểu dữ liệu** với **chuỗi ký tự mô tả ngày giờ**. Khi cần chuyển chuỗi sang giá trị thời gian, Oracle phải biết thành phần nào là năm, tháng, ngày, giờ, phút, giây, phần lẻ giây và múi giờ. Nếu không chỉ định quy tắc chuyển đổi, kết quả có thể phụ thuộc các thiết lập NLS của phiên kết nối và gây lỗi chỉ xuất hiện ở một máy, một môi trường triển khai hoặc một tài khoản.

So sánh ba cách viết:

```sql
-- 1. Literal ngày kiểu DATE, không phụ thuộc NLS_DATE_FORMAT.
SELECT DATE '2026-11-14' AS event_day FROM dual;

-- 2. Chuỗi được chuyển sang DATE theo format model tường minh.
SELECT TO_DATE('14/11/2026', 'DD/MM/YYYY') AS event_day FROM dual;

-- 3. Chỉ là chuỗi ký tự, chưa phải giá trị DATE.
SELECT '14/11/2026' AS event_day_text FROM dual;
```

Hai câu đầu tạo giá trị **DATE**; câu cuối tạo **văn bản**. Khi câu SQL sử dụng chuỗi để so sánh với cột `DATE`, Oracle có thể phải chuyển đổi ngầm theo NLS của phiên. Đó chính là rủi ro cần tránh.

Bài học này giúp bạn:

1. Chọn đúng literal kiểu ngày giờ cho dữ liệu đã biết trong câu SQL.
2. Dùng `TO_DATE`, `TO_TIMESTAMP`, `TO_TIMESTAMP_TZ` với **format model được chỉ định rõ** khi đầu vào là chuỗi.
3. Dùng `TO_CHAR` để tạo văn bản hiển thị ngày giờ có quy tắc nhất quán.
4. Phân biệt kiểu dữ liệu có/không chứa thời gian, phần lẻ giây và múi giờ.
5. Tránh phụ thuộc `NLS_DATE_FORMAT`, `NLS_TIMESTAMP_FORMAT` và các chuyển đổi ngầm.
6. Viết điều kiện lọc ngày giờ đúng và dùng bind trong Java/JDBC.

Các ví dụ sử dụng Oracle SQL, có thể thử trong SQL*Plus, SQLcl hoặc công cụ SQL tương thích. Những câu `SELECT ... FROM dual` chỉ đọc dữ liệu; các ví dụ DDL/DML ở phần thực hành cần schema riêng có quyền phù hợp.

## 2. Đầu tiên phải phân biệt kiểu dữ liệu ngày giờ

Format model là quy tắc **biểu diễn hoặc đọc văn bản**. Nó không làm thay đổi bản chất kiểu dữ liệu đang dùng. Vì vậy cần hiểu kiểu trước khi chọn định dạng.

| Kiểu Oracle | Thành phần thông tin | Độ chính xác / múi giờ | Trường hợp sử dụng thường gặp |
|---|---|---|---|
| `DATE` | Năm, tháng, ngày, giờ, phút, giây | Đến giây, **không** lưu phần lẻ giây hoặc thông tin múi giờ | Ngày nghiệp vụ, thời điểm không cần phần lẻ giây |
| `TIMESTAMP[(p)]` | Các thành phần của `DATE` cùng phần lẻ giây | `p` là độ chính xác phần lẻ giây, **không** lưu múi giờ | Thời điểm cần mili/micro giây theo ngữ cảnh đã biết |
| `TIMESTAMP[(p)] WITH TIME ZONE` | Timestamp và thông tin múi giờ | Có múi giờ dưới dạng offset hoặc region phù hợp | Thời điểm từ nhiều múi giờ, giao tiếp hệ thống |
| `TIMESTAMP[(p)] WITH LOCAL TIME ZONE` | Timestamp được chuẩn hóa theo timezone của database và diễn giải theo session khi truy xuất | Không giữ nguyên vùng múi giờ đầu vào như `WITH TIME ZONE` | Hiển thị thời điểm theo múi giờ phiên sử dụng |

**Lưu ý quan trọng:** kiểu `DATE` của Oracle **có cả giờ, phút, giây**. Tên `DATE` dễ khiến người mới tưởng nó chỉ chứa ngày. Ví dụ `TO_DATE('2026-11-14 15:20:30', 'YYYY-MM-DD HH24:MI:SS')` tạo `DATE` với phần giờ là 15:20:30, trong khi `DATE '2026-11-14'` đặt thời gian về **00:00:00**.

`TIMESTAMP` không kèm time zone chỉ cho biết giá trị ngày giờ trên lịch. Nó **không tự cho biết đây là UTC hay giờ Việt Nam**. Nếu ứng dụng xử lý một khoảnh khắc tuyệt đối giữa các khu vực, cần xác định và lưu/trao đổi thông tin múi giờ một cách có chủ đích.

### `DATE` và `TIMESTAMP` không tự định dạng trên đĩa như `DD/MM/YYYY`

Oracle lưu giá trị thời gian bằng cấu trúc nội bộ phù hợp với kiểu dữ liệu. Một cột `DATE` không “lưu chuỗi `14/11/2026`”, còn giá trị `TIMESTAMP` không được lưu dưới dạng chuỗi hiển thị `2026-11-14 16:30:00.123`. **Format model chỉ được sử dụng khi chuyển đổi giữa chuỗi và kiểu ngày giờ**.

Khi mở một SQL worksheet và thấy:

```text
14-NOV-26
```

đó có thể chỉ là cách công cụ hoặc phiên Oracle **hiển thị** một giá trị `DATE`, không phải giá trị trong cột đã mất năm đầy đủ hay mất giờ. Muốn biết giờ, hãy chủ động:

```sql
SELECT TO_CHAR(
           TO_DATE('2026-11-14 16:30:45', 'YYYY-MM-DD HH24:MI:SS'),
           'YYYY-MM-DD HH24:MI:SS'
       ) AS full_datetime
FROM dual;
```

Kết quả văn bản mong đợi: `2026-11-14 16:30:45`.

## 3. Literal kiểu `DATE`: cách viết ngày cố định, không phụ thuộc NLS

### 3.1. Cú pháp chuẩn của Oracle

Một **ANSI DATE literal** được Oracle hỗ trợ có dạng:

```sql
DATE 'YYYY-MM-DD'
```

Ví dụ:

```sql
SELECT DATE '2026-11-14' AS ngay_bao_cao
FROM dual;

SELECT DATE '2000-01-01' AS moc_dau
FROM dual;
```

Phần trong dấu nháy phải theo cấu trúc năm bốn chữ số, tháng hai chữ số và ngày hai chữ số với dấu `-`. Literal này không dựa vào `NLS_DATE_FORMAT` của phiên, nên thích hợp cho các mốc ngày **cố định trong SQL hoặc DDL**.

**Không dùng**:

```sql
-- Không phải cú pháp DATE literal hợp lệ:
-- DATE '14/11/2026'
-- DATE '2026-11-14 08:30:00'
```

Nếu cần thêm giờ, hãy dùng `TO_DATE(..., ...)`, một literal `TIMESTAMP`, hoặc bind một giá trị có kiểu phù hợp. `DATE '2026-11-14'` có thời gian là 00:00:00, **không phải ngày không có thời gian ở cấp lưu trữ**.

### 3.2. Dùng DATE literal trong điều kiện

Giả sử bảng `orders` có cột `created_at DATE`:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= DATE '2026-11-14';
```

Điều kiện trên lấy mọi giá trị từ 00:00:00 ngày 14/11/2026 trở đi, kể cả các ngày sau. Nếu mục tiêu là **chỉ lấy đơn hàng trong ngày 14/11/2026**, cần có cả cận trên:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';
```

Khoảng nửa mở `[bắt đầu, kết thúc)` này dễ áp dụng với `DATE` và `TIMESTAMP`, kể cả khi có phần lẻ giây ở kiểu `TIMESTAMP`.

### 3.3. Literal và biểu thức ngày giờ khác nhau ở đâu?

```sql
SELECT DATE '2026-11-14' + 1 AS ngay_tiep_theo
FROM dual;
```

Khi cộng số nguyên vào `DATE`, Oracle có thể thực hiện phép cộng theo đơn vị ngày; ví dụ trên có giá trị ngày 15/11/2026. Nhưng với các kiểu `TIMESTAMP`, dùng **interval** sẽ rõ nghĩa hơn:

```sql
SELECT TIMESTAMP '2026-11-14 16:30:00' + INTERVAL '1' DAY
       AS timestamp_ngay_tiep_theo
FROM dual;
```

Đừng nhầm một **literal** biểu diễn mốc thời gian với một **format model** định nghĩa cách đọc chuỗi. `DATE '2026-11-14'` đã tạo giá trị có kiểu; chuỗi `'2026-11-14'` vẫn chỉ là text cho đến khi chuyển đổi.

## 4. Literal `TIMESTAMP`: ngày và giờ với phần lẻ giây

Oracle hỗ trợ literal kiểu:

```sql
TIMESTAMP 'YYYY-MM-DD HH24:MI:SS[.phan_le_giay]'
```

Ví dụ:

```sql
SELECT TIMESTAMP '2026-11-14 09:30:15' AS event_time
FROM dual;

SELECT TIMESTAMP '2026-11-14 09:30:15.123456' AS precise_time
FROM dual;
```

Khác `DATE`, `TIMESTAMP` có thể biểu diễn phần lẻ giây. Độ chính xác khai báo của cột `TIMESTAMP(p)` ảnh hưởng số chữ số phần lẻ giây được lưu; `TIMESTAMP(3)` thường dùng cho mili giây, `TIMESTAMP(6)` cho micro giây theo độ chính xác thập phân. Giá trị mặc định và giới hạn `p` phụ thuộc các quy tắc Oracle, thông dụng là từ 0 đến 9 với mặc định 6.

Ví dụ tạo cột:

```sql
CREATE TABLE event_log_demo (
    event_id   NUMBER PRIMARY KEY,
    created_at TIMESTAMP(6) NOT NULL
);
```

Khi bạn đã có một mốc thời gian cố định và không cần thời gian được tính động, literal `TIMESTAMP` giúp tránh việc phụ thuộc `NLS_TIMESTAMP_FORMAT`.

**Điểm cần nhớ:** `TIMESTAMP '2026-11-14 09:30:15'` **không có timezone**. Nó không tương đương với một sự kiện được xác định tuyệt đối trong UTC nếu chưa quy định vùng thời gian diễn giải bên ngoài.

### Định dạng khi hiển thị `TIMESTAMP`

```sql
SELECT TO_CHAR(
           TIMESTAMP '2026-11-14 09:30:15.123456',
           'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS text_value
FROM dual;
```

Kết quả văn bản mong đợi là `2026-11-14 09:30:15.123456`. Cú pháp `FF6` yêu cầu phần hiển thị lẻ giây đến sáu chữ số; cột timestamp có độ chính xác thấp hơn có thể thể hiện thêm các chữ số `0` theo quy tắc của Oracle.

## 5. Khi đầu vào là chuỗi: `TO_DATE`, `TO_TIMESTAMP`, `TO_TIMESTAMP_TZ`

Không phải lúc nào ứng dụng cũng nhận sẵn giá trị kiểu ngày giờ. Người dùng có thể nhập `14/11/2026`, hệ thống tích hợp gửi `"2026-11-14T09:30:15"` hoặc dữ liệu nhập khẩu từ CSV có dạng khác. Khi nhận **văn bản**, nên quy định format model rõ ràng và chuyển đổi có chủ đích.

### 5.1. `TO_DATE(char, fmt)` dành cho DATE

```sql
SELECT TO_DATE('14/11/2026', 'DD/MM/YYYY') AS ngay
FROM dual;

SELECT TO_DATE(
           '14/11/2026 16:30:45',
           'DD/MM/YYYY HH24:MI:SS'
       ) AS thoi_diem
FROM dual;
```

Trong format model:

- `DD`: ngày trong tháng.
- `MM`: tháng dạng số.
- `YYYY`: năm bốn chữ số.
- `HH24`: giờ theo hệ 24 giờ.
- `MI`: phút.
- `SS`: giây.

Chính chuỗi mẫu `'DD/MM/YYYY HH24:MI:SS'` cho Oracle biết `14` là ngày, `11` là tháng, `16` là giờ. Không còn phải đoán theo format mặc định của phiên.

### 5.2. `TO_TIMESTAMP(char, fmt)` dành cho TIMESTAMP

Khi có phần lẻ giây:

```sql
SELECT TO_TIMESTAMP(
           '2026-11-14 16:30:45.123',
           'YYYY-MM-DD HH24:MI:SS.FF3'
       ) AS created_at
FROM dual;
```

`FF3` tương ứng phần lẻ giây tối đa ba chữ số trong cách biểu diễn được chọn. Nếu dữ liệu có sáu chữ số thập phân, có thể dùng `FF6`. Đừng dùng `TO_DATE` rồi hy vọng giữ được mili giây: kiểu `DATE` không chứa phần lẻ giây.

Chuỗi có ký tự `T` phân tách theo ISO-like có thể được chuyển bằng một literal text trong format model:

```sql
SELECT TO_TIMESTAMP(
           '2026-11-14T16:30:45.123456',
           'YYYY-MM-DD"T"HH24:MI:SS.FF6'
       ) AS event_time
FROM dual;
```

`"T"` trong chuỗi format là ký tự `T` **cố định**, không phải một phần tử format như `MM` hoặc `SS`. Kiểu đầu ra vẫn là `TIMESTAMP` không có timezone.

### 5.3. `TO_TIMESTAMP_TZ(char, fmt)` khi chuỗi có múi giờ

Nếu nguồn dữ liệu gửi thêm **độ lệch UTC**, ví dụ `+07:00`:

```sql
SELECT TO_TIMESTAMP_TZ(
           '2026-11-14 16:30:45 +07:00',
           'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       ) AS event_at
FROM dual;
```

Hai thành phần `TZH` và `TZM` tương ứng phần giờ và phút của độ lệch múi giờ. Một ví dụ khác biểu diễn **cùng một thời điểm tuyệt đối**:

```sql
SELECT TO_TIMESTAMP_TZ(
           '2026-11-14 09:30:45 +00:00',
           'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       ) AS utc_time
FROM dual;
```

Trong hai ví dụ, 16:30:45 ở UTC+07:00 và 09:30:45 ở UTC+00:00 chỉ cùng một mốc thời gian. Nhưng `TIMESTAMP` không có timezone sẽ không tự cung cấp thông tin để xác định hai giá trị đó có tương đương hay không.

Khi chuỗi sử dụng **tên vùng** như `Europe/Paris`, cách diễn giải còn phụ thuộc bảng timezone của Oracle, quy tắc DST (giờ mùa hè) và đôi khi cần thông tin bổ sung để xử lý giờ trùng/lỗ hổng trong ngày chuyển giờ. Không thay tên vùng bằng offset cố định nếu nghiệp vụ yêu cầu giữ quy tắc vùng theo lịch sử.

### 5.4. Chọn hàm chuyển đổi theo dữ liệu đích

| Dữ liệu đầu vào | Kiểu cần tạo | Cách viết phù hợp |
|---|---|---|
| `'2026-11-14'` | `DATE` | `DATE '2026-11-14'` hoặc `TO_DATE('2026-11-14','YYYY-MM-DD')` |
| `'14/11/2026 08:25:00'` | `DATE` | `TO_DATE(...,'DD/MM/YYYY HH24:MI:SS')` |
| `'2026-11-14 08:25:00.123456'` | `TIMESTAMP` | `TO_TIMESTAMP(...,'YYYY-MM-DD HH24:MI:SS.FF6')` |
| `'2026-11-14 08:25:00 +07:00'` | `TIMESTAMP WITH TIME ZONE` | `TO_TIMESTAMP_TZ(...,'YYYY-MM-DD HH24:MI:SS TZH:TZM')` |
| Giá trị ngày giờ đã có kiểu trong bind JDBC | Kiểu phù hợp với cột | Dùng API bind giá trị có kiểu; không cần đổi thành chuỗi để parse lại |

**Không dùng `TO_DATE` trên một giá trị đã có kiểu `DATE` rồi tự áp format.** Oracle có thể phải chuyển giá trị `DATE` sang chuỗi theo `NLS_DATE_FORMAT`, sau đó parse lại bằng format bạn nêu. Nếu hai mẫu không khớp, kết quả sai hoặc sinh lỗi. `TO_DATE` có mục đích **chuyển văn bản thành `DATE`**.

## 6. Format model: mỗi ký hiệu mang một ý nghĩa cụ thể

Format model là chuỗi mô tả cấu trúc đầu vào cho hàm chuyển đổi hoặc cấu trúc đầu ra cho hàm định dạng. Những phần tử cơ bản nên thuộc:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| `YYYY` | Năm bốn chữ số | `2026` |
| `YY` | Năm hai chữ số gắn với thế kỷ theo quy tắc Oracle | `26` |
| `RR` | Năm hai chữ số theo quy tắc diễn giải thế kỷ đặc biệt | `26` |
| `MM` | Tháng bằng số, thường `01`–`12` | `11` |
| `MON` | Tên tháng viết tắt theo ngôn ngữ NLS | `NOV` trong English |
| `MONTH` | Tên tháng đầy đủ theo NLS | `NOVEMBER` trong English |
| `DD` | Ngày trong tháng | `14` |
| `DDD` | Số thứ tự ngày trong năm | Ví dụ 1–366 |
| `DY`, `DAY` | Tên thứ viết tắt/đầy đủ theo NLS | `SAT`, `SATURDAY` trong English |
| `HH24` | Giờ 24 giờ, `00`–`23` | `16` |
| `HH12` / `HH` | Giờ 12 giờ, thường đi với `AM`/`PM` | `04 PM` |
| `MI` | **Phút**, `00`–`59` | `30` |
| `SS` | Giây, `00`–`59` | `45` |
| `FF`, `FF1`…`FF9` | Phần lẻ giây trong biểu thức `TIMESTAMP` | `FF3` cho mili giây |
| `TZH` | Phần giờ độ lệch múi giờ | `+07` |
| `TZM` | Phần phút độ lệch múi giờ | `00` |
| `TZR` | Tên vùng múi giờ hoặc vùng/offset theo cú pháp được hỗ trợ | `Europe/Paris` |
| `TZD` | Tên viết tắt chỉ trạng thái daylight saving theo vùng khi áp dụng | Phụ thuộc vùng/điều kiện |

### Các nhầm lẫn dễ gây lỗi

- **`MM` là tháng, `MI` là phút**. Viết `'HH24:MM:SS'` để đọc giờ-phút-giây là sai ý nghĩa.
- **`DD` là ngày trong tháng**, còn `DY`/`DAY` là tên thứ. `D` là thứ trong tuần theo quy tắc `NLS_TERRITORY`, nên không dùng `D` như một mã ngày tháng bất biến giữa môi trường.
- **`HH12` khác `HH24`**. Nếu dữ liệu dùng `04:30 PM`, format cần diễn đạt giờ 12 giờ và `PM`.
- **`YYYY` khác `YY` và `RR`**. Nếu có thể, gửi năm bốn chữ số để tránh quy tắc suy đoán thế kỷ.
- **`FF` dành cho timestamp**; `DATE` không giữ phần lẻ giây.
- **`TZH:TZM` là offset**; không thể thay thế mọi trường hợp cần tên vùng timezone có lịch sử DST.

Ví dụ các mẫu thường dùng:

```sql
-- Ngày Việt Nam
SELECT TO_DATE('14/11/2026', 'DD/MM/YYYY') FROM dual;

-- Ngày và giờ kiểu 24h
SELECT TO_DATE('14-11-2026 16:05:09',
               'DD-MM-YYYY HH24:MI:SS') FROM dual;

-- Giờ 12h có AM/PM
SELECT TO_DATE('14/11/2026 04:05:09 PM',
               'DD/MM/YYYY HH12:MI:SS AM') FROM dual;

-- Timestamp có mili giây
SELECT TO_TIMESTAMP('2026-11-14 16:05:09.321',
                    'YYYY-MM-DD HH24:MI:SS.FF3') FROM dual;
```

Trong mẫu `HH12:MI:SS AM`, ký hiệu `AM` trong format đại diện cho AM/PM theo cách Oracle phân tích dữ liệu, dù đầu vào ví dụ là `PM`.

## 7. `TO_CHAR`: định dạng chiều ngược lại, từ ngày giờ thành text

`TO_DATE` và `TO_TIMESTAMP` đọc **chuỗi để tạo giá trị thời gian**. `TO_CHAR` thực hiện việc ngược lại: từ giá trị ngày giờ tạo **chuỗi để hiển thị, xuất dữ liệu hoặc xây thông báo**.

### 7.1. Định dạng cố định để xuất báo cáo

```sql
SELECT TO_CHAR(DATE '2026-11-14', 'DD/MM/YYYY') AS display_day
FROM dual;
```

Kết quả: `14/11/2026`.

Một giá trị `DATE` có giờ:

```sql
SELECT TO_CHAR(
           TO_DATE('2026-11-14 16:30:45',
                   'YYYY-MM-DD HH24:MI:SS'),
           'DD/MM/YYYY HH24:MI:SS'
       ) AS displayed_time
FROM dual;
```

Kết quả: `14/11/2026 16:30:45`.

Cho `TIMESTAMP`:

```sql
SELECT TO_CHAR(
           TIMESTAMP '2026-11-14 16:30:45.123456',
           'YYYY-MM-DD"T"HH24:MI:SS.FF6'
       ) AS iso_like_text
FROM dual;
```

Kết quả: `2026-11-14T16:30:45.123456`.

Lưu ý đây là **chuỗi ISO-like không có thông tin UTC/offset** vì giá trị đầu vào là `TIMESTAMP` không có timezone. Không tự thêm ký tự `Z` rồi gọi là UTC trừ khi bạn biết và đã chuyển đúng về UTC.

### 7.2. Format model làm thay đổi biểu diễn, không thay đổi giá trị gốc

```sql
SELECT TO_CHAR(DATE '2026-11-14', 'YYYY-MM-DD') AS us_iso,
       TO_CHAR(DATE '2026-11-14', 'DD/MM/YYYY') AS vn_date
FROM dual;
```

Hai chuỗi hiển thị khác nhau nhưng bắt nguồn từ **cùng một giá trị DATE**. Cột `DATE` trong database không bị viết lại khi gọi `TO_CHAR`.

Đừng lưu kết quả `TO_CHAR(created_at, 'DD/MM/YYYY')` trở lại cột ngày giờ chỉ để “dễ đọc”. Cách hiển thị thuộc tầng giao diện hoặc xuất dữ liệu, còn việc lưu trữ/truy vấn nên giữ kiểu ngày giờ.

### 7.3. `FM`: bỏ phần đệm trong kết quả định dạng

Một số phần tử định dạng như `MONTH` hoặc `DAY` có thể tự đệm khoảng trắng để giữ độ rộng. Modifier **`FM`** (*fill mode*) có thể bỏ phần đệm và số 0 ở đầu khi định dạng.

```sql
SELECT TO_CHAR(DATE '2026-01-05', 'DD/MM/YYYY')   AS padded_date,
       TO_CHAR(DATE '2026-01-05', 'FMDD/MM/YYYY') AS compact_date
FROM dual;
```

Kết quả minh họa: `05/01/2026` so với `5/1/2026`. Dùng `FM` có ích cho chuỗi hiển thị thân thiện, nhưng không nên dùng bừa khi hệ thống tích hợp yêu cầu số chữ số cố định. Với file trao đổi dữ liệu, `YYYY-MM-DD` thường dễ kiểm soát hơn `FMYYYY-MM-DD`.

### 7.4. Tên tháng và ngôn ngữ NLS

`MON`, `MONTH`, `DAY`, `DY` dựa vào ngôn ngữ ngày giờ, nên có thể tạo chuỗi khác nhau giữa phiên đặt tiếng Anh và một ngôn ngữ khác.

```sql
SELECT TO_CHAR(
           DATE '2026-11-14',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=ENGLISH'
       ) AS english_date
FROM dual;
```

Kết quả minh họa: `14-NOV-2026`.

Tham số thứ ba ở những hàm hỗ trợ cho phép chỉ định ngôn ngữ cho các thành phần tên tháng/thứ, giúp định dạng không phụ thuộc ngôn ngữ mặc định của session. Trong dữ liệu tích hợp giữa các hệ thống, ưu tiên format **chỉ dùng số** nếu không có yêu cầu dùng tên tháng.

## 8. `FX`: yêu cầu input tuân theo format chặt chẽ

Không phải cứ viết `'YYYY-MM-DD'` là mọi dấu phân cách đều được Oracle so khớp một cách tuyệt đối trong tất cả chế độ parse. Oracle có thể chấp nhận một số biến thể khi không dùng modifier kiểm tra chính xác. Nếu định dạng đầu vào là **hợp đồng dữ liệu** cần tuân thủ nghiêm ngặt, dùng **`FX`** (*format exact*) trong format model.

```sql
SELECT TO_DATE('2026-11-14', 'FXYYYY-MM-DD') AS parsed_day
FROM dual;
```

Đoạn trên yêu cầu cấu trúc và số chữ số đúng theo format tường minh. Một chuỗi không khớp chính xác có thể bị từ chối:

```sql
-- Ví dụ cần bị từ chối bởi định dạng chính xác:
-- TO_DATE('2026/11/14', 'FXYYYY-MM-DD')
-- TO_DATE('2026-1-4',   'FXYYYY-MM-DD')
```

Một format model tường minh **không thay thế việc kiểm tra tính hợp lệ lịch**. Ví dụ ngày 30/02/2026 không tồn tại; Oracle sẽ từ chối khi parse:

```sql
-- Sai ngày lịch, ví dụ:
-- SELECT TO_DATE('2026-02-30', 'FXYYYY-MM-DD') FROM dual;
```

`FM` và `FX` có chức năng khác nhau: `FM` kiểm soát phần điền/đệm trong định dạng, còn `FX` yêu cầu so khớp chính xác khi parse. Có thể kết hợp theo những quy tắc format model của Oracle, nhưng nên dùng một quy ước đơn giản, rõ ràng cho dữ liệu đầu vào thay vì tạo format phức tạp khó bảo trì.

## 9. NLS tác động ở đâu? Vì sao cùng script chạy khác môi trường?

**NLS (National Language Support)** trong Oracle là nhóm thiết lập liên quan ngôn ngữ, lãnh thổ, trình bày và cách chuyển đổi dữ liệu. Các tham số liên quan ngày giờ thường gặp:

| Tham số NLS/session | Phạm vi tác động khái quát |
|---|---|
| `NLS_DATE_FORMAT` | Mẫu mặc định hiển thị/chuyển đổi ngầm kiểu `DATE` |
| `NLS_TIMESTAMP_FORMAT` | Mẫu mặc định với `TIMESTAMP` không timezone |
| `NLS_TIMESTAMP_TZ_FORMAT` | Mẫu mặc định với `TIMESTAMP WITH TIME ZONE` |
| `NLS_DATE_LANGUAGE` | Ngôn ngữ của tên tháng, tên thứ và các thành phần văn bản của ngày |
| `NLS_TERRITORY` | Quy ước lãnh thổ, có thể ảnh hưởng thứ trong tuần và các mặc định |
| `SESSIONTIMEZONE` | Múi giờ của phiên khi xử lý các loại/biểu thức phụ thuộc session timezone |

### 9.1. Quan sát thiết lập của phiên

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_TERRITORY'
)
ORDER BY parameter;

SELECT SESSIONTIMEZONE AS session_time_zone
FROM dual;
```

Các giá trị thực tế phụ thuộc client, driver, session và cấu hình database. Một ứng dụng có thể thiết lập NLS riêng khi mở session hoặc qua connection pool, nên kết quả không nhất thiết giống một phiên SQL*Plus thủ công.

### 9.2. Ví dụ chuyển đổi ngầm nguy hiểm

Hãy xem:

```sql
-- Không nên dựa vào chuyển đổi chuỗi ngầm:
SELECT *
FROM orders
WHERE created_at = '14/11/2026';
```

Nếu `created_at` là `DATE`, Oracle cần diễn giải chuỗi `'14/11/2026'`. Cách diễn giải phụ thuộc ngữ cảnh chuyển đổi, bao gồm định dạng NLS. Cùng câu SQL có thể chạy trên một phiên và lỗi trên phiên khác.

Viết lại:

```sql
-- Mốc ngày đúng và độc lập NLS:
SELECT *
FROM orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';
```

Hoặc nếu đầu vào thực sự là chuỗi theo định dạng ngày/tháng/năm:

```sql
SELECT *
FROM orders
WHERE created_at >= TO_DATE('14/11/2026', 'FXDD/MM/YYYY')
  AND created_at <  TO_DATE('14/11/2026', 'FXDD/MM/YYYY') + 1;
```

Trong ứng dụng, thường nên **parse và bind giá trị ngày giờ một lần**, tránh gọi nhiều hàm chuyển đổi trên cùng tham số khi đã có cách chuẩn hơn.

### 9.3. `ALTER SESSION SET NLS_DATE_FORMAT` dùng để làm gì?

Trong phiên thực hành SQL*Plus, bạn có thể tạm thay đổi format hiển thị mặc định:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY HH24:MI:SS';

SELECT DATE '2026-11-14' AS dt
FROM dual;
```

Lệnh trên thay đổi **cách phiên hiển thị hoặc chuyển đổi mặc định**, không chuyển đổi toàn bộ dữ liệu `DATE` đã lưu. Nó không phải giải pháp tốt để ép mọi ứng dụng có cùng cách parse chuỗi, bởi mỗi phiên có thể có NLS khác và có thể được connection pool tái sử dụng.

Để hiển thị nhất quán trong một báo cáo, nên ghi format trực tiếp bằng `TO_CHAR`; để truyền giá trị trong code, bind giá trị có kiểu.

### 9.4. Ngày có tên tháng: chỉ định `NLS_DATE_LANGUAGE`

```sql
SELECT TO_DATE(
           '14-Nov-2026',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=ENGLISH'
       ) AS parsed_date
FROM dual;
```

Với chuỗi đầu vào có tên tháng tiếng Anh, việc chỉ định `NLS_DATE_LANGUAGE=ENGLISH` ngăn parser phụ thuộc ngôn ngữ của session. Tuy nhiên, `DD-MON-YYYY` vẫn nhạy với cách viết tên tháng; nếu bạn kiểm soát format đầu vào, dùng dạng số `YYYY-MM-DD` thường đơn giản và ít rủi ro hơn.

## 10. Năm hai chữ số, `YY`, `RR` và lỗi “đổi thế kỷ”

Tránh dùng năm hai chữ số cho dữ liệu nghiệp vụ cần tồn tại nhiều thập kỷ. Các format `YY` và `RR` đều liên quan suy luận năm bốn chữ số, nhưng quy tắc không giống nhau:

- **`YY`** diễn giải hai chữ số theo thế kỷ hiện tại theo quy tắc Oracle.
- **`RR`** có quy tắc chọn thế kỷ đặc biệt dựa vào năm hiện tại và giá trị đầu vào; nó được thiết kế để hỗ trợ một số dữ liệu hai chữ số từ các ứng dụng cũ.
- **`YYYY`** nêu trực tiếp năm bốn chữ số, tránh việc thay đổi kết quả theo thế kỷ hiện tại.

Ví dụ dữ liệu nguồn `01/01/49` và `01/01/50` chứa sự mơ hồ về thế kỷ. Việc mặc định các chuỗi đó thành 2049 hoặc 1950 mà không có quy tắc nghiệp vụ rõ ràng có thể sai. Nên yêu cầu nguồn cung cấp `2049-01-01` hoặc `1950-01-01` khi đó là thông tin chính xác.

**Khuyến nghị:** dữ liệu trao đổi giữa các hệ thống nên chứa năm bốn chữ số và timezone/offset khi là mốc thời gian tuyệt đối; giữ `RR` chủ yếu để xử lý định dạng di sản đã được quy định rõ.

## 11. Ngày và giờ không đồng nghĩa với múi giờ

### 11.1. `DATE`/`TIMESTAMP` không lưu thông tin timezone

```sql
SELECT DATE '2026-11-14' AS d,
       TIMESTAMP '2026-11-14 16:30:00' AS ts
FROM dual;
```

Không giá trị nào ở đây tự cho biết 16:30 là theo UTC+07:00 hay UTC+00:00. `DATE` của Oracle cũng không tự lưu “ngày theo múi giờ của hệ thống”. Đó là một giá trị lịch và giờ; việc diễn giải theo timezone thuộc ứng dụng/quy tắc nghiệp vụ.

### 11.2. `TIMESTAMP WITH TIME ZONE`

Nếu nguồn có offset:

```sql
SELECT TO_TIMESTAMP_TZ(
           '2026-11-14 16:30:00 +07:00',
           'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       ) AS event_with_zone
FROM dual;
```

Bạn có thể xuất văn bản đi kèm offset:

```sql
SELECT TO_CHAR(
           TO_TIMESTAMP_TZ(
               '2026-11-14 16:30:00 +07:00',
               'YYYY-MM-DD HH24:MI:SS TZH:TZM'
           ),
           'YYYY-MM-DD"T"HH24:MI:SS TZH:TZM'
       ) AS event_text
FROM dual;
```

Việc định dạng có `TZH:TZM` giúp người đọc biết chênh lệch so với UTC. Nếu muốn xuất theo UTC, cần **chuyển đổi timezone** trước khi gắn ký hiệu UTC, không chỉ thay `+07:00` thành `Z` trong chuỗi.

### 11.3. `TIMESTAMP WITH LOCAL TIME ZONE`

Loại này được Oracle **chuẩn hóa** về cơ sở lưu trữ theo database timezone và được **hiển thị theo session timezone** khi truy vấn. Nó không giữ nguyên zone region/offset nguồn như `TIMESTAMP WITH TIME ZONE`.

Do đó cùng một giá trị `TIMESTAMP WITH LOCAL TIME ZONE` có thể được hiển thị khác nhau ở hai phiên:

```text
Session 1 TIME_ZONE = '+07:00'  -> 16:30
Session 2 TIME_ZONE = '+00:00'  -> 09:30
```

Hai cách hiển thị có thể đại diện cùng một mốc. Điều này hữu ích nhưng phải được cân nhắc trong ứng dụng nhiều khu vực, các batch job và connection pool có timezone khác nhau.

### 11.4. Những hàm “thời điểm hiện tại” khác nhau

| Biểu thức | Kiểu trả về | Cách hiểu chính |
|---|---|---|
| `SYSDATE` | `DATE` | Ngày giờ từ hệ thống nơi database hoạt động, đến giây, không timezone trong kiểu trả về |
| `SYSTIMESTAMP` | `TIMESTAMP WITH TIME ZONE` | Thời điểm hiện tại kèm thông tin timezone từ môi trường database |
| `CURRENT_DATE` | `DATE` | Ngày giờ hiện tại tính theo timezone của session |
| `CURRENT_TIMESTAMP` | `TIMESTAMP WITH TIME ZONE` | Timestamp hiện tại theo timezone của session |
| `LOCALTIMESTAMP` | `TIMESTAMP` | Ngày giờ hiện tại theo session nhưng không lưu timezone trong kiểu trả về |

Ví dụ:

```sql
SELECT TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS') AS server_clock,
       TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS session_clock,
       TO_CHAR(CURRENT_TIMESTAMP,
               'YYYY-MM-DD HH24:MI:SS TZH:TZM') AS timestamp_with_offset
FROM dual;
```

Các giá trị phụ thuộc thời điểm thực thi và cấu hình môi trường. Không sử dụng hàm hiện tại để tạo những ngày mẫu cần tái lập kết quả; khi thực hành định dạng, hãy dùng literal cố định.

### 11.5. Offset và tên vùng không phải một

Offset `+07:00` thể hiện chênh lệch với UTC tại mốc thời gian cụ thể. Tên vùng như `Europe/Paris` có quy tắc múi giờ **thay đổi theo lịch** (ví dụ DST). Cùng một vùng có thể sử dụng các offset khác nhau theo mùa; một giờ địa phương có thể không tồn tại hoặc bị lặp trong ngày chuyển DST.

Khi hệ thống đặt lịch **trong tương lai theo giờ địa phương của một khu vực**, việc giữ **region ID và quy tắc vùng** có thể quan trọng hơn lưu chỉ một offset tĩnh. Khi chỉ cần truyền một thời điểm đã xảy ra giữa các hệ thống, timestamp có offset/UTC được chuẩn hóa thường dễ đối chiếu hơn. Cần chọn thiết kế theo nghiệp vụ.

## 12. So sánh và lọc dữ liệu DATE/TIMESTAMP chính xác

### 12.1. Bẫy `=` với DATE có phần giờ

Giả sử:

```text
created_at = 2026-11-14 10:30:00
```

Điều kiện:

```sql
WHERE created_at = DATE '2026-11-14'
```

chỉ tìm các hàng có thời gian **đúng 00:00:00** của ngày 14/11/2026, không phải mọi hàng trong ngày đó.

Cách phổ biến để lấy mọi thời điểm của một ngày:

```sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
```

Nếu `created_at` là `TIMESTAMP`, mốc bắt đầu và kết thúc cần có kiểu/ép kiểu phù hợp theo chính sách dữ liệu; ví dụ:

```sql
WHERE created_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-15 00:00:00'
```

Không dùng cận cuối dạng `23:59:59` để lọc `TIMESTAMP`: bạn có thể bỏ sót các giá trị như `23:59:59.999999`. Khoảng nửa mở tránh phải đoán độ chính xác của phần lẻ giây.

### 12.2. Vì sao `BETWEEN` dễ bỏ sót cuối ngày?

```sql
-- Dễ thiếu các giá trị có giờ sau 00:00:00 ngày kết thúc:
WHERE created_at BETWEEN DATE '2026-11-01' AND DATE '2026-11-30'
```

`BETWEEN` bao gồm cả hai cận, nhưng `DATE '2026-11-30'` là 00:00:00. Nếu muốn lấy toàn bộ tháng 11, viết:

```sql
WHERE created_at >= DATE '2026-11-01'
  AND created_at <  DATE '2026-12-01'
```

Với cột có timezone, cần xác định “ngày” theo **múi giờ nào** trước khi tính hai cận thời gian. Một ngày địa phương ở vùng có DST không nhất thiết luôn kéo dài 24 giờ tuyệt đối.

### 12.3. Tránh chuyển cột ngày giờ thành chuỗi để lọc

Ví dụ sau khó tối ưu và có thể thay đổi ý nghĩa:

```sql
-- Không nên dùng như cách lọc chính cho cột DATE/TIMESTAMP:
WHERE TO_CHAR(created_at, 'DD/MM/YYYY') = '14/11/2026'
```

Nó biến **cột ngày giờ** thành text trước khi so sánh. Điều này có thể cản trở việc sử dụng một index thông thường trên cột `created_at`, khiến Oracle phải xử lý chuyển đổi trên nhiều hàng và làm phụ thuộc kết quả vào các lựa chọn format/collation liên quan.

Cách tốt hơn cho phạm vi ngày:

```sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
```

Một số hệ thống có **function-based index** dành riêng cho biểu thức trên cột ngày giờ, nhưng đó là quyết định thiết kế có kiểm chứng, không phải lý do để mặc định dùng `TO_CHAR` cho mọi bộ lọc.

### 12.4. Cận lọc nên được bind với kiểu phù hợp

Nếu người dùng chọn ngày bắt đầu/kết thúc, backend nên parse yêu cầu vào kiểu ngày giờ phù hợp rồi bind:

```text
Người dùng chọn ngày 14/11/2026
                |
                v
Backend parse LocalDate(2026-11-14)
                |
                v
Tạo start = 2026-11-14 00:00
     end   = 2026-11-15 00:00
                |
                v
SQL: created_at >= ? AND created_at < ?
```

Tùy kiểu cột `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, backend sẽ chọn kiểu tham số và cách chuyển timezone phù hợp. Giá trị đầu vào phải được kiểm tra trước, không nên ghép trực tiếp chuỗi ngày giờ của người dùng vào SQL.

## 13. Java/JDBC: bind giá trị có kiểu thay vì phụ thuộc NLS

Ứng dụng Java thường nhận `LocalDate`, `LocalDateTime`, `OffsetDateTime` hoặc một loại thời gian khác từ tầng nghiệp vụ. JDBC cho phép gắn tham số có kiểu, tránh phải dựng SQL như `'14/11/2026'`.

### 13.1. Ví dụ với cột `DATE`

Giả sử bảng có cột `created_at DATE`, ứng dụng cần lọc các bản ghi trong một ngày:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDate;
import java.time.LocalDateTime;

LocalDate selectedDay = LocalDate.of(2026, 11, 14);
LocalDateTime start = selectedDay.atStartOfDay();
LocalDateTime end = selectedDay.plusDays(1).atStartOfDay();

String sql = """
    SELECT order_id
    FROM orders
    WHERE created_at >= ?
      AND created_at < ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(1, Timestamp.valueOf(start));
    ps.setTimestamp(2, Timestamp.valueOf(end));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("order_id");
            // Xử lý kết quả...
        }
    }
}
```

Đây là đoạn minh họa cho **cột ngày giờ không mang timezone**, trong môi trường driver và cách ánh xạ đã được thống nhất. `TIMESTAMP` của JDBC và Oracle `DATE` có thể được chuyển đổi theo driver/cấu hình; khi ứng dụng có yêu cầu timezone hoặc semantics khác, phải chọn kiểu mapping phù hợp và kiểm chứng với driver thực tế.

Ví dụ không ghép:

```java
// Tránh: phụ thuộc chuỗi ngày theo format hoặc tạo SQL động không an toàn.
String unsafe = "SELECT * FROM orders WHERE created_at = '"
                + userInputDate + "'";
```

Dùng `PreparedStatement` với tham số là giá trị ngày giờ giúp tách **dữ liệu** khỏi **cú pháp SQL**, giảm nguy cơ injection và giảm phụ thuộc vào NLS date format.

### 13.2. LocalDate, LocalDateTime và OffsetDateTime trả lời các câu hỏi khác nhau

| Kiểu Java | Ý nghĩa | Thường xem xét với kiểu Oracle nào |
|---|---|---|
| `LocalDate` | Một ngày lịch, không có giờ/múi giờ | `DATE` dùng phần ngày, theo chính sách ứng dụng |
| `LocalDateTime` | Ngày giờ địa phương nhưng không kèm múi giờ | `TIMESTAMP`, hoặc `DATE` nếu chỉ cần đến giây |
| `OffsetDateTime` | Ngày giờ kèm độ lệch UTC | `TIMESTAMP WITH TIME ZONE` |
| `Instant` | Mốc thời gian tuyệt đối trên trục UTC | Cần quyết định cách biểu diễn/bind theo driver và schema, thường quy về UTC hoặc timezone-aware column |
| `ZonedDateTime` | Ngày giờ gắn tên vùng và quy tắc timezone | Cần chiến lược lưu cả thông tin vùng nếu lịch hẹn tương lai phụ thuộc quy tắc DST |

JDBC 4.2 và các phiên bản Oracle JDBC hiện đại hỗ trợ nhiều ánh xạ `java.time`, nhưng hỗ trợ cụ thể cho `TIMESTAMP WITH TIME ZONE`, `TIMESTAMP WITH LOCAL TIME ZONE` và region/offset cần đối chiếu phiên bản driver, framework và chính sách timezone đang dùng. Không tự giả định truyền một `LocalDateTime` sẽ luôn chuyển đúng UTC.

### 13.3. Ví dụ bind có timezone

Nếu schema và driver hỗ trợ `OffsetDateTime` cho cột `TIMESTAMP WITH TIME ZONE`, cách diễn đạt ở tầng Java có thể như sau:

```java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.LocalDateTime;
import java.sql.PreparedStatement;

OffsetDateTime eventTime = OffsetDateTime.of(
    LocalDateTime.of(2026, 11, 14, 16, 30, 45),
    ZoneOffset.ofHours(7)
);

String sql = "INSERT INTO events_tz (event_id, occurred_at) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1001L);
    ps.setObject(2, eventTime);
    ps.executeUpdate();
}
```

Đây là **minh họa API**: nó giả định bảng `events_tz` có cột `TIMESTAMP WITH TIME ZONE`, driver hỗ trợ ánh xạ `OffsetDateTime`, và transaction được quản lý đúng. Với driver cũ, có thể cần cách bind riêng của Oracle. Không đổi một `OffsetDateTime` thành chuỗi bằng `toString()` rồi tin rằng Oracle sẽ parse giống nhau ở mọi phiên.

### 13.4. Ranh giới giữa ngày lịch và thời điểm tuyệt đối

“Ngày sinh 14/11/2026” là **ngày lịch**; thường không cần biến thành một `Instant` UTC. Ngược lại, “đơn hàng được tạo lúc 16:30:45 tại Việt Nam” là **thời điểm phát sinh sự kiện**; ứng dụng phân tán nên có hợp đồng timezone/offset rõ ràng.

Một lỗi phổ biến là ép mọi giá trị ngày lịch qua `Instant` rồi đổi timezone, dẫn đến ngày hiển thị lệch một ngày ở một số khu vực. Chọn đúng bản chất dữ liệu trước khi chọn kiểu Oracle hay format model.

## 14. Ví dụ thực hành: nhập, hiển thị và lọc ngày giờ

Các ví dụ dưới đây thiết kế cho schema thực hành. Những lệnh `CREATE TABLE`, `INSERT`, `DROP TABLE` thay đổi dữ liệu; chỉ chạy nếu được phép và trên schema dành cho học tập.

### Bước 1. Xem NLS phiên và timezone

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT',
    'NLS_DATE_LANGUAGE'
)
ORDER BY parameter;

SELECT SESSIONTIMEZONE AS tz FROM dual;
```

Ghi lại kết quả; không cần thay đổi các giá trị này để hoàn thành các bước tiếp theo.

### Bước 2. Tạo bảng dùng đủ ba kiểu thời gian

```sql
CREATE TABLE demo_datetime_formats (
    event_id    NUMBER PRIMARY KEY,
    event_day   DATE NOT NULL,
    event_time  TIMESTAMP(6) NOT NULL,
    event_tz    TIMESTAMP(6) WITH TIME ZONE NOT NULL
);
```

Ở đây `event_day` có tên “day” nhưng vì là kiểu `DATE` nó vẫn có thể chứa giờ-phút-giây; câu chèn phía dưới sử dụng midnight để minh họa ngày thuần.

### Bước 3. Chèn bằng literal và format tường minh

```sql
INSERT INTO demo_datetime_formats (
    event_id, event_day, event_time, event_tz
) VALUES (
    1,
    DATE '2026-11-14',
    TIMESTAMP '2026-11-14 16:30:45.123456',
    TO_TIMESTAMP_TZ(
        '2026-11-14 16:30:45.123456 +07:00',
        'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
    )
);

INSERT INTO demo_datetime_formats (
    event_id, event_day, event_time, event_tz
) VALUES (
    2,
    TO_DATE('15/11/2026', 'FXDD/MM/YYYY'),
    TO_TIMESTAMP('2026-11-15T08:15:00.500000',
                 'YYYY-MM-DD"T"HH24:MI:SS.FF6'),
    TO_TIMESTAMP_TZ('2026-11-15 08:15:00 +07:00',
                    'YYYY-MM-DD HH24:MI:SS TZH:TZM')
);

COMMIT;
```

Cả hai dòng đều dùng giá trị được parse theo quy tắc rõ ràng; không yêu cầu `NLS_DATE_FORMAT` phải là `DD/MM/YYYY`.

### Bước 4. Hiển thị với một format do script kiểm soát

```sql
SELECT event_id,
       TO_CHAR(event_day,  'YYYY-MM-DD HH24:MI:SS') AS day_text,
       TO_CHAR(event_time, 'YYYY-MM-DD HH24:MI:SS.FF6') AS timestamp_text,
       TO_CHAR(event_tz,   'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM') AS tz_text
FROM demo_datetime_formats
ORDER BY event_id;
```

Bạn có thể thấy `event_day` ở 00:00:00, `event_time` giữ phần lẻ giây, còn `event_tz` có offset. Format model được dùng **chỉ ở bước trình bày**, không thay kiểu cột.

### Bước 5. Lọc đúng ngày 14/11 bằng khoảng nửa mở

```sql
SELECT event_id
FROM demo_datetime_formats
WHERE event_day >= DATE '2026-11-14'
  AND event_day <  DATE '2026-11-15'
ORDER BY event_id;
```

Kết quả kỳ vọng là `event_id = 1`. Nếu thay `event_day` bằng một cột chứa giờ khác 00:00:00, điều kiện dạng nửa mở vẫn hoạt động theo ý nghĩa “mọi thời điểm trong ngày”.

### Bước 6. Quan sát năm/tháng/ngày mà không định dạng cả chuỗi

Oracle có hàm `EXTRACT` phù hợp với nhiều kiểu datetime:

```sql
SELECT event_id,
       EXTRACT(YEAR  FROM event_time) AS event_year,
       EXTRACT(MONTH FROM event_time) AS event_month,
       EXTRACT(DAY   FROM event_time) AS event_day_num
FROM demo_datetime_formats
ORDER BY event_id;
```

Khi cần giá trị số để tính toán, dùng API datetime/extract phù hợp, tránh chuyển cả giá trị thành chuỗi `TO_CHAR` rồi parse ngược sang số.

### Bước 7. Dọn bảng thử nghiệm

Sau khi chắc chắn bảng chỉ dùng cho bài tập và không có dữ liệu cần giữ:

```sql
DROP TABLE demo_datetime_formats PURGE;
```

Lệnh này xóa bảng và dữ liệu trong schema thực hành, bỏ qua recycle bin theo hành vi `PURGE`, và là DDL có commit ngầm. Không chạy ở môi trường dữ liệu thật.

## 15. Các lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng/lỗi | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| `ORA-01861: literal does not match format string` | Chuỗi ngày không khớp format được mong đợi | Xem đầu vào thật, chỉ định đúng `TO_DATE`/`TO_TIMESTAMP` format; dùng `FX` khi cần strict |
| `ORA-01843: not a valid month` | Vị trí tháng sai, giá trị tháng không hợp lệ hoặc tên tháng không phù hợp ngôn ngữ | Kiểm tra `MM`, `MON`, NLS language và dữ liệu thực |
| `ORA-01830: date format picture ends before converting entire input string` | Format model không mô tả hết chuỗi đầu vào | Bổ sung phần giờ/phút/giây hoặc sửa định dạng đầu vào |
| `ORA-01858: a non-numeric character was found where a numeric was expected` | Ký tự văn bản xuất hiện ở vị trí format yêu cầu số | Kiểm tra ký tự phân tách và phần tử số |
| `ORA-01847: day of month must be between 1 and last day of month` | Ngày trong tháng không tồn tại | Kiểm tra tính hợp lệ của ngày lịch |
| Dữ liệu lọc theo `DATE 'YYYY-MM-DD'` bị thiếu hàng | Cột `DATE` chứa giờ khác midnight, dùng `=` | Dùng `>= start AND < next_day` |
| Cùng một câu SQL chạy khác nhau trên hai môi trường | Dựa vào chuyển đổi ngầm hoặc NLS phiên khác nhau | Dùng literal chuẩn, format model tường minh và bind đúng kiểu |
| Thấy `14-NOV-26` trong client dù lưu năm 2026 | Định dạng hiển thị dùng năm hai chữ số | `TO_CHAR(value, 'YYYY-MM-DD HH24:MI:SS')` |
| Dữ liệu bị mất mili giây | Ép `TIMESTAMP` sang `DATE` hoặc dùng kiểu `DATE` | Chọn cột/kiểu `TIMESTAMP` và `FF` phù hợp |
| Hai nơi hiển thị giờ khác nhau | Timezone/session timezone hoặc kiểu `WITH LOCAL TIME ZONE` | Xác định kiểu dữ liệu, vùng/offset và timezone của session |
| Parse chuỗi `14-NOV-2026` thất bại trong phiên không dùng tiếng Anh | Tên tháng theo `NLS_DATE_LANGUAGE` | Truyền tham số NLS hoặc dùng format số |
| Báo cáo tháng bỏ sót ngày cuối | `BETWEEN` cận cuối ở midnight | Dùng khoảng nửa mở của tháng |
| `TO_DATE(date_column, ...)` trả sai hoặc lỗi | Chuyển ngầm DATE → text → DATE | Không parse lại giá trị đã có kiểu |

### Quy trình chẩn đoán từng bước

1. **Kiểu dữ liệu gốc là gì?** Kiểm tra `USER_TAB_COLUMNS.DATA_TYPE` hoặc `ALL_TAB_COLUMNS`, đừng chỉ nhìn chuỗi hiển thị trong công cụ.
2. **Chuỗi đến từ đâu?** Literal cố định trong SQL, CSV, HTTP request, hay biến bind của Java? Nếu đã là kiểu datetime, thường không cần `TO_DATE`.
3. **Format đầu vào đã nêu đủ thành phần chưa?** So khớp năm, tháng, ngày, giờ 12/24, phút, giây, phần lẻ giây và timezone.
4. **Có phụ thuộc NLS không?** Kiểm tra các tham số ngày giờ của phiên, đặc biệt khi sử dụng tên tháng hoặc chuyển đổi ngầm.
5. **Ý nghĩa nghiệp vụ là ngày lịch hay mốc thời gian tuyệt đối?** Chọn `DATE`/`TIMESTAMP` hoặc timezone-aware type phù hợp.
6. **Điều kiện lọc có bao gồm toàn bộ khoảng thời gian không?** Với dữ liệu có phần giờ, ưu tiên cận bắt đầu `>=` và cận kết thúc `<`.

## 16. Bộ quy ước đề xuất cho SQL và hệ thống ứng dụng

Trong các dự án Oracle kết nối với Java, nên ghi rõ hợp đồng dữ liệu ở tầng API, tầng database và tầng hiển thị:

| Trường hợp | Cách biểu diễn/giao tiếp gợi ý | Lý do |
|---|---|---|
| Mốc ngày cố định trong SQL | `DATE 'YYYY-MM-DD'` | Rõ ràng, không phụ thuộc `NLS_DATE_FORMAT` |
| Timestamp cố định không timezone | `TIMESTAMP 'YYYY-MM-DD HH24:MI:SS.FF'` | Có phần lẻ giây, không cần parse theo NLS |
| Chuỗi ngày do người dùng nhập | `TO_DATE(text, 'FXDD/MM/YYYY')` nếu giao diện đã quy định mẫu | Parser có hợp đồng rõ và có thể kiểm tra chặt |
| Chuỗi thời gian có phần lẻ giây | `TO_TIMESTAMP(text, 'YYYY-MM-DD HH24:MI:SS.FF6')` | Không mất phần lẻ giây |
| Chuỗi thời điểm kèm offset | `TO_TIMESTAMP_TZ(text, 'YYYY-MM-DD HH24:MI:SS TZH:TZM')` | Tránh mất thông tin timezone |
| Trình bày báo cáo | `TO_CHAR(value, 'DD/MM/YYYY HH24:MI:SS')` hoặc format cụ thể | Chuyển kiểu chỉ ở ranh giới hiển thị |
| Lọc ngày | `>= start AND < end` | Bao gồm đúng khoảng, kể cả giờ/phần lẻ giây |
| Ứng dụng Java/JDBC | Bind kiểu `LocalDate`, `LocalDateTime`, `OffsetDateTime` theo schema/driver | Không phải ghép chuỗi SQL hay dựa vào NLS |
| Tích hợp đa vùng | Chuẩn hóa timestamp với offset/UTC và lưu region riêng nếu lịch tương lai cần quy tắc DST | Giữ đúng ý nghĩa một thời điểm |

### Những câu nên tránh

```sql
-- 1. So sánh DATE với chuỗi theo format phụ thuộc session:
-- WHERE created_at = '14/11/2026'

-- 2. Lọc ngày bằng TO_CHAR trên cột:
-- WHERE TO_CHAR(created_at, 'DD/MM/YYYY') = '14/11/2026'

-- 3. Dùng TO_DATE để parse lại giá trị DATE đã có sẵn:
-- SELECT TO_DATE(created_at, 'YYYY-MM-DD') FROM orders

-- 4. Nhầm MM (tháng) với MI (phút):
-- TO_DATE('14/11/2026 16:30', 'DD/MM/YYYY HH24:MM')

-- 5. Giả định DATE không chứa phần giờ:
-- WHERE created_at = DATE '2026-11-14'
```

Viết lại bằng literal chuẩn hoặc bind đúng kiểu, với mẫu ngày giờ thể hiện đầy đủ ý nghĩa nghiệp vụ.

## 17. Tự kiểm tra kiến thức

**Câu 1.** `DATE '2026-11-14'` có chứa phần giờ không?

**Đáp án:** Có. Kiểu `DATE` của Oracle chứa ngày và giờ đến giây; literal chỉ định ngày tạo giá trị lúc 00:00:00.

**Câu 2.** `'14/11/2026'` có phải kiểu DATE không?

**Đáp án:** Không, đó là chuỗi. Muốn tạo DATE tường minh dùng `TO_DATE('14/11/2026', 'DD/MM/YYYY')` hoặc đổi cách biểu diễn để dùng `DATE '2026-11-14'`.

**Câu 3.** Format `'YYYY-MM-DD HH24:MM:SS'` sai ở đâu khi muốn đọc 16 giờ 30 phút?

**Đáp án:** `MM` là tháng; `MI` mới là phút. Format đúng là `'YYYY-MM-DD HH24:MI:SS'`.

**Câu 4.** `TO_DATE('2026-11-14 16:30:45.123', 'YYYY-MM-DD HH24:MI:SS.FF3')` có thích hợp không?

**Đáp án:** Không. `DATE` không lưu phần lẻ giây; dùng `TO_TIMESTAMP(..., 'YYYY-MM-DD HH24:MI:SS.FF3')` khi cần mili giây.

**Câu 5.** Vì sao `WHERE created_at = DATE '2026-11-14'` thường không lọc hết các hàng trong ngày?

**Đáp án:** Vì literal là 00:00:00, còn cột có thể chứa các giờ khác. Dùng khoảng nửa mở từ midnight ngày 14 đến trước midnight ngày 15.

**Câu 6.** `TO_CHAR` và `TO_DATE` hoạt động theo hướng nào?

**Đáp án:** `TO_CHAR(datetime, fmt)` biến giá trị thời gian thành chuỗi hiển thị; `TO_DATE(text, fmt)` chuyển chuỗi thành giá trị kiểu DATE.

**Câu 7.** `FX` và `FM` khác nhau thế nào?

**Đáp án:** `FX` yêu cầu khớp chính xác format khi đọc đầu vào; `FM` kiểm soát phần điền/đệm ở biểu diễn định dạng.

**Câu 8.** Cần xử lý chuỗi có tên tháng tiếng Anh trong phiên có ngôn ngữ khác. Làm gì?

**Đáp án:** Chỉ định `NLS_DATE_LANGUAGE=ENGLISH` trong hàm chuyển đổi hỗ trợ, hoặc tốt hơn là quy định đầu vào chỉ dùng số năm-tháng-ngày nếu bạn kiểm soát giao thức.

**Câu 9.** `TIMESTAMP '2026-11-14 16:30:00'` đã cho biết đó là giờ Việt Nam chưa?

**Đáp án:** Chưa. Đây là timestamp **không kèm múi giờ**. Nếu là thời điểm tuyệt đối, cần thông tin offset/region hoặc hợp đồng timezone bên ngoài.

**Câu 10.** Một ứng dụng Java nhận `LocalDate` từ người dùng và lưu vào Oracle. Có bắt buộc format thành `DD/MM/YYYY` rồi đưa vào câu SQL không?

**Đáp án:** Không. Nên bind giá trị thời gian qua JDBC API phù hợp với cột và driver, thay vì tự ghép chuỗi ngày giờ vào SQL.

**Câu 11.** `SYSDATE` và `CURRENT_DATE` có thể trả về ngày/giờ khác nhau không?

**Đáp án:** Có, do ngữ cảnh đồng hồ/hệ thống database và timezone của session. Cả hai trả kiểu `DATE`, không kèm thông tin timezone trong giá trị trả về.

**Câu 12.** Vì sao không nên gắn `'Z'` vào chuỗi thời gian địa phương để gọi nó là UTC?

**Đáp án:** `Z` có nghĩa là UTC trong cách biểu diễn thời gian tương ứng. Nếu giá trị thực tế chưa chuyển sang UTC, thêm ký hiệu đó chỉ làm sai ý nghĩa thời điểm.

## 18. Kết luận

**Literal ngày giờ** như `DATE '2026-11-14'` và `TIMESTAMP '2026-11-14 16:30:45.123'` tạo giá trị có kiểu ngay trong SQL và tránh phụ thuộc định dạng ngày giờ mặc định của phiên Oracle. Khi phải đọc **văn bản**, hãy chọn `TO_DATE`, `TO_TIMESTAMP` hoặc `TO_TIMESTAMP_TZ` với **format model tường minh**, dùng `FX` khi cần kiểm tra cấu trúc nghiêm ngặt, và chỉ định ngôn ngữ NLS nếu biểu thức chứa tên tháng/thứ.

Để xuất dữ liệu hoặc hiển thị cho người dùng, `TO_CHAR(datetime, format)` là công cụ định dạng, nhưng việc lưu trữ và so sánh trong database vẫn nên dùng **giá trị kiểu thời gian**. Phân biệt `DATE` có giờ đến giây, `TIMESTAMP` có phần lẻ giây và các kiểu timestamp có timezone sẽ giúp bạn tránh việc diễn giải sai một mốc thời gian. Trong truy vấn lọc ngày, dùng **khoảng nửa mở**; trong Java, **bind tham số có kiểu** thay vì ghép chuỗi và trông đợi NLS xử lý.

