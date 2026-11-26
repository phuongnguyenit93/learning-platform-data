# Mô hình SIMD, lane, vector và các bài toán phù hợp với xử lý dữ liệu song song

## Phạm vi và phiên bản sử dụng

Bài học thuộc chương **Vector API** của module **JAVA_VERSION_JAVA22**, dành cho việc học những tính năng có mặt ở Java 22 và còn hữu ích trong Java hiện đại. Trọng tâm là hiểu cách một phép toán xử lý nhiều phần tử dữ liệu cùng loại, đọc được các khái niệm lane và vector, rồi nhận diện những đoạn tính toán đáng cân nhắc áp dụng SIMD.

Vector API đã có trong Java 22 dưới dạng module incubator `jdk.incubator.vector`; Java 22 không phải lần đầu API xuất hiện. Có thể đối chiếu nền tảng này tại [module Vector API của Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/jdk.incubator.vector/module-summary.html).

**Mốc đối chiếu của bài là ngày 25/11/2026, với ví dụ dùng JDK 27.** Vector API vẫn là tính năng incubator, ở lần ươm tạo thứ mười hai trong Java 27. Vì vậy, bài sử dụng mô hình và những API cốt lõi đang có trong tài liệu hiện hành, đồng thời giữ rõ trạng thái chưa ổn định của module. Thông tin phiên bản được xác nhận trong [các thay đổi của JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html).

## 1. SIMD giải quyết kiểu song song nào?

SIMD là viết tắt của **Single Instruction, Multiple Data**: một chỉ thị áp dụng cùng loại phép toán lên nhiều phần tử dữ liệu. Chẳng hạn, cần cộng hai dãy số theo từng vị trí:

```java
for (int i = 0; i < a.length; i++) {
    out[i] = a[i] + b[i];
}
```

Ở cấp mã nguồn, vòng lặp mô tả một phép cộng cho mỗi phần tử. Với cách biểu diễn SIMD, ta gom một nhóm phần tử thành vector rồi thực hiện phép cộng theo từng vị trí của cả nhóm.

Giả sử nhóm có bốn phần tử:

```text
Vị trí trong nhóm       0       1       2       3

Vector a             [  3  |    7  |    2  |    9  ]
                        +       +       +       +
Vector b             [ 10  |   20  |   30  |   40  ]
                        ↓       ↓       ↓       ↓
Vector kết quả       [ 13  |   27  |   32  |   49  ]
```

Bốn vị trí này là bốn **lane**. Tất cả cùng thực hiện phép cộng, nhưng mỗi lane làm việc với cặp dữ liệu ở vị trí tương ứng.

Một luồng Java có thể thực hiện các phép toán SIMD trên CPU hỗ trợ. Chương trình không cần tạo bốn luồng chỉ vì có bốn lane. Khi áp dụng lên một mảng dài, luồng đó vẫn lặp qua các nhóm; mỗi nhóm chứa nhiều phần tử hơn so với cách mô tả scalar.

Định nghĩa vector, lane và phép toán theo lane được trình bày trong [Vector của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html).

### SIMD và việc chia công việc cho nhiều luồng

Hai cơ chế này giải quyết những cấp độ song song khác nhau:

| Cơ chế | Đơn vị được chia hoặc xử lý cùng nhau | Ví dụ |
| --- | --- | --- |
| SIMD | Nhiều phần tử cùng kiểu trong một phép toán vector | Cộng đồng thời các cặp số tương ứng. |
| Nhiều luồng trên CPU | Các phần công việc được lập lịch lên nhiều luồng | Chia một ảnh lớn thành các vùng để xử lý. |
| Đồng thời cho công việc chờ I/O | Các tác vụ có thể tiến triển trong khi tác vụ khác chờ | Gọi nhiều dịch vụ rồi tổng hợp phản hồi. |

Có thể kết hợp SIMD với nhiều luồng: mỗi luồng xử lý một đoạn dữ liệu riêng, rồi dùng vector trong đoạn đó. Tuy nhiên, số luồng và số lane là hai đại lượng riêng; tăng chúng không bảo đảm hiệu năng tăng theo tích của hai con số.

Vector API đang xét phục vụ các phép toán vector trên CPU. Các kiến trúc CPU được tài liệu nêu làm ví dụ gồm x64 với AVX và AArch64 với NEON; việc điều khiển tính toán trên GPU cần một cơ chế thực thi khác. Xem mô tả của [module jdk.incubator.vector trong Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html).

## 2. Lane, kiểu phần tử, shape và species

### 2.1. Lane là vị trí chứa một giá trị

Một vector có số lane cố định đối với species của nó. Các lane trong cùng vector có cùng kiểu phần tử, chẳng hạn `int` hoặc `float`. Với `IntVector`, mỗi lane chứa một giá trị `int`.

Định danh lane thường chạy từ `0` đến `L - 1`, trong đó `L` là số lane. Khi tải dữ liệu từ mảng ở offset `i`, lane thứ `k` nhận phần tử `a[i + k]`.

Ví dụ với bốn lane:

```text
Mảng a:       ... a[i]   a[i+1]   a[i+2]   a[i+3] ...
                    │       │        │        │
Vector:         lane 0   lane 1   lane 2   lane 3
```

Lane là vị trí dữ liệu trong mô hình vector; nó không có vòng đời, bộ lập lịch hoặc ngăn xếp lời gọi riêng như một thread.

### 2.2. Shape biểu diễn dung lượng theo bit

**Shape** gắn với kích thước theo bit của vector. Khi biết kích thước đó và kích thước của một phần tử, có thể tính số lane:

```text
Số lane = Kích thước vector theo bit / Kích thước một phần tử theo bit
```

Ví dụ minh họa cho các shape cố định:

| Kiểu phần tử | Số bit mỗi phần tử | Số lane trong 128 bit | Số lane trong 256 bit |
| --- | --- | --- | --- |
| `byte` | 8 | 16 | 32 |
| `short` | 16 | 8 | 16 |
| `int` | 32 | 4 | 8 |
| `long` | 64 | 2 | 4 |
| `float` | 32 | 4 | 8 |
| `double` | 64 | 2 | 4 |

Bảng này là quan hệ kích thước, không phải cam kết máy đang chạy hỗ trợ mọi shape hay mọi phép toán với hiệu năng như nhau. Tài liệu [VectorShape](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorShape.html) khuyến khích mã không phụ thuộc cứng vào một shape vì hỗ trợ của các nền tảng khác nhau.

### 2.3. Species kết hợp kiểu phần tử và shape

**Species** xác định tổ hợp kiểu phần tử với shape, qua đó xác định số lane của vector. Ví dụ:

```java
private static final VectorSpecies<Integer> SPECIES =
        IntVector.SPECIES_PREFERRED;
```

`SPECIES_PREFERRED` chọn species được nền tảng Java hiện tại ưu tiên cho kiểu phần tử đó. Những phép cộng theo lane thông thường cần các vector đầu vào cùng species để từng cặp lane tương ứng có ý nghĩa rõ ràng.

Các truy vấn thường dùng:

| Lời gọi | Ý nghĩa |
| --- | --- |
| `SPECIES.length()` | Số lane. |
| `SPECIES.elementSize()` | Số bit của một phần tử. |
| `SPECIES.vectorBitSize()` | Tổng số bit của vector. |
| `SPECIES.loopBound(n)` | Bội số lớn nhất của số lane không vượt quá `n`. |
| `SPECIES.indexInRange(i, n)` | Mask đánh dấu lane có chỉ số mảng hợp lệ tại offset `i`. |

Hợp đồng của những phương thức này nằm trong [VectorSpecies của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html).

Kiểu generic `Integer` trong `VectorSpecies<Integer>` mô tả loại phần tử của species; các lane của `IntVector` vẫn chứa giá trị primitive `int`. Không cần chuyển mảng đầu vào thành `Integer[]` để dùng API.

## 3. Mô hình tải dữ liệu, tính toán và ghi kết quả

Một đoạn tính toán vector cơ bản thường có ba bước:

1. **Load:** tải một nhóm phần tử từ bộ nhớ vào giá trị vector.
2. **Compute:** thực hiện một hoặc nhiều phép toán vector.
3. **Store:** ghi các lane kết quả về bộ nhớ.

Ví dụ cộng một nhóm phần tử:

```java
IntVector va = IntVector.fromArray(SPECIES, a, i);
IntVector vb = IntVector.fromArray(SPECIES, b, i);
IntVector sum = va.add(vb);
sum.intoArray(out, i);
```

Với `L = SPECIES.length()`, đoạn mã tương ứng với:

```text
out[i + k] = a[i + k] + b[i + k], với k từ 0 đến L - 1
```

`IntVector` biểu diễn một dãy giá trị bất biến. `va.add(vb)` trả về giá trị vector kết quả; phép gọi đó không tự sửa mảng `a` hay làm `va` đổi thành tổng. Việc ghi ra mảng chỉ diễn ra khi gọi thao tác như `intoArray`. Xem mô tả của [IntVector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html).

Một phép gọi API không nhất thiết tương ứng đúng một lệnh máy. JIT và nền tảng quyết định cách thực hiện; khi không thể biên dịch sang lệnh vector thích hợp, API có triển khai scalar mặc định. Vì vậy, hãy phân biệt mô hình dữ liệu ở mã Java với số lệnh hoặc số chu kỳ thực tế trên CPU.

## 4. Ví dụ đầy đủ: cộng hai mảng trên một luồng Java

Lưu mã sau thành `SimdAdditionDemo.java` trong môi trường học có JDK 27. Phương thức nhận ba mảng không `null`, cùng độ dài. Mảng đầu ra được cấp phát ở ngoài phần tính toán.

```java
import java.util.Arrays;
import java.util.Objects;
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

public class SimdAdditionDemo {
    private static final VectorSpecies<Integer> SPECIES =
            IntVector.SPECIES_PREFERRED;

    static void add(int[] a, int[] b, int[] out) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");
        Objects.requireNonNull(out, "out");

        if (a.length != b.length || a.length != out.length) {
            throw new IllegalArgumentException("Các mảng phải cùng độ dài");
        }

        int n = a.length;
        int bound = SPECIES.loopBound(n);
        int i = 0;

        for (; i < bound; i += SPECIES.length()) {
            IntVector va = IntVector.fromArray(SPECIES, a, i);
            IntVector vb = IntVector.fromArray(SPECIES, b, i);
            va.add(vb).intoArray(out, i);
        }

        // Xử lý phần còn lại khi độ dài không chia hết cho số lane.
        for (; i < n; i++) {
            out[i] = a[i] + b[i];
        }
    }

    public static void main(String[] args) {
        int n = 2 * SPECIES.length() + 1;
        int[] a = new int[n];
        int[] b = new int[n];
        int[] out = new int[n];

        Arrays.fill(a, 7);
        Arrays.fill(b, 11);
        add(a, b, out);

        System.out.println("bits=" + SPECIES.vectorBitSize());
        System.out.println("lanes=" + SPECIES.length());
        System.out.println("length=" + n);
        System.out.println("first=" + out[0] + ", last=" + out[n - 1]);
    }
}
```

Biên dịch và chạy bằng công cụ của cùng JDK 27:

```shell
javac --add-modules jdk.incubator.vector SimdAdditionDemo.java
java --add-modules jdk.incubator.vector SimdAdditionDemo
```

`--add-modules` đưa module incubator vào tập module được phân giải. Ví dụ này chỉ dùng Vector API với mảng, nên không cần `--enable-preview` riêng cho API đó. Incubator và preview là hai cơ chế khác nhau; nếu chương trình còn dùng tính năng preview khác thì phải cấu hình tính năng đó riêng. Ý nghĩa của tùy chọn module được mô tả trong [javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) và [java launcher](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html).

Nếu runtime chọn species 256 bit cho `int`, kết quả minh họa là:

```text
bits=256
lanes=8
length=17
first=18, last=18
```

Ba dòng đầu có thể khác giữa các nền tảng. Với cách tạo dữ liệu trong ví dụ, mọi phần tử kết quả đều bằng `18`, bất kể số lane được chọn.

Chương trình gọi `add` trực tiếp từ `main`; nó không tạo thêm tác vụ hay thread. Việc xử lý nhiều lane xảy ra bên trong các phép toán vector khi runtime và phần cứng hỗ trợ. Đây là ví dụ về mô hình thực thi, chưa phải số liệu đo hiệu năng.

## 5. Vì sao phải xử lý phần đuôi của mảng?

Giả sử để minh họa có `n = 10` phần tử và `L = 4` lane:

```text
Chỉ số mảng:   0  1  2  3 | 4  5  6  7 | 8  9
Nhóm xử lý:    vector thứ 1 | vector thứ 2 | đuôi
```

`SPECIES.loopBound(10)` trả về `8` trong trường hợp này. Vòng vector xử lý hai nhóm đủ lane; vòng scalar xử lý hai phần tử còn lại.

Nếu chỉ tăng `i` theo số lane rồi tải một vector đầy đủ ở offset `8`, chương trình sẽ cố đọc cả những phần tử không tồn tại. Bỏ qua phần cuối lại làm kết quả thiếu dữ liệu. Cách tách vòng lặp trong ví dụ bảo đảm những trường hợp sau đều có đường xử lý rõ ràng:

- Mảng rỗng: cả hai vòng đều không chạy.
- Mảng ngắn hơn một vector: phần scalar xử lý toàn bộ.
- Độ dài chia hết cho số lane: không có phần đuôi.
- Độ dài không chia hết: phần đuôi chứa ít hơn `L` phần tử.

Không tự giả định số lane luôn là `4`, `8`, `16`, hoặc luôn là một lũy thừa của hai để viết công thức làm tròn bằng bit. `loopBound` đã cung cấp đúng chức năng đó cho species đang sử dụng.

### Dùng mask cho nhóm cuối

Mask là dãy cờ chọn lane. Có thể thay vòng scalar cuối trong phương thức `add` bằng một nhóm vector có mask. Đoạn sau đặt ngay sau vòng xử lý các nhóm đầy đủ và dùng lại `i`, `n`, `a`, `b`, `out` của phương thức:

```java
if (i < n) {
    var mask = SPECIES.indexInRange(i, n);
    IntVector va = IntVector.fromArray(SPECIES, a, i, mask);
    IntVector vb = IntVector.fromArray(SPECIES, b, i, mask);
    va.add(vb).intoArray(out, i, mask);
}
```

Với hai phần tử còn lại trong nhóm bốn lane, mask có dạng:

```text
Lane:          0      1      2      3
Chỉ số mảng:   8      9     10     11
Mask:        true   true  false  false
```

Những lane không được chọn không đọc các vị trí ngoài mảng ở thao tác load có mask và không ghi chúng ở thao tác store có mask. Mask phải được áp dụng đúng ở thao tác truy cập bộ nhớ; chỉ gắn mask vào phép cộng nhưng vẫn tải đầy đủ từ ngoài biên không giải quyết lỗi truy cập.

Quy tắc chọn lane được mô tả tại [VectorMask](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorMask.html). Hai cách xử lý phần đuôi và ảnh hưởng của mask lên hiệu năng được minh họa trong [tổng quan package Vector API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html).

Không có quy tắc rằng dùng mask luôn nhanh hơn vòng scalar cuối. Lựa chọn phụ thuộc kích thước dữ liệu, phép toán và khả năng của nền tảng. Với phép toán khác phép cộng, cũng cần xét ý nghĩa của lane không hoạt động; không coi giá trị nạp mặc định là phần tử trung hòa cho mọi phép toán hoặc reduction.

## 6. Phép toán theo lane, reduction và di chuyển giữa các lane

### 6.1. Lane-wise: cùng phép toán, các vị trí độc lập

Phép toán theo lane áp dụng cùng công thức cho từng vị trí. Những ví dụ điển hình gồm:

```text
Cộng:                  out[k] = a[k] + b[k]
Nhân với hệ số:        out[k] = a[k] * scale
Biến đổi tuyến tính:   out[k] = a[k] * scale + bias
So sánh:               mask[k] = a[k] > threshold
```

Một giá trị scalar như `scale` có thể được broadcast, tức được dùng như cùng một giá trị ở mọi lane. Chọn dữ liệu theo điều kiện có thể biểu diễn bằng mask và thao tác blend. Các toán tử và nhóm phép toán được định nghĩa trong [VectorOperators](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorOperators.html).

Ví dụ khái niệm cho việc giữ số dương và đặt số còn lại về `0`:

```text
Dữ liệu:           [ -3 |  5 | -1 |  8 ]
Điều kiện > 0:     [  F |  T |  F |  T ]
Kết quả chọn:      [  0 |  5 |  0 |  8 ]
```

Mask cho phép biểu diễn điều kiện trên từng lane, nhưng không biến mỗi lane thành một tác vụ tự do chạy một luồng điều khiển dài khác nhau. Những nhánh phức tạp với nhiều lời gọi và tác động bên ngoài thường khó chuyển thành chuỗi phép toán vector hiệu quả.

### 6.2. Reduction: gom nhiều lane thành một kết quả

Nếu muốn tổng của mọi phần tử, kết quả cần gom dữ liệu giữa các lane:

```text
Vector:        [ 3 | 7 | 2 | 9 ]
                    cộng gộp
                       ↓
Scalar:               21
```

Reduction cần kết hợp các giá trị, nên có chi phí và ràng buộc khác phép cộng hai vector theo từng vị trí. Trong một thuật toán tổng, có thể tích lũy nhiều nhóm vào vector rồi mới giảm thành scalar, thay vì đọc từng lane ra và cộng ở mỗi vòng.

Với `float` và `double`, thay đổi thứ tự cộng có thể thay đổi kết quả làm tròn. Một phép tổng vector không mặc nhiên giữ kết quả giống từng bit với vòng lặp scalar cộng từ trái sang phải. Tài liệu [FloatVector.reduceLanes](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html) nêu rõ thứ tự áp dụng `ADD` và `MUL` trong reduction có thể thay đổi.

### 6.3. Shuffle: sắp xếp lại vị trí

Một số thuật toán cần chuyển dữ liệu từ lane này sang lane khác:

```text
Trước:   [ 10 | 20 | 30 | 40 ]
Sau:     [ 30 | 10 | 40 | 20 ]
```

Vector API có cơ chế như `VectorShuffle` để mô tả việc chọn lane nguồn. Những thao tác này hữu ích cho việc tổ chức lại dữ liệu, nhưng số bước cần thực hiện và chi phí phụ thuộc phần cứng. Hợp đồng chọn chỉ số lane nguồn nằm trong [VectorShuffle](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorShuffle.html).

Một thuật toán phải shuffle liên tục hoặc truy cập dữ liệu phân tán có thể tốn nhiều công di chuyển dữ liệu hơn phần phép toán số học mà SIMD giúp tiết kiệm.

## 7. Những bài toán phù hợp với SIMD

Ứng viên thuận lợi thường có dữ liệu cùng kiểu, số lượng đủ lớn và một công thức được lặp lại trên nhiều phần tử. Việc truy cập liên tiếp vào mảng primitive giúp phần tính toán có cấu trúc đều đặn.

| Nhóm bài toán | Phần có thể áp dụng SIMD | Điều cần xem xét |
| --- | --- | --- |
| Biến đổi tín hiệu hoặc chuỗi mẫu số | Nhân hệ số, cộng độ lệch, trộn hai nguồn mẫu | Độ chính xác và khả năng bị giới hạn bởi truy cập bộ nhớ. |
| Xử lý ảnh trong bộ đệm pixel | Áp dụng công thức cho nhiều pixel hoặc kênh | Cách bố trí kênh, miền giá trị và chuyển kiểu. |
| Tính khoảng cách giữa các dãy số | Trừ, bình phương từng cặp rồi reduction | Chi phí reduction và sai số số thực. |
| Tích vô hướng của các vector số học | Nhân các cặp phần tử rồi cộng gộp | Thứ tự cộng và yêu cầu chính xác của thuật toán. |
| Quét dữ liệu theo ngưỡng | So sánh nhiều phần tử rồi đếm các lane đạt điều kiện | Đếm khác với xây dựng danh sách đầu ra có độ dài biến thiên. |
| Các kernel trong xử lý ma trận | Nhiều phép nhân, cộng trên các khối dữ liệu | Cần tổ chức khối và tái sử dụng dữ liệu, không chỉ đổi từng dòng sang API. |
| Biến đổi dữ liệu bit hoặc số nguyên | Những phép bitwise và số học lặp đều | Kiểu có dấu, tràn số và phép toán được CPU hỗ trợ. |

Đây là những ứng viên để phân tích và đo, không phải danh sách cam kết tăng tốc. Ví dụ, cộng hai mảng rất đều đặn nhưng có thể bị giới hạn bởi băng thông bộ nhớ; một kernel số học phức tạp hơn lại có cơ hội tận dụng thêm năng lực tính toán.

Trong xử lý ảnh, giá trị kênh 8 bit thường được hiểu trong miền `0..255`, trong khi `byte` của Java có dấu. Nếu thuật toán cần cộng rồi chặn miền, phải chọn cách diễn giải, mở rộng và thu hẹp kiểu phù hợp; cộng trực tiếp mọi thứ trong `ByteVector` không tự mang ý nghĩa bão hòa về miền màu.

## 8. Các trường hợp cần thuật toán khác hoặc ít phù hợp

### 8.1. Phụ thuộc vào kết quả vừa tính ở phần tử trước

Vòng lặp sau có phụ thuộc tuần tự:

```java
for (int i = 1; i < values.length; i++) {
    values[i] = values[i - 1] + input[i];
}
```

`values[i]` cần kết quả mới của `values[i - 1]`. Không thể thay nó bằng một phép cộng vector theo lane đơn giản mà vẫn giữ nguyên quan hệ đó.

Một số bài toán như prefix sum có thuật toán song song hoặc thuật toán vector riêng. Muốn khai thác chúng phải tổ chức lại cách tính và xử lý quan hệ giữa các nhóm, thay vì chỉ đổi kiểu biến trong vòng lặp ban đầu.

### 8.2. Dữ liệu phân tán và cấu trúc nhiều đối tượng

Một danh sách liên kết hoặc đồ thị đối tượng có nhiều bước đi theo tham chiếu. Phần tử tiếp theo cần đọc có thể phụ thuộc dữ liệu vừa lấy được; việc gom nhóm đủ lane vì thế khó hơn duyệt mảng liên tiếp.

Với dữ liệu điểm hai chiều, nếu kernel chỉ cần tọa độ `x`, hai mảng `float[] x` và `float[] y` có thể thuận tiện hơn cho việc tải nhiều giá trị `x` liên tiếp. Tuy nhiên, chuyển một mô hình đối tượng sẵn có sang dạng mảng cũng có chi phí. Chỉ thay bố cục khi lợi ích tính toán và tái sử dụng dữ liệu bù được phần chuyển đổi đó.

### 8.3. Khối dữ liệu nhỏ, công việc chủ yếu chờ hoặc có tác động bên ngoài

Nếu đầu vào chỉ có vài phần tử, phần chuẩn bị và xử lý đuôi có thể chiếm phần lớn thời gian. Nếu tác vụ chủ yếu đợi mạng hoặc cơ sở dữ liệu, tăng tốc vài phép cộng không tác động nhiều lên thời gian chờ.

Một vòng lặp gửi email, ghi log hoặc thực hiện giao dịch cho mỗi phần tử có những tác động và hợp đồng riêng. Vector API không cung cấp một cách tổng quát để biến các lời gọi nghiệp vụ đó thành các lane SIMD. Khi đánh giá, hãy tìm kernel dữ liệu thuần bên trong luồng xử lý, nếu có.

### 8.4. Lọc hoặc ghi đầu ra có vị trí thay đổi

So sánh nhiều phần tử để tạo mask là công việc đều đặn. Từ mask đó tạo một mảng chỉ chứa phần tử đạt điều kiện cần thêm bước nén dữ liệu và tính vị trí ghi. Vì vậy, một vòng `filter` không luôn tương đương một phép so sánh vector duy nhất.

Tương tự, nhiều lane muốn cập nhật cùng một vị trí đầu ra có thể tạo xung đột dữ liệu. Việc chọn scatter hoặc thay thuật toán phải dựa vào hợp đồng cụ thể; không suy từ tính độc lập của các giá trị đầu vào rằng mọi phép ghi đều độc lập.

## 9. Tính đúng đắn của dữ liệu vẫn quyết định thiết kế

**Số nguyên vẫn có miền giá trị hữu hạn.** Phép cộng `int` trong ví dụ không tự mở rộng sang `long` khi tổng vượt miền `int`. Nếu yêu cầu nghiệp vụ cần tổng lớn hơn, phải thiết kế kiểu dữ liệu và phép tính thích hợp cho cả phần vector lẫn phần scalar.

**Số thực cần hợp đồng về độ chính xác.** Những thuật toán reduction có thể thay đổi thứ tự phép tính; việc dùng fused multiply-add thay chuỗi nhân rồi cộng cũng có thể thay đổi làm tròn. Cần xác định ứng dụng chấp nhận sai số nào và cách xử lý `NaN`, vô cực hoặc số không có dấu khi chúng liên quan đến dữ liệu.

**Bố cục và quyền sở hữu mảng cần rõ ràng.** Ví dụ đầy đủ không có offset, và mỗi vị trí chỉ phụ thuộc hai vị trí đầu vào tương ứng. Nếu mở rộng sang những đoạn dữ liệu chồng lấn, hoặc một nhóm ghi vào dữ liệu mà nhóm sau sẽ đọc, phải xét lại phụ thuộc bộ nhớ trước khi áp dụng cùng cách tính.

**Lane và thread là hai trách nhiệm khác nhau.** SIMD không tự bảo vệ một mảng bị luồng khác sửa đồng thời. Nếu kết hợp nhiều luồng, cần chia vùng đầu ra và xác định rõ dữ liệu đầu vào nào chỉ được đọc trong thời gian tính toán.

## 10. Đánh giá hiệu năng trước khi chọn cách triển khai

### 10.1. Nhiều lane không đồng nghĩa nhanh hơn đúng số lần đó

Vector tám lane có khả năng biểu diễn tám phép toán theo vị trí, nhưng toàn bộ công việc vẫn có các phần:

- Tải hai nhóm dữ liệu đầu vào.
- Thực hiện phép toán.
- Ghi nhóm kết quả.
- Điều khiển vòng lặp và xử lý phần đuôi.
- Thực hiện các bước chuyển kiểu, shuffle hoặc reduction nếu thuật toán cần.

Với hai mảng `int` đầu vào và một mảng `int` đầu ra, mỗi phần tử kết quả tương ứng về mặt dữ liệu với hai lần đọc 4 byte và một lần ghi 4 byte. Lưu lượng thực qua cache và RAM còn phụ thuộc hệ thống bộ nhớ. Khi việc đưa dữ liệu tới CPU là giới hạn chính, thêm lane có thể không giúp tốc độ tăng tương ứng.

Tăng tốc kernel cũng khác tăng tốc toàn yêu cầu. Ví dụ giả định một kernel chiếm `20%` thời gian ban đầu, phần còn lại giữ nguyên và kernel nhanh gấp `4` lần:

```text
Thời gian tương đối mới = 0,80 + 0,20 / 4 = 0,85
Mức tăng tốc toàn bộ    = 1 / 0,85 ≈ 1,18 lần
```

Đây là phép tính minh họa theo các giả định đã nêu, không phải kết quả benchmark của Vector API.

### 10.2. So sánh với một vòng scalar có chất lượng

HotSpot có khả năng tự vector hóa một số vòng lặp scalar. Do đó, mã nguồn `for` thông thường cũng có thể được biên dịch thành SIMD. Vector API cho phép biểu diễn phép tính vector trực tiếp hơn, nhưng hiệu quả thực tế cần so với cách triển khai scalar tốt trên cùng runtime. Hai hướng được trình bày trong bài nói của kỹ sư Oracle tại [SIMD Vectors in the HotSpot JVM](https://inside.java/2026/07/02/simd-vectors-hotspot-jvm/).

Chọn `SPECIES_PREFERRED` là cách viết thích nghi với nền tảng, không thay thế việc đo kernel cụ thể. Không có một mức phần trăm tăng tốc dùng chung cho mọi CPU, JDK, kiểu dữ liệu và phép toán.

### 10.3. Đo phần tính toán với điều kiện có thể so sánh

Khi cần quyết định tối ưu hóa, có thể dùng [JMH của OpenJDK](https://github.com/openjdk/jmh) để xây dựng benchmark cho JVM. Những điều kiện cần làm rõ gồm:

| Điều kiện | Mục đích |
| --- | --- |
| Cùng đầu vào và hợp đồng kết quả | So sánh cùng công việc. |
| Có giai đoạn warmup và nhiều lần đo | Quan sát hành vi sau khi runtime có cơ hội tối ưu. |
| Kết quả được tiêu thụ đúng cách | Tránh đo công việc bị trình biên dịch loại bỏ vì không ai dùng. |
| Tách khởi tạo, in console và I/O khỏi kernel khi cần | Xác định chi phí thực sự đang đo. |
| Nhiều kích thước dữ liệu thực tế | Nhìn được ảnh hưởng của phần đuôi, cache và băng thông. |
| Ghi JDK, CPU, cấu hình và số lane | Giúp người khác hiểu giới hạn của kết quả. |

Một lần gọi `System.nanoTime()` quanh chương trình ví dụ ngắn không đủ để kết luận về tốc độ SIMD. Ví dụ trong bài chủ yếu giúp quan sát species, nhóm đủ lane và phần đuôi; quyết định triển khai cần dựa vào kernel có vai trò rõ ràng trong thời gian xử lý thực tế.
