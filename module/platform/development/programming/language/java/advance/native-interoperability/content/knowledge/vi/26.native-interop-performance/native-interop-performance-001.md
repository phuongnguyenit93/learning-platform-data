# Đo chi phí vượt ranh giới Java/C thay vì chỉ đo thời gian thuật toán C

## Mục tiêu

Khi Java gọi thư viện C qua Foreign Function & Memory API (FFM), JNI hoặc cơ chế tương tự, **thời gian chạy thuật toán bên C chỉ là một phần của chi phí thực tế**. Ứng dụng còn phải chuẩn bị tham số, chuyển đổi dữ liệu, có thể sao chép giữa heap và native memory, đi qua ranh giới Java/C, nhận kết quả và quản lý tài nguyên. Một thuật toán C rất nhanh vẫn có thể khiến ứng dụng chậm đi nếu phải gọi hàng triệu lần cho công việc quá nhỏ.

Bài này hướng dẫn xác định đúng phạm vi đo, thiết kế benchmark có đối chứng, dùng Java 22+ và C với JMH, đọc kết quả và quyết định khi nào cần batch, tái sử dụng buffer hoặc ở lại phía Java. Trọng tâm là **chi phí nhìn từ Java caller khi nhận kết quả có ích**, thay vì chỉ thời gian một hàm C chạy độc lập.

## 1. Bóc tách chi phí qua Java/C

Một lời gọi thực tế có thể trải qua:

1. **Java input:** kiểm tra điều kiện, định dạng dữ liệu, chuyển đối tượng/chuỗi/buffer thành kiểu native hiểu được.
2. **Interop setup:** load shared library, tìm symbol, tạo `MethodHandle`/JNI binding, cấp phát arena/buffer. Các bước này có thể diễn ra một lần hoặc lặp mỗi request.
3. **Marshaling và copy-in:** chuyển mảng heap sang off-heap, encode UTF-8, copy các trường của struct, pin/copy trong JNI tùy đường API.
4. **Cross-boundary:** FFM downcall hoặc JNI native method, truyền đối số theo ABI và phối hợp với JVM.
5. **Thuật toán C:** tính toán, đọc/ghi native memory và các thao tác trong thư viện C.
6. **Return và copy-out:** chuyển kết quả, copy dữ liệu về heap, giải mã, ánh xạ lỗi thành exception hoặc mã trả về.
7. **Cleanup:** giải phóng buffer, xử lý quyền sở hữu bộ nhớ, đóng arena hoặc release JNI resources.

Có thể hình dung:

`T_end_to_end ≈ T_prepare + T_copy_in + T_boundary + T_C + T_copy_out + T_cleanup`

Đây là **mô hình phân rã**, không phải phép cộng có thể luôn đo chính xác từng số hạng bằng cách trừ số liệu. Cache, JIT, GC, memory bandwidth và các tối ưu ở hai phía tương tác lẫn nhau. Nếu đối tượng trong production tái sử dụng buffer, chi phí tạo buffer không thuộc về mỗi call; nếu tạo mỗi request, benchmark đầu cuối phải tính chi phí đó.

**Điểm mấu chốt:** executable C đo nội bộ hàm C chỉ trả lời “thuật toán C chạy mất bao lâu?”. Nó không trả lời “Java gọi C và xử lý được một request mất bao lâu?”.

### Vì sao hàm C nhanh chưa chắc có lợi

Giả sử một call có phần overhead cố định `F`, còn xử lý mỗi phần tử tốn `W`:

- Gọi C `N` lần, mỗi call làm một phần tử: `N × (F + W)`.
- Gọi C một lần để xử lý `N` phần tử: `F + N × W + T_prepare_batch`.

Gộp call có thể làm giảm nhiều lần trả `F` nhưng có thể làm tăng copy, cấp phát và latency. Do đó cần đo các kích thước batch khác nhau và đường đi thực tế, không kết luận chỉ từ công thức.

## 2. Lập ma trận phép đo có đối chứng

| Benchmark | Thời gian bao gồm | Mục đích |
| --- | --- | --- |
| Java-only, phép cộng nhỏ | Phép tính trong JVM | Mốc tham chiếu cho thao tác rất nhỏ |
| C nhỏ gọi từ Java | FFM/JNI call + một phép tính C | Nhìn thấy đường call cho thao tác rất nhỏ |
| Java tính tổng mảng | Vòng lặp Java trên `int[]` | Phương án chỉ dùng Java |
| C tính tổng, buffer đã chuẩn bị | Downcall + vòng lặp C trên off-heap | Khi dữ liệu vốn nằm ở native memory |
| C tính tổng **kèm copy** | Copy Java heap → off-heap + downcall + C | Khi Java phải chuẩn bị payload cho C |
| Đầu cuối một request | Parse/validate + marshal + C + nhận kết quả + cleanup | Chỉ số quyết định ở tầng ứng dụng |

Không được gọi kịch bản “C đã có con trỏ” là “end-to-end” nếu request thật luôn phải chuyển `int[]` sang native memory. Ngược lại, nếu cả pipeline đã sử dụng native memory, cố tình copy lại trong benchmark cũng gây sai lệch.

FFM và JNI là **hai cách kết nối khác nhau**. Benchmark FFM không trực tiếp đại diện overhead JNI; nếu so JNI/FFM, cần triển khai cùng API C và workload, giữ nguyên kích thước dữ liệu, kết quả và môi trường.

## 3. Ví dụ thực hành: Java 22+ gọi C bằng FFM và đo với JMH

Ví dụ bao gồm mã C, một class JMH và cấu hình Maven. Java 22 là phiên bản đầu tiên FFM API trở thành API chính thức (JEP 454). Sử dụng JMH 1.37 để warmup, fork JVM và không để kết quả tính toán bị bỏ qua.

### 3.1. Cấu trúc dự án

~~~text
java-c-benchmark/
├── pom.xml
├── native/
│   └── tiny.c
└── src/
    └── main/
        └── java/
            └── example/
                └── BoundaryBench.java
~~~

### 3.2. Thư viện native: `native/tiny.c`

~~~c
#include <stdint.h>

#if defined(_WIN32)
    #define EXPORT __declspec(dllexport)
#else
    #define EXPORT __attribute__((visibility("default")))
#endif

EXPORT int32_t add_one(int32_t x) {
    return x + 1;
}

EXPORT int64_t sum_i32(const int32_t *data, int32_t count) {
    int64_t result = 0;
    for (int32_t i = 0; i < count; i++) {
        result += data[i];
    }
    return result;
}
~~~

Hàm `add_one` cố ý rất nhỏ để quan sát lời gọi native khi khối lượng tính toán thấp. Hàm `sum_i32` tăng lượng công việc theo `count`. Các kiểu có độ rộng rõ ràng giúp ánh xạ `int32_t` ↔ `JAVA_INT` và `int64_t` ↔ `JAVA_LONG`; `int32_t*` ↔ `ADDRESS`. Không tự ánh xạ C `long` sang Java `long` trên mọi ABI: trên Windows 64-bit, C `long` thường chỉ 32 bit.

Biên dịch thư viện với một lệnh phù hợp hệ điều hành (ở thư mục gốc dự án):

~~~bash
# Linux:
cc -O3 -fPIC -shared -o native/libtiny.so native/tiny.c

# macOS:
cc -O3 -fPIC -dynamiclib -o native/libtiny.dylib native/tiny.c

# Windows với MinGW-w64:
gcc -O3 -shared -o native/tiny.dll native/tiny.c
~~~

Chỉ chạy lệnh dành cho hệ điều hành đang dùng. Compiler C và JVM phải cùng kiến trúc/ABI; lưu lại version và flags của compiler. C nhận pointer và length hợp lệ; nếu ứng dụng native đọc vượt quá vùng bộ nhớ được cấp phát, kiểm tra biên của Java `MemorySegment` không thể bảo vệ truy cập C tùy ý.

### 3.3. Build JMH: `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>java-c-benchmark</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>22</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.openjdk.jmh</groupId>
            <artifactId>jmh-core</artifactId>
            <version>1.37</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.openjdk.jmh</groupId>
                            <artifactId>jmh-generator-annprocess</artifactId>
                            <version>1.37</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.5.3</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals><goal>shade</goal></goals>
                        <configuration>
                            <finalName>benchmarks</finalName>
                            <createDependencyReducedPom>false</createDependencyReducedPom>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>org.openjdk.jmh.Main</mainClass>
                                </transformer>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

JMH cần annotation processor để sinh benchmark harness. Build tạo executable jar `target/benchmarks.jar`, và JVM chạy fork sẽ nhận cờ native access do annotation trong class ở bước tiếp theo. Nếu dùng JDK cũ hơn 22 hoặc thư viện C sai ABI, ví dụ không chạy đúng.

### 3.4. Mã đo: `src/main/java/example/BoundaryBench.java`

~~~java
package example;

import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(value = 2, jvmArgsAppend = "--enable-native-access=ALL-UNNAMED")
public class BoundaryBench {
    @Param({"1", "64", "1024", "16384"})
    public int size;

    public int input = 41;

    private Arena arena;
    private MemorySegment offHeap;
    private int[] heap;
    private long expectedSum;
    private MethodHandle addOne;
    private MethodHandle sumI32;

    @Setup(Level.Trial)
    public void setUp() throws Throwable {
        arena = Arena.ofShared();
        heap = new int[size];
        offHeap = arena.allocate(ValueLayout.JAVA_INT, size);

        for (int i = 0; i < size; i++) {
            heap[i] = i & 255;
            offHeap.setAtIndex(ValueLayout.JAVA_INT, i, heap[i]);
            expectedSum += heap[i];
        }

        String os = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT);
        String library = os.contains("win") ? "tiny.dll"
                : os.contains("mac") ? "libtiny.dylib"
                : "libtiny.so";
        Path libraryPath = Path.of("native", library).toAbsolutePath();

        SymbolLookup symbols =
                SymbolLookup.libraryLookup(libraryPath, arena);
        Linker linker = Linker.nativeLinker();

        addOne = linker.downcallHandle(
                symbols.find("add_one").orElseThrow(),
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT,
                        ValueLayout.JAVA_INT));

        sumI32 = linker.downcallHandle(
                symbols.find("sum_i32").orElseThrow(),
                FunctionDescriptor.of(
                        ValueLayout.JAVA_LONG,
                        ValueLayout.ADDRESS,
                        ValueLayout.JAVA_INT));

        if ((int) addOne.invokeExact(41) != 42
                || (long) sumI32.invokeExact(offHeap, size) != expectedSum) {
            throw new IllegalStateException("Kết quả Java/C không khớp");
        }
    }

    @TearDown(Level.Trial)
    public void tearDown() {
        arena.close();
    }

    @Benchmark
    public int javaSmall() {
        return input + 1;
    }

    @Benchmark
    public int cSmall() throws Throwable {
        return (int) addOne.invokeExact(input);
    }

    @Benchmark
    public long javaSumHeap() {
        long result = 0;
        for (int value : heap) {
            result += value;
        }
        return result;
    }

    @Benchmark
    public long cSumPreloaded() throws Throwable {
        return (long) sumI32.invokeExact(offHeap, size);
    }

    @Benchmark
    public long cSumWithCopy() throws Throwable {
        for (int i = 0; i < size; i++) {
            offHeap.setAtIndex(ValueLayout.JAVA_INT, i, heap[i]);
        }
        return (long) sumI32.invokeExact(offHeap, size);
    }
}
~~~

**Giải thích thiết kế:**

- `@State(Scope.Thread)` tạo trạng thái riêng cho mỗi benchmark thread. `@Param` tạo nhiều workload sizes, không chỉ một điểm đo.
- `@Setup(Level.Trial)` tạo arena, cấp buffer, copy dữ liệu ban đầu, tải native library và tạo `MethodHandle` một lần. Các thao tác setup này **không nằm trong thời gian benchmark từng method**. Đây là giả định ứng dụng tái sử dụng handle/buffer; nếu thực tế setup mỗi request, cần thêm benchmark chứa setup đó trong vùng đo.
- Hai `invokeExact` khớp descriptor C. Truyền `MemorySegment` cho pointer trong FFM; hàm native trả `long`. Signature/ABI sai có thể làm JVM crash hoặc hỏng bộ nhớ.
- `javaSumHeap` dùng mảng trên Java heap, `cSumPreloaded` dùng buffer native đã được chuẩn bị, và `cSumWithCopy` đưa từng phần tử sang native memory **trong vùng đo**.
- Benchmark methods trả kết quả thật để JMH có thể tiêu thụ. Setup kiểm tra native và Java đồng ý về đầu ra trước khi bắt đầu đo. `@TearDown` đóng arena khi trial kết thúc.
- Trên JDK 22+, các API native bị hạn chế có thể cần `--enable-native-access=ALL-UNNAMED`. `@Fork` truyền cờ vào JVM con do JMH tạo ra.

Đây là ví dụ cho input-copy và scalar return. Nếu API thật trả mảng, chuỗi, struct hay cấp phát bộ nhớ bên C, cần thêm đường đo copy-out, decode và release đúng ownership. Không thể lấy `cSumPreloaded` đại diện cho những đường đi đó.

### 3.5. Chạy và lưu kết quả

Sau khi build thư viện ở bước 3.2, dùng Maven/JDK 22+ trong thư mục `java-c-benchmark`:

~~~bash
mvn -q -DskipTests package
java -jar target/benchmarks.jar "example.BoundaryBench" -prof gc -rf json -rff results.json
~~~

Kết quả JMH thường có `Benchmark`, `(size)`, `Mode`, `Cnt`, `Score`, `Error`, `Units`. Trong ví dụ này, `Mode=avgt` và `Units=ns/op` là thời gian trung bình **cho một lượt gọi phương thức benchmark**, không phải thời gian “một phép toán C” nếu method còn copy dữ liệu. `Score` phụ thuộc CPU, JVM, compiler và môi trường; vì vậy **không đưa ra bảng số nano giây cố định** khi chưa chạy trên máy mục tiêu.

Nếu không load được thư viện, kiểm tra tên `tiny.dll`/`libtiny.so`/`libtiny.dylib`, đường dẫn `native/` tương đối với working directory lúc JMH fork, symbol export, kiến trúc JVM và compiler C. Nếu không được phép tạo downcall, kiểm tra JVM con có nhận native-access flag.

## 4. Phân tích từng nhóm kết quả

### 4.1. Hàm nhỏ: `javaSmall` và `cSmall`

Khi phần tính toán chỉ là cộng 1, đường Java có thể được JIT inline mạnh, trong khi đường C vẫn phải qua native call. Kết quả có thể cho thấy gọi C cho phép toán quá nhỏ không hiệu quả. Tuy nhiên **không trừ thẳng hai `Score` rồi khẳng định đó là một hằng số overhead FFM phổ quát**: hai đường có khác biệt về JIT, data flow và cách đo.

Nếu mục tiêu chỉ là đánh giá mức overhead của đường gọi native, thử thêm một họ hàm C no-op hoặc trả về primitive với cùng kiểu đối số và không có copy; kiểm tra compiler/JIT không loại bỏ công việc và lặp dưới nhiều workload.

### 4.2. Có sẵn native memory: `cSumPreloaded`

Phương án này thích hợp khi ứng dụng đã nhận dữ liệu ở off-heap, từ vùng native buffer hoặc pipeline khác làm việc trên cùng vùng nhớ. Phép đo gồm downcall và xử lý C trên native buffer, nhưng **không gồm tạo dữ liệu hay copy từ `int[]`**.

Đặt cạnh `javaSumHeap` chỉ cho thấy hiệu năng của **hai pipeline với vị trí dữ liệu khác nhau**. Đừng dùng hiệu đó để kết luận tổng quát “C nhanh hơn Java” hoặc “interop có chi phí bằng X”.

### 4.3. Có chuyển dữ liệu: `cSumWithCopy`

Phép đo bao gồm copy các `int` vào off-heap bằng `setAtIndex` rồi gọi C. Đây là phép đo liên quan hơn khi dữ liệu nguồn nằm ở Java heap. So sánh với `cSumPreloaded` giúp quan sát tác động của việc copy, nhưng hiệu đo được không phải định lượng độc lập hoàn hảo của memcpy vì cache, CPU và JIT cũng thay đổi.

Với payload lớn, băng thông bộ nhớ và caching có thể chi phối phần lớn thời gian. Hãy đo cả chi phí trả kết quả lớn về Java, encode/decode string hoặc tạo struct nếu request thật làm những bước ấy.

### 4.4. Đường request thực tế quyết định lựa chọn

Ngoài microbenchmark, đo một workload bao gồm toàn bộ phần chuẩn bị, chuyển dữ liệu, gọi native, nhận kết quả, giải phóng và logic nghiệp vụ Java liên quan. Nếu service có nhiều request đồng thời, phải đo thêm concurrency, p50/p95/p99 latency và throughput. Nhanh hơn ở `ns/op` đơn luồng chưa chắc tốt hơn dưới tải khi native library có lock, contention, native memory pressure hoặc queueing.

JMH `-prof gc` đo một số chỉ tiêu cấp phát/GC của JVM; nó không tự đếm đầy đủ native `malloc`, mmap, RSS hay tài nguyên mà C giữ. Dùng profiler hoặc chỉ số OS/native memory thích hợp khi workload có cấp phát native đáng kể.

## 5. Biến số cần kiểm soát trong benchmark Java/C

| Nhóm | Những thứ cần thử hoặc giữ ổn định | Nếu bỏ qua |
| --- | --- | --- |
| Số lần call | Gọi từng phần tử và gộp batch 1/64/1024/... | Không thấy chi phí cố định mỗi lần qua boundary |
| Payload | Scalar, array, string UTF-8, struct, buffer lớn | Không thấy marshaling, encoding, copy |
| Vị trí dữ liệu | Heap, off-heap đã cấp phát, native-owned buffer | So sánh không tương đương |
| Setup | Load library/tra symbol một lần hay mỗi request | Bỏ sót/đếm thừa overhead |
| Kích thước | Nhỏ trong cache, lớn vượt cache, truy cập ngẫu nhiên | Bỏ qua cache và bandwidth |
| Chiều gọi | Java → C và C → Java callbacks/upcalls | Bỏ qua chi phí chiều ngược |
| Đồng thời | 1 thread, nhiều thread, native lock | Không thấy contention |
| Đường lỗi | Thành công, `errno`, exception mapping | Bỏ qua chi phí failure path |
| Cleanup | Buffer pooling, arena close, JNI release | Không thấy native allocation/lifecycle |
| Công cụ | JDK, GC, JMH, C compiler, tối ưu `-O3`, ABI | Kết quả không tái lập |

Với JNI, cần phân biệt `GetIntArrayElements`, `GetPrimitiveArrayCritical`, direct `ByteBuffer`, JNI string conversion và release/copy-back. Không được tự giả định mọi call đều zero-copy; một số API có thể copy hoặc pin tùy JVM và tình huống. Vùng critical JNI có hạn chế nghiêm ngặt với hoạt động thực hiện trong khi giữ con trỏ. Với FFM, cũng phải khai báo đúng `MemoryLayout`, alignment, phạm vi hiệu lực của `Arena` và ownership; truyền `MemorySegment` không đồng nghĩa toàn bộ request không có copy.

## 6. Những sai lầm phổ biến

**Đo một call bằng `System.nanoTime()`:** chi phí clock, warmup JIT, class loading, lịch OS và độ phân giải đồng hồ có thể lấn át hàm nhỏ. Dùng JMH warmup, nhiều iteration/fork và theo dõi sai số. `nanoTime()` vẫn có ích cho tác vụ dài hoặc instrumentation có phạm vi rõ.

**Không tiêu thụ kết quả:** compiler Java/C có thể loại bỏ tính toán không quan sát được hoặc tối ưu vòng lặp thành hằng số. Trả kết quả về JMH, dùng `Blackhole` khi phù hợp và kiểm tra correctness ngoài vùng đo; không rải `volatile` khắp nơi vì nó thay đổi workload.

**Chỉ đo C-only:** executable C không bao gồm JNI/FFM, heap/off-heap copy, decode và setup. Giữ số đo C-only nếu muốn tìm bottleneck bên C, nhưng đặt cạnh benchmark Java caller đúng đường đi.

**So hai thuật toán khác nhau:** một phía dùng SIMD hoặc batch, phía kia gọi một phần tử/lần, hay khác điều kiện lỗi/độ chính xác. Khi so overhead, giữ công việc tương đương. Khi so lựa chọn sản phẩm, ghi rõ các khác biệt và đảm bảo output đúng.

**Trộn cold start với steady-state:** tải thư viện, tạo handle và JIT warmup có thể đáng kể cho chương trình chạy ngắn nhưng không đại diện latency sau warmup. Đo riêng hai chế độ nếu cả hai quan trọng, dán nhãn rõ từng kết quả.

**Không kiểm soát môi trường:** đo trên máy bị tải nặng, CPU thay đổi mức xung, phiên bản JDK/compiler khác nhau. Ghi lại JDK vendor/version, CPU/OS, 32/64-bit, JVM flags, C compiler flags, JMH version và dữ liệu đầu vào. Chạy nhiều fork và xem độ nhiễu.

**Cho rằng batch luôn thắng:** batch giảm số call nhưng có thể tăng copy, bộ nhớ, độ trễ đuôi, thời gian giữ lock và thời gian chờ request; kết luận bằng throughput *và* p95/p99 dưới tải yêu cầu.

## 7. Tìm điểm hòa vốn và chọn kiến trúc

Với cùng kích thước workload `n`, ghi ít nhất:

1. `T_java(n)`: thực hiện trong Java với dữ liệu/trạng thái tương đương.
2. `T_native_prepared(n)`: native xử lý khi dữ liệu đã nằm trong memory phù hợp.
3. `T_native_full(n)`: Java chuẩn bị/copy, gọi native, xử lý output và cleanup theo đúng request thật.

Tìm ngưỡng mà `T_native_full(n)` thấp hơn `T_java(n)` **ổn định qua nhiều fork, lớn hơn nhiễu đo và vẫn đạt yêu cầu latency**. Nếu `T_native_prepared(n)` thấp nhưng `T_native_full(n)` cao, phần chuyển dữ liệu có thể là bottleneck. Lúc đó cần xem xét tái sử dụng native buffer, bớt chuyển đổi representation, gộp nhiều phần tử cho mỗi call, hoặc giữ cả một giai đoạn xử lý về cùng phía ranh giới. Nếu workload đã nằm native từ đầu, cần dùng ngữ cảnh đó thay vì ép toàn bộ request copy từ heap.

Đặc biệt, một ứng dụng hiệu năng cao có thể **không** nên dùng native cho thao tác scalar nhỏ dù vòng lặp C chạy nhanh hơn, bởi tổng chi phí tương tác và duy trì native code không bù được lợi ích.

## 8. Checklist kiểm chứng

- [ ] Phạm vi đo được mô tả rõ: C-only, FFM/JNI prepared, with copy, hay end-to-end?
- [ ] Ít nhất một benchmark thật sự bắt đầu từ Java caller và qua API interop production?
- [ ] Input/output tương đương, kết quả được tiêu thụ và correctness được kiểm tra?
- [ ] Copy-in, copy-out, encoding, allocation, cleanup có được tính khi request thật yêu cầu?
- [ ] Warmup/JIT, fork, compiler flags, CPU/JDK version và sai số được ghi?
- [ ] Đã đo nhiều kích thước payload, số native calls và batch sizes?
- [ ] Nếu có callback, string, struct, error handling hoặc native malloc, đã đo chúng?
- [ ] Đã xem latency, throughput và memory/GC dưới tải phù hợp?
- [ ] Quyết định tối ưu dựa trên đường đi dữ liệu Java → C → Java thật?

## Tài liệu tham khảo

- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM chính thức trong Java 22.
- [Java 24 — Foreign Function and Memory API](https://docs.oracle.com/en/java/javase/24/core/foreign-function-and-memory-api.html): downcalls, library lookup, memory segment và native access.
- [OpenJDK JMH](https://github.com/openjdk/jmh): nguyên tắc microbenchmark, harness, fork và warmup.
- [JMH samples](https://github.com/openjdk/jmh/tree/master/jmh-samples): ví dụ dùng JMH và những cạm bẫy tối ưu JIT.

**Ghi nhớ:** Chi phí phải được đo từ **điểm Java bắt đầu tương tác** đến khi **có kết quả Java sử dụng được**. Benchmark C-only là một số đo thành phần; phép đo Java/C đầu cuối mới phản ánh quyết định sử dụng native trong hệ thống.