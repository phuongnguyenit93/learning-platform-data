# Khác biệt kết quả dấu phẩy động và yêu cầu về sai số khi vector hóa

## Phạm vi và phiên bản sử dụng

Bài học thuộc chương **Vector API** của module **JAVA_VERSION_JAVA22**, dành cho việc học những tính năng có mặt ở Java 22 và còn hữu ích trong Java hiện đại. Trọng tâm là xác định khi nào kết quả số thực có thể thay đổi sau vector hóa, cách định nghĩa sai số chấp nhận được và cách giữ hợp đồng số học của ứng dụng.

Vector API đã hiện diện trong Java 22 dưới dạng module incubator `jdk.incubator.vector`; đây không phải lần đầu API xuất hiện. Bối cảnh được mô tả trong [module Vector API của Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/module-summary.html).

**Mốc đối chiếu của bài là ngày 25/11/2026. Các ví dụ dùng JDK 27**, nơi Vector API vẫn ở trạng thái incubator, lần ươm tạo thứ mười hai. Bài sử dụng các phép toán đang được tài liệu hiện hành mô tả, không dựa vào biến thể API cũ hoặc tùy chọn JVM không còn phù hợp. Trạng thái phiên bản được xác nhận trong [các thay đổi của JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html).

## 1. Định nghĩa kết quả đúng trước khi tối ưu

Một phiên bản vector có thể cho kết quả khác phiên bản scalar ở một số bit cuối, thậm chí khác đáng kể với dữ liệu có triệt tiêu mạnh. Muốn đánh giá đúng, trước hết phải xác định ứng dụng yêu cầu điều gì.

| Loại yêu cầu | Điều cần giữ |
| --- | --- |
| Khớp từng bit với một thuật toán đã chỉ định | Giữ đúng kiểu trung gian, cách làm tròn, thứ tự kết hợp và quy tắc cho giá trị đặc biệt. |
| Độ chính xác số học theo một dung sai | Sai số so với giá trị tham chiếu phải nằm trong giới hạn đã định nghĩa. |
| Chất lượng đầu ra của ứng dụng | Ngoài sai số số học, kết quả phải đáp ứng yêu cầu như ngưỡng quyết định hoặc chất lượng tín hiệu. |

“Gần giống mã cũ” và “gần giá trị toán học hơn” là hai tiêu chí riêng. Nếu mã scalar đã mất thông tin do làm tròn, ép phiên bản vector khớp nó từng bit có thể giữ lại sai số đó. Ngược lại, khi hợp đồng bắt buộc tương thích từng bit, một kết quả gần giá trị toán học hơn vẫn có thể không đáp ứng hợp đồng.

Cần phân biệt thêm hai đại lượng:

- **Độ lệch giữa các phiên bản:** chênh lệch giữa kết quả vector và kết quả scalar.
- **Sai số đối với tham chiếu:** chênh lệch giữa kết quả tính được và giá trị tham chiếu đủ chính xác cho bài toán.

Vòng lặp scalar đơn giản thường là baseline dễ đọc, nhưng không tự trở thành một tham chiếu số học chính xác tuyệt đối.

## 2. Vì sao phép cộng dấu phẩy động không có tính kết hợp?

`float` dùng định dạng nhị phân 32 bit với độ chính xác phần định trị 24 bit; `double` dùng định dạng 64 bit với độ chính xác 53 bit. Không phải mọi số thực đều biểu diễn được. Sau nhiều phép toán, kết quả phải được làm tròn về tập giá trị của kiểu đó. Các đặc điểm kiểu được quy định trong [JLS về kiểu dấu phẩy động](https://docs.oracle.com/javase/specs/jls/se27/html/jls-4.html#jls-4.2.3).

Ví dụ sau dùng các đầu vào biểu diễn chính xác được bằng `float`:

```java
float a = 16_777_216f; // 2^24
float b = 1f;
float c = -16_777_216f;

System.out.println((a + b) + c); // 0.0
System.out.println(a + (b + c)); // 1.0
```

Tại `2^24`, khoảng cách tới số `float` lớn hơn kế tiếp là `2`. Tổng `a + b` nằm giữa hai giá trị biểu diễn được và làm tròn về `a`, nên lần cộng với `c` sau đó cho `0`.

Trong biểu thức còn lại, `b + c` là `-16_777_215`, biểu diễn được chính xác. Cộng với `a` cho `1`.

```text
Cách nhóm thứ nhất:     (16_777_216 + 1) + (-16_777_216)
                               ↓ làm tròn
                           16_777_216 + (-16_777_216) = 0

Cách nhóm thứ hai:      16_777_216 + (1 + (-16_777_216))
                                           ↓
                       16_777_216 + (-16_777_215) = 1
```

Theo số học thực, cả hai đều bằng `1`. Theo số học dấu phẩy động, cách đặt ngoặc quyết định những lần làm tròn trung gian.

Java không cho phép trình biên dịch tùy ý dùng tính kết hợp của số thực để viết lại một biểu thức scalar thành biểu thức có kết quả quan sát được khác. Quy tắc bảo toàn dấu ngoặc và thứ tự phép tính được nêu trong [JLS về thứ tự đánh giá](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html#jls-15.7.3). Khi đổi thuật toán sang nhiều bộ tích lũy hoặc reduction, chính mã mới đã chọn một cách nhóm phép tính khác.

## 3. Phép toán theo lane và reduction có hợp đồng khác nhau

### 3.1. Phép toán theo lane

Với một phép cộng hai vector, mỗi lane thực hiện phép cộng của cặp giá trị tương ứng. Nếu thuật toán giữ cùng kiểu dữ liệu và cùng chuỗi phép toán trên từng phần tử, việc gom các phần tử độc lập vào vector không mặc nhiên làm mọi kết quả thay đổi.

Ví dụ:

```text
Scalar trên từng vị trí:       out[i] = a[i] + b[i]
Vector theo lane:              kết quả[k] = a[k] + b[k]
```

Đặc tả của `VectorOperators` yêu cầu phép toán dấu phẩy động theo lane tuân theo độ chính xác và tính đơn điệu của phép toán Java tương ứng, trừ trường hợp tài liệu chỉ rõ khác. Không có quyền tự do làm tròn tùy ý chỉ vì phép toán chạy bằng SIMD.

### 3.2. Reduction giữa các lane

Một tổng vector cần gom nhiều lane thành một giá trị. Với `ADD` và `MUL` trong reduction số thực, thứ tự kết hợp **không được đặc tả cố định**. Điều này cho phép runtime chọn cách thực hiện phù hợp với nền tảng.

Hợp đồng đó không bảo đảm luôn cộng lần lượt từ lane `0` tới lane cuối. Không nên dựa vào việc một bản JDK hoặc một CPU hiện tại tình cờ dùng thứ tự nào đó. Quy tắc được nêu trực tiếp trong [VectorOperators: operations on floating point vectors](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorOperators.html).

Ngoài reduction cuối, bản thân vòng lặp tích lũy theo lane cũng nhóm lại dữ liệu. Với `L` lane, lane `0` có thể cộng các phần tử `0, L, 2L, ...`, lane `1` cộng `1, L+1, 2L+1, ...`. Đây đã là thứ tự khác với một biến tổng duy nhất đi từ đầu mảng đến cuối mảng.

## 4. Ví dụ đầy đủ: tổng scalar bằng 0, tổng vector bằng 1

Ví dụ này chủ động đặt hai số lớn trái dấu vào cùng lane ở hai lượt xử lý. Giá trị `1` nằm ở lane khác. Các phần tử còn lại bằng `0`.

Lưu thành `VectorRoundingDemo.java` trong môi trường học có JDK 27:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorOperators;
import jdk.incubator.vector.VectorSpecies;

public class VectorRoundingDemo {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    static float sumScalar(float[] values) {
        float sum = 0f;
        for (float value : values) {
            sum += value;
        }
        return sum;
    }

    static float sumVector(float[] values) {
        FloatVector accumulator = FloatVector.zero(SPECIES);
        int bound = SPECIES.loopBound(values.length);
        int i = 0;

        for (; i < bound; i += SPECIES.length()) {
            FloatVector current = FloatVector.fromArray(SPECIES, values, i);
            accumulator = accumulator.add(current);
        }

        float sum = accumulator.reduceLanes(VectorOperators.ADD);
        for (; i < values.length; i++) {
            sum += values[i];
        }
        return sum;
    }

    static double sumWider(float[] values) {
        double sum = 0.0;
        for (float value : values) {
            sum += value;
        }
        return sum;
    }

    public static void main(String[] args) {
        int lanes = SPECIES.length();
        if (lanes < 2) {
            throw new IllegalStateException("Ví dụ cần ít nhất hai lane");
        }

        float[] values = new float[2 * lanes + 1];
        values[0] = 0x1.0p24f;
        values[1] = 1f;
        values[lanes] = -0x1.0p24f;

        System.out.println("lanes=" + lanes);
        System.out.println("scalar=" + sumScalar(values));
        System.out.println("vector=" + sumVector(values));
        System.out.println("wider=" + sumWider(values));
    }
}
```

Biên dịch và chạy bằng công cụ của cùng JDK 27:

```shell
javac --add-modules jdk.incubator.vector VectorRoundingDemo.java
java --add-modules jdk.incubator.vector VectorRoundingDemo
```

Ví dụ kết quả khi species có tám lane:

```text
lanes=8
scalar=0.0
vector=1.0
wider=1.0
```

Số lane phụ thuộc nền tảng; cách dựng dữ liệu trong ví dụ thích nghi với số lane được chọn. Các giá trị `scalar`, `vector` và `wider` ở đây được giải thích từ chính bộ dữ liệu, không phải số liệu benchmark.

Ở phiên bản vector, hai số lớn triệt tiêu trong lane `0` thành `0`, còn lane `1` giữ `1`. Reduction cuối chỉ gom một giá trị `1` với các giá trị `0`, nên ví dụ này không phụ thuộc vào việc reduction chọn cây cộng cụ thể nào. Phần đuôi có một số `0`.

Ở phiên bản scalar, `1` đã bị làm tròn mất ngay sau số lớn đầu tiên. Trong ví dụ này, tổng tích lũy bằng `double` giữ được kết quả chính xác là `1`. Điều đó không biến mọi phép cộng bằng `double` thành một tham chiếu chính xác cho mọi mảng đầu vào.

`SPECIES_PREFERRED`, số lane và giới hạn vòng lặp được mô tả trong [VectorSpecies](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html). Việc phân giải module khi biên dịch và chạy được mô tả trong [javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) và [java launcher](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html). Riêng ví dụ Vector API với mảng này không yêu cầu `--enable-preview`.

## 5. FMA và hai lần làm tròn của nhân rồi cộng

FMA, tức fused multiply-add, tính `a * b + c` như một phép toán có kết quả trung gian chính xác rồi làm tròn một lần về kiểu kết quả. Chuỗi nhân rồi cộng riêng thực hiện làm tròn sau phép nhân, sau đó làm tròn tiếp sau phép cộng.

Hai cách vì thế có thể khác nhau ngay trên một phần tử, trước khi xuất hiện reduction.

Đặt đoạn sau trong một phương thức của lớp ví dụ, nơi đã có `SPECIES`:

```java
float delta = 0x1.0p-23f;
float a = 1.0f + delta;
float b = 1.0f - delta;

float separate = a * b + (-1.0f);
float fused = Math.fma(a, b, -1.0f);

float vectorSeparate = FloatVector.broadcast(SPECIES, a)
        .mul(b).add(-1.0f).lane(0);
float vectorFused = FloatVector.broadcast(SPECIES, a)
        .fma(b, -1.0f).lane(0);

System.out.println(Float.toHexString(separate));
System.out.println(Float.toHexString(fused));
System.out.println(Float.toHexString(vectorSeparate));
System.out.println(Float.toHexString(vectorFused));
```

Kết quả dự kiến:

```text
0x0.0p0
-0x1.0p-46
0x0.0p0
-0x1.0p-46
```

Tích thực của hai đầu vào là `(1 + 2^-23) * (1 - 2^-23) = 1 - 2^-46`. Nhân riêng làm tròn tích về `1`, rồi trừ `1` cho `0`. FMA giữ phần `-2^-46` đến lúc làm tròn cuối cùng.

FMA trong trường hợp này gần giá trị toán học hơn, nhưng chuyển từ chuỗi nhân-cộng sang FMA vẫn là thay đổi ngữ nghĩa làm tròn cần được hợp đồng cho phép. Mô tả của các phép FMA vector nằm trong [FloatVector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html) và [DoubleVector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/DoubleVector.html).

Khi dùng FMA ở phần vector của một kernel theo phần tử, phần đuôi scalar cũng cần chọn cùng ngữ nghĩa nếu ứng dụng yêu cầu nhất quán:

```java
out[i] = Math.fma(a[i], b[i], c[i]);
```

Nếu phần vector dùng `.fma(...)` còn phần đuôi dùng `a[i] * b[i] + c[i]`, cùng một bộ giá trị có thể được tính theo hai cách làm tròn tùy vị trí của nó so với biên nhóm lane.

## 6. Những nguồn khác làm kết quả thay đổi

### 6.1. Thay số lane hoặc số bộ tích lũy

Đổi species, CPU, cách chia khối hoặc số bộ tích lũy có thể đổi nhóm các số được cộng trước. Với tổng hoặc tích vô hướng, sự thay đổi này ảnh hưởng các giá trị trung gian và mức triệt tiêu.

Chọn một species cố định chỉ cố định một phần cấu trúc. Nó không tự ép `reduceLanes(ADD)` dùng một thứ tự mà đặc tả không cam kết. Ngay cả trên cùng nền tảng, không nên coi một kết quả reduction quan sát được là hợp đồng bất biến qua mọi thay đổi runtime.

### 6.2. Thời điểm chuyển từ float sang double

Hai dòng sau không có cùng ý nghĩa về độ chính xác:

```java
double productAfterRounding = (double) (a * b);
double productInDouble = (double) a * (double) b;
```

Giả sử `a` và `b` là `float`: dòng đầu đã nhân và làm tròn theo `float` trước khi mở rộng. Dòng sau mở rộng đầu vào rồi nhân theo `double`. Mở rộng sau cùng không khôi phục phần đã mất trước đó.

Việc mở rộng một giá trị `float` hữu hạn sang `double` giữ chính xác giá trị nhị phân đã lưu; thu hẹp từ `double` sang `float` có thể mất độ chính xác hoặc miền biểu diễn. Quy tắc chuyển kiểu được nêu trong [JLS về chuyển đổi primitive](https://docs.oracle.com/javase/specs/jls/se27/html/jls-5.html#jls-5.1.2).

### 6.3. Hàm toán học có hợp đồng sai số riêng

Các hàm như `sin`, `exp` hoặc `log` có yêu cầu độ chính xác riêng. Những triển khai hợp lệ có thể khác một số bit trong phạm vi đặc tả. Không được áp một quy tắc duy nhất rằng mọi hàm vector phải khớp từng bit với một hàm scalar bất kỳ.

Nếu baseline gọi một hàm thuộc `StrictMath`, hãy đối chiếu đúng hợp đồng của nó với toán tử vector định dùng. Một số hàm của `StrictMath` yêu cầu kết quả theo thuật toán được chỉ định, nhưng yêu cầu đó không tự truyền sang một phép gọi vector khác. Xem [StrictMath của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/StrictMath.html).

### 6.4. Overflow, underflow và triệt tiêu

Đổi thứ tự phép tính còn có thể làm một kết quả trung gian vượt miền biểu diễn, hoặc trở nên quá nhỏ rồi mất thông tin. Vì vậy, khác biệt không luôn giới hạn ở một vài ULP cuối cùng.

Triệt tiêu xảy ra khi lấy tổng hoặc hiệu của những giá trị lớn gần đối nhau và chỉ còn một kết quả nhỏ. Những sai số đã có trong các thành phần có thể trở nên lớn khi so với phần kết quả còn lại. Với dữ liệu như vậy, một tiêu chí chỉ dùng sai số tương đối của tổng cuối thường không đủ.

## 7. Chọn thước đo sai số phù hợp

### 7.1. Sai số tuyệt đối

Với giá trị tham chiếu `r` và kết quả `x`:

```text
absoluteError = |x - r|
```

Sai số tuyệt đối có cùng đơn vị với dữ liệu. Nó đặc biệt hữu ích khi kết quả ở gần `0`, nơi chia cho độ lớn của tham chiếu dễ làm sai số tương đối rất lớn hoặc không xác định.

Một giới hạn tuyệt đối cần xuất phát từ ý nghĩa đầu ra. Chẳng hạn, một hệ xử lý tín hiệu cần đánh giá lượng nhiễu chấp nhận được theo đơn vị tín hiệu, thay vì chọn số chữ số thập phân tùy ý.

### 7.2. Sai số tương đối

Khi `r` khác `0`, cách định nghĩa thường gặp là:

```text
relativeError = |x - r| / |r|
```

Nó cho biết độ lệch so với quy mô của kết quả. Một sai số tuyệt đối bằng `1` có ý nghĩa khác nhau nếu đầu ra ở quy mô `10^9` hoặc `10^-9`.

Nếu dùng một tiêu chí so sánh đối xứng, có thể lấy quy mô từ cả hai giá trị. Bài sử dụng quy tắc kết hợp sau cho các giá trị hữu hạn:

```text
|x - r| <= absTol + relTol * max(|x|, |r|)
```

`absTol` có cùng đơn vị với kết quả; `relTol` không có đơn vị. Đây là một chính sách so sánh cụ thể. Một hệ thống chọn quy tắc dùng riêng độ lớn tham chiếu hoặc chọn `max` giữa hai ngưỡng cần ghi rõ và dùng nhất quán chính sách của nó.

### 7.3. ULP

ULP là đơn vị gắn với khoảng cách giữa những giá trị dấu phẩy động biểu diễn được tại một quy mô nhất định. Nó giúp nói về độ lệch ở mức biểu diễn thay vì một số chữ số thập phân cố định.

Ví dụ với `float`, `Math.ulp(1.0f)` bằng `2^-23`; tại `0`, kết quả là giá trị `float` dương nhỏ nhất, `Float.MIN_VALUE`. Định nghĩa và các trường hợp đặc biệt nằm trong [Math.ulp](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Math.html).

Ngưỡng ULP phù hợp cho một số phép toán có hợp đồng độ chính xác cục bộ. Với một tổng dài có triệt tiêu, yêu cầu kết quả phải cách baseline một số ULP nhỏ có thể không phản ánh đúng bài toán. Nếu cần đếm số bước biểu diễn giữa hai giá trị, phải xử lý riêng dấu, số không và NaN; không lấy hiệu hai mẫu bit có dấu một cách trực tiếp.

### 7.4. Không có một epsilon chung cho mọi kernel

Độ chính xác của kiểu dữ liệu chỉ là một phần của yêu cầu. Ngưỡng chấp nhận còn phụ thuộc:

- Số lượng phép toán và cách tổ chức reduction.
- Miền giá trị đầu vào và mức triệt tiêu.
- Kiểu dùng cho trung gian, tích lũy và đầu ra.
- Việc có dùng FMA hoặc hàm toán học với sai số riêng hay không.
- Mức sai số mà bước xử lý sau có thể chịu được.

Không tăng dung sai chỉ vì một phiên bản mới chưa vượt qua phép đối chiếu. Trước hết cần xác định nguyên nhân: thay đổi phép tính hợp lệ, lỗi mask, bỏ sót phần đuôi, sai chuyển kiểu hay bản thân thuật toán không đủ ổn định.

## 8. Mẫu so sánh float có chính sách rõ ràng

Hàm dưới đây dùng quy tắc kết hợp ở mục trước. Nó nhận hai kết quả `float`, tính độ lệch bằng `double` và quy định rõ:

- Từ chối NaN ở cả hai phía.
- Chấp nhận vô cực khi hai phía cùng dấu.
- Coi `+0.0f` và `-0.0f` là tương đương về giá trị.
- Yêu cầu `absTol` hữu hạn, không âm; `relTol` hữu hạn trong `[0, 1]`.

Đây là hàm tiện ích có thể đặt trong lớp ví dụ; các ngưỡng phải do hợp đồng của ứng dụng cung cấp:

```java
static boolean closeFloat(
        float expected,
        float actual,
        double absTol,
        double relTol) {
    if (!Double.isFinite(absTol) || absTol < 0.0
            || !Double.isFinite(relTol) || relTol < 0.0 || relTol > 1.0) {
        throw new IllegalArgumentException("Dung sai không hợp lệ");
    }

    if (Float.isNaN(expected) || Float.isNaN(actual)) {
        return false;
    }

    // Bao gồm cùng dấu vô cực và hai số không có dấu khác nhau.
    if (expected == actual) {
        return true;
    }

    if (!Float.isFinite(expected) || !Float.isFinite(actual)) {
        return false;
    }

    double reference = expected;
    double observed = actual;
    double difference = Math.abs(observed - reference);
    double scale = Math.max(Math.abs(reference), Math.abs(observed));

    return difference <= absTol + relTol * scale;
}
```

Hàm mở rộng hai đầu vào hữu hạn từ `float` sang `double` trước khi trừ, nên tránh tràn trong phép trừ sai số của hai số `float` lớn trái dấu. Đây là một lựa chọn dành cho miền đầu vào `float`; không sao chép máy móc rồi đổi tham số thành `double` mà bỏ qua nguy cơ overflow của phép trừ hoặc ngưỡng so sánh.

Hành vi kiểm tra NaN, giá trị hữu hạn và biểu diễn bit được mô tả trong [Float](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Float.html) và [Double](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Double.html).

Các quy tắc của hàm là lựa chọn của bài, không phải một chuẩn bắt buộc cho mọi ứng dụng. Nếu NaN là kết quả được phép cho một miền đầu vào, hãy tách tiêu chí kiểm tra NaN khỏi so sánh dung sai. Nếu cần phân biệt số không có dấu, hãy xử lý dấu của số không trước nhánh `expected == actual`.

Quan hệ “gần nhau” theo dung sai cũng không nhất thiết có tính bắc cầu. Không dùng hàm này làm định nghĩa `equals` tổng quát cho khóa của `Map` hoặc phần tử của `Set`.

## 9. NaN, vô cực, số không có dấu và phần đuôi

### 9.1. Giá trị đặc biệt cần chính sách riêng

| Giá trị hoặc tình huống | Điều cần quyết định |
| --- | --- |
| NaN | Có được phép xuất hiện không; cần hai phía cùng NaN hay yêu cầu từ chối dữ liệu đó. |
| Vô cực | Có phải kết quả hợp lệ theo miền đầu vào không; phải giữ dấu khi so sánh. |
| `+0.0` và `-0.0` | Có được coi tương đương không, nhất là khi kết quả còn đi vào phép nghịch đảo. |
| Số subnormal | Thuật toán có cần giữ các giá trị rất nhỏ và độ nhạy gần underflow không. |
| Overflow của trung gian | Có làm kết quả đổi thành vô cực hoặc NaN dù một cách nhóm khác cho giá trị hữu hạn không. |

`+0.0f == -0.0f` là `true`, nhưng `1.0f / +0.0f` và `1.0f / -0.0f` cho hai vô cực khác dấu. Còn NaN không bằng chính nó theo phép `==`. Vì vậy, chỉ nhìn một phép so sánh bằng hoặc một chuỗi số đã định dạng có thể bỏ qua điều hợp đồng thực sự cần giữ.

Khi cần khớp bit, phải chỉ định có chuẩn hóa NaN hay giữ mẫu bit thô. Phép toán dấu phẩy động không cung cấp một cam kết chung rằng payload NaN đầu vào sẽ được bảo toàn qua mọi phép tính.

### 9.2. Mask bảo vệ biên không tự bảo vệ mọi phép tính số học

Load có mask thường tạo giá trị `0` ở các lane không hoạt động. Những giá trị đó không luôn là đầu vào vô hại cho các bước tiếp theo.

Ví dụ, một kernel tính nghịch đảo ở nhóm cuối có thể nạp `0` vào lane ngoài biên. Nếu lấy `1 / 0` ở lane đó rồi reduction không có mask, vô cực của lane không hợp lệ có thể đi vào kết quả tổng. Hoặc một phép nhân với vô cực tại lane đệm `0` có thể sinh NaN.

Cần mang mask hợp lệ tới những phép toán và reduction có hợp đồng cho phép chọn lane, hoặc tổ chức phần đuôi scalar để loại những lane đó khỏi kết quả. Chỉ mask thao tác ghi mảng không đủ nếu reduction đã nhận dữ liệu của lane ngoài phạm vi.

Ngay cả khi điền `0` không ảnh hưởng tổng thông thường, thêm phép cộng với `0` vẫn cần xét riêng nếu ứng dụng có yêu cầu nghiêm ngặt về dấu của số không. Với tích, min hoặc max, phần tử trung hòa lại khác. Hợp đồng reduction có mask và các giá trị trả về khi không có lane nào được chọn được mô tả trong [DoubleVector.reduceLanes](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/DoubleVector.html).

## 10. Xây dựng giá trị tham chiếu phù hợp

### 10.1. Phân biệt đầu vào đã lưu và số thập phân mong muốn

Một mảng `float` chứa những giá trị nhị phân đã được làm tròn khi nhập. Nếu mục tiêu là đánh giá sai số của kernel trên mảng đó, tham chiếu cần bắt đầu từ chính các giá trị đã lưu.

Chuyển chúng thành chuỗi thập phân ngắn để rồi tính lại có thể thay đổi bài toán tham chiếu: chuỗi in ra bảo đảm đọc lại được giá trị, nhưng số thập phân mà chuỗi mô tả không nhất thiết bằng chính xác giá trị nhị phân ban đầu.

### 10.2. Tham chiếu chính xác cho tổng các float hữu hạn

Với một tập dữ liệu đối chiếu vừa phải, có thể dùng số học thập phân tùy ý để tính tổng chính xác của những giá trị nhị phân hữu hạn đã lưu. Cần import `java.math.BigDecimal` cho phương thức sau:

```java
static BigDecimal exactSumOfStoredFloats(float[] values) {
    BigDecimal sum = BigDecimal.ZERO;

    for (float value : values) {
        if (!Float.isFinite(value)) {
            throw new IllegalArgumentException("Chỉ nhận float hữu hạn");
        }

        // float -> double giữ nguyên giá trị nhị phân đã lưu.
        // Constructor này chuyển đúng giá trị double đó sang thập phân.
        BigDecimal exactValue = new BigDecimal((double) value);
        sum = sum.add(exactValue);
    }

    return sum;
}
```

Phương thức không đặt `MathContext`, nên các phép cộng ở đây được tính chính xác. Mục đích là tạo tham chiếu ngoài kernel tối ưu, không phải đặt `BigDecimal` vào vòng SIMD cần hiệu năng.

Trong trường hợp này, chọn `new BigDecimal((double) value)` là có chủ đích: constructor giữ đúng giá trị nhị phân của đầu vào. `BigDecimal.valueOf(double)` đi qua biểu diễn chuỗi chuẩn, có ý nghĩa khác. Hai cách chuyển đổi được phân biệt trong [tài liệu BigDecimal](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigDecimal.html).

Nếu đầu ra cần một `float` được làm tròn từ tổng chính xác, đó là một hợp đồng riêng với việc tái hiện từng bước cộng bằng `float`. Với tích vô hướng hoặc thuật toán nhiều giai đoạn, cũng phải xác định tham chiếu đang đánh giá tích chính xác của đầu vào, tích đã làm tròn theo `float`, hay một chuỗi FMA cụ thể.

Mẫu `closeFloat` nhận tham chiếu đã là `float`. Nếu cần đo sai số trực tiếp so với tham chiếu độ chính xác cao, hãy giữ độ chính xác đó trong bước tính sai số thay vì ép nó về `float` quá sớm.

## 11. Chọn cách giảm sai số và giữ khả năng tái lập

Có thể thay đổi thuật toán để tăng độ chính xác thay vì chỉ nới ngưỡng so sánh:

| Cách tổ chức | Lợi ích có thể đạt được | Giới hạn cần nhớ |
| --- | --- | --- |
| Tích lũy bằng kiểu rộng hơn | Giảm mất thông tin ở các bước cộng trung gian | Không khôi phục sai số đã xảy ra trước khi mở rộng. |
| Cộng theo cây hoặc theo khối phù hợp | Có thể giảm một số dạng tích lũy sai số | Thay đổi thứ tự; cần đánh giá theo dữ liệu và hợp đồng. |
| Dùng thuật toán cộng bù | Theo dõi một phần thông tin bị mất do làm tròn | Thêm chi phí và cần thiết kế riêng khi chia thành nhiều lane. |
| Dùng FMA khi hợp đồng cho phép | Giảm một lần làm tròn trong nhân-cộng | Có thể khác kết quả của chuỗi nhân rồi cộng cũ. |
| Chuẩn hóa hoặc đổi công thức ổn định hơn | Hạn chế overflow, underflow hoặc triệt tiêu không cần thiết | Phải phân tích lại công thức và miền đầu vào. |

Tài liệu [DoubleStream.sum](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/DoubleStream.html#sum()) cũng thảo luận việc dùng kỹ thuật cộng bù và ảnh hưởng của thứ tự cộng. Đây là bối cảnh về lựa chọn thuật toán; không phải cam kết rằng gọi một API tổng khác sẽ khớp thuật toán vector đang viết.

Nếu yêu cầu là tái lập từng bit giữa các môi trường, cần đặc tả đầy đủ cấu trúc phép tính, kiểu dữ liệu, chính sách FMA, hàm toán học và xử lý giá trị đặc biệt. Một reduction có thứ tự không được đặc tả không đủ để bảo đảm yêu cầu này, kể cả khi cố định số lane.

Có thể giữ một đường tính toán có thứ tự được kiểm soát cho những đầu ra cần tương thích nghiêm ngặt, đồng thời dùng vector cho các bước theo phần tử mà hợp đồng cho phép. Quyết định này phải được đánh giá cùng hiệu năng và mức chính xác cần thiết của từng đầu ra.

## 12. Ghi rõ hợp đồng sai số khi đưa kernel vào ứng dụng

Một mô tả đủ dùng cho người bảo trì cần nêu:

1. Miền đầu vào: kích thước, khoảng giá trị, NaN, vô cực và subnormal có được phép hay không.
2. Công thức số học: kiểu trung gian, kiểu tích lũy, thứ tự hoặc quyền thay đổi thứ tự và chính sách FMA.
3. Tham chiếu: tái hiện mã cũ hay đánh giá độ chính xác toán học của đầu vào đã lưu.
4. Tiêu chí: khớp bit, sai số tuyệt đối, tương đối, ULP hoặc chỉ tiêu chất lượng đầu ra nào.
5. Phạm vi cam kết: những cấu hình JDK, CPU, species và miền dữ liệu mà yêu cầu áp dụng.

Các nhóm dữ liệu giúp làm rõ giới hạn của một kernel gồm giá trị cùng dấu, giá trị lớn nhỏ xen kẽ, các cặp gần triệt tiêu, dữ liệu gần ngưỡng quyết định, trường hợp đặc biệt được phép và độ dài nằm quanh biên một nhóm lane. Chỉ dùng dữ liệu ngẫu nhiên vừa phải có thể bỏ qua chính những trường hợp làm thuật toán nhạy với thứ tự tính.

| Hiện tượng | Hướng phân tích |
| --- | --- |
| Kết quả thay đổi khi đổi số lane | Xem lại nhóm tích lũy, reduction và cách ghép phần đuôi. |
| Chỉ phần đuôi khác phần vector | Đối chiếu FMA, chuyển kiểu và mask ở hai đường. |
| Sai số tương đối rất lớn khi kết quả gần 0 | Xem mức triệt tiêu và tiêu chí sai số tuyệt đối theo đơn vị đầu ra. |
| Kết quả đột ngột thành NaN hoặc vô cực | Kiểm tra trung gian, lane ngoài biên và miền của phép toán. |
| Vector khác baseline nhưng gần tham chiếu hơn | Xác định lại hợp đồng đang yêu cầu độ chính xác hay tương thích với baseline. |
| Cùng số chữ số in ra nhưng yêu cầu khớp bit thất bại | Quan sát biểu diễn bit, số không có dấu và quy tắc chuẩn hóa NaN. |
| Cần dung sai lớn hơn sau mỗi lần thay mã | Tìm nguyên nhân thay đổi và đánh giá lại thuật toán trước khi sửa ngưỡng. |
