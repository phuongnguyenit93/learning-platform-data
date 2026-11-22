# Sai lầm: tạo `BigDecimal` từ `double` khi đầu vào cần chính xác thập phân

Một số giá trị như tiền, đơn giá, thuế suất, số liệu đo đã được quy định theo chữ số thập phân cần được giữ **đúng giá trị đã nhập**. Lỗi phổ biến trong Java là nhận chuỗi `"0.1"` nhưng chuyển thành `double` rồi mới tạo `BigDecimal`. Khi ấy ứng dụng có thể đã làm mất thông tin thập phân tại bước chuyển sang dấu phẩy động nhị phân. `BigDecimal` không thể tự suy đoán để khôi phục nguyên văn số mà người dùng gửi.

Bài này phân biệt `new BigDecimal(double)`, `BigDecimal.valueOf(double)` và `new BigDecimal(String)`; chỉ rõ trường hợp mỗi cách phù hợp, hậu quả khi đã qua `double`, cách kiểm soát `scale`/làm tròn và cách kiểm thử dữ liệu đầu vào chính xác trong Java 17+.

## 1. Vì sao `double` không biểu diễn chính xác mọi số thập phân?

`double` trong Java tuân theo kiểu dấu phẩy động nhị phân IEEE 754 binary64. Phần hữu hạn thông thường của nó có thể hiểu như một số nhị phân với độ chính xác hữu hạn. Các phân số có mẫu số chỉ chứa lũy thừa của 2, chẳng hạn `0.5` (1/2), `0.25` (1/4), có thể được biểu diễn chính xác. Nhưng `0.1` (1/10) không có biểu diễn hữu hạn trong hệ nhị phân, nên phải được **làm tròn đến giá trị `double` gần nhất**.

Ví dụ:

```java
double a = 0.1;
double b = 0.2;
System.out.println(a + b); // 0.30000000000000004
```

Đầu ra không phải do Java “cộng sai ngẫu nhiên”; đây là kết quả của biểu diễn và làm tròn trong phép tính nhị phân. Bản thân `double` được thiết kế rất hữu ích cho nhiều bài toán kỹ thuật và khoa học có sai số cho phép, nhưng nó **không phải kho lưu giữ nguyên văn các chữ số decimal**.

Có hai loại chính xác cần tách bạch:

- **Chính xác của giá trị nhị phân đang có:** Giá trị `double` cụ thể là một số hữu tỉ nhị phân xác định; có thể chuyển sang biểu diễn thập phân đầy đủ của **chính giá trị đó**.
- **Chính xác của số thập phân ban đầu:** Chuỗi `"0.1"` phải tương ứng đúng 1/10, hoặc chuỗi `"1.2300"` còn cần bảo toàn cả số chữ số phần lẻ theo hợp đồng.

Một khi chuỗi đầu vào được parse thành `double`, hai dạng thông tin trên không còn tương đương.

## 2. Bẫy chính: `new BigDecimal(double)`

Constructor nhận `double` tạo một `BigDecimal` có giá trị **chính xác bằng giá trị nhị phân mà `double` thực sự đang biểu diễn**, không phải giá trị thập phân ngắn thường được in trên màn hình:

```java
import java.math.BigDecimal;

BigDecimal fromDouble = new BigDecimal(0.1);
System.out.println(fromDouble.toPlainString());
```

Kết quả:

```text
0.1000000000000000055511151231257827021181583404541015625
```

Ở đây constructor làm đúng hợp đồng của nó: lưu chính xác giá trị `double` gần 0,1. Chính `double` đã xấp xỉ 1/10 trước khi constructor được gọi. Vì thế cách này **không phù hợp khi muốn giữ đúng số decimal `0.1`**.

So sánh:

```java
BigDecimal expected = new BigDecimal("0.1");
BigDecimal actual = new BigDecimal(0.1);

System.out.println(actual.compareTo(expected) == 0); // false
```

`actual` không bằng `expected` về **giá trị số**, chứ không đơn thuần khác `scale`. Điều này có thể làm kiểm tra giới hạn, so khớp số tiền, kiểm thử equality hay phân bổ số tiền cho kết quả bất ngờ.

Một số giá trị như `0.5` được biểu diễn chính xác bởi binary64, nên `new BigDecimal(0.5)` cho giá trị thập phân đúng `0.5`. Tuy nhiên, không nên suy từ một ví dụ may mắn để dùng constructor `double` cho mọi đầu vào decimal.

## 3. Đúng khi có văn bản nguồn: `new BigDecimal(String)`

Nếu dữ liệu gốc đang ở dạng chuỗi thập phân, hãy parse trực tiếp từ chuỗi:

```java
BigDecimal price = new BigDecimal("19.99");
BigDecimal rate = new BigDecimal("0.075");
BigDecimal value = new BigDecimal("0.1");
```

Các giá trị trên được tạo theo đúng chữ số thập phân trong chuỗi, không trải qua bước làm tròn binary64. Constructor này hỗ trợ dấu và dạng biểu diễn decimal hợp lệ theo cú pháp của `BigDecimal`; nó không tự xử lý mọi quy ước locale, dấu phân nhóm tiền tệ hoặc ký hiệu đơn vị.

Không có gì đặc biệt về **literal chuỗi**: chuỗi đọc từ HTTP body, tệp cấu hình, CSV hoặc một trường nhập liệu cũng thích hợp nếu đó là đại diện decimal gốc và đã được xác thực theo hợp đồng.

Ví dụ:

```java
BigDecimal left = new BigDecimal("0.1");
BigDecimal right = new BigDecimal("0.2");

System.out.println(left.add(right).toPlainString()); // 0.3
```

Không nên viết:

```java
BigDecimal wrong = new BigDecimal(Double.parseDouble("19.99"));
```

`Double.parseDouble` làm tròn theo binary64 trước, sau đó `BigDecimal` lưu chính xác **giá trị đã làm tròn**. Nếu yêu cầu là đọc chính xác `19.99`, parse thẳng bằng `new BigDecimal("19.99")`.

### So sánh ba cách tạo

| Cách tạo | Giá trị nhận vào | Điều nó bảo đảm | Khi phù hợp |
| --- | --- | --- | --- |
| `new BigDecimal("0.1")` | Chuỗi decimal | Giá trị decimal đúng như chuỗi, giữ scale theo biểu diễn | Dữ liệu gốc cần decimal chính xác |
| `new BigDecimal(0.1)` | `double` | Giá trị **nhị phân double hiện tại** được chuyển chính xác sang decimal | Cần phân tích/lưu chính xác giá trị binary64 đã có |
| `BigDecimal.valueOf(0.1)` | `double` | Chuyển qua biểu diễn `Double.toString(double)` rồi tạo decimal | Khi đầu vào thực sự chỉ có `double` và muốn decimal theo chuỗi hiển thị chuẩn |
| `new BigDecimal(Double.toString(d))` | Chuỗi chuẩn từ một `double` | Về giá trị tương đương đường chuyển thường dùng của `valueOf(d)` | Khi cần thể hiện rõ bước chuyển từ `double` |

Với dữ liệu gốc là chuỗi, **đừng đi qua `double`** chỉ để rồi gọi `valueOf`.

## 4. `BigDecimal.valueOf(double)` sửa được điều gì, không sửa được điều gì?

`BigDecimal.valueOf(double)` thường là lựa chọn tốt hơn `new BigDecimal(double)` **khi dữ liệu duy nhất bạn có thực sự là một `double`**. Nó dùng biểu diễn chuỗi chuẩn của `Double.toString(double)`, tức biểu diễn decimal ngắn cho phép round-trip trở lại cùng giá trị `double`:

```java
BigDecimal a = new BigDecimal(0.1);
BigDecimal b = BigDecimal.valueOf(0.1);

System.out.println(b.toPlainString()); // 0.1
System.out.println(a.compareTo(b) == 0); // false
```

`valueOf` loại bỏ dãy chữ số dài do biểu diễn nhị phân của ví dụ `0.1` và tạo decimal `0.1`. Nhưng **nó không bảo đảm khôi phục đầu vào decimal ban đầu** trong mọi trường hợp.

Ví dụ, chuỗi `"0.10000000000000001"` và `"0.1"` đều có thể được `Double.parseDouble` làm tròn về cùng giá trị `double`. Khi giá trị đã bị gộp, `BigDecimal.valueOf` không biết chuỗi nào đã xuất hiện ban đầu:

```java
String source = "0.10000000000000001";
double rounded = Double.parseDouble(source);

BigDecimal recovered = BigDecimal.valueOf(rounded);
BigDecimal original = new BigDecimal(source);

System.out.println(recovered.toPlainString()); // 0.1
System.out.println(original.toPlainString());  // 0.10000000000000001
```

Ngoài ra, nếu đã có phép tính dùng `double`, `valueOf` sẽ lưu lại decimal tương ứng với **kết quả tính binary64**:

```java
double computed = 0.1 + 0.2;
BigDecimal result = BigDecimal.valueOf(computed);

System.out.println(result.toPlainString()); // 0.30000000000000004
```

Chuyển đổi sau phép cộng không thể biến kết quả `double` thành một phép cộng decimal đúng 0,3. Muốn tính thập phân chính xác, phải chuyển sang `BigDecimal` **trước khi thực hiện phép toán** và có số decimal nguồn chính xác.

### `valueOf` cũng không bảo toàn định dạng văn bản ban đầu

`BigDecimal.valueOf(1.0)` được xây dựng từ chuỗi `"1.0"` của `Double.toString(1.0)`; nó không phân biệt liệu dữ liệu ban đầu là `"1"`, `"1.0"`, `"1.00"` hay `"1.000"`. Nếu số chữ số phần lẻ mang ý nghĩa nghiệp vụ, phải nhận và giữ giá trị đó qua văn bản gốc hoặc qua metadata riêng, không thể khôi phục từ một `double`.

## 5. Vì sao chuyển đổi muộn có thể phá hợp đồng thập phân?

Xét một API nhận thuế suất hoặc số tiền từ người dùng. Nếu đường đi là:

```text
"0.10000000000000001" (decimal gốc)
     ↓ Double.parseDouble
0.1 (double gần đúng, không còn ghi nhớ chuỗi gốc)
     ↓ BigDecimal.valueOf
0.1 (BigDecimal decimal)
```

kết quả cuối không còn đại diện cho toàn bộ thông tin decimal đã gửi. Hai chuỗi decimal khác nhau đã có thể tạo cùng một `double`, nên **không tồn tại thuật toán đảo ngược chung** để xác định chính xác chuỗi nào ban đầu.

Đường đi giữ chính xác:

```text
"0.10000000000000001" (decimal gốc)
     ↓ new BigDecimal(String)
0.10000000000000001 (BigDecimal)
     ↓ tính toán BigDecimal
Kết quả decimal theo hợp đồng toán học/rounding
```

Nhận diện điểm mất thông tin là quan trọng hơn việc chọn constructor ở cuối pipeline. Ngay cả khi cuối cùng cần `BigDecimal`, hãy kiểm tra kiểu của **mọi bước trước đó**: thư viện JSON, parser CSV, mapping DTO, JDBC, phép toán trung gian, hoặc getter trả `double`.

## 6. `scale`, `precision` và equality: hiểu cả giá trị lẫn biểu diễn

`BigDecimal` lưu giá trị thập phân như một số nguyên không tỉ lệ cùng với `scale`. Hai giá trị có thể bằng nhau về số học nhưng có `scale` khác nhau:

```java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.compareTo(y) == 0); // true
System.out.println(x.equals(y));         // false
System.out.println(y.scale());           // 2
```

`compareTo` so sánh **giá trị số**. `equals` xét cả **giá trị số và scale**, nên `"1.0"` và `"1.00"` không bằng nhau theo `equals`. `HashMap`/`HashSet` sử dụng `equals` và `hashCode`; `TreeMap`/`TreeSet` theo thứ tự tự nhiên dùng `compareTo`, vì vậy sự khác biệt này cũng ảnh hưởng đến xác định khóa trùng.

Khi parse trực tiếp từ `"1.00"`, scale 2 được giữ. Nếu parse qua `double`, thông tin về số chữ số phần lẻ gốc đã có thể mất.

Phân biệt:

- **Độ chính xác của giá trị:** decimal chính xác có bằng đại lượng gốc không?
- **`precision()` của `BigDecimal`:** số chữ số có nghĩa trong phần nguyên không tỉ lệ.
- **`scale()` của `BigDecimal`:** số chữ số theo lũy thừa 10 ở mẫu; scale có thể âm.
- **Độ phân giải nghiệp vụ:** chẳng hạn đơn vị nhỏ nhất là 0,01 hoặc 0,001.
- **Định dạng hiển thị:** dấu thập phân, dấu phân nhóm, số chữ số sau dấu và locale.

Không nên mặc định rằng một `BigDecimal` được tạo thành công là đã đáp ứng độ phân giải hoặc giới hạn của nghiệp vụ.

## 7. Hợp đồng làm tròn và kiểm tra độ phân giải

Nếu một trường tiền chỉ được phép có độ phân giải 0,01, có ít nhất hai chính sách:

**Chính sách từ chối giá trị không biểu diễn chính xác ở hai chữ số:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("12.30")
        .setScale(2, RoundingMode.UNNECESSARY);
```

Giá trị `"12.345"` sẽ khiến `setScale(2, RoundingMode.UNNECESSARY)` ném `ArithmeticException`, vì phải làm tròn để về hai chữ số. Giá trị `"12.300"` lại có thể chuyển chính xác thành `"12.30"`: bỏ số 0 cuối **không đổi giá trị số**. Điều này khác với hợp đồng bắt buộc **đúng hình thức hai chữ số trong chuỗi đầu vào**; hợp đồng về định dạng đó cần kiểm tra riêng.

**Chính sách cho phép làm tròn có quy tắc rõ ràng:**

```java
BigDecimal rounded = new BigDecimal("12.345")
        .setScale(2, RoundingMode.HALF_UP);
// rounded = 12.35
```

`HALF_UP` chỉ là một lựa chọn; nhiều bài toán cần `HALF_EVEN`, quy tắc pháp lý, hoặc từ chối mọi phép làm tròn. Nên ghi rõ **lúc nào** thực hiện rounding (mỗi dòng, tổng hóa đơn, bước xuất dữ liệu...) vì làm tròn ở các thời điểm khác nhau có thể cho kết quả khác nhau.

### `new BigDecimal(double, MathContext)` không khôi phục đầu vào

Có thể chỉ định `MathContext` để làm tròn giá trị được xây dựng từ `double` đến số chữ số có nghĩa nhất định. Tuy nhiên, giá trị xuất phát vẫn là binary64 đã xấp xỉ, nên đây không phải cách đảm bảo tái lập chuỗi decimal ban đầu. `MathContext` mô tả **chính sách precision và rounding**, không phải công cụ giải mã thông tin đã mất.

Nếu ứng dụng cần số đơn vị nhỏ dưới dạng `long`, nên chuyển từ decimal chính xác rồi dùng exact conversion:

```java
long cents = new BigDecimal("12.30")
        .movePointRight(2)
        .longValueExact(); // 1230
```

`movePointRight(2)` nhân 100 theo số học decimal; `longValueExact()` từ chối phần không nguyên hoặc giá trị ngoài miền `long`. Đừng thay bằng `longValue()` nếu không chấp nhận cắt phần lẻ hoặc bit cao.

## 8. Code Java 17+ hoàn chỉnh: so sánh đầu vào, conversion và giới hạn

Lưu chương trình sau thành **`BigDecimalFromDoubleDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalFromDoubleDemo {
    static BigDecimal parseExactAmount(String text) {
        if (text == null) {
            throw new IllegalArgumentException("amount is required");
        }
        BigDecimal amount = new BigDecimal(text)
                .setScale(2, RoundingMode.UNNECESSARY);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        return amount;
    }

    public static void main(String[] args) {
        BigDecimal fromDouble = new BigDecimal(0.1);
        BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
        BigDecimal fromText = new BigDecimal("0.1");

        System.out.println("ctor decimal = " + fromDouble.toPlainString());
        System.out.println("valueOf decimal = " + fromValueOf.toPlainString());
        System.out.println("text decimal = " + fromText.toPlainString());
        System.out.println("ctor equals numeric text = "
                + (fromDouble.compareTo(fromText) == 0));

        BigDecimal exactSum = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("exact sum = " + exactSum.toPlainString());
        System.out.println("double sum converted = "
                + BigDecimal.valueOf(0.1 + 0.2).toPlainString());

        String source = "0.10000000000000001";
        System.out.println("original = " + new BigDecimal(source).toPlainString());
        System.out.println("through double = "
                + BigDecimal.valueOf(Double.parseDouble(source)).toPlainString());

        BigDecimal scaled = new BigDecimal("1.00");
        System.out.println("scale = " + scaled.scale());
        System.out.println("numeric equal = "
                + (scaled.compareTo(new BigDecimal("1.0")) == 0));
        System.out.println("object equal = "
                + scaled.equals(new BigDecimal("1.0")));

        System.out.println("accepted amount = "
                + parseExactAmount("12.300").toPlainString());
        try {
            parseExactAmount("12.345");
            System.out.println("extra decimals = accepted");
        } catch (ArithmeticException ex) {
            System.out.println("extra decimals = rejected");
        }
        try {
            parseExactAmount("-0.01");
            System.out.println("negative = accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("negative = rejected");
        }

        long cents = parseExactAmount("12.30")
                .movePointRight(2)
                .longValueExact();
        System.out.println("cents = " + cents);
        System.out.println("half exact = " + new BigDecimal(0.5).toPlainString());
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 BigDecimalFromDoubleDemo.java
java BigDecimalFromDoubleDemo
```

Stdout:

```text
ctor decimal = 0.1000000000000000055511151231257827021181583404541015625
valueOf decimal = 0.1
text decimal = 0.1
ctor equals numeric text = false
exact sum = 0.3
double sum converted = 0.30000000000000004
original = 0.10000000000000001
through double = 0.1
scale = 2
numeric equal = true
object equal = false
accepted amount = 12.30
extra decimals = rejected
negative = rejected
cents = 1230
half exact = 0.5
```

Giải thích quan trọng:

1. Constructor nhận `double` cho ra biểu diễn decimal dài, chính xác của **binary64 0.1**, khác số decimal `0.1` trong văn bản.
2. `BigDecimal.valueOf(0.1)` cho giá trị decimal `0.1`, nhưng khi `0.1 + 0.2` được cộng trong `double` **trước khi gọi** `valueOf`, kết quả vẫn là `0.30000000000000004`.
3. Chuỗi `"0.10000000000000001"` bị mất các chữ số bổ sung khi đi qua `Double.parseDouble`, trong khi `new BigDecimal(source)` giữ nguyên giá trị decimal.
4. `"1.00"` và `"1.0"` bằng nhau về số học nhưng khác `equals` do scale.
5. Bộ parse nghiệp vụ dùng `setScale(2, UNNECESSARY)` để chuẩn hóa các giá trị có thể biểu diễn đúng theo phần trăm của đơn vị tiền; từ chối `"12.345"` và số âm.
6. `BigDecimal.valueOf(0.5)` hay `new BigDecimal(0.5)` không thể hiện bẫy vì 1/2 được biểu diễn chính xác trong nhị phân; không phải mọi phân số decimal đều như vậy.

## 9. Ranh giới JSON, database và các nguồn dữ liệu bên ngoài

**JSON:** JSON number là ký pháp thập phân trong văn bản, nhưng cách thư viện giải mã mới quyết định có mất dữ liệu không. Nếu serializer/deserializer đưa trường JSON decimal qua `double` trước khi tạo `BigDecimal`, độ chính xác có thể đã mất. Cấu hình parser để đọc token số decimal trực tiếp thành `BigDecimal` khi hợp đồng cần chính xác. Với đầu vào `{"amount": 0.10000000000000001}`, giữ kiểu decimal trong backend sẽ khác với dùng `double` làm bước trung gian.

**JavaScript:** `Number` sử dụng binary64. Khi JavaScript parse số JSON thành `Number`, nó có thể không giữ chính xác các chữ số decimal mà server mong muốn. Nếu giao thức yêu cầu giữ chính xác tiền/tỷ lệ hoặc số nguyên lớn, cần thỏa thuận biểu diễn (ví dụ **chuỗi thập phân** và thư viện decimal tương ứng) giữa frontend và backend. Đừng đổi tùy tiện một trường JSON number sang string khi client chưa có schema mới.

**Database/JDBC:** SQL `DECIMAL`/`NUMERIC` thường thích hợp cho decimal chính xác trong phạm vi schema. Khi đọc số decimal, dùng mapping/getter tương ứng `BigDecimal`; lấy qua `getDouble()` có thể làm tròn trước khi convert. Ngược lại, dữ liệu trong cột dấu phẩy động `FLOAT`/`DOUBLE` đã có thể bị xấp xỉ khi ghi, dù ứng dụng nhận bằng `BigDecimal`.

**CSV/Excel:** Cột số có thể đã được nhập, lưu hoặc tính dưới dạng dấu phẩy động trong một công cụ khác. Nếu file đã mất chữ số khi lưu số dạng binary64, parse sang `BigDecimal` ở bước nhập Java **không thể khôi phục lại nguồn gốc**. Với tệp CSV chứa nguyên chuỗi decimal, parse trực tiếp từ trường văn bản và xác định rõ dấu thập phân/locale.

**Tích hợp API:** Nếu chữ số sau dấu thập phân là một phần của hợp đồng, cần nói rõ trong tài liệu JSON/CSV/DTO: đơn vị, miền, scale tối đa, có cho phép dạng exponent không, có chấp nhận số 0 ở cuối không, làm tròn hay từ chối khi quá độ phân giải. Cả hai phía cần cùng một quy tắc parse và validate.

## 10. Chọn API theo nguồn gốc dữ liệu

| Nguồn đầu vào | Nên làm gì | Tránh |
| --- | --- | --- |
| Chuỗi decimal do người dùng nhập | `new BigDecimal(text)` rồi validate miền/scale | `Double.parseDouble(text)` trước |
| Hằng số decimal cần chính xác | `new BigDecimal("0.1")` | `new BigDecimal(0.1)` |
| Đã có `double` hợp lệ từ phép đo | Cân nhắc `BigDecimal.valueOf(d)` nếu cần decimal theo `Double.toString(d)` | Tưởng `valueOf` khôi phục số decimal nguyên thủy |
| Muốn biết chính xác giá trị binary64 đã lưu | `new BigDecimal(d)` | Nhầm với biểu diễn decimal gốc |
| Kết quả `double` đã được tính toán | Giữ nguyên ý nghĩa xấp xỉ hoặc tính lại từ nguồn decimal | Chỉ gọi `valueOf` ở cuối rồi tin phép tính chính xác |
| Decimal có độ phân giải cố định | `setScale(scale, UNNECESSARY)` để từ chối rounding, hoặc mode tường minh | `setScale(scale)` rồi bỏ qua ngoại lệ/rounding |
| Số tiền dạng đơn vị nhỏ nguyên | Parse decimal đúng → nhân theo thang decimal → `longValueExact()` | Nhân bằng `double` rồi cast sang `long` |
| JSON/SQL decimal | Giữ ánh xạ decimal trực tiếp qua ranh giới | Đi qua kiểu `double` trung gian |
| Đầu vào đã là số nguyên | `BigDecimal.valueOf(longValue)` hoặc `new BigDecimal(BigInteger)` | Đổi số nguyên lớn thành `double` trước |

`BigDecimal.valueOf(long)` là một overload khác với `BigDecimal.valueOf(double)`: khi đầu vào là `long`, giá trị nguyên được chuyển **chính xác**, không qua binary64. Đây là lựa chọn phù hợp khi đầu vào vốn là số nguyên cần biểu diễn dạng decimal.

## 11. Kiểm thử phát hiện sự cố chuyển đổi

Các ca kiểm thử nên được thiết kế từ **chuỗi nguồn và miền nghiệp vụ**, không chỉ từ kết quả của cùng một parser đã bị lỗi.

| Ca kiểm thử | Cách tạo | Điều cần khẳng định |
| --- | --- | --- |
| Phân số không biểu diễn đúng bằng nhị phân | `"0.1"` | `new BigDecimal("0.1")` giữ giá trị; `new BigDecimal(0.1)` khác |
| Phân số biểu diễn được bằng nhị phân | `"0.5"` | Constructor `double` tình cờ khớp |
| Phép cộng decimal | `"0.1" + "0.2"` | `BigDecimal.add` trên chuỗi cho `0.3` |
| Phép cộng binary64 rồi mới convert | `BigDecimal.valueOf(0.1 + 0.2)` | `0.30000000000000004` |
| Thông tin decimal mất khi parse double | `"0.10000000000000001"` | Parse chuỗi trực tiếp giữ nguyên decimal |
| Scale khác nhau | `"1.0"` và `"1.00"` | `compareTo == 0` nhưng `equals == false` |
| Dư độ phân giải | `"12.345"` với scale 2 | Từ chối hoặc làm tròn đúng theo hợp đồng |
| Có số 0 cuối | `"12.300"` với scale 2 | Chuẩn hóa thành `12.30` mà không đổi giá trị |
| Giá trị âm ngoài miền | `"-0.01"` trong trường không âm | Từ chối sau khi parse |
| Ký hiệu không hợp lệ | `"12,34"` với parser không locale | Không tự hiểu dấu phẩy decimal |
| Giá trị vượt miền nguyên nhỏ | Số cent vượt `long` | `longValueExact()` ném |
| Giá trị NaN/vô cực | `Double.NaN`, `Infinity` | Không có giá trị `BigDecimal` thông thường tương ứng |

Nếu phải chuyển `BigDecimal` sang `double`, hãy kiểm tra rủi ro mất precision ở chiều ngược lại. `bigDecimal.doubleValue()` có thể trả một giá trị xấp xỉ hoặc vô cực với đầu vào đủ lớn; nếu hợp đồng cấm mất độ chính xác, không được dùng conversion này làm bước vô hại.

Các kiểm thử tích hợp nên bao trùm cả đường đi đầu-cuối: từ literal JSON/CSV/database qua DTO, domain model, phép tính, đến dữ liệu được serialize trả lại. Nếu trong bất kỳ khâu nào đầu vào bị chuyển thành `double`, xác minh xem đó là quyết định chấp nhận sai số có chủ đích hay là lỗi thiết kế.

## 12. Những sai lầm thường gặp

1. **Dùng `new BigDecimal(0.1)` vì tưởng constructor sẽ giữ giá trị decimal 0,1.** Constructor thực sự lưu chính xác giá trị binary64 gần 0,1.
2. **Tin `BigDecimal.valueOf(d)` luôn khôi phục đầu vào decimal.** Nó dựa trên `Double.toString(d)`; nếu dữ liệu đã bị làm tròn thành `double`, thông tin nguồn không thể phục hồi.
3. **Tính bằng `double` trước, đổi sang `BigDecimal` sau.** Các sai số và kết quả làm tròn trước đó vẫn tồn tại trong biểu diễn decimal của kết quả.
4. **Đi từ chuỗi → `double` → `BigDecimal`.** Thêm bước binary64 không cần thiết và có thể đánh mất chữ số.
5. **Nhầm `compareTo` với `equals`.** Cùng giá trị thập phân nhưng khác `scale` có thể khác nhau theo `equals`; ngược lại giá trị từ constructor `double` có thể khác thật cả về số.
6. **Cho rằng `setScale` là cách phục hồi chính xác decimal.** Làm tròn có thể cho một số trông giống mong muốn nhưng không chứng minh được chữ số gốc.
7. **Dùng `BigDecimal.valueOf(1.0)` rồi tưởng nhớ được chuỗi `"1.000"` đã nhập.** `double` không lưu biểu diễn văn bản.
8. **Không quy định lỗi phần thập phân thừa.** Một API vô tình làm tròn có thể thay đổi giá trị nghiệp vụ.
9. **Không xem xét JSON/JDBC/front-end.** Dù Java dùng `BigDecimal`, một thư viện trung gian dùng `double` vẫn có thể gây mất decimal.
10. **Dùng `double` là sai trong mọi ngữ cảnh.** Điều này cũng không đúng: `double` có giá trị sử dụng trong tính toán xấp xỉ. Lỗi nằm ở việc dùng nó **khi hợp đồng yêu cầu decimal chính xác từ đầu vào**.

## 13. Quy tắc áp dụng

Khi đọc dữ liệu thập phân cần chính xác, **giữ biểu diễn decimal từ nguồn và tạo `BigDecimal` trực tiếp từ chuỗi hoặc kiểu decimal chính xác**. Chỉ dùng `BigDecimal.valueOf(double)` khi nguồn thực sự là `double` và cần decimal theo cách biểu diễn chuẩn của nó. Dùng `new BigDecimal(double)` khi muốn biết chính xác giá trị nhị phân hiện có, không phải khi muốn tái tạo ý nghĩa thập phân của người nhập.

Sau khi parse, kiểm tra miền, độ phân giải, rounding và `null` theo hợp đồng. Tính toán bằng API `BigDecimal` phù hợp, tránh conversion trung gian qua `double`, và dùng phép chuyển **exact** khi đưa về kiểu số nguyên. Điều quan trọng nhất là phát hiện bước đầu tiên làm mất thông tin; các phép chuyển đổi được thêm sau bước ấy không thể thay thế độ chính xác vốn đã mất.

### Tài liệu chính thức

- [`BigDecimal` — constructor, `valueOf`, scale, rounding](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [`Double` — `toString`, `parseDouble`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html)
- [`RoundingMode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html)
- [JLS §4.2.3 — Floating-point types and values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3)