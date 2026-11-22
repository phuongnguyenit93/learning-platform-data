# Gọi bằng invokeExact với kiểu tham số và kiểu nhận kết quả chính xác

Khi dùng **Foreign Function & Memory API (FFM)** để gọi một hàm C từ Java, `Linker.downcallHandle(...)` tạo ra một `java.lang.invoke.MethodHandle`. Điểm khác biệt căn bản so với Java method thông thường là lời gọi `handle.invokeExact(...)` chỉ thành công khi **chữ ký tại vị trí gọi (call-site method type) trùng chính xác với `handle.type()`**, gồm cả:

1. **Số tham số** và **thứ tự tham số**.
2. **Kiểu Java tĩnh** của từng biểu thức đối số: `int` khác `long`, `double` khác `float`, `MemorySegment` khác `Object`.
3. **Kiểu kết quả mà call site yêu cầu**: `int` khác `long`, `void` khác mọi kiểu có giá trị.
4. Các tham số FFM đặc biệt khi có: địa chỉ hàm với unbound handle, bộ cấp phát cho struct return, vùng lưu call state, v.v.

**`invokeExact` không tự boxing/unboxing, widening, narrowing, chuyển đối số hoặc thích ứng kiểu trả về.** Nếu không khớp, JVM ném `WrongMethodTypeException`. Đây là lỗi kiểu của **Java MethodHandle**, nhưng vẫn phải phân biệt với lỗi nghiêm trọng hơn: `FunctionDescriptor` khai báo **sai prototype C** có thể dẫn đến hành vi không xác định, hỏng bộ nhớ hoặc crash JVM ngay cả khi `invokeExact` khớp handle đã tạo.

Bài học thuộc nhóm **Gọi hàm bằng FFM**. Ta xây một shared library C nhỏ, dùng Java 22+ tạo downcall handles, in kết quả chính xác, cố ý gây các kiểu `WrongMethodTypeException` an toàn, rồi giải thích `invoke`/`asType`, ABI, pointer, `size_t`, void, thread và lifetime.

> **Phiên bản:** API FFM trong `java.lang.foreign` được hoàn thiện ở **JDK 22** (JEP 454). Ví dụ này chạy trên **Linux/x86-64, JDK 22+ và C11**. Không dùng nguyên import/API này trên Java 17; JDK 21 còn là bản preview. Gọi native bằng FFM cần cấp quyền native access phù hợp.

## 1. Hai chữ ký phải đúng: C ABI và Java MethodType

Xét C prototype:

```c
int add_exact(int a, int b);
```

Để gọi nó từ Java, ta mô tả chữ ký C theo ABI:

```java
FunctionDescriptor descriptor = FunctionDescriptor.of(
    ValueLayout.JAVA_INT,
    ValueLayout.JAVA_INT,
    ValueLayout.JAVA_INT);
```

Đoạn Java ở trên giả định import `java.lang.foreign.*`, là đoạn **trong method** chứ không phải file độc lập. Trong `FunctionDescriptor.of(returnLayout, argumentLayouts...)`, phần tử thứ nhất là **return layout**, hai phần tử còn lại là **argument layouts**. Trên Linux/x86-64, C `int` thường tương ứng `JAVA_INT`, carrier `int.class`. Với ABI khác, nên hỏi `Linker.nativeLinker().canonicalLayouts().get("int")` thay vì đoán.

Nếu tạo bound downcall handle từ đúng địa chỉ function symbol, kiểu Java của handle này là:

```text
(int,int)int

Java call-site:
    int result = (int) add.invokeExact(7, 5);
                       ^              ^  ^
                       |              |  |
              yêu cầu return int     int int
```

Việc **cast kết quả** thành `(int)` là quan trọng. Dù Java có biến bên trái kiểu `int`, cách viết tường minh vẫn giúp compiler tạo chính xác descriptor return tại call site và giúp người đọc xác nhận `int` từ MethodHandle.

Hai tầng kiểm tra hoàn toàn khác nhau:

| Tầng | Ai kiểm tra? | Điều được kiểm tra | Nếu sai |
| --- | --- | --- | --- |
| **Java call site ↔ MethodHandle** | JVM khi thực thi `invokeExact` | `MethodType` tĩnh có trùng với `handle.type()` không? | `WrongMethodTypeException` trước khi gọi hàm |
| **FFM FunctionDescriptor ↔ C binary** | Người tích hợp, build/tests/ABI probe | Kiểu C thật, calling convention, pointer và struct có đúng không? | Có thể gây memory corruption, crash, dữ liệu sai; không tự được JVM xác minh |

Đừng đọc một thông báo “`invokeExact` chạy được” như bằng chứng rằng C ABI đã an toàn. Bạn có thể mô tả sai C function rồi gọi Java **đúng chính descriptor sai đó**.

## 2. `MethodHandle.invokeExact` là lời gọi signature-polymorphic

`MethodHandle.invokeExact` có khai báo Java trông như:

```java
public final Object invokeExact(Object... args) throws Throwable;
```

Nhưng đây là **signature-polymorphic method**: JVM compiler không bắt buộc phải đóng gói mọi đối số thành `Object[]` hay trả một `Object` đúng như chữ ký hiển thị bằng reflection. Tại mỗi vị trí gọi, compiler ghi một *symbolic method descriptor* dựa trên **kiểu biểu thức đối số thực sự** và **kiểu kết quả mà ngữ cảnh yêu cầu**.

Ví dụ dưới đây đều là những call sites khác nhau:

```java
int a = (int) mh.invokeExact(1, 2);   // (int,int)int
long b = (long) mh.invokeExact(1, 2); // (int,int)long
mh.invokeExact(1, 2);                 // (int,int)void
int c = (int) mh.invokeExact(1L, 2L); // (long,long)int
```

Đây là **mã minh họa trong một method**, giả định `mh` là `MethodHandle`. Nếu `mh.type()` là `(int,int)int`, chỉ **dòng đầu** trùng khớp. Ba dòng còn lại có thể biên dịch, nhưng khi chạy sẽ gây `WrongMethodTypeException`.

### 2.1. Java không tự chèn chuyển đổi số khi dùng `invokeExact`

Trong Java method thông thường, một `int` có thể được widening sang `long` theo Java method invocation conversion; Java compiler biết chữ ký của method tĩnh. Nhưng `invokeExact` là signature-polymorphic, **không thực hiện Java method invocation conversions** để sửa call-site type thành handle type. Một literal `7` là `int`; literal `7L` là `long`. Vì vậy:

```java
long answer = (long) handleLong.invokeExact(7L);
```

Là đúng với handle có kiểu `(long)long`. Còn:

```java
long answer = (long) handleLong.invokeExact(7);
```

Yêu cầu kiểu `(int)long` và **không** tự biến `7` thành `7L` cho `invokeExact`. Thậm chí nếu con số đủ nhỏ và biểu diễn được bằng mọi kiểu, type descriptor vẫn sai.

### 2.2. Boxing/unboxing cũng không diễn ra tự động

Nếu handle cần primitive `int`:

```java
Integer boxed = Integer.valueOf(7);
int answer = (int) add.invokeExact(boxed, 5);
```

Biểu thức `boxed` có kiểu tĩnh `Integer`, không phải `int`. Tại call site, JVM không unbox thành `int` giúp `invokeExact`. Cách đúng là tạo primitive tường minh:

```java
int primitive = boxed.intValue();
int answer = (int) add.invokeExact(primitive, 5);
```

Cả hai đoạn là **mã minh họa**, không độc lập. Mục đích là phân biệt kiểu tĩnh của biểu thức với “giá trị trông giống số 7”.

### 2.3. Kiểu kết quả là một phần của hợp đồng

Điều dễ bỏ sót nhất: `invokeExact` quan tâm **cả return type tại call site**.

```java
// Với MethodHandle.type() == (int,int)int:
int x = (int) add.invokeExact(2, 3);  // Đúng.
long y = (long) add.invokeExact(2, 3); // Sai: return long.
add.invokeExact(2, 3);                // Sai: statement nhận void.
```

Nếu muốn bỏ qua kết quả mà vẫn gọi hàm C, phải nhận đúng kiểu rồi chủ động bỏ biến:

```java
int ignored = (int) add.invokeExact(2, 3);
// Không dùng ignored cho logic tiếp theo.
```

Hoặc tạo **adapter handle** có return type `void` bằng các combinators thích hợp nếu chủ đích của API là bỏ kết quả. Không được tưởng lời gọi chỉ vì là statement sẽ tự bỏ return. Ngược lại, với native function C trả `void`, cách gọi đúng thường chính là **statement** không cast.

## 3. Từ `FunctionDescriptor` đến `MethodHandle.type()`

FFM mô tả C types bằng `MemoryLayout`. Một `ValueLayout` có **Java carrier**; đó là kiểu mà method handle nhận/trả cho giá trị ấy. Một pointer được biểu diễn bằng `AddressLayout`, carrier `MemorySegment.class`.

Ví dụ (đối với Linux/x86-64):

| C prototype fragment | FFM layout | Java carrier | Kiểu cần ở `invokeExact` |
| --- | --- | --- | --- |
| `int` | canonical `"int"` | `int` | Literal `7` hoặc biến `int` |
| `long long` | canonical `"long long"` | `long` | `7L` hoặc biến `long` |
| `double` | canonical `"double"` | `double` | `2.5` hoặc biến `double` |
| `float` | canonical `"float"` | `float` | `2.5f` hoặc biến `float` |
| `void *` / `int *` | canonical `"void*"` | `MemorySegment` | `MemorySegment` còn hợp lệ |
| `size_t` (Linux/x64) | canonical `"size_t"` | `long` | `long`, nhưng kiểm tra từng ABI |
| C `void` return | `FunctionDescriptor.ofVoid(...)` | `void` | Lời gọi như một statement |

**Không hard-code “C long = Java long” trên mọi hệ điều hành.** LLP64 trên Windows/x64 có C `long` thường 4 byte; Linux/x64 LP64 thường 8 byte. `canonicalLayouts` và kết quả `handle.type()` là nguồn sự thật cho handle đang chạy, nhưng phải so với header và ABI của library đích.

### 3.1. Quan sát trực tiếp kiểu handle

```java
System.out.println(handle.type());

boolean matches = handle.type().equals(
    MethodType.methodType(int.class, int.class, int.class));
```

Đây là code trong method đã có `MethodHandle handle`, import `java.lang.invoke.MethodType`. Việc kiểm tra `equals` có thể đưa vào startup validation để **fail fast** nếu descriptor/carrier không phù hợp với call site đã viết.

`FunctionDescriptor.toMethodType()` cũng chuyển layout-carriers thành một `MethodType`. Với **bound downcall đơn giản, chỉ có scalar/pointer types, không có tham số linker đặc biệt**, `descriptor.toMethodType()` tương ứng `handle.type()`. Tuy nhiên không lấy đó làm quy tắc tuyệt đối cho mọi downcall: unbound handles và một số tính năng ABI có thêm tham số ẩn.

## 4. Ví dụ C11: bốn function prototypes rõ ràng

Để tránh phụ thuộc `libc`/symbol availability hoặc ABI giả định, ta tự biên dịch một shared library C trên Linux. File **`exact_ffi.c`**:

```c
/* exact_ffi.c: ISO C11, biên dịch thành libexactffi.so. */

/* C int -> Java int trên Linux/x86-64 thông dụng. */
int ffi_add(int a, int b) {
    return a + b;
}

/* C long long -> Java long trên Linux/x86-64. */
long long ffi_double_ll(long long value) {
    return value * 2;
}

/* C double -> Java double. */
double ffi_average(double left, double right) {
    return (left + right) / 2.0;
}

/* C void return; param đầu là int* (native address). */
void ffi_store_int(int *destination, int value) {
    if (destination != 0) {
        *destination = value;
    }
}
```

Đây là **file C đầy đủ**. C functions được export trên Linux với compiler flags thông thường; không có dấu hiệu `JNIEXPORT` vì đây là **FFM downcall**, không phải JNI native method đăng ký với JVM. Trên Windows, cần thiết lập export/calling convention theo compiler, không bê nguyên build command Linux.

Miền dữ liệu trong demo tránh signed integer overflow của C: `7 + 5` và `21 * 2` đều hợp lệ. FFM **không** tự chuyển lỗi native của mọi thư viện thành Java exceptions: với C code khác, bạn phải đọc contract về errno/status và ownership.

Các function prototypes tương ứng:

| C function | C signature | Java MethodHandle mong đợi |
| --- | --- | --- |
| `ffi_add` | `int(int,int)` | `(int,int)int` |
| `ffi_double_ll` | `long long(long long)` | `(long)long` |
| `ffi_average` | `double(double,double)` | `(double,double)double` |
| `ffi_store_int` | `void(int*,int)` | `(MemorySegment,int)void` |

Đặc biệt, kiểu `int*` trong C không trở thành Java `int[]` hoặc `long` khi gọi bằng FFM. Nó là một pointer tới bộ nhớ native hợp lệ, được biểu diễn bằng `MemorySegment`.

## 5. Ví dụ Java 22+ đầy đủ: đúng kiểu, sai kiểu và adapter rõ ràng

File **`ExactInvokeDemo.java`** dưới đây:

- Dùng canonical C layouts của chính ABI đang chạy, không đoán kiểu C.
- Nạp `libexactffi.so` với `SymbolLookup.libraryLookup(Path, Arena)`.
- Tạo **bound downcall handles** cho bốn function symbols.
- Kiểm tra `MethodType` trước khi gọi.
- Dùng `invokeExact` với các primitive types/return casts chính xác.
- Thử bốn **call sites sai kiểu** và bắt `WrongMethodTypeException`.
- Dùng `asType` để chủ động **widen return** từ `int` sang `long` khi cần.

### 5.1. `ExactInvokeDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.foreign.AddressLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.nio.file.Path;
import java.util.Map;

public final class ExactInvokeDemo {
    private ExactInvokeDemo() {}

    private static MemoryLayout require(
            Map<String, MemoryLayout> abi, String name) {

        MemoryLayout layout = abi.get(name);
        if (layout == null) {
            throw new IllegalStateException(
                "Missing C layout: " + name);
        }
        return layout;
    }

    private static MethodHandle downcall(
            Linker linker,
            SymbolLookup symbols,
            String symbolName,
            FunctionDescriptor signature) {

        MemorySegment address = symbols.find(symbolName).orElseThrow(
            () -> new IllegalStateException(
                "Missing C symbol: " + symbolName));

        return linker.downcallHandle(address, signature);
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        Map<String, MemoryLayout> abi =
            linker.canonicalLayouts();

        MemoryLayout cInt = require(abi, "int");
        MemoryLayout cLongLong = require(abi, "long long");
        MemoryLayout cDouble = require(abi, "double");
        MemoryLayout cPointer = require(abi, "void*");

        // Bộ ví dụ cố ý target Linux/x86-64.
        // Không âm thầm gọi native nếu carriers khác.
        if (!(cInt instanceof ValueLayout.OfInt)
                || !(cLongLong instanceof ValueLayout.OfLong)
                || !(cDouble instanceof ValueLayout.OfDouble)
                || !(cPointer instanceof AddressLayout)) {
            throw new IllegalStateException(
                "Unexpected C ABI for this example");
        }

        try (Arena arena = Arena.ofConfined()) {
            Path library =
                Path.of("libexactffi.so").toAbsolutePath();

            SymbolLookup symbols =
                SymbolLookup.libraryLookup(library, arena);

            FunctionDescriptor addSig = FunctionDescriptor.of(
                cInt, cInt, cInt);
            FunctionDescriptor doubleSig = FunctionDescriptor.of(
                cLongLong, cLongLong);
            FunctionDescriptor averageSig = FunctionDescriptor.of(
                cDouble, cDouble, cDouble);
            FunctionDescriptor storeSig = FunctionDescriptor.ofVoid(
                cPointer, cInt);

            MethodHandle add = downcall(
                linker, symbols, "ffi_add", addSig);
            MethodHandle twice = downcall(
                linker, symbols, "ffi_double_ll", doubleSig);
            MethodHandle average = downcall(
                linker, symbols, "ffi_average", averageSig);
            MethodHandle store = downcall(
                linker, symbols, "ffi_store_int", storeSig);

            boolean typesOk =
                add.type().equals(MethodType.methodType(
                    int.class, int.class, int.class))
                && twice.type().equals(MethodType.methodType(
                    long.class, long.class))
                && average.type().equals(MethodType.methodType(
                    double.class, double.class, double.class))
                && store.type().equals(MethodType.methodType(
                    void.class, MemorySegment.class, int.class));

            System.out.println("types-ok=" + typesOk);
            if (!typesOk) {
                throw new IllegalStateException(
                    "Unexpected downcall MethodType");
            }

            // Đúng: đối số int, kết quả int.
            int sum = (int) add.invokeExact(7, 5);
            System.out.println("add=" + sum);

            // Đúng: cả đối số lẫn kết quả là long.
            long doubled = (long) twice.invokeExact(21L);
            System.out.println("double-long-long=" + doubled);

            // Đúng: double + double -> double.
            double avg = (double)
                average.invokeExact(2.0, 3.0);
            System.out.println("average=" + avg);

            // Đúng: pointer có carrier MemorySegment.
            // Native function C trả void, gọi như statement.
            MemorySegment slot = arena.allocate(cInt);
            store.invokeExact(slot, 123);
            System.out.println(
                "stored=" + slot.get(ValueLayout.JAVA_INT, 0));

            // Sai 1: tham số call site là long,long.
            try {
                int value = (int) add.invokeExact(7L, 5L);
                System.out.println("unreachable=" + value);
            } catch (WrongMethodTypeException expected) {
                System.out.println(
                    "wrong-args=WrongMethodTypeException");
            }

            // Sai 2: return type call site là long.
            try {
                long value = (long) add.invokeExact(7, 5);
                System.out.println("unreachable=" + value);
            } catch (WrongMethodTypeException expected) {
                System.out.println(
                    "wrong-return=WrongMethodTypeException");
            }

            // Sai 3: statement tự yêu cầu return void.
            try {
                add.invokeExact(7, 5);
                System.out.println("unreachable");
            } catch (WrongMethodTypeException expected) {
                System.out.println(
                    "ignored-return=WrongMethodTypeException");
            }

            // Sai 4: Integer không được unbox tự động.
            Integer boxedA = Integer.valueOf(7);
            Integer boxedB = Integer.valueOf(5);
            try {
                int value = (int) add.invokeExact(
                    boxedA, boxedB);
                System.out.println("unreachable=" + value);
            } catch (WrongMethodTypeException expected) {
                System.out.println(
                    "boxed-args=WrongMethodTypeException");
            }

            // Có chủ đích: adapter widen int return -> long.
            MethodHandle addWithLongReturn = add.asType(
                MethodType.methodType(
                    long.class, int.class, int.class));

            long widened = (long)
                addWithLongReturn.invokeExact(7, 5);
            System.out.println("adapted-return=" + widened);
        }

        System.out.println("complete");
    }
}
```

**Tại sao sample có `throws Throwable`?** `MethodHandle.invokeExact` khai báo có thể ném `Throwable`; Java code phải catch hoặc khai báo throws phù hợp. Mã mẫu dùng `main(String[]) throws Throwable` cho gọn. Trong chương trình production, không nên xử lý mọi `Throwable` như lỗi input thông thường: cần phân biệt Java linkage/type errors với native library errors và lỗi nghiêm trọng.

**Tại sao `SymbolLookup.libraryLookup` nằm trong `try (Arena arena ...)`?** Symbol lookup và library lifetime gắn với arena được truyền vào. Giữ arena còn sống khi dùng handles. `Arena.ofConfined()` phù hợp vì tất cả calls trong demo thực hiện trên một thread; nếu chuyển handles/buffers sang nhiều thread, chọn scope và synchronization phù hợp với library.

**Tại sao dùng một `Path` tuyệt đối?** Chương trình mẫu build `libexactffi.so` vào working directory. `Path.of(...).toAbsolutePath()` giúp không phụ thuộc search path thư viện native của hệ điều hành khi gọi `libraryLookup(Path, Arena)`. Chạy ở thư mục chứa cả library và class file.

### 5.2. Chữ ký MethodType thực tế cần khớp

Đoạn kiểm tra ở đầu chương trình so sánh:

```text
add:      (int,int)int
twice:    (long)long
average:  (double,double)double
store:    (MemorySegment,int)void
```

Cụ thể `store.invokeExact(slot, 123);` đúng vì MethodHandle trả `void` và Java statement cũng yêu cầu `void`. Không thêm `(Object)` hay `(Void)` cast. Ngược lại, một method trả `int` mà bạn gọi như statement sẽ có call-site return `void` và nhận `WrongMethodTypeException`.

Biến `slot` có kiểu khai báo **`MemorySegment`**. Khi FFM mô tả C pointer bằng `AddressLayout`, nó cần một `MemorySegment` argument; nếu chỉ truyền raw `long address` dù 64-bit bằng kích thước pointer, call-site type không khớp.

### 5.3. Biên dịch và chạy trên Linux

Cần JDK 22+ và C compiler hỗ trợ C11. Đặt `exact_ffi.c` và `ExactInvokeDemo.java` trong cùng thư mục:

```bash
cc -std=c11 -O2 -Wall -Wextra -Wpedantic \
   -fPIC -shared exact_ffi.c -o libexactffi.so

javac ExactInvokeDemo.java

java --enable-native-access=ALL-UNNAMED ExactInvokeDemo
```

`--enable-native-access=ALL-UNNAMED` cấp quyền gọi các FFM restricted methods cho code chạy trên classpath/unnamed module. Nếu ứng dụng chạy trong named module, phải cấu hình native access cho đúng module thay vì mặc định toàn bộ ứng dụng có quyền.

**Stdout dự kiến chính xác trên Linux/x86-64 với hai file như trên:**

```text
types-ok=true
add=12
double-long-long=42
average=2.5
stored=123
wrong-args=WrongMethodTypeException
wrong-return=WrongMethodTypeException
ignored-return=WrongMethodTypeException
boxed-args=WrongMethodTypeException
adapted-return=12
complete
```

Bốn dòng `WrongMethodTypeException` được **chủ động tạo** để quan sát khác biệt chữ ký và đã được Java catch. Chúng không phải C crashes, không làm native functions được gọi với ABI sai. C code chỉ thực sự chạy ở những đường gọi có Java call-site type khớp.

Lưu ý: Đây là **stdout kỳ vọng được xác định từ mã**, không phải kết quả benchmark; thời gian thực tế và cách tải thư viện phụ thuộc JDK, dynamic linker và OS. Trên Windows/macOS cần tên thư viện, compiler flags, calling convention và quy tắc export phù hợp khác Linux.

## 6. Đọc từng lỗi để hiểu "chính xác" nghĩa là gì

### 6.1. Sai tham số: `int` vs `long`

Handle mong đợi `(int,int)int`. Bạn gọi:

```java
int value = (int) add.invokeExact(7L, 5L);
```

Java literal `7L` và `5L` là `long`. Call site yêu cầu `(long,long)int`. Mismatch được phát hiện ở tầng MethodHandle, không phải bằng cách C `int add_exact` cố đọc hai giá trị 64 bit. Không có phép narrowing ngầm.

Sửa:

```java
int value = (int) add.invokeExact(7, 5);
```

Hoặc nếu dữ liệu đầu vào là `long` từ một API khác, kiểm tra miền giá trị rồi chuyển **tường minh**:

```java
long raw = 7L;
int checked = Math.toIntExact(raw);
int value = (int) add.invokeExact(checked, 5);
```

`Math.toIntExact` ném `ArithmeticException` nếu raw vượt phạm vi `int`, thay vì âm thầm cắt 32 bit. Đây là một bước kiểm tra nghiệp vụ trước FFM downcall, **không phải** chuyển đổi do `invokeExact` thực hiện.

### 6.2. Sai kiểu trả về: `int` vs `long`

Handle trả `int`, nhưng:

```java
long value = (long) add.invokeExact(7, 5);
```

Call site yêu cầu `long`. Không tự widen dù việc widen `int → long` hoàn toàn có thể thực hiện trong Java bình thường. Phân biệt **cast bên ngoài lời gọi** và **cast trực tiếp trên kết quả của `invokeExact`**:

```java
int original = (int) add.invokeExact(7, 5);
long widened = original;             // Java widening bình thường.
```

Nếu muốn viết một biểu thức:

```java
long widened = (long) (int) add.invokeExact(7, 5);
```

Cast gần `invokeExact` nhất là `(int)` và yêu cầu Java call-site return `int`; sau đó cast bên ngoài chuyển Java `int` sang `long`. Để tránh đọc nhầm, dùng biến trung gian là cách rõ ràng nhất.

### 6.3. Bỏ qua return value không làm kiểu thành `void`

Trong Java, bạn có thể viết `someIntMethod();` như statement và bỏ giá trị trả về, vì compiler biết method tĩnh đó trả `int`. Nhưng với `invokeExact`, statement xây call-site return type là **`void`**. Khi handle trả `int`, type mismatch ngay.

Hai cách đúng:

```java
int ignored = (int) add.invokeExact(7, 5);

// Hoặc chủ động tạo handle có return type void:
MethodHandle onlySideEffect =
    MethodHandles.filterReturnValue(
        add,
        MethodHandles.empty(MethodType.methodType(
            void.class, int.class))); // ĐÂY LÀ VÍ DỤ SAI CÁCH GHÉP
```

**Không dùng ví dụ ghép combiner trên như code chạy**: nó là một cấu trúc cảnh báo vì filter phải có đúng parameter/return contract và cách dựng `empty` kiểu `(int)void` ở đây không tương ứng với mọi cách gọi mong muốn. Cách **đơn giản, chắc chắn** để bỏ return vẫn là nhận đúng kiểu rồi không sử dụng kết quả. Trong code library dùng nhiều kiểu `MethodHandle`, hãy kiểm tra `MethodHandles.dropArguments/filterReturnValue` theo Javadoc và test `handle.type()` sau khi compose.

### 6.4. Boxing và các reference types

`invokeExact` không tự unwrap `Integer` thành `int`, và cũng không tự upcast/downcast mọi reference types cho phù hợp handle.

```java
Integer boxed = Integer.valueOf(7);
int a = (int) add.invokeExact(boxed, 5); // Mismatch.
int b = (int) add.invokeExact(boxed.intValue(), 5); // Đúng.
```

Nếu một handle yêu cầu chính xác `MemorySegment` mà bạn lưu segment vào biến kiểu `Object`:

```java
Object obj = arena.allocate(4);
// store.invokeExact(obj, 123); // Call-site (Object,int)void: sai.
MemorySegment segment = (MemorySegment) obj;
store.invokeExact(segment, 123); // Nếu segment hợp lệ: đúng kiểu.
```

Đoạn là ví dụ khi `arena` và `store` đã có. **Object đang chứa MemorySegment ở runtime không đủ**; compiler dùng **kiểu tĩnh của biểu thức** tại call site. Cast tường minh sang `MemorySegment` giúp biểu thức mang đúng Java reference type.

### 6.5. `float`, `double` và số nguyên literal

Với C `double average(double,double)`, Java phải truyền `double`:

```java
double ok = (double) average.invokeExact(2.0, 3.0);

// Hai literal 2f và 3f là float: mismatch ở invokeExact.
// double bad = (double) average.invokeExact(2f, 3f);
```

Tương tự, C `float` thường tương ứng Java `float` và cần `2.0f`; dùng `2.0` sẽ yêu cầu `double`. Với primitive `boolean`/`byte`/`short`/`char`, không tự giả định numeric promotion của Java sẽ xuất hiện thay bạn khi gọi `invokeExact`.

### 6.6. MethodHandle có tham số thừa hoặc thiếu

Nếu C prototype có hai tham số mà descriptor của downcall handle cũng có hai, call site phải có đúng hai đối số. Không thể truyền thêm một đối số status hoặc quên một tham số rồi kỳ vọng FFM tự suy ra.

```java
// add.type() == (int,int)int
int ok = (int) add.invokeExact(7, 5);

// Sai arity:
// int wrong = (int) add.invokeExact(7);
```

Một cách lập trình cấu trúc hơn là dùng wrapper Java có chữ ký rõ ràng:

```java
static int addTwo(MethodHandle handle, int left, int right)
        throws Throwable {
    return (int) handle.invokeExact(left, right);
}
```

Đoạn này chỉ hợp lệ nếu handle bạn truyền thực sự có `(int,int)int`; wrapper không thay thế startup verification.

## 7. `invokeExact`, `invoke`, `invokeWithArguments` và `asType`

Cùng một `MethodHandle` có nhiều cách gọi, nhưng **không nên chọn cách permissive chỉ để che lỗi ABI**.

| API | Cơ chế | Khi phù hợp | Điều cần cẩn trọng |
| --- | --- | --- | --- |
| `invokeExact` | Yêu cầu call site == `handle.type()` tuyệt đối | Downcalls đã biết chính xác method type; hot path; review nghiêm | Phải đúng cả return type |
| `invoke` | Có thể thích ứng theo quy tắc `MethodHandle.asType(...)` | API Java tổng quát chủ động cho phép conversion | Có boxing/numeric conversions, không chữa descriptor C sai |
| `invokeWithArguments` | Nhận các đối số dạng objects, thích ứng động | Diagnostics/prototyping, dynamic dispatch | Boxing, allocations, lỗi bị phát hiện muộn, kém rõ kiểu |
| `asType(MethodType)` | Tạo adapter handle có kiểu mới | Chuyển đổi có chủ đích, kiểm soát ở một boundary | Phải biết conversion semantics và miền giá trị |
| `explicitCastArguments` | Chuyển kiểu theo casting rules rộng hơn | Bridge bắt buộc có contract rõ | Có thể narrowing ngoài ý muốn nếu không validate |

### 7.1. `invoke` khác `invokeExact` ở đâu?

Nếu handle có kiểu `(int,int)int`, lời gọi `invoke` với caller cần trả `long` có thể dùng conversion `int → long` theo adapter semantics:

```java
long widened = (long) add.invoke(7, 5);
```

Đó là **sự thích ứng của MethodHandle**, không phải C function đột ngột đổi return thành `long`. Nếu dùng `invokeExact` cho cùng call site, mismatch sẽ ném `WrongMethodTypeException`. Không nên dùng `invoke` một cách vô thức khi C signature chưa chắc chắn; nó chỉ che khác biệt kiểu Java, không xác thực cách C truyền dữ liệu.

### 7.2. `asType` khi muốn có contract mới

Trong chương trình chạy đầy đủ:

```java
MethodHandle addWithLongReturn = add.asType(
    MethodType.methodType(long.class, int.class, int.class));

long widened = (long)
    addWithLongReturn.invokeExact(7, 5);
```

Đoạn adapter này đổi **kiểu Java của handle từ `(int,int)int` sang `(int,int)long`** bằng conversion kết quả, trong khi native function vẫn nhận hai C `int` và trả C `int`. Đây là cách rõ ràng để tạo API wrapper trả Java `long` mà không khai báo sai native `FunctionDescriptor`.

`asType` có thể cho phép các conversion khác; không có nghĩa mọi chuyển đổi số đều bảo toàn dữ liệu. Khi có `long → int`, `double → int` hoặc unsigned bit pattern, cần kiểm tra phạm vi và policy trước khi chọn adapter. Với hot path, có thể tạo adapter một lần lúc khởi tạo, thay vì xây lại cho từng request.

### 7.3. Vì sao không lấy `invokeWithArguments` làm mặc định?

`invokeWithArguments(Object... args)` linh hoạt, nhưng làm yếu đi khả năng đọc code: người duy trì không thấy rõ primitive types hay expected return type từ chính call site, và các conversions/boxing gây thêm công việc. Nó có chỗ đứng trong framework runtime discovery hoặc API dành cho người dùng động, nhưng với một số hàm C tĩnh, `invokeExact` thường giúp **fail fast** về sai Java MethodType và dễ code review hơn.

Cả `invoke` và `invokeWithArguments` đều không thể biến một pointer đã free thành an toàn, không thể suy đúng native prototype từ symbol name và không sửa sai calling convention.

## 8. `void` và pointer: phải tách type-safety khỏi memory-safety

Trong ví dụ, C có:

```c
void ffi_store_int(int *destination, int value);
```

Java descriptor:

```java
FunctionDescriptor storeSig = FunctionDescriptor.ofVoid(
    cPointer, cInt);
```

Kết quả là handle nhận một `MemorySegment`, một `int` và trả **`void`**:

```java
MemorySegment slot = arena.allocate(cInt);
store.invokeExact(slot, 123);
```

Điều này đúng về **Java type**. Nhưng nếu truyền một segment có address không hợp lệ, byteSize không đủ hoặc arena đã close, có thể nhận FFM safety exception hoặc lỗi native nghiêm trọng tùy sai phạm. Chữ ký đúng **không chứng minh pointer chỉ tới bộ nhớ có thể ghi**.

### 8.1. Không chuyển pointer thành `long` chỉ vì 64-bit

Một C pointer đi qua `AddressLayout`, Java carrier `MemorySegment`. Không viết:

```java
// Sai: giả định C int* có thể truyền như Java long.
// store.invokeExact(slot.address(), 123);
```

Nếu `slot.address()` là số `long`, call site trở thành `(long,int)void`, khác `(MemorySegment,int)void`. Thậm chí nếu chuyển một integer sang segment theo API cho phép, vẫn phải có contract về nguồn gốc pointer, ownership, alignment và lifetime.

### 8.2. `Arena` quản lý lifetime của vùng nhớ

`Arena.ofConfined()` tạo scope chỉ accessible ở owner thread và close được. `arena.allocate(cInt)` cấp phát off-heap theo alignment của layout, vùng đó còn hợp lệ khi arena còn sống. `store.invokeExact(slot,123)` kết thúc trước khi `try-with-resources` close arena.

Trong code async, C library có thể **giữ pointer để dùng sau khi function return**. Nếu Java đóng arena ngay sau downcall, pointer trở nên dangling khi C callback đến muộn. Đây là lỗi memory-lifetime nghiêm trọng dù `invokeExact` đã khớp type. Cần một owner giữ allocation sống tới native completion/cancel thực sự.

### 8.3. Read-only và heap segments

Khi address layout trông đợi một pointer native, FFM downcall thông thường không nhận heap segment như một native pointer (trừ option chuyên biệt có điều kiện), vì Java heap không có address native ổn định theo cách API C cần. Dùng `Arena.allocate` hoặc đúng native segment khi C function yêu cầu pointer.

Nếu C function sẽ ghi dữ liệu, segment/bộ nhớ phải writable theo hợp đồng thực sự. `MemorySegment.asReadOnly()` không phải cơ chế thay đổi C pointer thành `const int*` được C tự tuân thủ. Java metadata không bảo vệ khỏi mọi thao tác tùy ý trong thư viện C nhận raw address; trust boundary vẫn là native code.

## 9. Vì sao `FunctionDescriptor.toMethodType()` không luôn bằng downcall handle type?

Đối với bound handle có scalar/pointer parameters và return, không có linker options đặc biệt:

```java
FunctionDescriptor fd =
    FunctionDescriptor.of(cInt, cInt, cInt);

MethodHandle bound = linker.downcallHandle(
    symbols.find("ffi_add").orElseThrow(), fd);

System.out.println(fd.toMethodType().equals(bound.type()));
// true trong ví dụ này
```

Đây là đoạn trong method đã có `linker`, `symbols` và `cInt`.

Nhưng FFM có các dạng handle khác. **Phải đọc `handle.type()` cuối cùng**, nhất là khi xây generic wrapper.

### 9.1. Bound handle so với unbound handle

Hai overload:

```java
MethodHandle bound =
    linker.downcallHandle(address, descriptor);

MethodHandle unbound =
    linker.downcallHandle(descriptor);
```

Đoạn này giả định `address` và `descriptor` hợp lệ.

- **Bound:** địa chỉ native function đã được gắn lúc tạo handle; với chữ ký đơn giản, call site chỉ truyền các C arguments.
- **Unbound:** handle **nhận thêm một `MemorySegment` ở đầu**, chỉ tới native function address; bạn có thể dùng một handle cho nhiều symbol cùng ABI signature.

Nếu `descriptor` mô tả `int(int,int)`:

```text
Bound handle:     (int,int)int
Unbound handle:   (MemorySegment,int,int)int
```

Với unbound handle, gọi đúng kiểu là:

```java
int result = (int) unbound.invokeExact(
    functionAddress, 7, 5);
```

Không thêm address argument cho bound handle. Không nhầm thêm `MemorySegment` ở đây với pointer argument đã được C function khai báo; đây là **địa chỉ của function symbol**, không phải địa chỉ data buffer.

### 9.2. Struct/union trả về bằng giá trị

Nếu native function trả C `struct`/`union` by value và `FunctionDescriptor` dùng group layout làm return, downcall handle cần một tham số **`SegmentAllocator`** bổ sung để Java cấp chỗ chứa kết quả theo ABI. Thường truyền một `Arena` phù hợp, rồi nhận `MemorySegment` chứa struct result. Với unbound handle còn có function address argument ở đầu; thứ tự cần xác nhận theo `handle.type()` cụ thể.

Ví dụ method type có thể có dạng:

```text
Bound, struct by value:   (SegmentAllocator,...C args...)MemorySegment
Unbound, struct by value: (MemorySegment,SegmentAllocator,...C args...)MemorySegment
```

Đây là **sơ đồ dạng chữ ký**, không phải mô tả một ABI cụ thể hay một chương trình. Với aggregate thực tế, phải kiểm tra layout/padding thật từ C header và `sizeof/offsetof`. Không coi struct return là pointer return rồi bỏ allocator.

### 9.3. Linker options có thể đổi type

Một số options như bắt call state (ví dụ `errno` hoặc lỗi hệ điều hành) có thể bổ sung yêu cầu về vùng nhớ phụ trong call site, tùy JDK/linker API. Không tự giả định rằng `FunctionDescriptor.toMethodType()` luôn phản ánh đầy đủ các tham số được linker thêm. Hãy tạo handle, gọi `type()`, kiểm tra prefix/arity/return rồi mới viết `invokeExact`.

Quy tắc: **MethodHandle là sự thật về Java call-site type; C header/prototype là sự thật về native ABI. Cần cả hai.**

## 10. `size_t`, C `long` và việc chọn kiểu kết quả theo ABI

Đây là một trường hợp đặc biệt quan trọng với `invokeExact`. C:

```c
size_t strlen(const char *s);
```

Trên nhiều ABI 64-bit, `size_t` dùng Java `long`; trên ABI 32-bit nó có thể dùng Java `int`. Nếu khai báo handle theo đúng canonical layout, **return type tại call site cũng phải thay đổi theo ABI**.

Mã **minh họa trong một Java method** đã có `Linker linker`, `Arena arena` và đã cấp quyền native access:

```java
Map<String, MemoryLayout> abi =
    linker.canonicalLayouts();

ValueLayout sizeT =
    (ValueLayout) abi.get("size_t");
MemoryLayout ptr = abi.get("void*");

MethodHandle strlen = linker.downcallHandle(
    linker.defaultLookup().find("strlen").orElseThrow(),
    FunctionDescriptor.of(sizeT, ptr));

MemorySegment cText = arena.allocateFrom("Hello");

if (sizeT.carrier() == long.class) {
    long n = (long) strlen.invokeExact(cText);
    System.out.println(Long.toUnsignedString(n));
} else if (sizeT.carrier() == int.class) {
    int n = (int) strlen.invokeExact(cText);
    System.out.println(Integer.toUnsignedLong(n));
} else {
    throw new IllegalStateException("Unsupported size_t");
}
```

Tất cả các call sites ở hai nhánh đều hợp lệ về **Java compilation**; nhánh được chạy theo carrier hiện tại mới khớp actual handle. Nếu cần một wrapper portable hơn, chuẩn hóa kết quả sau khi nhận đúng kiểu; không sửa function descriptor sai để “cho vừa” Java source.

Mã trên dùng `linker.defaultLookup()` nên cần nền tảng mà default lookup expose `strlen`; trên Linux/x64 là trường hợp phổ biến, không phải bảo đảm mọi JVM/OS. Mã chính của bài dùng library C tự tạo để stdout luôn xác định.

### 10.1. Signedness không được `invokeExact` giải quyết

C `size_t` là unsigned. Nếu Java carrier là `int` và native trả bit pattern `0xFFFFFFFF`, giá trị Java tương ứng có thể là `-1`. `Integer.toUnsignedLong` chuyển cách **diễn giải** bit pattern thành `4294967295`; nó không thay đổi ABI.

Với carrier `long` và unsigned 64-bit, dùng `Long.toUnsignedString` hoặc comparison unsigned phù hợp, không cho rằng mọi giá trị C `size_t` đều là Java signed long không âm.

Tương tự, C `long` trên Linux/x64 thường có carrier `long.class`, nhưng trên Windows/x64 thường là `int.class`. Việc `invokeExact` báo `WrongMethodTypeException` vì Java code hard-code `long` chỉ là triệu chứng; giải pháp bắt đầu từ đọc ABI/canonical layout và C header, không ép `asType` để che lỗi.

## 11. Variadic functions và default argument promotions

Nếu hàm C dùng `...`, ví dụ:

```c
int printf(const char *format, ...);
```

C có **default argument promotions**: ví dụ C `float` trong variadic phần thường được promote thành `double`, integer types nhỏ thường promote thành `int` hoặc `unsigned int` tùy miền.

FFM linker cần **descriptor cho chuyên biệt hóa có danh sách tham số cụ thể**, cùng option `Linker.Option.firstVariadicArg(index)`. Nó không tự promote sai kiểu bạn đưa vào một lời gọi `invokeExact`.

Ví dụ descriptor cho `printf("%d", 42)` trên Linux/x64:

```java
MethodHandle printf = linker.downcallHandle(
    linker.defaultLookup().find("printf").orElseThrow(),
    FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS,
        ValueLayout.JAVA_INT),
    Linker.Option.firstVariadicArg(1));

MemorySegment format = arena.allocateFrom("%d");
int count = (int) printf.invokeExact(format, 42);
```

Đây là **đoạn minh họa trong một method**, chưa phải file độc lập. Nếu chạy, `printf` sẽ in số `42` bằng C stdout; giá trị trả `count` biểu diễn số ký tự được in theo contract của C. Chỉ dùng format string do ứng dụng kiểm soát, không đưa chuỗi format tùy ý từ người dùng vào `printf`. Nếu chuyên biệt hóa variadic `float`, mô tả **promoted C `double`** và Java call-site `double` theo descriptor.

**Không** chỉ nhìn `ValueLayout.JAVA_FLOAT` rồi truyền `2.0f` cho C vararg; đúng `invokeExact` về kiểu Java của một descriptor sai vẫn không đồng nghĩa C varargs ABI đúng.

## 12. Phân biệt lỗi `WrongMethodTypeException` với lỗi native thực sự

Một số lỗi có thông điệp tương tự nhưng bản chất khác nhau:

| Tình huống | Lớp lỗi/biểu hiện | Nguồn gốc |
| --- | --- | --- |
| Java gọi `invokeExact(7L)` cho `(int)int` | `WrongMethodTypeException` | Java MethodHandle call site không khớp |
| Return cast `(long)` khi handle trả `int` | `WrongMethodTypeException` | Expected return type sai |
| Gọi `invokeExact` như statement nhưng handle trả `int` | `WrongMethodTypeException` | Call-site yêu cầu `void` |
| MethodHandle cần `MemorySegment`, truyền `Object` | `WrongMethodTypeException` | Kiểu tĩnh của biến khác |
| Library không tìm được symbol | `NoSuchElementException` từ `orElseThrow()` hoặc lỗi do ứng dụng tạo | Lookup/config/library |
| Dùng FFM restricted API khi chưa bật quyền | Có thể nhận `IllegalCallerException`, tùy JDK | Native-access policy |
| Segment đã đóng | `IllegalStateException`/scope error | Lifetime FFM |
| Confined segment sai thread | `WrongThreadException` | Thread confinement |
| Truyền heap segment như native pointer khi không được phép | Có thể `IllegalArgumentException` | Memory safety contract |
| Native function declaration sai arity/ABI | Có thể sai dữ liệu, crash JVM | **Sai FunctionDescriptor với binary C** |
| C function trả status báo lỗi, không ném Java | Giá trị C bình thường về mặt MethodHandle | Ứng dụng phải diễn giải native error code |
| C function block vô hạn hoặc deadlock | Call không return | Native dependency, không phải type mismatch |

`WrongMethodTypeException` là dấu hiệu tốt rằng JVM chặn một call **trước khi vào C**. Tuy nhiên, nó không đồng nghĩa bạn đang sử dụng FFM một cách an toàn ở các đường khác. Cần kiểm tra C function prototypes, integer widths, pointers, valid memory, alignment, module native access, error codes và thread-safety riêng.

### 12.1. Vì sao không nên “bắt và bỏ qua” mọi mismatch?

Nếu code production liên tục gây `WrongMethodTypeException`, điều đó thể hiện một lỗi thiết kế adapter hoặc source code. Không nên catch rồi trả giá trị mặc định giả như dữ liệu C đã được xử lý. Hãy fail fast ở startup bằng `handle.type()` và sửa call site/descriptor, thay vì cho request bị lỗi lặp lại ở thời điểm chạy.

Các exceptions khác như `IllegalStateException` của segment closed cũng thường báo contract vi phạm. Tránh catch broad `Throwable` và retry native call tùy tiện; một lời gọi xuống C có side effects có thể đã chạy trước khi lỗi được ghi nhận ở tầng khác.

## 13. Hiệu năng: type exact không đồng nghĩa native call miễn phí

`invokeExact` có lợi thế là call site có kiểu rõ, có thể giúp JVM tối ưu adapter path trong điều kiện phù hợp. Nhưng tổng chi phí còn gồm FFM transition, ABI marshalling, native execution, pointer validation, memory copying/ownership, CPU caches và JNI/VM interactions khác.

Không nên suy rằng “`invokeExact` luôn nhanh hơn `invoke` một mức X%” khi chưa benchmark trên đúng runtime/CPU/C library. JIT có thể tối ưu các adapter tĩnh, đặc biệt khi handle là hằng hoặc được cache. Với các hàm C rất ngắn, chi phí đi qua boundary có thể là tỷ lệ đáng kể so với body.

Thực hành:

- Tạo `Linker`/lookup/`MethodHandle` **một lần** khi khởi tạo component, không lookup native symbol ở mỗi request nếu không cần.
- Cache handle đã xác minh type, bảo đảm library còn loaded/lifetime phù hợp.
- Dùng `invokeExact` trên đường hot khi biết rõ method type; nếu cần adapter, xây `asType` **một lần**.
- Tránh boxing và `Object...` trên hot path nếu không cần dynamic dispatch.
- Giữ bytes/pointers sống đến khi downcall kết thúc; không đóng arena quá sớm.
- Đo throughput, latency p95/p99, allocations, CPU và native library behavior theo workload thật.
- Không chọn workaround thay `FunctionDescriptor` để đổi carrier rồi nghĩ đó là một tối ưu; độ đúng ABI phải đi trước.

### 13.1. Khả năng dùng cùng một handle ở nhiều thread

`MethodHandle` là immutable và có thể chia sẻ về mặt Java, nhưng **không có nghĩa mọi argument và native library đều thread-safe**. Nếu handle gọi C function sử dụng global state hoặc một pointer từ confined arena, thread khác có thể race hoặc bị chặn bởi scope checks. FFM type-safe boundary và concurrency safety là hai hợp đồng riêng.

Không truyền `MemorySegment` từ `Arena.ofConfined()` sang worker thread khác rồi mong `invokeExact` tự chuyển thành shared memory. Dùng `Arena.ofShared()` khi thật sự có multi-thread access và có synchronization phù hợp, hoặc sử dụng ownership rõ ràng cho từng request.

## 14. Checklist debug và kiểm thử cần có

### 14.1. Kiểm thử đúng kiểu và kết quả

1. `add.type()` bằng `(int,int)int`; gọi với `(int) invokeExact(7,5)` trả 12.
2. `twice.type()` bằng `(long)long`; gọi `(long) invokeExact(21L)` trả 42.
3. `average.type()` bằng `(double,double)double`; gọi `(double) invokeExact(2.0,3.0)` trả 2.5.
4. `store.type()` bằng `(MemorySegment,int)void`; ghi vào native slot rồi đọc lại 123.
5. `invokeExact` với `long,long` cho handle `int,int` phải ném `WrongMethodTypeException`.
6. Return `long` ở call site khi handle trả `int` phải ném mismatch.
7. Gọi handle trả `int` như statement phải ném mismatch vì expected `void`.
8. Đối số `Integer` phải ném mismatch nếu handle đòi primitive `int`.
9. Adapter `asType((int,int)long)` phải nhận đúng `long` kết quả và không đổi C prototype.
10. Method handles được tạo từ đúng `SymbolLookup` và descriptor trước khi gọi.
11. Tắt native-access permissions phải gây lỗi policy phù hợp, không tự bypass bằng reflection.
12. Gọi với buffer expired/sai thread phải bị chặn theo FFM scope contract, không coi như lỗi kiểu MethodHandle.
13. Không bao giờ thử descriptor C sai nguy hiểm chỉ để đo JVM có crash không; dùng review/header/compiler probes.

### 14.2. Các câu hỏi kiểm tra code review

- Native C header chính xác của symbol là gì? C API có macro/typedef/calling-convention đặc biệt không?
- Layout Java đã đối chiếu canonical C types theo đúng ABI đang chạy chưa?
- `FunctionDescriptor.of(...)` có đúng số tham số, đúng thứ tự, đúng return layout không?
- Downcall là **bound** hay **unbound**? Có thêm địa chỉ hàm ở đầu không?
- Hàm trả `struct` by value có yêu cầu `SegmentAllocator` ở call site không?
- Linker options có thêm capture state hoặc variadic specialization nào cần xét không?
- `handle.type()` đã được kiểm tra ngay sau khi tạo chưa?
- `invokeExact` có đúng kiểu **tĩnh** của tất cả arguments không?
- Cast kết quả gần lời gọi nhất có đúng kiểu return của handle không?
- Nếu function trả non-void, có đang vô tình gọi `invokeExact` như statement không?
- Nếu function trả `void`, có đang cố nhận một `Object` hoặc `Void` không?
- Có boxing/implicit widening/ngữ cảnh `Object` làm đổi call-site descriptor không?
- Pointer argument là `MemorySegment`, arena còn sống, đúng thread và memory ownership chưa?
- Với C `size_t`/`long`, có hard-code Java `long` không phụ thuộc ABI không?
- Có kiểm thử stdout, native side effects, return status, timeout và resource cleanup không?

### 14.3. Quy trình xử lý `WrongMethodTypeException`

```text
Downcall MethodHandle ném WrongMethodTypeException
       |
       v
In ra/log handle.type()
       |
       v
Xác định call-site symbolic type:
    - từng argument expression type
    - expected return type
    - số lượng và thứ tự
       |
       v
So với handle.type() có giống hệt?
       |
       +--> Không: sửa call-site/cast/argument types,
       |           hoặc tạo adapter asType có chủ đích.
       |
       +--> Có: kiểm tra code path/handle thực đang chạy,
                   wrapper và linker options.
       |
       v
Xác minh riêng FunctionDescriptor với C header/ABI.
       |
       v
Kiểm thử return, side effects, lifetime và lỗi native.
```

In `handle.type()` rất hữu ích nhưng không thay thế kiểm tra **compiler-generated call-site descriptor**. Nếu nghi ngờ kiểu tĩnh bị thay do generic wrapper hay compiler context, dùng `javap -c -v` để xem bytecode và symbolic descriptor khi debug; trong code production bình thường, các cast và biến local tường minh là cách dễ đọc hơn.

## 15. Kết luận và tài liệu tham khảo

**Quy tắc quan trọng:** khi một FFM downcall handle có kiểu `(int,int)int`, gọi nó bằng `(int) handle.invokeExact(7,5)`. Không truyền `7L`, không cố nhận `long`, không gọi như statement, không đưa `Integer` rồi trông chờ tự unbox. Với C `void` function, statement `invokeExact(...)` lại là đúng; với C pointer, dùng `MemorySegment` đúng scope. Khi thật sự muốn API Java khác kiểu native, tạo adapter `asType` có chủ đích **sau khi** đã mô tả C ABI đúng.

Một câu dễ nhớ: **`FunctionDescriptor` phải đúng với C; `invokeExact` phải đúng với `MethodHandle.type()`.** Sai tầng thứ nhất có thể crash; sai tầng thứ hai thường được JVM chặn bằng `WrongMethodTypeException`.

### Tài liệu chính thức

- [Java SE 22 — MethodHandle: invokeExact, call-site descriptor và WrongMethodTypeException](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 22 — WrongMethodTypeException](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html)
- [Java SE 22 — MethodType](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/invoke/MethodType.html)
- [Java SE 22 — FFM Linker: downcallHandle, canonicalLayouts, bound/unbound handles](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Java SE 22 — FunctionDescriptor và toMethodType](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [Java SE 22 — SymbolLookup: libraryLookup, lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Java SE 22 — ValueLayout và Java carriers](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454)
