# javac -h và quy trình sinh header JNI đang sử dụng (Java 10+)

## 1. Bài toán: từ một phương thức `native` trong Java tới một hàm C thật

Trong Java, khai báo:

```java
public static native int add(int a, int b);
```

chỉ nói rằng phương thức **được triển khai bằng mã native**. Trình biên dịch Java có thể biên dịch khai báo ấy thành bytecode, nhưng **không tự viết hàm C, không tạo thư viện .so/.dylib/.dll và không tự kết nối một file thư viện**. Để Java Native Interface (JNI) tìm được hàm đúng, ta cần một **hợp đồng ABI** giữa Java và C/C++: tên symbol, kiểu tham số, kiểu trả về, cách truyền receiver và các quy tắc vòng đời.

Trong quy trình hiện hành, công cụ tạo **C/C++ header JNI** trực tiếp là:

```bash
javac -h build/headers -d build/classes src/example/jni/NativeCalculator.java
```

Tùy chọn `-h` sinh file header khi **biên dịch source Java**. Sau đó C/C++ code **include file header được sinh**, triển khai các hàm JNI, build thành native library, và Java tải thư viện lúc chạy.

### Liên hệ trực tiếp với Java 10

- **JEP 313 — Remove the Native-Header Generation Tool (javah)** được thực hiện trong **JDK 10**: công cụ `javah` đã bị loại khỏi JDK.
- `javac -h` đã được hỗ trợ **từ JDK 8** và **vẫn là cách chính thức được tài liệu `javac` của JDK hiện hành mô tả**.
- Không áp dụng quy trình lịch sử `javah -jni ...` cho dự án mới. Cũng không giả định phải có công cụ `javah` trong một JDK 17/21/25/27 hiện đại.
- `javac -h` **không loại bỏ JNI**; nó chỉ kết hợp việc sinh header và biên dịch trong cùng công cụ.

**Mục tiêu bài:** hiểu chi tiết `-h`, cấu trúc header và JNI signatures; thực hành Java 17+, có phần C được triển khai theo header; kiểm tra kết quả biên dịch với `javap`; build thư viện trên Linux, macOS hoặc Windows; chạy với native-access policy JDK 24+; tránh các nhầm lẫn về classpath, library path và lifecycle trong CI/CD.

**Special Note:** mọi khuyến nghị kỹ thuật ở đây dựa trên JNI và `javac -h` còn được hỗ trợ trên JDK mới, không hướng dẫn dùng `javah` đã bị xóa hoặc những giao diện JVM nội bộ không ổn định.

## 2. Quy trình JNI hiện hành theo một sơ đồ

```text
src/example/jni/NativeCalculator.java
       |
       | javac --release 17 -h build/headers -d build/classes
       |
       +--> build/classes/example/jni/NativeCalculator.class
       |
       +--> build/headers/example_jni_NativeCalculator.h
                                     |
                                     | #include trong native/mathbridge.c
                                     v
                             C compiler + linker
                                     |
             +-----------------------+-----------------------+
             |                       |                       |
             v                       v                       v
   Linux: libmathbridge.so   macOS: libmathbridge.dylib   Windows: mathbridge.dll
             |                       |                       |
             +-----------------------+-----------------------+
                                     |
                         System.loadLibrary("mathbridge")
                                     |
                           JVM tìm native symbol
                                     |
                            Java method gọi hàm C
```

Cần phân biệt **bốn loại artifact**:

| Artifact | Công cụ tạo | Nơi dùng |
| --- | --- | --- |
| `NativeCalculator.class` | `javac -d` | Java classpath/module path |
| `example_jni_NativeCalculator.h` | `javac -h` | C/C++ compiler, qua `#include` |
| `mathbridge.c` | Lập trình viên viết | C compiler/linker |
| `libmathbridge.so`, `libmathbridge.dylib` hoặc `mathbridge.dll` | Native linker | JVM load lúc chạy |

File `.h` chỉ là **khai báo C và constants**. Nó **không** tự chạy, không chứa thư viện native hoàn chỉnh, cũng không được thêm vào Java classpath.

## 3. Cú pháp chính xác của `javac -h`

Theo Java SE 27 `javac` manual:

```text
-h directory
```

Chỉ định vị trí ghi **các header files được sinh**. Khi bật tùy chọn này, `javac` sinh header cho mỗi class:

1. có **ít nhất một phương thức `native`**, hoặc
2. có **ít nhất một hằng số được đánh dấu `@java.lang.annotation.Native`**.

Thư mục đích và các thư mục con cần thiết có thể được tạo khi chưa tồn tại. Với named modules, layout output có thể có thư mục phản ánh module và package theo quy định của JDK. **Đừng áp đặt một đường dẫn file cố định cho mọi module/build tool**: quan sát file thật trong `-h` destination.

### 3.1. `-h` khác `-d`

```bash
javac -h build/headers -d build/classes \
      src/example/jni/NativeCalculator.java
```

- `-h build/headers`: sinh **C header files**.
- `-d build/classes`: sinh **Java `.class` files**.
- Không trộn header và class vào cùng thư mục khi thiết kế build pipeline.
- Không sử dụng `-h` như tên file đơn lẻ: tham số cần là **directory**.
- Không gọi `javac -h` với một file `.class` để “sinh header sau biên dịch”; đó là công việc của công cụ lịch sử `javah` đã bị loại bỏ. **`javac` biên dịch source**.

### 3.2. `--release 17` có liên quan gì?

Trong ví dụ hiện hành:

```bash
javac --release 17 -encoding UTF-8 \
      -d build/classes -h build/headers \
      src/example/jni/NativeCalculator.java
```

`--release 17` bảo đảm compiler biên dịch source theo Java 17 API/bytecode compatibility. Nó **không biên dịch thư viện C tương ứng cho một kiến trúc khác**.

Một file JNI native library được build cho **OS/architecture/ABI cụ thể**, không có tính portable như `.class`. Muốn chạy trên Linux, macOS và Windows phải có **native build phù hợp từng nền tảng**.

### 3.3. Trường hợp chỉ có `@Native`

`java.lang.annotation.Native` đánh dấu một constant field để trình biên dịch đưa thông tin của nó vào header. Ví dụ:

```java
import java.lang.annotation.Native;

public final class Constants {
    @Native public static final int ABI_LEVEL = 3;
}
```

Đoạn code trên là **minh họa**. Dù class không có native method, `javac -h` vẫn có thể sinh header chứa một macro cho constant field. Trong lab bên dưới, một class vừa có `@Native` constant vừa có hai native methods nên ta quan sát cả hai loại nội dung trong cùng header.

`@Native` **không** tự biến một trường thành native allocation, không phải annotation liên quan JNI library loading, và không buộc mọi field Java phải được xuất sang C.

## 4. Chuẩn bị bài thực hành Java 17+

Bài mẫu được thiết kế để:

- phần **Java source và header** có thể được biên dịch/kiểm tra bằng JDK 17+ mà **không cần C compiler**;
- phần **native C** chỉ yêu cầu trình biên dịch phù hợp với OS;
- output kiểm chứng header có thể được xác định chính xác trên JDK đã thử;
- phần chạy native có output dự kiến rõ, nhưng chỉ đạt được **sau khi bạn thực sự build shared library**.

### 4.1. Cấu trúc project

Từ một thư mục lab trống:

```text
jni-lab/
├── src/
│   └── example/
│       └── jni/
│           └── NativeCalculator.java
├── native/
│   └── mathbridge.c
├── HeaderAudit.java
└── build/
    ├── classes/
    ├── headers/
    └── native/
```

`build/*` là output do công cụ tạo. `HeaderAudit.java` là chương trình kiểm tra header không cần native library; `NativeCalculator.java` là class Java **có native methods**; `mathbridge.c` sẽ implement các hàm được khai báo trong generated header.

### 4.2. Source chính: `NativeCalculator.java`

Lưu đúng file `src/example/jni/NativeCalculator.java`:

```java
package example.jni;

import java.lang.annotation.Native;

public final class NativeCalculator {
    @Native public static final int ABI_VERSION = 3;

    static {
        System.loadLibrary("mathbridge");
    }

    public static native int add(int left, int right);
    public native String hello();

    public static void main(String[] args) {
        System.out.println("abi=" + ABI_VERSION);
        System.out.println("sum=" + add(7, 5));
        System.out.println("message=" + new NativeCalculator().hello());
    }
}
```

**Giải thích từng thành phần:**

1. `package example.jni` tham gia xác định tên symbol JNI.
2. `@Native ... ABI_VERSION = 3` cho phép đưa constant này vào C header.
3. `static { System.loadLibrary("mathbridge"); }` yêu cầu JVM tải native library theo **tên logic** `mathbridge` khi class được khởi tạo.
4. `static native int add(int,int)` không có thân Java; C sẽ triển khai nó và nhận tham số class (`jclass`) làm receiver.
5. `native String hello()` là instance method; C sẽ nhận object (`jobject`) làm receiver và trả một `jstring`.
6. `main` chỉ là harness để chạy thử sau khi native library đã build.

**Cảnh báo:** chạy `NativeCalculator.main` **trước khi có native library** sẽ thất bại khi class được khởi tạo; đó là hành vi mong đợi, không phải lỗi của `javac -h`.

### 4.3. Biên dịch và sinh header cùng một lần

Tại thư mục `jni-lab`, trên POSIX shell:

```bash
mkdir -p build/classes build/headers build/native
javac --release 17 -encoding UTF-8 \
      -d build/classes -h build/headers \
      src/example/jni/NativeCalculator.java
```

Trên PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path build/classes,build/headers,build/native
javac --release 17 -encoding UTF-8 -d build/classes -h build/headers src/example/jni/NativeCalculator.java
```

Kiểm tra hai artifact:

```text
build/classes/example/jni/NativeCalculator.class
build/headers/example_jni_NativeCalculator.h
```

**Đây là đường dẫn đã xác minh trên OpenJDK 24.0.2 trong bài lab classpath (không dùng named module)**. Với một project module hoặc compiler pipeline khác, layout header có thể được đặt thêm dưới thư mục module.

Không cần gọi `javah`.

## 5. Generated JNI header thực sự chứa gì?

Trong lab JDK 24.0.2, `build/headers/example_jni_NativeCalculator.h` chứa phần cốt lõi:

```c
/* DO NOT EDIT THIS FILE - it is machine generated */
#include <jni.h>
/* Header for class example_jni_NativeCalculator */

#ifndef _Included_example_jni_NativeCalculator
#define _Included_example_jni_NativeCalculator
#ifdef __cplusplus
extern "C" {
#endif
#undef example_jni_NativeCalculator_ABI_VERSION
#define example_jni_NativeCalculator_ABI_VERSION 3L

/*
 * Class:     example_jni_NativeCalculator
 * Method:    add
 * Signature: (II)I
 */
JNIEXPORT jint JNICALL Java_example_jni_NativeCalculator_add
  (JNIEnv *, jclass, jint, jint);

/*
 * Class:     example_jni_NativeCalculator
 * Method:    hello
 * Signature: ()Ljava/lang/String;
 */
JNIEXPORT jstring JNICALL Java_example_jni_NativeCalculator_hello
  (JNIEnv *, jobject);

#ifdef __cplusplus
}
#endif
#endif
```

**Đây là header được trích chính xác về nội dung có ý nghĩa trên JDK thử nghiệm**. Một JDK mới có thể thay đổi comments, khoảng trắng, cấu trúc guard hoặc layout, nhưng ABI JNI phải theo spec.

### 5.1. `#include <jni.h>`

`jni.h` định nghĩa các kiểu và macro của JNI:

- `JNIEnv` / `JavaVM`;
- `jint`, `jlong`, `jboolean`, `jobject`, `jclass`, `jstring`, các kiểu mảng;
- `JNIEXPORT` để xuất symbol khi native linker yêu cầu;
- `JNICALL` quy định calling convention thích hợp.

**Bạn cần include path tới `jni.h` và `jni_md.h`** theo OS khi biên dịch C. Chỉ truyền header sinh từ `javac -h` cho compiler mà không cung cấp JDK include directories có thể dẫn đến `jni.h: No such file or directory`.

### 5.2. Include guard và `extern "C"`

Header có include guard ngăn khai báo lặp. Khi compile C++, `extern "C"` giúp khai báo các symbol dùng C linkage, tránh việc C++ compiler tự mangling tên.

**Nên include generated header trong chính source C/C++ triển khai** để compiler kiểm tra prototypes và linkage, không tự viết tên hàm thủ công ở file native.

### 5.3. Constant macro

```c
#define example_jni_NativeCalculator_ABI_VERSION 3L
```

Được sinh từ `@Native public static final int ABI_VERSION = 3`. Phần này cho phép mã native chia sẻ một constant value. Nếu thay `ABI_VERSION` trong Java, **phải regenerate header và rebuild C library** để tránh hai phía bất đồng giá trị.

### 5.4. Native method signature

```text
add(int,int) -> int:
  descriptor (II)I

hello() -> java.lang.String:
  descriptor ()Ljava/lang/String;
```

`(II)I`: hai tham số kiểu primitive `int`, trả về `int`. `()Ljava/lang/String;`: không có tham số Java, trả về object reference kiểu `java.lang.String`.

Đây là **JVM type descriptors**, không phải C function parameter list. Bên C còn có tham số ẩn `JNIEnv *` và `jclass/jobject`.

### 5.5. Vì sao tên symbol trông dài?

```text
Java_example_jni_NativeCalculator_add
Java_example_jni_NativeCalculator_hello
```

JNI dùng quy tắc mã hóa package/class/method name. **Đổi tên package/class/native method mà không rebuild native library có thể tạo `UnsatisfiedLinkError`**, dù Java compile thành công.

Quy tắc cụ thể cho tên có dấu gạch dưới, ký tự Unicode và overload phức tạp hơn việc thay toàn bộ dấu chấm thành `_`; phải để `javac -h` tạo tên đúng và kiểm tra generated header.

## 6. Phân biệt `JNIEnv*`, `jclass` và `jobject`

Đoạn header:

```c
JNIEXPORT jint JNICALL Java_example_jni_NativeCalculator_add
  (JNIEnv *, jclass, jint, jint);

JNIEXPORT jstring JNICALL Java_example_jni_NativeCalculator_hello
  (JNIEnv *, jobject);
```

Cho biết:

| C tham số / kiểu | Vai trò |
| --- | --- |
| `JNIEnv *env` | Giao diện để native code gọi JNI functions của JVM; gắn với context thread hiện tại |
| `jclass cls` | Receiver ẩn khi Java method là `static native` |
| `jobject self` | Receiver ẩn khi Java method là **instance native** |
| `jint a, jint b` | Hai `int` Java đã được chuyển sang kiểu JNI tương ứng |
| `jstring` | Java `String` reference, **không phải C `char *`** |

`JNIEnv*` **không** là một con trỏ tiện dụng để truyền tùy ý sang thread native khác rồi tái sử dụng. Native threads được attach vào JVM theo cơ chế JNI phù hợp phải lấy environment của đúng thread; tham chiếu JNI còn chịu quy tắc local/global references.

### 6.1. Bảng chuyển một số kiểu Java sang JNI

| Java | JNI C type |
| --- | --- |
| `boolean` | `jboolean` |
| `byte` | `jbyte` |
| `char` | `jchar` |
| `short` | `jshort` |
| `int` | `jint` |
| `long` | `jlong` |
| `float` | `jfloat` |
| `double` | `jdouble` |
| `String` | `jstring` |
| `Object` | `jobject` |
| `Class<?>` | `jclass` |
| `int[]` | `jintArray` |
| `byte[]` | `jbyteArray` |
| `String[]` | `jobjectArray` |

Với reference types, ABI JNI thường dùng các handle/opaque references. **Không** cast `jstring` thành `const char *` để đọc chuỗi như C string. Dùng JNI functions thích hợp và giải phóng resources đúng vòng đời.

### 6.2. Primitive và reference values không giống nhau

`jint` đại diện giá trị số nguyên Java trong hợp đồng JNI. Nhưng `jobject`/`jstring` không phải pointer trực tiếp tới object layout mà C có thể dereference tùy ý. GC có thể di chuyển objects; JNI handles và access functions bảo đảm sự tương tác hợp lệ khi dùng đúng spec.

**Không** dùng `sizeof(jobject)` hay phép cộng pointer để đo kích thước Java object, và không suy từ một `jstring` rằng C đã sở hữu bytes UTF-8.

## 7. Viết phần triển khai native C

Lưu file `native/mathbridge.c`:

```c
#include "example_jni_NativeCalculator.h"

JNIEXPORT jint JNICALL Java_example_jni_NativeCalculator_add(
        JNIEnv *env, jclass cls, jint left, jint right) {
    (void) env;
    (void) cls;
    return left + right;
}

JNIEXPORT jstring JNICALL Java_example_jni_NativeCalculator_hello(
        JNIEnv *env, jobject self) {
    (void) self;
    return (*env)->NewStringUTF(env, "Hello from C");
}
```

**Giải thích:**

- `#include "example_jni_NativeCalculator.h"` nhập **prototype do `javac` sinh**.
- `JNIEXPORT` và `JNICALL` giữ đúng ABI, export/calling convention.
- `add` nhận `JNIEnv *`, `jclass` và hai `jint`; trong lab không cần dùng `env/cls` nên viết `(void)` để tránh warnings.
- `hello` nhận `JNIEnv *` và `jobject` của instance hiện tại.
- `(*env)->NewStringUTF(env, "Hello from C")` tạo **Java String** từ một chuỗi ASCII hợp lệ. Không trả trực tiếp `char *` hoặc pointer tới stack C.
- Trong C (không phải C++), gọi JNI functions thông qua `(*env)->Function(env, ...)`.

`NewStringUTF` dùng **Modified UTF-8** của JNI, không phải cam kết giải mã mọi byte stream UTF-8 chuẩn tùy ý. Để chuyển nội dung non-ASCII/Unicode phức tạp, xem đúng contract JNI và quản lý lỗi/bộ nhớ cẩn thận. Bài chọn literal ASCII để đầu ra và phương pháp minh bạch.

### 7.1. Vì sao không cần `free` cho kết quả `NewStringUTF`?

Hàm `NewStringUTF` tạo một **Java string object** được JVM quản lý và trả local reference cho native method. C code không sở hữu vùng C string output kiểu `malloc` phải gọi `free` ở đây.

Trường hợp ngược lại — dùng `GetStringUTFChars` để nhận một native character buffer/view — có **quy tắc `ReleaseStringUTFChars` tương ứng**. Đừng học sai rằng mọi tài nguyên JNI đều được GC tự dọn tức thì.

### 7.2. Đừng sửa generated header

Một số developer thấy C compiler báo mismatch rồi sửa prototype trong file `.h` để “build được”. Cách đó tạo nguy cơ Java/C ABI không còn cùng hợp đồng, và lần build kế tiếp `javac -h` lại ghi đè.

**Nguồn sự thật là khai báo Java native method và generated header mới nhất.** Sửa signature trong Java theo thiết kế, regenerate header rồi cập nhật source C cho khớp; kiểm tra lại cả ba artifact.

### 7.3. C++ khác C ở chỗ nào?

JNI hỗ trợ viết native code bằng C hoặc C++. Với C++, cách gọi `JNIEnv` method thường dùng cú pháp đối tượng C++ như `env->NewStringUTF(...)`, còn C dùng `(*env)->NewStringUTF(env, ...)`.

**File demo là `.c` và cú pháp C**, nên các lệnh build bên dưới dùng C compiler. Nếu đổi sang `.cpp`, cần compiler C++, giữ linkage JNI mà generated header quy định và điều chỉnh cú pháp `JNIEnv` theo C++ interface. Không copy nguyên phần body C rồi giả định mọi cú pháp JNI đều tương đương.

## 8. Build thư viện native trên Linux, macOS và Windows

**Hai điều kiện đầu tiên:**

1. Có **JDK headers** (`$JAVA_HOME/include/jni.h` và header nền tảng tương ứng `jni_md.h`).
2. Có C compiler/linker cho OS/CPU mục tiêu.

Môi trường có `javac` không đồng nghĩa có GCC/Clang/MSVC. **`javac -h` tự nó không yêu cầu C compiler**, nhưng tạo native library thì có.

### 8.1. Linux — GCC/Clang

Tại thư mục `jni-lab`:

```bash
cc -std=c11 -fPIC -shared \
   -I"$JAVA_HOME/include" \
   -I"$JAVA_HOME/include/linux" \
   -I"build/headers" \
   -o build/native/libmathbridge.so \
   native/mathbridge.c
```

- `-fPIC`: tạo position-independent code phù hợp shared library.
- `-shared`: liên kết thành shared object.
- `-I .../include` và `-I .../include/linux`: tìm `jni.h` và `jni_md.h`.
- `-I"build/headers"`: tìm generated header.
- `-o libmathbridge.so`: tên thư viện đúng quy ước Linux cho logical name `mathbridge`.

**Không** cố đặt file `.so` vào Java classpath; JVM tìm native libraries theo native-library search path hoặc đường dẫn nạp rõ ràng.

### 8.2. macOS — Clang

```bash
cc -std=c11 -dynamiclib \
   -I"$JAVA_HOME/include" \
   -I"$JAVA_HOME/include/darwin" \
   -I"build/headers" \
   -o build/native/libmathbridge.dylib \
   native/mathbridge.c
```

macOS dùng thư mục include platform `darwin` và tên thư viện `libmathbridge.dylib`. Các bản JDK/compiler/toolchain có yêu cầu architecture/signing riêng; đảm bảo library được build cho cùng architecture mà JVM chạy (ví dụ arm64 vs x86_64).

### 8.3. Windows — MSVC Developer Command Prompt

Mở **Developer Command Prompt** đã cấu hình MSVC toolchain, tại `jni-lab`:

```bat
cl /nologo /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /I"build\headers" native\mathbridge.c /link /OUT:build\native\mathbridge.dll
```

- `/LD`: tạo DLL.
- `JNIEXPORT` từ JDK headers giúp export symbol theo môi trường Windows.
- `/I` dẫn compiler tới `jni.h`, `jni_md.h`, generated header.
- `/OUT` tạo `mathbridge.dll`, tên mà `System.loadLibrary("mathbridge")` tìm trên Windows.

**Lưu ý:** `cl` không tự có sẵn trong một PowerShell mới mở; cần Developer Command Prompt hoặc shell đã nạp Visual Studio build environment. Bài không giả định hệ thống nào có C compiler chỉ vì JDK đã cài.

### 8.4. Khác biệt tên native library theo OS

| OS | Logical name truyền vào Java | Filename thường dùng |
| --- | --- | --- |
| Linux | `mathbridge` | `libmathbridge.so` |
| macOS | `mathbridge` | `libmathbridge.dylib` |
| Windows | `mathbridge` | `mathbridge.dll` |

`System.loadLibrary("mathbridge")` tự áp quy tắc mapping của hệ điều hành; **không truyền `"libmathbridge.so"` hoặc đường dẫn file đầy đủ cho `loadLibrary`**. Nếu bạn thật sự muốn load theo **đường dẫn tuyệt đối**, dùng `System.load(path)` có contract khác.

### 8.5. Không nhầm library search path với compiler include path

- `-I...` của C compiler: nơi tìm **header**.
- `-h...` của `javac`: nơi **ghi generated header**.
- `-d...` của `javac`: nơi **ghi class files**.
- `-cp...` của `java`: nơi **tìm Java classes**.
- `-Djava.library.path=...`: nơi **JVM tìm native library** khi nạp theo tên logic.

Đây là năm cơ chế **khác nhau**. Đừng thử sửa `UnsatisfiedLinkError: no mathbridge in java.library.path` bằng việc thêm `.dll` vào Java classpath.

## 9. Chạy Java với native library vừa build

Sau khi đã biên dịch đúng thư viện theo OS, tại thư mục `jni-lab`:

```bash
java --enable-native-access=ALL-UNNAMED \
     -Djava.library.path=build/native \
     -cp build/classes example.jni.NativeCalculator
```

Dấu `\` nối dòng dành cho shell POSIX. Trên PowerShell chạy một dòng:

```powershell
java --enable-native-access=ALL-UNNAMED -Djava.library.path=build/native -cp build/classes example.jni.NativeCalculator
```

**Stdout mong đợi nếu bạn đã build đúng native library từ C source trong bài:**

```text
abi=3
sum=12
message=Hello from C
```

**Phạm vi kiểm thử:** Mình đã kiểm chứng đầy đủ lệnh `javac -h`, generated header, JNI prototypes và chương trình Java kiểm tra header trên OpenJDK 24.0.2. Máy kiểm thử **không có C compiler trong PATH**, nên không tuyên bố đã thực thi phần `mathbridge.c` end-to-end. Ba dòng stdout ở trên là **kết quả được suy ra trực tiếp từ C implementation khi thư viện đã được build và load thành công**, không phải log đo được từ máy thiếu C compiler.

### 9.1. Vì sao cần `--enable-native-access=ALL-UNNAMED`?

Từ **JDK 24**, **JEP 472 — Prepare to Restrict the Use of JNI** điều chỉnh native library loading/binding theo chính sách *integrity by default*:

- Lệnh nạp như `System.loadLibrary` và các khai báo/native methods chịu chính sách **restricted native access**.
- Trên JDK 24, gọi mà không cho phép native access có thể tạo **cảnh báo**; các JDK sau có thể siết chặt hơn tùy chính sách hiện hành.
- Với ví dụ Java chạy trên **classpath / unnamed module**, dùng `--enable-native-access=ALL-UNNAMED`.
- Với **named module**, ưu tiên grant chọn lọc `--enable-native-access=example.module` tương ứng, thay vì mở mọi module.
- Đây là **quyền opt-in có chủ đích cho native code**, không làm JNI memory-safe.

Tùy chọn `--enable-native-access` được mô tả trong JEP hiện hành và dùng để chuẩn bị khi policy chặt hơn. **Không** dựa vào `--illegal-native-access=allow` như workaround lâu dài; khi có native code hợp lệ, hãy grant native access đúng scope.

### 9.2. Native code có khả năng crash process

C/C++ JNI có thể:

- dereference pointer sai;
- truy cập ngoài bounds;
- giữ reference quá hạn;
- tạo data race hoặc deadlock;
- vi phạm GC safepoint/threading contracts;
- khiến JVM crash mà không phải Java exception thông thường.

Do đó, **native access phải được quản trị như một khả năng rủi ro cao hơn Java bytecode thuần**. Native library nên được build từ nguồn tin cậy, phân phối có kiểm soát và kiểm thử với đúng runtime/architecture.

### 9.3. JVM và native library phải cùng architecture

`64-bit JVM` cần native library ABI tương thích. Ví dụ không thể nạp một DLL 32-bit vào JVM Windows 64-bit. Tương tự, macOS arm64 và x86_64 cần binary đúng architecture hoặc universal binary phù hợp.

Khi deployment dùng nhiều nền tảng, build mỗi library riêng trong CI matrix và đưa đúng artifact vào package tương ứng. **`javac --release 17` không tự biên dịch C cho các target khác.**

## 10. Kiểm chứng header bằng Java 17+ ngay cả khi chưa có C compiler

Để kiểm chứng workflow `javac -h` một cách **tự động và độc lập với native toolchain**, ta có thể dùng một Java program chỉ đọc generated header.

Lưu file `HeaderAudit.java` ở gốc `jni-lab`:

```java
import java.nio.file.Files;
import java.nio.file.Path;

public final class HeaderAudit {
    public static void main(String[] args) throws Exception {
        Path file = Path.of("build/headers/example_jni_NativeCalculator.h");
        String header = Files.readString(file);

        System.out.println("headerExists=" + Files.isRegularFile(file));
        System.out.println("includesJni=" +
                header.contains("#include <jni.h>"));
        System.out.println("hasAddSymbol=" +
                header.contains("Java_example_jni_NativeCalculator_add"));
        System.out.println("hasHelloSymbol=" +
                header.contains("Java_example_jni_NativeCalculator_hello"));
        System.out.println("addSignature=" +
                header.contains("Signature: (II)I"));
        System.out.println("helloSignature=" +
                header.contains("Signature: ()Ljava/lang/String;"));
        System.out.println("staticReceiver=" +
                header.contains("(JNIEnv *, jclass, jint, jint);"));
        System.out.println("instanceReceiver=" +
                header.contains("(JNIEnv *, jobject);"));
        System.out.println("nativeConstant=" +
                header.contains(
                        "#define example_jni_NativeCalculator_ABI_VERSION 3L"));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 -d build/classes HeaderAudit.java
java -cp build/classes HeaderAudit
```

**Stdout đã kiểm thử chính xác trên OpenJDK 24.0.2** sau khi chạy `javac -h`:

```text
headerExists=true
includesJni=true
hasAddSymbol=true
hasHelloSymbol=true
addSignature=true
helloSignature=true
staticReceiver=true
instanceReceiver=true
nativeConstant=true
```

Nếu dùng JDK khác với **format comments/whitespace header** khác, một assertion theo `contains(...)` trong chương trình này có thể cần điều chỉnh. Đây là **bài test của ví dụ/header layout đã kiểm chứng**, không phải một đặc tả đầy đủ cho việc kiểm thử JNI ABI trên mọi phiên bản/compiler.

### 10.1. Tại sao HeaderAudit không gây `UnsatisfiedLinkError`?

`HeaderAudit` chỉ đọc **file văn bản generated header**, không gọi `NativeCalculator.main()`, không gọi `add/hello`, và không khởi tạo class `NativeCalculator`. Vì vậy static initializer `System.loadLibrary("mathbridge")` **không chạy**.

Đây là cách tách giai đoạn **compile/header QA** khỏi giai đoạn **native runtime integration QA** trong pipeline.

### 10.2. Kiểm tra descriptors bằng `javap`

```bash
javap -classpath build/classes -s -p example.jni.NativeCalculator
```

Trong output của JDK thử nghiệm:

```text
public static native int add(int, int);
  descriptor: (II)I

public native java.lang.String hello();
  descriptor: ()Ljava/lang/String;
```

Đây là **trích đoạn** từ output đầy đủ, không phải toàn bộ stdout. `javap -s -p` cho phép đối chiếu Java class ABI mà JVM thực sự nhìn thấy, bổ sung cho việc đọc generated header.

Nếu signature Java đổi, regenerate header và rebuild native library ngay. Không giữ cả file `.class` mới và `.so` cũ khi đang thử JNI.

## 11. JNI naming, overloading và ký hiệu descriptor

### 11.1. Các thành phần của native symbol

Một tên JNI thông thường có dạng:

```text
Java_<mangled-class-name>_<mangled-native-method-name>
```

Khi có overload cần phân biệt tham số, có thể có **suffix `__`** kèm encoded argument descriptor.

Ví dụ trong bài:

```text
package: example.jni
class:   NativeCalculator
method:  add

=> Java_example_jni_NativeCalculator_add
```

Đây là output của `javac -h`, không phải thuật toán tự viết tùy ý. JNI specification có quy tắc escape đặc biệt:

- `/` của internal binary name thành `_`;
- ký tự `_` trong tên gốc phải escape thành `_1`;
- một số ký tự Unicode được escape thành mã dạng `_0xxxx`;
- overload xử lý tham số theo encoding quy định.

Đừng dùng `replace('.', '_')` cho mọi tên rồi tin chắc không xung đột; **đọc generated header**.

### 11.2. Một method overload có thể làm symbol đổi

Giả sử bạn thêm:

```java
// Đoạn minh họa, không thuộc NativeCalculator.java đang chạy.
public static native int add(int a, int b, int c);
```

Khi có overload, tên JNI có thể dùng suffix mã hóa descriptors để phân biệt. Nếu native source vẫn export symbol cũ, kết nối có thể fail hoặc chọn symbol không mong muốn theo quy tắc tra cứu của JVM.

**Không đoán tên mới**. Chạy lại `javac -h`, đọc cả header và `javap -s`, cập nhật C source, compile/relink, rồi kiểm thử runtime.

### 11.3. Generic erasure và native ABI

Một số kiểu Java generic không tồn tại ở runtime ở mức giống source; JVM descriptors dùng **erased types**. Khi giao tiếp JNI, phải dựa trên **bytecode signature** chứ không dựa vào cách hiển thị generic type trong IDE.

Tương tự, JNI không thể dùng Java overload resolution phía C như trong source Java. C functions/symbols phải tuân quy tắc do JVM và generated header quy định.

### 11.4. Native symbol lookup và `RegisterNatives`

JNI còn hỗ trợ đăng ký native implementations bằng `RegisterNatives` thay vì chỉ dựa vào tên exported functions chuẩn. Đây là cơ chế JNI hiện hành nhưng mang thêm trách nhiệm tạo bảng method names/signatures và quản lý đúng classloader/lifetime.

Bài cơ bản dùng **name-based JNI export** vì minh bạch, dễ theo dõi từ `javac -h` tới C function. Nếu framework/native library dùng `RegisterNatives`, việc không nhìn thấy symbol `Java_...` trong exported symbols **không tự chứng minh phương thức chưa được liên kết**.

## 12. JNI threading, references và memory management

### 12.1. `JNIEnv*` không chia sẻ tùy ý giữa threads

JNI specification quy định `JNIEnv*` là context cho một thread. Khi native code tạo threads ngoài JVM rồi muốn gọi lại Java, cần dùng JNI Invocation API như `AttachCurrentThread` đúng cách, quản lý attach/detach và lấy environment hợp lệ.

Không lưu `JNIEnv*` trong một global variable và dùng trực tiếp từ mọi native thread.

### 12.2. Local vs global references

Các đối tượng nhận từ JNI thường là local references có thời hạn tương ứng với native call/frame. Nếu cần giữ reference sau khi phương thức native return, dùng global reference qua API tương ứng, và giải phóng khi không còn dùng.

**Không** lưu `jobject` local reference làm pointer sống vĩnh viễn. GC có thể di chuyển hoặc reclaim đối tượng theo semantics của JNI references.

### 12.3. String/array pinning và releases

Các API như `GetStringUTFChars`, `GetByteArrayElements` hoặc `GetPrimitiveArrayCritical` có hợp đồng cấp phát/pin/copy và release riêng. Nếu quên `Release...`, ứng dụng có thể giữ resources hoặc làm GC bị ảnh hưởng.

Bài dùng `NewStringUTF` để giảm độ phức tạp, nhưng không có nghĩa JNI luôn dễ như cộng hai số.

### 12.4. Kiểm tra pending exceptions

Nhiều JNI calls có thể thất bại hoặc để lại pending Java exception (ví dụ out-of-memory). Nếu native function tiếp tục thao tác khi đang có exception pending mà không tuân quy tắc JNI, có thể gây lỗi.

Trong C thực tế, kiểm tra kết quả trả về và dùng `ExceptionCheck`/`ExceptionOccurred` khi cần. Không ép một C pointer NULL thành một Java object thành công.

### 12.5. Chỉ gọi JNI code đáng tin cậy

Native library có khả năng can thiệp memory toàn process. Cần quản trị:

- provenance của thư viện;
- code review và native memory safety;
- compiler sanitizers/test tools khi phù hợp;
- binary dependencies và architecture;
- đường dẫn nạp library không cho thư viện giả mạo chen vào;
- native access policies theo module;
- crash handling và observability.

Đừng xử lý lỗi JNI bằng cách thêm tùy chọn cho phép access bừa bãi hoặc nạp library từ thư mục có thể bị bên không tin cậy sửa.

## 13. Lỗi thường gặp: triệu chứng và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hành động |
| --- | --- | --- |
| `javah: command not found` | Công cụ bị **xóa từ Java 10** | Dùng `javac -h` |
| `javac: invalid flag: -h` | Dùng compiler khác/command bị viết sai hoặc JDK không phù hợp | Kiểm tra `javac -version` và `javac --help` |
| Không có generated `.h` | Class không có native method/`@Native`, output path khác, source không được compile | Kiểm tra class/source và `-h` directory |
| Header trống hoặc cũ | Incremental build không compile lại sources, output stale | Regenerate từ source hiện tại, clean build |
| C báo `jni.h: No such file` | Chưa include JDK headers | Thêm `-I"$JAVA_HOME/include"` |
| C báo `jni_md.h: No such file` | Thiếu include OS-specific | Thêm `-I"$JAVA_HOME/include/linux"` hoặc `darwin/win32` |
| C báo conflicting types | Signature C không khớp header | Sửa implementation theo generated prototype |
| `UnsatisfiedLinkError: no mathbridge in java.library.path` | JVM không tìm được shared library theo logical name | Kiểm tra filename, native path, permissions, architecture |
| `UnsatisfiedLinkError: ...add...` | DLL được nạp nhưng không export đúng function/symbol, ABI stale | So generated symbol với native exports |
| `wrong ELF class` hoặc `%1 is not a valid Win32 application` | Architecture/ABI mismatch | Build đúng target OS/CPU |
| Warnings JNI native access trên JDK 24+ | Chưa opt-in native access | Grant `--enable-native-access` đúng module/classpath |
| `IllegalCallerException` cho native access | Chính sách `--illegal-native-access` chặt hơn | Grant native access đúng module, không bỏ security bằng workaround |
| Java prints `abi=3` rồi dừng | Có thể `System.loadLibrary` hoặc native binding lỗi trước dòng sau | Đọc stacktrace/OS loader errors và symbol exports |
| Chạy nhầm JNI library version | `java.library.path`/OS dependencies trỏ file cũ | Chốt version/digest, kiểm tra library được nạp thực tế |

Đặc biệt lưu ý: một file DLL/.so có tên đúng vẫn có thể **không tải được các native dependencies khác** mà nó cần. Lỗi loader vì thiếu thư viện phụ khác với lỗi Java classpath.

### 13.1. Lỗi `UnsatisfiedLinkError` có hai nhóm chính

**Nhóm A — không tìm/tải được native library:**

```text
java.lang.UnsatisfiedLinkError: no mathbridge in java.library.path
```

Đây là **ví dụ dạng lỗi**, không phải output bắt buộc của bài. Kiểm tra vị trí file, extension/prefix, OS architecture, loader dependencies, quyền truy cập và `java.library.path`.

**Nhóm B — tải library thành công nhưng không tìm thấy native method implementation:**

```text
java.lang.UnsatisfiedLinkError: 'int example.jni.NativeCalculator.add(int, int)'
```

Ví dụ dạng lỗi tương tự có thể xuất hiện nếu export symbol khác, method signature lệch hoặc implementation library không còn khớp với `.class`. Regenerate header và rebuild C, rồi đọc exports thật.

**Đừng** cố khắc phục Nhóm B chỉ bằng cách đổi `java.library.path` nếu DLL đã nạp đúng.

### 13.2. Kiểm tra native exports

Một số công cụ OS có thể giúp:

- Linux: `nm -D build/native/libmathbridge.so` hoặc `readelf -Ws`.
- macOS: `nm -gU build/native/libmathbridge.dylib`.
- Windows Developer Command Prompt: `dumpbin /EXPORTS build\native\mathbridge.dll`.

Tìm `Java_example_jni_NativeCalculator_add` và `Java_example_jni_NativeCalculator_hello`. Tên hiển thị và decorations phụ thuộc toolchain/architecture, nhưng đây là symbols mà generated header của demo yêu cầu.

Nếu library dùng `RegisterNatives` thay vì exported JNI names, phải kiểm tra cơ chế đăng ký riêng; không bắt buộc mọi JNI library có symbols `Java_...`.

## 14. Quy trình CI/CD: bảo đảm Java và native ABI luôn cùng phiên bản

Một pipeline đáng tin cậy nên làm theo thứ tự:

1. **Chốt JDK toolchain**: vendor, feature/update/build; ghi nhận `javac -version`.
2. **Compile Java + generate JNI headers**: `javac -h ... -d ...` từ source chính thức.
3. **Xác minh header có nội dung**: tên class, prototypes, descriptors, constants khi có.
4. **Compile C/C++** với generated headers mới và JDK headers của toolchain đã chọn.
5. **Link native library** theo OS/architecture matrix.
6. **Kiểm tra exported JNI symbols** hoặc cơ chế `RegisterNatives` nếu có.
7. **Package/deploy `.class/.jar` và native binaries cùng release**.
8. **Chạy native integration test** bằng JVM thật với native access policy đúng.
9. **Quan sát** `UnsatisfiedLinkError`, stderr warnings, loader dependency và crash diagnostics.
10. **Không publish** khi ABI Java/C mismatch hoặc native test chưa chạy cho target được cam kết hỗ trợ.

### 14.1. Header là artifact được sinh, không phải nguồn sửa chính

Đặt generated headers dưới thư mục `build` (hoặc generated sources phù hợp build tool). Dựng dependency graph:

```text
compileJava --(-h)--> generatedHeader
                              |
                              v
                         compileNative
                              |
                              v
                          linkLibrary
                              |
                              v
                       integrationTest
```

Nếu một native method parameter thay đổi, các bước native build phải được chạy lại. **Không giữ header từ release trước** nếu Java source/class đã thay đổi.

### 14.2. Incremental build và stale outputs

Một lỗi tinh vi: build tool thấy Java source “up to date”, bỏ qua compileJava nhưng C compiler vẫn dùng **header cũ** từ build cache.

Các biện pháp:

- khai báo header generation như một output/dependency của task Java compile;
- đảm bảo header directory có trong build artifacts đúng phiên;
- tự động clean/regenerate khi thay package/native method signature;
- nếu dùng remote build cache, khóa key theo **Java sources, JDK toolchain và compiler options**;
- chạy `javap -s -p` hoặc ABI checker khi có thay đổi JNI interface;
- không lấy generated headers được copy tay từ một workspace khác làm dữ liệu nguồn.

### 14.3. Maven/Gradle và `-h`

Maven Compiler Plugin hoặc Gradle JavaCompile thường có cách chuyển **compiler arguments** bổ sung tới `javac`. Bạn có thể cấu hình `-h <generated-header-directory>` và đảm bảo bước C/C++ phụ thuộc vào bước Java compile.

Tuy nhiên, **đừng giả định mỗi build tool tự triển khai JNI header generation đúng cách nếu bạn chưa cấu hình**. Kiểm tra compilation command và output trên đúng JDK. Không gợi ý dùng plugin `javah` đời cũ như một giải pháp hiện hành.

### 14.4. Modular JARs và named modules

Với JPMS, `javac -h` có thể đặt generated headers vào cấu trúc output phản ánh **module**. `--enable-native-access=module.name` cần cấu hình phù hợp khi Java module gọi restricted native operations trên JDK mới.

Đừng copy máy móc `ALL-UNNAMED` vào một ứng dụng đã chia module rõ ràng mà không đánh giá phạm vi. Mặt khác, **Java classpath** không tự mang tên named module cho grant riêng: `ALL-UNNAMED` là cách thể hiện scope tương ứng khi cần.

### 14.5. Native libraries trong container

Một image Linux muốn chạy JNI cần:

- JDK/runtime image phù hợp Java bytecode;
- `libmathbridge.so` build cho Linux architecture đó;
- mọi native dependencies yêu cầu;
- loader path phù hợp và quyền đọc/execute;
- startup flags native access theo policy;
- smoke test chạy trong **image cuối cùng**.

Không xây DLL trên Windows rồi copy sang Linux container. Không nghĩ `--release 17` biến native artifact thành cross-platform.

## 15. JNI hiện hành và Foreign Function & Memory API (FFM)

JNI **vẫn được hỗ trợ** trên JDK mới. Tuy nhiên, với những tác vụ chỉ cần gọi thư viện native bên ngoài, **Foreign Function & Memory API** đã được chuẩn hóa trong **Java 22 / JEP 454** và có thể đáng đánh giá.

| Nhu cầu | JNI có phù hợp? | Cân nhắc FFM |
| --- | --- | --- |
| Native code cần callback/truy cập Java objects, class/methods | Thường phù hợp | Tùy thiết kế |
| Tích hợp thư viện C có ABI rõ, chủ yếu primitive/struct calls | Có thể dùng | Có thể tránh một số JNI glue |
| Codebase đang có native methods/JNI headers | Tiếp tục phù hợp | Migration không tự cần thiết |
| Muốn Java trực tiếp quản lý native memory theo scope | JNI vẫn có lựa chọn | FFM `Arena/MemorySegment` hiện hành |
| Mục tiêu giảm rủi ro crash native code | JNI không memory-safe | FFM cải thiện một số contracts nhưng vẫn có restricted native operations |

**`javac -h` là công cụ đúng khi bạn chọn JNI native methods.** Nó không tạo header cho FFM downcalls; đó là mô hình tương tác khác. Không dùng FFM incubator APIs của các JDK thử nghiệm cũ cho project mới khi API chuẩn có sẵn.

Từ JDK 24, cả JNI và FFM cùng được đặt trong lộ trình **native access restrictions**. Lựa chọn công nghệ không loại bỏ nhu cầu đánh giá security, phân phối native libraries và kiểm thử ABI.

## 16. Thực hành tự kiểm tra và mở rộng

### Bài tập 1 — Đổi hằng số `@Native`

Thay `ABI_VERSION=3` thành `4`, chạy `javac -h` lại, xem macro `#define ... ABI_VERSION 4L`. Nếu C source có code dựa vào giá trị macro cũ, phải rebuild library.

**Mục tiêu:** hiểu generated header là artifact của **Java source version hiện tại**.

### Bài tập 2 — Đổi phương thức `add`

Thay `int add(int,int)` bằng `long add(long,long)` rồi regenerate header.

Quan sát:

- Java descriptor thay từ `(II)I` thành `(JJ)J`.
- JNI C types chuyển `jint` thành `jlong`.
- C implementation cũ không còn khớp prototype.

**Mục tiêu:** hiểu native ABI là hợp đồng nhạy cảm với kiểu, không thể chỉ sửa Java code.

### Bài tập 3 — Đổi package

Đổi `example.jni` thành `example.nativebridge` và đặt file Java vào path source tương ứng. Regenerate header và thấy tên exported symbol thay đổi.

**Mục tiêu:** biết package/class rename có thể phá native symbols; build và deploy phải đồng bộ.

### Bài tập 4 — Thử không có native library

Sau khi generate header nhưng chưa build `mathbridge`, chạy `NativeCalculator.main`.

**Kết quả mong đợi:** lỗi nạp native library (thường `UnsatisfiedLinkError`). Đây là minh họa sự khác biệt **compiler tạo header** và **runtime có library**.

### Bài tập 5 — Ghi nhận lỗi path

Đặt library vào `build/native` nhưng bỏ `-Djava.library.path`. Xác định thông báo lỗi và kiểm tra vị trí JVM tìm thư viện.

**Mục tiêu:** phân biệt Java `-cp` và native library path.

### Bài tập 6 — Xác minh JNI receiver

Đọc generated header: `add` static nhận `jclass`; `hello` instance nhận `jobject`.

**Mục tiêu:** hiểu tham số ẩn mà Java source không viết.

### Bài tập 7 — Build Linux vs Windows

So sánh `libmathbridge.so` và `mathbridge.dll`. Kiểm tra `System.mapLibraryName("mathbridge")` để thấy tên theo runtime OS nếu cần.

**Mục tiêu:** không mang native binaries qua OS/arch một cách tùy tiện.

### Bài tập 8 — JDK 24+ native access

Chạy integration test có/không có `--enable-native-access=ALL-UNNAMED` trên JDK 24 với JVM policy thích hợp; quan sát stderr native access warnings hoặc lỗi.

**Mục tiêu:** quản trị native access như một quyền có chủ đích. Không dùng flag cho phép bừa bãi trên production.

### Bài tập 9 — Giả lập stale header

Giữ header cũ, thay Java signature, rồi thử compile native code; kết quả có thể build được/không tùy mức lệch nhưng ABI runtime có thể sai. Đừng lấy việc C compile thành công với header cũ làm chứng nhận tương thích Java mới.

**Mục tiêu:** CI cần regenerate + integration test, không chỉ build từng bên riêng lẻ.

### Bài tập 10 — Đọc descriptors

Dùng `javap -s -p` cho class có native method nhận `String` và `int[]`. So với header `jstring` và `jintArray`.

**Mục tiêu:** biết descriptor và JNI C type khác nguồn chữ ký Java.

## 17. Những nhầm lẫn thường gặp

**Nhầm lẫn 1 — “Java 10 có `javah` nên cứ dùng.”**  
Sai. **JDK 10 đã xóa `javah`**; dùng `javac -h`.

**Nhầm lẫn 2 — “`javac -h` biên dịch cả file C.”**  
Sai. Nó biên dịch Java và sinh header; C compiler/linker là bước riêng.

**Nhầm lẫn 3 — “`-h` và `-d` đều là nơi xuất class.”**  
Sai. `-h` ghi header, `-d` ghi class output.

**Nhầm lẫn 4 — “Mỗi Java class luôn có generated header.”**  
Sai. Phải có native method hoặc ít nhất một constant `@Native` được compiler xử lý.

**Nhầm lẫn 5 — “Cứ đổi package Java nhưng giữ .so cũ là được.”**  
Không bảo đảm. JNI names gắn với binary class/method name.

**Nhầm lẫn 6 — “Gọi `System.loadLibrary("libmathbridge.so")` trên mọi OS.”**  
Sai. `loadLibrary` nhận logical library name; OS mapping tự thêm prefix/extension.

**Nhầm lẫn 7 — “Đặt .so vào `-cp` là đủ.”**  
Sai. Java classpath và native library path là hai cơ chế khác nhau.

**Nhầm lẫn 8 — “`jni.h` là generated header trong `build/headers`.”**  
Sai. `jni.h` thuộc JDK include; header project là file riêng do `javac -h` tạo.

**Nhầm lẫn 9 — “C function nhận đúng số tham số viết ở Java.”**  
Sai. Có thêm `JNIEnv*` và `jclass/jobject`.

**Nhầm lẫn 10 — “`jstring` chính là `char *`.”**  
Sai. Nó là Java string reference; phải dùng JNI functions.

**Nhầm lẫn 11 — “`JNIEnv *` có thể chia sẻ giữa mọi threads.”**  
Sai. Thread-attached context và reference lifetimes phải theo JNI specification.

**Nhầm lẫn 12 — “Có header mới thì .so cũ tự tương thích.”**  
Sai. Phải rebuild và kiểm thử ABI giữa Java/C cùng version.

**Nhầm lẫn 13 — “`javac --release 17` giúp .dll chạy trên Linux.”**  
Sai. Java bytecode target và native ABI portability khác nhau.

**Nhầm lẫn 14 — “Thấy `UnsatisfiedLinkError` tức Java source sai.”**  
Không nhất thiết. Có thể do thiếu native library, sai architecture, loader path, symbol hoặc dependencies.

**Nhầm lẫn 15 — “JDK mới bỏ JNI, phải viết lại FFM.”**  
Sai. JNI vẫn được hỗ trợ, nhưng JDK 24+ có native access restrictions cần cấu hình.

**Nhầm lẫn 16 — “`ALL-UNNAMED` luôn tối ưu về security cho mọi module.”**  
Không. Named modules cho phép grant chọn lọc.

**Nhầm lẫn 17 — “Có C source là chắc stdout đúng trên mọi OS.”**  
Không. Phải build/link đúng toolchain/OS/architecture, rồi chạy integration test thực tế.

**Nhầm lẫn 18 — “Có thể sửa generated .h để chữa ABI mismatch.”**  
Không. Sửa Java source, regenerate header, rebuild native library.

## 18. Câu hỏi kiểm tra kiến thức

**Câu 1.** `javah` còn dùng được trên JDK 21/25/27 không?  
**Đáp án:** Không; công cụ bị xóa ở **JDK 10**, dùng `javac -h`.

**Câu 2.** `-h` trong `javac` có nghĩa là gì?  
**Đáp án:** Chỉ định thư mục để sinh native headers.

**Câu 3.** `-d` trong cùng lệnh là gì?  
**Đáp án:** Chỉ định thư mục output chứa Java class files.

**Câu 4.** Có thể sinh header cho class chỉ có `@Native` constant không?  
**Đáp án:** Có, theo tài liệu `javac -h` hiện hành.

**Câu 5.** Vì sao `NativeCalculator.class` tồn tại mà Java vẫn báo `UnsatisfiedLinkError`?  
**Đáp án:** Header/class compile chưa tạo hoặc chưa nạp được thư viện native.

**Câu 6.** Hai JNI symbols của bài là gì?  
**Đáp án:** `Java_example_jni_NativeCalculator_add` và `Java_example_jni_NativeCalculator_hello`.

**Câu 7.** Vì sao static native `add` nhận `jclass` mà instance native `hello` nhận `jobject`?  
**Đáp án:** Vì receiver ẩn của JNI phụ thuộc phương thức static hay instance.

**Câu 8.** Descriptor `(II)I` là gì?  
**Đáp án:** Phương thức nhận hai `int` và trả `int`.

**Câu 9.** Header project có cần `#include <jni.h>` không?  
**Đáp án:** Có, để lấy JNI types và macros của JDK.

**Câu 10.** Tên thư viện Linux dùng với `System.loadLibrary("mathbridge")` thường là gì?  
**Đáp án:** `libmathbridge.so`.

**Câu 11.** Có thể thay `JNIEnv*` bằng `void*` để đỡ include JNI header không?  
**Đáp án:** Không. Phải tuân đúng JNI prototypes/ABI.

**Câu 12.** Thay signature Java từ `int` sang `long` mà không rebuild native library có an toàn không?  
**Đáp án:** Không, có nguy cơ ABI mismatch/link failure hoặc hành vi lỗi.

**Câu 13.** JNI trên JDK 24+ cần quan tâm chính sách nào?  
**Đáp án:** Native access restrictions theo JEP 472; opt-in bằng `--enable-native-access` đúng scope.

**Câu 14.** `-Djava.library.path` và `-cp` khác nhau thế nào?  
**Đáp án:** Một cấu hình native library lookup, một cấu hình Java class loading.

**Câu 15.** Chương trình `HeaderAudit` có cần native library không?  
**Đáp án:** Không. Nó chỉ đọc file header do `javac` sinh.

**Câu 16.** Kiểm tra ABI Java đang thực sự có bằng công cụ nào?  
**Đáp án:** `javap -s -p` để xem descriptors, kết hợp generated header và integration test.

**Câu 17.** Có nên commit generated header vào source rồi chỉnh tay liên tục không?  
**Đáp án:** Không nên; coi nó là generated artifact tái lập từ source Java và quản lý dependency build.

**Câu 18.** Nếu source C compile được trên Windows, có đủ chứng minh chạy trên Linux chưa?  
**Đáp án:** Chưa. Phải build/link và thử trên Linux target.

**Câu 19.** JNI và FFM có phải cùng một cách sinh header không?  
**Đáp án:** Không. `javac -h` phục vụ JNI native methods; FFM có mô hình downcall/memory khác.

**Câu 20.** Khi Java/C ABI mismatch trong CI, trình tự sửa đúng là gì?  
**Đáp án:** Sửa khai báo Java hoặc C source cho nhất quán → `javac -h` mới → rebuild native → kiểm tra symbol → chạy integration test trên target.

## 19. Ghi nhớ

1. **Java 10/JEP 313 xóa `javah`; `javac -h` là công cụ hiện hành để sinh JNI headers.**
2. **`javac -h` sinh header và biên dịch Java cùng lúc**, nhưng **không** biên dịch C/C++ thành native library.
3. `-h` là thư mục header; `-d` là thư mục class output.
4. Header sinh cho class có **native methods** hoặc `@Native` constants; tên/prototypes/ABI do compiler/JNI quy định.
5. Đọc generated header để thấy **`JNIEnv*`, `jclass/jobject`, `jint/jstring`** và mangled native symbols.
6. Native source phải **include generated header**, tuân đúng C ABI, link thành `.so/.dylib/.dll` theo OS/CPU.
7. `System.loadLibrary("mathbridge")` dùng **logical name**; native library path khác Java classpath.
8. Từ **JDK 24/JEP 472**, cần quản trị **native access opt-in** cho classpath/named modules; không dựa vào quyền mặc định của các bản cũ.
9. **Regenerate header và rebuild native code** khi Java signature/package/constant thay đổi; kiểm chứng bằng `javap -s` và integration test.
10. **Không nhầm kiểm tra header với chạy được JNI end-to-end**: phần native cần compiler/linker và environment thật.
11. JNI vẫn được hỗ trợ, còn FFM API từ JDK 22 là một lựa chọn khác cho những use cases phù hợp.

## Tài liệu tham khảo chính thức, vẫn có hiệu lực

- OpenJDK **JEP 313 — Remove the Native-Header Generation Tool (javah)**, delivered in Java 10: https://openjdk.org/jeps/313
- Oracle **JDK Migration Guide — Removed Native-Header Generation Tool (javah)**: https://docs.oracle.com/en/java/javase/17/migrate/removed-tools-and-components.html
- Oracle **Java SE 27 — The javac Command** (`-h`, `-d`, `--release`): https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html
- Oracle **Java SE 27 — The javap Command** (`-s`, `-p`): https://docs.oracle.com/en/java/javase/27/docs/specs/man/javap.html
- Oracle **Java Native Interface Specification — Design Overview**, native method resolution, naming, Java/native linkage: https://docs.oracle.com/en/java/javase/26/docs/specs/jni/design.html
- Oracle **Java Native Interface Specification — JNI Functions**, `JNIEnv`/`NewStringUTF`/refs: https://docs.oracle.com/en/java/javase/26/docs/specs/jni/functions.html
- Oracle **Java Native Interface Specification — Invocation API**, `JNI_OnLoad`, classloaders/native libraries: https://docs.oracle.com/en/java/javase/26/docs/specs/jni/invocation.html
- OpenJDK **JEP 472 — Prepare to Restrict the Use of JNI**, introduced in JDK 24: https://openjdk.org/jeps/472
- Oracle **JDK Migration Guide — Native Access Restrictions**: https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html
- OpenJDK **JEP 454 — Foreign Function & Memory API**, standardized JDK 22: https://openjdk.org/jeps/454
