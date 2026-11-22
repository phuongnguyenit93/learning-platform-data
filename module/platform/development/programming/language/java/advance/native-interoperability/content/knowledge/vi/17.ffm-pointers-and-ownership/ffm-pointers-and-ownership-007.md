# Quy định bộ nhớ được mượn, chuyển giao hoặc phải giải phóng bởi bên gọi trong Java Native Interoperability

Khi Java tương tác với mã native C/C++ qua JNI hoặc Foreign Function & Memory API (FFM), một con trỏ có thể hợp lệ về mặt địa chỉ nhưng **không có quyền sở hữu (ownership)**. Cũng một chữ ký `void *`, `char *`, `MemorySegment` hay `long handle` có thể đại diện cho ba hợp đồng hoàn toàn khác nhau:

1. **Borrowed (mượn):** bên nhận chỉ được sử dụng tạm thời, **không được giải phóng**; bên sở hữu gốc bảo đảm vùng nhớ còn sống trong thời gian mượn.
2. **Transferred (chuyển giao quyền sở hữu):** bên hiện đang sở hữu bàn giao trách nhiệm hủy tài nguyên cho bên kia; sau khi transfer thành công, chủ cũ **không được dùng/giải phóng** như thể vẫn còn là chủ.
3. **Caller-owned / caller-frees (bên gọi sở hữu và phải giải phóng):** API cấp phát rồi **trả về một tài nguyên có owner là bên gọi**; bên gọi phải dùng đúng hàm giải phóng được công bố, thường là cặp `create/destroy` của **chính thư viện cấp phát**, không tự chọn `free` tùy ý.

Đây là bài về **hợp đồng ownership và lifetime**. Từ `const` trong `const char *` có thể biểu thị chỉ được đọc qua pointer đó, **không** tự cho biết ai phải `free`. Tương tự, việc Java giữ một `ByteBuffer` hoặc `MemorySegment` không tự chứng minh rằng nó sở hữu vùng native mà đối tượng mô tả.

**Nguyên tắc một dòng:** với mọi tài nguyên, trả lời chính xác **ai cấp**, **ai sở hữu hiện tại**, **ai được dùng**, **dùng đến khi nào**, **ai giải phóng**, **giải phóng bằng API nào**, và **lỗi xảy ra thì ownership nằm ở đâu**.

## 1. Ownership là một contract, không phải kiểu con trỏ

C thường biểu diễn mọi trường hợp dưới dạng pointer:

```c
const unsigned char *get_bytes(void);
unsigned char *create_bytes(size_t size);
void consume_bytes(unsigned char *bytes);
```

Đây là **khai báo minh họa**, không phải một chương trình C độc lập. Chỉ nhìn chữ ký, ta **không biết**:

- `get_bytes()` trả pointer đến bộ nhớ tĩnh, mượn từ object, hay cấp phát mới?
- `create_bytes()` có thể được giải phóng bằng `free` hay phải gọi `destroy_bytes`?
- `consume_bytes` chỉ đọc, ghi dữ liệu, hay **nhận luôn ownership**?
- Khi `consume_bytes` lỗi, bên gọi còn sở hữu buffer không?
- Pointer có còn hợp lệ sau callback hoặc sau `close` không?
- Có được gọi từ thread khác không?

Một thiết kế tốt phải công bố các điều kiện ấy trong API contract, không bắt người dùng thử nghiệm để suy ra.

### Bảng phân loại cơ bản

| Loại contract | Bên cấp phát/sở hữu trước lời gọi | Quyền của bên nhận | Ai giải phóng? | Ví dụ điển hình |
| --- | --- | --- | --- | --- |
| Borrowed, read-only | Bên cung cấp dữ liệu | Đọc trong thời hạn được công bố | **Chủ gốc**; borrower không `free` | C nhận `const uint8_t *` và `size` chỉ trong lời gọi |
| Borrowed, writable | Chủ gốc | Đọc/ghi trong thời hạn được công bố | **Chủ gốc** | Hàm C ghi vào buffer do caller cấp |
| Caller-allocated output | Bên gọi cấp buffer và capacity | Callee ghi tối đa capacity | **Bên gọi** | `fill_bytes(out, cap, &written)` |
| Callee-allocated, caller-frees | Thư viện cấp phát, trả ownership ra ngoài | Caller dùng sau khi API return | **Caller**, bằng đúng destructor/free API | `create_blob` + `destroy_blob` |
| Ownership transfer to callee | Caller đang sở hữu | Callee giữ và quản lý sau thành công | **Callee** sau transfer | `adopt_blob`, `take_buffer` |
| Shared ownership | Nhiều owners theo protocol | Dùng khi còn share reference/lease hợp lệ | Owner cuối theo ref-count/contract | Native handle có `retain/release` |
| JNI borrowed elements | JVM quản lý Java array/string và quyền Get | C dùng tạm pointer JNI cấp | **C phải gọi JNI Release để trả quyền mượn**, không `free` | `GetByteArrayElements` → `ReleaseByteArrayElements` |
| Java-owned off-heap region qua FFM | `Arena` quản lý | Dùng segment trong scope/thread cho phép | **Owner arena**, không giải phóng bằng C `free` tùy ý | `Arena.ofConfined().allocate(...)` |

**Phân biệt chủ sở hữu dữ liệu với trách nhiệm kết thúc một lease:** `GetByteArrayElements` có thể trả pointer vào data JVM hoặc bản sao do VM quản lý. Native code **không sở hữu allocation để dùng `free`**, nhưng **vẫn có nghĩa vụ gọi `ReleaseByteArrayElements`** để trả quyền sử dụng. Đây là một tài nguyên mượn có cặp Get/Release, không phải caller-owned allocation kiểu `malloc`.

## 2. Sáu câu hỏi bắt buộc cho mỗi pointer/handle

Khi review một lời gọi native, đặt những câu hỏi sau:

1. **Origin:** Pointer đến từ `malloc`, `new`, Java array, `GetStringUTFChars`, `Arena.allocate`, `mmap`, OS handle hay allocator của bên thứ ba?
2. **Owner:** Trước lời gọi, ai là owner? Sau lời gọi thành công, owner thay đổi hay không?
3. **Lifetime:** Pointer sống qua **một hàm**, **một callback**, **một request**, **một Java object** hay **đến khi gọi explicit release**?
4. **Allowed operations:** Pointer read-only/writable? Có được giữ lại, dùng từ thread khác, thay đổi capacity hoặc tạo view khác không?
5. **Failure:** Nếu API trả lỗi hoặc Java exception xuất hiện, caller còn phải free không? Callee có thể đã nhận ownership một phần không?
6. **Deallocator:** Phải dùng `free`, `delete[]`, `destroy_blob`, `ReleaseStringUTFChars`, `DeleteGlobalRef`, `munmap` hay `Arena.close()`? Có cần đúng thread/allocator?

Thiếu **một** câu trả lời có thể dẫn đến memory leak, double-free, use-after-free, heap corruption, race hoặc crash JVM. Một địa chỉ trong phạm vi số học hợp lệ chưa đủ để chứng minh quyền truy cập: nó còn cần object sống, bounds và ABI phù hợp.

## 3. Quy định borrowed: không được giải phóng, không được giữ quá hạn

Một hàm C nhận dữ liệu chỉ đọc:

```c
/* Contract: 'data' mượn từ caller trong thời gian hàm chạy.
 * length là số byte thực; callee KHÔNG retain pointer.
 * Callee KHÔNG free, không ghi vào data.
 */
unsigned long checksum_borrowed(const unsigned char *data,
                                size_t length);
```

**Contract đúng:**

- Caller phải bảo đảm `data` trỏ tới ít nhất `length` bytes hợp lệ cho **toàn bộ thời gian hàm chạy**.
- Callee chỉ đọc các bytes trong bounds.
- Callee **không** lưu pointer để dùng sau khi hàm return, trừ khi một contract khác cho phép và có cơ chế lifetime riêng.
- Callee không gọi `free(data)`.
- Sau return, caller vẫn sở hữu vùng memory và tiếp tục quyết định lifecycle.

`const` là tín hiệu về **mutability**, không đủ làm tài liệu về ownership. Một pointer `const char *` vẫn có thể trỏ tới vùng mới malloc mà caller phải free bằng một API riêng; ngược lại `char *` không nhất thiết cho phép callee free.

### Borrowing cho callback và async

Nếu C nhận:

```c
/* C API minh họa; không phải implementation độc lập. */
typedef void (*bytes_callback)(void *ctx,
                               const unsigned char *data,
                               size_t length);
void register_callback(bytes_callback callback, void *ctx);
```

Cần định nghĩa **callback chỉ mượn data trong lúc callback chạy** hay **giữ pointer/ctx để gọi về sau**. Nếu native code cất `ctx` là pointer đến buffer Java/FFM tạm thời để dùng nhiều giờ sau, hợp đồng synchronous borrowing đã bị phá.

Đối với callback bất đồng bộ, phải có cơ chế bảo đảm cả **dữ liệu**, **context**, **native library/code** và **callback function pointer** còn sống cho đến khi callback cuối hoàn tất. Chỉ giữ pointer trần trong C không khiến Java GC coi buffer đó là strong Java reference.

## 4. Quy định caller-frees: dùng đúng cặp cấp phát/hủy

Ví dụ một thư viện C sở hữu allocator nội bộ:

```c
/* Contract ví dụ: create_blob trả ownership cho caller.
 * Trả NULL nếu thất bại. Caller gọi destroy_blob đúng một lần
 * sau khi sử dụng; tuyệt đối không tự chọn free/delete[].
 */
typedef struct Blob Blob;
Blob *create_blob(size_t length);
size_t blob_size(const Blob *blob);
const unsigned char *blob_data(const Blob *blob); /* borrowed */
void destroy_blob(Blob *blob);
```

Trong ví dụ này:

- Pointer `Blob *` trả từ `create_blob` thuộc về **caller**.
- Hàm `blob_data` trả **borrowed view** sống tối đa đến lúc `destroy_blob(blob)` hoặc một mutation làm invalidated view theo contract.
- Caller phải gọi `destroy_blob(blob)` **một lần** khi hoàn tất (trừ trường hợp contract cho phép `NULL` hoặc chuyển ownership đi nơi khác).
- Không gọi `free(blob)` từ code Java/JNI nếu contract yêu cầu `destroy_blob`: thư viện có thể dùng arena/pool allocator, memory-mapped storage, C++ `new` hoặc cần đóng handle khác trước khi giải phóng.
- Không gọi `destroy_blob` rồi tiếp tục đọc `blob_data`: đó là use-after-free.

**Allocator matching là bất biến quan trọng:** ai cấp phát qua allocator X thì giải phóng qua API tương ứng của X. `malloc/free`, `new/delete`, `new[]/delete[]`, `CoTaskMemAlloc/CoTaskMemFree`, library `create/destroy` và `Arena.allocate/Arena.close` **không hoán đổi tùy ý**.

### Bảng cặp tạo–hủy

| Nguồn tài nguyên | Hàm/API cấp phát | Hàm/API trả lại |
| --- | --- | --- |
| Native C heap | `malloc` / `calloc` / `realloc` | `free` theo contract; sau `realloc` owner pointer có thể đổi |
| C++ object | `new T` | `delete` hoặc `std::unique_ptr<T>` |
| C++ array | `new T[n]` | `delete[]` hoặc RAII container |
| Library opaque handle | `lib_create(...)` | `lib_destroy(handle)` do thư viện công bố |
| OS file/descriptor | `open` / `fopen` / platform API | `close` / `fclose` / platform-specific close |
| JNI byte elements | `GetByteArrayElements` | `ReleaseByteArrayElements` với cùng array/pointer |
| JNI UTF string lease | `GetStringUTFChars` | `ReleaseStringUTFChars` với cùng `jstring`/pointer |
| JNI global reference | `NewGlobalRef` | `DeleteGlobalRef` |
| FFM confined/shared memory | `Arena.allocate` | `Arena.close()` bởi đúng owner/lifetime |
| DirectByteBuffer bọc C malloc | `malloc` và `NewDirectByteBuffer` | Native `free` theo owner protocol; **không** tự free vì buffer GC |

Bảng này là contract minh họa; các loại allocator/OS/library cụ thể có quy tắc riêng. Không dựa vào kiểu pointer hoặc tên đối tượng Java để suy ra deallocator.

## 5. Quy định ownership transfer: hai bên không được cùng làm owner

Khi API **tiếp nhận quyền sở hữu** (take/adopt), contract cần xác định **thời điểm giao quyền**:

```c
/* Mẫu API C có ownership chuyển giao:
 *
 * SUCCESS:
 *   Hàm nhận ownership của *inout và đặt *inout = NULL.
 *   Caller không còn quyền dùng/free object cũ.
 *
 * ERROR:
 *   Ownership KHÔNG đổi; *inout vẫn là pointer ban đầu.
 *   Caller tiếp tục có nghĩa vụ hủy.
 *
 * Hàm phải tự triển khai đúng contract này.
 */
int adopt_blob(Blob **inout);
```

Chữ ký trên chỉ là **gợi ý thiết kế**, không tự động biến contract thành hiện thực. Implementation phải bảo đảm nếu thất bại giữa chừng, không để caller và callee cùng tưởng mình sở hữu cùng buffer, hoặc ngược lại **cả hai đều không sở hữu**.

### Khi thành công

```c
Blob *owner = create_blob(128);
if (owner == NULL) {
    /* Xử lý allocation failure. */
} else if (adopt_blob(&owner) == 0) {
    /* Theo contract: owner == NULL; callee đã nhận trách nhiệm. */
} else {
    /* Theo contract: owner vẫn do caller sở hữu. */
    destroy_blob(owner);
    owner = NULL;
}
```

Đoạn này **minh họa**, chưa có implementation của `Blob`, `create_blob` và `adopt_blob`. Quy ước `0` là thành công chỉ áp dụng nếu API do bạn thiết kế định nghĩa như vậy.

### Failure atomicity và partial transfer

Câu hỏi sống còn: **nếu callee bắt đầu xử lý nhưng trả lỗi, ai free?** Có ba policy thường thấy:

1. **Transfer only on success:** thất bại trả ownership về caller không thay đổi.
2. **Consume always:** callee nhận ownership ngay khi gọi, bất kể kết quả thành công hay thất bại; caller không free sau lời gọi.
3. **Partial transfer:** mỗi phần được nhận có owner riêng, API phải cho biết rõ những phần đã tiêu thụ. Loại này khó dùng và dễ leak; tránh nếu không cần.

Không đoán policy từ giá trị return. Viết trong documentation và unit tests. Với FFI native không đáng tin hoặc plugin ABI thay đổi, tốt hơn dùng **opaque handles**, **hai pha prepare/commit** và error contract dễ kiểm chứng.

### Shared ownership không phải transfer đơn giản

Một API `retain(handle)`/`release(handle)` có thể quản lý reference count; lúc đó mỗi owner giữ một reference và giải phóng lần cuối mới hủy object. Cần xử lý concurrency/atomic refcount, tránh cycle và xác định callback nào được phép retain. Không tự tạo nhiều `jlong` chứa cùng pointer rồi xem mỗi wrapper là owner độc lập.

## 6. JNI: `Get...` là quyền mượn có cặp `Release`

Trong JNI, Java array hay Java `String` do JVM quản lý. Một native method muốn đọc giá trị có thể mượn vùng dữ liệu thông qua `Get...`. Con trỏ trả về **không phải malloc pointer do caller có thể free**.

### Array elements: JVM có thể pin hoặc copy

```c
/* Mẫu hàm C trong JNI; env và byteArray hợp lệ. */
jsize length = (*env)->GetArrayLength(env, byteArray);
jbyte *elements = (*env)->GetByteArrayElements(env, byteArray, NULL);
if (elements == NULL) {
    /* Get thất bại: không có lease hợp lệ để release. */
    return; /* Chỉ đúng với hàm C trả void. */
}
for (jsize i = 0; i < length; ++i) {
    /* Đọc elements[i] tại đây. */
}
(*env)->ReleaseByteArrayElements(
        env, byteArray, elements, JNI_ABORT);
```

**Hợp đồng ở đây:**

- Java array vẫn do JVM quản lý.
- `GetByteArrayElements` có thể tạo bản sao hoặc trả pointer vào mảng được pin; `isCopy` không được dùng làm điều kiện để bỏ `Release`.
- `ReleaseByteArrayElements` trả lại quyền sử dụng. Với xử lý chỉ đọc, `JNI_ABORT` phù hợp để không copy-back bản sao; không mặc nhiên nghĩa mọi thay đổi trên pinned memory đều có thể rollback.
- Không giữ `elements` sau `Release` và không cất vào global C variable để dùng bất đồng bộ.
- Không `free(elements)`; không truyền `elements` cho một API C **take ownership** nếu API ấy sẽ tự giải phóng.
- `Get...ArrayCritical` có cặp `ReleasePrimitiveArrayCritical` riêng và ràng buộc **không block/không gọi JNI tùy ý** trong critical region.

#### Ba giá trị mode của Release

| Mode | Khi JNI đã tạo bản sao | Ý nghĩa ownership |
| --- | --- | --- |
| `0` | Copy-back dữ liệu rồi free bản sao | **Kết thúc lease** |
| `JNI_ABORT` | Không copy-back; free bản sao | **Kết thúc lease**; hay dùng chỉ đọc |
| `JNI_COMMIT` | Copy-back nhưng **không free** bản sao | **Chưa kết thúc lease**; cần một lần Release cuối với `0`/`JNI_ABORT` |

Theo JNI Specification, nếu elements không phải copy, mode không tạo ra "undo" ma thuật cho những byte đã sửa trực tiếp. Không dùng `JNI_ABORT` làm cơ chế transaction rollback khi đã write vào pinned data.

### String access: release bằng đúng cặp

```c
/* jstring text là Java reference, không phải char*. */
const char *utf = (*env)->GetStringUTFChars(env, text, NULL);
if (utf == NULL) {
    return; /* Đoạn minh họa cho native void method. */
}

/* Đọc modified UTF-8 bytes theo độ dài JNI phù hợp. */

(*env)->ReleaseStringUTFChars(env, text, utf);
```

`GetStringUTFChars` trả **modified UTF-8**, không nhất thiết là UTF-8 chuẩn mà các C libraries nhận. Pointer mượn phải kết thúc bằng `ReleaseStringUTFChars` dù JVM cấp bản sao hay không. `GetStringChars` thì dùng `const jchar*` theo UTF-16 và **`ReleaseStringChars`**. Không đổi chéo cặp, không giữ pointer sau Release và không dùng `free`.

**Quan trọng:** `DeleteLocalRef(text)` chỉ quản lý JNI reference; nó **không** thay thế `ReleaseStringUTFChars` cho con trỏ đã Get. Local ref hết hạn khi native frame trả về Java cũng không làm một lần Get bị bỏ Release trở thành đúng.

### Nếu không muốn lease, hãy dùng Region/copy

`GetByteArrayRegion(env, array, 0, length, nativeBuffer)` **sao chép** vào buffer do C đã cấp. Nó không tạo pointer mượn kiểu `GetByteArrayElements` nên **không có** `ReleaseByteArrayRegion`. Caller sở hữu `nativeBuffer` theo allocator của nó.

`SetByteArrayRegion` sao chép dữ liệu từ native buffer vào Java array; Java array sau đó vẫn do JVM quản lý. Một hướng chuyển đổi ownership rất an toàn là **copy bytes tại boundary** thay vì trao pointer trực tiếp. Thường tốn chi phí copy nhưng tách lifetime rõ ràng.

## 7. JNI references và native allocation là hai loại quyền sở hữu

Các JNI references không đồng nhất với pointer C:

| JNI operation | Nó tạo ra gì? | Lifetime/cleanup |
| --- | --- | --- |
| `NewStringUTF` | Java `jstring` local reference | `DeleteLocalRef` khi không cần; không `free` Java object |
| `NewObject` | Java `jobject` local reference | JVM quản lý object; local ref theo JNI frame |
| `NewGlobalRef` | Global reference giữ Java object reachable | `DeleteGlobalRef` khi hoàn thành |
| `NewWeakGlobalRef` | Weak global ref | `DeleteWeakGlobalRef` |
| `GetStringUTFChars` | Lease của một vùng ký tự/biểu diễn MUTF-8 | `ReleaseStringUTFChars`, **khác** DeleteLocalRef |
| `malloc` trong native library | C allocation | `free` / destructor phù hợp |
| `jlong` chứa địa chỉ malloc | Số nguyên biểu diễn pointer, **không tự có ownership** | Wrapper/owner phải định nghĩa explicit close |

Một callback C lưu `jobject` local reference vào global C variable rồi dùng sau khi native method return là lỗi lifetime. Muốn giữ Java object qua các calls, dùng `NewGlobalRef` và `DeleteGlobalRef` theo owner chính xác. Dù có global ref, thread khác cần `JNIEnv*` của chính thread thông qua attach khi phù hợp; không truyền `JNIEnv*` xuyên threads.

Đừng dùng `DeleteGlobalRef` thay cho `free` của một native allocation, hoặc `free` thay cho `DeleteGlobalRef`. Chúng thuộc hai bộ quản lý tài nguyên khác nhau.

## 8. DirectByteBuffer: một Java view không mặc nhiên sở hữu pointer C

JNI có:

```c
jobject NewDirectByteBuffer(
        JNIEnv *env, void *address, jlong capacity);
```

API tạo một direct `java.nio.ByteBuffer` nhìn vào native memory ở `address`, với `capacity` bytes. **Nó không phải một lệnh chuyển quyền sở hữu implicit** cho JVM hay một lời hứa rằng GC của buffer sẽ gọi `free(address)` do C cấp.

Ví dụ nguy hiểm:

```c
/* Minh họa lỗi thiết kế, không chạy như code production. */
void *mem = malloc(4096);
jobject view = (*env)->NewDirectByteBuffer(env, mem, 4096);
free(mem); /* SAI: view vẫn trỏ vào vùng vừa free. */
return view; /* Chỉ hợp chữ ký native function trả jobject. */
```

Ngược lại, **không free** pointer do C cấp rồi kỳ vọng `NewDirectByteBuffer` tự free khi Java không dùng cũng có thể gây leak.

Thiết kế đúng cần một **owner handle** tồn tại ít nhất cho đến khi mọi view/callback sử dụng buffer hoàn tất; Java `AutoCloseable` hoặc native `destroy(handle)` nhận trách nhiệm. Khi owner đóng, các alias ByteBuffer cũ phải được coi là invalid; do ByteBuffer thông thường không kiểm tra full C allocation lifetime, API wrapper không nên để view thoát ngoài owner kiểm soát.

`ByteBuffer.allocateDirect(...)` của JDK có cơ chế cấp phát và thu hồi riêng do JDK quản lý; đừng suy contract này áp dụng tương tự cho **`NewDirectByteBuffer` bọc một pointer C do bạn malloc**. `GetDirectBufferAddress` trả địa chỉ của direct buffer có backing memory hợp lệ theo API; không có nghĩa caller được `free` địa chỉ đó.

## 9. Ví dụ hoàn chỉnh Java 17+ / JNI C11: mượn dữ liệu và caller phải đóng bộ nhớ đã copy

Bài thực hành này tách **hai kiểu hợp đồng trong cùng một chương trình**:

- `borrowedSum(byte[])`: native code **mượn** Java bytes thông qua `GetByteArrayElements`, tính tổng rồi `ReleaseByteArrayElements(..., JNI_ABORT)` trước khi trả về. Native code không sở hữu array và không giữ pointer.
- `nativeCopy(byte[])`: native code tạo một **bản sao độc lập bằng `malloc`**, trả opaque-ish `jlong` handle cho Java wrapper. Java **trở thành owner**, có nghĩa vụ gọi `nativeFree` đúng một lần; `try-with-resources` làm điều này đáng tin cậy.
- `nativeChecksum(handle)`: **mượn** native block từ wrapper trong thời gian lời gọi chạy, không free/retain pointer.
- `nativeFree(handle)`: phá hủy allocation bằng `free` tại **cùng native module** đã cấp phát.

Kết quả quan trọng: sửa Java input sau khi copy thì lần mượn mới thấy dữ liệu Java mới, trong khi bản sao native vẫn giữ nội dung cũ.

**Giới hạn ví dụ:** chạy trên Linux/JDK 17+ và CPU pointer có thể chuyển qua `intptr_t`/`jlong` (phù hợp các kiến trúc Linux 64-bit phổ biến). Đây là **bài học về ownership**, không phải cách xây API bảo mật; raw pointer gói trong `jlong` không được tin nếu nhận từ nguồn không đáng tin. Input được giới hạn 1 MiB để tổng các unsigned bytes chắc chắn không tràn `jint` trong ví dụ.

### File 1 — `NativeOwnershipDemo.java`

```java
public final class NativeOwnershipDemo {
    static {
        System.loadLibrary("ownershipdemo");
    }

    private static final class OwnedBuffer implements AutoCloseable {
        // Chỉ wrapper này được sở hữu handle.
        // synchronized bảo vệ read/close trên CÙNG instance.
        private long handle;

        OwnedBuffer(byte[] input) {
            if (input == null) {
                throw new NullPointerException("input");
            }
            handle = nativeCopy(input);
            if (handle == 0) {
                throw new OutOfMemoryError("nativeCopy returned null");
            }
        }

        synchronized int checksum() {
            if (handle == 0) {
                throw new IllegalStateException("buffer closed");
            }
            return nativeChecksum(handle);
        }

        @Override
        public synchronized void close() {
            if (handle != 0) {
                long old = handle;
                handle = 0; // Không còn owner handle sau dòng này.
                nativeFree(old);
            }
        }
    }

    // Native code mượn Java array trong thời gian gọi.
    private static native int borrowedSum(byte[] source);

    // Native code cấp phát, chuyển ownership sang OwnedBuffer.
    private static native long nativeCopy(byte[] source);

    // Chỉ đọc dữ liệu native khi owner còn sống.
    private static native int nativeChecksum(long handle);

    // Đóng vùng nhớ được cấp phát bởi nativeCopy.
    private static native void nativeFree(long handle);

    public static void main(String[] args) {
        byte[] source = {1, 2, (byte) 0xFF};

        System.out.println(
                "borrowedBefore=" + borrowedSum(source));

        OwnedBuffer owned = new OwnedBuffer(source);
        try (owned) {
            System.out.println(
                    "ownedBefore=" + owned.checksum());

            source[0] = 9;

            System.out.println(
                    "borrowedAfter=" + borrowedSum(source));
            System.out.println(
                    "ownedAfter=" + owned.checksum());
        } // owned.close() tự được gọi một lần.

        try {
            owned.checksum();
            System.out.println("unexpectedUseAfterClose");
        } catch (IllegalStateException expected) {
            System.out.println(
                    "afterClose=IllegalStateException");
        }

        owned.close(); // Idempotent trên wrapper Java.
        System.out.println("closeTwice=ok");
    }
}
```

Các điểm cần đọc kỹ:

1. `OwnedBuffer` implements `AutoCloseable`, có **một** handle và `close()`. Owner là wrapper Java, không phải GC của một số `long`.
2. `try (owned)` là cú pháp Java 9+, được hỗ trợ trên Java 17 (biến resource effectively final). Dù code trong block ném Java exception, `close()` vẫn chạy.
3. `checksum()`/`close()` là `synchronized`, ngăn hai Java threads cùng sử dụng **chính instance này** đụng nhau trong lúc đóng. Nó không tự bảo vệ nếu native code giữ pointer ngoài wrapper, có nhiều wrappers cùng handle, hoặc một callback dùng pointer sau call.
4. `close()` đặt `handle = 0` trước khi gọi `nativeFree` để tránh double free qua cùng wrapper. Bài demo không giả định native freeing luôn có thể phục hồi nếu gặp lỗi OS/native; production cần contract riêng.
5. Một `jlong` tự nó không cấp khả năng kiểm tra validity. Không công khai pointer handles cho code không đáng tin; production nên cân nhắc opaque registry với id/generation và state machine.

### File 2 — `ownership_demo.c`

```c
#include "NativeOwnershipDemo.h" /* javac -h sinh ra, có jni.h */
#include <stdint.h>             /* intptr_t, SIZE_MAX */
#include <stddef.h>             /* size_t */
#include <stdlib.h>             /* malloc, free */

/* Demo Linux 32/64-bit với intptr_t vừa trong jlong. */
_Static_assert(sizeof(intptr_t) <= sizeof(jlong),
               "pointer does not fit into jlong");

/* Không dùng input quá 1 MiB để tránh jint sum overflow. */
#define MAX_INPUT (1024 * 1024)

typedef struct {
    jsize length;
    unsigned char bytes[]; /* Flexible array: nội dung copy-owned */
} NativeBlock;

static void throw_if_no_pending(JNIEnv *env,
                                const char *class_name,
                                const char *message) {
    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    jclass cls = (*env)->FindClass(env, class_name);
    if (cls != NULL) {
        (*env)->ThrowNew(env, cls, message);
        (*env)->DeleteLocalRef(env, cls);
    }
}

/* BORROWED: lấy Java array elements rồi Release; không retain pointer. */
JNIEXPORT jint JNICALL
Java_NativeOwnershipDemo_borrowedSum(JNIEnv *env, jclass clazz,
                                     jbyteArray source) {
    (void)clazz;

    if (source == NULL) {
        throw_if_no_pending(env, "java/lang/NullPointerException",
                            "source");
        return 0;
    }

    jsize length = (*env)->GetArrayLength(env, source);
    if (length > MAX_INPUT) {
        throw_if_no_pending(env, "java/lang/IllegalArgumentException",
                            "demo limit: 1 MiB");
        return 0;
    }
    if (length == 0) {
        return 0;
    }

    jbyte *elements = (*env)->GetByteArrayElements(env, source, NULL);
    if (elements == NULL) {
        throw_if_no_pending(env, "java/lang/OutOfMemoryError",
                            "GetByteArrayElements failed");
        return 0;
    }

    jint sum = 0;
    for (jsize i = 0; i < length; ++i) {
        sum += (jint)(unsigned char)elements[i];
    }

    /* Dù isCopy true hay false, C PHẢI trả lease. */
    (*env)->ReleaseByteArrayElements(
            env, source, elements, JNI_ABORT);
    return sum;
}

/* CALLEE ALLOCATES -> CALLER OWNS:
 * C tạo bản sao, trả handle; Java OwnedBuffer phải nativeFree.
 */
JNIEXPORT jlong JNICALL
Java_NativeOwnershipDemo_nativeCopy(JNIEnv *env, jclass clazz,
                                    jbyteArray source) {
    (void)clazz;

    if (source == NULL) {
        throw_if_no_pending(env, "java/lang/NullPointerException",
                            "source");
        return 0;
    }

    jsize length = (*env)->GetArrayLength(env, source);
    if (length > MAX_INPUT) {
        throw_if_no_pending(env, "java/lang/IllegalArgumentException",
                            "demo limit: 1 MiB");
        return 0;
    }

    if ((size_t)length > SIZE_MAX - sizeof(NativeBlock)) {
        throw_if_no_pending(env, "java/lang/OutOfMemoryError",
                            "allocation size overflow");
        return 0;
    }

    NativeBlock *block = (NativeBlock *)malloc(
            sizeof(NativeBlock) + (size_t)length);
    if (block == NULL) {
        throw_if_no_pending(env, "java/lang/OutOfMemoryError",
                            "native malloc failed");
        return 0;
    }

    block->length = length;
    if (length > 0) {
        /* Copy vào bộ nhớ C đã cấp. Không mượn pointer array. */
        (*env)->GetByteArrayRegion(
                env, source, 0, length, (jbyte *)block->bytes);
        if ((*env)->ExceptionCheck(env)) {
            free(block); /* Lỗi trước transfer -> C vẫn là owner. */
            return 0;
        }
    }

    /* Tại return thành công, ownership sang Java wrapper. */
    return (jlong)(intptr_t)block;
}

/* BORROWED handle: chỉ đọc, caller không chuyển ownership đi. */
JNIEXPORT jint JNICALL
Java_NativeOwnershipDemo_nativeChecksum(JNIEnv *env, jclass clazz,
                                        jlong handle) {
    (void)clazz;

    if (handle == 0) {
        throw_if_no_pending(env, "java/lang/IllegalStateException",
                            "buffer closed");
        return 0;
    }

    NativeBlock *block = (NativeBlock *)(intptr_t)handle;
    jint sum = 0;
    for (jsize i = 0; i < block->length; ++i) {
        sum += (jint)block->bytes[i];
    }
    return sum;
}

/* CALLER-FREES: đúng cùng allocator/module đã tạo block. */
JNIEXPORT void JNICALL
Java_NativeOwnershipDemo_nativeFree(JNIEnv *env, jclass clazz,
                                    jlong handle) {
    (void)env;
    (void)clazz;

    if (handle != 0) {
        NativeBlock *block = (NativeBlock *)(intptr_t)handle;
        free(block);
    }
}
```

**Giải thích ownership từng nhánh:**

- Trong `borrowedSum`, `GetByteArrayElements` thành công → C có **một lease JNI**. Sau khi tính tổng, `ReleaseByteArrayElements(..., JNI_ABORT)` hoàn tất lease. Nếu Get thất bại và trả `NULL`, C **không** Release pointer chưa được cấp.
- Trong `nativeCopy`, ngay sau `malloc`, C là **owner**. Nếu `GetByteArrayRegion` gặp lỗi, C phải `free(block)` và không trả một handle sở hữu chưa hoàn chỉnh sang Java.
- Chỉ khi `nativeCopy` trả handle khác 0 thành công, Java `OwnedBuffer` nhận trách nhiệm gọi `nativeFree`. Không được thêm `free(block)` sau lệnh return thành công.
- `nativeChecksum` chỉ mượn handle trong thời gian lời gọi JNI chạy, không free pointer. Java wrapper đang giữ monitor `synchronized`, nên `close` trên cùng object không đồng thời free trong lúc checksum đang đọc.
- `nativeFree` chỉ nhận handle đã được `nativeCopy` trả thành công **và chưa free**. JNI không có cách tự xác thực một `jlong` giả mạo trỏ tới vùng hợp lệ. Đây là điều kiện tiền đề của bài demo, không phải security boundary.

### Build và chạy trên Linux

Tạo hai file `NativeOwnershipDemo.java` và `ownership_demo.c` trong cùng thư mục. Cần JDK 17+ và compiler C cùng kiến trúc với JVM. Đặt `JAVA_HOME` trỏ tới JDK có `include/jni.h`:

```bash
javac -encoding UTF-8 -h . NativeOwnershipDemo.java

cc -std=c11 -Wall -Wextra -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libownershipdemo.so ownership_demo.c

java -Djava.library.path=. NativeOwnershipDemo
```

`javac -h .` tạo `NativeOwnershipDemo.h` với exported JNI method declarations. Linux ánh xạ tên logic `ownershipdemo` từ `System.loadLibrary` sang `libownershipdemo.so`. Windows/macOS cần cách build và tên native binary khác; chương trình này là demo dành cho Linux/JDK 17+.

### Stdout kỳ vọng

```text
borrowedBefore=258
ownedBefore=258
borrowedAfter=266
ownedAfter=258
afterClose=IllegalStateException
closeTwice=ok
```

Vì sao?

- `source` chứa unsigned byte values 1, 2, 255. Dù trong Java `(byte)0xFF` được hiển thị dưới dạng signed -1, mã C chủ động ép sang `unsigned char` nên `1 + 2 + 255 = 258`.
- `nativeCopy` sao chép **ba byte ban đầu** vào vùng mới malloc. `ownedBefore=258`.
- Sau khi Java đổi `source[0]` từ 1 thành 9, `borrowedSum` trên lần gọi mới mượn mảng **hiện tại** và trả `9 + 2 + 255 = 266`.
- Native block độc lập vẫn chứa 1, 2, 255, vì vậy `ownedAfter=258`.
- Khi rời `try (owned)`, `close()` gọi `nativeFree`. Mọi lần `checksum()` sau đó bị Java wrapper chặn bằng `IllegalStateException`, không dereference con trỏ cũ.
- Gọi `owned.close()` lần nữa không có tác dụng vì wrapper đã đặt handle về 0, nên in `closeTwice=ok`. Việc này chỉ bảo vệ **cùng wrapper**, không chứng minh hai wrappers dùng chung con trỏ là an toàn.

Chương trình không dùng `System.gc()`, không dựa vào finalizer hay Cleaner, và không tự động "chuyển" Java array vào native heap; nó **sao chép có chủ đích** để tách lifetime.

## 10. Hạn chế của `jlong` chứa pointer: minh họa khác production

Trong demo, `jlong handle` chứa địa chỉ native để tập trung vào bài học ownership. Nhưng một hàm nhận `long handle` từ public API không tự biết:

- Handle có được cấp bởi đúng allocator/library này không?
- Đã `free` từ trước hay chưa (stale handle)?
- Có bị sửa số bit địa chỉ không?
- Có hai wrappers cùng tưởng mình là owner không?
- Thread khác có đang đọc block trong lúc owner close không?
- Module native/library đang chứa code để free có còn được nạp không?

Dereference một pointer không hợp lệ trong C **có thể làm crash JVM**, không phải lúc nào cũng chuyển thành Java exception. Vì thế production nên dùng **opaque handle registry** thay vì trực tiếp tin tưởng địa chỉ do caller cung cấp. Một mô hình an toàn hơn có thể gán id/generation, giữ registry dưới lock, đếm các active borrows và chỉ free khi không còn borrower.

```text
Java AutoCloseable owner
      |
      +-- handle id + generation (không phải raw address)
               |
               v
Native registry (lock/ref-count/state)
      |
      +-- OPEN: cho phép checkout pointer tạm
      +-- CLOSING: không nhận borrows mới
      +-- CLOSED: giải phóng native allocation đúng một lần
```

Registry/lock cũng phải có chính sách xử lý callback và reentrancy. `synchronized` trong demo bảo vệ một Java instance, không thay thế cơ chế registry nếu nhiều handles cùng trỏ một allocation, C giữ con trỏ bất đồng bộ, hoặc user có thể tự gọi JNI qua reflection/native APIs.

**Không dùng `Cleaner` như giải pháp giải phóng chính** cho tài nguyên cần dọn xác định. Có thể dùng nó làm safety net nếu thiết kế state/deallocator đúng, nhưng cleanup time do GC quyết định và không có deadline. `finalize()` không phải lựa chọn cho owner native. `AutoCloseable` + `try-with-resources` hoặc C++ RAII là phương án rõ ràng hơn.

## 11. C++ RAII và hợp đồng riêng cho từng resource

C++ thường biến ownership thành một object **không thể copy** và destructor gọi đúng deleter. Ví dụ minh họa:

```cpp
#include <memory>

/* 'Blob' và 'destroy_blob' là API native giả định. */
struct BlobDeleter {
    void operator()(Blob *p) const noexcept {
        if (p != nullptr) {
            destroy_blob(p);
        }
    }
};

using UniqueBlob = std::unique_ptr<Blob, BlobDeleter>;

void example() {
    UniqueBlob owned(create_blob(128));
    if (!owned) {
        return;
    }

    // blob_data(owned.get()) trả con trỏ MƯỢN.
    const unsigned char *view = blob_data(owned.get());
    // Dùng view khi owned còn sống, theo contract.

} // ~unique_ptr tự destroy_blob chính xác một lần.
```

Đây là **mã C++ minh họa**, cần có header với khai báo `Blob`, `create_blob`, `destroy_blob` và `blob_data` trước khi biên dịch độc lập. Ý nghĩa:

- `UniqueBlob` là unique owner, nên tránh double-destroy qua copy.
- `view` chỉ mượn từ object do `owned` sở hữu; không được dùng sau destructor.
- `owned.release()` (nếu gọi) chuyển pointer thô ra khỏi `unique_ptr` **mà không destroy**: từ đó phải có owner mới rõ ràng; nếu bỏ pointer sẽ leak.
- `owned.reset(newPointer)` hủy object cũ rồi nhận owner mới (theo deleter đã cấu hình).

Để **transfer** từ một unique owner vào API native:

```cpp
/* Mẫu ý tưởng: take_blob có contract nhận ownership
 * chỉ khi trả thành công; cách chuyển phải bảo toàn owner
 * nếu thất bại. Không gọi raw.release() trước khi biết
 * API thực sự đã tiêu thụ object!
 */
```

Nếu API `take_blob` luôn tiêu thụ ownership dù thành công hay thất bại, `release` có thể được dùng theo đúng contract. Nếu transfer chỉ trên success, thiết kế một adapter hoặc API nhận pointer-to-pointer để đảm bảo không mất owner khi thất bại. **Không mặc định** mọi `void*` được hàm C nhận sẽ tự động trở thành callee-owned.

## 12. FFM Java 22+: Arena là owner, MemorySegment là một view có lifetime

FFM finalized từ JDK 22 dùng `java.lang.foreign.Arena` và `MemorySegment` để làm ownership/lifetime **rõ hơn** trên Java side:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment nativeData =
            arena.allocate(ValueLayout.JAVA_INT);

    nativeData.set(ValueLayout.JAVA_INT, 0, 42);
    int answer = nativeData.get(ValueLayout.JAVA_INT, 0);
    System.out.println(answer); // 42
} // arena.close() giải phóng backing native memory.
```

Đây là đoạn minh họa cần đặt trong class/method; chỉ chạy trên JDK 22+. Java 17 dùng FFM incubator API khác.

**Cơ chế ownership:**

- `Arena.ofConfined()` tạo owner có lifetime xác định; chỉ owner thread được truy cập và đóng.
- `Arena.ofShared()` cho nhiều threads truy cập nhưng caller vẫn phải điều phối khi nào đóng, không tự loại bỏ data races.
- `Arena.ofAuto()` để GC quản lý lifetime **không xác định lúc giải phóng** và không hỗ trợ close tường minh.
- `Arena.global()` có lifetime không giới hạn trong đời VM.
- `MemorySegment.asSlice(...)`, `asReadOnly()` và `asByteBuffer()` là views; chúng **không tự biến thành owners với lifetime riêng**.

Đừng `free` thủ công địa chỉ `nativeData.address()` bằng một C function ngẫu nhiên: allocation thuộc arena. Khi `arena.close()` thành công, các segment/views từ arena đó không còn quyền truy cập theo contract; dùng `get` sau close có thể ném `IllegalStateException`. Nếu C giữ raw address quá thời hạn, các kiểm tra Java không thể bảo vệ lần dereference từ C.

### Khi thư viện C trả pointer và báo Java phải free

FFM có thể tương tác với con trỏ mà thư viện C trả về. Nhưng Java không thể đoán **độ dài thật**, **alignment**, **owner** và **đúng deallocator** chỉ từ một địa chỉ. Các restricted operations như `MemorySegment.reinterpret(...)` gán bounds/lifetime theo contract; khai báo sai có thể cho truy cập vượt backing allocation hoặc dùng sau C `free`.

Một thiết kế an toàn là cung cấp cặp `native_alloc(...)`/`native_free(...)` ở chính thư viện native, bọc pointer trong một Java owner `AutoCloseable`, và không cho pointer thoát khỏi lifetime. Nếu FFM downcall gọi C `free`, nó phải dùng đúng allocator và function descriptor. Thao tác reinterpret **không chuyển quyền sở hữu** nếu C API chưa cho phép.

**Phân biệt FFM với JNI:** `MemorySegment` có bounds/scope checks khi truy cập bằng FFM, trong khi `jlong` pointer của demo không có những checks ấy. Dù vậy, cả hai vẫn cần hiểu chính xác ownership khi crossing boundary và khi C giữ pointer.

## 13. Exception safety và cleanup trên mọi nhánh

Tài nguyên có thể được acquire thành công rồi logic kế tiếp thất bại. Không thể chỉ giải phóng ở "happy path".

Một mẫu C phù hợp là **một khối cleanup cuối hàm**:

```c
/* Pseudocode C JNI, env, javaArray và thông số hợp lệ. */
jbyte *borrowed = NULL;
unsigned char *owned = NULL;
jint result = 0;

borrowed = (*env)->GetByteArrayElements(env, javaArray, NULL);
if (borrowed == NULL) {
    goto cleanup;
}

owned = (unsigned char *)malloc(1024);
if (owned == NULL) {
    goto cleanup;
}

/* Xử lý dữ liệu, có thể gặp lỗi hoặc JNI callback ném exception. */
result = 1;

cleanup:
free(owned); /* free(NULL) hợp lệ. */
if (borrowed != NULL) {
    (*env)->ReleaseByteArrayElements(
            env, javaArray, borrowed, JNI_ABORT);
}
return result;
```

Đây là mã **minh họa**, không phải một exported JNI function hoàn chỉnh. Trong production, cần biến lỗi malloc thành Java exception khi chưa có exception pending và preserve Java error gốc nếu JNI callback ném lỗi. `ReleaseByteArrayElements` là JNI cleanup call được phép khi có pending exception.

Với C++, một RAII wrapper giữ `JNIEnv*`, `jbyteArray` và pointer từ `GetByteArrayElements`, destructor `noexcept` gọi đúng `ReleaseByteArrayElements`; cấm copy wrapper để tránh Release hai lần. Java exception pending **không tự làm C++ stack unwind**: native code phải chủ động kiểm tra `ExceptionCheck` rồi `return` hoặc vào đường cleanup. Không để C++ exception vượt qua JNI boundary.

**Ownership trên nhánh lỗi phải rõ:**

- Trước khi transfer thành công, allocator C còn là owner; nếu bước khởi tạo thất bại, nó free.
- Sau transfer thành công, caller Java là owner; nếu Java method sau đó ném exception, `try-with-resources` vẫn gọi close.
- Borrowed JNI elements/string lease phải Release đúng một lần trên mọi nhánh đã Get thành công.
- Nếu cleanup cũng thất bại, cần chính sách không che lấp lỗi Java gốc; các hàm cleanup JNI được phép lúc exception pending nhưng không được gọi JNI operations không an toàn tùy ý.

## 14. Concurrent access: ai được free khi còn borrower?

Một thiết kế ownership có thể đúng trên một thread nhưng sai khi nhiều threads:

```text
Thread A: owner.checksum()
           |
           +-- borrowed pointer đang được đọc
                                Thread B: owner.close()
                                          |
                                          +-- free(pointer)
           |
           +-- đọc tiếp => use-after-free
```

Trong demo, Java methods `checksum()` và `close()` cùng `synchronized` **trên một owner instance**, nên hai thao tác đó không chạy đồng thời qua wrapper ấy. Nhưng:

- Nếu C giữ pointer ngoài thời gian `nativeChecksum`, wrapper lock không còn bảo vệ.
- Nếu hai Java wrappers dùng chung một pointer, lock của wrapper A không đồng bộ với lock của wrapper B.
- Nếu callback nhận pointer và chạy bất đồng bộ, cần đăng ký/ủy quyền lifetime kéo dài phù hợp.
- Nếu một thread gọi native `free` trực tiếp, Java lock không chặn được.
- Nếu một foreign library unload trước khi owner close, deallocator cũng có thể không còn hợp lệ.

Một protocol tốt hơn cho async: **stop accepting new borrows → wait active operations/callbacks → release owner once**. Các borrow leases có thể được đếm bằng refcount dưới mutex hoặc state machine. Không đóng arena/free buffer chỉ vì một `Future` vừa được tạo hoặc một request Java đã return.

### Không chia sẻ `JNIEnv*` giữa threads

`JNIEnv*` chỉ hợp lệ trong thread tương ứng. Khi native thread khác phải callback vào JVM, attach thread theo Invocation API để lấy `JNIEnv*` riêng và detach phù hợp. Các JNI local references cũng có lifetime theo frame/thread; nếu lưu Java object cho callback dài hạn, dùng `NewGlobalRef`/`DeleteGlobalRef` với lifecycle riêng. Global ref không thay thế ownership native pointer.

## 15. Phân biệt dữ liệu có thể copy với dữ liệu bắt buộc zero-copy

| Bối cảnh | Copy | Borrow/zero-copy |
| --- | --- | --- |
| Chuỗi/byte[] nhỏ, xử lý đồng bộ | Dễ hiểu lifetime, ít aliasing | Có thể tránh copy nhưng phải Release đúng và không giữ pointer |
| Native callback bất đồng bộ | Copy vào native-owned buffer có explicit free | Chỉ khi owner và active-borrow protocol rõ |
| Buffer lớn hiệu năng nhạy | Có chi phí copy, có thể dùng pool | Cần scope/lifetime, synchronization và deallocator đúng |
| Java caller cần giữ kết quả nhiều giờ | Trả Java array/object hoặc owner handle rõ | Không thể trả pointer JNI Get đã Release |
| C API trả allocated string | Copy vào Java String rồi gọi thư viện's free | Giữ raw pointer buộc Java quản lý native owner dài hạn |
| FFM dùng temporary native buffer | Arena confined/shared có close chính xác | Shared scope còn sống và native không giữ pointer sau close |

**Không có quy tắc rằng zero-copy luôn tốt hơn.** Chi phí copy của vài KiB có thể nhỏ hơn rủi ro giữ một vùng native lớn, pinning, GC pressure hoặc complexity của concurrency. Chọn dựa trên lifetime thực và benchmark đã đo.

## 16. Lỗi phổ biến và cách khắc phục

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `free` pointer từ `GetByteArrayElements` | Sai allocator/ownership, có thể crash | Gọi `ReleaseByteArrayElements` đúng cặp |
| `ReleaseStringChars` cho pointer `GetStringUTFChars` | Sai loại lease | Dùng `ReleaseStringUTFChars` |
| Không Release vì `isCopy == JNI_FALSE` | Giữ pin/lease quá lâu | Luôn Release khi Get thành công |
| Dùng `JNI_COMMIT` rồi coi buffer đã free | Lease còn mở nếu copy | Release cuối với `0`/`JNI_ABORT` |
| `DeleteLocalRef` thay `free` native block | JNI reference không sở hữu malloc block | Đúng deallocator của owner native |
| `NewDirectByteBuffer` rồi `free` ngay | Java ByteBuffer trỏ vào memory đã giải phóng | Giữ native owner còn sống đến khi mọi view xong |
| Cho rằng GC ByteBuffer tự `free` C malloc | Leak | Explicit owner `close`/native destroy |
| Gửi borrowed pointer vào hàm `adopt` | Callee có thể tự free vùng không thuộc nó | Copy hoặc transfer từ owner thật theo contract |
| Gọi `destroy_blob` hai lần | Double-free | Unique ownership, set handle 0, registry/state |
| Native function fail giữa chừng và cả hai bên cùng free | Heap corruption | Tài liệu hóa transfer on success/failure atomicity |
| Native function fail và không bên nào free | Leak | Caller retains ownership on error hoặc callee consumes always theo contract |
| Lưu JNI local ref cho thread khác | Ref hết hạn/sai thread | Global ref + thread attach hợp lệ |
| `Arena.close()` rồi C dùng raw pointer | Use-after-free | Wait active native calls, định nghĩa scope hợp lệ |
| Native C giữ pointer, Java dùng `Arena.ofAuto()` rồi bỏ owner | GC không biết C pointer là strong ref | Explicit lifetime/handshake, không dựa vào GC |
| Tin rằng `jlong` handle là an toàn từ client | Pointer forged/stale có thể crash | Opaque registry id/generation và kiểm tra ownership |
| Hai wrappers sở hữu một pointer | Double free hoặc UAF | Factory chỉ tạo một owner, hoặc shared refcount |
| Không kiểm tra lỗi cấp phát/exception | Return handle không hoàn chỉnh, leak | Cleanup trước transfer; không nuốt pending exception |

## 17. Checklist review contract giữa Java và C

**Trước khi công bố một native API**, mỗi pointer/handle cần có tài liệu:

1. **Direction:** Java → C hay C → Java?
2. **Type:** Java array/String, JNI reference, JNI elements lease, C heap, OS handle, direct ByteBuffer hay FFM segment?
3. **Ownership at entry:** Ai là owner trước lời gọi?
4. **Ownership at exit:** Ai là owner khi thành công? Khi thất bại?
5. **Borrow lifetime:** Chỉ trong lời gọi, chỉ trong callback hay sau một explicit release?
6. **Mutation:** Read-only, writable, copy-back mode có ý nghĩa gì?
7. **Size:** Có pointer + byte length; bytes, UTF-16 code units hay số phần tử?
8. **Allocator:** Dùng `free`/`delete`/`destroy`/JNI Release/`Arena.close` API nào?
9. **Null/error:** Null có nghĩa empty, failure hay ownership không được chuyển?
10. **Thread:** Owner có được chuyển thread không? JNI environment, lock/refcount, callbacks?
11. **Exceptions:** Mọi nhánh lỗi đã free/release những tài nguyên acquire trước đó chưa?
12. **Concurrency:** Có cơ chế ngăn free trong khi borrow đang được dùng?
13. **Multiple owners:** Có refcount thực sự hay chỉ hai biến trỏ cùng địa chỉ?
14. **Observability:** Có test leak/double-free, active-handle count, sanitizer/JNI checks phù hợp?
15. **Security:** Có thể gửi pointer giả/stale từ caller không? Có cần registry?
16. **Version/ABI:** Binary, pointer width, alignment, allocator và library module có nhất quán không?

Một contract ngắn viết kèm API có ích hơn lời hứa chung chung như "caller takes care of memory".

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `GetStringUTFChars` thành công và `isCopy == JNI_FALSE`. Native code có được bỏ `ReleaseStringUTFChars` không?

**Không.** `isCopy` mô tả implementation; nghĩa vụ kết thúc lease vẫn tồn tại. Pointer không được `free` bằng C allocator.

**Câu 2.** `NewDirectByteBuffer` bọc một `malloc` C. Java GC có tự `free` pointer ấy không?

**Không nên giả định.** JNI tạo view tới vùng native caller cung cấp; API phải có owner/lifetime và deallocator rõ. `ByteBuffer.allocateDirect` do JVM cấp có contract khác.

**Câu 3.** Hàm `create_blob()` trả `Blob *` và tài liệu yêu cầu `destroy_blob()`. Có thể thay bằng `free(blob)` không?

**Không.** Thư viện có thể dùng allocator riêng, đóng handles khác hoặc `new`. Tuân thủ đúng `destroy_blob`.

**Câu 4.** `adopt_blob(&p)` thất bại. Caller có phải free `p` không?

Theo policy **transfer only on success** được công bố ở ví dụ, thất bại giữ ownership ở caller và caller phải destroy. Nhưng với một thư viện khác, policy có thể là **consume always**; phải đọc contract cụ thể, không suy theo tên hàm.

**Câu 5.** `GetByteArrayElements` rồi `Release(..., JNI_COMMIT)` có chấm dứt quyền mượn không?

**Chưa** nếu elements là bản sao: `JNI_COMMIT` copy back nhưng không free buffer, cần một Release cuối. Nên chỉ dùng `JNI_COMMIT` khi cần tiếp tục dùng pointer theo contract.

**Câu 6.** Vì sao sau khi sửa Java `source[0]`, `borrowedSum` đổi kết quả nhưng `nativeChecksum` giữ nguyên?

Vì `borrowedSum` mượn nội dung Java array ở **mỗi lần gọi**, còn `nativeCopy` đã tạo một bản sao native độc lập và **chuyển ownership** sang Java wrapper.

**Câu 7.** Đặt `handle = 0` trong một wrapper `close()` có bảo đảm cả chương trình không double-free không?

**Không.** Nó giúp riêng wrapper đó idempotent. Nếu có nhiều wrappers cùng địa chỉ, C callbacks giữ pointer hoặc client có thể forging handle, cần registry/refcount/locking đầy đủ.

**Câu 8.** Dùng `Arena.ofConfined()` trả `MemorySegment` rồi đóng arena trước khi caller dùng có hợp lệ không?

**Không.** Scope đã đóng nên segment/view hết quyền truy cập; phải copy dữ liệu, hoặc chuyển thiết kế ownership cho caller với arena có lifetime phù hợp.

**Câu 9.** Java callback giữ một pointer borrowed để chạy 10 giây sau. Có hợp lệ không?

Chỉ khi API contract **cho phép retain** và có ownership/lifetime handshake bảo đảm owner vẫn sống. Borrowed chỉ trong lời gọi/callback thông thường **không** được tự kéo dài như vậy.

**Câu 10.** FFM `MemorySegment` có bounds/scope checks, vậy có bảo đảm pointer C thư viện cấp không bị free sớm không?

**Không.** Metadata của FFM không thay thế hợp đồng C allocator. Restricted reinterpret có thể khai báo nhầm size/lifetime; C vẫn có thể free ngoài kiến thức Java.

## 19. Tài liệu chính thức

- Oracle JNI Specification — [Get/Release primitive array elements, `JNI_ABORT` và `JNI_COMMIT`](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#getprimitivetypearrayelements-routines).
- Oracle JNI Specification — [String operations: `GetStringUTFChars` và `ReleaseStringUTFChars`](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#string-operations).
- Oracle JNI Specification — [Direct Byte Buffers, `NewDirectByteBuffer`/`GetDirectBufferAddress`](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#nio-support).
- Oracle JNI Specification — [JNI global/local references và lifetime](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html#global-and-local-references).
- Oracle Java SE 17 — [`AutoCloseable` và `try-with-resources`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html).
- Oracle Java SE 22 — [FFM `Arena`, ownership/scope và `close()`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- Oracle Java SE 22 — [FFM `MemorySegment`, bounds, scope và views](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- OpenJDK JEP 454 — [FFM finalized ở JDK 22](https://openjdk.org/jeps/454).

**Ghi nhớ:** *borrowed* nghĩa là **được dùng tạm nhưng không sở hữu**; *ownership transferred* nghĩa là **chủ mới có trách nhiệm hủy sau thời điểm chuyển giao xác định**; *caller-frees* nghĩa là **bên gọi phải dùng đúng deallocator theo contract của bên cấp phát**. JNI Get/Release là **một lease đặc biệt của JVM**, không phải malloc. Hãy ưu tiên **ownership duy nhất, lifetime rõ ràng, cleanup trên mọi nhánh lỗi và tuyệt đối không free vùng nhớ không thuộc mình**.