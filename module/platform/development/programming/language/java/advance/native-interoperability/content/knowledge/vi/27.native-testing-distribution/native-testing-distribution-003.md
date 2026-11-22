# Kiểm thử lỗi cấp phát, mã lỗi thư viện, ngoại lệ callback và dọn dẹp một phần

Một chương trình Java giao tiếp với thư viện C/C++ có thể thất bại **sau khi đã cấp phát một phần tài nguyên**: vùng nhớ native được tạo nhưng handle chưa mở; handle đã mở nhưng đăng ký callback thất bại; callback đang xử lý lại ném ngoại lệ Java; hoặc quá trình `close()` chỉ giải phóng được một nửa tài nguyên. Kiểm thử đường đi thành công không thể chứng minh các trường hợp này an toàn.

Bài học này trình bày cách thiết kế *failure injection* (chủ động gây lỗi có kiểm soát), phân loại mã lỗi native, giữ ngoại lệ callback trong biên ABI và kiểm chứng *partial cleanup* trên Java 17+ với JNI, cũng như Foreign Function & Memory API (FFM) ổn định từ Java 22. Trọng tâm là **trạng thái ownership sau mỗi lỗi**: tài nguyên nào đã được tạo, còn ai có thể sử dụng nó, ai có quyền giải phóng và bằng chứng nào cho phép chuyển sang bước dọn dẹp tiếp theo.

## 1. Mô hình lỗi qua biên Java/native

| Nơi phát sinh | Biểu hiện điển hình | Cách quan sát | Tác động cần kiểm thử |
| --- | --- | --- | --- |
| Cấp phát trong Java | `OutOfMemoryError`, lỗi tạo wrapper hoặc cấu trúc theo dõi | Java throwable; test injector thay cho làm cạn RAM | Không để native handle đã tạo bị bỏ quên |
| Cấp phát bộ nhớ C/C++ | `malloc/calloc` trả `NULL`, C++ allocation báo lỗi theo hợp đồng | Return code, `errno` nếu API dùng | Giải phóng những bước đã sở hữu; không dereference NULL |
| Cấp phát FFM | `Arena.allocate` thất bại, arena đóng/sai thread, size không hợp lệ | Java exception/error thuộc nguyên nhân tương ứng | Không nhầm mọi lỗi FFM là native `ENOMEM` |
| Thư viện trả mã lỗi | Return code khác 0, sentinel như `-1` hoặc null pointer | Giá trị trả về; trạng thái lỗi đúng theo C API | Không coi tài nguyên được tạo thành công khi kết quả không bảo đảm |
| Trạng thái OS/runtime | POSIX `errno`, Windows `GetLastError`/Winsock `WSAGetLastError` | Chụp ngay theo quy định của từng hàm | Không đọc trạng thái cũ, sai luồng hoặc đã bị ghi đè |
| Callback native → Java | Listener ném `RuntimeException`, `Error`, callback thất bại | Cầu nối bắt và ghi nhận throwable, trả mã lỗi ABI | Không để exception thoát qua FFM upcall; không để JNI pending exception bị bỏ sót |
| Dọn dẹp một phần | `unregister`, `destroy`, `free` hay `close` thất bại | Trạng thái thực tế và kết quả từng bước release | Không free bộ nhớ còn bị native dùng; không double-free khi retry |
| Lỗi ABI / truy cập native | Sai descriptor, pointer hỏng, use-after-free, race | Có thể là crash JVM/process, sanitizer, dump | Chạy thử nghiệm nguy hiểm trong tiến trình tách biệt |

**Không phải lỗi nào cũng cứu được bằng `try/catch`.** Lỗi Java trong logic wrapper có thể được ném và xử lý. Nhưng truy cập C vào địa chỉ đã free, ABI không khớp hoặc lỗi use-after-free có thể giết cả JVM trước khi Java kịp bắt ngoại lệ. Kiểm thử native cần cả unit test xác định, integration test và test trong tiến trình riêng.

### 1.1. Phân biệt ba khái niệm

- **Failure signal:** hàm báo thất bại bằng mã trả về, `errno`, null pointer, Java exception hay callback status.
- **Ownership state:** tài nguyên đã chuyển từ *not acquired* sang *owned*, *borrowed*, *released*, hay *unknown* chưa?
- **Safety to release:** mọi bên dùng tài nguyên đã kết thúc hay chưa? Đặc biệt, có callback hoặc native worker đang chạy không?

Một return code thất bại không luôn có nghĩa “chưa xảy ra thay đổi”. Ví dụ `register_callback` có thể đăng ký xong rồi lỗi khi bật worker; `native_destroy` có thể giải phóng một phần cấu trúc trước khi báo lỗi. Chỉ coi **fail-before-effect** khi tài liệu C API hoặc wrapper của chính bạn bảo đảm điều đó. Nếu trạng thái sau lỗi không xác định, đánh dấu **UNKNOWN / QUARANTINED**, không thử `free` hoặc `destroy` lần nữa theo cảm tính.

## 2. Hợp đồng lỗi và ownership phải được viết trước khi test

Ví dụ một native session có các bước:

```text
Java wrapper
  ├─ 1. allocate buffer B                 [Java/C/FFM owner]
  ├─ 2. create native handle H            [native object owner]
  ├─ 3. create callback context/stub U/S   [Java/arena owner]
  ├─ 4. register callback R with H        [library registration]
  ├─ 5. start worker / perform operation  [asynchronous users]
  └─ close: stop → unregister/drain → destroy H → free U/S/B
                           → unload library when allowed
```

Đồ thị phụ thuộc cần ghi rõ:

```text
Callback R còn chạy  ──cần──> U/S + H + thư viện
Native handle H       ──có thể cần──> buffer B + thư viện
Hàm destroy/free      ──cần──> thư viện còn được nạp
```

Nếu callback cuối có thể xảy ra trong `destroy(H)`, context/stub phải sống đến **sau** `destroy`; nếu destructor sử dụng buffer B thì B chỉ được free **sau** khi destructor trả về. Thứ tự cụ thể phụ thuộc hợp đồng native, không chỉ thứ tự cấp phát.

Mỗi hàm bridge nên được đặc tả bằng năm câu hỏi:

1. Thành công được báo bằng giá trị nào? Có lấy thêm `errno` hay error object không?
2. Khi thất bại, tài nguyên đầu ra có thể đã được cấp phát/đăng ký một phần không?
3. Đầu ra là **owned**, **borrowed** hay chuyển ownership cho thư viện?
4. Có side effect bất đồng bộ (thread, callback, queue) sau khi hàm trả về không?
5. Việc cleanup có **idempotent**, có thể retry và có bảo đảm quiescence hay không?

Một bảng mẫu:

| API minh họa | Thành công | Khi thất bại | Owner sau thành công | Điều kiện dọn dẹp |
| --- | --- | --- | --- | --- |
| `native_alloc(n, &p)` | `OK`, `p != NULL` khi `n > 0` | `ERR_NOMEM`; **nếu** hợp đồng bảo đảm `p == NULL` | Caller | Không còn con trỏ mượn; `native_free(p)` một lần |
| `native_create(p, &h)` | `OK` và handle hợp lệ | Có thể đã lấy ownership của `p` tùy API | Caller hoặc thư viện | Kết thúc mọi downcall; gọi đúng destructor |
| `native_register(h, fn, ctx)` | `OK` | Có thể có callback đăng ký dở nếu API không atomic | Owner của registration | Unregister **và** drain, theo hợp đồng |
| `native_close(h)` | `OK` | Tài nguyên có thể vẫn sống hoặc đã đóng một phần | Không rõ nếu API không quy định | Không retry trước khi biết trạng thái thực tế |

*Các tên hàm và mã `ERR_*` trong bảng là mô hình thiết kế, không phải API tiêu chuẩn của Java hay C.*

## 3. Kiểm thử lỗi cấp phát: gây lỗi chính xác thay vì làm cạn bộ nhớ

### 3.1. Gây lỗi ở mọi điểm cấp phát

Trong test native, thay `malloc` hoặc allocator do bạn sở hữu bằng cổng có thể gây lỗi tại lần gọi thứ N:

```c
/* C11: minh họa bộ tiêm lỗi; dùng trong test bridge do bạn sở hữu. */
#include <stddef.h>
#include <stdlib.h>

typedef struct {
    size_t calls;
    size_t fail_at; /* 0 = không gây lỗi */
} AllocFault;

static void *test_malloc(AllocFault *fault, size_t size) {
    ++fault->calls;
    if (fault->fail_at != 0 && fault->calls == fault->fail_at) {
        return NULL;
    }
    return malloc(size);
}
```

Với đường khởi tạo có N lần cấp phát, chạy N+1 kịch bản: lần 1 thất bại, lần 2 thất bại, ..., lần N thất bại, và lần N+1 không gây lỗi. **Không test bằng cách cấp phát lượng RAM khổng lồ**: hệ điều hành có thể overcommit, kill process hoặc làm hỏng tính xác định của CI.

Khi wrapper dùng `errno`, injector phải mô phỏng chính xác *hợp đồng* của allocator: nếu native code trông đợi `errno == ENOMEM` sau `malloc` trả NULL, injector cần đặt `errno` tương ứng. Không áp dụng quy tắc đó cho mọi custom allocator: nhiều thư viện trả mã lỗi riêng, không dùng `errno`.

Khi cấp phát `n * sizeof(T)`, kiểm tra tràn số nguyên **trước** khi nhân; cấp phát 0 byte cũng cần xử lý riêng vì `malloc(0)` có thể trả NULL hoặc pointer có thể free được tùy implementation. Không được mặc nhiên diễn giải mọi `NULL` là `ENOMEM` nếu truyền size bằng 0.

### 3.2. Kiểm chứng sau mỗi lần failure injection

Sau mỗi trường hợp, xác minh:

- Mọi tài nguyên thực sự đã cấp phát được release đúng một lần **khi đã đủ điều kiện an toàn**.
- Không gọi `destroy` trên handle chưa tạo hoặc `free` trên vùng nhớ do phía khác sở hữu.
- Output pointer/handle ở trạng thái hợp lệ theo hợp đồng (ví dụ null khi mở thất bại trước khi tạo).
- Lỗi gốc không bị exception phát sinh trong rollback thay thế.
- Không callback hoặc worker nào vẫn giữ pointer vào vùng đã free.
- Một lượt khởi tạo thành công sau lượt thất bại trước đó vẫn hoạt động đúng.

**Phân biệt JVM heap và native memory.** `OutOfMemoryError` không chỉ nói về Java heap: một số thao tác off-heap hoặc runtime cũng có thể báo OOME. Ngược lại, `malloc` trả NULL trong C không tự chuyển thành `OutOfMemoryError` ở Java. JNI wrapper có thể trả mã lỗi hoặc ném exception tùy thiết kế. Lỗi thiếu bộ nhớ thực sự thường khiến việc tạo exception/log hay cấu trúc theo dõi cũng thất bại; test riêng bằng fault hook có kiểm soát và giữ đường dọn dẹp ít cấp phát nhất có thể.

### 3.3. Các ranh giới FFM và JNI

- FFM `Arena.allocate(...)` có lifetime gắn với arena. Truy cập sau khi đóng arena hay từ sai luồng confined là lỗi phạm vi/thread; không được gộp vào báo cáo “native cấp phát thiếu RAM”. Những hàm C được gọi bằng `Linker.downcallHandle` vẫn có thể trả NULL/mã lỗi; FFM không tự ánh xạ chúng thành Java exception có ý nghĩa nghiệp vụ.
- JNI `NewGlobalRef` có thể thất bại và báo lỗi cấp phát của JVM. Kiểm tra return/pending exception theo JNI; không cố tiếp tục callback với global reference chưa tạo. Một `jobject` local reference không được giữ làm context bất đồng bộ; chỉ dùng global ref khi hợp đồng cần và xóa sau khi native ngừng dùng.
- Bộ nhớ do `malloc` tạo phải dùng allocator tương ứng để free; memory do native object sở hữu phải để destructor của nó giải phóng. Tránh gọi `free` cho vùng mà `Arena` hoặc thư viện khác đang quản lý.

## 4. Mã lỗi native: return value, `errno` và trạng thái nền tảng

### 4.1. Return code là tín hiệu chính của C API

Ví dụ một C API thiết kế riêng có thể quy định:

```c
/* ABI minh họa: không phải API tiêu chuẩn của hệ điều hành. */
enum {
    NATIVE_OK = 0,
    NATIVE_ERR_NO_MEMORY = 1001,
    NATIVE_ERR_INVALID_STATE = 1002,
    NATIVE_ERR_CALLBACK = 1003,
    NATIVE_ERR_IO = 1004
};

int native_open_session(const char *path, void **out_handle);
```

Java bridge phải kiểm tra `rc` trước khi dùng `out_handle`; chỉ ánh xạ những mã đã công bố thành exception cụ thể. Với mã chưa biết, giữ nguyên mã và tên thao tác để chẩn đoán. Đừng giả định `rc < 0` nghĩa là lỗi: có thư viện dùng số âm, số dương, null sentinel hoặc error object. Test cần có mã không nhận diện và boundary values theo hợp đồng.

Lỗi nên đi kèm ngữ cảnh **thao tác, đường gọi, mã thư viện, mã hệ điều hành nếu hợp lệ, trạng thái ownership**. Không đưa dữ liệu bí mật, con trỏ thô, access token hoặc nội dung nhạy cảm vào log.

### 4.2. `errno` phải được đọc đúng lúc và đúng điều kiện

`errno` là trạng thái lỗi thread-local của C runtime theo nền tảng; nhiều hàm chỉ quy định giá trị của nó **khi trả thất bại**. Thành công không có nghĩa `errno` được reset về 0. Một hàm native gọi thêm có thể ghi đè `errno` trước khi Java/bridge đọc nó.

```c
/* C POSIX: minh họa ghi lại ngay sau một hàm C mà tài liệu nói dùng errno. */
#include <errno.h>

int rc = operation_using_errno();
int captured_errno = errno; /* chụp ngay, trước gọi C khác */
if (rc == -1) {
    /* Dùng captured_errno; không đọc lại errno sau khi log/format lỗi. */
}
```

Ở đây `operation_using_errno()` là tên hàm minh họa, **không phải ví dụ C hoàn chỉnh để biên dịch**. Luôn ưu tiên API trả mã lỗi tường minh nếu thư viện cung cấp. Không suy luận lỗi dựa trên `errno` khi giá trị return báo thành công.

Đối với Windows, chỉ dùng `GetLastError()` sau lời gọi Win32 được tài liệu chỉ định; với Winsock có API `WSAGetLastError()`. Không coi `errno`, `GetLastError` và `WSAGetLastError` là một kho mã lỗi tương đương. Mã số và tên lỗi có thể khác giữa hệ điều hành và thư viện C.

### 4.3. FFM Java 22+: chụp trạng thái lỗi cùng downcall

FFM cung cấp `Linker.Option.captureCallState("errno")` để capture `errno` ngay sau native downcall. Đối số capture-state `MemorySegment` được thêm vào method handle theo chữ ký do linker tạo; vùng capture phải có layout tương thích `Linker.Option.captureStateLayout()`. Với hàm cố định không cần allocator/result buffer ngầm, capture-state argument đứng trước các đối số C thông thường. Đọc giá trị bằng `VarHandle` đến field mang tên `errno`.

```java
// Mảnh minh họa Java 22+; functionAddress/descriptor/arguments
// phải được giải quyết từ C ABI thật và chữ ký handle của bạn.
Linker linker = Linker.nativeLinker();
Linker.Option capture = Linker.Option.captureCallState("errno");
StructLayout stateLayout = Linker.Option.captureStateLayout();
VarHandle errnoField = stateLayout.varHandle(
    MemoryLayout.PathElement.groupElement("errno"));

MethodHandle call = linker.downcallHandle(
    functionAddress, descriptor, capture);

try (Arena arena = Arena.ofConfined()) {
    MemorySegment state = arena.allocate(stateLayout);
    // Gọi call với đối số đầu tiên là state,
    // rồi truyền đúng các đối số C theo descriptor.
    // Chỉ đọc errnoField khi return code báo lỗi và API dùng errno.
}
```

Đây là **đoạn tích hợp** cần import `java.lang.foreign.*`, `java.lang.invoke.*`, và một symbol cùng `FunctionDescriptor` hợp lệ; không phải chương trình standalone. Tên capture được hỗ trợ phụ thuộc nền tảng; dùng `captureStateLayout()` để kiểm tra field thay vì giả định `GetLastError` luôn tồn tại. Với downcall trên luồng native hoặc callback bất đồng bộ, phải capture lỗi từ **đúng lời gọi/đúng thread**.

### 4.4. Không retry một cách mù quáng

Một `EINTR` có thể cho phép retry **nếu** hàm và trạng thái side effect quy định như vậy. `EAGAIN` có thể yêu cầu lịch thử lại, còn `ENOMEM` thường cần giảm tải/hủy yêu cầu. Hàm đã tạo session một phần, gửi gói tin một phần hay commit thay đổi không nhất thiết an toàn để gọi lại. Mọi retry phải có định nghĩa idempotency và ownership của lần gọi trước.

## 5. Ngoại lệ callback: chặn tại biên ABI, ghi nhận để báo lại

### 5.1. Java listener lỗi không phải là mã lỗi C

Native có thể giữ function pointer gọi Java về sau. C ABI cần callback trả `int` hoặc `void` theo chữ ký; Java exception không phải một dạng return value của C. Với FFM upcall, **không để exception từ MethodHandle target thoát ra ngoài**: tài liệu Linker cảnh báo exception không bắt có thể khiến JVM kết thúc đột ngột.

Một wrapper callback Java có thể chuyển lỗi thành mã ABI và lưu lỗi đầu tiên để Java chủ động kiểm tra ở vị trí an toàn:

```java
// Mẫu logic (không độc lập): eventHandler là callback ứng dụng.
private static final int CALLBACK_FAILED = -700;
private final java.util.concurrent.atomic.AtomicReference<Throwable>
    firstCallbackFailure = new java.util.concurrent.atomic.AtomicReference<>();

int dispatchEventSafely(int eventCode) {
    try {
        eventHandler.accept(eventCode);
        return 0;
    } catch (Throwable ex) {
        // Không để Java Throwable đi qua upcall boundary.
        firstCallbackFailure.compareAndSet(null, ex);
        return CALLBACK_FAILED;
    }
}
```

Giá trị `-700` chỉ là **mã ví dụ**, phải khớp hợp đồng C API khi triển khai thật. Bắt `Throwable` ở ranh giới upcall giúp không cho exception thoát qua ABI; riêng `OutOfMemoryError`, `ThreadDeath` và lỗi JVM nghiêm trọng cần chính sách fail-safe, tránh tạo thêm nhiều object/log khi hệ thống đang kiệt tài nguyên. Lưu throwable vào reference ổn định là tối thiểu; không hứa tiếp tục chạy bình thường sau mọi `Error`.

Không gọi lại listener vô hạn khi lỗi lặp; quy định callback failure có khiến native dừng session, từ chối sự kiện, báo lỗi khi next downcall, hay chuyển vào hàng đợi lỗi không. Test chính xác những ngữ nghĩa đó. Khi có nhiều callback đồng thời, phải quyết định giữ lỗi đầu tiên, tổng hợp lỗi hay ghi tất cả theo giới hạn bộ nhớ.

### 5.2. JNI callback: kiểm tra pending exception

Sau `CallVoidMethod` / `CallObjectMethod` vào Java, native C phải kiểm tra `ExceptionCheck`. Có hai chiến lược hợp lệ:

1. Với **native method được Java gọi đồng bộ**, ngừng công việc và trở về để exception đang pending lan về Java, nếu hợp đồng cho phép và không có cleanup bất hợp lệ.
2. Với **callback trên native worker**, chủ động thu nhận/ghi nhận ngoại lệ bằng JNI rồi `ExceptionClear` trước khi tiếp tục các thao tác JNI không được phép khi còn pending; truyền lỗi qua error channel riêng.

```c
/* C/JNI pseudocode: env, listener và on_event đã được thiết lập hợp lệ. */
(*env)->CallVoidMethod(env, listener, on_event, event_code);
if ((*env)->ExceptionCheck(env)) {
    jthrowable thrown = (*env)->ExceptionOccurred(env); /* local ref */
    (*env)->ExceptionClear(env);                        /* clear trước JNI thường */
    /* ghi nhận thrown qua error channel hợp lệ, có thể cần NewGlobalRef */
    /* xóa local ref; kiểm tra lỗi khi tạo global ref */
    (*env)->DeleteLocalRef(env, thrown);
    return CALLBACK_FAILED; /* giá trị này thuộc ABI minh họa */
}
return CALLBACK_OK;
```

Đoạn trên chỉ trình bày thứ tự xử lý; `CALLBACK_FAILED`/`CALLBACK_OK`, error channel và đối tượng JNI là ứng dụng cung cấp. Không lưu `thrown` local reference sang callback khác; cần lifetime dài hơn thì tạo `NewGlobalRef` và `DeleteGlobalRef` đúng thời điểm. Nếu `NewGlobalRef` cũng thất bại do thiếu bộ nhớ, cần lối báo lỗi dự phòng không tiếp tục dùng reference null.

Khi thread được tạo bên C, phải attach bằng `JavaVM.AttachCurrentThread` trước khi lấy `JNIEnv*` và detach theo quy tắc tương ứng. `JNIEnv*` **không dùng chung giữa các luồng**. Đặc biệt, kiểm thử callback lỗi trong cả thread được Java tạo lẫn native worker đã attach.

### 5.3. Test callback cần kiểm tra hơn một exception

- Listener ném `IllegalArgumentException`; native nhận mã lỗi dự kiến, JVM không chết, lỗi có thể được Java truy xuất.
- Listener ném trước khi cập nhật state; rollback/ack của sự kiện theo hợp đồng, không tự giả định sự kiện đã xử lý.
- Listener ném khi callback xảy ra đồng thời với close; context còn sống cho tới khi native quiescent.
- Callback lỗi ngay trong quá trình unregister/destroy nếu destructor có thể gọi ngược; không free stub/global ref quá sớm.
- Exception trong lúc báo cáo lỗi (logging, listener phụ) cũng phải được ngăn khỏi biên ABI; không che mất lỗi gốc.
- Sai signature function pointer/ABI không phải ngoại lệ nghiệp vụ để bắt; test trong process cô lập và dùng native sanitizer.

## 6. Dọn dẹp một phần: quy tắc an toàn khi cleanup tự thất bại

**Cleanup là một chuỗi thao tác có điều kiện**, không phải danh sách `finally { freeEverything(); }` bất chấp trạng thái. Một thứ tự phổ biến:

```text
OPEN
  │
  ├─ stop accepting Java calls / transition to CLOSING
  ├─ stop native producer
  ├─ unregister callbacks + drain/join existing callbacks
  │      └─ nếu KHÔNG quiescent: giữ stub/context/handle/buffer sống
  ├─ destroy handle (khi không còn user; destructor dependencies còn sống)
  │      └─ nếu kết quả UNKNOWN: không free buffer còn có thể bị dùng
  ├─ release callback context + GlobalRef + upcall stub (đúng thời điểm)
  ├─ free externally owned buffer, close its Arena
  └─ release/unload library (nếu mô hình nạp cho phép)
CLOSED
```

Không có thứ tự duy nhất cho mọi thư viện: nếu `destroy` có thể gọi callback cuối, cần giữ callback đến sau `destroy`. Nếu native object tự sở hữu buffer thì destructor free buffer, Java không free lần hai. Một lỗi cleanup cần dừng **các bước phụ thuộc không còn an toàn**, trong khi có thể thực hiện những cleanup độc lập được chứng minh an toàn.

### 6.1. Trạng thái cần theo dõi

| Trạng thái | Ý nghĩa | Có được giải phóng tài nguyên phụ thuộc không? |
| --- | --- | --- |
| `NOT_ACQUIRED` | Bước cấp phát chưa chạy hoặc fail-before-effect chắc chắn | Không cần free |
| `ACQUIRED` | Caller sở hữu tài nguyên hợp lệ | Chỉ khi mọi bên mượn đã dừng |
| `BORROWED` | Thư viện/đối tượng khác sở hữu | Không free trực tiếp |
| `QUIESCING` | Đang ngừng producer, có thể còn callback | Chưa free stub/context |
| `QUIESCENT` | Native cam kết không còn callback mới/in-flight | Có thể giải phóng tài nguyên callback theo phụ thuộc còn lại |
| `RELEASED` | Release thành công rõ ràng | Không release lần nữa |
| `UNKNOWN` | Cleanup báo lỗi và có thể có side effect một phần | Khoanh vùng, không retry theo phỏng đoán |

Ghi state theo từng tài nguyên, không chỉ `boolean closed` của toàn session. Một session có thể đã unregister callback nhưng còn handle/buffer vì destroy thất bại. Nếu API `free` trả `void` và có undefined behavior khi double free, không thể “test retry” trong cùng tiến trình trên pointer nghi ngờ đã free.

### 6.2. Lỗi gốc và lỗi cleanup

Java `try-with-resources` có cơ chế suppressed exceptions: khi body ném lỗi và `close()` cũng ném lỗi, lỗi từ close được gắn vào lỗi body. Khi tự viết rollback:

```java
Throwable original = ...; // đoạn minh họa, không phải method độc lập
try {
    releaseResourcesWhosePreconditionsHold();
} catch (Throwable cleanupFailure) {
    original.addSuppressed(cleanupFailure);
}
```

Đoạn trên chỉ minh họa việc **giữ lỗi gốc**, không cho phép chạy cleanup bất chấp điều kiện an toàn. Cần bảo đảm `releaseResourcesWhosePreconditionsHold()` chỉ chọn bước độc lập, hợp lệ theo state. Trong ứng dụng thực tế, tránh tự ghép thứ tự từ tên các hàm; đặc tả hành vi riêng cho từng native API.

Khi cleanup thất bại mà trạng thái không chắc chắn, không được tuyên bố `CLOSED` rồi xóa reference cuối cùng đến tài nguyên. Có thể giữ session ở `CLOSE_FAILED/QUARANTINED`, phát cảnh báo và để cơ chế phục hồi được thiết kế trước xử lý; đôi khi chấp nhận giữ tài nguyên đến hết tiến trình an toàn hơn use-after-free.

## 7. Ví dụ Java 17+ chạy được: fault matrix và cleanup từng phần

Ví dụ dưới đây dùng `FakeNative` thay cho thư viện C. Injector **cố ý thất bại trước khi thay đổi state của thao tác tương ứng**; vì vậy test có thể retry sau khi bỏ injection. API native thực sự không mặc nhiên có tính chất này. `drain()` ở fake không tạo worker: nó đại diện cho một native API đã bảo đảm không còn callback in-flight; đây là mô phỏng ownership và lỗi, **không chứng minh** giao thức callback bất đồng bộ trong thực tế. Ví dụ được chạy tuần tự để tập trung vào failure injection; wrapper production cần đồng bộ khi nhiều thread đồng thời gọi native/close.

Tạo file `NativeFailureMatrixDemo.java`:

```java
public final class NativeFailureMatrixDemo {
    static final int CALLBACK_ERROR = -700;

    static final class NativeFailure extends Exception {
        final int code;
        NativeFailure(String operation, int code) {
            super(operation + " failed, code=" + code);
            this.code = code;
        }
    }

    static final class FakeNative {
        String failAt;
        boolean buffer, handle, callbackRegistered;
        int freed, destroyed, unregistered;
        Throwable callbackFailure;

        FakeNative(String failAt) {
            this.failAt = failAt;
        }

        void maybeFail(String operation) throws NativeFailure {
            if (operation.equals(failAt)) {
                throw new NativeFailure(operation,
                    operation.equals("alloc") ? 12 : 5);
            }
        }

        void allocate() throws NativeFailure {
            maybeFail("alloc");
            buffer = true;
        }

        void create() throws NativeFailure {
            if (!buffer) throw new IllegalStateException("no buffer");
            maybeFail("create");
            handle = true;
        }

        void register() throws NativeFailure {
            if (!handle) throw new IllegalStateException("no handle");
            maybeFail("register");
            callbackRegistered = true;
        }

        int fireCallback(Runnable listener) {
            if (!callbackRegistered) {
                throw new IllegalStateException("callback not registered");
            }
            try {
                listener.run();
                return 0;
            } catch (Throwable failure) {
                callbackFailure = failure;
                return CALLBACK_ERROR;
            }
        }

        void drain() throws NativeFailure {
            maybeFail("drain");
            // Real native API: must prove no in-flight or future callbacks.
        }

        void unregister() throws NativeFailure {
            if (!callbackRegistered) return;
            maybeFail("unregister");
            callbackRegistered = false;
            unregistered++;
        }

        void destroy() throws NativeFailure {
            if (!handle) return;
            if (callbackRegistered) {
                throw new IllegalStateException("callback still registered");
            }
            maybeFail("destroy");
            handle = false;
            destroyed++;
        }

        void free() throws NativeFailure {
            if (!buffer) return;
            if (handle) {
                throw new IllegalStateException("handle still uses buffer");
            }
            maybeFail("free");
            buffer = false;
            freed++;
        }
    }

    static final class Session implements AutoCloseable {
        private final FakeNative api;
        private boolean closed;

        private Session(FakeNative api) {
            this.api = api;
        }

        static Session open(FakeNative api) throws NativeFailure {
            try {
                api.allocate();
                api.create();
                api.register();
                return new Session(api);
            } catch (NativeFailure original) {
                try {
                    api.drain();
                    api.unregister();
                    api.destroy();
                    api.free();
                } catch (NativeFailure cleanupError) {
                    original.addSuppressed(cleanupError);
                }
                throw original;
            }
        }

        @Override
        public void close() throws NativeFailure {
            if (closed) return;
            api.drain();
            api.unregister();
            api.destroy();
            api.free();
            closed = true;
        }
    }

    static void checkClean(FakeNative api) {
        if (api.buffer || api.handle || api.callbackRegistered
                || api.freed > 1 || api.destroyed > 1
                || api.unregistered > 1) {
            throw new AssertionError("invalid ownership or double cleanup");
        }
    }

    public static void main(String[] args) throws Exception {
        for (String phase : new String[] {"alloc", "create", "register"}) {
            FakeNative api = new FakeNative(phase);
            try {
                Session.open(api);
                throw new AssertionError("expected " + phase + " failure");
            } catch (NativeFailure expected) {
                if (!expected.getMessage().startsWith(phase + " failed")) {
                    throw expected;
                }
            }
            checkClean(api);
            System.out.println(phase + " failure: rollback OK");
        }

        FakeNative api = new FakeNative(null);
        try (Session session = Session.open(api)) {
            int status = api.fireCallback(() -> {
                throw new IllegalArgumentException("bad event");
            });
            if (status != CALLBACK_ERROR
                    || !(api.callbackFailure instanceof IllegalArgumentException)) {
                throw new AssertionError("callback exception escaped");
            }
        }
        checkClean(api);
        System.out.println("callback exception: contained and cleaned");

        for (String phase : new String[] {
                "drain", "unregister", "destroy", "free"}) {
            FakeNative failing = new FakeNative(phase);
            Session session = Session.open(failing);
            try {
                session.close();
                throw new AssertionError("expected " + phase + " failure");
            } catch (NativeFailure expected) {
                if (!expected.getMessage().startsWith(phase + " failed")) {
                    throw expected;
                }
            }
            // Must retain every resource still needed by the failed phase.
            if (phase.equals("drain") || phase.equals("unregister")) {
                if (!failing.buffer || !failing.handle
                        || !failing.callbackRegistered) {
                    throw new AssertionError("released while callbacks possible");
                }
            } else if (phase.equals("destroy")) {
                if (!failing.buffer || !failing.handle
                        || failing.callbackRegistered) {
                    throw new AssertionError("invalid partial destroy state");
                }
            } else {
                if (!failing.buffer || failing.handle
                        || failing.callbackRegistered) {
                    throw new AssertionError("invalid partial free state");
                }
            }

            // The fake guarantees fail-before-effect; a real API may not.
            failing.failAt = null;
            session.close();
            session.close();
            checkClean(failing);
            System.out.println(phase + " failure: retained, recovered");
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac --release 17 NativeFailureMatrixDemo.java
java NativeFailureMatrixDemo
```

Stdout chính xác của chương trình:

```text
alloc failure: rollback OK
create failure: rollback OK
register failure: rollback OK
callback exception: contained and cleaned
drain failure: retained, recovered
unregister failure: retained, recovered
destroy failure: retained, recovered
free failure: retained, recovered
```

Trong lượt test đầu, lỗi ở `alloc/create/register` khiến `open()` rollback đúng tài nguyên đã sở hữu. Trong lượt callback, exception Java được giữ ở `callbackFailure` và quy đổi thành `CALLBACK_ERROR`; sau đó session đóng. Bốn lượt cuối chứng minh **không được xóa những tài nguyên còn là phụ thuộc**:

- Lỗi `drain` hoặc `unregister`: giữ cả registration, handle và buffer.
- Lỗi `destroy`: callback đã được unregister, nhưng handle và buffer còn.
- Lỗi `free`: handle đã hủy, buffer còn được owner ghi nhận.

Sau khi injector được tắt, fake cho phép retry và bảo đảm mỗi destructor chạy nhiều nhất một lần. **Không áp dụng retry này cho native destructor thực tế khi chưa biết nó có fail-before-effect hay không**; có API trả lỗi sau khi đã free một phần. Chương trình chỉ kiểm tra logic state nhân tạo, cần bổ sung test JNI/FFM bằng native implementation thật để chứng minh quiescence, allocator và lifetime.

## 8. Ma trận test lỗi native cần có

| Điểm tiêm / tình huống | Kết quả cần quan sát | Bất biến cần kiểm chứng |
| --- | --- | --- |
| Lần malloc/calloc thứ 1...N thất bại | Mã lỗi thiếu bộ nhớ, không crash | Mỗi tài nguyên tạo trước đó được cleanup phù hợp |
| `malloc(0)` và phép nhân size tràn | Xử lý size rõ ràng; từ chối overflow | Không nhầm NULL do size 0 với lỗi chắc chắn |
| Native create trả lỗi **trước** side effect | Không có handle hợp lệ | Không gọi destroy với handle chưa có |
| Native create trả lỗi **sau** side effect một phần | State không chắc chắn được công bố | Không free nhầm buffer native còn giữ |
| Register callback trả lỗi khi worker đã bắt đầu | Quiescence vẫn được thực hiện | Stub/context sống tới khi callback cuối hoàn tất |
| Native trả mã lỗi chưa biết | Exception giữ nguyên mã và operation | Không ép mã chưa nhận diện thành success |
| Return thành công nhưng `errno` khác 0 | Thành công theo return code | Không tạo false positive từ errno cũ |
| Return lỗi với `errno` bị thay đổi sau logging | Snapshot vẫn đúng | Đọc/capture trước mọi C call khác |
| Callback Java ném `RuntimeException` | Trả callback error theo ABI | Không exception thoát FFM upcall |
| Callback Java ném `Error` | Chính sách fail-safe được kích hoạt | Không dựa vào log/allocator khi đã thiếu RAM |
| JNI callback có pending exception | Được propagate hoặc clear có chủ đích | Không gọi JNI tùy ý khi còn pending |
| Callback và close race | Shutdown đợi native quiescence | Không use-after-free của callback/global ref |
| Unregister/drain lỗi | Bước phụ thuộc bị chặn | Không destroy/free khi native còn có thể dùng |
| Destroy lỗi nhưng có side effect không rõ | Session chuyển `UNKNOWN` | Không tự retry hoặc free theo phỏng đoán |
| Free lỗi | Ownership được đánh dấu theo hợp đồng | Không double-free hoặc đánh dấu CLOSED sai |
| Cleanup tiếp tục lỗi sau lỗi gốc | Lỗi gốc được giữ, lỗi sau suppressed | Có thông tin chẩn đoán và trạng thái partial |
| Close gọi hai lần/đồng thời | Một owner release, close kết thúc nhất quán | Không phá tài nguyên do thread khác đang mượn |
| Nhiều session cùng thư viện | Session độc lập được đóng từng cái | Không unload thư viện khi session khác còn sử dụng |

Một test case nên kiểm tra **kết quả API + ledger tài nguyên + thứ tự sự kiện**, thay vì chỉ xác nhận exception class. Ví dụ log theo session:

```text
session=17 ACQUIRE_BUFFER
session=17 CREATE_HANDLE
session=17 REGISTER_CALLBACK
session=17 INJECT_ERROR operation=UNREGISTER
session=17 CLOSE_FAILED retains=callback,handle,buffer
```

Trong sản phẩm thật, log này chỉ nên chứa ID logic; tránh ghi raw pointer, nội dung nhạy cảm hay địa chỉ của dữ liệu người dùng.

## 9. Kịch bản kiểm thử tích hợp JNI/FFM với thư viện thật

### 9.1. Test seam ở C/C++ và Java

Để không thay đổi hành vi production, đặt injector sau cờ test/build riêng hoặc một adapter allocator nội bộ. Có thể thay:
- Allocator: `malloc/calloc/realloc` hoặc custom allocator, điều khiển lần thứ N thất bại.
- Native operations: `open/register/read/destroy`, ép mã lỗi có chủ đích và xác định side effect đã xảy ra hay chưa.
- Callback: listener cố tình ném, sleep theo latch, gọi close lồng nhau, hoặc giữ callback active trong lúc thread khác đóng.
- Cleanup: các thao tác release có điểm tiêm lỗi độc lập và ledger trạng thái sau lỗi.

Không sửa behavior của thư viện bên thứ ba bằng cách giả định nó có sẵn hook; có thể viết **test-only shim** sở hữu C ABI và chuyển tiếp sang thư viện thật. Shim phải được xây dựng với đúng calling convention, layout, pointer width và mang nhãn rõ để không đóng gói nhầm trong artifact production.

### 9.2. Kiểm thử bất đồng bộ có thứ tự xác định

Dùng latch/barrier trước vùng callback critical để dàn dựng race:

```text
Thread NATIVE: callback bắt đầu → signal ENTERED → đợi RELEASE
Thread JAVA:   đợi ENTERED → close() → xác minh chưa free
Thread TEST:   signal RELEASE → đợi close hoàn tất → xác minh free một lần
```

Đặt timeout cho **test orchestration**, nhưng không biến timeout thành quyền free tài nguyên native chưa quiescent. Một hàm `unregister` trả về sớm không chứng minh callback đã kết thúc. Kiểm thử cả callback đã được queue nhưng chưa bắt đầu, vì bộ đếm `inFlight` bên Java có thể chưa kịp tăng. Native shutdown phải có hàng rào ngăn callback mới và chờ callbacks đã phát.

Nếu native destructor có thể gọi ngược Java, giữ callback context đến khi destructor xong và test trường hợp destructor ném lỗi hoặc callback trả error. Tránh close giữ Java monitor mà callback phải lấy; tình huống đó có thể deadlock.

### 9.3. Kiểm thử process riêng cho lỗi nguy hiểm

Các lỗi như ABI mismatch, free sai allocator, use-after-free, double-free trong native code có thể giết JVM. Chạy test riêng thành **subprocess** với timeout/exit code/stdout/stderr và core/minidump khi cần, để không làm chết toàn bộ bộ test. Sử dụng AddressSanitizer/UndefinedBehaviorSanitizer khi build C/C++ hỗ trợ, `-Xcheck:jni` trên JVM hỗ trợ, native debugger, kiểm tra thread còn sống và vùng nhớ còn sở hữu.

Đừng dựa hoàn toàn vào `System.gc()` hay `Cleaner` để phát hiện và chữa lỗi lifetime. GC không quyết định thời điểm native callback dừng, không thay cho explicit close. Tool phát hiện leak cũng cần nhận biết process-wide allocations hợp lệ; so sánh delta sau các vòng create/destroy với warm-up và baseline.

### 9.4. Kiểm thử phân phối đa môi trường

Parent topic là **Kiểm thử và phân phối**: native library là artifact phụ thuộc OS, kiến trúc CPU, compiler/ABI và JDK. Một bộ test chạy trên Windows x64 chưa đủ chứng minh Linux x64, macOS arm64 hoặc khác biệt C runtime an toàn. Ma trận CI nên phân biệt:

| Biến số | Điều cần kiểm tra |
| --- | --- |
| OS/runtime | Linux/macOS/Windows: loader, errno/Win32 error, allocator, tên thư viện |
| Kiến trúc | 32/64 bit nếu hỗ trợ, alignment, kích thước `size_t`/pointer |
| JDK | Java 17+ JNI; Java 22+ cho FFM final API |
| Build | Debug + sanitizer, release/optimized nếu cần |
| Concurrency | Single thread, callback native worker, close cạnh tranh |
| Packaging | Đúng phiên bản thư viện và dependency; artifact không chứa test shim |
| Lifecycle | Init thất bại, shutdown thường, shutdown khi lỗi, process restart |

FFM native access có cơ chế cấp quyền tùy phiên bản JDK/cách chạy; cấu hình `--enable-native-access` phù hợp khi cần. Việc chạy JNI không biến thành FFM: hai đường có lifetime, exception handling và cơ chế nạp thư viện khác nhau.

## 10. Các lỗi thiết kế thường bị bỏ sót

**1. Chỉ test rằng exception được ném.** Test `assertThrows` xác nhận tín hiệu lỗi nhưng không chứng minh vùng nhớ đã free đúng, callback không chạy nữa hay handle không leaked. Kiểm tra ledger/event sequence và cảnh báo sanitizer.

**2. Đọc `errno` sau khi tạo thông báo lỗi.** Formatter, logger hoặc native call khác có thể ghi đè `errno`. Capture ngay cùng native operation và chỉ dùng nếu return code báo lỗi theo hợp đồng.

**3. Đặt `closed=true` ngay đầu `close()`.** Nếu `unregister` lỗi, wrapper đã bị đánh dấu đóng nhưng native callback vẫn giữ reference. Cần state `CLOSING/CLOSE_FAILED` riêng và chủ sở hữu tài nguyên còn tồn tại.

**4. Một `finally` gọi tất cả destructor bất chấp kết quả drain.** Khi callback có thể chạy, free stub/context là use-after-free. Cleanup phụ thuộc điều kiện; lỗi đầu tiên có thể khiến các bước sau phải trì hoãn.

**5. Retry destroy sau lỗi chưa rõ side effect.** Destructor có thể đã free pointer rồi báo lỗi vì flush hoặc external I/O. Chỉ retry nếu API cam kết safe/idempotent hoặc có một thủ tục xác minh trạng thái.

**6. Tin rằng exception Java tự đi qua C ABI.** FFM upcall target ném exception không bắt là hành vi nguy hiểm; JNI cần kiểm tra pending exception và quyết định propagate/clear. C callback status phải là giá trị hợp lệ theo ABI.

**7. Nhầm leak có kiểm soát với dọn dẹp hoàn tất.** Khi native còn chạy và không thể drain, giữ vùng nhớ sống có thể là lựa chọn an toàn tạm thời. Nhưng phải báo failure, giữ ownership/diagnostics và xác định lúc process được tái khởi động hoặc phục hồi; không âm thầm coi session đã đóng.

**8. Bỏ qua lỗi khi clean up lỗi khác.** Nếu `open()` thất bại rồi `close()` cũng thất bại, báo cả lỗi gốc và suppressed/secondary diagnostics. Có thể có tài nguyên chưa giải phóng, phải theo dõi cả hai.

**9. Test race bằng `Thread.sleep` không có đồng bộ.** Sleep không chứng minh callback đã bắt đầu hoặc hết sử dụng pointer. Dùng latch, barrier, native handshake và thread-join đúng hợp đồng.

**10. Chỉ nhìn Java heap.** Native allocation, shared library, global references và worker threads không tự thể hiện như object Java heap tương đương. Giám sát cả native memory và thời điểm release.

## 11. Checklist áp dụng cho một Java/native module

- [ ] Mỗi hàm có tài liệu return code/`errno`/Win32 error và đặc tả side effect khi failure.
- [ ] Mỗi handle, buffer, callback stub, GlobalRef và thư viện có owner duy nhất; phân biệt borrowed pointer và transferred ownership.
- [ ] Có injector xác định cho mọi điểm acquire; ma trận test chạy từng lỗi riêng và lượt không lỗi.
- [ ] Kiểm tra integer overflow, size 0, null pointer, lỗi native allocator và lỗi tạo reference của JVM khi liên quan.
- [ ] Lỗi Java callback được bắt ở ABI boundary, chuyển thành status và ghi nhận để báo lại; JNI pending exception được xử lý đúng.
- [ ] Có bước stop/unregister **và** quiescence theo hợp đồng trước khi free callback context.
- [ ] Destructor thất bại có state xác định; không tự retry khi side effect không biết.
- [ ] Rollback giữ nguyên lỗi gốc và ghi nhận lỗi cleanup thứ cấp; không cleanup phụ thuộc khi chưa an toàn.
- [ ] Unit test kiểm tra ownership ledger và số lần release; integration test kiểm tra native lifetime và khả năng chạy lại sau thất bại.
- [ ] Stress/concurrency test có barrier chính xác; native sanitizer và subprocess test cho trường hợp có thể crash.
- [ ] Pipeline phân phối chạy trên các hệ điều hành/kiến trúc hỗ trợ và không đóng gói injector test vào production.

**Kết luận:** kiểm thử lỗi native đạt yêu cầu khi trả lời được hai câu hỏi cùng lúc: **“Lỗi đã được báo chính xác qua biên Java/native chưa?”** và **“Sau lỗi, mỗi tài nguyên còn ở trạng thái nào, có đủ bằng chứng để giải phóng hay không?”** Mã lỗi, callback exception và rollback đều phải gắn với ownership và lifetime; một exception đúng nhưng để lại callback vào vùng nhớ đã free vẫn là một bài test thất bại.

### Tài liệu tham khảo

- [OpenJDK JEP 454 — Foreign Function & Memory API (Java 22)](https://openjdk.org/jeps/454).
- [Oracle Java 22 — Foreign Function & Memory API, native errors với errno](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html).
- [dev.java — Troubleshoot Calls to Native Library Functions](https://dev.java/learn/api/io/ffm/troubleshoot/).
- [Oracle Java 22 — Linker.Option / captureCallState](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.Option.html).
- [Oracle Java 22 — Linker / upcall exception handling](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).
- [Oracle JNI Specification — Exception Handling](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/design.html).
- [Oracle JNI Specification — JNI Functions](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/functions.html).
