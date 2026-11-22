# Quan hệ giữa JVM, mã Java, thư viện C/C++ và bộ nhớ ngoài heap

## 1. Bức tranh tổng thể

Một chương trình Java chạy trên **JVM (Java Virtual Machine)**, nhưng JVM bản thân là phần mềm native (chủ yếu viết bằng C/C++) chạy trong tiến trình của hệ điều hành. Vì vậy, **mã Java, JVM và thư viện C/C++ có thể cùng tồn tại trong một tiến trình và cùng sử dụng bộ nhớ của tiến trình đó**.

Có ba câu hỏi cần tách bạch:

1. **Ai thực thi?** Bytecode Java được JVM thông dịch hoặc biên dịch JIT thành mã máy; mã C/C++ đã được biên dịch thành mã máy cho hệ điều hành và kiến trúc CPU cụ thể.
2. **Giao tiếp bằng cách nào?** Java có thể gọi hàm native qua **JNI** hoặc **Foreign Function & Memory API (FFM)**. Các API Java như NIO cũng có thể nhờ JVM thực hiện I/O bằng mã native.
3. **Dữ liệu nằm ở đâu, ai giải phóng?** Đối tượng Java thường nằm trên **Java heap**; vùng nhớ cấp phát bằng `malloc`, direct buffer hoặc native `MemorySegment` có thể nằm **ngoài Java heap (off-heap)**. Cơ chế quản lý vòng đời khác nhau theo nguồn cấp phát.

Sơ đồ khái niệm:

~~~text
Một tiến trình của hệ điều hành
|
+-- JVM runtime (mã native)
|   +-- Nạp class, xác minh bytecode, thông dịch/JIT, GC
|   +-- Java heap: các đối tượng Java thông thường
|   +-- Bộ nhớ phục vụ JVM: metaspace, code cache, thread stack, ...
|   +-- Mã Java đang chạy
|        +-- API Java thuần túy
|        +-- Java NIO / direct ByteBuffer
|        +-- JNI / FFM ----> hàm native trong thư viện C/C++
|
+-- Thư viện native được nạp vào cùng tiến trình (.dll/.so/.dylib)
|   +-- Mã máy và dữ liệu của thư viện
|   +-- Vùng nhớ do malloc/new/mmap hoặc bộ cấp phát khác quản lý
|
+-- Không gian địa chỉ ảo chung của tiến trình (do OS quản lý)
~~~

Các khối trong sơ đồ biểu diễn **vai trò quản lý**, không phải những phân vùng bộ nhớ vật lý tách biệt tuyệt đối. Ví dụ, cả JVM và thư viện native đều có thể yêu cầu bộ nhớ từ hệ điều hành. **Gọi JNI/FFM thông thường không tạo tiến trình mới**: đây là lời gọi qua ranh giới ngôn ngữ và ABI trong cùng tiến trình. Một lỗi truy cập con trỏ trong thư viện native có thể làm sập toàn bộ JVM.

## 2. JVM là cầu nối giữa Java và hệ điều hành

Luồng thực thi thường là:

~~~text
NativeBridge.java
    -- javac --> bytecode (.class)
    -- JVM nạp/xác minh --> Interpreter hoặc JIT
    -- gọi native method / foreign function -->
    thư viện C/C++ đã biên dịch (mã máy)
    -- trả kết quả --> Java
~~~

- **Java compiler (`javac`)** tạo bytecode có tính di động theo đặc tả JVM.
- **JVM** chịu trách nhiệm quản lý đối tượng, class loading, GC, thread Java, kiểm tra và thực thi bytecode; JIT có thể biên dịch những đoạn mã nóng thành mã máy.
- **Native library** được biên dịch riêng theo nền tảng: Linux thường là `.so`, macOS là `.dylib`, Windows là `.dll`. Thư viện có thể phụ thuộc vào C runtime, các thư viện hệ thống hoặc thư viện native khác.
- **ABI (Application Binary Interface)** quy định cách truyền tham số, trả giá trị, bố trí dữ liệu, quy ước gọi hàm và cách tên hàm xuất hiện ở mức mã máy. Chọn đúng ABI và đúng kiến trúc CPU là điều kiện để gọi native an toàn.

Thư viện C++ có name mangling và nhiều đặc tính ABI phụ thuộc trình biên dịch. Khi cần giao tiếp ổn định từ Java, nên thiết kế một **lớp hàm C ABI** (chẳng hạn các hàm `extern "C"`) bọc phần triển khai C++; không coi tên phương thức C++ hay bố cục đối tượng C++ là giao diện liên thông ổn định.

## 3. Java heap và off-heap khác nhau như thế nào?

| Vùng/kiểu cấp phát | Dữ liệu tiêu biểu | Vòng đời và trách nhiệm |
| --- | --- | --- |
| **Java heap** | Object, array, String, phần vỏ đối tượng `ByteBuffer` | GC theo dõi khả năng truy cập của các đối tượng; giới hạn chính thường liên quan `-Xmx`. |
| **Direct buffer** | Dữ liệu byte của `ByteBuffer.allocateDirect(...)` | Thường dùng bộ nhớ native; đối tượng đệm vẫn là Java object; việc thu hồi phần native thường gắn với reachability/cleaner, **không bảo đảm giải phóng ngay tại cuối scope**. |
| **Native memory do C/C++ cấp phát** | `malloc`/`free`, `new`/`delete`, vùng từ thư viện native | Bên sở hữu phải giải phóng theo đúng API và đúng thời điểm; GC không tự biết cách giải phóng mọi con trỏ C/C++. |
| **FFM native segment** (JDK 22+) | `MemorySegment` do `Arena` cấp phát | `Arena` quy định vòng đời; arena có thể đóng rõ ràng và làm segment không còn hợp lệ. |
| **Bộ nhớ phục vụ JVM** | Metaspace, JIT code cache, ngăn xếp thread, cấu trúc GC | JVM/quy trình runtime quản lý; không đồng nhất với heap Java. |
| **Memory-mapped file** | Vùng file ánh xạ qua OS | Có thể nằm ngoài Java heap; trang nhớ và đồng bộ dữ liệu phụ thuộc cơ chế ánh xạ và OS. |

**Off-heap** chỉ có nghĩa vùng lưu dữ liệu nằm ngoài Java heap. Nó **không có nghĩa** “ngoài tiến trình”, “không tiêu tốn RAM”, “luôn nhanh hơn”, “không bao giờ được GC tác động gián tiếp” hoặc “không có giới hạn”. Địa chỉ ảo, bộ nhớ vật lý, dữ liệu ánh xạ file và số liệu RSS là các khái niệm khác nhau.

Đặc biệt:

- `-Xmx` giới hạn tối đa **Java heap**, không phải toàn bộ bộ nhớ tiến trình. Tiến trình có thể tiêu thụ nhiều hơn `-Xmx` do thread stack, metaspace, JIT, direct buffer và thư viện native.
- `-XX:MaxDirectMemorySize` là giới hạn liên quan đến direct-buffer allocation của JVM (phụ thuộc JVM/phiên bản); nó **không phải trần cho mọi lệnh `malloc` từ C/C++**.
- Một Java object giữ tham chiếu tới địa chỉ native chỉ giúp giữ *wrapper* sống. Nếu thư viện native đã `free` vùng đó, tham chiếu không làm vùng nhớ hợp lệ trở lại; ngược lại, quên `free` có thể gây rò rỉ native memory dù Java heap còn ít.

## 4. Ví dụ Java 17+: direct `ByteBuffer` không cần tự viết JNI

Tạo file `DirectMemoryDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class DirectMemoryDemo {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocateDirect(8)
                .order(ByteOrder.nativeOrder());

        buffer.putInt(40);
        buffer.putInt(2);
        buffer.flip();

        int result = buffer.getInt() + buffer.getInt();
        System.out.println("direct=" + buffer.isDirect());
        System.out.println("sum=" + result);
        System.out.println("remaining=" + buffer.remaining());
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac DirectMemoryDemo.java
java DirectMemoryDemo
~~~

Stdout:

~~~text
direct=true
sum=42
remaining=0
~~~

Giải thích:

1. `allocateDirect(8)` tạo buffer có dung lượng 8 byte để chứa hai số `int` (mỗi số 4 byte); `isDirect()` báo đây là direct buffer.
2. `order(ByteOrder.nativeOrder())` chọn thứ tự byte theo kiến trúc máy. Khi trao đổi dữ liệu thực tế, **hai phía phải thống nhất byte order** thay vì mặc định “native” là giống nhau ở mọi máy.
3. `putInt` ghi dữ liệu, làm `position` tiến; `flip` chuyển buffer từ chế độ ghi sang đọc bằng cách đặt lại `position` và `limit` thích hợp.
4. Hai lệnh `getInt` đọc lần lượt hai giá trị; còn 0 byte có thể đọc trong vùng giới hạn hiện tại.
5. `clear()` (nếu được gọi) chỉ đặt lại con trỏ logic của buffer; **không xóa dữ liệu và không giải phóng phần native**. Cũng không nên giữ direct buffer lớn vô thời hạn chỉ vì đang dùng ít byte.

**Khi nào dùng?** Direct buffer hữu ích cho một số đường I/O native, file/channel hoặc thư viện hỗ trợ direct buffer. Nó có chi phí cấp phát/giải phóng cao hơn heap buffer; hãy đo đạc workload trước khi kết luận nhanh hơn. Nếu native code nhận địa chỉ từ direct buffer, phải bảo đảm vùng nhớ còn sống suốt thời gian native sử dụng.

## 5. JNI: Java gọi hàm C trong cùng tiến trình

**JNI (Java Native Interface)** là giao diện lâu đời của JVM cho phép native code tương tác với Java method, object và array. Dưới đây là ví dụ độc lập trên JDK 17+, không cần framework.

Tạo `NativeBridge.java`:

~~~java
public class NativeBridge {
    static {
        System.loadLibrary("arithnative");
    }

    private static native int add(int left, int right);

    public static void main(String[] args) {
        System.out.println("2 + 3 = " + add(2, 3));
    }
}
~~~

Tạo `nativebridge.c`:

~~~c
#include <jni.h>
#include "NativeBridge.h"

JNIEXPORT jint JNICALL Java_NativeBridge_add(
        JNIEnv *env, jclass clazz, jint left, jint right) {
    (void) env;
    (void) clazz;
    return left + right;
}
~~~

**Các bước trên Linux** (đã cài JDK 17+ và trình biên dịch C; `JAVA_HOME` trỏ tới thư mục JDK):

~~~bash
javac -h . NativeBridge.java
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libarithnative.so nativebridge.c
java -Djava.library.path=. NativeBridge
~~~

Stdout:

~~~text
2 + 3 = 5
~~~

Trên macOS, dùng file `libarithnative.dylib`, thư mục header `$JAVA_HOME/include/darwin` và tùy chọn liên kết `-dynamiclib`; trên Windows, tạo `arithnative.dll` bằng công cụ C phù hợp và thêm `%JAVA_HOME%\include`, `%JAVA_HOME%\include\win32` vào include path. Tên file cụ thể do quy tắc `System.mapLibraryName(...)` của nền tảng quyết định.

**Cơ chế của ví dụ**:

1. `javac -h .` vừa biên dịch Java vừa sinh file header `NativeBridge.h` với khai báo JNI tương ứng.
2. JVM chạy `System.loadLibrary("arithnative")` và tìm thư viện native theo cơ chế nạp thư viện, trong đó có đường dẫn cấu hình `java.library.path`.
3. Java gọi `add(2, 3)`, JVM chuyển qua entry point JNI `Java_NativeBridge_add`; `jint` là kiểu số nguyên 32 bit của JNI.
4. Hàm C trả `5` về Java; toàn bộ lời gọi xảy ra trong cùng tiến trình. Ví dụ cố ý dùng số nhỏ để tránh vấn đề tràn số nguyên có dấu bên C.

**Vì sao cần `JNIEnv*` và `jclass`?** `JNIEnv*` cung cấp bảng hàm JNI để native code truy cập JVM theo hợp đồng; tham số `jclass` là class của native method `static`. Với instance native method, tham số thứ hai thường là `jobject`.

**Khi dùng C++:** header JNI sinh sẵn có bảo vệ liên kết C thích hợp khi biên dịch dưới C++. Mã triển khai thường cần tách rõ hàm export JNI, xử lý ngoại lệ C++ bên native và chuyển lỗi thành Java exception hoặc mã lỗi phù hợp; không để C++ exception tùy tiện đi xuyên qua ranh giới JNI.

## 6. Chuyển dữ liệu qua JNI: copy, pinning và vòng đời

Gọi native method chỉ truyền tham số; **không mặc nhiên có zero-copy**. Những cách điển hình:

| Dữ liệu Java | Cách native tiếp cận | Điều phải chú ý |
| --- | --- | --- |
| `int`, `long`, `double` và kiểu nguyên thủy | Truyền giá trị JNI như `jint`, `jlong`, `jdouble` | Kiểu C thông thường như `long` có kích thước thay đổi theo nền tảng; dùng kiểu JNI/cố định độ rộng. |
| `byte[]` / primitive array | API JNI như `GetByteArrayElements`, `ReleaseByteArrayElements` | JVM có thể **copy hoặc pin**; phải release đúng cách, không được giả định con trỏ tồn tại mãi. |
| `String` | API JNI cho chuỗi UTF hoặc UTF-16 | Quy ước mã hóa và độ dài quan trọng; `GetStringUTFChars` dùng *modified UTF-8* của JNI, không đồng nhất với mọi dữ liệu UTF-8 chuẩn. |
| Direct `ByteBuffer` | `GetDirectBufferAddress` / `GetDirectBufferCapacity` khi được hỗ trợ | Có thể truy cập vùng dữ liệu trực tiếp; phải giữ buffer và vùng backing hợp lệ trong suốt lượt sử dụng. |
| `jobject` | Tham chiếu JNI cục bộ/toàn cục | Local reference có vòng đời riêng; muốn giữ lâu hơn phải tạo và giải phóng global reference đúng API. |

Ví dụ về **sở hữu bộ nhớ**:

~~~text
Java byte[] -> JNI yêu cầu elements -> C xử lý
                                   -> JNI Release... -> Java tiếp tục

Java direct buffer -> native lấy địa chỉ -> C đọc/ghi
                   -> phải giữ backing memory còn hợp lệ
                   -> không dùng lại địa chỉ khi vòng đời kết thúc

C malloc(...) -> địa chỉ native -> wrapper Java giữ handle
               -> native free(...) khi hoàn tất
               -> wrapper không được truy cập lại địa chỉ đã free
~~~

Trong JNI, `JNIEnv*` là giao diện gắn với thread; không chia sẻ tùy tiện giữa các thread. Một thread do native code tự tạo muốn gọi API JNI thường phải gắn vào JVM trước và gỡ ra khi phù hợp. Khi đi qua JNI thường xuyên với dữ liệu nhỏ, chi phí chuyển lời gọi, copy/chuyển đổi và đồng bộ có thể lấn át phần tính toán native; đo tổng thời gian end-to-end trước khi tối ưu.

## 7. FFM API từ JDK 22: quản lý native memory có vòng đời rõ hơn

**Foreign Function & Memory API (FFM)** là API chính thức trong package `java.lang.foreign` kể từ **JDK 22** (JEP 454). FFM cung cấp hai nhóm chức năng:

- **Foreign memory:** `MemorySegment` mô tả một vùng nhớ có kích thước/ranh giới; `Arena` quy định cấp phát, quyền truy cập theo thread và vòng đời.
- **Foreign function:** `Linker`, `SymbolLookup`, `FunctionDescriptor` và method handle có thể dùng để gọi hàm native theo ABI phù hợp; một số thao tác liên quan native linkage là *restricted* và cần cấu hình quyền truy cập native theo JDK/cách đóng gói.

Ví dụ quản lý **bộ nhớ ngoài heap**, không cần biên dịch thư viện C, dành cho **JDK 22+**. Tạo `ForeignMemoryDemo.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ForeignMemoryDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            long size = 2L * ValueLayout.JAVA_INT.byteSize();
            MemorySegment data = arena.allocate(
                    size, ValueLayout.JAVA_INT.byteAlignment());

            data.setAtIndex(ValueLayout.JAVA_INT, 0, 40);
            data.setAtIndex(ValueLayout.JAVA_INT, 1, 2);

            int sum = data.getAtIndex(ValueLayout.JAVA_INT, 0)
                    + data.getAtIndex(ValueLayout.JAVA_INT, 1);
            System.out.println("sum=" + sum);
        }
    }
}
~~~

Chạy bằng JDK 22 trở lên:

~~~bash
javac ForeignMemoryDemo.java
java ForeignMemoryDemo
~~~

Stdout:

~~~text
sum=42
~~~

`Arena.ofConfined()` gắn quyền truy cập segment với thread tạo arena; đóng arena ở cuối `try-with-resources` sẽ hủy hiệu lực các native segment do arena quản lý và giải phóng vùng nhớ theo hợp đồng. Truy cập sai thread, ngoài biên hoặc sau khi đóng arena bị API kiểm tra và từ chối; **điều này không làm mã native tùy ý trở thành memory-safe**. Cần phân biệt `MemorySegment.ofArray(...)` (dữ liệu có thể nằm trên heap) với segment do native arena cấp phát (off-heap).

Khi dùng FFM để **gọi hàm C** từ Java, cần mô tả đúng function signature, bố cục struct, calling convention, cách tìm symbol, vòng đời con trỏ và quyền native access. **Không dùng cú pháp FFM của JDK 22 trong dự án chỉ chạy JDK 17**; ở JDK 17, `java.lang.foreign` chưa phải API chuẩn ổn định.

## 8. Sở hữu, giải phóng và đồng bộ: ba hợp đồng bắt buộc

Để Java và native code dùng chung một vùng nhớ, phải có thỏa thuận rõ ràng:

1. **Ownership (ai sở hữu):** Bên nào cấp phát, bên nào được đọc/ghi, bên nào chịu trách nhiệm giải phóng? Một vùng nhớ phải có quy tắc giải phóng duy nhất hoặc quy tắc chia sẻ được thiết kế rõ.
2. **Lifetime (sống đến khi nào):** Native code có được giữ địa chỉ sau khi hàm trả về không? Java wrapper còn sống có đủ bảo vệ backing memory không? Sau khi `free`/đóng `Arena`, mọi con trỏ, view hoặc handle liên quan phải được xem là hết hiệu lực.
3. **Concurrency (ai được truy cập đồng thời):** Nếu Java và C/C++ cùng sửa một vùng nhớ, phải có cơ chế đồng bộ và memory ordering tương thích. Không tự giả định Java `volatile` đủ để đồng bộ mọi truy cập native.

Ngoài ra còn **layout**: byte order, độ rộng số nguyên, alignment, padding của struct, null-termination và mã hóa chuỗi. Chẳng hạn, kiểu C `long` có thể khác kích thước giữa Windows và Linux 64 bit; không gán một cách mù quáng kiểu Java `long` cho C `long`. Với dữ liệu trao đổi độc lập nền tảng, ưu tiên cấu trúc có kích thước cố định và mô tả layout rõ ràng.

Tình huống lỗi điển hình:

~~~text
C malloc 100 bytes
   -> trả địa chỉ sang Java
   -> C free địa chỉ
   -> Java gọi native đọc lại địa chỉ cũ
   -> use-after-free: dữ liệu sai, crash hoặc memory corruption
~~~

Đây là lỗi **native memory safety**; Java type checking và GC không tự cứu được khi API native đã cho phép sử dụng địa chỉ không còn hợp lệ. Chiều ngược lại, nếu không gọi `free` sau khi wrapper Java biến mất, có thể gây **native memory leak**.

## 9. Lựa chọn công nghệ theo bài toán

| Cách tiếp cận | Phù hợp khi | Giới hạn cần cân nhắc |
| --- | --- | --- |
| **Java thuần + heap object/array** | Xử lý nghiệp vụ, dữ liệu nhỏ/vừa, không cần API hệ điều hành hoặc native library | Tùy đường I/O có thể phát sinh copy; vẫn nên đo hiệu năng thực tế. |
| **NIO direct `ByteBuffer`** | I/O hiệu năng cao hoặc thư viện nhận direct buffer; cần Java 17 tương thích | Quản lý vòng đời kém tường minh hơn arena; cấp phát tốn chi phí; không có giao diện tự động gọi C. |
| **JNI** | Tích hợp thư viện native hiện có, callback/truy cập Java object, hỗ trợ JDK cũ | Cần code wrapper và build theo nền tảng; dễ có bug pointer, reference, copy/pin, thread. |
| **FFM (JDK 22+)** | Muốn mô tả native memory/function bằng API Java chuẩn, vòng đời segment rõ ràng | Phải thiết kế ABI/layout/quyền native access chính xác; native library vẫn có thể gây lỗi nguy hiểm. |
| **Tiến trình native riêng + IPC/RPC** | Cần cô lập lỗi/crash và quyền truy cập của native component | Có chi phí serialization, truyền dữ liệu và vận hành; không còn là lời gọi cùng tiến trình. |

**Chọn off-heap vì một nhu cầu đo được** (I/O, tương tác thư viện native, vùng nhớ lớn có kiểm soát), không vì giả định “GC không đụng tới thì luôn nhanh”. Khi cần tích hợp C++, thiết kế một giao diện C ABI nhỏ, ổn định và mô tả quyền sở hữu bộ nhớ rõ trong tài liệu API.

## 10. Quan sát và chẩn đoán bộ nhớ

Giả sử ứng dụng đặt `-Xmx512m` nhưng RSS của tiến trình lớn hơn nhiều. Điều này **không tự chứng minh Java heap leak**. Trình tự tìm nguyên nhân:

1. Đo Java heap thực dùng, số thread và GC; đối chiếu với giới hạn `-Xmx`.
2. Kiểm tra lượng direct-buffer allocation, metaspace, code cache và native/JVM memory; đồng thời theo dõi bộ nhớ tiến trình từ OS.
3. Nếu dùng JNI hoặc thư viện C/C++ có `malloc` riêng, dùng công cụ native profiler/leak detector thích hợp; Java heap dump có thể chỉ thấy wrapper mà không thấy mọi vùng native được cấp phát.
4. Xem vòng đời handle/buffer/arena, số lượt gọi, các nhánh lỗi và thời điểm release.

Ví dụ, bật Native Memory Tracking của HotSpot lúc khởi chạy ứng dụng:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
jcmd <PID> VM.native_memory summary
~~~

`<PID>` là PID thực của tiến trình JVM. **NMT có chi phí và chủ yếu theo dõi các vùng cấp phát do JVM quản lý**; không được coi là bộ đo đầy đủ cho mọi lần thư viện C/C++ tự `malloc`. Kết hợp với số liệu OS (RSS, mappings) và công cụ phân tích native phù hợp khi cần.

Một số biểu hiện thường gặp:

| Triệu chứng | Nghi vấn cần kiểm chứng |
| --- | --- |
| `OutOfMemoryError: Java heap space` | Vùng heap hoặc số đối tượng sống vượt giới hạn/khả năng cấp phát. |
| Thông báo không cấp phát được direct buffer | Giới hạn/áp lực direct memory; buffer giữ lâu, cấp phát dồn dập hoặc giới hạn cấu hình. |
| RSS tăng nhưng heap ổn định | Direct/off-heap/native allocation, thread stacks, mmap, bộ nhớ runtime hoặc memory accounting. |
| `UnsatisfiedLinkError` | Sai library path/tên/symbol, phụ thuộc native thiếu, sai kiến trúc/ABI hoặc lỗi liên kết. |
| JVM crash với tín hiệu native hoặc access violation | Pointer sai, tràn bộ đệm, use-after-free, race hay lỗi native/JVM; xem `hs_err_pid*.log` và native stack khi có. |

`-Xcheck:jni` có thể giúp HotSpot phát hiện **một số** lỗi dùng JNI; đây không phải công cụ chứng minh toàn bộ native code an toàn.

## 11. Các hiểu nhầm cần tránh

- **“JVM là Java thuần nên không liên quan C/C++.”** Sai: bản triển khai JVM có mã native và gọi nhiều dịch vụ OS qua lớp runtime.
- **“Java gọi C nghĩa là tạo tiến trình C riêng.”** Sai trong JNI/FFM thông thường: thư viện chạy cùng tiến trình; IPC/RPC mới là kiến trúc tiến trình tách biệt.
- **“Mọi thứ ngoài `-Xmx` đều là memory leak.”** Sai: heap Java chỉ là một phần bộ nhớ tiến trình.
- **“Off-heap không có GC.”** Vùng C `malloc` do C quản lý; nhưng một direct buffer có thể được thu hồi gián tiếp khi Java wrapper không còn reachable. Cần phân biệt hai cơ chế.
- **“Có pointer rồi thì Java tự bảo đảm an toàn.”** Sai: API native có thể phá vỡ bảo vệ thường thấy ở Java; phải kiểm tra biên, ownership và lifetime.
- **“JNI array luôn zero-copy.”** Sai: JNI có thể copy/pin tùy API và JVM; phải release và đo hiệu năng.
- **“FFM thay thế mọi lý do dùng JNI.”** Không hẳn: FFM hỗ trợ native function/memory bằng API chuẩn; JNI vẫn có những kịch bản gắn chặt với JVM object, VM tooling, integration cũ.
- **“Dùng C++ trực tiếp như gọi method Java.”** Sai: cần cầu nối và hợp đồng ABI, mangling, layout, exception, ownership.
- **“Chỉ cần gọi `free` là xong.”** Sai nếu còn buffer/view/con trỏ đang được dùng bởi thread khác hoặc Java wrapper; phải chấm dứt mọi lượt dùng trước khi giải phóng.

## 12. Tự kiểm tra kiến thức

1. Khi `-Xmx` được đặt 512 MB, vì sao RSS tiến trình có thể là 1 GB mà chưa chắc bị heap leak?
2. Trong chương trình `DirectMemoryDemo`, `flip()` thay đổi dữ liệu, giải phóng native memory hay chỉ thay đổi con trỏ đọc/ghi?
3. Tại sao thư viện JNI có thể khiến cả tiến trình JVM crash?
4. Bên C trả về một con trỏ do `malloc` cấp phát. Tài liệu API giữa C và Java tối thiểu phải nói rõ những điều gì?
5. Nếu native code cần giữ dữ liệu sau khi JNI method trả về, tại sao không được tùy tiện giữ địa chỉ `byte[]` lấy qua JNI?
6. Khác biệt chính giữa `ByteBuffer.allocateDirect` và `Arena.ofConfined` về khả năng chủ động xác định thời điểm hết hiệu lực là gì?

**Gợi ý đối chiếu:** (1) JVM và native code còn dùng memory ngoài heap; (2) chỉ đổi trạng thái position/limit; (3) cùng không gian địa chỉ và native pointer có thể sai; (4) ownership, lifetime, layout, lỗi và đồng bộ; (5) bản copy/pin và vòng đời JNI không được bảo đảm sau khi release; (6) arena đóng tường minh, còn direct buffer thường phụ thuộc vòng đời wrapper/cleaner.

## 13. Tài liệu chuẩn để học sâu

- Oracle JDK 17, `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Oracle, Java Native Interface Specification: https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html
- OpenJDK, JEP 454 – Foreign Function & Memory API (finalized in JDK 22): https://openjdk.org/jeps/454
- Oracle JDK 22, package `java.lang.foreign`: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html

**Điểm cần nắm:** JVM thực thi mã Java, dùng mã native để tương tác OS, và có thể gọi trực tiếp thư viện C/C++. Java heap do GC quản lý, còn off-heap có nhiều cơ chế cấp phát/giải phóng khác nhau. An toàn và hiệu năng của đường Java–native phụ thuộc **ABI, cách truyền dữ liệu, quyền sở hữu, vòng đời và đồng bộ**.
