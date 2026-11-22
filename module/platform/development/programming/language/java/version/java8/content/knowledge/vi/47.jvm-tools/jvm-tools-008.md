# javac -h và sinh header cho tích hợp native khi cần

`javac -h` là tùy chọn của Java compiler dùng để **sinh header C/C++ cho các khai báo native trong mã Java**. Header mô tả tên hàm JNI, kiểu trả về, tham số và các hằng số native được đánh dấu. Native developer dùng header ấy làm hợp đồng giữa Java class và phần triển khai C/C++.

Đây là bước quan trọng khi tích hợp một thư viện native qua **Java Native Interface (JNI)**: Java khai báo method có từ khóa `native`; `javac -h` tạo header; compiler C/C++ dùng header đó để viết/biên dịch hàm; runtime nạp thư viện và liên kết symbol khi method được gọi.

Cần hiểu đúng phạm vi: **`javac -h` chỉ tạo header**. Nó không viết phần thân C/C++, không biên dịch thành DLL/SO, không liên kết thư viện và không chứng minh native implementation chạy đúng. Phần build native cần toolchain C/C++ và phải khớp hệ điều hành, kiến trúc CPU, ABI và JDK/runtime đích.

Bài hướng dẫn quy trình từ Java declaration đến header và native library, giải thích tên symbol, kiểu JNI, cách build/nạp thư viện trên Windows/Linux/macOS, các lỗi thường gặp và khi nào nên chọn API native hiện đại khác. Các ví dụ dùng cú pháp JNI còn được hỗ trợ; không dựa vào công cụ hoặc API đã bị loại bỏ.

## 1. Khi nào cần tích hợp native?

JNI cho phép Java đang chạy trong JVM gọi code viết bằng C, C++ hoặc ngôn ngữ native khác. Một số tình huống thực tế:

- Ứng dụng phải dùng một thư viện C/C++ đã tồn tại và không có Java binding phù hợp.
- Cần gọi API hệ điều hành hoặc thiết bị mà Java API chuẩn không cung cấp.
- Phải tương tác với driver, codec, SDK phần cứng hoặc thư viện native của nhà cung cấp.
- Một phần nhỏ của workload cần native implementation và việc chuyển đổi đã được benchmark chứng minh có lợi.
- Ứng dụng phải duy trì một JNI ABI đã được phát hành cho nhiều hệ thống.

**Không nên thêm JNI chỉ vì muốn code chạy nhanh hơn.** Crossing Java/native boundary, chuyển đổi dữ liệu, quản lý bộ nhớ và đồng bộ có chi phí. Nếu phần việc đã được Java API hỗ trợ, hãy bắt đầu bằng Java thuần và đo trước khi chọn native.

### 1.1. JNI và FFM trên JDK hiện đại

Từ JDK 22, **Foreign Function & Memory API (FFM)** thuộc `java.lang.foreign` đã là API ổn định. FFM cho phép Java tìm symbol trong native library, mô tả chữ ký hàm và gọi C function trực tiếp qua `Linker`/`MethodHandle` mà không cần viết lớp JNI trung gian cho nhiều trường hợp gọi hàm thông thường.

Tài liệu JNI hiện hành của Oracle khuyến nghị ưu tiên FFM khi phù hợp. Tuy nhiên, JNI vẫn có lý do tồn tại:

- Dự án còn phải chạy trên Java 8, không có FFM.
- Đang tích hợp một thư viện JNI đã có và cần giữ ABI hiện tại.
- Native library được thiết kế quanh JNI, callback hoặc tương tác trực tiếp với object/method của JVM.
- Có yêu cầu tương thích với một hệ thống hoặc SDK chỉ cung cấp JNI.

**Quy tắc chọn:** nếu chỉ cần gọi một tập C function từ ứng dụng chạy JDK hiện đại, hãy đánh giá FFM trước. Nếu phải khai báo Java native method và triển khai theo JNI, dùng `javac -h` để sinh header. Hai hướng không nên bị trộn lẫn trong cùng một ví dụ.

## 2. `javac -h` tạo ra những gì?

Cú pháp cơ bản:

~~~bash
javac -h <header-directory> <source-files>
~~~

Tùy chọn `-h` chỉ định thư mục đặt header được sinh. Compiler tạo header cho mỗi class được biên dịch có:

- Ít nhất một method khai báo từ khóa `native`; hoặc
- Một hay nhiều constant được đánh dấu annotation `java.lang.annotation.Native`.

Nếu class nằm trong package/module, tên và vị trí header phản ánh thông tin class/package/module theo cách tổ chức output của compiler. Thư mục đích và các thư mục cần thiết được tạo nếu chưa có. Hãy xem file thật do đúng JDK của dự án sinh ra, không tự đoán đường dẫn.

Header thường chứa:

- `#include <jni.h>` để dùng các kiểu và macro JNI.
- Include guard chống include lặp.
- Macro cho constant có annotation `@Native`.
- Prototype hàm với `JNIEXPORT` và `JNICALL`.
- Các kiểu JNI như `jint`, `jstring`, `jboolean`, `jobject` hoặc `jclass`.
- Tên symbol được compiler tạo theo package, class và method signature.

**Header là output sinh tự động.** Không chỉnh sửa trực tiếp header vì lần compile sau sẽ sinh lại và ghi mất thay đổi. Hãy sửa Java declaration hoặc C implementation, rồi chạy lại quy trình sinh header.

## 3. Khai báo Java native method

Tạo file `src/demo/bridge/NativeMath.java`:

~~~java
package demo.bridge;

import java.lang.annotation.Native;

public final class NativeMath {
    @Native
    public static final int ABI_VERSION = 1;

    static {
        System.loadLibrary("nativebridge");
    }

    public native int add(int left, int right);
    public native String echo(String text);
    public native int scale(int value);
    public native int scale(String value);
    public static native boolean isPositive(long value);

    public static void main(String[] args) {
        NativeMath math = new NativeMath();
        System.out.println("ABI: " + ABI_VERSION);
        System.out.println("add: " + math.add(12, 30));
        System.out.println("echo: " + math.echo("JNI works"));
        System.out.println("scale(int): " + math.scale(21));
        System.out.println("scale(String): " + math.scale("hello"));
        System.out.println("isPositive: " + isPositive(5L));
    }
}
~~~

Class trên có bốn ý cần chú ý:

1. `add`, `echo` và hai overload `scale` là instance native methods.
2. `isPositive` là static native method.
3. Hai method `scale` có cùng tên nhưng khác tham số; JNI cần symbol phân biệt signature.
4. `ABI_VERSION` được đánh dấu `@Native` nên compiler đưa constant vào header.

Từ khóa `native` chỉ khai báo rằng phần thân method nằm ở native library. Java compiler không sinh phần triển khai C/C++ và cũng không kiểm tra xem symbol đã tồn tại trong DLL/SO chưa. Việc liên kết chỉ được xác nhận khi thư viện native phù hợp được nạp và method được gọi.

### 3.1. Sinh header và class file trong một lần compile

Từ thư mục dự án:

~~~bash
javac -encoding UTF-8 -d build/classes -h build/headers src/demo/bridge/NativeMath.java
~~~

Các tùy chọn:

| Tùy chọn | Ý nghĩa |
|---|---|
| `-encoding UTF-8` | Đọc source bằng UTF-8 |
| `-d build/classes` | Đặt class file trong thư mục riêng |
| `-h build/headers` | Đặt header JNI do compiler sinh |
| Source file | Class cần compile và tạo header |

Nếu class phụ thuộc source/class khác, cung cấp chúng trong cùng lượt compile hoặc cấu hình `--class-path`/`--source-path` phù hợp. Với module, dùng module path và cấu trúc source/module tương ứng.

### 3.2. Kết quả header đã sinh

Với package và khai báo ở ví dụ trên, JDK 24 sinh file `demo_bridge_NativeMath.h`. Các prototype chính:

~~~c
#include <jni.h>
/* Header for class demo_bridge_NativeMath */

#ifndef _Included_demo_bridge_NativeMath
#define _Included_demo_bridge_NativeMath
#ifdef __cplusplus
extern "C" {
#endif

#undef demo_bridge_NativeMath_ABI_VERSION
#define demo_bridge_NativeMath_ABI_VERSION 1L

JNIEXPORT jint JNICALL Java_demo_bridge_NativeMath_add
  (JNIEnv *, jobject, jint, jint);

JNIEXPORT jstring JNICALL Java_demo_bridge_NativeMath_echo
  (JNIEnv *, jobject, jstring);

JNIEXPORT jint JNICALL Java_demo_bridge_NativeMath_scale__I
  (JNIEnv *, jobject, jint);

JNIEXPORT jint JNICALL Java_demo_bridge_NativeMath_scale__Ljava_lang_String_2
  (JNIEnv *, jobject, jstring);

JNIEXPORT jboolean JNICALL Java_demo_bridge_NativeMath_isPositive
  (JNIEnv *, jclass, jlong);

#ifdef __cplusplus
}
#endif
#endif
~~~

Những dòng này được chạy lấy từ header do `javac -h` tạo, không phải tên hàm tự đặt. Header cũng có include guard, macro hằng số và vùng `extern "C"` để tương thích khi được include từ C++.

Tên file cụ thể có thể thay đổi khi package, class, module hoặc source declaration thay đổi. Hãy include đúng file thực tế trong C/C++ source.

## 4. Đọc prototype JNI

### 4.1. Hai tham số đầu luôn theo quy tắc JNI

Mọi native method implementation đều nhận interface pointer `JNIEnv *env` ở đầu danh sách tham số. Tham số thứ hai phụ thuộc method Java là instance hay static:

| Khai báo Java | Tham số JNI thứ hai | Ý nghĩa |
|---|---|---|
| `native int add(...)` | `jobject` | Object nhận lời gọi, tương đương `this` |
| `static native boolean isPositive(...)` | `jclass` | Class khai báo static method |

Các tham số tiếp theo ánh xạ theo thứ tự tham số Java. Kiểu trả về cũng ánh xạ sang kiểu JNI tương ứng. Không tự bỏ `env` hoặc đổi `jobject` thành `jclass` chỉ vì tên hàm gần giống nhau.

### 4.2. Bảng kiểu Java sang kiểu JNI thông dụng

| Java | JNI/C type |
|---|---|
| `void` | `void` |
| `boolean` | `jboolean` |
| `byte` | `jbyte` |
| `char` | `jchar` |
| `short` | `jshort` |
| `int` | `jint` |
| `long` | `jlong` |
| `float` | `jfloat` |
| `double` | `jdouble` |
| Object reference | `jobject` hoặc kiểu con như `jstring`, `jclass` |
| Array reference | `jarray` hoặc kiểu con như `jintArray` |

Các kiểu JNI được khai báo trong `jni.h`. Hãy dùng đúng kiểu JNI trong prototype, tránh tự giả định kích thước của `long`, pointer hoặc kiểu số native theo nền tảng.

### 4.3. Tên symbol và method overload

JNI tạo tên symbol từ tên class/package và tên method. Khi một native method bị overload với native method khác trong cùng class, symbol dài thêm phần mã hóa parameter descriptor.

Ví dụ header ở trên sinh:

~~~text
Java_demo_bridge_NativeMath_scale__I
Java_demo_bridge_NativeMath_scale__Ljava_lang_String_2
~~~

`__I` biểu diễn tham số kiểu int. `__Ljava_lang_String_2` biểu diễn tham số String. Đừng tự viết quy tắc mã hóa tên; **dùng đúng prototype từ header do compiler tạo**. Sai một ký tự cũng có thể khiến JVM không tìm thấy symbol.

### 4.4. Chữ ký method cũng là hợp đồng

Header có comment signature dạng JVM descriptor:

| Java declaration | Descriptor |
|---|---|
| `int add(int, int)` | `(II)I` |
| `String echo(String)` | `(Ljava/lang/String;)Ljava/lang/String;` |
| `int scale(int)` | `(I)I` |
| `int scale(String)` | `(Ljava/lang/String;)I` |
| `static boolean isPositive(long)` | `(J)Z` |

Khi đổi tên method, package, kiểu tham số hoặc kiểu trả về, hãy compile lại header và build lại native library. Thay đổi chữ ký Java mà không cập nhật binary có thể dẫn tới `UnsatisfiedLinkError` khi gọi.

## 5. Viết phần triển khai C

Tạo file `src/native_math.c`. Ví dụ dưới đây include header đã sinh và định nghĩa từng symbol:

~~~c
#include <limits.h>
#include "demo_bridge_NativeMath.h"

static void throwArithmeticException(JNIEnv *env, const char *message) {
    jclass exceptionClass =
            (*env)->FindClass(env, "java/lang/ArithmeticException");
    if (exceptionClass != NULL) {
        (*env)->ThrowNew(env, exceptionClass, message);
        (*env)->DeleteLocalRef(env, exceptionClass);
    }
}

JNIEXPORT jint JNICALL Java_demo_bridge_NativeMath_add(
        JNIEnv *env, jobject self, jint left, jint right) {
    (void) self;
    if ((right > 0 && left > INT_MAX - right)
            || (right < 0 && left < INT_MIN - right)) {
        throwArithmeticException(env, "int addition overflow");
        return 0;
    }
    return left + right;
}

JNIEXPORT jstring JNICALL Java_demo_bridge_NativeMath_echo(
        JNIEnv *env, jobject self, jstring text) {
    (void) self;
    if (text == NULL) {
        return NULL;
    }

    const char *utf = (*env)->GetStringUTFChars(env, text, NULL);
    if (utf == NULL) {
        return NULL;
    }

    jstring result = (*env)->NewStringUTF(env, utf);
    (*env)->ReleaseStringUTFChars(env, text, utf);
    return result;
}

JNIEXPORT jint JNICALL Java_demo_bridge_NativeMath_scale__I(
        JNIEnv *env, jobject self, jint value) {
    (void) self;
    if (value > INT_MAX / 2 || value < INT_MIN / 2) {
        throwArithmeticException(env, "int multiplication overflow");
        return 0;
    }
    return value * 2;
}

JNIEXPORT jint JNICALL Java_demo_bridge_NativeMath_scale__Ljava_lang_String_2(
        JNIEnv *env, jobject self, jstring text) {
    (void) self;
    if (text == NULL) {
        return 0;
    }
    return (*env)->GetStringLength(env, text);
}

JNIEXPORT jboolean JNICALL Java_demo_bridge_NativeMath_isPositive(
        JNIEnv *env, jclass type, jlong value) {
    (void) env;
    (void) type;
    return value > 0 ? JNI_TRUE : JNI_FALSE;
}
~~~

Các điểm quan trọng trong ví dụ:

- Hàm C phải khớp tên, kiểu trả về, calling convention và danh sách tham số trong header.
- `GetStringUTFChars` lấy biểu diễn Modified UTF-8 của Java String; sau khi dùng xong phải gọi `ReleaseStringUTFChars`.
- `GetStringLength` trả số đơn vị UTF-16 của Java String, không phải số byte UTF-8 hoặc số grapheme người dùng nhìn thấy.
- `FindClass` và `ThrowNew` có thể tạo exception Java đang chờ xử lý; không tiếp tục gọi API JNI tùy tiện khi exception chưa được xử lý.
- Ví dụ kiểm tra overflow trước phép tính số nguyên để tránh undefined behavior trong C.

### 5.1. C và C++ có cú pháp gọi JNI khác nhau

Với file C, các hàm JNI thường được gọi qua bảng function pointer:

~~~c
const char *value = (*env)->GetStringUTFChars(env, text, NULL);
~~~

Với C++, JNI cung cấp cú pháp member-function tiện hơn:

~~~cpp
const char *value = env->GetStringUTFChars(text, nullptr);
~~~

Header sinh tự động có vùng `extern "C"` để prototype không bị C++ name mangling. Khi dùng C++, giữ nguyên calling convention/macro JNI và include đúng header; đừng tự bỏ `JNIEXPORT` hoặc `JNICALL`.

## 6. Build thư viện native theo hệ điều hành

Trước khi build, cần có:

- JDK đầy đủ với thư mục `include` chứa `jni.h` và header theo nền tảng.
- C/C++ compiler phù hợp hệ điều hành/kiến trúc.
- Header do `javac -h` sinh trong `build/headers`.
- Thư mục output `build/native` đã được tạo.

Tên thư viện nạp bằng `System.loadLibrary("nativebridge")` thường là `nativebridge.dll` trên Windows, `libnativebridge.so` trên Linux và `libnativebridge.dylib` trên macOS. Tên file chính xác theo quy ước của runtime/OS.

### 6.1. Windows với MSVC

Mở Developer Command Prompt/PowerShell có môi trường MSVC, rồi chạy:

~~~powershell
New-Item -ItemType Directory -Force build/native | Out-Null
cl /nologo /LD /I"$env:JAVA_HOME\include" /I"$env:JAVA_HOME\include\win32" /I"build\headers" src\native_math.c /link /OUT:build\native\nativebridge.dll
~~~

`/LD` yêu cầu compiler tạo DLL. `JAVA_HOME` phải trỏ tới đúng JDK dùng để phát triển/chạy ứng dụng. Nếu có dependency native khác, cấu hình thêm include path, library path và linker inputs tương ứng.

### 6.2. Linux với GCC

~~~bash
mkdir -p build/native
gcc -std=c11 -fPIC -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" -I"build/headers" -shared src/native_math.c -o build/native/libnativebridge.so
~~~

`-fPIC` tạo position-independent code; `-shared` tạo shared library. Dùng đúng thư mục include cho Linux và đúng kiến trúc mục tiêu. Nếu thư viện phụ thuộc các `.so` khác, dynamic loader của hệ điều hành cũng phải tìm thấy chúng.

### 6.3. macOS với Clang

~~~bash
mkdir -p build/native
clang -std=c11 -fPIC -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" -I"build/headers" -dynamiclib src/native_math.c -o build/native/libnativebridge.dylib
~~~

macOS dùng include directory `darwin` và output dynamic library `.dylib`. Chú ý kiến trúc CPU (arm64/x86_64), deployment target và các dependency native cần đóng gói.

### 6.4. Kiến trúc phải tương thích

Một JVM 64-bit cần native library đúng kiến trúc/ABI của process. DLL x86 không thể nạp vào JVM x64; tương tự binary Linux x86_64 không dùng được trên macOS arm64. Kiểm tra compiler target, JDK architecture, OS ABI và dependency trước khi điều tra lỗi Java.

## 7. Nạp và gọi native library

Trong ví dụ Java:

~~~java
static {
    System.loadLibrary("nativebridge");
}
~~~

`System.loadLibrary` nhận **tên logic** của thư viện, không truyền prefix/suffix của OS và không truyền đường dẫn tuyệt đối. JVM tìm thư viện theo cơ chế platform-specific, trong đó `java.library.path` là một trong các nguồn tìm kiếm.

Chạy ví dụ sau khi đã build native library:

~~~bash
java -Djava.library.path=build/native -cp build/classes demo.bridge.NativeMath
~~~

Với JDK hiện đại có native-access restrictions, hãy cấp native access cho module thực sự dùng JNI. Nếu class chạy từ classpath/unnamed module:

~~~bash
java --enable-native-access=ALL-UNNAMED -Djava.library.path=build/native -cp build/classes demo.bridge.NativeMath
~~~

Nếu ứng dụng là named module, dùng tên module cụ thể thay cho `ALL-UNNAMED`. Java 8 không có module system và không dùng tùy chọn này; đây là lưu ý cho các JDK hiện hành.

Nếu build thành công, native implementation ở phần 5 tạo output minh họa:

~~~text
ABI: 1
add: 42
echo: JNI works
scale(int): 42
scale(String): 5
isPositive: true
~~~

Output này là **kết quả dự kiến khi C library đã được build và nạp thành công**. Trong môi trường soạn bài này, Java compiler/header generation đã chạy được nhưng không có GCC, Clang hoặc MSVC, nên chưa thực hiện link DLL/SO hay chạy lời gọi native end-to-end.

## 8. Quy trình thay đổi method native

Khi sửa Java declaration, luôn cập nhật header và binary theo cùng một phiên bản source:

1. Sửa native declaration trong Java.
2. Chạy lại `javac -h` để tạo header mới.
3. So prototype mới với C/C++ implementation.
4. Sửa implementation và các test liên quan.
5. Build native library cho từng OS/architecture được hỗ trợ.
6. Chạy integration test trên đúng JDK, OS và binary.
7. Đóng gói thư viện native cùng artifact theo classifier/platform phù hợp.

Không chỉnh header thủ công để “làm cho build qua”. Nếu header và implementation lệch nhau, sửa Java source hoặc native implementation rồi sinh lại header.

## 9. Lỗi thường gặp khi tích hợp JNI

| Lỗi | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `no nativebridge in java.library.path` | Không tìm thấy file thư viện | Tên file, path, prefix/suffix |
| `UnsatisfiedLinkError` khi gọi method | Symbol không khớp | Prototype, package, overload, rebuild |
| `wrong ELF class` / Bad image | Sai kiến trúc/ABI | JDK và native compiler target |
| Không tìm thấy `jni.h` | Thiếu include path JDK | `JAVA_HOME/include` |
| Không tìm thấy `jni_md.h` | Thiếu include path theo OS | `include/linux`, `include/win32`, `include/darwin` |
| DLL load failed | Thiếu dependency native | OS dependency inspection |
| JVM crash | Lỗi memory/pointer trong C/C++ | Debugger, sanitizer, JNI checks |
| Method trả kết quả sai | JNI type/signature hoặc encoding sai | Header, kiểu JNI, test biên |
| Java class load cảnh báo native access | Module chưa được cấp native access | Cấu hình runtime phù hợp |

### 9.1. Phân biệt lỗi nạp thư viện và lỗi liên kết symbol

Nếu JVM báo không tìm thấy thư viện, kiểm tra tên file, thư mục tìm kiếm và dependency của native binary. Nếu thư viện đã nạp nhưng không tìm thấy method symbol, kiểm tra lại tên prototype trong header và implementation. Hai lỗi này có nguyên nhân khác nhau, không nên chỉ thay đổi `java.library.path` khi symbol bị sai.

Có thể dùng công cụ của nền tảng để xem export/dependency: `dumpbin /exports` trên Windows, `nm -D`/`ldd` trên Linux hoặc `nm`/`otool -L` trên macOS.

## 10. An toàn và vòng đời JNI

Native code chạy trong cùng process với JVM. Một lỗi pointer, buffer length, ownership hoặc concurrency có thể làm crash toàn bộ process; JVM không thể bảo vệ Java heap khỏi mọi thao tác C/C++ sai.

### 10.1. Không giữ JNIEnv qua thread

`JNIEnv *env` chỉ hợp lệ trong thread hiện tại. Không lưu pointer này rồi dùng từ native thread khác. Native thread tự tạo muốn gọi JNI phải attach vào JVM, lấy JNIEnv cho thread đó, rồi detach trước khi kết thúc theo đúng lifecycle.

### 10.2. Quản lý local/global references

JNI object reference không phải raw pointer tới layout object Java. Dùng JNI functions để đọc/ghi object. Local references có lifetime gắn với native call/local frame; nếu giữ reference lâu hơn hoặc dùng ở thread khác, cần loại reference phù hợp và quản lý release. Không giữ local reference trong biến global C rồi dùng về sau.

### 10.3. Giải phóng tài nguyên lấy từ JNI

Mọi cặp lấy/nhả cần tuân thủ API tương ứng:

- `GetStringUTFChars` → `ReleaseStringUTFChars`.
- `GetStringChars` → `ReleaseStringChars`.
- `Get<Type>ArrayElements` → `Release<Type>ArrayElements`.
- `GetPrimitiveArrayCritical` → `ReleasePrimitiveArrayCritical`.

Không giữ critical pointer trong thời gian dài, không thực hiện I/O hoặc chờ lâu khi đang giữ critical array. Kiểm tra giá trị NULL và exception sau các lời gọi JNI có thể thất bại.

### 10.4. Exception Java từ native code

Native code có thể ném exception Java bằng `Throw`/`ThrowNew`. Khi một exception đang pending, chỉ gọi những JNI functions được phép trong trạng thái đó; thường native method có thể trả về để exception được truyền lại cho Java caller. Đừng tiếp tục xử lý bình thường như thể không có lỗi.

### 10.5. Quyền native access trên JDK mới

Từ các JDK có cơ chế restricted native access, khai báo `native` hoặc nạp thư viện từ module chưa được cấp native access có thể tạo warning hoặc exception tùy runtime configuration. Dùng `--enable-native-access` có phạm vi hẹp theo module khi triển khai. Không bật cho toàn bộ ứng dụng nếu chỉ một module cần dùng native code.

## 11. Khi nào dùng `@Native` và `RegisterNatives`?

`@Native` đánh dấu một constant native để compiler đưa macro tương ứng vào generated header. Nó hữu ích khi Java và native code cần dùng chung hằng số ABI/flag đã định nghĩa. Annotation này **không tự biến method thành native** và không đăng ký function pointer.

JNI còn có `RegisterNatives` để gắn tên/signature Java với function pointer trong native code lúc runtime. Cách này phù hợp với một số kiến trúc đăng ký động, nhưng yêu cầu quản lý method signature và function pointer rất cẩn thận. Với luồng cơ bản dùng symbol naming, header từ `javac -h` là cách trực tiếp và dễ đối chiếu hơn. Chỉ chọn `RegisterNatives` khi thiết kế native library thực sự cần đăng ký tường minh.

## 12. `javac -h` không thay thế build system

Trong dự án thực tế, header và binary native là artifact có vòng đời riêng:

- Header được sinh từ Java source bằng JDK compiler.
- C/C++ source include generated header.
- Native build system dùng compiler/linker theo nền tảng.
- Java build system compile class và đóng gói resource/library.
- CI chạy ma trận test cho từng OS/architecture được hỗ trợ.

Có thể dùng Maven/Gradle để gọi native build tool, nhưng không nên giả định plugin Java compile mặc định đã build native library. Giữ rõ dependency giữa bước compile Java/header và bước compile/link C/C++.

### 12.1. Không commit binary build cho mọi nền tảng vào cùng một output không phân loại

Nếu ứng dụng hỗ trợ Windows/Linux/macOS, thường cần artifact riêng theo OS và architecture, hoặc tải binary phù hợp trong packaging step. Đặt tên và version native library rõ ràng để tránh nạp nhầm bản. Đối với native code có ABI public, cần chính sách versioning và backward compatibility riêng.

## 13. Checklist trước khi phát hành

1. Tên package/class và method trong Java có đúng với header không?
2. Mọi native method đã có implementation?
3. Header mới nhất được sinh từ đúng source revision?
4. Overload đã dùng symbol dài đúng signature?
5. Instance/static method dùng đúng `jobject`/`jclass`?
6. C/C++ compiler đã include đúng JDK và OS headers?
7. DLL/SO/dylib đúng OS, architecture và ABI?
8. Runtime tìm thấy native library và mọi dependency?
9. Module cần native access đã được cấp đúng phạm vi?
10. String/array references được release đúng cách?
11. Native thread attach/detach và JNIEnv lifecycle đúng?
12. Exception pending được kiểm tra và xử lý đúng?
13. Test có cover null, boundary, overflow, encoding và concurrency?
14. CI có build/test cho từng nền tảng mục tiêu?
15. Native library được đóng gói và version hóa cùng ứng dụng?

## 14. Những sai lầm thường gặp

**1. Nghĩ `javac -h` sinh luôn DLL/SO.** Nó chỉ tạo header và compile class Java.

**2. Viết prototype bằng tay rồi bỏ qua header sinh.** Dễ sai tên, kiểu hoặc calling convention.

**3. Chỉ sửa Java native method mà không build lại native library.** Binary có thể không còn khớp chữ ký.

**4. Dùng tên ngắn cho các native overload cùng tên.** Symbol phải phân biệt signature.

**5. Dùng `jobject` cho static method.** Tham số thứ hai phải là `jclass`.

**6. Dùng kiểu C mặc định thay cho JNI type.** Kích thước/ABI có thể khác nền tảng.

**7. Quên include path theo hệ điều hành.** `jni.h` còn phụ thuộc `jni_md.h`.

**8. Trộn DLL x86 và JVM x64.** Không tương thích kiến trúc.

**9. Đưa phần mở rộng file vào `System.loadLibrary`.** Truyền tên logic, không thêm `.dll`/`.so`.

**10. Coi Java native method compile được là runtime đã liên kết.** Compile không kiểm tra native symbol có trong thư viện hay không.

**11. Không release string/array pointer.** Có thể giữ tài nguyên hoặc cản GC.

**12. Lưu `JNIEnv` dùng ở thread khác.** Pointer gắn với thread hiện tại.

**13. Dùng local reference sau khi native call kết thúc.** Lifetime không còn hợp lệ.

**14. Bỏ qua exception pending.** JNI calls sau đó có thể không an toàn.

**15. C++ name mangling làm JVM không tìm thấy symbol.** Dùng prototype/header JNI và C linkage phù hợp.

**16. Chỉnh sửa generated header thủ công.** Lần compile tiếp theo sẽ ghi lại.

**17. Chỉ test trên một OS.** Library là binary phụ thuộc nền tảng.

**18. Dùng JNI cho mọi lời gọi C đơn giản trên JDK mới.** Đánh giá FFM khi phù hợp.

## 15. Bài tập tự luyện

1. `javac -h` nhận thư mục nào và tạo ra loại file gì?
2. `javac -h` có biên dịch phần thân C/C++ không?
3. Class nào sẽ có generated header?
4. `@Native` có tác dụng gì đối với constant?
5. Vì sao header có `JNIEXPORT` và `JNICALL`?
6. Hai tham số đầu của JNI native function là gì?
7. Tham số JNI thứ hai khác nhau thế nào giữa instance và static?
8. Vì sao overloaded native methods có tên symbol dài?
9. `jstring` khác `jobject` ở điểm nào?
10. Vì sao phải gọi `ReleaseStringUTFChars`?
11. `GetStringLength` đếm đơn vị nào?
12. `System.loadLibrary` nhận tên thư viện ở dạng nào?
13. Vì sao cần kiểm tra architecture của JVM và native library?
14. `JNIEnv` có thể dùng xuyên thread không?
15. Khi nào cần attach native thread vào JVM?
16. Vì sao phải kiểm tra pending exception sau một số JNI calls?
17. `RegisterNatives` khác dynamic symbol naming thế nào?
18. JDK hiện đại có API nào nên đánh giá thay JNI cho nhiều C function calls?
19. Vì sao Java 8 project không dùng FFM?
20. `javac -h` và native compiler cần chạy ở bước nào trong build pipeline?

**Gợi ý đáp án:** (1) Header output directory; file header JNI. (2) Không. (3) Class có native method hoặc constant @Native. (4) Đưa constant vào header. (5) Export/calling convention tương thích JNI. (6) JNIEnv* và receiver. (7) jobject cho instance, jclass cho static. (8) Phân biệt signature. (9) jstring là kiểu JNI chuyên biệt cho Java String. (10) Giải phóng buffer/handle đã lấy. (11) UTF-16 code units. (12) Tên logic không extension. (13) Binary/ABI phải khớp process. (14) Không. (15) Native-created thread muốn gọi JNI. (16) Tránh gọi API không hợp lệ khi exception đang pending. (17) Đăng ký function pointer tường minh thay vì tra symbol theo tên. (18) Foreign Function & Memory API từ JDK22. (19) FFM chưa có trong Java 8. (20) Compile Java/header trước, rồi build native library.

## Tổng kết

`javac -h` tạo header JNI từ class Java có native methods hoặc constant `@Native`. Header cung cấp prototype và tên symbol chuẩn để C/C++ triển khai đúng hợp đồng Java. Quy trình đầy đủ gồm **khai báo native method → compile Java và sinh header → viết C/C++ → build thư viện theo OS/architecture → nạp bằng System.loadLibrary → chạy integration test**. Header không phải binary, compile Java không chứng minh native linking thành công. Giữ đúng kiểu JNI, signature overload, static/instance receiver, quản lý memory/reference/exception và native access. Với JDK22+, đánh giá FFM trước nếu chỉ cần gọi native functions thông thường; dùng JNI khi tương thích hiện hữu hoặc yêu cầu native method thực sự cần nó.

### Tài liệu chính thức hiện hành

- [Oracle Java SE 25 — javac command và tùy chọn -h](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [Oracle Java SE 26 — JNI Introduction](https://docs.oracle.com/en/java/javase/26/docs/specs/jni/intro.html)
- [Oracle Java SE 26 — JNI Design Overview, native symbol names and arguments](https://docs.oracle.com/en/java/javase/26/docs/specs/jni/design.html)
- [Oracle Java SE 26 — JNI Functions](https://docs.oracle.com/en/java/javase/26/docs/specs/jni/functions.html)
- [Oracle Java SE 26 — JNI Invocation API and library loading](https://docs.oracle.com/en/java/javase/26/docs/specs/jni/invocation.html)
- [Oracle Java SE 26 — java.lang.foreign](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Oracle Java SE 26 — Restricted Methods and native access](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/doc-files/RestrictedMethods.html)
