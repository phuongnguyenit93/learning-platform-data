# Đăng ký phương thức bằng RegisterNatives thay cho tìm ký hiệu theo tên

## 1. Mục tiêu: hai cơ chế liên kết Java native method với hàm C

Trong **Java Native Interface (JNI)**, khai báo `native` trong class Java chỉ cho biết phần thân phương thức được thực thi bởi mã native. JVM còn phải biết **hàm native nào** ứng với từng phương thức Java. Có hai cách liên kết quan trọng:

1. **Tìm ký hiệu theo tên (name-based lookup):** thư viện export hàm mang tên theo quy tắc JNI, chẳng hạn `Java_demo_jni_RegisteredOps_doubleValue`. Khi cần giải quyết native method, JVM tìm symbol tương ứng trong thư viện native đã nạp.
2. **Đăng ký tường minh (explicit registration):** native code gọi `RegisterNatives`, truyền một bảng chứa **tên method Java, chữ ký JVM và con trỏ hàm C**. JVM ghi nhận ánh xạ này; các hàm triển khai C **không nhất thiết mang tên `Java_...` hoặc được export công khai**.

Bài này tập trung vào **`RegisterNatives` trong vòng đời JNI**: hình dạng `JNINativeMethod`, chữ ký, đăng ký vào đúng `jclass`, thời điểm dùng `JNI_OnLoad`, class loader, kiểm tra lỗi, rủi ro ABI, so sánh với name-based lookup và ví dụ Java 17 + C có thể biên dịch/chạy trên Linux, macOS, Windows.

**Không nhầm hai việc:** `RegisterNatives` thay thế **cách tìm hàm C cho native method**, chứ **không thay thế `System.loadLibrary` hoặc `System.load`**. Trước khi code trong thư viện có thể đăng ký phương thức, thư viện đó vẫn phải được JVM nạp phù hợp.

## 2. Cách liên kết mặc định: ký hiệu `Java_...`

Nếu không đăng ký tường minh, một khai báo như:

~~~java
package demo.jni;

public final class NamedExample {
    public static native int doubleValue(int value);
}
~~~

có thể được JNI liên kết với symbol C kiểu:

~~~c
JNIEXPORT jint JNICALL Java_demo_jni_NamedExample_doubleValue(
    JNIEnv *env, jclass clazz, jint value
) {
    (void) env;
    (void) clazz;
    return value * 2;
}
~~~

Đây là **hai trích đoạn minh họa**, chưa phải chương trình chạy độc lập (chưa có bước nạp thư viện và `main`).

Vì phương thức Java có `static`, đối số JNI ẩn thứ hai là `jclass`. Nếu là instance native method, vị trí ấy là `jobject`. `JNIEXPORT` giúp export symbol, còn `JNICALL` chọn calling convention JNI tương ứng nền tảng.

Cách tự động này tiện khi học JNI và dễ so khớp với header do `javac -h` sinh. Tuy nhiên, tên ký hiệu trở nên dài hoặc khó đọc khi class có package, phương thức chứa dấu gạch dưới/Unicode, lớp lồng nhau, hay nhiều overload. Một lần đổi package/tên có thể làm symbol cũ không còn khớp, dẫn tới `UnsatisfiedLinkError` khi lời gọi cần giải quyết native method.

**`RegisterNatives` giải quyết trực tiếp bài toán ánh xạ** bằng một bảng đăng ký thay vì đặt quy ước tên C lên từng hàm triển khai.

## 3. API RegisterNatives và cấu trúc JNINativeMethod

Chữ ký từ JNI C API:

~~~c
jint RegisterNatives(
    JNIEnv *env,
    jclass clazz,
    const JNINativeMethod *methods,
    jint nMethods
);
~~~

Đây là **prototype để giải thích**, không phải hàm do chúng ta tự định nghĩa; trong code JNI C thực tế gọi qua:

~~~c
jint rc = (*env)->RegisterNatives(env, clazz, methods, count);
~~~

Các tham số:

| Tham số | Ý nghĩa |
|---|---|
| `env` | `JNIEnv *` của thread hiện tại, sử dụng đúng thread |
| `clazz` | `jclass` biểu thị **class Java có các native methods cần đăng ký** |
| `methods` | Con trỏ đến bảng `JNINativeMethod`, không được `NULL` |
| `nMethods` | Số phần tử trong bảng, phải lớn hơn 0 |

Khi thành công, API trả **`JNI_OK` (= 0)**. Khi thất bại, trả **mã âm**. Nếu một mục chỉ tới method không tồn tại hoặc không được khai báo `native`, JNI có thể ném **`NoSuchMethodError`**. Không được coi giá trị trả về khác 0 là “đã đăng ký một phần đủ dùng”. Với bảng đăng ký lỗi, nên dừng quá trình khởi tạo và sửa khai báo/chữ ký thay vì cố chạy tiếp.

Cấu trúc JNI:

~~~c
typedef struct {
    char *name;
    char *signature;
    void *fnPtr;
} JNINativeMethod;
~~~

Đây là hình dạng theo đặc tả; `jni.h` đã khai báo kiểu, vì vậy **không chép lại typedef** vào chương trình thật.

- **`name`:** tên phương thức **Java nguyên gốc**, ví dụ `"addBias"`, **không phải** `"Java_demo_jni_RegisteredOps_addBias"`.
- **`signature`:** **method descriptor JVM đầy đủ**, chẳng hạn `"(I)I"`: nhận một `int`, trả `int`. Trong descriptor method, phần kiểu trả về là bắt buộc.
- **`fnPtr`:** con trỏ hàm native có **JNI ABI đúng** cho method đó, bao gồm `JNIEnv *`, receiver `jobject`/`jclass` và toàn bộ các tham số khai báo Java.

Theo đặc tả, chuỗi `name` và `signature` trong bảng là **modified UTF-8**. Tên ASCII và descriptor trong ví dụ dùng ký tự ASCII, nên không có vấn đề mã hóa đặc biệt.

Ví dụ hai entry:

~~~c
static JNINativeMethod methods[] = {
    {"addBias",     "(I)I", (void *) add_bias_impl},
    {"doubleValue", "(I)I", (void *) double_value_impl}
};
~~~

Đây là trích đoạn; `add_bias_impl` và `double_value_impl` sẽ được định nghĩa đầy đủ ở phần thực hành. Không lấy tên C trong `fnPtr` làm tên Java: ánh xạ được quyết định bởi hai chuỗi `name` + `signature` nằm cùng entry.

Một compiler C dùng kiểu `void *` cho trường `fnPtr` theo giao diện JNI. Việc biểu diễn function pointer dưới dạng `void *` là quy ước ABI của JNI trên các nền tảng được hỗ trợ; tránh tự phát minh typedef hoặc gọi hàm qua một kiểu con trỏ không khớp.

## 4. Chữ ký JVM: sai một ký tự là một method khác

**Method descriptor** có dạng:

~~~text
(<descriptor các tham số theo thứ tự>)<descriptor kiểu trả về>
~~~

Bảng thông dụng:

| Kiểu Java | Descriptor |
|---|---|
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `void` (trả về) | `V` |
| `String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |

Ví dụ:

| Java declaration | Method descriptor đăng ký |
|---|---|
| `native int addBias(int x)` | `(I)I` |
| `static native int doubleValue(int x)` | `(I)I` |
| `static native void send(String message)` | `(Ljava/lang/String;)V` |
| `native long sum(int[] values)` | `([I)J` |
| `static native String format(int n, String prefix)` | `(ILjava/lang/String;)Ljava/lang/String;` |

Dấu `/` trong tên class của descriptor là **dấu phân cách nội bộ JVM**, không phải separator tệp trên Linux hay Windows. `String` viết là `Ljava/lang/String;`, không viết `java.lang.String`. Descriptor `(I)I` **không tự chứa** `JNIEnv *` hoặc receiver, vì hai tham số ấy thuộc chữ ký C JNI, không thuộc các tham số Java được khai báo.

**Instance/static không được nhận biết chỉ bằng descriptor.** Cả `addBias(int)` và `doubleValue(int)` đều có `(I)I`, nhưng hàm C của instance phải nhận **`jobject self`**, còn static phải nhận **`jclass clazz`**. `RegisterNatives` không sửa được một hàm C dùng sai calling convention/kiểu tham số; mapping chỉ hoạt động đúng khi con trỏ hàm khớp JNI ABI.

### 4.1. Overload không cần JNI long-name mangling

Giả sử class có:

~~~java
public static native int transform(int x);
public static native long transform(long x);
~~~

Đây là **trích đoạn độc lập**, không thuộc class thực hành bên dưới. Bảng đăng ký có thể mô tả:

~~~c
static JNINativeMethod overloaded[] = {
    {"transform", "(I)I", (void *) transform_int_impl},
    {"transform", "(J)J", (void *) transform_long_impl}
};
~~~

Hai entry có **cùng tên Java nhưng descriptor khác nhau**. Không cần đặt tên C dạng dài có hậu tố escaped descriptor như `Java_..._transform__I` và `Java_..._transform__J`, miễn bảng được đăng ký đúng. Hai hàm C cũng phải có kiểu trả về và tham số thực sự phù hợp: `jint`/`jlong` tương ứng.

Điều này đặc biệt hữu ích khi class có tên phức tạp, nhưng không có nghĩa có thể đăng ký bất kỳ Java method thường nào: **mục tiêu là method được khai báo `native`**. `RegisterNatives` tìm method theo cặp tên + descriptor trong **class `clazz` được truyền vào**.

## 5. Chọn thời điểm đăng ký trong vòng đời thư viện JNI

Để phương thức native có thể gọi được, phải đăng ký **trước khi lần gọi Java cần thực thi nó**. Có hai thiết kế cơ bản.

### 5.1. Đăng ký trong `JNI_OnLoad` — thường thuận tiện

Thư viện native có thể export hook:

~~~c
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved);
~~~

`JNI_OnLoad` là **hook tùy chọn** mà JVM gọi khi nạp thư viện động bằng `System.loadLibrary`/`System.load`. Ta có thể dùng hook để:

1. Nhận `JavaVM *vm` từ JVM; dùng `GetEnv` lấy `JNIEnv *` hợp lệ cho thread nạp.
2. Dùng `FindClass` lấy đúng `jclass` của class chứa native methods.
3. Chuẩn bị bảng `JNINativeMethod` và gọi `RegisterNatives`.
4. Xóa local class reference nếu không cần giữ.
5. Khi thành công, trả hằng `JNI_VERSION_1_6`; nếu khởi tạo/đăng ký thất bại, báo thất bại theo hợp đồng `JNI_OnLoad` (ví dụ trả `JNI_ERR`).

Ví dụ sơ đồ:

~~~text
JVM khởi tạo class RegisteredOps
  |
  | static { System.loadLibrary("registeredops"); }
  v
JVM nạp thư viện registeredops
  |
  v
JNI_OnLoad(JavaVM*, void*)
  |
  +--> GetEnv --> JNIEnv*
  +--> FindClass("demo/jni/RegisteredOps") --> jclass
  +--> RegisterNatives(clazz, methods, 2) --> JNI_OK
  +--> DeleteLocalRef(clazz)
  +--> return JNI_VERSION_1_6
  |
  v
Quá trình nạp thư viện thành công
  |
  v
Java gọi RegisteredOps.doubleValue(5)
  |
  v
JVM dùng function pointer đã đăng ký
  |
  v
double_value_impl(env, clazz, 5) --> 10
~~~

`JNI_VERSION_1_6` là **phiên bản giao diện JNI mà thư viện yêu cầu**, **không phải “Java SE 6” phải được cài**. JDK 17 nhận biết hằng JNI này. Cần include `<jni.h>` và dùng đúng các macro của nền tảng.

**Không nhầm `JNI_OnLoad` với Java static initializer:** static initializer gọi `System.loadLibrary`; trong quá trình nạp đó, JVM gọi `JNI_OnLoad`. Hook là hàm C được export bởi thư viện và là nơi đăng ký; không cần một Java native bootstrap method riêng trong mô hình này.

### 5.2. Đăng ký từ một native bootstrap method

Một lựa chọn khác: export một hàm JNI theo tên (hoặc một entrypoint đã có cơ chế liên kết), Java gọi nó để thực hiện `RegisterNatives` cho các method còn lại. Thiết kế này có thể hữu ích nếu cần chọn tập hàm theo cấu hình runtime.

Tuy nhiên, **vẫn phải có một entrypoint đã gọi được** để bắt đầu đăng ký. Nếu tất cả Java native methods đều chưa có symbol/registration và `JNI_OnLoad` cũng không đăng ký, thì gọi một method sẽ không thể tự “ma thuật” tìm được con trỏ hàm chưa từng khai báo.

Đăng ký tại `JNI_OnLoad` giúp các method cần dùng đã được ánh xạ **trước** lời gọi đầu tiên và sai tên/signature thường được phát hiện **sớm trong giai đoạn nạp**, thay vì chờ tới lần gọi method gây `UnsatisfiedLinkError`.

## 6. Ví dụ hoàn chỉnh: Java 17 + C, hai native methods đăng ký tường minh

Ví dụ sẽ chứng minh ba điều:

- Một **instance native method** nhận `jobject` và đọc field riêng của từng đối tượng.
- Một **static native method** nhận `jclass`.
- Cả hai hàm C đều có **tên thông thường**, được khai báo `static` trong C, **không export `Java_...`**; JVM vẫn gọi được nhờ bảng `RegisterNatives` được thực hiện trong `JNI_OnLoad`.

Cấu trúc:

~~~text
register-natives-demo/
├── src/
│   └── demo/jni/
│       └── RegisteredOps.java
├── registeredops.c
└── build/
    └── classes/                 (javac tạo)
        └── demo/jni/
            └── RegisteredOps.class
~~~

Các thư viện động `registeredops.dll`, `libregisteredops.so` hoặc `libregisteredops.dylib` được tạo trong thư mục gốc bởi compiler tương ứng. **Không có yêu cầu phải sinh header `Java_...` để triển khai code bên dưới**, vì C functions được đăng ký bằng pointer thay vì được lookup theo tên export.

### 6.1. Java — `src/demo/jni/RegisteredOps.java`

~~~java
package demo.jni;

public final class RegisteredOps {
    static {
        System.loadLibrary("registeredops");
    }

    private final int bias;

    public RegisteredOps(int bias) {
        this.bias = bias;
    }

    public native int addBias(int value);

    public static native int doubleValue(int value);

    public static void main(String[] args) {
        RegisteredOps first = new RegisteredOps(7);
        RegisteredOps second = new RegisteredOps(-2);

        System.out.println("instance A = " + first.addBias(5));
        System.out.println("instance B = " + second.addBias(5));
        System.out.println("static = " + RegisteredOps.doubleValue(5));
    }
}
~~~

Giải thích:

- `addBias` là method **instance**; `first` và `second` có field `bias` riêng nên cùng tham số 5 nhưng kết quả khác.
- `doubleValue` là method **static**; gọi bằng tên class, không có receiver instance `this` ngầm định.
- Khối `static` nạp thư viện logic `registeredops` khi class được khởi tạo. Trước khi lời gọi native đầu tiên xảy ra, JVM đã có cơ hội gọi `JNI_OnLoad` và thực hiện registration.
- Nếu nạp/đăng ký thư viện thất bại, khởi tạo class hoặc lời gọi native sẽ không thể thành công; chương trình không được giả vờ đã có implementation chỉ vì `javac` biên dịch được.

### 6.2. C — `registeredops.c`

~~~c
#include <jni.h>

/* Instance implementation: tham số thứ hai là jobject self. */
static jint JNICALL add_bias_impl(
    JNIEnv *env, jobject self, jint value
) {
    jclass clazz = (*env)->GetObjectClass(env, self);
    if (clazz == NULL) {
        return 0; /* Pending Java exception nếu lookup thất bại. */
    }

    jfieldID field = (*env)->GetFieldID(
        env, clazz, "bias", "I"
    );

    /* clazz là local reference, không cần giữ sau GetFieldID. */
    (*env)->DeleteLocalRef(env, clazz);

    if (field == NULL) {
        return 0; /* GetFieldID có thể để lại Java exception. */
    }

    jint bias = (*env)->GetIntField(env, self, field);
    return value + bias;
}

/* Static implementation: tham số thứ hai là jclass clazz. */
static jint JNICALL double_value_impl(
    JNIEnv *env, jclass clazz, jint value
) {
    (void) env;
    (void) clazz;
    return value * 2;
}

/* Khai báo method Java -> descriptor JVM -> con trỏ hàm C. */
static JNINativeMethod methods[] = {
    {"addBias",     "(I)I", (void *) add_bias_impl},
    {"doubleValue", "(I)I", (void *) double_value_impl}
};

/* Hook duy nhất cần export để đăng ký các native implementations. */
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void) reserved;

    JNIEnv *env = NULL;

    if ((*vm)->GetEnv(
            vm, (void **) &env, JNI_VERSION_1_6
        ) != JNI_OK) {
        return JNI_ERR;
    }

    jclass clazz = (*env)->FindClass(
        env, "demo/jni/RegisteredOps"
    );
    if (clazz == NULL) {
        return JNI_ERR; /* Class lookup thất bại. */
    }

    jint count = (jint) (sizeof(methods) / sizeof(methods[0]));
    jint rc = (*env)->RegisterNatives(
        env, clazz, methods, count
    );

    (*env)->DeleteLocalRef(env, clazz);

    if (rc != JNI_OK) {
        /* Registration không hợp lệ: không hoàn tất loading. */
        return JNI_ERR;
    }

    return JNI_VERSION_1_6;
}
~~~

Đây là **tệp C đầy đủ** cho ví dụ. Không có hàm nào tên `Java_demo_jni_RegisteredOps_addBias` hoặc `Java_demo_jni_RegisteredOps_doubleValue`, và hai hàm triển khai C được khai báo `static` để giữ phạm vi liên kết trong translation unit. JVM vẫn biết đường gọi tới chúng vì bảng `methods` giữ đúng con trỏ hàm.

**Các chi tiết phải khớp tuyệt đối:**

1. `FindClass(env, "demo/jni/RegisteredOps")` dùng **tên nội bộ JVM với slash `/`**, không dùng tên package dấu chấm trong chuỗi C.
2. `"addBias"` và `"doubleValue"` là **tên Java chính xác**, viết đúng hoa/thường; không thêm tiền tố `Java_`.
3. Cả hai Java methods là `int method(int)` nên descriptor đều là `"(I)I"`. `static` không xuất hiện trong descriptor.
4. `add_bias_impl(JNIEnv*, jobject, jint)` nhận receiver; `double_value_impl(JNIEnv*, jclass, jint)` nhận class. Đăng ký sai receiver type có thể gây lỗi ABI khó phát hiện hoặc crash.
5. `JNINativeMethod.fnPtr` trỏ đến **địa chỉ hàm thật**; method không tự động liên kết chỉ vì chuỗi name/signature đúng.
6. `RegisterNatives` được kiểm tra kết quả; nếu thất bại, `JNI_OnLoad` không trả version thành công.
7. `DeleteLocalRef(clazz)` xóa **handle local** dùng để đăng ký. Nó **không hủy bảng ánh xạ đã đăng ký** và không xóa class khỏi JVM. Không giữ `clazz` như một con trỏ C dùng về sau sau khi local reference hết hiệu lực.
8. `GetFieldID` lấy instance field `bias` với descriptor `I`. Nếu không tìm thấy field, có thể để lại pending exception, và hàm instance trả về để JVM xử lý ngoại lệ.
9. Các hàm triển khai dùng phép cộng/nhân các số nhỏ; trong bài toán thật nên xét overflow khi chuyển qua ranh giới C/Java thay vì ngầm giả định mọi giá trị `jint` đều tính toán như Java nếu C có signed overflow.

**Vì sao không include header do `javac -h` sinh?** Header đó thường khai báo tên C theo quy tắc `Java_...` để phục vụ **name-based lookup**. Với bảng đăng ký, implementation tự dùng tên riêng và cần bảo đảm chữ ký phù hợp JNI; `jni.h` là header bắt buộc. Có thể sinh header **để đối chiếu** nhưng không nhất thiết include header hay export những tên `Java_...` trong ví dụ này.

### 6.3. Compile Java và kiểm tra descriptor

Từ thư mục gốc `register-natives-demo`:

**Linux/macOS (shell):**

~~~bash
mkdir -p build/classes
javac -d build/classes src/demo/jni/RegisteredOps.java
javap -s -p -classpath build/classes demo.jni.RegisteredOps
~~~

**Windows Command Prompt:**

~~~bat
if not exist build\classes mkdir build\classes
javac -d build\classes src\demo\jni\RegisteredOps.java
javap -s -p -classpath build\classes demo.jni.RegisteredOps
~~~

Trong đầu ra `javap`, tìm hai native method và dòng descriptor `(I)I`. Đầu ra `javap` còn chứa constructor, field, `main` và `static initializer`; không nên sao chép toàn bộ kết quả vào bảng `JNINativeMethod`. Chỉ **tên và descriptor của từng native method** cần khớp.

Nếu muốn dùng `javac -h` để kiểm tra declaration, bạn **có thể** thay lệnh compile Java bằng:

~~~bash
javac -h build -d build/classes src/demo/jni/RegisteredOps.java
~~~

Lệnh này sinh thêm header dựa trên khai báo Java; nó không thay đổi cơ chế liên kết của thư viện `registeredops.c`. Trong bài thực hành, header đó chỉ là công cụ đối chiếu, **không phải điều kiện bắt buộc** để registration hoạt động.

### 6.4. Build thư viện C và chạy

Biến môi trường `JAVA_HOME` cần trỏ tới JDK 17+ có thư mục `include`. Compiler phải tạo thư viện đúng nền tảng, CPU, bitness và ABI của **tiến trình JVM**. Chỉ dùng một bộ lệnh phù hợp với OS.

**Linux (GCC):**

~~~bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  registeredops.c -o libregisteredops.so

java -Djava.library.path=. -cp build/classes demo.jni.RegisteredOps
~~~

**macOS (Clang):**

~~~bash
cc -dynamiclib -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  registeredops.c -o libregisteredops.dylib

java -Djava.library.path=. -cp build/classes demo.jni.RegisteredOps
~~~

**Windows (MSVC trong Developer Command Prompt, cmd.exe):**

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" registeredops.c /Fe:registeredops.dll

java -Djava.library.path=. -cp build\classes demo.jni.RegisteredOps
~~~

Lệnh `-Djava.library.path=.` phải nằm trước tên class, để JVM tìm thư viện tại thư mục đang đứng. `System.loadLibrary("registeredops")` dùng tên logic `registeredops`, không thêm `lib` hay đuôi `.dll`/`.so`/`.dylib`.

**Stdout chính xác khi build, nạp và đăng ký thành công:**

~~~text
instance A = 12
instance B = 3
static = 10
~~~

Giải thích:

- `first.addBias(5)` đọc field `bias = 7` từ receiver đầu tiên, trả `5 + 7 = 12`.
- `second.addBias(5)` đọc `bias = -2` từ receiver thứ hai, trả `5 + (-2) = 3`.
- `RegisteredOps.doubleValue(5)` không có receiver instance, trả `5 * 2 = 10`.

Mã C chỉ export hook `JNI_OnLoad` và không cần export hai tên `Java_...` của native implementations. Đó là bằng chứng thực hành cho thấy **registration thay thế name-based symbol lookup** đối với hai method, trong khi **thư viện vẫn được JVM nạp bình thường**.

## 7. Vì sao JNI_OnLoad và class loader liên quan trực tiếp đến RegisterNatives?

### 7.1. FindClass trong JNI_OnLoad dùng loader của class nạp thư viện

Khi gọi `FindClass` **từ `JNI_OnLoad`**, JVM chọn **class loader của class đang nạp native library**. Trong ví dụ, `RegisteredOps` gọi `System.loadLibrary` từ static initializer, nên `FindClass("demo/jni/RegisteredOps")` tìm đúng class trong ngữ cảnh loader đó.

Đây là khác biệt quan trọng so với `FindClass` trên **native thread mới attach** mà không có Java frame thích hợp: trong bối cảnh khác, `FindClass` có thể tìm bằng **system class loader** và không thấy class chỉ tồn tại trong custom loader.

Để đăng ký đúng, phải có **`jclass` của class thực tế**. Cùng tên `demo.jni.RegisteredOps` nhưng được nạp bởi hai class loader độc lập có thể là **hai Java class identity khác nhau**. Chỉ khớp tên chuỗi không đồng nghĩa đăng ký được cho mọi bản sao class ở mọi loader.

### 7.2. Thư viện native được quản lý theo class loader

Trên JNI thông thường, **một thư viện JNI không được nạp vào nhiều class loaders khác nhau cùng lúc**. JVM có thể ném `UnsatisfiedLinkError` nếu một thư viện JNI đã được liên kết với loader này lại được nạp từ loader khác. Đây là cơ chế giữ ranh giới namespace và tránh trộn class không tương thích.

Vì thế, kiến trúc plugin/hot reload dùng nhiều loaders cần thiết kế thư viện/registration cẩn thận. Không nên giả định rằng một lần `RegisterNatives` theo tên class là “đăng ký toàn JVM” cho mọi class loader.

### 7.3. Khi nào registration tồn tại và khi nào cleanup?

Registration kết nối các native methods **của class `clazz`** với hàm C đã cung cấp. Nó không phải thao tác chỉ có hiệu lực cho **một lần gọi**; sau khi đăng ký thành công, các lời gọi tiếp theo dùng ánh xạ ấy theo vòng đời class/native library.

`JNI_OnLoad` chạy **khi thư viện được nạp**, không chạy ở mỗi lần gọi native method. Vì thế bảng C khai báo `static JNINativeMethod methods[]` phù hợp cho ví dụ. Các hàm C mà con trỏ trỏ đến phải tiếp tục tồn tại và có ABI đúng **suốt thời gian JVM còn có thể gọi tới chúng**.

Nếu class loader có thể được GC và native library được unload, `JNI_OnUnload(JavaVM*, void*)` là hook tùy chọn để dọn tài nguyên native do thư viện sở hữu. Đừng coi việc GC/unload xảy ra theo một thời điểm chắc chắn. `JNI_OnUnload` cũng chạy trong bối cảnh không nên tùy tiện gọi Java callbacks.

### 7.4. UnregisterNatives không phải bước cuối bắt buộc

JNI cung cấp:

~~~c
jint UnregisterNatives(JNIEnv *env, jclass clazz);
~~~

API này đưa các native methods của class về trạng thái trước khi được liên kết/đăng ký. Theo đặc tả, nó **không được khuyến khích dùng trong native code bình thường**; chủ yếu phục vụ các chương trình đặc biệt cần relink/reload.

Đừng tự động gọi `UnregisterNatives` sau khi `RegisterNatives` thành công hoặc sau mỗi lời gọi Java: như vậy có thể làm mất mapping trước khi các lời gọi khác sử dụng. Nếu thực sự triển khai cơ chế thay đổi registration động, cần có **đồng bộ lifecycle** để không làm thay đổi con trỏ hàm khi những thread khác đang sử dụng chúng.

## 8. So sánh RegisterNatives và tìm ký hiệu theo tên

| Tiêu chí | Name-based symbol lookup | RegisterNatives |
|---|---|---|
| Java declaration | Vẫn khai báo `native` | Vẫn khai báo `native` |
| C function name | Theo quy tắc `Java_package_Class_method...` | Tên C do người viết chọn |
| Export từng implementation | Thường cần export đúng symbol JNI | Implementation có thể để `static`/ẩn; cần entrypoint có thể thực hiện registration |
| Cách khớp overload | Short/long mangled name có hậu tố parameter | Cặp `name` + **method descriptor đầy đủ** |
| Nơi tạo mapping | JVM tìm symbol khi giải quyết native method | Native code chủ động gọi `RegisterNatives` |
| Thời điểm phát hiện sai mapping | Thường lúc JVM cần resolve method | Thường tại bước đăng ký nếu gọi ngay trong `JNI_OnLoad` |
| Phụ thuộc class loader | Có, trong quá trình load/lookup | Có, vì đăng ký lên **`jclass` cụ thể** |
| Dễ debug | Có thể xem export table và `javac -h` | Cần kiểm tra entries, descriptor, function pointer, kết quả registration |
| Rủi ro chính | Sai tên/escaping/overload suffix | Sai descriptor, receiver ABI, method không `native`, đăng ký nhầm class |
| Nạp native library | Vẫn cần | **Vẫn cần** |

Không nên coi một bên luôn tốt hơn bên còn lại. Với ví dụ nhỏ và ít method, name-based lookup đơn giản, trực quan. Với thư viện nhiều native methods, API ổn định hoặc muốn kiểm soát việc ánh xạ, `RegisterNatives` giúp tách tên C khỏi tên Java, hỗ trợ kiểm tra sớm tại lúc nạp và có thể giảm yêu cầu export nhiều symbols.

**Giới hạn quan trọng:** RegisterNatives không phải “API sandbox” hay cơ chế bảo mật. Một thư viện native được tin cậy không đúng cách có thể thay đổi việc thực thi native methods. Không đăng ký từ nguồn không đáng tin, không tải binary chưa kiểm soát provenance và không sử dụng registration để thay thế các method nhạy cảm ngoài hợp đồng ứng dụng.

## 9. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách chẩn đoán và sửa |
|---|---|---|
| `NoSuchMethodError` khi `RegisterNatives` | Sai `name`, descriptor, class hoặc method không khai báo `native` | Đối chiếu Java source và `javap -s -p`; kiểm tra đúng `jclass` |
| `UnsatisfiedLinkError` khi gọi method | Chưa load thư viện, chưa đăng ký, hoặc name-based lookup cũng không tìm symbol | Bảo đảm `JNI_OnLoad` được export/called, registration trả `JNI_OK` |
| Nạp thư viện lỗi ngay ở static initializer | `JNI_OnLoad` trả version không hợp lệ/`JNI_ERR` hoặc lỗi nạp dependency | Kiểm tra kết quả `GetEnv`, `FindClass`, `RegisterNatives` và tên thư viện |
| `FindClass` không tìm thấy class | Sai dấu `/`, package, loader hoặc binary chưa nằm trong classpath | Dùng internal name `demo/jni/RegisteredOps`; xem `-cp build/classes` |
| `RegisterNatives` trỏ nhầm hàm C | Mục `fnPtr` sai, signature Java/C không khớp | So sánh đầy đủ return type, receiver, loại tham số và thứ tự |
| C nhận `jclass` thay `jobject` cho instance | Dùng sai chữ ký JNI ABI | Instance → `jobject`; static → `jclass` |
| C gặp crash/`hs_err_pid...log` | Native pointer/ABI sai, JNI ref hết hạn, lỗi bộ nhớ | Rà soát C prototype, JNI refs; dùng kiểm tra JNI, đọc native stack |
| Hệ điều hành không tìm được `JNI_OnLoad` | Hook không export hoặc bị C++ name mangling | Dùng `JNIEXPORT`/`JNICALL`; với C++ đảm bảo linkage C |
| `NoSuchMethodError` khi overload | Descriptor bị thiếu `( ... )Return` hoặc lấy nhầm tham số | Dùng `javap -s -p`, đăng ký từng cặp name + descriptor |
| Một thư viện bị load từ hai class loaders | Ràng buộc thư viện theo class loader | Thiết kế lại cách phân phối library/class loader thay vì gọi `System.loadLibrary` trùng |
| Dùng `JNIEnv *` của thread khác | JNI environment là thread-specific | Mỗi native thread phải attach đúng và lấy environment riêng |
| Giữ `jclass` local lâu dài | Local ref không có vòng đời toàn thư viện | Nếu cache, tạo global ref và cleanup ở nơi thích hợp |

### 9.1. Kiểm tra symbol export

**Linux:**

~~~bash
nm -D libregisteredops.so | grep JNI_OnLoad
~~~

**macOS:**

~~~bash
nm -g libregisteredops.dylib
~~~

**Windows (Visual Studio Developer Command Prompt):**

~~~bat
dumpbin /EXPORTS registeredops.dll
~~~

Các lệnh là ví dụ kiểm tra bảng symbol; tên/ký hiệu trang trí có thể khác theo nền tảng/compiler. Cần xác minh **`JNI_OnLoad` là entrypoint được export**. Không nhất thiết nhìn thấy `add_bias_impl` hoặc `double_value_impl` trong bảng export vì chúng được khai báo `static` và JVM gọi qua function pointers sau khi registration.

`-Xcheck:jni` của HotSpot có thể giúp phát hiện một số cách dùng JNI sai:

~~~bash
java -Xcheck:jni -Djava.library.path=. -cp build/classes demo.jni.RegisteredOps
~~~

Đây là chế độ chẩn đoán (không bảo đảm phát hiện mọi lỗi C/ABI). Nếu chương trình chạy đúng, stdout ứng dụng vẫn gồm ba dòng `instance A = 12`, `instance B = 3`, `static = 10`.

### 9.2. Vì sao JNI_OnLoad thất bại cần được xử lý nghiêm túc?

Nếu `FindClass` không ra class đích hoặc `RegisterNatives` trả mã âm, không nên trả `JNI_VERSION_1_6` như thể initialization đã thành công. Khi làm vậy, Java có thể đi tiếp trong trạng thái chưa có mapping đúng và chỉ lỗi muộn ở lần gọi method.

Trả `JNI_ERR` giúp biểu thị thất bại trong quá trình nạp. Ngoại lệ/cách mô tả lỗi cụ thể mà Java nhìn thấy phụ thuộc tình huống và JVM; đừng giả định mọi lỗi sẽ có cùng message. Với ứng dụng production, nên ghi chẩn đoán phù hợp và kiểm tra exception đang pending trước khi tiếp tục gọi thêm các JNI APIs; không tự clear lỗi rồi báo thành công giả.

Nếu triển khai retry/re-registration, phải phân biệt lỗi có thể phục hồi với sai chữ ký/cấu hình. Không dựa vào giả định mọi entry trong bảng được rollback tự động nếu một entry thất bại: thiết kế registration theo một tập nhất quán, kiểm tra kết quả, và từ chối tiếp tục khi trạng thái không đạt yêu cầu.

## 10. Khi dùng C++ thay vì C

JNI có hai cách gọi API tùy ngôn ngữ:

~~~c
/* C: hàm JNI lấy qua bảng function pointers. */
jint rc = (*env)->RegisterNatives(env, clazz, methods, count);
~~~

~~~cpp
// C++: JNIEnv là wrapper với member methods.
jint rc = env->RegisterNatives(clazz, methods, count);
~~~

Đây chỉ là **hai trích đoạn cú pháp**, không phải hai chương trình hoàn chỉnh.

Với C++, phải bảo đảm export `JNI_OnLoad` bằng **C linkage**, ví dụ:

~~~cpp
extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(
    JavaVM *vm, void *reserved
) {
    // Triển khai GetEnv, FindClass, RegisterNatives tương ứng.
    return JNI_VERSION_1_6;
}
~~~

Trích đoạn này **chưa đăng ký method**, chỉ minh họa linkage. Nếu `JNI_OnLoad` bị C++ name-mangle thành một tên symbol khác, JVM có thể không gọi hook dự kiến, dẫn đến thiếu registration. Các function implementations có thể là static C++ functions miễn có kiểu gọi phù hợp và được đưa vào `fnPtr` đúng cách.

Nếu dùng instance method của C++ object làm function pointer, cần nhớ non-static member function có receiver C++ ẩn nên **không khớp** dạng callback JNI thông thường. Hãy dùng static/free function làm JNI entrypoint, rồi điều phối sang C++ object phía trong theo thiết kế riêng.

## 11. Thiết kế nâng cao: nhiều class và nhiều phương thức

### 11.1. Nhiều method trong một class

Có thể dùng cùng một bảng cho các native methods **trong cùng class `clazz`**, với `nMethods` đúng số phần tử. Mỗi mục cần tên, descriptor và con trỏ hàm riêng.

Tuy nhiên, nếu số method lớn, nên tách hàm chuẩn bị/đăng ký cho dễ review, tránh nhầm tên/descriptor. Đăng ký là phần **liên kết runtime**, vì vậy sai một mục có thể khiến quá trình nạp thất bại thay vì chỉ làm hỏng một trường hợp hiếm.

### 11.2. Nhiều class trong cùng thư viện

Nếu một thư viện triển khai native methods cho nhiều Java classes, có thể:

1. Tìm class A bằng `FindClass`, đăng ký bảng A lên `jclass A`.
2. Tìm class B bằng `FindClass`, đăng ký bảng B lên `jclass B`.
3. Xóa local references khi xong.
4. Chỉ báo `JNI_OnLoad` thành công khi **tất cả các đăng ký bắt buộc** thành công.

Không truyền method thuộc class B vào `RegisterNatives(env, classA, ...)` và mong JVM “tự tìm sang class khác”. `clazz` là phạm vi đăng ký cụ thể.

Cần chú ý loader visibility và **thứ tự khởi tạo class**: trong `JNI_OnLoad`, đừng tự phát gọi Java method có thể dẫn tới khởi tạo class lặp hoặc nạp lại thư viện. Mẫu ví dụ chỉ gọi `FindClass` và `RegisterNatives` để tránh side effects không cần thiết.

### 11.3. Cache thông tin JNI sau OnLoad

Có thể cache `jmethodID`, `jfieldID` hoặc `jclass` để tránh lookup nhiều lần, nhưng phải tuân thủ vòng đời:

- `jclass` trả từ `FindClass` là **local reference**; muốn giữ qua native calls/threads phải tạo `NewGlobalRef` và giải phóng bằng `DeleteGlobalRef` khi phù hợp.
- `jmethodID`/`jfieldID` không phải local references; không gọi `DeleteLocalRef` lên chúng. Hiệu lực gắn với class tương ứng, nên không dùng sau khi class bị unload.
- `JNIEnv *` thuộc **thread hiện tại**; không cache một `JNIEnv *` rồi chia sẻ giữa các thread. `JavaVM *` có thể dùng để attach/get môi trường cho thread theo hợp đồng JNI.
- Không để global references khiến class loader không thể thu gom ngoài ý muốn; nếu cache class global, phải có kế hoạch release.

Ví dụ đơn giản ở phần 6 cố ý **không cache `jclass`**. Hook đăng ký xong rồi xóa local reference, không tạo tài nguyên toàn cục cần dọn.

## 12. Bài tập tự kiểm tra

1. `RegisterNatives` thay thế bước nào trong quá trình liên kết Java ↔ C? Nó có thay thế `System.loadLibrary` không?
2. Ba trường của `JNINativeMethod` là gì? Với `native long sum(int[] data)`, method descriptor đúng là gì?
3. Vì sao hai method `addBias(int)` (instance) và `doubleValue(int)` (static) đều có descriptor `(I)I` nhưng function pointers có chữ ký C khác nhau?
4. Trong ví dụ, nếu đổi tên Java `doubleValue` thành `twice` mà không cập nhật bảng `methods`, lỗi thường xuất hiện ở giai đoạn nào khi đăng ký trong `JNI_OnLoad`?
5. Vì sao hàm C được khai báo `static` và không có tên `Java_...` vẫn được JVM gọi?
6. `FindClass` trong `JNI_OnLoad` dùng class loader nào? Vì sao điều này có ích khi ứng dụng dùng custom class loader?
7. Tham số `JNI_VERSION_1_6` trong `GetEnv` và giá trị trả về của `JNI_OnLoad` nói lên điều gì?
8. Nếu `RegisterNatives` trả mã âm, tại sao không được bỏ qua và trả `JNI_VERSION_1_6` ngay?
9. Với hai overload Java `transform(int)` và `transform(long)`, bảng `JNINativeMethod` phân biệt ra sao?
10. Tại sao không nên gọi `UnregisterNatives` tự động sau mỗi lần đăng ký thành công?
11. Một class loader khác cố nạp lại cùng thư viện JNI sẽ gặp nguy cơ gì?
12. Nếu giữ `jclass` từ `FindClass` qua nhiều lần gọi mà không tạo global reference, lỗi vòng đời nào có thể xảy ra?

**Kết luận:** `RegisterNatives` là cơ chế **đăng ký chủ động** ánh xạ `name + JVM signature → native function pointer` cho một **`jclass` cụ thể**. Dùng `JNI_OnLoad` giúp đăng ký ở **thời điểm nạp thư viện**, phát hiện sai mapping sớm, không yêu cầu export từng tên `Java_...`. Nhưng phải giữ đúng JNI ABI, loader/lifecycle, version, cleanup references và kiểm tra lỗi. Tên C tự chọn linh hoạt hơn, **không có nghĩa bỏ qua quy tắc JNI hay việc tải native library**.

### Tài liệu tham khảo chuẩn

- [JNI Specification — RegisterNatives, UnregisterNatives](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html): bảng `JNINativeMethod`, trạng thái lỗi, class và chữ ký.
- [JNI Invocation API — JNI_OnLoad, JNI_OnUnload, library/class-loader lifecycle](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html): hook, version, yêu cầu nạp thư viện, quản lý theo loader.
- [JNI Specification — FindClass and Class Loader](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html): quy tắc chọn class loader khi gọi `FindClass` từ `JNI_OnLoad`.
- [Android NDK JNI Tips — RegisterNatives và JNI_OnLoad](https://developer.android.com/ndk/guides/jni-tips): thực hành đăng ký tường minh, xác định class loader và gỡ lỗi liên kết.
