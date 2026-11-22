# Chuỗi thập phân sang `BigDecimal` để giữ ý nghĩa thập phân trong Java

## 1. Vì sao cần parse chuỗi thập phân bằng `BigDecimal`?

Khi người dùng nhập `"0.1"`, dữ liệu ban đầu là **chuỗi biểu diễn một phần mười trong hệ thập phân**. Nếu lập trình viên chuyển chuỗi đó sang `double`, giá trị được lưu thường chỉ là **số nhị phân gần nhất có thể biểu diễn**, không phải đúng một phần mười về mặt toán học.

Java có hai cách xử lý rất khác nhau:

~~~java
double binary = Double.parseDouble("0.1");
BigDecimal decimal = new BigDecimal("0.1");
~~~

Đây là đoạn minh họa; cần `import java.math.BigDecimal;` khi đặt vào class.

- `binary` là giá trị `double` gần `0.1` nhất theo quy tắc của binary64.
- `decimal` là giá trị thập phân **chính xác** `0.1`: phần nguyên chưa được scale là 1, `scale` là 1, tương đương `1 × 10^-1`.

`BigDecimal` đặc biệt hữu ích cho dữ liệu có **ý nghĩa thập phân từ nguồn**: đơn giá, số tiền, thuế, tỷ lệ kinh doanh, dữ liệu xuất nhập dạng CSV/JSON chứa số thập phân, hoặc yêu cầu so sánh/kiểm toán chính xác theo chữ số.

**Cốt lõi:** Nếu nguồn là chuỗi thập phân, tạo trực tiếp bằng **`new BigDecimal(text)`**. Đừng buộc dữ liệu đi qua `double` nếu cần giữ đúng ý nghĩa thập phân gốc.

~~~java
BigDecimal sum = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));
// sum.toString() bằng "0.3"
~~~

Phép cộng ở đây giữ chính xác giá trị thập phân vì hai đầu vào được parse trực tiếp, không có sai số nhị phân trung gian. Nhưng cần hiểu rõ rằng `BigDecimal` **không tự giúp mọi phép chia ra số hữu hạn**, cũng không thể tự khôi phục một giá trị thập phân đã bị thay đổi trước đó.

## 2. `BigDecimal` lưu số theo cấu trúc nào?

`java.math.BigDecimal` là một lớp **bất biến** (*immutable*), biểu diễn số thập phân với độ chính xác tùy ý trong giới hạn tài nguyên và ràng buộc của API.

Có thể hiểu giá trị của một `BigDecimal` bằng:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Trong đó:

- `unscaledValue()` là số nguyên `BigInteger` mang toàn bộ chữ số của hệ số.
- `scale()` là số nguyên chỉ **số chữ số ở bên phải dấu thập phân** nếu dương; `scale` cũng có thể bằng 0 hoặc âm.
- `precision()` là **số chữ số thập phân có nghĩa của phần hệ số** theo định nghĩa của `BigDecimal`, không phải số chữ số sau dấu chấm.

Ví dụ:

| Chuỗi nhập | Giá trị thập phân | `unscaledValue()` | `scale()` | `precision()` |
|---|---:|---:|---:|---:|
| `"123.45"` | 123.45 | 12345 | 2 | 5 |
| `"0.1"` | 0.1 | 1 | 1 | 1 |
| `"1.20"` | 1.20 | 120 | 2 | 3 |
| `"1000"` | 1000 | 1000 | 0 | 4 |
| `"1E+3"` | 1000 | 1 | -3 | 1 |
| `"0.00"` | 0.00 | 0 | 2 | 1 |

**Ví dụ quan trọng:** `new BigDecimal("1.20")` và `new BigDecimal("1.2")` có cùng **giá trị toán học 1.2**, nhưng có **scale khác nhau** (2 và 1), vì thế có thể khác về định dạng và phương thức so sánh đối tượng.

`BigDecimal` không phải một kiểu số dấu phẩy động IEEE 754 như `double`. Nó dựa trên hệ số nguyên và lũy thừa 10, nên có thể biểu diễn chính xác nhiều phân số thập phân hữu hạn mà binary64 không thể.

## 3. Ba cách tạo từ dữ liệu — kết quả khác nhau

### 3.1. `new BigDecimal(String)`: cách đúng cho nguồn chữ số thập phân

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("12.3400");
BigDecimal c = new BigDecimal("-7.25");
~~~

Những chuỗi được parse trực tiếp theo cú pháp số thập phân mà `BigDecimal` hỗ trợ. `b` giữ scale 4, nên `b.toString()` thường in `12.3400`; đối tượng không tự ý bỏ các số 0 cuối.

### 3.2. `new BigDecimal(double)`: giữ **chính xác giá trị nhị phân** đã có

~~~java
BigDecimal fromBinary = new BigDecimal(0.1);
~~~

`double` chứa một giá trị nhị phân gần 0.1 nhưng **không đúng bằng** 0.1 toán học. Constructor nhận `double` chuyển **giá trị double đang lưu** thành một `BigDecimal` chính xác đối với *double đó*, nên nó hiện rõ phần sai lệch nhị phân:

~~~text
0.1000000000000000055511151231257827021181583404541015625
~~~

Đây không phải lỗi của `BigDecimal`. Dữ liệu đã bị xấp xỉ ngay từ bước tạo `double`.

### 3.3. `BigDecimal.valueOf(double)`: dựa trên biểu diễn thập phân của `double`

~~~java
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
~~~

`valueOf(double)` sử dụng biểu diễn thập phân dạng chuỗi do `Double.toString(double)` tạo ra, rồi chuyển thành `BigDecimal`. Vì `Double.toString(0.1)` là `"0.1"`, kết quả ở ví dụ này có `toString()` bằng `"0.1"`.

**Nhưng `BigDecimal.valueOf(double)` không thể khôi phục toàn bộ dữ liệu thập phân gốc** nếu phép tính dùng `double` đã thay đổi giá trị:

~~~java
double sum = 0.1 + 0.2;
BigDecimal afterDouble = BigDecimal.valueOf(sum);
// afterDouble là 0.30000000000000004, không phải đúng 0.3
~~~

Nhớ quy tắc:

- **Nguồn là `String` thập phân:** dùng `new BigDecimal(text)`.
- **Nguồn thực sự đã là `double`:** hiểu rõ dữ liệu đã có sai số/rounding; `valueOf(double)` thường tạo dạng thập phân dễ đọc, nhưng không đảo ngược lịch sử phép toán.
- **`new BigDecimal(double)`:** chỉ chọn khi thật sự cần chuyển chính xác **giá trị binary64 hiện tại** sang thập phân, không phải vì muốn “tránh sai số”.

## 4. Ví dụ Java 17+ chạy độc lập: so sánh ba cách tạo

Tạo tệp `DecimalConstructionDemo.java`:

~~~java
import java.math.BigDecimal;

public class DecimalConstructionDemo {
    public static void main(String[] args) {
        String source = "0.1";

        BigDecimal exact = new BigDecimal(source);
        BigDecimal fromDouble =
                new BigDecimal(Double.parseDouble(source));
        BigDecimal viaValueOf =
                BigDecimal.valueOf(Double.parseDouble(source));

        System.out.println("text=" + exact);
        System.out.println("doubleConstructor=" + fromDouble);
        System.out.println("valueOfDouble=" + viaValueOf);
        System.out.println("binarySum=" + (0.1 + 0.2));
        System.out.println("decimalSum="
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));
        System.out.println("valueOfBinarySum="
                + BigDecimal.valueOf(0.1 + 0.2));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac DecimalConstructionDemo.java
java DecimalConstructionDemo
~~~

Đầu ra:

~~~text
text=0.1
doubleConstructor=0.1000000000000000055511151231257827021181583404541015625
valueOfDouble=0.1
binarySum=0.30000000000000004
decimalSum=0.3
valueOfBinarySum=0.30000000000000004
~~~

Dòng `decimalSum` mới là ví dụ giữ **ý nghĩa thập phân của hai chuỗi gốc**. Dòng `valueOfBinarySum` chỉ làm tròn chuỗi biểu diễn của **kết quả double đã được tính**; nó không sửa được sai số của phép cộng thực hiện trước đó.

## 5. Cú pháp chuỗi hợp lệ cho `BigDecimal`

`new BigDecimal(String)` chấp nhận văn bản số thập phân theo ngữ pháp của `BigDecimal`, bao gồm dấu tùy chọn, dấu chấm thập phân và ký pháp số mũ `e`/`E`.

Ví dụ hợp lệ:

~~~java
new BigDecimal("42");        // 42
new BigDecimal("+42.00");    // 42.00
new BigDecimal("-0.125");    // -0.125
new BigDecimal(".5");        // 0.5
new BigDecimal("5.");        // 5
new BigDecimal("1.23E+4");   // 12300
new BigDecimal("1e-3");     // 0.001
~~~

Đây là các lời gọi minh họa. Các dạng trên có thể có **scale** khác nhau; ví dụ `"1.23E+4"` có hệ số 123 và scale -2, giá trị 12300.

**Không nhầm** parser runtime với các biểu thức literal Java. Các dạng sau là lỗi định dạng nếu truyền trực tiếp cho `new BigDecimal(text)`:

- `"1_000.50"`: gạch dưới hợp lệ trong một số literal Java, **không phải** chữ số thập phân trong chuỗi parse.
- `"1,234.50"` hoặc `"1.234,50"`: dấu phân nhóm hay dấu phẩy thập phân theo locale **không được hiểu tự động** bởi constructor này.
- `" 12.34 "`: khoảng trắng đầu/cuối không được tự trim.
- `""`, `"+"`, `"."`: không có dãy chữ số hợp lệ.
- `"NaN"`, `"Infinity"`: không phải giá trị thập phân `BigDecimal` có thể biểu diễn.
- `"0x1.8p2"`: không phải cú pháp số thập phân của constructor này.

Các chuỗi không hợp lệ thường dẫn tới `NumberFormatException`. Nếu nguồn có thể là `null`, cần kiểm tra `null` riêng trước khi parse; không coi nó tương đương chuỗi `"0"`.

### Có thể dùng `trim()` không?

Nếu hợp đồng dữ liệu cho phép khoảng trắng đầu/cuối, bạn **có thể chủ động** gọi `text.trim()` hoặc `strip()` trước khi parse. Tuy nhiên, đây là **quyết định chuẩn hóa dữ liệu**. Trong hệ thống yêu cầu định dạng chặt (mã giao dịch, tài chính, ký số), nên từ chối đầu vào không đúng thay vì âm thầm thay đổi.

Các chuỗi hiển thị số theo locale cần một bước xử lý riêng: quy định rõ dấu thập phân, dấu tách hàng nghìn, nhóm số và cách kiểm tra. Đừng tùy tiện thay mọi dấu `,` bằng `.` vì `"1,234"` có thể nghĩa là 1234 hoặc 1.234 tùy locale.

## 6. Ví dụ Java 17+: parse và báo lỗi rõ ràng

Tạo tệp `DecimalInputValidationDemo.java`:

~~~java
import java.math.BigDecimal;

public class DecimalInputValidationDemo {
    static void parse(String input) {
        try {
            BigDecimal value = new BigDecimal(input);
            System.out.println("ok[" + input + "]="
                    + value.toPlainString());
        } catch (NumberFormatException ex) {
            System.out.println("bad[" + input + "]");
        }
    }

    public static void main(String[] args) {
        parse("42");
        parse("+42.00");
        parse("1.23E+4");
        parse("0.001");
        parse("1_000.50");
        parse("1,234.50");
        parse(" 12.34 ");
        parse("NaN");
        parse("");
    }
}
~~~

~~~bash
javac DecimalInputValidationDemo.java
java DecimalInputValidationDemo
~~~

Đầu ra:

~~~text
ok[42]=42
ok[+42.00]=42.00
ok[1.23E+4]=12300
ok[0.001]=0.001
bad[1_000.50]
bad[1,234.50]
bad[ 12.34 ]
bad[NaN]
bad[]
~~~

Hàm `parse` chỉ dùng dữ liệu ví dụ nên đầu vào luôn là chuỗi không `null`. Khi xử lý dữ liệu bên ngoài, kiểm tra `null` trước và đặt giới hạn độ dài/số chữ số/số mũ phù hợp yêu cầu hệ thống. `BigDecimal` không bị giới hạn bởi độ chính xác 53 bit như `double`, nhưng vẫn có **giới hạn tài nguyên, miền `int` của scale và độ dài tính toán**.

Nếu cần báo lỗi nhập liệu, hãy ghi rõ trường nào sai và định dạng được phép; đừng che giấu lỗi bằng `catch (Exception)` rồi trả về một số 0 mặc định.

## 7. Từ chuỗi đã parse đến phép tính thập phân chính xác

`BigDecimal` hỗ trợ các phép toán qua **phương thức** chứ không dùng các toán tử `+`, `-`, `*`, `/` trực tiếp trên đối tượng:

| Phép toán | Ví dụ `BigDecimal` | Ý nghĩa |
|---|---|---|
| Cộng | `a.add(b)` | Tổng số thập phân |
| Trừ | `a.subtract(b)` | Hiệu số thập phân |
| Nhân | `a.multiply(b)` | Tích số thập phân |
| Chia | `a.divide(b)` | Thương chính xác **chỉ khi biểu diễn được theo dạng thập phân hữu hạn** nếu không quy định làm tròn |
| So sánh số học | `a.compareTo(b)` | So sánh **giá trị số** |
| Đổi dấu | `a.negate()` | Số đối |
| Đặt scale | `a.setScale(2, RoundingMode.HALF_UP)` | Chọn số chữ số sau dấu chấm theo quy tắc làm tròn |

Các phương thức như `add`, `subtract`, `multiply` với **không có `MathContext` giới hạn độ chính xác** cho kết quả chính xác về giá trị thập phân trong giới hạn thực tế và API. Nếu cung cấp `MathContext` hoặc gọi `setScale` với chế độ làm tròn, kết quả **có thể bị làm tròn theo chính sách được chọn**.

### Vì sao dùng toán tử trực tiếp không được?

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
// BigDecimal wrong = a + b; // Lỗi biên dịch: không có toán tử + cho BigDecimal
BigDecimal right = a.add(b);
~~~

Đây là đoạn minh họa. `BigDecimal` là class, không phải primitive numeric type. Ngoại lệ thường gặp là toán tử `+` với `String` tạo nối chuỗi, nhưng điều đó **không phải phép cộng số**.

### `BigDecimal` là immutable

~~~java
BigDecimal total = new BigDecimal("1.20");
total.add(new BigDecimal("0.30"));  // Không sửa total!
total = total.add(new BigDecimal("0.30")); // total thành 1.50
~~~

Mỗi phép toán trả **đối tượng kết quả**. Quên gán lại là một lỗi logic phổ biến: lệnh `total.add(...)` riêng lẻ không thay đổi biến `total`.

## 8. Phép chia và quy tắc làm tròn: vấn đề riêng với `BigDecimal`

Kết quả `1 ÷ 3` là số thập phân vô hạn tuần hoàn. Không tồn tại `BigDecimal` hữu hạn nào biểu diễn chính xác toàn bộ thương đó. Vì vậy:

~~~java
BigDecimal one = new BigDecimal("1");
BigDecimal three = new BigDecimal("3");
// one.divide(three); // Ném ArithmeticException vì khai triển không kết thúc.
~~~

Muốn nhận kết quả thực dụng, chỉ định scale và `RoundingMode`:

~~~java
BigDecimal quotient = one.divide(three, 4, RoundingMode.HALF_UP);
// quotient = 0.3333
~~~

Đây là đoạn minh họa; cần import `java.math.RoundingMode`.

**Phân biệt rất quan trọng:**

- **Parse chuỗi**: `new BigDecimal("0.1")` giữ đúng số mà chuỗi biểu diễn.
- **Cộng/trừ/nhân không giới hạn precision**: giữ đúng giá trị thập phân toán học khi kết quả trong khả năng biểu diễn.
- **Chia không kết thúc**: cần chọn rounding/precision hoặc để API ném lỗi.
- **Làm tròn nghiệp vụ**: cần chính sách `scale`, `precision` và `RoundingMode`; “dùng BigDecimal” **không tự quyết định chính sách ấy**.

### `setScale` và `MathContext` không giống nhau

- `setScale(2, HALF_UP)` đặt **hai chữ số sau dấu chấm thập phân**, có thể làm tròn giá trị.
- `MathContext(4, HALF_UP)` giới hạn **4 chữ số có nghĩa của toàn bộ hệ số**, không đồng nghĩa 4 chữ số thập phân sau dấu chấm.
- `RoundingMode.UNNECESSARY` yêu cầu không cần làm tròn; nếu phép chuyển phải bỏ chữ số có ý nghĩa, ném `ArithmeticException`.

Ví dụ số `"123.456"`:
- `setScale(2, HALF_UP)` cho `123.46`.
- `round(new MathContext(4, HALF_UP))` cho `123.5`.

Quy tắc nào đúng phụ thuộc nghiệp vụ. Với khoản tiền, thường thống nhất cả đơn vị tiền tệ, số chữ số thập phân, cơ chế làm tròn thuế/phí và thời điểm làm tròn.

## 9. Ví dụ Java 17+: cộng, nhân, chia và làm tròn

Tạo tệp `DecimalArithmeticDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class DecimalArithmeticDemo {
    public static void main(String[] args) {
        BigDecimal price = new BigDecimal("19.95");
        BigDecimal quantity = new BigDecimal("3");
        BigDecimal total = price.multiply(quantity);

        System.out.println("total=" + total);
        System.out.println("sum="
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));
        System.out.println("exactDivision="
                + new BigDecimal("1").divide(new BigDecimal("4")));
        System.out.println("roundedDivision="
                + new BigDecimal("1").divide(
                        new BigDecimal("3"), 4, RoundingMode.HALF_UP));

        BigDecimal sample = new BigDecimal("2.345");
        System.out.println("halfUp="
                + sample.setScale(2, RoundingMode.HALF_UP));
        System.out.println("halfEven="
                + sample.setScale(2, RoundingMode.HALF_EVEN));
        System.out.println("signAware="
                + new BigDecimal("-2.345").setScale(
                        2, RoundingMode.HALF_UP));

        BigDecimal precise = new BigDecimal("123.456");
        System.out.println("scale2="
                + precise.setScale(2, RoundingMode.HALF_UP));
        System.out.println("precision4="
                + precise.round(new MathContext(
                        4, RoundingMode.HALF_UP)));
    }
}
~~~

~~~bash
javac DecimalArithmeticDemo.java
java DecimalArithmeticDemo
~~~

Đầu ra:

~~~text
total=59.85
sum=0.3
exactDivision=0.25
roundedDivision=0.3333
halfUp=2.35
halfEven=2.34
signAware=-2.35
scale2=123.46
precision4=123.5
~~~

Dòng `halfUp` và `halfEven` khác nhau do cách xử lý trường hợp giá trị chính giữa hai lựa chọn. Với `2.345` ở scale 2, `HALF_UP` cho `2.35`, còn `HALF_EVEN` cho `2.34` vì chữ số cuối của kết quả 2.34 là chẵn.

**Không giả định quy tắc “làm tròn đến hai chữ số” mặc định luôn là `HALF_UP`**. Nếu một hệ thống cần `HALF_EVEN`, `DOWN`, `CEILING` hay quy tắc khác, phải truyền `RoundingMode` phù hợp.

## 10. `equals` và `compareTo`: khác biệt vì scale

Hai đối tượng `BigDecimal` có thể có **giá trị số bằng nhau** nhưng **khác scale**:

~~~java
BigDecimal a = new BigDecimal("1.20");
BigDecimal b = new BigDecimal("1.2");

a.equals(b);                // false
a.compareTo(b) == 0;        // true
~~~

`equals` xét cả **giá trị không scale và scale**, nên ở đây trả `false`. `compareTo` chỉ so sánh **giá trị số học**, nên cho 0.

| Phép kiểm tra | `"1.20"` và `"1.2"` | Ý nghĩa |
|---|---|---|
| `a.equals(b)` | `false` | Khác scale (2 so với 1) |
| `a.compareTo(b) == 0` | `true` | Cùng độ lớn thập phân |
| `a.hashCode() == b.hashCode()` | Không nên dựa vào | `hashCode` phù hợp với `equals`, không phải thay thế so sánh số học |
| `a.toString().equals(b.toString())` | `false` | Khác chuỗi/scale, không phải kiểm tra số học |

**Hệ quả với cấu trúc dữ liệu:** `HashSet<BigDecimal>` sử dụng `equals`/`hashCode` nên có thể giữ cả `1.2` và `1.20` như hai phần tử khác nhau. Trong khi `TreeSet<BigDecimal>` mặc định dùng `compareTo` để xếp thứ tự và thường coi hai giá trị đó tương đương theo comparator.

### Ví dụ Java 17+: scale, so sánh và collection

Tạo tệp `DecimalScaleEqualityDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class DecimalScaleEqualityDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.20");
        BigDecimal b = new BigDecimal("1.2");

        System.out.println("aScale=" + a.scale());
        System.out.println("bScale=" + b.scale());
        System.out.println("equals=" + a.equals(b));
        System.out.println("numericEqual=" + (a.compareTo(b) == 0));

        Set<BigDecimal> hashes = new HashSet<>();
        hashes.add(a);
        hashes.add(b);

        Set<BigDecimal> sorted = new TreeSet<>();
        sorted.add(a);
        sorted.add(b);

        System.out.println("hashSetSize=" + hashes.size());
        System.out.println("treeSetSize=" + sorted.size());

        BigDecimal original = new BigDecimal("1000.00");
        BigDecimal normalized = original.stripTrailingZeros();
        System.out.println("original=" + original);
        System.out.println("normalized=" + normalized);
        System.out.println("normalizedScale=" + normalized.scale());
        System.out.println("plain=" + normalized.toPlainString());
    }
}
~~~

~~~bash
javac DecimalScaleEqualityDemo.java
java DecimalScaleEqualityDemo
~~~

Đầu ra:

~~~text
aScale=2
bScale=1
equals=false
numericEqual=true
hashSetSize=2
treeSetSize=1
original=1000.00
normalized=1E+3
normalizedScale=-3
plain=1000
~~~

`stripTrailingZeros()` bỏ số 0 không cần thiết ở phần hệ số và có thể tạo **scale âm**. Không nên gọi nó tùy tiện nếu scale lưu trữ là thông tin nghiệp vụ quan trọng, chẳng hạn hệ thống yêu cầu ghi đúng `"1.20"` theo định dạng nhập.

## 11. `toString`, `toPlainString` và giữ **giá trị** so với giữ **cách viết ban đầu**

Khi parse chuỗi, `BigDecimal` giữ **giá trị thập phân và scale tương ứng**, nhưng **không giữ nguyên mọi ký tự của chuỗi đầu vào**.

Ví dụ:

~~~java
BigDecimal a = new BigDecimal("0001.2300");
BigDecimal b = new BigDecimal("1.23E+4");

System.out.println(a);                  // 1.2300
System.out.println(b);                  // 1.23E+4
System.out.println(b.toPlainString());  // 12300
~~~

Đây là minh họa. Dãy số 0 đứng đầu trong `"0001.2300"` không nhất thiết được xuất lại; ký pháp số mũ cũng có thể được chuẩn hóa. `BigDecimal` không phải công cụ lưu **token văn bản gốc** từng ký tự.

- `toString()` tạo biểu diễn chuỗi thập phân chuẩn của `BigDecimal`, có thể dùng số mũ.
- `toPlainString()` xuất **không dùng ký pháp số mũ**. Nó phù hợp với một số giao diện/CSV, nhưng có thể tạo chuỗi dài nếu scale lớn.
- `toEngineeringString()` có thể dùng số mũ ở bội số 3, phù hợp một số ứng dụng khoa học/kỹ thuật.
- `stripTrailingZeros()` tạo **giá trị `BigDecimal` mới** sau chuẩn hóa chữ số 0 cuối; nó có thể thay đổi scale.

Nếu cần lưu chứng từ chứa chính xác cách khách nhập `"+0001.2300"`, hãy lưu riêng **chuỗi đầu vào đã xác thực** cùng giá trị `BigDecimal` khi cần truy xuất bản gốc. Không kỳ vọng `toString()` khôi phục dấu cộng hoặc số 0 đầu.

Nếu xây dựng round-trip, cần xác định rõ “giữ nguyên” là **cùng giá trị số**, **cùng scale**, hay **cùng chuỗi ký tự**. Ba mục tiêu này không giống nhau.

## 12. Đọc dữ liệu ngoại vi: CSV, JSON và định dạng theo locale

### Khi nguồn đã là String

Với chuỗi JSON/CSV số thập phân như `"123.4500"`, dùng `new BigDecimal(text)` sau khi kiểm tra format. Hạn chế chuyển qua `Double.parseDouble` hoặc ép sang `double` trong pipeline.

Ví dụ một pipeline **mất ý nghĩa decimal**:

~~~java
String input = "0.1";
double intermediate = Double.parseDouble(input);
BigDecimal result = new BigDecimal(intermediate); // mang theo xấp xỉ nhị phân
~~~

Pipeline giữ giá trị theo chuỗi:

~~~java
String input = "0.1";
BigDecimal result = new BigDecimal(input);
~~~

### Khi nguồn là JSON number

Nhiều thư viện JSON cho phép chọn kiểu số khi parse. Nếu một thư viện tự parse mọi số thập phân thành `double` trước, các chữ số có thể đã mất hoặc bị làm tròn **trước khi** tạo `BigDecimal`. Với dữ liệu tiền/số thập phân cần chính xác, hãy cấu hình parser lấy numeric token trực tiếp thành `BigDecimal` hoặc chuỗi theo API cụ thể của thư viện.

Không thể nói tất cả thư viện JSON mặc định xử lý giống nhau; phải kiểm tra phiên bản, model DTO và cơ chế parser thực tế.

### Khi nguồn là số theo locale

Một người dùng có thể nhập `"1.234,56"` hoặc `"1,234.56"`. Đây là hai cách viết có thể tương ứng với 1234.56 ở các locale khác nhau. `new BigDecimal(String)` **không tự hiểu dấu tách hàng nghìn hoặc dấu phẩy thập phân theo locale**. Nếu ứng dụng cần nhập số theo ngôn ngữ:

1. Xác định và cố định **locale** đầu vào.
2. Dùng parser/formatter hỗ trợ locale phù hợp hoặc xác thực định dạng theo hợp đồng.
3. Chuyển số thu được sang `BigDecimal` **không đi qua `double`** nếu yêu cầu chính xác; một số API `NumberFormat` có thể cấu hình parse thành `BigDecimal` hoặc có thể xây dựng quy trình chuẩn hóa token có kiểm soát.
4. Đặt test cho các chuỗi mơ hồ, dấu âm, separator và khoảng trắng.

Đừng thay dấu phân cách kiểu “replace all comma thành dot” rồi tự nhận là đã hỗ trợ locale.

## 13. Các giới hạn cần biết

**`BigDecimal` chính xác theo hệ thập phân không có nghĩa mọi phép toán luôn giữ vô hạn chữ số.**

- `BigDecimal` là immutable: cần lưu kết quả phép toán trả về.
- Constructor `BigDecimal(String)` chỉ phân tích văn bản hợp lệ, không nhận `NaN`/vô cực.
- `BigDecimal.divide` không chỉ định rounding có thể ném `ArithmeticException` với phần thập phân tuần hoàn.
- `MathContext` giới hạn precision và có thể làm tròn.
- `setScale` có thể làm tròn hoặc ném lỗi khi dùng `UNNECESSARY`.
- `doubleValue()` có thể mất độ chính xác hoặc overflow sang Infinity; `intValue()`/`longValue()` có thể mất thông tin. Dùng phương thức `...ValueExact()` phù hợp nếu cần kiểm tra tính chính xác và miền.
- Độ lớn scale dùng `int`, kích thước số nguyên hệ số và thao tác tính toán vẫn bị ràng buộc bởi bộ nhớ/tài nguyên. Không xem `BigDecimal` là bộ nhớ vô hạn.
- Chuỗi cực dài hoặc số mũ cực trị từ nguồn không tin cậy cần được **giới hạn và kiểm tra** để giảm rủi ro tiêu tốn tài nguyên.
- Chính sách scale/rounding khi ghi dữ liệu cần được xác định nhất quán với yêu cầu nghiệp vụ.

### Khi nào chọn `BigDecimal`, `double` hoặc `long`?

| Bài toán | Lựa chọn thường phù hợp |
|---|---|
| Tiền tệ, thuế, giá thập phân chính xác | `BigDecimal` hoặc đơn vị nhỏ nhất trong `long` nếu thiết kế phù hợp |
| Vật lý, đồ họa, mô phỏng, thống kê chấp nhận sai số | `double`/`float` tùy precision/performance |
| Số lượng nguyên, bộ đếm chính xác trong miền | `int`/`long` với kiểm tra tràn khi cần |
| Phân tích dữ liệu đầu vào là chuỗi thập phân nhiều chữ số | `BigDecimal(String)` |
| Phân tích nguồn vốn đã là số nhị phân `double` | Xác định rõ mục tiêu; `valueOf(double)` hoặc `BigDecimal(double)` có ngữ nghĩa khác nhau |
| Cần giữ nguyên từng ký tự của token nhập | Giữ `String` gốc song song với `BigDecimal` |

## 14. Những lỗi phổ biến

| Nhận định sai | Thực tế |
|---|---|
| “`new BigDecimal(0.1)` chính là số thập phân 0.1.” | Nó lấy **giá trị binary64 xấp xỉ của 0.1** rồi chuyển chính xác giá trị đó. |
| “`BigDecimal.valueOf(0.1 + 0.2)` sửa phép cộng double.” | Không: nó nhận `0.30000000000000004` từ phép cộng đã thực hiện. |
| “Cứ gọi `BigDecimal` là mọi phép chia đều chính xác hữu hạn.” | `1.divide(3)` không rounding ném `ArithmeticException`. |
| “`setScale(2)` chỉ là đổi cách hiển thị.” | Khi giảm scale, nó có thể cần làm tròn hoặc ném lỗi; nó trả `BigDecimal` mới. |
| “`precision()` là số chữ số sau dấu phẩy.” | `precision` là số chữ số có nghĩa của hệ số; `scale` biểu thị vị trí dấu thập phân. |
| “`equals` và `compareTo == 0` luôn tương đương.” | `equals` quan tâm scale; `compareTo` so giá trị số. |
| “`stripTrailingZeros` luôn giữ scale không âm.” | Nó có thể tạo scale âm và hiển thị số mũ. |
| “`toString` luôn trả chuỗi nhập ban đầu.” | Nó chuẩn hóa biểu diễn; dấu cộng/số 0 đầu có thể mất. |
| “`new BigDecimal("1,23")` tự hiểu locale Việt Nam.” | Không: constructor không tự dùng locale thập phân. |
| “BigDecimal chấp nhận `NaN` hoặc `Infinity` như `double`.” | Không. |
| “Dùng `doubleValue()` là luôn giữ đúng số.” | Chuyển sang `double` có thể làm tròn hoặc tràn miền. |
| “Số học BigDecimal loại bỏ nhu cầu test và chính sách.” | Vẫn cần kiểm tra định dạng, rounding, scale, resource và quy tắc nghiệp vụ. |

## 15. Checklist triển khai trong dự án

1. **Giữ nguyên nguồn dạng chuỗi thập phân:** tránh chuyển sang `double` trước khi xây `BigDecimal`.
2. **Xác minh cú pháp đầu vào:** dấu, dấu thập phân, số mũ, khoảng trắng, locale, tập chữ số cho phép.
3. **Giới hạn đầu vào không tin cậy:** độ dài, số mũ, số chữ số và các giá trị theo miền nghiệp vụ.
4. **Parse bằng `new BigDecimal(text)`** và bắt `NumberFormatException` ở ranh giới.
5. **Chọn đơn vị và scale kỳ vọng:** ví dụ số tiền hai chữ số sau dấu thập phân, không tự giả định mọi loại tiền dùng hai chữ số.
6. **Dùng `add`/`subtract`/`multiply`/`divide`**, luôn gán kết quả mới nếu cần cập nhật.
7. **Chỉ định rounding rõ ràng** ở điểm làm tròn cần thiết; phân biệt scale với precision.
8. **So sánh bằng `compareTo`** nếu mục tiêu là độ lớn số học; sử dụng `equals` khi cả scale cũng là một phần của định danh.
9. **Chọn cách serialize:** `toString` có thể dùng số mũ; `toPlainString` không dùng số mũ, nhưng không tái tạo chính xác token gốc.
10. **Không quay lại `double`** ở các bước cần decimal exactness.
11. **Test các biên:** `"0"`, `"-0.00"`, `"0.1"`, `"1.20"`, số mũ, 0 đứng đầu, dữ liệu lỗi, chia cho 3, rounding ties và scale âm.
12. **Lưu ý API collection:** `HashSet<BigDecimal>` và `TreeSet<BigDecimal>` có hành vi khác nhau khi cùng giá trị nhưng khác scale.

## 16. Câu hỏi tự kiểm tra

1. `new BigDecimal("0.1")` khác `new BigDecimal(0.1)` ở đâu?
2. `BigDecimal.valueOf(0.1)` thường in ra gì? Nó có sửa được kết quả `0.1 + 0.2` đã tính bằng `double` không?
3. `new BigDecimal("1.20").scale()` là bao nhiêu? Còn `precision()`?
4. Hai số `"1.20"` và `"1.2"` có `equals` bằng nhau không? `compareTo`?
5. `new BigDecimal("1").divide(new BigDecimal("3"))` có thể ném lỗi nào?
6. `setScale(2, HALF_UP)` khác `round(new MathContext(2, HALF_UP))` ở ý nghĩa ra sao?
7. Tại sao `new BigDecimal("1_000.50")` không hợp lệ dù `1_000.50` là một kiểu literal Java có thể viết?
8. `new BigDecimal("1.23E+4").toPlainString()` in ra gì?
9. `stripTrailingZeros` có thể thay đổi `scale` như thế nào?
10. Nếu cần lưu đúng nguyên văn `"+0001.2300"` khách nhập, chỉ lưu `BigDecimal` đã đủ không?
11. Khi đọc số tiền trong JSON, nguy cơ gì nếu thư viện parse số thành `double` trước?
12. Vì sao `BigDecimal` không tự quyết định một mức rounding đúng cho mọi hệ thống?

**Đáp án gợi ý:** (1) Constructor `String` giữ chính xác ý nghĩa thập phân, constructor `double` giữ giá trị binary64 xấp xỉ đã có. (2) `0.1`; không, phép cộng `double` trước đó đã tạo `0.30000000000000004`. (3) Scale 2, precision 3. (4) `equals` false, `compareTo` 0. (5) `ArithmeticException` khi phần thập phân không kết thúc mà không chọn rounding. (6) Một cái chọn số chữ số sau dấu chấm, một cái chọn số chữ số có nghĩa. (7) Parser runtime không đọc cú pháp literal Java có underscore. (8) `12300`. (9) Có thể bỏ số 0 cuối và tạo scale âm. (10) Không, phải giữ `String` gốc khi yêu cầu nguyên văn. (11) Mất chính xác thập phân trước khi tạo `BigDecimal`. (12) Rounding là chính sách nghiệp vụ, cần lựa chọn rõ lúc cần.

**Ghi nhớ:** Với **chuỗi số thập phân**, sử dụng **`new BigDecimal(text)` ngay tại ranh giới nhập liệu** để giữ đúng giá trị thập phân. Phân biệt `BigDecimal(String)`, `BigDecimal(double)` và `BigDecimal.valueOf(double)`; hiểu **scale, precision, equals/compareTo, các phép toán và quy tắc làm tròn**. Tránh đưa dữ liệu qua `double` ở giữa nếu bài toán đòi hỏi độ chính xác thập phân.