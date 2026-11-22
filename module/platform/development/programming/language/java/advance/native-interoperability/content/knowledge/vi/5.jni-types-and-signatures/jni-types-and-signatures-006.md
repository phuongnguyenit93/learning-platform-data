# Nạp chồng phương thức native trong JNI: khi nào dùng tên ký hiệu ngắn, khi nào dùng tên đầy đủ?

## 1. Mục tiêu bài học và vấn đề đặt ra

Trong Java, **nạp chồng phương thức** (*method overloading*) cho phép nhiều phương thức cùng tên, miễn là danh sách kiểu tham số của chúng khác nhau. Quy tắc này vẫn áp dụng cho phương thức đánh dấu `native`. Tuy nhiên, khi thân phương thức nằm trong một thư viện C/C++, JVM phải biết **ký hiệu native (exported symbol)** nào thực thi chính xác phiên bản đã được chọn.

Ví dụ:

```java
package demo.jni;

public final class NativeNames {
    private static native int scale(int n);
    private static native long scale(long n);
}
```

Hai phương thức đều tên `scale` nhưng nhận kiểu `int` và `long` khác nhau. Việc C có thể định nghĩa một hàm tên `scale` không đủ giúp JVM phân biệt hai overload. JNI sử dụng quy tắc mã hóa tên, tạo ra một **tên ngắn** và khi cần một **tên dài chứa kiểu tham số**.

Cần trả lời chính xác năm câu hỏi:

1. Java chọn overload nào khi gọi `scale(7)` hoặc `scale(7L)`?
2. JVM tìm tên ký hiệu **ngắn** và **dài** theo thứ tự nào?
3. Chuỗi đuôi `__I` hay `__J` được tạo từ đâu?
4. Nếu một phương thức `native` trùng tên với một phương thức Java thông thường, có bắt buộc dùng tên dài không?
5. Làm sao dùng `javac -h` để tránh tự đoán tên và chữ ký JNI?

**Phân biệt hai giai đoạn:** chọn overload là quy tắc của **ngôn ngữ Java và bytecode**; tìm hàm C/C++ thực hiện overload đó là **liên kết JNI**. Chúng liên quan nhưng không phải cùng một thao tác.

## 2. Overload trong Java và descriptor của JVM

Với hai khai báo:

```java
static native int scale(int n);
static native long scale(long n);
```

- `scale(7)` chọn overload nhận `int` vì literal `7` có kiểu `int`.
- `scale(7L)` chọn overload nhận `long` vì hậu tố `L` làm literal có kiểu `long`.
- `scale((long) 7)` cũng chọn overload nhận `long`.
- Java giải quyết overload tại **thời điểm biên dịch** theo các quy tắc áp dụng được, độ ưu tiên chuyển đổi kiểu, varargs, generic, v.v. Bytecode của lời gọi tham chiếu một phương thức có tên và *descriptor* xác định; JNI không tự suy đoán overload bằng cách đọc giá trị lúc chạy.

**Method descriptor** trong định dạng JVM có dạng:

```text
(kiểu_tham_số_1 kiểu_tham_số_2 ...)kiểu_trả_về
```

Không có dấu phẩy hay khoảng trắng giữa các mã kiểu. Một số mã cơ bản:

| Kiểu Java | Mã JVM |
| --- | --- |
| `byte` | `B` |
| `char` | `C` |
| `double` | `D` |
| `float` | `F` |
| `int` | `I` |
| `long` | `J` |
| `short` | `S` |
| `boolean` | `Z` |
| `void` (chỉ làm kiểu trả về) | `V` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |

Đối với hai `scale` ở trên:

| Khai báo | Full JVM method descriptor | Phần descriptor **tham số** |
| --- | --- | --- |
| `int scale(int n)` | `(I)I` | `I` |
| `long scale(long n)` | `(J)J` | `J` |

**Điểm quan trọng:** tên dài của JNI chỉ mã hóa **danh sách tham số** (phần nằm trong cặp ngoặc tròn), **không mã hóa kiểu trả về**. Dù method descriptor đầy đủ có kiểu trả về, kiểu trả về không nằm trong suffix tên hàm JNI. Điều này phù hợp với Java: không thể tạo hai overload khác nhau **chỉ nhờ kiểu trả về**.

## 3. JNI tạo tên ngắn và tên dài như thế nào?

Khi dùng **liên kết theo tên symbol (name-based JNI linking)**, dạng tên thường gặp là:

```text
Tên ngắn:
Java_<tên_lớp_đã_escape>_<tên_phương_thức_đã_escape>

Tên dài:
Java_<tên_lớp_đã_escape>_<tên_phương_thức_đã_escape>__<tham_số_đã_escape>
                                                                ^^
                                                        hai dấu gạch dưới
```

Với `demo.jni.NativeNames`, tên nội bộ lớp là `demo/jni/NativeNames`. Ký tự slash `/` khi mã hóa JNI trở thành dấu gạch dưới `_`, nên tiền tố là:

```text
Java_demo_jni_NativeNames_
```

Các ký hiệu tương ứng:

| Phương thức Java | Tên ngắn (không có tham số) | Tên dài (có tham số) |
| --- | --- | --- |
| `int scale(int)` | `Java_demo_jni_NativeNames_scale` | `Java_demo_jni_NativeNames_scale__I` |
| `long scale(long)` | `Java_demo_jni_NativeNames_scale` | `Java_demo_jni_NativeNames_scale__J` |
| `int sum(int,int)` | `Java_demo_jni_NativeNames_sum` | `Java_demo_jni_NativeNames_sum__II` |
| `int parse(String)` | `Java_demo_jni_NativeNames_parse` | `Java_demo_jni_NativeNames_parse__Ljava_lang_String_2` |

**Tên ngắn của hai `scale` giống hệt nhau.** Nếu chúng cùng là phương thức `native`, ta cần hai ký hiệu tên dài khác nhau để cài đúng cả hai.

Ở ký hiệu tên dài, chuỗi `__I` được phân tích là `__` (dấu phân cách tên dài) + `I` (tham số Java `int`); tương tự `__J` là overload có tham số `long`. `__II` có nghĩa **hai tham số `int`**, hoàn toàn không liên quan đến kiểu trả về.

### Trình tự JVM tìm ký hiệu

JNI Specification nêu rõ thứ tự tìm theo tên khi JVM liên kết lời gọi native:

1. Thử tìm **tên ngắn**, không có hậu tố chữ ký.
2. Nếu không tìm thấy tên ngắn, mới thử **tên dài** chứa chữ ký tham số.

```text
Java gọi scale(7)
       │ overload đã chọn: scale(int)
       ▼
JVM thử Java_demo_jni_NativeNames_scale
       │ nếu không có
       ▼
JVM thử Java_demo_jni_NativeNames_scale__I
       │ nếu có
       ▼
Gọi đúng hàm C nhận jint
```

Vì **tên ngắn được thử trước**, đừng xuất một ký hiệu tên ngắn dùng chung cho các overload `native` có ABI khác nhau. Chẳng hạn nếu vô tình xuất `Java_demo_jni_NativeNames_scale` cho cả hai, JVM có thể liên kết một overload vào một hàm C không nhận đúng kiểu tham số: hành vi không đáng tin cậy, từ kết quả sai đến lỗi native/crash. Khi có nhiều phương thức `native` cùng tên, hãy tạo **tên dài riêng cho từng overload** bằng header sinh tự động.

Cũng cần tách biệt: tên file thư viện trong `System.loadLibrary("native_names")` là **tên thư viện chứa các hàm**, còn `Java_demo_jni_NativeNames_scale__I` là **tên hàm được export trong thư viện**. Hai tên này giải quyết hai vấn đề khác nhau.

## 4. Trường hợp đặc biệt: overload chỉ có một phương thức native

Xét lớp có:

```java
private static native int size(int n);
private static int size(String text) {
    return text.length();
}
```

Ở cấp Java, đây vẫn là **hai overload của `size`**. Nhưng chỉ một overload có thân mã C; `size(String)` được cài hoàn toàn bằng Java.

Trong trường hợp này, tên ngắn `Java_demo_jni_NativeNames_size` **đủ để liên kết phương thức native**. Không bắt buộc dùng `Java_demo_jni_NativeNames_size__I`. Theo đặc tả JNI, tên dài cần thiết khi **hai hoặc nhiều phương thức `native` trong cùng lớp có cùng tên**; overload Java thông thường không tạo ra hàm JNI để gây mơ hồ.

So sánh:

| Nhóm khai báo | Ký hiệu native khuyến nghị |
| --- | --- |
| Chỉ `native void ping()` | `Java_demo_jni_NativeNames_ping` |
| `native int size(int)` + Java `int size(String)` | `Java_demo_jni_NativeNames_size` |
| `native int scale(int)` + `native long scale(long)` | `Java_demo_jni_NativeNames_scale__I` và `Java_demo_jni_NativeNames_scale__J` |

**Quy tắc thực hành:** nếu muốn biết chính xác compiler kỳ vọng gì, dùng `javac -h` và lấy tên/prototype từ header; không cần tự ước lượng.

## 5. Quy tắc escape/mangling khi tên hoặc tham số có ký tự đặc biệt

JNI không ghép thẳng tên Java có dấu chấm, underscore hay kiểu đối tượng vào symbol C. Trong JNI Specification:

| Ký tự gốc trong tên nội bộ / descriptor | Kết quả escape JNI |
| --- | --- |
| Ký tự ASCII `A–Z`, `a–z`, `0–9` | Giữ nguyên |
| `/` (phân cách package trong internal name) | `_` |
| `_` (underscore thực sự trong tên Java) | `_1` |
| `;` (kết thúc kiểu object trong descriptor) | `_2` |
| `[` (bắt đầu kiểu mảng) | `_3` |
| UTF-16 code unit khác | `_0xxxx`, bốn chữ số hex viết thường |

Ví dụ minh họa:

- Class `com.example.My_Class` có tên nội bộ `com/example/My_Class`: phần class trong symbol là `com_example_My_1Class`, vì underscore gốc phải được escape `_1`.
- Phương thức Java `run_task()`: phần tên phương thức là `run_1task`.
- Kiểu `String`: descriptor `Ljava/lang/String;` → chuỗi escape `Ljava_lang_String_2`.
- Kiểu `int[]`: descriptor `[I` → `_3I`.
- Kiểu `String[]`: descriptor `[Ljava/lang/String;` → `_3Ljava_lang_String_2`.

Từ đó, nếu lớp `demo.jni.NativeNames` có hai phương thức `native void process(int[])` và `native void process(String[])`, tên dài sẽ lần lượt là:

```text
Java_demo_jni_NativeNames_process___3I
Java_demo_jni_NativeNames_process___3Ljava_lang_String_2
```

Trong `process___3I` có **ba dấu gạch dưới liên tiếp** sau tên phương thức: `__` của dạng tên dài, rồi `_3` để biểu diễn dấu mở mảng `[`. Đây không phải lỗi gõ.

Kiểu trả về `void` trong ví dụ không tạo thêm `V` ở cuối symbol. Nhưng descriptor đầy đủ để Java/JVM nhận diện phương thức vẫn lần lượt là `([I)V` và `([Ljava/lang/String;)V`.

Với ký tự Unicode, JNI mã hóa theo **UTF-16 code unit**; ký tự ngoài BMP dùng cặp surrogate sẽ được escape thành hai phần. Vì vậy càng không nên tự gõ symbol dài khi có package, nested class, tên Unicode hoặc kiểu mảng phức tạp. `javac -h` loại bỏ phần lớn sai sót đặt tên thủ công.

## 6. Ví dụ JNI hoàn chỉnh có thể xây dựng bằng Java 17+ và C

Ví dụ dưới đây đồng thời chứng minh:

- Hai overload `native` của `scale` phải có **hai tên dài** riêng.
- Một phương thức `native size(int)` bị overload bởi `size(String)` **viết bằng Java** có thể dùng **tên ngắn**.
- Java chọn overload từ kiểu đối số; JNI tìm đúng hàm triển khai C theo tên symbol.
- Tệp `.h` do `javac -h` tạo là nguồn chuẩn để lấy prototype.

### Bước 1 — Tạo tệp `src/demo/jni/NativeNames.java`

```java
package demo.jni;

public final class NativeNames {
    static {
        System.loadLibrary("native_names");
    }

    private static native int scale(int n);
    private static native long scale(long n);

    private static native int size(int n);

    private static int size(String text) {
        return text.length();
    }

    public static void main(String[] args) {
        System.out.println("int: " + scale(7));
        System.out.println("long: " + scale(7L));
        System.out.println("native size: " + size(5));
        System.out.println("java size: " + size("abc"));
    }
}
```

Vì `7` là `int` và `7L` là `long`, compiler liên kết hai lời gọi vào hai descriptor khác nhau. Vì đối số `"abc"` là `String`, lời gọi `size("abc")` **không chuyển vào native code**.

### Bước 2 — Biên dịch Java và sinh JNI header

Từ thư mục gốc dự án, tạo các thư mục đầu ra (ví dụ Linux/macOS shell):

```bash
mkdir -p build/classes build/include build/native

javac -h build/include \
  -d build/classes \
  src/demo/jni/NativeNames.java
```

- `-d build/classes` là nơi lưu class file (`demo/jni/NativeNames.class`).
- `-h build/include` yêu cầu `javac` sinh header JNI cho các phương thức `native`.
- Header có tên `build/include/demo_jni_NativeNames.h` (đây là cách đặt tên cho class không modular trong ví dụ).
- `javac` chưa tạo thư viện C hay native executable; nó tạo bytecode và C header.

Trong header, phần prototype có ý nghĩa như sau (lược bớt các comment/header guards sinh tự động):

```c
#include <jni.h>

JNIEXPORT jint JNICALL Java_demo_jni_NativeNames_scale__I
  (JNIEnv *, jclass, jint);

JNIEXPORT jlong JNICALL Java_demo_jni_NativeNames_scale__J
  (JNIEnv *, jclass, jlong);

JNIEXPORT jint JNICALL Java_demo_jni_NativeNames_size
  (JNIEnv *, jclass, jint);
```

Quan sát quan trọng: `scale(int)` mang suffix `__I`, `scale(long)` mang suffix `__J`, còn `size(int)` chỉ có ký hiệu **ngắn**. Không có prototype JNI cho `size(String)` vì nó được cài bằng Java.

**Đã kiểm tra quy tắc này bằng `javac -h` trên JDK 24:** header tạo ra đúng ba prototype trên. Trên JDK 17+ với cùng khai báo, dùng lệnh `javac -h` để kiểm tra bản JDK thực tế của bạn.

### Bước 3 — Cài đặt C trong `NativeNames.c`

```c
#include <jni.h>
#include "demo_jni_NativeNames.h"

JNIEXPORT jint JNICALL Java_demo_jni_NativeNames_scale__I(
        JNIEnv *env, jclass clazz, jint n) {
    (void) env;
    (void) clazz;
    return n * 2;
}

JNIEXPORT jlong JNICALL Java_demo_jni_NativeNames_scale__J(
        JNIEnv *env, jclass clazz, jlong n) {
    (void) env;
    (void) clazz;
    return n * 3;
}

JNIEXPORT jint JNICALL Java_demo_jni_NativeNames_size(
        JNIEnv *env, jclass clazz, jint n) {
    (void) env;
    (void) clazz;
    return n + 1;
}
```

Hai điểm cần đối chiếu với header:

1. `JNIEXPORT` đánh dấu hàm được xuất khỏi thư viện theo cách phù hợp compiler/platform; `JNICALL` dùng calling convention do JNI yêu cầu. Giữ nguyên các macro này, nhất là khi chuyển nền tảng.
2. Hai tham số đầu là `JNIEnv *env` và `jclass clazz` vì cả ba phương thức Java đều `static native`. Với phương thức **instance native** (không có `static`), tham số thứ hai là `jobject obj` tương ứng đối tượng `this`. Sau đó mới đến tham số Java đã đổi sang kiểu JNI (`int → jint`, `long → jlong`).

Nếu viết phần native bằng **C++**, cần bảo đảm hàm JNI có C linkage (thường dùng `extern "C"`); nếu để compiler C++ tự mangle symbol theo quy tắc C++, JVM có thể không tìm được ký hiệu `Java_...` dù tên hàm trong source nhìn có vẻ đúng. Header sinh từ `javac -h` đã đặt prototype trong khối `extern "C"` khi biên dịch C++.

### Bước 4 — Tạo thư viện trên Linux

Yêu cầu: JDK 17+ và GCC, biến môi trường `JAVA_HOME` trỏ vào thư mục JDK chứa `include/jni.h`.

```bash
gcc -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  -o build/native/libnative_names.so \
  NativeNames.c
```

Nạp và chạy chương trình Java:

```bash
java -Djava.library.path=build/native \
  -cp build/classes \
  demo.jni.NativeNames
```

**Stdout chính xác khi biên dịch, nạp và liên kết thành công:**

```text
int: 14
long: 21
native size: 6
java size: 3
```

Giải thích:

- `scale(7)` đi tới `Java_demo_jni_NativeNames_scale__I` và tính `7 * 2 = 14`.
- `scale(7L)` đi tới `Java_demo_jni_NativeNames_scale__J` và tính `7 * 3 = 21`.
- `size(5)` dùng symbol ngắn `Java_demo_jni_NativeNames_size`, trả `5 + 1 = 6`.
- `size("abc")` thực thi thân Java, trả `3` mà không gọi JNI.

### Biên dịch trên macOS hoặc Windows

Mã Java/C ở trên không phụ thuộc Linux; chỉ lệnh build thư viện và tên file khác nhau.

**macOS** (JDK và Apple Clang; sau khi tạo `build/classes`, `build/include`, `build/native` và chạy `javac -h` như trên):

```bash
clang -O2 -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include \
  -o build/native/libnative_names.dylib \
  NativeNames.c

java -Djava.library.path=build/native \
  -cp build/classes \
  demo.jni.NativeNames
```

**Windows** (JDK, Visual Studio C compiler; chạy từ *Developer Command Prompt* đã thiết lập `cl` và `JAVA_HOME`):

```bat
mkdir build\classes
mkdir build\include
mkdir build\native

javac -h build\include -d build\classes src\demo\jni\NativeNames.java

cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /I"build\include" NativeNames.c /Febuild\native\native_names.dll

java -Djava.library.path=build\native -cp build\classes demo.jni.NativeNames
```

Lệnh `mkdir` có thể báo thư mục đã tồn tại khi chạy lại; điều đó không ảnh hưởng đến nội dung source. Trên cả ba nền tảng, phải dùng JDK và compiler native có **kiến trúc phù hợp nhau** (ví dụ x64 với x64). `System.loadLibrary("native_names")` tự ánh xạ tên logic thành tên thư viện theo nền tảng.

Lưu ý phân biệt **stdout** và **stderr**: JDK mới có thể in cảnh báo chính sách native access trên stderr. Nếu runtime yêu cầu bật native access cho chương trình ở classpath, sử dụng tùy chọn phù hợp phiên bản JDK, chẳng hạn `--enable-native-access=ALL-UNNAMED` khi chạy trên bản JDK hỗ trợ; cảnh báo không thuộc bốn dòng stdout ở trên.

## 7. Những tên dài có tham số object và array

Trong dự án thực tế, overload thường chứa `String`, các lớp trong package, hoặc mảng. Lấy ví dụ độc lập về tên ký hiệu (không phải chương trình hoàn chỉnh):

```java
package demo.jni;

public class ReferenceOverloads {
    public native int find(int id, String text);
    public native int find(int id, Object value);
    public native void accept(int[] items);
    public native void accept(String[] items);
}
```

Phân tích các descriptor và tên symbol:

| Khai báo | Descriptor đầy đủ | Chỉ tham số để mã hóa | Tên ký hiệu dài |
| --- | --- | --- | --- |
| `find(int, String)` | `(ILjava/lang/String;)I` | `ILjava/lang/String;` | `Java_demo_jni_ReferenceOverloads_find__ILjava_lang_String_2` |
| `find(int, Object)` | `(ILjava/lang/Object;)I` | `ILjava/lang/Object;` | `Java_demo_jni_ReferenceOverloads_find__ILjava_lang_Object_2` |
| `accept(int[])` | `([I)V` | `[I` | `Java_demo_jni_ReferenceOverloads_accept___3I` |
| `accept(String[])` | `([Ljava/lang/String;)V` | `[Ljava/lang/String;` | `Java_demo_jni_ReferenceOverloads_accept___3Ljava_lang_String_2` |

Cả bốn phương thức trong bảng đều là *instance native*, nên prototype C nhận `jobject` làm tham số thứ hai (khác với `jclass` trong ví dụ `static`).

Đừng nhầm **JNI symbol suffix** với **full JVM descriptor**:

- JNI symbol `...find__ILjava_lang_String_2` dùng **tham số đã escape**, không gồm cặp `()` và không gồm kiểu trả về `I`.
- JNI API như `GetMethodID` hoặc `RegisterNatives` nhận **full descriptor**, ví dụ `"(ILjava/lang/String;)I"`, có dấu ngoặc và kiểu trả về.
- Các chuỗi kiểu như `Ljava/lang/String;` sử dụng **slash `/`**, không sử dụng dấu chấm như tên Java source.

## 8. Lựa chọn khác: đăng ký ánh xạ bằng RegisterNatives

JNI còn cung cấp API `RegisterNatives`. Thay vì JVM tìm C symbol bắt đầu bằng `Java_...`, native code có thể **đăng ký tường minh** từng phương thức Java theo **tên và descriptor đầy đủ**, rồi gắn với con trỏ hàm C tương ứng.

Minh họa một phần cấu hình đăng ký (đây chỉ là trích đoạn, chưa phải chương trình tự chạy; cần khai báo các hàm C, lấy `jclass`, gọi đăng ký tại thời điểm thích hợp và xử lý lỗi):

```c
static JNINativeMethod methods[] = {
    {"scale", "(I)I", (void *) nativeScaleInt},
    {"scale", "(J)J", (void *) nativeScaleLong}
};

/* env: JNIEnv*, targetClass: jclass đã tìm được */
jint result = (*env)->RegisterNatives(
    env, targetClass, methods, 2);
```

Ở đây:

- `"scale"` là **tên phương thức Java**, không phải C symbol `Java_demo_jni_NativeNames_scale__I`.
- `"(I)I"` và `"(J)J"` là **descriptor đầy đủ**, có kiểu trả về, giúp đăng ký đúng overload.
- `nativeScaleInt` và `nativeScaleLong` có thể mang tên C tự chọn, miễn con trỏ trỏ tới hàm có **ABI/signature JNI đúng**.
- Phải kiểm tra giá trị trả về và exception. Đăng ký sai kiểu/con trỏ cũng có thể gây lỗi hoặc crash. `RegisterNatives` là cơ chế khác, không phải bằng chứng quy tắc short/long symbol đã bị thay đổi.

Dùng `javac -h` và liên kết theo tên phù hợp với ví dụ đơn giản; đăng ký tường minh có ích khi framework/native runtime muốn quản lý bảng ánh xạ phương thức. Với Java 17+ thông thường, cả hai là kỹ thuật JNI cần được bảo trì cẩn thận.

## 9. Chẩn đoán lỗi nạp chồng phương thức native

### 9.1. Thư viện chưa được tải ≠ symbol không khớp

`System.loadLibrary("native_names")` có thể thất bại vì **không tìm thấy thư viện native chính hoặc dependency của nó** (ví dụ `libnative_names.so`, `native_names.dll`), khi đó lỗi nằm ở bước nạp thư viện.

Ngược lại, nếu thư viện tải thành công nhưng JVM **không tìm thấy hàm JNI tương ứng** khi gọi `scale(int)`, Java có thể ném:

```text
java.lang.UnsatisfiedLinkError: 'int demo.jni.NativeNames.scale(int)'
```

Thông điệp thực tế phụ thuộc JDK và runtime; mẫu trên mô tả **liên kết phương thức** bị thiếu, không khẳng định toàn bộ stack trace. Dùng tên class + tên method + descriptor để xác định đúng overload thất bại.

### 9.2. Kiểm tra bằng `javac -h` và công cụ xem symbol

1. Sinh lại header với đúng phiên bản Java source hiện tại: `javac -h build/include -d build/classes ...`.
2. Đối chiếu tên `Java_...` và toàn bộ prototype C với header, gồm `JNIEXPORT`, `JNICALL`, `JNIEnv*`, `jclass/jobject` và kiểu JNI.
3. Xem các symbol xuất thực tế từ thư viện:

```bash
# Linux (ELF): xem symbol exported, kiểm tra tên đầy đủ
nm -D --defined-only build/native/libnative_names.so | grep Java_demo_jni_NativeNames

# Linux: cũng có thể dùng readelf
readelf -Ws build/native/libnative_names.so | grep Java_demo_jni_NativeNames
```

```bash
# macOS (Mach-O): symbol có thể hiển thị thêm dấu '_' ở đầu
nm -gU build/native/libnative_names.dylib | grep Java_demo_jni_NativeNames
```

```bat
rem Windows: trong Visual Studio Developer Command Prompt
dumpbin /EXPORTS build\native\native_names.dll
```

4. Nếu thấy `Java_demo_jni_NativeNames_scale` mà không có `...scale__I` và `...scale__J`, không nên coi đó là bản cài đặt hợp lệ cho **hai overload native**.
5. Nếu thư viện được viết bằng C++, kiểm tra có export **C linkage** hay không. Nếu thay đổi package, tên class, tên method hoặc kiểu tham số, **sinh lại header và build lại thư viện**.

### 9.3. Lỗi và hướng kiểm tra

| Hiện tượng | Nguyên nhân khả dĩ | Kiểm tra/sửa |
| --- | --- | --- |
| `no native_names in java.library.path` | JVM chưa tìm được thư viện chính | Tên logic, file `.so`/`.dll`/`.dylib`, `java.library.path` |
| Lỗi `scale(int)` nhưng `scale(long)` chạy | Thiếu hoặc sai symbol `__I` | So header và exported symbols; build lại hàm cho `int` |
| Lỗi `scale(long)` nhưng `scale(int)` chạy | Thiếu hoặc sai symbol `__J` | So header và exported symbols; build lại hàm cho `long` |
| Có symbol nhưng sai kiểu tham số hoặc gọi crash | C function prototype/ABI sai, hoặc symbol ngắn bị dùng chung | Dùng nguyên mẫu JNI từ header, bỏ tên ngắn mơ hồ |
| Symbol có tên dài lạ như `___3I` | Mảng được escape thành `_3I` | Đọc method descriptor `([I)...` và quy tắc escape |
| Đổi tên package/method rồi gọi không được | Symbol C vẫn mang tên class/method cũ | Sinh header mới, cập nhật mã C và biên dịch lại |
| C++ export tên kiểu `_Z...` | C++ compiler mangling thay vì JNI C linkage | Khai báo với `extern "C"` và macro JNI |
| Tên symbol đúng nhưng vẫn tải lỗi | Thiếu thư viện phụ thuộc, sai OS/architecture hoặc quyền native access | Kiểm tra loader, platform và chính sách JDK |

**Đặc biệt:** không thử sửa lỗi `scale(int)` bằng cách đổi tên Java method cho hết overload nếu overload là API cần thiết. Quy tắc tên dài đã được thiết kế để giải quyết chính xác trường hợp này.

## 10. Bài tập tự kiểm tra

**Bài 1.** Với hai phương thức `native int combine(int, int)` và `native int combine(int, long)` trong lớp `demo.jni.NativeNames`, hãy cho biết tên dài.

Đáp án: tham số lần lượt có descriptor `II` và `IJ`, nên symbol là:

```text
Java_demo_jni_NativeNames_combine__II
Java_demo_jni_NativeNames_combine__IJ
```

**Bài 2.** Một lớp có `native int count(int[])` và `native int count(String[])`. Vì sao có ba dấu gạch dưới ngay trước `3`?

Đáp án: `__` phân cách phần tên dài, còn `_3` là cách escape ký tự `[`. Tên dài tương ứng là `...count___3I` và `...count___3Ljava_lang_String_2`.

**Bài 3.** Lớp có `native double calc(double)` và `int calc(String)` (thân viết bằng Java). Có bắt buộc xuất `Java_..._calc__D` không?

Đáp án: **Không**. Chỉ có một overload là `native`, nên tên ngắn `Java_..._calc` đủ; chỉ cần kiểu/prototype C khớp phương thức `calc(double)`.

**Bài 4.** Thư viện export cả `Java_demo_jni_NativeNames_scale` (tên ngắn) và `Java_demo_jni_NativeNames_scale__I`/`__J` (tên dài). Có thể khẳng định JVM luôn chọn đúng tên dài không?

Đáp án: **Không**. Theo JNI Specification, JVM **thử tên ngắn trước**, nên việc vô tình xuất tên ngắn gây rủi ro. Khi có nhiều phương thức `native` cùng tên, nên chỉ xuất các tên dài đúng overload.

**Bài 5.** `RegisterNatives` phân biệt overload bằng chuỗi `"__I"` và `"__J"` hay bằng full descriptor?

Đáp án: Bằng **tên phương thức cùng full descriptor**, ví dụ `"scale" + "(I)I"` và `"scale" + "(J)J"`. Quy tắc tạo symbol `Java_...__I` không cần được dùng nếu đã đăng ký hàm tường minh.

## 11. Ghi nhớ để áp dụng

- Nạp chồng do **Java compiler** chọn theo kiểu tham số; **JNI linker** cần tìm hàm C/C++ của overload đã chọn.
- **Tên ngắn**: `Java_<class>_<method>`; **tên dài**: thêm `__<escaped parameter descriptor>`.
- JVM thử **tên ngắn trước**, rồi mới đến **tên dài** khi tìm symbol theo quy tắc JNI.
- Nếu **hai hoặc nhiều overload cùng là `native`**, tạo **tên dài riêng**; nếu chỉ một overload `native`, tên ngắn là đủ dù có các overload Java thường.
- Kiểu trả về **không nằm trong suffix JNI**, nhưng nằm trong descriptor đầy đủ của `GetMethodID`/`RegisterNatives`.
- Dấu `_`, `/`, `;`, `[` và ký tự Unicode có quy tắc escape riêng; **`javac -h` là cách an toàn nhất** để lấy tên hàm và prototype chính xác.
- Lỗi không tìm được **thư viện** và lỗi không tìm được **phương thức JNI** phải được chẩn đoán riêng.

## Tài liệu tham khảo chính thức

- [JNI Specification (Java 17), Design Overview: Resolving Native Method Names](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html#resolving-native-method-names)
- [JNI Specification (Java 24), Design Overview: short/long symbol resolution, escaping và native access](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/design.html)
- [Java Virtual Machine Specification, Method Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.3)
- [`javac`, tùy chọn tạo native headers `-h`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [JNI Functions: RegisterNatives](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#registering-native-methods)
