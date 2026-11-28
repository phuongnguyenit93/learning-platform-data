# Nạp dữ liệu từ mảng và ghi kết quả

> **Mốc cập nhật: 27-11-2026.** Vector API trong JDK 27 tiếp tục là **Incubator lần thứ 12** theo JEP 537. API nằm trong module `jdk.incubator.vector`, chưa phải API ổn định của Java SE. Bài này dùng hợp đồng JDK 27 cho `VectorSpecies`, `FloatVector.fromArray(...)`, `intoArray(...)`, `VectorMask` và xử lý phần tử cuối mảng.

## 1. Mục tiêu thực hành

Vector API biểu diễn phép toán trên nhiều phần tử cùng lúc theo mô hình SIMD (Single Instruction, Multiple Data). Thay vì đọc một phần tử, tính toán rồi ghi lại trong mỗi vòng lặp scalar, chương trình có thể nạp một nhóm phần tử thành vector, thực hiện phép toán theo từng lane và ghi vector kết quả trở lại mảng.

Bài học tập trung vào hai thao tác nền tảng:

- **Load:** nạp các lane từ mảng primitive vào vector bằng `fromArray(...)`.
- **Store:** ghi các lane của vector ra mảng bằng `intoArray(...)`.

Sau bài này, bạn có thể:

- Chọn `VectorSpecies` phù hợp với kiểu dữ liệu và phần cứng hiện tại.
- Hiểu `offset`, số lane và điều kiện truy cập mảng hợp lệ.
- Nạp và ghi vector theo từng block có kích thước bằng số lane.
- Xử lý phần dư cuối mảng bằng scalar tail hoặc masked load/store.
- Tránh đọc hoặc ghi vượt biên bằng `VectorMask`.
- Biên dịch và chạy đúng module incubator của JDK 27.
- Đo hiệu năng trên workload thật và so sánh với vòng lặp Java thông thường.

## 2. Trạng thái và cách sử dụng Vector API hiện hành

JDK 27 đưa Vector API vào lần incubator thứ 12 theo **JEP 537 — Vector API (Twelfth Incubator)**. Đây là API thử nghiệm nằm trong module riêng; package documentation ghi rõ trạng thái incubating. API có thể tiếp tục thay đổi hoặc bị loại bỏ trong một release tương lai.

Các kiểu vector hỗ trợ sáu kiểu primitive:

| Kiểu vector | Kiểu phần tử của mảng |
|---|---|
| `ByteVector` | `byte[]` |
| `ShortVector` | `short[]` |
| `IntVector` | `int[]` |
| `LongVector` | `long[]` |
| `FloatVector` | `float[]` |
| `DoubleVector` | `double[]` |

Mỗi vector gồm một số lane cố định. Mỗi lane chứa một giá trị primitive. Ví dụ, một `FloatVector` có thể có 4, 8 hoặc số lane khác tùy species được chọn và nền tảng chạy.

Vector API không phải API tạo nhiều Java thread. Các lane là các phần tử được xử lý song song theo lệnh SIMD nếu CPU và JIT hỗ trợ. Nó cũng không thay thế mọi phép tối ưu tự động của HotSpot; JIT có thể tự vectorize một số vòng lặp Java scalar.

### 2.1. Incubator khác Preview

| Trạng thái | Cách bật |
|---|---|
| Preview API/language feature | Dùng `--enable-preview` khi compile và run. |
| Incubator module | Thêm module bằng `--add-modules`. |

Vector API cần:

```text
--add-modules jdk.incubator.vector
```

Không cần `--enable-preview` chỉ để sử dụng Vector API. Hai cơ chế này khác nhau.

Biên dịch và chạy một chương trình bằng JDK 27:

```text
javac --release 27 --add-modules jdk.incubator.vector VectorArrayIO.java
java --add-modules jdk.incubator.vector VectorArrayIO
```

Nếu ứng dụng dùng module system, khai báo dependency trong `module-info.java`:

```java
module com.example.vectorapp {
    requires jdk.incubator.vector;
}
```

Nếu chạy trên classpath, không cần `module-info.java`; chỉ cần thêm `--add-modules jdk.incubator.vector` cho cả compile và runtime.

## 3. VectorSpecies và số lane

Một `VectorSpecies<E>` mô tả kiểu phần tử và hình dạng vector. Species xác định số lane, kích thước vector và các đặc tính cần thiết để tạo vector cùng loại.

Ví dụ với float:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

static final VectorSpecies<Float> SPECIES =
        FloatVector.SPECIES_PREFERRED;
```

`SPECIES_PREFERRED` chọn species phù hợp với nền tảng hiện tại. Đây là lựa chọn nên dùng cho code portable vì số lane có thể khác giữa các CPU hoặc JVM.

Một số species cố định cũng có sẵn, ví dụ:

```java
FloatVector.SPECIES_128
FloatVector.SPECIES_256
FloatVector.SPECIES_512
```

Không nên mặc định CPU nào cũng hỗ trợ shape 512-bit. Nếu chọn một shape không được nền tảng hỗ trợ tối ưu, code vẫn có thể chạy qua implementation scalar nhưng không đạt lợi ích SIMD mong đợi.

Các thông tin thường dùng:

| API | Ý nghĩa |
|---|---|
| `SPECIES.length()` | Số lane trong một vector. |
| `SPECIES.vectorBitSize()` | Tổng số bit của vector. |
| `SPECIES.vectorByteSize()` | Tổng số byte của vector. |
| `SPECIES.elementType()` | Kiểu primitive của lane. |
| `SPECIES.loopBound(length)` | Mốc lớn nhất không vượt quá length và là bội số của số lane. |
| `SPECIES.indexInRange(offset, limit)` | Tạo mask cho các lane có index nằm trong miền hợp lệ. |

Giữ species trong một field `static final` hoặc local/parameter khi dùng. Javadoc khuyến nghị cách này để runtime compiler tối ưu việc tạo và sử dụng vector tốt hơn.

## 4. Nạp vector từ mảng bằng fromArray

Với `FloatVector`, dạng cơ bản:

```java
FloatVector vector = FloatVector.fromArray(
        SPECIES,
        source,
        offset
);
```

Các tham số:

- `SPECIES`: species của vector cần tạo.
- `source`: mảng `float[]`.
- `offset`: index của phần tử đầu tiên được nạp vào lane 0.

Giả sử species có 4 lane và mảng là:

```text
source = [10, 20, 30, 40, 50, 60, 70, 80]
```

Khi gọi:

```java
FloatVector vector = FloatVector.fromArray(SPECIES, source, 2);
```

vector nhận các giá trị:

```text
lane 0 = source[2] = 30
lane 1 = source[3] = 40
lane 2 = source[4] = 50
lane 3 = source[5] = 60
```

`offset` là index phần tử trong mảng, không phải byte offset. API không yêu cầu lập trình viên tự căn chỉnh offset theo số byte của vector; tuy nhiên hiệu năng có thể phụ thuộc nền tảng và cách truy cập bộ nhớ.

### 4.1. Điều kiện biên của load không mask

Khi nạp vector không dùng mask, mọi lane phải đọc được một phần tử hợp lệ. Với species có `L` lane, điều kiện là:

```text
0 <= offset
offset + L <= source.length
```

Nếu một lane vượt ngoài mảng, `fromArray(...)` ném `IndexOutOfBoundsException`.

Ví dụ sai khi species có 8 lane:

```java
float[] source = new float[10];

// offset 4 cần đọc index 4..11, vượt quá source.length - 1.
FloatVector vector = FloatVector.fromArray(SPECIES, source, 4);
```

Không giả định lần nạp cuối luôn đủ lane. Khi độ dài mảng không chia hết cho số lane, phải xử lý phần dư.

## 5. Ghi vector ra mảng bằng intoArray

Sau khi tính toán, ghi vector vào mảng đích:

```java
vector.intoArray(destination, offset);
```

`intoArray` ghi lane 0 vào `destination[offset]`, lane 1 vào `destination[offset + 1]` và tiếp tục theo thứ tự lane.

Ví dụ:

```java
float[] destination = new float[8];

FloatVector vector = FloatVector.fromArray(
        SPECIES,
        new float[] { 1, 2, 3, 4 },
        0
);

vector.intoArray(destination, 2);
```

Kết quả:

```text
destination = [0, 0, 1, 2, 3, 4, 0, 0]
```

Khi không dùng mask, toàn bộ lane phải có chỗ ghi hợp lệ:

```text
0 <= offset
offset + SPECIES.length() <= destination.length
```

Nếu vùng ghi không đủ, `intoArray(...)` ném `IndexOutOfBoundsException`.

### 5.1. Ghi trực tiếp hay tạo mảng mới?

Nếu cần ghi vào mảng kết quả đã cấp phát, ưu tiên:

```java
vector.intoArray(destination, offset);
```

Nếu cần tạo một mảng mới chứa các lane của vector, có thể dùng:

```java
float[] lanes = vector.toArray();
```

`toArray()` tạo một mảng mới. Trong vòng lặp xử lý dữ liệu lớn, gọi `toArray()` cho từng block thường tạo allocation không cần thiết. `intoArray()` ghi trực tiếp vào mảng đích và phù hợp hơn với pipeline load–compute–store.

## 6. Ví dụ đầy đủ — nhân hai mảng và ghi kết quả

Bài toán: cho hai mảng `a` và `b` có cùng kích thước, tạo mảng `result` sao cho:

[
result[i] = a[i] \times b[i]
]

Dùng vector để xử lý nhiều phần tử trong một vòng lặp:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public final class VectorArrayIO {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    private VectorArrayIO() {}

    public static void multiply(
            float[] a,
            float[] b,
            float[] result) {

        if (a == null || b == null || result == null) {
            throw new NullPointerException("Arrays must not be null");
        }

        if (a.length != b.length || a.length != result.length) {
            throw new IllegalArgumentException(
                    "All arrays must have the same length"
            );
        }

        int i = 0;
        int upperBound = SPECIES.loopBound(a.length);

        // Chỉ xử lý các block có đủ số lane.
        for (; i < upperBound; i += SPECIES.length()) {
            FloatVector va = FloatVector.fromArray(SPECIES, a, i);
            FloatVector vb = FloatVector.fromArray(SPECIES, b, i);

            FloatVector product = va.mul(vb);

            product.intoArray(result, i);
        }

        // Xử lý phần dư bằng scalar.
        for (; i < a.length; i++) {
            result[i] = a[i] * b[i];
        }
    }

    public static void main(String[] args) {
        float[] a = { 1, 2, 3, 4, 5, 6, 7 };
        float[] b = { 10, 20, 30, 40, 50, 60, 70 };
        float[] result = new float[a.length];

        multiply(a, b, result);

        System.out.println(java.util.Arrays.toString(result));
    }
}
```

Kết quả:

```text
[10.0, 40.0, 90.0, 160.0, 250.0, 360.0, 490.0]
```

### 6.1. Vì sao dùng loopBound?

`SPECIES.loopBound(a.length)` trả về số phần tử lớn nhất không vượt quá độ dài mảng và chia hết cho số lane.

Ví dụ species có 4 lane:

| Độ dài mảng | loopBound | Vector loop | Scalar tail |
|---:|---:|---|---:|
| 0 | 0 | Không chạy | 0 |
| 3 | 0 | Không chạy | 3 |
| 4 | 4 | 1 block | 0 |
| 6 | 4 | 1 block | 2 |
| 8 | 8 | 2 block | 0 |
| 10 | 8 | 2 block | 2 |

Cách này bảo đảm `fromArray` và `intoArray` không đọc/ghi vượt biên. Không tự viết phép AND bit để tính phần chia hết cho lane count, vì không nên giả định số lane luôn là lũy thừa của 2.

## 7. Xử lý phần dư bằng VectorMask

Thay vì tách scalar tail, có thể dùng mask để xử lý cả block cuối cùng. Mask xác định lane nào được phép đọc hoặc ghi.

### 7.1. Tạo mask bằng indexInRange

```java
VectorMask<Float> mask =
        SPECIES.indexInRange(offset, arrayLength);
```

Mask bật những lane có index `offset + lane` nằm trong khoảng:

```text
[0, arrayLength - 1]
```

Các lane ngoài khoảng bị tắt.

Ví dụ species có 4 lane, mảng có 6 phần tử, offset là 4:

```text
lane:       0     1     2     3
array idx:  4     5     6     7
in range:   yes   yes   no    no
mask:       true  true  false false
```

### 7.2. Masked load và masked store

`fromArray` có overload nhận mask:

```java
FloatVector vector =
        FloatVector.fromArray(SPECIES, source, offset, mask);
```

Các lane được bật sẽ đọc phần tử tương ứng từ mảng. Lane bị tắt được đặt về giá trị mặc định của kiểu lane, với float là positive zero.

`intoArray` cũng có overload nhận mask:

```java
vector.intoArray(destination, offset, mask);
```

Chỉ những lane được bật mới được ghi. Các vị trí tương ứng với lane tắt giữ nguyên giá trị cũ trong mảng đích.

Ví dụ hoàn chỉnh với masked tail:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorSpecies;

public final class MaskedVectorArrayIO {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    public static void add(
            float[] a,
            float[] b,
            float[] result) {

        if (a.length != b.length || a.length != result.length) {
            throw new IllegalArgumentException(
                    "All arrays must have the same length"
            );
        }

        for (int i = 0; i < a.length; i += SPECIES.length()) {
            VectorMask<Float> mask =
                    SPECIES.indexInRange(i, a.length);

            FloatVector va =
                    FloatVector.fromArray(SPECIES, a, i, mask);
            FloatVector vb =
                    FloatVector.fromArray(SPECIES, b, i, mask);

            FloatVector sum = va.add(vb);

            sum.intoArray(result, i, mask);
        }
    }
}
```

Trong vòng cuối, masked load chỉ đọc lane hợp lệ và masked store chỉ ghi các lane hợp lệ. Không cần scalar tail.

### 7.3. Chọn scalar tail hay masked tail?

| Cách xử lý | Ưu điểm | Điểm cần cân nhắc |
|---|---|---|
| Full vector loop + scalar tail | Vòng lặp chính không cần mask; Javadoc lưu ý cách này có thể đạt hiệu năng tốt hơn với mảng lớn. | Có thêm vòng lặp scalar ngắn. |
| Masked load/store | Một vòng lặp; biểu diễn rõ ràng lane hợp lệ ở cuối mảng. | Mask được tạo và dùng ở mọi vòng; có thể có chi phí thêm. |

Không có một cách luôn nhanh hơn. Hãy đo trên CPU, JDK và kích thước dữ liệu thực tế.

## 8. Bài tập load/store với các kiểu dữ liệu khác

Mô hình `fromArray` và `intoArray` tương tự giữa các subtype vector. Chỉ thay loại vector, species và kiểu mảng.

### 8.1. IntVector

```java
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

static final VectorSpecies<Integer> INT_SPECIES =
        IntVector.SPECIES_PREFERRED;

static void addInts(int[] a, int[] b, int[] result) {
    if (a.length != b.length || a.length != result.length) {
        throw new IllegalArgumentException("Length mismatch");
    }

    int i = 0;
    int upper = INT_SPECIES.loopBound(a.length);

    for (; i < upper; i += INT_SPECIES.length()) {
        IntVector va = IntVector.fromArray(INT_SPECIES, a, i);
        IntVector vb = IntVector.fromArray(INT_SPECIES, b, i);

        va.add(vb).intoArray(result, i);
    }

    for (; i < a.length; i++) {
        result[i] = a[i] + b[i];
    }
}
```

### 8.2. DoubleVector

```java
import jdk.incubator.vector.DoubleVector;
import jdk.incubator.vector.VectorSpecies;

static final VectorSpecies<Double> DOUBLE_SPECIES =
        DoubleVector.SPECIES_PREFERRED;

static void scale(double[] source, double factor, double[] result) {
    if (source.length != result.length) {
        throw new IllegalArgumentException("Length mismatch");
    }

    int i = 0;
    int upper = DOUBLE_SPECIES.loopBound(source.length);
    DoubleVector factorVector =
            DoubleVector.broadcast(DOUBLE_SPECIES, factor);

    for (; i < upper; i += DOUBLE_SPECIES.length()) {
        DoubleVector values =
                DoubleVector.fromArray(DOUBLE_SPECIES, source, i);

        values.mul(factorVector).intoArray(result, i);
    }

    for (; i < source.length; i++) {
        result[i] = source[i] * factor;
    }
}
```

Hãy tự viết thêm phiên bản `LongVector` cho mảng `long[]`, và `ByteVector` cho mảng `byte[]`. Với byte arithmetic, cần hiểu quy tắc tràn số của kiểu `byte` và phép toán vector trước khi so sánh với scalar code.

## 9. Lỗi thường gặp khi load và store

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `IndexOutOfBoundsException` khi load | Offset không còn đủ chỗ cho tất cả lane. | Dùng `loopBound` + scalar tail hoặc masked load. |
| `IndexOutOfBoundsException` khi store | Mảng đích không đủ chỗ cho toàn vector. | Kiểm tra độ dài hoặc masked store. |
| Kết quả cuối mảng sai | Vòng vector bỏ qua phần dư nhưng quên scalar tail. | Xử lý mọi index từ upperBound đến length. |
| Kết quả có số 0 ngoài ý muốn | Masked load đặt lane tắt thành zero nhưng code lưu cả vector. | Dùng cùng mask khi store để không ghi lane tắt. |
| Không compile được Vector API | Module incubator chưa được thêm. | Thêm `--add-modules jdk.incubator.vector`. |
| Dùng `--enable-preview` nhưng vẫn không tìm thấy package | Preview flag không bật incubator module. | Thêm module flag; không nhầm hai cơ chế. |
| Mã chạy nhưng không nhanh hơn | CPU/JIT không hỗ trợ SIMD phù hợp, workload quá nhỏ hoặc scalar loop đã được auto-vectorize. | Đo benchmark, kiểm tra platform và workload. |
| Vector operation báo species không tương thích | Các vector đầu vào có species/shape/length khác nhau. | Tạo các vector từ cùng species. |

Không dùng `SPECIES_512` chỉ vì nghĩ vector càng rộng càng nhanh. Hình dạng vector phải phù hợp với phần cứng và dữ liệu. Ưu tiên `SPECIES_PREFERRED` cho code tổng quát.

## 10. Lưu ý về offset, mask và mảng

### 10.1. Offset là chỉ số phần tử

Với `float[]`, offset được tính theo phần tử float. Không nhân offset với 4 để chuyển thành byte offset. `fromArray` và `intoArray` làm việc trực tiếp với array index.

### 10.2. Mask phải cùng species

Mask được tạo từ `SPECIES.indexInRange(...)` có species tương ứng với vector. Khi dùng một mask với vector khác species, thao tác có thể thất bại do không tương thích. Hãy tạo vector và mask từ cùng một species.

### 10.3. Mask không sửa kích thước vector

Masked load vẫn tạo vector có đầy đủ số lane của species. Lane bị tắt được điền giá trị mặc định; vector không trở thành vector ngắn hơn. Mask chỉ điều khiển lane nào tham gia truy cập hoặc phép toán.

### 10.4. Không ghi nhầm phần tử ngoài phạm vi

Masked store là cơ chế quan trọng khi xử lý phần dư. Nếu lane cuối bị tắt, phần tử đích tương ứng không bị ghi. Điều này đặc biệt hữu ích khi mảng đích đã có dữ liệu và chỉ một phần block cuối thuộc vùng cần cập nhật.

### 10.5. Kiểm soát alias giữa mảng nguồn và đích

Nếu `result` trùng hoàn toàn với `a` hoặc `b`, phép tính element-wise tại cùng offset thường có thể thực hiện in-place vì mỗi block được nạp trước khi ghi kết quả block đó. Nếu các mảng có vùng chồng lấp lệch offset hoặc dữ liệu được chia sẻ qua view khác, cần phân tích thứ tự đọc/ghi để tránh ghi đè dữ liệu chưa được nạp.

## 11. Kiểm tra tính đúng trước khi benchmark

Trước khi đo tốc độ, so sánh kết quả vector với phiên bản scalar cho nhiều độ dài mảng:

- Độ dài 0 và 1.
- Độ dài nhỏ hơn một vector.
- Độ dài đúng bằng một vector.
- Độ dài lớn hơn một vector một phần tử.
- Nhiều block đầy đủ và phần dư.
- Offset khác 0.
- Mảng có số âm, số 0, giá trị lớn và giá trị nhỏ.
- Mảng đích có sẵn giá trị để xác nhận masked store không ghi lane bị tắt.

Ví dụ kiểm tra:

```java
static void verify(float[] a, float[] b) {
    float[] scalar = new float[a.length];
    float[] vector = new float[a.length];

    for (int i = 0; i < a.length; i++) {
        scalar[i] = a[i] * b[i];
    }

    VectorArrayIO.multiply(a, b, vector);

    if (!java.util.Arrays.equals(scalar, vector)) {
        throw new AssertionError("Vector result differs from scalar");
    }
}
```

Với phép tính float element-wise đơn giản như nhân từng cặp phần tử, thứ tự phép toán trong mỗi lane giống phép scalar tương ứng. Với phép reduction như tổng nhiều lane, thứ tự cộng có thể thay đổi và kết quả dấu phẩy động có thể khác ở các bit cuối do quy tắc làm tròn.

## 12. Đánh giá hiệu năng đúng cách

Vector API được thiết kế để JIT biên dịch phép toán thành lệnh SIMD phù hợp nếu nền tảng hỗ trợ. Nếu không có phần cứng vector thích hợp hoặc operation không được tối ưu, implementation scalar mặc định vẫn bảo đảm kết quả đúng nhưng có thể không nhanh hơn.

Các điểm cần đo:

- Kích thước mảng nhỏ, trung bình và lớn.
- Chi phí cấp phát mảng kết quả tách biệt với chi phí tính toán.
- Warm-up JIT trước khi ghi nhận số liệu.
- Số lần chạy và nhiều fork của JVM.
- Throughput (phần tử/giây) và thời gian mỗi phần tử.
- CPU model, JDK vendor/build, kiến trúc và cờ JVM.
- So sánh scalar loop, vector loop có scalar tail và vector loop masked.

Dùng JMH hoặc harness benchmark đáng tin cậy. Không kết luận từ một lần đo `System.nanoTime()` hoặc một lần chạy duy nhất. HotSpot có thể tự vectorize vòng lặp scalar; do đó baseline phải là code scalar tối ưu hợp lý, không cố tình viết chậm để làm Vector API có vẻ nhanh hơn.

Không giả định mọi CPU đều có cùng khả năng SIMD. Tài liệu JDK 27 mô tả implementation tối ưu trên Intel x64 hỗ trợ AVX2 đến AVX-512 và ARM AArch64 với NEON; nền tảng không có hỗ trợ SIMD chuyên dụng vẫn chạy đúng nhưng có thể không nhận được lợi ích hiệu năng. Kiểm tra tài liệu và kết quả trên đúng CPU triển khai, không suy rộng từ một máy phát triển.

## 13. Bài tập tổng hợp

1. Viết hàm nhân hai mảng `float[]` bằng `FloatVector.fromArray` và `intoArray`.
2. Viết phiên bản dùng `loopBound` và scalar tail.
3. Viết phiên bản masked load/store với `indexInRange`.
4. Thử độ dài mảng không chia hết cho `SPECIES.length()`; xác nhận không đọc/ghi vượt biên.
5. Đổi sang `IntVector` và `DoubleVector`; giữ cùng cấu trúc load–compute–store.
6. Tạo offset bắt đầu khác 0 và xử lý một đoạn con của mảng.
7. Kiểm tra mảng đích có sẵn giá trị; xác nhận masked store giữ nguyên lane bị tắt.
8. So sánh thời gian của scalar, vector + scalar tail và masked vector.
9. Thử chạy trên hai loại CPU hoặc hai cấu hình JVM khác nhau; ghi nhận species length và kết quả.
10. Giải thích vì sao `SPECIES_PREFERRED` portable hơn việc hard-code `SPECIES_512`.

Bảng ghi nhận:

| Trường hợp | Độ dài | Species length | Vector blocks | Tail | Kết quả đúng |
|---|---:|---:|---:|---:|---|
| Mảng rỗng | 0 | | 0 | 0 | |
| Nhỏ hơn một vector | 3 | | 0 | 3 | |
| Đúng một vector | | | | 0 | |
| Một vector + 1 | | | | 1 | |
| Nhiều vector + phần dư | | | | | |

## 14. Checklist trước khi dùng

- [ ] Đã xác nhận Vector API là incubator, không phải stable hay preview.
- [ ] Dùng đúng JDK 27 và thêm module `jdk.incubator.vector` ở compile/runtime.
- [ ] Không bật `--enable-preview` nếu không dùng một preview feature khác.
- [ ] Species được chọn bằng `SPECIES_PREFERRED` trừ khi có lý do phần cứng rõ ràng.
- [ ] Tất cả vector tham gia cùng phép toán có species tương thích.
- [ ] Offset và vùng đọc/ghi được kiểm tra.
- [ ] Phần dư được xử lý bằng scalar tail hoặc masked load/store.
- [ ] Không ghi lane bị tắt của mask vào mảng đích.
- [ ] Đã kiểm tra độ dài 0, nhỏ hơn vector, chia hết và có phần dư.
- [ ] Đã benchmark với scalar baseline và workload đại diện.
- [ ] Không đưa incubator type vào API công khai lâu dài nếu chưa chấp nhận rủi ro thay đổi.

## Tài liệu tham khảo chính thức

- [JEP 537: Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537)
- [JDK 27 Release Notes — Vector API (Twelfth Incubator)](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html)
- [Vector API Package Summary — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html)
- [FloatVector API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html)
- [VectorSpecies API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html)
- [VectorMask API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorMask.html)
- [Vector API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html)
- [IntVector API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html)
- [Vector API User Guide — Java SE 27](https://docs.oracle.com/en/java/javase/27/core/vector-api.html)

