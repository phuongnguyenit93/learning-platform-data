# Chia cho 0 trong Java: phân biệt vô cực và NaN

Trong Java, câu hỏi “chia cho 0 sẽ xảy ra chuyện gì?” **không có cùng một đáp án cho mọi kiểu số**. Với phép chia **số nguyên** (`int`, `long` và các kiểu nguyên nhỏ được nâng lên `int`), số chia bằng 0 dẫn đến `ArithmeticException` khi phép toán được thực hiện. Với phép chia **dấu phẩy động** (`float` hoặc `double`), Java sử dụng các giá trị đặc biệt IEEE 754: `Infinity`, `-Infinity` và `NaN`.

Quy tắc cần nhớ:

- **Số hữu hạn khác 0 / ±0.0 → vô cực có dấu (`Infinity` hoặc `-Infinity`).**
- **±0.0 / ±0.0 → `NaN` (*Not a Number*).**
- **Phép chia nguyên với số chia 0 → `ArithmeticException`**, không sinh `Infinity` hoặc `NaN`.
- Vô cực và NaN còn có thể xuất hiện **không phải do chia cho 0**, chẳng hạn số thực tràn phạm vi hoặc các phép toán vô định khác.

Bài học dưới đây dùng Java 17+ và phân biệt **kết quả tính toán**, **cách Java hiển thị kết quả** và **cách kiểm tra/xử lý giá trị bất thường**.

## 1. Vì sao Java có kết quả vô cực và NaN?

`float` và `double` là kiểu số dấu phẩy động nhị phân theo IEEE 754. Ngoài các giá trị hữu hạn, chúng chứa các mã biểu diễn riêng cho:

| Giá trị | Ý nghĩa thực tế | Java |
| --- | --- | --- |
| Dương vô cực | Kết quả vượt phía dương của miền số hữu hạn hoặc phép toán được định nghĩa cho ra dương vô cực | `Double.POSITIVE_INFINITY`, `Float.POSITIVE_INFINITY` |
| Âm vô cực | Kết quả vượt phía âm hoặc phép toán được định nghĩa cho ra âm vô cực | `Double.NEGATIVE_INFINITY`, `Float.NEGATIVE_INFINITY` |
| NaN | Kết quả số thực không xác định theo các quy tắc IEEE 754, ví dụ `0.0 / 0.0` | `Double.NaN`, `Float.NaN` |
| Dương zero | Số 0 có bit dấu bằng 0 | `0.0`, `0.0f` |
| Âm zero | Số 0 có bit dấu bằng 1 | `-0.0`, `-0.0f` |

Java mặc định in `Double.POSITIVE_INFINITY` là `Infinity`, in `Double.NEGATIVE_INFINITY` là `-Infinity` và in `Double.NaN` là `NaN`. Những chữ này là cách biểu diễn văn bản của **giá trị kiểu số thực**, không phải chuỗi được phép trộn tùy ý với phép toán nguyên.

```java
double plusInfinity = Double.POSITIVE_INFINITY;
double minusInfinity = Double.NEGATIVE_INFINITY;
double notANumber = Double.NaN;
System.out.println(plusInfinity);  // Infinity
System.out.println(minusInfinity); // -Infinity
System.out.println(notANumber);    // NaN
```

**NaN không có nghĩa “giá trị là số 0”, “lỗi bằng 0” hay “chưa khởi tạo”.** Nó là một giá trị đặc biệt mang ý nghĩa rằng phép tính không có kết quả số thực thông thường theo quy tắc của kiểu.

## 2. Số hữu hạn khác 0 chia cho zero: vô cực có dấu

Đối với `double`, khi tử số **hữu hạn và khác 0**, còn mẫu số là `+0.0` hoặc `-0.0`, kết quả là vô cực; dấu của kết quả phụ thuộc vào dấu của hai toán hạng.

| Biểu thức | Kết quả | Diễn giải |
| --- | --- | --- |
| `1.0 / 0.0` | `Infinity` | Dương / zero dương |
| `-1.0 / 0.0` | `-Infinity` | Âm / zero dương |
| `1.0 / -0.0` | `-Infinity` | Dương / zero âm |
| `-1.0 / -0.0` | `Infinity` | Âm / zero âm |
| `10.0 / 0.0` | `Infinity` | Tử số dương hữu hạn |
| `0.0 / 0.0` | `NaN` | Tử số không khác 0 — quy tắc khác |

Ví dụ:

```java
System.out.println(1.0 / 0.0);   // Infinity
System.out.println(-1.0 / 0.0);  // -Infinity
System.out.println(1.0 / -0.0);  // -Infinity
System.out.println(-1.0 / -0.0); // Infinity
```

**Không có exception chỉ vì mẫu số số thực bằng 0.** Bởi vậy `try/catch (ArithmeticException ...)` không phải cách thông thường để phát hiện phép chia `double` cho 0. Phải kiểm tra miền đầu vào hoặc kết quả sau phép tính.

### `float` cũng có hành vi tương ứng

```java
float result = 5.0f / 0.0f;       // Float.POSITIVE_INFINITY
float indeterminate = 0.0f / 0.0f; // Float.NaN
```

`5.0f` và `0.0f` có kiểu `float`, còn `5.0` và `0.0` có kiểu `double`. Hậu tố `f`/`F` giúp ghi rõ kiểu literal `float`.

## 3. Zero chia cho zero: vì sao lại là NaN?

Khi **cả tử số và mẫu số đều bằng zero**, phép chia dấu phẩy động cho `NaN` bất kể zero mang dấu nào:

```java
double a = 0.0 / 0.0;   // NaN
double b = -0.0 / 0.0;  // NaN
double c = 0.0 / -0.0;  // NaN
double d = -0.0 / -0.0; // NaN
```

**Vô cực và NaN là hai trạng thái khác nhau.** Nếu tử số hữu hạn khác 0 và mẫu bằng 0, dấu của tỷ số xác định được theo quy tắc số thực nên nhận vô cực có dấu. Nếu tử số cũng bằng 0, không có một tỷ số xác định chung cho biểu thức `0/0`, vì vậy quy tắc số thực cho `NaN`.

Đừng diễn giải `NaN` như một số quá lớn: nó **không phải vô cực** và không có thứ tự số học thông thường. Hơn nữa, các giá trị `NaN` có thể phát sinh từ nhiều phép toán không xác định khác, không riêng `0.0 / 0.0`.

## 4. Số nguyên chia cho 0: `ArithmeticException`

Với `int` và `long`, Java **không có giá trị vô cực hoặc NaN**. Nếu mẫu số bằng 0, phép chia nguyên tại thời điểm chạy ném `ArithmeticException`.

```java
int dividend = 10;
int divisor = 0;

try {
    int quotient = dividend / divisor;
    System.out.println(quotient);
} catch (ArithmeticException ex) {
    System.out.println("integer division by zero");
}
```

Output:

```text
integer division by zero
```

**Kiểu của biểu thức tại thời điểm chia** mới quyết định hành vi, không phải kiểu biến dùng để lưu kết quả:

```java
int a = 1;
int b = 0;

// double wrong = a / b; // thực thi sẽ ném ArithmeticException trước khi gán
double floating = (double) a / b; // Infinity: toán hạng bên trái đã là double
double alsoFloating = a / (double) b; // Infinity
double literalFloating = 1.0 / 0;     // Infinity: int 0 được nâng thành double
```

Dòng `wrong` được chú thích là **minh họa mã ném exception khi thực thi**, không phải lỗi do gán kiểu. Khi hai toán hạng đều là `int`, `a / b` là phép chia `int`. Nếu chuyển một toán hạng sang `double` **trước** phép chia, Java thực hiện phép chia dấu phẩy động.

Với hai `byte`/`short`, phép chia số học thường nâng lên `int`; `byte b = 0; int x = 1 / b;` cũng ném `ArithmeticException`. Với kiểu `long`, `1L / 0L` ném cùng loại exception.

**Lưu ý:** `ArithmeticException` có thể có những nguyên nhân số học nguyên khác. Không nên dựa hoàn toàn vào thông điệp chi tiết của exception để suy luận chính xác nghiệp vụ.

## 5. Dấu âm của zero quan trọng như thế nào?

IEEE 754 và Java phân biệt `+0.0` với `-0.0` ở **biểu diễn bit**. Tuy nhiên, phép so sánh số học `==` cho chúng bằng nhau:

```java
System.out.println(0.0 == -0.0); // true
```

Các phép toán có thể nhận ra dấu khác nhau:

```java
System.out.println(1.0 / 0.0);  // Infinity
System.out.println(1.0 / -0.0); // -Infinity
System.out.println(-1.0 / Double.POSITIVE_INFINITY); // -0.0
```

Có thể xem bit gốc:

```java
long positiveZeroBits = Double.doubleToRawLongBits(0.0);  // 0
long negativeZeroBits = Double.doubleToRawLongBits(-0.0); // Long.MIN_VALUE
```

Không nên viết một kiểm tra `denominator == 0.0` rồi nghĩ rằng nó phân biệt được dấu zero; phép `==` coi hai giá trị zero bằng nhau.

### Khi số thực hữu hạn chia cho vô cực

Hành vi đối xứng cũng đáng chú ý:

| Biểu thức | Kết quả |
| --- | --- |
| `1.0 / Double.POSITIVE_INFINITY` | `0.0` |
| `-1.0 / Double.POSITIVE_INFINITY` | `-0.0` |
| `1.0 / Double.NEGATIVE_INFINITY` | `-0.0` |
| `-1.0 / Double.NEGATIVE_INFINITY` | `0.0` |

Đây là các phép chia số thực hợp lệ. Zero có dấu còn có thể xuất hiện do **underflow** khi một kết quả quá nhỏ về trị tuyệt đối so với khả năng biểu diễn.

## 6. Nếu có vô cực hoặc NaN trong phép toán tiếp theo

Một kết quả vô cực hoặc NaN có thể tiếp tục tham gia các biểu thức:

| Biểu thức | Kết quả |
| --- | --- |
| `Double.POSITIVE_INFINITY + 100.0` | `Infinity` |
| `Double.POSITIVE_INFINITY + Double.NEGATIVE_INFINITY` | `NaN` |
| `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` | `NaN` |
| `0.0 * Double.POSITIVE_INFINITY` | `NaN` |
| `Double.POSITIVE_INFINITY / Double.POSITIVE_INFINITY` | `NaN` |
| `Double.NaN + 1.0` | `NaN` |
| `1.0 / Double.POSITIVE_INFINITY` | `0.0` |
| `1.0 % 0.0` | `NaN` |

**NaN thường lan truyền** qua các phép toán số thực. Ví dụ `(0.0 / 0.0) + 10.0` vẫn ra `NaN`, chứ không trở thành số 10.

```java
double infinity = 1.0 / 0.0;
double nan = 0.0 / 0.0;

System.out.println(infinity + 1.0); // Infinity
System.out.println(nan + 1.0);      // NaN
```

### Phép dư `%` cũng có quy tắc riêng

Với `double`/`float`, `1.0 % 0.0` cho `NaN`. Với `int`/`long`, `1 % 0` ném `ArithmeticException` khi thực thi.

```java
System.out.println(1.0 % 0.0); // NaN
```

Toán tử `%` của Java dùng phép lấy dư theo ngữ nghĩa của ngôn ngữ, không đồng nhất với phép toán `Math.IEEEremainder` trong mọi trường hợp. Đừng tự cho rằng kết quả hoặc cách xử lý phần dư giống mọi ngôn ngữ lập trình khác.

## 7. Vô cực không chỉ đến từ phép chia cho 0

Một số dấu phẩy động hữu hạn có thể vượt phạm vi biểu diễn khi nhân hoặc thực hiện các phép toán khác:

```java
double overflow = Double.MAX_VALUE * 2.0;
System.out.println(overflow); // Infinity
```

`Double.MAX_VALUE` là giá trị `double` hữu hạn dương lớn nhất. Khi kết quả vượt khả năng biểu diễn hữu hạn, phép toán có thể cho `Infinity` ngay cả khi không hề chia cho 0.

Ở phía ngược lại, **underflow** có thể làm một kết quả khác 0 về mặt toán học trở thành zero có dấu:

```java
double underflow = Double.MIN_VALUE / 2.0;
System.out.println(underflow); // 0.0
```

`Double.MIN_VALUE` trong Java là **số `double` dương nhỏ nhất lớn hơn 0** (*positive subnormal*), **không** phải số hữu hạn âm lớn nhất về trị tuyệt đối. Do đó chia tiếp cho 2 sẽ làm tròn về `+0.0`.

Một số phép toán không xác định khác cũng sinh NaN:

```java
double invalidRoot = Math.sqrt(-1.0); // NaN
double undefined = Double.POSITIVE_INFINITY
        - Double.POSITIVE_INFINITY; // NaN
```

**Không thể kết luận “mẫu số bằng 0” chỉ bằng cách thấy `Infinity`**; cũng không thể kết luận “tử và mẫu đều bằng 0” chỉ bằng cách thấy `NaN`. Muốn tìm nguyên nhân, hãy kiểm tra đầu vào và các bước trung gian.

## 8. Cách phát hiện `Infinity`, `-Infinity` và `NaN`

Java cung cấp API chuyên dụng:

| API | `Infinity` | `-Infinity` | `NaN` | Số hữu hạn |
| --- | --- | --- | --- | --- |
| `Double.isInfinite(x)` | `true` | `true` | `false` | `false` |
| `Double.isNaN(x)` | `false` | `false` | `true` | `false` |
| `Double.isFinite(x)` | `false` | `false` | `false` | `true` |

`Float` có các API tương ứng: `Float.isInfinite`, `Float.isNaN` và `Float.isFinite`.

```java
double positiveInfinity = 1.0 / 0.0;
double undefined = 0.0 / 0.0;

System.out.println(Double.isInfinite(positiveInfinity)); // true
System.out.println(Double.isNaN(undefined));              // true
System.out.println(Double.isFinite(positiveInfinity));    // false
System.out.println(Double.isFinite(42.0));                // true
```

### Vì sao không nên kiểm tra NaN bằng `==`?

Theo ngữ nghĩa số học dấu phẩy động, NaN không bằng bất kỳ giá trị nào, **kể cả chính nó**:

```java
double x = Double.NaN;
System.out.println(x == Double.NaN); // false
System.out.println(x == x);          // false
System.out.println(Double.isNaN(x)); // true
```

Các phép so sánh thứ tự với NaN như `x < 1.0`, `x >= 1.0` đều `false`. Riêng `x != x` là `true` khi `x` là NaN. Trong code thực tế, `Double.isNaN(x)` diễn đạt ý định rõ hơn mẹo `x != x`.

`Double.compare` có quy tắc sắp xếp NaN và zero có dấu để phục vụ các tình huống cần thứ tự nhất quán. Nó không đồng nghĩa với `==` về mọi trường hợp đặc biệt: chẳng hạn `0.0 == -0.0` là `true` nhưng `Double.compare(0.0, -0.0)` không bằng 0.

## 9. Nên kiểm tra đầu vào hay kiểm tra đầu ra?

Có hai chính sách khác nhau, tùy hợp đồng nghiệp vụ.

### Chính sách A: Không cho mẫu số bằng zero

Nếu API của bạn đòi hỏi **mẫu khác 0**, hãy kiểm tra mẫu trước khi chia:

```java
static double divideFiniteInputs(double numerator, double denominator) {
    if (!Double.isFinite(numerator) || !Double.isFinite(denominator)) {
        throw new IllegalArgumentException("Inputs must be finite");
    }
    if (denominator == 0.0) {
        throw new IllegalArgumentException("Denominator must be nonzero");
    }
    double result = numerator / denominator;
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("Result is not finite");
    }
    return result;
}
```

Đây là **method minh họa phải đặt trong một class**, không phải chương trình Java độc lập. Mẫu `denominator == 0.0` chủ động từ chối cả `+0.0` lẫn `-0.0`. Kiểm tra `Double.isFinite` sau phép chia còn bắt trường hợp **overflow sang vô cực dù mẫu không bằng 0**, và các kết quả không hữu hạn khác.

Phần xử lý lỗi là **chính sách của API**, không phải exception Java tự động ném cho phép chia số thực. `IllegalArgumentException` và `ArithmeticException` ở ví dụ trên do **chính người lập trình viết ra**.

### Chính sách B: Chấp nhận giá trị IEEE 754

Trong một số tính toán khoa học, việc tạo `Infinity` hoặc `NaN` có thể được giữ lại có chủ đích và được xử lý ở tầng phân tích kết quả:

```java
double ratio = numerator / denominator;
if (Double.isNaN(ratio)) {
    // Xử lý phép toán không xác định
} else if (Double.isInfinite(ratio)) {
    // Xử lý vô cực theo mô hình của ứng dụng
} else {
    // Xử lý kết quả hữu hạn
}
```

Đoạn này là **ví dụ nằm trong method có các biến đã khai báo**. Đừng mặc định biến mọi `NaN` thành 0: `0` có thể là giá trị hợp lệ, khiến lỗi dữ liệu bị che khuất.

Đối với tính tiền, chia số lượng hoặc phân bổ tài nguyên, thông thường cần thiết kế quy tắc làm tròn, phạm vi và kiểm tra dữ liệu rõ ràng; `double`/`float` không phải công cụ lưu tiền thập phân chính xác. `BigDecimal` có quy tắc phép chia và exception riêng, **không** áp dụng trực tiếp bảng IEEE 754 của `double`.

## 10. Một số bẫy khi chuyển kiểu và truyền dữ liệu

### Cast vô cực hoặc NaN sang số nguyên

Narrowing từ `double` sang `int` không ném exception trong trường hợp `Infinity` hay `NaN`; Java áp dụng quy tắc chuyển đổi được định nghĩa:

```java
int positive = (int) Double.POSITIVE_INFINITY; // Integer.MAX_VALUE
int negative = (int) Double.NEGATIVE_INFINITY; // Integer.MIN_VALUE
int nan = (int) Double.NaN;                    // 0
```

Điều này đặc biệt nguy hiểm nếu bạn cố “chữa” kết quả phép chia bằng cast. Mọi giá trị `NaN` đều trở thành `0` khi cast trực tiếp sang `int`; vô cực được chặn tại biên `int`. Việc cast **không chứng minh dữ liệu đầu vào hợp lệ**.

### Chuỗi đầu ra không tự kể nguyên nhân

`String.valueOf(Double.POSITIVE_INFINITY)` tạo chuỗi `"Infinity"`, `String.valueOf(Double.NaN)` tạo `"NaN"`. Giá trị gốc vẫn là số thực. Java có thể parse các chuỗi hợp lệ này bằng `Double.parseDouble("Infinity")` hay `Double.parseDouble("NaN")`; tuy nhiên giao thức bên ngoài như JSON tiêu chuẩn **không mặc nhiên cho phép** NaN/vô cực dưới dạng số JSON. Khi xuất dữ liệu cần xác định rõ cách biểu diễn, ví dụ từ chối hoặc ánh xạ sang cấu trúc lỗi riêng theo contract.

### Không nhầm NaN với `null` hoặc chuỗi rỗng

`Double.NaN` là một giá trị primitive `double`. `null` chỉ áp dụng cho tham chiếu như `Double` wrapper. Khi `Double` wrapper chứa `null` bị *unbox* trong phép chia, có thể xảy ra `NullPointerException` **trước cả khi tính toán**. Đây là tình huống hoàn toàn khác `0.0 / 0.0` sinh `NaN`.

## 11. Chương trình Java 17+ kiểm chứng đầy đủ

Lưu thành tệp **`FloatingDivideByZeroDemo.java`**:

```java
public class FloatingDivideByZeroDemo {
    public static void main(String[] args) {
        System.out.println("positiveOverZero=" + (1.0 / 0.0));
        System.out.println("negativeOverZero=" + (-1.0 / 0.0));
        System.out.println("positiveOverNegativeZero=" + (1.0 / -0.0));
        System.out.println("negativeOverNegativeZero=" + (-1.0 / -0.0));
        System.out.println("zeroOverZero=" + (0.0 / 0.0));
        System.out.println("negativeZeroOverZero=" + (-0.0 / 0.0));

        System.out.println("floatOverZero=" + (5.0f / 0.0f));
        System.out.println("floatZeroOverZero=" + (0.0f / 0.0f));
        System.out.println("zeroEquality=" + (0.0 == -0.0));
        System.out.println("negativeZeroBits=" +
                Long.toHexString(Double.doubleToRawLongBits(-0.0)));

        System.out.println("finiteOverPositiveInfinity=" +
                (1.0 / Double.POSITIVE_INFINITY));
        System.out.println("negativeOverPositiveInfinity=" +
                (-1.0 / Double.POSITIVE_INFINITY));
        System.out.println("infinityOverInfinity=" +
                (Double.POSITIVE_INFINITY / Double.POSITIVE_INFINITY));
        System.out.println("zeroTimesInfinity=" +
                (0.0 * Double.POSITIVE_INFINITY));
        System.out.println("remainderByZero=" + (1.0 % 0.0));

        double infinity = 1.0 / 0.0;
        double nan = 0.0 / 0.0;
        System.out.println("isInfinite=" + Double.isInfinite(infinity));
        System.out.println("isNaN=" + Double.isNaN(nan));
        System.out.println("isFiniteInfinity=" + Double.isFinite(infinity));
        System.out.println("isFiniteOne=" + Double.isFinite(1.0));
        System.out.println("nanEqualsItself=" + (nan == nan));
        System.out.println("nanLessThanOne=" + (nan < 1.0));

        int numerator = 1;
        int denominator = 0;
        try {
            System.out.println(numerator / denominator);
        } catch (ArithmeticException ex) {
            System.out.println("integerDivideByZero=ArithmeticException");
        }
        System.out.println("promotedDivision=" +
                ((double) numerator / denominator));

        System.out.println("overflowWithoutZero=" + (Double.MAX_VALUE * 2.0));
        System.out.println("underflowToZero=" + (Double.MIN_VALUE / 2.0));
        System.out.println("castInfinity=" + (int) Double.POSITIVE_INFINITY);
        System.out.println("castNaN=" + (int) Double.NaN);
    }
}
```

Tại thư mục chứa file, chạy bằng JDK 17 trở lên:

```bash
javac FloatingDivideByZeroDemo.java
java FloatingDivideByZeroDemo
```

Output chính xác:

```text
positiveOverZero=Infinity
negativeOverZero=-Infinity
positiveOverNegativeZero=-Infinity
negativeOverNegativeZero=Infinity
zeroOverZero=NaN
negativeZeroOverZero=NaN
floatOverZero=Infinity
floatZeroOverZero=NaN
zeroEquality=true
negativeZeroBits=8000000000000000
finiteOverPositiveInfinity=0.0
negativeOverPositiveInfinity=-0.0
infinityOverInfinity=NaN
zeroTimesInfinity=NaN
remainderByZero=NaN
isInfinite=true
isNaN=true
isFiniteInfinity=false
isFiniteOne=true
nanEqualsItself=false
nanLessThanOne=false
integerDivideByZero=ArithmeticException
promotedDivision=Infinity
overflowWithoutZero=Infinity
underflowToZero=0.0
castInfinity=2147483647
castNaN=0
```

Bốn dòng đầu chứng minh dấu của tử và mẫu quyết định dấu vô cực. Các dòng `zeroOverZero` và `infinityOverInfinity` chứng minh NaN không đồng nghĩa với “mẫu số bằng 0”. `integerDivideByZero` và `promotedDivision` cho thấy chỉ một bước chuyển kiểu **trước khi chia** đã đổi hoàn toàn hành vi.

## 12. Lỗi phổ biến và checklist giải bài

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| “Mọi phép chia cho 0 trong Java đều ném exception.” | Sai | `float`/`double` có `Infinity` hoặc `NaN`; phép chia nguyên mới ném `ArithmeticException`. |
| “`1.0 / 0.0` trả `NaN`.” | Sai | Tử hữu hạn khác zero nên trả `Infinity`. |
| “`0.0 / 0.0` trả `Infinity`.” | Sai | Đây là `NaN`. |
| “`-0.0` giống hoàn toàn `+0.0`.” | Sai | `==` coi bằng nhau nhưng dấu zero ảnh hưởng phép chia và bit lưu. |
| “`double x = 1 / 0` sẽ cho `Infinity`.” | Sai | Hai toán hạng `int`; chia nguyên ném exception trước khi gán. |
| “Dùng `Double.isNaN(x)` để phát hiện vô cực.” | Sai | Dùng `Double.isInfinite(x)` cho vô cực; `isNaN` chỉ cho NaN. |
| “`Double.NaN == Double.NaN` đúng.” | Sai | Theo `==` số thực, NaN không bằng chính nó. |
| “Thấy `Infinity` tức là chắc chắn đã chia cho 0.” | Sai | Overflow số thực cũng tạo vô cực. |
| “Thấy `NaN` tức là chắc chắn tử và mẫu đều bằng 0.” | Sai | `Infinity/Infinity`, `0*Infinity` và nhiều phép khác cũng sinh NaN. |
| “Cast `NaN` sang `int` sẽ ném exception.” | Sai | `(int) Double.NaN` cho 0. |
| “`try/catch ArithmeticException` đủ bảo vệ phép chia `double`.” | Sai | Cần kiểm tra mẫu, tính hữu hạn của đầu vào và/hoặc kết quả. |

Khi gặp phép chia trong code, hãy kiểm tra theo trình tự:

1. **Kiểu của biểu thức tại phép chia là gì?** `int/long` → chia zero ném exception; `float/double` → quy tắc IEEE 754.
2. **Tử số là hữu hạn khác 0 hay bằng 0?** Với mẫu zero, tử khác 0 dẫn đến vô cực có dấu; zero/zero dẫn đến NaN.
3. **Mẫu zero có dấu gì?** `+0.0` và `-0.0` có thể cho dấu vô cực khác nhau.
4. **Đã có Infinity/NaN trong toán hạng từ trước chưa?** Nếu có, phân tích quy tắc lan truyền thay vì chỉ tập trung mẫu zero.
5. **Contract có cho kết quả không hữu hạn không?** Nếu không, kiểm tra `Double.isFinite` của đầu vào/kết quả và trả lỗi rõ ràng.
6. **Đừng chữa lỗi bằng cast hoặc chuỗi hiển thị.** Việc chuyển vô cực/NaN sang kiểu khác có thể che mất thông tin về lỗi.

**Ghi nhớ:** Với phép chia số thực, **khác 0 chia cho ±0.0 tạo ±Infinity; ±0.0 chia cho ±0.0 tạo NaN**. Với phép chia nguyên, mẫu 0 ném `ArithmeticException`. Muốn kiểm soát đúng nghiệp vụ, hãy xác định kiểu phép toán, kiểm tra dữ liệu và xử lý `Infinity`/`NaN` tường minh.