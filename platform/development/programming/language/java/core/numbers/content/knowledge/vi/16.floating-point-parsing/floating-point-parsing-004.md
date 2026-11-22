# Đầu vào số thực hợp lệ vẫn có thể bị làm tròn, overflow hoặc underflow trong Java

## 1. Cú pháp hợp lệ không có nghĩa giá trị được giữ chính xác

`Float.parseFloat(String)` và `Double.parseDouble(String)` chuyển một chuỗi ký tự hợp lệ thành giá trị dấu phẩy động `float` hoặc `double`. Hai API này kiểm tra **cú pháp chuỗi**, rồi chuyển giá trị toán học được mô tả bởi chuỗi sang tập hữu hạn các số dấu phẩy động mà Java biểu diễn được.

Có ba tình huống rất khác nhau:

1. **Làm tròn (rounding):** chuỗi mô tả một số hợp lệ nhưng không nằm chính xác trên lưới giá trị `float`/`double`; parser trả về một giá trị đại diện gần nó.
2. **Overflow:** độ lớn của số hữu hạn mà chuỗi mô tả quá lớn; kết quả có thể là `+Infinity` hoặc `-Infinity`.
3. **Underflow:** độ lớn quá nhỏ so với độ phân giải gần 0; kết quả có thể là **số dưới chuẩn** (*subnormal*) với độ chính xác giảm hoặc bị làm tròn hẳn thành `+0.0`/`-0.0`.

Cả ba đều có thể xảy ra **dù chuỗi hoàn toàn hợp lệ** và không có `NumberFormatException`.

```java
double a = Double.parseDouble("0.1");       // Hữu hạn, nhưng không chính xác tuyệt đối 0.1
double b = Double.parseDouble("1e400");     // Infinity
double c = Double.parseDouble("1e-4000");   // 0.0
float d = Float.parseFloat("3.5e38");       // Infinity
float e = Float.parseFloat("1e-50");        // 0.0
```

Đây là đặc tính của phép chuyển sang số dấu phẩy động có độ rộng cố định, không mặc nhiên là lỗi parser. Ứng dụng cần tự quyết định có chấp nhận kết quả làm tròn, số dưới chuẩn, số 0 do underflow hoặc vô cực hay không.

### Ba câu hỏi phải tách biệt

| Câu hỏi | Ví dụ | Cách xác minh |
| --- | --- | --- |
| Chuỗi có cú pháp được parser hỗ trợ không? | `"1e400"` | `parseDouble` có trả giá trị hay ném `NumberFormatException`? |
| Giá trị parse được có hữu hạn không? | `"1e400"` → `Infinity` | `Double.isFinite(result)` |
| Giá trị gốc được biểu diễn chính xác không? | `"0.1"` → một `double` gần 0.1 | So giá trị toán học nguồn với giá trị nhị phân chính xác theo cách không làm tròn nguồn thêm lần nữa |

Không kết luận “parse thành công” đồng nghĩa “nằm trong miền hữu hạn” hoặc “không mất chữ số”.

## 2. Nền tảng IEEE 754: một chuỗi có thể mô tả nhiều số hơn kiểu đích

Java `float` là binary32, có 32 bit tổng cộng với **24 bit độ chính xác phần trị hữu hiệu**. Java `double` là binary64, có 64 bit tổng cộng với **53 bit độ chính xác phần trị hữu hiệu**.

Mỗi kiểu có các giá trị hữu hạn, số chuẩn hóa (*normal*), số dưới chuẩn (*subnormal*), số 0 có dấu, vô cực và `NaN`. Khoảng cách giữa hai số biểu diễn liền kề thay đổi theo độ lớn.

| Thuộc tính | `float` | `double` |
| --- | --- | --- |
| Độ chính xác phần trị | 24 bit | 53 bit |
| `MAX_VALUE` (hữu hạn dương lớn nhất) | Khoảng `3.4028235E38` | Khoảng `1.7976931348623157E308` |
| `MIN_NORMAL` (dương chuẩn hóa nhỏ nhất) | Khoảng `1.17549435E-38` | Khoảng `2.2250738585072014E-308` |
| `MIN_VALUE` (dương khác 0 nhỏ nhất, dưới chuẩn) | Khoảng `1.4E-45` | Khoảng `4.9E-324` |
| Ký hiệu vô cực dương | `Float.POSITIVE_INFINITY` | `Double.POSITIVE_INFINITY` |
| Kiểm tra hữu hạn | `Float.isFinite(x)` | `Double.isFinite(x)` |

**Đặc biệt:** `Float.MIN_VALUE` và `Double.MIN_VALUE` **không phải số âm nhỏ nhất**. Chúng là các số **dương khác 0 nhỏ nhất** mà kiểu tương ứng biểu diễn được. Cận âm hữu hạn về thứ tự số học là `-Float.MAX_VALUE` hoặc `-Double.MAX_VALUE`.

Đừng hiểu `MIN_NORMAL` là ngưỡng mà mọi giá trị nhỏ hơn đều thành 0. **Số dưới chuẩn** cho phép biểu diễn thêm các giá trị dương rất nhỏ nằm giữa 0 và `MIN_NORMAL`, nhưng độ chính xác tương đối thường kém hơn các số chuẩn hóa.

### Miền biểu diễn và độ chính xác là hai giới hạn khác nhau

Một chuỗi `"9007199254740993"` nằm rất xa cận overflow của `double`. Nhưng số nguyên đó (`2^53 + 1`) **không thể** được biểu diễn chính xác bằng `double`: nó sẽ làm tròn thành `9007199254740992`.

Trong khi đó chuỗi `"1e400"` biểu diễn số hữu hạn theo toán học nhưng lớn hơn `Double.MAX_VALUE` nhiều lần. Parser trả về `Infinity`.

Do đó, một giá trị có thể:

- Hữu hạn và chính xác, như `0.5`.
- Hữu hạn nhưng bị làm tròn, như `0.1` hoặc `2^53 + 1`.
- Hữu hạn, rất nhỏ, dưới chuẩn và có thể bị làm tròn.
- Nhỏ đến mức thành `0.0`.
- Lớn đến mức thành vô cực.

## 3. Chuỗi hợp lệ nhưng bị làm tròn

### 3.1. Giá trị thập phân `0.1`

Số thập phân `0.1` không có biểu diễn nhị phân hữu hạn. Parser chọn một số `double` gần nó:

```java
double x = Double.parseDouble("0.1");

System.out.println(x);                         // 0.1
System.out.println(new java.math.BigDecimal(x));
// 0.1000000000000000055511151231257827021181583404541015625
```

`Double.toString` chọn dạng thập phân ngắn có thể parse ngược về cùng giá trị `double`, nên việc in `0.1` **không chứng minh** lưu chính xác `1/10`.

Ở đây `new BigDecimal(x)` là **thủ thuật quan sát chính xác giá trị nhị phân của `double` đã có**, không phải cách khuyên dùng để khởi tạo số tiền decimal. Nếu muốn giữ đúng số thập phân gốc, dùng `new BigDecimal("0.1")`.

Với `float`:

```java
float x = Float.parseFloat("0.1");
System.out.println((double) x); // 0.10000000149011612
```

Ép `float` đã parse sang `double` giúp thấy rõ giá trị `float` gần đúng (vì mọi `float` hữu hạn đều có thể được biểu diễn chính xác bằng `double`); việc ép kiểu không phục hồi số `0.1` toán học.

### 3.2. Số nguyên lớn vẫn có thể làm tròn

```java
double x = Double.parseDouble("9007199254740993");
double y = Double.parseDouble("9007199254740992");

System.out.println(x);      // 9.007199254740992E15
System.out.println(x == y); // true
```

Chuỗi đầu hợp lệ nhưng giá trị nguyên `2^53 + 1` không có biểu diễn `double` đúng. Hai chuỗi mô tả **hai số nguyên khác nhau**, nhưng sau khi parse thì cùng một giá trị.

Nếu đây là ID, timestamp nguyên với độ phân giải nhỏ, số lượng hoặc khóa cần phân biệt từng đơn vị, không nên lưu chúng trong `double`. Dùng `Long.parseLong` khi vừa miền `long`, hoặc `BigInteger` khi cần miền rộng hơn.

### 3.3. Parser làm tròn theo quy tắc nào?

Java chuyển số thập phân và số dấu phẩy động hexa hợp lệ sang giá trị có thể đại diện theo kiểu đích, làm tròn tới giá trị gần nhất. Nếu giá trị đúng nằm chính giữa hai giá trị đại diện được, chọn giá trị có phần trị chẵn ở bit cuối (*round to nearest, ties to even*).

Ví dụ hexa nhị phân biểu diễn chính xác giá trị nằm đúng **nửa ULP** trên `1.0`:

```java
double halfway = Double.parseDouble("0x1.00000000000008p0");
System.out.println(halfway); // 1.0
```

Ở đây chuỗi hexa mô tả `1 + 2^-53`, chính giữa `1.0` và `Math.nextUp(1.0)`; phía `1.0` có bit cuối phần trị chẵn nên được chọn.

Điều này khác `Math.round`, vốn có quy tắc riêng và trả kiểu nguyên. Cũng khác `BigDecimal.setScale`, nơi người dùng chủ động chọn một `RoundingMode`.

**Chú ý:** `Float.parseFloat` trực tiếp nhắm đến độ chính xác `float`. Không nên mặc định quy trình `Double.parseDouble(text)` rồi ép sang `float` tương đương về mọi trường hợp sát biên làm tròn, vì **làm tròn hai lần** có thể khác làm tròn trực tiếp một lần.

## 4. Chuỗi hợp lệ nhưng overflow thành vô cực

Overflow xảy ra khi giá trị có độ lớn vượt khả năng đại diện hữu hạn của kiểu đích. Parser vẫn có thể trả về một giá trị IEEE 754 hợp lệ: `+Infinity` hoặc `-Infinity`.

```java
double positive = Double.parseDouble("1e400");
double negative = Double.parseDouble("-1e400");
float tooBigForFloat = Float.parseFloat("3.5e38");

System.out.println(positive);       // Infinity
System.out.println(negative);       // -Infinity
System.out.println(tooBigForFloat); // Infinity
```

Không có `NumberFormatException` ở ba chuỗi trên. Chúng **có cú pháp hợp lệ** và biểu diễn các số hữu hạn thập phân rất lớn, nhưng không biểu diễn được dưới dạng số hữu hạn của kiểu được chọn.

```java
System.out.println(Double.isInfinite(positive)); // true
System.out.println(Double.isFinite(positive));   // false
System.out.println(Double.isNaN(positive));      // false
```

### `Infinity` viết trong chuỗi cũng là đầu vào hợp lệ

Parser hỗ trợ token `"Infinity"`, `"-Infinity"`, `"NaN"`:

```java
System.out.println(Double.parseDouble("Infinity")); // Infinity
System.out.println(Double.isNaN(Double.parseDouble("NaN"))); // true
```

Vì vậy khi kết quả là vô cực, chỉ dựa vào `Double.isInfinite(result)` **không thể biết**:

1. Người dùng đã gửi token `"Infinity"`, hay
2. Người dùng đã gửi một số hữu hạn như `"1e400"` nhưng số đó overflow.

Nếu hợp đồng cần phân biệt nguyên nhân, phải xét **chuỗi nguồn và cú pháp/giá trị nguồn trước khi mất thông tin**, không chỉ xét giá trị `double` trả về.

Ứng dụng có thể từ chối mọi giá trị không hữu hạn; nhưng đây là **kiểm tra miền nghiệp vụ sau parse**, không phải lỗi cú pháp mà Java tự phát hiện giúp.

### Overflow không chỉ xuất hiện khi parse

Ngay cả hai số `double` hữu hạn khi thực hiện phép nhân/cộng vẫn có thể tạo `Infinity`; vì vậy kiểm tra `isFinite` tại đầu vào chỉ xác nhận đầu vào, **không chứng minh mọi phép toán sau đó hữu hạn**. Nếu thuật toán yêu cầu miền hữu hạn, hãy xác minh tại các ranh giới phù hợp.

## 5. Chuỗi hợp lệ nhưng underflow thành dưới chuẩn hoặc số 0

Gần số 0, độ phân giải của `double` có giới hạn. Số **dương khác 0 nhỏ nhất** là `Double.MIN_VALUE`, khoảng `4.9406564584124654 × 10^-324`. Với `float`, tương ứng khoảng `1.401298464324817 × 10^-45`.

Khi một số dương rất nhỏ hơn mức biểu diễn tối thiểu, việc làm tròn có thể tạo ra `0.0`. Nếu số âm cực nhỏ, kết quả có thể là `-0.0` — số 0 âm vẫn có **bit dấu**.

```java
double tiny = Double.parseDouble("1e-4000");
double tinyNegative = Double.parseDouble("-1e-4000");

System.out.println(tiny);           // 0.0
System.out.println(tinyNegative);   // -0.0
System.out.println(tinyNegative == 0.0); // true
```

Cả `"1e-4000"` và `"-1e-4000"` đều là chuỗi hợp lệ, đều mô tả số toán học **khác 0**, nhưng sau khi parse mất độ lớn. Không có exception.

Kiểm tra dấu của số 0:

```java
long bits = Double.doubleToRawLongBits(tinyNegative);
System.out.println(Long.toHexString(bits)); // 8000000000000000
```

Dù `-0.0 == +0.0` là `true`, dấu có thể ảnh hưởng phép toán như `1.0 / -0.0` (cho `-Infinity`) và hành vi `Double.compare`, `Double.equals`.

### Vùng dưới chuẩn (subnormal)

Không phải số nào nhỏ hơn `Double.MIN_NORMAL` đều bị làm tròn về 0:

```java
double subnormal = Double.parseDouble("1e-320");
System.out.println(subnormal); // 1.0E-320
```

Đây là giá trị `double` dương, khác 0, nhưng **nhỏ hơn `Double.MIN_NORMAL`**. Nó nằm trong vùng dưới chuẩn. Tại vùng này, bước nhảy tuyệt đối giữa hai giá trị lân cận vẫn rất nhỏ, nhưng độ chính xác tương đối giảm khi độ lớn tiến về 0.

Với `float`:

```java
System.out.println(Float.parseFloat("1e-44")); // 9.8E-45
System.out.println(Float.parseFloat("1e-50")); // 0.0
```

Chuỗi `"1e-44"` tạo số dưới chuẩn khác 0 sau làm tròn, còn `"1e-50"` quá nhỏ và thành 0. Theo cách dùng IEEE 754 chặt chẽ, tín hiệu *underflow* gắn với độ nhỏ và việc mất độ chính xác; trong lập trình ứng dụng, “underflow” thường được dùng rộng hơn để nói kết quả đi vào vùng dưới chuẩn hoặc làm tròn về 0. Khi viết tài liệu kiểm thử, nên tách rõ **SUBNORMAL** và **ROUNDED_TO_ZERO** thay vì coi chúng hoàn toàn giống nhau.

### Tại sao `result == 0.0` chưa đủ để phát hiện underflow?

Hai chuỗi:

```java
Double.parseDouble("0.0");
Double.parseDouble("1e-4000");
```

đều trả `0.0`, nhưng **nguồn gốc khác nhau**. Từ giá trị `double` cuối cùng, không thể suy ra chắc chắn đầu vào gốc là 0 hay một số khác 0 đã underflow. Muốn phát hiện phải giữ nguyên chuỗi ban đầu và phân tích giá trị gốc theo cách đủ miền/độ chính xác.

## 6. `NumberFormatException` khác overflow/underflow như thế nào?

Các parser nhận chuỗi theo cú pháp mà Java hỗ trợ. Nếu chuỗi **không có dạng hợp lệ**, parser thường ném `NumberFormatException`. Ví dụ:

```java
Double.parseDouble("not-a-number"); // NumberFormatException
Double.parseDouble("1_000.0");      // NumberFormatException
```

Dấu gạch dưới trong literal Java như `1_000.0` là cú pháp **trong mã nguồn**, không tự trở thành cú pháp chuỗi được `Double.parseDouble` chấp nhận.

Một số chuỗi hợp lệ có thể bất ngờ đối với người mới:

| Chuỗi | `Double.parseDouble` | Vì sao |
| --- | --- | --- |
| `"0.5"` | `0.5` | Phân số nhị phân chính xác |
| `"0.1"` | In ra `0.1`, nhưng làm tròn nhị phân | Hữu hạn, không biểu diễn chính xác số decimal nguồn |
| `"9007199254740993"` | `9.007199254740992E15` | Giá trị vượt miền số nguyên liên tiếp chính xác của `double` |
| `"1e400"` | `Infinity` | Overflow |
| `"-1e400"` | `-Infinity` | Overflow |
| `"1e-4000"` | `0.0` | Làm tròn xuống 0 do quá nhỏ |
| `"1e-320"` | `1.0E-320` | Giá trị subnormal hữu hạn, khác 0 |
| `"Infinity"` | `Infinity` | Token được parser hỗ trợ |
| `"NaN"` | `NaN` | Token được parser hỗ trợ |
| `"0x1.8p1"` | `3.0` | Cú pháp dấu phẩy động hexa |
| `"1_000.0"` | `NumberFormatException` | Dấu `_` không hợp lệ trong chuỗi parser |
| `"1,5"` | `NumberFormatException` | Không phải cú pháp decimal của `parseDouble` |

`Double.parseDouble(" 1.25 ")` được chấp nhận sau khi loại các ký tự whitespace theo quy tắc của parser, nhưng **không nên suy ra mọi định dạng locale đều được chấp nhận**. Đầu vào dùng dấu phẩy làm dấu thập phân hoặc dấu nhóm hàng nghìn cần một parser theo locale được cấu hình cụ thể. Với đầu vào `null`, API có thể ném `NullPointerException`, không phải cách báo overflow.

Cũng cần phân biệt `Integer.parseInt("99999999999999999999")` với `Double.parseDouble` các số rất lớn: parser nguyên có thể ném `NumberFormatException` do vượt miền `int`, trong khi parser dấu phẩy động có thể trả `Infinity` khi giá trị hữu hạn thập phân quá lớn. Không áp dụng quy tắc báo lỗi của parser nguyên cho parser số thực.

## 7. Demo Java 17 đầy đủ: bốn kết quả từ chuỗi hợp lệ

Tạo tệp `FloatingParseDemo.java`:

```java
import java.math.BigDecimal;

public class FloatingParseDemo {
    public static void main(String[] args) {
        double preciseHalf = Double.parseDouble("0.5");
        double roundedDecimal = Double.parseDouble("0.1");

        System.out.println("half = " + preciseHalf);
        System.out.println("decimal printed = " + roundedDecimal);
        System.out.println("decimal exact binary value = "
                + new BigDecimal(roundedDecimal));

        double roundedInteger = Double.parseDouble("9007199254740993");
        double adjacentInteger = Double.parseDouble("9007199254740992");
        System.out.println("large integer = " + roundedInteger);
        System.out.println("two parsed integers equal = "
                + (roundedInteger == adjacentInteger));

        System.out.println("double overflow = "
                + Double.parseDouble("1e400"));
        System.out.println("negative overflow = "
                + Double.parseDouble("-1e400"));
        System.out.println("float overflow = "
                + Float.parseFloat("3.5e38"));

        double tiny = Double.parseDouble("1e-4000");
        double negativeTiny = Double.parseDouble("-1e-4000");
        System.out.println("double underflow = " + tiny);
        System.out.println("negative underflow bits = "
                + Long.toHexString(
                        Double.doubleToRawLongBits(negativeTiny)));
        System.out.println("double subnormal = "
                + Double.parseDouble("1e-320"));
        System.out.println("float underflow = "
                + Float.parseFloat("1e-50"));
        System.out.println("float subnormal = "
                + Float.parseFloat("1e-44"));

        System.out.println("hex floating point = "
                + Double.parseDouble("0x1.8p1"));
        System.out.println("explicit infinity = "
                + Double.isInfinite(Double.parseDouble("Infinity")));
        System.out.println("explicit NaN = "
                + Double.isNaN(Double.parseDouble("NaN")));

        try {
            Double.parseDouble("1_000.0");
            System.out.println("unexpected success");
        } catch (NumberFormatException ex) {
            System.out.println("invalid syntax: NumberFormatException");
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac FloatingParseDemo.java
java FloatingParseDemo
```

Đầu ra:

```text
half = 0.5
decimal printed = 0.1
decimal exact binary value = 0.1000000000000000055511151231257827021181583404541015625
large integer = 9.007199254740992E15
two parsed integers equal = true
double overflow = Infinity
negative overflow = -Infinity
float overflow = Infinity
double underflow = 0.0
negative underflow bits = 8000000000000000
double subnormal = 1.0E-320
float underflow = 0.0
float subnormal = 9.8E-45
hex floating point = 3.0
explicit infinity = true
explicit NaN = true
invalid syntax: NumberFormatException
```

Kết quả trên làm rõ bốn trạng thái: giá trị có thể biểu diễn đúng (`0.5`), bị làm tròn (`0.1` hoặc số nguyên lớn), overflow thành vô cực (`1e400`), underflow thành 0 hoặc số dưới chuẩn. Chỉ trường hợp cuối của ví dụ — chuỗi chứa dấu `_` — làm parser báo lỗi cú pháp.

## 8. Kiểm tra sau parse: `isFinite`, `isInfinite`, `isNaN` và phân loại subnormal

Nếu hợp đồng dữ liệu chỉ chấp nhận **số hữu hạn**, hãy kiểm tra *sau khi* parse:

```java
static double parseFiniteDouble(String text) {
    double result = Double.parseDouble(text);

    if (!Double.isFinite(result)) {
        throw new IllegalArgumentException(
                "Expected a finite number: " + text);
    }

    return result;
}
```

Đây là đoạn phương thức độc lập có thể đặt vào một class Java. Nó loại cả `NaN` lẫn vô cực, bất kể chúng đến từ token tường minh hay overflow. Nhưng nó **không** phát hiện mất chính xác do làm tròn hoặc số khác 0 bị làm tròn thành `0.0`, vì 0 và subnormal vẫn là giá trị hữu hạn.

Đối với các giá trị hữu hạn dương/âm khác 0:

```java
static boolean isSubnormal(double x) {
    return Double.isFinite(x)
            && x != 0.0
            && Math.abs(x) < Double.MIN_NORMAL;
}
```

Phương thức trên kiểm tra một giá trị kết quả **có nằm trong vùng subnormal không**, không chứng minh chuỗi nguồn bị làm tròn hay không. Một số subnormal được mô tả đúng bằng dạng nhị phân hoặc decimal phù hợp vẫn có thể được biểu diễn chính xác.

Nếu miền ứng dụng không cho phép kết quả subnormal do hạn chế độ chính xác, từ chối một cách tường minh; đừng tự hiểu `Double.isFinite` là đã bao hàm yêu cầu này.

### Cẩn thận với số 0 âm

`-0.0` là hữu hạn và `-0.0 == 0.0` là `true`. Khi dấu cần được phân biệt:

```java
double x = Double.parseDouble("-1e-4000");
boolean negativeZero =
        Double.doubleToRawLongBits(x)
        == Double.doubleToRawLongBits(-0.0);
```

Có hai trường hợp cho cùng `-0.0`: chuỗi thực sự mô tả âm không (`"-0.0"`) hoặc một số âm khác 0 đã underflow. Đọc bit dấu chỉ cho thấy **trạng thái cuối**, không khôi phục được nguyên nhân.

## 9. Muốn biết có làm tròn hay không phải giữ giá trị nguồn

Sau khi `Double.parseDouble("0.1")` đã trả về `double`, kết quả không còn mang đầy đủ thông tin về chuỗi gốc. `Double.toString(result)` in biểu diễn ngắn để round-trip thành cùng giá trị, **không** cho biết decimal nguồn được giữ tuyệt đối.

Với một đầu vào **thuần thập phân** nằm trong miền mà `BigDecimal(String)` có thể phân tích, có thể so sánh chính xác giá trị thập phân gốc với **giá trị nhị phân chính xác** đã parse:

```java
import java.math.BigDecimal;

BigDecimal source = new BigDecimal("0.1");
double parsed = Double.parseDouble("0.1");

// Constructor BigDecimal(double) giữ đúng giá trị nhị phân đã có.
// Nó được dùng ở đây để chẩn đoán, không phải để khởi tạo tiền tệ.
BigDecimal storedExactly = new BigDecimal(parsed);

boolean unchanged = source.compareTo(storedExactly) == 0;
// unchanged là false: decimal 0.1 khác giá trị nhị phân của parsed.
```

Với `"0.5"`, hai giá trị bằng nhau vì `1/2` có biểu diễn nhị phân hữu hạn. Với `"9007199254740993"`, kết quả khác nhau vì đã làm tròn số nguyên. Phải đảm bảo `parsed` hữu hạn trước khi gọi `new BigDecimal(parsed)` vì constructor đó không chấp nhận vô cực hoặc `NaN`.

**Lưu ý đặc biệt:** `BigDecimal.valueOf(parsed)` không tương đương `new BigDecimal(parsed)` trong bài toán chẩn đoán trên. `valueOf(double)` dùng biểu diễn decimal từ `Double.toString`, phù hợp nhiều nhu cầu thông thường nhưng có thể in lại `0.1` và **che đi khác biệt** giữa số nhị phân và decimal chính xác. Dùng `new BigDecimal(double)` **chỉ khi cần thấy đúng toàn bộ giá trị nhị phân**; với số tiền hoặc đầu vào decimal chính xác, ưu tiên `new BigDecimal(String)`.

### Phân loại đơn giản với decimal input

Nếu hợp đồng đầu vào chỉ chấp nhận số decimal hữu hạn viết thành chuỗi, thuật toán chẩn đoán có thể làm như sau:

1. Phân tích giá trị nguồn `new BigDecimal(text)` để giữ giá trị decimal chính xác.
2. Phân tích sang `double` bằng `Double.parseDouble(text)`.
3. Nếu kết quả vô cực → **overflow** (vì đã loại token `"Infinity"`/`"NaN"` trong bước 1).
4. Nếu nguồn khác 0 mà kết quả là `0.0` hoặc `-0.0` → **underflow to zero**.
5. Nếu kết quả khác 0 và có độ lớn nhỏ hơn `Double.MIN_NORMAL` → giá trị đầu ra là **subnormal**; có thể so sánh tiếp để biết nó chính xác hay bị làm tròn.
6. Nếu kết quả hữu hạn, dùng `source.compareTo(new BigDecimal(parsed))` để kiểm tra **có làm tròn** so với giá trị decimal nguồn hay không.

Ví dụ áp dụng:

| Chuỗi decimal | Giá trị đích | Kết luận |
| --- | --- | --- |
| `"0.5"` | `0.5` | Chính xác |
| `"0.1"` | Giá trị gần `0.1` | Hữu hạn nhưng làm tròn |
| `"9007199254740993"` | `9007199254740992` | Làm tròn giá trị nguyên |
| `"1e400"` | `Infinity` | Overflow |
| `"1e-4000"` | `0.0` | Underflow thành 0 |
| `"1e-320"` | Subnormal gần `1e-320` | Dưới chuẩn; cần xét thêm sai số nếu muốn biết có chính xác không |

Cách này là **chẩn đoán cho nguồn decimal**, không phải parser tổng quát cho chuỗi hexa, token `"Infinity"`/`"NaN"` hoặc mọi đầu vào cực dài: `BigDecimal(String)` có miền cú pháp và giới hạn exponent/scale riêng, và có thể tiêu tốn nhiều tài nguyên khi chuỗi quá lớn. Hãy đặt giới hạn kích thước đầu vào thích hợp.

## 10. Chọn kiểu số và chính sách xử lý theo bài toán

| Nhu cầu | Khuyến nghị |
| --- | --- |
| Chỉ chấp nhận chuỗi có cú pháp số thực Java | `Float.parseFloat` / `Double.parseDouble`, bắt `NumberFormatException` |
| Cần mọi kết quả **hữu hạn** | Sau parse, dùng `Float.isFinite` / `Double.isFinite` |
| Cần cấm `NaN` và vô cực rõ ràng | Dùng `isNaN`/`isInfinite` hoặc `isFinite`; thông báo lỗi nghiệp vụ cụ thể |
| Cần phát hiện số khác 0 bị parse thành 0 | Giữ và phân tích **nguồn trước làm tròn**, ví dụ `BigDecimal(String)` cho decimal |
| Cần phát hiện/chặn vùng dưới chuẩn | Kiểm tra giá trị hữu hạn, khác 0, và `abs(x) < MIN_NORMAL` |
| Cần decimal chính xác như số tiền | `BigDecimal(String)` với quy tắc làm tròn/tính toán thích hợp |
| Cần lưu nguyên lớn và phân biệt từng đơn vị | `long` / `BigInteger`, không chuyển thành `double` làm khóa |
| Cần giao tiếp JSON/API chặt | Xác định rõ cú pháp số được phép, có cho phép NaN/Infinity không, ngưỡng giá trị, cách báo overflow/underflow |
| Cần tính toán khoa học nhị phân | Dùng `double`/`float` nếu đáp ứng độ chính xác, kiểm tra lỗi số học và miền kết quả |

Một quy trình nhập dữ liệu đáng tin cậy nên có **ba lớp kiểm tra**:

**(1) Syntax:** chuỗi có đúng grammar mà ứng dụng hỗ trợ không? Điều này có thể khác grammar rộng của Java, vì nhiều giao thức không cho phép `"NaN"`, `"Infinity"` hoặc dạng số hexa.

**(2) Range and finiteness:** kết quả có nằm trong miền nghiệp vụ và hữu hạn không? Kiểm tra sau parse và xét cách nhận biết overflow.

**(3) Precision:** sai lệch do làm tròn có chấp nhận được không? Nếu không, giữ dữ liệu gốc và dùng kiểu số thích hợp; không kỳ vọng parser tự báo mọi trường hợp mất độ chính xác.

### Vì sao `try/catch NumberFormatException` chưa đủ?

```java
try {
    double value = Double.parseDouble(text);
    // Phải tiếp tục kiểm tra value theo hợp đồng ứng dụng.
} catch (NumberFormatException ex) {
    // Chỉ xử lý cú pháp không hợp lệ; không đại diện mọi mất độ chính xác.
}
```

Nếu `text = "1e400"`, khối `catch` không chạy dù `value == Infinity`; nếu `text = "1e-4000"`, khối `catch` cũng không chạy dù giá trị nguồn khác 0 bị làm tròn thành 0. Một hệ thống chấp nhận các kết quả đó mà không kiểm tra có thể tạo lỗi khó phát hiện.

## 11. Lỗi phổ biến

1. **Nhầm parse thành công với giữ nguyên giá trị.** Parser có thể làm tròn một số hữu hạn đúng cú pháp.
2. **Nghĩ overflow số thực sẽ ném `NumberFormatException`.** Chuỗi hợp lệ vượt cận có thể trả `Infinity`.
3. **Nghĩ underflow luôn là số 0.** Vùng subnormal vẫn chứa nhiều giá trị khác 0.
4. **Nghĩ `MIN_VALUE` là số âm nhất.** Với `Float`/`Double`, đó là số dương khác 0 nhỏ nhất.
5. **Nhìn `Double.toString(0.1)` rồi kết luận nhị phân lưu đúng 0.1.** Đây là chuỗi ngắn có khả năng round-trip về cùng `double`.
6. **Dùng `BigDecimal.valueOf(double)` để kiểm tra có giữ chính xác decimal nguồn hay không.** Nó không phản ánh toàn bộ số nhị phân chính xác, nên có thể che đi sự khác biệt; mục đích chẩn đoán này cần `new BigDecimal(double)` với đầu vào hữu hạn.
7. **Chuyển nguồn sang `double` rồi mới giữ bằng `BigDecimal`.** Thông tin đã mất không tự hồi phục.
8. **Dùng `result == 0` để kết luận chuỗi gốc biểu diễn số 0.** Có thể là số khác 0 đã underflow.
9. **Dùng `isFinite(result)` để kết luận không làm tròn.** Hữu hạn và chính xác là hai thuộc tính khác nhau.
10. **Dùng số thực làm ID nguyên lớn.** Các giá trị nguyên khác nhau có thể parse thành cùng một `double`.
11. **Cho rằng chuỗi parser chấp nhận mọi literal Java.** Literal mã nguồn có `_` không được `parseDouble` nhận như vậy; cú pháp giao thức/locale còn có thể khác.
12. **Không xét `-0.0`.** Mất độ lớn vẫn có thể giữ dấu, ảnh hưởng một số phép toán và biểu diễn bit.
13. **So sánh chuỗi đầu vào với kết quả `Double.toString` bằng ký tự.** Một giá trị decimal chính xác có thể in ra dưới dạng khác mà không thay đổi số; ngược lại cùng chuỗi ngắn cũng chưa chứng minh số nhị phân bằng giá trị decimal toán học.
14. **Chỉ kiểm tra đầu vào hữu hạn mà bỏ qua phép tính sau đó.** Overflow/underflow cũng có thể phát sinh trong toán học nội bộ.
15. **Áp dụng `BigDecimal` vô điều kiện với chuỗi cực dài.** Cần giới hạn độ dài và kích thước exponent để phòng trường hợp tiêu tốn tài nguyên quá mức.

## 12. Bài tập có đáp án

**Câu 1.** `Double.parseDouble("1e400")` có ném `NumberFormatException` không? Kết quả là gì?

**Đáp án:** Không. Chuỗi có cú pháp hợp lệ, biểu diễn giá trị hữu hạn toán học nhưng quá lớn so với miền `double` hữu hạn, nên parser trả `Infinity`.

**Câu 2.** Có thể phân biệt kết quả của `Double.parseDouble("0")` và `Double.parseDouble("1e-4000")` nếu chỉ giữ hai giá trị `double` trả về không?

**Đáp án:** Không. Cả hai đều có thể bằng `+0.0`. Muốn biết số thứ hai vốn khác 0, phải giữ và phân tích chuỗi nguồn trước khi thông tin mất.

**Câu 3.** Vì sao `Float.parseFloat("0.1")` và `Double.parseDouble("0.1")` không lưu đúng số thực `1/10`?

**Đáp án:** `0.1` không có biểu diễn nhị phân hữu hạn. Cả `float` lẫn `double` phải chọn giá trị gần nó trên lưới biểu diễn. `double` có độ chính xác phần trị cao hơn nên thường gần hơn.

**Câu 4.** Chuỗi `"1e-320"` có parse thành `0.0` trong `double` không?

**Đáp án:** Không với giá trị đã nêu: parser trả một số subnormal khác 0 (in ra `1.0E-320`). Nó nhỏ hơn `Double.MIN_NORMAL` nhưng lớn hơn độ phân giải tối thiểu gần 0.

**Câu 5.** Nếu yêu cầu mọi kết quả parse phải hữu hạn, dùng điều kiện nào?

**Đáp án:** Sau `double x = Double.parseDouble(text)`, dùng `Double.isFinite(x)`. Nếu trả `false`, dữ liệu có `NaN` hoặc vô cực. Nhưng kiểm tra này **không** khẳng định không làm tròn/underflow thành 0.

**Câu 6.** Khi kiểm tra sai lệch decimal giữa chuỗi `"0.1"` và kết quả `double` đã parse, vì sao `new BigDecimal(parsed)` giúp chẩn đoán tốt hơn `BigDecimal.valueOf(parsed)`?

**Đáp án:** `new BigDecimal(parsed)` chuyển **giá trị nhị phân chính xác** của `double` hữu hạn thành decimal, thể hiện phần lệch thực sự. `BigDecimal.valueOf(parsed)` dựa trên dạng thập phân ngắn `Double.toString`, có thể cho ra `"0.1"` và che phần lệch so với giá trị toán học nguồn.

**Câu 7.** Vì sao một chuỗi nguyên có cú pháp hợp lệ lại mất thông tin khi parse bằng `Double.parseDouble`?

**Đáp án:** `double` có 53 bit độ chính xác phần trị; nó không biểu diễn liên tiếp mọi số nguyên vượt `2^53`. Chẳng hạn `"9007199254740993"` làm tròn thành `9007199254740992` dù số đó còn xa ngưỡng overflow.

**Câu 8.** `Double.parseDouble("-1e-4000")` có thể cho `-0.0`. `-0.0 == 0.0` trả gì và có chứng minh không còn dấu âm không?

**Đáp án:** So sánh primitive `==` trả `true`, nhưng bit dấu âm còn tồn tại; `Double.doubleToRawLongBits` cho phép thấy bit dấu. `1.0/-0.0` tạo `-Infinity`.

**Kết luận:** Parser dấu phẩy động trả **một giá trị được biểu diễn bằng `float`/`double`**, chứ không hứa bảo toàn mọi số toán học trong chuỗi. Hãy tách lỗi cú pháp khỏi overflow, underflow và rounding; kiểm tra `isFinite` khi cần, phân biệt số dưới chuẩn với 0, và giữ giá trị nguồn ở biểu diễn phù hợp khi tính chính xác là yêu cầu bắt buộc.