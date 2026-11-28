# VectorSpecies, VectorShape và kiểu phần tử

*Tình trạng API được đối chiếu đến ngày 27/11/2026.*

Vector API biểu diễn phép tính SIMD (Single Instruction, Multiple Data): một lệnh vector xử lý nhiều giá trị cùng kiểu trong các lane của một vector. Ba khái niệm quyết định cách vector được bố trí là **kiểu phần tử** (element type), **hình dạng vector** (vector shape) và **species**.

- Kiểu phần tử cho biết mỗi lane chứa kiểu dữ liệu nào, ví dụ `int` hoặc `float`.
- Vector shape cho biết tổng độ rộng của vector tính bằng bit.
- Vector species là tổ hợp duy nhất của kiểu phần tử và shape; nó xác định số lane và loại vector được tạo ra.

Trong Java 26, Vector API là incubator lần thứ mười một theo JEP 529. Java 27 tiếp tục incubator lần thứ mười hai theo JEP 537. API nằm trong module `jdk.incubator.vector`, chưa phải API ổn định của Java SE. Vì vậy, ví dụ phải bật module tường minh và không được nhầm cờ incubator với `--enable-preview`.

## 1. Vector gồm các lane có kiểu phần tử cố định

Một vector là một dãy có số lane cố định. Mỗi lane chứa một giá trị nguyên thủy thuộc cùng một kiểu phần tử. Các phép toán theo lane như cộng, nhân hoặc so sánh áp dụng phép toán tương ứng lên từng cặp lane.

Vector API hiện hỗ trợ sáu kiểu phần tử:

| Kiểu phần tử (ETYPE) | Vector class | Kích thước mỗi lane |
|---|---|---:|
| `byte` | `ByteVector` | 8 bit |
| `short` | `ShortVector` | 16 bit |
| `int` | `IntVector` | 32 bit |
| `long` | `LongVector` | 64 bit |
| `float` | `FloatVector` | 32 bit |
| `double` | `DoubleVector` | 64 bit |

Không có vector class cho `boolean` hoặc `char`. `VectorMask` dùng boolean để biểu diễn lane được chọn hay bị bỏ qua, nhưng mask không phải kiểu phần tử của vector dữ liệu.

Trong khai báo generic, kiểu `E` là wrapper tương ứng của kiểu nguyên thủy. Ví dụ `Vector<Integer>` có lane chứa giá trị `int`, không phải mỗi lane là một object `Integer`. Vector API tránh boxing từng phần tử khi thực hiện phép toán vector.

## 2. VectorShape biểu diễn tổng độ rộng của vector

`VectorShape` là enum chọn định dạng vector theo tổng số bit. Java 27 cung cấp các shape sau:

| Shape | Tổng độ rộng |
|---|---:|
| `S_64_BIT` | 64 bit |
| `S_128_BIT` | 128 bit |
| `S_256_BIT` | 256 bit |
| `S_512_BIT` | 512 bit |
| `S_Max_BIT` | Độ rộng lớn nhất mà nền tảng hỗ trợ |

Tên `S_Max_BIT` có chữ `Max` viết hoa chữ đầu, đúng như enum trong API. Shape không phải là số lane; nó chỉ xác định tổng dung lượng bit của vector.

Một shape cụ thể không nhất thiết được hỗ trợ hoặc tăng tốc trên mọi CPU. Ví dụ, mã chọn vector 512 bit có thể không được biên dịch thành lệnh vector 512 bit trên máy chỉ có hỗ trợ 256 bit; implementation có thể dùng đường thực thi scalar. Một số tổ hợp kiểu và shape cũng có thể không khả dụng.

Có hai cách truy vấn shape theo nền tảng:

- `VectorShape.preferredShape()`: shape ưu tiên chung cho các kiểu lane. Shape này chọn độ rộng lớn nhất có thể mà vẫn hỗ trợ tất cả các kiểu lane từ `byte` đến `double`.
- `VectorShape.largestShapeFor(float.class)`: shape lớn nhất được hỗ trợ cho một kiểu lane cụ thể. Shape lớn nhất của một kiểu có thể rộng hơn shape ưu tiên chung.

Với code cần chạy trên nhiều CPU, nên để nền tảng chọn shape thay vì mặc định rằng mọi máy đều có AVX-512 hoặc một độ rộng cố định khác.

## 3. VectorSpecies kết hợp kiểu phần tử và shape

`VectorSpecies<E>` mô tả tất cả vector có cùng kiểu phần tử và cùng shape. Mỗi tổ hợp ETYPE + shape tạo thành một species duy nhất. Species xác định:

- Kiểu vector cụ thể, ví dụ `IntVector` hoặc `FloatVector`.
- Tổng độ rộng vector, qua `vectorBitSize()`.
- Kích thước lane, qua `elementSize()`.
- Số lane, qua `length()`.
- Shape, qua `vectorShape()`.

Trong generic, `E` là kiểu wrapper, nhưng đối số `elementType` của factory phải là class mirror của kiểu nguyên thủy: dùng `float.class`, `int.class`, không dùng `Float.class` hoặc `Integer.class`. `VectorSpecies` là sealed interface do module cung cấp; ứng dụng nên lấy species qua hằng của vector class hoặc các factory, không tự triển khai interface này.

Ví dụ, một vector có shape 256 bit và lane kiểu `int` chứa 8 lane. Với cùng shape 256 bit nhưng lane kiểu `double`, vector chỉ chứa 4 lane.

Công thức luôn đúng:

\[
\text{VLENGTH} = \frac{\text{vectorBitSize}}{\text{elementSize}}
\]

Trong đó `VLENGTH` chính là số lane của species. Tổng độ rộng, số lane và kiểu phần tử ràng buộc lẫn nhau; không thể tùy ý đổi một thành phần mà bỏ qua hai thành phần còn lại.

### Ví dụ số lane theo shape

| Shape | `byte` | `short` | `int` / `float` | `long` / `double` |
|---|---:|---:|---:|---:|
| 64 bit | 8 | 4 | 2 | 1 |
| 128 bit | 16 | 8 | 4 | 2 |
| 256 bit | 32 | 16 | 8 | 4 |
| 512 bit | 64 | 32 | 16 | 8 |

Bảng này là phép tính theo dung lượng bit của từng shape. Nó không khẳng định CPU hiện tại có lệnh phần cứng tương ứng cho mọi shape.

## 4. Chọn species phù hợp với nền tảng

Cách thông dụng nhất là dùng species ưu tiên từ vector class tương ứng:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

public class PreferredSpecies {
    static final VectorSpecies<Float> FLOATS =
            FloatVector.SPECIES_PREFERRED;

    static final VectorSpecies<Integer> INTS =
            IntVector.SPECIES_PREFERRED;
}
```

Các species ưu tiên của các kiểu phần tử khác nhau có cùng shape cơ sở. Điều này giúp thuật toán có thể chuyển đổi/reinterpret giữa các kiểu lane mà không vô tình thay đổi tổng dung lượng vector.

Cũng có thể lấy species qua factory:

```java
VectorSpecies<Float> preferred =
        VectorSpecies.ofPreferred(float.class);

VectorSpecies<Float> largestForFloat =
        VectorSpecies.ofLargestShape(float.class);
```

`ofPreferred()` chọn shape chung được nền tảng ưu tiên cho mọi kiểu lane. `ofLargestShape()` chọn shape lớn nhất riêng cho kiểu lane được truyền vào. Dùng `ofPreferred()` thường là lựa chọn tốt hơn cho thuật toán tổng quát, đặc biệt khi cần reinterpret vector giữa nhiều kiểu phần tử.

### Chọn shape tường minh

Khi thuật toán có lý do cụ thể để dùng một độ rộng cố định, có thể tạo species trực tiếp:

```java
import jdk.incubator.vector.VectorShape;
import jdk.incubator.vector.VectorSpecies;

VectorSpecies<Float> floats256 =
        VectorSpecies.of(float.class, VectorShape.S_256_BIT);
```

Nếu tổ hợp kiểu phần tử và shape không có species tương ứng, factory có thể ném `IllegalArgumentException`. Ngay cả khi tạo được species, không nên mặc định rằng CPU sẽ tăng tốc shape đó bằng lệnh SIMD. Chỉ chọn shape cố định khi đã kiểm soát nền tảng triển khai hoặc đã có phương án kiểm tra và xử lý trường hợp không phù hợp.

## 5. Đọc thông tin từ species

Có thể kiểm tra kiểu lane, shape và số lane trước khi xử lý dữ liệu:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public class SpeciesInfo {
    static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    public static void main(String[] args) {
        System.out.println("Element type: "
                + SPECIES.elementType().getTypeName());
        System.out.println("Shape: " + SPECIES.vectorShape());
        System.out.println("Vector bits: " + SPECIES.vectorBitSize());
        System.out.println("Vector bytes: " + SPECIES.vectorByteSize());
        System.out.println("Element bits: " + SPECIES.elementSize());
        System.out.println("Lane count: " + SPECIES.length());
    }
}
```

Với species của `FloatVector`, `elementType()` trả về class mirror của kiểu nguyên thủy `float`; generic parameter vẫn là `Float`. Đây là lý do code có thể khai báo `VectorSpecies<Float>` nhưng dữ liệu thực trong lane không bị boxing.

Các phương thức hữu ích khác:

| Phương thức | Ý nghĩa |
|---|---|
| `elementType()` | Class mirror của kiểu lane nguyên thủy |
| `elementSize()` | Kích thước một lane, tính bằng bit |
| `length()` | Số lane của species |
| `vectorShape()` | Shape của vector |
| `vectorBitSize()` | Tổng độ rộng, tính bằng bit |
| `vectorByteSize()` | Tổng độ rộng, tính bằng byte |
| `loopBound(length)` | Bội số lớn nhất của số lane không vượt quá chiều dài dữ liệu |
| `indexInRange(offset, limit)` | Tạo mask để chọn những lane có index nằm trong phạm vi |

## 6. Đổi kiểu lane hoặc shape

Một species có thể được biến đổi thành species khác bằng hai phương thức:

- `withLanes(newType)`: giữ nguyên shape, thay kiểu phần tử.
- `withShape(newShape)`: giữ nguyên kiểu phần tử, thay shape.

Ví dụ:

```java
VectorSpecies<Float> floats =
        FloatVector.SPECIES_PREFERRED;

// Cùng shape, đổi lane từ float sang int.
VectorSpecies<Integer> ints =
        floats.withLanes(int.class);

// Cùng kiểu float, yêu cầu shape 256 bit.
VectorSpecies<Float> floats256 =
        floats.withShape(VectorShape.S_256_BIT);
```

Các phương thức này tìm species tương ứng. Nếu tổ hợp mới không hợp lệ hoặc không khả dụng, chúng có thể ném `IllegalArgumentException`. Việc đổi species không tự chuyển đổi dữ liệu của vector hiện có; nó chỉ tạo mô tả định dạng khác. Muốn chuyển đổi hoặc reinterpret dữ liệu, cần dùng các API chuyển đổi/reinterpret của vector và tuân thủ quy tắc số lane, shape và kiểu phần tử.

## 7. Các phép toán cần cùng species

Các phép toán theo lane thường yêu cầu mọi vector đầu vào có cùng shape và cùng số lane, tức là cùng species. Ví dụ, hai vector `FloatVector` có độ rộng khác nhau không thể tùy ý cộng từng lane với nhau. Tương tự, vector `IntVector` và `FloatVector` không cùng ETYPE dù có cùng tổng độ rộng.

Có thể kiểm tra tính tương thích tường minh bằng `check()`:

```java
FloatVector a = ...;
FloatVector b = ...;

a.check(b.species());
```

Trong code thực tế, cách đơn giản nhất là dùng cùng một hằng `SPECIES` khi tạo tất cả vector tham gia một phép toán. Điều này tránh nhầm lẫn về lane count và định dạng dữ liệu.

Species là metadata mô tả vector, không phải chính dữ liệu vector. Một species có thể được dùng để tạo nhiều vector có giá trị lane khác nhau nhưng cùng ETYPE và shape.

## 8. Dùng species để xử lý mảng có độ dài bất kỳ

Một ví dụ thực tế là cộng hai mảng `float`. Species ưu tiên quyết định số phần tử được xử lý trong mỗi vòng vector. Phần dư ở cuối mảng được xử lý bằng vòng scalar:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public class VectorArrayAdd {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    static void add(float[] a, float[] b, float[] result) {
        if (a.length != b.length || a.length != result.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }

        int i = 0;
        int bound = SPECIES.loopBound(a.length);

        for (; i < bound; i += SPECIES.length()) {
            FloatVector va = FloatVector.fromArray(SPECIES, a, i);
            FloatVector vb = FloatVector.fromArray(SPECIES, b, i);

            va.add(vb).intoArray(result, i);
        }

        // Xử lý phần tử còn lại chưa đủ một vector.
        for (; i < a.length; i++) {
            result[i] = a[i] + b[i];
        }
    }
}
```

`loopBound()` trả về vị trí kết thúc lớn nhất mà số phần tử từ đầu mảng là bội số của số lane. Nhờ vậy, vòng vector chỉ đọc các vùng dữ liệu đầy đủ. Vòng scalar xử lý phần đuôi còn lại mà không truy cập vượt giới hạn mảng.

Một cách khác là dùng mask từ `SPECIES.indexInRange(i, length)` để xử lý cả vòng cuối bằng vector. Mask giúp bảo đảm lane vượt ngoài mảng không được đọc hoặc ghi. Tuy nhiên, dùng mask cho mọi vòng có thể kém tối ưu hơn cách tách phần đuôi scalar trên mảng lớn; hãy đo trên workload thực tế.

Không tự tính giới hạn vòng lặp bằng giả định rằng số lane luôn là lũy thừa của hai. `S_Max_BIT` có thể mang độ rộng phụ thuộc nền tảng; dùng `loopBound()` để tránh phụ thuộc giả định về số lane.

Không nên giả định độ rộng của `S_Max_BIT` luôn là 128, 256 hoặc 512 bit. API cho phép shape có độ rộng phụ thuộc nền tảng; tài liệu nêu cả trường hợp giả định 384 bit. Vì vậy, biểu thức bit-mask dựa trên giả định số lane là lũy thừa của hai có thể sai trên một số nền tảng.

## 9. Các lưu ý về hiệu năng và tính di động

Vector API mô tả phép tính theo lane; JIT compiler quyết định cách ánh xạ sang lệnh SIMD phù hợp tại runtime. API có đường thực thi scalar mặc định khi không thể biên dịch thao tác thành lệnh vector phần cứng. Vì thế, code có thể vẫn chạy đúng trên nền tảng thiếu SIMD nhưng không nhất thiết nhanh hơn code scalar.

Các nguyên tắc quan trọng:

- Ưu tiên `SPECIES_PREFERRED` hoặc `VectorSpecies.ofPreferred()` cho thuật toán tổng quát.
- Chỉ chọn `S_256_BIT` hoặc `S_512_BIT` khi có yêu cầu cụ thể và đã kiểm tra CPU/JDK mục tiêu.
- Giữ species trong biến cục bộ, tham số hoặc field `static final`; tài liệu API lưu ý lưu species trong field thông thường hoặc phần tử mảng có thể gây chi phí hiệu năng.
- Các kiểu `Vector`, `VectorMask`, `VectorShuffle` và `VectorSpecies` có semantics value-based. Không dựa vào identity so sánh bằng `==`; dùng `equals()` hoặc API kiểm tra tương ứng.
- Dùng cùng species cho các vector tham gia phép toán lane-wise.
- Đo cả trường hợp dữ liệu nhỏ, dữ liệu lớn, phần đuôi không đủ một vector và nhiều kiến trúc CPU.
- Không giả định vector rộng hơn luôn nhanh hơn. Chi phí chuyển đổi shape, tải/ghi bộ nhớ, mask và khả năng hỗ trợ phần cứng đều ảnh hưởng kết quả.

Vector API không tự động làm mọi vòng lặp nhanh hơn. Nó phù hợp nhất với workload số học trên lượng dữ liệu lớn, phép toán độc lập theo lane và có thể giảm chi phí nhánh hoặc tận dụng SIMD. Với tác vụ bị giới hạn bởi bộ nhớ, I/O hoặc phụ thuộc dữ liệu tuần tự, lợi ích có thể thấp.

## 10. Trạng thái incubator và cách bật module

Vector API không phải preview feature. Đây là incubator module có tên `jdk.incubator.vector`.

| JDK | JEP | Trạng thái |
|---|---|---|
| Java 26 | JEP 529 | Eleventh Incubator |
| Java 27 | JEP 537 | Twelfth Incubator |

JDK 27 tiếp tục incubate Vector API mà không có thay đổi API đáng kể so với Java 26. Tuy nhiên, trạng thái incubator vẫn có nghĩa API có thể thay đổi hoặc bị loại bỏ trong bản JDK sau. Không dùng `--enable-preview` chỉ để bật Vector API; cần thêm module.

Biên dịch và chạy với JDK 27:

```bash
javac --add-modules jdk.incubator.vector -d out VectorArrayAdd.java
java --add-modules jdk.incubator.vector -cp out VectorArrayAdd
```

Nếu dùng đồng thời một tính năng ngôn ngữ/API preview khác trong cùng chương trình, khi đó mới cần bật `--enable-preview` riêng cho preview feature đó. Hai cơ chế có mục đích khác nhau.

Khi nâng cấp từ JDK 26 lên JDK 27, vẫn cần kiểm tra lại API specification, module path, compiler và runtime. Đừng đưa incubator API vào hợp đồng public lâu dài của thư viện nếu chưa chấp nhận chi phí sửa đổi khi API thay đổi.

## 11. Khi nào nên dùng?

Nên cân nhắc Vector API khi:

- Có lượng lớn dữ liệu số cùng kiểu cần xử lý theo cùng một phép toán.
- Các phần tử ở mỗi vị trí độc lập, ví dụ cộng, nhân, clamp hoặc so sánh hai mảng.
- Workload đủ lớn để chi phí thiết lập vector không lấn át lợi ích.
- Ứng dụng có thể kiểm soát JDK và chấp nhận module incubator.
- Có benchmark trên các CPU triển khai thực tế để xác nhận lợi ích.

Không nên chọn Vector API chỉ vì muốn thay một vòng lặp scalar ngắn. Hãy bắt đầu từ thuật toán và dữ liệu, chọn species ưu tiên, xử lý phần đuôi an toàn, rồi benchmark với code scalar tương đương. Nếu ứng dụng yêu cầu API ổn định lâu dài và không thể chấp nhận thay đổi incubator, chưa nên tạo phụ thuộc production trực tiếp vào module này.

## Tài liệu tham chiếu

1. [Oracle Java SE 27 API – Vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html)
2. [Oracle Java SE 27 API – VectorSpecies](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html)
3. [Oracle Java SE 27 API – VectorShape](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorShape.html)
4. [Oracle Java SE 27 API – Package jdk.incubator.vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html)
5. [Oracle Java SE 26 API – VectorSpecies](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html)
6. [Oracle Java SE 26 API – VectorShape](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorShape.html)
7. [JEP 529 – Vector API (Eleventh Incubator, Java 26)](https://openjdk.org/jeps/529)
8. [JEP 537 – Vector API (Twelfth Incubator, Java 27)](https://openjdk.org/jeps/537)
9. [Oracle – Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)

