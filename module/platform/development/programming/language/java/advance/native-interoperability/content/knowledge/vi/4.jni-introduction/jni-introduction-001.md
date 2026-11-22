# Luồng từ phương thức `native` đến phần triển khai C hoặc C++ bằng JNI

## 1. Mục tiêu và bức tranh tổng thể

**JNI (Java Native Interface)** là giao diện cho phép mã Java chạy trong JVM gọi hàm native được biên dịch thành thư viện máy, thường viết bằng C hoặc C++. Bài này theo dõi **trọn vẹn một lời gọi**: từ khai báo `native`, sinh header, build và nạp thư viện, liên kết symbol, JVM chuyển đối số sang JNI, C/C++ xử lý, rồi trả kết quả về Java.

Sau bài học, bạn có thể:

- Viết một lớp Java chứa phương thức `native` và nạp thư viện qua `System.loadLibrary`.
- Dùng `javac -h` sinh header JNI khớp chính xác khai báo Java.
- Tạo thư viện chia sẻ `.so`, `.dylib` hoặc `.dll` có triển khai C **hoặc** C++.
- Hiểu vì sao hàm native có thêm `JNIEnv *` và `jclass`/`jobject`, cách `jint`, `jstring` đi qua ranh giới.
- Phân biệt nạp thư viện với liên kết phương thức; chẩn đoán `UnsatisfiedLinkError` và các lỗi lifetime/ABI.

Sơ đồ tổng quát:

~~~text
Java source                      Build native                    Khi chạy
JniJourney.java  --javac -h--> JniJourney.h
     |                                |
     |                           jni_journey.c/.cpp
     |                                |
     v                                v
JniJourney.class                 libjnijourney.so / .dylib / jnijourney.dll
     |                                ^
     | JVM khởi tạo lớp               | System.loadLibrary("jnijourney")
     v                                |
Java gọi add(20,22) --> JVM tìm/liên kết JNI entry point
                                |
                                v
                Java_JniJourney_add(JNIEnv *, jclass, jint, jint)
                                |
                                v
                         C/C++ trả jint 42
                                |
                                v
                       Java nhận int 42
~~~

**Phân biệt ba việc:** (1) `javac` biên dịch Java và tạo header; (2) trình biên dịch C/C++ tạo thư viện native; (3) **JVM** nạp thư viện và chuyển điều khiển vào hàm JNI khi ứng dụng chạy. `javac` không biên dịch mã C/C++, và JVM không tự tạo bản triển khai native chỉ từ từ khóa `native`.

JNI xuất hiện trong ứng dụng cần tích hợp thư viện hệ điều hành, mã C/C++ sẵn có, thiết bị/driver, công nghệ native hoặc phép tính chuyên biệt. JNI cho phép truy cập bộ nhớ và API ngoài cơ chế an toàn thông thường của Java: một lỗi native có thể làm crash cả JVM.

## 2. Chuẩn bị project và môi trường

Ví dụ sử dụng **JDK 17 trở lên** và C11 hoặc C++17. Để có kết quả xác định trên mọi nền tảng, ví dụ chỉ cộng hai số nhỏ và xử lý chuỗi ASCII `"Java"`.

Yêu cầu: `javac` và `java` thuộc **cùng bộ JDK**, trình biên dịch C/C++ tương ứng với hệ điều hành (GCC/Clang hoặc MSVC), và biến môi trường `JAVA_HOME` trỏ tới **thư mục gốc của JDK có `include/jni.h`**. JDK và thư viện native phải cùng kiến trúc, ví dụ cả hai đều x64 hoặc cả hai đều ARM64.

Cấu trúc thư mục **sau khi build** trên Linux minh họa:

~~~text
jni-first/
├── JniJourney.java
├── JniJourney.class          # javac tạo
├── JniJourney.h              # javac -h tạo
├── jni_journey.c             # chọn C
├── libjnijourney.so          # compiler/linker tạo
└── ...                       # trên macOS/Windows tên thư viện khác
~~~

Mọi lệnh phía dưới chạy từ thư mục `jni-first`. Chỉ cần **một** triển khai: dùng `jni_journey.c` **hoặc** `jni_journey.cpp`. Không link cả hai vì chúng export cùng hai JNI symbol.

## 3. Bước 1 — Khai báo phương thức `native` trong Java

Tạo **`JniJourney.java`** (không có khai báo `package` để tên JNI dễ quan sát):

~~~java
public final class JniJourney {
    static {
        System.loadLibrary("jnijourney");
    }

    private JniJourney() {
    }

    public static native int add(int left, int right);

    public static native String greet(String name);

    public static void main(String[] args) {
        int result = add(20, 22);
        String greeting = greet("Java");

        System.out.println("add(20, 22) = " + result);
        System.out.println(greeting);
    }
}
~~~

Điểm cần hiểu:

1. `native` báo cho compiler/JVM biết rằng **thân phương thức được triển khai bên ngoài bytecode Java**. Vì thế Java khai báo kết thúc bằng dấu `;`, không có khối `{ ... }`.
2. `static` là lựa chọn của ví dụ để gọi trực tiếp trên lớp. Một native method **instance** cũng hợp lệ; khi đó hàm JNI nhận `jobject` thay cho `jclass`.
3. Khối khởi tạo `static` chạy khi JVM khởi tạo lớp trước việc sử dụng `main`/phương thức static; nó gọi `System.loadLibrary("jnijourney")` để nạp thư viện tương ứng nền tảng.
4. `"jnijourney"` là **tên logic** của thư viện: trên Linux thường khớp `libjnijourney.so`, macOS khớp `libjnijourney.dylib`, Windows khớp `jnijourney.dll`. Không viết đường dẫn hoặc tiền tố `lib`/đuôi `.dll` vào `loadLibrary`.
5. `int` và `String` ở Java **chưa phải** tham số C thông thường: JVM sẽ chuyển sang các kiểu JNI `jint` và `jstring` theo đặc tả.

Bản Java này **biên dịch được khi chưa có thư viện native**, nhưng nếu chạy ngay thì bước nạp thư viện hoặc liên kết symbol sẽ thất bại. Hai bước biên dịch Java và build native là độc lập.

## 4. Bước 2 — Sinh header JNI bằng JDK

Trong thư mục `jni-first`, chạy:

~~~bash
javac -h . JniJourney.java
~~~

Tham số `-h .` yêu cầu `javac` tạo header native trong thư mục hiện tại. Kết quả gồm `JniJourney.class` và **`JniJourney.h`**. Không chỉnh tay header được sinh: nếu bạn đổi tên lớp, package, phương thức, overload hoặc kiểu Java, hãy **chạy lại `javac -h`** rồi biên dịch lại native.

Phần quan trọng của header sẽ có hai khai báo tương đương:

~~~c
#include <jni.h>

/* Trích yếu các prototype được sinh; không phải toàn bộ header */
JNIEXPORT jint JNICALL Java_JniJourney_add(
    JNIEnv *, jclass, jint, jint);

JNIEXPORT jstring JNICALL Java_JniJourney_greet(
    JNIEnv *, jclass, jstring);
~~~

Ý nghĩa:

- `JNIEXPORT` đánh dấu cách export symbol để JVM có thể tìm thấy hàm trong thư viện động (chi tiết macro tùy nền tảng).
- `JNICALL` chỉ định quy ước gọi mà JNI yêu cầu trên nền tảng tương ứng.
- `JNIEnv *` cho native code quyền gọi các hàm JNI để thao tác với đối tượng/trạng thái JVM trong **thread hiện tại**.
- `jclass` là đối số ngầm cho native method `static`; với native method instance, đối số thứ hai là `jobject` (đối tượng `this`).
- Các đối số Java xuất hiện **sau hai tham số ngầm** theo đúng thứ tự khai báo.
- `jint` là kiểu JNI dành cho Java `int`; `jstring` là tham chiếu JNI đến đối tượng Java `String`. Không diễn giải `jstring` là `char *`.

Tên `Java_JniJourney_add` và `Java_JniJourney_greet` là tên **JNI entry point**, không phải tên Java tùy chọn. JVM liên kết chúng với các phương thức `native` nhờ quy tắc đặt tên của JNI (hoặc một cơ chế đăng ký tường minh, xem phần sau).

## 5. Bước 3 — Cài đặt hai JNI entry point bằng C

Tạo **`jni_journey.c`** với nội dung đầy đủ:

~~~c
#include "JniJourney.h"
#include <stdio.h>

JNIEXPORT jint JNICALL Java_JniJourney_add(
        JNIEnv *env, jclass clazz, jint left, jint right) {
    (void) env;
    (void) clazz;

    return left + right;
}

JNIEXPORT jstring JNICALL Java_JniJourney_greet(
        JNIEnv *env, jclass clazz, jstring name) {
    (void) clazz;

    if (name == NULL) {
        jclass type = (*env)->FindClass(
                env, "java/lang/NullPointerException");
        if (type != NULL) {
            (*env)->ThrowNew(env, type, "name must not be null");
        }
        return NULL;
    }

    const char *chars = (*env)->GetStringUTFChars(env, name, NULL);
    if (chars == NULL) {
        return NULL;  /* JVM đã có ngoại lệ đang chờ, thường OOME */
    }

    char buffer[128];
    int count = snprintf(buffer, sizeof(buffer), "Hello, %s!", chars);

    (*env)->ReleaseStringUTFChars(env, name, chars);

    if (count < 0 || (size_t) count >= sizeof(buffer)) {
        jclass type = (*env)->FindClass(
                env, "java/lang/IllegalArgumentException");
        if (type != NULL) {
            (*env)->ThrowNew(env, type, "name is too long");
        }
        return NULL;
    }

    return (*env)->NewStringUTF(env, buffer);
}
~~~

**`add`: Java → C → Java**

- Java truyền `20` và `22` dưới dạng hai giá trị `int`; khi vào JNI chúng có kiểu `jint`.
- JVM thêm `JNIEnv *env` và `jclass clazz`; hàm `add` không cần dùng hai tham số này nên ép sang `void` để tránh cảnh báo compiler.
- C tính `left + right` với hai số nhỏ và trả về `jint 42`.
- JVM nhận giá trị `jint` và chuyển trở lại kết quả `int` của lời gọi Java.

**`greet`: Java `String` → JNI → Java `String`**

- `name` là một **tham chiếu JNI** đến đối tượng `String`. Không được ép thẳng thành `char *` hoặc đọc trực tiếp layout nội bộ của đối tượng.
- `GetStringUTFChars` lấy một chuỗi byte **Modified UTF-8** có byte NUL kết thúc; JVM có thể tạo bản sao hoặc dùng vùng nhớ được ghim. Vì vậy mã phải gọi `ReleaseStringUTFChars` khi xong.
- `snprintf` đưa tên vào buffer cố định và trả số byte cần để ghi (không tính NUL); mã kiểm tra để tránh trả một chuỗi bị cắt. Ví dụ giới hạn tổng chiều dài đầu ra ở 127 byte.
- `NewStringUTF` tạo **Java `String` mới** từ Modified UTF-8. Với đầu vào ASCII `"Java"`, kết quả chính xác là `"Hello, Java!"`.
- Nếu `name == NULL` hoặc chuỗi quá dài, native code tạo Java exception bằng `FindClass`/`ThrowNew` rồi trả `NULL`. Khi quay về Java, JVM lan truyền ngoại lệ đang chờ. `GetStringUTFChars` trả `NULL` khi thất bại (ví dụ thiếu bộ nhớ) nên phải kiểm tra trước khi dùng.

**Lưu ý encoding:** Modified UTF-8 của JNI **khác một số trường hợp với UTF-8 chuẩn**, đặc biệt đối với U+0000 và cặp surrogate. Ví dụ chạy dùng ASCII để giữ stdout ổn định; khi tích hợp chuỗi Unicode hoặc API yêu cầu UTF-8 chuẩn, phải xử lý chuyển mã đúng thay vì coi hai dạng là đồng nhất.

## 6. Bước 4 — Biên dịch thư viện native

Chọn đúng một nhóm lệnh cho hệ điều hành. `JAVA_HOME` phải trỏ đến JDK hiện đang dùng để biên dịch/chạy Java.

### Linux với GCC hoặc Clang

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  jni_journey.c -o libjnijourney.so
~~~

### macOS với Clang

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  jni_journey.c -o libjnijourney.dylib
~~~

### Windows x64 với MSVC

Mở **x64 Native Tools Command Prompt for Visual Studio** rồi chạy:

~~~bat
cl /nologo /W4 /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" jni_journey.c /link /OUT:jnijourney.dll
~~~

Lưu ý: các ví dụ lệnh shell là **ba lựa chọn theo nền tảng**, không chạy nối tiếp. Trên Windows, `JAVA_HOME` phải là biến môi trường tương ứng của CMD, không phải biến theo cú pháp Bash. Cần MSVC build đúng x64 nếu JVM là x64.

Các tùy chọn thường gặp:

- `-I` hoặc `/I`: chỉ thư mục header của JDK, nơi chứa `jni.h` và header phụ thuộc hệ điều hành.
- `-fPIC`: sinh mã độc lập vị trí phù hợp cho shared object trên các nền tảng áp dụng.
- `-shared`/`-dynamiclib`/`/LD`: tạo thư viện chia sẻ để JVM nạp.
- Tên output phải khớp cách JVM ánh xạ `"jnijourney"` trên nền tảng thực tế.

Thư viện JNI dùng đúng ABI của tiến trình đang chạy. Không thể nạp `.dll` Windows vào JVM Linux, thư viện x86-64 vào tiến trình ARM64, hoặc trộn 32-bit và 64-bit. Với các dependency native khác, trình nạp của hệ điều hành cũng phải tìm được những thư viện phụ thuộc đó.

## 7. Bước 5 — Chạy và theo dõi kết quả

Từ thư mục chứa `JniJourney.class` và thư viện native đã tạo, chạy:

~~~bash
java -Djava.library.path=. JniJourney
~~~

Kết quả stdout thành công:

~~~text
add(20, 22) = 42
Hello, Java!
~~~

`-Djava.library.path=.` bổ sung thư mục hiện tại vào đường tìm kiếm thư viện của JVM trong ví dụ. Thiết lập từ lúc khởi động JVM; nếu cấu hình lại đường tìm kiếm, hãy **khởi động tiến trình Java mới**. `java.library.path` và biến đường tìm kiếm dependency của hệ điều hành (ví dụ `PATH`/`LD_LIBRARY_PATH`) có vai trò liên quan nhưng không hoàn toàn giống nhau.

### 7.1. Dòng thời gian thực tế của `add(20, 22)`

1. JVM tải/khởi tạo `JniJourney`; khối `static` yêu cầu nạp `jnijourney`. OS loader mở file thư viện có kiến trúc phù hợp; JNI/VM ghi nhận thư viện trong ngữ cảnh class loader.
2. Mã Java gọi `JniJourney.add(20, 22)`. Bytecode mô tả lời gọi tới một phương thức có cờ `native`; phương thức không có phần thân bytecode do Java compiler tạo.
3. JVM **giải quyết native entry point**. Với cách liên kết theo tên trong ví dụ, JVM tìm symbol export `Java_JniJourney_add` trong thư viện đã nạp. Chi tiết **thời điểm** giải quyết có thể phụ thuộc JVM; không nên giả định mỗi lời gọi đều dò symbol từ đầu.
4. JVM chuẩn bị chuyển từ Java sang mã native, truyền `JNIEnv *`, `jclass` và hai `jint` đúng theo JNI/ABI trên nền tảng.
5. Hàm C chạy, tính `20 + 22`, đặt kết quả `jint 42` theo quy ước gọi và trả điều khiển cho JVM.
6. JVM hoàn tất bước trở về Java, chuyển giá trị thành `int 42`. Java in dòng đầu tiên.

Với `greet("Java")`, thay bước scalar bằng một **JNI reference `jstring`**. Native phải sử dụng API trên `JNIEnv` để đọc/tạo String; JVM vẫn quản lý đối tượng Java và garbage collector.

Mô hình này giúp phân biệt **hai cổng giao tiếp**: Java ↔ JNI runtime ↔ thư viện C/C++. JVM và mã native phải thống nhất chữ ký JNI, ABI, kiểu dữ liệu và lifetime của dữ liệu được mượn.

## 8. Nếu triển khai bằng C++ thay cho C

C++ dùng cùng header `JniJourney.h` và cùng Java class; khác biệt dễ nhìn là lời gọi JNI: **C** dùng `(*env)->NewStringUTF(env, ...)`, **C++** dùng `env->NewStringUTF(...)`. JNI cung cấp các giao diện cú pháp khác nhau để hỗ trợ hai ngôn ngữ.

Để thay C bằng C++, **không build `jni_journey.c`**. Thay bằng toàn bộ file **`jni_journey.cpp`**:

~~~cpp
#include "JniJourney.h"
#include <cstddef>
#include <cstdio>

extern "C" JNIEXPORT jint JNICALL Java_JniJourney_add(
        JNIEnv *env, jclass clazz, jint left, jint right) {
    (void) env;
    (void) clazz;
    return left + right;
}

extern "C" JNIEXPORT jstring JNICALL Java_JniJourney_greet(
        JNIEnv *env, jclass clazz, jstring name) {
    (void) clazz;

    if (name == nullptr) {
        jclass type = env->FindClass("java/lang/NullPointerException");
        if (type != nullptr) {
            env->ThrowNew(type, "name must not be null");
        }
        return nullptr;
    }

    const char *chars = env->GetStringUTFChars(name, nullptr);
    if (chars == nullptr) {
        return nullptr;
    }

    char buffer[128];
    int count = std::snprintf(buffer, sizeof(buffer), "Hello, %s!", chars);
    env->ReleaseStringUTFChars(name, chars);

    if (count < 0 || static_cast<std::size_t>(count) >= sizeof(buffer)) {
        jclass type = env->FindClass(
                "java/lang/IllegalArgumentException");
        if (type != nullptr) {
            env->ThrowNew(type, "name is too long");
        }
        return nullptr;
    }

    return env->NewStringUTF(buffer);
}
~~~

Biên dịch **file C++ thay thế** trên Linux:

~~~bash
c++ -std=c++17 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  jni_journey.cpp -o libjnijourney.so
~~~

Trên macOS:

~~~bash
c++ -std=c++17 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  jni_journey.cpp -o libjnijourney.dylib
~~~

Trên Windows x64 (MSVC Native Tools CMD):

~~~bat
cl /nologo /EHsc /W4 /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" jni_journey.cpp /link /OUT:jnijourney.dll
~~~

Sau khi build, chạy lại đúng lệnh Java ở phần 7. **Stdout giống hệt bản C** vì hai phiên bản export cùng các tên/kiểu JNI và cùng logic.

**Vì sao cần `extern "C"`?** C++ thường *name-mangle* symbol để biểu diễn overload. JNI tra cứu tên export theo quy tắc của JNI; dùng C linkage giúp tên export đúng dạng `Java_JniJourney_add`. Header do `javac -h` sinh cũng bảo vệ các prototype C++ bằng cơ chế `extern "C"`; viết rõ ở định nghĩa giúp minh họa chủ đích. Không được để C++ exception thoát thẳng qua biên JNI: hãy xử lý trong C++ và báo lỗi bằng cơ chế JNI thích hợp (ví dụ `ThrowNew`). Chỉ khai báo `extern "C"` không làm một C++ class có layout C ổn định.

## 9. Chữ ký native: cách JVM tìm đúng hàm

Với lớp không thuộc package của ví dụ:

| Java | C/C++ JNI |
| --- | --- |
| `public static native int add(int, int);` | `Java_JniJourney_add(JNIEnv *, jclass, jint, jint)` trả `jint` |
| `public static native String greet(String);` | `Java_JniJourney_greet(JNIEnv *, jclass, jstring)` trả `jstring` |

Khi có package, tên export mang tên package. Ví dụ lớp `com.example.NativeMath` với phương thức `add` thường có tiền tố `Java_com_example_NativeMath_add`. Dấu gạch dưới trong tên, Unicode, ký tự đặc biệt và overload còn có **quy tắc escape**; không tự ghép tên theo cảm tính.

Với các **native method overload**, tên JNI dạng dài có thể cần hậu tố `__` cùng chữ ký tham số đã mã hóa. JVM thử cơ chế tìm tên ngắn/dài theo đặc tả JNI; nếu overload yêu cầu phân biệt, các symbol phải không mơ hồ. Header do `javac -h` sinh là nguồn quyết định để không viết sai tên. Nếu Java đổi signature mà bạn quên build lại native, việc tìm symbol hoặc ABI của lời gọi có thể bị sai.

Ngoài liên kết theo tên export, JNI có cơ chế **`RegisterNatives`** để đăng ký tên phương thức, chữ ký JNI và con trỏ hàm C/C++. Ví dụ khai báo cấu trúc thông tin (đoạn minh họa, không phải chương trình độc lập):

~~~c
/* Ví dụ mô tả một entry đăng ký native method */
JNINativeMethod entry = {
    "add",        /* Tên phương thức Java */
    "(II)I",      /* (int, int) -> int theo JNI descriptor */
    (void *) native_add_impl
};

/* Sau khi có env và jclass chính xác, kiểm tra kết quả: */
// (*env)->RegisterNatives(env, clazz, &entry, 1);
~~~

Khi sử dụng `RegisterNatives`, code phải cung cấp `native_add_impl` có đúng prototype ABI của JNI và đăng ký với `jclass` phù hợp. Cơ chế này hữu ích khi tự chủ trình khởi tạo, nhưng **không cần thiết** cho ví dụ `Java_JniJourney_add` theo tên export. Một mục đăng ký sai có thể dẫn đến hành vi không xác định, nên dùng đúng chữ ký và chỉ đăng ký những phương thức bạn kiểm soát.

### 9.1. Phương thức `static` và instance khác nhau thế nào?

~~~java
// Minh họa khai báo trong một lớp, chưa phải ví dụ chạy độc lập:
public static native int staticSum(int a, int b);
public native int instanceSum(int a, int b);
~~~

Prototype khái niệm sau khi `javac -h`:

~~~c
JNIEXPORT jint JNICALL Java_Example_staticSum(
        JNIEnv *env, jclass clazz, jint a, jint b);

JNIEXPORT jint JNICALL Java_Example_instanceSum(
        JNIEnv *env, jobject self, jint a, jint b);
~~~

Ở ví dụ ký hiệu `Example` là tên lớp giả định dùng để minh họa signature; nếu class thực có package hoặc tên khác, header thay đổi tương ứng. **Tham số thứ hai** là class reference đối với static native, còn instance native nhận reference tới đối tượng hiện tại. Java method có hai tham số thì hàm C nhận bốn tham số, không phải hai.

## 10. Java và JNI truyền những kiểu gì?

| Kiểu Java | Kiểu JNI thường dùng ở C/C++ | Ghi chú |
| --- | --- | --- |
| `boolean` | `jboolean` | Dùng `JNI_TRUE`/`JNI_FALSE` khi cần; không giả định C `bool` có ABI giống nhau |
| `byte` | `jbyte` | 8-bit signed theo Java |
| `char` | `jchar` | 16-bit unsigned UTF-16 code unit, không phải C `char` |
| `short` | `jshort` | 16-bit signed |
| `int` | `jint` | 32-bit signed |
| `long` | `jlong` | 64-bit signed, **không** suy ra C `long` là 64-bit trên Windows |
| `float` | `jfloat` | 32-bit floating-point |
| `double` | `jdouble` | 64-bit floating-point |
| `String` | `jstring` | Reference opaque tới Java String |
| `int[]` | `jintArray` | Reference tới mảng Java; cần API JNI để truy cập |
| `Object`/lớp Java | `jobject`/kiểu tham chiếu JNI thích hợp | Không được dereference như một con trỏ tới C struct |
| `void` | `void` | Native method không trả kết quả |

**Primitive** được truyền theo giá trị tương ứng; Java object/array được truyền qua **JNI reference** mà JVM quản lý. Đừng giả định địa chỉ con trỏ `jobject` là địa chỉ ổn định của object heap: GC có thể di chuyển object, còn handle JNI vẫn được JVM quản lý qua cơ chế reference.

Một JNI reference trả về từ JNI function thường là **local reference**. Với lời gọi native do Java bắt đầu, local reference hợp lệ trong thời gian lời gọi trên thread đó và được JVM thu hồi khi native method kết thúc. Nếu native cần giữ object qua nhiều lời gọi, phải tạo **global reference** qua `NewGlobalRef` rồi `DeleteGlobalRef` đúng lúc. Không lưu local reference vào biến toàn cục và tái sử dụng ở thread khác.

### 10.1. Khi nhận mảng `int[]`

Ví dụ minh họa **mẫu JNI** cho một đối số `jintArray`, không phải chương trình `JniJourney` chạy độc lập:

~~~c
JNIEXPORT jint JNICALL Java_Example_firstElement(
        JNIEnv *env, jclass clazz, jintArray values) {
    (void) clazz;

    if (values == NULL) {
        return 0;  /* Ví dụ giản lược: API thực cần hợp đồng lỗi */
    }

    jsize length = (*env)->GetArrayLength(env, values);
    if (length == 0) {
        return 0;
    }

    jint value = 0;
    (*env)->GetIntArrayRegion(env, values, 0, 1, &value);
    return value;
}
~~~

`GetIntArrayRegion` **sao chép** phần tử được yêu cầu vào buffer C, cho phép code chỉ cần giá trị đầu tiên mà không phải nắm giữ con trỏ đến cả mảng. Mẫu này chỉ hợp lý sau khi kiểm tra null và độ dài. Nếu thao tác qua `GetIntArrayElements`, phải cân nhắc bản sao và **gọi `ReleaseIntArrayElements`** đúng quy tắc; nhiều vùng dữ liệu JNI trả về phải được release và không được dùng sau release.

## 11. Điều gì xảy ra khi có lỗi hoặc Java exception?

JNI không tự chuyển mọi `errno`, C return code, C++ exception hoặc lỗi cấp phát thành Java exception. Cần xác định hợp đồng báo lỗi:

- **Java exception đang chờ:** `ThrowNew` đánh dấu ngoại lệ để JVM ném khi điều khiển trở về Java; code native phải trả về kiểu tương thích và tránh tiếp tục các lời gọi JNI không được phép khi còn pending exception.
- **JNI operation thất bại:** `GetStringUTFChars` hoặc `NewStringUTF` có thể trả `NULL` khi thất bại; nhiều API JNI đặt một exception đang chờ. Kiểm tra kết quả trước khi dùng.
- **C++ exception:** catch ở phía C++, dọn tài nguyên, rồi tạo Java exception phù hợp. Để C++ exception vượt qua frame JNI là cách tích hợp không an toàn.
- **Native crash:** dereference con trỏ sai, use-after-free, sai ABI hoặc buffer overflow có thể kết thúc cả JVM; Java `try/catch` không sửa được bộ nhớ native bị hỏng.
- **Native function trả bình thường:** một giá trị `jint 0` không tự có nghĩa là “thành công”. Ý nghĩa lỗi/kết quả phải do thiết kế API quy định.

Ví dụ thay vì kết thúc bằng `return NULL` khi input null, hàm `greet` gọi `FindClass("java/lang/NullPointerException")` rồi `ThrowNew`; Java sẽ nhìn thấy Java exception. Trả `NULL` ở đây **không thay cho việc tạo exception** mà chỉ là giá trị trả phù hợp khi kết thúc hàm native có exception đang chờ.

### 11.1. `JNIEnv *` và an toàn theo thread

`JNIEnv *` gắn với **thread hiện tại**; không lưu nó để truyền cho một thread OS khác. Nếu thread native do chính ứng dụng C/C++ tạo cần gọi vào JVM, nó phải được gắn qua Invocation API (ví dụ `AttachCurrentThread`) rồi tháo theo hợp đồng. Các JNI local references cũng có phạm vi thread/lời gọi tương ứng. Bộ nhớ của `GetStringUTFChars`, array elements và native buffer phải còn hợp lệ trong toàn bộ thời gian dùng.

JNI không tự làm hàm C/C++ trở nên thread-safe. Nếu nhiều Java threads cùng gọi `add` thì ví dụ không có shared mutable state; nếu native dùng biến global, bộ đệm dùng chung hoặc state thư viện, bạn phải tự đồng bộ theo yêu cầu.

## 12. Lỗi thường gặp và cách sửa

| Triệu chứng | Giải thích thường gặp | Kiểm tra |
| --- | --- | --- |
| `UnsatisfiedLinkError: no jnijourney in java.library.path` | JVM chưa tìm được thư viện tên logic `jnijourney` | Tên output `libjnijourney.so`/`.dylib`/`jnijourney.dll`, thư mục chạy, `-Djava.library.path=.`, tên case-sensitive trên OS liên quan |
| `UnsatisfiedLinkError: ... add(II)I` | Thư viện được nạp nhưng JVM không liên kết được đúng native method | Xem header `javac -h`, tên symbol export, `extern "C"`, overload, package; build lại native |
| `wrong ELF class`/lỗi architecture | JVM và thư viện không cùng kiến trúc hoặc định dạng | Kiểm tra x86/x64/ARM64, target compiler, 32/64-bit, OS |
| `jni.h: No such file or directory` | Thiếu include path của JDK | Xác nhận `JAVA_HOME/include/jni.h`, thêm header theo OS |
| `NoClassDefFoundError: Could not initialize class ...` | Lớp thất bại trong khởi tạo trước đó, có thể do `loadLibrary` ném lỗi | Xem **exception đầu tiên** trong stack trace và sửa lỗi gốc |
| Java String ra rác/chuỗi bị cắt | Ép `jstring` sang `char *`, sai Modified UTF-8 hoặc overflow | Dùng JNI API, kiểm tra size và release nguồn |
| JVM crash sau vài lần gọi | JNI reference/buffer hết lifetime; sai chữ ký; memory corruption | Kiểm tra `hs_err_pid...log`, ABI, local/global reference, ownership và build debug |
| Chỉ lỗi trong ứng dụng có nhiều class loaders | Thư viện JNI đã được gắn với class loader khác | Kiểm tra chiến lược load library theo class loader và bản thư viện được dùng |

Để kiểm tra symbol export, bạn có thể dùng công cụ phù hợp:

~~~bash
# Linux / ELF
nm -D libjnijourney.so

# macOS / Mach-O
nm -gU libjnijourney.dylib
~~~

Windows (Developer Command Prompt):

~~~bat
dumpbin /exports jnijourney.dll
~~~

Tìm các tên `Java_JniJourney_add` và `Java_JniJourney_greet` (trên một số nền tảng, tiện ích disassembly/symbol có thể hiển thị thêm tiền tố hoặc decoration đặc thù). Trên 32-bit x86 có thể có quy tắc name decoration và convention khác x64; luôn dùng **header JNI và compiler đúng target**.

**Quy trình chẩn đoán tối thiểu:** kiểm tra `java -version` và `javac -version` → xác nhận JDK header → biên dịch Java và header mới → kiểm tra file thư viện đúng kiến trúc → kiểm tra export → chạy lại với đường library đã cấu hình lúc khởi động → chỉ sau đó điều tra xử lý dữ liệu/exception.

## 13. Những sai lầm về luồng JNI cần tránh

1. **Nghĩ rằng `native` đã chứa triển khai.** Từ khóa chỉ khai báo hợp đồng; native library phải được build và liên kết.
2. **Nghĩ `System.loadLibrary` gọi luôn hàm JNI.** Nó chủ yếu nạp thư viện và kích hoạt các hook liên quan nếu có; `add` chỉ chạy khi Java gọi `add`.
3. **Tự viết prototype thay vì dùng `javac -h`.** Bạn dễ quên `JNIEnv *`, `jclass` hoặc sai tên symbol khi có package/overload.
4. **Dùng C `int/long` tùy ý thay kiểu JNI.** Hãy sử dụng `jint`, `jlong`, `jstring`; đặc biệt C `long` có thể 32 bit trên Windows x64.
5. **Xem `jstring` như một chuỗi C.** Nó là opaque reference, cần `GetStringUTFChars`/`ReleaseStringUTFChars` hoặc API tương ứng.
6. **Quên `extern "C"` với C++.** Name mangling gây khó liên kết JNI nếu export sai tên; luôn theo header được sinh.
7. **Giữ `JNIEnv *` hoặc local reference ở sai thread/ngoài lifetime.** Đây là nguồn lỗi khó tái hiện và có thể crash JVM.
8. **Trộn `System.load` và `System.loadLibrary`.** `System.load` thường dùng đường dẫn tuyệt đối tới file thư viện, còn `loadLibrary` nhận tên logic không có đường dẫn/đuôi.
9. **Xem JNI là FFM.** Foreign Function & Memory API có mô hình symbol/descriptor khác; `Linker.downcallHandle` cho C ABI thuần không tự thêm `JNIEnv *` và `jclass` như JNI entry point.
10. **Coi các lệnh build là độc lập với OS.** File extension, header phụ thuộc nền tảng và calling convention đều phải thống nhất với JVM.

## 14. Kiểm tra hiểu bài

1. Sau khi viết `public static native int add(int, int);`, còn những bước build/run nào trước khi chương trình Java gọi thành công?
2. Vì sao khi Java gọi `add(20, 22)`, hàm C lại nhận bốn tham số?
3. Nếu đổi Java class từ `JniJourney` sang `com.acme.JniJourney` mà không build lại native, lỗi nào thường xuất hiện?
4. Vì sao `GetStringUTFChars` phải đi với `ReleaseStringUTFChars` và tại sao `NewStringUTF` cần đúng Modified UTF-8?
5. Phân biệt lỗi **không thấy thư viện** và lỗi **không thấy native method symbol**.
6. Nếu dùng C++ thay C, điều gì giữ nguyên và điều gì thay đổi trong signature và cú pháp gọi API JNI?

**Gợi ý đáp án:** (1) `javac -h` → tạo C/C++ JNI implementation theo header → biên dịch thành thư viện đúng target → nạp library và gọi; (2) hai tham số ngầm `JNIEnv *` và `jclass`; (3) thường `UnsatisfiedLinkError` khi không tìm đúng symbol; (4) vùng byte phải được release, Modified UTF-8 không đồng nhất UTF-8 chuẩn; (5) một lỗi xảy ra lúc load library, một lỗi xảy ra lúc link phương thức; (6) vẫn là JNI types/symbol/hợp đồng, C++ dùng `env->...` và cần C linkage.

## Tài liệu chuẩn để đối chiếu

- [Oracle Java SE 17 — JNI Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): luồng gọi, tên hàm native, nạp/liên kết, `JNIEnv`, tham số ẩn và local/global references.
- [Oracle Java SE 17 — JNI Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): mapping các kiểu Java và JNI, `JNIEnv`, `jobject`, `jarray`.
- [Oracle Java SE 17 — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `GetStringUTFChars`, `ReleaseStringUTFChars`, `NewStringUTF`, `ThrowNew`, `RegisterNatives`.
- [Oracle Java SE 17 — JNI Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): quản lý thư viện và liên kết với class loader.
- [Oracle Java SE 17 — javac command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): tùy chọn `-h` để sinh native header.
