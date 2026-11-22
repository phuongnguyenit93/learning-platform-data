# SYSDATE, SYSTIMESTAMP, CURRENT_DATE và CURRENT_TIMESTAMP trong Oracle Database

Ứng dụng tại Việt Nam có thể kết nối đến một Oracle Database đặt ở trung tâm dữ liệu dùng múi giờ khác. Khi cùng lúc chạy `SYSDATE` và `CURRENT_DATE`, bạn có thể nhận được **hai giá trị giờ khác nhau** mà cả hai đều đúng. Chúng được lấy theo những ngữ cảnh thời gian khác nhau. Thêm vào đó, `SYSDATE` có kiểu `DATE` dù chứa cả giờ, phút, giây; `SYSTIMESTAMP` có thể chứa phần lẻ giây và thông tin múi giờ. Nếu không phân biệt rõ, ứng dụng dễ ghi sai thời điểm tạo bản ghi, lọc “hôm nay” sai ngày hoặc chuyển đổi thời gian nhiều lần.

Bài học trong nhóm **Ngày giờ và NLS** giải thích bốn hàm lấy thời gian hiện tại của Oracle: **`SYSDATE`, `SYSTIMESTAMP`, `CURRENT_DATE` và `CURRENT_TIMESTAMP`**. Ta sẽ xác định nguồn đồng hồ, ảnh hưởng của múi giờ phiên, kiểu dữ liệu trả về, cách NLS hiển thị giá trị và phương pháp lưu/so sánh thời điểm đáng tin cậy.

Sau bài học, bạn có thể:

- Phân biệt thời gian **phía database server** và thời gian **theo session time zone**.
- Giải thích khác biệt giữa kiểu `DATE` và `TIMESTAMP WITH TIME ZONE`.
- Viết truy vấn hiển thị giờ, phần lẻ giây và độ lệch múi giờ bằng `TO_CHAR`.
- Kiểm tra `SESSIONTIMEZONE`, `DBTIMEZONE`, các tham số NLS và thiết lập múi giờ phiên khi thực hành.
- Dùng `AT TIME ZONE`, `SYS_EXTRACT_UTC` và các datetime literal có độ lệch múi giờ để đối chiếu **cùng một thời điểm tuyệt đối**.
- Chọn kiểu cột, giá trị mặc định và cách truy vấn theo khoảng thời gian cho ứng dụng nhiều múi giờ.

> **Điều kiện ví dụ:** Các đoạn SQL có thể chạy bằng SQL*Plus, SQLcl, SQL Developer hoặc công cụ hỗ trợ Oracle SQL. Kết quả đồng hồ thay đổi ở mỗi lần chạy, vì vậy số liệu giờ trong bảng chỉ là **minh họa**, không phải giá trị cố định. Các lệnh `ALTER SESSION` chỉ ảnh hưởng đến phiên hiện tại; bài thực hành tạo bảng chỉ nên chạy trong schema/PDB học tập.

## 1. Hai trục phân biệt: nguồn giờ và kiểu dữ liệu trả về

Nhớ bảng sau trước khi viết SQL:

| Hàm | Nguồn/ngữ cảnh thời gian | Kiểu trả về | Độ chính xác thời gian | Có thông tin múi giờ trong giá trị? |
| --- | --- | --- | --- | --- |
| `SYSDATE` | Đồng hồ của hệ điều hành phía **database server** | `DATE` | Đến **giây** | **Không** |
| `SYSTIMESTAMP` | Đồng hồ phía **database server**, kèm múi giờ/offset phía server | `TIMESTAMP WITH TIME ZONE` | Có **phần lẻ giây** | **Có** |
| `CURRENT_DATE` | Thời điểm hiện tại diễn giải theo **session time zone** | `DATE` | Đến **giây** | **Không** |
| `CURRENT_TIMESTAMP` | Thời điểm hiện tại diễn giải theo **session time zone** | `TIMESTAMP WITH TIME ZONE` | Có **phần lẻ giây** | **Có** |

Trong một môi trường Oracle thông thường:

~~~text
                     THOI DIEM HIEN TAI
                              |
               +--------------+---------------+
               |                              |
               v                              v
       Database server clock           Session time zone
               |                              |
          +----+----+                    +----+----+
          |         |                    |         |
          v         v                    v         v
      SYSDATE  SYSTIMESTAMP        CURRENT_DATE CURRENT_TIMESTAMP
       DATE     TIMESTAMP             DATE       TIMESTAMP
                WITH TIME ZONE                   WITH TIME ZONE
~~~

Ví dụ **giả định** server hoạt động theo UTC (`+00:00`), còn session được cấu hình `+07:00`. Trong cùng một khoảng thời gian:

| Hàm | Giá trị minh họa |
| --- | --- |
| `SYSDATE` | `2026-11-14 08:30:00` |
| `SYSTIMESTAMP` | `2026-11-14 08:30:00.123 +00:00` |
| `CURRENT_DATE` | `2026-11-14 15:30:00` |
| `CURRENT_TIMESTAMP` | `2026-11-14 15:30:00.123 +07:00` |

Hai timestamp có offset khác nhau có thể chỉ **cùng một thời điểm thực**, ví dụ `08:30 +00:00` và `15:30 +07:00`. Trong khi đó, hai giá trị `DATE` không chứa offset nên tự chúng không nói rõ múi giờ nào đã được dùng khi hình thành giá trị.

**Lưu ý về tính đồng thời:** Nếu bạn gọi hai hàm ở hai thời điểm khác nhau, chúng có thể chênh vài mili giây hoặc qua ranh giới giây/ngày. Bảng ví dụ coi chúng được lấy gần như cùng lúc để nhấn mạnh khác biệt về múi giờ. Trên một số triển khai có cấu hình thời gian đặc biệt, hành vi hàm server-side còn chịu ảnh hưởng chính sách database; cần kiểm tra cấu hình thực tế khi đối chiếu môi trường.

## 2. Hiểu kiểu `DATE` của Oracle: không chỉ là ngày

Trong Oracle SQL, kiểu dữ liệu **`DATE` chứa cả năm, tháng, ngày, giờ, phút và giây**. Nó không giống kiểu `LocalDate` chỉ chứa ngày ở nhiều ngôn ngữ lập trình.

Ví dụ:

~~~sql
SELECT
    SYSDATE AS server_datetime,
    CURRENT_DATE AS session_datetime
FROM dual;
~~~

Nếu công cụ hiển thị chỉ có `14-NOV-26`, điều đó **không có nghĩa phần giờ đã mất**. Định dạng hiển thị mặc định có thể đang bỏ giờ. Hãy định dạng tường minh:

~~~sql
SELECT
    TO_CHAR(SYSDATE,      'YYYY-MM-DD HH24:MI:SS') AS server_datetime,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS session_datetime
FROM dual;
~~~

Lúc này bạn thấy cả giờ, phút, giây. Nhưng **không thể lấy phần lẻ giây hoặc độ lệch múi giờ** trực tiếp từ một `DATE` thông thường, vì chúng không nằm trong giá trị.

### 2.1. Kiểu `TIMESTAMP WITH TIME ZONE`

`SYSTIMESTAMP` và `CURRENT_TIMESTAMP` trả về kiểu `TIMESTAMP WITH TIME ZONE` (thường viết tắt `TSTZ`). Nó có các trường ngày giờ, **phần lẻ giây** và thông tin múi giờ đi kèm. Múi giờ có thể được biểu diễn bằng độ lệch như `+07:00` hoặc thông tin khu vực theo cách tạo giá trị; độ lệch cụ thể có thể thay đổi theo daylight saving time.

~~~sql
SELECT
    TO_CHAR(
        SYSTIMESTAMP,
        'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM'
    ) AS server_timestamp,
    TO_CHAR(
        CURRENT_TIMESTAMP,
        'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM'
    ) AS session_timestamp
FROM dual;
~~~

Trong format trên:

- `YYYY-MM-DD`: năm, tháng, ngày.
- `HH24:MI:SS`: giờ 24h, phút, giây; **`MI` là phút, `MM` là tháng**.
- `FF3`: hiển thị ba chữ số phần lẻ giây, thường tương ứng mili giây.
- `TZH:TZM`: giờ/phút của **UTC offset** gắn với giá trị timestamp.

`FF3` chỉ là **format hiển thị**; không đồng nghĩa dữ liệu gốc hoặc hệ điều hành chỉ có độ chính xác ba chữ số. Mức phân giải thực tế còn tùy hệ điều hành và cách Oracle lấy thời gian.

### 2.2. So sánh nhanh các kiểu dữ liệu ngày giờ

| Kiểu dữ liệu Oracle | Ngày/giờ | Phần lẻ giây | Múi giờ trong giá trị | Ghi chú |
| --- | --- | --- | --- | --- |
| `DATE` | Có | Không | Không | Đến giây |
| `TIMESTAMP(p)` | Có | Có, theo `p` | Không | Giá trị local date-time, chưa nêu timezone |
| `TIMESTAMP(p) WITH TIME ZONE` | Có | Có | Có | Có thể diễn tả một thời điểm tuyệt đối với offset/region |
| `TIMESTAMP(p) WITH LOCAL TIME ZONE` | Có | Có | Không giữ timezone đầu vào như TSTZ; trình bày theo session | Oracle chuẩn hóa cho lưu trữ theo database time zone và hiển thị theo session time zone |

Không nên chọn kiểu `DATE` chỉ vì tên cột là `CREATED_DATE` nếu yêu cầu nghiệp vụ phải giữ được độ chính xác dưới giây và đối chiếu giữa nhiều múi giờ.

## 3. `SYSDATE`: giờ hiện tại theo database server

### 3.1. Cách dùng cơ bản

`SYSDATE` không cần đối số:

~~~sql
SELECT SYSDATE FROM dual;

SELECT TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS')
       AS server_now
FROM dual;
~~~

Trong triển khai thông thường, `SYSDATE` lấy giờ hệ điều hành nơi Oracle Database server chạy. Hàm không sử dụng múi giờ riêng của máy client để định dạng một thời điểm mới. Một ứng dụng ở Việt Nam và một ứng dụng ở nước khác truy vấn cùng database có thể nhìn thấy giá trị `SYSDATE` gần nhau, dù session time zone của hai ứng dụng khác nhau.

`SYSDATE` trả về `DATE` nên:

- Có **năm, tháng, ngày, giờ, phút, giây**.
- Không có fractional seconds.
- Không mang thông tin offset hoặc timezone region.
- Sử dụng được trong biểu thức ngày giờ Oracle, ví dụ `SYSDATE + 1` là thêm **một ngày** vào `DATE`.

Ví dụ tính giới hạn thời gian trên kiểu `DATE`:

~~~sql
SELECT
    TO_CHAR(SYSDATE,     'YYYY-MM-DD HH24:MI:SS') AS now_value,
    TO_CHAR(SYSDATE + 1, 'YYYY-MM-DD HH24:MI:SS') AS one_day_later
FROM dual;
~~~

Đoạn ví dụ biểu thị phép cộng số ngày của `DATE`; trong bài toán lịch có daylight saving time, “sau 24 giờ tuyệt đối” và “cùng giờ ngày hôm sau ở một vùng múi giờ” không phải lúc nào cũng tương đương. Khi cần tính lịch theo region, dùng kiểu/dữ liệu thời gian phù hợp.

### 3.2. Trường hợp dùng `SYSDATE`

`SYSDATE` phù hợp với:

- Hệ thống thống nhất quy ước thời gian theo clock của database server.
- Những bảng legacy lưu `DATE` và đã có hợp đồng thời gian rõ ràng.
- Các đoạn SQL quản trị muốn xem thời gian server theo giây.

Hạn chế: khi cột `DATE` được dùng cho thời điểm tạo bản ghi, **múi giờ không được lưu cùng giá trị**. Nếu chuyển database sang server có múi giờ hệ điều hành khác, so sánh lịch sử với giá trị mới có thể gây sai lệch nếu hệ thống không quy ước rõ múi giờ.

### 3.3. `TRUNC(SYSDATE)` là đầu ngày theo clock server

~~~sql
SELECT
    TO_CHAR(TRUNC(SYSDATE), 'YYYY-MM-DD HH24:MI:SS')
        AS start_of_server_day
FROM dual;
~~~

`TRUNC(SYSDATE)` đặt phần giờ/phút/giây bằng `00:00:00` trong **ngữ cảnh ngày giờ server**. Nó **không nhất thiết là 00:00 của người dùng tại Việt Nam** nếu server ở múi giờ khác.

## 4. `SYSTIMESTAMP`: giờ database server có phần lẻ giây và timezone

`SYSTIMESTAMP` là lựa chọn quan trọng khi muốn lưu một **thời điểm sự kiện** có thể so sánh nhất quán giữa các múi giờ.

~~~sql
SELECT
    SYSTIMESTAMP AS raw_server_timestamp,
    TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM')
        AS formatted_server_timestamp
FROM dual;
~~~

Giá trị kiểu `TIMESTAMP WITH TIME ZONE` giúp nhận diện instant khi đi kèm offset. Chẳng hạn:

~~~text
2026-11-14 08:30:00.123456 +00:00
2026-11-14 15:30:00.123456 +07:00
~~~

Nếu hai dòng được định nghĩa tại cùng một instant, chúng biểu diễn **cùng một thời điểm**, dù biểu diễn giờ địa phương khác nhau.

### 4.1. Dùng `AT TIME ZONE` để trình bày instant theo vùng khác

~~~sql
SELECT
    TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM')
        AS server_view,
    TO_CHAR(
        SYSTIMESTAMP AT TIME ZONE '+07:00',
        'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM'
    ) AS utc_plus_7_view,
    TO_CHAR(
        SYSTIMESTAMP AT TIME ZONE 'UTC',
        'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM'
    ) AS utc_view
FROM dual;
~~~

`AT TIME ZONE` **chuyển cách biểu diễn một instant** sang múi giờ đích. Nó không đơn giản là cộng chuỗi “+7” vào con số giờ mà bỏ qua ngày/offset. Với vùng thời gian có daylight saving time, việc chuyển theo **region name** và ngày cụ thể giúp áp dụng đúng luật thời gian mà Oracle biết.

### 4.2. Trích xuất thời gian UTC

~~~sql
SELECT
    SYS_EXTRACT_UTC(SYSTIMESTAMP) AS utc_timestamp
FROM dual;
~~~

`SYS_EXTRACT_UTC` trả về `TIMESTAMP` đã được đưa về giờ UTC, **không kèm trường timezone trong kiểu dữ liệu kết quả**. Nếu dùng nó để lưu trong cột `TIMESTAMP`, ứng dụng phải quy định rõ “mọi giá trị cột này là UTC”; chỉ riêng kiểu `TIMESTAMP` không tự chứa lời cam kết đó.

### 4.3. Giới hạn của timestamp theo giờ hệ điều hành

`SYSTIMESTAMP` mô tả thời gian phía server và offset tương ứng; trong môi trường đa máy/RAC hoặc khi đồng hồ host cấu hình không nhất quán, việc giám sát đồng bộ clock (NTP và cấu hình hạ tầng) vẫn rất quan trọng. Các hàm thời gian không thay thế cơ chế thứ tự giao dịch hoặc một đồng hồ logic toàn cục; hai sự kiện gần nhau ở máy khác nhau không nên được sắp thứ tự tuyệt đối chỉ bằng timestamp nếu cần tính đúng đắn phân tán.

## 5. `CURRENT_DATE`: DATE diễn giải theo múi giờ session

`CURRENT_DATE` trả về **giờ hiện tại theo session time zone**, kiểu `DATE`, không có offset trong giá trị:

~~~sql
SELECT
    SESSIONTIMEZONE AS session_time_zone,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS')
        AS current_date_in_session
FROM dual;
~~~

Nếu session là `+07:00` nhưng server chạy theo UTC, `CURRENT_DATE` sẽ cho giá trị giờ muộn hơn `SYSDATE` khoảng 7 giờ ở cùng instant. Nếu gần nửa đêm, **ngày dương lịch cũng có thể khác**.

### 5.1. Thay đổi session time zone

Trên một phiên lab riêng:

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';

SELECT
    SESSIONTIMEZONE AS session_tz,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS session_now,
    TO_CHAR(SYSDATE,      'YYYY-MM-DD HH24:MI:SS') AS server_now
FROM dual;
~~~

Sau đó thử một offset khác:

~~~sql
ALTER SESSION SET TIME_ZONE = '-05:00';

SELECT
    SESSIONTIMEZONE AS session_tz,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS session_now,
    TO_CHAR(SYSDATE,      'YYYY-MM-DD HH24:MI:SS') AS server_now
FROM dual;
~~~

Bạn sẽ thấy `CURRENT_DATE` thay đổi về **biểu diễn giờ địa phương**, trong khi `SYSDATE` không đổi theo biến `TIME_ZONE` của session trong cấu hình thông thường. Cả hai hàm vẫn lấy **thời điểm hiện tại**; chúng không “quay lui đồng hồ hệ thống”. Nếu hai phép truy vấn chạy cách nhau vài giây, `SYSDATE` tất nhiên sẽ tiến theo thời gian thực.

Ghi lại `SESSIONTIMEZONE` ban đầu và khôi phục sau bài thực hành bằng `ALTER SESSION SET TIME_ZONE = '...'` với giá trị cũ, hoặc thoát phiên lab. Cấu hình không tự lan sang session khác hay application connection pool.

### 5.2. Dùng `CURRENT_DATE` để xác định “hôm nay” của phiên

~~~sql
SELECT
    TO_CHAR(TRUNC(CURRENT_DATE), 'YYYY-MM-DD HH24:MI:SS')
        AS session_day_start,
    TO_CHAR(TRUNC(SYSDATE), 'YYYY-MM-DD HH24:MI:SS')
        AS server_day_start
FROM dual;
~~~

Nếu server UTC đang ở 18:30 ngày 14/11 và session `+07:00`, phiên có thể đang ở **01:30 ngày 15/11**. Khi đó `TRUNC(CURRENT_DATE)` và `TRUNC(SYSDATE)` cho **hai ngày khác nhau**.

Điều này quan trọng với nghiệp vụ “đơn hàng hôm nay” hoặc “ngày đến hạn” của người dùng. Tuy nhiên, chỉ chọn `CURRENT_DATE` là chưa đủ nếu các hàng được lưu trong cột `DATE` theo một múi giờ khác: bộ lọc phải dùng **cùng quy ước thời gian** ở cả cột dữ liệu và giới hạn truy vấn.

## 6. `CURRENT_TIMESTAMP`: timestamp theo múi giờ session

`CURRENT_TIMESTAMP` trả về kiểu `TIMESTAMP WITH TIME ZONE`, giống `SYSTIMESTAMP` về **họ kiểu dữ liệu**, nhưng độ lệch/region được xác định theo múi giờ session:

~~~sql
SELECT
    SESSIONTIMEZONE AS session_tz,
    TO_CHAR(
        CURRENT_TIMESTAMP,
        'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
    ) AS current_timestamp_value
FROM dual;
~~~

Bạn có thể yêu cầu độ chính xác phần lẻ giây khi gọi hàm, ví dụ:

~~~sql
SELECT
    CURRENT_TIMESTAMP(3) AS session_timestamp_to_milliseconds
FROM dual;
~~~

Số trong ngoặc điều khiển độ chính xác fractional seconds của kết quả, **không thay đổi session time zone**.

### 6.1. So sánh `CURRENT_TIMESTAMP` với `SYSTIMESTAMP`

~~~sql
SELECT
    TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM')
        AS server_clock,
    TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM')
        AS session_clock
FROM dual;
~~~

Nếu server và session có múi giờ khác nhau, **hai chuỗi local time khác nhau**. Sau khi quy đổi về UTC, chúng biểu diễn những thời điểm rất gần nhau. Không dùng so sánh từng ký tự của chuỗi đã định dạng để kết luận hai instant khác nhau.

### 6.2. Nên dùng `CURRENT_TIMESTAMP` khi nào?

Nó phù hợp khi:

- Ứng dụng muốn một giá trị thời điểm hiện tại **có offset** theo phiên kết nối.
- Cần hiển thị hoặc lưu thời điểm theo timezone do session thiết lập.
- Có một hợp đồng rõ ràng để session time zone được thiết lập từ ứng dụng/connection pool trước khi thao tác.

Nếu mục tiêu chỉ là **lưu instant chính xác để audit**, `SYSTIMESTAMP` cũng phù hợp. Mỗi cách cho phép tạo giá trị có offset hợp lệ; điều quan trọng là kiểu cột và chính sách timezone phải được ghi rõ, nhất quán trong ứng dụng.

**Chú ý connection pool:** một client có thể đặt `ALTER SESSION SET TIME_ZONE` rồi trả connection về pool. Session kế tiếp mượn lại connection có thể thừa hưởng cấu hình nếu pool không reset/init lại. Vì vậy khi dựa vào `CURRENT_DATE`/`CURRENT_TIMESTAMP`, hãy xác định timezone trong quy trình khởi tạo session và kiểm tra trước khi sử dụng.

## 7. `SESSIONTIMEZONE`, `DBTIMEZONE` và múi giờ của database server

Ba khái niệm sau **không đồng nhất**:

| Nguồn | Quan sát | Được dùng như thế nào? |
| --- | --- | --- |
| **Session time zone** | `SESSIONTIMEZONE` | `CURRENT_DATE`, `CURRENT_TIMESTAMP` và cách hiển thị `TIMESTAMP WITH LOCAL TIME ZONE` |
| **Database time zone** | `DBTIMEZONE` | Mốc normalization của `TIMESTAMP WITH LOCAL TIME ZONE` và một số xử lý cấp database |
| **Clock/timezone phía database server** | `SYSDATE`, `SYSTIMESTAMP` và cấu hình host | Thời gian do hệ điều hành server cung cấp cho các hàm server-side trong triển khai thông thường |

Truy vấn:

~~~sql
SELECT
    SESSIONTIMEZONE AS session_tz,
    DBTIMEZONE AS database_tz,
    TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM')
        AS server_timestamp,
    TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM')
        AS session_timestamp
FROM dual;
~~~

Giả sử `DBTIMEZONE = '+00:00'` và `SESSIONTIMEZONE = '+07:00'`. **Không suy ra server OS cũng chắc chắn chạy theo `+00:00`.** Database time zone là một thuộc tính database, không phải hàm luôn trả về timezone hiện tại của host. Đặc biệt, việc diễn giải một `DATE` từ `SYSDATE` thành instant bằng cách tự gắn `DBTIMEZONE` có thể sai nếu server clock dùng một timezone khác.

### 7.1. Offset và timezone region

Session có thể sử dụng:

~~~sql
-- Fixed offset, khong tu doi theo daylight saving time.
ALTER SESSION SET TIME_ZONE = '+07:00';
~~~

Hoặc một **timezone region** được Oracle time zone file hỗ trợ:

~~~sql
-- Vi du region pho bien; chi chay neu ban muon thuc hanh DST.
ALTER SESSION SET TIME_ZONE = 'America/New_York';
~~~

Khác biệt:

- `+07:00` là một **UTC offset cố định**.
- `America/New_York` là tên khu vực, có thể áp dụng quy tắc daylight saving time theo **ngày cụ thể** và phiên bản time zone data mà Oracle cài.

Không nên thay region bằng một offset cố định khi nghiệp vụ là “9 giờ sáng tại New York vào một ngày trong tương lai”, vì mùa hè và mùa đông có thể khác offset. Ngược lại, với một instant đã xác định, một offset như `+07:00` đủ để chuyển đổi sang biểu diễn tương đương tại thời điểm đó.

Nếu một region không được hệ thống hỗ trợ, Oracle có thể báo lỗi về timezone; DBA cần kiểm tra time zone file và các region được hỗ trợ thay vì sửa dữ liệu timestamp để ép chạy.

### 7.2. Cẩn thận ở ranh giới DST

Ở những vùng có daylight saving time, có những giờ địa phương **không tồn tại** khi đồng hồ nhảy về phía trước và **xuất hiện hai lần** khi đồng hồ lùi lại. Nếu dữ liệu chỉ lưu `TIMESTAMP` (không offset), chẳng hạn “01:30” của ngày chuyển giờ, đôi khi không thể biết instant nào được nói tới.

`TIMESTAMP WITH TIME ZONE` kèm offset/region phù hợp giúp xác định thời điểm chính xác. Khi nhập giờ địa phương bằng timezone region, Oracle còn có các quy tắc để phát hiện hoặc xử lý thời gian không hợp lệ/mơ hồ; ứng dụng cần thiết kế validation cho lịch hẹn tại các vùng có DST.

## 8. NLS: định dạng hiển thị khác với giá trị lưu trữ

**NLS (National Language Support)** gồm nhiều thiết lập về cách Oracle xử lý ngôn ngữ, ký tự, so sánh và định dạng. Với bài ngày giờ, hai nhóm đặc biệt quan trọng:

1. **Time zone của session** quyết định `CURRENT_DATE` và `CURRENT_TIMESTAMP`.
2. **NLS datetime format** quyết định cách một giá trị `DATE`/`TIMESTAMP` được **chuyển ngầm sang chuỗi** để hiển thị hoặc phân tích trong một số ngữ cảnh.

Đổi `NLS_DATE_FORMAT` **không làm đổi instant**, không chuyển giờ từ server sang session và không thêm timezone vào cột `DATE`.

### 8.1. Những tham số NLS liên quan

| Tham số | Vai trò |
| --- | --- |
| `NLS_DATE_FORMAT` | Định dạng mặc định cho `DATE` khi chuyển đổi ngầm sang chuỗi |
| `NLS_TIMESTAMP_FORMAT` | Định dạng mặc định cho `TIMESTAMP` không timezone |
| `NLS_TIMESTAMP_TZ_FORMAT` | Định dạng mặc định cho `TIMESTAMP WITH TIME ZONE` |
| `NLS_DATE_LANGUAGE` | Ngôn ngữ dùng cho tên tháng/ngày và một số thành phần chữ trong datetime |
| `NLS_TERRITORY` | Có thể ảnh hưởng các mặc định về trình bày theo vùng |

Kiểm tra giá trị trong phiên:

~~~sql
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
~~~

### 8.2. Thay đổi định dạng của phiên

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT =
    'YYYY-MM-DD HH24:MI:SS';

ALTER SESSION SET NLS_TIMESTAMP_TZ_FORMAT =
    'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM';

SELECT SYSDATE, SYSTIMESTAMP, CURRENT_DATE, CURRENT_TIMESTAMP
FROM dual;
~~~

Những lệnh này chỉ thay cách Oracle **mặc định trình bày** các kiểu datetime trong phiên khi client thực hiện chuyển đổi. SQL Developer, JDBC và công cụ khác có thể tự định dạng kết quả nên màn hình không nhất thiết tuân theo NLS session format trong mọi chế độ hiển thị.

Với truy vấn/report cần định dạng ổn định, dùng `TO_CHAR` có format mask rõ ràng:

~~~sql
SELECT
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS local_time_text,
    TO_CHAR(CURRENT_TIMESTAMP,
            'YYYY-MM-DD"T"HH24:MI:SS.FF3TZH:TZM') AS iso_like_text
FROM dual;
~~~

Chuỗi trong dấu ngoặc kép bên **trong format mask** (`"T"`) chỉ ký tự chữ `T` của format, không phải SQL identifier. Kết quả có dạng gần giống ISO 8601, ví dụ `2026-11-14T15:30:00.123+07:00`.

### 8.3. Không phụ thuộc vào implicit conversion

Tránh viết:

~~~sql
-- De bi anh huong boi NLS_DATE_FORMAT cua session.
SELECT *
FROM orders
WHERE created_at = '14/11/2026';
~~~

Nếu `CREATED_AT` là `DATE`, Oracle có thể phải **ngầm chuyển chuỗi thành DATE** theo NLS của session. Hai môi trường cấu hình khác nhau có thể cho kết quả khác hoặc báo `ORA-01861`, `ORA-01843`. Ngoài ra, so sánh bằng một `DATE` ở 00:00 không tìm được các hàng có giờ trong ngày khác 00:00.

Ưu tiên datetime literal hoặc hàm chuyển có format rõ:

~~~sql
-- DATE literal: ngay 2026-11-14, gio 00:00:00.
SELECT *
FROM orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';

-- Neu input la chuoi theo dinh dang duoc quy dinh:
SELECT TO_DATE('14/11/2026', 'DD/MM/YYYY') AS parsed_date
FROM dual;
~~~

`TO_DATE` dùng cho input chuỗi; **không dùng `TO_DATE(SYSDATE, ...)` để “định dạng” SYSDATE**. Bởi `SYSDATE` đã là `DATE`, việc đưa nó vào `TO_DATE` có thể gây chuyển đổi ngầm từ DATE sang chuỗi theo NLS trước khi phân tích lại, gây lỗi hoặc sai giá trị. Muốn hiển thị dùng `TO_CHAR`; muốn giữ kiểu `DATE` thì giữ trực tiếp.

### 8.4. DATE literal không có timezone

~~~sql
SELECT
    DATE '2026-11-14' AS date_at_midnight,
    TIMESTAMP '2026-11-14 15:30:00' AS timestamp_without_tz,
    TIMESTAMP '2026-11-14 15:30:00 +07:00'
        AS timestamp_with_tz
FROM dual;
~~~

Trong Oracle, literal `TIMESTAMP '... +07:00'` với trường offset được nhận là timestamp có timezone; nếu cần minh bạch hoàn toàn khi parsing chuỗi ở đường ứng dụng, có thể dùng `TO_TIMESTAMP_TZ`:

~~~sql
SELECT TO_TIMESTAMP_TZ(
           '2026-11-14 15:30:00 +07:00',
           'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       ) AS ts_with_time_zone
FROM dual;
~~~

Phân biệt: `DATE '2026-11-14'` không gắn `+07:00`; nó là một **giá trị DATE tại nửa đêm**, và ý nghĩa múi giờ chỉ đến từ hợp đồng dữ liệu hoặc phép biến đổi được thực hiện sau đó.

## 9. Cùng một instant, nhiều biểu diễn: thực hành với UTC

Để học cách Oracle nhận biết hai thời gian khác local clock nhưng **cùng instant**, dùng dữ liệu cố định thay vì thời điểm `NOW` thay đổi:

~~~sql
SELECT
    TO_CHAR(
        FROM_TZ(TIMESTAMP '2026-11-14 15:30:00', '+07:00'),
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ) AS vietnam_time,
    TO_CHAR(
        FROM_TZ(TIMESTAMP '2026-11-14 15:30:00', '+07:00')
            AT TIME ZONE 'UTC',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ) AS utc_time
FROM dual;
~~~

Kết quả mong đợi:

~~~text
VIETNAM_TIME             UTC_TIME
-----------------------  -----------------------
2026-11-14 15:30:00 +07:00
                         2026-11-14 08:30:00 +00:00
~~~

Với `FROM_TZ(timestamp_without_tz, timezone)`, Oracle **gắn ngữ cảnh múi giờ cho một local timestamp**. Còn `AT TIME ZONE 'UTC'` trên một giá trị đã có timezone thì **chuyển biểu diễn cùng instant** sang UTC. Đây là hai thao tác khác nhau.

Có thể so sánh hai giá trị timestamp có timezone:

~~~sql
SELECT CASE
         WHEN FROM_TZ(
                TIMESTAMP '2026-11-14 15:30:00', '+07:00'
              ) =
              TO_TIMESTAMP_TZ(
                '2026-11-14 08:30:00 +00:00',
                'YYYY-MM-DD HH24:MI:SS TZH:TZM'
              )
         THEN 'SAME INSTANT'
         ELSE 'DIFFERENT INSTANT'
       END AS comparison_result
FROM dual;
~~~

Với hai thời điểm trên, kết quả là `SAME INSTANT`. Việc so chuỗi `'15:30'` và `'08:30'` có vẻ khác nhau, nhưng sau khi xét timezone chúng chỉ một instant.

**Không lấy `DBTIMEZONE` để tự gắn timezone cho `SYSDATE`** nếu chưa xác nhận server clock thực sự dùng timezone đó. `SYSDATE` đã mất thông tin timezone, nên không thể suy ra instant duy nhất của một giá trị `DATE` tùy ý nếu chưa có quy ước dữ liệu.

## 10. Dùng bốn hàm làm giá trị mặc định của cột

Chọn hàm default theo yêu cầu lưu dữ liệu, không chỉ theo định dạng bạn muốn nhìn thấy trên màn hình.

### 10.1. Lựa chọn cột phù hợp

| Nhu cầu | Kiểu cột / default tham khảo | Điều cần xác định |
| --- | --- | --- |
| Hệ thống legacy quản lý datetime bằng clock server, đến giây | `DATE DEFAULT SYSDATE` | Timezone ngầm của giá trị DATE phải được mô tả |
| Muốn DATE hiện tại theo timezone đã thiết lập cho mỗi session | `DATE DEFAULT CURRENT_DATE` | Pool phải khởi tạo session time zone nhất quán |
| Lưu instant tạo bản ghi với fractional seconds/offset | `TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP` | Xác định cách serialize/hiển thị cho các client |
| Lưu instant theo timezone của session đang insert | `TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP` | Session timezone phải được thiết lập/kiểm soát |
| Cần local datetime mà không mang offset | `TIMESTAMP` với hợp đồng timezone riêng | Không thể suy timezone chỉ từ giá trị đã lưu |
| Trường cần hiển thị theo timezone session khi đọc | `TIMESTAMP WITH LOCAL TIME ZONE` | Hiểu sự normalize về DB timezone và đổi hiển thị theo session |

### 10.2. Một bảng lab quan sát bốn default

Trong schema thực hành:

~~~sql
CREATE TABLE time_functions_lab (
    id                NUMBER PRIMARY KEY,
    server_date       DATE DEFAULT SYSDATE NOT NULL,
    server_timestamp  TIMESTAMP WITH TIME ZONE
                          DEFAULT SYSTIMESTAMP NOT NULL,
    session_date      DATE DEFAULT CURRENT_DATE NOT NULL,
    session_timestamp TIMESTAMP WITH TIME ZONE
                          DEFAULT CURRENT_TIMESTAMP NOT NULL
);
~~~

Đặt timezone session cho lần ghi thứ nhất:

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';

INSERT INTO time_functions_lab (id) VALUES (1);
COMMIT;
~~~

Đổi sang session timezone khác trong **chính phiên lab**:

~~~sql
ALTER SESSION SET TIME_ZONE = '-05:00';

INSERT INTO time_functions_lab (id) VALUES (2);
COMMIT;
~~~

Xem kết quả bằng format tường minh:

~~~sql
SELECT
    id,
    TO_CHAR(server_date, 'YYYY-MM-DD HH24:MI:SS') AS server_date_text,
    TO_CHAR(server_timestamp,
            'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM') AS server_ts_text,
    TO_CHAR(session_date, 'YYYY-MM-DD HH24:MI:SS') AS session_date_text,
    TO_CHAR(session_timestamp,
            'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM') AS session_ts_text
FROM time_functions_lab
ORDER BY id;
~~~

Những điều cần quan sát:

- Cột `SERVER_DATE` và `SESSION_DATE` là **DATE**, không giữ offset.
- Cột `SERVER_TIMESTAMP` và `SESSION_TIMESTAMP` giữ kiểu **TIMESTAMP WITH TIME ZONE**.
- Session timezone lúc **INSERT** chi phối `CURRENT_DATE` và `CURRENT_TIMESTAMP` được gán vào hàng.
- Cùng một bản ghi có thể chứa những biểu diễn local clock khác nhau nhưng cùng khoảng thời điểm tạo; từng default được đánh giá khi câu lệnh thực hiện.
- Hai hàng được insert ở hai thời điểm khác nhau nên **không được kỳ vọng giá trị UTC của chúng bằng nhau**; bài lab kiểm tra quy tắc timezone, không cố tạo hai hàng cùng instant.

Nếu muốn dọn bảng, chỉ thực hiện trên bảng lab do bạn vừa tạo:

~~~sql
DROP TABLE time_functions_lab;
~~~

`DROP TABLE` là DDL có tác động thật và commit theo hành vi DDL Oracle. Không chạy trên schema chia sẻ hoặc production.

### 10.3. Nên lấy timestamp ở database hay ứng dụng?

Không có một lựa chọn tuyệt đối cho mọi hệ thống:

- **Database default** như `SYSTIMESTAMP` giúp hàng nhận thời điểm từ một nguồn phía database ngay cả khi có nhiều client khác nhau, nhưng cần thiết kế thống nhất khi ứng dụng gửi giá trị riêng.
- **Application clock** có thể thuận tiện cho event tracing xuyên dịch vụ, nhưng phụ thuộc đồng bộ thời gian của từng node và quy tắc chuyển đổi khi bind JDBC.
- **Commit time** không tự đồng nghĩa với `DEFAULT SYSTIMESTAMP`: default thường được đánh giá trong lúc insert, trước hoặc khác thời điểm commit. Nếu nghiệp vụ đòi mốc commit chính xác, cần mô hình/event mechanism khác phù hợp.

Đối với audit cơ bản, timestamp tại database và kiểu lưu có timezone là lựa chọn dễ hiểu; đối với hệ thống phân tán, cần xác định rõ **event time**, **ingestion time** và **processing time** nếu chúng mang ý nghĩa khác nhau.

## 11. Lọc dữ liệu theo ngày: “hôm nay” của ai?

Giả sử bảng `APP_EVENTS` có `CREATED_AT` là `TIMESTAMP WITH TIME ZONE`. Nếu yêu cầu “mọi sự kiện thuộc ngày 14/11 theo giờ Việt Nam”, ta cần ranh giới ngày **theo vùng/offset Việt Nam**, không đơn giản `TRUNC(SYSDATE)` nếu server đang ở giờ khác.

Với một ngày cố định ở múi giờ `+07:00`:

~~~sql
SELECT *
FROM app_events
WHERE created_at >= FROM_TZ(
          TIMESTAMP '2026-11-14 00:00:00', '+07:00'
      )
  AND created_at <  FROM_TZ(
          TIMESTAMP '2026-11-15 00:00:00', '+07:00'
      );
~~~

Hai giá trị `FROM_TZ` chỉ định chính xác mốc **00:00 giờ Việt Nam** và mốc **00:00 ngày kế tiếp**, có offset rõ. Nếu bảng dùng timezone region có DST, nên tính hai đầu ngày theo **region và từng ngày cụ thể**, vì một ngày lịch có thể chỉ dài 23 hoặc 25 giờ theo UTC.

### 11.1. Vì sao dùng khoảng nửa mở?

Điều kiện:

~~~sql
WHERE created_at >= :day_start
  AND created_at <  :next_day_start
~~~

có các ưu điểm:

- Bao gồm mọi thời điểm trong ngày, kể cả phần lẻ giây.
- Không phải đoán “giây cuối ngày” là `23:59:59` hay `23:59:59.999999`.
- Tránh thao tác `TRUNC(created_at)` trên từng hàng trong điều kiện khi không cần thiết, thường thuận lợi hơn cho index/range scan.

Hai bind parameter phải cùng một hợp đồng **timezone và kiểu dữ liệu** với cột. Với cột `DATE` đã lưu local clock mà không có offset, việc so sánh với một TSTZ có thể dẫn đến chuyển đổi ngầm khó kiểm soát; trước tiên phải biết timezone nghiệp vụ của những giá trị DATE đó.

### 11.2. “Ngày hôm nay theo phiên” khác “24 giờ vừa qua”

Hai yêu cầu khác nhau:

- **Hôm nay theo session:** từ 00:00 của ngày hiện tại theo timezone người dùng đến 00:00 ngày sau.
- **24 giờ vừa qua:** khoảng 24 giờ liên tục tính ngược từ instant hiện tại.

Ở vùng có daylight saving time, một ngày lịch có thể có 23 hoặc 25 giờ, nên dùng cùng một công thức “trừ 1 ngày” cho cả hai yêu cầu có thể gây sai. Xác định nghiệp vụ trước rồi chọn hàm, timezone và kiểu cột.

## 12. SQL, JDBC và ứng dụng nhiều múi giờ

### 12.1. Phân biệt timezone của kết nối với timezone của người dùng

Một ứng dụng có server ở UTC và người dùng ở nhiều vùng có thể đặt timezone của mỗi session database theo UTC hoặc theo timezone người dùng. Nếu dùng connection pool, nhiều request có thể dùng lại cùng một session vật lý. Khi đó:

1. Nếu toàn ứng dụng quy ước **database session luôn UTC**, cần khởi tạo/kiểm tra timezone trên mọi connection theo chính sách pool.
2. Nếu session theo timezone người dùng, bắt buộc thiết lập lại theo request/người dùng và kiểm soát không rò timezone giữa các request.
3. Nếu chỉ muốn hiển thị giờ địa phương, thường có thể **giữ instant có timezone** trong database và chuyển đổi ở tầng presentation theo timezone người dùng, thay vì đổi timezone session cho mọi truy vấn.

Ví dụ ứng dụng đặt session timezone:

~~~sql
ALTER SESSION SET TIME_ZONE = '+00:00';

SELECT SESSIONTIMEZONE FROM dual;
~~~

Kiểm tra `SESSIONTIMEZONE` trước khi dựa vào `CURRENT_DATE`/`CURRENT_TIMESTAMP`. Giá trị có thể là offset hoặc region name tùy session và cách thiết lập.

### 12.2. Java time API và ánh xạ Oracle

Tư duy lập trình tương ứng:

| Java type | Ý nghĩa | Cảnh báo khi ánh xạ |
| --- | --- | --- |
| `LocalDate` | Ngày lịch, không có giờ/offset | Phù hợp ngày sinh, ngày nghỉ nếu không cần instant |
| `LocalDateTime` | Ngày + giờ local, không timezone | Không tự xác định instant khi dùng nhiều timezone |
| `Instant` | Mốc thời gian tuyệt đối (UTC timeline) | Cần driver/mapping rõ ràng khi lưu SQL |
| `OffsetDateTime` | Local date-time với UTC offset | Gần ý nghĩa của một `TIMESTAMP WITH TIME ZONE` dạng offset |
| `ZonedDateTime` | Local date-time với timezone region và các quy tắc của nó | Cần kiểm tra driver/ORM có giữ đủ region hay chỉ offset |

Trong Java/JDBC hiện đại, `PreparedStatement` với mapping phù hợp giúp truyền dữ liệu datetime có kiểu rõ ràng. Ví dụ minh họa với driver hỗ trợ JDBC 4.2:

~~~java
import java.sql.PreparedStatement;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

OffsetDateTime capturedAt = OffsetDateTime.now(ZoneOffset.UTC);

String sql = """
    INSERT INTO app_events (event_id, created_at)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, eventId);
    ps.setObject(2, capturedAt);
    ps.executeUpdate();
}
~~~

Ví dụ giả định cột `CREATED_AT` là `TIMESTAMP WITH TIME ZONE` và driver Oracle được dùng **hỗ trợ mapping `OffsetDateTime` như mong muốn**. Hãy kiểm thử round-trip bằng driver/ORM phiên bản đang triển khai. Không tự động chuyển `java.sql.Timestamp` hoặc `LocalDateTime` sang instant bằng timezone mặc định của JVM khi chưa có hợp đồng rõ.

### 12.3. Tránh lưu giờ dưới dạng chuỗi

Một cột `VARCHAR2(50)` chứa `2026-11-14T15:30:00+07:00` nhìn có vẻ đủ thông tin, nhưng database sẽ coi nó là **văn bản**, dẫn tới khó đảm bảo format, ràng buộc, so sánh thời gian và xử lý timezone. Với sự kiện thời gian, dùng kiểu datetime Oracle phù hợp, còn chuỗi ISO 8601 dùng ở ranh giới API để trao đổi.

Nếu xuất ra JSON:

~~~sql
SELECT
    TO_CHAR(
        created_at AT TIME ZONE 'UTC',
        'YYYY-MM-DD"T"HH24:MI:SS.FF3TZH:TZM'
    ) AS created_at_utc_text
FROM app_events;
~~~

Chuỗi này là **cách serialize cho API**, không nên bị nhầm với dạng lưu tốt nhất bên trong database. Khi cần ISO 8601 chuẩn cho nhiều môi trường, kiểm tra cả fractional precision, offset và quy ước `Z` ở API cụ thể.

## 13. Những lỗi thường gặp và cách xác định nguyên nhân

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `SYSDATE` khác `CURRENT_DATE` vài giờ | Server clock timezone khác session timezone | Hiển thị tường minh cả hai; xem `SESSIONTIMEZONE` và cấu hình server |
| `SYSTIMESTAMP` khác `CURRENT_TIMESTAMP` về giờ/offset | Hai hàm dùng timezone phía server và session | Chuyển cả hai sang UTC hoặc cùng một timezone để đối chiếu instant |
| `SYSDATE` chỉ hiện ngày, không có giờ | NLS/client format ẩn phần giờ | `TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS')` |
| Giá trị `DATE` không hiển thị `.123` hoặc `+07:00` | `DATE` không chứa fractional seconds/timezone | Dùng `TIMESTAMP WITH TIME ZONE` nếu cần |
| `ORA-01861` khi parse chuỗi ngày | Chuỗi không khớp format mask hoặc phụ thuộc NLS | Dùng `TO_DATE`/`TO_TIMESTAMP_TZ` với mask rõ, hoặc bind kiểu datetime |
| `ORA-01843` | Giá trị/tháng không hợp lệ hoặc định dạng ngôn ngữ không khớp | Xem input, `NLS_DATE_LANGUAGE`, format và calendar |
| “Hôm nay” trả số hàng khác người dùng kỳ vọng | Trộn server day và user day, hoặc cột DATE lưu theo múi giờ khác | Xác định timezone của cả giới hạn và cột, chuyển về cùng instant |
| JDBC và SQL*Plus hiển thị khác nhau | Client format hoặc timezone mapping khác | Kiểm tra NLS/session/JVM/driver và giá trị thực qua explicit format |
| Session này có giờ đúng, session khác sai | Timezone/NLS được thay đổi riêng cho từng session | Kiểm tra `SESSIONTIMEZONE` và NLS mỗi session; cấu hình pool |
| Sau migration host, giờ legacy DATE khó so sánh | `DATE` đã lưu local clock mà không giữ timezone | Xác định timezone lịch sử theo metadata/vận hành trước khi chuyển đổi |
| Dữ liệu ở ngày chuyển DST không nhất quán | Sử dụng fixed offset thay region hoặc local time mơ hồ | Xem timezone region, ngày cụ thể, offset và quy tắc DST |

### 13.1. Bộ truy vấn chẩn đoán tối thiểu

~~~sql
SELECT
    SESSIONTIMEZONE AS session_tz,
    DBTIMEZONE AS db_tz,
    TO_CHAR(SYSDATE,      'YYYY-MM-DD HH24:MI:SS') AS sys_date,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS current_date_value,
    TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM')
        AS sys_ts,
    TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM')
        AS current_ts
FROM dual;

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT',
    'NLS_DATE_LANGUAGE'
)
ORDER BY parameter;
~~~

Đây là bước đầu tiên trước khi thay `ALTER SESSION SET TIME_ZONE` hoặc format NLS. Nó cho thấy cả **giá trị đã định dạng rõ** và môi trường phiên, tránh nhầm do công cụ hiển thị.

### 13.2. Quy trình suy luận khi có lỗi thời gian

1. **Xác định câu hỏi nghiệp vụ:** cần instant tuyệt đối, ngày lịch theo user, hay giờ ở một địa điểm?
2. **Kiểm tra kiểu cột thật:** `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE` hay `TIMESTAMP WITH LOCAL TIME ZONE`.
3. **Xác định nguồn giá trị:** `SYSDATE`, `CURRENT_DATE`, application clock, file import hay migration.
4. **Kiểm tra timezone:** server host, session, giá trị có offset/region hay không, và có liên quan DST không.
5. **Tách dữ liệu khỏi cách hiển thị:** dùng format `TO_CHAR` rõ ràng hoặc truy cập datetime có kiểu qua driver.
6. **So sánh cùng instant:** đổi dữ liệu có timezone về UTC/cùng region trước khi so; không chỉ so chuỗi giờ local.
7. **Áp dụng sửa đổi nhỏ nhất:** sửa contract, format hoặc session initialization tại đúng chỗ và kiểm thử với trường hợp cận ranh giới ngày.

## 14. Bài thực hành tổng hợp

Bài sau chỉ cần quyền `SELECT FROM DUAL` và quyền `ALTER SESSION` thông thường, trừ phần tạo bảng tùy chọn. Hãy sử dụng **một phiên SQL mới** để không làm thay đổi timezone/NLS của ứng dụng đang dùng chung.

### Bước 1 — Xem cả bốn hàm trong một lần truy vấn

~~~sql
SELECT
    TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS') AS sysdate_value,
    TO_CHAR(SYSTIMESTAMP,
            'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM') AS systimestamp_value,
    TO_CHAR(CURRENT_DATE,
            'YYYY-MM-DD HH24:MI:SS') AS current_date_value,
    TO_CHAR(CURRENT_TIMESTAMP,
            'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM') AS current_timestamp_value
FROM dual;
~~~

Ghi lại: cặp nào theo server, cặp nào theo session, cặp nào có timezone?

### Bước 2 — Ghi timezone và NLS hiện tại

~~~sql
SELECT SESSIONTIMEZONE, DBTIMEZONE FROM dual;

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_DATE_FORMAT', 'NLS_TIMESTAMP_TZ_FORMAT');
~~~

Ghi lại giá trị `SESSIONTIMEZONE` để khôi phục nếu cần. Không giả định nó trùng `DBTIMEZONE`.

### Bước 3 — Chuyển session timezone sang `+07:00`

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';

SELECT
    SESSIONTIMEZONE AS tz,
    TO_CHAR(SYSDATE,      'YYYY-MM-DD HH24:MI:SS') AS server_now,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS session_now
FROM dual;
~~~

Hãy giải thích vì sao `CURRENT_DATE` hiển thị giờ `+07:00` còn `SYSDATE` thường tiếp tục theo server. Không cần server đặt ở UTC để thực hiện phép thử này.

### Bước 4 — Chuyển session timezone sang `-05:00`

~~~sql
ALTER SESSION SET TIME_ZONE = '-05:00';

SELECT
    SESSIONTIMEZONE AS tz,
    TO_CHAR(SYSTIMESTAMP,
            'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM') AS server_ts,
    TO_CHAR(CURRENT_TIMESTAMP,
            'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM') AS session_ts
FROM dual;
~~~

Quan sát offset trong `CURRENT_TIMESTAMP` và giờ server trong `SYSTIMESTAMP`. Dùng thêm `AT TIME ZONE 'UTC'` cho từng timestamp để so cách biểu diễn ở cùng timezone.

### Bước 5 — Kiểm tra NLS format

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';

SELECT SYSDATE, CURRENT_DATE FROM dual;

SELECT
    TO_CHAR(SYSDATE,      'YYYY-MM-DD HH24:MI:SS') AS explicit_server,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM-DD HH24:MI:SS') AS explicit_session
FROM dual;
~~~

Nếu công cụ chuyển kết quả theo `NLS_DATE_FORMAT`, truy vấn đầu có thể chỉ còn hiện ngày; truy vấn thứ hai vẫn hiển thị đầy đủ theo format mask bạn viết. Giá trị DATE không hề mất giờ sau `ALTER SESSION`.

### Bước 6 — So sánh hai giá trị xác định cùng instant

~~~sql
SELECT
    TO_CHAR(
        FROM_TZ(TIMESTAMP '2026-11-14 15:30:00', '+07:00')
            AT TIME ZONE 'UTC',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ) AS converted_utc,
    TO_CHAR(
        TO_TIMESTAMP_TZ(
            '2026-11-14 08:30:00 +00:00',
            'YYYY-MM-DD HH24:MI:SS TZH:TZM'
        ),
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ) AS direct_utc
FROM dual;
~~~

Hai giá trị trả về phải cùng biểu diễn UTC của một instant, nếu câu lệnh được thực hiện theo các kiểu datetime đã nêu.

### Bước 7 — Khôi phục môi trường phiên hoặc thoát

Khôi phục session time zone và format NLS theo những giá trị đã ghi ở Bước 2, hoặc đóng phiên lab. Không dùng connection đang chia sẻ cho bài thử có `ALTER SESSION`.

## 15. Những nhầm lẫn cần tránh

**“`SYSDATE` chỉ có ngày.”** Sai. Oracle `DATE` giữ cả giờ đến giây; có thể format của client đang ẩn giờ.

**“`CURRENT_DATE` chỉ có ngày.”** Sai. Nó là `DATE` chứa ngày + giờ theo session time zone.

**“`SYSTIMESTAMP` và `CURRENT_TIMESTAMP` luôn phải có cùng chuỗi hiển thị.”** Sai. Chúng có thể trình bày cùng instant theo timezone khác nhau, do đó local clock và offset khác nhau.

**“`DBTIMEZONE` luôn là timezone của hệ điều hành database server.”** Sai. `DBTIMEZONE` là thuộc tính riêng của database, nhất là liên quan `TIMESTAMP WITH LOCAL TIME ZONE`.

**“Đổi `NLS_DATE_FORMAT` sẽ đổi ngày/giờ đã lưu.”** Sai. NLS format thay cách chuyển đổi/hiển thị; dữ liệu datetime vẫn mang kiểu gốc.

**“`DATE` tự biết timezone người dùng.”** Sai. DATE không chứa offset hay region. Cần quy ước hoặc chọn kiểu timezone-aware cho instant.

**“`FROM_TZ` và `AT TIME ZONE` giống nhau.”** Sai. `FROM_TZ` gắn timezone vào local timestamp chưa có timezone; `AT TIME ZONE` chuyển instant đã xác định sang cách biểu diễn ở timezone đích.

**“Dùng `TO_DATE(SYSDATE, ... )` để in theo format.”** Sai. `SYSDATE` đã là DATE; định dạng đầu ra dùng `TO_CHAR`.

**“00:00 mỗi ngày luôn cách nhau chính xác 24 giờ.”** Sai ở các vùng có chuyển daylight saving time. Bài toán ngày lịch theo vùng và khoảng 24 giờ tuyệt đối có thể khác nhau.

**“Dùng `CURRENT_TIMESTAMP` là đủ, connection pool không ảnh hưởng.”** Sai. Timezone của session có thể bị ảnh hưởng bởi connection initialization hoặc thay đổi từ request trước; cần kiểm soát khi dùng pool.

## 16. Câu hỏi tự kiểm tra

1. Trong bốn hàm, hàm nào trả về kiểu `DATE`, hàm nào trả về `TIMESTAMP WITH TIME ZONE`?
2. Session `+07:00`, server theo UTC. Khi server là `2026-11-14 20:00:00`, `CURRENT_DATE` có thể là ngày nào?
3. Vì sao `SYSDATE` và `CURRENT_DATE` có thể khác ngày, dù truy vấn chạy trong một giây?
4. Khi cần hiển thị mili giây và UTC offset, chọn `SYSDATE` hay `SYSTIMESTAMP`?
5. `SESSIONTIMEZONE` và `DBTIMEZONE` có luôn bằng nhau không?
6. `ALTER SESSION SET TIME_ZONE = '+07:00'` có đổi clock hệ điều hành của server không?
7. `ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY'` có xóa giờ trong một cột `DATE` không?
8. Vì sao `TO_DATE('14/11/2026')` có thể thiếu an toàn nếu không có format mask?
9. `FROM_TZ(TIMESTAMP '2026-11-14 15:30:00', '+07:00')` và timestamp `2026-11-14 08:30:00 +00:00` có cùng instant không?
10. Vì sao không thể tự suy timezone của một giá trị `DATE` lưu từ năm trước chỉ bằng cách đọc `DBTIMEZONE` hiện tại?
11. Bảng audit cần ghi instant và fractional seconds cho nhiều người dùng: vì sao `TIMESTAMP WITH TIME ZONE` thường rõ nghĩa hơn `DATE`?
12. Một người dùng hỏi “sự kiện hôm nay” ở New York. Vì sao không nên mặc định dùng `TRUNC(SYSDATE)` làm mốc ngày?
13. Tại sao một ngày theo region có DST đôi khi dài 23 hoặc 25 giờ?
14. Một ứng dụng thay `TIME_ZONE` theo user trên connection pool: rủi ro gì nếu không reset khi trả connection?
15. `DEFAULT SYSTIMESTAMP` trên bảng có luôn đồng nghĩa thời điểm `COMMIT` không?

**Gợi ý trả lời:**

1. `SYSDATE`/`CURRENT_DATE` trả `DATE`; `SYSTIMESTAMP`/`CURRENT_TIMESTAMP` trả `TIMESTAMP WITH TIME ZONE`.
2. Theo `+07:00` là `2026-11-15 03:00:00`.
3. Chúng diễn giải thời gian theo clock server và timezone session khác nhau.
4. `SYSTIMESTAMP` hoặc `CURRENT_TIMESTAMP`, dùng `TO_CHAR(..., '...FF3 TZH:TZM')`.
5. Không.
6. Không, chỉ đổi timezone của session.
7. Không, chỉ đổi cách hiển thị/chuyển ngầm.
8. Oracle có thể sử dụng NLS format của phiên và parse sai hoặc báo lỗi.
9. Có, cùng instant.
10. `DATE` không lưu offset; `DBTIMEZONE` không mặc định mô tả timezone gốc của mọi dữ liệu.
11. Nó giữ thông tin timezone và phần lẻ giây để so sánh instant minh bạch hơn.
12. Ngày của server có thể khác ngày của người dùng; phải xây giới hạn theo vùng giờ nghiệp vụ.
13. Clock tại vùng đó được điều chỉnh tiến/lùi do DST.
14. Session sau có thể thừa hưởng timezone của người dùng trước, làm sai kết quả `CURRENT_DATE`/`CURRENT_TIMESTAMP`.
15. Không, default thường được đánh giá lúc insert, không phải một dấu mốc commit được bảo đảm.

## Tài liệu tham khảo Oracle

- [Oracle SQL Language Reference — SYSDATE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SYSDATE.html): kiểu DATE và nguồn giờ phía server.
- [Oracle SQL Language Reference — SYSTIMESTAMP](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SYSTIMESTAMP.html): kiểu TIMESTAMP WITH TIME ZONE và thời gian server.
- [Oracle SQL Language Reference — CURRENT_DATE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CURRENT_DATE.html): giá trị DATE theo session time zone.
- [Oracle SQL Language Reference — CURRENT_TIMESTAMP](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CURRENT_TIMESTAMP.html): timestamp theo session time zone.
- [Oracle SQL Language Reference — Datetime Data Types and Time Zone Support](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html): DATE, TIMESTAMP, TIMESTAMP WITH TIME ZONE và TIMESTAMP WITH LOCAL TIME ZONE.
- [Oracle SQL Language Reference — FROM_TZ](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FROM_TZ.html): cách gắn timezone cho local timestamp.
- [Oracle SQL Language Reference — SYS_EXTRACT_UTC](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SYS_EXTRACT_UTC.html): trích xuất giá trị UTC.
- [Oracle Database Globalization Support Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/): NLS datetime formats, múi giờ và các lưu ý về daylight saving time.
