# DATE, TIMESTAMP và các kiểu dữ liệu có múi giờ trong Oracle Database

Một ứng dụng đặt vé có thể ghi “khởi hành lúc **09:30 ngày 14/11/2026 tại Thành phố Hồ Chí Minh**”. Một hệ thống thanh toán khác ghi “giao dịch hoàn tất lúc **02:30 UTC**”. Hai giá trị có thể mô tả **cùng một thời điểm thực** nhưng cách lưu và ý nghĩa nghiệp vụ khác nhau. Nếu chỉ chọn kiểu dữ liệu vì nó có chữ “date” hoặc “timestamp”, ứng dụng dễ gặp lỗi khi đổi múi giờ, dùng daylight saving time (DST), so sánh dữ liệu từ nhiều quốc gia hoặc tính khoảng thời gian.

Oracle Database có bốn kiểu ngày giờ thường dùng:

- `DATE`.
- `TIMESTAMP[(fractional_seconds_precision)]`.
- `TIMESTAMP[(fractional_seconds_precision)] WITH TIME ZONE`.
- `TIMESTAMP[(fractional_seconds_precision)] WITH LOCAL TIME ZONE`.

Điểm phân biệt không chỉ là **có bao nhiêu chữ số phần giây** mà còn là **có gắn ngữ nghĩa múi giờ không, có giữ thông tin múi giờ gốc không, và kết quả hiển thị thay đổi thế nào theo session**. Bài học xây dựng mô hình lựa chọn kiểu, hướng dẫn literal và hàm chuyển đổi, minh họa SQL có thể thực hành, đồng thời giải thích những bẫy như NLS, DST, implicit conversion và tích hợp Java/JDBC.

## 1. Ba khái niệm: ngày lịch, giờ trên đồng hồ và thời điểm tuyệt đối

Trước khi chọn kiểu Oracle, cần làm rõ dữ liệu biểu diễn cái gì.

**Ngày lịch (calendar date)** là ngày như “2026-11-14”; thường dùng cho sinh nhật, ngày hóa đơn, ngày đóng kỳ kế toán. Ngày lịch **không bắt buộc** gắn với một thời điểm chính xác trên trục thời gian toàn cầu.

**Giờ địa phương (wall-clock datetime)** là “2026-11-14 09:30:00”, nghĩa là đồng hồ ở một nơi hoặc trong một quy tắc nghiệp vụ hiển thị 09:30. Không biết múi giờ thì chưa thể suy ra UTC.

**Thời điểm tuyệt đối (instant)** là một điểm cụ thể trên trục thời gian, ví dụ 2026-11-14 02:30 UTC. Tại cùng thời điểm đó, đồng hồ ở Việt Nam (UTC+07:00) chỉ 09:30.

~~~text
                    CÙNG MỘT THỜI ĐIỂM

UTC                       2026-11-14 02:30:00 +00:00
Việt Nam (UTC+07:00)       2026-11-14 09:30:00 +07:00

                    KHÁC CÁCH BIỂU DIỄN
~~~

Nếu chỉ lưu `2026-11-14 09:30:00` vào một cột không có múi giờ, dữ liệu **không nói được** nó là 09:30 ở Việt Nam, New York hay tại múi giờ máy chủ.

### 1.1 Time zone offset khác time zone region

**Offset** là độ lệch so với UTC tại một thời điểm: `+07:00`, `-05:00`, `+00:00`.

**Region** là tên vùng có quy tắc giờ theo lịch sử và pháp lý, ví dụ `Asia/Ho_Chi_Minh`, `America/New_York` hoặc `Europe/Paris`. Vùng có thể thay đổi offset theo ngày do DST hoặc thay đổi luật địa phương. Một offset `-05:00` **không xác định duy nhất** region nào đã tạo ra offset đó.

Ví dụ:

~~~text
2026-01, America/New_York: có thể dùng UTC-05:00
2026-07, America/New_York: có thể dùng UTC-04:00
~~~

Muốn đặt một lịch hẹn lặp mỗi ngày lúc 09:00 tại New York, thường phải lưu **region** để biết luật offset theo ngày. Chỉ lưu offset hiện tại không đủ mô tả toàn bộ lịch tương lai.

## 2. Bảng so sánh bốn kiểu Oracle

| Kiểu | Độ chính xác thời gian | Thông tin múi giờ trong giá trị | Ngữ nghĩa khi đọc | Tình huống phù hợp |
|---|---|---|---|---|
| `DATE` | Đến **giây**, không có phần giây | Không có | Giữ nguyên các thành phần ngày-giờ đã lưu | Ngày nghiệp vụ, giá trị giờ không cần mili giây và múi giờ được quy ước bên ngoài |
| `TIMESTAMP(p)` | Có phần giây, `p` từ 0 đến 9; mặc định thường 6 | Không có | Giữ nguyên ngày-giờ và phần giây | Thời gian địa phương với độ chính xác cao, dữ liệu đã có ngữ nghĩa múi giờ ở nơi khác |
| `TIMESTAMP(p) WITH TIME ZONE` | Có phần giây | Có **offset hoặc region** gắn với giá trị | Biểu diễn một instant và thông tin zone gắn với giá trị theo dạng được lưu | Sự kiện từ nhiều múi giờ, kiểm toán cần offset/region, lịch thời điểm tuyệt đối |
| `TIMESTAMP(p) WITH LOCAL TIME ZONE` | Có phần giây | Không giữ zone gốc trong từng giá trị | Oracle chuẩn hóa khi lưu rồi chuyển sang **session time zone** khi đọc | Instant cần hiển thị theo múi giờ session/người dùng, không cần tái tạo zone gốc |

`p` là độ chính xác **phần giây**. Ví dụ `TIMESTAMP(3)` có độ chính xác đến mili giây; `TIMESTAMP(6)` đến micro giây; `TIMESTAMP(9)` đến nano giây về biểu diễn. Độ phân giải thực tế của nguồn thời gian, hệ điều hành, driver và ứng dụng có thể thấp hơn độ chính xác cột khai báo.

**Cảnh báo dễ nhầm:** `DATE` của Oracle **có cả giờ, phút, giây**; nó không tương đương hoàn toàn với kiểu chỉ lưu ngày lịch trong một số hệ quản trị khác. Và `TIMESTAMP` mặc định **không mang múi giờ**.

## 3. DATE: lưu ngày và giờ đến giây

Oracle `DATE` lưu các thành phần **năm, tháng, ngày, giờ, phút và giây**, không lưu fractional seconds hay time zone. Dạng lưu trữ nội bộ của Oracle DATE thông thường dùng 7 byte.

### 3.1 Literal DATE và thời điểm nửa đêm

~~~sql
SELECT DATE '2026-11-14' AS calendar_start
FROM dual;
~~~

Literal theo cú pháp `DATE 'YYYY-MM-DD'` tạo giá trị ngày với phần thời gian **00:00:00**. Nó rất hữu ích để tránh phụ thuộc `NLS_DATE_FORMAT` của session.

Nhưng literal DATE không chứa giờ khác nửa đêm:

~~~sql
SELECT TO_DATE(
         '2026-11-14 09:30:45',
         'YYYY-MM-DD HH24:MI:SS'
       ) AS event_local_date
FROM dual;
~~~

`TO_DATE` chuyển **chuỗi** thành Oracle DATE theo format model rõ ràng. Giá trị kết quả vẫn không có múi giờ. Nếu một giao dịch diễn ra ở Việt Nam, ứng dụng phải xác định và thống nhất quy ước “giờ trong cột DATE là giờ địa phương Việt Nam” hoặc “DATE này là UTC”; chỉ nhìn kiểu dữ liệu không thể biết điều đó.

### 3.2 Vì sao nhìn DATE không thấy giờ?

Truy vấn:

~~~sql
SELECT TO_DATE('2026-11-14 09:30:45', 'YYYY-MM-DD HH24:MI:SS')
FROM dual;
~~~

có thể chỉ hiển thị `14-NOV-26` hoặc một chuỗi ngày khác, tùy cấu hình `NLS_DATE_FORMAT` của session/client. **Phần giờ có thể vẫn được lưu đầy đủ**, chỉ là định dạng hiển thị không in ra.

Muốn hiển thị rõ:

~~~sql
SELECT TO_CHAR(
         TO_DATE('2026-11-14 09:30:45', 'YYYY-MM-DD HH24:MI:SS'),
         'YYYY-MM-DD HH24:MI:SS'
       ) AS date_text
FROM dual;
~~~

`TO_CHAR` trả về **chuỗi**. Nó không thay đổi cách giá trị DATE được lưu. Nên phân biệt ba lớp: **giá trị trong database**, **kiểu dữ liệu của biểu thức**, **cách client hiển thị**.

### 3.3 Phép toán với DATE

Trong Oracle, trừ hai giá trị DATE trả về **NUMBER tính theo ngày**:

~~~sql
SELECT
    TO_DATE('2026-11-14 12:00:00', 'YYYY-MM-DD HH24:MI:SS')
  - TO_DATE('2026-11-14 09:00:00', 'YYYY-MM-DD HH24:MI:SS')
    AS difference_in_days
FROM dual;
~~~

Kết quả ý niệm là `0.125` ngày, tức 3 giờ.

Một số phép cộng:

~~~sql
SELECT DATE '2026-11-14' + 1       AS next_day,
       DATE '2026-11-14' + (1/24)  AS one_hour_later
FROM dual;
~~~

Ở đây `1` tương đương một ngày trong phép cộng số với DATE, còn `1/24` là một giờ tính theo ngày. Cách tính này phù hợp với Oracle DATE như giá trị ngày-giờ không có zone; nó **không tự xử lý** những chuyển đổi đồng hồ DST của một region bên ngoài.

### 3.4 DATE có nên dùng cho sinh nhật?

Sinh nhật là **ngày lịch**, nhưng Oracle không có một kiểu `DATE_ONLY` tách khỏi time-of-day. Có thể dùng `DATE` với quy ước giờ luôn là nửa đêm và kiểm soát nhập dữ liệu; hoặc lưu thành phần ngày/tháng/năm theo mô hình nghiệp vụ khác nếu thực sự cần.

Điều cần đảm bảo là **không vô tình biến ngày lịch thành instant rồi đổi múi giờ**: “sinh ngày 14/11” không có nghĩa sinh vào 00:00 UTC và có thể bị hiển thị thành 13/11 ở quốc gia khác.

## 4. TIMESTAMP: thêm độ chính xác phần giây, vẫn không có time zone

`TIMESTAMP(p)` mở rộng khả năng biểu diễn phần giây. Ví dụ:

~~~sql
SELECT TIMESTAMP '2026-11-14 09:30:45.123456'
       AS local_event_timestamp
FROM dual;
~~~

Literal này chứa năm-tháng-ngày, giờ-phút-giây và phần giây `.123456`. **Không có thông tin múi giờ** trong bản thân giá trị.

### 4.1 Chọn precision

~~~sql
CREATE TABLE event_precision_lab (
    event_id  NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    ts_millis TIMESTAMP(3),
    ts_micros TIMESTAMP(6),
    ts_nanos  TIMESTAMP(9)
);
~~~

| Precision | Mức biểu diễn | Ví dụ phần giây |
|---|---|---|
| `TIMESTAMP(0)` | Không có phần giây | `09:30:45` |
| `TIMESTAMP(3)` | Mili giây | `09:30:45.123` |
| `TIMESTAMP(6)` | Micro giây | `09:30:45.123456` |
| `TIMESTAMP(9)` | Nano giây | `09:30:45.123456789` |

Chỉ tăng precision không làm mọi nguồn dữ liệu tự có độ chính xác cao hơn. Ví dụ một nguồn chỉ cung cấp giây sẽ không có nano giây có ý nghĩa, dù cột khai báo `TIMESTAMP(9)`.

### 4.2 TO_TIMESTAMP cho chuỗi có phần giây

~~~sql
SELECT TO_TIMESTAMP(
         '2026-11-14 09:30:45.123456',
         'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS parsed_ts
FROM dual;
~~~

`FF6` cho biết phần giây với precision tương ứng. Với `TIMESTAMP`, không dùng `TZH:TZM` hay `TZR` để “thêm zone” vào giá trị: các thông tin này thuộc kiểu **TIMESTAMP WITH TIME ZONE**.

### 4.3 DATE và TIMESTAMP có thể trông giống nhau

Nếu chỉ dùng:

~~~sql
SELECT TO_CHAR(
         TIMESTAMP '2026-11-14 09:30:45.123456',
         'YYYY-MM-DD HH24:MI:SS'
       ) AS text_without_fraction
FROM dual;
~~~

ta sẽ không thấy phần giây lẻ vì format model đã bỏ qua nó. Phải hiển thị `FF` khi cần:

~~~sql
SELECT TO_CHAR(
         TIMESTAMP '2026-11-14 09:30:45.123456',
         'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS text_with_fraction
FROM dual;
~~~

**TIMESTAMP không tự biết UTC hay giờ địa phương.** Nếu đội phát triển quy ước mọi TIMESTAMP đều biểu diễn UTC, đó là một **quy ước ứng dụng** phải được bảo vệ bằng API, kiểm thử, schema documentation và việc chuyển đổi tại biên hệ thống.

## 5. TIMESTAMP WITH TIME ZONE: một instant có zone gắn với giá trị

`TIMESTAMP(p) WITH TIME ZONE` (viết tắt **TSTZ**) biểu diễn ngày giờ kèm thông tin time zone: có thể dưới dạng **UTC offset** hoặc **time zone region**. Oracle có thể so sánh các giá trị theo **thời điểm thực tương ứng** sau khi tính đến offset.

### 5.1 Tạo TSTZ từ chuỗi có offset

~~~sql
SELECT TO_TIMESTAMP_TZ(
         '2026-11-14 09:30:00.123456 +07:00',
         'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
       ) AS payment_time
FROM dual;
~~~

Ở đây:

- `2026-11-14 09:30:00.123456`: giờ được diễn đạt tại offset đã chỉ ra.
- `+07:00`: thời điểm này sớm hơn UTC 7 giờ theo cách tính local − UTC.
- Instant tương ứng: `2026-11-14 02:30:00.123456 UTC`.

Có thể chứng minh hai biểu diễn mô tả cùng thời điểm:

~~~sql
SELECT CASE
         WHEN TO_TIMESTAMP_TZ(
                '2026-11-14 09:30:00 +07:00',
                'YYYY-MM-DD HH24:MI:SS TZH:TZM'
              )
              =
              TO_TIMESTAMP_TZ(
                '2026-11-14 02:30:00 +00:00',
                'YYYY-MM-DD HH24:MI:SS TZH:TZM'
              )
         THEN 'SAME INSTANT'
         ELSE 'DIFFERENT INSTANT'
       END AS comparison_result
FROM dual;
~~~

Phép so sánh bằng cho kết quả `SAME INSTANT` vì cùng mốc UTC. Điều này khác so sánh hai `TIMESTAMP` không có zone: với timestamp thuần, `09:30` và `02:30` đơn thuần là hai giá trị đồng hồ khác nhau.

### 5.2 Tạo TSTZ với region bằng FROM_TZ

`FROM_TZ` nhận một `TIMESTAMP` không có zone và **gắn vùng/offset được chỉ định**, trả về giá trị TSTZ:

~~~sql
SELECT FROM_TZ(
         TIMESTAMP '2026-11-14 09:30:00',
         'Asia/Ho_Chi_Minh'
       ) AS vietnam_instant
FROM dual;
~~~

Region phải là tên được **time zone file** của Oracle hỗ trợ. Oracle dùng bộ quy tắc time zone trong time zone file; danh sách region và các quy tắc có thể khác theo phiên bản file.

`FROM_TZ` là thao tác **diễn giải** một wall-clock time ở vùng đã biết. Nó khác với **chuyển đổi** một instant vốn đã có zone sang vùng khác.

### 5.3 Chuyển instant sang múi giờ khác với AT TIME ZONE

~~~sql
SELECT TO_CHAR(
         FROM_TZ(
           TIMESTAMP '2026-11-14 09:30:00',
           'Asia/Ho_Chi_Minh'
         ) AT TIME ZONE 'UTC',
         'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       ) AS utc_display
FROM dual;
~~~

Kết quả ý niệm: `2026-11-14 02:30:00 +00:00`.

Luồng xử lý:

~~~text
TIMESTAMP không có zone: 2026-11-14 09:30
       |
       | FROM_TZ(..., 'Asia/Ho_Chi_Minh')
       v
TSTZ: 2026-11-14 09:30 theo Việt Nam
       |
       | AT TIME ZONE 'UTC'
       v
TSTZ: 2026-11-14 02:30 theo UTC
~~~

Ở bước cuối, **instant vẫn là một**, chỉ cách diễn đạt theo đồng hồ ở time zone khác nhau.

### 5.4 Giữ region hay chỉ giữ offset?

Ví dụ nhập `2026-11-14 09:30 +07:00` chỉ cho biết offset; không đủ để kết luận người dùng chọn region `Asia/Ho_Chi_Minh`. Nếu nghiệp vụ cần phân biệt **nơi/vùng tổ chức lịch hẹn**, cần lưu region chính xác hoặc một trường metadata nghiệp vụ riêng.

TSTZ có thể mang thông tin zone dưới dạng offset hoặc region tùy cách tạo/nhập. Khi qua driver, API hoặc phép CAST/format, cần kiểm tra việc bảo toàn region gốc. Không suy từ “cột TSTZ” rằng mọi đường tích hợp đều giữ lại đúng tên region mà người dùng nhập.

## 6. TIMESTAMP WITH LOCAL TIME ZONE: lưu instant, hiển thị theo session

`TIMESTAMP(p) WITH LOCAL TIME ZONE` (viết tắt **TSLTZ**) có cách hoạt động khác TSTZ:

1. Khi lưu, Oracle nhận giá trị với ngữ nghĩa thời điểm, **chuẩn hóa** theo database time zone để lưu nội bộ.
2. Khi truy vấn, Oracle **chuyển đổi giá trị sang session time zone** đang dùng.
3. **Không lưu time zone gốc cho từng giá trị**, nên không thể chỉ đọc cột TSLTZ để biết người nhập đã dùng region hay offset nào.

### 6.1 Thử nghiệm ý niệm với hai session time zone

Giả sử có bảng:

~~~sql
CREATE TABLE tz_local_lab (
    event_id    NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    occurred_at TIMESTAMP(6) WITH LOCAL TIME ZONE
);
~~~

Ghi một thời điểm rõ offset:

~~~sql
INSERT INTO tz_local_lab (occurred_at)
VALUES (
    TO_TIMESTAMP_TZ(
      '2026-11-14 09:30:00 +07:00',
      'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    )
);

COMMIT;
~~~

Đọc trong một session đặt time zone `+07:00`:

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';

SELECT TO_CHAR(
         occurred_at,
         'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS displayed_local_time
FROM tz_local_lab;
~~~

Kết quả ý niệm là `2026-11-14 09:30:00.000000`.

Đổi session sang UTC:

~~~sql
ALTER SESSION SET TIME_ZONE = '+00:00';

SELECT TO_CHAR(
         occurred_at,
         'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS displayed_local_time
FROM tz_local_lab;
~~~

Giá trị được hiển thị là `2026-11-14 02:30:00.000000`. **Dữ liệu logic về instant không thay đổi**; chỉ múi giờ session thay đổi cách hiển thị.

### 6.2 Database time zone và session time zone

Hai tham số quan trọng:

~~~sql
SELECT DBTIMEZONE      AS database_tz,
       SESSIONTIMEZONE AS session_tz
FROM dual;
~~~

- `DBTIMEZONE`: múi giờ cơ sở dữ liệu sử dụng trong các quy tắc liên quan, đặc biệt chuẩn hóa TSLTZ khi lưu.
- `SESSIONTIMEZONE`: múi giờ được session dùng khi hiển thị TSLTZ và khi tính một số hàm ngày giờ.

**DBTIMEZONE không nhất thiết giống múi giờ hệ điều hành của máy chủ**, và không phải múi giờ người dùng cuối. Việc thay đổi database time zone có điều kiện nghiêm ngặt, đặc biệt nếu có cột TSLTZ, vì nó ảnh hưởng ngữ nghĩa lưu trữ; không nên dùng thao tác thay DBTIMEZONE để chỉnh giờ hiển thị của một session.

### 6.3 Ưu điểm và giới hạn TSLTZ

Ưu điểm:

- Nhiều người dùng có thể xem **cùng một instant** theo múi giờ session của mình.
- Không cần ứng dụng tự tạo một cột hiển thị theo mọi region để lưu cùng sự kiện.
- Hữu ích cho các event toàn cầu khi chỉ cần thời điểm và giờ local tại phiên truy cập.

Giới hạn:

- Không giữ lại region/offset do nguồn cung cấp.
- Kết quả văn bản có thể khác giữa hai session, tạo khó khăn khi xuất log, báo cáo hoặc kiểm thử nếu session timezone chưa được kiểm soát.
- Nếu cần lịch “09:00 mỗi ngày tại New York”, TSLTZ không tự thay thế việc lưu **time zone region** và quy tắc lặp lịch.

**TSLTZ khác TIMESTAMP thường:** cùng một giá trị lưu có thể **hiển thị khác nhau ở các session**, còn TIMESTAMP thuần không tự đổi theo session time zone.

## 7. Các hàm thời gian hiện tại dễ nhầm trong Oracle

Oracle có nhiều hàm “thời gian hiện tại”, nhưng kiểu trả về và cơ sở timezone khác nhau.

| Biểu thức | Kiểu giá trị trả về | Time zone/nguồn thời gian |
|---|---|---|
| `SYSDATE` | `DATE` | Giờ hệ thống của máy chủ database theo cấu hình môi trường, không có phần giây lẻ hay zone trong giá trị |
| `SYSTIMESTAMP` | `TIMESTAMP WITH TIME ZONE` | Timestamp của hệ thống database kèm fractional seconds và thông tin offset/time zone |
| `CURRENT_DATE` | `DATE` | Ngày-giờ hiện tại **theo session time zone**, làm tròn ở mức giây của DATE |
| `CURRENT_TIMESTAMP` | `TIMESTAMP WITH TIME ZONE` | Timestamp hiện tại **theo session time zone** |
| `LOCALTIMESTAMP` | `TIMESTAMP` | Timestamp hiện tại **theo session time zone**, nhưng bỏ thông tin time zone khỏi kiểu |
| `DBTIMEZONE` | Giá trị biểu thị zone | Múi giờ database; không phải đồng hồ hiện tại |
| `SESSIONTIMEZONE` | Giá trị biểu thị zone | Múi giờ session; không phải đồng hồ hiện tại |

Ví dụ quan sát:

~~~sql
SELECT
    TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS')          AS sys_date_text,
    TO_CHAR(SYSTIMESTAMP,
            'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM')       AS system_ts_text,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS')     AS current_date_text,
    TO_CHAR(CURRENT_TIMESTAMP,
            'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM')       AS current_ts_text,
    TO_CHAR(LOCALTIMESTAMP,
            'YYYY-MM-DD HH24:MI:SS.FF6')               AS local_ts_text,
    DBTIMEZONE                                         AS db_tz,
    SESSIONTIMEZONE                                    AS session_tz
FROM dual;
~~~

Các phép gọi được thực hiện gần cùng thời điểm nhưng có thể lệch rất nhỏ vì quá trình lấy thời gian/hiển thị; không thiết kế kiểm thử yêu cầu các giá trị từ nhiều hàm luôn trùng chính xác đến micro giây.

### 7.1 Vì sao SYSDATE và CURRENT_DATE khác nhau?

Giả sử database server chạy ở UTC, còn session đặt `+07:00`. Khi cùng một instant:

~~~text
SYSDATE        có thể hiển thị   02:30  (giờ hệ thống database)
CURRENT_DATE   có thể hiển thị   09:30  (giờ session)
~~~

Hai hàm không chỉ khác cách format; chúng lấy giá trị theo cơ sở thời gian khác nhau. Vì kiểu DATE không chứa timezone, phép so sánh trực tiếp giữa các giá trị này như hai thời điểm độc lập có thể dẫn đến hiểu sai.

### 7.2 Chọn giá trị mặc định cột

Một bảng lưu sự kiện toàn cầu có thể dùng:

~~~sql
CREATE TABLE audit_event (
    event_id    NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    occurred_at TIMESTAMP(6) WITH TIME ZONE
                DEFAULT SYSTIMESTAMP NOT NULL,
    event_type  VARCHAR2(40) NOT NULL
);
~~~

`SYSTIMESTAMP` trả về TSTZ, phù hợp để ghi nhận thời điểm theo nguồn đồng hồ database. Nhưng ứng dụng có thể có thêm thời điểm sự kiện **do nguồn phát sinh**, khác thời điểm database nhận, và cần lưu hai cột riêng.

Một lựa chọn khác là dùng `CURRENT_TIMESTAMP` nếu nghiệp vụ muốn giá trị TSTZ theo session, với điều kiện ứng dụng kiểm soát session time zone. Không có một default duy nhất đúng cho mọi loại timestamp.

## 8. Chuyển đổi chuỗi và định dạng theo NLS

Các hàm thường dùng:

| Hàm | Chuyển đổi | Ví dụ format đặc trưng |
|---|---|---|
| `TO_DATE(text, format)` | Chuỗi → DATE | `YYYY-MM-DD HH24:MI:SS` |
| `TO_TIMESTAMP(text, format)` | Chuỗi → TIMESTAMP | `YYYY-MM-DD HH24:MI:SS.FF6` |
| `TO_TIMESTAMP_TZ(text, format)` | Chuỗi → TSTZ | `YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM` hoặc `TZR` |
| `TO_CHAR(datetime, format)` | Ngày giờ → chuỗi | Tạo biểu diễn nhất quán để log, xuất dữ liệu |
| `CAST(value AS datetime_type)` | Chuyển kiểu | Có thể mất thông tin phần giây/zone tùy loại đích |
| `FROM_TZ(timestamp, zone)` | Gắn zone cho TIMESTAMP thuần | Nhận timestamp và offset/region đã biết |
| `AT TIME ZONE` | Biểu diễn một datetime có zone trong zone khác | Dùng cho TSTZ sau khi đã gắn ngữ nghĩa zone |

### 8.1 Format model cơ bản

~~~sql
SELECT
    TO_DATE('2026-11-14 09:30:45',
            'YYYY-MM-DD HH24:MI:SS') AS d,
    TO_TIMESTAMP('2026-11-14 09:30:45.987654',
                 'YYYY-MM-DD HH24:MI:SS.FF6') AS ts,
    TO_TIMESTAMP_TZ('2026-11-14 09:30:45.987654 +07:00',
                    'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM') AS tstz
FROM dual;
~~~

Ý nghĩa một số ký hiệu:

- `YYYY`: năm bốn chữ số.
- `MM`: tháng số; `DD`: ngày trong tháng.
- `HH24`: giờ theo định dạng 24 giờ; `MI`: phút; `SS`: giây.
- `FFn`: phần giây, ví dụ `FF3` hoặc `FF6` trong TIMESTAMP.
- `TZH:TZM`: thành phần offset giờ/phút.
- `TZR`: time zone region; `TZD`: dạng viết tắt daylight/standard time dùng khi cần phân biệt ở những vùng hỗ trợ.

Hãy dùng format model **có nghĩa rõ**, đặc biệt phân biệt `MI` (minute) với `MM` (month). Nhiều lỗi dữ liệu phát sinh chỉ vì nhầm hai ký hiệu này.

### 8.2 Không phụ thuộc chuyển đổi ngầm

Ví dụ không nên dùng:

~~~sql
-- Không nên: phụ thuộc NLS_DATE_FORMAT của session.
WHERE created_at = '14/11/2026'
~~~

Vì `created_at` là DATE, Oracle có thể tự chuyển chuỗi sang DATE theo NLS hiện hành. Nếu đổi môi trường, ngày có thể bị đọc sai hoặc truy vấn báo lỗi.

Nên viết:

~~~sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
~~~

hoặc:

~~~sql
WHERE created_at >= TO_DATE('2026-11-14', 'YYYY-MM-DD')
  AND created_at <  TO_DATE('2026-11-15', 'YYYY-MM-DD')
~~~

Đối với TIMESTAMP, dùng `TIMESTAMP '...'` hoặc bind parameter có đúng kiểu dữ liệu. Đối với TSTZ, gắn zone tường minh bằng `TO_TIMESTAMP_TZ` hoặc `FROM_TZ`.

### 8.3 NLS không thay đổi dữ liệu theo ý muốn

Các thiết lập `NLS_DATE_FORMAT`, `NLS_TIMESTAMP_FORMAT` và `NLS_TIMESTAMP_TZ_FORMAT` điều khiển **định dạng chuyển đổi/hiển thị mặc định** trong nhiều ngữ cảnh. Chúng **không tự gắn timezone** vào DATE/TIMESTAMP đã lưu.

Ví dụ thay đổi format hiển thị trong một session có thể làm cùng một DATE in ra dạng `14-NOV-26` hoặc `2026-11-14 09:30:00`. Điều đó không có nghĩa giá trị đã đổi thành một instant khác.

### 8.4 Chuyển DATE sang TIMESTAMP hoặc ngược lại

~~~sql
SELECT CAST(
         TO_DATE('2026-11-14 09:30:45',
                 'YYYY-MM-DD HH24:MI:SS')
         AS TIMESTAMP
       ) AS ts_from_date
FROM dual;
~~~

Khi chuyển DATE sang TIMESTAMP, phần giây lẻ không thể tự xuất hiện vì DATE không lưu nó.

Ngược lại:

~~~sql
SELECT CAST(
         TIMESTAMP '2026-11-14 09:30:45.123456'
         AS DATE
       ) AS date_from_ts
FROM dual;
~~~

Kết quả DATE không còn phần giây lẻ. Với kiểu có zone, các phép CAST có thể chuyển/mất thông tin zone theo ngữ cảnh và session; phải chỉ rõ semantics và kiểm thử trước khi dùng trong dữ liệu nghiệp vụ.

## 9. DST: khi đồng hồ địa phương bị nhảy hoặc lặp

**Daylight saving time** thay đổi offset theo mùa ở một số quốc gia. Tại thời điểm chuyển sang giờ mùa hè, đồng hồ có thể **nhảy qua** một khoảng (local time không tồn tại). Khi chuyển về giờ thường, một khoảng local time có thể **lặp hai lần** (local time mơ hồ).

Ví dụ ý niệm cho một region áp dụng DST:

~~~text
Spring forward:
01:59:59 -> 03:00:00
Khoảng 02:00 - 02:59 ở ngày đó không tồn tại.

Fall back:
01:59:59 -> 01:00:00
01:30 xảy ra hai lần nhưng là hai instant khác nhau.
~~~

Không phải mọi quốc gia hoặc mọi năm đều áp dụng quy tắc này; các quy tắc được quản lý trong time zone data của Oracle.

### 9.1 Vì sao offset không đủ cho lịch tương lai?

Lịch họp “09:00 mỗi thứ Hai tại New York” cần gắn với **region New York**. Tùy ngày, 09:00 có thể tương ứng UTC-05:00 hoặc UTC-04:00. Nếu lưu cứng offset `-05:00` cho mọi tuần, các cuộc họp mùa hè có thể lệch một giờ.

Thiết kế hợp lý cho lịch lặp thường lưu:

- Giờ trên đồng hồ, ví dụ `09:00`.
- Region theo quy tắc IANA/Oracle được hệ thống hỗ trợ, ví dụ `America/New_York`.
- Quy tắc lặp (ngày trong tuần, kỳ hạn, exceptions).
- Quy tắc giải quyết trường hợp giờ không tồn tại hoặc mơ hồ.

Sau đó tính **instant cho từng lần diễn ra** theo quy tắc thời gian tương ứng. Một cột TSTZ chứa instant của **một lần diễn ra** không tự chứa toàn bộ lịch lặp.

### 9.2 Đặt region/offset khi gặp giờ mơ hồ

Trong Oracle, chuyển một wall-clock time mơ hồ sang TSTZ với `TZR` có thể cần thêm thông tin `TZD` hoặc offset để xác định lần nào của một giờ địa phương được chọn. Một số hành vi còn liên quan tham số session `ERROR_ON_OVERLAP_TIME`.

Nguyên tắc an toàn:

1. Không tự đoán khi local time không tồn tại trong region đang xét.
2. Khi một local time xuất hiện hai lần, yêu cầu ngữ nghĩa đủ để chọn **đúng instant**, chẳng hạn zone + offset áp dụng cho lần đó.
3. Dùng region để tính lịch tương lai; dùng offset/instant rõ ràng để ghi sự kiện đã phát sinh.
4. Kiểm tra toàn bộ hệ thống khi nâng cấp dữ liệu quy tắc timezone hoặc di chuyển database.

Không nên đưa một giá trị mơ hồ vào DB và hy vọng Oracle “luôn chọn đúng lần” theo kỳ vọng của nghiệp vụ.

### 9.3 Oracle time zone file và thay đổi quy tắc

Oracle có bộ dữ liệu quy tắc múi giờ theo phiên bản. Thay đổi luật giờ mùa hè của một quốc gia có thể khiến việc chuyển region ↔ UTC khác nhau giữa các phiên bản time zone file.

DBA có thể kiểm tra phiên bản time zone file và các region bằng các dynamic view phù hợp (cần quyền), ví dụ:

~~~sql
SELECT filename, version
FROM v$timezone_file;

SELECT tzname
FROM v$timezone_names
WHERE tzname IN ('UTC', 'Asia/Ho_Chi_Minh', 'America/New_York')
ORDER BY tzname;
~~~

Nâng cấp timezone data của Oracle là một **thao tác vận hành cần quy trình riêng**, có thể liên quan tính năng `DBMS_DST` và dữ liệu TSTZ. Không tự áp dụng thay đổi này như một chỉnh sửa định dạng ngày thông thường.

## 10. So sánh, sắp xếp và trừ các giá trị có múi giờ

### 10.1 So sánh cùng instant

Như ví dụ phần 5, hai TSTZ mang offset khác nhau vẫn có thể bằng nhau nếu quy về cùng UTC. Vì vậy:

~~~text
09:30 +07:00  =  02:30 +00:00  (cùng instant)
09:30 TIMESTAMP khác 02:30 TIMESTAMP (khác wall-clock value)
~~~

**Ý nghĩa so sánh không giống nhau giữa kiểu có zone và không có zone.** Nếu dữ liệu đang lưu TIMESTAMP thuần nhưng một số hàng là UTC, một số là local time, phép `ORDER BY` có thể sắp thứ tự sai về thời gian thực.

### 10.2 Trừ TIMESTAMP khác trừ DATE

~~~sql
SELECT
    TIMESTAMP '2026-11-14 12:00:00'
  - TIMESTAMP '2026-11-14 09:30:00'
    AS difference_interval
FROM dual;
~~~

Trừ hai TIMESTAMP trả về **INTERVAL DAY TO SECOND**, không phải NUMBER số ngày như `DATE - DATE`.

Với TSTZ, phép tính độ chênh instant phải xét offset/zone. Chênh giữa hai wall-clock times tại cùng region qua ngày DST có thể không bằng số giờ mà đồng hồ hiển thị khi trừ hai timestamp không có zone.

### 10.3 Khoảng thời gian thực và ngày lịch khác nhau

Giả sử cần “hết hạn sau đúng **24 giờ**” kể từ một instant. Khi đó có thể cộng interval giờ/ngày trên cơ sở timestamp có zone hoặc xử lý instant UTC.

Nhưng yêu cầu “đến **09:00 giờ địa phương ngày mai**” là phép tính **lịch** theo region; tại ngày đổi DST, khoảng thời gian tuyệt đối giữa hai lần 09:00 liên tiếp có thể là 23 hoặc 25 giờ. Hai yêu cầu này không tương đương.

Một số biểu thức minh họa:

~~~sql
SELECT
    DATE '2026-11-14' + 1 AS next_calendar_day,
    TIMESTAMP '2026-11-14 09:30:00'
      + INTERVAL '1' DAY AS next_wall_clock_day,
    ADD_MONTHS(DATE '2026-01-31', 1) AS next_month_rule
FROM dual;
~~~

`ADD_MONTHS` có quy tắc tháng và cuối tháng riêng; nó không đồng nghĩa cộng một số ngày cố định.

### 10.4 Dùng SYS_EXTRACT_UTC

Muốn lấy **giá trị TIMESTAMP biểu diễn thời gian UTC** từ TSTZ:

~~~sql
SELECT SYS_EXTRACT_UTC(
         TO_TIMESTAMP_TZ(
           '2026-11-14 09:30:00 +07:00',
           'YYYY-MM-DD HH24:MI:SS TZH:TZM'
         )
       ) AS utc_timestamp
FROM dual;
~~~

Kết quả ý niệm là `2026-11-14 02:30:00`, nhưng **kiểu trả về là TIMESTAMP không có zone**. Khi chuyển kết quả này qua API, cần ghi rõ rằng những thành phần giờ đang được quy ước là UTC. Không tự coi mọi TIMESTAMP nói chung đều là UTC chỉ vì từng dùng `SYS_EXTRACT_UTC` ở một bước.

## 11. Thiết kế cột theo từng nhu cầu nghiệp vụ

Lựa chọn kiểu dữ liệu trước hết là một câu hỏi về **ý nghĩa của dữ liệu**.

| Yêu cầu | Kiểu thường cân nhắc | Lưu ý |
|---|---|---|
| Ngày sinh, ngày chốt sổ, kỳ báo cáo theo lịch | `DATE` với quy ước giờ 00:00:00 | Không đổi thành UTC instant khi nghiệp vụ chỉ quan tâm ngày |
| Giờ mở cửa địa phương hoặc lịch lặp | `TIMESTAMP`/cột ngày giờ + **region riêng** | Cần quy tắc region/DST cho các lần diễn ra tương lai |
| Timestamp đo đạc trong một hệ thống đã quy ước UTC | `TIMESTAMP(p)` theo UTC hoặc kiểu zone rõ ràng | Quy ước UTC phải được thực thi nhất quán; timestamp thuần không tự chứng minh UTC |
| Thời điểm thanh toán từ nhiều khu vực | `TIMESTAMP(p) WITH TIME ZONE` | Bảo toàn instant và thông tin offset/zone phù hợp |
| Hiển thị cùng instant theo session người xem | `TIMESTAMP(p) WITH LOCAL TIME ZONE` | Không giữ zone gốc của nguồn; session time zone phải được kiểm soát |
| Audit gồm thời gian phát sinh và thời gian database nhận | Hai cột event time và receive time | Tránh trộn ý nghĩa và nguồn đồng hồ |
| Hạn chót cố định toàn cầu | Instant UTC hoặc TSTZ | Chuyển thành giờ địa phương khi hiển thị |
| Lịch hẹn ở một văn phòng với giờ địa phương và DST | Giờ lịch + region; có thể thêm instant đã tính | Offset hiện tại không đủ cho lịch tương lai |

### 11.1 Ví dụ: đơn hàng quốc tế

Một bản ghi đơn hàng có thể cần:

~~~sql
CREATE TABLE global_orders (
    order_id          NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id       NUMBER NOT NULL,
    placed_at         TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    received_at       TIMESTAMP(6) WITH TIME ZONE
                      DEFAULT SYSTIMESTAMP NOT NULL,
    customer_tz_region VARCHAR2(100)
);
~~~

- `PLACED_AT`: thời điểm người dùng hoàn tất thao tác, theo nguồn dữ liệu có timezone rõ ràng.
- `RECEIVED_AT`: thời điểm database/server ghi nhận, hữu ích để đo độ trễ.
- `CUSTOMER_TZ_REGION`: region có ý nghĩa nghiệp vụ nếu cần giữ chính xác vùng người dùng chọn; cần validate với danh sách vùng được hệ thống hỗ trợ.

Trong thực tế, một chuỗi do client gửi có thể sai vì đồng hồ thiết bị lệch. Lưu cả client event time và server receive time giúp phân tích, nhưng phải công bố nguồn độ tin cậy của từng giá trị.

### 11.2 Ví dụ: báo cáo theo ngày địa phương

Giả sử `placed_at` là TSTZ, doanh nghiệp cần báo cáo doanh số theo **ngày Việt Nam** thay vì ngày UTC. Có thể diễn đạt rõ phép chuyển đổi:

~~~sql
SELECT
    TO_CHAR(
      placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
      'YYYY-MM-DD'
    ) AS vietnam_day,
    COUNT(*) AS order_count
FROM global_orders
GROUP BY TO_CHAR(
           placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
           'YYYY-MM-DD'
         )
ORDER BY vietnam_day;
~~~

Chuyển zone **trước** khi lấy ngày là quan trọng. Một giao dịch xảy ra lúc 23:30 UTC có thể thuộc ngày kế tiếp theo lịch Việt Nam.

Đối với báo cáo lớn, việc áp dụng hàm trên cột có thể ảnh hưởng khả năng dùng index/partition pruning. Có thể cân nhắc các cột dẫn xuất, function-based index, partitioning hoặc bảng tổng hợp phù hợp nếu cần tối ưu, nhưng quyết định phải đi từ định nghĩa ngày nghiệp vụ và execution plan thực tế.

### 11.3 Tại sao UTC không giải quyết mọi bài toán?

UTC rất hữu ích làm mốc thống nhất cho **instant**. Nhưng những thông tin như “thứ Hai lúc 09:00 ở Paris”, “ngày sinh 14/11” hoặc “kết thúc ngày kinh doanh tại chi nhánh” còn cần **quy tắc lịch và region**. Chỉ chuyển mọi thứ thành UTC có thể làm mất ngữ nghĩa thời gian địa phương nếu không lưu metadata cần thiết.

## 12. Lọc theo khoảng thời gian sao cho đúng và hiệu quả

Một sai lầm phổ biến là:

~~~sql
-- Không an toàn nếu cột có giờ, phút, giây.
WHERE created_at = DATE '2026-11-14'
~~~

Điều kiện chỉ khớp bản ghi đúng **00:00:00** của ngày đó. Nếu cần mọi bản ghi trong một ngày, dùng **khoảng nửa mở**:

~~~sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
~~~

Khoảng `[start, end)` bao gồm đầu, loại trừ cuối. Cách này tránh bỏ sót các giá trị có phần giờ hoặc phải đoán “giây cuối ngày”, đặc biệt khi cột là TIMESTAMP có độ chính xác đến micro/nano giây.

### 12.1 TIMESTAMP precision và ngày cuối cùng

Với cột `TIMESTAMP(6)`, không nên viết:

~~~sql
-- Dễ bỏ sót thời điểm có phần giây sau 23:59:59.
WHERE recorded_at BETWEEN
      TIMESTAMP '2026-11-14 00:00:00'
  AND TIMESTAMP '2026-11-14 23:59:59'
~~~

Mọi giá trị từ `23:59:59.000001` đến trước nửa đêm hôm sau sẽ bị bỏ sót. Hãy dùng:

~~~sql
WHERE recorded_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND recorded_at <  TIMESTAMP '2026-11-15 00:00:00'
~~~

### 12.2 Ngày địa phương với cột TSTZ

Nếu muốn mọi sự kiện thuộc **ngày 14/11 theo Việt Nam**, giới hạn phải được diễn giải với zone Việt Nam, không lấy đơn thuần mốc UTC của ngày 14/11.

~~~sql
WHERE occurred_at >=
      FROM_TZ(
        TIMESTAMP '2026-11-14 00:00:00',
        'Asia/Ho_Chi_Minh'
      )
  AND occurred_at <
      FROM_TZ(
        TIMESTAMP '2026-11-15 00:00:00',
        'Asia/Ho_Chi_Minh'
      )
~~~

Hai mốc là các **instants** tương ứng với ranh giới ngày ở region đã chọn. Với region có DST, khoảng ngày lịch có thể dài 23 hoặc 25 giờ. Tạo hai ranh giới giờ địa phương theo region đáng tin cậy thường diễn đạt đúng yêu cầu hơn tính “UTC start + 24 giờ” một cách máy móc.

### 12.3 Giữ predicate sargable

Ví dụ:

~~~sql
-- Có thể làm Oracle phải áp dụng hàm cho nhiều dòng,
-- ảnh hưởng cách dùng index B-tree thường.
WHERE TRUNC(created_at) = DATE '2026-11-14'
~~~

So với khoảng nửa mở:

~~~sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
~~~

Điều kiện thứ hai thường dễ tận dụng index range scan hoặc partition pruning theo cột hơn. Tuy vậy optimizer có thể chọn phương án khác tùy thống kê, số hàng và index/function-based index có sẵn. Không kết luận chỉ từ cú pháp mà bỏ qua execution plan.

### 12.4 Bind variable phải đúng loại

Trong ứng dụng Java, ưu tiên truyền tham số thời gian bằng **kiểu temporal thích hợp** qua driver, thay vì ghép chuỗi và gửi định dạng phụ thuộc NLS.

~~~sql
SELECT order_id, placed_at
FROM global_orders
WHERE placed_at >= :p_start
  AND placed_at <  :p_end;
~~~

Với `PLACED_AT` là TSTZ, ứng dụng phải bind hai mốc mang ngữ nghĩa instant/timezone phù hợp. Nếu bind một giá trị timestamp không zone rồi để Oracle tự diễn giải, kết quả có thể phụ thuộc quy tắc chuyển kiểu/session và gây lệch báo cáo.

## 13. Tích hợp Java và JDBC: tránh mất múi giờ ở ranh giới ứng dụng

Một hệ thống Java thường làm việc với `java.time`, JDBC và Oracle. Cần phân biệt **kiểu thời gian của Java** với kiểu lưu Oracle:

| Java type | Ngữ nghĩa | Quan hệ thường được cân nhắc |
|---|---|---|
| `LocalDate` | Ngày lịch, không có giờ/zone | Oracle DATE với quy ước giờ 00:00:00 hoặc mô hình lưu ngày phù hợp |
| `LocalDateTime` | Ngày giờ địa phương, **không có offset/zone** | Oracle TIMESTAMP hoặc DATE khi không cần phần giây |
| `OffsetDateTime` | Ngày giờ kèm UTC offset | Có thể ánh xạ sang TSTZ qua Oracle JDBC hỗ trợ |
| `ZonedDateTime` | Ngày giờ kèm region và quy tắc zone | Có thể cần lưu region riêng nếu phải bảo toàn tên region một cách tin cậy |
| `Instant` | Một thời điểm tuyệt đối trên timeline | Có thể lưu dưới dạng UTC hoặc TSTZ với chuyển đổi rõ ràng |
| `java.sql.Date` | Kiểu JDBC legacy thiên về ngày | Không đại diện đầy đủ thành phần giờ của Oracle DATE theo kỳ vọng thường gặp |
| `java.sql.Timestamp` | Ngày giờ và phần giây của API JDBC cũ, không tự lưu tên region | Cần quy ước timezone/chuyển đổi khi dùng với loại có zone |

Các phép mapping hỗ trợ chi tiết phụ thuộc **Oracle JDBC driver version**, framework (JPA/Hibernate, Spring JDBC...) và cấu hình session. Không coi bảng trên là bảo đảm mọi phương thức `ResultSet.getObject(..., SomeClass.class)` đều hoạt động như nhau ở mọi phiên bản.

### 13.1 Điểm nguy hiểm của java.sql.Date với Oracle DATE

Người mới học có thể nghĩ Oracle `DATE` giống `java.sql.Date` vì cùng tên. Nhưng Oracle DATE có giờ-phút-giây, trong khi `java.sql.Date` là abstraction SQL date có ngữ nghĩa chỉ ngày. Nếu dùng mapping không phù hợp, có nguy cơ **mất phần thời gian** hoặc bị ảnh hưởng chuyển đổi ngày giờ ở driver/framework.

Với cột Oracle DATE được dùng làm datetime, cần kiểm tra mapping rõ ràng với `LocalDateTime` hoặc kiểu JDBC phù hợp; với ngày lịch thuần, dùng quy ước `LocalDate` tương ứng.

### 13.2 OffsetDateTime và Instant khác ZonedDateTime

`OffsetDateTime.parse("2026-11-14T09:30:00+07:00")` có đủ thông tin xác định instant, nhưng không cho biết region ban đầu là Việt Nam hay một vùng khác trùng offset.

`ZonedDateTime` có thêm region, ví dụ `Asia/Ho_Chi_Minh` hoặc `Europe/Paris`. Nếu ứng dụng đặt lịch tương lai theo vùng, giữ region là yêu cầu riêng.

Khi ghi nhận sự kiện xảy ra:

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

Instant now = Instant.now();
OffsetDateTime utc = now.atOffset(ZoneOffset.UTC);
// Bind "utc" bằng driver Oracle JDBC hỗ trợ OffsetDateTime và TSTZ.
~~~

Ví dụ minh họa ngữ nghĩa Java; API bind chi tiết phải tương thích driver thực tế và schema. Không chuyển `Instant` sang `LocalDateTime` bằng timezone mặc định của máy chủ rồi lưu vào Oracle TIMESTAMP mà không ghi rõ quy ước.

### 13.3 Quy tắc cho REST API

Một API có thể nhận thời gian theo ISO 8601:

~~~json
{
  "occurredAt": "2026-11-14T09:30:00.123456+07:00",
  "timeZoneRegion": "Asia/Ho_Chi_Minh"
}
~~~

Nếu chỉ cần instant, trường `occurredAt` với offset là đủ để xác định thời điểm. Nếu cần tính lịch tương lai hoặc tái hiện vùng người dùng chọn, `timeZoneRegion` có ý nghĩa riêng.

Không gửi một chuỗi như `"14/11/2026 09:30"` qua nhiều hệ thống rồi mặc định bên nhận sẽ biết đó là UTC+7. Trong tài liệu API, cần nêu rõ zone, precision, cách xử lý DST và ý nghĩa của “ngày”.

## 14. Thực hành với bốn kiểu dữ liệu trong một bảng

Phần này dành cho **schema lab** có quyền tạo bảng và đủ quota. Không chạy DDL trên schema production chỉ để quan sát. Các câu lệnh `CREATE TABLE` là DDL có implicit commit; `ROLLBACK` sau khi tạo bảng không tự xóa được bảng đã tạo.

### 14.1 Tạo bảng

~~~sql
CREATE TABLE time_type_lab (
    id          NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    date_value  DATE,
    ts_value    TIMESTAMP(6),
    tstz_value  TIMESTAMP(6) WITH TIME ZONE,
    tsltz_value TIMESTAMP(6) WITH LOCAL TIME ZONE
);
~~~

### 14.2 Nạp cùng một sự kiện theo bốn cách

~~~sql
INSERT INTO time_type_lab (
    date_value, ts_value, tstz_value, tsltz_value
)
VALUES (
    TO_DATE('2026-11-14 09:30:45', 'YYYY-MM-DD HH24:MI:SS'),
    TO_TIMESTAMP('2026-11-14 09:30:45.123456',
                 'YYYY-MM-DD HH24:MI:SS.FF6'),
    TO_TIMESTAMP_TZ('2026-11-14 09:30:45.123456 +07:00',
                    'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'),
    TO_TIMESTAMP_TZ('2026-11-14 09:30:45.123456 +07:00',
                    'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM')
);

COMMIT;
~~~

Trong hàng này:

- `DATE_VALUE` giữ `09:30:45` đến giây nhưng không có phần `.123456` hoặc zone.
- `TS_VALUE` giữ phần `.123456` nhưng không có zone.
- `TSTZ_VALUE` có offset `+07:00` gắn với thời điểm.
- `TSLTZ_VALUE` là cùng instant có đầu vào zone rõ, nhưng zone gốc không được giữ trong cột.

### 14.3 Đọc ở session +07:00

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';

SELECT
    TO_CHAR(date_value, 'YYYY-MM-DD HH24:MI:SS')
        AS date_display,
    TO_CHAR(ts_value, 'YYYY-MM-DD HH24:MI:SS.FF6')
        AS timestamp_display,
    TO_CHAR(tstz_value, 'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM')
        AS tz_display,
    TO_CHAR(tsltz_value, 'YYYY-MM-DD HH24:MI:SS.FF6')
        AS local_tz_display
FROM time_type_lab;
~~~

TSLTZ hiển thị theo session `+07:00`. DATE và TIMESTAMP không có cơ chế tự chuyển zone. TSTZ thể hiện instant và zone gắn với giá trị theo biểu diễn được lưu.

### 14.4 Đọc ở session UTC

~~~sql
ALTER SESSION SET TIME_ZONE = '+00:00';

SELECT
    TO_CHAR(date_value, 'YYYY-MM-DD HH24:MI:SS')
        AS date_display,
    TO_CHAR(ts_value, 'YYYY-MM-DD HH24:MI:SS.FF6')
        AS timestamp_display,
    TO_CHAR(tstz_value, 'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM')
        AS tz_display,
    TO_CHAR(tsltz_value, 'YYYY-MM-DD HH24:MI:SS.FF6')
        AS local_tz_display
FROM time_type_lab;
~~~

Kỳ vọng cơ bản:

| Cột | Khi session +07:00 | Khi session +00:00 | Có đổi biểu diễn theo session? |
|---|---|---|---|
| `DATE_VALUE` | 09:30:45 | 09:30:45 | Không |
| `TS_VALUE` | 09:30:45.123456 | 09:30:45.123456 | Không |
| `TSTZ_VALUE` | 09:30:45.123456 +07:00 (theo zone của giá trị) | Vẫn theo zone của giá trị nếu format trực tiếp | Không tự biến thành session zone như TSLTZ |
| `TSLTZ_VALUE` | 09:30:45.123456 | 02:30:45.123456 | **Có** |

Nếu muốn TSTZ hiển thị theo session, có thể **chuyển đổi có chủ đích** với `AT TIME ZONE SESSIONTIMEZONE` hoặc zone cụ thể. Đừng nhầm chuyển đổi tường minh đó với cơ chế hiển thị mặc định của TSLTZ.

### 14.5 Quan sát kiểu dữ liệu được khai báo

~~~sql
SELECT column_name,
       data_type,
       data_scale
FROM user_tab_columns
WHERE table_name = 'TIME_TYPE_LAB'
ORDER BY column_id;
~~~

`DATA_TYPE` sẽ phân biệt DATE, TIMESTAMP và các biến thể time zone. Precision có thể được trình bày trong metadata của cột; đừng kết luận độ chính xác dựa vào giao diện chỉ hiển thị đến giây.

### 14.6 Dọn môi trường

Nếu hoàn toàn sở hữu bảng lab và đã xác nhận dữ liệu không cần giữ, có thể xóa bảng bằng quy trình quản trị lab. `DROP TABLE` tác động đến dữ liệu/schema và có implicit commit; không dùng trên bảng nghiệp vụ đang được ứng dụng sử dụng.

## 15. Lỗi và ngộ nhận thường gặp

### 15.1 “DATE chỉ có ngày, không có giờ”

Sai với Oracle. `DATE` có giờ-phút-giây. Việc công cụ chỉ in ngày thường là do format hiển thị.

### 15.2 “TIMESTAMP tự có UTC”

Sai. `TIMESTAMP` không lưu time zone. Nếu ứng dụng sử dụng UTC trong cột TIMESTAMP, đó là quy ước riêng và phải bảo vệ tính nhất quán của quy ước đó.

### 15.3 “TIMESTAMP WITH LOCAL TIME ZONE giữ lại zone người gửi”

Sai. TSLTZ chuẩn hóa giá trị và hiển thị theo session time zone, **không giữ zone gốc của từng hàng**.

### 15.4 “Chỉ cần lưu +07:00 là đủ để biết region”

Sai. Offset không xác định duy nhất region và không mang đủ quy tắc DST của vùng cho lịch tương lai.

### 15.5 “BETWEEN 00:00:00 và 23:59:59 là đủ cho cả ngày”

Không đủ với TIMESTAMP chứa phần giây. Dùng khoảng nửa mở `>= start AND < next_day_start`.

### 15.6 “TRUNC(date_time) luôn là cách lọc ngày tối ưu nhất”

Không có bảo đảm. Hàm trên cột có thể hạn chế một số đường truy cập index; so sánh ranh giới typed values thường dễ tối ưu hơn. Với dữ liệu có zone, phải xét **ngày ở region nghiệp vụ nào** trước khi `TRUNC`/nhóm ngày.

### 15.7 “SYSDATE và CURRENT_DATE luôn giống nhau”

Sai. `SYSDATE` dựa trên thời gian của database server, `CURRENT_DATE` theo session time zone. Nếu hai zone khác nhau, hiển thị có thể khác giờ/ngày.

### 15.8 “Đổi NLS_DATE_FORMAT sẽ sửa dữ liệu lưu sai múi giờ”

Sai. NLS chủ yếu tác động vào parsing/formatting mặc định, không xác minh hoặc sửa ngữ nghĩa zone bị thiếu trong DATE/TIMESTAMP.

### 15.9 “Date/time parsing luôn tự hiểu định dạng quốc tế”

Không nên giả định. Các chuỗi như `01/02/2026` có thể được hiểu là 1/2 hoặc 2/1 tùy quy tắc. Dùng literal ISO/format model rõ ràng hoặc bind đúng kiểu từ ứng dụng.

### 15.10 “Cộng 24 giờ luôn bằng ngày mai cùng giờ địa phương”

Sai ở region chuyển DST. Cần phân biệt **duration** và **calendar schedule**.

## 16. Lỗi Oracle thường gặp khi xử lý ngày giờ

| Nhóm lỗi | Ví dụ biểu hiện | Hướng kiểm tra |
|---|---|---|
| Chuỗi không khớp format | `ORA-01861: literal does not match format string` | So sánh chuỗi nguồn với format model; kiểm tra dấu, số phần giây và NLS |
| Ngày/giờ không hợp lệ | Các lỗi `ORA-018xx` về tháng/ngày/giờ không hợp lệ | Kiểm tra ngày lịch thật, năm nhuận, `HH24`, `MI`, `SS` |
| Thiếu thông tin khi parse TSTZ | Giá trị có offset nhưng format model không khai báo `TZH:TZM`, hoặc ngược lại | Dùng `TO_TIMESTAMP_TZ` và format zone đúng |
| Region không được nhận diện | Sai tên region/không có trong Oracle timezone file | Kiểm tra `V$TIMEZONE_NAMES` và phiên bản timezone file |
| Giờ mơ hồ/không tồn tại do DST | Lỗi hoặc diễn giải không như dự kiến ở ngày đổi DST | Bổ sung region, offset/`TZD` phù hợp; xác định chính sách nghiệp vụ |
| Kết quả TSLTZ khác giữa các ứng dụng | Session ở các time zone khác nhau | Kiểm tra `SESSIONTIMEZONE` trong từng connection |
| Ghi đúng nhưng báo cáo lệch ngày | Nhóm theo UTC thay vì zone nghiệp vụ | Chuyển instant sang region nghiệp vụ trước khi lấy ngày |
| Dữ liệu hiển thị mất micro giây | `TO_CHAR` thiếu `FFn` hoặc cột DATE | Kiểm tra kiểu dữ liệu, precision và format |
| Index không được sử dụng như kỳ vọng | Dùng `TRUNC(column)` hoặc implicit conversion | Kiểm tra execution plan và viết predicate theo kiểu cột |
| Dữ liệu nhập bị lệch giờ | Ứng dụng bind TIMESTAMP không zone vào cột có zone | Kiểm tra mapping JDBC, session time zone, offset đầu vào |

Khi gỡ lỗi, nên ghi lại **kiểu cột, kiểu dữ liệu bind, giá trị nguồn, format model, session time zone, database time zone, Oracle timezone file version và driver version**. Chỉ nhìn chuỗi in trên màn hình thường chưa đủ phân biệt lỗi parsing, lỗi truyền timezone hay lỗi hiển thị.

## 17. Migration và dữ liệu ngày giờ kế thừa

Hệ thống cũ có thể lưu `CREATED_AT DATE` hoặc `TIMESTAMP` và để ứng dụng tự ngầm hiểu tất cả giá trị là giờ Việt Nam. Khi mở rộng sang nhiều quốc gia, nhu cầu mới là tính thứ tự event theo instant toàn cầu.

**Không thể tự chuyển chính xác toàn bộ dữ liệu cũ sang TSTZ nếu không biết quy ước time zone lịch sử**. Kế hoạch chuyển đổi thường gồm:

1. **Kiểm kê:** cột nào là ngày lịch, cột nào là wall-clock datetime, cột nào thực chất là UTC được lưu không zone?
2. **Xác nhận nguồn và thời kỳ:** từ trước đến nay app server/DB server đặt zone nào, có thay đổi server hoặc region theo thời gian không?
3. **Tách dữ liệu chắc chắn và dữ liệu mơ hồ:** giá trị có offset từ log có thể khôi phục instant; giá trị local time tại vùng DST ở giờ lặp có thể cần nguồn bổ sung.
4. **Chọn kiểu đích và semantics:** TSTZ, TSLTZ hoặc timestamp UTC + region riêng tùy dữ liệu.
5. **Chuyển theo batch có đối soát:** kiểm tra số hàng, mốc UTC, thứ tự event, và báo cáo theo ngày nghiệp vụ.
6. **Sửa cả biên ứng dụng:** API, JDBC, export/import, BI, cache và downstream phải thống nhất kiểu và zone.
7. **Kiểm thử DST và tương thích timezone file:** đặc biệt nếu chuyển Oracle release/region data.

Ví dụ **chỉ khi đã xác nhận toàn bộ giá trị legacy là giờ địa phương Việt Nam**:

~~~sql
SELECT FROM_TZ(
         CAST(legacy_created_at AS TIMESTAMP),
         'Asia/Ho_Chi_Minh'
       ) AS created_at_with_timezone
FROM legacy_orders;
~~~

Nếu thật ra dữ liệu cũ là UTC, cách chuyển trên sẽ **dịch instant sai 7 giờ**. Đây là lỗi dữ liệu nghiệp vụ, không thể khắc phục bằng đổi format khi hiển thị. Phải xác nhận quy ước cũ trước khi biến đổi.

### 17.1 Giữ nguồn gốc dữ liệu

Khi hệ thống tích hợp với thiết bị di động, máy quét hoặc server ngoài, nên ghi thêm:

- Thời điểm event do nguồn báo (nếu có zone/offset).
- Thời điểm database nhận event.
- Source ID và độ tin cậy/đồng bộ đồng hồ nguồn.
- Region gốc nếu cần diễn giải lịch, hoặc một trường chất lượng dữ liệu khi nguồn không cung cấp zone.

Không gắn offset theo “địa chỉ hiện tại của người dùng” cho sự kiện lịch sử khi chưa biết vị trí và quy tắc tại thời điểm phát sinh.

## 18. Bài tập tình huống

### Tình huống A — Hai bản ghi giống giờ nhưng khác instant

Một API gửi:

~~~text
Event A: 2026-11-14T09:30:00+07:00
Event B: 2026-11-14T09:30:00+01:00
~~~

Hai chuỗi có cùng 09:30 nhưng khác offset. Hỏi:

1. Chúng có cùng instant không?
2. Dùng TIMESTAMP thuần có làm mất điều gì?
3. Có thể xác định region gốc chỉ từ offset không?

**Gợi ý:** A tương ứng 02:30 UTC, B tương ứng 08:30 UTC; không cùng instant. TIMESTAMP thuần chỉ còn cùng wall-clock time `09:30` nếu bỏ zone. Offset không xác định duy nhất region.

### Tình huống B — Báo cáo doanh thu theo ngày tại Việt Nam

Một đơn được thanh toán lúc `2026-11-14 23:45 UTC`. Nhóm BI lọc `UTC_DATE = 2026-11-14` và gọi đó là “doanh thu ngày 14/11 tại Việt Nam”.

Hỏi: Ngày kinh doanh tại Việt Nam của giao dịch là ngày nào?

**Gợi ý:** UTC+07:00 tương ứng `2026-11-15 06:45`. Nếu doanh thu được định nghĩa theo ngày địa phương Việt Nam, giao dịch thuộc **15/11**, không phải 14/11. Cần chuyển TSTZ sang region tương ứng **trước khi nhóm theo ngày**.

### Tình huống C — Hiển thị khác nhau giữa hai connection

Một cột `TIMESTAMP WITH LOCAL TIME ZONE` được ghi một lần. Kết quả truy vấn từ connection A là 09:30, từ connection B là 02:30. Đều không có lỗi SQL.

Hỏi:

1. Điều gì có thể giải thích hai kết quả?
2. Có nên sửa giá trị đã lưu để “đồng bộ” hai màn hình?
3. Khi export dữ liệu định kỳ, cần thống nhất điều gì?

**Gợi ý:** `SESSIONTIMEZONE` khác nhau. Không tự sửa dữ liệu instant chỉ vì cách hiển thị khác; cần cấu hình session hoặc chuyển zone tường minh trong query/export và công bố zone trong dữ liệu xuất.

### Tình huống D — Cảnh báo hết hạn

Một token hết hạn “đúng 24 giờ kể từ lúc tạo”. Một lịch bảo trì diễn ra “09:00 sáng mai tại New York”.

Hỏi nên dùng quy tắc nào cho mỗi trường hợp?

**Gợi ý:** Token dựa trên **duration tính từ instant**; lịch bảo trì dựa trên **ngày/giờ địa phương + region**, vì 24 giờ sau không luôn là ngày mai cùng giờ địa phương ở thời điểm DST.

### Tình huống E — Migration Oracle DATE sang TSTZ

Một bảng cũ có `created_at DATE`, tài liệu cũ chỉ ghi “giờ local”, và hiện tại server đặt UTC. DBA muốn cập nhật tất cả bằng cách gắn `+00:00`.

Hỏi có đủ bằng chứng để làm vậy không?

**Gợi ý:** Chưa. “Giờ local” có thể từng là giờ Việt Nam hoặc một múi giờ khác; server hiện tại không chứng minh cấu hình lịch sử. Cần điều tra nguồn, log, thay đổi hạ tầng, hệ thống kết nối và chất lượng dữ liệu trước khi gắn timezone.

## 19. Quy tắc ra quyết định

Khi chọn kiểu dữ liệu Oracle cho một trường thời gian, hãy hỏi:

1. **Nó là ngày lịch, wall-clock time hay instant?** Ngày sinh và một sự kiện thanh toán cần mô hình khác nhau.
2. **Có cần phần giây không?** Nếu chỉ có giây, DATE có thể đủ về precision; nếu cần micro giây, dùng TIMESTAMP phù hợp.
3. **Có cần biết offset/region gốc không?** Nếu có, TSTZ hoặc trường region riêng có thể cần thiết; TSLTZ không giữ zone gốc.
4. **Người đọc có cần giờ theo session không?** Nếu có, TSLTZ phù hợp trong những trường hợp nhất định, với điều kiện session timezone được quản lý.
5. **Dữ liệu có phục vụ lịch tương lai hoặc qua DST không?** Phải có region và quy tắc lịch, không chỉ instant/offset.
6. **Dữ liệu đi qua những hệ thống nào?** Kiểm tra format API, bind JDBC, reporting, export, index/predicate và cấu hình NLS.

**Oracle DATE** là giá trị ngày-giờ chính xác đến giây, **TIMESTAMP** thêm phần giây nhưng không tự có timezone, **TIMESTAMP WITH TIME ZONE** cho phép biểu diễn instant kèm offset/region, còn **TIMESTAMP WITH LOCAL TIME ZONE** chuẩn hóa instant để hiển thị theo time zone của session mà không giữ zone gốc. Chọn đúng kiểu và chuyển đổi tường minh từ đầu sẽ hạn chế lệch giờ, lệch ngày báo cáo và lỗi DST, đồng thời làm dữ liệu ổn định khi ứng dụng mở rộng sang nhiều múi giờ.
