# Giới hạn cam kết tương thích của incubator và tiêu chí duy trì cách tính vô hướng

> **Chương:** Vector API
>
> **Phạm vi:** JDK 25 với JEP 508 (Tenth Incubator), đặt trong bối cảnh JDK 26/JEP 529 và JDK 27/JEP 537. Vector API vẫn là incubator module, chưa phải API Java SE ổn định. Bài học tập trung vào giới hạn tương thích, cách cô lập dependency, cách viết vector loop có scalar tail và tiêu chí quyết định khi nào giữ cách tính vô hướng.

## 1. Vector API giải quyết bài toán gì?

Với cách tính vô hướng (scalar), chương trình xử lý từng phần tử:

~~~java
for (int i = 0; i < a.length; i++) {
    result[i] = a[i] + b[i];
}
~~~

Với SIMD (Single Instruction, Multiple Data), một lệnh vector có thể thực hiện cùng phép toán trên nhiều lane dữ liệu trong một lần:

~~~text
Scalar:
  a[0] + b[0] -> result[0]
  a[1] + b[1] -> result[1]
  a[2] + b[2] -> result[2]
  a[3] + b[3] -> result[3]

SIMD vector:
  [a0, a1, a2, a3] + [b0, b1, b2, b3]
                 |
                 v
        [r0, r1, r2, r3]
~~~

Vector API cung cấp các kiểu như IntVector, FloatVector, DoubleVector, VectorMask và VectorSpecies để diễn đạt phép toán theo lane. JIT compiler có thể chuyển các phép toán này thành lệnh SIMD phù hợp với CPU đang chạy.

Các workload thường có cơ hội hưởng lợi:

- Cộng, nhân, chuẩn hóa hoặc biến đổi các mảng số lớn.
- Tính toán ma trận, ảnh, tín hiệu và dữ liệu khoa học.
- Một số bước tiền xử lý trong analytics hoặc inference.
- Vòng lặp có dữ liệu liên tục, ít nhánh và cùng một phép toán lặp lại trên nhiều phần tử.

Vector API không tự làm mọi chương trình nhanh hơn. Với dữ liệu nhỏ, code bị giới hạn bởi băng thông bộ nhớ, nhiều nhánh hoặc nhiều thao tác không vector hóa được, chi phí phụ có thể lớn hơn lợi ích.

## 2. Trạng thái incubator qua các phiên bản Java

Vector API đã trải qua nhiều vòng incubator. Tình trạng đến JDK 27:

| JDK | JEP | Vòng phát triển | Trạng thái |
| --- | --- | --- | --- |
| 25 | JEP 508 | Tenth Incubator | Module incubator |
| 26 | JEP 529 | Eleventh Incubator | Module incubator |
| 27 | JEP 537 | Twelfth Incubator | Module incubator |

JDK 25 đưa API vào vòng thứ mười. JDK 26 tiếp tục vòng thứ mười một; JDK 27 tiếp tục vòng thứ mười hai. Các vòng gần đây duy trì phần lớn mô hình lập trình vector hiện có, vì vậy những pattern cốt lõi trong bài vẫn dùng được ở các JDK mới hơn. Tuy nhiên, việc API đã tồn tại qua nhiều phiên bản **không tạo ra cam kết tương thích**.

Vector API được phân phối trong module có tên jdk.incubator.vector. Theo quy ước incubator module:

- API không thuộc Java SE Platform.
- Ứng dụng phải chủ động đưa module vào module graph.
- Chữ ký, hành vi, tên API hoặc cách triển khai có thể thay đổi giữa các JDK.
- Một incubator module có thể được nâng cấp, thiết kế lại hoặc bị loại bỏ trong bản phát hành sau.

Vì vậy, không xem Vector API như một dependency có bảo đảm source compatibility hoặc binary compatibility dài hạn. Đây là công cụ để thử nghiệm và khai thác SIMD trong phạm vi đã kiểm soát.

## 3. Incubator khác preview như thế nào?

Không nhầm incubator module với preview feature:

| Đặc điểm | Incubator module | Preview feature |
| --- | --- | --- |
| Phạm vi | API hoặc công cụ trong module JDK riêng | Tính năng ngôn ngữ, VM hoặc API được preview theo cơ chế JEP 12 |
| Ví dụ | jdk.incubator.vector | Structured Concurrency ở các bản preview |
| Cách bật | Thêm module vào module graph | Dùng cờ --enable-preview khi compile và run |
| Tương thích | Có thể đổi hoặc bị loại bỏ khi còn incubating | Có thể đổi trước khi final; tuân theo quy trình preview |
| Vị trí API | Namespace/module JDK-specific | Tùy feature; không nhất thiết là module incubator |

Với Vector API, cách bật thông thường là --add-modules jdk.incubator.vector. Không cần --enable-preview chỉ vì đang dùng Vector API.

Đây là khác biệt có ý nghĩa trong build pipeline: một cấu hình chỉ thêm --enable-preview mà quên resolve module incubator vẫn không làm cho package jdk.incubator.vector khả dụng.

## 4. Bật module trong ứng dụng classpath

Ví dụ biên dịch bằng JDK 25:

~~~bash
javac --release 25 --add-modules jdk.incubator.vector -d out src/main/java/example/VectorAdd.java
java --add-modules jdk.incubator.vector -cp out example.VectorAdd
~~~

Khi chạy, JVM có thể in cảnh báo cho biết đang sử dụng incubator module. Cảnh báo này là tín hiệu về trạng thái API, không phải lỗi biên dịch.

Nếu dùng JDK 27 để kiểm tra tương thích:

~~~bash
javac --release 27 --add-modules jdk.incubator.vector -d out src/main/java/example/VectorAdd.java
java --add-modules jdk.incubator.vector -cp out example.VectorAdd
~~~

Luôn compile và test trên từng JDK mà sản phẩm tuyên bố hỗ trợ. Không chỉ dựa vào việc source code biên dịch được trên máy phát triển.

### 4.1. Ứng dụng dùng named module

Trong module-info.java, khai báo dependency tường minh:

~~~java
module example.analytics {
    requires jdk.incubator.vector;
}
~~~

Sau đó compile và chạy ứng dụng theo module path như các module JDK khác. Khi tạo custom runtime image bằng jlink, phải đưa jdk.incubator.vector vào danh sách module cần đóng gói.

### 4.2. Không bật preview flags không liên quan

Vector API là incubator module, không phải preview language feature. Cấu hình tối thiểu cần resolve module; không thêm --enable-preview nếu ứng dụng không dùng một preview feature khác.

## 5. Giới hạn tương thích cần dự phòng

Khi API còn incubating, có ít nhất ba lớp tương thích cần được quản lý:

| Lớp tương thích | Rủi ro | Cách dự phòng |
| --- | --- | --- |
| Source compatibility | Source có thể không compile sau khi chữ ký hoặc kiểu API thay đổi | Giữ adapter nhỏ, compile trên mọi JDK mục tiêu |
| Binary compatibility | Class file được biên dịch với một phiên bản module có thể không liên kết được với phiên bản khác | Build lại ứng dụng theo JDK runtime; không coi binary cũ là hợp đồng |
| Behavioral compatibility | Cách triển khai, tối ưu hoặc kết quả ở một số phép toán có thể thay đổi | Kiểm thử kết quả, sai số số học và hiệu năng trên từng runtime |

Không công khai các kiểu Vector, VectorSpecies hoặc VectorMask trong public API của thư viện dùng chung nếu không cần thiết. Một thư viện có thể giữ kiểu dữ liệu ổn định như primitive array, ByteBuffer hoặc domain object ở biên; phần vector hóa nằm sau một adapter nội bộ.

Ví dụ cấu trúc:

~~~text
analytics-core
  ├── ScalarKernel          API nội bộ ổn định
  ├── VectorKernel          phụ thuộc jdk.incubator.vector
  └── KernelSelector        chọn implementation theo cấu hình

application
  └── gọi analytics-core bằng primitive arrays
~~~

Nếu sau này API incubator đổi, phần cần sửa chủ yếu nằm trong VectorKernel và build configuration. Nếu module không còn được cung cấp trong một runtime, scalar implementation vẫn có thể duy trì chức năng cốt lõi.

## 6. Dùng preferred species thay vì cố định kích thước vector

Mỗi vector có:

- Element type: kiểu lane như int, long, float hoặc double.
- Shape: tổng số bit của vector.
- Species: kết hợp element type và shape, xác định số lane.

Không giả định CPU nào cũng hỗ trợ vector 256-bit hoặc 512-bit. JDK cung cấp preferred species cho nền tảng đang chạy:

~~~java
private static final VectorSpecies<Integer> SPECIES =
        IntVector.SPECIES_PREFERRED;
~~~

SPECIES_PREFERRED cho phép code thích nghi với shape được runtime ưu tiên. Số lane lấy từ SPECIES.length(); không hard-code số 4, 8 hoặc 16.

Không dùng phép bit-mask tự chế như:

~~~java
int bound = length & ~(SPECIES.length() - 1);
~~~

để thay cho helper của API. Cách này chỉ đúng khi lane count là lũy thừa của hai; API không yêu cầu mọi shape phải có đặc điểm đó.

## 7. Giữ scalar implementation làm chuẩn tham chiếu

Trước khi vector hóa, viết một cách tính vô hướng đơn giản, dễ đọc và dễ kiểm thử. Đây là implementation tham chiếu cho:

- Kiểm thử kết quả trên nhiều kích thước dữ liệu.
- Đối chiếu hành vi ở CPU không có SIMD phù hợp.
- So sánh hiệu năng với khả năng auto-vectorization của JIT.
- Duy trì chức năng nếu Vector API đổi hoặc không còn được đóng gói trong runtime.

Ví dụ phép cộng hai mảng int:

~~~java
static void addScalar(int[] a, int[] b, int[] result) {
    checkLengths(a, b, result);

    for (int i = 0; i < a.length; i++) {
        result[i] = a[i] + b[i];
    }
}

private static void checkLengths(int[] a, int[] b, int[] result) {
    if (a.length != b.length || a.length != result.length) {
        throw new IllegalArgumentException("Array lengths must match");
    }
}
~~~

Scalar implementation không phải code dự phòng tạm thời. Nó là định nghĩa rõ ràng của phép tính và là đối chứng để đánh giá vector path.

## 8. Vector loop có scalar tail

Ví dụ vector hóa cùng phép cộng:

~~~java
package example;

import java.util.Arrays;
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

public final class VectorAdd {

    private static final VectorSpecies<Integer> SPECIES =
            IntVector.SPECIES_PREFERRED;

    static void add(int[] a, int[] b, int[] result) {
        checkLengths(a, b, result);

        int upperBound = SPECIES.loopBound(a.length);
        int i = 0;

        for (; i < upperBound; i += SPECIES.length()) {
            IntVector va = IntVector.fromArray(SPECIES, a, i);
            IntVector vb = IntVector.fromArray(SPECIES, b, i);

            va.add(vb).intoArray(result, i);
        }

        // Xử lý phần tử còn lại bằng scalar code.
        for (; i < a.length; i++) {
            result[i] = a[i] + b[i];
        }
    }

    private static void checkLengths(int[] a, int[] b, int[] result) {
        if (a.length != b.length || a.length != result.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 3, 4, 5};
        int[] b = {10, 20, 30, 40, 50};
        int[] result = new int[a.length];
        add(a, b, result);
        System.out.println(Arrays.toString(result));
    }
}
~~~

SPECIES.loopBound(a.length) trả về giới hạn lớn nhất để vector loop chỉ xử lý các nhóm đủ lane. Phần tử cuối chưa đủ một vector được xử lý bởi scalar tail.

Ưu điểm:

- Không đọc vượt giới hạn mảng.
- Không cần mask cho từng vòng lặp chính.
- Dễ so sánh với scalar implementation.
- Không giả định lane count cụ thể.

Đây là pattern phù hợp cho vòng lặp dữ liệu tuyến tính, nơi phần lớn phần tử có thể xử lý theo block đầy đủ.

## 9. Mask khi dữ liệu không chia hết theo lane

Một cách khác là dùng VectorMask để xử lý cả block cuối:

~~~java
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorSpecies;

final class MaskedVectorAdd {

    private static final VectorSpecies<Integer> SPECIES =
            IntVector.SPECIES_PREFERRED;

    static void addMasked(int[] a, int[] b, int[] result) {
        checkLengths(a, b, result);

        for (int i = 0; i < a.length; i += SPECIES.length()) {
            VectorMask<Integer> mask = SPECIES.indexInRange(i, a.length);
            IntVector va = IntVector.fromArray(SPECIES, a, i, mask);
            IntVector vb = IntVector.fromArray(SPECIES, b, i, mask);

            va.add(vb).intoArray(result, i, mask);
        }
    }

    private static void checkLengths(int[] a, int[] b, int[] result) {
        if (a.length != b.length || a.length != result.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }
    }
}
~~~

indexInRange tạo mask chỉ bật lane có index nằm trong giới hạn. Các load/store có mask tránh truy cập phần tử ngoài mảng.

Mask hữu ích khi:

- Dữ liệu có ranh giới thay đổi theo từng block.
- Một số lane cần bị loại theo điều kiện.
- Không thể tách phần tử cuối thành một scalar loop đơn giản.

Với mảng dài và chỉ có một tail nhỏ, loopBound cộng scalar tail thường dễ tối ưu hơn vì không phải thực hiện masked operation ở mọi vòng. Hãy benchmark cả hai khi mask là một phần đáng kể của workload.

## 10. Runtime scalar fallback không thay thế scalar baseline

Javadoc của Vector API nêu rõ mỗi operation có default scalar implementation nếu runtime không biên dịch được operation đó thành lệnh vector. Vì vậy, code Vector API vẫn có thể chạy đúng trên nền tảng thiếu SIMD chuyên dụng.

Nhưng cần phân biệt:

1. **Runtime scalar fallback:** JVM thực hiện operation vector bằng implementation scalar để giữ đúng hành vi API.
2. **Scalar baseline của ứng dụng:** code vô hướng riêng, không phụ thuộc module jdk.incubator.vector.

Runtime fallback giúp Vector API chạy được trên nhiều nền tảng, nhưng ứng dụng vẫn cần scalar baseline nếu muốn:

- Chạy trên JDK distribution không có incubator module.
- Loại bỏ dependency incubator khỏi sản phẩm.
- Có một implementation độc lập để đối chiếu kết quả.
- Định tuyến các workload mà vector path không đem lại lợi ích.

Không nên coi việc có scalar fallback nội bộ là bằng chứng rằng mọi môi trường đều có thể nạp module Vector API.

## 11. Phạm vi hỗ trợ phần cứng và giới hạn hiện tại

Javadoc JDK 27 mô tả các nền tảng implementation đang tối ưu tốt nhất:

| Nền tảng | Trạng thái tối ưu được mô tả |
| --- | --- |
| Intel x64 | AVX2 đến AVX-512; masking bằng mask register của AVX-512 chưa được hỗ trợ trực tiếp trong implementation hiện tại |
| ARM AArch64 | NEON |
| ARM SVE | API được thiết kế để có thể hỗ trợ SVE, nhưng implementation hiện tại chưa cung cấp SVE và general masking capability |
| CPU không có SIMD chuyên dụng | Vẫn chạy đúng qua scalar implementation, nhưng thường không có lợi ích hiệu năng đặc biệt |

Một số floating-point transcendental operation như SIN và LOG hiện chưa có vector instruction tối ưu theo implementation note. Nếu workload chủ yếu gọi các phép toán này, không nên mặc định Vector API sẽ tăng tốc.

Các giới hạn trên là mô tả của implementation hiện tại, không phải danh sách hỗ trợ bất biến cho mọi JDK tương lai. Kiểm tra Javadoc và benchmark trên đúng CPU/JDK sẽ triển khai.

## 12. Độ chính xác số học và tính tương đương với scalar

Không phải mọi phép toán vector đều có thể thay thế scalar loop mà không cần kiểm thử ngữ nghĩa.

### Số nguyên

Với phép cộng int theo lane, kết quả từng lane tuân theo phép toán int. Tuy nhiên, vẫn cần kiểm thử các trường hợp tràn số, giá trị âm và ranh giới dữ liệu.

### Số thực dấu phẩy động

Phép toán floating-point có thể nhạy với thứ tự tính:

- Phép cộng số thực không có tính kết hợp tuyệt đối do làm tròn.
- Một phép reduction có thể cộng lane theo thứ tự khác scalar loop tuần tự.
- FMA có thể cho kết quả khác với phép nhân rồi cộng riêng vì chỉ làm tròn một lần.
- NaN, signed zero, infinity và subnormal cần được kiểm tra theo yêu cầu nghiệp vụ.

Nếu hệ thống yêu cầu kết quả bit-for-bit giống scalar, giữ scalar path hoặc chỉ vector hóa những phép toán đã chứng minh tương đương. Nếu cho phép sai số, xác định tolerance rõ ràng và kiểm thử worst-case.

Đừng bật một phép reduction vector chỉ vì nó ngắn hơn. Xác định thứ tự toán học và hợp đồng sai số trước.

## 13. So sánh Vector API với auto-vectorization của JIT

HotSpot JIT có thể tự vector hóa một số scalar loop khi nhận diện được pattern phù hợp. Vì vậy, trước khi đưa Vector API vào:

1. Viết scalar loop rõ ràng, tránh abstraction làm che mất pattern.
2. Benchmark scalar loop trên đúng JDK và CPU.
3. Kiểm tra JIT đã auto-vectorize được chưa nếu công cụ phân tích machine code có sẵn.
4. Chỉ thử Vector API khi scalar code chưa đạt mục tiêu và có cơ hội SIMD rõ ràng.

Vector API hữu ích khi muốn diễn đạt tường minh lane operation, mask, shuffle, conversion hoặc reduction mà JIT không tự nhận diện ổn định từ scalar code.

Nếu JIT đã tạo machine code tốt cho scalar loop, Vector API có thể chỉ làm code phức tạp hơn mà không tăng tốc.

## 14. Tiêu chí giữ scalar hay thêm vector path

| Đặc điểm workload | Hướng ưu tiên |
| --- | --- |
| Mảng nhỏ, số phần tử ít hơn vài vector | Scalar |
| Vòng lặp branch-heavy hoặc truy cập dữ liệu không liên tục | Scalar trước; chỉ vector hóa sau benchmark |
| Workload chủ yếu chờ memory/cache hoặc I/O | Scalar trước; SIMD có thể không giải quyết bottleneck |
| Phép toán số học đơn giản trên mảng lớn, liên tục | Thử Vector API và benchmark |
| Nhiều phép toán lane-wise cùng một block dữ liệu | Vector API có cơ hội giảm chi phí load/store và loop |
| Dùng nhiều SIN/LOG hoặc operation chưa có vector instruction tối ưu | Scalar hoặc thư viện toán học chuyên dụng đã kiểm chứng |
| Runtime không có module incubator hoặc không chấp nhận dependency JDK-specific | Scalar |
| Cần public library API ổn định trên nhiều JDK/vendor | Scalar ở API boundary; vector adapter nội bộ tùy chọn |
| Kết quả phải bit-for-bit giống thứ tự scalar | Giữ scalar nếu vector/reduction không bảo đảm cùng thứ tự |

Vector path chỉ nên được chọn khi đáp ứng cả ba điều kiện:

1. Đúng đắn: kết quả thỏa hợp đồng nghiệp vụ và kiểm thử.
2. Có lợi: benchmark cho thấy cải thiện trên workload đại diện.
3. Có thể vận hành: tổ chức chấp nhận incubator module và có kế hoạch theo dõi thay đổi JDK.

## 15. Benchmark công bằng bằng JMH

Không đo bằng một lần gọi System.nanoTime quanh một vòng lặp. JIT warmup, dead-code elimination, CPU frequency scaling và cache có thể làm kết quả sai lệch.

Benchmark nên có ít nhất hai implementation:

- Scalar reference: vòng lặp từng phần tử.
- Vector candidate: vector loop cộng scalar tail.

Thiết kế phép đo:

1. Dùng JMH với warmup và nhiều measurement iterations.
2. Chạy nhiều fork để tránh kết quả phụ thuộc một lần khởi động JVM.
3. Dùng nhiều kích thước dữ liệu: nhỏ, trung bình, lớn và kích thước không chia hết cho lane count.
4. Dùng cùng dữ liệu đầu vào, cùng CPU affinity/quota và cùng JDK build.
5. Đưa kết quả vào Blackhole hoặc kiểm tra output để tránh dead-code elimination.
6. Đo throughput hoặc latency theo mục tiêu thực tế; không chỉ đo một vòng lặp tổng hợp.
7. So sánh scalar loop có thể auto-vectorize với Vector API.

Nên đo cả:

- Startup và chi phí nạp module.
- Warmup/JIT compilation.
- Throughput sau warmup.
- Allocation rate nếu code tạo object phụ.
- CPU utilization và memory bandwidth khi workload lớn.

Không đặt một ngưỡng tăng tốc cố định cho mọi ứng dụng. Nếu chênh lệch nhỏ hơn độ biến thiên giữa các lần chạy, độ phức tạp và rủi ro tương thích có thể không đáng.

## 16. Chiến lược cô lập dependency cho sản phẩm

Vì module chưa ổn định, có thể giữ hai implementation sau một interface nội bộ:

~~~java
interface IntArrayAdder {
    void add(int[] a, int[] b, int[] result);
}

final class ScalarIntArrayAdder implements IntArrayAdder {
    @Override
    public void add(int[] a, int[] b, int[] result) {
        if (a.length != b.length || a.length != result.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }
        for (int i = 0; i < a.length; i++) {
            result[i] = a[i] + b[i];
        }
    }
}
~~~

Vector implementation nằm trong adapter riêng, chỉ module này import jdk.incubator.vector. Application chỉ biết IntArrayAdder và primitive arrays.

Các lựa chọn triển khai:

- Nếu runtime và tổ chức chấp nhận incubator module, chọn vector adapter bằng cấu hình hoặc dependency injection.
- Nếu module không có trong runtime, chỉ đóng gói scalar implementation.
- Nếu module có nhưng CPU không hỗ trợ SIMD phù hợp, Vector API vẫn chạy đúng nhưng có thể không nhanh hơn; benchmark hoặc chọn scalar theo cấu hình.
- Nếu JDK mới đổi API, chỉ cần cập nhật adapter và kiểm thử tương thích.

Không đưa VectorSpecies hoặc Vector vào DTO, serialized format, public method signature hoặc interface dùng chung giữa nhiều service.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Compiler không tìm thấy package jdk.incubator.vector | Module chưa được resolve | Thêm --add-modules jdk.incubator.vector khi compile/run hoặc requires trong module-info.java |
| JVM báo module không tồn tại | JDK distribution/runtime image không đóng gói module | Kiểm tra runtime image và vendor; giữ scalar build nếu module không có |
| Dùng --enable-preview nhưng vẫn lỗi import | Nhầm incubator với preview | Resolve module bằng --add-modules |
| Vector code chạy nhưng không nhanh hơn | CPU không có SIMD phù hợp, shape không được hỗ trợ hoặc workload không compute-bound | Dùng preferred species, xem machine code và benchmark |
| Vector loop đọc vượt mảng | Không xử lý tail | Dùng SPECIES.loopBound() và scalar tail hoặc masked load/store |
| Kết quả floating-point lệch | Thứ tự reduction, rounding hoặc FMA khác | Xác định tolerance; giữ scalar khi cần bitwise equivalence |
| Build JDK mới không tương thích source cũ | Incubator API đã đổi | Compile theo từng JDK mục tiêu và sửa adapter |
| Public library phụ thuộc incubator module | API nội bộ JDK bị lộ ra ngoài boundary | Ẩn Vector API sau primitive arrays/interface ổn định |
| Performance regression ở mảng nhỏ | Chi phí setup vector lớn hơn công việc | Đặt ngưỡng kích thước dựa trên benchmark hoặc dùng scalar |
| Dùng Vector API cho SIN/LOG nhưng không tăng tốc | Implementation chưa có vectorized instruction tối ưu cho các phép toán đó | Đo đúng operation; chọn scalar hoặc thư viện phù hợp |

## 18. Bài tập thực hành

### Bài A — Cài đặt scalar reference

Viết hàm cộng hai mảng int có kiểm tra độ dài và xử lý mảng rỗng.

**Điều kiện đạt:** kết quả đúng với mảng có giá trị âm, dương và trường hợp tràn int.

### Bài B — Thêm Vector API

Viết vector implementation dùng IntVector.SPECIES_PREFERRED và SPECIES.loopBound().

**Điều kiện đạt:** kết quả bằng scalar reference với các kích thước 0, 1, laneCount - 1, laneCount, laneCount + 1 và nhiều block cộng tail.

### Bài C — So sánh masked tail

Viết thêm implementation dùng VectorMask và indexInRange().

**Điều kiện đạt:** không đọc/ghi ngoài mảng; benchmark được masked loop với vector loop cộng scalar tail.

### Bài D — Kiểm tra tính tương thích

Compile và chạy cùng adapter trên JDK 25 và JDK 27, bật module incubator ở cả hai môi trường.

**Điều kiện đạt:** ghi lại JDK vendor/build, cờ module, lỗi compile/runtime nếu có và kết quả kiểm thử.

### Bài E — Đo hiệu năng

Tạo benchmark JMH cho scalar, scalar có thể auto-vectorize và explicit Vector API. Dùng ít nhất ba kích thước mảng.

**Điều kiện đạt:** giải thích được khi nào vector nhanh hơn, khi nào scalar ngang bằng hoặc tốt hơn và vì sao.

## 19. Checklist quyết định triển khai

- [ ] Đã xác nhận Vector API vẫn là incubator module trong JDK mục tiêu.
- [ ] Đã chấp nhận rủi ro API thay đổi hoặc module bị loại bỏ.
- [ ] Module jdk.incubator.vector được resolve ở compile và runtime.
- [ ] Không dùng --enable-preview thay cho --add-modules.
- [ ] Không lộ kiểu Vector API qua public API hoặc serialized model.
- [ ] Có scalar implementation độc lập và được kiểm thử.
- [ ] Dùng SPECIES_PREFERRED hoặc species phù hợp với nền tảng.
- [ ] Dùng loopBound cộng scalar tail hoặc masked operation đúng ranh giới.
- [ ] Kiểm thử dữ liệu rỗng, nhỏ, không chia hết lane và dữ liệu lớn.
- [ ] Kiểm tra khác biệt floating-point, reduction, overflow và NaN theo yêu cầu.
- [ ] Benchmark bằng JMH trên đúng JDK/CPU/runtime image.
- [ ] So sánh với scalar loop có khả năng auto-vectorization.
- [ ] Có kế hoạch nâng cấp adapter khi chuyển JDK.
- [ ] Chỉ bật vector path khi lợi ích đo được vượt chi phí tương thích và vận hành.

## 20. Tài liệu tham khảo

1. [JEP 508 — Vector API (Tenth Incubator)](https://openjdk.org/jeps/508): trạng thái và mục tiêu Vector API trong JDK 25.
2. [Oracle Java SE 25 — Vector API package summary](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html): vector lanes, species, preferred species, loopBound, masks và scalar implementation.
3. [Oracle Java SE 25 — Module jdk.incubator.vector](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/module-summary.html): module name và trạng thái incubator.
4. [JEP 11 — Incubator Modules](https://openjdk.org/jeps/11): mục đích, opt-in và vòng đời của incubator module.
5. [JEP 529 — Vector API (Eleventh Incubator)](https://openjdk.org/jeps/529): vòng incubator trong JDK 26.
6. [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): xác nhận Vector API là Eleventh Incubator.
7. [JEP 537 — Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537): vòng incubator trong JDK 27.
8. [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): xác nhận Vector API vẫn là incubating API trong JDK 27.
9. [Oracle Java SE 27 — Vector API package and hardware notes](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html): shape/species, AVX2/AVX-512, AArch64 NEON, SVE và giới hạn transcendental.
10. [JEP 338 — Vector API (Incubator)](https://openjdk.org/jeps/338): nền tảng ban đầu của API trong JDK 16.

**Ghi nhớ:** Vector API là lựa chọn SIMD hữu ích cho phép toán số học trên dữ liệu lớn, nhưng đến JDK 27 vẫn là incubator module và không có cam kết tương thích dài hạn. Giữ scalar implementation làm chuẩn đúng đắn, cô lập vector code sau adapter, dùng preferred species và xử lý tail an toàn. Chỉ đưa vector path vào sản phẩm khi kiểm thử tương thích và benchmark trên phần cứng mục tiêu chứng minh lợi ích rõ ràng.
