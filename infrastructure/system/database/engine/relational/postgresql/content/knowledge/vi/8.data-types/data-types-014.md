# Ép kiểu tường minh, suy luận kiểu và chuyển đổi ngầm trong PostgreSQL

PostgreSQL là hệ quản trị cơ sở dữ liệu **có hệ thống kiểu dữ liệu chặt chẽ**. Mỗi cột, kết quả hàm, toán tử và biểu thức SQL có một kiểu xác định. Khi các thành phần mang những kiểu khác nhau xuất hiện trong cùng biểu thức, PostgreSQL phải tìm cách xác định kiểu kết quả, tìm toán tử/hàm phù hợp, hoặc chuyển đổi giá trị sang kiểu mà ngữ cảnh yêu cầu.

Ví dụ, một biểu thức `5 / 2` có kết quả khác với `5::numeric / 2`; chuỗi `'2026-11-14'` có thể được hiểu là ngày, văn bản hoặc một kiểu khác tùy ngữ cảnh; một tham số Java gửi dưới dạng `text` không nhất thiết được chuyển ngầm sang `uuid`. Không hiểu những điểm này có thể gây lỗi truy vấn, làm tròn sai dữ liệu, thay đổi ngữ nghĩa thời gian và khiến PostgreSQL không chọn được toán tử mong muốn.

Bài học phân biệt ba cơ chế:

1. **Ép kiểu tường minh (explicit cast):** lập trình viên chỉ định kiểu đích bằng `CAST(... AS ...)` hoặc `::`.
2. **Suy luận và phân giải kiểu (type inference/type resolution):** PostgreSQL xác định kiểu của literal, tham số, toán tử, hàm hoặc biểu thức nhiều nhánh dựa trên ngữ cảnh.
3. **Chuyển đổi ngầm (implicit cast):** PostgreSQL tự áp dụng một phép chuyển kiểu **được phép** để biểu thức hoặc lệnh gán hợp lệ.

Không phải mọi cặp kiểu đều chuyển được, và không phải phép chuyển nào cũng an toàn hoặc giữ nguyên dữ liệu.

## 1. Phân biệt kiểu dữ liệu với hình thức biểu diễn

Giả sử bạn nhìn thấy ba giá trị `42` trong câu SQL:

```sql
SELECT
    42 AS number_value,
    '42' AS string_literal,
    '42'::integer AS explicitly_typed_integer;
```

Dù công cụ hiển thị có thể in ra giống nhau, ý nghĩa về kiểu khác nhau:

- `42` là numeric literal không có dấu thập phân; PostgreSQL thường chọn kiểu `integer` khi giá trị nằm trong phạm vi, nếu lớn hơn có thể dùng `bigint` hoặc `numeric`.
- `'42'` là **literal chuỗi chưa định kiểu cụ thể** (`unknown` trong giai đoạn phân tích cú pháp). PostgreSQL có thể sử dụng kiểu do ngữ cảnh quy định, hoặc giải quyết nó thành `text` khi không có ngữ cảnh khác phù hợp.
- `'42'::integer` buộc PostgreSQL diễn giải nội dung chuỗi theo cú pháp đầu vào của kiểu `integer`.

Bạn có thể quan sát kiểu kết quả bằng hàm `pg_typeof`:

```sql
SELECT
    pg_typeof(42) AS type_a,
    pg_typeof(42.0) AS type_b,
    pg_typeof('42'::integer) AS type_c,
    pg_typeof('42'::text) AS type_d;
```

Kết quả mong đợi tương ứng là `integer`, `numeric`, `integer` và `text`. Khi một literal chưa được gắn kiểu, PostgreSQL có thêm bước phân giải trong ngữ cảnh truy vấn; vì vậy không nên nhìn dấu nháy trong SQL rồi kết luận chắc chắn kết quả luôn là kiểu `text`.

### Các nhóm kiểu thường cần chuyển đổi

| Nhóm | Ví dụ PostgreSQL | Điều cần lưu ý |
| --- | --- | --- |
| Số nguyên | `smallint`, `integer`, `bigint` | Giới hạn miền giá trị, phép chia nguyên |
| Số chính xác | `numeric`, `decimal` | Giữ độ chính xác thập phân, có thể áp độ rộng và scale |
| Số dấu chấm động | `real`, `double precision` | Có sai số biểu diễn nhị phân |
| Văn bản | `text`, `varchar`, `char` | Phải phân biệt dữ liệu nhập với định danh và literal |
| Boolean | `boolean` | `TRUE`, `FALSE`, `NULL`; không coi mọi số là Boolean |
| Ngày giờ | `date`, `time`, `timestamp`, `timestamptz` | Múi giờ và thời điểm có ý nghĩa riêng |
| Định danh | `uuid` | Có cú pháp đầu vào hợp lệ và biểu diễn nhị phân riêng |
| Cấu trúc | `json`, `jsonb`, array, composite | Không phải mọi phép chuyển tương đương việc phân tích cấu trúc |
| Kiểu tự định nghĩa | enum, domain, user-defined types | Quy tắc chuyển đổi và ràng buộc riêng |

Một biểu thức có vẻ tương đồng về mặt văn bản có thể không tương đương về mặt dữ liệu. Ví dụ `'false'::text` vẫn là chuỗi, còn `'false'::boolean` là giá trị Boolean sai.

## 2. Ép kiểu tường minh: CAST và toán tử ::

Hai cú pháp phổ biến:

```sql
CAST(expression AS target_type)

expression::target_type
```

`CAST` là cú pháp SQL tiêu chuẩn và có tính di động tốt hơn giữa các hệ quản trị. `::` là cách viết gọn đặc trưng PostgreSQL, rất phổ biến trong câu SQL và các ví dụ sử dụng `psql`.

Ví dụ:

```sql
SELECT CAST('42' AS integer) AS via_cast;
SELECT '42'::integer AS via_colon;

SELECT CAST('129.75' AS numeric(10, 2));
SELECT '2026-11-14'::date;
SELECT 'true'::boolean;
```

Cả hai cú pháp yêu cầu có đường chuyển đổi hợp lệ tới kiểu đích. Ép kiểu **không bảo đảm luôn thành công**:

```sql
-- Lỗi: invalid input syntax for type integer.
SELECT 'forty two'::integer;

-- Lỗi: vượt phạm vi kiểu integer.
SELECT '999999999999999999999'::integer;
```

Trong truy vấn thực tế, nếu cột đang lưu chuỗi nhập liệu không chắc hợp lệ, hãy kiểm tra hoặc chuẩn hóa dữ liệu trước khi cast. Một lỗi chuyển đổi ở bất kỳ hàng nào có thể làm cả statement thất bại.

### 2.1. CAST không chỉ dùng cho chuỗi

```sql
SELECT
    12::numeric(10, 2) AS amount,
    1::double precision / 4 AS fraction,
    123::text AS number_as_text;
```

Ý nghĩa:

- `12::numeric(10, 2)` cho giá trị có phần thập phân theo scale 2.
- `1::double precision / 4` thực hiện phép chia theo ngữ cảnh số dấu chấm động.
- `123::text` chuyển số sang biểu diễn văn bản.

Không nên lạm dụng ép kiểu sang `text` chỉ vì muốn hai giá trị so sánh được. Việc biến mã định danh kiểu số thành text có thể đổi thứ tự sắp xếp, cách so sánh và khả năng sử dụng index.

### 2.2. Ép kiểu trong biểu thức phức tạp

```sql
SELECT
    (15 + 5)::numeric / 3 AS average_value,
    ('250.00'::numeric(12, 2) * 0.08)::numeric(12, 2) AS tax,
    CAST((3 + 2) AS text) || ' items' AS label;
```

Dùng dấu ngoặc để thể hiện rõ biểu thức nào được ép kiểu. Với `::`, nên phân biệt cách phân tích biểu thức với cast riêng từng toán hạng, nhất là khi kết hợp phép toán, hàm và toán tử do extension định nghĩa.

## 3. Cùng số liệu nhưng kết quả khác: phép chia nguyên và số thập phân

Một ví dụ kinh điển:

```sql
SELECT
    5 / 2 AS integer_division,
    5::numeric / 2 AS numeric_division,
    5 / 2.0 AS numeric_literal_division;
```

Kết quả:

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `5 / 2` | `2` | Hai toán hạng kiểu nguyên; phần lẻ bị loại bỏ theo phép chia nguyên |
| `5::numeric / 2` | `2.5` | Một toán hạng là `numeric`, phép toán được phân giải theo kiểu phù hợp |
| `5 / 2.0` | `2.5` | Literal `2.0` thường được nhận là `numeric` |

Đối với số âm, phép chia nguyên PostgreSQL cắt phần lẻ **về phía 0**; ví dụ `-5 / 2` cho `-2`.

Sai lầm thường thấy khi tính tỷ lệ:

```sql
-- Tỷ lệ có thể mất phần thập phân trước khi nhân 100.
SELECT 3 / 10 * 100 AS wrong_percentage;

-- Ép kiểu trước phép chia để giữ phần thập phân.
SELECT 3::numeric / 10 * 100 AS correct_percentage;
```

Biểu thức đầu cho `0`; biểu thức thứ hai cho `30` theo phép toán số chính xác. Nếu muốn hiện hai chữ số thập phân:

```sql
SELECT round(3::numeric / 10 * 100, 2) AS percentage;
```

### 3.1. Rounding và overflow là hệ quả của chuyển kiểu

```sql
SELECT
    12.7::integer AS rounded_integer,
    12.345::numeric(6, 2) AS rounded_decimal;
```

Ép từ `numeric` có phần thập phân sang kiểu số nguyên trong PostgreSQL thực hiện làm tròn theo quy tắc của phép cast, không đơn giản là phép cắt phần lẻ giống phép chia số nguyên. Kết quả `12.7::integer` là `13`; `12.345::numeric(6,2)` cho `12.35`.

Nếu muốn làm tròn theo một chiến lược nghiệp vụ cụ thể, hãy biểu diễn rõ bằng các hàm phù hợp như `round`, `trunc`, `floor` hoặc `ceil` trước khi cast. Chọn `numeric` cho giá trị tiền tệ cần độ chính xác thập phân; không mặc định dùng `double precision` để biểu diễn số tiền.

Một cast tới kiểu nhỏ hơn còn có thể gây **overflow**:

```sql
-- 40000 vượt giới hạn smallint.
SELECT 40000::smallint;
```

Lỗi này là tín hiệu dữ liệu vượt hợp đồng kiểu đích. Đừng tự động thay mọi trường hợp overflow bằng `0` hay `NULL` nếu không có quyết định nghiệp vụ rõ ràng.

## 4. Unknown literal: tại sao chuỗi có thể trở thành số hoặc ngày?

Trong PostgreSQL, literal viết trong dấu nháy đơn nhưng **chưa mang ép kiểu** ban đầu có kiểu tạm thời `unknown`. Bộ phân tích SQL sử dụng ngữ cảnh để quyết định cần hiểu literal đó là gì.

Ví dụ:

```sql
SELECT 1 = '1' AS numbers_match;

SELECT DATE '2026-11-14' + INTERVAL '1 day' AS next_day;

SELECT '2026-11-14'::date AS explicit_date;
```

Ở `1 = '1'`, PostgreSQL có thể chọn toán tử so sánh số nguyên phù hợp rồi diễn giải literal `'1'` thành số nguyên. Điều này **không có nghĩa** một cột đã được khai báo kiểu `text` cũng tự động chuyển ngầm sang integer trong mọi phép so sánh.

Phân biệt hai tình huống:

```sql
-- Literal chưa có kiểu cụ thể: ngữ cảnh có thể quyết định là integer.
SELECT 10 = '10';

-- Giá trị đã có kiểu text: không dựa vào khả năng phân giải unknown literal.
SELECT 10 = '10'::text;
```

Biểu thức thứ hai có thể báo lỗi không có toán tử `integer = text` phù hợp. Muốn so sánh có ý nghĩa, chỉ định phép chuyển kiểu rõ ràng:

```sql
SELECT 10 = ('10'::text)::integer;

-- Hoặc nếu mục tiêu thật sự là so sánh văn bản:
SELECT 10::text = '10'::text;
```

Hai cách so sánh trên có thể cho cùng kết quả ở dữ liệu minh họa, nhưng ngữ nghĩa khác nhau: so sánh số không phân biệt các cách biểu diễn như `'010'` và `'10'`, trong khi so sánh văn bản thì có thể phân biệt.

### 4.1. Typed literal

PostgreSQL còn cho phép một số cú pháp đặt tên kiểu trước chuỗi:

```sql
SELECT DATE '2026-11-14';
SELECT TIMESTAMP '2026-11-14 09:30:00';
SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07';
SELECT INTERVAL '2 days';
```

Đây là cách tạo literal với kiểu rõ ràng, rất hữu ích khi so sánh ngày giờ và tránh phụ thuộc vào suy luận kiểu.

Một literal định dạng ngày không hợp lệ vẫn gây lỗi:

```sql
SELECT 'not-a-date'::date;
```

Định dạng ngày mơ hồ có thể bị ảnh hưởng bởi `DateStyle`. Dùng định dạng ISO `YYYY-MM-DD` hoặc timestamp ISO có offset rõ ràng để giảm phụ thuộc môi trường.

## 5. Chuyển đổi ngầm: PostgreSQL được phép tự làm gì?

Có những trường hợp PostgreSQL có thể chuyển một kiểu sang kiểu khác mà SQL không cần viết `CAST`. Ví dụ, trong một biểu thức toán học phối hợp kiểu số nguyên và `numeric`, hệ thống có thể chọn phép toán và chuyển đổi kiểu thích hợp để không mất phần thập phân.

```sql
SELECT
    2 + 0.5 AS result,
    pg_typeof(2 + 0.5) AS result_type;
```

Kết quả có kiểu `numeric`. Nhưng không thể kết luận mọi `text` đều tự động đổi thành `integer` hoặc mọi `jsonb` đều tự biến thành `text`.

PostgreSQL phân biệt các ngữ cảnh cast:

| Ngữ cảnh | Ý nghĩa | Ví dụ định hướng |
| --- | --- | --- |
| **Implicit** | Có thể tự dùng khi phân giải biểu thức, hàm, toán tử | Một số phép chuyển giữa các kiểu số |
| **Assignment** | Được phép khi gán/ghi vào cột đích, ngoài các ngữ cảnh được phép rõ ràng khác | Chuyển giá trị phù hợp sang kiểu cột trong `INSERT`/`UPDATE` |
| **Explicit only** | Chỉ cho phép khi người viết SQL yêu cầu cast | Những chuyển đổi có khả năng làm mất ngữ nghĩa hoặc cần lựa chọn chủ động |

Đó là **mức cho phép chuyển đổi**, không phải cam kết rằng PostgreSQL luôn dùng cast đó trong bất kỳ biểu thức nào. Bộ phân giải còn xét số lượng ứng viên hàm/toán tử, kiểu ưu tiên, kiểu của tham số và các quy tắc lựa chọn cụ thể.

### 5.1. Tại sao chuyển ngầm lại được giới hạn?

Nếu database tự đổi mọi giá trị text sang số, các câu lệnh như `'001' = 1` có thể đánh đồng mã định danh với giá trị số. Nếu tự đổi text sang ngày, các chuỗi không hợp lệ hoặc định dạng mơ hồ sẽ gây lỗi khó dự đoán. Hạn chế cast ngầm giúp ngăn việc chọn nhầm toán tử hoặc âm thầm làm mất thông tin.

Một ví dụ về khác biệt giữa literal và cột:

```sql
CREATE SCHEMA IF NOT EXISTS cast_lab;

CREATE TABLE cast_lab.imported_values (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_code text NOT NULL
);

INSERT INTO cast_lab.imported_values(raw_code)
VALUES ('10'), ('010'), ('not_a_number');

-- Đây là so sánh văn bản hợp lệ:
SELECT * FROM cast_lab.imported_values
WHERE raw_code = '10';
```

Nếu muốn diễn giải toàn bộ `raw_code` như số, câu `raw_code::integer` sẽ gặp lỗi ở hàng `not_a_number`. Đây là vấn đề **chất lượng dữ liệu**, không phải chỉ do thiếu cú pháp cast.

### 5.2. Tra cứu cast hợp lệ qua pg_cast

PostgreSQL có catalog `pg_cast` lưu nhiều phép chuyển đổi đã đăng ký. Ví dụ:

```sql
SELECT
    c.castsource::regtype AS source_type,
    c.casttarget::regtype AS target_type,
    CASE c.castcontext
        WHEN 'i' THEN 'implicit'
        WHEN 'a' THEN 'assignment'
        WHEN 'e' THEN 'explicit'
    END AS cast_context,
    CASE c.castmethod
        WHEN 'f' THEN 'function'
        WHEN 'i' THEN 'input/output'
        WHEN 'b' THEN 'binary-compatible'
    END AS cast_method
FROM pg_cast AS c
WHERE c.castsource = 'integer'::regtype
   OR c.casttarget = 'integer'::regtype
ORDER BY source_type::text, target_type::text;
```

Cột `castcontext` có các ký hiệu `i`, `a`, `e`. Cột `castmethod` chỉ cách thực hiện: gọi hàm, dùng input/output hoặc chuyển đổi tương thích nhị phân.

**Giới hạn quan trọng:** `pg_cast` không liệt kê mọi trường hợp PostgreSQL có thể chuyển đổi. Chẳng hạn một số chuyển đổi từ/đến chuỗi, domain và kiểu phức hợp được xử lý bằng các quy tắc đặc biệt. Vì vậy, không tìm thấy dòng trong `pg_cast` không tự động chứng minh không có đường chuyển đổi nào.

### 5.3. CAST hợp lệ không có nghĩa giá trị hợp lệ

```sql
SELECT '123'::integer;      -- Thành công
SELECT '12.3'::integer;     -- Lỗi cú pháp integer
SELECT 'true'::boolean;     -- Thành công
SELECT 'perhaps'::boolean;  -- Lỗi cú pháp boolean
```

Các chuyển đổi đầu vào có thể phụ thuộc dữ liệu cụ thể. Việc query parse được chưa bảo đảm mọi giá trị trong bảng chạy qua cast thành công.

## 6. Suy luận kiểu trong toán tử và lời gọi hàm

PostgreSQL có nhiều toán tử và hàm **nạp chồng (overload)**: cùng tên nhưng nhận các kiểu tham số khác nhau.

```sql
SELECT 7 + 5;
SELECT 7::numeric + 5;
SELECT 7::double precision + 5::double precision;
```

Toán tử `+` được lựa chọn dựa trên kiểu toán hạng và các phép chuyển có thể áp dụng. Điều này cũng xảy ra với hàm.

### 6.1. Hàm round và kiểu numeric/double precision

```sql
SELECT round(12.345::numeric, 2) AS rounded_amount;

-- Hàm một tham số cho double precision có thể được dùng:
SELECT round(12.345::double precision);
```

PostgreSQL có biến thể `round(numeric, integer)` để chỉ định số chữ số thập phân, nhưng không có cùng chữ ký `round(double precision, integer)` trong bộ hàm chuẩn thường dùng.

```sql
-- Không chọn được hàm round(double precision, integer).
SELECT round(12.345::double precision, 2);

-- Chuyển rõ về numeric nếu thật sự muốn dùng scale:
SELECT round(12.345::double precision::numeric, 2);
```

Cách chuyển từ số dấu chấm động về `numeric` chỉ chuyển giá trị đã được biểu diễn ở độ chính xác của double; không thể “khôi phục” toàn bộ chữ số thập phân gốc nếu dữ liệu đã chịu sai số làm tròn từ trước.

### 6.2. Truy vấn pg_typeof để quan sát kết quả phân giải

```sql
SELECT
    pg_typeof(7 + 5) AS integer_math,
    pg_typeof(7 + 0.5) AS numeric_math,
    pg_typeof(7::double precision + 0.5::double precision)
        AS floating_math;
```

Đây là một cách thực hành trực tiếp để thấy kết quả chọn kiểu. Khi hàm trả về kiểu khác mong đợi, hãy xem kiểu của từng đối số trước khi thêm các cast tùy tiện.

### 6.3. Truy vấn báo lỗi ambiguous function/operator

Nếu nhiều biến thể hàm/toán tử đều có vẻ phù hợp và hệ thống không thể chọn một ứng viên duy nhất theo quy tắc phân giải, PostgreSQL có thể báo lỗi dạng **function ... is not unique** hoặc **operator is not unique**.

Giải pháp thường là cast một hoặc vài đối số về kiểu bạn thật sự muốn. Cần chọn dựa trên ý nghĩa nghiệp vụ và chữ ký hàm, không chỉ thử ngẫu nhiên cho tới khi lỗi biến mất.

Ví dụ, nếu hàm ứng dụng đã có nhiều overload cho `integer`, `numeric` và `text`, việc truyền tham số không có kiểu cụ thể có thể khiến lựa chọn thiếu rõ ràng. Viết `my_function($1::numeric)` khi đầu vào thực sự là số thập phân.

## 7. Suy luận kiểu của CASE, COALESCE, UNION và VALUES

Các biểu thức có thể trả về nhiều nhánh phải chọn **một kiểu kết quả thống nhất**. PostgreSQL áp dụng các quy tắc tương thích và lựa chọn kiểu; không phải cứ có `text` là tự chuyển mọi giá trị thành text.

### 7.1. CASE

```sql
SELECT
    CASE
        WHEN TRUE THEN 10
        ELSE 12.5
    END AS chosen_value;
```

Kết quả có kiểu `numeric` vì các nhánh số có thể được thống nhất dưới kiểu đó.

```sql
SELECT pg_typeof(
    CASE WHEN TRUE THEN 10 ELSE 12.5 END
);
```

Nếu các nhánh trả về kiểu không tương thích, việc phân giải có thể báo lỗi:

```sql
-- Không nên giả định kiểu integer và text đã định kiểu cụ thể
-- sẽ tự thống nhất theo nội dung hiển thị.
SELECT CASE WHEN TRUE THEN 1 ELSE 'abc'::text END;
```

Khi muốn một biểu thức trả về văn bản, chuyển rõ:

```sql
SELECT
    CASE
        WHEN TRUE THEN 1::text
        ELSE 'abc'::text
    END AS display_value;
```

Một lưu ý: kiểu được giải quyết tại **thời điểm phân tích câu SQL**, không chờ đến khi chạy nhánh được chọn. Không thể dùng `CASE` để che giấu một nhánh có kiểu hoàn toàn không hợp lệ rồi hy vọng PostgreSQL bỏ qua việc phân giải nhánh ấy.

### 7.2. COALESCE

`COALESCE` trả về đối số đầu tiên khác `NULL`, nhưng các đối số vẫn phải có **kiểu kết quả thống nhất**:

```sql
SELECT
    COALESCE(NULL, 10, 12.5) AS value,
    pg_typeof(COALESCE(NULL, 10, 12.5)) AS value_type;
```

`value_type` là `numeric` trong ví dụ trên. `NULL` không được định kiểu tường minh có thể nhận kiểu theo các đối số còn lại.

Nếu lấy một giá trị số từ văn bản, hãy cast một cách có chủ đích:

```sql
SELECT COALESCE(NULLIF('42', '')::integer, 0);
```

`NULLIF('42', '')` trả về giá trị text `'42'`; cast sang `integer` rồi mới dùng với số mặc định `0`. Nếu chuỗi khác rỗng nhưng không phải số, phép cast vẫn thất bại.

### 7.3. UNION và UNION ALL

Hai vế của `UNION` cần các cột tương ứng có kiểu tương thích:

```sql
SELECT 10 AS amount
UNION ALL
SELECT 20.5 AS amount;
```

Kiểu kết quả là `numeric`. Với những chuỗi literal chưa gắn kiểu:

```sql
SELECT 'alpha' AS code
UNION ALL
SELECT 'beta' AS code;
```

Cột kết quả thường được giải thành `text` khi chỉ có các literal chưa xác định kiểu.

Khi ghép nhiều `UNION` theo chuỗi, PostgreSQL giải quyết kiểu theo từng cặp trong cấu trúc biểu thức. Một vế trung gian chỉ chứa `NULL`/unknown có thể đã được chọn thành `text` trước khi gặp vế kiểu `integer` ở sau, dẫn đến lỗi. Dùng ép kiểu tường minh ở các nhánh đầu khi muốn tất cả cùng loại:

```sql
SELECT NULL::integer AS score
UNION ALL
SELECT NULL::integer
UNION ALL
SELECT 5;
```

### 7.4. VALUES và INSERT

`VALUES` nhiều dòng cũng cần thống nhất kiểu của từng vị trí cột:

```sql
SELECT *
FROM (VALUES (1), (2.5), (3)) AS v(amount);
```

Trong `INSERT`, **kiểu cột đích** cung cấp ngữ cảnh gán:

```sql
CREATE TABLE cast_lab.payments (
    payment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    amount numeric(12, 2) NOT NULL,
    paid boolean NOT NULL DEFAULT FALSE,
    paid_on date
);

INSERT INTO cast_lab.payments (amount, paid, paid_on)
VALUES ('150.75', 'true', '2026-11-14');
```

Các chuỗi literal chưa định kiểu được diễn giải theo kiểu các cột đích: `numeric`, `boolean` và `date`. Đừng suy ra rằng nếu thay các literal đó bằng **tham số JDBC đã định kiểu text** thì mọi phép gán cũng sẽ được chuyển đổi ngầm theo cách tương tự.

### 7.5. ARRAY

Một array PostgreSQL có kiểu phần tử xác định:

```sql
SELECT ARRAY[1, 2, 3]::integer[] AS integer_array;
SELECT ARRAY['a', 'b', 'c']::text[] AS text_array;
```

Các phần tử có kiểu không tương thích có thể làm biểu thức array thất bại. Khi cần array giá trị định danh, hãy chỉ rõ kiểu như `uuid[]`, `bigint[]` thay vì chuyển hết sang text.

## 8. NULL và kiểu chưa xác định

`NULL` biểu thị vắng mặt giá trị SQL. Một `NULL` không có cast thường được suy luận kiểu từ vị trí xuất hiện, ví dụ:

```sql
SELECT COALESCE(NULL, 100::bigint);
SELECT NULL::date;
SELECT NULL::uuid;
```

`NULL::date` và `NULL::uuid` đều vẫn là `NULL`, nhưng thuộc **kiểu khác nhau**. Điều đó rất quan trọng trong hàm nạp chồng, `UNION` và tham số có thể rỗng.

Ví dụ:

```sql
SELECT
    pg_typeof(NULL::integer) AS integer_null,
    pg_typeof(NULL::text) AS text_null,
    pg_typeof(NULL::boolean) AS boolean_null;
```

Lưu ý `NULL` không được coi là giá trị `0`, `FALSE` hoặc chuỗi rỗng. Ép `NULL` sang một kiểu phù hợp chỉ thay đổi kiểu của giá trị thiếu, không tự tạo dữ liệu.

### 8.1. Tránh giả định null giúp bỏ qua cast lỗi

```sql
SELECT COALESCE(NULLIF('', '')::integer, 0); -- 0
```

Nhưng:

```sql
SELECT COALESCE(NULLIF('bad', '')::integer, 0);
```

sẽ thất bại vì `'bad'::integer` không hợp lệ. `COALESCE` chỉ xử lý `NULL` sau khi biểu thức cast được tính thành công; nó không phải cơ chế bắt lỗi chuyển kiểu.

Với dữ liệu đầu vào không chắc hợp lệ, cần xác định điều kiện chấp nhận, chuẩn hóa ở ranh giới nhập liệu, hoặc xử lý lỗi trong ứng dụng/quy trình ETL. Một regex đơn giản kiểm tra ký tự số không bảo đảm giá trị nằm trong phạm vi kiểu đích.

## 9. Chuyển đổi date, timestamp và timestamptz

Đây là lĩnh vực cần cast rõ ràng nhất trong nhiều ứng dụng.

PostgreSQL phân biệt:

- `date`: ngày theo lịch, không có giờ và múi giờ.
- `time without time zone`: giờ trong ngày không kèm múi giờ.
- `timestamp without time zone`: ngày giờ “local” nhưng không xác định múi giờ hay một thời điểm UTC duy nhất.
- `timestamp with time zone` (`timestamptz`): biểu diễn một **thời điểm**, được diễn giải theo múi giờ khi nhập không có offset và được hiển thị theo múi giờ session.

Ví dụ:

```sql
SELECT
    '2026-11-14'::date AS calendar_day,
    '2026-11-14 09:00:00'::timestamp AS local_datetime,
    '2026-11-14 09:00:00+07'::timestamptz AS instant;
```

Giá trị `timestamptz` được lưu và so sánh theo một mốc thời gian tuyệt đối; việc trình bày có thể khác khi session đổi `TimeZone`.

```sql
BEGIN;
    SET LOCAL TIME ZONE 'UTC';

    SELECT '2026-11-14 09:00:00+07'::timestamptz AS utc_display;
COMMIT;
```

Khi hiển thị ở UTC, thời điểm đó tương ứng `2026-11-14 02:00:00+00`.

### 9.1. Dữ liệu không có múi giờ không tự nhiên biến thành thời điểm chính xác

```sql
SELECT '2026-11-14 09:00:00'::timestamp;
```

Giá trị trên không tự cho biết đó là 9 giờ ở Việt Nam hay UTC. Nếu ép `timestamp without time zone` thành `timestamptz`, PostgreSQL diễn giải thời gian theo múi giờ session nếu không chỉ định rõ ngữ cảnh.

Nếu dữ liệu được định nghĩa là giờ địa phương ở thành phố cụ thể, có thể nêu vùng giờ:

```sql
SELECT
    '2026-11-14 09:00:00'::timestamp
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS instant;
```

Biểu thức đó chuyển một giờ địa phương được biết rõ múi giờ sang một `timestamptz` tương ứng. Ngược lại, áp dụng `AT TIME ZONE` lên `timestamptz` cho một `timestamp without time zone` thể hiện giờ địa phương tại vùng giờ được chọn.

Chuyển đổi qua lại mà không xác định yêu cầu nghiệp vụ có thể làm lệch nhiều giờ, đặc biệt với múi giờ có giờ mùa hè.

### 9.2. CAST sang date có thể bỏ phần thời gian

```sql
SELECT '2026-11-14 14:30:00'::timestamp::date AS only_date;
```

Kết quả `date` chỉ còn ngày. Với `timestamptz::date`, **ngày được xác định theo múi giờ session**, nên cùng một instant có thể được nhìn thành hai ngày lịch ở hai múi giờ khác nhau.

Khi ứng dụng Java dùng `LocalDate`, `LocalDateTime` hoặc `OffsetDateTime`/`Instant`, mapping tới kiểu PostgreSQL phải phù hợp ngữ nghĩa. `LocalDateTime` không mang offset, nên không nên dùng thay `Instant` khi cần thời điểm toàn cục.

## 10. CAST với UUID

PostgreSQL có kiểu `uuid` riêng:

```sql
SELECT
    '550e8400-e29b-41d4-a716-446655440000'::uuid AS user_id;
```

Định dạng không hợp lệ sẽ gây lỗi:

```sql
SELECT 'user-123'::uuid;
```

Giả sử bảng:

```sql
CREATE TABLE cast_lab.users (
    user_id uuid PRIMARY KEY,
    username text NOT NULL UNIQUE
);

INSERT INTO cast_lab.users (user_id, username)
VALUES (
    '550e8400-e29b-41d4-a716-446655440000',
    'learner'
);
```

Chuỗi ở `INSERT` là literal chưa định kiểu và nhận ngữ cảnh cột `uuid`. Đối với tham số client đã định kiểu `text`, nên truyền đúng giá trị UUID hoặc cast tường minh tại vị trí thích hợp:

```sql
SELECT *
FROM cast_lab.users
WHERE user_id = '550e8400-e29b-41d4-a716-446655440000'::uuid;
```

**Không** nên cast `user_id::text` ở mọi điều kiện chỉ để so sánh với một tham số văn bản. Cách đó thay đổi biểu thức truy vấn, có thể làm index B-tree bình thường trên `user_id` không còn là lựa chọn trực tiếp và dễ che giấu việc ứng dụng truyền sai kiểu. Truyền tham số đúng kiểu `uuid` thường tốt hơn.

## 11. CAST với JSON và JSONB

`jsonb` là dữ liệu có cấu trúc. Hai thao tác sau mang ý nghĩa khác nhau:

```sql
SELECT
    '{"quantity": 3}'::jsonb AS parsed_json,
    '{"quantity": 3}'::text AS plain_text;
```

Giá trị đầu được PostgreSQL phân tích thành JSONB hợp lệ; giá trị sau chỉ là chuỗi ký tự. Chuỗi JSON không hợp lệ sẽ bị từ chối khi chuyển thành `jsonb`:

```sql
SELECT '{quantity:3}'::jsonb;
```

### 11.1. -> và ->> khác nhau về kiểu kết quả

```sql
SELECT
    pg_typeof(('{"quantity":3}'::jsonb -> 'quantity'))
        AS jsonb_result,
    pg_typeof(('{"quantity":3}'::jsonb ->> 'quantity'))
        AS text_result;
```

`->` giữ giá trị `jsonb`, trong khi `->>` lấy giá trị ở dạng `text`. Nếu cần dùng giá trị trong phép toán số, hãy cast khi biết định dạng dữ liệu hợp lệ:

```sql
SELECT
    (('{"quantity":3}'::jsonb ->> 'quantity')::integer * 10)
        AS total_units;
```

Đối với dữ liệu JSONB có thể chứa `{"quantity":"many"}`, cast sang integer sẽ lỗi. Do đó, việc lưu kiểu đúng ngay từ đầu và xác thực payload ở ranh giới nhập là quan trọng.

### 11.2. JSON null không giống SQL NULL

```sql
SELECT
    jsonb_typeof('{"flag":null}'::jsonb -> 'flag') AS json_null_type,
    jsonb_typeof('{}'::jsonb -> 'flag') AS missing_type;
```

Kết quả thứ nhất là chuỗi `'null'`; thứ hai là SQL `NULL` vì không có khóa tương ứng. Các phép chuyển đổi từ JSONB về text/Boolean phải tính đến khả năng thiếu khóa, JSON null và dữ liệu sai kiểu.

### 11.3. Chuyển số sang JSONB không phải chỉ đổi định dạng hiển thị

```sql
SELECT
    to_jsonb(42) AS json_number,
    to_jsonb('42'::text) AS json_string;
```

Giá trị đầu là JSON number `42`; giá trị sau là JSON string `"42"`. Chúng có cùng nội dung khi nhìn bằng mắt nhưng khác kiểu và hành vi so sánh trong JSON.

## 12. Chuyển kiểu text, varchar, char và độ dài

`text` và `varchar` thường có thể dùng trong các truy vấn văn bản. `varchar(n)` áp ràng buộc độ dài, còn `char(n)` có ngữ nghĩa đệm khoảng trắng riêng.

```sql
SELECT
    'hello'::text AS a,
    'hello'::varchar(10) AS b,
    'AB'::char(5) AS c;
```

Chuyển tường minh sang `varchar(n)` hoặc `char(n)` có thể cắt bớt dữ liệu dài hơn giới hạn theo quy tắc của PostgreSQL. Trong khi đó, khi **gán vào cột** đã khai báo độ dài, giá trị vượt giới hạn thường bị từ chối, trừ một số trường hợp khoảng trắng được xử lý đặc biệt.

```sql
SELECT 'abcdef'::varchar(3) AS shortened;
```

Đầu ra ở ví dụ tường minh chỉ còn `abc`. Đây là phép **mất dữ liệu** có chủ đích khi cast, không nên dùng như cách làm sạch chuỗi mặc định.

Nếu cần giới hạn đầu vào người dùng, hãy xác thực dữ liệu trước khi lưu và trả lỗi rõ ràng thay vì dựa vào cast cắt ngắn.

### 12.1. Toán tử nối chuỗi ||

```sql
SELECT 'Order #' || 123::text AS label;
```

PostgreSQL cũng hỗ trợ các biến thể của `||` có thể nhận một số kiểu không phải văn bản. Nhưng khi biểu thức có nhiều kiểu hoặc kiểu tự định nghĩa, cast rõ ràng giúp code dễ hiểu hơn và ít phụ thuộc overload resolution.

Một lỗi khác là ép số sang text rồi so sánh thứ tự:

```sql
SELECT '10'::text < '2'::text AS lexical_comparison;
SELECT 10 < 2 AS numeric_comparison;
```

So sánh text theo quy tắc collation có thể cho kết quả khác so sánh số. Không chuyển cột số sang text khi ý định là so sánh giá trị toán học.

## 13. Assignment cast khi ghi vào cột

Khi `INSERT` hoặc `UPDATE`, PostgreSQL cần đảm bảo biểu thức gán phù hợp kiểu cột đích.

```sql
CREATE TABLE cast_lab.measurements (
    measurement_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reading numeric(10, 2) NOT NULL,
    recorded_on date NOT NULL
);

INSERT INTO cast_lab.measurements (reading, recorded_on)
VALUES ('12.45', '2026-11-14');

UPDATE cast_lab.measurements
SET reading = 15
WHERE measurement_id = 1;
```

Giá trị literal chưa gắn kiểu hoặc số nguyên được chuyển phù hợp trong ngữ cảnh gán cột `numeric(10,2)`. Nhưng các quy tắc assignment không có nghĩa bất cứ giá trị không hợp lệ nào cũng được bỏ qua:

```sql
-- Câu này gây lỗi khi chuỗi không phải số hợp lệ.
INSERT INTO cast_lab.measurements (reading, recorded_on)
VALUES ('not-a-number', '2026-11-14');
```

`numeric(10,2)` còn áp giới hạn độ rộng và làm tròn scale. Kiểu SQL là một phần hợp đồng dữ liệu giữa ứng dụng và database, không phải chỉ là lựa chọn lưu trữ.

### 13.1. DEFAULT không phải implicit cast

```sql
CREATE TABLE cast_lab.jobs (
    job_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    enabled boolean NOT NULL DEFAULT TRUE
);
```

`DEFAULT TRUE` được dùng khi cột `enabled` không được gán hoặc khi dùng từ khóa `DEFAULT`. Nó không có nhiệm vụ chuyển `NULL`, `''` hoặc một giá trị sai kiểu thành `TRUE`. Kiểm tra default và kiểm tra cast là hai cơ chế khác nhau.

### 13.2. CHECK, domain và enum

Một column hoặc domain có thể có ràng buộc bổ sung sau khi kiểu được xác định:

```sql
CREATE DOMAIN cast_lab.positive_amount AS numeric(12, 2)
    CHECK (VALUE >= 0);

CREATE TABLE cast_lab.invoices (
    invoice_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    amount cast_lab.positive_amount NOT NULL
);

INSERT INTO cast_lab.invoices(amount) VALUES (125.00);
```

Ép/ghi một giá trị về kiểu domain còn phải đáp ứng ràng buộc domain (theo ngữ cảnh kiểm tra). Không nên cast sang kiểu cơ sở để cố tình né những quy tắc dữ liệu mà hệ thống yêu cầu.

Với enum:

```sql
CREATE TYPE cast_lab.order_status AS ENUM
    ('draft', 'submitted', 'approved');

CREATE TABLE cast_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status cast_lab.order_status NOT NULL DEFAULT 'draft'
);
```

Literal `'submitted'` có thể được nhận là giá trị enum khi cột cung cấp ngữ cảnh, nhưng một cột `text` không tự động trở thành `cast_lab.order_status` trong mọi biểu thức. Muốn chuyển giá trị text đã kiểm tra thành enum:

```sql
SELECT 'submitted'::text::cast_lab.order_status;
```

Nếu văn bản không khớp nhãn enum, PostgreSQL báo lỗi. Việc chuyển kiểu không tạo nhãn enum mới.

## 14. Kiểu dữ liệu của tham số trong SQL và Java/JDBC

Nhiều lỗi ở production chỉ xuất hiện khi thay literal SQL bằng tham số chuẩn bị từ ứng dụng.

### 14.1. PREPARE có thể định nghĩa kiểu tham số

Trong `psql`:

```sql
PREPARE find_payment(numeric) AS
SELECT payment_id, amount
FROM cast_lab.payments
WHERE amount >= $1;

EXECUTE find_payment(100.00);
DEALLOCATE find_payment;
```

Tham số `$1` được khai báo kiểu `numeric`. Điều này giúp PostgreSQL chọn phép so sánh `numeric` phù hợp.

Nếu để kiểu tham số không xác định, PostgreSQL có thể suy luận từ ngữ cảnh; trong trường hợp thiếu thông tin hoặc quá nhiều cách diễn giải, lệnh chuẩn bị có thể lỗi.

```sql
PREPARE echo_integer(integer) AS
SELECT $1 + 1;

EXECUTE echo_integer(41);
DEALLOCATE echo_integer;
```

Ở đây kết quả là `42`, và chữ ký tham số không mơ hồ.

### 14.2. JDBC truyền đúng kiểu cho database

Giả sử có bảng `cast_lab.users(user_id uuid, username text)`, code JDBC nên truyền `UUID`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;

public String loadUsername(Connection connection, String rawId)
        throws SQLException {
    UUID userId = UUID.fromString(rawId);

    String sql = """
        SELECT username
        FROM cast_lab.users
        WHERE user_id = ?
        """;

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setObject(1, userId);

        try (ResultSet rs = ps.executeQuery()) {
            return rs.next() ? rs.getString("username") : null;
        }
    }
}
```

`UUID.fromString` xác thực định dạng đầu vào trước khi truyền tới database; PostgreSQL vẫn xác thực kiểu `uuid` và constraint. Nếu `rawId` không hợp lệ, Java ném `IllegalArgumentException`, cần được xử lý ở ranh giới API thành thông báo lỗi phù hợp.

Lỗi phổ biến là truyền một chuỗi dạng `varchar` rồi kỳ vọng PostgreSQL tự ép thành `uuid` trong `WHERE user_id = ?`. Tùy driver và chế độ binding, biểu thức có thể báo lỗi không tìm được toán tử. Chọn đúng kiểu Java/SQL từ đầu hoặc dùng cast tường minh khi bắt buộc là hướng rõ ràng hơn.

### 14.3. SQL CAST cho tham số được truyền dưới dạng chuỗi

Trong một số trường hợp tích hợp, client thực sự chỉ có tham số văn bản và SQL cần quy định cách phân tích:

```sql
-- Trong JDBC PreparedStatement, ? là placeholder do driver thay bằng bind parameter:
SELECT username
FROM cast_lab.users
WHERE user_id = CAST(? AS uuid);
```

Cách này rõ ngữ nghĩa, nhưng giá trị sai định dạng vẫn tạo lỗi PostgreSQL. Không tạo SQL bằng phép nối kiểu:

```java
// Tránh xây SQL từ dữ liệu người dùng như thế này:
String sql = "SELECT username FROM cast_lab.users WHERE user_id = '"
    + rawId + "'::uuid";
```

Cách nối chuỗi dễ gây SQL injection và làm mất sự tách biệt giữa câu SQL với dữ liệu. Hãy dùng `PreparedStatement` và placeholder.

### 14.4. NULL parameter cần có kiểu

`PreparedStatement.setNull` cần mã kiểu SQL:

```java
import java.sql.Types;

// Ví dụ cột nullable kiểu integer:
ps.setNull(1, Types.INTEGER);
```

Với `uuid` hoặc kiểu mở rộng PostgreSQL, cách bind có thể phụ thuộc JDBC driver; có thể dùng `setObject` với giá trị thuộc kiểu Java thích hợp khi không null, hoặc dùng cast rõ ràng tại placeholder nếu cần truyền null.

Khi nhận một `null` không có ngữ cảnh đủ rõ, server có thể không suy ra được kiểu tham số. Vì vậy, với hàm nạp chồng, `CASE`, mệnh đề `IS NULL` và câu SQL động, typing của tham số đặc biệt quan trọng.

## 15. Ảnh hưởng của CAST đến index và kế hoạch thực thi

Ép kiểu đúng có thể giữ nguyên ý nghĩa truy vấn nhưng thay đổi biểu thức planner phải xử lý.

Giả sử `cast_lab.users.user_id` là `uuid PRIMARY KEY`, PostgreSQL đã có B-tree index trên cột:

```sql
-- So sánh bằng giá trị đúng kiểu: phù hợp với index trên user_id.
SELECT *
FROM cast_lab.users
WHERE user_id = '550e8400-e29b-41d4-a716-446655440000'::uuid;
```

Nếu cast **cột** sang text:

```sql
SELECT *
FROM cast_lab.users
WHERE user_id::text = '550e8400-e29b-41d4-a716-446655440000';
```

điều kiện đã trở thành một biểu thức trên cột. B-tree index thông thường của `user_id` không nhất thiết được dùng trực tiếp cho biểu thức `user_id::text` như cách dùng toán tử bằng trên `uuid`. Ngoài ra, so sánh text khác ngữ nghĩa với so sánh UUID.

Với một cột văn bản lưu số:

```sql
CREATE TABLE cast_lab.legacy_prices (
    row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_amount text NOT NULL
);
```

Truy vấn:

```sql
SELECT *
FROM cast_lab.legacy_prices
WHERE raw_amount::numeric > 100;
```

buộc PostgreSQL diễn giải giá trị từng hàng thành số trước khi so sánh và có thể lỗi nếu có chuỗi sai định dạng. Index B-tree bình thường trên `raw_amount` không tương đương index trên biểu thức `raw_amount::numeric`.

**Giải pháp tốt nhất thường là sửa thiết kế kiểu cột**, ví dụ dùng `numeric` cho số tiền, `date` cho ngày, `uuid` cho UUID. Expression index có thể hữu ích trong một số trường hợp migration, nhưng tạo index trên cast lỗi với dữ liệu bẩn cũng thất bại, và index không sửa được mô hình dữ liệu sai.

### 15.1. Kiểm tra EXPLAIN trên dữ liệu đại diện

```sql
EXPLAIN
SELECT *
FROM cast_lab.users
WHERE user_id = '550e8400-e29b-41d4-a716-446655440000'::uuid;
```

`EXPLAIN` cho biết planner dự kiến dùng scan/index nào. `EXPLAIN (ANALYZE, BUFFERS)` thực sự chạy truy vấn để thu thập số liệu, nên chỉ sử dụng với truy vấn và môi trường phù hợp. Với bảng rất nhỏ, PostgreSQL có thể chọn sequential scan ngay cả khi index có thể dùng được; đừng kết luận index bị vô hiệu chỉ từ một kế hoạch trên vài hàng.

## 16. Tại sao không nên dùng cast để che giấu mô hình dữ liệu sai?

Một bảng có cột `amount_text text` chứa mọi số tiền dưới dạng chuỗi có thể “chạy được” nhờ `amount_text::numeric` trong mọi báo cáo. Tuy nhiên:

- Giá trị sai định dạng có thể làm query thất bại.
- Mọi phép tính phải lặp lại cast.
- So sánh/sắp xếp text có thể sai về số học nếu quên cast.
- Index và thống kê kiểu text không phản ánh tốt miền số thực.
- Việc cập nhật dữ liệu và xác thực dữ liệu trở nên phức tạp.

Các kiểu dữ liệu PostgreSQL có mục đích cụ thể: `numeric` cho giá trị chính xác, `date` cho ngày, `timestamptz` cho thời điểm, `uuid` cho ID, `boolean` cho đúng/sai, `jsonb` cho cấu trúc JSON. Hãy chuyển dữ liệu tại **ranh giới nhập** và lưu đúng kiểu càng sớm càng tốt.

### 16.1. Migration từ text sang kiểu đúng

Giả sử một bảng legacy `cast_lab.old_measurements` có cột `raw_reading text`. Quy trình thay đổi nên:

1. Khảo sát có bao nhiêu giá trị thiếu, trống, sai định dạng và ngoài khoảng mong muốn.
2. Xác định quy tắc làm sạch dữ liệu theo nghiệp vụ.
3. Tạo bản sao/migration có khả năng phục hồi và thử trên dữ liệu đại diện.
4. Chuyển cột với `USING` khi mọi hàng đã được chuẩn hóa.
5. Cập nhật code Java/API và bỏ các cast thừa khỏi truy vấn.

Ví dụ cú pháp với dữ liệu đã bảo đảm chỉ gồm số hợp lệ hoặc chuỗi rỗng:

```sql
-- Ví dụ minh họa: bảng old_measurements và dữ liệu đã được chuẩn bị.
ALTER TABLE cast_lab.old_measurements
    ALTER COLUMN raw_reading TYPE numeric(12, 2)
    USING NULLIF(trim(raw_reading), '')::numeric(12, 2);
```

`USING` quy định cách tính giá trị kiểu mới từ kiểu cũ. Nếu còn một chuỗi như `'not-a-number'`, migration sẽ lỗi; không nên thay thế tùy tiện thành `0`. Việc thay kiểu cột có thể cần viết lại bảng và index, lấy lock và ảnh hưởng downtime; cần có kế hoạch cho môi trường thật.

## 17. Lỗi thường gặp và cách nhận biết

| Triệu chứng | Nguyên nhân điển hình | Hướng xử lý |
| --- | --- | --- |
| `invalid input syntax for type integer` | Văn bản không phải số nguyên hợp lệ | Xác thực dữ liệu, xử lý chuỗi rỗng/sentinel, cast sau khi làm sạch |
| `integer out of range` | Giá trị vượt phạm vi kiểu đích | Chọn kiểu đủ rộng, kiểm tra giới hạn và quy tắc nhập |
| `operator does not exist: integer = text` | Hai toán hạng đã có kiểu không có toán tử/cast ngầm phù hợp | Truyền đúng kiểu hoặc cast tường minh đúng ngữ nghĩa |
| `function ... does not exist` | Chữ ký hàm không khớp các kiểu đầu vào | Kiểm tra overload và cast đối số phù hợp |
| `function ... is not unique` | Nhiều overload cùng có thể được chọn | Cast rõ đối số cần phân biệt |
| `CASE types ... cannot be matched` | Các nhánh không thống nhất được kiểu | Quy định một kiểu kết quả chung và cast từng nhánh |
| Kết quả phép chia mất phần lẻ | Hai toán hạng nguyên | Ép `numeric` trước phép chia |
| Số tiền có sai số | Dùng `real`/`double precision` thay vì kiểu chính xác | Cân nhắc `numeric` và quy tắc làm tròn nghiệp vụ |
| Thời gian lệch vài giờ | Nhầm `timestamp` với `timestamptz` hoặc dùng sai `TimeZone` | Chỉ rõ ý nghĩa thời điểm, offset và vùng giờ |
| Query có cast chậm | Cast trên cột, index không phù hợp hoặc dữ liệu sai kiểu | Sửa typing, xem `EXPLAIN`, cân nhắc index phù hợp |
| JDBC query theo UUID thất bại | Gửi tham số `varchar` thay vì `uuid` | Dùng `java.util.UUID` / bind đúng kiểu hoặc cast placeholder |
| `COALESCE` vẫn lỗi với chuỗi sai kiểu | Cast bị lỗi trước khi có kết quả để COALESCE | Xác thực/làm sạch đầu vào thay vì coi COALESCE là bắt lỗi |
| `UNION` với NULL và số lỗi | Một nhánh trung gian đã giải kiểu khác | Gắn kiểu cho `NULL`/literal và các nhánh `UNION` |

Hãy bắt đầu chẩn đoán bằng **kiểu của biểu thức thực tế**, kiểu cột trong catalog và thông điệp lỗi đầy đủ, thay vì sửa bằng `::text` hàng loạt.

## 18. Thực hành tổng hợp

Thực hành trong một database riêng với schema `cast_lab` đã tạo trong bài. Các ví dụ không yêu cầu xóa hoặc sửa dữ liệu production.

### Bài 1: Quan sát kiểu của literal và phép toán

```sql
SELECT
    pg_typeof(1) AS a,
    pg_typeof(1.0) AS b,
    pg_typeof(1::bigint) AS c,
    pg_typeof(1 + 2.5) AS d;

SELECT
    7 / 2 AS wrong_ratio,
    7::numeric / 2 AS correct_ratio;
```

Giải thích vì sao `wrong_ratio` mất phần thập phân và cách quyết định kiểu dữ liệu mong muốn.

### Bài 2: Phân biệt unknown literal với text có kiểu

```sql
SELECT 1 = '1';

-- Thử để quan sát lỗi chọn toán tử:
SELECT 1 = '1'::text;

-- Dùng so sánh số rõ ràng:
SELECT 1 = ('1'::text)::integer;
```

Phân tích sự khác nhau giữa literal `'1'` và biểu thức đã có kiểu `text`.

### Bài 3: CAST với tiền tệ

```sql
SELECT
    '120.456'::numeric(10, 2) AS rounded_price,
    round(120.456::numeric, 2) AS rounded_by_function;

SELECT
    3 / 8 * 100 AS integer_percentage,
    round(3::numeric / 8 * 100, 2) AS decimal_percentage;
```

So sánh kết quả, kiểm tra cách làm tròn và lý do phải cast trước phép chia.

### Bài 4: CASE, COALESCE và UNION

```sql
SELECT
    pg_typeof(
        CASE WHEN TRUE THEN 10 ELSE 11.5 END
    ) AS case_type,
    pg_typeof(COALESCE(NULL, 1, 2.5)) AS coalesce_type;

SELECT NULL::numeric AS amount
UNION ALL
SELECT 100::integer
UNION ALL
SELECT 200.5::numeric;
```

Thử thay một nhánh thành `'unknown'::text` rồi giải thích vì sao kết quả chọn kiểu thay đổi hoặc có lỗi.

### Bài 5: Thời điểm và múi giờ

```sql
BEGIN;
    SET LOCAL TIME ZONE 'UTC';
    SELECT
        '2026-11-14 09:00:00+07'::timestamptz AS instant_utc,
        '2026-11-14 09:00:00'::timestamp AS local_only,
        ('2026-11-14 09:00:00'::timestamp
           AT TIME ZONE 'Asia/Ho_Chi_Minh') AS local_to_instant;
COMMIT;
```

Giải thích vì sao hai biểu thức có giá trị giờ hiển thị khác nhau nhưng có thể cùng mô tả một thời điểm.

### Bài 6: Dữ liệu JSONB và truy vấn có tham số đúng kiểu

```sql
SELECT
    ('{"qty":3}'::jsonb -> 'qty') AS json_value,
    ('{"qty":3}'::jsonb ->> 'qty')::integer AS integer_value;

PREPARE user_by_id(uuid) AS
SELECT username FROM cast_lab.users WHERE user_id = $1;

EXECUTE user_by_id('550e8400-e29b-41d4-a716-446655440000');
DEALLOCATE user_by_id;
```

Thử thay `qty` thành chuỗi `"three"` trên môi trường thực hành để quan sát lỗi chuyển kiểu, và nêu cách kiểm soát lỗi tại đầu vào.

## 19. Những nguyên tắc cần nhớ

- **Ép kiểu tường minh** với `CAST(expr AS type)` hoặc `expr::type` khi ý nghĩa của phép chuyển cần rõ ràng, nhất là với số, ngày giờ, UUID và dữ liệu JSON.
- **Suy luận kiểu** diễn ra khi PostgreSQL phân tích literal `unknown`, toán tử, hàm, `CASE`, `COALESCE`, `UNION`, `VALUES` và tham số; đây không phải một cơ chế tự động biến mọi text thành mọi kiểu.
- **Chuyển đổi ngầm** chỉ được phép trong một số ngữ cảnh và theo các cast PostgreSQL hỗ trợ. `pg_cast` giúp tìm hiểu một phần quy tắc, nhưng không liệt kê mọi chuyển đổi đặc biệt.
- **Kiểu quyết định kết quả toán học**: phép chia nguyên bỏ phần thập phân; kiểu `numeric` và kiểu số dấu chấm động có đặc tính độ chính xác khác nhau.
- **Cast có thể làm mất dữ liệu hoặc thất bại** do làm tròn, tràn số, cắt chuỗi, cú pháp đầu vào không hợp lệ hoặc ngữ nghĩa múi giờ. Kiểm tra dữ liệu trước khi chuyển.
- **Ghi dữ liệu đúng kiểu từ đầu**. Nếu database lưu số bằng text hoặc thời điểm bằng chuỗi, các cast lặp lại là dấu hiệu nên xem lại mô hình và quá trình nhập dữ liệu.
- **Ứng dụng phải bind tham số đúng kiểu**. Trong JDBC/JPA, sử dụng kiểu Java phù hợp với kiểu PostgreSQL giúp tránh lỗi chọn toán tử, giảm cast trên cột và giữ khả năng dùng index.
- **Đừng tối ưu hóa bằng cách đoán**: dùng `pg_typeof` để quan sát kết quả biểu thức và `EXPLAIN` để đánh giá kế hoạch khi cần.

Hiểu cơ chế chuyển kiểu giúp viết SQL có kết quả dự đoán được, giữ toàn vẹn dữ liệu và phân biệt rõ lỗi dữ liệu với lỗi phân giải biểu thức. Một câu lệnh SQL tốt không chỉ chạy thành công với dữ liệu mẫu mà còn mô tả chính xác **kiểu dữ liệu mà hệ thống cam kết lưu giữ và xử lý**.
