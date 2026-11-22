# Vai trò `jni.h`, header theo nền tảng, `JNIEXPORT` và `JNICALL`

> **Chủ đề:** Java Advance — Native Interoperability · **Mục:** JNI đầu tiên. Bài học này giải thích bốn thành phần thường xuất hiện ngay khi viết JNI lần đầu: `jni.h` cung cấp những gì, tại sao có header phụ thuộc hệ điều hành, tại sao `javac -h` tạo thêm một header riêng cho lớp Java, và `JNIEXPORT`/`JNICALL` bảo đảm điều gì ở ranh giới Java–C/C++.

## 1. Nhìn toàn bộ đường đi của một lời gọi JNI

**Java Native Interface (JNI)** là giao diện chuẩn để mã chạy trong JVM gọi mã native (thường viết bằng C/C++) và để mã native tương tác trở lại với lớp, đối tượng, mảng, chuỗi, exception và phương thức Java.

Ví dụ khi Java khai báo:

```java
package demo.jni;

public class NativeMath {
    public static native int add(int left, int right);
}
```

Dấu `native` nói với JVM rằng phương thức không có thân Java; khi phương thức được liên kết và gọi, JVM sẽ tìm phần triển khai native tương ứng trong một thư viện đã được tải. Phần triển khai phải tuân thủ **ABI (Application Binary Interface)** và hợp đồng JNI: tên symbol hoặc đăng ký thủ công, kiểu dữ liệu, thứ tự tham số, calling convention và cách tương tác với JVM.

```text
Mã Java (.java)
    |
    | javac -h ...                (tạo class + header khai báo native)
    v
NativeMath.class        demo_jni_NativeMath.h
    |                            |
    | System.loadLibrary(...)    | #include <jni.h>
    v                            | #include "jni_md.h" (gián tiếp)
JVM/JNI linker <-----------------+----------------+
    |                                             |
    | tìm symbol JNI                              | C compiler + linker
    v                                             v
Java_demo_jni_NativeMath_add(...)   <----   libnative_math.so / .dylib / native_math.dll
                      (được gọi trong chính tiến trình JVM)
```

Đây là **ba lớp header cần phân biệt**:

1. **`jni.h`:** header JNI chung do JDK cung cấp. Nó khai báo kiểu JNI, `JNIEnv`, `JavaVM`, bảng hàm JNI và các macro/cấu trúc cần thiết.
2. **`jni_md.h`:** header nền tảng do JDK cung cấp, được `jni.h` include để lấy các định nghĩa phụ thuộc máy/ABI, chẳng hạn một số kiểu số nguyên nền tảng và export decoration.
3. **`demo_jni_NativeMath.h`:** header **của ứng dụng**, được `javac -h` sinh từ các phương thức `native` của một lớp cụ thể. Nó chứa prototype đúng của các hàm Java ↔ native.

`jni.h` không phải một header riêng cho mỗi dự án; còn header do `javac -h` sinh ra **không phải** bản sao của `jni.h`. Cả hai phối hợp để native code có những khai báo khớp JVM và lớp Java.

## 2. Vai trò của `jni.h`: hợp đồng chung với JVM

Thông thường, mã C có thể viết:

```c
#include <jni.h>
```

Header này (và các header được nó include) cung cấp:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Kiểu nguyên thủy JNI | `jboolean`, `jbyte`, `jchar`, `jshort`, `jint`, `jlong`, `jfloat`, `jdouble` | Biểu diễn chính xác kiểu dữ liệu Java qua ABI JNI |
| Kiểu tham chiếu | `jobject`, `jclass`, `jstring`, `jarray`, `jintArray` | Tham chiếu JNI tới object/class/string/array do JVM quản lý |
| Môi trường JNI | `JNIEnv`, `JNIEnv *env` | Truy cập hàm JVM trên thread hiện tại: đọc field, gọi method, tạo string, xử lý exception, v.v. |
| Giao diện máy ảo | `JavaVM` | Truy cập các thao tác liên quan JVM, chẳng hạn attach/detach thread native |
| Kiểu và giá trị phụ trợ | `jsize`, `jmethodID`, `jfieldID`, `JNI_OK`, `JNI_VERSION_1_8` | Kích thước, ID cho method/field, status và version |
| Macro hỗ trợ khai báo | `JNIEXPORT`, `JNICALL` | Xuất symbol và thống nhất calling convention theo platform/JDK |

**Không thay kiểu JNI bằng kiểu C một cách cảm tính.** Ví dụ, Java `int` ánh xạ sang `jint`, Java `long` sang `jlong`; C `long` có kích thước khác nhau giữa các ABI, đặc biệt Windows x64 và Linux x64. Java `char` là đơn vị UTF-16 16-bit, nên JNI dùng `jchar` chứ không đơn giản dùng C `char`. String Java không tự biến thành `char *`: JNI truyền `jstring` và muốn lấy bytes/characters thì dùng hàm API với quy tắc release phù hợp.

### `JNIEnv` không phải đối tượng Java thông thường

Một native method viết bằng **C** có thể gọi hàm JNI:

```c
/* Fragment minh họa; chỉ dùng bên trong native method hợp lệ. */
jstring result = (*env)->NewStringUTF(env, "Hello JNI");
```

Trong **C++**, wrapper của `JNIEnv` hỗ trợ cú pháp khác:

```cpp
// Fragment minh họa; chỉ dùng bên trong native method hợp lệ.
jstring result = env->NewStringUTF("Hello JNI");
```

Hai cú pháp cùng sử dụng JNI function table. Sự khác nhau nằm ở định nghĩa `JNIEnv` cho C/C++, không phải ở Java method signature.

**Quy tắc thread:** `JNIEnv*` chỉ hợp lệ trên thread nhận nó. Không cất `env` rồi mang sang thread native khác để dùng; thread native tự tạo phải attach vào JVM theo quy tắc JNI và detach phù hợp. Tương tự, JNI local reference thường chỉ sống trong ngữ cảnh thread/native call tương ứng; muốn giữ object lâu hơn phải hiểu global reference và vòng đời của nó.

## 3. Vì sao `jni.h` cần header nền tảng `jni_md.h`?

Không gian API JNI khá thống nhất giữa các hệ điều hành, nhưng cách biên dịch thành mã máy vẫn phụ thuộc **OS, CPU architecture, ABI, compiler/toolchain**. Do đó JDK thường tổ chức:

```text
<JDK_HOME>/
  include/
    jni.h                 # giao diện JNI chung
    jvmti.h               # API khác, không cần cho ví dụ JNI này
    linux/
      jni_md.h            # cấu hình ABI của bản JDK Linux
    darwin/
      jni_md.h            # cấu hình ABI của bản JDK macOS
    win32/
      jni_md.h            # cấu hình ABI của bản JDK Windows
```

Sơ đồ thể hiện **ba cài đặt JDK khác nhau** để so sánh, không phải một thư mục JDK duy nhất chứa tất cả ba nền tảng. Tùy nhà cung cấp JDK, một số nhánh nền tảng có thể khác. Khi build trên Linux, lấy header Linux của JDK tương ứng; trên macOS lấy header `darwin`; trên Windows lấy `win32`, ngay cả khi máy Windows là 64-bit.

`jni.h` chứa một chỉ thị include theo tên đơn giản:

```c
#include "jni_md.h"
```

Vì vậy compiler phải được chỉ đúng **cả hai include directories**. Đối với Linux:

```bash
-I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux"
```

Tương đương trên macOS:

```bash
-I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin"
```

Và trên Windows với MSVC Developer Command Prompt:

```bat
/I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32"
```

`jni_md.h` thường quy định một phần kiểu machine-dependent, visibility/export, và các chi tiết nền tảng phù hợp với ABI. **Không sửa trực tiếp `jni_md.h`** để chữa lỗi build. Chọn đúng JDK/target platform/toolchain, sau đó cấu hình include path; sửa header của JDK sẽ dễ tạo binding sai mà khó debug.

### Không được trộn header và binary không tương thích

Ví dụ dự án compile native code theo ABI Linux x86-64 nhưng lại deploy DLL Windows x64: đều là "64-bit" nhưng định dạng binary, calling convention, thư viện hệ thống và cách link hoàn toàn khác nhau. Cần đồng bộ **JDK headers + compiler target + OS/CPU + thư viện native**. Khi build cross-compile, phải có target headers/toolchain phù hợp chứ không lấy bừa `jni_md.h` của host.

Nếu compiler báo `fatal error: jni.h: No such file or directory`, thường thiếu đường dẫn `include` hoặc trỏ vào JRE/JDK không đúng. Nếu báo `fatal error: jni_md.h: No such file or directory`, thường đã tìm thấy `jni.h` nhưng **chưa có đường dẫn include của nền tảng**.

## 4. `JNIEXPORT` và `JNICALL` có hai trách nhiệm khác nhau

Khuôn mẫu quen thuộc:

```c
JNIEXPORT jint JNICALL Java_demo_jni_NativeMath_add(
    JNIEnv *env,
    jclass clazz,
    jint left,
    jint right
);
```

Đọc từ trái sang phải:

| Thành phần | Ý nghĩa |
|---|---|
| `JNIEXPORT` | Yêu cầu compiler/linker **export** function qua ranh giới thư viện động theo cách phù hợp nền tảng |
| `jint` | Kiểu giá trị trả về native, tương ứng Java `int` |
| `JNICALL` | Chọn **calling convention** mà JNI/JVM mong đợi cho native function |
| `Java_demo_jni_NativeMath_add` | Symbol tương ứng class `demo.jni.NativeMath`, phương thức `add` theo quy tắc JNI name mapping |
| `JNIEnv *env` | Con trỏ tới giao diện JNI của thread hiện hành |
| `jclass clazz` | Lớp khai báo phương thức, vì `add` là `static native` |
| `jint left, jint right` | Hai tham số Java `int` được ánh xạ sang JNI `jint` |

### `JNIEXPORT`: hàm phải hiện diện trong symbol table

Trên Windows, export của DLL thường sử dụng cơ chế như `__declspec(dllexport)`. Trên hệ Unix-like, compiler/linker có cơ chế symbol visibility; một số JDK triển khai `JNIEXPORT` bằng attribute visibility phù hợp, có cài đặt để trống khi mặc định đã export. **Cách expand cụ thể là chi tiết nền tảng/phiên bản JDK**, vì thế người viết code dùng macro do JDK cung cấp thay vì tự hard-code.

Không có export đúng, mã C có thể **compile/link thành công** nhưng JVM không tìm được symbol tại lúc liên kết native method. Trên Windows, `JNIEXPORT` đặc biệt quan trọng khi tạo DLL. Ngay cả trên Linux, build với `-fvisibility=hidden` có thể ẩn function nếu thiếu export annotation phù hợp.

### `JNICALL`: bên gọi và bên được gọi phải thống nhất ABI

**Calling convention** quy định cách đặt tham số (register/stack), quy tắc return và những chi tiết mang tính ABI. Trong lịch sử Win32 x86, JNI dùng convention kiểu `__stdcall`; trên nhiều ABI hiện đại, convention mặc định đã phù hợp và macro có thể expand thành rỗng. Không cần đoán `JNICALL` sẽ expand thành gì trên máy bạn.

Nếu caller và callee bất đồng calling convention, ứng dụng có thể xử lý tham số sai hoặc hỏng stack; lỗi đặc biệt khó lần trên cấu hình 32-bit cũ. `JNICALL` **không** nghĩa là Java callback, async call, fast call, hay cơ chế quản lý thread. Nó chỉ bảo đảm khai báo native function tuân thủ convention cần thiết.

### Hai macro không thể thay thế cho nhau

- `JNIEXPORT` giải quyết **khả năng nhìn thấy symbol từ bên ngoài thư viện**.
- `JNICALL` giải quyết **cách mã máy thực hiện lời gọi hàm**.
- Tên `Java_...` giải quyết **JVM tìm đúng native method nào**.

Có đủ ba yếu tố mới hình thành một binding tĩnh đúng theo naming convention. Ngoài cách dùng tên `Java_...`, JNI còn hỗ trợ `RegisterNatives` để đăng ký function pointer, nhưng trong bài thực hành đầu tiên nên dùng header sinh bởi `javac -h` để tránh lỗi ánh xạ.

## 5. Tự viết và chạy một JNI từ đầu: Java 17+

Ví dụ sau cố ý có **một phương thức `static native` và một `instance native`** để so sánh `jclass` và `jobject`. Mọi số đều nhỏ, không cần bàn tới tràn số trong phần thực hành này.

Yêu cầu: JDK 17+, C compiler tương thích nền tảng, đặt `JAVA_HOME` trỏ đến thư mục JDK đang dùng; ví dụ lệnh chính dùng Linux với GCC.

### Bước 1 — Viết lớp Java

Tạo `src/demo/jni/NativeMath.java`:

```java
package demo.jni;

public final class NativeMath {
    static {
        System.loadLibrary("native_math");
    }

    public static native int add(int left, int right);

    public native int doubleValue(int value);

    public static void main(String[] args) {
        System.out.println("add=" + add(20, 22));
        System.out.println("double=" + new NativeMath().doubleValue(21));
    }
}
```

- `System.loadLibrary("native_math")` nhận **tên thư viện logic**, không phải tên tệp có đuôi `.so`, `.dll` hoặc `.dylib`.
- `native` khai báo method mà không có thân Java. Native implementation có thể nằm trong cùng một shared library.
- `static native` sẽ nhận `jclass` làm đối số JNI thứ hai; instance native nhận `jobject` (đối tượng `this`).

### Bước 2 — Dùng `javac -h` sinh prototype

Trong thư mục gốc dự án:

```bash
mkdir -p build/classes build/headers
javac -d build/classes -h build/headers src/demo/jni/NativeMath.java
```

Từ JDK 17, `javac -h` là cách chính thức để sinh JNI native header. Lệnh trên tạo:

```text
build/classes/demo/jni/NativeMath.class
build/headers/demo_jni_NativeMath.h
```

Nội dung quan trọng của `build/headers/demo_jni_NativeMath.h` có dạng:

```c
/* DO NOT EDIT THIS FILE - it is machine generated */
#include <jni.h>
/* Header for class demo_jni_NativeMath */

#ifndef _Included_demo_jni_NativeMath
#define _Included_demo_jni_NativeMath

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Class:     demo_jni_NativeMath
 * Method:    add
 * Signature: (II)I
 */
JNIEXPORT jint JNICALL Java_demo_jni_NativeMath_add
  (JNIEnv *, jclass, jint, jint);

/*
 * Class:     demo_jni_NativeMath
 * Method:    doubleValue
 * Signature: (I)I
 */
JNIEXPORT jint JNICALL Java_demo_jni_NativeMath_doubleValue
  (JNIEnv *, jobject, jint);

#ifdef __cplusplus
}
#endif
#endif
```

Một số khoảng trắng, comment hoặc include guard có thể khác giữa các phiên bản compiler; **prototype và kiểu tham số mới là hợp đồng phải khớp**. Trong `(II)I`, hai `I` ở bên trong ngoặc nghĩa là hai tham số Java `int`, `I` sau ngoặc là kiểu trả về `int`. `(I)I` nghĩa là một tham số `int` và trả về `int`.

Lưu ý header này được **sinh từ code Java** và tự include `jni.h`. Đừng viết tay hoặc chỉnh tên symbol trong header; khi thay đổi khai báo Java, chạy lại `javac -h` rồi rebuild thư viện C.

### Bước 3 — Viết phần triển khai bằng C

Tạo `native/NativeMath.c`:

```c
#include "demo_jni_NativeMath.h"

JNIEXPORT jint JNICALL Java_demo_jni_NativeMath_add(
        JNIEnv *env, jclass clazz, jint left, jint right) {
    (void) env;
    (void) clazz;
    return left + right;
}

JNIEXPORT jint JNICALL Java_demo_jni_NativeMath_doubleValue(
        JNIEnv *env, jobject self, jint value) {
    (void) env;
    (void) self;
    return value * 2;
}
```

Đây là một tệp C hoàn chỉnh (được link thành thư viện động). `(void) env` và `(void) clazz/self` chỉ để compiler khỏi cảnh báo **unused parameter**; JVM vẫn truyền đủ các tham số đó.

Header được sinh bảo vệ tính nhất quán bằng prototype. Nếu C implementation sai return type, thiếu `JNIEnv*` hoặc tráo `jclass`/`jobject`, compiler có cơ hội phát hiện **conflicting types** ngay khi build, thay vì chờ JVM báo lỗi ở runtime.

### Bước 4 — Compile thư viện Linux

```bash
gcc -std=c11 -fPIC -shared \
  -I"build/headers" \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libnative_math.so native/NativeMath.c
```

Giải thích cờ:

- `-Ibuild/headers`: tìm header `demo_jni_NativeMath.h` mà `javac` vừa sinh.
- `-I$JAVA_HOME/include`: tìm `jni.h` của JDK.
- `-I$JAVA_HOME/include/linux`: tìm `jni_md.h` dành cho target Linux.
- `-fPIC`: tạo position-independent code phù hợp shared library.
- `-shared -o libnative_math.so`: tạo thư viện động cho Linux, tên được `System.loadLibrary("native_math")` ánh xạ.

### Bước 5 — Chạy Java và kiểm chứng

JDK 17–23:

```bash
java -Djava.library.path=. -cp build/classes demo.jni.NativeMath
```

Với JDK 24+ nên cấp quyền native access cho ứng dụng trên classpath:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. -cp build/classes demo.jni.NativeMath
```

**stdout mong đợi (không tính diagnostic của công cụ):**

```text
add=42
double=42
```

`-Djava.library.path=.` yêu cầu JVM tìm thư viện JNI trong thư mục làm việc hiện hành. Nếu không muốn phụ thuộc thư mục hiện hành, có thể dùng `System.load(absolutePath)` và quản lý đường dẫn tuyệt đối; `System.loadLibrary` vẫn nhận tên logic. Đừng nhầm `java.library.path` với classpath: `-cp build/classes` để tìm `.class`, còn `java.library.path` để tìm native library.

### Tên và lệnh tương ứng trên macOS

Java source/header được biên dịch tương tự. Dùng compiler Clang/Xcode command-line tools:

```bash
clang -std=c11 -dynamiclib -fPIC \
  -I"build/headers" \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o libnative_math.dylib native/NativeMath.c
```

Sau đó chạy Java với cùng classpath và `-Djava.library.path=.`; cấp `--enable-native-access=ALL-UNNAMED` cho JDK 24+. Thư viện macOS có đuôi `.dylib` thay vì Linux `.so`.

### Tên và lệnh tương ứng trên Windows

Trong **Developer Command Prompt for Visual Studio** với MSVC và `JAVA_HOME` trỏ tới JDK Windows:

```bat
mkdir build\classes
mkdir build\headers
javac -d build\classes -h build\headers src\demo\jni\NativeMath.java
cl /LD /I"build\headers" /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" native\NativeMath.c /link /OUT:native_math.dll
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. -cp build\classes demo.jni.NativeMath
```

Lệnh chạy ở trên dành cho JDK 24+; nếu dùng JDK 17–23, bỏ `--enable-native-access=ALL-UNNAMED`. `mkdir` có thể báo thư mục đã tồn tại nếu chạy lại; bạn có thể giữ thư mục cũ. DLL là `native_math.dll`, không có tiền tố `lib`. Bộ công cụ MSVC có thể tạo thêm `.obj` và `.lib`; đó là artifact của toolchain. Các lệnh shell của Linux/macOS và Windows không hoán đổi trực tiếp cho nhau.

## 6. Vì sao header tự sinh quan trọng hơn việc tự đoán tên hàm?

JNI dynamic linking truyền thống ánh xạ tên Java sang C symbol. Với class `demo.jni.NativeMath`, phương thức `add` không overload thì dạng ngắn thường là:

```text
Java_demo_jni_NativeMath_add
```

Phần `demo_jni` là package được biến đổi theo JNI name mangling. Dấu gạch dưới xuất hiện trong tên nguồn Java có quy tắc escape riêng; không được suy ra rằng mọi `_` trong tên Java chỉ là dấu phân cách package.

Với hai phương thức `native` overload:

```java
// Fragment minh họa, không phải lớp độc lập để chạy.
native int scale(int value);
native long scale(long value);
```

Tên dài trong JNI thường có hậu tố tham số:

```text
Java_demo_jni_Scale_scale__I
Java_demo_jni_Scale_scale__J
```

`I` là descriptor tham số Java `int`; `J` là `long`. Đây là ví dụ giả sử hai phương thức nằm trong lớp `demo.jni.Scale`. Dạng mangling còn có quy tắc cho object/array, dấu chấm, dấu gạch dưới, ký tự Unicode. **Hãy dùng `javac -h`** để nhận prototype đúng, nhất là khi có overload; không tự nối chuỗi hoặc đổi tên prototype theo cảm giác.

`javac -h` tạo **prototype được kiểm tra tại thời điểm compile**; nó không tạo C implementation và không tự tạo `.so`/`.dylib`/`.dll`. Khi đổi chữ ký Java, tên package hoặc modifiers, phải tạo lại header và thư viện tương ứng.

## 7. C và C++: giữ đúng linkage

C++ compiler có **name mangling** để hỗ trợ overload và namespace. JVM lại tìm một symbol theo JNI naming convention; một symbol bị C++ mangling sẽ không trùng tên.

Header do `javac -h` sinh thường bao quanh prototype bằng:

```cpp
#ifdef __cplusplus
extern "C" {
#endif
// JNI prototypes
#ifdef __cplusplus
}
#endif
```

Câu lệnh `extern "C"` yêu cầu các khai báo bên trong dùng **C linkage**. Nếu viết native implementation bằng `.cpp`, include đúng header đã sinh và bảo đảm definition có cùng C linkage. Ví dụ minh họa cho phương thức `add` bên trên:

```cpp
// Fragment C++: thay thế definition C của add khi build bằng C++.
#include "demo_jni_NativeMath.h"

extern "C" JNIEXPORT jint JNICALL Java_demo_jni_NativeMath_add(
        JNIEnv *env, jclass clazz, jint left, jint right) {
    (void) env;
    (void) clazz;
    return left + right;
}
```

Fragment này chưa có implementation `doubleValue`, nên không phải thư viện hoàn chỉnh cho Java class của bài thực hành. Khi viết toàn bộ binding bằng C++, định nghĩa cả hai phương thức đúng prototype. Dùng `extern "C"` **không** có nghĩa là JNI chỉ chạy C: implementation vẫn có thể sử dụng tính năng C++ nội bộ; chỉ ABI/exported symbol được giới hạn theo C linkage.

## 8. Phân biệt lỗi compile, load và link native method

Quy trình chạy có **ba thời điểm lỗi khác nhau**:

| Thời điểm | Dấu hiệu tiêu biểu | Cách kiểm tra |
|---|---|---|
| **Compile native code** | `jni.h: No such file or directory` | Thiếu `-I<JDK>/include` hoặc `JAVA_HOME` sai |
| **Compile native code** | `jni_md.h: No such file or directory` | Thiếu `-I<JDK>/include/linux`, `darwin` hoặc `win32` tương ứng |
| **Compile native code** | `conflicting types for 'Java_...'` | Header `javac -h` và C definition khác signature, thiếu/thừa kiểu |
| **Load thư viện** | `UnsatisfiedLinkError: no native_math in java.library.path` | Sai tên logic, thư mục, file extension, quyền truy cập |
| **Load thư viện** | Báo wrong architecture, missing dependent DLL/`.so`, loader error | Sai bitness/OS/CPU, thư viện phụ thuộc, toolchain runtime |
| **Link phương thức** | `UnsatisfiedLinkError` nhắc tới Java native method/signature | Thư viện có thể đã load nhưng không có đúng symbol, export bị ẩn, tên sai hoặc thiếu function |

### Các lệnh xem symbol đã export

Trên Linux, sau khi build:

```bash
nm -D --defined-only libnative_math.so | grep Java_
```

Với Windows và MSVC Developer Command Prompt:

```bat
dumpbin /EXPORTS native_math.dll
```

Trên macOS, có thể dùng `nm -gU libnative_math.dylib` để xem global external symbols; tên có thể hiển thị thêm một dấu gạch dưới ở đầu theo convention của công cụ Mach-O. Điều cần quan tâm là **symbol JNI đúng tên và được export**, không chỉ việc file tồn tại.

Khi debug, tách ba câu hỏi: (1) compiler có tìm đúng header? (2) JVM có tải đúng thư viện? (3) thư viện có xuất đúng native symbol? Trộn chúng thành một lỗi "JNI không chạy" sẽ khiến việc sửa trở nên mò mẫm.

## 9. Những hiểu nhầm thường gặp về macro và header

1. **“Include mỗi `jni.h` là compiler tự tìm được mọi thứ.”** Chưa đủ: compiler còn phải tìm được `jni_md.h` của target và header ứng dụng do `javac -h` sinh nếu code include nó.
2. **“`jni.h` chính là header được sinh từ lớp Java.”** Sai: `jni.h` là API chung từ JDK; `javac -h` sinh prototype cho lớp của bạn.
3. **“`JNIEXPORT` và `JNICALL` chỉ để code đẹp.”** Sai: chúng thể hiện yêu cầu export symbol/calling convention; bỏ sai có thể gây lỗi load/link hoặc ABI.
4. **“`JNIEXPORT` luôn expand giống nhau trên mọi OS/JDK.”** Sai: cách export phụ thuộc toolchain và phiên bản header; dùng macro từ JDK thay vì tự copy expansion.
5. **“`JNICALL` làm cho lời gọi JNI luôn nhanh hơn.”** Sai: nó quyết định calling convention cần thiết, không bảo đảm latency hay throughput.
6. **“Native method static nhận `jobject this`.”** Sai: static nhận `jclass`; instance nhận `jobject`; cả hai có `JNIEnv*` trước đó.
7. **“Java `long` luôn là C `long`.”** Sai: dùng `jlong`; C primitive có thể khác kích thước giữa ABI.
8. **“`System.loadLibrary` nhận `libnative_math.so`.”** Không đúng trong ví dụ: đưa tên logic `native_math`, để JVM ánh xạ sang tên thư viện theo OS.
9. **“C++ export function tên như C nếu tên hàm nhìn giống nhau.”** Không luôn đúng: phải kiểm soát C linkage, thông thường bằng header `javac -h` có `extern "C"`.
10. **“Có header đúng thì library chắc chắn chạy an toàn.”** Sai: JNI chạy native code cùng tiến trình JVM; truy cập pointer sai, use-after-free hoặc native crash vẫn có thể làm hỏng JVM.

## 10. Native access trên JDK mới, tương thích và bảo trì

Từ **JDK 24 (JEP 472)**, việc dùng các thao tác JNI nhạy cảm như load native library và liên kết native method cần được xem xét theo chính sách **native access**. Với module chưa được cấp quyền, JDK 24 mặc định phát cảnh báo; trạng thái xử lý có thể điều chỉnh bằng `--illegal-native-access` và sẽ được tăng cường ở các bản JDK sau.

- Chạy trên **classpath**: `--enable-native-access=ALL-UNNAMED`.
- Chạy ứng dụng **named module**: cấp quyền cụ thể, ví dụ `--enable-native-access=my.module`, cho module dùng native access.
- Để phát hiện sớm chỗ thiếu quyền, trên JDK hỗ trợ có thể chạy thử với `--illegal-native-access=deny`.
- `JNIEXPORT`, `JNICALL` và các header không thay thế việc khai báo quyền native access của Java runtime.
- Cấp native access không làm native code trở thành memory-safe; kiểm tra input, ownership và lỗi JNI vẫn cần thiết.

Khi phát hành, nên:

1. Gắn native library phù hợp **OS/CPU**, kèm toolchain runtime/dependencies cần thiết.
2. Build trên CI cho mỗi target và kiểm tra exported symbols.
3. Giữ Java native declarations, header sinh và C/C++ implementation đồng bộ qua build pipeline.
4. Tránh commit/sửa tay header sinh nếu build có thể tạo lại; nếu dự án lưu generated header để review, phải có quy trình tái sinh và kiểm tra drift.
5. Ghi rõ JDK tối thiểu, cách cấu hình `JAVA_HOME`, `java.library.path`, chính sách native access và cách tái tạo binary.
6. Dùng JNI API đúng kiểu: không chia sẻ `JNIEnv*` giữa thread, không giữ local refs quá vòng đời, cân đối acquire/release array và string khi có dùng.
7. Ghi nhận rằng lỗi native có thể crash JVM; thử nghiệm mã native lạ trong môi trường cô lập.

## 11. Bài tự kiểm tra

**Câu 1.** Compiler tìm thấy `jni.h` nhưng lỗi `jni_md.h`. Cần kiểm tra gì trước?  
**Trả lời:** Include path theo nền tảng, chẳng hạn `$JAVA_HOME/include/linux` trên Linux, và bảo đảm `JAVA_HOME`/target JDK đúng.

**Câu 2.** Vì sao function C phải khai báo `JNIEXPORT jint JNICALL ...`?  
**Trả lời:** `JNIEXPORT` lo export symbol, `jint` khớp kiểu trả về Java `int`, `JNICALL` áp dụng calling convention tương ứng ABI JNI.

**Câu 3.** Cùng một class có `static native int f()` và `native int g()`. Hai native function khác tham số thứ hai ra sao?  
**Trả lời:** Cả hai có `JNIEnv*` trước; `f` nhận `jclass`, `g` nhận `jobject`.

**Câu 4.** Tệp `demo_jni_NativeMath.h` nằm ở đâu và ai tạo?  
**Trả lời:** Trong thư mục chỉ định bởi `javac -h` (ví dụ `build/headers`); `javac` sinh nó từ các khai báo `native`, lập trình viên không nên tự sửa.

**Câu 5.** JVM tải được DLL nhưng báo `UnsatisfiedLinkError` khi gọi `add`. Kiểm tra gì?  
**Trả lời:** Prototype/symbol có đúng naming convention và mangling không, export có bị ẩn không, phương thức có overload không, C++ có C linkage không; kiểm tra `dumpbin /EXPORTS` hoặc `nm` tùy nền tảng.

**Câu 6.** Có thể thay `JNIEXPORT` bằng `JNICALL` được không?  
**Trả lời:** Không; chúng đảm nhận hai khía cạnh ABI khác nhau. Dùng đúng cả hai theo header JDK để tránh giả định sai nền tảng.

### Tóm lược những điểm cần nhớ

`jni.h` định nghĩa giao diện JNI chung; `jni_md.h` bổ sung các chi tiết phụ thuộc target; `javac -h` sinh header đúng với phương thức Java. Trong prototype `JNIEXPORT <type> JNICALL Java_...(...)`, từng thành phần có nhiệm vụ riêng: **export symbol**, **kiểu JNI**, **calling convention**, **tên phương thức đã mangling**, **`JNIEnv*`/`jclass` hoặc `jobject` và tham số**. Muốn JNI hoạt động ổn định, phải đồng bộ header, toolchain/ABI, tên library, cách load và chính sách native access.

## Tài liệu tham khảo chính thức

- [Java Native Interface Specification — Introduction](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/intro.html)
- [Java Native Interface Specification — Design Overview: naming, arguments, interface pointer](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html)
- [Java Native Interface Specification — JNI Types and Data Structures](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/types.html)
- [Java SE 21 — javac tool options (`-h`)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472)
