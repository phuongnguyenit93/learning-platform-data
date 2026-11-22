# BigDecimal.valueOf(double) và giới hạn của giá trị double nguồn trong Java

## 1. Vấn đề cốt lõi: chuyển kiểu không thể phục hồi thông tin đã mất

`BigDecimal.valueOf(double)` là cách thường được khuyến nghị khi bạn **đã có một giá trị `double`** và muốn tạo `BigDecimal` có biểu diễn thập phân ngắn, dễ hiểu. Nhưng phương thức này **không biến một phép tính `double` sai số thành phép tính decimal chính xác**, cũng không thể phục hồi chữ số đã bị làm tròn trước đó.

Ba câu lệnh trông giống nhau nhưng có ngữ nghĩa khác nhau:

```java
import java.math.BigDecimal;

BigDecimal fromText = new BigDecimal("0.1");
BigDecimal viaValueOf = BigDecimal.valueOf(0.1);
BigDecimal fromDoubleConstructor = new BigDecimal(0.1);
```

- `new BigDecimal("0.1")` đọc **chuỗi thập phân gốc**, lưu giá trị 0.1 chính xác.
- `BigDecimal.valueOf(0.1)` trước hết nhận **literal `double`** gần 0.1, sau đó sử dụng dạng chuỗi mà `Double.toString(0.1)` tạo ra, trong trường hợp này là `"0.1"`, để tạo `BigDecimal` có giá trị decimal 0.1.
- `new BigDecimal(0.1)` biểu diễn **chính xác giá trị nhị phân đang lưu trong `double`** dưới dạng decimal. Vì giá trị ấy không phải đúng 1/10, đối tượng thu được không bằng decimal 0.1.

Lớp `BigDecimal` không gây ra sai số nguồn. Sai số phát sinh **trước khi gọi** khi ta viết, parse, tính toán hoặc ép hẹp một giá trị thành `double`.

**Nguyên tắc học tập:** phải phân biệt **giá trị decimal gốc**, **giá trị binary64 thực sự được lưu**, và **chuỗi decimal ngắn dùng để biểu diễn lại giá trị binary64**. Ba thứ này có thể khác nhau.

## 2. Nhắc lại: `double` lưu số thực nhị phân như thế nào?

Kiểu `double` của Java là số dấu phẩy động nhị phân 64 bit, theo định dạng IEEE 754 binary64:

| Thành phần | Số bit | Ý nghĩa |
|---|---:|---|
| Dấu | 1 | Dương hoặc âm |
| Số mũ | 11 | Quy mô giá trị theo lũy thừa của 2 |
| Phần phân số lưu trữ | 52 | Các bit của phần trị |
| Độ chính xác phần trị hiệu dụng | 53 | Có thêm bit dẫn đầu ẩn ở số chuẩn hóa |

`double` cung cấp khoảng **15–17 chữ số thập phân có nghĩa**, nhưng không có nghĩa mọi số thập phân với 15 chữ số đều chính xác. Những phân số như 1/10 thường có biểu diễn nhị phân vô hạn, nên Java phải lưu một **giá trị nhị phân gần đúng**.

Ví dụ:

```java
double x = 0.1;
double y = 0.2;
double sum = x + y;

System.out.println(sum); // 0.30000000000000004
```

Dù toán học thập phân cho 0.1 + 0.2 = 0.3, các toán hạng đã được làm tròn thành binary64 và phép cộng cũng chịu làm tròn. Vì thế giá trị `sum` đang lưu tương ứng với biểu diễn in ra là `0.30000000000000004`.

Ngay lúc này, chuyển `sum` thành `BigDecimal` **không thể tự đoán** người viết mong 0.3 hay mong chính xác 0.30000000000000004. Nó chỉ biết giá trị `double` được truyền vào.

## 3. `BigDecimal.valueOf(double)` thực sự làm gì?

Theo hợp đồng API, `BigDecimal.valueOf(double)` dùng biểu diễn thập phân chuẩn do `Double.toString(double)` cung cấp, tương đương về **giá trị và cách đọc chuỗi** với cách gọi:

```java
double source = 0.1;

BigDecimal viaValueOf = BigDecimal.valueOf(source);
BigDecimal viaText =
        new BigDecimal(Double.toString(source));
```

Trong trường hợp này, cả hai đối tượng đều có giá trị decimal **0.1** và scale 1.

`Double.toString` tạo ra chuỗi thập phân chuẩn có thể **round-trip** về cùng giá trị `double` (với các quy tắc đặc biệt cho số 0, NaN và vô cực). Nó **không in toàn bộ khai triển decimal chính xác của mẫu bit binary64** trong mọi trường hợp.

Ví dụ:

```java
System.out.println(Double.toString(0.1)); // 0.1
System.out.println(BigDecimal.valueOf(0.1)); // 0.1
```

Nhưng:

```java
double sum = 0.1 + 0.2;
System.out.println(Double.toString(sum));
// 0.30000000000000004

System.out.println(BigDecimal.valueOf(sum));
// 0.30000000000000004
```

Sự khác biệt này là **kết quả có sẵn từ giá trị nguồn**, không phải một lựa chọn tự động “sửa lỗi” theo trực giác của `BigDecimal`.

### Câu hỏi thường gặp: `valueOf` có phải phép chuyển “chính xác” không?

Phải xác định **“chính xác so với cái gì?”**:

1. **Chính xác so với chuỗi `Double.toString(source)`:** có. `valueOf` tạo decimal đúng với chuỗi ấy.
2. **Chính xác với số thập phân gốc mà người dùng nhập trước khi chuyển thành `double`:** không bảo đảm.
3. **Chính xác với mọi bit của giá trị binary64 khi khai triển thành phân số decimal:** không. Muốn khai triển decimal chính xác của giá trị binary64, constructor `new BigDecimal(double)` có ngữ nghĩa đó.
4. **Chính xác với kết quả toán học lý tưởng trước các phép toán `double`:** không thể khẳng định.

Vì vậy `valueOf` hữu ích, nhưng nó là **chuyển đổi từ trạng thái hiện có**, không phải cơ chế khôi phục lịch sử đầu vào.

## 4. Ba cách tạo `BigDecimal` và điểm khác biệt

| Cách tạo | Nguồn ý nghĩa | Kết quả với ví dụ 0.1 |
|---|---|---|
| `new BigDecimal("0.1")` | Chuỗi decimal chính xác | Giá trị 0.1, scale 1 |
| `BigDecimal.valueOf(0.1)` | Decimal chuẩn từ `Double.toString` của `double` | Giá trị 0.1, scale 1 |
| `new BigDecimal(0.1)` | Khai triển chính xác giá trị binary64 đã được lưu | Decimal dài hơn, không bằng đúng 0.1 |
| `BigDecimal.valueOf(1L)` | Số nguyên `long` | Số nguyên 1 chính xác |
| `BigDecimal.valueOf(12345L, 2)` | Số nguyên không chia tỷ lệ + scale | 123.45 chính xác |

Biểu diễn decimal chính xác của mẫu binary64 gần 0.1 là:

```text
0.1000000000000000055511151231257827021181583404541015625
```

Đây là giá trị của `new BigDecimal(0.1)`, **không phải** chuỗi mà `Double.toString(0.1)` in ra.

### Phân biệt overload `valueOf(double)` và `valueOf(long)`

`BigDecimal.valueOf(123L)` nhận một **số nguyên `long`** nên có thể giữ chính xác mọi giá trị `long`. Đừng ép số nguyên lớn qua `double` trước khi tạo decimal:

```java
long original = 9_007_199_254_740_993L;

BigDecimal exact = BigDecimal.valueOf(original);
BigDecimal potentiallyRounded =
        BigDecimal.valueOf((double) original);
```

`original` vượt vùng mà mọi số nguyên liên tiếp đều biểu diễn chính xác dưới dạng binary64, nên đường qua `double` đã mất thông tin.

Ngoài ra, `BigDecimal.valueOf(unscaledValue, scale)` rất hữu ích để tạo số decimal chính xác từ đơn vị nhỏ nhất, ví dụ số xu, mà không đi qua số thực nhị phân.

## 5. Ví dụ Java 17+ số 1: thấy rõ ba cách tạo

Tạo tệp `ValueOfBasicsDemo.java`:

```java
import java.math.BigDecimal;

public class ValueOfBasicsDemo {
    public static void main(String[] args) {
        BigDecimal fromText = new BigDecimal("0.1");
        BigDecimal valueOf = BigDecimal.valueOf(0.1);
        BigDecimal fromBinary = new BigDecimal(0.1);

        System.out.println("text: " + fromText.toPlainString());
        System.out.println("valueOf: " + valueOf.toPlainString());
        System.out.println("binary exact: "
                + fromBinary.toPlainString());

        System.out.println("text equals valueOf: "
                + fromText.equals(valueOf));
        System.out.println("text equals binary: "
                + fromText.equals(fromBinary));

        double sum = 0.1 + 0.2;
        System.out.println("double sum: " + sum);
        System.out.println("valueOf(sum): "
                + BigDecimal.valueOf(sum).toPlainString());
        System.out.println("decimal sum: "
                + new BigDecimal("0.1")
                        .add(new BigDecimal("0.2"))
                        .toPlainString());

        System.out.println("valueOf(12345, 2): "
                + BigDecimal.valueOf(12345L, 2).toPlainString());
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac ValueOfBasicsDemo.java
java ValueOfBasicsDemo
```

Kết quả:

```text
text: 0.1
valueOf: 0.1
binary exact: 0.1000000000000000055511151231257827021181583404541015625
text equals valueOf: true
text equals binary: false
double sum: 0.30000000000000004
valueOf(sum): 0.30000000000000004
decimal sum: 0.3
valueOf(12345, 2): 123.45
```

Trong ví dụ, `new BigDecimal("0.1")` và `BigDecimal.valueOf(0.1)` bằng nhau, nhưng điều đó chỉ xảy ra vì chuỗi chuẩn của giá trị binary64 gần 0.1 là `"0.1"`. Đừng suy rộng rằng `valueOf` luôn hồi phục được chuỗi thập phân gốc hoặc tự động làm tròn về “giá trị dễ nhìn”.

## 6. Sai số do **phép tính `double` đã hoàn tất** trước khi gọi `valueOf`

Đây là giới hạn quan trọng nhất.

So sánh hai luồng dữ liệu:

**Luồng A — decimal chính xác ngay từ đầu:**

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal total = a.add(b); // 0.3
```

**Luồng B — tính bằng binary64 rồi mới chuyển:**

```java
double a = 0.1;
double b = 0.2;
double total = a + b;
BigDecimal converted = BigDecimal.valueOf(total);
// 0.30000000000000004
```

Ở luồng B, phép cộng đã chạy với quy tắc floating-point. `valueOf` không biết nguồn ban đầu của hai số là literal decimal 0.1 và 0.2, cũng không được thông báo rằng nghiệp vụ muốn 1 chữ số thập phân.

Tương tự:

```java
double third = 1.0 / 3.0;
BigDecimal saved = BigDecimal.valueOf(third);
// 0.3333333333333333
```

`saved` là decimal hữu hạn với 16 chữ số 3 sau dấu chấm. **Không thể coi nó là biểu diễn chính xác phân số toán học 1/3**, vì phân số đó có khai triển decimal vô hạn.

### “Chuyển sang `BigDecimal` rồi tính tiếp” có hữu ích không?

Có, nếu bạn hiểu ranh giới độ chính xác:

- Các phép toán `BigDecimal` **sau thời điểm chuyển** có thể sử dụng decimal của đối tượng và chính sách làm tròn do bạn xác định.
- **Sai số đã có trong giá trị `double` đầu vào sẽ đi theo** trong dữ liệu `BigDecimal` được tạo từ đó.
- Nếu còn chuỗi decimal gốc hoặc dữ liệu nguyên chính xác, **nên tạo `BigDecimal` trực tiếp từ nguồn đó** thay vì qua `double`.

Không nên gọi `setScale(2, ...)` tùy ý rồi tuyên bố “đã sửa hoàn toàn sai số”. Làm tròn có thể đúng nếu nghiệp vụ quy định 2 chữ số, nhưng đó là **một quyết định nghiệp vụ**, không phải bằng chứng giá trị gốc đã phục hồi.

## 7. Mất số nguyên lớn: giới hạn 53 bit phần trị

Binary64 có 53 bit độ chính xác phần trị. Mọi số nguyên có trị tuyệt đối không quá \(2^{53}\) được biểu diễn chính xác, nhưng **không phải mọi số nguyên liên tiếp lớn hơn giới hạn ấy** đều chính xác.

Giá trị:

\[
2^{53} = 9\,007\,199\,254\,740\,992
\]

là một số nguyên được biểu diễn chính xác. Số kế tiếp \(2^{53}+1\) **không** được biểu diễn chính xác bằng `double` và sẽ bị làm tròn.

Ví dụ:

```java
long original = 9_007_199_254_740_993L;
double rounded = (double) original;

BigDecimal wrong = BigDecimal.valueOf(rounded);
BigDecimal right = BigDecimal.valueOf(original);
```

`wrong` chứa 9_007_199_254_740_992, còn `right` chứa đúng 9_007_199_254_740_993.

**Bài học cho hệ thống:** không chuyển ID số nguyên lớn, số xu, bộ đếm, timestamp nanosecond hoặc số nguyên quan trọng sang `double` chỉ để dùng `BigDecimal.valueOf` sau đó. Nếu nguồn là `long`, hãy gọi trực tiếp `BigDecimal.valueOf(long)`.

### JavaScript/JSON và API trung gian

Một hệ thống khác có thể gửi số JSON qua runtime dùng number nhị phân 64 bit. Nếu dữ liệu đã bị làm tròn ở một bên, server Java **không thể khôi phục chữ số bằng `BigDecimal.valueOf`**. Đối với ID hoặc số tiền chính xác, cần quy định kiểu truyền phù hợp như chuỗi decimal hoặc đối tượng có số nguyên/đơn vị rõ ràng.

Điểm mấu chốt là **tính chính xác đầu-cuối**: Java chỉ bảo toàn được dữ liệu gốc nếu các bước trước đó cũng bảo toàn nó.

## 8. Ví dụ Java 17+ số 2: mất số nguyên và chữ số decimal gốc

Tạo tệp `SourcePrecisionDemo.java`:

```java
import java.math.BigDecimal;

public class SourcePrecisionDemo {
    public static void main(String[] args) {
        long exactId = 9_007_199_254_740_993L;
        double roundedId = (double) exactId;

        System.out.println("long source: " + exactId);
        System.out.println("double as long: " + (long) roundedId);
        System.out.println("via double: "
                + BigDecimal.valueOf(roundedId).toPlainString());
        System.out.println("via long: "
                + BigDecimal.valueOf(exactId).toPlainString());

        String preciseText = "0.1000000000000000000001";
        BigDecimal direct = new BigDecimal(preciseText);
        BigDecimal viaDouble =
                BigDecimal.valueOf(Double.parseDouble(preciseText));

        System.out.println("from decimal text: "
                + direct.toPlainString());
        System.out.println("after double parse: "
                + viaDouble.toPlainString());
        System.out.println("same decimal value: "
                + (direct.compareTo(viaDouble) == 0));
    }
}
```

Chạy:

```bash
javac SourcePrecisionDemo.java
java SourcePrecisionDemo
```

Kết quả:

```text
long source: 9007199254740993
double as long: 9007199254740992
via double: 9007199254740992
via long: 9007199254740993
from decimal text: 0.1000000000000000000001
after double parse: 0.1
same decimal value: false
```

Ở trường hợp decimal dài, `Double.parseDouble` chỉ giữ giá trị binary64 gần nhất, tương ứng chuỗi chuẩn `"0.1"`. Khi chuyển bằng `valueOf`, chữ số `...0001` cuối trong nguồn **không tồn tại trong đầu vào nữa**.

Đây là lý do **dữ liệu yêu cầu decimal chính xác phải được parse thành decimal chính xác ngay từ đầu**.

## 9. Số 0 cuối và `scale` cũng có thể bị mất

Một lỗi khác tinh tế hơn sai số số học: **giá trị số có thể giữ được nhưng cách biểu diễn và `scale` không giữ được**.

Giả sử nguồn vào là chuỗi:

```text
"19.90"
```

Nếu bạn parse nó qua `double`:

```java
double d = Double.parseDouble("19.90");
System.out.println(Double.toString(d)); // 19.9

BigDecimal fromDouble = BigDecimal.valueOf(d);
System.out.println(fromDouble);         // 19.9
System.out.println(fromDouble.scale()); // 1
```

Trong khi đó:

```java
BigDecimal fromText = new BigDecimal("19.90");
System.out.println(fromText);         // 19.90
System.out.println(fromText.scale()); // 2
```

Hai đối tượng có giá trị toán học bằng nhau, nhưng:

```java
System.out.println(fromDouble.compareTo(fromText)); // 0
System.out.println(fromDouble.equals(fromText));    // false
```

**Vì sao?** `compareTo` so giá trị số, còn `equals` của `BigDecimal` xét cả **scale**. `double` không mang thông tin “người nhập đã viết bao nhiêu chữ số 0 sau dấu chấm”.

Nếu scale có ý nghĩa trong hóa đơn, dữ liệu lưu hoặc giao thức, **phải giữ chuỗi gốc hoặc metadata về scale**. `valueOf` không thể suy đoán rằng 19.9 trước kia được viết 19.90 hay 19.9000.

### Giải thích scale ngắn gọn

Một `BigDecimal` có thể biểu diễn bằng:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

`new BigDecimal("19.90")` có phần trị nguyên 1990 và scale 2. `BigDecimal.valueOf(19.9)` có phần trị nguyên 199 và scale 1. Cả hai biểu diễn cùng giá trị toán học 19.9, nhưng **hợp đồng biểu diễn** khác nhau.

## 10. `BigDecimal.valueOf(double)` không mang khái niệm NaN hoặc Infinity

Kiểu `double` có các giá trị đặc biệt:

- `Double.NaN`.
- `Double.POSITIVE_INFINITY`.
- `Double.NEGATIVE_INFINITY`.

Nhưng `BigDecimal` **không có giá trị NaN hay ±Infinity** trong mô hình decimal của lớp. Vì vậy:

```java
// BigDecimal.valueOf(Double.NaN);               // NumberFormatException
// BigDecimal.valueOf(Double.POSITIVE_INFINITY); // NumberFormatException
// BigDecimal.valueOf(Double.NEGATIVE_INFINITY); // NumberFormatException
```

Các dòng trên bị comment để ví dụ không dừng chương trình. `BigDecimal.valueOf` không âm thầm biến NaN thành số 0 hay Infinity thành số lớn nhất.

Tình huống phổ biến:

```java
double invalid = 0.0 / 0.0; // NaN
// BigDecimal result = BigDecimal.valueOf(invalid);
// khi chạy sẽ ném NumberFormatException
```

Vì thế, với `double` đến từ đầu vào không tin cậy hoặc chuỗi tính toán có nguy cơ tràn, hãy kiểm tra trước:

```java
static BigDecimal requireFiniteDecimal(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException(
                "NaN or infinity is not a decimal value");
    }
    return BigDecimal.valueOf(value);
}
```

Đây là phương thức **minh họa** cần được đặt bên trong class có import `java.math.BigDecimal`. Kiểm tra `Double.isFinite` chỉ bảo đảm đối số có thể chuyển thành một decimal hữu hạn; nó **không chứng minh nguồn được biểu diễn chính xác**.

## 11. Overflow và underflow trước khi gọi `valueOf`

### 11.1. Overflow: giá trị hữu hạn biến thành Infinity

`double` có giới hạn độ lớn. Ví dụ:

```java
double source = Double.MAX_VALUE;
double overflowed = source * 2.0;

System.out.println(Double.isFinite(source)); // true
System.out.println(Double.isFinite(overflowed)); // false
```

Tích của hai số hữu hạn có thể tràn thành +Infinity. Sau bước này `BigDecimal.valueOf(overflowed)` sẽ ném `NumberFormatException` thay vì tự suy ra kết quả decimal vô cùng lớn.

Nếu bài toán yêu cầu tính toán chính xác với những số vượt miền `double` và **dữ liệu gốc còn chính xác**, cần chuyển vào `BigDecimal` trước phép nhân, thay vì dùng kết quả Infinity làm đầu vào.

### 11.2. Underflow: giá trị quá nhỏ biến thành 0.0

Số dương nhỏ nhất khác 0 của `double` là `Double.MIN_VALUE` (một số dưới chuẩn dương). Nếu chia cho 2, kết quả được làm tròn về 0:

```java
double smallest = Double.MIN_VALUE;
double underflowed = smallest / 2.0;

System.out.println(underflowed); // 0.0
System.out.println(Double.isFinite(underflowed)); // true
```

Sau đó:

```java
BigDecimal converted = BigDecimal.valueOf(underflowed);
// giá trị decimal 0.0
```

Phần thông tin khác 0 đã mất **trước khi gọi `valueOf`**. Vì 0.0 vẫn hữu hạn, chỉ kiểm tra `isFinite` không phát hiện underflow.

**Phân biệt thêm:** `BigDecimal.valueOf(Double.MIN_VALUE)` được tạo từ chuỗi chuẩn `Double.toString(Double.MIN_VALUE)`, thông thường in `4.9E-324`. Đó là decimal ngắn round-trip về `Double.MIN_VALUE`, không phải toàn bộ khai triển decimal chính xác của bit pattern nhị phân cực nhỏ ấy.

## 12. Số 0 có dấu: `double` phân biệt nhưng `BigDecimal` không

IEEE 754 binary64 có hai mẫu bit cho số 0:

- +0.0.
- -0.0.

Theo so sánh số học `double`:

```java
System.out.println(0.0 == -0.0); // true
System.out.println(1.0 / 0.0);   // Infinity
System.out.println(1.0 / -0.0);  // -Infinity
```

Trong khi đó, `BigDecimal` có **số 0 decimal** nhưng không lưu **bit dấu âm của zero** như kiểu floating-point. Vì vậy:

```java
BigDecimal plus = BigDecimal.valueOf(0.0);
BigDecimal minus = BigDecimal.valueOf(-0.0);

System.out.println(plus.equals(minus)); // true
System.out.println(minus.toPlainString()); // 0.0
```

`Double.toString(-0.0)` có thể chứa dấu âm `"-0.0"`, nhưng khi được parse thành `BigDecimal`, giá trị decimal 0 không giữ một dấu âm tách biệt. Nếu một giao thức yêu cầu phân biệt chính xác **mẫu bit +0.0 và -0.0**, bạn phải lưu mẫu bit `double` riêng, ví dụ qua `Double.doubleToRawLongBits`, thay vì trông chờ `BigDecimal` bảo toàn chi tiết đó.

Đây là một ví dụ khác cho thấy **valueOf chuyển đổi giá trị**, không bảo toàn toàn bộ thông tin biểu diễn của `double`.

## 13. Ví dụ Java 17+ số 3: các trường hợp đặc biệt

Tạo tệp `FloatingBoundaryDemo.java`:

```java
import java.math.BigDecimal;

public class FloatingBoundaryDemo {
    private static void tryConvert(String label, double value) {
        try {
            System.out.println(label + " -> "
                    + BigDecimal.valueOf(value).toString());
        } catch (NumberFormatException e) {
            System.out.println(label + " -> NumberFormatException");
        }
    }

    public static void main(String[] args) {
        double overflow = Double.MAX_VALUE * 2.0;
        double underflow = Double.MIN_VALUE / 2.0;

        System.out.println("overflow finite: "
                + Double.isFinite(overflow));
        System.out.println("underflow: " + underflow);
        System.out.println("underflow finite: "
                + Double.isFinite(underflow));

        tryConvert("NaN", Double.NaN);
        tryConvert("+Infinity", Double.POSITIVE_INFINITY);
        tryConvert("-Infinity", Double.NEGATIVE_INFINITY);
        tryConvert("underflowed zero", underflow);

        BigDecimal negativeZero =
                BigDecimal.valueOf(-0.0);
        BigDecimal positiveZero =
                BigDecimal.valueOf(+0.0);

        System.out.println("zero decimals equal: "
                + negativeZero.equals(positiveZero));
        System.out.println("negative zero converted: "
                + negativeZero.toPlainString());
        System.out.println("double raw zero bits equal: "
                + (Double.doubleToRawLongBits(-0.0)
                    == Double.doubleToRawLongBits(+0.0)));
    }
}
```

Biên dịch và chạy:

```bash
javac FloatingBoundaryDemo.java
java FloatingBoundaryDemo
```

Kết quả:

```text
overflow finite: false
underflow: 0.0
underflow finite: true
NaN -> NumberFormatException
+Infinity -> NumberFormatException
-Infinity -> NumberFormatException
underflowed zero -> 0.0
zero decimals equal: true
negative zero converted: 0.0
double raw zero bits equal: false
```

Ví dụ cho thấy `BigDecimal.valueOf` không thể biến một giá trị Infinity hoặc NaN thành decimal. Nó cũng không thể phục hồi một số rất nhỏ đã underflow về 0, và không bảo toàn thông tin dấu âm của zero.

## 14. Cẩn thận khi lấy `double` từ chuỗi, JSON và database

Có hai luồng parse rất khác nhau.

### Luồng A: đọc trực tiếp chuỗi decimal chính xác

```java
String text = "12345678901234567890.1234500";
BigDecimal value = new BigDecimal(text);
```

Kết quả giữ **đúng các chữ số decimal và scale từ chuỗi**, miễn là cú pháp hợp lệ và tài nguyên đủ. Điều này phù hợp với các dữ liệu mà hợp đồng yêu cầu bảo toàn decimal.

### Luồng B: đọc qua `double` trước

```java
String text = "12345678901234567890.1234500";
double approximate = Double.parseDouble(text);
BigDecimal value = BigDecimal.valueOf(approximate);
```

Trong luồng B, nhiều chữ số có thể đã bị làm tròn khi `Double.parseDouble` tạo binary64. `BigDecimal.valueOf` không thể lấy lại các chữ số ấy, dù đối tượng `BigDecimal` sau đó có khả năng chứa decimal dài.

Với JSON, spreadsheet, database hay giao diện người dùng, bạn cần xác định:

- Parser có map trường số sang `double`, `BigDecimal` hay một kiểu khác?
- Có yêu cầu giữ **giá trị decimal** hoặc **scale và các số 0 cuối** không?
- Đầu vào có thể lớn hơn miền `double` hay hơn 53 bit chính xác phần nguyên không?
- JSON number do một runtime khác tạo có thể đã bị làm tròn ở phía gửi hay không?
- Với cột database `DECIMAL/NUMERIC`, driver/ORM có trả `BigDecimal` trực tiếp hay đã chuyển qua kiểu số thực?

**Khuyến nghị thực tế:** nếu giá trị là tiền, tỷ lệ được quy định theo decimal hoặc một trường dữ liệu có yêu cầu chính xác, hãy **truyền nhận và parse trực tiếp bằng `BigDecimal` hoặc số nguyên có đơn vị**, thay vì đi qua `double` không cần thiết.

### Số 0 cuối trong dữ liệu tài chính

Nếu hệ thống nhận `"19.90"`, `BigDecimal.valueOf(Double.parseDouble("19.90"))` tạo 19.9. Điều đó có thể bằng nhau về giá trị nhưng khác scale với `new BigDecimal("19.90")`. Khi scale là một phần hợp đồng lưu trữ hoặc hiển thị, không thể bỏ qua khác biệt này.

## 15. Làm tròn có thể đúng nhưng phải là quy tắc đã chọn

Một số người giải quyết sai số `double` bằng:

```java
BigDecimal amount = BigDecimal.valueOf(value)
        .setScale(2, java.math.RoundingMode.HALF_UP);
```

Cách này **hợp lệ nếu** nghiệp vụ quy định làm tròn đến 2 chữ số decimal bằng `HALF_UP`. Nhưng cần hiểu:

1. `value` đã có giá trị binary64; lỗi do nguồn có thể đã xảy ra.
2. `BigDecimal.valueOf(value)` lấy decimal chuẩn từ giá trị ấy.
3. `setScale(2, HALF_UP)` **làm tròn giá trị decimal đó**, không hứa khôi phục dữ liệu nguồn.
4. Nếu ứng dụng cần làm tròn theo một chuẩn khác, `HALF_EVEN` hoặc chính sách khác có thể đúng hơn.

### Ví dụ điểm giữa

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal a = new BigDecimal("2.675");
BigDecimal b = BigDecimal.valueOf(2.675);
BigDecimal c = new BigDecimal(2.675);
```

Đây là **đoạn mã minh họa trong phương thức**, cần có import tương ứng. `a` và `b` có giá trị decimal 2.675; `c` biểu diễn chính xác giá trị binary64 xấp xỉ 2.675 (nằm dưới 2.675 toán học một chút).

Khi làm tròn hai chữ số sau dấu chấm bằng `HALF_UP`:

- `a.setScale(2, HALF_UP)` → **2.68**.
- `b.setScale(2, HALF_UP)` → **2.68**.
- `c.setScale(2, HALF_UP)` → **2.67**.

Ví dụ này không chứng minh `valueOf` “chữa được binary64”. Nó cho thấy **hai cách diễn giải nguồn binary64 thành decimal khác nhau**, và thời điểm chuyển dữ liệu quyết định số được đem đi làm tròn.

Nếu đầu vào ban đầu là chuỗi `"2.675"`, cách ít nhập nhằng nhất là `new BigDecimal("2.675")`. Nếu đầu vào chỉ còn là một `double` sau nhiều phép tính, cần xác định liệu làm tròn decimal dạng `Double.toString` có phù hợp nghiệp vụ hay không.

## 16. Chương trình Java 17+ số 4: parse, scale và làm tròn

Tạo tệp `DecimalInputPolicyDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalInputPolicyDemo {
    public static void main(String[] args) {
        String text = "19.90";
        BigDecimal exact = new BigDecimal(text);
        BigDecimal viaDouble = BigDecimal.valueOf(
                Double.parseDouble(text));

        System.out.println("direct decimal: "
                + exact.toPlainString());
        System.out.println("via double: "
                + viaDouble.toPlainString());
        System.out.println("direct scale: " + exact.scale());
        System.out.println("via double scale: " + viaDouble.scale());
        System.out.println("numeric compare: "
                + exact.compareTo(viaDouble));
        System.out.println("equals: "
                + exact.equals(viaDouble));

        BigDecimal directRounded =
                new BigDecimal("2.675")
                        .setScale(2, RoundingMode.HALF_UP);
        BigDecimal valueOfRounded =
                BigDecimal.valueOf(2.675)
                        .setScale(2, RoundingMode.HALF_UP);
        BigDecimal constructorRounded =
                new BigDecimal(2.675)
                        .setScale(2, RoundingMode.HALF_UP);

        System.out.println("direct rounding: "
                + directRounded);
        System.out.println("valueOf rounding: "
                + valueOfRounded);
        System.out.println("constructor rounding: "
                + constructorRounded);

        System.out.println("cents exact: "
                + BigDecimal.valueOf(1990L, 2)
                        .toPlainString());
    }
}
```

Biên dịch và chạy:

```bash
javac DecimalInputPolicyDemo.java
java DecimalInputPolicyDemo
```

Kết quả:

```text
direct decimal: 19.90
via double: 19.9
direct scale: 2
via double scale: 1
numeric compare: 0
equals: false
direct rounding: 2.68
valueOf rounding: 2.68
constructor rounding: 2.67
cents exact: 19.90
```

Ví dụ cho thấy điều mất đi không chỉ có thể là chữ số giá trị, mà còn là **scale và ý nghĩa của số 0 cuối**. Khi dữ liệu gốc cần giữ 2 chữ số decimal, mô hình `BigDecimal.valueOf(1990L, 2)` cũng có thể hợp lý vì nó nhận số nguyên đơn vị nhỏ nhất chính xác.

## 17. `valueOf(double)` không phải cách kiểm tra dữ liệu có hợp lệ không

Một đầu vào `double` hữu hạn vẫn có thể:

- Âm trong khi nghiệp vụ chỉ chấp nhận số dương.
- Quá lớn so với hạn mức thực tế.
- Có phần lẻ trong khi cần số nguyên.
- Đã bị làm tròn so với nguồn decimal.
- Có precision thấp hơn yêu cầu.
- Có giá trị -0.0 cần xử lý đặc biệt.
- Có scale gốc đã mất.

Vì vậy phương thức chuyển đổi chỉ nên là **một bước** trong pipeline. Ví dụ:

```java
static BigDecimal convertMeasuredRate(double input) {
    if (!Double.isFinite(input)) {
        throw new IllegalArgumentException("non-finite rate");
    }
    if (input < 0.0 || input > 1.0) {
        throw new IllegalArgumentException("rate outside 0..1");
    }
    return BigDecimal.valueOf(input);
}
```

Đây là một **phương thức minh họa** đặt trong class với import `BigDecimal`. Nó kiểm tra hữu hạn và giới hạn [0, 1], nhưng **không bảo đảm chính xác decimal theo nguồn**. Nó chỉ phù hợp nếu nghiệp vụ chấp nhận cách chuyển từ số đo/xác suất xấp xỉ `double` sang decimal chuẩn.

Nếu nhu cầu là một **tỷ lệ thập phân chính xác do người dùng nhập**, API nên nhận `String` hoặc `BigDecimal` ngay tại ranh giới, để không mất dữ liệu đầu vào:

```java
static BigDecimal parseExactRate(String text) {
    BigDecimal value = new BigDecimal(text);
    if (value.compareTo(BigDecimal.ZERO) < 0
            || value.compareTo(BigDecimal.ONE) > 0) {
        throw new IllegalArgumentException("rate outside 0..1");
    }
    return value;
}
```

Không nên dùng `Double.parseDouble` rồi `BigDecimal.valueOf` ở đây nếu yêu cầu là giữ đúng decimal gốc.

## 18. Sử dụng `BigDecimal.valueOf(double)` khi nào là phù hợp?

Những tình huống có thể phù hợp:

1. **Hệ thống đã có dữ liệu dạng `double` theo thiết kế**, ví dụ giá trị đo, kết quả phân tích thống kê, hoặc API thư viện chỉ trả `double`. Bạn chấp nhận rằng binary64 đã xác định giá trị hiện có.
2. Cần một **biểu diễn decimal ngắn và dễ đọc** theo `Double.toString` thay vì khai triển decimal dài chính xác của các bit binary64.
3. Muốn thực hiện các bước số học decimal tiếp theo theo một chính sách rõ ràng, **mà vẫn thừa nhận độ chính xác nguồn chỉ là `double`**.
4. Muốn lưu **một giá trị gần với thông tin mà `Double.toString` truyền đạt**, không phải những chữ số có thể đã mất trước đó.

Những tình huống **không nên xem là giải pháp đủ**:

- Chuỗi tiền tệ gốc cần giữ đúng số lẻ và scale.
- ID nguyên lớn, số đếm lớn, hoặc timestamps có độ chính xác vượt khả năng binary64.
- Các phép toán cần chính xác decimal ngay từ đầu.
- Giá trị đã overflow thành Infinity, underflow thành 0 hoặc rơi vào NaN.
- Đầu vào từ hệ thống khác đã làm tròn mà bạn cần chứng minh tính toàn vẹn dữ liệu.

### So sánh lựa chọn API

| Dữ liệu hiện có | API gợi ý | Bảo toàn gì? |
|---|---|---|
| `String "19.90"` | `new BigDecimal("19.90")` | Decimal gốc và scale |
| `long cents = 1990` | `BigDecimal.valueOf(cents, 2)` | Số nguyên chính xác với scale 2 |
| `long count` | `BigDecimal.valueOf(count)` | Mọi giá trị `long` chính xác |
| `double rate` đã được phép là xấp xỉ | `BigDecimal.valueOf(rate)` | Decimal chuẩn từ `Double.toString(rate)` |
| `double d` cần khai triển decimal chính xác của giá trị nhị phân | `new BigDecimal(d)` | Giá trị binary64 thực sự |
| `double` NaN/Infinity | Không thể tạo một `BigDecimal` bình thường | Cần từ chối hoặc biểu diễn trạng thái riêng |

Đặc biệt với dữ liệu decimal từ JSON, CSV, giao diện hoặc database, **hợp đồng dữ liệu phải xác định kiểu đầu vào trước khi chọn overload**. Đừng chọn `valueOf(double)` chỉ vì dễ viết.

## 19. Những lỗi phổ biến

| Nhầm lẫn | Thực tế | Cách giải quyết |
|---|---|---|
| `BigDecimal.valueOf(0.1 + 0.2)` thành 0.3 | Kết quả `double` đã là 0.30000000000000004 | Tính bằng `BigDecimal` từ nguồn decimal trước |
| `valueOf(double)` luôn ghi lại chính xác bit binary64 | Nó dùng decimal chuẩn từ `Double.toString` | Dùng `new BigDecimal(d)` nếu thật sự cần khai triển bit-value |
| `valueOf` khôi phục chữ số decimal đã mất | Không có thông tin đầu vào gốc | Parse trực tiếp chuỗi decimal |
| `valueOf((double) longBig)` giữ nguyên mọi số nguyên | Binary64 có giới hạn 53 bit phần trị | Dùng `valueOf(long)` |
| `valueOf(Double.NaN)` trả decimal NaN | `BigDecimal` không có NaN | Kiểm tra `Double.isFinite` và xử lý lỗi |
| `valueOf(Double.POSITIVE_INFINITY)` tự giới hạn thành MAX | Không có saturation kiểu đó; ném `NumberFormatException` | Xử lý infinity trước |
| Underflow về 0 vẫn khôi phục được số nhỏ ban đầu | Nguồn đã thành 0.0 | Xử lý decimal hoặc kiểu phù hợp trước |
| `valueOf(-0.0)` giữ dấu âm zero | `BigDecimal` không giữ signed zero | Lưu mẫu `double` riêng nếu cần |
| Decimal `"19.90"` qua `double` vẫn scale 2 | `Double.toString` in 19.9 | Giữ `String` hoặc tạo decimal với scale rõ |
| `equals` và `compareTo` luôn tương đương | `equals` xét cả scale | Chọn phép so theo mục tiêu |
| `setScale(2)` tự sửa chính xác nguồn | Đó là quy tắc làm tròn trên decimal đã có | Đặt rounding theo yêu cầu nghiệp vụ |
| `Double.isFinite` chứng minh decimal chính xác | Chỉ loại NaN/Infinity | Kiểm tra nguồn và precision riêng |
| Mọi hệ thống JSON truyền number giống nhau | Các runtime/parser có thể làm tròn ở bước khác | Quy định giao thức kiểu và đơn vị |

## 20. Tự kiểm tra

**Câu 1.** `BigDecimal.valueOf(0.1)` có bằng `new BigDecimal("0.1")` theo `equals` không?  
**Đáp án:** Có, trong trường hợp này cả hai có giá trị 0.1 và scale 1.

**Câu 2.** `new BigDecimal(0.1)` có phải decimal 0.1 chính xác không?  
**Đáp án:** Không. Nó lưu khai triển decimal chính xác của giá trị binary64 gần 0.1, dài hơn 0.1.

**Câu 3.** Vì sao `BigDecimal.valueOf(0.1 + 0.2)` không ra 0.3?  
**Đáp án:** Vì phép cộng `double` xảy ra trước, cho 0.30000000000000004. `valueOf` dùng biểu diễn decimal chuẩn của kết quả đã tính.

**Câu 4.** Nếu nhập chuỗi `"19.90"` và cần bảo toàn scale 2, nên làm gì?  
**Đáp án:** Dùng `new BigDecimal("19.90")` trực tiếp, không parse qua `double`.

**Câu 5.** `BigDecimal.valueOf(9_007_199_254_740_993L)` khác `BigDecimal.valueOf((double) 9_007_199_254_740_993L)` ở đâu?  
**Đáp án:** Overload `long` giữ đúng 9_007_199_254_740_993; đường qua `double` bị làm tròn xuống 9_007_199_254_740_992.

**Câu 6.** `BigDecimal.valueOf(Double.NaN)` có thành công không?  
**Đáp án:** Không. `BigDecimal` không có giá trị NaN; phương thức ném `NumberFormatException`.

**Câu 7.** Nếu `double` underflow về 0 trước khi chuyển, `valueOf` có thể lấy lại số dương rất nhỏ không?  
**Đáp án:** Không. Giá trị truyền vào đã bằng 0.0.

**Câu 8.** `BigDecimal.valueOf(-0.0)` và `BigDecimal.valueOf(+0.0)` có giữ hai dấu zero khác nhau không?  
**Đáp án:** Không. Chúng bằng nhau theo `equals`; `BigDecimal` không biểu diễn signed zero riêng.

**Câu 9.** Khi nào `new BigDecimal(d)` có thể hữu ích hơn `valueOf(d)`?  
**Đáp án:** Khi cần khai triển decimal **chính xác giá trị binary64** đang lưu, ví dụ phân tích sai số hoặc kiểm thử biểu diễn; không phải khi muốn khôi phục decimal nguồn.

**Câu 10.** Có phải `BigDecimal.valueOf(2.675).setScale(2, HALF_UP)` luôn có cùng kết quả với `new BigDecimal(2.675).setScale(2, HALF_UP)`?  
**Đáp án:** Không. Với ví dụ này, cách đầu làm tròn 2.675 thành 2.68, còn constructor `double` dùng giá trị binary64 hơi nhỏ hơn 2.675 nên thành 2.67.

**Câu 11.** `BigDecimal.valueOf(12345L, 2)` cho gì?  
**Đáp án:** Decimal chính xác 123.45, vì đầu vào là số nguyên `long` và scale 2.

**Câu 12.** `Double.isFinite(d)` có bảo đảm `BigDecimal.valueOf(d)` khôi phục được chuỗi decimal gốc không?  
**Đáp án:** Không. `isFinite` chỉ kiểm tra số không phải NaN/Infinity; precision hoặc scale có thể đã mất từ trước.

## 21. Checklist khi đưa `double` vào hệ thống decimal

Trước khi chọn `BigDecimal.valueOf(double)`, kiểm tra:

1. **Dữ liệu gốc là gì?** Chuỗi decimal, `long`, cảm biến hay giá trị tính bằng `double`?
2. **Có cần bảo toàn từng chữ số decimal nguồn không?** Nếu có, parse trực tiếp từ `String` hoặc kiểu decimal.
3. **Có cần giữ scale/số 0 cuối không?** `double` không mang thông tin này.
4. **Giá trị có thể vượt 53 bit chính xác phần nguyên không?** Nếu có, tránh luồng qua binary64.
5. **Đã thực hiện phép tính `double` nào chưa?** Sai số có thể hình thành từ trước.
6. **Có thể là NaN, ±Infinity, underflow về 0 không?** Xử lý trước khi chuyển nếu nghiệp vụ không cho phép.
7. **Có cần giữ signed zero hoặc payload NaN không?** `BigDecimal` không phải định dạng lưu mọi bit IEEE 754.
8. **Cần làm tròn theo quy tắc nào?** Quy định thời điểm, scale và `RoundingMode`.
9. **API/JSON/database có chuyển kiểu ẩn không?** Xác minh toàn bộ đường đi.
10. **Đã có test giá trị biên và dữ liệu gốc cụ thể chưa?** Kiểm thử số 0 cuối, decimal dài, số nguyên lớn, số cực nhỏ, cực lớn và lỗi parse.

**Kết luận:** `BigDecimal.valueOf(double)` là công cụ **chuyển một giá trị binary64 hiện có sang một decimal theo biểu diễn `Double.toString`**. Nó rất hữu ích khi bạn chấp nhận kiểu `double` của nguồn, nhưng **không khôi phục precision, scale, kết quả số học hay thông tin bit đã mất trước đó**. Để tính toán decimal chính xác theo dữ liệu nghiệp vụ, hãy dùng `BigDecimal` hoặc số nguyên theo đơn vị quy định **ngay từ nguồn**.

Tài liệu chính thức:
- [Java SE 17 — BigDecimal.valueOf(double)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html#valueOf(double))
- [Java SE 17 — BigDecimal(double)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html#%3Cinit%3E(double))
- [Java SE 17 — Double.toString(double)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html#toString(double))
- [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html)
