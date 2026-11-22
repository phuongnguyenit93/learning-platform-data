# Native method stack và ranh giới lời gọi mã native trong JVM

Khi một thread Java gọi phương thức viết bằng Java, JVM cung cấp mô hình **Java Virtual Machine stack**, các **frames**, local variables và operand stack. Khi lời gọi đi vào một phương thức triển khai bằng C/C++ hoặc thư viện hệ điều hành, thread vượt qua **ranh giới Java ↔ native**. Một JVM implementation có thể dùng **native method stack** (thường được gọi là “C stack”) để hỗ trợ phần thực thi ngoài Java bytecode.

Điểm mấu chốt: **native method stack khác Java heap, khác bộ nhớ off-heap nói chung, và không bắt buộc tồn tại như một stack vật lý thứ hai độc lập với Java stack trên mọi JVM**. JVM Specification (JVMS) mô tả hành vi và các lựa chọn triển khai, không quy định duy nhất một layout của stack trong hệ điều hành. Với một JVM phổ biến như HotSpot, native calls thường sử dụng stack và ABI của OS thread đang chạy; mã JIT/compiler có thể giữ dữ liệu trên thanh ghi, inline functions và tổ chức frames theo cách riêng.

Bài này đi từ khái niệm vùng nhớ đến ranh giới **JNI**, cách truyền tham số và exception, cách tương tác với GC, quản lý native threads, một ví dụ **Java 17 + C đầy đủ** và quy trình chẩn đoán lỗi.

## 1. Native method stack là gì theo JVMS?

JVMS §2.5.6 cho phép implementation dùng conventional stacks (thường gọi là **C stacks**) để hỗ trợ:

- **Native methods**: phương thức triển khai bằng ngôn ngữ khác Java và được JVM gọi.
- Mã bên trong JVM/interpreter nếu được triển khai bằng một ngôn ngữ sử dụng conventional call stacks.

Nếu một JVM không hỗ trợ nạp native methods và không cần conventional stack cho implementation của chính nó, đặc tả **không bắt buộc** cung cấp native method stacks. Khi có, chúng thường gắn với **thread** lúc thread được tạo. Stack có thể có kích thước cố định hoặc mở rộng/co lại theo khả năng implementation.

**Hai kết luận đúng:** Java có khái niệm trừu tượng native method stack; native code thực tế cần ngữ cảnh thực thi và storage tương ứng với ABI/platform.

**Kết luận không đúng:** mỗi method Java gọi native chắc chắn tạo một native stack vùng riêng biệt với Java stack, hoặc mỗi lời gọi native tạo một OS thread mới.

### 1.1. Các giới hạn bộ nhớ

JVMS liên kết native method stacks với những trạng thái lỗi:

- Khi tính toán cần stack lớn hơn kích thước được cho phép, có **`StackOverflowError`** theo quy tắc vùng nhớ này.
- Nếu stack cần mở rộng hoặc cần tạo cho thread mới nhưng không thể cấp phát memory thích hợp, có **`OutOfMemoryError`**.

Đây là mô hình lỗi của JVM Specification. Nó **không cam kết** mọi lỗi trong C — stack smash, buffer overrun, use-after-free, dereference địa chỉ không hợp lệ — đều chuyển thành Java exception dễ `catch`. Mã C lỗi vẫn có thể gây **SIGSEGV/access violation và làm sập toàn bộ tiến trình**.

## 2. Native method stack, JVM stack, Java heap và native memory

| Khái niệm | Vai trò | Phạm vi | Không được nhầm với |
| --- | --- | --- | --- |
| JVM stack | Các frames, local variables, operand stacks, dynamic linking/return logic theo mô hình JVM | Per JVM thread | Java heap |
| Native method stack | Stack dùng cho native methods/JVM implementation nếu dùng conventional stack | Thường per thread | “toàn bộ native memory” |
| Java heap | Java objects và arrays do GC quản lý | Chia sẻ trong JVM | C call frames |
| Method area / metaspace | Class metadata và runtime structures tương ứng; cách cấp phát phụ thuộc JVM | Do VM quản lý | Native method call stack |
| Native/off-heap memory | Native stacks, `malloc`, direct buffers, JIT code cache, VM structures và nhiều thành phần khác | Tùy cấp phát | Chỉ một native method stack |
| Registers | Values/call state do compiler/CPU quản lý | Lúc thực thi | Java local-variable slot vật lý cố định |

Ví dụ, `String input` trong Java chứa **reference**, không chép toàn bộ nội dung String vào frame của Java caller. Khi truyền qua JNI, native function nhận **`jstring` handle/reference**, không phải bản sao bắt buộc của Java object trên C stack.

JNI có hàm lấy dữ liệu chuỗi, nhưng việc tạo copy hay pin dữ liệu tùy API và JVM. Cần phân biệt **object nằm trên Java heap**, **handle mà native code giữ**, và **buffer cấp phát tạm**.

### 2.1. JVM frame không nhất thiết tương ứng một C frame

Một Java method có thể có `Code` attribute với `max_stack` và `max_locals`. C function tuân theo calling convention/ABI, và native compiler có thể dùng registers, machine stack, tối ưu tail/inlining.

- Java local slot 0 ở instance method là `this` theo JVM, không phải một offset C stack luôn cố định.
- Biến C `int result` có thể hoàn toàn nằm trong register.
- Java stack trace và native debugger backtrace không phải cùng một định dạng hoặc lúc nào cũng in cùng chuỗi frames.
- Đừng suy dung lượng native stack chỉ bằng cách đếm số dòng Java source.

## 3. Đi qua ranh giới lời gọi Java → native

Java khai báo:

```java
static native int sum(int left, int right);
```

Đây là **declaration**, không có method body Java. Trong class file, phương thức mang flag **`ACC_NATIVE`**, và không có `Code` attribute chứa Java bytecode để làm phép cộng. JVM liên kết lời gọi này đến một **native entrypoint** thông qua cơ chế tương tác phù hợp, ví dụ JNI.

```text
Java method (caller)
   │ invoke* tới native declaration
   │ arguments theo descriptor JVM
   ▼
JVM/JNI transition
   │ chọn native implementation và calling convention
   │ truyền JNIEnv*, receiver/class, arguments
   ▼
Native C function
   │ C function calls / native stack hoặc CPU registers
   │ có thể gọi JNI API hoặc callback vào Java
   ▼
Return JNI primitive/reference hoặc exception pending
   │
   ▼
JVM khôi phục ngữ nghĩa Java caller
   ├─ normal result → caller nhận giá trị
   └─ Java exception → tìm catch/unwind frames
```

Không có opcode bytecode tên `jni_call`. Những opcode như `invokestatic`, `invokevirtual` hoặc `invokespecial` có thể gọi phương thức khai báo `native`; việc thực thi mã native là trách nhiệm của JVM và native linkage, không có body bytecode Java để `javap -c` liệt kê.

### 3.1. `JNIEnv*` và đối số ngầm

Với C JNI entrypoint:

- `JNIEnv *env` là **interface pointer hợp lệ trên thread hiện tại**.
- Static native method nhận thêm `jclass clazz`.
- Instance native method nhận thêm `jobject receiver`.
- Các Java parameters được ánh xạ thành `jint`, `jlong`, `jdouble`, `jstring`, `jobject`, `jarray` và những JNI types thích hợp.

| Java declaration | C signature (phần cốt lõi) |
| --- | --- |
| `static native int add(int a, int b)` | `(JNIEnv*, jclass, jint, jint) → jint` |
| `native long scale(long n)` | `(JNIEnv*, jobject, jlong) → jlong` |
| `static native void log(String value)` | `(JNIEnv*, jclass, jstring) → void` |

Đây là cách ánh xạ **tại API boundary**, không phải lời hứa compiler C đẩy tất cả parameters vào native stack ở mọi hệ điều hành/CPU.

### 3.2. Primitive values và object references

Các primitive arguments đi qua JNI như **giá trị** theo kiểu tương ứng. Với reference, JNI dùng **opaque handles** thay vì cho phép native code đọc internal Java heap object layout bằng phép dereference tùy ý.

Một `jstring` không phải `char*`. Một `jobject` không phải con trỏ ổn định vào object được phép cast thành `struct*` của C. GC có thể di chuyển object, nên muốn đọc field, gọi method hoặc lấy data cần dùng JNI functions được hỗ trợ.

## 4. Ví dụ JNI đầy đủ: Java gọi C, C gọi ngược Java và ném lỗi

Ví dụ gồm hai file: **`NativeBoundaryDemo.java`** và **`boundarydemo.c`**. Phần Java biên dịch bằng JDK 17; phần C cần native compiler cùng architecture/ABI với JDK. Chương trình in stdout xác định khi biên dịch và tải thư viện thành công.

### 4.1. Java: `NativeBoundaryDemo.java`

```java
public class NativeBoundaryDemo {
    static {
        System.loadLibrary("boundarydemo");
    }

    private static native int add(int left, int right);

    private static native int twiceViaJava(int value);

    private static native void requireNonNegative(int value);

    private static int doubleValue(int value) {
        return value * 2;
    }

    public static void main(String[] args) {
        System.out.println("sum=" + add(5, 7));
        System.out.println("callback=" + twiceViaJava(9));

        try {
            requireNonNegative(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        System.out.println("done");
    }
}
```

`System.loadLibrary("boundarydemo")` dùng **tên logic**, không kèm `lib` prefix hay đuôi `.so`, `.dylib`, `.dll`. Ở ví dụ này class không khai báo package để C symbol dễ đọc.

### 4.2. Sinh header JNI và bytecode Java

Trong thư mục chứa Java source:

```bash
javac --release 17 -h . -d out NativeBoundaryDemo.java
```

`javac -h .` tạo file **`NativeBoundaryDemo.h`** với JNI function prototypes tương ứng; `-d out` đặt `NativeBoundaryDemo.class` vào thư mục `out`. Không sửa các prototype JNI bằng tay khi đã có header do compiler sinh.

### 4.3. C: `boundarydemo.c`

```c
#include <jni.h>

static jint add_in_c(jint a, jint b) {
    const jint result = a + b;
    return result;
}

JNIEXPORT jint JNICALL
Java_NativeBoundaryDemo_add(JNIEnv *env, jclass clazz,
                            jint left, jint right) {
    (void)env;
    (void)clazz;
    return add_in_c(left, right);
}

JNIEXPORT jint JNICALL
Java_NativeBoundaryDemo_twiceViaJava(JNIEnv *env, jclass clazz,
                                     jint value) {
    jmethodID method =
        (*env)->GetStaticMethodID(env, clazz, "doubleValue", "(I)I");

    if (method == NULL) {
        return 0; /* Có thể tồn tại JNI exception pending. */
    }

    return (*env)->CallStaticIntMethod(env, clazz, method, value);
}

JNIEXPORT void JNICALL
Java_NativeBoundaryDemo_requireNonNegative(JNIEnv *env, jclass clazz,
                                           jint value) {
    (void)clazz;

    if (value >= 0) {
        return;
    }

    jclass type =
        (*env)->FindClass(env, "java/lang/IllegalArgumentException");
    if (type == NULL) {
        return; /* FindClass có thể đã báo exception pending. */
    }

    (*env)->ThrowNew(env, type, "negative value");
    (*env)->DeleteLocalRef(env, type);
}
```

Cách đọc:

- `JNIEXPORT` và `JNICALL` theo `jni.h` hỗ trợ visibility/calling convention.
- `add_in_c` mô tả một C helper call. Native compiler có thể tạo stack frame, inline hoặc giữ giá trị trong registers; đây là chi tiết tối ưu hóa.
- `GetStaticMethodID` lấy handle cho method `doubleValue` với descriptor **`(I)I`**.
- `CallStaticIntMethod` đi từ native sang Java rồi quay lại native cùng thread.
- Nếu `GetStaticMethodID` thất bại, code trả về với pending exception; `0` không đồng nghĩa JVM bỏ qua exception để Java caller nhận số 0.
- `ThrowNew` thiết lập Java exception pending. `DeleteLocalRef` giải phóng local reference cho `type` và là thao tác được phép trong điều kiện pending exception.
- C library **không** dùng C `throw` hay truyền `errno` sang Java tự động; muốn Java catch một lỗi nghiệp vụ, code native chủ động giao tiếp qua JNI.

### 4.4. Biên dịch thư viện native

**Linux với GCC**, khi `JAVA_HOME` trỏ tới JDK đầy đủ:

```bash
gcc -fPIC -shared -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" -o libboundarydemo.so boundarydemo.c
```

**macOS với Clang**:

```bash
cc -dynamiclib -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" -o libboundarydemo.dylib boundarydemo.c
```

**Windows với Visual Studio Developer Command Prompt** (sử dụng dấu nháy cho biến có dấu cách):

```bat
cl /LD /I"%JAVA_HOME%/include" /I"%JAVA_HOME%/include/win32" boundarydemo.c /Fe:boundarydemo.dll
```

Mỗi lệnh chỉ dành cho **OS và native compiler đã nêu**; cần JDK headers tương ứng và cùng kiến trúc CPU (64-bit/arm64/x86_64) cho JVM và shared library.

### 4.5. Chạy và stdout

Ở thư mục chứa shared library và thư mục `out`:

```bash
java -Djava.library.path=. -cp out NativeBoundaryDemo
```

**Stdout khi biên dịch/liên kết thành công:**

```text
sum=12
callback=18
caught=negative value
done
```

Diễn tiến:

1. `main` gọi native `add(5,7)`. C gọi `add_in_c` và trả `jint 12`; caller Java in `sum=12`.
2. `main` gọi native `twiceViaJava(9)`. C gọi `CallStaticIntMethod` vào Java `doubleValue(9)`, nhận `18`, trả lại caller Java và in `callback=18`.
3. `main` gọi `requireNonNegative(-1)`. C dùng `ThrowNew`; khi JNI method quay về, JVM điều khiển theo đường exception và `main` bắt `IllegalArgumentException` rồi in message.
4. Sau handler Java tiếp tục in `done`.

**Ranh giới thực sự:** một lời gọi Java→native→Java callback có thể tạo chuỗi Java/native execution context đan xen. Không tự kết luận có một native OS thread mới hay một physical stack thứ hai được tạo cho mỗi transition.

## 5. JNI local references, global references và GC

JNI phân biệt **lifetime của reference** với lifetime của biến C chứa nó.

| JNI reference | Lifetime/ownership | Cách quản lý |
| --- | --- | --- |
| **Local** | Có hiệu lực trong JNI local frame/native invocation tương ứng và chỉ thread thích hợp | Thường được giải phóng sau native return; có thể `DeleteLocalRef` sớm |
| **Global** | Giữ được qua nhiều native calls tới khi xóa | `NewGlobalRef` và `DeleteGlobalRef` |
| **Weak global** | Không giữ object sống mạnh như global ref; có thể bị GC clear | `NewWeakGlobalRef`, kiểm tra hợp lệ khi dùng và `DeleteWeakGlobalRef` |
| **Native pointer từ `malloc`** | Theo native allocator/ownership | Phải `free` hoặc release theo library contract |

Ví dụ **sai**, vì C static storage sống lâu hơn một JNI local reference:

```c
/* Minh họa anti-pattern, không phải chương trình độc lập */
static jobject saved;

JNIEXPORT void JNICALL
Java_Example_bad(JNIEnv *env, jclass clazz, jobject value) {
    (void)env;
    (void)clazz;
    saved = value; /* Local JNI reference mất hiệu lực sau native call */
}
```

Nếu thực sự phải giữ object nhiều lời gọi, native code cần **`NewGlobalRef(env, value)`**, kiểm tra lỗi và cuối vòng đời cần **`DeleteGlobalRef`**. Một JNI global reference còn tồn tại có thể giữ Java object reachable trên heap, dẫn tới heap pressure nếu bị rò.

### 5.1. Một `jobject` không phải con trỏ thô

JNI handles được JVM theo dõi. GC có thể di chuyển object phù hợp implementation; không cast `jobject` trực tiếp thành `void*` rồi đọc member layout như C struct.

Ngay cả khi `jobject` được lưu trong C stack slot, **lifetime của handle do JNI quản lý**, không do việc C local biến còn trong scope hay không.

### 5.2. Strings/arrays và quy tắc release

Một snippet minh họa cách lấy dữ liệu `jstring` đúng API:

```c
/* Trong native function có JNIEnv *env, jstring text;
   chỉ là snippet, không phải function độc lập. */
const char *buffer = (*env)->GetStringUTFChars(env, text, NULL);
if (buffer == NULL) {
    return; /* Có thể đang pending OutOfMemoryError. */
}

/* Đọc buffer trong phạm vi hợp lệ */
(*env)->ReleaseStringUTFChars(env, text, buffer);
```

Cần ghi nhớ:

- `GetStringUTFChars` dùng **Modified UTF-8** của JNI, không phải mọi trường hợp giống UTF-8 chuẩn.
- Không dùng C `free(buffer)` cho memory mà JNI function yêu cầu **`ReleaseStringUTFChars`**.
- Các hàm `Get<PrimitiveType>ArrayElements` có hàm release tương ứng; có thể nhận copy hoặc vùng được giữ theo implementation.
- Dùng `GetPrimitiveArrayCritical` nên hạn chế nghiêm ngặt thao tác làm block giữa `Get` và `Release` theo JNI contract.
- Trong native loop tạo hàng nghìn JNI local refs, nên quản lý refs theo lượt hoặc dùng `PushLocalFrame`/`PopLocalFrame` thay vì tích lũy vô hạn.

## 6. `JNIEnv*` gắn với thread, không được chia sẻ tùy tiện

JNI `JNIEnv*` chỉ hợp lệ trên **thread hiện tại**. Không dùng một pointer `env` lấy ở thread A để gọi JNI từ thread B.

```text
Java thread A → native f() → JNIEnv* envA
Java thread B → native f() → JNIEnv* envB

envA KHÔNG được dùng trong C function thực thi ở thread B.
JNI local references cũng có thread/lifetime constraints riêng.
```

C code có C static/global variables chia sẻ được giữa threads trong một process. Nhưng điều đó không làm `JNIEnv*` hoặc JNI local refs trở thành thread-safe globals; phần data C chia sẻ cần synchronization đúng.

### 6.1. Khi native library tự tạo OS thread

Một thread do `pthread_create` hoặc Windows native API tạo **không tự động có quyền gọi JNI APIs của JVM**. Native thread muốn gọi Java phải:

1. Lấy `JavaVM*` thích hợp, chẳng hạn qua `GetJavaVM` trong JNI context hợp lệ.
2. Từ native thread mới, gọi **`AttachCurrentThread`** để nhận `JNIEnv*` của chính thread đó.
3. Sử dụng JNI theo những quy tắc local refs và exception state của thread.
4. Gọi **`DetachCurrentThread`** khi hoàn tất và trước lúc thread kết thúc, theo API contract.

Thread được attach phải có stack capacity phù hợp, được cấu hình theo OS thread API/ABI. `DetachCurrentThread` không được thực hiện trong một trạng thái còn Java frames trên stack trái API restriction.

**Một Java call vào native method không tự tạo thread mới.** Tạo thread là quyết định riêng của native library nếu nó có code làm việc đó.

## 7. Pending Java exception khác lỗi C làm sập process

JNI có `Throw` / `ThrowNew`, `ExceptionCheck` / `ExceptionOccurred` và `ExceptionClear`.

### 7.1. `ThrowNew` không tương đương C++ stack unwinding

Khi `ThrowNew` thành công, JNI đánh dấu **Java exception đang pending**. Native function **không tự nhảy vào Java `catch` ngay giữa execution của C**. Nó cần quay về JVM hoặc xử lý pending exception theo JNI restrictions; nhiều JNI functions không được gọi khi có exception pending.

```text
C: ThrowNew(...)
     │
     ▼
pending Java Throwable ở thread JNI
     │
     ▼
C method trả quyền thực thi về JVM
     │
     ▼
JVM tìm Java exception handler hoặc unwind Java frames
```

Trong ví dụ, Java `requireNonNegative(-1)` không hoàn tất bình thường; JVM chạy `catch` trong `main`.

### 7.2. C `SIGSEGV` khác Java `NullPointerException`

Nếu C dereference sai địa chỉ, use-after-free, buffer overflow hoặc trộn sai allocator, hậu quả có thể là:

- Unix signal như `SIGSEGV`.
- Windows access violation.
- Fatal error log `hs_err_pid...log` do HotSpot ghi nếu có thể.
- Crash toàn tiến trình hoặc memory corruption khó phát hiện.

**Java `try/catch(Exception)` không được bảo đảm cứu một process native crash.** Java bytecode verifier không có khả năng kiểm tra các phép truy cập con trỏ C tùy ý.

## 8. Native stack overflow, OOM và giới hạn Java heap

Các platform threads có thể tiêu tốn native address space và memory đáng kể vì stacks và thread management structures. Ứng dụng tạo quá nhiều threads có thể báo lỗi không cấp phát được native thread dù Java heap vẫn còn.

Công cụ JVM phổ biến:

```bash
java -Xss1m MyApp
```

`-Xss` cấu hình Java thread stack size trong các JVM hỗ trợ, nhưng **không bảo đảm native C stack của mọi thread — đặc biệt threads do thư viện C tự tạo — đúng 1 MiB**. OS thread stack layout, guard pages và stack reservation khác nhau theo implementation.

Đừng mặc định tăng `-Xmx` giải quyết native OOM. `-Xmx` dành cho Java heap; native stack resources, direct memory, JNI allocations và giới hạn process là những hạng mục cần đánh giá riêng.

### 8.1. Java recursion và C recursion

- Java recursion có thể làm JVM stack cạn và ném `StackOverflowError`.
- C recursion sâu có thể vượt native stack, dẫn tới crash hoặc lỗi khác tùy OS/JVM.
- Chuỗi JNI callbacks có thể xen kẽ Java/native code và cùng tạo áp lực lên execution stack resources.
- Không nên dùng bài thử “đệ quy vô hạn native” trong ứng dụng production hoặc IDE session chung để đo stack size; có nguy cơ giết toàn JVM.

## 9. Chẩn đoán native boundary thực tế

Các lệnh Java/HotSpot hữu ích:

```bash
java -version

# Xem Java thread dump, không giả định sẽ thấy mọi native C frame:
jcmd <pid> Thread.print

# Kiểm tra thêm một số hành vi JNI (HotSpot):
java -Xcheck:jni -Djava.library.path=. -cp out NativeBoundaryDemo

# Native Memory Tracking phải bật lúc JVM khởi động:
java -XX:NativeMemoryTracking=summary -Djava.library.path=. -cp out NativeBoundaryDemo

# Trong khi process có NMT vẫn đang chạy:
jcmd <pid> VM.native_memory summary
```

**Các giới hạn quan trọng:**

- `jcmd Thread.print` giúp xem Java frames/trạng thái threads, không thay thế GDB/LLDB/WinDbg để xem toàn bộ native C stack frames.
- `-Xcheck:jni` có thể phát hiện nhiều lỗi dùng JNI APIs nhưng **không chứng minh mọi mã C không có buffer overflow/data race**.
- HotSpot Native Memory Tracking (**NMT**) chỉ theo dõi những nguồn native memory thuộc phạm vi HotSpot tracking; **không hứa thấy mọi `malloc` từ bên trong mọi native library bên thứ ba**.
- `jcmd VM.native_memory` chỉ hoạt động đúng khi JVM đã bật NMT với chế độ phù hợp lúc khởi động.
- Khi JVM crash, đọc **`hs_err_pid...log`, core dump, native backtrace và debugger symbols** thay vì chỉ tìm Java exception stack trace.

### 9.1. `UnsatisfiedLinkError`

Thường xảy ra khi:

- Tên/đường dẫn shared library không đúng với `System.loadLibrary` hoặc `java.library.path`.
- `.dll` / `.so` / `.dylib` sai architecture/ABI so với JVM.
- JNI C symbol không khớp tên Java class, package, method hoặc overloaded signature.
- Thiếu các shared library dependencies khác.
- File library bị OS loader từ chối do policy/permission tương ứng.

`UnsatisfiedLinkError` thuộc nhóm `LinkageError`; nó không báo rằng Java heap thiếu memory. Khi đổi Java signature, phải biên dịch lại **cả generated header và C library** hoặc cập nhật `RegisterNatives` nếu dùng đăng ký động.

## 10. JNI, DirectByteBuffer và FFM API không đồng nghĩa

JNI là một cơ chế tương tác lâu đời để Java chạy code native và callback vào JVM. Java cũng có `ByteBuffer.allocateDirect` để sử dụng direct buffers, nhưng một direct buffer không phải là một “native method stack”; nó chủ yếu liên quan storage bên ngoài heap và các API quản lý buffer.

Trong Java hiện đại, **Foreign Function & Memory (FFM) API** cung cấp hướng tiếp cận khác tới native functions/memory. FFM trở thành tính năng chuẩn trong **Java 22**. Không nên lấy ví dụ FFM Java 22 rồi quảng bá như API chuẩn có thể dùng y hệt trên Java 17 mà không có khác biệt về trạng thái feature, module, flags và lifecycle.

Dù API nào, code native vẫn phải tôn trọng **ABI, memory ownership, stack/thread context, resource lifetime và quy tắc an toàn**. Không có cơ chế nào tự biến mọi raw C pointer accesses thành Java GC-safe operations.

## 11. Các lỗi hiểu nhầm thường gặp

1. **“Native method stack nằm trong Java heap.”** Sai: native stacks và Java heap có vai trò/runtime allocation khác nhau.
2. **“Mọi JVM có một native method stack vật lý độc lập tuyệt đối.”** Sai: JVMS cho phép nhiều cách triển khai.
3. **“Mỗi native call tạo một thread mới.”** Sai: bình thường Java thread hiện tại đi qua boundary.
4. **“Native method vẫn có `Code` chứa body Java bytecode.”** Sai: `ACC_NATIVE` method không có body `Code` như method Java bình thường.
5. **“`jobject` là C pointer có thể dereference vào Java object layout.”** Sai: đó là JNI reference theo contract VM.
6. **“`JNIEnv*` dùng chung giữa các threads.”** Sai: interface pointer thuộc thread hiện tại.
7. **“C global chứa `jobject` thì reference tự có lifetime global.”** Sai: phải dùng `NewGlobalRef` để kéo dài JNI reference hợp lệ.
8. **“Native method stack là toàn bộ native/off-heap memory.”** Sai: off-heap còn nhiều vùng như `malloc` và direct buffers.
9. **“GC sẽ tự `free` mọi C allocation.”** Sai: `malloc` cần `free`/library-specific release.
10. **“`jstring` luôn trỏ vào C UTF-8 null-terminated.”** Sai: dùng JNI string APIs và hiểu Modified UTF-8.
11. **“`ThrowNew` ngay lập tức thoát khỏi C function bằng C++ exception.”** Sai: pending Java exception là cơ chế riêng.
12. **“Java catch bắt được mọi `SIGSEGV` của JNI.”** Sai: C native crash có thể kết thúc JVM process.
13. **“`-Xmx` càng lớn càng sửa được native stack OOM.”** Sai: heap và native resources có giới hạn riêng.
14. **“`-Xss` buộc stack của mọi C thread có cùng size trên mọi OS.”** Không có cam kết xuyên platform.
15. **“`Thread.print` chứa toàn bộ C frames.”** Sai: Java thread dump không thay native debugger.
16. **“`-Xcheck:jni` phát hiện hết memory corruption.”** Sai: chỉ có phạm vi JNI checks nhất định.
17. **“JNI local references còn sống vĩnh viễn nếu C không gọi `DeleteLocalRef`.”** Sai: thường hết hiệu lực sau native return.
18. **“Truyền `String` qua JNI tức copy toàn bộ object lên native stack.”** Sai: thông thường truyền JNI handle; data access dùng API khác.
19. **“Native method chỉ có thể trả số, không gọi ngược Java.”** Sai: JNI `Call...Method` hỗ trợ callback theo contract.
20. **“Trên Java 17 FFM đã là Java standard API tương đương Java 22.”** Sai: cần phân biệt trạng thái API theo release.

## 12. Tự kiểm tra và đáp án

**Câu 1.** Native method stack có phải tồn tại như một bộ nhớ riêng trên mọi JVM?

**Đáp án:** Không. JVMS cho phép implementation dùng conventional stacks để hỗ trợ native methods và không bắt buộc cấu trúc vật lý riêng.

**Câu 2.** Với `static native int add(int,int)`, C JNI function nhận gì trước hai `jint`?

**Đáp án:** `JNIEnv *env` và `jclass clazz`. Instance native method nhận `jobject receiver` thay cho `jclass`.

**Câu 3.** Trong ví dụ, `twiceViaJava(9)` có quay lại mã Java từ C không?

**Đáp án:** Có. JNI `CallStaticIntMethod` gọi `doubleValue(9)`, trả `18` rồi C trả `18` về Java caller.

**Câu 4.** `ThrowNew` trong C hoạt động như `areturn` không?

**Đáp án:** Không. Nó báo pending Java exception, dẫn tới đường exceptional khi quyền điều khiển quay về JVM.

**Câu 5.** Tại sao lưu local `jobject` vào C static variable không an toàn khi dùng sau native method return?

**Đáp án:** JNI local reference chỉ hợp lệ trong thời gian sống local-reference frame/thread phù hợp, không tự kéo dài theo storage duration của C variable.

**Câu 6.** Nếu muốn native thread tự tạo gọi Java, cần xử lý gì?

**Đáp án:** Dùng `JavaVM*` và `AttachCurrentThread` để nhận `JNIEnv*` của chính thread đó; dùng đúng APIs và `DetachCurrentThread` khi hoàn tất theo hợp đồng.

**Câu 7.** JNI library `malloc` 2 GiB rồi quên `free`. Java heap `-Xmx` thấp có tự quyết định giải phóng 2 GiB đó không?

**Đáp án:** Không. Native memory ownership là độc lập; JVM GC không tự `free` arbitrary C allocations.

**Câu 8.** C truy cập pointer đã được free và gây `SIGSEGV`. Java `try/catch(RuntimeException)` có cứu được chắc chắn không?

**Đáp án:** Không. Native crash có thể làm toàn bộ process kết thúc; cần native diagnostics và sửa C memory safety.

**Câu 9.** Tại sao `jcmd Thread.print` và GDB native backtrace có thể khác nhau?

**Đáp án:** Một bên tập trung Java thread/logical frames, bên kia dựa trên native machine call stack, ABI và debug symbols.

**Câu 10.** `-Xcheck:jni` bảo đảm ứng dụng native an toàn hoàn toàn không?

**Đáp án:** Không; đây là hỗ trợ phát hiện một số JNI API violations, không phải memory-safety verifier tổng quát cho C/C++.

**Câu 11.** `jstring` có thể đưa thẳng cho C `strlen` bằng cast không?

**Đáp án:** Không. Phải dùng JNI string API phù hợp và release; `GetStringUTFChars` dùng Modified UTF-8.

**Câu 12.** Thêm `-Xmx` có giải quyết triệt để lỗi không tạo được native thread không?

**Đáp án:** Không. Cần kiểm tra native address space, OS/process thread limits, native stacks và memory allocations thực tế.

## 13. Ghi nhớ bằng sơ đồ

```text
Java platform thread
   │
   ├─ Java method frames (JVM stack model)
   │       └─ invoke native declaration
   │
   ▼
JVM / JNI transition
   ├─ JNI interface gắn với thread: JNIEnv*
   ├─ primitive arguments và opaque JNI object handles
   └─ native function link / platform ABI
   │
   ▼
C/native function execution
   ├─ C stack/registers (tùy implementation/compiler)
   ├─ C malloc/free cho native heap
   ├─ JNI refs tới Java heap objects
   ├─ có thể callback Java qua JNI
   └─ return value hoặc Java exception pending
   │
   ▼
JVM trả quyền điều khiển về Java caller
   ├─ normal typed result
   └─ exception handler/unwinding

GC quản lý Java heap; JNI quản lý contract references;
native allocator và OS quản lý phần việc riêng của chúng.
```

**Chốt kiến thức:** Native method stack hỗ trợ việc chạy native/VM code khi implementation dùng conventional stacks. Nó không phải nơi chứa toàn bộ Java objects, cũng không phải synonym của mọi vùng off-heap. Qua ranh giới Java ↔ native, JVM/JNI quản lý chuyển đối số, JNI handle lifetime, trạng thái exception và thread identity. Mã native có thể tương tác với JVM nhưng vẫn chịu những rủi ro memory-safety/ABI vốn không tồn tại trong bytecode Java được verify. Khi chẩn đoán, kết hợp Java thread dump, JNI checks, NMT đúng giới hạn và native debugger.

### Tài liệu tham khảo

- [JVMS Java SE 17, §2.5.6 — Native Method Stacks](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.6).
- [JVMS Java SE 17, `2.5.2 / `2.6 — JVM Stacks và Frames](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6).
- [JVMS Java SE 17, §4 — ACC_NATIVE và Code attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html).
- [Java SE 17 JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html).
- [Java SE 17 JNI Specification — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html).
- [Java SE 17 JNI Specification — Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html).
- [JDK 17 javac Documentation, `-h`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
- [JDK 17 Troubleshooting, `-Xcheck:jni`](https://docs.oracle.com/en/java/javase/17/troubleshoot/command-line-options1.html).
