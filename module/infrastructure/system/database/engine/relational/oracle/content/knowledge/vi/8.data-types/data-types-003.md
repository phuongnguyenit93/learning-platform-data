# BINARY_FLOAT, BINARY_DOUBLE và những giá trị số đặc biệt trong Oracle Database

Khi lưu số đo cảm biến, kết quả tính toán khoa học hoặc các đại lượng có biên độ rất lớn, Oracle Database cung cấp hai kiểu dữ liệu dấu phẩy động nhị phân: **`BINARY_FLOAT`** và **`BINARY_DOUBLE`**. Chúng có đặc tính khác `NUMBER` về **cách biểu diễn**, **độ chính xác**, **phạm vi giá trị** và **hành vi khi phát sinh các giá trị đặc biệt** như *NaN* hoặc dương/vô cực âm.

Một câu hỏi rất thực tế: *Vì sao truy vấn lọc `reading > 100` lại có thể lấy cả một dòng chứa NaN?* Trong SQL của Oracle, **NaN được coi là lớn hơn mọi giá trị số khác, kể cả dương vô cực, và bằng chính nó**. Điều này khác với ngữ nghĩa so sánh NaN thường thấy trong Java, Python và cách hiểu thuần IEEE 754. Vì vậy, việc dùng các kiểu số này cần đi kèm quy tắc kiểm tra và làm sạch dữ liệu rõ ràng.

Bài học thuộc nhóm **Kiểu dữ liệu** của Oracle Database quan hệ; các ví dụ dùng SQL phổ biến trong Oracle Database 19c trở lên và có thể chạy trong SQL*Plus, SQLcl hoặc công cụ SQL khác khi có quyền phù hợp. Kết quả hiển thị số cụ thể có thể thay đổi tùy định dạng của công cụ, thiết lập NLS và phần mềm client.

## 1. Phân biệt NUMBER, BINARY_FLOAT và BINARY_DOUBLE

### 1.1. Bảng so sánh

| Đặc điểm | `NUMBER` | `BINARY_FLOAT` | `BINARY_DOUBLE` |
| --- | --- | --- | --- |
| Kiểu biểu diễn | Số theo độ chính xác **thập phân** của Oracle | Số thực dấu phẩy động **nhị phân** 32 bit | Số thực dấu phẩy động **nhị phân** 64 bit |
| Dung lượng giá trị | Dài biến thiên theo cách lưu trữ Oracle, tối đa khoảng 22 byte | **4 byte** | **8 byte** |
| Độ chính xác | Tối đa khoảng **38 chữ số thập phân** có nghĩa | Khoảng **6–9 chữ số thập phân** khi chuyển đổi/biểu diễn; thường coi khoảng 7 chữ số có nghĩa | Khoảng **15–17 chữ số thập phân** khi chuyển đổi/biểu diễn; thường coi khoảng 15–16 chữ số có nghĩa |
| Số lớn nhất hữu hạn (xấp xỉ) | Nhỏ hơn `1E126` | `3.4028235E38` | `1.7976931348623157E308` |
| Số dương nhỏ nhất dạng **normal** (xấp xỉ) | Khoảng `1E-130` theo miền giá trị NUMBER | `1.17549435E-38` | `2.2250738585072014E-308` |
| Hỗ trợ giá trị đặc biệt | Không chứa NaN hay ±Infinity như giá trị NUMBER | Có **NaN**, **+Infinity**, **-Infinity** | Có **NaN**, **+Infinity**, **-Infinity** |
| Phép tính có phần thập phân | Theo độ chính xác thập phân của NUMBER | Xấp xỉ theo nhị phân; có làm tròn | Xấp xỉ theo nhị phân; có làm tròn |
| Ứng dụng phù hợp | Tiền tệ, kế toán, số thập phân cần chính xác, định danh số | Số đo/mô phỏng khi độ chính xác single đủ | Tính toán khoa học, thống kê, số đo cần độ chính xác/range lớn hơn |

**Chú ý:** khoảng chính xác 6–9 và 15–17 chữ số là đặc trưng biểu diễn/chuyển đổi của IEEE 754, không có nghĩa mọi giá trị thập phân với từng ấy chữ số đều được lưu chính xác. Khi phải bảo đảm phép tính tiền tệ theo chữ số thập phân, thường chọn `NUMBER(p,s)`, chẳng hạn `NUMBER(18,2)`.

### 1.2. `BINARY_FLOAT` và `BINARY_DOUBLE` là hai kiểu thực sự riêng

Oracle định nghĩa:

- `BINARY_FLOAT` dùng 32 bit, tương đương cách biểu diễn *single precision* IEEE 754. Trong 32 bit có **1 bit dấu**, **8 bit số mũ** và **23 bit lưu fraction** (độ chính xác significand hiệu dụng 24 bit).
- `BINARY_DOUBLE` dùng 64 bit, tương đương *double precision*. Trong 64 bit có **1 bit dấu**, **11 bit số mũ** và **52 bit lưu fraction** (độ chính xác significand hiệu dụng 53 bit).

Mô hình khái niệm:

```text
BINARY_FLOAT  (32 bit)
+------+--------------+--------------------------+
| dấu  | số mũ (8 bit)| fraction lưu (23 bit)    |
+------+--------------+--------------------------+

BINARY_DOUBLE (64 bit)
+------+---------------+--------------------------------+
| dấu  | số mũ (11 bit)| fraction lưu (52 bit)          |
+------+---------------+--------------------------------+
```

Số bit nhiều hơn giúp `BINARY_DOUBLE` lưu được **nhiều chữ số có nghĩa hơn** và biểu diễn được **miền giá trị lớn hơn**. Tuy nhiên, cả hai đều là kiểu **xấp xỉ**; nhiều số thập phân quen thuộc vẫn không có biểu diễn nhị phân hữu hạn.

### 1.3. Đừng nhầm Oracle FLOAT với BINARY_FLOAT

Trong Oracle SQL, **`FLOAT`** là một subtype của **`NUMBER`**, có độ chính xác khai báo theo đơn vị bit trong cú pháp SQL, và không đồng nghĩa với kiểu 32-bit IEEE 754.

Ví dụ:

```sql
CREATE TABLE numeric_type_examples (
    exact_value  NUMBER(18, 4),
    legacy_float FLOAT(126),
    float32_val  BINARY_FLOAT,
    float64_val  BINARY_DOUBLE
);
```

Ở đây `legacy_float` **không** trở thành một cột `BINARY_FLOAT`. Nếu muốn dùng số nhị phân IEEE 754, hãy khai báo rõ `BINARY_FLOAT` hoặc `BINARY_DOUBLE`.

## 2. Vì sao số thập phân 0.1 không luôn chính xác?

### 2.1. Cơ chế nhị phân

Trong hệ thập phân:

```text
0.1 = 1 / 10
```

Số này được biểu diễn đúng bằng một chữ số sau dấu phẩy. Nhưng trong hệ nhị phân, `0.1` có khai triển vô hạn; một kiểu 32-bit/64-bit chỉ lưu được số lượng bit hữu hạn và phải **làm tròn** đến giá trị nhị phân gần nhất.

Hệ quả:

- Giá trị lưu là xấp xỉ của số thập phân đã nhập.
- Hai cách tính ra kết quả toán học giống nhau có thể cho các chuỗi bit khác nhau.
- Kiểm tra bằng dấu `=` có thể không phù hợp nếu mục tiêu là “gần bằng” trong một sai số cho phép.

Ví dụ:

```sql
SELECT
    0.1 + 0.2                    AS decimal_expression,
    0.1d + 0.2d                  AS double_expression,
    TO_BINARY_FLOAT(0.1)        AS float_expression,
    TO_BINARY_DOUBLE(0.1)       AS converted_double
FROM dual;
```

Các biểu thức có chứa hậu tố `d` hoặc chuyển đổi `TO_BINARY_DOUBLE` sử dụng kiểu dấu phẩy động nhị phân. Công cụ có thể làm tròn số khi **hiển thị**, nên hai cột trông giống nhau không chứng minh chúng có cùng biểu diễn nội bộ.

### 2.2. Độ chính xác khác độ lớn miền giá trị

`BINARY_DOUBLE` có miền biểu diễn lớn hơn rất nhiều `NUMBER` về **số mũ**, nhưng chỉ có khoảng 15–17 chữ số thập phân để biểu diễn giá trị theo độ chính xác nhị phân.

Ví dụ về các số nguyên lớn:

```sql
SELECT
    CASE
      WHEN TO_BINARY_DOUBLE(9007199254740992) =
           TO_BINARY_DOUBLE(9007199254740993)
      THEN 'EQUAL AFTER CONVERSION'
      ELSE 'DIFFERENT'
    END AS double_comparison
FROM dual;
```

Các số 9.007.199.254.740.992 và 9.007.199.254.740.993 khác nhau chính xác dưới dạng `NUMBER`. Nhưng tại vùng này, độ phân giải của double 53-bit không đủ để biểu diễn mọi số nguyên liên tiếp, nên chúng có thể làm tròn về cùng một giá trị nhị phân. Đây là lý do không nên dùng `BINARY_DOUBLE` để lưu các định danh số nguyên cực lớn cần so khớp tuyệt đối.

### 2.3. Normal, subnormal, underflow

Bên cạnh các số *normal*, IEEE 754 còn có các số **subnormal** rất gần 0, có độ chính xác tương đối thấp hơn. Với `BINARY_FLOAT`, mức dương subnormal nhỏ nhất khoảng `1.40129846E-45`; với `BINARY_DOUBLE` khoảng `4.9406564584124654E-324`.

Một kết quả quá nhỏ để biểu diễn trong định dạng đích có thể **underflow về 0**. Ngược lại, kết quả quá lớn để biểu diễn hữu hạn có thể trở thành **Infinity** trong phép toán dấu phẩy động nhị phân.

Vì vậy không nên hiểu “dải biểu diễn rất lớn” là “mọi phép toán đều giữ đủ chữ số”. Miền số và độ chính xác là hai giới hạn khác nhau.

## 3. Khai báo cột, literal và chuyển đổi kiểu

### 3.1. Tạo bảng với hai kiểu số nhị phân

```sql
CREATE TABLE sensor_readings (
    reading_id   NUMBER(12) PRIMARY KEY,
    sensor_code  VARCHAR2(30) NOT NULL,
    raw_value    BINARY_FLOAT,
    refined_value BINARY_DOUBLE,
    recorded_at  TIMESTAMP DEFAULT SYSTIMESTAMP
);
```

Trong ví dụ này:

- `raw_value` chứa số nhị phân 32-bit.
- `refined_value` chứa số nhị phân 64-bit.
- Hai cột có thể lưu số hữu hạn, NaN, ±Infinity hoặc `NULL` nếu không có `NOT NULL`/`CHECK` ràng buộc.
- `recorded_at` dùng `TIMESTAMP` để ghi nhận thời điểm, không liên quan trực tiếp đến phạm vi số thực.

Bảng này chỉ minh họa schema. Khi thiết kế thực tế còn phải xét nguồn dữ liệu, chuẩn hóa đơn vị đo, quy tắc kiểm tra ngoại lệ và yêu cầu nghiệp vụ.

### 3.2. Literal `f/F` và `d/D`

Oracle hỗ trợ hậu tố trực tiếp trong numeric literal:

| Cú pháp | Kiểu số |
| --- | --- |
| `25`, `0.5`, `1.25e3` | `NUMBER` theo cú pháp literal số thông thường |
| `25f`, `0.5F`, `1.25e3f` | `BINARY_FLOAT` |
| `25d`, `0.5D`, `1.25e3d` | `BINARY_DOUBLE` |

Ví dụ:

```sql
SELECT
    12.5       AS number_value,
    12.5f      AS binary_float_value,
    12.5d      AS binary_double_value
FROM dual;
```

**Không dùng dấu ngoặc kép cho hậu tố.** `12.5d` là literal số có kiểu nhị phân; `'12.5d'` là chuỗi ký tự và không mang cùng ý nghĩa.

Với numeric literal viết trực tiếp trong SQL, dấu chấm thường được dùng làm ký hiệu thập phân theo cú pháp SQL. Khi chuyển từ **chuỗi** sang số, quy tắc NLS có thể ảnh hưởng. Đối với đầu vào từ bên ngoài, dùng bind variables/driver phù hợp thay vì ghép số hoặc chuỗi vào câu SQL.

### 3.3. Các hàm chuyển đổi

Các hàm thường gặp:

- `TO_BINARY_FLOAT(expr)`: chuyển biểu thức sang `BINARY_FLOAT`.
- `TO_BINARY_DOUBLE(expr)`: chuyển biểu thức sang `BINARY_DOUBLE`.
- `TO_NUMBER(expr)`: chuyển sang `NUMBER` khi giá trị có thể chuyển đổi và được hỗ trợ.
- `CAST(expr AS BINARY_FLOAT)` hoặc `CAST(expr AS BINARY_DOUBLE)`: khai báo kiểu đích rõ ràng.

Ví dụ:

```sql
SELECT
    TO_BINARY_FLOAT(3.125)        AS as_float32,
    TO_BINARY_DOUBLE(3.125)       AS as_float64,
    CAST(3.125 AS BINARY_DOUBLE)  AS cast_float64
FROM dual;
```

Số `3.125 = 25/8` có biểu diễn hữu hạn trong hệ nhị phân nên được giữ chính xác ở cả hai kiểu trong phạm vi này. Các số như `0.1` lại phải làm tròn.

**Chuyển đổi không tự khôi phục độ chính xác đã mất.** Nếu một số chính xác được làm tròn khi ghi vào `BINARY_FLOAT`, việc chuyển sau đó sang `BINARY_DOUBLE` chỉ biểu diễn chính xác hơn **giá trị đã bị làm tròn**, không phục hồi chữ số thập phân ban đầu.

### 3.4. Numeric precedence khi trộn các kiểu số

Oracle áp dụng thứ tự ưu tiên kiểu số (*numeric precedence*):

```text
BINARY_DOUBLE
      >
BINARY_FLOAT
      >
NUMBER
```

Với các phép toán/hàm hỗ trợ những kiểu số này:

- Nếu có toán hạng `BINARY_DOUBLE`, Oracle thường chuyển toán hạng còn lại sang `BINARY_DOUBLE` trước khi tính.
- Nếu không có `BINARY_DOUBLE` nhưng có `BINARY_FLOAT`, Oracle thường chuyển sang `BINARY_FLOAT`.
- Nếu tất cả là `NUMBER`, phép tính dùng ngữ nghĩa của `NUMBER`.

Ví dụ:

```sql
SELECT
    1 + 0.5d         AS result_using_double,
    1 + 0.5f         AS result_using_float,
    1 + 0.5          AS result_using_number
FROM dual;
```

Quy tắc này có nghĩa **một toán hạng double có thể khiến biểu thức NUMBER chuyển sang biểu diễn nhị phân**, tạo ra kết quả làm tròn mà người viết SQL không dự tính.

Ngoài ra, từng hàm SQL có quy tắc kiểu dữ liệu riêng; luôn tra cứu tài liệu của hàm khi kết quả phụ thuộc kiểu trả về.

## 4. Những giá trị số đặc biệt: NaN và Infinity

### 4.1. NaN là gì?

**NaN** viết tắt của *Not a Number*. Đây là một **giá trị hợp lệ của kiểu floating-point**, thường biểu diễn kết quả của phép toán không xác định, chẳng hạn một phép toán floating-point dạng `0.0 / 0.0` theo ngữ nghĩa IEEE 754.

NaN:

- Là **giá trị** được lưu trong `BINARY_FLOAT`/`BINARY_DOUBLE`, không phải `NULL`.
- Không phải một con số hữu hạn để đo lường thông thường.
- Có thể lan truyền qua các phép toán khác.
- Có quy tắc **so sánh và sắp xếp riêng** trong Oracle SQL.

Trong Oracle, các bit pattern NaN được chuẩn hóa theo kiểu dữ liệu; Oracle không cung cấp cách sử dụng riêng signaling/quiet NaN như những chế độ ngoại lệ tùy chỉnh trong phép tính SQL thông thường.

### 4.2. Infinity là gì?

**Infinity** có hai hướng:

- **`+Infinity`**, ký hiệu `+INF`: dương vô cực.
- **`-Infinity`**, ký hiệu `-INF`: âm vô cực.

Với các phép toán dấu phẩy động nhị phân, kết quả có thể trở thành Infinity khi vượt dải hữu hạn hoặc gặp phép chia cho 0 trong những tình huống được định nghĩa. Infinity lớn hơn mọi giá trị hữu hạn dương hoặc âm theo thứ tự tương ứng, nhưng **NaN đứng cao hơn +Infinity** trong phép so sánh theo Oracle SQL.

**Infinity không phải một số thập phân rất lớn.** Nếu dữ liệu “vô cực” xuất hiện trong ứng dụng kinh doanh, cần xác định nó mang ý nghĩa nghiệp vụ gì và có nên chấp nhận hay coi là trạng thái lỗi.

### 4.3. Bốn hằng số đặc biệt Oracle cung cấp

| Hằng số Oracle | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `BINARY_FLOAT_NAN` | `BINARY_FLOAT` | NaN độ chính xác đơn |
| `BINARY_FLOAT_INFINITY` | `BINARY_FLOAT` | Dương vô cực độ chính xác đơn |
| `BINARY_DOUBLE_NAN` | `BINARY_DOUBLE` | NaN độ chính xác kép |
| `BINARY_DOUBLE_INFINITY` | `BINARY_DOUBLE` | Dương vô cực độ chính xác kép |

Để biểu diễn âm vô cực, dùng toán tử âm trên hằng số:

```sql
SELECT
    BINARY_FLOAT_INFINITY    AS positive_float_infinity,
   -BINARY_FLOAT_INFINITY    AS negative_float_infinity,
    BINARY_DOUBLE_NAN        AS double_nan,
   -BINARY_DOUBLE_INFINITY   AS negative_double_infinity
FROM dual;
```

Không có nhu cầu đặt tên riêng cho “negative NaN”: dấu của NaN không có nghĩa giá trị số theo chuẩn ngữ nghĩa mà Oracle cung cấp.

### 4.4. Số 0 và âm 0

IEEE 754 có thể biểu diễn `+0` và `-0` ở mức bit. Trong các kiểu dấu phẩy động Oracle, **`-0` được chuẩn hóa thành `+0`**, và phép so sánh bỏ qua dấu của số 0.

Do đó, không nên sử dụng dấu của zero làm trạng thái nghiệp vụ khác nhau trong một cột `BINARY_FLOAT` hoặc `BINARY_DOUBLE`. Nếu ứng dụng cần phân biệt hai trạng thái, hãy dùng cột trạng thái riêng hoặc kiểu dữ liệu mô tả rõ ràng.

### 4.5. NaN và Infinity xuất hiện từ phép toán như thế nào?

Trong các phép toán floating-point nhị phân theo ngữ nghĩa Oracle, một số tình huống thường dẫn đến:

| Tình huống | Kết quả điển hình |
| --- | --- |
| Vượt miền số hữu hạn (*overflow*) | `+INF` hoặc `-INF` |
| Kết quả quá nhỏ để biểu diễn (*underflow*) | Giá trị subnormal hoặc `0` tùy độ lớn và làm tròn |
| Phép toán không xác định (*invalid operation*) | `NaN` |
| Chia floating-point cho 0 | `+INF`, `-INF` hoặc `NaN` tùy toán hạng |
| Kết quả không thể biểu diễn chính xác (*inexact*) | Một số hữu hạn được làm tròn |

Oracle sử dụng chế độ xử lý ngoại lệ floating-point mặc định, không phát sinh các **IEEE 754 floating-point exceptions** tùy chỉnh như một số hệ thống tính toán. Tuy nhiên, điều này **không có nghĩa mọi biểu thức SQL đều không phát sinh lỗi**: phép toán trên `NUMBER`, chuyển đổi kiểu, ràng buộc dữ liệu hoặc cú pháp sai vẫn có thể đưa ra Oracle error.

Ví dụ, biểu thức thuần `NUMBER` chia cho 0 có thể phát sinh `ORA-01476: divisor is equal to zero`; đây không phải cùng ngữ nghĩa với phép chia dành cho native floating-point.

## 5. Phân biệt NaN, Infinity và NULL

Ba trạng thái này **hoàn toàn khác nhau**:

| Trạng thái | Bản chất | `IS NULL` | Có thể xuất hiện trong `BINARY_DOUBLE`? |
| --- | --- | --- | --- |
| Giá trị hữu hạn | Số thực xấp xỉ có thể dùng tính toán | FALSE | Có |
| `NaN` | Giá trị floating-point không phải số | FALSE | Có |
| `+INF` hoặc `-INF` | Giá trị vô cực floating-point | FALSE | Có |
| `NULL` | Không có giá trị SQL | TRUE | Có nếu cột cho phép NULL |

Một cột `NOT NULL` **vẫn có thể chứa NaN hoặc Infinity** nếu không có ràng buộc khác. Tương tự, hàm `COUNT(column)` bỏ qua `NULL` nhưng có thể đếm cả NaN và Infinity vì chúng là các giá trị không-null.

### 5.1. Các điều kiện chuyên dụng

Oracle cung cấp các điều kiện:

- `expression IS NAN`: giá trị là NaN.
- `expression IS NOT NAN`: giá trị không phải NaN.
- `expression IS INFINITE`: là dương hoặc âm vô cực.
- `expression IS NOT INFINITE`: không phải dương hoặc âm vô cực.

Ví dụ:

```sql
SELECT reading_id, refined_value
FROM   sensor_readings
WHERE  refined_value IS NAN;

SELECT reading_id, refined_value
FROM   sensor_readings
WHERE  refined_value IS INFINITE;

SELECT reading_id, refined_value
FROM   sensor_readings
WHERE  refined_value IS NOT NULL
AND    refined_value IS NOT NAN
AND    refined_value IS NOT INFINITE;
```

Truy vấn cuối chọn các giá trị **hữu hạn và không-null**, phù hợp làm tập đầu vào cho nhiều công thức thống kê.

**Chú ý cú pháp:** `IS NAN` và `IS INFINITE` là điều kiện SQL của Oracle, không phải tên hàm dạng `IS_NAN(value)`. Khi viết SQL, dùng cú pháp được database hỗ trợ; ở phía Java hoặc Python có tên hàm và quy tắc khác.

### 5.2. CASE để phân loại dữ liệu

```sql
SELECT
    reading_id,
    CASE
      WHEN refined_value IS NULL THEN 'NULL'
      WHEN refined_value IS NAN THEN 'NaN'
      WHEN refined_value = BINARY_DOUBLE_INFINITY THEN '+Infinity'
      WHEN refined_value = -BINARY_DOUBLE_INFINITY THEN '-Infinity'
      ELSE 'FINITE'
    END AS value_class
FROM sensor_readings
ORDER BY reading_id;
```

Điều kiện `IS NULL` được kiểm tra riêng. Nhánh cuối `ELSE 'FINITE'` chỉ còn các trường hợp hữu hạn khi những nhánh trước đã loại NaN/±Infinity.

Với ứng dụng thực tế, có thể phân loại bằng `IS INFINITE` trước rồi phân dấu, hoặc dùng cấu trúc `CASE` tương đương để dễ đọc hơn.

## 6. Quy tắc so sánh NaN của Oracle có gì khác IEEE 754 thông thường?

### 6.1. Thứ tự so sánh Oracle áp dụng

Trong Oracle Database SQL, trật tự của **các giá trị không-null** là:

```text
-Infinity  <  số hữu hạn âm  <  0  <  số hữu hạn dương  <  +Infinity  <  NaN
```

Đặc biệt:

- `BINARY_DOUBLE_NAN > BINARY_DOUBLE_INFINITY` là **TRUE** trong Oracle.
- `BINARY_DOUBLE_NAN = BINARY_DOUBLE_NAN` là **TRUE** trong Oracle.
- Các NaN cùng được coi bằng nhau theo ngữ nghĩa so sánh của Oracle.

Ví dụ xác nhận bằng `CASE`:

```sql
SELECT
    CASE
      WHEN BINARY_DOUBLE_NAN = BINARY_DOUBLE_NAN
      THEN 'TRUE' ELSE 'FALSE'
    END AS nan_equals_nan,
    CASE
      WHEN BINARY_DOUBLE_NAN > BINARY_DOUBLE_INFINITY
      THEN 'TRUE' ELSE 'FALSE'
    END AS nan_above_infinity
FROM dual;
```

Đây là điểm quan trọng khi chuyển code giữa SQL và Java/Python. Trong phép so sánh kiểu IEEE 754 thông dụng ở Java, `Double.NaN == Double.NaN` là **false**, nhưng Oracle SQL lại thiết lập thứ tự để NaN lớn nhất và bằng chính nó.

**Đừng áp dụng quy tắc của ngôn ngữ ứng dụng để suy diễn kết quả so sánh trong Oracle SQL.**

### 6.2. Lọc bằng >, >= có thể vô tình lấy NaN

Xét câu SQL:

```sql
SELECT reading_id, refined_value
FROM   sensor_readings
WHERE  refined_value > 100d;
```

Nếu dữ liệu có NaN, Oracle có thể đưa nó vào kết quả vì **NaN lớn hơn mọi số hữu hạn**, bao gồm 100. Câu SQL này không đủ để diễn đạt “các số đo hợp lệ lớn hơn 100”.

Cách viết an toàn hơn khi nghiệp vụ chỉ chấp nhận số hữu hạn:

```sql
SELECT reading_id, refined_value
FROM   sensor_readings
WHERE  refined_value IS NOT NULL
AND    refined_value IS NOT NAN
AND    refined_value IS NOT INFINITE
AND    refined_value > 100d;
```

Tương tự, khi tìm `MAX` hoặc báo cáo top-N, NaN có thể làm sai cách hiểu kết quả nếu không lọc từ trước.

### 6.3. ORDER BY và NULL

Ví dụ:

```sql
SELECT reading_id, refined_value
FROM   sensor_readings
ORDER BY refined_value ASC NULLS LAST;
```

Trong các giá trị không-null, Oracle sắp **NaN sau +Infinity**. `NULL` có quy tắc sắp xếp riêng và có thể được đặt cuối hoặc đầu bằng `NULLS LAST`/`NULLS FIRST`.

Khi sắp xếp dữ liệu cảm biến, nên quyết định rõ:

1. Có loại bỏ NaN/Infinity không?
2. Có cần hiển thị các giá trị ngoại lệ thành một nhóm riêng không?
3. `NULL` được hiểu là “không ghi nhận được dữ liệu” hay “không áp dụng”?

Không nên chỉ dựa vào `ORDER BY reading DESC` để suy ra top-N hợp lệ nếu cột có thể chứa những giá trị đặc biệt.

### 6.4. NaN không phải NULL trong logic ba giá trị

SQL sử dụng các kết quả điều kiện **TRUE**, **FALSE**, **UNKNOWN** trong ngữ cảnh liên quan đến `NULL`. Ví dụ:

```sql
SELECT CASE
         WHEN CAST(NULL AS BINARY_DOUBLE) =
              CAST(NULL AS BINARY_DOUBLE)
         THEN 'TRUE'
         ELSE 'NOT TRUE'
       END AS null_comparison
FROM dual;
```

So sánh `NULL = NULL` không trả TRUE; vì vậy `CASE` đi vào nhánh `ELSE`. Trái lại, phép so sánh hai NaN theo Oracle SQL có thể trả TRUE.

Do vậy, không dùng `NVL` hoặc `COALESCE` với hy vọng tự động thay thế NaN/Infinity; các hàm đó chủ yếu xử lý **NULL**, không tự biến các giá trị floating-point đặc biệt thành null.

## 7. Phép toán, làm tròn và kiểm tra gần bằng

### 7.1. Sai số làm tròn và phép cộng không kết hợp tuyệt đối

Trong toán học thực:

```text
(a + b) + c = a + (b + c)
```

Nhưng khi lưu và tính trên số thực nhị phân hữu hạn, sai số làm tròn từng bước có thể khiến hai biểu thức cho kết quả khác nhau ở các bit cuối. Điều này đặc biệt dễ thấy khi cộng số cực lớn với số cực nhỏ.

Các nguyên nhân chính:

- Chữ số có nghĩa vượt quá khả năng biểu diễn.
- Thay đổi thứ tự thực hiện phép toán.
- Đổi giữa `BINARY_FLOAT` và `BINARY_DOUBLE`.
- Dùng hàm tổng hợp hoặc parallel execution khiến thứ tự cộng dồn khác nhau.
- Chuyển qua lại giữa số thập phân, driver và binary floating-point.

Không nên viết logic nghiệp vụ yêu cầu **so khớp bit-exact** nếu phép tính dựa vào floating-point xấp xỉ mà không kiểm soát những điều kiện này.

### 7.2. So sánh gần bằng với ngưỡng sai số

Ví dụ muốn xác định hai phép đo hữu hạn gần nhau trong sai số tuyệt đối `1E-9`:

```sql
SELECT reading_id, refined_value
FROM   sensor_readings
WHERE  refined_value IS NOT NULL
AND    refined_value IS NOT NAN
AND    refined_value IS NOT INFINITE
AND    ABS(refined_value - 12.5d) <= 1e-9d;
```

Đây là một **ngưỡng tuyệt đối** phù hợp khi đại lượng được đo và độ lớn của nó đã biết. Với dữ liệu trải rộng nhiều cấp độ, có thể kết hợp ngưỡng tương đối và tuyệt đối:

```sql
-- Mô hình minh họa khi biết tham số expected_value là số hữu hạn.
SELECT reading_id, refined_value
FROM   sensor_readings
WHERE  refined_value IS NOT NULL
AND    refined_value IS NOT NAN
AND    refined_value IS NOT INFINITE
AND    ABS(refined_value - 12.5d)
         <= 1e-9d * GREATEST(1d, ABS(refined_value), ABS(12.5d));
```

Đây **không phải công thức chung cho mọi nghiệp vụ**: cần chọn tolerance theo đơn vị đo, độ chính xác nguồn dữ liệu và mức độ chấp nhận rủi ro. Đặc biệt, công thức dùng `GREATEST` không được truyền NaN/Infinity vào mà không xử lý trước.

### 7.3. ROUND, TRUNC và TO_CHAR không khôi phục số gốc

Các hàm như `ROUND`, `TRUNC` hoặc `TO_CHAR` có thể giúp kiểm soát giá trị hiển thị hay lượng chữ số sau dấu phẩy, nhưng không thể tái tạo chính xác dữ liệu thập phân đã mất khi nhập vào kiểu nhị phân.

Ví dụ, khi một số `NUMBER` được chuyển xuống `BINARY_FLOAT` và bị làm tròn, một lần `CAST` ngược lại sang `NUMBER` không biết chữ số ban đầu đã bị cắt. Muốn giữ dữ liệu gốc, hãy lưu vào một cột có kiểu phù hợp ngay từ đầu hoặc lưu cả giá trị thô và giá trị đã biến đổi theo nhu cầu truy xuất.

### 7.4. Các ngoại lệ có thể ảnh hưởng đến phép tổng hợp

Với dữ liệu floating-point chứa NaN/Infinity:

- `COUNT(value)` đếm các giá trị không-null, bao gồm NaN và Infinity.
- `MIN`, `MAX`, `SUM`, `AVG` có thể nhận kết quả không mong muốn nếu các giá trị đặc biệt được đưa vào phép tính.
- `ORDER BY` có thể đặt NaN ở vị trí cao nhất trong số những giá trị không-null.
- Nhóm/ghép khóa theo số floating-point có thể bị ảnh hưởng bởi sai số biểu diễn và quy tắc so sánh Oracle.

Thực hành tốt là **định nghĩa thế nào là “mẫu hợp lệ”** trước khi tính thống kê. Ví dụ:

```sql
SELECT COUNT(*) AS valid_sample_count,
       AVG(refined_value) AS average_valid_reading,
       MIN(refined_value) AS minimum_valid_reading,
       MAX(refined_value) AS maximum_valid_reading
FROM   sensor_readings
WHERE  refined_value IS NOT NULL
AND    refined_value IS NOT NAN
AND    refined_value IS NOT INFINITE;
```

Nếu Infinity/NaN thực sự mang ý nghĩa nghiệp vụ, hãy lưu và xử lý chúng theo chính sách riêng thay vì âm thầm loại bỏ.

## 8. Thiết kế bảng và kiểm soát dữ liệu đầu vào

### 8.1. Có nên cho phép NaN và Infinity?

Câu trả lời tùy nghiệp vụ:

- **Bài toán khoa học hoặc máy học** có thể cần lưu các kết quả đặc biệt để mô tả phép tính thất bại, không hội tụ hoặc tràn số.
- **Cảm biến/telemetry** có thể coi NaN/Infinity là dữ liệu lỗi, cần đưa vào hàng đợi kiểm tra và ghi nguyên nhân.
- **Tiền tệ, tồn kho, hạn mức tín dụng** thường không nên lưu theo kiểu floating-point; `NUMBER` và ràng buộc phù hợp có ý nghĩa hơn.

Nếu được phép lưu các giá trị đặc biệt, cần xác định rõ hành vi của API, SQL reports, jobs và công cụ BI. Không nên để một trường `BINARY_DOUBLE` nhận mọi giá trị mà toàn bộ hệ thống lại giả định giá trị của nó luôn hữu hạn.

### 8.2. Ví dụ CHECK constraint chỉ chấp nhận số hữu hạn

Nếu một phép đo bắt buộc phải có giá trị hợp lệ và không âm:

```sql
CREATE TABLE quality_measurements (
    measurement_id NUMBER(12) PRIMARY KEY,
    measured_value BINARY_DOUBLE NOT NULL,
    CONSTRAINT chk_quality_value
      CHECK (
        measured_value IS NOT NAN
        AND measured_value IS NOT INFINITE
        AND measured_value >= 0d
      )
);
```

Ràng buộc này thể hiện rõ ba yêu cầu: **không NULL**, **không NaN/Infinity** và **không âm**. Nếu chỉ dùng `CHECK (measured_value >= 0d)`, điều kiện có thể **không chặn NaN**, vì Oracle xếp NaN cao hơn mọi giá trị số trong so sánh.

Nếu dữ liệu có thể thiếu, hãy lựa chọn `NULL` có chủ đích, ghi rõ `NULL` khác “NaN từ phép toán”. Các ràng buộc `CHECK` của SQL cũng cần hiểu về ba trạng thái logic; không mặc định nó thay cho `NOT NULL`.

### 8.3. Khi nào nên lưu thêm trạng thái thay vì đưa NaN vào cột?

Một thiết kế khác là lưu riêng số đo và tình trạng đo:

```sql
CREATE TABLE sensor_samples (
    sample_id        NUMBER(12) PRIMARY KEY,
    measured_value   BINARY_DOUBLE,
    measure_status   VARCHAR2(20) NOT NULL,
    CONSTRAINT chk_sensor_status
      CHECK (measure_status IN ('OK', 'MISSING', 'INVALID', 'OVERFLOW'))
);
```

Ví dụ:

- `OK`: giá trị hữu hạn hợp lệ.
- `MISSING`: không nhận được mẫu; `measured_value` có thể `NULL`.
- `INVALID`: phép đo thất bại.
- `OVERFLOW`: kết quả vượt dải đo.

Thiết kế này cần thêm ràng buộc liên cột nếu muốn bảo đảm nhất quán hoàn toàn, nhưng làm rõ ý nghĩa nghiệp vụ và cho phép SQL reports không phải diễn giải một giá trị đặc biệt theo nhiều cách.

## 9. Làm việc với Java/JDBC

### 9.1. Kiểu tương ứng ở phía Java

Trong Java:

- `float` / `Float` có độ chính xác kiểu 32-bit tương ứng về mặt biểu diễn với `BINARY_FLOAT`.
- `double` / `Double` có độ chính xác 64-bit tương ứng với `BINARY_DOUBLE`.
- `Double.NaN`, `Double.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY` là các giá trị đặc biệt có sẵn.
- `Double.isNaN(value)` và `Double.isInfinite(value)` kiểm tra trạng thái; Java 8 trở lên có `Double.isFinite(value)`.

Tuy nhiên, **quy tắc so sánh NaN trong Java khác Oracle SQL**:

```java
double x = Double.NaN;

System.out.println(x == x);               // false trong Java
System.out.println(Double.isNaN(x));       // true
System.out.println(Double.isInfinite(x));  // false
System.out.println(Double.isFinite(x));    // false
```

Bởi vậy, nếu ứng dụng Java thực hiện filter cho NaN bằng phép `==` còn Oracle thực hiện filter bằng SQL `=`, hành vi có thể khác nhau.

### 9.2. Đọc NULL và NaN riêng trong ResultSet

Khi gọi `ResultSet.getDouble(...)`, giá trị SQL `NULL` được ánh xạ thành `0.0` nếu dùng getter primitive; cần gọi `wasNull()` ngay sau lần đọc đó để phân biệt.

Ví dụ:

```java
try (java.sql.PreparedStatement stmt = connection.prepareStatement(
         "SELECT reading_id, refined_value FROM sensor_readings WHERE reading_id = ?")) {
    stmt.setLong(1, 1001L);

    try (java.sql.ResultSet rs = stmt.executeQuery()) {
        if (rs.next()) {
            double value = rs.getDouble("refined_value");
            boolean sqlNull = rs.wasNull();

            if (sqlNull) {
                System.out.println("Missing (SQL NULL)");
            } else if (Double.isNaN(value)) {
                System.out.println("Not a Number");
            } else if (Double.isInfinite(value)) {
                System.out.println("Infinity");
            } else {
                System.out.println("Finite: " + value);
            }
        }
    }
}
```

Đây là đoạn mã minh họa trong một ứng dụng đã có `connection` JDBC hợp lệ. Khả năng bind/trả về các giá trị đặc biệt còn phụ thuộc phiên bản Oracle JDBC driver và cơ chế truy xuất của ứng dụng; cần thử trên đúng phiên bản triển khai.

### 9.3. Đừng dùng double cho tiền tệ chỉ vì JDBC hỗ trợ

Nếu cột Oracle là `NUMBER(18,2)` và yêu cầu số tiền chính xác, ứng dụng Java nên dùng kiểu phù hợp như `BigDecimal` để giữ ý nghĩa decimal và kiểm soát scale/rounding. Việc chuyển `NUMBER` sang `double` có thể đưa sai số nhị phân vào các phép tính kế toán.

Ngược lại, với số đo khoa học vốn đã là floating-point, `double` là lựa chọn tự nhiên nếu độ chính xác và phạm vi đủ. Quyết định dựa trên **yêu cầu dữ liệu**, không chỉ việc một kiểu chiếm ít byte hơn.

## 10. Thực hành SQL: tạo và tra cứu các giá trị đặc biệt

Các thao tác tạo bảng/ghi dữ liệu chỉ dành cho **schema thực hành** được cấp quyền phù hợp. Nếu đang học trên một PDB, kết nối đúng PDB và tránh chạy trong root của hệ thống sản xuất.

### 10.1. Tạo bảng

```sql
CREATE TABLE lab_floating_values (
    sample_id    NUMBER(3) PRIMARY KEY,
    sample_label VARCHAR2(30) NOT NULL,
    value_f      BINARY_FLOAT,
    value_d      BINARY_DOUBLE
);
```

### 10.2. Chèn số hữu hạn, ±Infinity, NaN và NULL

```sql
INSERT INTO lab_floating_values
    (sample_id, sample_label, value_f, value_d)
VALUES
    (1, 'finite', 0.1f, 0.1d);

INSERT INTO lab_floating_values
    (sample_id, sample_label, value_f, value_d)
VALUES
    (2, 'positive infinity',
     BINARY_FLOAT_INFINITY, BINARY_DOUBLE_INFINITY);

INSERT INTO lab_floating_values
    (sample_id, sample_label, value_f, value_d)
VALUES
    (3, 'negative infinity',
     -BINARY_FLOAT_INFINITY, -BINARY_DOUBLE_INFINITY);

INSERT INTO lab_floating_values
    (sample_id, sample_label, value_f, value_d)
VALUES
    (4, 'NaN', BINARY_FLOAT_NAN, BINARY_DOUBLE_NAN);

INSERT INTO lab_floating_values
    (sample_id, sample_label, value_f, value_d)
VALUES
    (5, 'SQL NULL', NULL, NULL);

INSERT INTO lab_floating_values
    (sample_id, sample_label, value_f, value_d)
VALUES
    (6, 'zero', 0f, 0d);

COMMIT;
```

Các literal được viết rõ kiểu, giúp tránh nhầm phép tính `NUMBER` và phép tính floating-point.

### 10.3. Phân loại từng dòng

```sql
SELECT
    sample_id,
    sample_label,
    CASE
      WHEN value_d IS NULL THEN 'NULL'
      WHEN value_d IS NAN THEN 'NaN'
      WHEN value_d = BINARY_DOUBLE_INFINITY THEN '+Infinity'
      WHEN value_d = -BINARY_DOUBLE_INFINITY THEN '-Infinity'
      ELSE 'FINITE'
    END AS classification
FROM lab_floating_values
ORDER BY sample_id;
```

Kết quả mong đợi về mặt phân loại:

| SAMPLE_ID | SAMPLE_LABEL | CLASSIFICATION |
| ---: | --- | --- |
| 1 | finite | FINITE |
| 2 | positive infinity | +Infinity |
| 3 | negative infinity | -Infinity |
| 4 | NaN | NaN |
| 5 | SQL NULL | NULL |
| 6 | zero | FINITE |

### 10.4. Tìm NaN và Infinity

```sql
-- Chỉ dòng NaN.
SELECT sample_id, sample_label
FROM   lab_floating_values
WHERE  value_d IS NAN;

-- Cả dương và âm vô cực.
SELECT sample_id, sample_label
FROM   lab_floating_values
WHERE  value_d IS INFINITE;

-- Chỉ số hữu hạn, loại cả NULL.
SELECT sample_id, sample_label, value_d
FROM   lab_floating_values
WHERE  value_d IS NOT NULL
AND    value_d IS NOT NAN
AND    value_d IS NOT INFINITE
ORDER BY sample_id;
```

Kỳ vọng các truy vấn trên tương ứng nhận: dòng `4`, các dòng `2` và `3`, và các dòng `1` và `6`.

### 10.5. Quan sát so sánh và sắp xếp

```sql
SELECT sample_id, sample_label, value_d
FROM   lab_floating_values
ORDER BY value_d ASC NULLS LAST;
```

Theo trật tự Oracle SQL, thứ tự khái niệm là:

```text
-Infinity
0
0.1
+Infinity
NaN
NULL
```

Bây giờ xét:

```sql
SELECT sample_id, sample_label
FROM   lab_floating_values
WHERE  value_d > 100d
ORDER  BY sample_id;
```

Một kết quả dễ gây bất ngờ: truy vấn có thể trả **cả dương vô cực và NaN**, vì cả hai đều lớn hơn `100` trong so sánh của Oracle.

Nếu chỉ muốn số đo hữu hạn lớn hơn `100`:

```sql
SELECT sample_id, sample_label
FROM   lab_floating_values
WHERE  value_d > 100d
AND    value_d IS NOT NAN
AND    value_d IS NOT INFINITE;
```

Bộ dữ liệu thực hành này không chứa số hữu hạn nào lớn hơn 100, nên truy vấn thứ hai không có dòng.

### 10.6. COUNT khác COUNT trên cột

```sql
SELECT
    COUNT(*)       AS total_rows,
    COUNT(value_d) AS non_null_values,
    COUNT(CASE
            WHEN value_d IS NOT NULL
             AND value_d IS NOT NAN
             AND value_d IS NOT INFINITE
            THEN 1
          END)     AS finite_values
FROM lab_floating_values;
```

Theo dữ liệu mẫu:

- `TOTAL_ROWS = 6`: tất cả 6 dòng.
- `NON_NULL_VALUES = 5`: loại trừ dòng SQL `NULL`, nhưng **vẫn tính NaN và Infinity**.
- `FINITE_VALUES = 2`: chỉ các dòng `finite` và `zero`.

Đây là ví dụ cho thấy “không null” không đồng nghĩa “số hữu hạn hợp lệ”.

### 10.7. Xóa bảng thực hành khi không còn dùng

```sql
-- CHỈ chạy trên bảng LAB_FLOATING_VALUES do bạn tạo để thực hành.
DROP TABLE lab_floating_values PURGE;
```

Đây là thao tác **phá hủy đối tượng và dữ liệu của bảng**; chỉ thực hiện sau khi xác nhận chính xác bảng thuộc schema học tập, không chứa dữ liệu cần giữ.

## 11. Vấn đề thường gặp khi chuyển dữ liệu hoặc viết báo cáo

### 11.1. “Tôi thấy 0.1 nhưng so sánh lại không bằng”

Công cụ có thể chỉ hiển thị một số chữ số thập phân, che đi sai số nhị phân. Cần hiểu nguồn dữ liệu `NUMBER` hay `BINARY_FLOAT/DOUBLE`, các phép chuyển kiểu, và xác định ngưỡng sai số nếu nghiệp vụ cho phép so sánh gần đúng.

Không nên sửa bằng cách tự động dùng `ROUND(value, 2)` trong mọi câu query; làm tròn theo số chữ số cố định có thể che giấu sai số thực và làm mất thông tin đo lường.

### 11.2. “ORDER BY DESC đưa NaN lên đầu”

Do Oracle xếp NaN cao hơn +Infinity, `ORDER BY value DESC` có thể ưu tiên NaN. Nếu nghiệp vụ muốn giá trị hữu hạn lớn nhất, hãy lọc `IS NOT NAN` và `IS NOT INFINITE` trước rồi mới sắp xếp.

### 11.3. “Cột NOT NULL nhưng dữ liệu vẫn không phải số”

`NOT NULL` chỉ ngăn SQL `NULL`. Nó không chặn NaN/Infinity của cột floating-point. Cần thêm điều kiện kiểm tra hữu hạn trong query hoặc `CHECK` constraint phù hợp.

### 11.4. “Ứng dụng Java nói NaN != NaN, Oracle SQL nói NaN = NaN”

Cả hai có thể đúng trong ngữ cảnh riêng: ngữ nghĩa Java cho `double` theo phép so sánh IEEE 754 thông thường khác quy tắc SQL Oracle dùng để sắp xếp và so sánh NaN. Trên application layer dùng `Double.isNaN`; trên Oracle SQL dùng `IS NAN` khi cần nhận diện trạng thái.

### 11.5. “Số từ NUMBER chuyển sang double làm tròn”

Nếu `NUMBER` có nhiều chữ số có nghĩa hoặc lớn hơn khả năng phân biệt của double, chuyển kiểu sẽ mất độ chính xác. Để lưu số decimal cần chính xác, tiếp tục sử dụng `NUMBER`/`BigDecimal` và tránh chuyển qua `double` không cần thiết.

### 11.6. “BINARY_FLOAT nhanh hơn NUMBER nên luôn nên đổi”

Không nên quyết định chỉ dựa trên giả định tốc độ. Native floating-point có thể phù hợp cho workload số học, nhưng hiệu quả phụ thuộc truy vấn, hardware, khối lượng dữ liệu, index, data access và các phép chuyển kiểu. Nếu đổi kiểu làm mất độ chính xác hoặc vi phạm yêu cầu nghiệp vụ, lợi ích tiềm năng không bù được chi phí sai dữ liệu.

### 11.7. “Đã dùng BINARY_DOUBLE thì không cần kiểm soát overflow”

`BINARY_DOUBLE` có miền số rất lớn nhưng hữu hạn. Overflow vẫn có thể tạo Infinity; phép toán không xác định vẫn có thể tạo NaN. Cần có quy trình phát hiện những giá trị đặc biệt ngay cả trong pipeline dùng double.

## 12. Gợi ý kiểm tra khi vận hành

Khi có nghi ngờ về dữ liệu floating-point, có thể thực hiện các bước đọc-only:

1. **Xác định kiểu cột**:

   ```sql
   SELECT table_name, column_name, data_type
   FROM   user_tab_columns
   WHERE  table_name = 'SENSOR_READINGS'
   ORDER  BY column_id;
   ```

2. **Đếm NaN/Infinity/NULL riêng biệt**:

   ```sql
   SELECT
       COUNT(*) AS total_count,
       COUNT(CASE WHEN refined_value IS NULL THEN 1 END) AS null_count,
       COUNT(CASE WHEN refined_value IS NAN THEN 1 END) AS nan_count,
       COUNT(CASE WHEN refined_value IS INFINITE THEN 1 END) AS infinity_count
   FROM sensor_readings;
   ```

3. **Kiểm tra logic lọc/sắp xếp**: xác định `WHERE value > threshold` có vô tình lấy NaN hay không; kiểm tra `ORDER BY` và thống kê.
4. **Xem các phép chuyển kiểu**: `NUMBER → BINARY_FLOAT → BINARY_DOUBLE` có thể làm mất độ chính xác ngay ở bước đầu.
5. **Đối chiếu ứng dụng**: Java/JDBC có dùng `isNaN`, `isInfinite`, `wasNull` đúng cách không.
6. **Xác định chính sách dữ liệu**: có loại bỏ, lưu riêng, cảnh báo hay quy đổi NaN/Infinity thành trạng thái nghiệp vụ có giải thích?

Khi phát hiện dòng dữ liệu bất thường, không nên xóa hay chuyển thành `NULL` hàng loạt trước khi hiểu vì sao giá trị đặc biệt xuất hiện. Nó có thể là bằng chứng quan trọng về lỗi phép đo, phép chia, overflow hoặc dữ liệu nguồn.

## 13. Bài tập tự kiểm tra

### Câu 1: Kiểu dữ liệu

Một hệ thống cần lưu số tiền có hai chữ số sau dấu thập phân, yêu cầu tổng tiền chính xác khi cộng nhiều giao dịch. Nên chọn `NUMBER(18,2)` hay `BINARY_DOUBLE`? Vì sao?

**Gợi ý:** Thường chọn `NUMBER(18,2)` vì phép tính decimal và scale có ý nghĩa trực tiếp đối với tiền tệ; `BINARY_DOUBLE` là số nhị phân xấp xỉ.

### Câu 2: Phạm vi

Giữa `BINARY_FLOAT` và `BINARY_DOUBLE`, kiểu nào có độ chính xác và phạm vi giá trị lớn hơn? Hai kiểu có thể lưu NaN không?

**Gợi ý:** `BINARY_DOUBLE` cao hơn về cả hai đặc tính; cả hai hỗ trợ NaN/Infinity.

### Câu 3: So sánh NaN

Trong Oracle SQL, điều kiện `BINARY_DOUBLE_NAN = BINARY_DOUBLE_NAN` có TRUE không? So sánh này có giống `Double.NaN == Double.NaN` trong Java không?

**Gợi ý:** Oracle SQL trả TRUE; trong Java, phép `==` với NaN trả false.

### Câu 4: Bộ lọc số lớn

Một cột `READING` kiểu `BINARY_DOUBLE` chứa số 50, 200, NaN và +Infinity. Truy vấn `WHERE reading > 100d` có thể lấy các dòng nào?

**Gợi ý:** 200, +Infinity và NaN theo quy tắc so sánh của Oracle. Muốn chỉ lấy số hữu hạn lớn hơn 100, thêm `IS NOT NAN` và `IS NOT INFINITE`, cùng xử lý `NULL` khi cần.

### Câu 5: NULL

`COUNT(reading)` có bỏ qua NaN không? Nếu số đo chưa từng được thu thập, nên hiểu nó khác NaN thế nào?

**Gợi ý:** `COUNT(column)` chỉ loại các giá trị `NULL`, không tự loại NaN. `NULL` thường là không có giá trị; NaN là giá trị floating-point đặc biệt phát sinh từ phép toán/trạng thái số học.

### Câu 6: Numeric precedence

Phép cộng một `NUMBER` với một `BINARY_DOUBLE` thông thường được xử lý theo kiểu nào? Có rủi ro gì?

**Gợi ý:** `BINARY_DOUBLE` có ưu tiên cao hơn, có thể khiến giá trị `NUMBER` bị chuyển đổi và làm tròn.

### Câu 7: CHECK constraint

`CHECK (reading >= 0d)` đã đủ để bảo đảm mọi dòng lưu số không âm **hữu hạn** chưa?

**Gợi ý:** Chưa, vì NaN được coi lớn hơn mọi số; cần chặn `IS NAN` và `IS INFINITE`, và quyết định có cho phép `NULL` không.

### Câu 8: Java JDBC

Sau `double reading = rs.getDouble("reading")`, giá trị trả về là 0.0. Làm sao biết database lưu thực sự số 0 hay SQL `NULL`?

**Gợi ý:** Gọi `rs.wasNull()` ngay sau khi đọc cột bằng getter primitive.

### Câu 9: Tính toán

Tại sao việc chuyển `NUMBER → BINARY_FLOAT → BINARY_DOUBLE` có thể không phục hồi được giá trị NUMBER ban đầu?

**Gợi ý:** `BINARY_FLOAT` đã làm tròn; `BINARY_DOUBLE` chỉ biểu diễn chính xác hơn kết quả đã làm tròn, không tái tạo dữ liệu mất trước đó.

### Câu 10: Theo dõi chất lượng

Viết truy vấn trả `COUNT(*)` số dòng của bảng `SENSOR_READINGS` có `REFINED_VALUE` là số hữu hạn không-null.

**Gợi ý:**

```sql
SELECT COUNT(*) AS finite_count
FROM   sensor_readings
WHERE  refined_value IS NOT NULL
AND    refined_value IS NOT NAN
AND    refined_value IS NOT INFINITE;
```

## 14. Tài liệu Oracle chính thức

- [Oracle Database SQL Language Reference — Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html): `NUMBER`, `BINARY_FLOAT`, `BINARY_DOUBLE`, phạm vi, độ chính xác và numeric precedence.
- [Oracle Database SQL Language Reference — Literals](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Literals.html): hậu tố `f`/`d` và các hằng số `BINARY_*_NAN`, `BINARY_*_INFINITY`.
- [Oracle Database SQL Language Reference — Floating-Point Conditions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Floating-Point-Conditions.html): các điều kiện `IS NAN`, `IS NOT NAN`, `IS INFINITE` và `IS NOT INFINITE`.
- [Oracle Database SQL Language Reference — Data Type Comparison Rules](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Type-Comparison-Rules.html): thứ tự so sánh và quy tắc Oracle với NaN.
- [Oracle Database Development Guide — Using SQL Data Types in Database Applications](https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/sql-data-types.html): IEEE 754, số subnormal, giá trị đặc biệt, làm tròn và so sánh.
- [Oracle Database SQL Language Reference — TO_BINARY_FLOAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_BINARY_FLOAT.html): chuyển sang kiểu 32-bit.
- [Oracle Database SQL Language Reference — TO_BINARY_DOUBLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_BINARY_DOUBLE.html): chuyển sang kiểu 64-bit.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): cách làm việc với dữ liệu số qua JDBC.

Khi dùng `BINARY_FLOAT` và `BINARY_DOUBLE`, cần nhớ bốn nguyên tắc: **đây là số nhị phân xấp xỉ**, **kiểu dữ liệu quyết định độ chính xác và cách chuyển đổi**, **NaN/Infinity là giá trị có thật chứ không phải NULL**, và **Oracle SQL có quy tắc so sánh NaN riêng**. Chọn kiểu dữ liệu theo yêu cầu nghiệp vụ và đưa các giá trị đặc biệt vào quy tắc kiểm tra từ lúc thiết kế schema, xử lý SQL đến lớp Java/JDBC.
