# Nạp, tính toán và ghi dữ liệu bằng các kiểu vector số nguyên hoặc số thực

## 1. Mục tiêu và phiên bản sử dụng

Một phép xử lý mảng thường có ba bước: đọc dữ liệu, tính toán, rồi ghi kết quả. Vector API giữ cấu trúc đó nhưng mỗi lần làm việc với một nhóm phần tử được gọi là các **lane**.

Trong chương **Vector API** của module Java 22, bài này tập trung vào mẫu thao tác tiếp tục hữu ích trong Java hiện đại: **load → compute → store**, chọn đúng kiểu số và xử lý phần cuối mảng an toàn.

Các ví dụ dùng **JDK 27**. Ở phiên bản này, Vector API vẫn là API incubator trong module `jdk.incubator.vector`, được ghi nhận là **Twelfth Incubator**. Khi thực hành, cần đưa module này vào cả bước biên dịch và chạy. Xem [thay đổi của JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html).

Sau bài học, bạn có thể:

- Chọn kiểu vector tương ứng với mảng số nguyên hoặc số thực.
- Nạp một khối dữ liệu từ mảng nguyên thủy vào vector.
- Thực hiện phép toán theo từng lane và ghi lại kết quả.
- Dùng vòng lặp scalar hoặc mask cho các phần tử còn dư.
- Giữ đúng ý nghĩa số học khi thay mã scalar bằng mã vector.

## 2. Chọn kiểu vector và species

### Kiểu phần tử quyết định kiểu vector

| Dữ liệu trong mảng | Lớp vector | Số bit mỗi lane |
| --- | --- | --- |
| `byte[]` | `ByteVector` | 8 |
| `short[]` | `ShortVector` | 16 |
| `int[]` | `IntVector` | 32 |
| `long[]` | `LongVector` | 64 |
| `float[]` | `FloatVector` | 32 |
| `double[]` | `DoubleVector` | 64 |

Đây là các lớp chuyên biệt được cung cấp trong [package jdk.incubator.vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html).

Ví dụ, xử lý `int[]` bằng `IntVector` giữ các lane ở kiểu `int`. Chọn `FloatVector` là một quyết định dùng số thực, không phải một cách viết khác cho cùng kiểu dữ liệu.

### Species mô tả định dạng vector

Một `VectorSpecies` xác định kiểu phần tử và hình dạng vector. Số lane được lấy bằng `length()`; tổng số bit được lấy bằng `vectorBitSize()`. Xem [VectorSpecies](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html).

Ví dụ khởi đầu:

```java
private static final VectorSpecies<Integer> INT_SPECIES =
        IntVector.SPECIES_PREFERRED;

private static final VectorSpecies<Float> FLOAT_SPECIES =
        FloatVector.SPECIES_PREFERRED;
```

`SPECIES_PREFERRED` chọn species ưu tiên của nền tảng. Hãy lấy số lane từ species khi viết vòng lặp, thay vì gắn cứng rằng mọi máy đều xử lý tám phần tử mỗi lượt.

Nếu cùng có độ rộng 256 bit, một vector `int` chứa tám lane, còn một vector `double` chứa bốn lane. Vì vậy, khi đổi kiểu phần tử, cần xem lại cả số phần tử được xử lý trong mỗi bước.

Tham số `Integer` hoặc `Float` trong `VectorSpecies<Integer>` và `VectorSpecies<Float>` là cách API biểu diễn kiểu. Các mảng đang nạp vẫn là `int[]` và `float[]`.

## 3. Đọc mẫu load → compute → store

Giả sử muốn cộng hai mảng:

```java
result[i] = a[i] + b[i];
```

Nếu một vector có bốn lane, một lượt xử lý có thể được hình dung như sau:

```text
a:       ... |  1 |  2 |  3 |  4 | ...
b:       ... | 10 | 20 | 30 | 40 | ...
                   nạp cùng một khối
                         ↓
vA:          [ 1,  2,  3,  4]
vB:          [10, 20, 30, 40]
                         ↓ cộng theo lane
vResult:     [11, 22, 33, 44]
                         ↓ ghi lại
result:  ... | 11 | 22 | 33 | 44 | ...
```

Mã tương ứng với một khối đủ lane:

```java
var va = IntVector.fromArray(INT_SPECIES, a, i);
var vb = IntVector.fromArray(INT_SPECIES, b, i);
var vr = va.add(vb);
vr.intoArray(result, i);
```

`fromArray(species, array, offset)` lấy lane thứ `k` từ phần tử `array[offset + k]`. `intoArray(array, offset)` ghi lane thứ `k` về phần tử đó của mảng đích. Offset của các thao tác mảng này được tính theo **phần tử**, không phải byte. Xem [IntVector.fromArray và intoArray](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html).

Các phép như `add` tạo giá trị vector kết quả; không thay đổi giá trị của `va` tại chỗ. Mảng đích chỉ được cập nhật khi thực hiện thao tác ghi như `intoArray`. Mô hình vector và các thao tác theo lane được mô tả trong [Vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html).

Cách tính này diễn đạt cùng một phép toán trên nhiều phần tử bằng SIMD. Bản thân đoạn mã không tạo một Java thread cho từng lane.

## 4. Chương trình hoàn chỉnh với int và float

Chương trình sau có hai phép xử lý:

- Cộng hai mảng `int` theo từng vị trí.
- Biến đổi mảng `float` theo công thức `output[i] = input[i] * scale + bias`.

Hàm số nguyên dùng phần đuôi scalar. Hàm số thực dùng mask ở phần đuôi để minh họa hai cách giải quyết cùng một vấn đề.

Lưu thành `NumericVectors.java`:

```java
import java.util.Arrays;

import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

public class NumericVectors {
    private static final VectorSpecies<Integer> INT_SPECIES =
            IntVector.SPECIES_PREFERRED;

    private static final VectorSpecies<Float> FLOAT_SPECIES =
            FloatVector.SPECIES_PREFERRED;

    static void addInts(int[] a, int[] b, int[] output) {
        int n = a.length;

        if (b.length != n || output.length != n) {
            throw new IllegalArgumentException(
                    "Các mảng phải có cùng độ dài");
        }

        int upper = INT_SPECIES.loopBound(n);
        int i = 0;

        for (; i < upper; i += INT_SPECIES.length()) {
            var va = IntVector.fromArray(INT_SPECIES, a, i);
            var vb = IntVector.fromArray(INT_SPECIES, b, i);
            var sum = va.add(vb);

            sum.intoArray(output, i);
        }

        for (; i < n; i++) {
            output[i] = a[i] + b[i];
        }
    }

    static void affineFloats(
            float[] input,
            float scale,
            float bias,
            float[] output) {

        int n = input.length;

        if (output.length != n) {
            throw new IllegalArgumentException(
                    "Hai mảng phải có cùng độ dài");
        }

        var scaleVector = FloatVector.broadcast(FLOAT_SPECIES, scale);
        var biasVector = FloatVector.broadcast(FLOAT_SPECIES, bias);

        int upper = FLOAT_SPECIES.loopBound(n);
        int i = 0;

        for (; i < upper; i += FLOAT_SPECIES.length()) {
            var values = FloatVector.fromArray(FLOAT_SPECIES, input, i);
            var transformed = values.mul(scaleVector).add(biasVector);

            transformed.intoArray(output, i);
        }

        if (i < n) {
            var mask = FLOAT_SPECIES.indexInRange(i, n);
            var values =
                    FloatVector.fromArray(FLOAT_SPECIES, input, i, mask);
            var transformed = values.mul(scaleVector).add(biasVector);

            transformed.intoArray(output, i, mask);
        }
    }

    public static void main(String[] args) {
        int n = 2 * Math.max(
                INT_SPECIES.length(),
                FLOAT_SPECIES.length()) + 3;

        int[] a = new int[n];
        int[] b = new int[n];
        int[] sums = new int[n];

        float[] input = new float[n];
        float[] output = new float[n];

        for (int i = 0; i < n; i++) {
            a[i] = i + 1;
            b[i] = 10 * (i + 1);
            input[i] = i * 0.5f;
        }

        addInts(a, b, sums);
        affineFloats(input, 2.0f, 1.0f, output);

        System.out.println("Số lane int: " + INT_SPECIES.length());
        System.out.println("Số lane float: " + FLOAT_SPECIES.length());
        System.out.println(Arrays.toString(Arrays.copyOf(sums, 5)));
        System.out.println(Arrays.toString(Arrays.copyOf(output, 5)));
    }
}
```

### Biên dịch và chạy

Dùng JDK 27 cho cả hai công cụ, tại thư mục chứa tệp:

```powershell
javac --add-modules jdk.incubator.vector -encoding UTF-8 NumericVectors.java
if ($LASTEXITCODE -ne 0) {
    throw 'Bien dich that bai.'
}
java --add-modules jdk.incubator.vector NumericVectors
```

`jdk.incubator.vector` là tên module cần đưa vào quá trình biên dịch và chạy. Xem [mô tả module](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html).

Hai dòng đếm lane phụ thuộc nền tảng. Hai dòng dữ liệu đầu ra dự kiến là:

```text
[11, 22, 33, 44, 55]
[1.0, 2.0, 3.0, 4.0, 5.0]
```

Chương trình in năm phần tử đầu để kết quả dễ đọc. Kích thước mảng được tính từ species nhằm tạo dữ liệu đủ cho nhiều khối vector; không dùng số phần tử cố định làm giả định về độ rộng phần cứng.

### Broadcast dùng để làm gì?

`FloatVector.broadcast(species, scale)` tạo vector có mọi lane mang cùng giá trị `scale`. Tương tự, `biasVector` chứa cùng giá trị `bias` ở các lane.

Chẳng hạn với bốn lane:

```text
values:       [0.0, 0.5, 1.0, 1.5]
scaleVector:  [2.0, 2.0, 2.0, 2.0]
biasVector:   [1.0, 1.0, 1.0, 1.0]

values * scaleVector + biasVector
           = [1.0, 2.0, 3.0, 4.0]
```

Vector hằng được chuẩn bị trước vòng lặp vì hệ số không đổi giữa các khối. Các overload nhận scalar, chẳng hạn `values.mul(scale).add(bias)`, cũng biểu diễn việc dùng cùng hệ số ở các lane.

## 5. Giữ phần nạp và ghi trong giới hạn mảng

### Vì sao điều kiện i < n chưa đủ?

Một lệnh nạp không mask cần đủ dữ liệu cho mọi lane. Nếu mảng có mười phần tử và một vector có bốn lane, các khối đầy đủ bắt đầu ở `i = 0` và `i = 4`. Tại `i = 8` chỉ còn hai phần tử.

```text
Chỉ số:       0 1 2 3 | 4 5 6 7 | 8 9
Khối vector:  đủ 4    | đủ 4    | còn 2
```

Do đó, vòng lặp dùng `i < n` nhưng vẫn nạp cả bốn lane ở lượt cuối có thể vượt phạm vi mảng.

### loopBound chia mảng thành hai phần

`species.loopBound(n)` trả về bội số lớn nhất của số lane không vượt `n`. Với `n = 10` và bốn lane, kết quả là `8`. Xem [VectorSpecies.loopBound](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html#loopBound(int)).

Điều kiện của phần vector chính là:

```java
int upper = INT_SPECIES.loopBound(n);

for (; i < upper; i += INT_SPECIES.length()) {
    // Nạp, tính toán và ghi một khối đầy đủ.
}
```

Sau vòng lặp, `i` đánh dấu đầu phần còn dư. Hàm `addInts` xử lý các phần tử này bằng vòng lặp scalar.

Cách chia trên bao quát các trường hợp:

| Độ dài n | Phần vector đầy đủ | Phần còn dư |
| --- | --- | --- |
| `0` | Không có | Không có |
| `n < L` | Không có | Toàn bộ mảng |
| `n = L` | Một khối | Không có |
| `n = L + 1` | Một khối | Một phần tử |
| `n = 2L` | Hai khối | Không có |

`L` là `species.length()` của kiểu vector đang dùng.

### Ràng buộc độ dài là một phần của hợp đồng hàm

Trong `addInts`, kiểm tra ba mảng cùng độ dài giúp xác định rõ rằng mọi phần tử đầu vào có một vị trí đầu ra tương ứng. Trong `affineFloats`, độ dài mảng đầu vào và đầu ra cũng phải bằng nhau.

Mask không thay thế việc xác định hợp đồng này. Một mask được tạo theo độ dài mảng `a` không tự bảo vệ mảng `b` ngắn hơn ở những lane vẫn được bật.

## 6. Xử lý phần đuôi bằng mask

Trong `affineFloats`, sau các khối đầy đủ, đoạn sau xử lý tối đa một khối còn dư:

```java
if (i < n) {
    var mask = FLOAT_SPECIES.indexInRange(i, n);
    var values =
            FloatVector.fromArray(FLOAT_SPECIES, input, i, mask);
    var transformed = values.mul(scaleVector).add(biasVector);

    transformed.intoArray(output, i, mask);
}
```

`indexInRange(i, n)` bật những lane có chỉ số tương ứng nằm trong mảng. Mask này được dùng ở cả thao tác nạp và thao tác ghi.

Với masked load của `FloatVector`, lane tắt được điền `+0.0f`. Với masked store, lane tắt không ghi vào mảng đích. Các quy tắc được mô tả trong [FloatVector.fromArray và intoArray](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html).

Giả sử `n = 10`, có bốn lane và `i = 8`:

```text
input còn lại:   [4.0, 4.5, ngoài mảng, ngoài mảng]
mask:            [true, true, false, false]
sau khi nạp:     [4.0, 4.5, 0.0, 0.0]
nhân 2, cộng 1:  [9.0, 10.0, 1.0, 1.0]
ghi có mask:     output[8] = 9.0
                 output[9] = 10.0
```

Hai lane tắt vẫn có thể mang giá trị trung gian khác zero sau phép toán. Chúng không trở thành dữ liệu hợp lệ của mảng. Giữ mask khi ghi bảo đảm chỉ hai phần tử thật được cập nhật.

### Mask ở phép tính không thay mask ở truy cập mảng

Nếu nạp không mask tại vị trí chỉ còn hai phần tử, lỗi vượt giới hạn có thể xảy ra ngay lúc nạp. Thêm mask cho một phép cộng phía sau không sửa được lần truy cập trước đó.

Ngược lại, nạp có mask rồi ghi không mask vẫn có thể vượt mảng đích. Khi xử lý phần đuôi, hãy theo dõi toàn bộ đường đi của một khối: vị trí nạp, lane hợp lệ và vị trí ghi.

### Có thể dùng mask cho phần đuôi int

Trong `addInts`, có thể thay riêng vòng lặp scalar cuối bằng đoạn dưới đây:

```java
if (i < n) {
    var mask = INT_SPECIES.indexInRange(i, n);

    var va = IntVector.fromArray(INT_SPECIES, a, i, mask);
    var vb = IntVector.fromArray(INT_SPECIES, b, i, mask);

    va.add(vb).intoArray(output, i, mask);
}
```

Các mảng vẫn phải tuân theo kiểm tra độ dài ở đầu hàm.

Hai phương án phần đuôi có ưu điểm khác nhau:

| Phương án | Đặc điểm |
| --- | --- |
| Scalar tail | Dễ đối chiếu với công thức từng phần tử |
| Masked tail | Tiếp tục diễn đạt phép xử lý bằng vector và mask |

Lựa chọn hiệu năng cần được đo trên tác vụ và nền tảng cụ thể. Một phần đuôi ngắn không tự chứng minh rằng dùng mask sẽ nhanh hơn.

## 7. Áp dụng cùng mẫu cho double và các kiểu số nguyên khác

Khi dữ liệu cần `double`, thay đồng bộ kiểu mảng, lớp vector và species. Thêm import:

```java
import jdk.incubator.vector.DoubleVector;
```

Ví dụ dưới đây xử lý đúng một khối, có thể đặt trong một phương thức của `NumericVectors`:

```java
VectorSpecies<Double> species = DoubleVector.SPECIES_PREFERRED;

double[] input = new double[species.length()];
double[] output = new double[input.length];

Arrays.fill(input, 4.0);

var values = DoubleVector.fromArray(species, input, 0);
var scaled = values.mul(0.5);
scaled.intoArray(output, 0);

System.out.println(Arrays.toString(output));
```

Mọi phần tử đầu ra của khối này là `2.0`. Mảng được tạo đúng bằng số lane nên ví dụ không có phần đuôi. Với mảng dài tùy ý, áp dụng lại cách chia khối và xử lý phần dư ở các phần trước. Xem [DoubleVector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/DoubleVector.html).

Bảng đối chiếu khi chuyển kiểu:

| Thành phần | Phiên bản int | Phiên bản long | Phiên bản double |
| --- | --- | --- | --- |
| Mảng | `int[]` | `long[]` | `double[]` |
| Vector | `IntVector` | `LongVector` | `DoubleVector` |
| Species | `VectorSpecies<Integer>` | `VectorSpecies<Long>` | `VectorSpecies<Double>` |
| Hằng scalar điển hình | `2` | `2L` | `2.0` |
| Bước vòng lặp | Species của `int` | Species của `long` | Species của `double` |

Với `byte` và `short`, cũng cần chọn các kiểu tương ứng. Hãy kiểm tra rằng phạm vi giá trị và phép toán của kiểu đó đáp ứng yêu cầu dữ liệu.

Việc đổi vector đang chứa số nguyên thành số thực là một thao tác chuyển đổi riêng. Không coi việc nhìn lại cùng các bit dưới kiểu khác là phép chuyển giá trị số học. Trong bài này, mỗi phương thức nạp trực tiếp từ mảng có đúng kiểu dữ liệu cần tính.

## 8. Giữ đúng ý nghĩa số học

### Phép cộng int vẫn có thể tràn

Một lane `int` vẫn có phạm vi 32 bit. Dùng vector không tự mở rộng kết quả của phép cộng thành `long`.

Ví dụ scalar:

```java
int result = Integer.MAX_VALUE + 1;
// result là Integer.MIN_VALUE
```

Phép cộng `int` thông thường không tự báo lỗi tràn. Khi vector hóa phép cộng tương ứng, cần giữ đúng yêu cầu số học của ứng dụng. Quy tắc phép toán số nguyên được mô tả tại [JLS 4.2.2](https://docs.oracle.com/javase/specs/jls/se27/html/jls-4.html#jls-4.2.2); biểu thức của các toán tử vector được nêu trong [VectorOperators](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorOperators.html).

Nếu nghiệp vụ cần kết quả nằm ngoài miền `int`, hãy thiết kế đầu vào, phép tính và đầu ra với kiểu phù hợp. Nếu cần phát hiện tràn, đó phải là một phần rõ ràng của thuật toán; không giả định `IntVector.add` có hành vi như `Math.addExact`.

### mul rồi add và fused multiply-add là hai lựa chọn

Trong `affineFloats`, chuỗi phép toán đang là:

```java
var transformed = values.mul(scaleVector).add(biasVector);
```

Vector API còn có phép `fma` để diễn đạt fused multiply-add:

```java
var transformed = values.fma(scaleVector, biasVector);
```

FMA tính tích cộng với số hạng còn lại rồi làm tròn theo hợp đồng của phép toán hợp nhất. Vì cách làm tròn khác phép nhân rồi phép cộng riêng, kết quả có thể khác ở những dữ liệu nhạy với sai số. Xem [Math.fma](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Math.html#fma(float,float,float)).

Khi lựa chọn FMA, phần đuôi scalar tham chiếu cũng nên dùng công thức tương ứng, chẳng hạn:

```java
output[i] = Math.fma(input[i], scale, bias);
```

Không dùng kết quả của một công thức làm bằng chứng rằng công thức khác luôn phải khớp từng bit.

### Dữ liệu số thực cần tiêu chí so sánh phù hợp

Ví dụ với hệ số `2.0f` và `1.0f` được chọn để dễ đọc. Với dữ liệu thực tế, cần xác định rõ:

- Dùng `float` hay `double`.
- Có cho phép sai số tuyệt đối hoặc tương đối hay không.
- Xử lý `NaN`, vô cực và zero có dấu như thế nào.
- Chuỗi phép toán của bản tham chiếu có giống bản vector hay không.

Bài này xử lý từng phần tử độc lập. Nếu mở rộng thành phép cộng dồn nhiều lane, thứ tự cộng là một vấn đề số học khác cần được xem xét riêng.

## 9. Những lỗi thường gặp khi nạp, tính và ghi

| Hiện tượng | Nguyên nhân có thể gặp | Cách sửa |
| --- | --- | --- |
| Compiler không thấy package vector | Chưa đưa module incubator vào bước biên dịch | Thêm `--add-modules jdk.incubator.vector` |
| Chạy chương trình không nạp được lớp vector | Bước chạy thiếu module tương ứng | Đặt cùng tùy chọn module cho `java` |
| Lỗi vượt giới hạn ở khối cuối | Nạp hoặc ghi toàn bộ lane khi mảng còn ít phần tử | Dùng `loopBound` và xử lý phần đuôi |
| Phần cuối mảng giữ nguyên giá trị cũ | Chỉ xử lý các khối đầy đủ | Bổ sung scalar tail hoặc masked tail |
| Kết quả vẫn bằng dữ liệu ban đầu | Bỏ qua giá trị trả về của phép toán | Ghi vector kết quả thay vì vector đầu vào |
| Chỉ đúng trên một cấu hình máy | Bước lặp hoặc số lane bị gắn cứng | Lấy số lane từ species |
| Mask không dùng được với vector | Mask thuộc kiểu hoặc định dạng khác | Tạo mask từ species đang dùng |
| Mảng đầu ra sai sau khi đổi kiểu số | Chỉ đổi một phần trong mảng, vector, species hoặc công thức | Chuyển đồng bộ và kiểm tra lại số học |

### Phân biệt vector bất biến và mảng có thể thay đổi

`values.mul(...)` biểu diễn giá trị kết quả mới. `intoArray(...)` là thao tác cập nhật mảng được truyền vào. Khi thiết kế hàm, cần biết mảng nào là đầu vào và mảng nào nhận kết quả.

Hai hàm trong bài có thể ghi tại chỗ nếu mảng đầu ra chính là một mảng đầu vào tương ứng:

```java
addInts(a, b, a);
affineFloats(input, 2.0f, 1.0f, input);
```

Điều này phù hợp với các hàm đã viết vì mỗi phần tử đầu ra chỉ dùng dữ liệu đầu vào ở cùng chỉ số, và dữ liệu của khối được nạp trước khi khối được ghi.

Không suy rộng tính chất đó sang thuật toán dùng phần tử lân cận hoặc dùng các vùng đọc/ghi chồng lấn có offset lệch nhau. Khi thêm những quan hệ phụ thuộc như vậy, cần phân tích lại thứ tự nạp và ghi.

## 10. Thực hành và đánh giá hiệu quả

### Đối chiếu với bản scalar

Một bản tham chiếu đơn giản cho hai công thức là:

```java
for (int i = 0; i < a.length; i++) {
    expectedInts[i] = a[i] + b[i];
}

for (int i = 0; i < input.length; i++) {
    expectedFloats[i] = input[i] * scale + bias;
}
```

Các mảng `expectedInts` và `expectedFloats` phải được tạo đúng độ dài trước khi dùng. Khi thực hành, chạy bản tham chiếu và bản vector trên cùng dữ liệu đầu vào, rồi kiểm tra từng vị trí.

Các kích thước nên xét, với `L` là số lane của từng kiểu:

| Kích thước | Mục đích |
| --- | --- |
| `0` | Không nạp hoặc ghi khối nào |
| `1` | Xử lý đầu vào rất ngắn |
| `L - 1` | Phần còn dư chiếm toàn bộ mảng, nếu `L > 1` |
| `L` | Đúng một khối đầy đủ |
| `L + 1` | Một khối và một phần tử đuôi |
| `2L + 3` | Nhiều khối và có thể có phần đuôi |
| Mảng lớn với độ dài không chia hết cho `L` | Kiểm tra xử lý phần dư khi có nhiều khối |

Với số nguyên, thêm dữ liệu gần giới hạn của kiểu. Với số thực, thêm giá trị âm, phân số và các giá trị đặc biệt theo yêu cầu của ứng dụng.

### Bài tập mở rộng

1. Thay scalar tail trong `addInts` bằng masked tail, rồi đối chiếu kết quả theo các kích thước trên.
2. Viết hàm cho `double[]` theo công thức `output[i] = input[i] * factor`, hỗ trợ mảng dài tùy ý.
3. Cho phép `affineFloats` ghi vào chính mảng đầu vào và giải thích vì sao cách làm này phù hợp với công thức hiện tại.
4. Tạo một phiên bản dùng FMA và chỉ rõ bản scalar tham chiếu tương ứng.

### Đo hiệu năng trên công việc thực tế

Số lane không phải hệ số tăng tốc được bảo đảm. Chi phí đọc/ghi bộ nhớ, kích thước dữ liệu, khả năng tối ưu của JVM và tập lệnh của CPU đều ảnh hưởng đến kết quả. Mô tả module nêu khả năng biên dịch sang SIMD trên các nền tảng phù hợp, chẳng hạn AVX trên x64 và NEON trên AArch64. Xem [module Vector API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html).

Sau khi đã xác định đúng kết quả, có thể đo bản scalar và bản vector bằng [OpenJDK JMH](https://github.com/openjdk/jmh). Cần dành thời gian warmup, tránh đưa việc tạo dữ liệu hoặc in log vào phần đang đo, và bảo đảm kết quả phép tính thực sự được sử dụng.
