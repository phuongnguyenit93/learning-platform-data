# Chạy ví dụ tối thiểu và kiểm tra kiểu, kết quả, lỗi nạp và lỗi liên kết (JNI)

## 1. Mục đích và ranh giới bài học

Trong nhóm **JNI đầu tiên** của Java Native Interoperability, bài này đưa một phương thức Java `native` qua bốn chặng: **Java biên dịch → C biên dịch thành thư viện động → JVM nạp và tìm phương thức native → Java kiểm tra kết quả**. Mục tiêu không dừng ở “chương trình chạy”, mà là biết chứng minh kiểu dữ liệu và chữ ký ở hai phía khớp nhau, xác định lỗi xảy ra ở bước nào và xử lý đúng nguyên nhân.

Bạn sẽ tạo một chương trình có `public static native int add(int, int)` được triển khai bằng C. Chương trình gọi với hai bộ dữ liệu, kiểm tra kết quả, rồi in `RESULT: PASS`. Mọi file nguồn được trình bày đầy đủ và có thể chạy trên **JDK 17 trở lên** với compiler C phù hợp.

Sau khi thực hiện, người học phải giải thích được:
- `javac -h` tạo header từ chữ ký Java như thế nào; tại sao không tự đoán tên hàm C.
- `jint`, `JNIEnv *`, `jclass`, `JNIEXPORT` và `JNICALL` dùng để làm gì.
- Vì sao tên thư viện trong `System.loadLibrary` khác tên file `.so/.dylib/.dll`.
- Sự khác nhau giữa lỗi **biên dịch C**, **link thư viện C**, **nạp thư viện tại JVM**, **liên kết native method**, **lỗi kiểu/ABI** và **kết quả sai**.
- Cách kiểm tra descriptor Java, exported symbol, đường dẫn thư viện, kiến trúc CPU và thư viện phụ thuộc mà không sửa thử nhiều chỗ cùng lúc.

### Bức tranh toàn bộ

~~~text
src/demo/jni/FirstJni.java
    |
    | javac --release 17 -h native -d out
    +--> out/demo/jni/FirstJni.class
    +--> native/demo_jni_FirstJni.h
                |
native/firstjni.c + generated header
    |
    | C compiler + native linker
    +--> libfirstjni.so (Linux)
    |    libfirstjni.dylib (macOS)
    |    firstjni.dll (Windows)
    |
    | java -Djava.library.path=. -cp out demo.jni.FirstJni
    v
  static initializer: System.loadLibrary("firstjni")   <- lỗi NẠP
    |
  call add(12, 30): tìm Java_demo_jni_FirstJni_add   <- lỗi LIÊN KẾT PHƯƠNG THỨC
    |
  C thực thi: jint + jint -> jint                     <- lỗi KIỂU/ABI hoặc LOGIC
    |
  Java assert: 42, -3                                 <- lỗi KẾT QUẢ
    |
  RESULT: PASS
~~~

**Ba tầng dễ bị gọi nhầm là “link”:** native linker tạo `.so`/`.dylib`/`.dll`; system loader mở file và các thư viện phụ thuộc; JVM resolve native method với symbol trong binary. Cả hai chặng sau có thể báo `UnsatisfiedLinkError`, nhưng nguyên nhân hoàn toàn khác nhau.

## 2. Điều kiện chạy và cấu trúc thư mục

Cần JDK **17+** (có `java`, `javac` và `include/jni.h`), compiler C của đúng nền tảng, và terminal. Không cần Maven, Gradle, Spring Boot, JNA hoặc FFM cho ví dụ này.

Kiểm tra trước:

~~~sh
java -version
javac -version
~~~

Đặt tên thư mục thực hành là `jni-first`; tạo ba thư mục con và file Java ở đúng package:

~~~text
jni-first/
├── src/
│   └── demo/
│       └── jni/
│           └── FirstJni.java      # Tạo thủ công
├── native/
│   ├── demo_jni_FirstJni.h        # Sinh bằng javac -h
│   └── firstjni.c                 # Tạo thủ công
├── out/
│   └── demo/jni/FirstJni.class    # Sinh bằng javac
└── libfirstjni.so                 # Linux; tùy OS sẽ có tên khác
~~~

Trong Linux/macOS terminal, chạy từ thư mục `jni-first`:

~~~sh
mkdir -p src/demo/jni native out
~~~

Trong Windows **Developer Command Prompt (CMD)**:

~~~bat
mkdir src\demo\jni
mkdir native
mkdir out
~~~

Nếu ba thư mục đã có thì chỉ cần dùng lại chúng. `JAVA_HOME` ở các bước build native phải trỏ đến **gốc JDK**, tức nơi có `include/jni.h` và `include/linux` / `include/darwin` / `include/win32`. Kiến trúc binary native phải tương thích kiến trúc JVM đang chạy (chẳng hạn x86-64 với x86-64, arm64 với arm64); “Java chạy trên máy 64-bit” chưa đủ để suy ra compiler đang xuất đúng kiến trúc.

## 3. Tạo Java class và một phép kiểm thử có kết quả xác định

Nội dung đầy đủ của **`src/demo/jni/FirstJni.java`**:

~~~java
package demo.jni;

public final class FirstJni {
    static {
        System.loadLibrary("firstjni");
    }

    private FirstJni() {}

    public static native int add(int left, int right);

    public static void main(String[] args) {
        int first = add(12, 30);
        int second = add(-5, 2);

        if (first != 42 || second != -3) {
            throw new AssertionError(
                    "Wrong JNI result: " + first + ", " + second);
        }

        System.out.println("JNI loaded");
        System.out.println("add(12, 30) = " + first);
        System.out.println("add(-5, 2) = " + second);
        System.out.println("RESULT: PASS");
    }
}
~~~

`add` khai báo là `native` nên **không có thân hàm Java**. `javac` kiểm tra kiểu ở Java; khi JVM chạy sẽ cần một định nghĩa native tương ứng trong thư viện. `static` của `add` quyết định tham số ẩn thứ hai ở phía C là `jclass`; nếu đổi thành phương thức đối tượng thì phía C nhận `jobject`.

Khối `static` nạp thư viện khi class khởi tạo; ở chương trình này việc khởi tạo xảy ra trước phần thân `main`. Vì thế một lỗi load làm cho chương trình chưa thể in `JNI loaded`. Đoạn kiểm tra giá trị có chủ đích: có thể thư viện nạp và hàm C được gọi đúng nhưng tính sai. `RESULT: PASS` chỉ xuất hiện sau khi **cả hai** lời gọi trả đúng số. Hai phép cộng trong ví dụ không gây overflow cho kiểu `jint`.

**Tên thư viện:** `System.loadLibrary("firstjni")` nhận **tên logic `firstjni`**, không ghi `libfirstjni.so`, `firstjni.dll`, đuôi file hoặc đường dẫn. Đường dẫn được chỉ định bằng cơ chế tìm thư viện (bài dùng `-Djava.library.path=.`), còn `System.load` là API khác có thể nhận đường dẫn tuyệt đối.

## 4. Biên dịch Java và sinh header JNI chính xác

Tại gốc `jni-first`:

~~~sh
javac --release 17 -h native -d out src/demo/jni/FirstJni.java
~~~

Ý nghĩa:
- `--release 17`: biên dịch tương thích API/bytecode Java 17; chạy được bằng JDK 17+.
- `-d out`: tạo `out/demo/jni/FirstJni.class` theo package.
- `-h native`: sinh `native/demo_jni_FirstJni.h` từ method `native` mà Java compiler nhìn thấy. Đây là **hợp đồng kiểu** nên không chỉnh tay file này.

Trong generated header sẽ xuất hiện đoạn sau (cùng các comment và include guard do `javac` sinh):

~~~c
#include <jni.h>

/*
 * Class:     demo_jni_FirstJni
 * Method:    add
 * Signature: (II)I
 */
JNIEXPORT jint JNICALL Java_demo_jni_FirstJni_add
  (JNIEnv *, jclass, jint, jint);
~~~

Cùng lúc, kiểm tra descriptor trong bytecode Java:

~~~sh
javap -s -p -classpath out demo.jni.FirstJni
~~~

Output có thêm constructor/`main`/static initializer; phần quan trọng phải là:

~~~text
public static native int add(int, int);
  descriptor: (II)I
~~~

**Đọc `(II)I`:** hai `I` trong ngoặc là hai input `int`; `I` sau ngoặc là kết quả `int`. Descriptor là của JVM và không trùng với “tên hàm C”. Tên native symbol ở ví dụ là `Java_demo_jni_FirstJni_add`, bao gồm package, class và tên method (đã escape theo quy tắc JNI). Với overloaded native methods, JVM còn có dạng JNI name dài chứa thông tin signature; hãy để `javac -h` sinh prototype thay vì tự đặt hậu tố.

### Giải mã chữ ký C

| Đoạn prototype | Nghĩa |
|---|---|
| `JNIEXPORT` | Bảo đảm khai báo export/visibility thích hợp để dynamic loader/JVM thấy symbol |
| `jint` ở vị trí trả về | Kiểu JNI cho Java `int`, số có dấu 32-bit |
| `JNICALL` | Calling convention theo JNI/ABI, đặc biệt cần đúng trên Windows |
| `Java_demo_jni_FirstJni_add` | Tên hàm Java-native mà JVM phải resolve cho class/package/method |
| `JNIEnv *` | Con trỏ tới interface JNI dành cho thread hiện tại, JVM cấp khi gọi native |
| `jclass` | Đối số thứ hai cho phương thức Java **static**; phương thức instance sẽ nhận `jobject` |
| `jint, jint` | Hai số nguyên Java `left` và `right`, sau hai tham số ẩn của JNI |

Không được tự bỏ `JNIEnv *` hay `jclass` để tạo một hàm C chỉ nhận hai số. `JNIEnv *` không phải con trỏ quản lý tự tạo; JNI quy định phạm vi sử dụng gắn với thread và lời gọi. Cũng không nên thay `jint` thành C `long`: kích thước `long` thay đổi theo ABI, chẳng hạn Windows 64-bit thường dùng `long` 32-bit trong khi Java `long` là 64-bit (JNI `jlong`).

## 5. Triển khai C khớp header sinh ra

Tạo file **`native/firstjni.c`** với toàn bộ nội dung sau:

~~~c
#include "demo_jni_FirstJni.h"

JNIEXPORT jint JNICALL Java_demo_jni_FirstJni_add(
        JNIEnv *env, jclass declaring_class, jint left, jint right) {
    (void)env;
    (void)declaring_class;
    return left + right;
}
~~~

Đây là C code **hoàn chỉnh cho native library**. Header được sinh bởi `javac` đã include `jni.h` nên chứa các kiểu `jint`, `jclass` và macro JNI. Hai dòng `(void)` tránh cảnh báo unused parameters: `env` và `declaring_class` là tham số ABI bắt buộc dù phương thức cộng chưa cần dùng.

Phải giữ tên hàm, kiểu trả về, số và thứ tự tham số theo generated header. Một thay đổi từ `static` sang instance method ở Java đòi tái tạo header và rà soát code native. Với file C++ (`.cpp`) phải dùng cơ chế `extern "C"` từ generated header; không để C++ name mangling khiến symbol JNI khác tên JVM chờ đợi.

## 6. Xây shared library và chạy end-to-end

Chọn nhánh **cùng hệ điều hành với JVM sẽ chạy**. Các lệnh chạy từ thư mục `jni-first`, sau khi đã tạo source và header như trên.

### Linux: GCC hoặc Clang

Trên Linux có `readlink -f`, có thể suy ra đường dẫn JDK từ `javac`; nếu `JAVA_HOME` đã trỏ đúng JDK thì giữ nguyên giá trị đó:

~~~sh
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"

cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Inative \
  -o libfirstjni.so native/firstjni.c

java -Djava.library.path=. -cp out demo.jni.FirstJni
~~~

`-fPIC` tạo position-independent code, `-shared` xây shared object `libfirstjni.so`; `-I` tìm cả `jni.h`, `jni_md.h` và generated header. Với ví dụ chỉ nhận `JNIEnv *` được JVM đưa vào, không cần tự link `libjvm` hay gọi `JNI_CreateJavaVM`.

### macOS: Clang

Trong Terminal có Xcode Command Line Tools và JDK:

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home)"

cc -std=c11 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Inative \
  -o libfirstjni.dylib native/firstjni.c

java -Djava.library.path=. -cp out demo.jni.FirstJni
~~~

File đầu ra là `libfirstjni.dylib`. Trên Apple Silicon, JVM arm64 cần native binary arm64; nếu JVM chạy ở chế độ x86-64/Rosetta thì native binary phải tương thích x86-64.

### Windows: MSVC Developer Command Prompt (CMD)

`JAVA_HOME` cần chỉ tới JDK đúng kiến trúc, ví dụ trong shell CMD có sẵn `cl.exe` của x64 Native Tools khi JVM x64:

~~~bat
javac --release 17 -h native -d out src\demo\jni\FirstJni.java

cl /nologo /W4 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /Inative ^
  native\firstjni.c /Fe:firstjni.dll

java -Djava.library.path=. -cp out demo.jni.FirstJni
~~~

`/LD` tạo DLL, `/Fe:firstjni.dll` chọn tên đúng với `loadLibrary("firstjni")`. Dấu `^` nối lệnh trong **CMD**, không sao chép các dòng này nguyên xi vào PowerShell. Nếu terminal thiếu `cl.exe`, cần mở đúng Developer Command Prompt hoặc dùng toolchain C phù hợp thay thế.

### Kết quả chính xác của chương trình chuẩn

~~~text
JNI loaded
add(12, 30) = 42
add(-5, 2) = -3
RESULT: PASS
~~~

Kết quả này đã được đối chiếu bằng **JDK 21 (`javac --release 17`), GCC C11 và Linux shared library** với chính hai file nguồn trên. Các nhánh macOS/Windows dùng công cụ native tương ứng; output dự kiến giống nhau nếu cùng chữ ký và hành vi. Chạy từ thư mục chứa shared library, vì dấu `.` ở `java.library.path` là **working directory của process Java**.

Để kiểm tra thêm việc sử dụng JNI trong HotSpot:

~~~sh
java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.FirstJni
~~~

Ví dụ này không gọi thêm hàm qua `JNIEnv` nên output chuẩn không đổi. `-Xcheck:jni` giúp phát hiện một số cách dùng JNI sai khi mở rộng, nhưng không thay thế kiểm thử C về tràn bộ nhớ hay kiểu ABI không tương thích.

## 7. Kiểm tra kiểu: Java type không được suy ra từ C tùy tiện

Java bytecode kiểm tra kiểu theo Java; ở C bạn cần giữ **JNI types** thay vì thay bằng kiểu C có thể trùng kích thước ngẫu nhiên.

| Java type | JNI type | Rủi ro khi bind sai |
|---|---|---|
| `boolean` | `jboolean` | Không đồng nhất với tùy ý `int` hay C `bool`; JNI dùng representation 8-bit |
| `byte` | `jbyte` | Số có dấu 8-bit |
| `short` | `jshort` | Số có dấu 16-bit |
| `char` | `jchar` | Code unit UTF-16 không dấu 16-bit, không phải C `char` thông thường |
| `int` | `jint` | Số có dấu 32-bit; ví dụ `add` dùng kiểu này |
| `long` | `jlong` | Số có dấu 64-bit; không mặc định bằng C `long` |
| `float` | `jfloat` | Float 32-bit theo JNI |
| `double` | `jdouble` | Float 64-bit theo JNI |
| `String` | `jstring` | Tham chiếu đối tượng JVM; không cast thành `char *` |
| `int[]` | `jintArray` | Tham chiếu mảng JVM; truy cập qua JNI API |
| `void` | `void` | Không có kết quả trả về |

Với `static native int add(int,int)`:
- Java compiler công nhận `(II)I`.
- C header sinh prototype `JNIEXPORT jint JNICALL ... (JNIEnv *, jclass, jint, jint)`.
- C implementation phải giữ `jint` cho tham số và return.
- Java caller nhận giá trị `int` và so sánh bằng các test. Kết quả đúng cho 42 và -3 kiểm tra luồng dữ liệu **ở các input này**, không chứng minh implementation đúng mọi input.

Trong JNI, **symbol đúng tên chưa đảm bảo ABI đúng**. Nếu C khai báo sai số/kiểu tham số nhưng vẫn export tên JNI mà JVM tìm thấy, có thể xảy ra giá trị rác, crash hoặc hành vi không xác định. Vì vậy hãy luôn include generated header vào C để compiler đối chiếu prototype và **rebuild** khi thay đổi Java declaration.

### Kiểm tra exported native symbol

Trên Linux, sau khi build:

~~~sh
nm -D --defined-only libfirstjni.so | grep Java_demo_jni_FirstJni_add
~~~

Phải xuất hiện tên `Java_demo_jni_FirstJni_add` dưới dạng symbol được định nghĩa (thường có ký hiệu `T`). Địa chỉ hex thay đổi theo lần build, không phải một expected output cần so chính xác. Có thể xem thông tin symbol bằng:

~~~sh
readelf -Ws libfirstjni.so | grep Java_demo_jni_FirstJni_add
~~~

Trên macOS có `nm -gU libfirstjni.dylib` (ký hiệu có thể mang dấu `_` đầu theo quy ước công cụ). Windows có `dumpbin /EXPORTS firstjni.dll`. Không tìm thấy symbol? Kiểm tra source C có được compile vào binary, phiên bản generated header, tên package/method, `JNIEXPORT/JNICALL`, C++ name mangling và đúng file thư viện thực tế được nạp.

## 8. Lỗi ở giai đoạn nào: bảng chẩn đoán

| Lỗi / dấu hiệu thường thấy | Phân loại | Hướng xử lý |
|---|---|---|
| `javac: file not found`, `package ... does not exist` | Java compile | Đường dẫn source, package, working directory |
| `Could not find or load main class demo.jni.FirstJni` | JVM classpath | `-cp out`, file `out/demo/jni/FirstJni.class`, tên class đầy đủ |
| `fatal error: jni.h: No such file or directory` | C compile | `JAVA_HOME`, `-I` tới header JDK và platform |
| `conflicting types for Java_demo_jni_FirstJni_add` | C compile / sai prototype | Sửa C theo generated header, không sửa tay header |
| `undefined reference` / `LNK2019` trong quá trình build | Native link | Thiếu định nghĩa/import native; giải quyết linker trước lúc chạy JVM |
| `UnsatisfiedLinkError: no firstjni in java.library.path: ...` | **Load:** JVM chưa tìm thấy file library | Kiểm tra tên file, working directory, `-Djava.library.path=.` |
| `cannot open shared object file` / `Library not loaded` | **Load/dependency:** OS loader thiếu thư viện phụ thuộc | Kiểm tra `ldd`, `otool -L` hoặc `dumpbin /DEPENDENTS` |
| `wrong ELF class` / `not a valid Win32 application` / `wrong architecture` | **Load:** sai OS/CPU/ABI | Kiểm tra bản 32/64-bit, arm64/x86-64, đúng native toolchain |
| `UnsatisfiedLinkError: 'int demo.jni.FirstJni.add(int, int)'` | **Method linking:** không resolve được JNI symbol | Kiểm tra `javap -s`, generated header, export và binary cũ |
| `AssertionError: Wrong JNI result: ...` | **Logic/result:** native method đã trả về nhưng sai | Kiểm tra công thức C, dữ liệu input/output, conversion |
| JVM crash khi vào C | **Native/ABI/memory:** không phải Java compile error | Đối chiếu prototype/ABI, pointer, stack, crash log; thử `-Xcheck:jni` |

Thông báo có thể khác tùy JDK và hệ điều hành. Với `UnsatisfiedLinkError`, hãy xem nó xuất hiện tại **`System.loadLibrary`** hay tại **lời gọi `add`**. Một lỗi load trong static initializer có thể khiến những lần thử dùng class về sau báo lỗi khởi tạo class thay vì đúng stack trace ban đầu.

### Có ba loại đường dẫn cần tách riêng

1. `-cp out` tìm **Java class**. Thay đổi classpath không giúp tìm file DLL/SO.
2. `-Djava.library.path=.` giúp JVM tìm **thư viện được `loadLibrary` yêu cầu**. Đặt option trước tên main class và chạy trong đúng working directory.
3. Loader của hệ điều hành tìm **các thư viện mà native binary phụ thuộc**. Linux có `LD_LIBRARY_PATH` và RPATH/RUNPATH; macOS có loader paths và chính sách `DYLD_*`; Windows có DLL search order/PATH. Các yếu tố này khác `java.library.path`, và chỉ thêm Java path có thể không giải quyết dependency thiếu.

Để xem các phụ thuộc của Linux binary đáng tin cậy:

~~~sh
ldd libfirstjni.so
readelf -d libfirstjni.so
~~~

Trên macOS dùng `otool -L libfirstjni.dylib`; Windows dùng `dumpbin /DEPENDENTS firstjni.dll`. Nếu dependency được ghi “not found”, xác định thư viện còn thiếu rồi sửa deploy/search path. Công cụ `ldd` nên chỉ dùng với binary đáng tin cậy trên máy kiểm thử.

## 9. Tái hiện hai lỗi để hiểu khác biệt và cách khắc phục

Chỉ làm hai thí nghiệm sau **sau khi chương trình chuẩn đã PASS**. Sau mỗi thí nghiệm, trả source Java/C về trạng thái đồng bộ, build lại và chạy PASS.

### A. Cố tình dùng library path sai (lỗi nạp)

Trên Linux/macOS, thử một đường dẫn không có thư viện:

~~~sh
java -Djava.library.path=/definitely/not/a/jni/library -cp out demo.jni.FirstJni
~~~

Thông thường, JVM ném lỗi dạng:

~~~text
java.lang.UnsatisfiedLinkError: no firstjni in java.library.path: ...
~~~

Stack trace trỏ tới `System.loadLibrary`/`FirstJni.<clinit>`. Không có dòng `JNI loaded`. Lỗi này xảy ra **trước khi** JVM gọi native `add`; đừng sửa code phép cộng. Sửa lại path đến thư mục có file binary với tên đúng, ví dụ `-Djava.library.path=.` từ thư mục `jni-first`.

### B. Có library nhưng native symbol không tương ứng (lỗi liên kết phương thức)

Giữ nguyên file `libfirstjni.so` đã build có symbol `Java_demo_jni_FirstJni_add`. Trong `FirstJni.java`, đổi **tên method ở khai báo và hai lời gọi** từ `add` thành `addV2`, nhưng **không rebuild file C/shared library**. Chạy lại **chỉ**:

~~~sh
javac --release 17 -h native -d out src/demo/jni/FirstJni.java
java -Djava.library.path=. -cp out demo.jni.FirstJni
~~~

Lần này thư viện có thể nạp thành công, nhưng JVM cần `Java_demo_jni_FirstJni_addV2`. Vì binary vẫn chỉ export symbol cũ, lỗi sẽ có dạng:

~~~text
java.lang.UnsatisfiedLinkError: 'int demo.jni.FirstJni.addV2(int, int)'
~~~

Stack trace tại `FirstJni.addV2(Native Method)`. Thí nghiệm này được đối chiếu trên JDK 21/Linux; cách trình bày lỗi có thể khác trên platform khác. Cách sửa là **đồng bộ Java declaration + generated header + C implementation + native binary** rồi rebuild; không sửa `java.library.path` vì thư viện đã được tìm thấy.

**Thử thêm để phân biệt lỗi kết quả:** với Java chuẩn `add` và library đúng tên, đổi duy nhất thân C từ `return left + right;` sang `return left - right;` rồi rebuild. Native method vẫn có thể liên kết/gọi được, nhưng `main` ném `AssertionError` do 12−30 khác 42. Khôi phục phép cộng sau khi quan sát. Điều này chứng minh **không có `UnsatisfiedLinkError` chưa đủ để kết luận tính toán đúng**.

## 10. Quy trình debug hiệu quả với JNI thực tế

Khi gặp lỗi, làm theo đúng thứ tự dưới đây để tránh sửa sai tầng:

1. **Đóng băng đầu vào:** ghi lại phiên bản Java và JDK, compiler/architecture, Java class/package, tên file native và **lệnh chạy**. Tìm stack trace đầu tiên xuất hiện.
2. **Chứng minh Java build:** chạy `javac -h`, kiểm tra file `.class`, `javap -s` và generated header. So từng kiểu Java với `jint/jlong/...` bên C.
3. **Chứng minh C build:** xem compiler/linker return code và sự tồn tại của binary mới. Lỗi `jni.h`, `conflicting types` hoặc linker error đều ở giai đoạn này.
4. **Chứng minh exported symbol + dependency:** kiểm tra `nm/readelf/dumpbin` và `ldd/otool/dumpbin`; xác nhận architecture và file được JVM tìm đến là **bản build vừa tạo**, không phải file trùng tên cũ.
5. **Chứng minh loader:** chạy Java với `-Djava.library.path` tường minh và `-cp` đúng. Nếu lỗi ở `<clinit>`, tập trung vào tên/path/platform/dependency.
6. **Chứng minh native method lookup:** nếu lỗi xảy ra khi gọi `add`, so `Java_demo_jni_FirstJni_add`, generated header, descriptor `(II)I` và bản native binary đang được nạp.
7. **Chứng minh logic:** chạy các input có expected result, bắt sai lệch bằng assertion/test. Chỉ sau khi toàn chuỗi đã PASS mới mở rộng sang `String`, array, object refs, callback hoặc native memory.

### Các lỗi phổ biến cần tránh

- Tự gõ tên JNI theo trí nhớ, đổi package/class nhưng không tạo lại header và native binary.
- Dùng `long` của C thay `jlong`, dùng `jint` thay `jlong` hoặc đảo vị trí `JNIEnv *`/`jclass`/tham số Java.
- Viết `System.loadLibrary("libfirstjni.so")` hoặc thêm đuôi file trên Windows.
- Cho rằng `java.library.path` thay thế `classpath` hay mọi dependency search path của OS.
- Compile native cho x86 nhưng chạy JVM x64/arm64.
- Sửa C source mà quên build lại shared library, JVM tiếp tục tải binary cũ.
- Chỉ test đường chạy thành công mà không đối chiếu returned values.
- Vội chuyển Java `String` thành C `char *` hoặc Java array thành C pointer; các loại tham chiếu JNI cần API và lifetime tương ứng.

## 11. Bảng nghiệm thu và câu hỏi kiểm tra

| Bước | Dấu hiệu đạt |
|---|---|
| Java compile | Có `out/demo/jni/FirstJni.class`, không có compile error |
| Header | Có `native/demo_jni_FirstJni.h` với `(II)I` và symbol `Java_demo_jni_FirstJni_add` |
| C compile/link | Có đúng file `libfirstjni.so`/`libfirstjni.dylib`/`firstjni.dll` mới và đúng ABI |
| Export | Công cụ symbol hiển thị `Java_demo_jni_FirstJni_add` |
| Load | `System.loadLibrary("firstjni")` không ném `UnsatisfiedLinkError` |
| Native lookup | Hai lời gọi `add` đều resolve và trả `jint` |
| Logic | Giá trị `42` và `-3` đúng, stdout kết thúc bằng `RESULT: PASS` |

**1. `javac` biên dịch thành công nhưng `java` vẫn báo `UnsatisfiedLinkError`. Tại sao?**  
Vì `javac` chỉ biên dịch Java và sinh header, không bảo đảm binary native có tồn tại/đúng kiến trúc/đúng path/đủ dependencies hay có symbol mà JVM cần.

**2. Tại sao có hai đối số “ẩn” trong hàm C khi Java `add` chỉ nhận hai `int`?**  
`JNIEnv *` được JVM cấp để gọi JNI API trên thread hiện tại, và `jclass` là tham chiếu class vì `add` là `static`. Sau đó mới tới hai `jint` từ Java.

**3. Khi nào phải kiểm tra `java.library.path`, khi nào phải kiểm tra symbol export?**  
Lỗi nạp tại `System.loadLibrary` gợi ý tìm file/dependencies/path/kiến trúc. Lỗi tại lời gọi `add` sau khi library đã nạp gợi ý native method name, export và signature.

**4. Vì sao kiểu và kết quả cần kiểm thử riêng?**  
C có thể export đúng tên và phương thức được gọi nhưng hiểu sai kiểu ABI, truyền sai số hoặc tính sai. Chữ ký tương thích là điều kiện cần, assertion đầu ra xác minh hành vi của các test case.

**5. Thấy `RESULT: PASS` có đủ chứng minh mọi lời gọi JNI an toàn?**  
Không. Điều đó xác nhận đường đi, symbol và phép cộng cho hai input của bài; muốn thao tác Java array, `String`, JNI references, thread hay native memory phải kiểm chứng thêm quy tắc JNI tương ứng.

## 12. Kết luận và tài liệu đối chiếu

Với JNI đầu tiên, hãy giữ một chuỗi bằng chứng có thể lặp lại: **Java declaration → `javac -h` → C function đúng prototype → shared library đúng nền tảng → load thành công → resolve đúng symbol → assert kết quả**. Khi xảy ra lỗi, xác định nó đứng ở chặng nào trước khi sửa.

Tài liệu nền tảng: [Oracle JNI Design Overview](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html), [công cụ `javac` và tùy chọn `-h`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), [`System.loadLibrary`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html), [`UnsatisfiedLinkError`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/UnsatisfiedLinkError.html).