# Thiết kế AutoCloseable phía Java với trạng thái đã đóng rõ ràng khi bao bọc thư viện C++

## Mục tiêu học tập

Khi một ứng dụng Java sử dụng thư viện C++, Java có thể giữ một **native handle** trỏ tới một đối tượng được cấp phát bằng C++ `new`, factory function hoặc cơ chế allocator riêng. **Java garbage collector không tự biết cách gọi destructor C++** và không thể suy ra khi nào một handle C++ phải được giải phóng. Vì vậy wrapper phía Java cần một **hợp đồng sở hữu và vòng đời rõ ràng**: tạo tài nguyên, dùng tài nguyên, đóng **đúng một lần**, và từ chối mọi thao tác sau đóng.

`AutoCloseable` cùng `try-with-resources` cung cấp giao diện đóng tài nguyên quen thuộc với Java. Tuy nhiên, chỉ thêm `implements AutoCloseable` **không tự bảo đảm** native pointer an toàn. Wrapper phải có **trạng thái đã đóng hiển thị được**, chặn **use-after-close**, tránh **double-free**, kiểm soát thao tác đồng thời giữa `get` và `close`, và xử lý đường lỗi của native destructor phù hợp.

Bạn sẽ học:

- Phân biệt Java reference, native pointer/handle, **owner** và **borrower**.
- Thiết kế state machine `OPEN → CLOSED` (hoặc `OPEN → CLOSING → CLOSED` trong hệ phức tạp), với `isClosed()` và lỗi `IllegalStateException`.
- Tạo `close()` **idempotent theo hợp đồng wrapper** dù `AutoCloseable` không bắt buộc tất cả implementation phải idempotent.
- Đặt `synchronized` hoặc một lock chung quanh **cả kiểm tra trạng thái, native call và release** nhằm tránh race gây use-after-free.
- Tạo C ABI façade cho C++ opaque object, rồi viết wrapper Java bằng FFM (JDK 22+) hoặc theo nguyên tắc tương tự với JNI.
- Sử dụng `try-with-resources`, phân biệt native resource lifetime với Java `Arena`, và chọn chính sách phù hợp khi destructor không thể báo thành công chắc chắn.
- Kiểm thử close lặp, use-after-close, concurrent close, lỗi khởi tạo và callback/async resource retention.

Bài có **một ví dụ Java 17+ độc lập** dùng native bridge giả lập, đã chạy trên JDK 24, và **một minh họa thực tế C++/Java FFM** cho Linux x64 (C++ part được review tĩnh, không khẳng định native binary đã được thực thi).

## 1. Vấn đề: Java object vẫn sống nhưng đối tượng C++ có thể đã bị delete

Một wrapper đơn giản thường giữ:

~~~text
Java heap                                   Native heap (C++)
+--------------------------------+           +----------------------+
| NativeCounter Java wrapper     |           | CounterHandle       |
| - handle: MemorySegment/long --+---------->| value = 7            |
| - closed: boolean              |           | native allocation    |
+--------------------------------+           +----------------------+

Java wrapper còn được tham chiếu  ≠  C++ allocation chắc còn tồn tại.
C++ allocation bị delete        ≠  Java wrapper tự biến thành null.
~~~

Nếu mã khác gọi native `delete` mà wrapper không biết, Java vẫn giữ giá trị pointer **dangling**. Ngược lại, nếu Java wrapper không gọi destructor dù không còn dùng nữa, tài nguyên C++ có thể **rò rỉ** cho tới khi tiến trình kết thúc.

Với C++:

~~~cpp
CounterHandle* h = counter_create(7);
int32_t v = 0;
counter_get(h, &v);  // hợp lệ khi h còn sống
counter_destroy(h);  // free một lần
// counter_get(h, &v);  // use-after-free: không được gọi
// counter_destroy(h);  // double-free: không được gọi
~~~

Đây là snippet minh họa dùng một **C ABI façade** được định nghĩa đầy đủ ở các mục sau; chưa phải chương trình C++ độc lập. Sau `destroy`, giá trị bit của `h` có thể vẫn khác 0, nhưng điều đó **không** làm pointer hợp lệ.

Vì vậy phía Java phải **theo dõi trạng thái bằng dữ liệu riêng**, không dựa vào GC hoặc phép so sánh địa chỉ.

## 2. Xác định ownership trước khi viết `close()`

Ba mô hình thường gặp:

| Mô hình | Ai cấp/tạo? | Ai phải hủy? | Java wrapper được `close()` gì? |
| --- | --- | --- | --- |
| **Owned handle** | Factory native tạo một resource mới và chuyển ownership cho Java | Java wrapper | Gọi destructor/deallocator đúng **một lần** |
| **Borrowed handle** | Native library hoặc owner khác đang giữ resource | Owner gốc | Chỉ kết thúc quyền truy cập của wrapper nếu hợp đồng cho phép; **không tự delete** resource |
| **Shared/ref-counted handle** | Native API cấp shared ownership và có `retain/release` | Mỗi owner giữ một reference count | Gọi **`release` một lần** cho ownership share của mình, không nhất thiết gọi `delete` trực tiếp |

Một Java class có `close()` gọi `delete` **chỉ đúng** khi nó sở hữu đối tượng native theo hợp đồng C++. Nếu C++ trả pointer vào một singleton, vùng nằm trong container hoặc subobject của một object khác, gọi delete có thể phá dữ liệu hoặc gây crash.

**Quy tắc thiết kế:** mỗi wrapper owned có **một chủ quyền release duy nhất**. Không tạo hai Java wrappers đều “own” cùng một raw handle nếu native library không có cơ chế reference counting. Nếu cần nhiều views trên một resource, dùng một owner và cấp **borrowed views** có lifetime ràng buộc, hoặc một native retain/release protocol.

### Ví dụ factory ownership

~~~text
native counter_create(7)
   |
   +--> trả CounterHandle* hợp lệ và chuyển ownership tới Java
          |
          v
   new NativeCounter(handle) -> State OPEN
          |
          +--> get()/operation() nhiều lần khi OPEN
          |
          +--> close() đúng một lần -> counter_destroy(handle)
                                      State CLOSED
          |
          +--> close() tiếp theo = no-op
          +--> get() tiếp theo = IllegalStateException
~~~

Đây là một hợp đồng **được lựa chọn và triển khai rõ**, không phải tính năng tự có của mọi C++ library.

## 3. `AutoCloseable` và `try-with-resources` làm gì, không làm gì?

`AutoCloseable` có một phương thức:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

Interface `AutoCloseable` là chuẩn Java từ Java 7. `try-with-resources` tự gọi `close()` khi rời khối, kể cả khi body ném exception.

~~~java
try (NativeCounter c = new NativeCounter(7)) {
    System.out.println(c.value());
} // c.close() được gọi dù body return/throw.
~~~

Ví dụ giả định class `NativeCounter` triển khai `AutoCloseable` như phần thực hành phía dưới.

**Điều `AutoCloseable` không tự bảo đảm:**

- Interface **không bắt buộc** mọi implementation phải idempotent; nhưng wrapper giải phóng C++ resource nên **nên chủ động triển khai close lặp thành no-op**.
- Không tạo `closed` flag, không xóa native handle, không gọi C++ destructor tự động.
- Không đồng bộ giữa một thread đang dùng pointer và thread khác đang close.
- Không biết C++ handle có phải owned hay borrowed.
- Không sửa được sai C++ allocator hay exception vượt qua C ABI.
- Không bảo vệ khỏi native library tự phá resource bên ngoài hợp đồng.

Bạn có thể override `close()` thành phương thức **không khai báo checked exception**:

~~~java
@Override
public void close() {
    // Chính wrapper thực hiện release.
}
~~~

Cách này giúp việc dùng wrapper không buộc caller catch `Exception` chung của interface. Nếu native release có thể báo lỗi, hãy định nghĩa một exception policy rõ (ví dụ unchecked `IllegalStateException` hoặc một custom exception phù hợp), đồng thời tránh retry không an toàn.

### Vì sao thường chọn `IllegalStateException` cho thao tác sau đóng?

Sau `close()`, `value()` không bị lỗi vì Java argument xấu; lỗi nằm ở **vòng đời của object**. `IllegalStateException("Counter is closed")` thể hiện rõ hợp đồng: object đã chấm dứt quyền gọi native.

Không trả giá trị mặc định như 0 để che use-after-close, vì 0 có thể là kết quả C++ hợp lệ và lỗi sẽ lây sang dữ liệu nghiệp vụ.

## 4. State machine tối thiểu: OPEN, CLOSED

Để Java wrapper thể hiện trạng thái rõ:

~~~text
                tạo native resource thành công
          +-----------------------------------------+
          |                                         v
    CONSTRUCTING                                OPEN
          |                                      |
          | nếu create lỗi: không publish         | close() lần đầu
          | wrapper owned                          v
          +--> constructor throws              CLOSED
                                                  |
                                     close() lần 2: no-op
                                     operation(): fail-fast
~~~

Trong cấu trúc đơn giản, dùng **`boolean closed`** và **handle không-null khi OPEN** là đủ. Không cần một enum phức tạp nếu close/destructor đồng bộ, không tái mở và native release không yêu cầu bước bất đồng bộ.

Những **bất biến (invariants)** quan trọng:

1. **OPEN:** `closed == false` và handle native đang thuộc wrapper, không phải null pointer theo contract.
2. **CLOSED:** `closed == true` và wrapper không bao giờ gọi native function với handle cũ.
3. **Close idempotent:** một wrapper owned chỉ phát hành tối đa **một lần** lời gọi destructor; lần close tiếp theo là no-op.
4. **Không reopen:** không gán handle mới vào wrapper đã CLOSED. Muốn resource khác, tạo **wrapper mới**.
5. **Không raw pointer escape:** API công khai không trả `long address`/`MemorySegment handle` để client có thể bypass `closed` guard.
6. **Đồng bộ:** mọi operation và close phải kiểm/đổi trạng thái theo cùng một cơ chế bảo vệ concurrency.

Có thể có state `CLOSING` nếu native cleanup mất thời gian, có callback, reference counting, cancellation hoặc failure cần ghi nhận. Tuy nhiên **không tự đưa thêm trạng thái phức tạp** nếu một lock + close đồng bộ đủ giải quyết.

### Tại sao không chỉ xét `handle != 0`?

Bạn có thể chọn `0` là sentinel cho null C pointer, nhưng nếu:

- native resource được giải phóng nhưng biến handle vẫn giữ địa chỉ cũ;
- library có handle IDs mà số 0 không nhất thiết là invalid;
- native close trả lỗi và chưa rõ tài nguyên đã release hay chưa;

thì phép kiểm chỉ trên số handle không phản ánh đầy đủ lifecycle. Dùng **`closed` làm nguồn sự thật** cho quyền truy cập Java, đồng thời đặt handle về sentinel hợp lệ để giảm nguy cơ vô tình dùng pointer cũ. Null/sentinel phải phù hợp hợp đồng cụ thể.

## 5. Thiết kế Java wrapper đúng: chặn dùng sau đóng và close lặp

Một phiên bản mô phỏng **chưa cần JNI/FFM**:

~~~java
public final class Counter implements AutoCloseable {
    private long handle;      // ID giả lập ở ví dụ này, không phải raw C pointer.
    private boolean closed;

    public Counter(int initial) {
        this.handle = FakeBridge.create(initial);
    }

    private void requireOpen() {
        if (closed) {
            throw new IllegalStateException("Counter is closed");
        }
    }

    public synchronized int value() {
        requireOpen();
        return FakeBridge.read(handle);
    }

    public synchronized boolean isClosed() {
        return closed;
    }

    @Override
    public synchronized void close() {
        if (closed) return;
        closed = true;
        long oldHandle = handle;
        handle = 0L;
        FakeBridge.destroy(oldHandle);
    }
}
~~~

Đây là **trích đoạn minh họa** nằm trong class giả lập `LifecycleLab` được cung cấp đầy đủ ở mục 10, không nên copy riêng và chạy khi chưa có `FakeBridge`.

Mỗi chi tiết có chủ đích:

- `final class` tránh subclass ghi đè `close` hoặc gọi native qua nhánh không guard.
- `handle` là private; client không thể tự gửi pointer cũ qua bridge.
- `closed` được đọc bằng `requireOpen` trước khi gọi native.
- `value` và `close` cùng `synchronized` trên **một Java monitor** nên thao tác không thể xen kẽ nhau trên **cùng wrapper**.
- `close` đặt `closed = true` trước khi gọi release để ngăn một lần close khác giải phóng trùng ngay cả khi release thất bại. Handle được thay sentinel.
- `isClosed` là một API quan sát được; nó không thay thế `requireOpen` trong chính các thao tác, vì giữa lúc client gọi `isClosed()` và `value()` một thread khác có thể close.
- `FakeBridge.destroy` chỉ xuất hiện một lần trong đường OPEN → CLOSED.

### Tại sao thứ tự trong `close` quan trọng?

Phản ví dụ:

~~~java
// KHÔNG làm thế:
public synchronized void closeBad() {
    FakeBridge.destroy(handle);
    closed = true;
}
~~~

Trong trường hợp destructor ném exception, `closed` vẫn false. Caller retry `closeBad()` có thể destroy một resource đã free một phần hoặc free hoàn toàn, dẫn tới **double-free**. Ngoài ra không có guard ở đầu nên lặp close có thể gọi destructor lần nữa.

Cách tốt hơn cho destructor **không thể rollback/retry an toàn** là invalid hóa quyền dùng **trước** khi gọi native release. Nếu release báo lỗi, trạng thái Java vẫn là CLOSED, nhưng phải ghi lại **có thể còn native leak/unknown release status**; không được báo release chắc chắn thành công chỉ vì closed=true.

## 6. Race nguy hiểm: kiểm closed rồi call native ở thread khác

Một mẫu nhìn có vẻ đúng nhưng **không an toàn**:

~~~java
// KHÔNG đủ an toàn nếu close có thể chạy trên thread khác.
public int valueBad() {
    if (closed) throw new IllegalStateException("closed");
    return NativeBridge.get(handle);
}

@Override
public void closeBad() {
    if (!closed) {
        NativeBridge.destroy(handle);
        closed = true;
    }
}
~~~

Có thể xảy ra interleaving:

~~~text
Thread A                                  Thread B
--------                                  --------
if (!closed)  -> true
                                         if (!closed) -> true
                                         destroy(handle)
                                         closed = true
NativeBridge.get(handle)  // USE AFTER FREE
~~~

**Thêm `volatile boolean closed` chỉ cải thiện visibility**, không biến `if (!closed) → native call` thành một thao tác nguyên tử. `AtomicBoolean.compareAndSet` chỉ ngăn **hai close** cùng thắng; nó **không ngăn một operation đang chạy** đồng thời với destroy.

### Cách đơn giản: giữ cùng một lock suốt native call

~~~java
public synchronized int value() {
    requireOpen();
    return NativeBridge.get(handle);
}

@Override
public synchronized void close() {
    if (closed) return;
    closed = true;
    long old = handle;
    handle = 0L;
    NativeBridge.destroy(old);
}
~~~

Đây là snippet, giả định `NativeBridge` có các hàm như trên. Nếu thread A đã vào `value` thì thread B đợi monitor trước khi close; nếu B close trước thì A vào sau và bị `IllegalStateException`. **Không có đường gọi native bằng handle đã bị wrapper release** trong hai thao tác này.

Một lock chung còn đảm bảo visibility của `handle` và `closed` giữa threads đi qua synchronized methods. `isClosed()` cũng synchronized để tránh đọc state không được đồng bộ.

**Điều kiện:** lock giải quyết concurrency của **wrapper này**. Nếu một API khác giữ cùng native handle và gọi destroy bên ngoài wrapper, lock Java không cứu được. Cần phối hợp ownership ở cấp toàn hệ thống.

### Khi `synchronized` không đủ hoặc không phù hợp

Nếu native function gọi ngược vào Java (callbacks), có thể block lâu, có thread affinity hoặc giữ lock gây deadlock, không nên giữ intrinsic lock xuyên qua một native call không kiểm soát được mà không đánh giá. Khi đó cần mô hình:

- State `OPEN / CLOSING / CLOSED` có lock rõ ràng.
- Counter `inFlightOperations`; chỉ release khi không còn operation đang chạy.
- `close` ngăn operation mới, chờ in-flight hoàn thành hoặc cancel theo contract.
- Không chờ native worker khi vẫn giữ lock mà callback cần lấy lại.
- Native pointer chỉ thực sự free sau khi mọi bên có quyền sử dụng đã hoàn tất.

Đây là một **thiết kế nâng cao**; bài này dùng lock đơn giản vì native `counter_get` là một hàm ngắn, đồng bộ, không callback và không giữ resource sau khi trả về.

## 7. C++ façade: không xuất ABI class trực tiếp sang Java

Trong C++, RAII sử dụng constructor/destructor, nhưng **C++ class ABI có name mangling, overloads và exception semantics phụ thuộc toolchain**. Để Java FFM hoặc JNI giao tiếp ổn định, nên xuất **C ABI functions** nhận opaque pointer:

~~~text
Java NativeCounter                      C ABI façade               C++ object
------------------                      ------------               ----------
new NativeCounter(7) ─── counter_create(7) ──────────────> new CounterHandle
value() ──────────────── counter_get(handle,&out) ────────> đọc value
close() ──────────────── counter_destroy(handle) ────────> delete CounterHandle
~~~

C ABI façade phải nói rõ:

- `counter_create` trả **owned** pointer hoặc null khi tạo thất bại.
- `counter_get` chỉ đọc, không giữ out pointer lại sau return; trả status 0 thành công, nonzero khi input sai.
- `counter_destroy` nhận owned pointer và giải phóng **một lần**. Caller tuyệt đối không dùng handle sau khi destroy.
- C++ exceptions **không** được thoát qua C/FFM/JNI ABI; có status/error contract và destructor bảo đảm không ném.
- Tất cả function signatures, pointer types, encoding và `int32_t` phải phù hợp native ABI.

### 7.1. Header C/C++: `demo_counter.h`

~~~c
#ifndef DEMO_COUNTER_H
#define DEMO_COUNTER_H

#include <stdint.h>

#ifdef __cplusplus
#define DEMO_NOEXCEPT noexcept
extern "C" {
#else
#define DEMO_NOEXCEPT
#endif

typedef struct CounterHandle CounterHandle;

/* Trả owned CounterHandle*, NULL nếu không cấp phát được. */
CounterHandle *counter_create(int32_t initial) DEMO_NOEXCEPT;

/* Trả 0 khi OK; -1 khi handle/out không hợp lệ. */
int counter_get(const CounterHandle *handle,
                int32_t *out_value) DEMO_NOEXCEPT;

/* Caller owner phải gọi tối đa một lần trên từng handle còn sống. */
void counter_destroy(CounterHandle *handle) DEMO_NOEXCEPT;

#ifdef __cplusplus
}
#endif
#undef DEMO_NOEXCEPT

#endif
~~~

**`CounterHandle` là opaque type** đối với C/Java. Header không cần công bố fields; Java chỉ trao một pointer lại cho façade. `extern "C"` tắt C++ name mangling cho các hàm exported. Macro `DEMO_NOEXCEPT` cho phép header **đọc được bằng cả C compiler lẫn C++ compiler** mà C++ declarations vẫn có exception specification khớp implementation.

### 7.2. Implementation C++: `demo_counter.cpp`

~~~cpp
#include "demo_counter.h"
#include <new>

struct CounterHandle {
    int32_t value;
};

extern "C" CounterHandle *counter_create(int32_t initial) noexcept {
    // Trivial aggregate constructor; nothrow new trả nullptr khi OOM.
    return new (std::nothrow) CounterHandle{initial};
}

extern "C" int counter_get(const CounterHandle *handle,
                           int32_t *out_value) noexcept {
    if (handle == nullptr || out_value == nullptr) {
        return -1;
    }
    *out_value = handle->value;
    return 0;
}

extern "C" void counter_destroy(CounterHandle *handle) noexcept {
    delete handle;
}
~~~

Đây là implementation đủ cho ba API declared trong header, nhắm tới C++17 và ABI thông dụng có `int32_t` là 32-bit. `CounterHandle` chỉ chứa một integer với destructor trivial; không có C++ exception được ném trong hai thao tác get/destroy. Factory dùng `std::nothrow`.

**Không diễn giải `noexcept` như giải pháp cho mọi lỗi C++:** nếu destructor thật sự ném khi được khai báo `noexcept`, C++ có thể gọi `std::terminate`. Một thư viện production nên thiết kế destructor không ném, chuyển lỗi recoverable sang API status/release chuyên dụng, và kiểm ownership/allocator từ đầu. Truyền pointer dangling vào `counter_get` hoặc double-delete vẫn là **undefined behavior**, dù hàm có null check và `noexcept`.

### 7.3. Build native library Linux

Đặt `demo_counter.h` và `demo_counter.cpp` cùng thư mục, dùng compiler C++17:

~~~bash
g++ -std=c++17 -Wall -Wextra -Werror -fPIC -shared \
    demo_counter.cpp -o libdemo_counter.so
~~~

Tên `libdemo_counter.so` khớp `System.loadLibrary("demo_counter")` trên Linux. Đây là **lệnh mẫu Linux**, không dùng nguyên cho Windows/macOS; tên `.dll`/`.dylib`, export attributes và flags linker khác nhau. Đối với Windows DLL, có thể cần `__declspec(dllexport)` trên các symbols.

**Giới hạn kiểm thử:** phần C++ không được native-compile trên môi trường chỉ có Java JDK 24 mà thiếu `g++`/`clang++`. Những stdout sau đây là kỳ vọng theo contract khi build và load đúng native binary.

## 8. Wrapper Java thật bằng FFM: rõ ownership và trạng thái CLOSED

FFM dùng `Linker`, `SymbolLookup` và `MethodHandle` để gọi C ABI mà không phải tự viết JNI glue. Ví dụ này yêu cầu **JDK 22+**, đã kiểm tra **cú pháp Java trên JDK 24**; không tuyên bố đã chạy end-to-end với C++ library trong môi trường thiếu compiler.

Tạo tệp `NativeCounter.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;

public final class NativeCounter implements AutoCloseable {
    private static final MethodHandle CREATE;
    private static final MethodHandle GET;
    private static final MethodHandle DESTROY;

    static {
        System.loadLibrary("demo_counter");

        Linker linker = Linker.nativeLinker();
        SymbolLookup lookup = SymbolLookup.loaderLookup();

        CREATE = linker.downcallHandle(
                lookup.findOrThrow("counter_create"),
                FunctionDescriptor.of(
                        ValueLayout.ADDRESS, ValueLayout.JAVA_INT));

        GET = linker.downcallHandle(
                lookup.findOrThrow("counter_get"),
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT,
                        ValueLayout.ADDRESS, ValueLayout.ADDRESS));

        DESTROY = linker.downcallHandle(
                lookup.findOrThrow("counter_destroy"),
                FunctionDescriptor.ofVoid(ValueLayout.ADDRESS));
    }

    // Handle owned. Không expose ra bên ngoài.
    private MemorySegment handle;
    private boolean closed;

    public NativeCounter(int initial) {
        try {
            MemorySegment ptr =
                    (MemorySegment) CREATE.invokeExact(initial);
            if (ptr.address() == 0L) {
                throw new IllegalStateException(
                        "counter_create returned NULL");
            }
            handle = ptr;
            // Khi constructor thành công: closed mặc định false.
        } catch (RuntimeException | Error e) {
            throw e;
        } catch (Throwable t) {
            throw new IllegalStateException(
                    "create invocation failed", t);
        }
    }

    private void requireOpen() {
        if (closed) {
            throw new IllegalStateException("Counter is closed");
        }
    }

    public synchronized int value() {
        requireOpen();

        // out_value là native buffer tạm chỉ cần sống trong lời gọi này.
        try (Arena scratch = Arena.ofConfined()) {
            MemorySegment out = scratch.allocate(ValueLayout.JAVA_INT);

            int status = (int) GET.invokeExact(handle, out);
            if (status != 0) {
                throw new IllegalStateException(
                        "counter_get status=" + status);
            }
            return out.get(ValueLayout.JAVA_INT, 0);
        } catch (RuntimeException | Error e) {
            throw e;
        } catch (Throwable t) {
            throw new IllegalStateException(
                    "get invocation failed", t);
        }
    }

    public synchronized boolean isClosed() {
        return closed;
    }

    @Override
    public synchronized void close() {
        if (closed) {
            return;
        }

        // Ngăn mọi use/release tiếp theo trước khi gọi native.
        closed = true;
        MemorySegment toDestroy = handle;
        handle = MemorySegment.NULL;

        try {
            DESTROY.invokeExact(toDestroy);
        } catch (Throwable t) {
            // Không retry khi không biết native resource đã free chưa.
            throw new IllegalStateException(
                    "destroy failed; handle invalidated", t);
        }
    }
}
~~~

### Vì sao mã này đúng hợp đồng?

**(1) Khởi tạo:** `CREATE` là FFM downcall tới `counter_create(int32_t)`. C trả pointer dưới dạng `MemorySegment`. Khi address 0, constructor thất bại và không publish wrapper OPEN. Không được gọi `counter_destroy` trên invalid null handle để chữa lỗi tạo.

**(2) Get:** `GET` nhận hai `ADDRESS` arguments: owned `handle` và địa chỉ `out` cho `int32_t*`. `Arena.ofConfined()` chỉ quản lý **buffer tạm `out`**, không phải C++ object được tạo bởi `counter_create`.

**(3) Close:** native C++ object được giải phóng **chỉ** bằng `counter_destroy`. `Arena.close()` của buffer tạm không có quyền/khả năng delete object C++ đó.

**(4) Guard:** `requireOpen()` chạy trong `synchronized value()`, còn `close()` cùng monitor. Không có interleaving giữa native `counter_get` và `counter_destroy` trong cùng wrapper.

**(5) Trạng thái rõ ràng:** `isClosed()` trả boolean. `close()` lần 2 no-op. Sau close, `value()` lập tức ném `IllegalStateException` **trước khi gọi C++**.

**(6) FFM loading:** `System.loadLibrary` nạp library vào class loader; `SymbolLookup.loaderLookup()` tra cứu symbols của libraries đã nạp vào class loader này, phù hợp tài liệu JDK 24. `Linker.downcallHandle` cần native-access permission vì là restricted FFM API.

**(7) Signature:** `int32_t` được map sang `JAVA_INT` cho ABI Linux x64 trong ví dụ, pointer sang `ADDRESS`. Phải kiểm ABI thật và signature C khi port. `invokeExact` bắt buộc Java carrier types khớp; không tùy tiện cast `MemorySegment` thành `long`.

**(8) Lỗi release:** ví dụ native destructor đơn giản không có trạng thái lỗi recoverable. Nếu lời gọi Java FFM `DESTROY` gặp Throwable, Java state vẫn CLOSED và thông báo “handle invalidated”; **không tuyên bố native resource chắc đã được free**. Cần điều tra lỗi, không retry blindly để tránh double-free.

### Những gì ví dụ không tự giải quyết

- C++ library có thể giữ pointer ở thread/callback khác và destroy ngoài wrapper: điều này **vi phạm ownership giả định**.
- Nếu `counter_get` nội bộ tự gọi Java callback, Java monitor có thể tham gia deadlock; code cần thiết kế lại cho trường hợp ấy.
- Nếu native resource yêu cầu creator-thread affinity, `synchronized` không đủ: nó khóa concurrency nhưng không cố định thread thực thi.
- Nếu bạn cần release thất bại có thể retry, native C ABI phải **định nghĩa rõ** khi lỗi handle còn thuộc ai và có bị free một phần hay không; state machine sẽ khác.
- `MemorySegment.NULL` gán vào field chỉ xóa pointer Java wrapper; nó **không delete** native allocation. Phần thực hiện release là `counter_destroy`.

## 9. Client Java dùng `try-with-resources` và kết quả kỳ vọng

Tạo tệp `CounterApp.java`:

~~~java
public final class CounterApp {
    public static void main(String[] args) {
        NativeCounter c = new NativeCounter(7);

        try (c) {
            System.out.println("value=" + c.value());
            System.out.println("closed-in-scope=" + c.isClosed());
        }

        // close() lặp là no-op theo hợp đồng wrapper.
        c.close();
        System.out.println("closed-after=" + c.isClosed());

        try {
            c.value();
        } catch (IllegalStateException expected) {
            System.out.println("use-after-close="
                    + expected.getClass().getSimpleName());
        }
    }
}
~~~

Đây là client độc lập nếu các tệp `NativeCounter.java`, `CounterApp.java` và native shared library đã được build.

Trên Linux:

~~~bash
javac -encoding UTF-8 NativeCounter.java CounterApp.java
java --enable-native-access=ALL-UNNAMED \
     -Djava.library.path=. CounterApp
~~~

**Stdout kỳ vọng** nếu Linux library build đúng và C++ ABI khớp:

~~~text
value=7
closed-in-scope=false
closed-after=true
use-after-close=IllegalStateException
~~~

Đầu ra không in native memory address (phụ thuộc allocator và ASLR). Một test production nên thêm **native instrumentation** để xác nhận đúng một lần `counter_destroy`, chứ không chỉ dựa vào việc Java `close()` không ném.

**Quan trọng:** Đây là kết quả logic kỳ vọng của ví dụ C++/FFM đầy đủ, **chưa phải stdout end-to-end đã quan sát ở môi trường thiếu C++ compiler**. Một bài thực hành Java thuần đã chạy thật nằm ngay sau đây.

## 10. Bài lab Java 17+ chạy độc lập: giả lập native handle và destructor

Để kiểm tra **lifecycle semantics** mà không cần C++ compiler hay FFM, ví dụ này dùng map Java giả lập native heap. Mỗi native handle được mô phỏng bằng một số ID **không phải địa chỉ C thật**. Việc giải phóng xóa ID khỏi map, ghi đếm hủy; nếu hủy trùng, test ném lỗi để phát hiện.

Tạo tệp `LifecycleLab.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public final class LifecycleLab {
    private static final class FakeBridge {
        private static long next = 1L;
        private static final Map<Long, Integer> values = new HashMap<>();
        private static int destroyCount;

        static synchronized long create(int initial) {
            long handle = next++;
            values.put(handle, initial);
            return handle;
        }

        static synchronized int read(long handle) {
            Integer value = values.get(handle);
            if (value == null) {
                throw new AssertionError("invalid handle");
            }
            return value;
        }

        static synchronized void destroy(long handle) {
            if (values.remove(handle) == null) {
                throw new AssertionError("double free");
            }
            destroyCount++;
        }

        static synchronized int destroyCount() {
            return destroyCount;
        }
    }

    public static final class Counter implements AutoCloseable {
        private long handle;
        private boolean closed;

        public Counter(int initial) {
            handle = FakeBridge.create(initial);
        }

        private void requireOpen() {
            if (closed) {
                throw new IllegalStateException("Counter is closed");
            }
        }

        public synchronized int value() {
            requireOpen();
            return FakeBridge.read(handle);
        }

        public synchronized boolean isClosed() {
            return closed;
        }

        @Override
        public synchronized void close() {
            if (closed) return;

            closed = true;
            long h = handle;
            handle = 0L;
            FakeBridge.destroy(h);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Counter c = new Counter(7);
        try (c) {
            System.out.println("value=" + c.value());
            System.out.println("closed-in-scope=" + c.isClosed());
        }

        c.close();
        System.out.println("closed-after=" + c.isClosed());
        System.out.println("destroy-count=" + FakeBridge.destroyCount());

        try {
            c.value();
        } catch (IllegalStateException e) {
            System.out.println("use-after-close="
                    + e.getClass().getSimpleName());
        }

        Counter raced = new Counter(9);
        Thread t1 = new Thread(raced::close);
        Thread t2 = new Thread(raced::close);
        t1.start();
        t2.start();
        t1.join();
        t2.join();

        System.out.println("raced-closed=" + raced.isClosed());
        System.out.println("total-destroys=" + FakeBridge.destroyCount());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**, không cần native access:

~~~bash
javac -encoding UTF-8 LifecycleLab.java
java LifecycleLab
~~~

**Stdout đã được đối chiếu bằng JDK 24**:

~~~text
value=7
closed-in-scope=false
closed-after=true
destroy-count=1
use-after-close=IllegalStateException
raced-closed=true
total-destroys=2
~~~

### Đọc kết quả thí nghiệm

- Trong `try`, object OPEN, `value() == 7` và `isClosed() == false`.
- Ra khỏi `try`, Java gọi `close()`; `destroy-count=1` chứng minh một resource được hủy.
- `c.close()` tiếp theo không tăng count.
- `c.value()` sau close ném `IllegalStateException` ở Java **trước** khi `FakeBridge.read`.
- Hai threads cùng gọi `raced.close()`. Mỗi wrapper có monitor riêng, nên chỉ một thread đi qua chuyển trạng thái OPEN → CLOSED, thread còn lại thấy CLOSED và no-op.
- Tổng số native destroys là 2: mỗi một trong **hai Counter instances** được destroy **một lần**. Thứ tự threads khác nhau không ảnh hưởng output.

Điểm quan trọng: test này xác minh **lógica Java wrapper**, không chứng minh native `delete` thực sự được gọi đúng trong bản FFM/JNI. Test integration cần thêm C++ counters/hooks hoặc ASan để quan sát native allocations thật.

## 11. Lỗi đóng tài nguyên: state CLOSED và resource release là hai sự kiện khác nhau

Một vấn đề thiết kế nâng cao: nếu destructor/deallocator native **có thể báo lỗi**, việc `close()` đã chuyển state CLOSED **không đủ** để nói tài nguyên chắc chắn đã release thành công.

Giả sử native API trả status:

~~~c
/* Prototype minh họa, không thuộc demo_counter.h ở mục 7. */
int counter_release_ex(CounterHandle *h);
~~~

Cần xác định rõ:

1. Status 0: handle đã được release hoàn toàn?
2. Status khác 0: handle còn hoàn toàn nguyên vẹn, có thể retry, hay đã release một phần?
3. Có thể xảy ra lỗi nhưng native đã free handle rồi không?
4. Có native logging/error object nào giúp chẩn đoán sau release không?
5. Ai có quyền retry và khi nào? Có thể an toàn khi nhiều threads gọi close không?

Nếu native contract **không** bảo đảm trạng thái sau failure, cách an toàn hơn là **đóng quyền sử dụng Java** ngay trước release, không retry tự phát, ghi nhận potential leak và chuyển lỗi cho owner.

~~~java
// Ý tưởng minh họa, không phải thay thế trực tiếp cho NativeCounter ở mục 8:
if (!closed) {
    closed = true;              // Java object không còn được dùng.
    MemorySegment old = handle;
    handle = MemorySegment.NULL;
    // Gọi native release duy nhất một lần.
    // Nếu có lỗi: report + instrumentation, không blindly retry.
}
~~~

Với API thực sự quy định “failure leaves the resource fully owned and unchanged”, có thể thiết kế retry state riêng như `CLOSE_FAILED`, nhưng cần phân biệt rõ **retryable** và **terminal**. Không tự giả định `close()` sẽ luôn thành công hoặc luôn retry được.

### Đừng để `InterruptedException` rò ra từ `close` nếu không bắt buộc

Javadoc `AutoCloseable` khuyến nghị không để `close` ném `InterruptedException`, vì nó có thể làm thay đổi interrupted state và gây khó cho cú pháp try-with-resources. Nếu shutdown cần đợi native worker, hãy định nghĩa rõ cancel/timeouts/retry, bảo toàn thread interruption semantics và chọn kiểu ngoại lệ đúng hợp đồng Java application.

### Try-with-resources khi cả body lẫn close đều lỗi

Ví dụ:

~~~java
try (NativeCounter c = new NativeCounter(7)) {
    throw new IllegalStateException("work failed");
}
~~~

Nếu `close()` cũng ném, Java **giữ exception từ body làm primary** và đặt exception từ `close` vào danh sách **suppressed exceptions** (trừ những trường hợp đặc biệt theo ngữ nghĩa Java). Khi debug, kiểm `Throwable.getSuppressed()`; đừng chỉ tìm lỗi đầu tiên rồi kết luận cleanup chắc đã thành công.

Đoạn ví dụ là snippet để giải thích language semantics, không gắn stdout cố định.

## 12. JNI wrapper cũng cần trạng thái đóng như FFM wrapper

Nếu dự án không dùng FFM (ví dụ cần Java 17 + JNI), một lớp Java có thể giữ opaque handle `long` do JNI method trả lại:

~~~java
public final class JniCounter implements AutoCloseable {
    private long handle;
    private boolean closed;

    public JniCounter(int initial) {
        long h = nativeCreate(initial);
        if (h == 0L) {
            throw new IllegalStateException("nativeCreate returned NULL");
        }
        handle = h;
    }

    private void requireOpen() {
        if (closed) throw new IllegalStateException("closed");
    }

    public synchronized int value() {
        requireOpen();
        return nativeGet(handle);
    }

    public synchronized boolean isClosed() {
        return closed;
    }

    @Override
    public synchronized void close() {
        if (closed) return;
        closed = true;
        long h = handle;
        handle = 0L;
        nativeDestroy(h);
    }

    private static native long nativeCreate(int initial);
    private static native int nativeGet(long handle);
    private static native void nativeDestroy(long handle);
}
~~~

Đây là **minh họa Java source cần JNI implementation tương ứng**, không phải file chạy độc lập. Nó cố ý bỏ phần `System.loadLibrary` và JNI C++ glue để tập trung vào state; trong project thật phải nạp library và khai báo Java native signatures phù hợp. Cần map handle vào pointer ở JNI bằng cast an toàn theo ABI (`intptr_t`/`uintptr_t`, không giả định Java `long` bằng C pointer trên mọi platform) và không ném C++ exception vượt JNI boundary.

Điểm chung không thay đổi: `AutoCloseable` ở Java vẫn kiểm soát **quyền truy cập**, **ownership** và **lifetime** của resource. Khác nhau chỉ ở cơ chế gọi native: JNI dùng native methods và `JNIEnv`, FFM dùng `Linker`/`MethodHandle`.

## 13. `Arena`, `MemorySegment` và C++ destructor không thể thay thế nhau

Trong FFM, `Arena.ofConfined()`/`Arena.ofShared()` quản lý **memory do Arena cấp và resources gắn với scope đó**. Nhưng nếu native C++ code trả `CounterHandle*` từ `new` thì `MemorySegment` đại diện pointer ấy **không tự mang C++ destructor**.

| Resource | Được cấp bằng | Phương thức đúng để giải phóng |
| --- | --- | --- |
| Out buffer tạm `int32_t*` | `arena.allocate(JAVA_INT)` | `arena.close()` |
| C++ opaque object | `counter_create` với C++ `new` | `counter_destroy` đúng một lần theo ownership |
| Raw pointer wrapper | Giá trị `MemorySegment` từ `ADDRESS` | Không tự sở hữu memory; không tự `free` |
| FFM upcall stub | `linker.upcallStub(..., arena)` | Đóng arena **sau** khi native không còn gọi callback |
| C string allocated với `malloc`/native allocator | Native function/library | Deallocator đúng allocator theo API, không mặc định Arena đóng |
| JNI global reference | `NewGlobalRef` | `DeleteGlobalRef`, khác với C++ destructor |

**Một trường hợp nguy hiểm:** tạo C++ handle bằng `counter_create`, sau đó gọi `MemorySegment.ofAddress(pointer.address()).reinterpret(...)` và tin rằng view có size được gắn Arena sẽ gọi `delete`. Không đúng. `reinterpret`/scope chỉ mô tả quyền truy cập view; allocator và destructor của C++ object vẫn độc lập.

Java `Cleaner` có thể được thiết kế như backstop cho quên close, nhưng không thay thế release deterministic (xem mục 15).

## 14. Borrowed views, clone/copy và quyền sở hữu một lần

Giả sử native API có:

~~~cpp
// Prototype minh họa:
CounterHandle* counter_get_child(CounterHandle* parent);
~~~

Nếu `child` là **borrowed pointer** thuộc parent, Java không được tạo `new NativeCounter(child)` mà constructor mặc định sẽ own/delete child. Có thể chọn:

- Một `BorrowedCounterView` chỉ gọi native khi **parent còn OPEN**.
- Borrowed view giữ một tham chiếu mạnh đến parent để tránh Java parent bị GC sớm, đồng thời parent không được close trong lúc view đang dùng (cùng lock/lifetime protocol).
- Native API `counter_retain(child)`/`counter_release(child)` nếu cho phép chuyển sang shared ownership.
- Copy thực sự bằng native `counter_clone(child)` tạo allocation mới, sau đó Java wrapper khác mới owned.

**Không đồng nghĩa:** copy Java wrapper object hoặc clone reference `MemorySegment` không làm native object được duplicate. Nếu hai wrappers cùng gọi native delete vào một address, double-free là rủi ro nghiêm trọng.

Khi native method tạo resource mới và trả handle, **mọi nhánh lỗi sau create nhưng trước khi wrapper nhận ownership** phải cleanup resource nếu cần. Nếu constructor Java gặp lỗi sau khi create thành công, dùng cấu trúc try/catch/finally để gọi release đúng một lần hoặc chuyển ownership một cách nguyên tử.

## 15. `Cleaner`, finalization và shutdown hook: chỉ là lớp bảo vệ phụ

Một số thư viện dùng `java.lang.ref.Cleaner` để dọn native memory nếu caller quên `close()`. Nhưng:

- Thời điểm Cleaner chạy **không deterministic**. GC có thể không xảy ra trước khi tiến trình kết thúc.
- Cleaner phải có **State object riêng** làm cleaning action, không giữ tham chiếu ngược tới chính Java wrapper gây giữ sống wrapper vô hạn.
- Cần làm cleaning action idempotent và phối hợp với explicit `close()` để không double-free.
- Nếu native resource yêu cầu giải phóng trên một thread nhất định, Cleaner thread có thể không phù hợp.
- Nếu native library đã unload trước khi cleaner chạy, gọi destructor qua stale function pointer rất nguy hiểm.
- `finalize()` đã bị deprecate for removal, không phải phương án release tài nguyên mới đáng tin.
- `Runtime.addShutdownHook` không thay `close()`: shutdown order, abrupt termination và các dependencies không được bảo đảm như normal try-with-resources.

Nếu dùng Cleaner, hãy **bảo đảm không có callback/native worker đang dùng resource** trước khi cleanup và tránh thiết kế nhiều owners cùng release một address. Với workload chứa database handles, GPU contexts, C++ objects có affinity hoặc native threads, explicit owner `close()` thường là trung tâm thiết kế.

### Ví dụ về lối nghĩ sai

~~~java
// Sai về mặt hợp đồng, dù Java source biên dịch:
class BadWrapper {
    long nativePointer;
    @Override
    protected void finalize() throws Throwable {
        nativeDestroy(nativePointer);
    }
}
~~~

Đây là **phản ví dụ**, không có `nativeDestroy` implementation và không nên chạy. GC không biết khi nào native work còn sử dụng pointer; finalizer không đảm bảo release kịp thời và có vấn đề an toàn/lifecycle. Hãy dùng `AutoCloseable` với owner cụ thể thay vì dựa vào finalization.

## 16. Callback, async native work và xử lý close chậm

Một wrapper đơn giản `synchronized` phù hợp khi `counter_get` **đồng bộ và không giữ handle** sau return. Nếu C++ API tạo background tasks hoặc lưu callback function pointers, vòng đời khó hơn:

~~~text
Java wrapper OPEN
    |
    +-- startAsync(handle) -> native worker giữ handle
    |
    +-- close() được gọi từ Java
             |
             +-- chặn operation mới
             +-- yêu cầu native cancel/unregister
             +-- chờ mọi in-flight operation/callback kết thúc
             +-- counter_destroy(handle)
             +-- Java state CLOSED
~~~

Điểm mấu chốt: **không gọi delete khi native worker vẫn còn pointer**. Nếu close chỉ invalidate Java field rồi delete ngay, native worker có thể dereference vùng nhớ đã free. Phải có protocol từ native library để xác nhận không còn người dùng.

Một hệ thống phức tạp có thể cần:

- Reference count/in-flight lease quanh mỗi native use.
- Lock state và condition/latch để close chờ lease count về 0.
- Native unregister/cancel API với acknowledgment.
- Tránh chờ callbacks trong khi đang giữ lock mà callback cũng cần.
- Thread affinity: một số C++ objects phải được destroy trên native event-loop/creator thread.
- Timeout/error state rõ ràng; nếu không thể stop worker, báo lỗi và **không giả vờ resource đã free an toàn**.

**Đừng áp mẫu giả lập đơn giản vào native async API không có lifecycle guarantee.** Trạng thái `CLOSING` có ích để biểu diễn rằng close đã được yêu cầu nhưng native chưa release; API `isClosed()` phải định nghĩa rõ nó nghĩa là “không còn được phép dùng” hay “native đã giải phóng”, tránh đánh đồng hai khái niệm.

## 17. Những trường hợp ngoại lệ cần thiết kế

| Tình huống | Rủi ro | Quy tắc nên chọn |
| --- | --- | --- |
| `counter_create` trả NULL | Constructor có thể publish handle invalid | Fail fast, không tạo wrapper OPEN |
| C++ factory ném exception | Exception không được đi qua FFM/C ABI | C ABI catch/mapping errors, trả status/null |
| `value()` sau close | Use-after-free | Ném `IllegalStateException` trước downcall/JNI |
| `close()` lần 2 | Double delete | Idempotent/no-op |
| Two threads cùng close | Double delete nếu guard không atomic | Một monitor/lock bảo vệ transition |
| Thread A đang get, B close | UAF nếu chỉ volatile flag | Một lock bảo vệ cả native call và close |
| `close()` ném sau khi đã free | Blind retry có thể double-free | Invalidate state trước release, ghi nhận lỗi |
| Native destructor có thể fail nhưng vẫn giữ handle | Leak hoặc mất ownership nếu state sai | Cần contract retryability và state `CLOSE_FAILED` nếu an toàn |
| Native worker còn giữ pointer | UAF sau Java close | Cancel/unregister, drain in-flight rồi free |
| Borrowed pointer bị wrapper own | Invalid/double-free | Phân biệt owner/borrower ở type level |
| Hai wrappers own cùng pointer | Double delete | Chuyển ownership, retain/release hoặc clone thật |
| Native library unload trước wrapper close | Gọi stale function pointer | Ràng buộc classloader/library lifetime |
| Native operation trả error code | Java không nhận ra thất bại | Map status sang exception/domain result |
| UI thread gọi close tốn thời gian | Freeze/deadlock giao diện | Điều phối cleanup bất đồng bộ với contract rõ |

**Các exception không thể “catch rồi tiếp tục” một cách vô tư:** segmentation fault do invalid native pointer, heap corruption do double-free và sai C++ calling convention thường có thể giết JVM. Nên ngăn bằng ownership/state/ABI contract thay vì dựa vào Java `try/catch`.

## 18. Test strategy: chứng minh release đúng một lần

Bộ test khuyến nghị:

1. **Create success:** owned handle khác NULL, state OPEN, operation trả dữ liệu đúng.
2. **Create failure:** factory trả NULL/status lỗi → constructor thất bại, không publish resource và không gọi destructor trên invalid pointer.
3. **Implicit close:** `try-with-resources` ra khỏi scope → destructor gọi đúng một lần.
4. **Explicit + implicit close:** gọi `close()` bên trong `try` rồi tự đóng lần nữa → vẫn một destructor.
5. **Repeat close:** 2/3/10 lần liên tiếp → no-op, không crash.
6. **Use-after-close:** mọi public method chạm native (bao gồm getter/mutator/callback registration) → `IllegalStateException` trước native call.
7. **Concurrent close:** nhiều threads gọi `close` → count destroy vẫn 1.
8. **Get vs close:** dùng `CountDownLatch` hoặc barrier làm native get chờ, close phải đợi get hoàn tất (hoặc dùng lease protocol rõ).
9. **Destroy failure:** giả lập native release trả lỗi ở nhiều thời điểm; wrapper không retry mù và báo ownership không chắc chắn.
10. **Shared/borrowed views:** đóng parent/view đúng lifetime; không double free.
11. **Native sanitizers:** ASan/UBSan trên C++ binary (khi hỗ trợ) để phát hiện UAF/double-free; công cụ heap profiler/Valgrind khi phù hợp.
12. **Leak tests:** tạo/close nhiều resource rồi kiểm native allocation count, không chỉ Java heap usage.

### Một kiểm thử interleaving phải có tiêu chí đúng

Với wrapper dùng một monitor, nếu operation thật được giữ lâu trong native code, thread close **không được** gọi `counter_destroy` trước khi operation trả về. Đó là điều kiện cần chứ không chỉ là kiểm Java `closed` sau khi join. Một test có native hook/latch có thể ghi timestamp sự kiện vào log để chứng minh thứ tự, nhưng test không nên dựa vào `Thread.sleep` một khoảng ngẫu nhiên rồi suy ra race đã được thử đủ.

### Test close failure không nên tạo double-free

Nếu mock destructor cố ý “free rồi ném”, Java wrapper phải giữ `closed=true`, tránh gọi destroy lần hai. Nếu mock destructor “ném trước khi free”, wrapper có thể leak; **không thể vừa bảo đảm không leak vừa bảo đảm không double-free mà không có native contract phân biệt hai trạng thái**. Đây là lý do phải thiết kế C ABI cleanup status thật rõ từ đầu.

## 19. Mẫu thiết kế sai và cách chỉnh

| Anti-pattern | Vì sao sai? | Thay thế |
| --- | --- | --- |
| `class NativeThing { long ptr; }` không close | Không có lifecycle owner | `implements AutoCloseable`, trạng thái CLOSED và release |
| `close(){ nativeDelete(ptr); }` | Gọi lần hai delete trùng | Guard + set CLOSED + invalidate ptr |
| Chỉ kiểm `if (ptr != 0)` | Không thể hiện ownership/failure rõ | `closed` là API contract |
| Chỉ dùng `volatile closed` | Race check-then-call vẫn tồn tại | Lock quanh cả operation và destroy |
| `AtomicBoolean.getAndSet(true)` rồi destroy nhưng operation không lock | Có thể UAF trong operation | Lock hoặc in-flight lease protocol |
| Expose `public long address()` | Client bypass guard/destroy | Encapsulate handle, chỉ expose safe operations |
| Gán `ptr=0` mà không gọi native delete | Resource vẫn leak | Gọi đúng destructor/deallocator |
| Gọi C `free` với C++ `new` | Allocator mismatch | Export C ABI factory/destructor pair |
| Dùng `Arena.close()` để hủy C++ object | Arena không tự biết C++ destructor | Gọi `counter_destroy` |
| Gọi `counter_destroy` từ Cleaner như cơ chế duy nhất | GC scheduling không deterministic | Explicit `close()`, Cleaner chỉ optional backstop |
| Copy native pointer thành hai owned Java objects | Double-free | One owner hoặc retain/release |
| Gọi close khi callback/native thread còn dùng handle | UAF/deadlock | Unregister/drain, then release |
| Swallow mọi lỗi native get rồi trả 0 | Che trạng thái hỏng | Map status sang exception rõ |
| Treat closed flag == successful native free | Lệch nếu release có lỗi | Phân biệt access closed với release status |
| Sửa raw pointer bằng `reinterpret` hoặc cast `long` | Không phục hồi memory đã free | Tôn trọng lifetime/ABI |
| Dùng Java `null` làm FFM C null address | Không phải pointer carrier hợp lệ theo contract | `MemorySegment.NULL` |

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `AutoCloseable` không tự giải phóng `new CounterHandle` trong C++?

Vì nó chỉ định nghĩa **`close()` interface**. Caller phải hiện thực `close` để gọi đúng native destructor, bảo vệ trạng thái và quyền sở hữu. GC của Java không tự hiểu C++ allocator.

**Câu 2.** `AutoCloseable.close()` bắt buộc idempotent theo Javadoc không?

Không. Interface không yêu cầu tuyệt đối, nhưng Javadoc **khuyến khích** các implementation đóng idempotent. Với wrapper sở hữu một C++ pointer, idempotence thường là tiêu chí an toàn để tránh double-free.

**Câu 3.** Tại sao `volatile boolean closed` vẫn chưa đủ?

Vì thread A có thể đọc closed=false, thread B free native pointer, rồi A mới gọi native. Check và call không nguyên tử. Cần lock hoặc lease/refcount bảo vệ **khoảng thời gian native call đang sử dụng pointer**.

**Câu 4.** `isClosed()==false` có chứng minh native object chắc còn sống không?

Chỉ khi **ownership contract** được tuân thủ và mọi native owner khác không tự delete. Nếu native library tự free ngoài wrapper, Java state có thể sai. Vì vậy không expose raw handle và cần chính sách owner.

**Câu 5.** Vì sao set `closed=true` trước native release có thể hợp lý?

Nếu release lỗi hoặc ném exception sau khi free một phần/hoàn toàn, Java không retry và dùng lại pointer đã không rõ tình trạng. Điều đó có thể đi kèm leak khi release thất bại trước free; cần native contract để xử lý chính xác.

**Câu 6.** Nếu `close()` gọi lần 2 khi CLOSED thì nên làm gì trong ví dụ?

Trả về ngay, không gọi `counter_destroy` nữa. State vẫn CLOSED.

**Câu 7.** Hai wrappers cùng nhận một pointer C++ và cả hai có `close()` gọi delete thì sao?

Có nguy cơ double-free. Chọn một owned wrapper, borrowed view, hoặc native reference counting với mỗi share được retain và release riêng.

**Câu 8.** `Arena.ofConfined()` trong `value()` của FFM wrapper đang giải phóng cái gì?

Nó chỉ cấp và giải phóng **out buffer tạm** cho `int32_t*`. C++ CounterHandle thuộc `counter_create` và cần `counter_destroy`.

**Câu 9.** Sau `close()` nhưng native cleanup throw, có nên tự động gọi `close()` thêm lần nữa không?

Không nếu không biết chắc trạng thái native handle. Blind retry có thể double-free. Hãy báo lỗi và dựa vào status/ownership contract trước khi quyết định recovery.

**Câu 10.** Một native async operation vẫn giữ handle khi Java gọi `close()`. Phải làm gì?

Ngăn operation mới, cancel/unregister hoặc đợi in-flight operations hoàn tất, rồi mới destroy. Khi cần, dùng state `CLOSING` và native acknowledgment thay vì free ngay.

**Câu 11.** `try-with-resources` có bảo đảm thứ tự close không?

Có. Với nhiều resources trong header `try`, Java đóng theo **thứ tự đảo ngược khai báo**. Nếu resource phụ thuộc vào nhau, chọn thứ tự khai báo phù hợp và kiểm suppressed exceptions.

**Câu 12.** Có thể dùng `Cleaner` thay cho `AutoCloseable` không?

Không nên. Cleaner/GC không bảo đảm thời điểm release và có ràng buộc thread/library lifetime. Với C++ wrapper có owner rõ, dùng explicit `close()` và Cleaner chỉ như backstop nếu thiết kế chắc chắn an toàn.

## 21. Checklist triển khai production

- [ ] Native factory trả owned handle hay borrowed pointer? Ghi rõ bằng tài liệu/C ABI.
- [ ] Native destructor/deallocator chính xác là gì? Có ABI `extern "C"` ổn định không?
- [ ] Wrapper là `final` hoặc kiểm soát rõ subclassing và ownership?
- [ ] Native handle là private, không cho client giữ raw pointer để vượt guard?
- [ ] State OPEN/CLOSED được bảo vệ bởi một cơ chế concurrency nhất quán?
- [ ] `isClosed()` mô tả đúng **quyền sử dụng** của wrapper, không lẫn với release success?
- [ ] Mọi public native operation đều `requireOpen()` khi giữ lock/lease đúng?
- [ ] `close()` idempotent: destructor được gọi nhiều nhất một lần per ownership share?
- [ ] `close()` invalidate handle + state theo failure policy rõ ràng?
- [ ] Constructor xử lý factory return NULL và không để resource owned bị leak khi init lỗi?
- [ ] `try-with-resources` dùng ở call sites nơi có thể; không trông chờ GC?
- [ ] Không đóng resource khi native callback/async worker vẫn còn dùng?
- [ ] C ABI không để C++ exception tràn qua JNI/FFM boundary?
- [ ] FFM `SymbolLookup` và `Linker` dùng đúng native library, ABI và permission?
- [ ] Native C++ code được build với đúng target, compiler, libstdc++/libc++ runtime?
- [ ] Tests kiểm close lặp, use-after-close, concurrent close, operation vs close, close failure và leaks?
- [ ] Không double-delete khi có borrowed views và resource sharing?
- [ ] Không dùng Cleaner/finalizer như cơ chế release duy nhất?

## Tài liệu chính thức

1. [Oracle Java SE 24 — AutoCloseable](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/AutoCloseable.html): `close`, try-with-resources, nguyên tắc release trước khi ném exception và khuyến nghị idempotence.
2. [Java Language Specification `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se24/html/jls-14.html#jls-14.20.3): đóng resources theo thứ tự ngược, primary/suppressed exceptions.
3. [Oracle Java SE 24 — Linker](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.html): downcall, C ABI và restricted native access.
4. [Oracle Java SE 24 — SymbolLookup](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/SymbolLookup.html): `loaderLookup()` sau `System.loadLibrary()` và lifetime của native symbols.
5. [Oracle Java SE 24 — Arena](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html): cấp phát out buffers, scope và thread confinement.
6. [Oracle Java SE 24 — MemorySegment](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html): `NULL`, native address, bounds và lifetime.
7. [Oracle Java SE 24 — Cleaner](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ref/Cleaner.html): hạn chế và hướng dẫn dùng cleaning action.
8. [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): API FFM chính thức từ Java 22.

**Tóm tắt:** Một wrapper Java sở hữu C++ resource phải nói rõ **ai được close, close làm gì và sau close điều gì bị cấm**. `AutoCloseable` kết nối với `try-with-resources`; `closed`/`isClosed` làm rõ trạng thái; **lock hoặc lease** bảo vệ pointer trong cả native call; **native destructor đúng allocator và đúng một lần** ngăn rò rỉ/double-free. Khi resource có callback/async lifetime, phải thiết kế shutdown protocol, không chỉ thêm một boolean.
