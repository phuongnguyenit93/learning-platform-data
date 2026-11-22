# Số nguyên, numeric và số dấu phẩy động trong PostgreSQL

## 1. Cùng là số, vì sao PostgreSQL cần nhiều kiểu dữ liệu?

Trong PostgreSQL, những giá trị trông giống nhau trong SQL có thể mang ý nghĩa rất khác nhau:

- `25` có thể là **số lượng sản phẩm** và nên lưu dưới dạng số nguyên.
- `125000.50` có thể là **đơn giá** và cần tính toán thập phân chính xác.
- `23.687491` có thể là **nhiệt độ đo bởi cảm biến** và chấp nhận sai số xấp xỉ.
- `9000000000000000000` là số nguyên rất lớn, vượt giới hạn của kiểu `integer` thông thường.

PostgreSQL cung cấp ba nhóm quan trọng:

1. **Số nguyên**: `smallint`, `integer`, `bigint`, lưu số nguyên chính xác trong phạm vi xác định.
2. **Số thập phân chính xác**: `numeric`, còn có tên tương đương `decimal`, phù hợp cho tiền tệ và những quy tắc cần độ chính xác thập phân.
3. **Số dấu phẩy động nhị phân**: `real` và `double precision`, tối ưu cho nhiều phép tính khoa học, đo lường và dữ liệu xấp xỉ, nhưng **không đảm bảo biểu diễn chính xác mọi số thập phân**.

Ví dụ hai cột:

```sql
CREATE TABLE product_metrics (
    price numeric(12,2) NOT NULL,
    measured_temperature double precision NOT NULL
);
```

Đơn giá cần đảm bảo `0.10 + 0.20` theo số thập phân cho kết quả tương ứng với 0.30. Nhiệt độ cảm biến thường vốn có sai số thiết bị và phép đo; dùng kiểu dấu phẩy động có thể phù hợp hơn về tốc độ và phạm vi giá trị.

**Chọn kiểu số không chỉ để tiết kiệm bộ nhớ.** Nó quyết định tính chính xác, phạm vi giá trị, hành vi làm tròn, lỗi tràn số, kết quả phép chia, khả năng tổng hợp và sự nhất quán của nghiệp vụ.

## 2. Bảng tổng quan các kiểu số

| Kiểu PostgreSQL | Kích thước lưu trữ điển hình | Phạm vi/độ chính xác | Phù hợp |
| --- | --- | --- | --- |
| `smallint` | 2 byte | Số nguyên có dấu, từ −32.768 đến 32.767 | Số đếm nhỏ khi phạm vi thật sự được đảm bảo |
| `integer` / `int` / `int4` | 4 byte | Từ −2.147.483.648 đến 2.147.483.647 | Số lượng, chỉ số, nhiều loại ID |
| `bigint` / `int8` | 8 byte | Từ −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | Bộ đếm lớn, ID tăng dài hạn |
| `numeric(p,s)` / `decimal(p,s)` | Biến đổi | Chính xác thập phân theo precision và scale khai báo | Giá, tiền, tỷ lệ chính xác |
| `numeric` không giới hạn p/s khi khai báo | Biến đổi | Số thập phân chính xác trong giới hạn thực thi của PostgreSQL | Tính toán cần nhiều chữ số |
| `real` / `float4` | 4 byte | Khoảng 6 chữ số thập phân có nghĩa | Dữ liệu đo xấp xỉ khi sai số chấp nhận được |
| `double precision` / `float8` | 8 byte | Khoảng 15 chữ số thập phân có nghĩa | Tính toán số học, đo lường cần độ chính xác cao hơn `real` |

Hai lưu ý quan trọng:

- `smallint`, `integer` và `bigint` là **số nguyên có dấu**. PostgreSQL không có bản tương đương trực tiếp `UNSIGNED INT` như một số hệ quản trị khác.
- `real` và `double precision` có thể biểu diễn phạm vi giá trị rất lớn/nhỏ, nhưng **phạm vi rộng không đồng nghĩa chính xác tuyệt đối**. Một giá trị như `0.1` thường không có biểu diễn chính xác hữu hạn trong cơ số 2.

### 2.1. Tên kiểu đồng nghĩa

PostgreSQL chấp nhận nhiều tên gọi:

```sql
SELECT
    15::smallint AS small_value,
    15::integer AS integer_value,
    15::int AS int_alias,
    15::bigint AS bigint_value,
    15.25::numeric AS numeric_value,
    15.25::decimal AS decimal_alias,
    15.25::real AS real_value,
    15.25::double precision AS double_value;
```

`decimal` về cơ bản là cách viết tương đương `numeric` trong PostgreSQL. Với số dấu phẩy động, `float4` là alias của `real` và `float8` là alias của `double precision`. Những alias này thuận tiện khi đọc catalog hoặc code cũ, nhưng khi thiết kế bài học/schema nên ưu tiên tên dễ hiểu như `integer` và `double precision`.

## 3. Nhóm số nguyên: `smallint`, `integer`, `bigint`

### 3.1. Khi nào dùng số nguyên?

Số nguyên phù hợp cho những giá trị không có phần thập phân theo bản chất nghiệp vụ:

- Số lượng hàng tồn kho.
- Số sản phẩm mua trong một dòng đơn.
- Mã định danh hoặc bộ đếm tăng.
- Số lần truy cập.
- Số giây nguyên hoặc số mili giây nguyên khi đơn vị được thiết kế rõ.

Ví dụ:

```sql
CREATE TABLE inventory_counts (
    product_id bigint PRIMARY KEY,
    on_hand integer NOT NULL CHECK (on_hand >= 0),
    reserved integer NOT NULL DEFAULT 0 CHECK (reserved >= 0)
);
```

`on_hand` và `reserved` là **số lượng đơn vị nguyên**. Ràng buộc `CHECK` diễn đạt quy tắc không được âm; kiểu `integer` một mình vẫn cho phép số âm.

### 3.2. Giới hạn của từng kiểu

```text
smallint
  -32768 .............................. 32767

integer
  -2147483648 ......................... 2147483647

bigint
  -9223372036854775808 ... 9223372036854775807
```

Ví dụ nhập dữ liệu hợp lệ:

```sql
SELECT
    32767::smallint AS max_smallint,
    2147483647::integer AS max_integer,
    9223372036854775807::bigint AS max_bigint;
```

Nếu cố ép giá trị vượt phạm vi:

```sql
-- Cố tình gây lỗi:
SELECT 32768::smallint;

-- Cố tình gây lỗi:
SELECT 2147483648::integer;
```

PostgreSQL báo lỗi số nằm ngoài phạm vi của kiểu yêu cầu; nó không tự cho phép một `integer` giữ vô hạn chữ số chỉ vì nguồn đầu vào lớn.

### 3.3. `integer` hay `bigint` cho ID?

`integer` dùng 4 byte, `bigint` dùng 8 byte. Nếu ID có thể tăng trong nhiều năm hoặc số hàng dự kiến rất lớn, `bigint` thường là lựa chọn hợp lý cho khóa tăng.

```sql
CREATE TABLE customer_accounts (
    account_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name text NOT NULL
);
```

`GENERATED ... AS IDENTITY` cung cấp giá trị định danh thông qua sequence. Có thể gặp kiểu `serial`/`bigserial` trong hệ thống cũ:

```sql
-- Cách khai báo legacy tương đối phổ biến:
CREATE TABLE legacy_example (
    id bigserial PRIMARY KEY
);
```

`serial` và `bigserial` là cách viết tiện ích liên quan đến sequence, **không phải các kiểu số hoàn toàn độc lập** như `integer` và `bigint`.

**Identity/sequence không đảm bảo số ID liên tục không có khoảng trống.** Sequence có thể tiêu thụ giá trị qua transaction rollback hoặc va chạm, và PostgreSQL không hoàn tác lần cấp giá trị sequence theo cùng cách hoàn tác hàng dữ liệu. Không dùng ID tăng làm bằng chứng số lượng bản ghi hoặc dùng nó cho số hóa đơn bắt buộc liên tục theo pháp lý nếu chưa thiết kế riêng.

### 3.4. Chú ý phép tính trung gian bị tràn

Giả sử nhân hai số `integer`:

```sql
-- Cố tình có nguy cơ integer out of range vì phép nhân
-- xảy ra trong kiểu integer trước khi cast ra bigint:
SELECT (50000::integer * 50000::integer)::bigint;
```

Kết quả toán học là `2.500.000.000`, vượt giới hạn `integer`. Việc ép kiểu **sau** phép nhân không cứu được phép toán đã tràn.

Đúng hơn:

```sql
SELECT 50000::bigint * 50000::integer AS product;
```

Khi một toán hạng đã là `bigint`, PostgreSQL có thể chọn phép nhân và kiểu kết quả phù hợp với phạm vi lớn hơn.

Nhưng `bigint` cũng có giới hạn. Nếu có thể vượt giới hạn 64 bit, cân nhắc `numeric` trước khi nhân:

```sql
SELECT
    9000000000000000000::numeric
    * 1000000000000000000::numeric AS huge_product;
```

**Quy tắc:** chuyển lên kiểu đủ lớn **trước khi** thực hiện phép toán gây tràn.

### 3.5. Thay đổi giá trị có điều kiện

```sql
UPDATE inventory_counts
SET on_hand = on_hand - 2
WHERE product_id = 101
  AND on_hand >= 2
RETURNING product_id, on_hand;
```

Việc dùng một câu `UPDATE ... WHERE` giúp kiểm tra và ghi dựa trên dữ liệu tại thời điểm cập nhật, tránh cách làm ứng dụng đọc số lượng rồi tự tính và ghi mà không xem xét đồng thời. Với nghiệp vụ giữ hàng nhiều bước, vẫn cần thiết kế transaction và khóa phù hợp.

## 4. Phép chia số nguyên: kết quả bị bỏ phần thập phân

Một khác biệt dễ gây lỗi giữa kiểu số:

```sql
SELECT
    5 / 2 AS integer_division,
    5.0 / 2 AS decimal_division,
    5::numeric / 2 AS explicit_numeric_division;
```

Kết quả tiêu biểu:

| Biểu thức | Kết quả | Lý do |
| --- | ---: | --- |
| `5 / 2` | `2` | Hai toán hạng số nguyên: chia số nguyên |
| `5.0 / 2` | `2.500000...` | Literal 5.0 là số thập phân numeric trong ngữ cảnh thông thường |
| `5::numeric / 2` | `2.500000...` | Ép kiểu sang numeric trước khi chia |

Với phép chia nguyên, PostgreSQL bỏ phần thập phân bằng cách **truncation về phía 0**, không phải luôn lấy floor:

```sql
SELECT
    -5::integer / 2::integer AS negative_integer_division,
    floor(-5::numeric / 2) AS numeric_floor;
```

Kết quả:

- `-5 / 2` trong phép chia số nguyên là `-2`.
- `floor(-2.5)` là `-3`.

Điều này quan trọng nếu bạn dùng phép chia để tính tỷ lệ:

```sql
-- Không phù hợp nếu muốn kết quả phần trăm có phần thập phân:
SELECT 3 / 4 * 100 AS percentage_wrong;

-- Chuyển kiểu trước phép chia:
SELECT 3::numeric / 4 * 100 AS percentage_correct;
```

Kết quả tương ứng là `0` và `75.000...`. Với bảng có hai cột `success_count integer` và `total_count integer`, biểu thức `success_count / total_count` cũng gặp vấn đề tương tự nếu không ép kiểu.

### 4.1. Tránh chia cho 0

```sql
-- Cố tình gây lỗi:
SELECT 10 / 0;
```

Có thể dùng `NULLIF` để tránh mẫu số bằng 0:

```sql
SELECT
    10::numeric / NULLIF(0, 0) AS safe_ratio;
```

`NULLIF(0, 0)` trả `NULL`, nên phép chia trả `NULL` thay vì lỗi chia cho 0. Tuy nhiên, `NULL` cần được xử lý rõ ở tầng báo cáo: nó có thể biểu thị “không xác định”, không phải 0%.

### 4.2. Tỷ lệ từ dữ liệu tổng hợp

```sql
SELECT
    7::numeric / NULLIF(20, 0) AS ratio,
    round(100 * 7::numeric / NULLIF(20, 0), 2) AS percent;
```

Kết quả: tỷ lệ `0.35` và phần trăm `35.00`. Có thể thiết kế hiển thị phần trăm bằng cách nhân 100 ở lớp trình bày, nhưng phải nhất quán giữa API và cơ sở dữ liệu: lưu `0.35` dưới tên `rate` khác lưu `35` dưới tên `percentage_points`.

## 5. `numeric` / `decimal`: số thập phân chính xác

### 5.1. Khi nào chọn numeric?

Dùng `numeric` khi nghiệp vụ yêu cầu tính toán theo hệ thập phân mà không chấp nhận sai số biểu diễn nhị phân của floating point, ví dụ:

- Đơn giá, thành tiền, số tiền thuế.
- Số dư kế toán.
- Phí, tỷ lệ chiết khấu và lãi suất cần độ chính xác quy định.
- Kết quả tính toán có nhiều chữ số chính xác.

```sql
CREATE TABLE prices (
    product_code text PRIMARY KEY,
    price numeric(12,2) NOT NULL CHECK (price >= 0),
    tax_rate numeric(7,6) NOT NULL CHECK (tax_rate >= 0 AND tax_rate <= 1)
);
```

`numeric(12,2)` phù hợp cho giá có tối đa 12 chữ số tổng và 2 chữ số sau dấu thập phân, trong giới hạn của khai báo. `numeric(7,6)` giữ 6 chữ số sau dấu thập phân cho tỷ lệ như `0.080000`.

### 5.2. Precision và scale nghĩa là gì?

Khai báo tổng quát:

```sql
numeric(precision, scale)
```

- **Precision (`p`):** tổng số chữ số có nghĩa được cho phép trong số theo khai báo.
- **Scale (`s`):** số chữ số sau dấu thập phân mà kiểu được thiết kế để lưu/ép giá trị đến đó.

Một số ví dụ thông dụng khi `0 <= s <= p`:

| Kiểu | Số chữ số bên trái dấu thập phân tối đa | Số chữ số sau dấu thập phân | Ví dụ hợp lệ |
| --- | ---: | ---: | --- |
| `numeric(5,2)` | 3 | 2 | `999.99` |
| `numeric(8,3)` | 5 | 3 | `12345.678` |
| `numeric(12,2)` | 10 | 2 | `1234567890.12` |
| `numeric(7,6)` | 1 | 6 | `0.123456` |
| `numeric(18,8)` | 10 | 8 | `1234567890.12345678` |

Ví dụ:

```sql
SELECT
    123.45::numeric(5,2) AS accepted,
    12.345::numeric(5,2) AS rounded;
```

Giá trị `12.345` được làm tròn theo scale 2 chữ số thành `12.35`.

Nếu vượt giới hạn chữ số phần nguyên:

```sql
-- Cố tình gây numeric field overflow:
SELECT 1000.00::numeric(5,2);
```

`numeric(5,2)` chỉ cho 3 chữ số bên trái dấu thập phân, không chứa được `1000.00`.

### 5.3. Thứ tự làm tròn rồi kiểm tra phạm vi

Khi ép một giá trị vào `numeric(p,s)`, PostgreSQL làm tròn về scale được khai báo, sau đó giá trị phải phù hợp giới hạn chữ số được phép.

```sql
SELECT 999.994::numeric(5,2) AS still_fits;
```

Kết quả là `999.99`, nằm trong phạm vi. Nhưng:

```sql
-- Sau làm tròn thành 1000.00 sẽ vượt phạm vi numeric(5,2):
SELECT 999.995::numeric(5,2);
```

Kết quả được dự kiến là lỗi vượt giới hạn. Do đó, một số đầu vào ở gần ngưỡng có thể bị từ chối **sau khi làm tròn**.

### 5.4. Scale không đồng nghĩa phép kiểm tra nhập đúng số lẻ

Giả sử cột:

```sql
amount numeric(12,2)
```

Nếu ứng dụng gửi `12.345`, PostgreSQL có thể **làm tròn thành `12.35`** khi ép vào kiểu cột. Nếu yêu cầu nghiệp vụ là “phải từ chối giá trị có quá hai chữ số thập phân”, thì kiểu `numeric(12,2)` **một mình không đủ để bác bỏ đầu vào đó**. Cần xác thực trước khi giá trị bị làm tròn, trong ứng dụng hoặc trong một bước nhập dữ liệu/staging có giữ nguyên giá trị gốc.

Điều này đặc biệt quan trọng khi phân biệt:

- **Chuẩn hóa số tiền bằng làm tròn**: chấp nhận đầu vào nhiều số lẻ và lưu theo chính sách.
- **Từ chối dữ liệu không đúng đơn vị tiền**: không chấp nhận số có nhiều chữ số lẻ hơn cho phép.

### 5.5. `numeric` không khai báo precision và scale

PostgreSQL cho phép:

```sql
CREATE TABLE exact_measurements (
    measure_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exact_value numeric NOT NULL
);
```

`numeric` không kèm `(p,s)` dùng độ chính xác và scale của giá trị trong phạm vi giới hạn triển khai, không tự ép mọi đầu vào về hai chữ số thập phân.

```sql
INSERT INTO exact_measurements (exact_value)
VALUES
    (0.123456789012345678901234567890),
    (12345678901234567890.123456789);
```

Loại này hữu ích khi cần xử lý số thập phân rất dài nhưng thường tốn tài nguyên hơn các kiểu số cố định. Với giá/tiền có quy tắc scale rõ ràng, hãy khai báo `numeric(p,s)` phù hợp để tài liệu hóa miền giá trị.

### 5.6. Scale âm và scale lớn hơn precision

Trong **PostgreSQL 15 trở lên**, cú pháp `numeric` cho phép một số cấu hình mở rộng như **scale âm**, dùng để làm tròn về bên trái dấu thập phân.

```sql
-- PostgreSQL 15+:
SELECT 12345::numeric(5,-2) AS rounded_to_hundreds;
```

Giá trị được làm tròn đến hàng trăm, ví dụ `12300`.

Đây là một tính năng khác với việc thay đổi số chữ số sau dấu phẩy khi lưu tiền. Không nên dùng scale âm cho giá trị tiền có yêu cầu lưu đến đơn vị nhỏ nhất. Cần kiểm tra phiên bản PostgreSQL khi dùng đặc tính này trong hệ thống cũ.

## 6. Làm tròn với `numeric`

### 6.1. `round`: làm tròn theo số chữ số

```sql
SELECT
    round(12.345::numeric, 2) AS rounded_two_decimals,
    round(12.344::numeric, 2) AS rounded_down,
    round(-12.345::numeric, 2) AS rounded_negative;
```

Kết quả theo quy tắc làm tròn của PostgreSQL `numeric`:

| Biểu thức | Kết quả |
| --- | ---: |
| `round(12.345::numeric, 2)` | `12.35` |
| `round(12.344::numeric, 2)` | `12.34` |
| `round(-12.345::numeric, 2)` | `-12.35` |

Với giá trị nằm chính xác **giữa hai lựa chọn làm tròn** (*tie*), PostgreSQL `numeric` làm tròn theo quy tắc **ra xa 0** (*away from zero*).

```sql
SELECT
    round(2.5::numeric) AS positive_half,
    round(-2.5::numeric) AS negative_half;
```

Kết quả là `3` và `-3`.

Trong tài chính, không phải doanh nghiệp nào cũng dùng cùng một quy tắc làm tròn. Nếu yêu cầu **banker's rounding / ties-to-even**, không nên tự giả định `round(numeric, s)` mặc định đáp ứng chính sách đó. Phải thiết kế chính sách làm tròn của nghiệp vụ và triển khai/kiểm chứng nhất quán giữa ứng dụng và database.

### 6.2. `trunc`: cắt phần thập phân, không làm tròn

```sql
SELECT
    trunc(12.349::numeric, 2) AS trunc_positive,
    trunc(-12.349::numeric, 2) AS trunc_negative;
```

Kết quả:

- `12.34`, không phải `12.35`.
- `-12.34`, vì `trunc` cắt về phía 0.

So sánh:

```sql
SELECT
    round(19.999::numeric, 2) AS rounded,
    trunc(19.999::numeric, 2) AS truncated;
```

`round` cho `20.00`, còn `trunc` cho `19.99`.

Không dùng `trunc` và `round` thay cho nhau chỉ vì kết quả của nhiều ví dụ thông thường trùng nhau.

### 6.3. `floor` và `ceil`

```sql
SELECT
    floor(2.8::numeric) AS floor_positive,
    ceil(2.2::numeric) AS ceil_positive,
    floor(-2.2::numeric) AS floor_negative,
    ceil(-2.8::numeric) AS ceil_negative;
```

Kết quả theo thứ tự là `2`, `3`, `-3` và `-2`.

- `floor(x)`: số nguyên gần nhất **không lớn hơn x**.
- `ceil(x)`: số nguyên gần nhất **không nhỏ hơn x**.
- `trunc(x)`: cắt phần lẻ về phía 0.

Khi tính số kiện cần để chứa sản phẩm, `ceil(quantity / capacity)` chỉ đúng nếu phép chia có kết quả không bị cắt phần thập phân **trước** khi `ceil` được gọi:

```sql
SELECT
    ceil(7::numeric / 3) AS boxes_needed;
```

Kết quả là `3`; còn `ceil(7 / 3)` đã nhận kết quả số nguyên `2` từ phép chia nên có thể cho đáp án sai.

## 7. Nhóm số dấu phẩy động: `real` và `double precision`

### 7.1. “Dấu phẩy động” nghĩa là gì?

`real` và `double precision` trong PostgreSQL thường được triển khai theo số dấu phẩy động nhị phân IEEE 754, với số bit cho phần trị và số mũ có giới hạn.

Khác với `numeric` (biểu diễn thập phân chính xác), floating point sử dụng biểu diễn **xấp xỉ nhị phân**. Nhiều số thập phân như `0.1` và `0.2` không có biểu diễn hữu hạn chính xác ở dạng nhị phân.

Điều này tương tự việc số `1/3` không có dạng thập phân hữu hạn:

```text
1 / 3 = 0.333333333333333...
```

Ngược lại, `0.1` không có dạng nhị phân hữu hạn, nên `double precision` phải lưu một giá trị rất gần nó.

### 7.2. `real` và `double precision` khác nhau ra sao?

| Thuộc tính | `real` | `double precision` |
| --- | --- | --- |
| Kích thước | 4 byte | 8 byte |
| Độ chính xác khoảng | 6 chữ số thập phân có nghĩa | 15 chữ số thập phân có nghĩa |
| Phạm vi số mũ | Hẹp hơn | Rộng hơn |
| Sai số biểu diễn | Lớn hơn tương đối | Thường nhỏ hơn `real` |
| Ứng dụng | Cảm biến không cần quá nhiều chữ số, dữ liệu khoa học khối lượng lớn | Đo lường, thuật toán số học tổng quát |
| Tính chính xác thập phân tuyệt đối | Không | Không |

Ví dụ:

```sql
SELECT
    12345678.9::real AS measured_real,
    12345678.9::double precision AS measured_double;
```

Với `real`, chữ số cuối có thể bị thay đổi đáng kể vì số có nhiều chữ số có nghĩa hơn khả năng chính xác của kiểu. `double precision` giữ được nhiều chữ số chính xác hơn, nhưng vẫn là xấp xỉ nhị phân.

**Không suy luận rằng số được in đẹp trong psql thì giá trị lưu bên trong đã chính xác tuyệt đối.** PostgreSQL có cơ chế định dạng kết quả floating point khi hiển thị; hình thức chữ số in ra và giá trị binary lưu trữ là hai vấn đề.

### 7.3. Thử `0.1 + 0.2`

```sql
SELECT
    0.1::numeric + 0.2::numeric AS exact_decimal_sum,
    0.1::double precision + 0.2::double precision AS approximate_sum;
```

Với `numeric`, giá trị toán học là `0.3` một cách chính xác theo số thập phân. Với `double precision`, kết quả thường gần `0.30000000000000004` trên những hệ thống IEEE 754 phổ biến.

So sánh bằng tuyệt đối:

```sql
SELECT
    (0.1::numeric + 0.2::numeric = 0.3::numeric)
        AS numeric_equal,
    (0.1::double precision + 0.2::double precision
        = 0.3::double precision)
        AS float_equal;
```

Thông thường:

- `numeric_equal` là `true`.
- `float_equal` là `false` với phép tính IEEE 754 phổ biến.

Đây không phải “lỗi PostgreSQL”; đó là tính chất của **số dấu phẩy động nhị phân**.

### 7.4. So sánh floating point bằng ngưỡng sai số

Nếu bạn cần kiểm tra hai kết quả đo có **gần nhau trong sai số cho phép**, hãy diễn đạt ngưỡng từ nghiệp vụ:

```sql
SELECT
    abs(
        (0.1::double precision + 0.2::double precision)
        - 0.3::double precision
    ) < 1e-12::double precision AS approximately_equal;
```

Ví dụ dùng ngưỡng tuyệt đối `1e-12` chỉ để minh họa. Với giá trị có độ lớn khác nhau nhiều, thường cần xem xét cả **sai số tuyệt đối** và **sai số tương đối**.

Một cách kiểm tra gần đúng thường gặp:

```sql
SELECT
    abs(a - b) <= 1e-9::double precision
        + 1e-6::double precision
          * greatest(abs(a), abs(b)) AS close_enough
FROM (
    SELECT
        0.1::double precision + 0.2::double precision AS a,
        0.3::double precision AS b
) AS values_to_compare;
```

Các hằng ngưỡng phải dựa vào sai số cảm biến, quy tắc chấp nhận kết quả hoặc yêu cầu thuật toán, không sao chép một công thức epsilon cho mọi dự án.

**Nếu số đó thực sự là tiền, cách giải quyết không phải so sánh tiền với epsilon thật nhỏ; thông thường nên dùng `numeric` ngay từ đầu.**

### 7.5. Không dùng floating point cho khóa nghiệp vụ đòi hỏi bằng nhau tuyệt đối

Ví dụ không nên dùng `double precision` để biểu diễn “giá niêm yết đúng 0.30” rồi dựa vào phép `= 0.3` để tìm bản ghi. Giá tiền nên dùng `numeric`; mã ID nên dùng `bigint` hoặc kiểu định danh tương ứng; số đo xấp xỉ mới phù hợp hơn với floating point.

Dùng float trong cột có index không phải bị cấm, nhưng phải hiểu ý nghĩa của các toán tử so sánh và phân bố dữ liệu trước khi thiết kế truy vấn chính xác theo một giá trị đo.

## 8. Giá trị đặc biệt: `NaN`, `Infinity` và `-Infinity`

PostgreSQL hỗ trợ các giá trị đặc biệt của floating point, chẳng hạn:

```sql
SELECT
    'NaN'::double precision AS not_a_number,
    'Infinity'::double precision AS positive_infinity,
    '-Infinity'::double precision AS negative_infinity;
```

`NaN` (*Not a Number*) thường xuất hiện trong mô hình số học khi một kết quả không có giá trị số thông thường. `Infinity` và `-Infinity` đại diện các giá trị vô cực theo ngữ nghĩa kiểu hỗ trợ.

PostgreSQL cũng hỗ trợ các giá trị đặc biệt tương ứng trong `numeric` trên những phiên bản hiện đại, chẳng hạn:

```sql
SELECT
    'NaN'::numeric AS numeric_nan,
    'Infinity'::numeric AS numeric_infinity;
```

**Giới hạn quan trọng:** giá trị vô cực của `numeric` không thể lưu trong kiểu `numeric(p,s)` có precision hữu hạn được khai báo; cách xử lý và chấp nhận các giá trị này còn phụ thuộc phiên bản, kiểu cột và ràng buộc.

### 8.1. So sánh `NaN` trong PostgreSQL

Khác với một số kỳ vọng trực tiếp từ IEEE 754, PostgreSQL định nghĩa quy tắc sắp xếp/so sánh cho `NaN` nhằm hỗ trợ index và `ORDER BY`. Với các kiểu số hỗ trợ, PostgreSQL coi `NaN` **bằng chính nó** và lớn hơn những giá trị không phải `NaN` theo các phép so sánh thích hợp.

```sql
SELECT
    ('NaN'::double precision = 'NaN'::double precision)
        AS pg_nan_equals_nan,
    ('NaN'::numeric > 1000000::numeric)
        AS pg_nan_sorts_high;
```

Đây là quy tắc **cụ thể của PostgreSQL**, không nên đem trực tiếp áp vào mọi thư viện số học trong ứng dụng.

### 8.2. Rủi ro cho ràng buộc tài chính

Một cột:

```sql
amount numeric NOT NULL CHECK (amount >= 0)
```

không tự diễn đạt “mọi giá trị đều là số hữu hạn hợp lệ”. Vì `NaN` có ngữ nghĩa so sánh đặc biệt, nó có thể vượt qua những điều kiện so sánh tưởng như hiển nhiên.

Nếu nghiệp vụ không chấp nhận giá trị `NaN`, hãy đưa quy tắc đó vào validation/ràng buộc phù hợp, chẳng hạn ở dạng numeric không giới hạn:

```sql
CREATE TABLE checked_amounts (
    amount numeric NOT NULL,
    CONSTRAINT chk_nonnegative_finite
        CHECK (
            amount >= 0
            AND amount <> 'NaN'::numeric
            AND amount <> 'Infinity'::numeric
        )
);
```

Mục đích ví dụ là **cố ý từ chối NaN và vô cực dương**; vô cực âm đã không đạt điều kiện `amount >= 0`. Với kiểu `numeric(p,s)`, bản thân precision cũng giới hạn khả năng nhận vô cực. Trong hệ thống thật, validation cần xác định dữ liệu chỉ bao gồm giá trị hữu hạn theo yêu cầu và phù hợp phiên bản PostgreSQL được dùng.

Không mặc định `NaN` hay `Infinity` có cùng ý nghĩa với SQL `NULL`:

- `NULL` biểu thị không có/không biết giá trị theo logic SQL.
- `NaN` là một giá trị đặc biệt **bên trong kiểu số**.
- `Infinity` là giá trị biểu diễn vô cực của kiểu phù hợp.

## 9. Ép kiểu số và suy luận kiểu của biểu thức

PostgreSQL xác định kiểu cho literal và biểu thức theo ngữ cảnh. Điều này làm thay đổi kết quả toán học nếu bạn không chú ý.

### 9.1. Kiểm tra kiểu bằng `pg_typeof`

```sql
SELECT
    pg_typeof(42) AS literal_integer_type,
    pg_typeof(42::bigint) AS bigint_type,
    pg_typeof(42.0) AS decimal_literal_type,
    pg_typeof(42.0::real) AS real_type,
    pg_typeof(42.0::double precision) AS double_type;
```

Thông thường:

- Một literal số nguyên nhỏ như `42` được hiểu là `integer`.
- Literal có dấu thập phân như `42.0` có kiểu `numeric` trong ngữ cảnh thích hợp.
- Cast tường minh sẽ tạo kiểu được yêu cầu.

Với số nguyên literal quá lớn cho `integer` nhưng còn trong `bigint`, PostgreSQL có thể chọn `bigint`; lớn hơn nữa có thể được suy luận thành `numeric`. Tuy nhiên, đừng dựa vào quy tắc suy luận khi kiểu kết quả là một phần yêu cầu chính xác của hệ thống: **cast rõ ràng**.

### 9.2. Hai dạng ép kiểu

PostgreSQL hỗ trợ:

```sql
SELECT
    CAST('123.45' AS numeric(8,2)) AS standard_cast,
    '123.45'::numeric(8,2) AS postgres_cast;
```

Dạng `CAST(x AS type)` là cách viết SQL phổ biến. Dạng `x::type` gọn và thường gặp trong PostgreSQL.

### 9.3. Cast không phải luôn giữ nguyên giá trị

Ví dụ:

```sql
SELECT
    12.345::numeric(5,2) AS rounded_to_scale,
    2.7::numeric::integer AS converted_to_integer;
```

- `numeric(5,2)` làm tròn về 2 chữ số thập phân.
- Khi cast `numeric` có phần lẻ sang kiểu số nguyên PostgreSQL, giá trị được **làm tròn sang số nguyên** theo quy tắc chuyển kiểu; nó không giống phép chia số nguyên đã cắt phần lẻ.

Đừng nhầm:

```sql
SELECT
    5::integer / 2::integer AS integer_division,
    (5::numeric / 2)::integer AS rounded_numeric_result;
```

Biểu thức đầu cho `2`; biểu thức thứ hai trước tiên có giá trị `2.5` rồi ép sang `integer`, nên kết quả có thể là `3` theo quy tắc làm tròn của cast numeric.

Khi bắt buộc cắt phần lẻ, hãy dùng `trunc` trước khi cast:

```sql
SELECT trunc(5::numeric / 2)::integer AS explicitly_truncated;
```

### 9.4. Cast sau phép toán không khôi phục độ chính xác đã mất

Sai lầm:

```sql
SELECT
    (0.1::double precision + 0.2::double precision)::numeric
        AS cast_after_approximate_math;
```

Ép kết quả từ float sang numeric **không thể khôi phục thông tin chính xác thập phân đã mất** trong quá trình làm tròn và tính toán xấp xỉ ở kiểu float.

Đúng hơn, nếu yêu cầu giá trị thập phân chính xác:

```sql
SELECT
    0.1::numeric + 0.2::numeric AS exact_math;
```

Để duy trì độ chính xác, cần chọn kiểu phù hợp **ngay từ dữ liệu nguồn và xuyên suốt những bước tính**.

## 10. Các phép toán số học và kiểu kết quả

Các phép toán thường dùng:

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `+` | Cộng | `7 + 2` |
| `-` | Trừ | `7 - 2` |
| `*` | Nhân | `7 * 2` |
| `/` | Chia | `7 / 2` |
| `%` | Lấy phần dư theo kiểu hỗ trợ | `7 % 2` |
| `^` | Lũy thừa theo kiểu hàm/toán tử PostgreSQL | `2.0::numeric ^ 3` |
| `abs(x)` | Giá trị tuyệt đối | `abs(-5)` |
| `sqrt(x)` | Căn bậc hai với kiểu phù hợp | `sqrt(9::numeric)` |

Điểm quan trọng: PostgreSQL có **nhiều overload** của cùng toán tử/hàm cho những kiểu khác nhau. Kiểu của toán hạng ảnh hưởng việc PostgreSQL chọn hàm/toán tử và kiểu kết quả.

### 10.1. Truy vấn tự xem kiểu của phép toán

```sql
SELECT
    pg_typeof(1::integer + 2::integer) AS sum_int_type,
    pg_typeof(1::bigint + 2::bigint) AS sum_bigint_type,
    pg_typeof(1::numeric + 2::numeric) AS sum_numeric_type,
    pg_typeof(1::double precision + 2::double precision)
        AS sum_double_type;
```

Cùng là phép cộng nhưng kiểu dữ liệu kết quả khác nhau. Đây là lý do ứng dụng cần kiểm tra driver mapping và nơi nào sẽ xảy ra overflow hoặc rounding.

### 10.2. Kiểu rộng hơn không đồng nghĩa miễn tràn

`bigint` có thể chứa nhiều số nguyên hơn `integer`, nhưng:

```sql
-- Có thể gây lỗi overflow:
SELECT 9223372036854775807::bigint + 1::bigint;
```

Cần chuyển sang numeric **trước** phép cộng:

```sql
SELECT 9223372036854775807::numeric + 1::numeric
    AS exact_sum;
```

Với số dấu phẩy động, vượt phạm vi còn có các kiểu hành vi đặc biệt như overflow/underflow hoặc giá trị vô cực, tùy phép toán và phiên bản. Không dùng floating point thay cho bigint chỉ vì muốn “khỏi tràn” khi thực tế cần giữ **chính xác từng đơn vị nguyên**.

## 11. Tổng hợp: `SUM`, `AVG`, `COUNT` và kiểu trả về

Một lỗi trong báo cáo là giả định kiểu đầu vào luôn bằng kiểu kết quả của hàm tổng hợp.

Với PostgreSQL:

| Biểu thức đầu vào | Kiểu kết quả điển hình |
| --- | --- |
| `sum(smallint)` | `bigint` |
| `sum(integer)` | `bigint` |
| `sum(bigint)` | `numeric` |
| `sum(numeric)` | `numeric` |
| `sum(real)` | `real` |
| `sum(double precision)` | `double precision` |
| `avg(integer)` | `numeric` |
| `avg(bigint)` | `numeric` |
| `avg(numeric)` | `numeric` |
| `avg(real)` | `double precision` |
| `avg(double precision)` | `double precision` |
| `count(*)` | `bigint` |

Các lựa chọn trên giúp tổng nhiều số nguyên không dễ tràn ngay ở kiểu gốc. Nhưng không được mặc nhiên nghĩ mọi kết quả tổng hợp là `integer`.

Ví dụ:

```sql
SELECT
    pg_typeof(sum(v)) AS sum_type,
    pg_typeof(avg(v)) AS avg_type,
    sum(v) AS sum_value,
    avg(v) AS average_value
FROM (VALUES (1::integer), (2::integer), (3::integer)) AS t(v);
```

`sum(v)` có kiểu `bigint`; `avg(v)` là `numeric` với giá trị trung bình `2`.

### 11.1. `AVG` không thực hiện chia nguyên như `sum/count` nếu kiểu thích hợp

```sql
SELECT
    avg(v) AS average_by_avg,
    sum(v) / count(*) AS ratio_by_sum_count,
    sum(v)::numeric / count(*) AS precise_ratio
FROM (VALUES (1::integer), (2::integer)) AS t(v);
```

- `avg(v)` trả giá trị trung bình chính xác dạng numeric, tức `1.5`.
- `sum(v)` là bigint và `count(*)` cũng bigint; phép `sum(v) / count(*)` là **chia nguyên**, có thể cho `1`.
- Ép `sum(v)::numeric` trước khi chia cho kết quả `1.5`.

Vì vậy, khi tính tỷ lệ, trung bình thủ công hoặc phần trăm bằng `SUM/COUNT`, phải chú ý kiểu của cả hai toán hạng.

### 11.2. `SUM`, `AVG` trên tập rỗng và `NULL`

```sql
SELECT
    count(*) AS row_count,
    sum(amount) AS total_amount,
    avg(amount) AS avg_amount
FROM numeric_lab.sales
WHERE false;
```

Với tập rỗng:

- `COUNT(*)` là `0`.
- `SUM(...)` thường trả `NULL`.
- `AVG(...)` trả `NULL`.

Khi muốn hiển thị tổng bằng 0 trong báo cáo, có thể dùng:

```sql
SELECT
    COALESCE(SUM(amount), 0::numeric) AS total_amount
FROM numeric_lab.sales
WHERE false;
```

`COALESCE` phục vụ **quy ước kết quả báo cáo**, không chứng minh có dữ liệu thật. Phân biệt “không có đơn hàng” với “có đơn hàng nhưng tổng tiền bằng 0” khi nghiệp vụ cần.

## 12. Xây dựng ví dụ thực hành: số lượng, đơn giá và cảm biến

Các câu SQL sau dùng một database **thử nghiệm** có quyền tạo schema/bảng. Không chạy lệnh thay đổi bảng trên môi trường sản xuất chỉ để học. Nếu thực hành nhiều lần, nên dùng schema mới hoặc chủ động quản lý dữ liệu đã có.

### 12.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS numeric_lab;

CREATE TABLE numeric_lab.sales (
    sale_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12,2) NOT NULL CHECK (
        unit_price >= 0
        AND unit_price <> 'NaN'::numeric
    ),
    tax_rate numeric(7,6) NOT NULL CHECK (
        tax_rate >= 0
        AND tax_rate <= 1
        AND tax_rate <> 'NaN'::numeric
    ),
    measured_weight real,
    measured_temperature double precision,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Ý nghĩa:

- `sale_id bigint`: ID cho số lượng bản ghi có thể tăng lớn, được cấp qua identity.
- `quantity integer`: số lượng đơn vị bán, không có phần lẻ.
- `unit_price numeric(12,2)`: đơn giá thập phân chính xác ở scale 2.
- `tax_rate numeric(7,6)`: tỷ lệ thuế dưới dạng 0–1, giữ 6 chữ số thập phân.
- `measured_weight real`: dữ liệu cân đo xấp xỉ.
- `measured_temperature double precision`: dữ liệu đo cần nhiều chữ số hơn `real`.

Phần `CHECK` ví dụ chủ động từ chối `NaN` ở các cột tiền/tỷ lệ. Giá trị thực tế vẫn cần validation nghiệp vụ và quy tắc thuế phù hợp.

### 12.2. Nạp dữ liệu mẫu

```sql
INSERT INTO numeric_lab.sales
    (
        product_code,
        quantity,
        unit_price,
        tax_rate,
        measured_weight,
        measured_temperature
    )
VALUES
    ('BOOK-001', 2, 125000.00, 0.080000, 1.25, 25.1254),
    ('PEN-002', 5, 15000.50, 0.080000, 0.08, 24.8132),
    ('NOTE-003', 3, 32000.75, 0.050000, 0.35, 23.9971);
```

Đây là dữ liệu giả định để học kiểu số. Giá trị tax_rate chỉ mang tính minh họa, không phải một khẳng định về thuế suất thực tế.

### 12.3. Tính thành tiền với numeric

```sql
SELECT
    sale_id,
    product_code,
    quantity,
    unit_price,
    quantity::numeric * unit_price AS line_subtotal,
    round(
        quantity::numeric * unit_price * tax_rate,
        2
    ) AS line_tax,
    round(
        quantity::numeric * unit_price * (1 + tax_rate),
        2
    ) AS line_total
FROM numeric_lab.sales
ORDER BY sale_id;
```

Ví dụ với hàng `BOOK-001`:

- `quantity = 2`.
- `unit_price = 125000.00`.
- `tax_rate = 0.080000`.
- `line_subtotal = 2 × 125000.00 = 250000.00`.
- `line_tax = 250000.00 × 0.08 = 20000.00`.
- `line_total = 270000.00`.

Các phép toán được thực hiện trong miền numeric phù hợp, không mang sai số nhị phân kiểu `double precision` vào đơn giá và thuế.

### 12.4. Làm tròn từng dòng hay cuối hóa đơn?

Hai cách tính này có thể cho kết quả khác:

**Cách A: làm tròn tiền thuế theo từng dòng, sau đó cộng.**

```sql
SELECT
    SUM(
        round(quantity::numeric * unit_price * tax_rate, 2)
    ) AS tax_rounded_per_line
FROM numeric_lab.sales;
```

**Cách B: cộng số tiền thuế chưa làm tròn, rồi làm tròn cuối cùng.**

```sql
SELECT
    round(
        SUM(quantity::numeric * unit_price * tax_rate),
        2
    ) AS tax_rounded_after_sum
FROM numeric_lab.sales;
```

Kết quả có thể khác ở chữ số cuối khi nhiều dòng có số lẻ rất nhỏ. PostgreSQL không quyết định thay doanh nghiệp cách nào là đúng: **chính sách tính thuế/làm tròn** phải do quy tắc nghiệp vụ và quy định áp dụng xác định.

Khi chọn một chính sách, cần áp dụng nhất quán trong PostgreSQL, Java và các hệ thống đối soát.

### 12.5. Báo cáo tổng số lượng và doanh thu

```sql
SELECT
    product_code,
    SUM(quantity) AS total_quantity,
    SUM(quantity::numeric * unit_price) AS total_before_tax,
    round(
        SUM(quantity::numeric * unit_price * (1 + tax_rate)),
        2
    ) AS total_with_tax
FROM numeric_lab.sales
GROUP BY product_code
ORDER BY product_code;
```

`SUM(quantity)` nhận số lượng nguyên và trả kiểu `bigint`; tổng tiền dùng `numeric`. Khi ứng dụng Java đọc những cột này, phải chọn kiểu mapping tương ứng (ví dụ `Long` cho tổng số lượng, `BigDecimal` cho tiền), không mặc định mọi cột số trả về `Integer`.

### 12.6. Truy vấn số đo

```sql
SELECT
    product_code,
    measured_weight,
    measured_temperature
FROM numeric_lab.sales
WHERE measured_temperature >= 24.0::double precision
ORDER BY measured_temperature DESC;
```

Phù hợp khi dùng số đo xấp xỉ và so sánh theo ngưỡng. Nếu cần kiểm tra hai lần đo “gần như bằng nhau”, hãy định nghĩa sai số chấp nhận được thay vì đòi dấu `=` khớp biểu diễn nhị phân tuyệt đối.

### 12.7. Kiểm tra kiểu thực sự của các cột

```sql
SELECT
    pg_typeof(quantity) AS quantity_type,
    pg_typeof(unit_price) AS price_type,
    pg_typeof(measured_weight) AS weight_type,
    pg_typeof(measured_temperature) AS temperature_type
FROM numeric_lab.sales
LIMIT 1;
```

Truy vấn giúp quan sát PostgreSQL đang lưu/đọc giá trị theo kiểu nào. Nó không đo được độ chính xác thực tế của cảm biến; độ chính xác cảm biến là đặc tính của nguồn đo, không phải chỉ của kiểu số trong database.

## 13. Giá trị tiền: `numeric` hay số nguyên đơn vị nhỏ nhất?

Có hai chiến lược phổ biến cho tiền:

### 13.1. Lưu bằng `numeric(p,s)`

```sql
CREATE TABLE wallet_balances_numeric (
    wallet_id bigint PRIMARY KEY,
    balance numeric(18,2) NOT NULL
);
```

Ưu điểm:

- Trực tiếp diễn đạt số tiền có hai chữ số thập phân.
- SQL đọc dễ hiểu.
- Phép tính thập phân chính xác.
- Có thể dùng scale khác cho tỷ lệ, tiền tệ hoặc nghiệp vụ cần nhiều số lẻ.

Cần kiểm soát chính sách làm tròn và hạn mức thông qua ràng buộc/logic nghiệp vụ.

### 13.2. Lưu bằng `bigint` theo đơn vị nhỏ nhất

```sql
CREATE TABLE wallet_balances_minor_units (
    wallet_id bigint PRIMARY KEY,
    balance_cents bigint NOT NULL
);
```

Nếu đơn vị nhỏ nhất được quy định và cố định, có thể lưu **số lượng đơn vị nhỏ nhất** dưới dạng số nguyên:

```text
12.34 đơn vị tiền chính
= 1234 đơn vị nhỏ nhất (nếu 1 đơn vị chính = 100 đơn vị nhỏ)
```

Ưu điểm:

- Toán học nguyên chính xác trong giới hạn `bigint`.
- Không phát sinh phần lẻ không hợp lệ ở lớp lưu trữ nếu mọi hệ thống dùng cùng đơn vị.

Nhược điểm:

- Cần quy tắc chuyển đổi và làm tròn ở biên.
- Cần cẩn thận với nhiều đơn vị tiền có số chữ số thập phân khác nhau.
- Rủi ro tràn `bigint` khi cộng/nhân số lượng lớn.
- Các phép tính tỷ lệ/thuế vẫn cần số thập phân hoặc logic làm tròn thích hợp.

**Không có một lựa chọn đúng cho mọi hệ thống tài chính.** Điều quan trọng là định nghĩa rõ **đơn vị**, **scale**, **quy tắc làm tròn**, **phạm vi giá trị**, **kiểu mapping ở ứng dụng** và quy tắc đối soát.

### 13.3. Kiểu `money` trong PostgreSQL

PostgreSQL còn có kiểu `money`, nhưng việc hiển thị và một số hành vi liên quan đến locale/cấu hình khiến nó không phải mặc định thích hợp cho mọi ứng dụng.

Với các bài toán cần kiểm soát precision, scale, chuyển đổi JSON/API và tính toán, `numeric(p,s)` thường là lựa chọn dễ giải thích và nhất quán hơn. Chỉ dùng `money` khi đã hiểu đầy đủ hành vi, yêu cầu locale và tương thích ứng dụng.

## 14. Số liệu đo lường và tính toán khoa học

Với dữ liệu cảm biến, nhiều chữ số đầu vào có thể không phản ánh độ chính xác vật lý thật:

```text
Nhiệt kế báo 24.123456 °C
Sai số thiết bị ±0.1 °C
```

Dù lưu `numeric(20,10)`, bạn **không làm cảm biến chính xác hơn**. Ngược lại, `double precision` có thể đủ để thực hiện những phép tính số học trên giá trị đo.

### 14.1. Khi nào `real` phù hợp?

Nếu hàng tỷ giá trị đo có thể chấp nhận khoảng 6 chữ số có nghĩa, `real` giảm dung lượng so với double. Nhưng phải ước lượng sai số chấp nhận:

- Giá trị gốc có bao nhiêu chữ số đáng tin?
- Phép tính tiếp theo có cộng hàng triệu giá trị?
- Sai số tích lũy có làm thay đổi quyết định/ngưỡng an toàn không?
- Có cần đảm bảo cùng kết quả giữa CPU/kiến trúc/phần mềm khác nhau không?

`real` có thể tiết kiệm lưu trữ nhưng không luôn mang lại kết quả đáng tin cho mọi phép tính.

### 14.2. Khi nào dùng `double precision`?

`double precision` thường phù hợp hơn `real` cho tính toán tổng quát và thuật toán số học cần độ chính xác xấp xỉ cao hơn, chẳng hạn:

- Dữ liệu khoa học.
- Tọa độ/số đo với quy tắc sai số được định nghĩa.
- Tính toán thống kê nhiều bước.
- Dữ liệu học máy dạng xấp xỉ, khi schema và hệ thống xử lý chấp nhận float.

Vẫn cần cảnh giác với **cộng dồn sai số**.

### 14.3. Cộng số dấu phẩy động có thể phụ thuộc thứ tự

Do mỗi phép cộng floating point có thể làm tròn, tổng của một tập số có thể thay đổi đôi chút khi thứ tự cộng thay đổi.

Ví dụ ý tưởng:

```text
Số rất lớn + số rất nhỏ + số rất nhỏ + ...
so với
số rất nhỏ + ... + số rất nhỏ + số rất lớn
```

Những số nhỏ có thể bị mất phần đóng góp trong các bước cộng vào số lớn do giới hạn chữ số có nghĩa. Các kế hoạch truy vấn song song có thể cộng theo thứ tự khác, làm kết quả float có sai lệch nhỏ.

Nếu một báo cáo tài chính đòi tổng tiền chính xác, dùng `SUM(numeric)` thay vì `SUM(double precision)`. Nếu là thống kê đo lường, hãy định nghĩa sai số và kiểm thử độ ổn định của thuật toán.

## 15. Kiểu dữ liệu trong Java, JDBC và ứng dụng

PostgreSQL là nơi lưu trữ, nhưng ứng dụng cũng phải giữ đúng độ chính xác khi truyền dữ liệu.

| PostgreSQL | Java/JDBC thường phù hợp | Ghi chú |
| --- | --- | --- |
| `smallint` | `Short`/`short` | Phải hiểu giới hạn nhỏ |
| `integer` | `Integer`/`int` | Phù hợp số đếm trong phạm vi |
| `bigint` | `Long`/`long` | Lớn hơn integer nhưng vẫn hữu hạn |
| `numeric` / `decimal` | `java.math.BigDecimal` | Giữ biểu diễn thập phân có độ chính xác |
| `real` | `Float`/`float` | Số đo xấp xỉ 32 bit |
| `double precision` | `Double`/`double` | Số đo xấp xỉ 64 bit |

### 15.1. Tránh `double` cho giá tiền Java

Không nên:

```java
double unitPrice = 0.10;
double fee = 0.20;
double total = unitPrice + fee;
```

Đây vẫn là phép cộng floating point nhị phân ở Java, dù sau đó bạn gửi `total` vào cột `numeric` trong PostgreSQL.

Dùng `BigDecimal` với chuỗi decimal khi cần giá trị chính xác:

```java
import java.math.BigDecimal;

BigDecimal unitPrice = new BigDecimal("0.10");
BigDecimal fee = new BigDecimal("0.20");
BigDecimal total = unitPrice.add(fee);

System.out.println(total); // 0.30
```

Không khởi tạo `BigDecimal` từ một `double` đã xấp xỉ mà không hiểu ý nghĩa; ví dụ `new BigDecimal(0.1)` có thể mang giá trị nhị phân xấp xỉ đã được mở rộng thành decimal. Khi dữ liệu đầu vào là số thập phân nghiệp vụ, dùng nguồn chuỗi decimal hoặc cơ chế parse chính xác thích hợp.

### 15.2. Đọc/ghi numeric qua JDBC

Ví dụ Java:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class PriceReader {
    public static BigDecimal findPrice(Connection conn, long saleId)
            throws Exception {
        String sql =
                "SELECT unit_price FROM numeric_lab.sales WHERE sale_id = ?";

        try (PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setLong(1, saleId);

            try (ResultSet rs = stmt.executeQuery()) {
                if (rs.next()) {
                    return rs.getBigDecimal("unit_price");
                }
                return null;
            }
        }
    }
}
```

`getBigDecimal` phù hợp để đọc cột numeric mà không ép sang double. Khi ghi, có thể dùng `PreparedStatement.setBigDecimal` để giữ đúng kiểu dự kiến.

### 15.3. Chú ý scale ở Java và PostgreSQL

Trong Java, hai `BigDecimal` có cùng giá trị toán học nhưng scale khác nhau có thể xử lý khác trong một số phép so sánh theo object; cần thống nhất khi mapping và đối soát.

Ví dụ:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false (khác scale)
```

Ở PostgreSQL, kiểu `numeric` so sánh theo giá trị số. Đừng lấy hành vi `BigDecimal.equals` của Java làm quy tắc SQL để so sánh numeric.

### 15.4. JSON và định dạng API

Khi chuyển số tiền từ PostgreSQL qua API:

- Không tự chuyển giá tiền sang JavaScript Number rồi mặc định giữ mọi chữ số chính xác cho mọi phạm vi.
- Với số nguyên `bigint` rất lớn, một số môi trường JavaScript không biểu diễn chính xác mọi số nguyên 64 bit trong kiểu `Number`.
- Cân nhắc biểu diễn dạng chuỗi decimal hoặc hợp đồng dữ liệu có quy tắc parse rõ ràng cho tiền và ID lớn.

**Tính chính xác cần được duy trì từ database tới mọi lớp**: JDBC, service, JSON serialization, frontend và hệ thống kế toán bên ngoài.

## 16. Index và hiệu năng: kiểu số ảnh hưởng thế nào?

### 16.1. Kích thước và chi phí tính toán

Về nguyên tắc:

- `smallint`/`integer`/`bigint` có kích thước cố định và phép toán số nguyên thường hiệu quả.
- `real`/`double precision` có kích thước cố định và phù hợp bộ xử lý dấu phẩy động.
- `numeric` có dạng lưu trữ biến đổi và các phép toán độ chính xác cao có thể tiêu tốn CPU/bộ nhớ hơn.

Nhưng thời gian một câu SQL còn phụ thuộc cách index, số hàng, độ chọn lọc, I/O, bộ nhớ, JOIN và kế hoạch. Đừng chọn `real` cho tiền chỉ vì kỳ vọng nhanh hơn; đúng dữ liệu luôn là yêu cầu trước.

### 16.2. Index B-tree cho numeric và integer

```sql
CREATE INDEX idx_sales_unit_price
    ON numeric_lab.sales (unit_price);

CREATE INDEX idx_sales_quantity
    ON numeric_lab.sales (quantity);
```

Ví dụ:

```sql
SELECT sale_id, product_code, unit_price
FROM numeric_lab.sales
WHERE unit_price >= 100000.00::numeric
ORDER BY unit_price, sale_id;
```

Index có thể hữu ích khi bảng lớn và điều kiện đủ chọn lọc. Với vài hàng thực hành, PostgreSQL có thể chọn sequential scan vì nó rẻ hơn.

Kiểm tra:

```sql
EXPLAIN
SELECT sale_id, product_code, unit_price
FROM numeric_lab.sales
WHERE unit_price >= 100000.00::numeric;
```

Không tạo nhiều index chỉ để làm một bài thực hành nhanh hơn trên dữ liệu rất nhỏ. Index có chi phí lưu trữ và chi phí bảo trì khi ghi.

### 16.3. Chú ý kiểu tham số khi truy vấn

Nếu cột là `numeric(12,2)`, truyền giá trị qua JDBC bằng `BigDecimal` giúp định nghĩa rõ ý nghĩa thập phân. Nếu cột là `bigint`, truyền đúng long/BigInt ở ứng dụng thay vì floating point có thể làm mất chính xác một số ID rất lớn.

Khi SQL dùng phép cast trên cột hoặc so sánh các kiểu khác nhau, kế hoạch index có thể bị ảnh hưởng. Đừng kết luận chỉ dựa vào một biểu thức cast rằng “index chắc chắn không dùng được”; hãy xác minh bằng `EXPLAIN` và statistics của bảng thực.

### 16.4. Floating point và truy vấn bằng equality

```sql
SELECT *
FROM numeric_lab.sales
WHERE measured_temperature = 24.8::double precision;
```

Truy vấn equality là **so sánh giá trị binary đã lưu**, không phải “nhiệt độ gần 24.8”. Nếu nguồn là cảm biến, bạn thường nên truy vấn một khoảng:

```sql
SELECT *
FROM numeric_lab.sales
WHERE measured_temperature >= 24.7::double precision
  AND measured_temperature <  24.9::double precision;
```

Khoảng này có ý nghĩa “từ 24.7 đến dưới 24.9” theo nghiệp vụ, không phải một epsilon mặc định cho mọi dữ liệu. Nếu cần quy tắc đo riêng, hãy định nghĩa ngưỡng đúng yêu cầu.

## 17. Phạm vi giá trị, đơn vị và ràng buộc

Chọn kiểu đủ rộng nhưng cũng cần bảo vệ logic miền giá trị.

### 17.1. Số lượng không âm

```sql
CREATE TABLE numeric_lab.stock_levels (
    sku text PRIMARY KEY,
    quantity integer NOT NULL
        CHECK (quantity >= 0)
);
```

Kiểu integer cho phép số âm về mặt toán học; `CHECK` mới áp dụng quy tắc “tồn kho không âm”.

### 17.2. Phần trăm phải quy ước từ 0 đến 1 hay từ 0 đến 100

Hai thiết kế:

```sql
discount_rate numeric(7,6)
    CHECK (discount_rate >= 0 AND discount_rate <= 1)
```

hoặc:

```sql
discount_percent numeric(5,2)
    CHECK (discount_percent >= 0 AND discount_percent <= 100)
```

Cả hai có thể hợp lý, nhưng cần đặt tên theo **đơn vị** và ghi rõ trong hợp đồng API. Nếu người dùng nhập 15% mà hệ thống lưu vào `discount_rate`, giá trị phải là `0.15` chứ không phải `15`.

### 17.3. Nhiệt độ không có cùng miền với phần trăm

```sql
temperature_celsius double precision
```

Với nhiệt độ có thể âm, không nên thêm `CHECK (temperature_celsius >= 0)` chỉ vì nhiều cột số khác đều không âm. Ràng buộc phải xuất phát từ thực tế và mục tiêu nghiệp vụ.

### 17.4. Chọn kiểu vừa đủ nhưng dự phòng tăng trưởng

Một bộ đếm truy cập trong `integer` có thể không đủ khi hệ thống lớn. Nếu dự kiến vượt khoảng 2,1 tỷ, hãy dùng `bigint` từ sớm hoặc chuẩn bị migration có kiểm soát.

Ngược lại, thay mọi cột `smallint` bằng `numeric` “để không bao giờ tràn” không nhất thiết hợp lý: chi phí lưu trữ, tính toán và tính rõ ràng về miền giá trị đều cần được xem xét.

## 18. Lỗi thường gặp và cách xử lý

| Lỗi hoặc hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `smallint out of range` | Giá trị vượt ±32 nghìn | Chọn `integer` hoặc miền giá trị đúng |
| `integer out of range` | Phép toán/literal vượt giới hạn 32-bit | Dùng `bigint` hoặc `numeric` trước phép tính |
| `bigint out of range` | Giá trị hoặc phép toán vượt 64-bit | Dùng `numeric` nếu bài toán thật sự cần |
| `numeric field overflow` | Giá trị sau làm tròn vượt precision/scale khai báo | Xem p/s và miền nghiệp vụ |
| Dữ liệu 12.345 vào `numeric(12,2)` thành 12.35 | Cột tự làm tròn đến scale 2 | Xác định chính sách round hay reject |
| `5 / 2` bằng 2 | Phép chia số nguyên | Ép kiểu trước phép chia |
| `SUM(integer)/COUNT(*)` ra số nguyên | Hai toán hạng aggregate có kiểu nguyên | Cast `SUM(...)::numeric` trước khi chia |
| `0.1 + 0.2` float khác 0.3 | Sai số nhị phân | Dùng numeric nếu cần chính xác thập phân |
| `round(double precision, integer)` không khớp overload | Hàm `round(x, s)` có phiên bản numeric phù hợp | Cast sang numeric khi có chủ đích về làm tròn decimal |
| Giá trị float khác nhau do thứ tự tổng | Cộng dồn sai số và thứ tự tính | Chấp nhận/tính sai số hoặc dùng numeric khi cần |
| `NaN` lọt qua so sánh tưởng hợp lý | Ngữ nghĩa NaN đặc biệt của PostgreSQL | Ràng buộc/validation giá trị hữu hạn |
| `numeric` chậm hơn integer trong batch | Tính toán exact precision có chi phí | Chỉ chọn khi đúng nghiệp vụ, đo workload |
| ID quá lớn bị thay đổi ở frontend | Number của JavaScript không giữ mọi int64 | Dùng serialization và kiểu nhận phù hợp |
| Giá tiền bị sai trước khi ghi PostgreSQL | Ứng dụng đã tính bằng double | Dùng BigDecimal/decimal xuyên suốt |
| Query float equality không tìm đúng số đo | Giá trị lưu là xấp xỉ và sai số đo | Dùng khoảng hoặc sai số có ý nghĩa nghiệp vụ |
| Tỷ lệ tính ra `NULL` | Mẫu số bằng 0 và dùng `NULLIF` | Xác định cách biểu diễn dữ liệu thiếu/không xác định |

### 18.1. Gặp lỗi numeric field overflow

Ví dụ:

```sql
-- Cố tình báo lỗi:
SELECT 12345.67::numeric(6,2);
```

`numeric(6,2)` chỉ có 4 chữ số trước dấu thập phân; `12345.67` có 5 chữ số trước dấu, nên không thể lưu.

Đừng lập tức tăng precision vô hạn nếu vấn đề là **dữ liệu nhập sai quy tắc**. Xem bảng giá trị hợp lệ của nghiệp vụ trước khi thay đổi schema.

### 18.2. `round` với hai đối số cho double precision

```sql
-- Câu này không có overload tương ứng như numeric:
-- SELECT round(1.234::double precision, 2);

-- Nếu bạn thực sự muốn round theo decimal ở bước này:
SELECT round(1.234::double precision::numeric, 2);
```

Nhưng cast double sang numeric ở bước cuối không làm dữ liệu xấp xỉ trở thành số gốc thập phân chính xác như trước khi nó đi qua float. Phải xác định mục tiêu của phép làm tròn.

### 18.3. Khác biệt của `round` trên numeric và float tại điểm tie

Với numeric:

```sql
SELECT round(2.5::numeric), round(-2.5::numeric);
```

Kết quả là `3` và `-3`.

Với các kiểu dấu phẩy động, khi giá trị nằm đúng giữa hai số nguyên, PostgreSQL thường dựa theo quy tắc làm tròn của nền tảng; trên nhiều hệ thống, kết quả có xu hướng **ties-to-even**. Đừng dựa vào sự trùng hợp giữa `round(numeric)` và `round(double precision)` khi chính sách làm tròn là phần quan trọng của nghiệp vụ.

## 19. Bài tập thực hành

### Bài 1. Chọn kiểu cho số lượng sản phẩm

Một cửa hàng bán từng chiếc, số lượng mỗi dòng tối đa vài triệu.

**Gợi ý:** `integer` là lựa chọn hợp lý; thêm `CHECK (quantity > 0)` cho dòng bán hoặc `CHECK (stock >= 0)` cho tồn kho. Không dùng numeric chỉ vì giá tiền dùng numeric.

### Bài 2. Chọn kiểu cho giá tiền

Đơn giá cần 2 chữ số thập phân, phần nguyên có thể đến 10 chữ số.

**Gợi ý:** `numeric(12,2)` (10 chữ số phần nguyên và 2 chữ số phần thập phân), kết hợp ràng buộc giá trị hợp lệ và validation theo nghiệp vụ. Nếu có thể vượt giới hạn, phải chọn p phù hợp hơn.

### Bài 3. Phép chia `7 / 2` trả gì?

```sql
SELECT
    7 / 2 AS integer_value,
    7::numeric / 2 AS precise_value;
```

**Đáp án:** kết quả phép chia nguyên là `3`; kết quả numeric có phần lẻ `3.5`.

### Bài 4. Vì sao `round(-2.5::numeric)` không bằng −2?

**Đáp án:** PostgreSQL `round(numeric)` xử lý tie bằng cách làm tròn **ra xa 0**, nên `-2.5` thành `-3`.

### Bài 5. Kiểu nào dùng cho cảm biến ghi khoảng 7 chữ số có nghĩa?

**Gợi ý:** `double precision` thường phù hợp hơn `real` nếu cần giữ khoảng 7 chữ số có nghĩa của giá trị đo. Nhưng phải xem sai số thực tế và yêu cầu tính toán; nếu cần số thập phân chính xác theo một chuẩn đo cụ thể, có thể cần mô hình khác.

### Bài 6. Tính tỷ lệ thành công

Cho 29 lần thành công trên 40 lần thử. Viết SQL trả tỷ lệ chính xác và phần trăm hai số lẻ.

```sql
SELECT
    29::numeric / NULLIF(40, 0) AS success_rate,
    round(100 * 29::numeric / NULLIF(40, 0), 2)
        AS success_percent;
```

**Đáp án:** tỷ lệ `0.725` và phần trăm `72.50`.

### Bài 7. `numeric(5,2)` có giữ `999.995` không?

**Đáp án:** không. Sau làm tròn đến hai chữ số, giá trị thành `1000.00`, vượt giới hạn ba chữ số phần nguyên của `numeric(5,2)`.

### Bài 8. Vì sao cast `numeric` sau phép nhân `integer` không tránh overflow?

```sql
SELECT (50000::integer * 50000::integer)::numeric;
```

**Đáp án:** phép nhân integer xảy ra **trước** cast, nên đã tràn. Cần cast toán hạng trước:

```sql
SELECT 50000::numeric * 50000::integer;
```

### Bài 9. Tổng hai số nguyên và trung bình

```sql
SELECT
    sum(v) AS total,
    avg(v) AS average,
    sum(v) / count(*) AS problematic_manual_average,
    sum(v)::numeric / count(*) AS exact_manual_average
FROM (VALUES (1::integer), (2::integer)) AS t(v);
```

**Đáp án:** `total = 3`; `average = 1.5`; trung bình thủ công sai vì chia nguyên cho `1`; trung bình có cast numeric cho `1.5`.

### Bài 10. Lưu tiền bằng double có an toàn không?

**Đáp án:** không phù hợp khi yêu cầu chính xác thập phân để tính tiền và đối soát, vì các số như `0.1` không được biểu diễn chính xác trong binary float. Nên dùng `numeric(p,s)` hoặc số nguyên đơn vị nhỏ nhất với quy tắc rõ ràng.

### Bài 11. Chọn kiểu tổng lớn

Bạn cần lưu số lượt sự kiện đã xử lý, có thể vượt 2,1 tỷ.

**Đáp án:** cân nhắc `bigint`; khi kết quả phép cộng có khả năng vượt giới hạn 64-bit, dùng `numeric` hoặc mô hình dữ liệu khác phù hợp. Không dựa vào `integer` chỉ vì hiện tại còn ít dữ liệu.

### Bài 12. Tổng hợp doanh thu của từng mã sản phẩm

```sql
SELECT
    product_code,
    SUM(quantity) AS items_sold,
    SUM(quantity::numeric * unit_price) AS revenue
FROM numeric_lab.sales
GROUP BY product_code
ORDER BY product_code;
```

**Đáp án:** `items_sold` là tổng số lượng; `revenue` là tổng tiền trước thuế ở miền numeric. Kiểm tra mapping của ứng dụng để nhận `SUM(quantity)` dưới dạng kiểu có đủ phạm vi.

### Bài 13. Tìm nhiệt độ gần 25°C

Giả sử cảm biến có sai số chấp nhận ±0,2°C. Viết truy vấn tìm khoảng này:

```sql
SELECT sale_id, measured_temperature
FROM numeric_lab.sales
WHERE measured_temperature BETWEEN
    24.8::double precision AND 25.2::double precision;
```

**Giải thích:** ngưỡng ±0,2°C là quy tắc ví dụ; `BETWEEN` bao gồm cả hai biên. Với bài toán cần biên mở hoặc quy tắc đo khác, viết điều kiện cho rõ.

### Bài 14. Vì sao `NaN` không phải `NULL`?

**Đáp án:** `NaN` là một giá trị đặc biệt trong kiểu số, có ngữ nghĩa sắp xếp/so sánh riêng ở PostgreSQL. `NULL` biểu thị thiếu/không biết giá trị theo logic SQL. Cần validation phù hợp để không lưu NaN trong cột tiền, không chỉ dùng `NOT NULL`.

### Bài 15. Chọn kiểu cho tỉ giá ngoại tệ

Nếu nghiệp vụ yêu cầu nhiều chữ số thập phân cố định và đối soát chính xác, có thể dùng `numeric(p,s)` với scale được xác định theo chuẩn nghiệp vụ, ví dụ `numeric(20,10)`. Không lấy `double precision` chỉ vì tỉ giá có phần thập phân dài.

## 20. Checklist thiết kế kiểu số

Trước khi tạo một cột số, hãy trả lời:

| Câu hỏi | Nếu câu trả lời là… | Nên xem xét |
| --- | --- | --- |
| Dữ liệu có bao giờ có phần lẻ không? | Không, đếm đơn vị nguyên | `integer` / `bigint` |
| Có cần chính xác thập phân tuyệt đối không? | Có | `numeric(p,s)` |
| Là số đo xấp xỉ tự nhiên? | Có, sai số đã biết | `real` / `double precision` |
| Phần nguyên lớn nhất bao nhiêu chữ số? | Rất lớn | Kiểm tra precision/range |
| Phần thập phân cần bao nhiêu chữ số? | Theo nghiệp vụ | Định nghĩa scale |
| Nếu giá trị vượt giới hạn thì sao? | Có thể xảy ra | Chọn kiểu rộng hơn, validation |
| Làm tròn theo chính sách nào? | Half-up, ties-even, truncation, theo dòng hoặc tổng | Thiết kế phép tính rõ ràng |
| Phép nhân/cộng trung gian có thể tràn không? | Có | Cast toán hạng **trước** phép toán |
| Dữ liệu có thể là NaN/vô cực không? | Không được phép | Validation/ràng buộc hữu hạn |
| Ứng dụng đọc giá trị bằng kiểu gì? | Java/JSON/client khác | Đồng bộ kiểu để tránh mất precision |
| Có dùng index trên cột số không? | Có | Đo kế hoạch và kiểu tham số |
| Đơn vị dữ liệu đã rõ chưa? | Chưa | Đặt tên cột và hợp đồng API rõ đơn vị |

Đừng chọn kiểu số chỉ vì “có thể chứa mọi giá trị ví dụ”. Một schema tốt phải phản ánh **miền dữ liệu có thể xảy ra**, **độ chính xác cần giữ** và **cách hệ thống sử dụng giá trị**.

## 21. Tổng kết

PostgreSQL có nhiều kiểu số vì những bài toán số học không giống nhau:

1. **`smallint`, `integer`, `bigint`** lưu số nguyên chính xác trong phạm vi xác định. Dùng cho số lượng và ID, kết hợp `CHECK` để giới hạn miền nghiệp vụ.
2. **`numeric`/`decimal`** lưu và tính toán số thập phân chính xác. `numeric(p,s)` xác định precision và scale; giá trị có thể bị làm tròn khi ghi, sau đó bị từ chối nếu vượt phạm vi.
3. **`real`/`double precision`** lưu số dấu phẩy động nhị phân xấp xỉ. `double precision` có nhiều chữ số có nghĩa hơn `real` nhưng **không biến 0.1 thành số binary chính xác tuyệt đối**.
4. **Phép chia số nguyên cắt phần lẻ**, và cast sau phép tính có thể quá muộn. Muốn chia có phần thập phân hoặc tránh overflow, chuyển kiểu toán hạng trước.
5. **`round`, `trunc`, `floor`, `ceil` không tương đương**. Numeric làm tròn điểm tie ra xa 0; chính sách làm tròn tiền phải được định nghĩa rõ.
6. **`SUM` và `AVG` có kiểu kết quả khác kiểu cột đầu vào**; kiểm tra khi tự tính tỷ lệ và mapping dữ liệu sang Java.
7. **`NaN`, vô cực và `NULL` không giống nhau**. Cần xác định có được phép lưu giá trị đặc biệt vào một cột hay không.
8. **Kiểu số phải chính xác xuyên suốt ứng dụng**: PostgreSQL `numeric` đi cùng Java `BigDecimal` và hợp đồng API phù hợp; không chuyển sang double giữa chừng để rồi kỳ vọng lấy lại độ chính xác.
9. **Hiệu năng là đánh đổi thứ cấp sau tính đúng đắn**. Dùng kiểu đơn giản nhất đáp ứng miền giá trị và độ chính xác thật sự, sau đó đo workload và thiết kế index phù hợp.

Một quy tắc dễ nhớ: **đếm thì dùng số nguyên; tiền và số thập phân cần đối soát thì dùng numeric; dữ liệu đo đạc và tính toán chấp nhận sai số thì dùng real hoặc double precision**. Luôn kiểm tra phạm vi, đơn vị và quy tắc làm tròn trước khi đưa kiểu số vào schema PostgreSQL.
