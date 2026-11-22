# Phương thức native không có bytecode để chèn trực tiếp

## 1. Vấn đề cốt lõi: có khai báo Java nhưng không có thân lệnh JVM

Một phương thức khai báo bằng từ khóa `native` là **điểm giao tiếp từ Java sang phần triển khai không nằm trong bytecode JVM của chính phương thức ấy**. Java compiler vẫn ghi thông tin phương thức vào tệp `.class`: tên, descriptor (kiểu tham số/kiểu trả về), access flags, annotation và những metadata hợp lệ. Nhưng nó **không ghi thân `Code` chứa các instruction** cho phương thức đó.

Ví dụ:

~~~java
public final class NativeExample {
    public static native int add(int left, int right);

    public static int addJava(int left, int right) {
        return left + right;
    }
}
~~~

Đây là **mã nguồn minh họa** (có thể lưu thành `NativeExample.java` rồi biên dịch), chưa kèm thư viện native để gọi `add` thành công. Hai phương thức có cùng kiểu tham số và kết quả nhưng:

- `add` có cờ **`ACC_NATIVE`**. Trong `method_info` của tệp class **không có thuộc tính `Code`**.
- `addJava` có phần triển khai Java bình thường, được `javac` dịch thành bytecode (ví dụ những instruction tương đương đọc hai tham số, cộng rồi `ireturn`).
- Lời gọi `add` phải được JVM liên kết đến **implementation native** theo cơ chế phù hợp, chẳng hạn JNI. Cách thực thi native không đồng nghĩa một mảng instruction JVM để ASM/Byte Buddy tự chèn vào.
- Một `ClassFileTransformer` vẫn **nhìn thấy dữ liệu class file chứa khai báo native method**, nhưng không có thân bytecode của chính method ấy để thêm probe ở đầu/cuối.

**Kết luận ngay:** “native không có bytecode để chèn trực tiếp” **không** có nghĩa “không thể quan sát bất kỳ điều gì về native”. Nó nghĩa là **không thể đặt các instruction JVM trực tiếp vào `Code` vốn không tồn tại của native method**. Có các cơ chế khác: wrapper Java, native-method prefix trong Java instrumentation, hay sự kiện/hook của JVM TI.

### 1.1. Phân biệt bốn lớp công nghệ

| Tầng | Vai trò | Có bytecode JVM để weave không? |
| --- | --- | --- |
| `method_info` của native method | Khai báo tên, descriptor, `ACC_NATIVE` | **Không** có `Code` trong native method |
| Phương thức Java gọi native | Chứa `invokestatic`, `invokevirtual` hoặc instruction call phù hợp | **Có**, có thể instrument call site |
| Wrapper Java quanh native | Chứa before/after/try-finally và gọi native | **Có**, có thể instrument wrapper |
| Phần triển khai native | Mã máy/library hoặc cơ chế do JVM cung cấp | **Không** thể sửa bằng cách chèn JVM bytecode vào native method |

Không nên dùng “JNI” và “native” như hai từ đồng nghĩa tuyệt đối: nhiều method native của JDK dùng đường thực thi đặc thù hoặc được JVM tối ưu bằng intrinsic, trong khi **JNI** là một giao diện tiêu chuẩn để kết nối mã Java và native library. Bài tập C/JNI ở dưới là một ví dụ cụ thể, không có ý nói mọi native method đều bắt buộc phải thực thi qua một file `.so` tự viết.

## 2. Căn cứ đặc tả JVM: `ACC_NATIVE` và quy tắc `Code`

Theo Java Virtual Machine Specification (JVMS), mỗi khai báo method có cấu trúc `method_info` gồm các trường như `access_flags`, `name_index`, `descriptor_index` và bảng `attributes`. `Code` là một thuộc tính mô tả **các instruction và metadata thực thi của method**.

Quy tắc ở **JVMS `4.7.3**:

- Phương thức **`native` hoặc `abstract`** **không được chứa** thuộc tính `Code` trong `method_info`.
- Phương thức không phải native, không abstract cần một thuộc tính `Code` theo ràng buộc của định dạng class file.
- `ACC_NATIVE` có bit mask `0x0100` trong `method_info.access_flags`.
- `ACC_ABSTRACT` là trường hợp khác: cũng không có code nhưng vì **không có implementation trong chính method**, chứ không phải gọi sang native implementation.

Sơ đồ:

~~~text
method_info của Java method có thân:
    name_index -> "addJava"
    descriptor -> "(II)I"
    flags      -> ACC_PUBLIC, ACC_STATIC
    attributes -> Code {
        max_stack, max_locals,
        code[] = JVM instructions
        exception_table, ...
    }

method_info của native method:
    name_index -> "add"
    descriptor -> "(II)I"
    flags      -> ACC_PUBLIC, ACC_STATIC, ACC_NATIVE
    attributes -> (có thể có annotation / Exceptions / metadata khác)
    KHÔNG CÓ Code attribute
~~~

Đây là **mô hình cấu trúc**, không phải bản dump bytes theo offset. Mọi công cụ bytecode phải tuân quy tắc này khi ghi class-file output. Việc tự gắn `Code` vào một method vẫn mang `ACC_NATIVE` sẽ tạo tệp class không hợp lệ theo JVMS; không phải một mẹo để khiến JVM thực thi phần Code mới.

**Không nhầm “không có `Code`” với “không có class-file entry”.** Native method vẫn có tên/descriptor/flags và có thể được reflection như `Class.getDeclaredMethod(...)` hoặc kiểm tra bằng `Modifier.isNative(...)`.

Nguồn: [JVMS Java 17 — `4.6 Methods và `4.7.3 Code Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html).

## 3. `javap` cho thấy sự khác nhau bằng mắt

Biên dịch ví dụ `NativeExample.java` ở trên:

~~~bash
javac --release 17 NativeExample.java
javap -p -c NativeExample
javap -p -v NativeExample
~~~

`javap -c` in instruction cho method có phần `Code`. Nó hiển thị khai báo method native nhưng **không có danh sách instruction của chính native method**.

Đầu ra rút gọn có ý nghĩa:

~~~text
public static native int add(int, int);

public static int addJava(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: ireturn
~~~

Đây là **trích đoạn minh họa của `javap -c`**, không phải toàn bộ output (constructor, constant pool và chi tiết khác bị lược). Khi dùng `javap -v`, hãy tìm cờ `ACC_NATIVE` và kiểm tra **không có `Code:` thuộc về method native**. Các dòng `Code:` sau đó có thể thuộc constructor hoặc phương thức Java khác, nên đừng tìm nguyên chuỗi `Code:` trên toàn file rồi kết luận sai.

Nếu parser dùng ASM hoặc một bytecode library phát hiện flag `ACC_NATIVE`, nó phải **không đối xử với native method như một method có instruction list**. Việc `visitMethod` được gọi khi parser gặp khai báo native không đồng nghĩa `visitCode` có body hợp lệ để instrument.

## 4. Vì sao transformer không thể tự chèn mã vào body native?

Trong Java agent, `ClassFileTransformer.transform(...)` nhận **toàn bộ mảng class-file bytes**. Vì vậy agent vẫn có thể:

- Quan sát **khai báo** native method: class name, method name, descriptor, flags.
- Thay đổi **những method Java có Code** cùng class, ví dụ call site `someNative(...)`.
- Ở giai đoạn class load được phép, biến đổi **cấu trúc class** để thêm wrapper Java và đổi cách liên kết native name theo cơ chế hỗ trợ.
- Trả class-file bytes được xây lại hợp lệ.

Nhưng `transform` **không nhận địa chỉ máy** của native function dưới dạng một danh sách JVM instructions. Có hai bất biến:

1. Native method gốc có `ACC_NATIVE` thì không có `Code` để đặt `onEnter/onExit` bằng JVM bytecode vào “đầu/cuối” chính method.
2. JVM/Java agent không cung cấp API “sửa tùy ý implementation C/C++ của JNI function” qua `ClassFileTransformer`.

Ví dụ dạng callback:

~~~java
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    if (className == null || !className.startsWith("demo/")) {
        return null;
    }

    // Parser có thể nhận ra method_info mang ACC_NATIVE.
    // Không có Code attribute để thêm instruction vào method ấy.
    // Khi chỉ quan sát, trả null để không thay đổi class bytes.
    return null;
}
~~~

Đây là **mảnh code trong lớp implements `ClassFileTransformer`**, cần có import/agent setup, không phải chương trình độc lập. `return null` nghĩa transformer này không thay đổi bytes, không cấm transformer khác áp dụng.

**Điểm phân biệt:** chỉnh sửa **call site Java** là có thể, nhưng không chắc bắt được tất cả lời gọi tới native function (một số call site không nằm trong phạm vi instrument, một số native method có nhiều entry path, hoặc JVM áp dụng cơ chế đặc thù). Nếu cần quan sát tại **thời điểm native function được bind/call**, phải chọn công cụ ở tầng thích hợp thay vì tuyên bố đã sửa native body.

### 4.1. So sánh với abstract method

`abstract` cũng không có `Code`, nhưng tình huống khác:

- Abstract method không có implementation trong class/interface khai báo; JVM dispatch tới **implementation cụ thể** ở subclass hoặc class cung cấp method.
- Native method có implementation **ngoài JVM bytecode của method ấy**, thường thông qua native binding.
- Với abstract, có thể instrument method override **có code**.
- Với native, thường instrument **wrapper/call site**, hoặc dùng khả năng native/JVM TI.

Hai trường hợp cùng không có `Code`, nhưng lời giải instrumentation không giống nhau.

## 5. Hướng thực hành đơn giản nhất: dùng wrapper Java

Nếu bạn **kiểm soát source hoặc phiên bản API**, đặt một non-native Java method bao ngoài native declaration:

~~~java
private static native int nativeAdd(int a, int b);

public static int add(int a, int b) {
    long start = System.nanoTime();
    try {
        return nativeAdd(a, b);
    } finally {
        long elapsed = System.nanoTime() - start;
        recordElapsed(elapsed);
    }
}
~~~

Đây là **mảnh code trong một class**; `recordElapsed` do ứng dụng định nghĩa. Wrapper `add` có bytecode Java, bao gồm `try/finally` và call instruction tới `nativeAdd`. Nó có thể được instrument tiếp bằng ASM, Byte Buddy, JDK Class-File API (JDK 24+) hoặc cách khác phù hợp.

Ưu điểm: dễ lý giải, có entry/exit và duration, Java stack/caller context rõ ràng, có thể test bằng unit test. Nhược điểm: chỉ đo những lời gọi **đi qua wrapper**; code gọi thẳng native declaration sẽ bỏ qua wrapper. Nếu native function gọi lại Java hoặc chạy async ở native thread, duration của wrapper không nhất thiết bằng toàn bộ công việc native phía sau.

**`finally`** chạy khi return bình thường và khi exception/error unwind thông thường. Nó không bảo đảm event được phát khi process bị hủy đột ngột hoặc native code làm JVM crash. Bản thân recorder cũng cần được thiết kế ít overhead và không che mất lỗi nghiệp vụ.

### 5.1. Đo call boundary khác đo thời gian CPU native

| Phép đo | Quan sát | Không tự khẳng định |
| --- | --- | --- |
| Wrapper `startNanos → finally` | Thời gian tường trôi của một lời gọi qua boundary | Bao nhiêu thời gian là CPU, syscalls, I/O, GC, scheduler |
| Đếm số lần đi qua wrapper | Số lượt gọi wrapper | Mọi native call path trong JVM |
| `ClassFileTransformer` trên Java caller | Java bytecode gọi native | Instruction bên trong JNI function |
| JVMTI native bind event | Thời điểm native implementation được **liên kết** | Số lần native function được gọi |
| Sampling profiler/native stack profiler | Stack/CPU samples tùy công cụ | Mọi lời gọi ngắn hoặc toàn bộ biến nội bộ |

Không dùng một counter `onEnter` ở call site rồi gọi đó là “số native method invocations toàn hệ thống” nếu còn đường gọi khác không instrument.

## 6. Ví dụ Java 17 + JNI C thật: nhìn thấy native declaration và wrapper có Code

Ví dụ dưới đây **tạo và nạp native library thật**, sau đó gọi Java wrapper. Trên Linux x86_64/aarch64 có OpenJDK headers + GCC phù hợp, toàn bộ ví dụ biên dịch/chạy được. Nó dùng một function cộng hai số để stdout không phụ thuộc thời gian hay scheduling.

**Cấu trúc:**

~~~text
native-boundary/
├── NativeBoundaryDemo.java
├── NativeBoundaryDemo.c
├── NativeBoundaryDemo.h          (javac -h tạo)
├── NativeBoundaryDemo.class      (javac tạo)
└── libnativeboundary.so          (gcc tạo, tên trên Linux)
~~~

### 6.1. Tệp `NativeBoundaryDemo.java`

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public final class NativeBoundaryDemo {
    static {
        System.loadLibrary("nativeboundary");
    }

    private static native int nativeAdd(int left, int right);

    private static int observedAdd(int left, int right) {
        System.out.println("enter");
        try {
            return nativeAdd(left, right);
        } finally {
            System.out.println("exit");
        }
    }

    public static void main(String[] args) throws Exception {
        Method nativeMethod = NativeBoundaryDemo.class.getDeclaredMethod(
                "nativeAdd", int.class, int.class);
        Method wrapperMethod = NativeBoundaryDemo.class.getDeclaredMethod(
                "observedAdd", int.class, int.class);
        System.out.println("nativeFlag="
                + Modifier.isNative(nativeMethod.getModifiers()));
        System.out.println("wrapperNativeFlag="
                + Modifier.isNative(wrapperMethod.getModifiers()));
        System.out.println("result=" + observedAdd(7, 5));
    }
}
~~~

**Lưu ý:** `NativeBoundaryDemo.nativeAdd` là private static native declaration **không có Java body**. `observedAdd` là Java method bình thường, do `javac` tạo `Code`; nó gọi `nativeAdd` từ bên trong khối `try/finally`. `System.loadLibrary("nativeboundary")` yêu cầu hệ điều hành/JVM tìm được native library theo `java.library.path`.

### 6.2. Tệp `NativeBoundaryDemo.c`

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL Java_NativeBoundaryDemo_nativeAdd(
        JNIEnv *env, jclass type, jint left, jint right) {
    (void) env;
    (void) type;
    return left + right;
}
~~~

Đây là **một hàm JNI thực**. Tên `Java_NativeBoundaryDemo_nativeAdd` được tạo theo quy tắc JNI về việc ánh xạ Java class/method name sang symbol của native library. `JNIEnv*` và `jclass` là các tham số được JVM truyền cho static native method; ví dụ này không cần dùng chúng.

Dùng `javac -h .` để tạo header `NativeBoundaryDemo.h` và đối chiếu chữ ký function. Không được tự đoán tên JNI symbol khi package/name chứa dấu gạch dưới, ký tự đặc biệt hoặc overload; thuật toán mangle JNI có quy tắc escape và phương án tên dài riêng.

### 6.3. Lệnh trên Linux (JDK 17+, GCC)

Trong thư mục chứa hai tệp source trên:

~~~bash
javac --release 17 -h . NativeBoundaryDemo.java

# JAVA_HOME phải trỏ đến thư mục JDK đang dùng:
gcc -std=c11 -Wall -Wextra -Werror -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  NativeBoundaryDemo.c -o libnativeboundary.so

java -Djava.library.path=. NativeBoundaryDemo

javap -p -c NativeBoundaryDemo
javap -p -v NativeBoundaryDemo
~~~

Dấu `\` cuối dòng trong lệnh `gcc` là cú pháp **shell Unix/Linux**. Người dùng Windows cần toolchain tạo **`nativeboundary.dll`** và dùng JDK header đường dẫn `include/win32`; trên macOS thư viện thông thường là `libnativeboundary.dylib` và có tùy chọn linker/header tương ứng. **Không** lấy câu lệnh `gcc` Linux ở trên rồi chạy nguyên văn trong PowerShell.

Kiểm tra `JAVA_HOME` nếu chưa có giá trị. `javac -h .` tạo JNI header. Trên JDK 21 test đã dùng `javac --release 17` để chứng minh source/API phù hợp Java 17. `java -Djava.library.path=.` phải chạy ở đúng thư mục chứa thư viện đã build.

### 6.4. Stdout chính xác khi native library nạp được

~~~text
nativeFlag=true
wrapperNativeFlag=false
enter
exit
result=12
~~~

Kết quả đã được kiểm thử bằng OpenJDK 21 với `javac --release 17` và GCC trên Linux; các dòng có thứ tự như trên. Vì `observedAdd` thực hiện `return nativeAdd(...)` trong `try`, khối `finally` in `exit` **trước khi** `main` in `result=12`.

`javap -p -v NativeBoundaryDemo` xác nhận tại khai báo `nativeAdd`:

~~~text
private static native int nativeAdd(int, int);
  descriptor: (II)I
  flags: (0x010a) ACC_PRIVATE, ACC_STATIC, ACC_NATIVE

private static int observedAdd(int, int);
  descriptor: (II)I
  flags: (0x000a) ACC_PRIVATE, ACC_STATIC
  Code:
~~~

Đây là **trích đoạn đã chọn** từ `javap -v`, không phải toàn bộ output với constant pool và line numbers. Khác biệt quyết định là **`nativeAdd` không có `Code:`**, còn wrapper `observedAdd` có.

### 6.5. Điều gì xảy ra khi thư viện native không có?

Nếu xóa/đổi tên `libnativeboundary.so` hoặc bỏ đường dẫn `java.library.path`, chương trình có thể ném **`UnsatisfiedLinkError`** ngay ở `System.loadLibrary`. Nếu thư viện có mặt nhưng thiếu symbol tương ứng hoặc không đăng ký native function đúng, lỗi có thể xuất hiện khi JVM resolve/call `nativeAdd`.

Lỗi native binding **không chứng minh** method có hay không có bytecode; đó là hai tầng khác nhau. Khi debug, phân biệt rõ:

1. JVM có tải được thư viện OS không?
2. Native function có được ánh xạ đúng tên/descriptor qua JNI symbol hoặc `RegisterNatives` không?
3. Java wrapper có nhận được ngoại lệ/linkage error và ghi nhận đúng không?
4. Nếu thư viện native gây crash/process abort, Java exception handling và `finally` có thể **không** chạy.

## 7. Với Java agent không sửa source: `setNativeMethodPrefix` là cơ chế wrapper được hỗ trợ

Nếu không thể sửa mã nguồn để tạo wrapper, Java agent có một khả năng đặc biệt:

~~~java
boolean available = inst.isNativeMethodPrefixSupported();
inst.setNativeMethodPrefix(transformer, "$AgentNative$_");
~~~

Đây là **mảnh code trong agent**, cần có `Instrumentation inst` và một `ClassFileTransformer transformer` **đã được đăng ký**. Chỉ gọi `setNativeMethodPrefix` nếu `isNativeMethodPrefixSupported()` trả `true`; flag này còn phụ thuộc manifest agent và JVM.

### 7.1. Ý tưởng chuyển native method thành wrapper Java

Javadoc chính thức mô tả chuyển:

~~~java
native boolean foo(int x);
~~~

Sang hình thức **khái niệm**:

~~~java
boolean foo(int x) {
    // Ghi sự kiện enter, start time, context...
    return $AgentNative$_foo(x);
}
native boolean $AgentNative$_foo(int x);
~~~

Hai đoạn trên là **mẫu chuyển đổi chữ ký**, không phải source có thể chạy độc lập. Trong class đã transform:

- Method `foo` là **non-native wrapper** với `Code` để agent cài logic trước/sau lời gọi.
- Method native được đổi tên thành `$AgentNative$_foo`, vẫn không có `Code`.
- JVM có thể không tìm được native symbol với tên mới; khi native resolution thông thường thất bại, **native prefix mechanism** cho phép thử lại với prefix bị loại bỏ theo hợp đồng.
- Nhờ đó native method đã đổi tên có thể được liên kết tới implementation vốn dành cho tên gốc `foo`.

**`setNativeMethodPrefix` không tự động sinh wrapper!** Transformer phải **thực sự viết lại class file** để có wrapper phù hợp. Chỉ cấu hình prefix mà transformer luôn trả `null` thì native method gốc không được instrument.

Cần chọn prefix có tính duy nhất, tránh trùng tên method có sẵn. Nhiều transformer có thể tạo nhiều lớp wrapper với prefix riêng; đặc tả mô tả thứ tự thử prefix và các trường hợp một tầng không áp dụng wrapper. Không tự đổi tên tất cả native methods một cách máy móc khi không cần.

### 7.2. Khi nào set prefix là lựa chọn phù hợp?

Phù hợp khi agent có thể **biến đổi class ở lần định nghĩa đầu tiên**, muốn giữ API method gốc và ghi nhận trước/sau mỗi native call thông qua Java wrapper. Đây là khả năng **phụ trợ native resolution**, không phải debugger/profiler native machine code.

Cần kiểm tra:

- Manifest JAR có `Can-Set-Native-Method-Prefix: true`.
- JVM và cấu hình agent trả `isNativeMethodPrefixSupported() == true`.
- Transformer đã được `addTransformer(...)` **trước khi** gọi `setNativeMethodPrefix`.
- Transformer tạo **method wrapper có Code hợp lệ** và đổi tên native method đúng prefix/descriptor.
- Không xung đột native symbol/JNI `RegisterNatives`, overload, class loader, module, static/native flags.
- Có test thực khi target native implementation được liên kết và method được gọi.

**Ràng buộc rất quan trọng:** Việc đổi một native method thành wrapper non-native và tạo/thay đổi method có thể là **thay đổi schema/modifiers**. Không được giả định `retransformClasses`/`redefineClasses` của **class đã load** cho phép làm vậy. Với HotSpot/JVM thông thường, nhiều thay đổi schema hay method modifiers bị hạn chế. Vì thế tài liệu Javadoc đặt ví dụ native wrapping ở **initial class definition**. Thiết kế agent cần hoạt động sớm, hoặc lựa chọn kỹ thuật khác cho class đã nạp.

### 7.3. Hai kiểm tra capability khác nhau

| Kiểm tra | Có ý nghĩa gì? | Không chứng minh điều gì? |
| --- | --- | --- |
| `isNativeMethodPrefixSupported()` | Agent/JVM có capability retry native binding bằng prefix | Transformer đã tạo wrapper hay native call đã được đo |
| `isRetransformClassesSupported()` | Có quyền yêu cầu retransformation những class đã load khi điều kiện khác đúng | Được phép đổi native method thành Java wrapper ở class đã load |
| `isRedefineClassesSupported()` | Có quyền redefine class đã load theo ràng buộc JVM | Native implementation có body bytecode để chèn |
| `isModifiableClass(type)` | Class cụ thể có thể là đối tượng của redefine/retransform | Native method bên trong class có `Code` |

Đây là các capability ở **nhiều tầng**. `Can-Set-Native-Method-Prefix` không thay thế `Can-Retransform-Classes`, cũng không phải bằng chứng instrument tất cả native method thành công.

## 8. Ví dụ Java 17: kiểm tra capability native prefix của một agent thật

Ví dụ này kiểm tra **khả năng native prefix và thứ tự đăng ký transformer** trong JVM. Để giữ độc lập với thư viện bytecode, transformer **cố ý không sửa class**; vì vậy đây là ví dụ **kiểm tra cấu hình**, không phải demo native weaving.

**Tệp `NativePrefixAgent.java`:**

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class NativePrefixAgent {
    public static void premain(String options, Instrumentation inst) {
        System.out.println("prefixSupported="
                + inst.isNativeMethodPrefixSupported());
        ClassFileTransformer transformer = new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String name,
                    Class<?> type, ProtectionDomain domain, byte[] bytes) {
                return null;
            }
        };
        inst.addTransformer(transformer, false);
        if (inst.isNativeMethodPrefixSupported()) {
            inst.setNativeMethodPrefix(transformer, "$DemoNative$_");
            System.out.println("prefixConfigured=true");
        }
    }
}
~~~

**Tệp `Target.java`:**

~~~java
public final class Target {
    public static void main(String[] args) {
        System.out.println("target=run");
    }
}
~~~

**Tệp `MANIFEST.MF`:**

~~~text
Manifest-Version: 1.0
Premain-Class: NativePrefixAgent
Can-Set-Native-Method-Prefix: true

~~~

Bản manifest có dòng trống kết thúc main attributes. Không cần `Can-Retransform-Classes: true` trong ví dụ vì transformer dùng `addTransformer(..., false)`.

### 8.1. Biên dịch và chạy

Đặt ba file cùng thư mục và chạy bằng JDK 17+:

~~~bash
javac --release 17 NativePrefixAgent.java Target.java
jar --create --file prefix-agent.jar --manifest MANIFEST.MF NativePrefixAgent.class 'NativePrefixAgent$1.class'
java -javaagent:prefix-agent.jar Target
~~~

Khi build bằng Unix shell hoặc Windows PowerShell, dấu quote đơn trong `'NativePrefixAgent$1.class'` giúp không biến `$1` thành nội dung shell variable. Đây là tên class ẩn danh do compiler tạo. Nếu thay bằng một nested class có tên khác, lệnh đóng JAR cần cập nhật.

**Stdout đã kiểm thử trên OpenJDK 21 (HotSpot):**

~~~text
prefixSupported=true
prefixConfigured=true
target=run
~~~

Môi trường/JVM khác có thể trả `prefixSupported=false`; khi đó code **bỏ qua** `setNativeMethodPrefix`, chỉ in `prefixSupported=false` và `target=run`. Đây là kết quả capability runtime, không nên hardcode `true` trên tất cả VM.

**Chi tiết dễ nhầm:** `ClassFileTransformer` trên Java 17 **không phải functional interface** theo nghĩa có đúng một abstract method; vì vậy không thể thay anonymous class của ví dụ bằng một lambda `(loader, name, ...)-> null` như `Predicate`. Hãy implement/override overload phù hợp.

### 8.2. Prefix khác với việc rename ngay mọi native method

Sau ví dụ trên:

- Agent có capability prefix.
- Một transformer đã được đăng ký và liên kết với prefix.
- **Không có native wrapper nào được sinh** vì `transform` luôn trả `null`.
- Các method của `Target` không bị thay đổi và `target=run` vẫn in bình thường.
- Agent cũng không đụng đến JNI library hoặc triển khai một `NativeMethodBind` callback.

Đây là một test **một API capability**, không được trình bày như công cụ “đo native method hoàn chỉnh”. Muốn có wrapper thực phải thêm bytecode transform, class matching và test JNI binding.

## 9. JVM TI: quan sát native ở tầng VM mà không cần Code attribute

**JVM Tool Interface (JVM TI / JVMTI)** là giao diện native phục vụ debugger, profiler và agent ở mức JVM. Nó có các event/capability liên quan native methods, nhưng **khác** Java `ClassFileTransformer`.

### 9.1. `NativeMethodBind`: sự kiện khi gắn method với địa chỉ native

Theo đặc tả JVM TI:

- `JVMTI_EVENT_NATIVE_METHOD_BIND` có thể được gửi khi VM **liên kết** native method với địa chỉ hàm implementation.
- Điều này có thể xảy ra khi native method được gọi **lần đầu** hoặc khi JNI `RegisterNatives` đăng ký function.
- Callback có tham số `jmethodID method`, `void *address` (địa chỉ dự định bind) và `void **new_address_ptr` (có thể dùng để redirect).
- Agent phải có capability tùy chọn `can_generate_native_method_bind_events` và bật đúng event notification theo spec.
- Việc **thay address** là kỹ thuật native-level, có yêu cầu proxy đúng calling convention/ABI/JNI signature và quản lý vòng đời function pointer; không nên làm bằng code mẫu thiếu kiểm thử.

**Rất quan trọng:** NativeMethodBind là event **khi binding**, không phải **mỗi lần gọi**. Một native method có thể được gọi một triệu lần sau khi đã bind nhưng JVM TI chỉ phát sự kiện bind ở các thời điểm liên kết/đăng ký tương ứng. Không dùng counter bind event làm invocation counter.

Mô hình:

~~~text
JNI/VM resolve native method -> NativeMethodBind event
     |
     +-- address gốc: 0x... 
     +-- agent có thể chọn proxy address thích hợp
     |
     v
Nhiều lần invoke native method về sau
     -> không tự sinh NativeMethodBind ở mỗi lần
~~~

Nếu mục tiêu là thời gian trong chính native implementation, proxy wrapper native phù hợp có thể đo, hoặc dùng profiler native-stack/sampling có kiểm soát. Đây là kỹ thuật khác với đặt `onEnter` vào Java bytecode.

### 9.2. `MethodEntry` và `MethodExit` của JVM TI

JVM TI còn có các event **method entry/exit**, có thể bao gồm cả **native methods** theo đặc tả. Chúng **không đòi `Code` trong native method** vì JVM phát sự kiện từ cơ chế thực thi/quan sát ở mức VM, không phải do agent chèn Java instruction.

Tuy nhiên:

- Cần capability tương ứng, bật event bằng `SetEventNotificationMode`, và kiểm tra phase/thread filter theo JVM TI.
- Event method entry/exit **có thể rất tốn hiệu năng** trên nhiều JVM; đặc tả khuyên thận trọng khi bật rộng ở các ứng dụng performance-critical.
- Callback có thể xảy ra ở môi trường nhiều thread và phase đặc biệt; logic native agent phải đúng ABI, thread safety và lifecycle.
- Method entry/exit VM TI **không phải** tương đương thêm instruction vào `ACC_NATIVE`; nó là một **cơ chế sự kiện khác**.

**Phân biệt:** `NativeMethodBind` có mục tiêu thay địa chỉ khi resolve; `MethodEntry/Exit` quan sát invocation boundary. Không nên nói cả hai event tự mang dữ liệu đầy đủ về native CPU samples, stack trace, hoặc logic code native.

Nguồn: [JVM TI 17 Specification — Native Method Bind và Method Entry/Exit](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html).

### 9.3. Vì sao không đưa pseudo-C JVMTI agent thành “ví dụ chạy ngay”?

Một native JVMTI agent đầy đủ phải cung cấp `Agent_OnLoad`, yêu cầu capability, cài callback `jvmtiEventCallbacks`, bật event, đúng JNI reference/phase và được build thành shared library. Mã C rút gọn thiếu những bước này **không có tính runnable**, nên bài chọn **JNI runnable** và **Java agent runnable** riêng ở trên để minh họa hai phần có thể kiểm chứng, thay vì gắn nhãn “đầy đủ” cho snippet JVMTI chưa triển khai.

## 10. JNI binding, native symbol và những lỗi dễ nhầm

Trong ví dụ JNI, Java khai báo:

~~~java
private static native int nativeAdd(int left, int right);
~~~

Tên native function ở ví dụ không package là:

~~~c
JNIEXPORT jint JNICALL Java_NativeBoundaryDemo_nativeAdd(
        JNIEnv *env, jclass type, jint left, jint right);
~~~

Đây là **chữ ký C minh họa**; phần triển khai đã có ở mục 6. JNI còn hỗ trợ `RegisterNatives` để liên kết trực tiếp class/method descriptor với function pointer thay vì chỉ dựa vào tên symbol. Vì vậy việc có native function không tên `Java_...` trong thư viện **không tự chứng minh** là chưa đăng ký được; cần xem đường đăng ký thực tế.

| Lỗi/hiện tượng | Tầng có vấn đề | Gợi ý |
| --- | --- | --- |
| `UnsatisfiedLinkError` tại `System.loadLibrary` | OS loader không tìm/nạp được thư viện | Đường dẫn, tên file, kiến trúc CPU, ABI và phụ thuộc native |
| `UnsatisfiedLinkError` khi gọi native method | JNI binding chưa resolve đúng function/descriptor | Kiểm tra header `javac -h`, export symbol, `RegisterNatives` |
| `ClassFormatError` sau khi biến đổi native declaration | Class-file output vi phạm format | Không tạo `Code` bên trong `ACC_NATIVE`, kiểm tra flags/schema |
| `VerifyError` hoặc `LinkageError` khi weave wrapper | Java bytecode/descriptor/stackmap hoặc linking sai | Verify output, đúng signature, loader/module visibility |
| `IllegalArgumentException` từ `setNativeMethodPrefix` | Transformer chưa được đăng ký | `addTransformer` trước khi set prefix |
| `UnsupportedOperationException` từ `setNativeMethodPrefix` | Capability native prefix không được bật | Kiểm tra manifest/JVM và `isNativeMethodPrefixSupported` |
| `NullPointerException` tại `setNativeMethodPrefix` | Truyền transformer null | Dùng registered transformer non-null |
| JNI method chạy nhưng metric vẫn bằng 0 | Probe đặt tại caller/wrapper không bao mọi đường | Xác định coverage, test từng đường gọi |
| Native crash/JVM crash | Mã native/ABI/lifetime không an toàn | Debug native stack, sanitizer, crash log và ownership |

**Không nhầm hai dạng `LinkageError`:** Không tìm native implementation có thể tạo `UnsatisfiedLinkError`, là một subtype của `LinkageError`. Nhưng `LinkageError` còn nhiều nguyên nhân khác (loader constraints, binary mismatch, duplicate class definition). Chẩn đoán bằng subclass và stack trace thực tế.

### 10.1. JNI symbol không phải JVM instruction

JVM bytecode chỉ ghi lệnh gọi symbolic reference đến Java method. Khi method đó có `ACC_NATIVE`, VM sẽ dùng đường resolve native implementation. Các lệnh trong C function được compiler native tạo thành **machine code theo ABI**, không phải `Code` trong class file.

Tương tự, bạn không thể dùng `javap -c` để xem instruction của file `libnativeboundary.so`. Nếu cần đọc machine code, đó là công việc của disassembler native thích hợp, cần chú ý symbol stripping/optimization, và **không thuộc Java ClassFileTransformer**.

## 11. Khi class đã được load: schema thay đổi không phải phép miễn trừ

`Instrumentation.retransformClasses(...)` và `redefineClasses(...)` có thể cho phép áp dụng bytecode mới với class đã load khi JVM hỗ trợ và class modifiable. Nhưng **không nên suy** rằng mọi thay đổi cấu trúc class đều hợp lệ.

Biến đổi native wrapping có thể đòi:

- Đổi `ACC_NATIVE` của method gốc sang Java wrapper.
- Đổi tên native method hoặc tạo một method mới để giữ native declaration.
- Thêm `Code` cho wrapper và cập nhật constant pool/stack maps phù hợp.
- Giữ đúng JNI native binding của function gốc.

Các thay đổi **method set/modifiers** thường bị hạn chế trong retransformation/redefinition của class đang chạy. Với JVM HotSpot phổ biến, thêm/xóa method hoặc đổi modifiers/schema kiểu này có thể bị từ chối bằng `UnsupportedOperationException`. Một transformer hoạt động hoàn hảo **ở lúc class được định nghĩa lần đầu** có thể **không** áp dụng được cho class đã load.

Nếu mục tiêu là quan sát native method tồn tại sẵn trong JVM:

- Có thể instrument **Java call sites hoặc wrapper đã tồn tại** nếu chúng có bytecode và class đủ điều kiện.
- Dùng profiler/event phù hợp ở mức JVM TI/native, nếu capability và chi phí phù hợp.
- Cân nhắc khởi động lại JVM với Java agent được nạp **từ đầu** nếu cần native-method prefix wrapping.
- Không cố biến mọi native method đã load thành Java wrapper bằng một lời gọi `retransformClasses` rồi coi lỗi là JVM “không hỗ trợ Java agent”.

Sự khác biệt giữa **instrument class file tại initial definition** và **retransform/redefine existing class** là trọng tâm khi thiết kế khả năng hỗ trợ native.

## 12. Kiến trúc điểm đo: đặt probe ở ranh giới đúng mục tiêu

~~~text
Java caller A ---> Java wrapper W ---> native method N ---> C/JNI function
       |                |                    |                  |
  Call-site probe   Wrapper probe       JVM TI event       Native profiler /
  đếm A->W          đếm lượt qua W      entry/bind        proxy/counter C
~~~

Đặt điểm đo ở đâu phụ thuộc câu hỏi:

| Câu hỏi của hệ thống | Lựa chọn phù hợp |
| --- | --- |
| Bao nhiêu lần một service gọi native API qua wrapper chuẩn? | Instrument wrapper Java đã kiểm soát |
| Một call site cụ thể gọi native bao nhiêu lần? | Transform bytecode **caller** |
| Muốn giữ chữ ký API native nhưng tự sinh wrapper Java khi class load? | `ClassFileTransformer` + `setNativeMethodPrefix` nếu capability hỗ trợ |
| Bao nhiêu lần JVM bind native function? | JVM TI `NativeMethodBind`, **không coi là invocation** |
| Đo method entry/exit kể cả native trong JVM TI | Dùng `MethodEntry/MethodExit` nếu VM/capability hỗ trợ, chấp nhận overhead |
| CPU nóng nằm bên trong C/C++ function nào? | Native stack sampling/profiling hoặc native tracing |
| JNI function bị thiếu không resolve được | Kiểm tra `UnsatisfiedLinkError`, JNI exports và `RegisterNatives` |
| Chỉ cần biết method nào trong một class là native | Reflection `Modifier.isNative`, `javap -v` hoặc đọc `ACC_NATIVE` từ class file |

**Không phải lúc nào cũng nên instrument native code:** nếu mục tiêu chỉ là latency của API Java gọi native, một wrapper/call-site probe thường đã đủ. Native hook sâu có thể tăng chi phí, rủi ro ABI và crash của process.

### 12.1. Ví dụ về thời lượng và exception

Với wrapper dạng:

~~~java
long start = System.nanoTime();
try {
    return nativeOperation();
} finally {
    recordNanos(System.nanoTime() - start);
}
~~~

Đây là **mảnh code minh họa trong method có sẵn `nativeOperation()`/`recordNanos`**, không phải một chương trình. Duration là **elapsed wall-clock trong cùng JVM**, gồm thời gian đi qua Java-to-native boundary và thời gian chờ/scheduling nếu có, không tách sẵn CPU native. `System.nanoTime()` thích hợp so elapsed time trong một JVM; không dùng hai nanoTime ở JVM khác nhau để lấy hiệu.

Đối với JNI call gây `UnsatisfiedLinkError` (một `Error`), `finally` có thể vẫn chạy khi stack unwind bình thường. Đối với JNI native function gây segmentation fault/process abort, Java `finally` **không được bảo đảm thực thi**. Cần mô hình observability chịu được event bị mất và phân biệt process crash với method-level exception.

## 13. Lưu ý an toàn, khả năng tương thích và hiệu năng

1. **Tương thích nền tảng:** `.so`, `.dylib`, `.dll` khác nhau; JNI C compile/link cần header/ABI đúng với JDK target và kiến trúc CPU. Source Java có thể tương thích JDK 17, nhưng native binary xây ở máy khác chưa chắc load được.
2. **Đúng chữ ký JNI:** static native có `jclass`, instance native nhận `jobject`; sai signature có thể gây memory corruption/crash, không chỉ một Java exception.
3. **Không biến prefix thành tìm kiếm toàn cục:** nhiều agent/native wrappers có thể có prefix riêng; cần namespace đủ đặc thù và test thứ tự transform/native resolution.
4. **Không xem `isNativeMethodPrefixSupported` là thao tác instrumentation:** nó chỉ là phép hỏi capability. Phải có transformer thật và native resolution thành công.
5. **Không in log vô hạn trong `transform`:** logger/helper có thể tự kích hoạt class loading; lọc sớm và tránh reentrancy.
6. **Tránh đo tất cả JVM TI MethodEntry trên production:** event volume/overhead có thể lớn. Chỉ bật cho phạm vi/thời điểm cần với capability/filters thích hợp.
7. **Dữ liệu JNI crossing boundary:** native code có thể giữ references, tạo thread, callback vào Java; mỗi thứ có quy tắc JNI references, detach/attach thread và error handling riêng.
8. **Đừng viết vào `classfileBuffer` tại chỗ:** transformer phải trả mảng bytes mới khi thay đổi, không mutate input. Với native method, có thể thay **cấu trúc ở load-time** nhưng không có `Code` nguyên bản để chèn instruction.
9. **Bảo vệ fallback:** nếu JVM không hỗ trợ native prefix, agent cần bỏ qua có báo cáo/cơ chế khác, không làm ứng dụng crash chỉ vì thiếu capability.
10. **Đúng metric semantics:** JNI binding event, method entry, Java call-site call và native CPU sample là bốn nguồn số liệu không tương đương.
11. **Cấu trúc JVM và version:** instrument wrapper tại initial load thường dễ hơn biến đổi schema class đã nạp; cần kiểm tra giới hạn retransform/redefine trên VM đích.
12. **Quyền và bảo mật:** JNI/native library chạy trong process JVM; một thư viện không tin cậy có thể đọc/ghi bộ nhớ hoặc làm sập process. Không nạp JNI từ nguồn không kiểm soát chỉ để “thêm metric”.
13. **Module/class-loader access:** Java wrapper/helper phải nhìn thấy đúng class/helper/module theo JPMS và loading rules; native symbol lookup cũng có namespace/lifetime riêng.
14. **Đủ kiểm thử:** tập kiểm thử nên có normal return, exception/link error, nhiều threads, overload, native library absent, class-load order và nhiều agent.

## 14. Checklist chẩn đoán: native không được instrument

Một quy trình có thể áp dụng cho Java 17+:

1. **Định vị loại method:** `Modifier.isNative(method.getModifiers())` hoặc xem `ACC_NATIVE` trong `javap -v`.
2. **Kiểm tra class file:** method native **không có `Code`**; đừng tìm `visitCode`/instruction của chính method.
3. **Xác định mục tiêu:** cần đo Java call sites, Java-to-native boundary, native bind address hay CPU ở C/C++?
4. **Nếu có wrapper sẵn:** instrument wrapper/non-native caller; kiểm tra có đường bypass không.
5. **Nếu agent muốn tự sinh wrapper:** kiểm tra transformer/matcher, capability `isNativeMethodPrefixSupported` và manifest `Can-Set-Native-Method-Prefix: true`.
6. **Đăng ký đúng thứ tự:** `addTransformer` trước `setNativeMethodPrefix`.
7. **Xác minh output class:** wrapper có `Code`, method native sau đổi tên vẫn có `ACC_NATIVE` và không có `Code`; class-file hợp lệ.
8. **Kiểm tra JNI binding:** thư viện có load được không, native symbol/`RegisterNatives` có ánh xạ đúng không, prefix có bị trùng không?
9. **Nếu class đã load:** kiểm tra schema changes có bị cấm; xem xét startup agent hoặc cách đo khác.
10. **Nếu dùng JVM TI:** xác minh capability, thời điểm/phase event và chi phí; không coi `NativeMethodBind` là per-invocation.
11. **Đối chiếu kết quả:** gọi native function bằng một test có output xác định, xác minh count/exception và không làm thay đổi logic ứng dụng.
12. **Vận hành:** bảo đảm helper/logger/recorder không bị self-instrument, và xác định chính sách khi native code crash.

### Một ví dụ quyết định

~~~text
Cần đếm số lượt gọi System.nanoTime()?
    |
    +-- Chỉ một số call site Java của ứng dụng?
    |      -> instrument caller hoặc wrapper bạn kiểm soát
    |
    +-- Muốn mọi điểm gọi đúng API native thông qua lớp JDK?
    |      -> phải nghiên cứu phạm vi coverage, module/JDK internals,
    |         intrinsic và rủi ro runtime; không tự cho rằng chỉ weave caller là đủ
    |
    +-- Muốn CPU time trong VM/native implementation?
           -> native/JVM TI profiler, không phải chèn JVM bytecode
              vào native method không có Code
~~~

Đây là **mô hình chọn công cụ**, không phải mã executable. Đối với các method được JDK tối ưu đặc biệt, cách định nghĩa thực tế của “một lượt native call” còn cần xác định theo đường thực thi cụ thể.

## 15. Những hiểu lầm phổ biến

1. **“Method native không có `Code` tức không xuất hiện trong `.class`.”** Sai: vẫn có `method_info`, tên, descriptor, `ACC_NATIVE`.
2. **“Có thể thêm instruction ngay trước lệnh đầu native method.”** Sai: method ấy không có lệnh bytecode đầu tiên.
3. **“Không có `Code` thì không thể đo native.”** Sai: đo bằng wrapper, caller, JVM TI hoặc native profiler theo mục tiêu.
4. **“`setNativeMethodPrefix` tự tạo wrapper.”** Sai: transformer vẫn phải thực hiện biến đổi class file.
5. **“`Can-Set-Native-Method-Prefix: true` đảm bảo mọi JVM hỗ trợ.”** Sai: còn phụ thuộc capability JVM, kiểm tra runtime.
6. **“`setNativeMethodPrefix` đổi tên ngay native function trong C.”** Sai: nó thay đổi cơ chế retry native resolution theo prefix, không vá machine code.
7. **“Native method có `Code` sau khi transformer đổi cờ?”** Một method nếu **không còn native** có thể có `Code` như wrapper, nhưng method **vẫn giữ `ACC_NATIVE`** không được có `Code`.
8. **“Một Java agent có thể biến đổi mọi loaded native method bằng retransform.”** Sai: retransform/redefine có ràng buộc schema, modifiers.
9. **“`NativeMethodBind` đếm số invocation native.”** Sai: event diễn ra lúc liên kết function.
10. **“JVMTI không thể quan sát native vì không có bytecode.”** Sai: VM TI có event entry/exit và native binding khi được hỗ trợ.
11. **“JNI C function là JVM bytecode được `javap -c` in ra.”** Sai: C được compiler native dịch thành machine code.
12. **“`UnsatisfiedLinkError` chứng minh phương thức Java không biên dịch đúng.”** Không nhất thiết: Java declaration có thể hợp lệ nhưng thiếu/mismatch native library.
13. **“Chỉ cần dùng lambda để khai báo `ClassFileTransformer` Java 17.”** Sai: interface không có đúng một abstract method duy nhất theo Java 17; ví dụ dùng class triển khai.
14. **“Wrapper `finally` luôn chạy dù JVM crash.”** Sai: crash/halt không theo Java stack unwind thông thường.
15. **“Có thể lấy mọi native elapsed time bằng một call-site.”** Sai: thiếu đường gọi khác và không phân biệt scheduling/CPU.
16. **“Mỗi JVM native method đều là JNI function ngoài thư viện riêng.”** Sai: runtime/JDK có nhiều kiểu triển khai và tối ưu; JNI là một cơ chế chuẩn được trình bày trong demo.

## 16. Câu hỏi tự kiểm tra

1. Trong JVMS, một native method được đánh dấu bằng access flag nào?
2. Nếu method có `ACC_NATIVE`, nó được phép có `Code` attribute không? Vì sao?
3. Vì sao `javap -c` không hiển thị instruction của `nativeAdd` nhưng lại hiển thị instruction của `observedAdd`?
4. `ClassFileTransformer` có thể sửa method Java caller của native không? Điều đó có đồng nghĩa sửa implementation native không?
5. Tại sao một Java wrapper cần `try/finally` nếu muốn ghi event kết thúc cả lúc có exception?
6. `setNativeMethodPrefix` có tự sinh wrapper hay cần transformer tạo output class thích hợp?
7. Manifest attribute nào liên quan native prefix, và API nào hỏi capability này lúc chạy?
8. Tại sao phải gọi `addTransformer` trước `setNativeMethodPrefix`?
9. Khi native method đã được định nghĩa, vì sao `retransformClasses` không chắc cho phép đổi nó thành wrapper non-native?
10. `NativeMethodBind` và `MethodEntry` của JVM TI khác nhau về thời điểm event như thế nào?
11. Vì sao không thể dùng số `NativeMethodBind` để tính số lần gọi một JNI function?
12. Khi native library không có, exception nào thường xuất hiện ở `System.loadLibrary` hoặc lúc resolve native method?
13. Vì sao code Java có thể tương thích `--release 17` nhưng file `libnativeboundary.so` vẫn phụ thuộc OS/CPU?
14. Nếu một JNI function gây segmentation fault, Java `finally` có được bảo đảm chạy không?
15. Khi cần biết CPU hotspot bên trong C function, nên dùng gì thay vì `ClassFileTransformer`?

**Ghi nhớ:** Java `native` method có **khai báo ở `.class` nhưng không có thuộc tính `Code`**. Vì không có các instruction JVM trong chính body ấy, agent không thể “chèn probe vào dòng bytecode đầu/native method” theo cách áp dụng cho method Java bình thường. Chọn **non-native wrapper hoặc call site**, dùng **`setNativeMethodPrefix`** nếu cần transform thành wrapper ngay khi class load và JVM cho phép, hoặc chọn **JVM TI/native tooling** để quan sát binding/invocation ở mức thích hợp. Đừng nhầm native binding event với mỗi lượt gọi, hay nhầm Java agent capability với quyền sửa machine code.

### Tài liệu tham khảo chính thức

- [JVMS Java 17 — `4.6 Methods và `4.7.3 Code Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html)
- [Java 17 — Instrumentation: isNativeMethodPrefixSupported và setNativeMethodPrefix](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java 17 — java.lang.instrument manifest: Can-Set-Native-Method-Prefix](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [JNI Specification Java 17 — Resolving Native Method Names](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [JVM TI Specification Java 17 — NativeMethodBind, MethodEntry/MethodExit](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html)
