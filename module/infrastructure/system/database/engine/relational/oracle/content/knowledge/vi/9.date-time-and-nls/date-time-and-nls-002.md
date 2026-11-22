# NLS_DATE_FORMAT, NLS_TIMESTAMP_FORMAT và nguy cơ phụ thuộc cấu hình phiên trong Oracle Database

Trong Oracle Database, một cột `DATE` hoặc `TIMESTAMP` lưu **giá trị ngày giờ theo kiểu dữ liệu**, còn chuỗi như `14/11/2026`, `2026-11-14` hay `14-NOV-26 08:30:00` chỉ là **cách biểu diễn** giá trị đó. Hai tham số NLS thường gặp, **`NLS_DATE_FORMAT`** và **`NLS_TIMESTAMP_FORMAT`**, chi phối cách Oracle chuyển đổi mặc định giữa ngày giờ và ký tự trong **phiên làm việc (session)**.

Điểm nguy hiểm là một câu SQL có thể chạy đúng trên máy của lập trình viên nhưng thất bại hoặc diễn giải dữ liệu khác trên server, kết nối JDBC, job chạy nền hoặc một phiên dùng cấu hình vùng khác. Ví dụ:

```sql
-- SQL phụ thuộc NLS_DATE_FORMAT của session:
SELECT TO_DATE('14/11/2026') AS event_date
FROM   dual;
```

Nếu phiên dùng `DD/MM/YYYY`, chuỗi trên có thể được hiểu là ngày 14 tháng 11 năm 2026. Với phiên đòi hỏi `YYYY-MM-DD`, câu lệnh có thể lỗi chuyển đổi. Cách viết có ý nghĩa rõ ràng là:

```sql
SELECT TO_DATE('14/11/2026', 'DD/MM/YYYY') AS event_date
FROM   dual;
```

Bài học thuộc nhóm **Ngày giờ và NLS** của Oracle Database quan hệ. Nội dung giải thích cơ chế session NLS, kiểu dữ liệu, cách xem/thiết lập tham số, ví dụ lỗi thực tế và cách viết SQL ít phụ thuộc vào cấu hình máy hoặc người dùng.

## 1. Phân biệt dữ liệu ngày giờ với định dạng hiển thị

### 1.1. DATE, TIMESTAMP và chuỗi ký tự khác nhau

Oracle cung cấp nhiều kiểu ngày giờ, trong đó ba nhóm quan trọng là:

| Kiểu dữ liệu | Thông tin được lưu | Độ chính xác và đặc điểm |
| --- | --- | --- |
| `DATE` | Năm, tháng, ngày, **giờ, phút, giây** | Chính xác đến giây; không lưu phần giây lẻ hoặc múi giờ |
| `TIMESTAMP(p)` | Ngày, giờ, phút, giây và **phần giây lẻ** | `p` là độ chính xác phần giây, từ 0 đến 9; mặc định thường là 6 |
| `TIMESTAMP WITH TIME ZONE` | Ngày giờ có thông tin múi giờ/offset | Có quy tắc lưu trữ, hiển thị và so sánh liên quan đến múi giờ |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Thời điểm được chuẩn hóa theo cơ chế của database và hiển thị theo múi giờ phiên | Giá trị hiển thị có thể thay đổi khi `SESSIONTIMEZONE` thay đổi |

Riêng **`DATE` của Oracle có cả giờ, phút, giây**, mặc dù nhiều công cụ chỉ hiển thị ngày. Ví dụ, một cột `DATE` có thể chứa thời điểm `2026-11-14 16:25:40` nhưng SQL*Plus hiển thị `14-NOV-26` nếu format mặc định không có thành phần giờ.

Đối với dữ liệu ngày giờ, cần phân biệt ba tầng:

1. **Kiểu dữ liệu thực của cột/biểu thức**: `DATE`, `TIMESTAMP`, `VARCHAR2`...
2. **Giá trị ngày giờ được lưu**: ví dụ ngày 14/11/2026 lúc 16:25:40.
3. **Chuỗi trình bày**: `14-NOV-26`, `2026-11-14 16:25:40` hoặc `14/11/2026 04:25:40 PM`.

Thay đổi tầng 3 **không tự động thay đổi tầng 2**.

### 1.2. NLS_DATE_FORMAT điều khiển điều gì?

`NLS_DATE_FORMAT` là **session parameter** mô tả định dạng mặc định để Oracle chuyển đổi `DATE` và chuỗi khi không chỉ định format model tường minh.

Ví dụ:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY HH24:MI:SS';

SELECT SYSDATE AS current_server_date
FROM   dual;
```

Khi công cụ hiển thị `SYSDATE` theo chuyển đổi ký tự mặc định của session, kết quả có dạng:

```text
CURRENT_SERVER_DATE
-------------------
14/11/2026 15:45:12
```

Ngày giờ ở ví dụ chỉ để minh họa, không phải số liệu hiện hành. Khi đổi thành:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';

SELECT SYSDATE AS current_server_date
FROM   dual;
```

Cùng loại giá trị `DATE` có thể chỉ được hiển thị như `2026-11-14`, khiến giờ/phút/giây không xuất hiện. **Thông tin giờ không bị xóa khỏi `SYSDATE`**; chỉ có format hiển thị không đưa phần đó ra chuỗi.

### 1.3. NLS_TIMESTAMP_FORMAT điều khiển điều gì?

`NLS_TIMESTAMP_FORMAT` tương tự nhưng áp dụng cho **`TIMESTAMP` không chứa time zone**.

Ví dụ:

```sql
ALTER SESSION SET NLS_TIMESTAMP_FORMAT =
    'DD/MM/YYYY HH24:MI:SS.FF3';

SELECT LOCALTIMESTAMP AS session_timestamp
FROM   dual;
```

`LOCALTIMESTAMP` trả về một giá trị `TIMESTAMP` theo múi giờ session, **không kèm thông tin time zone trong kiểu trả về**, nên đây là hàm thích hợp để minh họa `NLS_TIMESTAMP_FORMAT`.

Khi format chứa `FF3`, phần giây lẻ được trình bày với ba chữ số; nếu dùng `FF6` thì hiển thị sáu chữ số phần giây. Giá trị TIMESTAMP bên trong không được tạo lại chỉ vì thay đổi độ dài phần hiển thị.

**Không dùng `SYSTIMESTAMP` để chứng minh trực tiếp `NLS_TIMESTAMP_FORMAT`.** `SYSTIMESTAMP` trả về `TIMESTAMP WITH TIME ZONE`, có định dạng mặc định riêng do `NLS_TIMESTAMP_TZ_FORMAT` điều khiển.

### 1.4. Các tham số liên quan không được nhầm lẫn

| Tham số | Tác động chính | Ví dụ |
| --- | --- | --- |
| `NLS_DATE_FORMAT` | Chuyển đổi mặc định cho `DATE` | `YYYY-MM-DD HH24:MI:SS` |
| `NLS_TIMESTAMP_FORMAT` | Chuyển đổi mặc định cho `TIMESTAMP` | `YYYY-MM-DD HH24:MI:SS.FF6` |
| `NLS_TIMESTAMP_TZ_FORMAT` | Chuyển đổi mặc định cho `TIMESTAMP WITH TIME ZONE` | `YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM` |
| `NLS_DATE_LANGUAGE` | Ngôn ngữ tên tháng, tên ngày và một số thành phần văn bản của định dạng ngày giờ | `AMERICAN` hoặc cấu hình ngôn ngữ khác |
| `NLS_TERRITORY` | Quy ước vùng, bao gồm các giá trị format mặc định khi không được thiết lập tường minh | `AMERICA`, `VIETNAM` nếu được bản Oracle hỗ trợ |
| `SESSIONTIMEZONE` | Múi giờ hiện tại của session, tác động đến một số giá trị và phép tính có time zone | `+07:00`, hoặc tên vùng |
| `NLS_CALENDAR` | Hệ lịch theo cấu hình NLS ở những thao tác liên quan | `GREGORIAN` |

Nếu cần xử lý time zone, **NLS format chỉ xác định chuỗi trình bày**, không thay thế việc chọn đúng kiểu `TIMESTAMP WITH TIME ZONE` hay `TIMESTAMP WITH LOCAL TIME ZONE`.

## 2. Tại sao cấu hình phiên dễ khác nhau?

### 2.1. Nhiều lớp cấu hình có thể ảnh hưởng NLS

Một Oracle Database có thể được sử dụng bởi nhiều ứng dụng:

```text
                Oracle Database
                      |
        +-------------+-------------+
        |             |             |
    SQL*Plus A     SQLcl B      Java/JDBC C
        |             |             |
  Session NLS A  Session NLS B  Session NLS C
        |             |             |
  DD/MM/YYYY     YYYY-MM-DD      Giá trị do driver,
                                 môi trường và phiên
                                 quyết định
```

Thông số NLS mặc định chịu ảnh hưởng của cấu hình database/instance, vùng lãnh thổ và có thể bị **client/driver ghi đè lúc thiết lập kết nối**. Sau đó, ứng dụng hoặc script còn có thể dùng `ALTER SESSION` để thay đổi giá trị. Cơ chế ưu tiên chi tiết phụ thuộc loại NLS parameter, Oracle Client và driver sử dụng.

Vì vậy:

- Hai phiên cùng kết nối một PDB có thể có **`NLS_DATE_FORMAT` khác nhau**.
- Một phiên có thể đổi format trong lúc làm việc, khiến SQL trước và sau đó được diễn giải khác.
- Ứng dụng có **connection pool** có thể sử dụng lại session đã thay đổi cấu hình từ tác vụ trước nếu không quản lý trạng thái phiên.
- Một job chạy bởi scheduler hoặc batch có thể không nhận cùng thiết lập client mà lập trình viên dùng khi chạy thủ công.

**Không coi format của SQL Developer/SQL*Plus trên laptop là cấu hình cố định của toàn database.**

### 2.2. Kiểm tra NLS của session đang chạy

Cách trực tiếp nhất là truy vấn `NLS_SESSION_PARAMETERS`:

```sql
SELECT parameter, value
FROM   nls_session_parameters
WHERE  parameter IN (
         'NLS_DATE_FORMAT',
         'NLS_TIMESTAMP_FORMAT',
         'NLS_TIMESTAMP_TZ_FORMAT',
         'NLS_DATE_LANGUAGE',
         'NLS_TERRITORY',
         'NLS_CALENDAR'
       )
ORDER  BY parameter;
```

Kết quả **minh họa**:

```text
PARAMETER                    VALUE
---------------------------  ---------------------------------------
NLS_CALENDAR                 GREGORIAN
NLS_DATE_FORMAT              DD/MM/YYYY HH24:MI:SS
NLS_DATE_LANGUAGE            AMERICAN
NLS_TERRITORY                AMERICA
NLS_TIMESTAMP_FORMAT         YYYY-MM-DD HH24:MI:SS.FF6
NLS_TIMESTAMP_TZ_FORMAT      YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM
```

Giá trị thực phải lấy từ phiên đang điều tra. Không nên dựa vào bản chụp cấu hình của một phiên khác rồi suy ra format mà ứng dụng đang dùng.

### 2.3. NLS_SESSION_PARAMETERS khác NLS_DATABASE_PARAMETERS

Một số view thường gặp:

| View | Thông tin chính | Dùng để làm gì? |
| --- | --- | --- |
| `NLS_SESSION_PARAMETERS` | Giá trị NLS đang có hiệu lực với **session hiện tại** | Chẩn đoán SQL phụ thuộc NLS |
| `NLS_INSTANCE_PARAMETERS` | Giá trị NLS ở mức instance theo cấu hình phù hợp | Đối chiếu cấu hình instance |
| `NLS_DATABASE_PARAMETERS` | Thông tin NLS ở mức database | Xem bối cảnh cấu hình database |

Các view không thay thế cho nhau. Trong nhiều môi trường, thông số NLS của session có thể khác giá trị database/instance do thiết lập của client/driver hoặc `ALTER SESSION`.

Khi cần biết **một câu SQL cụ thể sẽ diễn giải chuỗi ngày giờ thế nào**, phải kiểm tra **session thực thi chính câu SQL đó**, không chỉ đọc một tham số từ tài khoản DBA khác.

### 2.4. Thay đổi phiên bằng ALTER SESSION

Ví dụ cấu hình thử nghiệm trong một cửa sổ SQL*Plus:

```sql
ALTER SESSION SET NLS_DATE_FORMAT =
    'YYYY-MM-DD HH24:MI:SS';

ALTER SESSION SET NLS_TIMESTAMP_FORMAT =
    'YYYY-MM-DD HH24:MI:SS.FF6';

SELECT parameter, value
FROM   nls_session_parameters
WHERE  parameter IN ('NLS_DATE_FORMAT', 'NLS_TIMESTAMP_FORMAT');
```

`ALTER SESSION` thay đổi **session hiện tại**, không cập nhật dữ liệu đang lưu và không tự sửa NLS của những session khác. Sau khi client ngắt kết nối, session mới có thể nhận lại các giá trị mặc định từ cấu hình/driver.

Cần có quyền sử dụng lệnh theo chính sách database. Không đặt lệnh `ALTER SESSION` như một biện pháp bắt buộc cho mọi truy vấn nếu có thể dùng ANSI literals, format model tường minh hoặc bind variables.

## 3. Format model của Oracle: đọc chính xác từng ký hiệu

### 3.1. Các phần tử thường dùng

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `YYYY` | Năm bốn chữ số | `2026` |
| `MM` | Tháng dạng số, từ 01 đến 12 | `11` |
| `DD` | Ngày trong tháng | `14` |
| `HH24` | Giờ dạng 24 giờ, từ 00 đến 23 | `16` |
| `HH12` hoặc `HH` | Giờ dạng 12 giờ | `04` |
| `MI` | Phút, từ 00 đến 59 | `25` |
| `SS` | Giây, từ 00 đến 59 | `40` |
| `FF` hoặc `FFn` | Phần giây lẻ; `n` xác định số chữ số mong muốn khi format | `FF3` → `123` |
| `MON` | Tên tháng viết tắt theo ngôn ngữ | `NOV` khi dùng tiếng Anh |
| `MONTH` | Tên tháng đầy đủ theo ngôn ngữ | `NOVEMBER` khi dùng tiếng Anh |
| `AM` / `PM` | Chỉ buổi theo định dạng 12 giờ | `PM` |
| `TZH:TZM` | Phần offset múi giờ dưới dạng giờ:phút trong format phù hợp | `+07:00` |
| `RR` | Quy tắc nhận diện thế kỷ từ năm hai chữ số | Có thể gây sai lệch khi dữ liệu không rõ năm |
| `"T"` | Ký tự chữ T cố định khi định dạng chuỗi kiểu ISO | `2026-11-14T16:25:40` |

**Lỗi rất phổ biến:** `MM` là **month**, còn `MI` mới là **minute**. Ví dụ:

```sql
SELECT TO_CHAR(
         TIMESTAMP '2026-11-14 16:25:40.123456',
         'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS formatted_timestamp
FROM   dual;
```

Kết quả mong đợi:

```text
2026-11-14 16:25:40.123456
```

Nếu viết `HH24:MM:SS`, phần giữa sẽ được hiểu là tháng chứ không phải phút.

### 3.2. Giờ trong DATE không đồng nghĩa format có giờ

Một giá trị `DATE` có thể chứa đầy đủ giờ phút giây:

```sql
SELECT TO_CHAR(
         TO_DATE('2026-11-14 16:25:40',
                 'YYYY-MM-DD HH24:MI:SS'),
         'YYYY-MM-DD HH24:MI:SS'
       ) AS full_date_value
FROM   dual;
```

Trong khi đó, nếu chọn format hiển thị `YYYY-MM-DD`, giờ sẽ bị ẩn khỏi **chuỗi đầu ra**:

```sql
SELECT TO_CHAR(
         TO_DATE('2026-11-14 16:25:40',
                 'YYYY-MM-DD HH24:MI:SS'),
         'YYYY-MM-DD'
       ) AS date_only_text
FROM   dual;
```

Giá trị gốc của biểu thức `DATE` vẫn chứa `16:25:40`. Không cần cộng lại phần giờ vì nó chưa bị mất.

### 3.3. FF chỉ có ý nghĩa với TIMESTAMP

`DATE` không lưu phần giây lẻ. Khi cần dữ liệu như `16:25:40.123456`, dùng `TIMESTAMP(6)` và format với `FF6`.

```sql
SELECT TO_CHAR(
         TO_TIMESTAMP('2026-11-14 16:25:40.123456',
                      'YYYY-MM-DD HH24:MI:SS.FF6'),
         'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS full_timestamp_value
FROM   dual;
```

Kết quả minh họa:

```text
2026-11-14 16:25:40.123456
```

Nếu dữ liệu ngày giờ được lưu vào một cột `DATE` thay vì `TIMESTAMP`, phần giây lẻ không được giữ lại chỉ bằng cách đặt `NLS_DATE_FORMAT` có thêm ký hiệu mong muốn.

### 3.4. Tên tháng phụ thuộc ngôn ngữ

Ví dụ chuỗi `14-NOV-2026` có tháng dạng chữ. Để tránh lệ thuộc `NLS_DATE_LANGUAGE`, nêu rõ ngôn ngữ khi chuyển đổi:

```sql
SELECT TO_DATE(
         '14-NOV-2026',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE=ENGLISH'
       ) AS event_date
FROM   dual;
```

Với đầu ra dạng chữ, có thể làm tương tự:

```sql
SELECT TO_CHAR(
         DATE '2026-11-14',
         'DD MON YYYY',
         'NLS_DATE_LANGUAGE=ENGLISH'
       ) AS english_date
FROM   dual;
```

Nếu không có yêu cầu tên tháng bằng chữ, format dạng số `YYYY-MM-DD` thường đơn giản và ổn định hơn giữa các ngôn ngữ.

### 3.5. Tránh suy đoán với năm hai chữ số

Chuỗi `14/11/26` không cho biết rõ năm **1926**, **2026** hay một thế kỷ khác nếu thiếu ngữ cảnh. Các format `YY` và `RR` có quy tắc xử lý năm khác nhau; `RR` sử dụng cơ chế suy đoán thế kỷ dựa trên năm hiện tại và phần năm nhập vào.

Trong hệ thống trao đổi dữ liệu hoặc lưu trữ lâu dài:

- Dùng **`YYYY`** cho năm bốn chữ số.
- Yêu cầu dữ liệu đầu vào chứa đủ năm.
- Không dựa vào `RR` để “tự sửa” dữ liệu lịch sử có năm thiếu thế kỷ.

## 4. Chuyển đổi ngầm định: nguồn gốc của nhiều lỗi

### 4.1. Oracle có thể tự chuyển chuỗi sang DATE/TIMESTAMP

Xét một bảng:

```sql
CREATE TABLE nls_event_log (
    event_id NUMBER PRIMARY KEY,
    event_date DATE NOT NULL,
    event_ts TIMESTAMP(6) NOT NULL
);
```

Một câu `INSERT` viết như sau có vẻ dễ hiểu nhưng dễ phụ thuộc phiên:

```sql
-- Không khuyến nghị: literal dạng chuỗi cho cột DATE.
INSERT INTO nls_event_log (event_id, event_date, event_ts)
VALUES (
    1,
    '14/11/2026 16:25:40',
    '14/11/2026 16:25:40.123456'
);
```

Đây là **hai chuỗi ký tự**. Oracle phải chuyển đổi ngầm định từ `VARCHAR2` sang `DATE` và `TIMESTAMP` theo các quy tắc của session. Câu lệnh có thể thành công trong một phiên và lỗi trong phiên khác.

Cách viết rõ ràng:

```sql
INSERT INTO nls_event_log (event_id, event_date, event_ts)
VALUES (
    1,
    TO_DATE('2026-11-14 16:25:40', 'YYYY-MM-DD HH24:MI:SS'),
    TO_TIMESTAMP('2026-11-14 16:25:40.123456',
                 'YYYY-MM-DD HH24:MI:SS.FF6')
);

COMMIT;
```

Các phép chuyển đổi này quy định tường minh cả phần giá trị đầu vào lẫn cách giải mã, giúp kết quả độc lập với `NLS_DATE_FORMAT`/`NLS_TIMESTAMP_FORMAT` của session đối với định dạng số đã chọn.

### 4.2. Không viết TO_DATE mà thiếu format khi nhập chuỗi không chuẩn hóa

Hai lệnh sau có ý nghĩa khác nhau:

```sql
-- Phụ thuộc NLS_DATE_FORMAT:
SELECT TO_DATE('14/11/2026') FROM dual;

-- Rõ format, không phụ thuộc NLS_DATE_FORMAT cho cấu trúc chuỗi:
SELECT TO_DATE('14/11/2026', 'DD/MM/YYYY') FROM dual;
```

Tương tự với `TIMESTAMP`:

```sql
-- Phụ thuộc NLS_TIMESTAMP_FORMAT:
SELECT TO_TIMESTAMP('14/11/2026 16:25:40.123') FROM dual;

-- Rõ format:
SELECT TO_TIMESTAMP(
         '14/11/2026 16:25:40.123',
         'DD/MM/YYYY HH24:MI:SS.FF3'
       ) FROM dual;
```

Điểm khác biệt nằm ở **chuyển đổi ngầm định và chuyển đổi mặc định**. Với SQL không tự chỉ định format, một thay đổi cấu hình phiên đủ làm thay đổi cách diễn giải chuỗi.

### 4.3. Các lỗi ngày giờ thường gặp

| Mã lỗi | Ý nghĩa thường gặp | Nguyên nhân nên kiểm tra |
| --- | --- | --- |
| `ORA-01861` | Literal không khớp format string | Dùng chuỗi `DD/MM/YYYY` khi format đang chờ `YYYY-MM-DD` |
| `ORA-01843` | Tháng không hợp lệ | Nhầm `DD/MM` với `MM/DD`, tên tháng không phù hợp ngôn ngữ, dữ liệu tháng sai |
| `ORA-01830` | Format kết thúc trước khi chuyển đổi hết chuỗi | Chuỗi có thêm giờ/giây nhưng format model không mô tả |
| `ORA-01858` | Có ký tự không phải số ở vị trí cần chữ số | Dữ liệu đầu vào chứa chữ/ký hiệu không phù hợp |
| `ORA-01847` | Ngày trong tháng không hợp lệ | Ví dụ một ngày không tồn tại trong tháng |
| `ORA-01821` | Format không được nhận diện | Format model có ký hiệu không hợp lệ hoặc kết hợp sai |

Mã lỗi cho biết **nhóm vấn đề**, không nhất thiết chứng minh tham số NLS là nguyên nhân duy nhất. Cần xem chuỗi đầu vào, format model, kiểu dữ liệu cột và session NLS thực tế.

### 4.4. Dùng FX khi cần khớp khuôn dạng chặt chẽ

Oracle có modifier `FX` (*format exact*) để yêu cầu khớp định dạng chặt hơn trong nhiều trường hợp. Ví dụ:

```sql
SELECT TO_DATE('2026-11-14',
               'FXYYYY-MM-DD') AS exact_date
FROM   dual;
```

Khi làm sạch dữ liệu từ file import, API hoặc hệ thống bên ngoài, có thể dùng `FX` để tránh việc Oracle linh hoạt chấp nhận một số dấu phân cách hoặc khoảng trống không đúng quy ước đầu vào.

`FX` chỉ xác định **mức chặt chẽ của chuyển đổi chuỗi**, không thay thế kiểm tra giá trị ngày hợp lệ, time zone, quy tắc nghiệp vụ hay xử lý lỗi của ứng dụng.

### 4.5. Không gọi TO_DATE trên một giá trị đã là DATE

Một lỗi phổ biến là:

```sql
-- Sai ý tưởng: SYSDATE đã có kiểu DATE.
SELECT TO_DATE(SYSDATE, 'YYYY-MM-DD')
FROM   dual;
```

`TO_DATE` được thiết kế để giải mã dữ liệu ký tự thành DATE. Với `SYSDATE` đã là DATE, Oracle có thể phải **chuyển ngầm DATE → chuỗi theo NLS_DATE_FORMAT**, rồi mới giải mã chuỗi đó bằng mask `YYYY-MM-DD`. Nếu chuỗi trung gian không khớp format, có thể lỗi hoặc diễn giải sai.

Tùy mục tiêu, dùng một trong các cách:

```sql
-- Cần giá trị DATE hiện tại: giữ nguyên kiểu.
SELECT SYSDATE FROM dual;

-- Cần chuỗi được trình bày với format cố định:
SELECT TO_CHAR(SYSDATE, 'YYYY-MM-DD') FROM dual;

-- Cần bỏ phần giờ nhưng vẫn giữ kiểu DATE:
SELECT TRUNC(SYSDATE) FROM dual;
```

Đây là sự khác biệt giữa **chuyển đổi kiểu**, **định dạng thành chuỗi** và **thao tác trên giá trị thời gian**.

## 5. ANSI DATE/TIMESTAMP literals: không cần NLS session format

Oracle hỗ trợ các **ANSI datetime literals**, có cú pháp cố định và rõ ràng.

### 5.1. DATE literal

```sql
SELECT DATE '2026-11-14' AS event_day
FROM   dual;
```

Cú pháp `DATE 'YYYY-MM-DD'` được Oracle phân tích theo cú pháp literal, **không dựa vào `NLS_DATE_FORMAT`**. Giá trị có phần giờ mặc định `00:00:00`.

Do DATE literal chỉ có phần ngày theo cú pháp này, **không viết**:

```sql
-- Không phải cú pháp DATE literal hợp lệ:
-- DATE '2026-11-14 16:25:40'
```

Nếu cần giờ, phút, giây của kiểu DATE, dùng `TO_DATE` với format tường minh hoặc bind parameter đúng kiểu.

### 5.2. TIMESTAMP literal

```sql
SELECT TIMESTAMP '2026-11-14 16:25:40.123456' AS event_time
FROM   dual;
```

Literal `TIMESTAMP` chứa ngày giờ và phần giây lẻ mà không cần `NLS_TIMESTAMP_FORMAT`. Đây là lựa chọn rõ ràng khi giá trị cố định nằm trong câu SQL, chẳng hạn dữ liệu minh họa hoặc mốc thời gian trong một phép kiểm thử.

Không đặt literal SQL vào dấu nháy kép; cú pháp đúng sử dụng từ khóa kiểu `TIMESTAMP` và chuỗi literal trong dấu nháy đơn.

### 5.3. Chọn cách nhập theo dữ liệu nguồn

| Tình huống | Cách khuyến nghị | Vì sao? |
| --- | --- | --- |
| Ngày cố định không có giờ | `DATE '2026-11-14'` | ANSI literal, độc lập NLS_DATE_FORMAT |
| Mốc thời gian cố định có phần giây | `TIMESTAMP '2026-11-14 16:25:40.123456'` | Độc lập NLS_TIMESTAMP_FORMAT |
| Chuỗi từ file theo khuôn dạng đã biết | `TO_DATE(text,'YYYY-MM-DD')` hoặc `TO_TIMESTAMP(text,'...')` | Chuyển đổi tường minh và có thể kiểm soát lỗi |
| Tham số từ ứng dụng Java/Python | **Bind variable đúng kiểu ngày giờ** | Tránh ghép chuỗi, giảm lệ thuộc NLS và tăng an toàn |
| Cần hiển thị cho người dùng | `TO_CHAR(date_value, format)` | Quy định rõ định dạng đầu ra |
| Giá trị đã là DATE/TIMESTAMP | Giữ nguyên kiểu dữ liệu | Không chuyển qua chuỗi rồi parse lại |

## 6. Nguy cơ khi viết điều kiện WHERE

### 6.1. So sánh ngày giờ với chuỗi không định dạng

Ví dụ:

```sql
SELECT event_id, event_date
FROM   nls_event_log
WHERE  event_date >= '14/11/2026';
```

Ở đây `event_date` là `DATE`, còn `'14/11/2026'` là ký tự. Oracle phải quyết định chuyển đổi ngầm định và có thể dựa vào `NLS_DATE_FORMAT` của session. Vì thế câu SQL có nguy cơ chạy khác nhau giữa các phiên.

Viết rõ:

```sql
SELECT event_id, event_date
FROM   nls_event_log
WHERE  event_date >= DATE '2026-11-14';
```

Nếu cần mốc có giờ:

```sql
SELECT event_id, event_date
FROM   nls_event_log
WHERE  event_date >=
       TO_DATE('2026-11-14 16:00:00', 'YYYY-MM-DD HH24:MI:SS');
```

### 6.2. So sánh bằng một ngày thường bỏ sót các bản ghi có giờ

Giả sử `event_date` chứa `2026-11-14 16:25:40`. Điều kiện:

```sql
WHERE event_date = DATE '2026-11-14'
```

chỉ tìm các giá trị đúng bằng **nửa đêm** đầu ngày, vì `DATE '2026-11-14'` có phần giờ là `00:00:00`. Các bản ghi khác trong ngày sẽ không khớp.

Cách phổ biến để lọc **toàn bộ một ngày** là khoảng nửa mở:

```sql
SELECT event_id, event_date
FROM   nls_event_log
WHERE  event_date >= DATE '2026-11-14'
AND    event_date <  DATE '2026-11-15';
```

Điều kiện lấy mọi thời điểm từ đầu ngày 14 đến trước đầu ngày 15 theo ngữ nghĩa kiểu DATE, không cần biết session hiển thị ngày dưới format nào.

### 6.3. TIMESTAMP và phần giây lẻ

Với cột `TIMESTAMP`, dùng cùng nguyên tắc và literal đúng kiểu:

```sql
SELECT event_id, event_ts
FROM   nls_event_log
WHERE  event_ts >= TIMESTAMP '2026-11-14 00:00:00'
AND    event_ts <  TIMESTAMP '2026-11-15 00:00:00';
```

Không viết `BETWEEN ... 23:59:59` rồi cho rằng đã lấy hết dữ liệu trong ngày: `TIMESTAMP` có thể chứa các giá trị như `23:59:59.999999`, nằm sau `23:59:59`. Khoảng nửa mở với giới hạn trên là đầu ngày tiếp theo tránh được lỗi này.

### 6.4. TRUNC(column) và chỉ mục

Một cách lọc theo ngày khác:

```sql
SELECT event_id
FROM   nls_event_log
WHERE  TRUNC(event_date) = DATE '2026-11-14';
```

Câu lệnh này có ý nghĩa hợp lệ về mặt kết quả, nhưng việc đặt hàm `TRUNC` lên **cột** có thể hạn chế khả năng dùng **B-tree index thông thường trên chính cột**. Oracle có thể cần function-based index hoặc chiến lược truy xuất khác. Điều kiện dạng range `event_date >= ... AND event_date < ...` thường thuận lợi hơn cho truy vấn dùng index range scan, tùy execution plan và dữ liệu thực tế.

Không chọn cách viết SQL chỉ vì thấy màn hình hiển thị ngày không có giờ; cần dựa trên kiểu dữ liệu và mục tiêu lọc.

### 6.5. Nguy cơ khi sắp xếp chuỗi thay vì giá trị ngày giờ

Ví dụ:

```sql
SELECT TO_CHAR(event_date, 'DD/MM/YYYY') AS displayed_date
FROM   nls_event_log
ORDER  BY displayed_date;
```

Kết quả được **sắp xếp theo chuỗi**, không bảo đảm thứ tự thời gian trên nhiều tháng/năm theo format `DD/MM/YYYY`.

Nếu muốn sắp xếp theo thời gian thực:

```sql
SELECT TO_CHAR(event_date, 'DD/MM/YYYY') AS displayed_date
FROM   nls_event_log
ORDER  BY event_date;
```

**Cột/biểu thức ngày giờ** nên được giữ nguyên kiểu khi so sánh, sắp xếp, nhóm theo mốc thời gian; chỉ chuyển `TO_CHAR` tại ranh giới hiển thị hoặc xuất dữ liệu đã định dạng.

## 7. TO_CHAR, TO_DATE và TO_TIMESTAMP: đúng chiều chuyển đổi

### 7.1. Sơ đồ chuyển đổi

```text
        Chuỗi ký tự (VARCHAR2)
               |
               | TO_DATE(text, format)
               v
              DATE
               |
               | TO_CHAR(date, format)
               v
        Chuỗi ký tự (VARCHAR2)


        Chuỗi ký tự (VARCHAR2)
               |
               | TO_TIMESTAMP(text, format)
               v
            TIMESTAMP
               |
               | TO_CHAR(timestamp, format)
               v
        Chuỗi ký tự (VARCHAR2)
```

**`TO_DATE` / `TO_TIMESTAMP` giải mã chuỗi thành kiểu ngày giờ**; **`TO_CHAR` biến giá trị ngày giờ thành văn bản**. Không dùng hai chiều này lẫn lộn.

### 7.2. Format rõ ở cả đầu vào và đầu ra

```sql
SELECT
    TO_CHAR(
      TO_DATE('2026-11-14 16:25:40',
              'YYYY-MM-DD HH24:MI:SS'),
      'DD/MM/YYYY HH24:MI:SS'
    ) AS display_vn,

    TO_CHAR(
      TO_TIMESTAMP('2026-11-14 16:25:40.123456',
                   'YYYY-MM-DD HH24:MI:SS.FF6'),
      'YYYY-MM-DD"T"HH24:MI:SS.FF3'
    ) AS display_iso_like
FROM dual;
```

Kết quả minh họa:

```text
DISPLAY_VN           DISPLAY_ISO_LIKE
-------------------  -----------------------
14/11/2026 16:25:40  2026-11-14T16:25:40.123
```

Khi format dùng toàn thành phần số và dấu cố định, kết quả ít phụ thuộc ngôn ngữ. Nếu dùng `MON`, `MONTH`, `DAY`..., cần kiểm soát `NLS_DATE_LANGUAGE` theo nhu cầu.

### 7.3. Format hiển thị không quyết định kiểu của dữ liệu

So sánh:

```sql
SELECT
    TO_CHAR(DATE '2026-11-14', 'DD/MM/YYYY') AS text_value,
    DATE '2026-11-14'                       AS date_value
FROM dual;
```

Hai cột có thể **trông giống nhau** trong giao diện, nhưng `TEXT_VALUE` có kiểu ký tự còn `DATE_VALUE` có kiểu `DATE`. Tác vụ tiếp theo như sorting, filter, phép cộng ngày và bind qua JDBC có thể khác nhau vì kiểu dữ liệu khác nhau.

Nếu cần truyền date/time giữa các tầng, ưu tiên giữ kiểu ngày giờ càng lâu càng tốt; format thành chuỗi tại lớp trình bày hoặc khi giao thức yêu cầu rõ chuẩn chuỗi.

## 8. Ứng dụng Java/JDBC và connection pool

### 8.1. Truyền tham số bằng bind variables

Một lỗi dễ gặp khi ghép câu SQL trong Java:

```java
// Không khuyến nghị: ghép đầu vào ngày giờ thành SQL text.
String sql = "SELECT event_id FROM nls_event_log "
           + "WHERE event_ts >= '" + userInput + "'";
```

Nếu `userInput` là chuỗi `14/11/2026`, SQL có thể phụ thuộc session NLS. Cách ghép chuỗi còn làm tăng nguy cơ SQL injection hoặc lỗi khi dữ liệu có ký tự đặc biệt.

Thay bằng `PreparedStatement` với tham số đúng kiểu:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDateTime;

LocalDateTime from = LocalDateTime.of(2026, 11, 14, 0, 0);
LocalDateTime until = from.plusDays(1);

String sql = """
    SELECT event_id, event_ts
    FROM nls_event_log
    WHERE event_ts >= ?
      AND event_ts < ?
    ORDER BY event_ts
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(1, Timestamp.valueOf(from));
    ps.setTimestamp(2, Timestamp.valueOf(until));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("event_id"));
        }
    }
}
```

Đoạn mã minh họa dùng **Java 15 trở lên** vì sử dụng text blocks và giả định biến `connection` đã kết nối hợp lệ. Khi JDBC driver hỗ trợ, ứng dụng có thể chọn các mapping `java.time` thích hợp. Với timestamp có múi giờ, cần xem cách driver map thời điểm/time zone và chính sách của hệ thống thay vì mặc định dùng `LocalDateTime` cho mọi trường hợp.

Điểm chính là **bind tham số có kiểu ngày giờ**, không tạo chuỗi SQL chứa ngày tháng theo format màn hình hoặc `NLS_DATE_FORMAT` của phiên.

### 8.2. Connection pool có thể giữ trạng thái NLS của phiên

Giả sử một dịch vụ giữ pool 20 Oracle connections. Tác vụ A mượn connection rồi chạy:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';
```

Khi tác vụ A trả connection về pool, physical session phía Oracle có thể **vẫn mang format này**. Tác vụ B mượn lại cùng connection, chạy SQL dùng chuỗi ngày tháng không format và nhận kết quả khác dự kiến.

Đây là ví dụ của **session state leakage**: trạng thái cấu hình của một tác vụ ảnh hưởng tác vụ tiếp theo do tái sử dụng kết nối.

Biện pháp:

- Không phụ thuộc implicit datetime conversion trong SQL của ứng dụng.
- Dùng format tường minh khi buộc phải parse chuỗi.
- Cấu hình session initialization và reset theo cơ chế pool/driver để bảo đảm những session states bắt buộc luôn nhất quán.
- Giữ quy tắc truyền dữ liệu bằng typed bind parameters.
- Kiểm tra hành vi thực tế của session sau khi ứng dụng trả/mượn lại connection.

Cấu hình `ALTER SESSION` ở đầu từng request có thể phát sinh overhead và không thay thế thiết kế kiểu dữ liệu đúng.

### 8.3. Đừng dựa vào cách công cụ hiển thị dữ liệu

SQL Developer, SQL*Plus, SQLcl, JDBC và công cụ BI có thể format dữ liệu theo cách riêng. Ví dụ một UI có thể hiển thị `DATE` theo thiết lập ở client mà người dùng không cần thay `NLS_DATE_FORMAT` trên server.

Nếu hai công cụ hiển thị khác nhau:

1. Xác định kiểu dữ liệu cột và giá trị thực.
2. Kiểm tra `NLS_SESSION_PARAMETERS` trong đúng phiên.
3. Xem cách driver/công cụ format ngày giờ ở phía client.
4. Chạy `TO_CHAR(date_col, 'YYYY-MM-DD HH24:MI:SS')` để có chuỗi đối chiếu rõ ràng.

Không kết luận ngay rằng một trong hai công cụ đã **ghi sai datafile**.

## 9. NLS_DATE_LANGUAGE, NLS_TERRITORY và múi giờ: ba tác động khác nhau

### 9.1. Ngôn ngữ tên tháng

Với format `DD-MON-YYYY`, phần `MON` là tên tháng viết tắt. Tháng 11 có thể được trình bày hoặc giải mã theo ngôn ngữ khác nhau.

Ví dụ:

```sql
SELECT
    TO_CHAR(DATE '2026-11-14',
            'DD-MON-YYYY',
            'NLS_DATE_LANGUAGE=ENGLISH') AS english_text
FROM dual;
```

Khi nhập chuỗi chứa tên tháng, nên dùng đối số `NLS_DATE_LANGUAGE` trong `TO_DATE`/`TO_TIMESTAMP` nếu format có tên ngày/tháng dạng chữ.

### 9.2. Vùng lãnh thổ ảnh hưởng mặc định

`NLS_TERRITORY` là một yếu tố Oracle dùng để xác định quy ước vùng và định dạng mặc định cho ngày/giờ, tiền tệ và các thuộc tính khác. Một default format có thể phù hợp với `MM/DD/YYYY` ở môi trường này nhưng `DD/MM/YYYY` ở môi trường khác.

**Không dựa vào giá trị mặc định được suy từ tên vùng.** Kiểm tra trực tiếp `NLS_DATE_FORMAT` và `NLS_TIMESTAMP_FORMAT` trong `NLS_SESSION_PARAMETERS`, bởi client/driver hoặc câu lệnh `ALTER SESSION` có thể đã ghi đè.

### 9.3. Múi giờ không nằm trong NLS_DATE_FORMAT

`DATE` và `TIMESTAMP` thông thường **không lưu time zone**. Nếu hệ thống cần biểu diễn chính xác một thời điểm theo múi giờ hoặc chuyển đổi giữa các múi giờ, cần chọn kiểu và logic thích hợp, chẳng hạn `TIMESTAMP WITH TIME ZONE`.

Ví dụ:

```sql
SELECT
    SESSIONTIMEZONE AS session_timezone,
    DBTIMEZONE      AS database_timezone,
    SYSTIMESTAMP    AS server_timestamp,
    CURRENT_TIMESTAMP AS current_timestamp_with_tz,
    LOCALTIMESTAMP  AS local_timestamp_without_tz
FROM dual;
```

Ở đây:

- `SYSTIMESTAMP` có kiểu `TIMESTAMP WITH TIME ZONE` và gắn với đồng hồ/múi giờ của hệ điều hành máy chủ.
- `CURRENT_TIMESTAMP` là `TIMESTAMP WITH TIME ZONE` theo múi giờ session.
- `LOCALTIMESTAMP` trả về `TIMESTAMP` theo múi giờ session nhưng không kèm time zone.
- `NLS_TIMESTAMP_TZ_FORMAT` điều khiển format mặc định cho giá trị có time zone, khác với `NLS_TIMESTAMP_FORMAT`.

Ví dụ chuỗi có offset từ dữ liệu time zone:

```sql
SELECT TO_CHAR(
         SYSTIMESTAMP,
         'YYYY-MM-DD"T"HH24:MI:SS.FF3TZH:TZM'
       ) AS timestamp_with_offset
FROM dual;
```

Khi hệ thống cần chuẩn hóa dữ liệu giao tiếp giữa các múi giờ, nên có quy ước rõ về kiểu thời gian, offset hoặc tên vùng múi giờ, thay vì chỉ đổi format thành `YYYY-MM-DD HH24:MI:SS` rồi giả định mọi người đang nói về cùng một thời điểm.

## 10. Thực hành: cùng dữ liệu, hai session NLS khác nhau

Bài thực hành dành cho môi trường học tập có quyền tạo bảng và chạy `ALTER SESSION`. Các giá trị thời gian được cố định để dễ so sánh.

### 10.1. Chuẩn bị bảng thử nghiệm

```sql
CREATE TABLE nls_event_log (
    event_id   NUMBER PRIMARY KEY,
    event_date DATE NOT NULL,
    event_ts   TIMESTAMP(6) NOT NULL
);
```

Chèn dữ liệu có format tường minh:

```sql
INSERT INTO nls_event_log(event_id, event_date, event_ts)
VALUES (
    101,
    TO_DATE('2026-11-14 08:09:10',
            'YYYY-MM-DD HH24:MI:SS'),
    TO_TIMESTAMP('2026-11-14 08:09:10.123456',
                 'YYYY-MM-DD HH24:MI:SS.FF6')
);

INSERT INTO nls_event_log(event_id, event_date, event_ts)
VALUES (
    102,
    TO_DATE('2026-11-14 18:30:45',
            'YYYY-MM-DD HH24:MI:SS'),
    TO_TIMESTAMP('2026-11-14 18:30:45.987654',
                 'YYYY-MM-DD HH24:MI:SS.FF6')
);

COMMIT;
```

Hai câu `INSERT` ghi dữ liệu ngày giờ trực tiếp dưới các kiểu phù hợp; không cần giả định một session dùng mặc định `DD/MM/YYYY` hay `YYYY-MM-DD`.

### 10.2. Session A: format dạng ngày/tháng/năm

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';

ALTER SESSION SET NLS_TIMESTAMP_FORMAT =
    'DD/MM/YYYY HH24:MI:SS.FF3';

SELECT event_id, event_date, event_ts
FROM   nls_event_log
ORDER  BY event_id;
```

Với công cụ hiển thị dựa trên session NLS, hình thức dữ liệu sẽ tương tự:

```text
EVENT_ID  EVENT_DATE  EVENT_TS
--------  ----------  -----------------------
101       14/11/2026  14/11/2026 08:09:10.123
102       14/11/2026  14/11/2026 18:30:45.987
```

Ở cột `EVENT_DATE`, giờ không xuất hiện do format `DD/MM/YYYY`. Phần giờ **vẫn nằm trong DATE**.

### 10.3. Session B: format dạng năm-tháng-ngày

Mở phiên khác hoặc đổi giá trị trong cùng phiên:

```sql
ALTER SESSION SET NLS_DATE_FORMAT =
    'YYYY-MM-DD HH24:MI:SS';

ALTER SESSION SET NLS_TIMESTAMP_FORMAT =
    'YYYY-MM-DD HH24:MI:SS.FF6';

SELECT event_id, event_date, event_ts
FROM   nls_event_log
ORDER  BY event_id;
```

Ví dụ kết quả:

```text
EVENT_ID  EVENT_DATE            EVENT_TS
--------  -------------------   --------------------------
101       2026-11-14 08:09:10   2026-11-14 08:09:10.123456
102       2026-11-14 18:30:45   2026-11-14 18:30:45.987654
```

**Dữ liệu bảng không thay đổi.** Khác biệt nằm ở format trình bày theo phiên.

### 10.4. Xác nhận giá trị thực bằng TO_CHAR tường minh

Chạy ở cả hai session:

```sql
SELECT event_id,
       TO_CHAR(event_date,
               'YYYY-MM-DD HH24:MI:SS') AS explicit_date,
       TO_CHAR(event_ts,
               'YYYY-MM-DD HH24:MI:SS.FF6') AS explicit_timestamp
FROM   nls_event_log
ORDER  BY event_id;
```

Hai session sẽ nhận cùng các chuỗi đầu ra cho dữ liệu mẫu, bởi mask đã được chỉ định rõ trong câu SQL.

Đây là cách đối chiếu hữu ích để phân biệt **khác biệt display** với **khác biệt dữ liệu được lưu**.

### 10.5. Quan sát chuyển đổi chuỗi không format

Trong session A:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';

SELECT TO_DATE('14/11/2026') AS parsed_date
FROM   dual;
```

Đổi sang format không phù hợp:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';

-- Câu lệnh sau có thể phát sinh lỗi chuyển đổi:
SELECT TO_DATE('14/11/2026') AS parsed_date
FROM   dual;
```

Cách viết ổn định ở cả hai môi trường:

```sql
SELECT TO_CHAR(
         TO_DATE('14/11/2026', 'DD/MM/YYYY'),
         'YYYY-MM-DD'
       ) AS parsed_date_text
FROM dual;
```

Kết quả mong đợi là `2026-11-14`. Nếu muốn giữ giá trị là DATE để xử lý tiếp, chỉ dùng `TO_DATE(..., 'DD/MM/YYYY')`, không cần `TO_CHAR`.

### 10.6. Kiểm tra bộ lọc ngày theo khoảng

```sql
SELECT event_id
FROM   nls_event_log
WHERE  event_date >= DATE '2026-11-14'
AND    event_date <  DATE '2026-11-15'
ORDER  BY event_id;
```

Cả hai bản ghi 101 và 102 đều nằm trong ngày 14/11/2026, bất kể phần giờ và session NLS.

Đối chiếu với:

```sql
SELECT event_id
FROM   nls_event_log
WHERE  event_date = DATE '2026-11-14';
```

Truy vấn `=` không trả hai bản ghi trên vì thời điểm lưu không phải `00:00:00`.

### 10.7. Dọn môi trường học tập

Chỉ khi bảng được tạo riêng cho bài thực hành và không chứa dữ liệu cần giữ, có thể xóa theo chính sách môi trường:

```sql
-- THAO TÁC PHÁ HỦY: chỉ dành cho bảng học tập do bạn sở hữu.
DROP TABLE nls_event_log PURGE;
```

Lệnh `DROP TABLE` xóa bảng và dữ liệu của nó. Không chạy trên bảng ứng dụng hoặc hệ thống sản xuất.

## 11. Lỗi thường gặp trong triển khai và cách xử lý

### 11.1. Chạy được trong SQL Developer, lỗi trên Java server

**Dấu hiệu:** cùng câu SQL chuyển đổi ngày từ chuỗi, SQL Developer chạy thành công nhưng API báo `ORA-01861`.

**Có thể do:** hai phiên có `NLS_DATE_FORMAT` khác nhau; công cụ có tùy chọn format riêng; JDBC gửi/bind kiểu khác; hoặc chuỗi đầu vào không có format tường minh.

**Hướng xử lý:** đọc `NLS_SESSION_PARAMETERS` trong connection thực của ứng dụng, xác nhận kiểu cột và câu SQL, chuyển sang bind ngày giờ hoặc `TO_DATE/TO_TIMESTAMP` với mask rõ ràng.

### 11.2. Hiển thị thiếu giờ nhưng ứng dụng báo sai lọc dữ liệu

**Dấu hiệu:** màn hình hiển thị `14/11/2026` nhưng truy vấn `WHERE created_at = DATE '2026-11-14'` không tìm được dòng.

**Có thể do:** cột `DATE` lưu giờ khác `00:00:00`, trong khi format hiển thị chỉ có ngày.

**Hướng xử lý:** dùng `TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS')` để quan sát đủ giờ và dùng khoảng nửa mở khi tìm cả ngày.

### 11.3. Đổi NLS_DATE_FORMAT nhưng vẫn thấy một kiểu format khác

**Có thể do:** kết quả đang là `TIMESTAMP` hoặc `TIMESTAMP WITH TIME ZONE`, công cụ format ở phía client, hoặc câu SQL đã dùng `TO_CHAR` tường minh.

**Hướng xử lý:** xác định kiểu cột/biểu thức, kiểm tra cả ba tham số `NLS_DATE_FORMAT`, `NLS_TIMESTAMP_FORMAT`, `NLS_TIMESTAMP_TZ_FORMAT`, rồi xem cách công cụ hiển thị.

### 11.4. Dữ liệu có tháng dạng chữ không parse được

**Dấu hiệu:** chuỗi `14-NOV-2026` gây lỗi tháng không hợp lệ trên một hệ thống, nhưng chạy được trên hệ thống khác.

**Có thể do:** `NLS_DATE_LANGUAGE` hoặc format model khác nhau.

**Hướng xử lý:** dùng format tường minh với `'NLS_DATE_LANGUAGE=ENGLISH'` nếu đầu vào thực sự dùng tên tháng tiếng Anh; tốt hơn nữa, chuẩn hóa dữ liệu trao đổi thành năm-tháng-ngày dạng số nếu được phép.

### 11.5. API trả dữ liệu ngày giờ đúng trên máy chủ nhưng sai múi giờ của người dùng

**Có thể do:** thiết kế dùng `DATE` hoặc `TIMESTAMP` không lưu time zone trong khi nghiệp vụ đòi hỏi một thời điểm tuyệt đối; hoặc session/app áp dụng time zone khác.

**Hướng xử lý:** xem kiểu cột, `SESSIONTIMEZONE`, API serialization, `TIMESTAMP WITH TIME ZONE` và quy ước lưu/đọc thời điểm. **Không cố xử lý lỗi time zone chỉ bằng cách đổi `NLS_DATE_FORMAT`**.

### 11.6. Kết quả thất thường khi connection pool tái sử dụng connection

**Có thể do:** một tác vụ trước đã gọi `ALTER SESSION` rồi trả session về pool; tác vụ tiếp theo thực hiện SQL có implicit conversion.

**Hướng xử lý:** loại bỏ implicit conversion, áp dụng quy tắc session initialization/reset có kiểm soát, và tái hiện lỗi bằng đúng connection pool của ứng dụng thay vì chỉ mở một session SQL*Plus riêng.

### 11.7. Dữ liệu import bị đổi ngày/tháng

Nếu các chuỗi dạng `05/06/2026` được hiểu theo `DD/MM/YYYY`, đó là 5/6/2026; theo `MM/DD/YYYY`, đó là 6/5/2026. Cả hai đều có thể là ngày hợp lệ nên lỗi dữ liệu **không nhất thiết phát sinh ORA-018xx**.

Đây là nguy cơ nghiêm trọng hơn lỗi cú pháp vì dữ liệu có thể được ghi sai một cách âm thầm. Cần thống nhất format đầu vào, kiểm tra mẫu dữ liệu, dùng typed bind hoặc parse tường minh, và đối soát sau import.

## 12. Quy tắc thiết kế để không phụ thuộc cấu hình phiên

### 12.1. Những điều nên thực hiện

1. **Lưu ngày giờ dưới kiểu DATE/TIMESTAMP phù hợp**, thay vì lưu chuỗi ngày giờ trong `VARCHAR2` chỉ để dễ trình bày.
2. **Dùng ANSI literals** cho mốc ngày giờ cố định trong SQL: `DATE 'YYYY-MM-DD'` hoặc `TIMESTAMP 'YYYY-MM-DD HH24:MI:SS.FF...'`.
3. **Dùng typed bind variables** khi nhận tham số từ ứng dụng hoặc dịch vụ bên ngoài.
4. Khi nhận **chuỗi** từ nguồn không hỗ trợ typed bind, dùng `TO_DATE`, `TO_TIMESTAMP` hoặc `TO_TIMESTAMP_TZ` với format model đã quy định rõ.
5. Khi tạo **chuỗi trình bày**, dùng `TO_CHAR` với format model tường minh; nếu có tên tháng/ngày, kiểm soát `NLS_DATE_LANGUAGE`.
6. Trong `WHERE` và `ORDER BY`, ưu tiên **giữ nguyên kiểu dữ liệu thời gian**. Dùng khoảng nửa mở để lọc ngày có giờ/giây lẻ.
7. Đặt quy ước time zone và kiểu cột riêng cho nghiệp vụ có người dùng ở nhiều múi giờ.
8. Khi chẩn đoán lỗi, kiểm tra `NLS_SESSION_PARAMETERS` trong **đúng session gặp lỗi**.

### 12.2. Những điều cần tránh

| Cách viết dễ gây lỗi | Vì sao có rủi ro? | Cách thay |
| --- | --- | --- |
| `TO_DATE('14/11/2026')` | Dùng format mặc định của session | `TO_DATE('14/11/2026','DD/MM/YYYY')` |
| `TO_TIMESTAMP('14/11/2026 15:20:30.123')` | Dùng `NLS_TIMESTAMP_FORMAT` của session | `TO_TIMESTAMP(...,'DD/MM/YYYY HH24:MI:SS.FF3')` |
| `date_col = '14/11/2026'` | Implicit conversion và có thể bỏ sót thời gian | `date_col >= DATE '2026-11-14' AND date_col < DATE '2026-11-15'` |
| `TO_DATE(SYSDATE,'YYYY-MM-DD')` | `SYSDATE` vốn là DATE; có thể bị DATE → CHAR → DATE qua NLS | Giữ `SYSDATE` hoặc dùng `TRUNC(SYSDATE)` |
| `ORDER BY TO_CHAR(date_col,'DD/MM/YYYY')` | Sắp xếp chuỗi thay vì thời gian | `ORDER BY date_col` |
| `BETWEEN start_day AND '... 23:59:59'` | Có thể bỏ sót phần giây lẻ của TIMESTAMP | Dùng khoảng nửa mở |
| Ghép chuỗi ngày giờ từ request vào SQL | NLS-dependent, dễ phát sinh SQL injection | Prepared statement với bind date/time |
| Đổi NLS format để giải quyết lỗi time zone | NLS format không thay đổi bản chất múi giờ | Chọn đúng timestamp type và quy ước time zone |

### 12.3. Khi nào ALTER SESSION vẫn có ích?

`ALTER SESSION SET NLS_DATE_FORMAT = ...` hoàn toàn hợp lệ để:

- Quy định cách xuất kết quả đọc trong một **phiên quản trị tương tác**.
- Giúp script SQL*Plus hiển thị thời gian theo một chuẩn thống nhất.
- Thiết lập môi trường thử nghiệm có chủ đích để tái hiện lỗi.
- Hỗ trợ những ứng dụng legacy cần format session cố định, nếu chưa thể cải tiến ngay.

Tuy vậy, **đặt NLS session format không nên là bảo đảm duy nhất về tính đúng đắn của dữ liệu**. SQL ứng dụng và giao thức dữ liệu vẫn cần quy định rõ kiểu và format ở nơi chuyển đổi.

## 13. Bài tập tự kiểm tra

### Câu 1 — DATE có lưu giờ không?

Một cột `DATE` chứa giá trị ngày 14/11/2026 lúc 16:25:40. Khi DBA đặt `NLS_DATE_FORMAT='DD/MM/YYYY'`, dữ liệu có mất giờ không?

**Gợi ý:** Không. Format mặc định chỉ làm giờ không xuất hiện trên chuỗi trình bày; DATE vẫn lưu đến giây.

### Câu 2 — Khi nào NLS_TIMESTAMP_FORMAT có tác dụng?

Hai biểu thức `LOCALTIMESTAMP` và `SYSTIMESTAMP` có cùng kiểu dữ liệu không? Tham số format nào thường liên quan đến hiển thị mặc định của từng biểu thức?

**Gợi ý:** `LOCALTIMESTAMP` trả về TIMESTAMP; `SYSTIMESTAMP` trả về TIMESTAMP WITH TIME ZONE. Các format tương ứng thường là `NLS_TIMESTAMP_FORMAT` và `NLS_TIMESTAMP_TZ_FORMAT`.

### Câu 3 — Chuyển đổi an toàn

Viết lại SQL sau để kết quả không phụ thuộc `NLS_DATE_FORMAT`:

```sql
SELECT TO_DATE('25/12/2026')
FROM   dual;
```

**Gợi ý:**

```sql
SELECT TO_DATE('25/12/2026', 'DD/MM/YYYY')
FROM   dual;
```

### Câu 4 — Tìm cả ngày

Cột `CREATED_AT` có kiểu `TIMESTAMP(6)`. Viết điều kiện tìm toàn bộ ngày 14/11/2026, kể cả `23:59:59.999999`.

**Gợi ý:**

```sql
WHERE created_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-15 00:00:00'
```

### Câu 5 — Format khác nhau

Một phiên dùng `DD/MM/YYYY`, phiên khác dùng `YYYY-MM-DD`. Cả hai truy vấn `TO_CHAR(DATE '2026-11-14','YYYY-MM-DD')`. Chuỗi kết quả có khác nhau vì `NLS_DATE_FORMAT` không?

**Gợi ý:** Không, vì format đầu ra được chỉ định tường minh.

### Câu 6 — Sai lệch không phát sinh lỗi

Tại sao chuỗi `05/06/2026` nguy hiểm hơn một chuỗi tháng không hợp lệ khi dùng implicit conversion?

**Gợi ý:** Nó có thể được hiểu thành hai ngày **khác nhau nhưng đều hợp lệ** theo `DD/MM/YYYY` và `MM/DD/YYYY`; dữ liệu sai có thể được ghi mà không có lỗi.

### Câu 7 — Connection pool

Một request đổi `NLS_DATE_FORMAT` trước khi chạy SQL rồi trả connection vào pool. Request kế tiếp lấy lại connection đó. Vấn đề nào có thể xảy ra?

**Gợi ý:** Session NLS vẫn có thể mang trạng thái do request trước để lại; SQL phụ thuộc implicit conversion có thể diễn giải khác dự định.

### Câu 8 — MM và MI

Trong format model `YYYY-MM-DD HH24:MM:SS`, ký hiệu nào sai nếu muốn hiển thị **phút**?

**Gợi ý:** `MM` là tháng. Cần dùng `MI` cho phút: `YYYY-MM-DD HH24:MI:SS`.

### Câu 9 — Chọn đúng kiểu

Hệ thống cần giữ microseconds của số liệu sự kiện. Chọn `DATE` hay `TIMESTAMP(6)`? Đổi `NLS_DATE_FORMAT` có khắc phục được việc mất microseconds khi lưu DATE không?

**Gợi ý:** `TIMESTAMP(6)`. Format không tăng độ chính xác lưu trữ của `DATE`.

### Câu 10 — Giải thích lỗi TO_DATE(SYSDATE)

Vì sao câu `TO_DATE(SYSDATE,'YYYY-MM-DD')` có thể rủi ro dù đối số đầu tiên đã là một giá trị ngày giờ hợp lệ?

**Gợi ý:** Vì Oracle có thể phải chuyển từ DATE sang chuỗi theo NLS của session rồi mới dùng format model đã cho để parse ngược. Không cần gọi `TO_DATE` cho một giá trị đã là DATE.

## 14. Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — Datetime Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html): kiểu `DATE`, `TIMESTAMP` và các kiểu timestamp có time zone.
- [Oracle Database SQL Language Reference — Format Models](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Format-Models.html): ký hiệu `YYYY`, `MM`, `DD`, `HH24`, `MI`, `SS`, `FF`, `FX` và định dạng ngày giờ.
- [Oracle Database SQL Language Reference — TO_DATE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_DATE.html): chuyển đổi chuỗi sang DATE và tham số NLS.
- [Oracle Database SQL Language Reference — TO_TIMESTAMP](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_TIMESTAMP.html): chuyển đổi chuỗi sang TIMESTAMP với format tường minh.
- [Oracle Database SQL Language Reference — TO_CHAR (datetime)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_CHAR-datetime.html): định dạng giá trị ngày giờ thành chuỗi.
- [Oracle Database Reference — NLS_DATE_FORMAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/NLS_DATE_FORMAT.html): phạm vi, default và cách thiết lập của tham số.
- [Oracle Database Reference — NLS_TIMESTAMP_FORMAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/NLS_TIMESTAMP_FORMAT.html): định dạng mặc định cho TIMESTAMP.
- [Oracle Database Reference — NLS_SESSION_PARAMETERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/NLS_SESSION_PARAMETERS.html): xem NLS của session.
- [Oracle Database Globalization Support Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/): các lớp cấu hình NLS, ngôn ngữ và vùng lãnh thổ.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): truyền dữ liệu ngày giờ qua JDBC và bind parameters.

Khi làm việc với Oracle, hãy giữ nguyên nguyên tắc: **DATE/TIMESTAMP là kiểu lưu dữ liệu**, còn **NLS_DATE_FORMAT/NLS_TIMESTAMP_FORMAT là quy tắc chuyển đổi/hiển thị mặc định trong phiên**. Một câu SQL đáng tin cậy nên dùng **format model rõ ràng**, **ANSI datetime literals** hoặc **typed bind variables** để việc nhập, lọc và trao đổi ngày giờ không thay đổi chỉ vì ứng dụng kết nối bằng một session khác.
