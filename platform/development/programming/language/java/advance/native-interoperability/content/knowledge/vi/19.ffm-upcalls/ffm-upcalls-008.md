# Truyền trạng thái ứng dụng qua tham số user data theo hợp đồng C

## 1. Mục tiêu và vấn đề cần giải quyết

Trong **Foreign Function & Memory API (FFM)**, Java có thể đưa một **function pointer** cho C để C gọi lại mã Java (**upcall**). Nhiều C APIs dùng một chữ ký callback gồm các đối số nghiệp vụ và con trỏ **void *user_data**:

~~~c
typedef void (*event_callback)(int32_t value, void *user_data);
int32_t emit_twice(int32_t first, event_callback callback,
                   void *user_data);
~~~

**user_data** còn được gọi là *client data*, *context*, *cookie* hoặc *opaque pointer*. Caller truyền một giá trị ngữ cảnh khi đăng ký/gọi callback; thư viện C trả lại đúng giá trị đó mỗi khi callback diễn ra. Nhờ vậy Java xác định **event thuộc request, session hoặc đối tượng nghiệp vụ nào** mà không cần để C hiểu Java object model.

Sau bài này, bạn sẽ biết:

1. Đọc hợp đồng C về **void\***, số lần callback, khả năng lưu pointer, thread và quyền sở hữu.
2. Ánh xạ **void\*** sang **ValueLayout.ADDRESS**/**MemorySegment** và khai báo **FunctionDescriptor** cho callback/đường gọi C.
3. Tạo **Linker.upcallStub** trỏ vào Java MethodHandle với đúng ABI.
4. Chuyển ứng dụng state bằng **opaque token + Java registry**, không giả mạo địa chỉ Java object.
5. Phân biệt cách dùng **native struct** làm user_data nếu C thực sự cần đọc dữ liệu.
6. Quản lifetime của **token**, **upcall stub**, **Java State** và **native library**, đặc biệt với callback bất đồng bộ.
7. Chặn Java exception thoát qua upcall, tránh race, dangling pointer, ABA và resource leak.
8. Chạy ví dụ **Java 22+ và C11** đầy đủ, có stdout xác định và kiểm thử được.

**Baseline:** Gói **java.lang.foreign** ổn định từ JDK 22 theo JEP 454. Các ví dụ dùng **Java 22+**; không tuyên bố chạy nguyên xi trên Java 17 vì FFM ở giai đoạn đó có API khác.

## 2. Sơ đồ ứng dụng Java gửi state qua C

~~~text
Java State A       Java State B
     |                  |
     v                  v
Token A             Token B
     |                  |
     +--------+---------+
              |
      C API nhận callback pointer
        và void *user_data
              |
        C phát sinh event
              |
 C gọi callback(value, user_data)
              |
       FFM upcall stub
              |
     Java callback nhận address
              |
   Registry ánh xạ address -> State
              |
    Cập nhật đúng State A hoặc B
~~~

Có **ba đối tượng có vòng đời độc lập**:

| Đối tượng | Công dụng | Quy tắc sở hữu |
| --- | --- | --- |
| **Upcall stub** | Function pointer C gọi được, tạo bởi **Linker.upcallStub** | Arena chứa stub phải sống khi C có thể gọi callback |
| **user_data** | C pointer C lưu/echo hoặc đọc theo hợp đồng | Owner của token/struct phải giữ vùng memory hợp lệ và chỉ free đúng lúc |
| **Java State** | Session, Counter, Handler, Context trên Java heap | Phải có strong reference đến khi callback cuối đã xong |

**Không nên đánh đồng** function pointer, native token và Java object: một MemorySegment trả về từ FFM không tự giữ sống mọi Java object liên quan. Một con trỏ **void\*** cũng không đương nhiên cho C quyền free dữ liệu.

## 3. Hợp đồng C quan trọng hơn tên user_data

C API có thể dùng tham số giống nhau nhưng hành vi khác nhau:

| Điều cần xác nhận | Câu hỏi chính |
| --- | --- |
| **Synchronous/Asynchronous** | Callback chạy trong downcall hay C giữ pointer để gọi về sau? |
| **Opaque/Readable** | C chỉ echo nguyên pointer hay thực sự đọc struct ở địa chỉ đó? |
| **Nullability** | user_data hoặc callback được phép NULL không? |
| **Ownership** | Java caller chỉ cho C mượn pointer hay chuyển quyền free cho C? |
| **Lifetime** | Pointer phải sống tới khi hàm trả về, unsubscribe hay hết session? |
| **Thread** | Callback gọi trên thread Java đang downcall hay native worker? |
| **Concurrency** | C có gọi nhiều callback cùng lúc hoặc reentrant không? |
| **Unregister** | Unregister có chờ callback đang chạy hoàn tất không? |
| **Error model** | Callback return có mã lỗi không? Nếu callback fail, C sẽ làm gì? |
| **ABI** | Các đối số thực tế là int32_t, long, size_t, pointer hay struct? |

Không có các thông tin này, **FFM không thể tự suy ra contract của void\*** từ một FunctionDescriptor. Việc tạo MethodHandle thành công không xác nhận rằng C sẽ không giữ pointer.

### Hai dạng hợp đồng tiêu biểu

**Đồng bộ, không lưu pointer:**

~~~c
/* Contract: cb và ctx chỉ được mượn trong lời gọi này. */
int32_t emit(int32_t value, event_callback cb, void *ctx);
~~~

Java có thể cấp token/stub trong **Arena.ofConfined()**, gọi C và đóng arena **sau khi** downcall hoàn tất.

**Bất đồng bộ, lưu pointer:**

~~~c
/* Contract: C giữ cb/ctx cho đến khi unregister + drain. */
int register_cb(event_callback cb, void *ctx);
void unregister_cb(void);
void wait_callbacks_finished(void);
~~~

Đây là **header minh họa**, không phải C implementation runnable. Java phải giữ token/stub và State sống đến sau **unregister + drain**. Không dùng request-local arena rồi đóng ngay khi **register_cb** trả về.

## 4. ABI của callback và con trỏ void*

Với:

~~~c
typedef void (*event_callback)(int32_t value, void *user_data);
~~~

Đường từ Java sang C được mô tả bằng:

~~~java
FunctionDescriptor callbackDescriptor =
    FunctionDescriptor.ofVoid(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS
    );
~~~

Java callback target cần kiểu:

~~~java
private static void onEvent(int value, MemorySegment userData) {
    // value ứng với int32_t; userData ứng với void*.
}
~~~

**ValueLayout.ADDRESS** có carrier **MemorySegment**, không phải int hoặc Java object. **ValueLayout.JAVA_INT** phù hợp int32_t ở các ABI thông dụng được ví dụ hỗ trợ. Nếu header dùng **C long** hoặc **size_t**, phải chọn layout theo native ABI, không tự ép thành Java long xuyên OS.

### Zero-length pointer không phải buffer rỗng thật

Một address được C đưa vào upcall thường hiện ra dưới dạng **MemorySegment kích thước 0**, mang địa chỉ thật và scope toàn cục. Đây là cách FFM tránh tự bịa số byte hợp lệ:

~~~java
long tokenAddress = userData.address(); // Có thể dùng như opaque key.
// KHÔNG gọi userData.get(JAVA_INT, 0) khi chưa biết bounds.
~~~

MemorySegment zero-length **không có nghĩa C đã cấp 0 byte**, mà có nghĩa Java **không biết độ dài**. Nếu bạn dùng **reinterpret(size)** hoặc **AddressLayout.withTargetLayout(...)** để đọc, phải chứng minh size/alignment/lifetime theo C contract; các API này là restricted và không thể tự ngăn pointer giả hoặc đã free.

### Không truyền Java object trực tiếp như con trỏ

Không dùng **System.identityHashCode(state)** làm pointer: đó chỉ là hash số nguyên, có thể trùng và không phải địa chỉ native hợp lệ. Không ép reference Java thành **void\*** rồi để C dereference: Java heap chịu GC và không cung cấp một pointer ổn định theo FFM contract.

Hai phương án rõ ràng là **native token có địa chỉ thật rồi tra Java registry**, hoặc **native struct có ABI/layout đã kiểm chứng**.

## 5. Phương án A: opaque token và Java registry

Khi C **chỉ giữ/echo pointer, không đọc nội dung**, bạn có thể cấp một token 1 byte trong Arena:

~~~java
MemorySegment token = arena.allocate(1);
long key = token.address();
~~~

Sau đó:

1. Tạo State thuộc Java, ví dụ Counter hoặc RequestContext.
2. Đưa **key → State** vào **ConcurrentHashMap<Long, State>**, giữ State bằng strong reference.
3. Truyền token cùng upcall stub cho C.
4. Khi C callback, Java nhận MemorySegment userData, lấy **address()** và tra map.
5. Cập nhật State; không để exception thoát qua callback.
6. Chờ xác nhận C đã ngừng sử dụng token; **remove** entry, rồi đóng Arena.

Token 1 byte **không chứa State**; kích thước nhỏ chỉ tạo một native pointer hợp lệ. C không được dereference nó nếu contract nói opaque.

### Vì sao cách này phù hợp?

Java State có thể là một object phức tạp gồm dịch vụ, queue, collection, metadata và các invariant nghiệp vụ. C không cần hiểu hoặc sao chép những field đó; C chỉ trả một native address. Registry giải quyết từ native identity sang Java State.

### Giới hạn quan trọng

- Registry không phải cơ chế xác thực bảo mật: native library có thể đưa địa chỉ không được đăng ký. Hãy kiểm tra missing key.
- Nếu quên **remove**, registry giữ State sống vô hạn → Java heap leak.
- Nếu remove trước khi callback cuối xong, callback có thể không tìm thấy State.
- Native allocator có thể tái sử dụng **cùng địa chỉ** cho token mới sau khi token cũ được free. Callback trễ có thể nhầm State mới (**ABA**); phải chặn callback đến muộn bằng teardown barrier, có thể thêm generation/session ID nếu API hỗ trợ.
- ConcurrentHashMap bảo vệ thao tác map, **không tự bảo đảm** State, native worker hay Arena teardown an toàn.

## 6. Phương án B: truyền một native struct

Nếu C thực sự **đọc context**, một struct có layout cụ thể phù hợp hơn:

~~~c
#include <stdint.h>

typedef struct AppContext {
    int32_t request_id;
    int32_t multiplier;
} AppContext;
~~~

Java mô tả vùng native (trên ABI phù hợp):

~~~java
MemoryLayout contextLayout = MemoryLayout.structLayout(
    ValueLayout.JAVA_INT.withName("request_id"),
    ValueLayout.JAVA_INT.withName("multiplier")
);

try (Arena arena = Arena.ofConfined()) {
    MemorySegment context = arena.allocate(contextLayout);
    context.set(ValueLayout.JAVA_INT, 0, 101);
    context.set(ValueLayout.JAVA_INT, 4, 3);
    // Truyền context như void* khi callback/C API dùng trong scope.
}
~~~

Đây là snippet chưa có downcall. C có thể trỏ tới struct và đọc các field **nếu** contract đồng ý. Java callback cần biết chính xác layout khi muốn đọc pointer được echo. **sizeof, alignof, offsetof** phải được kiểm chứng với native binary thực nếu struct phức tạp, có packing hoặc typedef theo ABI.

Một cách khai báo target layout:

~~~java
AddressLayout contextPointer =
    ValueLayout.ADDRESS.withTargetLayout(contextLayout);

FunctionDescriptor desc = FunctionDescriptor.ofVoid(
    ValueLayout.JAVA_INT,
    contextPointer
);
~~~

Đây là snippet Java 22+ giả định đã import AddressLayout và tạo contextLayout. **withTargetLayout** là restricted API: nó cho FFM biết size kỳ vọng của pointee, **không chứng minh** C thực sự đã cấp vùng đó hoặc pointer vẫn sống. Đừng dùng kiểu này khi C contract chỉ nói user_data là opaque cookie không được dereference.

**Khi chọn cách nào?** Dùng **registry** nếu trạng thái Java phức tạp và C chỉ echo pointer. Dùng **native struct** nếu C cần đọc/ghi những trường dữ liệu đơn giản với ABI/lifetime đã xác minh.

## 7. Upcall stub và chính sách exception

Tạo function pointer từ một Java MethodHandle:

~~~java
Linker linker = Linker.nativeLinker();

MethodHandle target = MethodHandles.lookup().findStatic(
    UserDataCallbackDemo.class,
    "onEvent",
    MethodType.methodType(
        void.class, int.class, MemorySegment.class
    )
);

MemorySegment callback = linker.upcallStub(
    target,
    FunctionDescriptor.ofVoid(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS
    ),
    arena
);
~~~

Đây là snippet, giả định class có onEvent và arena còn sống. C có thể gọi địa chỉ stub như một **event_callback** đúng ABI.

**Cảnh báo quan trọng:** Theo JDK 22 Linker, Java callback MethodHandle **không được ném exception xuyên qua upcall**; một exception thoát ra có thể khiến JVM kết thúc đột ngột. Vì vậy callback cần **catch tại biên FFM** rồi ghi lỗi vào request State, AtomicReference hoặc trả mã lỗi theo C signature.

~~~java
private static void onEvent(int value, MemorySegment userData) {
    try {
        // Tra context và xử lý an toàn.
    } catch (Throwable failure) {
        // Báo lỗi qua state/queue riêng, KHÔNG rethrow qua C ABI.
    }
}
~~~

Đây là snippet mô tả nguyên tắc; production không được nuốt lỗi im lặng mà cần một kênh quan sát. Nếu callback C trả int status, có thể trả mã lỗi sau khi catch. Nếu C callback chạy trên thread nhạy latency, nên xử lý ngắn rồi gửi event sang queue có backpressure.

## 8. Ví dụ hoàn chỉnh: C11 gọi callback Java hai lần

Ví dụ này thực thi **contract đồng bộ**: C không lưu function pointer hoặc user_data sau khi trả về. Java có thể dùng **Arena.ofConfined()**, bởi callback chạy ngay trong lời gọi C trên thread đang thực hiện downcall.

Kết quả mong đợi: C gọi Java với value **10 và 11**, cả hai callback nhận cùng token và cập nhật cùng State.

### Bước 1 — Tạo userdata_callback.c

~~~c
#include <stdint.h>
#include <stddef.h>

#if defined(_WIN32)
#  define API __declspec(dllexport)
#else
#  define API __attribute__((visibility("default")))
#endif

typedef void (*event_callback)(
    int32_t value, void *user_data
);

/*
 * CONTRACT:
 * - callback và user_data không NULL;
 * - user_data là opaque, không dereference/không free;
 * - chỉ mượn hai pointers trong lời gọi này;
 * - hai callbacks đồng bộ, trên caller thread;
 * - không lưu callback/user_data sau khi return;
 * - return 2 nếu đã gọi hai lần; -1/-2 nếu input lỗi.
 */
API int32_t emit_twice(
    int32_t first,
    event_callback callback,
    void *user_data
) {
    if (callback == NULL || user_data == NULL) {
        return -1;
    }
    if (first == INT32_MAX) {
        return -2;
    }

    callback(first, user_data);
    callback(first + 1, user_data);
    return 2;
}
~~~

Điểm quyết định không nằm ở 2 callback mà ở **lời cam kết C không giữ pointers**. Nếu đổi implementation sang native worker gọi sau return, Java code bên dưới phải đổi scope/lifecycle theo session, không thể chỉ sửa một cờ.

### Bước 2 — Biên dịch shared library

**Linux:**

~~~bash
cc -std=c11 -O2 -fPIC -shared \
  userdata_callback.c -o libuserdatacallback.so
~~~

**macOS:**

~~~bash
clang -std=c11 -O2 -fPIC -dynamiclib \
  userdata_callback.c -o libuserdatacallback.dylib
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /nologo /W4 /LD userdata_callback.c /link /OUT:userdatacallback.dll
~~~

Ba lệnh là **các phương án thay thế theo hệ điều hành**, không chạy cả ba. Binary phải khớp OS/CPU/ABI của JVM. Đặt library ở thư mục làm việc dùng cho bước Java.

### Bước 3 — Tạo UserDataCallbackDemo.java

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

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class UserDataCallbackDemo {
    private static final ConcurrentHashMap<Long, State> REGISTRY =
            new ConcurrentHashMap<>();

    // Demo chạy một request duy nhất; production nên
    // lưu failure theo từng session/context.
    private static final AtomicReference<Throwable> CALLBACK_FAILURE =
            new AtomicReference<>();

    private static final class State {
        final AtomicInteger calls = new AtomicInteger();
        final AtomicInteger sum = new AtomicInteger();
        final AtomicInteger last = new AtomicInteger();
    }

    private UserDataCallbackDemo() {
    }

    // C signature: void callback(int32_t, void*).
    private static void onEvent(int value, MemorySegment userData) {
        try {
            State state = REGISTRY.get(userData.address());

            if (state == null) {
                CALLBACK_FAILURE.compareAndSet(
                        null,
                        new IllegalStateException("Unknown user_data")
                );
                return;
            }

            state.calls.incrementAndGet();
            state.sum.addAndGet(value);
            state.last.set(value);
        } catch (Throwable failure) {
            // Không để Throwable thoát qua C upcall boundary.
            CALLBACK_FAILURE.compareAndSet(null, failure);
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // Library scope phải sống dài hơn thời gian gọi native.
        try (Arena libraryArena = Arena.ofConfined()) {
            Path library = Path.of(
                    System.mapLibraryName("userdatacallback")
            ).toAbsolutePath();

            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, libraryArena);

            // C: int32_t emit_twice(int32_t,
            //                       event_callback, void*);
            MethodHandle emit = linker.downcallHandle(
                    symbols.find("emit_twice").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.ADDRESS
                    )
            );

            MethodHandle target =
                    MethodHandles.lookup().findStatic(
                            UserDataCallbackDemo.class,
                            "onEvent",
                            MethodType.methodType(
                                    void.class,
                                    int.class,
                                    MemorySegment.class
                            )
                    );

            FunctionDescriptor callbackDescriptor =
                    FunctionDescriptor.ofVoid(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS
                    );

            // Contract sync: stub/token chỉ cần sống tới
            // khi emit_twice trả về.
            try (Arena callArena = Arena.ofConfined()) {
                MemorySegment token = callArena.allocate(1);
                long key = token.address();
                State state = new State();

                if (REGISTRY.putIfAbsent(key, state) != null) {
                    throw new IllegalStateException(
                            "Token already registered"
                    );
                }

                try {
                    MemorySegment callback = linker.upcallStub(
                            target, callbackDescriptor, callArena
                    );

                    CALLBACK_FAILURE.set(null);
                    int delivered = (int) emit.invokeExact(
                            10, callback, token
                    );

                    Throwable failure = CALLBACK_FAILURE.get();
                    if (failure != null) {
                        throw new IllegalStateException(
                                "Callback failed", failure
                        );
                    }
                    if (delivered != 2) {
                        throw new IllegalStateException(
                                "C returned: " + delivered
                        );
                    }

                    System.out.println("delivered=" + delivered);
                    System.out.println(
                            "events=" + state.calls.get()
                    );
                    System.out.println(
                            "sum=" + state.sum.get()
                    );
                    System.out.println(
                            "last=" + state.last.get()
                    );
                } finally {
                    // C đã trả về và cam kết không giữ pointers.
                    REGISTRY.remove(key, state);
                }
            } // Arena đóng: token và upcall stub hết hiệu lực.

            System.out.println(
                    "registryEmpty=" + REGISTRY.isEmpty()
            );
        } // Sau cùng mới đóng library arena.
    }
}
~~~

### Bước 4 — Chạy Java 22+

~~~bash
javac UserDataCallbackDemo.java
java --enable-native-access=ALL-UNNAMED UserDataCallbackDemo
~~~

Ứng dụng classpath cần quyền native access cho **SymbolLookup.libraryLookup**, **Linker.downcallHandle** và **Linker.upcallStub**. Với ứng dụng modularized, cấp quyền cho đúng module cần thiết.

**Stdout chính xác nếu build/load và lời gọi native thành công:**

~~~text
delivered=2
events=2
sum=21
last=11
registryEmpty=true
~~~

Giải thích: C gọi hai lần với **10 và 11**; Java callback tra đúng địa chỉ token trong REGISTRY, cộng **10+11=21**, cập nhật last=11 và count=2. Sau khi C return, entry được xóa, nên registryEmpty=true. C không bao giờ dereference hoặc free token.

**Giới hạn demo:** Code là mẫu Java 22+/C11 hoàn chỉnh theo C contract đã mô tả. Output là kết quả dự kiến nếu build và thực thi thành công; phải thử integration trên toolchain/JDK mục tiêu trước deployment. Registry và error slot static chỉ phục vụ một request; production nhiều request nên có error tracking **theo context**.

## 9. Callback async và teardown đúng thứ tự

Với API có **register(callback, user_data)** rồi gọi callback về sau, phạm vi sống không còn là một downcall ngắn. Một session owner phải giữ:

- **Library lookup** và function pointers còn được load.
- **Upcall stub** hợp lệ cho toàn thời gian C còn giữ callback.
- **user_data token/struct** hợp lệ tới callback cuối.
- **Java State strong reference** trong map tới khi không còn callback sử dụng.
- **Cơ chế stop/unregister và drain/join** theo contract C.

Trình tự đóng an toàn:

~~~text
Session start
  1. Tạo owner Arena sống dài theo session
  2. Tạo token, State, registry entry, callback stub
  3. C register thành công
  4. C có thể gọi callbacks từ native worker
Session close
  5. Chặn request mới / đặt closing state
  6. C unregister
  7. Chờ C bảo đảm không còn callback in flight
  8. Remove token->State registry
  9. Close Arena chứa token và stub
 10. Unload library khi không còn user
~~~

**Unregister không đương nhiên bằng callback drained.** Nếu C có thể vẫn đang chạy callback, phải có thêm API/hợp đồng chờ. Đóng Arena trước khiến native pointer trỏ tới function stub đã giải phóng, có thể làm sập JVM. Xóa registry trước khiến callback tra không thấy State. Với API C thiếu shutdown barrier rõ, không có một try-with-resources đơn giản nào tự bảo đảm an toàn.

### Thread confinement và synchronization

- **Arena.ofConfined()** phù hợp cho callback đồng bộ trên thread tạo Arena như ví dụ.
- **Arena.ofShared()** thích hợp cho lifetime multi-thread khi cần, nhưng **không tự đồng bộ dữ liệu ứng dụng**.
- **ConcurrentHashMap** chỉ bảo vệ mapping, không bảo vệ lifecycle của mọi native consumer.
- **AtomicInteger** giúp từng phép update trong ví dụ an toàn, không tạo atomic snapshot giữa nhiều fields.
- Nếu native callback chạy đồng thời/reentrant, cần trạng thái session và cơ chế đóng có synchronization/active callback counter.
- Tránh lock dài quanh downcall có thể upcall cùng lúc; có nguy cơ reentrancy deadlock.

**FFM upcall không đồng nghĩa JNI JNIEnv callback.** Không chuyển một JNIEnv của Java thread sang native worker; nếu đồng thời dùng JNI, JNI thread rules vẫn áp dụng riêng.

## 10. Pointer lifetime, ABA và ownership

### 10.1. ABA khi tái sử dụng địa chỉ

Giả sử token cũ ở địa chỉ P được giải phóng. Native allocator có thể cấp lại đúng địa chỉ P cho session mới; callback trễ từ session cũ sẽ tra registry ra State mới. Đây là **ABA problem**.

Phòng ngừa chính là đảm bảo không có callback trễ **trước khi free token**. Khi API cho phép, dùng generation/unique handle để giảm nguy cơ nhầm danh tính; nhưng không dùng generation để biện minh việc dereference một pointer đã free.

### 10.2. Borrowed hay transferred ownership?

Nếu C API chỉ mượn user_data, **Java Arena** có thể sở hữu token và giải phóng khi đóng. Nếu C nhận **ownership transfer**, phải có owner/deallocator mới và đảm bảo Java không free cùng allocation. Không gọi libc free lên memory do Arena quản lý chỉ vì nó được truyền thành void*.

### 10.3. NULL pointer và invalid context

Không mặc định NULL có nghĩa “state mặc định”; một API có thể cho phép NULL như no context, hoặc cấm hoàn toàn. Đọc contract, kiểm tra status, và từ chối callback có key không tồn tại. Token từ memory cấp thật **không phải security token**: native library ác ý hoặc bị lỗi vẫn có thể đưa một địa chỉ khác.

### 10.4. Khi nào không nên dùng token 1 byte?

Nếu C **dereference user_data** như struct, token 1 byte không đủ. Phải cấp native struct đúng kích thước/alignment, dữ liệu được khởi tạo đúng ABI, và lifetime bao trùm mọi truy cập C. Không reinterpret pointer tùy ý thành một struct lớn rồi tin rằng FFM đã cấp đủ memory.

## 11. Các lỗi phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Ép Java object/hash thành void* | Địa chỉ sai/không ổn định | Native token + registry hoặc C struct |
| C callback nhận pointer zero-length rồi get() | Out-of-bounds | Dùng address() opaque hoặc layout được chứng minh |
| Sai FunctionDescriptor | ABI mismatch/crash | Đối chiếu C typedef và platform |
| Java callback throw qua upcall | JVM có thể terminate | Catch và ghi lỗi/return code |
| Đóng Arena sau register async | Dangling stub/user_data | Session lifetime + unregister/drain |
| Quên remove mapping | Java heap leak | Xóa khi C hết quyền callback |
| Remove mapping quá sớm | Missing state/race | Chờ in-flight callbacks xong |
| Dùng address vĩnh viễn làm identity | ABA | Quiescence + generation khi phù hợp |
| C free token Java Arena cấp | Invalid/double-free | Một owner, matching allocator |
| ConcurrentHashMap là toàn bộ synchronization | State/teardown race | Lock/atomic/in-flight tracking |
| C giữ pointer rồi Java dùng prefix buffer lại | Dữ liệu bị overwrite | Buffer riêng hoặc await completion |
| Library unload khi callback còn sống | Gọi code không còn hợp lệ | Library lifetime dài hơn |
| Callback chạy lâu, block hoặc reenter sai | Deadlock/latency | Callback ngắn, queue hợp đồng rõ |
| C đọc native struct nhưng Java truyền token 1B | Truy cập sai memory | Cấp struct đúng ABI và lifetime |

## 12. Checklist trước production

- [ ] Có C header đúng phiên bản và callback prototype chính xác.
- [ ] Xác định C **echo** hay **dereference** user_data.
- [ ] Có hợp đồng NULL, ownership, byte bounds và deallocator.
- [ ] Upcall MethodHandle phù hợp FunctionDescriptor, không throw qua ABI.
- [ ] Không dùng hash/object address của Java heap làm C pointer.
- [ ] Registry giữ State sống đủ lâu và có đường remove.
- [ ] Stub Arena và token Arena sống tới sau native callback cuối.
- [ ] Với async, unregister/drain bảo đảm không còn callback in flight.
- [ ] Không dùng lại token address khi callback cũ vẫn có thể đến.
- [ ] Thread affinity, concurrency và reentrancy có test thực.
- [ ] Library lookup sống lâu hơn callback và cleanup.
- [ ] Có test nhiều sessions, missing token, callback error, registration thất bại, close race và shutdown.
- [ ] Với native struct, có sizeof/alignment/offsetof test theo OS/ABI.
- [ ] Dùng native diagnostics nếu callback pointer sai gây crash.

## 13. Câu hỏi tự kiểm tra

**1. void *user_data có phải Java object reference không?**

**Trả lời:** Không. Đây là C pointer. Java State phải được giữ qua registry/handle rõ ràng hoặc chuyển dữ liệu cần thiết vào native struct.

**2. Vì sao native token 1 byte đủ cho ví dụ?**

**Trả lời:** C chỉ echo địa chỉ và không đọc byte nào. Allocation một byte cung cấp pointer hợp lệ trong lifetime đồng bộ.

**3. Callback nhận MemorySegment byteSize=0 có nghĩa C cấp 0 byte không?**

**Trả lời:** Không; Java chưa biết bounds. Có thể dùng address như opaque key, không được dereference tùy tiện.

**4. Khi nào có thể đóng callArena ngay sau downcall?**

**Trả lời:** Chỉ khi C contract bảo đảm không lưu callback/token và mọi callback đã hoàn tất trước khi downcall trả về.

**5. Vì sao không để callback ném RuntimeException?**

**Trả lời:** C ABI không truyền Java Throwable bình thường; FFM cảnh báo exception thoát khỏi upcall có thể làm JVM dừng đột ngột.

**6. ConcurrentHashMap có chặn được callback trễ sau arena.close không?**

**Trả lời:** Không. Cần unregister/drain đúng contract trước khi remove map và close.

**7. Java cần làm gì khi C thực sự đọc AppContext*?**

**Trả lời:** Cấp struct native đúng layout, size/alignment, khởi tạo field, bảo vệ lifetime và synchronization; không truyền token 1 byte.

**8. Vì sao không dùng System.identityHashCode làm user_data pointer?**

**Trả lời:** Hash không phải địa chỉ native, có thể trùng và không bảo vệ Java object trước GC.

**9. Với hai callback values 10 và 11, output sum=?**

**Trả lời:** **21**, do Java callback tìm cùng State từ user_data và cộng cả hai event.

**10. Cần đóng gì trước: Arena chứa callback hay native library?**

**Trả lời:** Sau unregister/drain, đóng Arena chứa stub/token; chỉ unload library khi không còn callback và các lời gọi native cần tới nó.

## Tài liệu tham khảo chính thức

- [JEP 454 — Foreign Function & Memory API hoàn thiện trong JDK 22](https://openjdk.org/jeps/454).
- [JDK 22 — Linker: downcall/upcall, function pointers, callback exception](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).
- [JDK 22 — MemorySegment: zero-length address, scope, reinterpret](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [JDK 22 — Arena: confined/shared và cleanup lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- [JDK 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html).
- [JDK 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).

**Kết luận:** **user_data là một hợp đồng C về ngữ cảnh và lifetime**, không phải một Java object hay một vùng nhớ được FFM quản tự động. Với C API chỉ echo pointer, dùng native token + Java registry để chọn đúng State; khi C cần dữ liệu, dùng native struct có layout được xác minh. Luôn giữ stub/token/State sống đủ lâu, xử lý callback exception và chờ callback cuối hoàn tất **trước khi** đóng Arena.
