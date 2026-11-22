# Giữ stub sống trong suốt thời gian thư viện còn có thể gọi lại

## Mục tiêu

Foreign Function & Memory API (FFM) cho phép Java gọi C qua **downcall** và cho C gọi lại Java qua **upcall stub**. Khi thực hiện `Linker.upcallStub(target, descriptor, arena)`, JVM tạo một native function pointer tương ứng với `MethodHandle` của Java. Hàm C có thể nhận và **lưu** pointer này trong registry, một listener, event loop hoặc native thread.

Lỗi nguy hiểm xảy ra khi phía Java nghĩ rằng đăng ký callback đã hoàn tất nên đóng `Arena`, nhưng C vẫn có thể gọi lại vào function pointer ấy. Một callback được thực thi **sau khi arena đã giải phóng stub** có thể gây crash JVM hoặc memory corruption. Đây không phải lỗi Java thông thường có thể luôn bắt bằng `try/catch`.

Bài này hướng dẫn:

- Hiểu bản chất và vòng đời của `MemorySegment` đại diện cho upcall stub.
- Phân biệt lifetime của `Arena`, Java `MethodHandle`/captured state, thư viện native và callback registration.
- Xác định điều kiện đóng an toàn: **ngừng nhận callback mới → unregister → drain hoặc join tất cả in-flight/queued callbacks → đóng arena**.
- Viết ví dụ **JDK 22+ + C11** đầy đủ, trong đó C giữ pointer qua nhiều lời gọi Java, sau đó hủy đăng ký trước khi Java đóng arena.
- Kiểm tra descriptor, ABI, quyền native access, native symbol lifetime và exception handling ở upcall target.
- Dùng owner state machine và đồng bộ hóa để tránh race giữa callback, unregister và close.
- Phân biệt callback đồng bộ chỉ chạy trong một downcall và callback bất đồng bộ có thể đến sau hàng giờ.
- Kiểm thử an toàn mà không cố ý gọi function pointer đã giải phóng.

> **Yêu cầu JDK:** FFM trong `java.lang.foreign` trở thành API chuẩn từ **JDK 22** theo JEP 454. Không thể biên dịch đoạn `Linker.upcallStub` này trên Java 17; Java 17 có API incubator khác hoặc có thể dùng JNI. Ví dụ chính cần JDK 22+, C compiler và khi chạy trên class path dùng `--enable-native-access=ALL-UNNAMED` cho các restricted FFM operations. Không cần `--enable-preview` trên JDK 22.

## 1. Upcall stub là gì?

Trong C, callback có thể là một function pointer:

~~~c
#include <stdint.h>

typedef int32_t (*callback_fn)(int32_t value);

int32_t register_callback(callback_fn callback);
~~~

Đây là **khai báo minh họa**. `callback_fn` không phải Java object; C chỉ thấy một địa chỉ native có thể được gọi theo đúng calling convention. Java thông thường không thể cast một lambda thành loại pointer này. FFM `Linker` tạo một stub/trampoline, và khi C gọi địa chỉ ấy, JVM điều phối sang Java `MethodHandle`.

~~~text
Java method: int onEvent(int value)
                |
         MethodHandles.lookup()
                |
           MethodHandle
                |
       Linker.upcallStub(...)
                |
        MemorySegment stub
        (native function pointer)
                |
       C register_callback(stub)
                |
       C lưu pointer trong state
                |
          ... thời gian trôi ...
                |
       C gọi pointer(value)
                |
         FFM upcall bridge
                |
       Java onEvent(value)
                |
         C nhận int32_t
~~~

Theo đặc tả `Linker.upcallStub` của Java SE 22:

- Nó nhận `MethodHandle`, `FunctionDescriptor`, `Arena` và linker options tùy chọn.
- Nó trả về **MemorySegment độ dài 0** với địa chỉ native của upcall stub.
- **Arena kiểm soát lifetime của stub**: nếu arena đã đóng, địa chỉ stub không còn hợp lệ.
- Method handle target phải tương thích carrier types với descriptor.
- Target **không được ném Java exception xuyên qua upcall boundary**; đặc tả cảnh báo JVM có thể kết thúc đột ngột.

Như vậy `MemorySegment stub` vừa là handle Java để quản lý địa chỉ, vừa là một **resource native có lifetime**. Nó không tự tạo refcount với các C libraries đã nhận pointer.

## 2. Điều kiện quan trọng nhất: khi nào thực sự hết callback?

Không được quyết định close bằng thời điểm `register_callback` trả về. Thay vào đó, hỏi:

> **Thư viện native đã hoàn toàn mất khả năng sử dụng function pointer này chưa, bao gồm callback đang chạy, đang chờ trong queue và callback đã được worker giữ bản sao pointer?**

Chỉ khi câu trả lời được bảo đảm là **có**, bạn mới được đóng arena.

~~~text
CREATE arena và upcall stub
         |
REGISTER pointer với thư viện C
         |
    CALLBACK ACTIVE
         |
 C có thể gọi một hoặc nhiều lần
         |
  REQUEST STOP / CLOSING
         |
 ngăn callback mới được lập lịch
         |
 unregister pointer khỏi registry
         |
 cancel/drain queued callbacks
         |
 chờ tất cả in-flight invocations xong
         |
    NATIVE QUIESCENT
         |
  ARENA.CLOSE() một lần
         |
       CLOSED
       pointer INVALID
~~~

Ba điều kiện cần phân biệt:

1. **Không còn đăng ký mới:** native library từ chối sự kiện mới liên quan đến callback.
2. **Không còn công việc đã lên lịch:** mọi queue item giữ pointer đã được hủy hoặc hoàn tất, kể cả task chưa bắt đầu thực thi.
3. **Không còn invocation đang chạy:** mọi thread đã rời upcall stub và Java target, không giữ pointer để dùng tiếp.

Chỉ xóa một biến global C **chưa đủ** nếu native thread đã đọc pointer vào biến local hoặc queue đã copy pointer từ trước.

### Phản ví dụ use-after-free

~~~text
Java: create arena
Java: create stub
Java: register(stub)
C:    g_callback = stubAddress

Java: return from register()
Java: arena.close()           <--- sai

C:    event later
C:    g_callback(42)          <--- địa chỉ stub đã bị free
                                     => crash/undefined behavior
~~~

Không thử chạy phản ví dụ: việc gọi con trỏ hàm hết lifetime có thể làm sập cả JVM.

## 3. Ba vòng đời không được nhầm lẫn

| Thành phần | Ai sở hữu/quản lý? | Điều kiện còn dùng được |
|---|---|---|
| Upcall stub | `Arena` dùng khi tạo stub | Scope còn sống và chưa close |
| Target `MethodHandle` | Java/FFM linker và owner references | Target/captured state có lifetime hợp lệ |
| Native callback registration | SDK/thư viện C | SDK còn lưu hoặc có thể gọi function pointer |
| Native library/symbols | `SymbolLookup.libraryLookup`, class loader hoặc OS loader | Mã thư viện chưa bị unload trong lúc còn downcall/callback |
| Memory/data mà callback truy cập | Java object, arena khác hoặc SDK | Không bị close/free hay race |
| Native worker/queue | Event loop/thread pool SDK | Đã drain/join trước khi hủy stub |

**Giữ Java reference tới `MemorySegment stub` không ngăn bạn tự đóng arena.** Một Java object mô tả segment vẫn có thể tồn tại khi native backing đã bị giải phóng. Ngược lại, giữ arena sống mà state của Java target đã close sớm hoặc library code bị unload cũng không an toàn.

Một ownership contract hữu ích:

> `CallbackRegistration` sở hữu arena và stub. Native SDK **mượn địa chỉ** trong thời gian callback ACTIVE. SDK phải cung cấp cách unregister và xác nhận không còn callbacks in-flight/queued. Owner Java chỉ đóng arena sau khi native đã hết quyền gọi lại. Những consumer khác không được tự đóng arena.

Nếu chỉ đọc một giá trị trả về từ `register` rồi bỏ owner, bạn có thể đã làm mất khả năng kiểm soát lifecycle.

## 4. ABI và FunctionDescriptor phải đúng

Giả sử C định nghĩa:

~~~c
typedef int32_t (*callback_fn)(int32_t value);
int32_t register_callback(callback_fn cb);
int32_t fire_callback(int32_t x);
void unregister_callback(void);
~~~

Mapping FFM trong chương trình này:

| C signature | FFM descriptor | Java carrier |
|---|---|---|
| Callback `int32_t(int32_t)` | `FunctionDescriptor.of(JAVA_INT, JAVA_INT)` | `int → int` |
| `register_callback(callback_fn)` | `FunctionDescriptor.of(JAVA_INT, ADDRESS)` | `MemorySegment → int` |
| `fire_callback(int32_t)` | `FunctionDescriptor.of(JAVA_INT, JAVA_INT)` | `int → int` |
| `unregister_callback(void)` | `FunctionDescriptor.ofVoid()` | `() → void` |

`ValueLayout.ADDRESS` dành cho địa chỉ function pointer. Không thay bằng `ValueLayout.JAVA_LONG` chỉ vì pointer trên máy hiện tại có thể rộng 64 bit. Đừng giả định C `long` luôn tương đương Java `long`: C ABI thay đổi theo nền tảng.

Đối với target:

~~~java
MethodHandle target = MethodHandles.lookup().findStatic(
        UpcallLifetimeDemo.class,
        "onValue",
        MethodType.methodType(int.class, int.class));

MemorySegment stub = linker.upcallStub(
        target,
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.JAVA_INT),
        arena);
~~~

Đây là **mảnh Java**, cần những imports và `linker`/`arena` phù hợp. Ví dụ chạy đầy đủ dưới đây có target bắt lỗi.

ABI mismatch như C gọi `void (*)(double)` nhưng Java stub lại mô tả `int(int)` có thể dẫn đến crash hoặc memory corruption. Một `ClassCastException` ở Java **không** bảo vệ lỗi gọi function pointer bằng ABI sai. Đối với thư viện C++, cần C ABI shim khi cần, không tùy tiện cast C++ member-function pointer thành C callback.

## 5. Ví dụ chạy được JDK 22+ + C11: C giữ callback qua nhiều lời gọi

Bài thực hành có một shared library C và một chương trình Java. C không chạy background thread; mọi thao tác theo thứ tự trên một thread, để xác minh được output. Thư viện C **lưu** pointer khi đăng ký, rồi gọi ở những lần `fire_callback` sau đó. Đây là deferred registration qua **nhiều downcalls**, dù bản thân từng lần fire là đồng bộ.

### 5.1. File native `upcalllifetime.c`

~~~c
#include <stdint.h>
#include <stddef.h>

#if defined(_WIN32)
    #define API __declspec(dllexport)
#else
    #define API __attribute__((visibility("default")))
#endif

typedef int32_t (*callback_fn)(int32_t value);

/*
 * Demo SINGLE-THREADED.
 * Các biến C static chưa có mutex, không dùng đồng thời.
 */
static callback_fn stored_callback = NULL;

API int32_t register_callback(callback_fn callback) {
    if (callback == NULL || stored_callback != NULL) {
        return 0;
    }
    stored_callback = callback;
    return 1;
}

API int32_t fire_callback(int32_t value) {
    callback_fn current = stored_callback;
    if (current == NULL) {
        return -1;
    }
    return current(value);
}

API int32_t is_registered(void) {
    return stored_callback != NULL ? 1 : 0;
}

API void unregister_callback(void) {
    stored_callback = NULL;
}
~~~

**Giải thích:**

- `stored_callback` là một function pointer trong memory của C library; nó **không** giữ strong Java reference hay mở rộng lifetime của arena.
- `register_callback` chỉ lưu pointer và trả 1 khi thành công; nó không lập tức gọi Java.
- `fire_callback` có thể được gọi ở những thời điểm sau trong chương trình; nếu đã unregister, nó trả `-1`, **không truy cập pointer cũ**.
- `unregister_callback` xóa pointer. Trong mẫu chỉ có một thread và không queue, nên khi nó trả về không còn invocation nào dùng pointer.
- Không nâng cấp mẫu thành multi-thread chỉ bằng cách thêm `pthread_create`. Khi `fire` và `unregister` chạy đồng thời, truy cập `stored_callback` không có synchronization là C data race. Phải thiết kế registry lock/refcount/quiescence riêng.

### 5.2. File Java `UpcallLifetimeDemo.java`

~~~java
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

public final class UpcallLifetimeDemo {

    /*
     * Không cho bất kỳ Java Throwable nào thoát ra upcall target.
     * C protocol sẽ nhận một mã sentinel khi callback thất bại.
     */
    private static int onValue(int value) {
        try {
            return Math.multiplyExact(value, 2);
        } catch (Throwable failure) {
            return Integer.MIN_VALUE;
        }
    }

    public static void main(String[] args) throws Throwable {
        MemorySegment escapedStub;

        try (Arena arena = Arena.ofShared()) {
            Path library = Path.of(
                    System.mapLibraryName("upcalllifetime"))
                    .toAbsolutePath();

            Linker linker = Linker.nativeLinker();
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, arena);

            MethodHandle register = linker.downcallHandle(
                    symbols.find("register_callback").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS));

            MethodHandle fire = linker.downcallHandle(
                    symbols.find("fire_callback").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT));

            MethodHandle isRegistered = linker.downcallHandle(
                    symbols.find("is_registered").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT));

            MethodHandle unregister = linker.downcallHandle(
                    symbols.find("unregister_callback").orElseThrow(),
                    FunctionDescriptor.ofVoid());

            MethodHandle target =
                    MethodHandles.lookup().findStatic(
                            UpcallLifetimeDemo.class,
                            "onValue",
                            MethodType.methodType(
                                    int.class, int.class));

            MemorySegment stub = linker.upcallStub(
                    target,
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT),
                    arena);

            escapedStub = stub;
            boolean registered = false;

            try {
                int rc = (int) register.invokeExact(stub);
                if (rc != 1) {
                    throw new IllegalStateException(
                            "callback registration failed");
                }
                registered = true;

                System.out.println(
                        "registered="
                        + (int) isRegistered.invokeExact());
                System.out.println(
                        "first=" + (int) fire.invokeExact(7));
                System.out.println(
                        "second=" + (int) fire.invokeExact(11));
                System.out.println(
                        "overflowFallback="
                        + (int) fire.invokeExact(Integer.MAX_VALUE));
                System.out.println(
                        "stubScopeAliveDuring="
                        + stub.scope().isAlive());

            } finally {
                /*
                 * Native code ngừng giữ pointer trước close.
                 * Unregister trong demo không thất bại/không chờ thread.
                 */
                if (registered) {
                    unregister.invokeExact();
                }
            }

            System.out.println(
                    "registeredAfter="
                    + (int) isRegistered.invokeExact());

            System.out.println(
                    "fireAfterUnregister="
                    + (int) fire.invokeExact(7));

        } // Arena close chỉ SAU khi C xóa pointer.

        System.out.println(
                "stubScopeAliveAfter="
                + escapedStub.scope().isAlive());

        // Không gọi lại địa chỉ stub đã đóng!
    }
}
~~~

**Tại sao example đảm bảo lifetime?**

1. Arena được tạo **trước** library lookup và stub, sống cho đến hết `try` bao trùm tất cả các downcalls.
2. `SymbolLookup.libraryLookup(library, arena)` tải và tra cứu library theo scope arena; không unload khi callback còn đăng ký.
3. Java tạo `MethodHandle` có type đúng `int(int)` rồi `upcallStub` trong arena còn sống.
4. Khi C đăng ký thành công, `registered=true`; mọi đường thoát khỏi khối `try` bên trong đều đi qua `finally` và `unregister_callback`.
5. `fire_callback` được gọi hai lần **sau khi** `register_callback` đã trả về. Stub phải còn sống trong suốt khoảng này.
6. Mã C có đúng một Java thread, không có asynchronous event queue hoặc thread giữ bản sao pointer; `unregister_callback` đồng bộ và xóa pointer hoàn toàn.
7. Sau unregister, Java kiểm tra C `is_registered()==0` và gọi `fire_callback` để nhận `-1` mà **không dereference pointer**.
8. Chỉ sau khi không còn callback registration, arena đóng. `escapedStub` còn được Java giữ để kiểm tra scope nhưng không thể tiếp tục được gọi từ C.

**Lưu ý về production:** nếu `unregister` có thể ném hoặc không bảo đảm drain, `try-with-resources` của arena có thể đóng ở đường exception **khi C vẫn giữ pointer**. Mẫu này an toàn vì `unregister_callback` của demo được thiết kế là thao tác đồng bộ, không lỗi và không có concurrent callbacks. Với SDK có async unregister, owner phải điều khiển close bằng state machine riêng.

### 5.3. Biên dịch trên Linux/macOS/Windows

Đặt hai file cùng thư mục. Dùng JDK 22+, C11 compiler đúng kiến trúc JVM. FFM không sử dụng JNI header, nên **không cần `javac -h`**.

**Linux (GCC):**

~~~bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
  upcalllifetime.c -o libupcalllifetime.so

javac UpcallLifetimeDemo.java
java --enable-native-access=ALL-UNNAMED UpcallLifetimeDemo
~~~

**macOS (Clang):**

~~~bash
clang -std=c11 -Wall -Wextra -dynamiclib \
  upcalllifetime.c -o libupcalllifetime.dylib

javac UpcallLifetimeDemo.java
java --enable-native-access=ALL-UNNAMED UpcallLifetimeDemo
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /LD /W4 upcalllifetime.c /Fe:upcalllifetime.dll
javac UpcallLifetimeDemo.java
java --enable-native-access=ALL-UNNAMED UpcallLifetimeDemo
~~~

`System.mapLibraryName("upcalllifetime")` trả tên file của thư viện theo OS, ví dụ `libupcalllifetime.so` hoặc `upcalllifetime.dll`. `toAbsolutePath` trỏ vào **working directory hiện tại**: chạy Java từ thư mục chứa binary. `SymbolLookup.libraryLookup(Path, Arena)` là restricted method; `--enable-native-access=ALL-UNNAMED` áp dụng cho code trên class path. Với named module, thay bằng module cụ thể để hạn chế quyền.

`Linker.downcallHandle` và `Linker.upcallStub` cũng là restricted operations. Nếu gặp `IllegalCallerException` hoặc cảnh báo native access, kiểm tra startup options, JDK version và module configuration. Nếu gặp lỗi tìm library/symbol, kiểm tra tên file, exported symbol C, compiler flags, OS/CPU architecture và thư mục làm việc.

### 5.4. Output mong đợi

~~~text
registered=1
first=14
second=22
overflowFallback=-2147483648
stubScopeAliveDuring=true
registeredAfter=0
fireAfterUnregister=-1
stubScopeAliveAfter=false
~~~

**Vì sao các dòng trên đúng?**

- `register_callback` trả 1 và lưu pointer → C báo đang registered.
- `fire_callback(7)` gọi `onValue(7)` → 14. Callback không tự hết hạn sau lần gọi đầu.
- `fire_callback(11)` → 22, minh họa pointer vẫn sống qua nhiều lượt gọi.
- `fire_callback(Integer.MAX_VALUE)` làm `Math.multiplyExact` ném `ArithmeticException` bên trong Java target, nhưng target bắt `Throwable` và trả sentinel `Integer.MIN_VALUE`; C không nhận một Java exception vượt qua ABI.
- Khi còn trong arena, `stub.scope().isAlive()` là true.
- Java gọi `unregister_callback`; C xóa pointer. `is_registered` trả 0 và `fire_callback` từ chối gọi, trả -1.
- Java thoát `try` và đóng arena; dù `escapedStub` vẫn là object Java, scope không còn sống nên trả false.

Đầu ra trên được suy luận từ mã và contract API; việc có thể chạy thành công phụ thuộc JDK, C compiler và việc nạp native library đúng môi trường. **Không cần, và không an toàn, cố gọi pointer sau arena.close để kiểm tra crash.**

## 6. Vì sao có ba thời gian sống riêng?

**Thời gian sống 1 — stub native.** `Linker.upcallStub` gắn stub vào arena. Khi arena đóng thành công, native code không còn quyền gọi địa chỉ đó.

**Thời gian sống 2 — registration C.** C có thể giữ pointer trong global variable, struct, event queue hoặc truyền đến thread. FFM không tự được thông báo khi một C library không còn muốn gọi callback.

**Thời gian sống 3 — state Java và native library.** Java target có thể dùng object, buffer hay arena thứ hai. Thư viện C cũng cần mã máy/ABI tồn tại đủ lâu. Đóng state khác hoặc unload shared library quá sớm có thể làm callback lỗi dù stub arena vẫn sống.

| Thời gian sống | Điều kiện kết thúc an toàn |
|---|---|
| Stub arena | Native đã không còn khả năng gọi pointer |
| Java callback state | Callback cuối cùng đã hoàn tất và không còn user |
| Native registration | Đã unsubscribe và được SDK xác nhận drained |
| Library lookup | Không còn callback/downcall/native worker cần mã library |
| Native user data | Không còn borrowed pointers/slices được callback hoặc C dùng |

**Giữ `MemorySegment stub` trong Java field không đủ nếu `arena.close()` đã xảy ra.** Cũng không dùng `Arena.ofAuto()` chỉ vì GC quản lý lifetime: một pointer thô được C giữ không tự động kéo dài reachability của Java owner.

## 7. Callback đồng bộ và callback trì hoãn

### Chỉ gọi đồng bộ, không giữ function pointer

~~~c
typedef int32_t (*callback_fn)(int32_t);

int32_t call_once(callback_fn fn, int32_t x) {
    return fn(x);
}
~~~

Đây là hàm C minh họa. Nếu hợp đồng C **bảo đảm không giữ pointer khi `call_once` return**, có thể dùng arena ngắn:

~~~text
Arena create
  -> upcallStub
  -> downcall(call_once)
      -> C gọi Java target
      -> C return
  -> arena.close
~~~

### Đăng ký để gọi lại sau

~~~c
static callback_fn stored;

void subscribe(callback_fn fn) {
    stored = fn;
}
~~~

Đây là mảnh C minh họa, **không an toàn khi truy cập đồng thời nếu thiếu khóa**. `subscribe` chỉ giữ pointer; callback có thể xảy ra sau khi Java method return, bởi timer, packet mạng, GPU completion, native worker hoặc SDK event loop. Arena phải sống đến khi toàn bộ subscription kết thúc, không chỉ qua lời gọi `subscribe`.

Một API có tên `stop` không chứng minh callback đã dừng. Hãy kiểm tra tài liệu SDK xem `stop` là synchronous drain hay chỉ là yêu cầu dừng sẽ hoàn tất về sau.

## 8. Unregister chưa chắc đã loại bỏ callback đang chạy

Race nguy hiểm:

~~~text
Native thread A                     Java thread B
      |                                   |
load g_callback                        unregister()
      |                                   |
      |                              g_callback = NULL
      |                                   |
      +-- đã cầm bản sao pointer      arena.close()
      |                                   |
      +---------------------> gọi pointer đã free
~~~

Trong C, một thread có thể đọc `g_callback` vào biến local trước khi thread khác xóa biến global. Dù global pointer là NULL sau unregister, bản copy cũ vẫn tồn tại.

### Strong unregister và weak unregister

| SDK contract | Sau khi unregister return | Được close arena ngay? |
|---|---|---|
| **Synchronous unregister and drain** | Không còn registration, callbacks queued/active hoặc bản sao pointer nào sẽ gọi nữa | Có, nếu đó là bảo đảm được SDK ghi rõ |
| **Remove-from-registry only** | Ngăn callbacks mới nhưng callback đã chạy hoặc đã được worker giữ pointer có thể tiếp tục | Không; phải join/drain |
| **Asynchronous unregister request** | SDK đã nhận lệnh, chưa hoàn tất | Không; phải đợi confirmation |
| **Unregister + completion future** | Future có thể báo request accepted hoặc callback quiescent, tùy contract | Chỉ close sau milestone “no future callback possible” |
| **Không có unregister API** | Pointer có thể tồn tại suốt lifetime SDK | Giữ arena sống cho đến khi SDK không còn có thể gọi, có thể cần process lifetime |

Một API có response `OK` chỉ báo “yêu cầu đã nhận” có thể không đồng nghĩa các worker đã ngừng. Phải phân biệt **acceptance**, **cancellation** và **completion**.

## 9. Giao thức native đa luồng: quiescence/lease

Trong SDK thực, cần một state machine và đồng bộ hóa:

~~~text
              ACTIVE
                |
    native event takes lease
                |
      in_flight += 1
                |
       Java callback runs
                |
      in_flight -= 1
                |
 request_unregister()
                |
              STOPPING
      no new leases granted
      cancel/drain queued jobs
      wait in_flight == 0
                |
             QUIESCENT
                |
       Java arena.close()
                |
              CLOSED
~~~

Một thuật toán minh họa C với `mutex`/`condition variable`:

~~~text
register(callback):
  lock(mutex)
  if state != UNREGISTERED: fail
  store callback pointer
  state = ACTIVE
  unlock(mutex)

reserve_and_invoke(value):
  lock(mutex)
  if state != ACTIVE: unlock; return NO_CALLBACK
  in_flight++
  local_callback = callback
  unlock(mutex)

  result = local_callback(value)  // không giữ mutex khi upcall

  lock(mutex)
  in_flight--
  if state == STOPPING && in_flight == 0:
    signal(all_done)
  unlock(mutex)
  return result

unregister_and_drain():
  lock(mutex)
  state = STOPPING
  callback = NULL
  prevent_new_reservations()
  cancel_or_count_queued_work()
  while in_flight != 0 || queued_work_can_call:
    wait(all_done, mutex)
  state = QUIESCENT
  unlock(mutex)
  return COMPLETE
~~~

Đây là **pseudocode**, không phải C11 source runnable. Muốn triển khai phải định nghĩa mutex, condition variable, memory ordering và cách bảo đảm counters luôn được giảm kể cả khi native worker gặp lỗi. Mục đích chính:

1. **Tăng số lượt đang chạy trước khi thả lock và trước khi worker dùng pointer.**
2. **Ngăn lượt mới bằng cùng lock/protocol** khi chuyển STOPPING.
3. Không close arena cho đến khi số leases và queued jobs có thể gọi callback trở về zero.
4. Chỉ báo QUIESCENT khi đã thực sự không còn nơi nào có thể gọi pointer.

Nếu native worker **đưa pointer vào queue** trước khi bắt đầu invocation, queue item cũng phải được xem là một lượt giữ quyền dùng, hoặc phải được hủy an toàn trước close. Chỉ đếm số target Java đang chạy không đủ trong trường hợp queue còn pointer.

### Không giữ lock khi vào Java callback

Nếu native giữ mutex của registry rồi gọi Java target, và target reentrant gọi `unregister` hoặc API khác cũng cần mutex, dễ deadlock. Cách đúng là tăng `in_flight` dưới lock, thả lock trước upcall, rồi giảm counter sau khi upcall trả về.

### Callback tự yêu cầu close có thể tự deadlock

~~~text
C callback enters Java target
  -> Java target gọi owner.close()
  -> close yêu cầu native_unregister_and_drain()
  -> drain chờ in_flight == 0
  -> in_flight chứa chính callback hiện tại
  -> callback không thể return vì đang chờ drain
~~~

Hãy **defer phần drain/close** sang coordinator ngoài callback, hoặc thiết kế giao thức không chờ chính nó. Không đóng stub arena khi callback hiện tại vẫn chưa hoàn tất.

## 10. Java owner và state machine

Với callback dài hạn, một wrapper nên sở hữu `Arena`, `MethodHandle`, `MemorySegment stub`, registration token và trạng thái.

| State | Có thể phát callback? | Được close arena? |
|---|---|---|
| NEW | Không | Được nếu chưa trao pointer |
| REGISTERING | Có thể, tùy C register gọi đồng bộ | Chưa rõ cho đến khi biết kết quả |
| ACTIVE | Có | **Không** |
| STOPPING | Callback đang chạy/queued vẫn có thể xảy ra | **Không** |
| QUIESCENT | Native đã xác nhận không còn caller | **Có** |
| CLOSED | Không | Không gọi close lần hai |
| FAILED_STOP | Có thể còn native caller | Không an toàn để close cưỡng bức |

Mô hình owner:

~~~text
CallbackOwner.start():
  tạo arena
  tạo MethodHandle và upcall stub
  gọi native register
  nếu success: state ACTIVE

CallbackOwner.close():
  chuyển ACTIVE -> STOPPING (khóa lifecycle)
  stop accepting new operations
  call native unregister_and_drain
  nếu native xác nhận QUIESCENT:
      arena.close()
      state = CLOSED
  nếu thất bại:
      state = FAILED_STOP
      không deallocate stub khi native còn có thể gọi
~~~

Đây là **khung thuật toán**, không phải class biên dịch độc lập. Nếu wrapper muốn `close()` idempotent, nó phải bảo đảm chỉ một caller gọi `Arena.close()` thật sự; bản thân `Arena.close()` **không idempotent** và có thể ném `IllegalStateException` khi close lần hai.

Không giữ lifecycle lock trong khi chờ native drain nếu callback đang hoàn tất cần chính lock đó, vì sẽ deadlock. Có thể đánh dấu STOPPING dưới lock, release lock, đợi native, rồi reacquire để commit CLOSED.

### Một bẫy của try-with-resources

`try (Arena arena = ...)` tự động gọi `close()` ở mọi đường rời scope, **kể cả khi unregister lỗi**. Điều này có thể gây UAF nếu native còn giữ pointer. Ví dụ runnable an toàn do unregister C đồng bộ, không lỗi và single-thread; SDK thật có unregister bất đồng bộ/thất bại phải dùng owner điều phối để **chỉ close sau quiescence**.

Nếu không thể xác nhận C đã thôi dùng pointer, giữ arena sống và báo lỗi resource leak có kiểm soát đôi khi an toàn hơn giải phóng stub mà C vẫn có thể gọi. Đây là trạng thái cần khắc phục về kiến trúc, không nên nuốt lỗi.

## 11. Không cho Java exception thoát khỏi upcall target

`Linker.upcallStub` tạo cầu nối trực tiếp từ C function pointer vào Java target. Theo JDK 22 `Linker`, nếu target ném exception vượt qua biên giới upcall, JVM **có thể kết thúc đột ngột**. Vì vậy callback boundary cần catch lỗi và trả status theo C ABI.

Trong ví dụ:

~~~java
private static int onValue(int value) {
    try {
        return Math.multiplyExact(value, 2);
    } catch (Throwable failure) {
        return Integer.MIN_VALUE;
    }
}
~~~

Đây là method hợp lệ. `Math.multiplyExact(Integer.MAX_VALUE,2)` ném `ArithmeticException`, nhưng được bắt, nên C nhận số sentinel thay vì Java exception.

Trong production:

- Catch ở vòng ngoài cùng của callback bridge, kể cả khi callback gọi user listener hoặc plugin.
- Chuyển lỗi thành mã trả về/đưa vào queue xử lý lỗi với policy rõ, không throw qua upcall.
- Đừng dùng logger phức tạp trong catch nếu logger có thể lại throw.
- Không mặc định mọi `Error` đều có thể recovery; việc bắt `Throwable` chỉ là hàng rào không vượt qua ABI.
- Callback phải trả đúng carrier type; một nhánh lỗi của `int(int)` cũng phải trả `int`.
- Đối với callback `void`, không thể tùy tiện trả một integer error code; cần giao thức status khác.
- Không cho rằng catch Java sẽ cứu được mismatch ABI C, use-after-free của stub, hoặc native memory corruption.

## 12. Thread confinement và callback state

Một native SDK có thể gọi callback từ thread khác thread đăng ký, hoặc nhiều native threads đồng thời. Nếu Java target dùng `ArrayList`, mutable map, native segment confined, UI state hoặc `ThreadLocal`, những điều này phải được xem xét riêng.

- `Arena.ofShared()` thường dễ phù hợp khi callback có khả năng cross-thread và cần đóng tường minh.
- `Arena.ofConfined()` phù hợp với một số lời gọi đồng bộ/được confined rõ ràng; đừng giả định native thread tùy ý có thể truy cập tài nguyên confined.
- `Arena.ofAuto()` không tạo completion handshake và GC không biết C pointer vẫn còn sử dụng.
- `Arena.global()` tồn tại không giới hạn, có thể tạo memory leak khi registrations ngắn hạn lặp lại.

**Shared arena không đồng nghĩa callback target thread-safe.** Nếu nhiều threads cập nhật state, dùng synchronization/atomic hoặc actor/event-loop. Không giữ `JNIEnv*` của thread này để dùng trên thread khác nếu hệ thống còn có JNI code, vì `JNIEnv*` gắn với thread.

Một callback còn sống có thể truy cập một native segment khác đã bị đóng: arena của **stub** còn sống không tự kéo dài lifetime các resources mà callback sử dụng. Owner phải quản lý cả graph dependency.

## 13. Native library lifetime cũng quan trọng

`SymbolLookup.libraryLookup(Path, Arena)` tải/truy xuất symbols và gắn lifetime lookup/library với arena, theo hợp đồng API. Nếu đóng arena của library trong khi native code đang chạy hoặc callback chưa unregister, có rủi ro **unload** mã còn cần dùng.

Ví dụ Java dùng cùng arena cho lookup và stub. Điều này hợp lý vì cả hai chỉ được release sau khi C không còn registration. Với ứng dụng có library lifetime dài hơn callback lifetime, có thể dùng arena hoặc loader riêng, nhưng cần thứ tự rõ:

~~~text
load library
  -> create stub and register
  -> callbacks active
  -> unregister + drain
  -> close stub arena
  -> khi không còn downcall/native work: release library lifetime
~~~

`System.loadLibrary` + `SymbolLookup.loaderLookup()` có chính sách symbol visibility và classloader lifetime khác `libraryLookup(Path,Arena)`. Không đổi qua lại chỉ vì tên API gần giống. Trong mọi trường hợp, callback pointer không được tồn tại lâu hơn cả stub và native code cần thiết.

## 14. Callback có captured state

Một target có thể là `MethodHandle` đã bind vào một Java object:

~~~java
final class Stats {
    private long events;

    synchronized int onEvent(int value) {
        events++;
        return value + 1;
    }
}
~~~

Đây là class minh họa. Một `findVirtual` + `bindTo(stats)` có thể làm target mang state `Stats`. Cần thiết kế:

- State Java phải còn reachable theo lifecycle của owner.
- Nếu state có `close()`, không close trước khi callback cuối cùng hoàn tất.
- Nếu callbacks song song, state phải thread-safe.
- Không dùng `WeakReference` để “biết lúc nào C không còn muốn callback”: GC không quản lý C registration.
- Tránh callback nhận sự kiện sau STOPPING rồi tiếp tục dùng resources đã đóng; policy có thể trả mã “stopped” nhưng stub chỉ được free sau drain.

Giữ một field `target`/`state` trong owner giúp rõ quyền sở hữu, nhưng **không cứu stub** nếu arena đóng. Thời hạn của state và thời hạn của native function pointer phải được quản lý đồng thời.

## 15. Những lỗi thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Đóng arena ngay khi `register` return | C vẫn giữ function pointer | Giữ arena xuyên toàn bộ registration |
| Giữ `MemorySegment stub` field nhưng đóng arena | Java reference không giữ backing native đã bị free | Chỉ close sau drain |
| `unregister` chỉ xóa pointer global | Worker khác có thể đã copy pointer | Count in-flight/queued leases |
| Dùng `Arena.ofAuto()` vì C sẽ giữ pointer | GC không biết raw C pointer là Java strong reference | Explicit owner + close |
| Dùng global arena cho hàng ngàn callbacks | Không deallocate stub đúng hạn | Arena per registration/owner |
| Descriptor dùng `JAVA_LONG` thay `ADDRESS` | Sai ABI cho function pointer | Đúng `ADDRESS` |
| Target Java có type không khớp C typedef | Undefined behavior/crash | Validate ABI trước register |
| Target throw exception xuyên FFM | JVM có thể terminate abruptly | Catch và trả status |
| Native giữ mutex khi upcall Java | Callback reentrant có thể deadlock | Lease trước, unlock rồi call |
| Callback tự gọi close và đợi drain | Callback chờ chính nó | Defer close tới sau callback |
| `shutdownNow()` rồi close | Worker có thể còn chạy | Actual join/completion |
| Test bằng cách gọi pointer sau close | Có thể crash cả tiến trình | Chỉ kiểm tra scope/registry, không dereference |
| Không xử lý register failure | Arena có thể rò rỉ hoặc C giữ pointer không rõ | Hợp đồng register atomic, cleanup đúng |
| Unregister lỗi nhưng `try` vẫn close | C có thể gọi địa chỉ free | Quarantine, chỉ close sau quiescence |
| Library bị unload trước unregister | Code native còn được dùng | Stop/drain trước unload |
| Copy pointer sang long và dùng lại | Không có temporal bounds khi C dùng raw address | Không xuất pointer vô thời hạn |
| Callback state đã close trước callback cuối | Stub alive nhưng state invalid | Gắn state lifetime với registration |
| Nhiều Java closers | Double-close arena, race | Một owner, state machine/lock |
| Dùng sleep để chờ worker | Timing không chứng minh quiescence | Future/join/condvar/ack thực |
| Không đếm queued jobs | Worker có pointer nhưng chưa in-flight | Reservation lease từ khi queue nhận pointer |

## 16. Kiểm thử an toàn

Đừng dựa vào việc “chưa từng crash” để chứng minh một callback sống đúng hạn. Test các điều kiện quan sát được mà **không gọi freed pointer**:

1. Register thành công, C báo trạng thái ACTIVE.
2. C gọi callback trong lần downcall thứ nhất và trả giá trị đúng.
3. C gọi callback lần hai sau khi `register` đã return, xác nhận stub còn dùng được.
4. Java target cố ý phát sinh một exception nội bộ được catch, C nhận sentinel, JVM không crash.
5. Unregister trả về trạng thái không còn pointer trong C registry.
6. Gọi `fire` **sau unregister nhưng trước arena.close**: C phải từ chối mà không dereference pointer.
7. Đóng arena sau khi đã chứng minh native QUIESCENT; kiểm tra `stub.scope().isAlive()==false`.
8. Không thực hiện callback qua stub đã close.
9. Register failure không để lại partial registration mơ hồ.
10. Trường hợp hai native threads: unregister chặn lượt mới, chờ mọi in-flight calls.
11. Queued-but-not-started events được cancel/đếm trước khi free.
12. Callback reentrant gọi requestStop không tự deadlock.
13. Unregister timeout không tự động làm close arena.
14. Hai Java close callers không tạo double-close.
15. Native library còn sống khi callback và downcall chưa hoàn tất.
16. Test memory leak/native allocations khi đăng ký/hủy lặp lại.
17. Test target state, captured references, Java classloader lifetime trong môi trường plugin.
18. Test ABI/architecture trên đúng OS/CPU của production.

Các tests race nên dùng `CountDownLatch`, barrier hoặc native condition variable để điều phối, không dựa vào `Thread.sleep(...)`. Native sanitizer có thể giúp phát hiện use-after-free ở mã C, nhưng không nên cố tình dereference một địa chỉ stub đã free trong một JVM đang làm việc.

## 17. Câu hỏi tự luyện

**1. `upcallStub` trả gì?** Một `MemorySegment` zero-length có địa chỉ C function pointer; lifetime gắn với arena được truyền vào.

**2. C đã lưu pointer, Java method đăng ký return. Có được close arena không?** Không, trừ khi contract chứng minh C không thể gọi lại pointer về sau.

**3. Vì sao giữ Java field `stub` vẫn chưa đủ?** Vì arena có thể đã close; reference còn sống không khiến native trampoline được tái cấp phát.

**4. `register_callback` và chính callback dùng cùng FunctionDescriptor không?** Không. Register nhận `ADDRESS`, còn callback ví dụ nhận/trả `JAVA_INT`.

**5. SDK xóa biến pointer global, nhưng native thread đã copy pointer. Có an toàn close không?** Chưa. Phải đợi hoặc hủy lượt giữ pointer đã tồn tại.

**6. `Arena.ofAuto()` có phù hợp cho callback C giữ lâu không?** Không phải cách đảm bảo lifecycle; GC không biết một C pointer thô là registration cần giữ sống.

**7. Arena.ofShared có tự đồng bộ mutable state trong Java target không?** Không. Target và native registry cần synchronization riêng.

**8. Nếu Java callback ném exception thì sao?** JDK 22 cảnh báo JVM có thể chấm dứt đột ngột nếu exception vượt upcall boundary. Catch ở target và trả mã lỗi C.

**9. Callback tự gọi unregister-and-drain có thể gặp lỗi gì?** Self-deadlock nếu drain đợi callback hiện tại hoàn tất. Hãy defer close.

**10. Vì sao ví dụ gọi fire sau unregister vẫn an toàn?** C kiểm tra pointer NULL rồi trả -1, không gọi địa chỉ stub cũ.

**11. Chỉ `Future.get()` của việc submit native job đã đủ chưa?** Không, nếu nó chỉ xác nhận submit, không xác nhận native callback consumer đã dừng.

**12. Close một arena lần hai có phải no-op không?** Không. `Arena.close()` không idempotent; wrapper phải quản lý state để tránh lặp.

## Tài liệu tham chiếu

- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): `upcallStub`, native function pointer, ABI safety, target exception handling.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): scope, lifetime, `ofShared`/`ofConfined`, close semantics.
- [Oracle Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): `libraryLookup(Path, Arena)` và lifetime của library.
- [Oracle Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): native calling signatures cho upcalls/downcalls.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): zero-length address segment và scope.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM ổn định trong JDK 22.
- [Dev.java — Troubleshoot Calls to Native Library Functions](https://dev.java/learn/api/io/ffm/troubleshoot/): restricted native access và tùy chọn `--enable-native-access`.

## Ghi nhớ

**Upcall stub là con trỏ hàm native có lifetime được điều khiển bằng Arena.** Native library còn có thể gọi pointer thì arena phải sống.

Chuỗi xử lý đúng:

1. Tạo target `MethodHandle` có type khớp `FunctionDescriptor` và C ABI.
2. Tạo stub bằng `Linker.upcallStub` trong arena do một owner quản lý.
3. Đăng ký pointer; giữ arena/stub/target state sống xuyên mọi thời điểm thư viện còn có thể callback.
4. Khi ngừng, ngăn callback mới, unregister pointer, cancel/drain queue, chờ in-flight calls hoàn tất.
5. Chỉ khi đã **quiescent**, gọi `arena.close()` một lần; đồng thời quản lý library lookup lifetime.
6. Không để Java throwable vượt qua upcall; trả status theo C protocol.
7. Không thử gọi freed pointer để test: đó có thể là lỗi an toàn bộ nhớ khiến JVM sập.

**Một câu cần nhớ:** *Vòng đời callback kết thúc khi thư viện không còn khả năng gọi lại, không phải khi phương thức Java đăng ký đã trả về.*
