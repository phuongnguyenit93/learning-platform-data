# Phạm vi và giới hạn sử dụng UnregisterNatives trong JNI

`UnregisterNatives` là một hàm hiếm khi cần dùng trong JNI (Java Native Interface). Nó **hủy liên kết giữa các phương thức `native` của một lớp Java cụ thể và các hàm native đang thực thi chúng**, trả lớp đó về trạng thái trước khi các phương thức native được liên kết hoặc được đăng ký. Nó **không** có nghĩa là dỡ file `.so`/`.dll` ra khỏi tiến trình, hủy các Java objects, giải phóng mọi vùng nhớ C/C++, hay thay thế an toàn mã native khi chương trình đang chạy.

Đặc tả JNI nói rõ API này **không nên dùng trong native code thông thường**; nó dành cho một số chương trình đặc biệt cần cơ chế nạp/liên kết lại. Vì thế, muốn dùng đúng phải hiểu **phạm vi theo `jclass`**, cách nó tương tác với `RegisterNatives`, cơ chế tìm ký hiệu native theo tên, vòng đời thư viện và rủi ro khi nhiều thread đang gọi native method.

## 1. API chính xác và ý nghĩa

Trong `jni.h`, thông qua bảng hàm `JNIEnv`:

```c
jint UnregisterNatives(JNIEnv *env, jclass clazz);
```

Ở C, thường gọi qua:

```c
jint rc = (*env)->UnregisterNatives(env, targetClass);
```

Ở C++:

```cpp
jint rc = env->UnregisterNatives(targetClass);
```

Các tham số và mã trả về:

| Thành phần | Ý nghĩa | Điều cần bảo đảm |
| --- | --- | --- |
| `env` | JNI environment của thread hiện tại | Không truyền `NULL`; không dùng `JNIEnv*` của thread khác |
| `clazz` | Một đối tượng `java.lang.Class` được biểu diễn bằng `jclass` | Là class đích hợp lệ, không phải instance `jobject` hay tên chuỗi |
| Trả về `0`, tức `JNI_OK` | JNI operation thành công | Không suy ra thư viện đã unload hay đã giải phóng tài nguyên |
| Trả về giá trị âm | Thao tác thất bại | Kiểm tra JNI exception đang pending và áp dụng chính sách báo lỗi rõ ràng |

Không có tham số `methodName`, `jmethodID` hay `nMethods` ở `UnregisterNatives`. Vì vậy đây **không phải** API “unregister đúng một method”. Phạm vi của lời gọi là **các native methods của class đã truyền**.

Đặc tả JNI nêu: class trở lại trạng thái trước khi được liên kết hoặc đăng ký với native function của nó. Câu này quan trọng hơn cách diễn đạt đơn giản “xóa pointer”: một lần gọi Java native method về sau có thể lại đi qua quá trình tìm/liên kết native function theo cơ chế JNI thông thường, nếu có một implementation phù hợp khả dụng.

**Không nhầm với `RegisterNatives`:**

```c
jint RegisterNatives(
    JNIEnv *env,
    jclass clazz,
    const JNINativeMethod *methods,
    jint nMethods);
```

`RegisterNatives` nhận mảng `JNINativeMethod` chứa tên, descriptor và địa chỉ hàm C/C++; `UnregisterNatives` **không nhận mảng đó** mà thao tác trên trạng thái native linkage của class đích.

## 2. Phạm vi chính xác: lớp Java nào bị ảnh hưởng?

Xét hai Java classes khác nhau:

```java
final class AudioNative {
    static native int decode(byte[] bytes);
}

final class VideoNative {
    static native int decode(byte[] bytes);
}
```

Dù cả hai method có tên `decode` và descriptor giống nhau `([B)I`, chúng thuộc **hai lớp khác nhau**. Việc gọi:

```c
(*env)->UnregisterNatives(env, audioClass);
```

chỉ nhằm thay đổi liên kết native của `AudioNative`. Nó không phải lệnh xóa mọi method tên `decode` trong JVM; không tự động quét mọi class loader, không hủy method Java thường và không gửi yêu cầu đóng tất cả thư viện native.

| Câu hỏi về phạm vi | Kết luận |
| --- | --- |
| Có giới hạn vào class được truyền qua `clazz` không? | **Có**; đây là API thao tác trên native methods của một class |
| Có tham số chỉ chọn một native method trong class không? | **Không**; muốn thiết kế thao tác theo từng chức năng phải dùng cơ chế khác |
| Có xóa bytecode, khai báo method, field hoặc class khỏi JVM không? | **Không**; định nghĩa Java class vẫn tồn tại |
| Có xóa native methods của class khác cùng tên ở class loader khác không? | Không phải thao tác toàn cục như vậy; mỗi class runtime có identity riêng |
| Có gọi `System.loadLibrary` lần hai để nạp bản binary khác không? | **Không**; lệnh này không điều khiển native library loading |
| Có dừng native stack frame đang thực thi không? | **Không có bảo đảm như vậy**; không xem đây là cơ chế cancel/stop |
| Có tự giải phóng `malloc`, file descriptor hay `NewGlobalRef` không? | **Không**; owner riêng phải dọn theo hợp đồng |
| Có ép `JNI_OnUnload` chạy không? | **Không**; đó là một lifecycle hook khác |

Ở mức Java, **class identity không chỉ là class name**: class được định danh bởi tên và defining class loader. Hai class cùng binary name do hai loader khác nhau định nghĩa là hai class runtime khác nhau. Truyền đúng `jclass` trong `UnregisterNatives` là thiết yếu; đừng dùng heuristic dựa trên tên rồi giả định tất cả bản sao class của plugin đã bị ảnh hưởng.

Khi một class có nhiều native methods, hãy xem `UnregisterNatives` là thao tác thay đổi **toàn bộ nhóm native bindings của class đó**. Nếu muốn một API có thể tắt riêng chức năng A nhưng vẫn giữ chức năng B, cách phổ biến hơn là giữ bindings cố định và dùng Java/native dispatch với trạng thái kiểm soát, không unregister toàn class.

## 3. Ba vòng đời rất khác nhau

```text
                     Java VM / process
                            |
         +------------------+------------------+
         |                  |                  |
   Java Class         Native method        Native library
 (Class identity)       bindings            (.so/.dll)
         |                  |                  |
   defined by loader  RegisterNatives      System.loadLibrary
   may be unloaded    UnregisterNatives    JNI_OnLoad / JNI_OnUnload
   with its loader    method resolution    OS/JVM library handles
         |                  |                  |
         +------------------+------------------+
                            |
             Native heap / file / global refs
             riêng biệt, chủ sở hữu phải dọn
```

Ba vòng đời này có liên quan nhưng **không tương đương**:

1. **Định nghĩa Java class:** JVM có class, method declarations và class loader. Unregister không xóa class.
2. **Native method linkage:** JVM biết hoặc đang tìm địa chỉ C/C++ cho một khai báo Java `native`. Đây là lớp mà `UnregisterNatives` tác động.
3. **Native library lifecycle:** `System.load`/`System.loadLibrary` quản lý việc nạp thư viện vào JVM; `JNI_OnLoad` được gọi khi thư viện được nạp nếu được export, còn `JNI_OnUnload` gắn với điều kiện unload thư viện/class loader theo đặc tả. Unregister **không gọi** các thao tác này.

Do đó không được suy luận:

```text
UnregisterNatives(clazz)
    != System.loadLibrary(...) đảo ngược
    != dlclose(...) / FreeLibrary(...)
    != JNI_OnUnload(...) ngay lập tức
    != free(nativeState)
    != System.gc() hoặc class unloading
    != thay file native đang chạy bằng build khác
```

Ngay cả khi các native methods của một class đã bị unregistered, thư viện C/C++ đã được load trước đó có thể vẫn được JVM giữ lại. Các symbol khác trong cùng thư viện vẫn có thể phục vụ class khác; các global variables, native threads, callbacks và memory allocations không được JNI tự động thu hồi chỉ nhờ unregister.

### `JNI_OnUnload` có vai trò gì?

`JNI_OnUnload` là một **hàm tùy chọn do native library export**, được JVM gọi theo lifecycle unload thư viện liên quan tới class loader, chứ không phải một callback trực tiếp của `UnregisterNatives`. Class loader được GC thu hồi và native library đủ điều kiện unload là câu chuyện khác; thời điểm/khả năng GC và unloading không phải điều ứng dụng được phép dựa vào để lập tức giải phóng tài nguyên.

Nếu native library có state cần hủy, hãy cung cấp lifecycle API rõ ràng như `close()`/`shutdown()` với ownership riêng, quản lý thread và handle đúng cách. Không dùng unregister để “đóng” database client, socket, GPU context hay native object.

## 4. Sau khi unregister: tại sao chưa chắc sẽ luôn nhận UnsatisfiedLinkError?

Phải phân biệt **đăng ký tường minh** và **liên kết theo tên JNI**.

### Liên kết bằng `RegisterNatives`

```c
static jint JNICALL impl(JNIEnv *env, jclass clazz, jint x) {
    (void)env;
    (void)clazz;
    return x + 1;
}

JNINativeMethod methods[] = {
    {"next", "(I)I", (void *)impl}
};

jint rc = (*env)->RegisterNatives(env, targetClass, methods, 1);
```

Đây là **đoạn minh họa C**, cần có `env`, `targetClass`, header JNI và class Java khai báo `static native int next(int)`. Mảng `JNINativeMethod` chứa:

- `name`: tên Java native method (modified UTF-8).
- `signature`: JNI descriptor, `(I)I` nghĩa là nhận `int` và trả `int`.
- `fnPtr`: địa chỉ hàm C/C++ thực thi, phải có kiểu ABI/calling convention phù hợp.

Khi `RegisterNatives` thành công, JVM dùng con trỏ native được đăng ký cho method đó.

### Liên kết động bằng tên symbol

JNI cũng có cơ chế xác định native function từ tên symbol được export trong native library tương ứng, ví dụ Java:

```java
final class NativeTarget {
    static native int twice(int value);
}
```

Thư viện có thể export một symbol JNI tương ứng như:

```c
JNIEXPORT jint JNICALL
Java_NativeTarget_twice(JNIEnv *env, jclass clazz, jint value);
```

Đây là **khai báo**, không phải implementation độc lập. Trong trường hợp này, khi native binding được đưa về trạng thái chưa liên kết, JVM có thể **tìm được symbol** để liên kết lại lúc Java gọi tiếp. Do đó:

> “Đã gọi `UnregisterNatives` nên method chắc chắn sẽ ném `UnsatisfiedLinkError` mãi mãi” là một kết luận **sai**.

Ngược lại, nếu implementation được đăng ký qua `RegisterNatives` và **không có symbol JNI tương ứng được export để JVM tự tìm**, một lời gọi Java sau unregister **thường không tìm được implementation** và ném `UnsatisfiedLinkError`. Bài thực hành dưới đây cố ý xây đúng điều kiện đó, rồi đăng ký lại để chứng minh method vẫn tồn tại và có thể liên kết lại.

### Unregister không phải cơ chế khóa bảo mật

Nếu mục tiêu là “không cho người dùng gọi native function nữa”, unregister không phải ranh giới an ninh. Method có thể được re-register bởi code native đủ quyền hoặc được link lại theo tên; native library và con trỏ function khác vẫn tồn tại. Kiểm soát quyền phải thực hiện ở API Java, module/boundary, cấu hình native access, xác thực và thiết kế ownership phù hợp.

## 5. Mô hình dùng đúng trong chương trình đặc biệt

Đặc tả coi `UnregisterNatives` là API dành cho trường hợp chuyên biệt có điều phối việc liên kết lại, **không phải routine shutdown mặc định**. Khi thực sự cần một chu kỳ đổi bindings trong framework hoặc test harness, tối thiểu phải:

1. **Chỉ rõ class owner:** `jclass` đích, class loader và danh sách các native methods liên quan.
2. **Dừng nhận lời gọi mới:** ứng dụng sở hữu một cơ chế quiescence/điều phối; không cho Java code khác tự do invoke target trong lúc chuyển trạng thái.
3. **Chờ các lời gọi đang chạy kết thúc:** xử lý cả native callbacks, tasks, background threads và references liên quan. Unregister không tự dừng chúng.
4. **Giữ code/library cũ hợp lệ trong lúc còn người dùng:** không `dlclose`/unmap/ghi đè binary vì chỉ vừa unregister.
5. **Gọi unregister trên đúng class:** kiểm tra mã trả về; không coi `0` là bằng chứng đã unload.
6. **Nếu cần, đăng ký/resolve lại một cách có chủ đích:** dùng `RegisterNatives` với đúng tên, descriptor, ABI và function pointers. Kiểm tra kết quả.
7. **Chỉ khôi phục traffic khi trạng thái hoàn chỉnh:** các class và mọi native dependencies đã thống nhất version; có hướng phục hồi khi từng bước lỗi.
8. **Theo dõi resource ownership và class loader riêng:** không lấy JNI linkage làm lifecycle manager cho malloc, global refs và các native subsystems.

Ngay cả quy trình trên cũng chỉ là **nguyên tắc an toàn thiết kế**, không phải bảo đảm rằng mọi JVM hỗ trợ hot swap live native code. Nếu cần thay binary/ABI của một service production, chiến lược thường ổn định hơn là **restart/rolling deployment của JVM** với binary mới.

## 6. Ví dụ hoàn chỉnh: Register → Unregister → Register lại (Java 17+)

Ví dụ minh họa chính xác phạm vi class-level, gồm ba Java files và một C file. Cần tách hai lớp:

- **`NativeRegistry`:** lớp **điều khiển** có hai native methods được JVM liên kết theo tên symbol `Java_NativeRegistry_...`. Lớp này **không** bị unregister.
- **`NativeTarget`:** lớp **đích** có hai native methods được liên kết **chỉ bằng `RegisterNatives`**, không export các symbol `Java_NativeTarget_...`. `UnregisterNatives(env, NativeTarget.class)` sẽ ngắt bindings của cả hai.
- **`UnregisterNativesDemo`:** chương trình Java chạy một chu kỳ tuần tự để quan sát.

Ví dụ viết cho **Linux, OpenJDK/HotSpot JDK 17+ và C compiler có hỗ trợ shared library**. Các phiên bản JDK mới có thể yêu cầu cấu hình native access/module bổ sung; chạy với JDK 17 hoặc 21 là cách đơn giản để thực hành. Không thực hiện unregister khi một thread khác đang sử dụng target.

### File A — `NativeTarget.java`

```java
public final class NativeTarget {
    private NativeTarget() {
    }

    static native int twice(int value);
    static native int add(int left, int right);
}
```

Đây là class bị thao tác unregister. Chú ý không đặt lệnh `System.loadLibrary` và không viết native implementation có tên symbol JNI chuẩn `Java_NativeTarget_twice`/`Java_NativeTarget_add`. Hai method có thể được đăng ký bằng `RegisterNatives` từ thư viện của controller.

### File B — `NativeRegistry.java`

```java
public final class NativeRegistry {
    static {
        System.loadLibrary("unregisterdemo");
    }

    private NativeRegistry() {
    }

    static native void registerTarget(Class<?> targetClass);
    static native void unregisterTarget(Class<?> targetClass);
}
```

Lớp điều khiển load thư viện `unregisterdemo` và có native methods riêng. Cần tách lớp vì nếu để `registerTarget` và `unregisterTarget` cùng class với các native methods đích, thao tác unregister toàn class có thể xóa **cả bindings của chính method điều khiển**, khiến việc đăng ký lại không thể thực hiện theo kế hoạch.

### File C — `UnregisterNativesDemo.java`

```java
public final class UnregisterNativesDemo {
    public static void main(String[] args) {
        // Loading NativeRegistry lần đầu sẽ System.loadLibrary.
        NativeRegistry.registerTarget(NativeTarget.class);

        System.out.println(
                "beforeUnregister=" + NativeTarget.twice(21));
        System.out.println(
                "sum=" + NativeTarget.add(3, 4));

        // Unregister mọi native method của NativeTarget.
        NativeRegistry.unregisterTarget(NativeTarget.class);

        try {
            NativeTarget.twice(21);
            System.out.println("unexpected=linked");
        } catch (UnsatisfiedLinkError expected) {
            // Demo cố ý không export Java_NativeTarget_twice.
            System.out.println(
                    "afterUnregister=UnsatisfiedLinkError");
        }

        // Controller thuộc class khác, vẫn có thể được gọi.
        NativeRegistry.registerTarget(NativeTarget.class);

        System.out.println(
                "afterReRegister=" + NativeTarget.twice(21));
        System.out.println(
                "sumAgain=" + NativeTarget.add(3, 4));
    }
}
```

Code không chứa vòng lặp hay nhiều thread. `UnsatisfiedLinkError` chỉ được bắt để minh họa trường hợp **sau unregister không có native symbol thay thế**; không nên dùng exception này làm logic on/off của API production.

### File D — `unregister_demo.c`

```c
#include "NativeRegistry.h"  /* Header do javac -h sinh ra. */

/* Hai implementation chỉ có linkage nội bộ của C file. */
static jint JNICALL target_twice(JNIEnv *env, jclass owner, jint x) {
    (void)env;
    (void)owner;
    return x * 2;
}

static jint JNICALL target_add(JNIEnv *env, jclass owner,
                              jint a, jint b) {
    (void)env;
    (void)owner;
    return a + b;
}

/*
 * Tên/descriptor phải khớp chính xác hai khai báo Java:
 * NativeTarget.twice(int)    -> (I)I
 * NativeTarget.add(int,int)  -> (II)I
 *
 * JNI dùng void* cho fnPtr theo định nghĩa JNINativeMethod.
 */
static JNINativeMethod target_methods[] = {
    {"twice", "(I)I", (void *)target_twice},
    {"add",   "(II)I", (void *)target_add}
};

/* Chỉ ném lỗi bổ sung nếu chưa có pending Java exception. */
static void throw_if_no_pending(JNIEnv *env,
                                const char *class_name,
                                const char *message) {
    if ((*env)->ExceptionCheck(env)) {
        return;
    }
    jclass type = (*env)->FindClass(env, class_name);
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

/* Export symbol động của CLASS ĐIỀU KHIỂN NativeRegistry. */
JNIEXPORT void JNICALL
Java_NativeRegistry_registerTarget(JNIEnv *env, jclass owner,
                                   jclass target) {
    (void)owner;
    if (target == NULL) {
        throw_if_no_pending(env, "java/lang/NullPointerException",
                            "targetClass");
        return;
    }

    jint result = (*env)->RegisterNatives(
            env, target, target_methods, 2);
    if (result != JNI_OK) {
        /* Nếu JNI đã ném NoSuchMethodError, giữ nguyên exception. */
        throw_if_no_pending(env, "java/lang/UnsatisfiedLinkError",
                            "RegisterNatives failed");
    }
}

/* Export symbol động của CLASS ĐIỀU KHIỂN NativeRegistry. */
JNIEXPORT void JNICALL
Java_NativeRegistry_unregisterTarget(JNIEnv *env, jclass owner,
                                     jclass target) {
    (void)owner;
    if (target == NULL) {
        throw_if_no_pending(env, "java/lang/NullPointerException",
                            "targetClass");
        return;
    }

    jint result = (*env)->UnregisterNatives(env, target);
    if (result != JNI_OK) {
        throw_if_no_pending(env, "java/lang/UnsatisfiedLinkError",
                            "UnregisterNatives failed");
    }
}
```

**Lưu ý về kiểu chữ ký C:**

- `NativeRegistry.registerTarget(Class<?>)` là Java `static native void`, nên JNI entry có hai tham số đầu `JNIEnv*` và `jclass` của lớp điều khiển, theo sau là `jclass target` (một `Class` reference).
- `target_twice` và `target_add` là C functions dành cho các **static** native methods của `NativeTarget`, nên tham số thứ hai cũng là `jclass`. Nếu chuyển chúng thành instance native methods, tham số thứ hai phải là `jobject` và phải kiểm tra signature phù hợp.
- `JNINativeMethod.name` và `signature` phải khớp **chính xác** với các khai báo Java; sai method hoặc khai báo không `native` có thể làm `RegisterNatives` thất bại và ném `NoSuchMethodError`.
- Hai implementation `target_twice`/`target_add` được khai báo `static` ở C để **không export** symbols có tên JNI thông thường của `NativeTarget`. Vì vậy sau unregister, lệnh gọi Java tới target không thể tìm thấy chúng qua convention `Java_NativeTarget_...`; điều này tạo ra nhánh lỗi có thể quan sát.
- Hai exported entry points của `NativeRegistry` **không bị unregister**, vì `clazz` truyền vào `UnregisterNatives` là `NativeTarget.class` chứ không phải `NativeRegistry.class`.

Helper `throw_if_no_pending` kiểm tra exception đang pending trước khi gọi `FindClass`/`ThrowNew`. Nếu `RegisterNatives` đã để lại `NoSuchMethodError`, không nên che nguyên nhân bằng một lỗi khác. Hàm này chỉ được dùng khi cần báo lỗi cho caller; không tạo exception vì một `UnregisterNatives` đã thành công.

### Biên dịch và chạy (Linux)

Đặt cả bốn file trong **cùng thư mục**. Cần `JAVA_HOME` trỏ tới một JDK có `include/jni.h` và `include/linux/jni_md.h`, compiler `cc` tương thích kiến trúc của tiến trình Java.

```bash
javac -encoding UTF-8 -h . \
  NativeTarget.java NativeRegistry.java UnregisterNativesDemo.java

cc -std=c11 -Wall -Wextra -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libunregisterdemo.so unregister_demo.c

java -Djava.library.path=. UnregisterNativesDemo
```

`javac -h .` tạo `NativeRegistry.h` trong cùng thư mục, chứa prototype của hai JNI entry points. Với JDK 17/21 và Linux phù hợp, `System.loadLibrary("unregisterdemo")` tìm file `libunregisterdemo.so`. Đối với Windows/macOS cần tên native file và lệnh build riêng. Trên các JDK có chính sách restricted native access mới, có thể cần bật native access cho module của ứng dụng theo tài liệu JDK đó.

**Stdout kỳ vọng trong trường hợp không có symbol JNI thay thế:**

```text
beforeUnregister=42
sum=7
afterUnregister=UnsatisfiedLinkError
afterReRegister=42
sumAgain=7
```

Diễn giải theo thời điểm:

1. `NativeRegistry.registerTarget(NativeTarget.class)` liên kết hai Java native methods tới `target_twice` và `target_add`. Kết quả `twice(21)=42` và `add(3,4)=7`.
2. `UnregisterNatives(env, NativeTarget.class)` trả nhóm native methods của **class target** về trạng thái chưa liên kết. Vì không export `Java_NativeTarget_twice`, lần gọi `twice` sau đó không tìm được native implementation và ném `UnsatisfiedLinkError` (ở môi trường demo đã mô tả).
3. `NativeRegistry` vẫn có hai methods điều khiển vì nó là **class khác**, nên lời gọi `registerTarget` tiếp theo có thể đăng ký lại cùng các con trỏ. `twice` và `add` tiếp tục chạy như ban đầu.
4. Không bước nào yêu cầu unload hoặc reload file `libunregisterdemo.so`. Cùng một native binary có thể vẫn đang được nạp trong suốt cả quá trình.

Để thấy demo không dựa vào exported target symbols, trên Linux có thể quan sát dynamic symbol table (lệnh tùy chọn):

```bash
nm -D --defined-only libunregisterdemo.so
```

Trong output bạn có thể thấy các symbol `Java_NativeRegistry_registerTarget` và `Java_NativeRegistry_unregisterTarget`. Bạn **không nên thấy** các symbol `Java_NativeTarget_twice`/`Java_NativeTarget_add`, vì ví dụ không định nghĩa hai symbol đó. Kiểu/số lượng các symbol phụ thêm phụ thuộc compiler/linker và runtime.

Bài thực hành trên là **chứng minh về native method linkage**, không phải mẫu hot reload để áp dụng nguyên trạng trong ứng dụng đa luồng.

## 7. Tại sao không gọi unregister trong chính class target?

Một cách thiết kế dễ thất bại là:

```java
// Thiết kế có rủi ro: không dùng làm framework thực tế.
final class BadTarget {
    static native int calculate(int x);
    static native void unregisterSelf();
    static native void registerSelf();
}
```

Nếu `unregisterSelf()` gọi `UnregisterNatives(env, BadTarget.class)`, thao tác này tác động lên native methods của **cả class**, gồm `calculate`, `unregisterSelf` và `registerSelf`. Sau đó, nếu không có symbol native có thể được liên kết động lại cho `registerSelf`, Java sẽ không gọi được chính hàm khôi phục.

Đó là lý do demo tách:

```text
NativeRegistry (control plane)
  ├── registerTarget(...)     [binding còn nguyên]
  └── unregisterTarget(...)   [binding còn nguyên]
                     |
                     v
NativeTarget (target plane)
  ├── twice(...)              [binding bị gỡ]
  └── add(...)                [binding bị gỡ]
```

Dù tách class, framework thật vẫn cần **điều phối đồng bộ**. Việc tồn tại một phương thức re-register không bảo đảm tất cả threads dừng gọi native target trong giai đoạn chuyển trạng thái. Nếu sử dụng phiên bản `RegisterNatives` mới với con trỏ khác, phải chắc chắn code cũ không bị unload khi đang có active native calls/callbacks.

## 8. Class loader và native library ownership

Mỗi runtime `Class<?>` gắn với một defining class loader. Hai plugin có thể đều định nghĩa lớp có tên `com.example.NativeTarget` nhưng qua hai class loaders khác nhau. Khi gọi `UnregisterNatives` cần biết rõ class object nào đang được truyền; đừng chỉ lưu class name rồi tưởng API đã xử lý mọi bản sao lớp đó.

JNI native libraries cũng có vòng đời theo cơ chế của class loader. Theo JNI Invocation API, cùng một JNI native library không thể tùy tiện nạp vào hai class loaders khác nhau. Một `System.loadLibrary` lần thứ hai từ một loader khác có thể ném `UnsatisfiedLinkError` về việc thư viện đã được loaded trong loader khác. **`UnregisterNatives` không khắc phục quy tắc library ownership này.**

Nếu xây plugin host với nhiều class loaders:

- Quản lý rõ loader nào nạp native library, loader nào chứa class có các native bindings.
- Không lưu `jclass`/`jobject` local references qua đời sống native call. Dùng `NewGlobalRef` và `DeleteGlobalRef` khi thực sự cần giữ lâu, có chính sách giải phóng rõ ràng.
- Đừng coi unregister là thao tác làm cho class loader cũ lập tức được GC. Global refs/native threads/callbacks hoặc các reference Java khác vẫn có thể giữ class loader sống.
- Không giả định tạo class loader mới rồi nạp cùng một native library sẽ tránh được giới hạn một library theo loader; có thể cần kiến trúc tách tiến trình hoặc định danh/thư viện riêng với hợp đồng ABI phù hợp.

Đối với **ứng dụng thường**, cấu hình và nạp native library ổn định ở startup, giữ method binding cố định trong suốt vòng đời JVM sẽ ít rủi ro hơn các vòng unregister/re-register.

## 9. Rủi ro gọi đồng thời và native code đang chạy

Unregister không phải **stop-the-world API do ứng dụng kiểm soát**. Một thread có thể đang thực thi JNI method, trong khi thread khác yêu cầu unregister. Đặc tả API không cung cấp một giao kèo portable rằng:

- Native stack frame đang chạy sẽ bị hủy hoặc kết thúc ngay.
- JVM sẽ tự chờ mọi native calls từ class target thoát trước khi báo thành công.
- Việc thay function pointer, unload binary hoặc giải phóng state có thể diễn ra an toàn ngay sau khi return `JNI_OK`.
- Lời gọi bắt đầu giữa thời điểm unregister và re-register sẽ luôn xử lý theo một trạng thái duy nhất ứng dụng đã dự đoán.
- Các native callbacks hoặc threads nằm ngoài đường gọi Java hiện tại đã dừng hoạt động.

**Không suy đoán một chính sách concurrency cố định** từ mã return của `UnregisterNatives`. Khi JNI/native code đang giữ vùng nhớ hoặc thực thi instructions trong shared library cũ, gỡ hoặc overwrite binary quá sớm là vấn đề thuộc OS loader, JVM và lifetime native, không được hàm unregister giải quyết.

Một cách điều phối ở tầng ứng dụng, nếu thật sự có framework chuyên biệt:

```text
RUNNING
  |
  +-- Chặn lời gọi mới vào target (application gate)
  |
  +-- Chờ active calls + callbacks + native tasks về 0
  |
  +-- UnregisterNatives(targetClass)
  |
  +-- Thực hiện thay đổi bindings nếu mô hình JVM cho phép
  |
  +-- RegisterNatives(targetClass, đúng signatures, pointers)
  |
  +-- Kiểm tra trạng thái/khôi phục nếu lỗi
  |
  +-- Mở lại application gate
  |
  v
RUNNING
```

Đây chỉ là **một bản thiết kế điều phối**, không phải trình tự bảo đảm hot swap cho mọi VM hoặc mọi thư viện. Gate phải bao phủ **tất cả** call sites; giữ lock Java thông thường chưa chắc đủ nếu code native có callback hoặc background threads nằm ngoài phạm vi gate. Đối với thay đổi ABI/binary/logic native quan trọng, **restart JVM** thường là lựa chọn quản trị đáng tin cậy.

## 10. Trường hợp đáng dùng và không đáng dùng

| Nhu cầu | `UnregisterNatives` phù hợp? | Cách nên xem xét |
| --- | --- | --- |
| Framework chuyên biệt cần thử chu kỳ register/unregister trong môi trường cô lập | **Có thể**, với điều phối/lifecycle chặt | Test harness, serial execution, kiểm tra mã trả về |
| Runtime/framework do bạn kiểm soát muốn đổi native linkage có quản lý | **Chỉ khi** đã kiểm chứng contract/JVM và quiescence | Thiết kế trạng thái bindings riêng, kiểm thử từng JVM |
| Ứng dụng JNI bình thường load một thư viện và gọi vài methods | **Không cần** | `System.loadLibrary` + `RegisterNatives` khi cần, giữ binding ổn định |
| Muốn unregister một method duy nhất còn giữ các method khác trong class | **Không hỗ trợ trực tiếp** | Tách class hoặc dispatch theo trạng thái application |
| Muốn unload `.so`/`.dll` và giải phóng native heap | **Không** | Quản lý resource ownership, library/classloader lifecycle và restart nếu cần |
| Muốn bật/tắt quyền gọi native như security boundary | **Không đáng tin** | Xác thực ở Java API, chính sách native access, sandbox/process boundary |
| Muốn thay binary native trong khi các threads vẫn đang chạy | **Không bảo đảm an toàn** | Graceful shutdown + rolling restart |
| Plugin unload nhưng class loader cũ còn bị giữ bởi global refs | **Không giải quyết tận gốc** | Giải phóng refs/threads và lifecycle plugin đúng |
| Muốn reset một state C `static`/global | **Không** | Native cleanup/reset API được thiết kế riêng |
| Muốn xử lý `UnsatisfiedLinkError` do sai kiến trúc hoặc thiếu dependency | **Không** | Chẩn đoán ABI/OS loader/dependencies |

Đặc tả JNI cảnh báo thêm về **`RegisterNatives`**: đăng ký function pointers có thể thay đổi hành vi hệ thống đáng kể, kể cả những chức năng có ý nghĩa bảo mật, tính đúng đắn hoặc type safety. Vì vậy việc kết hợp register/unregister càng không phù hợp làm extension point cho nguồn native code không đáng tin cậy.

## 11. Khi `UnregisterNatives` hoặc `RegisterNatives` lỗi thì sao?

### Kết quả trả về không phải Java boolean

`UnregisterNatives` trả `jint`, với `JNI_OK`/`0` là thành công và giá trị âm là thất bại. Không dùng kiểu kiểm tra `if (rc) success`; điều kiện đúng là `rc == JNI_OK`. JNI có thể để lại Java exception pending khi thao tác khác trong đường gọi lỗi. Code native phải kiểm tra `ExceptionCheck` trước khi gọi các API không được phép trong trạng thái pending.

Trong demo, `registerTarget`/`unregisterTarget` là các `void native methods`, nên failure được chuyển thành một Java error nếu chưa có pending exception; nếu đã có lỗi gốc, helper giữ nguyên lỗi đó. Một production API có thể trả status rõ ràng hoặc dùng exception có ngữ cảnh hơn, tùy contract.

### `RegisterNatives` kiểm tra tên/descriptor

Các lỗi phổ biến khi đăng ký:

- Java method không tồn tại trong class đích.
- Method tồn tại nhưng không được khai báo `native`.
- Descriptor bị sai: `(I)I` khác `(J)J`; `String` dùng `Ljava/lang/String;`, array dùng `[...`.
- Tên hoặc chữ ký C function pointer không khớp loại static/instance, thứ tự hoặc carrier type; có thể gây crash khi gọi dù bước đăng ký có vẻ thành công.
- Một controller đăng ký bindings cho **class loader/class khác** cùng tên.
- Binary không đúng CPU, 32/64-bit, native ABI hoặc thiếu dependent libraries.

`RegisterNatives` có thể ném `NoSuchMethodError` nếu một method đăng ký không tìm thấy hoặc không phải native. Chữ ký JNI kiểm tra bằng:

```bash
javap -s -p NativeTarget
```

Hai descriptor của demo sẽ là `(I)I` và `(II)I`. Cần lấy header tạo bằng `javac -h` cho exported entry points, không đoán tên C function nếu class có package, overload hoặc các ký tự đặc biệt.

### Khi “unregister xong nhưng vẫn gọi được”

Không vội kết luận VM sai: có thể method được liên kết lại bằng **native symbol export theo tên JNI**, có code đã register lại, hoặc thực tế bạn đã gọi unregister cho **class khác** với class chứa method Java đang được invoke. Cũng nên loại trừ trường hợp log từ active call đã khởi chạy **trước** khi unregister.

Khi thực hành, bảo đảm:

1. Native target implementation chỉ được đăng ký qua `RegisterNatives` (không có exported `Java_NativeTarget_*`).
2. Lệnh unregister dùng đúng `NativeTarget.class`.
3. Không có concurrent Java/native tasks.
4. Mã return `UnregisterNatives` là `JNI_OK`.
5. Không có code khác re-register trước lúc test một lần gọi target.

### Khi “unregister xong rồi JVM crash”

Không coi đây là hành vi bình thường phải chấp nhận. Kiểm tra liệu code đã giải phóng native state/library trong lúc vẫn có active code, gọi JNI trên thread sai, dùng function pointer/ABI sai, xử lý JNI pending exception không đúng hoặc gọi native khi classloader/lifetime không hợp lệ.

Bật `-Xcheck:jni` trên JVM hỗ trợ để phát hiện nhiều lỗi giao tiếp JNI; kiểm tra `hs_err_pid*.log` và native backtrace, dùng AddressSanitizer/UndefinedBehaviorSanitizer trong môi trường có thể. `-Xcheck:jni` không chứng minh được mọi race hay tính an toàn của hot swap.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Gọi `UnregisterNatives(env, SomeClass.class)` có giải phóng file shared library trong tiến trình không?

**Không.** Nó thay đổi native method linkage của class; native library lifecycle thuộc cơ chế load/unload khác. Global refs, threads và native heap cần owner tự dọn.

**Câu 2.** Vì sao `UnregisterNatives` không thích hợp để tắt riêng `getValue()` trong class có hai native methods `getValue()` và `setValue()`?

Vì hàm nhận **`jclass`**, không nhận `jmethodID` hay tên method. Cần thiết kế tách class, dispatch có trạng thái, hoặc một API kiểm soát riêng nếu muốn chọn từng chức năng.

**Câu 3.** Sau unregister, `NativeTarget.twice(1)` có nhất định ném `UnsatisfiedLinkError` không?

**Không nhất định.** Nếu VM có thể tìm lại exported native symbol phù hợp hoặc bindings đã được đăng ký lại, method có thể được liên kết lại. Trong demo, do implementation chỉ là private C functions đăng ký tường minh và không có exported JNI symbols cho `NativeTarget`, nhánh sau unregister được thiết kế để tạo `UnsatisfiedLinkError`.

**Câu 4.** Trong demo, vì sao `NativeRegistry.registerTarget(...)` vẫn gọi được sau khi unregister?

Vì `UnregisterNatives` được gọi với `NativeTarget.class`, còn `NativeRegistry` là **class điều khiển khác**, có JNI exported symbols riêng và không bị unregister.

**Câu 5.** `UnregisterNatives` trả `JNI_OK` trong lúc thread khác đang chạy một native call. Có thể `dlclose` thư viện ngay không?

**Không có bảo đảm an toàn.** `JNI_OK` không chứng minh mọi active frames/native callbacks đã dừng hoặc code không còn được dùng. Phải có quiescence/lifecycle riêng và tốt nhất dùng restart khi thay binary production.

**Câu 6.** Unregister có giải quyết lỗi “native library already loaded in another classloader” không?

**Không.** Lỗi liên quan tới cách JVM gắn native library với class loader, khác với native bindings của một class. Cần thiết kế class loader/library ownership phù hợp.

**Câu 7.** `RegisterNatives` có hai entries; chỉ một entry sai descriptor. Có thể coi những entry còn lại chắc chắn đã đăng ký và tiếp tục không?

**Không.** Phải kiểm tra `RegisterNatives` thất bại và trạng thái exception; không dựa vào một partial state không được contract bảo đảm. Hãy sửa bảng tên/descriptors và chỉ mở đường gọi Java khi bước đăng ký hoàn tất thành công.

**Câu 8.** Một framework bắt buộc thay native implementation lúc chạy nên làm gì trước khi unregister?

Chặn nhận calls mới, chờ calls/callbacks/tasks đang chạy kết thúc, xác nhận đúng target class và ownership, chuẩn bị phương án khôi phục, rồi chỉ thực hiện thao tác trên môi trường/JVM mà framework đã kiểm chứng. Unregister không làm thay công việc đồng bộ và an toàn memory.

## Tài liệu chính thức

- Oracle JNI Specification — *UnregisterNatives* (prototype, phạm vi class và cảnh báo dành cho special programs): https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#unregisternatives
- Oracle JNI Specification — *RegisterNatives* (`JNINativeMethod`, tên/descriptor/pointer, mã trả về): https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#registernatives
- Oracle JNI Specification — *Compiling, Loading and Linking Native Methods* và native/class loader: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html
- Oracle JNI Specification — *Invocation API, Library and Version Management, JNI_OnLoad/JNI_OnUnload*: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/invocation.html#library-and-version-management
- Oracle Java 17 — `javac -h` sinh JNI header: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Java Language Specification — *Unloading of Classes and Interfaces*: https://docs.oracle.com/en/java/javase/25/docs/specs/jls/jls-12.html#jls-12.7

**Ghi nhớ:** `UnregisterNatives` là thao tác **class-scoped native method unlinking** cho trường hợp chuyên biệt. Nó **không** unload thư viện, không xóa class, không giải phóng tài nguyên, không cấp bảo đảm hot swap/concurrency và không hủy riêng một method. Để ứng dụng JNI ổn định, hãy giữ native bindings cố định; nếu phải đổi binary hoặc ABI, ưu tiên một quy trình khởi động lại JVM có kiểm soát.