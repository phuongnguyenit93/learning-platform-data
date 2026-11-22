# Biên dịch, liên kết và xuất ký hiệu của thư viện dùng chung cho JNI đầu tiên

Khai báo một phương thức `native` trong Java mới chỉ tạo ra **hợp đồng gọi hàm**; JVM chưa có mã máy để thực thi nó. Để một lời gọi JNI chạy được, bạn phải biên dịch mã Java, sinh prototype JNI, biên dịch mã C/C++ đúng header và ABI, liên kết thành **thư viện dùng chung** (shared library), cho JVM tìm và nạp thư viện, rồi bảo đảm thư viện **xuất đúng ký hiệu** (exported symbol) mà JVM tìm.

Bài này đi trọn chuỗi đó với Java 17+ và C11. Kết quả cuối cùng là chạy được `demo.NativeMath.add(7, 35)` từ Java, nhận `42` từ mã native; biết kiểm tra thư viện `.so`, `.dylib`, `.dll` và lần theo nguyên nhân khi gặp `UnsatisfiedLinkError`.

## 1. Phân biệt biên dịch, liên kết, nạp thư viện và liên kết phương thức JNI

~~~text
NativeMath.java
    |
    | javac -h ... -d ...
    +--> NativeMath.class ---------------------+
    |                                         |
    +--> demo_NativeMath.h                    |
                |                             |
nativemath.c ---+                             |
    |                                         |
    | C compiler: compile -c                  |
    v                                         |
nativemath.o / nativemath.obj                 |
    |                                         |
    | Native linker: -shared / -dynamiclib     |
    v                                         |
libnativemath.so / libnativemath.dylib         |
               / nativemath.dll              |
    |                                         |
    | System.loadLibrary("nativemath")         |
    v                                         v
       JVM nạp thư viện, tra ký hiệu Java_demo_NativeMath_add
                           |
                           v
                        gọi JNI
~~~

Các bước có nghĩa khác nhau:

1. **Biên dịch Java:** `javac` kiểm tra kiểu, tạo `.class` và (với `-h`) tạo header C cho các khai báo `native`; nó **không** biên dịch C và cũng không cung cấp thư viện native.
2. **Biên dịch C/C++:** compiler biến từng source thành object file `.o`/`.obj`; phải có `jni.h`, header do `javac -h` tạo và các header dự án trong include path.
3. **Liên kết native:** linker ghép object file cùng các dependency cần thiết thành một shared library mang định dạng của hệ điều hành: ELF `.so` (Linux), Mach-O `.dylib` (macOS), PE `.dll` (Windows).
4. **Nạp lúc chạy:** `System.loadLibrary` yêu cầu JVM/OS tìm và load file thư viện cùng những dependency của nó. Không tìm được file hoặc không load được đều có thể gây `UnsatisfiedLinkError`.
5. **Liên kết phương thức JNI:** lúc phương thức `native` được resolve, JVM tìm export có tên và signature JNI phù hợp (hoặc bản đăng ký qua `RegisterNatives`). Load được `.so/.dll` **chưa chứng minh** phương thức đã được gắn thành công.

Một thư viện **tĩnh** (`.a` hoặc `.lib` tĩnh) là tập object để linker sử dụng khi tạo binary; nó không thay thế trực tiếp cho shared library mà `System.loadLibrary` nạp theo cách thông thường. Trên Windows, file `.lib` cũng có thể là **import library** cho một `.dll`: cần phân biệt vai trò theo đầu ra linker và toolchain.

| Giai đoạn | Đầu vào chính | Đầu ra / lỗi tiêu biểu |
| --- | --- | --- |
| `javac` | `.java` | `.class`, `.h`; lỗi kiểu Java hoặc khai báo sai |
| C compiler (`-c`) | `.c` + `.h` | `.o`/`.obj`; thiếu header, sai prototype, syntax error |
| Native linker | object files + libraries | `.so/.dylib/.dll`; `undefined reference`, `unresolved external symbol` |
| OS/JVM loader | binary native + dependencies | image đã nạp hoặc lỗi thiếu file, sai kiến trúc, thiếu dependency |
| JNI method lookup | Java declaration + exported name/registration | native được gọi hoặc `UnsatisfiedLinkError` do thiếu symbol/signature |

## 2. Chuẩn bị môi trường và cấu trúc thư mục

Bạn cần JDK 17 trở lên (có `javac`, `java`, `jni.h`), trình biên dịch C và linker cùng kiến trúc với JVM (64 bit với 64 bit, ARM64 với ARM64...), và terminal tương ứng. Sử dụng **JDK đang chạy chương trình** để lấy header JNI khi build; xác minh `JAVA_HOME` trỏ đến thư mục JDK thực tế, không phải thư mục `bin` hay JRE thiếu header.

Kiểm tra:

~~~sh
java -version
javac -version
echo "$JAVA_HOME"
~~~

Trên Windows Command Prompt:

~~~bat
java -version
javac -version
echo %JAVA_HOME%
~~~

Trong JDK, hai thư mục include thường được dùng:

- `$JAVA_HOME/include`: chứa `jni.h` và header dùng chung.
- `$JAVA_HOME/include/linux`, `darwin` hoặc `win32`: chứa `jni_md.h` và những khai báo theo nền tảng.

Ví dụ dự án:

~~~text
native-demo/
├── src/
│   └── demo/
│       └── NativeMath.java
├── native/
│   └── nativemath.c
└── build/                   (được tạo trong quá trình build)
    ├── classes/
    ├── include/
    └── lib/
~~~

Từ đây mọi lệnh được chạy ở thư mục `native-demo`. Source gồm **hai tệp** `src/demo/NativeMath.java` và `native/nativemath.c`; các thư mục `build` là output. Đường dẫn ở ví dụ không chứa khoảng trắng để lệnh ngắn, nhưng khi dự án thực có khoảng trắng bạn phải quote đường dẫn thích hợp.

Không hard-code đường dẫn đến một JDK bất kỳ từ máy khác: build trên hệ điều hành đích bằng bộ compiler/headers/architecture tương thích rồi đóng gói binary tương ứng.

## 3. Bước 1: khai báo phương thức native bên Java

Tạo `src/demo/NativeMath.java` với nội dung hoàn chỉnh:

~~~java
package demo;

public final class NativeMath {
    private NativeMath() {
    }

    static {
        System.loadLibrary("nativemath");
    }

    public static native long add(int left, int right);

    public static void main(String[] args) {
        System.out.println("7 + 35 = " + add(7, 35));
    }
}
~~~

Giải thích từng điểm:

- `package demo` là một phần **tên nhị phân** của lớp, và cũng ảnh hưởng đến tên symbol theo chuẩn JNI.
- `native` nói thân hàm nằm ở ngoài bytecode Java; trong source Java nó kết thúc bằng dấu `;`, không có block triển khai.
- `static` khiến tham số JNI thứ hai là `jclass`; nếu đây là phương thức đối tượng thì tham số thứ hai phải là `jobject`.
- Java `int` tương ứng JNI `jint`, Java `long` tương ứng JNI `jlong`; ví dụ trả về `long` để phép cộng của hai `int` không gây overflow kiểu cộng 32 bit.
- `System.loadLibrary("nativemath")` dùng tên **logic** của thư viện, không truyền phần mở rộng, tiền tố `lib` hay đường dẫn file. JVM ánh xạ sang tên hệ điều hành.
- Khối `static` chạy khi lớp khởi tạo; lỗi load thường xuất hiện tại thời điểm này, trước khi thân `main` gọi phương thức native.

Nếu muốn load một tệp bằng đường dẫn tuyệt đối, dùng `System.load(absolutePath)`, nhưng khi đó bạn phải cung cấp tên file đầy đủ và path tuyệt đối. Cách chọn loader không thay thế việc giải quyết những thư viện phụ thuộc mà OS loader cần.

### 3.1. Sinh class và JNI header: `javac -h`

Linux/macOS:

~~~sh
mkdir -p build/classes build/include build/lib
javac -h build/include -d build/classes src/demo/NativeMath.java
~~~

Windows Command Prompt:

~~~bat
mkdir build\classes build\include build\lib
javac -h build\include -d build\classes src\demo\NativeMath.java
~~~

Sau lệnh, những tệp quan trọng gồm:

~~~text
build/classes/demo/NativeMath.class
build/include/demo_NativeMath.h
~~~

`-d` đặt class file vào thư mục chứa cấu trúc package; `-h` đặt header JNI vào thư mục chỉ định. Đừng thay `-h` bằng cách tự gõ symbol theo cảm tính. Mỗi khi đổi package, lớp, `native` method, overload hay kiểu tham số/trả về, **tái sinh header** và build lại mã C/C++.

Bản header do `javac -h` tạo sẽ có khai báo tương đương đoạn sau (đây là đoạn trích minh họa, **không thay thế toàn bộ tệp header đã sinh**):

~~~c
#include <jni.h>

/*
 * Class:     demo_NativeMath
 * Method:    add
 * Signature: (II)J
 */
JNIEXPORT jlong JNICALL Java_demo_NativeMath_add
  (JNIEnv *, jclass, jint, jint);
~~~

`(II)J` là JVM method descriptor: hai đối số `I` = `int`, kết quả `J` = `long`. Java method descriptor và tên C ABI là hai khái niệm khác nhau: descriptor dùng mô tả kiểu, còn exported symbol là tên mà runtime/linker nhìn thấy.

Có thể kiểm tra descriptor từ class đã biên dịch:

~~~sh
javap -s -classpath build/classes demo.NativeMath
~~~

Trong kết quả, phương thức tương ứng có descriptor `(II)J`. Đừng tự suy ra điều này từ tên file `.java` nếu project có package/overload phức tạp; compiler và `javap` là nguồn xác minh trực tiếp.

## 4. Bước 2: triển khai đúng prototype và export JNI trong C

Tạo `native/nativemath.c`:

~~~c
#include "demo_NativeMath.h"

JNIEXPORT jlong JNICALL
Java_demo_NativeMath_add(JNIEnv *env, jclass declaring_class,
                         jint left, jint right) {
    (void) env;
    (void) declaring_class;

    return (jlong) left + (jlong) right;
}
~~~

Đây là **mã C hoàn chỉnh cho phần native** của ví dụ. Nó không có `main` vì entry point là hàm JNI được JVM gọi sau khi nạp thư viện. Đừng chạy `nativemath.c` như một chương trình C độc lập.

Chữ ký JNI có bốn phần không thể tùy tiện thay đổi:

1. `JNIEXPORT`: khai báo visibility/export phù hợp nền tảng trong bộ header JNI; đặc biệt cần trên Windows để DLL có symbol xuất ra.
2. `jlong`: kiểu trả về tương ứng Java `long`.
3. `JNICALL`: calling convention theo JNI/target ABI. Trên 32-bit Windows điều này đặc biệt quan trọng; không bỏ vì thấy lệnh chạy trên máy 64 bit.
4. `Java_demo_NativeMath_add(JNIEnv *, jclass, jint, jint)`: tên theo JNI, interface pointer, class của phương thức static và hai đối số.

Bộ header `jni.h`/`jni_md.h` cung cấp các macro và kiểu. Khai báo trong `demo_NativeMath.h` giúp compiler phát hiện signature không khớp thay vì để lỗi trôi đến runtime.

Dòng `(jlong) left + (jlong) right` thực hiện cộng trong miền 64 bit. Nếu cộng trực tiếp `left + right` trước khi ép kiểu, hai số nguyên 32 bit ở C có thể overflow, dẫn tới undefined behavior. Hai `jint` 32 bit cộng sau khi mở rộng lên `jlong` 64 bit luôn nằm trong miền `jlong`.

Hai tham số `env` và `declaring_class` hiện không cần dùng; `(void)` để compiler không cảnh báo unused parameter với các cờ warning. Trong ví dụ cần gọi JNI API, `env` là interface đến JVM, không phải pointer tùy ý có thể dùng ở thread khác.

### 4.1. Export symbol khác với làm hàm `public` trong Java

Java `public` quyết định quyền truy cập Java; nó không xuất symbol native. Bên native, tên symbol, visibility và calling convention mới quyết định runtime có tìm được hàm JNI hay không.

Ví dụ trên Linux, khi export đúng, dynamic symbol table chứa `Java_demo_NativeMath_add`. Nếu build với `-fvisibility=hidden` cho dự án C/C++ lớn, `JNIEXPORT` vẫn được thiết kế để đánh dấu entry point JNI cần hiển thị với linker/loader. Nếu tự định nghĩa wrapper API khác, nó có thể cần quy tắc export riêng.

Không sửa tên hàm C thành `add` chỉ vì Java đặt tên `add`: JVM sử dụng quy tắc JNI hoặc `RegisterNatives`, không tự động ánh xạ tên C tùy ý.

## 5. Bước 3 và 4 trên Linux: compile object rồi link `.so`

Điều kiện: shell POSIX, C compiler như GCC/Clang, `JAVA_HOME` đã trỏ đến JDK, chạy tại `native-demo`.

~~~sh
cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  -c native/nativemath.c -o build/nativemath.o

cc -shared build/nativemath.o -o build/lib/libnativemath.so
~~~

Lệnh đầu **biên dịch** ra object file; lệnh sau **liên kết** object đó thành shared object. Bạn cũng có thể gộp thành một lệnh để compiler driver tự thực hiện cả hai bước:

~~~sh
cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  native/nativemath.c -o build/lib/libnativemath.so
~~~

Giải nghĩa cờ:

- `-std=c11`: chọn dialect C; `-Wall -Wextra -Wpedantic`: phát hiện nhiều vấn đề ở compile time (không bảo đảm toàn bộ lỗi được bắt).
- `-O2`: tối ưu trong bản build thông thường; để debug có thể thay bằng `-O0 -g`.
- `-I...`: thêm đường tìm **header** ở lúc compile, không phải đường tìm library lúc chạy.
- `-fPIC`: tạo position-independent code thích hợp khi ghép thành shared object trên nhiều target ELF; thiếu cờ có thể gây lỗi relocation lúc link.
- `-c`: chỉ compile, không link; `-o build/nativemath.o` đặt tên object output.
- `-shared`: tạo shared library; `-o build/lib/libnativemath.so` chọn tên output.
- Đưa object vào lệnh link; với external library, thứ tự object và `-l...` có thể ảnh hưởng đến khả năng resolve symbol trên một số linker.

Tại sao tên là `libnativemath.so`? Với Java `System.loadLibrary("nativemath")`, tên logic `nativemath` thường được JVM ánh xạ sang `libnativemath.so` trên Linux. Không viết `System.loadLibrary("libnativemath.so")`.

### 5.1. Chạy từ Java

~~~sh
java -Djava.library.path=build/lib -cp build/classes demo.NativeMath
~~~

Khi biên dịch và nạp đúng, **stdout chính xác**:

~~~text
7 + 35 = 42
~~~

`-cp build/classes` chỉ classpath cho bytecode Java; `-Djava.library.path=build/lib` cung cấp vị trí để JVM tìm thư viện JNI. Hai đường dẫn này giải quyết **hai loại file khác nhau**. Đặt `-Djava.library.path` trước tên main class, vì đây là JVM option.

Lệnh không cần đặt `libnativemath.so` trong cùng thư mục `.class`; chỉ cần thư viện nằm ở nơi loader có thể tìm theo cơ chế được chỉ định.

## 6. Bước 3 và 4 trên macOS: compile rồi tạo `.dylib`

Sử dụng JDK dành cho macOS cùng kiến trúc (Apple Silicon/Intel) và compiler Clang. Giữ nguyên hai file nguồn Java/C:

~~~sh
mkdir -p build/classes build/include build/lib
javac -h build/include -d build/classes src/demo/NativeMath.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include \
  -c native/nativemath.c -o build/nativemath.o

cc -dynamiclib build/nativemath.o -o build/lib/libnativemath.dylib
java -Djava.library.path=build/lib -cp build/classes demo.NativeMath
~~~

Output vẫn là:

~~~text
7 + 35 = 42
~~~

Trên macOS, `-dynamiclib` là lựa chọn chuẩn của toolchain Clang để tạo dynamic library; khác `-shared` trong ví dụ Linux. Tên file tương ứng thông thường là `libnativemath.dylib`. Một số môi trường JNI cũ còn nhắc `.jnilib`; với build hiện đại, dùng tên JVM ánh xạ được trên target JDK và kiểm chứng trực tiếp bằng ví dụ ở phần 9.

Nếu build Java chạy trên Apple Silicon nhưng file `.dylib` chứa binary Intel-only, hoặc ngược lại, loader có thể báo lỗi không tương thích architecture. Đừng sửa lỗi này bằng cách đổi đuôi file: phải build đúng target/architecture hoặc tạo universal binary theo quy trình phù hợp.

## 7. Bước 3 và 4 trên Windows: MSVC, `.dll` và export

Ví dụ Windows dùng **x64 Native Tools Command Prompt for VS** hoặc Developer Command Prompt có `cl` và `link` trong `PATH`. Đặt `JAVA_HOME` đến bản JDK Windows x64 tương ứng. Các lệnh dưới đây là **Command Prompt**, không dùng cú pháp biến môi trường của PowerShell.

~~~bat
mkdir build\classes build\include build\lib
javac -h build\include -d build\classes src\demo\NativeMath.java

cl /nologo /W4 /O2 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /I"build\include" ^
  native\nativemath.c ^
  /link /OUT:build\lib\nativemath.dll

java -Djava.library.path=build\lib -cp build\classes demo.NativeMath
~~~

Dấu `^` là ký tự nối dòng trong Windows Command Prompt; nếu copy lệnh vào môi trường khác, hãy chuyển thành một dòng hoặc dùng cú pháp shell tương ứng. Nếu đặt `JAVA_HOME` chứa dấu cách, quote như ví dụ.

Output:

~~~text
7 + 35 = 42
~~~

Ở MSVC, `/LD` yêu cầu build DLL, và `/OUT:...dll` chọn file output. `JNIEXPORT` trong JDK Windows mở rộng thành cơ chế export DLL phù hợp, nên một JNI function được khai báo đúng thường xuất hiện trong export table. Các file trung gian `.obj`, `.exp`, `.lib` có thể được linker tạo thêm; Java nạp **`nativemath.dll`**, không nạp `nativemath.lib`.

Nếu dùng MinGW-w64 thay MSVC, cần compiler GCC tương thích target Windows/kiến trúc/JDK, thay include platform bằng `win32` và tạo `nativemath.dll` với `-shared`. Không gộp bừa các object, runtime library và import library từ toolchain khác ABI khi chưa xác minh tương thích.

**Khác biệt Windows cần nhớ:** khi Windows báo không load được DLL, có thể lỗi ở chính `nativemath.dll`, sai bitness, hoặc một DLL **phụ thuộc** bị thiếu. Chỉ nhìn sự tồn tại của file đích chưa đủ để kết luận library có thể load được.

## 8. Xem thư viện đã xuất đúng symbol chưa

Sau khi build, cần kiểm tra **native dynamic/export symbol table**. Các lệnh này là lệnh kiểm tra, không làm thay đổi file:

| Hệ điều hành | Lệnh kiểm tra | Điều cần thấy |
| --- | --- | --- |
| Linux | `nm -D --defined-only build/lib/libnativemath.so` | Có `Java_demo_NativeMath_add` trong dynamic defined symbols |
| Linux | `readelf -Ws build/lib/libnativemath.so` | Symbol có binding/visibility phù hợp và được định nghĩa |
| macOS | `nm -gU build/lib/libnativemath.dylib` | Có `_Java_demo_NativeMath_add` (dấu gạch dưới đầu thường do công cụ Mach-O hiển thị) |
| Windows/MSVC | `dumpbin /exports build\lib\nativemath.dll` | Có tên export JNI cho phương thức |
| Linux/macOS | `file build/lib/libnativemath.so` / `file build/lib/libnativemath.dylib` | Format và kiến trúc binary khớp target |

Ví dụ Linux lọc chính xác symbol:

~~~sh
nm -D --defined-only build/lib/libnativemath.so | grep Java_demo_NativeMath_add
~~~

Dòng kết quả dạng minh họa (giá trị địa chỉ khác nhau theo build):

~~~text
0000000000001100 T Java_demo_NativeMath_add
~~~

`T` thông thường biểu thị symbol nằm trong vùng code/text được định nghĩa. Trên Linux, `nm` thiếu `-D` có thể liệt kê symbol table thường, trong khi loader cần symbol mà nó có thể tìm trong **dynamic symbol table**; dùng `nm -D` hoặc `readelf -Ws` cho câu hỏi export lúc runtime.

macOS:

~~~sh
nm -gU build/lib/libnativemath.dylib | grep Java_demo_NativeMath_add
otool -L build/lib/libnativemath.dylib
~~~

Windows (Developer Command Prompt):

~~~bat
dumpbin /exports build\lib\nativemath.dll
dumpbin /dependents build\lib\nativemath.dll
~~~

Nếu export tên bị sai, có thể Java load thư viện thành công nhưng chỉ ném `UnsatisfiedLinkError` **khi gọi phương thức native**. Nếu thư viện có symbol nhưng DLL/shared library còn thiếu dependency hoặc sai kiến trúc, lỗi xuất hiện sớm hơn khi load.

### 8.1. Ý nghĩa `JNIEXPORT`, `JNICALL` và C++ name mangling

Trong C++, tên function thường bị **name mangling** để mã hóa namespace và kiểu tham số. JVM theo quy tắc JNI tìm `Java_demo_NativeMath_add`, chứ không tự hiểu một tên C++ bị mangling khác. Nếu đổi `native/nativemath.c` thành `native/nativemath.cpp` và biên dịch C++, hãy định nghĩa entry point bằng **C language linkage**:

~~~cpp
#include "demo_NativeMath.h"

extern "C" JNIEXPORT jlong JNICALL
Java_demo_NativeMath_add(JNIEnv *env, jclass declaring_class,
                         jint left, jint right) {
    (void) env;
    (void) declaring_class;
    return (jlong) left + (jlong) right;
}
~~~

`extern "C"` giữ C linkage cho tên symbol; `JNIEXPORT` giải quyết export/visibility; `JNICALL` xác định convention gọi. Ba khái niệm khác nhau và không thể tùy tiện thay cho nhau.

Header do `javac -h` tạo thường đã bọc prototype bằng guard `extern "C"` khi compile C++, nhưng ghi rõ trên phần triển khai giúp người đọc nhận ra ABI contract. Khi đổi sang C++, sử dụng compiler driver `c++`/`g++`/`clang++` hoặc `cl` ở chế độ C++ cho cả bước compile và link phù hợp, bởi thư viện có thể cần C++ runtime. Đừng chỉ đổi đuôi source rồi tiếp tục giả định liên kết như C thuần.

### 8.2. Tên JNI cho overloaded methods

Với phương thức không có overload native, tên ngắn của ví dụ là:

~~~text
Java_demo_NativeMath_add
~~~

Nếu có **nhiều phương thức native cùng tên** trong một lớp, JNI dùng tên dài chứa mã hóa kiểu tham số, ví dụ cho cặp `(int, int)` có hậu tố `__II`. JVM có quy tắc tra tên ngắn trước rồi đến tên dài; các trường hợp overload không nên được xử lý bằng cách phỏng đoán thủ công.

Những ký tự trong package/lớp/method cũng có quy tắc escape (chẳng hạn dấu gạch dưới trong tên Java được mã hóa đặc biệt), nên **luôn** chạy lại `javac -h`. Rename `demo.NativeMath` thành tên package khác mà không build lại `nativemath.c` là một nguyên nhân điển hình khiến export tồn tại nhưng JVM không tìm đúng method.

`RegisterNatives` là lựa chọn khác: native code đăng ký function pointer theo tên/descriptor, thường từ `JNI_OnLoad`. Khi đó entry point Java của từng hàm **không nhất thiết** phải xuất dưới tên `Java_...`, nhưng symbol `JNI_OnLoad` và logic đăng ký phải được export/triển khai đúng. Với **JNI đầu tiên**, cách dùng tên xuất tự động từ `javac -h` là con đường dễ kiểm chứng và ít thành phần nhất.

## 9. Phân biệt ba đường dẫn: include path, library link path và runtime search path

Ba kiểu path thường bị nhầm:

| Path | Dùng khi nào | Ví dụ |
| --- | --- | --- |
| Header include path | C compiler đọc khai báo | `-I"$JAVA_HOME/include"`, `-Ibuild/include` |
| Linker library search path | Native linker tìm `-lfoo` hoặc import library | `-Lvendor/lib -lfoo`, MSVC `/LIBPATH:...` |
| Runtime shared-library search path | JVM/OS loader nạp `.so/.dylib/.dll` và dependency | `-Djava.library.path=build/lib`, system loader paths, rpath/runpath, OS-specific mechanisms |

`-I` không giúp JVM tìm `libnativemath.so`. `-Djava.library.path` không giúp C compiler tìm `jni.h`. `-L` giúp native **link** tới dependency, nhưng không bảo đảm OS tìm được dependency đó **lúc chạy**.

### 9.1. Khi thư viện JNI gọi một thư viện native khác

Giả sử `nativemath.c` gọi hàm từ `libhelper.so` (đã có header và library), thì trên Linux lệnh link có thể cần dạng:

~~~sh
cc -shared build/nativemath.o \
  -Lvendor/lib -lhelper \
  -o build/lib/libnativemath.so
~~~

Đây là **mẫu minh họa** cho một dependency bổ sung, không chạy độc lập nếu thiếu `libhelper.so` và những khai báo/định nghĩa cần thiết. `-lhelper` khiến linker tìm library có tên hợp lệ theo quy tắc toolchain, thường `libhelper.so` hoặc `libhelper.a` ở các thư mục tìm kiếm. Cần phân biệt link động hay link tĩnh: file được chọn ảnh hưởng đến dependency khi deploy.

Nếu link thành công mà `libhelper.so` không có trong loader path lúc chạy, `System.loadLibrary("nativemath")` vẫn có thể thất bại. Kiểm tra:

~~~sh
readelf -d build/lib/libnativemath.so
ldd build/lib/libnativemath.so
~~~

`readelf -d` thể hiện metadata như `NEEDED`, `RPATH`/`RUNPATH` nếu có; `ldd` hiển thị dependency resolution trong môi trường cụ thể và chỉ nên chạy với binary đáng tin cậy. Nếu dependency nằm cạnh `libnativemath.so` trong một bộ package Linux, linker có thể nhúng runtime search path tương đối bằng `$ORIGIN`; sử dụng rpath/runpath phải được thiết kế nhất quán với layout bản phát hành:

~~~sh
cc -shared build/nativemath.o \
  -Lbuild/lib -lhelper \
  -Wl,-rpath,'$ORIGIN' \
  -o build/lib/libnativemath.so
~~~

Mẫu trên giả định `libhelper.so` đã nằm trong `build/lib` lúc link và deploy cùng thư mục thư viện JNI. Dấu quote đơn bảo toàn `$ORIGIN` để **dynamic loader** mở rộng lúc chạy, thay vì shell thay biến quá sớm. Trên macOS thường sử dụng khái niệm `@loader_path`, còn Windows dùng quy tắc tìm DLL/loader riêng; không sao chép cờ Linux sang hệ khác.

**Không cần link trực tiếp `libjvm.so` chỉ để triển khai hàm JNI cơ bản** như ví dụ: các thao tác JNI được gọi qua bảng hàm `JNIEnv`. Nếu C ứng dụng dùng Invocation API để tự tạo JVM hoặc trực tiếp gọi các symbol ngoài interface đó, điều kiện link sẽ khác.

## 10. Phân biệt lỗi ở thời điểm build, load và gọi JNI

Các tình huống sau giúp chẩn đoán đúng tầng:

| Triệu chứng | Nguyên nhân có thể | Kiểm tra / hướng sửa |
| --- | --- | --- |
| `jni.h: No such file or directory` | Thiếu đường include JDK | Xác nhận `JAVA_HOME` và `-I.../include` |
| `jni_md.h: No such file or directory` | Thiếu thư mục include của OS | Thêm `-I.../linux`, `darwin` hoặc `win32` |
| `conflicting types for Java_...` | Source C không khớp generated header | Build lại bằng `javac -h`; đối chiếu static/instance, return và argument |
| `relocation ... recompile with -fPIC` | Object không phù hợp link vào `.so` | Biên dịch lại object với `-fPIC` trước khi link |
| `undefined reference` hoặc `unresolved external symbol` | Thiếu object/library hoặc sai signature/link order | Xác định symbol unresolved, thêm object/`-l`/import library chính xác |
| `no nativemath in java.library.path` | JVM không tìm thấy thư viện theo tên/path | Xem `-Djava.library.path` và tên file chuẩn trên OS |
| `Can't load ... / wrong ELF class`, lỗi `Bad CPU type` hoặc `not a valid Win32 application` | Binary sai kiến trúc hoặc format | Kiểm tra 32/64 bit, x86_64/ARM64, OS và toolchain |
| `libhelper.so: cannot open shared object file` / thiếu DLL phụ | Thư viện chính có dependency chưa resolve | `readelf/ldd`, `otool -L`, `dumpbin /dependents`, layout package |
| `UnsatisfiedLinkError: 'long demo.NativeMath.add(int, int)'` (thông báo cụ thể phụ thuộc JVM) | Library load được nhưng method chưa resolve | `nm -D`/`dumpbin /exports`, header, method signature, đăng ký native |
| JVM crash khi vào native method | Prototype/ABI sai hoặc lỗi bộ nhớ C | So lại header và calling convention, bật debugger/sanitizer, `-Xcheck:jni` |

Hãy xử lý theo thứ tự:

1. **Có class và header mới nhất chưa?** Kiểm tra `javap -s`, file `demo_NativeMath.h` và đúng JDK.
2. **C compiler có tạo object thành công chưa?** Nếu chưa, đây là lỗi compile (headers/syntax/types).
3. **Linker có tạo shared library hợp lệ chưa?** Nếu chưa, giải quyết object, flags, unresolved symbol và dependency.
4. **Thư viện có đúng kiến trúc và ở đúng path JVM tìm không?** Dùng `file`/`dumpbin`, path, loader diagnostic.
5. **Export có đúng JNI name và linkage không?** Dùng `nm`/`readelf`/`dumpbin` và so với header sinh ra.
6. **Nếu đã gọi được mà kết quả sai/crash**, xem ABI, memory lifetime, pointer, exception và logic native; đừng tiếp tục đổi path khi lỗi nằm trong mã đang chạy.

### 10.1. Hai lỗi `UnsatisfiedLinkError` rất khác nhau

**Tình huống A — lỗi khi khởi tạo lớp:**

~~~text
java.lang.UnsatisfiedLinkError: no nativemath in java.library.path: ...
~~~

JVM chưa tìm/load được thư viện logic `nativemath`. Hãy kiểm tra vị trí file, tên platform, architecture, permissions và dependency. Tên text cụ thể có thể khác giữa các bản JVM.

**Tình huống B — lỗi khi gọi native:**

~~~text
java.lang.UnsatisfiedLinkError: 'long demo.NativeMath.add(int, int)'
~~~

Library có thể đã load, nhưng JVM không tìm thấy implementation khớp. Kiểm tra symbol `Java_demo_NativeMath_add` hoặc logic `RegisterNatives`, bảo đảm C source được rebuild sau khi Java signature đổi, kiểm tra name mangling C++ và symbol visibility. Không giải quyết lỗi B chỉ bằng cách chuyển `.so` sang thư mục classpath.

### 10.2. Kiểm tra bằng JVM và native tools

Có thể thêm `-Xcheck:jni` khi chạy để nhận thêm kiểm tra JNI do JVM hỗ trợ:

~~~sh
java -Xcheck:jni -Djava.library.path=build/lib \
  -cp build/classes demo.NativeMath
~~~

Cờ này giúp phát hiện một số cách dùng JNI API sai, nhưng **không thay thế** việc kiểm tra toàn bộ lỗi con trỏ, overflow và ABI trong C/C++. Khi gặp crash native, debugger (gdb/lldb/Visual Studio) cùng symbol debug từ `-g` hoặc `/Zi` hữu ích hơn chỉ nhìn Java stack trace.

Tự hỏi “lỗi xuất hiện khi `javac`, khi `cc/cl`, khi `System.loadLibrary` hay khi gọi `add`?” thường giúp khoanh vùng nhanh hơn thử ngẫu nhiên các flag.

## 11. Export symbol trong dự án nhiều tệp và build release

Khi dự án tăng lên, tách hàm tiện ích native thành object riêng. Luồng build vẫn là: **mỗi source -> một object -> một shared library**. Ví dụ nếu có thêm `native/helper.c` và code đã gọi một hàm được khai báo trong `helper.h`, Linux cần compile cả hai:

~~~sh
cc -std=c11 -fPIC -Ibuild/include \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -Inative -c native/nativemath.c -o build/nativemath.o

cc -std=c11 -fPIC -Inative \
  -c native/helper.c -o build/helper.o

cc -shared build/nativemath.o build/helper.o \
  -o build/lib/libnativemath.so
~~~

Đây là ví dụ mở rộng **chỉ hợp lệ sau khi bạn thật sự thêm helper.c/helper.h cùng lời gọi tương ứng**. Nếu chỉ tạo `nativemath.o` mà quên `helper.o`, linker có thể báo unresolved reference; với một số linker/build mode, lỗi còn có thể lộ lúc load/call. Giới hạn symbol export ở các entry point cần thiết giúp API native rõ hơn, đặc biệt khi thư viện sử dụng C++.

Khi build release, lưu ý:

- **ABI và platform:** build theo OS + CPU architecture + toolchain tương thích; Linux `.so` không dùng thay Windows `.dll`; đừng nghĩ sửa extension là đủ.
- **JDK headers:** lấy từ JDK mục tiêu; tránh dùng header đã copy từ bản JDK/OS khác mà không kiểm tra tương thích.
- **Library name:** Java gọi tên logic một cách nhất quán; mỗi nền tảng đóng gói file theo convention của nó.
- **Reproducibility:** script build nên tái sinh `.h` sau mỗi thay đổi `native`, loại bỏ object cũ và chạy smoke test JNI thật.
- **Visibility:** export symbol JNI và callback/hook được runtime cần dùng, giữ hàm nội bộ private nếu phù hợp; `JNI_OnLoad` cần đúng signature và export nếu dùng.
- **Dependencies:** phát hành cả thư viện native phụ thuộc hợp lệ, cấu hình runtime loader tương thích layout deployment, license và kiến trúc đích.
- **Threads và initialization:** nếu dùng `JNI_OnLoad` để đăng ký/hook, xử lý status trả về và không giữ `JNIEnv *` của thread này cho thread khác.
- **Kiểm thử:** thử cả build Debug/Release và runtime với Java đúng version/architecture; kiểm tra symbols thực tế sau bước link.

### 11.1. Về `JNI_OnLoad`

Đây là entry point **tùy chọn** để thư viện native làm việc khởi tạo JNI khi được load. Khi khai báo, pattern thường có dạng:

~~~c
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void) vm;
    (void) reserved;
    return JNI_VERSION_1_8;
}
~~~

Đây là **đoạn minh họa**, chưa có thao tác đăng ký/khởi tạo; để dùng độc lập phải include `jni.h` và link vào shared library. `JNI_VERSION_1_8` biểu thị mức phiên bản JNI mà library yêu cầu, **không có nghĩa chương trình chỉ chạy Java 8**. Nếu `JNI_OnLoad` trả version JNI không được VM hỗ trợ, load sẽ thất bại.

Với bài đầu tiên không cần thêm `JNI_OnLoad`; JVM tìm `Java_demo_NativeMath_add` theo convention. Khi chuyển sang `RegisterNatives`, cần hiểu rõ method descriptor `(II)J` và đăng ký con trỏ hàm tương ứng với Java declaration.

## 12. Bài tự kiểm tra để củng cố compile/link/export

1. **Đổi tên library logic.** Thay `System.loadLibrary("nativemath")` thành `"othermath"` nhưng chưa đổi file. Dự đoán lỗi xảy ra ở bước nào; sau đó trả lại tên đúng.
2. **Đổi Java method từ `add` thành `sum`.** Chạy lại `javac -h`. Quan sát generated header đổi thành `Java_demo_NativeMath_sum`, rồi cập nhật source C; kiểm tra export sau build.
3. **Đổi `static native` thành instance `native`.** Generated header sẽ đổi tham số JNI thứ hai từ `jclass` thành `jobject`; sửa Java caller cho phù hợp và rebuild.
4. **Bỏ `JNIEXPORT` trong một bản thử nghiệm.** Quan sát export table, nhất là trên Windows hoặc khi build với hidden visibility; restore macro trước khi hoàn tất.
5. **Tạo lỗi load và lỗi lookup riêng biệt.** Di chuyển thư viện khỏi `build/lib` để kiểm tra lỗi loader; đặt lại thư viện nhưng cố tình xuất sai tên method để kiểm tra lỗi lookup. Khôi phục source, build và xác minh output `7 + 35 = 42`.

Khi thực hiện các bài thử trên, thay đổi từng yếu tố một và luôn chạy lại bước biên dịch + liên kết liên quan. Điều quan trọng là xác định đúng ranh giới giữa lỗi **compiler**, lỗi **linker**, lỗi **dynamic loader** và lỗi **JNI lookup**.

## 13. Checklist trước khi gọi đây là một thư viện JNI chạy được

- Java `.class` mới nhất và header `javac -h` được tạo từ cùng declaration (package, method, `static`, argument/return types).
- Hàm C/C++ có `JNIEXPORT`, `JNICALL`, JNI name/prototype đúng; C++ có C linkage; không dùng sai `jclass` và `jobject`.
- Compiler tìm thấy `jni.h`/`jni_md.h`/generated header; build object cho đúng OS/CPU/toolchain.
- Linker tạo đúng `.so/.dylib/.dll` và không thiếu object/library bắt buộc; entry point nằm trong export table.
- `System.loadLibrary` nhận **tên logic**; file nằm trong đường JVM/OS loader có thể tìm, các dependency cũng load được.
- Không nhầm `CLASSPATH`, `-I`, `-L` và `java.library.path`; xác định đúng thời điểm lỗi.
- Chạy Java thực tế và nhận đúng **`7 + 35 = 42`**; kiểm tra được exported symbol trên thư viện đã đóng gói, không chỉ trên object trung gian.
- Nếu phát hành nhiều nền tảng, có artifact riêng cho từng target và một smoke test JNI sau build.

**Mấu chốt:** “Build thành công” chỉ nói compiler/linker đã tạo file; một lần gọi JNI thành công đòi **đúng Java declaration, đúng C ABI/prototype, đúng exported symbol, đúng shared library và đúng runtime loader path**. Mỗi mắt xích đều kiểm chứng được bằng công cụ tương ứng.

### Tài liệu tham khảo chính thức

- Oracle, [JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): quy tắc tên ký hiệu, signature, load/link, `RegisterNatives`.
- Oracle, [JNI Specification — Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): bảng hàm JNI và hợp đồng xử lý tài nguyên/lỗi.
- Oracle, [JDK 17 javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): tùy chọn sinh header `-h` và output `-d`.
- Oracle, [System.loadLibrary](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#loadLibrary(java.lang.String)): cách JVM nạp library bằng tên logic.