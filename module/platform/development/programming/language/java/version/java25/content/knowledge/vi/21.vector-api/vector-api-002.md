# Mô hình vector, species, lane và mask cho xử lý dữ liệu song song

> **Chương:** Vector API  
> **Phạm vi:** Vector API trong JDK 25, tiếp tục được incubate ở JDK 26 và JDK 27.  
> **Mục tiêu:** Hiểu mô hình SIMD, cách `VectorSpecies` xác định định dạng vector, cách dữ liệu được chia thành lane và cách `VectorMask` điều khiển phép tính theo từng lane.

## 1. Vector API giải quyết bài toán nào?

Nhiều chương trình xử lý một lượng lớn phần tử độc lập theo cùng một công thức: cộng hai mảng số, nhân từng pixel, chuẩn hóa tín hiệu, tính điểm cho nhiều bản ghi hoặc lọc dữ liệu số. Cách viết scalar truyền thống xử lý từng phần tử một:

~~~java
for (int i = 0; i < a.length; i++) {
    result[i] = a[i] + b[i];
}
~~~

Vòng lặp này dễ đọc và thường được JIT compiler tối ưu. Tuy nhiên, nếu phần cứng có các thanh ghi SIMD (Single Instruction, Multiple Data), CPU có thể thực hiện cùng một phép toán trên nhiều phần tử trong một lệnh vector. Vector API cho phép lập trình viên diễn đạt rõ phép tính theo nhóm lane để HotSpot có cơ hội sinh mã SIMD phù hợp.

Ví dụ, một vector 256 bit chứa các lane `int` có thể có 8 lane, vì mỗi `int` chiếm 32 bit. Phép cộng vector áp dụng cùng một phép cộng cho cả 8 cặp lane tương ứng.

~~~mermaid
flowchart LR
    A["A: [a0, a1, a2, a3]"] --> C["Vector add"]
    B["B: [b0, b1, b2, b3]"] --> C
    C --> D["R: [a0+b0, a1+b1, a2+b2, a3+b3]"]
~~~

Vector API phù hợp với dữ liệu có cấu trúc và phép toán có thể thực hiện độc lập trên nhiều phần tử. Nó không tự chia công việc thành nhiều Java thread. SIMD là song song ở cấp lệnh và thanh ghi của CPU; parallelism theo thread là một lớp khác và có thể kết hợp riêng khi bài toán cần.

### Những tình huống có thể hưởng lợi

- Xử lý ảnh, video và pixel.
- Tín hiệu số, audio và phép biến đổi dữ liệu.
- Tính toán ma trận hoặc vector số học.
- Phân tích dữ liệu số theo batch.
- Mã hóa, checksum hoặc các phép toán trên buffer phù hợp.
- Một số bước tiền xử lý trong machine learning và mô phỏng.

Không phải mọi vòng lặp đều phù hợp. Các thuật toán có nhánh phức tạp, phụ thuộc dữ liệu giữa các vòng lặp, truy cập bộ nhớ rời rạc hoặc bị giới hạn bởi I/O có thể không hưởng lợi đáng kể.

## 2. Trạng thái hiện tại: Vector API vẫn là incubating module

Vector API được phát triển qua nhiều vòng incubator. Theo các JEP và release notes hiện hành:

| JDK | JEP | Trạng thái |
|---|---|---|
| Java 25 | JEP 508 | Vector API — Tenth Incubator |
| Java 26 | JEP 529 | Vector API — Eleventh Incubator |
| Java 27 | JEP 537 | Vector API — Twelfth Incubator |

Tại ngày 27-11-2026, Vector API vẫn là **incubating API**, chưa trở thành Java SE API ổn định. JDK 27 tiếp tục đưa API vào incubator lần thứ mười hai. API có thể thay đổi hoặc bị loại bỏ trong một release tương lai.

Điều này không có nghĩa API không dùng được. Có thể thử nghiệm, xây dựng ứng dụng nội bộ và đánh giá hiệu năng bằng JDK có hỗ trợ. Tuy nhiên, dự án cần:

- Pin rõ JDK vendor và release dùng để biên dịch/chạy.
- Kiểm tra lại API khi nâng JDK.
- Không giả định source/binary compatibility giữa các vòng incubator.
- Cân nhắc rủi ro khi công bố thư viện công khai phụ thuộc module incubator.
- Có implementation scalar thay thế nếu ứng dụng cần chạy trên runtime không cung cấp module này.

**Incubator không giống preview feature.** Vector API được cung cấp qua module `jdk.incubator.vector`; khi dùng trên classpath cần resolve module đó. Không cần `--enable-preview` chỉ để dùng Vector API.

## 3. Các khái niệm cốt lõi: vector, lane, shape, species và mask

Năm khái niệm này tạo nên mô hình lập trình của Vector API.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Vector | Một dãy bất biến gồm số lượng lane cố định, cùng kiểu phần tử | `IntVector` |
| Lane | Một vị trí chứa một giá trị primitive trong vector | Lane 0 chứa `12`, lane 1 chứa `25` |
| Shape | Định dạng/độ rộng vector theo bit | `S_128_BIT`, `S_256_BIT` |
| Species | Kết hợp kiểu lane và shape, xác định số lane và kiểu vector | `IntVector.SPECIES_PREFERRED` |
| Mask | Dãy boolean có cùng số lane, bật/tắt từng lane khi thực hiện thao tác | `VectorMask<Integer>` |

Ví dụ vector 128 bit với lane `int`:

~~~text
Shape: 128 bit
Element type: int (32 bit)
Lane count: 128 / 32 = 4

+---------+---------+---------+---------+
| lane 0  | lane 1  | lane 2  | lane 3  |
|   10    |   20    |   30    |   40    |
+---------+---------+---------+---------+
~~~

Vector API hỗ trợ sáu kiểu lane primitive:

- `byte` — `ByteVector`
- `short` — `ShortVector`
- `int` — `IntVector`
- `long` — `LongVector`
- `float` — `FloatVector`
- `double` — `DoubleVector`

Dù generic type hiển thị dạng `Vector<Integer>`, lane bên trong vẫn mang giá trị primitive `int`; Vector API tránh boxing từng phần tử thành `Integer`.

## 4. VectorSpecies: định dạng của các vector tương thích

`VectorSpecies<E>` đại diện cho một tổ hợp duy nhất của kiểu primitive lane (ETYPE), shape của vector (VSHAPE) và số lane tương ứng với kiểu lane và shape.

Ví dụ:

~~~java
VectorSpecies<Integer> species = IntVector.SPECIES_256;
~~~

Species này biểu diễn vector có lane kiểu `int` và shape 256 bit. Trên kiến trúc phù hợp, nó có 8 lane.

Các thông tin có thể truy vấn:

~~~java
int lanes = species.length();
int vectorBits = species.vectorBitSize();
int elementBits = species.elementSize();
~~~

- `length()` trả về số lane.
- `vectorBitSize()` trả về tổng độ rộng vector.
- `elementSize()` trả về số bit của một lane.

Với một species `int` 256 bit, kết quả tương ứng là 8 lane, 256 bit tổng và 32 bit mỗi lane.

### Dùng SPECIES_PREFERRED cho mã portable

Không nên mặc định CPU nào cũng hỗ trợ một shape cố định. Dùng species được runtime ưu tiên:

~~~java
static final VectorSpecies<Integer> SPECIES =
        IntVector.SPECIES_PREFERRED;
~~~

`SPECIES_PREFERRED` cho phép runtime chọn shape phù hợp với nền tảng hiện tại. Một máy có thể ưu tiên 128 bit, máy khác có thể ưu tiên 256 hoặc 512 bit. Số lane vì thế cũng thay đổi.

Có thể dùng các species cố định như `IntVector.SPECIES_128`, `SPECIES_256` hoặc `SPECIES_512` khi có lý do cụ thể, nhưng phải hiểu nền tảng mục tiêu. Nếu shape không được phần cứng/runtime hỗ trợ để sinh SIMD instruction tối ưu, implementation có thể dùng scalar fallback.

**Khuyến nghị:** giữ species trong `static final` field và viết thuật toán dựa trên `species.length()` thay vì hard-code số lane.

## 5. Lane-wise operation: cùng phép toán trên các lane tương ứng

Phần lớn phép toán vector là lane-wise. Mỗi lane của kết quả được tính từ các lane có cùng chỉ số của vector đầu vào.

Ví dụ:

~~~text
A = [10, 20, 30, 40]
B = [ 1,  2,  3,  4]

A.add(B)

R = [11, 22, 33, 44]
~~~

Với hai vector cùng species, phép cộng áp dụng độc lập cho từng cặp lane. Một số operation thường gặp:

| Nhóm | Ví dụ | Mô tả |
|---|---|---|
| Số học | `add`, `sub`, `mul`, `div` | Cộng, trừ, nhân, chia từng lane |
| So sánh | `compare`, `lt`, `eq`, `gt` | Tạo mask từ kết quả so sánh |
| Min/max | `min`, `max` | Chọn giá trị nhỏ/lớn hơn theo lane |
| Bitwise | `and`, `or`, `xor` | Phép logic bit cho lane kiểu nguyên |
| Reduction | `reduceLanes` | Gom nhiều lane thành một scalar |
| Reformat | `convert`, `reinterpretShape` | Chuyển kiểu lane hoặc cách diễn giải dữ liệu |
| Cross-lane | `rearrange`, `slice`, `unslice` | Di chuyển dữ liệu giữa các lane |

Các vector đầu vào của một operation thường phải có cùng species. Nếu trộn khác shape hoặc số lane, phép toán có thể ném lỗi kiểm tra kiểu/shape. Có thể gọi `check(species)` để xác nhận rõ một vector hoặc mask tương thích với species mong muốn.

## 6. Ví dụ đầu tiên: cộng hai mảng bằng IntVector

Tạo file `VectorApiDemo.java`:

~~~java
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

import java.util.Arrays;

public class VectorApiDemo {

    private static final VectorSpecies<Integer> SPECIES =
            IntVector.SPECIES_PREFERRED;

    static void add(int[] a, int[] b, int[] result) {
        if (a.length != b.length || result.length < a.length) {
            throw new IllegalArgumentException("Array lengths are incompatible");
        }

        int upperBound = SPECIES.loopBound(a.length);
        int i = 0;

        // Xử lý các nhóm có đủ số lane.
        for (; i < upperBound; i += SPECIES.length()) {
            IntVector va = IntVector.fromArray(SPECIES, a, i);
            IntVector vb = IntVector.fromArray(SPECIES, b, i);
            IntVector vr = va.add(vb);
            vr.intoArray(result, i);
        }

        // Xử lý phần đuôi còn lại bằng scalar.
        for (; i < a.length; i++) {
            result[i] = a[i] + b[i];
        }
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
        int[] b = {10, 20, 30, 40, 50, 60, 70, 80, 90, 100};
        int[] result = new int[a.length];

        add(a, b, result);

        System.out.println(Arrays.toString(result));
        System.out.println("Species: " + SPECIES);
        System.out.println("Lanes per vector: " + SPECIES.length());
    }
}
~~~

Kết quả:

~~~text
[11, 22, 33, 44, 55, 66, 77, 88, 99, 110]
Species: Species[int, ..., ...]
Lanes per vector: ...
~~~

Phần `...` phụ thuộc CPU/runtime. Không ghi cứng số lane trong kết quả mong đợi vì `SPECIES_PREFERRED` có thể khác nhau giữa máy.

Trong mỗi vòng vector:

1. `fromArray()` nạp một nhóm lane từ mảng.
2. `add()` cộng các lane tương ứng.
3. `intoArray()` ghi vector kết quả trở lại mảng.

`loopBound(a.length)` trả về chỉ số lớn nhất là bội số của số lane và không vượt quá độ dài mảng. Nhờ vậy, vòng vector chỉ chạy khi còn đủ một vector hoàn chỉnh.

## 7. Mask: điều khiển phép tính theo từng lane

`VectorMask<E>` là một dãy boolean bất biến có cùng số lane và species tương thích với vector. Mỗi bit của mask quyết định lane tương ứng có tham gia thao tác hay không.

Ví dụ:

~~~text
Vector: [  5,  12,  -3,  20,   8,  -1,  30,   4]
Mask:   [  T,   T,   .,   T,   T,   .,   T,   T]
                T = lane được chọn
                . = lane không được chọn
~~~

Mask có thể được tạo từ phép so sánh:

~~~java
IntVector values = IntVector.fromArray(SPECIES, data, 0);
VectorMask<Integer> positive =
        values.compare(VectorOperators.GT, 0);
~~~

`positive` có bit `true` ở các lane mà giá trị lớn hơn 0.

Có thể dùng mask để chọn lane trong phép tính hoặc trộn hai vector:

~~~java
IntVector increased = values.blend(
        values.add(10),
        positive);
~~~

Với `blend(other, mask)`, lane được bật trong mask lấy giá trị từ `other`; lane không được bật giữ giá trị từ vector hiện tại. Kết quả ở đây là cộng 10 cho số dương, còn các lane khác giữ nguyên.

Mask cũng có thể kết hợp logic:

~~~java
VectorMask<Integer> greaterThanZero =
        values.compare(VectorOperators.GT, 0);

VectorMask<Integer> lessThanTwenty =
        values.compare(VectorOperators.LT, 20);

VectorMask<Integer> selected =
        greaterThanZero.and(lessThanTwenty);
~~~

`selected` chọn các lane thỏa đồng thời hai điều kiện. Các thao tác thường dùng gồm `and`, `or`, `xor`, `not`, `allTrue()` và `trueCount()`.

### Masked operation

Nhiều method nhận mask ở tham số cuối. Lane được bật thực hiện phép toán; lane không được bật bị bỏ qua. Với masked load/store, các lane không được bật không đọc hoặc ghi phần tử tương ứng. Điều này hữu ích khi xử lý phần đuôi mảng hoặc vùng dữ liệu có điều kiện.

Mask phải tương thích với vector về species/số lane. Không lấy mask của một species rồi áp dụng tùy ý cho vector khác species.

## 8. Xử lý phần đuôi mảng bằng indexInRange

Độ dài mảng thường không chia hết cho số lane. Nếu vector có 8 lane mà mảng có 10 phần tử, sau một vòng đầy đủ vẫn còn 2 phần tử. Có hai cách phổ biến:

- Dùng `loopBound()` rồi xử lý phần đuôi bằng scalar, như ví dụ trước.
- Dùng mask để nạp và lưu có điều kiện ở cả vòng cuối.

`VectorSpecies.indexInRange(offset, limit)` tạo mask chỉ bật các lane có chỉ số nằm trong miền hợp lệ `[0, limit)`.

~~~java
static void addMasked(int[] a, int[] b, int[] result) {
    if (a.length != b.length || result.length < a.length) {
        throw new IllegalArgumentException("Array lengths are incompatible");
    }

    for (int i = 0; i < a.length; i += SPECIES.length()) {
        VectorMask<Integer> mask =
                SPECIES.indexInRange(i, a.length);

        IntVector va = IntVector.fromArray(SPECIES, a, i, mask);
        IntVector vb = IntVector.fromArray(SPECIES, b, i, mask);

        va.add(vb).intoArray(result, i, mask);
    }
}
~~~

Ở vòng cuối, nếu chỉ còn 2 phần tử thì mask chỉ bật hai lane đầu. Những lane còn lại không đọc khỏi mảng và không ghi vào kết quả.

| Cách xử lý | Ưu điểm | Điểm cần cân nhắc |
|---|---|---|
| `loopBound()` + scalar tail | Vòng vector chính không cần mask; thường là cách tốt để bắt đầu tối ưu | Có thêm vòng scalar cho phần dư |
| `indexInRange()` + masked load/store | Code gọn, một vòng lặp; xử lý biên an toàn | Mask được tính ở mỗi vòng; hiệu năng phụ thuộc CPU/JIT và workload |

Không mặc định một cách luôn nhanh hơn. Đo trên dữ liệu và phần cứng mục tiêu.

## 9. Species, shape và lane count phụ thuộc phần cứng

Species không chỉ là tên kiểu dữ liệu. Nó ràng buộc cả lane type và vector shape. Mọi phép toán lane-wise thông thường yêu cầu các vector đầu vào cùng shape và cùng số lane để ghép cặp lane chính xác.

Ví dụ:

| Species | Lane type | Vector width | Lane count |
|---|---|---:|---:|
| `IntVector.SPECIES_128` | `int` | 128 bit | 4 |
| `IntVector.SPECIES_256` | `int` | 256 bit | 8 |
| `IntVector.SPECIES_512` | `int` | 512 bit | 16 |
| `FloatVector.SPECIES_256` | `float` | 256 bit | 8 |
| `DoubleVector.SPECIES_256` | `double` | 256 bit | 4 |

Đây là quan hệ về kích thước, không phải lời hứa CPU thực tế sẽ chạy đúng một lệnh phần cứng tương ứng. Khả năng sinh SIMD instruction còn phụ thuộc CPU, JDK build, JIT compiler và operation cụ thể.

`SPECIES_PREFERRED` giúp code thích ứng với nền tảng:

~~~java
VectorSpecies<Float> floatSpecies =
        FloatVector.SPECIES_PREFERRED;

System.out.println(floatSpecies.vectorShape());
System.out.println(floatSpecies.vectorBitSize());
System.out.println(floatSpecies.length());
~~~

Không giả định `SPECIES_PREFERRED` luôn là 256 bit hoặc số lane luôn là lũy thừa của hai. Dùng `length()` và `loopBound()` thay cho bit trick tự viết dựa trên một lane count cố định.

## 10. Reduction: gom các lane thành một giá trị scalar

Một số bài toán cần kết quả tổng hợp thay vì giữ lại một vector, ví dụ tính tổng hoặc giá trị lớn nhất. Vector API cung cấp các phép reduction như `reduceLanes()`.

Ví dụ tính tổng các phần tử `int`:

~~~java
static long sum(int[] values) {
    int upperBound = SPECIES.loopBound(values.length);
    int i = 0;
    long total = 0;

    for (; i < upperBound; i += SPECIES.length()) {
        IntVector vector = IntVector.fromArray(SPECIES, values, i);
        total += vector.reduceLanes(VectorOperators.ADD);
    }

    for (; i < values.length; i++) {
        total += values[i];
    }

    return total;
}
~~~

Trong ví dụ, mỗi vector được cộng trong miền `int`, sau đó kết quả scalar được cộng vào biến `long`. Vì phép reduction của `IntVector` vẫn trả về `int`, nếu tổng của các lane trong một vector có thể vượt miền `int`, kết quả reduction có thể overflow trước khi được cộng vào `long`. Khi cần tổng chính xác cho miền lớn, phải chuyển lane sang `long` trước reduction hoặc chọn thuật toán phù hợp.

Với số thực dấu phẩy động, reduction vector có thể cộng theo thứ tự khác vòng lặp scalar. Do phép cộng floating point không kết hợp tuyệt đối do làm tròn, kết quả có thể sai khác vài bit cuối. Ứng dụng khoa học/tài chính cần xác định tolerance và yêu cầu reproducibility trước khi thay thuật toán scalar bằng vector reduction.

## 11. Mask không phải Java branch và không phải thread

Mask điều khiển các lane trong một vector operation. Nó không tạo thread mới, không lên lịch task và không thay thế `ExecutorService`, virtual threads hoặc parallel streams.

Phân biệt:

| Cơ chế | Đơn vị song song | Ví dụ |
|---|---|---|
| Vector API / SIMD | Nhiều lane trong một vector instruction | Cộng 8 cặp `int` cùng lúc |
| Java threads | Các luồng thực thi độc lập | Nhiều request xử lý đồng thời |
| Parallel stream | Chia pipeline thành task song song | `parallelStream()` |
| Mask | Chọn lane tham gia một vector operation | Chỉ cập nhật lane có giá trị dương |

Có thể kết hợp thread-level parallelism và SIMD, chẳng hạn mỗi worker xử lý một đoạn mảng bằng Vector API. Tuy nhiên, cần tránh oversubscription, tranh chấp bộ nhớ và chia đoạn không hợp lý. Bắt đầu với một tầng vector hóa đơn giản, benchmark trước khi kết hợp nhiều thread.

## 12. Hiệu năng và các giới hạn cần hiểu

Vector API được thiết kế để JIT compiler có thể biên dịch phép toán vector thành SIMD instruction tối ưu trên nền tảng hỗ trợ. Khi runtime không thể sinh vector instruction cho operation/shape, API có implementation scalar fallback để giữ tính đúng đắn.

Vì vậy:

- Code dùng Vector API không bảo đảm nhanh hơn scalar trên mọi CPU.
- Shape lớn hơn không luôn nhanh hơn; nó có thể không được hỗ trợ trực tiếp hoặc gây chi phí chuyển đổi.
- Với dữ liệu nhỏ, chi phí gọi method, kiểm tra biên hoặc chuẩn bị dữ liệu có thể lớn hơn lợi ích SIMD.
- Nếu workload bị giới hạn bởi memory bandwidth, tăng số phép toán mỗi instruction có thể không làm throughput tăng tương ứng.
- Một số phép toán floating point hoặc cross-lane có thể không có mapping phần cứng tối ưu.
- JIT cần warm-up và profile; không đánh giá chỉ bằng lần chạy đầu tiên.

### Các nguyên tắc viết code

1. Bắt đầu với `SPECIES_PREFERRED`.
2. Lưu species trong `static final`.
3. Giữ các phép tính trong cùng species nếu có thể.
4. Dùng `loopBound()` hoặc mask cho phần đuôi.
5. Hạn chế tạo array tạm trong vòng lặp vector.
6. Đặt dữ liệu liên tục và truy cập tuần tự khi có thể.
7. Không dùng identity comparison `==` cho vector/mask/species; đây là các value-based classes, dùng `equals()` khi cần so sánh giá trị.
8. Giữ implementation scalar để đối chiếu kết quả và làm fallback.
9. Benchmark trên JDK, CPU và kích thước dữ liệu mục tiêu.

## 13. Khi nào nên và không nên dùng Vector API?

| Tình huống | Đánh giá | Lý do |
|---|---|---|
| Cộng/nhân hai mảng số lớn | Phù hợp để thử nghiệm | Phép toán độc lập trên từng phần tử |
| Xử lý pixel hoặc sample âm thanh | Phù hợp để thử nghiệm | Dữ liệu thường liên tục và có cùng phép tính |
| Tính checksum hoặc transform theo block | Có thể phù hợp | Có thể xử lý nhiều lane trong một bước |
| Vòng lặp có dependency giữa phần tử trước và sau | Khó vector hóa | Kết quả lane này phụ thuộc lane khác |
| Nhiều nhánh phức tạp theo từng phần tử | Cần đánh giá kỹ | Mask có thể giúp nhưng không làm mọi nhánh hiệu quả |
| Công việc chủ yếu chờ database/network | Thường không phù hợp | Bottleneck không nằm ở phép tính CPU |
| Mảng rất nhỏ hoặc request đơn lẻ | Thường không đáng | Chi phí chuẩn bị có thể lớn hơn lợi ích |
| Thư viện cần API Java SE ổn định tuyệt đối | Cần cân nhắc | Vector API vẫn là incubating module |

Không chuyển mọi vòng lặp trong ứng dụng sang Vector API. Chọn hotspot CPU đã đo được, nơi dữ liệu và phép toán có cấu trúc phù hợp.

## 14. Biên dịch và chạy Vector API trên JDK 25

Vector API nằm trong module `jdk.incubator.vector`. Khi ứng dụng chạy trên classpath, cần resolve module này lúc biên dịch và chạy.

~~~bash
javac --add-modules jdk.incubator.vector \
      -d out VectorApiDemo.java

java --add-modules jdk.incubator.vector \
     -cp out VectorApiDemo
~~~

JDK sẽ phát cảnh báo rằng chương trình đang sử dụng incubating module. Đây là hành vi dự kiến.

**Không thêm `--enable-preview` chỉ vì Vector API đang incubating.** `--enable-preview` dành cho Java preview language/API features; Vector API được bật bằng module `jdk.incubator.vector`.

### Nếu ứng dụng dùng named module

Trong `module-info.java`:

~~~java
module com.example.vectorapp {
    requires jdk.incubator.vector;
}
~~~

Sau đó biên dịch/chạy ứng dụng theo module path của dự án. Không cần đồng thời thêm `requires java.base`; module này luôn được đọc ngầm định.

### Kiểm tra JDK và module

~~~bash
java --version
javac --version
java --list-modules | grep jdk.incubator.vector
~~~

Đảm bảo `java` và `javac` thuộc cùng JDK release. Khi nâng từ JDK 25 lên 26 hoặc 27, biên dịch lại và đọc release notes/JEP của Vector API tương ứng.

## 15. Benchmark: so sánh scalar và vector một cách công bằng

Không dùng một lần chạy `System.nanoTime()` đơn lẻ để kết luận Vector API nhanh hơn. JIT compilation, warm-up, CPU frequency scaling, cache, memory bandwidth và GC đều có thể làm sai lệch phép đo.

Một benchmark có ý nghĩa nên:

1. Dùng cùng dữ liệu đầu vào và cùng kết quả mong đợi.
2. So sánh implementation scalar với implementation vector.
3. Dùng JMH hoặc harness benchmark JVM phù hợp.
4. Có warm-up iterations và measurement iterations.
5. Chạy nhiều fork để giảm ảnh hưởng trạng thái JVM.
6. Thử nhiều kích thước dữ liệu: nhỏ, vừa và lớn.
7. Đo throughput/operations per second hoặc thời gian trên mỗi phần tử.
8. Xác minh kết quả hai implementation bằng nhau (hoặc nằm trong tolerance với floating point).
9. Chạy trên CPU và JDK giống môi trường triển khai.
10. Ghi lại CPU model, JDK full version, OS và species được chọn.

### Những số liệu cần ghi

| Thông tin | Ví dụ |
|---|---|
| JDK | Vendor, full version và build |
| CPU | Model, ISA/vector extensions |
| Species | `IntVector.SPECIES_PREFERRED` và `length()` |
| Data size | 1K, 64K, 1M phần tử |
| Scalar throughput | Operations/s |
| Vector throughput | Operations/s |
| Speedup | Vector throughput / scalar throughput |
| Kết quả | Đúng tuyệt đối hoặc sai số cho phép |
| Ghi chú | Warm-up, forks, memory bandwidth, CPU load |

Nếu scalar loop đã được HotSpot auto-vectorize, Vector API có thể không tạo thêm lợi thế. Benchmark phải so sánh với scalar implementation được tối ưu và có cùng semantics, không so với code scalar cố tình viết kém.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Quên `--add-modules jdk.incubator.vector` | Compiler/runtime không resolve được package | Thêm module flag hoặc khai báo `requires` |
| Nhầm incubator với preview | Dùng sai `--enable-preview` | Dùng module flag; không cần preview flag cho Vector API |
| Hard-code số lane | Sai trên CPU có species khác | Dùng `SPECIES.length()` |
| Hard-code shape không được hỗ trợ | Có thể rơi về scalar hoặc mất hiệu năng | Bắt đầu bằng `SPECIES_PREFERRED` |
| Không xử lý phần đuôi | Đọc/ghi vượt mảng hoặc bỏ sót phần tử | Dùng `loopBound()` + scalar tail hoặc masked operation |
| Dùng vector khác species | Phép toán không tương thích | Dùng cùng species hoặc kiểm tra bằng `check()` |
| Dùng mask sai species | Không tương thích số lane/shape | Tạo mask từ species của vector |
| Cho rằng mask tạo thread | Hiểu sai mô hình song song | Mask chỉ điều khiển lane |
| So sánh vector bằng `==` | So sánh identity thay vì nội dung | Dùng `equals()` |
| Cho rằng API luôn sinh SIMD | Kỳ vọng hiệu năng không thực tế | Xem JIT/hardware và benchmark |
| Bỏ qua overflow/reduction order | Sai khác kết quả số học | Xác định miền dữ liệu và semantics |
| Dùng Vector API trong mọi vòng lặp | Code phức tạp nhưng không tăng tốc | Chỉ vector hóa hotspot đã đo |
| Nâng JDK mà không kiểm tra API | Gặp incompatibility giữa incubator releases | Đọc JEP/release notes và compile lại |

## 17. Bài tập thực hành và checklist

### Bài tập A — Cộng hai mảng

Viết hai hàm cộng `int[]`:

- Bản scalar dùng vòng lặp thông thường.
- Bản vector dùng `IntVector.SPECIES_PREFERRED`, `add()` và `loopBound()`.

Kiểm tra với mảng rỗng, mảng một phần tử, mảng ngắn hơn species và mảng có chiều dài không chia hết cho số lane.

### Bài tập B — Dùng mask để chọn giá trị

Cho mảng điểm số. Dùng vector comparison tạo mask cho các phần tử từ 80 trở lên. Tăng 5 điểm cho các lane được chọn, giữ nguyên lane còn lại. Kiểm tra kết quả với implementation scalar.

### Bài tập C — Xử lý tail bằng masked load/store

Viết lại phép cộng hai mảng bằng `SPECIES.indexInRange(i, length)`. So sánh kết quả và thời gian với phiên bản `loopBound()` + scalar tail.

### Bài tập D — Đếm số phần tử vượt ngưỡng

Dùng `VectorMask.trueCount()` để đếm số lane lớn hơn một ngưỡng. Xử lý phần đuôi scalar hoặc bằng mask và xác minh kết quả.

### Checklist

- [ ] Phân biệt SIMD lane parallelism với Java thread parallelism.
- [ ] Hiểu vector, lane, shape và species.
- [ ] Dùng `SPECIES_PREFERRED` thay vì giả định vector width cố định.
- [ ] Hiểu `VectorMask` và cách mask chọn lane.
- [ ] Dùng `loopBound()` hoặc `indexInRange()` để xử lý phần đuôi.
- [ ] Biết các vector đầu vào cần cùng species cho lane-wise operations.
- [ ] Biết Vector API dùng primitive lane, tránh boxing từng phần tử.
- [ ] Biết API có scalar fallback và không bảo đảm tăng tốc.
- [ ] Biên dịch/chạy đúng module `jdk.incubator.vector`.
- [ ] Không nhầm incubator module với preview feature.
- [ ] Benchmark scalar/vector trên cùng workload và kiểm tra correctness.
- [ ] Kiểm tra JEP/release notes khi nâng JDK vì API vẫn đang incubate.

## 18. Tài liệu chính thức

- [JEP 508 — Vector API (Tenth Incubator)](https://openjdk.org/jeps/508): trạng thái và thay đổi của Vector API trong JDK 25.
- [JEP 529 — Vector API (Eleventh Incubator)](https://openjdk.org/jeps/529): vòng incubator trong JDK 26.
- [JEP 537 — Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537): vòng incubator trong JDK 27.
- [Java SE 25 — Package jdk.incubator.vector](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html): mô hình vector, lane-wise operations, species, mask và ví dụ xử lý mảng.
- [Java SE 25 — VectorSpecies](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html): shape, lane count, SPECIES_PREFERRED, loopBound() và indexInRange().
- [Java SE 25 — VectorMask](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorMask.html): mask operations, lane selection và reduction trên mask.
- [Java SE 25 — IntVector](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html): các phép toán vector cho lane kiểu int.
- [Oracle JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): xác nhận Vector API tiếp tục ở Eleventh Incubator.
- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): xác nhận Vector API tiếp tục ở Twelfth Incubator.
- [Java SE 27 — Vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html): đối chiếu mô hình vector và species ở JDK mới hơn.
- [OpenJDK JMH](https://github.com/openjdk/jmh): công cụ benchmark JVM để đo scalar và vector implementation.

> **Ghi nhớ:** Vector là dãy lane cùng kiểu primitive; species xác định kiểu lane và shape; mask chọn lane tham gia phép tính. Dùng SPECIES_PREFERRED và xử lý phần đuôi bằng loopBound() hoặc indexInRange(). Vector API vẫn là incubating module trong JDK 27, vì vậy cần kiểm tra tương thích khi nâng JDK và đo hiệu năng trên workload thực tế.
