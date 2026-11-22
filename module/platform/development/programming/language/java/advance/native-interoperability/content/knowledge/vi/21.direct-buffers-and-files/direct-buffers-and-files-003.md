# Bộ đệm và tệp — Quy định bên sở hữu khi Java giữ bộ đệm trỏ vào bộ nhớ do C cấp phát

## 1. Vấn đề: Java giữ một buffer không đồng nghĩa Java sở hữu memory

Khi Java và một thư viện C trao đổi dữ liệu qua JNI hoặc Foreign Function & Memory (FFM) API, Java có thể nhận một `ByteBuffer` / `MemorySegment` biểu diễn **địa chỉ của một vùng nhớ ngoài Java heap**. Vùng nhớ đó có thể đã được C cấp phát bằng `malloc`, allocator của thư viện, hoặc một API hệ điều hành. Đối tượng Java lúc này chỉ là **view/handle** tới vùng nhớ.

**Câu hỏi cần trả lời trước khi dùng buffer:** ai đã cấp phát, ai hiện đang sở hữu, ai được quyền đọc/ghi, ai phải giải phóng, dùng hàm giải phóng nào, và những view Java còn lại có thể tồn tại tới lúc nào?

Các khái niệm:

- **Allocator:** nơi tạo block, ví dụ `malloc`, `HeapAlloc`, `mmap`, `VirtualAlloc`, hoặc allocator riêng của thư viện.
- **Owner:** thành phần có trách nhiệm đảm bảo block được giải phóng **đúng một lần**, sau khi không còn ai sử dụng.
- **Borrower (bên mượn):** có quyền sử dụng tạm thời nhưng **không được free**; không được giữ view lâu hơn owner/lifetime.
- **Transfer of ownership:** thư viện C tạo block rồi **chuyển trách nhiệm giải phóng** cho phía Java thông qua một giao thức rõ ràng.
- **Aliasing:** hai hoặc nhiều `ByteBuffer`, `slice()`, `duplicate()`, `MemorySegment` cùng trỏ tới **cùng block native**. Giải phóng block làm **mọi alias** thành nguy hiểm nếu còn truy cập.
- **Lifetime:** khoảng từ lúc cấp phát thành công tới lúc giải phóng thành công. Một Java object còn reachable **không chứng minh** native block còn sống.
- **View ≠ allocation:** tạo một `ByteBuffer` trực tiếp từ địa chỉ không sao chép bytes, và không đồng nghĩa tự tạo một cơ chế free.

Sơ đồ ownership:

```text
             Native C library                 Java
       ┌─────────────────────┐      ┌─────────────────────┐
malloc │ block 16 bytes       │◄─────│ ByteBuffer view     │
  ───► │ ptr = 0x...          │      │ MemorySegment view  │
       └─────────────────────┘      └─────────────────────┘
                 ▲                            │
                 │                     chỉ giữ địa chỉ,
                 │                     không tự sở hữu
                 │                            │
                 └── free()/release(ptr) ◄────┘
                      phải có MỘT owner
```

Một sai lầm thường gặp: "Java giữ reference đến `ByteBuffer`, nên GC sẽ không làm mất dữ liệu". Sai: **GC quản lý Java object; native allocator có vòng đời riêng**. Nếu C đã `free(ptr)` trong khi Java vẫn dùng view, đó là **use-after-free**; có thể là dữ liệu rác, memory corruption hoặc JVM crash chứ không bắt buộc là Java exception.

Bài học thuộc **Bộ đệm và tệp**: ngoài việc đọc/ghi dữ liệu bằng `java.nio.ByteBuffer`, ta còn phải xử lý ownership khi native buffer được đưa vào `FileChannel` hoặc các API I/O. Ví dụ chính dùng **Java 22+ FFM**, minh họa C `malloc/free` trên Windows và đã kiểm thử với OpenJDK 24; phần JNI cũng được giải thích để tránh nhầm vòng đời.

## 2. Đặt hợp đồng sở hữu trước khi trả buffer cho Java

Ba mô hình phổ biến:

| Mô hình | Ai cấp phát? | Java được làm gì? | Ai free? |
| --- | --- | --- | --- |
| **Borrowed native buffer** | C/thư viện | Đọc/ghi trong phạm vi mà thư viện cho phép; không giữ sau khi owner hủy | **C/thư viện** |
| **Transferred native buffer** | C/thư viện | Nhận quyền sở hữu sau khi API báo thành công; có trách nhiệm cleanup | **Java gọi release API của thư viện**, trực tiếp hoặc qua scope có cleanup |
| **Caller-owned output buffer** | Java (`Arena.allocate` hoặc buffer khác) | Java cấp memory, C chỉ điền nội dung và trả số bytes đã ghi | **Java/Arena** đóng hoặc giải phóng theo allocator gốc |

Đôi khi có **shared ownership** qua reference counting: C và Java đều giữ một reference đến một native object, mỗi bên gọi retain/release theo hợp đồng. Đây không phải hệ quả mặc định của `ByteBuffer` mà là giao thức do thư viện thiết kế.

### 2.1. Borrowed: thư viện vẫn là owner

Ví dụ C giả định:

```c
// Trả pointer tới buffer nội bộ, hợp lệ cho tới khi close_device(handle).
const unsigned char *device_peek(device_handle *handle, size_t *length);
```

**Đây là declaration minh họa**, không phải API thư viện có sẵn. Java chỉ được đọc trong khoảng `device_peek` và `close_device` hoặc tới khi hợp đồng nói pointer hết hạn (có thể là ngay lần gọi tiếp theo). Java **không free** pointer. Nếu cần dữ liệu sau khi thiết bị đóng, **copy** trước khi đóng.

### 2.2. Transfer: bên Java trở thành owner sau thành công

Ví dụ C giả định:

```c
// 0 = success; thư viện malloc/allocate và chuyển ownership.
int image_decode(const void *encoded, size_t encoded_size,
                 unsigned char **out_bytes, size_t *out_size);
void image_release(unsigned char *ptr);
```

Sau `image_decode` trả `0`, Java nhận pointer, size và **nghĩa vụ gọi `image_release(ptr)` chính xác một lần**. Nếu C đã dùng allocator riêng, Java không được thay `image_release` bằng `free` của một CRT khác hoặc API hệ điều hành bất kỳ. Nếu giải mã thất bại, hành vi của `*out_bytes` và ownership vẫn phải đọc **tài liệu** của thư viện; không suy diễn mọi API đều đặt pointer thành `NULL`.

### 2.3. Caller-owned: Java cấp, C chỉ ghi

```c
// Bên gọi cấp buf; C chỉ điền tối đa capacity byte.
int read_into_buffer(file_handle *h, unsigned char *buf,
                     size_t capacity, size_t *bytes_written);
```

Java sở hữu buffer. C không được gọi `free(buf)`. Nếu C lưu pointer lại để dùng bất đồng bộ, Java phải kéo dài lifetime cho tới khi C báo đã xong, **không** đóng Arena ngay sau lời gọi "submit". Điều này đặc biệt quan trọng với tệp, sockets, I/O completion callbacks và native worker threads.

## 3. Bảy quy tắc ownership không được bỏ sót

1. **Ai cấp phát bằng allocator nào thì phải có đường giải phóng tương thích.** `malloc/free` là cặp; `new/delete` là cặp; `HeapAlloc/HeapFree` là cặp (đúng heap handle); object/handle riêng cần `library_release`; `mmap` cần `munmap`/API tương ứng. Không trộn allocator.
2. **Chỉ một owner chịu trách nhiệm free ở thời điểm kết thúc.** Nếu dùng reference counting, "một lần" nghĩa là mỗi owner release một reference theo hợp đồng, chứ không gọi free trên block nhiều lần.
3. **Không free trước khi tất cả view/người dùng ngừng truy cập.** `slice()`, `duplicate()` và các alias ở Java có thể giữ cùng native pointer. Native code cũng có thể vẫn đang đọc/ghi block trong một callback.
4. **Không đọc quá kích thước hợp lệ.** Một pointer C chỉ là địa chỉ; Java phải biết số bytes có thể đọc, số bytes đã được C khởi tạo, và bounds chính xác.
5. **Không giả định GC giải phóng C `malloc`.** Nếu ứng dụng có trách nhiệm release, dùng `AutoCloseable`/`try-with-resources`, explicit native release hoặc cleanup action gắn với Arena. `Cleaner` chỉ là phương án dự phòng trong một số thiết kế, không bảo đảm release đúng thời điểm.
6. **Không mượn quá lifetime.** Borrowed pointer có thể bị vô hiệu ngay khi C owner đóng hoặc tái cấp phát; giữ Java reference đến view không kéo dài lifetime tự động.
7. **Phân biệt release với invalidation.** Sau `free`, địa chỉ cũ có thể vẫn là một số khác `0` nhưng việc dereference là không hợp lệ. Một FFM view gắn với closed scope có thể bị từ chối bằng `IllegalStateException`; raw JNI `ByteBuffer` không nhất thiết có cơ chế tương tự.

### Ma trận review của một API C

Trước khi thiết kế Java wrapper, hãy ghi rõ:

| Câu hỏi | Ví dụ câu trả lời đúng |
| --- | --- |
| Con trỏ nhận ở đâu? | Return value `unsigned char*` hoặc out-param `unsigned char**` |
| Size lấy từ đâu? | `size_t *length`; kiểm tra hợp đồng error/partial result |
| Đã khởi tạo bao nhiêu byte? | `length` bytes trên nhánh `status == 0` |
| Ownership khi thành công? | Transferred to caller |
| Ownership khi lỗi? | Không có block được chuyển; check contract |
| Deallocator chính xác? | `image_release(ptr)` của cùng thư viện |
| Có được mượn từ thread khác? | Chỉ khi thư viện và Java wrapper hỗ trợ |
| Có được dùng sau khi đóng? | Không; view/alias phải bị loại bỏ |
| Ai đóng và lúc nào? | Một owner Java, sau khi tất cả đồng bộ/async users hoàn tất |
| Nếu caller quên close? | Leak C memory; có thể có Cleaner fallback, không dựa vào GC latency |

## 4. JNI: `NewDirectByteBuffer` là view chứ không phải hợp đồng free

Với JNI, native code có thể đưa một C pointer vào Java dưới dạng **direct `java.nio.ByteBuffer`**:

```c
// Snippet JNI, không phải native library độc lập.
void *ptr = malloc(capacity); // C cấp phát.
if (ptr == NULL) {
    // Báo allocation failure qua chính sách JNI của ứng dụng.
    return NULL;
}

jobject buffer = (*env)->NewDirectByteBuffer(env, ptr, (jlong)capacity);
if (buffer == NULL) {
    free(ptr); // Không bàn giao được view: rollback allocation.
    return NULL;
}
// TODO trong sản phẩm thật: tạo owner handle/close contract.
// Chỉ tạo ByteBuffer KHÔNG đăng ký free(ptr).
return buffer;
```

Đoạn này **chỉ giải thích một bước**, không phải lời khuyên copy nguyên thành chương trình, vì nó **chưa có** giao thức release khi Java sử dụng xong. Trong code thật phải cung cấp một **owner object/opaque native handle** và phương thức `close()` có kiểm soát trước khi trả buffer cho ứng dụng. Tránh expose một API `nativeFree(ByteBuffer anyBuffer)` tự `free(GetDirectBufferAddress(anyBuffer))`: bất kỳ direct buffer tùy ý nào cũng có thể bị free nhầm hoặc double-free.

**JNI `NewDirectByteBuffer` không chuyển quyền sở hữu bằng phép màu.** Nó tạo một view trên `address` với `capacity`, **không** có tham số "deallocator"; Java `ByteBuffer` không tự biết cần gọi `library_release` hay `free`. `GetDirectBufferAddress` lấy địa chỉ của direct buffer, **không chứng nhận** địa chỉ ấy có thể giải phóng bằng allocator nào.

Ngoài ra:

- Java `ByteBuffer` có `position`, `limit` và `capacity`; **capacity không phải ownership**. `slice()`/`duplicate()` tạo aliases trỏ tới cùng block native.
- Buffer của `NewDirectByteBuffer` có **byte order mặc định `BIG_ENDIAN`** theo JNI spec; nếu C struct/int được viết ở thứ tự byte của máy, Java phải gọi `buffer.order(ByteOrder.nativeOrder())` trước khi đọc multi-byte values. Đừng assume endianness.
- JNI `NewDirectByteBuffer` nhận pointer/size hợp lệ theo JNI specification; không xây view trên `NULL` hoặc size ngoài phạm vi NIO buffer. Native code phải bảo đảm memory **thật sự truy cập được**.
- Sau C `free(ptr)`, Java có thể vẫn giữ `ByteBuffer` và `isDirect() == true`, nhưng điều đó **không có nghĩa** block còn sống. Truy cập có thể gây crash/ghi vào vùng đã được dùng lại.
- `ByteBuffer.allocateDirect(size)` là trường hợp **JVM tạo và quản lý native allocation**, **khác** trường hợp C `malloc` rồi JNI wrap pointer; không quy mọi direct buffer về một owner duy nhất.
- Nếu `JNI NewDirectByteBuffer` được dùng với memory do C sở hữu lâu dài, Java chỉ được mượn trong phạm vi C bảo đảm. Nếu Java được giao ownership, phải xây Java wrapper `AutoCloseable` và native release function đúng allocator.

### Thiết kế JNI wrapper có trách nhiệm sở hữu rõ

Một hợp đồng API khả thi:

```java
// API design sketch, không phải chương trình độc lập.
interface BorrowedNativeBuffer {
    // Chỉ cho phép đọc/ghi trong một thao tác đồng bộ được kiểm soát.
    <T> T withBuffer(java.util.function.Function<ByteBuffer, T> action);
}

interface OwnedNativeBuffer extends AutoCloseable {
    // Cho phép callback sử dụng view khi object còn open.
    <T> T withBuffer(java.util.function.Function<ByteBuffer, T> action);
    @Override void close(); // Gọi native library_release đúng một lần.
}
```

**Đây là interfaces mô tả ý tưởng**, không tự tạo bảo đảm an toàn: nếu callback giữ lại `ByteBuffer` trong một field, vòng đời vẫn có thể bị vi phạm. Implementation cần đồng bộ để `close()` không chạy khi `withBuffer` đang dùng memory, có state `OPEN/CLOSING/CLOSED`, và quy định rõ mọi alias chỉ có hiệu lực trong callback. Các object trỏ tới cùng C allocation phải chia sẻ **một owner/retained handle**, không độc lập `close`. Nếu không thể kiểm soát aliases, **copy bytes sang Java heap** là chiến lược an toàn và dễ kiểm chứng hơn.

## 5. FFM: gắn quyền sở hữu C allocation vào Arena

Với FFM API đã chính thức từ **JDK 22**, một C function `malloc(size_t)` trả native pointer dưới dạng `MemorySegment` (thường là **zero-length address segment**). Java có thể tạo view có kích thước cụ thể bằng `reinterpret(size)`. Nhưng **`reinterpret` không cấp phát và không tự giải phóng memory**.

Nếu Java nhận ownership, FFM hỗ trợ:

```java
MemorySegment ownedView = pointer.reinterpret(
    size, ownerArena, cleanup);
```

`cleanup` là một `Consumer<MemorySegment>` được chạy khi Arena scope bị invalidated. Nó phải gọi **đúng deallocator** của block, không dùng free chung cho block của allocator khác. View được trả về gắn với scope/lifetime của `ownerArena`. Nếu Arena đã đóng, truy cập view/`asByteBuffer()` bị chặn ở FFM level.

**Hai điều cực kỳ quan trọng:**

1. **Reinterpret không xác minh kích thước allocation thật.** Nếu truyền `size` lớn hơn block mà C cấp, FFM không biết và truy cập vẫn có thể gây memory corruption. Kiểm tra size từ C contract, giới hạn ứng dụng, alignment và ABI trước khi dùng.
2. **FFM không tự chặn mọi alias của pointer.** Native code hoặc một `MemorySegment.ofAddress(address)` khác với global scope vẫn có thể truy cập địa chỉ sau `free` — cực kỳ nguy hiểm. View có scope giúp bảo vệ **các accesses thông qua view đó**, không tạo quyền sở hữu vật lý độc quyền trên toàn process.

Trong thực tế, chỉ nên tạo **một cleanup owner** cho một block C; không vừa gọi `free` thủ công vừa đăng ký cleanup action cho cùng block. Nếu `reinterpret` thất bại **trước khi đăng ký cleanup**, Java vẫn đang giữ ownership và phải giải phóng block bằng nhánh rollback.

### Scope và `ByteBuffer` của FFM

`MemorySegment.asByteBuffer()` tạo **direct ByteBuffer** cho native segment. Theo tài liệu, ByteBuffer view này **chia sẻ liveness và thread confinement** với segment: sau khi `ownerArena.close()`, việc truy cập buffer ném `IllegalStateException` (với API Java phù hợp). Byte order ban đầu là `BIG_ENDIAN`, có thể đổi bằng `order(ByteOrder.nativeOrder())`.

Điều này **khác một raw JNI `NewDirectByteBuffer`**: FFM có scope gắn với `MemorySegment` để kiểm tra truy cập, còn một raw JNI view không tự biết khi nào native owner đã free block.

## 6. Ví dụ Java chạy thật: C `malloc/free` + FFM `MemorySegment` + `ByteBuffer`

Ví dụ đầy đủ sau **không cần tự biên dịch C**. Trên **Windows 64-bit**, Java dùng FFM để gọi trực tiếp hai hàm C từ **cùng một CRT DLL `msvcrt.dll`**:

- `malloc(16)` tạo một native block 16 byte và trả pointer. **Java nhận ownership của block sau lời gọi thành công** theo chính sách demo.
- `free(pointer)` từ **chính cùng DLL** được đăng ký làm cleanup action của một confined Arena.
- Java `reinterpret` pointer với size 16 và scope của Arena, sau đó tạo `ByteBuffer` view để ghi/đọc.
- Java copy 16 byte sang `byte[]` trước khi đóng arena. Byte array sống độc lập sau khi native block được giải phóng.
- Khi Arena đóng, action gọi `free` **một lần**. Lần truy cập tiếp theo qua scoped ByteBuffer đã đóng ném `IllegalStateException`; bản sao Java vẫn đọc được.

**Giới hạn ABI:** lệnh `malloc(size_t)` được mô tả với `ValueLayout.JAVA_LONG` vì `size_t` rộng 64 bit trên Windows x64. `free(void*)` nhận pointer `ADDRESS` và không trả về gì. Không dùng nguyên descriptor này trên ABI 32-bit. Với Linux/macOS, phải thay cách tìm C library và xác minh ABI/names.

### 6.1. File đầy đủ `NativeMallocOwnershipDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.concurrent.atomic.AtomicInteger;

public final class NativeMallocOwnershipDemo {
    private static final long LENGTH = 16;

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // Keep the library loaded while ANY handle/cleanup may call it.
        try (Arena libraryLifetime = Arena.ofConfined()) {
            SymbolLookup crt =
                SymbolLookup.libraryLookup("msvcrt.dll", libraryLifetime);

            MethodHandle malloc = linker.downcallHandle(
                crt.findOrThrow("malloc"),
                FunctionDescriptor.of(ValueLayout.ADDRESS,
                    ValueLayout.JAVA_LONG));

            MethodHandle free = linker.downcallHandle(
                crt.findOrThrow("free"),
                FunctionDescriptor.ofVoid(ValueLayout.ADDRESS));

            AtomicInteger releaseCount = new AtomicInteger();
            ByteBuffer expiredBuffer;
            byte[] copy;

            try (Arena owner = Arena.ofConfined()) {
                MemorySegment pointer =
                    (MemorySegment) malloc.invokeExact(LENGTH);

                if (pointer.address() == 0) {
                    throw new OutOfMemoryError("malloc failed");
                }

                boolean cleanupRegistered = false;
                try {
                    // The same C allocation gets ONE cleanup owner.
                    MemorySegment view = pointer.reinterpret(
                        LENGTH, owner, p -> {
                            try {
                                free.invokeExact(p);
                                releaseCount.incrementAndGet();
                            } catch (Throwable t) {
                                throw new IllegalStateException(
                                    "free failed", t);
                            }
                        });
                    cleanupRegistered = true;

                    // View: no new native allocation or byte copy.
                    ByteBuffer bytes = view.asByteBuffer()
                        .order(ByteOrder.nativeOrder());

                    bytes.putInt(0, 123456);
                    bytes.putInt(4, -9);
                    System.out.println("direct: " + bytes.isDirect());
                    System.out.println("first: " + bytes.getInt(0));
                    System.out.println("second: " + bytes.getInt(4));

                    // Copy data BEFORE native release.
                    copy = new byte[bytes.capacity()];
                    bytes.duplicate().clear().get(copy);
                    expiredBuffer = bytes;
                } finally {
                    // Only if reinterpret/registration failed:
                    // release ownership manually as rollback.
                    if (!cleanupRegistered) {
                        free.invokeExact(pointer);
                    }
                }
            } // owner.close() calls the registered free exactly once.

            System.out.println("release calls: "
                + releaseCount.get());

            // Java heap copy is independent from native memory.
            System.out.println("copy after close: "
                + ByteBuffer.wrap(copy)
                    .order(ByteOrder.nativeOrder()).getInt(0));

            try {
                expiredBuffer.getInt(0);
                System.out.println("after close: unexpected");
            } catch (IllegalStateException expected) {
                System.out.println(
                    "after close: IllegalStateException");
            }
        }
    }
}
```

**Vì sao `finally` có nhánh fallback?** Sau `malloc` thành công, Java đã nhận trách nhiệm release. Nếu `reinterpret` thất bại trước khi gắn cleanup action, Arena không tự biết về block mới malloc. Nhánh `finally` chỉ gọi `free` khi `cleanupRegistered == false`. Khi đăng ký thành công, **chỉ Arena.close()** gọi `free`; không còn explicit free trong nhánh đó. Điều này tránh cả **memory leak** lẫn **double-free** cho những đường chạy bình thường.

**Vì sao có hai Arena?** `libraryLifetime` giữ thư viện CRT được lookup còn loaded khi cleanup gọi `free`. `owner` quản lý riêng lifetime của block malloc và view. Đóng owner **trước** libraryLifetime, nên cleanup action vẫn có thể gọi được `free` từ DLL.

**Vì sao không return `ByteBuffer`?** Demo giữ view đến sau Arena close chỉ để chứng minh một **truy cập bị từ chối có kiểm soát**. Production code không được trả alias native ra khỏi owner scope như một buffer dùng lâu dài. `ByteBuffer` chỉ được phép dùng khi owner vẫn mở và không có actor nào free block bên ngoài.

### 6.2. Biên dịch và chạy trên Windows x64 / JDK 22+

Mở PowerShell hoặc terminal có `java` và `javac` của **JDK 22+**:

```powershell
javac -encoding UTF-8 NativeMallocOwnershipDemo.java
java --enable-native-access=ALL-UNNAMED NativeMallocOwnershipDemo
```

`--enable-native-access=ALL-UNNAMED` cho phép các restricted FFM operations từ code trên classpath (tạo downcall handle và `reinterpret`), đồng thời tránh các cảnh báo/denials về native access theo JDK đang dùng. FFM đã final từ JDK 22 nên không cần `--enable-preview` **chỉ để dùng FFM**.

**Stdout chính xác đã kiểm chứng trên OpenJDK 24.0.2 / Windows x64:**

```text
direct: true
first: 123456
second: -9
release calls: 1
copy after close: 123456
after close: IllegalStateException
```

Vì dùng `ByteOrder.nativeOrder()` ở cả lượt ghi và lượt đọc từ heap copy, ví dụ tránh phụ thuộc vào thứ tự byte mặc định của direct `ByteBuffer`. `releaseCount` chỉ là số lần **Java cleanup callback gọi free** trong demo; nó không phải bộ đếm của allocator ở mức hệ điều hành. Không lấy cách đếm này làm thay thế cho memory sanitizer/profiler trong ứng dụng lớn.

### 6.3. Từng bước ownership trong code

| Đối tượng | Ai tạo? | Ai sở hữu native allocation? | Kết thúc ở đâu? |
| --- | --- | --- | --- |
| `pointer` từ `malloc` | C CRT `malloc` | **Java nhận ownership sau success**, theo chính sách demo | Cleanup action gọi `free(pointer)` |
| `view` từ `reinterpret` | FFM tạo Java view | Không cấp block mới; dùng cùng C allocation | Mất hiệu lực khi `owner.close()` |
| `bytes` từ `asByteBuffer` | FFM tạo Java buffer view | Không sở hữu block riêng | Mất hiệu lực theo scope của `view` |
| `bytes.duplicate()` | Java tạo alias | Cùng block, không sở hữu allocation mới | Mất hiệu lực cùng scope |
| `copy` kiểu `byte[]` | Java heap | Java GC quản lý bytes **đã sao chép** | Độc lập với `owner.close()` |
| `owner` | Java `Arena.ofConfined()` | **Cleanup owner** theo registration của `reinterpret` | `try-with-resources` đóng, gọi cleanup |
| `libraryLifetime` | Java `Arena.ofConfined()` | Sở hữu handle/lifetime của library lookup | Đóng sau `owner`, tránh unload quá sớm |

**Quan trọng về pointer gốc:** kết quả pointer thô từ `malloc` chỉ là **địa chỉ**. Khi Java gắn view `reinterpret(LENGTH, owner, cleanup)`, scope bảo vệ **view đó**, không thay đổi lifetime của mọi con trỏ/alias đã được C hoặc Java tạo độc lập. Sau free, không dùng lại `pointer` hoặc một view global từ cùng địa chỉ.

## 7. Nếu không dùng `reinterpret(..., Arena, cleanup)` thì sao?

Bạn có thể quản lý `malloc/free` thủ công:

```java
// Snippet minh họa, không phải class độc lập.
// malloc/free là MethodHandle đúng ABI; size là bytes hợp lệ.
MemorySegment raw = (MemorySegment) malloc.invokeExact(size);
if (raw.address() == 0) throw new OutOfMemoryError("malloc failed");
try {
    MemorySegment view = raw.reinterpret(size);
    // Chỉ dùng view trong try và copy dữ liệu khi cần.
} finally {
    free.invokeExact(raw);
}
// Không được dùng view hay bất kỳ pointer alias nào sau free.
```

Mẫu này giải phóng rõ ràng, nhưng `raw.reinterpret(size)` tạo một view **không được gắn lifetime của một closeable owner Arena**. Nếu lộ view ra ngoài, Java có thể không chặn được truy cập sau `free`. Do vậy mẫu **`reinterpret(size, ownerArena, cleanup)`** cung cấp một lớp kiểm soát lifetime tốt hơn cho **những view FFM lấy từ nó**.

**Không nên** dùng `Arena.ofAuto()` làm cách giải phóng deterministically: automatic arena được runtime/GC quản lý, không đóng tường minh được. Một C allocation chuyển ownership thường cần giải phóng ở điểm rõ ràng; **`Arena.ofConfined()/ofShared()` với cleanup + `try-with-resources`** phù hợp hơn.

### Có nên dùng `Cleaner`/finalizer?

`Cleaner` có thể giúp như fallback khi developer quên close, nhưng:

- GC/Cleaner không bảo đảm **thời điểm** chạy; tài nguyên hệ thống có thể cạn trước khi heap pressure kích hoạt cleanup.
- Cleanup state cần tránh giữ vòng reference ngăn GC và tránh gọi destructor native sau khi thư viện đã unload.
- Java `finalize()` đã bị deprecate và không nên dùng cho ownership native.
- Nếu `close()` đã gọi release, Cleaner fallback không được release lần hai. Cần state/atomic guard được thiết kế kỹ.
- Tuyệt đối không coi `Cleaner` là cách làm an toàn cho native **borrowed pointer** khi owner có thể hủy memory trước.

Trong API dễ kiểm soát nhất, bắt caller dùng `try-with-resources` và xem Cleaner chỉ là giải pháp bổ sung. Khi gặp native resource leak, kiểm tra **native memory metrics** chứ không chỉ Java heap usage.

## 8. Kết nối với file I/O và NIO buffers

Một ứng dụng có thể dùng native-owned buffer để truyền bytes cho Java NIO:

```java
// Snippet minh họa, chưa phải chương trình độc lập.
// buffer là ByteBuffer view đang hợp lệ trong owner Arena.
// channel là FileChannel đã mở đồng bộ để ghi.
ByteBuffer toWrite = buffer.duplicate();
toWrite.position(0);
toWrite.limit(numberOfValidBytes);

while (toWrite.hasRemaining()) {
    channel.write(toWrite);
}
// Chỉ sau khi thao tác đồng bộ hoàn tất mới đóng owner Arena.
```

**Những điều cần xác định trước `FileChannel.write`:**

1. `numberOfValidBytes` là số byte **C đã ghi thành công**, không tự động là `buffer.capacity()`; đọc bytes chưa khởi tạo có thể lộ dữ liệu cũ.
2. `position`/`limit` của ByteBuffer giới hạn **lượt I/O**, nhưng **không quyết định native allocation lifetime**.
3. `FileChannel.write(ByteBuffer)` có thể ghi **ít hơn số byte yêu cầu**; dùng vòng lặp hoặc xử lý partial-write theo hợp đồng I/O.
4. `duplicate()` và `slice()` **không copy** native bytes; chúng tạo view mới cùng memory. Không đóng/free sau khi tạo duplicate nếu duplicate vẫn đang được dùng.
5. Khi dùng **asynchronous native I/O** hoặc library giữ pointer sau khi submit, phải đợi completion thực sự rồi mới close; việc submit trở về **không** có nghĩa buffer đã được dùng xong.
6. Nếu Java cần giữ dữ liệu tệp lâu hơn owner Arena, **copy vào `byte[]` / owned Java buffer** trước khi đóng, rồi xử lý file I/O từ bản sao.
7. Nếu C cũng ghi vào buffer song song khi Java đang đọc/ghi tệp, cần synchronization và memory visibility. `isDirect()` không bảo đảm thread safety.

### Trường hợp memory-mapped file hoặc OS handle

`mmap/munmap`, `MapViewOfFile/UnmapViewOfFile` và file handles dùng **deallocator riêng**; **không gọi `free` lên mapped address**. Nếu C cung cấp một mapped region, hợp đồng owner phải chỉ rõ ai gọi `munmap`/`UnmapViewOfFile` và ai đóng backing file handle. `FileChannel.map`/FFM mapped segments còn có lifecycle khác với C `malloc`. Mỗi loại resource cần cặp acquire/release đúng.

### Khi nên copy thay vì zero-copy

Zero-copy view có lợi khi kích thước dữ liệu lớn và xử lý đồng bộ, nhanh, có owner/lifetime rõ. Copy về Java heap thường nên ưu tiên khi:

- Kết quả cần cache hoặc trả cho API không kiểm soát lifecycle;
- Native owner sẽ đóng ngay, mà Java vẫn cần sử dụng;
- Có nhiều threads, async tasks, event queues khó đồng bộ;
- Bộ dữ liệu nhỏ đến vừa, chi phí copy không đáng kể so với rủi ro use-after-free;
- Không thể bảo đảm tất cả aliases được thu hồi trước khi native free.

Quy tắc ra quyết định: **zero-copy chỉ an toàn khi ownership, lifetime, bounds và concurrency đều xác định rõ**. Nếu không đạt, copy.

## 9. Thiết kế Java `AutoCloseable` cho một C-owned allocation

Một lớp wrapper tốt nên có các đặc điểm:

- **Một owner instance cho một native allocation** hoặc một shared ownership protocol có ref-count; không để nhiều wrappers cùng free.
- **Không expose raw pointer** hoặc một `ByteBuffer` lâu dài nếu không thể kiểm soát use-after-close.
- Có trạng thái rõ **OPEN → CLOSING → CLOSED**; `close()` không chạy trong lúc có operation đang dùng buffer.
- Nếu wrapper chọn `close()` idempotent, implementation phải có guard bằng locking/atomic state, **không giả định `Arena.close()` cũng idempotent**.
- Mọi thất bại khi allocate/constructor trước khi bàn giao ownership phải rollback và gọi deallocator đúng.
- `close()` gọi cleanup đúng allocator và đúng thread. `Arena.ofConfined()` chỉ được đóng bởi thread sở hữu; nếu cần đa luồng, xem `Arena.ofShared()` và đồng bộ đóng.
- Nếu thư viện có `retain/release`, wrapper giữ số lượng refs đúng và chỉ hủy dữ liệu khi ref-count thực sự về zero.
- Trước khi release, đợi các tác vụ C và Java còn giữ alias hoàn tất; xác định ai chờ và ai signal.
- Nếu native deallocator có thể báo lỗi, định nghĩa cách truyền lỗi; không âm thầm coi cleanup thất bại như đã free.
- Test **double-close**, **use-after-close**, lỗi cấp phát, lỗi I/O, concurrent consumers và trường hợp native API chỉ trả borrowed view.

Ví dụ API thiết kế đúng hướng:

```java
// Ý tưởng API: chưa phải implementation đầy đủ.
try (OwnedNativeBuffer owner = openNativeBuffer()) {
    owner.useSynchronously(buffer -> {
        // Chỉ mượn ByteBuffer trong khoảng callback này.
        // Không lưu vào field hoặc trả reference ra ngoài.
        return consume(buffer);
    });
} // Đợi in-flight users kết thúc rồi gọi native release.
```

Cấu trúc callback giúp giao tiếp rõ lifetime, nhưng **không tự ngăn** callback cố ý giữ alias. Với API public khó tin cậy callers, có thể cấp bản sao read-only, trả Java primitives/arrays, hoặc áp dụng kiểm soát handle có đồng bộ. Không thể biến raw pointer tự do thành memory-safe hoàn toàn chỉ bằng interface Java.

## 10. Những lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Native memory leak dù Java heap ổn | C `malloc` nhưng không có release path sau khi Java giữ buffer | Xác định owner; `AutoCloseable` và correct native deallocator |
| Double-free/native heap corruption | Java explicit free **và** Arena cleanup/C Cleaner cùng chạy | Chỉ một cleanup owner; guard idempotent ở wrapper |
| `ByteBuffer` còn reachable nhưng JVM crash | Native owner đã `free` trước khi Java ngừng dùng | Borrow/lifetime contract; đợi users; copy nếu cần |
| Gọi `free` của CRT khác với DLL đã malloc | Allocator/heap mismatch, đặc biệt Windows CRT | Gọi `library_release` hoặc đúng deallocator cùng allocator |
| Dùng `GetDirectBufferAddress` để free mọi buffer | Địa chỉ không chứng minh ownership hay nguồn allocation | Dùng opaque owner handle đã được kiểm soát |
| `ByteBuffer.allocateDirect` bị đối xử như C `malloc` | Nhầm Java-managed direct memory với C-managed memory | Không native free trừ khi API rõ ràng chuyển ownership |
| `reinterpret(size)` lớn hơn block thật | Java không biết size native cấp phát | Validate size/ABI; bounded cap; không đoán từ pointer |
| `reinterpret` với Arena rồi vẫn dùng raw global pointer | FFM scoped view không thu hồi mọi alias | Không lộ pointer thô; cleanup thống nhất |
| `IllegalStateException` sau Arena.close | Dùng view FFM sau scope lifetime | Copy trước close; không giữ scoped ByteBuffer |
| `WrongThreadException` | Confined Arena được dùng/đóng sai thread | Cùng thread owner hoặc shared arena + coordination |
| Native buffer ghi file ra bytes lạ | C chỉ ghi một phần, Java ghi cả capacity | Chỉ write initialized length; đúng position/limit |
| Corrupt dữ liệu multi-byte | Byte order mặc định của ByteBuffer khác native | `ByteOrder.nativeOrder()` hoặc encoding theo file/API contract |
| Crash khi async read/write | C hoặc Java free trong lúc I/O đang dùng pointer | Có completion barrier, reference count hoặc copy |
| File-mapped memory được giải phóng bằng `free` | API acquisition/release không khớp | Dùng `munmap/UnmapViewOfFile` và handle policy phù hợp |

Một lỗi nữa: **nhận `ByteBuffer` view từ JNI rồi bỏ Java reference không bảo đảm native block được free**. Đối với C-owned memory, GC có thể thu Java wrapper nhưng C vẫn giữ allocation; nếu không có cleanup protocol, native heap vẫn leak. Ngược lại, giải phóng C memory khi Java alias còn live còn nguy hiểm hơn leak vì có thể crash JVM.

## 11. Checklist tích hợp native buffers

- [ ] Xác nhận source C: `malloc`, custom allocator, mapped file hay OS handle.
- [ ] Có bảng rõ **owner, borrower, size, read/write rights, release function, lifetime** cho từng pointer.
- [ ] Check native status trước khi tin pointer/length; phân biệt null/error/partial result.
- [ ] Validate byte count, overflow, byte order và số bytes thực sự initialized.
- [ ] Không gọi `free` với pointer mượn hoặc không thuộc allocator đó.
- [ ] Đối với transferred ownership: release **một lần**, dù có exception; rollback nếu chưa gắn cleanup thành công.
- [ ] Không đăng ký hai deallocators cho cùng block; không double-free.
- [ ] JNI `NewDirectByteBuffer`: có owner/release contract rõ, không tin GC tự dọn C memory.
- [ ] FFM `reinterpret`: hiểu đây là restricted view, không phải allocation; cleanup action gắn với Arena đúng lifetime.
- [ ] Giữ native library/deallocator loaded tới khi cleanup chạy xong.
- [ ] Không dùng `slice()`/`duplicate()` sau close/free; tất cả aliases cùng chia sẻ backing memory.
- [ ] Với FileChannel hoặc native async I/O: đợi operations hoàn tất trước khi release.
- [ ] Nếu caller cần dữ liệu sau release, copy sang Java-owned `byte[]` hoặc owned buffer.
- [ ] Test allocation failure, exception mid-operation, memory leak, double-close, wrong-thread, async completion, native sanitizer/profiler.

## 12. Câu hỏi tự luyện

1. Tại sao giữ một biến Java kiểu `ByteBuffer` không đồng nghĩa JVM sẽ tự gọi `free` cho C `malloc`?
2. `NewDirectByteBuffer` có tham số cleanup/deallocator không? Khi JNI trả direct buffer, ai phải chịu trách nhiệm release?
3. Một C API trả pointer tới `static const char[]`, Java được phép `free` không? Tại sao?
4. Nếu C malloc bằng allocator của DLL A và Java gọi `free` của DLL B, nguy cơ gì có thể xảy ra?
5. `ByteBuffer.duplicate()` hoặc `slice()` có tạo native allocation độc lập không? Khi owner free, các aliases còn dùng được không?
6. Trong ví dụ `NativeMallocOwnershipDemo`, vì sao `owner` phải đóng **trước** `libraryLifetime`?
7. Tại sao cần `cleanupRegistered` để rollback khi `reinterpret` thất bại, và vì sao không `free` thủ công khi đăng ký cleanup đã thành công?
8. Vì sao bản sao `byte[]` vẫn dùng được sau close, trong khi scoped direct `ByteBuffer` không được dùng?
9. `reinterpret(size, arena, cleanup)` có xác minh block thật dài `size` byte không? Trường hợp đoán size sai có thể gây điều gì?
10. Với `FileChannel.write`, vì sao phải dùng `numberOfValidBytes` chứ không ghi cả `capacity` theo mặc định?
11. Một native library giữ pointer để ghi bất đồng bộ sau khi function submit đã trả về. Khi nào Java được đóng Arena hoặc free block?
12. Sự khác nhau giữa **borrowed**, **transferred** và **caller-owned** native buffers là gì? Hãy chỉ ra đúng phía cleanup cho từng trường hợp.

**Ghi nhớ:** Khi Java giữ `ByteBuffer`/`MemorySegment` trỏ tới memory **do C cấp phát**, **quyền sở hữu không tự di chuyển theo Java reference**. Phải có hợp đồng minh bạch về allocator, size, lifetime, quyền truy cập và deallocator. Nếu C vẫn sở hữu, Java chỉ mượn và không được free. Nếu ownership chuyển cho Java, Java chịu trách nhiệm release bằng **đúng native API, đúng một lần**, sau khi mọi user hoàn tất. Dùng FFM Arena + cleanup có kiểm soát, JNI owner wrapper hoặc copy về Java heap để tránh use-after-free.

### Tài liệu chính thức

- [Oracle JNI Specification JDK 24 — NewDirectByteBuffer, GetDirectBufferAddress](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/functions.html).
- [Oracle JDK 24 — MemorySegment API: reinterpret, asByteBuffer, scope](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [Oracle JDK 24 — Arena API: lifetime, cleanup và thread confinement](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html).
- [Oracle JDK 24 — Linker API for downcalls](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.html).
- [Oracle JDK 24 — SymbolLookup.libraryLookup lifetime](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- [Oracle Java `ByteBuffer` API — direct buffers, order, position/limit/capacity](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/ByteBuffer.html).
- [OpenJDK JEP 454 — FFM Final API (JDK 22)](https://openjdk.org/jeps/454).
- [OpenJDK JEP 442 — FFM Third Preview (JDK 21)](https://openjdk.org/jeps/442).
