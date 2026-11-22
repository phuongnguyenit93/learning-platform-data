# Kiểu số, độ chính xác và nguy cơ mất giá trị

Một API Java nhận giá `19.99`, ghi xuống database và trả phản hồi “lưu thành công”. Nhưng báo cáo sau đó hiển thị `20.00`. Một dịch vụ khác nhận mã số `9007199254740993` qua JSON rồi đọc thành `9007199254740992`. Cả hai thao tác đều có thể hoàn tất mà không ném lỗi: **giá trị đã bị thay đổi trong quá trình biểu diễn hoặc chuyển kiểu**.

Bài học này thuộc chương **Biểu diễn dữ liệu** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module trang bị nền tảng lưu trữ dữ liệu bền vững trong ứng dụng Java: chọn mô hình dữ liệu và lược đồ, truy vấn và chỉ mục; transaction, isolation, kiểm soát đồng thời; ranh giới persistence, lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và tối ưu hiệu năng. Với chủ đề **“Kiểu số, độ chính xác và nguy cơ mất giá trị”**, chúng ta xác định cách giữ đúng ý nghĩa của một con số khi đi qua giao diện, Java, JDBC, database, JSON và hệ thống báo cáo.

Sau bài học, bạn có thể:

- Phân biệt **số nguyên**, **số thập phân chính xác** và **số dấu phẩy động nhị phân**; nhận diện điểm mất thông tin của mỗi nhóm.
- Hiểu **miền giá trị**, **precision**, **scale**, **đơn vị đo** và **quy tắc làm tròn** là thành phần của hợp đồng dữ liệu.
- Chọn kiểu Java và SQL phù hợp, tránh overflow, truncation, rounding ngoài ý muốn và chuyển kiểu ngầm.
- Thiết kế đường đi Java → database → API sao cho giá trị quan trọng có thể round-trip mà không thay đổi.
- Viết tiêu chí kiểm tra ở các giá trị biên và trong quá trình tiến hóa schema.

## 1. Con số là giá trị nghiệp vụ, không chỉ là chuỗi chữ số

Ví dụ `1250` có thể biểu diễn **1.250 đồng**, **12,50 đơn vị tiền nhỏ nhất**, **1.250 sản phẩm**, **1,250 kg** hoặc một **mã định danh**. Nếu chỉ lưu “1250” mà không biết ý nghĩa, phần mềm không thể xác định kiểu số hay cách hiển thị đúng.

Trước khi chọn kiểu dữ liệu, cần trả lời:

| Thuộc tính của giá trị | Câu hỏi cần làm rõ | Ví dụ |
| --- | --- | --- |
| **Ngữ nghĩa** | Giá trị là số lượng, tiền, tỷ lệ, số đo hay mã định danh? | `quantity` khác `orderId` dù cùng gồm chữ số |
| **Miền giá trị** | Nhỏ nhất/lớn nhất là bao nhiêu? Có âm không? | Tồn kho có thể không âm; điều chỉnh tồn kho có thể âm |
| **Đơn vị** | Cents, đồng, kilogram, millisecond hay phần trăm? | `amountMinorUnits = 1999` nghĩa là 19,99 đơn vị chính nếu hệ tiền dùng 100 đơn vị nhỏ |
| **Độ phân giải** | Bước nhỏ nhất có ý nghĩa? | Giá được định nghĩa đến 0,01; cảm biến đến 0,1 °C |
| **Độ chính xác cần giữ** | Có cho phép sai số không? Bao nhiêu? | Tổng thanh toán thường cần tính chính xác theo quy tắc tiền tệ |
| **Quy tắc làm tròn** | Ở bước nào, theo cách nào? | Làm tròn tại từng dòng hóa đơn hay khi tổng hợp? |
| **Vắng mặt/không hợp lệ** | `null` khác 0 không? Có chấp nhận NaN/vô cực không? | “Chưa đo” không có nghĩa giá trị đo bằng 0 |
| **Quy tắc chuyển đổi** | Định dạng khác có giữ nguyên ý nghĩa? | `"000123"` là mã, không nên ép thành số 123 |

Một số kiểu dữ liệu phù hợp trong bộ nhớ vẫn có thể không phù hợp khi đi qua mạng hoặc lưu xuống database. **Ranh giới persistence** cần quy định cả những phép chuyển đổi được phép và khi nào phải từ chối dữ liệu.

## 2. Ba nhóm biểu diễn số cần phân biệt

| Nhóm | Java thường dùng | SQL thường gặp | Đặc điểm |
| --- | --- | --- | --- |
| **Số nguyên cố định** | `byte`, `short`, `int`, `long` | `SMALLINT`, `INTEGER`, `BIGINT` | Biểu diễn chính xác các số nguyên trong miền giới hạn |
| **Số nguyên tùy ý lớn** | `BigInteger` | `NUMERIC`/`DECIMAL` không có phần lẻ, tùy khả năng engine | Không bị giới hạn bởi 32/64 bit của Java, nhưng vẫn bị giới hạn bởi bộ nhớ, schema và hệ lưu trữ |
| **Thập phân chính xác** | `BigDecimal` | `DECIMAL(p,s)`, `NUMERIC(p,s)` | Giữ chính xác các số thập phân hữu hạn trong miền được hỗ trợ; cần quy định precision/scale |
| **Dấu phẩy động nhị phân** | `float`, `double` | `REAL`, `FLOAT`, `DOUBLE PRECISION` (tùy engine) | Biểu diễn gần đúng; hiệu quả cho nhiều tính toán khoa học, đo lường nhưng có sai số làm tròn |
| **Chuỗi biểu diễn số** | `String` | `VARCHAR`, `TEXT` | Giữ ký tự nguyên văn như số tài khoản, mã có số 0 đầu; không tự hỗ trợ phép toán số |

### Số nguyên có giới hạn biểu diễn

- Java `int` có 32 bit có dấu, giá trị từ **−2.147.483.648 đến 2.147.483.647**.
- Java `long` có 64 bit có dấu, giá trị từ **−9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807**.
- `BigInteger` hỗ trợ số nguyên có độ dài tùy khả năng bộ nhớ; khi lưu vào DB vẫn phải kiểm tra giới hạn kiểu cột.
- SQL `INTEGER`/`BIGINT` thường tương ứng 32/64 bit ở các hệ quan hệ phổ biến, nhưng khi thiết kế phải kiểm tra **tài liệu của DB cụ thể**, đặc biệt với kiểu unsigned hoặc `NUMBER`.

Nếu cần số nguyên tuyệt đối chính xác, `double` **không phải một cách an toàn để thay cho `long`**. IEEE 754 binary64 có 53 bit độ chính xác của phần trị; không thể biểu diễn mọi số nguyên lớn hơn **2^53 = 9.007.199.254.740.992**. Ví dụ `9.007.199.254.740.993` không thể giữ nguyên khi đổi sang binary64.

### Số thập phân không phải luôn là số thực nhị phân

Số `0.1` viết ở hệ thập phân là một phân số hữu hạn, nhưng trong hệ nhị phân thường phải biểu diễn thành chuỗi vô hạn. Vì vậy `double` chỉ lưu một giá trị gần với `0.1`, không phải chính xác phân số \(1/10\).

`BigDecimal` lưu giá trị dạng **unscaled integer × 10^(−scale)**. Ví dụ `new BigDecimal("12.30")` có unscaled value là `1230` và scale là `2`. Nhờ dùng cơ số 10, nó giữ đúng số thập phân hữu hạn được truyền vào dưới dạng chuỗi mà không cần đi qua nhị phân dấu phẩy động.

Điều này không làm mọi phép toán trở nên chính xác vô hạn. Phép chia `1/3` có phần thập phân vô hạn; khi cần kết quả hữu hạn, **chính sách scale và rounding** vẫn bắt buộc.

## 3. Mất độ chính xác khi dùng `float`/`double`

Ví dụ Java:

```java
public class FloatingPointExample {
    public static void main(String[] args) {
        double a = 0.1;
        double b = 0.2;
        double sum = a + b;

        System.out.println(sum);           // 0.30000000000000004
        System.out.println(sum == 0.3);    // false
    }
}
```

Đây là hệ quả tự nhiên của biểu diễn dấu phẩy động nhị phân. `double` có khoảng 15–17 chữ số thập phân có nghĩa tùy giá trị; `float` ít hơn, thường khoảng 6–9 chữ số có nghĩa. Số liệu này **không phải** là cam kết rằng luôn có từng ấy chữ số sau dấu thập phân.

**Dùng `double` hợp lý khi** dữ liệu vốn là phép đo gần đúng, sai số được chấp nhận, thuật toán có phân tích sai số và không cần giữ chính xác đơn vị tiền nhỏ nhất. Ví dụ mô phỏng, tọa độ, tín hiệu cảm biến hoặc thống kê có thể phù hợp.

**Không nên dùng `double` làm đơn vị lưu chính cho** số tiền cần tính đúng đến phần nhỏ nhất, số lượng cần đếm chính xác, ID nguyên rất lớn hoặc một tỷ lệ cần tuân thủ chính sách làm tròn thập phân cụ thể.

### Đổi `double` sang `BigDecimal` không khôi phục được dữ liệu đã mất

```java
import java.math.BigDecimal;

BigDecimal fromText = new BigDecimal("0.1");  // chính xác 0.1
BigDecimal fromBinary = new BigDecimal(0.1);  // phơi bày giá trị double gần đúng

System.out.println(fromText);
// 0.1

System.out.println(fromBinary);
// 0.1000000000000000055511151231257827021181583404541015625
```

`BigDecimal.valueOf(0.1)` thường cho chuỗi thập phân ngắn `0.1` bằng cách chuyển đổi qua biểu diễn chuỗi của `double`, nhưng **không thể phục hồi các chữ số ban đầu đã bị mất** nếu `double` trước đó đến từ phép tính hoặc ép kiểu làm tròn.

Vì vậy, nếu yêu cầu độ chính xác thập phân, hãy **nhận dữ liệu từ dạng văn bản thập phân hoặc đơn vị số nguyên** ngay từ đầu. Đừng nhận vào `double` rồi mới chuyển để “sửa” sai số.

### So sánh số gần đúng

Với số dấu phẩy động, phép kiểm tra bằng tuyệt đối thường không phù hợp cho kết quả từ các phép toán. Có thể dùng ngưỡng sai số **được xác định theo ý nghĩa bài toán**, bao gồm cả sai số tuyệt đối và tương đối khi cần. Không có một giá trị epsilon cố định phù hợp với mọi thang đo.

Ngược lại, nếu nghiệp vụ yêu cầu **chính xác tuyệt đối**, so sánh có dung sai để “bỏ qua vài cent” là thay đổi quy tắc nghiệp vụ, không phải sửa một chi tiết kỹ thuật.

## 4. Precision và scale trong thập phân chính xác

Với kiểu `DECIMAL(p, s)` hoặc `NUMERIC(p, s)`, theo định nghĩa thường gặp:

- **Precision `p`**: số chữ số thập phân có nghĩa tối đa theo khai báo.
- **Scale `s`**: số chữ số dành cho phần sau dấu thập phân.
- Số chữ số phần nguyên được dành chỗ thường là **`p − s`**, với `0 ≤ s ≤ p` trong thiết kế thông dụng.

Ví dụ:

| Khai báo | Phần nguyên tối đa theo khai báo | Ví dụ phù hợp | Ví dụ cần kiểm tra |
| --- | --- | --- | --- |
| `DECIMAL(5,2)` | 3 chữ số | `999.99`, `12.30` | `1000.00` vượt miền; `1.234` cần xử lý scale |
| `DECIMAL(10,2)` | 8 chữ số | `99999999.99` | `100000000.00` vượt precision |
| `DECIMAL(18,0)` | 18 chữ số | Số lượng nguyên lớn trong giới hạn | `123.45` có phần lẻ |
| `DECIMAL(19,4)` | 15 chữ số | `123456.7890` | Giá trị có trên 4 chữ số thập phân |

**Chú ý khác biệt giữa các engine:** khi ghi số có scale lớn hơn cột, hệ quản trị có thể làm tròn, báo lỗi hoặc chịu ảnh hưởng cấu hình/chế độ SQL. Khi vượt giới hạn precision, hành vi và mã lỗi cũng phụ thuộc sản phẩm. **Không dựa vào sự thành công của `INSERT` để suy ra không có làm tròn**. Ứng dụng nên kiểm tra trước và dùng phép thử round-trip với chính DB triển khai.

Đặc biệt, `DECIMAL(10,2)` không có nghĩa “10 chữ số trước dấu phẩy và 2 chữ số sau”, mà thường là **10 chữ số tổng cộng**.

### Scale khác độ chính xác nghiệp vụ

`1.20` và `1.2` có thể đại diện cùng giá trị số học nhưng khác scale/định dạng. Với `BigDecimal`:

```java
import java.math.BigDecimal;

BigDecimal x = new BigDecimal("1.20");
BigDecimal y = new BigDecimal("1.2");

System.out.println(x.compareTo(y) == 0); // true: cùng giá trị số học
System.out.println(x.equals(y));         // false: khác scale
System.out.println(x.scale());           // 2
System.out.println(y.scale());           // 1
```

Nếu dùng `BigDecimal` làm key trong `HashMap` hoặc so sánh bằng `equals`, phải có quy tắc chuẩn hóa scale. Nếu muốn định dạng hiển thị cố định, dùng một scale được quy định và formatter thích hợp; đừng chỉ dựa vào `stripTrailingZeros()` vì kết quả có thể chuyển sang biểu diễn khoa học.

### Nguy cơ làm tròn sớm

Giả sử quy tắc làm tròn là `HALF_UP` về hai chữ số thập phân:

```text
Làm tròn từng dòng:
0.015 → 0.02
0.015 → 0.02
Tổng     0.04

Cộng trước, làm tròn một lần:
0.015 + 0.015 = 0.030 → 0.03
```

Hai kết quả khác nhau dù đều dùng `HALF_UP`. Do đó hợp đồng nghiệp vụ phải xác định **làm tròn tại từng dòng, từng giao dịch hay cuối phép tổng hợp**; không chỉ ghi “sử dụng 2 số lẻ”.

Trong Java, `RoundingMode.HALF_UP`, `HALF_EVEN`, `DOWN` và các chế độ khác không tương đương. Không tự chọn một chế độ cho toàn bộ hệ thống: quy tắc thuế, lãi suất, giá và đơn vị đo có thể khác nhau.

## 5. Overflow, thu hẹp kiểu và mất phần thập phân

Ngay cả các kiểu **biểu diễn chính xác** vẫn có thể làm mất dữ liệu nếu vượt miền hoặc ép kiểu sai.

### `int` và `long` có thể overflow mà không báo lỗi

```java
int max = Integer.MAX_VALUE;
int next = max + 1;
System.out.println(next); // -2147483648: tràn số với phép toán int

int checked = Math.addExact(max, 1); // ArithmeticException
```

Ví dụ với `long` và đơn vị tiền nhỏ nhất:

```java
long unitPriceMinor = 4_000_000_000_000_000_000L;
long quantity = 3;

long unsafe = unitPriceMinor * quantity; // overflow, kết quả sai
long checked = Math.multiplyExact(unitPriceMinor, quantity);
// ArithmeticException thay vì âm thầm chấp nhận dữ liệu hỏng
```

Đối với đại lượng có số lượng đủ lớn, có thể dùng `BigInteger` hoặc `BigDecimal` rồi kiểm tra miền khi ghi xuống database. Dù chọn cách nào, **ràng buộc độ lớn thuộc yêu cầu nghiệp vụ và schema**, không chỉ thuộc kiểu Java.

### Ép kiểu có thể cắt giá trị

```java
long big = 3_000_000_000L;
int narrowed = (int) big;      // mất giá trị, không ném lỗi
int safe = Math.toIntExact(big); // ArithmeticException

double approximate = 19.99;
long truncated = (long) approximate; // 19, bỏ phần lẻ
```

Các phép ép kiểu từ dấu phẩy động sang số nguyên còn có quy tắc riêng với NaN, vô cực và giá trị ngoài miền, vì vậy không dùng cast để xác nhận tiền hay số lượng.

Với `BigDecimal`, nên dùng các phép chuyển **đòi hỏi chính xác**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("123.00");

long whole = amount.longValueExact(); // 123
long invalid = new BigDecimal("123.45").longValueExact();
// ArithmeticException: có phần lẻ

BigDecimal exactTwoDigits =
        new BigDecimal("1.20").setScale(2, RoundingMode.UNNECESSARY);

BigDecimal invalidScale =
        new BigDecimal("1.234").setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException: cần làm tròn mới giảm scale được
```

Phép `setScale(2, RoundingMode.UNNECESSARY)` hữu ích ở **ranh giới nhập liệu** khi dữ liệu không được phép có nhiều hơn hai chữ số thập phân có ý nghĩa. Nếu nghiệp vụ **cho phép** làm tròn, hãy dùng chế độ đã được phê duyệt thay vì `UNNECESSARY`.

### Khi phép chia không có kết quả hữu hạn

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// one.divide(three) ném ArithmeticException vì 1/3 vô hạn tuần hoàn.

BigDecimal ratio = one.divide(three, 6, RoundingMode.HALF_EVEN);
// 0.333333, chính sách scale/rounding được thể hiện rõ
```

Không tự cắt các chữ số dư hoặc làm tròn ở nhiều tầng khác nhau, vì như vậy dữ liệu có thể bị thay đổi mà người gọi không biết.

## 6. Chọn biểu diễn theo loại dữ liệu

| Trường hợp | Phương án thường phù hợp | Rủi ro cần kiểm soát |
| --- | --- | --- |
| **Số lượng hàng nguyên** | `int`/`long` hoặc `BIGINT` theo miền | Overflow, số lượng âm, lost update khi ghi đồng thời |
| **Tiền theo đơn vị nhỏ nhất đã quy định** | `long`/`BIGINT` nếu miền đủ rộng | Nhầm đơn vị (đồng với cent), tràn khi nhân, tiền tệ có độ chia khác |
| **Tiền dạng số thập phân** | `BigDecimal` ↔ `DECIMAL(p,s)` | Scale, rounding, precision, quy tắc tiền tệ và thuế |
| **Lãi suất, tỷ lệ, phép tính tài chính** | `BigDecimal` với precision/scale trung gian được thiết kế | Làm tròn sớm, chia vô hạn, tính lãi theo thời đoạn |
| **Đo lường gần đúng** | `double`/`REAL` hoặc `DOUBLE PRECISION` theo sai số cho phép | Sai số nhị phân, NaN/vô cực, tích lũy sai số |
| **Đo lường có bước chính xác** | Số nguyên đã scale hoặc `BigDecimal` | Nhầm đơn vị, mức phân giải, chuyển đổi đơn vị |
| **Số thứ tự rất lớn** | `long` hoặc `BigInteger`; khi qua JSON cần xét an toàn của client | Mất chữ số ở client dùng IEEE 754 binary64 |
| **Mã bưu chính, số điện thoại, tài khoản, mã có số 0 đầu** | `String`/`VARCHAR` | Mất số 0 đầu, đổi định dạng, vượt miền số dù không cần phép toán |

Đừng chọn `BigDecimal` chỉ vì “luôn an toàn hơn”. `BigDecimal` không tự kiểm tra đơn vị, không ngăn kết quả âm hoặc sai quy tắc làm tròn, và không giải quyết đồng thời/transaction. Cũng không coi mọi phép đo `double` là sai: tính đúng đắn dựa trên **sai số được phép** và thiết kế thuật toán.

### Tiền và đơn vị nhỏ nhất

Nếu một hệ thống dùng **2 chữ số thập phân** cho một loại tiền và muốn lưu `19.99` thành số nguyên `1999`, hợp đồng cần ghi:

- `currency` có giá trị nào; một bản ghi tiền không nên thiếu tiền tệ.
- `amountMinorUnits` là **đơn vị nhỏ nhất do ứng dụng quy định**; không được tự giả định mọi loại tiền đều có 100 đơn vị nhỏ nhất.
- Khi nhân giá với số lượng hoặc cộng các khoản, phải kiểm tra overflow.
- Khi chuyển sang tiền của loại khác, cần tỷ giá, thời điểm, độ chính xác và quy tắc làm tròn được xác định riêng.

Đối với một hệ thống quản lý hóa đơn có nhiều tiền tệ, lưu `amount` và `currency` tách riêng; không cộng hai `amount` khác tiền tệ nếu chưa có quy tắc chuyển đổi.

## 7. Ví dụ Java + SQL: giữ số thập phân chính xác qua persistence

Giả sử miền nghiệp vụ yêu cầu **giá trị hóa đơn không âm, hai chữ số thập phân, tối đa 17 chữ số phần nguyên**. Ta có thể chọn `DECIMAL(19,2)` trong một database hỗ trợ kiểu này theo đúng ngữ nghĩa precision/scale. Đây là **yêu cầu ví dụ**, không phải quy tắc chung cho mọi giá trị tiền.

### 7.1. Thiết kế schema

```sql
CREATE TABLE invoice_amount (
    invoice_id UUID PRIMARY KEY,
    currency_code CHAR(3) NOT NULL,
    amount DECIMAL(19, 2) NOT NULL,
    CONSTRAINT ck_invoice_amount_nonnegative CHECK (amount >= 0)
);
```

`NOT NULL` và `CHECK` giải quyết hai điều kiện khác nhau: một biểu thức `CHECK (amount >= 0)` đơn lẻ không nên được dùng để thay cho `NOT NULL` vì SQL có logic ba giá trị. `CHAR(3)` ở đây minh họa mã tiền tệ ba ký tự; hợp lệ hay không vẫn phải kiểm tra theo danh sách và quy tắc nghiệp vụ.

`DECIMAL(19,2)` dành 17 chữ số phần nguyên và 2 chữ số phần lẻ trong cách định nghĩa thông dụng. Tuy nhiên, độ lớn tối đa cần kiểm thử trên chính hệ quản trị và schema thực tế.

### 7.2. Kiểu dữ liệu đầu vào và kiểm soát scale

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

record InvoiceMoney(BigDecimal amount, String currencyCode) {
    InvoiceMoney {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currencyCode, "currencyCode");

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Amount must be nonnegative");
        }
        if (!currencyCode.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid currency code format");
        }

        // Chỉ nhận giá trị biểu diễn chính xác ở hai chữ số thập phân.
        amount = amount.setScale(2, RoundingMode.UNNECESSARY);

        // Ví dụ ứng dụng giới hạn 17 chữ số phần nguyên.
        BigDecimal max = new BigDecimal("99999999999999999.99");
        if (amount.compareTo(max) > 0) {
            throw new IllegalArgumentException("Amount exceeds schema range");
        }
    }

    static InvoiceMoney fromText(String raw, String currencyCode) {
        // Chỉ chấp nhận cú pháp thập phân chuẩn; không parse qua double.
        if (raw == null || !raw.matches("(0|[1-9][0-9]*)(\\.[0-9]+)?")) {
            throw new IllegalArgumentException("Invalid decimal text");
        }
        return new InvoiceMoney(new BigDecimal(raw), currencyCode);
    }
}
```

Đoạn mã dùng `record` (Java 16 trở lên), chủ động **từ chối** dữ liệu cần làm tròn. Nó chỉ minh họa một miền giá trị có hai chữ số thập phân; với refund, số âm hoặc các loại tiền khác, domain cần kiểu và chính sách riêng. Biểu thức kiểm tra mã tiền tệ chỉ kiểm tra *hình dạng*, chưa chứng minh mã có thực hoặc phù hợp với loại giao dịch.

Đối với biểu diễn đầu vào `"001.20"`, ví dụ trên từ chối để buộc dạng chuẩn hóa. Nếu sản phẩm cho phép dấu cộng, dấu phân nhóm hoặc dấu phẩy thập phân theo locale, hãy parse ở lớp giao diện theo **locale đã biết** rồi chuyển về định dạng chuẩn; không đoán locale ở database.

### 7.3. Ghi bằng JDBC

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

final class InvoiceAmountWriter {
    private final DataSource dataSource;

    InvoiceAmountWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    void insert(UUID invoiceId, InvoiceMoney money) throws SQLException {
        String sql = """
                INSERT INTO invoice_amount (invoice_id, currency_code, amount)
                VALUES (?, ?, ?)
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setObject(1, invoiceId);
            ps.setString(2, money.currencyCode());
            ps.setBigDecimal(3, money.amount());
            ps.executeUpdate();
        }
    }
}
```

Ví dụ tập trung vào **đường chuyển kiểu và prepared statement**, giả định `DataSource` và driver đã cấu hình, transaction/autocommit được quản lý theo hợp đồng của ứng dụng. Nếu insert cần nằm cùng nhiều thao tác nguyên tử, phải đưa chúng vào **cùng transaction** và chỉ xác nhận thành công theo kết quả commit; `executeUpdate()` không tự chứng minh đã commit khi `autoCommit=false`.

Đường đọc tương ứng cần dùng `ResultSet.getBigDecimal("amount")` và tái kiểm tra invariant, **không** đọc bằng `getDouble()` rồi chuyển lại `BigDecimal`. Nếu ứng dụng dùng ORM, kiểm tra mapping thực tế và `precision/scale` của cột; annotation không thay thế migration/schema thật trên DB.

### 7.4. Phép kiểm tra round-trip

Một vòng round-trip số cần kiểm tra:

```text
Input text "19.99"
    → BigDecimal("19.99"), scale 2
    → JDBC setBigDecimal
    → DECIMAL(19,2) trong database
    → JDBC getBigDecimal
    → Output text "19.99"
```

Nếu giá trị đọc lại khác giá trị đã được chấp nhận, đó là lỗi hợp đồng dù SQL thành công. Với các giá trị phải chính xác, hãy so sánh bằng giá trị số và kiểm tra scale/format theo yêu cầu hiển thị riêng; không dùng `double` trung gian.

## 8. JSON, JavaScript và các hệ thống trung gian

JSON có kiểu `number` nhưng không ràng buộc mọi client phải dùng cùng biểu diễn số. Nhiều ứng dụng JavaScript dùng IEEE 754 binary64 cho `Number`; điều này ảnh hưởng số nguyên lớn và cả phép tính thập phân.

Ví dụ:

```javascript
const original = 9007199254740993n; // BigInt
const rounded = Number(original);

console.log(rounded);                // 9007199254740992
console.log(Number.isSafeInteger(rounded)); // false
```

Nếu một API gửi mã định danh hoặc số lượng nguyên rất lớn dưới dạng JSON number, client có thể **mất chữ số trước khi hiển thị hoặc gửi lại**, dù server Java và database vẫn lưu chính xác. Do đó:

- Với **ID**, thường dùng chuỗi để giữ nguyên định danh, kể cả số 0 đầu.
- Với **số nguyên có thể vượt ngưỡng an toàn của client**, dùng chuỗi thập phân hoặc một giao thức thống nhất hỗ trợ integer lớn.
- Với **số thập phân tài chính phải chính xác**, cân nhắc chuỗi dạng thập phân chuẩn, hoặc minor units có giới hạn được mô tả rõ và an toàn ở client.
- Phải công bố **đơn vị, miền giá trị, định dạng và cách xử lý khi số vượt giới hạn**. Việc đổi kiểu ở một API version có thể là breaking change.

Ví dụ hợp đồng API:

```json
{
  "invoiceId": "000123",
  "currency": "USD",
  "amount": "19.99",
  "balanceMinorUnits": "9007199254740993"
}
```

`invoiceId` là **định danh**, `amount` là **decimal dưới dạng văn bản chuẩn**, và `balanceMinorUnits` là **integer lớn dưới dạng văn bản**. Client cần parse chúng bằng thư viện decimal/BigInt có khả năng giữ chính xác và kiểm soát format. Đừng biến `"19.99"` thành `Number` rồi tiếp tục tính tiền nếu hợp đồng yêu cầu tính toán decimal chính xác.

### CSV, bảng tính và ETL cũng có thể làm mất giá trị

- `"000123"` có thể bị công cụ tự nhận là số và chuyển thành `123`.
- Chuỗi `"1,234"` có thể nghĩa là một nghìn hai trăm ba mươi bốn hoặc một phẩy hai ba bốn tùy locale.
- Giá trị `"1.234567890123456789"` có thể bị làm tròn khi qua công cụ dùng số thực nhị phân.
- Dữ liệu cột `DECIMAL(19,4)` xuất ra CSV rồi nhập vào cột `DECIMAL(19,2)` có thể bị làm tròn ở bước import.
- Giá trị bị thiếu có thể bị thay bằng `0`, làm sai dữ liệu dù không có lỗi kiểu số.

Đối với dữ liệu trao đổi, hãy mô tả **schema đầu vào/đầu ra** và kiểm tra khi nhập, thay vì giao cho công cụ tự suy đoán kiểu cột.

## 9. Nguy cơ khi chuyển kiểu, tổng hợp và tiến hóa schema

Các chuyển đổi gây mất dữ liệu thường nằm ngoài thao tác insert đơn lẻ:

| Chuyển đổi | Nguy cơ | Hướng xử lý |
| --- | --- | --- |
| `long → int` | Tràn hoặc đổi dấu khi vượt miền | `Math.toIntExact`, kiểm tra giới hạn |
| `BigDecimal → double` | Mất chữ số thập phân chính xác | Giữ `BigDecimal` hoặc dạng chuỗi trong đường dữ liệu chính xác |
| `DECIMAL(19,4) → DECIMAL(19,2)` | Làm tròn hoặc lỗi khi thay cột | Khảo sát dữ liệu, chọn chính sách rounding, backfill có kiểm tra |
| `BIGINT → INTEGER` | Dữ liệu hiện có vượt miền đích | Scan dữ liệu và dự báo tăng trưởng trước migration |
| `SUM`/`AVG` và phép chia | Kiểu kết quả, scale, overflow phụ thuộc engine/biểu thức | Ép kiểu có chủ đích, kiểm tra dữ liệu biên và cách JDBC nhận kết quả |
| Giá trị đo `kg → g` | Nhân hệ số có thể overflow hoặc tạo phần lẻ | Định nghĩa đơn vị, miền, rounding và lưu vết chuyển đổi |
| Số chính xác qua JSON/CSV | Client hoặc công cụ nhập làm tròn/đổi kiểu | Dùng string khi cần, schema rõ ràng, kiểm tra round-trip |
| `NULL → 0` | Mất phân biệt “không có dữ liệu” và “bằng không” | Áp dụng nullability/default theo nghiệp vụ |

### Bẫy của `SUM` và `AVG`

Một truy vấn như `AVG(quantity)` có thể trả về kiểu và scale khác nhau giữa các engine hoặc tùy kiểu cột. Không mặc định phép chia hai số nguyên sẽ cho kết quả thập phân đúng như ý. Hãy chọn kiểu và cách tính mong muốn, kiểm tra query result metadata/mapping, rồi thử dữ liệu biên.

Khi tổng hợp một triệu dòng, tổng có thể vượt miền `int` dù từng dòng đều hợp lệ. Chọn kiểu tích lũy đủ rộng hoặc dùng số nguyên/decimal lớn hơn; ở Java có thể dùng `Math.addExact` để nhận biết overflow thay vì chấp nhận tổng sai âm thầm.

### Migration thu hẹp scale không được xem là vô hại

Giả sử cột cũ `rate DECIMAL(12,6)` chuyển thành `DECIMAL(12,4)`. Trước khi thay schema:

1. Đếm bản ghi có trên 4 chữ số thập phân có ý nghĩa; phân biệt những chữ số thêm chỉ là `0`.
2. Xác định chính sách: từ chối migration, chấp nhận rounding, hay giữ dữ liệu gốc trong cột bổ sung.
3. Chạy chuyển đổi trên bản sao và đối chiếu số dòng, tổng, min/max, lỗi, những giá trị đã thay đổi.
4. Kiểm thử phiên bản ứng dụng cũ/mới và API/ETL liên quan trong thời gian rollout.
5. Xác định cách rollback và giữ dữ liệu gốc đủ lâu nếu phép chuyển làm mất thông tin.

Sau khi đã **cắt bỏ chữ số** hoặc chuyển qua kiểu gần đúng, đổi lại `DECIMAL` rộng hơn không tự phục hồi được những gì đã mất.

## 10. Kiểm thử hợp đồng số và tiêu chí nghiệm thu

Không thể chứng minh biểu diễn đúng chỉ bằng việc insert một giá trị bình thường. Các phép thử cần bao phủ đường đi qua **Java, driver, DB, API và consumer** ở nơi có chuyển đổi.

| Nhóm ca kiểm tra | Dữ liệu mẫu | Điều kiện đạt |
| --- | --- | --- |
| **Giá trị đơn giản** | `0`, `1`, `19.99` | Ghi và đọc lại cùng giá trị theo hợp đồng |
| **Biên precision** | `99999999999999999.99` với `DECIMAL(19,2)` | Chấp nhận nếu hợp lệ; giá trị lớn hơn bị từ chối rõ |
| **Biên scale** | `1.23`, `1.230`, `1.234` | Phân biệt thêm số 0 với giá trị cần làm tròn; hành vi được quy định |
| **Làm tròn** | `0.015 + 0.015` | Đúng chính sách “làm tròn từng dòng” hoặc “làm tròn cuối” |
| **Overflow** | `Integer.MAX_VALUE + 1`, `long` gần giới hạn | Không ghi giá trị sai; chuyển lỗi thành thông báo phù hợp |
| **Số âm/không có giá trị** | `−1`, `null`, `0` | Đúng quy tắc nghiệp vụ, không đồng nhất null với 0 |
| **Số gần đúng** | `0.1 + 0.2`, phép tính với số rất nhỏ | Sai số nằm trong ngưỡng đã định cho phép đo |
| **JSON integer lớn** | `9007199254740993` | Consumer không làm tròn ID/số nguyên phải chính xác |
| **Mã có số 0 đầu** | `"000123"` | Chuỗi vẫn giữ đủ ký tự sau import/export |
| **Migration schema** | `DECIMAL(12,6)` sang `DECIMAL(12,4)` | Báo cáo rõ mọi giá trị thay đổi, lỗi và cách phục hồi |
| **Tổng hợp dữ liệu lớn** | Nhiều dòng khiến tổng vượt `int` | Kiểu tổng đủ rộng; kiểm tra kết quả với dữ liệu tham chiếu |

Với `BigDecimal`, so sánh bằng `compareTo` khi chỉ quan tâm giá trị; nếu nghiệp vụ quan tâm đúng scale, hãy kiểm tra thêm `scale()`. Với `double`, dùng ngưỡng sai số theo ý nghĩa của phép đo. Với số nguyên và tiền chính xác, kiểm tra **bằng đúng giá trị**, không dùng dung sai.

### Một hợp đồng mẫu cho trường `invoice.amount`

```yaml
field: invoice.amount
meaning: "Giá trị hóa đơn không âm, tính theo đơn vị tiền chính"
java_type: BigDecimal
database_type: "DECIMAL(19,2)"
scale: 2
precision: 19
accepted_input: "Chuỗi thập phân chuẩn, không qua double"
rounding_on_input: "UNNECESSARY (từ chối nếu phải làm tròn)"
unit: "Kết hợp với currency_code của từng hóa đơn"
json_representation: "String, ví dụ \"19.99\""
round_trip_requirement: "Giữ nguyên giá trị số sau Java -> DB -> API"
overflow_behavior: "Từ chối trước ghi, đồng thời có constraint ở DB"
```

Đây là **hợp đồng minh họa**; số chữ số, quy tắc rounding và đơn vị phải do nghiệp vụ phê duyệt. Nếu cần tính thuế, chia tiền nhiều bên hoặc đổi ngoại tệ, phải bổ sung chính sách **thời điểm làm tròn và tính phần dư**; riêng `DECIMAL(19,2)` chưa giải quyết các phép tính đó.

## 11. Bài tập suy luận và thực hành

**Bài tập 1 — nhận biết sai số.** Một lập trình viên dùng `double` để cộng các giá trị tiền rồi gọi `BigDecimal.valueOf(result)` ngay trước khi lưu. Phương án này có đảm bảo kết quả đúng đến đồng/cent không?

*Gợi ý:* Không. Giá trị đã trải qua phép tính binary floating-point có thể mang sai số; việc đổi sang `BigDecimal` ở bước cuối không tái tạo kết quả decimal lý tưởng ban đầu. Hãy tính bằng `BigDecimal` từ chuỗi hoặc minor units ngay từ đầu.

**Bài tập 2 — chọn kiểu.** Bạn cần lưu: (a) số lượng sản phẩm nguyên có thể tới 3 tỷ, (b) số tài khoản `"001234567890"`, (c) mức nhiệt cảm biến sai số cho phép 0,1 °C, (d) giá tiền có hai chữ số thập phân. Đề xuất kiểu Java và SQL, nêu miền và phép kiểm tra.

*Gợi ý:* (a) cần vượt `int`, có thể dùng `long/BIGINT`; (b) `String/VARCHAR` để giữ số 0 đầu; (c) `double` có thể phù hợp nếu phân tích sai số, hoặc số nguyên theo 0,1 °C; (d) `BigDecimal/DECIMAL` hay minor units có hợp đồng rõ.

**Bài tập 3 — precision và scale.** Cột `DECIMAL(5,2)` được gán `999.99`, `1000.00` và `12.345`. Trường hợp nào hợp lệ về miền/scale? Điều gì có thể xảy ra với giá trị có thêm chữ số thập phân?

*Gợi ý:* `999.99` phù hợp, `1000.00` vượt precision. `12.345` cần giảm scale nên DB có thể làm tròn hoặc từ chối tùy engine/cấu hình; ứng dụng phải định nghĩa chính sách và kiểm chứng.

**Bài tập 4 — round-trip.** Server Java dùng `long` cho ID `9007199254740993`, serialize thành JSON number, ứng dụng JavaScript parse và gửi lại. Vì sao ID thay đổi? Làm thế nào để giữ nguyên?

*Gợi ý:* Số vượt giới hạn nguyên chính xác của `Number`. Truyền ID bằng chuỗi, không parse thành `Number`; nếu cần phép toán nguyên lớn, dùng `BigInt`/thư viện tương ứng.

**Bài tập 5 — làm tròn và tổng.** Hai dòng có giá trị `0.015`. So sánh tổng khi làm tròn mỗi dòng và khi làm tròn cuối theo `HALF_UP` với scale 2. Ai quyết định quy tắc áp dụng?

*Gợi ý:* Kết quả lần lượt `0.04` và `0.03`. Quy tắc là một phần của hợp đồng nghiệp vụ/kế toán được phê duyệt, không nên ngầm chọn theo framework.

**Thực hành có kiểm soát:** Trong môi trường thử nghiệm, tạo một bảng `DECIMAL(19,2)`, thử ghi bằng `BigDecimal` các giá trị biên, giá trị cần làm tròn và giá trị tràn miền; đọc lại bằng `getBigDecimal()`. Tiếp theo xuất qua JSON sang một client có `Number` và so sánh với dạng chuỗi. Lập bảng gồm **giá trị ban đầu, kiểu tại mỗi bước, giá trị sau round-trip, trạng thái pass/fail và nguyên nhân nếu khác**. Kết quả kiểm tra cần dựa trên DB/driver thực tế sẽ sử dụng.

## Ghi nhớ

**Dữ liệu đã được lưu bền vững vẫn có thể là một giá trị sai** nếu nó đã bị làm tròn, tràn số, thu hẹp kiểu hoặc đổi định dạng trước khi ghi. Muốn giữ đúng số trong ứng dụng Java, hãy xác định ý nghĩa, đơn vị, miền, precision, scale và quy tắc rounding từ nghiệp vụ; chọn `int/long`, `BigInteger`, `BigDecimal` hoặc `double` đúng với yêu cầu; kiểm soát chuyển kiểu tại Java–SQL–JSON–ETL; và kiểm tra round-trip cùng các giá trị biên. Đây là nền tảng để thiết kế schema, transaction và các luồng persistence đáng tin cậy.
