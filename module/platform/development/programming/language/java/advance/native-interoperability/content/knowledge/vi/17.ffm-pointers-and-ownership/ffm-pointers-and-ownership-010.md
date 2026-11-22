# Gắn hành động dọn dẹp với scope phù hợp, tránh giải phóng hai lần

## Mục tiêu bài học

Khi Java tương tác với C/C++ bằng **Foreign Function & Memory API (FFM)**, dữ liệu có thể được cấp phát bởi **Arena của Java** hoặc bởi **một thư viện native** thông qua malloc, create, open, retain hay hàm khởi tạo tài nguyên riêng. Điểm khó không chỉ là lấy được địa chỉ: ứng dụng phải biết **ai sở hữu tài nguyên, bao giờ nó hết hiệu lực, và chính xác thao tác nào phải giải phóng nó**.

Một lỗi đặc biệt nguy hiểm là **double-free**: gọi hàm giải phóng hai lần đối với cùng một allocation mà không có lần cấp phát mới xen giữa. Lỗi này có thể phá cấu trúc quản lý heap của C, làm hỏng bộ nhớ, treo tiến trình hoặc gây JVM crash. Bên cạnh đó, gắn cleanup sai scope có thể tạo **use-after-free** hoặc **memory leak** ngay cả khi không xảy ra double-free.

Sau bài này, bạn sẽ:

1. Phân biệt **Java-owned**, **C-owned/borrowed**, **transferred ownership** và **reference-counted** resources.
2. Hiểu **Arena.ofConfined, Arena.ofShared, Arena.ofAuto, Arena.global** và lúc nào nên đóng scope tường minh.
3. Biết dùng **MemorySegment.reinterpret(long, Arena, Consumer<MemorySegment>)** để gắn **một cleanup action** vào scope phù hợp cho con trỏ được C cấp và **Java thực sự sở hữu**.
4. Không nhầm **reinterpret**, **asSlice**, **MemorySegment** và **Arena.close** với thao tác free riêng của C.
5. Giữ **SymbolLookup/library và deallocator** sống lâu hơn các tài nguyên cần được giải phóng.
6. Phân tích các đường thất bại, giải phóng một lần, thread affinity, callback bất đồng bộ, lỗi cleanup và thứ tự shutdown.
7. Chạy ví dụ **Java 22+ và C11 hoàn chỉnh**, kiểm chứng rằng hàm release của C được gọi đúng **một lần** khi arena sở hữu đóng.
8. Áp dụng checklist review và test để ngăn double-free, leak và use-after-free trong dự án native interop.

**Baseline:** Bài dùng API ổn định **java.lang.foreign** từ **JDK 22** theo JEP 454. Những cú pháp này **không chạy nguyên xi trên JDK 17** vì FFM khi đó còn có API/incubator/preview khác.

---

## 1. Phân biệt tài nguyên với view và địa chỉ

Giả sử C cấp một vùng 4 byte:

~~~c
int32_t *p = malloc(sizeof(int32_t));
~~~

Địa chỉ **p** biểu diễn một allocation do C runtime quản lý. Java có thể nhận địa chỉ đó dưới dạng **MemorySegment**; từ đó tạo thêm **slice** hoặc **reinterpret** view. Nhưng việc có nhiều object MemorySegment **không có nghĩa** native code đã cấp nhiều allocations.

~~~text
        C malloc: 1 allocation thực
                   |
                address P
                   |
       +-----------+------------+
       |           |            |
   raw pointer   managed      asSlice
   view          view         view
       |           |            |
       +-----------+------------+
             CÙNG backing bytes

    Chỉ MỘT owner được gọi đúng deallocator
    MỘT lần khi allocation hết vòng đời.
~~~

Những khái niệm phải tách riêng:

| Khái niệm | Bản chất | Có tự giải phóng tài nguyên C không? |
| --- | --- | --- |
| **Địa chỉ native** | Số địa chỉ trả về từ C | Không |
| **MemorySegment** | View có địa chỉ, byte bounds, scope | Không mặc định sở hữu allocation C |
| **MemorySegment.asSlice** | View con dùng chung backing memory và scope với view gốc | Không |
| **MemorySegment.reinterpret** | Tạo alias với size/scope được khai báo lại; restricted API | **Không**, trừ khi đã gắn cleanup thực sự có chức năng release |
| **Arena** | Phạm vi quản lý vùng nhớ/các segment được gắn với arena | Đóng arena giải phóng vùng do arena cấp; custom cleanup có thể quản tài nguyên C khác |
| **Hàm C destroy/free/release** | Thao tác native giải phóng hoặc giảm reference count theo contract | Có, nếu đúng hàm, đúng allocator, đúng ownership |

**Quy tắc sở hữu:** Một allocation có thể có nhiều người **mượn/view**, nhưng phải có một **đầu mối chịu trách nhiệm giải phóng** theo đúng hợp đồng. Nếu hai cleanup actions cùng gọi free trên một địa chỉ, hoặc vừa gọi thủ công vừa đăng ký cleanup tự động cho cùng allocation, đó là nguy cơ double-free.

## 2. Điều FFM biết và điều nó không thể tự biết

FFM biết rằng một MemorySegment có phạm vi byte và một scope. Khi Java thực hiện get/set, FFM có thể kiểm tra bounds, thread access và scope còn sống. Nhưng FFM **không tự chứng minh** rằng một pointer native:

- Do ai cấp phát: Java Arena, C malloc, thư viện C++ new, pool riêng hay stack?
- Là **owned** (caller phải free) hay **borrowed** (không được free)?
- Có thể NULL không? NULL có nghĩa lỗi hay giá trị rỗng?
- Có độ dài bao nhiêu byte, theo API nào?
- Cần **free**, **destroy**, **close**, **release** hay một deallocator chuyên biệt?
- Có còn được C giữ sau khi return hoặc callback không?
- Có cần giải phóng trên cùng thread, trong cùng event loop hay trước khi unload library?
- Có dùng reference count hay cơ chế chia sẻ ownership?
- Có thể giải phóng khi một native worker vẫn chạy không?

Tài liệu C/header và kiểm thử của **binary thực** mới cung cấp những thông tin semantic này. **FunctionDescriptor** chỉ giúp linker gọi hàm theo ABI đã được lập trình viên mô tả; nó không biến C pointer thành một smart pointer có quyền sở hữu tự động.

## 3. Bốn dạng ownership cần đọc từ hợp đồng C

### 3.1. Java-owned: cấp phát bởi Arena

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment buffer = arena.allocate(256);
    buffer.set(ValueLayout.JAVA_INT, 0, 42);
} // Arena giải phóng backing memory của buffer.
~~~

Đây là snippet Java 22+ bên trong một method có import java.lang.foreign. Vùng native do Arena cấp phát đã có owner: **Arena**. Không gắn thêm callback gọi **free(buffer)** của libc để “chắc chắn dọn sạch”: có thể tạo **double-free** hoặc phá hợp đồng allocator.

**Tóm tắt:** Arena.allocate → Arena là owner → chỉ đóng Arena đúng lần khi không còn consumer.

### 3.2. Borrowed: C vẫn là owner

Header C có thể khai báo:

~~~c
/* p chỉ là borrowed pointer, không free ở caller. */
const unsigned char *device_get_view(
    struct Device *device,
    size_t *length
);
~~~

Nếu thư viện giữ quyền sở hữu, Java chỉ được đọc trong khoảng hiệu lực quy định (ví dụ tới lần gọi tiếp theo hoặc tới khi Device bị đóng). **Không đăng ký deallocator** cho pointer borrowed. Reinterpret về scope Java chỉ giới hạn đường truy cập qua view; nó **không kéo dài** lifetime thật của vùng nhớ do C quản.

### 3.3. Ownership transferred: Java phải gọi destroy

Header C có thể khai báo:

~~~c
/* Trả một allocation thuộc caller; hủy bằng blob_destroy. */
struct Blob *blob_create(void);
void blob_destroy(struct Blob *blob);
~~~

Khi hàm tạo thành công và hợp đồng nói caller sở hữu, Java cần chọn **một cơ chế duy nhất**:

- **Tự động theo scope:** đăng ký một cleanup action gọi blob_destroy khi owner Arena đóng.
- **Thủ công với AutoCloseable owner:** wrapper Java gọi blob_destroy khi close, có state để không release lặp. Khi chọn cách này, **không đồng thời** gắn cleanup blob_destroy thứ hai vào Arena cho cùng pointer.

Hai cơ chế có thể đều hợp lệ, nhưng **không được kết hợp để mỗi cơ chế tự cho mình là owner của cùng allocation**.

### 3.4. Reference-counted hoặc shared native object

Một API có thể cung cấp:

~~~c
void object_retain(struct Object *obj);
void object_release(struct Object *obj);
~~~

Hợp đồng này khác malloc/free. Mỗi lần **retain** thành công tạo một ownership share cần được **release** tương ứng; hai wrappers chỉ được release độc lập nếu **mỗi wrapper thật sự sở hữu một reference đã được retain**, không phải vì chúng cùng nhìn thấy một address. Nếu chỉ có một ref được cấp, tạo hai wrappers cùng tự release là sai.

**Phải đọc contract cụ thể:** không suy luận từ chữ release rằng nó tương đương free; trên một số API release chỉ giảm đếm và object được hủy khi refcount về 0.

### Ma trận sở hữu

| Nguồn dữ liệu | Ai giải phóng? | Cleanup đúng | Sai lầm thường gặp |
| --- | --- | --- | --- |
| **Arena.allocate** | Arena Java | Đóng Arena một lần | Gọi libc free vào segment do Arena sở hữu |
| C trả **borrowed pointer** | Chủ sở hữu phía C | Không free từ Java | Đăng ký custom free cho borrowed address |
| C **malloc/create** chuyển quyền cho caller | Java owner mới | Đúng C deallocator một lần | Vừa manual free vừa arena cleanup |
| Object C **reference-counted** | Chủ của từng ref | release tương ứng với retain/ownership thực | Nhiều aliases cùng release một ref |
| Pointer vào vùng **stack/native callback** | Thread/callback C sở hữu | Không free; không dùng sau thời hạn | Giữ view Java và sử dụng sau callback |
| Pointer vào **mapped file** | Mapping owner | Unmap/close theo mapping contract | Gọi free lên địa chỉ mapping |

## 4. Chọn scope phù hợp: khi nào cleanup chạy?

Trong Java 22, **Arena** quyết định **temporal bounds** của segments liên kết với nó:

| Arena | Vòng đời | Phù hợp cho cleanup native |
| --- | --- | --- |
| **Arena.ofConfined()** | Đóng tường minh trên thread tạo arena | Thường là mặc định tốt cho một request/transaction native trên một thread |
| **Arena.ofShared()** | Đóng tường minh; có thể dùng từ nhiều thread | Tài nguyên nhiều worker cùng dùng, khi đã phối hợp dừng trước close |
| **Arena.ofAuto()** | Được thu hồi theo reachability/GC, thời điểm không xác định | Chỉ khi tài nguyên cho phép cleanup không xác định thời điểm và không có thread-affinity khắt khe |
| **Arena.global()** | Sống theo JVM, không close tường minh | Không phù hợp nếu cần release có thời điểm xác định |

### Confined Arena

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(32);
    // Dùng trong thread sở hữu arena.
}
// arena.close() chạy lúc thoát try-with-resources.
~~~

Khi close hoàn tất bình thường, scope hết hiệu lực. Truy cập Java qua các segment liên kết với scope đó sẽ bị chặn. Chỉ owner thread được đóng confined arena.

### Shared Arena

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment block = arena.allocate(32);
    // Có thể có nhiều Java worker dùng cùng scope,
    // nhưng phải chờ mọi worker xong trước khi close.
}
~~~

Shared arena **không tự biến dữ liệu thành thread-safe** và **không tự ngắt native worker** đang giữ raw pointer. Phải có cơ chế stop/unregister/join hoặc acknowledgment rằng mọi consumer đã hoàn tất. Nếu một downcall còn đang truy cập segment của arena, close cũng có thể thất bại do ràng buộc truy cập đồng thời.

### Auto Arena

Cleanup liên kết với auto arena có thể được thực thi khi runtime xác định vùng không còn reachable, **không phải tại một thời điểm do code chủ động chọn**. Đừng dựa vào Arena.ofAuto() để đóng kết nối thiết bị đúng hạn, giải phóng socket khan hiếm hay gửi một thông điệp protocol quan trọng ngay khi người dùng bấm đóng.

Nếu cleanup action giữ một reference mạnh tới arena hoặc tới thứ làm arena vẫn reachable, bộ dọn tự động có thể **không bao giờ đủ điều kiện kích hoạt**. Vì vậy khi cleanup có side effects quan trọng, ưu tiên scope đóng tường minh.

### Global Arena

Arena.global không thể đóng tường minh; gắn resource đòi hỏi giải phóng sớm vào lifetime toàn JVM thường là **memory/resource leak xét theo vòng đời ứng dụng**. Global scope không phải một giải pháp bảo vệ ownership.

## 5. Scope đúng là scope của quyền sở hữu thực tế

Không phải cứ “hai thao tác nằm cùng một phương thức Java” thì cleanup nên gắn cùng arena. Hãy chọn scope theo **khi nào consumer cuối cùng hoàn tất**:

~~~text
Java request bắt đầu
    |
    +-- tạo native resource (Java trở thành owner)
    |
    +-- truyền tới native library / worker
    |                     |
    |                 còn đang dùng?
    |                     |
    +-- Java method return  (chưa chắc resource đã rảnh)
                          |
                    worker hoàn tất
                          |
                unregister / drain / join
                          |
                    owner.close()
                          |
              đúng native deallocator MỘT lần
~~~

Nếu C giữ pointer sau một downcall, **đóng request-local Arena ngay khi Java method return là quá sớm**. Ngược lại, gắn một request nhỏ vào Arena.global khiến resource không được giải phóng đúng hạn.

Một checklist nhanh để chọn scope: Ai yêu cầu resource? Ai được đọc/ghi? Có background thread/callback? Có handoff ownership? Có một điểm rõ ràng xác nhận tất cả consumers đã kết thúc chưa? Nếu chưa, đừng đóng resource.

## 6. Gắn cleanup action bằng MemorySegment.reinterpret

FFM JDK 22 có overload restricted:

~~~java
MemorySegment managed =
    rawPointer.reinterpret(byteSize, ownerArena, cleanupAction);
~~~

Các thành phần:

- **rawPointer**: MemorySegment biểu diễn địa chỉ native đang muốn quản lý.
- **byteSize**: số byte thật sự hợp lệ theo hợp đồng native.
- **ownerArena**: arena có lifetime phản ánh **thời hạn Java sở hữu resource**.
- **cleanupAction**: **Consumer<MemorySegment>** được thực thi khi scope của arena mất hiệu lực, ví dụ trong quá trình đóng Arena.ofConfined/ofShared.

**Đặc biệt quan trọng:** **reinterpret tự nó không cấp phát thêm và không giải phóng bộ nhớ**. Việc giải phóng xảy ra **chỉ nếu cleanup action thực sự gọi đúng native deallocator**. Nếu cleanup là null, alias chỉ có scope/size được gắn lại, không có cơ chế trả allocation C cho allocator của C.

### Pointer C trả về thường có byteSize bằng 0

Giả sử một C function trả **int32_t\***. FFM biểu diễn con trỏ trả về như một **MemorySegment zero-length**, thường có scope luôn sống. Bạn không thể get(JAVA_INT, 0) trực tiếp trên view 0 byte.

~~~java
MemorySegment raw = (MemorySegment) create.invokeExact(42);
// raw.byteSize() thường bằng 0 cho pointer return.
~~~

Đây là snippet, giả định MethodHandle **create** có signature **(int) -> MemorySegment**. Để đọc an toàn, chỉ khi đã xác minh C thực sự cấp ít nhất **sizeof(int32_t)** byte mới được gắn size và scope:

~~~java
MemorySegment managed = raw.reinterpret(
    ValueLayout.JAVA_INT.byteSize(),
    ownerArena,
    cleanupAction
);
~~~

**Cảnh báo:** reinterpret là restricted method vì bạn có thể khai báo sai size/lifetime. FFM không thể chứng minh con trỏ còn sống, đủ byte hoặc đúng alignment. Một pointer đã free vẫn có thể được reinterpret và sau đó gây crash khi dereference.

### Cleanup action nhận một segment khác với managed

Theo JDK 22 API, cleanup Consumer được truyền một segment **mới** có cùng native address, với scope toàn cục và số byte phù hợp. Nó được cung cấp để có thể truyền **địa chỉ** vào hàm free ngay lúc scope gốc trở nên không hợp lệ.

~~~java
java.util.function.Consumer<MemorySegment> cleanup = ptr -> {
    try {
        destroyHandle.invokeExact(ptr);
    } catch (Throwable failure) {
        throw new IllegalStateException(
                "Native destroy failed", failure
        );
    }
};
~~~

Đây là snippet, giả định **destroyHandle** có MethodType **(MemorySegment)void**. Hãy dùng cleanup pointer **chỉ để hoàn tất giải phóng**, không lưu nó vào global/list hoặc gửi ra ngoài. Vì pointer cleanup có global scope, để nó thoát ra ngoài có thể dẫn tới dereference sau free mà FFM không chặn được.

Không gọi **managed.get(...)** trong cleanup rồi tưởng managed còn sống; thời điểm cleanup là lúc scope đang hết hiệu lực. Cleanup nên ngắn, có mục đích cụ thể, tránh callback làm phát sinh thao tác native không cần thiết.

## 7. Tránh double-free: đăng ký đúng một lần cho mỗi ownership

### 7.1. Một owner, nhiều aliases không sở hữu

~~~text
         Native allocation P
                  |
         owner Arena R
                  |
     reinterpret(P, R, destroy)    <-- ĐÚNG MỘT registration
                  |
              managed
            /    |     \
        asSlice viewA viewB
                  |
     R.close() -> destroy(P) MỘT LẦN
~~~

Những aliases, view hoặc slice **không nhận thêm cleanup riêng**. Chúng cùng dùng backing memory và bị vô hiệu hóa khi owner Arena đóng.

### 7.2. Sai: hai cleanup registrations cùng free một pointer

~~~java
// CỐ Ý SAI: hai cleanup độc lập cùng trỏ một allocation.
MemorySegment a = raw.reinterpret(size, arenaA, freeAction);
MemorySegment b = raw.reinterpret(size, arenaB, freeAction);
// arenaA.close() -> free(P)
// arenaB.close() -> free(P) lần hai: double-free!
~~~

Đây chỉ là **mã cảnh báo không được chạy**. Dù hai Java views có scope riêng, C heap vẫn chỉ có **một allocation**. FFM không có cơ chế tự nhận ra “pointer này đã được registered ở arena khác”.

### 7.3. Sai: vừa free thủ công vừa gắn arena cleanup

~~~java
// CỐ Ý SAI: resource vừa có auto cleanup vừa manual free.
MemorySegment managed = raw.reinterpret(size, arena, freeAction);
freeHandle.invokeExact(raw); // Giải phóng ngay.
// ...
arena.close();               // Callback sẽ free lần nữa.
~~~

Đây là **pseudocode Java/FFM về anti-pattern**, không phải chương trình độc lập. Đừng chạy một lần free để “kiểm tra” bằng debugger trên data thật: double-free có thể gây hỏng heap trước khi bạn thấy stack trace.

### 7.4. Sai: free alias thay vì owner

Một slice không sở hữu allocation riêng. Gọi free bằng địa chỉ của slice ở **giữa** allocation còn có thể tạo invalid free. Ngay cả khi slice bắt đầu đúng base address, nó cũng **không có quyền giải phóng** nếu owner khác đã đăng ký cleanup.

**Quy tắc:** Giải phóng qua **owner record** đã biết allocator/deallocator chính xác; không free chỉ vì có một MemorySegment.address().

### 7.5. Arena.close không idempotent

Theo tài liệu JDK 22, **Arena.close() không idempotent**: cố đóng một Arena đã đóng sẽ ném **IllegalStateException**. Đây là tín hiệu lỗi lifecycle. Không nên hiểu rằng gọi close lần hai là một cách hợp lệ để “bảo đảm dọn dẹp thêm”.

Tuy nhiên cần phân biệt:

- **Gọi close hai lần trên cùng một Arena**: API thông thường ném exception lần thứ hai. Điều đó **khác** với việc chắc chắn đã gọi C free hai lần.
- **Đăng ký hai cleanup callbacks cho cùng C pointer, hoặc manual free cộng callback**: thực sự có thể dẫn tới **double-free**.
- **Hai owner có địa chỉ khác nhau**: chúng có thể giải phóng riêng nếu mỗi owner sở hữu allocation riêng đúng theo C contract.

Việc close ném exception không có nghĩa một cleanup action trong hệ thống phức tạp đã hoàn toàn thành công; luôn có một đường lỗi/giám sát rõ ràng cho native deallocator.

## 8. Ví dụ hoàn chỉnh Java 22+ kết hợp C11: cleanup đúng một lần

Ví dụ tạo một **int32_t** trong C bằng malloc rồi giao ownership cho Java. Java gắn một cleanup action bằng **reinterpret(size, ownerArena, cleanup)**. Khi owner Arena đóng, cleanup gọi **đúng hàm release của thư viện C**. Thư viện có bộ đếm để chứng minh có **một lần release**, sau đó Java xác nhận managed view đã bị vô hiệu hóa.

Chương trình tạo **hai Arena** với trách nhiệm khác nhau:

- **libraryArena**: giữ shared library và các downcall MethodHandles sống để cleanup còn gọi được hàm release.
- **ownerArena**: quản **một C allocation được chuyển quyền cho Java**; được đóng trước libraryArena.

Không gọi manual free, không tạo cleanup riêng cho slice.

### Bước 1 — Tạo scope_cleanup.c

~~~c
#include <stdint.h>
#include <stdlib.h>

#if defined(_WIN32)
#  define API __declspec(dllexport)
#else
#  define API __attribute__((visibility("default")))
#endif

/*
 * Demo chạy đơn luồng; bộ đếm không thiết kế thread-safe.
 * Một lần make thành công -> caller phải release đúng một lần.
 */
static int32_t release_counter = 0;

/* Trả NULL khi malloc thất bại. */
API int32_t *demo_make_int(int32_t value) {
    int32_t *p = (int32_t *)malloc(sizeof(*p));
    if (p != NULL) {
        *p = value;
    }
    return p;
}

/*
 * Contract: p là pointer chưa được release, do
 * demo_make_int cấp và ownership thuộc caller.
 */
API void demo_release_int(int32_t *p) {
    if (p != NULL) {
        free(p);
        release_counter++;
    }
}

API int32_t demo_release_count(void) {
    return release_counter;
}
~~~

**C contract không thể bỏ qua:** demo_release_int chỉ được gọi trên pointer do demo_make_int trả thành công, chưa release và chưa chuyển ownership tiếp. Nếu truyền địa chỉ lạ hoặc gọi hai lần, điều kiện tiền đề không còn đúng; chính C function này **không phải một bộ phát hiện double-free**. Chỉ số release_counter chứng minh đường thành công của demo, không có nghĩa gọi lại sau free sẽ an toàn.

Đây là ví dụ C11 đơn giản trên hệ điều hành/ABI phổ biến có **int32_t**. Bộ đếm static được đọc/ghi tuần tự từ cùng một Java thread; nếu sử dụng nhiều thread trong production phải thêm synchronization/atomic thích hợp.

### Bước 2 — Biên dịch native library

**Linux (GCC hoặc Clang):**

~~~bash
cc -std=c11 -O2 -fPIC -shared \
  scope_cleanup.c -o libscopecleanup.so
~~~

**macOS (Clang):**

~~~bash
clang -std=c11 -O2 -fPIC -dynamiclib \
  scope_cleanup.c -o libscopecleanup.dylib
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /nologo /W4 /LD scope_cleanup.c /link /OUT:scopecleanup.dll
~~~

Chỉ chạy **một lệnh phù hợp hệ điều hành**. Output dùng tên thư viện tương ứng với **System.mapLibraryName("scopecleanup")**. Biên dịch cùng kiến trúc/ABI với JDK; cần bảo đảm C runtime và binary dependencies có thể được nạp.

### Bước 3 — Tạo ScopeCleanupDemo.java

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class ScopeCleanupDemo {
    private ScopeCleanupDemo() {
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        /*
         * libraryArena có lifetime LỚN HƠN resource owner.
         * Cleanup của owner vẫn phải gọi được demo_release_int.
         */
        try (Arena libraryArena = Arena.ofConfined()) {
            Path path = Path.of(
                    System.mapLibraryName("scopecleanup")
            ).toAbsolutePath();

            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(path, libraryArena);

            // C: int32_t *demo_make_int(int32_t value)
            MethodHandle make = linker.downcallHandle(
                    symbols.find("demo_make_int").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT
                    )
            );

            // C: void demo_release_int(int32_t *p)
            MethodHandle release = linker.downcallHandle(
                    symbols.find("demo_release_int").orElseThrow(),
                    FunctionDescriptor.ofVoid(ValueLayout.ADDRESS)
            );

            // C: int32_t demo_release_count(void)
            MethodHandle releaseCount = linker.downcallHandle(
                    symbols.find("demo_release_count").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT)
            );

            System.out.println(
                    "releasedBefore=" + (int) releaseCount.invokeExact()
            );

            MemorySegment managed;

            /*
             * Owner scope: một allocation của C, một cleanup.
             * Java sẽ đóng owner TRƯỚC libraryArena.
             */
            try (Arena ownerArena = Arena.ofConfined()) {
                MemorySegment raw =
                        (MemorySegment) make.invokeExact(42);

                if (raw.address() == 0L) {
                    throw new OutOfMemoryError(
                            "demo_make_int returned NULL"
                    );
                }

                /*
                 * C đã cấp ít nhất sizeof(int32_t) byte.
                 * reinterpret KHÔNG sở hữu tự động; Consumer
                 * mới là thứ gọi deallocator lúc owner đóng.
                 */
                managed = raw.reinterpret(
                        ValueLayout.JAVA_INT.byteSize(),
                        ownerArena,
                        cleanupPointer -> {
                            try {
                                release.invokeExact(cleanupPointer);
                            } catch (Throwable failure) {
                                throw new IllegalStateException(
                                        "Native release failed", failure
                                );
                            }
                        }
                );

                // Slice chỉ là view, KHÔNG đăng ký cleanup mới.
                MemorySegment alias = managed.asSlice(
                        0, ValueLayout.JAVA_INT.byteSize()
                );
                System.out.println(
                        "value=" + alias.get(ValueLayout.JAVA_INT, 0)
                );

                /*
                 * Không gọi release.invokeExact(raw) ở đây.
                 * Quyền release đã nằm trong ownerArena.
                 */
            } // ownerArena.close() -> demo_release_int đúng một lần.

            System.out.println(
                    "releasedAfter=" + (int) releaseCount.invokeExact()
            );

            try {
                managed.get(ValueLayout.JAVA_INT, 0);
                System.out.println("accessAfterClose=unexpected");
            } catch (IllegalStateException expected) {
                System.out.println("accessAfterClose=blocked");
            }
        } // Đến đây mới đóng libraryArena.
    }
}
~~~

### Bước 4 — Biên dịch và chạy

Đặt file Java và native library vừa build **trong thư mục làm việc hiện tại**. Sử dụng **JDK 22 hoặc mới hơn**:

~~~bash
javac ScopeCleanupDemo.java
java --enable-native-access=ALL-UNNAMED ScopeCleanupDemo
~~~

**Stdout chính xác khi build/library load và native call thành công:**

~~~text
releasedBefore=0
value=42
releasedAfter=1
accessAfterClose=blocked
~~~

Ý nghĩa từng dòng:

- **releasedBefore=0:** chưa gọi release của C.
- **value=42:** dữ liệu int32_t được C cấp và Java đọc qua managed alias sau khi gắn đúng size/scope.
- **releasedAfter=1:** ownerArena vừa đóng; custom cleanup đã gọi **demo_release_int** một lần.
- **accessAfterClose=blocked:** managed segment có scope của ownerArena đã hết hiệu lực; FFM từ chối Java dereference sau khi close.

**Phạm vi kết quả:** Output được suy ra từ code và hợp đồng FFM/C trong môi trường build thành công, không có một lần chạy thực tế nào được khẳng định ở đây. Nếu library thiếu hoặc JDK/native access không phù hợp, chương trình có thể fail trước khi in đủ các dòng.

### Bước 5 — Điều ví dụ đã làm đúng

1. **C cung cấp deallocator tương ứng:** pointer từ demo_make_int được giải phóng bằng **demo_release_int** cùng thư viện.
2. **Ownership đã rõ:** Java nhận quyền giải phóng đúng một allocation sau khi create thành công.
3. **Resource scope phù hợp:** confined ownerArena chỉ sống trong khoảng code cần dùng pointer.
4. **Chỉ một cleanup registration:** một lần gọi reinterpret với một Consumer. Slice alias không đăng ký release.
5. **Library scope sống dài hơn:** libraryArena đóng **sau** ownerArena. Cleanup không gọi function pointer đã bị unload.
6. **Không free thủ công:** code không có đường free thứ hai đối với raw pointer.
7. **Không đọc raw sau close:** raw có thể mang scope toàn cục, nhưng nó vẫn trỏ tới allocation đã free. Managed alias mới là interface được code sử dụng.
8. **Sau close Java access bị chặn:** đó là temporal safety của view được gắn owner scope; không phải bằng chứng rằng C không thể vi phạm memory safety.
9. **Không có worker nền:** demo không cần shared arena hoặc synchronization phức tạp. Production phải bổ sung nếu có concurrent consumers.

### Hạn chế cố ý của demo

Code ngắn để tập trung vào **cleanup một lần**. Production có thể cần xử lý lỗi khi tạo wrapper trước khi registration hoàn tất, chống gọi API khi resource đang closing, theo dõi native status khi destroy và thích ứng ABI cho nhiều nền tảng. Một deallocator trả **void** cũng có thể thất bại ngầm theo thư viện C; callback exception phía Java không có nghĩa C memory chắc chắn đã được giải phóng.

Nếu **reinterpret** bị lỗi trước khi việc chuyển ownership được thiết lập, con trỏ C vừa tạo có nguy cơ **leak**, vì chưa có owner cleanup được gắn. Hệ thống production nên thiết kế một helper quản trách nhiệm ownership transfer nguyên tử ở mức ứng dụng, có nhánh release khi setup không thành công và test đường lỗi; tránh đăng ký trước rồi vô tình free lần nữa trong nhánh catch.

## 9. Đường lỗi: khi nào ai phải dọn?

Tạo một resource native không phải lúc nào cũng thành công:

~~~text
C create() ---> NULL -----------------> Không có allocation thành công
        |
        +--> pointer P
                 |
          setup wrapper / metadata
                 |
        +--------+-----------+
        |                    |
   setup thành công      setup thất bại
        |                    |
  owner nhận P       creator/caller vẫn
  (cleanup đăng ký)   phải release P nếu đang sở hữu
        |                    |
  owner.close()       gọi deallocator đúng một lần
        |
  release P đúng một lần
~~~

Cần phân biệt ba thời điểm:

- **Trước khi nhận quyền sở hữu:** Nếu API chỉ cho mượn pointer, Java tuyệt đối không free khi có lỗi.
- **Đã nhận quyền sở hữu nhưng chưa giao cho wrapper:** Nếu bước khởi tạo Java thất bại, phải có nhánh cleanup cho pointer chưa đăng ký.
- **Sau khi wrapper/arena sở hữu thành công:** Mọi nhánh lỗi Java đều đi qua **owner.close()**; **không manual free thêm** trong catch/finally.

### Một owner record có trạng thái rõ

Một state machine hữu ích:

~~~text
    NOT_ALLOCATED
          |
      create OK
          v
       OWNED_RAW
          |
     bind to scope
          v
     OWNED_SCOPED
          |
    close / release
          v
        CLOSED
~~~

Các transition phải được thiết kế rõ ràng. Không cho hai đường độc lập cùng chuyển từ OWNED_SCOPED sang free. Nếu có concurrent close, quản lý state bằng synchronization/atomic mechanism ở **lớp sở hữu**, không chỉ trông chờ vào trường boolean không đồng bộ.

### Tại sao chỉ thêm AtomicBoolean chưa đủ?

Một wrapper Java có thể dùng **AtomicBoolean.compareAndSet(false, true)** để ngăn hai luồng cùng gọi deallocator thông qua wrapper. Nhưng nó **không** biết thư viện C hoặc một cleanup action khác đã free pointer hay chưa. Đồng thời nếu native destroy có hành vi thất bại phức tạp, việc đánh dấu CLOSED trước khi gọi destroy có thể để lại leak, còn đánh dấu sau khi destroy có thể tạo nguy cơ retry sai. Cần xác định **mô hình lỗi của deallocator**, điều kiện được phép retry và ownership thực từ contract.

Nếu chọn wrapper AutoCloseable có close idempotent theo thiết kế ứng dụng, **đừng đồng thời đăng ký arena cleanup cùng deallocator**. Chỉ một cơ chế sở hữu cuối cùng.

## 10. Không nhầm close hai lần với double-free

Một lỗi Java phổ biến:

~~~java
// CỐ Ý SAI: try-with-resources đã tự close.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(32);
    arena.close();
} // Java thử close arena một lần nữa.
~~~

Đây là **anti-pattern minh họa**, không nên chạy như workflow thực. **Arena.close** không idempotent theo JDK 22; close lần thứ hai có thể ném IllegalStateException. Nhưng điều đó **không phải** bằng chứng rằng C free đã thực thi hai lần.

Ngược lại, nếu có **hai cleanup registrations** trên hai arenas khác nhau cho cùng một pointer C, mỗi arena đều có thể close hợp lệ, và C thực sự bị yêu cầu giải phóng cùng allocation **hai lần**. Đây mới là double-free nguy hiểm.

### Chọn một trong hai chiến lược rõ ràng

**Chiến lược A — Scope owns resource:**

~~~text
create P -> reinterpret(P, ownerArena, destroy)
         -> xử lý P
         -> ownerArena.close() -> destroy(P)
~~~

**Chiến lược B — Manual wrapper owns resource:**

~~~text
create P -> NativeHandle(P)
         -> xử lý P
         -> NativeHandle.close() -> destroy(P)
~~~

Không xây hệ thống trong đó **NativeHandle.close** gọi destroy(P) rồi **Arena.close** cũng chạy custom destroy(P), trừ khi đó là các reference counts **khác nhau đã được retain hợp lệ**. “Có nhiều đối tượng Java trỏ cùng P” không tự tạo thêm ownership shares.

## 11. Library lifetime và thứ tự cleanup

Một sai lầm không trực tiếp là double-free nhưng có thể gây crash:

~~~text
1. libraryLookup("libnative.so", libraryArena)
2. lấy MethodHandle destroy từ library
3. create P, register custom cleanup vào resourceArena
4. ĐÓNG libraryArena trước
5. resourceArena.close() -> gọi destroy tại thư viện đã unload!
~~~

**SymbolLookup.libraryLookup(path, arena)** gắn lifetime của library lookup vào arena được truyền. Khi scope tương ứng hết hiệu lực, library có thể bị unload theo hợp đồng API. Do đó **cần giữ library/symbols/deallocator tồn tại lâu hơn resource owner**.

Mô hình nested try đúng:

~~~java
try (Arena libraryArena = Arena.ofConfined()) {
    // Tải library, tìm create/destroy functions.
    try (Arena resourceArena = Arena.ofConfined()) {
        // Tạo C resource, register cleanup vào resourceArena.
    } // Gọi destroy trong khi library vẫn còn được nạp.
} // Sau cùng mới đóng library arena.
~~~

Đoạn này là **skeleton**, thiếu phần Java tạo handles và resource; ví dụ hoàn chỉnh ở mục 8 thể hiện thứ tự chính xác.

Nếu ứng dụng có nhiều native resources, một libraryArena chung có thể sống tới shutdown của module, còn mỗi resource hoặc mỗi batch có ownerArena riêng. Nhưng nếu cùng arena gắn cleanup cho nhiều resources và chúng có dependency lẫn nhau, **không mặc định thứ tự chạy cleanup callbacks** theo thứ tự đăng ký, trừ khi tài liệu API có bảo đảm cụ thể. Để kiểm soát thứ tự (ví dụ destroy child trước parent), thiết kế **nested scopes/owner graph** rõ ràng.

## 12. Parent–child ownership và resource graph

Một library C có thể có:

~~~c
Database *db_open(void);
Statement *db_prepare(Database *db, const char *sql);
void statement_destroy(Statement *s);
void db_close(Database *db);
~~~

Giả sử hợp đồng yêu cầu **Statement chỉ hợp lệ khi Database vẫn mở**. Nếu Java register cleanup cho cả Database và Statement vào cùng một arena rồi dựa vào thứ tự không được cam kết, có thể đóng DB trước Statement.

Mô hình owner đúng:

~~~text
   Database owner arena
         |
       db handle
         |
   Statement owner arena
         |
      stmt handle

Đóng statement scope TRƯỚC.
Đóng database scope SAU.
~~~

Ví dụ skeleton:

~~~java
try (Arena databaseScope = Arena.ofConfined()) {
    // dbCreate, dbDestroy; gắn cleanup của database.
    try (Arena statementScope = Arena.ofConfined()) {
        // stmtCreate từ db; gắn cleanup của statement.
        // Sử dụng statement.
    } // statement cleanup chạy trước.
} // database cleanup chạy sau.
~~~

Không tự giải phóng **mỗi MemorySegment.asSlice** của Statement như một object riêng. Nếu C API nói **db_close tự hủy mọi statement**, Java không được đồng thời tự hủy lại các statements đó. Contract có thể thay đổi cách ownership được phân chia; nested scopes chỉ là một mô hình sau khi đã biết đúng quy tắc của thư viện.

### Transfer ownership vào C

Đôi khi hàm C **nhận ownership**:

~~~c
/* Giả định contract: on success, C nhận ownership buffer. */
int pipeline_take_buffer(void *buffer);
~~~

Nếu gọi thành công và C đã nhận quyền giải phóng, cleanup Java gắn trước đó phải **không còn quyền free**. Không nên cố “gỡ callback” bằng cách để arena sống vô hạn hoặc để callback tự phỏng đoán. Hãy dùng API wrapper có **cơ chế transfer ownership rõ**, state transition có synchronization và cleanup gắn đúng giai đoạn; trong nhiều trường hợp, dùng **manual owner** sẽ phù hợp hơn scope cleanup cố định.

Nếu C API có thể chuyển ownership **chỉ khi thành công**, cần ghi chính xác return code và trạng thái khi lỗi: nếu thất bại thì Java vẫn sở hữu, nếu thành công thì native library sở hữu. Đừng giải phóng cả hai phía.

## 13. Các vấn đề thread và callback bất đồng bộ

### 13.1. Confined arena chỉ cho owner thread

Nếu Java owner dùng **Arena.ofConfined**, không chuyển managed segment cho Java thread khác rồi thao tác get/set từ thread đó. Scope checks có thể ném **WrongThreadException**. Cũng không giả định native deallocator an toàn khi được gọi từ một callback/thread bất kỳ: có API yêu cầu giải phóng trên chính thread khởi tạo.

Đóng confined arena phải thực hiện từ owner thread. Nếu resource được dùng bởi worker và cần dọn trên worker, hãy thiết kế một owner loop nhận lệnh close trên đúng thread.

### 13.2. Shared arena cho phép truy cập đa luồng, không cấp đồng bộ tự động

**Arena.ofShared** hữu ích khi nhiều Java threads cần vùng nhớ được chia sẻ. Tuy nhiên:

- Java writes vào cùng bytes vẫn cần memory-order/synchronization theo hợp đồng dữ liệu.
- Không đóng arena khi worker còn đang đọc/ghi hoặc downcall còn active.
- Nếu native C tự giữ raw address, FFM không thể theo dõi mọi native read/write để tự bảo vệ lifetime.
- Có thể có IllegalStateException nếu close xung đột với một access đang diễn ra.
- Một worker bị hủy giữa chừng có thể vẫn có native work chưa được xác nhận hoàn tất.

Cần có **stop accepting new work → cancel/drain → join/await completion → owner.close**.

### 13.3. Callback và upcall stub có lifetime riêng

Một C API có thể giữ function pointer của **Linker.upcallStub**. Stub được tạo với Arena và hết hiệu lực theo scope của Arena. Nếu C còn giữ và gọi pointer sau khi arena đóng, đó có thể là **use-after-free ở cấp function pointer**.

Cleanup đúng không chỉ giải phóng data pointer mà còn phải:

1. Unregister callback ở phía C.
2. Chờ callback đang chạy kết thúc.
3. Đóng resource data theo thứ tự dependency.
4. Đóng arena chứa upcall stub.
5. Sau cùng unload library nếu thích hợp.

Không coi callback pointer, dữ liệu context và resource handle là cùng một allocation; mỗi loại có owner và deallocator/arena riêng.

### 13.4. Arena.ofAuto và thread-affine cleanup

Vì auto arena được dọn khi runtime xác định unreachable, code không kiểm soát chắc chắn thread hoặc thời điểm cleanup. Nếu native API quy định destroy phải chạy trên UI thread, event loop hoặc thread mở resource, **đừng chọn GC-timed cleanup** làm cơ chế chính. Sử dụng owner thread + explicit close/dispatch hoặc một native resource manager biết thread affinity.

## 14. Cleanup action thất bại thì sao?

Không phải mọi hàm release đều trả void và “không lỗi”. Một C API có thể trả error code, đòi hỏi status logging, timeout hoặc không được retry nếu trạng thái đã thay đổi.

Ví dụ:

~~~c
/* Header minh họa, không có implementation. */
int remote_resource_close(struct RemoteResource *r);
~~~

Khi gắn cleanup:

- Nếu hàm close có thể lỗi, xác định **khi nào ownership được xem là đã giải phóng**.
- Ghi nhận lỗi bằng cơ chế quan sát được, không nuốt âm thầm.
- Không retry một cách mù quáng: lần đầu có thể đã giải phóng native memory nhưng trả lỗi do bước phụ, retry có thể double-free.
- Nếu cần retry, contract phải hỗ trợ retry hoặc idempotency thật sự.
- Nếu close phụ thuộc network/async protocol, cleanup callback chạy lúc Arena.close có thể không phù hợp; cân nhắc một abstraction close tường minh trả kết quả.

Theo JDK 22, nếu custom cleanup action ném exception, **Arena.close có thể ném RuntimeException**. Đừng mặc định việc close thất bại nghĩa resource chắc chắn còn sống. Cũng không dùng riêng một boolean "isAlive()" để chứng minh deallocator C đã hoàn tất: Java scope status và native resource state là hai khái niệm khác nhau.

### Một lỗi thường bị bỏ qua: cleanup giữ chính arena sống

Với **Arena.ofAuto()**, nếu cleanup lambda capture một object tham chiếu mạnh trở lại chính arena/segment của nó, arena có thể không trở nên unreachable, khiến callback không chạy. Ví dụ ý tưởng sai:

~~~text
autoArena -> resource -> cleanupAction -> autoArena
           ^                         |
           +-------------------------+
~~~

Đồ thị tham chiếu cần được xem xét theo reachability thực tế; đặc biệt, **không capture autoArena trong cleanup action rồi kỳ vọng nó tự thu hồi đúng lúc**. Scope đóng tường minh thường dễ audit hơn với tài nguyên quan trọng.

## 15. Bảo vệ trước pointer alias và địa chỉ được tái sử dụng

Sau khi free(P), allocator C có thể dùng **địa chỉ P** cho một allocation mới. Vì vậy:

- Không dùng địa chỉ (long address) như một **ID duy nhất vĩnh viễn** cho resource.
- Không suy ra “địa chỉ vẫn giống nhau nên resource vẫn là resource cũ”.
- Một raw MemorySegment global-scoped có thể vẫn chứa số địa chỉ P sau khi P được giải phóng. Nó **không tự bị vô hiệu hóa** theo ownerArena mà bạn tạo ở một alias khác.
- Nếu code lưu raw pointer ở nhiều nơi, việc bảo vệ managed view bằng scope chưa ngăn các nơi khác dereference raw/alias không được quản lý.

**Thiết kế tốt:** che raw pointer trong một owner abstraction, chỉ xuất API có kiểm tra trạng thái, không để các module tùy tiện reinterpret/free cùng address. Khi cần truyền pointer sang C, chỉ cho mượn trong một lời gọi có lifetime được xác nhận hoặc tạo cơ chế borrow tracking/concurrent owner rõ ràng.

### Phân biệt double-free với use-after-free

| Tình trạng | Ví dụ | Hậu quả |
| --- | --- | --- |
| **Double-free** | free(P), rồi free(P) lần nữa | Heap corruption/crash; undefined behavior |
| **Use-after-free** | free(P), sau đó get dữ liệu ở P | Đọc rác, ghi phá heap, crash |
| **Memory leak** | malloc(P) nhưng không bao giờ free | Tăng native RSS/resource exhaustion |
| **Invalid free** | free(P + 4) hoặc free(borrowed P) | Undefined behavior |
| **Premature free** | Đóng Arena trước khi C worker dùng xong P | Native use-after-free |
| **Wrong deallocator** | C dùng custom allocator nhưng Java gọi libc free | Heap corruption/allocator violation |
| **Double-close of Arena** | close cùng Arena hai lần | Lần sau thường ném IllegalStateException; không đồng nghĩa free(P) hai lần |

Nếu phát hiện một native crash liên quan heap, nên kiểm tra đồng thời **ownership, lifetime, aliasing và error path** thay vì chỉ grep những lời gọi free xuất hiện cạnh nhau.

## 16. Chiến lược thiết kế owner rõ ràng

### Chiến lược A: một Arena theo request

Phù hợp khi C API trả **một hoặc nhiều owned pointers** có lifetime bằng một request, không có native consumer nào vượt qua request.

~~~text
request start
   |
   ownerArena = ofConfined()
   |
   create owned handles
   |
   attach cleanup cho từng handle (không duplicate)
   |
   xử lý đồng bộ
   |
   tất cả consumers hoàn tất
   |
   ownerArena.close()
   |
request end
~~~

Nếu các resources có dependency, dùng **nested arenas** hoặc chủ động quản thứ tự cleanup thay vì dựa vào thứ tự thực thi của nhiều callbacks cùng arena.

### Chiến lược B: một Arena theo session

Phù hợp khi một session mở một C object, xử lý nhiều request và đóng khi session kết thúc. Không đưa session object vào request-local scope. Session owner phải có một hàm close được điều phối; sau close, mọi request mới bị từ chối.

Nếu nhiều thread dùng chung session, cần một cơ chế **reference/borrow counting** hoặc lock nhằm bảo đảm không đóng khi còn request active.

### Chiến lược C: owner wrapper thay vì auto cleanup

Phù hợp khi resource được **transfer ownership**, có close trả trạng thái, cần retry hợp lệ hoặc cần đóng theo thread/event loop xác định. Một wrapper AutoCloseable có thể giữ pointer, custom deallocator và state chuyển đổi.

**Điều kiện:** khi wrapper là owner, không đăng ký thêm **reinterpret(..., cleanup)** gọi cùng deallocator. Wrapper chịu trách nhiệm duy nhất. MemorySegment mang scope phù hợp vẫn có thể dùng để kiểm tra truy cập, nhưng không được có một release path thứ hai.

### Chiến lược D: batch arena với custom cleanup từng handle

Nếu các resources sống theo cùng batch và độc lập, có thể gắn cleanup cho nhiều **địa chỉ khác nhau** vào cùng arena. Đừng hiểu “một arena có nhiều actions” là sai: sai nằm ở **một allocation bị release nhiều lần** hoặc **thứ tự dependency không được bảo vệ**.

Khi batch xong, cần chắc chắn không còn C callback hoặc thread nào đang giữ địa chỉ. Sau đó close một lần; tất cả các cleanup hợp lệ được thực hiện theo contract runtime, nhưng nếu có dependencies phức tạp cần thứ tự riêng.

## 17. Kiểm thử để phát hiện double-free và leak

Nên có các bài test sau với **native binary thật**:

| Test | Cách thực hiện | Kết quả cần xác minh |
| --- | --- | --- |
| **Happy path** | create → use → owner.close | đúng một destroy, dữ liệu trước close hợp lệ |
| **Null allocation** | native create trả NULL | không đăng ký cleanup sai, có lỗi rõ |
| **Setup failure** | tạo pointer thành công, bước tạo wrapper thất bại | đúng một cleanup qua nhánh sở hữu phù hợp |
| **Java exception during use** | ném exception trong try | try-with-resources vẫn close owner đúng cách |
| **Borrowed pointer** | C trả view không owned | Java không gọi free |
| **Multiple aliases** | tạo nhiều asSlice/view | chỉ owner duy nhất dọn |
| **Duplicate close** | thử close cùng Arena hai lần trong test kiểm soát | Java báo IllegalStateException; không dùng như free thứ hai |
| **Concurrent use** | worker giữ segment, owner muốn close | không đóng trước consumer cuối |
| **Native callback** | unregister rồi close | không callback sau khi stub/data hết hiệu lực |
| **Library unload** | đóng resource rồi mới đóng library arena | cleanup gọi được deallocator |
| **Different allocator** | C custom allocator + matching destroy | không gọi libc free sai |
| **Refcount** | retain/release theo ownership shares | số release cân bằng số retain/ownership |
| **Long-lived sessions** | mở/đóng hàng nghìn session | native RSS/handle count ổn định |

### Native diagnostics

- Trên Linux/macOS với toolchain phù hợp, có thể build C test library với **AddressSanitizer (ASan)** để phát hiện double-free/use-after-free ở native code.
- Dùng **UndefinedBehaviorSanitizer**, Valgrind hoặc công cụ heap diagnostics tùy OS khi phù hợp.
- Nếu JNI/FFM crash, lưu JVM crash log/core dump và native stack symbols.
- Không coi mọi **IllegalStateException** là bằng chứng chương trình memory-safe: C có thể phá memory bên ngoài các access được FFM kiểm soát.
- Với third-party untrusted native code, chạy integration tests ở **process riêng** để một crash không giết toàn bộ test runner.

Một bộ đếm release như demo hữu ích cho smoke test nhưng không thay ASan. Nếu code thực sự double-free, process có thể crash trước khi bộ đếm tăng đến 2.

## 18. Các lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Gắn **free** vào segment do Arena.allocate cấp | Arena đã sở hữu allocation | Chỉ close Arena |
| Gắn cleanup cho borrowed pointer | Java không có quyền free | Để owner C giải phóng; Java chỉ mượn đúng lifetime |
| Gắn hai cleanup cùng address | Hai owners nghĩ mình sở hữu một allocation | Chỉ một owner, slices không owning |
| Manual free rồi đợi arena cleanup | Deallocator được gọi hai lần | Chọn manual **hoặc** scope cleanup |
| Reinterpret xong tưởng memory tự free | reinterpret không tự cấp/free | Phải dùng đúng cleanup action nếu Java sở hữu C allocation |
| Reinterpret size tùy ý | FFM không biết allocation thật | Lấy byteSize từ C contract, validate |
| Dùng libc free cho pointer cần custom_destroy | Sai allocator/contract | Dùng matching deallocator |
| Đóng library lookup trước resource owner | Cleanup gọi vào code native đã unload | Library arena sống lâu hơn owner arena |
| Đóng arena khi worker chưa xong | C vẫn dùng dangling address | Drain/join rồi close |
| Dùng Arena.ofAuto để đóng resource theo deadline | GC không có lịch cố định | Dùng explicit close và owner loop |
| Dùng Arena.global cho request resource | Không release đúng thời điểm | Confined/shared arena theo lifetime |
| Close cùng Arena hai lần | Arena.close không idempotent | Một owner đóng qua try-with-resources một lần |
| Gọi free từ mỗi asSlice | Slice không sở hữu allocation riêng | Cleanup duy nhất tại base owner |
| Giữ raw pointer global sau free | Raw scope không phản ánh native free | Che raw handle và chỉ dùng managed view |
| Nghĩ AtomicBoolean sửa mọi lỗi double-free | Không kiểm soát native side/other wrappers | Ownership architecture, state, native contract |
| Thứ tự cleanup trong cùng arena phụ thuộc ngầm | Parent có thể bị destroy trước child | Nested scopes hoặc explicit teardown ordering |
| Cleanup lambda capture auto arena | Có thể làm arena không unreachable | Tránh reference cycle qua cleanup |
| Cleanup failure rồi retry mù quáng | Có thể đã free thật, retry dẫn tới double-free | Contract lỗi rõ, không retry vô điều kiện |
| Chỉ so sánh địa chỉ để nhận diện resource | Address có thể được tái sử dụng | Resource IDs/generation và owner state |
| Không kiểm tra create() trả NULL | Reinterpret NULL rồi dereference | Check pointer trước khi quản lý/use |

## 19. Checklist review trước khi triển khai

- [ ] Xác định chính xác resource **do Java Arena cấp, native cấp rồi chuyển quyền, borrowed hay reference-counted**.
- [ ] Có **đúng một owner** cho mỗi allocation/reference ownership share.
- [ ] Deallocator đúng thư viện, đúng kiểu, đúng ABI và đúng allocator.
- [ ] Không gắn cleanup cho borrowed pointer hoặc gọi free vào slice.
- [ ] Nếu dùng **reinterpret(size, arena, cleanup)**, biết rõ size, lifetime, quyền sở hữu và rủi ro restricted API.
- [ ] Có một nhánh xử lý **NULL** và thất bại trước khi ownership được đăng ký.
- [ ] Đã chọn **Arena scope** theo consumer cuối cùng, không theo phạm vi cú pháp Java một cách máy móc.
- [ ] Library lookup/MethodHandle destroy còn hợp lệ **khi cleanup chạy**.
- [ ] Không đồng thời dùng manual free và custom arena cleanup cho cùng address.
- [ ] try-with-resources không có thêm arena.close thủ công làm close lặp.
- [ ] Cleanup không lưu **global-scoped cleanup pointer** để dùng sau native free.
- [ ] Không cho native worker/callback dùng pointer sau khi arena đóng; có unregister/drain/join.
- [ ] Confined/shared arena và deallocator thread-affinity phù hợp với thiết kế thực.
- [ ] Parent/child resources có thứ tự cleanup được quản rõ ràng.
- [ ] Nếu ownership transfer sang C, Java không tiếp tục giải phóng cùng resource.
- [ ] Không retry một deallocator mà không biết trạng thái native sau thất bại.
- [ ] Có test cho alias, double close, setup error, native error, GC/auto arena và concurrent shutdown.
- [ ] Có ASan/heap diagnostics hoặc integration harness phù hợp để phát hiện native heap corruption.

## 20. Câu hỏi tự kiểm tra

**1. Gọi MemorySegment.reinterpret(size, arena, null) có tự free pointer C khi arena.close không?**

**Trả lời:** Không. reinterpret chỉ tạo alias với size/scope mới. Nếu pointer do C cấp và Java sở hữu, phải có cleanup action gọi đúng deallocator hoặc một cơ chế manual release khác.

**2. Một MemorySegment từ Arena.allocate đã được arena quản lý. Có nên thêm callback gọi libc free?**

**Trả lời:** Không. Arena đã sở hữu backing region, và free thủ công có thể dẫn tới double-free hoặc sai allocator.

**3. Hai asSlice của một owned segment có cần hai cleanup callbacks không?**

**Trả lời:** Không. Chúng là views của cùng allocation; chỉ owner đăng ký cleanup. Mỗi slice không có allocation độc lập.

**4. Một C API trả const char* borrowed. Java có được gắn free khi scope kết thúc?**

**Trả lời:** Không, trừ khi contract thực sự chuyển quyền (chỉ từ const không suy được). Borrowed pointer do owner C quản.

**5. Vì sao một libraryArena nên sống lâu hơn resourceArena nếu cleanup gọi MethodHandle destroy?**

**Trả lời:** Vì library lookup có thể khiến library bị unload khi arena của nó đóng. Nếu unload trước, cleanup gọi function pointer không còn hợp lệ.

**6. Arena.close bị gọi hai lần có chắc là double-free native không?**

**Trả lời:** Không. JDK 22 Arena.close không idempotent; lần hai ném IllegalStateException. Double-free thực xảy ra khi một native allocation bị gọi deallocator quá số lần ownership cho phép.

**7. C function giữ pointer sau return, còn Java gắn cleanup vào request Arena đóng ngay sau return. Sai ở đâu?**

**Trả lời:** Scope Java ngắn hơn lifetime của C consumer, có thể gây use-after-free. Phải giữ resource sống tới khi native work hoàn tất rồi mới close.

**8. Nếu một native object dùng retain/release, hai Java wrappers có luôn được release riêng không?**

**Trả lời:** Chỉ khi mỗi wrapper thực sự sở hữu một reference share đã được retain/chuyển quyền theo contract. Hai aliases của cùng một ref không được tự release độc lập.

**9. Vì sao không dùng Arena.ofAuto cho một resource phải đóng trên UI thread đúng lúc?**

**Trả lời:** Thời điểm và thread cleanup qua GC không do ứng dụng điều khiển. Cần owner thread và explicit close/dispatch.

**10. Sau khi ownerArena.close, managed.get bị IllegalStateException; liệu rawPointer có còn an toàn?**

**Trả lời:** Không. Raw pointer có thể vẫn có global scope nhưng đã trỏ vào vùng C free. FFM không tự vô hiệu hóa mọi alias đã tách ngoài scope owner.

**11. Nếu custom cleanup ném exception, có nên gọi native free lại ngay?**

**Trả lời:** Không nếu chưa biết native deallocator đã giải phóng memory hay chưa. Phải tuân thủ contract lỗi/retry để tránh gọi free hai lần.

**12. Khi nào nested arenas có giá trị hơn một arena chung?**

**Trả lời:** Khi resources có dependency lifetime như statement thuộc database hoặc native library phải sống dài hơn resource. Nested scopes tạo thứ tự close rõ ràng hơn.

## Tài liệu tham khảo chính thức

- [JEP 454 — Foreign Function & Memory API được hoàn thiện trong JDK 22](https://openjdk.org/jeps/454).
- [Java SE 22 — Arena: scope, confined/shared/auto/global, close không idempotent và cleanup errors](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- [Java SE 22 — MemorySegment: reinterpret với Arena và cleanup Consumer](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [Oracle Java 22 Guide — Foreign Functions That Return Pointers: malloc/free qua reinterpret cleanup](https://docs.oracle.com/en/java/javase/22/core/foreign-functions-that-return-pointers.html).
- [Java SE 22 — SymbolLookup: lifetime của thư viện gắn với Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- [Java SE 22 — Linker và FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).

**Kết luận:** Để tránh double-free trong FFM, phải nắm **quyền sở hữu của native allocation**, chọn **scope kết thúc đúng lúc consumer cuối hoàn tất**, gắn **đúng một cleanup action** hoặc một manual owner (không cả hai), gọi **đúng matching deallocator**, và giữ **thư viện/native code sống lâu hơn cleanup**. MemorySegment, asSlice và reinterpret chỉ quản view/scope; chúng **không thể tự chứng minh quyền sở hữu C pointer**. Thiết kế ownership rõ ràng là biện pháp phòng ngừa double-free, leak và use-after-free quan trọng nhất.
