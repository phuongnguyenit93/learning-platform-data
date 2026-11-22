# Tên nhị phân, dấu gạch chéo và quy tắc tên hàm JNI

## 1. Vì sao một class Java có nhiều cách viết tên?

Khi làm việc với Java Native Interface (JNI), cùng một class có thể xuất hiện dưới nhiều biểu diễn:

- **Tên kiểu Java ở mã nguồn**: `edu.demo.jni.NativeNames`.
- **Tên nhị phân (binary name)** của class: `edu.demo.jni.NativeNames`; với lớp thành viên, binary name thường có dấu `$`.
- **Tên nội bộ (internal form)** trong JVM: `edu/demo/jni/NativeNames`, dùng dấu gạch chéo xuôi `/` thay cho dấu chấm ngăn cách package.
- **Descriptor (mô tả kiểu)**: `Ledu/demo/jni/NativeNames;`; descriptor phương thức có thêm danh sách tham số và kiểu trả về.
- **Tên hàm C export theo quy tắc JNI**: ví dụ `Java_edu_demo_jni_NativeNames_sum_1value`; đây là *symbol* sau khi mã hóa (mangling), không phải tên class hay đường dẫn.
- **Tên thư viện native**: chẳng hạn `libnative_names.so`, `native_names.dll` hoặc `libnative_names.dylib`; tên tệp này thuộc cơ chế nạp thư viện của hệ điều hành.

Những biểu diễn trên liên quan với nhau nhưng **không thể hoán đổi tùy ý**. Dấu `/` trong `edu/demo/jni/NativeNames` là quy ước tên nội bộ JVM, không phải yêu cầu chọn Linux hay macOS. Tên hàm JNI dùng dấu `_` theo **bảng escape chính xác**, nên không thể chỉ thay mọi dấu chấm bằng dấu gạch dưới.

Mục tiêu của bài: phân biệt binary/internal name, hiểu dấu `/` trong descriptor và JNI API, tự suy ra tên JNI dạng ngắn/dài, giải thích quy tắc `_1`/`_2`/`_3`/`_0xxxx`, và kiểm chứng bằng `javac -h` với Java 17+.

## 2. Tên ở mã nguồn, binary name và internal form

### 2.1. Class top-level có package

Với khai báo:

~~~java
package edu.demo.jni;

public class NativeNames {
}
~~~

ta có:

| Bối cảnh | Chuỗi tên | Ý nghĩa |
|---|---|---|
| Mã Java / `Class.getName()` | `edu.demo.jni.NativeNames` | Tên nhị phân của class thông thường, dấu chấm phân tách package. |
| JVM internal form | `edu/demo/jni/NativeNames` | Dấu `/` phân tách các thành phần package/class ở cấu trúc class file. |
| Field descriptor của kiểu object | `Ledu/demo/jni/NativeNames;` | `L` mở đầu một kiểu tham chiếu class/interface; `;` kết thúc. |
| Tên tệp nguồn theo layout phổ biến | `src/edu/demo/jni/NativeNames.java` | Đường dẫn filesystem, chịu cú pháp shell và OS. |
| Class file theo layout phổ biến | `build/classes/edu/demo/jni/NativeNames.class` | Tệp build; trên Windows separator filesystem có thể là `\`. |

Lưu ý: package trong Java được viết bằng dấu chấm. Khi đổi sang internal form, các dấu chấm **phân tách package** được thay bằng `/`. Đây là quy tắc của JVM/JNI, **không phải** phép đổi separator filesystem tùy nền tảng. Trong literal Java, viết `"edu/demo/jni/NativeNames"` khi một API JNI yêu cầu internal name, kể cả khi chạy trên Windows.

Tên nhị phân là tên của **class**; “binary” ở đây không có nghĩa `.dll` hoặc `.so`. Đừng nhầm nó với *binary filename* hay với tên thư viện native.

### 2.2. Lớp thành viên, nested class và ký tự `$`

Xét mã sau (minh họa về tên, chưa liên quan đến native method):

~~~java
package edu.demo.jni;

public class Outer {
    public static class Inner {
    }
}
~~~

Tên của `Inner`:

| Biểu diễn | Giá trị |
|---|---|
| Cách viết trong Java source | `edu.demo.jni.Outer.Inner` |
| Binary name / `Outer.Inner.class.getName()` | `edu.demo.jni.Outer$Inner` |
| Internal form | `edu/demo/jni/Outer$Inner` |
| Descriptor | `Ledu/demo/jni/Outer$Inner;` |
| Phần class sau JNI escaping | `edu_demo_jni_Outer_00024Inner` |

Điểm dễ sai: Java source dùng `Outer.Inner`, nhưng **binary name của member class** có `Outer$Inner`. Khi mã hóa tên hàm JNI, ký tự `$` (U+0024) không thể giữ nguyên như chữ/số ASCII, vì vậy thành `_00024`. Không tự đổi `$` thành `_`. Với local/anonymous class, binary name có thể có các phần đánh số; nên luôn lấy tên từ class thực tế thay vì tự đoán từ source.

### 2.3. Tên của mảng không giống class thông thường

JVM mô tả array bằng dấu `[` ở đầu:

| Kiểu Java | JVM type descriptor |
|---|---|
| `int[]` | `[I` |
| `long[][]` | `[[J` |
| `String[]` | `[Ljava/lang/String;` |
| `edu.demo.jni.NativeNames[][]` | `[[Ledu/demo/jni/NativeNames;` |

Có một khác biệt nhỏ nhưng quan trọng: `String[].class.getName()` trả về chuỗi kiểu tên nhị phân `[Ljava.lang.String;` với **dấu chấm** trong phần tên class; descriptor JVM và đối số `FindClass` dành cho mảng object lại sử dụng **dấu slash**, chẳng hạn `[Ljava/lang/String;`. Đừng nhầm đầu ra của `Class.getName()` cho array với bytecode descriptor phải viết cho JNI.

## 3. Dấu `/` trong chữ ký JVM và lời gọi JNI

### 3.1. Quy tắc field descriptor

Các ký tự mô tả kiểu JVM cơ bản:

| Java type | Descriptor | JNI C type tương ứng (khi dùng làm tham số/giá trị) |
|---|---|---|
| `boolean` | `Z` | `jboolean` |
| `byte` | `B` | `jbyte` |
| `char` | `C` | `jchar` |
| `short` | `S` | `jshort` |
| `int` | `I` | `jint` |
| `long` | `J` | `jlong` |
| `float` | `F` | `jfloat` |
| `double` | `D` | `jdouble` |
| `void` | `V` | `void` (chỉ vị trí kiểu trả về phương thức) |
| `java.lang.String` | `Ljava/lang/String;` | `jstring` |
| `int[]` | `[I` | `jintArray` |
| `String[]` | `[Ljava/lang/String;` | `jobjectArray` |

Quy tắc hình thành descriptor: một class/interface có dạng `L<tên-nội-bộ>;`; một chiều mảng thêm một dấu `[` trước descriptor của phần tử. Ví dụ Java `String[][]` có descriptor `[[Ljava/lang/String;`. Slash `/` là thành phần tên nội bộ; `L`, `;` và `[` là cú pháp descriptor, không phải ký tự trang trí.

### 3.2. Method descriptor chứa cả đầu vào và đầu ra

Ví dụ khai báo:

~~~java
static native long calculate(int count, String[] names);
~~~

Method descriptor là:

~~~text
(I[Ljava/lang/String;)J
~~~

Phân rã:

- `(` và `)` bao quanh các **descriptor tham số theo thứ tự**.
- `I` là `int count`.
- `[Ljava/lang/String;` là `String[] names`.
- `J` sau dấu `)` là kiểu trả về `long`.

**Tách hai khái niệm:** descriptor JVM đầy đủ **có kiểu trả về**, còn hậu tố của *tên JNI dạng dài* chỉ lấy **phần descriptor của các tham số**, bỏ `(`, `)` và phần kiểu trả về. Do đó ví dụ trên dùng chuỗi tham số `I[Ljava/lang/String;` để mã hóa hậu tố JNI, không dùng nguyên chuỗi `(I[Ljava/lang/String;)J`.

Generics phần lớn bị **type erasure** trong descriptor JVM thông thường: ví dụ một tham số `java.util.List<String>` có descriptor đối tượng `Ljava/util/List;`, không nhúng `<String>` vào JNI method descriptor.

### 3.3. API JNI nào dùng internal form?

Phía mã C (đoạn dưới là **minh họa trong một hàm JNI**; cần có `JNIEnv *env` hợp lệ):

~~~c
jclass cls = (*env)->FindClass(env, "edu/demo/jni/NativeNames");
~~~

`FindClass` nhận tên class ở dạng nội bộ (hoặc descriptor mảng tương ứng), nên dùng `/`. Với mảng `String[]`, dạng là:

~~~c
jclass arrayCls = (*env)->FindClass(env, "[Ljava/lang/String;");
~~~

Cả hai ví dụ phải kiểm tra kết quả `NULL` và pending Java exception trước khi tiếp tục. `FindClass` cũng chịu ngữ cảnh class loader; tên đúng chưa bảo đảm lớp luôn thấy được ở mọi loader.

Khi tìm method/field bằng JNI, **tên Java và descriptor là hai đối số khác nhau**:

~~~c
/* Minh họa: chỉ gọi sau khi có một jclass cls hợp lệ. */
jmethodID id = (*env)->GetStaticMethodID(
    env, cls, "size", "([I)I"
);
~~~

`"size"` là tên phương thức **nguyên gốc**, không phải tên C `Java_...`; `"([I)I"` là descriptor chính xác cho `static int size(int[])`. `GetStaticMethodID` tìm static method; với instance method dùng `GetMethodID`. Khi lookup thất bại, JNI có thể để lại Java exception cần được xử lý.

## 4. Cách tạo tên hàm C theo quy tắc JNI (name mangling)

### 4.1. Công thức

Đối với cơ chế **name-based JNI linking**, quy tắc có dạng:

~~~text
Tên ngắn:
Java_<escaped-internal-class-name>_<escaped-method-name>

Tên dài:
Java_<escaped-internal-class-name>_<escaped-method-name>__<escaped-parameter-descriptor>
~~~

Bước thực hiện:

1. Lấy **binary name** của class thực sự **khai báo native method**.
2. Chuyển thành **internal form** (`.` ngăn package → `/`, giữ đúng `$` của nested class).
3. **Escape** tên class nội bộ theo bảng JNI.
4. Escape tên phương thức Java (không tự ý đổi `_`).
5. Nếu cần phân biệt các native method overloaded: thêm đúng **hai dấu gạch dưới** `__`, rồi escape chuỗi descriptor **của các tham số** (không chứa dấu ngoặc hay kiểu trả về).

Tên dài không phải cách viết của method descriptor thông thường, mà là một tên symbol C có chứa bản **mã hóa** của descriptor tham số.

### 4.2. Bảng escape chính thức

| Ký tự gốc | Phần được ghi trong tên JNI C | Ví dụ |
|---|---|---|
| Chữ/số ASCII `A–Z`, `a–z`, `0–9` | Giữ nguyên | `size` → `size` |
| Dấu slash `/` | `_` | `java/lang` → `java_lang` |
| Dấu gạch dưới `_` | `_1` | `sum_value` → `sum_1value` |
| Dấu chấm phẩy `;` | `_2` | `Ljava/lang/String;` → `Ljava_lang_String_2` |
| Dấu ngoặc vuông mở `[` | `_3` | `[I` → `_3I` |
| Ký tự UTF-16 khác | `_0xxxx`, bốn chữ số hex thường | `$` (U+0024) → `_00024`; `é` (U+00E9) → `_000e9` |

Ký hiệu `_0xxxx` ở đây nghĩa là dấu `_`, số `0` rồi **bốn chữ số hexa** đại diện một *UTF-16 code unit*. Với ký tự nằm ngoài Basic Multilingual Plane (có surrogate pair), từng đơn vị surrogate được mã hóa riêng; không gộp thành một mã code point có hơn bốn chữ số. Một số quy tắc bổ sung của JVM bảo đảm ánh xạ hợp lệ với các tên class được phép trong class file; cách chắc chắn nhất là để `javac -h` sinh header.

**Vì sao ký tự `_` phải thành `_1`?** Nếu giữ nguyên, dấu `_` trong tên method có thể bị nhầm với dấu phân tách package/class/method hoặc dấu mở đầu hậu tố overload. Ví dụ `sum_value` phải thành `sum_1value`; viết `sum_value` trong tên C có thể trỏ tới một tên Java khác.

**Vì sao hai dấu `__` đôi khi thành ba dấu `___`?** Hậu tố long name bắt đầu bằng `__`, trong khi descriptor mảng `[I` khi escape bắt đầu bằng `_3I`. Ghép trực tiếp: `__` + `_3I` = `___3I`. Đây là kết quả đúng, không phải lỗi gõ thừa underscore.

### 4.3. Short name và long name khi overload

Khi giải quyết phương thức `native` bằng tên symbol, JVM tìm **short name trước**, rồi nếu không thấy mới tìm **long name** (theo đặc tả JNI). Vì vậy:

- Một native method không bị overload bởi native method khác thường có thể dùng **short name**.
- Hai hoặc nhiều **native** method trong cùng class có cùng tên nhưng khác kiểu tham số cần các **long name riêng biệt**, để mỗi phương thức trỏ đúng mã C.
- Nếu chỉ trùng tên với một phương thức **Java không native**, native method không nhất thiết phải dùng long name, vì phương thức Java kia không cần symbol trong thư viện native.
- Không nên export một short symbol “dùng chung” cho nhiều native overload với chữ ký C khác nhau; short name được thử trước có thể dẫn tới liên kết không mong muốn và lỗi ABI nguy hiểm.

Mặc dù biết quy tắc là cần thiết, bạn nên **sinh header bằng `javac -h` mỗi khi khai báo hoặc thay đổi native method**, rồi include header đó vào tệp C/C++.

## 5. Ví dụ suy ra tên JNI từ class và overload

Giả sử class trong package `edu.demo.jni`:

~~~java
package edu.demo.jni;

public final class NativeNames {
    public static native int sum_value(int a, int b);
    public static native int size(int[] values);
    public static native int size(String text);
}
~~~

Đây là **đoạn khai báo để phân tích**, chương trình chạy đầy đủ sẽ có `static` load library và `main` ở phần thực hành bên dưới.

Tên internal class: `edu/demo/jni/NativeNames`. Sau escaping: `edu_demo_jni_NativeNames`.

| Java method | JVM descriptor | Descriptor **tham số** | Tên hàm JNI C |
|---|---|---|---|
| `sum_value(int,int)` | `(II)I` | `II` | `Java_edu_demo_jni_NativeNames_sum_1value` |
| `size(int[])` | `([I)I` | `[I` | `Java_edu_demo_jni_NativeNames_size___3I` |
| `size(String)` | `(Ljava/lang/String;)I` | `Ljava/lang/String;` | `Java_edu_demo_jni_NativeNames_size__Ljava_lang_String_2` |

Giải thích kết quả:

- `sum_value` không overload: tên ngắn đủ dùng, và dấu `_` trong tên method phải được escape thành `_1`.
- `size(int[])` cần hậu tố phân biệt overload: `__` + escape `[I` là `_3I`, tạo ra `size___3I`.
- `size(String)` dùng hậu tố `__Ljava_lang_String_2` vì `/` biến thành `_`, còn dấu `;` biến thành `_2`.

Đừng gắn thêm `I` của **kiểu trả về** vào hậu tố long name: hai hàm `size` đều trả `int` nhưng JVM phân biệt chúng bằng **tham số**.

### 5.1. Tên JVM có `$` và Unicode

Nếu một member class có binary name `edu.demo.jni.Outer$Inner`, phần tên class trong symbol JNI có dạng:

~~~text
edu_demo_jni_Outer_00024Inner
~~~

Nếu method được khai báo tên `tínhToán` hoặc class chứa Unicode, tên C có thể chứa các escape `_0xxxx` bổ sung. Không phiên âm, bỏ dấu, hoặc chuyển tùy ý sang ASCII: chỉ cần sai một UTF-16 code unit sẽ khác symbol mà JVM dự kiến. Header được JDK sinh là nguồn đối chiếu đáng tin.

## 6. Thực hành hoàn chỉnh Java 17+ → header JNI → C → JVM

Ví dụ này chạy bằng **một class Java có một native method chứa underscore và hai native overload**, qua đó kiểm tra đồng thời `_1`, `_3`, `_2` và `__`.

Cấu trúc thư mục sau khi tạo file:

~~~text
jni-names/
├── src/
│   └── edu/demo/jni/
│       └── NativeNames.java
├── native_names.c
└── build/               (được tạo bởi các lệnh biên dịch)
    ├── classes/
    └── headers/
~~~

### 6.1. Java: `src/edu/demo/jni/NativeNames.java`

~~~java
package edu.demo.jni;

public final class NativeNames {
    static {
        System.loadLibrary("native_names");
    }

    private NativeNames() {
    }

    public static native int sum_value(int a, int b);

    public static native int size(int[] values);

    public static native int size(String text);

    public static void main(String[] args) {
        System.out.println("sum_value(2, 3) = " + sum_value(2, 3));
        System.out.println("size(int[]) = " + size(new int[] {2, 4, 6}));
        System.out.println("size(String) = " + size("JNI"));
    }
}
~~~

Đây là mã Java **đầy đủ và có thể biên dịch** trên Java 17+. Khối `static` nạp thư viện theo **tên logic** `native_names`; tên tệp native thực tế sẽ được hệ thống/JVM ánh xạ phù hợp nền tảng. `System.loadLibrary("native_names")` không sử dụng tên Java class hay tên symbol `Java_...`.

### 6.2. Sinh bytecode và header

Ở thư mục `jni-names`, chạy trên Linux/macOS:

~~~bash
mkdir -p build/classes build/headers
javac -h build/headers -d build/classes src/edu/demo/jni/NativeNames.java
~~~

Trên Windows Command Prompt:

~~~bat
if not exist build\classes mkdir build\classes
if not exist build\headers mkdir build\headers
javac -h build\headers -d build\classes src\edu\demo\jni\NativeNames.java
~~~

Kết quả gồm `build/classes/edu/demo/jni/NativeNames.class` và header **`build/headers/edu_demo_jni_NativeNames.h`**. Trong header, phần khai báo hàm cốt lõi có dạng (đây là **trích đoạn**, header thực có guard, `#include <jni.h>` và thông tin signature):

~~~c
JNIEXPORT jint JNICALL Java_edu_demo_jni_NativeNames_sum_1value
  (JNIEnv *, jclass, jint, jint);

JNIEXPORT jint JNICALL Java_edu_demo_jni_NativeNames_size___3I
  (JNIEnv *, jclass, jintArray);

JNIEXPORT jint JNICALL Java_edu_demo_jni_NativeNames_size__Ljava_lang_String_2
  (JNIEnv *, jclass, jstring);
~~~

Cả ba method đều được khai báo `static native`, nên đối số ẩn thứ hai của hàm JNI là **`jclass`** (tham chiếu class). Nếu khai báo instance native method, vị trí này là `jobject` (receiver/`this`). `JNIEnv *` luôn đứng trước ở dạng C JNI thông thường.

Bạn cũng có thể đọc descriptor từ bytecode:

~~~bash
javap -s -p -classpath build/classes edu.demo.jni.NativeNames
~~~

Tìm các dòng `descriptor: (II)I`, `descriptor: ([I)I` và `descriptor: (Ljava/lang/String;)I`. Các dòng này là cách kiểm tra **descriptor JVM**; hãy phân biệt với phần escaped descriptor trong tên C.

### 6.3. C: `native_names.c`

~~~c
#include "edu_demo_jni_NativeNames.h"

JNIEXPORT jint JNICALL Java_edu_demo_jni_NativeNames_sum_1value(
    JNIEnv *env, jclass cls, jint a, jint b
) {
    (void) env;
    (void) cls;
    return a + b;
}

JNIEXPORT jint JNICALL Java_edu_demo_jni_NativeNames_size___3I(
    JNIEnv *env, jclass cls, jintArray values
) {
    (void) cls;
    return (*env)->GetArrayLength(env, values);
}

JNIEXPORT jint JNICALL Java_edu_demo_jni_NativeNames_size__Ljava_lang_String_2(
    JNIEnv *env, jclass cls, jstring text
) {
    (void) cls;
    return (*env)->GetStringLength(env, text);
}
~~~

Đây là **tệp C đầy đủ** cho ví dụ. Nó include header do `javac -h` tạo, nên compiler có thể kiểm tra các kiểu khai báo JNI. `JNIEXPORT` đảm bảo export symbol; `JNICALL` chọn calling convention tương ứng với JNI ở nền tảng. Không tự xóa các macro này.

`GetArrayLength` trả **số phần tử mảng** (ở đây `{2,4,6}` có 3 phần tử). `GetStringLength` trả độ dài chuỗi Java theo **UTF-16 code units** (chuỗi `"JNI"` có 3 đơn vị). Ví dụ chỉ truyền tham số **khác null**; code học tập này chưa định nghĩa chính sách cho đầu vào null. Hai phép cộng/nhân của ví dụ không cần API JNI nào khác; với tính toán `int` thực tế cần cân nhắc tràn số nguyên nếu dùng toán hạng lớn.

### 6.4. Biên dịch native library và chạy

Chỉ chạy **bộ lệnh phù hợp với hệ điều hành của JVM**. Cần một JDK có `jni.h`, compiler C phù hợp với kiến trúc của JVM, và biến `JAVA_HOME` trỏ tới JDK. Các lệnh dưới đây giả định bạn vừa chạy bước `javac -h` thành công.

**Linux (GCC):**

~~~bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  native_names.c -o libnative_names.so

java -Djava.library.path=. -cp build/classes edu.demo.jni.NativeNames
~~~

**macOS (Clang):**

~~~bash
cc -dynamiclib -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/headers \
  native_names.c -o libnative_names.dylib

java -Djava.library.path=. -cp build/classes edu.demo.jni.NativeNames
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /I"build\headers" native_names.c /Fe:native_names.dll

java -Djava.library.path=. -cp build\classes edu.demo.jni.NativeNames
~~~

Khi build và nạp thành công, **stdout chính xác**:

~~~text
sum_value(2, 3) = 5
size(int[]) = 3
size(String) = 3
~~~

Giải thích kết quả: method chứa underscore được JVM liên kết với symbol `sum_1value`; overload `size(int[])` được liên kết với symbol có `___3I`; overload `size(String)` được liên kết với symbol chứa `__Ljava_lang_String_2`. Kết quả bằng nhau ở hai lệnh `size` không có nghĩa chúng cùng C function: chúng nhận loại tham số khác nhau, có tên JNI dài khác nhau và dùng API JNI khác nhau.

## 7. Từ class file đến symbol: trình tự cần nhớ

~~~text
Java source
  package edu.demo.jni;
  class NativeNames { native int size(int[] v); }
           |
           v javac
Class binary name: edu.demo.jni.NativeNames
           |
           v Internal form
edu/demo/jni/NativeNames
           |
           v Escape tên class + tên method
Java_edu_demo_jni_NativeNames_size
           |
           v Overload: lấy descriptor tham số "[I"
           v Escape "[I" -> "_3I"
           v Thêm "__" trước hậu tố
Java_edu_demo_jni_NativeNames_size___3I
           |
           v Export từ thư viện native + JVM lookup
Lời gọi Java -> hàm C JNI -> giá trị trả về Java
~~~

Sơ đồ chỉ mô tả **quy tắc ánh xạ tên**, không thể thay thế việc build đúng binary, nạp thư viện và kiểm tra class loader/ABI. Tên thư viện `native_names` và tên symbol `Java_...` là hai cơ chế độc lập: thư viện có thể chứa nhiều symbol cho nhiều class Java.

## 8. Chú ý riêng: dấu gạch chéo không phải dấu phân cách file trên Windows

Không trộn bốn loại separator:

| Bối cảnh | Ví dụ chính xác | Quy tắc |
|---|---|---|
| Package Java / binary name | `edu.demo.jni.NativeNames` | Dấu chấm `.` |
| Internal name JVM | `edu/demo/jni/NativeNames` | Slash `/`, không đổi theo OS |
| Path filesystem Windows | `src\edu\demo\jni\NativeNames.java` | Backslash `\` trong cmd (đường dẫn); Java API có thể nhận slash tùy ngữ cảnh |
| JNI mangled C symbol | `Java_edu_demo_jni_NativeNames_size___3I` | Underscore và escape có quy tắc |

Ngay cả trên Windows, `FindClass(env, "edu/demo/jni/NativeNames")` vẫn dùng slash chuẩn JVM. Viết `"edu\demo\jni\NativeNames"` vào string Java sẽ gây vấn đề escape ký tự, còn dùng backslash để thay slash trong JNI internal class name là không đúng hợp đồng API.

Trong `System.load("/absolute/path/libnative_names.so")`, bạn đang truyền **đường dẫn tệp** native, không phải internal name. `System.loadLibrary("native_names")` nhận **tên logic**, không nhận slash hay đuôi `.so`/`.dll`/`.dylib`. Đừng ghép những API khác mục đích vào cùng một quy tắc.

## 9. Nếu dùng `RegisterNatives` thì còn cần tên `Java_...` không?

Ngoài tra cứu symbol tự động theo tên, JNI cho phép đăng ký thủ công qua `RegisterNatives`, ánh xạ từng phương thức Java với con trỏ hàm native. Khi đăng ký, ta dùng **tên Java nguyên gốc** và **descriptor JVM đầy đủ**, ví dụ:

~~~text
method name:  "size"
signature:    "([I)I"
native impl:  (con trỏ hàm C có chữ ký JNI phù hợp)
~~~

Vì mapping đã được đăng ký tường minh, tên hàm C **không nhất thiết phải có dạng `Java_...`**. Tuy nhiên vẫn phải khớp JNI ABI, `JNIEnv *`, `jclass`/`jobject`, kiểu đối số, kiểu trả về, và quản lý đăng ký đúng class loader. `RegisterNatives` là cơ chế khác, không phải cách “bỏ qua” chữ ký.

Người mới học nên dùng `javac -h` và exported name trước vì dễ nhìn thấy sự tương ứng. Khi đã vững quy tắc, có thể đọc tiếp các thư viện triển khai JNI thông qua đăng ký phương thức.

## 10. Những lỗi đặt tên dễ làm JNI không liên kết được

| Lỗi | Triệu chứng/hậu quả | Cách khắc phục |
|---|---|---|
| Dùng dấu chấm trong tên hàm C | Không có symbol JVM dự kiến | Lấy internal form rồi dùng quy tắc JNI escape, sinh lại header. |
| Dùng `_` thô trong tên Java có underscore | Export sai `Java_..._sum_value` thay vì `..._sum_1value` | Escape `_` thành `_1`. |
| Quên phần `__` khi có hai native overload | Không có tên dài phân biệt hoặc liên kết nhầm | So với header do `javac -h` sinh, dùng đúng hậu tố tham số. |
| Dùng `[I` nguyên trong symbol C | Ký tự `[` không phải tên escape hợp lệ | `[` phải thành `_3`. |
| Chỉ đổi `/` thành `_` mà quên `;` | String overload bị thiếu `_2` | Escape descriptor toàn phần theo bảng. |
| Thêm kiểu trả về vào hậu tố long name | Symbol không đúng tên mà JVM dự đoán | Chỉ dùng descriptor **tham số** trong hậu tố. |
| Viết nested class bằng `Outer.Inner` thay cho binary name `Outer$Inner` | Class/symbol sai | Dùng binary name có `$`, escape thành `_00024`. |
| Đưa `java.lang.String` vào field/method descriptor | Descriptor sai | Viết `Ljava/lang/String;`. |
| Truyền đường dẫn file vào `FindClass` | JVM không tìm thấy class | Truyền internal name `pkg/Class` hoặc array descriptor. |
| Đổi chữ ký Java nhưng không build lại C/header | Lỗi `UnsatisfiedLinkError` hoặc mismatch | Chạy lại `javac -h`, cập nhật C và build lại native library. |

Đối với lỗi **không tìm thấy phương thức native**, hãy tách ba điểm kiểm tra: (1) JVM đã **load được thư viện** chưa, (2) thư viện đã **export đúng symbol JNI** hoặc `RegisterNatives` đúng chưa, và (3) **descriptor/ABI** có đúng với khai báo Java hiện tại không. Một lỗi `UnsatisfiedLinkError` có thể xuất phát từ các giai đoạn khác nhau.

Công cụ gợi ý:

~~~text
Java:    javac -h ; javap -s -p
Linux:   nm -D ; readelf -Ws
macOS:   nm -g
Windows: dumpbin /EXPORTS
~~~

Đây là **danh sách tên công cụ và tùy chọn gợi ý**, không phải một lệnh shell hoàn chỉnh. Khi sử dụng, truyền đúng tên class, tên tệp thư viện và các tham số phù hợp với công cụ hiện tại. Không phải mọi compiler/linker đều export symbol giống nhau khi cấu hình khác nhau, vì vậy header và bảng symbol của binary mới build là bằng chứng cần đối chiếu.

## 11. Tự kiểm tra trước khi chuyển sang bài JNI tiếp theo

1. Với `org.demo.Fast_Parser`, internal class name là gì, và phần class escaped trong tên JNI thay đổi thế nào ở dấu `_`?
2. `Outer.Inner` và `Outer$Inner` khác nhau ở ngữ cảnh nào? Vì sao tên JNI có thể xuất hiện `_00024`?
3. Descriptor của `int[][]`, `String[]` và `long calculate(int, String[])` lần lượt là gì?
4. Vì sao `size(int[])` tạo ra `size___3I` với **ba dấu underscore liên tiếp**?
5. Với `static native int f(String s)`, vì sao suffix long name (nếu cần) chứa `Ljava_lang_String_2` nhưng không chứa kiểu trả về `I`?
6. Trong JNI C, khi gọi `FindClass` với `"java/lang/String"`, dấu `/` có phụ thuộc hệ điều hành không?
7. Nếu chuyển class từ `edu.demo.jni.NativeNames` sang package khác mà quên biên dịch lại C, JVM có liên kết được symbol tên cũ không?
8. Trường hợp nào có thể dùng short name cho một native method có cùng tên với một phương thức Java thường, và vì sao không nên export short name chung cho nhiều **native overload**?

**Ghi nhớ:** Đầu tiên lấy **binary name** đúng, chuyển sang **internal name dùng `/`**, xác định descriptor JVM và chỉ sau đó **escape theo bảng JNI** để hình thành symbol `Java_...`. Short name không có hậu tố tham số; long name thêm `__` và **descriptor tham số đã escape**. `javac -h` là cách đáng tin nhất để kiểm chứng tên và chữ ký thật.

### Tài liệu chuẩn để tra cứu

- [Java Native Interface Specification — Resolving Native Method Names](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html): quy tắc tạo short/long names và bảng escape ký tự.
- [The Java Virtual Machine Specification — Names and Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html): binary names, internal form, field/method descriptors.
- [Lệnh javac — tùy chọn -h](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): cách sinh header JNI từ khai báo Java.
