# Tra cứu JLS và Javadoc các API số trong Java: tìm đúng quy tắc, đúng phiên bản, đúng phương thức

## 1. Vì sao cần đọc tài liệu gốc?

Khi gặp một kết quả khó hiểu như `Integer.MAX_VALUE + 1` trở thành số âm, `-7 / 3` ra `-2`, `2.0` khác `2.00` trong `BigDecimal.equals()`, hoặc `Double.MIN_VALUE` lại **dương**, cách đáng tin nhất là lần theo **tài liệu đặc tả chính thức** thay vì suy đoán hoặc chỉ nhìn kết quả trên một máy.

Java có hai nguồn tài liệu quan trọng nhưng **khác mục đích**:

1. **JLS – Java Language Specification:** định nghĩa ngữ nghĩa của **ngôn ngữ Java**: kiểu primitive, toán tử `+`/`-`/`*`/`/`/`%`, promotion, casting, boxing/unboxing, thứ tự đánh giá, so sánh, literal và quy tắc khi chạy biểu thức.
2. **Javadoc – tài liệu API Java SE:** định nghĩa **lớp, hằng, constructor và phương thức thư viện**: `Math.addExact`, `Integer.parseInt`, `Double.isNaN`, `BigDecimal.divide`, `BigInteger.mod`, `RoundingMode.HALF_EVEN`, v.v.

Một truy vấn thường cần cả hai. Ví dụ, để giải thích vì sao `Integer.MAX_VALUE + 1` không tự ném lỗi, hãy tra **JLS** về toán học số nguyên; để biết thay bằng `Math.addExact` thì ngoại lệ gì được ném, hãy tra **Javadoc của `Math`**.

Bài học này là **hướng dẫn tra cứu và đối chiếu**, không phải bản liệt kê tất cả API số. Sau khi học, bạn có thể tự xác định “vấn đề này thuộc JLS hay Javadoc?”, chọn đúng bản Java, tìm đúng đề mục/phương thức, đọc hợp đồng và tạo chương trình Java 17+ để tái hiện kết quả.

## 2. Bản đồ nguồn tài liệu chính thức

| Cần giải đáp | Ưu tiên nguồn | Ví dụ câu hỏi |
|---|---|---|
| Ngữ nghĩa của toán tử `+`, `/`, `%`, `==` | JLS, thường Chương 15 | Vì sao `-7 % 3` là `-1`? |
| Miền primitive và quy tắc floating-point | JLS Chương 4 | `int` có mấy bit? `double` có signed zero? |
| Chuyển kiểu, boxing, unboxing, numeric promotion | JLS Chương 5 | `int + long` ra kiểu gì? `Integer` null bị unbox khi nào? |
| Kiểu và hành vi của `Math.floorDiv`, `addExact` | Javadoc `java.lang.Math` | Phương thức trả gì, ngoại lệ nào? |
| Hằng `MIN_VALUE`, `MAX_VALUE` và parse | Javadoc `Integer`, `Long`, `Double` | `Double.MIN_VALUE` thực ra là gì? |
| Số thập phân chính xác và so sánh giá trị | Javadoc `java.math.BigDecimal` | `equals` khác `compareTo` ở đâu? |
| Số nguyên tùy độ lớn, chia lấy dư | Javadoc `java.math.BigInteger` | `mod` có chấp nhận modulus âm không? |
| Rounding và precision | Javadoc `RoundingMode`, `MathContext` | `HALF_EVEN` xử lý đúng điểm giữa ra sao? |
| Random cho mô phỏng hay token | Javadoc `Random`, `SecureRandom` | Thuật toán có phù hợp bảo mật không? |
| Bytecode/JVM runtime, biểu diễn ở mức máy ảo | JVM Specification (JVMS), khi thật sự cần | Lệnh bytecode, verifier, execution engine |

**JLS không phải Javadoc**, và Javadoc không phải quy tắc của một toán tử tự thân. `BigDecimal.add` là **method call** được mô tả trong Javadoc; `int + int` là **biểu thức** được quy định bởi JLS. Đừng viện dẫn `BigDecimal` để giải thích mặc định phép cộng primitive hay ngược lại.

### Điểm vào cho Java 17 (phù hợp ví dụ trong bài)

- [JLS Java SE 17 – trang chủ](https://docs.oracle.com/javase/specs/jls/se17/html/index.html).
- [JLS Chương 4 – Types, Values, and Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html).
- [JLS Chương 5 – Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html).
- [JLS Chương 15 – Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html).
- [Java SE 17 API documentation – Module `java.base`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/module-summary.html).
- [Javadoc `java.lang.Math`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html).
- [Javadoc `java.math.BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).

Đường dẫn tài liệu **có phiên bản**: `se17` trong JLS và `/javase/17/docs/api/` trong Javadoc. Khi dự án chạy Java 17, hãy bắt đầu với Java 17. Nếu dự án chạy bản khác, chuyển sang **JLS/Javadoc cùng phiên bản**, vì các API mới có thể chưa tồn tại hoặc hành vi/hợp đồng có ghi chú thay đổi.

## 3. Quy trình tra cứu chuẩn: từ biểu thức đến dẫn chứng

Đề xuất quy trình 7 bước có thể áp dụng trong review và debug:

1. **Viết lại câu hỏi thật cụ thể.** Ví dụ: “Ở Java 17, với biến `int a = -7;`, tại sao `a / 3` trả `-2` mà không phải `-3`?”
2. **Phân loại biểu thức.** Toán tử ngôn ngữ hay lời gọi method? Primitive, wrapper hay `BigDecimal`? Có thể có unboxing/promotion không?
3. **Khóa phiên bản JDK.** Lấy `java -version`, `javac -version`; nếu build có `--release 17` hoặc cấu hình toolchain, dùng đúng mức đó để so API.
4. **Mở JLS hoặc Javadoc đúng đề mục.** Với toán tử chia, tới JLS §15.17.2; với `Math.floorDiv`, tìm method trong Javadoc `Math`.
5. **Đọc đầy đủ các điều kiện cạnh và chú thích.** Quan tâm dấu âm, zero, overflow, rounding, loại tham số, `null`, ngoại lệ, và giới hạn của provider/implementation nếu có.
6. **Tạo tái hiện tối thiểu.** Một lớp Java nhỏ, input cố định, in kiểu/giá trị hoặc bắt ngoại lệ có tên; tránh dependency bên ngoài.
7. **Ghi kết luận kèm nguồn và phiên bản.** Trình bày tách bạch: “JLS định nghĩa ...; phương thức API theo Javadoc ...; chạy Java 17 cho kết quả ...”.

Mẫu ghi chú thực tế:

```text
Câu hỏi    : Vì sao -7 / 3 = -2?
Kiểu       : int / int -> int
Nguồn      : JLS SE 17 §15.17.2 (Integer Division Operator /)
Kết luận   : Phép chia nguyên làm tròn thương về 0
Kiểm chứng : javac --release 17, java; in (-7 / 3) được -2
API khác   : Math.floorDiv(-7,3) = -3, tra Javadoc Math.floorDiv
```

Đây là **mẫu ghi chú tra cứu**, không phải lệnh shell. Điểm quan trọng là dẫn **đề mục**, không chỉ đưa link tới một trang chủ quá rộng.

## 4. Đọc JLS số ở đâu?

### 4.1. Chương 4: primitive và miền giá trị

[JLS §4.2 – Primitive Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2) giải thích các kiểu primitive. Những mốc hữu ích:

| Mục JLS 17 | Nội dung nên tra |
|---|---|
| [§4.2.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.1) | Kiểu số nguyên và miền `byte`, `short`, `int`, `long`, `char` |
| [§4.2.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.2) | Các phép toán số nguyên, tràn số nguyên |
| [§4.2.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3) | Kiểu và giá trị floating-point `float`, `double` |
| [§4.2.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.4) | Các phép toán floating-point và quy tắc số học |

**Ví dụ câu hỏi:** “`Double.MIN_VALUE` có phải số âm bé nhất?” Trước tiên tra Javadoc `Double.MIN_VALUE` để hiểu hằng **cụ thể**; dùng JLS §4.2.3–4.2.4 để hiểu miền floating-point, subnormal, zero có dấu và `Infinity`. Chú ý `Double.MIN_VALUE` là **số dương khác 0 nhỏ nhất** biểu diễn được, không phải số hữu hạn âm nhỏ nhất.

### 4.2. Chương 5: kiểu của biểu thức và chuyển đổi

[JLS Chương 5](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html) đặc biệt hữu ích khi thấy kết quả bất ngờ sau casting hoặc boxing:

| Mục | Câu hỏi điển hình |
|---|---|
| [§5.1.2 Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.2) | `int` chuyển sang `long` có chính xác không? `long` sang `double` có thể mất chữ số không? |
| [§5.1.3 Narrowing Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.3) | Ép `long` sang `int` bị mất phần nào? |
| [§5.1.7 Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7) | Khi `int` chuyển thành `Integer`, có tạo object mới không? |
| [§5.1.8 Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8) | `Integer n = null; n + 1` sẽ làm gì? |
| [§5.6 Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6) | Khi `int + double`, operands được promote thế nào? |

**Điểm tinh tế:** chuyển sang kiểu rộng hơn không nhất thiết giữ **mọi bit chính xác số học**. `long` → `double` là *widening primitive conversion* nhưng có thể mất chính xác với số nguyên lớn; nếu đang debug một giá trị `long` gần `2^53`, hãy tra JLS §5.1.2 thay vì cho rằng “widening luôn không mất dữ liệu”.

### 4.3. Chương 15: toán tử và ngữ nghĩa biểu thức

Các mục thường dùng:

- [§15.17 – Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17): `*`, `/`, `%`; đặc biệt [§15.17.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.2) cho phép chia và [§15.17.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17.3) cho phép dư.
- [§15.18 – Additive Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18): phép cộng/trừ (và `+` nối chuỗi); [§15.18.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18.2) cho cộng/trừ số.
- [§15.21 – Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21): so sánh bằng, gồm numeric equality và reference equality.
- [§15.7 – Evaluation Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.7): thứ tự đánh giá các phần của biểu thức.
- [§15.26 – Assignment Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.26): phép gán và compound assignment như `+=`.

Ví dụ dễ nhầm: `byte b = 1; b += 1;` hợp lệ nhưng `b = b + 1;` không biên dịch nếu thiếu ép kiểu, bởi numeric promotion và quy tắc compound assignment không hoàn toàn giống gán đơn. Tra **JLS §5.6** và **§15.26.2** thay vì chỉ đọc Javadoc của `Byte`.

## 5. Đọc Javadoc các API số như thế nào?

Một trang Javadoc điển hình có các phần: **Class/Interface/Enum**, mô tả ở đầu lớp, field/constructor/method summary, rồi **method detail**. Để xác nhận hành vi, đừng chỉ đọc summary một dòng; hãy cuộn tới đúng **overload** và kiểm tra:

- **Signature:** `static`/instance, kiểu tham số, kiểu trả về, overload nhận `int`, `long`, `double`, `BigDecimal` hay `MathContext`.
- **Parameters/Returns:** ý nghĩa `bound`, giá trị âm, giới hạn mở/đóng, thứ tự/scale của kết quả.
- **Throws:** ngoại lệ có thể phát sinh như `ArithmeticException`, `NumberFormatException`, `NullPointerException`.
- **Since:** API xuất hiện từ bản Java nào; rất quan trọng nếu code phải chạy Java 17.
- **API Note / Implementation Requirements / Implementation Note:** đọc khi có, nhưng phân biệt hợp đồng của API với mô tả chi tiết triển khai.
- **See Also:** các API liên quan và lựa chọn thay thế.
- **Mô tả của lớp:** đôi khi quy tắc quan trọng (như `BigDecimal.equals` khác `compareTo`) được nêu ở đầu lớp thay vì lặp lại trong mọi method.

Đừng suy ra hành vi mọi overload chỉ từ tên phương thức. Chẳng hạn `BigDecimal.divide(BigDecimal)`, `divide(BigDecimal, int, RoundingMode)` và `divide(BigDecimal, MathContext)` có **hợp đồng độ chính xác/rounding khác nhau**.

### Bảng điều hướng nhanh

| Lớp / enum | Link Javadoc Java 17 | Nên tra |
|---|---|---|
| `java.lang.Integer` | [Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html) | `MIN_VALUE`, `MAX_VALUE`, `parseInt`, `valueOf`, `compare`, `compareUnsigned` |
| `java.lang.Long` | [Long](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html) | `parseLong`, `valueOf`, `compareUnsigned`, biên 64 bit |
| `java.lang.Double` | [Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html) | `MIN_VALUE`, `MIN_NORMAL`, `isNaN`, `isFinite`, `compare`, `equals` |
| `java.lang.Float` | [Float](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html) | Hằng, parse, so sánh floating-point |
| `java.lang.Math` | [Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html) | `abs`, `floor`, `ceil`, `round`, `floorDiv`, `floorMod`, `addExact`, `nextUp`, `ulp` |
| `java.lang.StrictMath` | [StrictMath](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html) | Hợp đồng độ chính xác/tính tái lập của hàm số học |
| `java.math.BigInteger` | [BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html) | `add`, `divide`, `remainder`, `mod`, `intValueExact` |
| `java.math.BigDecimal` | [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html) | `scale`, `precision`, `equals`, `compareTo`, `divide`, `setScale` |
| `java.math.MathContext` | [MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html) | Precision kết quả và rounding mode |
| `java.math.RoundingMode` | [RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html) | `HALF_EVEN`, `HALF_UP`, `CEILING`, `FLOOR`, `UNNECESSARY` |
| `java.util.Random` | [Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html) | Seed, `nextInt(bound)`, mô phỏng ngẫu nhiên |
| `java.security.SecureRandom` | [SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html) | Sinh dữ liệu khó đoán cho mục tiêu bảo mật |

**Tìm nhanh:** mở class Javadoc và dùng chức năng tìm kiếm trên trang (`Ctrl+F`) theo `methodName` hoặc `fieldName`, rồi chọn đúng overload trong phần **Method Details**; hoặc dùng mục Search của trang Java SE API. Khi phương thức có nhiều overload, ghi đầy đủ kiểu tham số trong ghi chú (ví dụ `divide(BigDecimal, int, RoundingMode)`).

## 6. Tình huống 1: vì sao chia số nguyên âm khác `Math.floorDiv`?

**Câu hỏi:** `-7 / 3` và `Math.floorDiv(-7, 3)` có giống nhau không?

Tra cứu theo hai bước:

1. **JLS §15.17.2** quy định phép chia nguyên `/` làm tròn thương về **0** (*truncation toward zero*). Bởi vậy `-7 / 3 = -2`.
2. **Javadoc `Math.floorDiv`** định nghĩa chia theo hướng **âm vô cực**; bởi vậy `Math.floorDiv(-7, 3) = -3`.

Phép dư `% ` primitive có dấu gắn với phép chia về 0: `-7 % 3 = -1`. `Math.floorMod(-7,3)` tương ứng với `floorDiv`, cho `2`. Nguồn: JLS §15.17.3 và Javadoc `Math.floorMod`.

**Tệp `NumericJlsDemo.java` – Java 17+:**

```java
public class NumericJlsDemo {
    public static void main(String[] args) {
        System.out.println("intDivision=" + (-7 / 3));
        System.out.println("intRemainder=" + (-7 % 3));
        System.out.println("floorDivision=" + Math.floorDiv(-7, 3));
        System.out.println("floorMod=" + Math.floorMod(-7, 3));

        int max = Integer.MAX_VALUE;
        System.out.println("overflow=" + (max + 1));

        try {
            System.out.println(Math.addExact(max, 1));
        } catch (ArithmeticException ex) {
            System.out.println("addExact=ArithmeticException");
        }

        System.out.println("widenedDivision=" + (7.0 / 2));
        System.out.println("integerDivision=" + (7 / 2));
    }
}
```

Lệnh:

```bash
javac --release 17 NumericJlsDemo.java
java NumericJlsDemo
```

Stdout:

```text
intDivision=-2
intRemainder=-1
floorDivision=-3
floorMod=2
overflow=-2147483648
addExact=ArithmeticException
widenedDivision=3.5
integerDivision=3
```

Ở ví dụ này, `7.0 / 2` thực hiện phép chia floating-point sau numeric promotion, còn `7 / 2` là phép chia nguyên. Biểu thức `max + 1` là cộng `int` và bị overflow, không ném ngoại lệ. `Math.addExact(max,1)` **là phương thức API khác**, có hợp đồng ném `ArithmeticException` khi tràn. Đây là lý do hai nguồn JLS/Javadoc phải được đọc phối hợp.

## 7. Tình huống 2: `BigDecimal.equals` khác `compareTo` ở đâu?

**Câu hỏi:** Vì sao `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` trả `false`, nhưng `compareTo` lại trả `0`?

Đây là **hành vi thư viện**, không phải trực tiếp quy tắc `==` cho primitive. Tra Javadoc lớp `BigDecimal` và hai method:

- `equals(Object)`: yêu cầu giá trị **và biểu diễn/scale** tương ứng cùng nhau.
- `compareTo(BigDecimal)`: so thứ tự theo giá trị số học, có thể trả 0 cho hai số khác scale.
- `scale()`, `precision()`: giải thích chi tiết biểu diễn.
- `setScale(int,RoundingMode)`: điều chỉnh scale, có thể cần rounding.
- `divide`: từng overload đặt chính sách tính chính xác/rounding khác nhau.

**Tệp `NumericBigDecimalDocsDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class NumericBigDecimalDocsDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println("equals=" + a.equals(b));
        System.out.println("compareTo=" + a.compareTo(b));
        System.out.println("scaleA=" + a.scale());
        System.out.println("scaleB=" + b.scale());
        System.out.println("precisionB=" + b.precision());

        BigDecimal half = new BigDecimal("2.345")
                .setScale(2, RoundingMode.HALF_EVEN);
        System.out.println("halfEven=" + half);

        try {
            System.out.println(BigDecimal.ONE.divide(new BigDecimal("3")));
        } catch (ArithmeticException ex) {
            System.out.println("exactDivision=ArithmeticException");
        }

        BigDecimal approx = BigDecimal.ONE.divide(
                new BigDecimal("3"), 2, RoundingMode.HALF_UP);
        System.out.println("roundedDivision=" + approx);
    }
}
```

```bash
javac --release 17 NumericBigDecimalDocsDemo.java
java NumericBigDecimalDocsDemo
```

```text
equals=false
compareTo=0
scaleA=1
scaleB=2
precisionB=3
halfEven=2.34
exactDivision=ArithmeticException
roundedDivision=0.33
```

**Cách đọc kỹ:** `BigDecimal.ONE.divide(new BigDecimal("3"))` không thể tạo một thương thập phân hữu hạn chính xác, nên ném `ArithmeticException`; overload với scale `2` và `HALF_UP` trả `0.33`. Nếu nhầm các overload, bạn có thể áp dụng sai cách làm tròn hoặc kết luận sai rằng `BigDecimal.divide` “lúc nào cũng lỗi khi chia 3”.

Một ngộ nhận phổ biến khác: `new BigDecimal(0.1)` và `new BigDecimal("0.1")` **không đồng nhất** về giá trị thập phân, do tham số `double` đã mang sai số biểu diễn nhị phân. Điều này được giải thích trong mô tả constructor của Javadoc `BigDecimal`; hãy đọc **constructor details**, không chỉ xem tên lớp.

## 8. Tình huống 3: widening không luôn có nghĩa giữ toàn bộ chính xác

**Câu hỏi:** `long` có thể chuyển thành `double` mà không mất chữ số không?

Tra **JLS §5.1.2**: `long` → `double` là một phép widening primitive conversion được phép, nhưng **có thể mất precision** vì `double` có số bit hữu hiệu hữu hạn.

Một ví dụ được chọn sát ngưỡng `2^53`:

**Tệp `NumericConversionDocsDemo.java`:**

```java
public class NumericConversionDocsDemo {
    public static void main(String[] args) {
        long original = 9_007_199_254_740_993L;
        double converted = original;

        System.out.println("original=" + original);
        System.out.println("convertedBack=" + (long) converted);
        System.out.println("sameAfterRoundTrip="
                + (original == (long) converted));

        Integer maybe = null;
        try {
            System.out.println(maybe + 1);
        } catch (NullPointerException ex) {
            System.out.println("unboxing=NullPointerException");
        }
    }
}
```

```bash
javac --release 17 NumericConversionDocsDemo.java
java NumericConversionDocsDemo
```

```text
original=9007199254740993
convertedBack=9007199254740992
sameAfterRoundTrip=false
unboxing=NullPointerException
```

Tra **JLS §5.1.7–§5.1.8** để hiểu boxing/unboxing. `maybe + 1` đòi unbox `Integer` thành `int`; vì `maybe == null` nên ném `NullPointerException`. Javadoc `Integer` giải thích kiểu wrapper và phương thức; quy tắc chuyển đổi trong **biểu thức `+`** thuộc JLS.

Ví dụ cũng nhắc rằng một phép chuyển đổi hợp lệ theo hệ thống kiểu có thể **không đáp ứng yêu cầu dữ liệu** nếu nghiệp vụ đòi giữ chính xác mọi chữ số.

## 9. Tình huống 4: `Double.MIN_VALUE`, `NaN` và signed zero

**Câu hỏi:** Vì sao `Double.MIN_VALUE` dương và `Double.NaN == Double.NaN` false?

Tra kết hợp:

1. Javadoc `Double.MIN_VALUE` định nghĩa nó là **giá trị `double` dương khác 0 nhỏ nhất**; `Double.MIN_NORMAL` là giá trị normal dương nhỏ nhất.
2. JLS §4.2.3–§4.2.4 mô tả các giá trị `float`/`double`, gồm signed zero, infinities và NaN.
3. JLS §15.21.1 quy định numeric equality; so sánh `NaN == NaN` là false, còn `0.0 == -0.0` là true.
4. Javadoc `Double.equals` và `Double.compare` mô tả quy tắc riêng khi **hai giá trị là wrapper**: NaN và signed zero có xử lý khác với primitive `==`.

**Tệp `NumericFloatingDocsDemo.java`:**

```java
public class NumericFloatingDocsDemo {
    public static void main(String[] args) {
        System.out.println("minPositive=" + Double.MIN_VALUE);
        System.out.println("nextUpZero=" + Math.nextUp(0.0));
        System.out.println("nextUpOne=" + Math.nextUp(1.0));
        System.out.println("nanPrimitive="
                + (Double.NaN == Double.NaN));
        System.out.println("nanWrapper="
                + Double.valueOf(Double.NaN)
                        .equals(Double.valueOf(Double.NaN)));
        System.out.println("zeroPrimitive=" + (0.0 == -0.0));
        System.out.println("zeroWrapper="
                + Double.valueOf(0.0)
                        .equals(Double.valueOf(-0.0)));
    }
}
```

```bash
javac --release 17 NumericFloatingDocsDemo.java
java NumericFloatingDocsDemo
```

```text
minPositive=4.9E-324
nextUpZero=4.9E-324
nextUpOne=1.0000000000000002
nanPrimitive=false
nanWrapper=true
zeroPrimitive=true
zeroWrapper=false
```

Nếu cần kiểm tra một giá trị có phải NaN hoặc hữu hạn, hãy đọc hợp đồng `Double.isNaN` và `Double.isFinite`. Không dùng `x == Double.NaN` để phát hiện NaN. Khi cần xét “giá trị kề theo biểu diễn”, `Math.nextUp`, `nextDown`, `ulp` được định nghĩa trong Javadoc `Math`, không phải tự lấy `x + 0.0000001` cho mọi độ lớn.

## 10. Chọn đúng phiên bản và tránh thông tin “đúng nhưng không dùng được”

Một bài đăng có thể giới thiệu phương thức hợp lệ trong Java 21 nhưng dự án đang dùng Java 17. Khi ấy mã có thể không biên dịch, dù ý tưởng đúng.

**Quy trình phiên bản:**

- Kiểm tra runtime: `java -version`.
- Kiểm tra compiler: `javac -version`.
- Kiểm tra cấu hình project (Maven `maven.compiler.release`, Gradle toolchain hoặc `--release`) khi có.
- Tra Javadoc đúng **Java SE release** theo target, không mặc định trang “latest”.
- Xem tag **Since** ở class và method; phương thức được thêm vào bản mới có thể không tồn tại trong bản cũ.
- Dùng `javac --release 17 Demo.java` để kiểm tra **ngôn ngữ và public API** theo mục tiêu Java 17 khi biên dịch bằng JDK hỗ trợ cờ này. Sau đó vẫn phải chạy thử trên runtime mục tiêu.

Ví dụ, **không tự mặc định** một tên phương thức đọc được từ Javadoc Java 21 cũng có trong Java 17. Nếu Java 17 chưa có API tương ứng, cần phương án tương thích Java 17 hoặc yêu cầu nâng bản Java có căn cứ.

### Javadoc khác với implementation detail

Javadoc của một phương thức có thể nêu “returns...” và “throws...”: đây là phần hợp đồng API. Một câu “implementation may use ...” hoặc một thuộc tính dựa trên provider/hệ điều hành có thể chỉ là chi tiết triển khai. Cần giữ ranh giới:

- **Contract:** client được phép dựa vào.
- **Implementation note:** thông tin hữu ích để tối ưu/chẩn đoán, không nhất thiết bảo đảm mọi nền tảng.
- **JLS:** quy tắc ngôn ngữ được tiêu chuẩn hóa cho các compiler/Java implementation phù hợp.

Ví dụ `Math` và `StrictMath` có các mô tả về độ chính xác và khả năng tái lập của hàm toán học. Đọc lời mở đầu của class và từng method trước khi tuyên bố “`Math.sin` luôn trả bit-pattern giống nhau trên mọi platform”.

## 11. Mẹo tìm kiếm và trích dẫn nguồn

Khi một vấn đề chưa rõ nằm ở đâu, nên tìm các từ khóa tiếng Anh đúng thuật ngữ tài liệu:

| Vấn đề | Từ khóa để tìm | Trang ưu tiên |
|---|---|---|
| Overflow `int` | `integer overflow JLS 4.2.2` | JLS §4.2.2 hoặc §15.18.2 |
| Chia số âm | `integer division rounds toward zero JLS 15.17.2` | JLS §15.17.2 |
| Ép kiểu số | `widening narrowing primitive conversion JLS 5.1` | JLS §5.1.2/§5.1.3 |
| Boxing cache / unboxing null | `JLS 5.1.7 5.1.8` | JLS §5.1.7–§5.1.8 |
| Wrapper `==` | `reference equality JLS 15.21` | JLS §15.21 |
| `Math.abs` của MIN_VALUE | `Math abs Integer.MIN_VALUE Java 17` | Javadoc `Math.abs(int)` |
| `BigDecimal.equals` | `BigDecimal equals compareTo scale Javadoc` | Javadoc `BigDecimal` |
| `BigDecimal.divide` | `BigDecimal divide ArithmeticException non terminating` | Javadoc đúng overload `divide` |
| Chính sách làm tròn | `RoundingMode HALF_EVEN table` | Javadoc `RoundingMode` |
| `Double.MIN_VALUE` | `Double MIN_VALUE MIN_NORMAL Java 17` | Javadoc `Double` |

Nếu dùng công cụ tìm kiếm ngoài tài liệu, giới hạn kết quả vào miền chính thức như `docs.oracle.com`, rồi đối chiếu phiên bản. Trang thảo luận, blog và diễn đàn hữu ích để có ví dụ, nhưng đối với **hợp đồng ngôn ngữ/API**, nên kết luận dựa trên JLS/Javadoc gốc. Với một vấn đề tương tác của nhiều API, ghi đủ hai hoặc nhiều nguồn thay vì ép tất cả vào một link.

**Dẫn chứng tốt:** “Java SE 17 JLS §15.17.2 (integer division) quy định chia nguyên theo hướng 0; Javadoc `Math.floorDiv(int,int)` định nghĩa floor division.”  
**Dẫn chứng chưa đủ:** “Đọc trên mạng thấy Java chia âm hơi lạ.”

## 12. Những lỗi thường gặp khi tra cứu

1. **Tra nhầm Javadoc cho toán tử:** `int + int`, `/`, `%`, `==` thuộc JLS; class `Integer` không trực tiếp thay thế ngữ nghĩa mọi toán tử.
2. **Tra JLS để hỏi overload thư viện:** `BigDecimal.divide` và `Math.floorDiv` có hợp đồng method được mô tả trong Javadoc; JLS chỉ định nghĩa lời gọi method và các quy tắc ngôn ngữ liên quan.
3. **Bỏ qua kiểu toán hạng:** `7 / 2` và `7.0 / 2` khác vì numeric promotion; wrapper còn có unboxing.
4. **Bỏ qua dấu âm/zero:** `-7 / 3`, `-7 % 3`, `Math.floorDiv`, `Double.NaN`, `+0.0`/`-0.0` thường là test phân biệt đúng sai.
5. **Chỉ xem method summary:** bỏ lỡ overload, `Throws`, `Since` hoặc câu cảnh báo trong method detail.
6. **Nhầm `MIN_VALUE`:** `Integer.MIN_VALUE` là biên âm, `Double.MIN_VALUE` là số **dương** khác 0 nhỏ nhất.
7. **Dùng Javadoc phiên bản mới hơn:** mã không thể biên dịch trên target cũ dù trang “latest” mô tả API hợp lệ.
8. **Suy luận từ một lần chạy:** một kết quả có thể phụ thuộc implementation/provider; chạy chương trình chỉ là kiểm chứng, không thay thế mô tả đặc tả.
9. **Đọc chữ “exact” mà bỏ kiểu đích:** `Math.addExact`, `BigDecimal.divide`, `BigInteger.intValueExact` đều có ý nghĩa chính xác và ngoại lệ tùy method; đọc đúng signature.
10. **Bỏ qua precision/scale:** cùng giá trị toán học có thể khác `BigDecimal.equals`; nhìn `toString` mà không đọc `scale()` gây hiểu nhầm.
11. **Quên rằng JLS/Javadoc là tài liệu tiếng Anh chuẩn:** khi dịch các từ `truncation`, `floor`, `ceiling`, `round toward zero`, `narrowing`, giữ kèm thuật ngữ gốc để giảm sai lệch.
12. **Coi FAQ/preview/ảnh chụp tài liệu là nguồn cuối cùng:** ưu tiên trang đặc tả có đường dẫn phiên bản và section/method chính xác.

## 13. Bài tập tra cứu có đáp án

1. **Câu hỏi:** `-7 / 3` có phải floor division? Tra ở đâu?  
   **Đáp án:** Không, `/` primitive `int` lấy thương hướng 0, cho `-2`; xem **JLS §15.17.2**. Muốn floor division `-3`, xem method `Math.floorDiv` trong **Javadoc `Math`**.

2. **Câu hỏi:** `Math.addExact(Integer.MAX_VALUE,1)` có khác `Integer.MAX_VALUE+1` không?  
   **Đáp án:** Có. Toán tử primitive overflow theo JLS; `Math.addExact` ném `ArithmeticException` theo Javadoc method. Kết quả `+` là `Integer.MIN_VALUE`.

3. **Câu hỏi:** `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` là `false` do JLS hay Javadoc?  
   **Đáp án:** Chủ yếu là hợp đồng `BigDecimal.equals` trong **Javadoc `BigDecimal`**; so sánh giá trị số học bằng `compareTo() == 0`.

4. **Câu hỏi:** Vì sao `Double.MIN_VALUE > 0`?  
   **Đáp án:** Hằng `MIN_VALUE` được **Javadoc `Double`** định nghĩa là số dương khác 0 nhỏ nhất. JLS §4.2.3 mô tả mô hình giá trị `double`.

5. **Câu hỏi:** Nếu `Integer x = null;` thì `x + 1` làm gì?  
   **Đáp án:** Ném `NullPointerException` khi unboxing, tra **JLS §5.1.8** và §5.6. `x == null` chỉ là reference equality nên không unbox.

6. **Câu hỏi:** `Math.nextUp(1.0)` tìm ở đâu?  
   **Đáp án:** Method detail của **Javadoc `Math`**. Nó trả số `double` biểu diễn được kề trên 1.0, được in là `1.0000000000000002`.

7. **Câu hỏi:** `BigDecimal.ONE.divide(new BigDecimal("3"))` có làm tròn tự động không?  
   **Đáp án:** Overload chia chính xác sẽ ném `ArithmeticException` khi thương thập phân không kết thúc; xem **Javadoc `BigDecimal.divide(BigDecimal)`**. Chọn overload với scale và rounding mode khi nghiệp vụ cho phép làm tròn.

8. **Câu hỏi:** Vì sao cùng lời gọi method trên JDK mới biên dịch nhưng Java 17 không?  
   **Đáp án:** Kiểm tra phần **Since** và phiên bản Javadoc, dùng `javac --release 17` để đối chiếu API công khai theo target; có thể method chưa được hỗ trợ trên Java 17.

9. **Câu hỏi:** Nếu muốn tìm quy tắc `byte b = 1; b += 1;` khác `b = b + 1;`, đọc đâu?  
   **Đáp án:** **JLS §5.6** về numeric promotion và **§15.26.2** về compound assignment. Không phải chỉ Javadoc `Byte`.

10. **Câu hỏi:** Khi viết một báo cáo lỗi số học, cần dẫn chứng thế nào?  
    **Đáp án:** Nêu phiên bản Java, kiểu toán hạng, biểu thức cụ thể, method overload (nếu có), expected/actual, đoạn mã tái hiện, và link JLS section hoặc Javadoc method phù hợp.

## 14. Checklist tra cứu nhanh trước khi kết luận

- [ ] Ghi đúng bản Java target và lệnh biên dịch/run.
- [ ] Xác định đây là **toán tử ngôn ngữ**, **chuyển kiểu**, hay **method thư viện**.
- [ ] Tra JLS §4, §5, §15 nếu liên quan primitive, toán tử, promotion, casting, boxing/unboxing.
- [ ] Tra **đúng lớp, đúng overload, đúng Java release** trong Javadoc nếu liên quan API.
- [ ] Đọc `Returns`, `Throws`, `Since`, cảnh báo trong class/method detail.
- [ ] Kiểm tra biên: MIN/MAX, số âm, số 0, NaN/Infinity, scale, rounding.
- [ ] Viết chương trình nhỏ có đầu ra xác định và đối chiếu với đặc tả.
- [ ] Phân biệt điều **được bảo đảm** với chi tiết triển khai/provider.
- [ ] Lưu link tới section hoặc method cụ thể trong ghi chú kiến thức, test hoặc review.

## 15. Tổng kết

Đối với Java Core – numbers, hãy nhớ một nguyên tắc: **JLS giải thích Java thực hiện biểu thức như thế nào; Javadoc giải thích thư viện số công khai cam kết điều gì.** Khi cần kiểm chứng một hành vi:

1. Xác định **kiểu và phiên bản Java**.
2. Tìm **đúng section JLS** nếu là toán tử/chuyển đổi, hoặc **đúng method Javadoc** nếu là API.
3. Đọc **các trường hợp biên, ngoại lệ, rounding và overload**.
4. Dùng ví dụ Java 17+ tái hiện, nhưng kết luận theo **hợp đồng tài liệu**.
5. Ghi nguồn chính thức cùng section/method để người khác kiểm chứng lại.

Nguồn gốc: [JLS SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html), [Java SE 17 Javadoc – `java.base`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/module-summary.html), [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), [Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html), [Double](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html).
