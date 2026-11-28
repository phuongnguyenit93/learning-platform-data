# Cấu hình module incubator và kiểm tra hỗ trợ của JVM cùng phần cứng

## 1. Mục tiêu và trạng thái của Vector API

**Vector API** cung cấp các kiểu và phép toán để biểu diễn tính toán SIMD (Single Instruction, Multiple Data): một phép toán được áp dụng đồng thời lên nhiều lane dữ liệu. JVM có thể biên dịch phép toán vector thành lệnh SIMD của CPU, chẳng hạn AVX trên Intel/AMD x64 hoặc NEON trên ARM AArch64.

Trong module **JAVA_VERSION_JAVA25**, bài này tập trung vào cách cấu hình module incubator và kiểm tra môi trường trước khi đánh giá hiệu năng:

- Xác định module `jdk.incubator.vector` có trong JDK đang dùng hay không.
- Thêm module khi biên dịch và chạy ứng dụng đặt trên classpath.
- Khai báo dependency trong `module-info.java` khi ứng dụng dùng Java Platform Module System.
- Kiểm tra CPU features mà HotSpot nhận diện và vector species được runtime ưu tiên.
- Phân biệt CPU có SIMD với việc JVM thực sự sinh mã vector cho một phép toán cụ thể.
- Xử lý tình huống API vẫn chạy nhưng không có tăng tốc phần cứng.

### Trạng thái theo từng JDK

Vector API là **incubator API**, không phải API Java SE đã final và cũng không phải preview language feature.

| JDK | JEP | Trạng thái |
|---|---|---|
| JDK 25 | JEP 508 | Lần incubator thứ 10 |
| JDK 26 | JEP 529 | Lần incubator thứ 11 |
| JDK 27 | JEP 537 | Lần incubator thứ 12 |

Tính đến ngày 27/11/2026, Vector API vẫn đang được incubate. JEP 537 tiếp tục duy trì API ở JDK 27; API chưa được chuyển thành tính năng final. Việc tiếp tục incubate liên quan đến các thay đổi về value objects trong Project Valhalla mà Vector API dự kiến sẽ tận dụng khi thích hợp.

**Phạm vi ví dụ:** các lệnh cấu hình và API trong bài được viết cho JDK 25, sử dụng JEP 508. Khi dùng JDK 26 hoặc JDK 27, hãy biên dịch bằng đúng JDK mục tiêu và đọc tài liệu module của release đó. Không giả định mọi phiên bản incubator đều có binary compatibility như API Java SE đã final.

## 2. Hiểu đúng module jdk.incubator.vector

Vector API nằm trong module:

```text
jdk.incubator.vector
```

Module này xuất package:

```text
jdk.incubator.vector
```

Một số kiểu thường dùng:

| Kiểu | Vai trò |
|---|---|
| `Vector` | Lớp cơ sở biểu diễn một vector có nhiều lane |
| `IntVector` | Vector của các giá trị `int` |
| `LongVector` | Vector của các giá trị `long` |
| `FloatVector` | Vector của các giá trị `float` |
| `DoubleVector` | Vector của các giá trị `double` |
| `VectorSpecies` | Chọn element type và vector shape |
| `VectorShape` | Biểu diễn độ rộng vector |
| `VectorMask` | Mặt nạ chọn các lane được xử lý |
| `VectorShuffle` | Hoán vị hoặc sắp xếp lại lane |
| `VectorOperators` | Các toán tử lane-wise như cộng, so sánh, chuyển đổi |

Tên module bắt đầu bằng `jdk.` cho biết đây là module thuộc JDK. Module incubator có thể thay đổi API hoặc bị loại bỏ trong release tương lai. Nó không được bảo đảm có mặt trong mọi Java runtime implementation hoặc trong mọi custom runtime image được tạo bằng `jlink`.

### Incubator khác preview như thế nào?

| Cơ chế | Cách bật | Ý nghĩa |
|---|---|---|
| Incubator module | `--add-modules jdk.incubator.vector` hoặc khai báo `requires` | Thêm một module/API chưa final vào module graph |
| Preview language/API feature | `--enable-preview` | Cho phép sử dụng preview feature của đúng JDK release |

Với Vector API, hãy dùng **module configuration**. Không thêm `--enable-preview` chỉ vì API đang incubate. Hai cơ chế này giải quyết hai vấn đề khác nhau.

## 3. Kiểm tra JDK có cung cấp module hay không

Trước khi sửa build, xác nhận đúng JDK được shell gọi:

```bash
java -version
javac -version
```

Kiểm tra danh sách module:

```bash
java --list-modules | grep jdk.incubator.vector
```

Trên Windows PowerShell:

```powershell
java --list-modules | Select-String "jdk.incubator.vector"
```

Nếu module xuất hiện, xem descriptor của module:

```bash
java --describe-module jdk.incubator.vector
```

Lệnh này giúp xác nhận module có trong runtime image và package được export. Nếu không tìm thấy module:

1. Kiểm tra `java` và `javac` có cùng JDK distribution/version không.
2. Xác nhận đang dùng JDK đầy đủ thay vì runtime image tùy biến đã lược bỏ module.
3. Kiểm tra vendor/build có cung cấp module Vector API theo cấu hình phân phối của họ không.
4. Nếu dùng custom runtime tạo bằng `jlink`, xác nhận module đã được đưa vào image.

Không cố khắc phục lỗi “module not found” bằng cách tải một JAR Vector API độc lập từ Maven Central. Vector API là module đi cùng JDK; hãy chọn đúng JDK có module tương ứng.

## 4. Biên dịch và chạy ứng dụng trên classpath

Với ứng dụng chưa dùng `module-info.java`, module incubator không tự động được resolve chỉ vì source import package của nó. Cần thêm module vào lúc compile và runtime.

Giả sử có file `src/VectorProbe.java`:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public class VectorProbe {
    public static void main(String[] args) {
        VectorSpecies<Float> species = FloatVector.SPECIES_PREFERRED;

        System.out.printf(
            "shape=%s, bits=%d, lanes=%d%n",
            species.vectorShape(),
            species.vectorBitSize(),
            species.length()
        );
    }
}
```

Biên dịch bằng JDK 25:

```bash
javac --release 25 \
  --add-modules jdk.incubator.vector \
  -d out src/VectorProbe.java
```

Chạy:

```bash
java --add-modules jdk.incubator.vector \
  -cp out VectorProbe
```

Giải thích:

- `--release 25` biên dịch source theo Java SE 25.
- `--add-modules jdk.incubator.vector` đưa module incubator vào module graph.
- Khi ứng dụng nằm trên classpath, các class thuộc unnamed module cần đọc module incubator đã được resolve.
- Phải cấu hình ở cả compile time và runtime. Compile thành công không có nghĩa runtime tự resolve module.

Khi chạy, JDK có thể in cảnh báo cho biết đang sử dụng incubator module. Đây là thông báo trạng thái API, không phải lỗi compile hoặc runtime.

## 5. Khai báo dependency khi ứng dụng dùng named module

Nếu ứng dụng có `module-info.java`, khai báo dependency trực tiếp:

```java
module com.example.vectorapp {
    requires jdk.incubator.vector;
}
```

Ví dụ cấu trúc thư mục:

```text
src/
  com.example.vectorapp/
    module-info.java
    com/example/vectorapp/Main.java
```

Class `Main.java`:

```java
package com.example.vectorapp;

import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public class Main {
    public static void main(String[] args) {
        VectorSpecies<Float> species = FloatVector.SPECIES_PREFERRED;
        System.out.println(species);
    }
}
```

Biên dịch module:

```bash
javac --release 25 \
  --module-source-path src \
  -d out \
  -m com.example.vectorapp
```

Chạy module:

```bash
java --module-path out \
  -m com.example.vectorapp/com.example.vectorapp.Main
```

Vì descriptor đã có `requires jdk.incubator.vector`, module system sẽ resolve dependency đó khi resolve ứng dụng. Nếu module không được tìm thấy, kiểm tra JDK compiler/runtime và module image đang dùng.

**Không cần thêm `requires transitive` chỉ để ứng dụng của bạn gọi Vector API.** Dùng `requires` thông thường khi dependency chỉ phục vụ implementation nội bộ. Chỉ cân nhắc re-export dependency nếu API công khai của module thực sự buộc consumer phải đọc kiểu thuộc module incubator; thiết kế như vậy làm tăng coupling với một API chưa final.

## 6. Cấu hình build tool và môi trường IDE

Cấu hình module phải xuất hiện ở đúng nơi thực thi compiler hoặc JVM. Chỉ thêm import vào source không đủ.

### Gradle (Groovy DSL), ứng dụng trên classpath

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 25
    options.compilerArgs += [
        "--add-modules",
        "jdk.incubator.vector"
    ]
}

tasks.withType(Test).configureEach {
    jvmArgs("--add-modules", "jdk.incubator.vector")
}

tasks.withType(JavaExec).configureEach {
    jvmArgs("--add-modules", "jdk.incubator.vector")
}
```

Nếu dùng Gradle Kotlin DSL, cú pháp cấu hình tương ứng sẽ khác; giữ nguyên hai tham số JVM là `--add-modules` và `jdk.incubator.vector`.

### Maven, ứng dụng trên classpath

Trong `maven-compiler-plugin`, thêm compiler arguments:

```xml
<configuration>
    <release>25</release>
    <compilerArgs>
        <arg>--add-modules</arg>
        <arg>jdk.incubator.vector</arg>
    </compilerArgs>
</configuration>
```

Đối với test forked JVM, cấu hình thêm VM argument `--add-modules jdk.incubator.vector` trong plugin chạy test (ví dụ `maven-surefire-plugin`). Đối với ứng dụng chạy qua plugin hoặc launcher riêng, bảo đảm JVM khởi chạy ứng dụng cũng nhận tùy chọn này.

### IDE

Trong cấu hình Run/Debug:

1. Chọn đúng JDK 25 làm Project SDK/Gradle JVM/Maven JDK.
2. Thêm `--add-modules jdk.incubator.vector` vào VM options nếu chạy ứng dụng trên classpath.
3. Thêm cùng module option vào cấu hình test runner nếu test chạy trong JVM riêng.
4. Nếu dùng named module, giữ `requires jdk.incubator.vector` trong module descriptor.
5. Xác nhận log khởi chạy cho biết đúng JDK và module.

Một cấu hình IDE chạy được không chứng minh CI hoặc production đã có cùng VM options. Hãy kiểm tra build và launch script được commit hoặc sinh ra trong pipeline.

## 7. Kiểm tra CPU features mà HotSpot nhận diện

Có ba lớp cần phân biệt:

1. **CPU vật lý/ảo có tính năng SIMD:** ví dụ AVX2, AVX-512 hoặc NEON.
2. **Hệ điều hành và JVM có thể sử dụng tính năng đó:** CPU feature có thể bị hypervisor, VM hoặc cấu hình hệ thống che đi.
3. **JIT thực sự sinh lệnh vector cho method cụ thể:** còn phụ thuộc shape, operation, profile, compilation và giới hạn implementation.

Trên HotSpot, xem thông tin CPU khi JVM khởi động:

```bash
java -Xlog:os+cpu=info -version
```

Log này giúp xem architecture và CPU features mà JVM nhận diện. Đây thường là bằng chứng hữu ích hơn việc chỉ đọc tên model CPU từ máy chủ.

Trên Linux, có thể kiểm tra thêm:

```bash
lscpu
grep -m1 -E 'flags|Features' /proc/cpuinfo
```

- Trên x86-64, tìm các flag như `avx2`, `avx512f` và những extension liên quan.
- Trên AArch64, xem feature `asimd` (Advanced SIMD, thường được gọi là NEON).
- Trong container/VM, kết quả có thể phản ánh CPU features mà guest được phép nhìn thấy, không nhất thiết toàn bộ khả năng của host.

Nếu CPU model hỗ trợ AVX-512 nhưng JVM không báo các feature tương ứng, không nên kết luận Vector API đang chạy AVX-512. Kiểm tra BIOS/OS, hypervisor, VM CPU model và JDK build trước khi điều tra code.

## 8. Phần cứng nào được tối ưu trong JDK 25?

Tài liệu Vector API của JDK 25 mô tả các nền tảng được tối ưu tốt nhất như sau:

| Nền tảng | Hỗ trợ được mô tả trong JDK 25 | Lưu ý |
|---|---|---|
| Intel/AMD x64 | AVX2 đến AVX-512 | AVX-512 mask-register operations và mask-accepting hardware instructions chưa được implementation hỗ trợ |
| ARM AArch64 | NEON | Đây là đường SIMD được hỗ trợ trong implementation |
| ARM SVE | API được thiết kế để có thể hỗ trợ SVE | JDK 25 chưa có implementation SVE tương ứng |
| Nền tảng không có SIMD phù hợp | Scalar fallback | API vẫn chạy đúng nhưng thường không có lợi ích tăng tốc vector |

Danh sách này mô tả trạng thái implementation JDK 25, không phải giới hạn vĩnh viễn của Vector API. CPU feature và backend có thể thay đổi ở các JDK release sau.

**Không suy ra “CPU có vector register” đồng nghĩa “mọi Vector API operation đều có lệnh SIMD tương ứng”.** Có thể một số operation hoặc mask pattern chưa được ánh xạ tối ưu trên một kiến trúc cụ thể.

## 9. Kiểm tra preferred species và vector shape

Vector API dùng `VectorSpecies` để biểu diễn kết hợp của element type và vector shape.

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public class SpeciesProbe {
    public static void main(String[] args) {
        VectorSpecies<Float> species = FloatVector.SPECIES_PREFERRED;

        System.out.println("species       = " + species);
        System.out.println("shape         = " + species.vectorShape());
        System.out.println("vector bits   = " + species.vectorBitSize());
        System.out.println("lane size     = " + species.elementSize());
        System.out.println("lane count    = " + species.length());
    }
}
```

Các giá trị cần hiểu:

- **Element size:** số bit của một lane, ví dụ `float` có 32 bit.
- **Vector bit size:** tổng số bit của vector.
- **Lane count:** số phần tử có thể xử lý trong một vector, bằng vector bit size chia element size.
- **Vector shape:** độ rộng vector mà species đại diện.

`FloatVector.SPECIES_PREFERRED` chọn species được nền tảng ưu tiên cho `float`. Theo API, preferred species được chọn theo shape lớn nhất thỏa các ràng buộc hỗ trợ lane types; các preferred species của nhiều element type có cùng underlying shape để thuận lợi cho reinterpretation.

Đây là cách viết tổng quát hơn so với hard-code `SPECIES_512`. Máy chạy chỉ có vector width 256 bit có thể không sinh vector instructions cho species 512 bit; implementation sẽ dùng scalar fallback cho operation không thể compile thành vector instructions.

## 10. Không hard-code shape nếu chưa có lý do đo đạc

Vector API cung cấp các species cố định như:

- `FloatVector.SPECIES_128`
- `FloatVector.SPECIES_256`
- `FloatVector.SPECIES_512`
- `FloatVector.SPECIES_MAX`
- `FloatVector.SPECIES_PREFERRED`

Các shape cố định hữu ích khi cần kiểm soát một thí nghiệm cụ thể. Trong code tổng quát, nên bắt đầu bằng `SPECIES_PREFERRED`.

Không giả định:

- Mọi CPU đều hỗ trợ vector 512 bit.
- Mọi vector shape đều hỗ trợ mọi lane type như nhau.
- `SPECIES_MAX` luôn là lựa chọn nhanh nhất.
- Lane count luôn là lũy thừa của hai.
- Một shape lớn hơn luôn nhanh hơn.

Tài liệu API khuyến nghị code không phụ thuộc shape cụ thể vì shape không được hỗ trợ có thể khiến operation chạy scalar fallback hoặc chậm hơn. Dùng `species.loopBound(length)` để tính phần tử xử lý theo vector loop; không tự tính bằng bit mask với giả định lane count là lũy thừa của hai.

## 11. Kiểm tra chức năng và xử lý phần tử cuối mảng

Một vòng lặp vector cần xử lý cả phần tử dư khi độ dài mảng không chia hết cho số lane. Có hai cách phổ biến:

- Dùng `VectorMask` để chỉ xử lý các lane nằm trong giới hạn.
- Dùng `loopBound` cho phần vector loop rồi xử lý phần dư bằng scalar loop.

Ví dụ phép cộng hai mảng `float`:

```java
import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public class VectorAdd {
    private static final VectorSpecies<Float> SPECIES =
        FloatVector.SPECIES_PREFERRED;

    static void add(float[] a, float[] b, float[] result) {
        if (a.length != b.length || a.length != result.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }

        int i = 0;
        int upperBound = SPECIES.loopBound(a.length);

        for (; i < upperBound; i += SPECIES.length()) {
            FloatVector va = FloatVector.fromArray(SPECIES, a, i);
            FloatVector vb = FloatVector.fromArray(SPECIES, b, i);
            FloatVector vr = va.add(vb);
            vr.intoArray(result, i);
        }

        for (; i < a.length; i++) {
            result[i] = a[i] + b[i];
        }
    }
}
```

Biên dịch và chạy theo cách classpath ở mục 4. Phần scalar loop cuối cùng bảo đảm mọi phần tử đều được xử lý mà không đọc vượt giới hạn mảng.

Nếu muốn dùng mask, có thể tạo mask bằng `SPECIES.indexInRange(offset, limit)` rồi truyền mask vào `fromArray` và `intoArray`. Với mảng rất lớn, vector loop không mask cộng scalar tail có thể tối ưu hơn việc tạo mask cho mọi vòng lặp; hãy đo trên workload thật.

## 12. Vì sao module đã bật nhưng chương trình không nhanh hơn?

Có module trong module graph mới chỉ chứng minh code có thể truy cập API. Nó không chứng minh hardware SIMD đã được sử dụng.

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Compile báo không tìm thấy package | Module chưa được resolve lúc compile | Thêm `--add-modules` hoặc `requires` |
| Runtime báo package/module không được đọc | Runtime chưa resolve module hoặc module descriptor thiếu dependency | Kiểm tra `--add-modules`, `requires` và đúng runtime |
| Chương trình chạy nhưng chậm tương đương scalar | CPU thiếu SIMD phù hợp, shape không được hỗ trợ hoặc workload quá nhỏ | Xem `-Xlog:os+cpu=info` và preferred species |
| Species là 512 bit nhưng CPU chỉ hỗ trợ 256 bit | Code chọn shape quá rộng | Dùng `SPECIES_PREFERRED` hoặc shape được hỗ trợ |
| Benchmark lúc nhanh lúc chậm | JIT chưa warm-up, CPU frequency, thermal throttling hoặc workload khác nhau | Dùng JMH, nhiều fork và cùng điều kiện |
| Vector loop nhanh nhưng tổng chương trình không nhanh | Chi phí memory bandwidth, copy, allocation hoặc phần scalar khác chi phối | Profile toàn workload |
| API hoạt động trên CPU không hỗ trợ SIMD | Scalar fallback đang thực thi | Đúng về chức năng, không đồng nghĩa có tăng tốc |

Vector API phụ thuộc vào khả năng dynamic compilation của runtime. Package có scalar implementation mặc định cho operation không thể biên dịch thành vector instruction. Đây là lý do API có thể chạy đúng trên phần cứng không có SIMD chuyên dụng.

## 13. Kiểm tra hiệu năng theo cách có thể tái lập

Trước khi giữ Vector API trong một hot path:

1. Viết baseline scalar đơn giản và kiểm tra kết quả đúng.
2. Viết phiên bản vector với preferred species và scalar tail.
3. Dùng cùng input, kích thước mảng và dữ liệu phân bố.
4. Warm up đủ để JIT biên dịch các method nóng.
5. Dùng JMH hoặc harness benchmark phù hợp thay vì đo một lần bằng đồng hồ trong `main`.
6. Chạy nhiều fork/iteration, giữ JDK, CPU, heap và runtime flags nhất quán.
7. So sánh throughput, latency, allocation và CPU utilization.
8. Thử kích thước dữ liệu nhỏ, vừa và lớn; SIMD overhead có thể không đáng với mảng nhỏ.
9. Kiểm tra sai số số học nếu phép toán thay đổi thứ tự cộng/nhân hoặc dùng reduction.
10. Đo lại trên từng kiến trúc CPU mục tiêu.

Không dùng kết quả trên laptop AVX-512 để khẳng định cùng code sẽ tăng tốc tương tự trên ARM NEON. Vector shape, instruction set, memory bandwidth và JIT backend khác nhau theo nền tảng.

## 14. Giữ incubator dependency trong phạm vi có thể thay thế

Vì Vector API chưa final, hãy thiết kế để có thể thay thế khi API thay đổi:

- Giữ phần code phụ thuộc `jdk.incubator.vector` trong package hoặc module riêng.
- Đưa interface nghiệp vụ ổn định ra ngoài, ví dụ `ArrayMath` hoặc `ImageKernel`.
- Cung cấp implementation scalar làm baseline và fallback.
- Không để `Vector`, `VectorSpecies` hoặc `VectorMask` xuất hiện trong public API nếu consumer không thực sự cần phụ thuộc incubator.
- Pin JDK/toolchain ở build và test; cập nhật dependency cùng JDK có chủ đích.
- Khi nâng JDK, compile lại và chạy correctness/performance tests thay vì giả định binary tương thích.
- Kiểm tra custom runtime image có chứa module `jdk.incubator.vector`.

Incubator không đồng nghĩa API đã lỗi thời. Tính năng vẫn đang được phát triển trong JDK 27, nhưng contract và khả năng tương thích chưa có mức bảo đảm như Java SE API đã final. Chỉ nên dùng khi lợi ích đo được đủ lớn để chấp nhận chi phí theo dõi thay đổi.

## 15. Bài thực hành: xác nhận module, CPU và species

### Bước 1 — Kiểm tra JDK và module

```bash
java -version
javac -version
java --list-modules | grep jdk.incubator.vector
java --describe-module jdk.incubator.vector
```

Trên Windows PowerShell, thay lệnh `grep` bằng `Select-String`.

### Bước 2 — Xem CPU features của HotSpot

```bash
java -Xlog:os+cpu=info -version
```

Ghi lại architecture và các feature JVM nhận diện. Nếu chạy trong container, ghi lại cả CPU model/feature được guest nhìn thấy.

### Bước 3 — Compile và chạy SpeciesProbe

```bash
javac --release 25 --add-modules jdk.incubator.vector -d out src/SpeciesProbe.java
java --add-modules jdk.incubator.vector -cp out SpeciesProbe
```

Ghi lại vector shape, vector bit size, element size và lane count.

### Bước 4 — Chạy phép cộng vector

Compile và chạy `VectorAdd`. Dùng các mảng có kích thước nhỏ hơn một vector, bằng đúng một vector, lớn hơn một vector một phần tử, không chia hết cho lane count và đủ lớn để phép đo hiệu năng có ý nghĩa.

So sánh từng phần tử với scalar reference, bao gồm phần tail.

### Bước 5 — Phân loại kết quả

| Quan sát | Kết luận |
|---|---|
| Module không có trong runtime | JDK/build hoặc custom image chưa cung cấp module |
| Module có nhưng compile lỗi | Chưa resolve module hoặc compiler đang dùng JDK khác |
| Module có, species hợp lý, kết quả đúng | Cấu hình và chức năng cơ bản đã hoạt động |
| CPU có SIMD, species phù hợp | Môi trường có điều kiện để JIT sinh SIMD |
| Không có SIMD phù hợp | Chương trình vẫn chạy bằng scalar implementation |
| Benchmark không cải thiện | Chưa có lý do giữ vector implementation; cần xem lại workload và JIT |

Không kết luận SIMD đã được sinh chỉ từ giá trị species. Muốn xác nhận hiệu năng, hãy benchmark; muốn xác nhận instruction cụ thể, cần kiểm tra mã máy JIT bằng công cụ phù hợp với JDK/platform và symbol/disassembler tương ứng.

## 16. Checklist cấu hình trước khi đưa vào pipeline

- [ ] Đã pin JDK release/vendor dùng để compile và run.
- [ ] Xác nhận module `jdk.incubator.vector` tồn tại bằng `--list-modules`.
- [ ] Hiểu Vector API là incubator module, không phải preview feature.
- [ ] Không bật `--enable-preview` chỉ để dùng Vector API.
- [ ] Ứng dụng classpath thêm `--add-modules jdk.incubator.vector` ở compile và runtime.
- [ ] Ứng dụng named module khai báo `requires jdk.incubator.vector`.
- [ ] Test runner, IDE, service launcher và CI nhận đúng module option.
- [ ] Custom runtime image có chứa module incubator.
- [ ] Dùng `-Xlog:os+cpu=info` để xem CPU features JVM nhận diện.
- [ ] Kiểm tra architecture và SIMD feature thực tế trong VM/container.
- [ ] Dùng `SPECIES_PREFERRED` cho code tổng quát; chỉ chọn shape cố định khi đã đo.
- [ ] Xử lý phần tử dư bằng mask hoặc scalar tail.
- [ ] Không coi species width là bằng chứng JIT đã sinh SIMD instructions.
- [ ] Có scalar baseline và correctness tests.
- [ ] Benchmark nhiều kích thước dữ liệu, warm-up, nhiều fork và nhiều kiến trúc.
- [ ] Giữ incubator dependency trong implementation có thể thay thế.
- [ ] Đọc lại tài liệu Vector API khi nâng JDK vì incubator API có thể thay đổi.

### Tài liệu tham khảo chính thức

1. [JEP 508 — Vector API (Tenth Incubator, JDK 25)](https://openjdk.org/jeps/508)
2. [Oracle Java SE 25 — Module jdk.incubator.vector](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/module-summary.html)
3. [Oracle Java SE 25 — Package jdk.incubator.vector, Performance Notes and Hardware Dependencies](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html)
4. [Oracle Java SE 25 — VectorSpecies](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorSpecies.html)
5. [Oracle Java SE 25 — VectorShape](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/jdk/incubator/vector/VectorShape.html)
6. [Oracle Java SE 25 — FloatVector](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.incubator.vector/jdk/incubator/vector/FloatVector.html)
7. [Oracle Java SE 25 — javac command and --add-modules](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
8. [Oracle Java SE 25 — java command and --add-modules](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
9. [JEP 529 — Vector API (Eleventh Incubator, JDK 26)](https://openjdk.org/jeps/529)
10. [JEP 537 — Vector API (Twelfth Incubator, JDK 27)](https://openjdk.org/jeps/537)
11. [Oracle Java SE 26 — Vector API (Eleventh Incubator)](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
12. [Oracle Java SE 27 — Vector API (Twelfth Incubator)](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
