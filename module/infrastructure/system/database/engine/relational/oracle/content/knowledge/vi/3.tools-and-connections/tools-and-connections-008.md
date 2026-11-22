# Quản lý biến bind, biến thay thế và dấu kết thúc SQL/PLSQL trong script

## 1. Vì sao ba khái niệm này quan trọng?

Khi viết một script Oracle, những dòng trông giống nhau có thể được xử lý bởi **hai nơi khác nhau**: công cụ chạy script như SQL\*Plus/SQLcl và Oracle Database. Điều này giải thích vì sao cùng một dấu `&`, dấu `:` hoặc dấu `/` có thể khiến script hoạt động đúng trong SQL\*Plus nhưng thất bại khi gửi qua JDBC.

Ví dụ:

```sql
SELECT &p_id AS id_from_substitution FROM dual;
SELECT :b_id AS id_from_bind FROM dual;

BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello, Oracle');
END;
/
```

Ba điểm khác nhau xuất hiện trong ví dụ:

1. `&p_id` là **biến thay thế** (*substitution variable*): SQL\*Plus/SQLcl thay văn bản `&p_id` trước khi gửi câu SQL cho Oracle.
2. `:b_id` là **biến bind** (*bind variable*): một giá trị được truyền tách biệt với văn bản SQL, có kiểu dữ liệu và cần được khai báo/gán trong công cụ thực thi.
3. Dấu `/` trên **một dòng riêng** là lệnh của công cụ script để thực thi khối PL/SQL đang được giữ trong bộ đệm; nó không phải toán tử chia hay một phần cú pháp PL/SQL.

Nhầm lẫn các cơ chế này dẫn đến câu lệnh bị nhắc nhập giá trị ngoài ý muốn, lỗi bind chưa khai báo, PL/SQL không được thực thi, hoặc cùng câu SQL bị chạy hai lần.

**Mục tiêu sau bài học:** bạn có thể chọn đúng loại biến cho từng mục đích, quản lý vòng đời biến trong phiên script, phân biệt dấu `;` và `/`, viết một file `.sql` chạy tuần tự trong SQL\*Plus/SQLcl, đồng thời nhận ra những khác biệt khi chạy lệnh từ Java/JDBC hoặc một công cụ GUI.

## 2. Hiểu đường đi của một lệnh trong script Oracle

Hãy hình dung hai tầng xử lý:

```text
File .sql hoặc câu lệnh gõ ở terminal
                  |
                  v
       SQL*Plus / SQLcl / công cụ script
       - Đọc DEFINE, ACCEPT, VARIABLE, SET
       - Xử lý &ten và &&ten
       - Nhận biết ;, / và lệnh của client
       - Gắn giá trị bind :ten nếu có
                  |
                  v
           Oracle Database
       - Phân tích SQL hoặc PL/SQL
       - Thực thi với các giá trị bind
       - Trả kết quả / lỗi / output
                  |
                  v
       Công cụ hiển thị kết quả
```

Trong bài này, ví dụ được viết chủ yếu cho **Oracle SQL\*Plus** và **Oracle SQLcl**. Hai công cụ này hỗ trợ các lệnh script như `DEFINE`, `VARIABLE`, `PROMPT`, `SET`, `@` và `/`. SQL Developer ở chế độ **Run Script** (thường là `F5`) hỗ trợ nhiều cú pháp tương tự, nhưng cách hiển thị, nhắc nhập giá trị và mức hỗ trợ một số lệnh có thể khác. Chế độ **Run Statement** (thường là `Ctrl+Enter`) không tương đương việc chạy cả file qua SQL\*Plus.

**Phân biệt hai nhóm lệnh:**

| Nhóm | Ví dụ | Ai xử lý? |
|---|---|---|
| SQL | `SELECT`, `INSERT`, `UPDATE`, `CREATE TABLE` | Oracle Database |
| PL/SQL | `DECLARE ... BEGIN ... END;`, procedure, function | Oracle Database |
| Lệnh client | `DEFINE`, `ACCEPT`, `VARIABLE`, `PRINT`, `SET`, `PROMPT`, `@` | SQL\*Plus/SQLcl |
| Ký hiệu điều khiển script | `&`, `&&`, dấu `/` riêng dòng | Công cụ script xử lý trước hoặc khi gửi lệnh |

Một cú pháp do SQL\*Plus xử lý có thể **không hợp lệ** khi gửi nguyên văn qua JDBC. Vì vậy, luôn xác định rõ script chạy ở công cụ nào trước khi viết.

## 3. Biến thay thế `&name`: thay văn bản trước khi Oracle nhận SQL

Biến thay thế là cơ chế của SQL\*Plus/SQLcl, không phải biến PL/SQL. Cú pháp thông dụng là `&ten_bien`.

Ví dụ trong SQL\*Plus:

```sql
SELECT &p_number AS so_duoc_nhap FROM dual;
```

Nếu chưa có biến `p_number`, công cụ có thể hiển thị lời nhắc như:

```text
Enter value for p_number: 25
```

Sau khi người dùng nhập `25`, công cụ gửi về cơ bản câu lệnh sau đến Oracle:

```sql
SELECT 25 AS so_duoc_nhap FROM dual;
```

Oracle **không biết** trước đó người dùng gõ `&p_number`; nó chỉ nhận phần SQL đã được thay thế. Vì thay đổi diễn ra ở mức **văn bản**, phần nhập phải tạo thành cú pháp SQL hợp lệ sau khi được chèn vào.

### 3.1. `DEFINE`: đặt trước giá trị thay thế

Thay vì mỗi lần chạy đều nhập tương tác, bạn có thể định nghĩa giá trị trong phiên:

```sql
DEFINE p_number = 25

SELECT &p_number AS so_duoc_chon FROM dual;

UNDEFINE p_number
```

`DEFINE` tạo hoặc gán biến thay thế. `UNDEFINE` xóa định nghĩa để tránh rò rỉ giá trị sang các script chạy tiếp trong **cùng phiên**. Lệnh `DEFINE` không có tham số có thể dùng để liệt kê các biến đang được định nghĩa, nhưng với dữ liệu nhạy cảm cần hạn chế hiển thị giá trị trên màn hình hoặc log.

Các lệnh `DEFINE`, `UNDEFINE` là lệnh client; thông thường **không thêm dấu `;`** như câu SQL.

### 3.2. `&name` và `&&name` khác nhau như thế nào?

| Cú pháp | Ý nghĩa khi chưa có giá trị | Những lần dùng tiếp theo |
|---|---|---|
| `&name` | Nhắc nhập giá trị để thay vào vị trí hiện tại | Có thể hỏi lại nếu chưa `DEFINE` biến |
| `&&name` | Nhắc nhập rồi **định nghĩa lại để giữ giá trị trong phiên** | Sử dụng giá trị đã lưu, không hỏi lại cho đến khi `UNDEFINE` |
| `DEFINE name = value` | Đặt sẵn giá trị, không cần hỏi | Cả `&name` và `&&name` có thể dùng giá trị đó |

Ví dụ:

```sql
SELECT '&&p_city' AS thanh_pho_lan_1 FROM dual;
SELECT '&&p_city' AS thanh_pho_lan_2 FROM dual;

UNDEFINE p_city
```

Ở lần đầu, công cụ hỏi `p_city` nếu biến chưa tồn tại; lần hai dùng lại giá trị đã lưu. Các dấu nháy đơn bao quanh `&&p_city` là **dấu nháy SQL** tạo chuỗi ký tự, không phải một phần giá trị của biến thay thế. Nếu người dùng nhập một chuỗi chứa dấu nháy không được xử lý đúng, câu SQL có thể lỗi hoặc bị thay đổi ý nghĩa.

Ngược lại, nếu viết:

```sql
SELECT &p_city AS gia_tri FROM dual;
```

và nhập tên thành phố là `Ha Noi` không có nháy đơn, Oracle sẽ nhận một biểu thức không hợp lệ. Thêm nháy ngoài `&p_city` có thể giải quyết việc hình thành chuỗi ở ví dụ đơn giản, **nhưng vẫn không tạo ra tham số an toàn**. Với dữ liệu do người dùng cung cấp, dùng bind variable phù hợp hơn.

### 3.3. `ACCEPT`: nhập có lời nhắc và kiểu cơ bản

`ACCEPT` là lệnh của SQL\*Plus/SQLcl để thu thập giá trị tương tác, lưu vào **biến thay thế**. Ví dụ:

```sql
ACCEPT p_limit NUMBER PROMPT 'Nhap gioi han so: '

SELECT &p_limit AS gioi_han FROM dual;

UNDEFINE p_limit
```

`ACCEPT ... NUMBER` giúp kiểm tra đầu vào có dạng số theo quy tắc của client. Đây không phải cơ chế bind: sau khi chấp nhận, `&p_limit` vẫn được **thay bằng văn bản**. `ACCEPT` hữu ích cho các script quản trị/chẩn đoán chạy tương tác, còn ứng dụng Java thường nhận dữ liệu ở tầng API và gửi bind qua driver.

### 3.4. Cách chẩn đoán phần SQL được thay thế

SQL\*Plus có thể hiện câu SQL trước và sau khi thay thế bằng `SET VERIFY ON`:

```sql
SET VERIFY ON
DEFINE p_number = 7

SELECT &p_number AS n FROM dual;

UNDEFINE p_number
SET VERIFY OFF
```

Trong output, bạn có thể thấy các dòng `old` và `new` cho biết văn bản nào được thay. `SET VERIFY OFF` tắt việc hiển thị cặp dòng này, **không tắt cơ chế thay thế biến**. `SET ECHO ON/OFF` là tùy chọn khác, quyết định việc hiển thị các dòng lệnh khi chạy script trong các hoàn cảnh được hỗ trợ; nó không đồng nghĩa với `SET VERIFY`.

Khi script có giá trị bí mật, cả echo, verify, spool và log của các công cụ liên quan đều cần được kiểm soát. Việc ẩn dòng `old/new` không tự bảo đảm bí mật không xuất hiện ở đầu ra khác.

## 4. Dấu `&` trong dữ liệu thật: cách tránh prompt ngoài ý muốn

Một lỗi quen thuộc là viết:

```sql
SELECT 'R&D' AS ten_bo_phan FROM dual;
```

Trong môi trường SQL\*Plus có bật substitution, dấu `&` có thể khiến công cụ thử diễn giải phần sau là tên biến và nhắc nhập, dù lập trình viên chỉ muốn chuỗi `R&D`.

Cách thường dùng là **tắt thay thế biến** trong đoạn có dữ liệu chứa dấu `&`:

```sql
SET DEFINE OFF

SELECT 'R&D' AS ten_bo_phan FROM dual;
SELECT 'A&B' AS nhan_hieu FROM dual;

SET DEFINE ON
```

`SET DEFINE OFF` tác động đến **phiên công cụ**, không thay đổi cấu hình Oracle Database. Sau khi bật trở lại bằng `SET DEFINE ON`, các biểu thức `&name` lại được xử lý. Nếu có script khác được gọi cùng phiên, việc quên bật lại có thể khiến các script đó không nhận giá trị thay thế như dự kiến.

Một số môi trường hỗ trợ thay đổi ký tự substitution bằng `SET DEFINE` với một ký tự thay thế; cách đó đòi hỏi các script liên quan thống nhất quy ước. Khi muốn viết giá trị chuỗi chứa `&` một cách có kiểm soát, có thể **khởi tạo bind** trong đoạn `SET DEFINE OFF` rồi dùng bind ở các câu SQL khác:

```sql
VARIABLE b_brand VARCHAR2(100)

SET DEFINE OFF
BEGIN
    :b_brand := 'R&D';
END;
/
SET DEFINE ON

SELECT :b_brand AS brand FROM dual;
PRINT b_brand
```

Điểm cần hiểu: khi viết literal `'R&D'` trực tiếp trong file script, SQL\*Plus vẫn phải **đọc văn bản đó**. Bind variable giúp sử dụng giá trị đã thiết lập trong SQL sau này; `SET DEFINE OFF` ở đoạn khởi tạo ngăn SQL\*Plus động chạm vào ký tự `&` trong literal.

## 5. Biến bind `:name`: truyền giá trị có kiểu vào SQL/PLSQL

**Bind variable** là tham số/biến được công cụ cung cấp cho Oracle khi thực thi. Khác `&name`, Oracle nhận câu SQL với placeholder và nhận giá trị riêng; vì thế nó không cần chèn văn bản của giá trị vào cấu trúc câu lệnh.

Trong SQL\*Plus/SQLcl, có thể khai báo biến bind bằng lệnh `VARIABLE` (viết tắt `VAR`):

```sql
VARIABLE b_customer_id NUMBER
VARIABLE b_customer_name VARCHAR2(100)
```

Đặt giá trị thông qua khối PL/SQL:

```sql
BEGIN
    :b_customer_id := 101;
    :b_customer_name := 'Nguyen Lan';
END;
/
```

Sử dụng biến bind trong câu truy vấn:

```sql
SELECT :b_customer_id AS customer_id,
       :b_customer_name AS customer_name
FROM dual;
```

In biến bind bằng lệnh client:

```sql
PRINT b_customer_id
PRINT b_customer_name
```

Các điểm quan trọng:

- Dấu `:` khi dùng trong SQL/PLSQL, ví dụ `:b_customer_id`, chỉ một giá trị bind do công cụ cung cấp. `VARIABLE` và `PRINT` lại dùng **tên biến không kèm dấu `:`**.
- Khai báo `VARIABLE` trong SQL\*Plus/SQLcl cần thực hiện **trước khi** dùng biến trong lệnh SQL/PLSQL. Nếu bỏ qua, có thể gặp lỗi dạng `SP2-0552: Bind variable ... not declared`.
- Bind variable vẫn tồn tại ở phạm vi phiên công cụ. `UNDEFINE` chỉ xóa **biến thay thế**, không phải cơ chế xóa bind variable. Có thể khai báo/gán lại tùy nhu cầu hoặc kết thúc phiên.
- Oracle thực hiện kiểm tra kiểu dữ liệu và điều kiện phù hợp khi gắn giá trị. Với số tiền hoặc mã định danh, chọn kiểu phù hợp thay vì biến mọi thứ thành chuỗi.

### 5.1. Gán nhanh bằng `EXEC`

SQL\*Plus có lệnh `EXEC` (viết tắt của `EXECUTE`) để chạy câu PL/SQL một dòng. Ví dụ:

```sql
VARIABLE b_rate NUMBER
EXEC :b_rate := 0.15

SELECT 1000 * :b_rate AS thue FROM dual;
```

`EXEC` là cách viết ngắn do client hỗ trợ. Cú pháp tương đương về ý nghĩa trong trường hợp này là:

```sql
BEGIN
    :b_rate := 0.15;
END;
/
```

Khi chuyển sang mã JDBC, bạn không gửi nguyên chữ `EXEC :b_rate := ...` như một câu SQL; bạn dùng API driver hoặc một khối PL/SQL đúng cú pháp.

### 5.2. Nhận dữ liệu từ PL/SQL vào bind

Biến bind cho phép đưa kết quả PL/SQL ra ngoài phạm vi khối:

```sql
VARIABLE b_table_count NUMBER

BEGIN
    SELECT COUNT(*)
    INTO :b_table_count
    FROM user_tables;
END;
/

PRINT b_table_count
```

`USER_TABLES` là view chứa thông tin các bảng thuộc schema đang kết nối, nên ví dụ không đòi hỏi có sẵn bảng `EMPLOYEES` hay dữ liệu ứng dụng. `:b_table_count` ở đây đóng vai trò đầu ra. Ngược lại, một biến PL/SQL cục bộ khai báo bằng `DECLARE v_count NUMBER;` chỉ có phạm vi trong block đó; bạn không thể gọi `PRINT v_count` sau khi block kết thúc trừ khi đã gán giá trị sang biến bind của client.

### 5.3. Giá trị bind dùng với `WHERE`, DML và `RETURNING`

Trong ứng dụng có bảng `app_customers`, một truy vấn tham số hóa có dạng:

```sql
SELECT customer_id, full_name
FROM app_customers
WHERE customer_id = :b_customer_id;
```

Khi cần ghi dữ liệu, bind cũng có thể xuất hiện trong `INSERT`, `UPDATE`, `DELETE`. Một số công cụ Oracle hỗ trợ nhận giá trị `RETURNING ... INTO` vào biến bind, ví dụ cấu trúc minh họa dưới đây (chỉ chạy nếu bạn có bảng/cột tương ứng):

```sql
VARIABLE b_new_id NUMBER
VARIABLE b_email VARCHAR2(200)

BEGIN
    :b_email := 'lan@example.com';
END;
/

INSERT INTO app_customers (email, full_name)
VALUES (:b_email, 'Nguyen Lan')
RETURNING customer_id INTO :b_new_id;

PRINT b_new_id
```

Với ví dụ ghi dữ liệu, bạn phải tự quyết định giao dịch: `COMMIT` để xác nhận, hoặc `ROLLBACK` để hủy thay đổi chưa commit. Không mặc định rằng lệnh `PRINT` sẽ commit thay bạn. Phần ví dụ chỉ nhằm phân biệt biến đầu vào và đầu ra, không phải một script migration để chạy nguyên vẹn trên mọi database.

### 5.4. Bind không thay được tên bảng hay tên cột

Bind dùng cho **giá trị biểu thức**; không dùng để thay cấu trúc cú pháp SQL:

```sql
-- Minh họa ý tưởng SAI: tên bảng không thể lấy từ bind như dữ liệu
SELECT * FROM :b_table_name;
```

Nếu cần chọn tên bảng/cột động, hãy sử dụng danh sách định danh được phép (*allowlist*) và xây dựng SQL động có kiểm soát; các giá trị lọc vẫn nên bind. `&table_name` có thể chèn văn bản để hình thành tên bảng trong một script đáng tin cậy, nhưng nếu cho dữ liệu người dùng chưa kiểm chứng đi vào biến thay thế, rủi ro SQL injection vẫn tồn tại.

## 6. Bảng so sánh `&name`, `&&name`, `:name` và biến PL/SQL

| Đặc điểm | `&name` | `&&name` | `:name` trong SQL\*Plus | `v_name` khai báo trong PL/SQL |
|---|---|---|---|---|
| Bản chất | Biến thay thế văn bản | Biến thay thế và lưu giá trị dùng lại | Bind variable | Biến cục bộ/chương trình PL/SQL |
| Được xử lý chủ yếu ở đâu? | Client script | Client script | Client cung cấp giá trị cho database | PL/SQL engine |
| Khai báo thường dùng | `DEFINE`, `ACCEPT`, hoặc prompt | `DEFINE`, prompt lần đầu | `VARIABLE` | `DECLARE`, tham số procedure/function |
| Cách đưa giá trị vào SQL | Thay chuỗi trước khi gửi | Thay chuỗi trước khi gửi | Gắn tham số riêng với SQL | Dùng trực tiếp trong phạm vi PL/SQL |
| Có kiểu dữ liệu không? | Về cơ bản là văn bản; `ACCEPT` có kiểm tra đầu vào | Tương tự `&` | Có, theo khai báo và driver | Có |
| Nguy cơ injection khi chèn đầu vào vào SQL | Cao nếu không kiểm soát | Cao nếu không kiểm soát | Giảm mạnh đối với giá trị được bind đúng cách | Phụ thuộc cách dùng; SQL động ghép chuỗi vẫn có rủi ro |
| Dùng lại sau một block PL/SQL? | Nếu còn trong phiên client | Có cho đến khi `UNDEFINE` | Có trong phiên client | Không, nếu chỉ là biến cục bộ của block |

**Quy tắc thực dụng:** với **giá trị dữ liệu**, ưu tiên bind. Với **lựa chọn cấu trúc script do người vận hành kiểm soát**, biến thay thế có thể hữu ích, nhưng phải kiểm tra đầu vào. Với **tính toán nội bộ PL/SQL**, dùng biến PL/SQL và chỉ đưa ra bind khi thực sự cần truyền kết quả về client.

### 6.1. Hai ví dụ trông giống nhau nhưng khác bản chất

Biến thay thế:

```sql
DEFINE p_id = 42
SELECT &p_id AS customer_id FROM dual;
UNDEFINE p_id
```

Client tạo ra câu SQL tương đương `SELECT 42 AS customer_id FROM dual` trước khi Oracle xử lý.

Biến bind:

```sql
VARIABLE b_id NUMBER
BEGIN
    :b_id := 42;
END;
/
SELECT :b_id AS customer_id FROM dual;
```

Client truyền giá trị số `42` cho placeholder `:b_id`. Câu SQL giữ cấu trúc tham số hóa. Một câu lệnh tham số hóa có thể hỗ trợ chia sẻ cursor/giảm parse khi được dùng đúng cách, nhưng hiệu quả thực tế còn phụ thuộc cách thực thi và môi trường; đó không phải lý do để ghép văn bản SQL tùy tiện.

## 7. Dấu kết thúc: `;` và `/` có nhiệm vụ khác nhau

Trong SQL\*Plus/SQLcl, cần phân biệt **kết thúc một câu SQL**, **kết thúc câu lệnh bên trong PL/SQL** và **yêu cầu công cụ thực thi bộ đệm**.

### 7.1. Câu SQL thông thường kết thúc bằng `;`

```sql
SELECT 'Hello' AS greeting FROM dual;
```

Theo thiết lập mặc định phổ biến, dấu chấm phẩy `;` ở cuối lệnh là **SQL terminator** mà SQL\*Plus nhận diện để gửi câu SQL đi thực thi. Dấu `;` kết thúc thao tác nhập trong công cụ; nó không phải một phần bắt buộc trong chuỗi SQL gửi qua mọi API.

Một câu SQL nhiều dòng vẫn chỉ cần một terminator:

```sql
SELECT employee_id,
       first_name,
       last_name
FROM employees
WHERE department_id = 10
ORDER BY employee_id;
```

Ví dụ này cần schema có bảng `EMPLOYEES` (chẳng hạn schema thực hành HR); nó minh họa cách kết thúc SQL, không bảo đảm có sẵn bảng trong mọi môi trường.

### 7.2. Khối PL/SQL có dấu `;` bên trong và thường cần `/` riêng dòng

```sql
SET SERVEROUTPUT ON

BEGIN
    DBMS_OUTPUT.PUT_LINE('Dong thu nhat');
    DBMS_OUTPUT.PUT_LINE('Dong thu hai');
END;
/
```

- Dấu `;` sau từng lời gọi `DBMS_OUTPUT.PUT_LINE(...)` **kết thúc statement PL/SQL bên trong block**.
- `END;` **kết thúc block theo cú pháp PL/SQL**.
- Dấu `/` **đứng riêng một dòng** ra lệnh SQL\*Plus/SQLcl thực thi block trong bộ đệm.
- `SET SERVEROUTPUT ON` yêu cầu client hiển thị nội dung do `DBMS_OUTPUT.PUT_LINE` tạo ra; nếu không bật, block vẫn có thể chạy nhưng không thấy dòng output mong đợi.

Không nên viết `END; /` trên cùng một dòng khi đang dùng mô hình script SQL\*Plus; hãy đặt `/` trên dòng riêng.

Trong khối `DECLARE`, cấu trúc vẫn tương tự:

```sql
DECLARE
    v_x NUMBER := 10;
    v_y NUMBER := 20;
BEGIN
    DBMS_OUTPUT.PUT_LINE('Tong = ' || (v_x + v_y));
END;
/
```

### 7.3. Tạo procedure/function cũng thường dùng `/`

Nếu có quyền `CREATE PROCEDURE`, một script định nghĩa procedure có thể viết:

```sql
CREATE OR REPLACE PROCEDURE demo_hello
AS
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from procedure');
END;
/
```

Ở đây `END;` hoàn tất định nghĩa PL/SQL, còn `/` yêu cầu client gửi câu `CREATE OR REPLACE PROCEDURE` tới Oracle để biên dịch/tạo object. Việc `CREATE OR REPLACE` thay đổi đối tượng trong database; chỉ chạy trong schema thực hành hoặc khi được phép. Ví dụ này khác với block `BEGIN ... END; /` không tạo đối tượng lưu lâu dài.

### 7.4. Dấu `/` sau một câu SQL đã chạy có thể làm chạy lặp

Trong SQL\*Plus, `/` thực thi lại câu lệnh SQL hoặc PL/SQL hiện được lưu trong SQL buffer. Vì vậy:

```sql
SELECT 'Lan 1' AS nhan FROM dual;
/
```

có thể làm **câu `SELECT` được thực thi hai lần**: một lần khi gặp `;`, rồi một lần khi gặp `/`. Với `INSERT`, `UPDATE` hoặc `DELETE`, tác động chạy lặp có thể nghiêm trọng hơn: ghi trùng, tăng giá trị hai lần hoặc gặp lỗi ràng buộc.

Khi dùng SQL\*Plus/SQLcl theo cách thông thường, **SQL dùng `;`**, còn **khối PL/SQL/định nghĩa stored program dùng `END;` cùng dòng `/` riêng**. Hãy chú ý rằng `;` nằm *bên trong dấu nháy của string* (ví dụ `'A;B'`) không phải terminator của câu SQL.

### 7.5. Lệnh client thường không cần `;`

Các dòng sau minh họa lệnh của SQL\*Plus:

```sql
SET SERVEROUTPUT ON
SET VERIFY OFF
DEFINE p_flag = Y
VARIABLE b_value NUMBER
PROMPT Chuan bi thuc thi script

UNDEFINE p_flag
```

Chúng được công cụ nhận diện như lệnh riêng; không viết như `SET SERVEROUTPUT ON;` hoặc `DEFINE p_flag = Y;` rồi cho rằng Oracle server sẽ xử lý theo SQL. SQL\*Plus có thể điều chỉnh terminator bằng các thiết lập như `SET SQLTERMINATOR`, nên trong hệ thống có cấu hình khác mặc định cần kiểm tra quy ước công cụ. Dù terminator SQL thay đổi, dấu `;` **trong PL/SQL** vẫn là một phần cú pháp ngôn ngữ và có vai trò riêng.

### 7.6. Bảng tóm tắt dấu kết thúc

| Nội dung trong file script | Kết thúc theo cách phổ biến | Lý do |
|---|---|---|
| `SELECT`, `INSERT`, `UPDATE`, `DELETE` | `;` | Client gửi câu SQL đi thực thi |
| `CREATE TABLE`, `ALTER TABLE` | `;` | DDL là câu SQL |
| `BEGIN ... END;` | `END;` rồi `/` riêng dòng | Dấu `;` thuộc PL/SQL; `/` yêu cầu thực thi buffer |
| `DECLARE ... BEGIN ... END;` | `END;` rồi `/` riêng dòng | Tương tự anonymous block |
| `CREATE OR REPLACE PROCEDURE/FUNCTION/PACKAGE/TRIGGER` | Đóng phần PL/SQL đúng cú pháp rồi `/` riêng dòng | Yêu cầu client gửi định nghĩa tới Oracle |
| `SET`, `DEFINE`, `VARIABLE`, `PRINT`, `PROMPT`, `@file.sql` | Kết thúc bằng xuống dòng | Lệnh riêng của client |

## 8. Chạy một file `.sql` từ công cụ phù hợp

### 8.1. SQL\*Plus và SQLcl

Trong phiên công cụ có kết nối database, bạn có thể chạy file script:

```text
SQL> @demo_variables.sql
```

Lệnh `@` là cơ chế đọc/thực thi script của SQL\*Plus/SQLcl. Khi tổ chức nhiều script, `@@` thường được dùng để gọi file liên quan theo vị trí của script đang chạy trong các trường hợp được hỗ trợ. Đường dẫn cụ thể và current directory phụ thuộc phiên công cụ.

Ví dụ nội dung file `demo_variables.sql` **chỉ đọc dữ liệu**:

```sql
-- demo_variables.sql: chay trong SQL*Plus hoac SQLcl
SET ECHO ON
SET VERIFY OFF
SET SERVEROUTPUT ON
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

PROMPT === Bat dau minh hoa bien Oracle ===

-- Bien thay the, duoc thay van ban trong client
DEFINE p_label = Oracle

-- Bien bind, co kieu va duoc gan trong PL/SQL
VARIABLE b_table_count NUMBER

BEGIN
    SELECT COUNT(*) INTO :b_table_count FROM user_tables;
    DBMS_OUTPUT.PUT_LINE('Da doc so bang trong schema hien tai.');
END;
/

PRINT b_table_count

SELECT '&p_label' AS nhan_script,
       :b_table_count AS so_bang
FROM dual;

UNDEFINE p_label
PROMPT === Hoan thanh ===
```

Bạn có thể lưu nội dung vào file UTF-8 `demo_variables.sql`, mở SQL\*Plus/SQLcl đã kết nối đến Oracle rồi chạy `@demo_variables.sql` (hoặc chỉ định đường dẫn file). Script sử dụng các đối tượng hệ thống `DUAL` và `USER_TABLES` nên không yêu cầu tạo bảng nghiệp vụ hay ghi dữ liệu. `WHENEVER SQLERROR` giúp công cụ kết thúc khi phát sinh lỗi SQL/PLSQL theo quy tắc đã cấu hình; lệnh đó **không bảo đảm bắt được mọi lỗi cú pháp riêng của SQL\*Plus**. Ở script sản xuất cần thiết kế thêm xử lý lỗi hệ điều hành và log nếu phù hợp.

### 8.2. SQL Developer: Run Statement hay Run Script?

| Tình huống | Lựa chọn thường phù hợp | Ghi nhớ |
|---|---|---|
| Chạy một câu `SELECT` để xem bảng kết quả | Run Statement (`Ctrl+Enter` thường gặp) | Công cụ có thể tự xử lý dấu kết thúc và hộp thoại bind |
| Chạy file có `SET`, `PROMPT`, `VARIABLE`, nhiều câu SQL và PL/SQL | Run Script (`F5` thường gặp) | Cách hoạt động gần với script SQL\*Plus hơn |
| Khởi tạo biến bind thông qua `VARIABLE`/`PRINT` | Script mode khi công cụ hỗ trợ | Không mặc định giống hộp thoại bind của statement mode |
| Chạy procedure có dấu `/` | Script mode | Dấu `/` là lệnh client, không phải SQL được gửi thẳng vào database |

Không phải mọi client SQL đều hỗ trợ đầy đủ SQL\*Plus syntax. Khi chuyển script giữa SQL\*Plus, SQLcl, SQL Developer, JDBC, migration tools hoặc IDE khác, cần đối chiếu cách mỗi công cụ phân tách và gửi câu lệnh.

## 9. Dùng biến trong script nhiều file

Biến thay thế và biến bind do SQL\*Plus/SQLcl quản lý thường gắn với **phiên công cụ**, không tự bị hủy sau một lần `@file.sql`. Điều này có lợi khi các script muốn chia sẻ cấu hình, nhưng cũng dễ gây tác dụng ngoài ý muốn nếu script sau dùng lại một biến cũ.

Ví dụ file gọi `main.sql`:

```sql
DEFINE p_env = DEV
PROMPT Environment: &p_env

@child.sql

UNDEFINE p_env
```

Trong `child.sql`:

```sql
SELECT '&p_env' AS current_env FROM dual;
```

Khi chạy `main.sql`, giá trị `p_env` được dùng trong file con vì cùng phiên. Sau khi file con kết thúc, `UNDEFINE p_env` dọn biến. Với script gọi lồng nhau, tránh đặt tên biến quá chung như `x`, `id` hoặc `status` nếu các file có thể ảnh hưởng lẫn nhau.

### 9.1. Tham số vị trí `&1`, `&2`

SQL\*Plus/SQLcl còn hỗ trợ truyền tham số cho file script ở dạng biến thay thế vị trí. Ví dụ nội dung `report_period.sql`:

```sql
SELECT '&1' AS report_period FROM dual;
```

Có thể chạy:

```text
SQL> @report_period.sql 2026-11
```

Khi đó `&1` được thay bằng tham số thứ nhất. Đây vẫn là **thay văn bản**, nên chỉ phù hợp khi đầu vào đáng tin cậy và được kiểm tra. Đối với giá trị đến từ người dùng ứng dụng hoặc hệ thống bên ngoài, cách an toàn hơn là để Java/driver dùng bind thay vì nối chuỗi tạo file SQL.

### 9.2. `COLUMN ... NEW_VALUE`: lấy kết quả SQL làm biến thay thế

Một script báo cáo có thể cần dùng ngày hiện tại làm nhãn:

```sql
COLUMN report_day NEW_VALUE p_report_day NOPRINT

SELECT TO_CHAR(SYSDATE, 'YYYY-MM-DD') AS report_day
FROM dual;

PROMPT Report date: &p_report_day

COLUMN report_day CLEAR
UNDEFINE p_report_day
```

SQL\*Plus lấy giá trị của cột được chọn và lưu vào biến thay thế `p_report_day`. Tính năng này hữu ích khi tạo tiêu đề báo cáo hoặc tên file do script kiểm soát. Vì giá trị vẫn là văn bản thay thế, hãy cẩn trọng nếu dùng dữ liệu không đáng tin cậy để cấu thành lệnh SQL hoặc lệnh hệ điều hành.

## 10. Java/JDBC xử lý bind và terminator khác SQL\*Plus

Trong ứng dụng Java, bạn thường **không** gửi cả file có `DEFINE`, `VARIABLE` và `/` qua một `PreparedStatement`. JDBC gửi một câu SQL hoặc khối PL/SQL cho database thông qua driver; ứng dụng quản lý các tham số bằng API.

Ví dụ minh họa khi bảng `app_customers` tồn tại:

```java
String sql = "SELECT customer_id, full_name "
           + "FROM app_customers WHERE customer_id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);

    try (ResultSet rows = statement.executeQuery()) {
        while (rows.next()) {
            long id = rows.getLong("customer_id");
            String name = rows.getString("full_name");
            System.out.println(id + " - " + name);
        }
    }
}
```

Những khác biệt cần nhớ:

- Với `PreparedStatement` chuẩn, tham số thường được viết bằng dấu **`?`**, sau đó gắn bằng `setLong`, `setString`, `setBigDecimal`... theo vị trí. API và công cụ Oracle khác có thể hỗ trợ named bind, nhưng không nên tự giả định mọi driver hiểu cú pháp `:name` theo cùng cách.
- Chuỗi SQL gửi qua JDBC **thường không bao gồm dấu `;` kết thúc của SQL\*Plus**. Nếu bạn sao chép câu SQL có `;` vào Java rồi gửi nguyên chuỗi, một số trường hợp có thể báo lỗi cú pháp như `ORA-00911` hoặc lỗi phân tích câu lệnh khác.
- Dấu `/` đứng riêng dòng là lệnh của công cụ script, **không** phải ký hiệu Oracle JDBC gửi để kết thúc khối PL/SQL. Một callable statement hoặc khối `BEGIN ... END;` qua driver không sử dụng `/` để yêu cầu thực thi.
- `&p_id` không phải placeholder của JDBC: nó chỉ có ý nghĩa nếu bạn tự đi qua bước tiền xử lý kiểu SQL\*Plus trước đó. Không xây cơ chế thay chuỗi thủ công bằng `String.replace` để giả làm bind.

Ví dụ cấu trúc PL/SQL gửi qua JDBC:

```java
String plsql = "BEGIN DBMS_OUTPUT.PUT_LINE(?); END;";

try (CallableStatement call = connection.prepareCall(plsql)) {
    call.setString(1, "Chao tu Java");
    call.execute();
}
```

Lệnh trên minh họa cách truyền tham số cho một PL/SQL block; `DBMS_OUTPUT` của Oracle không mặc nhiên được console Java hiển thị nếu ứng dụng không có cơ chế đọc output tương ứng. Trong ứng dụng thật, log Java và phản hồi API thường là kênh báo kết quả phù hợp hơn.

### Công cụ migration có cú pháp tách statement riêng

Các công cụ migration và deployment như Flyway, Liquibase hoặc framework tự viết có cơ chế nhận diện ranh giới statement theo định dạng, phiên bản và cấu hình. Một số hỗ trợ dấu `/` cho Oracle trong chế độ nhất định, một số lại yêu cầu không có `/` hoặc sử dụng delimiter riêng. Vì vậy, **không sao chép trực tiếp toàn bộ script SQL\*Plus vào migration rồi mặc định nó sẽ chạy giống nhau**. Hãy đọc quy ước parser của công cụ thực sự dùng để phát hành schema.

## 11. Rủi ro khi chọn sai biến: từ lỗi cú pháp đến SQL injection

Giả sử bạn muốn truy vấn một khách hàng theo địa chỉ email. Cách thay văn bản sau không thích hợp với đầu vào không đáng tin cậy:

```sql
-- Minh hoa cach khong nen dung voi du lieu nguoi dung
SELECT customer_id FROM app_customers
WHERE email = '&p_email';
```

Nếu người dùng nhập địa chỉ chứa dấu nháy đơn hoặc đoạn SQL được cố ý tạo, câu truy vấn sau thay thế có thể bị lỗi hoặc thay đổi ý nghĩa. **Dấu nháy bao quanh `&p_email` không có tác dụng bảo vệ như bind**.

Trong SQL\*Plus, sử dụng biến bind đã khai báo và gán một cách có kiểm soát:

```sql
VARIABLE b_email VARCHAR2(200)

BEGIN
    :b_email := 'lan@example.com';
END;
/

SELECT customer_id FROM app_customers
WHERE email = :b_email;
```

Ở ứng dụng Java, `PreparedStatement` với `setString(...)` là cơ chế truyền dữ liệu đầu vào phù hợp. Ví dụ SQL\*Plus ở trên cố ý dùng literal an toàn để minh họa bind; nếu chương trình thu thập dữ liệu từ người dùng, việc gán vào bind vẫn phải đi qua API/công cụ phù hợp mà không tái dựng SQL bằng phép nối chuỗi nguy hiểm.

**Phân biệt hai trường hợp:**

1. **Giá trị cần lọc/ghi** (`customer_id`, email, số tiền, ngày...): dùng bind; xác thực/kiểm tra nghiệp vụ ở tầng phù hợp.
2. **Tên bảng, tên cột, thứ tự sắp xếp, mệnh đề tùy chọn**: bind không thể thay cho cú pháp SQL; phải chọn từ danh sách cấu trúc cho phép hoặc xây SQL động an toàn bằng công cụ thích hợp.

Ngay cả khi một script nội bộ chỉ có DBA chạy, thói quen phân biệt **tham số giá trị** và **thay thế cú pháp** vẫn giúp giảm lỗi trong vận hành.

## 12. Các lỗi thường gặp và cách lần theo nguyên nhân

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `Enter value for ...` xuất hiện bất ngờ | Dấu `&` bị nhận như substitution variable | Xem phần văn bản chứa `&`; tắt `DEFINE` có phạm vi phù hợp nếu đó là dữ liệu literal |
| `SP2-0552: Bind variable ... not declared` | Dùng `:b_id` nhưng chưa khai báo `VARIABLE b_id ...` trong SQL\*Plus | Khai báo trước, kiểm tra đúng tên và phiên client |
| `ORA-01008: not all variables bound` | Driver/công cụ gửi câu SQL có placeholder chưa được gán đủ | Kiểm tra số lượng/vị trí/tên bind và các nhánh gán tham số |
| SQL/PLSQL đứng chờ nhập tiếp hoặc không có output | Thiếu terminator hoặc thiếu dòng `/` để chạy block trong script mode | Phân biệt `;` với `/`; kết thúc PL/SQL đúng kiểu client |
| Một `INSERT` hoặc `SELECT` chạy hai lần | Dùng cả `;` lẫn `/` ngay sau cùng một câu SQL trong SQL buffer | Bỏ dấu `/` không cần thiết sau SQL đã chạy |
| `ORA-00911` hoặc lỗi cú pháp khi gọi JDBC | Gửi dấu `;`, `/` hoặc lệnh client không thích hợp qua driver | Chỉ gửi SQL/PLSQL thực sự, bỏ terminator thuộc script |
| `SET`, `DEFINE` bị báo sai cú pháp trong editor/JDBC | Công cụ không chạy chế độ SQL\*Plus-compatible | Chọn chế độ script thích hợp hoặc chuyển sang API công cụ đó hỗ trợ |
| Script con dùng sai giá trị `&name` | Biến thay thế cũ vẫn tồn tại trong phiên | Đặt tên rõ ràng; `DEFINE` đầu file, `UNDEFINE` cuối file |
| `PRINT b_x` không có giá trị như mong muốn | Chưa gán bind, hoặc gán trong phiên/công cụ khác | Kiểm tra `VARIABLE`, phần `BEGIN...END;/` và kết nối hiện hành |
| Có nhiều dòng `old`/`new` trong log | `SET VERIFY ON` | Đổi sang `SET VERIFY OFF` khi không cần hiển thị giá trị thay thế |

### Quy trình chẩn đoán nhanh

Khi script thất bại, hãy hỏi theo thứ tự:

1. **Lệnh đang chạy ở đâu?** SQL\*Plus, SQLcl, SQL Developer Run Script, JDBC hay migration tool?
2. **Đây là SQL/PLSQL hay lệnh client?** `SET`, `DEFINE`, `VARIABLE`, `PRINT` phải do client tương ứng hiểu.
3. **Giá trị được đưa vào bằng cách nào?** `&`/`&&` là thay văn bản; `:` hoặc `?` là cơ chế bind phù hợp với client/driver.
4. **Câu lệnh kết thúc đúng kiểu chưa?** SQL thông thường dùng `;` trong script; PL/SQL dùng `END;` và `/` riêng dòng khi cần.
5. **Có trạng thái còn sót từ script trước không?** Kiểm tra `DEFINE`, biến bind và các tùy chọn `SET` trong phiên hiện tại.

## 13. Bài thực hành có hướng dẫn

Các ví dụ phần này có thể thử trong SQL\*Plus/SQLcl sau khi kết nối bằng tài khoản có quyền `SELECT FROM DUAL` và `USER_TABLES`; không yêu cầu tạo hay xóa dữ liệu.

### Bài 1: Quan sát sự khác nhau giữa biến thay thế và bind

```sql
SET VERIFY ON

DEFINE p_score = 90
SELECT &p_score AS score_from_text FROM dual;

VARIABLE b_score NUMBER
BEGIN
    :b_score := 90;
END;
/
SELECT :b_score AS score_from_bind FROM dual;

UNDEFINE p_score
SET VERIFY OFF
```

Quan sát: ở câu dùng `&p_score`, khi bật `VERIFY`, client có thể hiển thị bản `old`/`new`; ở câu dùng `:b_score`, biến bind không bị thay thô bằng văn bản `90` trong dòng SQL như vậy. Dù kết quả truy vấn giống nhau, cơ chế truyền giá trị khác nhau.

### Bài 2: Xử lý ký tự `&` trong chuỗi

```sql
SET DEFINE OFF
SELECT 'Sales & Marketing' AS team_name FROM dual;
SET DEFINE ON
```

Tự giải thích vì sao chỉ cần đổi chế độ tiền xử lý của client, không phải tạo thêm hàm SQL trong Oracle. Hãy nhớ bật lại `DEFINE` nếu các phần script sau còn dùng `&name`.

### Bài 3: Hiểu phạm vi của biến PL/SQL và bind

```sql
SET SERVEROUTPUT ON
VARIABLE b_total NUMBER

DECLARE
    v_first NUMBER := 12;
    v_second NUMBER := 30;
BEGIN
    :b_total := v_first + v_second;
    DBMS_OUTPUT.PUT_LINE('Ket qua trong block: ' || :b_total);
END;
/

PRINT b_total
SELECT :b_total AS result_after_block FROM dual;
```

`v_first` và `v_second` là biến chỉ tồn tại trong block; `:b_total` là biến bind của phiên, tiếp tục được sử dụng sau khi block kết thúc. `DBMS_OUTPUT` và `PRINT` là **hai cách khác nhau** để hiển thị thông tin.

### Bài 4: Chọn terminator thích hợp

Phân loại các đoạn sau trước khi chạy:

```sql
-- A. SQL
SELECT 1 AS n FROM dual;

-- B. PL/SQL
BEGIN
    NULL;
END;
/

-- C. Lenh client
PROMPT Script done
```

Đáp án: A dùng `;` để client thực thi SQL; B dùng `;` trong PL/SQL và `/` riêng dòng để chạy block; C là lệnh client hoàn tất bằng xuống dòng. Không thêm `/` sau A chỉ vì B có `/`.

### Bài 5: Viết script có thể chạy lại trong cùng phiên

Yêu cầu: đặt nhãn báo cáo bằng `DEFINE`, đếm bảng của schema bằng biến bind, in kết quả và dọn trạng thái sau khi chạy. Có thể tham khảo cấu trúc:

```sql
SET VERIFY OFF
DEFINE p_report_name = SCHEMA_REPORT
VARIABLE b_count NUMBER

BEGIN
    SELECT COUNT(*) INTO :b_count FROM user_tables;
END;
/

SELECT '&p_report_name' AS report_name,
       :b_count AS table_count
FROM dual;

UNDEFINE p_report_name
```

Chạy lại lần thứ hai trong cùng phiên và xem script có tự đặt nhãn rõ ràng, không yêu cầu nhập `p_report_name` từ phiên trước hay không.

## 14. Một số quy ước giúp script dễ vận hành

- **Ghi rõ công cụ mục tiêu** ở đầu file, ví dụ `-- Chay bang SQL*Plus/SQLcl`, vì các lệnh client và terminator phụ thuộc công cụ.
- **Đặt tên biến dễ nhận diện**: `p_...` cho substitution parameter, `b_...` cho bind, `v_...` cho biến PL/SQL cục bộ. Đây là quy ước gợi ý, không phải cú pháp bắt buộc của Oracle.
- **Ưu tiên bind cho dữ liệu**, kể cả khi dùng script để truy vấn lặp lại với nhiều giá trị khác nhau.
- **Dọn biến thay thế bằng `UNDEFINE`**, và khôi phục các tùy chọn `SET` đã thay đổi để giảm tác động đến script chạy sau.
- **Đặt `/` đúng vị trí** trong các khối PL/SQL. Rà soát đặc biệt những script DML trước khi thêm dấu `/` vì có thể làm chạy lại lệnh.
- **Dùng `SET SERVEROUTPUT ON` khi cần xem `DBMS_OUTPUT`**, nhưng không mặc định log ứng dụng Java tự nhận được nội dung này.
- **Tránh đưa mật khẩu, token hay bí mật vào `DEFINE`, `PROMPT`, log hoặc file script**. Dùng cơ chế quản lý secret và nhập liệu an toàn phù hợp công cụ vận hành.
- **Phân biệt script kiểm tra với script thay đổi dữ liệu**; trong script ghi, xác định rõ quyền, ranh giới transaction, lỗi và cơ chế rollback/commit.

## 15. Kết luận

Trong hệ sinh thái công cụ Oracle, ba quy tắc sau giúp bạn đọc và viết script chính xác:

1. **`&name` và `&&name` là thay thế văn bản của công cụ script**: hữu ích cho tham số vận hành, nhưng không thay thế được bind an toàn cho dữ liệu đầu vào.
2. **`:name` là biến bind khi công cụ hỗ trợ và cung cấp giá trị**: dữ liệu được truyền với câu lệnh, có kiểu và có thể được SQL/PLSQL sử dụng mà không cần ghép văn bản thủ công. Trong Java/JDBC chuẩn, cơ chế tương ứng thường là `PreparedStatement` với dấu `?`.
3. **`;` và `/` phục vụ các tầng cú pháp khác nhau**: câu SQL thường kết thúc bằng `;` trong SQL\*Plus/SQLcl; PL/SQL chứa các dấu `;` nội bộ và thường cần `/` đứng riêng để client thực thi toàn bộ block hoặc định nghĩa chương trình.

Khi đã biết **ai xử lý biến**, **giá trị được truyền vào ở giai đoạn nào** và **lệnh được thực thi lúc gặp dấu nào**, bạn sẽ tự tin hơn khi chạy file `.sql`, chuyển giữa SQL\*Plus/SQLcl và ứng dụng Java, đồng thời tránh nhiều lỗi phát sinh từ việc sao chép câu lệnh giữa các công cụ có cách thực thi khác nhau.
