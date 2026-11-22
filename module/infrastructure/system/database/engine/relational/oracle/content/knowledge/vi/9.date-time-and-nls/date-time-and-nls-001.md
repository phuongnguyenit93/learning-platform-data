# NLS_DATABASE_PARAMETERS, NLS_INSTANCE_PARAMETERS và NLS_SESSION_PARAMETERS

Trong Oracle Database, cùng một cột `DATE` có thể được công cụ A hiển thị thành `14/11/2026`, còn công cụ B hiển thị thành `2026-11-14 09:30:00`. Một lệnh chuyển chuỗi sang ngày có thể chạy ở máy phát triển nhưng báo `ORA-01861` khi triển khai. Để tìm nguyên nhân, cần phân biệt **cấu hình NLS ở database**, **cấu hình NLS ở instance**, và **giá trị NLS thực sự đang có hiệu lực trong phiên SQL**.

Ba data dictionary view `NLS_DATABASE_PARAMETERS`, `NLS_INSTANCE_PARAMETERS` và `NLS_SESSION_PARAMETERS` giúp trả lời ba câu hỏi khác nhau. Bài học này hướng dẫn truy vấn, đối chiếu và diễn giải chúng trong bối cảnh **ngày giờ và National Language Support (NLS)**, rồi áp dụng vào SQL*Plus, SQL Developer, JDBC và ứng dụng có connection pool.

> **Ý chính:** Khi một câu SQL đang chạy có vấn đề với định dạng ngày, số hoặc ngôn ngữ, cần xem `NLS_SESSION_PARAMETERS` của **chính phiên chạy câu SQL đó**. Giá trị ở database hay instance chỉ là một phần ngữ cảnh; chúng không bảo đảm mọi client dùng cùng định dạng.

## 1. NLS nằm ở những cấp nào?

**NLS (National Language Support)** là hệ thống cấu hình của Oracle để hỗ trợ ngôn ngữ, lãnh thổ, cách trình bày và diễn giải ngày giờ, số, ký tự và một số quy tắc sắp xếp/so sánh. NLS không phải một kiểu dữ liệu riêng.

~~~mermaid
flowchart TD
    A["Database: các mặc định và đặc tính NLS"] --> B["Instance: cấu hình NLS ở cấp instance"]
    B --> C["Session được tạo khi client kết nối"]
    D["Client/driver: SQL*Plus, SQL Developer, JDBC..."] --> C
    E["ALTER SESSION SET NLS_..."] --> C
    C --> F["SQL trong phiên: TO_CHAR, TO_DATE, implicit conversion..."]
    G["Kiểu DATE/TIMESTAMP/NUMBER được lưu có cấu trúc"] --> F
~~~

Sơ đồ cho thấy **các nguồn ảnh hưởng**, không phải phép sao chép tuần tự mọi giá trị từ database → instance → session. Một số giá trị của phiên có thể được xác lập khi đăng nhập, được client/driver khởi tạo, hoặc được sửa tường minh bằng `ALTER SESSION`. Một số thuộc tính ở cấp database, điển hình là character set, không phải thiết lập có thể thay đổi tùy ý trong một session.

| View | Phạm vi cần hiểu | Dùng khi nào? |
|---|---|---|
| `NLS_DATABASE_PARAMETERS` | Các thông tin/cấu hình NLS cấp database, gồm các đặc tính bền vững như character set | Xác định cấu hình NLS của database đang kết nối; hiểu mặc định và khả năng lưu ký tự |
| `NLS_INSTANCE_PARAMETERS` | Các thiết lập NLS được Oracle ghi nhận ở cấp instance, từ cấu hình khởi tạo/điều khiển instance tương ứng | Đối chiếu cấu hình instance với giá trị cấp database và phiên |
| `NLS_SESSION_PARAMETERS` | Giá trị NLS đang có hiệu lực **trong session hiện tại** | Chẩn đoán định dạng ngày, ngôn ngữ tháng, số, cách diễn giải chuỗi trong SQL đang chạy |

Cả ba thường có hai cột dễ sử dụng: `PARAMETER` và `VALUE`. **Không nên coi ba view là ba bản sao đồng bộ**: danh sách tham số có thể khác nhau, và cùng một tên tham số có thể có giá trị khác nhau theo phạm vi.

## 2. Xem chính xác ba view trong một kết nối

Các câu `SELECT` sau là phép quan sát, không làm thay đổi dữ liệu hay cấu hình.

### 2.1 Xem cấu hình database

~~~sql
SELECT parameter, value
FROM nls_database_parameters
ORDER BY parameter;
~~~

Những hàng có ý nghĩa đặc biệt:

- `NLS_CHARACTERSET`: bộ ký tự chính của database, dùng cho các kiểu như `VARCHAR2` và `CLOB`.
- `NLS_NCHAR_CHARACTERSET`: bộ ký tự quốc gia, dùng cho `NCHAR`, `NVARCHAR2`, `NCLOB`.
- Các hàng NLS khác mô tả giá trị nền/mặc định mà database ghi nhận; chúng **không tự chứng minh** phiên ứng dụng hiện dùng cùng một giá trị.

Ví dụ kết quả trích lọc **minh họa**:

~~~text
PARAMETER               VALUE
----------------------  --------
NLS_CHARACTERSET        AL32UTF8
NLS_NCHAR_CHARACTERSET  AL16UTF16
NLS_LANGUAGE            AMERICAN
NLS_TERRITORY           AMERICA
~~~

Ví dụ này không phải kết quả cố định của mọi Oracle. Muốn kết luận database thực tế hỗ trợ lưu tiếng Việt bằng kiểu ký tự thông thường hay không, cần xem đúng `NLS_CHARACTERSET` của hệ thống/PDB được sử dụng.

### 2.2 Xem cấu hình instance

~~~sql
SELECT parameter, value
FROM nls_instance_parameters
ORDER BY parameter;
~~~

View này phản ánh thông tin NLS ở **instance đang phục vụ phiên**. Những tham số như `NLS_LANGUAGE` hoặc `NLS_TERRITORY` có thể phản ánh cấu hình cấp instance, và có thể khác với các giá trị cấp database.

Oracle RAC có thể có nhiều instance phục vụ cùng database. Nếu đang khảo sát sự khác nhau giữa các node, hãy ghi lại instance/host cho mỗi kết nối; một phép đọc `NLS_INSTANCE_PARAMETERS` từ node A không tự đại diện cho mọi node.

### 2.3 Xem cấu hình session

~~~sql
SELECT parameter, value
FROM nls_session_parameters
ORDER BY parameter;
~~~

Đây là điểm kiểm tra chính đối với **một câu SQL cụ thể**. Ví dụ cần chú ý:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_DATE_LANGUAGE',
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT',
    'NLS_NUMERIC_CHARACTERS',
    'NLS_CALENDAR',
    'NLS_SORT',
    'NLS_COMP'
)
ORDER BY parameter;
~~~

Lưu ý tên cột `VALUE` trong các view là **chuỗi mô tả giá trị tham số**, không phải bản lưu các giá trị ngày giờ trong bảng ứng dụng. Một thay đổi ở `NLS_DATE_FORMAT` không tự chỉnh sửa hàng nào trong cột `DATE`.

### 2.4 Lấy bối cảnh của phép đo

Trước khi so sánh kết quả hai người gửi từ hai máy, xác định session đang ở database/container/instance nào:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

Nếu có quyền xem dynamic performance view:

~~~sql
SELECT instance_name, host_name, version
FROM v$instance;

SELECT name, cdb, open_mode
FROM v$database;
~~~

Trong kiến trúc CDB/PDB, kết quả của một số view và quyền xem metadata phụ thuộc **container hiện tại**. Khi so sánh cần ghi kèm tên PDB, service và instance. Không lấy giá trị từ `CDB$ROOT` rồi mặc định mọi PDB hoặc mọi ứng dụng đều có cùng trạng thái cấu hình.

## 3. Đặt ba nguồn lên cùng một bảng để đối chiếu

Có thể so sánh những tham số NLS cùng tên bằng một truy vấn pivot đơn giản:

~~~sql
WITH nls_values AS (
    SELECT 'DATABASE' AS scope_name, parameter, value
    FROM nls_database_parameters
    UNION ALL
    SELECT 'INSTANCE' AS scope_name, parameter, value
    FROM nls_instance_parameters
    UNION ALL
    SELECT 'SESSION' AS scope_name, parameter, value
    FROM nls_session_parameters
)
SELECT parameter,
       MAX(CASE WHEN scope_name = 'DATABASE' THEN value END)
           AS database_value,
       MAX(CASE WHEN scope_name = 'INSTANCE' THEN value END)
           AS instance_value,
       MAX(CASE WHEN scope_name = 'SESSION' THEN value END)
           AS session_value
FROM nls_values
WHERE parameter IN (
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_NUMERIC_CHARACTERS',
    'NLS_TIMESTAMP_FORMAT'
)
GROUP BY parameter
ORDER BY parameter;
~~~

Ví dụ kết quả **giả định để đọc ý nghĩa**, không phải giá trị mặc định bắt buộc:

| Parameter | Database | Instance | Session |
|---|---|---|---|
| `NLS_LANGUAGE` | `AMERICAN` | `AMERICAN` | `AMERICAN` |
| `NLS_TERRITORY` | `AMERICA` | `AMERICA` | `VIETNAM` |
| `NLS_DATE_FORMAT` | `DD-MON-RR` | `DD-MON-RR` | `YYYY-MM-DD HH24:MI:SS` |
| `NLS_NUMERIC_CHARACTERS` | `.,` | `.,` | `,.` |

Nếu trong kết quả thật có ô `NULL` ở một cột, cần xem **tham số đó có xuất hiện trong view tương ứng không**; không tự hiểu `NULL` là giá trị NLS đang dùng. Ba view không nhất thiết chứa cùng tập tham số, ví dụ các thông tin character set cấp database không cần có bản sao tương đương trong view session.

**Diễn giải đúng ví dụ:** phiên hiện tại dùng `NLS_DATE_FORMAT = YYYY-MM-DD HH24:MI:SS`, dù ở database/instance có giá trị khác. Khi Oracle phải chuyển một `DATE` thành chuỗi theo **mặc định phiên**, kết quả có thể theo định dạng này. Truy vấn database/instance vẫn hữu ích để giải thích vì sao các phiên có thể khởi đầu khác nhau, nhưng không được dùng thay cho giá trị của session đang lỗi.

### Vì sao các giá trị có thể khác nhau?

Một số nguyên nhân:

1. Database được tạo với các đặc tính NLS nhất định.
2. Instance được khởi động với tham số NLS trong cấu hình tương ứng.
3. Client/driver khởi tạo session và có thể cung cấp thiết lập ngôn ngữ/lãnh thổ/định dạng theo cách riêng.
4. Một logon trigger, công cụ SQL hoặc ứng dụng có thể chạy `ALTER SESSION`.
5. Connection pool giữ session tồn tại qua nhiều request; trạng thái phiên có thể bị ảnh hưởng bởi thao tác trước đó nếu không được quản lý đúng.

Không nên chỉ dựa vào ba giá trị cuối cùng để tuyên bố chắc chắn **ai** đã đổi tham số và **vào thời điểm nào**. Ba view là ảnh chụp trạng thái, không phải lịch sử audit của mọi lần `ALTER SESSION`.

## 4. NLS_DATE_FORMAT: định dạng ngày không phải bản chất dữ liệu DATE

Trong Oracle, kiểu `DATE` lưu thông tin **năm, tháng, ngày, giờ, phút, giây**, nhưng không lưu múi giờ và không có phần giây lẻ. Giá trị trong cột `DATE` không được lưu dưới dạng chuỗi `DD/MM/YYYY` hay `YYYY-MM-DD`.

`NLS_DATE_FORMAT` quyết định một số quy tắc **chuyển đổi mặc định giữa DATE và chuỗi**, đặc biệt khi hiển thị giá trị ngày thông qua client hoặc thực hiện implicit conversion. Nó không biến `DATE` thành `VARCHAR2`.

### 4.1 Quan sát trước và sau ALTER SESSION

Trong **một session thực hành riêng**:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_DATE_FORMAT';

SELECT DATE '2026-11-14' AS order_date
FROM dual;
~~~

Đặt định dạng rõ ràng:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';

SELECT DATE '2026-11-14' AS order_date
FROM dual;
~~~

Ví dụ trong công cụ hiển thị theo định dạng session, cột `ORDER_DATE` có thể hiện `14/11/2026`. Đổi tiếp:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';

SELECT DATE '2026-11-14' AS order_date
FROM dual;
~~~

Giá trị có thể hiện `2026-11-14 00:00:00`. **Giá trị DATE không đổi**; biểu thức `DATE '2026-11-14'` chỉ định ngày với phần thời gian nửa đêm. Cách giao diện render có thể còn bị thiết lập hiển thị riêng của một số công cụ tác động.

Để kiểm tra chính xác chuỗi đầu ra độc lập với `NLS_DATE_FORMAT`, dùng `TO_CHAR` có format model:

~~~sql
SELECT TO_CHAR(
           DATE '2026-11-14',
           'YYYY-MM-DD HH24:MI:SS'
       ) AS stable_date_text
FROM dual;
~~~

Kết quả là `2026-11-14 00:00:00` theo format đã ghi. `TO_CHAR` trả về **VARCHAR2**, phù hợp khi cần xuất báo cáo dạng văn bản cố định. Trong mã ứng dụng, nên giữ dữ liệu là kiểu ngày/giờ càng lâu càng tốt và chỉ định dạng ở điểm cần hiển thị.

### 4.2 Vì sao chuyển đổi ngầm định dễ lỗi?

Ví dụ câu SQL phụ thuộc cấu hình phiên:

~~~sql
-- Oracle có thể phải chuyển chuỗi thành DATE ngầm định:
SELECT *
FROM orders
WHERE created_at >= '14/11/2026';
~~~

Giả sử `CREATED_AT` là kiểu `DATE`, chuỗi `'14/11/2026'` cần được diễn giải thành ngày. Phiên dùng `NLS_DATE_FORMAT = 'DD/MM/YYYY'` có thể chấp nhận, nhưng phiên dùng format khác có thể báo lỗi như `ORA-01861` hoặc `ORA-01843`.

Viết rõ kiểu dữ liệu/format:

~~~sql
-- DATE literal dùng định dạng ISO cố định:
SELECT *
FROM orders
WHERE created_at >= DATE '2026-11-14';

-- Khi dữ liệu đầu vào là chuỗi theo một định dạng quy ước:
SELECT TO_DATE(
           '14/11/2026 09:30:00',
           'DD/MM/YYYY HH24:MI:SS'
       ) AS parsed_date
FROM dual;
~~~

`DATE 'YYYY-MM-DD'` không phụ thuộc vào `NLS_DATE_FORMAT` của phiên. `TO_DATE` có format model tường minh giúp loại bỏ nhiều mơ hồ. Đối với giá trị ngày đến từ Java/JDBC, cách thích hợp hơn nữa là **bind tham số bằng kiểu ngày/giờ**, tránh tự nối chuỗi vào SQL.

### 4.3 DATE có phần thời gian nên dùng khoảng nửa mở

Khi tìm toàn bộ dữ liệu ngày 14/11/2026 trong một cột `DATE` có giờ/phút/giây:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';
~~~

Cách lọc từ đầu ngày tới **trước đầu ngày tiếp theo** không phụ thuộc format hiển thị. So sánh `created_at = DATE '2026-11-14'` chỉ khớp các giá trị đúng 00:00:00, không đại diện cho mọi thời điểm trong ngày.

## 5. NLS_DATE_LANGUAGE và NLS_TERRITORY: cùng là NLS nhưng tác động khác nhau

### 5.1 NLS_DATE_LANGUAGE điều khiển tên tháng và tên ngày

`NLS_DATE_LANGUAGE` liên quan ngôn ngữ dùng để hiển thị hoặc diễn giải tên tháng/thứ theo format model chứa `MON`, `MONTH`, `DAY`... Nó **không đổi tháng/năm được lưu** trong giá trị `DATE`.

~~~sql
SELECT TO_CHAR(
           DATE '2026-11-14',
           'FMMonth',
           'NLS_DATE_LANGUAGE=AMERICAN'
       ) AS month_american,
       TO_CHAR(
           DATE '2026-11-14',
           'FMMonth',
           'NLS_DATE_LANGUAGE=FRENCH'
       ) AS month_french
FROM dual;
~~~

Ví dụ mong đợi là tên tháng tiếng Anh và tiếng Pháp tương ứng (chẳng hạn `November` và `Novembre`). Tham số thứ ba của `TO_CHAR` đặt ngôn ngữ **cho phép chuyển đổi đó**, không cần thay đổi toàn session.

Tương tự, khi nguồn là chuỗi có tên tháng:

~~~sql
SELECT TO_DATE(
           '14-NOV-2026',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=AMERICAN'
       ) AS parsed_date
FROM dual;
~~~

Nếu bỏ tham số ngôn ngữ và session dùng một ngôn ngữ khác, cùng chuỗi tên tháng có thể không được nhận diện như dự định. Với các API giữa hệ thống, format số tháng (`MM`) thường ít lệ thuộc ngôn ngữ hơn tên tháng (`MON`/`MONTH`).

### 5.2 NLS_TERRITORY ảnh hưởng các mặc định theo vùng

`NLS_TERRITORY` thể hiện quy ước lãnh thổ và có thể ảnh hưởng mặc định của một số tham số như định dạng ngày và ký tự số, nếu chưa được chỉ định riêng. `NLS_LANGUAGE` chủ yếu liên quan ngôn ngữ; `NLS_TERRITORY` liên quan quy ước vùng. Không nên mặc định rằng cứ thấy `NLS_TERRITORY = VIETNAM` thì tất cả ngày tháng ứng dụng chắc chắn hiển thị theo một mẫu duy nhất.

Có thể quan sát đồng thời:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_DATE_LANGUAGE',
    'NLS_DATE_FORMAT',
    'NLS_NUMERIC_CHARACTERS'
)
ORDER BY parameter;
~~~

Khi `NLS_DATE_FORMAT` đã được đặt trực tiếp bằng `ALTER SESSION` hoặc client, phải đọc giá trị đó, không suy ra ngược từ `NLS_TERRITORY`. Một số thiết lập NLS có quan hệ với nhau ở giai đoạn xác lập mặc định, song **giá trị hiện hành** trong session vẫn là bằng chứng quan trọng nhất đối với truy vấn đang chạy.

## 6. NLS_TIMESTAMP_FORMAT và NLS_TIMESTAMP_TZ_FORMAT

Oracle phân biệt một số kiểu thời gian:

| Kiểu dữ liệu | Lưu những gì? | NLS định dạng mặc định có liên quan |
|---|---|---|
| `DATE` | Ngày + giờ/phút/giây, **không** có giây lẻ hoặc timezone | `NLS_DATE_FORMAT` |
| `TIMESTAMP` | Ngày giờ với giây lẻ, **không** lưu timezone | `NLS_TIMESTAMP_FORMAT` |
| `TIMESTAMP WITH TIME ZONE` | Thời gian kèm thông tin timezone/offset theo quy tắc kiểu dữ liệu | `NLS_TIMESTAMP_TZ_FORMAT` |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Giá trị được chuẩn hóa theo ngữ cảnh database và hiển thị theo timezone session; không lưu timezone gốc như TSTZ | Các định dạng timestamp phù hợp cùng cấu hình timezone phiên |

Xem format hiện hành:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT'
)
ORDER BY parameter;
~~~

Trong session thực hành:

~~~sql
ALTER SESSION SET NLS_TIMESTAMP_FORMAT =
    'YYYY-MM-DD HH24:MI:SS.FF3';

ALTER SESSION SET NLS_TIMESTAMP_TZ_FORMAT =
    'YYYY-MM-DD HH24:MI:SS.FF3 TZH:TZM';

SELECT TIMESTAMP '2026-11-14 09:30:15.123' AS local_timestamp,
       CURRENT_TIMESTAMP AS current_timestamp_with_zone
FROM dual;
~~~

Các `ALTER SESSION` này chỉ thay **mẫu trình bày/chuyển đổi mặc định** trong phiên, không thêm timezone vào cột `TIMESTAMP` vốn không có timezone. Khi định dạng trực tiếp, có thể dùng:

~~~sql
SELECT TO_CHAR(
           TIMESTAMP '2026-11-14 09:30:15.123',
           'YYYY-MM-DD HH24:MI:SS.FF3'
       ) AS stable_timestamp_text
FROM dual;
~~~

`FF3` biểu thị ba chữ số giây lẻ theo format model, khác với `SS` chỉ giây nguyên.

### 6.1 Múi giờ của session không phải NLS_DATE_FORMAT

~~~sql
SELECT SESSIONTIMEZONE,
       DBTIMEZONE,
       CURRENT_DATE,
       CURRENT_TIMESTAMP,
       SYSTIMESTAMP
FROM dual;
~~~

- `SESSIONTIMEZONE`: múi giờ của session.
- `DBTIMEZONE`: timezone được cấu hình cho database, không đại diện cho tất cả phiên.
- `CURRENT_DATE`: giá trị ngày giờ theo timezone session, trả về kiểu `DATE`.
- `CURRENT_TIMESTAMP`: thời điểm hiện tại theo timezone session, có timezone.
- `SYSTIMESTAMP`: timestamp lấy từ hệ điều hành máy database server, kèm thông tin timezone tương ứng.

Trong phiên thực hành, có thể thay múi giờ riêng:

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';

SELECT SESSIONTIMEZONE, CURRENT_TIMESTAMP
FROM dual;
~~~

**`TIME_ZONE` không phải `NLS_DATE_FORMAT`.** Đổi một mẫu ngày chỉ thay cách trình bày/parse chuỗi; đổi timezone phiên có thể tác động giá trị của các biểu thức thời gian phụ thuộc session và hiển thị kiểu có ngữ nghĩa timezone. Nếu hai máy lệch giờ, phải kiểm tra **kiểu cột, timezone session, timezone server và cách ứng dụng chuyển đổi**, không chỉ ba NLS view.

## 7. NLS_NUMERIC_CHARACTERS: một ví dụ khác về cùng giá trị, khác chuỗi

Tuy bài học tập trung ngày giờ, việc so sánh ba view sẽ dễ hiểu hơn nếu nhìn thêm tham số số. `NLS_NUMERIC_CHARACTERS` dùng hai ký tự: **ký tự phân cách thập phân trước**, **ký tự phân nhóm hàng nghìn sau**.

~~~sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';

SELECT TO_CHAR(1234.5, 'FM9G999D0') AS formatted_number
FROM dual;
~~~

Trong định dạng này, `D` là dấu thập phân và `G` là dấu nhóm theo NLS; kết quả dự kiến là `1,234.5`.

~~~sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';

SELECT TO_CHAR(1234.5, 'FM9G999D0') AS formatted_number
FROM dual;
~~~

Kết quả dự kiến là `1.234,5`. Số `1234.5` kiểu `NUMBER` **không hề đổi giá trị** giữa hai lần chạy; chuỗi hiển thị mới khác. Các lỗi chuyển chuỗi thành số như `ORA-01722` có thể liên quan việc dùng dấu phân cách không phù hợp với session hoặc dữ liệu nhập không hợp lệ.

Tương tự với ngày giờ, giải pháp bền vững là **gửi giá trị NUMBER dưới dạng NUMBER/bind**, và chỉ dùng `TO_CHAR` với format cụ thể khi cần tạo văn bản. Không ghép chuỗi số đã định dạng tại giao diện vào câu SQL như thể đó là literal số.

## 8. ALTER SESSION và tác động đến ba view

Trong một kết nối có quyền thực hiện `ALTER SESSION`, dùng:

~~~sql
-- Trước khi đổi
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_DATE_FORMAT', 'NLS_DATE_LANGUAGE')
ORDER BY parameter;

-- Đổi trong session hiện tại
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';
ALTER SESSION SET NLS_DATE_LANGUAGE = 'AMERICAN';

-- Quan sát lại
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_DATE_FORMAT', 'NLS_DATE_LANGUAGE')
ORDER BY parameter;
~~~

Sau đó thử xem `NLS_DATABASE_PARAMETERS` và `NLS_INSTANCE_PARAMETERS`. Việc thay đổi session **không biến thành thao tác sửa thuộc tính cấp database hoặc tham số instance**; dữ liệu khác ở hai view không phải lỗi đồng bộ.

| Hành động | Điều gì được tác động trực tiếp? | Có sửa dữ liệu DATE đang lưu không? |
|---|---|---|
| `ALTER SESSION SET NLS_DATE_FORMAT = ...` | Mặc định format của session hiện tại | Không |
| `ALTER SESSION SET NLS_DATE_LANGUAGE = ...` | Ngôn ngữ ngày tháng của session hiện tại | Không |
| Công cụ tạo connection mới với NLS khác | Giá trị NLS của session mới | Không |
| DBA thay cấu hình NLS ở cấp instance theo quy trình phù hợp | Cấu hình cấp instance và các phiên chịu ảnh hưởng theo cơ chế Oracle | Không tự viết lại các giá trị DATE trong bảng |
| Thay đổi database character set qua quy trình migration | Khả năng mã hóa/lưu dữ liệu ký tự của database | Đây là dự án chuyển đổi riêng, không phải cách đổi format DATE |

Nếu muốn quay về mặc định ban đầu của môi trường thực hành, cách đơn giản là **đóng session thử nghiệm và mở một session mới**, rồi kiểm tra lại `NLS_SESSION_PARAMETERS`. Không có lý do chạy `ALTER SYSTEM` hoặc thay đổi file cấu hình Oracle chỉ để thử định dạng một báo cáo.

### 8.1 NLS của session đang được dùng trong SQL nào?

Giả sử bạn mở hai cửa sổ công cụ, mỗi cửa sổ là một connection:

~~~text
Session A:
  NLS_DATE_FORMAT = DD/MM/YYYY
  SELECT DATE '2026-11-14' FROM DUAL;
  -> Có thể hiển thị 14/11/2026

Session B:
  NLS_DATE_FORMAT = YYYY-MM-DD
  SELECT DATE '2026-11-14' FROM DUAL;
  -> Có thể hiển thị 2026-11-14
~~~

Không có mâu thuẫn về dữ liệu. Hai session có định dạng mặc định khác nhau. Khi debug, phải chạy truy vấn `NLS_SESSION_PARAMETERS` **ngay trong connection gây lỗi**, thay vì chạy ở một cửa sổ SQL khác rồi cho rằng đã kiểm tra đúng trạng thái.

## 9. Công cụ kết nối có thể thay đổi kết quả bạn thấy

### 9.1 SQL*Plus và NLS_LANG

Trong đường kết nối **SQL*Plus dùng Oracle Client/OCI**, biến môi trường `NLS_LANG` là một yếu tố có thể ảnh hưởng ngôn ngữ/lãnh thổ và khai báo character set của client.

Ví dụ trên shell Linux/macOS sử dụng môi trường UTF-8 phù hợp:

~~~sh
export NLS_LANG=AMERICAN_AMERICA.AL32UTF8
sqlplus -L app_user@//db-host.example:1521/my_pdb_service
~~~

Trong PowerShell:

~~~powershell
$env:NLS_LANG = 'AMERICAN_AMERICA.AL32UTF8'
sqlplus -L app_user@//db-host.example:1521/my_pdb_service
~~~

Những ví dụ trên dùng host/user/service giả định, và SQL*Plus sẽ yêu cầu mật khẩu. `NLS_LANG` là thiết lập ở **phía client phù hợp với đường OCI**, không phải cách đổi `NLS_CHARACTERSET` của database. Phần character set phải phản ánh encoding mà client thực sự dùng; không sao chép máy móc từ database.

Sau khi đăng nhập, **vẫn phải truy vấn `NLS_SESSION_PARAMETERS`**, vì những giá trị như `NLS_DATE_FORMAT` có thể bị đặt lại tường minh. `NLS_LANG` cũng không phải một phép đo chắc chắn phông chữ hoặc encoding tệp đầu vào.

### 9.2 SQL Developer, SQLcl và ứng dụng JDBC Thin

SQL Developer, SQLcl và nhiều ứng dụng Java kết nối bằng JDBC Thin có cơ chế cấu hình client/session khác SQL*Plus qua OCI. Java `String` là dữ liệu Unicode; đặt `NLS_LANG` trong shell không phải cơ chế chính điều khiển character encoding của Java/JDBC Thin.

Các thiết lập có thể ảnh hưởng điều bạn thấy:

- Cài đặt hiển thị định dạng ngày/giờ của công cụ giao diện.
- SQL hoặc tùy chọn khởi tạo session khi connection được tạo.
- Lệnh `ALTER SESSION` do người dùng/script/application chạy.
- Kiểu dữ liệu thật của cột, cách driver bind/đọc giá trị, và cách ứng dụng serialize JSON.

Chẳng hạn SQL Developer có thể hiển thị `DATE` với format của giao diện mà không giống hoàn toàn cách một terminal SQL*Plus hiển thị. Vì vậy **không suy ra giá trị `NLS_DATE_FORMAT` của session chỉ bằng mắt nhìn một ô kết quả**; hãy hỏi trực tiếp `NLS_SESSION_PARAMETERS`.

### 9.3 JDBC: bind ngày giờ có kiểu thay vì dựa NLS

Giả sử ứng dụng Java cần tìm đơn hàng kể từ một mốc thời gian và dùng `PreparedStatement`:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.LocalDateTime;

LocalDateTime from = LocalDateTime.of(2026, 11, 14, 9, 30);

String sql = """
    SELECT order_id, created_at
    FROM orders
    WHERE created_at >= ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(1, Timestamp.valueOf(from));
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý giá trị qua API kiểu dữ liệu.
        }
    }
}
~~~

Đoạn mã giả định đã có `Connection connection` và bảng `ORDERS` trong đúng PDB/schema, với `CREATED_AT` là kiểu ngày giờ phù hợp. `Timestamp.valueOf(LocalDateTime)` tạo mốc thời gian kiểu timestamp **không gắn timezone**; nếu nghiệp vụ cần thời điểm tuyệt đối qua nhiều múi giờ, phải chọn kiểu cột và API timezone tương ứng. Mục đích ở đây là tránh tạo chuỗi `'14/11/2026 09:30'` rồi để Oracle tự đoán format.

### 9.4 Connection pool và trạng thái phiên còn sót lại

Giả sử request A mượn connection:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';
~~~

rồi trả connection về pool. Request B mượn lại chính connection đó, thực thi câu SQL dùng implicit conversion và nhận kết quả khác kỳ vọng. Nếu pool không khôi phục NLS session state, `ALTER SESSION` của request A có thể ảnh hưởng request B.

Một cách thiết kế bền vững là:

1. Giữ SQL độc lập với format mặc định bằng bind đúng kiểu và format model tường minh ở những nơi cần chuỗi.
2. Nếu ứng dụng buộc phải có một số NLS cố định, thiết lập chúng nhất quán khi khởi tạo/mượn connection theo cơ chế pool/driver đang dùng.
3. Không cho mỗi request thay đổi các mặc định chung rồi trả connection về pool mà không kiểm soát việc reset trạng thái.
4. Khi tái hiện lỗi, ghi lại session NLS **trên chính connection** đang thực thi truy vấn nghiệp vụ.

## 10. Trường hợp CDB/PDB: đọc đúng phạm vi

Trong Oracle multitenant, ứng dụng kết nối đến một **service của PDB**. Cùng một CDB có thể có nhiều PDB được tạo hoặc plug từ nguồn khác nhau. Khi đọc các NLS view, nên ghi rõ bối cảnh:

~~~sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV','CON_ID') AS con_id,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS service_name
FROM dual;

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_DATE_FORMAT', 'NLS_DATE_LANGUAGE')
ORDER BY parameter;
~~~

Với tài khoản có quyền:

~~~sql
SELECT name, cdb, open_mode
FROM v$database;
~~~

**Không đánh đồng CDB root với PDB ứng dụng.** Phạm vi các view, tham số có thể điều chỉnh ở PDB và hành vi của client tùy thuộc phiên bản/cấu hình Oracle. Nếu cần đối chiếu nhiều PDB, thực hiện quan sát trong **từng kết nối/PDB được phép**, ghi rõ nguồn, thay vì gộp kết quả rồi kết luận mọi PDB có chung ngữ nghĩa.

Một đặc điểm cần phân biệt:

- `NLS_CHARACTERSET` và `NLS_NCHAR_CHARACTERSET` mô tả cơ chế lưu ký tự ở cấp database/container phù hợp, **không phải định dạng hiển thị DATE của từng session**.
- `NLS_DATE_FORMAT` hoặc `NLS_DATE_LANGUAGE` có thể khác nhau giữa các session trong cùng PDB.
- `NLS_INSTANCE_PARAMETERS` phản ánh cấp instance; khi RAC có nhiều instance, cần biết instance nào đang phục vụ kết nối.

Vì vậy bảng so sánh ba view chỉ có ý nghĩa khi đã biết **chúng được truy vấn ở nơi nào**.

## 11. Những lỗi phổ biến khi diễn giải NLS

| Triệu chứng | Nguyên nhân có thể | Phép kiểm tra đầu tiên |
|---|---|---|
| Cùng `DATE`, SQL*Plus và GUI hiển thị khác nhau | NLS session khác, hoặc định dạng hiển thị riêng của client | Đọc `NLS_SESSION_PARAMETERS` trong từng connection; dùng `TO_CHAR` với format cố định |
| `ORA-01861: literal does not match format string` | Chuỗi ngày không khớp format khi parse | Xem biểu thức có implicit conversion không; dùng DATE literal, bind hoặc `TO_DATE` với format |
| `ORA-01843: not a valid month` | Dữ liệu tháng hoặc tên tháng không phù hợp ngôn ngữ/format | Kiểm tra `NLS_DATE_LANGUAGE`, `NLS_DATE_FORMAT` và chuỗi nguồn |
| Chạy được ở dev nhưng lỗi ở prod | Mặc định NLS session khác hoặc dữ liệu đầu vào khác | So sánh session NLS cùng câu SQL, bind và dữ liệu thực tế |
| `ORA-01722: invalid number` | Chuỗi số không thể chuyển thành NUMBER theo ngữ cảnh | Xem `NLS_NUMERIC_CHARACTERS`, loại dữ liệu và chuyển đổi tường minh |
| `SYSDATE` hiển thị không có giờ | `NLS_DATE_FORMAT` không chứa `HH24:MI:SS` | Dùng `TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS')` |
| `CURRENT_TIMESTAMP` lệch giờ mong đợi | Timezone session, server hoặc mapping cột/ứng dụng | Xem `SESSIONTIMEZONE`, `DBTIMEZONE` và kiểu dữ liệu, không chỉ NLS |
| `NLS_DATABASE_PARAMETERS` và `NLS_SESSION_PARAMETERS` khác nhau | Session được client hoặc `ALTER SESSION` thiết lập khác | Kiểm tra giá trị session, không xem sự khác nhau tự động là lỗi |
| Không truy vấn được một NLS view | Thiếu quyền xem metadata hoặc sai phạm vi đối tượng | Đọc lỗi Oracle đầy đủ, xác nhận quyền và PDB |
| Đổi `ALTER SESSION` rồi cửa sổ SQL khác không thay | Các cửa sổ có session khác nhau | Kiểm tra connection của mỗi cửa sổ và giá trị session riêng |

Một thông báo lỗi ngày giờ có thể phát sinh từ **chuỗi nguồn không hợp lệ**, kiểu cột, timezone hoặc API ứng dụng, không chỉ NLS. Cần điều tra câu SQL thực tế, giá trị bind và ngữ cảnh phiên thay vì sửa đại trà cấu hình database.

### Sơ đồ chẩn đoán khi ngày giờ hiển thị hoặc parse sai

~~~mermaid
flowchart TD
    A["Ngày giờ hiển thị/parse không như dự kiến"] --> B{"Giá trị cột là DATE/TIMESTAMP hay VARCHAR2?"}
    B -->|DATE/TIMESTAMP| C["Kiểm tra NLS_SESSION_PARAMETERS và format UI"]
    B -->|VARCHAR2| D["Kiểm tra dữ liệu chuỗi, format đầu vào"]
    C --> E{"Chỉ hiển thị khác?"}
    E -->|Có| F["Dùng TO_CHAR với format tường minh tại điểm xuất"]
    E -->|Không| G["Kiểm tra bind, timezone, điều kiện so sánh"]
    D --> H["Dùng TO_DATE/TO_TIMESTAMP có format hoặc sửa hợp đồng đầu vào"]
    G --> I["Thử trong cùng session gây lỗi"]
    F --> I
    H --> I
~~~

## 12. Bài thực hành: quan sát sự khác nhau giữa ba cấp

Thực hiện trên **hai session riêng** của database/PDB thực hành. Không cần đổi tham số hệ thống.

### Bước 1 — Ghi nhận cấu hình ban đầu

Ở **session A**, chạy:

~~~sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV','SERVICE_NAME') AS service_name
FROM dual;

SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_LANGUAGE', 'NLS_TERRITORY', 'NLS_DATE_FORMAT'
)
ORDER BY parameter;

SELECT parameter, value
FROM nls_instance_parameters
WHERE parameter IN (
    'NLS_LANGUAGE', 'NLS_TERRITORY', 'NLS_DATE_FORMAT'
)
ORDER BY parameter;

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_LANGUAGE', 'NLS_TERRITORY', 'NLS_DATE_FORMAT'
)
ORDER BY parameter;
~~~

Ghi kết quả thành ba cột theo từng view. Nếu khác nhau, mô tả đúng **phạm vi** của khác biệt; chưa cần xác định nguyên nhân lịch sử cụ thể khi không có audit.

### Bước 2 — Chỉ thay đổi session A

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';

SELECT DATE '2026-11-14' AS d,
       TO_CHAR(DATE '2026-11-14','DD/MM/YYYY') AS forced_format
FROM dual;

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_DATE_FORMAT';
~~~

Trong cùng session A, kiểm tra hai view database/instance một lần nữa và ghi lại nhận xét. Không cần `ALTER SYSTEM`.

### Bước 3 — Mở session B và so sánh

Mở **kết nối mới** tới cùng service/PDB (không chỉ một tab UI dùng chung connection nếu công cụ tái sử dụng session), sau đó:

~~~sql
SELECT SYS_CONTEXT('USERENV','CON_NAME') AS con_name
FROM dual;

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_DATE_FORMAT';

SELECT DATE '2026-11-14' AS d
FROM dual;
~~~

Session B có thể dùng giá trị mặc định khác session A đã chỉnh. Nếu B cũng có cùng định dạng, điều đó **không chứng minh** lệnh `ALTER SESSION` ở A đã tác động đến B; có thể B vốn được tạo với format đó. Phải đối chiếu bối cảnh và giá trị trước/sau.

### Bước 4 — Đổi ngôn ngữ tên tháng bằng format tường minh

~~~sql
SELECT TO_CHAR(
           DATE '2026-11-14',
           'FMMonth',
           'NLS_DATE_LANGUAGE=AMERICAN'
       ) AS english_month,
       TO_CHAR(
           DATE '2026-11-14',
           'FMMonth',
           'NLS_DATE_LANGUAGE=FRENCH'
       ) AS french_month
FROM dual;
~~~

Giải thích tại sao **một giá trị DATE** có thể tạo **hai chuỗi ngôn ngữ khác nhau**, và tại sao việc này không đòi hỏi sửa dữ liệu trong bảng.

### Bước 5 — Thử định dạng số theo session

~~~sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
SELECT TO_CHAR(1234.5, 'FM9G999D0') AS number_text FROM dual;

ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';
SELECT TO_CHAR(1234.5, 'FM9G999D0') AS number_text FROM dual;
~~~

Quan sát chuỗi xuất ra và nhắc lại rằng giá trị NUMBER không thay đổi.

### Bước 6 — Giải thích lựa chọn trong ứng dụng

Một API Java nhận ngày `14/11/2026 09:30` và lưu `CREATED_AT` kiểu `DATE`. Hãy trình bày:

1. Vì sao không nên ghép chuỗi vào `WHERE created_at >= '14/11/2026 09:30'`?
2. Nên bind tham số ngày giờ hoặc dùng format model tường minh thế nào?
3. Nếu chỉ muốn hiển thị kiểu `YYYY-MM-DD` cho frontend, nên dùng `TO_CHAR` hoặc tầng hiển thị ở đâu?
4. Nếu một request từng chạy `ALTER SESSION` trong connection pool, request sau có thể gặp điều gì?
5. Trong ba view, view nào cho biết format đang có hiệu lực của **connection thực thi request lỗi**?

## 13. Câu hỏi tự kiểm tra

1. `NLS_DATABASE_PARAMETERS` khác `NLS_INSTANCE_PARAMETERS` và `NLS_SESSION_PARAMETERS` ở phạm vi nào?
2. Vì sao không được coi khác biệt giữa database/instance/session là bằng chứng database lưu sai ngày?
3. Lệnh `ALTER SESSION SET NLS_DATE_FORMAT = ...` thay đổi dữ liệu cột `DATE` hay chỉ hành vi chuyển đổi/hiển thị của phiên?
4. Vì sao `DATE '2026-11-14'` đáng tin hơn một chuỗi ngày không có format tường minh?
5. `NLS_DATE_LANGUAGE` và `NLS_TERRITORY` có vai trò khác nhau như thế nào?
6. `NLS_TIMESTAMP_FORMAT`, `NLS_TIMESTAMP_TZ_FORMAT` và `SESSIONTIMEZONE` khác nhau ở điểm nào?
7. Khi hai JDBC connection dùng cùng database nhưng parse ngày khác nhau, phải kiểm tra gì trên **cả hai connection**?
8. Nếu `NLS_DATABASE_PARAMETERS` chứa `NLS_CHARACTERSET = AL32UTF8`, điều đó có kết luận được giá trị `NLS_DATE_FORMAT` của session không?
9. Vì sao mở thêm một tab SQL không đủ chứng minh có session mới?
10. Phép `TO_CHAR` có format tường minh giúp ích gì khi phát hành kết quả API/báo cáo?

## 14. Ghi nhớ

| Muốn biết... | Hãy hỏi... | Cần tránh kết luận... |
|---|---|---|
| Database đang ghi nhận cấu hình NLS gì? | `NLS_DATABASE_PARAMETERS` | Tất cả client đang dùng y hệt |
| Instance có thiết lập NLS gì? | `NLS_INSTANCE_PARAMETERS` | Mọi session hoặc mọi node RAC giống nhau |
| SQL trong kết nối hiện tại đang theo format nào? | `NLS_SESSION_PARAMETERS` | Đây là log lịch sử ai đổi tham số |
| Giá trị DATE/TIMESTAMP lưu gì? | Kiểu cột, giá trị và quy tắc Oracle | Định dạng màn hình chính là định dạng lưu trên đĩa |
| Muốn chuỗi ngày/số ổn định? | Bind đúng kiểu hoặc dùng `TO_CHAR`/`TO_DATE` có format | Dùng implicit conversion và hy vọng NLS đồng nhất |
| Nghi ngờ lệch múi giờ? | `SESSIONTIMEZONE`, `DBTIMEZONE`, kiểu timestamp, ứng dụng | Chỉ đổi `NLS_DATE_FORMAT` là đủ |

Trình tự phân tích nên là **xác định session và container → đọc cả ba nhóm tham số để hiểu bối cảnh → lấy `NLS_SESSION_PARAMETERS` làm điểm kiểm tra trực tiếp cho câu SQL → xác định loại dữ liệu và phép chuyển đổi → dùng format hoặc bind tường minh → thử lại trong đúng connection**. Khi làm như vậy, bạn phân biệt được vấn đề cấu hình ban đầu, trạng thái phiên, cách công cụ hiển thị và dữ liệu thực sự được Oracle lưu trữ.
