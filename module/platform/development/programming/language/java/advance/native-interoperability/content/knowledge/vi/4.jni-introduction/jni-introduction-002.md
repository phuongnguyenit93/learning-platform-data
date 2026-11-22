# Khai báo phương thức native cho đối tượng và phương thức static

## 1. Mục tiêu: khai báo đúng hai loại phương thức JNI đầu tiên

Trong Java, từ khóa `native` đánh dấu một phương thức **được khai báo trong class Java nhưng phần thân được triển khai bằng mã native** (chẳng hạn C/C++). Khi dùng JNI (Java Native Interface), JVM kết nối lời gọi Java với hàm native tương ứng. Hai hình thức thường gặp là:

- **Phương thức native của đối tượng (instance native method):** không có `static`; gọi trên một đối tượng cụ thể, có thể đọc trạng thái của đối tượng đó thông qua JNI.
- **Phương thức static native (class-level native method):** có `static`; gọi qua tên class, không có đối tượng nhận `this` ngầm định. Mã native nhận tham chiếu đến class và có thể truy cập trạng thái static nếu cần.

Bài này tập trung vào **cách khai báo và ánh xạ hai loại phương thức**, hiểu chữ ký JNI, tạo header bằng JDK, biên dịch thư viện, chạy thử và xử lý lỗi thường gặp. Các khái niệm tải thư viện chỉ được nhắc ở mức cần thiết để chạy ví dụ.

Sau bài học, bạn có thể nhìn vào:

~~~java
public native int addWithOffset(int left, int right);
public static native int multiply(int left, int right);
~~~

và giải thích vì sao hàm C đầu tiên nhận `jobject`, còn hàm thứ hai nhận `jclass`.

## 2. Cú pháp và ý nghĩa của `native` trong Java

Ví dụ về hai khai báo hợp lệ:

~~~java
public class NativeDeclaration {
    private native int increment(int value);       // Instance native
    public static native int doubleValue(int value); // Static native
}
~~~

Đây chỉ là **khai báo minh họa**, chưa phải chương trình chạy độc lập: muốn gọi được cần thư viện native và các hàm JNI tương ứng.

Đặc điểm quan trọng:

1. **Không có phần thân Java:** một phương thức `native` kết thúc bằng dấu `;`, không viết khối `{ ... }`. Việc viết cả `native` và phần thân Java sẽ không biên dịch.
2. **`static` là một tính chất độc lập:** `native` không tự làm phương thức trở thành static. Thiếu `static` thì phương thức nhận một đối tượng `this` theo quy tắc Java.
3. **Kiểu truy cập vẫn áp dụng:** `public`, `protected`, `private` điều khiển khả năng truy cập phía Java. Một phương thức `private native` vẫn được code Java trong class đó gọi và vẫn có thể có hàm native tương ứng.
4. **Các kiểu tham số/trả về phải được ánh xạ đúng:** Java `int` tương ứng `jint`, Java `long` tương ứng `jlong`, `String` tương ứng `jstring`; đối tượng/mảng có biểu diễn JNI riêng.
5. **`native` và `abstract` không thể cùng khai báo trên một phương thức:** `abstract` là yêu cầu lớp con triển khai phương thức Java, còn `native` là khai báo một triển khai native.
6. **`native` không nạp thư viện:** cần đưa thư viện vào tiến trình Java, thường bằng `System.loadLibrary(...)` hoặc `System.load(...)`. Khai báo biên dịch thành công không chứng minh được hàm C/C++ đã được kết nối.

So sánh lệnh gọi:

~~~java
NativeDeclaration obj = new NativeDeclaration();
obj.increment(4);                 // Instance: cần một đối tượng
NativeDeclaration.doubleValue(4); // Static: gọi qua class
~~~

Mã trên cũng chỉ minh họa cách gọi. Nếu chưa tạo/nạp JNI library, thực thi có thể phát sinh `UnsatisfiedLinkError`. Dù Java cho phép cú pháp gọi static thông qua một biến đối tượng, nên **dùng tên class** để biểu đạt rõ đây là phương thức static.

## 3. JVM ánh xạ instance và static xuống hai chữ ký C khác nhau

Với **JNI C API**, mỗi hàm triển khai native thường nhận các đối số ẩn ở đầu chữ ký: `JNIEnv *` và một tham chiếu phù hợp với loại phương thức.

| Đặc điểm | Instance `native` | `static native` |
|---|---|---|
| Cú pháp Java | `public native int calculate(int x);` | `public static native int calculate(int x);` |
| Cách gọi Java | `object.calculate(5)` | `SomeClass.calculate(5)` |
| Đối tượng nhận ngầm định trong Java | Có `this` | Không có `this` |
| Đối số JNI thứ nhất | `JNIEnv *env` | `JNIEnv *env` |
| Đối số JNI thứ hai | `jobject self`: tham chiếu đối tượng nhận | `jclass clazz`: tham chiếu đến class khai báo phương thức |
| Đối số tường minh tiếp theo | `jint x` | `jint x` |
| Có thể đọc field của object? | Có, qua `self` và API JNI | Không có object nhận sẵn; phải được truyền một `jobject` nếu muốn đọc instance field |
| Có thể đọc static field? | Có, nếu lấy đúng `jclass` | Có, dùng `clazz` và các API `GetStatic...` |

Hai chữ ký C khái niệm (tên lớp/method khác nhau để dễ đối chiếu):

~~~c
JNIEXPORT jint JNICALL Java_SomeClass_instanceCall(
    JNIEnv *env, jobject self, jint x
);

JNIEXPORT jint JNICALL Java_SomeClass_staticCall(
    JNIEnv *env, jclass clazz, jint x
);
~~~

**`JNIEnv *`** là giao diện gọi các chức năng JVM từ mã native của **luồng hiện tại**: đọc field, thao tác đối tượng, tạo chuỗi, ném ngoại lệ... Không chia sẻ con trỏ `JNIEnv *` trực tiếp giữa các thread.

**`jobject`** đại diện một tham chiếu JNI tới đối tượng Java đang nhận lời gọi instance; nó **không phải** con trỏ C trỏ vào cấu trúc layout của Java object. Muốn đọc `this.offset`, mã C dùng các hàm JNI, không ép kiểu `jobject` thành `struct *`.

**`jclass`** là tham chiếu JNI tới đối tượng `java.lang.Class` của class khai báo phương thức static. Nó không phải một instance của class nghiệp vụ; cũng không nên ép kiểu nó thành con trỏ struct C. Các API `GetStaticFieldID`, `GetStaticIntField`, `GetStaticMethodID`... được dùng khi cần truy cập thành viên static.

**`JNIEXPORT`** giúp export symbol đúng cách; **`JNICALL`** dùng calling convention JNI phù hợp với nền tảng. Nên dùng nguyên vẹn các macro này thay vì tự đoán từ kiểu `int`/calling convention của compiler.

> Quy tắc nhớ nhanh: *instance* nhận `JNIEnv *` + `jobject` + tham số khai báo trong Java; *static* nhận `JNIEnv *` + `jclass` + tham số khai báo trong Java.

## 4. Ví dụ hoàn chỉnh: một class chứa cả instance và static native

Ta sẽ tạo một class `NativeKinds` có trạng thái riêng của từng đối tượng:

- `addWithOffset(left, right)` là **instance native**, trả về `left + right + offset`; hai object có `offset` khác nhau sẽ cho kết quả khác nhau.
- `multiply(left, right)` là **static native**, trả về tích hai tham số; không sử dụng `offset` của bất kỳ object nào.

Cấu trúc làm việc:

~~~text
jni-example/
├── NativeKinds.java       # Khai báo và phần chạy Java
├── nativekinds.c           # Triển khai JNI bằng C
└── NativeKinds.h           # Tự sinh bằng javac -h .
~~~

Tệp `.class` và tệp thư viện native được sinh ra trong quá trình build, không viết tay.

### 4.1. Viết `NativeKinds.java`

~~~java
public final class NativeKinds {
    static {
        System.loadLibrary("nativekinds");
    }

    private final int offset;

    public NativeKinds(int offset) {
        this.offset = offset;
    }

    public native int addWithOffset(int left, int right);

    public static native int multiply(int left, int right);

    public static void main(String[] args) {
        NativeKinds first = new NativeKinds(10);
        NativeKinds second = new NativeKinds(20);

        System.out.println("instance A: " + first.addWithOffset(2, 3));
        System.out.println("instance B: " + second.addWithOffset(2, 3));
        System.out.println("static: " + NativeKinds.multiply(2, 3));
    }
}
~~~

Đọc kỹ ba điểm:

1. `addWithOffset` **không có `static`** nên mỗi lời gọi có đối tượng nhận riêng: `first` hoặc `second`.
2. `multiply` **có `static`** nên gọi bằng `NativeKinds.multiply(...)`. Trong chữ ký Java của phương thức này không có `this` và không thể trực tiếp dùng `offset` như một biến instance.
3. Khối `static` nạp thư viện theo tên logic `nativekinds` khi class được khởi tạo. Tên tệp thực tế sẽ tùy hệ điều hành: `nativekinds.dll`, `libnativekinds.so` hoặc `libnativekinds.dylib`. Không đưa đuôi tệp vào `loadLibrary`.

Chưa chạy `java NativeKinds` lúc này, vì triển khai C chưa được build. Lệnh `javac` có thể thành công dù thư viện native chưa tồn tại.

### 4.2. Sinh header bằng JDK, không tự đoán tên hàm

Từ thư mục chứa `NativeKinds.java`, dùng **JDK 17 hoặc mới hơn**:

~~~bash
javac -h . NativeKinds.java
~~~

Lệnh tạo `NativeKinds.class` và `NativeKinds.h`. Header là hợp đồng giữa Java và C. Phần khai báo hàm cốt lõi trong header có hình thức:

~~~c
JNIEXPORT jint JNICALL Java_NativeKinds_addWithOffset
  (JNIEnv *, jobject, jint, jint);

JNIEXPORT jint JNICALL Java_NativeKinds_multiply
  (JNIEnv *, jclass, jint, jint);
~~~

Đây là **trích đoạn** của header, không phải toàn bộ tệp sinh tự động (header thật còn include guard, `#include <jni.h>` và comment mô tả chữ ký). Lưu ý rằng **`jobject` và `jclass` là điểm khác biệt quan trọng duy nhất ở hai đối số ngầm định**; các đối số `jint` còn lại tương ứng với hai tham số `int` được khai báo trong Java.

Các JNI type cơ bản liên quan:

| Khai báo Java | Kiểu thường thấy trong JNI C | Descriptor JVM |
|---|---|---|
| `boolean` | `jboolean` | `Z` |
| `byte` | `jbyte` | `B` |
| `char` | `jchar` | `C` |
| `short` | `jshort` | `S` |
| `int` | `jint` | `I` |
| `long` | `jlong` | `J` |
| `float` | `jfloat` | `F` |
| `double` | `jdouble` | `D` |
| `void` | `void` (kiểu trả về) | `V` |
| `String` | `jstring` | `Ljava/lang/String;` |
| `int[]` | `jintArray` | `[I` |

Chữ ký JVM cho cả hai phương thức Java trong ví dụ là `(II)I`: nhận hai `int`, trả về `int`. Descriptor **không liệt kê** `JNIEnv *`, `jobject` hoặc `jclass`, vì đó là tham số ngầm định của hàm C, không phải tham số khai báo trong phương thức Java.

### 4.3. Triển khai hai hàm trong `nativekinds.c`

~~~c
#include "NativeKinds.h"

JNIEXPORT jint JNICALL Java_NativeKinds_addWithOffset(
    JNIEnv *env, jobject self, jint left, jint right
) {
    /* Tìm class của đối tượng hiện tại. */
    jclass clazz = (*env)->GetObjectClass(env, self);
    if (clazz == NULL) {
        return 0; /* Đã có Java exception đang chờ. */
    }

    /* "I" là descriptor của field kiểu int. */
    jfieldID offsetField = (*env)->GetFieldID(
        env, clazz, "offset", "I"
    );
    if (offsetField == NULL) {
        (*env)->DeleteLocalRef(env, clazz);
        return 0; /* GetFieldID báo lỗi bằng Java exception. */
    }

    jint offset = (*env)->GetIntField(env, self, offsetField);
    (*env)->DeleteLocalRef(env, clazz);

    return left + right + offset;
}

JNIEXPORT jint JNICALL Java_NativeKinds_multiply(
    JNIEnv *env, jclass clazz, jint left, jint right
) {
    (void) env;   /* Ví dụ này không cần gọi hàm JNI. */
    (void) clazz; /* Static method nhận class, không nhận this. */
    return left * right;
}
~~~

**Giải thích phần instance:**

- Tham số `self` là đối tượng `first` hoặc `second` tùy từng lần gọi.
- `GetObjectClass(env, self)` nhận tham chiếu class; `GetFieldID(..., "offset", "I")` tìm field `offset` kiểu `int`.
- `GetIntField(env, self, offsetField)` đọc đúng giá trị từ **đối tượng đang gọi**. Do đó `first` dùng 10, còn `second` dùng 20.
- `DeleteLocalRef` giải phóng tham chiếu local tới `clazz` khi không cần nữa. `offsetField` là ID, không phải `jobject` local reference để xóa theo cách này.
- Nếu `GetObjectClass` hoặc `GetFieldID` thất bại, chúng có thể để lại **pending Java exception**. Giá trị `0` ở nhánh lỗi chỉ là giá trị trả về từ C khi xử lý ngoại lệ; nếu ngoại lệ còn chờ, phía Java sẽ nhận ngoại lệ thay vì dùng `0` như kết quả hợp lệ.

**Giải thích phần static:**

- Tham số thứ hai là `jclass clazz`, **không phải `jobject self`**.
- Hàm chỉ dùng `left` và `right`, nên ép void để compiler không cảnh báo hai tham số JNI không sử dụng.
- Nếu muốn truy cập biến `static int factor` trong class, mã C phải dùng `GetStaticFieldID` và `GetStaticIntField` với `clazz`. Không dùng `GetIntField` cho static field.

Để bài dễ chạy và output xác định, ví dụ dùng các số nhỏ: không khảo sát tràn số nguyên có dấu trong C. Khi tính toán với giá trị lớn, cần chủ động định nghĩa cách xử lý overflow vì ngữ nghĩa số nguyên có dấu C và Java khác nhau.

### 4.4. Biên dịch thư viện theo hệ điều hành

Chạy **một** trong ba cách sau tùy máy đang chạy JVM. Máy cần JDK có header JNI và compiler C phù hợp; biến `JAVA_HOME` trỏ tới JDK đó. Thực hiện từ thư mục chứa `NativeKinds.java`, `NativeKinds.h` và `nativekinds.c`.

**Linux (GCC):**

~~~bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  nativekinds.c -o libnativekinds.so

java -Djava.library.path=. NativeKinds
~~~

**macOS (Clang):**

~~~bash
cc -dynamiclib -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  nativekinds.c -o libnativekinds.dylib

java -Djava.library.path=. NativeKinds
~~~

**Windows (MSVC trong Developer Command Prompt, cú pháp `cmd.exe`):**

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" nativekinds.c /Fe:nativekinds.dll

java -Djava.library.path=. NativeKinds
~~~

Nếu sử dụng `javac` và `java` từ các JDK khác nhau, hoặc compiler biên dịch cho kiến trúc không trùng JVM (ví dụ DLL 32-bit nhưng JVM 64-bit), việc nạp có thể thất bại. Cần build cho **hệ điều hành + CPU/bitness + ABI tương thích tiến trình JVM**.

Khi build, nạp và gọi thành công, stdout chính xác là:

~~~text
instance A: 15
instance B: 25
static: 6
~~~

Giải thích: `first.addWithOffset(2,3) = 2 + 3 + 10 = 15`; `second.addWithOffset(2,3) = 2 + 3 + 20 = 25`; `multiply(2,3) = 6`. Hai instance dùng cùng mã hàm C nhưng mang dữ liệu trạng thái Java khác nhau; static native không có state của một `this` ngầm định.

## 5. Lần theo lời gọi Java → JNI → C

~~~text
Java thread thực thi main()
    |
    +--> first.addWithOffset(2, 3)
    |      +--> JVM chuyển sang hàm JNI instance
    |      +--> (JNIEnv*, jobject first, jint 2, jint 3)
    |      +--> GetIntField(first, offset) = 10
    |      +--> trả 15 về Java
    |
    +--> second.addWithOffset(2, 3)
    |      +--> (JNIEnv*, jobject second, jint 2, jint 3)
    |      +--> GetIntField(second, offset) = 20
    |      +--> trả 25 về Java
    |
    +--> NativeKinds.multiply(2, 3)
           +--> JVM chuyển sang hàm JNI static
           +--> (JNIEnv*, jclass NativeKinds, jint 2, jint 3)
           +--> trả 6 về Java
~~~

Trong cả ba lần gọi, **mã C chạy bên trong tiến trình JVM đang hoạt động**. `native` không tự tạo tiến trình con, không tự sử dụng mạng/IPC và không chuyển đối tượng Java thành struct C. JVM duy trì việc chuyển tiếp giữa Java và native theo hợp đồng JNI.

Một đối tượng có thể có nhiều method native instance; mỗi lần gọi sẽ nhận receiver phù hợp. Một static native method vẫn được gọi qua class kể cả khi không tồn tại instance nào của class đó.

## 6. Các điểm cần hiểu sâu về `jobject` và `jclass`

### 6.1. Vì sao hàm instance nhận `jobject` nhưng không thể đọc `self->offset`?

JVM quản lý bố trí đối tượng, GC và tham chiếu. Vì vậy, `jobject` là **JNI reference**, không phải định nghĩa công khai về địa chỉ/layout của object. Dùng `GetFieldID` và `GetIntField` thay cho dereference con trỏ như C struct.

`jobject` trong ví dụ là một *local reference* hợp lệ trong thời gian gọi JNI hiện tại; không lưu nguyên tham chiếu này vào biến global C để sử dụng tùy ý sau khi hàm đã trả về. Nếu phải giữ tham chiếu qua nhiều lời gọi, dùng cơ chế **global reference** (`NewGlobalRef`/`DeleteGlobalRef`) và quản lý vòng đời cẩn thận.

### 6.2. `jclass` có thể truy cập gì?

`jclass` đại diện class khai báo phương thức static. Để đọc trạng thái static của class từ C, ý tưởng là:

~~~c
/* Trích đoạn minh họa; chỉ hợp lệ khi class có static int factor. */
jfieldID factorField = (*env)->GetStaticFieldID(
    env, clazz, "factor", "I"
);
if (factorField == NULL) {
    return 0; /* Java exception đang chờ. */
}
jint factor = (*env)->GetStaticIntField(
    env, clazz, factorField
);
~~~

Đây là **trích đoạn**, không phải phần bổ sung cần chèn vào `nativekinds.c` của ví dụ chạy hoàn chỉnh. Muốn dùng thật phải có field Java `static int factor` cùng tên/kiểu và một hàm native với chữ ký phù hợp.

Nếu static native method cần làm việc với một **đối tượng cụ thể**, phương thức Java có thể **nhận đối tượng đó như tham số tường minh**; lúc ấy hàm C nhận thêm một `jobject` tương ứng với tham số được khai báo. Bản thân lời gọi static vẫn không có `this` ngầm định.

### 6.3. Khác biệt giữa field instance và field static trong JNI

| Tác vụ | Instance field | Static field |
|---|---|---|
| Lấy field ID | `GetFieldID` | `GetStaticFieldID` |
| Đọc field `int` | `GetIntField(env, object, fieldID)` | `GetStaticIntField(env, clazz, fieldID)` |
| Ghi field `int` | `SetIntField(env, object, fieldID, value)` | `SetStaticIntField(env, clazz, fieldID, value)` |
| Đối tượng cần có | Một `jobject` nhận | Một `jclass` |
| Trạng thái | Mỗi object có giá trị riêng | Một giá trị gắn với class (theo loader tương ứng) |

Tên field và JVM descriptor phải khớp khai báo thực tế. `GetFieldID` tìm instance field, `GetStaticFieldID` tìm static field; sử dụng sai API hoặc sai descriptor có thể dẫn tới lỗi tìm field và pending exception.

### 6.4. Kế thừa, đa hình và static

- **Instance native method** là một instance method Java bình thường về mặt quy tắc gọi và override: nếu có thể override, lớp con có thể override bằng phương thức Java hoặc triển khai native phù hợp. Trong ví dụ, class được đánh dấu `final` để tập trung vào sự khác nhau giữa receiver và class.
- **Static native method** tuân theo quy tắc static Java: chọn method theo class/kiểu tại compile time, không có dynamic dispatch theo kiểu đối tượng nhận. Static method có thể *hide* static method cùng tên ở superclass, không override instance method.
- JNI C function được chọn phải khớp phương thức native mà JVM đang giải quyết. Không được suy diễn rằng vì class con có object khác nên `static native` nhận object đó.

## 7. Tên hàm JNI và phương thức overload

Khi dùng JNI theo **cách tìm symbol dựa trên tên** (name-based lookup), hàm export thường có dạng:

~~~text
Java_<package_và_class_đã_mã_hóa>_<method_đã_mã_hóa>
~~~

Ví dụ không dùng package, không overload:

~~~text
Java_NativeKinds_addWithOffset
Java_NativeKinds_multiply
~~~

Với class nằm trong package, tên export có thêm các thành phần package đã được mã hóa theo quy tắc JNI. Dấu `_` có ý nghĩa đặc biệt trong quy tắc mã hóa: không thể luôn lấy tên đầy đủ của class rồi thay mỗi dấu chấm bằng dấu gạch dưới và coi như xong. **Dùng `javac -h`** để tránh sai tên, sai signature hay dấu mangle.

Nếu **overload** nhiều phương thức `native` cùng tên nhưng khác kiểu tham số, tên dài có thêm phần mô tả **kiểu tham số**. Ví dụ khai báo (đây là ví dụ riêng, không chèn vào `NativeKinds.java` ở trên):

~~~java
public static native int sum(int a, int b);
public static native long sum(long a, long b);
~~~

Với class giả định tên `Overloads` trong default package, header có thể chứa các tên:

~~~text
Java_Overloads_sum__II
Java_Overloads_sum__JJ
~~~

Phần `__II` biểu diễn hai tham số `int`; `__JJ` biểu diễn hai `long`. Phân biệt overload dựa trên kiểu tham số theo JNI descriptor; **không dùng kiểu trả về** để phân biệt overload Java. Tốt nhất vẫn sinh header từ mã thật để lấy tên chính xác.

Một con đường khác là **`RegisterNatives`**, nơi thư viện chủ động đăng ký ánh xạ giữa tên Java, descriptor và con trỏ hàm C. Khi đó không nhất thiết phải dựa vào symbol export theo mẫu `Java_...`. Bài thực hành chọn name-based lookup để thấy trực tiếp sự khác nhau giữa `jobject` và `jclass`.

## 8. Những điều `static native` và instance `native` không tự làm

**Không tự động chuyển ownership của dữ liệu.** `jobject` là tham chiếu quản lý qua JNI; dữ liệu native cấp phát bằng `malloc` hoặc các native allocator không tự động được GC Java thu hồi. Nếu cấp phát tài nguyên native, cần cơ chế giải phóng tương ứng.

**Không tự động bảo đảm an toàn luồng.** Nhiều Java thread có thể gọi native methods; C code cần bảo vệ trạng thái dùng chung theo yêu cầu. `JNIEnv *` là gắn với thread hiện tại và **không được dùng lại từ thread khác**. Các biến C `static`/global khác với field `static` phía Java dù có thể đều là trạng thái chung.

**Không tự động bảo đảm an toàn kiểu ở runtime native.** Java compiler kiểm tra lời gọi Java, còn C compiler kiểm tra chữ ký C của hàm. Sai ánh xạ, dùng sai API JNI, giữ tham chiếu quá hạn hay truy cập bộ nhớ bất hợp lệ có thể làm JVM crash.

**Không bảo đảm method đã liên kết chỉ vì class biên dịch thành công.** Cần đúng thư viện native, đúng symbol hoặc đăng ký native method, đúng CPU/ABI và các thư viện phụ thuộc. JVM có thể báo `UnsatisfiedLinkError` khi nạp thư viện hoặc khi giải quyết phương thức.

**Không thay thế quy tắc khởi tạo class.** Lời gọi static native vẫn chịu quy tắc class initialization của Java. Trong ví dụ, khối `static` chứa `System.loadLibrary` chạy trong quá trình khởi tạo class. Nếu nạp thất bại, lời gọi native sẽ không thực hiện được.

## 9. Lỗi thường gặp khi tự làm JNI đầu tiên

| Lỗi hoặc triệu chứng | Nguyên nhân thường gặp | Cách xác minh và sửa |
|---|---|---|
| `'native' method cannot have a body` hoặc lỗi biên dịch tương tự | Viết `native ... { ... }` | Khai báo bằng `;`; đặt phần triển khai trong C/C++. |
| Gọi `obj.method()` khi method là instance mà chưa tạo obj | Thiếu receiver hoặc đối tượng `null` | Tạo object thực và gọi instance method, hoặc đổi thiết kế thành static nếu không cần state. |
| `UnsatisfiedLinkError: no nativekinds in java.library.path` | Không tìm thấy thư viện theo tên logic | Kiểm tra tên và tham số `-Djava.library.path=.` trước class. |
| Tìm thấy file nhưng vẫn `UnsatisfiedLinkError` | Thiếu dependency, sai kiến trúc, sai định dạng hoặc sai export | Kiểm tra binary OS/CPU/bitness, dependency và tên symbol. |
| Lỗi không tìm thấy native method sau khi đổi chữ ký | C vẫn build theo header cũ hoặc tên/descriptor đã đổi | Chạy lại `javac -h`, cập nhật C, build lại thư viện. |
| C nhận `jclass` thay vì `jobject` cho instance (hoặc ngược lại) | Tự viết signature sai | Đọc header vừa sinh; đối số 2 khác nhau theo `static`. |
| `GetFieldID` không tìm được field | Sai tên, descriptor, hoặc field thật là static | Kiểm tra field Java, dùng đúng `GetFieldID`/`GetStaticFieldID` và `I` cho `int`. |
| Crash/`hs_err_pid...log` | Truy cập JNI reference sai, con trỏ/ABI hỏng hoặc native memory error | Dùng JNI API đúng, bật kiểm tra JNI khi debug; xem crash log và native stack. |
| C/C++ báo symbol linkage khó hiểu | C++ mangling hoặc thiếu macro/khai báo | Include header từ `javac -h`, dùng linkage C đúng theo header JNI. |

**Lệnh kiểm tra hữu ích:**

~~~bash
java -version
java -Xcheck:jni -Djava.library.path=. NativeKinds
~~~

`-Xcheck:jni` là tùy chọn kiểm tra sử dụng JNI của HotSpot, có thể giúp phát hiện một số cách gọi JNI không hợp lệ khi debug; nó không chứng minh toàn bộ mã C/C++ là an toàn và không ngăn mọi crash. Kết quả đúng của chương trình bình thường vẫn là ba dòng `instance A: 15`, `instance B: 25` và `static: 6`; tùy JVM/cấu hình, chế độ kiểm tra có thể in thêm cảnh báo khi tìm thấy lỗi JNI.

Với lỗi build, hãy nhìn **lỗi đầu tiên** do compiler/linker đưa ra. Với lỗi runtime, xác định thất bại xảy ra lúc **nạp thư viện** hay khi **gọi native method**, bởi đó là hai giai đoạn khác nhau. Kiểm tra binary và dependency theo hệ điều hành nếu cần:

~~~text
Linux:   file / readelf / ldd
macOS:   file / lipo / otool -L
Windows: dumpbin /HEADERS /DEPENDENTS
~~~

Dòng trên liệt kê **tên công cụ**, không phải lệnh shell hoàn chỉnh; mỗi công cụ cần được truyền đúng đường dẫn thư viện khi chạy.

## 10. Bài tập tự kiểm tra

1. Trong `NativeKinds.java`, vì sao hai object có `offset` khác nhau nhưng hàm JNI `Java_NativeKinds_addWithOffset` vẫn là **một** hàm C?
2. Vì sao `Java_NativeKinds_multiply` nhận `jclass` dù khai báo Java không có tham số kiểu `Class`?
3. Nếu đổi `addWithOffset` thành `static native` mà không thay đổi C, chữ ký có còn đúng không? Điều gì xảy ra với việc đọc `offset`?
4. `GetFieldID` và `GetStaticFieldID` khác nhau như thế nào? Với field Java `private final int offset`, cần dùng API nào?
5. Khi thêm overload `multiply(long, long)` bên cạnh `multiply(int, int)`, cần làm gì để tránh viết sai tên hàm native?
6. Vì sao biên dịch `NativeKinds.java` thành công chưa đủ chứng minh lệnh `java NativeKinds` sẽ chạy thành công?

**Kết luận:** Trong JNI, **instance native method nhận `JNIEnv *` và `jobject` (đại diện `this`)**; **static native method nhận `JNIEnv *` và `jclass` (đại diện class khai báo)**. Các tham số Java xuất hiện sau hai tham số ẩn này. Khai báo đúng, sinh header bằng `javac -h`, triển khai đúng JNI API và kiểm thử bằng một ví dụ thực thi sẽ giúp bạn phân biệt rõ hai cách gọi ngay từ bài JNI đầu tiên.
