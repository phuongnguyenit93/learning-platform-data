# Bộ ký tự, mã hóa và tham số phiên khi kết nối từ công cụ

Khi làm việc với Oracle Database từ SQL*Plus, SQLcl, SQL Developer, DBeaver hoặc ứng dụng Java, một câu lệnh có thể chạy thành công nhưng lại hiển thị `Tiếng Việt` thành dấu hỏi hoặc ký tự lạ; ngày tháng xuất hiện theo định dạng bất ngờ; hoặc chuỗi `1,25` được hiểu khác với `1.25`. Những biểu hiện này liên quan đến **bộ ký tự và quá trình chuyển mã**, **thiết lập NLS của phiên kết nối**, và **cách công cụ hiển thị hoặc gửi giá trị**.

Bài này hướng dẫn cách phân biệt các lớp đó, tự quan sát cấu hình từ công cụ truy cập Oracle, thử dữ liệu Unicode và thiết lập tham số phiên có chủ đích. Những ví dụ thao tác dữ liệu chỉ nên thực hiện trong schema thực hành được cấp quyền.

## 1. Cần phân biệt bốn lớp khi một ký tự đi từ công cụ vào Oracle

~~~mermaid
flowchart LR
    A["Người dùng nhập 'Tiếng Việt'"] --> B["Editor / terminal / tệp SQL"]
    B --> C["Client: SQL*Plus, SQLcl, JDBC..."]
    C -->|"Oracle Net và chuyển đổi ký tự khi cần"| D["Oracle server / session"]
    D --> E["VARCHAR2/CLOB: database character set"]
    D --> F["NCHAR/NVARCHAR2/NCLOB: national character set"]
    D --> G["Session NLS: ngôn ngữ, số, ngày, sắp xếp..."]
~~~

| Lớp | Quyết định điều gì? | Ví dụ điển hình |
|---|---|---|
| **Encoding của tệp/terminal** | Các byte người dùng nhập hoặc công cụ đọc/hiển thị được giải mã thành ký tự như thế nào | Tệp `.sql` lưu UTF-8; terminal dùng UTF-8; phông chữ có hỗ trợ dấu tiếng Việt |
| **Character set của client/driver** | Cách client truyền hoặc chuyển đổi ký tự trước khi Oracle tiếp nhận và sau khi Oracle trả về | `NLS_LANG` ở client OCI/SQL*Plus; Java String Unicode trong JDBC Thin |
| **Character set của database** | Cách Oracle mã hóa ký tự trong loại cột dữ liệu tương ứng | `AL32UTF8` cho `VARCHAR2`/`CLOB`; `AL16UTF16` cho `NVARCHAR2` |
| **Thiết lập NLS của session** | Ngôn ngữ, định dạng ngày/số, quy tắc so sánh/sắp xếp và một số hành vi mặc định khi chạy SQL | `NLS_DATE_FORMAT`, `NLS_NUMERIC_CHARACTERS`, `NLS_DATE_LANGUAGE`, `NLS_SORT` |

**Character set** là tập ký tự cùng quy tắc biểu diễn bằng byte. **Encoding** là cách mã hóa ký tự thành byte theo quy tắc đó. Oracle đặt tên các bộ ký tự như `AL32UTF8` (UTF-8 chuẩn cho Unicode) hoặc `AL16UTF16` (UTF-16 big-endian cho national character data). **NLS** là viết tắt của *National Language Support*; nhiều tham số NLS điều khiển **cách trình bày và diễn giải giá trị**, chứ không làm thay đổi byte của các bản ghi đã lưu.

Một tình huống phổ biến: database đã dùng `AL32UTF8` nhưng terminal hoặc client đọc tệp bằng sai encoding. Khi đó bản thân database có thể hoàn toàn đúng mà chữ hiển thị bị lỗi; cũng có trường hợp chữ đã bị biến dạng **trước khi** Oracle nhận dữ liệu, nên database lưu chính chuỗi bị lỗi đó.

## 2. Bộ ký tự của Oracle: database character set và national character set

Oracle thường có hai khai báo bộ ký tự cần quan sát:

- **`NLS_CHARACTERSET`:** bộ ký tự chính của database, áp dụng cho dữ liệu ký tự trong `CHAR`, `VARCHAR2`, `CLOB` và nhiều cấu trúc ký tự thông thường.
- **`NLS_NCHAR_CHARACTERSET`:** bộ ký tự quốc gia, áp dụng cho `NCHAR`, `NVARCHAR2`, `NCLOB`. Các giá trị phổ biến gồm `AL16UTF16`; tùy phiên bản/cấu hình có thể gặp giá trị khác.

Từ phiên SQL kết nối đến **database/PDB cần khảo sát**, thực hiện:

~~~sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET')
ORDER BY parameter;
~~~

Kết quả **ví dụ**, không đại diện cho mọi Oracle:

~~~text
PARAMETER               VALUE
----------------------  --------
NLS_CHARACTERSET        AL32UTF8
NLS_NCHAR_CHARACTERSET  AL16UTF16
~~~

Với Oracle multitenant, hãy kiểm tra đúng **container đang kết nối**. Tùy phiên bản và cấu hình, root và PDB có thể có điều kiện/giới hạn khác nhau liên quan bộ ký tự; không lấy một truy vấn ở root để mặc nhiên thay cho quan sát của PDB ứng dụng. Có thể xác định container bằng:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
~~~

### 2.1 Chọn `VARCHAR2` hay `NVARCHAR2`?

Ví dụ tạo bảng trong schema thực hành:

~~~sql
CREATE TABLE nls_text_lab (
    id              NUMBER PRIMARY KEY,
    label_varchar   VARCHAR2(40 CHAR),
    label_nvarchar  NVARCHAR2(40)
);
~~~

`LABEL_VARCHAR` dùng database character set; `LABEL_NVARCHAR` dùng national character set. Trên database `AL32UTF8`, `VARCHAR2` đã hỗ trợ Unicode, bao gồm chữ tiếng Việt, nên **không cần mặc định chuyển mọi cột tiếng Việt sang `NVARCHAR2`**. Lựa chọn kiểu cột còn phụ thuộc kiến trúc dữ liệu, khả năng tương thích và chi phí chuyển đổi khi truy vấn.

Nếu database sử dụng bộ ký tự chính không thể biểu diễn một ký tự nào đó, việc chuyển đổi từ client có thể gây lỗi hoặc mất dữ liệu, tùy đường đi và cấu hình. Vì thế truy vấn `NLS_CHARACTERSET` là bước nền tảng khi xử lý lỗi Unicode; đổi mỗi định dạng hiển thị không tự bổ sung khả năng lưu Unicode cho một bộ ký tự cũ.

### 2.2 `BYTE` và `CHAR` trong khai báo độ dài

Với một bộ ký tự đa byte như `AL32UTF8`, **số ký tự** và **số byte** của một chuỗi có thể khác nhau:

~~~sql
CREATE TABLE nls_length_lab (
    code_byte VARCHAR2(10 BYTE),
    code_char VARCHAR2(10 CHAR)
);
~~~

- `VARCHAR2(10 BYTE)` đặt giới hạn **10 byte** theo database character set. Chuỗi gồm 10 ký tự Unicode không nhất thiết vừa.
- `VARCHAR2(10 CHAR)` đặt giới hạn **10 ký tự** (vẫn chịu giới hạn số byte tối đa của kiểu dữ liệu/thiết lập database).
- `NLS_LENGTH_SEMANTICS` có thể điều khiển cách hiểu mặc định khi khai báo `VARCHAR2(10)` mà không ghi `BYTE` hay `CHAR`. Nó **không thay đổi định nghĩa những cột đã tồn tại**.

Quan sát giá trị của session:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter = 'NLS_LENGTH_SEMANTICS';
~~~

Ở schema thực hành, nếu muốn khai báo rõ ràng, hãy ghi `BYTE` hoặc `CHAR` ngay trong DDL thay vì phụ thuộc mặc định môi trường. Không nên thay đổi character set của database bằng lệnh quản trị chỉ để xử lý một lỗi nhập tiếng Việt: đó là thay đổi kiến trúc có tác động lớn, cần quy trình chuyển đổi dữ liệu riêng.

## 3. Những tham số NLS nào tác động đến một phiên SQL?

Mỗi kết nối ứng dụng/công cụ tạo ra một **session**. Các tham số NLS của session có thể đến từ cấu hình database, thiết lập lúc client đăng nhập, công cụ và các lệnh `ALTER SESSION`. Hai phiên cùng một database **có thể hiển thị cùng giá trị khác nhau**.

### 3.1 Quan sát tham số đang có hiệu lực trong session

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
    'NLS_SORT',
    'NLS_COMP',
    'NLS_LENGTH_SEMANTICS'
)
ORDER BY parameter;
~~~

Một số tham số quan trọng:

| Tham số | Ý nghĩa thường gặp |
|---|---|
| `NLS_LANGUAGE` | Ngôn ngữ mặc định cho nhiều thông báo và cách trình bày theo ngôn ngữ |
| `NLS_TERRITORY` | Quy ước lãnh thổ, ảnh hưởng một số mặc định khi kết nối |
| `NLS_DATE_LANGUAGE` | Ngôn ngữ tên tháng/ngày và cách đọc các tên này trong định dạng ngày |
| `NLS_DATE_FORMAT` | Cách mặc định hiển thị/diễn giải `DATE` khi có chuyển đổi chuỗi ngầm định |
| `NLS_TIMESTAMP_FORMAT` | Định dạng mặc định cho `TIMESTAMP` không có timezone |
| `NLS_TIMESTAMP_TZ_FORMAT` | Định dạng mặc định cho `TIMESTAMP WITH TIME ZONE` |
| `NLS_NUMERIC_CHARACTERS` | Hai ký tự: ký tự thập phân trước, ký tự nhóm hàng nghìn sau |
| `NLS_SORT` | Quy tắc sắp xếp ngôn ngữ khi Oracle sử dụng cơ chế so sánh/sắp xếp NLS tương ứng |
| `NLS_COMP` | Xác định mức áp dụng so sánh ngôn ngữ đối với các phép so sánh SQL phù hợp |
| `NLS_LENGTH_SEMANTICS` | Ngữ nghĩa `BYTE`/`CHAR` mặc định cho một số khai báo kiểu ký tự mới |

Để đối chiếu tham số được lưu ở mức database:

~~~sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_DATE_FORMAT',
    'NLS_NUMERIC_CHARACTERS'
)
ORDER BY parameter;
~~~

**Lưu ý:** `NLS_DATABASE_PARAMETERS` và `NLS_SESSION_PARAMETERS` không phải cùng một nguồn dữ liệu. Giá trị lúc tạo database không nhất thiết là giá trị phiên đang dùng, và một số tham số phiên được xác định/ghi đè khi kết nối. Khi mô tả lỗi đang xảy ra trên công cụ nào, ưu tiên **giá trị session đó**.

### 3.2 Thay đổi tham số chỉ trong phiên hiện tại

Các lệnh sau thích hợp để thực hành trong một kết nối riêng:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';
ALTER SESSION SET NLS_DATE_LANGUAGE = 'AMERICAN';
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';

SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_NUMERIC_CHARACTERS'
)
ORDER BY parameter;
~~~

`ALTER SESSION` thay đổi hành vi **của kết nối hiện tại**; không chuyển mã các giá trị đã lưu và không sửa cấu hình toàn hệ thống. Khi thoát và mở session mới, giá trị có thể trở về mặc định hoặc bị công cụ/application thiết lập lại.

Nếu công cụ dùng **connection pool**, kết nối vật lý được tái sử dụng. Một thay đổi session do request trước thực hiện có thể ảnh hưởng request sau nếu pool không khôi phục/reset trạng thái. Trong ứng dụng, nên thiết lập nhất quán lúc lấy hoặc khởi tạo connection, sử dụng kiểu bind phù hợp và tránh phụ thuộc các mặc định không được kiểm soát.

## 4. `NLS_LANG` nằm ở đâu trong đường kết nối?

`NLS_LANG` là **biến môi trường của phía client** dùng bởi các công cụ/thư viện Oracle dựa trên **Oracle Call Interface (OCI)**, trong đó có nhiều cách chạy SQL*Plus. Nó thường có dạng:

~~~text
LANGUAGE_TERRITORY.CHARACTER_SET
AMERICAN_AMERICA.AL32UTF8
~~~

Ba phần có vai trò khác nhau:

1. `LANGUAGE`: ngôn ngữ mặc định mà client yêu cầu, ví dụ `AMERICAN`.
2. `TERRITORY`: quy ước lãnh thổ, ví dụ `AMERICA`.
3. `CHARACTER_SET`: khai báo bộ ký tự client dùng khi giao tiếp qua con đường OCI phù hợp.

Điều cần nhớ: **`NLS_LANG` không phải là lệnh đổi character set của Oracle Database.** Phần cuối của biến này cần phản ánh cách **client đang thực sự biểu diễn ký tự**, không phải tự động sao chép giá trị `NLS_CHARACTERSET` của server. Đặt sai có thể khiến Oracle chuyển mã sai hoặc khiến dữ liệu bị biến dạng khi nhập/xuất.

### 4.1 Ví dụ với shell Unicode trên Linux/macOS

Trong shell có locale/terminal thực sự hoạt động theo UTF-8, trước khi mở SQL*Plus:

~~~sh
locale
export NLS_LANG=AMERICAN_AMERICA.AL32UTF8
sqlplus -L app_user@//db-host.example:1521/my_pdb_service
~~~

Các giá trị `db-host.example` và `my_pdb_service` chỉ là chỗ trống cần thay; SQL*Plus sẽ hỏi mật khẩu. Việc terminal khai báo UTF-8, tệp SQL lưu UTF-8 và công cụ truyền dữ liệu theo encoding phù hợp đều cần thống nhất. Nếu file đã bị đọc sai từ trước, chỉ `export NLS_LANG` không khôi phục được ký tự đã mất.

Xem biến client trong shell:

~~~sh
printf '%s\n' "$NLS_LANG"
~~~

### 4.2 Ví dụ với Windows PowerShell

Trong PowerShell, đặt biến môi trường **cho tiến trình shell hiện tại và các tiến trình con** trước khi chạy SQL*Plus:

~~~powershell
$env:NLS_LANG = 'AMERICAN_AMERICA.AL32UTF8'
sqlplus -L app_user@//db-host.example:1521/my_pdb_service
~~~

Để quan sát:

~~~powershell
$env:NLS_LANG
~~~

Trên Windows, **console code page, encoding thực tế của ứng dụng, encoding file và phông chữ** là các yếu tố riêng. `chcp 65001` có thể thay đổi code page console, nhưng không đảm bảo mọi phiên bản SQL*Plus hay mọi đường đọc/ghi dữ liệu Unicode sẽ hoạt động đúng. Kiểm tra môi trường thực tế thay vì xem một biến hoặc một code page là bằng chứng duy nhất.

### 4.3 SQLcl, SQL Developer, DBeaver và JDBC Thin

Không được áp dụng công thức `NLS_LANG` cho mọi công cụ:

| Công cụ/đường kết nối | Cách suy nghĩ về ký tự |
|---|---|
| **SQL*Plus qua OCI** | `NLS_LANG` và encoding đầu vào/đầu ra của hệ điều hành có thể ảnh hưởng chuyển đổi ký tự |
| **SQLcl** | Công cụ dựa trên Java; kiểm tra cách công cụ/Java đọc file và mã hóa terminal cùng NLS của session, không mặc định xử lý byte như SQL*Plus OCI |
| **SQL Developer** | Công cụ Java/JDBC; quan tâm encoding của editor/export/import, cài đặt giao diện và NLS của connection |
| **DBeaver dùng JDBC Thin** | Java String/driver xử lý ký tự Unicode; kiểm tra driver, encoding import/export, cấu hình connection/session |
| **Ứng dụng Java JDBC Thin** | Tham số chuỗi Java được gửi qua driver rồi chuyển sang kiểu cột theo khả năng server; `NLS_LANG` của OCI không phải cách chính để điều khiển chuyển mã Java String |

Với **JDBC Thin**, đường chuyển đổi ký tự được driver và giao thức Oracle xử lý từ các giá trị Java Unicode; việc đặt `NLS_LANG=...AL32UTF8` trong shell không phải cách sửa lỗi gốc của một ứng dụng Java dùng JDBC Thin. Với **JDBC OCI** hoặc công cụ phụ thuộc OCI, quy tắc client NLS có thể khác. Luôn xác định **loại driver/connection** trước khi chọn tham số cần chỉnh.

Không nên suy từ chuỗi:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'LANGUAGE') AS current_language
FROM dual;
~~~

rằng terminal hoặc tệp SQL chắc chắn dùng encoding đó. Chuỗi này phản ánh ngữ cảnh ngôn ngữ/character set do Oracle cung cấp (phần character set của nó liên quan đến **database character set**), **không phải phép đo byte encoding của cửa sổ terminal**.

## 5. Một phép thử có thể phân biệt lỗi nhập, lỗi lưu và lỗi hiển thị

Phương pháp đáng tin cậy là kết hợp **giá trị nhìn thấy**, **độ dài ký tự/byte** và **biểu diễn byte**. Chỉ nhìn một chuỗi có dấu trên màn hình không đủ chứng minh rằng byte gốc được xử lý đúng.

### 5.1 Thử trong SQL mà không phụ thuộc dấu tiếng Việt gõ trực tiếp

Hàm Oracle `UNISTR` cho phép tạo chuỗi Unicode từ các mã escape ASCII. Ví dụ:

~~~sql
SELECT UNISTR('Ti\1EBFng Vi\1EC7t - H\00E0 N\1ED9i') AS vietnamese_text
FROM dual;
~~~

Kết quả mong muốn là **`Tiếng Việt - Hà Nội`**. Lệnh đầu vào chỉ dùng ký tự ASCII và escape `\hhhh`, giúp tách lỗi **đọc/nhập tệp SQL có dấu** khỏi lỗi **trả kết quả ra công cụ**. Nếu kết quả nhìn trên màn hình sai, chưa vội kết luận dữ liệu đã lưu sai: lúc này chỉ mới tạo giá trị trong biểu thức.

`UNISTR` tạo chuỗi Unicode thuộc họ national character data. Khi đưa giá trị vào cột `VARCHAR2`, Oracle sẽ chuyển đổi sang **database character set**; trên `AL32UTF8`, chuỗi tiếng Việt trong ví dụ được biểu diễn đầy đủ. Trên bộ ký tự khác, cần xem khả năng biểu diễn của bộ ký tự đó.

### 5.2 Lưu thử trong schema được phép

Nếu có quyền tạo bảng trong một schema **thực hành**, dùng bảng `NLS_TEXT_LAB` ở phần trước rồi chạy:

~~~sql
INSERT INTO nls_text_lab (id, label_varchar, label_nvarchar)
VALUES (
    1,
    UNISTR('Ti\1EBFng Vi\1EC7t - H\00E0 N\1ED9i'),
    UNISTR('Ti\1EBFng Vi\1EC7t - H\00E0 N\1ED9i')
);

COMMIT;

SELECT id, label_varchar, label_nvarchar
FROM nls_text_lab
WHERE id = 1;
~~~

`INSERT` có tác động ghi dữ liệu nên chỉ dùng ở schema mẫu. Để tránh nhầm khi chạy lại, chỉ chạy `INSERT` một lần cho `ID = 1`; nếu chạy lại cùng khóa chính, Oracle sẽ báo trùng khóa. Trong môi trường không được phép tạo bảng, có thể bỏ qua toàn bộ phần ghi và dùng biểu thức `UNISTR` để khảo sát cách công cụ trả ký tự.

### 5.3 Quan sát độ dài và byte của chuỗi được lưu

~~~sql
SELECT id,
       label_varchar,
       LENGTH(label_varchar) AS characters_count,
       LENGTHB(label_varchar) AS bytes_count,
       DUMP(label_varchar, 1016) AS database_bytes_hex
FROM nls_text_lab
WHERE id = 1;
~~~

Ý nghĩa:

- `LENGTH` đo độ dài theo ký tự của biểu thức.
- `LENGTHB` đo độ dài theo byte trong cách biểu diễn của giá trị Oracle đang xét; ở cột `VARCHAR2` trên `AL32UTF8`, nhiều ký tự có dấu chiếm hơn một byte.
- `DUMP(value, 1016)` hiển thị thông tin kiểu dữ liệu, độ dài và các byte theo hệ thập lục phân. Có thể dùng kết quả để đối chiếu dữ liệu thực sự đang nằm ở Oracle, thay vì chỉ tin vào chữ do công cụ vẽ ra.

Ví dụ ngắn, riêng biệt để so sánh:

~~~sql
SELECT LENGTH('A') AS ascii_chars,
       LENGTHB('A') AS ascii_bytes,
       LENGTH(UNISTR('\1ED9')) AS unicode_chars,
       DUMP(CAST(UNISTR('\1ED9') AS VARCHAR2(10 CHAR)), 1016)
           AS unicode_in_database_charset
FROM dual;
~~~

Với `AL32UTF8`, ký tự `ộ` (U+1ED9) được mã hóa bằng **ba byte UTF-8**. Không nên kỳ vọng mọi ký tự Unicode đều chiếm hai hoặc ba byte; UTF-8 sử dụng độ dài biến thiên, một số ký tự ngoài BMP cần bốn byte.

Để so sánh **một ký tự nhập trực tiếp** với phiên bản bằng `UNISTR`:

~~~sql
SELECT CASE
         WHEN 'Tiếng Việt' = UNISTR('Ti\1EBFng Vi\1EC7t')
         THEN 'MATCH'
         ELSE 'DIFFERENT'
       END AS typed_input_check
FROM dual;
~~~

Nếu tệp/script hoặc terminal truyền chuỗi `'Tiếng Việt'` đúng, kết quả sẽ là `MATCH`. Nếu là `DIFFERENT`, có thể có lỗi mã hóa đầu vào, hoặc hai chuỗi nhìn giống nhưng dùng các mã Unicode khác nhau.

**Unicode normalization:** cùng một chữ có dấu đôi khi được biểu diễn bằng ký tự dựng sẵn (composed) hoặc ký tự cơ sở cộng dấu kết hợp (decomposed). Chúng có thể hiển thị giống nhau nhưng byte và phép so sánh nhị phân khác nhau. Việc chuẩn hóa Unicode cần được xử lý có chủ đích ở nơi nhập/xử lý dữ liệu; không mặc định Oracle tự chuẩn hóa mọi chuỗi về cùng dạng.

## 6. Kiểm tra ảnh hưởng của NLS lên số và ngày

Nhiều vấn đề được gọi chung là “lỗi encoding” thực ra là **lỗi chuyển đổi kiểu dữ liệu do session NLS**.

### 6.1 Số thập phân và dấu phân nhóm

~~~sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';

SELECT TO_CHAR(1234.5, 'FM9G999D0') AS formatted_number
FROM dual;
~~~

Với giá trị `'.,'`: dấu thập phân là **chấm**, dấu phân nhóm là **phẩy**, nên kết quả theo format model là `1,234.5`. Đổi cho phiên thực hành:

~~~sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';

SELECT TO_CHAR(1234.5, 'FM9G999D0') AS formatted_number
FROM dual;
~~~

Lúc này kết quả tương ứng là `1.234,5`. Các ký hiệu định dạng `D` và `G` đi theo `NLS_NUMERIC_CHARACTERS`. **Giá trị NUMBER vẫn là cùng một giá trị**; chỉ chuỗi được định dạng thay đổi.

Tránh xây câu SQL bằng cách ghép chuỗi số từ dữ liệu giao diện:

~~~sql
-- Không nên phụ thuộc việc Oracle tự hiểu chuỗi theo phiên:
SELECT '12,50' AS text_input FROM dual;

-- Số trong SQL là literal số (không phải chuỗi nhập từ người dùng):
SELECT 12.50 AS numeric_value FROM dual;
~~~

`'12,50'` là chuỗi; chuyển chuỗi này sang `NUMBER` mà không chỉ rõ quy tắc có thể gây sai số hoặc lỗi `ORA-01722`. Trong Java, dùng `PreparedStatement.setBigDecimal(...)` hoặc bind số bằng kiểu tương ứng thay vì ghép `"12,50"` vào SQL.

### 6.2 Định dạng ngày và ngôn ngữ tên tháng

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY HH24:MI:SS';

SELECT SYSDATE AS shown_date
FROM dual;
~~~

`SYSDATE` là giá trị kiểu `DATE` của Oracle; công cụ có thể tự chuyển sang chuỗi theo `NLS_DATE_FORMAT` khi in ra. `DATE` của Oracle có cả **ngày và phần giờ/phút/giây**, dù một định dạng không hiển thị phần giờ. Nếu đổi:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';

SELECT SYSDATE AS shown_date
FROM dual;
~~~

phần giờ không hiện trên màn hình nhưng không bị xóa khỏi giá trị gốc.

Để kết quả nhất quán giữa các phiên, dùng định dạng tường minh:

~~~sql
SELECT TO_CHAR(
           DATE '2026-11-14',
           'YYYY-MM-DD'
       ) AS stable_date
FROM dual;
~~~

`DATE '2026-11-14'` là cú pháp date literal độc lập với `NLS_DATE_FORMAT`. Với chuỗi do người dùng nhập, nên dùng bind đúng kiểu ngày/giờ hoặc `TO_DATE(text, format_model)` / `TO_TIMESTAMP(text, format_model)` với format model cụ thể. Các lỗi `ORA-01843` (*not a valid month*) hay `ORA-01861` (*literal does not match format string*) thường là dấu hiệu chuyển đổi ngày/chuỗi không thống nhất.

Khi dùng tên tháng như `MON`, `MONTH`, cấu hình `NLS_DATE_LANGUAGE` cũng có thể thay đổi cách Oracle diễn giải/hiển thị. Nếu phải parse tên tháng bằng chuỗi, cần cố định ngôn ngữ thích hợp thay vì trông đợi cùng kết quả trong mọi session.

### 6.3 Múi giờ là một thuộc tính khác với mã hóa ký tự

~~~sql
SELECT SESSIONTIMEZONE,
       DBTIMEZONE,
       CURRENT_TIMESTAMP,
       SYSTIMESTAMP
FROM dual;
~~~

- `SESSIONTIMEZONE`: múi giờ của **session**.
- `DBTIMEZONE`: múi giờ cấu hình cho database; không đồng nghĩa với timezone của mọi session.
- `CURRENT_TIMESTAMP`: thời điểm hiện tại có thông tin múi giờ session.
- `SYSTIMESTAMP`: thời điểm từ hệ thống máy chủ database, có phần múi giờ/offset tương ứng.

Có thể đặt timezone phiên trong một kết nối thực hành:

~~~sql
ALTER SESSION SET TIME_ZONE = '+07:00';

SELECT SESSIONTIMEZONE, CURRENT_TIMESTAMP
FROM dual;
~~~

Thay đổi này không thay đổi character set hoặc tự động chuyển mọi `DATE` thành múi giờ mới. `DATE` và `TIMESTAMP` không có timezone, còn `TIMESTAMP WITH TIME ZONE` và `TIMESTAMP WITH LOCAL TIME ZONE` có quy tắc lưu/hiển thị khác nhau. Khi kiểm tra lệch giờ, hãy xem loại cột, timezone của session và cách driver gửi giá trị; đừng chẩn đoán nó như một lỗi UTF-8.

## 7. Sắp xếp và so sánh chuỗi không đồng nghĩa với lưu trữ UTF-8

Giả sử hai từ có chữ hoa/thường hoặc dấu:

~~~sql
SELECT label_varchar
FROM nls_text_lab
ORDER BY label_varchar;
~~~

Kết quả sắp xếp phụ thuộc quy tắc so sánh/collation áp dụng cho biểu thức và cấu hình database/session. **Unicode hoặc AL32UTF8 chỉ quy định khả năng biểu diễn ký tự, không bảo đảm thứ tự sắp xếp phù hợp tiếng Việt**.

Ở các môi trường hỗ trợ quy tắc NLS tương ứng, có thể quan sát tham số:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_SORT', 'NLS_COMP')
ORDER BY parameter;
~~~

`NLS_SORT` liên quan sắp xếp ngôn ngữ; `NLS_COMP` ảnh hưởng cách dùng so sánh ngôn ngữ trong một số biểu thức SQL. Từ Oracle 12.2 trở lên, cơ chế **data-bound collation** của cột/biểu thức cũng có thể tham gia quyết định cách so sánh. Vì vậy không nên giả định rằng chỉ cần đổi một tham số là mọi phép `ORDER BY`, `WHERE` và chỉ mục đều hoạt động giống nhau trong mọi phiên bản.

Việc thay đổi quy tắc so sánh có thể ảnh hưởng kết quả tìm kiếm, tính phân biệt hoa/thường và khả năng dùng index. Hãy kiểm tra định nghĩa cột và yêu cầu nghiệp vụ trước khi chọn cách so sánh, đặc biệt khi chuỗi được dùng làm khóa tìm kiếm hoặc trường cần tính duy nhất.

## 8. Các công cụ kết nối: thiết lập gì và không thiết lập gì?

### 8.1 SQL*Plus chạy script SQL

Một cách tổ chức bài thực hành:

~~~sh
sqlplus -L app_user@//db-host.example:1521/my_pdb_service
~~~

Sau khi kết nối, có thể chạy script:

~~~sql
-- Ở dấu nhắc SQL> của SQL*Plus:
@my_script.sql
~~~

Các lớp cần kiểm tra theo thứ tự: **file `my_script.sql` đã lưu đúng encoding**, client SQL*Plus đọc byte nào, `NLS_LANG`/môi trường OCI có phù hợp không, server đã chuyển đổi vào kiểu cột nào, và terminal có hiển thị Unicode được không. Nếu script chạy bằng `@` bị sai dấu nhưng `UNISTR` hiển thị đúng, ưu tiên kiểm tra **encoding của script hoặc bước client đọc script**.

SQL*Plus `SPOOL` xuất kết quả ra tệp. Encoding của tệp kết quả phụ thuộc đường xuất ký tự của client/môi trường và cấu hình tương ứng; nó **không mặc định chính là AL32UTF8 chỉ vì database đang dùng AL32UTF8**. Nếu cần trao đổi tệp CSV hoặc văn bản giữa công cụ, hãy xác định encoding thực tế của file xuất và file nhập.

### 8.2 SQL Developer và DBeaver

Trong công cụ giao diện đồ họa, các cài đặt cần phân biệt gồm:

- Encoding khi **mở/lưu SQL script** trong editor.
- Encoding khi **import/export CSV hoặc tệp văn bản**; UTF-8 thường là lựa chọn phù hợp cho tiếng Việt nếu cả hai đầu thống nhất.
- Kiểu driver (JDBC Thin hay cơ chế khác) và phiên bản driver.
- Câu lệnh cấu hình connection/session (nếu công cụ hỗ trợ), chẳng hạn `ALTER SESSION SET NLS_DATE_FORMAT = ...`.
- Font và rendering của bảng kết quả. Hiển thị ô vuông hoặc glyph thiếu có thể là lỗi phông chữ, không phải dữ liệu trong Oracle.

Để phân biệt vấn đề giao diện với dữ liệu, chạy **cùng một truy vấn `DUMP`** qua hai công cụ. Nếu byte trong Oracle giống nhau nhưng chữ vẽ khác nhau, nguyên nhân nghiêng về client/rendering. Nếu giá trị đã được lưu sai, cần truy vết encoding nhập ở điểm đầu và dữ liệu truyền qua driver.

### 8.3 Ứng dụng Java JDBC

Ví dụ kết nối bằng service name:

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//db-host.example:1521/my_pdb_service
spring.datasource.username=app_user
~~~

Địa chỉ, account trong ví dụ là placeholder. Mật khẩu nên đi qua cơ chế quản lý secret của môi trường, không đưa vào tài liệu hoặc log.

Khi ghi dữ liệu ký tự, sử dụng bind variable:

~~~java
String sql = "INSERT INTO nls_text_lab (id, label_varchar) VALUES (?, ?)";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 2L);
    statement.setString(2, "Tiếng Việt");
    statement.executeUpdate();
}
~~~

Đây là đoạn bên trong luồng đã có `Connection connection`, import JDBC và transaction phù hợp. Java `String` biểu diễn Unicode; driver chuyển giá trị theo giao thức/kiểu cột. `PreparedStatement` giúp phân biệt **giá trị** với **SQL text**, tránh ghép input thẳng vào câu lệnh và giảm phụ thuộc vào việc client diễn giải chuỗi literal. Nếu dữ liệu đã sai trong JSON/file ngay trước `setString`, JDBC không thể tự đoán để sửa.

Đối với số/ngày, ưu tiên bind bằng kiểu dữ liệu thích hợp (`setBigDecimal`, `setDate`, `setTimestamp` hoặc API thời gian tương ứng theo driver) để không phụ thuộc định dạng chuỗi theo NLS. Khi cần xuất văn bản cho người dùng, định dạng có chủ đích ở tầng giao diện/API.

## 9. Các triệu chứng thường gặp và cách khoanh vùng

| Triệu chứng | Khả năng liên quan | Phép kiểm tra đầu tiên |
|---|---|---|
| Dấu tiếng Việt biến thành `?` ngay khi nhập | Bước chuyển mã không biểu diễn được ký tự, hoặc file/client đã chuyển đổi mất dữ liệu | Đối chiếu chuỗi gõ trực tiếp với `UNISTR`; truy vấn `DUMP` giá trị sau khi lưu |
| Chữ thành chuỗi lạ như `Ã©` | Một bộ byte đã bị giải mã theo sai encoding ở một bước nào đó | Xem encoding file/terminal/client, kiểm tra raw byte trước và sau mỗi bước |
| SQL*Plus lỗi dấu nhưng SQL Developer hiển thị đúng | Hai client sử dụng đường giải mã/hiển thị khác nhau | Kiểm tra `NLS_LANG` của SQL*Plus, locale/console và encoding script |
| `ORA-12899` khi chèn chuỗi có dấu | Độ dài theo byte vượt giới hạn cột | Xem `VARCHAR2(... BYTE/CHAR)`, `LENGTHB` và định nghĩa cột |
| `ORA-12704` (*character set mismatch*) | Biểu thức dùng các họ character set không tương thích trong ngữ cảnh đó | Kiểm tra kiểu cột, literal, `CAST`/`CONVERT` được dùng |
| `ORA-12705` về NLS data files/environment | Cấu hình hoặc dữ liệu NLS tại client/server không hợp lệ/không truy cập được | Kiểm tra `NLS_LANG`, Oracle Home và môi trường chạy công cụ |
| `ORA-01722` với chuỗi số | Parse số bị lệch separator/format hoặc dữ liệu không phải số | So sánh `NLS_NUMERIC_CHARACTERS` và cách bind/`TO_NUMBER` |
| `ORA-01843` hoặc `ORA-01861` | Chuỗi ngày không khớp mẫu hoặc ngôn ngữ | Kiểm tra `NLS_DATE_FORMAT`/`NLS_DATE_LANGUAGE`; parse có format tường minh |
| Cùng dữ liệu ngày nhưng hai máy hiển thị khác | Session NLS hoặc cấu hình UI | Truy vấn `NLS_SESSION_PARAMETERS`; dùng `TO_CHAR` với format cụ thể |
| Ký tự hiển thị thành ô vuông, nhưng byte đúng | Font/rendering thiếu glyph | Đổi font hỗ trợ Unicode, so sánh kết quả `DUMP` |
| Tìm kiếm hoa/thường hoặc thứ tự tiếng Việt khác kỳ vọng | Collation/NLS sort/comparison | Xem `NLS_SORT`, `NLS_COMP` và collation của cột/biểu thức |

### 9.1 Phân biệt ba giai đoạn bị lỗi

~~~mermaid
flowchart TD
    A["Ký tự có dấu xuất hiện sai"] --> B["Dùng UNISTR để tạo cùng giá trị từ ASCII"]
    B --> C{"UNISTR hiển thị đúng?"}
    C -->|Có| D["Xem encoding file gốc/terminal lúc nhập chữ"]
    C -->|Không| E["Kiểm tra client nhận/trả ký tự và font hiển thị"]
    D --> F["Lưu vào bảng thực hành và xem DUMP/LENGTHB"]
    E --> F
    F --> G{"Byte Oracle đúng với giá trị mong đợi?"}
    G -->|Có| H["Khoanh vùng lỗi hiển thị/xuất file ở phía client"]
    G -->|Không| I["Khoanh vùng chuyển đổi lúc nhập, kiểu cột và character set"]
~~~

Với dữ liệu quan trọng, **đừng tiếp tục nhập đè hay sửa hàng loạt** chỉ dựa trên màn hình đang hiển thị lỗi. Chỉ định đúng giai đoạn xảy ra sai khác bằng truy vấn và mẫu test nhỏ trước khi chọn cách xử lý.

## 10. Bài thực hành có thứ tự

### Bước 1 — Xác định đúng database và container

Đăng nhập bằng công cụ được phép, sau đó:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       USER AS session_user
FROM dual;

SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_NCHAR_CHARACTERSET')
ORDER BY parameter;
~~~

Ghi lại tên PDB/container, schema và hai character set. Không nhầm `NLS_NCHAR_CHARACTERSET` với một biến có thể đổi bằng `ALTER SESSION`.

### Bước 2 — Ghi nhận các tham số của phiên

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_NUMERIC_CHARACTERS',
    'NLS_SORT',
    'NLS_COMP',
    'NLS_LENGTH_SEMANTICS'
)
ORDER BY parameter;
~~~

### Bước 3 — So sánh chuỗi có dấu và chuỗi Unicode escape

~~~sql
SELECT 'Tiếng Việt' AS typed_text,
       UNISTR('Ti\1EBFng Vi\1EC7t') AS escaped_text,
       CASE
           WHEN 'Tiếng Việt' = UNISTR('Ti\1EBFng Vi\1EC7t')
           THEN 'MATCH'
           ELSE 'DIFFERENT'
       END AS comparison_result
FROM dual;
~~~

Nếu `DIFFERENT`, quan sát encoding của file SQL hoặc đầu vào. Nếu chuỗi bằng nhau nhưng xuất hiện ô vuông trong bảng kết quả, xem khả năng rendering/font. Nếu cần kiểm tra giá trị đã lưu, thực hiện `DUMP(...,1016)` trên cột cụ thể.

### Bước 4 — Thử thay đổi định dạng **trong session**

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS';
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';

SELECT SYSDATE AS display_date,
       TO_CHAR(1234.5, 'FM9G999D0') AS display_number
FROM dual;
~~~

Đổi `NLS_NUMERIC_CHARACTERS` sang `',.'` trong cùng session và chạy lại `TO_CHAR` để thấy sự khác biệt. Mở một kết nối thứ hai và quan sát giá trị `NLS_SESSION_PARAMETERS` của kết nối mới; không giả định cả hai phiên tự đồng bộ.

### Bước 5 — So sánh qua hai công cụ

Chạy cùng lệnh `UNISTR`, `NLS_SESSION_PARAMETERS` và, nếu có bảng mẫu, `DUMP` bằng SQL*Plus và SQL Developer/SQLcl. Ghi rõ: loại client, cách kết nối, encoding file/script, giá trị NLS của **mỗi session** và byte trong Oracle. Mục tiêu là xác định biến số cụ thể, không chỉ ghi “máy A lỗi, máy B không lỗi”.

## 11. Những kết luận cần nhớ

1. **`NLS_CHARACTERSET` và `NLS_NCHAR_CHARACTERSET`** quy định bộ ký tự lưu dữ liệu tương ứng trong Oracle. Thay đổi `ALTER SESSION` không chuyển đổi những bộ ký tự này.
2. **`NLS_LANG`** thuộc đường client OCI/SQL*Plus phù hợp, có phần ngôn ngữ/lãnh thổ và khai báo character set client. `NLS_LANG` không phải phép đo mọi terminal và không phải cơ chế chính để mã hóa Java String của JDBC Thin.
3. **`NLS_SESSION_PARAMETERS`** mới phản ánh các thiết lập NLS đang có hiệu lực trong phiên đang chạy; cùng một database có thể có nhiều session mang giá trị khác nhau.
4. **Định dạng số, ngày, múi giờ và collation** là những khía cạnh khác với encoding của chuỗi. Một ngày hiển thị khác không có nghĩa byte Unicode bị lỗi.
5. **`UNISTR`, `LENGTH`, `LENGTHB`, `DUMP`** giúp xác định lỗi bắt đầu từ đầu vào, lưu trữ hay hiển thị. Kiểm tra trên mẫu nhỏ và đúng PDB trước khi thay đổi cấu hình.

Khi gặp hiện tượng “Oracle hiển thị sai tiếng Việt”, trình tự thực hành hợp lý là **xác minh encoding của nguồn → nhận diện client/driver → kiểm tra bộ ký tự database và loại cột → kiểm tra NLS session → đối chiếu dữ liệu bằng Unicode escape và byte dump → xác nhận cách hiển thị/export**. Làm rõ từng lớp giúp sửa đúng nguyên nhân mà không làm hỏng những dữ liệu vốn đã được lưu chính xác.
