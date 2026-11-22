# Hai chiều gọi: Java sang hàm bản địa và hàm bản địa gọi lại Java

## 1. Bản chất của tương tác hai chiều

Java chạy trong JVM; thư viện bản địa (native library) thường là mã máy biên dịch từ C/C++. Khi tích hợp, luồng điều khiển có thể đi theo **cả hai hướng**:

- **Java → native (downcall):** Java yêu cầu một hàm C thực hiện công việc, chẳng hạn gọi thư viện thiết bị, xử lý dữ liệu hoặc sử dụng API hệ điều hành.
- **Native → Java (callback/upcall):** Trong hoặc sau khi xử lý, mã C thông báo kết quả, sự kiện hay lỗi về một phương thức Java. Callback có thể đồng bộ ngay trên luồng gọi hoặc bất đồng bộ trên một luồng native khác.

Hai con đường phổ biến là **Java Native Interface (JNI)** và **Foreign Function & Memory API (FFM)**. JNI cho mã C/C++ thao tác trực tiếp với đối tượng, phương thức và trạng thái JVM qua `JNIEnv`. FFM (API chính thức từ JDK 22) cho Java gọi hàm C theo ABI và tạo con trỏ hàm để C gọi ngược về một `MethodHandle` Java.

Ví dụ luồng đồng bộ:

```text
Java: multiplyAndNotify(6, 7)
    │
    ▼  lời gọi native
C: tính kết quả 42
    │
    ▼  callback sang Java
Java: onNativeResult(42)  → in thông báo
    │
    ▼  quay về hàm C
C: return 42
    │
    ▼
Java: nhận 42 và tiếp tục xử lý
```

Điểm cốt lõi: **kết quả trả về** của hàm C và **callback** là hai kênh truyền thông tin khác nhau. Một hàm native có thể thực hiện callback rồi mới trả kết quả; callback không tự động biến thành bất đồng bộ.

## 2. JNI: ví dụ hoàn chỉnh Java → C → Java

Ví dụ sau chạy với **JDK 17+ và GCC trên Linux**. Thư viện `nativebridge` nhân hai số nguyên, gọi lại phương thức Java để báo kết quả, rồi trả kết quả của chính lời gọi native. Mọi đoạn mã trong mục này cùng thuộc một chương trình chạy được.

### 2.1. Java khai báo native method và callback

Tạo `NativeBridge.java`:

```java
public final class NativeBridge {
    static {
        System.loadLibrary("nativebridge");
    }

    // Java -> C: JVM tìm hàm JNI được xuất từ thư viện.
    private native int multiplyAndNotify(int a, int b);

    // C -> Java: hàm C sẽ tìm và gọi phương thức này qua JNI.
    private void onNativeResult(int result) {
        System.out.println("Native callback: " + result);
    }

    public static void main(String[] args) {
        NativeBridge bridge = new NativeBridge();
        int result = bridge.multiplyAndNotify(6, 7);
        System.out.println("Java result: " + result);
    }
}
```

`native` chỉ khai báo chữ ký; phần thân nằm trong thư viện C. `System.loadLibrary("nativebridge")` yêu cầu JVM nạp thư viện theo quy tắc đặt tên của hệ điều hành: Linux thường là `libnativebridge.so`, macOS là `libnativebridge.dylib`, Windows là `nativebridge.dll`. Phương thức `onNativeResult` không cần là `native`: đây là **phương thức Java bình thường**, được C gọi qua JNI.

### 2.2. C thực hiện phép tính và gọi lại Java

Trước hết dùng `javac -h .` (ở bước biên dịch bên dưới) để tạo header `NativeBridge.h`. Sau đó tạo `nativebridge.c`:

```c
#include <jni.h>
#include <stdint.h>
#include "NativeBridge.h"

JNIEXPORT jint JNICALL Java_NativeBridge_multiplyAndNotify(
        JNIEnv *env, jobject self, jint a, jint b) {

    // Tránh tràn số nguyên có dấu trong phép nhân C.
    jlong wide = (jlong) a * (jlong) b;
    if (wide > INT32_MAX || wide < INT32_MIN) {
        jclass error = (*env)->FindClass(env, "java/lang/ArithmeticException");
        if (error != NULL) {
            (*env)->ThrowNew(env, error, "native result out of int range");
            (*env)->DeleteLocalRef(env, error);
        }
        return 0; // Khi có exception pending, Java sẽ nhận exception.
    }
    jint result = (jint) wide;

    jclass cls = (*env)->GetObjectClass(env, self);
    if (cls == NULL) {
        return 0; // JVM đã đặt exception nếu thao tác thất bại.
    }

    // (I)V: nhận một int, trả void.
    jmethodID callback = (*env)->GetMethodID(
            env, cls, "onNativeResult", "(I)V");
    if (callback == NULL) {
        (*env)->DeleteLocalRef(env, cls);
        return 0;
    }

    (*env)->CallVoidMethod(env, self, callback, result);
    (*env)->DeleteLocalRef(env, cls);

    if ((*env)->ExceptionCheck(env)) {
        return 0; // Giữ nguyên exception Java và trả về JVM.
    }
    return result;
}
```

Giải thích theo thứ tự thực thi:

1. `JNIEXPORT` và `JNICALL` công bố entry point với quy ước gọi phù hợp; `Java_NativeBridge_multiplyAndNotify` là tên JNI ứng với class/phương thức trong ví dụ không có package. Dùng header do `javac -h` tạo để tránh viết sai chữ ký.
2. `JNIEnv *env` là giao diện JNI **của luồng hiện tại**; `jobject self` là đối tượng `NativeBridge` đã gọi phương thức instance. Nếu `native` là `static` thì tham số tương ứng là `jclass`.
3. `jint` và `jlong` là kiểu JNI có kích thước xác định. Phép nhân được nâng lên `jlong` trước khi kiểm tra miền của `jint` để tránh hành vi không xác định do tràn `int` trong C.
4. `GetObjectClass` trả về một **local reference** đến class của `self`; `GetMethodID` tìm phương thức instance theo **tên và descriptor**. `jmethodID` là định danh phương thức, không phải local reference.
5. `CallVoidMethod` chuyển điều khiển ngược vào Java. Khi `onNativeResult` kết thúc, C tiếp tục chạy ngay sau lời gọi đó. `DeleteLocalRef` giải phóng tham chiếu cục bộ tạo trong native frame.
6. Nếu callback ném exception, `ExceptionCheck` phát hiện exception còn pending. C không tiếp tục gọi các JNI API tùy ý; khi native method trả về, exception đó được ném về phía Java. `return 0` trong đường lỗi chỉ đáp ứng chữ ký C, không phải kết quả thành công.

### 2.3. Biên dịch và chạy trên Linux

Đặt `NativeBridge.java` và `nativebridge.c` trong cùng thư mục; cấu hình `JAVA_HOME` trỏ đến thư mục JDK (có `include/jni.h`). Chạy:

```bash
javac -encoding UTF-8 -h . NativeBridge.java
gcc -fPIC -shared -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" -o libnativebridge.so nativebridge.c
java -Xcheck:jni -Djava.library.path=. NativeBridge
```

`javac -h .` sinh `NativeBridge.h` chứa nguyên mẫu JNI. GCC biên dịch thư viện chia sẻ có thể nạp trong JVM. `-Djava.library.path=.` cho JVM tìm thư viện ở thư mục hiện tại; `-Xcheck:jni` bật kiểm tra bổ sung cho một số lỗi sử dụng JNI.

Kết quả chuẩn khi chạy với `6` và `7`:

```text
Native callback: 42
Java result: 42
```

Thứ tự in chứng tỏ callback chạy **trước khi** `multiplyAndNotify` trả về Java. Trên macOS dùng include `$JAVA_HOME/include/darwin` và cách tạo `.dylib` phù hợp; trên Windows dùng include `win32`, thư viện `.dll` và công cụ biên dịch tương thích. Tên và đường dẫn thư viện phải khớp `System.loadLibrary`.

## 3. JNI tìm phương thức Java như thế nào?

JNI không tra phương thức qua tên Java đơn lẻ. `GetMethodID` cần descriptor JVM của tham số và kiểu trả về.

| Kiểu/Phương thức Java | Descriptor JNI |
| --- | --- |
| `void callback(int x)` | `(I)V` |
| `void callback(String s)` | `(Ljava/lang/String;)V` |
| `int size(byte[] bytes)` | `([B)I` |
| `long getValue()` | `()J` |

Quy tắc thường gặp: `V` = `void`, `I` = `int`, `J` = `long`, `Z` = `boolean`, `Lpackage/Class;` = đối tượng, `[` = mảng. Descriptor đầy đủ bao gồm **danh sách tham số trong ngoặc** và **kiểu trả về**. Sai descriptor có thể khiến `GetMethodID` trả `NULL` và có `NoSuchMethodError` pending.

Chọn đúng lời gọi tương ứng với kiểu trả về: `CallVoidMethod` cho `void`, `CallIntMethod` cho `int`, `CallObjectMethod` cho đối tượng. Với phương thức static, dùng `GetStaticMethodID` và `CallStatic...Method`. JNI không tự kiểm tra tính hợp lệ của mọi tham số như trình biên dịch Java; ID, đối tượng, chữ ký và kiểu phải thống nhất.

## 4. Callback trên một luồng native khác

Ví dụ ở mục 2 là **callback đồng bộ trên luồng Java đã vào JNI**, nên JVM đã cung cấp `JNIEnv *` hợp lệ. Với callback phát ra từ một luồng do C/C++ tự tạo (ví dụ luồng nhận sự kiện thiết bị), phải xử lý **gắn luồng, tham chiếu và vòng đời**:

1. Khi còn ở một lời gọi JNI hợp lệ, lấy `JavaVM *` bằng `(*env)->GetJavaVM(env, &vm)`. Có thể lưu `JavaVM *` cho mục đích gắn luồng; **không lưu `JNIEnv *` để dùng ở luồng khác**.
2. Nếu callback cần truy cập một đối tượng Java sau khi native method ban đầu kết thúc, tạo `global reference` qua `NewGlobalRef`. `jobject` nhận từ tham số hoặc `GetObjectClass` thường là local reference: không được lưu rồi sử dụng sau khi native frame kết thúc.
3. Trên luồng C thực hiện callback, gọi `GetEnv` để xác định luồng đã gắn JVM hay chưa. Nếu nhận `JNI_EDETACHED`, gọi `AttachCurrentThread` (hoặc `AttachCurrentThreadAsDaemon` theo thiết kế) để lấy `JNIEnv *` riêng cho **luồng đó**. Nếu attach thất bại, không gọi JNI.
4. Dùng `JNIEnv *` của luồng hiện tại, global reference còn sống và `jmethodID` hợp lệ để gọi callback. Xác định cách xử lý exception phát sinh, đặc biệt khi không có Java caller đồng bộ để nhận exception.
5. Nếu chính luồng C đã attach, gọi `DetachCurrentThread` trước khi luồng kết thúc (khi không còn Java frame trên stack). Không detach luồng Java đang dùng JNI chỉ vì hàm callback vừa hoàn thành.
6. Khi hủy đăng ký callback hoặc đóng thư viện, đồng bộ với những callback đang chạy, rồi gọi `DeleteGlobalRef` tại thời điểm hợp lệ. Không giải phóng tham chiếu/dữ liệu khi luồng C vẫn có thể dùng.

Một lưu ý khi tra class: `FindClass` từ một native thread tự attach có ngữ cảnh class loader khác với lời gọi bắt đầu từ Java; với class ứng dụng, nên giữ class reference hợp lệ hoặc dùng class loader đã chọn thay vì giả định lúc nào `FindClass` cũng tìm được. Callback từ luồng riêng còn đòi hỏi cơ chế shutdown rõ ràng để tránh gọi Java sau khi listener hoặc VM ngừng hoạt động.

**Global reference không có nghĩa là bất biến hay an toàn luồng**: nó chỉ giữ đối tượng Java còn có thể truy cập. Dữ liệu trong đối tượng vẫn cần đồng bộ hóa phù hợp; callback vẫn có thể đua với thao tác hủy hoặc cập nhật trạng thái.

## 5. FFM (JDK 22+): downcall và upcall không cần hàm JNI cho từng entry point

Khi tích hợp **hàm C theo ABI**, FFM cung cấp mô hình khác:

- `downcallHandle` tạo `MethodHandle` để Java gọi một **hàm C** tại địa chỉ ký hiệu đã tìm được;
- `upcallStub` tạo **con trỏ hàm native** trỏ ngược về `MethodHandle` Java;
- `FunctionDescriptor` và `ValueLayout` mô tả chữ ký nhị phân; `Arena` kiểm soát vòng đời tài nguyên native, trong đó có upcall stub.

Đây là ví dụ độc lập khác với JNI ở trên. Nó dùng **JDK 22 trở lên** với API `java.lang.foreign` chính thức (không cần `--enable-preview`) và GCC trên Linux.

### 5.1. Hàm C nhận con trỏ callback

Tạo `ffmbridge.c`:

```c
typedef void (*callback_t)(int);

int compute_and_notify(int a, int b, callback_t callback) {
    // Ví dụ dùng đầu vào nhỏ, trong miền int.
    int result = a * b;
    if (callback != 0) {
        callback(result); // C gọi function pointer của Java upcall stub.
    }
    return result;
}
```

Thư viện nhận con trỏ hàm có chữ ký `void (*)(int)`. C không biết gì về class Java, `JNIEnv` hoặc `jmethodID`; nó chỉ gọi con trỏ theo ABI đã thỏa thuận. Trong hệ thống thật, cần quy định miền đầu vào và cách báo lỗi thay vì để phép nhân `int` C bị tràn.

### 5.2. Java tạo downcall handle và upcall stub

Tạo `FfmBridge.java`:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class FfmBridge {
    private static void onResult(int value) {
        System.out.println("Native callback: " + value);
    }

    public static void main(String[] args) throws Throwable {
        System.loadLibrary("ffmbridge");

        Linker linker = Linker.nativeLinker();
        SymbolLookup symbols = SymbolLookup.loaderLookup();
        MemorySegment function = symbols.find("compute_and_notify")
                .orElseThrow();

        // C callback: void (*)(int)
        FunctionDescriptor callbackType =
                FunctionDescriptor.ofVoid(ValueLayout.JAVA_INT);

        // C function: int (int, int, callback_t)
        FunctionDescriptor nativeType = FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT,
                ValueLayout.ADDRESS);

        MethodHandle target = MethodHandles.lookup().findStatic(
                FfmBridge.class,
                "onResult",
                MethodType.methodType(void.class, int.class));
        MethodHandle downcall = linker.downcallHandle(function, nativeType);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment callback =
                    linker.upcallStub(target, callbackType, arena);
            int result = (int) downcall.invokeExact(6, 7, callback);
            System.out.println("Java result: " + result);
        }
    }
}
```

`System.loadLibrary` nạp thư viện trước khi `SymbolLookup.loaderLookup()` tìm tên ký hiệu C. `JAVA_INT` biểu diễn `int` trong ABI phù hợp với ví dụ; `ADDRESS` là tham số con trỏ callback. `findStatic` tạo handle đến phương thức Java; `upcallStub` biến handle đó thành địa chỉ C có thể gọi. `invokeExact` yêu cầu kiểu Java khớp chữ ký handle chính xác: hai `int`, một `MemorySegment`, kết quả `int`.

Biên dịch và chạy trên Linux:

```bash
gcc -fPIC -shared -o libffmbridge.so ffmbridge.c
javac -encoding UTF-8 FfmBridge.java
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. FfmBridge
```

Đầu ra:

```text
Native callback: 42
Java result: 42
```

Cần bật quyền native access cho module thực hiện lời gọi bị hạn chế (ví dụ `ALL-UNNAMED` với chương trình chạy trên classpath). Khi chạy trong **named module**, cấp quyền cho đúng tên module. Không nhầm `--enable-native-access` với `--enable-preview`: FFM đã chính thức từ JDK 22.

### 5.3. Vòng đời và ranh giới lỗi của FFM

Trong ví dụ này, C gọi callback **đồng bộ** trước khi `compute_and_notify` trả về, nên `Arena.ofConfined()` còn sống cho đến khi callback kết thúc. Nếu C **lưu con trỏ callback để gọi sau**, không thể đóng arena ngay sau downcall; cần một arena/vòng đời phù hợp, quản lý hủy đăng ký, số callback đang chạy, và quyền truy cập giữa các luồng. Gọi con trỏ sau khi stub đã bị giải phóng có thể gây lỗi nghiêm trọng.

**Không để exception thoát khỏi đích upcall FFM.** Theo hợp đồng của `Linker.upcallStub`, exception Java không được xử lý ở boundary callback có thể làm JVM chấm dứt đột ngột. Callback trong ứng dụng thật cần bắt và xử lý mọi lỗi trước khi quay lại C (ví dụ ghi lỗi vào trạng thái an toàn, trả mã lỗi qua giao thức đã định), không dựa vào việc C sẽ tự bắt được exception Java.

FFM không tự biến một hàm C++ có name mangling tùy ý thành C ABI. Nếu gọi thư viện C++, thường cần `extern "C"` wrapper với kiểu/ABI rõ ràng. `MemorySegment` và con trỏ native cũng không phải `jobject`; không truyền địa chỉ của đối tượng Java tùy tiện cho C.

## 6. Chọn JNI hay FFM cho bài toán hai chiều

| Tiêu chí | JNI | FFM (JDK 22+) |
| --- | --- | --- |
| Java gọi mã bản địa | Khai báo `native`, export hàm JNI đúng chữ ký | `Linker.downcallHandle` cho hàm C ABI |
| Native gọi lại Java | `GetMethodID` + `Call...Method` trên `JNIEnv` hợp lệ | C gọi function pointer từ `Linker.upcallStub` |
| Dữ liệu Java | Truy cập `jobject`, mảng, chuỗi qua JNI | Ưu tiên kiểu C, `MemorySegment` và layout |
| Vòng đời callback | Local/global/weak global references; attach luồng khi cần | Arena và thời gian sống của upcall stub |
| Trường hợp điển hình | Tích hợp JVM sâu, SDK đã dùng JNI, gọi phương thức/đối tượng Java | Gọi thư viện C hiện có qua ABI và đăng ký callback dạng con trỏ hàm |
| Rủi ro cần quản lý | Sai reference/chữ ký, pending exception, dùng sai `JNIEnv`/thread | Sai layout/ABI, con trỏ hết hạn, exception thoát khỏi upcall |

Hai API đều vượt ra khỏi hàng rào an toàn bộ nhớ thuần Java. API nào cũng cần xác định **ai sở hữu tài nguyên**, **ai được phép gọi callback** và **khi nào callback không còn hợp lệ**. Với C++ và Java 17, JNI là lựa chọn thực tế nếu cần gọi đối tượng Java từ mã native; FFM theo dạng đã ổn định yêu cầu JDK 22+.

## 7. Thiết kế hợp đồng callback an toàn

Trước khi triển khai, chốt các điểm sau ở cả phía Java và native:

1. **Chữ ký và ABI:** Kiểu `int/long/pointer`, calling convention, độ rộng dữ liệu, encoding chuỗi và quy tắc trả về. Với JNI, descriptor phải khớp Java; với FFM, `FunctionDescriptor` phải khớp định nghĩa C.
2. **Đồng bộ hay bất đồng bộ:** Callback xảy ra trước return hay có thể tới sau? Có thể tới nhiều lần, song song, hoặc sau lệnh hủy không? Có cần thứ tự sự kiện không?
3. **Luồng gọi:** Callback tới từ luồng nào; có được truy cập UI thread, transaction, thread-local context không? Với JNI, native thread ngoài JVM phải attach đúng cách; không truyền `JNIEnv` qua các luồng.
4. **Sở hữu và giải phóng:** Ai giữ Java listener, local/global reference, `MemorySegment`, buffer và function pointer? Khi shutdown phải ngừng phát callback rồi mới giải phóng thứ chúng dùng.
5. **Lỗi và hủy:** Có mã trạng thái, callback báo lỗi, hay exception? Với JNI có pending Java exception; với FFM phải giữ exception khỏi thoát upcall. Quy định rõ đường đi khi callback từ chối dữ liệu, timeout hoặc bị hủy.
6. **Reentrancy và khóa:** Trong lúc Java đang giữ lock gọi C, C có thể gọi lại chính Java hoặc Java gọi lại C. Tránh giữ lock qua callback không kiểm soát vì dễ bế tắc; cập nhật trạng thái theo hợp đồng đồng bộ hóa đã chọn.
7. **Kiểm soát dữ liệu:** Kiểm tra độ dài vùng nhớ, null, buffer capacity, overflow và encoding ở ranh giới; không giả định native code tự bảo đảm an toàn kiểu Java.

Một thiết kế thường dễ quản lý là để native phát **sự kiện nhỏ có kiểu rõ ràng**, còn Java nhận callback rồi xếp tác vụ lên executor phù hợp nếu cần xử lý nặng. Không thực hiện I/O kéo dài trong callback nếu hàm native đang chờ đồng bộ để hoàn tất.

## 8. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `UnsatisfiedLinkError` khi load | Tên thư viện, đường dẫn, kiến trúc hoặc phụ thuộc native không phù hợp | Đối chiếu `System.loadLibrary`, file `.so/.dll/.dylib`, `java.library.path`, kiến trúc JVM và các thư viện phụ thuộc |
| `UnsatisfiedLinkError` khi gọi `native` | Không có symbol JNI tương ứng hoặc chữ ký C sai | Sinh lại header bằng `javac -h`; kiểm tra package, tên hàm, overload và symbol export |
| `NoSuchMethodError` khi callback JNI | `GetMethodID` tìm sai tên, descriptor hoặc static/instance | So lại chữ ký `(I)V`; phân biệt `GetMethodID` với `GetStaticMethodID` |
| Crash khi dùng reference sau return | Lưu local reference/`JNIEnv` quá vòng đời hoặc dùng từ luồng khác | Dùng global reference có cleanup; lấy `JNIEnv` riêng cho mỗi luồng |
| JNI tiếp tục lỗi sau callback | Java đã ném exception nhưng C vẫn gọi JNI không hợp lệ | Kiểm tra `ExceptionCheck`; return để exception lan về Java hoặc xử lý và clear có chủ đích |
| FFM crash/lỗi ngẫu nhiên | Sai `FunctionDescriptor`, ABI, địa chỉ hoặc callback stub hết hạn | Đối chiếu chữ ký C và layout; giữ arena sống đúng vòng đời |
| Chương trình dừng khi FFM callback lỗi | Exception Java thoát khỏi `upcallStub` | Bắt mọi exception trong callback và chuyển thành cơ chế báo lỗi riêng |
| Treo/chạy sai trạng thái | Callback reentrant, race khi unregister, hoặc giữ lock qua native call | Xác định luồng và thứ tự lock; đồng bộ shutdown; thử nghiệm đồng thời |

`-Xcheck:jni` hỗ trợ phát hiện nhiều lỗi JNI nhưng không thay thế kiểm tra bộ nhớ C hoặc kiểm thử đa luồng. Ngoài happy path, cần thử lỗi thư viện không nạp được, callback ném exception, hủy listener, callback tới trễ và dữ liệu ở biên kiểu số.

## 9. Tự kiểm tra hiểu bài

- Trong ví dụ JNI, vì sao `NativeBridge.onNativeResult` được gọi **trước** dòng `Java result: 42` dù cả hai cùng chạy trong Java? Hãy chỉ ra đúng lệnh JNI chuyển điều khiển.
- Nếu `onNativeResult(int)` đổi thành `onNativeResult(long)`, descriptor nào phải thay và C cần đổi kiểu đối số/lệnh gọi nào?
- Nếu thư viện C gửi callback từ một worker thread sau khi `multiplyAndNotify` đã return, vì sao không được giữ `self` hoặc `env` ban đầu?
- Nếu FFM C lưu `callback` vào một biến toàn cục rồi gọi sau khi `try (Arena arena...)` kết thúc, vấn đề vòng đời là gì? Thiết kế lại cách đăng ký/hủy callback thế nào để an toàn?
- Hãy nêu cơ chế truyền lỗi thích hợp cho trường hợp Java callback thất bại trong JNI và trường hợp thất bại trong FFM upcall. Vì sao không thể dùng cùng một cách xử lý exception?

**Ghi nhớ:** Java → native và native → Java là hai chiều điều khiển có **chữ ký, luồng, vòng đời và ranh giới lỗi** riêng. Ví dụ đồng bộ giải thích cơ chế; hệ thống callback bất đồng bộ phải bổ sung attach/thread, giữ tham chiếu hoặc stub, và shutdown an toàn.

### Tài liệu tham khảo

- Java Native Interface Specification: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/
- JNI Invocation API (gắn/hủy gắn native thread): https://docs.oracle.com/en/java/javase/25/docs/specs/jni/invocation.html
- JEP 454 — Foreign Function & Memory API (JDK 22): https://openjdk.org/jeps/454
- `Linker` API: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html
