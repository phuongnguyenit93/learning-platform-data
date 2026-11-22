# Tạo upcallStub với FunctionDescriptor và Arena phù hợp

> **Ngữ cảnh:** Java Advance → Native Interoperability → Gọi lại bằng FFM. Bài học hướng dẫn sử dụng Foreign Function & Memory API để chuyển **một Java `MethodHandle` thành native function pointer** bằng `Linker.upcallStub(target, descriptor, arena)`, đối chiếu chữ ký bằng `FunctionDescriptor`, và chọn `Arena` sao cho function pointer sống đủ lâu nhưng được giải phóng đúng lúc. Mã chạy trên **JDK 22+** (FFM chính thức từ JEP 454); ví dụ `qsort` dùng C ABI của hệ điều hành 64-bit với `size_t` 8 byte.

## 1. Upcall là gì và tại sao cần một native function pointer?

Khi Java gọi hàm C/C++ qua FFM, đó là một **downcall**. Ngược lại, thư viện native có thể cần gọi lại logic viết bằng Java qua **callback**, ví dụ hàm so sánh `qsort`, listener từ SDK, API lập trình sự kiện hoặc thư viện xử lý dữ liệu:

```c
// Khai báo C chuẩn; không phải chương trình độc lập.
void qsort(void *base, size_t count, size_t elementSize,
           int (*compare)(const void *left, const void *right));
```

Đối số `compare` là một **con trỏ hàm C**, không phải Java `Comparator`, lambda hoặc object thông thường. Native code sẽ lưu hoặc gọi địa chỉ này theo C ABI.

FFM cung cấp chuỗi chuyển đổi:

```text
Java method / lambda-bound state
           |
           | MethodHandles.lookup().findStatic/findVirtual
           v
MethodHandle  (chữ ký Java / MethodType)
           |
           | FunctionDescriptor (chữ ký native / C ABI)
           | Arena (lifetime của trampoline/code stub)
           v
Linker.upcallStub(target, descriptor, arena)
           |
           v
MemorySegment stub (địa chỉ function pointer, size=0)
           |
           | truyền dưới dạng ADDRESS vào native function
           v
Native C/C++ invokes function pointer
           |
           v
FFM runtime -> Java MethodHandle -> trả kết quả về native
```

**Ba yếu tố bắt buộc** để một upcall được tạo và dùng đúng:

1. **`target` — MethodHandle:** đại diện một Java method có **kiểu tham số và kiểu trả về** khớp với carrier types suy ra từ descriptor.
2. **`function` — FunctionDescriptor:** mô tả **C function-pointer signature** theo ABI của platform, không chỉ kiểu Java nhìn thấy trên source.
3. **`arena` — lifetime owner:** giữ native stub/code pointer còn sống trong toàn bộ khoảng thời gian mã C có thể gọi nó.

Nếu chỉ đúng hai trong ba yếu tố, ứng dụng vẫn có thể gặp lỗi từ runtime, crash JVM hoặc native use-after-free.

## 2. Phân biệt MethodHandle, FunctionDescriptor, MemorySegment và Arena

| Đối tượng | Công dụng | Ví dụ với comparator `int (*)(const int*, const int*)` |
|---|---|---|
| `MethodHandle` | Đích gọi Java, biểu diễn bằng `MethodType` | `(MemorySegment, MemorySegment)int` |
| `FunctionDescriptor` | Chữ ký C ABI (return layout, argument layouts) | `of(JAVA_INT, ADDRESS, ADDRESS)` với target layouts cho hai pointer |
| `Linker.nativeLinker()` | Liên kết ABI hiện tại, tạo downcall và upcall | Native linker của Linux/x64, Windows/x64, v.v. |
| `Linker.upcallStub(...)` | Tạo native trampoline để native gọi Java | Trả `MemorySegment` có địa chỉ function pointer |
| `Arena` | Quản lý lifetime của stub | `Arena.ofConfined()` cho callback chỉ dùng trong synchronous downcall |
| `MemorySegment` stub | **Function pointer**, không phải mảng dữ liệu Java | Truyền như đối số `ValueLayout.ADDRESS` |
| `SymbolLookup` | Tìm tên native function trong thư viện | `defaultLookup().findOrThrow("qsort")` |

Dễ nhầm nhất là **hai loại MemorySegment**:

- `arena.allocateFrom(JAVA_INT, ...)` tạo segment **chứa các số nguyên** cần sắp xếp.
- `linker.upcallStub(...)` tạo segment **chỉ mang địa chỉ native callback stub**; `stub.byteSize()==0`. Không gọi `stub.get(JAVA_INT,0)` để “đọc callback”. Đưa `stub` vào một đối số C có kiểu **function pointer**.

Hai segment có thể nằm trong cùng Arena để quản lý lifetime gọn hơn, nhưng chúng là hai loại tài nguyên có ý nghĩa và cách dùng khác nhau.

## 3. Định nghĩa descriptor từ chữ ký C, không đoán từ Java

Ví dụ C comparator:

```c
int compare(const int *a, const int *b);
```

Theo ABI ví dụ, `int` là số nguyên 32-bit và hai pointer trỏ tới mỗi giá trị `int`. Descriptor FFM tương ứng:

```java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.ValueLayout;

FunctionDescriptor comparatorDescriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT),
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT)
);
```

Đây là **đoạn minh họa**, đặt trong method/static initializer. Ý nghĩa thứ tự:

- Tham số đầu tiên của `FunctionDescriptor.of(returnLayout, argLayouts...)` là **layout của giá trị trả về**. `JAVA_INT` mô tả `int` của comparator.
- Hai tham số tiếp theo là **pointer arguments**, mỗi tham số có carrier type Java là `MemorySegment`.
- `ADDRESS.withTargetLayout(JAVA_INT)` khai báo **kiểu dữ liệu ở đích con trỏ**, cho phép FFM tạo view có size của một `int` để callback đọc tại offset 0.
- Không viết `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT)`: hai tham số C là `const int*`, không phải hai giá trị `int`.
- Không hiểu `withTargetLayout` là một thao tác copy hoặc allocate: nó chỉ mô tả view/độ dài mà FFM áp dụng cho pointer argument.

Trong Java, callback sẽ có chữ ký:

```java
// Trích đoạn định nghĩa hàm Java; không phải chương trình đầy đủ.
static int compare(MemorySegment a, MemorySegment b) {
    int x = a.get(ValueLayout.JAVA_INT, 0);
    int y = b.get(ValueLayout.JAVA_INT, 0);
    return Integer.compare(x, y);
}
```

**Đừng dùng `return x - y`** để so sánh hai `int`, vì trừ có thể tràn số. `Integer.compare(x,y)` trả âm/0/dương đúng hợp đồng comparator C.

### `ofVoid` và callback không có giá trị trả về

Với C prototype:

```c
typedef void (*event_callback)(int value, void *context);
```

Descriptor dùng `FunctionDescriptor.ofVoid(JAVA_INT, ADDRESS)`. Java target nhận `(int, MemorySegment)void`. Nếu một callback C trả `void`, không dùng `FunctionDescriptor.of(JAVA_INT,...)` chỉ vì bạn muốn Java trả status; **native ABI phải được mô tả chính xác**.

## 4. Ghép đúng MethodType: carrier Java phải khớp descriptor

Đây là ví dụ đúng khi Java comparator là static method:

```java
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT),
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT)
);

MethodHandle target = MethodHandles.lookup().findStatic(
        CallbackDemo.class,
        "compare",
        descriptor.toMethodType()
);
```

Đoạn code này chỉ minh họa cách lookup; giả định `CallbackDemo.compare` có chữ ký `(MemorySegment, MemorySegment)int`, cùng imports từ `java.lang.invoke` và `java.lang.foreign`.

`descriptor.toMethodType()` chuyển native layouts thành Java carrier types:

| C/FFM layout | Java MethodHandle carrier |
|---|---|
| `JAVA_INT` | `int.class` |
| `JAVA_LONG` | `long.class` |
| `JAVA_DOUBLE` | `double.class` |
| `ADDRESS` | `MemorySegment.class` |
| `FunctionDescriptor.ofVoid(...)` | `void.class` cho return type |

Cách viết tương đương:

```java
MethodType.methodType(
        int.class, MemorySegment.class, MemorySegment.class
)
```

Trong thực tế, hãy dùng `descriptor.toMethodType()` để tránh lỗi quên tham số. Nếu callback là **instance method**, `findVirtual` tạo handle có receiver ở đầu; phải **bind receiver** bằng `bindTo(instance)`, hoặc dùng `MethodHandles.insertArguments` để đạt đúng MethodType mà descriptor đòi.

Nếu Java method nhận `long` nhưng descriptor là `JAVA_INT`, hoặc Java target trả `void` trong khi descriptor trả `JAVA_INT`, `upcallStub` thường ném `IllegalArgumentException` khi kiểu không tương thích. Không sửa bằng cách cast pointer hay ép số bừa: đọc lại C prototype và cách ánh xạ C type theo ABI thật.

**`FunctionDescriptor` không biến Java object thành native C object.** Nếu C callback nhận `void *userData`, đây là native pointer (được biểu diễn `MemorySegment`), không phải một `Object` Java tùy ý. Muốn lưu Java state, đơn giản nhất là **bind instance vào MethodHandle** rồi giữ ownership/lifetime của state, thay vì cố cast Java object reference thành `void*`.

## 5. Ví dụ hoàn chỉnh chạy được: qsort gọi lại Java comparator

Ví dụ này đặc biệt phù hợp để kiểm tra `upcallStub` vì `qsort` của C standard library gọi callback **đồng bộ**, trước khi `qsort` trả về; do đó **`Arena.ofConfined()`** là lựa chọn rõ ràng khi mọi invocation nằm trên thread đang thực hiện downcall.

**Tệp `QsortUpcallDemo.java`, JDK 22+ trên ABI có `int` 32-bit và `size_t` 64-bit (ví dụ Linux x86_64):**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;

import static java.lang.foreign.ValueLayout.*;

public final class QsortUpcallDemo {
    static final class CompareState {
        final AtomicReference<Throwable> failure =
                new AtomicReference<>();

        int compare(MemorySegment left, MemorySegment right) {
            try {
                int a = left.get(JAVA_INT, 0);
                int b = right.get(JAVA_INT, 0);
                return Integer.compare(a, b);
            } catch (Throwable error) {
                // KHÔNG để Throwable vượt ra native callback.
                failure.compareAndSet(null, error);
                return 0; // fallback trong lượt gọi bị lỗi.
            }
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // int compare(const int*, const int*)
        FunctionDescriptor compareDescriptor =
                FunctionDescriptor.of(
                        JAVA_INT,
                        ADDRESS.withTargetLayout(JAVA_INT),
                        ADDRESS.withTargetLayout(JAVA_INT)
                );

        CompareState state = new CompareState();
        MethodHandle compareHandle = MethodHandles.lookup()
                .findVirtual(CompareState.class, "compare",
                        compareDescriptor.toMethodType())
                .bindTo(state);

        // void qsort(void*, size_t, size_t, compare_fn)
        MethodHandle qsort = linker.downcallHandle(
                linker.defaultLookup().findOrThrow("qsort"),
                FunctionDescriptor.ofVoid(
                        ADDRESS, JAVA_LONG, JAVA_LONG, ADDRESS)
        );

        MemorySegment callbackPointer;

        try (Arena arena = Arena.ofConfined()) {
            callbackPointer = linker.upcallStub(
                    compareHandle, compareDescriptor, arena);

            // Mảng C int[6] trong off-heap memory.
            MemorySegment data = arena.allocateFrom(
                    JAVA_INT, 9, 4, 7, 1, 3, 2);

            // invokeExact đúng chữ ký handle:
            // (MemorySegment, long, long, MemorySegment)void.
            qsort.invokeExact(data, 6L,
                    JAVA_INT.byteSize(), callbackPointer);

            if (state.failure.get() != null) {
                throw new IllegalStateException(
                        "callback failed", state.failure.get());
            }

            System.out.println("result="
                    + Arrays.toString(data.toArray(JAVA_INT)));
            System.out.println("stubBytes="
                    + callbackPointer.byteSize());
        } // qsort đã return; không còn native caller dùng stub.

        System.out.println("stubAlive="
                + callbackPointer.scope().isAlive());

        // KHÔNG gọi function pointer sau khi Arena đã close.
    }
}
```

Chạy với JDK 22+:

```bash
javac -encoding UTF-8 QsortUpcallDemo.java
java --enable-native-access=ALL-UNNAMED QsortUpcallDemo
```

**stdout thành công (hành vi và các giá trị đã đối chiếu bằng JDK 24):**

```text
result=[1, 2, 3, 4, 7, 9]
stubBytes=0
stubAlive=false
```

**Vì sao từng phần là cần thiết?**

1. `Linker.nativeLinker()` biết ABI của JVM hiện tại; `defaultLookup()` tìm `qsort` trong các thư viện native do runtime cung cấp.
2. `compareDescriptor` mô tả **function pointer signature** của comparator; hai `ADDRESS.withTargetLayout(JAVA_INT)` cho callback view đọc được một C `int`.
3. `findVirtual(...).bindTo(state)` giữ callback receiver gắn với MethodHandle và loại bỏ receiver khỏi parameter list, để target có `(MemorySegment,MemorySegment)int` đúng descriptor.
4. `linker.upcallStub(compareHandle,compareDescriptor,arena)` tạo native function pointer nằm trong scope của Arena.
5. `arena.allocateFrom(JAVA_INT,...)` copy các số vào native memory, không truyền trực tiếp địa chỉ nội bộ của Java heap array.
6. `qsort.invokeExact(data, 6L, 4L, callbackPointer)` đi **Java → C**; mỗi lần comparator được gọi, control đi **C → Java → C**.
7. Khi `qsort` đã trả về, không còn invocation `qsort` đồng bộ đang dùng callback; đóng Arena ở cuối `try` là an toàn trong ví dụ này.
8. `stubBytes=0` nhắc rằng callbackPointer chỉ là **địa chỉ hàm**, không phải data segment 4 byte.
9. `stubAlive=false` chỉ minh họa scope đã đóng; **không** biến con trỏ đó thành pointer có thể sử dụng nữa.

Mẫu đã bắt `Throwable` **bên trong** `CompareState.compare` và ghi lỗi vào `AtomicReference`. Nếu lỗi xảy ra, comparator trả fallback 0 chỉ để **không ném qua native boundary**; sau khi `qsort` return, Java kiểm tra lỗi và throw từ **call stack Java**, lúc đó đã an toàn hơn để báo lỗi. Trong production, phải quyết định ứng xử khi comparator gặp lỗi giữa quá trình sắp xếp: kết quả có thể không phải thứ tự đúng và cần bị loại bỏ.

### Giới hạn ABI của ví dụ

Mã mô tả C `size_t` bằng `JAVA_LONG` (8 byte), đúng trên nhiều nền tảng 64-bit, không phải mọi platform. Nếu JVM chạy trên ABI 32-bit, `size_t` có thể là 4 byte, cần `JAVA_INT` và điều chỉnh đúng argument carriers khi `invokeExact`. Để triển khai đa nền tảng, kiểm tra `linker.canonicalLayouts().get("size_t")` hoặc dùng bindings sinh từ `jextract`, không hard-code size_t mapping xuyên kiến trúc.

Lỗi ABI **có thể crash JVM**, không chỉ ném Java exception. Hãy dùng C header chính xác và test trên OS/CPU/toolchain mục tiêu.

## 6. Tại sao upcallStub trả MemorySegment 0 byte?

Một `upcallStub` trả về `MemorySegment` có **native address**. API quy định kích thước segment nhận được là **0** vì nó không chứa một vùng dữ liệu người dùng có thể đọc bằng `get/set`; địa chỉ nằm trong segment là native code trampoline được linker tạo.

Các thao tác đúng:

```java
MemorySegment functionPointer =
        linker.upcallStub(target, callbackDescriptor, arena);

// Truyền functionPointer vào đối số C có kiểu function pointer.
// Ví dụ: registerCallback.invokeExact(functionPointer);
// Có thể kiểm tra functionPointer.byteSize() == 0.
```

Đây là trích đoạn; các biến đã được khai báo ở đoạn code ngoài. Không dùng `functionPointer.asSlice(0,...)`, `reinterpret` hoặc `get(JAVA_INT,0)` để “truy cập mã callback” vì pointer không đại diện một Java/C data buffer. Đừng tự gọi C `free(functionPointer.address())`; Arena là owner của stub.

Nếu một callback cần trả **data pointer**, giá trị trả về của Java target phải là một `MemorySegment` mang địa chỉ native hợp lệ, và native consumer phải có hợp đồng ownership/lifetime riêng cho **dữ liệu** được trỏ tới. Native function có thể giữ địa chỉ sau callback; nếu Java đóng Arena chứa dữ liệu trước lúc native dùng xong, sẽ xảy ra dangling pointer. Trả pointer trong upcall **không** tự gia hạn lifetime của data.

## 7. Chọn Arena đúng: phạm vi callback quyết định

| Arena | Ai có thể truy cập và đóng? | Khi dùng cho upcall stub | Điểm phải nhớ |
|---|---|---|---|
| `Arena.ofConfined()` | Owner Java thread; close tại owner | Callback đồng bộ và không có native thread khác giữ/call pointer | Đóng sau khi native downcall return; không phù hợp làm mặc định cho callback có thể đến từ foreign worker |
| `Arena.ofShared()` | Không owner thread cố định; close chủ động, multi-thread access | Callback SDK được giữ lại, callback có thể đến từ nhiều native threads | **Unregister + quiescence + join** trước `arena.close()` |
| `Arena.ofAuto()` | GC-managed, không thể close chủ động | Trường hợp không cần thời điểm release xác định và có Java reachability rõ ràng | C native giữ raw pointer **không được** xem là một Java strong reference |
| `Arena.global()` | Global scope, không explicit close | Chỉ với callback cần sống toàn vòng đời JVM/process theo thiết kế | Stub/native resources không được thu hồi bằng `close`; dễ rò nếu dùng cho callbacks ngắn hạn |

**Chọn nhanh:**

- Hàm C gọi callback ngay trong một lời gọi đồng bộ rồi hoàn tất (ví dụ `qsort`): `try(Arena arena = Arena.ofConfined())`.
- SDK đăng ký callback và gọi ở thời điểm sau, không cùng call stack, hoặc callback từ thread native khác: **`Arena.ofShared()` + lifecycle owner + stop/unregister/drain**.
- Callback thực sự cần tồn tại đến hết tiến trình: cân nhắc Arena global nhưng phải chấp nhận lifetime dài và tính toán leak.
- Không biết SDK giữ callback pointer đến khi nào? **Chưa an toàn để tạo/đóng stub**. Đọc contract native trước.

**Đừng hiểu shared arena là bảo đảm thread-safety cho Java listener.** `Arena.ofShared` cho phép quản lý/access scope đa luồng; state Java trong callback vẫn cần `AtomicInteger`, locks, queue hoặc thread confinement riêng để tránh data race. Việc callback có thể chạy trên native-created thread cũng ảnh hưởng thread-local context và ứng dụng UI/framework; không giả định nó chạy trên Java main thread.

### Vì sao `Arena.ofAuto()` khó kiểm soát cho callback giữ bởi SDK?

Một native SDK có thể chỉ lưu **một địa chỉ máy** trong C struct, không giữ Java reference đến `Arena` hoặc `MemorySegment`. Java GC không hiểu địa chỉ thô đó là strong reference. Nếu Java không giữ owner/stub/state còn reachable theo một contract xác định, dùng GC-managed arena có thể khiến stub bị giải phóng trong khi native vẫn giữ function pointer. Dùng `ofShared` với `close()` sau khi unregister là cách rõ ràng hơn khi callback tồn tại theo vòng đời một session.

## 8. Ví dụ thứ hai: SDK giữ callback qua nhiều native calls

`qsort` chỉ cần callback trong một downcall đồng bộ. Nhiều native SDK thì khác: Java gọi `register_callback(fn)`, native **lưu pointer**, và một lệnh `fire_callback` xảy ra về sau. Lúc này Arena không được đóng ngay khi `register_callback` return.

Ví dụ Linux đơn giản sau dùng **SDK single-threaded/synchronous dispatch**, để tập trung minh họa **retained function pointer + shared Arena + unregister**. Nó **không** tự tạo pthread. Muốn callback chạy từ native worker, phải mở rộng C code để có stop, join và in-flight barrier như mục 9.

### 8.1. Native file `callback_demo.c`

```c
// C11; thư viện ví dụ chỉ được gọi tuần tự từ một control thread.
typedef void (*event_callback)(int value);

static event_callback current = 0;

int register_callback(event_callback cb) {
    if (cb == 0 || current != 0) {
        return -1;
    }
    current = cb;              // GIỮ native function pointer.
    return 0;
}

void fire_callback(int value) {
    // Trong ví dụ, fire đồng bộ; callback return trước hàm này.
    if (current != 0) {
        current(value);
    }
}

void unregister_callback(void) {
    // SDK mẫu không có native worker/in-flight calls đồng thời.
    current = 0;
}
```

**Giới hạn rõ ràng:** biến global `current` không được đồng bộ; chỉ gọi lần lượt từ một control thread. Nếu một thread gọi `fire_callback` trong khi thread khác `unregister_callback`, đây có thể là data race C và không đủ an toàn. Một SDK thật phải định nghĩa thread safety và guarantee rằng unregister đã ngăn callbacks mới và đợi callback đang chạy (hoặc cho phép client dùng barrier riêng).

### 8.2. Java file `CallbackRegistrationDemo.java`

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
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static java.lang.foreign.ValueLayout.*;

public final class CallbackRegistrationDemo {
    private static final AtomicInteger last = new AtomicInteger(-1);
    private static final AtomicReference<Throwable> failure =
            new AtomicReference<>();

    private static void onValue(int value) {
        try {
            last.set(value);
        } catch (Throwable error) {
            // Không bao giờ để Throwable thoát khỏi upcall.
            failure.compareAndSet(null, error);
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // Shared arena sống xuyên qua register -> fire -> unregister.
        try (Arena arena = Arena.ofShared()) {
            SymbolLookup sdk = SymbolLookup.libraryLookup(
                    Path.of("./libcallback_demo.so").toAbsolutePath(),
                    arena);

            MethodHandle register = linker.downcallHandle(
                    sdk.findOrThrow("register_callback"),
                    FunctionDescriptor.of(JAVA_INT, ADDRESS));

            MethodHandle fire = linker.downcallHandle(
                    sdk.findOrThrow("fire_callback"),
                    FunctionDescriptor.ofVoid(JAVA_INT));

            MethodHandle unregister = linker.downcallHandle(
                    sdk.findOrThrow("unregister_callback"),
                    FunctionDescriptor.ofVoid());

            MethodHandle javaTarget = MethodHandles.lookup()
                    .findStatic(CallbackRegistrationDemo.class,
                            "onValue",
                            MethodType.methodType(void.class, int.class));

            MemorySegment callbackPointer = linker.upcallStub(
                    javaTarget,
                    FunctionDescriptor.ofVoid(JAVA_INT),
                    arena);

            int status = (int)register.invokeExact(callbackPointer);
            if (status != 0) {
                throw new IllegalStateException("register failed");
            }

            try {
                fire.invokeExact(7);    // Native -> onValue(7)
                fire.invokeExact(21);   // Native -> onValue(21)

                if (failure.get() != null) {
                    throw new IllegalStateException(
                            "callback failed", failure.get());
                }
                System.out.println("last=" + last.get());
            } finally {
                unregister.invokeExact();
                // SDK không còn lưu địa chỉ callback.
            }
        } // Đóng arena SAU unregister và sau mọi fire đồng bộ.

        System.out.println("unregistered");
    }
}
```

Lệnh biên dịch/chạy trên Linux có GCC và JDK 22+:

```bash
gcc -std=c11 -fPIC -shared \
  -o libcallback_demo.so callback_demo.c

javac -encoding UTF-8 CallbackRegistrationDemo.java
java --enable-native-access=ALL-UNNAMED CallbackRegistrationDemo
```

**stdout mong đợi khi chạy thành công:**

```text
last=21
unregistered
```

Giải thích:

- `SymbolLookup.libraryLookup(Path,arena)` mở native library và liên kết lifetime lookup/library với arena thích hợp. Dùng đúng đường file đã build và quyền native access.
- `register`, `fire`, `unregister` là **downcall handles** cho ba C entrypoints; `javaTarget` là **MethodHandle Java** cho callback.
- `FunctionDescriptor.ofVoid(JAVA_INT)` mô tả `void (*event_callback)(int)`. Không sử dụng `FunctionDescriptor.of(JAVA_INT,...)` vì hàm callback không trả giá trị.
- `upcallStub(javaTarget, ..., arena)` tạo pointer mà C có thể lưu. Sau `register`, **không được đóng arena**, dù Java invocation register đã return.
- `fire_callback` gọi pointer đã lưu; Java `onValue` cập nhật `AtomicInteger`. Việc dùng atomic giúp listener sẵn sàng cho trường hợp cần đồng bộ state, nhưng **không tự sửa được** data race phía C nếu C implementation được gọi từ nhiều threads.
- Trong `finally`, `unregister.invokeExact()` xóa pointer khỏi SDK. Vì C ví dụ chỉ gọi đồng bộ tuần tự trên một thread, sau `fire.invokeExact` cuối cùng return không còn callback in-flight.
- Sau `unregister` mới thoát `try` và `arena.close()`, khiến stub và symbol lookup không còn được dùng.

**Vì sao chọn `Arena.ofShared` dù C ví dụ đồng bộ?** Để minh họa owner session có thể sống qua nhiều lời gọi và tránh thiết kế giới hạn một owner thread nếu sau này SDK mở rộng callback từ worker. Nếu biết chắc mọi hoạt động cùng Java owner thread và SDK không có async callback, `ofConfined` vẫn có thể dùng, miễn mọi thao tác và close xảy ra đúng thread.

**Lưu ý ngoại lệ:** demo giả định SDK register/fire/unregister đều đáp ứng contract và unregister không thất bại. SDK thật cần error-code handling, shutdown owner, stop/await khi có native workers, và không được đóng Arena sau unregister thất bại nếu SDK có thể vẫn giữ pointer. Không thử chạy ví dụ `callback_demo.c` như một SDK đa luồng production.

## 9. Native worker gọi callback bất đồng bộ: stop, unregister, join, rồi close

Một số thư viện C/C++ lưu callback rồi gọi sau đó từ timer, I/O thread hoặc worker pool. Function pointer phải còn sống **qua toàn bộ thời gian SDK có thể gọi nó**.

```text
Java: Session OPEN                  Native SDK:
   create Arena.ofShared()
   create MethodHandle
   upcallStub -> fnPtr
   register(fnPtr)  -----------------> stores fnPtr in registry
   start()           ----------------> worker thread
                                       |
                                       +--> callback(fnPtr) ---> Java method
                                       +--> callback(fnPtr) ---> Java method
   requestStop()     ----------------> stop new callbacks
   unregister()      ----------------> remove registration
   awaitQuiescent()  <---------------- worker + in-flight calls done
   arena.close()                     no native user of fnPtr remains
   Session CLOSED
```

Tên API thực tế có thể khác: `stop`, `unregister`, `join`, `drain` hoặc `awaitStopped`; thứ tự phụ thuộc guarantee của SDK. Ví dụ một SDK có thể yêu cầu **unregister trước stop**, SDK khác có `stopAndJoin` thực hiện cả hai. Không tự suy ra rằng `unregister` luôn đợi callback đang chạy. Điều cần chứng minh trước khi `arena.close()` là:

1. Không còn native entrypoint có thể **bắt đầu** gọi function pointer.
2. Mọi callback đang chạy đã **return**.
3. Mọi worker có thể giữ và gọi pointer đã được **join/drain**, hoặc có synchronization/retention guarantee tương đương.
4. Không còn queued task hay SDK object chứa function pointer sẽ được gọi lại.
5. Thư viện cung cấp callback trampoline và target Java state vẫn còn sống trong suốt khoảng đó.

**Sai nghiêm trọng:**

```java
// ANTI-PATTERN: KHÔNG chạy.
MemorySegment callbackPointer;
try (Arena arena = Arena.ofShared()) {
    callbackPointer =
            linker.upcallStub(target, descriptor, arena);
    sdkRegister.invokeExact(callbackPointer);
} // Arena đóng trong khi SDK còn giữ pointer.
  // callback sau này: có thể nhảy vào native code stub đã giải phóng.
```

JVM không được bảo đảm sẽ ném `IllegalStateException` **trước** khi C gọi một địa chỉ máy đã bị giải phóng. Từ phía C, đó có thể là một **dangling function pointer** và crash hoặc memory corruption. Điều kiện `MemorySegment.scope().isAlive()` chỉ giúp Java kiểm tra trạng thái view; nó không thể làm native C lưu pointer “tự nhiên” trở nên an toàn.

### Không giữ lock cần cho callback khi join

Nếu controller giữ mutex rồi `join(worker)`, trong khi callback ở worker muốn lấy cùng mutex Java/native, deadlock có thể xảy ra. Một lifecycle owner tốt tách `requestStop()` không chặn khỏi `awaitStopped()`, và chỉ release pointer khi nhận được acknowledgement từ SDK. Nếu callback gọi `close()` và `close` cố join chính callback thread, đó cũng là self-join/lock inversion.

## 10. Phân biệt lifetime của stub, data, library và Java callback state

Một upcall thành công thường liên quan **nhiều** owner:

| Tài nguyên | Ai quản lý? | Khi nào kết thúc? |
|---|---|---|
| Native upcall stub/trampoline | Arena truyền vào `upcallStub` | Sau unregister + mọi callback quiescent, `arena.close()` |
| Java MethodHandle / listener / bound receiver | Java reference graph, callback registration owner | Giữ reachable đến sau callback cuối cùng |
| Native library/symbol lookup | `SymbolLookup.libraryLookup(..., arena)` hoặc runtime loader | Không unload khi native code vẫn có thể chạy hoặc function pointers còn được dùng |
| Native user-data/context pointer | SDK hoặc ứng dụng native owner | Theo allocator-specific destroy, sau in-flight callbacks |
| Callback input pointer | Bên native gọi callback | Thường chỉ hợp lệ **trong một callback invocation** hoặc theo SDK docs |
| Java data segment truyền xuống native | Arena cấp phát data | Sống đủ lâu cho native operation/callback có thể giữ nó |
| Native worker/timer | SDK/executor | Ngừng và join trước khi hủy resources mà nó truy cập |

Đóng stub Arena **không** giải phóng data buffer cấp bởi SDK. Đóng data Arena **không** tự unregister function pointer trong SDK. Xóa một Java listener reference không tự stop native callback. Mỗi tài nguyên có lifecycle API riêng và có thể phụ thuộc nhau.

Khi callback nhận `MemorySegment` trỏ tới native data và `FunctionDescriptor` có `ADDRESS.withTargetLayout(T)`, segment argument có view tương ứng `T.byteSize()` theo hợp đồng type/ABI. **Đừng giữ pointer view rồi đọc sau khi native SDK đã free bộ nhớ**: global scope của pointer argument không tự bảo đảm physical memory lifetime; size kiểm tra của Java cũng không ngăn native use-after-free.

## 11. Mô tả callback có tham số pointer và dữ liệu ngữ cảnh

Một SDK có thể cung cấp:

```c
// Header minh họa. Context là void* do ứng dụng/SDK quản lý.
typedef void (*event_cb)(int code, const char *message, void *userData);
int sdk_register(event_cb callback, void *userData);
int sdk_unregister(event_cb callback, void *userData);
```

FFM callback descriptor sơ lược:

```java
FunctionDescriptor cbDesc = FunctionDescriptor.ofVoid(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS,  // const char *message
        ValueLayout.ADDRESS   // void *userData
);

// Java target: void callback(int, MemorySegment, MemorySegment)
```

Đây là snippet minh họa, **không runnable độc lập**. Vì `ADDRESS` mặc định không chỉ rõ kích thước bộ nhớ trỏ tới, `message` thường là segment **size=0**. Không dùng `message.get(JAVA_BYTE,0)` mà không có contract về độ dài và scope. Nếu message là NUL-terminated C string và API bảo đảm một vùng nhớ hợp lệ, có thể dùng API string C/FFM tương ứng với lifetime/encoding xác định. Nếu SDK cung cấp thêm `size_t length`, nên dùng length có giới hạn và verify trước khi tạo view.

**Không chuyển Java Object thẳng thành C `void*`.** Java references không phải native pointer. Cách đơn giản với Java state là bind receiver vào `MethodHandle`, hoặc quản lý một numeric registry/token có synchronized mapping. Nếu C API yêu cầu `userData`, có thể cấp native context riêng trong Arena và truyền address hợp lệ, nhưng phải chốt ownership và lifetime của context độc lập với stub.

### C callback có return pointer hoặc struct

Một callback kiểu `const char *(*cb)(int)` đòi `FunctionDescriptor.of(ADDRESS,JAVA_INT)` và Java target trả `MemorySegment` (không phải `String`). Vùng memory mà pointer đó trỏ tới phải còn sống đủ lâu theo hợp đồng C; nếu string được cấp trong một `Arena.ofConfined` đóng trước khi C đọc, callback vẫn sai dù chữ ký MethodHandle khớp.

Callback trả `struct` by value cần group layout tương thích ABI, padding tường minh, và Java MethodHandle carrier phù hợp. Không đoán struct layout; đo C `sizeof`/`offsetof` hoặc dùng binding generator.

## 12. Tránh Java exception vượt khỏi upcall

Đây là rủi ro **khác** với các Java exception bình thường khi Java gọi Java. Đặc tả `Linker.upcallStub` yêu cầu target MethodHandle **không ném exception ra ngoài**: nếu target ném exception trong upcall, **JVM có thể kết thúc đột ngột**. Đừng viết:

```java
// ANTI-PATTERN: KHÔNG dùng trực tiếp làm upcall target.
static int badCompare(MemorySegment a, MemorySegment b) {
    throw new IllegalStateException("cannot compare");
}
```

Hướng an toàn:

```java
// Trích đoạn minh họa trong một state object.
private final AtomicReference<Throwable> failure =
        new AtomicReference<>();

int safeCompare(MemorySegment a, MemorySegment b) {
    try {
        return Integer.compare(
                a.get(ValueLayout.JAVA_INT, 0),
                b.get(ValueLayout.JAVA_INT, 0)
        );
    } catch (Throwable t) {
        failure.compareAndSet(null, t);
        return 0; // Giá trị fallback đúng carrier int.
    }
}
```

Không nên gọi `throw new RuntimeException` trong `catch` vì đó vẫn là exception thoát qua native boundary. Nếu callback C trả `void`, `catch` có thể ghi lỗi vào shared state/log rồi return bình thường. Sau native downcall hoặc từ control thread, ứng dụng đọc `failure` và quyết định:

- Báo lỗi/exception **ở Java caller** khi callback đã kết thúc.
- Dừng SDK theo protocol và release stub sau quiescence.
- Nếu C ABI có return code để báo lỗi, trả một mã error hợp lệ từ callback (không nhất thiết luôn là 0).
- Không hủy/trả native pointer khi callback đang ở giữa invocation.

**Lưu ý:** fallback comparator `0` chỉ là cách cô lập JVM khỏi exception. `qsort` có thể không cho output đúng nếu comparator đã lỗi; Java cần coi kết quả của operation là thất bại, không sử dụng mảng đã sắp xếp dở dang.

`MethodHandles.catchException` cũng có thể bọc một MethodHandle bằng handler nhưng phải kiểm tra chính xác method type và handler cũng **không được ném**. Với bài này, `try/catch(Throwable)` ngay trong target là phương án dễ hiểu nhất.

## 13. Sử dụng Java receiver, closure và MethodHandle chính xác

Khi callback cần Java state, đừng dùng `static mutable global` làm cơ chế duy nhất cho mọi session. Một lớp state riêng, được bind vào MethodHandle, tạo ra một callback độc lập cho từng registration:

```java
// Trích đoạn Java minh họa; giả định descriptor đã được tạo.
final class Counter {
    private final java.util.concurrent.atomic.AtomicInteger calls =
            new java.util.concurrent.atomic.AtomicInteger();

    int onCompare(MemorySegment a, MemorySegment b) {
        calls.incrementAndGet();
        return Integer.compare(
                a.get(ValueLayout.JAVA_INT, 0),
                b.get(ValueLayout.JAVA_INT, 0));
    }

    int calls() { return calls.get(); }
}

Counter state = new Counter();
MethodHandle unbound = MethodHandles.lookup().findVirtual(
        Counter.class, "onCompare", descriptor.toMethodType());

MethodHandle bound = unbound.bindTo(state);
// unbound.type() có receiver Counter ở vị trí đầu.
// bound.type() chỉ còn (MemorySegment,MemorySegment)int.
```

Đây là trích đoạn thiết kế; trong chương trình thật phải thêm **catch(Throwable)** trong target để không để lỗi `get`/callback thoát ra. Trong ví dụ đầy đủ `QsortUpcallDemo`, `CompareState` đã làm điều đó.

**`bindTo` chỉ giữ receiver Java**, không quản lý lifecycle của native registration. Native SDK vẫn giữ function pointer; Java owner cần giữ references phù hợp đến stub, method handle, state và Arena cho tới sau unsubscribe. Không coi “garbage collector thấy method handle” là bằng chứng native pointer còn hợp lệ sau khi arena đóng.

Một số lỗi MethodHandle phổ biến:

- `findStatic` để tra cứu instance method, hoặc `findVirtual` cho static method → lookup exception.
- Chưa `bindTo` receiver nên MethodHandle có thêm một tham số ngoài descriptor.
- Java target dùng `long` nhưng C prototype dùng `int` (hoặc ngược lại) → sai carrier/ABI.
- Java target `throws Exception` thực tế không xử lý ở bên trong → lỗi nghiêm trọng khi native invokes.
- Native C lưu pointer sau khi owner Java scope kết thúc → dangling stub.
- `MethodHandle.asType` được dùng để che C prototype sai: Java adaptation không sửa được native calling convention hoặc pointer width.

## 14. Kiểu C ABI, size_t, calling convention và FunctionDescriptor

`Linker.nativeLinker()` chỉ biết ABI hiện tại. C header phải là nguồn sự thật cho callback:

```c
// Hai callback KHÁC ABI: không dùng chung descriptor.
int (*compare_ptr)(const void *, const void *);
void (*event_ptr)(int value);
```

| C signature | FunctionDescriptor gợi ý theo ABI thông thường | Java target carrier |
|---|---|---|
| `int f(int)` | `of(JAVA_INT, JAVA_INT)` | `(int)int` |
| `void f(int)` | `ofVoid(JAVA_INT)` | `(int)void` |
| `double f(double,double)` | `of(JAVA_DOUBLE,JAVA_DOUBLE,JAVA_DOUBLE)` | `(double,double)double` |
| `int f(const int*,const int*)` | `of(JAVA_INT,ADDRESS.withTargetLayout(JAVA_INT),ADDRESS.withTargetLayout(JAVA_INT))` | `(MemorySegment,MemorySegment)int` |
| `void f(void*)` | `ofVoid(ADDRESS)` | `(MemorySegment)void` |

Bảng mang tính **ví dụ**: C `int`, `long`, `size_t`, `wchar_t`, `bool`, pointer size có mapping theo ABI. `linker.canonicalLayouts()` cung cấp các layout canonical cho các tên type C do linker hỗ trợ. Trên Linux/x64 điển hình, `size_t` và `long` đều có thể là 8 byte; Windows/x64 `long` thường 4 byte dù pointer và `size_t` thường 8. Không suy ra ABI chỉ bằng tên Java primitive.

`FunctionDescriptor.of(...)` diễn giải **return layout trước**, còn `FunctionDescriptor.ofVoid(...)` chỉ có **argument layouts**. `ValueLayout.ADDRESS` cần được dùng cho native pointer, không thay bằng `JAVA_LONG` chỉ vì máy hiện tại dùng con trỏ 64-bit; calling convention và pointer representation vẫn có quy tắc riêng.

**Quan trọng:** Java linker có thể phát hiện MethodHandle/descriptor **không tương thích**, nhưng không thể tự kiểm chứng một function pointer C hoặc tên native symbol thật sự mang chữ ký bạn khai báo. C code cast callback sang function pointer type sai rồi gọi có thể làm JVM crash hoặc gây undefined behavior. Với ABI khó hoặc structs phức tạp, sinh bindings bằng `jextract` từ C header chính xác thường đáng tin hơn tự gõ layout thủ công.

## 15. Upcall và JNI callback có gì khác?

| Đặc điểm | JNI gọi ngược Java | FFM upcallStub |
|---|---|---|
| Đường gọi | Native thread dùng `JNIEnv*` và `Call<Type>Method` | Native code gọi function pointer do `upcallStub` tạo |
| Mô tả phương thức | `jmethodID`/`jobject` cùng chữ ký JNI | Java `MethodHandle` + native `FunctionDescriptor` |
| Vòng đời Java reference | `NewGlobalRef`/`DeleteGlobalRef` khi giữ Java object | Java state và MethodHandle phải còn reachable; stub thuộc Arena |
| Native thread | Thread phải attach JVM trước khi sử dụng `JNIEnv*` | FFM runtime thực hiện bước cầu nối upcall; vẫn cần quản lý native worker và callback lifetimes |
| Exception | JNI pending exception thuộc thread JNI | Không để Java Throwable thoát khỏi upcall target; có thể khiến JVM terminate |
| Cleanup | Dừng worker rồi xóa JNI refs/SDK handles | Unregister/drain/join, đóng Arena, giải phóng native resources theo owner |
| Lỗi dễ mắc | Dùng `JNIEnv*`/local JNI refs sai thread | Sai descriptor ABI hoặc đóng Arena khi native còn function pointer |

FFM **không** làm native memory safety tự động. Nó thay một số cách biểu diễn và cung cấp scope checks cho Java side, nhưng nếu native code gọi địa chỉ đã giải phóng, scope của Java không thể làm hồi sinh code stub.

Các hệ thống có thể dùng cả JNI và FFM. Không trộn các loại handle/allocator release khác nhau: một FFM `upcallStub` có owner là `Arena`, không được `free` bằng C, và JNI `jobject` không phải C function pointer.

## 16. Lỗi phổ biến và cách sửa đúng

| Lỗi | Triệu chứng/rủi ro | Cách sửa |
|---|---|---|
| `upcallStub` nhận target type khác descriptor | `IllegalArgumentException` khi tạo | Dùng `descriptor.toMethodType()`, bind receiver đúng |
| C callback trả `void` nhưng Java descriptor trả `JAVA_INT` | Sai C ABI; crash/undefined behavior | `FunctionDescriptor.ofVoid(...)` đúng prototype |
| C pointer được mô tả bằng `JAVA_LONG` tùy tiện | Sai calling convention/ABI | Dùng `ValueLayout.ADDRESS` |
| C `size_t` giả định luôn `JAVA_LONG` | Sai trên 32-bit ABI | Dùng `canonicalLayouts().get("size_t")`/generated binding |
| Quên `withTargetLayout` nhưng callback gọi `get` ngay | Pointer argument segment thường dài 0 byte | Chọn bounded target layout theo C contract, hoặc xử lý bound an toàn |
| Native truyền con trỏ NULL nhưng callback `get` tại offset0 | Truy cập invalid/null pointer | Kiểm tra `MemorySegment.NULL` hoặc address, theo C contract |
| Đọc `const int*` sau khi native đã free dữ liệu | Use-after-free | Chỉ đọc trong callback lifetime hợp lệ, copy khi cần giữ lâu |
| Dùng `Arena.ofConfined` cho callback từ SDK thread khác | Vi phạm thread confinement/lifetime assumptions | Dùng shared Arena và đúng shutdown protocol |
| Đóng Arena ngay sau `register` | SDK vẫn giữ function pointer đã giải phóng | Unregister/drain/join trước close |
| Dùng `Arena.ofAuto` nhưng chỉ native giữ raw pointer | GC có thể thu hồi stub khi không còn Java reachability | Session owner + explicit `Arena.ofShared` |
| Giữ stub toàn JVM bằng `Arena.global()` cho mọi request | Leak native stub/resource | Chọn closeable Arena theo session |
| Java callback ném `RuntimeException` | JVM có thể chấm dứt đột ngột | Target tự `catch(Throwable)` và chuyển lỗi qua status/state |
| Java comparator dùng `a - b` | Integer overflow, thứ tự sai | `Integer.compare(a,b)` |
| Java callback gọi stop/join từ chính worker | Deadlock/self-join | Callback chỉ phát requestStop; control thread thực hiện await |
| Unregister không chờ in-flight callback nhưng Arena close ngay | Use-after-free | Đợi SDK quiescence barrier trước close |
| Callback đọc/writes cùng Java object thiếu lock | Data race | Atomic/queue/locking phù hợp, độc lập với Arena |
| Tìm `qsort` bằng `defaultLookup` thất bại | Native library lookup khác OS/loader | Kiểm tra native symbol/ABI, dùng libraryLookup khi cần |
| FFM restricted method không có native access | Warning hoặc IllegalCallerException tùy JDK/options | `--enable-native-access=ALL-UNNAMED` hoặc module name |
| Dùng tutorial `jdk.incubator.foreign` JDK17/18 cho JDK22+ | Tên API/signature không khớp | Dùng `java.lang.foreign` ổn định JDK22+ |

### Checklist tối thiểu khi debug

1. Mở đúng C header và viết **exact callback typedef** trước.
2. Kiểm tra OS/CPU ABI, các canonical layouts và type widths.
3. In hoặc kiểm tra `descriptor.toMethodType()` so với `target.type()`.
4. Xác nhận `upcallStub` dùng Arena còn sống.
5. Đảm bảo native function pointer chỉ được lưu và gọi theo contract.
6. Không để Throwable thoát khỏi Java target.
7. Nếu callback trên native worker, xác định stop/unregister/in-flight/join.
8. Chỉ đóng Arena sau khi có bằng chứng callback không còn chạy.
9. Với native data pointer, xác minh bounds, alignment, ownership và lifetime.
10. Khi phát hiện crash, kết hợp native sanitizers và unit tests; không dựa riêng vào Java `try/catch`.

## 17. Bài tập có đáp án

**Bài 1 — xác định descriptor.** C SDK yêu cầu `void (*cb)(int eventCode)`. Java target là `static void onEvent(int code)`. Descriptor nào đúng?

**Đáp án:** `FunctionDescriptor.ofVoid(ValueLayout.JAVA_INT)`, `MethodType.methodType(void.class,int.class)`. `FunctionDescriptor.of(JAVA_INT,JAVA_INT)` sẽ sai return type.

**Bài 2 — hai pointer int.** C `int (*cmp)(const int*, const int*)`. Nếu Java target là `int compare(int a,int b)` thì có thể dùng nó trực tiếp với `ADDRESS,ADDRESS` không?

**Đáp án:** Không. Hai tham số C là pointer, MethodHandle carrier phải là `MemorySegment,MemorySegment`. Dùng `ADDRESS.withTargetLayout(JAVA_INT)` để đọc mỗi value ở offset0, rồi `Integer.compare`.

**Bài 3 — Arena lifetime.** Java gọi `register(cb)` rồi đóng `Arena.ofConfined()` khi register return; SDK lưu callback và sẽ gọi sau 3 giây. An toàn không?

**Đáp án:** Không. SDK còn giữ raw function pointer; arena đã giải phóng stub. Dùng một Arena sống theo registration/session và chỉ close sau unregister + in-flight callback quiescence. Nếu callback có thể đến từ foreign thread, ưu tiên `Arena.ofShared()`.

**Bài 4 — kiểm tra segment.** `upcallStub` trả `MemorySegment` với `byteSize()==0`. Có nên `reinterpret(4)` rồi `get(JAVA_INT,0)` để đọc giá trị trả về callback không?

**Đáp án:** Không. Stub chứa địa chỉ **mã native trampoline**, không phải data segment. Giá trị trả về đến từ Java MethodHandle khi native gọi function pointer, không phải bytes có thể `get` trên stub.

**Bài 5 — exception.** Java comparator ném `IllegalArgumentException` trong khi `qsort` gọi qua function pointer. Có thể bắt nó bằng `try/catch` quanh `qsort.invokeExact` trên Java không?

**Đáp án:** Không được dựa vào điều đó. Đặc tả upcall cảnh báo exception thoát khỏi target có thể kết thúc JVM đột ngột. Bắt `Throwable` ngay bên trong callback, ghi lỗi vào Java state hoặc status và xử lý sau downcall.

**Bài 6 — native worker.** SDK `unregister(cb)` chỉ ngăn callback mới, callback đang chạy chưa return. Đã được `arena.close()` ngay chưa?

**Đáp án:** Chưa. Cần chờ callback in-flight hoàn tất hoặc nhận SDK quiescence acknowledgement rồi mới đóng stub Arena. Nếu có worker/queue giữ pointer thì stop/join/drain cả chúng.

**Bài 7 — ABI.** C `qsort` chạy trên ABI có `size_t` 4 byte. Java hard-code `JAVA_LONG` cho hai `size_t`. Rủi ro gì?

**Đáp án:** Descriptor downcall sai ABI. Phải dùng canonical layout `size_t` cho platform, với Java MethodHandle carrier phù hợp (ví dụ `JAVA_INT` khi 4 byte), và đúng number of args. Không thể chỉ đổi giá trị literal từ `6L` thành `6` nếu descriptor chưa sửa.

**Bài 8 — state.** C SDK cần giữ callback lâu dài và nhiều Java sessions cùng active. Dùng một static `AtomicInteger last` và một `Arena.global()` cho mọi session có tốt không?

**Đáp án:** Dễ lẫn state giữa các sessions và không release native stub. Thiết kế state/MethodHandle riêng cho mỗi registration, giữ Arena shared closeable theo session, unregister + join trước close.

**Bài 9 — pointer target.** Callback C nhận `const uint8_t* bytes` và `size_t length`. Có thể đọc 100 byte chỉ vì Java nhận `MemorySegment bytes` không?

**Đáp án:** Không. Phải kiểm tra length do C cung cấp, ABI của `size_t`, pointer NULL, lifetime native buffer và bounds khi tạo view/copy. `ADDRESS` không tự biết số byte thật sự hợp lệ.

**Bài 10 — thứ tự cuối.** Một SDK đã stop callback và join tất cả workers, sau đó muốn close Arena và unload shared library. Cần cân nhắc gì?

**Đáp án:** Phải chắc chắn không còn in-flight native call, pending callback/function pointer invocation hay data pointer từ thư viện. Sau quiescence, đóng Arena để release stub và lookup/library theo ownership, rồi unload dependency theo API. Không gọi `dlclose` khi còn code trong library đang được thực thi.

## 18. Tóm tắt và tài liệu tham khảo

**Công thức để nhớ:**

```java
// Minh họa ba đầu vào; không phải file chạy độc lập.
MemorySegment callback = linker.upcallStub(
        targetMethodHandle,  // Java carrier types đúng
        functionDescriptor, // native C ABI đúng
        arena               // lifetime đúng
);
```

Mọi thành phần đều quan trọng:

- **`FunctionDescriptor`** mô tả native callback prototype: kiểu trả về, các tham số, pointer/target layout đúng ABI.
- **`MethodHandle`** đại diện logic Java thực thi khi native gọi, có `MethodType` khớp descriptor và không ném Throwable ra ngoài.
- **`Arena.ofConfined()`** thích hợp cho callback **đồng bộ, cùng phạm vi downcall** đã hoàn tất trước khi close.
- **`Arena.ofShared()`** thích hợp cho callback **được giữ lâu hoặc có thể đến từ foreign threads**, nhưng vẫn phải **unregister, drain/join rồi mới close**.
- **`MemorySegment` stub size0** đại diện địa chỉ hàm, không phải dữ liệu để `get/set`.
- **FFM không cứu được native function pointer đã hết hạn**. Một pointer còn lưu trong C sau khi Arena đóng có thể gây JVM crash khi được gọi.

### Tài liệu chính thức

- [JEP 454 — Foreign Function & Memory API chính thức từ JDK 22](https://openjdk.org/jeps/454)
- [Oracle Java SE 25 — Linker: `upcallStub`, qsort callback, safety/exception và ABI](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle Java SE 25 — Upcalls: Passing Java Code as a Function Pointer](https://docs.oracle.com/en/java/javase/25/core/upcalls-passing-java-code-function-pointer-foreign-function.html)
- [Oracle Java SE 25 — FunctionDescriptor, `of`/`ofVoid`/`toMethodType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [Oracle Java SE 25 — Arena: confined/shared/automatic/global scopes](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html)
- [Oracle Java SE 25 — ValueLayout/AddressLayout, `withTargetLayout`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/AddressLayout.html)
- [Oracle Java SE 24 — Restricted methods và `--enable-native-access`](https://docs.oracle.com/en/java/javase/24/core/restricted-methods.html)
- [Oracle Java SE 22 — SegmentAllocator và `allocateFrom`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html)
