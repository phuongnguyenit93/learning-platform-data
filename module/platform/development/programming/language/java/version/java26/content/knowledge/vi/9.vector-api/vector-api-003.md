# SIMD, lane và quan hệ với phép tính vô hướng

Vector API cho phép viết phép tính trên nhiều phần tử cùng kiểu bằng một biểu thức vector. Thay vì mô tả một phép nhân cho từng cặp số như vòng lặp vô hướng (*scalar loop*), chương trình nạp một nhóm phần tử vào các **lane** của vector rồi áp dụng cùng phép nhân lên tất cả lane. Khi CPU và JIT hỗ trợ, JVM có thể biên dịch phép tính đó thành lệnh SIMD (*Single Instruction, Multiple Data*) để phần cứng xử lý nhiều phần tử trong cùng một thao tác.

Vector API thuộc module `jdk.incubator.vector`. Trong JDK 26, API ở vòng **Eleventh Incubator — JEP 529**; JDK 27 tiếp tục ở vòng **Twelfth Incubator — JEP 537**. Đây vẫn là API incubator, có thể thay đổi hoặc bị loại bỏ trong các bản JDK tương lai. Bài này giải thích mô hình SIMD, lane và cách đối chiếu với scalar bằng API của JDK 26/27.

## 1. Từ scalar đến SIMD

Một phép tính scalar xử lý từng giá trị riêng lẻ. Ví dụ nhân hai mảng:

```java
static void scalarMultiply(float[] a, float[] b, float[] result) {
    for (int i = 0; i < a.length; i++) {
        result[i] = a[i] * b[i];
    }
}
```

Ở mức ý nghĩa, mỗi vòng lặp thực hiện một phép nhân `a[i] * b[i]` rồi ghi một kết quả. CPU có thể thực thi nhiều lệnh khác nhau chồng lấp nhờ pipeline, nhưng mã Java đang diễn tả phép toán theo từng phần tử.

SIMD thay đổi cách biểu diễn dữ liệu và phép toán. Một vector chứa nhiều giá trị cùng kiểu; một phép toán vector như `va.mul(vb)` áp dụng phép nhân scalar tương ứng cho từng cặp lane:

```text
Scalar:
  a[0] * b[0] -> result[0]
  a[1] * b[1] -> result[1]
  a[2] * b[2] -> result[2]
  a[3] * b[3] -> result[3]

SIMD với 4 lane:
  [a0, a1, a2, a3]
        *
  [b0, b1, b2, b3]
        =
  [r0, r1, r2, r3]
```

Với SIMD, cùng một loại lệnh được áp dụng trên nhiều phần tử độc lập. Các lane có thể được xử lý song song bởi vector registers và vector instructions của CPU. Đây là **song song ở mức dữ liệu**. Nó không đồng nghĩa với việc Java tạo thêm bốn thread hoặc tự phân chia công việc lên nhiều core. Một luồng Java có thể phát ra lệnh SIMD xử lý nhiều lane.

Không nên hiểu “một lệnh xử lý nhiều lane” là luôn hoàn thành trong đúng một chu kỳ CPU. Số chu kỳ, throughput và tốc độ thực tế phụ thuộc vi kiến trúc, loại phép toán, dữ liệu và băng thông bộ nhớ.

## 2. Lane, vector shape và species

Một vector là một dãy có số lượng phần tử cố định, cùng kiểu phần tử. Mỗi phần tử trong dãy được gọi là một **lane**. Lane được đánh chỉ số từ `0` đến `length() - 1`.

Ba khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Element type (`ETYPE`) | Kiểu primitive của mỗi lane | `float`, `int`, `double` |
| Vector shape (`VSHAPE`) | Dung lượng vector tính theo bit | 128 bit, 256 bit, 512 bit |
| Vector length (`VLENGTH`) | Số lane trong vector | Vector 256 bit chứa 8 lane `float` 32 bit |

Ví dụ minh họa: một vector `float` có shape 256 bit chứa `256 / 32 = 8` lane. Nếu cùng shape nhưng mỗi lane là `double` 64 bit thì vector có `256 / 64 = 4` lane.

Một **`VectorSpecies<E>`** đại diện cho một tổ hợp element type và shape cụ thể. Các vector tham gia một phép toán lane-wise thường phải có cùng species để lane tương ứng được ghép đúng vị trí.

Không nên mặc định CPU nào cũng hỗ trợ shape 256 hoặc 512 bit. Shape phù hợp phụ thuộc kiến trúc và khả năng của nền tảng. Vì vậy, với mã portable, nên dùng species được chọn theo nền tảng:

```java
private static final VectorSpecies<Float> SPECIES =
        FloatVector.SPECIES_PREFERRED;
```

`SPECIES_PREFERRED` chọn species có shape được runtime ưu tiên cho kiểu phần tử đó. Số lane có thể khác nhau giữa máy phát triển, CI và production. Luôn lấy số lane từ `SPECIES.length()` thay vì hard-code `4`, `8` hoặc `16`.

## 3. Lane-wise operation là phép tính scalar được lặp trên từng lane

Phần lớn phép toán Vector API là *lane-wise*: cùng một toán tử scalar được áp dụng độc lập cho các lane tương ứng của vector đầu vào.

Ví dụ hai vector có bốn lane:

```text
va = [1.0, 2.0, 3.0, 4.0]
vb = [10.0, 20.0, 30.0, 40.0]

va.mul(vb)
   = [1*10, 2*20, 3*30, 4*40]
   = [10.0, 40.0, 90.0, 160.0]
```

Đây là cách hiểu trực tiếp nhất về quan hệ giữa scalar và SIMD: phép nhân scalar vẫn là phép toán nền tảng; vector operation phân phối nó trên các lane.

Vector API cũng có các nhóm thao tác khác:

- **Comparison**: so sánh lane tương ứng và tạo `VectorMask`, ví dụ lane nào lớn hơn 0.
- **Masked operation**: chỉ thực hiện phép toán ở các lane được bật trong mask.
- **Reduction**: gộp nhiều lane thành một giá trị scalar, ví dụ cộng tất cả lane bằng `reduceLanes`.
- **Cross-lane operation**: di chuyển hoặc sắp xếp dữ liệu giữa các lane, ví dụ `rearrange` với `VectorShuffle`.

Các phép reduction đặc biệt quan trọng khi chuyển từ SIMD về scalar. Ví dụ tính tổng: trước hết cộng các phần tử theo lane, sau đó gộp các lane thành một số duy nhất. Với phép toán dấu phẩy động, thứ tự cộng có thể thay đổi và làm kết quả khác đôi chút do quy tắc làm tròn; không nên mặc định reduction luôn cho cùng bit pattern với vòng lặp scalar tuần tự.

## 4. So sánh cùng một thuật toán scalar và vector

Ví dụ sau thực hiện phép nhân từng phần tử của hai mảng `float`. Hai phương thức có cùng kết quả toán học, nhưng phần xử lý dữ liệu chính được diễn tả khác nhau.

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public final class SimdMultiply {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    private SimdMultiply() {}

    private static void checkLengths(float[] a, float[] b, float[] result) {
        if (a.length != b.length || a.length != result.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }
    }

    static void scalarMultiply(float[] a, float[] b, float[] result) {
        checkLengths(a, b, result);

        for (int i = 0; i < a.length; i++) {
            result[i] = a[i] * b[i];
        }
    }

    static void vectorMultiply(float[] a, float[] b, float[] result) {
        checkLengths(a, b, result);

        int i = 0;
        int upperBound = SPECIES.loopBound(a.length);

        // Mỗi vòng xử lý một nhóm SPECIES.length() phần tử.
        for (; i < upperBound; i += SPECIES.length()) {
            FloatVector va = FloatVector.fromArray(SPECIES, a, i);
            FloatVector vb = FloatVector.fromArray(SPECIES, b, i);
            FloatVector vc = va.mul(vb);
            vc.intoArray(result, i);
        }

        // Xử lý các phần tử còn lại chưa đủ một vector.
        for (; i < a.length; i++) {
            result[i] = a[i] * b[i];
        }
    }

    public static void main(String[] args) {
        float[] a = {1, 2, 3, 4, 5};
        float[] b = {10, 20, 30, 40, 50};
        float[] result = new float[a.length];

        vectorMultiply(a, b, result);
        System.out.println(java.util.Arrays.toString(result));
    }
}
```

Kết quả:

```text
[10.0, 40.0, 90.0, 160.0, 250.0]
```

Trong ví dụ:

1. `SPECIES_PREFERRED` chọn shape phù hợp với nền tảng hiện tại.
2. `SPECIES.length()` cho biết mỗi vector xử lý bao nhiêu phần tử.
3. `SPECIES.loopBound(a.length)` trả về giới hạn lớn nhất không vượt quá độ dài mảng và chia hết cho số lane.
4. Vòng vector chỉ chạy trên vùng có đủ một vector hoàn chỉnh.
5. Vòng scalar cuối xử lý phần đuôi có ít hơn `SPECIES.length()` phần tử.

Nếu preferred species có 8 lane nhưng mảng chỉ có 5 phần tử, `loopBound(5)` là `0`; toàn bộ mảng được xử lý bằng scalar tail. Nếu mảng có 19 phần tử và species có 8 lane, hai vòng vector xử lý 16 phần tử, vòng scalar xử lý 3 phần tử cuối. Cùng mã vẫn hoạt động khi số lane khác nhau trên một máy khác.

## 5. Vì sao cần scalar tail hoặc mask?

Độ dài mảng bất kỳ thường không chia hết cho số lane. Nếu cứ gọi `fromArray` hoặc `intoArray` với một vector đầy đủ ở vị trí cuối, thao tác có thể đọc hoặc ghi vượt giới hạn mảng.

Có hai cách xử lý phổ biến:

**Cách 1 — vector loop và scalar tail:** dùng `loopBound()` cho các vector đầy đủ, rồi dùng vòng scalar xử lý phần còn lại. Cách này thường phù hợp khi phần lớn vòng lặp có vector đầy đủ và chỉ một phần đuôi ngắn cần xử lý.

**Cách 2 — masked vector operation:** tạo `VectorMask` để chỉ bật các lane nằm trong phạm vi mảng. Ví dụ:

```java
static void vectorMultiplyWithMask(float[] a, float[] b, float[] result) {
    if (a.length != b.length || a.length != result.length) {
        throw new IllegalArgumentException("Array lengths must match");
    }

    for (int i = 0; i < a.length; i += SPECIES.length()) {
        var mask = SPECIES.indexInRange(i, a.length);
        var va = FloatVector.fromArray(SPECIES, a, i, mask);
        var vb = FloatVector.fromArray(SPECIES, b, i, mask);
        va.mul(vb).intoArray(result, i, mask);
    }
}
```

`indexInRange(i, a.length)` tạo mask bật những lane có chỉ số tương ứng nằm trong mảng. Các lane không được bật sẽ không tham gia thao tác masked; vì vậy lượt cuối không đọc hoặc ghi ngoài phạm vi.

Mask hữu ích khi thuật toán vốn có điều kiện theo từng lane hoặc cần xử lý vùng biên gọn trong một vòng lặp. Tuy nhiên, dùng mask trong mọi vòng có thể tạo thêm chi phí. Tài liệu Vector API minh họa rằng vector loop không mask cộng scalar tail có thể hiệu quả hơn trên mảng lớn. Hãy đo trên workload thực tế thay vì mặc định một cách luôn nhanh hơn.

## 6. Scalar fallback và tính portable

Vector API được thiết kế để mã Java có thể chạy đúng trên nền tảng có hoặc không có vector instruction chuyên dụng. Khi JIT có thể biên dịch thao tác vector thành lệnh phần cứng phù hợp, phép tính có thể được tăng tốc. Khi không thể biên dịch shape hoặc operation đó thành vector instruction, implementation có scalar implementation dự phòng.

Điều này tạo ra hai thuộc tính khác nhau:

- **Tính đúng đắn:** mã vẫn có thể chạy đúng khi không có phần cứng SIMD phù hợp.
- **Hiệu năng:** không có SIMD chuyên dụng thì thường không có lợi ích tăng tốc đặc biệt; scalar fallback không bảo đảm nhanh hơn vòng scalar được viết trực tiếp.

Ví dụ, nếu code cố định `IntVector.SPECIES_512` nhưng CPU/JVM chỉ hỗ trợ vector shape 256 bit, phép toán không nhất thiết được ánh xạ thành lệnh 512 bit. Implementation có thể dùng scalar fallback. Dùng `SPECIES_PREFERRED` giúp runtime chọn shape phù hợp hơn và tránh giả định sai về độ rộng vector.

Đừng nhầm scalar fallback với scalar tail:

| Khái niệm | Mục đích |
| --- | --- |
| Scalar fallback | Runtime thực hiện một vector operation bằng triển khai scalar khi không thể sinh vector instruction phù hợp |
| Scalar tail | Mã ứng dụng xử lý phần tử cuối không đủ một vector đầy đủ |

Hai cơ chế có thể cùng xuất hiện trong một chương trình nhưng giải quyết hai vấn đề khác nhau.

## 7. SIMD không phải đa luồng

Vector API và concurrency giải quyết hai chiều khác nhau của hiệu năng:

| SIMD / Vector API | Multithreading / concurrency |
| --- | --- |
| Song song dữ liệu: một phép toán trên nhiều lane | Song song tác vụ: nhiều luồng thực thi các công việc khác nhau |
| Thường khai thác vector register và vector instruction của một CPU core | Có thể phân phối công việc trên nhiều core |
| Thích hợp cho vòng lặp số học, xử lý ảnh/tín hiệu, mã hóa, tính toán ma trận | Thích hợp cho request độc lập, I/O đồng thời, nhiều tác vụ nền |
| Không tự tạo thread | Có quản lý thread, scheduling và đồng bộ |

Hai cách có thể kết hợp. Một ứng dụng có thể dùng Structured Concurrency để xử lý nhiều request độc lập, trong mỗi tác vụ lại dùng Vector API cho phép tính số học trên mảng dữ liệu lớn. Nhưng không nên dùng SIMD chỉ để thay thế việc chia tác vụ độc lập lên nhiều thread.

## 8. Khi nào Vector API có thể hữu ích?

Vector API phù hợp nhất với workload có nhiều phần tử cùng kiểu và cùng phép toán, ví dụ:

- Nhân, cộng, chuẩn hóa hoặc chuyển đổi các mảng số.
- Tính tổng tích vô hướng (dot product), reduction và một số phép toán tuyến tính.
- Xử lý ảnh, âm thanh và tín hiệu theo từng nhóm pixel/sample.
- Một số bước trong mã hóa, checksum, lọc dữ liệu và phân tích số.
- Các thuật toán xử lý dữ liệu có cấu trúc đều, ít nhánh và có thể diễn tả bằng lane-wise operations.

Vector API thường ít hữu ích hơn khi:

- Mỗi phần tử có luồng xử lý rất khác nhau hoặc nhiều nhánh khó biểu diễn bằng mask.
- Workload bị giới hạn bởi I/O hoặc truy cập bộ nhớ không liên tục thay vì phép tính.
- Mảng quá nhỏ, chi phí tạo/đọc dữ liệu lớn hơn lợi ích vectorization.
- Phép toán không có hỗ trợ vector tốt trên nền tảng đích và scalar fallback được sử dụng.

HotSpot cũng có thể tự vector hóa một số vòng lặp scalar đơn giản. Vì vậy, không thể kết luận rằng viết lại bằng Vector API luôn nhanh hơn. Hãy giữ một scalar baseline và benchmark cả hai trên JDK, CPU, kích thước dữ liệu và kiểu dữ liệu triển khai thực tế. Với benchmark Java, dùng JMH, có warmup và nhiều lần đo; tránh chỉ chạy một lần bằng `System.nanoTime()` rồi kết luận.

## 9. Những điểm cần lưu ý khi tối ưu

- **Giữ species ổn định:** khai báo species trong `static final` để runtime compiler có thể tối ưu việc tạo và sử dụng vector.
- **Không hard-code số lane:** dùng `SPECIES.length()` và `SPECIES.loopBound()`.
- **Cùng species cho các vector đầu vào:** lane-wise operation thường yêu cầu vector có cùng shape và số lane.
- **Hạn chế chuyển đổi và di chuyển lane không cần thiết:** conversion, shuffle và cross-lane operation có thể làm tăng chi phí.
- **Cân nhắc memory bandwidth:** tăng số phép tính SIMD không giúp nhiều nếu chương trình đã bị giới hạn bởi tốc độ đọc/ghi bộ nhớ.
- **Đo đúng phép toán:** với floating point reduction, thứ tự cộng có thể khác scalar loop và ảnh hưởng sai số làm tròn.
- **Tránh giả định identity:** Vector, VectorMask, VectorShuffle và VectorSpecies là value-based classes. Không dùng `==` để so sánh giá trị vector; dùng `equals()` khi cần so sánh bằng.
- **Không giữ vector object trong cấu trúc dữ liệu tùy tiện:** ưu tiên local variables và parameters; lưu trong field/array có thể gây bất lợi cho tối ưu.

## 10. Trạng thái incubator và cách bật module

Vector API chưa phải API Java SE ổn định. Trong JDK 26, JEP 529 tiếp tục incubate lần thứ 11; JDK 27 tiếp tục bằng JEP 537, lần thứ 12. JDK 27 vẫn cung cấp module `jdk.incubator.vector`; vòng incubator tiếp tục vì API còn phụ thuộc các khả năng của Project Valhalla trước khi có thể hoàn thiện thiết kế lâu dài.

Để biên dịch chương trình classpath trên JDK 26 hoặc JDK 27, thêm module khi biên dịch:

```bash
javac --add-modules jdk.incubator.vector -d out src/SimdMultiply.java
```

Khi chạy, cũng thêm module vào module graph:

```bash
java --add-modules jdk.incubator.vector -cp out SimdMultiply
```

Vector API là **incubator module**, vì vậy cần `--add-modules jdk.incubator.vector`; không cần `--enable-preview` chỉ để dùng Vector API. Nếu chạy trên custom runtime image tạo bằng `jlink`, image phải chứa module `jdk.incubator.vector`.

Do API vẫn incubator, tránh để các kiểu `jdk.incubator.vector.*` xuất hiện trong public API của thư viện dùng lâu dài nếu không kiểm soát được phiên bản JDK. Có thể đặt phần vectorized computation sau một abstraction nội bộ và giữ scalar implementation làm phương án dự phòng. Khi nâng JDK, đọc lại JEP, API Specification và biên dịch/test lại trên JDK đích.

## Ghi nhớ

- Scalar loop diễn tả phép toán theo từng phần tử; SIMD áp dụng cùng phép toán trên nhiều lane.
- Lane là một phần tử của vector; `VectorSpecies` xác định element type và vector shape.
- `SPECIES_PREFERRED` giúp mã thích nghi với shape phù hợp của nền tảng; không hard-code số lane.
- `loopBound()` cho phép xử lý các vector đầy đủ, sau đó dùng scalar tail cho phần dư.
- `VectorMask` xử lý lane có điều kiện hoặc phần tử cuối chưa đủ một vector.
- Scalar fallback giữ tính đúng khi runtime không thể sinh lệnh vector, nhưng không bảo đảm tăng tốc.
- SIMD là song song dữ liệu, không phải tạo thêm Java thread.
- Vector API vẫn là incubator: JDK 26 JEP 529, JDK 27 JEP 537; thêm module bằng `--add-modules jdk.incubator.vector`.

## Tài liệu tham khảo

- [JEP 529 — Vector API (Eleventh Incubator)](https://openjdk.org/jeps/529) — trạng thái và mục tiêu Vector API trong JDK 26.
- [JEP 537 — Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537) — vòng incubator tiếp theo trong JDK 27.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html) — xác nhận JEP 529 là Eleventh Incubator.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html) — xác nhận JEP 537 là Twelfth Incubator.
- [Package `jdk.incubator.vector`, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html) — mô hình lane, ví dụ nhân mảng, mask, scalar tail và performance notes.
- [Class `Vector`, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html) — SIMD, lane-wise operations, vector shape, species và reduction.
- [Class `VectorSpecies`, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html) — preferred species, `length()`, `loopBound()` và `indexInRange()`.
- [Class `VectorMask`, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorMask.html) — biểu diễn điều kiện theo lane.
- [Java 26 in IntelliJ IDEA](https://blog.jetbrains.com/idea/2026/03/java-26-in-intellij-idea/) và [Java 27 in IntelliJ IDEA](https://blog.jetbrains.com/idea/2026/09/java-27-in-intellij-idea/) — cách thêm incubator module khi chạy và trạng thái Vector API giữa hai bản JDK.
