# Con trỏ trả về trong FFM: MemorySegment kích thước 0 và hợp đồng độ dài rõ ràng

Khi Java gọi thư viện C qua Foreign Function & Memory API (FFM) và nhận một giá trị kiểu `char *`, `int32_t *` hoặc `void *`, JVM thường **chỉ biết địa chỉ đầu tiên**, không biết có bao nhiêu byte thật sự được phép đọc, bộ nhớ thuộc về ai, hoặc nó còn sống đến khi nào. Trong FFM chuẩn từ **JDK 22**, một pointer được trả từ foreign function dưới `ValueLayout.ADDRESS` được Java biểu diễn thành **`MemorySegment` có `byteSize() == 0`**. Đây là ranh giới an toàn có chủ đích, không có nghĩa C đã cấp phát một buffer rỗng.

Để đọc nội dung đằng sau pointer, bạn phải có **hợp đồng độ dài** và **hợp đồng sở hữu/vòng đời** từ C API, xác minh cả hai, rồi mới mở rộng view bằng `reinterpret(...)`. Việc mở rộng là thao tác **restricted và không an toàn nếu khai báo sai**: FFM kiểm tra theo kích thước bạn *khai báo*, chứ không biết allocation thực sự lớn đến đâu. Một `reinterpret(1_000_000)` không khiến buffer native tự lớn thêm một triệu byte.

Bài thuộc nhóm **Con trỏ và sở hữu**, giải thích vì sao size bằng 0, phân biệt địa chỉ null với dữ liệu rỗng, các cách truyền độ dài, kiểm tra overflow/bounds, tạo scoped view, giải phóng native memory và tránh use-after-free. Cuối bài có **ví dụ Java 22+ + C11 hoàn chỉnh** cho hai tình huống: pointer mượn tới mảng `static const` có độ dài qua out-parameter, và pointer do `malloc` cấp phát phải gọi đúng hàm giải phóng. Các lệnh build cho Linux, macOS và Windows được tách rõ; mã Java 17/21 không dùng nguyên API này.

## 1. Zero-length pointer là “chưa biết kích thước”, không phải “mảng có 0 phần tử”

Một lời gọi FFM tưởng tượng tới C:

~~~c
/* Mảnh C minh họa một khai báo, chưa phải chương trình đầy đủ. */
const int32_t *get_items(int32_t *out_count);
~~~

Giả sử C trả địa chỉ `0x12340000` và ghi `*out_count = 3`. Khi Java nhận pointer với `ValueLayout.ADDRESS`, các thông tin phía FFM biết và **không biết** là:

| Thông tin | Có trong raw `MemorySegment`? | Ghi chú |
| --- | --- | --- |
| Địa chỉ pointer | Có, qua `address()` | Một native address có thể khác 0 |
| `byteSize()` | Có, nhưng bằng **0** | API không tự đo buffer C |
| Số phần tử | **Không** | Phải lấy từ `out_count`, return code, metadata hoặc hợp đồng khác |
| Kích thước mỗi phần tử | Không được suy từ pointer | Phải biết C type/ABI, ví dụ `int32_t` 4 byte |
| Số byte hợp lệ | **Không** | Cần tính `count * elementSize` đã kiểm tra |
| Read-only hay writable | Không được đảm bảo chỉ bởi `ADDRESS` | C `const` là hợp đồng API, không tự ép Java view read-only |
| Thời hạn còn sống | **Không** | Pointer có thể tới static data, malloc block, vùng tạm hay object do native quản lý |
| Hàm giải phóng | **Không** | Phải xác định `free`, `destroy_*`, không giải phóng, hoặc ownership transfer |
| Thread safety | Không | C có thể mutate/free từ thread khác |

Trong JDK 22, raw pointer segment loại này thường gắn với **global scope (always-alive)**, vì JVM chưa biết thời hạn native allocation. Điều đó **không có nghĩa** vùng C luôn sống. Nó chỉ nói Java không có thông tin để tự hết hạn raw address. Lấy một scoped view do bạn quản lý giúp ngăn truy cập Java sau khi arena đóng, nhưng **không** ngăn C tự giải phóng vùng nhớ sớm hơn.

~~~text
C:
    pointer p --------------------> [ 7 ][11 ][13 ]
                                          3 x int32_t
    *out_count = 3

FFM:
    raw = address p
    raw.byteSize() == 0        (không thể đọc phần tử)
             |
             | API hợp đồng: count=3, sizeof(int32_t)=4,
             | dữ liệu còn sống tới khi library bị unload
             v
    raw.reinterpret(12, arena, null)
             |
             v
    view.byteSize() == 12      (Java có thể bounds-check 0..11)

Không có bước nào hỏi JVM "buffer C thực sự có bao nhiêu byte?"
~~~

`MemorySegment` có size 0 có thể **truyền như opaque pointer** sang một foreign function khác nhận `ADDRESS`, chẳng hạn một hàm `free_items(pointer)`. Nhưng `raw.get(ValueLayout.JAVA_INT, 0)` không hợp lệ: 4 byte cần đọc vượt bounds 0, thường ném `IndexOutOfBoundsException`. Quy tắc cấm đọc ngay này là tính năng bảo vệ để người gọi phải thể hiện quyết định “tôi biết có bao nhiêu byte”.

## 2. Phân biệt bốn trường hợp thường bị lẫn

- **Null pointer:** `MemorySegment.NULL` mô tả địa chỉ 0; khi C trả `NULL` qua address layout, Java nhận biểu diễn địa chỉ null. Không dereference. Null có thể có nghĩa lỗi, không có dữ liệu hoặc một trường hợp hợp lệ **chỉ khi API quy định**.
- **Non-null pointer, `byteSize()==0`:** địa chỉ có thể trỏ tới cả mảng lớn, nhưng spatial bound của raw view chưa biết; phải hỏi/biết length trước khi đọc.
- **Buffer có length bằng 0:** API có thể cho phép return `NULL` hoặc một non-null sentinel; ở mức ứng dụng, có 0 phần tử. Không cần và không được đọc phần tử đầu tiên.
- **String có terminator NUL:** C string có thể được xác định bằng sentinel byte 0 thay vì độ dài out-parameter, nhưng Java vẫn **không biết vị trí NUL** chỉ nhờ một raw pointer. Đọc đến khi gặp NUL mà không có cap là một hành vi không thể bảo đảm an toàn.

`raw.address() == 0L` là cách kiểm tra địa chỉ null phù hợp với ví dụ native-address. Không lấy `raw.byteSize()==0` làm điều kiện “không có dữ liệu”, vì tất cả pointer trả về chưa có target layout đều có thể có size0.

Trong chương trình Java, `null` reference và `MemorySegment.NULL` cũng khác nhau. Một MethodHandle được khai báo carrier `MemorySegment.class` cho `ADDRESS`; đừng tự truyền `(MemorySegment)null` hoặc ép arbitrary integer thành pointer mà không hiểu contract. C `NULL` là giá trị pointer, không phải Java object reference `null`.

## 3. Năm kiểu hợp đồng độ dài cho C pointer

| Mẫu C API | Nơi lấy độ dài | Điều phải kiểm chứng |
| --- | --- | --- |
| `const T *get_items(size_t *out_count)` | Out-parameter ghi `count` | Hàm luôn khởi tạo count, đơn vị là **phần tử** hay byte, pointer còn sống bao lâu |
| `const void *get_data(size_t *out_bytes)` | Out-parameter ghi byte count | Không nhân thêm `sizeof(T)` khi count đã là byte |
| `size_t read_data(void *dst, size_t capacity)` | Giá trị trả về hoặc out-written | Không đọc quá capacity, phân biệt số byte thực ghi và byte cần có |
| `struct Buffer { void *data; size_t size; }` | Field `size` đi kèm pointer trong struct | Padding, alignment, ABI, pointer/data lifetime, ownership |
| `const T *get_fixed_array(void)` | Contract cố định, ví dụ chính xác 8 `T` | Versioning của native API, kích thước C `T` trên target |
| `const char *get_name(void)` | Sentinel NUL | Encoding, giới hạn scan tối đa, có thật terminator trong vùng hợp lệ |
| `void *malloc(size_t bytes)` | Kích thước caller đã yêu cầu | Khi thành công allocation đáp ứng request; caller phải free theo allocator family |
| `void *map_region(size_t *mapped_bytes)` | Native trả mapped length | Trang/bộ nhớ mapping, unmap đúng size và đúng owner |

**Câu hỏi đầu tiên luôn là “độ dài tính bằng đơn vị gì?”** Với `int32_t *` trả 3 phần tử, byte size là `3 * 4 = 12`. Với `char *` trả `out_bytes=3`, tổng là 3 byte, **không** 3 Java `char` (Java `char` có 2 byte/UTF-16 code unit). Với `size_t count`, dùng layout theo C ABI (32/64-bit) đúng hệ điều hành; không tự ép sang `int` rồi tin số còn nguyên.

Nếu API không cho length, không có sentinel/tập bounds đáng tin, và không có giới hạn bảo đảm khác, **không thể đọc an toàn tùy ý**. Cách sửa thường phải ở C interface: thêm out-parameter, hàm `get_size(handle)`, một struct `{pointer,length}`, hoặc API copy-into-buffer do Java cấp kèm capacity. “Đoán đến khi đọc được” không phải giải pháp.

### 3.1. Trường hợp count đi kèm pointer

~~~c
/* Mảnh minh họa contract C, không phải code chạy độc lập. */
const int32_t *get_values(int32_t *out_count);
/* Hợp đồng:
   - out_count non-NULL và được ghi trên mọi nhánh return.
   - count >= 0, tính bằng số phần tử int32_t.
   - count > 0 => pointer != NULL và trỏ tới ít nhất count phần tử.
   - nếu borrowed, caller KHÔNG free.
   - dữ liệu bất biến trong lúc caller đọc.
*/
~~~

Ở Java, lấy `out_count` từ một segment do `Arena` cấp, sau đó kiểm tra count và pointer. Đừng dùng `count` chưa được khởi tạo khi C return lỗi. Hãy quyết định rõ tình huống `count==0`: có thể trả kết quả rỗng mà không `reinterpret` hay dereference. Với count lớn, phải tính số byte bằng phép nhân kiểm tra overflow.

### 3.2. Trường hợp pointer chỉ là handle mờ

~~~c
typedef struct Context Context;
Context *context_open(void);
void context_close(Context *ctx);
int context_execute(Context *ctx, int value);
~~~

Nếu `Context` là opaque type và C chỉ cho phép truyền pointer trở lại các native functions, Java **không cần `reinterpret`** và không nên tự đọc memory phía sau. Một `MemorySegment` size0 là đại diện phù hợp cho handle `Context *`; `context_execute` nhận lại `ADDRESS` và `context_close` giải phóng theo contract.

Quan trọng: không phải *mọi pointer* là buffer. Không đưa con trỏ opaque tới `MemorySegment.get(JAVA_INT,0)` chỉ vì muốn xem “field đầu tiên”; layout của struct C có thể private, thay đổi theo version và không thuộc hợp đồng của Java.

## 4. Vì sao `reinterpret(...)` là thao tác nguy hiểm?

JDK 22 cung cấp những overload đáng chú ý:

~~~java
// Các chữ ký minh họa của API JDK 22:
MemorySegment reinterpret(long newSize);
MemorySegment reinterpret(long newSize, Arena arena,
                          Consumer<MemorySegment> cleanup);
MemorySegment reinterpret(Arena arena,
                          Consumer<MemorySegment> cleanup);
~~~

Đây là **mảnh khai báo API**, không phải code Java độc lập để copy vào class. `reinterpret(long)` đặt lại kích thước nhưng giữ scope hiện tại (raw address thường gắn global scope). `reinterpret(long,Arena,Consumer)` đặt **byte size mới và scope mới** theo arena, có thể đăng ký cleanup action nếu hợp đồng owner cho phép.

Các overload này là **restricted methods**. Nếu caller module không được cấp native access, JDK có thể ném `IllegalCallerException`. Khi byte size được khai sai, bounds checker của `MemorySegment` chỉ kiểm tra trong vùng **mới khai**, không thể kiểm chứng C allocation. Đọc `ptr.reinterpret(1024)` khi C chỉ cấp bốn byte vẫn có thể gây native memory corruption/JVM crash.

~~~java
// Mảnh minh họa: chỉ an toàn nếu C bảo đảm ít nhất 12 byte,
// pointer non-null, ABI int32_t khớp JAVA_INT và memory đang sống.
MemorySegment raw = /* pointer từ foreign function */;
MemorySegment view = raw.reinterpret(12L, arena, null);
int third = view.getAtIndex(ValueLayout.JAVA_INT, 2);
~~~

Những điều phải đúng **trước khi** lấy `third`:

1. Pointer không null.
2. C thật sự có tối thiểu 3 phần tử `int32_t` trong memory liên tiếp (ít nhất 12 byte).
3. `sizeof(int32_t)==4` và alignment phù hợp `JAVA_INT` trên ABI target.
4. Buffer còn sống, không bị free/realloc từ thread khác.
5. Caller đang ở thread hợp lệ của `arena`, scope chưa đóng.
6. Không có mutator concurrent gây data race theo ngôn ngữ C.
7. Việc `reinterpret` được cấp native access theo chính sách JDK.

Không có bước nào trong `reinterpret` tự thực hiện phần 2–4. Do đó “bọc pointer vào segment” không phải một phép bảo chứng an toàn của JVM cho dữ liệu bên ngoài.

### 4.1. Thay đổi scope giúp nhưng không thay hợp đồng native

Với `Arena.ofConfined()`, derived segment có thể được tạo bằng:

~~~java
MemorySegment bounded = raw.reinterpret(12, arena, null);
~~~

Sau `arena.close()`, các accesses Java vào `bounded` bị từ chối theo scope. Nhưng nếu C gọi `free(raw_pointer)` **trước** khi đóng arena, `bounded` vẫn có thể trông như alive mặc dù memory đã bị thu hồi: đây là use-after-free mà Java bounds/lifetime check không biết. **Thời điểm native free phải được phối hợp với Java scope.**

Tương tự, `reinterpret(12, arena, null)` **không free** dữ liệu C khi arena đóng, vì cleanup action là `null`. Nếu dữ liệu malloc được trả về cho Java sở hữu, bạn vẫn phải gọi native `destroy/free` đúng một lần. Có thể đăng ký cleanup action vào arena, nhưng chỉ khi chắc về allocator, thứ tự thư viện tồn tại, số lần free và quãng thời gian callback còn sử dụng pointer.

## 5. Trước khi mở rộng size: kiểm tra số phần tử, phép nhân và alignment

Công thức chuẩn cho mảng liên tiếp:

~~~text
byteCount = elementCount * elementByteSize
Điều kiện:
elementCount >= 0
elementCount <= LIMIT theo contract
elementByteSize > 0
byteCount tính bằng phép nhân không overflow
pointer != NULL nếu elementCount > 0
vùng C chứa >= byteCount byte và sống trong lúc truy cập
~~~

Với Java 22+:

~~~java
// Mảnh minh họa, đòi hỏi count nằm trong range đã kiểm tra.
long bytes = Math.multiplyExact(
        (long) count, ValueLayout.JAVA_INT.byteSize());
~~~

`ValueLayout.JAVA_INT.byteSize() == 4`; `count==3` cho `bytes==12`. Dùng `Math.multiplyExact` giúp bắt overflow Java khi code thay đổi nhận count kiểu `long` hoặc element layout phức tạp hơn. Với count kiểu `int` không âm, nhân 4 bằng `long` cũng không vượt 64-bit, nhưng vẫn cần **giới hạn nghiệp vụ/cap** (ví dụ tối đa 1.000.000 phần tử) để tránh mượn cả gigabyte vùng nhớ trên một pointer không đáng tin.

Nếu count được C xuất qua `size_t`, không thể luôn đọc bằng `ValueLayout.JAVA_INT` hoặc `JAVA_LONG`. Đối chiếu `Linker.nativeLinker().canonicalLayouts().get("size_t")` trên target, và kiểm tra miền không dấu trước khi chuyển sang Java count/byteCount. Trên Windows x64, C `long` thường 32-bit còn Java `long` 64-bit; đừng dùng “cùng tên long” để chọn descriptor.

### 5.1. Alignment là nghĩa vụ riêng

Pointer có thể trỏ vào vùng packed/unaligned. `getAtIndex(ValueLayout.JAVA_INT,i)` yêu cầu địa chỉ tương thích alignment của layout. Khi C API thực sự bảo đảm `int32_t *` đến một mảng bình thường được allocate hợp lệ, alignment của phần tử thường phù hợp. Với wire format packed hoặc bytes ở offset bất thường, có thể cần `JAVA_INT_UNALIGNED` **nếu dữ liệu thật sự không aligned**, nhưng vẫn phải thỏa bounds và byte order đúng.

Không dùng `*_UNALIGNED` để bỏ qua lỗi “count sai” hoặc pointer không hợp lệ. Layout unaligned giảm ràng buộc căn chỉnh của Java access; nó không mở rộng C allocation.

### 5.2. Khi dùng struct và stride

Nếu C trả `struct Item *items`, cần cả count lẫn **`sizeof(struct Item)`** và field offsets theo ABI. Không thể tự giả định `itemSize == tổng kích thước các field` vì compiler có thể thêm padding. Khi có struct array, `byteCount = count * sizeof(Item)`, không nhất thiết bằng count nhân riêng size của trường đầu tiên. Dùng `MemoryLayout.structLayout` với padding đúng, kiểm tra `offsetof` và `sizeof` từ C compiler.

## 6. Ownership: ai được đọc, ai được sửa và ai phải giải phóng?

| Kiểu pointer | Ai sở hữu bộ nhớ | Java được làm gì? | Dọn thế nào? |
| --- | --- | --- | --- |
| **Borrowed static** | Thư viện C; `static const` sống trong thời gian binary còn loaded | Đọc trong lúc library sống; không mutate/free | Java không gọi `free`; bảo đảm library được giữ loaded khi đọc |
| **Borrowed view từ object/handle** | C object hoặc native context | Chỉ đọc/ghi theo contract; không dùng sau destroy/realloc | Đóng owner handle sau khi mọi view/callback hoàn tất |
| **Caller-owned malloc block** | Quyền sở hữu chuyển sang Java caller | Đọc/ghi đúng cap; giải phóng đúng một lần | Gọi `destroy_*`/`free_*` đúng thư viện allocator |
| **Transfer-to-native** | C nhận ownership sau khi Java gọi API | Không còn sử dụng/giải phóng từ Java sau transfer | Theo native contract; Java phải đánh dấu handle đã chuyển |
| **Pointer vào buffer do Arena cấp** | Java arena sở hữu memory | Native chỉ mượn trong khoảng hợp lệ | `Arena.close()`, sau khi native dừng dùng pointer |
| **Opaque context pointer** | Native API sở hữu context qua create/destroy | Truyền opaque handle tới C; không tự dereference | `context_destroy` theo contract |

**`Arena.close()` không có nghĩa “`free` tất cả các địa chỉ nhìn thấy trong arena”.** Nó giải phóng vùng memory do arena quản lý và chạy cleanup actions được đăng ký thích hợp. Nếu C dùng `malloc` và trả pointer, chỉ tạo `raw.reinterpret(bytes, arena, null)` không có cleanup của malloc; vẫn phải gọi destroy/free do C API yêu cầu.

**Không dùng Java `Cleaner` như đường cleanup duy nhất** khi tài nguyên cần đóng đúng hạn. `try-with-resources` và `close()` trong API Java là thiết kế xác định hơn, đặc biệt với socket/DB/GPU resources, native threads và callbacks. Cleaner có thể làm fallback với state/ownership riêng, nhưng không có lịch GC bảo đảm.

### 6.1. Vì sao thư viện C nào cấp thì nên C đó giải phóng?

C library có thể dùng allocator custom, CRT khác trên Windows, arena riêng, slab/pool hoặc native API có reference count. Gọi một `free` không khớp allocator có thể gây undefined behavior. Một contract tốt nên cung cấp cặp:

~~~c
/* Mảnh C API minh họa (không phải toàn chương trình). */
int32_t *create_items(int32_t count);
void destroy_items(int32_t *data);
~~~

Java giữ opaque/raw pointer để gửi lại `destroy_items` bằng `ValueLayout.ADDRESS`. Không bao giờ free hai lần; sau destroy, các derived segments vẫn có thể mang cùng địa chỉ trong representation nhưng **không còn hợp lệ để dereference**.

## 7. Ví dụ hoàn chỉnh: một thư viện C với cả borrowed và owned pointer

Ta viết C library `pointers` có hai API:

1. `borrow_numbers(int32_t *out_count)` trả pointer tới `static const int32_t[3] = {7,11,13}`, đồng thời ghi `out_count = 3`. Java **không free** con trỏ.
2. `create_numbers(int32_t count)` cấp một mảng `malloc` gồm `count` phần tử (trong ví dụ có `count=4`), điền `10,20,30,40`; Java phải gọi `destroy_numbers(ptr)` đúng một lần.

Đây là hai tình huống phổ biến nhưng khác nhau về lifetime. Java 22+ dùng FFM downcall; vì C là C ABI thuần nên không có `JNIEnv`, `jobject` hay generated JNI header.

Cấu trúc thư mục:

~~~text
ffi-returned-pointer/
├── native/
│   └── pointers.c
├── src/
│   └── PointerLengthDemo.java
└── build/
    ├── classes/
    └── lib/
~~~

### 7.1. File C11 đầy đủ: `native/pointers.c`

~~~c
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>

#if defined(_WIN32)
#define API_EXPORT __declspec(dllexport)
#else
#define API_EXPORT __attribute__((visibility("default")))
#endif

/* Hợp đồng: data của thư viện, read-only, count=3, không free.
   Chỉ hợp lệ khi binary của thư viện vẫn loaded. */
API_EXPORT const int32_t *borrow_numbers(int32_t *out_count) {
    static const int32_t ITEMS[3] = {7, 11, 13};

    if (out_count == NULL) {
        return NULL;
    }

    *out_count = 3;
    return ITEMS;
}

/* Hợp đồng: count phải từ 1..1000000.
   Khi thành công trả buffer đúng count phần tử.
   Ownership chuyển cho caller, gọi destroy_numbers đúng một lần. */
API_EXPORT int32_t *create_numbers(int32_t count) {
    if (count <= 0 || count > 1000000) {
        return NULL;
    }

    if ((size_t) count > SIZE_MAX / sizeof(int32_t)) {
        return NULL;
    }

    int32_t *data = malloc((size_t) count * sizeof *data);
    if (data == NULL) {
        return NULL;
    }

    for (int32_t i = 0; i < count; ++i) {
        data[i] = (i + 1) * 10; /* max count giới hạn tránh overflow */
    }
    return data;
}

API_EXPORT void destroy_numbers(int32_t *data) {
    free(data);
}
~~~

**Hợp đồng C cần đọc kỹ:**

- `borrow_numbers` yêu cầu `out_count != NULL`; khi thành công nó ghi chính xác ba phần tử và trả con trỏ non-null tới dữ liệu `static const`. Java được đọc nhưng không write, không gọi `destroy_numbers` trên pointer borrowed.
- `create_numbers` trả `NULL` khi count ngoài 1..1.000.000 hoặc cấp phát lỗi; không có “mảng rỗng malloc(0)” trong API mẫu. Khi non-null, vùng memory chứa **đúng count số `int32_t`**, đủ liên tục và aligned. `count=4` tạo 10,20,30,40. Đã kiểm tra `SIZE_MAX / sizeof(int32_t)` trước phép nhân size.
- `destroy_numbers` là cặp release duy nhất dành cho pointer **do `create_numbers` trả**. `free(NULL)` trong C là hợp lệ, nhưng Java vẫn nên quản lý ownership để không gọi destroy nhầm borrowed pointer hoặc double-free.
- C `int32_t` có đúng 32 bit theo `stdint.h` nếu được hỗ trợ; Java dùng `ValueLayout.JAVA_INT` cho 4 byte trên ABI triển khai. Các layout structs, `size_t` hoặc C `long` của API khác phải được đối chiếu riêng.
- Trong API này, `create_numbers` không tự lưu pointer cho thread khác và `borrow_numbers` không thay đổi dữ liệu static. Do đó Java có thể đọc các phần tử trong một scope xác định mà không cần native synchronization riêng.

Mã trên là **thư viện C đầy đủ**, không có `main`; hãy biên dịch thành `.so`/`.dylib`/`.dll`. Không cần `-I"$JAVA_HOME/include"` vì đây là C ABI thuần, không dùng JNI header.

### 7.2. Java JDK 22+: `src/PointerLengthDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class PointerLengthDemo {
    private static final int MAX_ELEMENTS = 1_000_000;

    private PointerLengthDemo() {
    }

    private static long checkedBytes(int count) {
        if (count < 0 || count > MAX_ELEMENTS) {
            throw new IllegalArgumentException("invalid element count");
        }
        return Math.multiplyExact(
                (long) count, ValueLayout.JAVA_INT.byteSize());
    }

    public static void main(String[] args) throws Throwable {
        Path library = Path.of("build", "lib",
                System.mapLibraryName("pointers")).toAbsolutePath();

        try (Arena libraryArena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, libraryArena);

            // const int32_t *borrow_numbers(int32_t *out_count)
            MethodHandle borrow = linker.downcallHandle(
                    symbols.find("borrow_numbers").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.ADDRESS,
                            ValueLayout.ADDRESS));

            // int32_t *create_numbers(int32_t count)
            MethodHandle create = linker.downcallHandle(
                    symbols.find("create_numbers").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT));

            // void destroy_numbers(int32_t *data)
            MethodHandle destroy = linker.downcallHandle(
                    symbols.find("destroy_numbers").orElseThrow(),
                    FunctionDescriptor.ofVoid(ValueLayout.ADDRESS));

            // PHẦN A: borrowed pointer có chiều dài từ out-parameter.
            try (Arena readScope = Arena.ofConfined()) {
                MemorySegment outCount =
                        readScope.allocate(ValueLayout.JAVA_INT);
                MemorySegment raw =
                        (MemorySegment) borrow.invokeExact(outCount);

                int count = outCount.get(ValueLayout.JAVA_INT, 0);
                long byteCount = checkedBytes(count);

                if (count == 0) {
                    throw new IllegalStateException(
                            "demo expected 3 elements");
                }
                if (raw.address() == 0L) {
                    throw new IllegalStateException(
                            "null pointer with positive count");
                }

                System.out.println(
                        "borrowedRawSize=" + raw.byteSize());
                System.out.println("borrowedLength=" + count);

                // C đã bảo đảm count int32_t và static lifetime.
                MemorySegment view =
                        raw.reinterpret(byteCount, readScope, null);

                StringBuilder values = new StringBuilder();
                long total = 0;
                for (int i = 0; i < count; ++i) {
                    int value =
                            view.getAtIndex(ValueLayout.JAVA_INT, i);
                    if (i != 0) {
                        values.append(',');
                    }
                    values.append(value);
                    total += value;
                }
                System.out.println("borrowedValues=" + values);
                System.out.println("borrowedSum=" + total);
                // KHÔNG destroy/free raw: C vẫn sở hữu static data.
            }

            // PHẦN B: owned pointer cấp bằng malloc, phải release.
            try (Arena ownedScope = Arena.ofConfined()) {
                int count = 4;
                MemorySegment raw =
                        (MemorySegment) create.invokeExact(count);

                if (raw.address() == 0L) {
                    throw new IllegalStateException(
                            "native allocation failed");
                }

                boolean released = false;
                try {
                    long byteCount = checkedBytes(count);
                    System.out.println(
                            "ownedRawSize=" + raw.byteSize());
                    System.out.println("ownedLength=" + count);

                    MemorySegment view =
                            raw.reinterpret(byteCount, ownedScope, null);

                    long total = 0;
                    for (int i = 0; i < count; ++i) {
                        total +=
                                view.getAtIndex(ValueLayout.JAVA_INT, i);
                    }
                    System.out.println("ownedSum=" + total);
                } finally {
                    // Pointer raw có thể size0 nhưng hợp lệ cho ADDRESS.
                    // Không được sử dụng view sau lời gọi destroy này.
                    destroy.invokeExact(raw);
                    released = true;
                }
                System.out.println("released=" + released);
            }
        }
    }
}
~~~

**Tính runnable:** đây là một tệp Java hoàn chỉnh, không có package; class và filename khớp. Dùng `JDK 22+`. Vì `main` gọi `MethodHandle.invokeExact`, khai báo `throws Throwable` tránh xử lý checked throwable riêng trong ví dụ. Các native call signatures chính xác: `ADDRESS` ánh xạ Java carrier `MemorySegment`, `JAVA_INT` là `int`; `destroy` trả `void`.

**Tại sao có hai arena?** `libraryArena` quản lý lifetime của `SymbolLookup.libraryLookup` và các symbols/thư viện; nó **sống suốt** hai phần sử dụng native pointers, nên code C và `static const` chưa bị dỡ. `readScope` đặt deadline truy cập cho borrowed view. `ownedScope` đặt deadline cho owned view; nó **không** free C memory khi dùng cleanup `null`. `destroy.invokeExact(raw)` ở `finally` thực hiện đúng C free trước khi scope/lookup được đóng.

**Tại sao dùng `raw` cho destroy thay vì `view`?** C `destroy_numbers` cần địa chỉ gốc do `malloc` trả. `raw` vẫn là một segment size0 mang cùng address và có thể được truyền như `ADDRESS`. Truyền vùng cắt sai offset hoặc pointer đã advance khác địa chỉ gốc tới `free` là sai. Trong ví dụ không có thao tác slice pointer nên cả hai có cùng address, nhưng nguyên tắc vẫn là giữ riêng **base allocation pointer** cho cleanup.

**Lưu ý về tính an toàn:** Sau `destroy.invokeExact(raw)`, một view Java dù còn trong `ownedScope` không nên được dereference. Scope check không tự biết C free đã xảy ra. Ví dụ không cho `view` thoát khỏi khối `try/finally`; trong ứng dụng production, đóng gói pointer/view vào `AutoCloseable` có state chống use-after-close hoặc dùng arena cleanup action phù hợp để buộc lifetime Java sát lifetime C.

## 8. Lệnh biên dịch và chạy trên ba hệ điều hành

Chạy các lệnh từ thư mục gốc `ffi-returned-pointer`. Yêu cầu JDK **22 trở lên** để compile `java.lang.foreign` bản chuẩn, compiler C có `stdint.h`/`int32_t` và kiến trúc native library đúng với JVM. Các lệnh Java dùng classpath, nên cấp quyền native access cho **unnamed module**:

~~~sh
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes PointerLengthDemo
~~~

`--enable-native-access=ALL-UNNAMED` cần thiết vì `libraryLookup`, `downcallHandle` và `reinterpret` là các restricted operations. Với **named module**, dùng tên module cụ thể. Không cần `--enable-preview` trên JDK 22+. Java 17 (FFM incubator) và Java 21 (FFM preview) không chạy nguyên code này.

### 8.1. Linux (GCC hoặc Clang)

~~~sh
mkdir -p build/classes build/lib

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  native/pointers.c -o build/lib/libpointers.so

javac -d build/classes src/PointerLengthDemo.java

java --enable-native-access=ALL-UNNAMED \
  -cp build/classes PointerLengthDemo
~~~

### 8.2. macOS (Clang)

~~~sh
mkdir -p build/classes build/lib

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -dynamiclib \
  native/pointers.c -o build/lib/libpointers.dylib

javac -d build/classes src/PointerLengthDemo.java

java --enable-native-access=ALL-UNNAMED \
  -cp build/classes PointerLengthDemo
~~~

### 8.3. Windows x64 (MSVC Developer Command Prompt)

~~~bat
mkdir build\classes
mkdir build\lib

cl /nologo /W4 /O2 /LD native\pointers.c ^
  /link /OUT:build\lib\pointers.dll

javac -d build\classes src\PointerLengthDemo.java

java --enable-native-access=ALL-UNNAMED ^
  -cp build\classes PointerLengthDemo
~~~

Các dòng Windows dùng **Command Prompt**, dấu `^` nối dòng. Chạy trong Visual Studio Developer Command Prompt đã cấu hình `cl` cho đúng x64 target. `System.mapLibraryName("pointers")` trả tên file phù hợp platform (thường `libpointers.so`, `libpointers.dylib` hoặc `pointers.dll`); Java tự dựng **đường dẫn tuyệt đối** tới file đã build. Đổi phần mở rộng của một binary không thay đổi ABI của nó.

### 8.4. Stdout kỳ vọng

Với native binary đúng ABI và source trên, stdout chính xác là:

~~~text
borrowedRawSize=0
borrowedLength=3
borrowedValues=7,11,13
borrowedSum=31
ownedRawSize=0
ownedLength=4
ownedSum=100
released=true
~~~

Lý do: con trỏ trả về (không có target layout) có segment size0; `borrow_numbers` ghi count3 và cung cấp 7+11+13=31; `create_numbers(4)` cấp 10+20+30+40=100; `finally` gọi đúng `destroy_numbers` và in kết quả sau đó. Mã không in địa chỉ pointer, vì địa chỉ thay đổi theo process/ASLR. Stdout này được suy ra từ source; muốn xác nhận runtime phải thật sự chạy compiler/Java trên platform mục tiêu.

### 8.5. Kiểm tra exported symbols

Linux:

~~~sh
nm -D --defined-only build/lib/libpointers.so
~~~

Cần thấy:

~~~text
borrow_numbers
create_numbers
destroy_numbers
~~~

Trên macOS dùng `nm -gU build/lib/libpointers.dylib` (Mach-O thường có dấu `_` trước tên); trên Windows dùng `dumpbin /exports build\lib\pointers.dll`. Nếu Java báo không tìm thấy symbol, kiểm tra export macro, tên function/ABI đúng, đường dẫn thư viện và compiler architecture. Nếu `UnsatisfiedLinkError` khi load, đó không phải một dấu hiệu `byteSize` của pointer bị sai — chương trình còn chưa gọi thành công C.

## 9. Vì sao không thể “lấy kích thước bằng cách đọc cho đến khi lỗi”?

Một hiểu lầm thường gặp: vì `MemorySegment` ném `IndexOutOfBoundsException` khi truy cập quá kích thước, ta có thể `reinterpret` thành kích thước rất lớn rồi quét đến khi bắt exception. **Không đúng.**

Bounds check chỉ áp dụng **đối với số byte bạn đã cấp vào `reinterpret`**. Nếu C allocation thực tế là 12 byte mà bạn khai 1.000.000 byte, Java tin cửa sổ 1.000.000 byte được cho phép; đọc byte thứ 13 có thể đi sang vùng không thuộc allocation, đọc dữ liệu nhạy cảm hoặc crash process mà **không** gây exception có thể bắt được. Java không có thông tin allocator để tự kiểm tra “12 byte là điểm kết thúc thật”.

~~~text
C thực sự cấp:       [ 0 .......... 11 ]  (12 byte)
Java khai sai:       [ 0 ................................ 999999 ]
                                      ^ từ 12 trở đi là unsafe
bounds checker Java: chỉ biết vùng 0..999999, không biết 12
~~~

Nếu API chỉ trả `void*` không ghi độ dài, không cung cấp cách lấy length và không có sentinel/metadata bảo đảm, cách thiết kế đúng là thay đổi C API hoặc wrapper. Không thể viết một “generic safe pointer length detector” trên raw address. Các công cụ C debugger/OS memory maps cũng không thay hợp đồng allocation length; một vùng mapped có thể lớn hơn allocation mà app thực sự được phép dùng.

### 9.1. Pointer+length cũng phải cùng một snapshot nhất quán

Ngay cả khi C trả `pointer` cùng `count`, hai giá trị có thể không còn cùng hiệu lực nếu native thread khác vừa `realloc`/`free` hoặc thay đổi buffer. Contract cần bảo đảm:

- Pointer không đổi cho đến khi caller đọc xong, hoặc có lock/retain-release bảo vệ.
- Count đúng **snapshot** của buffer ấy, không phải count của buffer mới.
- Không có writer concurrent theo cách vi phạm data-race rules.
- Ownership không bị chuyển đi hoặc callback không tự giải phóng buffer giữa chừng.

Một pattern thường dùng cho dữ liệu thay đổi là API `copy_into(dst,capacity)` do Java cấp buffer, hoặc handle có hàm `retain/release`, thay vì borrowed pointer không được bảo vệ.

## 10. Khi pointer tới char buffer hoặc C string

Hợp đồng cho `char *` thường dễ sai hơn vì có nhiều cách đếm:

| Dữ liệu | Length đúng | Mối nguy |
| --- | --- | --- |
| `unsigned char *bytes` + `size_t len` | Số **byte**, có thể chứa `0x00` | Dùng `strlen` sẽ cắt tại NUL đầu |
| `char *utf8` + `byte_len` | Số byte UTF-8 | Không phải `String.length()` của Java (UTF-16 units) |
| `char *cstr` NUL-terminated | Số byte trước terminator | Phải có terminator trong vùng hợp lệ và limit quét |
| `uint16_t *utf16` + `unit_count` | Số code units 16-bit | Non-BMP code point cần hai units |
| `void *blob` + `size_t blob_bytes` | Payload size | Không được suy từ bytes trông như string |

Nếu C API có pointer + **byte length** thì nên tạo `MemorySegment` size đúng byteLength, sau đó copy/giải mã bằng charset/decoder có chính sách xử lý dữ liệu lỗi. Nếu C API trả C string NUL-terminated mà **không hề có giới hạn tối đa được chứng thực**, một cuộc quét NUL vẫn là truy cập native không có bảo đảm bounds. Cách tốt nhất là thay API để có `length` hoặc `copy_into`. Với native string đã biết tối đa 256 byte và C bảo đảm terminator trong phạm vi ấy, mới có thể mở view có cap256 rồi tìm NUL **trong 256 byte đó** (sau khi xác nhận allocation thật sự đủ 256 byte hoặc contract cam kết cap hợp lệ).

Đừng dùng JNI `GetStringUTFLength` để đo trực tiếp một `char*` từ FFM. JNI Modified UTF-8 khác UTF-8 chuẩn ở U+0000 và supplementary Unicode. FFM pointer return không tự tuyên bố encoding; length của Java `String`, byte count của C buffer và terminator là ba khái niệm độc lập.

### 10.1. API copy-into-buffer: giảm nhu cầu `reinterpret`

Một thiết kế thay thế:

~~~c
/* Mảnh C API minh họa, không phải file chạy độc lập. */
size_t copy_bytes(unsigned char *dst, size_t capacity);
/* Trả số byte thực ghi, <= capacity; hàm không lưu dst sau return.
   Cần quy định lỗi/đầu ra khi dst=NULL,capacity=0. */
~~~

Java cấp buffer bằng `Arena.allocate(capacity)` và truyền `MemorySegment` vào C. Khi C function tuân thủ capacity, Java đã biết chính xác vùng nhớ mình sở hữu và có thể đọc trong số byte được ghi mà không reinterpret pointer trả về. Tuy nhiên phải kiểm tra C không ghi quá capacity; FFM không ngăn một foreign function sai contract ghi tràn từ bên trong C.

## 11. `AddressLayout.withTargetLayout(...)`: hữu ích khi kích thước cố định

JDK 22 còn có `AddressLayout.withTargetLayout(MemoryLayout)`, một **restricted** API cho phép nói trước loại dữ liệu con trỏ trỏ tới. Ví dụ một field trong C struct luôn là pointer tới **4 giá trị int32_t**:

~~~java
// Mảnh Java minh họa, không phải chương trình độc lập.
AddressLayout fourInts = ValueLayout.ADDRESS.withTargetLayout(
        MemoryLayout.sequenceLayout(4, ValueLayout.JAVA_INT));

MemorySegment p = structSegment.get(fourInts, pointerFieldOffset);
// Khi đọc địa chỉ bằng layout này, target có size 4*4 = 16 byte.
int last = p.getAtIndex(ValueLayout.JAVA_INT, 3);
~~~

Cần imports `java.lang.foreign.AddressLayout`, `java.lang.foreign.MemoryLayout` và `ValueLayout`. Đoạn này giả định `structSegment` là segment hợp lệ chứa pointer field, `pointerFieldOffset` đúng ABI và C **cam kết** ít nhất 4 ints sống đủ lâu. `withTargetLayout` tự đặt size theo target layout **khi đọc pointer** nhưng không thể thẩm định C allocation thực tế. Nếu length là **dynamic**, `reinterpret(bytes, arena, null)` sau khi đọc length rõ ràng và xác minh thường dễ kiểm soát hơn.

Không dùng target layout lớn vô hạn để “bật quyền đọc” memory tùy ý; restricted API vẫn có thể làm JVM crash khi contract sai. Target layout cũng không giải quyết ownership hoặc free.

### 11.1. Phân biệt function pointer và data pointer

`SymbolLookup.find("function")` cũng trả một zero-length segment biểu diễn **địa chỉ symbol**. Trường hợp này dùng `Linker.downcallHandle(symbol, FunctionDescriptor...)` để gọi hàm C; **không** `reinterpret` rồi `get(JAVA_INT,0)` trên code address. Với C function pointer trả về từ API, phải xây descriptor/handle đúng calling convention và giữ library loaded. Với **data pointer**, giải pháp là length/layout/ownership. Dù cả hai được mô tả bằng `ADDRESS`, mục đích và an toàn hoàn toàn khác.

## 12. Kiểm tra trước khi đọc: một protocol ngắn gọn

~~~text
1) C API specification:
   pointer type, length unit, allowed null, mutability, owner, lifetime
                      |
                      v
2) FFM downcall đúng FunctionDescriptor và target ABI
                      |
                      v
3) Lấy raw MemorySegment (thường byteSize=0) cùng length
                      |
                      v
4) Kiểm tra lỗi trả về / NULL / count âm hoặc quá lớn
                      |
                      v
5) Tính byteCount bằng checked multiplication
                      |
                      v
6) Chứng minh buffer C thực sự đủ bytes và chưa bị free
                      |
                      v
7) raw.reinterpret(byteCount, arena, cleanup nếu phù hợp)
                      |
                      v
8) Đọc/ghi đúng ValueLayout, alignment, byte order, index
                      |
                      v
9) Dừng mọi users/callbacks, free đúng một lần nếu owned
                      |
                      v
10) Không dùng view/handle sau free hay arena.close()
~~~

Ví dụ `checkedBytes` trong code hoàn chỉnh kiểm tra cả `count < 0` và ngưỡng 1.000.000. Nó không chỉ tránh overflow mà còn định nghĩa limit nghiệp vụ. Count lấy từ C được xem là **dữ liệu phải xác thực**, không vì nó do native code trả ra mà được mặc nhiên tin là hợp lý. Nếu native bị lỗi hoặc thư viện thay version, guard Java giúp hạn chế hậu quả ở nhiều đường lỗi, nhưng vẫn không thay native memory safety.

Một quy tắc quan trọng về native out-parameter: dùng `ValueLayout.JAVA_INT` cho C `int32_t*`, không dùng `ADDRESS` rồi đọc địa chỉ của buffer output như số nguyên. `outCount = arena.allocate(ValueLayout.JAVA_INT)` tạo vùng Java sở hữu đủ 4 byte, C ghi vào đó. Pointer **được trả về** là giá trị `MemorySegment` riêng; length ở `outCount.get(JAVA_INT,0)`. Không cộng địa chỉ hoặc nhầm hai con trỏ này.

## 13. Những lỗi phổ biến và triệu chứng

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| `raw.byteSize()==0` => tưởng C trả mảng rỗng | Mất dữ liệu, hiểu sai API | Size0 nghĩa là unknown extent, đọc count riêng |
| `raw.get(JAVA_INT,0)` khi raw size0 | `IndexOutOfBoundsException` | Chỉ đọc sau khi có length và bounded view |
| `raw.reinterpret(Long.MAX_VALUE)` để tránh bounds check | Truy cập memory ngoài allocation, crash/corruption | Chỉ reinterpret bytes được C contract chứng thực |
| Đọc 10 phần tử vì “thường API trả 10” | Version/ABI đổi khiến out-of-bounds | API trả count hoặc fixed count được tài liệu bảo đảm |
| Dùng byte count như element count | Vượt vùng gấp `sizeof(T)` | Ghi rõ đơn vị; nhân chỉ với element count |
| Dùng `count * size` kiểu int trước khi cast long | Integer overflow trước khi kiểm tra | Dùng long + `Math.multiplyExact` |
| Pointer C `NULL` mà count>0 vẫn reinterpret | Null dereference/crash | Kiểm tra pointer và error contract trước |
| `count==0` luôn đọc phần tử 0 để xem “sentinel” | Truy cập ngoài vùng rỗng | Xử lý rỗng mà không dereference |
| `Arena.close()` được xem là C `free` tự động | Native heap leak | Gọi matching destroy hoặc đăng ký cleanup đúng |
| Gọi destroy trên borrowed `static const` pointer | Invalid free/undefined behavior | Borrowed pointer không free |
| Gọi destroy hai lần | Double-free/corruption | Một owner, state idempotent, clear handle |
| Dùng derived view sau C free | Use-after-free dù segment scope còn alive | Đồng bộ free với users; không lộ view sau close |
| Đóng `libraryArena` khi vẫn còn function pointer/borrowed view | Dangling pointer/code không còn loaded | Library lifetime phải bao toàn bộ khoảng dùng |
| C realloc buffer nhưng Java giữ view cũ | Pointer có thể đã đổi, length cũ vô hiệu | Version/lock/retain hoặc copy-into-buffer |
| Pointer trỏ packed int, Java dùng aligned `JAVA_INT` | Alignment exception/sai ABI | Dùng layout thật theo contract, không “fix” bừa |
| C `size_t` trên Windows x64 đọc qua `JAVA_INT` | Truncated count, sai byteCount | Dùng ABI canonical layout cho `size_t` |
| `char*` UTF-8 dùng Java `String.length()` để tính byte | Cắt/misread Unicode | Dùng byte-length theo đúng encoding |
| Quên `--enable-native-access` với restricted APIs | `IllegalCallerException`/runtime policy | Cấp quyền đúng named hoặc unnamed module |
| Dựa vào `MemorySegment.NULL.byteSize()==0` để phát hiện null | Mọi raw pointer cũng có size0 | Kiểm tra `address()==0L` theo context |
| Gọi `free` từ thư viện/CRT sai allocator | Heap corruption, nhất là trên Windows | Dùng `destroy_numbers` từ chính C API |
| Nhầm `structLayout` tự chèn padding | Sai offset/stride, native lỗi | Khai báo padding, đo `sizeof/offsetof` bằng compiler |

### 13.1. Bốn loại lỗi cần tách riêng

- **Spatial bounds:** `IndexOutOfBoundsException` khi đọc ngoài phạm vi segment **mà Java đã biết**. Nếu kích thước bạn khai phóng đại so với C allocation, kiểm tra này không cứu được.
- **Scope lifetime:** `IllegalStateException` khi truy cập segment có arena đã đóng. Một native `free` riêng có thể xảy ra **trước** thời điểm này và không tự cập nhật scope.
- **Alignment/thread:** `IllegalArgumentException` hoặc `WrongThreadException` ở những trường hợp truy cập không phù hợp layout hoặc confined arena.
- **Native-access/ABI:** `IllegalCallerException` nếu thiếu quyền restricted operations; sai C ABI có thể gây corruption/JVM crash, không nhất thiết ném Java exception.

Đừng thử catch `IndexOutOfBoundsException` quanh một pointer bị reinterpret quá rộng để coi là an toàn: đọc memory native không hợp lệ không có cam kết sẽ tạo Java exception có thể catch.

## 14. Ma trận kiểm thử pointer contract

| Tình huống | Kết quả kỳ vọng | Cần xác nhận |
| --- | --- | --- |
| C trả 3 ints qua `borrow_numbers` | Raw size0, count3, sum31 | Out-parameter và pointer cùng snapshot |
| C trả `NULL`, count0 được cho phép | Trả Java kết quả rỗng | Không đọc raw pointer |
| C trả `NULL` nhưng count5 | Báo lỗi contract | Không reinterpret/dereference |
| C trả pointer non-null nhưng count âm | Báo lỗi count | Không chuyển âm sang `size_t` lớn |
| Count vượt limit nghiệp vụ | Báo lỗi trước đọc/cấp phát | Không mở view quá lớn |
| Count hợp lệ, byte count overflow với layout lớn | `Math.multiplyExact` báo lỗi | Không dùng kết quả đã overflow |
| Borrowed pointer tới `static const` | Read-only và không free | Library chưa unload |
| Malloc pointer do Java sở hữu | Free đúng một lần, kể cả Java exception | `finally`/`AutoCloseable` |
| Native realloc trong lúc Java đọc | Phải có lock/snapshot hoặc API copy | Không dùng stale view |
| Arena đóng | Derived scoped view không dùng được | Không escape/lưu bất hợp lệ |
| Buffer chứa NUL giữa chừng | Byte count vẫn giữ dữ liệu | Không thay length bằng `strlen` |
| FFM function returns opaque context | Chỉ truyền pointer lại C | Không tự đọc layout private |
| Chạy Java thiếu native access flag | Lỗi/cảnh báo policy tùy JDK | Cấu hình đúng module |
| Compiler C đổi struct padding | Java wrapper phải kiểm tra lại layout | Đo `sizeof`, `offsetof` trên đúng ABI |

Test tốt nhất kết hợp **unit tests** cho contract Java, **integration tests** trên OS/architecture có native library thật, **sanitizer** ở C nếu toolchain hỗ trợ, và test đặc biệt cho null/zero/negative/oversized length. Các bài test FFM chỉ gọi Java với segment bounds đúng chưa đủ; cần test phía C không viết/đọc vượt allocation.

### 14.1. Bài tập biến thể từ demo

1. Thay `borrow_numbers` trả mảng 5 phần tử và ghi count5. Cập nhật expected output và kiểm tra Java không có số 3 hard-code trong vòng lặp.
2. Thay `create_numbers(4)` thành `create_numbers(1)`; dự kiến sum10. Thử `create_numbers(0)`: C trả NULL, Java báo lỗi thay vì đọc mảng rỗng, vì contract mẫu không cho count0.
3. Trong một nhánh lỗi C, cố ý trả `NULL` nhưng ghi count3 từ borrowed API; Java phải từ chối trước reinterpret.
4. Thêm `copy_numbers(int32_t *dst,int32_t capacity)` để Java tự cấp buffer. So sánh việc dùng arena-owned segment với returned pointer có unknown size.
5. Mô tả một C API trả `const char *data,size_t bytes` với embedded NUL. Giải thích tại sao `String.length()` và `strlen` đều không thay thế byteLength.
6. Giả lập callback native chạy sau khi Java đã free pointer. Thiết kế protocol stop/in-flight/close để không đọc freed block.
7. Thêm một struct gồm `void *pointer; size_t byteCount`. Đo `sizeof`/`offsetof` trên Linux x64 và Windows x64 trước khi khai báo FFM `MemoryLayout`.
8. Tạo một opaque `Context *`; giải thích vì sao không cần reinterpret và vì sao giữ handle sau destroy là nguy hiểm.

Bài tập về pointer null và deliberately invalid size nên **kiểm tra guard trước khi truy cập**, không chủ đích dereference vùng nhớ native sai để “xem JVM báo lỗi gì”. Lỗi native pointer có thể crash JVM và làm mất dữ liệu, không phải bài thử exception an toàn.

## 15. Checklist áp dụng cho code production

- [ ] Đã đọc **C API contract**: pointer type, element size, byte order/ABI, return code, output length, allowed null.
- [ ] Độ dài có **nguồn tin đáng tin cậy** (out-param/struct/fixed-size/copy API), không tự đo size từ raw pointer.
- [ ] Đã phân biệt **zero-length pointer segment** với **buffer có 0 phần tử** và **NULL pointer**.
- [ ] Count có đúng **đơn vị byte hay phần tử**; có giới hạn max và kiểm tra số âm?
- [ ] Đã tính byte count bằng phép nhân kiểm tra overflow, không ép kiểu rồi mới kiểm tra?
- [ ] `reinterpret` chỉ tạo bounded view **đúng kích thước đã chứng thực**, không mở quá allocation.
- [ ] Target ABI phù hợp `ValueLayout`/struct padding/alignment và ký hiệu native export.
- [ ] Pointer là **borrowed, owned, opaque, hay transferred**? Còn hợp lệ trong toàn bộ thời gian Java dùng?
- [ ] Với borrowed data, thư viện/owner sống đủ lâu; không sửa dữ liệu `const` và không free.
- [ ] Với owned data, có **đúng một** đường free/destroy (kể cả exception), không double-free.
- [ ] Native memory không bị free/realloc trong lúc Java view còn đang đọc; threads/callbacks đã được đồng bộ.
- [ ] `Arena` scope, thread ownership và library lookup lifetime đúng; sau close không còn dùng view.
- [ ] Cấp native access cho module dùng `libraryLookup/downcallHandle/reinterpret`; không dùng nhầm Java 17/21 APIs.
- [ ] Với C strings, có encoding, terminator và **bound scan an toàn**; không tin `strlen` cho binary.
- [ ] Có test trên OS/CPU target, toolchain và C ABI thật, bao gồm null, length0, oversized và failure paths.

**Kết luận:** `MemorySegment` kích thước 0 từ một C pointer là thông báo “**FFM biết địa chỉ nhưng chưa biết vùng dữ liệu**”, không phải khẳng định native trả buffer rỗng. Chỉ khi API C cung cấp **kích thước và ownership rõ ràng**, Java mới có cơ sở `reinterpret` thành một view có bounds để đọc. Việc thiết kế cặp `pointer + length + lifetime + destroy` đúng quan trọng hơn việc dùng một lời gọi FFM có vẻ tiện lợi.

### Tài liệu chuẩn

- Oracle, [JDK 22 `MemorySegment` — Zero-length memory segments](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): pointer returns, `byteSize()==0`, `reinterpret`, global scope và các hạn chế an toàn.
- Oracle, [JDK 22 `Linker`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): `downcallHandle`, `FunctionDescriptor` và pointer return carrier.
- Oracle, [JDK 22 `AddressLayout`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/AddressLayout.html): `ADDRESS`, target layout, restricted resizing.
- Oracle, [JDK 22 `SymbolLookup`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): symbol address segments và library lookup lifetime.
- Oracle, [JDK 22 `Arena`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): allocation, scope, close và cleanup actions.
- Oracle, [JDK 22 Core Libraries — Foreign Functions That Return Pointers](https://docs.oracle.com/en/java/javase/22/core/foreign-functions-that-return-pointers.html): returned `malloc` pointer, reinterpret size và free.
- OpenJDK, [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM chuẩn từ JDK 22.