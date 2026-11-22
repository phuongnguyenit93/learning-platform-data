# Kiến trúc x86-64, AArch64 và ABI của hệ điều hành

## 1. Tại sao Java migration phải quan tâm CPU và ABI?

Một trong những ưu điểm của Java là bytecode có thể chạy trên nhiều hệ điều hành và kiến trúc CPU khi có JVM tương thích. Tuy nhiên, cam kết này **không tự động áp dụng cho mã native** được nạp bởi JNI, JNA, Foreign Function & Memory API, agent JVMTI hoặc thư viện phụ trợ.

Trong **Java Advance Compatibility Migration**, một ứng dụng có thể chuyển từ máy chủ Linux x86-64 sang Linux AArch64, chuyển từ Windows sang Linux container, chuyển base image từ glibc sang musl, hoặc dùng Apple Silicon để phát triển thay cho máy Intel. Khi ấy:

- JAR chứa bytecode Java vẫn có thể tải và chạy bình thường.
- JDK cần có bản phân phối đúng hệ điều hành và kiến trúc.
- Thư viện native như .so, .dll hoặc .dylib phải được biên dịch phù hợp **đúng kiến trúc và ABI**.
- Native agent, thư viện mã hóa, thư viện nén, JNI bindings, database driver native và các dependency bắc cầu có thể là nguyên nhân gây lỗi.
- Các struct, kiểu dữ liệu C, calling convention và cách liên kết động có thể khác nhau giữa các nền tảng dù đều được gọi là “64-bit”.

Ví dụ, một thư viện JNI xây dựng cho Linux x86-64 không thể được nạp trực tiếp bởi JVM Linux AArch64. Tương tự, một DLL Windows x86-64 không thể được nạp bởi tiến trình Java Linux x86-64 chỉ vì cả hai đều chạy trên CPU x86-64.

Bài học hướng đến khả năng:

1. Phân biệt kiến trúc tập lệnh (ISA), hệ điều hành, định dạng binary và ABI.
2. So sánh x86-64 với AArch64 ở góc nhìn native Java.
3. Hiểu các ràng buộc calling convention, data model, dynamic linking, libc và toolchain.
4. Xây dựng JNI/native library và đóng gói artifact cho từng tổ hợp OS/architecture.
5. Kiểm tra JNA, FFM API, JVMTI agent, native image và dependency có mã native.
6. Thiết kế CI matrix, kiểm thử khả năng nạp và chạy native code thực sự trên nền tảng mục tiêu.
7. Chẩn đoán lỗi UnsatisfiedLinkError, sai kiến trúc, thiếu symbol và không tương thích hệ điều hành.

## 2. Bốn khái niệm nền tảng không được đồng nhất

### 2.1. ISA: tập lệnh của CPU

ISA (Instruction Set Architecture) quy định tập lệnh, thanh ghi và những đặc điểm cấp kiến trúc mà mã máy dùng.

Hai ISA quan trọng khi vận hành Java hiện đại:

- **x86-64**: kiến trúc 64-bit mở rộng từ x86; còn được gọi là AMD64, Intel 64 hoặc x64 trong nhiều tài liệu.
- **AArch64**: trạng thái thực thi 64-bit của kiến trúc Arm; thường được gọi là arm64.

Đều là CPU 64-bit không có nghĩa mã máy dùng chung. File chứa lệnh x86-64 không trở thành file AArch64 nếu chỉ đổi phần mở rộng, tên thư mục hay compiler flag của ứng dụng Java.

### 2.2. Operating system

Hệ điều hành cung cấp cơ chế tạo tiến trình, virtual memory, system calls, dynamic loader, file permissions, signals và các API nền tảng.

Ví dụ:

- Linux x86-64.
- Linux AArch64.
- Windows x86-64.
- Windows on Arm64.
- macOS x86-64.
- macOS arm64.

Ngay cả trên cùng ISA, Windows, Linux và macOS không có chung toàn bộ binary interface. Một .so Linux không được coi là tương thích với macOS chỉ vì cả hai chạy CPU x86-64.

### 2.3. ABI: hợp đồng ở cấp nhị phân

ABI (Application Binary Interface) là tập quy tắc để các thành phần mã máy đã biên dịch giao tiếp với nhau. Tùy nền tảng, ABI bao gồm:

- Calling convention: truyền đối số và nhận giá trị trả về.
- Cách dùng register và stack, stack alignment và register nào bên gọi/bên được gọi phải bảo toàn.
- Kích thước, alignment và layout của các kiểu dữ liệu/struct.
- Symbol names, name mangling và cách xuất/nhập symbol.
- Định dạng object/shared library và cơ chế linking.
- Exception unwinding, thread-local storage và một phần runtime convention.
- Tương tác với thư viện hệ thống như C runtime, libstdc++ hoặc Windows runtime libraries.

ABI khác API. Một hàm C có cùng prototype trong header nhưng được biên dịch cho ABI khác có thể không gọi được hoặc đọc sai đối số. Ngược lại, các hàm Java public giống nhau không chứng minh lớp JNI phía dưới tương thích giữa Linux x86-64 và Windows x64.

### 2.4. Binary format và loader

| Nền tảng | Định dạng native phổ biến | Thư viện chia sẻ | Công cụ kiểm tra thường dùng |
|---|---|---|---|
| Linux x86-64/AArch64 | ELF | .so | file, readelf, ldd, objdump |
| Windows x64/Arm64 | PE/COFF | .dll | dumpbin, sigcheck hoặc công cụ PE phù hợp |
| macOS x86-64/arm64 | Mach-O | .dylib / framework | file, otool, lipo |

Tên đuôi file chỉ là tín hiệu ban đầu. Loader thực tế cần định dạng nhị phân, kiến trúc, dependency và các ràng buộc an toàn phù hợp.

## 3. So sánh x86-64 và AArch64 trong môi trường Java

| Đặc tính | x86-64 | AArch64 |
|---|---|---|
| Tên thường gặp | amd64, x86_64, x64 | aarch64, arm64 |
| Tập lệnh máy | Họ x86-64 | Họ Arm 64-bit |
| Register và calling convention | Do ABI OS quy định, thường dùng các register x86-64 | Do ABI OS quy định, thường dùng x0–x7 cho đối số nguyên/pointer ở nhiều ABI |
| Vector/SIMD | SSE/AVX và các extension tùy CPU | NEON/Advanced SIMD; extension như SVE tùy CPU |
| Bản phân phối JDK | JVM build cho OS + x86-64 | JVM build cho OS + AArch64 |
| Thư viện JNI | Phải là binary x86-64 cùng OS ABI | Phải là binary AArch64 cùng OS ABI |
| Java bytecode | Có thể dùng chung với JVM phù hợp | Có thể dùng chung với JVM phù hợp |

Java primitive types như int, long, double có kích thước được ngôn ngữ quy định và nhất quán giữa hai kiến trúc. Tuy nhiên, **C long, pointer, struct padding, alignment và cách truyền đối số ở phía native** phụ thuộc platform ABI.

Không nên chuyển đổi kiểu Java long thành C long theo thói quen mà không kiểm tra data model của hệ điều hành.

### 3.1. CPU architecture không phải Java language level

Các tổ hợp có thể tồn tại đồng thời:

~~~text
JDK 21 / Linux x86-64
JDK 21 / Linux AArch64
JDK 17 / Windows x64
JDK 21 / macOS arm64
~~~

Java class file có target Java 17 không gắn cố định với x86-64; JVM phù hợp ở AArch64 cũng có thể chạy bytecode đó. Nhưng nếu cùng JAR đóng gói thư viện JNI riêng cho x86-64 mà không có bản AArch64, ứng dụng có thể lỗi khi đến chức năng native.

### 3.2. Tối ưu hóa CPU có thể là ràng buộc bổ sung

Ngay trong cùng kiến trúc x86-64, binary native xây dựng với tập lệnh AVX/AVX2/AVX-512 hoặc mức x86-64 microarchitecture cao hơn có thể không chạy trên CPU đời cũ. Ở AArch64, các extension tùy chọn cũng không phải luôn có mặt.

Như vậy, compatibility gồm:

1. Đúng ISA cơ bản.
2. Đúng OS ABI.
3. Đúng baseline CPU features.
4. Đúng libc/runtime dependencies.
5. Đúng JDK/JNI/agent contract.

Một library có file ELF x86-64 đúng định dạng nhưng yêu cầu instruction extension mà CPU không hỗ trợ có thể gặp SIGILL/illegal instruction khi thực thi.

## 4. ABI khác nhau ngay trên cùng CPU x86-64

Một ví dụ quan trọng là **System V AMD64 ABI** trên các hệ Unix-like như Linux so với **Microsoft x64 calling convention** trên Windows. Dù cùng chạy CPU x86-64, quy tắc gọi hàm native khác nhau.

### 4.1. Calling convention: truyền đối số và kết quả

Một số quy ước phổ biến cho đối số kiểu integer/pointer:

| Môi trường | Các register đầu tiên thường dùng cho đối số integer/pointer |
|---|---|
| Linux x86-64 theo System V AMD64 | rdi, rsi, rdx, rcx, r8, r9 |
| Windows x64 theo Microsoft x64 ABI | rcx, rdx, r8, r9 |
| Linux AArch64 theo AAPCS64 | x0 đến x7 |

Đây là **tóm tắt đơn giản**, không phải mô tả đầy đủ ABI. Đối số floating point/vector, varargs, struct return, shadow space, stack alignment và những trường hợp đặc biệt có quy tắc riêng.

Windows x64 còn yêu cầu caller chuẩn bị vùng home/shadow space theo calling convention; System V AMD64 và Windows x64 cũng có khác biệt về quản lý stack. Không nên tự gọi một function pointer native bằng assumption của ABI khác.

### 4.2. AArch64 cũng có nhiều OS ABI

Không phải mọi hệ điều hành dùng AArch64 đều có ABI giống hệt nhau. Linux AArch64 thường tuân theo conventions của AAPCS64 cho user space; Windows Arm64 và Darwin/macOS arm64 có các yêu cầu ABI/runtime bổ sung hoặc khác biệt ở những trường hợp như varargs, stack layout, symbol handling và linkage.

Vì vậy:

> “Tôi đã compile .so cho arm64 trên Linux” không có nghĩa binary đó trở thành .dylib chạy trên macOS Apple Silicon hoặc DLL chạy trên Windows on Arm.

Với JNI/JNA/FFM, hãy dùng compiler và target triple thích hợp cho **từng OS/architecture**, kiểm tra tài liệu ABI của đúng nền tảng khi bind struct, variadic function hoặc custom calling convention.

### 4.3. Không đoán ABI từ tên x64/arm64

Một file native được build cho:

~~~text
linux-x86_64
windows-x86_64
macos-x86_64
linux-aarch64
windows-aarch64
macos-aarch64
~~~

cần được coi là những biến thể khác nhau trong quy trình packaging, dù một số platform sử dụng thuật ngữ tương tự cho kiến trúc.

## 5. Data model: LP64 và LLP64

Một nguồn lỗi native rất khó phát hiện là giả định “64-bit thì C long luôn có 64 bit”. Điều này **không đúng trên mọi hệ điều hành**.

Hai data model thường gặp:

| Kiểu C | LP64 (phổ biến Linux/macOS 64-bit) | LLP64 (Windows 64-bit) |
|---|---:|---:|
| char | 8 bit | 8 bit |
| short | 16 bit | 16 bit |
| int | 32 bit | 32 bit |
| long | 64 bit | 32 bit |
| long long | 64 bit | 64 bit |
| pointer | 64 bit | 64 bit |

Bảng mô tả các ABI thường gặp, không thay thế tài liệu compiler/platform trong trường hợp đặc thù. Với Java, long luôn là signed 64-bit, không tùy hệ điều hành.

### 5.1. Lỗi mapping Java long sang C long

Java:

~~~java
public static native long countRecords();
~~~

Trong JNI, kiểu trả về tương ứng là **jlong**, không nên dùng C long một cách không kiểm chứng:

~~~c
#include <jni.h>

JNIEXPORT jlong JNICALL
Java_com_example_NativeCounter_countRecords(JNIEnv *env, jclass clazz) {
    (void)env;
    (void)clazz;
    return (jlong)1234567890123LL;
}
~~~

JNI định nghĩa các kiểu cố định như jint và jlong theo hợp đồng JNI. Nếu library có API C riêng dùng long, cần xác định mức width và signedness thật của long ở ABI đích trước khi chuyển sang jlong.

### 5.2. C struct layout và padding

Ví dụ một struct:

~~~c
struct Record {
    int id;
    long timestamp;
    void *payload;
};
~~~

Kích thước và offset trường có thể khác nhau giữa LP64 và LLP64 vì C long và alignment. Nếu Java dùng ByteBuffer/MemorySegment để diễn giải struct theo offset hard-coded lấy từ Linux rồi chạy trên Windows, dữ liệu có thể bị đọc sai dù cả hai đều 64-bit.

Hướng xử lý:

- Dùng kiểu C fixed-width như int32_t, int64_t khi giao diện C thực sự yêu cầu độ rộng cố định.
- Dùng size_t và intptr_t khi biểu diễn kích thước, địa chỉ hoặc pointer-sized value; không tự đồng nhất size_t với Java int.
- Chú ý struct padding, packing pragmas, alignment, nested structs, union và bit-field.
- Xác định layout bằng C headers, compiler target và phương pháp binding phù hợp.
- Không serialize struct memory layout thẳng thành file/network format trừ khi protocol quy định đầy đủ layout và byte order.

### 5.3. Endianness không nên bị hard-code

x86-64 thường vận hành little-endian. Nhiều môi trường AArch64 hiện đại cũng dùng little-endian, nhưng code trao đổi dữ liệu không nên ngầm lấy endian của host làm wire format.

Ví dụ với ByteBuffer:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.order(ByteOrder.LITTLE_ENDIAN); // Wire format được định nghĩa là little-endian.
buffer.putLong(42L);
~~~

Nếu giao thức yêu cầu network byte order/big-endian, hãy đặt rõ ByteOrder.BIG_ENDIAN. Mục tiêu là làm rõ hợp đồng dữ liệu, không đoán từ kiến trúc đang chạy.

## 6. JNI là cầu nối Java/native, không phải bộ chuyển ABI tự động

JNI (Java Native Interface) chuẩn hóa cách Java gọi native method và cách native code tương tác với JVM. JNI giúp giữ giao diện Java tương đối ổn định giữa JVM implementations, nhưng **thư viện native vẫn phải được biên dịch cho OS, CPU và ABI đích**.

Ví dụ file Java:

~~~java
package com.example;

public final class NativeMath {
    static {
        System.loadLibrary("sample_native");
    }

    private NativeMath() {
    }

    public static native int add(int left, int right);

    public static void main(String[] args) {
        System.out.println(add(2, 3));
    }
}
~~~

Java sử dụng tên logic sample_native, để JVM tìm thư viện theo quy tắc load native library trên nền tảng tương ứng.

File C triển khai:

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL
Java_com_example_NativeMath_add(JNIEnv *env,
                                jclass clazz,
                                jint left,
                                jint right) {
    (void)env;
    (void)clazz;
    return left + right;
}
~~~

Vì method là static, đối số thứ hai nhận jclass; với instance native method, đối số tương ứng là jobject. Cần dùng JNIEXPORT/JNICALL và header jni.h đúng theo JNI contract; không tự đặt calling convention bằng assumption của Linux hoặc Windows.

### 6.1. Sinh header bằng javac -h

Với source nói trên, có thể tạo header JNI bằng compiler Java:

~~~bash
javac -h native -d classes src/com/example/NativeMath.java
~~~

Đường dẫn giả định source lưu ở src/com/example/NativeMath.java. Header được sinh giúp tránh tự ghi nhầm tên symbol, kiểu JNI và signature đặc biệt khi code phức tạp.

### 6.2. Build Linux native library

Ví dụ minh họa trên Linux có gcc, JDK và header đúng architecture:

~~~bash
gcc -fPIC -shared \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/linux" \
    -o libsample_native.so \
    native/sample_native.c
~~~

Đây là ví dụ build một C JNI library đơn giản. Nếu có source C++ hoặc thư viện hệ thống khác, cần compiler/linker flags và dependency bổ sung. Compiler đang dùng phải tạo ELF với đúng architecture và ABI của Linux đích; chạy lệnh trên host x86-64 không tự tạo binary AArch64.

### 6.3. Build macOS native library

Ví dụ trên macOS với clang:

~~~bash
clang -dynamiclib \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/darwin" \
    -o libsample_native.dylib \
    native/sample_native.c
~~~

Nếu cần một architecture cụ thể có thể dùng cấu hình target/arch tương ứng do Apple toolchain hỗ trợ. Với Universal binary, các slice phải được build đúng rồi kết hợp bằng toolchain phù hợp; không thể chỉ đổi tên file x86-64 thành arm64.

### 6.4. Build Windows DLL

Trên Windows cần compiler/toolchain sinh PE/COFF DLL đúng target, ví dụ MSVC hoặc một toolchain MinGW phù hợp với dependency được chọn. Cần include jni.h và header phần platform win32 của JDK, xuất JNI symbols đúng cách và kiểm tra runtime DLL dependencies.

Không dùng gcc Linux build .so rồi đổi tên thành .dll. DLL phụ thuộc định dạng PE/COFF, Windows ABI và Windows loader; tên file không tạo ra những đặc điểm đó.

### 6.5. Chạy thử Java + native library

Một ví dụ Linux sau khi compile class và native library:

~~~bash
java -Djava.library.path=. -cp classes com.example.NativeMath
~~~

Với library tương ứng, kết quả dự kiến là 5. Trong ứng dụng thật có thể dùng System.load với đường dẫn tuyệt đối đến artifact được xác minh, hoặc load qua cơ chế packaging của framework. Tránh dùng các đường dẫn writable không tin cậy để nạp arbitrary library.

Điểm quan trọng: thành công của javac không chứng minh thư viện .so/.dll/.dylib có thể nạp; cần thực thi một native method trên JVM có đúng OS và architecture.

## 7. JNI function names, C++ và binary linkage

JNI sử dụng cơ chế native method resolution theo convention hoặc RegisterNatives. Với C++, cần bảo đảm JNI entry points được xuất theo đúng tên/calling convention; sử dụng header được javac sinh giúp hạn chế sai sót.

Ví dụ triển khai C++:

~~~cpp
#include <jni.h>

extern "C" JNIEXPORT jint JNICALL
Java_com_example_NativeMath_add(JNIEnv *env,
                                jclass clazz,
                                jint left,
                                jint right) {
    (void)env;
    (void)clazz;
    return left + right;
}
~~~

extern "C" giúp tránh C++ name mangling ở symbol JNI được export. Tuy nhiên, trong nhiều header JNI do javac sinh, phần extern "C" đã được xử lý theo macro/khuôn khai báo tương ứng; cần triển khai nhất quán với header.

### 7.1. C++ ABI phức tạp hơn C ABI

Không nên coi C++ class, std::string, std::vector hoặc exception type là hợp đồng nhị phân bền vững giữa:

- Compiler vendor khác nhau.
- Version libstdc++ khác nhau.
- MSVC và các toolchain khác trên Windows.
- Các build flags ảnh hưởng ABI.
- Các nền tảng OS/architecture khác nhau.

Một giải pháp thực dụng là dùng **C-compatible API** ổn định tại boundary JNI/JNA/FFM, với kiểu cố định và ownership rõ ràng, còn C++ implementation nằm phía sau adapter.

Ví dụ interface C để tránh xuất trực tiếp std::string:

~~~c
#include <stdint.h>
#include <stddef.h>

typedef struct native_context native_context;

native_context *native_create(void);
int32_t native_process(native_context *context,
                       const uint8_t *input,
                       size_t input_length);
void native_destroy(native_context *context);
~~~

Giao diện trên vẫn cần quy định thêm ownership, thread safety, error codes và cách build cho từng ABI. Nó chỉ minh họa việc không đưa class C++ implementation vào binary boundary.

### 7.2. Ngoại lệ và lỗi native

Không ném trực tiếp C++ exception xuyên JNI ABI boundary vào JVM. Native code cần bắt lỗi ở phía C++ và chuyển thành lỗi Java theo JNI, hoặc trả error codes để lớp Java xử lý.

Nếu native method giữ pointer để dùng về sau:

- Xác định bên nào cấp phát và giải phóng.
- Không lưu JNI local reference ngoài thời gian sống của nó.
- Sử dụng global reference theo đúng contract khi cần giữ Java object lâu hơn call.
- Không dùng raw address đã được free.
- Kiểm tra concurrency và reentrancy.

Sai sót ở đây có thể gây crash JVM hoặc corrupt memory, khác hẳn Java exception thông thường.

## 8. JNA và FFM API cũng chịu ràng buộc ABI

### 8.1. JNA

Java Native Access (JNA) cho phép gọi native library thông qua mapping interface/structure mà không luôn cần tự viết JNI wrapper cho mỗi function. Nhưng JNA **không** biến DLL Windows thành .so Linux và không tự sửa struct layout.

Khi sử dụng JNA:

- Kiểm tra version JNA hỗ trợ JDK, OS và CPU mục tiêu.
- Xem dependency native bootstrap của chính JNA.
- Map integer width, long, size_t, pointer, wchar_t và struct alignment đúng platform.
- Xác định calling convention của thư viện C, đặc biệt khi hỗ trợ Windows.
- Cẩn thận với callback từ native sang Java và vòng đời memory.

### 8.2. Foreign Function & Memory API

Ở các phiên bản JDK có Foreign Function & Memory API được hỗ trợ, ứng dụng có thể dùng native linker, memory layout và memory segment để truy cập native code mà không viết JNI binding theo cách truyền thống cho mọi trường hợp.

FFM không loại bỏ OS ABI. Những việc vẫn phải xác định:

- Hàm native và symbol có tồn tại trong shared library của platform không.
- Calling convention do native linker của JDK và ABI đích áp dụng.
- C struct, union, array, alignment, pointer và giá trị return.
- Memory segment lifetime và ownership.
- Thread access, upcall/downcall và tính an toàn của callback.
- Native access policy và các điều kiện kích hoạt theo JDK release đang dùng.

Ví dụ C header dùng long hoặc một struct C không có layout như nhau trên LP64 và LLP64; FFM binding phải khai báo layout phù hợp target chứ không hard-code giả định Linux rồi dùng trên Windows.

Khi migration FFM, phải kiểm tra version JDK vì mức ổn định API, tên class và native-access restrictions đã phát triển qua các release. Không sao chép code FFM preview/incubator của JDK cũ vào JDK mục tiêu mà không điều chỉnh.

### 8.3. Khi nào chọn JNI, JNA hoặc FFM?

| Cơ chế | Ưu điểm thường gặp | Điều cần thận trọng |
|---|---|---|
| JNI | Hỗ trợ binding sâu với JVM, interface lâu đời và kiểm soát native wrapper. | C/C++ bridge, toolchain theo platform, quản lý tham chiếu JNI và crash memory. |
| JNA | Tiện để gọi API của thư viện native có C ABI mà không viết wrapper JNI cho từng hàm. | Runtime phụ trợ, mapping ABI/struct/callback và platform support. |
| FFM | Mô hình native linker/memory layout do JDK cung cấp ở các release phù hợp. | JDK version, native-access policy, layout/ownership và ABI portability. |

Không có lựa chọn nào làm mã máy native trở thành một artifact portable giữa x86-64 và AArch64. Dù chọn cơ chế nào, cần build/test binary cho từng target OS/architecture.

## 9. Native agent: JVMTI khác với Java instrumentation agent

Trong chương **Agent và mã native**, cần phân biệt:

**Java agent**: thường được đóng gói thành JAR và dùng Java Instrumentation API qua tùy chọn như -javaagent. Phần bytecode Java có tính portability theo JDK target, nhưng agent có thể kéo native dependency hoặc bytecode library không hỗ trợ JDK mới.

**Native JVMTI agent**: được build thành .so/.dll/.dylib và nạp bởi JVM qua -agentlib hoặc -agentpath theo cơ chế JVM Tool Interface.

Ví dụ:

~~~bash
java -agentpath:/opt/agents/libobserver.so -jar app.jar
~~~

Đường dẫn trên chỉ minh họa cho Linux; trên Windows/macOS cần native artifact đúng OS và architecture. Nếu một agent build Linux x86-64 được đưa nguyên vào image Linux AArch64, JVM không thể nạp nó đúng cách.

### 9.1. Ngoài ISA còn phải tương thích JVMTI/JDK

Native agent cần kiểm tra:

- JVMTI version/capabilities mà JDK đích cung cấp.
- Các callbacks, event và lifecycle gắn với agent.
- JDK startup options và các thay đổi về agent loading policy.
- Tương thích với GC, thread model, virtual threads khi ứng dụng dùng.
- Các thư viện phụ thuộc của agent và yêu cầu libc.
- Khả năng xử lý đúng class-file version được instrument.
- Tính an toàn với dynamic attach, shutdown và agent unload theo contract.

Một agent có binary đúng AArch64 vẫn có thể không tương thích với JDK đích nếu dùng JVMTI features/behavior ngoài phạm vi được hỗ trợ.

### 9.2. Startup agent và dynamic attach

Không nên giả định startup agent và dynamic attach có cùng điều kiện trên mọi JDK và môi trường bảo mật. Một số runtime/JDK release có chính sách hoặc cảnh báo riêng về nạp agent động.

Trong migration cần test:

1. Khởi động khi agent được nạp từ đầu.
2. Attach động nếu đó là tính năng được sản phẩm cam kết và runtime cho phép.
3. Khi agent không có mặt hoặc bị chặn, ứng dụng fail theo chính sách nào?
4. Memory leak, deadlock và crash trong luồng profiling/instrumentation.
5. Tác động hiệu năng khi chạy trên x86-64 và AArch64.

Nếu agent là công cụ quan sát tùy chọn, cần xác định ứng dụng có được tiếp tục chạy khi agent lỗi hay không. Nếu agent là thành phần bảo mật bắt buộc, fail-open có thể không phù hợp.

## 10. Linux: ELF, glibc, musl và dynamic loader

Trên Linux, chỉ có đúng CPU architecture vẫn chưa chắc load được native library. Runtime còn phụ thuộc vào:

- ELF machine architecture.
- Dynamic loader và interpreter phù hợp.
- C runtime library (thường glibc hoặc musl).
- Version symbols của glibc/libstdc++ và các dependency động.
- RPATH/RUNPATH, LD_LIBRARY_PATH và vị trí file.
- File permissions, mount options và chính sách bảo mật.

### 10.1. glibc và musl

Một tình huống thường gặp là native library được build trong môi trường Linux dùng glibc, nhưng container production dùng Alpine Linux với musl libc. Hai hệ libc không mặc nhiên tương thích nhị phân.

Ví dụ:

~~~text
Build environment : Linux x86-64 / glibc
Native artifact   : libexample.so (glibc-linked)
Runtime image     : Linux x86-64 / Alpine musl
Result            : Có thể thiếu dynamic loader hoặc thư viện/symbol
~~~

Hướng xử lý:

1. Chọn base image và runtime libc theo platform policy.
2. Build một biến thể native phù hợp musl nếu muốn hỗ trợ Alpine.
3. Hoặc dùng base image glibc tương thích nếu yêu cầu cho phép.
4. Kiểm tra native dependencies ngay trong container thực tế.

Không mặc định “Linux x86-64” là một nhãn artifact đủ chi tiết nếu ứng dụng dùng native library liên kết động với libc.

### 10.2. Versioned symbols

Một binary build trên distro quá mới có thể phụ thuộc symbol glibc version chưa có trên distro cũ. Triệu chứng:

~~~text
version 'GLIBC_2.xx' not found
~~~

Đây là thông báo minh họa; số version thực tế phải lấy từ binary và môi trường. Khi cần chạy trên nhiều distro, chọn build baseline đủ cũ theo support matrix hoặc đóng gói runtime phù hợp, không chỉ build trên distro mới nhất.

### 10.3. Công cụ chẩn đoán ELF

Trên môi trường Linux có các công cụ tương ứng:

~~~bash
uname -m
file libexample.so
readelf -h libexample.so
readelf -d libexample.so
readelf -Ws libexample.so
ldd libexample.so
~~~

Ý nghĩa:

- uname -m: kiến trúc kernel/máy được báo cáo; không nên dùng một mình để suy ra architecture của tiến trình Java khi có emulation.
- file/readelf -h: loại ELF và machine target.
- readelf -d: dynamic dependencies và metadata.
- readelf -Ws: exported/imported symbols.
- ldd: dependency resolution trong môi trường hiện tại.

Không chạy ldd trên binary không tin cậy trong môi trường đặc quyền; với artifact chưa tin cậy, ưu tiên phân tích tĩnh bằng readelf/objdump và thực hiện kiểm chứng trong sandbox cô lập.

### 10.4. RPATH/RUNPATH và vị trí thư viện

Một .so có thể được nạp nhưng phụ thuộc .so khác không được loader tìm thấy. Đường tìm kiếm chịu ảnh hưởng của ELF metadata, loader policy và biến môi trường.

Đừng giải quyết mọi lỗi bằng cách thêm thư mục bất kỳ vào LD_LIBRARY_PATH, đặc biệt thư mục user-writable. Khi thiết kế production image:

- Dùng đường dẫn kiểm soát.
- Đóng gói dependency cùng artifact theo policy.
- Xác định RPATH/RUNPATH khi cần.
- Không chấp nhận native binary từ thư mục writable bởi đối tượng không tin cậy.

## 11. Windows: PE/COFF, x64/Arm64 và runtime DLL

Trên Windows, native library thường là DLL định dạng PE/COFF. Cần phân biệt:

- Windows x64 process.
- Windows Arm64 process.
- Windows on Arm chạy ứng dụng x64 trong chế độ emulation khi hệ thống hỗ trợ.

Native DLL phải tương thích với **architecture của tiến trình Java đang chạy**, không chỉ CPU vật lý của máy. Nếu Windows Arm64 đang chạy JVM x64 thông qua emulation, DLL native cần tương thích x64 với tiến trình đó; một DLL Arm64 không thể được trộn tùy ý vào cùng JVM x64.

### 11.1. Runtime và toolchain

Kiểm tra:

- DLL machine type: AMD64, ARM64 hoặc mục tiêu khác.
- Phần mềm được build bằng MSVC hay toolchain khác và runtime dependencies đi kèm.
- Windows C runtime/UCRT và những runtime DLL yêu cầu.
- Exported symbols, calling convention và header.
- DLL search path, security policy và code signing khi áp dụng.

Các công cụ như dumpbin /headers và dumpbin /dependents có thể giúp xem metadata/dependencies khi Visual Studio build tools có sẵn.

### 11.2. LP64 và LLP64 tác động trực tiếp

Windows x64/Arm64 thường dùng LLP64: C long là 32-bit, pointer 64-bit. Code JNI/FFM/JNA nào coi C long là 64-bit do “chạy Windows 64-bit” có thể đọc/ghi sai dữ liệu.

Với native interface cần lưu timestamp, count hoặc ID 64-bit, nên dùng các kiểu đã xác định độ rộng ở C boundary thay vì dựa vào long theo platform.

### 11.3. DLL search path là vấn đề bảo mật

Một ứng dụng có thể load nhầm DLL cùng tên từ thư mục không đáng tin cậy nếu search path không được kiểm soát. Không đưa thư mục writable tùy ý lên đầu đường tìm kiếm chỉ để khắc phục UnsatisfiedLinkError.

Tốt hơn, chọn artifact đã xác minh, chỉ rõ địa điểm đóng gói và kiểm tra dependencies của chính DLL.

## 12. macOS: Mach-O, Apple Silicon và Universal binaries

Trên macOS, một tiến trình Java có thể chạy ở x86-64 hoặc arm64 tùy bản JDK và cách khởi chạy. Trên Apple Silicon, Rosetta 2 có thể cho phép một số ứng dụng Intel x86-64 chạy qua translation, nhưng không làm hai loại native binary có thể trộn trong cùng process một cách tùy ý.

### 12.1. Native binary phải khớp với process architecture

Ví dụ:

~~~text
Mac Apple Silicon host
  ├─ JDK arm64 process  → load arm64 dylib/slice
  └─ JDK x86-64 dưới Rosetta → load x86-64 dylib/slice
~~~

Nếu JDK process là arm64, một .dylib chỉ có x86-64 slice sẽ không được load trực tiếp như arm64. Không nên lấy uname -m làm bằng chứng duy nhất, vì phải xác nhận chính architecture của JVM process.

### 12.2. Universal 2 / fat Mach-O

Một Mach-O Universal binary có thể chứa nhiều architecture slices. Có thể dùng:

~~~bash
file libexample.dylib
lipo -info libexample.dylib
otool -L libexample.dylib
~~~

Các lệnh giúp xem slices và dynamic library dependencies. Muốn tạo universal binary, cần compile/link từng architecture đúng toolchain, sau đó kết hợp bằng công cụ tương ứng. Không phải mọi binary hoặc dependency đều dễ kết hợp thành universal artifact.

### 12.3. Darwin ABI và deployment target

Ngoài arm64/x86-64, binary macOS còn có ràng buộc về:

- macOS minimum deployment target.
- Frameworks và symbols có trong phiên bản macOS mục tiêu.
- Code signing, notarization/hardened runtime policy khi ứng dụng phân phối yêu cầu.
- @rpath, @loader_path và dynamic linker behavior.
- ABI calling conventions riêng, đặc biệt ở varargs hoặc C++ interoperability.

Vì vậy, một .dylib được build trên macOS mới có thể không chạy được trên macOS cũ nếu dùng symbol/API mới hơn deployment target.

## 13. Kiểm tra chính xác nền tảng mà JVM đang chạy

Java có các system properties hữu ích:

~~~java
public final class PlatformInfo {
    public static void main(String[] args) {
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("java.home=" + System.getProperty("java.home"));
    }
}
~~~

Giá trị os.arch có thể được báo cáo theo quy ước của JDK/vendor, ví dụ amd64/x86_64 hoặc aarch64/arm64. Không nên hard-code duy nhất một chuỗi mà không có normalization hoặc support matrix.

### 13.1. Process architecture quan trọng hơn host label

Trong các môi trường có emulation hoặc translation:

- CPU host có architecture A.
- Runtime Java process có thể thực thi binary dạng B nhờ hệ thống translation.
- JNI/shared library phải phù hợp với **process binary ABI**, trừ khi có một ranh giới IPC/emulation riêng hỗ trợ.

Điều này đặc biệt quan trọng trên macOS Apple Silicon/Rosetta, Windows on Arm và CI chạy QEMU.

### 13.2. Khi nào dùng platform detection?

Platform detection hữu ích để:

- Chọn native artifact đúng OS/arch/libc từ bộ đã đóng gói.
- Bật/tắt feature chỉ có trên một nền tảng.
- Ghi thông tin chẩn đoán.

Nhưng nó không thể thay thế việc kiểm tra binary format hoặc test runtime. Đừng bỏ qua architecture “không nhận ra” rồi cố load một .so x86-64 như phương án mặc định trên AArch64.

## 14. Thiết kế native artifact matrix

Một ứng dụng có thể cần nhiều bản binary:

| OS | ISA/process arch | Binary | Ràng buộc cần thêm |
|---|---|---|---|
| Linux | x86-64 | libnative.so | glibc/musl, symbol baseline, CPU features |
| Linux | AArch64 | libnative.so | glibc/musl, CPU features |
| Windows | x64 | native.dll | PE/COFF AMD64, Windows runtime DLL |
| Windows | Arm64 | native.dll | PE/COFF ARM64, Windows runtime DLL |
| macOS | x86-64 | libnative.dylib | Mach-O slice, deployment target, signing |
| macOS | arm64 | libnative.dylib | Mach-O slice, deployment target, signing |

Bảng là ví dụ cho dự án muốn hỗ trợ đủ sáu tổ hợp, không phải yêu cầu mọi dự án đều phải hỗ trợ tất cả. Hãy công bố support matrix cụ thể.

### 14.1. Layout lưu native artifacts

Một cấu trúc đóng gói có thể là:

~~~text
resources/
  native/
    linux-x86_64-glibc/libsample_native.so
    linux-aarch64-glibc/libsample_native.so
    linux-x86_64-musl/libsample_native.so
    linux-aarch64-musl/libsample_native.so
    windows-x86_64/sample_native.dll
    windows-aarch64/sample_native.dll
    macos-x86_64/libsample_native.dylib
    macos-aarch64/libsample_native.dylib
~~~

Đây là cấu trúc minh họa; tên thư mục tùy quy ước sản phẩm. Cần cung cấp selector có logic rõ cho OS, architecture, libc và artifact checksum.

### 14.2. Đóng gói trong JAR hay phân phối riêng?

Có ba lựa chọn phổ biến:

**Một JAR chứa nhiều native variants:** tiện cho người dùng nhưng tăng kích thước, đòi hỏi trích xuất và chọn binary đúng, phải quản lý lifecycle của file trích xuất.

**Artifact riêng theo classifier:** ví dụ package có classifier linux-aarch64 hoặc windows-x86_64; giảm dung lượng nhưng build/consumer phải chọn đúng artifact.

**Native library được cài bởi OS/container:** cho phép cập nhật độc lập nhưng yêu cầu deployment quản lý đường dẫn, version và dependency hệ thống.

Không có mô hình duy nhất đúng; chọn theo kênh phân phối và nhu cầu hỗ trợ. Dù chọn cách nào phải xác minh lib được nạp là đúng bản đã được phát hành.

### 14.3. Tải library từ trong JAR

System.loadLibrary không tự đọc native binary nằm trong một resource entry của JAR. Một số framework trích xuất binary ra file trên filesystem rồi gọi System.load bằng đường dẫn đã xác định.

Nếu tự triển khai cơ chế này:

1. Chọn biến thể theo OS, process arch và libc/runtime.
2. Kiểm tra integrity của resource (checksum hoặc chữ ký theo policy).
3. Trích xuất vào thư mục do ứng dụng kiểm soát, tránh race/collision và permission quá rộng.
4. Không tải arbitrary binary từ location writable không tin cậy.
5. Quản lý file lifetime và native library loading/classloader behavior.
6. Xác nhận tất cả transitive shared libraries có thể được tìm thấy.

Một loader “thử lần lượt mọi DLL/.so đến khi cái nào chạy” là khó chẩn đoán và có thể không an toàn. Tốt hơn là chọn biến thể theo metadata và fail rõ ràng nếu platform không được hỗ trợ.

## 15. Build và cross-compilation

### 15.1. Compiler target và sysroot

Để build native binary cho nền tảng khác host, cần một compiler/toolchain có khả năng target đến kiến trúc và OS tương ứng, kèm headers, libc/sysroot, linker và các dependency đã được build cho target đó.

Ví dụ:

~~~text
Host build machine: Linux x86-64
Target native lib : Linux AArch64 / glibc

Cần:
  cross-compiler hoặc target compiler
  AArch64 sysroot/headers
  target-compatible dependencies
  linker đúng architecture/ELF
  test trên AArch64 runtime thật hoặc emulation được xác minh
~~~

Không phải cứ truyền một cờ -march là tạo ra binary cho hệ điều hành khác. CPU target, object format, runtime library và linker đều phải phù hợp.

### 15.2. CMake hoặc build system native

Trong CMake project, có thể khai báo toolchain file hoặc target parameters phù hợp. Cách tổ chức:

~~~text
native source
      │
      ├─ Linux x86-64 build
      ├─ Linux AArch64 build
      ├─ Windows x64 build
      ├─ Windows Arm64 build
      ├─ macOS x86-64 build
      └─ macOS arm64 build
      │
      ▼
Platform-specific binaries + metadata/checksums
      │
      ▼
Java packaging/release pipeline
~~~

Tùy dự án có thể dùng CMake, Meson, Make, MSBuild, Gradle native plugins hoặc scripts. Quan trọng là version toolchain, target và dependency phải được kiểm soát để build tái lập.

### 15.3. Cross-build không thay thế runtime test

Một binary cross-compiled AArch64 có thể được tạo thành công nhưng:

- Dynamic linker/libc không có trong image đích.
- Symbol thiếu ở runtime.
- CPU thiếu extension.
- JNI symbol không được xuất đúng.
- Native function có lỗi memory alignment, pointer hoặc concurrency chỉ lộ trên AArch64.

Vì vậy, ít nhất cần có load test và native smoke test trên target runtime. Emulation có ích cho một số CI checks nhưng không thay thế hoàn toàn test hardware thật khi yêu cầu liên quan hiệu năng, CPU feature hoặc khả năng vận hành production.

## 16. Docker image và Kubernetes đa kiến trúc

Java container có thể được publish dưới một image tag đa kiến trúc. Registry thường cung cấp OCI/Docker manifest list hoặc image index với image khác nhau cho từng architecture.

Ví dụ, cùng một tag có thể trỏ đến:

~~~text
image:example
  ├─ linux/amd64
  └─ linux/arm64
~~~

Khi node Kubernetes AArch64 pull image, container runtime có thể chọn variant linux/arm64 nếu registry cung cấp và platform policy cho phép.

Nhưng điều này không chứng minh **native library bên trong image** tương thích nếu Dockerfile đã copy cố định .so x86-64 cho cả hai biến thể.

### 16.1. Các điểm cần kiểm tra

- Image thực tế có manifest entry cho linux/amd64 và linux/arm64 như đã công bố không?
- Base image JDK đúng OS/architecture?
- Native dependency và agent được build riêng cho architecture?
- Image dùng glibc hay musl, có đúng các runtime dependencies?
- Build pipeline có tạo/release từng biến thể từ đúng artifact?
- Container entrypoint và JVM process chạy architecture nào?
- Kubernetes nodeSelector/affinity và scheduler có thể phân bổ đến node tương thích?

### 16.2. Buildx và multi-platform images

Với Docker Buildx, một lệnh dạng:

~~~bash
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    -t example/native-java-app:1.0 \
    --push .
~~~

có thể dùng trong pipeline có buildx và builder được cấu hình phù hợp. Tuy nhiên, lệnh này tự nó không khiến native library có đủ hai kiến trúc. Dockerfile và các bước build native phải dùng target platform đúng. Nếu dùng emulation, phải đánh giá giới hạn của môi trường build.

### 16.3. Không nhầm architecture của builder với target

Trong multi-platform build có thể có các biến môi trường BUILDPLATFORM/TARGETPLATFORM do công cụ cung cấp. Cần dùng đúng target khi compile native code, không chỉ chạy lệnh uname -m trong build stage rồi suy ra binary cuối.

Một build stage chạy trên host x86-64 có thể tạo file x86-64 cho cả hai target nếu toolchain selection sai. Hãy kiểm tra file/readelf trong image/layer tương ứng trước khi phát hành.

## 17. Kiểm thử platform matrix trong CI

Đối với dự án phát hành native component, ma trận kiểm thử phải bao gồm nhiều chiều:

~~~text
JDK version
  × operating system
  × process architecture
  × C runtime / libc (khi liên quan)
  × native build variant
  × agent/dependency version
~~~

Một matrix mẫu:

| Job | JVM runtime | Native binary | Kiểm tra chính |
|---|---|---|---|
| linux-amd64 | JDK mục tiêu Linux x86-64 | ELF x86-64/glibc | Load + JNI call + runtime dependencies |
| linux-arm64 | JDK mục tiêu Linux AArch64 | ELF AArch64/glibc | Load + JNI call + runtime dependencies |
| linux-arm64-musl | JDK/môi trường hỗ trợ musl | ELF AArch64/musl | Loader + libc compatibility |
| windows-x64 | JDK Windows x64 | PE DLL AMD64 | DLL load + calling convention + test |
| windows-arm64 | JDK Windows Arm64 | PE DLL ARM64 | DLL load + function/struct mapping |
| macos-arm64 | JDK macOS arm64 | Mach-O arm64 | Load + code signing/rpath + native tests |

Chỉ đưa job vào danh sách chính thức khi nền tảng và runner có sẵn hoặc có chiến lược chạy được xác nhận. Không khẳng định hỗ trợ một tổ hợp chỉ vì binary đã compile.

### 17.1. Tầng test cần có

**Tầng 1 — Static artifact inspection**

- Xác định ELF/PE/Mach-O và machine type.
- Kiểm tra exported symbols.
- Xem dynamic dependencies, libc và baseline symbols.
- Kiểm tra checksum/release provenance.

**Tầng 2 — Load test**

- Khởi động JVM với đúng JDK target.
- Nạp library qua System.load/System.loadLibrary hoặc loader thực tế.
- Xác nhận không có UnsatisfiedLinkError, loader failure hoặc architecture mismatch.

**Tầng 3 — Functional JNI/JNA/FFM tests**

- Gọi native method với số nguyên, floating point, strings, arrays, buffers.
- Test struct alignment, pointer-sized values, null pointers, error conditions.
- Test thread safety/callback/long-lived handles nếu có.

**Tầng 4 — Integration tests**

- Chạy cùng framework, agent, container và security settings như deployment.
- Test các API nghiệp vụ đi qua native boundary.
- Kiểm tra memory/crash/logging và dọn dẹp resource.

**Tầng 5 — Production-like verification**

- Canaries trên node x86-64/AArch64 theo chính sách.
- Theo dõi native crashes, SIGILL, JVM fatal error log, agent startup và performance.
- Xác nhận rollback artifact/image/agent đúng architecture.

### 17.2. Test struct layout và ABI

Với thư viện có API C nhận struct, nên có C-side test xác nhận:

~~~c
#include <stddef.h>
#include <stdint.h>

struct Example {
    int32_t code;
    int64_t value;
};

/* Ví dụ kiểm tra offset theo ABI target thực tế:
   sizeof(struct Example)
   _Alignof(struct Example)
   offsetof(struct Example, code)
   offsetof(struct Example, value)
*/
~~~

Trong Java/JNA/FFM, mapping phải được kiểm thử với cùng bản native build. Không copy offset của một platform từ kết quả test rồi áp dụng cho mọi OS mà không có lý do.

### 17.3. Test lỗi cố ý

Ngoài positive tests, cần xác minh:

- Khi không có native binary cho platform, loader báo unsupported platform rõ ràng.
- Khi checksum không khớp, không cố load binary.
- Khi JNI symbol không tồn tại, lỗi được ghi với tên library/version và hướng xử lý.
- Khi hệ thống thiếu libc/runtime DLL, log giúp xác định dependency thiếu.
- Khi agent tùy chọn không load được, hành vi fallback phù hợp policy.
- Khi agent bắt buộc không load được, không tiếp tục chạy trong trạng thái mất kiểm soát bảo mật.

## 18. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Điều tra |
|---|---|---|
| UnsatisfiedLinkError: no library in java.library.path | Chưa tìm thấy thư viện theo tên/đường dẫn. | java.library.path, vị trí load, packaging. |
| UnsatisfiedLinkError với message sai architecture | File binary khác OS/CPU hoặc process arch. | file/readelf/dumpbin/lipo và JVM os.arch. |
| wrong ELF class / invalid ELF header | Binary không đúng bitness/định dạng hoặc file không hợp lệ. | ELF header, image build và artifact origin. |
| undefined symbol | Native library phụ thuộc symbol chưa được cung cấp hoặc ABI/link sai. | readelf -Ws, dependency versions, exported symbols. |
| GLIBC version not found | Binary build với glibc mới hơn runtime hỗ trợ. | readelf, runtime libc version, build baseline. |
| Native DLL dependency missing | DLL phụ thuộc runtime DLL khác chưa được phân phối. | dumpbin /dependents, loader search path. |
| Mach-O incompatible architecture | Không có slice phù hợp JVM process. | file/lipo -info, JDK architecture, Rosetta mode. |
| SIGILL / illegal instruction | CPU không hỗ trợ instruction extension được compiler dùng. | CPU feature baseline, compiler flags, crash details. |
| SIGSEGV / EXCEPTION_ACCESS_VIOLATION | Lỗi native memory, pointer, stack, calling convention hoặc thread misuse. | JVM fatal log, native symbols, debugger/sanitizer ở môi trường test. |
| JVM fatal error sau load agent | Native JVMTI agent không tương thích hoặc lỗi memory/lifecycle. | Agent/JDK version, JVMTI callbacks, native crash logs. |
| Struct values khác giữa Linux và Windows | LP64/LLP64, padding/alignment, endian hoặc binding sai. | sizeof/offsetof và C header của từng target. |

Một lỗi có thể có nhiều nguyên nhân. Ví dụ UnsatisfiedLinkError có thể do thư viện chính không có, symbol của nó không được export, hoặc dependency cấp dưới bị thiếu; không chỉ sửa java.library.path mà cần xem thông báo gốc và dynamic dependencies.

### 18.1. Quy trình điều tra một lỗi load library

1. Ghi Java version, vendor, OS, process architecture và container image.
2. Xác định chính xác native artifact được chọn cùng checksum.
3. Kiểm tra định dạng và machine architecture bằng công cụ OS.
4. Xem libc/C runtime, symbol dependencies và search path.
5. Xác định JDK/JNI/JVMTI version yêu cầu.
6. Tạo load test nhỏ nhất, không phụ thuộc toàn bộ ứng dụng.
7. Nếu load thành công nhưng crash khi gọi, kiểm tra function signature, struct layout và memory lifetime.
8. Build/test lại đúng target, cập nhật artifact matrix và release notes.

### 18.2. Đọc JVM fatal error log

Khi native code làm JVM crash, có thể xuất hiện báo cáo lỗi của HotSpot với thông tin về signal/exception, problematic frame, thread và native library liên quan.

Không kết luận một JNI method là thủ phạm chỉ vì crash xuất hiện gần nó trong log; cần kết hợp symbols/debug info, native stack, compiler optimizations và khả năng tái hiện.

Lưu ý bảo mật: crash dump và heap/core dump có thể chứa dữ liệu nhạy cảm, cần thu thập và lưu trữ theo chính sách, không tự động tải lên issue công khai.

## 19. Kiểm soát bộ nhớ, alignment và concurrency khi đổi kiến trúc

Một số lỗi native chỉ lộ khi chuyển x86-64 sang AArch64 vì các assumption trước đó bị che bởi cách xử lý memory alignment hoặc memory ordering.

### 19.1. Unaligned memory access

Không nên giả định mọi CPU/ABI chấp nhận mọi kiểu load/store từ địa chỉ chưa được align, hoặc compiler sẽ luôn xử lý giống nhau. Code C/C++ ép kiểu từ buffer bytes sang pointer của struct có thể có undefined behavior do aliasing/alignment.

Thay vì cast tùy tiện:

~~~c
/* Không nên giả định data được align và có layout đúng */
struct Record *record = (struct Record *)buffer;
~~~

cần thiết kế serialization/deserialization rõ ràng, sử dụng memcpy khi phù hợp, kiểm tra length và layout theo protocol. Với FFM/JNA cũng phải khai báo alignment và kích thước theo ABI.

### 19.2. Memory ordering và data races

x86-64 và AArch64 có mô hình memory ordering ở cấp hardware khác nhau. Một bug C/C++ native dùng shared memory nhưng không đồng bộ đúng có thể rất hiếm trên một kiến trúc và xuất hiện thường xuyên trên kiến trúc khác.

Không xử lý data race bằng cách thêm sleep hoặc dựa vào thứ tự instruction quan sát được. Cần dùng:

- C11/C++ atomics hoặc mutex/lock được hỗ trợ.
- Memory order phù hợp cho các thao tác chia sẻ.
- JNI synchronization có ngữ nghĩa rõ khi native cùng Java threads tương tác.
- Test concurrency trên cả x86-64 và AArch64, kết hợp sanitizer khi toolchain cho phép.

Java Memory Model không tự bảo đảm rằng code native dùng raw pointers và atomics sai vẫn đúng. Ranh giới JNI/FFM cần xác định rõ các quy tắc concurrency của cả hai phía.

### 19.3. Size_t, pointer và handle lifecycle

Java long 64-bit không được đồng nhất với mọi loại native handle hoặc pointer mà không xem xét semantics. Trên các môi trường 64-bit thông dụng, intptr_t có thể đủ chứa pointer, nhưng cách đóng gói pointer thành long vẫn cần chính sách quản lý lifetime và không lộ địa chỉ không cần thiết.

Một pattern native handle:

~~~text
Java object holds opaque handle
    │
    ▼
Native context allocated
    │
    ▼
Java calls native operations
    │
    ▼
close() explicitly frees context
~~~

Nếu dùng handle như long, phải kiểm tra null/closed state, double free, use-after-free, access từ nhiều thread và lỗi cleanup. Với FFM, có thể dùng arena/lifetime APIs thay vì raw long khi thiết kế phù hợp.

## 20. Bảo mật và supply-chain của native artifacts

Native code chạy trong tiến trình JVM với quyền của tiến trình, nên có thể truy cập bộ nhớ và OS APIs ngoài phạm vi kiểm soát bình thường của Java type system. Một thư viện native không tin cậy có thể tạo rủi ro nghiêm trọng.

Các nguyên tắc:

- Chỉ phân phối binary từ build pipeline và nguồn dependency được chấp thuận.
- Gắn version/checksum/signature/provenance với từng OS/architecture variant.
- Kiểm tra CVE và chính sách maintenance của native dependency, không chỉ Java JAR.
- Giới hạn quyền của container/process và đường dẫn native library.
- Tránh DLL/.so search path trỏ đến thư mục có thể bị bên khác ghi.
- Quản lý các temporary extracted native libraries an toàn.
- Không vô hiệu hóa security policy của JDK hoặc OS chỉ để load binary legacy.
- Xem xét code signing/hardened runtime khi platform deployment yêu cầu.

**Artifact đúng kiến trúc không đồng nghĩa an toàn hoặc được hỗ trợ.** Cần bổ sung các bằng chứng về nguồn gốc, runtime dependencies và cập nhật bảo mật.

## 21. Báo cáo compatibility cho native dependency

Một bảng kiểm kê nên đi kèm mỗi thư viện native:

| Thuộc tính | Nội dung cần ghi |
|---|---|
| Java module/service | Thành phần sử dụng native code. |
| Java wrapper | JNI, JNA, FFM, JVMTI agent hoặc framework. |
| Native artifact | Tên file, version, checksum, classifier. |
| OS target | Linux, Windows, macOS và phiên bản tối thiểu khi liên quan. |
| Process architecture | x86-64 hoặc AArch64, dùng tên chuẩn hóa. |
| Binary format | ELF, PE/COFF hoặc Mach-O. |
| ABI/data model | System V AMD64, Windows x64, AAPCS64/Darwin conventions; LP64/LLP64. |
| C runtime/dependencies | glibc/musl, UCRT, libstdc++, frameworks và symbols. |
| CPU baseline | Những extension bắt buộc hoặc runtime dispatch. |
| JDK/JNI/agent support | Java versions và các ràng buộc đặc thù JVMTI/FFM. |
| Packaging | JAR resource, OS package, container layer, classifier. |
| Verification | Static inspection, load test, functional/native integration tests. |
| Ownership | Nhóm chịu trách nhiệm build, sửa lỗi và nâng bản vá. |

Ví dụ support matrix minh họa:

~~~text
Component: image-accelerator-native
Version  : 2.x
OS       : Linux
Targets  :
  - linux-x86_64-glibc
  - linux-aarch64-glibc
JDK      : Java versions theo sản phẩm công bố
Tests    : load + buffer/struct + multithread + feature behavior
Status   : chỉ công bố SUPPORT khi đã có test evidence
~~~

Không suy ra support từ tên artifact hoặc từ một lần build thành công; status phải dựa trên runtime test của đúng target.

## 22. Chiến lược migration từ x86-64 sang AArch64

Giả sử một ứng dụng Java đang dùng Linux x86-64 và cần triển khai thêm Linux AArch64:

### Bước 1 — Kiểm kê tất cả native dependencies

Tìm:

- JNI libraries được gọi bằng System.load/LoadLibrary.
- JNA/FFM bindings và native libraries được load động.
- -agentpath/-agentlib và các agent có thành phần native.
- JNI code được framework đóng gói trong transitive JARs.
- Database drivers có native authentication, crypto/HSM libraries.
- Compression, ML, image/video và telemetry libraries.

Đừng kết luận “dự án thuần Java” chỉ vì không thấy file .c trong source; dependency bắc cầu có thể trích xuất .so ở runtime.

### Bước 2 — Xây dựng target matrix

Quyết định OS version, libc (glibc/musl), JDK distribution, AArch64 CPU baseline, container image và các agent phiên bản mục tiêu.

### Bước 3 — Có native binary phù hợp

Với thư viện tự phát triển, build bằng cross-compiler hoặc native runner đúng target. Với thư viện bên thứ ba, chọn version/classifier có AArch64 support chính thức; nếu không có, cân nhắc thay library hoặc cô lập chức năng.

### Bước 4 — Xem lại ABI assumptions

Kiểm tra C long, pointer, size_t, struct padding, alignment, calling convention, endianness, C++ ABI, CPU-specific intrinsics và shared-memory synchronization.

### Bước 5 — Kiểm tra packaging

Đảm bảo JAR hoặc container image chọn linux-aarch64 variant trên JVM AArch64, không nạp nhầm binary x86-64. Kiểm tra dynamic dependencies trong image đích.

### Bước 6 — Chạy test từng tầng

- Static binary inspection.
- JVM startup + native load.
- Native functional smoke test.
- Data boundary/struct/callback tests.
- Integration/agent tests.
- Concurrency, performance và long-running tests.

### Bước 7 — Rollout từng giai đoạn

Triển khai staging/canary trên AArch64 nodes đã chỉ định, quan sát JVM fatal errors, agent failure, native memory và throughput/latency. Có phương án rollback sang artifact và node architecture phù hợp.

### Bước 8 — Công bố phạm vi hỗ trợ

Ghi rõ sản phẩm hỗ trợ:

~~~text
Linux x86-64 + glibc, JDK target
Linux AArch64 + glibc, JDK target
~~~

nếu đó là hai tổ hợp đã được kiểm chứng. Nếu chưa hỗ trợ Alpine/musl, Windows Arm64 hay macOS arm64, đừng ngầm quảng bá tất cả môi trường “64-bit” đều tương thích.

## 23. Những giả định sai thường gặp

| Giả định | Vấn đề | Cách làm phù hợp |
|---|---|---|
| “Java chạy trên mọi máy nên JNI cũng vậy.” | JNI dùng binary OS/ISA-specific. | Build/test native variant cho từng target. |
| “x64 trên Windows giống x86-64 trên Linux.” | OS ABI, format, loader và C runtime khác. | Phân phối DLL/so theo OS target. |
| “AArch64 giống arm64 ở mọi hệ điều hành.” | Cùng ISA nhưng ABI và loader khác. | Phân biệt Linux/Windows/macOS targets. |
| “64-bit nghĩa là C long 64-bit.” | Windows 64-bit thường là LLP64. | Dùng jlong/fixed-width types và kiểm tra layout. |
| “Chỉ xem os.arch là đủ.” | Emulation và JDK process arch có thể khác host CPU. | Kiểm tra process và binary thực tế. |
| “Đổi tên .so thành .dll là chạy.” | ELF và PE/COFF khác định dạng/ABI. | Build đúng target toolchain. |
| “Image đa kiến trúc tự chuyển JNI library.” | Multi-arch manifest không tự compile native code. | Build/copy variant phù hợp từng image. |
| “Có .so AArch64 là chắc chắn chạy Alpine.” | glibc và musl có thể không tương thích. | Chọn libc variant và kiểm tra dependencies. |
| “Compile thành công là portable.” | Runtime có thể thiếu symbol, loader hoặc CPU feature. | Chạy load/integration tests trên target. |
| “Một JNI function nhận long giống Java long.” | C long khác width theo data model. | Dùng JNI types và interface contract cố định. |
| “JNA/FFM bỏ hết vấn đề ABI.” | Cả hai vẫn ánh xạ native calling convention và layout. | Test binding theo OS/arch và API version. |
| “Agent Java JAR không phụ thuộc native.” | Một số agent kéo JVMTI/JNI hoặc bytecode tooling phụ thuộc JDK. | Kiểm kê agent và runtime dependencies. |
| “CPU AArch64 chắc chắn chậm/nhanh hơn x86-64.” | Hiệu năng phụ thuộc CPU generation, workload, JIT, SIMD và native implementation. | Benchmark trên phần cứng đại diện. |
| “ldd an toàn với mọi binary lạ.” | Phân tích binary không tin cậy có rủi ro trong một số ngữ cảnh. | Ưu tiên static inspection và sandbox. |
| “Cùng ABI thì dùng chung C++ binary ở mọi compiler.” | C++ ABI, runtime và compiler options có thể khác. | Dùng C boundary và kiểm chứng toolchain. |

## 24. Quy trình xử lý sự cố native sau nâng JDK

Khi ứng dụng trước đây chạy tốt nhưng lỗi sau khi đổi JDK, OS hoặc architecture:

1. **Cố định bằng chứng:** JDK version, vendor, process architecture, OS, libc/container image, JVM args, module/library version.
2. **Tách đường native:** xác định JNI/JNA/FFM/JVMTI component đang được load.
3. **Chụp metadata artifact:** file type, machine architecture, checksum, exported symbols và dynamic dependencies.
4. **Đối chiếu ABI:** calling convention, C data model, struct layout, compiler/target và C runtime.
5. **Lặp lại bằng minimal load test:** giảm phạm vi từ cả ứng dụng xuống một method/agent có thể tái hiện.
6. **Kiểm tra integration:** JVM ↔ native types, memory lifetime, concurrency và lifecycle.
7. **Xử lý platform mismatch:** build lại đúng target hoặc chọn variant được hỗ trợ, không đổi tên file hoặc bỏ kiểm tra bảo mật.
8. **Kiểm thử nhiều tầng:** static, load, functional, integration, staging/canary.
9. **Ghi kết luận:** root cause, artifact version, platforms đã test, unsupported combinations và phương án rollback.

Nếu sự cố xuất hiện ở thư viện native bên thứ ba, cần đối chiếu tài liệu hỗ trợ và bản phát hành của vendor. Không tự sửa toolchain flags để override ABI mà không hiểu dependency và hợp đồng tương thích.

## 25. Kết luận

**x86-64 và AArch64 là hai kiến trúc CPU khác nhau, còn ABI là hợp đồng nhị phân chịu ảnh hưởng của hệ điều hành, compiler, C runtime và các thư viện liên kết.** Ngay khi cùng là 64-bit, Linux, Windows và macOS có thể dùng data model, calling convention, binary format và dynamic loader khác nhau. Mã Java chạy trên JVM tương ứng có thể portable, nhưng JNI, JNA, FFM bindings và native JVMTI agents vẫn phụ thuộc vào binary phù hợp với OS, process architecture và ABI.

Trong Java Advance Compatibility Migration, cần kiểm kê cả native dependencies trực tiếp lẫn bắc cầu, chuẩn hóa cách chọn artifacts theo OS/arch/libc, kiểm tra LP64/LLP64, struct alignment, native symbols, CPU instruction baseline và runtime linker. Build đa kiến trúc phải đi kèm kiểm thử thật trên từng target, đặc biệt khi chuyển x86-64 sang AArch64, khi dùng Alpine/musl hoặc khi chạy JVM dưới emulation.

Đích đến là **một compatibility matrix có bằng chứng**: mỗi tổ hợp JDK–OS–architecture–ABI đều có native artifact xác định, provenance rõ, kiểm thử load và chức năng, chính sách bảo mật và phương án rollout/rollback. Khi đó, lợi ích portability của Java được duy trì mà không bỏ sót các ranh giới phụ thuộc nền tảng trong phần mã native.
