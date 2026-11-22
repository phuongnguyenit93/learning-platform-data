# So sánh JNI, Foreign Function & Memory API và giao tiếp qua tiến trình

> **Ngữ cảnh:** Java Advance / Native Interoperability / Tổng quan tương tác. Bài này so sánh ba cách để ứng dụng Java sử dụng mã hoặc dịch vụ bên ngoài JVM, chú trọng ranh giới thực thi, khả năng kiểm soát bộ nhớ, độ tin cậy và tiêu chí lựa chọn.

## 1. Ba cách tiếp cận giải quyết ba kiểu ranh giới khác nhau

Giả sử chương trình Java cần gọi một hàm do thư viện C cung cấp, dùng codec viết bằng C++, hoặc chạy một chương trình tính toán sẵn có:

- **JNI (Java Native Interface):** Java khai báo phương thức `native`; một thư viện động chứa mã C/C++ triển khai phương thức đó và dùng giao diện JNI để tương tác với JVM, đối tượng Java, exception và callback.
- **FFM API (Foreign Function & Memory API):** Java sử dụng `java.lang.foreign` để tìm ký hiệu hàm C ABI, mô tả chữ ký hàm, tạo `MethodHandle` gọi mã native và quản lý vùng nhớ ngoài heap bằng `MemorySegment`/`Arena`. Với các hàm C ABI phù hợp, có thể bỏ lớp JNI glue viết bằng C.
- **Giao tiếp qua tiến trình (interprocess communication, IPC):** Java và chương trình trợ giúp chạy ở **hai tiến trình khác nhau**, trao đổi thông điệp qua stdin/stdout, pipe, Unix-domain socket, TCP, HTTP, gRPC hoặc cơ chế IPC khác. Chương trình trợ giúp có thể viết bằng Java, C, C++, Rust, Python, v.v.

```text
JNI:   [Java + JVM, PID A] -> [JNI wrapper C/C++] -> [native library, PID A]
FFM:   [Java + JVM, PID A] -> [Linker / MethodHandle] -> [C ABI library, PID A]
IPC:   [Java + JVM, PID A] -> [bytes + protocol] -> [helper process, PID B]
                                                         -> [native library, PID B]
```

**Điểm quyết định:** JNI và FFM gọi mã native **trong cùng không gian địa chỉ** của JVM; IPC tạo ranh giới tiến trình. Thay JNI bằng FFM không tự động cách ly JVM khỏi một thư viện native bị lỗi. Ngược lại, IPC không nhất thiết liên quan đến native code: Java có thể trao đổi với một tiến trình Java khác.

FFM được chuẩn hóa trong **JDK 22 (JEP 454)**. JNI có từ lâu và vẫn dùng được trên Java 17+. IPC với `ProcessBuilder` cũng dùng được trên Java 17+. Các ví dụ FFM bên dưới yêu cầu **JDK 22 trở lên**; ví dụ JNI/IPC chạy với Java 17+.

## 2. Bảng so sánh theo tiêu chí kỹ thuật

| Tiêu chí | JNI | FFM API | IPC qua tiến trình |
|---|---|---|---|
| Ranh giới | Java ↔ native **cùng tiến trình** | Java ↔ native **cùng tiến trình** | Hai tiến trình, có thể trên hai máy |
| Cổng Java | `native`, `System.loadLibrary`, `JNIEnv*` | `Linker`, `SymbolLookup`, `FunctionDescriptor`, `MethodHandle`; `MemorySegment`/`Arena` khi dùng bộ nhớ | `ProcessBuilder`, pipe, socket, HTTP/gRPC client |
| Cần mã C glue riêng? | Thường **có**: wrapper theo quy ước JNI | Thường **không** khi thư viện xuất C ABI phù hợp | Không cần trong JVM; helper tự xử lý giao thức và thư viện |
| API Java dùng lại | Java 17+ và các bản cũ | Ổn định từ Java 22 | Java 17+; giao thức độc lập ngôn ngữ |
| Tương tác object/GC | JNI cho truy cập object, array, class, exception, global/local refs | FFM ưu tiên dữ liệu ABI, layout và địa chỉ; chuyển Java object phức tạp cần chuyển đổi riêng | Serialize thành message, không dùng chung Java object/pointer |
| Vùng nhớ | Native pointer, `JNIEnv`, các API JNI pin/copy array; tự quản lý cẩn thận | `MemorySegment` có kiểm tra giới hạn/vòng đời khi truy cập qua Java; `Arena` kiểm soát sở hữu | Không chia sẻ address space theo mặc định; quản lý buffer ở mỗi bên |
| Chi phí mỗi lời gọi | JNI transition, mapping object/array và marshaling | Foreign downcall, ABI adaptation, cấp phát/chuyển dữ liệu nếu cần | Serialize/deserialize, IPC I/O, scheduling; khởi tạo process nếu gọi kiểu one-shot |
| Native crash/UB | Có thể làm **sập toàn JVM** | Vẫn có thể làm **sập toàn JVM** | Thường chỉ tiến trình helper sập; Java nhận EOF/exit/error và xử lý |
| Debug | Java stack + native debugger, symbol, core dump | Java stack + native debugger, layout/ABI | Log, trace, request ID và debug từng tiến trình |
| Phân phối | JVM + thư viện theo OS/CPU + wrapper JNI | JVM 22+ + thư viện theo OS/CPU và ABI tương thích | JVM + executable/container/helper + giao thức và lifecycle |
| Gọi ngược vào Java | JNI gọi phương thức Java qua `JNIEnv` | FFM có `upcallStub` để native gọi target Java qua method handle | Helper gửi message/callback theo protocol |
| Trường hợp nổi bật | Thư viện JNI sẵn có; cần thao tác sâu với Java object/JVM | C ABI rõ ràng; gọi hàm native/struct/pointer không muốn duy trì JNI glue | Cách ly mã dễ lỗi, công cụ CLI, service riêng, khác ngôn ngữ/quyền/máy |

Bảng thể hiện **đặc tính thiết kế**, không phải bảng xếp hạng tốc độ. Một JNI wrapper tối ưu có thể nhanh hơn hoặc chậm hơn FFM trong từng tải; một IPC worker sống lâu xử lý batch có thể hiệu quả hơn gọi native từng phần tử. Luôn đo với khối lượng dữ liệu và kiểu gọi thực tế.

## 3. JNI: Java gọi một phương thức được triển khai bằng C

JNI là giao diện nhị phân và bộ hàm để mã native làm việc với JVM. Khi Java gọi một phương thức `native`, JVM chuyển sang hàm native tương ứng; đối với C wrapper, tham số `JNIEnv*` cung cấp thao tác với Java object, string, array và exception. `JNIEnv*` gắn với thread gọi; **không giữ pointer này rồi dùng từ thread khác**. Các Java reference tạo qua JNI cũng có quy tắc vòng đời: local reference không được coi là global reference.

Ví dụ sau minh họa một JNI wrapper độc lập, thực thi phép cộng số nguyên nhỏ (giả sử không tràn `int`). Các lệnh build dùng **Linux, GCC, JDK đã cấu hình `JAVA_HOME`**.

**Tệp `JniAdd.java`:**

```java
public class JniAdd {
    static {
        System.loadLibrary("jniadd");
    }

    private static native int add(int a, int b);

    public static void main(String[] args) {
        System.out.println("JNI: " + add(20, 22));
    }
}
```

Tạo header bằng compiler của JDK:

```bash
javac -h . JniAdd.java
```

Lệnh này tạo `JniAdd.class` và `JniAdd.h`. Tên hàm native phải khớp header mà `javac -h` sinh ra.

**Tệp `JniAdd.c`:**

```c
#include <jni.h>
#include "JniAdd.h"

JNIEXPORT jint JNICALL Java_JniAdd_add(
        JNIEnv *env, jclass clazz, jint a, jint b) {
    (void) env;
    (void) clazz;
    return a + b;
}
```

Build shared library rồi chạy (Linux):

```bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libjniadd.so JniAdd.c

java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. JniAdd
```

**stdout (JDK 24+, đã cấp quyền native access):**

```text
JNI: 42
```

Trên Java 17, có thể chạy lệnh `java -Djava.library.path=. JniAdd`. Với macOS, thư viện tương ứng thường là `libjniadd.dylib` và lệnh biên dịch dùng `-dynamiclib`, header `include/darwin`; Windows cần DLL, toolchain và header `include/win32` phù hợp. Cả ba đều phải build thư viện cho đúng OS/CPU/JDK ABI. Lệnh `System.loadLibrary("jniadd")` dùng tên logic `jniadd`, không thêm tiền tố `lib` hay phần mở rộng.

**JNI hữu ích khi nào?** Khi thư viện đã cung cấp JNI wrapper, hoặc mã native cần lấy/gọi Java object, thao tác Java exception, callback, lớp và lifecycle sâu của JVM. Đổi lại, phải bảo trì glue C/C++, reference ownership, chuyển kiểu `jstring`/`jarray`, thread attachment và công cụ build native.

## 4. FFM API: gọi C ABI mà không viết JNI wrapper

FFM có hai phần hỗ trợ nhau:

1. **Foreign function:** `SymbolLookup` tìm địa chỉ hàm, `FunctionDescriptor` mô tả kiểu trả về và tham số, `Linker.nativeLinker()` tạo `MethodHandle` gọi hàm theo ABI của nền tảng. Một lời gọi Java → C là **downcall**; chiều C → Java có thể tạo **upcall stub**.
2. **Foreign memory:** `MemorySegment` đại diện một vùng nhớ liên tiếp; `MemoryLayout` mô tả kích thước/alignment/struct; `Arena` cấp phát và quyết định vòng đời vùng nhớ. `Arena.ofConfined()` giới hạn thao tác trong thread sở hữu và được đóng bằng `try-with-resources`; `Arena.ofShared()` hỗ trợ truy cập từ nhiều thread nhưng cần đồng bộ dữ liệu.

Dùng lại cùng phép cộng trong một thư viện C xuất hàm `add`. Ví dụ **Linux x86-64 / C ABI thông thường**; `C int` khớp với `ValueLayout.JAVA_INT` (32-bit) trên nền tảng này.

**Tệp `nativecalc.c`:**

```c
int add(int a, int b) {
    return a + b;
}
```

Build thư viện C:

```bash
gcc -fPIC -shared -o libnativecalc.so nativecalc.c
```

**Tệp `FfmAdd.java` (JDK 22+):**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public class FfmAdd {
    public static void main(String[] args) throws Throwable {
        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup symbols = SymbolLookup.libraryLookup(
                    Path.of("libnativecalc.so").toAbsolutePath(), arena);

            MethodHandle add = Linker.nativeLinker().downcallHandle(
                    symbols.find("add").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT, ValueLayout.JAVA_INT));

            int result = (int) add.invokeExact(20, 22);
            System.out.println("FFM: " + result);
        }
    }
}
```

Build và chạy:

```bash
javac FfmAdd.java
java --enable-native-access=ALL-UNNAMED FfmAdd
```

**stdout:**

```text
FFM: 42
```

`SymbolLookup.libraryLookup(Path, Arena)` lấy symbol trực tiếp từ thư viện và gắn vòng đời lookup với arena. `symbols.find("add").orElseThrow()` phù hợp cả JDK 22; phương thức tiện ích `findOrThrow` chỉ được bổ sung ở bản JDK sau. Khi `arena` đóng, các segment/lookup thuộc scope đó không còn được dùng; không giữ method handle hoặc pointer để gọi sau khi thư viện/vùng nhớ đã hết vòng đời.

**Điểm phải kiểm tra khi làm FFM thật:**

- C ABI phải khớp **chính xác**: số lượng/kiểu tham số, kiểu trả về, calling convention, alignment, layout struct/union và kích thước `long`/`size_t` theo OS/kiến trúc. Không suy diễn C `long` luôn là Java `long`; Windows 64-bit và Linux 64-bit có data model khác nhau.
- Con trỏ native là địa chỉ, không phải Java object. Cần làm rõ ai sở hữu bộ nhớ, phía nào cấp phát/giải phóng và native có giữ pointer sau khi Java đóng `Arena` không.
- Kiểm tra bounds/lifetime khi Java truy cập `MemorySegment` giúp tránh một lớp lỗi; **không bảo đảm** hàm C/C++ được gọi sẽ an toàn. Native code vẫn có thể ghi bậy, use-after-free hoặc crash JVM.
- Nếu thư viện chỉ xuất API C++ có name mangling, class method, template hay exception C++, thường cần một **C ABI facade** ổn định, rồi mới gọi bằng FFM; FFM không tự biến mọi API C++ thành ABI gọi được.

Với thư viện C có ABI đơn giản, FFM giúp giảm code JNI chuyên dụng và làm dữ liệu/pointer rõ ràng ở phía Java. Với thư viện dùng phức tạp nhiều Java object/callback và JNI ecosystem hiện hữu, việc chuyển sang FFM có thể không đáng chi phí.

## 5. IPC: Java trao đổi với tiến trình trợ giúp

IPC tách Java khỏi helper theo ranh giới của hệ điều hành. Helper có thể tải thư viện native mà JVM chính không cần tải. Cần thống nhất **protocol**: định dạng request/response (dòng text, JSON, Protobuf), encoding, framing, trạng thái lỗi, phiên bản, timeout, correlation ID và giới hạn kích thước.

Ví dụ Java 17+ bên dưới dùng **một request và một response qua pipe**. Helper viết bằng Java để demo dễ chạy; trong hệ thống native, bạn có thể thay helper bằng executable C/C++ có cùng giao thức.

**Tệp `ChildAdd.java`:**

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class ChildAdd {
    public static void main(String[] args) throws Exception {
        var input = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line = input.readLine();
        if (line == null) {
            throw new IllegalArgumentException("Missing request");
        }

        String[] fields = line.trim().split("\\s+");
        if (fields.length != 2) {
            throw new IllegalArgumentException("Expected: a b");
        }

        int a = Integer.parseInt(fields[0]);
        int b = Integer.parseInt(fields[1]);
        System.out.println(Math.addExact(a, b));
    }
}
```

**Tệp `ParentAdd.java`:**

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class ParentAdd {
    public static void main(String[] args) throws Exception {
        String executable = System.getProperty("os.name").startsWith("Windows")
                ? "java.exe" : "java";
        String javaBin = Path.of(
                System.getProperty("java.home"), "bin", executable).toString();

        Process child = new ProcessBuilder(
                javaBin, "-cp", System.getProperty("java.class.path"), "ChildAdd")
                .redirectError(ProcessBuilder.Redirect.INHERIT)
                .start();

        try (var writer = new BufferedWriter(
                new OutputStreamWriter(
                        child.getOutputStream(), StandardCharsets.UTF_8))) {
            writer.write("20 22\n");
        }

        String reply;
        try (var reader = new BufferedReader(
                new InputStreamReader(
                        child.getInputStream(), StandardCharsets.UTF_8))) {
            reply = reader.readLine();
        }

        int exit = child.waitFor();
        if (exit != 0 || reply == null) {
            throw new IllegalStateException(
                    "Helper failed: exit=" + exit + ", reply=" + reply);
        }
        System.out.println("IPC: " + Integer.parseInt(reply));
    }
}
```

Chạy trên Windows, Linux hoặc macOS với JDK 17+:

```bash
javac ChildAdd.java ParentAdd.java
java ParentAdd
```

**stdout:**

```text
IPC: 42
```

`ParentAdd` gửi request qua stdin của child, child trả response qua stdout, còn stderr được chuyển thẳng về console để tránh trộn log với dữ liệu máy đọc. `waitFor()` kiểm tra exit code. Đây là **ví dụ nhỏ, đồng bộ, một request**: `readLine()` vẫn có thể treo mãi nếu helper không trả dòng. Với môi trường thật, cần cơ chế timeout bao trùm I/O, tiêu thụ cả stdout/stderr (hoặc chuyển stderr về log), giới hạn message, đóng stream, xử lý hủy tiến trình và restart phù hợp.

Với helper chạy lâu, nên duy trì connection/worker pool thay vì khởi động process cho mọi lời gọi. Nếu cần trao đổi nhiều request hoặc nhiều client, chọn framed protocol, định danh request và kiểm soát backpressure; socket hoặc RPC thường rõ ràng hơn một pipe đơn giản.

## 6. Độ tin cậy, lỗi và khả năng cách ly

**JNI và FFM:** Cả hai đều đưa native library vào cùng process JVM. Một lỗi segmentation fault, ghi sai vùng nhớ, stack corruption hoặc undefined behavior ở C/C++ có thể khiến toàn JVM kết thúc. Java `try/catch` không phải lá chắn đối với crash mức native. Lỗi logic thông thường vẫn có thể được chuyển thành kết quả lỗi: JNI dùng API báo Java exception hoặc trả mã lỗi; FFM thường đọc return code/`errno`/struct kết quả theo hợp đồng C ABI.

**IPC:** Tiến trình helper có address space và trạng thái riêng. Nếu helper chết vì native crash, Java thường thấy pipe đóng, EOF, exit code khác 0 hoặc connection reset; Java có thể log, retry khi an toàn, restart helper hoặc trả lỗi cho request. Tuy vậy, IPC **không tự động** bảo đảm timeout, recovery, exactly-once, bảo mật hay khả năng phục hồi: thiết kế protocol và supervisor mới cung cấp các thuộc tính đó.

Cần phân biệt:

- **Crash isolation:** helper lỗi không trực tiếp phá hỏng heap JVM của tiến trình cha; các tiến trình vẫn chia sẻ tài nguyên máy (CPU, RAM, file, mạng) nên phải giới hạn tài nguyên.
- **Fault handling:** native call cùng tiến trình cần mã native kiểm tra pointer/return code; IPC cần quản lý timeout, connection, exit code và lifecycle.
- **Retry:** một lời gọi IPC timeout có thể đã thực thi ở helper; chỉ retry mù khi thao tác thật sự idempotent hoặc có request ID/deduplication.
- **Trust boundary:** helper chạy cùng user vẫn có thể đọc file/secret cùng quyền; muốn cô lập mạnh cần giảm OS privileges, container/sandbox thích hợp, filesystem/network policy và kiểm soát đầu vào.

## 7. Hiệu năng: nhìn toàn bộ đường đi của dữ liệu

Một mô hình định tính:

```text
JNI call ≈ transition JNI + chuyển đổi dữ liệu + native work
FFM call ≈ downcall/ABI adaptation + chuyển đổi dữ liệu + native work
IPC call ≈ encode + truyền dữ liệu + schedule + decode + helper work
           (+ process startup nếu tạo helper mới cho mỗi request)
```

- Với hàng triệu phép tính rất nhỏ, chi phí crossing boundary lặp lại có thể lấn át công việc; thử **batch nhiều phần tử** vào một lời gọi native/IPC.
- Với tác vụ nặng như xử lý video, ML inference, nén tập tin, chi phí IPC có thể nhỏ so với tính toán; isolation và vận hành có thể quan trọng hơn vài microsecond.
- Với array/struct lớn, đo số byte copy, pin, alignment, phân bổ bộ nhớ, serialization và mức độ tái sử dụng buffer. `MemorySegment` không đồng nghĩa với “zero copy” từ đầu tới cuối.
- Phân biệt **throughput**, **p50/p95/p99 latency**, CPU, bộ nhớ native, thời gian khởi động và mức ổn định khi lỗi. Benchmark với warm-up JIT, dữ liệu thật, cùng môi trường/hardware, không lấy một microbenchmark làm quy tắc tổng quát.

Không có bảo đảm chung “FFM luôn nhanh hơn JNI” hoặc “JNI luôn nhanh hơn IPC”: workload, thư viện, cách truyền dữ liệu và triển khai quyết định kết quả.

## 8. Chọn công nghệ theo yêu cầu

| Tình huống | Lựa chọn ban đầu hợp lý | Vì sao |
|---|---|---|
| Đã có JNI binding ổn định cho thư viện đang dùng | **JNI** | Tận dụng binding, callback và mã đã được kiểm thử; không cần chuyển chỉ vì có FFM |
| Cần gọi nhiều hàm C ABI đơn giản, chạy JDK 22+, không muốn tự viết JNI glue | **FFM** | Link symbol trực tiếp, mô tả kiểu C ABI và quản lý vùng nhớ phía Java |
| Cần tương tác sâu với object JVM từ C/C++ | **JNI** | `JNIEnv`, refs và callback Java là phần cốt lõi của JNI |
| Thư viện native không tin cậy hoặc dễ crash (codec/plugin bên thứ ba) | **IPC helper** | Giới hạn hậu quả crash và có thể khởi động lại helper |
| Công cụ CLI đã tồn tại, giao thức đầu vào/ra đơn giản | **IPC qua ProcessBuilder** | Tái sử dụng executable mà không buộc viết binding native trong JVM |
| Thành phần cần nâng cấp độc lập, nhiều client, có khả năng chạy từ xa | **IPC/RPC service** | Có biên giới triển khai, version và vận hành riêng |
| Cần vừa gọi C ABI vừa cô lập JVM | **FFM hoặc JNI ở helper process + IPC về Java chính** | Hai tiêu chí độc lập: cách helper gọi native và cách Java giao tiếp với helper |

**Quy trình quyết định nhanh:** (1) Có bắt buộc chạy **cùng tiến trình** không? Nếu yêu cầu cách ly crash/quyền/triển khai, ưu tiên IPC. (2) Nếu cùng tiến trình, có JNI wrapper hoặc cần thao tác Java object/JVM sâu không? Cân nhắc JNI. (3) Nếu chủ yếu gọi C ABI, có JDK 22+ và muốn giảm glue C, thử FFM. (4) Đo hiệu năng và đánh giá vận hành trước khi chốt.

Các cách có thể **kết hợp**: Java chính nói chuyện qua IPC với một worker C++; worker dùng C ABI hoặc JNI/FFM trong JVM riêng (nếu worker cũng là Java). Đây thường là giải pháp khi vừa cần native functionality vừa cần fault isolation.

## 9. An toàn, tương thích và triển khai

**Tính toàn vẹn JVM và native access.** Từ **JDK 24**, JEP 472 chuẩn bị hạn chế JNI và FFM nhất quán: nhiều thao tác native bị coi là restricted và mặc định phát cảnh báo khi chưa cấp quyền. Khi code nằm trên classpath, chạy với `--enable-native-access=ALL-UNNAMED`; ứng dụng module hóa nên cấp chính xác `--enable-native-access=ten.module`. Trong môi trường production, thử `--illegal-native-access=deny` (JDK 24+) để phát hiện sớm phần code thiếu quyền. Đây là cơ chế kiểm soát quyền *sử dụng native access* của module; nó không làm cho C/C++ trở thành memory-safe. Trên JDK 22–23, FFM restricted operations cần native-access enablement; trên JDK 17, chưa có FFM API ổn định.

**ABI và phân phối.** Native artifact theo hệ điều hành/kiến trúc: Linux `.so`, macOS `.dylib`, Windows `.dll`. Đúng định dạng file vẫn chưa đủ: cần matching architecture, calling convention, compiler/runtime dependency, symbol export, layout và thư viện phụ thuộc. C++ ABI không đồng nhất giữa các compiler; C facade thường ổn định hơn. Docker image, artifact classifier hay installer nên đóng gói đúng binary. IPC cũng cần phân phối đúng executable và version protocol, dù JVM chính không load binary vào address space của nó.

**Sở hữu bộ nhớ.** Với JNI, cặp acquire/release array/string và local/global references phải cân đối; đừng dùng `JNIEnv*` của thread khác. Với FFM, chọn confined/shared arena theo thread policy; không để pointer thoát scope, không cho native giữ pointer sau khi vùng nhớ bị giải phóng. Với IPC, không gửi pointer/address thô như dữ liệu có thể dùng lại ở tiến trình khác: truyền value, file descriptor/handle được chia sẻ theo protocol OS, hoặc shared memory có quyền và đồng bộ rõ ràng.

**Bảo mật.** Validate dữ liệu từ Java trước khi truyền xuống native hoặc gửi helper; giới hạn độ dài, encoding, path và tài nguyên. Với `ProcessBuilder`, truyền command/arguments thành từng phần tử thay vì ghép chuỗi shell tùy tiện; chỉ dùng shell khi thật sự cần và đã kiểm soát quoting. Giữ stdout sạch cho protocol và stderr riêng cho log; kiểm soát quyền thực thi của thư viện/executable, địa chỉ kết nối IPC và secret.

## 10. Lỗi thường gặp khi so sánh hoặc triển khai

1. **“FFM là JNI mới, thay thế hoàn toàn JNI.”** Sai: FFM ổn định từ JDK 22 và rất hợp C ABI/memory, nhưng JNI vẫn phù hợp với API làm việc sâu với JVM và hệ sinh thái binding hiện có.
2. **“FFM tránh được crash native.”** Sai: mã native vẫn chạy trong JVM process và có thể làm hỏng bộ nhớ.
3. **“IPC luôn chậm nên không dùng cho tính toán.”** Sai nếu native work lớn, batch tốt hoặc yêu cầu cách ly cao. Hãy đo p95/p99 và end-to-end cost.
4. **“Trả về thành công là đã xử lý đúng mọi lỗi.”** Sai: JNI cần xử lý pending Java exception, FFM cần kiểm tra return code/errno, IPC cần kiểm tra exit code, EOF, protocol error và timeout.
5. **“`int`/`long`/struct có layout giống nhau trên mọi nền tảng.”** Sai: kiểm tra C ABI, alignment và field offsets cụ thể; đặc biệt `long` và `size_t`.
6. **“Pointer native có thể truyền qua IPC như địa chỉ dùng chung.”** Sai: mỗi process có không gian địa chỉ riêng; phải dùng serialization hoặc cơ chế shared memory/handle được hệ điều hành hỗ trợ.
7. **“Đóng `Arena` là xong mọi trách nhiệm.”** Sai nếu native vẫn giữ pointer, dùng buffer sau khi đóng, hoặc không tuân thủ hợp đồng ownership.
8. **“`readLine()` rồi `waitFor()` đã đủ chống treo.”** Sai: cần timeout áp dụng cả giai đoạn đọc/ghi, xử lý bounded buffer và tiến trình không hợp tác.
9. **“Chuyển JNI sang FFM sẽ tự động tăng tốc.”** Không có bảo đảm; so sánh phải giữ nguyên workload, native implementation và chiến lược marshaling.

## 11. Bài thực hành để tự kiểm chứng

- Chạy ba ví dụ với `20` và `22`; cả ba trả về `42`. Sau đó thay bằng số âm và số biên, làm rõ overflow là trách nhiệm của native implementation/protocol.
- Trong ví dụ FFM, thử đổi sai `FunctionDescriptor` (chỉ thử ở môi trường thực hành) để hiểu **ABI mismatch có thể gây lỗi nghiêm trọng**; không thực hiện trên JVM đang chứa dữ liệu quan trọng.
- Với IPC, cho helper tự thoát với exit code khác 0 hoặc không in stdout; xem parent xử lý EOF/exit status. Thêm timeout thực sự bao phủ I/O và thử helper bị treo.
- Với JNI/FFM, kiểm tra cách load thư viện sai OS/CPU hoặc symbol không tồn tại sẽ tạo lỗi nào. Với IPC, kiểm tra executable không tồn tại hoặc protocol version không khớp.
- Nếu đo performance, so sánh **một triệu add đơn lẻ** với **một lời gọi batch một triệu phần tử**, cùng dữ liệu và công việc, để thấy crossing boundary và marshaling có thể là bottleneck.

**Kết luận thực hành:** Chọn **JNI** khi cần binding sâu vào JVM hoặc giữ tích hợp JNI hiện có; chọn **FFM** khi muốn dùng C ABI và native memory trực tiếp trên JDK 22+; chọn **IPC** khi ưu tiên cô lập, triển khai độc lập hoặc dùng executable/service riêng. Một hệ thống có thể kết hợp IPC với JNI/FFM ở phía worker.

## Tài liệu tham khảo chính thức

- [JEP 454 — Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454)
- [Java SE 25: `java.lang.foreign` package](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Java SE 25: `SymbolLookup`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Java SE 25: `Arena` và thread confinement](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html)
- [JEP 472 — Prepare to Restrict the Use of JNI (JDK 24)](https://openjdk.org/jeps/472)
- [Java SE 25: `ProcessBuilder`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ProcessBuilder.html)
- [Java Native Interface Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/index.html)
