# Bài tập tính tích vô hướng, lọc dữ liệu và so sánh hiệu năng với vòng lặp vô hướng

## 1. Mục tiêu và phạm vi phiên bản

Bài thực hành này thuộc chương **Vector API** của module **JAVA_VERSION_JAVA22 — Học các tính năng được giới thiệu trong Java 22 còn hữu ích ở Java hiện đại**. Bạn sẽ viết hai thuật toán theo cả cách vô hướng và cách dùng SIMD, kiểm tra tính đúng, rồi đo xem cách dùng vector có mang lại lợi ích trên máy của mình hay không.

Trong Java 22, Vector API được đưa vào vòng incubator thứ bảy theo JEP 460; API này đã xuất hiện trước Java 22. Vì vậy, đừng xem mọi phương thức trong bài là tính năng mới được thêm riêng ở phiên bản 22. Xem phần Vector API trong [thông báo phát hành Java 22 của Oracle](https://blogs.oracle.com/java/the-arrival-of-java-22).

**Mốc đối chiếu: ngày 25/11/2026.** Java 27 vẫn cung cấp Vector API ở trạng thái incubator, vòng thứ mười hai theo JEP 537. Các kỹ thuật xử lý mảng, mask và phép giảm trong bài vẫn có ý nghĩa, nhưng API chưa phải một API Java SE ổn định. Khi đổi JDK, hãy biên dịch lại, kiểm tra lại và đo lại. Xem [ghi chú phát hành JDK 27](https://www.oracle.com/java/technologies/javase/27all-relnotes.html).

Kết quả cần đạt:

- Tính tích vô hướng của hai mảng `float[]` bằng một bộ tích lũy vector.
- Lọc mảng theo điều kiện `x > threshold`, nén kết quả liên tục và giữ thứ tự.
- Xử lý đúng mảng rỗng, mảng ngắn hơn vector và phần đuôi không đủ một vector.
- So sánh thời gian bằng JMH và giải thích kết quả dựa trên dữ liệu đo thực tế.

Đây là SIMD trong một luồng xử lý: một phép toán tác động đến nhiều lane dữ liệu. Không cần tạo thêm thread để sử dụng các kernel trong bài. Khả năng tăng tốc phụ thuộc phần cứng, JVM và phép toán cụ thể; xem [mô hình thực thi trong tài liệu Vector API hiện đại](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html).

## 2. Đề bài và hợp đồng đầu vào

### 2.1. Bài A — Tích vô hướng

Với hai mảng cùng độ dài `n`, tính:

```text
dot(a, b) = a[0] * b[0] + a[1] * b[1] + ... + a[n-1] * b[n-1]
```

Ví dụ:

```text
a = [1, 2, 3]
b = [4, 5, 6]

dot(a, b) = 32
```

Viết hai hàm `dotScalar` và `dotVector` có cùng hợp đồng:

| Điều kiện | Yêu cầu |
|---|---|
| Một trong hai mảng là `null` | Ném `NullPointerException` |
| Hai mảng khác độ dài | Ném `IllegalArgumentException` |
| Hai mảng rỗng | Trả về `0.0f` |
| Dữ liệu dùng trong kiểm tra số học | Hữu hạn, có độ lớn được kiểm soát để tránh tràn |
| Độ chính xác | Được kiểm tra bằng sai số đã công bố, không đòi giống từng bit |

Không quét kiểm tra tính hữu hạn của mọi phần tử bên trong kernel. Bộ dữ liệu của bài phải đáp ứng tiền điều kiện này; nếu ứng dụng thực tế nhận dữ liệu bất kỳ thì cần thiết kế chính sách cho `NaN`, vô cực và tràn số riêng.

### 2.2. Bài B — Lọc dữ liệu và nén kết quả

Cho mảng `input`, ngưỡng `threshold` và bộ đệm `output`. Giữ mọi phần tử thỏa `input[i] > threshold` theo đúng thứ tự ban đầu.

```text
input     = [3, -1, 0, 5, 2]
threshold = 1

output[0..count) = [3, 5, 2]
count           = 3
```

Hai hàm `filterScalar` và `filterVector` phải:

- Trả về số phần tử đã ghi, gọi là `count`.
- Chỉ coi `output[0..count)` là kết quả hợp lệ.
- Không thay đổi phần còn lại `output[count..output.length)`.
- Không cấp phát mảng kết quả bên trong kernel.
- Yêu cầu `output.length >= input.length` và `input != output`.

Yêu cầu sức chứa bằng độ dài đầu vào là lựa chọn đơn giản của bài tập. Nó bảo đảm đủ chỗ ngay cả khi mọi phần tử đều đạt điều kiện. Hai mảng trùng nhau bị từ chối để giữ hợp đồng rõ ràng; bài này không triển khai lọc tại chỗ.

Điều kiện `>` giữ nguyên ngữ nghĩa của Java: giá trị bằng ngưỡng bị loại; `NaN > threshold` là `false`; ngưỡng `NaN` làm mọi so sánh đều `false`. Với ngưỡng `0.0f`, cả `+0.0f` và `-0.0f` đều bị loại. Phép so sánh `GT` của Vector API biểu diễn cùng điều kiện; xem [VectorOperators của Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorOperators.html).

### 2.3. Bài C — Đo hiệu năng

Thiết kế benchmark để trả lời ba câu hỏi:

1. Từ kích thước nào phiên bản vector bắt đầu có lợi trên máy đang dùng?
2. Lọc dữ liệu thay đổi thế nào khi giữ lại 0%, 50% hoặc 100% số phần tử?
3. Khi tăng kích thước mảng, tốc độ còn tăng nhờ SIMD hay đã bị giới hạn bởi việc truy cập bộ nhớ?

Không đặt mục tiêu bắt buộc SIMD phải nhanh hơn. Một kết quả chậm hơn nhưng được đo đúng và giải thích hợp lý vẫn hoàn thành bài tập.

## 3. Phác thảo thuật toán trước khi viết mã

### 3.1. Độ rộng vector và phần đuôi

Gọi `L` là số lane của `FloatVector.SPECIES_PREFERRED`. Mỗi vòng vector xử lý `L` số `float`.

```text
n = 2 * L + 3

[ L phần tử ][ L phần tử ][ 3 phần tử ]
      SIMD         SIMD       vô hướng
```

Sử dụng `SPECIES.loopBound(n)` để tìm ranh giới phần có thể đọc đủ một vector. Khi vòng vector kết thúc, xử lý các chỉ số còn lại bằng vòng lặp vô hướng. Không giả định mọi máy đều có cùng `L`, và không tự thay `loopBound` bằng mẹo bit đòi hỏi số lane là lũy thừa của hai. Xem [VectorSpecies.loopBound và indexInRange](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html#loopBound(int)).

### 3.2. Tích lũy theo lane rồi giảm một lần

Phiên bản tích vô hướng thực hiện ba bước:

1. Nạp hai khối dữ liệu.
2. Nhân theo lane và cộng vào bộ tích lũy vector.
3. Sau vòng lặp, giảm các lane thành một số rồi cộng phần đuôi.

Với `L = 4` chỉ để minh họa:

```text
acc[0] nhận các tích ở chỉ số 0, 4, 8, ...
acc[1] nhận các tích ở chỉ số 1, 5, 9, ...
acc[2] nhận các tích ở chỉ số 2, 6, 10, ...
acc[3] nhận các tích ở chỉ số 3, 7, 11, ...

result = tổng các lane của acc + tổng phần đuôi
```

Không lấy từng lane ra rồi cộng bằng Java ở mỗi vòng. Trong bài này, giữ dữ liệu trong vector đến cuối vòng lặp để tránh liên tục chuyển từ xử lý theo vector sang xử lý từng phần tử.

### 3.3. So sánh, nén rồi ghi tiền tố

Với phép lọc, một mask xác định lane nào đạt điều kiện:

```text
Dữ liệu:              [3, -1, 5, 0]
Điều kiện x > 1:      [T,  F, T, F]
Sau compress:         [3,  5, 0, 0]
Số phần tử hợp lệ:     2
Mask dùng để ghi:      [T,  T, F, F]
```

`compress` chuyển các phần tử được chọn về đầu vector theo thứ tự lane. Các lane còn lại được điền zero; chúng không phải kết quả lọc. Vì vị trí dữ liệu đã thay đổi sau khi nén, mask dùng để ghi phải chọn **`count` lane đầu**, thay vì dùng lại mask so sánh ban đầu. Xem [FloatVector.compress](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html#compress(jdk.incubator.vector.VectorMask)).

`selected.trueCount()` cho biết số lane được giữ lại. Đây là số phần tử cần tăng cho con trỏ đầu ra, không phải `L`. Xem [VectorMask.trueCount](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorMask.html#trueCount()).

## 4. Lời giải tham khảo cho hai kernel

Lưu lớp sau thành `src/main/java/lab/VectorKernels.java` trong dự án thực hành. Các đường dẫn ở phần mã là vị trí gợi ý trong dự án bạn tạo khi học bài.

```java
package lab;

import java.util.Objects;
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorOperators;
import jdk.incubator.vector.VectorSpecies;

public final class VectorKernels {
    public static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    private VectorKernels() {
    }

    private static void checkDot(float[] a, float[] b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        if (a.length != b.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }
    }

    private static void checkFilter(float[] input, float[] output) {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(output, "output");
        if (input == output) {
            throw new IllegalArgumentException("Distinct arrays required");
        }
        if (output.length < input.length) {
            throw new IllegalArgumentException("Output buffer too small");
        }
    }

    public static float dotScalar(float[] a, float[] b) {
        checkDot(a, b);
        float sum = 0.0f;
        for (int i = 0; i < a.length; i++) {
            sum += a[i] * b[i];
        }
        return sum;
    }

    public static float dotVector(float[] a, float[] b) {
        checkDot(a, b);
        int bound = SPECIES.loopBound(a.length);
        int i = 0;
        FloatVector acc = FloatVector.zero(SPECIES);

        for (; i < bound; i += SPECIES.length()) {
            FloatVector va = FloatVector.fromArray(SPECIES, a, i);
            FloatVector vb = FloatVector.fromArray(SPECIES, b, i);
            acc = acc.add(va.mul(vb));
        }

        float sum = acc.reduceLanes(VectorOperators.ADD);
        for (; i < a.length; i++) {
            sum += a[i] * b[i];
        }
        return sum;
    }

    public static int filterScalar(
            float[] input, float threshold, float[] output) {
        checkFilter(input, output);
        int written = 0;

        for (int i = 0; i < input.length; i++) {
            float value = input[i];
            if (value > threshold) {
                output[written++] = value;
            }
        }
        return written;
    }

    public static int filterVector(
            float[] input, float threshold, float[] output) {
        checkFilter(input, output);
        int bound = SPECIES.loopBound(input.length);
        int i = 0;
        int written = 0;

        for (; i < bound; i += SPECIES.length()) {
            FloatVector values =
                    FloatVector.fromArray(SPECIES, input, i);
            VectorMask<Float> selected =
                    values.compare(VectorOperators.GT, threshold);
            int count = selected.trueCount();

            if (count != 0) {
                FloatVector packed = values.compress(selected);
                VectorMask<Float> prefix =
                        SPECIES.indexInRange(0, count);
                packed.intoArray(output, written, prefix);
                written += count;
            }
        }

        for (; i < input.length; i++) {
            float value = input[i];
            if (value > threshold) {
                output[written++] = value;
            }
        }
        return written;
    }
}
```

Các hàm kiểm tra đầu vào nằm ngoài vòng lặp dữ liệu và có mặt ở cả hai phiên bản. Không có bước copy toàn bộ mảng, tạo stream hay cấp phát kết quả chen vào một phía của phép so sánh.

### 4.1. Vì sao phép lọc không ghi tràn?

Trước mỗi khối, `written` bằng số phần tử đã giữ từ phần đầu vào đã duyệt, nên `written <= i`.

Trong một khối đầy đủ:

```text
0 <= count <= L
written + count <= i + L <= input.length <= output.length
```

Chỉ `count` lane đầu được ghi, do đó mọi vị trí thực sự được truy cập đều nằm trong bộ đệm. `intoArray` có mask chỉ ghi và kiểm tra giới hạn ở lane được bật; lane tắt giữ nguyên phần tử đích. Điều này cũng bảo toàn phần hậu tố của `output`. Xem [quy tắc masked store của FloatVector](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html#intoArray(float%5B%5D,int,jdk.incubator.vector.VectorMask)).

Tính ổn định về thứ tự đến từ hai yếu tố: `compress` giữ thứ tự trong từng khối, còn các khối được nối vào đầu ra theo thứ tự duyệt.

### 4.2. Vì sao tích vô hướng có thể khác kết quả scalar?

Phiên bản scalar cộng các tích theo thứ tự từ trái sang phải. Phiên bản vector cộng riêng từng lane rồi mới gộp lại. Số thực dấu phẩy động có làm tròn, nên thay cách nhóm phép cộng có thể thay kết quả.

Ví dụ toán học:

```text
16_777_216 + 1 - 16_777_216 = 1
```

Nhưng nếu cộng lần lượt bằng `float`, số `1` có thể bị mất ở phép cộng đầu tiên. Vì vậy, scalar không tự động là đáp án chính xác tuyệt đối.

Thứ tự giảm của `ADD` trên số thực không được API cố định để JVM có thể chọn cách thực thi phù hợp. Không dùng phép so sánh `dotScalar(a, b) == dotVector(a, b)` như tiêu chuẩn chung. Xem [quy tắc phép toán số thực của Vector API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorOperators.html).

Lời giải dùng `mul` rồi `add`. Nếu thử thay bằng `fma`, bạn đang thay cả cách làm tròn vì phép nhân cộng hợp nhất chỉ làm tròn một lần. Hãy coi đó là biến thể riêng, có đối chứng và tiêu chí sai số riêng; không âm thầm đổi một phía của benchmark.

## 5. Kiểm tra tính đúng trước khi đo

### 5.1. Ma trận trường hợp bắt buộc

Với `L = SPECIES.length()`, kiểm tra các độ dài:

```text
0, 1, L - 1, L, L + 1, 2 * L + 3, 16_387
```

Nếu `L = 1` thì `L - 1` chính là trường hợp rỗng. Bộ trường hợp này phải được tính từ species đang chạy, thay vì giả định máy có tám hay mười sáu lane.

| Nhóm | Trường hợp cần bao phủ |
|---|---|
| Tích vô hướng | Ví dụ có đáp án 32; mảng rỗng; dữ liệu hữu hạn sinh từ seed cố định |
| Độ dài | Nhỏ hơn một vector, đúng một vector, có nhiều khối và có phần đuôi |
| Lọc | Không giữ phần tử nào, giữ một phần, giữ tất cả |
| Ranh giới | Giá trị bằng ngưỡng, `+0.0f`, `-0.0f` |
| Giá trị đặc biệt của phép lọc | `NaN`, vô cực dương, vô cực âm, ngưỡng `NaN` |
| Bộ đệm | Kiểm tra tiền tố đúng và hậu tố giữ nguyên sentinel |
| Hợp đồng | `null`, độ dài dot khác nhau, output quá nhỏ, input và output trùng nhau |

### 5.2. Chương trình kiểm tra có thể chạy độc lập

Lưu thành `src/main/java/lab/VectorSelfTest.java`. Chương trình này không dùng JMH và không đo thời gian.

```java
package lab;

import java.util.Arrays;
import java.util.Random;

public final class VectorSelfTest {
    private static final float SENTINEL = -9999.0f;

    public static void main(String[] args) {
        float[] a = {1.0f, 2.0f, 3.0f};
        float[] b = {4.0f, 5.0f, 6.0f};
        if (VectorKernels.dotScalar(a, b) != 32.0f
                || VectorKernels.dotVector(a, b) != 32.0f) {
            throw new AssertionError("Known dot example failed");
        }

        float[] example = {3.0f, -1.0f, 0.0f, 5.0f, 2.0f};
        float[] output = new float[example.length];
        int count = VectorKernels.filterVector(example, 1.0f, output);
        if (count != 3 || output[0] != 3.0f
                || output[1] != 5.0f || output[2] != 2.0f) {
            throw new AssertionError("Known filter example failed");
        }

        int lanes = VectorKernels.SPECIES.length();
        int[] sizes = {0, 1, lanes - 1, lanes,
                lanes + 1, 2 * lanes + 3, 16_387};
        Random random = new Random(20261125L);

        for (int size : sizes) {
            float[] x = new float[size];
            float[] y = new float[size];
            for (int i = 0; i < size; i++) {
                x[i] = random.nextFloat() * 2.0f - 1.0f;
                y[i] = random.nextFloat() * 2.0f - 1.0f;
            }

            checkDot(x, y);
            checkFilter(x, -2.0f);
            checkFilter(x, 0.0f);
            checkFilter(x, 2.0f);
            checkFilter(x, Float.NaN);
        }

        float[] specialValues = {
                Float.NaN, Float.NEGATIVE_INFINITY, -2.0f,
                -0.0f, 0.0f, 2.0f, Float.POSITIVE_INFINITY
        };
        float[] specialInput = new float[2 * lanes + 3];
        for (int i = 0; i < specialInput.length; i++) {
            specialInput[i] = specialValues[i % specialValues.length];
        }
        checkFilter(specialInput, -1.0f);
        checkFilter(specialInput, 0.0f);
        checkFilter(specialInput, Float.NaN);

        expect(NullPointerException.class,
                () -> VectorKernels.dotScalar(null, new float[0]));
        expect(NullPointerException.class,
                () -> VectorKernels.dotVector(new float[0], null));
        expect(IllegalArgumentException.class,
                () -> VectorKernels.dotScalar(new float[1], new float[2]));
        expect(IllegalArgumentException.class,
                () -> VectorKernels.dotVector(new float[1], new float[2]));
        expect(NullPointerException.class,
                () -> VectorKernels.filterScalar(null, 0.0f, new float[0]));
        expect(NullPointerException.class,
                () -> VectorKernels.filterVector(new float[0], 0.0f, null));
        expect(IllegalArgumentException.class,
                () -> VectorKernels.filterScalar(
                        new float[2], 0.0f, new float[1]));
        expect(IllegalArgumentException.class,
                () -> VectorKernels.filterVector(
                        new float[2], 0.0f, new float[1]));

        float[] same = new float[4];
        expect(IllegalArgumentException.class,
                () -> VectorKernels.filterScalar(same, 0.0f, same));
        expect(IllegalArgumentException.class,
                () -> VectorKernels.filterVector(same, 0.0f, same));

        System.out.println("PASS; species = " + VectorKernels.SPECIES);
    }

    private static void checkDot(float[] x, float[] y) {
        double reference = 0.0;
        double scale = 0.0;
        for (int i = 0; i < x.length; i++) {
            double product = (double) x[i] * (double) y[i];
            reference += product;
            scale += Math.abs(product);
        }

        double tolerance = 1.0e-6 + 1.0e-4 * scale;
        checkNear(reference, VectorKernels.dotScalar(x, y), tolerance);
        checkNear(reference, VectorKernels.dotVector(x, y), tolerance);
    }

    private static void checkNear(
            double reference, float actual, double tolerance) {
        if (!Float.isFinite(actual)
                || Math.abs(reference - actual) > tolerance) {
            throw new AssertionError(
                    "reference=" + reference + ", actual=" + actual
                            + ", tolerance=" + tolerance);
        }
    }

    private static void checkFilter(float[] input, float threshold) {
        float[] scalar = new float[input.length + 3];
        float[] vector = new float[input.length + 3];
        Arrays.fill(scalar, SENTINEL);
        Arrays.fill(vector, SENTINEL);

        int expected = VectorKernels.filterScalar(input, threshold, scalar);
        int actual = VectorKernels.filterVector(input, threshold, vector);
        if (expected != actual) {
            throw new AssertionError("Filter counts differ");
        }
        for (int i = 0; i < expected; i++) {
            if (Float.floatToRawIntBits(scalar[i])
                    != Float.floatToRawIntBits(vector[i])) {
                throw new AssertionError("Filter value differs at " + i);
            }
        }
        for (int i = expected; i < vector.length; i++) {
            if (scalar[i] != SENTINEL || vector[i] != SENTINEL) {
                throw new AssertionError("Output suffix was modified");
            }
        }
    }

    private static void expect(
            Class<? extends Throwable> type, Runnable operation) {
        try {
            operation.run();
        } catch (Throwable failure) {
            if (type.isInstance(failure)) {
                return;
            }
            throw new AssertionError("Unexpected exception", failure);
        }
        throw new AssertionError("Missing exception: " + type.getName());
    }
}
```

Tham chiếu `double` ở đây giảm ảnh hưởng làm tròn so với tính toàn bộ bằng `float`; nó vẫn là phép tính dấu phẩy động, không phải số học chính xác tùy ý.

Ngưỡng sai số `1e-6 + 1e-4 * sum(abs(a[i] * b[i]))` là chính sách minh họa cho bộ dữ liệu hữu hạn, có giới hạn kích thước của bài. Nó tránh chỉ chia sai số cho một tổng có thể gần zero do triệt tiêu. Đây không phải bảo đảm sai số áp dụng cho mọi độ dài hay mọi miền dữ liệu. Với ứng dụng có yêu cầu chặt hơn, cần xây dựng giới hạn sai số và bộ tham chiếu phù hợp.

Phép lọc chỉ chọn và di chuyển dữ liệu nên có thể so sánh các phần tử đầu ra theo bit. Kiểm tra cả số lượng lẫn thứ tự: chỉ so sánh tổng các phần tử sẽ bỏ sót lỗi đảo vị trí hoặc mất phần tử.

### 5.3. Biên dịch và chạy với module incubator

Từ thư mục gốc của dự án thực hành:

```powershell
javac --add-modules jdk.incubator.vector -encoding UTF-8 -d out src/main/java/lab/VectorKernels.java src/main/java/lab/VectorSelfTest.java
java --add-modules jdk.incubator.vector -cp out lab.VectorSelfTest
```

`--add-modules jdk.incubator.vector` dùng khi biên dịch và khi chạy. Bài này không dùng tính năng ngôn ngữ preview nên không cần `--enable-preview`. Module cần nạp được mô tả tại [jdk.incubator.vector của JDK 22](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/module-summary.html).

Dùng `java -version` và `javac -version` để bảo đảm bạn đang biên dịch và chạy bằng cùng bản JDK dự định thử nghiệm. Không dùng kết quả kiểm tra tính đúng để suy ra rằng chương trình đã được tăng tốc.

## 6. Tạo benchmark JMH

### 6.1. Chuẩn bị dự án

JMH cần mã benchmark được sinh bởi annotation processor. Cách bắt đầu trong bài là tạo dự án từ archetype chính thức, sau đó thêm các lớp ở trên. Xem [hướng dẫn sử dụng JMH](https://github.com/openjdk/jmh#usage).

Chạy từ một thư mục thực hành chưa có dự án Maven:

```powershell
mvn archetype:generate "-DinteractiveMode=false" "-DarchetypeGroupId=org.openjdk.jmh" "-DarchetypeArtifactId=jmh-java-benchmark-archetype" "-DgroupId=lab" "-DartifactId=vector-lab" "-Dversion=1.0"
Set-Location vector-lab
```

Lệnh chọn phiên bản archetype theo cơ chế của Maven. Khi ghi báo cáo, lưu phiên bản JMH thực tế từ `pom.xml` và giữ file này cùng mã benchmark để người khác có thể dựng lại cùng cấu hình.

Thêm `VectorKernels.java` và `VectorSelfTest.java` vào `src/main/java/lab/`. Trong `maven-compiler-plugin` của `pom.xml` được sinh, thay phần `configuration` bằng cấu hình sau khi dùng JDK 27:

```xml
<configuration>
    <source>27</source>
    <target>27</target>
    <encoding>UTF-8</encoding>
    <compilerArgs>
        <arg>--add-modules</arg>
        <arg>jdk.incubator.vector</arg>
    </compilerArgs>
    <annotationProcessors>
        <annotationProcessor>
            org.openjdk.jmh.generators.BenchmarkProcessor
        </annotationProcessor>
    </annotationProcessors>
</configuration>
```

Nếu thực hành trên JDK 22, đổi cả `source` và `target` thành `22`; với JDK khác, dùng đúng phiên bản đang thử. Giữ các dependency JMH và cấu hình đóng gói executable JAR của archetype. Khai báo processor tường minh giúp việc sinh benchmark không phụ thuộc cơ chế tự dò processor của JDK. Xem [cấu trúc dự án mẫu chính thức](https://github.com/openjdk/jmh/blob/master/jmh-archetypes/jmh-java-benchmark-archetype/src/main/resources/archetype-resources/pom.xml).

### 6.2. Mã benchmark

Lưu thành `src/main/java/lab/VectorBenchmark.java`:

```java
package lab;

import java.util.Random;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;
import org.openjdk.jmh.infra.Blackhole;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(value = 2,
        jvmArgsAppend = {"--add-modules=jdk.incubator.vector"})
@Threads(1)
public class VectorBenchmark {

    @State(Scope.Thread)
    public static class DotState {
        @Param({"31", "1024", "1048579"})
        public int size;

        public float[] a;
        public float[] b;

        @Setup(Level.Trial)
        public void setup() {
            Random random = new Random(42L);
            a = new float[size];
            b = new float[size];
            for (int i = 0; i < size; i++) {
                a[i] = random.nextFloat();
                b[i] = random.nextFloat();
            }
        }
    }

    @State(Scope.Thread)
    public static class FilterState {
        @Param({"31", "1024", "1048579"})
        public int size;

        @Param({"0", "50", "100"})
        public int selectedPercent;

        public float[] input;
        public float[] scalarOutput;
        public float[] vectorOutput;
        public float threshold = 0.0f;

        @Setup(Level.Trial)
        public void setup() {
            Random random = new Random(43L);
            input = new float[size];
            scalarOutput = new float[size];
            vectorOutput = new float[size];
            int kept = (int) ((long) size * selectedPercent / 100);

            for (int i = 0; i < size; i++) {
                input[i] = i < kept
                        ? 1.0f + random.nextFloat()
                        : -1.0f - random.nextFloat();
            }
            for (int i = input.length - 1; i > 0; i--) {
                int other = random.nextInt(i + 1);
                float temporary = input[i];
                input[i] = input[other];
                input[other] = temporary;
            }
        }
    }

    @Benchmark
    public float dotScalar(DotState data) {
        return VectorKernels.dotScalar(data.a, data.b);
    }

    @Benchmark
    public float dotVector(DotState data) {
        return VectorKernels.dotVector(data.a, data.b);
    }

    @Benchmark
    public int filterScalar(FilterState data, Blackhole blackhole) {
        int count = VectorKernels.filterScalar(
                data.input, data.threshold, data.scalarOutput);
        blackhole.consume(data.scalarOutput);
        return count;
    }

    @Benchmark
    public int filterVector(FilterState data, Blackhole blackhole) {
        int count = VectorKernels.filterVector(
                data.input, data.threshold, data.vectorOutput);
        blackhole.consume(data.vectorOutput);
        return count;
    }
}
```

Các kích thước benchmark là điểm bắt đầu cho khảo sát. Trong báo cáo, ghi thêm `size % L` vì một độ dài cụ thể có phần đuôi hay không phụ thuộc species. Ma trận kiểm tra tính đúng ở phần trước đã bao phủ các trường hợp quanh `L` một cách độc lập.

Với kích thước lẻ, nhãn `50` tạo `floor(size / 2)` phần tử đạt điều kiện, nên tỷ lệ thực tế xấp xỉ 50%. Hai nhãn `0` và `100` là chính xác.

### 6.3. Những chi tiết giúp phép so sánh có ý nghĩa

Dữ liệu và bộ đệm được tạo trong `@Setup(Level.Trial)`. Mỗi lần benchmark chỉ gọi một kernel trên toàn mảng. Không đưa sinh số ngẫu nhiên, in console, xác minh kết quả hay copy mảng vào vùng đo.

Các hàm dot trả về kết quả. Các hàm lọc trả về số lượng và chuyển tham chiếu bộ đệm đã ghi cho `Blackhole`. Cách này giữ kết quả quan sát được đối với harness, giảm nguy cơ JIT loại bỏ phần tính toán không có người dùng. Nó không thay cho việc kiểm tra nội dung đầu ra trước khi đo. Xem [mẫu JMH về dead-code elimination](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java).

Warmup cho JVM thời gian thu thập profile và biên dịch mã nóng. Hai fork tạo hai tiến trình JVM riêng, giúp hạn chế ảnh hưởng profile giữa các lần chạy. Số vòng trong ví dụ là cấu hình khởi đầu, không phải chứng nhận rằng mọi benchmark đã đạt trạng thái ổn định. Xem [mẫu JMH về fork](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_12_Forking.java).

`@Fork(... jvmArgsAppend = ...)` truyền cờ module cho JVM con. Cần chú ý cả JVM chạy harness lẫn JVM được JMH fork; xem [khai báo Fork của JMH](https://github.com/openjdk/jmh/blob/master/jmh-core/src/main/java/org/openjdk/jmh/annotations/Fork.java).

### 6.4. Chạy kiểm tra rồi mới chạy benchmark

```powershell
mvn clean verify
java --add-modules jdk.incubator.vector -cp target/classes lab.VectorSelfTest
java --add-modules jdk.incubator.vector -jar target/benchmarks.jar "lab.VectorBenchmark.dot.*" -prof gc -rf json -rff dot-results.json
java --add-modules jdk.incubator.vector -jar target/benchmarks.jar "lab.VectorBenchmark.filter.*" -prof gc -rf json -rff filter-results.json
```

Lệnh thứ hai chạy chương trình kiểm tra thủ công của bài; riêng `mvn verify` không tự biến lớp `VectorSelfTest` thành một bài kiểm thử tự động.

Muốn khảo sát thêm điểm chuyển tiếp của dot:

```powershell
java --add-modules jdk.incubator.vector -jar target/benchmarks.jar "lab.VectorBenchmark.dot.*" -p size=16,32,64,128,256,512,1024,4096
```

Toàn bộ ma trận với warmup và nhiều fork có thể mất vài phút. Nếu rút ngắn để kiểm tra cấu hình có chạy được hay không, không dùng số liệu chạy nhanh đó làm kết luận hiệu năng cuối cùng.

## 7. Đọc và giải thích kết quả

### 7.1. Một operation là xử lý cả mảng

Benchmark dùng `AverageTime` và đơn vị `ns/op`. Ở đây, một operation xử lý **toàn bộ mảng**, không phải một phần tử hay một lane.

Tính mức tăng tốc theo:

```text
speedup = thời gian scalar / thời gian vector
```

- `speedup > 1`: vector nhanh hơn ở trường hợp đo đó.
- `speedup < 1`: scalar nhanh hơn ở trường hợp đo đó.
- Khi chênh lệch nhỏ so với độ dao động, chưa có đủ cơ sở để kết luận lợi ích rõ ràng.

Lập bảng từ dữ liệu JMH thực tế:

| Kernel | n | Tỷ lệ giữ | n % L | Scalar ns/op | Vector ns/op | Speedup |
|---|---:|---:|---:|---:|---:|---:|
| Dot | 31 | Không áp dụng | Điền | Điền | Điền | Tính |
| Dot | 1024 | Không áp dụng | Điền | Điền | Điền | Tính |
| Dot | 1048579 | Không áp dụng | Điền | Điền | Điền | Tính |
| Filter | 1048579 | 0% | Điền | Điền | Điền | Tính |
| Filter | 1048579 | Xấp xỉ 50% | Điền | Điền | Điền | Tính |
| Filter | 1048579 | 100% | Điền | Điền | Điền | Tính |

Không điền các hệ số tăng tốc dự đoán vào bảng như số đo. Bài này không cung cấp số benchmark đã chạy sẵn.

### 7.2. Các giả thuyết cần kiểm chứng

**Mảng nhỏ:** chi phí gọi hàm, kiểm tra đầu vào, giảm lane và xử lý đuôi có thể chiếm phần lớn thời gian. `L` lane không kéo theo tốc độ nhanh hơn `L` lần.

**Tích vô hướng:** phiên bản vector phá một chuỗi cộng tuần tự thành nhiều chuỗi theo lane. Tuy nhiên, một bộ tích lũy vector vẫn có phụ thuộc giữa các lần cộng. Nhiều bộ tích lũy độc lập là một hướng thử tiếp, đồng thời thay đổi thứ tự làm tròn.

**Lọc 0% hoặc 100%:** nhánh scalar có thể dễ dự đoán. Trường hợp không giữ phần tử nào còn tránh toàn bộ ghi dữ liệu đầu ra trong cả hai kernel.

**Lọc xấp xỉ 50%:** dữ liệu được xáo trộn làm kết quả điều kiện xen kẽ khó đoán hơn. Phiên bản vector có thể hưởng lợi từ so sánh theo lane, nhưng vẫn phải trả chi phí đếm mask, nén và ghi tiền tố.

**Mảng lớn:** lượng dữ liệu phải đọc và ghi có thể trở thành giới hạn. Ước lượng khối lượng dữ liệu hữu ích cho một lần gọi:

```text
Dot:     8 * n byte                    // đọc hai mảng float
Filter:  4 * n + 4 * count byte        // đọc input, ghi các phần tử giữ lại
```

Đây là ước lượng dữ liệu của thuật toán, chưa gồm mọi lưu lượng cache, write allocation hay chi phí quản lý của hệ thống. Không dùng nó như số đọc trực tiếp từ bộ điều khiển bộ nhớ.

Các ý trên là giả thuyết phân tích, không phải kết quả đã xác nhận cho máy của bạn.

### 7.3. Scalar trong mã nguồn có thể được JIT tối ưu

Tên `dotScalar` và `filterScalar` mô tả cách viết trong Java. Nó không bảo đảm mã máy không có lệnh vector: JIT có thể tối ưu hoặc tự vector hóa những mẫu phù hợp.

So sánh chính nên giữ nguyên cấu hình JVM thông thường để trả lời câu hỏi thực tế: cách viết tường minh bằng Vector API có tốt hơn vòng lặp thông thường trên môi trường này hay không? Không cố làm chậm scalar để tạo hệ số tăng tốc đẹp hơn.

Nếu cần giải thích sâu hơn, quan sát mã máy bằng công cụ profiler phù hợp với hệ điều hành và bản JDK. Số `ns/op` tự nó không chứng minh CPU đã dùng một tập lệnh cụ thể.

### 7.4. Cache, cấp phát và độ nhiễu

Benchmark tái sử dụng cùng dữ liệu qua nhiều lần gọi. Khi tập dữ liệu đủ nhỏ, nhiều truy cập có thể được phục vụ từ cache. Kết luận phải mô tả đây là phép đo kernel trên bộ đệm tái sử dụng; nếu ứng dụng luôn nhận dữ liệu mới, cần thêm phép đo tương ứng.

Hai kernel lọc không cấp phát mảng trong vùng đo. Nếu mục tiêu thực tế là trả về một mảng mới có độ dài chính xác, hãy tạo benchmark riêng trong đó **cả hai** cách đều chịu cùng chi phí cấp phát và cắt mảng. Ghi lại số liệu allocation từ `-prof gc`, tránh đoán rằng mọi biểu thức vector chắc chắn không cấp phát trên mọi JVM.

Khi đọc `Score` và `Error`, xem cả độ dao động giữa các lần đo và các fork. Hai khoảng lỗi chồng nhau hoặc chênh lệch rất nhỏ cần được khảo sát thêm; không diễn giải một lần chạy ngắn thành bằng chứng thống kê chắc chắn.

Báo cáo nên lưu:

- CPU, hệ điều hành, phiên bản đầy đủ của JDK và nhà cung cấp JVM.
- Phiên bản JMH, cờ JVM, số thread, warmup, measurement và fork.
- `SPECIES`, số lane `L`, kích thước mảng, tỷ lệ giữ thực tế và kiểu phân bố dữ liệu.
- Thời gian, độ dao động, speedup, allocation và các file JSON kết quả.
- Điều kiện chạy ảnh hưởng rõ rệt như chế độ nguồn, tải nền hoặc giới hạn tài nguyên.

## 8. Các lỗi thường gặp khi làm bài

| Biểu hiện hoặc cách viết | Nguyên nhân cần kiểm tra |
|---|---|
| Sai khi độ dài là `L + 1` | Bỏ quên phần đuôi |
| Lọc ra nhiều zero thừa | Ghi tất cả lane sau `compress` thay vì chỉ ghi tiền tố hợp lệ |
| Mất phần tử hoặc có lỗ trong output | Dùng mask so sánh cũ để ghi vector đã nén |
| Sai vị trí bắt đầu khối đầu ra kế tiếp | Tăng `written` theo `L` thay vì theo số lane được chọn |
| Dot khác vài bit nhưng sai số nhỏ | Thay đổi thứ tự cộng và làm tròn |
| Kết quả cực nhanh bất thường | Kết quả không được sử dụng, dữ liệu quá đơn giản hoặc benchmark cấu hình sai |
| Chỉ một phía chịu chi phí tạo mảng | Hai benchmark đang thực hiện khối lượng công việc khác nhau |
| JVM con không nạp được Vector API | Cờ module chưa được truyền vào fork |
| Chỉ so sánh số phần tử lọc | Chưa phát hiện được lỗi thứ tự hoặc nội dung |
| Nói SIMD luôn nhanh hơn | Chưa xét kích thước, chi phí nén, cache và mã JIT thực tế |

## 9. Bài tập mở rộng

Chỉ thực hiện sau khi lời giải cơ bản đã đúng và có số đo.

### 9.1. Dùng mask cho phần đuôi của bộ lọc

Thay phần đuôi vô hướng bằng một lần nạp có mask. Các bước quan trọng:

```java
// Đặt sau vòng xử lý các khối đầy đủ, tại vị trí i.
if (i < input.length) {
    VectorMask<Float> valid =
            SPECIES.indexInRange(i, input.length);
    FloatVector values =
            FloatVector.fromArray(SPECIES, input, i, valid);
    VectorMask<Float> selected =
            values.compare(VectorOperators.GT, threshold).and(valid);
    int count = selected.trueCount();

    if (count != 0) {
        values.compress(selected).intoArray(
                output, written, SPECIES.indexInRange(0, count));
        written += count;
    }
}
```

Đoạn trên thay thế vòng đuôi trong `filterVector` và dùng các biến cục bộ đã có. Đừng chạy cả hai đoạn xử lý đuôi.

Phép `and(valid)` là bắt buộc về mặt logic. Các lane không được nạp mang giá trị zero; nếu ngưỡng âm, zero có thể đạt điều kiện so sánh dù không tương ứng phần tử thật. Thêm trường hợp `n = L + 1` với ngưỡng âm để phát hiện lỗi này.

### 9.2. Dùng nhiều bộ tích lũy cho dot

Thử hai hoặc bốn bộ tích lũy vector độc lập. Xác định ranh giới vòng lặp mới theo số vector mỗi lần duyệt, rồi xử lý những khối còn lại và phần đuôi.

Đánh giá cả thời gian và sai số. Việc thay đổi nhóm phép cộng có thể làm thay đổi kết quả, nên không bỏ qua kiểm tra số học chỉ vì phiên bản trước đã qua kiểm tra.

### 9.3. Thay đổi phân bố của bộ lọc

Giữ nguyên tỷ lệ phần tử đạt điều kiện, nhưng thử:

- Xáo trộn ngẫu nhiên như benchmark tham khảo.
- Gom mọi phần tử đạt điều kiện thành một vùng liên tiếp.
- Xen kẽ đều một phần tử đạt và một phần tử không đạt.

Nếu thời gian thay đổi dù tỷ lệ giữ giống nhau, hãy phân tích ảnh hưởng của vị trí dữ liệu và dự đoán nhánh, thay vì chỉ nhìn lượng ghi đầu ra.

### 9.4. Phân biệt lọc và đếm

Viết thêm hàm chỉ đếm số phần tử thỏa điều kiện bằng `trueCount`, không tạo đầu ra. So sánh hàm đếm scalar với hàm đếm vector để khảo sát riêng chi phí xác định điều kiện.

Không đưa hàm chỉ đếm vào bảng như một lời giải nhanh hơn cho yêu cầu lọc: hai hàm phải hoàn thành cùng một công việc mới tạo thành phép so sánh hợp lệ.

## 10. Sản phẩm cần nộp

Nộp mã hai phiên bản dot, hai phiên bản lọc, chương trình kiểm tra, benchmark JMH và kết quả đo của máy đang dùng. Phần nhận xét cần chỉ ra:

1. Cách xử lý phần đuôi và lý do đầu ra lọc giữ đúng thứ tự.
2. Chính sách sai số của dot và các trường hợp kiểm tra ranh giới.
3. Ít nhất một trường hợp vector có lợi hoặc không có lợi, dựa trên số liệu thực.
4. Phạm vi kết luận: JDK, CPU, kích thước, tỷ lệ giữ và điều kiện tái sử dụng dữ liệu.

Một bài hoàn chỉnh phải chứng minh được thuật toán đúng theo hợp đồng và phép đo so sánh cùng công việc. Hệ số tăng tốc là kết quả cần tìm hiểu, không phải một con số được ấn định trước.

