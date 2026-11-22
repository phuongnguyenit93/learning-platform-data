# decimal, float, double và dữ liệu tiền tệ trong Apache Cassandra

Trong Apache Cassandra, ba kiểu `decimal`, `float` và `double` đều lưu được giá trị có phần thập phân, nhưng chúng **không có cùng ý nghĩa về độ chính xác**. `decimal` biểu diễn số thập phân với độ chính xác tùy ý theo khả năng tài nguyên, trong khi `float` và `double` là số dấu phẩy động **nhị phân** theo IEEE 754, có sai số làm tròn. Sai khác này đặc biệt quan trọng với **giá tiền, thuế, số dư, tỷ giá và đối soát**.

Bài học thuộc chương **Kiểu dữ liệu** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Mục tiêu của module là hiểu Cassandra như hệ cơ sở dữ liệu wide-column phân tán, lựa chọn partition key, thiết kế bảng theo truy vấn, mức nhất quán đọc/ghi, replication, compaction, repair và kết nối bằng Java. Trong bối cảnh đó, chọn kiểu số là một phần của hợp đồng dữ liệu: **kiểu số phải giữ đúng nghĩa nghiệp vụ, còn khóa và bảng phải phục vụ đúng truy vấn**.

## 1. Bảng so sánh nhanh

| Tiêu chí | `decimal` | `float` | `double` |
|---|---|---|---|
| Mô hình số | Thập phân chính xác, độ chính xác biến thiên | IEEE 754 binary32 | IEEE 754 binary64 |
| Kích thước giá trị cơ bản | Biến thiên theo giá trị và scale | 4 byte | 8 byte |
| Độ chính xác | Giữ chính xác số thập phân được biểu diễn, có giới hạn thực tế bởi tài nguyên | Khoảng 6–9 chữ số thập phân có nghĩa | Khoảng 15–17 chữ số thập phân có nghĩa |
| `0.1` có được biểu diễn chính xác? | Có | Không | Không |
| Java Driver 4.x | `BigDecimal` | `float`/`Float` | `double`/`Double` |
| Điểm mạnh | Tính tiền, thuế, tỷ lệ theo quy tắc thập phân | Dữ liệu đo/telemetry cần tiết kiệm dung lượng, chấp nhận sai số | Tính toán khoa học, tọa độ, thống kê cần độ chính xác xấp xỉ cao hơn |
| Điểm cần tránh | Không tự kiểm soát scale, cách làm tròn hay giới hạn nghiệp vụ | Sai số, mất chữ số khi giá trị lớn | Sai số vẫn tồn tại; không thay được số tiền chính xác |

**Đừng hiểu “double chính xác gấp đôi float” là “double chính xác tuyệt đối”.** Cả hai có tập số biểu diễn hữu hạn. `double` thường cho xấp xỉ tốt hơn, nhưng vẫn không bảo toàn chính xác mọi số thập phân.

Các kiểu khác có thể phù hợp hơn cho dữ liệu liên quan:

- `bigint`: số tiền được quy đổi thành **đơn vị nhỏ nhất** dưới dạng số nguyên 64 bit, ví dụ 19,90 USD thành 1.990 cent khi quy tắc tiền tệ cho phép.
- `int`, `bigint`: số đo được **nhân theo một hệ số cố định** trước khi lưu, ví dụ 23,875 °C thành 23.875 milli-degree Celsius.
- `varint`: số nguyên vượt 64 bit; không chứa phần thập phân.
- `text`: mã tiền tệ như `USD`, `VND`, mã định danh giao dịch có chữ số 0 ở đầu.

## 2. Hiểu khác biệt giữa số thập phân và số dấu phẩy động

### 2.1. `decimal`: giá trị thập phân chính xác

Một số thập phân có thể được diễn giải theo hai thành phần:

\[
\text{giá trị} = \text{số nguyên không scale} \times 10^{-\text{scale}}
\]

Ví dụ, 19,90 được biểu diễn bằng số nguyên 1990 và scale bằng 2. Java `BigDecimal` sử dụng mô hình **unscaled value + scale** tương ứng; CQL `decimal` dùng kiểu thập phân có độ chính xác biến thiên.

Điểm cần nhớ:

- Lưu `19.90` như `decimal` giúp giữ chính xác giá trị thập phân đó, thay vì gần đúng trong cơ số 2.
- CQL khai báo **`decimal`**, không khai báo `decimal(18, 2)` như một số hệ quản trị quan hệ. Cassandra **không tự áp dụng hạn mức 18 chữ số hoặc scale 2**.
- Quy tắc “mọi số tiền USD phải có tối đa hai chữ số sau dấu thập phân” cần được **kiểm tra ở ứng dụng/hợp đồng dữ liệu**.
- `decimal` không có “vô hạn” bộ nhớ hay tốc độ; giá trị rất dài làm tăng kích thước lưu trữ và chi phí tính toán.

Ví dụ sau biểu diễn cùng một giá trị số theo nhiều scale:

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("19.9");   // unscaled = 199, scale = 1
BigDecimal b = new BigDecimal("19.90");  // unscaled = 1990, scale = 2

System.out.println(a.compareTo(b) == 0); // true: giá trị số bằng nhau
System.out.println(a.equals(b));         // false: khác cả scale
~~~

Khi so sánh **giá trị tiền**, thường cần `compareTo()` hoặc chuẩn hóa scale nhất quán; đừng dùng `equals()` một cách vô thức khi dữ liệu có thể mang scale khác nhau.

### 2.2. `float` và `double`: chính xác theo nhị phân, xấp xỉ theo thập phân

IEEE 754 lưu số dưới dạng dấu, phần định trị (*significand*) và số mũ nhị phân. Một số như \(1/2\) hay \(1/8\) có biểu diễn nhị phân hữu hạn, nhưng \(1/10\) thì không. Vì vậy, `0.1` chỉ có thể được làm tròn đến một số `float` hoặc `double` gần nhất.

~~~java
double sumDouble = 0.1 + 0.2;
System.out.println(sumDouble);              // 0.30000000000000004
System.out.println(sumDouble == 0.3);       // false

float sumFloat = 0.1f + 0.2f;
System.out.println(sumFloat);               // thường hiển thị 0.3
System.out.println(sumFloat == 0.3f);       // có thể true ở ví dụ này

BigDecimal sumDecimal = new BigDecimal("0.1")
    .add(new BigDecimal("0.2"));
System.out.println(sumDecimal);             // 0.3
~~~

Đôi khi `float` *hiển thị* kết quả “đẹp”, nhưng đó là định dạng chuỗi đã làm tròn; không có nghĩa phép toán thập phân được thực hiện chính xác. Không dùng kết quả hiển thị của một ví dụ để suy ra tính an toàn của một phép tính tiền.

Các mốc giới hạn hữu ích:

| Tính chất | `float` | `double` |
|---|---:|---:|
| Số bit định trị có hiệu lực (bao gồm bit ẩn) | 24 | 53 |
| Khoảng số nguyên liên tiếp biểu diễn chính xác quanh 0 | Đến \(2^{24}=16.777.216\) | Đến \(2^{53}=9.007.199.254.740.992\) |
| Khi vượt ngưỡng đó | Có số nguyên liên tiếp không phân biệt được | Có số nguyên liên tiếp không phân biệt được |

Ví dụ, ép số nguyên 16.777.217 sang Java `float` có thể cho kết quả 16.777.216. Điều này ảnh hưởng đến phép kiểm tra bằng nhau, tính tổng lớn và mã hóa JSON trung gian. Với số nguyên chính xác, hãy dùng kiểu nguyên phù hợp; với tiền, hãy dùng `decimal` hoặc cách lưu tiền bằng số nguyên đơn vị nhỏ nhất.

### 2.3. Độ chính xác (*precision*) khác với scale và quy tắc làm tròn

Ba khái niệm có vai trò khác nhau:

- **Precision**: số chữ số có nghĩa của một giá trị. Trong Java `BigDecimal`, `new BigDecimal("123.45").precision()` bằng 5.
- **Scale**: số chữ số thập phân theo mô hình `BigDecimal`. Với 123,45, scale là 2.
- **Rounding mode**: quy tắc chọn kết quả khi cần bỏ bớt chữ số: `HALF_UP`, `HALF_EVEN`, `DOWN`, `CEILING`... Quy tắc do nghiệp vụ xác định.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("10.005");

System.out.println(amount.setScale(2, RoundingMode.HALF_UP));   // 10.01
System.out.println(amount.setScale(2, RoundingMode.HALF_EVEN)); // 10.00
~~~

Cả hai kết quả có thể phù hợp trong những hợp đồng tính toán khác nhau. Cassandra không biết chính sách thuế, kế toán hay cách xử lý khoản tiền lẻ: **ứng dụng phải thống nhất cách làm tròn, thời điểm làm tròn và đơn vị tiền tệ**.

## 3. Chọn kiểu nào cho dữ liệu tiền tệ?

### 3.1. Chiến lược A: `decimal` + mã tiền tệ

Dùng khi cần biểu diễn số tiền dưới dạng thập phân rõ ràng, ví dụ đơn giá 19,90, thuế suất 0,075, tỷ giá có nhiều chữ số hoặc lượng tiền cần xử lý với scale nghiệp vụ.

~~~cql
CREATE TABLE prices_by_sku_currency (
    sku text,
    currency_code text,
    effective_from timestamp,
    unit_price decimal,
    tax_rate decimal,
    PRIMARY KEY ((sku, currency_code), effective_from)
) WITH CLUSTERING ORDER BY (effective_from DESC);

INSERT INTO prices_by_sku_currency (
    sku, currency_code, effective_from, unit_price, tax_rate
) VALUES (
    'SKU-001', 'USD', '2026-11-21T00:00:00Z', 19.90, 0.075
);

SELECT effective_from, unit_price, tax_rate
FROM prices_by_sku_currency
WHERE sku = 'SKU-001' AND currency_code = 'USD'
LIMIT 1;
~~~

Ở đây:

- `unit_price decimal` lưu đơn giá chính xác 19,90; `tax_rate decimal` lưu tỷ lệ 7,5% chính xác theo thập phân.
- `currency_code text` là thông tin bắt buộc để diễn giải tiền; con số 19,90 **không đủ** để nói đó là USD, EUR hay đơn vị khác.
- Partition key `(sku, currency_code)` gom lịch sử giá theo SKU và đồng tiền; `effective_from DESC` hỗ trợ lấy giá mới nhất từ một phân vùng.
- Nếu SKU có lịch sử giá tăng không giới hạn, phải tính tới kích thước phân vùng, thời gian lưu lịch sử và cách chia dữ liệu khi tải lớn. Đây là bài toán thiết kế bảng theo truy vấn; `decimal` không giải quyết thay phần khóa.

**Không nên** nối chuỗi để tính thuế hoặc lưu tiền như `"19.90"` chỉ vì cần giữ số 0 thập phân. Chuỗi là tốt cho **định dạng đầu vào/đầu ra**, còn `BigDecimal`/`decimal` tốt cho **giá trị số được tính toán**.

### 3.2. Chiến lược B: `bigint` theo đơn vị tiền nhỏ nhất

Trong nhiều hệ thống thanh toán, thay vì lưu 19,90 USD dưới dạng thập phân, có thể lưu **1990 cent** dưới dạng `bigint`. Giá trị được đếm bằng số nguyên nên phép cộng/trừ đơn vị nhỏ nhất không có sai số dấu phẩy động.

~~~cql
CREATE TABLE ledger_entries_by_account_currency_day (
    account_id uuid,
    currency_code text,
    entry_day date,
    entry_at timestamp,
    entry_id uuid,
    amount_minor bigint,
    description text,
    PRIMARY KEY (
        (account_id, currency_code, entry_day),
        entry_at, entry_id
    )
) WITH CLUSTERING ORDER BY (entry_at DESC, entry_id ASC);
~~~

Ví dụ khoản ghi có 19,90 USD có thể là `amount_minor = 1990`, trong khi khoản ghi nợ 5,00 USD có thể là `amount_minor = -500`. Cần xác định trong nghiệp vụ dấu dương/âm có nghĩa gì và giá trị bao gồm thuế, phí hay chưa.

**Không phải mọi loại tiền đều có hai chữ số thập phân.** Số chữ số đơn vị nhỏ nhất phụ thuộc mã tiền và chuẩn nghiệp vụ áp dụng; nhiều đơn vị không dùng phần lẻ, một số có ba chữ số. Hãy lấy scale từ một bảng/quy tắc tiền tệ do hệ thống kiểm soát, thay vì mặc định nhân mọi khoản tiền với 100.

Trong Java, chuyển đổi có kiểm tra:

~~~java
import java.math.BigDecimal;

BigDecimal usdAmount = new BigDecimal("19.90");
int usdMinorDigits = 2; // Theo quy ước tiền tệ của hệ thống.

long cents = usdAmount
    .movePointRight(usdMinorDigits)
    .longValueExact();

System.out.println(cents); // 1990
~~~

`longValueExact()` sẽ báo lỗi nếu phép chuyển đổi tạo phần lẻ của đơn vị nhỏ nhất hoặc vượt miền 64 bit. Cách này giúp phát hiện dữ liệu không hợp lệ, ví dụ yêu cầu lưu 19,999 USD vào hệ thống chỉ chấp nhận đơn vị cent nhưng chưa có quy tắc làm tròn.

**Ưu điểm** của `bigint` minor units: nhất quán cho cộng/trừ, kích thước cố định, dễ đối chiếu khi đơn vị nhỏ nhất đã chuẩn hóa. **Hạn chế**: không trực tiếp giữ được tỷ giá có nhiều chữ số, các khoản cần độ phân giải nhỏ hơn đơn vị tiền tệ, hoặc tổng tiền vượt phạm vi 64 bit. Khi đó cần thiết kế khác cho từng loại dữ liệu.

### 3.3. So sánh hai chiến lược tiền

| Câu hỏi thiết kế | `decimal` | `bigint` minor units |
|---|---|---|
| Giá 19,90 USD | `19.90` | `1990` cent |
| Có thể lưu tỷ giá `0.000123456789`? | Có, khi miền và scale được ứng dụng chấp nhận | Chỉ nếu quy đổi ra một đơn vị số nguyên phù hợp đã quy định |
| Quy tắc scale | Ứng dụng kiểm soát scale thập phân | Ứng dụng kiểm soát số chữ số đơn vị nhỏ nhất theo currency |
| Nguy cơ làm tròn | Khi tính toán/chuyển kết quả sang scale đích | Khi quy đổi từ giá thập phân sang đơn vị nhỏ nhất |
| Giới hạn miền | Tùy tài nguyên/biểu diễn | Số nguyên có dấu 64 bit |
| Chọn khi | Giá, thuế, tỷ lệ, các đại lượng thập phân chính xác | Giao dịch đã chốt theo đơn vị nhỏ nhất, tích lũy tiền trong miền 64 bit |

Đối với **một khoản tiền làm nguồn dữ liệu chuẩn**, thường chọn **một cách biểu diễn** và quy định cách chuyển đổi. Không ghi đồng thời `amount_decimal` và `amount_minor` như hai nguồn chân lý độc lập nếu không có cơ chế kiểm soát đồng nhất; khi chúng khác nhau sẽ khó biết giá trị nào đúng.

## 4. Tại sao không dùng `float` hoặc `double` làm tiền?

Giả sử cần cộng hàng triệu giá trị 0,01 để tính tổng. Với `double`, một số sai số rất nhỏ có thể xuất hiện sau phép cộng; cách tích lũy và thứ tự phép toán cũng có thể ảnh hưởng đến chữ số cuối. Với `float`, sai số có thể lớn hơn vì ít bit định trị hơn.

Nguy cơ thực tế không nằm ở việc UI hiển thị thêm vài chữ số: cùng một phép tính có thể đưa ra **kết quả làm tròn khác ở biên**, so sánh `==` sai, hoặc khiến hai dịch vụ tính ra số lẻ khác nhau. Vì vậy:

1. **Không dùng `float`/`double` để lưu giá trị chuẩn của tiền, giá, khoản nợ, tiền thuế hoặc số dư phải đối soát.**
2. Dùng `BigDecimal` từ lúc parse dữ liệu đến lúc tính toán và bind vào CQL `decimal`, hoặc dùng `long` với đơn vị nhỏ nhất theo quy tắc rõ ràng.
3. Tính toán thuế/phí/chiết khấu với độ chính xác trung gian phù hợp rồi **làm tròn tại bước nghiệp vụ đã định nghĩa**, chẳng hạn khi lập dòng hóa đơn hoặc khi chốt tổng hóa đơn. Hai chính sách này có thể cho kết quả khác nhau.
4. Khi chia tiền thành nhiều phần, phải có quy tắc xử lý **phần dư**; ba lần nhân 3,33 không tạo lại đủ 10,00.

Ví dụ chia một khoản 10,00 USD cho ba người:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal total = new BigDecimal("10.00");
BigDecimal first = total.divide(
    BigDecimal.valueOf(3), 2, RoundingMode.DOWN
); // 3.33
BigDecimal second = first;                 // 3.33
BigDecimal third = total.subtract(first).subtract(second); // 3.34

System.out.println(first.add(second).add(third)); // 10.00
~~~

Việc ai nhận phần dư là **chính sách nghiệp vụ**, không phải quy tắc có sẵn của Cassandra.

## 5. `float` và `double` phù hợp với dạng dữ liệu nào?

Không phải mọi giá trị thập phân đều là tiền hoặc phải đối soát tuyệt đối. `float` và `double` có vai trò quan trọng trong telemetry, phân tích số và khoa học.

| Dữ liệu | Kiểu thường phù hợp | Lý do |
|---|---|---|
| Nhiệt độ cảm biến sai số ±0,1 °C | `float` | Sai số đo thực tế thường lớn hơn sai số biểu diễn |
| Tọa độ địa lý phục vụ phép tính hình học | `double` | Cần độ chính xác xấp xỉ cao hơn `float` |
| Chỉ số, xác suất, điểm mô hình | `float` hoặc `double` | Phụ thuộc yêu cầu chữ số có nghĩa và thuật toán |
| Số đo phòng thí nghiệm phải giữ chính xác 4 chữ số thập phân theo quy chuẩn | `decimal` hoặc số nguyên đã scale | Dễ áp dụng chính xác quy tắc lượng tử hóa |
| Giá sản phẩm, hóa đơn, thuế phải đối soát | `decimal` hoặc `bigint` minor units | Cần chính xác theo hệ thập phân/đơn vị tiền |
| Số lượng hàng hóa là số nguyên | `int`/`bigint` | Tránh phần lẻ không có ý nghĩa |

Ví dụ bảng telemetry thiết kế theo truy vấn “lấy mẫu đo theo thiết bị và giờ”:

~~~cql
CREATE TABLE telemetry_by_device_hour (
    device_id uuid,
    hour_bucket timestamp,
    measured_at timestamp,
    sample_id uuid,
    temperature_c float,
    latitude double,
    longitude double,
    PRIMARY KEY ((device_id, hour_bucket), measured_at, sample_id)
) WITH CLUSTERING ORDER BY (measured_at DESC, sample_id ASC);

SELECT measured_at, sample_id, temperature_c, latitude, longitude
FROM telemetry_by_device_hour
WHERE device_id = 123e4567-e89b-12d3-a456-426614174000
  AND hour_bucket = '2026-11-21T01:00:00Z'
LIMIT 100;
~~~

Ở đây `float` phù hợp với nhiệt độ xấp xỉ; `double` phù hợp với kinh độ/vĩ độ cần nhiều chữ số có nghĩa. Cả hai đều là **cột dữ liệu**, còn partition key và clustering key được chọn theo mẫu truy vấn. Nếu cần tìm tất cả điểm đo trong một vùng địa lý, cần thiết kế đường truy cập riêng; việc dùng `double` không tạo ra khả năng tìm kiếm không gian mặc định.

**Kiểm tra đầu vào:** trước khi ghi dữ liệu đo ở Java, dùng `Float.isFinite(value)` hoặc `Double.isFinite(value)` nếu nghiệp vụ không chấp nhận NaN hoặc vô cực. Các giá trị đặc biệt và sai số đo phải được xử lý theo hợp đồng dữ liệu; không biến dữ liệu thiếu thành 0 một cách tùy tiện.

**Hạn chế thực dụng:** nếu giá trị thay đổi rất nhỏ so với độ lớn của số hiện tại, `float` có thể không còn phân biệt được hai mẫu liên tiếp. Ví dụ phép tăng 1 sau một giá trị lớn hơn \(2^{24}\) có thể không làm thay đổi giá trị `float` đã lưu. Với số đo cần chính xác theo một bước cố định, hãy cân nhắc lưu số nguyên theo đơn vị đã nhân hệ số.

## 6. Java Driver 4.x: ánh xạ và ghi/đọc an toàn

Với Apache Cassandra Java Driver 4.x, các ánh xạ phổ biến là:

| CQL | Java | Prepared statement | `Row` getter |
|---|---|---|---|
| `decimal` | `BigDecimal` | `setBigDecimal(index, value)` | `getBigDecimal(column)` |
| `float` | `float` | `setFloat(index, value)` | `getFloat(column)` |
| `double` | `double` | `setDouble(index, value)` | `getDouble(column)` |
| `bigint` (đơn vị tiền nhỏ nhất) | `long` | `setLong(index, value)` | `getLong(column)` |

### 6.1. Tính giá và lưu decimal

Giả sử `session` là một `CqlSession` đã kết nối tới cluster và sử dụng đúng keyspace. Đoạn mã sau ghi giá có hiệu lực và thuế suất vào bảng `prices_by_sku_currency`:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;

// CqlSession session = ...; // Đã được cấu hình ngoài ví dụ.

BigDecimal unitPrice = new BigDecimal("19.90");
BigDecimal taxRate = new BigDecimal("0.075"); // 7,5%
int quantity = 3;

// Dùng BigDecimal xuyên suốt phép tính.
BigDecimal subtotal = unitPrice.multiply(BigDecimal.valueOf(quantity));
BigDecimal tax = subtotal.multiply(taxRate)
    .setScale(2, RoundingMode.HALF_EVEN); // Chính sách ví dụ.
BigDecimal total = subtotal.add(tax);

System.out.println(subtotal); // 59.70
System.out.println(tax);      // 4.48
System.out.println(total);    // 64.18

PreparedStatement insertPrice = session.prepare(
    "INSERT INTO prices_by_sku_currency "
  + "(sku, currency_code, effective_from, unit_price, tax_rate) "
  + "VALUES (?, ?, ?, ?, ?)");

BoundStatement bound = insertPrice.boundStatementBuilder()
    .setString(0, "SKU-001")
    .setString(1, "USD")
    .setInstant(2, Instant.parse("2026-11-21T00:00:00Z"))
    .setBigDecimal(3, unitPrice)
    .setBigDecimal(4, taxRate)
    .build();

session.execute(bound);
~~~

Lưu ý: `total` ở ví dụ là kết quả tính trong Java, không được tự động lưu vào bảng giá. Nếu nghiệp vụ cần lưu hóa đơn, nên xây dựng **bảng hóa đơn theo truy vấn** có khóa, thông tin đơn vị tiền, tổng đã chốt và nguồn tính toán rõ ràng.

### 6.2. Đọc lại giá mà không chuyển thành double

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

PreparedStatement findLatest = session.prepare(
    "SELECT unit_price, tax_rate "
  + "FROM prices_by_sku_currency "
  + "WHERE sku = ? AND currency_code = ? LIMIT 1");

Row row = session.execute(
    findLatest.bind("SKU-001", "USD")
).one();

if (row != null && !row.isNull("unit_price")) {
    BigDecimal latestPrice = row.getBigDecimal("unit_price");
    // Giữ nguyên BigDecimal khi tính tiếp; tránh latestPrice.doubleValue().
}
~~~

**Không tạo `BigDecimal` từ một `double` đã mất độ chính xác**:

~~~java
BigDecimal bad = new BigDecimal(0.1);         // Mang sai số nhị phân của 0.1
BigDecimal good = new BigDecimal("0.1");      // Chính xác 0.1

double alreadyRounded = 0.1 + 0.2;
BigDecimal notRepaired = BigDecimal.valueOf(alreadyRounded);
// 0.30000000000000004: chuyển kiểu không khôi phục được dữ liệu gốc.
~~~

`BigDecimal.valueOf(0.1)` có thể cho biểu diễn thập phân `0.1` nhờ chuyển `double` thành chuỗi trước; tuy nhiên, nếu giá trị `double` đã là **kết quả phép tính sai số**, chuyển thành `BigDecimal` không thể suy ra giá trị thập phân lý tưởng ban đầu. Vì thế, nhận số tiền từ chuỗi/đơn vị tiền nhỏ nhất và giữ kiểu chính xác xuyên toàn bộ luồng.

### 6.3. Kiểm tra scale ở biên ghi

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

static BigDecimal requireTwoFractionDigits(BigDecimal amount) {
    // Chỉ chấp nhận giá trị biểu diễn chính xác tới 2 chữ số lẻ.
    return amount.setScale(2, RoundingMode.UNNECESSARY);
}

BigDecimal valid = requireTwoFractionDigits(new BigDecimal("12.30"));

// requireTwoFractionDigits(new BigDecimal("12.345"))
// sẽ ném ArithmeticException, vì phải làm tròn.
~~~

Hàm ví dụ chỉ dùng cho miền tiền đã định nghĩa scale = 2. Với loại tiền có scale khác, cần lấy giá trị đúng từ cấu hình nghiệp vụ. Có thể quy ước ứng dụng chuyển exception thành lỗi validation rõ ràng, thay vì lưu một giá trị bị cắt chữ số.

## 7. Mẫu truy cập trong Cassandra liên quan thế nào đến kiểu số?

Hai nhóm dữ liệu phía trên có mẫu truy cập khác nhau:

1. **Lịch sử giá:** tra theo `sku + currency_code`, lấy thời điểm hiệu lực mới nhất → bảng `prices_by_sku_currency` với clustering `effective_from DESC`.
2. **Telemetry:** tra theo `device_id + hour_bucket`, lấy mẫu thời gian gần nhất → bảng `telemetry_by_device_hour` với clustering `measured_at DESC`.

`decimal` không tự cho phép truy vấn “mọi sản phẩm có giá dưới 100 USD” trên toàn cluster; `double` cũng không tự giúp truy vấn “mọi thiết bị có nhiệt độ trên 35 °C” hiệu quả. Cassandra được thiết kế để đọc theo **partition key đã biết**, sau đó áp dụng điều kiện phù hợp trên clustering columns; những kiểu tìm kiếm khác cần một mô hình truy cập, chỉ mục hoặc hệ phân tích được đánh giá riêng.

Nếu thường xuyên cần lấy đơn hàng theo khách hàng và ngày, hãy thiết kế bảng với partition key tương ứng; **số tiền là cột dữ liệu trong row**, được chọn `decimal` hay `bigint` theo tính đúng đắn của tiền. Dùng số tiền làm partition key thường tạo mẫu truy cập khó kiểm soát và không giải quyết nhu cầu tìm kiếm theo khách hàng.

Không nên dùng số dấu phẩy động như một “khóa định danh chính xác”: vì phép đo có sai số, hai giá trị tưởng tương đương có thể không bằng nhau sau chuyển đổi. Nếu cần tra cứu theo khoảng độ đo, nên mô hình hóa bucket hoặc key định lượng theo quy tắc nhất quán và có bảng theo truy vấn phù hợp.

## 8. Retry, consistency và đối soát: Cassandra không làm tròn thay ứng dụng

Apache Cassandra là hệ phân tán: một lần ghi có thể thành công trên một số replica dù ứng dụng nhận timeout. Với dữ liệu tiền, các yêu cầu sau phải được thiết kế độc lập với kiểu số:

- **Idempotency:** cùng một giao dịch được retry phải dùng **cùng ID và khóa chính**. Nếu mỗi lần retry tạo `entry_id` mới, có thể sinh nhiều dòng cùng một giao dịch.
- **Tính nhất quán đọc/ghi:** consistency level như `LOCAL_QUORUM` điều chỉnh số replica cần xác nhận, nhưng **không biến nhiều thay đổi ở các phân vùng khác nhau thành một giao dịch tài chính ACID**.
- **Ghi đè và đồng thời:** hai client cùng đọc số dư, cộng rồi ghi đè có thể làm mất một cập nhật. `decimal` và `bigint` không tự tạo phép cộng nguyên tử.
- **Counter:** kiểu `counter` chuyên biệt có đặc tính ghi/retry khác và không thích hợp làm sổ cái phải đối soát đúng từng sự kiện.
- **Nguồn sự kiện:** với bài toán tiền, thường cần lưu bản ghi giao dịch có định danh ổn định, bảo đảm chống trùng ở cấp nghiệp vụ và tổng hợp/suy ra số dư theo thiết kế được kiểm soát.

Compaction quản lý SSTable, repair hỗ trợ đồng bộ replica; **không có cơ chế nào trong hai cơ chế này tự sửa số tiền đã tính sai vì `double` hoặc làm tròn khác quy tắc**. Với dữ liệu cần lưu trữ/kiểm toán, phải xem xét TTL, chính sách retention và việc xóa dữ liệu theo yêu cầu nghiệp vụ.

Sổ cái tài chính chuẩn có những yêu cầu bổ sung về bảo toàn giao dịch, chống ghi trùng và đối soát giữa tài khoản. Cassandra có thể tham gia kiến trúc này, nhưng chỉ với các ràng buộc và quy trình phù hợp; một bảng `ledger_entries_by_account_currency_day` là **ví dụ thiết kế truy vấn**, không phải giải pháp sổ cái hoàn chỉnh.

## 9. Những lỗi phổ biến khi dùng decimal, float, double

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Lưu `19.90` USD bằng `double` | Có thể xuất hiện sai số nhị phân trong tính toán | Dùng `decimal`/`BigDecimal` hoặc `bigint` minor units |
| Dùng `new BigDecimal(0.1)` cho tiền | Mang giá trị gần đúng của `double` vào `BigDecimal` | Parse chuỗi số thập phân hoặc đơn vị nguyên |
| Cho rằng `decimal` tự giới hạn hai số lẻ | Lưu được 19,999 dù nghiệp vụ chỉ cho phép cent | Kiểm tra scale và làm tròn ở biên ghi |
| Làm tròn trước mỗi bước nhưng hệ khác làm tròn sau tổng | Đối soát hai dịch vụ lệch nhau | Định nghĩa rõ thời điểm và chính sách làm tròn |
| Quy đổi mọi đồng tiền bằng hệ số 100 | Giá trị sai với currency có scale khác 2 | Dùng quy tắc đơn vị nhỏ nhất theo currency |
| Lấy `BigDecimal.doubleValue()` rồi tính tiếp | Mất chính xác vốn đã giữ được | Giữ `BigDecimal` trong toàn bộ pipeline |
| Cộng một khoản `bigint` bằng read-modify-write cạnh tranh | Có thể mất cập nhật | Thiết kế event/idempotency hoặc cơ chế concurrency phù hợp |
| Tìm giá/thang đo trên mọi partition bằng cách đổi kiểu cột | Truy vấn vẫn không khớp partition key | Thiết kế bảng truy vấn hoặc index theo workload |
| Giả định bản ghi double cũ có thể chuyển sang decimal mà khôi phục giá gốc | Sai số trước đây vẫn tồn tại | Backfill từ nguồn dữ liệu gốc và quy tắc đối soát |
| Dùng `float` để lưu số nguyên lớn chính xác | Các số liên tiếp có thể bị làm tròn thành cùng giá trị | Dùng `int`/`bigint`/`varint` |

## 10. Chuyển đổi schema khi trước đây đã dùng float/double cho tiền

Một hệ thống đã lưu số tiền bằng `float` hoặc `double` có thể cần chuyển sang `decimal` hay `bigint` minor units. Nên thực hiện theo hướng sau:

1. **Xác định quy tắc tiền**: mã tiền, scale, thuế/phí, làm tròn từng dòng hay tổng hóa đơn, timezone liên quan ngày chốt và cách xử lý giao dịch ngược.
2. **Xác định nguồn dữ liệu đáng tin**: hóa đơn gốc, sự kiện nguồn có số tiền chính xác, dữ liệu từ cổng thanh toán. Không cho rằng chuyển `double` lịch sử sang `BigDecimal` sẽ khôi phục chính xác dự định ban đầu.
3. **Tạo bảng/đường ghi mới phù hợp mẫu truy vấn** với kiểu đúng, thay vì giả định có thể thay đổi kiểu cột đang có dữ liệu một cách an toàn bằng một lệnh `ALTER`.
4. **Cập nhật Java codec và validation**: parse bằng chuỗi/đơn vị nguyên, dùng `setBigDecimal` hoặc `setLong`, kiểm tra scale, overflow và loại tiền.
5. **Backfill và đối chiếu**: kiểm tra số lượng giao dịch, tổng theo kỳ/tiền tệ, giao dịch biên, giao dịch hoàn tiền, ID trùng; thiết kế chuyển đổi luồng đọc/ghi có kiểm soát.
6. **Duy trì tính idempotent khi retry** trong thời gian chuyển đổi và xác nhận các dịch vụ không còn ghi vào schema/codec cũ trước khi thu hồi.

Điểm khó nhất thường là **khôi phục ngữ nghĩa tiền**, không phải cú pháp thay cột. Một giá trị `double` gần 19,90 có thể đã được dùng trong nhiều bước làm tròn khác nhau; migration cần quy định giá trị hợp lệ để đối soát.

## 11. Bài tập tự kiểm tra

**Bài 1 — Chọn kiểu.** Một dịch vụ nhận nhiệt độ cảm biến sai số ±0,5 °C, tốc độ 100.000 mẫu/giây, chỉ cần thống kê xu hướng. Nên ưu tiên `float` hay `decimal`? Giải thích dựa trên độ chính xác thực sự cần và chi phí dữ liệu.

**Gợi ý:** `float` thường đủ cho độ phân giải cảm biến này; cần đo benchmark và xác nhận dải đo trước khi chọn. Khóa phân vùng theo thiết bị/thời gian mới quyết định khả năng đọc mẫu gần nhất.

**Bài 2 — Cắt lỗi làm tròn.** Dữ liệu giá từ API là chuỗi `"12.345"`, currency có hai chữ số đơn vị nhỏ nhất. Nên làm gì trước khi ghi `bigint`?

**Gợi ý:** áp dụng hoặc từ chối theo quy tắc làm tròn đã thống nhất; không âm thầm cắt về 1234 cent. Nếu chính sách cấm phần lẻ cent, dùng `setScale(2, UNNECESSARY)` rồi `movePointRight(2).longValueExact()`.

**Bài 3 — Phân biệt nguồn số.** Java tính `double result = 0.1 + 0.2;` rồi tạo `BigDecimal.valueOf(result)`. Giá trị mới có bằng chính xác `new BigDecimal("0.3")` không?

**Đáp án:** không; kết quả trung gian đã chứa sai số và không được sửa chỉ bằng việc đổi kiểu.

**Bài 4 — Sửa truy vấn.** Bảng lưu `customer_id` làm partition key, `paid_at` làm clustering key, `amount decimal` là cột dữ liệu. Muốn truy vấn mọi giao dịch có `amount > 100` trên toàn bộ khách hàng thì đổi `amount` sang `double` có giải quyết không?

**Đáp án:** không. Cần một đường truy cập/thiết kế dữ liệu phục vụ truy vấn đó, hoặc lựa chọn chỉ mục/hệ phân tích được chứng minh phù hợp.

## 12. Checklist trước khi chốt kiểu số

- [ ] Giá trị là **tiền/thông tin cần chính xác** hay **số đo chấp nhận xấp xỉ**?
- [ ] Với tiền, đã xác định **mã tiền, scale, đơn vị nhỏ nhất, chính sách làm tròn và thời điểm làm tròn**?
- [ ] Nếu dùng `decimal`, ứng dụng có kiểm tra scale/miền giá trị thay vì giả định Cassandra tự kiểm tra?
- [ ] Nếu dùng `bigint` minor units, có kiểm tra `longValueExact()`, hệ số chuyển đổi và tràn 64 bit?
- [ ] Java có tạo `BigDecimal` từ **chuỗi số chính xác** và giữ kiểu đó qua các phép tính tiền?
- [ ] Nếu dùng `float`/`double`, đã xác nhận sai số chấp nhận được, dải đo và giá trị bất thường?
- [ ] Các kiểu cột đã khớp `setBigDecimal`/`setFloat`/`setDouble`/`setLong` của Java Driver?
- [ ] Bảng có partition key và clustering columns hỗ trợ **truy vấn thực tế**, giới hạn tăng trưởng phân vùng?
- [ ] Retry, ID giao dịch, cập nhật đồng thời và việc đối soát có được xử lý **ngoài quyết định chọn kiểu số**?
- [ ] Nếu có dữ liệu cũ bằng số dấu phẩy động, có nguồn gốc và quy trình migration/đối chiếu?

**Ghi nhớ:** chọn **`decimal`** khi cần giữ chính xác giá trị thập phân, đặc biệt trong tính giá, tỷ giá và thuế; chọn **`bigint` theo đơn vị tiền nhỏ nhất** khi nghiệp vụ có đơn vị nguyên rõ ràng; dùng **`float`/`double`** cho đại lượng đo hoặc tính toán cho phép sai số. Trong Cassandra, **độ chính xác của số** và **đúng mẫu truy vấn phân tán** phải được thiết kế đồng thời; replication, consistency và repair không thể thay thế quyết định này.

