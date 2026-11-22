# Chuẩn bị MethodHandle cho phương thức Java làm hàm gọi lại bằng FFM

**Mục tiêu:** khi một hàm C/C++ nhận đối số là **function pointer (callback)**, Java có thể cung cấp một phương thức Java làm implementation cho callback đó bằng Foreign Function & Memory API (FFM). Bước quan trọng nhất là chuẩn bị một `java.lang.invoke.MethodHandle` **đúng số lượng, thứ tự và kiểu tham số cùng kiểu trả về** mà ABI của hàm callback native mong đợi. Từ `MethodHandle` này, `Linker.upcallStub` tạo một địa chỉ callback có thể truyền vào C.

Chuỗi chuyển đổi đầy đủ:

```text
Phương thức Java (static hoặc instance)
       |
       | MethodHandles.lookup().findStatic / findVirtual
       v
MethodHandle Java gốc
       |
       | bindTo / insertArguments / asType nếu cần
       v
MethodHandle mục tiêu có MethodType khớp callback ABI
       |
       | FunctionDescriptor.of(...) + Linker.upcallStub(handle, desc, arena)
       v
MemorySegment đại diện function pointer / upcall stub
       |
       | Truyền qua downcallHandle(...), layout ADDRESS
       v
C gọi callback(int a, int b)
       |
       v
FFM chuyển C arguments -> Java method handle -> C return value
```

**Hai ranh giới phải tách:** `MethodHandle` là cách JVM biểu diễn một target callable có type chính xác; nó **không phải C function pointer**. `upcallStub` mới tạo cầu nối ABI/native pointer. Một `MethodHandle` đúng Java type nhưng ghép với **sai C ABI**, hoặc một stub đã hết lifetime, vẫn có thể dẫn đến JVM crash. Việc chuẩn bị handle vì thế gồm cả **chữ ký**, **target receiver**, **lifetime**, **thread** và **error contract**.

> **JDK:** FFM `java.lang.foreign` được finalize ở **JDK 22 (JEP 454)**. Bài dùng **Java 22+** và Linux x86-64 cho ví dụ chạy đầy đủ. Java 17 có FFM incubator khác API; Java 19–21 có preview APIs. Vì `Linker.upcallStub`, `downcallHandle` và `SymbolLookup.libraryLookup` là các API restricted, ví dụ chạy với `--enable-native-access=ALL-UNNAMED` khi code ở classpath. Chỉ thực hiện FFM với thư viện native đáng tin và ABI đã được kiểm chứng.

## 1. Callback trong native code cần mô tả rõ hợp đồng C

Xét API C đơn giản:

```c
typedef int (*int_binary_callback)(int left, int right);

int call_binary(int left, int right,
                int_binary_callback callback);
```

Đây là **đoạn chữ ký minh họa**, chưa phải implementation độc lập. `callback` là pointer tới hàm có chữ ký C:

```c
int callback(int left, int right);
```

Trên Linux x86-64 (System V ABI), C `int` là signed 32 bit; FFM sử dụng `ValueLayout.JAVA_INT` làm layout tương ứng. Callback nhận hai `int` và trả một `int`. Do đó target Java mong muốn phải có dạng:

```java
static int javaCallback(int left, int right) {
    return left + right;
}
```

Còn nếu Java muốn dùng một instance method, FFM vẫn yêu cầu handle **sau khi gắn receiver** có hình dạng callable cuối cùng tương đương `(int, int) -> int`.

### Bảng mapping cho callback này

| C ABI | FFM `FunctionDescriptor` | Java carrier trong `MethodHandle` |
| --- | --- | --- |
| `int left` | `ValueLayout.JAVA_INT` | `int` |
| `int right` | `ValueLayout.JAVA_INT` | `int` |
| Trả `int` | Return layout `ValueLayout.JAVA_INT` | `int` |
| Địa chỉ callback `int (*)(int,int)` khi truyền sang C | `ValueLayout.ADDRESS` trong descriptor **của hàm C nhận callback** | `MemorySegment` trong downcall handle |

Điểm dễ nhầm là có **hai FunctionDescriptors khác nhau**:

- **Callback descriptor**: mô tả hàm mà **C sẽ gọi**: `(int,int) -> int`.
- **Native caller descriptor**: mô tả hàm C **nhận pointer callback**: `(int,int,address) -> int`.

Không đưa `ADDRESS` vào callback descriptor chỉ vì ở Java bạn truyền một `MemorySegment` chứa địa chỉ callback. `ADDRESS` nằm tại tham số callback của **hàm C bên ngoài**.

## 2. `MethodType` và `FunctionDescriptor`: hai phía của cùng một hợp đồng

Trong Java:

```java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodType;

FunctionDescriptor callbackDesc = FunctionDescriptor.of(
        ValueLayout.JAVA_INT, // C return int
        ValueLayout.JAVA_INT, // C left int
        ValueLayout.JAVA_INT  // C right int
);

MethodType required = MethodType.methodType(
        int.class, int.class, int.class);

System.out.println(callbackDesc.toMethodType().equals(required));
// true
```

Đoạn trên **minh họa trong Java method** với JDK 22+. `FunctionDescriptor.of(returnLayout, argumentLayouts...)` đặt return layout **trước** trong Java API. `MethodType.methodType(returnType, parameterTypes...)` cũng đặt return type trước. `callbackDesc.toMethodType()` cho kiểu Java FFM mong đợi của callback này là:

```text
(int,int)int
```

Phải kiểm tra cả **arity** và **carrier types**. Mismatch thường gặp:

| Kết quả Java target | Vấn đề |
| --- | --- |
| `(int,int)int` | Khớp C `int (*)(int,int)` trên ABI đã chọn |
| `(long,long)long` | Không khớp vì Java `long` 64 bit khác C `int` 32 bit |
| `(Integer,Integer)Integer` | Boxed references, không phải native scalar carrier `int` |
| `(int)int` | Thiếu một đối số |
| `(int,int)void` | Sai kiểu trả về |
| `(MemorySegment,MemorySegment)int` | Chỉ đúng khi callback C thật sự nhận pointer arguments và descriptor dùng `ADDRESS` |
| `(int,int,int)int` | Có thêm Java argument chưa được bind/drop; không thể đưa trực tiếp vào stub hai tham số |

`Linker.upcallStub` kiểm tra `MethodHandle` có type tương thích với type suy ra từ `FunctionDescriptor`; một số mismatch gây `IllegalArgumentException` ngay khi tạo stub. Nhưng **FFM không thể suy ra hoàn toàn chữ ký thật của symbol C** chỉ từ địa chỉ. Mô tả ABI sai vẫn có thể crash dù code Java compile được.

**Lưu ý ABI:** Linux x64 C `int` khớp `JAVA_INT` trong ví dụ, nhưng các kiểu như C `long`, `size_t`, pointer, struct-by-value và variadic có quy ước khác theo OS/CPU. Với code cần portable, tra `Linker.nativeLinker().canonicalLayouts()` và headers C thay vì giả định C `long` luôn trùng Java `long`. Một số callbacks còn cần calling convention/cấu trúc layout do linker/ABI hỗ trợ.

## 3. Lấy `MethodHandle` cho phương thức Java `static` bằng `findStatic`

Cách đơn giản nhất là chuẩn bị một Java static method có signature trùng callback:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

final class DemoTargets {
    static int safeAdd(int left, int right) {
        try {
            return Math.addExact(left, right);
        } catch (Throwable unexpected) {
            return Integer.MIN_VALUE; // Giá trị lỗi do contract quy định.
        }
    }
}

/* Đoạn minh họa chạy trong một method được phép truy cập DemoTargets. */
MethodHandle handle = MethodHandles.lookup().findStatic(
        DemoTargets.class,
        "safeAdd",
        MethodType.methodType(int.class, int.class, int.class)
);
```

Ở đây `findStatic` tìm method theo **class, tên chính xác và MethodType**. Nếu tên, tham số hoặc return type không tồn tại, việc lookup thất bại với `NoSuchMethodException`; nếu lookup không được quyền truy cập, có thể bị `IllegalAccessException`.

- `MethodHandles.lookup()` mang theo quyền truy cập của class thực hiện lookup. `private` methods chỉ truy cập được khi có quyền phù hợp (ví dụ lookup trong cùng class/nestmate).
- `MethodHandles.publicLookup()` thường chỉ phù hợp với methods/public members thực sự công khai; không dùng làm mẹo vượt module access.
- `MethodHandles.privateLookupIn` có thể cần khi đủ quyền truy cập theo Java module/access rules; nó không phải đường tắt để bỏ qua bảo mật.
- Chữ ký chính xác trong `MethodType` không phải JNI descriptor kiểu `(II)I`, dù cả hai cùng diễn đạt thông tin types.

**Đừng tạo lookup bằng `MethodType.methodType(void.class,...)` nếu C callback trả `int`.** Java có thể chấp nhận method void nhưng FFM callback descriptor không thể biến một return type sai thành dữ liệu native hợp lệ.

## 4. Phương thức Java instance: xử lý receiver bằng `findVirtual` và `bindTo`

Một Java instance method có biến receiver `this`. `MethodHandle` từ `findVirtual` thường có **tham số receiver đầu tiên**, dù chữ ký method Java trông chỉ có hai tham số:

```java
final class OffsetAdder {
    private final int bias;

    OffsetAdder(int bias) {
        this.bias = bias;
    }

    int add(int left, int right) {
        return left + right + bias;
    }
}

// Mã minh họa trong class có quyền truy cập OffsetAdder.
MethodHandle virtual = MethodHandles.lookup().findVirtual(
        OffsetAdder.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class)
);
// virtual.type(): (OffsetAdder,int,int)int

OffsetAdder receiver = new OffsetAdder(10);
MethodHandle bound = virtual.bindTo(receiver);
// bound.type(): (int,int)int
```

**Bước `bindTo(receiver)` rất quan trọng.** C callback chỉ truyền `left` và `right`. Nó **không biết** Java receiver `this` là gì. Nếu đưa `virtual` chưa bind vào `upcallStub` với descriptor hai `int`, type không khớp.

`bindTo` cố định receiver trong MethodHandle. Java callback có thể truy cập state của object đó qua method của nó. State này cần thread-safety nếu C gọi callback từ nhiều native threads. Nếu instance là một tài nguyên `AutoCloseable`, không đóng receiver trước khi native code gọi callback cuối cùng.

`MethodHandle` được bind có thể giữ reference đến receiver. Nhưng **đừng suy ra** C function pointer có lifetime vô hạn chỉ nhờ Java object còn sống: địa chỉ upcall stub còn gắn với `Arena` được truyền vào `Linker.upcallStub`. Hai vòng đời phải được quản lý đồng thời.

## 5. Cố định tham số cấu hình bằng `MethodHandles.insertArguments`

Một Java method có thể có tham số cấu hình mà C callback không biết, ví dụ:

```java
static int addWithBias(int bias, int left, int right) {
    return left + right + bias;
}
```

MethodHandle gốc là `(int,int,int)int`. Dùng:

```java
MethodHandle raw = MethodHandles.lookup().findStatic(
        MyClass.class,
        "addWithBias",
        MethodType.methodType(
                int.class, int.class, int.class, int.class)
);
MethodHandle boundBias = MethodHandles.insertArguments(raw, 0, 10);
// raw.type():       (int,int,int)int
// boundBias.type(): (int,int)int
```

Đây là đoạn **minh họa**, `MyClass` đại diện class đã khai báo `addWithBias`; không phải chương trình đầy đủ. `insertArguments(raw, 0, 10)` cố định tham số Java đầu tiên (`bias`) thành 10. C sẽ chỉ truyền hai `int` còn lại.

**Phân biệt ba thao tác thích nghi:**

| Kỹ thuật | Dùng khi nào? | Trước và sau |
| --- | --- | --- |
| `findStatic` | Callback là Java static method | `(int,int)int` |
| `findVirtual` rồi `bindTo(receiver)` | Callback là instance method | `(Receiver,int,int)int` → `(int,int)int` |
| `insertArguments` | Có tham số cấu hình cố định | `(int,int,int)int` → `(int,int)int` |
| `dropArguments` | C truyền thêm đối số nhưng Java target cố ý bỏ qua | Ví dụ `(int,int)int` → `(MemorySegment,int,int)int` |
| `asType` | Điều chỉnh Java method types theo conversions được MethodHandle hỗ trợ | Không tự thay C ABI hoặc sửa descriptor sai |

Chỉ dùng adapters để biểu diễn **hợp đồng thực**, không dùng `asType` để che giấu sai mapping giữa `C int`/`C long`/pointer. `asType` có thể thêm boxing, cast hoặc conversion của Java, nhưng không biến một layout ABI sai thành đúng.

## 6. Tạo upcall stub từ MethodHandle bằng `Linker.upcallStub`

Khi target đã có type đúng:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

Linker linker = Linker.nativeLinker();
FunctionDescriptor callbackDesc = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT,
        ValueLayout.JAVA_INT);

try (Arena arena = Arena.ofConfined()) {
    // 'target' đã được tạo/bind và có type (int,int)int.
    MemorySegment callbackPointer =
            linker.upcallStub(target, callbackDesc, arena);
    // Truyền callbackPointer vào C trong lúc arena còn mở.
}
```

Đây là **mẫu Java minh họa**, `target` phải được cung cấp ở code gọi; chưa phải class chạy độc lập. Kết quả `callbackPointer` là `MemorySegment` có **địa chỉ upcall stub**. Nó có **kích thước 0 byte** theo contract (đây là function pointer, không phải mảng ký tự/buffer data để đọc).

Vòng đời:

- `upcallStub` tạo native callable bridge và gắn nó với arena.
- Khi `Arena.ofConfined()` được đóng thành công, stub được giải phóng; **C không được gọi pointer ấy sau đó**.
- `Arena.ofConfined()` có confinement theo owner thread: demo chỉ gọi C đồng bộ trên chính thread đã tạo arena.
- Nếu C sẽ gọi callback từ native thread khác hoặc sau khi Java method return, không dùng một confined arena ngắn hạn rồi hi vọng mọi thứ vẫn hợp lệ; cần `Arena.ofShared()`/lifetime đã điều phối và callback thread-safety.
- `Arena.ofAuto()` có GC-managed lifetime không xác định thời điểm; **không** lấy đó làm cơ chế bảo đảm một raw C function pointer được giữ lâu nếu không có Java owner references rõ ràng.
- Một callback stub không phải Java `Runnable`/`Function` chuyển tự động; C phải gọi đúng **C function pointer ABI**.

**Lưu ý quan trọng:** API `upcallStub` là restricted. Không cấp quyền native access đúng có thể dẫn tới `IllegalCallerException`. Trên classpath, chạy với `--enable-native-access=ALL-UNNAMED`; với named module, cấp quyền cho đúng module. Không bỏ qua cảnh báo của JDK mới về restricted/native operations.

## 7. Bài thực hành hoàn chỉnh: Java 22+ gọi C, C gọi lại Java

Ví dụ sử dụng một shared library C nhỏ có hai hàm:

- `call_binary` gọi Java callback **một lần** với hai số nguyên.
- `call_twice` gọi Java callback **hai lần** để thấy một stub có thể được sử dụng lặp lại **trong vòng đời hợp lệ**.

Java chuẩn bị ba MethodHandles:
1. `findStatic` cho `sum`.
2. `findStatic` + `insertArguments` cho `sumWithBias` có bias 10.
3. `findVirtual` + `bindTo` cho `OffsetAdder.apply` có bias 20.

Ba handles sau chuẩn bị đều có `(int,int)int`, khớp callback descriptor. Thư viện C **không lưu** function pointer sau khi trả về, vì vậy `Arena.ofConfined()` và downcall đồng bộ phù hợp.

### File `ffm_handle_callbacks.c`

```c
#include <limits.h> /* INT_MIN */
#include <stddef.h> /* NULL */

/* Trên Linux x86-64, C int khớp FFM JAVA_INT (32-bit). */
typedef int (*binary_callback)(int left, int right);

/*
 * Hợp đồng:
 * - callback chỉ được MƯỢN trong thời gian call_binary chạy.
 * - C không giữ pointer cho lời gọi bất đồng bộ.
 * - INT_MIN được dành làm mã lỗi của bài demo.
 */
int call_binary(int left, int right, binary_callback callback) {
    if (callback == NULL) {
        return INT_MIN;
    }
    return callback(left, right);
}

/* Gọi cùng callback hai lần khi stub còn sống. */
int call_twice(int left, int right, binary_callback callback) {
    if (callback == NULL) {
        return INT_MIN;
    }
    int first = callback(left, right);
    if (first == INT_MIN) {
        return INT_MIN;  /* Không gọi lần hai nếu lần đầu báo lỗi. */
    }
    return callback(first, 1);
}
```

Với compiler Linux/x64, hai symbols `call_binary` và `call_twice` được export từ shared library. Nếu dùng `-fvisibility=hidden` trong build production, phải thêm export attribute phù hợp; lệnh demo dùng mặc định nên không cần.

### File `FfmHandleCallbackDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

import java.nio.file.Path;

import static java.lang.foreign.ValueLayout.ADDRESS;
import static java.lang.foreign.ValueLayout.JAVA_INT;

public final class FfmHandleCallbackDemo {
    // Theo contract demo, dữ liệu thành công không có giá trị này.
    private static final int ERROR = Integer.MIN_VALUE;

    private static int safeSum(int left, int right, int bias) {
        try {
            return Math.addExact(Math.addExact(left, right), bias);
        } catch (Throwable failure) {
            // TUYỆT ĐỐI không cho Throwable thoát qua upcall boundary.
            return ERROR;
        }
    }

    private static int sum(int left, int right) {
        return safeSum(left, right, 0);
    }

    private static int sumWithBias(
            int bias, int left, int right) {
        return safeSum(left, right, bias);
    }

    public static final class OffsetAdder {
        private final int bias;

        public OffsetAdder(int bias) {
            this.bias = bias;
        }

        public int apply(int left, int right) {
            return safeSum(left, right, bias);
        }
    }

    private static MemorySegment stub(
            Linker linker,
            Arena arena,
            MethodHandle target,
            FunctionDescriptor descriptor) {

        if (!target.type().equals(descriptor.toMethodType())) {
            throw new IllegalArgumentException(
                    "Wrong upcall type: " + target.type());
        }
        return linker.upcallStub(target, descriptor, arena);
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // C callback: int (*)(int, int)
        FunctionDescriptor callbackDesc = FunctionDescriptor.of(
                JAVA_INT, JAVA_INT, JAVA_INT);

        // C function:
        // int call_binary(int left, int right, callback pointer)
        FunctionDescriptor callerDesc = FunctionDescriptor.of(
                JAVA_INT, JAVA_INT, JAVA_INT, ADDRESS);

        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle staticHandle = lookup.findStatic(
                FfmHandleCallbackDemo.class,
                "sum",
                MethodType.methodType(
                        int.class, int.class, int.class));

        MethodHandle rawWithBias = lookup.findStatic(
                FfmHandleCallbackDemo.class,
                "sumWithBias",
                MethodType.methodType(
                        int.class,
                        int.class, int.class, int.class));

        MethodHandle biasedHandle = MethodHandles.insertArguments(
                rawWithBias, 0, 10);

        MethodHandle virtualHandle = lookup.findVirtual(
                OffsetAdder.class,
                "apply",
                MethodType.methodType(
                        int.class, int.class, int.class));
        MethodHandle instanceHandle =
                virtualHandle.bindTo(new OffsetAdder(20));

        System.out.println(
                "staticType=" + staticHandle.type());
        System.out.println(
                "biasedType=" + biasedHandle.type());
        System.out.println(
                "instanceType=" + instanceHandle.type());

        try (Arena arena = Arena.ofConfined()) {
            // Cùng arena quản lý lifetime library lookup và stubs.
            SymbolLookup nativeLib = SymbolLookup.libraryLookup(
                    Path.of("./libffmhandlecallbacks.so")
                            .toAbsolutePath(),
                    arena);

            MemorySegment callSymbol = nativeLib.find(
                    "call_binary").orElseThrow();
            MemorySegment twiceSymbol = nativeLib.find(
                    "call_twice").orElseThrow();

            MethodHandle callBinary = linker.downcallHandle(
                    callSymbol, callerDesc);
            MethodHandle callTwice = linker.downcallHandle(
                    twiceSymbol, callerDesc);

            MemorySegment staticStub = stub(
                    linker, arena, staticHandle, callbackDesc);
            MemorySegment biasedStub = stub(
                    linker, arena, biasedHandle, callbackDesc);
            MemorySegment instanceStub = stub(
                    linker, arena, instanceHandle, callbackDesc);

            int staticResult = (int) callBinary.invokeExact(
                    3, 4, staticStub);
            int biasedResult = (int) callBinary.invokeExact(
                    3, 4, biasedStub);
            int instanceResult = (int) callBinary.invokeExact(
                    3, 4, instanceStub);
            int twiceResult = (int) callTwice.invokeExact(
                    3, 4, staticStub);

            // Math.addExact gặp overflow; callback bắt Throwable
            // rồi trả mã lỗi INT_MIN thay vì throw xuyên qua C.
            int overflowResult = (int) callBinary.invokeExact(
                    Integer.MAX_VALUE, 1, staticStub);

            System.out.println("staticResult=" + staticResult);
            System.out.println("biasedResult=" + biasedResult);
            System.out.println("instanceResult=" + instanceResult);
            System.out.println("twiceResult=" + twiceResult);
            System.out.println("overflow=" + overflowResult);
        }
    }
}
```

### Build/chạy trên Linux x86-64

Đặt hai files ở cùng một thư mục và bảo đảm `javac`/`java` đều từ **JDK 22+**. Dùng C compiler cung cấp shared-library ABI tương thích với JDK process:

```bash
cc -std=c11 -Wall -Wextra -O2 -fPIC -shared \
  -o libffmhandlecallbacks.so ffm_handle_callbacks.c

javac FfmHandleCallbackDemo.java

java --enable-native-access=ALL-UNNAMED FfmHandleCallbackDemo
```

Không cần `-Djava.library.path` vì ví dụ dùng `SymbolLookup.libraryLookup(Path, Arena)` với **đường dẫn tuyệt đối** tới `libffmhandlecallbacks.so`, không gọi `System.loadLibrary`. Việc load native library qua `libraryLookup` là restricted, nên flag `--enable-native-access=ALL-UNNAMED` có ý nghĩa thực. Trên JDK 22, FFM đã final, **không cần `--enable-preview`**.

Mã này dành cho Linux x86-64 và C `int` 32 bit. Nếu port sang macOS/Windows hoặc ABI khác, phải thay tên file thư viện, lệnh build và kiểm tra C layout/calling convention. Đừng giả định mọi nền tảng support function pointer cùng ABI chỉ vì Java code compile.

### Stdout kỳ vọng

```text
staticType=(int,int)int
biasedType=(int,int)int
instanceType=(int,int)int
staticResult=7
biasedResult=17
instanceResult=27
twiceResult=8
overflow=-2147483648
```

Giải thích:

- `staticHandle`: `sum(3,4)=7`.
- `biasedHandle`: `sumWithBias(10,3,4)=17`; tham số `bias` đã được `insertArguments` cố định **trước khi** tạo upcall stub.
- `instanceHandle`: `new OffsetAdder(20).apply(3,4)=27`; `bindTo` đã loại receiver khỏi tham số callback mà C cần cung cấp.
- `call_twice`: callback tĩnh lần đầu trả 7, lần sau tính `sum(7,1)=8`.
- `overflow`: `Math.addExact(Integer.MAX_VALUE,1)` ném `ArithmeticException` bên trong callback; `safeSum` bắt `Throwable` và trả `Integer.MIN_VALUE`. C nhận giá trị lỗi này dưới dạng `INT_MIN`.

**Giới hạn của mã lỗi:** `Integer.MIN_VALUE` là sentinel dành riêng trong **contract bài demo**, chỉ hợp lý nếu miền kết quả hợp lệ loại trừ sentinel. API production phải có một error channel rõ hơn (ví dụ status + output pointer/struct, hoặc callback trả mã lỗi và ghi kết quả vào con trỏ khác). Không suy rằng mọi lỗi Java đều có thể chuyển thành một số nguyên hợp lệ trong mọi hệ thống.

### Lúc nào tài nguyên được giải phóng?

Với cùng `Arena.ofConfined()`, Java tạo library lookup và ba upcall stubs, gọi C đồng bộ trong `try`, rồi đóng arena khi rời khối. C **không retain** function pointer, nên không còn native user đang gọi stub sau `try`. Demo không tạo native background thread hay callback bất đồng bộ. Nếu C giữ pointer lại và gọi sau khi arena đóng, code có thể crash. Đây là khác biệt quan trọng giữa một ví dụ hợp lệ và một callback registration service trong thực tế.

## 8. Chữ ký thay đổi thế nào khi callback nhận con trỏ?

Nếu C khai báo:

```c
typedef int (*compare_t)(const void *left, const void *right);
```

thì `(int,int)int` **không phù hợp**. Đây là callback nhận hai **địa chỉ**, không nhận hai số nguyên trực tiếp. Tương ứng:

```java
FunctionDescriptor compareDesc = FunctionDescriptor.of(
        JAVA_INT, ADDRESS, ADDRESS);

// Target Java phải có MethodType:
// (MemorySegment, MemorySegment) -> int.
```

Khi FFM đưa pointer C vào Java callback, carrier thường là `MemorySegment`. Pointer không tự mang length của buffer/struct ở đích. Trong nhiều trường hợp address segment nhận từ C có `byteSize() == 0`. Không thể cứ gọi `segment.get(JAVA_INT,0)` mà không có bounds hợp lệ.

Nếu contract C bảo đảm pointer mỗi lần trỏ tới đúng một `int`, có thể dùng `ADDRESS.withTargetLayout(JAVA_INT)` trong callback descriptor (được linker hỗ trợ) để FFM gắn bounds phù hợp cho target segment. Nhưng việc khai báo target layout phải chính xác theo **C ABI, alignment và lifetime thật**. Không dùng `reinterpret` tùy ý để vượt bounds rồi hy vọng JVM xác minh được C pointer đó.

Dưới đây là một cách minh họa ý tưởng đọc hai `int` từ pointers C:

```java
static int compareInts(MemorySegment left, MemorySegment right) {
    try {
        int l = left.get(JAVA_INT, 0);
        int r = right.get(JAVA_INT, 0);
        return Integer.compare(l, r);
    } catch (Throwable failure) {
        return 0;  // Chỉ là fallback minh họa, không phải API sort chuẩn.
    }
}

FunctionDescriptor compareDesc = FunctionDescriptor.of(
        JAVA_INT,
        ADDRESS.withTargetLayout(JAVA_INT),
        ADDRESS.withTargetLayout(JAVA_INT));
```

Đoạn này chỉ **minh họa** và cần imports class/method phù hợp; không phải full runnable example. Nó tương đương hướng dẫn `qsort` của Oracle FFM: dùng `withTargetLayout` khi biết pointer trỏ tới một C `int`. **Không** đổi `ADDRESS` thành `JAVA_INT` chỉ vì dữ liệu được trỏ tới là `int`.

## 9. Exception safety: không để Java exception thoát khỏi target

Đây là **quy tắc tối quan trọng** trong FFM upcalls.

Đặc tả JDK 22 `Linker.upcallStub` nói target `MethodHandle` **không được để exception thoát ra**. Nếu target ném exception và không bắt, **JVM có thể kết thúc đột ngột**, chứ không đơn giản có một `Java catch` ở phía gọi downcall. Đây không giống cách JNI Java exception thông thường được báo là pending exception của thread.

Ví dụ nguy hiểm:

```java
// KHÔNG truyền trực tiếp method này vào upcallStub.
static int unsafeDivide(int a, int b) {
    return a / b; // b == 0 -> ArithmeticException thoát ra!
}
```

Mẫu có fallback tại biên:

```java
static int safeDivide(int a, int b) {
    try {
        return a / b;
    } catch (Throwable unexpected) {
        return Integer.MIN_VALUE; // Native API phải hiểu mã này.
    }
}
```

Đây là hai đoạn minh họa, không phải full Java class. Bắt `Throwable` ngay tại boundary được dùng để **ngăn mọi throwable thoát qua callback function pointer**; cần cân nhắc việc nuốt các lỗi nghiêm trọng trong thiết kế production. Không làm thao tác JNI/FFM phức tạp hoặc cấp phát nhiều trong nhánh fallback khi JVM đang thiếu memory; dùng một mã lỗi đã định sẵn sẽ đáng tin cậy hơn việc ném tiếp một Java exception.

### Tách business error khỏi callback ABI

Trong hệ thống thật, nên có contract C rõ:

```c
/* Ví dụ contract C cần được triển khai rõ, không phải demo hoàn chỉnh:
 * 0 = success; khác 0 = error.
 * out_value chỉ ghi khi thành công.
 */
typedef int (*callback_with_status)(
        int left, int right, int *out_value);
```

Khi đó Java target có dạng `(int,int,MemorySegment)int` theo callback descriptor `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT, ADDRESS...)` (cần target layout và bounds hợp lệ cho `out_value`). Code Java có thể bắt exception và trả error status, thay vì cố nhét mọi giá trị và lỗi vào một `int` duy nhất.

**Không dùng `MethodHandles.catchException` một cách nửa vời.** Combinator này hữu ích nếu khai báo handler đúng type, nhưng bản thân handler cũng phải không để exception thoát; người viết vẫn phải hiểu mapping carrier và error code. Một wrapper Java method có `try/catch(Throwable)` rõ ràng thường dễ review hơn cho callback.

## 10. Lifetime của callback pointer và Arena là một phần của MethodHandle preparation

`MethodHandle` và upcall stub có vòng đời khác nhau:

| Thứ gì? | Thuộc Java hay native? | Khi nào hết hiệu lực? |
| --- | --- | --- |
| `MethodHandle` target | Java object với method type/target | Theo Java reachability, nhưng không có địa chỉ C callable trực tiếp |
| Receiver bound qua `bindTo` | Java object do handle có thể giữ | Theo reference/ownership của Java objects có liên quan |
| `MemorySegment` từ `upcallStub` | Function pointer native, gắn arena | Khi arena scope bị đóng/invalidated |
| `SymbolLookup.libraryLookup` / native symbol | Địa chỉ C function thuộc library lookup | Phụ thuộc lifetime native library/arena theo contract |
| C pointer giữ trong registry | Raw native address | **Không tự được GC nhận là Java reference**; phải có explicit lifetime policy |

**Điểm sai điển hình:** tạo stub trong `try (Arena a = Arena.ofConfined())`, đăng ký function pointer với C, thoát `try` rồi để C callback vào đêm hôm sau. Java object `MethodHandle` có thể vẫn còn sống nhưng native upcall stub đã bị deallocated. C gọi địa chỉ cũ có thể gây crash.

### Synchronous callback

Nếu C chỉ gọi callback **ngay trong một downcall** và không giữ lại function pointer, một confined arena và `try-with-resources` thường là giải pháp đơn giản nhất. Đóng arena **sau khi downcall return**.

### Asynchronous/native-stored callback

Nếu C giữ callback trong một registry/worker thread để gọi sau:

1. API C phải phân biệt `register(callback)`, `unregister(callback)` và việc chờ mọi callbacks đang chạy hoàn thành.
2. Java dùng arena có lifecycle phù hợp, thường `Arena.ofShared()` nếu callback sẽ được gọi từ nhiều native threads.
3. Java giữ một owner object sống cho callback registrations, method handle/receiver/buffers liên quan và arena.
4. Trước khi close, **unregister**, chặn callbacks mới rồi **chờ** các callbacks in-flight kết thúc.
5. Không unload C library khi vẫn có active callbacks hoặc stubs; không cho C dereference Java/FFM buffers đã đóng.
6. Điều phối riêng error handling, Java object state và synchronization.

`Arena.ofAuto()` cũng có thể được sử dụng trong một số FFM demos, nhưng **không** tạo ra bảo đảm rằng raw function pointer C giữ lâu sẽ giữ Java arena reachable. C pointer không tự biến thành một GC root của Java. Với long-lived callbacks, explicit lifetime và unregister protocol thường dễ chứng minh hơn.

### Callback có được gọi từ bất kỳ thread nào?

Cần phân biệt:

- `Arena.ofConfined()` chỉ phù hợp với access thread confinement đã được định nghĩa. Không truyền stub có confined lifetime cho arbitrary native worker threads rồi tin rằng FFM sẽ tự biến nó thành shared callback.
- `Arena.ofShared()` hỗ trợ lifetime và thread accessibility phù hợp hơn cho callback đa thread, nhưng **không** tự đồng bộ Java receiver state.
- Nếu C callback có thể chạy đồng thời, `sum` thuần hàm không có shared mutable state nên đơn giản; một `OffsetAdder` có mutable fields có thể cần locks/atomics.
- Không để callback block quá lâu nếu C giữ native mutex hoặc gọi callback trong critical section; kiểm tra nguy cơ deadlock/reentrancy.

**Không gọi `arena.close()` để "hủy ngay" callback đang thực thi.** Arena đóng không thay thế việc chặn lời gọi mới và đợi native work hoàn tất. Lỗi lifetime tại FFM boundary có thể ảnh hưởng cả tiến trình.

## 11. Callback có thêm `void *userData`: kết hợp MethodHandle với context

Nhiều C libraries truyền thêm context pointer:

```c
typedef int (*callback_with_ctx)(
        void *user_data, int left, int right);

int schedule_or_invoke(
        callback_with_ctx cb, void *user_data);
```

Phải xác định C thực sự gọi callback với **ba** tham số theo thứ tự `user_data, left, right`. Target MethodHandle có thể nhận `(MemorySegment,int,int)int`.

Nếu Java **không cần** dùng C context, có thể thích nghi một target `(int,int)int` bằng `dropArguments`:

```java
// 'bound' là MethodHandle (int,int)int
MethodHandle ignoresContext = MethodHandles.dropArguments(
        bound, 0, MemorySegment.class);
// ignoresContext.type(): (MemorySegment,int,int)int

FunctionDescriptor descriptorWithContext = FunctionDescriptor.of(
        JAVA_INT, ADDRESS, JAVA_INT, JAVA_INT);
```

Đây là snippet minh họa, yêu cầu `bound` và imports liên quan có sẵn. `dropArguments` thêm một tham số vào type nhưng target bỏ qua khi chạy. **Không** dùng nếu C contract yêu cầu xử lý context thật hoặc cần nhận một trạng thái bên ngoài qua `void *`.

Nếu context là Java state cố định, thay vì chuyền Java object reference trần qua `void*`, thường thuận tiện hơn dùng `bindTo` với receiver Java; method handle gắn Java state vào stub. Khi C API thật sự bắt buộc `void *userData` dùng để phân biệt nhiều registrations, cần thiết kế ID/opaque native context và lifetime độc lập, tránh convert một `jobject`/Java reference tùy tiện thành raw C pointer.

Nếu callback C có đối số là `const char *` hoặc `struct *`, carrier Java phải là `MemorySegment`; cần biết **encoding, byte length, alignment, ownership và lifetime**. Đừng tự suy từ `ADDRESS` rằng pointer có chuỗi NUL hay buffer đủ dài.

## 12. So sánh với JNI callback

Có hai khái niệm "native gọi lại Java" khác nhau:

### JNI reverse call

C có `JNIEnv *`, Java class/object và `jmethodID`, rồi gọi:

```c
/* JNI pseudocode: env, receiver, methodID đã hợp lệ. */
jint result = (*env)->CallIntMethod(
        env, receiver, methodID, (jint)3, (jint)4);
```

Đây là **đoạn minh họa**, không độc lập. JNI route dùng VM metadata và `JNIEnv*`, Java exception được biểu thị qua **pending exception**; C kiểm tra `ExceptionCheck`/xử lý theo contract.

### FFM upcall

C chỉ thấy một C function pointer như `int (*cb)(int,int)`:

```c
int result = callback(3, 4);
```

FFM route dùng `MethodHandle` + `FunctionDescriptor` + `Linker.upcallStub` để sinh một native callable pointer. C không cần `JNIEnv*` tại call site này.

| Đặc tính | JNI Java method call | FFM upcall |
| --- | --- | --- |
| Java target | `jobject/jclass` + `jmethodID` | Java `MethodHandle`, có thể `bindTo` receiver |
| C gọi bằng | `Call<Type>Method` / `CallStatic<Type>Method` | Function pointer C theo ABI |
| Java signature | JNI descriptor `(II)I` và method kind | `MethodType` + FFM `FunctionDescriptor` |
| Bridge | JNI VM call interface | `Linker.upcallStub` |
| Error | JNI pending Java exception | **Không để exception thoát target upcall**; JVM có thể terminate |
| Lifetime | JNI references/thread attach và JVM | Upcall stub `Arena`, native pointer và target state |
| C API bên ngoài cần pointer? | Không tự tạo C function pointer | FFM thích hợp khi C API yêu cầu callback pointer |

Không dùng tên "JNI callback" và "FFM upcall" hoán đổi khi chẩn đoán exception handling; mỗi cơ chế có hợp đồng riêng. Với một library C có callback pointer interface sẵn, FFM có thể giảm nhu cầu viết JNI glue chỉ để chuyển giữa function pointer và Java method.

## 13. Các lỗi thường gặp khi chuẩn bị MethodHandle

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `NoSuchMethodException` tại `findStatic` | Method tên/chữ ký không tồn tại, nhầm static/instance | Kiểm tra return/parameter types và dùng đúng find method |
| `IllegalAccessException` | `Lookup` không có quyền truy cập method/class | Đặt code lookup đúng class/module, dùng access hợp lệ |
| `WrongMethodTypeException` khi `invokeExact` | Return/argument carriers tại call site không khớp chính xác handle | Kiểm tra `handle.type()` và cast/args đúng |
| `IllegalArgumentException` tại `upcallStub` | `MethodHandle` type không tương thích descriptor | So sánh `target.type()` với `descriptor.toMethodType()` |
| Có thêm `Receiver` trong target type | `findVirtual` chưa `bindTo` | `virtual.bindTo(receiver)` |
| Target type `(int,int,int)int` nhưng callback nhận hai `int` | Chưa cố định Java config arg | `insertArguments` với đúng index và type |
| C crash khi gọi callback pointer | ABI C/descriptor sai, stale stub, C gọi sai function pointer type | Đối chiếu C header, C layouts, arena lifetime và native call sites |
| JVM terminate khi callback phát sinh Java exception | Exception thoát `MethodHandle` upcall | Bọc target bằng `try/catch(Throwable)` và mã lỗi rõ |
| `IllegalCallerException` khi tạo stub/library lookup | Chưa enable native access cho module | `--enable-native-access=ALL-UNNAMED` hoặc module tương ứng |
| `UnsatisfiedLinkError` / symbol không tìm thấy | Sai file/thư viện/symbol export | Kiểm tra absolute Path, `nm -D`, C compiler flags |
| `WrongThreadException` tại FFM call | Arena/segment không phù hợp thread | Chọn confined/shared theo contract, kiểm soát thread |
| Crash sau khi Java method return | C giữ pointer của stub từ arena đã đóng | Synchronous-only hoặc owner/unregister/await quy củ |
| Callback đọc sai bytes từ `ADDRESS` | Pointer không có bounds/encoding rõ | Dùng đúng target layout, length và C ownership |
| Java callback dùng shared mutable state sai | C gọi callback concurrently, Java object thiếu locks | Synchronization, immutable state hoặc atomic operations |
| Overhead callback không như kỳ vọng | Quá nhiều bridge crossings và conversions | Benchmark C+Java thực tế; batching nếu API cho phép |

Đừng dùng `catch (Throwable t)` ở Java **bên ngoài `downcall.invokeExact`** rồi nghĩ nó sẽ xử lý được Java exception đã thoát khỏi upcall. Quy tắc là **bắt trong target hoặc một handler method handle đã cấu hình đúng**, trước khi execution quay về C.

## 14. Quy trình review trước khi triển khai

Một checklist thiết kế có thể đánh dấu:

1. **JDK và API:** Java 22+ FFM finalized; build/runtime cùng version API. Native access flag đúng module.
2. **C header:** callback typedef được xác định bằng mã nguồn/header C thật, không đoán arity/types.
3. **ABI:** C `int`, `long`, pointers, structures và calling convention đã map đúng sang FFM layouts trên OS/CPU đích.
4. **Callback descriptor:** `FunctionDescriptor` mô tả **chính callback**, không phải hàm C chứa callback parameter.
5. **Downcall descriptor:** có `ADDRESS` ở tham số C nhận function pointer, các tham số khác đúng thứ tự.
6. **Target:** Java method `static`/instance tồn tại, `Lookup` đủ quyền và `MethodType` đúng.
7. **Receiver:** nếu `findVirtual`, đã `bindTo` một receiver còn hợp lệ; nếu config param, đã `insertArguments` đúng vị trí.
8. **Type verification:** `target.type().equals(callbackDesc.toMethodType())` sau các adapters.
9. **Exceptions:** target không để exception thoát; error return/status/secondary channel được công bố rõ.
10. **Stub lifetime:** `MemorySegment` từ `upcallStub` sống lâu hơn **mọi** native callback calls, nhưng không bị giữ vô hạn vô cớ.
11. **Thread:** arena phù hợp callback thread/confinement, Java receiver state được đồng bộ khi cần.
12. **C retains pointer?:** nếu có, phải có explicit `unregister` + in-flight callback drain trước close/unload.
13. **Pointer arguments:** `ADDRESS` data pointers có bounds/alignment/encoding/lifetime rõ; không áp sai `reinterpret`.
14. **Java callback state:** tránh shared mutable hoặc có lock/atomic, không giữ lock native gây deadlock qua callback.
15. **Failure paths:** library lookup/upcall creation/downcall errors không để leak arenas; `try-with-resources` đóng closeable arena.
16. **Tests:** happy path, bound receiver/config, callback được gọi nhiều lần, overflow/error sentinel, concurrent calls, teardown và ABI mismatch được kiểm tra ở môi trường cô lập.

### Gợi ý kiểm thử có chủ đích

- Bắt đầu bằng C callback hai `int` như demo, không dùng pointer đến struct để giảm yếu tố ABI.
- In `MethodHandle.type()` trước khi tạo stub; nó phải là `(int,int)int`.
- Gọi C với `(3,4)` và kiểm tra 7/17/27 khi dùng ba loại targets.
- Dùng `Math.addExact` ở callback và thử overflow để xác nhận exception đã được xử lý **trong callback**, không cho thoát.
- Chỉ sau khi đúng synchronous case, mới thiết kế async registration/teardown và kiểm thử với native worker threads.
- Dùng `nm -D --defined-only libffmhandlecallbacks.so` (Linux) để kiểm tra symbols khi `libraryLookup.find` thất bại; trên hệ thống khác dùng công cụ symbol tương ứng.
- Khi crash, lưu `hs_err_pid*.log` và C stack trace, kiểm tra descriptor/calling convention/lifetime đầu tiên.

Không đưa một callback ABI sai vào chương trình production để "xem exception gì". Vấn đề ABI có thể gây memory corruption hoặc abort trước khi Java exception nào được tạo.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không thể đưa trực tiếp một Java `MethodHandle` vào đối số C `int (*callback)(int,int)`?

Vì `MethodHandle` là Java object/VM callable handle, **không phải một native code address** theo C ABI. Cần `Linker.upcallStub` để sinh một `MemorySegment` biểu diễn function pointer.

**Câu 2.** `findVirtual` cho `int add(int,int)` trả MethodHandle type gì trước khi bind receiver?

`(Receiver,int,int)int`. C chỉ cung cấp hai `int`, vì vậy cần `bindTo(receiver)` hoặc adapter tương đương để target cuối cùng là `(int,int)int`.

**Câu 3.** Có thể dùng `MethodHandles.insertArguments` để cố định tham số `bias` không?

Có. Với `sumWithBias(int bias,int left,int right)`, `insertArguments(raw,0,10)` biến handle `(int,int,int)int` thành `(int,int)int` tương thích callback.

**Câu 4.** Tại sao callback descriptor là `FunctionDescriptor.of(JAVA_INT,JAVA_INT,JAVA_INT)` nhưng downcall C descriptor thêm `ADDRESS`?

Vì descriptor đầu là **chữ ký callback** hai `int`, return `int`. Descriptor sau mô tả **hàm C nhận callback pointer** làm tham số thứ ba, nên có `ADDRESS`.

**Câu 5.** Nếu Java callback ném `ArithmeticException` xuyên qua upcall, C có nhận được một mã lỗi JNI chuẩn không?

Không. Đặc tả FFM yêu cầu target **không throw** qua upcall; JVM có thể kết thúc đột ngột. Phải catch bên trong callback/handler handle và quy định error channel C.

**Câu 6.** Stub tạo từ `Arena.ofConfined()` có thể được C giữ và gọi sau khi arena đóng không?

Không. Closing arena làm stub hết hiệu lực; gọi stale pointer là lỗi native rất nghiêm trọng. Thiết kế callback synchronous-only hoặc registration owner có lifecycle rõ.

**Câu 7.** Java method nhận `int left,int right` nhưng C callback thực nhận `const int*`. Có thể dùng descriptor `JAVA_INT,JAVA_INT` chỉ vì giá trị được trỏ tới cũng là `int` không?

Không. C nhận **pointer** nên FFM carrier phù hợp là `MemorySegment` qua `ADDRESS`. Phải xử lý bounds, target layout và ownership riêng.

**Câu 8.** Vì sao `findStatic` có thể thất bại dù Java method tồn tại?

Có thể tên/return/parameter MethodType không khớp hoặc `MethodHandles.Lookup` thiếu access. Một instance method không thể được lấy bằng `findStatic`.

**Câu 9.** Mã Java `(int,int)int` hợp lệ có bảo đảm một callback C hoạt động đúng trên mọi OS không?

Không. `MethodType` chỉ nói kiểu phía Java. C ABI, calling convention, kích thước `long`/`size_t`, cấu trúc, symbol export và native access policy vẫn phải đúng.

**Câu 10.** Nếu cần gửi Java object state tới C callback, cách nào đơn giản hơn việc ép `jobject` thành `void*`?

Với callback target là instance method, dùng `findVirtual` rồi `bindTo(receiver)`; method handle đã capture Java receiver. Nếu C API còn có `void* userData` bắt buộc, có thể xử lý bằng `MemorySegment` context và contract rõ, không cast Java reference tùy tiện.

**Câu 11.** `MethodHandles.dropArguments` có thể giúp gì?

Nếu C callback có một argument thêm mà Java target không cần, adapter tạo handle nhận argument đó nhưng bỏ qua nó. Descriptor callback vẫn phải phản ánh **C chữ ký thật**; việc bỏ qua là một quyết định xử lý của Java target.

**Câu 12.** Vì sao `Arena.ofShared()` không đủ để tự bảo đảm an toàn callback đa thread?

Shared arena cho lifetime/access phù hợp nhiều threads nhưng không tự đồng bộ Java receiver state, không chặn native calls sau unregister và không giải quyết data races/deadlocks. Cần coordinator và Java synchronization phù hợp.

## 16. Tài liệu chính thức

- Oracle Java SE 22 — [`Linker`: upcall stubs, MethodHandle type, FunctionDescriptor, lifetime, ngoại lệ upcall và safety](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).
- Oracle Java SE 22 — [`FunctionDescriptor` và `toMethodType()`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html).
- Oracle Java SE 22 — [`SymbolLookup`: native library lookup, arena lifetime, restricted method](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- Oracle Java SE 22 — [`Arena`: confined/shared arenas và close](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- Oracle Java SE 22 — [`MethodHandles`: findStatic, findVirtual, insertArguments, dropArguments, catchException](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodHandles.html).
- Oracle Java SE 22 — [`MethodHandle` và `invokeExact`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodHandle.html).
- Dev.java — [How to Handle a Call from Native Code Back to Java Code](https://dev.java/learn/api/io/ffm/upcall/).
- OpenJDK — [JEP 454: FFM finalized trong JDK 22](https://openjdk.org/jeps/454).

**Ghi nhớ:** chuẩn bị callback FFM theo chuỗi **Java method → MethodHandle → bind/adapt để đúng MethodType → FunctionDescriptor tương thích C ABI → Linker.upcallStub trong Arena hợp lệ → truyền function pointer cho C**. Thông thường C không biết Java receiver, nên cần `bindTo`; không để Java exception thoát upcall; quản lý lifetime và thread của stub như một resource native. Đúng chữ ký Java là **cần thiết**, nhưng **chưa đủ** nếu ABI, ownership hoặc callback teardown sai.