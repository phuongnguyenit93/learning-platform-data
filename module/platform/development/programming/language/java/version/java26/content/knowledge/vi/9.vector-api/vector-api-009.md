# Phép giảm, đổi kiểu và sai số số thực

> **Mốc cập nhật: 27-11-2026.** Vector API trong JDK 27 vẫn là **Incubator lần thứ 12** theo JEP 537, nằm trong module `jdk.incubator.vector`. Bài thực hành dùng API Java 27 hiện hành để giảm nhiều lane thành một giá trị, chuyển đổi kiểu lane và kiểm soát sai số số thực. Đây là API incubator, chưa phải API ổn định của Java SE.

## 1. Mục tiêu

Một vector có nhiều lane. Phép toán lane-wise xử lý từng lane tương ứng, còn **reduction** gộp nhiều lane thành một kết quả scalar. Ví dụ: tổng, tích, giá trị nhỏ nhất hoặc lớn nhất của các phần tử trong vector.

Trong xử lý dữ liệu, reduction và conversion thường xuất hiện cùng nhau:

- Tính tổng hoặc cực trị của một block dữ liệu.
- Cộng nhiều block thành tổng toàn mảng.
- Mở rộng `int` thành `long` trước khi cộng để tránh tràn số.
- Chuyển `int` sang `float`, `double` sang `float` hoặc ngược lại.
- So sánh kết quả vector với kết quả scalar khi phép cộng dấu phẩy động có thứ tự thực hiện khác nhau.

Sau bài này, bạn có thể:

- Dùng `reduceLanes()` và overload có `VectorMask`.
- Hiểu identity value của reduction khi không lane nào được chọn.
- Phân biệt reduction integer và floating-point.
- Chuyển đổi lane bằng `convert()`, `convertShape()` và `castShape()`.
- Hiểu tham số `part` khi kích thước lane thay đổi.
- Phân biệt chuyển đổi giá trị với diễn giải lại bit.
- Đặt tolerance phù hợp để kiểm tra kết quả float/double.
- Tránh overflow, mất độ chính xác và kết luận sai từ benchmark.

## 2. Trạng thái API và cờ sử dụng

JDK 27 tiếp tục Vector API ở incubator lần thứ 12 theo JEP 537. Các kiểu chính dùng trong bài nằm trong package `jdk.incubator.vector`:

- `IntVector`, `LongVector`
- `FloatVector`, `DoubleVector`
- `VectorSpecies`, `VectorMask`
- `VectorOperators`

Biên dịch và chạy với JDK 27:

```text
javac --release 27 --add-modules jdk.incubator.vector VectorReductionDemo.java
java --add-modules jdk.incubator.vector VectorReductionDemo
```

Vector API là incubator module, vì vậy cần `--add-modules jdk.incubator.vector` ở compile và runtime. Không cần `--enable-preview` chỉ để dùng Vector API. Nếu dự án đồng thời sử dụng một preview feature khác thì cấu hình preview riêng cho feature đó.

## 3. Reduction: gộp các lane thành một giá trị

### 3.1. reduceLanes

Dùng `reduceLanes(VectorOperators.Associative)` để gộp lane trong vector:

```java
float sum = vector.reduceLanes(VectorOperators.ADD);
float product = vector.reduceLanes(VectorOperators.MUL);
float minimum = vector.reduceLanes(VectorOperators.MIN);
float maximum = vector.reduceLanes(VectorOperators.MAX);
```

Một số operator thường dùng:

| Operator | Kết quả |
|---|---|
| `ADD` | Tổng các lane. |
| `MUL` | Tích các lane. |
| `MIN` | Giá trị nhỏ nhất. |
| `MAX` | Giá trị lớn nhất. |
| `FIRST_NONZERO` | Giá trị khác zero ở lane có index nhỏ nhất; nếu không có thì trả zero theo quy tắc của API. |
| `AND`, `OR`, `XOR` | Các phép gộp bit trên vector integer tương ứng. |

Ví dụ:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorOperators;
import jdk.incubator.vector.VectorSpecies;

public class ReductionExample {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    public static void main(String[] args) {
        float[] values = new float[SPECIES.length()];
        for (int i = 0; i < values.length; i++) {
            values[i] = i + 1.5f;
        }

        FloatVector vector =
                FloatVector.fromArray(SPECIES, values, 0);

        float sum = vector.reduceLanes(VectorOperators.ADD);
        float min = vector.reduceLanes(VectorOperators.MIN);
        float max = vector.reduceLanes(VectorOperators.MAX);

        System.out.println("sum = " + sum);
        System.out.println("min = " + min);
        System.out.println("max = " + max);
    }
}
```

Ví dụ trên giả định mảng có đủ số lane cho species được chọn. Khi xử lý mảng có độ dài bất kỳ, dùng full-vector loop và xử lý tail hoặc dùng masked load/reduction như các phần tiếp theo.

### 3.2. Reduction có mask

Overload có mask chỉ gộp các lane được bật:

```java
float selectedSum = vector.reduceLanes(
        VectorOperators.ADD,
        mask
);
```

Mask phải tương thích với species của vector. Nếu không lane nào được chọn, API trả về identity value phụ thuộc operator:

| Operator | Identity khi mask không chọn lane nào |
|---|---:|
| `ADD` | `+0.0f` hoặc `+0.0d` |
| `FIRST_NONZERO` | Positive zero |
| `MUL` | `1.0` |
| `MAX` | `Float.NEGATIVE_INFINITY` hoặc `Double.NEGATIVE_INFINITY` |
| `MIN` | `Float.POSITIVE_INFINITY` hoặc `Double.POSITIVE_INFINITY` |

Vì vậy, nếu cần kiểm tra có ít nhất một lane hợp lệ hay không, đừng chỉ nhìn vào kết quả reduction. Ví dụ tổng bằng zero có thể là tổng của nhiều phần tử hợp lệ, hoặc mask không chọn lane nào. Kiểm tra riêng `mask.anyTrue()` hoặc số phần tử được chọn khi điều đó có ý nghĩa nghiệp vụ.

## 4. Bài tập 1 — Tính tổng một mảng float

Một mảng thường dài hơn một vector. Có thể dùng masked load và masked reduction để xử lý block cuối cùng mà không đọc vượt biên.

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorOperators;
import jdk.incubator.vector.VectorSpecies;

public final class FloatArraySum {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    private FloatArraySum() {}

    public static float sum(float[] values) {
        float total = 0.0f;

        for (int i = 0; i < values.length; i += SPECIES.length()) {
            VectorMask<Float> mask =
                    SPECIES.indexInRange(i, values.length);

            FloatVector block =
                    FloatVector.fromArray(SPECIES, values, i, mask);

            float partial = block.reduceLanes(
                    VectorOperators.ADD,
                    mask
            );

            total += partial;
        }

        return total;
    }

    public static void main(String[] args) {
        float[] values = {
                1.25f, 2.5f, 3.75f, 4.0f, 5.5f, 6.0f, 7.25f
        };

        System.out.println(sum(values));
    }
}
```

Vòng lặp tăng `i` theo số lane. Ở block cuối, `indexInRange(i, values.length)` chỉ bật các lane có index nhỏ hơn độ dài mảng. `fromArray(..., mask)` chỉ nạp lane hợp lệ và `reduceLanes(ADD, mask)` chỉ cộng các lane được bật.

Đây là ví dụ về cách viết gọn. Nó không đảm bảo kết quả bit-for-bit giống vòng lặp scalar cộng tuần tự, vì reduction float có thể chọn thứ tự cộng khác.

### 4.1. Scalar baseline để đối chiếu

```java
static double scalarReference(float[] values) {
    double total = 0.0;

    for (float value : values) {
        total += value;
    }

    return total;
}
```

Dùng double làm baseline thường giảm sai số tích lũy so với cộng tuần tự bằng float. Tuy nhiên, đây vẫn là một phép tính dấu phẩy động, không phải tổng thực chính xác tuyệt đối. Nếu cần tham chiếu chính xác cho miền dữ liệu cụ thể, cần xác định mô hình số học phù hợp với nghiệp vụ.

## 5. Thứ tự reduction và sai số floating-point

### 5.1. Vì sao cộng số thực không kết hợp?

Số thực IEEE 754 có độ chính xác hữu hạn. Sau mỗi phép cộng, kết quả được làm tròn về một giá trị biểu diễn được. Vì vậy, nói chung:

[
(a+b)+c \ne a+(b+c)
]

Ví dụ minh họa:

```java
float a = 1.0e20f;
float b = 1.0f;
float c = -1.0e20f;
float d = 1.0f;

float leftToRight = ((a + b) + c) + d;
float grouped = (a + c) + (b + d);

System.out.println(leftToRight);
System.out.println(grouped);
```

Do độ chính xác float hữu hạn, `a + b` có thể làm tròn về `a`. Cách nhóm phép cộng thứ hai triệt tiêu `a` và `c` trước, rồi cộng hai giá trị nhỏ. Hai cách có thể cho kết quả khác nhau.

### 5.2. ADD và MUL trong reduction vector

Javadoc JDK 27 mô tả `ADD` và `MUL` là associative operator để dùng trong reduction, nhưng cộng và nhân float/double không thực sự kết hợp theo số học dấu phẩy động. Thứ tự các phép toán scalar để gộp lane **không được xác định** và có thể thay đổi theo runtime hoặc phần cứng.

JVM được phép chọn lệnh vector hoặc chuỗi lệnh máy tối ưu cho nền tảng. Nếu không có chuỗi lệnh vector phù hợp, implementation mặc định có thể cộng lane tuần tự từ đầu đến cuối. Vì vậy, cùng input có thể cho kết quả khác giữa các cách triển khai.

Điều này có ý nghĩa:

- Không dựa vào kết quả bit-for-bit của `reduceLanes(ADD)` hoặc `reduceLanes(MUL)` cho float/double.
- Không giả định kết quả giống vòng lặp scalar có thứ tự cố định.
- Không dùng `==` để kiểm tra hai kết quả floating-point độc lập nếu sai số làm tròn có thể xảy ra.
- Nếu nghiệp vụ yêu cầu kết quả tái lập bit-for-bit, cần thiết kế một thứ tự cộng cố định và kiểm soát thuật toán; reduction tối ưu không xác định thứ tự không phù hợp với yêu cầu đó.

Với vector `float` hoặc `double`, `reduceLanesToLong()` cũng không phải cách tạo một phép cộng nguyên chính xác: phép reduction vẫn diễn ra theo lane type float/double rồi kết quả mới được cast sang long. Javadoc cảnh báo thao tác này có thể mất độ chính xác hoặc phạm vi; nếu kết quả mong muốn là float/double, ưu tiên `reduceLanes()` trả về đúng lane type.

Các reduction như `MIN` và `MAX` có tính kết hợp/giao hoán theo hợp đồng của API, nhưng cần chú ý NaN và signed zero theo quy tắc floating-point được mô tả trong Javadoc. Với dữ liệu có NaN, hãy xác định trước chính sách lọc hoặc lan truyền NaN.

### 5.3. Sai số tích lũy theo số lượng phần tử

Sai số thường tăng khi:

- Cộng nhiều giá trị có độ lớn rất khác nhau.
- Cộng một giá trị rất nhỏ vào tổng đang có độ lớn rất lớn.
- Dùng `float` thay cho `double`.
- Dùng reduction có thứ tự gộp lane khác với baseline.
- Có giá trị gần giới hạn biểu diễn gây overflow hoặc underflow.

Một lựa chọn là dùng double để tính baseline hoặc accumulator nếu miền dữ liệu cho phép. Điều này giảm sai số so với float, nhưng không biến double thành số thực chính xác tuyệt đối.

Với tiền tệ, không dùng float/double làm đơn vị tiền chính xác. Hãy lưu số tiền theo đơn vị nhỏ nhất bằng integer (ví dụ cents) hoặc dùng `BigDecimal` với scale và rounding policy rõ ràng.

## 6. Masked reduction và identity value

Masked reduction hữu ích khi block cuối không đầy đủ hoặc khi chỉ muốn tổng hợp các lane thỏa điều kiện.

Ví dụ cộng các giá trị dương:

```java
FloatVector vector =
        FloatVector.fromArray(SPECIES, values, offset, boundsMask);

VectorMask<Float> positiveMask =
        vector.compare(VectorOperators.GT, 0.0f)
                .and(boundsMask);

float positiveSum = vector.reduceLanes(
        VectorOperators.ADD,
        positiveMask
);
```

Ở đây:

- `boundsMask` xác định lane nào thuộc mảng.
- `positiveMask` xác định lane nào có giá trị lớn hơn zero.
- `and(boundsMask)` giữ cho mask cuối không chọn lane ngoài phạm vi.
- Reduction chỉ cộng lane dương và hợp lệ.

Đối với MAX/MIN, identity của masked reduction là vô cực âm/dương tương ứng. Điều này giúp block không có lane hợp lệ không ảnh hưởng kết quả khi gộp bằng MAX/MIN. Với ADD, block rỗng đóng góp zero; với MUL, block rỗng đóng góp one.

## 7. Reduction số nguyên và overflow

Với vector integer, `reduceLanes(ADD)` cộng theo kiểu lane. Kết quả `int` hoặc `long` có thể tràn theo quy tắc số nguyên Java.

Ví dụ:

```java
int[] values = { Integer.MAX_VALUE, 1 };

IntVector vector =
        IntVector.fromArray(IntVector.SPECIES_64, values, 0);

int sum = vector.reduceLanes(VectorOperators.ADD);
System.out.println(sum); // tràn số int
```

Một chi tiết dễ nhầm: `reduceLanesToLong(ADD)` không phải cách tự động mở rộng từng lane int trước khi cộng. Với vector có element type int, phương thức này thực hiện reduction theo kiểu lane của vector rồi mới cast kết quả sang long. Nếu tổng int đã tràn, cast sau đó không thể khôi phục giá trị ban đầu.

### 7.1. Mở rộng int thành long trước khi reduction

Muốn tránh overflow int, chuyển các lane sang long trước khi cộng. Khi lane width tăng từ 32 lên 64 bit nhưng shape vector giữ nguyên, số lane của output giảm một nửa. Tham số `part` chọn block kết quả cần lấy.

Ví dụ sau xử lý hai phần của mỗi IntVector:

```java
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.LongVector;
import jdk.incubator.vector.VectorOperators;
import jdk.incubator.vector.VectorSpecies;

public final class ExactIntArraySum {
    private static final VectorSpecies<Integer> INT_SPECIES =
            IntVector.SPECIES_PREFERRED;

    private ExactIntArraySum() {}

    public static long sum(int[] values) {
        long total = 0L;
        int i = 0;
        int upper = INT_SPECIES.loopBound(values.length);

        for (; i < upper; i += INT_SPECIES.length()) {
            IntVector ints =
                    IntVector.fromArray(INT_SPECIES, values, i);

            // I2L mở rộng int thành long; shape giữ nguyên.
            LongVector low = (LongVector)
                    ints.convert(VectorOperators.I2L, 0);

            LongVector high = (LongVector)
                    ints.convert(VectorOperators.I2L, 1);

            total += low.reduceLanes(VectorOperators.ADD);
            total += high.reduceLanes(VectorOperators.ADD);
        }

        // Tail cộng trực tiếp vào long.
        for (; i < values.length; i++) {
            total += values[i];
        }

        return total;
    }
}
```

Với chuyển đổi `I2L`, input int có gấp đôi số lane so với output long cùng vector shape. `part=0` lấy nửa lane đầu sau chuyển đổi, `part=1` lấy nửa còn lại. Cộng cả hai reduction mới bao phủ tất cả giá trị int ban đầu.

Tổng kết:

- `IntVector.reduceLanes(ADD)`: có thể overflow trong miền int.
- `IntVector.reduceLanesToLong(ADD)`: vẫn reduction theo int trước, sau đó mới cast long.
- Chuyển `I2L` trước, sau đó `LongVector.reduceLanes(ADD)`: tích lũy block trong miền long.
- Tổng toàn mảng vẫn có thể overflow long nếu dữ liệu vượt miền long; cần giới hạn nghiệp vụ hoặc kiểu số khác.

## 8. Chuyển đổi kiểu lane bằng convert

### 8.1. Value conversion khác với reinterpretation

`convert()` chuyển đổi **giá trị số** theo conversion operator. Ví dụ `I2F` chuyển một giá trị int thành giá trị float gần tương đương theo quy tắc Java cast.

```java
IntVector ints = IntVector.fromArray(
        IntVector.SPECIES_128,
        new int[] { 1, 2, 3, 4 },
        0
);

FloatVector numbers = (FloatVector)
        ints.convert(VectorOperators.I2F, 0);
```

Ngược lại, `reinterpretAsFloats()` diễn giải lại các bit của vector int như các bit float, không chuyển giá trị số:

```java
IntVector bits = IntVector.broadcast(
        IntVector.SPECIES_128,
        0x3f800000
);

FloatVector one = bits.reinterpretAsFloats();
```

`0x3f800000` là bit pattern của float 1.0. Do đó, reinterpretation trả về lane có giá trị 1.0, trong khi conversion số học từ integer 1,065,353,216 sang float trả về giá trị số 1,065,353,216.0.

| API | Ý nghĩa |
|---|---|
| `convert(VectorOperators.I2F, part)` | Chuyển giá trị int thành float. |
| `convert(VectorOperators.D2F, part)` | Chuyển giá trị double thành float; có thể mất độ chính xác/phạm vi. |
| `convertShape(conversion, species, part)` | Chuyển giá trị và có thể đổi vector shape. |
| `castShape(species, part)` | Tiện ích dùng quy tắc cast Java khi đổi lane type/shape. |
| `reinterpretAsFloats()`, `reinterpretAsInts()` | Giữ bit pattern, chỉ thay cách diễn giải lane. |

Không thay `convert` bằng `reinterpretAs...` nếu mục tiêu là đổi kiểu số học.

### 8.2. Widening conversion

Một số chuyển đổi mở rộng:

| Conversion | Kết quả |
|---|---|
| `I2L` | int → long |
| `I2D` | int → double |
| `F2D` | float → double |
| `S2I` | short → int |
| `B2I` | byte → int |

Widening không phải lúc nào cũng hoàn toàn chính xác cho mọi cặp kiểu. Ví dụ:

- `int → long` bảo toàn mọi giá trị int.
- `float → double` bảo toàn chính xác giá trị float đã biểu diễn.
- `int → float` có thể mất độ chính xác khi trị tuyệt đối vượt vùng mà float biểu diễn mọi số nguyên liên tiếp.
- `long → double` có thể mất độ chính xác với số nguyên lớn hơn khoảng (2^{53}).

Ví dụ, `16_777_217` không thể biểu diễn chính xác bằng float; chuyển sang float có thể cho `16_777_216`. Trong khi đó, mọi giá trị int đều chuyển chính xác sang long.

### 8.3. Narrowing conversion

Một số chuyển đổi thu hẹp:

| Conversion | Hệ quả |
|---|---|
| `D2F` | double → float; có thể mất độ chính xác và phạm vi. |
| `F2I` | float → int; cắt phần thập phân về zero; NaN thành 0 và giá trị ngoài miền được giới hạn ở `Integer.MIN_VALUE` hoặc `Integer.MAX_VALUE` theo quy tắc Java cast. |
| `D2L` | double → long; cắt phần thập phân và có thể mất phạm vi/độ chính xác. |
| `I2S`, `I2B` | int → short/byte; giữ các bit thấp theo quy tắc narrowing integer. |

Ví dụ float lớn hơn `Float.MAX_VALUE` sau khi chuyển từ double có thể thành vô cực. Giá trị quá nhỏ có thể bị làm tròn về zero hoặc subnormal. Không giả định narrowing luôn tạo một giá trị hữu hạn.

## 9. Tham số part khi chuyển đổi lane width

Các phép conversion thường giữ nguyên vector shape. Nếu kích thước lane thay đổi, số lane output có thể khác input; tham số `part` xác định phần logical result nào được chọn hoặc vị trí logical result được chèn vào output.

### 9.1. Mở rộng lane: selection

Ví dụ `I2L` chuyển lane 32-bit thành 64-bit. Với cùng vector shape, output có một nửa số lane. Logical result có nhiều lane hơn output, nên cần chọn một phần:

```java
LongVector lower = (LongVector)
        ints.convert(VectorOperators.I2L, 0);

LongVector upper = (LongVector)
        ints.convert(VectorOperators.I2L, 1);
```

Hai kết quả lần lượt giữ nửa đầu và nửa sau của các giá trị đã chuyển đổi. Nếu chỉ dùng `part=0`, nửa sau bị bỏ khỏi vector kết quả đó.

### 9.2. Thu hẹp lane: insertion

Ví dụ `D2F` chuyển lane 64-bit thành 32-bit. Với cùng vector shape, output có gấp đôi số lane; logical result được đặt vào một phần của output, phần còn lại được zero-padding.

```java
DoubleVector doubles = DoubleVector.fromArray(
        DoubleVector.SPECIES_128,
        new double[] { 1.25, 2.5 },
        0
);

FloatVector floats = (FloatVector)
        doubles.convert(VectorOperators.D2F, 0);
```

Với `part=0`, các giá trị float được đặt ở đầu vector; các lane dư được zero-padding. `part=-1` đặt logical result ở phần cuối của vector output. Không nhầm `part` với offset mảng; đây là chỉ số phần khi chuyển đổi vector.

### 9.3. convertShape và castShape

`convert()` giữ shape của vector đầu vào và là lựa chọn đơn giản cho conversion shape-invariant. `convertShape()` cho phép chỉ định output species khác shape. Khi shape khác nhau, chi phí thực thi có thể khác và không phải nền tảng nào cũng hỗ trợ mọi shape hiệu quả.

`castShape()` là convenience method tương đương `convertShape()` với conversion theo quy tắc Java cast. Dùng khi thực sự muốn đổi lane type/shape bằng cast. Nếu chỉ cần reinterpret bit, hãy dùng API reinterpretation.

## 10. Sai số và kiểm thử kết quả float/double

### 10.1. Không dùng equality tuyệt đối một cách máy móc

Không nên kiểm tra:

```java
if (actual == expected) {
    // exact
}
```

với kết quả reduction float/double nếu thứ tự tính toán có thể khác. Dùng tolerance phù hợp:

[
|actual - expected|
\leq absoluteTolerance + relativeTolerance \times |expected|
]

Ví dụ:

```java
static boolean nearlyEqual(
        double actual,
        double expected,
        double absoluteTolerance,
        double relativeTolerance) {

    if (Double.isNaN(actual) || Double.isNaN(expected)) {
        return Double.isNaN(actual) && Double.isNaN(expected);
    }

    if (Double.isInfinite(actual) || Double.isInfinite(expected)) {
        return actual == expected;
    }

    double difference = Math.abs(actual - expected);
    double allowed = absoluteTolerance
            + relativeTolerance * Math.abs(expected);

    return difference <= allowed;
}
```

Cần chọn tolerance dựa trên miền dữ liệu, số lượng phần tử và độ chính xác nghiệp vụ. Không có một epsilon phù hợp cho mọi phép toán.

### 10.2. NaN, infinity và signed zero

Khi kiểm tra kết quả floating-point:

- `NaN` không bằng chính nó theo toán tử `==`; kiểm tra bằng `Float.isNaN` hoặc `Double.isNaN`.
- `+Infinity` và `-Infinity` cần được xử lý riêng, không đưa vào phép so sánh tolerance thông thường.
- `+0.0` và `-0.0` bằng nhau khi so sánh bằng `==`, nhưng có bit pattern và một số hành vi toán học khác nhau.
- Với `MIN`, `MAX` và `FIRST_NONZERO`, Javadoc Vector API mô tả signed zero là giá trị phân biệt trong một số trường hợp. Nếu signed zero có ý nghĩa nghiệp vụ, hãy kiểm tra bằng `Float.floatToRawIntBits` hoặc `Double.doubleToRawLongBits`.

### 10.3. FMA và khác biệt làm tròn

Vector API có fused multiply-add (FMA): tính (a \times b + c) với intermediate precision mở rộng và chỉ làm tròn ở kết quả cuối. Điều này có thể khác với việc nhân rồi cộng thành hai phép toán riêng, vốn có thể làm tròn sau phép nhân và sau phép cộng.

Nếu so sánh code vector dùng `fma()` với scalar code dùng `a * b + c`, kết quả có thể khác ở bit cuối. Hãy xác định yêu cầu chính xác số học trước khi chọn FMA hoặc cách tính tách rời.

## 11. Bài tập tổng hợp

Thực hiện trên JDK 27 với module incubator được bật:

1. Tạo một `FloatVector` và tính tổng, tích, min, max bằng `reduceLanes()`.
2. Tạo mask chọn các lane dương; dùng `reduceLanes(ADD, mask)` để tính tổng dương.
3. Kiểm tra trường hợp mask không bật lane nào; ghi lại identity value của ADD, MUL, MIN và MAX.
4. Tính tổng một mảng float bằng vector reduction và so sánh với baseline double.
5. Dùng các giá trị có độ lớn rất khác nhau để quan sát ảnh hưởng của thứ tự cộng.
6. Tính tổng mảng int chứa giá trị gần `Integer.MAX_VALUE`; so sánh `reduceLanesToLong` với conversion `I2L` trước reduction.
7. Chuyển `IntVector` sang `FloatVector` bằng `I2F`; thử số nguyên lớn hơn (2^{24}) để quan sát mất độ chính xác.
8. Chuyển `IntVector` sang `LongVector` bằng hai phần `part=0` và `part=1`.
9. Chuyển `DoubleVector` sang `FloatVector` bằng `D2F`; quan sát phần zero-padding và khác biệt với reinterpretation.
10. So sánh vector FMA với phép nhân rồi cộng riêng; giải thích sai số làm tròn.
11. Viết hàm so sánh kết quả dùng absolute + relative tolerance; xử lý riêng NaN, infinity và signed zero.

Bảng ghi nhận:

| Phép thử | Kết quả cần ghi | Điều cần giải thích |
|---|---|---|
| Float ADD reduction | Kết quả vector và scalar | Thứ tự cộng không xác định. |
| Masked reduction | Mask và identity | Mask rỗng không tương đương dữ liệu có tổng bằng zero. |
| Integer sum | int result, long result | Overflow xảy ra trước hay sau widening. |
| I2F | Input int và output float | Độ chính xác float có giới hạn. |
| I2L | Hai part output | Lane width tăng nên phải chọn hai phần. |
| D2F | part, lane output, zero padding | Lane width giảm nên logical result được chèn vào output. |
| Reinterpretation | Bit pattern và giá trị hiển thị | Không phải chuyển đổi giá trị số. |
| FMA | Kết quả FMA và multiply-add | Số lần làm tròn khác nhau. |

## 12. Checklist trước khi dùng

- [ ] Đã xác nhận Vector API vẫn là incubator trong JDK 27.
- [ ] Đã thêm `--add-modules jdk.incubator.vector` ở compile và runtime.
- [ ] Đã chọn species phù hợp, thường bắt đầu bằng `SPECIES_PREFERRED`.
- [ ] Đã chọn đúng reduction operator và mask.
- [ ] Đã hiểu identity value khi mask rỗng.
- [ ] Không giả định floating ADD/MUL reduction có thứ tự cố định.
- [ ] Không dùng `reduceLanesToLong` như cách tránh overflow của IntVector.
- [ ] Đã widening lane trước khi reduction nếu cần miền tích lũy lớn hơn.
- [ ] Đã chọn đúng conversion operator và hiểu mất mát khi narrowing.
- [ ] Không nhầm `convert()` với `reinterpretAs...`.
- [ ] Đã chọn đúng `part` khi lane width thay đổi.
- [ ] Đã kiểm tra NaN, infinity, signed zero và tolerance.
- [ ] Đã benchmark và kiểm tra tính đúng trên JDK/CPU triển khai.

## Tài liệu tham khảo chính thức

- [JEP 537: Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537)
- [JDK 27 Release Notes — Vector API](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Vector API Package Summary — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html)
- [Vector API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html)
- [FloatVector — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html)
- [IntVector — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html)
- [LongVector — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/LongVector.html)
- [DoubleVector — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/DoubleVector.html)
- [VectorOperators — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorOperators.html)
- [VectorSpecies — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html)

