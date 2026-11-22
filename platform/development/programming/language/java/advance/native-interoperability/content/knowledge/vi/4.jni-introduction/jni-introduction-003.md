# Sinh tệp JNI header bằng `javac -h` thay cho `javah` cũ

## 1. Vì sao cần sinh JNI header?

Trong Java Native Interface (JNI), Java khai báo phương thức có từ khóa `native` nhưng **phần thân của phương thức nằm trong thư viện bản địa**, thường viết bằng C hoặc C++. Khi chạy, JVM phải tìm được hàm bản địa có tên, kiểu tham số, kiểu trả về và quy ước gọi phù hợp với khai báo Java.

Một tệp header `.h` do JDK sinh ra đóng vai trò **hợp đồng giữa Java và C/C++**. Nó giúp phía native biết:

- Tên hàm JNI cần định nghĩa hoặc xuất (export), bao gồm phần mã hóa tên package/class/phương thức.
- Kiểu trả về JNI, chẳng hạn `jint`, `jlong`, `jobject`.
- Hai tham số JNI ẩn: `JNIEnv *` và `jobject` (cho phương thức instance), hoặc `jclass` (cho phương thức static).
- Danh sách và kiểu các tham số Java được ánh xạ sang kiểu JNI.
- JNI method descriptor xuất hiện trong chú thích, ví dụ `(II)I`.

**Dùng `javac -h` để lấy chữ ký từ mã Java thật, không tự đoán tên hàm JNI.** Mỗi khi đổi chữ ký `native` hoặc tên/package của class, cần sinh lại header và biên dịch lại phần C/C++ tương ứng.

### `javah` đã đi đâu?

`javah` là công cụ đời cũ sinh header từ các class Java **đã biên dịch**. Từ **JDK 8**, `javac` có lựa chọn `-h` để vừa biên dịch nguồn Java vừa sinh native header. Công cụ `javah` đã **bị loại khỏi JDK kể từ JDK 10**. Vì vậy khi sử dụng Java 17, 21 hoặc mới hơn, quy trình chuẩn là:

```text
Tệp .java (khai báo native)
      │
      ▼
javac -h <header-directory> -d <classes-directory> <source.java>
      ├──────────────► tệp .class (bytecode)
      └──────────────► tệp .h (JNI C declarations)
                               │
                               ▼
                       C/C++ include header,
                       định nghĩa hàm JNI
                               │
                               ▼
                       compiler/linker native
                               │
                               ▼
                        .so / .dylib / .dll
                               │
                               ▼
                      JVM load thư viện và gọi
```

Điểm cần phân biệt: **`javac -h` không biên dịch C/C++ và không tự sinh thư viện `.so`/`.dll`**. Nó chỉ sinh bytecode Java cùng header JNI. Trình biên dịch native thực hiện bước còn lại.

## 2. Cú pháp và ý nghĩa các tham số

Cú pháp thường dùng:

```bash
javac -encoding UTF-8 -h build/headers -d build/classes src/demo/jni/NativeAdder.java
```

| Thành phần | Vai trò |
| --- | --- |
| `javac` | Trình biên dịch Java từ bộ **JDK**, không phải `java` launcher |
| `-h build/headers` | Thư mục nhận các **native header** sinh từ khai báo `native` (hoặc hằng số được đánh dấu `@Native`) |
| `-d build/classes` | Thư mục chứa các tệp `.class` sau biên dịch |
| `-encoding UTF-8` | Xác định mã hóa của mã nguồn để xử lý chú thích/chuỗi có dấu ổn định |
| `src/demo/jni/NativeAdder.java` | Đường dẫn **mã nguồn Java** được biên dịch |

`-h` cần **đường dẫn thư mục**, không phải tên tệp `.h` cụ thể. Tên header được `javac` tạo từ danh tính class. Với ví dụ dùng classpath và package `demo.jni` dưới đây, header dự kiến là `demo_jni_NativeAdder.h`.

Thông thường nên tách riêng `build/classes` và `build/headers`. Không nhầm `-h` với `-d`: `-h` quyết định vị trí header, còn `-d` quyết định vị trí bytecode. Có thể dùng cả hai trong **cùng một lần biên dịch**.

## 3. Thực hành từ đầu: một phương thức Java gọi C

Mục này cung cấp chương trình hoàn chỉnh với **Java 17+** và **GCC trên Linux**. Mục tiêu là chứng minh header được tạo đúng, C dùng chính header đó, thư viện được JVM nạp và lệnh gọi native trả kết quả.

### 3.1. Cấu trúc thư mục

Tạo thư mục dự án như sau:

```text
jni-header-demo/
├── src/
│   └── demo/
│       └── jni/
│           └── NativeAdder.java
└── nativeadder.c
```

Sau khi build sẽ có thêm `build/classes`, `build/headers` và `build/lib`. Các tệp trong `build/` là sản phẩm sinh ra; ở ví dụ này không cần viết tay header.

### 3.2. Khai báo phương thức `native` trong Java

Nội dung `src/demo/jni/NativeAdder.java`:

```java
package demo.jni;

public final class NativeAdder {
    static {
        // "nativeadder" là tên logic; JVM thêm tiền tố/hậu tố theo OS.
        System.loadLibrary("nativeadder");
    }

    // Cài đặt thật sự nằm trong thư viện native.
    public native int add(int left, int right);

    public static void main(String[] args) {
        NativeAdder adder = new NativeAdder();
        int result = adder.add(19, 23);
        System.out.println("Result: " + result);
    }
}
```

Ở đây:

- `package demo.jni` là thành phần của danh tính class và tác động tới tên symbol JNI.
- `public native int add(int, int)` **không có thân phương thức Java**. `native` là một phương thức cụ thể được triển khai ở tầng ngoài JVM.
- `System.loadLibrary("nativeadder")` yêu cầu JVM nạp thư viện theo tên logic `nativeadder`: Linux là `libnativeadder.so`, macOS là `libnativeadder.dylib`, Windows là `nativeadder.dll`.
- `main` gọi `add(19, 23)` để kiểm tra việc kết nối Java ↔ native.

**Không cần tạo file `NativeAdder.h` bằng tay.** Chính `javac -h` sẽ tạo nó dựa trên khai báo ở trên.

### 3.3. Sinh header và bytecode bằng một lệnh

Mở terminal **bash trên Linux**, chuyển tới thư mục `jni-header-demo`, bảo đảm `javac` thuộc JDK 17+ và chạy:

```bash
mkdir -p build/classes build/headers build/lib

javac -encoding UTF-8 \
  -h build/headers \
  -d build/classes \
  src/demo/jni/NativeAdder.java
```

Hai đầu ra quan trọng là:

```text
build/
├── classes/
│   └── demo/
│       └── jni/
│           └── NativeAdder.class
└── headers/
    └── demo_jni_NativeAdder.h
```

Trong ví dụ classpath này, `NativeAdder.class` nằm dưới cấu trúc package; header dùng tên class được mã hóa theo quy tắc JNI. Khi sử dụng **named Java module**, cách tổ chức thư mục header có thể còn phản ánh tên module; hãy xem đúng đầu ra của lệnh build thay vì cố đoán đường dẫn.

Nếu `javac` chạy thành công nhưng bạn chỉ tìm trong `build/classes` thì sẽ không thấy header, vì nó được đặt trong thư mục `build/headers` theo `-h`.

### 3.4. Đọc kết quả header được sinh

Mở `build/headers/demo_jni_NativeAdder.h`. Sau các include guard và chú thích, phần quan trọng sẽ tương đương:

```c
#include <jni.h>

/*
 * Class:     demo_jni_NativeAdder
 * Method:    add
 * Signature: (II)I
 */
JNIEXPORT jint JNICALL Java_demo_jni_NativeAdder_add
  (JNIEnv *, jobject, jint, jint);
```

Đây là **đoạn trích minh họa**, không phải nội dung toàn bộ header. File thật còn chứa include guard và khối `extern "C"` để tương thích khi được include từ C++.

Giải thích từng phần:

| Thành phần trong header | Ý nghĩa |
| --- | --- |
| `#include <jni.h>` | Nạp kiểu JNI và macro do JDK định nghĩa |
| `JNIEXPORT` | Bảo đảm ký hiệu hàm được xuất đúng cách trên nền tảng hỗ trợ |
| `jint` | Kiểu JNI tương ứng với `int` của Java |
| `JNICALL` | Quy ước gọi phù hợp ABI/JNI |
| `Java_demo_jni_NativeAdder_add` | Tên export JNI được mã hóa từ package, class và method |
| `JNIEnv *` | Giao diện JNI của **luồng thực hiện lời gọi** |
| `jobject` | Đối tượng `NativeAdder` gọi phương thức instance |
| `jint, jint` | Hai tham số Java `left` và `right` |
| `(II)I` | Descriptor: nhận hai `int` và trả một `int` |

Đếm số tham số C để tránh nhầm: trong ví dụ có **bốn** tham số ở hàm C (hai tham số JNI ẩn và hai tham số Java) dù khai báo Java chỉ có **hai** tham số.

JNI descriptor sử dụng chữ ký ở mức JVM, không dùng cú pháp `(int, int) -> int` của Java. Một số ký hiệu thường gặp: `I` = `int`, `J` = `long`, `Z` = `boolean`, `V` = `void`, `[B` = `byte[]`, `Ljava/lang/String;` = `String`. Vậy `(II)I` nghĩa là `int add(int, int)`.

### 3.5. Cài đặt C theo đúng prototype trong header

Tạo `nativeadder.c` ở thư mục gốc dự án:

```c
#include "demo_jni_NativeAdder.h"

JNIEXPORT jint JNICALL Java_demo_jni_NativeAdder_add(
        JNIEnv *env, jobject receiver, jint left, jint right) {
    (void)env;       // Ví dụ này chưa cần gọi các hàm JNI.
    (void)receiver;  // Ví dụ này chưa dùng đối tượng Java.

    // Đầu vào minh họa 19 và 23 không gây tràn jint.
    return left + right;
}
```

Tên hàm, kiểu trả về và thứ tự tham số phải khớp prototype. Việc `#include` **header do `javac` sinh** giúp trình biên dịch C phát hiện một số bất nhất về khai báo khi biên dịch. Không chỉnh sửa header sinh ra để hợp thức hóa một hàm C sai chữ ký; hãy sửa nguồn Java hoặc C phù hợp rồi sinh lại header.

Đây là ví dụ số học tối giản; với giá trị đầu vào tùy ý, cần kiểm tra tràn số nguyên có dấu ở tầng C trước khi cộng. Java và C không có cùng quy tắc an toàn tràn `int`, nên không nên lấy phép cộng `jint` chưa kiểm tra làm hợp đồng API sản xuất.

### 3.6. Biên dịch thư viện native và chạy Java

`JAVA_HOME` phải chỉ tới **JDK đang dùng**, có các file `include/jni.h` và `include/linux/jni_md.h`. Từ thư mục `jni-header-demo` chạy:

```bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  -o build/lib/libnativeadder.so \
  nativeadder.c

java -Xcheck:jni \
  -Djava.library.path=build/lib \
  -cp build/classes \
  demo.jni.NativeAdder
```

Các thành phần đáng chú ý:

- `-I"$JAVA_HOME/include"` và `-I"$JAVA_HOME/include/linux"`: để GCC tìm được header chuẩn của JNI.
- `-Ibuild/headers`: để tìm `demo_jni_NativeAdder.h` do `javac -h` sinh.
- `-fPIC -shared` và tên `libnativeadder.so`: tạo thư viện chia sẻ cho Linux.
- `-Djava.library.path=build/lib`: bổ sung thư mục tìm thư viện cho JVM. Đặt tùy chọn `-D` **trước** tên class Java.
- `-cp build/classes`: chỉ đường dẫn chứa `demo/jni/NativeAdder.class`.
- `-Xcheck:jni`: bật thêm kiểm tra JNI trong JVM (hữu ích khi học và chẩn đoán).

**Stdout dự kiến:**

```text
Result: 42
```

Luồng chạy là: class `NativeAdder` được khởi tạo → JVM nạp `libnativeadder.so` → `main` gọi `add` → JVM tìm `Java_demo_jni_NativeAdder_add` → C trả `42` → Java in `Result: 42`. Thành công ở bước này chứng tỏ header, bản cài đặt C, tên thư viện và lệnh nạp tương thích với nhau.

### 3.7. Những gì thay đổi ở macOS và Windows

**Trên macOS**, dùng header nền tảng `$JAVA_HOME/include/darwin`, tạo thư viện `libnativeadder.dylib` bằng công cụ tương thích; với Clang từ Command Line Tools có thể dùng:

```bash
cc -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/headers \
  -o build/lib/libnativeadder.dylib \
  nativeadder.c
```

**Trên Windows**, dùng `%JAVA_HOME%\include\win32` khi biên dịch bằng toolchain phù hợp, tạo `nativeadder.dll`, điều chỉnh dấu phân cách đường dẫn và cú pháp biến môi trường theo CMD/PowerShell. Phiên bản kiến trúc của thư viện (ví dụ x64) phải tương thích với JVM. Lệnh Java vẫn sử dụng tên logic `nativeadder` trong `System.loadLibrary`.

Các dòng `gcc` và `cc` ở trên dùng thư viện/toolchain riêng từng hệ điều hành; **header JNI và khai báo Java là phần hợp đồng có thể dùng lại**.

## 4. Thay đổi Java source thì header và C phải đổi như thế nào?

Giả sử đổi Java từ:

```java
public native int add(int left, int right);
```

thành:

```java
public native long add(long left, int right);
```

Đây là **minh họa thay đổi chữ ký**, không phải một chương trình hoàn chỉnh thay thế cho ví dụ trước. Sau khi sửa nguồn, chạy lại `javac -h`. Header mới sẽ có descriptor `(JI)J` vì `J` đại diện cho `long`:

```c
/*
 * Signature: (JI)J
 */
JNIEXPORT jlong JNICALL Java_demo_jni_NativeAdder_add
  (JNIEnv *, jobject, jlong, jint);
```

Mã C phải đổi **kiểu trả về thành `jlong`** và tham số tương ứng thành `jlong`. Nếu Java đã đổi chữ ký nhưng thư viện native chưa được rebuild, kết quả có thể là lỗi liên kết hoặc hành vi sai do ABI không tương thích; chỉ nhìn thấy tên hàm giống nhau **không bảo đảm chữ ký C còn đúng**.

Sau khi cập nhật một native method, thực hiện lại theo đúng thứ tự:

1. Biên dịch lại Java với `javac -h`.
2. Kiểm tra prototype mới trong header.
3. Cập nhật và biên dịch lại C/C++ dựa trên header mới.
4. Nạp thư viện mới bằng tiến trình JVM mới và chạy kiểm thử.

Với method `static native`, tham số thứ hai của hàm JNI là **`jclass` thay vì `jobject`**. Với **overload** (nhiều method cùng tên), tên symbol JNI còn có thể chứa phần mã hóa chữ ký tham số. Những tên class/package có ký tự cần escape cũng chịu quy tắc JNI name mangling. Vì thế không tự rút gọn tên export khi thấy một ví dụ đơn giản; **luôn lấy nguyên prototype từ file `.h` mới sinh**.

## 5. `javac -h` và `javah` khác nhau ở bước nào?

| Khía cạnh | `javah` (quy trình cũ) | `javac -h` (quy trình hiện đại) |
| --- | --- | --- |
| Đầu vào | Class Java đã được biên dịch và có trên classpath | Mã nguồn `.java` được biên dịch |
| Công việc | Sinh JNI header ở bước riêng | Biên dịch Java và sinh header trong một lượt |
| Trạng thái | Không còn trong JDK 10+ | Có từ JDK 8; dùng trên các JDK hiện đại |
| Đầu ra | Native header | Java `.class` và native header |
| Phù hợp Java 17+ | Không | Có |

Một quy trình **lịch sử** từng cần `javac` trước rồi mới dùng `javah` trên class đã biên dịch. Không nên đưa lệnh `javah` vào script dành cho JDK 17+, vì bản phân phối JDK thông thường không còn công cụ này.

Đổi mới đúng bản chất không phải thay tên command từ `javah` sang `javac`; cần **đưa bước sinh header vào chính tác vụ biên dịch source** và trỏ đúng `-h`/`-d`. Nếu một script cũ truyền tên class đã biên dịch cho `javah`, không thể truyền nguyên tên class đó cho `javac -h` rồi kỳ vọng kết quả tương đương: `javac` cần nguồn và lựa chọn biên dịch thích hợp.

## 6. Khi nào `javac -h` tạo header?

Theo tài liệu của `javac`, `-h` sinh native header cho mỗi class:

- Có một hay nhiều phương thức `native`; **hoặc**
- Có một hay nhiều hằng số được đánh dấu bằng annotation `java.lang.annotation.Native`.

Ví dụ khai báo hằng số dành cho native (đoạn này **chỉ minh họa annotation**, không thay thế toàn bộ chương trình ở mục 3):

```java
import java.lang.annotation.Native;

@Native
public static final int FLAG_ENABLED = 1;
```

Khi đặt trường hợp lệ đó **bên trong một class**, compiler có thể đưa định nghĩa hằng số vào header để C dùng cùng giá trị. Ngược lại, `final` đơn thuần không đồng nghĩa với `@Native`; một class không có native method và không có hằng `@Native` thường sẽ không có JNI header.

Với **named module**, classpath và module-path có thể làm khác vị trí header sinh ra theo phiên bản/kiểu build; hãy kiểm tra đường dẫn thực tế do compiler tạo. Với ví dụ classpath trong mục 3, file sinh trực tiếp dưới `build/headers` theo tên đã nêu.

## 7. Kiểm tra descriptor và symbol khi chẩn đoán lỗi

Ngoài header, có thể dùng `javap` để kiểm tra descriptor của class sau biên dịch:

```bash
javap -s -p -classpath build/classes demo.jni.NativeAdder
```

Trong kết quả, dòng liên quan đến `add` tương ứng với:

```text
public native int add(int, int);
  descriptor: (II)I
```

`javap -s` hiển thị descriptor từ bytecode; nó là **công cụ kiểm tra**, không thay thế chức năng sinh header `-h`. Đối chiếu `(II)I` với ghi chú `Signature: (II)I` trong header để xác nhận Java source và bytecode đồng nhất.

Nếu cần kiểm tra symbol của thư viện trên Linux, có thể dùng `nm -D build/lib/libnativeadder.so` (nếu toolchain có `nm`) rồi tìm tên `Java_demo_jni_NativeAdder_add`. Một tên sai package/class, một thư viện không được nạp, hoặc phiên bản `.so` cũ có thể gây lỗi runtime mặc dù lệnh `javac -h` đã chạy thành công.

## 8. Các lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `javah: command not found` / không tìm được `javah` | Dùng JDK 10+ | Chuyển pipeline sang `javac -h`; không cố dùng `javah` trên JDK mới |
| `javac: no source files` hoặc không tìm thấy tệp | Truyền tên class hoặc đường dẫn `.java` sai | Cấp đường dẫn source thật, ví dụ `src/demo/jni/NativeAdder.java` |
| Không xuất hiện file `.h` | Tìm nhầm dưới `-d`; class không có `native`/`@Native`; bước compile bị bỏ qua | Kiểm tra `-h`, lỗi biên dịch, khai báo native và task thực sự chạy |
| `jni.h: No such file or directory` | GCC chưa được cấp include path của JDK | Chỉ đúng `JAVA_HOME/include` và include path của hệ điều hành |
| `demo_jni_NativeAdder.h: No such file or directory` | Sai thư mục header hoặc chưa chạy `javac -h` | Thêm `-Ibuild/headers`, sinh lại header trước khi build C |
| `UnsatisfiedLinkError: no nativeadder in java.library.path` | Thư viện chưa build hoặc JVM tìm sai thư mục/tên file | Kiểm tra `build/lib`, tên file hệ điều hành và `-Djava.library.path` |
| `UnsatisfiedLinkError` khi gọi phương thức `native` | Tên exported symbol không khớp, overload sai, thư viện cũ | Đối chiếu header mới, tên symbol và rebuild thư viện |
| Compile C báo conflicting types | Prototype trong `.h` không khớp định nghĩa C | Sửa định nghĩa C theo header được sinh từ Java mới nhất |
| Chạy sai nền tảng/kiến trúc | Dùng include `linux` trên Windows hoặc thư viện khác kiến trúc JVM | Dùng include `linux/darwin/win32` và toolchain đúng nền tảng |

**Tuyệt đối không chỉnh file `.h` sinh ra để “vá” chữ ký** rồi quên sửa `.java` hoặc C. Header là kết quả của source-of-truth Java; khi rebuild, mọi chỉnh sửa thủ công có thể bị ghi đè.

## 9. Đưa bước sinh header vào quy trình build

Khi ví dụ nhỏ trở thành dự án thực tế, nên coi header là **artifact sinh ra từ nguồn Java** và thiết lập thứ tự phụ thuộc:

```text
compile Java + generate JNI headers (javac -h)
                     ↓
compile/link C hoặc C++ (dùng đúng header mới)
                     ↓
đóng gói thư viện native và cấu hình đường dẫn nạp
                     ↓
chạy kiểm thử tích hợp Java ↔ native
```

Trong Gradle/Maven hoặc script build nội bộ, việc compile native cần phụ thuộc đúng bước Java tạo header; không giả định rằng chỉ cần compile Java một lần rồi header sẽ mãi đúng. Nếu thay đổi chữ ký `native`, tên package hoặc class, cần bảo đảm compiler và bước compile C được chạy lại. Khi điều tra lỗi khó tái hiện, dọn artifact build cũ và build sạch là một cách hợp lý để loại trừ header/thư viện stale.

Header của JNI chỉ chứa khai báo cho cầu nối; **không tự giải quyết** quản lý bộ nhớ bản địa, vòng đời tham chiếu JNI, exception, luồng, hoặc ABI của những API C/C++ khác. Đây là bài mở đầu tập trung vào việc sinh chữ ký JNI chính xác.

## 10. Tự kiểm tra

1. Với `native int add(int, int)` trong package `demo.jni`, vì sao tên hàm C lại là `Java_demo_jni_NativeAdder_add` thay vì chỉ `add`? Chữ `(II)I` trong header biểu thị điều gì?
2. Lệnh `javac -h build/headers -d build/classes src/demo/jni/NativeAdder.java` tạo ra **hai loại file** nào? Chúng nằm ở đâu và được sử dụng bởi thành phần nào?
3. Nếu chuyển phương thức thành `static native int add(int, int)`, tham số JNI nào thay đổi từ `jobject` thành `jclass`? Vì sao việc tự viết prototype cũ trở nên rủi ro?
4. Vì sao không thể dùng lại một script `javah` cũ trên JDK 21? Tên class compiled từng truyền cho `javah` có thể đưa trực tiếp vào `javac -h` không?
5. Nếu Java đổi từ `int add(int, int)` thành `long add(long, int)`, hãy nêu descriptor mới, kiểu JNI mới và **thứ tự rebuild** cần thực hiện.

**Ghi nhớ:** Với Java hiện đại, dùng **`javac -h <header-dir>`** ngay khi biên dịch source để sinh JNI header; dùng **`-d <class-dir>`** cho bytecode; **include header được sinh vào mã C/C++ và biên dịch native library riêng**. Chữ ký Java thay đổi thì sinh lại header, cập nhật C và rebuild thư viện.

### Tài liệu chính thức

- [`javac` — mục `-h directory` (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html).
- [Oracle JDK 17 Migration Guide — `javah` bị loại khỏi JDK 10](https://docs.oracle.com/en/java/javase/17/migrate/removed-tools-and-components.html).
- [JNI Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/).
