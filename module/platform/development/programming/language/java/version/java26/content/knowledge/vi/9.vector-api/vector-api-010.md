# JIT, đường thực thi vô hướng và giới hạn phần cứng

Vector API không bảo đảm mọi phép toán Java sẽ chạy bằng lệnh SIMD. API định nghĩa kết quả theo phép toán vô hướng áp dụng độc lập lên từng lane; runtime có thể biên dịch các phép toán đó thành lệnh vector của CPU khi JIT và phần cứng hỗ trợ. Nếu một phép toán không thể được biên dịch thành lệnh vector, runtime có implementation vô hướng mặc định để vẫn cho kết quả đúng. Vì vậy, cùng một chương trình Vector API có thể được tăng tốc trên máy này và chạy theo đường vô hướng trên máy khác.

Trong JDK 27, Vector API vẫn là **Twelfth Incubator** (JEP 537), thuộc module `jdk.incubator.vector`. Nội dung bài tập tập trung vào cách JIT chọn đường thực thi, trường hợp phải chạy vô hướng và những giới hạn của implementation hiện tại. Các ghi chú phần cứng dưới đây là ghi chú của Oracle JDK 27; nhà cung cấp JDK hoặc bản build khác có thể có mức hỗ trợ khác. [JDK 27 package documentation](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html) · [JDK 27 `Vector`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html) · [JEP 537](https://openjdk.org/jeps/537).

## 1. Từ biểu thức Vector API đến lệnh máy

Một phép toán như `va.add(vb)` được viết bằng Java, nhưng ý nghĩa của nó là cộng các lane tương ứng. Với vector có 8 lane, phép toán biểu diễn 8 phép cộng độc lập. API mô tả hành vi theo các phép toán scalar cơ sở, nên có thể định nghĩa chính xác kết quả mà không phụ thuộc CPU có SIMD hay không.

Khi chương trình chạy trên một runtime có JIT, runtime có thể nhận diện các phép toán Vector API và biên dịch chúng thành lệnh vector phù hợp với CPU. Nếu phép toán và vector shape được hỗ trợ, nhiều lane có thể được xử lý song song bằng một hoặc nhiều lệnh SIMD. Nếu không, implementation vô hướng mặc định tính từng lane theo ngữ nghĩa của API.

```text
Mã Java dùng Vector API
          |
          v
Bytecode và runtime JDK
          |
          v
JIT kiểm tra operation + species/shape + khả năng nền tảng
          |
          +------------------------------+
          |                              |
          v                              v
Biên dịch được thành SIMD         Không biên dịch được thành SIMD
          |                              |
          v                              v
Lệnh vector của CPU               Implementation vô hướng mặc định
          |                              |
          +---------------+--------------+
                          |
                          v
                 Cùng ngữ nghĩa kết quả
```

Đây là cách hiểu về hai đường thực thi, không phải một API để ứng dụng chọn thủ công. Ứng dụng chọn phép toán, element type và species; runtime quyết định cách hiện thực trên nền tảng đang chạy.

### Ngữ nghĩa lane-wise và scalar fallback

Javadoc định nghĩa một phép toán lane-wise bằng phép toán scalar tương ứng lặp lại trên từng lane. Ví dụ `a.add(b)` có thể hiểu như sau:

```java
// Mô hình ngữ nghĩa của một phép cộng vector.
for (int lane = 0; lane < a.length(); lane++) {
    result[lane] = a.lane(lane) + b.lane(lane);
}
```

Đây là pseudocode giải thích ngữ nghĩa, không phải cách viết thay thế tối ưu cho Vector API. Trên CPU có hỗ trợ phù hợp, JIT có thể thực hiện nhiều phép cộng trong một lệnh vector. Nếu không thể biên dịch operation đó thành lệnh vector, runtime dùng implementation vô hướng mặc định.

Scalar fallback bảo đảm tính đúng đắn và tính portable của chương trình. Nó không bảo đảm lợi ích hiệu năng SIMD. Nếu workload chạy chủ yếu bằng đường fallback, Vector API có thể không nhanh hơn vòng lặp scalar thông thường và còn có thêm chi phí tổ chức dữ liệu hoặc gọi API.

## 2. Phân biệt Vector API với JIT auto-vectorization

HotSpot JIT cũng có thể tự vector hóa một số vòng lặp scalar. Ví dụ, một vòng lặp đơn giản đọc hai mảng, cộng từng cặp phần tử rồi ghi sang mảng thứ ba có thể được compiler nhận diện và chuyển thành SIMD. Tuy nhiên, auto-vectorization phụ thuộc cấu trúc vòng lặp, phụ thuộc dữ liệu, các nhánh, aliasing và khả năng nhận diện của compiler; không phải mọi vòng lặp scalar đều được chuyển đổi.

Vector API biểu diễn ý định vector hóa một cách tường minh trong mã nguồn:

```java
import jdk.incubator.vector.FloatVector;

// Giả sử SPECIES, a, b, c và offset đã được khai báo.
// Scalar source: JIT có thể auto-vectorize, nhưng không được bảo đảm.
for (int i = 0; i < a.length; i++) {
    c[i] = a[i] + b[i];
}

// Vector API: lập trình viên diễn đạt rõ phép cộng theo lane.
FloatVector va = FloatVector.fromArray(SPECIES, a, offset);
FloatVector vb = FloatVector.fromArray(SPECIES, b, offset);
va.add(vb).intoArray(c, offset);
```

Hai cách viết khác nhau ở mức ý định của chương trình:

| Cách viết | Ai diễn đạt vector hóa? | Điều cần hiểu |
|---|---|---|
| Vòng lặp scalar | JIT tự phân tích và quyết định có auto-vectorize hay không. | Có thể sinh SIMD, nhưng không nên giả định compiler luôn nhận diện được. |
| Vector API | Mã nguồn mô tả trực tiếp phép toán trên lane. | Runtime có đường biên dịch vector chuyên biệt; nếu không thể sinh lệnh SIMD, implementation scalar mặc định vẫn thực hiện phép toán. |

Không nên mặc định rằng vòng lặp scalar dùng làm baseline chắc chắn chạy bằng lệnh scalar. JIT có thể auto-vectorize chính baseline đó. Khi so sánh hiệu năng, cần đo mã đã warm up và nếu cần xác minh instruction đã sinh, kiểm tra mã máy thay vì suy luận từ cú pháp Java.

## 3. Vì sao vector shape quyết định khả năng sinh SIMD?

Một vector có `VectorShape` xác định kích thước logic và `VectorSpecies` xác định tổ hợp element type với shape. Ví dụ, `IntVector.SPECIES_512` biểu diễn vector int có shape 512 bit. Tuy nhiên, nền tảng không nhất thiết hỗ trợ mọi shape mà API định nghĩa.

JDK 27 package documentation nêu rõ: nếu code dùng `IntVector` với shape 512 bit trên nền tảng chỉ hỗ trợ vector 256 bit, phép toán đó không được biên dịch thành lệnh vector; implementation vô hướng mặc định được dùng. Chương trình vẫn có thể chạy đúng, nhưng không có mức tăng tốc SIMD mong muốn.

### Ưu tiên `SPECIES_PREFERRED`

Với thuật toán tổng quát, bắt đầu bằng species được nền tảng ưu tiên:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

static final VectorSpecies<Float> SPECIES = FloatVector.SPECIES_PREFERRED;

static void printVectorConfiguration() {
    System.out.println("species: " + SPECIES);
    System.out.println("shape: " + SPECIES.vectorShape());
    System.out.println("bits: " + SPECIES.vectorBitSize());
    System.out.println("lanes: " + SPECIES.length());
}
```

`SPECIES_PREFERRED` chọn shape ưu tiên chung cho các kiểu lane, với kích thước lớn nhất có thể mà vẫn hỗ trợ tất cả lane type. Vì vậy, các preferred species của `byte`, `short`, `int`, `long`, `float` và `double` có cùng shape. Điều này hữu ích khi thuật toán chuyển kiểu hoặc reinterpret vector giữa nhiều element type.

`VectorSpecies.ofLargestShape(type)` có thể chọn shape lớn hơn cho một element type cụ thể, nhưng shape đó không nhất thiết hỗ trợ mọi element type khác. Nếu thuật toán cần reinterpret hoặc chuyển qua nhiều kiểu lane, `SPECIES_PREFERRED` thường portable hơn.

Không hiểu `SPECIES_PREFERRED` là cam kết rằng mọi phép toán sẽ được ánh xạ thành đúng một lệnh phần cứng hoặc luôn nhanh nhất với mọi workload. Đây là lựa chọn mặc định hợp lý cho SIMD tổng quát; hiệu năng thực tế vẫn phụ thuộc operation, CPU, JIT và dữ liệu.

### Tránh cố định shape nếu không có lý do

```java
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

// Dễ mất đường SIMD trên máy không hỗ trợ shape 512 bit.
static final VectorSpecies<Integer> FIXED = IntVector.SPECIES_512;

// Thích ứng với shape được runtime ưu tiên.
static final VectorSpecies<Integer> PORTABLE = IntVector.SPECIES_PREFERRED;
```

Chỉ cố định shape khi yêu cầu thuật toán, benchmark và tập phần cứng triển khai đã được kiểm soát. Nếu ứng dụng chạy trên nhiều CPU, chọn preferred species để runtime có cơ hội dùng shape phù hợp với từng máy.

## 4. Giới hạn phần cứng trong Oracle JDK 27

Vector API được thiết kế để sử dụng SIMD resources như vector registers và vector instructions. Tuy nhiên, mức hỗ trợ trong implementation có giới hạn. Javadoc `Vector` của JDK 27 mô tả các nền tảng mà implementation hiện tại được tối ưu tốt nhất:

| Nền tảng | Hỗ trợ được nêu trong JDK 27 | Giới hạn cần nhớ |
|---|---|---|
| Intel x64 | CPU hỗ trợ AVX2 đến AVX-512. | Implementation hiện tại chưa dùng mask registers và các lệnh phần cứng nhận mask của AVX-512. |
| ARM AArch64 | CPU hỗ trợ NEON. | API được thiết kế để có thể hỗ trợ ARM SVE với vector size từ 128 đến 2048 bit, nhưng JDK 27 chưa có implementation SVE và general masking tương ứng. |
| Nền tảng không có SIMD chuyên dụng | Vector API vẫn hoạt động đúng. | Không nên kỳ vọng có lợi ích hiệu năng đặc biệt từ Vector API. |

Đây là ghi chú của implementation được mô tả trong Oracle JDK 27, không phải danh sách đầy đủ mọi khả năng của mọi nhà cung cấp JDK. Khi triển khai trên runtime khác, hãy kiểm tra tài liệu và benchmark của chính bản phân phối đó.

### Không đồng nhất vector shape với thanh ghi vật lý

`VectorShape` là định dạng vector của API. Nó không phải cam kết rằng mỗi object vector luôn nằm trong một thanh ghi vật lý có cùng số bit. Thanh ghi thực tế và cách compiler chia hoặc kết hợp operation là chi tiết của implementation. Vì vậy, đừng suy luận rằng `SPECIES_512` chắc chắn đồng nghĩa một lệnh AVX-512 được thực thi.

### Các phép toán không có hỗ trợ SIMD tối ưu

JDK 27 ghi nhận một số giới hạn cụ thể:

- **Masked lane-wise operations:** implementation hỗ trợ theo cách portable bằng cách kết hợp phép toán không mask với `blend`. Do đó, mask không nhất thiết trở thành predicated instruction của CPU; có thể cần thêm phép toán để chọn lane.
- **Floating-point transcendental operations:** các phép toán như `SIN` và `LOG` hiện chưa có lệnh vector hóa tối ưu trong implementation được mô tả. Không giả định mọi phép toán trên `FloatVector` hoặc `DoubleVector` đều có tốc độ SIMD tương đương `add` hay `mul`.
- **Cross-lane movement:** `rearrange`, `slice`, `unslice`, `compress`, `expand` và reduction di chuyển hoặc kết hợp dữ liệu giữa các lane. Các thao tác này có thể cần lệnh shuffle, nhiều lệnh hoặc bước xử lý bổ sung; chi phí phụ thuộc kiến trúc.
- **Shape-changing conversions:** thay đổi shape có thể cần di chuyển dữ liệu hoặc tạo nhiều bước trung gian. API giữ phần lớn operation shape-invariant để tránh làm code portable trở nên phụ thuộc vào tập shape của một CPU.

Vì thế, số lane không phải hệ số tăng tốc cố định. Một vector 512 bit không bảo đảm nhanh gấp đôi vector 256 bit; phép toán, khả năng phần cứng, băng thông bộ nhớ và chi phí chuyển dữ liệu đều ảnh hưởng kết quả.

## 5. Ví dụ: một thuật toán chạy trên nhiều đường thực thi

Ví dụ tính tích vô hướng minh họa cả vector loop lẫn phần đuôi scalar. Vòng vector dùng preferred species; vòng scalar xử lý số phần tử còn lại không đủ một vector.

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorOperators;
import jdk.incubator.vector.VectorSpecies;

public final class DotProduct {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    public static float compute(float[] a, float[] b) {
        if (a.length != b.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }

        int upperBound = SPECIES.loopBound(a.length);
        int i = 0;
        FloatVector accumulator = FloatVector.zero(SPECIES);

        // Runtime có thể biên dịch các phép toán vector thành SIMD.
        for (; i < upperBound; i += SPECIES.length()) {
            FloatVector va = FloatVector.fromArray(SPECIES, a, i);
            FloatVector vb = FloatVector.fromArray(SPECIES, b, i);
            accumulator = accumulator.add(va.mul(vb));
        }

        float sum = accumulator.reduceLanes(VectorOperators.ADD);

        // Phần đuôi luôn được viết dưới dạng scalar.
        for (; i < a.length; i++) {
            sum += a[i] * b[i];
        }

        return sum;
    }
}
```

Trên máy có shape và operation được JIT hỗ trợ, vòng đầu có thể dùng SIMD. Nếu shape hoặc operation không thể được biên dịch thành lệnh vector, runtime dùng scalar implementation mặc định. Vòng cuối được viết rõ là scalar để xử lý `a.length % SPECIES.length()` phần tử còn dư.

Ví dụ trên vẫn đúng khi chạy trên máy không có SIMD chuyên dụng. Tuy nhiên, nó không bảo đảm nhanh hơn một phiên bản scalar. Phép reduction còn có thể dùng thứ tự cộng khác vòng scalar tuần tự, nên kết quả `float` có thể khác vài bit cuối do làm tròn. Với ứng dụng cần độ chính xác cụ thể, hãy xác định tolerance và kiểm thử theo miền dữ liệu thực.

## 6. Vì sao masked loop có thể tốn chi phí hơn?

Một cách xử lý phần đuôi là tạo mask cho mọi vòng lặp:

```java
for (int i = 0; i < a.length; i += SPECIES.length()) {
    var mask = SPECIES.indexInRange(i, a.length);
    var va = FloatVector.fromArray(SPECIES, a, i, mask);
    var vb = FloatVector.fromArray(SPECIES, b, i, mask);
    va.add(vb).intoArray(result, i, mask);
}
```

Code này dễ viết và không đọc/ghi vượt biên. Nhưng package documentation của JDK 27 lưu ý rằng dùng mask ở mọi vòng có thể không đạt hiệu năng tối ưu với mảng lớn. Nếu chỉ block cuối cần mask, có thể dùng `SPECIES.loopBound(length)` để chạy các block đầy đủ, sau đó xử lý phần đuôi bằng scalar loop như ví dụ tích vô hướng.

Lý do không chỉ nằm ở việc tạo object mask. Phần cứng có thể không có lệnh predicated phù hợp cho mọi operation; implementation có thể phải kết hợp phép toán không mask với `blend`. Hãy benchmark cả hai cách trên CPU đích thay vì mặc định masked loop luôn nhanh hơn.

## 7. Các yếu tố khác làm mất lợi ích SIMD

Ngay cả khi operation được biên dịch thành lệnh vector, workload vẫn có thể không nhanh hơn đáng kể:

1. **Workload quá nhỏ:** chi phí gọi method, kiểm tra giới hạn, tạo mask hoặc reduction có thể lớn hơn thời gian tính toán tiết kiệm được.
2. **Memory-bound:** nếu thời gian chủ yếu nằm ở đọc/ghi mảng, tăng số phép toán trong mỗi lệnh không giải quyết được giới hạn băng thông bộ nhớ.
3. **Dữ liệu không liên tục hoặc phải shuffle nhiều:** truy cập dữ liệu và chuyển lane có thể tốn nhiều lệnh hơn phần số học.
4. **Nhiều nhánh hoặc mask phức tạp:** các lane không hoạt động làm giảm lượng công việc hữu ích; implementation có thể cần blend hoặc xử lý bổ sung.
5. **Phép toán không có lệnh vector phù hợp:** transcendental functions và một số phép chuyển đổi có thể đi theo scalar path hoặc nhiều instruction sequence.
6. **Species không phù hợp:** shape cố định vượt quá khả năng nền tảng có thể buộc runtime dùng scalar implementation.
7. **Vector objects được lưu trữ không phù hợp:** `Vector`, `VectorMask`, `VectorShuffle` và `VectorSpecies` là value-based types. Lưu chúng trong field thông thường hoặc phần tử mảng có thể làm giảm khả năng tối ưu; ưu tiên local variables, parameters và `static final` cho species.

## 8. Xác minh đường thực thi và đo hiệu năng

Không có một lời gọi Java portable nào bảo đảm trả lời “method này đã chạy bằng AVX2 hay AVX-512?”. Việc in species chỉ cho biết shape và lane count mà code yêu cầu; nó không chứng minh JIT đã sinh ra instruction SIMD cho mọi operation.

### Kiểm tra cấu hình vector

Có thể ghi log species khi khởi động hoặc trong benchmark:

```java
System.out.printf(
        "species=%s, shape=%s, bits=%d, lanes=%d%n",
        SPECIES,
        SPECIES.vectorShape(),
        SPECIES.vectorBitSize(),
        SPECIES.length()
);
```

Thông tin này giúp phát hiện ứng dụng đang chọn shape nào trên từng máy. Nó không thay thế việc kiểm tra mã máy.

### Kiểm tra mã máy khi thật sự cần

Với HotSpot, có thể dùng diagnostic disassembly để xem mã máy mà JIT tạo ra, ví dụ:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintAssembly --add-modules jdk.incubator.vector -cp out VectorBenchmark
```

Việc in assembly phụ thuộc HotSpot build và thư viện disassembler `hsdis` có sẵn trên môi trường. Cờ này là công cụ chẩn đoán riêng của HotSpot, không phải API Java portable. `PrintCompilation` hoặc log JIT cho biết method được biên dịch, nhưng tự nó chưa chứng minh operation vector đã trở thành lệnh SIMD cụ thể.

### Benchmark đúng cách

Khi so sánh scalar và Vector API, hãy dùng JMH hoặc benchmark harness phù hợp:

- Dùng warmup để JIT có thời gian tối ưu method; đo nhiều iteration và nhiều fork.
- Dùng cùng dữ liệu, cùng thuật toán và cùng điều kiện JVM cho hai phiên bản.
- Đo nhiều kích thước dữ liệu: nhỏ, vừa, lớn; dữ liệu vừa cache và dữ liệu vượt cache.
- Tiêu thụ kết quả benchmark để tránh dead-code elimination.
- Chạy trên từng kiến trúc CPU quan trọng trong production; không suy ra hiệu năng của ARM từ kết quả x64 hoặc ngược lại.
- So sánh cả scalar source và Vector API. Nhớ rằng scalar source cũng có thể được JIT auto-vectorize.
- Ghi lại JDK vendor/build, phiên bản CPU, OS, species, lane count và JVM flags cùng kết quả.
- Đo throughput, latency, CPU utilization và memory bandwidth khi phù hợp; không chỉ nhìn một con số thời gian chạy.

Không dùng một lần đo bằng `System.nanoTime()` hoặc kết quả của một máy phát triển để kết luận Vector API luôn nhanh hơn. Chỉ giữ phiên bản vector nếu benchmark đại diện chứng minh lợi ích đủ lớn và chi phí bảo trì API incubator là chấp nhận được.

## 9. Trạng thái API và cách chạy trên JDK 27

Vector API trong JDK 27 là **Twelfth Incubator** theo JEP 537, thuộc module `jdk.incubator.vector`. Đây là incubator module, không phải Java SE API final và không phải preview feature.

Với ứng dụng classpath, cần resolve module khi biên dịch và chạy:

```bash
javac --release 27 --add-modules jdk.incubator.vector -d out src/VectorBenchmark.java
java --add-modules jdk.incubator.vector -cp out VectorBenchmark
```

Không dùng `--enable-preview` để bật Vector API. Khi chuyển sang JDK release sau, đọc lại package documentation, kiểm tra module/API và biên dịch lại. Incubator API có thể thay đổi; không nên để các kiểu `Vector`, `FloatVector` hoặc `VectorSpecies` trở thành hợp đồng công khai của thư viện nếu không kiểm soát được JDK mà ứng dụng tiêu thụ sẽ dùng.

## 10. Checklist chẩn đoán khi Vector API không tăng tốc

- [ ] Đã xác nhận đang dùng đúng JDK build và module `jdk.incubator.vector`.
- [ ] Đã kiểm tra species, shape, vector bit size và số lane trên runtime đích.
- [ ] Đã dùng `SPECIES_PREFERRED` trừ khi có lý do và benchmark cho shape cố định.
- [ ] Đã xác minh CPU và JDK implementation có hỗ trợ operation cần thiết.
- [ ] Đã kiểm tra operation có thuộc nhóm bị giới hạn như masked operation hoặc floating-point transcendental hay không.
- [ ] Đã đánh giá memory bandwidth, cache, tail loop, shuffle và reduction.
- [ ] Đã nhớ rằng scalar source có thể được JIT auto-vectorize.
- [ ] Đã dùng JMH hoặc benchmark harness có warmup, nhiều iteration và nhiều fork.
- [ ] Nếu cần chứng minh SIMD, đã xem mã máy JIT trên đúng HotSpot build; không suy luận từ species hoặc log biên dịch đơn thuần.
- [ ] Đã benchmark trên các CPU thực tế mà ứng dụng hỗ trợ.
- [ ] Đã quyết định rõ rủi ro phụ thuộc API incubator và có phương án thay thế khi API đổi.

## Tài liệu tham khảo chính thức

- [JEP 537: Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537)
- [Java SE 27 — Package `jdk.incubator.vector`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html)
- [Java SE 27 — `Vector`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html)
- [Java SE 27 — `VectorSpecies`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html)
- [Java SE 27 — `VectorShape`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorShape.html)
- [Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
- [Advancing AI by Accelerating Java on Parallel Architectures — Inside.java](https://inside.java/2024/10/23/java-and-ai/)
- [The `javac` Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)

*Cập nhật nội dung: 27-11-2026. Các giới hạn AVX2/AVX-512, NEON, SVE, masking và transcendental functions được ghi theo tài liệu Oracle JDK 27; xác minh lại trên JDK vendor/build và CPU thực tế trước khi tối ưu production.*
