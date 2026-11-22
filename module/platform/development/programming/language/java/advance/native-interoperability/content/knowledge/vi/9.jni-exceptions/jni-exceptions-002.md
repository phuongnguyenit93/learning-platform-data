# Kiểm tra ngoại lệ đang chờ sau khi JNI gọi phương thức Java

## 1. Vấn đề: gọi Java từ C/C++ qua JNI không giống gọi hàm C bình thường

Trong **Java Native Interface (JNI)**, mã C/C++ có thể gọi ngược phương thức Java bằng các hàm như `CallObjectMethod`, `CallIntMethod`, `CallVoidMethod`, `CallStaticIntMethod`, `CallNonvirtualObjectMethod` và những biến thể `A`/`V` tương ứng. Phương thức Java đó có thể thực thi bình thường, trả về một giá trị, **hoặc ném một ngoại lệ Java**.

Điểm dễ nhầm: khi phương thức Java ném ngoại lệ trong lời gọi qua JNI, JVM đánh dấu một **ngoại lệ đang chờ** (*pending exception*) trên luồng đang thực hiện JNI. Mã native **không tự bị thoát khỏi hàm C**, và ngoại lệ Java **không tự trở thành exception của C++**. Quyền điều khiển quay lại sau lời gọi JNI, nơi lập trình viên phải kiểm tra trạng thái rồi chọn cách xử lý.

Ví dụ:

```text
Java main()
    |
    v
native method (C)
    |
    +-- CallStaticIntMethod(...) ----> Java compute(8, 0)
    |                                    |
    |                               ArithmeticException
    |                                    |
    |<---- trở lại C, exception pending -+
    |
    +-- ExceptionCheck(env) == JNI_TRUE
    |
    +-- Lựa chọn A: cleanup, return -> Java nhận ngoại lệ
    |
    +-- Lựa chọn B: ExceptionClear -> xử lý có chủ đích -> return fallback
```

Nếu **bỏ qua trạng thái pending** rồi gọi tiếp JNI API không được phép trong trạng thái này, chương trình có thể sinh cảnh báo dưới `-Xcheck:jni`, có kết quả không đáng tin cậy hoặc thất bại nghiêm trọng. Vì vậy **sau khi một JNI call gọi Java trở về, hãy kiểm tra ngoại lệ trước khi dùng kết quả hoặc gọi JNI tiếp**.

Bài này tập trung đúng vào tình huống **native code gọi phương thức Java**, nhận lỗi qua pending exception và chọn **lan truyền**, **xử lý**, hoặc **chuyển đổi** lỗi một cách kiểm soát.

## 2. Cơ chế “pending exception” trên luồng JNI

Một luồng Java đi vào native method mang theo con trỏ giao diện `JNIEnv *env`. Khi native code gọi lại phương thức Java:

1. JVM thực thi phương thức đã được chỉ định bởi `jmethodID`.
2. Nếu phương thức kết thúc bình thường, hàm JNI trả về giá trị tương ứng, không có ngoại lệ do lời gọi đó.
3. Nếu phương thức ném một `Throwable`, JVM đánh dấu ngoại lệ này **đang chờ** trên luồng hiện tại và trả quyền điều khiển về native code.
4. Native code kiểm tra bằng `ExceptionCheck` hoặc `ExceptionOccurred`; không được xem giá trị trả về của `Call*Method` là kết quả bình thường khi còn pending exception.
5. Nếu native method **trở về Java mà không xóa** ngoại lệ, JVM lan truyền ngoại lệ đó trong Java như một lần ném thông thường.
6. Nếu native code gọi `ExceptionClear`, ngoại lệ đang chờ bị gỡ; mã native có thể tiếp tục các JNI thao tác hợp lệ tiếp theo theo chính sách xử lý đã chọn.

**Ngoại lệ đang chờ là trạng thái của một luồng JNI**, không phải biến toàn cục dùng chung cho mọi luồng. `JNIEnv*` cũng gắn với luồng tương ứng; không lưu hoặc chuyển nó sang thread khác để kiểm tra ngoại lệ. Mỗi thread native được attach vào JVM có giao diện `JNIEnv*` riêng.

Không nhầm ba khái niệm:

- **Giá trị trả về của hàm JNI:** `jint`, `jobject`, `jboolean`, `void`…, chỉ có ý nghĩa bình thường khi lời gọi thành công.
- **Trạng thái pending exception:** JVM biết một lỗi Java chưa được xử lý ở luồng hiện tại, dù native code chưa thoát.
- **Local reference đến đối tượng exception:** có thể lấy bằng `ExceptionOccurred` để tham chiếu `jthrowable`; chỉ có nó không tự động xóa pending exception.

Ngoại lệ phát sinh từ Java callback có thể là checked exception, unchecked exception hoặc `Error`. JNI không tự động buộc mã C phân biệt loại đó trước khi trả về. Khi Java gọi native method trở lại, cơ chế `try/catch` thông thường của Java sẽ xử lý nếu khớp kiểu.

## 3. Các JNI API kiểm tra và xử lý ngoại lệ

| API JNI (C) | Ý nghĩa | Trạng thái pending sau lời gọi |
| --- | --- | --- |
| `(*env)->ExceptionCheck(env)` | Trả `JNI_TRUE` nếu có pending exception, ngược lại `JNI_FALSE`; không tạo local reference tới lỗi | **Giữ nguyên** |
| `(*env)->ExceptionOccurred(env)` | Trả `jthrowable` là **local reference** tới exception đang chờ, hoặc `NULL` | **Giữ nguyên** |
| `(*env)->ExceptionClear(env)` | Xóa pending exception trên luồng | **Bị xóa** |
| `(*env)->ExceptionDescribe(env)` | In exception và stack trace tới kênh chẩn đoán như stderr | **Bị xóa như tác dụng phụ** theo JNI Specification |
| `(*env)->Throw(env, throwable)` | Làm một đối tượng `Throwable` trở thành pending exception | **Đặt ngoại lệ mới** khi thành công |
| `(*env)->ThrowNew(env, clazz, message)` | Tạo và đặt exception mới thuộc class đã chọn | **Đặt ngoại lệ mới** khi thành công |

### 3.1. Dùng ExceptionCheck khi chỉ cần biết có lỗi hay không

```c
jint result = (*env)->CallStaticIntMethod(
    env, clazz, methodId, 8, 0);

if ((*env)->ExceptionCheck(env)) {
    /* Có lỗi Java. Đừng dùng result như phép chia thành công. */
    return 0; /* Placeholder cho kiểu trả về C; Java nhận exception. */
}

/* Không có pending exception từ lời gọi: result có ý nghĩa. */
return result;
```

Đây là **một đoạn mã minh họa**, không phải toàn bộ thư viện JNI; `clazz`/`methodId` phải được tìm hợp lệ trước đó. Khi `ExceptionCheck` trả `JNI_TRUE`, nó **không xóa** ngoại lệ. `return 0` chỉ làm hàm C thỏa kiểu `jint`; Java **không nhận số 0 như kết quả thành công**, mà nhận ngoại lệ đang chờ.

### 3.2. Dùng ExceptionOccurred khi cần giữ lại đối tượng Throwable

```c
jthrowable error = (*env)->ExceptionOccurred(env);
if (error != NULL) {
    /* error là local reference; pending exception vẫn tồn tại. */
    /* Có thể cleanup local reference bằng DeleteLocalRef. */
    (*env)->DeleteLocalRef(env, error);
    return 0;  /* Pending exception tiếp tục được chuyển về Java. */
}
```

`ExceptionOccurred` phù hợp khi sau đó cần phân loại, lưu, log hoặc ném lại một ngoại lệ. Nó **khác** `ExceptionCheck` ở chỗ tạo local reference mới, cần tuân thủ vòng đời local ref. Chỉ gọi `ExceptionOccurred` rồi dùng `error` để gọi bất kỳ Java method nào khi pending exception còn đó **vẫn sai**; nếu muốn thao tác thông thường qua JNI, phải xử lý trạng thái pending trước.

### 3.3. ExceptionDescribe không chỉ “in log”

JNI Specification quy định `ExceptionDescribe` in exception và backtrace tới kênh báo lỗi, **đồng thời clear pending exception**. Vì vậy đoạn sau là một bẫy:

```c
if ((*env)->ExceptionCheck(env)) {
    (*env)->ExceptionDescribe(env);
    return 0;
}
```

Người viết có thể tưởng lỗi sẽ tiếp tục đi lên Java sau khi in log, nhưng `ExceptionDescribe` đã **xóa lỗi**. Nếu mục tiêu là **lan truyền nguyên gốc**, không dùng `ExceptionDescribe` như một logger “vô hại”. Có thể để Java nhận/catch/log exception ở biên Java; hoặc lưu object `jthrowable`, clear, xử lý theo quy trình có chủ đích rồi dùng `Throw` để ném lại (mục 8).

## 4. Vì sao bắt buộc kiểm tra sau Call*Method?

Nhiều JNI hàm trả mã lỗi rõ ràng khi thất bại, ví dụ một API lookup có thể trả `NULL` và tạo pending exception. Nhưng nhóm hàm gọi Java như `CallIntMethod` hoặc `CallStaticIntMethod` **trả kiểu giá trị Java gốc**, nên giá trị trả về một mình không đủ báo lỗi.

Ví dụ:

- `CallIntMethod(...)`: số `0` có thể là giá trị thành công hợp lệ hoặc chỉ là giá trị không được phép dùng vì callback đã ném ngoại lệ. **Không suy ra thành công từ `result == 0` hay `result != 0`.**
- `CallObjectMethod(...)`: `NULL` có thể tương ứng kết quả Java `null` hợp lệ, hoặc có một ngoại lệ đang chờ. **Phải kiểm tra `ExceptionCheck`** khi cần phân biệt.
- `CallVoidMethod(...)`: hàm không có giá trị trả về, nhưng Java method vẫn có thể ném ngoại lệ.
- Các biến thể `CallStatic<Type>Method`, `CallNonvirtual<Type>Method` và dạng `A` (mảng `jvalue`)/`V` (`va_list`) có cùng bài toán pending exception.

Một chuỗi JNI calls an toàn về nguyên tắc:

```text
[Đã có env, obj, methodId hợp lệ]
  -> Call<Type>Method(...)
  -> ExceptionCheck / ExceptionOccurred
       +-- có exception: cleanup được phép + return (propagate)
       |                    hoặc clear + xử lý có chủ đích
       +-- không exception: dùng kết quả, tiếp tục JNI bình thường
```

**Kiểm tra ngay sau ranh giới có thể ném ngoại lệ.** Đừng trì hoãn qua một chuỗi `GetFieldID`, `NewStringUTF` hoặc `Call*Method` khác, vì những API này không mặc nhiên an toàn khi luồng có pending exception.

Ngoài ra, `GetMethodID`/`GetStaticMethodID`/`FindClass` cũng có thể thất bại với ngoại lệ Java như `NoSuchMethodError`/`NoClassDefFoundError`. Phải kiểm tra kết quả lookup **trước khi gọi method**, và nếu lookup đã tạo exception thì trả về/cleanup thay vì cố tiếp tục.

## 5. Những lời gọi JNI nào an toàn khi đã có pending exception?

Đặc tả JNI liệt kê một tập API an toàn khi có pending exception. Các nhóm quan trọng:

- **Quan sát/điều khiển exception:** `ExceptionOccurred`, `ExceptionCheck`, `ExceptionDescribe`, `ExceptionClear`.
- **Giải phóng local/global/weak JNI references:** `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef`.
- **Trả tài nguyên đã mượn từ JVM:** `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical`, `Release<Type>ArrayElements`, `ReleasePrimitiveArrayCritical`.
- **Kết thúc monitor hoặc local frame:** `MonitorExit`, `PopLocalFrame` và `PushLocalFrame` trong danh sách được cho phép.
- **Kết thúc một luồng đã attach:** `DetachCurrentThread` theo điều kiện áp dụng.

Không nên hiểu đây là giấy phép gọi tùy ý. Ví dụ `MonitorExit` phải tương ứng một lần `MonitorEnter` thành công trước đó, `ReleaseStringUTFChars` phải có buffer do API tương ứng cấp, `DeleteLocalRef` phải nhận local ref hợp lệ.

Đặc biệt, trong khi pending exception chưa clear, **đừng gọi** như thể bình thường các API `FindClass`, `GetObjectClass`, `GetMethodID`, `CallObjectMethod`, `NewStringUTF` hoặc `NewGlobalRef`. Chúng không thuộc tập API được đặc tả là an toàn trong trạng thái này.

**Hàm C thuần** như `free`, đóng file descriptor của OS hoặc giải phóng buffer native do mình quản lý không phải là JNI call; vẫn có thể dọn tài nguyên C trong nhánh lỗi. Hãy tránh gọi các hàm native có tác dụng phụ phức tạp nếu logic chương trình đã ở trạng thái lỗi.

## 6. Hai chiến lược chuẩn sau khi JNI gọi Java gặp ngoại lệ

### A. Để ngoại lệ gốc lan truyền về Java (propagate)

Áp dụng khi native method không thể hoặc không nên phục hồi:

```c
jint result = (*env)->CallStaticIntMethod(env, cls, mid, x, y);

if ((*env)->ExceptionCheck(env)) {
    /* Cleanup JNI references/borrowed buffers nếu có. */
    return 0; /* Không gọi ExceptionClear. */
}
return result;
```

Sau khi native method trở về, JVM tiếp tục lan truyền exception cho caller Java. Caller có thể xử lý bằng `try/catch`, stack trace giữ nguyên nguyên nhân gốc. Giá trị C `0` trên nhánh lỗi **bị bỏ qua như một giá trị thành công**.

**Ưu tiên cách này** nếu callback vi phạm hợp đồng hoặc ném lỗi không thể phục hồi; không tự nuốt exception chỉ để tiếp tục workflow native.

### B. Xóa ngoại lệ để phục hồi có chủ đích (handle/recover)

Áp dụng khi một lỗi Java cụ thể là tình huống **đã được thiết kế trước** và caller nên nhận fallback:

```c
jint result = (*env)->CallStaticIntMethod(env, cls, mid, x, y);

if ((*env)->ExceptionCheck(env)) {
    (*env)->ExceptionClear(env);
    return fallback;
}
return result;
```

Sau `ExceptionClear`, JNI có thể tiếp tục theo nhánh phục hồi. Nhưng thao tác này **nuốt ngoại lệ gốc**, có thể che giấu lỗi lập trình hoặc `OutOfMemoryError`. Dùng trong bài học để minh họa cơ chế, còn sản xuất nên **chỉ clear khi đã phân loại và quyết định lỗi là recoverable**, log/ghi nhận theo chính sách, hoặc gói thành exception mới có thông tin nguyên nhân.

| Nhu cầu | Hành vi với pending exception | Hậu quả phía Java |
| --- | --- | --- |
| Muốn caller Java bắt đúng ngoại lệ callback | Không clear; dọn tài nguyên và return | Java thấy exception gốc |
| Có lỗi được chấp nhận và fallback được định nghĩa | Clear sau khi quyết định xử lý | Java thấy fallback thay cho exception |
| Muốn biến lỗi A thành lỗi B | Lấy Throwable, clear, tạo/`Throw` lỗi phù hợp | Java thấy lỗi B (tùy cách giữ cause) |
| Chỉ muốn chụp thông tin debug | Đừng gọi bừa `ExceptionDescribe` rồi return | Tránh vô ý clear lỗi |
| Muốn tiếp tục gọi JNI API thông thường | Clear trước khi tiếp tục | Cần bảo đảm không làm mất thông tin lỗi quan trọng |

## 7. Ví dụ thực hành hoàn chỉnh Java 17+ / JNI C

Ví dụ dùng một class `demo.jni.PendingDemo` với ba phương thức `native`, minh họa cả ba tình huống:

1. **Gọi Java thành công:** kết quả phép chia được dùng.
2. **Gọi Java ném ArithmeticException:** native code phát hiện bằng `ExceptionCheck` và **clear** theo chính sách trả fallback.
3. **Gọi Java ném ArithmeticException khác:** native code phát hiện nhưng **không clear**, để Java `try/catch` bắt lỗi gốc.
4. **Gọi phương thức Java trả về object:** kiểm tra lỗi sau `CallStaticObjectMethod`, không nhầm kết quả object với trạng thái exception.

### 7.1. Tệp src/demo/jni/PendingDemo.java

```java
package demo.jni;

public final class PendingDemo {
    static {
        System.loadLibrary("pendingdemo");
    }

    private static int compute(int a, int b) {
        return a / b;
    }

    private static String compose(String who) {
        return "Hi " + who;
    }

    public static native int recover(int a, int b, int fallback);
    public static native int propagate(int a, int b);
    public static native String greeting(String who);

    public static void main(String[] args) {
        System.out.println("Normal: " + recover(8, 2, -1));
        System.out.println("Recovered: " + recover(8, 0, -1));

        try {
            propagate(8, 0);
            System.out.println("Unexpected: no exception");
        } catch (ArithmeticException error) {
            System.out.println("Propagated: " + error.getMessage());
        }

        System.out.println("Object: " + greeting("JNI"));
    }
}
```

`compute(8, 0)` ném `ArithmeticException` vì phép chia số nguyên cho 0. Phương thức `compute` và `compose` là Java thường, nhưng C có thể gọi chúng bằng `GetStaticMethodID` và `CallStatic<Type>Method` ngay cả khi chúng khai báo `private` trong class mà JNI method được định nghĩa.

### 7.2. Tạo class file và JNI header

Chạy từ thư mục gốc của ví dụ, trên shell Linux/macOS:

```bash
mkdir -p build/classes build/include build/native

javac -h build/include \
  -d build/classes \
  src/demo/jni/PendingDemo.java
```

`javac -h` sinh `build/include/demo_jni_PendingDemo.h`. Phần prototype chính xác đã được xác nhận bằng `javac -h` trên JDK 24:

```c
JNIEXPORT jint JNICALL Java_demo_jni_PendingDemo_recover
  (JNIEnv *, jclass, jint, jint, jint);

JNIEXPORT jint JNICALL Java_demo_jni_PendingDemo_propagate
  (JNIEnv *, jclass, jint, jint);

JNIEXPORT jstring JNICALL Java_demo_jni_PendingDemo_greeting
  (JNIEnv *, jclass, jstring);
```

Chữ ký được sinh từ các native methods:

- `recover(int,int,int):int` → `(III)I`.
- `propagate(int,int):int` → `(II)I`.
- `greeting(String):String` → `(Ljava/lang/String;)Ljava/lang/String;`.

### 7.3. Tệp PendingDemo.c

```c
#include <jni.h>
#include "demo_jni_PendingDemo.h"

/* Phục hồi bằng fallback: cố ý clear exception để minh họa.
   Production: chỉ clear những loại lỗi đã được phân loại cho phép. */
JNIEXPORT jint JNICALL Java_demo_jni_PendingDemo_recover(
        JNIEnv *env, jclass cls, jint a, jint b, jint fallback) {
    jmethodID mid = (*env)->GetStaticMethodID(
            env, cls, "compute", "(II)I");

    if (mid == NULL) {
        /* Lookup có thể đã đặt pending NoSuchMethodError.
           Không gọi JNI API thông thường khi có pending exception. */
        return 0;
    }

    jint result = (*env)->CallStaticIntMethod(env, cls, mid, a, b);

    if ((*env)->ExceptionCheck(env)) {
        (*env)->ExceptionClear(env);
        return fallback;
    }

    return result;
}

/* Giữ nguyên pending exception để Java caller bắt. */
JNIEXPORT jint JNICALL Java_demo_jni_PendingDemo_propagate(
        JNIEnv *env, jclass cls, jint a, jint b) {
    jmethodID mid = (*env)->GetStaticMethodID(
            env, cls, "compute", "(II)I");

    if (mid == NULL) {
        return 0; /* Để lỗi lookup lan truyền. */
    }

    jint result = (*env)->CallStaticIntMethod(env, cls, mid, a, b);

    if ((*env)->ExceptionCheck(env)) {
        return 0; /* KHÔNG gọi ExceptionClear. */
    }

    return result;
}

/* Gọi Java method trả về String và kiểm tra pending exception. */
JNIEXPORT jstring JNICALL Java_demo_jni_PendingDemo_greeting(
        JNIEnv *env, jclass cls, jstring who) {
    jmethodID mid = (*env)->GetStaticMethodID(
            env, cls, "compose",
            "(Ljava/lang/String;)Ljava/lang/String;");

    if (mid == NULL) {
        return NULL;
    }

    jstring result = (jstring) (*env)->CallStaticObjectMethod(
            env, cls, mid, who);

    if ((*env)->ExceptionCheck(env)) {
        return NULL; /* Để Java nhận exception gốc. */
    }

    return result;
}
```

**Lưu ý kết quả trả về:** trong `propagate`, `return 0` lúc exception pending không có nghĩa “trả 0 cho Java”. Nó chỉ thoát hàm C hợp lệ và để JVM đưa `ArithmeticException` lên Java. Trong `recover`, sau `ExceptionClear` thì `fallback` mới **thực sự là giá trị Java nhận được**.

**Local reference trong `greeting`:** `jstring result` là local reference trả về từ JNI; hàm native có thể `return result` cho Java. Không gọi `DeleteLocalRef(result)` trước khi trả nó. Nếu dùng thêm temporary references, cần quản lý riêng.

**Phạm vi bắt lỗi của `recover`:** trong ví dụ ngắn này, `ExceptionClear` xử lý mọi exception mà `compute` có thể ném. Vì `compute` chỉ thực hiện phép chia, nhánh thử với `b=0` có chủ đích. Trong hệ thống thật, không tự động nuốt mọi `Throwable`; xem mục 8 để phân loại trước khi clear/đổi lỗi.

### 7.4. Biên dịch native library trên Linux

Cần JDK 17+ và GCC. `JAVA_HOME` phải trỏ đến **JDK** có thư mục `include/jni.h`:

```bash
gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  -o build/native/libpendingdemo.so \
  PendingDemo.c

java -Djava.library.path=build/native \
  -cp build/classes \
  demo.jni.PendingDemo
```

**Stdout dự kiến chính xác khi biên dịch, nạp thư viện và thực thi thành công:**

```text
Normal: 4
Recovered: -1
Propagated: / by zero
Object: Hi JNI
```

Vì sao?

- `recover(8,2,-1)` gọi `compute` thành công, `ExceptionCheck` trả `JNI_FALSE`, kết quả là `4`.
- `recover(8,0,-1)` gọi `compute` ném `ArithmeticException`, native gọi `ExceptionClear` và trả fallback `-1`.
- `propagate(8,0)` nhận pending `ArithmeticException`, không clear và trở về; Java bắt lỗi, `getMessage()` là `/ by zero` theo hành vi Java số nguyên chuẩn.
- `greeting("JNI")` gọi `compose` và trả chuỗi `Hi JNI`.

Trường hợp JVM hiện đại cảnh báo quyền native access, có thể phát sinh thông báo **trên stderr**, không làm thay đổi bốn dòng stdout trên khi chương trình có quyền gọi JNI. Tùy chính sách JDK/module, có thể cần tham số `--enable-native-access=ALL-UNNAMED` cho chương trình classpath nếu runtime hỗ trợ hoặc yêu cầu.

### 7.5. Biên dịch trên macOS hoặc Windows

**macOS:** sau khi đã chạy `javac -h` và tạo thư mục `build/native`:

```bash
clang -O2 -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include \
  -o build/native/libpendingdemo.dylib \
  PendingDemo.c

java -Djava.library.path=build/native \
  -cp build/classes \
  demo.jni.PendingDemo
```

**Windows:** mở Visual Studio Developer Command Prompt có `cl`, JDK và `JAVA_HOME`:

```bat
mkdir build\classes
mkdir build\include
mkdir build\native

javac -h build\include -d build\classes src\demo\jni\PendingDemo.java

cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /I"build\include" PendingDemo.c /Febuild\native\pendingdemo.dll

java -Djava.library.path=build\native -cp build\classes demo.jni.PendingDemo
```

Thư viện Java yêu cầu bằng `System.loadLibrary("pendingdemo")` có tên thường gặp `libpendingdemo.so` (Linux), `libpendingdemo.dylib` (macOS) hoặc `pendingdemo.dll` (Windows). Đảm bảo JDK và C compiler cùng kiến trúc (x64/ARM64…). Nếu các thư mục build đã tồn tại, lệnh `mkdir` trên Windows có thể thông báo tồn tại; không làm thay đổi logic ví dụ.

## 8. Xử lý chọn lọc: chỉ phục hồi lỗi đã biết, giữ nguyên lỗi khác

Ví dụ `recover` trong mục 7 ưu tiên thể hiện `ExceptionCheck`/`ExceptionClear` dễ hiểu. Một thư viện đáng tin cậy cần chính sách hẹp hơn: **chỉ khôi phục sau loại lỗi đã được xem là recoverable**, không vô tình nuốt `OutOfMemoryError`, `LinkageError` hoặc bug từ Java callback.

Nếu muốn phân loại ngoại lệ, có thể:

1. Chuẩn bị `jclass` của loại lỗi mong đợi **trước** lời gọi Java dễ ném exception.
2. Sau lời gọi, lấy `jthrowable` bằng `ExceptionOccurred` (đây là **local reference**; pending vẫn tồn tại).
3. Gọi `ExceptionClear` **trước** các thao tác JNI thông thường như `IsInstanceOf`.
4. Nếu lỗi là loại mong đợi, dọn local references và trả fallback.
5. Nếu lỗi không mong đợi, `Throw(env, savedThrowable)` để làm nó pending trở lại, dọn local references (được phép khi pending) rồi return.

Đoạn C sau **chỉ là minh họa xử lý trong một hàm đã có `env`, `cls`, `mid`, `a`, `b` và `fallback` hợp lệ**; chưa phải một hàm độc lập để biên dịch riêng:

```c
/* Nên tra class khi chưa có pending exception. */
jclass arithmeticClass =
        (*env)->FindClass(env, "java/lang/ArithmeticException");

if (arithmeticClass == NULL) {
    return 0;  /* Lỗi lookup có thể đang pending. */
}

jint value = (*env)->CallStaticIntMethod(env, cls, mid, a, b);

jthrowable original = (*env)->ExceptionOccurred(env);
if (original == NULL) {
    (*env)->DeleteLocalRef(env, arithmeticClass);
    return value;
}

/* original là local ref; lúc này exception vẫn pending. */
(*env)->ExceptionClear(env);

/* Sau khi clear mới được gọi JNI API thông thường. */
jboolean expected =
        (*env)->IsInstanceOf(env, original, arithmeticClass);

if ((*env)->ExceptionCheck(env)) {
    /* Nếu bước phân loại gặp lỗi mới, giữ lỗi mới. */
    (*env)->DeleteLocalRef(env, arithmeticClass);
    (*env)->DeleteLocalRef(env, original);
    return 0;
}

(*env)->DeleteLocalRef(env, arithmeticClass);

if (expected == JNI_TRUE) {
    (*env)->DeleteLocalRef(env, original);
    return fallback;
}

/* Lỗi không thuộc loại cho phép: khôi phục exception gốc. */
(*env)->Throw(env, original);
(*env)->DeleteLocalRef(env, original);
return 0;
```

Cách này còn minh họa **phân biệt state và handle**: `ExceptionClear` xóa pending status nhưng `original` là local reference hợp lệ tới exception và vẫn có thể dùng để `Throw` lại. Nếu trong lúc xử lý có JNI operation ném exception mới, cần chính sách tránh ghi đè hoặc đánh mất lỗi mới đó. Một hệ thống production cũng phải giải quyết việc phân loại subclass, ghi log với ngữ cảnh, bảo toàn *cause* nếu chuyển sang loại lỗi khác.

**Không cần dùng cơ chế phức tạp này chỉ để propagate.** Khi không muốn xử lý, sau `ExceptionCheck` chỉ cleanup được phép rồi return; đây là đường đơn giản và ít lỗi nhất.

## 9. Cleanup khi callback đã ném ngoại lệ

Trong JNI, native code thường nắm giữ tài nguyên do các JNI API cấp: local reference, buffer chuỗi, mảng primitive, monitor, hoặc bộ nhớ C. Khi Java callback ném exception, vẫn phải dọn những tài nguyên này **mà không gọi JNI API không an toàn**.

Ví dụ một **đoạn C minh họa** (không phải phương thức chạy độc lập; giả định `env`, `array`, `clazz` và `methodId` hợp lệ; `array` là `jintArray`):

```c
jint *elements = (*env)->GetIntArrayElements(env, array, NULL);
if (elements == NULL) {
    /* Có thể đã pending OutOfMemoryError; không dùng elements. */
    return;
}

/* Gọi Java callback (method void) có thể ném exception. */
(*env)->CallStaticVoidMethod(env, clazz, methodId);

if ((*env)->ExceptionCheck(env)) {
    /* ReleaseIntArrayElements thuộc nhóm cleanup an toàn lúc pending.
       JNI_ABORT: không chép thay đổi từ buffer native về mảng Java. */
    (*env)->ReleaseIntArrayElements(env, array, elements, JNI_ABORT);
    return; /* Không clear => Java nhận lỗi gốc. */
}

/* Nhánh thành công: giải phóng buffer. */
(*env)->ReleaseIntArrayElements(env, array, elements, JNI_ABORT);
```

Tương tự, khi đã mượn dữ liệu từ `GetStringUTFChars`, phải gọi `ReleaseStringUTFChars` tương ứng; khi tạo local reference phải cân nhắc `DeleteLocalRef`; khi dùng `MonitorEnter` thành công phải `MonitorExit` ở đường lỗi. Với `GetPrimitiveArrayCritical`/`GetStringCritical`, tuân thủ thêm hạn chế *critical region* và trả tài nguyên sớm, tránh callback tùy tiện trong thời gian critical; ví dụ trên dùng `GetIntArrayElements` thông thường.

**Cần lưu ý:** cleanup không phải là thao tác “nuốt exception”. `DeleteLocalRef`, `ReleaseStringUTFChars` hay `ReleaseIntArrayElements` chỉ giải phóng tài nguyên tương ứng, không tự động xóa pending exception. Mục tiêu là vừa không rò rỉ bộ nhớ/khóa, vừa cho phép Java nhận lỗi ban đầu.

### Không được bỏ qua ngoại lệ để gọi JNI tiếp

Mẫu sai phổ biến:

```c
jobject result = (*env)->CallObjectMethod(env, obj, methodId);
jclass type = (*env)->GetObjectClass(env, result); /* SAI nếu có pending. */
```

Đúng hơn:

```c
jobject result = (*env)->CallObjectMethod(env, obj, methodId);

if ((*env)->ExceptionCheck(env)) {
    /* Cleanup an toàn, rồi return; hoặc clear theo chính sách. */
    return;
}

if (result != NULL) {
    jclass type = (*env)->GetObjectClass(env, result);
    if (type == NULL || (*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, result);
        return;
    }

    /* Dùng type ở đây khi không có exception. */
    (*env)->DeleteLocalRef(env, type);
}
if (result != NULL) {
    (*env)->DeleteLocalRef(env, result);
}
```

Đoạn sau cũng **chỉ là ví dụ trong ngữ cảnh native method trả `void`**, không phải hàm đầy đủ. Nó thể hiện phải kiểm tra lỗi không chỉ sau `CallObjectMethod`, mà sau những JNI API tiếp theo có khả năng thất bại.

## 10. Các tình huống phân biệt cần nhớ

### Tình huống 1: callback trả Java null hợp lệ

`CallStaticObjectMethod` trả `NULL`, nhưng `ExceptionCheck` trả `JNI_FALSE`. Đây có thể đơn giản là Java method đã `return null`. Không tự tạo exception chỉ vì có `NULL` nếu hợp đồng API cho phép trả null.

### Tình huống 2: callback ném lỗi nhưng giá trị C trông bình thường

`CallStaticIntMethod` trả một `jint` nào đó, nhưng `ExceptionCheck` trả `JNI_TRUE`. Không dùng giá trị đó; chỉ xử lý exception. Không có cam kết giá trị trả về hữu ích cho nhánh lỗi.

### Tình huống 3: một JNI lookup đã thất bại trước khi gọi Java

`GetStaticMethodID` trả `NULL` và pending `NoSuchMethodError`. Không tiếp tục gọi `CallStaticIntMethod` với `jmethodID NULL`. Trả về để lỗi lan truyền hoặc clear theo chính sách.

### Tình huống 4: gọi ExceptionDescribe để debug rồi mất lỗi

`ExceptionDescribe` in backtrace và **clear pending**. Nếu native code trở về ngay, Java không còn exception ban đầu. Để propagate, tránh gọi API đó hoặc phải chủ động xây dựng quy trình lưu/clear/rethrow đúng cách.

### Tình huống 5: một callback có exception, sau đó JNI callback thứ hai cũng được gọi

Sai ở chỗ tiếp tục `Call*Method` khác trong khi pending exception chưa được clear. Chọn một trong hai: xử lý xong/clear lỗi thứ nhất trước khi gọi tiếp, hoặc trả về và để Java xử lý lỗi đầu tiên.

### Tình huống 6: nhiều native threads cùng callback vào JVM

Pending exception thuộc **thread tạo ra nó**. Một thread không thể đọc hoặc clear ngoại lệ pending của thread khác chỉ bằng cách dùng lại `JNIEnv*`. Native worker phải attach JVM và lấy `JNIEnv*` của chính nó; cơ chế báo lỗi xuyên thread cần được thiết kế như truyền dữ liệu/Java Throwable reference hợp lệ, không phải chia sẻ con trỏ env.

## 11. Debug và xác thực bằng -Xcheck:jni

Trên HotSpot/OpenJDK, `-Xcheck:jni` giúp phát hiện nhiều vi phạm JNI. Ví dụ:

```bash
java -Xcheck:jni \
  -Djava.library.path=build/native \
  -cp build/classes \
  demo.jni.PendingDemo
```

Nó kiểm tra thêm các điều kiện như JNI arguments, invalid references, một số tình huống gọi JNI API không an toàn khi có pending exception. Thường dùng trong **dev/test**, có chi phí hiệu năng và không bảo đảm phát hiện mọi lỗi. Một số JNI misuse nghiêm trọng có thể làm JVM dừng hoặc báo lỗi.

Khi chẩn đoán một hệ thống thực tế:

1. Xác định **JNI call nào đã gọi Java** và có thể ném: `Call<Type>Method`, `CallStatic<Type>Method` hoặc `CallNonvirtual<Type>Method`.
2. Kiểm tra `ExceptionCheck` đặt **ngay sau call** chưa; kiểm tra lookup `GetMethodID`/`GetStaticMethodID` trước call đã hợp lệ chưa.
3. Nếu exception pending, đi nhánh propagate hoặc clear; **không** gọi tiếp JNI API không an toàn.
4. Nếu clear, kiểm tra lý do rõ ràng: lỗi nào được phép recover, có che mất lỗi bất ngờ không?
5. Nếu propagate, bảo đảm C resources, local JNI refs, borrowed buffers và monitor được cleanup.
6. Xác nhận Java caller có xử lý đúng kiểu lỗi và giữ nguyên stack trace/cause theo yêu cầu.
7. Kiểm tra C compiler, JDK headers, library loading, architecture; lỗi không tìm thấy `.so`/`.dll` là vấn đề khác với pending exception sau callback.

**Lưu ý:** `-Xcheck:jni` không phải công cụ thay thế code review và kiểm thử error paths. Cách đặt `ExceptionCheck`/`ExceptionOccurred` đúng chỗ và kiểm soát vòng đời JNI resources vẫn là trách nhiệm của người viết native code.

## 12. Lỗi phổ biến và cách sửa

| Lỗi | Nguyên nhân/hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `CallIntMethod` rồi dùng ngay số trả về | Java callback có thể ném exception | `ExceptionCheck` trước khi dùng kết quả |
| Chỉ kiểm tra `result == NULL` sau `CallObjectMethod` | `null` hợp lệ và pending exception là hai trạng thái khác nhau | Xét `ExceptionCheck`, sau đó mới đánh giá null |
| Tiếp tục `FindClass`/`GetMethodID` khi pending | Không an toàn theo JNI Specification | Return hoặc `ExceptionClear` trước JNI calls khác |
| `ExceptionOccurred` trả object nên tưởng exception đã clear | API chỉ trả local reference | Muốn clear phải gọi `ExceptionClear` rõ ràng |
| Gọi `ExceptionDescribe` để log rồi return | Đặc tả nói API **clear** exception | Không dùng nó nếu muốn tự động propagate |
| Gọi `ExceptionClear` cho mọi lỗi | Nuốt cả lỗi không thể phục hồi | Phân loại lỗi, clear có chủ đích |
| Quên `DeleteLocalRef` cho `jthrowable` đã lấy | Tăng local references trong vòng lặp | Dọn local ref khi không cần |
| Dọn tài nguyên bằng API JNI không thuộc allowlist khi pending | Có thể gây warning, lỗi native | Chỉ cleanup qua API được phép |
| Gọi `ThrowNew` khi đang pending exception cũ | Quy tắc thao tác JNI không an toàn | Giữ nguyên lỗi cũ, hoặc clear có chủ đích trước |
| Dùng `JNIEnv*` của thread khác | Vi phạm tính gắn luồng của JNI | Attach thread và dùng env của chính thread |
| Giả định `return 0` sẽ về Java dù đang pending | Java nhận exception, không nhận giá trị bình thường | Xác định đúng propagate vs recover |
| Test chỉ nhánh thành công | Bỏ sót lỗi JNI, cleanup, exception policy | Test normal, recover, propagate, object-null, lookup-failure |

## 13. Tự kiểm tra

**Câu 1.** Sau `CallStaticIntMethod`, bạn nhận `0` và `ExceptionCheck` trả `JNI_TRUE`. Java caller nên hiểu đây là `0` hay exception?

**Đáp án:** Exception. Kết quả primitive chỉ có ý nghĩa khi không có pending exception; nếu native return mà không clear, Java thấy exception.

**Câu 2.** `ExceptionCheck` có làm mất lỗi không?

**Đáp án:** Không. Nó chỉ trả boolean theo trạng thái hiện tại, không tạo local exception ref và không clear.

**Câu 3.** `ExceptionOccurred` khác `ExceptionCheck` ở đâu?

**Đáp án:** Nó trả `jthrowable` là local reference tới exception đang chờ; pending vẫn giữ nguyên. Phải quản lý vòng đời local reference nếu lưu `jthrowable`.

**Câu 4.** Sau khi gọi Java callback ném `ArithmeticException`, mã C muốn để Java tự xử lý thì cần làm gì?

**Đáp án:** Kiểm tra pending, cleanup bằng các thao tác được phép, **không clear**, return khỏi native method. Java nhận `ArithmeticException` và có thể `catch`.

**Câu 5.** Mã C muốn bỏ qua ngoại lệ để trả fallback thì cần làm gì?

**Đáp án:** Chỉ làm khi chính sách cho phép, gọi `ExceptionClear` để xóa pending rồi trả fallback. Với hệ thống thật cần phân loại lỗi; không nuốt mọi `Throwable`.

**Câu 6.** `ExceptionDescribe` có phải API log nhưng giữ nguyên pending?

**Đáp án:** Không. Theo JNI Specification nó in exception/backtrace và **clear pending** như side effect.

**Câu 7.** Trong lúc pending, có thể gọi `ReleaseStringUTFChars` để trả buffer đã mượn không? Có nên gọi `NewStringUTF` ngay không?

**Đáp án:** `ReleaseStringUTFChars` là cleanup được phép; `NewStringUTF` không thuộc allowlist khi còn pending, nên phải clear/return trước.

**Câu 8.** `CallStaticObjectMethod` trả `NULL` nhưng `ExceptionCheck` trả `JNI_FALSE`. Điều đó có nhất thiết là lỗi?

**Đáp án:** Không. Java callback có thể trả `null` hợp lệ; xử lý theo hợp đồng API.

## 14. Ghi nhớ nhanh

- **Sau mỗi JNI call gọi Java**, kiểm tra pending exception **trước khi dùng kết quả hoặc gọi JNI tiếp**.
- `ExceptionCheck` chỉ đọc boolean; `ExceptionOccurred` trả local `jthrowable`; cả hai **không clear**.
- `ExceptionClear` chủ động xóa; `ExceptionDescribe` **cũng xóa** pending exception.
- **Propagate:** dọn tài nguyên được phép và return, không clear; Java bắt exception gốc.
- **Recover:** clear có chính sách, mới dùng fallback hoặc tiếp tục JNI; đừng nuốt lỗi bất ngờ.
- Khi đang pending, chỉ dùng những JNI APIs an toàn theo đặc tả (đặc biệt nhóm **release/delete/exception**).
- `-Xcheck:jni` hữu ích trong kiểm thử, nhưng không thay kiểm tra logic và vòng đời tài nguyên native.

## Tài liệu chính thức

- [JNI Specification, Java 17 — Design Overview: Java Exceptions, Exception Handling](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html#java-exceptions)
- [JNI Specification, Java 17 — ExceptionOccurred / ExceptionDescribe / ExceptionClear / ExceptionCheck](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#exceptions)
- [JNI Specification — Calling Static Methods](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#calling-static-methods)
- [JNI Specification — Calling Instance Methods](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#calling-instance-methods)
- [Java SE 17 — javac -h (JNI headers)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle Java SE 17 Troubleshooting — -Xcheck:jni](https://docs.oracle.com/en/java/javase/17/troubleshoot/command-line-options1.html)

**Kết luận:** pending exception là tín hiệu Java callback **chưa kết thúc thành công** từ góc nhìn JNI. Kiểm tra ngay bằng `ExceptionCheck`/`ExceptionOccurred`, rồi chọn **giữ nguyên để lan truyền** hoặc **clear để phục hồi có chủ đích**. Chỉ dùng kết quả và gọi JNI APIs tiếp khi trạng thái exception đã được xử lý đúng.
