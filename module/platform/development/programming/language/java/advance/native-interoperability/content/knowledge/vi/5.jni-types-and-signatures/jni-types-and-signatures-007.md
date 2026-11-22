# Truyền danh sách tham số qua `jvalue` và các biến thể A hoặc V trong JNI

Khi mã native C/C++ cần **gọi ngược một phương thức Java** qua JNI (Java Native Interface), JNI cung cấp nhiều cách truyền tham số cho cùng một phương thức: đưa đối số trực tiếp sau `jmethodID`, đóng gói từng đối số vào mảng `jvalue[]` rồi gọi hàm có hậu tố **A**, hoặc chuyển một danh sách biến đối số C dạng `va_list` cho hàm có hậu tố **V**.

Ba cách chỉ khác **hình thức đưa tham số vào lời gọi JNI**. Phương thức Java đích, thứ tự tham số, kiểu trả về và chữ ký JNI phải nhất quán trong cả ba cách. Không có cơ chế tự phát hiện kiểu của từng phần tử trong `jvalue[]`: người lập trình chịu trách nhiệm khớp chính xác kiểu với method descriptor.

## 1. Ngữ cảnh: Java gọi native và native gọi Java

Luồng điển hình:

```text
Java: JniArgumentDemo.main()
   |
   | gọi native method, ví dụ callNumbers()
   v
C: Java_JniArgumentDemo_callNumbers(JNIEnv*, jclass)
   |
   | GetMethodID(...) / GetStaticMethodID(...)
   | chuẩn bị đối số C
   |
   +-- CallIntMethod(...)         // các đối số C trực tiếp
   +-- CallIntMethodA(..., args)  // mảng jvalue
   +-- CallIntMethodV(..., ap)    // va_list C
   |
   v
Java: một instance/static method được gọi ngược
   |
   | trả giá trị hoặc ném Java exception
   v
C: tiếp tục xử lý / trả kết quả về native caller
```

**Ranh giới quan trọng:** `jvalue[]`, `Call<Type>MethodA` và `Call<Type>MethodV` phục vụ chiều **native gọi phương thức Java**. Chúng không biến một Java `Object...` thành “danh sách đối số JNI”, và cũng không thay thế chữ ký C của một `native` method được Java gọi vào. Java varargs là một cú pháp ngôn ngữ được biên dịch thành **một tham số mảng**; C varargs (`...`) là cơ chế ABI/C khác hẳn.

Khi JNI đi tìm phương thức Java, thông thường cần:

1. Một `JNIEnv *env` hợp lệ của **thread hiện tại**.
2. `jclass` hoặc `jobject` đích phù hợp với kiểu phương thức.
3. `jmethodID` lấy bằng `GetMethodID` (instance/constructor) hoặc `GetStaticMethodID` (static).
4. Descriptor JNI chính xác: `(kiểu-tham-số...)kiểu-trả-về`.
5. Giá trị đối số được sắp **đúng vị trí và đúng kiểu**.

## 2. `jvalue` là một `union` C, không phải một Java object

`jni.h` khai báo kiểu giá trị cho từng **slot** đối số như sau (đây là định nghĩa dạng C theo đặc tả JNI):

```c
typedef union jvalue {
    jboolean z;
    jbyte    b;
    jchar    c;
    jshort   s;
    jint     i;
    jlong    j;
    jfloat   f;
    jdouble  d;
    jobject  l;
} jvalue;
```

Một `union` C chia sẻ cùng vùng nhớ giữa các thành viên; tại một thời điểm, slot phải được gán qua **thành viên phù hợp với kiểu tham số Java ở đúng vị trí**. `jvalue` không tự gắn thẻ “đây là int hay String” và không thực hiện ép kiểu an toàn ở runtime.

| Kiểu Java của tham số | Ký tự descriptor JNI | Thành viên trong `jvalue` | Kiểu native JNI |
| --- | --- | --- | --- |
| `boolean` | `Z` | `.z` | `jboolean` |
| `byte` | `B` | `.b` | `jbyte` |
| `char` | `C` | `.c` | `jchar` (16-bit unsigned) |
| `short` | `S` | `.s` | `jshort` |
| `int` | `I` | `.i` | `jint` |
| `long` | `J` | `.j` | `jlong` |
| `float` | `F` | `.f` | `jfloat` |
| `double` | `D` | `.d` | `jdouble` |
| `String`, mọi object và array | `Ljava/lang/String;`, `L...;` hoặc `[...]` | `.l` | `jobject` / `jstring` / `jarray` / ... |

Dùng `JNI_TRUE`/`JNI_FALSE` khi tạo `jboolean`. Java `char` là đơn vị mã UTF-16 16 bit; không đồng nhất nó với `char` C một byte. Tương tự, `jlong` là kiểu signed 64-bit của JNI; không mặc nhiên đồng nhất với C `long` trên mọi ABI.

### Ví dụ đóng gói một phương thức có các kiểu khác nhau

Giả sử Java có:

```java
public static String describe(String name, int count, double factor) {
    return name + ":" + count + ":" + factor;
}
```

Descriptor chính xác là `(Ljava/lang/String;ID)Ljava/lang/String;`: tham số thứ nhất là reference `String`, thứ hai `int`, thứ ba `double`; trả về `String`. Phía C:

```c
/* Đoạn minh họa, không độc lập: env, clazz phải hợp lệ. */
jmethodID mid = (*env)->GetStaticMethodID(
        env, clazz, "describe",
        "(Ljava/lang/String;ID)Ljava/lang/String;");
if (mid == NULL) {
    return; /* chỉ phù hợp với hàm C trả void */
}

jstring name = (*env)->NewStringUTF(env, "item");
if (name == NULL) {
    return; /* cần xử lý exception hoặc thiếu bộ nhớ */
}

jvalue args[3] = {{0}, {0}, {0}};
args[0].l = name;
args[1].i = 7;
args[2].d = 1.5;

jstring result = (jstring)(*env)->CallStaticObjectMethodA(
        env, clazz, mid, args);

(*env)->DeleteLocalRef(env, name);
/* Kiểm tra ExceptionCheck và xử lý 'result' theo contract của caller. */
```

Đây là **đoạn minh họa** cho hàm native `void` có `env` và `clazz` đã được cung cấp; ví dụ chạy đầy đủ có kiểm tra ngoại lệ ở phần 6. Lưu ý không gửi `char *` chứa chuỗi C trực tiếp vào `args[0].l`. Nó phải là một **Java reference** hợp lệ (ở đây là `jstring` tạo bằng JNI). Bản thân `jvalue[]` là mảng C nằm trong bộ nhớ native, **không phải** `jobjectArray` của Java.

### Quy tắc thứ tự

Nếu Java đích khai báo `f(int a, long b, String c)`, hãy dùng:

```c
jvalue args[3] = {{0}, {0}, {0}};
args[0].i = 10;        /* int a  */
args[1].j = (jlong)20; /* long b */
args[2].l = textRef;   /* String c: jstring đã hợp lệ */
```

Thứ tự phần tử trong mảng **chính là thứ tự tham số của descriptor**; không có trường tên tham số, không có tự sắp xếp hay tự kiểm tra số lượng. `args[1].i` không thể thay thế `args[1].j` chỉ vì giá trị 20 nhỏ. Với kiểu reference, `NULL` có thể đại diện Java `null` **nếu** contract của method cho phép; nó không thay thế một primitive.

## 3. Ba biến thể của cùng một lời gọi

Giả sử Java đích là:

```java
public int calculate(int x, int y) {
    return 100 + x * 10 + y;
}
```

Phía C đã có `jobject target` phù hợp, `jmethodID mid` lấy từ `GetMethodID(..., "calculate", "(II)I")`. Ba cách gọi:

### Không hậu tố: đối số trực tiếp trong `...` của C

```c
jint result = (*env)->CallIntMethod(env, target, mid, (jint)2, (jint)3);
```

Dễ đọc khi chữ ký và các đối số đã được biết tại nơi viết mã. Đây là **C variadic function call**, không phải cơ chế Java `Object...`.

### Hậu tố A: `jvalue[]`

```c
jvalue args[2] = {{0}, {0}};
args[0].i = 2;
args[1].i = 3;

jint result = (*env)->CallIntMethodA(env, target, mid, args);
```

Hữu ích khi các giá trị đã nằm trong một cấu trúc dữ liệu và cần sắp xếp thành danh sách tham số trước lúc gọi, ví dụ bridge/dispatcher native có metadata về từng loại tham số. Đừng tự động cho rằng “A” nghĩa là **asynchronous**: A ở đây là **array of `jvalue`**; lời gọi vẫn đồng bộ như hàm JNI tương ứng.

### Hậu tố V: `va_list`

```c
#include <stdarg.h>

static jint calculate_v(JNIEnv *env, jobject target,
                        jmethodID mid, ...) {
    va_list ap;
    va_start(ap, mid);
    jint result = (*env)->CallIntMethodV(env, target, mid, ap);
    va_end(ap);
    return result;
}

/* Trong một hàm C đang có env, target, mid hợp lệ: */
jint result = calculate_v(env, target, mid, 2, 3);
```

`va_list` được tạo bằng `va_start` trong một hàm C **thực sự có `...`**; nó không phải con trỏ đến `jvalue[]`. `va_end` phải được gọi sau khi dùng, kể cả trường hợp Java callback ném exception (như wrapper trên). Nếu một `va_list` cần sử dụng nhiều lần, phải hiểu vòng đời và dùng `va_copy` theo ABI C; không giả định JNI `...V` không làm thay đổi vị trí/biểu diễn nội bộ của `va_list`.

Ba ví dụ trên, nếu Java method chạy bình thường với `x = 2` và `y = 3`, đều trả `123`. Sự khác nhau nằm ở **cách cung cấp đối số**, không nằm ở công thức Java hay kiểu kết quả.

## 4. Chọn đúng nhóm hàm JNI

`<Type>` trong tên hàm là **kiểu trả về của Java method**, không phải kiểu tham số đầu tiên. Ví dụ phương thức Java trả `long` thì dùng `CallLongMethodA`; dù phương thức ấy nhận `int`, vẫn không dùng `CallIntMethodA`.

| Đích gọi | Lấy `jmethodID` bằng | A / V / không hậu tố |
| --- | --- | --- |
| Instance method (gọi ảo thông thường) | `GetMethodID(env, clazz, name, signature)` | `Call<Type>MethodA` / `Call<Type>MethodV` / `Call<Type>Method` |
| Static method | `GetStaticMethodID(env, clazz, name, signature)` | `CallStatic<Type>MethodA` / `CallStatic<Type>MethodV` / `CallStatic<Type>Method` |
| Instance method **nonvirtual** | `GetMethodID` trên class/interface chỉ định | `CallNonvirtual<Type>MethodA` / `...V` / `...`; có thêm `jclass clazz` |
| Constructor | `GetMethodID(env, clazz, "<init>", "(...)V")` | `NewObjectA` / `NewObjectV` / `NewObject` |

Các lựa chọn `<Type>` gồm `Object`, `Boolean`, `Byte`, `Char`, `Short`, `Int`, `Long`, `Float`, `Double`, `Void` (với phương thức Java trả `void`). `CallObjectMethodA` dành cho kiểu reference, gồm `String` và array; giá trị JNI trả về là local reference `jobject` có thể ép về subtype phù hợp sau khi kiểm tra method signature.

Ví dụ chữ ký:

| Java method | Descriptor | Hàm gọi phù hợp |
| --- | --- | --- |
| `int sum(int a, int b)` | `(II)I` | `CallIntMethodA` nếu là instance |
| `static long read(long seed)` | `(J)J` | `CallStaticLongMethodV` nếu có `va_list` |
| `String label(int id, String s)` | `(ILjava/lang/String;)Ljava/lang/String;` | `CallObjectMethodA` |
| `void fill(int[] numbers)` | `([I)V` | `CallVoidMethodA` với `args[0].l` là `jintArray` |
| `Widget(String name, int size)` | `(Ljava/lang/String;I)V` | `NewObjectA` hoặc `NewObjectV` |

Constructor không có “giá trị Java trả về”, descriptor luôn kết thúc bằng `V`; **`NewObjectA` trả `jobject`** cho instance mới sau khi constructor được gọi. Không dùng `CallObjectMethodA` để mô phỏng một lời gọi constructor thông thường.

**Nonvirtual khác virtual:** `Call<Type>MethodA` dispatch theo instance Java; `CallNonvirtual<Type>MethodA` yêu cầu class đích rõ ràng và có thể gọi implementation được chỉ định ở class cha (tương tự nhu cầu gọi `super`) hoặc default interface method. Phải truyền `jclass` và `jmethodID` nhất quán với class tương ứng; không chọn nonvirtual chỉ vì muốn tránh override một cách tùy tiện.

## 5. Descriptor, argument promotion và lỗi ABI

### Descriptor là hợp đồng ở runtime

JNI không nhìn tên biến Java hay generic type parameters. `GetMethodID`/`GetStaticMethodID` lấy method bằng **tên và descriptor**. Một dấu `;` hoặc `[` thiếu trong descriptor có thể khiến method lookup không tìm thấy method dù tên hiển thị giống.

| Java type | Descriptor |
| --- | --- |
| `boolean`/`byte`/`char`/`short` | `Z`/`B`/`C`/`S` |
| `int`/`long`/`float`/`double` | `I`/`J`/`F`/`D` |
| `String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |
| `void` | `V` (kiểu trả về hoặc của constructor) |

Ví dụ `long evaluate(int count, String text, int[] samples)` có descriptor `(ILjava/lang/String;[I)J`. Class trong descriptor dùng dấu `/` theo internal class name; `L...;` bao quanh kiểu reference. Với phương thức overload, mỗi overload phải được tìm theo **descriptor của chính nó**.

**Cách kiểm chứng:** `javap -s -p JniArgumentDemo` cho thấy descriptor của phương thức Java đã biên dịch (kể cả private). Tên Java `int` và kiểu C `jint` có hợp đồng bề rộng rõ ràng; kiểu native C `int`/`long` tùy ABI vẫn cần được dùng qua kiểu JNI tương ứng.

### C varargs có default argument promotions

Ở biến thể không hậu tố và trong helper `...` của V, C áp dụng quy tắc chuyển đổi đối số không có prototype riêng:

- `float` được nâng thành `double`.
- Những kiểu số nguyên nhỏ hơn `int` như `char`/`short` thường được nâng thành `int` (hoặc `unsigned int` theo quy tắc C).
- `int` giữ kiểu `int`; các kiểu khác phải truyền đúng representation và ABI yêu cầu của phương thức JNI.

Điều này **không áp dụng** cho mảng `jvalue[]` theo cách tự động. Với `A`, gán đúng `args[k].f` khi descriptor có `F`, `args[k].b` khi có `B`, `args[k].j` khi có `J`. Với `V`, C xử lý danh sách tham số theo default promotions và ABI. Ví dụ không thể lấy `jvalue args[3]` rồi ép `(va_list)args` để gọi `Call...MethodV`: `va_list` có thể là một kiểu cấu trúc/chứa thanh ghi theo ABI và không có representation tương thích mảng union.

Trên nhiều nền tảng, `va_list` còn có cơ chế truyền đối số qua register và stack riêng; sai kiểu khi truyền sang `...`/`...V` có thể gây giá trị sai hoặc crash. Khi dữ liệu đến từ JSON, một metadata table hoặc danh sách đối số động, **A** là đường đi tự nhiên hơn: chuẩn hóa type và fill từng `jvalue`. Đừng tự chế `va_list` từ byte buffer.

### Java varargs không làm tăng số lượng tham số JNI

Ví dụ:

```java
public static String join(String delimiter, String... values) {
    return String.join(delimiter, values);
}
```

Descriptor là `(Ljava/lang/String;[Ljava/lang/String;)Ljava/lang/String;`. JNI nhìn thấy **hai** tham số: `String` và `String[]`, không nhìn thấy N tham số riêng từ dấu `...` của Java. Với biến thể A, cần `jvalue args[2]`: `args[0].l` là `jstring` delimiter và `args[1].l` là `jobjectArray` chứa các `String`. Không đẩy từng phần tử của mảng `values` vào nhiều slot `jvalue` khác nhau.

## 6. Ví dụ chạy được Java 17+ và JNI C (Linux)

Ví dụ này kiểm chứng đồng thời:

- `NewObjectA` để truyền một đối số `int` vào constructor.
- `CallIntMethodA`, `CallIntMethodV` và `CallIntMethod` cho **cùng** instance method `compute(int,int)`.
- `CallStaticIntMethodA` cho static method trả `int`.
- `CallStaticObjectMethodA` với mảng `jvalue` hỗn hợp `String`, `int`, `double`.

Các file được đặt **cùng thư mục**, dùng GCC hoặc Clang, JDK 17+ trên Linux có cùng kiến trúc với thư viện native. Ví dụ này không cần framework; thư viện native dùng tên logic `jniargsdemo`.

### Bước 1 — `JniArgumentDemo.java`

```java
import java.util.Arrays;

public final class JniArgumentDemo {
    static {
        System.loadLibrary("jniargsdemo");
    }

    private final int base;

    public JniArgumentDemo(int base) {
        this.base = base;
    }

    public int compute(int a, int b) {
        return base + a * 10 + b;
    }

    public static int triple(int value) {
        return value * 3;
    }

    public static String describe(String name, int count, double factor) {
        return name + ":" + count + ":" + factor;
    }

    private static native int[] callNumbers();
    private static native String callMixed();

    public static void main(String[] args) {
        System.out.println("numbers=" + Arrays.toString(callNumbers()));
        System.out.println("mixed=" + callMixed());
    }
}
```

`System.loadLibrary("jniargsdemo")` tìm thư viện theo tên logic; Linux thông dụng ánh xạ sang file `libjniargsdemo.so`. Ở ví dụ này dùng `-Djava.library.path=.` ngay lúc khởi động. Java native methods `callNumbers` và `callMixed` chỉ là entry points từ Java sang C; các hàm `compute`/`triple`/`describe` lại là mục tiêu **C gọi ngược sang Java**.

### Bước 2 — `jni_argument_demo.c`

```c
#include "JniArgumentDemo.h"  /* do javac -h tạo; đã include jni.h */
#include <stdarg.h>

/* Wrapper C có ... thực sự: xây va_list rồi chuyển cho JNI V. */
static jint compute_with_v(JNIEnv *env, jobject obj,
                           jmethodID method, ...) {
    va_list ap;
    va_start(ap, method);
    jint value = (*env)->CallIntMethodV(env, obj, method, ap);
    va_end(ap);
    return value;
}

/* Chữ ký được javac -h khai báo trong JniArgumentDemo.h. */
JNIEXPORT jintArray JNICALL
Java_JniArgumentDemo_callNumbers(JNIEnv *env, jclass clazz) {
    jmethodID ctor = (*env)->GetMethodID(
            env, clazz, "<init>", "(I)V");
    if (ctor == NULL) {
        return NULL; /* Java exception pending nếu lookup thất bại */
    }

    jvalue initArgs[1] = {{0}};
    initArgs[0].i = 100;
    jobject obj = (*env)->NewObjectA(env, clazz, ctor, initArgs);
    if (obj == NULL) {
        return NULL;
    }

    jmethodID method = (*env)->GetMethodID(
            env, clazz, "compute", "(II)I");
    if (method == NULL) {
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    jmethodID staticMethod = (*env)->GetStaticMethodID(
            env, clazz, "triple", "(I)I");
    if (staticMethod == NULL) {
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    /* 1. Biến thể A: hai ô jvalue có kiểu jint. */
    jvalue pair[2] = {{0}, {0}};
    pair[0].i = 2;
    pair[1].i = 3;
    jint viaA = (*env)->CallIntMethodA(env, obj, method, pair);
    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    /* 2. Biến thể V: helper C tạo va_list. */
    jint viaV = compute_with_v(env, obj, method, 2, 3);
    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    /* 3. Không hậu tố: đối số C trực tiếp sau method. */
    jint direct = (*env)->CallIntMethod(
            env, obj, method, (jint)2, (jint)3);
    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    /* 4. Static method: phải dùng GetStaticMethodID/CallStatic*. */
    jvalue one[1] = {{0}};
    one[0].i = 4;
    jint viaStatic = (*env)->CallStaticIntMethodA(
            env, clazz, staticMethod, one);
    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    jint values[4] = {viaA, viaV, direct, viaStatic};
    jintArray output = (*env)->NewIntArray(env, 4);
    if (output == NULL) {
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    (*env)->SetIntArrayRegion(env, output, 0, 4, values);
    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, output);
        (*env)->DeleteLocalRef(env, obj);
        return NULL;
    }

    (*env)->DeleteLocalRef(env, obj);
    /* Local ref output được chuyển về Java; không xóa nó ở đây. */
    return output;
}

/* Ví dụ reference + primitive nằm cạnh nhau trong jvalue[]. */
JNIEXPORT jstring JNICALL
Java_JniArgumentDemo_callMixed(JNIEnv *env, jclass clazz) {
    jmethodID method = (*env)->GetStaticMethodID(
            env, clazz, "describe",
            "(Ljava/lang/String;ID)Ljava/lang/String;");
    if (method == NULL) {
        return NULL;
    }

    jstring name = (*env)->NewStringUTF(env, "item");
    if (name == NULL) {
        return NULL;
    }

    jvalue mixed[3] = {{0}, {0}, {0}};
    mixed[0].l = name;
    mixed[1].i = 7;
    mixed[2].d = 1.5;

    jstring result = (jstring)(*env)->CallStaticObjectMethodA(
            env, clazz, method, mixed);

    /* Dọn local ref đầu vào; result là ref khác cần trả cho Java. */
    (*env)->DeleteLocalRef(env, name);
    if ((*env)->ExceptionCheck(env)) {
        return NULL;
    }
    return result;
}
```

**Vì sao cần nhiều lần `ExceptionCheck`?** Khi Java method callback ném exception, JNI đánh dấu exception đang pending; native code phải trả quyền điều khiển về Java hoặc xử lý exception đúng cách. Không tiếp tục thực hiện những JNI calls tùy ý trong khi exception còn pending. `DeleteLocalRef` là một trong những thao tác được phép lúc pending, nên ví dụ dọn object trước khi trả về `NULL`.

Trong `callNumbers`, `jint[] values` là **mảng C** và `jintArray output` là **mảng Java**; `SetIntArrayRegion` sao chép bốn giá trị primitive vào Java array. Còn `jvalue pair[2]` là **mảng union C truyền tham số JNI**. Đây là ba cấu trúc khác nhau.

### Bước 3 — Biên dịch và chạy

Dùng shell Linux. Đặt `JAVA_HOME` trỏ đến **JDK đã cài** (cùng kiến trúc với compiler native); ví dụ cấu hình từ JDK của môi trường trước khi chạy các lệnh sau:

```bash
# Trong thư mục có JniArgumentDemo.java và jni_argument_demo.c:
javac -h . JniArgumentDemo.java

# Cần JAVA_HOME trỏ tới đúng JDK có include/jni.h.
cc -std=c11 -Wall -Wextra -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libjniargsdemo.so jni_argument_demo.c

java -Djava.library.path=. JniArgumentDemo
```

`javac -h .` tạo `JniArgumentDemo.class` và `JniArgumentDemo.h`; compile C sau bước này để dùng header đúng chữ ký và đúng kiểu JNI. Linux dùng `.so`; Windows cần `.dll` và option biên dịch/link phù hợp, macOS dùng quy tắc dylib/JDK tương ứng. `-Djava.library.path=.` phải đứng trước main class để JVM tìm được file `libjniargsdemo.so`.

**Stdout mong đợi**, khi mọi bước thành công:

```text
numbers=[123, 123, 123, 12]
mixed=item:7:1.5
```

Giải thích từng phần:

- Constructor tạo object với `base=100`.
- `compute(2, 3)` trả `100 + 2*10 + 3 = 123`. Ba lời gọi `CallIntMethodA`, `CallIntMethodV` và `CallIntMethod` truyền cùng hai đối số đến cùng method nên đều nhận `123`.
- `triple(4)` là static Java method, trả `12`.
- `describe("item", 7, 1.5)` là static method nhận reference, primitive `int` và `double`, trả `"item:7:1.5"`. C gán đúng `.l`, `.i`, `.d` rồi dùng `CallStaticObjectMethodA`.

Mọi output trên là **xác định bởi mã Java** đã cho; khác biệt về compiler/platform có thể làm thay cách build native, nhưng khi binary đúng ABI/JNI và đã nạp được, giá trị Java trả về phải như trên.

### Bước 4 — Kiểm chứng descriptor từ class đã biên dịch

```bash
javap -s -p JniArgumentDemo
```

Trong output dài hơn của `javap`, các descriptor đáng chú ý là:

```text
public JniArgumentDemo(int);
  descriptor: (I)V

public int compute(int, int);
  descriptor: (II)I

public static int triple(int);
  descriptor: (I)I

public static java.lang.String describe(java.lang.String, int, double);
  descriptor: (Ljava/lang/String;ID)Ljava/lang/String;

private static native int[] callNumbers();
  descriptor: ()[I

private static native java.lang.String callMixed();
  descriptor: ()Ljava/lang/String;
```

Các dòng này minh họa **những phần cần đối chiếu**, không phải bản sao toàn bộ output, vì `javap` còn in class header và các method khác. Các chữ ký được dùng ở `GetMethodID` và `GetStaticMethodID` phải tương ứng chính xác.

## 7. Khi nào nên dùng A, V hay biến thể trực tiếp?

| Tình huống | Chọn | Vì sao |
| --- | --- | --- |
| Native C có số đối số cố định ở vị trí gọi | Không hậu tố, ví dụ `CallIntMethod` | Cú pháp ngắn, nhìn rõ danh sách đối số |
| Native bridge xây danh sách tham số từ metadata | **A** với `jvalue[]` | Mỗi slot chứa đúng kiểu theo descriptor; dễ lặp qua metadata |
| Có một wrapper C variadic thực sự và muốn forward cho JNI | **V** với `va_list` | Tránh viết lại logic đọc `va_arg` của C |
| JNI callback đến static method | `CallStatic<Type>MethodA/V` | Đích là `jclass`, `jmethodID` từ `GetStaticMethodID` |
| JNI tạo Java object bằng constructor | `NewObjectA/V` | `<init>` có descriptor trả `V` nhưng kết quả API là reference tới object |
| Muốn gọi implementation không qua dispatch ảo | `CallNonvirtual<Type>MethodA/V` | Truyền thêm class chỉ định implementation |
| Java method nhận `String...` | A chứa **một reference đến String[]** cho tham số varargs | JNI dùng descriptor mảng; không bung Java varargs thành C varargs |

**Không có biến thể “A nhanh hơn V” như một quy tắc tối ưu hóa tổng quát.** Hãy chọn cấu trúc khớp dữ liệu thật của caller, bảo đảm đúng ABI/descriptor, rồi đo hiệu năng nếu ứng dụng thực sự nhạy với chi phí JNI. Chênh lệch giữa Java/native boundary, boxing/allocations, object lifetime và công việc của method thường quan trọng hơn việc tự suy tốc độ từ hậu tố A/V.

## 8. An toàn tham chiếu, lỗi ngoại lệ và vòng đời method ID

### Reference trong `jvalue.l` phải còn hợp lệ

`jvalue.l` lưu một **JNI reference** như `jstring`, `jobject` hoặc `jintArray`; không lưu con trỏ C tới buffer bất kỳ. Khi gọi `CallObjectMethodA` trả reference, kết quả thường là **local reference** mới (hoặc `NULL`), cần quản lý theo lifecycle JNI. Trong một native method call, local refs tự được dọn khi trở về Java; dọn sớm bằng `DeleteLocalRef` giúp tránh đầy local-reference table trong vòng lặp dài.

Ví dụ:

```c
jstring title = (*env)->NewStringUTF(env, "hello");
if (title == NULL) {
    return NULL; /* hợp với JNI function trả jobject/jstring */
}
jvalue arg[1] = {{0}};
arg[0].l = title;

/* ... CallObjectMethodA(..., arg) và kiểm tra exception ... */

(*env)->DeleteLocalRef(env, title);
```

Không dùng `title` sau khi đã xóa local ref. Không cất `jobject` của một local ref vào global C cache để thread khác gọi sau khi native method đã return; cần tạo **global reference** (`NewGlobalRef`) và giải phóng (`DeleteGlobalRef`) ở lifecycle phù hợp, đồng thời xử lý class-loader và thread attachment. `JNIEnv *` **không được chia sẻ giữa các native thread**; thread native tự attach vào VM để nhận `JNIEnv *` hợp lệ nếu cần callback.

### Ngoại lệ Java không biến thành error code C

`Call<Type>MethodA` hoặc `...V` có thể chạy Java method gây exception. JNI không “ném C exception”; nó tạo trạng thái **pending Java exception** trên thread. Sau lời gọi phải cân nhắc `ExceptionCheck(env)` hoặc `ExceptionOccurred` trước khi truy cập kết quả hay gọi các JNI APIs khác. Thao tác an toàn phổ biến là xóa các local refs đang giữ rồi return để exception được truyền về caller Java.

Không tự ý `ExceptionClear` chỉ để tiếp tục như chưa có lỗi; chỉ clear khi có hợp đồng bắt/đổi loại exception và sẽ thông báo lỗi một cách rõ ràng. Trong ví dụ runnable, đường lỗi return `NULL` với exception còn pending; Java nhận exception phù hợp.

### `jmethodID` không phải object reference

`jmethodID` là định danh opaque cho method đã resolve theo class, name, descriptor. Không gán nó vào `jvalue.l`; không quản lý bằng `DeleteLocalRef`. ID có hiệu lực theo vòng đời class được nạp; cache lâu dài cần cân nhắc class unloading và tham chiếu đến class/class loader. Với bridge nhiều class loader, không dùng cùng `jmethodID` cho một class khác dù tên method giống nhau.

### Không nên bỏ qua kiểm tra tham số

- Đọc mảng `jvalue` theo đúng số phần tử descriptor đòi hỏi; thiếu slot hoặc truy cập không khởi tạo có thể gây lỗi native khó đoán.
- Đảm bảo `jobject` receiver không phải `NULL` khi API yêu cầu object hợp lệ; static calls cần `jclass` hợp lệ.
- Không dùng `CallIntMethodA` cho method trả `long` hoặc `Object`.
- Đảm bảo `jvalue.l` là reference thuộc JVM hiện tại, không phải địa chỉ tùy ý hay reference đã hết hiệu lực.
- Với reference bị downcast, kiểm tra type khi thích hợp; JNI không tự biết “đây là một Java String” chỉ từ C union.
- Với JNI V, không lưu `va_list` để dùng bất đồng bộ sau khi hàm C đã thoát; `va_list` phải tuân đúng scope/ABI, `va_end` và `va_copy`.

## 9. Lỗi phổ biến và cách đọc triệu chứng

| Sai lầm | Hệ quả thường thấy | Cách sửa |
| --- | --- | --- |
| Gán `args[0].j` cho Java `int` | Khác kích thước/thành viên union, giá trị sai hoặc lỗi khó đoán | Dùng `args[0].i` cho descriptor `I` |
| Cho `jvalue[]` vào `Call...MethodV` bằng cast | `va_list` có layout ABI khác, có thể crash | Dùng `...MethodA`; không ép kiểu |
| Dùng `CallStaticIntMethodA` với `GetMethodID` của instance | Sai loại method ID/calling contract | Static → `GetStaticMethodID`, instance → `GetMethodID` |
| Dùng `CallIntMethodA` với method trả `long` | Return carrier sai | Chọn `CallLongMethodA` |
| Descriptor viết `(Ljava.lang.String;)V` | JNI class names dùng `/` và `L...;` | `(Ljava/lang/String;)V` |
| Constructor dùng `GetStaticMethodID("<init>", ...)` | Constructor không phải static method | `GetMethodID(clazz,"<init>","(...)V")` và `NewObjectA/V` |
| Java `String...` được đưa thành nhiều ô `jvalue` | JVM thấy duy nhất tham số `String[]` | Tạo `jobjectArray` và đưa vào một slot `.l` |
| Gọi `CallObjectMethodA` sau khi xóa `jstring` đầu vào | Java reference hết hợp lệ | Giữ local ref còn sống đến khi lời gọi kết thúc |
| Không kiểm tra pending exception trước JNI call tiếp theo | Có thể che nguyên nhân đầu tiên hoặc lỗi JNI khác | `ExceptionCheck`, dọn local refs, return hoặc xử lý rõ ràng |
| Lạm dụng `V` khi dữ liệu là mảng được chuẩn bị ở runtime | Khó tạo `va_list` portable | Dùng `A` với mảng union đã kiểm tra type |
| Cất `JNIEnv *`/local `jobject` để thread khác gọi | Sai thread/lifetime JNI | Attach thread để lấy env; tạo global ref nếu giữ object dài hạn |

**Khi lỗi không rõ:** chạy Java với `-Xcheck:jni` trên các JVM hỗ trợ tùy chọn này để phát hiện nhiều sai phạm JNI sớm hơn, nhưng không xem đây là bằng chứng chương trình native an toàn tuyệt đối. Dùng header do `javac -h` tạo, xem full Java exception/stack trace và kiểm tra chữ ký chính xác bằng `javap -s -p`.

## 10. Các câu hỏi tự kiểm tra

**1. Java method `long sum(int a, long b)` dùng A thì mảng nào đúng?**

```c
jvalue args[2] = {{0}, {0}};
args[0].i = (jint)3;
args[1].j = (jlong)4;
/* GetMethodID với "(IJ)J"; gọi CallLongMethodA(...) */
```

Vị trí 0 là `I`, vị trí 1 là `J`, kiểu trả `J` nên hàm gọi là `CallLongMethodA`.

**2. Có thể chuyển mảng `jvalue` thành `va_list` bằng cast không?**

Không. `jvalue[]` là dãy các union C; `va_list` mô tả trạng thái truyền varargs theo ABI và chỉ được tạo/quản lý qua `<stdarg.h>` trong bối cảnh phù hợp.

**3. Để gọi `static double price(String currency, int units)` cần gì?**

Dùng `GetStaticMethodID(clazz, "price", "(Ljava/lang/String;I)D")`, điền `args[0].l` bằng `jstring` hợp lệ và `args[1].i` bằng `jint`, rồi `CallStaticDoubleMethodA(env, clazz, mid, args)`; hoặc chuyển đúng danh sách C nếu dùng biến thể không hậu tố/V.

**4. `NewObjectA` và `CallObjectMethodA` có phải hoán đổi được không?**

Không. `NewObjectA` dùng method ID của constructor `<init>` để tạo instance mới. `CallObjectMethodA` gọi instance method có kiểu trả về reference, sau khi đã có receiver object.

**5. Dấu `...` trong Java `String... args` có liên quan trực tiếp tới `Call...MethodV` không?**

Không. Java varargs là **một tham số array** ở JVM bytecode; JNI V nhận **C `va_list`**. Chúng có tên na ná nhau nhưng dữ liệu và ABI khác nhau.

**6. Vì sao kết quả `CallIntMethodV` có vẻ hợp lý nhưng code vẫn sai?**

JNI/C ABI có thể tình cờ cho cùng số trong một môi trường; nếu truyền sai kiểu (đặc biệt `float`, `long`, pointer) hoặc dùng `jmethodID` không phù hợp, hành vi không được đảm bảo. Hãy xác minh descriptor, prototype và default promotions, không suy tính đúng đắn từ một lần chạy may mắn.

## Tài liệu chính thức và đối chiếu

- Oracle JNI Specification — *JNI Types and Data Structures*, khai báo `jvalue` và descriptor: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/types.html
- Oracle JNI Specification — *JNI Functions*, các nhóm `Call<Type>Method`, `Call<Type>MethodA/V`, static, nonvirtual và `NewObjectA/V`: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html
- Oracle JNI Specification — *Design Overview*, ngoại lệ và quy tắc JNI: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html
- Oracle `javac`, tùy chọn `-h` để sinh native headers: https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html
- GNU C Manual — `va_list`/`va_start`/`va_end` và default promotions: https://www.gnu.org/software/c-intro-and-ref/manual/html_node/Variable-Number-of-Arguments.html

**Ghi nhớ:** đúng `jmethodID` + đúng descriptor + đúng loại receiver/call + đúng giá trị đối số là điều kiện cốt lõi. Dùng **A** khi bạn đã có các slot kiểu `jvalue`, dùng **V** khi đang forward một `va_list` C hợp lệ, và dùng biến thể **không hậu tố** khi đối số được viết trực tiếp. Không tráo các representation với nhau, không bỏ qua ngoại lệ và lifetime của Java references.