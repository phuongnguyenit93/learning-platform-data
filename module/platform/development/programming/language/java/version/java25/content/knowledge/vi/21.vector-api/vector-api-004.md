# Xử lý phần dư, căn chỉnh dữ liệu và bảo toàn tính đúng của thuật toán

## Mục tiêu bài học

**Vector API** cho phép biểu diễn phép tính trên nhiều phần tử cùng kiểu bằng một vector gồm các lane. HotSpot có thể biên dịch những phép toán này thành lệnh SIMD (Single Instruction, Multiple Data) phù hợp với CPU, giúp xử lý nhiều phần tử trong một lượt thay vì lặp từng phần tử bằng scalar code.

Tuy nhiên, dữ liệu thực tế hiếm khi có độ dài đúng bằng bội số số lane của vector. Mảng có thể bắt đầu tại offset bất kỳ, vùng nhớ native có thể có yêu cầu căn chỉnh, và một phép cộng hoặc phép rút gọn có thể có quy tắc tràn số, làm tròn riêng. Nếu bỏ qua những điều kiện đó, phiên bản vector hóa có thể đọc vượt biên, ghi đè dữ liệu hoặc cho kết quả khác thuật toán scalar.

Bài **Xử lý phần dư, căn chỉnh dữ liệu và bảo toàn tính đúng của thuật toán** thuộc chương **Vector API** của module **JAVA_VERSION_JAVA25**. Nội dung tập trung vào ba việc: xử lý các phần tử cuối không đủ một vector, tổ chức offset/căn chỉnh dữ liệu và giữ nguyên ngữ nghĩa của thuật toán khi chuyển từ scalar sang vector.

Sau bài này, bạn có thể:

1. Chọn `VectorSpecies` phù hợp với CPU mà không cố định số lane.
2. Dùng `loopBound()` để tách vòng lặp vector và phần tử dư (tail).
3. Dùng `VectorMask` và `indexInRange()` để load/store an toàn ở vòng cuối.
4. Tính đúng offset khi dữ liệu bắt đầu tại một vị trí khác 0.
5. Phân biệt offset theo phần tử của array với offset theo byte của `MemorySegment`.
6. Hiểu căn chỉnh bộ nhớ ảnh hưởng tới hiệu năng như thế nào và khi nào không cần tự căn chỉnh.
7. Bảo toàn hành vi tràn số nguyên, làm tròn floating-point, reduction và xử lý lane không hoạt động.
8. Kiểm soát aliasing khi input/output dùng chung vùng nhớ.
9. Kiểm thử độ dài, offset, biên và benchmark scalar/vector trên cùng workload.

> **Trạng thái API hiện hành:** Vector API vẫn là incubating module trong JDK 27 (JEP 537, Twelfth Incubator). JDK 25 đưa vào JEP 508 (Tenth Incubator), JDK 26 là JEP 529 (Eleventh Incubator). Ví dụ trong bài dùng API có trong JDK 27; module vẫn có thể thay đổi hoặc bị loại bỏ trước khi trở thành API Java SE ổn định. Không cần `--enable-preview`; cần thêm module `jdk.incubator.vector` khi biên dịch và chạy.

## 1. Vector, lane và species

Một vector chứa một số lane cố định. Mỗi lane giữ một giá trị primitive như `int`, `long`, `float` hoặc `double`. Phép toán lane-wise áp dụng cùng một phép tính cho các lane tương ứng.

Ví dụ, nếu một `IntVector` có 8 lane, phép cộng hai vector tương đương thực hiện 8 phép cộng `int` độc lập trong cùng một vector operation.

~~~text
A = [a0, a1, a2, a3, a4, a5, a6, a7]
B = [b0, b1, b2, b3, b4, b5, b6, b7]
             A.add(B)
C = [a0+b0, a1+b1, a2+b2, a3+b3,
     a4+b4, a5+b5, a6+b6, a7+b7]
~~~

Số lane không phải hằng số phổ quát. Nó phụ thuộc vào element type và shape của vector. Ví dụ, vector 256 bit chứa 8 lane `int`, nhưng chỉ chứa 4 lane `long`.

### 1.1. Dùng preferred species

Mỗi vector type cung cấp `SPECIES_PREFERRED`. Đây là species có kích thước phù hợp nhất với nền tảng hiện tại theo lựa chọn của runtime.

~~~java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

static final VectorSpecies<Integer> INT_SPECIES =
        IntVector.SPECIES_PREFERRED;

static final VectorSpecies<Float> FLOAT_SPECIES =
        FloatVector.SPECIES_PREFERRED;
~~~

Có thể xem các thuộc tính:

~~~java
System.out.println(INT_SPECIES.vectorBitSize());
System.out.println(INT_SPECIES.vectorByteSize());
System.out.println(INT_SPECIES.length());
System.out.println(INT_SPECIES.vectorShape());
~~~

- `vectorBitSize()`: kích thước vector theo bit.
- `vectorByteSize()`: kích thước vector theo byte.
- `length()`: số lane.
- `vectorShape()`: shape tương ứng.

**Không hard-code** số lane như 4, 8 hoặc 16 trong thuật toán tổng quát. Cũng không nên tự thay `loopBound()` bằng bit mask như `length & ~(lanes - 1)`; không nên giả định mọi vector species đều có số lane là lũy thừa của hai.

### 1.2. API incubator không đảm bảo luôn có SIMD instruction

Vector API được thiết kế để runtime biên dịch phép toán vector thành lệnh phần cứng phù hợp khi có thể. Nếu shape không được CPU hỗ trợ hoặc runtime không sinh được lệnh vector tối ưu, implementation scalar có thể được sử dụng.

Điều này có hai hệ quả:

- Code vẫn phải đúng trên nền tảng không có SIMD chuyên dụng.
- Dùng Vector API không tự động đồng nghĩa với nhanh hơn scalar code.

Ưu tiên preferred species để code thích nghi với nền tảng. Chỉ chọn shape cố định khi đã có lý do cụ thể và benchmark trên tất cả nền tảng triển khai.

## 2. Phần tử dư xuất hiện ở đâu?

Giả sử một thuật toán xử lý 19 phần tử và species hiện tại có 8 lane:

- Vector thứ nhất xử lý phần tử 0–7.
- Vector thứ hai xử lý phần tử 8–15.
- Còn lại 3 phần tử 16–18.

Ba phần tử cuối được gọi là **tail** hoặc phần tử dư của vòng vector.

~~~text
Mảng có 19 phần tử:

[ 0  1  2  3  4  5  6  7 ] [ 8  9 10 11 12 13 14 15 ] [16 17 18]
  -------- vector 1 --------   -------- vector 2 --------    -- tail --
~~~

Không được load vector đầy đủ ở offset 16 nếu mảng chỉ có 19 phần tử. Vector đó cần 8 lane, trong khi chỉ còn 3 phần tử hợp lệ. Có hai cách xử lý phổ biến:

1. Dùng `loopBound()` để chỉ chạy các vector đầy đủ, sau đó xử lý tail bằng scalar loop.
2. Dùng `VectorMask` để chỉ load/store các lane hợp lệ của vector cuối.

Cả hai cách đều đúng nếu offset, mask và phạm vi mảng được tính chính xác.

## 3. Cách 1: loopBound và scalar tail

`VectorSpecies.loopBound(length)` trả về bội số lớn nhất của số lane không vượt quá `length`.

Nếu:

- `length = 19`
- `species.length() = 8`

thì:

- `loopBound(19) = 16`
- Vòng vector xử lý các vị trí 0–15.
- Scalar tail xử lý các vị trí 16–18.

### 3.1. Ví dụ cộng hai mảng int

~~~java
import java.util.Objects;
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

public final class VectorAdd {
    private static final VectorSpecies<Integer> SPECIES =
            IntVector.SPECIES_PREFERRED;

    public static void add(
            int[] a, int aOffset,
            int[] b, int bOffset,
            int[] out, int outOffset,
            int count) {

        Objects.checkFromIndexSize(aOffset, count, a.length);
        Objects.checkFromIndexSize(bOffset, count, b.length);
        Objects.checkFromIndexSize(outOffset, count, out.length);

        int bound = SPECIES.loopBound(count);
        int i = 0;

        // Chỉ xử lý các block có đủ SPECIES.length() phần tử.
        for (; i < bound; i += SPECIES.length()) {
            IntVector va = IntVector.fromArray(
                    SPECIES, a, aOffset + i);
            IntVector vb = IntVector.fromArray(
                    SPECIES, b, bOffset + i);

            va.add(vb).intoArray(out, outOffset + i);
        }

        // Xử lý phần tử dư bằng scalar.
        for (; i < count; i++) {
            out[outOffset + i] =
                    a[aOffset + i] + b[bOffset + i];
        }
    }
}
~~~

Các điểm cần giữ:

- `count` là số phần tử cần xử lý, không nhất thiết bằng chiều dài toàn mảng.
- `aOffset`, `bOffset`, `outOffset` là offset theo **phần tử**, không phải byte.
- `loopBound(count)` tính số phần tử đầu vào có thể xử lý theo block vector đầy đủ.
- Tail bắt đầu từ `i = bound`, không phải từ `bound + 1`.
- Mọi vùng input/output được kiểm tra trước bằng `Objects.checkFromIndexSize`.

### 3.2. Ví dụ tính tổng với accumulator long

Nếu tổng nhiều giá trị `int`, dùng accumulator `long` để tránh tràn `int` khi cộng dồn. `IntVector.reduceLanesToLong(ADD)` trả về kết quả reduction dưới dạng `long`.

~~~java
import static jdk.incubator.vector.VectorOperators.ADD;

import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

public final class VectorSum {
    private static final VectorSpecies<Integer> SPECIES =
            IntVector.SPECIES_PREFERRED;

    public static long sum(int[] values) {
        int bound = SPECIES.loopBound(values.length);
        int i = 0;
        long total = 0L;

        for (; i < bound; i += SPECIES.length()) {
            IntVector vector =
                    IntVector.fromArray(SPECIES, values, i);

            total += vector.reduceLanesToLong(ADD);
        }

        for (; i < values.length; i++) {
            total += values[i];
        }

        return total;
    }
}
~~~

Kết quả tương đương việc cộng các phần tử `int` vào biến `long` theo thứ tự scalar, miễn tổng cuối cùng vẫn nằm trong miền biểu diễn của `long`. Nếu tổng có thể vượt `Long.MAX_VALUE` hoặc thấp hơn `Long.MIN_VALUE`, cả accumulator long vẫn có thể tràn; phải xác định miền dữ liệu hoặc dùng chiến lược số học khác.

### 3.3. Khi nào chọn scalar tail?

Scalar tail thường dễ đọc, dễ debug và tránh phải thực hiện masked operation trong mọi vòng lặp. Đây là lựa chọn tốt để bắt đầu:

- Vòng vector chỉ chạy với block đầy đủ.
- Tail thường nhỏ hơn một vector.
- Không cần viết thêm logic cho mask.
- Dễ so sánh với scalar reference implementation.

Tuy nhiên, nếu thuật toán cần xử lý dữ liệu ở nhiều vùng có độ dài không cố định hoặc muốn một vòng lặp duy nhất, masked loop có thể tiện hơn.

## 4. Cách 2: masked load/store cho tail

`VectorSpecies.indexInRange(offset, limit)` tạo một mask chỉ bật những lane có chỉ số:

\[
offset + laneIndex \in [0, limit - 1]
\]

Các lane nằm ngoài phạm vi bị tắt.

~~~java
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorSpecies;

public final class MaskedVectorAdd {
    private static final VectorSpecies<Integer> SPECIES =
            IntVector.SPECIES_PREFERRED;

    public static void add(
            int[] a, int aOffset,
            int[] b, int bOffset,
            int[] out, int outOffset,
            int count) {

        Objects.checkFromIndexSize(aOffset, count, a.length);
        Objects.checkFromIndexSize(bOffset, count, b.length);
        Objects.checkFromIndexSize(outOffset, count, out.length);

        for (int i = 0; i < count; i += SPECIES.length()) {
            VectorMask<Integer> mask =
                    SPECIES.indexInRange(i, count);

            IntVector va = IntVector.fromArray(
                    SPECIES, a, aOffset + i, mask);
            IntVector vb = IntVector.fromArray(
                    SPECIES, b, bOffset + i, mask);

            va.add(vb).intoArray(out, outOffset + i, mask);
        }
    }
}
~~~

Trong ví dụ:

- Mask của block đầy đủ có tất cả lane bật.
- Mask của block cuối chỉ bật những lane còn nằm trong `count`.
- `fromArray(..., mask)` không đọc các phần tử ứng với lane bị tắt; lane đó được khởi tạo bằng giá trị mặc định của primitive type, ở đây là 0.
- `intoArray(..., mask)` chỉ ghi các lane bật; các phần tử output ở lane bị tắt được giữ nguyên.

### 4.1. Vì sao masked store quan trọng?

Giả sử output có 19 phần tử, vector cuối chỉ có 3 lane hợp lệ. Nếu ghi vector đủ 8 lane mà không mask, các phần tử sau index 18 có thể bị ghi vượt phạm vi hoặc gây exception.

Masked store chỉ ghi 3 lane hợp lệ. Điều này bảo vệ:

- Phần đuôi của mảng.
- Dữ liệu nằm sau vùng output được chỉ định.
- Các phần tử khác khi output là một vùng con trong mảng lớn hơn.

Không dùng mask chỉ ở bước load rồi quên mask ở bước store. Hai thao tác có phạm vi riêng; phải bảo đảm cả hai đều tuân theo cùng ranh giới dữ liệu.

### 4.2. Mask không tự kiểm tra mọi mảng

Trong ví dụ trên, `count` và các offset được kiểm tra trước. Mask được tính dựa trên số phần tử logic cần xử lý. Nếu các mảng có độ dài khác nhau hoặc offset khác nhau, phải xác minh từng vùng độc lập.

Ví dụ, nếu `a` còn 10 phần tử nhưng `b` chỉ còn 6, mask của `a` không bảo vệ được lần load từ `b`. Cần kiểm tra cả ba vùng hoặc tạo mask giao của các điều kiện hợp lệ.

## 5. Chọn scalar tail hay masked loop?

| Tiêu chí | `loopBound()` + scalar tail | Masked loop |
|---|---|---|
| Số vòng lặp | Vòng vector và vòng scalar riêng | Một vòng lặp |
| Load/store | Không mask trong vector đầy đủ | Dùng mask cho cả vòng |
| Dễ đọc | Rõ ràng với thuật toán tuyến tính | Gọn khi nhiều vùng có biên |
| Hiệu năng | Thường là điểm bắt đầu tốt cho mảng dài | Có thể có thêm chi phí mask ở các vòng đầy đủ |
| Tail | Scalar | Masked vector |
| Kiểm thử | Kiểm tra vector loop và tail | Kiểm tra mask đầy đủ, mask một phần và mask rỗng |

Không có lựa chọn nào luôn nhanh hơn. Oracle API documentation minh họa cả hai cách và lưu ý masked loop có thể kém tối ưu hơn trên mảng lớn vì mask được dùng trong mọi vòng, kể cả khi tất cả lane đều hợp lệ.

Hãy benchmark trên workload thực tế trước khi chọn.

## 6. Offset và ranh giới dữ liệu

Một lỗi thường gặp là lấy offset logic của một vùng dữ liệu làm offset của vùng khác.

Giả sử:

- Input A bắt đầu tại index 10.
- Input B bắt đầu tại index 20.
- Output bắt đầu tại index 4.
- Cần xử lý 19 phần tử.

Ở mỗi block vector, lane 0 phải tương ứng với:

| Mảng | Index của lane 0 |
|---|---:|
| A | `10 + i` |
| B | `20 + i` |
| Output | `4 + i` |

Lane 1 sẽ tương ứng với index tăng thêm 1 trong từng mảng.

~~~text
Logical position:   0  1  2  3  4 ... 18
A physical index:  10 11 12 13 14 ... 28
B physical index:  20 21 22 23 24 ... 38
Out index:          4  5  6  7  8 ... 22
~~~

Không dùng một offset chung cho cả ba mảng trừ khi chúng thực sự cùng bắt đầu ở một vị trí.

### 6.1. Kiểm tra vùng dữ liệu trước khi vector hóa

Với mỗi mảng, phải bảo đảm:

\[
0 \le offset,\quad 0 \le count,\quad offset + count \le array.length
\]

Trong Java, `Objects.checkFromIndexSize(offset, count, length)` là cách kiểm tra gọn và tránh tự viết phép cộng có thể overflow.

Nếu API nhận nhiều vùng input/output, kiểm tra riêng từng vùng trước khi vào vòng lặp vector. Không dựa vào mask để thay thế kiểm tra hợp đồng dữ liệu đầu vào.

### 6.2. Không nhầm offset array với offset MemorySegment

| API | Đơn vị offset |
|---|---|
| `IntVector.fromArray(..., int[] array, int offset)` | Số phần tử `int` |
| `FloatVector.fromArray(..., float[] array, int offset)` | Số phần tử `float` |
| `IntVector.fromMemorySegment(..., long offset, ByteOrder)` | Byte |
| `FloatVector.fromMemorySegment(..., long offset, ByteOrder)` | Byte |

Ví dụ, phần tử `int` thứ 5 nằm tại byte offset 20 nếu segment bắt đầu đúng tại đầu dãy int:

\[
5 \times Integer.BYTES = 20
\]

Với `MemorySegment`, dùng `long` cho byte offset và kiểm tra phép nhân/chuyển đổi kích thước trước khi truy cập.

## 7. Căn chỉnh dữ liệu và hiệu năng

Căn chỉnh (alignment) mô tả việc địa chỉ dữ liệu nằm trên ranh giới byte phù hợp với một yêu cầu truy cập. Trên CPU, căn chỉnh có thể ảnh hưởng đến loại lệnh load/store được sinh ra, số lần truy cập bộ nhớ và cache behavior.

Cần phân biệt hai vấn đề:

- **Tính đúng:** offset hợp lệ, đúng đơn vị, không vượt bounds và đọc đúng byte order.
- **Hiệu năng:** vị trí bắt đầu có thuận lợi cho vector load/store và cache line hay không.

Không biến căn chỉnh thành một điều kiện tự đặt ra nếu API không yêu cầu. Với array, Vector API nhận offset theo phần tử; runtime chịu trách nhiệm triển khai load/store phù hợp. Offset không phải bội số của vector width vẫn có thể đúng nếu nằm trong bounds. Hiệu năng của truy cập aligned và unaligned cần được đo trên CPU mục tiêu.

### 7.1. Vì sao không nên tự giả định vector width?

Ví dụ, `IntVector.SPECIES_PREFERRED` có thể chọn shape khác nhau tùy CPU/JDK. Số lane của một species không phải hằng số toàn cục.

Không nên viết:

~~~java
// Không nên: giả định mọi CPU đều xử lý 8 lane int.
for (int i = 0; i < values.length; i += 8) {
    // ...
}
~~~

Dùng:

~~~java
for (int i = 0; i < SPECIES.loopBound(values.length);
     i += SPECIES.length()) {
    // ...
}
~~~

Tương tự, không nên dùng `length & ~(lanes - 1)` nếu không có bảo đảm `lanes` là lũy thừa của hai. `loopBound()` đã mã hóa quy tắc này theo species.

### 7.2. Dùng MemorySegment khi cần kiểm soát vùng nhớ

Vector API hỗ trợ load/store trên `MemorySegment` với byte offset và `ByteOrder` tường minh. Foreign Function & Memory API (FFM) là API Java SE ổn định từ JDK 22; Vector API vẫn là incubator module riêng.

Ví dụ cấp phát vùng nhớ native có căn chỉnh 64 byte:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

try (Arena arena = Arena.ofConfined()) {
    int count = values.length;
    long byteSize = (long) count * Integer.BYTES;

    MemorySegment input = arena.allocate(byteSize, 64);
    MemorySegment output = arena.allocate(byteSize, 64);

    for (int i = 0; i < count; i++) {
        input.setAtIndex(ValueLayout.JAVA_INT, i, values[i]);
    }

    int bound = SPECIES.loopBound(count);
    int i = 0;

    for (; i < bound; i += SPECIES.length()) {
        long byteOffset = (long) i * Integer.BYTES;

        IntVector vector = IntVector.fromMemorySegment(
                SPECIES, input, byteOffset, ByteOrder.nativeOrder());

        vector.mul(2).intoMemorySegment(
                output, byteOffset, ByteOrder.nativeOrder());
    }

    for (; i < count; i++) {
        int value = input.getAtIndex(ValueLayout.JAVA_INT, i);
        output.setAtIndex(ValueLayout.JAVA_INT, i, value * 2);
    }
}
~~~

Ở ví dụ này:

- `Arena.allocate(byteSize, 64)` yêu cầu vùng native có căn chỉnh 64 byte.
- `byteOffset` được tính từ index logic nhân với `Integer.BYTES`.
- `ByteOrder.nativeOrder()` thường thuận lợi cho hiệu năng nếu dữ liệu có cùng byte order với CPU.
- `Arena.ofConfined()` giới hạn quyền truy cập segment theo thread sở hữu và tự giải phóng vùng native khi đóng arena.

Giá trị 64 byte chỉ là ví dụ về căn chỉnh. Không coi đây là vector width hoặc cache-line size bắt buộc trên mọi CPU.

### 7.3. Byte order là một phần của tính đúng

Nếu dữ liệu được đọc từ file/network theo big-endian nhưng CPU dùng little-endian, không được tự ý đổi sang `ByteOrder.nativeOrder()` nếu mục tiêu là giải mã định dạng dữ liệu ban đầu.

Dùng byte order đúng với định dạng:

~~~java
IntVector vector = IntVector.fromMemorySegment(
        SPECIES,
        segment,
        byteOffset,
        ByteOrder.BIG_ENDIAN
);
~~~

Chọn sai byte order có thể tạo ra giá trị khác dù offset và bounds đều hợp lệ.

### 7.4. Masked access trên MemorySegment

Nếu segment không đủ một vector ở cuối, dùng overload nhận mask:

~~~java
for (int i = 0; i < count; i += SPECIES.length()) {
    VectorMask<Integer> mask = SPECIES.indexInRange(i, count);
    long byteOffset = (long) i * Integer.BYTES;

    IntVector vector = IntVector.fromMemorySegment(
            SPECIES,
            segment,
            byteOffset,
            ByteOrder.nativeOrder(),
            mask
    );

    vector.mul(2).intoMemorySegment(
            outputSegment,
            byteOffset,
            ByteOrder.nativeOrder(),
            mask
    );
}
~~~

Chỉ lane bật trong mask được đọc/ghi. Vẫn phải bảo đảm segment còn sống, thread được phép truy cập theo scope và byte offset không vượt phạm vi segment.

### 7.5. Căn chỉnh không thay thế bounds check

Một địa chỉ aligned vẫn có thể nằm ngoài vùng nhớ hợp lệ. Ngược lại, một offset unaligned vẫn có thể nằm trong vùng hợp lệ và được API hỗ trợ.

Trước khi load/store:

- Kiểm tra `byteOffset` không âm.
- Kiểm tra số byte cần đọc/ghi.
- Dùng mask cho tail.
- Chọn đúng `ByteOrder`.
- Bảo đảm `MemorySegment` chưa bị đóng.
- Tuân thủ thread ownership của arena.

## 8. Bảo toàn tính đúng khi vector hóa số nguyên

Phép toán vector được định nghĩa theo phép toán scalar tương ứng trên từng lane. Tuy nhiên, thuật toán có thể dựa vào các thuộc tính mà code vector cần giữ đúng.

### 8.1. Overflow của int và long

Phép cộng `int` trong Java có hành vi wrap-around khi tràn. Ví dụ:

~~~java
int scalar = Integer.MAX_VALUE + 1;
~~~

Kết quả là `Integer.MIN_VALUE`. Phép cộng lane-wise của `IntVector` cũng có ngữ nghĩa số học int tương ứng.

Nếu thuật toán scalar đang dựa vào wrap-around, vector hóa không nên tự ý đổi sang phép cộng saturating hoặc accumulator khác.

Ngược lại, nếu nghiệp vụ yêu cầu phát hiện overflow:

- `IntVector.add()` không thay thế `Math.addExact()`.
- Phải kiểm tra điều kiện tràn bằng logic phù hợp.
- Hoặc giữ phần kiểm tra overflow ở scalar path.
- Không bỏ kiểm tra chỉ vì vector path nhanh hơn.

### 8.2. Reduction và accumulator

Khi tính tổng, phải chọn đúng kiểu accumulator. Ví dụ:

- Tổng `int` với semantics int: chấp nhận wrap-around.
- Tổng các `int` nhưng kết quả cần `long`: dùng reduction trả về long và cộng tail vào long.
- Tổng có thể vượt giới hạn long: cần chiến lược số học khác, chẳng hạn kiểm tra overflow hoặc kiểu số lớn.

Nếu dùng masked reduction, truyền mask vào reduction để chỉ cộng lane hợp lệ. Điều này quan trọng hơn với phép `MIN`, `MAX`, `AND` hoặc các phép reduction mà giá trị mặc định của lane không phải identity.

## 9. Bảo toàn tính đúng với floating-point

Floating-point là nơi cần thận trọng nhất khi thay đổi thứ tự tính toán.

### 9.1. Phép cộng không kết hợp như số thực toán học

Trong số học thực:

\[
(a+b)+c = a+(b+c)
\]

Nhưng với `float`/`double`, mỗi phép cộng có thể làm tròn. Do đó:

\[
(a+b)+c \ne a+(b+c)
\]

với một số giá trị cụ thể.

Vector reduction có thể cộng các lane theo thứ tự khác với scalar loop. Kết quả có thể khác một vài bit dù cả hai đều tuân thủ floating-point arithmetic.

Nếu ứng dụng cần kết quả gần nhau trong một sai số cho phép, hãy định nghĩa tolerance và kiểm thử. Nếu cần bit-for-bit reproducibility, không được mặc định reduction vector tương đương phép cộng scalar tuần tự.

### 9.2. FMA có thể đổi kết quả

Fused multiply-add thực hiện:

\[
a \times b + c
\]

với một lần làm tròn thay vì làm tròn sau phép nhân rồi làm tròn tiếp sau phép cộng. Vector API có phép `fma()` tường minh.

Nếu scalar algorithm viết:

~~~java
float result = a * b + c;
~~~

và yêu cầu giữ đúng thứ tự làm tròn của phép nhân rồi phép cộng, không tự ý đổi sang `fma()` khi vector hóa.

~~~java
FloatVector result = va.mul(vb).add(vc);
~~~

Chỉ dùng:

~~~java
FloatVector result = va.fma(vb, vc);
~~~

khi thuật toán chấp nhận semantics fused multiply-add và đã kiểm thử sai số/độ chính xác theo yêu cầu.

### 9.3. NaN, infinity và signed zero

Vector API áp dụng phép toán floating-point theo semantics của lane. Dù vậy, khi thay đổi reduction order hoặc sử dụng FMA, kết quả liên quan đến NaN, infinity, `+0.0` và `-0.0` có thể khác với đường scalar.

Nếu các giá trị này xuất hiện trong dữ liệu:

- Tạo test riêng cho NaN và infinity.
- Kiểm tra signed zero nếu dấu của zero có ý nghĩa.
- Không so sánh NaN bằng `==`; dùng `Float.isNaN` hoặc `Double.isNaN`.
- Kiểm tra kết quả sau reduction, min/max và conversion.
- Xác định rõ policy cho NaN trước khi tối ưu.

## 10. Lane không hoạt động và giá trị mặc định

Khi masked load, lane bị tắt được gán giá trị mặc định của primitive type:

- `int`: 0
- `long`: 0L
- `float`: +0.0f
- `double`: +0.0d

Điều này tiện cho nhiều phép toán element-wise, nhưng không phải lúc nào cũng an toàn nếu dùng vector đó cho reduction.

Ví dụ:

- Cộng: 0 là identity, nhưng vẫn nên dùng masked reduction để thể hiện rõ lane hợp lệ.
- Nhân: 0 không phải identity.
- Min: 0 có thể làm sai kết quả nếu mọi giá trị hợp lệ đều dương.
- Max: 0 có thể làm sai kết quả nếu mọi giá trị hợp lệ đều âm.

Nếu chỉ lưu kết quả element-wise, masked store bảo đảm lane tắt không ghi ra mảng. Nếu thực hiện reduction hoặc shuffle sau masked load, phải xác định cách loại bỏ lane không hợp lệ.

## 11. Aliasing giữa input và output

Nếu input và output là các mảng khác nhau hoặc cùng một mảng nhưng cùng offset, vectorization thường dễ giữ đúng thứ tự. Tuy nhiên, khi các vùng chồng lấn lệch nhau, ghi một vector có thể ghi đè dữ liệu mà vector tiếp theo còn cần đọc.

Ví dụ:

~~~text
Input:  a[0..99]
Output: a[1..100]
~~~

Nếu vector loop xử lý block đầu và ghi vào `a[1..VLENGTH]`, nó có thể ghi đè một phần input của block tiếp theo.

Trước khi vector hóa, xác định hợp đồng aliasing:

| Trường hợp | Cách xử lý |
|---|---|
| Input/output là mảng khác nhau | An toàn nếu các range hợp lệ |
| Cùng mảng, cùng offset | Có thể xử lý in-place nếu mỗi block load đủ input trước khi store |
| Cùng mảng, output nằm sau input | Có nguy cơ ghi đè phần tử input chưa đọc |
| Cùng mảng, output nằm trước input | Cần phân tích hướng xử lý và ranh giới block |
| Nhiều input chồng lấn khác offset | Cần xác định thứ tự đọc/ghi hoặc dùng buffer tạm |

Nếu API không định nghĩa rõ hành vi khi overlap, hãy từ chối vùng overlap hoặc copy input sang buffer riêng. Không dựa vào một implementation SIMD cụ thể để suy luận rằng thứ tự load/store luôn giống scalar loop.

## 12. Ví dụ tổng hợp: affine transform với tail

Bài toán:

\[
out[i] = \alpha \times x[i] + \beta \times y[i]
\]

Mục tiêu là xử lý các mảng con có offset riêng, dùng preferred species, vector loop đầy đủ và scalar tail.

~~~java
import java.util.Objects;
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public final class VectorAffine {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    public static void transform(
            float[] x, int xOffset,
            float[] y, int yOffset,
            float[] out, int outOffset,
            int count,
            float alpha,
            float beta) {

        Objects.checkFromIndexSize(xOffset, count, x.length);
        Objects.checkFromIndexSize(yOffset, count, y.length);
        Objects.checkFromIndexSize(outOffset, count, out.length);

        int bound = SPECIES.loopBound(count);
        int i = 0;

        for (; i < bound; i += SPECIES.length()) {
            FloatVector vx = FloatVector.fromArray(
                    SPECIES, x, xOffset + i);
            FloatVector vy = FloatVector.fromArray(
                    SPECIES, y, yOffset + i);

            FloatVector result =
                    vx.mul(alpha).add(vy.mul(beta));

            result.intoArray(out, outOffset + i);
        }

        for (; i < count; i++) {
            out[outOffset + i] =
                    alpha * x[xOffset + i]
                    + beta * y[yOffset + i];
        }
    }
}
~~~

Code giữ riêng phép nhân và phép cộng, không chủ động đổi sang `fma()`. Dù vậy, nếu thuật toán có yêu cầu reproducibility nghiêm ngặt, vẫn cần kiểm thử trên các CPU/JDK mục tiêu và xác định tolerance theo domain.

Nếu các vùng input/output có thể overlap lệch offset, phải bổ sung kiểm tra hoặc buffer tạm trước khi dùng method này.

## 13. Kiểm thử tail và biên

Một vectorized method phải được kiểm thử với nhiều độ dài, đặc biệt quanh bội số của lane count.

Nếu species có 8 lane, các độ dài quan trọng gồm:

| Độ dài | Trường hợp cần kiểm tra |
|---:|---|
| 0 | Không có phần tử |
| 1 | Nhỏ hơn một vector |
| 7 | Thiếu một lane so với vector |
| 8 | Đúng một vector |
| 9 | Một vector và một phần tử dư |
| 15 | Một vector và gần đủ vector thứ hai |
| 16 | Đúng hai vector |
| 17 | Hai vector và một phần tử dư |
| 31 | Gần bốn vector |
| 32 | Đúng bốn vector |
| 33 | Bốn vector và một phần tử dư |

Không giả định species có 8 lane trong test. Tạo test theo `SPECIES.length()`:

~~~java
int lanes = SPECIES.length();

int[] lengths = {
        0,
        1,
        Math.max(0, lanes - 1),
        lanes,
        lanes + 1,
        2 * lanes - 1,
        2 * lanes,
        2 * lanes + 1
};
~~~

### 13.1. So sánh với scalar reference

Với mỗi test:

1. Tạo input xác định hoặc seed ngẫu nhiên cố định.
2. Chạy scalar implementation.
3. Chạy vector implementation.
4. So sánh toàn bộ output.
5. Kiểm tra các phần tử ngoài output range không bị thay đổi.
6. Lặp lại với offset khác 0.
7. Lặp lại với độ dài nhỏ hơn, bằng và lớn hơn lane count.

Với `int` và `long`, có thể so sánh chính xác từng phần tử nếu hai implementation có cùng overflow semantics. Với `float`/`double`, xác định chính sách so sánh tuyệt đối, tương đối hoặc ULP phù hợp với thuật toán.

### 13.2. Các giá trị biên cần có

- `Integer.MIN_VALUE`, `Integer.MAX_VALUE`.
- Số âm, số 0 và số dương.
- `Float.MIN_VALUE`, `Float.MAX_VALUE`.
- `NaN`, `+Infinity`, `-Infinity`.
- `+0.0`, `-0.0`.
- Offset đầu mảng, offset giữa mảng và offset gần cuối.
- Input/output có range vừa khít cuối mảng.
- MemorySegment có byte size vừa đủ, thiếu một lane hoặc có phần dư.

## 14. Benchmark để xác định căn chỉnh có đáng tối ưu không

Không kết luận vectorized code nhanh hơn chỉ vì mỗi vòng xử lý nhiều lane. Cần benchmark scalar và vector trên cùng JDK, CPU và workload.

Các yếu tố cần cố định:

- JDK vendor, version và build.
- CPU architecture và tập lệnh được hỗ trợ.
- Kích thước dữ liệu.
- Heap, GC và JVM options.
- Warm-up và số lần đo.
- Dữ liệu aligned/unaligned.
- Tỷ lệ tail so với số phần tử đầy đủ.
- Cache state và memory bandwidth.

### 14.1. Benchmark các trường hợp riêng

| Trường hợp | Mục đích |
|---|---|
| Scalar baseline | Đo implementation tham chiếu |
| Vector full blocks | Đo throughput khi không có tail |
| Vector + scalar tail | Đo chi phí xử lý phần dư |
| Masked vector loop | Đo chi phí mask trên mọi vòng |
| Aligned memory segment | Đo truy cập với base alignment có chủ đích |
| Unaligned offset | Đo tác động của offset khác ranh giới vector |
| Dữ liệu nhỏ | Xem overhead setup có lấn át lợi ích SIMD không |
| Dữ liệu lớn | Xem giới hạn memory bandwidth |

Dùng JMH hoặc benchmark harness tương đương để tránh đo sai do JIT warm-up, dead-code elimination hoặc benchmark loop tự viết quá đơn giản. Trả về hoặc tiêu thụ kết quả để phép tính không bị loại bỏ.

### 14.2. Đo nhiều kích thước

Vectorization có thể có overhead ở dữ liệu nhỏ. Nên đo:

- Nhỏ hơn một vector.
- Một vài vector.
- Vài nghìn phần tử.
- Hàng triệu phần tử.
- Dataset gần kích thước production.

Nếu workload có nhiều mảng rất ngắn, scalar code có thể nhanh hơn vì không phải thiết lập vector path. Có thể dùng ngưỡng kích thước sau khi benchmark để chọn scalar hoặc vector path.

### 14.3. Kiểm tra generated code khi cần

Nếu benchmark cho thấy Vector API không tăng tốc:

- Xác minh JDK có module `jdk.incubator.vector`.
- Xác minh CPU có hỗ trợ shape/ISA phù hợp.
- Dùng preferred species.
- Kiểm tra method có được JIT compile không.
- Kiểm tra loop có bị ngăn cản bởi bounds checks, aliasing hoặc method call không inline.
- Dùng công cụ phân tích assembly/JIT phù hợp với nền tảng nếu cần.

Không dùng một kết quả benchmark từ CPU khác để khẳng định performance trên production.

## 15. Biên dịch và chạy Vector API

Vector API là incubator module, không phải preview language feature. Vì vậy, không dùng `--enable-preview` để bật nó.

### 15.1. Dùng JDK 27 hiện hành

~~~bash
javac --release 27 --add-modules jdk.incubator.vector \
      -d out VectorAffine.java

java --add-modules jdk.incubator.vector \
     -cp out VectorAffine
~~~

### 15.2. Dùng JDK 25

JDK 25 có Vector API Tenth Incubator theo JEP 508:

~~~bash
javac --release 25 --add-modules jdk.incubator.vector \
      -d out VectorAffine.java

java --add-modules jdk.incubator.vector \
     -cp out VectorAffine
~~~

### 15.3. Nếu dùng module-info.java

Module ứng dụng cần khai báo:

~~~java
module com.example.vectorapp {
    requires jdk.incubator.vector;
}
~~~

Khi chạy modular application, bảo đảm module incubator được resolve trong runtime image và module path. Với classpath application, dùng `--add-modules jdk.incubator.vector`.

### 15.4. Các mốc incubator

| JDK | JEP | Trạng thái |
|---|---|---|
| JDK 16 | JEP 338 | Incubator lần đầu |
| JDK 17–24 | JEP 414, 417, 426, 438, 448, 460, 469, 489 | Các lần incubator tiếp theo |
| JDK 25 | JEP 508 | Tenth Incubator |
| JDK 26 | JEP 529 | Eleventh Incubator |
| JDK 27 | JEP 537 | Twelfth Incubator |

Vector API tiếp tục ở incubator trong JDK 27. Do đó, khi nâng JDK, biên dịch lại, chạy test correctness và benchmark lại. Không xem binary/source phụ thuộc incubator là hợp đồng tương thích dài hạn như API Java SE permanent.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `IndexOutOfBoundsException` ở vector cuối | Load/store vector đầy đủ khi không còn đủ lane | Dùng `loopBound()` + scalar tail hoặc mask |
| Output cuối bị ghi đè | Store không dùng mask | Dùng masked `intoArray` hoặc scalar tail |
| Kết quả sai khi offset khác 0 | Dùng chung một offset cho mọi mảng | Dùng offset riêng cho từng vùng |
| Lỗi chỉ xuất hiện với length không chia hết lane count | Tail chưa được xử lý | Kiểm tra `bound`, mask và vòng scalar |
| Kết quả sum khác scalar | Reduction đổi thứ tự cộng hoặc overflow khác kiểu | Xác định accumulator và tolerance |
| Float result lệch vài ULP | Reassociation, FMA hoặc rounding | Kiểm tra thứ tự phép toán và chính sách sai số |
| Data native bị đảo byte | Chọn sai `ByteOrder` | Dùng byte order theo định dạng nguồn |
| MemorySegment báo lỗi scope/thread | Arena đã đóng hoặc confined segment bị truy cập từ thread khác | Quản lý lifetime và thread ownership |
| SIMD không nhanh hơn scalar | CPU không hỗ trợ shape, dữ liệu nhỏ hoặc memory-bound | Benchmark và dùng preferred species |
| Sai khi input/output cùng mảng | Vùng overlap lệch offset làm ghi đè dữ liệu chưa đọc | Xác định alias contract hoặc dùng buffer tạm |
| Compile không tìm thấy vector package | Chưa add incubator module | Dùng `--add-modules jdk.incubator.vector` |
| Thêm `--enable-preview` nhưng vẫn không thấy module | Vector API là incubator module, không phải preview feature | Dùng `--add-modules` |
| Dùng snippet cũ không compile trên JDK mới | API incubator đã thay đổi | Đọc JavaDoc đúng release và migrate |

## 17. Ma trận kiểm thử nghiệm thu

| Mã | Kịch bản | Kết quả mong đợi |
|---|---|---|
| V1 | Mảng rỗng | Không load/store, trả kết quả đúng |
| V2 | Mảng ngắn hơn một vector | Tail được xử lý đầy đủ |
| V3 | Độ dài đúng một vector | Một vector operation, không tail |
| V4 | Độ dài là bội số của lane count | Không đọc vượt biên |
| V5 | Độ dài có tail một phần | Mọi phần tử dư được xử lý đúng |
| V6 | Offset input khác 0 | Đọc đúng range |
| V7 | Offset output khác 0 | Chỉ ghi đúng output range |
| V8 | Masked load ở cuối mảng | Lane ngoài range không bị đọc |
| V9 | Masked store ở cuối mảng | Lane ngoài range không bị ghi |
| V10 | Integer boundary values | Overflow đúng semantics scalar |
| V11 | Floating NaN/infinity/signed zero | Kết quả theo policy đã định |
| V12 | Float reduction | Sai số nằm trong tolerance |
| V13 | MemorySegment native aligned | Load/store đúng byte order |
| V14 | MemorySegment offset khác vector boundary | Không lỗi bounds, dữ liệu đúng |
| V15 | MemorySegment tail masked | Chỉ lane hợp lệ được truy cập |
| V16 | Segment đã đóng | Runtime từ chối truy cập |
| V17 | Confined segment từ thread khác | Runtime từ chối truy cập |
| V18 | Input/output cùng range | Kết quả in-place đúng |
| V19 | Input/output overlap lệch offset | Tuân theo contract overlap hoặc bị từ chối |
| V20 | Scalar vs vector benchmark | Có số liệu latency/throughput có thể lặp lại |

## 18. Bài thực hành tổng hợp

Bạn có một pipeline xử lý dữ liệu cảm biến. Hai mảng `temperature` và `calibration` chứa các giá trị `float`; kết quả cần tính:

\[
result[i] = temperature[i] \times scale + calibration[i]
\]

Dữ liệu có thể bắt đầu ở offset khác 0 và số phần tử không cố định.

Thực hiện:

1. Viết scalar implementation làm chuẩn.
2. Viết vector implementation dùng `FloatVector.SPECIES_PREFERRED`.
3. Dùng `loopBound(count)` để xử lý vector blocks và scalar tail.
4. Viết phiên bản masked loop dùng `indexInRange()`.
5. Kiểm tra các độ dài 0, 1, lanes−1, lanes, lanes+1, 2×lanes−1, 2×lanes và 2×lanes+1.
6. Thử offset khác 0 cho cả hai input và output.
7. Thử dữ liệu có NaN, infinity, signed zero và các giá trị gần giới hạn.
8. So sánh vector/scalar với tolerance phù hợp.
9. Thử dùng `MemorySegment` native có alignment 64 byte và byte order tường minh.
10. Kiểm tra tail masked trên segment và lifetime của arena.
11. Benchmark scalar, vector-tail và masked vector bằng JMH.
12. Viết quyết định kỹ thuật: khi nào dùng scalar path, khi nào dùng vector path và giới hạn nền tảng.

**Sản phẩm nghiệm thu:** source code scalar/vector, test matrix V1–V20, kết quả correctness, JMH report, cấu hình JDK/module và ghi chú về alignment/byte order.

## 19. Checklist khi đưa Vector API vào thuật toán

- Kiểm tra trạng thái incubator của đúng JDK triển khai.
- Dùng `SPECIES_PREFERRED` cho thuật toán tổng quát.
- Không hard-code số lane hoặc giả định lane count là lũy thừa của hai.
- Dùng `loopBound()` hoặc mask cho tail.
- Kiểm tra offset và count của từng input/output range.
- Dùng masked store khi chỉ một phần vector lane hợp lệ.
- Không để lane mặc định ảnh hưởng reduction.
- Phân tích overflow và kiểu accumulator.
- Xác định chính sách floating-point, FMA và reduction order.
- Kiểm tra aliasing giữa input/output.
- Phân biệt array element offset và MemorySegment byte offset.
- Chọn byte order theo định dạng dữ liệu.
- Quản lý arena lifetime và thread ownership.
- Đo aligned/unaligned access thay vì giả định.
- Benchmark trên CPU/JDK mục tiêu và giữ scalar baseline.
- Biên dịch với `--add-modules jdk.incubator.vector`; không nhầm với preview flag.
- Chạy lại correctness và performance tests khi nâng JDK.

## Tài liệu tham khảo chính thức

- [JEP 537 — Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537): trạng thái Vector API trong JDK 27.
- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): xác nhận JEP 537 là Twelfth Incubator.
- [Oracle Java SE 27 — Package jdk.incubator.vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html): lane-wise operations, masked operations, species, tail loop và performance notes.
- [Oracle Java SE 27 — VectorSpecies](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html): `SPECIES_PREFERRED`, `length()`, `loopBound()`, `indexInRange()`.
- [Oracle Java SE 27 — IntVector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html): masked array/memory-segment loads and stores, reduction và lane operations.
- [Oracle Java SE 27 — Vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html): vector shapes, lane semantics, conversions, reductions và cross-lane operations.
- [Oracle Java SE 27 — VectorMask](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorMask.html): mask semantics và thao tác trên lane.
- [Oracle Java SE 27 — Arena](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Arena.html): cấp phát native MemorySegment với byte alignment và quản lý lifetime.
- [Oracle Java SE 27 — MemorySegment](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemorySegment.html): bounds, byte layout, scope và truy cập bộ nhớ.
- [JEP 529 — Vector API (Eleventh Incubator)](https://openjdk.org/jeps/529): lần incubator trong JDK 26.
- [JEP 508 — Vector API (Tenth Incubator)](https://openjdk.org/jeps/508): lần incubator trong JDK 25.
- [Oracle Java SE 25 — Package jdk.incubator.vector](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html): API Vector được cung cấp trong JDK 25.
- [JEP 11 — Incubator Modules](https://openjdk.org/jeps/11): mục đích và vòng đời của incubator modules.
