# BigDecimal, precision, scale và độ chính xác của tiền tệ

Trong ứng dụng Java sử dụng Hibernate để lưu trữ dữ liệu quan hệ, tiền tệ là trường hợp điển hình đòi hỏi **biểu diễn số thập phân chính xác**, **quy tắc làm tròn rõ ràng** và **kiểu cột cơ sở dữ liệu phù hợp**. Một khoản tiền `19.99`, tỷ lệ thuế `0.075` hoặc số dư `1000000.00` không nên bị thay đổi chỉ vì lựa chọn `double`, để cơ sở dữ liệu tự làm tròn hoặc khai báo sai `precision` và `scale`.

Ba khái niệm chính trong bài:

- **`BigDecimal`**: kiểu số thập phân chính xác của Java, phù hợp để biểu diễn số tiền và tính toán thập phân.
- **`precision`**: số chữ số có nghĩa của giá trị `BigDecimal`, hoặc giới hạn tổng số chữ số trong cột SQL `DECIMAL(p, s)`/`NUMERIC(p, s)`; phải phân biệt hai ngữ cảnh này.
- **`scale`**: số vị trí thập phân; trong SQL `DECIMAL(p, s)` thường là số chữ số tối đa ở bên phải dấu thập phân, còn trong `BigDecimal` là một phần của biểu diễn giá trị và có thể âm.

Kiến thức sẽ được áp dụng tới `@Column(precision = ..., scale = ...)`, `NUMERIC`/`DECIMAL`, JDBC, các phép cộng nhân chia, thuế/phí, quy đổi tiền tệ, validation và giao dịch.

## 1. Vì sao `double` và `float` không phải lựa chọn mặc định cho tiền?

`float` và `double` biểu diễn số theo **dấu phẩy động nhị phân**. Nhiều phân số thập phân quen thuộc, như `0.1` và `0.2`, không có biểu diễn nhị phân hữu hạn, nên chúng phải được xấp xỉ.

```java
double a = 0.1;
double b = 0.2;

System.out.println(a + b); // 0.30000000000000004
System.out.println((a + b) == 0.3); // false
```

Sai số rất nhỏ có thể tích lũy trong các quy trình cộng dồn, phân bổ phí, đối soát, kiểm tra bằng nhau hoặc làm tròn ở các mốc nhạy cảm. Vấn đề nằm ở **cách biểu diễn**, không phải Hibernate hay JDBC có lỗi.

```java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

System.out.println(a.add(b)); // 0.3
System.out.println(a.add(b).compareTo(new BigDecimal("0.3")) == 0); // true
```

`BigDecimal` lưu giá trị thập phân theo một số nguyên không có phần thập phân (*unscaled value*) và hệ số vị trí (*scale*). Do đó, giá trị được khởi tạo từ chuỗi thập phân có thể biểu diễn đúng **chính xác các chữ số trong chuỗi**.

Điều này không đồng nghĩa mọi phép tính đều luôn có biểu diễn hữu hạn: `1 / 3` vẫn có phần thập phân vô hạn, vì vậy **phải chọn quy tắc chia/làm tròn**. `BigDecimal` giúp ứng dụng kiểm soát sai số; nó không tự xác định chính sách kế toán.

## 2. Bên trong BigDecimal: unscaled value và scale

Công thức biểu diễn của Java:

\[
\text{giá trị} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Ví dụ:

| Chuỗi khởi tạo | `unscaledValue()` | `scale()` | `precision()` | Giá trị |
| --- | ---: | ---: | ---: | ---: |
| `"123.45"` | 12345 | 2 | 5 | 123.45 |
| `"123.4500"` | 1234500 | 4 | 7 | 123.4500 |
| `"0.0010"` | 10 | 4 | 2 | 0.0010 |
| `"1000"` | 1000 | 0 | 4 | 1000 |
| `"1E+3"` | 1 | -3 | 1 | 1000 |
| `"0.00"` | 0 | 2 | 1 | 0.00 |

```java
BigDecimal value = new BigDecimal("123.4500");

System.out.println(value.unscaledValue()); // 1234500
System.out.println(value.scale());         // 4
System.out.println(value.precision());     // 7
System.out.println(value.toPlainString()); // 123.4500
```

`BigDecimal` **immutable**: phương thức `add()`, `multiply()`, `setScale()` hoặc `stripTrailingZeros()` tạo ra và trả về đối tượng mới, không sửa chính instance ban đầu.

```java
BigDecimal price = new BigDecimal("10.00");

price.add(new BigDecimal("2.00"));
System.out.println(price); // 10.00: không đổi

price = price.add(new BigDecimal("2.00"));
System.out.println(price); // 12.00
```

### 2.1. Scale có thể âm

`new BigDecimal("1E+3")` biểu diễn `1000` với `scale = -3`. Tương tự, `new BigDecimal("1000.00").stripTrailingZeros()` có thể tạo ra giá trị tương đương `1E+3` với scale âm.

Trong code tiền tệ, **đừng giả định `scale()` luôn bằng 0 hoặc lớn hơn 0**, cũng đừng đồng nhất giá trị với chuỗi được in ra bởi `toString()`. Nếu muốn chuỗi không dùng ký pháp mũ, dùng `toPlainString()`; nếu muốn đúng hai chữ số thập phân, đặt scale có chủ đích trước khi xuất.

### 2.2. Precision của giá trị khác precision của cột

Với `new BigDecimal("0.0010")`, `precision()` trả về `2` vì phần biểu diễn `10` có hai chữ số có nghĩa, dù chuỗi nhìn thấy có bốn chữ số ở sau dấu phẩy.

Khi cột được khai báo `DECIMAL(19, 4)`, `19` là **giới hạn tổng số chữ số** trong kiểu SQL, không có nghĩa mọi giá trị Java lưu vào cột phải có `BigDecimal.precision() == 19`.

Tách bạch:

- `value.precision()`: độ chính xác của **một giá trị đang có**.
- `MathContext.precision`: giới hạn số chữ số có nghĩa mà phép tính được phép trả về.
- SQL `DECIMAL(p, s)` hoặc `@Column(precision=p, scale=s)`: đặc tính **cột dữ liệu** được yêu cầu ánh xạ.

Đây là ba mục đích khác nhau dù sử dụng cùng từ *precision*.

## 3. SQL DECIMAL(p, s) và NUMERIC(p, s) nghĩa là gì?

Theo cách dùng thông thường của SQL:

- `p` (*precision*) = tổng số chữ số trong giá trị lưu trữ.
- `s` (*scale*) = số chữ số ở bên phải dấu thập phân.
- Với `0 <= s <= p`, tối đa `p - s` chữ số ở phần nguyên.

Ví dụ:

```sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    unit_price DECIMAL(19, 4) NOT NULL,
    currency_code CHAR(3) NOT NULL
);
```

Cột `unit_price DECIMAL(19, 4)` theo quy tắc phổ biến của SQL có:

```text
Tổng số chữ số:           19
Số chữ số phần thập phân:  4
Số chữ số phần nguyên:    15

Giới hạn dương lớn nhất theo cấu hình:
999999999999999.9999
```

Một vài ví dụ lựa chọn cột:

| Định nghĩa | Chữ số phần nguyên | Chữ số phần lẻ | Tình huống minh họa |
| --- | ---: | ---: | --- |
| `DECIMAL(10, 2)` | 8 | 2 | Giá bán với mức tiền không quá lớn |
| `DECIMAL(19, 2)` | 17 | 2 | Số tiền có phạm vi lớn, lưu đến đơn vị phần trăm |
| `DECIMAL(19, 4)` | 15 | 4 | Đơn giá cần bốn chữ số thập phân |
| `DECIMAL(9, 6)` | 3 | 6 | Tỷ lệ, hệ số hoặc đơn giá tỷ lệ nhỏ, tùy nghiệp vụ |

**Không có một cặp `(p, s)` đúng cho mọi hệ thống.** `DECIMAL(19, 2)` có phạm vi giá trị rất lớn nhưng không thể lưu chính xác `0.0001`; `DECIMAL(19, 4)` chấp nhận phần lẻ chi tiết hơn nhưng giảm số chữ số phần nguyên.

Một số DBMS có hành vi riêng. Ví dụ PostgreSQL hỗ trợ `NUMERIC` không khai báo độ dài và thậm chí cho phép scale âm hoặc lớn hơn precision trong những phiên bản hiện đại. Để tăng tính portable, hãy ưu tiên `0 <= scale <= precision`, đồng thời tra **tài liệu DBMS đang sử dụng**.

### 3.1. Điều gì xảy ra khi ghi nhiều chữ số phần lẻ hơn cột?

Giả sử:

```sql
amount NUMERIC(8, 2)
```

và ứng dụng gửi giá trị `123.456`. Tùy DBMS và cấu hình, database có thể **làm tròn**, **cắt**, hoặc **báo lỗi**; PostgreSQL `numeric(8,2)` sẽ ép scale bằng cách làm tròn số thập phân trước khi kiểm tra phần nguyên có vừa giới hạn hay không.

Do đó, **không phó mặc cho database quyết định chính sách làm tròn tiền**. Thực hiện quy tắc làm tròn tại một ranh giới nghiệp vụ xác định trước khi persist và kiểm tra dữ liệu đầu vào. Khi cần ghi thất bại nếu có phần lẻ không hợp lệ, có thể dùng `RoundingMode.UNNECESSARY` để phát hiện thay vì tự động làm tròn.

### 3.2. Có thể overflow ngay sau khi làm tròn

Với `DECIMAL(5, 2)`, phần nguyên chỉ có ba chữ số. Giá trị `999.999` sau khi làm tròn về hai chữ số có thể thành `1000.00`, **vượt giới hạn**, dẫn tới lỗi lưu dữ liệu. Hãy xem xét cả phạm vi giá trị, số lượng phép tính cộng dồn và khả năng tăng chữ số khi làm tròn.

### 3.3. Đừng nhầm NUMERIC/DECIMAL với FLOAT/DOUBLE

Kiểu `DECIMAL`/`NUMERIC` là kiểu số **thập phân chính xác** ở mức SQL (trong giới hạn precision/scale); `REAL`, `FLOAT`, `DOUBLE PRECISION` thường là các kiểu xấp xỉ nhị phân. Một cột `DOUBLE` sẽ không trở thành chính xác chỉ vì thuộc tính Java được khai báo `BigDecimal`.

## 4. Hibernate ánh xạ BigDecimal như thế nào?

Hibernate ORM ánh xạ `java.math.BigDecimal` mặc định sang JDBC **`NUMERIC`**, rồi sử dụng dialect/database để quyết định DDL và cách giao tiếp JDBC phù hợp. Jakarta Persistence hỗ trợ `BigDecimal` làm kiểu thuộc tính entity cơ bản.

Ví dụ entity có đơn giá và tổng tiền:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "invoice_line")
public class InvoiceLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "unit_price", precision = 19, scale = 4, nullable = false)
    private BigDecimal unitPrice;

    @Column(name = "line_total", precision = 19, scale = 2, nullable = false)
    private BigDecimal lineTotal;

    @Column(name = "currency_code", length = 3, nullable = false)
    private String currencyCode;

    protected InvoiceLine() {
        // Constructor không tham số cho Jakarta Persistence.
    }

    public InvoiceLine(BigDecimal unitPrice,
                       BigDecimal lineTotal,
                       String currencyCode) {
        this.unitPrice = unitPrice;
        this.lineTotal = lineTotal;
        this.currencyCode = currencyCode;
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public BigDecimal getLineTotal() {
        return lineTotal;
    }

    public String getCurrencyCode() {
        return currencyCode;
    }
}
```

Về ý nghĩa:

- `unitPrice` có thể lưu giá trị như `19.9950` khi đơn giá cần độ chi tiết cao hơn đơn vị thanh toán.
- `lineTotal` dùng scale 2 trong **ví dụ có đơn vị tiền nhỏ nhất bằng 0.01**; không mặc nhiên đúng với mọi loại tiền.
- `currencyCode` giúp tránh nhập nhằng giữa `100 USD` và `100 JPY`.
- Cột database thực sự phải tương ứng với metadata đã xác định.

Chỉ ghi annotation **không đảm bảo** schema hiện tại tự thay đổi. Trên hệ thống đã có dữ liệu, cần migration DDL rõ ràng (Flyway, Liquibase hoặc quy trình tương đương), đồng thời kiểm tra schema bằng Hibernate nếu có cấu hình phù hợp.

### 4.1. Chính xác `@Column(precision, scale)` làm gì?

```java
@Column(precision = 19, scale = 4)
private BigDecimal unitPrice;
```

`precision` và `scale` là **metadata mapping cho cột exact numeric**. Chúng ảnh hưởng tới DDL khi provider thực hiện schema generation và mô tả cấu trúc mong đợi. Chúng **không** đồng nghĩa với:

- `BigDecimal` tự được làm tròn về bốn chữ số ở mọi lần gọi setter.
- Thuộc tính Java không bao giờ chứa giá trị quá lớn.
- Hibernate sẽ kiểm tra đầy đủ mọi quy tắc tính tiền trước khi gửi SQL.
- Thao tác `flush()`/`commit()` tự áp dụng chính sách thuế/phí của doanh nghiệp.
- Database luôn từ chối thay vì làm tròn khi nhận giá trị không đúng scale.

Với Jakarta Persistence, nếu không khai báo `precision`/`scale`, mặc định `0` có nghĩa provider **tự suy ra**, không phải một cam kết phổ quát rằng cột sẽ là `DECIMAL(0,0)` hay tiền không có phần lẻ. Nên chỉ rõ hai thuộc tính cho các cột tiền cần schema portable.

### 4.2. Schema do ứng dụng quản lý và schema Hibernate kỳ vọng

Ví dụ migration SQL cho PostgreSQL:

```sql
CREATE TABLE invoice_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    unit_price NUMERIC(19, 4) NOT NULL,
    line_total NUMERIC(19, 2) NOT NULL,
    currency_code CHAR(3) NOT NULL,
    CONSTRAINT ck_invoice_line_price_nonnegative CHECK (unit_price >= 0),
    CONSTRAINT ck_invoice_line_total_nonnegative CHECK (line_total >= 0)
);
```

`CHECK` trên là **quy tắc giả định** cho hóa đơn bán hàng thông thường. Hoàn tiền, điều chỉnh giảm hoặc bút toán đảo có thể yêu cầu số tiền âm; khi đó cần mô hình biểu diễn phù hợp thay vì sao chép ràng buộc này cho tất cả bảng.

Tên kiểu, cú pháp `IDENTITY` và cách database xử lý trailing zero phụ thuộc dialect. Khi đặt `@Column(columnDefinition = "...")`, cần biết rằng chuỗi SQL do ứng dụng cung cấp thường kém portable hơn việc dùng `precision`/`scale` chuẩn.

## 5. Tạo BigDecimal đúng cách

### 5.1. Dùng String hoặc valueOf(long)

```java
BigDecimal price = new BigDecimal("19.99");
BigDecimal taxRate = new BigDecimal("0.075");
BigDecimal zero = BigDecimal.ZERO;

BigDecimal cents = BigDecimal.valueOf(1999, 2); // 19.99
BigDecimal whole = BigDecimal.valueOf(19L);      // 19
```

Chuỗi decimal từ API, file hoặc biểu mẫu nên được **validate rồi parse từ chuỗi**, thay vì chuyển qua `double`.

### 5.2. Tránh `new BigDecimal(double)`

```java
BigDecimal wrong = new BigDecimal(0.1);
BigDecimal right = new BigDecimal("0.1");

System.out.println(wrong.toPlainString());
// 0.1000000000000000055511151231257827021181583404541015625

System.out.println(right.toPlainString()); // 0.1
```

`new BigDecimal(0.1)` tạo giá trị chính xác của **xấp xỉ nhị phân đã có trong `double`**, không tái tạo ý định “một phần mười”.

Nếu nguồn đầu vào bắt buộc là `double`, `BigDecimal.valueOf(double)` sử dụng biểu diễn từ `Double.toString(double)` và thường cho chuỗi dễ dự đoán hơn constructor `BigDecimal(double)`. Tuy nhiên, **giá trị đã trải qua các phép tính `double` có thể đã mất thông tin**; `valueOf` không thể khôi phục độ chính xác đã mất. Với tiền, giữ dữ liệu ở dạng chuỗi hoặc số nguyên đơn vị nhỏ nhất từ đầu thường phù hợp hơn.

### 5.3. Dữ liệu đầu vào phải có chính sách dấu phân cách

```text
"1234.50"   → chuỗi số theo định dạng máy/API
"1.234,50"  → định dạng hiển thị theo một số Locale
"1,234.50"  → định dạng hiển thị theo Locale khác
```

Không đưa trực tiếp chuỗi có dấu phân cách hàng nghìn vào `new BigDecimal(...)`. Dùng parser định dạng địa phương đáng tin cậy và validate đầy đủ đầu vào, hoặc chuẩn hóa giao thức API thành chuỗi thập phân với dấu `.` không chứa dấu nhóm. **Trình bày tiền** và **lưu giá trị tiền** là hai công đoạn riêng.

## 6. Làm tròn với setScale và RoundingMode

`setScale(newScale, roundingMode)` đặt số chữ số thập phân theo quy tắc chỉ định:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal raw = new BigDecimal("12.345");

BigDecimal halfUp = raw.setScale(2, RoundingMode.HALF_UP);
BigDecimal halfEven = raw.setScale(2, RoundingMode.HALF_EVEN);
BigDecimal down = raw.setScale(2, RoundingMode.DOWN);

System.out.println(halfUp);   // 12.35
System.out.println(halfEven); // 12.34
System.out.println(down);     // 12.34
```

Ở `12.345`, vị trí giữ cuối cùng là `4`, chính giữa giữa `12.34` và `12.35`:

- `HALF_UP`: ở trường hợp đúng giữa, làm tròn ra xa 0.
- `HALF_EVEN`: ở trường hợp đúng giữa, chọn kết quả có chữ số cuối được giữ là **chẵn**.
- `DOWN`: bỏ các chữ số dư về phía 0, **không phải** luôn làm tròn xuống về âm vô cùng.
- `UNNECESSARY`: không cho phép mất chữ số; nếu phải làm tròn thì ném `ArithmeticException`.

Bảng minh họa với scale 2:

| Đầu vào | `HALF_UP` | `HALF_EVEN` | `DOWN` |
| --- | --- | --- | --- |
| `12.345` | `12.35` | `12.34` | `12.34` |
| `12.355` | `12.36` | `12.36` | `12.35` |
| `-12.345` | `-12.35` | `-12.34` | `-12.34` |
| `12.344` | `12.34` | `12.34` | `12.34` |

`HALF_EVEN` có thể giảm thiên lệch thống kê trong những phép làm tròn lặp lại trên dữ liệu phù hợp, nhưng **không tự động là chính sách hợp lệ cho mọi loại thuế, hóa đơn, thị trường hay hợp đồng**. Chọn rounding mode theo yêu cầu nghiệp vụ, pháp luật và tiêu chuẩn kế toán áp dụng; không tùy tiện đổi từ `HALF_UP` sang `HALF_EVEN` giữa hai môi trường.

### 6.1. Kiểm tra đầu vào chính xác mà không làm tròn

```java
BigDecimal amount = new BigDecimal("19.990");

BigDecimal normalized = amount.setScale(2, RoundingMode.UNNECESSARY);
// 19.99: chỉ bỏ chữ số 0, không thay đổi giá trị

BigDecimal invalid = new BigDecimal("19.999");
invalid.setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException: phải làm tròn nếu muốn giữ 2 chữ số
```

`UNNECESSARY` là lựa chọn tốt tại ranh giới mà **người nhập phải cung cấp đúng đơn vị tiền cho phép**, ví dụ API nhận số tiền thanh toán có đúng hai chữ số phần lẻ. Với phép nhân tỷ lệ thuế, giá trị trung gian có thể cần thêm chữ số; cần làm tròn ở bước nghiệp vụ đã quy định, thay vì từ chối tất cả phép tính có nhiều chữ số.

### 6.2. Không làm tròn quá sớm

Giả sử đơn giá `0.3333`, số lượng `3`:

```java
BigDecimal unitPrice = new BigDecimal("0.3333");
BigDecimal quantity = new BigDecimal("3");

BigDecimal total = unitPrice
    .multiply(quantity)         // 0.9999
    .setScale(2, RoundingMode.HALF_UP); // 1.00
```

Nếu làm tròn đơn giá về hai chữ số trước rồi nhân:

```java
BigDecimal premature = unitPrice
    .setScale(2, RoundingMode.HALF_UP) // 0.33
    .multiply(quantity);              // 0.99
```

Kết quả lệch `0.01`. Cả hai là chuỗi phép tính có quy tắc nhưng chỉ **một quy tắc** có thể đúng theo hợp đồng. Cần xác định rõ làm tròn ở **đơn giá, từng dòng, từng loại thuế hay tổng đơn**; không thay đổi thứ tự trong nhiều service.

## 7. MathContext: precision của phép tính khác scale

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("12345.6789");

BigDecimal roundedSignificant = amount.round(
    new MathContext(4, RoundingMode.HALF_UP)
); // Kết quả có 4 chữ số có nghĩa: 1.235E+4

BigDecimal roundedFractional = amount.setScale(
    4, RoundingMode.HALF_UP
); // 12345.6789
```

`MathContext(4)` giới hạn **4 chữ số có nghĩa của toàn bộ số**; `setScale(4)` giữ **4 chữ số bên phải dấu thập phân**. Đây không phải hai cách viết tương đương.

Đối với nhiều phép tính tiền phổ thông, có thể thực hiện phép cộng/nhân chính xác trước rồi `setScale()` tại điểm quy định. Với chuỗi tính toán rất lớn hoặc phép chia, `MathContext` có thể cần thiết để giới hạn precision; phải hiểu rõ ảnh hưởng của việc làm tròn trung gian.

**`BigDecimal` không vô hạn về tài nguyên**: dù có precision tùy ý về mặt API, kết quả rất lớn vẫn tiêu tốn bộ nhớ và CPU, và `scale` nằm trong giới hạn kiểu `int`. Đặt giới hạn hợp lý cho dữ liệu đầu vào và tính toán.

## 8. Phép chia: chọn scale và rounding mode rõ ràng

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// one.divide(three) sẽ ném ArithmeticException:
// 1 / 3 không có biểu diễn thập phân hữu hạn.

BigDecimal quotient = one.divide(
    three,
    4,
    RoundingMode.HALF_UP
);
System.out.println(quotient); // 0.3333
```

Có hai kiểu nhu cầu:

1. **Kết quả chính xác hữu hạn**, ví dụ `10 / 4 = 2.5`: `divide()` không truyền rounding mode có thể hoạt động.
2. **Kết quả cần độ chính xác hữu hạn do nghiệp vụ định nghĩa**, như chia tổng tiền, tính giá trung bình hoặc tỷ giá: chỉ rõ scale và rounding mode.

```java
BigDecimal total = new BigDecimal("10.00");
BigDecimal people = BigDecimal.valueOf(3);

BigDecimal provisional = total.divide(
    people,
    2,
    RoundingMode.DOWN
); // 3.33
```

Ba phần `3.33` chỉ cộng lại thành `9.99`. Phần dư `0.01` **không được tự động biến mất**. Một chính sách phân bổ có thể đặt một phần thành `3.34`, hai phần thành `3.33`; điều kiện là tổng phân bổ đúng bằng `10.00`.

Với hóa đơn hoặc ledger, có thể giải bài toán phân bổ bằng **đơn vị nhỏ nhất dạng số nguyên** rồi chia lấy phần nguyên và phân bổ phần dư theo thứ tự xác định trước. Cách làm này đặc biệt hữu ích khi nhiều dòng phải khớp tổng chính xác.

## 9. So sánh BigDecimal: equals khác compareTo

Đây là lỗi phổ biến ngay cả khi đã chuyển khỏi `double`:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.equals(y));                 // false
System.out.println(x.compareTo(y) == 0);         // true
System.out.println(x.scale());                   // 1
System.out.println(y.scale());                   // 2
```

- `equals()` kiểm tra **giá trị số và biểu diễn scale**.
- `compareTo()` so sánh **giá trị số học** và coi `2.0` và `2.00` là bằng nhau.

Nếu muốn biết hai khoản tiền bằng nhau về lượng, dùng `compareTo() == 0` **và xác nhận cùng mã tiền tệ**. Không dùng `equals()` trực tiếp để kiểm tra “số tiền có bằng nhau” nếu scale chưa được chuẩn hóa.

```java
BigDecimal requested = new BigDecimal("100.0");
BigDecimal available = new BigDecimal("100.00");

boolean sameAmount = requested.compareTo(available) == 0; // true
boolean enough = available.compareTo(requested) >= 0;      // true
```

Khi dùng `BigDecimal` làm khóa của `HashMap` hoặc phần tử trong `HashSet`, `equals()` và `hashCode()` vẫn phân biệt `2.0` với `2.00`; `TreeSet` theo natural ordering dùng `compareTo()` lại coi chúng tương đương. Vì vậy, nếu cần dùng amount như identity/key, hãy xác định quy tắc chuẩn hóa scale và tiền tệ trước.

### 9.1. `stripTrailingZeros()` không phải luôn là cách chuẩn hóa tiền

```java
new BigDecimal("1000.00").stripTrailingZeros().toString();
// Có thể là "1E+3", với scale âm.
```

Nếu nghiệp vụ quy định hai chữ số thập phân thì:

```java
BigDecimal canonical = new BigDecimal("1000.00")
    .setScale(2, RoundingMode.UNNECESSARY); // 1000.00
```

Cách này giữ một **định dạng scale cố định** khi cần, thay vì xóa mọi số 0 ở cuối.

## 10. Đơn vị tiền tệ: BigDecimal chưa đủ để biểu diễn Money

Giá trị `100.00` **không cho biết nó là USD, EUR, VND hay JPY**. Một đối tượng tiền nên gồm ít nhất:

```text
Money = (amount: BigDecimal, currency: currencyCode)
```

Một số đơn vị tiền có số chữ số phần lẻ mặc định khác nhau: USD và EUR thường có 2, JPY thường có 0, một số loại có 3. Java cung cấp:

```java
import java.util.Currency;

int usdScale = Currency.getInstance("USD").getDefaultFractionDigits(); // 2
int jpyScale = Currency.getInstance("JPY").getDefaultFractionDigits(); // 0
int kwdScale = Currency.getInstance("KWD").getDefaultFractionDigits(); // 3
```

Với một số đơn vị/pseudo-currency, API có thể trả `-1` khi không có số chữ số phần lẻ mặc định. **Metadata ISO 4217 không thay thế quy tắc nghiệp vụ**: giá bán hàng hóa, ngoại hối, tỷ giá, crypto hoặc định giá nội bộ có thể dùng precision/scale riêng; chính sách ngân hàng và hệ thống thanh toán cũng có thể có giới hạn khác nhau.

### 10.1. Value object Money đơn giản

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

public final class Money {
    private final BigDecimal amount;
    private final Currency currency;

    private Money(BigDecimal amount, Currency currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public static Money of(BigDecimal input, Currency currency) {
        Objects.requireNonNull(input, "amount");
        Objects.requireNonNull(currency, "currency");

        int scale = currency.getDefaultFractionDigits();
        if (scale < 0) {
            throw new IllegalArgumentException(
                "Currency has no default fraction digits: " + currency
            );
        }

        BigDecimal normalized = input.setScale(
            scale, RoundingMode.UNNECESSARY
        );
        return new Money(normalized, currency);
    }

    public Money add(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }

    public BigDecimal amount() {
        return amount;
    }

    public Currency currency() {
        return currency;
    }

    @Override
    public boolean equals(Object object) {
        if (this == object) return true;
        if (!(object instanceof Money other)) return false;
        return amount.equals(other.amount)
            && currency.equals(other.currency);
    }

    @Override
    public int hashCode() {
        return Objects.hash(amount, currency);
    }
}
```

Đây là **value object thuần Java**, chưa phải entity/embeddable. `Money.of()` cố tình dùng `UNNECESSARY`: nó **từ chối số tiền có phần lẻ không khớp đơn vị mặc định** thay vì tự ý tính phí/làm tròn. Chính sách này hữu ích cho một số luồng thanh toán, nhưng **không dùng nguyên xi** cho đơn giá có 4–6 chữ số thập phân hoặc tỷ giá.

Để hỗ trợ các trường hợp khác, nên mô hình hóa riêng `UnitPrice`, `ExchangeRate`, `TaxRate` hoặc quy tắc rounding. Không ép mọi số decimal trong ứng dụng vào cùng scale của đồng tiền.

## 11. Mapping Money bằng Jakarta Persistence Embeddable

Khi cần lưu `amount` và `currency_code` cùng một entity, `@Embeddable` là lựa chọn để nhóm hai cột vào một thuộc tính đối tượng:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.math.BigDecimal;

@Embeddable
public class MonetaryValue {

    @Column(name = "amount", precision = 19, scale = 2, nullable = false)
    private BigDecimal amount;

    @Column(name = "currency_code", length = 3, nullable = false)
    private String currencyCode;

    protected MonetaryValue() {
        // JPA constructor
    }

    public MonetaryValue(BigDecimal amount, String currencyCode) {
        this.amount = amount;
        this.currencyCode = currencyCode;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrencyCode() {
        return currencyCode;
    }
}
```

Dùng trong entity:

```java
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Payment {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    private MonetaryValue paid;

    protected Payment() {
    }

    public Payment(MonetaryValue paid) {
        this.paid = paid;
    }
}
```

Đây là bản tối giản để thấy cách ánh xạ; ứng dụng sản xuất cần thêm **quy tắc kiểm tra currency/scale**, constructor/factory hợp lệ, bất biến cần bảo vệ và khả năng tái sử dụng mapping. `@Embeddable` là một object được ánh xạ cùng bảng với entity sở hữu, không cần bảng độc lập.

### 11.1. Khi có hai Money trong cùng một entity

Nếu entity lưu `subtotal` và `total`, tên cột `amount`/`currency_code` sẽ trùng nếu nhúng hai lần. Dùng `@AttributeOverride` để chỉ rõ từng cột:

```java
import jakarta.persistence.AttributeOverride;
import jakarta.persistence.AttributeOverrides;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;

// Bên trong một @Entity...
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "amount",
        column = @Column(
            name = "subtotal_amount",
            precision = 19,
            scale = 2,
            nullable = false
        )
    ),
    @AttributeOverride(
        name = "currencyCode",
        column = @Column(name = "subtotal_currency", length = 3, nullable = false)
    )
})
private MonetaryValue subtotal;

@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "amount",
        column = @Column(
            name = "total_amount",
            precision = 19,
            scale = 2,
            nullable = false
        )
    ),
    @AttributeOverride(
        name = "currencyCode",
        column = @Column(name = "total_currency", length = 3, nullable = false)
    )
})
private MonetaryValue total;
```

Lưu ý annotation mapping không tự đảm bảo `subtotal.currencyCode` và `total.currencyCode` phải giống nhau. Nếu nghiệp vụ yêu cầu cùng loại tiền, hãy kiểm tra ở domain service hoặc thiết kế model phù hợp.

## 12. Validation: kiểm tra trước khi dữ liệu đến database

Jakarta Bean Validation (khi được thêm dependency và tích hợp vào môi trường chạy) có annotation giúp diễn đạt ràng buộc:

```java
import jakarta.persistence.Column;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;

// Trích từ entity/embeddable:
@NotNull
@DecimalMin("0.00")
@Digits(integer = 17, fraction = 2)
@Column(name = "amount", precision = 19, scale = 2, nullable = false)
private BigDecimal amount;
```

Ý nghĩa:

| Ràng buộc | Mục đích |
| --- | --- |
| `@NotNull` | Từ chối giá trị null ở lớp validation |
| `@DecimalMin("0.00")` | Yêu cầu số tiền không âm trong ví dụ |
| `@Digits(integer=17, fraction=2)` | Không quá 17 chữ số nguyên và 2 chữ số thập phân |
| `@Column(precision=19, scale=2)` | Mô tả độ chính xác của cột SQL |
| `CHECK` và kiểu cột trong database | Bảo vệ dữ liệu ở mức database, kể cả ngoài ứng dụng |

`@Digits` là constraint validation **khác** với metadata SQL của `@Column`. Một dự án chỉ thêm annotation nhưng **không cài đặt/kích hoạt Bean Validation** sẽ không tự có kết quả kiểm tra mong đợi. Validation cũng không thay thế phép xử lý rounding của nghiệp vụ.

Ví dụ khi dùng `@Digits(fraction=2)`, `new BigDecimal("10.000")` có scale 3 nên có thể không hợp lệ ở tầng validation dù về mặt số học bằng `10.00`. Nếu muốn chấp nhận các chữ số 0 dư ở cuối, chuẩn hóa có kiểm soát trước khi kiểm tra theo chính sách của hệ thống.

Không nên phụ thuộc duy nhất vào validation ở service: những thao tác SQL trực tiếp, import dữ liệu và ứng dụng khác có thể đi vòng qua nó. Hãy kết hợp **validation ứng dụng + constraint database + migration có kiểm soát**.

## 13. Tính thuế, phí, chiết khấu và tiền phải trả

Một quy trình tính tiền điển hình cần ít nhất bốn quyết định:

1. **Scale đầu vào** của số lượng và đơn giá là bao nhiêu?
2. **Scale trung gian** cho thuế suất, tỷ giá, hệ số phân bổ là bao nhiêu?
3. **Mốc làm tròn** là từng dòng hay tổng hóa đơn?
4. **Rounding mode** nào được pháp luật/hợp đồng/quy tắc doanh nghiệp áp dụng?

Ví dụ một dòng hàng USD:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal unitPrice = new BigDecimal("19.9950");
BigDecimal quantity = new BigDecimal("3");
BigDecimal taxRate = new BigDecimal("0.075"); // 7.5%

BigDecimal subtotalExact = unitPrice.multiply(quantity);
// 59.9850

BigDecimal taxExact = subtotalExact.multiply(taxRate);
// 4.4988750

BigDecimal subtotal = subtotalExact.setScale(2, RoundingMode.HALF_UP);
// 59.99

BigDecimal tax = taxExact.setScale(2, RoundingMode.HALF_UP);
// 4.50

BigDecimal total = subtotal.add(tax);
// 64.49
```

Ví dụ này **giả định** mỗi thành phần `subtotal`, `tax` được làm tròn riêng về hai chữ số tại bước xác định; nếu hợp đồng quy định thuế được tính trên subtotal đã làm tròn, phép tính có thể khác. Quan trọng là chính sách được ghi thành công thức nhất quán.

Một ví dụ về thứ tự phép tính:

```text
Đơn giá gốc:       19.9950
Số lượng:                3
Subtotal chính xác: 59.9850

Làm tròn đơn giá trước: 20.00 × 3 = 60.00
Làm tròn subtotal sau: 59.9850 → 59.99
Chênh lệch:                       0.01
```

Cùng đầu vào nhưng thứ tự rounding khác nhau tạo kết quả khác. Nếu không có quy tắc được thống nhất, hai microservice cùng dùng `BigDecimal` vẫn có thể lệch số tiền.

### 13.1. Chiết khấu

Giả sử giá trước chiết khấu là `199.99`, giảm `12.5%`:

```java
BigDecimal gross = new BigDecimal("199.99");
BigDecimal discountRate = new BigDecimal("0.125");

BigDecimal discount = gross
    .multiply(discountRate)
    .setScale(2, RoundingMode.HALF_UP); // 25.00

BigDecimal net = gross.subtract(discount); // 174.99
```

Đây là một chính sách mẫu. Nếu phân bổ chiết khấu cho nhiều dòng hàng, phải bảo đảm **tổng mức giảm đã phân bổ bằng tổng giảm của đơn hàng**, xử lý phần dư theo nguyên tắc xác định trước.

### 13.2. Tỷ giá và chuyển đổi tiền tệ

Không được cộng trực tiếp hai đồng tiền khác nhau. Khi chuyển đổi:

```java
BigDecimal usd = new BigDecimal("100.00");
BigDecimal vndPerUsd = new BigDecimal("25123.4567");

BigDecimal vndExact = usd.multiply(vndPerUsd);
BigDecimal vnd = vndExact.setScale(0, RoundingMode.HALF_UP);
```

Cần ghi rõ **chiều tỷ giá** (`VND per USD`, không phải `USD per VND`), thời điểm áp dụng, nguồn tỷ giá, độ chính xác trung gian, cách rounding và loại tiền nhận. `BigDecimal` không bảo vệ trước lỗi sử dụng tỷ giá ngược chiều hoặc nhầm đơn vị.

## 14. JDBC và Hibernate: tránh chuyển qua double trong đường đi dữ liệu

Một đường đi đúng điển hình:

```text
API decimal string
    ↓ parse BigDecimal từ chuỗi
domain amount/rate với quy tắc scale
    ↓ BigDecimal
Hibernate/JPA thuộc tính BigDecimal
    ↓ JDBC NUMERIC / DECIMAL
CSDL DECIMAL(p,s) / NUMERIC(p,s)
    ↓ JDBC getBigDecimal()
entity/DTO BigDecimal
    ↓ serialize theo giao ước nhất quán
API decimal string hoặc JSON number có ràng buộc client
```

Khi viết JDBC trực tiếp:

```java
String sql = "INSERT INTO payment(amount) VALUES (?)";

try (java.sql.PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("123.45"));
    ps.executeUpdate();
}
```

Khi đọc:

```java
BigDecimal amount = resultSet.getBigDecimal("amount");
```

Không đổi `BigDecimal` thành `double` chỉ để bind parameter, ghi log, tạo DTO hay gọi repository. Một thao tác như `amount.doubleValue()` có thể mất thông tin nếu giá trị có nhiều chữ số hoặc không biểu diễn nhị phân hữu hạn.

### 14.1. Khi lấy dữ liệu từ SQL aggregate

Truy vấn như:

```sql
SELECT SUM(amount) FROM payment WHERE currency_code = 'USD';
```

về ý tưởng vẫn là tổng số thập phân; **kiểu trả về, precision và scale của biểu thức tổng hợp** có thể thay đổi theo DBMS, JDBC driver và dialect. Ví dụ Hibernate/JPA có thể ánh xạ kết quả `SUM` của thuộc tính `BigDecimal` về `BigDecimal`, nhưng vẫn cần kiểm tra cách database xử lý null (không có hàng), overflow và giới hạn precision của phép tổng hợp.

Một tổng không nên được giả định có mã tiền tệ nhất định nếu truy vấn vô tình gộp nhiều đồng tiền. Có thể **GROUP BY `currency_code`**, hoặc lọc duy nhất một currency và ghi currency cùng kết quả.

## 15. JSON và giao tiếp liên dịch vụ: tránh mất số ở client

Java giữ `BigDecimal` chính xác nhưng một client JavaScript thường đọc JSON number thành kiểu `Number` theo IEEE 754 binary floating point. Với số tiền rất lớn hoặc có nhiều chữ số thập phân, việc parse có thể làm mất chữ số.

Hai cách thiết kế contract phổ biến:

### Cách A — decimal string

```json
{
  "amount": "12345678901234567890.12",
  "currency": "USD"
}
```

Dịch vụ Java đọc `"amount"` và tạo `BigDecimal` từ chuỗi. Client cần thư viện decimal hoặc xử lý bằng chuỗi/đơn vị nguyên nếu muốn tính toán chính xác; không tự parse thành `Number` rồi mong giữ nguyên mọi chữ số.

### Cách B — số nguyên đơn vị nhỏ nhất

```json
{
  "minorUnits": "12345",
  "currency": "USD",
  "scale": 2
}
```

`minorUnits = 12345` biểu diễn `123.45 USD` khi scale 2. Trong môi trường JavaScript, dùng chuỗi hoặc `BigInt` cho số nguyên lớn vượt phạm vi số nguyên an toàn. Cách này phù hợp với nhiều hệ thanh toán nhưng chỉ khi **scale đã được xác định hợp lệ**; không dùng mặc định scale 2 cho mọi currency.

Với bất kỳ contract nào, phân biệt:

- **Giá trị nghiệp vụ:** số tiền phải thanh toán.
- **Định dạng truyền tải:** JSON string, number hoặc minor units.
- **Định dạng hiển thị:** dấu phân cách, ký hiệu tiền và Locale.
- **Đơn vị giao dịch:** currency code và quy tắc rounding.

Việc lưu chính xác trong database không đảm bảo dữ liệu vẫn chính xác nếu một gateway hoặc frontend chuyển về `double`.

## 16. Khi nào dùng số nguyên cents thay cho BigDecimal?

Một thiết kế khác là lưu `long` số **minor units**:

```java
long cents = 1999L; // 19.99 USD
```

Ưu điểm:

- Phép cộng/trừ số nguyên không có sai số phân số nhị phân.
- Phù hợp những luồng chỉ nhận số tiền đúng đơn vị nhỏ nhất, như `cents`.
- Dễ làm phân bổ phần dư bằng phép chia số nguyên.

Đổi lại:

- Mỗi currency có số chữ số phần lẻ khác nhau; phải giữ currency và scale.
- `long` có giới hạn `-2^63` đến `2^63-1`; cần kiểm soát overflow, dùng `Math.addExact()` và `Math.multiplyExact()` khi thích hợp.
- Đơn giá hoặc tỷ giá cần nhiều chữ số hơn minor units có thể không biểu diễn được nếu chỉ dùng `long`.
- Đổi loại tiền hoặc thay đơn vị quy ước đòi hỏi logic chuyển đổi rõ ràng.

`BigDecimal` và minor-unit integer **đều có thể đúng** khi chính sách scale/rounding được xác định. Chọn một representation phù hợp với nghiệp vụ, giữ nhất quán qua database, API và event; tránh chuyển đổi qua lại tùy tiện.

## 17. Các lỗi thường gặp trong Hibernate và dữ liệu tiền

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `0.1 + 0.2` thành `0.30000000000000004` | Dùng floating-point nhị phân | Dùng `BigDecimal` tạo từ String, tránh đi qua `double` |
| `new BigDecimal(0.1)` có rất nhiều chữ số | Constructor nhận biểu diễn `double` chính xác | `new BigDecimal("0.1")` hoặc `valueOf` khi không thể tránh `double` |
| `ArithmeticException` khi `divide()` | Thương có phần thập phân vô hạn, không chỉ định rounding | `divide(divisor, scale, roundingMode)` |
| `ArithmeticException` khi `setScale(..., UNNECESSARY)` | Giá trị cần bị làm tròn để phù hợp scale | Từ chối đầu vào hoặc dùng chính sách rounding được phê duyệt |
| `2.0.equals(2.00)` là false | `equals()` xét cả scale | So sánh amount bằng `compareTo()` hoặc chuẩn hóa scale |
| Lưu `12.345` rồi đọc về `12.35` | Cột DB hoặc tầng nào đó ép scale 2 | Kiểm tra DDL, input policy, rounding và JDBC |
| Insert thất bại vì numeric overflow | Tổng chữ số vượt `DECIMAL(p,s)`, có thể sau khi rounding | Nâng `precision` có migration; đặt giới hạn đúng nghiệp vụ |
| Unit price bị khác total một vài cent | Làm tròn trước/sau phép nhân hoặc chia khác nhau | Định nghĩa mốc làm tròn duy nhất, kiểm tra phân bổ phần dư |
| Tổng nhiều dòng không bằng tổng hóa đơn | Mỗi dòng đã được làm tròn khác quy tắc tính tổng | Chọn per-line/whole-invoice rounding; phân bổ phần dư |
| Backend đúng nhưng frontend mất chữ số | JSON number bị parse thành JS `Number` | Contract decimal string hoặc minor units an toàn |
| Schema production khác `@Column` | Migration chưa chạy hoặc DDL được quản lý độc lập | Đối chiếu migration/schema, không dựa vào annotation |
| Hai khoản 100 cộng vào nhau dù khác currency | Không lưu/kiểm tra currency | Value object Money; chặn cộng khác currency |

### 17.1. Rounding policy thay đổi là thay đổi nghiệp vụ

Thay `HALF_UP` thành `HALF_EVEN`, đổi scale 2 thành 4 hoặc di chuyển bước rounding có thể thay đổi kết quả thanh toán, doanh thu, thuế và đối soát. Những thay đổi này cần được xem như **thay đổi quy tắc tính tiền và dữ liệu**, có kiểm tra hồi quy và kế hoạch xử lý khoản đã ghi nhận; không nên đưa vào như một sửa đổi formatting thông thường.

### 17.2. Thay đổi precision/scale là migration dữ liệu

Giả sử production đang dùng `NUMERIC(12,2)` và muốn đổi sang `NUMERIC(19,4)`:

- Kiểm tra tất cả nơi xử lý số tiền: Java entity, validation, SQL, report, views, integration/ETL và API.
- Lập migration theo DBMS; mở rộng precision/scale thường ít rủi ro hơn thu hẹp, nhưng vẫn cần đánh giá khóa bảng, index và hệ quả với dữ liệu thật.
- Với thay đổi thu hẹp `NUMERIC(19,4)` về `(19,2)`, phải xác định rõ dữ liệu đang có phần lẻ thứ ba/thứ tư được làm tròn, từ chối hay điều chỉnh; **không để migration ngầm mất giá trị**.
- Các snapshot/sự kiện cũ có thể đang chứa amount với scale khác; định nghĩa chiến lược tương thích trước khi triển khai.

Việc Hibernate có `@Column(precision, scale)` đúng **không đảm bảo** mọi migration và tất cả hệ khác đã theo cùng hợp đồng.

## 18. Một thiết kế quy trình xử lý tiền rõ ràng

Ví dụ hệ thống thương mại lưu đơn giá bốn chữ số thập phân, nhưng tổng thanh toán USD hai chữ số:

```text
1. Nhận dữ liệu nguồn
   unitPrice: "19.9950" USD
   quantity: "3"

2. Parse và validate
   BigDecimal("19.9950")
   BigDecimal("3")
   Currency = USD
   quantity phải dương; unitPrice phải hợp lệ

3. Tính tiền chính xác
   subtotalExact = unitPrice × quantity
                 = 59.9850

4. Áp dụng chính sách làm tròn đã định nghĩa
   subtotalPayable = 59.99 (HALF_UP ở cấp dòng)

5. Áp dụng thuế, phí, chiết khấu theo quy tắc cụ thể
   ghi rõ base, rate, mốc rounding và thứ tự

6. Persist
   unitPrice     NUMERIC(19,4)
   lineTotal     NUMERIC(19,2)
   currencyCode  CHAR(3)

7. Kiểm tra invariant
   tổng các dòng + thuế/phí - giảm giá = tổng phải trả
   cùng đồng tiền; tổng phân bổ không mất phần dư

8. Trả kết quả
   amount dạng decimal string hoặc minor units + currency
```

Trong cùng hệ thống, có thể dùng ba kiểu decimal **khác mục đích**:

| Giá trị | Ví dụ | Scale có thể cân nhắc |
| --- | --- | --- |
| Đơn giá | Giá trên từng sản phẩm / mỗi kWh | 4 hoặc nhiều hơn tùy nghiệp vụ |
| Thuế suất/tỷ giá | Hệ số nhân | 4–10 hoặc theo hợp đồng/nguồn |
| Số tiền thanh toán | Khoản tiền khách thực trả | Theo minor unit và hệ thống thanh toán |

Đây là **ví dụ quy hoạch dữ liệu**, không phải quy định chung. Nếu dịch vụ thanh toán yêu cầu số nguyên minor units hoặc pháp luật quy định công thức thuế cụ thể, ưu tiên yêu cầu thực tế đó.

## 19. Câu hỏi thực hành

**Câu 1.** Có thể dùng `@Column(precision = 19, scale = 2)` để bảo đảm mọi phép nhân `BigDecimal` luôn làm tròn hai chữ số không?

**Trả lời:** Không. Annotation mô tả metadata cột database; phép nhân Java giữ kết quả theo quy tắc của `BigDecimal`. Nếu cần làm tròn về hai chữ số, chọn mốc phù hợp và gọi `setScale(2, roundingMode)` trong logic nghiệp vụ.

**Câu 2.** `new BigDecimal("9.99").multiply(new BigDecimal("3"))` có phải trả `29.97` chính xác không?

**Trả lời:** Có. Đây là phép nhân của những số decimal hữu hạn được tạo từ chuỗi, kết quả `29.97` có thể biểu diễn chính xác. Nếu có `MathContext` giới hạn precision, kết quả có thể bị làm tròn theo context.

**Câu 3.** `DECIMAL(8,3)` cho tối đa bao nhiêu chữ số phần nguyên?

**Trả lời:** Năm chữ số (`8 - 3 = 5`) theo quy tắc SQL thông thường. Giá trị `99999.999` vừa, còn `100000.000` vượt giới hạn phần nguyên.

**Câu 4.** Vì sao `new BigDecimal("1.00").equals(new BigDecimal("1.0"))` là `false`?

**Trả lời:** Hai giá trị có scale khác nhau (`2` và `1`). Dùng `compareTo(...) == 0` để so giá trị số học, cùng với kiểm tra đồng tiền nếu là Money.

**Câu 5.** Dự án nhận số tiền JSON `12345678901234567890.12`, nhưng frontend xử lý bằng JavaScript Number. Hibernate có đảm bảo dữ liệu cuối cùng chính xác không?

**Trả lời:** Không. Chữ số có thể mất trước khi tới Hibernate. Thiết kế contract bằng decimal string hoặc minor units truyền an toàn qua JavaScript, rồi parse thành `BigDecimal` trong backend.

**Câu 6.** Giá trị `10.005` cần lưu vào `DECIMAL(19,2)`. Nên áp dụng `HALF_UP` hay `HALF_EVEN`?

**Trả lời:** Không thể quyết định chỉ từ kiểu dữ liệu. Phải biết quy tắc làm tròn của giao dịch, hợp đồng và quy định liên quan. Sau khi chốt chính sách, áp dụng nhất quán trước khi lưu.

**Câu 7.** Nên dùng `long` cents hay `BigDecimal`?

**Trả lời:** Dùng `long` minor units nếu toàn bộ luồng làm việc với số nguyên đơn vị nhỏ nhất, phạm vi không vượt `long` và currency/scale rõ ràng. Dùng `BigDecimal` cho đơn giá, tỷ lệ hoặc số tiền cần biểu diễn decimal với độ chi tiết khác nhau. Hai cách đều cần validation và quy tắc làm tròn.

## 20. Tài liệu tham khảo

Các tài liệu chuẩn và hướng dẫn nhà cung cấp hữu ích khi kiểm tra chính xác API/DBMS:

- [Java SE BigDecimal Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): unscaled value, scale, precision, phép toán, `equals()`/`compareTo()`, `MathContext`, làm tròn và chia.
- [Java SE RoundingMode Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): ý nghĩa `HALF_UP`, `HALF_EVEN`, `DOWN`, `UNNECESSARY` và các mode khác.
- [Java SE Currency Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Currency.html): mã tiền ISO 4217 và số chữ số phần lẻ mặc định.
- [Jakarta Persistence 3.2 `@Column`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/Column.html): metadata `precision`, `scale` của cột exact numeric; các thuộc tính mặc định.
- [Hibernate ORM User Guide — Mapping basic types](https://docs.hibernate.org/stable/orm/userguide/html_single/): mapping `BigDecimal` sang JDBC `NUMERIC` và hành vi type/dialect.
- [PostgreSQL — Numeric types](https://www.postgresql.org/docs/current/datatype-numeric.html): `NUMERIC(p,s)`, rounding khi lưu, giới hạn precision và khác biệt với floating-point.
- [PostgreSQL — Monetary types](https://www.postgresql.org/docs/current/datatype-money.html): lưu ý về kiểu `money` đặc thù và khác biệt với `numeric`.

## Kết luận

Độ chính xác tiền tệ cần được bảo vệ **trên toàn bộ đường đi của dữ liệu**. Khởi tạo `BigDecimal` từ decimal string hoặc đơn vị nguyên; phân biệt precision của giá trị, `MathContext` và cột SQL; dùng `@Column(precision, scale)` cùng schema `DECIMAL`/`NUMERIC` phù hợp; chọn mốc và kiểu làm tròn theo nghiệp vụ; luôn lưu **mã tiền tệ**; tránh chuyển qua `double` khi bind JDBC, serialize API hoặc tính toán. Chỉ khi **biểu diễn, công thức, rounding, schema và contract** nhất quán, ứng dụng Hibernate mới giữ được số tiền đúng từ đầu vào đến database và đầu ra.
