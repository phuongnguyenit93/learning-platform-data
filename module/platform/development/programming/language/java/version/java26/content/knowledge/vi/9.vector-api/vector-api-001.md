# Vector API incubator lần 11 ở Java 26, lần 12 ở Java 27

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích SIMD và cách Vector API biểu diễn nhiều phép toán trên các lane trong một vector.
- Phân biệt Vector API với vòng lặp scalar và cơ chế auto-vectorization của JIT.
- Hiểu vai trò của `VectorSpecies`, vector shape, lane, mask và các phép toán lane-wise.
- Viết kernel nhân hai mảng `float` bằng Vector API, xử lý đúng phần tử cuối không đủ một vector.
- Biên dịch và chạy ứng dụng với module incubator trên JDK 26 và JDK 27.
- Đánh giá hiệu năng bằng benchmark có baseline scalar và xác định khi nào không nên dùng Vector API.
- Nhận diện Vector API vẫn là incubator ở cả hai release, chưa phải API Java SE ổn định.

## 1. Vector API giải quyết bài toán nào?

Nhiều workload thực hiện cùng một phép toán trên lượng dữ liệu lớn: cộng hai mảng số, nhân ma trận, xử lý tín hiệu, lọc ảnh, tính toán thống kê, mã hóa hoặc suy luận số học. Cách viết scalar truyền thống xử lý từng phần tử:

~~~java
for (int i = 0; i < a.length; i++) {
    result[i] = a[i] * b[i];
}
~~~

CPU hiện đại có các tập lệnh SIMD (Single Instruction, Multiple Data). Một lệnh SIMD có thể thực hiện cùng phép toán trên nhiều giá trị cùng lúc. Ví dụ, thay vì nhân một cặp số, CPU có thể nhân nhiều cặp số `float` trong các lane của một thanh ghi vector.

Vector API cung cấp cách biểu đạt phép toán này bằng Java. Ứng dụng mô tả dữ liệu và phép toán theo vector; HotSpot JIT có thể biên dịch chúng thành lệnh SIMD phù hợp với CPU đang chạy. API che giấu khác biệt giữa các tập lệnh phần cứng như AVX trên x64 và NEON trên AArch64.

Vector API hữu ích khi:

- Dữ liệu có thể xử lý theo từng phần tử độc lập hoặc theo nhóm lane.
- Cùng một phép toán được lặp lại trên mảng hoặc buffer lớn.
- Phần lớn chi phí nằm ở tính toán số học và dữ liệu có thể được nạp/lưu hiệu quả.
- Có thể kiểm tra kết quả và hiệu năng trên các CPU triển khai thực tế.

Nó không phải giải pháp tăng tốc tự động cho mọi vòng lặp. Nếu workload bị giới hạn bởi I/O, truy cập bộ nhớ ngẫu nhiên, nhánh phức tạp, cấp phát object hoặc lời gọi hàm không vector hóa được, SIMD có thể không đem lại cải thiện đáng kể.

## 2. Lịch sử và trạng thái ở Java 26, Java 27

Vector API tiếp tục ở trạng thái incubator trong hai release gần đây:

| JDK | JEP | Vòng incubator | Trạng thái |
|---|---|---:|---|
| JDK 26 | JEP 529 – Vector API | Lần 11 | Incubator module `jdk.incubator.vector` |
| JDK 27 | JEP 537 – Vector API | Lần 12 | Tiếp tục incubator module `jdk.incubator.vector` |

JDK 26 phát hành Vector API ở lần incubator thứ 11. JDK 27 tiếp tục ở lần thứ 12; API vẫn được phân phối trong module incubator và chưa trở thành API Java SE final. Số thứ tự incubator chỉ cho biết đây là vòng thử nghiệm tiếp theo của cùng API, không có nghĩa API đã được chuẩn hóa sau 12 lần.

Oracle JDK 26 và JDK 27 đều đánh dấu module `jdk.incubator.vector` là *Incubating Feature. Will be removed in a future release*. Điều đó có nghĩa API có thể thay đổi hoặc bị loại bỏ trong release sau. Không coi mã nguồn, chữ ký API hoặc binary phụ thuộc vào nó là hợp đồng tương thích lâu dài.

Vector API tiếp tục incubate trong khi các nền tảng ngôn ngữ và runtime cần thiết từ Project Valhalla được hoàn thiện. Vector là giá trị dữ liệu không cần ngữ nghĩa identity thông thường; việc tích hợp với value classes và generic specialization có thể ảnh hưởng đến hình dạng API lâu dài. Vì vậy, việc tiếp tục incubator là quyết định có chủ đích để tránh chuẩn hóa một thiết kế trước khi các phụ thuộc nền tảng sẵn sàng.

**Phân biệt incubator với preview:**

- Vector API là **incubator module**. Cần thêm module `jdk.incubator.vector` khi biên dịch/chạy.
- Preview language/API feature thường cần `--enable-preview` ở compiler và runtime.
- Chỉ sử dụng Vector API không yêu cầu `--enable-preview`. Nếu chương trình đồng thời dùng một preview feature khác, cấu hình preview riêng cho feature đó.

## 3. Các khái niệm cốt lõi

### Vector và lane

Một `Vector` là chuỗi bất biến gồm một số lane cố định. Mỗi lane giữ một giá trị primitive cùng kiểu, chẳng hạn `int`, `long`, `float` hoặc `double`.

Ví dụ một vector `float` có 256 bit chứa 8 lane, vì mỗi `float` chiếm 32 bit:

~~~text
FloatVector 256 bit
+--------+--------+--------+--------+--------+--------+--------+--------+
| lane 0 | lane 1 | lane 2 | lane 3 | lane 4 | lane 5 | lane 6 | lane 7 |
|  1.0   |  2.0   |  3.0   |  4.0   |  5.0   |  6.0   |  7.0   |  8.0   |
+--------+--------+--------+--------+--------+--------+--------+--------+
             một phép toán vector có thể xử lý các lane cùng lúc
~~~

Phép toán `va.mul(vb)` nhân các lane tương ứng của hai vector và tạo ra vector kết quả cùng species. Các vector không bị thay đổi tại chỗ; phương thức trả về giá trị vector mới.

### VectorSpecies và vector shape

`VectorSpecies<E>` mô tả một nhóm vector có cùng kiểu phần tử và shape. Shape biểu diễn độ rộng vector, ví dụ 128, 256 hoặc 512 bit. Số lane phụ thuộc vào cả shape lẫn kiểu phần tử.

Các hằng như `FloatVector.SPECIES_128`, `SPECIES_256` và `SPECIES_512` chọn shape cụ thể. `FloatVector.SPECIES_PREFERRED` yêu cầu runtime chọn species phù hợp nhất với nền tảng hiện tại.

Trong code đa nền tảng, ưu tiên `SPECIES_PREFERRED` thay vì giả định mọi CPU đều hỗ trợ một độ rộng cố định. Nếu chọn shape không được CPU hỗ trợ, API vẫn có implementation scalar mặc định, nhưng code có thể không được biên dịch thành lệnh SIMD mong muốn.

### Phép toán lane-wise

Phép toán lane-wise áp dụng cùng một phép toán scalar lên từng cặp lane tương ứng:

| Phép toán vector | Ý nghĩa theo từng lane |
|---|---|
| `va.add(vb)` | Cộng hai giá trị cùng vị trí |
| `va.sub(vb)` | Trừ hai giá trị cùng vị trí |
| `va.mul(vb)` | Nhân hai giá trị cùng vị trí |
| `va.div(vb)` | Chia hai giá trị cùng vị trí |
| `va.min(vb)`, `va.max(vb)` | Chọn min/max theo lane |
| `va.compare(VectorOperators.LT, vb)` | So sánh theo lane và trả về mask |

Ngoài phép toán lane-wise, API còn có các thao tác cross-lane như shuffle, rearrange, compress và các phép reduction để tổng hợp nhiều lane thành một giá trị scalar.

### Mask và điều kiện

`VectorMask<E>` chứa một bit boolean cho mỗi lane. Mask cho phép chỉ xử lý những lane thỏa điều kiện hoặc nằm trong miền dữ liệu hợp lệ.

Ví dụ, nếu mảng có 10 phần tử nhưng vector có 8 lane, lần lặp đầu xử lý 8 phần tử; lần lặp sau chỉ còn 2 phần tử. Mask có thể đánh dấu 2 lane hợp lệ và ngăn load/store vượt giới hạn mảng.

## 4. Ví dụ: nhân hai mảng float bằng Vector API

Ví dụ sau dùng species ưu tiên của nền tảng, xử lý phần vector đầy đủ trước rồi xử lý phần đuôi bằng scalar:

~~~java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public final class VectorMultiply {
    private static final VectorSpecies<Float> SPECIES =
        FloatVector.SPECIES_PREFERRED;

    static void multiply(float[] a, float[] b, float[] result) {
        if (a.length != b.length || a.length != result.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }

        int i = 0;
        int upperBound = SPECIES.loopBound(a.length);

        for (; i < upperBound; i += SPECIES.length()) {
            FloatVector va = FloatVector.fromArray(SPECIES, a, i);
            FloatVector vb = FloatVector.fromArray(SPECIES, b, i);
            FloatVector vr = va.mul(vb);
            vr.intoArray(result, i);
        }

        // Xử lý các phần tử còn lại chưa đủ một vector.
        for (; i < a.length; i++) {
            result[i] = a[i] * b[i];
        }
    }

    public static void main(String[] args) {
        float[] a = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
        float[] b = {2, 2, 2, 2, 2, 2, 2, 2, 2, 2};
        float[] result = new float[a.length];

        multiply(a, b, result);

        for (float value : result) {
            System.out.print(value + " ");
        }
    }
}
~~~

Giải thích:

1. `SPECIES_PREFERRED` chọn vector species thích hợp với CPU.
2. `SPECIES.length()` cho biết mỗi vector chứa bao nhiêu phần tử.
3. `loopBound(a.length)` trả về giới hạn lớn nhất không vượt quá độ dài mảng và chia hết cho số lane.
4. `fromArray` nạp các lane từ mảng.
5. `mul` nhân các lane tương ứng.
6. `intoArray` ghi vector kết quả trở lại mảng.
7. Vòng lặp scalar cuối xử lý phần đuôi khi số phần tử không chia hết cho số lane.

Không tự tính giới hạn bằng biểu thức bit như `length & ~(species.length() - 1)`. Cách đó giả định số lane là lũy thừa của 2; API không yêu cầu mọi shape tương lai phải thỏa giả định này. Dùng `loopBound()` để code đúng với species được runtime chọn.

## 5. Xử lý phần đuôi bằng mask

Có thể viết vòng lặp chỉ dùng mask cho cả phần vector đầy đủ và phần cuối:

~~~java
static void multiplyMasked(float[] a, float[] b, float[] result) {
    if (a.length != b.length || a.length != result.length) {
        throw new IllegalArgumentException("Array lengths must match");
    }

    for (int i = 0; i < a.length; i += SPECIES.length()) {
        VectorMask<Float> mask = SPECIES.indexInRange(i, a.length);

        FloatVector va = FloatVector.fromArray(SPECIES, a, i, mask);
        FloatVector vb = FloatVector.fromArray(SPECIES, b, i, mask);
        FloatVector vr = va.mul(vb);

        vr.intoArray(result, i, mask);
    }
}
~~~

`indexInRange(i, a.length)` tạo mask chỉ bật các lane có chỉ số nằm trong mảng. Các lane không được bật sẽ không thực hiện thao tác load/store tương ứng.

Cách dùng mask đơn giản và dễ tổng quát hóa cho nhiều trường hợp. Tuy nhiên, tạo và áp dụng mask trong mọi vòng lặp có thể tạo thêm chi phí. Với mảng lớn, cách dùng `loopBound()` và vòng scalar tail thường là lựa chọn nên benchmark trước. Với dữ liệu có biên phức tạp hoặc cần xử lý nhiều miền không liên tục, masked operations có thể giúp code rõ ràng hơn.

## 6. So sánh và xử lý có điều kiện bằng mask

Mask cho phép thay thế một số nhánh scalar bằng phép toán trên các lane được chọn. Ví dụ, đặt các giá trị âm thành 0:

~~~java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorOperators;

static FloatVector clampToZero(FloatVector values) {
    FloatVector zero = FloatVector.zero(values.species());
    VectorMask<Float> negative = values.compare(VectorOperators.LT, zero);
    return values.blend(zero, negative);
}
~~~

Trong đó:

- `compare(VectorOperators.LT, zero)` so sánh từng lane với 0 và tạo mask.
- `blend(zero, negative)` chọn giá trị từ vector `zero` ở các lane mask bật; các lane còn lại giữ giá trị ban đầu.

Đây là ví dụ minh họa thao tác mask. Với một kernel cụ thể, hãy kiểm tra đúng overload theo kiểu vector và benchmark trên JDK mục tiêu.

Mask cũng hữu ích khi truy cập mảng, lọc dữ liệu theo điều kiện, xử lý tail và thực hiện các phép toán mà một số lane không hợp lệ. Không được giả định một mask luôn làm phép toán nhanh hơn; hiệu năng phụ thuộc CPU và khả năng hạ lệnh của JIT.

## 7. Species, shape và tính portable

Vector API cho phép viết một thuật toán mà không gắn cứng vào số lane cụ thể. Một kernel portable nên:

- Lấy species từ `SPECIES_PREFERRED` hoặc truy vấn species phù hợp với kiểu dữ liệu.
- Dùng `species.length()` để bước qua các lane.
- Dùng `loopBound()` hoặc mask để xử lý giới hạn mảng.
- Đảm bảo các vector tham gia phép toán lane-wise có cùng species.
- Không dựa vào việc vector luôn có 128, 256 hoặc 512 bit.
- Kiểm tra fallback và tính đúng trên mọi kiến trúc CPU mà ứng dụng hỗ trợ.

Một vector có kiểu phần tử `float` và shape 256 bit có 8 lane; vector `double` cùng shape chỉ có 4 lane. Do đó, không dùng một hằng số số lane cho nhiều kiểu dữ liệu. Dùng `VectorSpecies` để lấy shape và lane count tương ứng.

## 8. Những lưu ý về tính đúng của số học

SIMD thay đổi cách nhóm phép toán. Với số nguyên, cần xem xét overflow theo đúng kiểu primitive; phép cộng hoặc nhân số nguyên Java vẫn có semantics tràn theo kiểu đích. Vector API không tự kiểm tra overflow cho từng lane.

Với `float` và `double`, thứ tự thực hiện phép toán có thể ảnh hưởng kết quả do IEEE 754. Các phép reduction như cộng nhiều lane có thể gom nhóm phép cộng khác với vòng lặp scalar. Số thực dấu phẩy động không có tính kết hợp tuyệt đối:

~~~text
(a + b) + c có thể khác a + (b + c)
~~~

Vì vậy:

- Không yêu cầu bit-for-bit equality nếu thuật toán thay đổi thứ tự phép toán và nghiệp vụ cho phép sai số.
- Đặt tolerance phù hợp và kiểm tra dữ liệu cực trị, NaN, vô cực, subnormal và dấu zero.
- Nếu kết quả phải tái lập chính xác theo quy tắc nghiệp vụ, kiểm tra semantics từng phép toán và tránh reduction không kiểm soát.
- Kiểm tra overflow, chuyển đổi lane và mask cho từng loại dữ liệu.
- So sánh kết quả vector với implementation scalar tham chiếu trên nhiều bộ dữ liệu.

## 9. Các lớp và cấu trúc chính của API

| Thành phần | Vai trò |
|---|---|
| `Vector<E>` | Kiểu vector tổng quát và các phép toán chung |
| `IntVector`, `LongVector`, `FloatVector`, `DoubleVector` | Vector chuyên biệt cho kiểu primitive |
| `VectorSpecies<E>` | Mô tả kiểu phần tử và shape |
| `VectorShape` | Biểu diễn độ rộng vector |
| `VectorMask<E>` | Chọn lane tham gia phép toán |
| `VectorShuffle<E>` | Điều khiển việc sắp xếp/di chuyển lane |
| `VectorOperators` | Token mô tả phép toán lane-wise |
| `VectorMath` | Các hàm số học hỗ trợ phép toán vector |

Vector và các kiểu hỗ trợ như `VectorMask`, `VectorShuffle`, `VectorSpecies` có ngữ nghĩa value-based. Tránh dựa vào so sánh identity bằng `==`; dùng `equals()` khi cần so sánh giá trị. Không đồng bộ trên các instance vector. API được thiết kế theo hướng bất biến: các phép toán trả về kết quả mới, không sửa vector đầu vào.

Không nên lưu vector vào field hoặc phần tử mảng nếu chưa đo hiệu năng. Tài liệu API khuyến nghị ưu tiên local variables, parameters và các hằng `static final` cho các giá trị species; việc lưu các object value-based ở field hoặc array có thể làm phát sinh chi phí biểu diễn không mong muốn.

## 10. Biên dịch và chạy trên JDK 26, JDK 27

Vector API nằm trong module incubator `jdk.incubator.vector`. Với ứng dụng classpath, thêm module ở cả compiler và runtime.

### JDK 26

~~~bash
javac --add-modules jdk.incubator.vector VectorMultiply.java
java --add-modules jdk.incubator.vector VectorMultiply
~~~

### JDK 27

~~~bash
javac --add-modules jdk.incubator.vector VectorMultiply.java
java --add-modules jdk.incubator.vector VectorMultiply
~~~

Đảm bảo cả hai lệnh dùng cùng JDK mục tiêu. JDK 26 chứa lần incubator thứ 11; JDK 27 chứa lần thứ 12. Khi nâng cấp, biên dịch lại và kiểm thử trên đúng JDK mới; không mặc định binary hoặc source của incubator module được bảo đảm tương thích giữa các release.

Nếu ứng dụng dùng module system, khai báo dependency trong `module-info.java`:

~~~java
module com.example.vectorapp {
    requires jdk.incubator.vector;
}
~~~

Sau đó biên dịch và chạy ứng dụng theo module path. Không cần `--enable-preview` chỉ vì dùng Vector API; `--add-modules` hoặc `requires` là cách bật incubator module.

Compiler sẽ phát cảnh báo rằng module đang dùng incubator API. Không nên tắt cảnh báo mà không ghi nhận dependency này trong build và tài liệu phát hành.

## 11. Đo hiệu năng đúng cách

Một kernel vector có thể nhanh hơn scalar trên CPU hỗ trợ SIMD, nhưng không có tỷ lệ tăng tốc cố định. Hiệu quả phụ thuộc:

- Kiến trúc và tập lệnh CPU (ví dụ AVX trên x64, NEON trên AArch64).
- Vector shape và số lane được chọn.
- Kích thước dữ liệu, cache locality và băng thông bộ nhớ.
- Chi phí load/store, alignment, mask và phần đuôi.
- Khả năng JIT biên dịch kernel thành lệnh vector.
- Warmup, compilation tier, mức tải nền và cách đo.

Khi benchmark, hãy so sánh ít nhất:

1. Implementation scalar rõ ràng và đúng.
2. Implementation Vector API dùng `SPECIES_PREFERRED`.
3. Biến thể mask-tail và loopBound-plus-scalar-tail nếu cả hai phù hợp.
4. Nhiều kích thước dữ liệu, bao gồm trường hợp nhỏ hơn một vector và dữ liệu lớn hơn cache.
5. Các JDK và CPU mà ứng dụng sẽ thực sự triển khai.

Dùng JMH cho microbenchmark thay vì một vòng lặp tự viết bằng `System.nanoTime()`. Có warmup, nhiều fork, dữ liệu đầu vào ổn định và ngăn dead-code elimination. Kiểm tra output để bảo đảm benchmark thực hiện cùng công việc. Không chạy profiler nặng hoặc logging khác nhau giữa baseline và candidate nếu chúng làm sai lệch phép đo.

Một số workload nhỏ có thể chậm hơn do chi phí setup, kiểm tra biên hoặc chuyển dữ liệu. Nếu kernel bị giới hạn bởi memory bandwidth, tăng số phép toán vector không nhất thiết cải thiện throughput. Cũng không giả định JIT auto-vectorization của vòng scalar luôn kém hơn Vector API; benchmark trên JDK hiện hành để xác định lựa chọn tốt hơn.

## 12. Khi nào nên dùng và khi nào nên tránh?

| Tình huống | Khuyến nghị |
|---|---|
| Xử lý mảng số lớn, phép toán lặp lại và lane độc lập | Đáng thử Vector API |
| Image processing, signal processing, numerical kernels | Có thể phù hợp nếu kernel ánh xạ tốt sang SIMD |
| Dữ liệu nhỏ, thao tác chỉ chạy vài lần | Giữ code scalar đơn giản cho đến khi benchmark chứng minh cần vector |
| Workload chủ yếu I/O hoặc truy cập dữ liệu ngẫu nhiên | Vector API thường không giải quyết nút thắt chính |
| Logic nhiều nhánh phức tạp và phụ thuộc giữa các phần tử | Cần thiết kế lại kernel; không ép vector hóa máy móc |
| Public library cần API ổn định giữa nhiều JDK | Tránh để kiểu incubator lộ ra public contract |
| Dự án có thể pin JDK và chấp nhận incubator | Có thể thử nghiệm trong module nội bộ, có scalar fallback |

Nếu dùng Vector API trong sản phẩm thử nghiệm, nên đóng gói nó sau một abstraction nội bộ, giữ implementation scalar làm fallback hoặc baseline correctness, kiểm tra CPU/JDK triển khai và có kế hoạch thay đổi API khi nâng cấp.

## 13. Checklist trước khi áp dụng

- [ ] Xác định kernel có đủ dữ liệu và tính độc lập giữa các lane.
- [ ] Dùng species ưu tiên thay vì giả định vector width.
- [ ] Xử lý phần đuôi bằng `loopBound()` và scalar loop hoặc mask.
- [ ] Xác nhận các vector có cùng species trước khi kết hợp.
- [ ] Kiểm tra kết quả trên dữ liệu biên và so sánh với scalar baseline.
- [ ] Đo trên CPU/JDK mục tiêu bằng JMH.
- [ ] Đánh giá floating-point tolerance và integer overflow.
- [ ] Thêm module `jdk.incubator.vector` trong build/runtime hoặc `requires` trong module descriptor.
- [ ] Ghi rõ JDK 26 là incubator lần 11, JDK 27 là incubator lần 12.
- [ ] Không công bố Vector API như một API Java SE final hoặc giả định tương thích dài hạn.

## Kết luận

Vector API cho phép Java biểu đạt phép toán SIMD theo vector, lane, species và mask. JDK 26 tiếp tục API ở incubator lần 11 theo JEP 529; JDK 27 tiếp tục ở lần 12 theo JEP 537. Cả hai đều dùng module `jdk.incubator.vector`, chưa phải API Java SE ổn định và cần được bật bằng `--add-modules` hoặc khai báo `requires` trong module system. Để dùng hiệu quả, hãy chọn `SPECIES_PREFERRED`, xử lý phần đuôi đúng cách, kiểm tra semantics số học và benchmark với scalar baseline trên CPU triển khai thực tế. Giữ API incubator sau một lớp abstraction nội bộ và kiểm tra lại khi nâng cấp JDK.

## Tài liệu tham khảo

- [JEP 529: Vector API (Eleventh Incubator), JDK 26](https://openjdk.org/jeps/529)
- [JEP 537: Vector API (Twelfth Incubator), JDK 27](https://openjdk.org/jeps/537)
- [Java 26 API – Module jdk.incubator.vector](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/module-summary.html)
- [Java 26 API – Package jdk.incubator.vector](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html)
- [Java 26 API – Vector](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html)
- [Java 26 API – VectorSpecies](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html)
- [Java 27 API – Module jdk.incubator.vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html)
- [Java 27 API – Package jdk.incubator.vector](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html)
- [Significant Changes in JDK 26 Release](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html)
- [Significant Changes in JDK 27 Release](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
