# Trạng thái incubator lần thứ mười của Vector API trong JDK 25

**Vector API** cho phép viết phép toán trên nhiều phần tử cùng lúc theo mô hình **SIMD (Single Instruction, Multiple Data)**. Thay vì chỉ mô tả một phép cộng cho từng phần tử, code Java mô tả phép cộng trên một vector gồm nhiều lane; JIT có thể biên dịch phép toán đó thành chỉ thị vector phù hợp với CPU đang chạy.

Trong JDK 25, Vector API bước vào **lần incubator thứ mười** theo **JEP 508**. Đây là API thử nghiệm trong module riêng `jdk.incubator.vector`, không phải preview feature và cũng chưa phải API Java SE ổn định. Đến thời điểm hiện tại, JDK 27 đã tiếp tục lần incubator thứ mười hai theo JEP 537; API vẫn đang incubate. Vì vậy, khi học trạng thái của JDK 25, cần hiểu cả mốc lịch sử JEP 508 lẫn trạng thái mới nhất để không nhầm một API incubator với API đã được chuẩn hóa.

Bài thuộc chương **Vector API** của module **Java 25** (`JAVA_VERSION_JAVA25`), theo đề bài **“Trạng thái incubator lần thứ mười của Vector API trong JDK 25”**. Nội dung giải thích ý nghĩa của incubator, tiến trình từ JDK 16 đến JDK 27, cách bật module và kiểm tra một ví dụ SIMD hiện hành, giới hạn phần cứng, tính đúng đắn số học và cách đánh giá hiệu năng. Các ví dụ dùng API vẫn có trong JDK 25 và JDK 27; không dùng các dạng API cũ đã thay đổi qua những vòng incubator trước.

## 1. SIMD giải quyết bài toán gì?

Nhiều chương trình xử lý một tập dữ liệu bằng cách lặp lại cùng một phép toán trên từng phần tử:

```java
for (int i = 0; i < a.length; i++) {
    result[i] = a[i] + b[i];
}
```

Đây là cách viết scalar: mỗi vòng lặp xử lý một cặp phần tử. Với SIMD, CPU có thể thực hiện một phép toán trên nhiều lane trong một chỉ thị vector. Ví dụ, một vector 256 bit có thể chứa tám giá trị `float` 32 bit; phép cộng vector có thể cộng tám cặp phần tử trong cùng một thao tác SIMD.

```text
Scalar:
  a[0] + b[0] -> result[0]
  a[1] + b[1] -> result[1]
  a[2] + b[2] -> result[2]
  a[3] + b[3] -> result[3]

SIMD vector:
  [a0, a1, a2, a3] + [b0, b1, b2, b3]
                |
                v
  [a0+b0, a1+b1, a2+b2, a3+b3]
```

SIMD khai thác **song song dữ liệu bên trong một luồng thực thi**. Nó khác với việc tạo nhiều thread để xử lý nhiều request hoặc nhiều công việc độc lập. Vector API cũng không tự chia công việc thành thread; lập trình viên vẫn quyết định vòng lặp và cách phân chia dữ liệu.

Các loại workload có thể hưởng lợi:

- Xử lý ảnh, âm thanh và tín hiệu số.
- Tính toán ma trận, vector, thống kê và mô phỏng số.
- Tính toán trên mảng lớn với cùng phép toán cho từng phần tử.
- Một số bước xử lý dữ liệu, similarity search và thuật toán số học.

SIMD thường ít hữu ích hơn với code chủ yếu chờ database/network, logic nghiệp vụ có nhiều nhánh không đồng nhất hoặc tập dữ liệu quá nhỏ để bù chi phí xử lý. Cần đo workload thực tế trước khi quyết định.

## 2. Vector API là gì và khác auto-vectorization ra sao?

HotSpot JIT đã có khả năng **auto-vectorization**: compiler có thể nhận diện một số vòng lặp scalar và tự chuyển chúng thành chỉ thị vector. Tuy nhiên, khả năng nhận diện phụ thuộc hình dạng vòng lặp, kiểu dữ liệu, dependency giữa các phép toán, nhánh điều kiện và phiên bản compiler.

Vector API cho phép lập trình viên diễn đạt rõ phép toán theo lane:

| Cách làm | Ai mô tả SIMD? | Đặc điểm |
| --- | --- | --- |
| Scalar loop | Lập trình viên viết phép toán từng phần tử; JIT tự nhận diện | Code đơn giản, JIT có thể tự vector hóa một số vòng lặp |
| Vector API | Lập trình viên mô tả vector, lane, mask và phép toán | Chủ động hơn với phép toán SIMD, nhưng cần quản lý tail và shape |
| Native SIMD qua JNI/FFM | Lập trình viên hoặc thư viện viết mã native | Có thể kiểm soát sâu phần cứng, đổi lại chi phí tích hợp và portability |

Vector API không đảm bảo nhanh hơn mọi scalar loop. JIT có thể đã vector hóa được scalar loop; một vòng lặp bị giới hạn bởi băng thông bộ nhớ cũng có thể không nhanh hơn khi chuyển sang SIMD. Hãy benchmark cả scalar baseline lẫn vector implementation.

## 3. Ý nghĩa của trạng thái incubator lần thứ mười trong JDK 25

JEP 508 đưa Vector API vào **lần incubator thứ mười** trong JDK 25. Từ incubator có nghĩa API được cung cấp để cộng đồng thử nghiệm, đánh giá và phản hồi trong khi thiết kế vẫn có thể thay đổi.

| Trạng thái | Ý nghĩa |
| --- | --- |
| Incubator module | API nằm trong module riêng, phải chủ động resolve module; có thể thay đổi hoặc bị loại bỏ trong bản JDK sau |
| Preview feature | API/language feature được phát hành để thử nghiệm với cơ chế preview; thường cần bật bằng `--enable-preview` |
| Standard API | API đã được chuẩn hóa trong Java SE; không còn yêu cầu cơ chế incubator/preview để sử dụng |

Vector API trong JDK 25 thuộc dòng đầu tiên. **Không dùng `--enable-preview` để bật Vector API.** Cách sử dụng đúng là thêm module `jdk.incubator.vector` bằng `--add-modules` ở compile/run, hoặc khai báo `requires` trong `module-info.java` nếu ứng dụng dùng named module.

JDK 25 là một bản Java LTS, nhưng điều đó không làm cho mọi API đi kèm trở thành API ổn định. Vector API vẫn là incubator trong JDK 25 và cần được đánh giá như một dependency có rủi ro thay đổi API.

## 4. Lịch sử các lần incubator

Vector API được phát hành lần đầu trong JDK 16 và tiếp tục qua các release sau:

| JDK | JEP | Lần incubator |
| --- | --- | ---: |
| 16 | JEP 338 | 1 |
| 17 | JEP 414 | 2 |
| 18 | JEP 417 | 3 |
| 19 | JEP 426 | 4 |
| 20 | JEP 438 | 5 |
| 21 | JEP 448 | 6 |
| 22 | JEP 460 | 7 |
| 23 | JEP 469 | 8 |
| 24 | JEP 489 | 9 |
| 25 | JEP 508 | **10** |
| 26 | JEP 529 | 11 |
| 27 | JEP 537 | 12 |

Do đó, tiêu đề “lần incubator thứ mười” mô tả chính xác trạng thái của JDK 25. Khi triển khai trên JDK mới hơn, hãy đọc JEP và tài liệu của đúng release; không mặc định rằng lần thứ mười vẫn là trạng thái mới nhất.

## 5. Trạng thái mới nhất: JDK 27 vẫn là incubator

Theo release notes của JDK 27 phát hành ngày 15/09/2026, Vector API tiếp tục là **Twelfth Incubator** theo JEP 537. Module hiện hành vẫn là `jdk.incubator.vector`. JDK 26 trước đó là Eleventh Incubator theo JEP 529.

Điều này có ba ý nghĩa thực tế:

1. **Chưa phải API chuẩn:** không nên giới thiệu Vector API như một phần API Java SE ổn định.
2. **Cần theo dõi thay đổi giữa JDK:** code dùng API incubator có thể cần chỉnh sửa khi nâng JDK.
3. **Chưa nên đặt làm hợp đồng công khai dài hạn:** nếu một thư viện công khai expose kiểu `Vector`, `VectorSpecies` hoặc `VectorMask`, người dùng thư viện sẽ bị ràng buộc với API incubator.

JEP 537 tiếp tục duy trì incubator trong khi chờ các khả năng cần thiết từ Project Valhalla. Mục tiêu là điều chỉnh cách biểu diễn vector để phù hợp với value classes/value objects trước khi tiến tới trạng thái preview. Việc API tiếp tục incubate không có nghĩa nó không chạy được; điều đó có nghĩa thiết kế và tính ổn định vẫn đang được hoàn thiện.

JDK 27 không thay đổi đáng kể mô hình lập trình Vector API so với JDK 25. Vì vậy, ví dụ cơ bản trong bài vẫn minh họa được cách dùng ở cả hai release, nhưng phải biên dịch và chạy với đúng JDK mục tiêu.

## 6. Module và cách bật Vector API

Vector API nằm trong module:

```text
jdk.incubator.vector
```

Module này không được tự động resolve trong mọi ứng dụng. Với ứng dụng classpath thông thường, thêm module ở cả lúc biên dịch và chạy.

Biên dịch bằng JDK 25:

```bash
javac --release 25 \
  --add-modules jdk.incubator.vector \
  -d out \
  src/VectorAdd.java
```

Chạy bằng JDK 25:

```bash
java --add-modules jdk.incubator.vector \
  -cp out \
  VectorAdd
```

Với JDK 27, thay release/compiler bằng JDK 27:

```bash
javac --release 27 \
  --add-modules jdk.incubator.vector \
  -d out \
  src/VectorAdd.java

java --add-modules jdk.incubator.vector \
  -cp out \
  VectorAdd
```

Không thêm `--enable-preview` chỉ vì module có chữ `incubator`. Preview và incubator là hai cơ chế khác nhau.

### Ứng dụng dùng named module

Trong `module-info.java`, khai báo dependency:

```java
module com.example.simd {
    requires jdk.incubator.vector;
}
```

Khi module được khai báo bằng `requires`, module system biết ứng dụng phụ thuộc Vector API. Với build tool, hãy đảm bảo compiler và JVM runtime đều resolve module này; cấu hình cho test, integration test và ứng dụng đóng gói phải nhất quán.

Khi khởi chạy, JDK có thể in cảnh báo rằng chương trình đang sử dụng incubating module. Đây là cảnh báo trạng thái API, không phải lỗi compile/runtime.

## 7. Các khái niệm cốt lõi: Vector, lane, species và shape

Một vector là một dãy có số lane cố định. Mỗi lane chứa một giá trị thuộc cùng element type.

| Khái niệm | Ý nghĩa |
| --- | --- |
| Vector | Giá trị vector gồm nhiều lane |
| Lane | Một phần tử scalar trong vector |
| Element type | Kiểu primitive của lane: byte, short, int, long, float hoặc double |
| Vector shape | Kích thước vector tính bằng bit, ví dụ 128, 256 hoặc 512 bit nếu nền tảng hỗ trợ |
| VectorSpecies | Kết hợp element type và shape; xác định số lane và kiểu vector |
| VectorMask | Mask cho biết lane nào được tham gia thao tác |
| VectorShuffle | Quy tắc chọn và sắp xếp lane từ một hoặc nhiều vector |

Ví dụ:

- `FloatVector.SPECIES_128` có 128 bit; với lane `float` 32 bit thì có 4 lane.
- `FloatVector.SPECIES_256` có 256 bit; với lane `float` thì có 8 lane.
- `IntVector.SPECIES_512` có 512 bit; với lane `int` 32 bit thì có 16 lane.

Không phải CPU nào cũng hỗ trợ mọi shape. Dùng `SPECIES_PREFERRED` để runtime chọn shape phù hợp trên nền tảng hiện tại thay vì hard-code 256/512 bit.

## 8. Ví dụ hiện hành: cộng hai mảng float

Ví dụ sau sử dụng API `FloatVector` có trong JDK 25 và JDK 27. Vòng lặp vector xử lý các block đầy đủ; phần tử còn dư ở cuối mảng được xử lý bằng scalar loop.

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public class VectorAdd {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    static void add(float[] left, float[] right, float[] result) {
        if (left.length != right.length || left.length != result.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }

        int upperBound = SPECIES.loopBound(left.length);
        int i = 0;

        for (; i < upperBound; i += SPECIES.length()) {
            FloatVector a = FloatVector.fromArray(SPECIES, left, i);
            FloatVector b = FloatVector.fromArray(SPECIES, right, i);
            a.add(b).intoArray(result, i);
        }

        // Xử lý tail không đủ một vector.
        for (; i < left.length; i++) {
            result[i] = left[i] + right[i];
        }
    }

    public static void main(String[] args) {
        float[] left = {1, 2, 3, 4, 5, 6, 7};
        float[] right = {10, 20, 30, 40, 50, 60, 70};
        float[] result = new float[left.length];

        add(left, right, result);
        System.out.println(java.util.Arrays.toString(result));
    }
}
```

Kết quả mong đợi:

```text
[11.0, 22.0, 33.0, 44.0, 55.0, 66.0, 77.0]
```

### Vì sao dùng SPECIES_PREFERRED và loopBound?

- `SPECIES_PREFERRED` truy vấn shape phù hợp với nền tảng đang chạy.
- `SPECIES.length()` cho biết số lane của vector.
- `SPECIES.loopBound(length)` trả về giới hạn lớn nhất để vòng lặp chỉ xử lý các block đủ lane.
- Scalar tail xử lý phần tử còn lại mà không đọc/ghi vượt mảng.

Không giả định số lane luôn là 4, 8 hoặc 16. Một shape hợp lệ trên nền tảng khác có thể có kích thước khác với máy phát triển.

## 9. Dùng mask khi muốn xử lý tail trong cùng vòng lặp

Một cách khác là dùng `VectorMask` để chỉ bật những lane nằm trong giới hạn mảng:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorSpecies;

final class MaskedVectorAdd {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    static void add(float[] left, float[] right, float[] result) {
        if (left.length != right.length || left.length != result.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }

        for (int i = 0; i < left.length; i += SPECIES.length()) {
            VectorMask<Float> mask =
                    SPECIES.indexInRange(i, left.length);

            FloatVector a = FloatVector.fromArray(SPECIES, left, i, mask);
            FloatVector b = FloatVector.fromArray(SPECIES, right, i, mask);
            a.add(b).intoArray(result, i, mask);
        }
    }
}
```

Mask bảo vệ các lane cuối không có phần tử tương ứng. Tùy workload và phần cứng, masked loop có thể không nhanh bằng vòng vector không mask cộng scalar tail. Hãy benchmark cả hai cách trên dữ liệu thật.

## 10. Các phép toán và khả năng của API

Vector API cung cấp nhiều nhóm thao tác:

| Nhóm | Thành phần | Mục đích |
| --- | --- | --- |
| Arithmetic | `add`, `sub`, `mul`, `div`, `min`, `max` | Phép toán số học theo lane |
| Comparison | `compare` và `VectorMask` | So sánh từng lane |
| Selection | `blend` | Chọn giá trị theo mask |
| Reduction | `reduceLanes` | Gom các lane thành một kết quả |
| Rearrangement | `VectorShuffle`, `rearrange`, `slice`, `unslice` | Di chuyển hoặc sắp xếp lane |
| Conversion | `convert`, `castShape` | Chuyển element type hoặc shape |
| Memory | `fromArray`, `intoArray`, các overload MemorySegment | Đọc/ghi vector từ vùng nhớ |

Ví dụ so sánh và mask:

```java
FloatVector values = FloatVector.fromArray(SPECIES, input, 0);
VectorMask<Float> positive = values.compare(
        jdk.incubator.vector.VectorOperators.GT, 0.0f);

FloatVector zeros = FloatVector.broadcast(SPECIES, 0.0f);
FloatVector selected = zeros.blend(values, positive);
```

Đoạn code minh họa chọn giữ các lane dương và thay lane còn lại bằng zero. Khi dùng mask, cần hiểu rõ lane bị mask sẽ không thực hiện thao tác tương ứng và giá trị kết quả của lane bị bỏ qua phụ thuộc loại operation.

## 11. Tương thích phần cứng và fallback

Vector API được thiết kế để tận dụng SIMD instruction khi CPU và JIT hỗ trợ. Các nền tảng được tối ưu phổ biến gồm:

- Intel/AMD x64 với các tập lệnh vector như AVX2 và AVX-512 tùy CPU/JDK.
- ARM 64-bit với NEON; mức hỗ trợ instruction cụ thể phụ thuộc runtime và nền tảng.

Không suy ra CPU hỗ trợ AVX-512 chỉ vì ứng dụng chạy trên x64. Cũng không suy ra mọi phép toán đều có chỉ thị phần cứng tương ứng.

JDK có implementation scalar mặc định cho các thao tác nếu runtime không biên dịch được thành vector instruction phù hợp. Điều này giúp code vẫn chạy đúng trên nền tảng không có hỗ trợ SIMD cần thiết, nhưng có thể không có lợi ích hiệu năng.

Vì vậy:

1. Chọn `SPECIES_PREFERRED` thay vì hard-code shape.
2. Dùng các phép toán shape-invariant nếu có thể để tăng tính portable.
3. Kiểm tra target CPU, JDK vendor/build và runtime flags trong benchmark.
4. Không coi tên API vector là bằng chứng rằng CPU đã thực thi một chỉ thị SIMD cụ thể.

## 12. Tính đúng đắn số học và các giới hạn cần biết

Vector hóa có thể thay đổi thứ tự thực hiện phép toán, đặc biệt với reduction số thực. Phép cộng số thực dấu phẩy động không có tính kết hợp tuyệt đối do rounding:

\[
(a+b)+c \ne a+(b+c)
\]

Vì vậy, `reduceLanes(ADD)` có thể cho kết quả khác vài bit so với vòng lặp scalar cộng tuần tự. Với thuật toán số học, cần xác định tolerance, error budget và yêu cầu reproducibility trước khi chuyển sang vector.

Các điểm cần kiểm tra:

- **Tail handling:** không đọc/ghi ngoài phạm vi mảng.
- **Overflow:** integer arithmetic vẫn chịu quy tắc overflow của kiểu primitive.
- **Floating-point rounding:** thứ tự reduction và fused multiply-add có thể ảnh hưởng kết quả.
- **NaN và signed zero:** xác nhận semantics phù hợp với thuật toán.
- **Mask correctness:** lane bị bỏ qua không được dùng nhầm trong kết quả.
- **Memory bandwidth:** nếu workload bị giới hạn bởi bộ nhớ, SIMD có thể không cải thiện nhiều.
- **Small inputs:** chi phí vòng lặp, dispatch và xử lý vector có thể lấn át lợi ích.

Vector và các helper như `VectorMask`, `VectorShuffle` là value-based types. Không dựa vào object identity, không dùng `==` để so sánh giá trị vector và không synchronize trên instance vector. Dùng `equals` hoặc các phép so sánh theo lane tùy mục tiêu.

## 13. Khi nào nên cân nhắc Vector API?

| Tình huống | Khuyến nghị |
| --- | --- |
| Vòng lặp số học trên mảng lớn là hot path đã đo được | Đáng thử Vector API |
| Xử lý ảnh/audio hoặc phép toán lặp theo lane | Có thể phù hợp |
| JIT chưa auto-vectorize được loop quan trọng | Vector API có thể giúp diễn đạt rõ SIMD |
| Workload chủ yếu chờ database/network | Ưu tiên xử lý latency I/O/dependency |
| Mảng rất nhỏ hoặc thao tác ít lần | Scalar code thường đơn giản hơn |
| Code nhiều nhánh, dependency giữa các iteration | Khó khai thác SIMD; cần thiết kế lại hoặc giữ scalar |
| Thư viện công khai cần ổn định API qua nhiều JDK | Cân nhắc kỹ rủi ro incubator |

Một quy tắc thực tế: **đo scalar trước, kiểm tra JIT auto-vectorization, sau đó mới thử Vector API**. Không chuyển toàn bộ codebase sang Vector API chỉ vì một microbenchmark cho thấy một loop nhanh hơn.

## 14. Benchmark và kiểm chứng hiệu năng

Một benchmark hữu ích cần so sánh ít nhất:

1. Scalar implementation dễ hiểu.
2. Scalar implementation sau JIT warm-up (để JIT có cơ hội auto-vectorize).
3. Vector API implementation với preferred species.
4. Nếu phù hợp, phiên bản masked tail và phiên bản scalar tail.

Dùng JMH hoặc harness benchmark được kiểm soát; tránh đo một vòng `System.nanoTime` đơn giản rồi kết luận. Cần:

- Warm-up đủ lâu để JIT biên dịch các hot methods.
- Nhiều fork/iteration và input size đại diện.
- Giữ cùng CPU, OS, JDK build, power mode và runtime flags.
- Dùng kết quả đầu ra để tránh dead-code elimination.
- Đo nhiều kích thước dữ liệu, không chỉ một array size.
- Theo dõi throughput, latency, allocation và CPU utilization.
- Kiểm tra kết quả số học giữa scalar và vector trong tolerance đã định.

Nếu cần xác nhận mã máy, dùng công cụ profiling/disassembly phù hợp với JDK và nền tảng. Đừng dựa vào việc code gọi `FloatVector.add` để kết luận chắc chắn compiler đã phát sinh một instruction cụ thể.

## 15. Quản trị rủi ro khi API còn incubator

Trước khi đưa Vector API vào một thành phần ứng dụng:

- Giới hạn việc sử dụng trong một package/module nội bộ.
- Tránh expose kiểu Vector API trong public method signatures nếu người dùng thư viện không kiểm soát JDK.
- Có scalar fallback dễ kiểm thử để giữ đường chạy trên nền tảng không phù hợp.
- Ghim JDK vendor/build trong CI và kiểm thử nâng cấp JDK sớm.
- Theo dõi JEP mới của Vector API mỗi release.
- Chuẩn bị sửa source/build flags nếu API thay đổi hoặc module bị loại bỏ.
- Ghi lại benchmark và correctness tests cho từng target CPU quan trọng.

Incubator không có nghĩa API chắc chắn bị loại bỏ; nó có nghĩa nhà phát triển phải chấp nhận rủi ro thiết kế còn thay đổi. Đánh giá rủi ro theo lợi ích hiệu năng đo được và khả năng kiểm soát JDK runtime của tổ chức.

## 16. Bài thực hành: kiểm tra trạng thái và chạy Vector API trên JDK 25

### Mục tiêu

Xác nhận Vector API trong JDK 25 là incubator module lần thứ mười, bật module đúng cách và chạy phép cộng mảng bằng preferred species.

### Nhiệm vụ

1. Kiểm tra `java -version` và ghi nhận vendor/build của JDK 25.
2. Đọc release notes/JEP 508 để xác nhận Vector API là Tenth Incubator.
3. Kiểm tra module `jdk.incubator.vector` trong JDK API docs.
4. Biên dịch ví dụ `VectorAdd` bằng `--add-modules jdk.incubator.vector`.
5. Chạy chương trình với cùng module flag và kiểm tra kết quả.
6. Thử array length nhỏ hơn, bằng và không chia hết cho `SPECIES.length()`.
7. Chạy scalar và vector implementation trên cùng dữ liệu.
8. Dùng benchmark harness để so sánh nhiều input size sau warm-up.
9. Chạy lại trên JDK 27 và xác nhận API vẫn ở lần incubator thứ mười hai.
10. Ghi nhận chênh lệch hiệu năng, kết quả số học, JDK và CPU; không điền số liệu giả định.

### Mẫu báo cáo

| Hạng mục | Kết quả cần ghi |
| --- | --- |
| JDK 25 vendor/build | Chưa đo |
| Trạng thái JEP 508 | Tenth Incubator |
| Module | `jdk.incubator.vector` |
| Compile/run flags | `--add-modules jdk.incubator.vector` |
| Preferred species | Chưa đo |
| CPU/OS | Chưa ghi |
| Kết quả scalar | Chưa đo |
| Kết quả Vector API | Chưa đo |
| Correctness/tolerance | Chưa kiểm tra |
| JDK 27 status | JEP 537, Twelfth Incubator |

### Tiêu chí hoàn thành

- Giải thích được SIMD và vai trò của Vector API.
- Phân biệt incubator module với preview feature và standard API.
- Nêu đúng JDK 25 là lần incubator thứ mười theo JEP 508.
- Nêu đúng JDK 27 là lần incubator thứ mười hai theo JEP 537.
- Biên dịch/chạy được ví dụ bằng `--add-modules`, không nhầm với `--enable-preview`.
- Xử lý đúng tail bằng `loopBound` hoặc mask.
- Benchmark scalar và vector trong điều kiện có thể tái lập.
- Giải thích được rủi ro API incubator và kế hoạch theo dõi khi nâng JDK.

## Tài liệu tham khảo

- [JEP 508 — Vector API (Tenth Incubator)](https://openjdk.org/jeps/508): trạng thái và phạm vi của Vector API trong JDK 25.
- [Oracle JDK 25 — Significant Changes](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): xác nhận Vector API là Tenth Incubator.
- [Oracle Java SE 25 — Module jdk.incubator.vector](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/module-summary.html): module, trạng thái incubating và mục đích SIMD.
- [JEP 529 — Vector API (Eleventh Incubator)](https://openjdk.org/jeps/529): trạng thái trong JDK 26.
- [JEP 537 — Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537): trạng thái trong JDK 27.
- [Oracle JDK 27 — Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html): xác nhận Vector API vẫn là incubating feature.
- [Oracle Java SE 27 — Package jdk.incubator.vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html): Vector, species, mask, preferred shape, loopBound và lưu ý hiệu năng.

**Kết luận:** JDK 25 đánh dấu lần incubator thứ mười của Vector API theo JEP 508; đây là module `jdk.incubator.vector`, không phải preview feature hay API chuẩn. Trạng thái mới nhất trong JDK 27 là lần incubator thứ mười hai theo JEP 537 và API vẫn tiếp tục được hoàn thiện. Hãy bật module bằng `--add-modules`, viết code shape-portable với `SPECIES_PREFERRED`, xử lý tail bằng `loopBound` hoặc mask, và chỉ áp dụng khi benchmark cho thấy lợi ích trên workload thực. Vì API còn incubator, cần cô lập dependency, kiểm thử đúng JDK/CPU và theo dõi JEP ở các release tiếp theo.
