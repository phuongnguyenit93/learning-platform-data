# Độ chính xác, số chữ số thập phân, làm tròn và tràn số

Một cột lưu số tiền có thể nhận giá trị `123.45` nhưng từ chối `100000.00`; một phép tính `0.1 + 0.2` có thể không bằng chính xác `0.3`; và giá trị `999.995` đôi khi gây lỗi khi đưa vào cột chỉ giữ hai chữ số sau dấu thập phân. Để hiểu những hiện tượng này, cần phân biệt **kiểu số**, **độ chính xác**, **số chữ số thập phân**, **quy tắc làm tròn**, và **phạm vi giá trị có thể biểu diễn**.

Bài học thuộc chủ đề **Database SQL – Kiểu dữ liệu**, tập trung vào số nguyên, số thập phân chính xác và số dấu phẩy động. Ví dụ chạy trực tiếp chủ yếu sử dụng **PostgreSQL**; những điểm có thể khác trong MySQL, SQL Server, Oracle và SQLite được nêu riêng.

## 1. Bốn khái niệm dễ nhầm lẫn

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Precision** (độ chính xác theo số chữ số) | Với `DECIMAL(p,s)`/`NUMERIC(p,s)`, `p` thường là tổng số chữ số thập phân có ý nghĩa được phép trong giá trị | `NUMERIC(7,2)` có `p = 7` |
| **Scale** (số chữ số sau dấu thập phân) | Với số thập phân chính xác, `s` xác định số chữ số được giữ sau dấu thập phân | `NUMERIC(7,2)` có `s = 2` |
| **Rounding** (làm tròn) | Thay một giá trị bằng một giá trị gần đó theo quy tắc xác định | `12.345 → 12.35` khi làm tròn đến hai chữ số theo quy tắc nửa đơn vị rời xa 0 |
| **Overflow** (tràn số) | Giá trị hoặc kết quả phép toán vượt phạm vi kiểu dữ liệu/kiểu đích có thể biểu diễn | `1000.00` không vừa `NUMERIC(5,2)` |

Một phép tính có thể **đủ precision nhưng sai scale**, **bị làm tròn nhưng không tràn**, hoặc **tràn sau khi làm tròn**. Đó là các tình huống khác nhau.

Cần phân biệt hai cách dùng từ “độ chính xác”:

- **Decimal precision** của `NUMERIC(p,s)`: số chữ số thập phân được khai báo, mô tả tập giá trị có thể lưu.
- **Độ chính xác của số dấu phẩy động**: số chữ số có ý nghĩa xấp xỉ mà `REAL`/`DOUBLE PRECISION` biểu diễn được; không đồng nghĩa với `DECIMAL(p,s)` và không bảo đảm từng chữ số thập phân được lưu chính xác.

## 2. Hiểu đúng `DECIMAL(p,s)` và `NUMERIC(p,s)`

Hai dạng khai báo phổ biến:

```sql
price  DECIMAL(7, 2)
weight NUMERIC(9, 3)
```

Ở nhiều DBMS, `DECIMAL` và `NUMERIC` cung cấp số thập phân **chính xác** (exact numeric), còn chi tiết giới hạn và cách thi hành có thể khác. Với cách khai báo thông dụng `0 ≤ s ≤ p`:

- `p`: tổng số chữ số được dành cho phần số.
- `s`: số chữ số sau dấu thập phân.
- `p - s`: số chữ số tối đa ở phần nguyên.
- Dấu âm không được tính là chữ số trong `p`; dấu thập phân cũng không được tính.

Ví dụ `NUMERIC(5,2)`:

```text
                    NUMERIC(5,2)
                          │ │
             precision = 5 │ scale = 2
                          │ │
                  1 2 3 . 4 5
                  └─3─┘   └2┘
                    ↑      ↑
                phần nguyên  phần thập phân
```

Trong cách hiểu này, phạm vi giá trị có thể lưu là từ **`-999.99` đến `999.99`**. Có ba chữ số ở phần nguyên và hai chữ số ở phần thập phân.

| Khai báo | Chữ số phần nguyên tối đa | Chữ số phần thập phân | Giá trị dương lớn nhất theo khuôn dạng |
| --- | ---: | ---: | ---: |
| `NUMERIC(5,2)` | 3 | 2 | `999.99` |
| `NUMERIC(7,2)` | 5 | 2 | `99999.99` |
| `NUMERIC(10,0)` | 10 | 0 | `9999999999` |
| `NUMERIC(12,4)` | 8 | 4 | `99999999.9999` |
| `NUMERIC(12,2)` | 10 | 2 | `9999999999.99` |

Một số DBMS hỗ trợ thêm cách khai báo đặc biệt, chẳng hạn scale âm hoặc scale lớn hơn precision. Các ví dụ trong bài chỉ dùng trường hợp thông dụng `0 ≤ s ≤ p` để người học nắm chắc nguyên lý cơ bản.

### Giá trị hợp lệ, giá trị được làm tròn và giá trị bị từ chối

Với cột PostgreSQL `NUMERIC(5,2)`:

| Giá trị đầu vào | Kết quả khi lưu | Giải thích |
| --- | --- | --- |
| `12.34` | `12.34` | Đã có hai chữ số thập phân |
| `12.345` | `12.35` | Làm tròn về scale 2 |
| `-12.345` | `-12.35` | Với PostgreSQL `numeric`, trường hợp đúng giữa hai mức được làm tròn ra xa 0 |
| `0.004` | `0.00` | Giá trị rất nhỏ bị làm tròn về 0 |
| `999.994` | `999.99` | Sau làm tròn vẫn còn trong phạm vi |
| `999.995` | **Lỗi tràn số** | Sau làm tròn thành `1000.00`, vượt ba chữ số phần nguyên |
| `1234.56` | **Lỗi tràn số** | Phần nguyên có bốn chữ số |

**Điểm dễ bỏ sót:** một số không vượt giới hạn trước khi làm tròn vẫn có thể tràn **sau** khi làm tròn. Với PostgreSQL, khi ép về `NUMERIC(p,s)`, giá trị được làm tròn tới scale đã khai báo rồi được kiểm tra số chữ số phần nguyên có vừa hay không.

## 3. Các nhóm kiểu số khác nhau như thế nào?

### 3.1. Số nguyên: `SMALLINT`, `INTEGER`, `BIGINT`

Số nguyên không có phần thập phân. Phạm vi thường giới hạn bởi số bit biểu diễn (các giá trị sau là của PostgreSQL):

| Kiểu | Phạm vi |
| --- | --- |
| `SMALLINT` | `-32768` đến `32767` |
| `INTEGER` / `INT` | `-2147483648` đến `2147483647` |
| `BIGINT` | `-9223372036854775808` đến `9223372036854775807` |

Việc khai báo `BIGINT` không làm giá trị trở nên vô hạn. Phép cộng, nhân, hay ép kiểu có thể vượt giới hạn và gây lỗi. Một số DBMS cho phép kiểu nguyên không dấu hoặc có hệ thống kiểu nguyên khác, vì vậy không nên tự suy ra cùng phạm vi trên mọi hệ.

### 3.2. Số thập phân chính xác: `DECIMAL` và `NUMERIC`

Đây là lựa chọn thường phù hợp khi **quy định số chữ số thập phân có ý nghĩa nghiệp vụ**, ví dụ số tiền theo đơn vị nhỏ nhất, tỷ lệ phần trăm hoặc số đo đã chuẩn hóa.

```sql
CREATE TABLE payment_example (
    payment_id BIGINT PRIMARY KEY,
    amount     NUMERIC(12, 2) NOT NULL,
    tax_rate   NUMERIC(7, 5) NOT NULL
);
```

`NUMERIC(12,2)` cho phép mười chữ số trước dấu thập phân và hai chữ số sau. `NUMERIC(7,5)` cho phép hai chữ số phần nguyên và năm chữ số phần thập phân, ví dụ `0.08250`. **Scale thể hiện đơn vị và quy tắc lưu**, không phải đơn thuần số chữ số đang hiển thị trên giao diện.

Trong PostgreSQL, `NUMERIC` không khai báo `(p,s)` cũng được hỗ trợ, nhưng không nên hiểu là độ chính xác vô hạn; DBMS vẫn có giới hạn thực tế về số chữ số, lưu trữ và phép tính.

### 3.3. Số dấu phẩy động: `REAL`, `DOUBLE PRECISION`, `FLOAT`

Số dấu phẩy động (floating point) lưu xấp xỉ theo biểu diễn nhị phân. Rất nhiều phân số thập phân hữu hạn như `0.1` **không có biểu diễn nhị phân hữu hạn**, vì thế không được lưu chính xác tuyệt đối.

Với PostgreSQL:

- `REAL` thường là số dấu phẩy động 32 bit, cho khoảng 6 chữ số thập phân có ý nghĩa ở mức độ tin cậy thông dụng.
- `DOUBLE PRECISION` thường là 64 bit, cho khoảng 15 chữ số thập phân có ý nghĩa ở mức độ tin cậy thông dụng.
- `FLOAT(p)` mô tả độ chính xác theo bit nhị phân ở PostgreSQL, **không phải** số chữ số sau dấu thập phân giống `NUMERIC(p,s)`.

Floating point rất hữu ích cho đo lường, tính toán khoa học và dữ liệu xấp xỉ. Nó không phải lựa chọn mặc định tốt cho phép tính tài chính yêu cầu khớp chính xác đến đồng/cent.

Ví dụ trên PostgreSQL:

```sql
SELECT 0.1::DOUBLE PRECISION
     + 0.2::DOUBLE PRECISION
     = 0.3::DOUBLE PRECISION AS equal_as_float;

SELECT 0.1::NUMERIC
     + 0.2::NUMERIC
     = 0.3::NUMERIC AS equal_as_decimal;
```

Trong phép tính floating point thông dụng theo IEEE 754, kết quả so sánh đầu có thể là `false` do sai số biểu diễn, còn phép tính `NUMERIC` trả `true`. Khi cần so sánh số xấp xỉ, thường dùng sai số cho phép phù hợp đơn vị và miền giá trị, thay vì đòi hỏi bằng nhau tuyệt đối.

## 4. Thực hành PostgreSQL: quan sát precision và scale

Phần này dùng một **bảng tạm** trong PostgreSQL. Bảng tồn tại trong phiên kết nối và không cần tên schema riêng. Các câu lệnh `CREATE TEMP TABLE`, `INSERT` nên chạy trong một kết nối thử nghiệm, không chạy trên hệ thống sản xuất.

### Bước 1: Tạo bảng tạm

```sql
CREATE TEMP TABLE precision_lab (
    id    INTEGER GENERATED ALWAYS AS IDENTITY,
    value NUMERIC(5, 2) NOT NULL
);
```

Nếu bảng tạm `precision_lab` đã tồn tại trong phiên, hãy mở phiên thực hành mới hoặc chọn tên khác trước khi chạy lại.

### Bước 2: Chèn giá trị cần làm tròn

```sql
INSERT INTO precision_lab (value)
VALUES
    (12.34),
    (12.345),
    (-12.345),
    (0.004),
    (999.994);

SELECT id, value
FROM precision_lab
ORDER BY id;
```

Kết quả mong đợi ở cột `value` lần lượt là:

```text
12.34
12.35
-12.35
0.00
999.99
```

Bảng vẫn chỉ lưu hai chữ số sau dấu thập phân theo scale đã khai báo, ngay cả khi input chứa ba chữ số.

### Bước 3: Thử một giá trị vượt giới hạn

Chạy câu này **riêng**, sau khi đọc được dữ liệu thành công từ bước 2:

```sql
INSERT INTO precision_lab (value) VALUES (999.995);
```

PostgreSQL sẽ từ chối vì không thể lưu kết quả `1000.00` trong `NUMERIC(5,2)`. Nếu đang dùng một transaction tường minh, lỗi có thể khiến transaction chuyển sang trạng thái cần `ROLLBACK` hoặc xử lý bằng savepoint; không ghép câu gây lỗi với các bước phía sau trong cùng giao dịch khi đang luyện tập.

So sánh một câu vẫn hợp lệ:

```sql
INSERT INTO precision_lab (value) VALUES (999.994);
```

Giá trị này được làm tròn thành `999.99` và vừa phạm vi cho phép.

### Bước 4: Ép kiểu trực tiếp, không cần bảng

```sql
SELECT CAST(123.456 AS NUMERIC(5,2)) AS rounded_value;

SELECT 12.345::NUMERIC(5,2) AS rounded_value;

SELECT ROUND(12.345::NUMERIC, 2) AS explicitly_rounded;
```

Hai cách đầu **ép về một kiểu đích có scale 2**; cách thứ ba gọi hàm **làm tròn một giá trị số**. Mặc dù thường cho cùng kết quả hiển thị, ý nghĩa khác nhau: ép kiểu có thể phát sinh lỗi precision/range; `ROUND` không tự bảo đảm kết quả vừa trong một cột `NUMERIC(p,s)` cụ thể.

## 5. Làm tròn: số chữ số được giữ và quy tắc chọn phía

Khi làm tròn đến hai chữ số thập phân, chữ số thứ ba cùng các chữ số tiếp theo quyết định kết quả theo **quy tắc rounding**. Có nhiều quy tắc hợp lệ:

| Quy tắc | Ý tưởng | Ví dụ làm tròn `1.245` về 2 chữ số |
| --- | --- | --- |
| Half away from zero | Nếu đúng giữa hai mức, chọn mức xa số 0 hơn | `1.25` |
| Half to even (banker's rounding) | Nếu đúng giữa hai mức, chọn mức có chữ số cuối chẵn | `1.24` |
| Truncate (cắt bỏ) | Bỏ chữ số dư, đi về phía số 0 | `1.24` |
| Floor | Chọn số nguyên/phạm vi thấp hơn theo hướng âm vô cực | `FLOOR(1.245) = 1` |
| Ceiling | Chọn số nguyên/phạm vi cao hơn theo hướng dương vô cực | `CEIL(1.245) = 2` |

Các quy tắc không thể thay thế lẫn nhau. Đặc biệt, **truncation không phải một kiểu làm tròn gần nhất**; nó loại bỏ phần dư theo quy tắc riêng.

PostgreSQL có các hàm cho kiểu `NUMERIC`:

```sql
SELECT ROUND(12.345::NUMERIC, 2) AS round_positive, -- 12.35
       TRUNC(12.345::NUMERIC, 2) AS trunc_positive; -- 12.34

SELECT ROUND(-12.345::NUMERIC, 2) AS round_negative, -- -12.35
       TRUNC(-12.345::NUMERIC, 2) AS trunc_negative; -- -12.34

SELECT FLOOR(-1.2::NUMERIC) AS floor_negative,  -- -2
       CEIL(-1.2::NUMERIC)  AS ceil_negative;   -- -1
```

Với giá trị `numeric` nằm đúng giữa hai mức, PostgreSQL làm tròn theo hướng ra xa số 0. Một số DBMS, kiểu số hoặc thư viện khác có thể áp dụng quy tắc khác; đặc biệt hàm làm tròn số floating point có thể phụ thuộc môi trường/triển khai. **Không nên suy ra quy tắc của PostgreSQL `NUMERIC` là quy tắc bắt buộc cho mọi hệ thống SQL.**

### Làm tròn đến chữ số phía trái dấu thập phân

Trong PostgreSQL, tham số thứ hai của `ROUND` có thể âm để làm tròn đến hàng chục, trăm, nghìn:

```sql
SELECT ROUND(1234.56::NUMERIC,  1) AS one_decimal,  -- 1234.6
       ROUND(1234.56::NUMERIC,  0) AS unit,         -- 1235
       ROUND(1234.56::NUMERIC, -1) AS ten,          -- 1230
       ROUND(1234.56::NUMERIC, -2) AS hundred;      -- 1200
```

Đây là tham số **hàm `ROUND`**, không đồng nghĩa với việc mọi DBMS đều cho phép khai báo cột `DECIMAL(p,-2)`.

## 6. Làm tròn diễn ra ở đâu trong vòng đời dữ liệu?

Một giá trị có thể bị ảnh hưởng ở nhiều thời điểm:

```text
Giá trị đầu vào (literal/parameter)
           │
           ▼
Phép tính trong biểu thức SQL
           │   ├─ kiểu trung gian
           │   └─ phép toán có thể làm tròn hoặc tràn
           ▼
Ép kiểu / gán vào cột
           │   ├─ scale của cột đích
           │   └─ kiểm tra phạm vi
           ▼
Giá trị đã lưu trong database
           │
           ▼
SELECT, tổng hợp hoặc trình bày
               ├─ có thể ROUND thêm
               └─ định dạng hiển thị có thể thay đổi
```

Ba hoạt động cần phân biệt:

1. **Làm tròn trong phép tính:** `ROUND(expression, 2)` tạo một kết quả theo quy tắc hàm.
2. **Làm tròn khi gán vào cột:** ép về `NUMERIC(p,2)` có thể thay đổi giá trị và kiểm tra giới hạn của kiểu đích.
3. **Định dạng hiển thị:** một giao diện có thể hiển thị `1.2` thành `1.20` mà không đổi giá trị đã lưu; ngược lại, SQL `ROUND` có thể thực sự thay đổi kết quả biểu thức.

Ví dụ:

```sql
SELECT 10.00::NUMERIC / 3::NUMERIC AS exact_division_result;

SELECT ROUND(10.00::NUMERIC / 3::NUMERIC, 2)
       AS rounded_for_business_rule;
```

Phép chia có thể tạo kết quả với nhiều chữ số thập phân. Chỉ làm tròn ở bước nào cần thiết phụ thuộc quy định nghiệp vụ; làm tròn quá sớm có thể làm thay đổi kết quả tổng sau này.

## 7. Vì sao làm tròn trước và sau khi tổng hợp cho kết quả khác nhau?

Giả sử có hai khoản với giá trị nguồn đều là `0.335`:

```sql
WITH charges(amount) AS (
    VALUES (0.335::NUMERIC), (0.335::NUMERIC)
)
SELECT ROUND(SUM(amount), 2)       AS round_after_sum,
       SUM(ROUND(amount, 2))       AS sum_after_each_round
FROM charges;
```

Trong PostgreSQL:

| Chiến lược | Cách tính | Kết quả |
| --- | --- | --- |
| Tổng trước, làm tròn sau | `ROUND(0.335 + 0.335, 2)` | `0.67` |
| Làm tròn từng dòng, rồi cộng | `ROUND(0.335, 2) + ROUND(0.335, 2)` | `0.68` |

Cả hai kết quả đều phù hợp với phép tính được yêu cầu, nhưng **khác quy tắc nghiệp vụ**. Ví dụ, thuế theo từng dòng hóa đơn và thuế theo tổng hóa đơn có thể cho số làm tròn khác nhau.

Vì vậy khi thiết kế dữ liệu và câu SQL, phải xác định:

- Đơn vị tiền tệ hoặc phép đo là gì?
- Dữ liệu đầu vào có bao nhiêu chữ số thập phân?
- Làm tròn ở dòng, ở nhóm hay ở tổng cuối?
- Quy tắc xử lý khi đúng giữa hai mức là gì?
- Số làm tròn có được lưu lại hay chỉ dùng để trình bày?

**Đừng dùng `ROUND(..., 2)` chỉ để “xóa sai số” khi chưa biết sai số sinh ra từ phép tính gần đúng hay từ quyết định nghiệp vụ.**

## 8. Tràn số ở cột và ngay trong biểu thức

### 8.1. Tràn khi lưu vào cột `NUMERIC(p,s)`

`NUMERIC(5,2)` không chứa được `1234.56` vì phần nguyên vượt ba chữ số. Cả khi làm tròn thành `1000.00`, số vẫn không vừa kiểu đích.

```sql
-- PostgreSQL: lỗi numeric field overflow
SELECT CAST(1234.56 AS NUMERIC(5,2));

-- PostgreSQL: kết quả làm tròn cũng vượt phạm vi
SELECT CAST(999.995 AS NUMERIC(5,2));
```

Nếu dữ liệu hợp lệ về mặt nghiệp vụ nhưng cột quá nhỏ, cần xem lại precision, scale và phạm vi dự kiến. Nếu dữ liệu vốn sai, tăng kích thước cột chỉ che lỗi nguồn.

### 8.2. Tràn phép toán số nguyên trước khi gán

Một biểu thức có thể tràn **trước** bước ép kiểu cuối:

```sql
-- PostgreSQL: 32-bit integer vượt phạm vi
SELECT 2147483647::INTEGER + 1::INTEGER;

-- Ép toán hạng lên BIGINT trước khi cộng
SELECT 2147483647::INTEGER::BIGINT + 1::BIGINT;

-- Ép kết quả sau phép cộng không cứu được phép cộng đã tràn
SELECT (2147483647::INTEGER + 1::INTEGER)::BIGINT;
```

Nếu phép cộng `INTEGER + INTEGER` được xử lý với kết quả `INTEGER`, câu đầu và câu cuối gặp tràn số. Câu giữa nâng kiểu toán hạng trước khi tính nên chứa được kết quả.

Nguyên tắc tương tự có thể gặp khi nhân hai số nguyên lớn hoặc đưa kết quả tổng hợp vào kiểu đích quá nhỏ. **Kiểu của biểu thức trung gian** quan trọng không kém kiểu cột lưu cuối cùng.

### 8.3. Phép tổng hợp và nhân/chia cũng cần tính phạm vi

Tổng của nhiều giá trị có thể lớn hơn từng giá trị đầu vào:

```sql
-- PostgreSQL: SUM trên INTEGER trả kết quả kiểu BIGINT
SELECT SUM(x) AS total
FROM (VALUES (2000000000), (2000000000)) AS v(x);
```

Ở PostgreSQL, `SUM(integer)` được nâng lên `bigint`, giúp ví dụ trên cho `4000000000`. Tuy nhiên, không thể kết luận mọi DBMS đều nâng kiểu tổng hợp giống vậy, hoặc mọi `SUM` đều không bao giờ tràn.

Với phép nhân số tiền và số lượng:

```sql
SELECT 99999.99::NUMERIC(7,2)
     * 1000::NUMERIC(7,0) AS line_amount;
```

Kết quả là `99999990.00`, lớn hơn phạm vi của riêng cột đơn giá `NUMERIC(7,2)`. Cột lưu **thành tiền** vì vậy cần miền giá trị tương ứng với phép nhân, chứ không nên sao chép nguyên độ rộng của cột đơn giá.

Ở một số DBMS, quy tắc xác định precision/scale của phép `+`, `-`, `*` và `/` cho `DECIMAL` có giới hạn riêng; kết quả có thể bị giảm scale hoặc phát sinh overflow khi các phép toán lồng nhau. Khi chuyển câu SQL sang hệ quản trị khác, cần kiểm tra **kiểu kết quả của biểu thức**, không chỉ kiểu dữ liệu ở cột nguồn.

## 9. Ép kiểu, chia số nguyên và chuyển đổi kiểu có thể làm mất thông tin

`CAST` yêu cầu DBMS đổi biểu thức thành kiểu khác. Đổi từ miền giá trị lớn sang nhỏ, từ decimal sang integer, hoặc từ số chính xác sang floating point có thể dẫn đến làm tròn, mất thông tin hoặc lỗi.

Trong PostgreSQL:

```sql
SELECT CAST(12.345 AS NUMERIC(5,2)) AS to_decimal; -- 12.35

SELECT 5::INTEGER / 2::INTEGER AS int_division;    -- 2

SELECT 5::NUMERIC / 2::NUMERIC AS decimal_division;
```

Phép chia hai số nguyên trong PostgreSQL bỏ phần dư; muốn kết quả dạng thập phân, hãy chuyển ít nhất một toán hạng sang kiểu phù hợp **trước phép chia**. Quy tắc chia số nguyên khác nhau giữa DBMS nên không nên giả định câu `5 / 2` luôn trả một kiểu giống nhau.

Khi chuyển giá trị decimal sang integer, cách làm tròn/loại bỏ phần thập phân tùy DBMS và phép toán. Nếu nghiệp vụ muốn **cắt về 0**, hãy sử dụng hàm truncation phù hợp; nếu muốn **làm tròn gần nhất**, hãy áp dụng quy tắc rounding rõ ràng, rồi mới ép kiểu.

### Phép tính qua số floating point

Giả sử cột gốc là số `DECIMAL` chính xác nhưng ứng dụng chuyển sang `DOUBLE`, thực hiện phép toán rồi chuyển về `DECIMAL(12,2)`. Bước chuyển sang floating point có thể mang sai số xấp xỉ vào phép tính. Ép lại về decimal với hai chữ số **không khôi phục** độ chính xác ban đầu.

Với tiền tệ, nên thống nhất dùng decimal chính xác xuyên suốt đường dữ liệu (DBMS, driver và ngôn ngữ ứng dụng) hoặc sử dụng số nguyên biểu diễn đơn vị nhỏ nhất, tùy quy tắc nghiệp vụ. Không nên vừa dùng decimal chính xác trong SQL vừa dùng kiểu dấu phẩy động nhị phân ở tầng ứng dụng cho các phép tính quan trọng đến cent.

## 10. Thiết kế precision và scale cho dữ liệu thực tế

Để chọn `DECIMAL(p,s)`, hãy bắt đầu bằng **miền dữ liệu và ý nghĩa nghiệp vụ**, không chỉ nhìn mẫu dữ liệu nhỏ hiện tại.

### Ví dụ 1: Đơn giá theo hai chữ số thập phân

Giả sử đơn giá lớn nhất được phép là `9,999,999.99`:

- Phần nguyên cần 7 chữ số.
- Phần thập phân cần 2 chữ số.
- Tổng precision cần ít nhất `7 + 2 = 9`.

Có thể khai báo:

```sql
unit_price NUMERIC(9,2)
```

Nếu chính sách cho phép giá đến `99,999,999.99`, cần ít nhất `NUMERIC(10,2)`. Nếu giá trị âm không hợp lệ, constraint riêng cho nghiệp vụ:

```sql
CREATE TABLE catalog_price_example (
    item_id BIGINT PRIMARY KEY,
    unit_price NUMERIC(10,2) NOT NULL
        CHECK (unit_price >= 0)
);
```

Giới hạn số chữ số **không thay thế** ràng buộc dấu, tính hợp lệ và miền giá trị cụ thể.

### Ví dụ 2: Tỷ lệ và phần trăm

`0.075` có thể đại diện tỷ lệ 7.5%, trong khi `7.5` đại diện phần trăm 7.5 nếu hệ thống quy định lưu theo dạng phần trăm. Cùng một hiện tượng nghiệp vụ nhưng giá trị số khác nhau 100 lần:

```text
Tỷ lệ 7.5%:
  lưu dạng phân số: 0.075
  lưu dạng phần trăm: 7.5
```

Nếu dùng `NUMERIC(7,5)` cho phân số, có năm chữ số sau dấu thập phân. Cần ghi rõ đơn vị và miền cho phép, ví dụ `0 ≤ rate ≤ 1`:

```sql
tax_rate NUMERIC(7,5) NOT NULL
    CHECK (tax_rate >= 0 AND tax_rate <= 1)
```

Một scale nhiều chữ số hơn không tự chứng minh số đo chính xác hơn; nó chỉ cho phép lưu nhiều chữ số thập phân hơn. Độ tin cậy còn phụ thuộc cách dữ liệu được đo/tính.

### Ví dụ 3: Tổng tiền cần chỗ lớn hơn đơn giá

Nếu đơn giá có bảy chữ số phần nguyên, còn số lượng có thể lớn, phép nhân có thể tạo nhiều chữ số phần nguyên hơn. Dùng cùng `NUMERIC(9,2)` cho cả `unit_price` và `total_amount` có thể thiếu phạm vi.

Một thiết kế minh họa:

```sql
CREATE TABLE order_line_example (
    line_id      BIGINT PRIMARY KEY,
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    unit_price   NUMERIC(9,2) NOT NULL CHECK (unit_price >= 0),
    total_amount NUMERIC(18,2) NOT NULL CHECK (total_amount >= 0)
);
```

`NUMERIC(18,2)` ở ví dụ này chỉ là **lựa chọn minh họa**; con số thực tế phải dựa trên số lượng tối đa, mức giá tối đa, quy tắc thuế/chiết khấu và cách làm tròn.

### Quy trình chọn kiểu

1. Xác định **giá trị nhỏ nhất/lớn nhất**, kể cả dấu âm nếu có.
2. Xác định **đơn vị và số chữ số thập phân có ý nghĩa**.
3. Tính `p = số chữ số phần nguyên tối đa + s` với decimal chính xác.
4. Xem xét **giá trị trung gian và kết quả tổng hợp**, không chỉ từng dòng.
5. Ghi rõ **thời điểm và quy tắc làm tròn**.
6. Đặt constraint nghiệp vụ (không âm, giới hạn tỷ lệ...) riêng khi cần.
7. Kiểm tra sự phù hợp giữa kiểu SQL và kiểu dữ liệu của ứng dụng.

## 11. Những khác biệt đáng lưu ý giữa các DBMS

| Hệ quản trị | Điều cần nhớ về precision/scale và overflow |
| --- | --- |
| **PostgreSQL** | `NUMERIC(p,s)` lưu decimal chính xác, làm tròn theo scale khi ép vào cột; nếu phần nguyên sau làm tròn không vừa sẽ báo overflow. Hàm `ROUND(numeric, s)` làm tròn giá trị đúng giữa hai mức ra xa 0. |
| **MySQL** | `DECIMAL(p,s)` là kiểu fixed-point chính xác; cách báo lỗi, cảnh báo hoặc xử lý giá trị vượt phạm vi phụ thuộc chế độ SQL (đặc biệt strict mode), câu lệnh và ngữ cảnh chuyển đổi. |
| **SQL Server** | `DECIMAL(p,s)` và `NUMERIC(p,s)` là các tên đồng nghĩa trong hệ này; precision tối đa của decimal là 38. Quy tắc suy ra precision/scale của các phép toán có thể ảnh hưởng kết quả; `ROUND` có quy tắc riêng và lỗi overflow khi giá trị không vừa kiểu đích. |
| **Oracle Database** | `NUMBER(p,s)` kiểm soát chữ số và vị trí thập phân, có hỗ trợ scale âm và các trường hợp đặc thù; cần đọc theo ngữ nghĩa `NUMBER` của Oracle. |
| **SQLite** | Có hệ thống kiểu động và **type affinity**. Khai báo dạng `DECIMAL(5,2)` không bắt SQLite tự thực thi ràng buộc precision/scale như PostgreSQL; cần cơ chế kiểm soát riêng nếu ứng dụng yêu cầu decimal cố định và chính xác. |

Khác biệt còn thể hiện ở phép chia số nguyên, hành vi chuyển kiểu chuỗi sang số, cách chọn kiểu kết quả phép cộng/nhân, xử lý NaN/Infinity, giới hạn precision tối đa và cú pháp làm tròn/cắt số. Khi làm bài trên một DBMS cụ thể, cần phân biệt **quy tắc SQL chung** và **quy tắc của chính hệ đó**.

## 12. Các lỗi thường gặp và cách nhận diện

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Chèn `999.995` vào `NUMERIC(5,2)` báo overflow | Làm tròn thành `1000.00` vượt ba chữ số phần nguyên | Kiểm tra miền giá trị thực; tăng precision nếu nghiệp vụ cho phép |
| `0.1 + 0.2` không bằng chính xác `0.3` | Số nhị phân floating point biểu diễn xấp xỉ | Dùng decimal exact nếu cần; hoặc so sánh theo tolerance phù hợp |
| Tổng tiền sai lệch một đơn vị nhỏ nhất | Khác thời điểm làm tròn: từng dòng hay tổng | Quy định chính sách rounding rồi áp dụng nhất quán |
| `CAST` không giữ mọi chữ số ban đầu | Kiểu đích có scale/precision nhỏ hơn | Chọn kiểu rộng hơn hoặc làm tròn chủ động trước khi cast |
| Cộng hai số nguyên lớn bị lỗi dù cột đích là BIGINT | Phép cộng tràn ở kiểu trung gian trước khi gán | Nâng kiểu toán hạng trước phép tính |
| Kết quả chia bằng số nguyên khi mong thập phân | Hai toán hạng nguyên theo quy tắc DBMS | Ép toán hạng sang `NUMERIC` trước khi chia |
| Một truy vấn chạy ở hệ A nhưng lỗi/cảnh báo ở hệ B | Khác SQL mode, quy tắc scale/overflow hoặc kiểu kết quả | Kiểm tra tài liệu và thử tình huống biên trên DBMS đích |
| Giá trị hiển thị `1.20` nhưng thực chất chỉ lưu `1.2` | Định dạng giao diện hoặc kiểu số không ép scale cố định | Phân biệt format với giá trị/kiểu dữ liệu đã lưu |

Một nguyên tắc chẩn đoán hữu ích: tìm xem sai lệch xuất hiện **lúc nhập dữ liệu, lúc tính biểu thức, lúc ép về kiểu đích, hay chỉ khi hiển thị**. Chỉ khi biết bước gây ra sai lệch mới chọn đúng cách khắc phục.

## 13. Bài tập tự luyện

Các bài dưới đây dùng quy tắc của PostgreSQL, trừ khi yêu cầu chỉ giải thích lý thuyết. Hãy dự đoán trước khi chạy.

**Bài 1 — Xác định precision và scale.** Với từng kiểu `NUMERIC(8,3)`, `NUMERIC(6,0)` và `NUMERIC(11,4)`, hãy tính số chữ số phần nguyên tối đa và giá trị dương lớn nhất theo định dạng đó.

**Bài 2 — Làm tròn trước khi lưu.** Hãy dự đoán kết quả của:

```sql
SELECT 18.345::NUMERIC(6,2);
SELECT -18.345::NUMERIC(6,2);
SELECT 999.995::NUMERIC(5,2);
```

**Bài 3 — Phân biệt làm tròn và cắt bỏ.**

```sql
SELECT ROUND(-2.675::NUMERIC, 2);
SELECT TRUNC(-2.675::NUMERIC, 2);
SELECT FLOOR(-2.675::NUMERIC);
```

**Bài 4 — Tại sao cast muộn không cứu được?** Hai biểu thức sau có khác kết quả không? Vì sao?

```sql
SELECT (2147483647::INTEGER + 1::INTEGER)::BIGINT;
SELECT 2147483647::BIGINT + 1::BIGINT;
```

**Bài 5 — Quy tắc tổng hợp.** Với các khoản `0.335` và `0.335`, so sánh `ROUND(SUM(amount),2)` với `SUM(ROUND(amount,2))`. Theo bạn, khi tính thuế từng dòng hóa đơn cần hỏi người phụ trách nghiệp vụ điều gì?

**Bài 6 — Thiết kế cột.** Một hệ thống có số dư lớn nhất `999,999,999.99`, có thể âm trong tình huống được cho phép, và yêu cầu lưu chính xác hai chữ số thập phân. Hãy chọn `NUMERIC(p,s)` nhỏ nhất đủ phạm vi theo công thức thông dụng. Giải thích tại sao số âm không tăng `p`.

**Bài 7 — Phân biệt exact decimal với floating point.** Tại sao cùng ký tự `0.1` ở bản ghi đầu vào nhưng việc chuyển thành `DOUBLE PRECISION` rồi tính có thể khác với giữ `NUMERIC`? Nếu ứng dụng cần lưu tiền đến cent, nên chọn chiến lược biểu diễn số nào?

### Đáp án tham khảo

- **Bài 1:** `NUMERIC(8,3)` có 5 chữ số phần nguyên, tối đa `99999.999`. `NUMERIC(6,0)` có 6 chữ số phần nguyên, tối đa `999999`. `NUMERIC(11,4)` có 7 chữ số phần nguyên, tối đa `9999999.9999`.
- **Bài 2:** Lần lượt là `18.35`, `-18.35`; biểu thức thứ ba gây lỗi numeric overflow vì `999.995` được làm tròn thành `1000.00`.
- **Bài 3:** Lần lượt `-2.68`, `-2.67` và `-3`; `ROUND`, `TRUNC` và `FLOOR` có quy tắc khác nhau.
- **Bài 4:** Biểu thức đầu tràn ở phép cộng integer trước khi cast; biểu thức sau dùng BIGINT ngay ở phép cộng và cho `2147483648`.
- **Bài 5:** Hai kết quả là `0.67` và `0.68`. Cần xác định làm tròn từng dòng hay sau khi cộng; quy tắc này phải được định nghĩa rõ trong nghiệp vụ.
- **Bài 6:** Giá trị lớn nhất có 9 chữ số phần nguyên, cộng 2 chữ số sau dấu thập phân nên chọn `NUMERIC(11,2)`. Dấu trừ không chiếm một chữ số precision.
- **Bài 7:** `DOUBLE PRECISION` dùng biểu diễn nhị phân xấp xỉ; `NUMERIC` lưu số decimal chính xác trong phạm vi hỗ trợ. Có thể dùng kiểu decimal xuyên suốt hoặc số nguyên biểu diễn đơn vị tiền tệ nhỏ nhất, theo yêu cầu hệ thống.

Trong thiết kế cơ sở dữ liệu, **precision cho biết chỗ dành cho các chữ số; scale cho biết độ phân giải thập phân; rounding quyết định giá trị sau khi giảm độ phân giải; overflow cho biết kết quả không còn nằm trong phạm vi kiểu dữ liệu**. Hiểu bốn khái niệm cùng với kiểu trung gian của biểu thức giúp bạn tránh sai lệch âm thầm và lỗi dữ liệu ở các tình huống biên.
