# UPPER, LOWER, INITCAP và ảnh hưởng bộ ký tự trong Oracle Database

Khi xử lý dữ liệu văn bản trong **Oracle Database**, ứng dụng thường cần chuẩn hóa tên người dùng, mã sản phẩm, địa chỉ email hoặc hiển thị tên theo dạng dễ đọc. Ba hàm SQL cơ bản thường được dùng là **`UPPER`**, **`LOWER`** và **`INITCAP`**:

- `UPPER(char)`: chuyển các chữ cái trong chuỗi thành chữ hoa.
- `LOWER(char)`: chuyển các chữ cái trong chuỗi thành chữ thường.
- `INITCAP(char)`: viết hoa chữ cái đầu mỗi từ, chuyển các chữ cái còn lại trong từ thành chữ thường.

Những hàm này nhìn đơn giản, nhưng kết quả có thể phụ thuộc **bộ ký tự**, **quy tắc chuyển chữ theo ngôn ngữ**, **collation/NLS settings** và cách dữ liệu được lưu trong `CHAR`, `VARCHAR2`, `NCHAR` hoặc `NVARCHAR2`. Đặc biệt, `UPPER` không đồng nghĩa với so sánh không phân biệt hoa thường; `INITCAP` cũng không phải công cụ hiểu tên riêng hay quy tắc viết hoa tự nhiên của mọi ngôn ngữ.

Bài học giải thích hành vi của từng hàm, phân biệt phép chuyển chữ theo ánh xạ ký tự với phép chuyển chữ theo quy tắc ngôn ngữ, cách kiểm tra cấu hình NLS và bộ ký tự, cách xây dựng truy vấn/index cho tìm kiếm không phân biệt hoa thường, cùng các lưu ý khi tích hợp Java/JDBC.

## 1. Phân biệt chuyển đổi chữ hoa/thường và so sánh chuỗi

Trước khi học từng hàm, cần tách ba thao tác:

1. **Chuyển đổi cách viết:** biến một chuỗi thành chữ hoa, chữ thường hoặc dạng viết hoa đầu từ. Đây là nhiệm vụ của `UPPER`, `LOWER`, `INITCAP` và các hàm NLS tương ứng.
2. **So sánh chuỗi:** xác định hai giá trị có bằng nhau, khác nhau hoặc xếp trước/sau nhau theo quy tắc nào. Việc này phụ thuộc collation, kiểu dữ liệu và các thiết lập so sánh.
3. **Chuẩn hóa dữ liệu:** áp dụng quy tắc nghiệp vụ ổn định trước khi lưu hoặc tìm kiếm, ví dụ trim khoảng trắng, chuẩn hóa mã định danh, xử lý Unicode và quyết định cách so sánh dấu/hoa thường.

Ví dụ:

```sql
SELECT UPPER('Oracle Database') AS upper_text,
       LOWER('Oracle Database') AS lower_text,
       INITCAP('ORACLE DATABASE') AS title_text
FROM dual;
```

Kết quả minh họa:

| `UPPER_TEXT` | `LOWER_TEXT` | `TITLE_TEXT` |
|---|---|---|
| ORACLE DATABASE | oracle database | Oracle Database |

`UPPER` trả về một biểu thức văn bản đã chuyển chữ hoa. Nó **không thay đổi dữ liệu gốc trong bảng** nếu chỉ được gọi trong `SELECT`. Muốn lưu kết quả đã chuẩn hóa, cần thực hiện `UPDATE` hoặc thiết kế cột chuẩn hóa riêng, có xét đến tác động dữ liệu và index.

```text
Giá trị gốc trong bảng
        |
        +---- SELECT UPPER(column) ----> Giá trị hiển thị/chuyển đổi
        |
        +---- UPDATE column = UPPER(column) ----> Thay đổi dữ liệu lưu
        |
        +---- Function-based index trên UPPER(column)
                                      ----> Hỗ trợ tìm kiếm/unique
```

Một ứng dụng có thể dùng `UPPER(username) = UPPER(:username)` để tìm kiếm không phân biệt hoa thường trong một phạm vi quy tắc nhất định, nhưng không nên giả định mọi ngôn ngữ đều có phép chuyển chữ đơn giản giống tiếng Anh.

## 2. Hàm UPPER: chuyển chữ thành chữ hoa

`UPPER(char)` trả về chuỗi trong đó các chữ cái được chuyển sang dạng chữ hoa theo ánh xạ ký tự mà Oracle sử dụng cho hàm này. Ký tự không có dạng hoa tương ứng, chữ số, khoảng trắng và dấu câu thường được giữ nguyên.

```sql
SELECT UPPER('oracle database 23ai') AS result
FROM dual;
```

Kết quả:

```text
ORACLE DATABASE 23AI
```

### 2.1. Dùng UPPER trong SELECT

```sql
SELECT customer_id,
       customer_name,
       UPPER(customer_name) AS customer_name_upper
FROM customers;
```

Truy vấn trả cả tên ban đầu và phiên bản chữ hoa. Nó phù hợp với báo cáo, xuất dữ liệu hoặc tạo nhãn tìm kiếm tạm thời. `UPPER` ở đây không cập nhật cột `CUSTOMER_NAME`.

### 2.2. Dùng UPPER trong điều kiện WHERE

Giả sử bảng `LAB_CASE_NAMES` có username được lưu với nhiều kiểu chữ. Để tìm `lan` bất kể người dùng nhập hoa hay thường:

```sql
SELECT user_id, username
FROM lab_case_names
WHERE UPPER(username) = UPPER('Lan');
```

Nếu dữ liệu có `lan`, `LAN`, `Lan`, phép so sánh sau chuyển hai vế thành cùng dạng chữ hoa theo quy tắc `UPPER` đang áp dụng. Đây là một cách phổ biến để tìm kiếm không phân biệt hoa thường trong những trường hợp quy tắc chữ phù hợp.

Với bind parameter trong ứng dụng:

```sql
SELECT user_id, username
FROM lab_case_names
WHERE UPPER(username) = UPPER(:p_username);
```

Giá trị `:p_username` nên được bind đúng kiểu ký tự từ driver. Không nối trực tiếp dữ liệu người dùng vào SQL.

### 2.3. UPPER không tự loại bỏ dấu

`UPPER` là phép chuyển chữ hoa, không phải phép bỏ dấu. Ví dụ chuỗi có ký tự `á` có thể được chuyển thành `Á`, nhưng dấu sắc vẫn còn. Nếu nghiệp vụ muốn tìm kiếm **không phân biệt dấu**, cần xem collation phù hợp hoặc một biểu thức chuẩn hóa riêng; không coi `UPPER` là `TRANSLATE` loại bỏ dấu.

### 2.4. UPPER và NULL

Nếu đối số là `NULL`, kết quả của `UPPER` cũng là `NULL`:

```sql
SELECT UPPER(NULL) AS result
FROM dual;
```

Kết quả là `NULL`. Vì vậy:

```sql
WHERE UPPER(customer_name) = 'LAN'
```

không chọn hàng có `CUSTOMER_NAME IS NULL`; biểu thức so sánh là `UNKNOWN`. Nếu nghiệp vụ cần xử lý giá trị thiếu, phải bổ sung điều kiện `IS NULL` riêng.

## 3. Hàm LOWER: chuyển chữ thành chữ thường

`LOWER(char)` chuyển các chữ cái trong chuỗi thành chữ thường. Ký tự số, khoảng trắng và dấu câu không phải chữ cái thường được giữ nguyên.

```sql
SELECT LOWER('ORACLE DATABASE 23AI') AS result
FROM dual;
```

Kết quả:

```text
oracle database 23ai
```

### 3.1. Chuẩn hóa khi lưu hoặc hiển thị

Có thể dùng `LOWER` trong truy vấn:

```sql
SELECT email,
       LOWER(email) AS email_normalized
FROM customers;
```

Hoặc trong một phép cập nhật dữ liệu:

```sql
-- Chỉ là ví dụ migration; phải đánh giá dữ liệu và tác động trước khi chạy.
UPDATE lab_case_names
SET username = LOWER(username);
```

`UPDATE` thay đổi dữ liệu đã lưu. Trước khi chuẩn hóa hàng loạt, phải kiểm tra xem các giá trị khác nhau trước đó có trở thành trùng sau chuyển đổi hay không. Ví dụ `Lan` và `LAN` có thể trở thành cùng `lan`; nếu có unique constraint trên cột gốc, thao tác cập nhật có thể bị từ chối hoặc gây lỗi ở một số hàng. Không chạy cập nhật chuẩn hóa trên production mà chưa có kế hoạch phát hiện duplicate, backup/rollback và kiểm thử ứng dụng.

### 3.2. LOWER cũng không loại bỏ dấu

Ví dụ chuỗi `ĐẶNG` khi chuyển chữ thường sẽ giữ ký tự có dấu theo ánh xạ tương ứng; kết quả không phải `dang`. Tìm kiếm không dấu cần một quy tắc riêng. Việc chuyển chữ và việc loại bỏ dấu là hai phép biến đổi độc lập.

### 3.3. LOWER và NULL

`LOWER(NULL)` trả `NULL`. Điều kiện `LOWER(column) = 'abc'` không chọn hàng có `column IS NULL`. Không dùng `NVL(column, '')` như một cách mặc định để biến dữ liệu thiếu thành chuỗi rỗng mà chưa xác định nghiệp vụ, vì Oracle xử lý chuỗi rỗng trong các kiểu ký tự như `NULL` trong nhiều ngữ cảnh SQL.

## 4. Hàm INITCAP: viết hoa chữ cái đầu mỗi từ

`INITCAP(char)` tạo chuỗi theo quy tắc:

- Chữ cái đầu của mỗi từ được chuyển thành chữ hoa.
- Những chữ cái còn lại trong từ được chuyển thành chữ thường.
- Ranh giới từ thường được xác định bởi khoảng trắng hoặc ký tự không phải chữ/số.

Ví dụ:

```sql
SELECT INITCAP('oracle database') AS result
FROM dual;
```

Kết quả:

```text
Oracle Database
```

### 4.1. Ví dụ với tên và cụm từ

```sql
SELECT INITCAP('NGUYEN VAN AN') AS full_name,
       INITCAP('customer service center') AS department_name,
       INITCAP('oracle-sql tutorial') AS title_text
FROM dual;
```

Kết quả minh họa theo ranh giới từ:

| Biểu thức | Kết quả |
|---|---|
| `INITCAP('NGUYEN VAN AN')` | `Nguyen Van An` |
| `INITCAP('customer service center')` | `Customer Service Center` |
| `INITCAP('oracle-sql tutorial')` | `Oracle-Sql Tutorial` |

Với dấu gạch nối hoặc dấu câu, việc xác định ranh giới từ có thể tạo ra kết quả không giống quy ước biên tập tên riêng mà tổ chức mong muốn. Hãy thử trên dữ liệu thực tế.

### 4.2. INITCAP không hiểu acronym và tên thương hiệu

`INITCAP` chỉ áp dụng quy tắc hình thức cho từng từ; nó không biết từ nào là tên riêng, chữ viết tắt hay thương hiệu:

```sql
SELECT INITCAP('API AND SQL FOR ORACLE') AS result
FROM dual;
```

Kết quả có thể là `Api And Sql For Oracle`, trong khi tài liệu kỹ thuật thường muốn `API and SQL for Oracle`. Tương tự, `iPhone`, `eBay`, tên người, tên địa danh và các từ viết tắt có quy tắc riêng không nên được định dạng tự động bằng `INITCAP` nếu yêu cầu giữ đúng kiểu chữ.

Nếu nghiệp vụ yêu cầu quy tắc trình bày cụ thể, hãy dùng một lớp định dạng ở ứng dụng, từ điển tên riêng hoặc quy tắc được định nghĩa rõ thay vì coi `INITCAP` là thuật toán viết hoa ngôn ngữ tự nhiên.

### 4.3. INITCAP và NULL

`INITCAP(NULL)` trả `NULL`. Các hàm chuyển chữ không tự thay thế giá trị thiếu bằng chuỗi khác. Nếu cần hiển thị nhãn thay thế, có thể dùng `COALESCE`/`NVL` theo quy tắc nghiệp vụ:

```sql
SELECT INITCAP(COALESCE(customer_name, 'unknown')) AS display_name
FROM customers;
```

Ở đây `UNKNOWN` được hiển thị thành `Unknown`; điều này là **quyết định trình bày**, không có nghĩa dữ liệu gốc đã được cập nhật.

## 5. So sánh nhanh UPPER, LOWER và INITCAP

| Hàm | Kết quả mong muốn | Ví dụ đầu vào | Kết quả ví dụ | Ứng dụng thường gặp |
|---|---|---|---|---|
| `UPPER` | Chữ hoa | `'Oracle Database'` | `ORACLE DATABASE` | Chuẩn hóa khóa tìm kiếm hoặc mã chữ |
| `LOWER` | Chữ thường | `'ORACLE Database'` | `oracle database` | Chuẩn hóa email/username theo chính sách |
| `INITCAP` | Viết hoa đầu từ, còn lại chữ thường | `'ORACLE DATABASE'` | `Oracle Database` | Hiển thị tiêu đề hoặc tên theo quy tắc đơn giản |

| Đặc điểm | `UPPER` | `LOWER` | `INITCAP` |
|---|---|---|---|
| Thay đổi hoa/thường | Tất cả chữ cái thành hoa | Tất cả chữ cái thành thường | Đầu mỗi từ hoa, phần còn lại thường |
| Giữ số và dấu câu | Thông thường giữ nguyên | Thông thường giữ nguyên | Giữ nguyên, nhưng có thể ảnh hưởng ranh giới từ |
| Tự loại bỏ dấu | Không | Không | Không |
| Tự chuẩn hóa Unicode NFC/NFD | Không | Không | Không |
| Tự sửa tên riêng/acronym | Không | Không | Không |
| Đối số `NULL` | Kết quả `NULL` | Kết quả `NULL` | Kết quả `NULL` |

## 6. Ảnh hưởng của bộ ký tự Oracle

Oracle lưu dữ liệu ký tự theo **character set**. Khi xử lý chữ hoa/thường, bộ ký tự và cách biểu diễn ký tự quyết định những ký tự nào có thể lưu được và ánh xạ nhị phân mặc định nào được áp dụng.

Hai khái niệm cần phân biệt:

- **Database character set**: bộ ký tự dùng cho `CHAR`, `VARCHAR2`, `CLOB` và nhiều dữ liệu ký tự thông thường.
- **National character set**: bộ ký tự dùng cho `NCHAR`, `NVARCHAR2`, `NCLOB`.

Trong nhiều triển khai Oracle hiện đại, database character set thường là **`AL32UTF8`** để hỗ trợ Unicode; national character set thường là **`AL16UTF16`**. Đây là các cấu hình phổ biến, không phải giả định đúng cho mọi database cũ.

### 6.1. Kiểm tra bộ ký tự của database

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;
```

Kết quả có thể cho thấy:

| Parameter | Ví dụ giá trị | Phạm vi |
|---|---|---|
| `NLS_CHARACTERSET` | `AL32UTF8` | Dữ liệu kiểu `CHAR`, `VARCHAR2`, `CLOB` |
| `NLS_NCHAR_CHARACTERSET` | `AL16UTF16` | Dữ liệu kiểu `NCHAR`, `NVARCHAR2`, `NCLOB` |

Nếu account không có quyền truy vấn view, hãy yêu cầu DBA cung cấp thông tin cấu hình; không cấp quyền quản trị rộng chỉ để đọc hai tham số.

### 6.2. CHAR/VARCHAR2 và NCHAR/NVARCHAR2

```sql
CREATE TABLE lab_character_types (
    id             NUMBER PRIMARY KEY,
    normal_text    VARCHAR2(100 CHAR),
    national_text  NVARCHAR2(100)
);
```

- `NORMAL_TEXT` dùng database character set.
- `NATIONAL_TEXT` dùng national character set.
- `VARCHAR2(100 CHAR)` chỉ định độ dài theo **character semantics** thay vì byte semantics.
- `NVARCHAR2(100)` có giới hạn theo ngữ nghĩa của national character set; không nên quy đổi số 100 thành số byte cố định nếu chưa xem cấu hình.

Việc gọi `UPPER`, `LOWER` hoặc `INITCAP` trên cột ký tự không tự biến `VARCHAR2` thành `NVARCHAR2`, cũng không phải một phép chuyển đổi bộ ký tự được thiết kế để sửa dữ liệu sai encoding. Hàm chuyển chữ hoạt động trên giá trị ký tự mà Oracle nhận được và trả kết quả theo quy tắc kiểu/character set áp dụng cho đối số.

### 6.3. BYTE semantics và CHAR semantics

Một ký tự Unicode có thể chiếm nhiều byte trong `AL32UTF8`. Vì vậy:

- `VARCHAR2(30 BYTE)` giới hạn theo số byte.
- `VARCHAR2(30 CHAR)` giới hạn theo số ký tự theo ngữ nghĩa của Oracle.
- Một chuỗi có 30 ký tự không nhất thiết chỉ chiếm 30 byte.

Kiểm tra độ dài:

```sql
SELECT customer_name,
       LENGTH(customer_name)  AS char_length,
       LENGTHB(customer_name) AS byte_length
FROM customers;
```

`LENGTH` đếm độ dài theo ký tự của kiểu dữ liệu, còn `LENGTHB` đếm byte. Với dữ liệu Unicode, hai giá trị có thể khác nhau. Việc chuyển chữ hoa/thường có thể ảnh hưởng biểu diễn ký tự theo quy tắc ánh xạ; do đó không nên giả định kết quả luôn có cùng số byte như đầu vào. Nếu cần đánh giá giới hạn cột hoặc kích thước index, hãy đo dữ liệu thực tế bằng các hàm độ dài thích hợp.

### 6.4. Bộ ký tự không thể sửa lỗi encoding đã xảy ra

Nếu client gửi dữ liệu bằng encoding không tương thích hoặc chuỗi đã bị biến dạng trước khi tới database, gọi `UPPER` không thể khôi phục nội dung ban đầu. Ví dụ, một tên tiếng Việt bị chuyển thành các ký tự rác do cấu hình client sai thì `UPPER` chỉ chuyển chữ trên chuỗi rác mà Oracle đang nhận được.

Khi điều tra dữ liệu tiếng Việt hoặc Unicode, hãy kiểm tra:

1. `NLS_CHARACTERSET` và `NLS_NCHAR_CHARACTERSET` của database.
2. Encoding của nguồn nhập dữ liệu (file CSV, API, message queue, ETL).
3. Driver/client có gửi chuỗi Unicode đúng hay không.
4. Dữ liệu có bị chuyển đổi nhiều lần hoặc mất ký tự trước khi insert không.
5. Kết quả hiển thị của SQL client có dùng font/encoding phù hợp không.

Không đổi database character set chỉ để sửa một cột bị lỗi encoding. Thay đổi character set là công việc quản trị có phạm vi lớn, cần đánh giá toàn bộ dữ liệu, ứng dụng và quy trình chuyển đổi.

## 7. UPPER/LOWER và quy tắc ngôn ngữ: NLS_UPPER, NLS_LOWER

`UPPER` và `LOWER` dùng ánh xạ chữ hoa/thường theo cách ánh xạ ký tự mà Oracle áp dụng cho bộ ký tự. Trong khi đó, **`NLS_UPPER`** và **`NLS_LOWER`** hỗ trợ chuyển chữ theo quy tắc ngôn ngữ (linguistic mapping), có thể chỉ định thông số NLS.

Cú pháp tổng quát:

```sql
NLS_UPPER(char [, 'nlsparam'])
NLS_LOWER(char [, 'nlsparam'])
```

Trong đó `nlsparam` có thể chỉ định quy tắc sort/ngôn ngữ thích hợp, ví dụ dạng:

```text
NLS_SORT = XTurkish
```

Nếu không truyền `nlsparam`, hàm sử dụng thiết lập NLS sort mặc định của session theo quy tắc Oracle. Để kết quả nhất quán giữa các session và ứng dụng, nên cân nhắc truyền tham số tường minh khi nghiệp vụ yêu cầu quy tắc ngôn ngữ cụ thể.

### 7.1. Ví dụ NLS_UPPER và NLS_LOWER

```sql
SELECT UPPER('istanbul') AS binary_upper,
       NLS_UPPER('istanbul', 'NLS_SORT = XTurkish') AS turkish_upper
FROM dual;
```

Trong quy tắc tiếng Thổ Nhĩ Kỳ, chữ `i` thường có dạng chữ hoa có dấu chấm `İ`; chữ `ı` (i không chấm) có dạng chữ hoa `I`. Vì thế quy tắc ngôn ngữ có thể tạo ra kết quả khác ánh xạ chữ hoa nhị phân thông thường. Tên sort hợp lệ và kết quả chính xác cần được xác nhận trên phiên bản/cấu hình Oracle đang dùng.

Ví dụ với chữ thường:

```sql
SELECT NLS_LOWER('ISTANBUL', 'NLS_SORT = XTurkish') AS turkish_lower
FROM dual;
```

Ví dụ trên minh họa vì sao một phép chuyển chữ phù hợp với tiếng Anh có thể không đủ cho mọi ngôn ngữ. Với dữ liệu đa ngôn ngữ, phải chọn quy tắc dựa trên yêu cầu nghiệp vụ và kiểm thử bằng các trường hợp biên.

### 7.2. INITCAP và NLS_INITCAP

Oracle còn cung cấp **`NLS_INITCAP`** để viết hoa đầu từ theo quy tắc ngôn ngữ được chỉ định:

```sql
NLS_INITCAP(char [, 'nlsparam'])
```

Ví dụ:

```sql
SELECT INITCAP('istanbul') AS default_title,
       NLS_INITCAP('istanbul', 'NLS_SORT = XTurkish') AS turkish_title
FROM dual;
```

Không nên dùng `INITCAP` hoặc `NLS_INITCAP` như một bộ định dạng tên người hoàn chỉnh. Tên riêng có thể có chữ hoa giữa từ, tiền tố, hậu tố, chữ viết tắt hoặc quy tắc văn hóa đặc thù.

### 7.3. Chọn hàm nào?

| Nhu cầu | Hàm phù hợp để bắt đầu | Lưu ý |
|---|---|---|
| Chuẩn hóa mã ASCII đơn giản thành hoa | `UPPER` | Không phải phép bỏ dấu |
| Chuẩn hóa chuỗi thành thường | `LOWER` | Cần xác định quy tắc cho ngôn ngữ đặc biệt |
| Hiển thị tiêu đề đơn giản | `INITCAP` | Không hiểu acronym và tên riêng |
| Chuyển chữ theo quy tắc ngôn ngữ | `NLS_UPPER`, `NLS_LOWER` | Chọn `nlsparam` phù hợp và nhất quán |
| Viết hoa đầu từ theo quy tắc ngôn ngữ | `NLS_INITCAP` | Vẫn không thay thế quy tắc biên tập tên riêng |
| So sánh không phân biệt hoa thường | Collation phù hợp hoặc chuẩn hóa hai vế | Chuyển chữ và so sánh là hai thao tác khác nhau |
| So sánh không phân biệt dấu | Collation accent-insensitive hoặc khóa chuẩn hóa riêng | Không chỉ dùng `UPPER`/`LOWER` |

## 8. NLS settings ảnh hưởng đến kết quả ra sao?

Oracle sử dụng nhiều tham số NLS để xác định ngôn ngữ, vùng, thứ tự sắp xếp và so sánh ký tự. Một số tham số thường gặp:

| Tham số | Ý nghĩa khái quát |
|---|---|
| `NLS_LANGUAGE` | Ngôn ngữ cho thông báo và một số quy tắc ngôn ngữ mặc định |
| `NLS_TERRITORY` | Quy tắc theo vùng, ví dụ định dạng ngày/số và quy ước vùng |
| `NLS_SORT` | Quy tắc sắp xếp/so sánh ngôn ngữ trong các ngữ cảnh áp dụng |
| `NLS_COMP` | Cách Oracle áp dụng so sánh linguistic hoặc binary cho một số phép so sánh SQL |
| `NLS_CHARACTERSET` | Bộ ký tự database cho kiểu ký tự thông thường |
| `NLS_NCHAR_CHARACTERSET` | Bộ ký tự quốc gia cho kiểu `NCHAR`/`NVARCHAR2`/`NCLOB` |

### 8.1. Xem NLS settings của database

```sql
SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET',
    'NLS_LANGUAGE',
    'NLS_TERRITORY'
)
ORDER BY parameter;
```

Các tham số character set phản ánh cấu hình ở mức database; `NLS_LANGUAGE` và `NLS_TERRITORY` ở đây phản ánh giá trị mặc định liên quan database.

### 8.2. Xem NLS settings của session

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_SORT',
    'NLS_COMP'
)
ORDER BY parameter;
```

Session có thể có thiết lập khác giá trị mặc định database do client, cấu hình ứng dụng hoặc `ALTER SESSION`. Vì vậy hai user chạy cùng SQL trên hai session khác nhau có thể nhận kết quả sắp xếp/so sánh khác nhau nếu câu SQL phụ thuộc NLS session.

### 8.3. ALTER SESSION chỉ ảnh hưởng session hiện tại

Ví dụ thay đổi cấu hình session để minh họa so sánh linguistic:

```sql
-- Ví dụ thử nghiệm trong một session riêng.
ALTER SESSION SET NLS_COMP = LINGUISTIC;
ALTER SESSION SET NLS_SORT = BINARY_CI;

SELECT customer_name
FROM customers
WHERE customer_name = 'lan';
```

`BINARY_CI` là kiểu sort binary không phân biệt hoa/thường. Các cấu hình `BINARY_AI` có thể dùng cho so sánh không phân biệt hoa/thường và dấu trong những ngữ cảnh hỗ trợ. Khi `NLS_COMP = LINGUISTIC`, Oracle áp dụng quy tắc `NLS_SORT` cho các phép so sánh SQL liên quan theo tài liệu phiên bản.

**Cảnh báo:** `ALTER SESSION` thay đổi trạng thái của session. Trong ứng dụng dùng connection pool, session có thể được tái sử dụng cho request tiếp theo; nếu không reset cấu hình, request khác có thể nhận hành vi so sánh ngoài dự kiến. Không thay đổi NLS settings toàn cục hoặc trong mỗi request chỉ để làm một màn hình tìm kiếm chạy được mà chưa đánh giá tác động tới sort, index, plan và nghiệp vụ.

### 8.4. Hàm NLS và tham số tường minh

Nếu chỉ cần chuyển chữ theo một quy tắc ngôn ngữ, có thể dùng `NLS_UPPER`/`NLS_LOWER` với `nlsparam` tường minh mà không phải thay toàn bộ session. Điều này giúp biểu thức dễ đọc và giảm phụ thuộc vào thiết lập session đang thay đổi.

Tuy nhiên, khi biểu thức được lưu trong **function-based index**, tính nhất quán của quy tắc là rất quan trọng. Không tạo index dựa trên một quy tắc NLS ngầm có thể thay đổi theo session rồi mong mọi client tạo cùng khóa. Nên dùng biểu thức có quy tắc cố định, kiểm tra theo phiên bản và quản lý việc rebuild index khi thay đổi chính sách.

## 9. Bộ ký tự, Unicode và các trường hợp chữ đặc biệt

Với tiếng Anh cơ bản, phép chuyển `a` thành `A` thường trực quan. Với Unicode và các ngôn ngữ khác, một ký tự có thể có quy tắc hoa/thường phức tạp hơn.

### 9.1. Chữ i trong tiếng Thổ Nhĩ Kỳ

Tiếng Thổ Nhĩ Kỳ phân biệt:

| Chữ thường | Chữ hoa tương ứng |
|---|---|
| `i` | `İ` (I có chấm) |
| `ı` | `I` (I không chấm) |

Do đó, một ứng dụng đa ngôn ngữ không nên mặc định mọi trường hợp đều có thể chuẩn hóa bằng `UPPER` theo quy tắc tiếng Anh. `NLS_UPPER` với quy tắc phù hợp có thể biểu đạt mapping theo ngôn ngữ, nhưng phải xác nhận giá trị NLS sort có sẵn và test trên database thật.

### 9.2. Dấu tiếng Việt

Ví dụ dữ liệu:

```sql
SELECT UPPER('đặng thị lan') AS upper_name,
       LOWER('ĐẶNG THỊ LAN') AS lower_name,
       INITCAP('ĐẶNG THỊ LAN') AS initcap_name
FROM dual;
```

Trên database hỗ trợ đầy đủ ký tự tiếng Việt, các hàm chuyển chữ sẽ áp dụng ánh xạ cho ký tự mà Oracle nhận được. Kết quả mong muốn về mặt hiển thị là dạng chữ hoa, chữ thường hoặc viết hoa đầu từ, **không loại bỏ dấu**. Cần kiểm tra với bộ ký tự, collation và phiên bản thực tế; không suy luận từ một ví dụ ASCII rằng mọi ký tự Unicode đều được xử lý giống nhau.

### 9.3. Ký tự có nhiều cách biểu diễn Unicode

Một ký tự nhìn giống nhau có thể được biểu diễn bằng một code point dựng sẵn hoặc bằng tổ hợp chữ cái và combining mark. Chuyển chữ hoa/thường **không đồng nghĩa với chuẩn hóa Unicode NFC/NFD**. Vì vậy hai chuỗi hiển thị giống nhau vẫn có thể khác biểu diễn bên trong và không nhất thiết so sánh bằng nhau theo quy tắc binary.

Nếu dữ liệu đến từ nhiều hệ thống, cần xác định chính sách Unicode normalization ở tầng ứng dụng hoặc cơ chế được lựa chọn, sau đó dùng nhất quán cho insert, update, tìm kiếm và uniqueness. Không dùng `UPPER` làm giải pháp duy nhất cho mọi vấn đề Unicode.

### 9.4. Độ dài có thể không chỉ là số byte

Để quan sát dữ liệu ký tự, có thể dùng:

```sql
SELECT text_value,
       LENGTH(text_value)  AS length_chars,
       LENGTHB(text_value) AS length_bytes,
       LENGTHC(text_value) AS length_complete_chars
FROM lab_unicode_text;
```

`LENGTHC` đếm Unicode complete characters theo định nghĩa Oracle; `LENGTHB` đếm byte. `LENGTH2` và `LENGTH4` có cách đếm theo UCS2/UCS4 code point. Những hàm này có giới hạn loại dữ liệu và phiên bản cần xem trong tài liệu Oracle. Bảng `LAB_UNICODE_TEXT` là ví dụ khái niệm, không thuộc bảng lab tạo ở phần trước.

Khi cột gần chạm giới hạn `VARCHAR2(n BYTE)` hoặc khi xây index trên biểu thức chuẩn hóa, hãy kiểm tra độ dài byte của kết quả chuyển chữ, không chỉ đếm số ký tự hiển thị.

## 10. So sánh không phân biệt hoa/thường: nhiều cách triển khai

Tìm kiếm không phân biệt hoa thường là một yêu cầu phổ biến, nhưng có nhiều cách làm. Chọn cách phù hợp với phiên bản Oracle, quy tắc ngôn ngữ, index và yêu cầu uniqueness.

### 10.1. Chuyển cả hai vế bằng UPPER

```sql
SELECT user_id, username
FROM app_users
WHERE UPPER(username) = UPPER(:p_username);
```

Ưu điểm:

- Dễ hiểu và áp dụng trong nhiều phiên bản Oracle.
- Không phải thay đổi giá trị gốc trong bảng.
- Có thể kết hợp với function-based index trên cùng biểu thức.

Hạn chế:

- Quy tắc case mapping là quy tắc của `UPPER`, không nhất thiết đáp ứng mọi ngôn ngữ.
- Nếu không có index phù hợp, Oracle có thể phải tính hàm trên nhiều hàng.
- Cột `NULL` vẫn tạo kết quả `NULL`; cần xác định chính sách dữ liệu thiếu.

### 10.2. Function-based index trên UPPER

Nếu truy vấn tìm kiếm theo `UPPER(username)` diễn ra thường xuyên, có thể tạo index trên biểu thức:

```sql
CREATE INDEX ix_app_users_upper_username
ON app_users (UPPER(username));
```

Truy vấn cần dùng biểu thức tương ứng:

```sql
SELECT user_id, username
FROM app_users
WHERE UPPER(username) = UPPER(:p_username);
```

Oracle có thể dùng function-based index khi biểu thức và điều kiện phù hợp với index, statistics và kế hoạch chi phí. Index **không buộc optimizer luôn dùng**; cần xem execution plan và workload thực tế.

### 10.3. Unique function-based index để cấm trùng không phân biệt hoa/thường

Giả sử username không phân biệt hoa thường theo quy tắc ứng dụng. Có thể tạo:

```sql
CREATE TABLE lab_case_users (
    user_id  NUMBER PRIMARY KEY,
    username VARCHAR2(80 CHAR) NOT NULL
);

CREATE UNIQUE INDEX ux_lab_case_users_upper
ON lab_case_users (UPPER(username));
```

Khi đó `Lan` và `LAN` tạo cùng index key `LAN`, nên không thể cùng tồn tại theo unique index. Đây là **unique index trên biểu thức**, không phải một `UNIQUE` constraint thông thường khai báo trực tiếp trên cột `USERNAME`. Nó có thể bảo vệ uniqueness theo biểu thức, nhưng không nên giả định nó có cùng metadata/khả năng làm khóa được foreign key tham chiếu như một unique constraint cột thông thường.

Vì `USERNAME` được khai báo `NOT NULL`, ví dụ không cho phép nhiều username thiếu. Nếu cột biểu thức có thể là `NULL`, B-tree index có các quy tắc riêng về việc lưu key null; cần thiết kế thêm `NOT NULL`/constraint theo yêu cầu nghiệp vụ.

### 10.4. Dùng NLS_UPPER với quy tắc cố định

Với dữ liệu đa ngôn ngữ, có thể cần biểu thức NLS cụ thể:

```sql
-- Ví dụ minh họa; chọn NLS_SORT đúng với yêu cầu và bản Oracle.
SELECT user_id, username
FROM lab_case_users
WHERE NLS_UPPER(username, 'NLS_SORT = XTurkish') =
      NLS_UPPER(:p_username, 'NLS_SORT = XTurkish');
```

Nếu muốn index hỗ trợ biểu thức này, biểu thức index và biểu thức truy vấn phải nhất quán:

```sql
-- Ví dụ thiết kế cần kiểm thử trên phiên bản đích.
CREATE INDEX ix_lab_case_users_turkish
ON lab_case_users (
    NLS_UPPER(username, 'NLS_SORT = XTurkish')
);
```

Sử dụng `nlsparam` tường minh giúp quy tắc chuyển chữ không phụ thuộc ngầm vào NLS session. Tuy vậy, việc tạo index/function-based index cho biểu thức linguistic cần được kiểm thử kỹ về tính ổn định, collation và khả năng sử dụng trên phiên bản Oracle đang chạy.

### 10.5. Collation không phân biệt hoa/thường hoặc dấu

Oracle có các collation như `BINARY_CI` (case-insensitive) và `BINARY_AI` (accent-insensitive và case-insensitive) trong các ngữ cảnh/phiên bản hỗ trợ. Collation quy định **cách so sánh và sắp xếp**, khác với việc thay đổi giá trị lưu trữ bằng `UPPER`/`LOWER`.

Ở những phiên bản hỗ trợ **data-bound collation**, có thể khai báo collation ở mức cột hoặc biểu thức theo cú pháp và điều kiện của release. Ví dụ khái niệm:

```sql
-- Cú pháp COLLATE cần đối chiếu phiên bản/cấu hình Oracle đích.
-- Ví dụ minh họa cho môi trường hỗ trợ data-bound collation:
CREATE TABLE lab_collation_users (
    user_id NUMBER PRIMARY KEY,
    username VARCHAR2(80 CHAR) COLLATE BINARY_CI
);
```

Không sao chép DDL `COLLATE` sang một release cũ chưa hỗ trợ hoặc chưa bật điều kiện cần thiết. Cũng không giả định `BINARY_AI` luôn đúng cho mọi yêu cầu tìm kiếm tiếng Việt; việc bỏ dấu có thể làm nhiều tên khác nhau trở thành tương đương, gây xung đột uniqueness hoặc kết quả tìm kiếm không mong muốn.

### 10.6. Chọn phương án theo yêu cầu

| Yêu cầu | Cách tiếp cận có thể cân nhắc | Lưu ý |
|---|---|---|
| Tìm mã ASCII không phân biệt hoa/thường | `UPPER(col) = UPPER(:value)` | Đơn giản, kiểm tra index |
| Tìm kiếm thường xuyên trên bảng lớn | Function-based index trên cùng biểu thức | Đo execution plan và chi phí DML |
| Username phải duy nhất không phân biệt hoa/thường | Unique function-based index hoặc thiết kế cột chuẩn hóa | Kiểm tra duplicate trước khi tạo |
| Ngôn ngữ có quy tắc case đặc biệt | `NLS_UPPER`/`NLS_LOWER` với `nlsparam` tường minh | Xác nhận NLS sort và test dữ liệu thực |
| Không phân biệt dấu/hoa thường khi so sánh | Collation phù hợp nếu release hỗ trợ | Kiểm tra va chạm và quy tắc ngôn ngữ |
| Dữ liệu cần giữ nguyên cách viết gốc | Giữ cột gốc, tạo biểu thức/index chuẩn hóa riêng | Không update cột gốc chỉ để tìm kiếm |

## 11. Character set và collation là hai lớp khác nhau

Một nhầm lẫn phổ biến là nghĩ `AL32UTF8` tự động làm mọi phép so sánh trở thành không phân biệt hoa thường hoặc không phân biệt dấu. **Character set** xác định tập ký tự và cách biểu diễn dữ liệu; **collation** xác định quy tắc so sánh/sắp xếp ký tự.

| Lớp | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| Character set | Ký tự nào có thể biểu diễn và được mã hóa ra sao? | `AL32UTF8`, `AL16UTF16` |
| Case mapping | Một chữ thường/hoa được chuyển thành chữ tương ứng nào? | `UPPER`, `LOWER`, `NLS_UPPER` |
| Collation | Hai chuỗi được so sánh/xếp thứ tự thế nào? | `BINARY`, `BINARY_CI`, `BINARY_AI`, linguistic sort |
| Unicode normalization | Các chuỗi có biểu diễn Unicode tương đương được chuẩn hóa thế nào? | NFC/NFD ở lớp hỗ trợ phù hợp |

Ví dụ, database có `AL32UTF8` cho phép lưu nhiều ký tự Unicode, nhưng một phép so sánh binary vẫn có thể coi hai biểu diễn code point khác nhau là khác. Muốn tìm kiếm không phân biệt hoa thường, phải lựa chọn collation hoặc chuẩn hóa theo yêu cầu. Muốn coi hai chuỗi Unicode có dạng kết hợp khác nhau là tương đương, cần xem normalization riêng.

## 12. Tích hợp Java/JDBC: dữ liệu Unicode và chuyển chữ

Java lưu `String` theo Unicode; JDBC driver chịu trách nhiệm truyền chuỗi tới Oracle và chuyển đổi theo kiểu cột/database. Khi ứng dụng sử dụng tiếng Việt hoặc dữ liệu đa ngôn ngữ, cần kiểm tra **cả dữ liệu trước khi gửi và dữ liệu sau khi đọc**.

### 12.1. Bind String thay vì nối chuỗi

```java
String sql = """
    SELECT user_id, username
    FROM lab_case_users
    WHERE UPPER(username) = UPPER(?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, inputUsername);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long userId = rs.getLong("user_id");
            String username = rs.getString("username");
            // Xử lý kết quả theo contract của ứng dụng.
        }
    }
}
```

Bind parameter tránh nối dữ liệu vào SQL và giữ đúng vai trò dữ liệu. Không cần tự viết `UPPER('` + input + `')` vì cách đó vừa có rủi ro SQL injection vừa dễ lỗi dấu nháy/encoding.

### 12.2. Kiểm tra dữ liệu tiếng Việt xuyên suốt

Một bộ kiểm thử hữu ích có thể bao gồm:

```text
Nguyễn An
NGUYỄN AN
nguyễn an
Đặng Thị Lan
đặng thị lan
İstanbul
Istanbul
istanbul
```

Không giả định các chuỗi này đều bằng nhau sau `UPPER`/`LOWER`; hãy xác định yêu cầu về hoa thường, dấu và ngôn ngữ. Kiểm tra:

1. Java nhận chuỗi từ HTTP/JSON/CSV có đúng Unicode không.
2. JDBC bind và insert vào đúng kiểu `VARCHAR2`/`NVARCHAR2`.
3. Oracle lưu và trả lại chuỗi có đúng ký tự không.
4. Hàm `UPPER`/`LOWER`/`NLS_UPPER` trả kết quả như yêu cầu trên database đích.
5. Collation/index có tạo kết quả tìm kiếm và uniqueness đúng như contract không.

### 12.3. Không nhầm NLS_LANG với mọi loại JDBC

Một số công cụ client cũ hoặc kết nối OCI có thiết lập môi trường encoding riêng; không thể lấy cấu hình của SQL*Plus/OCI rồi áp dụng máy móc cho JDBC Thin. Khi gặp lỗi ký tự, cần xác định **driver, client, môi trường chạy và đường truyền** cụ thể. Việc đặt một biến môi trường NLS bất kỳ không tự sửa encoding sai trong ứng dụng Java.

## 13. Kiểm thử hàm và quy tắc chữ với dữ liệu biên

Không nên chỉ thử `abc` và `ABC`. Một bộ kiểm thử cho hệ thống đa ngôn ngữ nên bao gồm:

| Nhóm dữ liệu | Ví dụ | Câu hỏi cần xác nhận |
|---|---|---|
| ASCII cơ bản | `oracle`, `ORACLE`, `Oracle` | Kết quả UPPER/LOWER và equality có đúng không? |
| Tiếng Việt có dấu | `Đặng`, `đặng`, `Nguyễn` | Ký tự có dấu được chuyển chữ đúng không? |
| Ký tự locale đặc biệt | `i`, `I`, `ı`, `İ` | Quy tắc Turkish/locale cần áp dụng là gì? |
| Chữ viết tắt | `API`, `SQL`, `eBay` | INITCAP có làm hỏng kiểu chữ cần giữ không? |
| Dấu câu/khoảng trắng | `an-nguyen`, `an  nguyen`, `O'Connor` | Ranh giới từ INITCAP có đúng yêu cầu không? |
| NULL/chuỗi rỗng | `NULL`, `''` | API và SQL có phân biệt trạng thái thiếu không? |
| Unicode tổ hợp | ký tự dựng sẵn và ký tự + combining mark | Có cần normalization không? |
| Độ dài lớn | chuỗi gần giới hạn cột | Chuyển đổi có ảnh hưởng giới hạn byte/index không? |

### 13.1. Tạo bảng test nhỏ

```sql
CREATE TABLE lab_case_conversion (
    id NUMBER PRIMARY KEY,
    raw_text VARCHAR2(200 CHAR)
);

INSERT INTO lab_case_conversion VALUES (1, 'oracle database');
INSERT INTO lab_case_conversion VALUES (2, 'ORACLE DATABASE');
INSERT INTO lab_case_conversion VALUES (3, 'Đặng Thị Lan');
INSERT INTO lab_case_conversion VALUES (4, 'API and SQL');
INSERT INTO lab_case_conversion VALUES (5, NULL);
COMMIT;
```

### 13.2. Chạy cả ba hàm và quan sát

```sql
SELECT id,
       raw_text,
       UPPER(raw_text) AS upper_text,
       LOWER(raw_text) AS lower_text,
       INITCAP(raw_text) AS initcap_text,
       LENGTH(raw_text) AS char_length,
       LENGTHB(raw_text) AS byte_length
FROM lab_case_conversion
ORDER BY id;
```

So sánh hàng 4 để thấy `INITCAP` có thể đổi `API` thành `Api` và `SQL` thành `Sql`. Hàng 5 cho thấy ba hàm đều trả `NULL`. Đối với hàng tiếng Việt, đối chiếu kết quả trên đúng bộ ký tự và phiên bản Oracle của môi trường.

### 13.3. Kiểm tra tìm kiếm không phân biệt hoa thường

```sql
SELECT id, raw_text
FROM lab_case_conversion
WHERE UPPER(raw_text) = UPPER('ORACLE DATABASE')
ORDER BY id;
```

Kết quả dự kiến có hàng 1 và 2. Hàng 5 không được chọn vì `UPPER(NULL)` là `NULL` và so sánh với chuỗi tạo `UNKNOWN`.

Sau khi thực hành, chỉ dọn dữ liệu nếu xác nhận đây là bảng lab do mình tạo trong DEV/TEST:

```sql
DROP TABLE lab_case_conversion PURGE;
```

`DROP TABLE ... PURGE` xóa object và dữ liệu, không đưa vào recycle bin; là thao tác DDL có implicit commit. Không chạy trên bảng thật hoặc schema dùng chung nếu chưa được phép.

## 14. Hiệu năng và các lỗi thiết kế thường gặp

### 14.1. Hàm trên cột có thể làm thay đổi đường truy cập

Nếu có index B-tree thông thường trên `USERNAME`, truy vấn:

```sql
WHERE UPPER(username) = 'LAN'
```

không còn là phép so sánh trực tiếp trên giá trị gốc của `USERNAME`. Optimizer có thể không dùng index thường như mong muốn. Function-based index trên `UPPER(USERNAME)` là một cách hỗ trợ phù hợp nếu workload cần thiết.

### 14.2. Không tạo function-based index cho mọi cột văn bản

Index tiêu tốn storage và làm tăng chi phí `INSERT`, `UPDATE`, `DELETE`, vì Oracle phải cập nhật index expression khi dữ liệu thay đổi. Chỉ tạo khi có truy vấn đủ thường xuyên và có lợi ích đo được. Nếu chỉ cần định dạng hiển thị ở một báo cáo nhỏ, `UPPER` trong `SELECT` thường đã đủ.

### 14.3. Unique index chuẩn hóa có thể làm lộ duplicate hiện hữu

Trước khi tạo:

```sql
CREATE UNIQUE INDEX ux_users_upper_name
ON users (UPPER(username));
```

hãy kiểm tra các giá trị có cùng biểu thức chuẩn hóa:

```sql
SELECT UPPER(username) AS normalized_name,
       COUNT(*) AS row_count
FROM users
WHERE username IS NOT NULL
GROUP BY UPPER(username)
HAVING COUNT(*) > 1;
```

Nếu truy vấn trả kết quả, unique index có thể không tạo được. Cần xác định bản ghi nào hợp lệ, cách gộp/đổi tên và ảnh hưởng tham chiếu trước khi sửa dữ liệu. Không tự xóa một trong các tài khoản chỉ để tạo index thành công.

### 14.4. Dùng cùng một quy tắc ở mọi đường ghi và tìm kiếm

Nếu ứng dụng insert dùng `LOWER(username)`, màn hình tìm kiếm dùng `UPPER(username)`, batch import giữ nguyên, còn index dùng một biểu thức `NLS_UPPER` khác, hệ thống có thể có hành vi không đồng nhất. Quy tắc chuẩn hóa cần được xác định **một lần ở cấp nghiệp vụ**, sau đó triển khai thống nhất ở database và ứng dụng.

### 14.5. INITCAP không phải công cụ sửa dữ liệu gốc

Không nên chạy `UPDATE people SET full_name = INITCAP(full_name)` hàng loạt chỉ vì dữ liệu đang viết hoa. Tên người có thể gồm họ kép, tiền tố, chữ viết tắt hoặc cách viết riêng. Dữ liệu hiển thị nên có quy tắc được chủ dữ liệu chấp thuận; giữ bản gốc nếu cần truy vết.

## 15. Các lỗi và hiểu lầm phổ biến

| Nhận định sai | Vì sao sai | Cách làm phù hợp |
|---|---|---|
| `UPPER` làm chuỗi không dấu | Hàm chỉ chuyển chữ hoa; dấu vẫn tồn tại | Dùng collation/chuẩn hóa không dấu theo yêu cầu |
| `LOWER` luôn tạo cùng kết quả ở mọi locale | Một số chữ có mapping theo ngôn ngữ | Cân nhắc `NLS_LOWER` với quy tắc tường minh |
| `INITCAP` hiểu tên người và acronym | Hàm chỉ áp dụng quy tắc đầu từ | Định dạng theo từ điển/quy tắc ứng dụng |
| `UPPER` làm thay đổi dữ liệu gốc | Hàm trong SELECT chỉ trả biểu thức | Dùng UPDATE có kiểm soát nếu thật sự muốn lưu |
| `UPPER` tự làm so sánh case-insensitive trong mọi ngữ cảnh | Chỉ chuyển biểu thức; collation và quy tắc locale vẫn quan trọng | Dùng cùng biểu thức hoặc collation được thiết kế rõ |
| `AL32UTF8` đồng nghĩa so sánh không phân biệt hoa/thường | Character set khác collation | Chọn quy tắc so sánh riêng |
| `VARCHAR2(100)` luôn chứa được 100 ký tự Unicode | Độ dài có thể theo BYTE semantics | Dùng `CHAR` semantics khi phù hợp và đo `LENGTHB` |
| Chuỗi nhìn giống nhau chắc chắn bằng nhau | Unicode có thể có nhiều biểu diễn code point | Xác định normalization và collation |
| `UPPER` và `NLS_UPPER` luôn tương đương | NLS function có thể áp dụng quy tắc ngôn ngữ | Chọn theo ngôn ngữ và kiểm thử |
| Chỉ cần ALTER SESSION để mọi ứng dụng tìm kiếm giống nhau | Session/pool có thể mang thiết lập khác nhau | Quản lý NLS/collation rõ ở cấp ứng dụng/database |
| Function-based index luôn được optimizer dùng | Optimizer vẫn quyết định theo chi phí và biểu thức | Xem execution plan, thống kê và workload |
| Tạo unique index trên `UPPER(col)` luôn thành công | Dữ liệu có thể trùng sau chuẩn hóa | Kiểm tra duplicate trước khi tạo |
| `UPPER(NULL)` trả chuỗi rỗng | Kết quả vẫn là NULL | Dùng `IS NULL`/`COALESCE` theo nghiệp vụ |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `UPPER('Oracle Database')` trả về gì?

**Đáp án:** `ORACLE DATABASE`.

**Câu 2.** `LOWER` có tự loại bỏ dấu tiếng Việt không?

**Đáp án:** Không. `LOWER` chuyển chữ thường; dấu vẫn được giữ theo ký tự đầu vào và mapping áp dụng.

**Câu 3.** `INITCAP('API AND SQL')` có bảo đảm trả `API and SQL` không?

**Đáp án:** Không. Hàm có thể trả dạng `Api And Sql`; nó không hiểu acronym hay quy tắc biên tập.

**Câu 4.** Database dùng `AL32UTF8` có đồng nghĩa `WHERE name = 'lan'` tự khớp `LAN` không?

**Đáp án:** Không. Character set và collation là hai khái niệm khác nhau; cần quy tắc so sánh không phân biệt hoa thường.

**Câu 5.** Muốn tìm username không phân biệt hoa thường bằng biểu thức đơn giản, có thể viết gì?

**Đáp án:** `WHERE UPPER(username) = UPPER(:p_username)`, nếu quy tắc case mapping phù hợp yêu cầu nghiệp vụ.

**Câu 6.** Nếu truy vấn thường xuyên dùng `UPPER(username)`, có thể cân nhắc index nào?

**Đáp án:** Function-based index trên `UPPER(username)`, sau khi đánh giá duplicate, chi phí DML và execution plan.

**Câu 7.** Tại sao `NLS_UPPER` có thể khác `UPPER`?

**Đáp án:** `NLS_UPPER` hỗ trợ quy tắc chuyển chữ theo ngôn ngữ và có thể nhận `nlsparam`; `UPPER` dùng ánh xạ ký tự mặc định của hàm.

**Câu 8.** Hai chuỗi Unicode hiển thị giống nhau nhưng có thể so sánh khác nhau vì sao?

**Đáp án:** Chúng có thể dùng biểu diễn code point khác nhau (ví dụ ký tự dựng sẵn và combining mark); chuyển hoa/thường không tự chuẩn hóa Unicode.

**Câu 9.** Có nên dùng `ALTER SESSION SET NLS_SORT = BINARY_CI` trong mỗi request của ứng dụng pool không?

**Đáp án:** Không nên làm tùy tiện. Session có thể được tái sử dụng; cần quản lý/reset trạng thái, đánh giá `NLS_COMP`, collation, index và kế hoạch thực thi.

**Câu 10.** Tạo unique index trên `UPPER(username)` nhưng database đã có `Lan` và `LAN`. Điều gì có thể xảy ra?

**Đáp án:** Hai hàng có cùng normalized key `LAN`; việc tạo unique index có thể thất bại cho tới khi dữ liệu trùng được xử lý theo chính sách nghiệp vụ.

## Kết luận

**`UPPER`**, **`LOWER`** và **`INITCAP`** là các hàm chuyển đổi cách viết của chuỗi; chúng không tự loại bỏ dấu, chuẩn hóa Unicode hay quyết định mọi quy tắc so sánh. **`NLS_UPPER`**, **`NLS_LOWER`** và **`NLS_INITCAP`** hỗ trợ quy tắc chuyển chữ theo ngôn ngữ, có thể dùng tham số NLS tường minh. Kết quả còn cần được hiểu trong bối cảnh database/national character set, collation và NLS session.

Khi xây dựng tìm kiếm hoặc uniqueness không phân biệt hoa thường, hãy chọn một quy tắc chuẩn hóa ổn định, kiểm tra dữ liệu trùng sau chuyển đổi, cân nhắc function-based index hoặc collation phù hợp và kiểm thử với dữ liệu Unicode thật. Đối với ứng dụng Java/JDBC, bảo đảm chuỗi được bind và lưu đúng encoding; không dùng hàm chuyển chữ để che giấu lỗi encoding hoặc thay thế quy tắc nghiệp vụ. Cách tiếp cận này giúp kết quả nhất quán giữa DEV, TEST, production và các client đa ngôn ngữ.
