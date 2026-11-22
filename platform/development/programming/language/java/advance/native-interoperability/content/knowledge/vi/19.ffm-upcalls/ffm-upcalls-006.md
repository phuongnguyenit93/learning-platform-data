# Gọi lại bằng FFM — Bắt mọi ngoại lệ trong callback để tránh ngoại lệ thoát qua ranh giới upcall

## 1. Quy tắc sống còn: không để Java `Throwable` vượt qua FFM upcall

**Foreign Function & Memory (FFM) API** cho phép Java gọi hàm C bằng **downcall**, đồng thời cho phép native code gọi ngược vào Java bằng **upcall stub**. Một upcall stub là con trỏ hàm native được tạo bởi `Linker.upcallStub(MethodHandle, FunctionDescriptor, Arena)`; khi C gọi con trỏ đó, JVM thực thi Java `MethodHandle` liên kết với stub.

Vấn đề là **Java exception không phải C exception**. C không có cơ chế bắt, unwind hay diễn dịch `RuntimeException`, `IOException` hoặc `Error` của Java. Theo hợp đồng chính thức của `Linker.upcallStub`, **target method handle không được ném exception ra ngoài**. Nếu target ném exception thoát qua ranh giới upcall, **JVM sẽ kết thúc đột ngột**, không đơn giản trả exception cho Java caller.

Đó là lý do bài này có một quy tắc bắt buộc:

> **Bọc toàn bộ code callback bằng `try/catch (Throwable t)`; ghi nhận lỗi mà không ném lại bên trong upcall; trả về giá trị hợp lệ theo đúng ABI C; sau khi native call kết thúc, xử lý/truyền lỗi ở phía Java.**

Sơ đồ:

```text
Java                           Native/C                         Java callback
  │                                │                                  │
  ├── downcall qsort(array, cmp) ──►│                                  │
  │                                ├── cmp(pointerA, pointerB) ──────►│
  │                                │                             try { work(); }
  │                                │                             catch(Throwable t) {
  │                                │                               record(t);
  │                                │                               return 0;
  │                                │                             }
  │                                │◄───────── int (valid ABI) ───────┤
  │◄──── native function returns ──┤                                  │
  │                                                                    │
  ├── inspect recorded failure                                       │
  └── throw Java exception HERE, after native returns                │
```

Phải phân biệt **Java exception ở một vòng gọi Java thông thường** với **exception thoát qua callback đang được native code gọi**. Java có thể `throw` ở một phương thức Java khác khi đã trở về Java context, nhưng **không được `throw` vượt khỏi target method handle do `upcallStub` sử dụng**.

**Phạm vi ví dụ:** FFM API chính thức **JDK 22+ (JEP 454)**. Chương trình đã được biên dịch/chạy với **OpenJDK 24.0.2 trên Windows x64** bằng thư viện C chuẩn `qsort`. Không cần tự tạo DLL; có hướng dẫn ABI 64-bit và lưu ý Linux/macOS. JDK 21 vẫn là FFM preview (JEP 442), cần flags và rà soát API.

## 2. Một upcall được tạo như thế nào?

Ví dụ C chuẩn:

```c
void qsort(void *base, size_t count, size_t element_size,
           int (*compare)(const void *, const void *));
```

`qsort` nhận con trỏ hàm `compare`. Native code gọi comparator nhiều lần để quyết định thứ tự phần tử; comparator **phải trả một số nguyên**:

- Giá trị âm: phần tử thứ nhất nhỏ hơn thứ hai.
- `0`: hai phần tử so sánh bằng nhau.
- Giá trị dương: phần tử thứ nhất lớn hơn thứ hai.

Trong Java FFM, ta cần:

1. Lấy `Linker.nativeLinker()` và tạo **downcall handle** tới `qsort`.
2. Viết một Java static method có chữ ký tương ứng với callback: hai `MemorySegment` là địa chỉ `const void*`, return `int`.
3. Tạo `MethodHandle` trỏ tới Java method đó.
4. Dùng `Linker.upcallStub` để tạo native function pointer cho `qsort`.
5. Giữ **Arena và upcall stub còn sống** cho đến khi native code chắc chắn không gọi callback nữa.
6. Trong callback, **không cho bất kỳ Java `Throwable` nào thoát**; lưu lỗi và trả giá trị hợp lệ.
7. Sau khi `qsort` trở về, **kiểm tra lỗi đã ghi**, không sử dụng dữ liệu sắp xếp nếu comparator từng lỗi.

### Hai `FunctionDescriptor` khác nhau

Đối với ABI 64-bit trong bài:

```java
// qsort(void *base, size_t count, size_t elemSize, functionPointer)
FunctionDescriptor qsortDesc = FunctionDescriptor.ofVoid(
    ValueLayout.ADDRESS, ValueLayout.JAVA_LONG,
    ValueLayout.JAVA_LONG, ValueLayout.ADDRESS);

// int compare(const void *a, const void *b)
FunctionDescriptor compareDesc = FunctionDescriptor.of(
    ValueLayout.JAVA_INT,
    ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT),
    ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT));
```

Đây là đoạn rút gọn hợp lệ khi đã import FFM types. `size_t` rộng **64 bit** trên Windows x64 và Linux x86-64 nên `JAVA_LONG` tương ứng ở đây; **không** áp nguyên descriptor cho hệ 32-bit. `ValueLayout.ADDRESS` là carrier `MemorySegment` trong Java, còn `JAVA_INT` là primitive `int`.

Hai con trỏ của comparator `qsort` thực tế trỏ đến phần tử `C int`. `ADDRESS.withTargetLayout(JAVA_INT)` cho FFM biết mỗi con trỏ có ít nhất **4 byte hợp lệ** để Java đọc, thay vì zero-length pointer không thể dereference. Việc khai báo target layout này là **restricted**, do bạn phải tự bảo đảm nó đúng ABI và nội dung thật. Sai ABI/pointer/bounds có thể gây crash bất kể code có `catch(Throwable)` hay không.

## 3. Vì sao phải bắt `Throwable`, không chỉ `Exception`?

Phân cấp Java:

```text
java.lang.Throwable
├── java.lang.Exception
│   ├── RuntimeException
│   │   ├── IllegalArgumentException
│   │   ├── IllegalStateException
│   │   ├── IndexOutOfBoundsException
│   │   └── NullPointerException
│   └── IOException, InterruptedException, ...
└── java.lang.Error
    ├── AssertionError
    ├── LinkageError
    ├── OutOfMemoryError
    ├── StackOverflowError
    └── VirtualMachineError, ...
```

`catch (Exception e)` không chặn `Error`. Nếu callback ném `AssertionError`, `LinkageError` hoặc một `Error` khác, exception đó có thể thoát qua upcall boundary. **`catch (Throwable t)`** là cách bọc boundary đủ rộng theo hợp đồng `Linker.upcallStub`.

Cần hiểu đúng giới hạn:

- Bắt `Throwable` là **biện pháp chặn exception ở Java boundary**, không có nghĩa mọi lỗi fatal đều phục hồi được. Với `OutOfMemoryError`, `StackOverflowError` hoặc JVM corruption, ngay cả handler có thể không còn đủ tài nguyên để thực hiện tác vụ phức tạp; JVM vẫn có thể dừng vì nguyên nhân khác.
- Không ném lại `t` **bên trong target method handle**.
- Không tự tạo exception mới, không format stack trace dài, không ghi log phức tạp hay gọi code dễ ném trong `catch`.
- Dùng cơ chế ghi lỗi tối thiểu (ví dụ `AtomicReference.compareAndSet`) để lưu **lỗi đầu tiên** và trả một sentinel hợp lệ cho C.
- Báo lỗi ở **Java boundary nằm ngoài native call** (ví dụ sau khi `qsort.invokeExact(...)` kết thúc).

**Quan trọng:** Một `try/catch(Throwable)` chỉ bao được code thực sự nằm **bên trong `try`**. Nếu callback còn logic có thể ném trước `try`, trong `finally` hoặc trong handler sau khi đã catch, ngoại lệ vẫn có thể thoát. Đừng để logger/metrics/callback cleanup tạo lỗi thứ hai bên ngoài vùng bảo vệ.

## 4. Hai ví dụ sai không được đưa vào production

### Sai 1 — callback ném thẳng qua upcall

```java
// CỐ Ý SAI: method được dùng làm FFM upcall target.
static int unsafeCompare(MemorySegment a, MemorySegment b) {
    int x = a.get(ValueLayout.JAVA_INT, 0);
    if (x < 0) {
        throw new IllegalArgumentException("negative element");
    }
    return Integer.compare(x, b.get(ValueLayout.JAVA_INT, 0));
}
```

Khi C `qsort` gọi comparator và `x < 0`, Java exception thoát khỏi target; **không có cơ chế bắt an toàn ở phía C**. Đừng chạy thử biến thể này để “xem JVM có crash không”: theo tài liệu Linker, JVM có thể kết thúc đột ngột. Thay bằng callback được bọc ở mục 5.

### Sai 2 — chỉ bắt `Exception` hoặc ném lại trong handler

```java
// CỐ Ý SAI: Error không được bắt.
try {
    work();
} catch (Exception e) {
    throw new RuntimeException("callback failed", e); // Vẫn thoát upcall!
}
```

Ngay cả `catch (Throwable t) { throw new RuntimeException(t); }` **vẫn sai**. Không chuyển exception về native bằng cách ném Java `Throwable`. Hãy định nghĩa một **error protocol** có thể biểu diễn trong C: trả status code, set out-parameter, đánh dấu failure state hoặc gọi API báo lỗi phù hợp (miễn handler không ném).

## 5. Ví dụ đầy đủ và đã chạy: an toàn khi FFM gọi `qsort`

Mục tiêu:

- `qsort` sẽ gọi ngược comparator Java thông qua FFM upcall stub.
- Với input tốt, comparator làm việc bình thường và `qsort` sắp xếp số tăng dần.
- Nếu comparator thấy giá trị `-7`, nó **cố ý ném `IllegalArgumentException` trong vùng `try`**, nhưng `catch(Throwable)` bắt lại, ghi vào `AtomicReference` rồi trả `0` cho C.
- Sau khi `qsort` hoàn tất, Java phát hiện recorded failure và ném `IllegalStateException` **ngoài upcall boundary**. Người gọi Java đọc nguyên nhân `getCause()`; JVM vẫn tiếp tục chạy.
- Đầu ra không phụ thuộc thứ tự sort của trường hợp lỗi, vì trường hợp đó **phải bỏ kết quả**.

### 5.1. Source đầy đủ: `SafeQsortUpcallDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;

public final class SafeQsortUpcallDemo {
    private static final Linker LINKER = Linker.nativeLinker();

    private static final FunctionDescriptor COMPARE_DESCRIPTOR =
        FunctionDescriptor.of(ValueLayout.JAVA_INT,
            ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT),
            ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT));

    private static final FunctionDescriptor QSORT_DESCRIPTOR =
        FunctionDescriptor.ofVoid(ValueLayout.ADDRESS, ValueLayout.JAVA_LONG,
            ValueLayout.JAVA_LONG, ValueLayout.ADDRESS);

    // The method handle bound to the upcall stub must NEVER let
    // a Throwable escape to foreign code.
    private static int safeCompare(MemorySegment a, MemorySegment b,
                                   AtomicReference<Throwable> failure) {
        try {
            if (failure.get() != null) return 0;

            int x = a.get(ValueLayout.JAVA_INT, 0);
            int y = b.get(ValueLayout.JAVA_INT, 0);

            if (x == -7 || y == -7) {
                throw new IllegalArgumentException("element -7 is invalid");
            }
            return Integer.compare(x, y);
        } catch (Throwable t) {
            // Keep the FIRST failure; avoid logging or throwing here.
            failure.compareAndSet(null, t);
            return 0; // Valid int ABI; do NOT trust sorting result now.
        }
    }

    private static int[] sort(int[] values) throws Throwable {
        // A NEW failure box for each native call avoids cross-call leakage.
        AtomicReference<Throwable> failure = new AtomicReference<>();

        MethodHandle target = MethodHandles.lookup().findStatic(
            SafeQsortUpcallDemo.class, "safeCompare",
            MethodType.methodType(int.class, MemorySegment.class,
                MemorySegment.class, AtomicReference.class));

        // Insert the failure state as arg #2: target is now
        // (MemorySegment, MemorySegment)int, matching the C callback.
        target = MethodHandles.insertArguments(target, 2, failure);

        MethodHandle qsort = LINKER.downcallHandle(
            LINKER.defaultLookup().findOrThrow("qsort"), QSORT_DESCRIPTOR);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment array = arena.allocate(
                (long) values.length * ValueLayout.JAVA_INT.byteSize(),
                ValueLayout.JAVA_INT.byteAlignment());

            for (int i = 0; i < values.length; i++) {
                array.setAtIndex(ValueLayout.JAVA_INT, i, values[i]);
            }

            // The stub lives at least as long as qsort may call it.
            MemorySegment callback =
                LINKER.upcallStub(target, COMPARE_DESCRIPTOR, arena);

            // qsort is synchronous: when it returns, callbacks are done.
            qsort.invokeExact(array, (long) values.length,
                ValueLayout.JAVA_INT.byteSize(), callback);

            // Only after returning from native code may Java throw.
            Throwable cause = failure.get();
            if (cause != null) {
                throw new IllegalStateException("upcall failed", cause);
            }

            int[] result = new int[values.length];
            for (int i = 0; i < result.length; i++) {
                result[i] = array.getAtIndex(ValueLayout.JAVA_INT, i);
            }
            return result;
        }
    }

    public static void main(String[] args) throws Throwable {
        System.out.println("good: "
            + Arrays.toString(sort(new int[] {4, 1, 3, 2})));

        try {
            sort(new int[] {5, -7, 3});
        } catch (IllegalStateException e) {
            Throwable cause = e.getCause();
            System.out.println("error after return: "
                + cause.getClass().getSimpleName() + ": " + cause.getMessage());
        }

        System.out.println("JVM still alive");
    }
}
```

### 5.2. Biên dịch và chạy

Chọn **JDK 22+**, một ABI **64-bit** có `qsort` trong `Linker.defaultLookup()` (chương trình đã được chạy trên Windows x64/OpenJDK 24). Không cần tạo DLL hoặc C source cho ví dụ này.

Trong thư mục chứa file `SafeQsortUpcallDemo.java`:

```bash
javac -encoding UTF-8 SafeQsortUpcallDemo.java

java --enable-native-access=ALL-UNNAMED SafeQsortUpcallDemo
```

**Stdout chính xác đã kiểm chứng trên OpenJDK 24.0.2 / Windows x64:**

```text
good: [1, 2, 3, 4]
error after return: IllegalArgumentException: element -7 is invalid
JVM still alive
```

Đây là output **thực thi**, không phải lời đoán. Compiler có thể phát cảnh báo restricted FFM APIs nếu bật `-Xlint:all`; lệnh ở trên không yêu cầu lint. `--enable-native-access=ALL-UNNAMED` cấp quyền native cho code classpath khi dùng `downcallHandle`, `upcallStub` và `ADDRESS.withTargetLayout`.

### 5.3. Phân tích các chi tiết giúp an toàn

**`safeCompare` bao kín body trong một `try`:** mọi thao tác đọc segment, kiểm tra dữ liệu và `Integer.compare` nằm trong vùng có `catch(Throwable)`. Khi giá trị `-7` gây `IllegalArgumentException`, code **không ném ra khỏi callback**, mà lưu đúng `Throwable`.

**`AtomicReference<Throwable> failure` là trạng thái theo mỗi lời gọi:** nếu dùng biến `static` toàn cục không reset, một lỗi từ lượt sort trước có thể làm lượt sau hỏng. `AtomicReference` cũng cho phép thấy lỗi giữa các thread nếu một native API gọi callbacks từ nhiều threads; tuy nhiên nó **không thay thế** giao thức đợi callbacks kết thúc.

**`compareAndSet(null,t)` giữ lỗi đầu tiên:** native code có thể gọi comparator nhiều lần. Sau lỗi đầu, callback trả `0` cho các lượt tiếp theo, tránh thêm tác vụ nguy hiểm. Trong điều kiện thông thường, thao tác AtomicReference này không cần cấp phát exception mới và không ném.

**`return 0` có thể bảo toàn ABI, không bảo toàn kết quả sắp xếp:** `0` là giá trị `int` hợp lệ cho comparator C. Tuy nhiên vì một số cặp bị coi bằng nhau sau lỗi, kết quả `qsort` của lượt lỗi **không đáng tin**. Do đó method `sort` **không bao giờ copy hoặc trả kết quả khi `failure != null`**; nó ném `IllegalStateException` sau native call.

**`MethodHandles.insertArguments` bảo toàn chữ ký callback:** method Java ban đầu có tham số thứ ba `AtomicReference`, không phải một tham số C. Sau `insertArguments(target,2,failure)`, handle target thực sự có `MethodType (MemorySegment,MemorySegment)int`, đúng callback descriptor. Nếu không bind context và đưa thẳng handle ba tham số cho `upcallStub`, linker sẽ từ chối do mismatch.

**`Arena.ofConfined()` sống trong toàn bộ downcall:** stub và array đều được tạo trong arena và chỉ bị dọn **sau** `qsort.invokeExact` trở về. `qsort` là ví dụ synchronous: sau return, nó không giữ function pointer để gọi sau. Nếu native API đăng ký callback lâu dài, **không được đóng arena** ngay sau hàm register; phải có unregister, chờ callbacks còn chạy hoàn tất rồi mới đóng arena phù hợp.

**Lỗi Java được ném ở `sort` sau khi native kết thúc:** vì lúc đó đã quay về Java code bên ngoài callback, một Java exception mới có thể đi theo quy tắc thông thường tới caller. `getCause()` giữ lỗi ban đầu, kể cả khi API public chỉ muốn lộ `IllegalStateException`.

## 6. Vì sao không thể chỉ “bọc downcall bằng try/catch”?

Mẫu **không giải quyết được ranh giới upcall**:

```java
// SAI về mặt chiến lược: upcall target vẫn được phép throw.
try {
    qsort.invokeExact(array, n, elementSize, unsafeCallback);
} catch (RuntimeException e) {
    // Nếu Java exception đã thoát từ target sang native,
    // không có bảo đảm control quay lại đây.
}
```

Đây là snippet minh họa, không độc lập để compile. C `qsort` **không phải Java method**; sau khi C gọi function pointer tới upcall, lỗi Java vượt qua callback boundary có thể khiến JVM kết thúc trước khi `qsort.invokeExact` trở lại. Đặt `try/catch` **ở caller Java xung quanh downcall** không thay thế việc chặn lỗi **ngay trong target**.

Tương tự, Java `UncaughtExceptionHandler` của thread không phải cơ chế bảo vệ FFM upcall. Nó không thay đổi hợp đồng “target should not throw”, và không thể biến `Throwable` thành exception C mà thư viện hiểu.

## 7. Phương án thứ hai: `MethodHandles.catchException`

Khi callback là một `MethodHandle` đã có sẵn hoặc khó sửa source, ta có thể **bọc method handle** bằng combinator:

```java
MethodHandle safe = MethodHandles.catchException(
    rawTarget, Throwable.class, fallbackHandler);
```

`fallbackHandler` phải có chữ ký tương thích: **tham số đầu là `Throwable`**, các tham số tiếp theo tương ứng target khi cần; **kiểu trả về giống target**. Nếu target trả `int` thì handler phải trả `int`. Handler cũng **không được ném lỗi ra ngoài**.

### 7.1. Ví dụ độc lập: `CatchCombinatorCheck.java`

Chương trình này kiểm thử chính `MethodHandles.catchException` bằng Java thuần, **không gọi native**. Nó minh họa chính xác cách bind error box và bắt `Throwable`. Đối với upcall thật, đặt handle đã được bảo vệ làm target của `Linker.upcallStub`.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.concurrent.atomic.AtomicReference;

public class CatchCombinatorCheck {
    public static int raw(int x) {
        if (x < 0) throw new IllegalArgumentException("negative");
        return x * 2;
    }

    public static int fallback(Throwable error,
                               AtomicReference<Throwable> box,
                               int x) {
        box.compareAndSet(null, error);
        return -1;
    }

    public static void main(String[] args) throws Throwable {
        AtomicReference<Throwable> box = new AtomicReference<>();

        MethodHandle raw = MethodHandles.lookup().findStatic(
            CatchCombinatorCheck.class, "raw",
            MethodType.methodType(int.class, int.class));

        MethodHandle handler = MethodHandles.lookup().findStatic(
            CatchCombinatorCheck.class, "fallback",
            MethodType.methodType(int.class, Throwable.class,
                AtomicReference.class, int.class));

        // Handler: (Throwable, AtomicReference, int)int
        // After binding box: (Throwable, int)int
        handler = MethodHandles.insertArguments(handler, 1, box);

        MethodHandle safe = MethodHandles.catchException(
            raw, Throwable.class, handler);

        System.out.println("safe type: " + safe.type());
        System.out.println("success: " + (int) safe.invokeExact(4));
        System.out.println("failure code: " + (int) safe.invokeExact(-1));
        System.out.println("captured: "
            + box.get().getClass().getSimpleName());
    }
}
```

### 7.2. Chạy ví dụ combinator

```bash
javac -encoding UTF-8 CatchCombinatorCheck.java
java CatchCombinatorCheck
```

**Stdout đã kiểm chứng trên OpenJDK 24:**

```text
safe type: (int)int
success: 8
failure code: -1
captured: IllegalArgumentException
```

Để dùng `safe` làm upcall target, `FunctionDescriptor` cần phù hợp chữ ký `(int)int` của handle này. Trong qsort của mục 5, comparator nhận **hai pointers**, nên phải viết target/handler dạng `(MemorySegment,MemorySegment)int` và giữ các tham số cùng return ABI khi bọc.

**Giới hạn combinator:** nếu `fallbackHandler` tự ném exception (ví dụ logger gặp lỗi) hoặc một `filter`/adapter phía ngoài handle được bọc ném, exception vẫn có thể thoát. Vì vậy **wrap layer cuối cùng** thực sự đưa vào `upcallStub` và kiểm thử cả lỗi từ handler. Trong nhiều ứng dụng, một Java method `try/catch(Throwable)` tường minh như `safeCompare` dễ review và quản lý ownership hơn.

## 8. Thiết kế một error protocol phù hợp ABI thay vì ném Java exception

### 8.1. Callback có giá trị trả về là mã trạng thái

Một C API do ứng dụng kiểm soát có thể thiết kế:

```c
// 0 = success, nonzero = application-defined callback failure.
typedef int (*process_callback)(int value, void *user_data);
int for_each_value(process_callback cb, void *user_data);
```

Java callback có thể trả mã `-1` hoặc một mã khác theo **hợp đồng do C định nghĩa**, đồng thời ghi lỗi Java để xử lý sau. Nếu C hỗ trợ dừng ngay khi callback trả nonzero, nó sẽ không tiếp tục xử lý dữ liệu sai. Thiết kế này **tốt hơn `qsort`** khi bạn được quyền thiết kế API, bởi comparator `qsort` chỉ có ngữ nghĩa âm/0/dương và **không có channel báo lỗi**.

### 8.2. Comparator như `qsort` không có lỗi riêng

Nếu callback buộc phải trả `int` so sánh, không có “return Java exception” hợp lệ. Lựa chọn fallback (ví dụ `0`) chỉ là cách đảm bảo C tiếp tục trong trạng thái không có Java exception. Một khi lỗi xảy ra:

- `AtomicReference` ghi failure để Java biết.
- Comparator không làm thêm nghiệp vụ không cần thiết.
- Native algorithm có thể tiếp tục một số bước vì không có error code chuyên biệt.
- Sau `qsort` return, **discard kết quả và báo lỗi ở Java**.

Không nên đưa trạng thái sắp xếp sau lỗi vào cache, DB hoặc kết quả public như thể phép sort đã thành công. Đây là yêu cầu **tính toàn vẹn dữ liệu**, không chỉ ngăn crash JVM.

### 8.3. Callback `void`

Nếu signature C là `void (*callback)(...)`, upcall Java cũng phải trả `void`; **không được tự thêm tham số hoặc trả `int` chỉ vì muốn có error code**. Trong handler:

```java
// Snippet; errorBox là AtomicReference<Throwable> hợp lệ.
static void safeNotify(int value,
                       AtomicReference<Throwable> errorBox) {
    try {
        doWork(value);
    } catch (Throwable t) {
        errorBox.compareAndSet(null, t);
        // Không throw lại. Return void theo đúng C ABI.
    }
}
```

`doWork` là logic ứng dụng được định nghĩa riêng; snippet chỉ minh họa và **không phải file độc lập**. Nếu API C không hỗ trợ status code, dùng error state/out-param hoặc một cơ chế báo lỗi riêng; không tạo ra return value trái ABI.

### 8.4. Callback trả con trỏ `T*`

Nếu callback C yêu cầu return `char*`/`void*`, carrier Java tương ứng là `MemorySegment`. Một fallback có thể là `MemorySegment.NULL` **chỉ khi C contract chấp nhận NULL**. Nếu API yêu cầu non-null pointer, trả NULL vẫn có thể khiến C dereference và crash. Đồng thời không được trả pointer tới segment đã hết scope khi upcall hoàn tất. Nói cách khác, **phải thống nhất error protocol với native ABI; không có sentinel vạn năng**.

## 9. Lưu và đưa lỗi Java trở lại đúng thời điểm

### 9.1. Ưu tiên state theo từng lời gọi

Với synchronous native functions như `qsort`, một `AtomicReference<Throwable>` được tạo **riêng cho mỗi invocation** giúp tránh rò rỉ lỗi giữa các lần:

```java
AtomicReference<Throwable> failure = new AtomicReference<>();
// Bind failure vào callback MethodHandle.
nativeDowncall.invokeExact(...);
Throwable cause = failure.get();
if (cause != null) {
    throw new IllegalStateException("callback failed", cause);
}
```

Đoạn này là **pseudocode về control flow**, không phải chương trình độc lập vì `nativeDowncall` và danh sách tham số thay đổi theo API. Quan trọng: chỉ `throw` **sau khi chắc chắn native function không còn gọi callback đó**.

Nếu muốn retry, hãy tạo error box mới hoặc reset dưới giao thức không có callback đang chạy; không reuse một state có leftover failure.

### 9.2. Nếu C gọi callback trên thread khác

Native library có thể tự tạo C worker thread rồi gọi function pointer. Khi đó Java callback có thể chạy trên **thread khác thread Java đăng ký callback**:

- **Không giả định `ThreadLocal` của caller chứa lỗi từ callback thread.** `ThreadLocal` gắn theo thread; native-created thread khác sẽ không có cùng value.
- `AtomicReference` hoặc queue thread-safe phù hợp để báo lỗi xuyên luồng. Nếu cần thu thập nhiều exception, dùng queue giới hạn/cơ chế tránh cấp phát thiếu kiểm soát.
- Nếu native call **asynchronous**, lúc hàm register trả về chưa chắc callbacks đã hoàn tất; **không kiểm tra lỗi một lần ngay sau register rồi kết luận an toàn**.
- Cần giao thức unregister/shutdown, đợi callback count về zero hoặc join/callback completion signal; chỉ sau đó mới inspect failure và đóng upcall stub.
- Nếu nhiều callback đồng thời, phải quy định kết quả nào được ưu tiên: lỗi đầu tiên, lỗi nghiêm trọng nhất hay tất cả lỗi. `compareAndSet(null,t)` cố ý giữ lỗi đầu tiên.

### 9.3. Không giữ `Throwable` mãi trong native registry

`Throwable` có cause, stack trace và có thể tham chiếu tới objects/class loaders; giữ trong `AtomicReference` lâu không cần thiết có thể gây retention. Sau khi an toàn để xử lý lỗi, clear state theo lifecycle (hoặc loại bỏ toàn bộ holder của từng operation). Nếu native callback registration sống lâu, quy định giới hạn bộ nhớ, logging và chính sách gỡ đăng ký.

## 10. Những trường hợp `catch(Throwable)` vẫn chưa đủ

**Không được hứa rằng catch mọi Throwable ngăn được mọi JVM crash.** Nó chỉ chặn đường **Java exception propagation** qua upcall boundary khi logic handler thực sự hoạt động. Những sự cố khác:

| Loại sự cố | Vì sao `catch(Throwable)` không cứu được? |
| --- | --- |
| Sai `FunctionDescriptor` hoặc calling convention | C dùng ABI sai, đọc tham số sai/ghi stack sai; có thể crash không thành Java exception |
| Stub bị deallocate vì Arena đã đóng | C gọi vào con trỏ hàm đã hết hạn; lỗi native xảy ra trước khi Java callback chạy |
| Native C buffer bị overflow/invalid pointer | Vi phạm memory safety ở native, không nhất thiết ném Java `Throwable` |
| Handler `catch` ném exception mới | Lỗi mới lại có thể thoát qua upcall |
| `OutOfMemoryError`/`StackOverflowError` nghiêm trọng | Process/JVM có thể đã ở trạng thái không thể tiếp tục an toàn |
| Native C giữ callback pointer sau unregister/free | Use-after-free function pointer, không phải một Java exception |
| Callback return sai type/lifetime | C dereference pointer invalid hoặc hiểu return value sai |
| Deadlock/recursive upcall | Callback có thể khóa vào monitor/lock bị native thread giữ; catch không xử lý deadlock |

Đừng cố “thử nghiệm” bằng cách để uncaught exception vượt upcall trong process production. Dùng unit tests để gây exception **bên trong `try` và xác nhận handler chặn nó**, như demo `-7` ở mục 5.

### Error handling của handler phải đủ đơn giản

Có thể không an toàn khi viết:

```java
catch (Throwable t) {
    LOGGER.error("Callback failed: {}", complexObject.toString(), t);
    // Logger, formatter, toString, allocation hoặc lock đều có thể ném/lỗi.
    return 0;
}
```

Đây là minh họa **không khuyến nghị** cho FFM upcall. Thay vào đó, lưu `Throwable` vào trạng thái ổn định và log/format **sau native return**. `AtomicReference.compareAndSet(null,t)` là một primitive ít phức tạp hơn, nhưng bản thân chương trình vẫn phải bảo đảm holder hợp lệ và không có logic có thể ném nằm ngoài guard.

Nếu callback thực hiện cleanup, cần đảm bảo cleanup đó không phát lỗi ra ngoài. Thường nên quản lý resource ở **scope bao quanh downcall** trong Java, sau khi native call hoàn tất, thay vì thực hiện cleanup có thể ném trong callback.

## 11. Quản lý vòng đời của upcall stub và native registration

`Linker.upcallStub(target, descriptor, arena)` tạo function pointer gắn với **Arena**. Nếu arena đóng khi C còn dùng pointer đó, việc C gọi callback sau đó có thể gây crash. Cần phân biệt:

- **Synchronous callback (ví dụ `qsort`):** `try (Arena arena = Arena.ofConfined())` phù hợp khi native function trả về **sau** toàn bộ callbacks. Stub còn sống trong toàn bộ lời gọi, rồi arena đóng.
- **Asynchronous/registered callback:** `registerCallback(pointer)` có thể trả về trong lúc C vẫn giữ pointer. Cần arena sống **tới khi unregister** và tất cả in-flight callbacks kết thúc; `Arena.ofShared()` thường phù hợp hơn khi C có callbacks trên nhiều threads.
- **Confined arena:** nếu native code gọi callback/touch memory trên thread khác, cần đánh giá thread accessibility. Không mặc định confined arena phù hợp cho mọi native callback async.
- **Native library unload:** C không được gọi stub hoặc các downcall symbols sau khi backing library/registration bị unload; phải quản lý lifecycle hai phía.

Một shutdown protocol hợp lý:

```text
register pointer (stub + state) → nhận callbacks
           │
           ▼
ngừng nhận callbacks mới / unregister từ thư viện native
           │
           ▼
đợi tất cả in-flight callbacks hoàn tất
           │
           ▼
xử lý failure đã ghi nhận / giao Java result
           │
           ▼
đóng Arena và giải phóng upcall stub
```

**Không được đóng Arena trước bước unregister-and-drain**. `catch(Throwable)` không thể bảo vệ function pointer đã bị deallocate.

## 12. Native access flags, Java version và platform ABI

### JDK 22+

FFM đã finalized ở **JDK 22 (JEP 454)**. Để dùng `Linker.downcallHandle`, `Linker.upcallStub` và `AddressLayout.withTargetLayout`, phải có quyền native access đúng module:

```bash
java --enable-native-access=ALL-UNNAMED SafeQsortUpcallDemo
```

`ALL-UNNAMED` áp dụng cho code classpath, như demo. Với named module, dùng tên module tương ứng (ví dụ `--enable-native-access=com.example.ffm`). `--enable-native-access` **không** thay `--enable-preview` ở phiên bản FFM còn preview.

JDK 24 có thể phát compile-time warning nếu build với `javac -Xlint:all` vì các API restricted. Đó là vấn đề an toàn FFM, không phải vì exception handler đang bị sai. Bật native access cho process để không gặp restricted access warnings/denials trong runtime theo chính sách JDK đang chạy.

### JDK 21

FFM của **JDK 21 là Third Preview (JEP 442)**. Khi port source sang JDK 21, phải kiểm tra API signatures của release đó rồi compile/run với:

```bash
javac --enable-preview --release 21 SafeQsortUpcallDemo.java
java --enable-preview --enable-native-access=ALL-UNNAMED SafeQsortUpcallDemo
```

Hai lệnh trên minh họa **flag cần có** trên JDK 21; **không tuyên bố source ví dụ JDK 24 được kiểm thử trên JDK 21 hay bảo đảm source compile nguyên xi**. Từ JDK 22, chỉ vì FFM thì không cần preview flags nữa, nhưng native-access permissions vẫn phải xét.

### ABI và compiler

`qsort` dùng C `size_t`, còn callback nhận hai `const void*` và trả `int`. Trên các ABI **64-bit** của ví dụ, `size_t` là 8 byte nên `JAVA_LONG` phù hợp. Trên 32-bit phải thay descriptor. `C long` còn khác nhau giữa Windows x64 (LLP64) và Linux x86-64 (LP64), nên không suy kiểu từ tên `long` đơn thuần. Luôn đối chiếu **C header, OS/CPU ABI, alignment và calling convention**.

`Linker.defaultLookup()` không bảo đảm chứa mọi symbol trên mọi hệ; trong ví dụ trên Windows x64/OpenJDK24, `qsort` đã được tìm và dùng thành công. Nếu platform khác không cung cấp `qsort` trong default lookup, phải dùng `SymbolLookup.libraryLookup` tới thư viện C phù hợp, cấu hình đường dẫn và giữ thư viện loaded trong suốt lifetime có callback.

## 13. FFM upcall so với JNI exception boundary

JNI truyền thống và FFM upcall đều có **ranh giới Java ↔ native**, nhưng cơ chế khác nhau.

| Vấn đề | JNI | FFM upcall |
| --- | --- | --- |
| Java gọi native | `native` method có C/C++ entrypoint qua JNI | Java gọi C function qua `MethodHandle` downcall |
| Native gọi Java | `Call<Type>Method`, tạo pending Java exception nếu Java method throw | Native gọi C function pointer của `upcallStub` |
| Phát hiện Java exception | JNI có `ExceptionCheck`/`ExceptionOccurred` | **Không có cơ chế `ExceptionCheck` trong FFM upcall target như JNI** |
| Lỗi Java vượt native boundary | JNI lập trình viên kiểm tra/điều khiển pending exception theo contract | **Target upcall không được throw; JVM có thể kết thúc đột ngột** |
| Truyền lỗi an toàn | Dùng JNI pending Java exception đúng lúc native return | Bắt `Throwable` trong callback; trả ABI value; lưu lỗi và xử lý sau khi native call xong |

Không dùng các hàm `env->ExceptionCheck()` của JNI trong một callback viết hoàn toàn bằng FFM; FFM không truyền một `JNIEnv*` cho upcall Java target. Nếu thư viện C của bạn có cả JNI và FFM, mỗi đường vẫn phải tuân thủ hợp đồng riêng.

## 14. Checklist thiết kế an toàn

- [ ] Mọi target method handle thực sự đưa vào `Linker.upcallStub` **không để `Throwable` thoát**.
- [ ] Dùng `catch(Throwable)`, không chỉ `catch(Exception)`, nếu cần đảm bảo cả `Error` không vượt boundary.
- [ ] Toàn bộ logic có thể ném nằm trong vùng guard, kể cả đọc memory, validate, callback nghiệp vụ và adapters.
- [ ] Trong handler, lưu lỗi tối thiểu; **không ném lại**, không gọi logging/formatting dễ lỗi.
- [ ] Return type/value khớp C ABI; sentinel chỉ hợp lệ khi C API chấp nhận.
- [ ] Có kênh thông báo lỗi riêng (return status, out-param, atomic state, queue, Java future...) phù hợp native protocol.
- [ ] Với native synchronous function, **kiểm tra failure sau downcall và trước khi dùng result**.
- [ ] Với async callbacks, có unregister/drain/join trước khi đọc kết quả cuối và đóng Arena.
- [ ] Sử dụng error holder riêng theo invocation/registration; tránh mutable global state dùng lẫn giữa callbacks.
- [ ] FFM `FunctionDescriptor` và `MethodType` khớp từng carrier/ABI; kiểm tra kích thước C `int`, `size_t` và pointer.
- [ ] Giữ stub, arena và native library sống khi C còn giữ function pointer.
- [ ] Không coi `catch(Throwable)` là biện pháp chống native memory corruption, ABI mismatch hoặc lỗi JVM nghiêm trọng.
- [ ] Test đường thành công, Java exception bình thường, `Error` có kiểm soát, fallback, một số callbacks tiếp theo, cleanup và failure propagation.

## 15. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Giải pháp |
| --- | --- | --- |
| JVM kết thúc khi Java comparator throw | `Throwable` đi ra khỏi upcall target | Bọc target với `try/catch(Throwable)` hoặc `MethodHandles.catchException` đúng cách |
| `catch(RuntimeException)` không chặn `AssertionError` | Chỉ bắt subtype, không bao cả `Error` | Sử dụng `catch(Throwable)` ở boundary |
| Upcall handler bắt lỗi xong lại crash | Logger/formatter/cleanup trong `catch` ném tiếp | Tối giản handler; ghi state rồi return |
| Lỗi xảy ra nhưng Java vẫn dùng kết quả sort | Fallback trả `0` làm qsort tiếp tục, kết quả không còn đáng tin | Đọc error box sau downcall; **discard** data và báo lỗi |
| `IllegalArgumentException` khi tạo stub | MethodType khác FunctionDescriptor hoặc descriptor không hỗ trợ | Kiểm tra exact parameter/return carriers và thứ tự `insertArguments` |
| Callback đọc pointer gặp `IndexOutOfBoundsException` | Con trỏ upcall default zero-length | Dùng target layout đúng ABI khi thực sự biết object size |
| Crash sau khi register callback | Arena chứa stub bị đóng sớm | Giữ Arena/stub đến khi unregister + drain callbacks |
| `WrongThreadException` khi callback | Dùng confined resources ở thread không được phép | Thiết kế shared resources và hợp đồng thread phù hợp |
| Không thấy lỗi trong Java caller | Callback trên thread khác, dùng `ThreadLocal` sai | Dùng state thread-safe và completion signal |
| C callback trả kiểu sai | Return ABI không tương thích | Chọn sentinel/status theo C signature, không trả Throwable |
| Crash dù đã bắt Throwable | Native memory bug, wrong calling convention, invalid pointer | Rà soát ABI/ownership, dùng native diagnostics/sanitizers |
| Bật `--enable-preview` mà vẫn có native-access warning | Preview không cấp restricted permission | Dùng `--enable-native-access` cho module cần native access |

## 16. Bài tập tự luyện

1. Vì sao `catch(Exception)` chưa đủ trong FFM upcall target? `catch(Throwable)` chặn thêm những nhóm lỗi nào?
2. Điều gì xảy ra theo hợp đồng `Linker.upcallStub` nếu Java target ném exception thoát ra ngoài? Có thể dựa vào `try/catch` ở Java downcall caller để cứu được không?
3. Trong `SafeQsortUpcallDemo`, tại sao `safeCompare` ghi vào `AtomicReference` rồi trả `0` thay vì ném lại `IllegalArgumentException`?
4. Sau khi callback trả sentinel `0`, có nên tin kết quả `qsort` không? Vì sao cần kiểm tra failure sau native return?
5. Vì sao phải `insertArguments(target,2,failure)` trước khi tạo upcall stub? Target cuối có `MethodType` nào?
6. Nếu C callback signature là `void (*cb)(int)`, Java có được tự đổi return thành `int` để báo lỗi không?
7. Khi native API chạy async và gọi callback từ C worker thread, vì sao `ThreadLocal` của Java caller không phù hợp làm failure box?
8. `MethodHandles.catchException` khác wrapper `try/catch(Throwable)` ở điểm nào? Điều gì xảy ra nếu handler của combinator tự ném?
9. Vì sao Arena cần sống đến khi native library chắc chắn không còn dùng function pointer?
10. Những lỗi nào có thể crash JVM mà `catch(Throwable)` **không** giải quyết được?
11. Nếu cần giữ nhiều lỗi từ nhiều callbacks, nên định nghĩa chính sách chọn lỗi đầu tiên hay tập hợp lỗi như thế nào?
12. Với Java 21 preview và Java 24 finalized FFM, khác nhau thế nào ở runtime flags?

**Ghi nhớ:** Tại **FFM upcall boundary**, luôn coi Java callback là hàm **không được phép ném**. Catch **`Throwable`** ngay trong target, ghi nhận lỗi bằng cơ chế có ownership rõ, **trả đúng ABI**, rồi xử lý/throw ở Java code **sau khi native call đã hoàn tất**. Đừng kỳ vọng native library C sẽ bắt `Throwable` thay Java.

### Tài liệu chính thức

- [Oracle JDK 24 — Linker.upcallStub: target must not throw, otherwise JVM terminates](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.html).
- [Oracle JDK 22 — Linker và FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).
- [Oracle JDK 24 — MethodHandles.catchException](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/MethodHandles.html).
- [Dev.java — How to Handle a Call from Native Code Back to Java Code (FFM Upcalls)](https://dev.java/learn/api/io/ffm/upcall/).
- [Oracle JDK 24 — Restricted Methods và quyền native access](https://docs.oracle.com/en/java/javase/24/core/restricted-methods.html).
- [OpenJDK JEP 454 — FFM Final API](https://openjdk.org/jeps/454).
- [OpenJDK JEP 442 — FFM Third Preview](https://openjdk.org/jeps/442).
