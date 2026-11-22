# JNI, JNA và khả năng tương thích thư viện native

Khi nâng một ứng dụng Java lên JDK mới, phần mã Java thuần có thể biên dịch và kiểm thử thành công nhưng chương trình vẫn lỗi ngay khi nạp thư viện native, khởi tạo agent, gọi một hàm C/C++ hoặc nhận callback từ mã ngoài JVM. Các lỗi như UnsatisfiedLinkError, lỗi truy cập bộ nhớ, JVM crash, sai dữ liệu trả về hoặc treo khi shutdown thường có nguồn gốc ở **ranh giới Java–native**.

Một thư viện native không chỉ phụ thuộc vào version Java. Nó còn phụ thuộc vào hệ điều hành, kiến trúc CPU, ABI, calling convention, trình biên dịch C/C++, runtime libraries, cơ chế nạp dynamic library, cách quản lý con trỏ, thread và bộ nhớ. Đó là lý do cùng một JAR có thể chạy tốt trên Linux x86-64 nhưng thất bại trên Linux ARM64, Windows, macOS hoặc một container có libc khác.

Trong chủ đề **Java Advance Compatibility Migration**, chương **Agent và mã native**, bài học này giải thích hai cơ chế quan trọng là **JNI (Java Native Interface)** và **JNA (Java Native Access)**, những loại tương thích phải đánh giá khi thay JDK và runtime, cách chẩn đoán lỗi và cách thiết kế quy trình migration an toàn.

Mục tiêu không phải chỉ làm cho JVM tìm thấy file .so, .dll hoặc .dylib. Mục tiêu là bảo đảm **Java và mã native thống nhất hoàn toàn về dữ liệu, quyền sở hữu bộ nhớ, cách gọi, ngoại lệ, threading, đóng tài nguyên và các nền tảng được hỗ trợ**.

## 1. Mã native nằm ở đâu trong một ứng dụng Java?

Ứng dụng Java có thể đi qua nhiều loại ranh giới:

~~~text
Java application
       |
       +--> Java framework / dependency JAR
       |         |
       |         +--> JNI wrapper
       |         |       |
       |         |       v
       |         |   C/C++ native library
       |         |
       |         +--> JNA / libffi invocation
       |                 |
       |                 v
       |             OS native library
       |
       +--> Java agent (-javaagent)
       |         |
       |         +--> Bytecode instrumentation
       |         +--> Có thể dùng JNI/JVMTI riêng
       |
       +--> Native agent (-agentlib/-agentpath)
                 |
                 v
               JVMTI
~~~

Những thư viện thường liên quan mã native:

- JDBC driver dùng native client library.
- Thư viện compression, image/video, OCR, audio hoặc computer vision.
- Cryptography, HSM, PKCS#11 và thư viện bảo mật.
- Embedded database hoặc storage engine.
- Machine-learning inference runtime.
- Truy cập thiết bị, serial port, USB, GPU.
- Operating-system integration.
- Monitoring, profiler, debugger, tracing agent.
- Libraries viết bằng Rust/C/C++ được đóng gói làm native binary.

Một thành phần có tên JAR không có nghĩa nó chỉ chứa bytecode Java. Nhiều JAR có file native nhúng, trích xuất ra thư mục tạm và nạp bằng System.load, JNI hoặc JNA.

## 2. Phân biệt JNI, JNA, FFM và JVMTI

| Cơ chế | Cách gọi | Đặc điểm | Mối quan tâm chính |
|---|---|---|---|
| JNI | Java khai báo native method; thư viện hiện thực theo giao thức JNI | API chuẩn lâu đời cho Java–native integration | JNI signatures, JNIEnv, exception, references |
| JNA | Java dùng interface/mapping để gọi hàm native qua JNA runtime | Giảm nhu cầu viết JNI glue code thủ công trong nhiều trường hợp | C ABI, types, structure layouts, JNA/libffi |
| FFM API | Java dùng Foreign Function & Memory API của JDK phù hợp | API chuẩn hiện đại để gọi foreign functions và quản lý off-heap memory | Descriptors, memory layouts, lifetimes, native access |
| JVMTI | Native agent tương tác với JVM qua tooling interface | Dành cho profiler/debugger/monitoring/agent | Event/capability lifecycle, JVMTI/JVM compatibility |
| Java Instrumentation API | Java agent biến đổi bytecode qua java.lang.instrument | Không phải JNI thuần | Bytecode, module openness, agent bootstrap |

**JNI và JNA không phải cùng một thứ.** JNI là giao diện mức thấp giữa Java và mã native. JNA là thư viện cung cấp cơ chế mapping/gọi các hàm native qua runtime hỗ trợ; JNA implementation bản thân cũng có thành phần native, và không biến một C++ API tùy ý thành ABI ổn định.

**JVMTI khác JNI.** Một JVMTI agent có thể dùng JNI để thao tác với Java objects, nhưng JVMTI định nghĩa một tập API khác cho instrumentation và quan sát JVM. Không nên xếp mọi lỗi agent vào cùng nhóm “JNI library missing”.

## 3. Các lớp tương thích cần đánh giá

Một đợt nâng Java có thể phá vỡ nhiều lớp mà compiler Java không nhìn thấy.

| Lớp | Câu hỏi | Triệu chứng có thể gặp |
|---|---|---|
| Java source | Native method declarations và wrapper API còn đúng không? | Lỗi compile |
| Java binary | Native method name/descriptor còn khớp không? | UnsatisfiedLinkError khi gọi |
| JNI contract | JNI function signature và cách dùng JNIEnv còn hợp lệ không? | Crash, exception, dữ liệu sai |
| C ABI | Calling convention, symbol, struct layout, integer size có khớp không? | Crash, tham số/trả về bị hỏng |
| Platform | OS, CPU, bitness, libc có cùng target không? | Không load thư viện |
| Dependencies | Native binary còn đủ dependency/linker symbols không? | Linker error |
| JDK policy | Quyền native access, module, agent loading có đổi không? | Warning hoặc runtime rejection tùy JDK |
| Memory | Con trỏ, buffer, reference có còn sống đủ lâu không? | Use-after-free, JVM crash |
| Threading | Thread native gọi vào JVM có attach/detach đúng không? | Crash, leak, treo |
| Error handling | Native error codes, Java exception, errno có được xử lý đúng không? | Silent corruption |
| Operations | Library được extract/load/cleanup như thế nào? | Lỗi ở container, permission, shutdown |

Một chương trình có thể vượt qua cả bước nạp thư viện và lời gọi đơn giản nhưng vẫn hỏng khi chạy đồng thời, khi GC hoạt động hoặc khi được shutdown/redeploy.

## 4. Mô hình JNI: Java gọi C qua tên và kiểu được quy định

JNI cho phép class Java công bố native method:

~~~java
package com.example.nativebridge;

public final class NativeMath {
    static {
        System.loadLibrary("nativecalc");
    }

    private NativeMath() {
    }

    public static native long sum(long a, long b);
}
~~~

Lời gọi:

~~~java
long result = NativeMath.sum(10L, 20L);
System.out.println(result);
~~~

Java chỉ có khai báo native method, không có thân method Java. Khi class khởi tạo, System.loadLibrary yêu cầu JVM nạp thư viện native có logical name nativecalc từ đường tìm kiếm phù hợp.

Native implementation cần có ABI JNI phù hợp.

### 4.1. Header C thường có dạng

~~~c
#include <jni.h>

JNIEXPORT jlong JNICALL
Java_com_example_nativebridge_NativeMath_sum(
        JNIEnv *env,
        jclass clazz,
        jlong a,
        jlong b) {
    (void)env;
    (void)clazz;
    return a + b;
}
~~~

Trong ví dụ:

- JNIEXPORT phục vụ cách export symbol theo platform.
- JNICALL biểu diễn calling convention do JNI quy định.
- JNIEnv* cung cấp tập JNI functions cho thread thực thi.
- Với **static native method**, tham số thứ hai là jclass.
- Với **instance native method**, tham số thứ hai là jobject.
- jlong là kiểu JNI có kích thước phù hợp với Java long 64-bit.

Tên hàm dài ở ví dụ ứng với quy ước đặt tên JNI cho class/method tương ứng. Trong trường hợp overload, tên native có thể thêm thành phần mã hóa signature. Không nên tự đoán mọi symbol name khi có thể tạo header bằng javac.

### 4.2. Tạo header với javac -h

Với JDK hỗ trợ:

~~~bash
javac -h native-headers -d classes src/com/example/nativebridge/NativeMath.java
~~~

Compiler có thể tạo header khai báo JNI function với tên, kiểu và macro cần thiết.

Tư duy an toàn:

1. Java native declaration là nguồn contract.
2. Generate header từ declaration.
3. C/C++ implementation include header đó.
4. Build native library bằng toolchain đúng platform.
5. Nạp bằng Java runtime tương ứng.
6. Chạy integration tests trên tất cả nền tảng được hỗ trợ.

Không nên viết tay mọi JNI function prototype rồi giả định vẫn khớp sau khi đổi package, tên method hoặc tham số.

### 4.3. Static và instance native methods

Instance method:

~~~java
public final class NativeCounter {
    public native int increment(int delta);
}
~~~

C implementation nhận jobject receiver thay cho jclass:

~~~c
JNIEXPORT jint JNICALL
Java_com_example_nativebridge_NativeCounter_increment(
        JNIEnv *env,
        jobject self,
        jint delta) {
    (void)env;
    (void)self;
    return delta + 1;
}
~~~

Đây là ví dụ minh họa hình dạng signature; package/class name của C function phải đúng với package Java thực tế. Chỉ thay jclass thành jobject hoặc đổi Java method mà không build lại thư viện là một rủi ro linkage.

## 5. JNI_OnLoad và vòng đời native library

Một thư viện JNI có thể khai báo JNI_OnLoad để nhận JavaVM pointer khi JVM nạp thư viện.

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_8;
}
~~~

JNI_OnLoad có thể là nơi kiểm tra hoặc khởi tạo một phần trạng thái. Nhưng không nên làm initialization nặng gây deadlock hoặc gọi các API không phù hợp thời điểm này.

Khi cần liên kết Java native methods mà không phụ thuộc vào tên symbol, có thể dùng RegisterNatives với đúng class và method signatures. Cách này đòi hỏi quản lý mapping rõ ràng; không được hiểu là bỏ qua type checks hay ràng buộc JNI.

### 5.1. Không phụ thuộc vào unload tự động để cleanup nghiệp vụ

JNI_OnUnload có thể xuất hiện khi thư viện được unload trong những điều kiện JVM cho phép. Tuy nhiên, thời điểm unload liên quan classloader và lifetime của native references, không phải một callback shutdown đáng tin cậy cho mọi ứng dụng.

Nên thiết kế explicit close/shutdown API cho context/handle native, và giải phóng tài nguyên khi ứng dụng hoặc service kết thúc theo hợp đồng rõ ràng.

### 5.2. Java object và native handle nên có ownership

Một Java object có thể giữ jlong đại diện cho con trỏ hoặc ID handle native. Cần phân biệt:

- Java object có đang sở hữu handle không?
- Native handle còn hợp lệ khi phương thức được gọi không?
- Có cho phép close nhiều lần không?
- Có nhiều Java objects dùng chung một handle không?
- Một thread có thể close khi thread khác đang gọi không?
- Khi lỗi một phần, ai giải phóng resource đã được cấp phát?

Không nên xem một jlong chứa địa chỉ memory là một con số bình thường để lưu, truyền hoặc sửa tùy ý.

## 6. JNI types và mapping dữ liệu

JNI có các kiểu định nghĩa rõ, không nên thay bằng kiểu C/C++ gần giống dựa trên trực giác.

| Java | JNI type | Ghi chú |
|---|---|---|
| boolean | jboolean | Biểu diễn JNI, không tự giả định bằng C++ bool trong mọi ABI |
| byte | jbyte | Số nguyên 8-bit có dấu |
| char | jchar | 16-bit unsigned code unit của UTF-16 |
| short | jshort | Số nguyên 16-bit |
| int | jint | Số nguyên 32-bit |
| long | jlong | Số nguyên 64-bit |
| float | jfloat | Số thực 32-bit |
| double | jdouble | Số thực 64-bit |
| Object | jobject | JNI reference |
| String | jstring | JNI reference tới String |
| Class | jclass | JNI class reference |
| Array | jarray / kiểu chuyên biệt | JNI array reference |

Các platform có thể khác kích thước C long, size_t, pointer và alignment. Nếu C code cần số 64-bit từ Java long, dùng jlong hoặc loại C cố định phù hợp khi chuyển đổi có kiểm soát.

### 6.1. Lỗi C long không phải Java long

Trên nhiều môi trường Linux 64-bit, C long thường là 64-bit. Trên Windows 64-bit, C long thường là 32-bit theo ABI tương ứng. Java long luôn 64-bit.

Nếu chuyển jlong sang C long mà không kiểm tra phạm vi/ABI, có thể mất dữ liệu trên một số nền tảng.

### 6.2. Char và Unicode

Java char là một UTF-16 code unit, không đồng nhất với ký tự Unicode đầy đủ và không phải C char byte.

JNI có các API làm việc với jstring theo UTF-16 hoặc modified UTF-8. **JNI modified UTF-8 không được đánh đồng với UTF-8 chuẩn**. Khi tích hợp C library yêu cầu UTF-8 chuẩn, cần chuyển mã rõ ràng và kiểm thử ký tự ngoài BMP, null byte, emoji và các ngôn ngữ khác.

### 6.3. Boolean khác byte thông thường

Khi mapping Java boolean sang native API, cần xác nhận phía native muốn _Bool, BOOL, bool, uint8_t hay int. Những kiểu này có thể có kích thước, alignment và calling convention khác nhau.

Không nên truyền jboolean trực tiếp qua interface của một thư viện OS vốn khai báo tham số 32-bit BOOL rồi coi đó là tương đương.

## 7. JNA: gọi C ABI mà không viết JNI glue thủ công

JNA cho phép khai báo Java interface biểu diễn các hàm C được export từ native library. Ví dụ C:

~~~c
/* nativecalc.c */
int add(int a, int b) {
    return a + b;
}
~~~

Khi build shared library, cần export symbol add theo toolchain/platform. Trên Windows có thể cần __declspec(dllexport); với C++ cần xem extern "C" để tránh name mangling.

Java JNA interface:

~~~java
package com.example.jnademo;

import com.sun.jna.Library;
import com.sun.jna.Native;

public interface NativeCalc extends Library {
    NativeCalc INSTANCE = Native.load(
        "nativecalc",
        NativeCalc.class
    );

    int add(int a, int b);
}
~~~

Sử dụng:

~~~java
int result = NativeCalc.INSTANCE.add(2, 3);
System.out.println(result);
~~~

Trong ví dụ, JNA chịu trách nhiệm phần lớn việc mapping lời gọi đến exported native function. Nó không cần cùng mẫu JNIEXPORT Java_package_Class_method như JNI code thủ công.

### 7.1. Điều kiện của ví dụ JNA

Ví dụ chỉ chạy được khi:

- Native library đã được build cho OS/CPU tương ứng.
- Symbol add thực sự được export.
- Chữ ký Java int, int → int khớp với C int trên ABI mục tiêu.
- JNA runtime và native support library tương thích với JDK/OS.
- Library và dependency native có thể được loader tìm thấy.
- Calling convention phù hợp.

Nếu mã C++ export function bị mangled hoặc function dùng calling convention khác, khai báo interface JNA thông thường có thể không tìm hoặc không gọi đúng symbol.

### 7.2. JNA không làm biến mất ABI

JNA giảm khối lượng JNI glue code, nhưng C ABI vẫn phải chính xác:

- Kích thước và signedness của integer.
- Pointer width.
- Struct packing/alignment.
- Callback signatures.
- Ownership của memory.
- Calling convention.
- String encoding.
- C++ symbol name và layout.
- Thời gian sống của function pointers.

Nếu ABI không khớp, JNA có thể dẫn tới crash, memory corruption hoặc trả kết quả sai mà Java compiler không phát hiện.

## 8. JNI và JNA nên chọn thế nào?

| Tiêu chí | JNI | JNA |
|---|---|---|
| Cần viết native bridge | Thường có | Thường ít hơn khi thư viện export C ABI phù hợp |
| Cần C/C++ compiler cho wrapper | Thường có | Không cần viết wrapper cho nhiều trường hợp đơn giản |
| Access tới Java objects | Trực tiếp qua JNI API | Có cơ chế callback/mapping nhưng không thay JNI đầy đủ |
| Tối ưu đường gọi đặc thù | Có thể kiểm soát bridge chi tiết | Có thêm lớp mapping/FFI |
| ABI mismatch | Rủi ro cao | Vẫn rủi ro cao |
| Tích hợp API OS dạng C | Có thể | Thường tiện |
| Callback/threading | Phải quản lý JNI rules | Phải quản lý callback lifetime/native rules |
| Dependency native hỗ trợ | Library và wrapper tự build | JNA runtime/libffi và library mục tiêu |
| Migration JDK | Kiểm tra JNI contract và native build | Kiểm tra JNA version, loader và library ABI |

Không có một lựa chọn tốt nhất cho mọi ứng dụng. Với thư viện native đã có C ABI đơn giản, JNA có thể giảm công sức. Với callback phức tạp, tương tác sâu với JVM hoặc hiệu năng cần kiểm soát chi tiết, JNI có thể phù hợp hơn. Với dự án mới trên JDK phù hợp, Foreign Function & Memory API là một hướng khác cần đánh giá.

### 8.1. Không quyết định chỉ bằng benchmark đơn giản

Hiệu năng phụ thuộc số lần crossing Java–native, chi phí marshalling, kích thước dữ liệu, calling conventions, JIT, library implementation và workload.

Một lời gọi native rất ngắn được thực hiện hàng triệu lần có thể bị chi phối bởi overhead boundary. Nhưng với việc xử lý một ảnh lớn hoặc thao tác mật mã nặng, chi phí tính toán native có thể lớn hơn nhiều so với overhead gọi.

Trước khi tối ưu, hãy xác định batch size, zero-copy khả thi, luồng dữ liệu và chi phí cấp phát/chuyển đổi.

## 9. OS, CPU architecture và bitness

Một native binary có định dạng riêng:

| Hệ điều hành | Ví dụ extension | Định dạng thường gặp |
|---|---|---|
| Windows | .dll | PE/COFF |
| Linux | .so | ELF |
| macOS | .dylib hoặc .jnilib theo ngữ cảnh legacy | Mach-O |

Không thể nạp Linux .so trực tiếp vào JVM trên Windows, hoặc thư viện x86-64 vào tiến trình ARM64 nếu không có cơ chế tương thích cụ thể ngoài chuẩn chung.

Những khác biệt cần ghi nhận:

- x86-64 và aarch64/arm64.
- Windows, Linux, macOS.
- 32-bit và 64-bit.
- glibc và musl trên Linux.
- Version tối thiểu của hệ điều hành.
- CPU instruction set như AVX/NEON.
- Native dependencies (OpenSSL, libstdc++, libgcc, CUDA, v.v.).
- ABI version của trình biên dịch hoặc runtime C++.

### 9.1. Thế nào là lỗi sai kiến trúc?

Ví dụ một Linux ARM64 container nạp .so build cho x86-64. JVM có thể báo UnsatisfiedLinkError kèm lỗi từ dynamic loader về sai ELF class, machine type hoặc format.

Cách xử lý là cung cấp binary đúng architecture hoặc build native component cho platform mục tiêu. Đặt lại java.library.path không biến file x86-64 thành ARM64.

### 9.2. Container image thay đổi libc

Một ứng dụng chạy trên Ubuntu/debian-based image có thể dùng native library link với glibc. Chuyển sang Alpine Linux thường kéo theo môi trường musl. Dù CPU architecture không đổi, .so và các dependency có thể không nạp được.

Đây là lý do migration JDK đồng thời với đổi base image là một thay đổi kép. Cần xác minh native compatibility với image cuối cùng.

### 9.3. macOS universal binaries và codesigning

macOS có các yêu cầu về architecture, code signing, hardened runtime và quyền tải dynamic libraries tùy môi trường. Một native library từng chạy trong môi trường phát triển có thể bị chặn khi đóng gói ứng dụng desktop hoặc distribution khác.

Cần kiểm tra chữ ký, quarantine, architecture slices và cơ chế packaging theo chính sách của platform, thay vì chỉ chỉnh Java classpath.

## 10. Dynamic linker, symbol và dependency native

System.loadLibrary chỉ yêu cầu load tên thư viện. Hệ điều hành còn phải giải quyết mọi dependency của thư viện đó.

Ví dụ:

~~~text
Java:
  System.loadLibrary("nativecalc")
       |
       v
nativecalc.so
       |
       +--> libstdc++.so
       +--> libcrypto.so
       +--> libc.so
~~~

Nếu nativecalc.so tồn tại nhưng libcrypto.so đúng ABI không có, JVM vẫn có thể báo UnsatisfiedLinkError do một dependency bắc cầu không tìm thấy.

Các câu hỏi cần đặt:

1. File library có được tìm thấy không?
2. Nó có đúng OS/CPU/bitness không?
3. Những dependency native khác đã có chưa?
4. Symbol cần dùng đã được export chưa?
5. Runtime linker có tìm đúng bản dependency không?
6. Có xung đột ABI giữa các version không?
7. Có bị policy OS chặn load không?

### 10.1. Tên thư viện Java và tên file

~~~java
System.loadLibrary("nativecalc");
~~~

dùng logical name. JVM ánh xạ thành tên file theo platform và implementation, chẳng hạn libnativecalc.so trên Linux hoặc nativecalc.dll trên Windows.

~~~java
System.load("/opt/app/native/libnativecalc.so");
~~~

dùng đường dẫn tuyệt đối tới file cụ thể. Đường dẫn ví dụ mang tính minh họa. Khi ứng dụng chạy trên nhiều OS, không nên hard-code đường Linux cho mọi môi trường.

### 10.2. java.library.path khác classpath

Classpath tìm Java classes/resources. java.library.path là một đầu vào cho cơ chế tìm native library của JVM phù hợp.

Đưa .so vào thư mục chứa JAR không tự bảo đảm System.loadLibrary sẽ tìm ra. Cũng không nên dựa vào việc thay java.library.path **sau khi JVM đã khởi động** rồi giả định loader sẽ cập nhật mọi đường tìm kiếm; cách xử lý thực tế phụ thuộc JVM và cơ chế load.

### 10.3. JNA có cơ chế tìm library riêng

JNA có những đường tìm kiếm/cấu hình như jna.library.path tùy cách dùng. Nhưng JNA vẫn phụ thuộc vào dynamic loader của OS và các native dependencies bên dưới.

Nếu chạy trong container, cần kiểm tra cả nơi JNA extract native support library, quyền execute của filesystem tạm và khả năng load library từ đường dẫn đó.

## 11. ABI: tại sao method signature trông giống vẫn có thể sai?

**ABI (Application Binary Interface)** định nghĩa cách các binary trao đổi dữ liệu và lời gọi ở cấp máy: register/stack, parameter layout, return values, symbol naming, alignment và những quy ước khác.

### 11.1. Kích thước primitive ở C không đồng nhất mọi nơi

Một số kiểu dễ nhầm:

| C/C++ type | Kích thước hoặc vấn đề | Hướng xử lý |
|---|---|---|
| int | Thường 32-bit trên platform phổ biến, nhưng do ABI quyết định | Xác nhận bằng header và platform ABI |
| long | Có thể 32-bit hoặc 64-bit | Không đồng nhất với Java long |
| size_t | Theo kích thước địa chỉ của platform | Mapping pointer-width phù hợp |
| void* | 32/64-bit hoặc hơn theo platform | Không ép bừa sang Java int |
| bool / _Bool | Biểu diễn theo compiler/ABI | Không tự coi là Java boolean |
| wchar_t | Khác kích thước giữa platform | Không đồng nhất với Java char |
| long double | Khác format/kích thước | Không map tùy tiện sang double |

Để thiết kế một C API ổn định cho JNA/JNI, có thể dùng fixed-width types như int32_t, int64_t, uint32_t từ stdint.h khi thích hợp, cùng hợp đồng rõ về pointer-sized types.

### 11.2. Calling convention

Trên một số platform và ABI, cdecl, stdcall, fastcall hoặc quy tắc platform có thể khác cách truyền tham số và quản lý stack.

Một interface JNA cần được khai báo theo calling convention tương ứng, có thể dùng StdCallLibrary trong những Windows APIs phù hợp. Nếu khai báo nhầm, lời gọi có thể gây lỗi khó chẩn đoán.

Với JNI, dùng đúng JNIEXPORT/JNICALL và header sinh ra bởi javac giúp giảm nguy cơ gọi sai convention.

### 11.3. C++ ABI không phải C ABI ổn định chung

C++ có name mangling, overload, class layout, virtual table, exception handling và standard library ABI phụ thuộc compiler/platform/version.

Nếu cần expose C++ library cho JNA hoặc nhiều runtime, nên cân nhắc một **C ABI facade** được công bố:

~~~cpp
extern "C" {
    int nativecalc_add(int a, int b) {
        return a + b;
    }
}
~~~

Để DLL trên Windows export function qua dynamic symbol table, có thể cần thêm export annotations/file .def tương ứng. extern "C" chủ yếu xử lý C language linkage, không tự bảo đảm symbol được export hoặc toàn bộ ABI tương thích.

## 12. Structure layout, alignment và packing

Một C struct:

~~~c
#include <stdint.h>

struct SensorReading {
    uint8_t status;
    double value;
    uint32_t sequence;
};
~~~

không có layout “cộng kích thước từng field” đơn giản. Compiler có thể thêm padding để căn chỉnh double hoặc phần tử tiếp theo.

Nếu code JNA mapping thành Structure, thứ tự field và quy tắc layout/packing phải khớp native ABI. Khác nhau về alignment có thể khiến đọc sai value hoặc sequence mà không gây lỗi ngay.

### 12.1. Cần kiểm tra sizeof và offsetof

Một cách mô tả ABI native rõ ràng là cung cấp test C:

~~~c
#include <stddef.h>
#include <stdio.h>

int main(void) {
    printf("sizeof=%zu\n", sizeof(struct SensorReading));
    printf("value_offset=%zu\n",
           offsetof(struct SensorReading, value));
    printf("sequence_offset=%zu\n",
           offsetof(struct SensorReading, sequence));
    return 0;
}
~~~

Với chương trình đầy đủ, thêm định nghĩa struct ở trên. Sau đó so sánh size/offset thực tế với Java mapping trên từng platform được hỗ trợ.

### 12.2. JNA Structure và field order

Một mapping JNA có thể dùng Structure và @FieldOrder:

~~~java
import com.sun.jna.Structure;

@Structure.FieldOrder({
    "status", "value", "sequence"
})
public class SensorReading extends Structure {
    public byte status;
    public double value;
    public int sequence;
}
~~~

Ví dụ thể hiện thứ tự field và kiểu cơ bản. **Chưa đủ để khẳng định mọi native ABI đều khớp**: cần xem alignment, packed attribute, unsigned semantics và platform-specific layout.

Với struct chứa pointer, union, array, bit-field hoặc nested struct, mapping phức tạp hơn; phải kiểm thử trực tiếp với native library.

### 12.3. Thay compiler flag có thể phá ABI

Nếu thay -fpack-struct, pragma pack, compiler flags, version C++ standard library hoặc alignment rules, layout có thể đổi ngay cả khi tên struct và field giữ nguyên.

Do đó, nâng compiler C/C++ trong cùng đợt nâng JDK phải được xem là một thay đổi ABI độc lập.

## 13. Con trỏ, buffer và quyền sở hữu bộ nhớ

Java GC quản lý vòng đời Java objects, nhưng nó không tự giải phóng mọi tài nguyên được native code cấp phát.

Ví dụ native:

~~~c
void* native_alloc(size_t size);
void native_free(void* ptr);
~~~

Nếu Java nhận pointer từ native_alloc, cần quy định **ai phải gọi native_free** và khi nào.

### 13.1. Các câu hỏi ownership quan trọng

- Caller hay callee cấp phát?
- Ai giải phóng?
- Có thể giữ pointer sau lời gọi không?
- Pointer có bị invalid khi object/context đóng không?
- Nhiều threads có được phép dùng đồng thời không?
- Function trả con trỏ đến static memory, stack memory hay heap memory?
- Có cần một paired free function từ đúng thư viện native không?
- Con trỏ có được trả về từ một instance nhưng giải phóng bởi instance khác không?

Không bao giờ giải phóng pointer của native allocator A bằng allocator B nếu API không bảo đảm điều đó. Trên Windows, khác CRT heap có thể đặc biệt nguy hiểm; trên mọi platform, quy tắc ownership vẫn cần được tuân thủ.

### 13.2. JNA Memory và Pointer

JNA cung cấp các abstraction như Pointer và Memory để thao tác với vùng nhớ native. Memory là vùng native được JNA cấp phát/quản lý theo API của nó; Pointer chỉ là một tham chiếu, không hàm ý bạn có quyền free pointer nguồn gốc bất kỳ.

Khi callback đưa cho Java một Pointer tạm có hiệu lực chỉ trong callback, không được giữ Pointer đó và đọc sau khi native đã giải phóng bộ nhớ.

### 13.3. DirectByteBuffer và JNI

JNI có thể tạo hoặc truy cập direct buffer để giảm copying trong một số đường dữ liệu. Tuy nhiên:

- Buffer có lifetime và ownership riêng.
- Native pointer phải vẫn hợp lệ trong suốt thời gian Java truy cập.
- Không được sử dụng sau khi native free.
- Cần bảo đảm thread safety.
- Byte order có thể cần được thiết lập rõ.
- Không giả định zero-copy luôn là lựa chọn nhanh/an toàn nhất.

Một buffer trỏ vào vùng nhớ đã được giải phóng có thể gây JVM crash ngoài cơ chế Java exception thông thường.

## 14. JNI reference: local, global và weak global

JNI không cho native code sử dụng Java object reference theo cách tùy ý.

### 14.1. Local reference

Local reference thường có hiệu lực trong phạm vi native call/thread context tương ứng và được JVM quản lý theo JNI rules. Không nên cache một local jobject vào global C variable rồi dùng lại khi native method đã trả về.

### 14.2. Global reference

Nếu native code cần giữ Java object qua nhiều lời gọi/callback, có thể tạo global reference bằng NewGlobalRef và phải giải phóng bằng DeleteGlobalRef khi không còn cần.

~~~c
jobject globalRef = (*env)->NewGlobalRef(env, someObject);

/* Dùng trong khoảng thời gian hợp lệ. */

(*env)->DeleteGlobalRef(env, globalRef);
~~~

Ví dụ giả định env và someObject hợp lệ. Cần xử lý tình huống NewGlobalRef không thành công và mọi exception theo JNI rules.

Global reference giữ Java object khỏi bị GC thu gom; nếu quên DeleteGlobalRef, ứng dụng có thể rò rỉ heap dù native memory không tăng rõ rệt.

### 14.3. Weak global reference

Weak global reference có semantics khác global reference mạnh. Native code không được giả định referent còn sống; cần dùng đúng JNI API để kiểm tra/tạo reference phù hợp trước khi thao tác.

Một native cache không được phép coi weak reference như raw pointer tồn tại vĩnh viễn.

### 14.4. Local reference trong vòng lặp lớn

Khi native code tạo rất nhiều Java object references trong một vòng lặp mà không trả về Java sớm, local references có thể tích lũy. Có thể dùng DeleteLocalRef hoặc PushLocalFrame/PopLocalFrame phù hợp.

Đây là lỗi thường chỉ xuất hiện khi xử lý batch lớn hoặc stress test, không phải khi gọi native method một lần.

## 15. JNI và Garbage Collector

GC có thể di chuyển Java objects. Native code không được giả định địa chỉ một Java object ổn định chỉ vì đã lấy được jobject.

JNI cung cấp API được định nghĩa cho việc truy cập arrays, strings và các vùng dữ liệu. Các lời gọi như GetByteArrayElements có thể trả con trỏ trực tiếp hoặc bản sao tùy JVM/điều kiện; phải gọi ReleaseByteArrayElements theo hợp đồng API.

### 15.1. GetPrimitiveArrayCritical

Những API Critical có quy tắc rất hạn chế. Khi giữ critical array access, native code không nên thực hiện các thao tác dài, blocking hoặc gọi JNI tùy tiện trái với contract, vì điều đó có thể cản trở GC và gây vấn đề latency.

Đừng dùng Critical API như mẹo zero-copy mặc định cho thao tác I/O kéo dài nhiều giây.

### 15.2. Native code và safepoints

Một native call dài, giữ tài nguyên lâu hoặc không phối hợp với JVM đúng cách có thể ảnh hưởng latency/observability. Không nên suy luận native execution sẽ tự phản hồi Thread.interrupt, shutdown hoặc GC theo cách của một Java blocking API.

Khi migration JDK/GC, nên đo pause times, throughput và native-thread behavior trên workload thực tế.

## 16. Thread native gọi ngược vào JVM

Một native library có thể tạo thread bằng pthreads, Windows threads hoặc thư viện tương đương. Thread đó không tự động có JNIEnv hợp lệ để gọi Java API.

### 16.1. JNIEnv là theo thread

JNIEnv* là interface gắn với thread context. Không cache một JNIEnv* từ Thread A rồi dùng lại trong Thread B.

Nếu native-created thread muốn gọi Java, nó cần có attachment phù hợp qua JavaVM:

~~~c
JavaVM *vm = /* JavaVM đã được cung cấp hợp lệ */;
JNIEnv *env = NULL;

/* Ví dụ khái niệm, cần kiểm tra kết quả và version. */
jint rc = (*vm)->AttachCurrentThread(vm, (void**)&env, NULL);

if (rc == JNI_OK) {
    /* Gọi JNI API bằng env của thread hiện tại. */
    (*vm)->DetachCurrentThread(vm);
}
~~~

Đây là ví dụ về API shape, không phải đoạn C độc lập đã hoàn thiện. Trong implementation thật, cần biết thread có được attach sẵn hay không, xử lý lỗi, pending exceptions và không detach một thread do JVM sở hữu theo cách không hợp lệ.

### 16.2. Những nguyên tắc callback

- Có ownership rõ ràng cho native thread.
- Attach trước khi gọi JNI từ native-created thread.
- Dùng JNIEnv đúng thread.
- Không chuyển local reference không hợp lệ qua thread.
- Dùng global reference có lifetime phù hợp nếu cần.
- Kiểm soát Java exception từ callback.
- Detach thread khi trách nhiệm attach kết thúc.
- Không giữ lock native trong lúc callback Java có thể gọi ngược vào native nếu gây deadlock.

Một callback chạy tốt khi test một luồng có thể deadlock trong production nếu Java callback cố lấy lock đang được native giữ.

## 17. Ngoại lệ Java và lỗi native

Java exceptions và native error codes không tự chuyển đổi hai chiều.

### 17.1. JNI pending exception

Nếu native code gọi một Java method qua JNI và method ném exception, native code cần xử lý trạng thái pending exception phù hợp. Nhiều JNI operations không nên tiếp tục tùy ý khi đang có pending exception.

Có thể dùng ExceptionCheck, ExceptionOccurred, ExceptionClear và các API liên quan theo quy tắc JNI. **Không gọi ExceptionClear rồi bỏ qua lỗi để “cho code chạy tiếp” nếu không có recovery contract**.

### 17.2. Native errors

C APIs thường dùng:

- Return code.
- errno.
- GetLastError trên Windows.
- Error object/struct.
- Thread-local last-error state.
- Exception C++ nội bộ.

Java wrapper phải map chúng sang kiểu kết quả hoặc exception có nghĩa.

Ví dụ:

~~~java
public final class NativeResult {
    public final boolean success;
    public final int errorCode;

    public NativeResult(boolean success, int errorCode) {
        this.success = success;
        this.errorCode = errorCode;
    }
}
~~~

Đây là DTO minh họa. Trong production, cần biết error code thuộc hệ nào, được đọc ở thời điểm nào và có thể bị ghi đè bởi lời gọi native khác hay không.

### 17.3. Không để C++ exception xuyên qua C/JNI boundary

Một C++ exception không nên thoát vô kiểm soát qua ABI C/JNI function. Native wrapper cần catch exception ở biên, giải phóng tài nguyên rồi chuyển thành Java exception/return code theo contract.

Tương tự, JNI code không được giả định JVM sẽ tự dọn dẹp mọi native resource nếu một exception xảy ra giữa chuỗi thao tác.

### 17.4. Cần bảo vệ dữ liệu trước crash

Một native segmentation fault hoặc access violation có thể kết thúc cả JVM process, không giống Java NullPointerException có thể được catch. Vì vậy, với tác vụ native không tin cậy hoặc thư viện có độ ổn định thấp, cân nhắc cô lập trong **tiến trình riêng** và giao tiếp qua IPC/gRPC/message thay vì để nó chạy chung tiến trình Java chính.

## 18. JNA callback và lifetime

JNA cho phép mapping C function pointers thành Java callback trong các tình huống phù hợp. Nhưng callback cũng có lifecycle riêng:

- Native library có giữ function pointer sau khi registration method trả về không?
- Java callback object có được giữ strong reference đủ lâu không?
- Thread gọi callback có do native tạo không?
- Calling convention có khớp không?
- Callback có được phép throw Java exception không và wrapper xử lý ra sao?
- Có thể unregister/cancel callback trong shutdown không?

Nếu Java GC thu hồi callback object trong khi native còn giữ function pointer, việc gọi lại có thể gây lỗi nghiêm trọng. Tương tự, nếu application đóng native context khi callback đang chạy, có thể xảy ra use-after-free.

Một thiết kế thực tế cần method register/unregister rõ ràng, strong reference khi callback còn hoạt động và đồng bộ hóa giữa callback execution với context shutdown.

## 19. Classloader và khả năng nạp lại native library

Java enterprise applications có thể sử dụng nhiều classloader:

~~~text
Bootstrap / Platform
        |
        v
Application loader
        |
      +-+-----------------+
      |                   |
      v                   v
Plugin loader A      Plugin loader B
      |                   |
      v                   v
JNI wrapper A        JNI wrapper B
~~~

Nếu hai classloader cố nạp cùng native library theo cách JVM không cho phép, có thể gặp lỗi kiểu:

~~~text
Native Library ... already loaded in another classloader
~~~

Không nên coi việc copy .so sang hai đường khác nhau là giải pháp chung. Thư viện native có thể chứa global state, singleton handle, native threads hoặc static caches không thiết kế cho hai instances.

### 19.1. Vấn đề khi redeploy WAR/plugin

Khi một web application bị undeploy:

- Classloader Java có thể được giải phóng nếu không còn reference.
- Native code vẫn có thể giữ global JNI references.
- Native thread có thể còn hoạt động.
- Callback có thể trỏ vào classloader cũ.
- Library có thể chưa được unload theo thời điểm mong đợi.

Kết quả là classloader leak hoặc lỗi ở lần redeploy sau.

Nên quản lý explicit lifecycle, native thread shutdown và global refs. Nếu library không hỗ trợ unload/reload an toàn, kiến trúc một process/container cho từng deployment có thể phù hợp hơn.

## 20. Native agent, Java agent và JVMTI

Tên chương là **Agent và mã native**, vì vậy khi điều tra một ứng dụng dùng JNI/JNA cần kiểm kê cả những agent tác động vào JVM.

### 20.1. Java agent

Cơ chế Java Instrumentation dùng:

~~~bash
java -javaagent:/opt/agents/monitor.jar -jar app.jar
~~~

Java agent có thể transform bytecode, append bootstrap search path hoặc sử dụng module access options tùy implementation. Nó không nhất thiết phải có native code, nhưng vẫn có thể phụ thuộc vào JDK internals hoặc công nghệ instrument bytecode.

### 20.2. Native JVMTI agent

Cơ chế native agent có thể dùng:

~~~bash
java -agentpath:/opt/agents/libprofiler.so -jar app.jar
~~~

Hoặc -agentlib với logical library name khi phù hợp.

JVMTI agent dùng những entry point và cơ chế capability/event của JVMTI, khác với một thư viện JNI chỉ export các native methods. Agent phải hỗ trợ JDK target, architecture, platform và JVM implementation.

### 20.3. Những thay đổi có thể làm agent lỗi

- JVMTI capability/event behavior không còn phù hợp với agent.
- JVM instrumentation hoặc class-file version mới.
- Native dependencies và ABI sai.
- Java module encapsulation chặn reflective access của agent.
- Agent được load ở thời điểm khác hoặc qua dynamic attach.
- JDK thay chính sách cảnh báo hoặc quyền native/dynamic agent loading.
- Agent không hỗ trợ virtual threads hoặc cơ chế runtime mới.
- Một agent bị version mismatch với framework/monitoring backend.

Chỉ nâng JAR application mà bỏ qua profiler/APM/security agent là một lỗi phổ biến trong Java migration.

### 20.4. Agent startup phải có kế hoạch rollback

Nếu agent gây crash hoặc làm chậm khởi động JVM, nên có phương án cấu hình để tắt agent và khởi động service ở chế độ fallback khi được chính sách vận hành cho phép.

Không nên gỡ bỏ những security agents bắt buộc mà không có kiểm soát và phê duyệt tương ứng.

## 21. Native access restrictions và JDK hiện đại

Các JDK mới đang tiến hóa cơ chế cảnh báo và hạn chế truy cập native, với mục tiêu làm rõ ứng dụng nào phụ thuộc vào JNI hoặc Foreign Function & Memory API.

Ví dụ trong một số release hiện đại có cơ chế cấu hình **--enable-native-access** cho module được phép thực hiện các restricted native operations, cùng warning/diagnostic hoặc policy về illegal native access theo từng JDK release.

Điều quan trọng:

- Hành vi và phạm vi của những option này **phụ thuộc phiên bản JDK**.
- Không phải mọi JDK phát hành cùng thời điểm đều áp dụng chính sách giống nhau.
- JNA hoặc thư viện JNI có thể cần nâng version để hỗ trợ những thay đổi này.
- Một warning không tự chứng minh ứng dụng đã bị chặn; ngược lại, không có warning cũng không chứng minh compatibility hoàn toàn.
- Không nên vô hiệu hóa tất cả cảnh báo hoặc cấp quyền quá rộng chỉ để lấp lỗi.

Khi nâng tới một JDK mới, cần đọc release notes của **đúng bản JDK đích** và tài liệu của native library/agent. Một thư viện có hỗ trợ JDK 17 không tự động bảo đảm hỗ trợ JDK 25 hoặc mới hơn.

### 21.1. --enable-native-access không sửa lỗi ABI

Nếu nativecalc.so là binary ARM64 còn JVM chạy trên x86-64, flag native access không giúp được.

Nếu C struct layout sai, việc cấp quyền cũng không sửa được memory corruption.

Nếu Java không tìm thấy JNI symbol, phải sửa library name, symbol hoặc native signature.

Cần phân loại quyền native access riêng với tương thích binary/runtime của thư viện.

## 22. Foreign Function & Memory API là lựa chọn hiện đại nào?

Foreign Function & Memory (FFM) API được chuẩn hóa trong Java 22. Nó cung cấp API để mô tả memory segments, layouts và lời gọi foreign functions theo cách tích hợp với Java.

Khác với JNI, FFM có thể giúp nhiều use case gọi C ABI mà không viết JNI glue truyền thống. Một số lợi ích thiết kế:

- Mô tả native memory layout rõ ràng.
- Quản lý lifetime qua abstraction có scope.
- Downcall tới native function bằng method handles.
- Khả năng tạo upcall stub cho callback trong những trường hợp phù hợp.
- Kiểm soát phạm vi lifetime của memory segment.

Tuy nhiên:

- API và mức hỗ trợ phụ thuộc JDK.
- Native access restrictions/policy vẫn cần được tính đến.
- C ABI, struct alignment, pointer semantics và concurrency vẫn quan trọng.
- Chuyển từ JNA/JNI sang FFM có thể là refactor lớn.
- Không phải mọi ứng dụng chạy Java 17 có thể dùng API FFM final của Java 22.

### 22.1. Không ép migration từ JNI/JNA sang FFM trong cùng một bước

Nếu mục tiêu hiện tại là chuyển Java 11 lên 17 hoặc giữ tương thích với nhiều JDK, việc đổi toàn bộ native binding sang FFM có thể vượt phạm vi. Hãy tách:

1. Xác nhận JNI/JNA hiện tại chạy an toàn trên JDK mục tiêu.
2. Nâng dependency và native artifacts.
3. Ổn định contract tests.
4. Đánh giá FFM như một quyết định kiến trúc riêng khi Java baseline cho phép.

JNI vẫn là cơ chế có giá trị cho những tích hợp cần tương tác sâu với Java objects/JVM. JNA vẫn phù hợp trong một số thư viện C ABI; FFM là một lựa chọn, không phải yêu cầu thay thế ngay mọi code legacy.

## 23. Phân phối native binary theo platform

Một ứng dụng cần chạy nhiều môi trường phải có cách chọn binary đúng.

Ví dụ cấu trúc phân phối có thể là:

~~~text
native/
  linux-x86_64/
    libnativecalc.so
  linux-aarch64/
    libnativecalc.so
  windows-x86_64/
    nativecalc.dll
  macos-aarch64/
    libnativecalc.dylib
~~~

Đây là một cấu trúc minh họa, không phải chuẩn đóng gói bắt buộc.

Một số Maven artifacts dùng classifier:

~~~text
nativecalc-1.2.0-linux-x86_64.jar
nativecalc-1.2.0-linux-aarch64.jar
nativecalc-1.2.0-windows-x86_64.jar
~~~

Phần code phân phối cần xác định OS/architecture đáng tin cậy, trích xuất vào đường dẫn có quyền phù hợp, kiểm tra file integrity và tránh race condition khi nhiều tiến trình khởi động.

### 23.1. Không chỉ dựa vào os.name

os.name và os.arch giúp định hướng nhưng đôi khi tên trả về khác kỳ vọng hoặc không đủ phân biệt libc/ABI. Cần xem cả packaging policy và runtime environment thực tế.

### 23.2. Tài nguyên native trong JAR phải được trích xuất

System.loadLibrary không tự mở một arbitrary .so như dynamic library trực tiếp từ bên trong JAR. Nhiều thư viện giải quyết bằng cách extract file sang local filesystem rồi System.load với đường dẫn tuyệt đối.

Điểm rủi ro:

- Thư mục tạm bị mount noexec.
- Không đủ quyền ghi/đọc.
- Bị antivirus hoặc security policy chặn.
- File bị xóa sớm.
- Hai tiến trình cùng extract cùng tên.
- Không xác minh checksum/chữ ký.
- Symlink/path traversal nếu extract resource không an toàn.
- Không dọn tài nguyên sau shutdown.

Trong container có filesystem read-only, cần bố trí thư mục writable/executable hoặc đóng gói native libraries vào image theo cách được kiểm soát.

## 24. Build native library bằng toolchain độc lập

Maven/Gradle có thể điều phối C/C++ build, nhưng maven-compiler-plugin hoặc JavaCompile không tự biên dịch C native code. Native part cần toolchain như gcc/clang/MSVC, CMake hoặc build system tương đương.

Ví dụ workflow:

~~~text
Java source
     |
     v
javac -h -> JNI header
     |
     v
C/C++ source + generated header
     |
     v
Native compiler/linker
     |
     v
.dll / .so / .dylib
     |
     v
Package per OS/architecture
     |
     v
Integration tests on target JDK
~~~

Một project có thể dùng CMake để build native layer, nhưng cần lựa chọn compiler, output library name và flags đúng platform. Không nên coi lệnh build Linux là đủ để phân phối Windows/macOS binaries.

### 24.1. JNI headers theo JDK

jni.h và những platform headers liên quan được cung cấp cùng JDK. Native compiler cần include paths phù hợp với JDK target/build environment.

Có thể build native code với headers của một JDK và chạy trên các JDK khác nếu sử dụng các JNI APIs được hỗ trợ và bảo toàn ABI, nhưng phải test phiên bản thấp nhất và cao nhất được cam kết. Không sử dụng private JVM headers hoặc HotSpot internal structures như API ổn định.

### 24.2. Compiler và linker version cũng cần được pin

Nếu một .so được build với libstdc++ mới hơn runtime production, có thể cần symbol version không tồn tại. Build image và runtime image cần được quản lý cùng compatibility baseline.

Không chỉ pin Java JDK mà bỏ qua:

- gcc/clang/MSVC version.
- glibc/musl baseline.
- C++ standard library.
- OpenSSL/native dependencies.
- Linker flags, visibility, rpath/runpath.
- Target CPU instruction set.
- OS deployment target.

## 25. Công cụ chẩn đoán native library

Những công cụ sau có thể hỗ trợ điều tra. Việc có sẵn của chúng phụ thuộc OS.

### 25.1. Java và runtime

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Xem Java home, architecture, java.library.path và những thuộc tính phù hợp. Không nên in toàn bộ environment chứa secrets vào log công khai.

### 25.2. Kiểm tra file trên Linux

~~~bash
file libnativecalc.so
~~~

Xem metadata architecture/format:

~~~bash
readelf -h libnativecalc.so
~~~

Xem dynamic dependencies:

~~~bash
readelf -d libnativecalc.so
~~~

Xem exported symbols:

~~~bash
nm -D libnativecalc.so
~~~

hoặc:

~~~bash
objdump -T libnativecalc.so
~~~

Những lệnh này có thể giúp tìm JNI symbol hoặc C API symbol bị thiếu. Không phải mọi platform dùng cùng tool và flags.

### 25.3. Kiểm tra dependency runtime

~~~bash
ldd libnativecalc.so
~~~

Trên Linux, ldd có thể cho biết dependency resolution, nhưng cần thận trọng với binary không tin cậy và hành vi của tool. Đối với artifact chưa tin cậy, ưu tiên phân tích tĩnh bằng readelf/objdump hoặc công cụ phù hợp trong môi trường cách ly.

Trên macOS có thể dùng otool; trên Windows dùng dumpbin hoặc công cụ PE tương đương.

### 25.4. JVM fatal error log

Khi JVM crash do native code, JVM thường tạo log như:

~~~text
hs_err_pid12345.log
~~~

Log có thể nêu:

- Problematic native frame.
- JVM/JDK version và build.
- Thread đang crash.
- Loaded native libraries.
- Stack/registers.
- Signal hoặc exception của OS.

Không nên đăng nguyên log lên kênh công khai vì có thể chứa đường dẫn, tham số, hostname hoặc thông tin nhạy cảm. Phân tích cùng native symbols/debug info và crash reproduction.

### 25.5. Không nhầm core dump với Java stack trace

Một SIGSEGV trong native code thường không thể được xử lý bằng cách catch RuntimeException. Có thể cần core dump, minidump, native debugger, AddressSanitizer hoặc các công cụ kiểm tra memory thích hợp.

Trong môi trường production, bật core dumps cần chính sách bảo mật và giới hạn dung lượng.

## 26. Những lỗi JNI/JNA thường gặp

### 26.1. UnsatisfiedLinkError: no ... in java.library.path

Ví dụ:

~~~text
java.lang.UnsatisfiedLinkError:
no nativecalc in java.library.path
~~~

Khả năng:

- Chưa phân phối library.
- Sai logical name.
- Sai đường tìm kiếm.
- Extract bị lỗi.
- Deployment container thiếu file.
- Classloader/load logic không đúng.

Giải pháp: xác định file đã tồn tại chưa, đúng platform chưa, đường nạp thực tế ở đâu. Không vội đặt global PATH/LD_LIBRARY_PATH rộng hơn nếu có thể cấu hình cụ thể.

### 26.2. UnsatisfiedLinkError: native method implementation not found

~~~text
java.lang.UnsatisfiedLinkError:
'long com.example.nativebridge.NativeMath.sum(long, long)'
~~~

Khả năng:

- Không có symbol JNI phù hợp.
- Native method bị đổi tên/package/signature.
- Wrapper dùng RegisterNatives sai.
- Thư viện cũ được load thay vì bản mới.
- Method overload mapping không đúng.

Kiểm tra header đã generate và exported symbols.

### 26.3. Wrong ELF class, invalid image, bad CPU type

Khả năng lớn là sai bitness, architecture hoặc binary format. Cần build/đóng gói đúng platform.

### 26.4. Symbol lookup error hoặc missing native dependency

Thư viện top-level tồn tại nhưng dependency bắc cầu không resolve hoặc ABI version không phù hợp. Kiểm tra shared library dependencies, rpath/runpath và native runtime images.

### 26.5. JNA Function not found

JNA tìm đúng library nhưng function name không được export hoặc có name mangling/calling convention khác. Cần kiểm tra API export của native library và JNA binding declaration.

### 26.6. Crash sau khi gọi function

Có thể do:

- Sai pointer hoặc memory lifetime.
- Sai struct alignment.
- Sai calling convention.
- Java int/long mapping sai.
- Use-after-free, double free.
- Callback object hết lifetime.
- Data race hoặc native library không thread-safe.
- Native exception bị thoát qua ABI boundary.

Đừng xem việc nạp thư viện thành công là bằng chứng ABI đúng.

### 26.7. JVM chỉ crash khi GC hoặc shutdown

Có thể do local/global reference dùng sai, native pointers tới Java objects không hợp lệ, callback còn chạy sau khi đóng context, JNI Critical access hoặc native threads không detach.

### 26.8. Agent chỉ hỏng trên JDK mới

Có thể do JVMTI capabilities, bytecode instrumentation, module access, native access policy hoặc vendor/JDK compatibility. Cần kiểm tra release notes của agent và JDK đích.

## 27. Cách kiểm tra library đúng với JDK mục tiêu

Không nên chỉ gọi một native function đơn giản rồi kết luận toàn bộ integration an toàn. Một bộ test cần bao phủ những biên quan trọng.

### 27.1. Test nạp library

- Đúng OS/CPU/bitness.
- Đúng native dependencies.
- Đúng file permissions và execution policy.
- Đúng load path trong container.
- Không xung đột khi nhiều classloader.
- Không vô tình load bản library cũ từ hệ thống.

### 27.2. Test dữ liệu

- Java int/long với giá trị biên.
- Unsigned/native integer conversion.
- Null pointer và null Java reference.
- Unicode, emoji, ký tự ngoài BMP.
- Chuỗi có dấu null hoặc bytes đặc biệt.
- Struct layout/packing.
- Array/buffer dài và rỗng.
- Negative error codes.
- Những tham số mà native API không hỗ trợ.

### 27.3. Test bộ nhớ

- Repeated allocate/free.
- Double close hoặc close idempotency.
- Call after close phải báo lỗi rõ.
- Native context còn sống trong callback.
- GC stress và reference lifetime.
- Direct buffer lifetime.
- Native memory growth theo thời gian.
- Error path giải phóng resource.

### 27.4. Test concurrency

- Nhiều Java threads gọi cùng native context.
- Native callbacks đồng thời.
- Native-created threads attach/detach.
- Shutdown khi callback đang chạy.
- Cancel/interrupt khi native call block.
- Plugin redeploy/classloader cleanup.
- Thread safety của native library phiên bản mới.

### 27.5. Test vận hành

- Container read-only root filesystem.
- Thư mục tạm noexec.
- Hệ điều hành/CPU khác nhau.
- Debug/monitoring agents cùng hoạt động.
- Security provider/FIPS mode nếu cần.
- Graceful shutdown và restart.
- Upgrade/rollback library artifacts.

## 28. Ma trận tương thích native

Một test matrix mẫu:

| Java runtime | OS/architecture | Native artifact | Kỳ vọng |
|---|---|---|---|
| JDK 17 | Linux x86-64 glibc | linux-x86_64 .so | Baseline |
| JDK 21 | Linux x86-64 glibc | linux-x86_64 .so | Migration target |
| JDK 21 | Linux ARM64 | linux-aarch64 .so | Architecture support |
| JDK 21 | Windows x86-64 | windows-x86_64 .dll | ABI/calling convention |
| JDK 21 | macOS ARM64 | macos-aarch64 .dylib | Packaging/security |
| JDK target | Linux musl | musl-compatible .so | Nếu Alpine được hỗ trợ |
| JDK target | JVM cùng native agent | agent bản tương thích | Observability/instrumentation |

Đây là ma trận minh họa. Phải chọn những phiên bản Java và platform đúng theo support policy của sản phẩm, không tự cam kết những tổ hợp chưa có native binary và test.

### 28.1. Khi chỉ hỗ trợ một platform

Nếu sản phẩm chỉ deploy Linux x86-64 với glibc, có thể không cần xây Windows/macOS binaries. Tuy nhiên, vẫn phải kiểm tra những thay đổi như:

- Container image mới.
- CPU instance types mới.
- glibc và native dependency versions.
- JDK vendor.
- Kernel/OS policies.
- Dynamic loader paths.
- Debug/monitoring agents.

Không có yêu cầu “đa nền tảng” không đồng nghĩa không có ABI risk.

## 29. Chiến lược migration theo pha

### Pha 1 — Kiểm kê native surface

Lập danh sách:

- Java native methods.
- JNA interfaces và loaded library names.
- Native libraries trong JAR.
- System.load/System.loadLibrary usage.
- Java agent và native agent flags.
- JNI_OnLoad và RegisterNatives.
- Java→native và native→Java callbacks.
- Native dependency graph.
- Nền tảng production thực tế.

Một bảng inventory:

| Thành phần | Cơ chế | Native file | Owner | JDK/platform support |
|---|---|---|---|---|
| image-engine | JNI | libimage.so | Vendor A | Cần xác minh |
| win-device | JNA | device.dll | Team B | Windows x86-64 |
| APM profiler | JVMTI agent | libprofiler.so | Vendor C | Cần xác minh |
| crypto-provider | JNI/PKCS#11 | provider.so | Security team | Chính sách riêng |

### Pha 2 — Chốt baseline và artifacts

Ghi:

- JDK cũ và JDK đích.
- JVM vendor/implementation.
- OS, architecture, libc.
- Compiler/linker C/C++.
- Native dependencies.
- Library hashes/versions.
- Java wrapper/JNA version.
- Container base image.
- Native access/agent flags.

### Pha 3 — Nâng bản được vendor hỗ trợ

Ưu tiên các phiên bản JNI/JNA/native agent được nhà cung cấp công bố hỗ trợ JDK và OS mới. Tránh tự patch binary closed-source khi đã có bản chính thức.

Nếu một library không có bản ARM64 hoặc không hỗ trợ JDK mới, cần quyết định thay thế hoặc cô lập trước khi rollout, thay vì chờ tới production mới phát hiện.

### Pha 4 — Giữ Java/native contract ổn định

Không đổi cùng lúc Java native declarations, native ABI, package names và serialization contract trừ khi cần thiết. Nếu buộc đổi ABI, version wrapper/library đồng bộ và bảo vệ consumer cũ qua phát hành có kế hoạch.

### Pha 5 — Xây và đóng gói native binaries

Build cho từng target OS/CPU/libc với toolchain phù hợp; kiểm tra symbol exports và dependency graph; ghi checksum và provenance của artifact.

### Pha 6 — Chạy integration/stress tests

Dùng đúng JDK/container cuối cùng. Test concurrent access, GC, callback, memory lifetime, shutdown và error paths. Với native crash, thu thập fatal error log/core dump theo chính sách bảo mật.

### Pha 7 — Canary và quan sát

Theo dõi:

- Startup load failures.
- Native crashes.
- Memory RSS/native allocation.
- Thread counts.
- Latency của boundary calls.
- JNI/JNA errors.
- GC pauses.
- Agent overhead.
- Resource cleanup.
- Error rate của nghiệp vụ.

### Pha 8 — Rollback thực tế

Một rollback có thể cần quay lại cả Java JAR, native .so/.dll, container image và agent version. Nếu native library viết file/database format mới, phải xét liệu bản cũ đọc lại được không.

Đừng giả định rollback chỉ là thay JDK image. Khi ABI và state format đổi, hai phiên bản có thể không dùng chung trạng thái.

## 30. Ví dụ tổng hợp: chuyển một thư viện JNI từ JDK cũ lên JDK mới

Giả sử hệ thống có:

~~~text
Java application: Java 11
JNI wrapper: native-image-bridge.jar
Native library: libimagebridge.so
OS: Linux x86-64
Container: glibc-based
Agent: native APM profiler
~~~

Mục tiêu: JDK 21, có khả năng chạy trên Linux ARM64 về sau.

### Bước 1 — Kiểm kê API và ABI

Xác định native methods trong JAR; kiểm tra header/signatures, JNI_OnLoad, callback, jlong handles và owner của memory.

### Bước 2 — Kiểm tra native binary

Dùng file/readelf/nm hoặc tool tương ứng để xác định ELF architecture, exported JNI symbols, version dependency C++ và glibc.

### Bước 3 — Xác minh vendor support

Cập nhật JNI wrapper và profiler lên bản hỗ trợ JDK 21. Nếu libimagebridge.so dùng public JNI API ổn định, có thể hoạt động mà không build lại, nhưng vẫn phải thử trên JDK mới.

### Bước 4 — Build và package theo architecture

Nếu cần ARM64, build native library ARM64; không dùng x86-64 .so. Kiểm tra dependency native tương ứng, đặc biệt image processing libraries và CPU instructions.

### Bước 5 — Kiểm thử logic và dữ liệu

Chạy ảnh nhỏ/lớn, data types, Unicode file names, allocation, error paths và Java/native callbacks.

### Bước 6 — Stress test

Chạy nhiều threads và GC dưới tải; theo dõi native RSS, thread count, leaks và crash logs.

### Bước 7 — Test image production

Sử dụng đúng container base image, read-only/noexec policies nếu có, deployment permissions, agent flags và toolchain runtime dependencies.

### Bước 8 — Canary và rollback

Canary một phần traffic, quan sát crash/error/memory. Chuẩn bị rollback đồng bộ Java wrapper, native library và agent, không chỉ JDK.

Trong suốt quy trình, không có bước nào được thay bằng việc chỉ nhìn Maven/Gradle build thành công.

## 31. Các hiểu lầm thường gặp

### “JNI là API chuẩn nên mọi thư viện native cũ chạy trên mọi JDK mới”

Không đúng. JNI cung cấp một interface có cam kết, nhưng binary có thể phụ thuộc private JVM internals, cấu hình security policy, ABI, native dependencies hoặc hành vi runtime khác.

### “JNA không dùng mã native”

Không đúng. JNA runtime dùng thành phần native và gọi native library; nó chỉ giảm nhu cầu viết JNI glue thủ công trong nhiều trường hợp.

### “Java long bằng C long trên mọi hệ điều hành”

Sai. C long thay đổi theo ABI; Java long luôn 64-bit.

### “Thư viện load thành công nghĩa là ABI tương thích”

Sai. Sai struct layout, pointer lifetime hoặc calling convention có thể chỉ gây crash khi gọi một function cụ thể.

### “Đổi java.library.path sẽ sửa mọi UnsatisfiedLinkError”

Không đúng. File có thể sai CPU/OS, thiếu dependencies hoặc thiếu JNI symbol; path không giải quyết những lỗi đó.

### “JNIEnv có thể dùng từ thread bất kỳ”

Sai. JNIEnv gắn với thread context. Native-created threads cần attach phù hợp.

### “GC quản lý luôn native memory”

Không đúng. Native allocations và resource handles thường cần giải phóng theo API native. Global JNI references cũng cần delete đúng lúc.

### “Một Pointer trong JNA có quyền sở hữu memory”

Không phải luôn. Pointer có thể tham chiếu vùng nhớ của thư viện, caller, callback hoặc một object khác.

### “Có thể trộn hai bản native library qua nhiều classloader mà không ảnh hưởng”

Không nên giả định như vậy. JVM load rules, global state và native thread/reference lifetime có thể gây xung đột hoặc leak.

### “Agent là Java JAR nên không liên quan native compatibility”

Không phải mọi agent đều là Java thuần. APM/debugger/profiler có thể dùng JVMTI/JNI hoặc thành phần native đi kèm.

### “--enable-native-access chữa được lỗi thiếu .so”

Không đúng. Native access policy và OS dynamic linker/ABI là các lớp khác nhau.

### “FFM thay thế được mọi JNI code mà không đổi contract”

Không đúng. FFM là cơ chế khác, có API/baseline/lifetime model riêng; một số use case JVM-level vẫn cần JNI/JVMTI.

### “Không có Java exception nghĩa là native call thành công”

Sai. Native code có thể hỏng dữ liệu, làm rò bộ nhớ hoặc gây crash trễ. Phải kiểm tra error codes, invariants và resource state.

## 32. Mẫu hồ sơ kiểm tra khả năng tương thích

~~~text
JAVA APPLICATION
  App/module:
  Current JDK/vendor/build:
  Target JDK/vendor/build:
  Framework:
  Java agent(s):
  Native agent(s):
  Java runtime options:

NATIVE DEPENDENCY
  Library name:
  JNI / JNA / FFM / JVMTI:
  Java wrapper version:
  Native binary version/hash:
  Native build toolchain:
  Required OS:
  Required architecture:
  32/64-bit:
  libc / C++ runtime dependencies:
  External native dependencies:

BINDING CONTRACT
  Java method/interface:
  Native symbol:
  Calling convention:
  Parameter and return types:
  Struct layout/alignment:
  String encoding:
  Error mapping:
  Callback contract:

MEMORY AND THREADING
  Allocation owner:
  Release/free API:
  Native handle lifetime:
  Local/global JNI references:
  Native thread attach/detach:
  Callback lifetime:
  Concurrent use allowed?:
  Shutdown/cleanup path:

LOADING AND PACKAGING
  loadLibrary/load path:
  java.library.path / JNA path:
  Extracted native artifacts:
  Filesystem permissions:
  Classloader behavior:
  Container/base image:
  Code signing/security policy:

VALIDATION
  JVM load:
  Symbol resolution:
  Dependency resolution:
  Boundary numeric values:
  Unicode/string data:
  Struct layout:
  Null/error cases:
  GC/memory stress:
  Concurrent callbacks:
  Shutdown/redeploy:
  Agent compatibility:
  Multi-platform matrix:
  Canary metrics:
  Rollback:

DECISION
  Compatible:
  Vendor upgrade required:
  Rebuild required:
  Platform-specific exception:
  Owner:
  Deadline:
~~~

Hồ sơ tốt phải chỉ ra **artifact nào đã được thử với JDK, OS, architecture và native dependency version nào**, thay vì ghi chung “JNI supported”.

## 33. Tổng kết

Khả năng tương thích native của một ứng dụng Java là một hợp đồng nhiều tầng. JVM có thể giữ nguyên JNI API nhưng ứng dụng vẫn thất bại vì thư viện native sai architecture, C ABI đổi, native dependency thiếu, pointer bị dùng sau khi free hoặc agent chưa hỗ trợ JDK mới.

Những nguyên tắc quan trọng:

1. **Nhận diện đúng cơ chế:** JNI, JNA, FFM, Java agent và JVMTI có phạm vi khác nhau.
2. **Đừng nhầm Java binary compatibility với native ABI compatibility:** Java class file đúng không bảo đảm .so/.dll đúng.
3. **Giữ chính xác types và layouts:** jlong, C long, pointer width, struct packing, calling convention và encoding cần được xác nhận.
4. **Định nghĩa ownership:** memory, handles, JNI references, callback và thread phải có lifecycle rõ ràng.
5. **Kiểm tra toàn bộ đường load:** file, CPU/OS, libc, native dependencies, symbols, classloader và permissions.
6. **Nâng cả agent và wrapper:** không chỉ application JAR, mà cả JNA runtime, JNI libraries, APM/JVMTI agents.
7. **Test trên artifact và runtime thật:** dùng đúng JDK, container, OS/architecture cùng kiểm thử concurrency/GC/shutdown.
8. **Triển khai có rollback đồng bộ:** Java bytecode, native binary, base image và agent versions có thể phải đi cùng nhau.

Một migration tốt không đơn giản là JVM đã load thành công thư viện native. Nó phải chứng minh ứng dụng vẫn trao đổi dữ liệu đúng, không vi phạm ABI, không rò rỉ tài nguyên, không crash khi tải lớn và có thể vận hành an toàn trong toàn bộ những môi trường production được cam kết hỗ trợ.

