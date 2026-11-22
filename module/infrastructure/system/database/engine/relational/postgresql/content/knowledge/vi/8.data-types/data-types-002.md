# Lựa chọn độ chính xác và biểu diễn giá trị tiền tệ trong PostgreSQL

Một số tiền nhìn đơn giản như **125.000 đồng** hoặc **19,99 USD** nhưng trong ứng dụng, cách lưu và tính toán nó quyết định tính chính xác của hóa đơn, ví điện tử, thanh toán, hoàn tiền và báo cáo. Nếu dùng kiểu số thực dấu phẩy động cho tiền rồi cộng hàng nghìn giao dịch, sai số nhị phân có thể xuất hiện. Nếu lưu số tiền bằng số nguyên nhưng không xác định rõ đơn vị, một bên có thể hiểu `100` là 100 đồng, còn bên kia lại hiểu là 100 xu. Nếu làm tròn ở bước không đúng, hai cách tính thuế trên cùng một hóa đơn có thể chênh nhau một đơn vị tiền.

PostgreSQL cung cấp nhiều kiểu dữ liệu liên quan:

- `NUMERIC` hoặc `DECIMAL`: biểu diễn số thập phân có độ chính xác được kiểm soát, phù hợp với nhiều phép tính tài chính.
- `SMALLINT`, `INTEGER`, `BIGINT`: lưu số nguyên, có thể biểu diễn **đơn vị nhỏ nhất** của đồng tiền như xu hoặc đồng.
- `MONEY`: kiểu tiền tệ chuyên biệt có độ phân giải và cách hiển thị chịu ảnh hưởng của locale.
- `REAL`, `DOUBLE PRECISION`: số dấu phẩy động nhị phân, phù hợp nhiều bài toán khoa học nhưng thường **không phải lựa chọn mặc định cho số tiền cần chính xác từng đơn vị**.

Bài học tập trung vào việc chọn kiểu dữ liệu đúng theo yêu cầu nghiệp vụ, xác định quy tắc làm tròn, lưu kèm đơn vị tiền tệ, kiểm soát giới hạn và phối hợp với ứng dụng. Các ví dụ là SQL PostgreSQL và một ít mã Java để minh họa cách truyền giá trị mà không làm mất độ chính xác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **số thập phân chính xác**, **số nguyên đơn vị nhỏ nhất** và **số thực nhị phân**.
2. Giải thích ý nghĩa của `NUMERIC(p,s)`: precision `p` và scale `s`.
3. Hiểu vì sao `NUMERIC(12,2)` không tự đảm bảo mọi quy tắc nghiệp vụ về tiền và không thay thế kiểm tra đầu vào.
4. Chọn `BIGINT` để lưu cents, đồng hoặc các đơn vị nhỏ nhất khi hợp đồng dữ liệu quy định rõ.
5. Nhận biết giới hạn của kiểu `MONEY`, đặc biệt với locale và tiền tệ có số chữ số thập phân khác nhau.
6. Xác định **thời điểm, phương pháp và cấp độ làm tròn** cho tổng tiền, thuế, phí, chiết khấu và tỷ giá.
7. Thiết kế schema có currency code, ràng buộc miền giá trị, tránh cộng trực tiếp số tiền khác đơn vị.
8. Tránh chuyển giá trị qua `double` hoặc kiểu `Number` thiếu an toàn trong ứng dụng.
9. Thiết kế các bước chuyển đổi và đối soát khi nhập, xuất hoặc thay đổi cách lưu tiền.
10. Giải thích vì sao độ chính xác của kiểu dữ liệu và tính đúng nghiệp vụ là **hai việc liên quan nhưng khác nhau**.

Các ví dụ giả định PostgreSQL hiện đại. Phần tạo và xóa bảng chỉ dành cho một database thử nghiệm.

---

## 2. Trước khi chọn kiểu dữ liệu: “một số tiền” gồm những gì?

Một giá trị tiền thường cần **ít nhất hai thành phần**:

```text
Giá trị số                Đơn vị tiền
   19.99                       USD
  125000                       VND
    1500                       JPY
    1.234                      KWD
```

Chỉ lưu `19.99` mà không có currency code chưa đủ để biết đang nói tới tiền gì. Ngoài ra, hệ thống cần biết:

- **Đơn vị tính:** đô la, đồng, yên, dinar...
- **Độ phân giải của đơn vị:** hệ thống có thể lưu bao nhiêu chữ số thập phân cho từng loại tiền?
- **Quy tắc làm tròn:** làm tròn gần nhất, xuống, lên, half-up hay một quy tắc khác?
- **Miền giá trị:** số âm có hợp lệ không? Tổng tiền tối đa bao nhiêu?
- **Ngữ nghĩa nghiệp vụ:** giá niêm yết, số tiền phải trả, số tiền đã thanh toán hay tỷ giá?
- **Thời điểm hiệu lực:** tỷ giá hoặc chính sách thuế nào đã dùng để tính?
- **Nguồn của giá trị:** client nhập, hệ thống tính, cổng thanh toán xác nhận hay dữ liệu import?

Ví dụ `100` có thể mang nghĩa:

| Cách biểu diễn | Ý nghĩa nếu hợp đồng dữ liệu rõ ràng |
| --- | --- |
| `amount = 100.00`, `currency = 'USD'` | 100 USD |
| `amount_minor = 100`, `currency = 'USD'` | 100 cents = 1 USD |
| `amount_minor = 100`, `currency = 'VND'` | 100 đồng nếu hệ thống dùng đồng làm đơn vị nhỏ nhất |
| `exchange_rate = 100` | Tỷ giá, **không phải số tiền** nếu thiếu cặp tiền tệ và chiều quy đổi |

**Kiểu dữ liệu có thể chính xác về mặt số học nhưng sai về mặt đơn vị.** Ví dụ một phép cộng chính xác giữa 100 USD và 100 JPY vẫn là một phép cộng tiền tệ sai nghĩa nếu không có bước quy đổi.

---

## 3. So sánh các kiểu dữ liệu trong PostgreSQL

| Kiểu dữ liệu | Cách biểu diễn | Điểm mạnh | Hạn chế hoặc điều cần lưu ý |
| --- | --- | --- | --- |
| `SMALLINT` | Số nguyên 2 byte | Gọn cho số lượng nhỏ | Miền rất hẹp cho tiền |
| `INTEGER` | Số nguyên 4 byte | Nhanh, đơn giản | Dễ hết miền nếu lưu giá trị tiền quy mô lớn hoặc cộng dồn |
| `BIGINT` | Số nguyên 8 byte | Chính xác, phù hợp lưu đơn vị tiền nhỏ nhất | Phải quy định rõ scale/currency; phép tính có thể overflow |
| `NUMERIC(p,s)` | Số thập phân độ chính xác được kiểm soát | Phù hợp tiền có phần thập phân và tính toán chính xác decimal | Thường tốn thêm tài nguyên so với integer; chuyển đổi/làm tròn theo scale |
| `NUMERIC` không khai báo `p,s` | Số thập phân có độ chính xác biến đổi | Phù hợp bước tính trung gian hoặc giá trị cần nhiều chữ số | Không tự đặt giới hạn nghiệp vụ; vẫn có hạn mức thực thi |
| `DECIMAL(p,s)` | Tương đương `NUMERIC(p,s)` trong PostgreSQL | Cú pháp quen thuộc theo SQL | Có cùng vấn đề precision/scale |
| `MONEY` | Kiểu tiền 8 byte với độ chính xác phân số cố định theo locale | Đọc/hiển thị dạng tiền trong một số ngữ cảnh | Phụ thuộc `lc_monetary`, không gắn currency code nghiệp vụ, kém linh hoạt đa tiền tệ |
| `REAL` | Floating point nhị phân 4 byte | Phù hợp nhiều bài toán đo lường không đòi hỏi exact decimal | Không biểu diễn chính xác mọi số thập phân |
| `DOUBLE PRECISION` | Floating point nhị phân 8 byte | Dải và độ chính xác lớn hơn `REAL` | Vẫn có sai số biểu diễn/so sánh với số thập phân |

Với hệ thống bán hàng hoặc thanh toán thông thường, hai lựa chọn được cân nhắc nhiều nhất là:

- **`NUMERIC(p,s)`**, ví dụ `NUMERIC(18,2)`, nếu schema biểu diễn trực tiếp giá trị ở đơn vị tiền chính (USD, đồng...).
- **`BIGINT`**, nếu schema biểu diễn số **đơn vị nhỏ nhất** như cents hoặc đồng theo một quy tắc scale được thống nhất.

Không nên chọn `MONEY` chỉ vì tên kiểu “đúng nghĩa tiền”; tên kiểu không tự thay thế đơn vị, tỷ giá, nghiệp vụ và quy tắc rounding.

---

## 4. NUMERIC(p,s): độ chính xác và số chữ số thập phân

Trong PostgreSQL:

```sql
NUMERIC(precision, scale)
```

- **Precision `p`**: số chữ số thập phân có nghĩa tối đa được khai báo.
- **Scale `s`**: số chữ số được giữ ở phía sau dấu thập phân theo khai báo.
- Với trường hợp thông dụng `0 <= s <= p`, có thể lưu tối đa `p - s` chữ số phía trước dấu thập phân.

Ví dụ:

```sql
price NUMERIC(12,2)
```

Có thể hình dung:

```text
       1234567890 . 12
       ----------   --
       10 chữ số    2 chữ số
            tổng precision = 12
```

Một giá trị dương lớn nhất theo cấu hình này là `9999999999.99`. Dấu âm và dấu thập phân không được tính thành chữ số precision.

### 4.1. Đọc một số khai báo quen thuộc

| Khai báo | Số chữ số nguyên tối đa trong dạng thông dụng | Scale | Tình huống minh họa |
| --- | ---: | ---: | --- |
| `NUMERIC(10,2)` | 8 | 2 | Giá bán, hóa đơn quy mô vừa |
| `NUMERIC(12,2)` | 10 | 2 | Tổng tiền lớn hơn |
| `NUMERIC(18,2)` | 16 | 2 | Giá trị tài chính có biên độ rộng |
| `NUMERIC(18,4)` | 14 | 4 | Đơn giá cần phần nhỏ hơn cent trong bước tính |
| `NUMERIC(24,10)` | 14 | 10 | Một số trường hợp tỷ giá/tính toán trung gian |
| `NUMERIC` | Không ràng buộc bởi một `p,s` được khai báo | Linh hoạt | Tính toán, staging hoặc khi cần kiểm soát theo lớp khác |

Đây là **ví dụ lựa chọn**, không phải chuẩn bắt buộc cho từng hệ thống. Cần dự đoán miền số tối đa, âm/dương, số lần cộng dồn, thuế, tỷ giá và khả năng thay đổi trong tương lai.

PostgreSQL hiện đại còn hỗ trợ những cách dùng scale khác ngoài `0..p` ở một số phiên bản, ví dụ scale âm để làm tròn tới hàng chục/hàng trăm. Đối với **cột tiền cần giữ một lượng cố định chữ số thập phân**, dạng thông dụng với scale không âm là dễ hiểu nhất; không áp dụng scale âm mà chưa phân tích yêu cầu làm tròn.

### 4.2. PostgreSQL làm gì khi nhập nhiều chữ số thập phân hơn scale?

Đây là điểm quan trọng: **`NUMERIC(p,s)` có thể làm tròn giá trị đầu vào về scale được khai báo**, chứ không luôn từ chối số có quá nhiều chữ số sau dấu thập phân.

Ví dụ:

```sql
SELECT
    12.345::NUMERIC(8,2) AS rounded_positive,
    (-12.345)::NUMERIC(8,2) AS rounded_negative,
    12.344::NUMERIC(8,2) AS rounded_down;
```

Với quy tắc làm tròn mặc định của `numeric` trong PostgreSQL, kết quả thường tương ứng:

| Đầu vào | Sau ép `NUMERIC(8,2)` |
| --- | ---: |
| 12.345 | 12.35 |
| -12.345 | -12.35 |
| 12.344 | 12.34 |

Khi đúng giữa hai giá trị có thể làm tròn, kiểu `numeric` của PostgreSQL thường làm tròn **ra xa 0** (*ties away from zero*). Quy tắc đó cần được đối chiếu với yêu cầu nghiệp vụ hoặc quy định tính thuế/tiền, không chỉ mặc định dùng vì database đã cung cấp.

### 4.3. Khi phần nguyên vượt precision

Ví dụ:

```sql
-- NUMERIC(5,2) chỉ có chỗ cho tối đa 3 chữ số phần nguyên.
SELECT 999.99::NUMERIC(5,2);
```

Giá trị này hợp lệ.

Nhưng:

```sql
-- Ví dụ dự kiến lỗi: numeric field overflow.
SELECT 1000.00::NUMERIC(5,2);
```

không hợp lệ, vì số chữ số phía trước dấu thập phân vượt giới hạn.

Lưu ý: làm tròn cũng có thể đẩy số qua giới hạn. Một giá trị gần `999.99` nếu được làm tròn lên thành `1000.00` sẽ không còn vừa trong `NUMERIC(5,2)`.

### 4.4. Exact decimal không có nghĩa mọi phép chia đều có kết quả hữu hạn

`NUMERIC` có thể biểu diễn chính xác các số thập phân hữu hạn trong khả năng của kiểu. Nhưng kết quả `1/3` không có biểu diễn thập phân hữu hạn:

```sql
SELECT
    1::NUMERIC / 3::NUMERIC AS one_third,
    ROUND(1::NUMERIC / 3::NUMERIC, 2) AS rounded_to_cents;
```

PostgreSQL phải lựa chọn độ chính xác hữu hạn khi thực hiện phép chia. Bởi vậy, **quy tắc lấy bao nhiêu chữ số và lúc nào làm tròn vẫn cần được xác định** ngay cả khi toàn bộ các toán hạng là `NUMERIC`.

### 4.5. Kiểu NUMERIC và các giá trị đặc biệt

Ở những phiên bản PostgreSQL hiện đại, `NUMERIC` có thể hỗ trợ giá trị đặc biệt như `NaN` và các dạng vô cực trong điều kiện tương ứng. Những giá trị này hiếm khi có ý nghĩa như một số tiền được phép thanh toán.

Nếu ứng dụng nhận trực tiếp dữ liệu từ bên ngoài, hãy kiểm tra giá trị **hữu hạn**, đúng miền nghiệp vụ và đúng định dạng. Đừng coi mọi giá trị parser nhận được là số tiền hợp lệ chỉ vì cột có kiểu `numeric`.

---

## 5. Vì sao không nên dùng FLOAT/DOUBLE PRECISION làm tiền mặc định?

`REAL` và `DOUBLE PRECISION` được lưu theo **số thực nhị phân dấu phẩy động**. Nhiều phân số thập phân quen thuộc, như `0.1`, không có biểu diễn nhị phân hữu hạn.

Ví dụ:

```sql
SELECT
    0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION
        AS binary_float_sum,
    0.3::DOUBLE PRECISION AS expected_float,
    (0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION)
        = 0.3::DOUBLE PRECISION AS exactly_equal;
```

Trong các phép tính floating point thông dụng, hai giá trị gần nhau có thể **không bằng nhau tuyệt đối** do sai số biểu diễn/làm tròn nhị phân. Giá trị hiển thị còn có thể bị rút gọn theo định dạng output, nên không được chỉ nhìn chuỗi in ra để kết luận phép tính hoàn toàn chính xác.

Trong khi đó:

```sql
SELECT
    (0.1::NUMERIC + 0.2::NUMERIC) = 0.3::NUMERIC
        AS exact_decimal_equal;
```

Với các hằng số decimal hữu hạn được biểu diễn theo `NUMERIC`, phép cộng trong ví dụ bằng nhau theo số học thập phân.

### 5.1. Sai số nhỏ có nguy hiểm không?

Một sai số nhị phân cực nhỏ có thể không đáng kể khi tính toán vật lý hoặc đồ họa. Nhưng với tiền, vấn đề gồm:

- So sánh `=`, `<`, `>` trong những logic “đủ tiền chưa?”.
- Tính thuế/phí lặp đi lặp lại.
- Cộng dồn nhiều dòng hóa đơn.
- Đối soát với con số chính xác từ ngân hàng/cổng thanh toán.
- Chuyển qua JSON, JavaScript, driver và các hệ thống khác.
- Làm tròn khác nhau giữa client và database.

Ví dụ hệ thống thu tiền tới từng cent có thể yêu cầu kết quả quyết toán **chính xác tới cent**, không chỉ “gần đúng trong một epsilon”.

### 5.2. Khi nào floating point vẫn hợp lý?

Floating point phù hợp cho rất nhiều bài toán:

- Đo lường khoa học, thống kê, đồ họa.
- Giá trị xác suất và mô hình dự báo khi sai số được chấp nhận.
- Phép toán tối ưu hóa mà kết quả tiền cuối cùng vẫn được chuyển sang representation/rounding được thiết kế rõ.

Nếu một thuật toán dự báo dùng `double precision` nhưng cuối cùng tạo ra một **giao dịch tiền**, phần chuyển đổi sang giá trị giao dịch vẫn phải có quy tắc làm tròn, kiểm tra phạm vi và đơn vị tiền tệ.

**Không dùng `CAST(double AS numeric)` như một cách khôi phục độ chính xác của số tiền gốc đã bị mất từ trước.** Khi đã tạo giá trị `double` không biểu diễn chính xác số đầu vào, việc cast chỉ chuyển biểu diễn của giá trị hiện tại theo quy tắc PostgreSQL, không biết được ý định ban đầu của người dùng.

---

## 6. Phương án A: lưu số tiền bằng NUMERIC

Một ứng dụng chỉ xử lý USD với hai chữ số thập phân có thể dùng:

```sql
CREATE TABLE example_usd_prices (
    price_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    price_usd NUMERIC(18,2) NOT NULL
        CHECK (price_usd >= 0)
);
```

Ví dụ thao tác:

```sql
INSERT INTO example_usd_prices (price_usd)
VALUES (19.99), (125.00)
RETURNING price_id, price_usd;

SELECT SUM(price_usd) AS total_usd
FROM example_usd_prices;
```

Ưu điểm:

1. Dễ đọc khi truy vấn SQL: `19.99` có nghĩa là 19 đô la và 99 cents nếu cột đã được định nghĩa đúng đơn vị.
2. Không cần tự chia/nhân 100 cho từng phép cộng thông thường.
3. Chính xác với các số thập phân hữu hạn như `0.01`.
4. Có thể dùng `SUM`, `ROUND`, `NUMERIC` arithmetic và constraints trực tiếp.
5. Ánh xạ thuận tiện sang `BigDecimal` của Java.

Nhược điểm hoặc điều cần thiết kế:

- Scale `2` áp dụng cho cột, không tự linh hoạt theo đồng tiền nếu nhiều currency chung một bảng.
- Nếu nhận `19.999`, cột có thể làm tròn khi nhập, thay vì từ chối theo ý nghĩa “người dùng gửi sai số lẻ”.
- Cột vẫn cần quy tắc giới hạn, currency và điều kiện nghiệp vụ.
- Các phép toán numeric có thể tốn tài nguyên hơn integer, tùy workload.
- Tổng cộng/tỷ giá có thể cần độ chính xác trung gian lớn hơn scale lưu cuối.

### 6.1. Đừng nhầm số lẻ đơn giá với số lẻ số tiền cuối cùng

Một đơn giá cho hàng hóa đo theo khối lượng hoặc dung lượng có thể cần độ chính xác lớn hơn cent:

```text
Đơn giá:    0.0150 USD mỗi đơn vị
Số lượng:  10.000 đơn vị
Thành tiền: 0.1500 USD
Số tiền thanh toán: 0.15 USD (theo quy tắc làm tròn)
```

Nếu đơn giá bị lưu ngay vào `NUMERIC(18,2)`, nó có thể được làm tròn thành `0.02` trước khi nhân với số lượng, làm sai giá trị gốc.

Một thiết kế thường gặp là:

- `unit_price NUMERIC(18,4)` hoặc scale lớn hơn theo miền nghiệp vụ.
- `quantity NUMERIC(12,3)` hoặc theo đơn vị đo.
- Tính thành tiền với đủ precision trung gian.
- Làm tròn số tiền phải trả về đúng đơn vị thanh toán ở **mốc nghiệp vụ đã chọn**.

Không phải trường “giá” nào cũng nên mặc định scale 2.

### 6.2. Không lưu mọi tỷ giá vào NUMERIC(18,2)

Tỷ giá có thể cần nhiều chữ số sau dấu thập phân. Nếu chỉ giữ hai chữ số rồi nhân với giá trị lớn, sai số có thể rất đáng kể.

Ví dụ:

```sql
SELECT
    10000::NUMERIC * 1.234567::NUMERIC AS precise_conversion,
    10000::NUMERIC * 1.23::NUMERIC AS prematurely_rounded;
```

Hai kết quả khác nhau. Chính sách tỷ giá cần định nghĩa **độ chính xác lưu tỷ giá**, **cặp tiền**, **chiều quy đổi**, **thời điểm hiệu lực** và **quy tắc làm tròn kết quả**, không chỉ đổi type.

---

## 7. Phương án B: lưu bằng BIGINT theo đơn vị tiền nhỏ nhất

Một cách khác là biểu diễn tiền bằng **số nguyên nhỏ nhất được phép lưu**.

Với USD, nếu hệ thống lấy cent làm đơn vị nhỏ nhất:

```text
19.99 USD    -> amount_minor = 1999
0.01 USD     -> amount_minor = 1
100.00 USD   -> amount_minor = 10000
```

Với VND, một hệ thống dùng đồng làm đơn vị tối thiểu có thể quy ước:

```text
125000 VND   -> amount_minor = 125000
```

Đây là **hợp đồng dữ liệu** giữa các hệ thống. Không thể đọc một giá trị `amount_minor = 100` mà tự biết nó tương đương bao nhiêu đơn vị tiền chính nếu thiếu currency và scale.

### 7.1. Thiết kế bảng số nguyên

```sql
CREATE TABLE example_usd_balances (
    account_id BIGINT PRIMARY KEY,
    balance_cents BIGINT NOT NULL CHECK (balance_cents >= 0)
);

INSERT INTO example_usd_balances (account_id, balance_cents)
VALUES (1, 10005), (2, 2500);

SELECT
    account_id,
    balance_cents,
    balance_cents::NUMERIC / 100 AS balance_usd
FROM example_usd_balances
ORDER BY account_id;
```

Dữ liệu đọc ra tương ứng:

| Tài khoản | `balance_cents` | USD |
| --- | ---: | ---: |
| 1 | 10005 | 100.05 |
| 2 | 2500 | 25.00 |

`BIGINT` dùng 8 byte và có phép toán số nguyên chính xác trong miền hợp lệ.

Ưu điểm:

- Không có phần thập phân nhị phân trong giá trị lưu.
- Phù hợp hệ thống thanh toán trao đổi giá trị theo đơn vị nhỏ nhất.
- Dễ so sánh `balance_cents >= amount_cents` và cộng trừ một số nguyên.
- Thường hiệu quả về lưu trữ/tính toán so với numeric khi yêu cầu phù hợp.

Hạn chế:

- Mọi client phải thống nhất scale.
- Khi thêm một đồng tiền có 0 hoặc 3 chữ số lẻ, không thể mặc định nhân mọi số tiền với 100.
- Phép nhân, cộng dồn và chuyển đổi có thể **tràn BIGINT**.
- Tỷ giá, phần trăm và chia không tự nhiên là số nguyên; cần tính trung gian chính xác rồi làm tròn.
- Nếu yêu cầu đơn giá dưới cent, lưu trực tiếp từng đơn giá vào cents sẽ mất độ chính xác quá sớm.

### 7.2. Chuyển đổi từ major unit sang minor unit

Nếu USD dùng 2 chữ số lẻ:

```sql
SELECT
    19.99::NUMERIC AS usd,
    (19.99::NUMERIC * 100)::BIGINT AS cents;
```

Với đầu vào chắc chắn có tối đa hai chữ số lẻ, phép nhân ra số nguyên và chuyển sang `BIGINT`.

Nhưng với:

```sql
SELECT 19.999::NUMERIC * 100 AS not_integral_cents;
```

kết quả không còn là số cent nguyên. Không nên cast trực tiếp mà không xác định **chính sách làm tròn hoặc từ chối**.

Ví dụ làm tròn rõ ràng:

```sql
SELECT ROUND(19.999::NUMERIC * 100, 0)::BIGINT
    AS rounded_cents;
```

Kết quả là 2000 cents nếu chính sách cho phép làm tròn tới cent. Nếu API yêu cầu người dùng chỉ gửi tối đa hai chữ số lẻ, dữ liệu `19.999` nên bị **từ chối trước khi chuyển** chứ không tự ý đổi thành 20.00.

### 7.3. Tránh overflow

Miền `BIGINT` là:

```text
-9223372036854775808 ... 9223372036854775807
```

Vì vậy, một số tiền lưu theo cents tiêu thụ nhiều đơn vị nguyên hơn cùng con số tính theo USD. Một bảng có thể lưu mỗi hàng hợp lệ nhưng phép `SUM` hoặc các phép nhân tính phí vẫn phải được xem xét miền số.

PostgreSQL có các quy tắc type riêng cho tổng hợp như `SUM(BIGINT)` có thể trả kiểu `NUMERIC`, nhưng một **biểu thức số học `BIGINT + BIGINT`** vẫn có nguy cơ tràn.

Cách tính trung gian an toàn hơn khi cần số lớn:

```sql
SELECT
    (9000000000000000000::BIGINT)::NUMERIC
      + (9000000000000000000::BIGINT)::NUMERIC
        AS total_without_bigint_add_overflow;
```

Nếu cuối cùng chuyển kết quả lại sang `BIGINT`, cần kiểm tra nó còn trong miền `BIGINT`. Cast hoặc constraint không làm miền kiểu lớn lên.

---

## 8. Kiểu MONEY: tiện nhìn nhưng không phải lựa chọn mặc định

PostgreSQL có kiểu riêng:

```sql
CREATE TABLE example_money_type (
    id INTEGER PRIMARY KEY,
    amount MONEY
);
```

Ví dụ:

```sql
INSERT INTO example_money_type (id, amount)
VALUES (1, 10.25::MONEY);

SELECT amount
FROM example_money_type;
```

Kiểu `MONEY` thường có biểu diễn lưu trữ 8 byte với độ chính xác phần lẻ cố định gắn với thiết lập `lc_monetary`. Cách **hiển thị và phân tích chuỗi tiền** phụ thuộc locale đang cấu hình, ví dụ ký hiệu tiền và dấu phân cách.

### 8.1. Tại sao lc_monetary quan trọng?

```sql
SHOW lc_monetary;
```

Nếu một hệ thống tạo dữ liệu với thiết lập locale này rồi đưa output money dạng text sang một hệ khác có quy tắc khác, cách parse có thể không giống nhau.

Những vấn đề phổ biến:

- Không linh hoạt khi một bảng chứa tiền tệ cần 0, 2, 3 chữ số lẻ theo từng hàng.
- Kiểu `money` không tự lưu mã ISO của đồng tiền với giá trị.
- Định dạng output phụ thuộc cấu hình, không nên coi nó là một format API ổn định.
- Việc chuyển đổi/nhân chia với một số kiểu khác cần hiểu quy tắc type và rounding; không dùng chuỗi tiền được format để tính toán.
- Khi dump/restore qua môi trường khác locale, có thể xuất hiện vấn đề tương thích dữ liệu và cách thể hiện.

Với ứng dụng cần JSON API rõ ràng, nhiều currency, quy tắc kiểm toán hay tính toán trung gian có scale khác nhau, `NUMERIC` hoặc `BIGINT` kèm mã currency thường dễ kiểm soát hơn.

**Không nên hiểu `MONEY` là một công cụ hỗ trợ tỷ giá hoặc tự động nhận biết USD, VND, JPY.** Nó chủ yếu là một kiểu giá trị số tiền có định dạng hiển thị đặc thù.

---

## 9. Tiền tệ khác nhau có số chữ số lẻ khác nhau

Một sai lầm lớn khi dùng một schema đa tiền tệ là giả định **mọi đồng tiền đều có 2 chữ số thập phân**.

Một số ví dụ thường gặp trong hệ thống dựa trên mã tiền tệ:

| Currency | Ví dụ đơn vị tiền nhỏ nhất thông dụng | Số chữ số thập phân minh họa |
| --- | --- | ---: |
| USD | cent | 2 |
| VND | đồng | 0 |
| JPY | yên | 0 |
| KWD | fils | 3 |

Bảng chỉ minh họa các đơn vị tiền thường được dùng; **cổng thanh toán, chuẩn định dạng dữ liệu hoặc hợp đồng hệ thống có thể dùng quy tắc scale riêng**. Vì vậy schema thực tế cần xác nhận quy ước của tất cả các bên tích hợp, không chỉ dựa vào tên currency.

### 9.1. Một định nghĩa đa tiền tệ

Có thể lưu metadata của mỗi currency:

```sql
CREATE TABLE currency_definitions (
    code VARCHAR(3) PRIMARY KEY
        CHECK (code ~ '^[A-Z]{3}$'),
    minor_digits SMALLINT NOT NULL
        CHECK (minor_digits BETWEEN 0 AND 3)
);

INSERT INTO currency_definitions (code, minor_digits)
VALUES
    ('USD', 2),
    ('VND', 0),
    ('JPY', 0),
    ('KWD', 3);
```

**Lưu ý:** Regex `^[A-Z]{3}$` chỉ kiểm tra hình thức mã ba chữ in hoa; nó **không chứng minh mã thuộc danh mục ISO đang có hiệu lực**. Bảng reference/nguồn chuẩn cần được quản trị như dữ liệu cấu hình, thay đổi phải có kiểm soát và lưu lịch sử khi nghiệp vụ yêu cầu.

### 9.2. Ví dụ ví tiền lưu BIGINT minor units

```sql
CREATE TABLE wallet_balances (
    wallet_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    currency_code VARCHAR(3) NOT NULL
        REFERENCES currency_definitions(code),
    balance_minor BIGINT NOT NULL CHECK (balance_minor >= 0)
);

INSERT INTO wallet_balances (currency_code, balance_minor)
VALUES
    ('USD', 1999),      -- 19.99 USD
    ('VND', 125000),    -- 125000 VND
    ('JPY', 1500),      -- 1500 JPY
    ('KWD', 1234);      -- 1.234 KWD
```

Khi cần hiển thị giá trị ở đơn vị tiền chính, dùng metadata scale:

```sql
SELECT
    w.wallet_id,
    w.currency_code,
    w.balance_minor,
    c.minor_digits,
    w.balance_minor::NUMERIC
       / POWER(10::NUMERIC, c.minor_digits)
        AS amount_major
FROM wallet_balances AS w
JOIN currency_definitions AS c
  ON c.code = w.currency_code
ORDER BY w.wallet_id;
```

Kết quả về mặt số học:

| Currency | `balance_minor` | `minor_digits` | Giá trị chính |
| --- | ---: | ---: | ---: |
| USD | 1999 | 2 | 19.99 |
| VND | 125000 | 0 | 125000 |
| JPY | 1500 | 0 | 1500 |
| KWD | 1234 | 3 | 1.234 |

Trong hệ thống thực, bảng `currency_definitions` phải được coi là metadata quan trọng. Nếu đổi `minor_digits` từ 2 thành 0 mà không di chuyển dữ liệu `balance_minor` tương ứng, **ý nghĩa số tiền đang lưu thay đổi 100 lần**. Không sửa scale đã áp dụng cho số dư như một thay đổi giao diện đơn thuần.

### 9.3. Không cộng trực tiếp hai đồng tiền

Sai:

```sql
SELECT SUM(balance_minor) AS misleading_total
FROM wallet_balances;
```

Câu SQL có thể chạy và trả về một số nguyên, nhưng tổng đó **vô nghĩa về tiền tệ**, vì nó cộng cents, đồng, yên và fils.

Tối thiểu phải nhóm theo currency:

```sql
SELECT
    currency_code,
    SUM(balance_minor) AS total_minor
FROM wallet_balances
GROUP BY currency_code
ORDER BY currency_code;
```

Nếu cần tổng quy đổi về một đồng tiền báo cáo, phải có **tỷ giá được xác định theo cặp, thời điểm và chiều quy đổi**, rồi áp dụng chính sách làm tròn hợp lệ.

---

## 10. Quy tắc ROUND: làm tròn ở đâu là quyết định nghiệp vụ

PostgreSQL cung cấp hàm `ROUND`:

```sql
SELECT
    ROUND(12.345::NUMERIC, 2) AS rounded_two_decimals,
    ROUND((-12.345)::NUMERIC, 2) AS rounded_negative;
```

Với `NUMERIC`, kết quả trong ví dụ là `12.35` và `-12.35`.

Nhưng câu hỏi quan trọng không chỉ là **làm tròn như thế nào**, mà còn là **làm tròn ở bước nào**:

- Sau từng dòng hàng hóa?
- Sau khi cộng tất cả dòng?
- Sau khi tính phí riêng?
- Sau khi áp dụng chiết khấu?
- Sau khi quy đổi tỷ giá?
- Khi phát sinh giao dịch thanh toán cuối cùng?

Hai quy trình đều dùng decimal exact nhưng có thể cho kết quả khác.

### 10.1. Làm tròn từng dòng hay làm tròn tổng?

Giả sử có hai dòng hàng, mỗi dòng có giá tính thuế `0.05 USD`, thuế suất minh họa `10%`.

Nếu làm tròn thuế **trên từng dòng**:

```sql
SELECT
    ROUND(0.05::NUMERIC * 0.10::NUMERIC, 2)
    + ROUND(0.05::NUMERIC * 0.10::NUMERIC, 2)
      AS tax_rounded_per_line;
```

Mỗi dòng tạo thuế `0.005`, làm tròn thành `0.01`, tổng `0.02`.

Nếu cộng cơ sở tính thuế trước rồi mới làm tròn:

```sql
SELECT
    ROUND(
        (0.05::NUMERIC + 0.05::NUMERIC)
         * 0.10::NUMERIC,
        2
    ) AS tax_rounded_on_total;
```

Kết quả là `0.01`.

| Quy trình | Thuế cuối cùng |
| --- | ---: |
| Làm tròn từng dòng rồi cộng | 0.02 USD |
| Cộng dòng rồi tính thuế, làm tròn một lần | 0.01 USD |

Sự khác nhau **không phải lỗi của `NUMERIC`**. Đó là khác biệt trong **quy tắc nghiệp vụ**. Với hệ thống thanh toán/thuế thật, phải tuân theo hợp đồng hoặc quy định áp dụng; không tự chọn một cách chỉ vì nó tạo số thấp hơn.

### 10.2. Half-up, half-even, floor và ceiling

Một số chính sách rounding quen thuộc:

| Chính sách | Ý nghĩa khái quát |
| --- | --- |
| Làm tròn gần nhất, tie ra xa 0 | Ví dụ cách `ROUND(numeric, scale)` thường xử lý giá trị đúng giữa |
| Half-even | Khi đúng giữa hai giá trị, chọn phía có chữ số cuối chẵn theo quy tắc |
| Floor | Làm tròn xuống theo hướng âm vô cùng |
| Ceiling | Làm tròn lên theo hướng dương vô cùng |
| Truncate | Cắt phần nhỏ hơn đơn vị theo quy tắc |

Ví dụ:

```sql
SELECT
    ROUND(2.5::NUMERIC) AS rounded_2_5,
    ROUND((-2.5)::NUMERIC) AS rounded_negative_2_5,
    FLOOR(2.5::NUMERIC) AS floored,
    CEIL(2.5::NUMERIC) AS ceiled,
    TRUNC(2.99::NUMERIC, 0) AS truncated;
```

**`FLOOR` không giống `TRUNC` với số âm.** Ví dụ `FLOOR(-1.2)` là `-2`, còn `TRUNC(-1.2)` là `-1`. Những chi tiết này rất quan trọng nếu tính phí, hoàn tiền và giá trị âm.

Nếu nghiệp vụ yêu cầu **half-even**, không được giả định `ROUND(numeric, scale)` của PostgreSQL mặc định thực hiện đúng chính sách đó. Hãy xây dựng hoặc dùng logic rounding đã được kiểm chứng riêng, và bảo đảm Java/backend/database đồng nhất.

### 10.3. Làm tròn trước khi SUM có thể làm sai tổng

Giả sử nhập hàng có đơn giá 0.015 USD và số lượng 100. Nếu bạn làm tròn đơn giá trước:

```sql
SELECT
    ROUND(0.015::NUMERIC, 2) * 100 AS premature_rounding,
    ROUND(0.015::NUMERIC * 100, 2) AS round_final_amount;
```

Theo rounding thập phân, hai kết quả sẽ khác nhau: `2.00` so với `1.50`. Phép toán chính xác vẫn không thể cứu được một quyết định làm tròn quá sớm.

Quy tắc thực hành: **giữ đủ precision trong các giá trị trung gian, chỉ làm tròn ở mốc nghiệp vụ đã định**.

---

## 11. Schema minh họa: đơn giá chính xác hơn số tiền phải thu

Một mô hình đơn hàng thường có:

- Số lượng có thể không nguyên: `quantity NUMERIC(12,3)`.
- Đơn giá có 4 chữ số lẻ: `unit_price_usd NUMERIC(18,4)`.
- Thành tiền USD được tính về 2 chữ số lẻ: `line_total_usd NUMERIC(18,2)`.

Tạo ví dụ trong schema thực hành:

> **Chỉ chạy trên database lab.** Các câu `DROP TABLE` ở phần này xóa dữ liệu cũ của đúng đối tượng minh họa. Không đặt tên trùng bảng production.

```sql
CREATE SCHEMA IF NOT EXISTS money_lab;

DROP TABLE IF EXISTS money_lab.invoice_lines;

CREATE TABLE money_lab.invoice_lines (
    line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL,
    quantity NUMERIC(12,3) NOT NULL
        CHECK (quantity > 0),
    unit_price_usd NUMERIC(18,4) NOT NULL
        CHECK (unit_price_usd >= 0),
    line_total_usd NUMERIC(18,2)
        GENERATED ALWAYS AS (
            ROUND(quantity * unit_price_usd, 2)
        ) STORED
);
```

Ở bảng này:

- `quantity` và `unit_price_usd` giữ precision theo yêu cầu hàng hóa.
- `line_total_usd` là **generated stored column**, tính và lưu kết quả theo expression.
- `ROUND(...,2)` thể hiện quy tắc tính thành tiền ở cấp dòng mà ví dụ lựa chọn.
- `NUMERIC(18,2)` của cột kết quả cũng giới hạn miền số cuối.
- Tên cột có hậu tố `usd` nói rõ đây là bảng một currency, **không trộn các đồng tiền khác vào cùng cột**.

Thêm ba dòng:

```sql
INSERT INTO money_lab.invoice_lines (
    sku, quantity, unit_price_usd
)
VALUES
    ('ITEM-A', 1.000, 19.9900),
    ('ITEM-B', 2.500,  4.2000),
    ('ITEM-C', 100.000, 0.0150)
RETURNING
    sku, quantity, unit_price_usd, line_total_usd;
```

Kết quả về mặt số học:

| SKU | Quantity | Đơn giá USD | Thành tiền USD |
| --- | ---: | ---: | ---: |
| ITEM-A | 1.000 | 19.9900 | 19.99 |
| ITEM-B | 2.500 | 4.2000 | 10.50 |
| ITEM-C | 100.000 | 0.0150 | 1.50 |
| **Tổng** | | | **31.99** |

Tổng:

```sql
SELECT
    SUM(line_total_usd) AS invoice_total_usd
FROM money_lab.invoice_lines;
```

Kết quả `31.99`.

### 11.1. Vì sao không nhập line_total từ API?

Nếu client gửi đồng thời `quantity`, `unit_price` và `line_total`, ba giá trị có thể không khớp. Việc để database tính generated column giúp có **một công thức rõ ràng** trong ví dụ.

Tuy nhiên, generated column không tự xử lý mọi chính sách:

- Đơn giá có thể thay đổi theo thời điểm; hóa đơn phải lưu snapshot giá đã chốt.
- Chiết khấu và thuế có thể được tính theo quy trình riêng.
- Một số thị trường yêu cầu làm tròn khác.
- Số âm có thể hợp lệ trong phiếu điều chỉnh/hoàn trả nhưng phải có mô hình rõ.
- Nếu tiền tệ thay đổi theo từng hàng, biểu thức cố định scale 2 không còn đúng cho tất cả.

Do đó, bảng minh họa phù hợp cho bài học **một currency USD, một quy tắc làm tròn cấp dòng**, không phải mẫu hóa đơn đa quốc gia đầy đủ.

### 11.2. Tổng hợp số tiền rỗng

Trong PostgreSQL:

```sql
SELECT SUM(line_total_usd) AS total
FROM money_lab.invoice_lines
WHERE sku = 'NOT-EXIST';
```

Với tập không có hàng, `SUM` trả **NULL**, không phải 0. Nếu kết quả kinh doanh cần “không có dòng thì tổng bằng 0”, có thể chủ động:

```sql
SELECT
    COALESCE(SUM(line_total_usd), 0::NUMERIC) AS total_usd
FROM money_lab.invoice_lines
WHERE sku = 'NOT-EXIST';
```

Phân biệt không có giao dịch với giao dịch có giá trị 0 khi nghiệp vụ cần lưu dấu vết.

---

## 12. Schema minh họa: ví đa tiền tệ bằng minor units

Tại database lab, tạo bảng reference currency và ví tiền. Dùng schema `money_lab` để không ảnh hưởng các ví dụ trước:

```sql
CREATE TABLE money_lab.currency_units (
    code VARCHAR(3) PRIMARY KEY
        CHECK (code ~ '^[A-Z]{3}$'),
    minor_digits SMALLINT NOT NULL
        CHECK (minor_digits BETWEEN 0 AND 3)
);

INSERT INTO money_lab.currency_units (code, minor_digits)
VALUES
    ('USD', 2),
    ('VND', 0),
    ('JPY', 0),
    ('KWD', 3);

CREATE TABLE money_lab.wallets (
    wallet_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_label TEXT NOT NULL,
    currency_code VARCHAR(3) NOT NULL
        REFERENCES money_lab.currency_units(code),
    balance_minor BIGINT NOT NULL
        CHECK (balance_minor >= 0)
);
```

Nạp dữ liệu ví:

```sql
INSERT INTO money_lab.wallets (
    owner_label, currency_code, balance_minor
)
VALUES
    ('Alice USD', 'USD', 10005),
    ('Bob USD',   'USD', 2500),
    ('Chi VND',   'VND', 125000),
    ('Dao JPY',   'JPY', 1500),
    ('Em KWD',    'KWD', 1234);
```

Xem theo đơn vị chính:

```sql
SELECT
    w.owner_label,
    w.currency_code,
    w.balance_minor,
    c.minor_digits,
    w.balance_minor::NUMERIC
        / POWER(10::NUMERIC, c.minor_digits) AS major_amount
FROM money_lab.wallets AS w
JOIN money_lab.currency_units AS c
  ON c.code = w.currency_code
ORDER BY w.wallet_id;
```

Dữ liệu số `10005` có nghĩa là **100.05 USD** nếu `minor_digits = 2`, còn `125000` với VND và scale 0 có nghĩa **125000 VND**.

### 12.1. Nhóm tổng theo currency

```sql
SELECT
    currency_code,
    SUM(balance_minor) AS total_minor
FROM money_lab.wallets
GROUP BY currency_code
ORDER BY currency_code;
```

Không sử dụng:

```sql
-- Ví dụ tính toán sai về ý nghĩa đơn vị, dù SQL hợp lệ.
SELECT SUM(balance_minor) FROM money_lab.wallets;
```

vì nó gộp các đơn vị khác nhau.

### 12.2. Không thay minor_digits của currency theo cách tùy tiện

Nếu metadata `USD = 2` bị đổi thành `USD = 0`, toàn bộ các số dư USD sẽ được diễn giải khác. Đây là lỗi rất nghiêm trọng, dù không có hàng nào ở `wallets` bị UPDATE.

Trong môi trường production, phải:

- Giới hạn quyền sửa bảng currency metadata.
- Xác định chuẩn và phiên bản scale dùng cho dữ liệu lịch sử.
- Lập kế hoạch chuyển đổi dữ liệu trước mọi thay đổi không tương thích.
- Kiểm tra tích hợp với cổng thanh toán và các hệ thống liên quan.
- Lưu audit/phê duyệt khi metadata ảnh hưởng tiền.

---

## 13. Tính tiền thuế, chiết khấu và phí với precision phù hợp

Những phép toán tiền thường kết hợp nhiều loại giá trị:

| Loại dữ liệu | Ví dụ kiểu | Lý do |
| --- | --- | --- |
| Giá cuối cùng USD | `NUMERIC(18,2)` | Hai chữ số lẻ cho số tiền thu |
| Đơn giá trước khi chốt | `NUMERIC(18,4)` | Có thể cần fraction nhỏ hơn cent |
| Số lượng | `NUMERIC(12,3)` | Hàng có trọng lượng/thể tích |
| Thuế suất | `NUMERIC(9,6)` | Tỷ lệ có nhiều chữ số thập phân |
| Phần trăm chiết khấu | `NUMERIC(9,6)` | Không phải số tiền; có miền như 0..1 |
| Tỷ giá | `NUMERIC(24,10)` hoặc theo nghiệp vụ | Cần precision lớn hơn tiền cuối cùng |
| Số tiền đã chốt theo cents | `BIGINT` | Giá trị nguyên sau rounding |

### 13.1. Biểu diễn tỷ lệ như thế nào?

Có thể lưu tỷ lệ dưới dạng số thập phân:

```sql
SELECT
    120.00::NUMERIC * 0.075::NUMERIC
        AS seven_point_five_percent;
```

Kết quả `9.00000...` tùy cách hiển thị.

Hoặc dưới dạng basis points (bps):

```text
1 bps = 0.01%
750 bps = 7.50%
```

Tính phí từ `amount_minor`:

```sql
SELECT
    ROUND(
        12345::NUMERIC * 750::NUMERIC / 10000::NUMERIC,
        0
    )::BIGINT AS fee_minor;
```

Với số tiền 12345 cents và phí 750 bps (7.5%), giá trị thập phân trước rounding là 925.875 cents, làm tròn theo policy minh họa thành 926 cents.

Điều quan trọng là **chọn được cơ chế rounding đúng với hợp đồng phí**, không phải chỉ áp dụng một công thức đúng về số học.

### 13.2. Số âm trong hoàn trả và điều chỉnh

Không phải tất cả các giá trị tiền đều phải không âm:

- Giá niêm yết thường không âm.
- Số dư ví thuộc mô hình prepaid có thể phải không âm.
- Bút toán kế toán có thể là debit/credit hoặc signed amount.
- Khoản hoàn tiền có thể biểu diễn bằng dòng điều chỉnh âm trong một mô hình cụ thể.

Đừng đặt `CHECK(amount >= 0)` một cách máy móc trên mọi bảng. Thay vào đó, mỗi bảng cần ràng buộc **theo ý nghĩa của trường**.

Ví dụ một bảng bút toán có thể dùng:

```sql
CREATE TABLE money_lab.ledger_entries (
    entry_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    wallet_id BIGINT NOT NULL
        REFERENCES money_lab.wallets(wallet_id),
    signed_amount_minor BIGINT NOT NULL
        CHECK (signed_amount_minor <> 0),
    operation_key TEXT NOT NULL UNIQUE,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Tuy nhiên, một bảng entry như trên **chưa tự bảo đảm sổ cái cân bằng** hoặc tổng bút toán bằng 0. Các invariant nhiều hàng cần cơ chế transaction và thiết kế nghiệp vụ riêng.

---

## 14. Quy đổi ngoại tệ: rate và money là hai đại lượng khác

Một tỷ giá cần ít nhất:

- Currency nguồn.
- Currency đích.
- Giá trị tỷ giá và chiều nhân/chia.
- Thời điểm hiệu lực và thời điểm đã dùng.
- Nguồn cung cấp tỷ giá.
- Precision và quy tắc làm tròn.
- Chính sách phí hoặc spread nếu có.

Ví dụ hoàn toàn **giả định** để minh họa: `1 USD = 25.000 VND`. Không sử dụng tỷ giá này như dữ liệu thị trường hiện hành.

Chuyển `123.45 USD` sang VND:

```sql
SELECT
    123.45::NUMERIC AS usd_amount,
    25000::NUMERIC AS illustrative_vnd_per_usd,
    ROUND(123.45::NUMERIC * 25000::NUMERIC, 0)
       AS vnd_amount;
```

Kết quả: `3.086.250 VND` trong ví dụ, làm tròn 0 chữ số lẻ.

Khi nguồn tiền lưu `minor units` là cents:

```sql
SELECT
    ROUND(
       (12345::NUMERIC / 100::NUMERIC)
       * 25000::NUMERIC,
       0
    )::BIGINT AS vnd_minor;
```

Kết quả cũng là `3086250` với giả định VND dùng scale 0.

### 14.1. Không ép tỷ giá xuống scale của tiền cuối cùng

Nếu tỷ giá nhỏ, ví dụ từ currency A sang B là `0.0001234567`, kiểu `NUMERIC(18,2)` có thể làm tròn thành `0.00` và khiến quy đổi bằng 0.

Vì vậy:

- Lưu tỷ giá với precision/scale phù hợp theo yêu cầu.
- Tính trung gian bằng `NUMERIC` đủ độ chính xác.
- Làm tròn **giá trị tiền đích** theo scale và policy của currency đích.
- Lưu lại rate, currency pair và thời điểm đã sử dụng nếu cần tái lập kết quả về sau.

### 14.2. Không lấy rate hiện tại để tính lại giao dịch quá khứ

Nếu giao dịch được chốt hôm qua với rate X, hôm nay rate đổi thành Y, báo cáo số tiền đã thanh toán không được tự thay đổi chỉ vì hệ thống gọi lại dịch vụ tỷ giá.

Dữ liệu cần lưu một **snapshot** của thông số tính tại thời điểm giao dịch theo yêu cầu đối soát, ví dụ `rate_applied`, `source_currency`, `target_currency` và `converted_amount_minor`.

---

## 15. Transaction và ràng buộc bảo vệ số tiền

Chọn đúng kiểu dữ liệu là cần thiết, nhưng chưa đủ để bảo vệ ví tiền khỏi hai request cập nhật đồng thời.

Giả sử hai ví USD trong bảng `money_lab.wallets` có số dư 10005 và 2500 cents. Cần chuyển 3000 cents từ ví thứ nhất sang ví thứ hai.

Một câu UPDATE có điều kiện giúp tránh trừ khi không đủ tiền:

```sql
UPDATE money_lab.wallets
SET balance_minor = balance_minor - 3000
WHERE owner_label = 'Alice USD'
  AND currency_code = 'USD'
  AND balance_minor >= 3000
RETURNING wallet_id, balance_minor;
```

Nếu không trả về hàng nào, thao tác trừ không diễn ra. **Ứng dụng phải coi đây là một nhánh nghiệp vụ cần xử lý**, không tự coi câu SQL chạy xong là chuyển tiền thành công.

Nhưng chuyển tiền không chỉ có trừ tiền: còn cộng tiền, ghi lịch sử, kiểm tra currency và khóa chống request trùng. Những bước này cần cùng transaction, ví dụ ở mức thiết kế:

```text
BEGIN
  Kiểm tra idempotency / tính hợp lệ yêu cầu
  Xác định hai ví có cùng currency
  Khóa các hàng liên quan theo thứ tự ổn định khi cần
  Trừ amount_minor với điều kiện đủ tiền
  Kiểm tra đúng một hàng được cập nhật
  Cộng amount_minor cho ví nhận
  Kiểm tra đúng một hàng được cập nhật
  Ghi ledger / kết quả yêu cầu
COMMIT

Bất kỳ lỗi hoặc điều kiện sai -> ROLLBACK
```

Đây là mô hình giao dịch, không phải SQL script hoàn chỉnh xử lý đầy đủ idempotency và đối soát. Trong production phải dùng giao dịch có kiểm soát, khóa và unique key thích hợp.

### 15.1. Vì sao phải kiểm tra currency ở tầng nghiệp vụ?

Hai ví có thể có cùng kiểu `BIGINT balance_minor` nhưng một ví USD, ví kia VND. Cộng và trừ cùng số nguyên `3000` giữa chúng mà không có bước đổi tiền là sai.

Hệ thống nên coi tiền như một cấu trúc:

```text
Money {
    currency: 'USD',
    minor_units: 3000
}
```

và chỉ cho cộng hai giá trị có cùng currency/scale. Mọi phép quy đổi khác currency phải qua một nghiệp vụ chuyển đổi có rate và rounding tường minh.

### 15.2. Constraint giúp nhưng không bảo vệ toàn bộ số dư

`CHECK(balance_minor >= 0)` ngăn một hàng ví có số dư âm. Nhưng nó không tự đảm bảo:

- Một lần chuyển tiền có hai bút toán cân bằng.
- Giao dịch đến từ người có quyền.
- Client retry không bị trừ tiền hai lần.
- Tham chiếu currency và rate chính xác theo thời điểm.
- Tổng doanh thu khớp giao dịch đã thanh toán.

Cần phối hợp kiểu dữ liệu, constraint, transaction, isolation level, idempotency và audit.

---

## 16. Nhập dữ liệu tiền từ CSV, JSON hoặc hệ thống khác

Một nguồn lỗi precision rất hay gặp không nằm trong PostgreSQL, mà xuất hiện **trước khi dữ liệu đến database**.

Ví dụ:

1. Client gửi chuỗi `"19.99"`.
2. Backend parse thành `double`.
3. Code thực hiện nhiều phép tính floating point.
4. Giá trị mới được chuyển thành `BigDecimal` hoặc `NUMERIC`.
5. Database lưu số đã bị ảnh hưởng bởi cách biểu diễn/rounding trung gian.

Dù cột cuối là `NUMERIC(18,2)`, dữ liệu gốc có thể đã bị thay đổi trước khi lưu.

### 16.1. Nhận decimal bằng string hoặc decimal-aware parser

Với API nhận giá trị tiền ở đơn vị chính, một hợp đồng rõ ràng có thể là:

```json
{
  "currency": "USD",
  "amount": "19.99"
}
```

Dạng chuỗi decimal cho phép backend kiểm soát:

- Đúng số chữ số phần lẻ.
- Dấu âm có được phép không.
- Phạm vi giá trị.
- Ký tự phân cách thập phân.
- Quy tắc chuyển sang `BigDecimal` hoặc minor units.

Nếu API chọn JSON number thay vì string, thư viện/parser phải được đánh giá về giới hạn precision, đặc biệt nếu dữ liệu đi qua JavaScript.

### 16.2. Minor units trong JSON

Một API khác có thể dùng:

```json
{
  "currency": "USD",
  "amount_minor": 1999
}
```

Điều này rất rõ nếu toàn bộ tích hợp đã đồng ý rằng `amount_minor` là số nguyên theo scale của currency và có giới hạn range an toàn.

Nhưng JavaScript `Number` chỉ biểu diễn chính xác số nguyên tới một giới hạn an toàn (thường nhắc tới `2^53 - 1`). `BIGINT` của PostgreSQL có miền rộng hơn đáng kể.

Do đó, với số nguyên rất lớn trong JSON đi qua JavaScript, có thể cần gửi dạng **string số nguyên**, dùng BigInt/decimal library phù hợp, hoặc giới hạn miền theo hợp đồng API.

### 16.3. CSV có dấu thập phân theo locale

File CSV có thể chứa:

```csv
order_id,currency,amount
1,USD,19.99
2,VND,125000
```

Trong khi một file khác dùng dấu phẩy thập phân hoặc phân cách hàng nghìn theo locale:

```text
19,99
1.234,50
```

Không thể giả định PostgreSQL `NUMERIC` parser tự hiểu mọi cách viết số tiền theo locale. Khi dữ liệu từ nhiều nước:

1. Định nghĩa rõ encoding và delimiter CSV.
2. Đưa dữ liệu về **chuỗi decimal chuẩn** trước khi ép kiểu.
3. Phân biệt dấu phân cách trường và dấu phân cách số.
4. Kiểm tra currency và scale từng hàng.
5. Đối soát số lượng/tổng tiền sau import.
6. Không đưa những giá trị không parse được thành 0 một cách âm thầm.

---

## 17. Kiểm soát số chữ số lẻ đầu vào

Một vấn đề cần thiết kế rõ: cột `NUMERIC(18,2)` **sẽ làm tròn đầu vào** nếu số có hơn hai chữ số lẻ. Trong một số nghiệp vụ, đó là điều mong muốn; trong một số nghiệp vụ khác, đây là dữ liệu **không hợp lệ cần từ chối**.

Giả sử API chỉ chấp nhận USD có tối đa 2 chữ số sau dấu thập phân.

### 17.1. Không thể dựa vào CHECK sau khi đã cast vào NUMERIC(18,2)

Ví dụ:

```sql
CREATE TABLE money_lab.received_amounts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    amount NUMERIC(18,2) NOT NULL
        CHECK (amount = ROUND(amount, 2))
);
```

Nếu insert `19.999`, PostgreSQL đã có thể làm tròn giá trị thành `20.00` khi ép vào kiểu của cột, nên `CHECK(amount = ROUND(amount,2))` không phát hiện được việc client gửi ba chữ số lẻ.

Điều này minh họa: **constraint trên giá trị sau ép kiểu không luôn xác định được input gốc**.

### 17.2. Kiểm tra trước khi ép kiểu

Có thể đưa dữ liệu vào staging `TEXT` hoặc xử lý trong ứng dụng bằng decimal parser:

```sql
CREATE TABLE money_lab.amount_staging (
    source_id TEXT PRIMARY KEY,
    currency_code VARCHAR(3) NOT NULL,
    amount_text TEXT NOT NULL
);
```

Ví dụ nhận:

```sql
INSERT INTO money_lab.amount_staging
    (source_id, currency_code, amount_text)
VALUES
    ('a1', 'USD', '19.99'),
    ('a2', 'USD', '19.999'),
    ('a3', 'USD', '-1.00');
```

Trong ví dụ **chỉ cho USD không âm với tối đa hai chữ số lẻ**, có thể phát hiện format sai:

```sql
SELECT *
FROM money_lab.amount_staging
WHERE currency_code = 'USD'
  AND amount_text !~ '^[0-9]+(\.[0-9]{1,2})?$';
```

Kết quả có thể bao gồm `19.999` và `-1.00`.

Regex này **chỉ kiểm tra hình thức đầu vào**, chưa xác minh miền số `NUMERIC(18,2)`, chưa cho phép ký hiệu tiền, dấu cách hoặc locale, chưa xử lý tất cả currency. Không biến nó thành quy tắc production mà không bổ sung kiểm tra nghiệp vụ, giới hạn độ dài và conversion errors.

### 17.3. Không nên dùng TEXT làm kiểu tiền lâu dài

Một cột text có thể giữ nguyên `"19.999"` để phục vụ kiểm tra input, nhưng dùng text làm trường tiền chính gây khó khăn:

- Không thể cộng/trừ đúng bằng các toán tử số.
- Dễ chứa nhiều format không thống nhất.
- Sắp xếp chuỗi khác sắp xếp giá trị số.
- Không ngăn dữ liệu như `'abc'` nếu thiếu constraint.
- Tốn công chuyển đổi ở mọi truy vấn tài chính.

Vì vậy **TEXT phù hợp staging/raw source**, còn bảng nghiệp vụ nên chuyển sang `NUMERIC` hoặc minor-unit integer theo thiết kế đã xác nhận.

---

## 18. Java: dùng BigDecimal khi tương tác với NUMERIC

Ứng dụng Java kết nối PostgreSQL qua JDBC thường dùng `java.math.BigDecimal` cho `NUMERIC/DECIMAL`.

### 18.1. Khởi tạo BigDecimal đúng cách

Cách nên dùng:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("19.99");
BigDecimal quantity = new BigDecimal("2.5");

BigDecimal raw = price.multiply(quantity);
BigDecimal amount = raw.setScale(2, RoundingMode.HALF_UP);

System.out.println(amount); // 49.98 (theo HALF_UP)
```

Trong trường hợp này, `19.99 × 2.5 = 49.975`, làm tròn HALF_UP hai chữ số thành `49.98`.

Không nên mặc định:

```java
// Không nên dùng để dựng decimal money từ literal double.
BigDecimal amount = new BigDecimal(0.1);
```

Vì `0.1` ở đây là một `double` nhị phân, `new BigDecimal(double)` có thể giữ biểu diễn chính xác của giá trị nhị phân đó, không phải chính xác chuỗi thập phân `"0.1"` mà người viết mong muốn.

Những lựa chọn tốt hơn:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = BigDecimal.valueOf(0.1);
```

`BigDecimal.valueOf(double)` dùng biểu diễn decimal của double theo quy tắc Java và thường tốt hơn constructor trực tiếp từ double; tuy nhiên, **nếu giá trị đã qua nhiều phép tính bằng double, nó không khôi phục được ý định số học ban đầu**. Với money, ưu tiên parse decimal từ string ngay từ đầu.

### 18.2. Làm tròn rõ ràng trong ứng dụng

```java
BigDecimal taxRate = new BigDecimal("0.075");
BigDecimal base = new BigDecimal("120.00");

BigDecimal rawTax = base.multiply(taxRate);
BigDecimal tax = rawTax.setScale(2, RoundingMode.HALF_UP);
```

Không mặc định mọi module dùng `HALF_UP`. Nếu yêu cầu là `HALF_EVEN` hoặc cơ chế khác, hãy đặt nó rõ trong domain/business rules và đảm bảo PostgreSQL/backend cùng dùng chính sách phù hợp.

Đặc biệt, phép chia BigDecimal nếu kết quả thập phân vô hạn có thể cần khai báo scale/rounding mode, ví dụ:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal oneThird = one.divide(
    three, 8, RoundingMode.HALF_UP
);
```

Nếu không chỉ định cách xử lý trong trường hợp kết quả vô hạn, phép chia có thể ném lỗi arithmetic.

### 18.3. Truyền NUMERIC với JDBC

Ví dụ sử dụng `PreparedStatement`:

```java
BigDecimal payment = new BigDecimal("19.99");

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO payments (amount_usd) VALUES (?)")) {
    ps.setBigDecimal(1, payment);
    ps.executeUpdate();
}
```

Đây là **mẫu code JDBC**, bảng `payments` trong ví dụ chưa được tạo ở lab. Điểm chính là dùng `setBigDecimal` thay vì ép tiền sang `double`.

Khi đọc:

```java
BigDecimal stored = resultSet.getBigDecimal("amount_usd");
```

Với thiết kế minor units, có thể dùng `setLong`/`getLong` và một kiểu domain money chứa currency + minor amount. Hãy xử lý `NULL` từ JDBC cẩn thận (ví dụ `getLong` trả 0 cho NULL và phải kiểm tra `wasNull()` nếu cột nullable).

### 18.4. Đừng cho frontend quyết định kết quả cuối cùng một mình

Frontend có thể hiển thị giá tiền đã làm tròn, nhưng backend cần tính/kiểm tra số tiền phải trả từ dữ liệu đã được phê duyệt. Không tin mù vào `total=...` do client gửi, vì client có thể sai logic hoặc bị sửa dữ liệu.

PostgreSQL constraints bảo vệ kiểu và miền dữ liệu, nhưng quyền áp giá, thuế, khuyến mãi và tỷ giá là quy tắc nghiệp vụ cần được kiểm soát ở tầng phù hợp.

---

## 19. NUMERIC, BIGINT và thứ tự quyết định trong kiến trúc

Một cách chọn theo tiêu chí:

| Câu hỏi | Nếu “có” | Gợi ý |
| --- | --- | --- |
| Hệ thống lưu số tiền cuối theo cents/đồng và hạ tầng đã thống nhất minor units? | Có | Cân nhắc `BIGINT` kèm currency code và scale metadata |
| Cần lưu đơn giá có 4–8 chữ số lẻ hoặc tỷ giá chi tiết? | Có | Cân nhắc `NUMERIC(p,s)` phù hợp |
| Có nhiều currency với scale khác nhau? | Có | Cần currency code + quy tắc scale; không cố định mọi thứ ở 2 chữ số |
| Có yêu cầu tốc độ/lưu trữ rất cao và toán học chỉ với số nguyên? | Có | `BIGINT` thường có lợi nếu miền số và phép tính phù hợp |
| Có phép chia hoặc % thuế/phí phức tạp? | Có | Tính trung gian bằng `NUMERIC`, rồi lượng tử hóa theo quy tắc cuối |
| Cần hiển thị ký hiệu tiền trong nhiều locale? | Có | Để tầng giao diện định dạng từ amount + currency; không phụ thuộc `MONEY` output |
| Có yêu cầu chính xác tới đơn vị nhỏ nhất của nghiệp vụ? | Có | Tránh binary float cho số tiền đã chốt |
| Đang có legacy `MONEY` hoặc `FLOAT`? | Có | Xây kế hoạch migration/đối soát trước khi thay type |

Có thể dùng **cả hai representation trong cùng hệ thống** khi có lý do:

- Bảng đơn giá: `NUMERIC(18,4)`.
- Bảng kết quả chốt giá: `NUMERIC(18,2)` hoặc `BIGINT cents`.
- Bảng sổ cái thanh toán: `BIGINT minor units`.
- Bảng tỷ giá: `NUMERIC(24,10)`.
- Truy vấn báo cáo: quy đổi sang `NUMERIC` để trình bày/tính toán.

Nhưng phải có **hợp đồng chuyển đổi rõ ràng**, tránh một bảng xem `100` là đô la và bảng khác xem `100` là cents.

---

## 20. Migration từ FLOAT/MONEY sang kiểu rõ ràng hơn

Đổi kiểu một cột tiền trên bảng đã có dữ liệu là thay đổi nghiệp vụ, không chỉ thay cú pháp DDL.

### 20.1. Những câu hỏi trước khi migration

1. Giá trị hiện có được lưu theo **đơn vị nào**?
2. Nếu là floating point, dữ liệu gốc còn ở đâu để đối soát?
3. Có bao nhiêu currency trong cùng cột?
4. Có giá âm, NULL, NaN, Infinity hoặc giá ngoài phạm vi không?
5. Có cần làm tròn tới 2, 0 hay 3 chữ số tùy currency?
6. Các báo cáo và API hiện có đang giả định kiểu nào?
7. Có khóa hoặc unique constraint nào bị ảnh hưởng?
8. Có thể dừng ghi hoặc chuyển đổi hai pha để tránh race condition không?

### 20.2. Không cast mù từ DOUBLE sang NUMERIC

Ví dụ minh họa:

```sql
SELECT
    19.999::DOUBLE PRECISION::NUMERIC(18,2)
        AS decimal_after_float;
```

Kết quả là giá trị sau quá trình float và rounding/cast, **không bảo đảm phản ánh ý định gốc của source system**.

Một quy trình migration an toàn hơn thường gồm:

```text
Khảo sát dữ liệu legacy
      |
      v
Xác định unit/currency và quy tắc rounding
      |
      v
Tạo cột/bảng mới với type phù hợp
      |
      v
Chuyển đổi theo batch hoặc giai đoạn kiểm soát
      |
      v
Đối soát dữ liệu từng hàng + tổng theo currency
      |
      v
Cập nhật writer/reader/API
      |
      v
Chuyển đổi chính thức và giám sát
```

### 20.3. Ví dụ chuyển số USD decimal sang cents

Giả sử một bảng staging có `amount_usd NUMERIC` và đã kiểm tra dữ liệu.

```sql
SELECT
    amount_usd,
    ROUND(amount_usd * 100, 0)::BIGINT AS amount_cents
FROM some_validated_usd_staging;
```

Đây là **mẫu SQL**, bảng `some_validated_usd_staging` chưa được tạo ở lab.

Nó chỉ phù hợp khi:

- Currency thực sự là USD.
- `amount_usd` được đo bằng đô la.
- Quy tắc làm tròn cho phép chuyển sang cents.
- Kết quả nằm trong miền BIGINT.
- Dữ liệu nguồn đã được xác minh và tổng sau chuyển đổi được đối soát.

Không tự biến mọi số thập phân không hợp lệ thành số được làm tròn khi chính sách yêu cầu từ chối.

---

## 21. Hiệu năng và lưu trữ

Một lựa chọn type không thể chỉ dựa vào tính chính xác; workload cũng quan trọng.

### 21.1. BIGINT và NUMERIC

`BIGINT` có kích thước cố định 8 byte. `NUMERIC` dùng biểu diễn decimal có kích thước biến thiên theo số chữ số và thường tốn thêm CPU cho một số phép toán so với integer.

Điều đó có thể quan trọng khi:

- Bảng có hàng trăm triệu bản ghi.
- Có nhiều phép cộng, so sánh, sort và index trên cột tiền.
- Chạy tổng hợp tài chính theo thời gian thực ở tần suất cao.
- Có giới hạn lưu trữ/IO nghiêm ngặt.

Tuy nhiên, **không đổi sang BIGINT chỉ vì nó nhanh hơn trong một benchmark nhỏ** nếu điều đó làm sai đơn vị hoặc buộc application viết nhiều phép chuyển đổi thiếu kiểm soát. Chi phí sai số hoặc lỗi nghiệp vụ cao hơn lợi ích vài phần trăm tốc độ.

### 21.2. Index và truy vấn có điều kiện

Có thể index cột số tiền nếu query pattern cần:

```sql
CREATE INDEX idx_wallets_currency_balance
ON money_lab.wallets (currency_code, balance_minor);
```

Chỉ số kết hợp currency + amount hữu ích hơn chỉ amount khi truy vấn thường lọc theo currency.

Ví dụ:

```sql
SELECT wallet_id, balance_minor
FROM money_lab.wallets
WHERE currency_code = 'USD'
  AND balance_minor >= 10000
ORDER BY balance_minor;
```

Index cần được đánh giá bằng `EXPLAIN` và dữ liệu thực. Bảng lab 5 hàng có thể được PostgreSQL chọn sequential scan vì rẻ hơn, hoàn toàn bình thường.

### 21.3. Không chuyển tiền thành chuỗi để ORDER BY

Ví dụ những chuỗi:

```text
'2.00'
'19.00'
'100.00'
```

Sắp xếp theo text khác sắp xếp theo số. Dữ liệu tiền nên được lưu dưới kiểu số, kèm currency, còn việc format “100,00 €” hoặc “100.00 USD” thuộc tầng hiển thị.

---

## 22. Những lỗi thường gặp

| Sai lầm | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| Lưu tiền bằng `DOUBLE PRECISION` cho mọi giao dịch | Không biểu diễn chính xác mọi decimal | Dùng `NUMERIC` hoặc `BIGINT` minor units theo yêu cầu |
| Dùng `NUMERIC(10,2)` cho mọi loại tiền | Currency có scale khác; đơn giá/rate có thể cần nhiều chữ số hơn | Thiết kế scale theo đại lượng và currency |
| Coi `NUMERIC(18,2)` là bộ kiểm tra “tối đa 2 số lẻ đầu vào” | Type có thể tự làm tròn trước constraint | Validate trước cast hoặc dùng staging |
| Dùng `MONEY` và tưởng PostgreSQL lưu mã tiền | Kiểu money không gắn currency code nghiệp vụ | Lưu currency riêng, dùng numeric/minor units khi phù hợp |
| Lưu `100` mà không nói là cents hay USD | Hệ thống khác có thể hiểu sai gấp 100 lần | Ghi rõ tên cột và API contract |
| Cộng `USD` với `JPY` trực tiếp | Sai về đơn vị dù SQL chạy | Nhóm theo currency, quy đổi theo rate có hiệu lực |
| Dùng `ROUND` mỗi bước tính | Có thể tích lũy sai khác | Làm tròn ở mốc nghiệp vụ đã định |
| Tin rằng `ROUND(numeric)` là half-even | Quy tắc ties có thể khác chính sách | Xác định mode rõ, triển khai đồng bộ |
| Parse tiền vào Java `double` rồi mới BigDecimal | Đã đưa sai số nhị phân vào pipeline | Parse string trực tiếp sang `BigDecimal` |
| Dùng `new BigDecimal(0.1)` | Ghi nhận giá trị nhị phân của double | `new BigDecimal("0.1")` hoặc decimal parser |
| Dùng JS Number cho `BIGINT` lớn | Vượt miền số nguyên chính xác của JavaScript | String/BigInt và API contract phù hợp |
| Dùng `INTEGER` cho số dư lớn | Rủi ro overflow | Ước lượng miền số, cân nhắc `BIGINT` |
| Dùng `NUMERIC` nhưng không giới hạn miền giá trị | Có thể cho phép giá âm/vô lý tùy nghiệp vụ | CHECK/NOT NULL và validation |
| Chỉ lưu tỷ giá 2 chữ số lẻ | Mất precision khi quy đổi | Lưu rate với precision phù hợp |
| Tính lại giao dịch cũ theo tỷ giá mới | Sai số tiền lịch sử | Lưu snapshot rate và kết quả đã chốt |
| Dùng cùng một scale cho sản phẩm, thuế và giá thanh toán | Đơn giá và tiền cuối khác độ phân giải | Tách kiểu/scale theo ý nghĩa từng cột |
| Không kiểm tra `UPDATE ... RETURNING` | Có thể ảnh hưởng 0 hàng mà không báo SQL lỗi | Kiểm tra số hàng, rollback giao dịch khi cần |
| Chỉ có CHECK số dư không âm, không có transaction | Có thể trừ một bên mà chưa cộng bên kia | Giao dịch atomic và bảo vệ concurrency |
| Đổi currency minor_digits trực tiếp | Toàn bộ giá trị cũ bị diễn giải sai | Metadata versioning/migration có đối soát |

---

## 23. Bài tập thực hành

### Bài 1 — Đọc precision và scale

Với `NUMERIC(12,2)`:

1. Có tối đa bao nhiêu chữ số phần nguyên?
2. Giá trị `9999999999.99` có hợp lệ không?
3. Giá trị `10000000000.00` có hợp lệ không?
4. PostgreSQL xử lý `12.345` ra sao khi ép vào `NUMERIC(12,2)`?
5. Vì sao dấu âm và dấu chấm không tính vào precision?

### Bài 2 — NUMERIC so với DOUBLE PRECISION

Chạy:

```sql
SELECT
    (0.1::NUMERIC + 0.2::NUMERIC) = 0.3::NUMERIC
        AS numeric_equal,
    (0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION)
        = 0.3::DOUBLE PRECISION AS floating_equal;
```

Giải thích lý do hai kết quả có thể khác nhau, và vì sao không nên dựa trên so sánh float bằng `=` cho những khoản tiền đã chốt.

### Bài 3 — BIGINT theo cents

Với `amount_cents = 1599`:

1. Giá trị USD tương ứng là bao nhiêu?
2. Tăng thêm 250 cents thì số nguyên mới là bao nhiêu?
3. Viết SQL dùng `NUMERIC` để hiển thị với hai chữ số lẻ.
4. Nếu cùng số nguyên 1599 được ghi cho VND với scale 0, giá trị biểu diễn là bao nhiêu VND?

### Bài 4 — Round theo dòng và theo tổng

Tính 10% của hai dòng có giá 0.05 USD mỗi dòng. So sánh:

- Làm tròn thuế từng dòng tới 2 số lẻ rồi cộng.
- Cộng cơ sở trước, tính thuế rồi làm tròn một lần.

Vì sao hai kết quả không bằng nhau? Ai phải quyết định chính sách được dùng?

### Bài 5 — Đơn giá có bốn chữ số lẻ

Một sản phẩm có `quantity = 100`, `unit_price = 0.0150 USD`.

Hãy tính:

```sql
SELECT
    ROUND(0.0150::NUMERIC, 2) * 100
        AS rounded_price_first,
    ROUND(0.0150::NUMERIC * 100, 2)
        AS rounded_total;
```

Giải thích vì sao chỉ cất đơn giá vào `NUMERIC(18,2)` có thể làm sai tổng tiền.

### Bài 6 — Thiết kế bảng đa tiền tệ

Dùng bảng `money_lab.currency_units` và `money_lab.wallets`. Thêm một ví JPY với `balance_minor = 3500` và một ví USD với `balance_minor = 3500`.

Viết SQL hiển thị số tiền chính của từng ví, nhóm tổng theo currency và giải thích vì sao không được cộng hai số `3500` trực tiếp.

### Bài 7 — Validate đầu vào trước khi cast

Giả sử API nhận USD trong các chuỗi:

```text
"19.99"
"19.999"
"0"
"-1.00"
"abc"
```

Nếu chính sách yêu cầu **không âm, tối đa 2 chữ số lẻ, định dạng decimal dùng dấu chấm**, hãy chỉ ra giá trị hợp lệ. Tại sao chỉ định nghĩa cột `NUMERIC(18,2)` không đủ để chặn `19.999`?

### Bài 8 — Kiểu MONEY

Chạy:

```sql
SHOW lc_monetary;
SELECT 10.25::MONEY AS sample_money;
```

Giải thích vì sao output có thể khác giữa môi trường có locale khác nhau. Kiểu `MONEY` có tự phân biệt giá trị 10.25 USD và 10.25 EUR không?

### Bài 9 — Java BigDecimal

So sánh:

```java
new BigDecimal(0.1)
new BigDecimal("0.1")
BigDecimal.valueOf(0.1)
```

Hãy giải thích kiểu nào giữ trực tiếp chuỗi decimal mong muốn và vì sao không nên qua một loạt phép toán `double` trước khi xây `BigDecimal` cho tiền.

### Bài 10 — Kiểm tra kiểu cho tỷ giá

Giả sử tỷ giá (giả định) là `0.0001234567`. So sánh:

```sql
SELECT
    0.0001234567::NUMERIC(18,2) AS badly_scaled_rate,
    0.0001234567::NUMERIC(18,10) AS better_scaled_rate;
```

Tại sao `NUMERIC(18,2)` phù hợp một số tiền USD cuối cùng nhưng không phù hợp để lưu tỷ giá trong tình huống này?

### Bài 11 — Transaction chuyển tiền

Thiết kế quy trình chuyển 3000 cents giữa hai ví USD:

- Kiểm tra hai ví cùng currency.
- Kiểm tra đủ tiền.
- Trừ/cộng trong cùng transaction.
- Kiểm tra số hàng cập nhật.
- Ghi một khóa yêu cầu không trùng để chống retry.
- Rollback nếu một bước không đạt.

Giải thích vì sao `CHECK(balance_minor >= 0)` chưa đủ để bảo đảm tổng hai ví được bảo toàn.

### Bài 12 — Chọn mô hình lưu trữ

Một hệ thống có:

1. Giá niêm yết một sản phẩm dùng USD và có thể nhỏ hơn 0.01 USD mỗi đơn vị.
2. Số tiền thanh toán cuối bằng cents.
3. Tỷ giá với 10 chữ số thập phân.
4. Mã currency và scale khác nhau theo currency.
5. Báo cáo tổng theo từng currency.

Hãy đề xuất kiểu dữ liệu cho từng thành phần, thời điểm rounding và một quy tắc kiểm tra không được cộng tiền khác currency.

---

## 24. Checklist trước khi đưa kiểu dữ liệu tiền vào production

| Câu hỏi thiết kế | Điều cần quyết định |
| --- | --- |
| Số tiền là loại giá trị nào? | Giá, số dư, thuế, phí, hoàn tiền, ledger entry, tỷ giá |
| Dùng major unit hay minor unit? | `NUMERIC` trực tiếp hay `BIGINT` theo đơn vị nhỏ nhất |
| Currency được lưu ở đâu? | Cột mã currency hoặc quan hệ với đối tượng tiền tệ |
| Scale nào đúng? | Theo currency và theo ngữ nghĩa field |
| Có cần số lẻ nhỏ hơn đơn vị thanh toán? | Scale lớn hơn cho đơn giá/tính toán trung gian |
| Miền số tối đa? | Chọn precision phù hợp, cân nhắc overflow |
| Có được nhập số âm hoặc 0? | `CHECK` riêng cho từng loại giao dịch |
| Làm tròn ở bước nào? | Dòng, tổng, thuế, phí, quy đổi, thanh toán |
| Rounding mode gì? | Theo hợp đồng và quy định; đồng nhất backend/database |
| Có phải từ chối quá nhiều số lẻ? | Validate trước khi cast/round |
| API/driver dùng kiểu gì? | BigDecimal, string decimal hoặc integer minor units |
| Có hệ thống JavaScript tham gia? | Giới hạn safe integer, cách truyền số lớn |
| Cần đổi currency không? | Rate, thời điểm, cặp tiền, rounding, snapshot |
| Có transaction nhiều bước? | Atomic updates, constraints, concurrency, idempotency |
| Có dữ liệu legacy không? | Migration và đối soát theo currency/batch |
| Có kiểm thử số biên? | Rounding tie, số âm, overflow, NULL, input sai |
| Có kiểm tra tổng báo cáo? | Không SUM lẫn currency, đối chiếu ledger và settlement |

## Kết luận

PostgreSQL có những công cụ tốt để lưu tiền chính xác, nhưng **không có một kiểu dữ liệu tự giải quyết mọi vấn đề tài chính**.

- **`NUMERIC(p,s)`** phù hợp số thập phân cần độ chính xác decimal; hãy chọn precision/scale theo đại lượng và nhớ rằng giá trị đầu vào có thể bị làm tròn khi ép về scale.
- **`BIGINT` minor units** phù hợp số tiền đã chốt theo đơn vị nhỏ nhất, với điều kiện currency và scale được định nghĩa thống nhất, đồng thời kiểm soát overflow.
- **`MONEY`** tồn tại và có ích trong một số môi trường, nhưng locale và scale cố định khiến nó không phải lựa chọn mặc định tối ưu cho hệ thống đa tiền tệ.
- **`REAL`/`DOUBLE PRECISION`** không bảo đảm biểu diễn chính xác các phân số thập phân như `0.1`, vì vậy thường không dùng để lưu số tiền cần đối soát từng đơn vị.
- **Làm tròn, tỷ giá, thuế, tiền tệ và transaction** là những quy tắc nghiệp vụ cần thiết kế rõ, dù kiểu dữ liệu được chọn rất chính xác.

Một thiết kế tốt lưu **giá trị + đơn vị**, giữ đủ precision ở bước trung gian, làm tròn đúng lúc, kiểm tra dữ liệu trước khi chuyển kiểu, và sử dụng transaction cùng constraints để bảo vệ các thay đổi tiền. Khi đó, PostgreSQL trở thành nền tảng đáng tin cậy cho tính toán tài chính mà không đánh đồng độ chính xác của số học với tính đúng của toàn bộ nghiệp vụ.
