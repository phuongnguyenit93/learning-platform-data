# SESSIONTIMEZONE, DBTIMEZONE và chuẩn hóa thời điểm giữa hệ thống

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Ngày giờ và NLS  
> **Mục tiêu:** Hiểu rõ `SESSIONTIMEZONE` và `DBTIMEZONE` có vai trò gì trong Oracle Database; chọn kiểu dữ liệu thời gian phù hợp; chuẩn hóa **thời điểm (instant)** khi dữ liệu đi qua ứng dụng, API, máy chủ và database ở nhiều múi giờ; viết truy vấn đúng qua ranh giới ngày và các lần đổi giờ mùa hè (DST).

## 1. Tình huống mở đầu: cùng một sự kiện, nhiều giờ hiển thị

Một yêu cầu thanh toán được ghi nhận vào lúc **09:30 ngày 14/11/2026 tại Việt Nam** (UTC+07:00). Cùng **một thời điểm thực**, hệ thống có thể biểu diễn dưới những dạng sau:

| Nơi hiển thị | Thời gian địa phương tương ứng | Ghi chú |
|---|---|---|
| Việt Nam, UTC+07:00 | `2026-11-14 09:30:00 +07:00` | Giờ người dùng tại Việt Nam |
| UTC | `2026-11-14 02:30:00 +00:00` | Mốc chuẩn trao đổi giữa hệ thống |
| New York, UTC−05:00 tại ngày này | `2026-11-13 21:30:00 -05:00` | Ngày lịch có thể khác |

Ba chuỗi trên nói về **cùng một instant**. Khác biệt là cách diễn đạt theo timezone, không có nghĩa sự kiện được tạo ba lần.

Nếu database chỉ lưu:

```text
2026-11-14 09:30:00
```

mà không có quy ước múi giờ, ứng dụng khác không thể biết chắc đây là 09:30 ở Việt Nam, UTC hay nơi nào khác. Một lệch múi giờ nhỏ cũng có thể gây sai dữ liệu báo cáo theo ngày, thứ tự sự kiện, thời hạn thanh toán, SLA hoặc audit.

Trong Oracle, cần phân biệt:

- **`SESSIONTIMEZONE`:** múi giờ của phiên làm việc hiện tại.
- **`DBTIMEZONE`:** múi giờ được cấu hình cho database, có vai trò đặc biệt khi lưu `TIMESTAMP WITH LOCAL TIME ZONE`.
- **Múi giờ/đồng hồ hệ điều hành của database server:** liên quan các hàm như `SYSDATE`, `SYSTIMESTAMP`.
- **Múi giờ nghiệp vụ của người dùng hoặc sự kiện:** ví dụ `Asia/Ho_Chi_Minh` hay `America/New_York`; do ứng dụng/nghiệp vụ xác định.

Bốn yếu tố này **không phải một** và không nên được giả định luôn giống nhau.

## 2. Các khái niệm nền tảng

### 2.1. Instant, local date-time, UTC offset và time zone region

Để thiết kế lưu trữ và trao đổi thời gian đúng, trước tiên cần tách bốn khái niệm:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| **Instant** | `2026-11-14T02:30:00Z` | Một thời điểm tuyệt đối trên dòng thời gian |
| **Local date-time** | `2026-11-14 09:30:00` | Ngày và giờ nhìn trên đồng hồ địa phương; **chưa xác định instant** nếu thiếu timezone/offset |
| **UTC offset** | `+07:00`, `-05:00` | Độ lệch so với UTC tại một thời điểm |
| **Time zone region** | `Asia/Ho_Chi_Minh`, `America/New_York` | Vùng có bộ quy tắc offset theo lịch sử/tương lai, có thể có DST |

UTC là mốc tham chiếu toàn cầu, thường ký hiệu `Z` hoặc `+00:00` trong chuỗi ISO 8601. Một **offset** mô tả độ lệch tại thời điểm cụ thể, còn **region** còn biểu thị bộ quy tắc để chuyển đổi các ngày khác nhau.

Ví dụ: `America/New_York` không có một offset cố định quanh năm. Tùy ngày, nó thường dùng `-05:00` hoặc `-04:00`. Vì vậy, lưu `-05:00` cho một **cuộc hẹn lặp lại hằng tháng tại New York** chưa đủ để biết giờ địa phương vào các tháng có DST.

### 2.2. Vì sao đồng hồ hệ thống không giống timezone?

Hai máy có thể cùng đồng bộ NTP nên đồng hồ vật lý chính xác, nhưng một máy hiển thị UTC và máy còn lại hiển thị giờ Việt Nam. Ngược lại, hai máy cùng dùng UTC+07:00 vẫn có thể có đồng hồ bị lệch vài phút nếu không đồng bộ thời gian.

- **Clock synchronization** giải quyết độ chính xác của thời gian máy.
- **Time zone** giải quyết cách biểu diễn một instant bằng ngày/giờ địa phương.
- **Oracle session time zone** giải quyết ngữ nghĩa trong một phiên SQL.
- **Database time zone** là thuộc tính cấu hình riêng của Oracle, không phải phép đo đồng hồ hiện tại.

Hệ thống phân tán cần cả đồng bộ đồng hồ đáng tin cậy lẫn quy ước lưu/trao đổi timezone rõ ràng.

## 3. SESSIONTIMEZONE là gì?

**`SESSIONTIMEZONE`** là hàm Oracle SQL trả về múi giờ của **session hiện tại**. Kết quả có thể là offset như `+07:00`, `-05:00` hoặc tên vùng như `Asia/Ho_Chi_Minh`, tùy cách session được cấu hình.

Kiểm tra:

```sql
SELECT SESSIONTIMEZONE AS session_timezone
FROM dual;
```

Ví dụ kết quả:

```text
SESSION_TIMEZONE
----------------
+07:00
```

Đây chỉ là ví dụ. Trên một JDBC connection do ứng dụng quản lý hoặc trên SQL Developer, kết quả có thể khác tùy môi trường client, driver và thiết lập phiên.

### 3.1. Thay đổi múi giờ trong session

Trong session SQL*Plus/SQLcl hoặc SQL Developer Worksheet:

```sql
ALTER SESSION SET TIME_ZONE = '+07:00';

SELECT SESSIONTIMEZONE FROM dual;
```

Để dùng vùng có quy tắc thời gian thay đổi theo lịch, nếu tên vùng được Oracle timezone file hỗ trợ:

```sql
ALTER SESSION SET TIME_ZONE = 'Asia/Ho_Chi_Minh';

SELECT SESSIONTIMEZONE FROM dual;
```

Hoặc thử một offset khác:

```sql
ALTER SESSION SET TIME_ZONE = '-05:00';

SELECT SESSIONTIMEZONE FROM dual;
```

**Phạm vi tác động:** `ALTER SESSION SET TIME_ZONE` đổi ngữ cảnh của **kết nối/session đó**. Nó không tự đổi timezone của toàn database, hệ điều hành, client khác hoặc mọi PDB.

Trong hệ thống dùng connection pool, một physical database session có thể được tái sử dụng cho nhiều request. Nếu code thay đổi session timezone mà không quản lý việc khởi tạo/đặt lại, request sau có thể nhận cấu hình của request trước. Vì vậy, cần quy ước cấu hình timezone nhất quán cho mọi connection khi lấy từ pool.

### 3.2. SESSIONTIMEZONE ảnh hưởng đến những gì?

Những tác động quan trọng:

- `CURRENT_TIMESTAMP` trả thời gian hiện tại dưới dạng `TIMESTAMP WITH TIME ZONE` theo timezone của session.
- `CURRENT_DATE` trả thời gian hiện tại dưới dạng Oracle `DATE` theo timezone của session.
- `LOCALTIMESTAMP` trả thời gian hiện tại dưới dạng `TIMESTAMP`, theo timezone của session nhưng **không chứa timezone** trong kết quả.
- Khi lấy giá trị từ cột `TIMESTAMP WITH LOCAL TIME ZONE`, Oracle chuyển sang múi giờ của session để hiển thị/diễn giải.
- Những phép chuyển đổi timestamp không có timezone có thể sử dụng timezone session hoặc yêu cầu nêu rõ ngữ cảnh, tùy biểu thức/hàm.

**Không nên hiểu** mọi cột `DATE` hoặc `TIMESTAMP` tự dịch giờ khi chạy `ALTER SESSION SET TIME_ZONE`. Hai kiểu đó không lưu thông tin timezone để tự thay đổi giá trị như `TIMESTAMP WITH LOCAL TIME ZONE`.

### 3.3. SESSIONTIMEZONE có phải timezone người dùng cuối không?

Không nhất thiết. Một web application chạy trên server có thể dùng một JDBC session đặt `+00:00`, trong khi người dùng đăng nhập từ Hà Nội, Sydney hoặc New York.

Nếu nghiệp vụ cần hiển thị theo người dùng, ứng dụng phải biết **timezone do người dùng chọn hoặc được hệ thống xác định đáng tin cậy**. Không lấy `SESSIONTIMEZONE` của một connection pool làm bằng chứng chắc chắn về vị trí/giờ địa phương của người dùng.

## 4. DBTIMEZONE là gì?

**`DBTIMEZONE`** là hàm Oracle trả về timezone được cấu hình cho database. Giá trị có thể được biểu diễn bằng UTC offset hoặc time zone region, tùy cấu hình và phiên bản.

Kiểm tra từ session đang kết nối đúng database/PDB:

```sql
SELECT DBTIMEZONE AS database_timezone,
       SESSIONTIMEZONE AS session_timezone
FROM dual;
```

Ví dụ minh họa:

```text
DATABASE_TIMEZONE  SESSION_TIMEZONE
-----------------  ----------------
+00:00             +07:00
```

Hai giá trị khác nhau là **bình thường**.

### 4.1. Vai trò thực tế của DBTIMEZONE

`DBTIMEZONE` được Oracle sử dụng đặc biệt để **chuẩn hóa giá trị của kiểu `TIMESTAMP WITH LOCAL TIME ZONE`** khi lưu trữ. Khi đọc, giá trị được trình bày theo timezone của session.

Nói cách khác:

```text
Ứng dụng ghi một instant có timezone/offset
                 |
                 v
  TIMESTAMP WITH LOCAL TIME ZONE
                 |
         Chuẩn hóa để lưu theo
         database time zone
                 |
                 v
              Datafiles
                 |
        Khi session truy vấn
                 |
                 v
       Chuyển theo SESSIONTIMEZONE
                 |
                 v
            Giá trị nhìn thấy
```

`DBTIMEZONE` **không quy định cách mọi kiểu ngày giờ lưu trữ**, không khiến tất cả các cột `DATE`/`TIMESTAMP` tự chuyển sang UTC và không thay thế timezone ứng dụng.

### 4.2. DBTIMEZONE khác giờ của database server

Giả sử:

- Server Oracle đang ở múi giờ UTC+07:00.
- `DBTIMEZONE` = `+00:00`.
- `SESSIONTIMEZONE` = `-05:00`.

Khi đó ba thông tin có thể tồn tại đồng thời, không có mâu thuẫn.

`SYSDATE` và `SYSTIMESTAMP` lấy thời gian từ đồng hồ của database host theo ngữ nghĩa tương ứng; còn `DBTIMEZONE` là thuộc tính timezone cấu hình. Chỉ đọc `DBTIMEZONE` **không thể suy ra ngay** giờ hiện tại trên server.

### 4.3. Có thể đổi DBTIMEZONE không?

Oracle có cú pháp quản trị:

```sql
ALTER DATABASE SET TIME_ZONE = '+00:00';
```

Tuy nhiên, đây là **thay đổi cấp database**, không phải thao tác cần chạy cho từng session. Giá trị mới có hiệu lực sau khi restart database theo cơ chế Oracle. Oracle cũng có các **hạn chế khi database chứa cột `TIMESTAMP WITH LOCAL TIME ZONE`**; việc thay đổi không được xem là phép chuyển đổi hàng loạt an toàn cho dữ liệu đã tồn tại.

Với môi trường sản xuất hoặc CDB/PDB đang dùng, thay đổi DBTIMEZONE cần DBA xác nhận điều kiện, phiên bản, dữ liệu TSLTZ, kế hoạch downtime, backup và quy trình kiểm chứng. **Không chạy lệnh này trong bài lab chỉ để làm hai giá trị DBTIMEZONE và SESSIONTIMEZONE giống nhau.**

### 4.4. Có cần DBTIMEZONE luôn bằng UTC?

UTC thường là lựa chọn tốt khi **khởi tạo database mới** và muốn chuẩn hóa các giá trị `TIMESTAMP WITH LOCAL TIME ZONE`. Nhưng không nhất thiết phải đổi DBTIMEZONE trong một database hiện có để xây dựng ứng dụng xử lý instant đúng.

Chẳng hạn, một ứng dụng lưu `TIMESTAMP WITH TIME ZONE` và trao đổi ISO 8601 với offset có thể quản lý thời điểm chính xác mà không yêu cầu `DBTIMEZONE = +00:00`. Điều quan trọng là **kiểu cột và hợp đồng dữ liệu** được thiết kế đúng.

## 5. Phân biệt năm nhóm kiểu thời gian trong Oracle

Bảng sau là cơ sở để chọn chiến lược chuẩn hóa:

| Kiểu | Lưu phần giây? | Lưu hoặc xử lý timezone? | Giá trị nhìn thấy khi SESSIONTIMEZONE thay đổi |
|---|---|---|---|
| **`DATE`** | Không; chính xác tới giây | Không lưu timezone | Giá trị cột không tự dịch timezone |
| **`TIMESTAMP(p)`** | Có | Không lưu timezone | Giá trị cột không tự dịch timezone |
| **`TIMESTAMP(p) WITH TIME ZONE`** (TSTZ) | Có | Chứa thông tin timezone offset hoặc vùng thời gian tương ứng | Giữ ngữ nghĩa instant và biểu diễn timezone của giá trị; không tự biến thành giờ session chỉ vì đổi SESSIONTIMEZONE |
| **`TIMESTAMP(p) WITH LOCAL TIME ZONE`** (TSLTZ) | Có | Chuẩn hóa theo DBTIMEZONE khi lưu; xuất theo SESSIONTIMEZONE khi đọc | Cách biểu diễn ngày/giờ có thể đổi theo session |
| **`INTERVAL`** | Tùy loại | Diễn đạt khoảng thời gian, không phải một instant | Không nên dùng để thay thế thời điểm |

### 5.1. DATE không có nghĩa “chỉ có ngày”

Trong Oracle, `DATE` chứa năm, tháng, ngày, giờ, phút và giây; nó không có phần giây lẻ và không chứa timezone.

```sql
SELECT TO_CHAR(
         TO_DATE('2026-11-14 09:30:45',
                 'YYYY-MM-DD HH24:MI:SS'),
         'YYYY-MM-DD HH24:MI:SS'
       ) AS oracle_date
FROM dual;
```

Kết quả tương đương:

```text
2026-11-14 09:30:45
```

Nếu chỉ biểu thị “ngày sinh 14/11/2026” hoặc “ngày đến hạn”, `DATE` thường hợp lý với **quy ước phần giờ 00:00:00**. Đừng tự chuyển ngày sinh sang UTC để rồi ngày lịch có thể bị đổi khi hiển thị ở quốc gia khác: **calendar date** không phải instant.

### 5.2. TIMESTAMP không có timezone

`TIMESTAMP(6)` có thể lưu:

```text
2026-11-14 09:30:45.123456
```

Nhưng chuỗi này chưa xác định một instant nếu không biết múi giờ hoặc quy ước của nguồn. Nó phù hợp với một số “giờ địa phương theo lịch” như giờ mở cửa `09:00` hoặc ứng dụng có hợp đồng rõ rằng mọi timestamp không timezone đều được hiểu theo UTC.

Nếu chọn lưu UTC trong cột `TIMESTAMP`, cần ghi rõ và tuân thủ quy ước ở **mọi điểm đọc/ghi**. Kiểu dữ liệu không tự kiểm tra xem một client có gửi nhầm giờ địa phương vào đó hay không.

### 5.3. TIMESTAMP WITH TIME ZONE (TSTZ)

`TIMESTAMP WITH TIME ZONE` phù hợp với những sự kiện cần so sánh theo **thời điểm tuyệt đối**. Nó lưu thông tin timezone kèm timestamp (offset hoặc region theo giá trị được cung cấp) và hỗ trợ các phép toán có nhận thức timezone.

Ví dụ:

```sql
SELECT TO_TIMESTAMP_TZ(
         '2026-11-14 09:30:00 +07:00',
         'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       ) AS event_time
FROM dual;
```

Đây là instant tương đương `2026-11-14T02:30:00Z`.

Không mặc định TSTZ luôn giữ **tên vùng địa lý**. Khi người dùng cung cấp `+07:00`, giá trị có offset; để lưu thông tin “sự kiện được lịch hóa theo khu vực `Asia/Ho_Chi_Minh`”, có thể cần giữ region hoặc thêm cột `zone_id` tùy nghiệp vụ.

### 5.4. TIMESTAMP WITH LOCAL TIME ZONE (TSLTZ)

TSLTZ biểu thị instant nhưng **không giữ nguyên biểu diễn timezone gốc** như TSTZ. Oracle chuẩn hóa theo database timezone khi lưu và chuyển sang session timezone khi đọc.

Ví dụ một hàng được chèn tại `09:30 +07:00`:

- Session `+07:00` thấy `09:30`.
- Session `+00:00` thấy `02:30`.
- Session `-05:00` thấy `21:30` của **ngày hôm trước**.

Không phải dữ liệu bị thay đổi ba lần; đây là ba cách trình bày một instant. Do TSLTZ bỏ ngữ cảnh offset/region ban đầu, **không dùng nó khi cần truy lại timezone địa phương gốc như một dữ kiện audit**.

### 5.5. Chọn TSTZ hay TSLTZ?

| Yêu cầu | Kiểu thường phù hợp | Lý do |
|---|---|---|
| Lưu sự kiện thanh toán, audit, log có instant rõ | TSTZ hoặc TSLTZ theo hợp đồng dữ liệu | Hỗ trợ so sánh đúng thời điểm |
| Cần biết offset hoặc vùng được gửi tại thời điểm nhập | TSTZ, cân nhắc cột region riêng | TSLTZ không giữ nguyên thông tin nguồn |
| Muốn cùng giá trị tự hiển thị theo timezone của mỗi session | TSLTZ | Session-dependent display là đặc tính của kiểu |
| Ngày sinh hoặc ngày khai sinh không có giờ | DATE với quy ước chỉ ngày | Không có ý nghĩa instant |
| Cuộc hẹn “09:00 mỗi thứ Hai tại New York” | Local date/time + time zone region + quy tắc lịch | UTC offset của một lần hẹn không đủ cho mọi lần tái diễn |
| Timestamp do hệ thống đã quy ước luôn UTC | TIMESTAMP hoặc TSTZ, nhưng phải nhất quán | TIMESTAMP không tự mang metadata timezone |
| Cần tính duration giữa hai sự kiện ở múi giờ khác nhau | TSTZ hoặc instant chuẩn hóa | Hiệu thời điểm phải tính theo instant |

## 6. Các hàm thời gian hay nhầm: SYSDATE, SYSTIMESTAMP, CURRENT_DATE

Chạy cùng lúc:

```sql
SELECT DBTIMEZONE,
       SESSIONTIMEZONE,
       SYSDATE,
       SYSTIMESTAMP,
       CURRENT_DATE,
       CURRENT_TIMESTAMP,
       LOCALTIMESTAMP
FROM dual;
```

Diễn giải:

| Biểu thức | Kiểu kết quả | Nguồn và timezone |
|---|---|---|
| `DBTIMEZONE` | Chuỗi timezone | Cấu hình timezone của database; không phải giờ hiện tại |
| `SESSIONTIMEZONE` | Chuỗi timezone | Timezone session |
| `SYSDATE` | `DATE` | Đồng hồ database server, không kèm timezone; tới giây |
| `SYSTIMESTAMP` | `TIMESTAMP WITH TIME ZONE` | Đồng hồ database server với thông tin timezone server |
| `CURRENT_DATE` | `DATE` | Giờ hiện tại theo timezone session, nhưng kiểu kết quả không chứa timezone |
| `CURRENT_TIMESTAMP` | `TIMESTAMP WITH TIME ZONE` | Giờ hiện tại theo timezone session |
| `LOCALTIMESTAMP` | `TIMESTAMP` | Giờ hiện tại theo timezone session, không kèm timezone |

Thực hành:

```sql
ALTER SESSION SET TIME_ZONE = '+07:00';

SELECT SESSIONTIMEZONE,
       TO_CHAR(CURRENT_TIMESTAMP,
               'YYYY-MM-DD HH24:MI:SS TZH:TZM') AS current_in_session,
       TO_CHAR(SYSTIMESTAMP,
               'YYYY-MM-DD HH24:MI:SS TZH:TZM') AS server_time
FROM dual;
```

Sau đó:

```sql
ALTER SESSION SET TIME_ZONE = '-05:00';

SELECT SESSIONTIMEZONE,
       TO_CHAR(CURRENT_TIMESTAMP,
               'YYYY-MM-DD HH24:MI:SS TZH:TZM') AS current_in_session,
       TO_CHAR(SYSTIMESTAMP,
               'YYYY-MM-DD HH24:MI:SS TZH:TZM') AS server_time
FROM dual;
```

Kỳ vọng: `CURRENT_TIMESTAMP` đổi cách biểu diễn theo session; `SYSTIMESTAMP` vẫn dựa vào timezone/đồng hồ host. Dĩ nhiên thời gian vật lý tiếp tục trôi giữa hai lần truy vấn.

**Bẫy phổ biến:** `SYSDATE` và `CURRENT_DATE` đều là Oracle DATE, nhưng không có nghĩa luôn trả cùng giờ. Khi server và session dùng timezone khác, hai kết quả có thể khác nhau đáng kể.

## 7. Bài thực hành: một instant qua ba kiểu cột

Bài lab này chỉ tạo và chỉnh dữ liệu trong schema bạn được phép sử dụng. Cần quyền `CREATE TABLE` và quota tablespace; không yêu cầu quyền DBA hoặc thay đổi DBTIMEZONE.

### 7.1. Tạo bảng thử nghiệm

```sql
CREATE TABLE lab_timezone_events (
    event_id         NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    source_system    VARCHAR2(32 CHAR) NOT NULL,
    event_tstz       TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    event_tsltz      TIMESTAMP(6) WITH LOCAL TIME ZONE NOT NULL,
    event_plain_ts   TIMESTAMP(6) NOT NULL
);
```

Ba cột cùng ghi một giá trị thời gian nhưng **khác ngữ nghĩa**:

- `EVENT_TSTZ` giữ timestamp có timezone.
- `EVENT_TSLTZ` giữ instant có chuyển đổi khi xem từ timezone session.
- `EVENT_PLAIN_TS` lưu local date-time không có timezone.

### 7.2. Chèn sự kiện lúc 09:30 tại Việt Nam

```sql
ALTER SESSION SET TIME_ZONE = '+07:00';

INSERT INTO lab_timezone_events (
    source_system, event_tstz, event_tsltz, event_plain_ts
)
VALUES (
    'PAYMENT_API',
    TO_TIMESTAMP_TZ(
        '2026-11-14 09:30:00 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ),
    TO_TIMESTAMP_TZ(
        '2026-11-14 09:30:00 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ),
    TIMESTAMP '2026-11-14 09:30:00'
);

COMMIT;
```

Kiểm tra:

```sql
SELECT event_id,
       TO_CHAR(event_tstz,
               'YYYY-MM-DD HH24:MI:SS.FF TZH:TZM') AS tstz_value,
       TO_CHAR(event_tsltz,
               'YYYY-MM-DD HH24:MI:SS.FF') AS tsltz_value,
       TO_CHAR(event_plain_ts,
               'YYYY-MM-DD HH24:MI:SS.FF') AS plain_value
FROM lab_timezone_events;
```

Khi session ở `+07:00`, ba cột đều có thể hiển thị phần ngày giờ là `2026-11-14 09:30:00`. Tuy nhiên, chỉ nhìn vào dạng hiển thị này **chưa phản ánh sự khác biệt ngữ nghĩa của ba kiểu**.

### 7.3. Đổi SESSIONTIMEZONE rồi truy vấn lại

```sql
ALTER SESSION SET TIME_ZONE = '-05:00';

SELECT SESSIONTIMEZONE,
       TO_CHAR(event_tstz,
               'YYYY-MM-DD HH24:MI:SS TZH:TZM') AS tstz_value,
       TO_CHAR(event_tsltz,
               'YYYY-MM-DD HH24:MI:SS') AS tsltz_value,
       TO_CHAR(event_plain_ts,
               'YYYY-MM-DD HH24:MI:SS') AS plain_value
FROM lab_timezone_events;
```

Kết quả theo ngữ nghĩa mong đợi:

| Cột | Dạng giờ hiển thị minh họa | Giải thích |
|---|---|---|
| `EVENT_TSTZ` | `2026-11-14 09:30:00 +07:00` | Biểu diễn có offset của giá trị được chèn |
| `EVENT_TSLTZ` | `2026-11-13 21:30:00` | Đã chuyển sang session `-05:00` |
| `EVENT_PLAIN_TS` | `2026-11-14 09:30:00` | Không có timezone để tự đổi |

Nếu session đổi lại `+00:00`, `EVENT_TSLTZ` sẽ được trình bày là `2026-11-14 02:30:00`. **DBTIMEZONE không cần đổi** trong thí nghiệm này.

### 7.4. Chuyển một thời điểm sang UTC bằng SQL

Một cách rõ ràng:

```sql
SELECT event_id,
       TO_CHAR(
           event_tstz AT TIME ZONE 'UTC',
           'YYYY-MM-DD HH24:MI:SS.FF TZH:TZM'
       ) AS event_in_utc
FROM lab_timezone_events;
```

Kết quả cho hàng minh họa là:

```text
2026-11-14 02:30:00.000000 +00:00
```

Có thể trích xuất timestamp ở UTC:

```sql
SELECT event_id,
       SYS_EXTRACT_UTC(event_tstz) AS utc_timestamp
FROM lab_timezone_events;
```

**Chú ý:** `SYS_EXTRACT_UTC` trả về `TIMESTAMP` **không mang timezone**. Giá trị này chỉ được hiểu là UTC vì **quy ước rõ ràng của hàm và contract dữ liệu**. Nếu chuyển nó sang chuỗi/API mà quên ký hiệu `Z` hoặc quy tắc UTC, người nhận lại có thể diễn giải sai.

### 7.5. Chứng minh cùng instant dù offset khác

```sql
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
```

Hai biểu diễn với offset khác nhau có thể tương đương về **thời điểm tuyệt đối**. Đây là nền tảng để join/sắp xếp/suy tính độ trễ của sự kiện từ nhiều hệ thống.

### 7.6. Dọn bảng lab

Khi không cần nữa, trên schema riêng:

```sql
DROP TABLE lab_timezone_events PURGE;
```

`DROP TABLE ... PURGE` xóa hẳn bảng lab (không đưa vào recycle bin). Chỉ chạy với dữ liệu thử đã chủ động tạo.

## 8. Chuẩn hóa thời điểm khi đi qua nhiều hệ thống

Một hệ thống có thể gồm:

```text
Mobile App (Asia/Ho_Chi_Minh)
            |
            | ISO 8601 timestamp có offset/UTC
            v
REST API / Java service (container chạy UTC)
            |
            | JDBC bind có timezone
            v
Oracle Database
            |
            | PDB có DBTIMEZONE riêng theo cấu hình
            v
Báo cáo tại New York / Tokyo / Việt Nam
```

Mục tiêu là **một sự kiện chỉ có một instant**, bất kể ứng dụng nào hiển thị.

### 8.1. Hợp đồng dữ liệu cho sự kiện

Với một **sự kiện đã xảy ra**, hợp đồng trao đổi thường nên là:

- Đầu vào biểu diễn **instant** dưới dạng ISO 8601 có offset rõ ràng, ví dụ `2026-11-14T09:30:00+07:00`.
- Hoặc chuẩn hóa đầu ra thành UTC, ví dụ `2026-11-14T02:30:00Z`.
- Lưu trong database bằng kiểu có ngữ nghĩa instant, như `TIMESTAMP WITH TIME ZONE` hoặc `TIMESTAMP WITH LOCAL TIME ZONE` theo yêu cầu.
- Khi hiển thị, chuyển từ instant sang timezone người dùng, **không tự cộng/trừ 7 giờ bằng số học thủ công**.
- Nếu nghiệp vụ cần biết vùng đã nhập, lưu thêm `source_zone_id` (chẳng hạn `Asia/Ho_Chi_Minh`).

Ví dụ JSON:

```json
{
  "eventId": "PAY-2048",
  "occurredAt": "2026-11-14T02:30:00Z",
  "sourceZoneId": "Asia/Ho_Chi_Minh"
}
```

`occurredAt` là instant; `sourceZoneId` là thông tin vùng nghiệp vụ, không phải một instant thứ hai.

### 8.2. Vì sao không dùng chuỗi “14/11/2026 09:30”?

Chuỗi này thiếu:

- Thông tin timezone/offset.
- Cách diễn giải format giữa các nền tảng (`DD/MM/YYYY` hay `MM/DD/YYYY`).
- Quy ước về phần giây.
- Quy tắc xử lý ngày DST bị thiếu/trùng.
- Thỏa thuận về múi giờ khi người dùng đi du lịch hoặc ứng dụng chuyển server.

**Chuỗi hiển thị dành cho giao diện** không nên đồng thời là định dạng tích hợp chính giữa các hệ thống.

### 8.3. Có nên chỉ lưu UTC?

Đối với log/audit/sự kiện đã xảy ra, việc chuẩn hóa instant sang UTC giúp so sánh và vận hành nhất quán. Tuy nhiên, không phải loại dữ liệu thời gian nào cũng nên chuyển UTC:

| Dữ liệu | Nên lưu gì? | Vì sao |
|---|---|---|
| Thời điểm thanh toán đã phát sinh | Instant UTC hoặc timestamp có timezone | Cần thứ tự tuyệt đối |
| Log nhận request | Instant UTC, tùy yêu cầu thêm client offset | Cần correlation giữa hệ thống |
| Ngày sinh | Calendar date | Không phải thời điểm cần chuyển timezone |
| Giờ mở cửa 08:00 hằng ngày ở Hà Nội | Local time + `Asia/Ho_Chi_Minh` | Giờ theo lịch địa phương |
| Cuộc họp “09:00 mỗi thứ Hai ở New York” | Local date/time rule + zone region | Offset thay đổi theo DST |
| Thời gian xử lý 1.500 milliseconds | Duration/interval hoặc số kèm đơn vị | Không phải một ngày giờ |
| Thời gian hết hạn theo UTC | Instant có timezone | So sánh deadline chính xác |

Nếu dùng UTC cho mọi đối tượng mà bỏ quên **zone region** của lịch lặp, ứng dụng có thể lập lịch sai sau khi vùng đó đổi offset vì DST.

## 9. Chuyển đổi bằng SQL: AT TIME ZONE, FROM_TZ và SYS_EXTRACT_UTC

### 9.1. AT TIME ZONE để biểu diễn cùng instant ở vùng khác

```sql
SELECT
    TO_CHAR(
        TO_TIMESTAMP_TZ(
            '2026-11-14 09:30:00 +07:00',
            'YYYY-MM-DD HH24:MI:SS TZH:TZM'
        ) AT TIME ZONE 'UTC',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ) AS utc_text
FROM dual;
```

Dạng kết quả: `2026-11-14 02:30:00 +00:00`.

Chuyển sang vùng có quy tắc lịch, nếu timezone file Oracle nhận diện tên đó:

```sql
SELECT TO_CHAR(
         TO_TIMESTAMP_TZ(
           '2026-11-14 09:30:00 +07:00',
           'YYYY-MM-DD HH24:MI:SS TZH:TZM'
         ) AT TIME ZONE 'America/New_York',
         'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       ) AS new_york_time
FROM dual;
```

Với ngày trong ví dụ, kết quả thể hiện khoảng `2026-11-13 21:30:00 -05:00`. Với ngày mùa hè, offset vùng này có thể khác.

### 9.2. FROM_TZ gắn vùng/offset cho TIMESTAMP không timezone

Giả sử nhận được:

```text
2026-11-14 09:30:00
```

và hợp đồng nguồn **xác nhận rõ** nó là thời gian địa phương tại Việt Nam. Khi đó có thể diễn giải bằng `FROM_TZ`:

```sql
SELECT TO_CHAR(
         FROM_TZ(
           TIMESTAMP '2026-11-14 09:30:00',
           'Asia/Ho_Chi_Minh'
         ) AT TIME ZONE 'UTC',
         'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       ) AS normalized_utc
FROM dual;
```

Ý nghĩa: từ một **local timestamp không có timezone**, gắn **timezone đã biết**, rồi chuyển sang UTC.

**Không dùng `FROM_TZ` để phỏng đoán timezone cho dữ liệu không rõ nguồn.** Nếu dữ liệu thực chất là UTC mà lại gắn `Asia/Ho_Chi_Minh`, kết quả sẽ bị lệch 7 giờ.

### 9.3. SYS_EXTRACT_UTC dùng khi nào?

`SYS_EXTRACT_UTC` nhận một giá trị timestamp có thông tin timezone và trích xuất UTC timestamp:

```sql
SELECT SYS_EXTRACT_UTC(
         TO_TIMESTAMP_TZ(
           '2026-11-14 09:30:00 +07:00',
           'YYYY-MM-DD HH24:MI:SS TZH:TZM'
         )
       ) AS utc_value
FROM dual;
```

Kết quả là một `TIMESTAMP` **không kèm zone**, vì vậy API/ứng dụng cần giữ hợp đồng “giá trị này là UTC”. Nếu muốn SQL tiếp tục mang timezone metadata, dùng `AT TIME ZONE 'UTC'` trên giá trị TSTZ.

### 9.4. Tránh công thức cộng/trừ giờ cố định

**Không dùng** kiểu:

```sql
-- Chỉ để minh họa cách làm dễ sai:
SELECT SYSDATE - 7/24 FROM dual;
```

để “đổi sang UTC” cho mọi nơi mọi thời điểm. Công thức này:

- Dựa trên giả định timezone server cố định `+07:00`.
- Không xử lý DST của vùng khác.
- Không biết giá trị đầu vào thực sự thuộc timezone nào.
- Dễ sai khi ứng dụng được chuyển sang host khác hoặc thay đổi cấu hình.

Dùng kiểu timestamp có timezone và các phép chuyển đổi do Oracle hỗ trợ.

## 10. Ngày theo múi giờ: không phải lúc nào cũng dài 24 giờ

Một câu hỏi thực tế là: “Lấy giao dịch trong **ngày 14/11/2026 theo giờ Việt Nam**”. Đây là câu hỏi về **calendar day tại một timezone**, không phải lấy 24 giờ tùy ý kể từ midnight UTC.

### 10.1. Truy vấn bằng khoảng nửa mở

Giả sử bảng:

```sql
CREATE TABLE lab_payments (
    payment_id NUMBER PRIMARY KEY,
    paid_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    amount NUMBER(14,2) NOT NULL
);
```

Lấy giao dịch thuộc ngày **14/11/2026 tại UTC+07:00**:

```sql
SELECT payment_id, paid_at, amount
FROM lab_payments
WHERE paid_at >= TO_TIMESTAMP_TZ(
          '2026-11-14 00:00:00 +07:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
  AND paid_at < TO_TIMESTAMP_TZ(
          '2026-11-15 00:00:00 +07:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      );
```

Khoảng được viết **[đầu ngày, đầu ngày hôm sau)** để:

- Bao gồm mọi thời điểm trong ngày, kể cả microsecond/phần giây.
- Không cần giả định cuối ngày là `23:59:59.999999`.
- Tránh biến đổi trực tiếp cột `PAID_AT` bằng `TO_CHAR`/`TRUNC` ở predicate, giúp optimizer có cơ hội dùng index range scan/partition pruning khi phù hợp.

Điều kiện này so sánh hai giá trị có timezone/instant, nên độc lập với timezone hiển thị của session trong phạm vi ngữ nghĩa được định rõ.

### 10.2. Một ngày tại vùng DST có thể dài 23 hoặc 25 giờ

Tại vùng có daylight saving time, giờ địa phương có lúc tiến một giờ hoặc lùi một giờ. Vì vậy, một ngày lịch cụ thể có thể không tương đương `24 * 60 * 60` giây.

Ví dụ khu vực `America/New_York` có ngày chuyển DST trong năm 2026. Nếu cần lấy **mọi event thuộc ngày địa phương** tại New York, hãy xác định cả **midnight đầu ngày** và **midnight đầu ngày kế tiếp** theo đúng region:

```sql
SELECT payment_id, paid_at
FROM lab_payments
WHERE paid_at >= FROM_TZ(
          TIMESTAMP '2026-11-01 00:00:00',
          'America/New_York'
      )
  AND paid_at < FROM_TZ(
          TIMESTAMP '2026-11-02 00:00:00',
          'America/New_York'
      );
```

Ở ngày DST kết thúc, khoảng giữa hai midnight trong cùng zone có thể kéo dài **25 giờ thực**. Cách dùng ranh giới theo region sẽ phản ánh quy tắc đó; cộng cứng 24 giờ từ đầu ngày có thể bỏ sót một phần dữ liệu.

Cần dùng **Oracle timezone file** đã cập nhật và hỗ trợ đúng region để áp dụng quy tắc DST của từng năm.

### 10.3. Chuyển từ instant sang ngày báo cáo

Nếu sự kiện lưu ở TSTZ, ngày báo cáo theo Việt Nam có thể xác định bằng cách chuyển sang region rồi lấy phần ngày cho **hiển thị/tổng hợp**. Ví dụ về hiển thị:

```sql
SELECT payment_id,
       TO_CHAR(
           paid_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
           'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       ) AS paid_at_vietnam
FROM lab_payments;
```

Nhưng khi lọc theo khoảng và cần dùng index, ưu tiên chuyển **giá trị biên** sang instant trước, thay vì áp dụng hàm cho mọi hàng trong cột indexed.

## 11. DST: thời gian không tồn tại và thời gian trùng lặp

Đây là trường hợp phân biệt **timezone region** với **offset** trở nên bắt buộc.

### 11.1. “Giờ không tồn tại” lúc DST bắt đầu

Khi đồng hồ địa phương nhảy từ `01:59:59` lên `03:00:00`, giá trị như `02:30` trong ngày đổi giờ có thể **không tồn tại** ở region đó.

Nếu hệ thống nhận:

```text
2026-03-08 02:30:00 America/New_York
```

thì cần quy tắc nghiệp vụ: báo lỗi để người dùng chọn lại, đẩy lên giờ hợp lệ tiếp theo, hay dùng một cách giải quyết đã thỏa thuận.

Không nên coi tất cả chuỗi `YYYY-MM-DD HH24:MI:SS` đều xác định được instant duy nhất.

### 11.2. “Giờ trùng lặp” lúc DST kết thúc

Khi đồng hồ lùi một giờ, local time `01:30` có thể xảy ra **hai lần**. Với New York ngày 01/11/2026, hai biểu diễn sau tương ứng hai instant khác nhau:

```text
2026-11-01 01:30:00 -04:00
2026-11-01 01:30:00 -05:00
```

Trong Oracle:

```sql
SELECT
    SYS_EXTRACT_UTC(
        TO_TIMESTAMP_TZ(
            '2026-11-01 01:30:00 -04:00',
            'YYYY-MM-DD HH24:MI:SS TZH:TZM'
        )
    ) AS first_occurrence_utc,
    SYS_EXTRACT_UTC(
        TO_TIMESTAMP_TZ(
            '2026-11-01 01:30:00 -05:00',
            'YYYY-MM-DD HH24:MI:SS TZH:TZM'
        )
    ) AS second_occurrence_utc
FROM dual;
```

Hai UTC timestamp lệch nhau **một giờ**. Nếu chỉ lưu `TIMESTAMP '2026-11-01 01:30:00'`, không thể phân biệt hai lần.

Với việc tạo/sửa lịch, ứng dụng nên yêu cầu/ghi nhận timezone region và cách giải quyết ambiguous local time. Oracle cũng có tham số `ERROR_ON_OVERLAP_TIME` cho một số thao tác liên quan thời gian bị trùng ở DST; sử dụng theo tài liệu của phiên bản khi cần kiểm soát hành vi nhập.

### 11.3. Vì sao offset hiện tại không giải quyết lịch tương lai?

Nếu đặt lịch “09:00 mỗi thứ Hai tại New York”, offset của phiên hiện tại có thể là `-05:00`; nhiều tháng sau có thể là `-04:00`. Nếu chỉ lưu offset hiện tại và lặp trên UTC, giờ hẹn địa phương có thể dịch thành 10:00 hoặc 08:00 sau khi DST đổi.

Giải pháp có thể là lưu:

```text
local_time = 09:00
zone_id = America/New_York
recurrence_rule = WEEKLY;BYDAY=MO
```

Khi tính từng lần hẹn, ứng dụng dùng quy tắc timezone tương ứng để xác định instant. Các lần đã xảy ra nên lưu instant riêng để audit không bị nhập nhằng.

## 12. NLS ảnh hưởng định dạng nhưng không thay ý nghĩa instant

Oracle có các thiết lập **NLS (National Language Support)** cho cách hiển thị và phân giải ngày giờ, như:

- `NLS_DATE_FORMAT`
- `NLS_TIMESTAMP_FORMAT`
- `NLS_TIMESTAMP_TZ_FORMAT`
- `NLS_DATE_LANGUAGE`
- `NLS_TERRITORY`

Có thể xem thông số của session:

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
```

Và thử thay đổi **chỉ trong session**:

```sql
ALTER SESSION SET NLS_DATE_FORMAT =
    'YYYY-MM-DD HH24:MI:SS';

ALTER SESSION SET NLS_TIMESTAMP_TZ_FORMAT =
    'YYYY-MM-DD HH24:MI:SS.FF TZH:TZM';
```

Điều này thay đổi cách **hiển thị** các giá trị khi client dùng định dạng mặc định. Nó **không** có nghĩa chuyển tất cả ngày giờ đang lưu sang timezone khác.

### 12.1. Tránh chuyển kiểu ngầm theo NLS

SQL dễ gây lỗi:

```sql
-- Không nên phụ thuộc NLS_DATE_FORMAT:
WHERE created_at = '14/11/2026'
```

Nếu cột là `DATE`:

```sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
```

Nếu nhận chuỗi thời gian có offset:

```sql
TO_TIMESTAMP_TZ(
  '2026-11-14 09:30:00 +07:00',
  'YYYY-MM-DD HH24:MI:SS TZH:TZM'
)
```

Sử dụng literal hoặc hàm chuyển đổi có **format mask cụ thể**, hoặc tốt hơn là dùng **bind variable có kiểu phù hợp** từ ứng dụng. Cách này giảm phụ thuộc NLS của kết nối.

### 12.2. TO_CHAR chỉ nên là lớp biểu diễn

Ví dụ:

```sql
SELECT TO_CHAR(
         SYSTIMESTAMP AT TIME ZONE 'UTC',
         'YYYY-MM-DD"T"HH24:MI:SS.FF3"Z"'
       ) AS iso_utc_text
FROM dual;
```

Dấu `Z` trong format trên là **ký tự hiển thị được đặt literal**; nó chỉ đúng vì biểu thức **đã chuyển sang UTC** trước đó. Không gắn `"Z"` vào timestamp giờ Việt Nam rồi gọi nó là UTC.

Khi trao đổi JSON/API, thư viện chuẩn ISO 8601 của ứng dụng thường là lựa chọn tốt hơn tự ghép chuỗi, vì có thể xử lý precision, offset và serialization một cách nhất quán.

### 12.3. NLS_DATE_LANGUAGE và tên tháng

Ví dụ:

```sql
SELECT TO_DATE(
         '14-NOV-2026',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE=ENGLISH'
       ) AS parsed_date
FROM dual;
```

Khi format chứa tên tháng/tuần bằng chữ, session có thể cần đúng ngôn ngữ. Sử dụng literal `DATE '2026-11-14'` hoặc định dạng số ISO giúp tránh nhiều lỗi liên quan ngôn ngữ.

## 13. DATE, TIMESTAMP và timezone trong JDBC/Java

Trong ứng dụng Java, các kiểu trong `java.time` giúp biểu diễn ngữ nghĩa tách bạch:

| Ý nghĩa nghiệp vụ | Java | Oracle phù hợp |
|---|---|---|
| Một ngày lịch | `LocalDate` | Oracle `DATE` với quy ước phần giờ 00:00:00 |
| Local date-time chưa có zone | `LocalDateTime` | `TIMESTAMP` |
| Instant tuyệt đối | `Instant` | TSTZ/TSLTZ hoặc UTC timestamp theo contract |
| Ngày giờ với offset | `OffsetDateTime` | `TIMESTAMP WITH TIME ZONE` |
| Ngày giờ gắn region | `ZonedDateTime` | TSTZ cộng thỏa thuận giữ region nếu cần |
| Time zone region | `ZoneId` | Lưu như metadata nghiệp vụ riêng nếu cần |

Khả năng mapping cụ thể của JDBC 4.2, Oracle JDBC driver, phiên bản Java và kiểu Oracle có thể khác nhau. Cần thử với driver thực tế, nhất là khi dùng `TIMESTAMP WITH LOCAL TIME ZONE` hoặc muốn giữ nguyên timezone region.

### 13.1. Chuẩn hóa ở tầng ứng dụng

```java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

class TimeExample {
    public static void main(String[] args) {
        OffsetDateTime fromVietnam =
            OffsetDateTime.parse("2026-11-14T09:30:00+07:00");

        Instant instant = fromVietnam.toInstant();
        OffsetDateTime utc = fromVietnam.withOffsetSameInstant(
            ZoneOffset.UTC
        );

        System.out.println(instant);
        // 2026-11-14T02:30:00Z

        System.out.println(utc);
        // 2026-11-14T02:30Z (biểu diễn có thể lược giây 00)
    }
}
```

`withOffsetSameInstant` đổi cách biểu diễn nhưng **giữ nguyên instant**. Khác với việc thay offset mà giữ nguyên local wall-clock, vốn có thể tạo ra một instant khác.

### 13.2. Ghi vào Oracle bằng PreparedStatement

Giả sử bảng:

```sql
CREATE TABLE lab_java_events (
    event_id NUMBER PRIMARY KEY,
    occurred_at TIMESTAMP(6) WITH TIME ZONE NOT NULL
);
```

Ví dụ với Oracle JDBC driver hỗ trợ ánh xạ `OffsetDateTime`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

class SaveEvent {
    static void insert(Connection connection, long id,
                       OffsetDateTime occurredAt) throws Exception {
        String sql = """
            INSERT INTO lab_java_events (event_id, occurred_at)
            VALUES (?, ?)
            """;

        // Chuyển về UTC trước khi bind là quy ước ứng dụng.
        OffsetDateTime utc = occurredAt.withOffsetSameInstant(
            ZoneOffset.UTC
        );

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);
            ps.setObject(2, utc);
            ps.executeUpdate();
        }
    }
}
```

Đoạn ví dụ sử dụng Java text block (phiên bản Java hỗ trợ) và JDBC driver có hỗ trợ binding tương ứng. Trong ứng dụng thực, cần đặt transaction/`commit` theo cơ chế quản lý giao dịch của hệ thống. Driver cũ có thể yêu cầu API Oracle JDBC riêng cho TSTZ.

**Không chuyển timestamp sang chuỗi theo `toString()` rồi ghép vào SQL.** Bind đúng kiểu giúp tránh phụ thuộc NLS và SQL injection.

### 13.3. Đọc instant, hiển thị theo người dùng

Ví dụ logic ở Java:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant instant = Instant.parse("2026-11-14T02:30:00Z");

ZonedDateTime vietnam = instant.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh")
);
ZonedDateTime newYork = instant.atZone(
    ZoneId.of("America/New_York")
);

System.out.println(vietnam); // 09:30 tại Việt Nam
System.out.println(newYork); // 21:30 ngày hôm trước tại New York
```

Thư viện `java.time` sử dụng timezone database của runtime Java. Oracle dùng timezone file của Oracle. Đối với các vùng có thay đổi luật DST, cần quản lý **phiên bản timezone data** của các môi trường để giảm chênh lệch khi chuyển đổi ngày giờ.

### 13.4. Connection pool và session time zone

Một ứng dụng có nhiều kết nối nên chọn chiến lược rõ:

- **Toàn hệ thống dùng UTC:** cấu hình session timezone `+00:00` nhất quán tại lúc tạo hoặc nhận connection, dùng TSTZ/TSLTZ theo nhu cầu; hiển thị ở UI theo người dùng.
- **Session dùng timezone người dùng:** cần đặt lại trên mỗi lượt mượn kết nối và tránh rò rỉ timezone giữa hai request.
- **Dựa vào timezone mặc định máy:** dễ gây sai lệch khi triển khai lên container/server mới, nên chỉ dùng khi đã được kiểm soát và ghi rõ.

Nếu code thay đổi `ALTER SESSION SET TIME_ZONE` trong một request rồi trả connection về pool mà không reset, người dùng kế tiếp có thể nhận giờ hiển thị theo timezone của người trước. Đây là lỗi không liên quan dữ liệu đã lưu nhưng gây báo cáo sai.

## 14. Tính thời lượng qua múi giờ và DST

Giả sử một yêu cầu bắt đầu tại Việt Nam và kết thúc tại Mỹ. Nếu dùng `TIMESTAMP` không timezone để trừ hai local wall-clock, kết quả có thể vô nghĩa.

Nên lưu **hai instant có timezone** rồi lấy độ chênh.

Ví dụ:

```sql
SELECT
    TO_TIMESTAMP_TZ(
        '2026-11-14 09:30:00 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    )
    -
    TO_TIMESTAMP_TZ(
        '2026-11-14 02:15:00 +00:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ) AS elapsed
FROM dual;
```

Đây là khoảng **15 phút**, bất kể hai timestamp được viết theo múi giờ khác nhau. Oracle biểu diễn hiệu thời gian timestamp có timezone dưới dạng interval phù hợp.

### 14.1. Khoảng thời gian khác calendar arithmetic

- “Sau 24 giờ” là một duration tuyệt đối.
- “Ngày hôm sau lúc 09:00 địa phương” là phép toán lịch theo region.

Tại vùng có DST, hai khái niệm có thể cho instant khác nhau. Nếu hệ thống cần nhắc lịch vào 09:00 hằng ngày theo region, phải tính ngày tiếp theo **trong local calendar và timezone region**, không mặc định cộng 24 giờ vào instant trước đó.

### 14.2. Không tính bằng chuỗi

Tránh lấy `SUBSTR` hoặc so sánh từ điển giữa timestamp dạng `'DD/MM/YYYY HH24:MI'`. Dùng đúng kiểu Oracle, sau đó chuyển sang format mong muốn tại ranh giới hiển thị/trao đổi.

## 15. Truy vấn, index và partition theo thời gian

### 15.1. Giữ predicate trên cột thời gian gốc

Giả sử:

```sql
CREATE INDEX ix_lab_payments_paid_at
ON lab_payments (paid_at);
```

Để lọc một ngày theo múi giờ cụ thể, chọn cận trước:

```sql
SELECT payment_id
FROM lab_payments
WHERE paid_at >= TO_TIMESTAMP_TZ(
          '2026-11-14 00:00:00 +07:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
  AND paid_at < TO_TIMESTAMP_TZ(
          '2026-11-15 00:00:00 +07:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      );
```

Hạn chế biểu thức như:

```sql
-- Dùng cho hiển thị thì được, nhưng không phải mặc định tốt nhất
-- để lọc hàng triệu dòng trên cột có index thông thường.
WHERE TO_CHAR(paid_at, 'YYYY-MM-DD') = '2026-11-14'
```

Trong trường hợp này, `TO_CHAR` còn diễn giải ngày theo timezone của kiểu/session và không xác định rõ “ngày theo vùng nào”. Hàm trên cột cũng có thể cản đường dùng index B-tree thông thường, trừ khi có index/virtual column phù hợp.

### 15.2. Truy vấn tối ưu phụ thuộc plan thực tế

Không phải cứ dùng khoảng thời gian là chắc chắn Oracle chọn index range scan. Optimizer còn xét:

- Mức chọn lọc điều kiện.
- Statistics/histogram.
- Kích thước bảng và index.
- Partitioning.
- I/O, parallel query và các phương án access path.

Có thể xem plan bằng:

```sql
EXPLAIN PLAN FOR
SELECT payment_id
FROM lab_payments
WHERE paid_at >= TO_TIMESTAMP_TZ(
          '2026-11-14 00:00:00 +07:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
  AND paid_at < TO_TIMESTAMP_TZ(
          '2026-11-15 00:00:00 +07:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      );

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` là plan ước tính; khi cần benchmark, đo thống kê lần chạy thật và so sánh điều kiện đồng nhất.

### 15.3. Partition theo ngày thuộc timezone nào?

Nếu dữ liệu partition theo UTC date nhưng báo cáo luôn theo ngày Việt Nam, mỗi ngày báo cáo địa phương có thể đi qua hai partition UTC tại ranh giới. Đây không phải bug, mà là hệ quả khác nhau giữa **ngày theo UTC** và **ngày theo vùng nghiệp vụ**.

Cần xác định:

- Partition dựa trên UTC instant hay local business date.
- Có cần cột `business_date` (calendar date theo một timezone nhất định) để phân vùng/đối soát không.
- Cần khả năng báo cáo nhiều timezone hay chỉ một timezone nghiệp vụ cố định.
- Có dữ liệu thuộc vùng DST khiến ngày báo cáo thay đổi độ dài không.

Không ép ngày báo cáo cho mọi thị trường bằng `TRUNC(SYS_EXTRACT_UTC(...))` nếu nghiệp vụ yêu cầu ngày địa phương.

## 16. Vấn đề khi tích hợp API, ETL và hệ thống cũ

### 16.1. Đầu vào chỉ chứa local timestamp

Giả sử CSV:

```csv
event_id,occurred_at
1001,2026-11-14 09:30:00
```

CSV không chứa timezone. Trước khi nhập:

1. Xác định **nguồn** là quốc gia/vùng nào.
2. Xác định tên vùng/offset tại thời điểm bản ghi xảy ra.
3. Nếu DST có giờ trùng/không tồn tại, quyết định cách xử lý.
4. Chuyển sang instant chuẩn khi ghi vào hệ thống đích.
5. Ghi provenance hoặc region nếu cần audit.

Nếu không có thông tin về timezone nguồn, **không thể phục hồi chính xác instant chỉ từ local wall-clock**. Phải liên hệ hệ thống nguồn hoặc quy ước dữ liệu được chứng minh.

### 16.2. Unix epoch

Nhiều hệ thống trao đổi thời điểm bằng số epoch:

- Epoch seconds: số giây từ mốc 1970-01-01T00:00:00Z.
- Epoch milliseconds: số mili giây từ cùng mốc.

Cả hai biểu thị instant, **không mang timezone hiển thị**. Khi truyền qua API, phải ghi rõ đơn vị:

```json
{
  "occurredAtEpochMillis": 1794623400000,
  "timeZone": "Asia/Ho_Chi_Minh"
}
```

*Số epoch trong ví dụ chỉ mang tính minh họa cho dạng dữ liệu; không dùng làm dữ kiện đối chiếu với các mốc giờ của bài khi chưa tính toán theo cùng một instant.*

Tránh tên field mơ hồ như `timestamp` khi một bên hiểu giây và bên khác hiểu mili giây. Lỗi nhầm đơn vị có thể khiến sự kiện rơi vào năm hoàn toàn khác.

### 16.3. Log và tracing giữa nhiều service

Để tương quan log, nên dùng:

- Timestamp trong UTC có ký hiệu `Z` hoặc offset rõ ràng.
- Request/trace ID để nối sự kiện.
- Đồng bộ clock giữa host/container.
- Độ chính xác phần giây đáp ứng yêu cầu, ví dụ milliseconds hoặc microseconds.
- Khi cần, ghi thêm local timezone/region để phục vụ điều tra với người vận hành địa phương.

Không nên đặt thứ tự tuyệt đối của sự kiện phân tán chỉ từ thời gian local text, vì đồng hồ các host có thể lệch và các sự kiện có thể cùng timestamp ở precision thấp.

### 16.4. Các hệ quản trị khác nhau có ngữ nghĩa khác nhau

Tên kiểu `TIMESTAMP` hoặc `DATETIME` trong một RDBMS khác không bảo đảm đồng nhất với Oracle. Ví dụ một số hệ thống có kiểu tự chuẩn hóa timezone hoặc hiển thị theo session theo cách khác.

Khi ETL từ Oracle sang hệ thống khác, cần ghi rõ:

```text
Oracle column type
  -> Ngữ nghĩa dữ liệu (instant, local time, date, duration)
  -> Chuyển đổi timezone/precision tường minh
  -> Kiểu dữ liệu đích
  -> Contract API/report
```

Chỉ ánh xạ **tên kiểu** theo bảng tương ứng là chưa đủ. Nên dùng bộ dữ liệu mẫu gồm ranh giới ngày, phần giây, UTC±offset và ngày DST để thử.

## 17. Kiểm tra timezone file và phiên bản DST của Oracle

Oracle lưu các định nghĩa timezone region trong **timezone files**. Quy tắc DST của quốc gia/vùng có thể được cập nhật theo thời gian; hai hệ thống dùng timezone data khác phiên bản có thể giải thích một ngày trong quá khứ/tương lai khác nhau nếu luật đã thay đổi.

Khi có quyền đọc view:

```sql
SELECT filename, version
FROM v$timezone_file;
```

Để kiểm tra tên region có được hỗ trợ:

```sql
SELECT tzname, tzabbrev
FROM v$timezone_names
WHERE tzname IN (
    'Asia/Ho_Chi_Minh',
    'America/New_York',
    'UTC'
)
ORDER BY tzname, tzabbrev;
```

Các view này có thể đòi quyền truy cập phù hợp. Nếu Oracle trả lỗi như `ORA-01882: timezone region not found`, cần kiểm tra tên vùng, timezone file và môi trường client; không đổi sang offset cố định cho mọi ngày khi nghiệp vụ có DST.

Nâng cấp timezone file có thể kéo theo công việc với dữ liệu `TIMESTAMP WITH TIME ZONE` và các công cụ/quy trình do Oracle cung cấp, ví dụ **`DBMS_DST`**. Đây là hoạt động quản trị cần backup, kế hoạch đổi phiên bản và kiểm tra tác động; không tự chạy upgrade DST chỉ vì một kết quả hiển thị khó hiểu.

### 17.1. So sánh Oracle và Java tzdata

Java dùng bộ dữ liệu timezone của runtime; Oracle dùng timezone file của Oracle. Nếu một quốc gia ban hành thay đổi DST có hiệu lực trong tương lai, Java và Oracle **có thể tạm thời khác quy tắc** nếu bản cập nhật được triển khai không đồng đều.

Để tránh sai khác:

1. Xác định version Oracle/JDBC/JDK và timezone data đang dùng.
2. Kiểm thử các vùng/tương lai liên quan đến nghiệp vụ.
3. Cập nhật timezone data theo hướng dẫn nhà cung cấp.
4. Lưu instant chính xác cho sự kiện đã xảy ra; lưu region riêng cho lịch hẹn tương lai.

## 18. Lỗi Oracle và triệu chứng thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| `SESSIONTIMEZONE` khác `DBTIMEZONE` | Hai giá trị có vai trò khác nhau | Bình thường; hiểu kiểu cột và ngữ nghĩa dữ liệu |
| `CURRENT_TIMESTAMP` khác `SYSTIMESTAMP` vài giờ | Session timezone khác timezone máy chủ | So sánh cùng instant sau khi chuyển timezone; không sửa clock vô cớ |
| `CURRENT_DATE` và `SYSDATE` khác ngày | Ranh giới ngày bị vượt khi đổi múi giờ | Xác định câu hỏi đang dùng ngày theo session hay server |
| Cột TSLTZ hiển thị khác sau khi `ALTER SESSION SET TIME_ZONE` | TSLTZ chuyển sang timezone session khi đọc | Đúng thiết kế; dùng TSTZ nếu cần giữ offset nguồn |
| Cột TIMESTAMP không đổi khi session timezone đổi | TIMESTAMP không lưu timezone | Cần hợp đồng xác định timezone nguồn khi diễn giải |
| ORA-01882 `timezone region not found` | Tên vùng không được nhận diện theo timezone files/cấu hình | Kiểm tra region hỗ trợ và phiên bản timezone data |
| ORA-01878 `specified field not found in datetime or interval` trong thời gian đổi DST | Có thể đang chỉ định local time không tồn tại khi DST nhảy | Kiểm tra ngày/region/offset và chính sách xử lý |
| ORA-01883 / vấn đề overlap time tùy tình huống | Có thể liên quan ambiguous DST time hoặc conversion | Kiểm tra timezone region và quy tắc phân giải giờ trùng |
| ORA-01861 `literal does not match format string` | Chuỗi ngày giờ không khớp format mask | Dùng literal/TO_TIMESTAMP_TZ có format tường minh |
| ORA-01843 `not a valid month` | Chuỗi ngày hoặc NLS date language sai | Dùng ISO literal hoặc mask/ngôn ngữ tường minh |
| `WHERE date_col = DATE '...'` trả ít hơn mong đợi | DATE chứa cả giờ | Dùng khoảng `>= đầu ngày` và `< đầu ngày sau` |
| Báo cáo “mất” đơn vào cuối ngày | Nhầm ngày UTC với ngày địa phương | Xác định timezone báo cáo và tính lại hai ranh giới |
| Java trả dữ liệu khác SQL Developer | JDBC session timezone/NLS, mapping driver hoặc format khác | Log cấu hình an toàn, kiểm tra `SESSIONTIMEZONE` và kiểu cột |
| Giờ lệch đúng 7 hoặc 8 tiếng | Giờ local bị gắn nhầm UTC/offset hoặc chuyển đổi hai lần | Xác minh contract đầu vào, kiểu cột và nơi áp dụng chuyển đổi |
| Một giờ xuất hiện hai lần khi DST kết thúc | Local wall time trùng | Lưu offset hoặc xác định instant rõ; quản lý region |

Thông báo lỗi chỉ cung cấp điểm khởi đầu chẩn đoán. Cùng một triệu chứng có thể đến từ ứng dụng, Oracle SQL, timezone file, cấu hình session hoặc dữ liệu nguồn.

## 19. Các lỗi thiết kế nên tránh

### 19.1. Coi DBTIMEZONE là “giờ hiện tại của server”

Sai vì `DBTIMEZONE` là cấu hình timezone được sử dụng bởi database, không phải phép đo đồng hồ. Để kiểm tra thời gian hệ thống, dùng `SYSTIMESTAMP`; để biết timezone của phiên, dùng `SESSIONTIMEZONE`.

### 19.2. Ghi mọi sự kiện bằng LOCALTIMESTAMP vào TIMESTAMP rồi coi là UTC

`LOCALTIMESTAMP` là local time của session **không chứa timezone**. Nếu session đang ở `+07:00`, giá trị `09:30` không tự trở thành `02:30Z` khi lưu vào cột TIMESTAMP.

Chỉ sử dụng cột TIMESTAMP theo quy ước UTC khi **nguồn giá trị đã được chuyển chính xác sang UTC** và contract được kiểm soát.

### 19.3. Đổi DBTIMEZONE để sửa báo cáo người dùng

Nếu người dùng cần xem giờ địa phương, hướng xử lý thường là thiết lập timezone đúng cho session/truy vấn hoặc chuyển instant trong ứng dụng. Thay đổi `DBTIMEZONE` không phải phép chữa lỗi hiển thị và có thể gây rủi ro cho dữ liệu TSLTZ đang tồn tại.

### 19.4. Lưu giờ địa phương không kèm timezone nguồn

`'2026-11-14 09:30:00'` không đủ để xác định instant khi nguồn ở nhiều quốc gia. Phải mang offset/region hoặc có contract khác đủ mạnh để diễn giải đúng.

### 19.5. Áp dụng UTC cho ngày sinh và lịch lặp một cách máy móc

Ngày sinh là calendar date; lịch lặp theo giờ địa phương cần timezone region và quy tắc DST. Chuyển mọi giá trị sang UTC rồi bỏ thông tin gốc có thể làm mất ý nghĩa nghiệp vụ.

### 19.6. Truy vấn cả ngày bằng TRUNC không xác định timezone

`TRUNC(event_tsltz)` có thể dựa vào cách timestamp được diễn giải trong session; với báo cáo từ nhiều múi giờ, kết quả nhóm ngày có thể khác nhau. Ngoài ra, dùng hàm trên cột có thể ảnh hưởng đường truy cập index.

Hãy quyết định ngày theo **region nào**, tính ranh giới và so sánh trên instant.

### 19.7. Chỉ lưu offset cho lịch tương lai có DST

Offset `-05:00` là thông tin của một thời điểm, không đại diện mọi mùa tại New York. Lưu timezone region và lịch địa phương cho quy tắc tái diễn.

### 19.8. Ghép SQL từ chuỗi timestamp của API

Nối chuỗi tạo rủi ro NLS, SQL injection và parse lỗi. Dùng binding ngày giờ có kiểu, hoặc chuyển đổi tường minh bằng format mask.

## 20. Quy trình chẩn đoán lệch thời gian giữa hai hệ thống

Giả sử ứng dụng A cho biết sự kiện xảy ra lúc `09:30`, trong khi báo cáo Oracle hiển thị `02:30` hoặc `21:30`.

### Bước 1 — Xác minh instant nguồn

Yêu cầu xác định rõ giá trị đi vào từ A:

```text
2026-11-14T09:30:00+07:00
```

hoặc:

```text
2026-11-14T02:30:00Z
```

Nếu chỉ có `2026-11-14 09:30:00`, tìm contract timezone của A.

### Bước 2 — Xem kiểu dữ liệu cột Oracle

```sql
SELECT column_name,
       data_type,
       data_scale,
       nullable
FROM user_tab_columns
WHERE table_name = 'LAB_TIMEZONE_EVENTS'
ORDER BY column_id;
```

Phân biệt TSTZ, TSLTZ và TIMESTAMP/DATE. Không đoán theo tên `CREATED_AT`.

### Bước 3 — Kiểm tra timezone và NLS của session thực sự

```sql
SELECT DBTIMEZONE,
       SESSIONTIMEZONE,
       SYSTIMESTAMP,
       CURRENT_TIMESTAMP
FROM dual;
```

Đồng thời:

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT'
);
```

Phải kiểm tra **connection ứng dụng bị lỗi** hoặc tạo kết nối cùng cấu hình; phiên SQL Developer của DBA có thể không giống JDBC session.

### Bước 4 — Xuất giá trị dưới dạng có ngữ nghĩa rõ

Với TSTZ:

```sql
SELECT event_id,
       TO_CHAR(event_tstz,
               'YYYY-MM-DD HH24:MI:SS.FF TZH:TZM') AS original_view,
       TO_CHAR(event_tstz AT TIME ZONE 'UTC',
               'YYYY-MM-DD HH24:MI:SS.FF TZH:TZM') AS utc_view
FROM lab_timezone_events;
```

Với TSLTZ, thử ở hai session timezone xác định và quan sát biến đổi. Với TIMESTAMP không timezone, phải dựa vào contract nguồn chứ không thể biết instant chỉ từ nội dung cột.

### Bước 5 — Tìm vị trí chuyển đổi

Theo vết:

```text
UI input
  -> API payload
  -> Java DTO / OffsetDateTime / LocalDateTime
  -> JDBC binder
  -> Oracle column type
  -> SQL query / report timezone
  -> JSON output
  -> UI rendering
```

Kiểm tra có nơi nào:

- Bỏ offset.
- Chuyển sang UTC hai lần.
- Gắn offset cho dữ liệu vốn đã là UTC.
- Lấy timezone server thay cho timezone user.
- Tự cộng/trừ giờ cố định.
- Dùng session timezone còn sót từ request khác trong connection pool.

### Bước 6 — So sánh hai hệ thống bằng cùng một instant

Chuẩn hóa hai phía sang UTC rồi so sánh:

```text
A: 2026-11-14T02:30:00Z
B: 2026-11-14T02:30:00Z
=> Cùng instant, chỉ khác presentation.
```

Nếu sau chuyển đổi vẫn lệch vài phút/giây, kiểm tra đồng bộ clock, precision, rounding/truncation và thời điểm lấy mẫu.

## 21. Kiểm tra thực hành theo ba kịch bản

### Kịch bản A — Hai người dùng ở hai timezone

Một người dùng tại Việt Nam và một tại New York cùng xem event `2026-11-14T02:30:00Z`.

Yêu cầu:

1. Xác định giờ hiển thị tại Việt Nam và New York.
2. Giải thích vì sao `EVENT_TSLTZ` có thể hiển thị hai ngày lịch khác nhau.
3. Xác định vì sao `EVENT_TSTZ` vẫn có thể giữ biểu diễn offset gốc.
4. Viết SQL chuyển TSTZ về UTC bằng `AT TIME ZONE`.

**Đáp án định hướng:** Việt Nam `09:30 14/11/2026`; New York `21:30 13/11/2026` tại offset `-05:00`. TSLTZ phụ thuộc session khi truy xuất; TSTZ lưu thông tin timezone/offset của giá trị. Hai màn hình vẫn nói về một instant.

### Kịch bản B — Lọc doanh thu theo ngày Việt Nam

Bảng `LAB_PAYMENTS` lưu `PAID_AT TIMESTAMP WITH TIME ZONE`. Viết câu SQL lấy toàn bộ đơn của ngày 14/11/2026 theo UTC+07.

**Đáp án:** Dùng khoảng nửa mở với start `2026-11-14 00:00:00 +07:00` và end `2026-11-15 00:00:00 +07:00`, rồi so sánh trực tiếp với cột `PAID_AT`.

Giải thích vì sao `DATE '2026-11-14'` trên cột TSTZ không thể mặc nhiên đại diện ngày lịch Việt Nam trong mọi session.

### Kịch bản C — Lịch lặp tại vùng DST

Một ứng dụng cần đặt lịch `01:30` tại New York ngày DST kết thúc.

Yêu cầu:

1. Giải thích vì sao local time `01:30` có thể là hai instant.
2. So sánh `01:30 -04:00` và `01:30 -05:00`.
3. Đề xuất thông tin cần hỏi người dùng để chọn đúng lần.
4. Trình bày vì sao lưu offset duy nhất không đủ để tạo lịch hằng tuần trong nhiều tháng.

**Đáp án định hướng:** Giờ địa phương lặp; hai offset xác định hai instant khác nhau một giờ. Với lịch lặp phải lưu vùng `America/New_York` và quy tắc xử lý DST.

### Kịch bản D — DATE, TIMESTAMP hay TSTZ?

Chọn kiểu cho:

| Thuộc tính | Nhu cầu | Gợi ý |
|---|---|---|
| `date_of_birth` | Ngày sinh, không có giờ nghiệp vụ | `DATE` với quy tắc chỉ ngày |
| `payment_completed_at` | Instant thanh toán toàn cầu | `TIMESTAMP WITH TIME ZONE` |
| `shift_start_local` | Giờ bắt đầu ca theo lịch tại từng chi nhánh | `TIMESTAMP`/time-of-day + zone ID, theo cách thiết kế |
| `duration_ms` | Độ trễ xử lý tính mili giây | `NUMBER` kèm đơn vị hoặc interval phù hợp |
| `created_at_user_view` | Hiển thị instant theo timezone session | Truy vấn/chuyển từ TSTZ, hoặc TSLTZ khi chính sách session được kiểm soát |

Một thuộc tính “giờ” chưa đủ để kết luận phải dùng `TIMESTAMP`. Hãy xác định nó là **calendar time, instant hay duration**.

### Kịch bản E — Session pool bị rò cấu hình

Service web cho phép mỗi request gọi:

```sql
ALTER SESSION SET TIME_ZONE = '+07:00';
```

nhưng không reset trước khi trả connection về pool. Request tiếp theo thuộc người dùng New York lấy lại connection và đọc TSLTZ.

**Câu hỏi:** Vì sao kết quả sai và sửa ở đâu?

**Định hướng:** Session physical giữ timezone cũ. Cần khởi tạo/đặt lại session context cho mỗi lần dùng connection, hoặc thiết kế pool cố định UTC và chuyển timezone ở tầng hiển thị. Sửa `DBTIMEZONE` không giải quyết vấn đề này.

## 22. Bảng ghi nhớ các phép đo và phép chuyển đổi

| Muốn biết | Biểu thức/công cụ | Điều không được suy ra |
|---|---|---|
| Timezone session hiện tại | `SELECT SESSIONTIMEZONE FROM dual` | Không chứng minh timezone của người dùng cuối |
| Database timezone cấu hình | `SELECT DBTIMEZONE FROM dual` | Không phải giờ hiện tại server |
| Thời gian server có timezone | `SYSTIMESTAMP` | Không nhất thiết là giờ theo session |
| Thời gian hiện tại theo session | `CURRENT_TIMESTAMP` | Không tự chứng minh local time của client đầu cuối |
| Oracle DATE theo session | `CURRENT_DATE` | Không chứa timezone trong kiểu kết quả |
| Chuyển TSTZ sang UTC có timezone | `tstz_col AT TIME ZONE 'UTC'` | Không thay đổi dữ liệu gốc của cột |
| Trích UTC dưới dạng TIMESTAMP | `SYS_EXTRACT_UTC(tstz_col)` | Kết quả không còn timezone metadata |
| Gắn vùng cho local TIMESTAMP | `FROM_TZ(local_ts, 'Asia/Ho_Chi_Minh')` | Chỉ đúng khi vùng của đầu vào được biết chắc |
| Kiểm tra timezone file | `V$TIMEZONE_FILE` | Không tự đồng bộ tzdata với Java |
| Lọc ngày địa phương | Hai cận TSTZ theo vùng, khoảng nửa mở | Không mặc định ngày nào cũng dài 24 giờ |
| Đọc kiểu Oracle | `USER_TAB_COLUMNS` | Không đủ xác định contract timezone của dữ liệu cũ |
| Xem cách hiển thị mặc định | `NLS_SESSION_PARAMETERS` | Định dạng không phải timezone conversion |

## 23. Quy trình thiết kế timezone cho hệ thống mới

Có thể áp dụng tuần tự:

1. **Phân loại từng trường thời gian**: calendar date, local time/recurrence, instant hay duration.
2. **Xác định miền dữ liệu và precision**: tới giây, mili giây hay micro giây; có cần timezone region nguồn không.
3. **Chọn kiểu Oracle**: `DATE` cho ngày lịch; `TIMESTAMP WITH TIME ZONE`/`TIMESTAMP WITH LOCAL TIME ZONE` cho instant; `TIMESTAMP` cho local date-time theo contract rõ.
4. **Chọn chuẩn trao đổi**: ISO 8601 `Z`/offset cho instant, truyền zone ID khi cần quy tắc lịch.
5. **Thiết lập timezone session nhất quán**: đặc biệt trong Java JDBC và connection pools.
6. **Chọn timezone báo cáo**: UTC hay vùng nghiệp vụ; viết truy vấn theo khoảng nửa mở.
7. **Kiểm thử DST và ranh giới ngày**: Việt Nam – UTC – New York, ngày tiến/lùi đồng hồ và phần giây.
8. **Quản lý timezone data**: Oracle timezone file, JDK tzdata và chính sách cập nhật.
9. **Quan sát/ghi log an toàn**: trace ID và UTC timestamp có offset, không phụ thuộc text format của session.
10. **Ghi rõ contract trong tài liệu API/schema**: tránh để nhóm khác suy ra ý nghĩa từ tên cột.

**Kết quả mong đợi:** Một sự kiện có một instant ổn định, được Oracle lưu trữ và truy vấn không nhập nhằng; mỗi người dùng có thể xem giờ theo vùng phù hợp; những dữ liệu không phải instant (ngày sinh, lịch lặp, thời lượng) vẫn giữ đúng ngữ nghĩa riêng.

## 24. Tài liệu Oracle để đối chiếu theo phiên bản

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — kiểu `DATE`, `TIMESTAMP WITH TIME ZONE`, `TIMESTAMP WITH LOCAL TIME ZONE`; các hàm `SESSIONTIMEZONE`, `DBTIMEZONE`, `FROM_TZ`, `SYS_EXTRACT_UTC` và phép `AT TIME ZONE`.
- [Oracle Database Globalization Support Guide](https://docs.oracle.com/en/database/) — NLS, timezone regions, DST và timezone files.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — `V$TIMEZONE_FILE`, `V$TIMEZONE_NAMES`, `NLS_SESSION_PARAMETERS`.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/) — ánh xạ dữ liệu ngày giờ, session timezone và Java/JDBC.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/) — cấu hình database timezone và các giới hạn khi thay đổi.

**Ghi nhớ quan trọng:** `SESSIONTIMEZONE` điều khiển ngữ cảnh thời gian của **session**; `DBTIMEZONE` là thuộc tính timezone của **database**, đặc biệt liên quan cơ chế lưu `TIMESTAMP WITH LOCAL TIME ZONE`. Khi tích hợp nhiều hệ thống, cần chuẩn hóa **instant**, không chỉ làm cho các chuỗi ngày giờ trông giống nhau. Những quyết định về timezone phải dựa trên ý nghĩa dữ liệu và phải được kiểm chứng trên đúng phiên bản Oracle/JDBC đang sử dụng.

