# ValueLayout.ADDRESS và MemorySegment.NULL biểu diễn địa chỉ C

## 1. Mục tiêu học tập

Trong **Foreign Function & Memory API (FFM)**, Java cần trao đổi giá trị con trỏ theo quy ước ABI của C mà không giả định rằng một pointer luôn là Java `long`. Hai công cụ cốt lõi là:

- **`ValueLayout.ADDRESS`**: mô tả kiểu **địa chỉ máy** (`void *`, `int *`, `char *`, v.v. theo hợp đồng C), dùng làm kiểu phần tử hoặc tham số/return trong `FunctionDescriptor`. Java carrier tương ứng là `MemorySegment.class`.
- **`MemorySegment.NULL`**: một **native memory segment dài 0 byte** biểu diễn **con trỏ C có địa chỉ 0**, tương đương về địa chỉ với `MemorySegment.ofAddress(0L)`.

Mục tiêu quan trọng nhất: **phân biệt giá trị pointer với vùng nhớ được pointer trỏ tới**. Một địa chỉ không tự mang kích thước allocation, trạng thái sống, quyền đọc/ghi hoặc ownership. FFM có những kiểm tra an toàn, nhưng các thao tác restricted cho phép gán bounds tùy ý sẽ chuyển trách nhiệm xác minh lại cho người viết native bridge.

Bạn sẽ biết cách đọc/ghi pointer slot, phát hiện NULL, phân biệt pointer-to-pointer, sử dụng `AddressLayout.withTargetLayout` một cách có kiểm soát và tránh dangling pointer, use-after-free, double-free. Các ví dụ có file Java độc lập, lệnh build/run và stdout xác định.

**Điều kiện phiên bản:** `java.lang.foreign` ổn định trong **JDK 22+** (JEP 454). Ví dụ đã được đối chiếu với API Java 22/24 và thử trên JDK 24. **Không áp trực tiếp sang Java 17**: FFM lúc đó còn là incubator API và khác package/chữ ký.

## 2. C pointer và FFM: điều gì là giá trị, điều gì là bộ nhớ?

Trong C:

~~~c
#include <stdint.h>

void inspect(void) {
    int32_t number = 2026;
    int32_t *p = &number;
    int32_t *none = NULL;

    /* p là con trỏ, *p là dữ liệu tại địa chỉ p. */
    (void) p;
    (void) none;
}
~~~

Đây là ví dụ C độc lập về khai báo biến trong hàm, **không phải JNI method**. `p` là một **giá trị địa chỉ**. `number` là **vùng chứa 4 byte dữ liệu int32_t**, và `*p` chỉ hợp lệ khi `number` còn tồn tại. `none` biểu diễn null pointer; dereference `*none` là lỗi nghiêm trọng.

Trong FFM, `MemorySegment` có hai vai trò thường gặp:

| Loại giá trị Java | Ví dụ | Nó có nghĩa gì? |
| --- | --- | --- |
| Segment có kích thước và scope do Java quản lý | `arena.allocate(ValueLayout.JAVA_INT)` | Biểu diễn vùng 4 byte có thể truy cập trong lifetime của arena |
| Segment chỉ bọc địa chỉ | `MemorySegment.ofAddress(0x1234L)` hoặc `slot.get(ValueLayout.ADDRESS, 0)` | Biểu diễn **giá trị con trỏ**, thường `byteSize()==0`, không chứng minh 4 byte nào hợp lệ |
| Constant native null pointer | `MemorySegment.NULL` | Địa chỉ 0; không có byte nào có thể dereference |
| Heap segment từ Java array | `MemorySegment.ofArray(new byte[] {1, 2})` | Vùng Java heap chịu GC, **không** phải native pointer C ổn định |

**Không đánh đồng Java reference/JNI `jobject` với C pointer.** JNI references được JVM quản lý theo GC; `MemorySegment` dùng làm pointer carrier của FFM có contract khác. Địa chỉ raw không được dùng để suy ra cấu trúc nội bộ của object Java.

### Một layout khác một segment

`ValueLayout.ADDRESS` thuộc interface `AddressLayout`, là **mô tả dữ liệu**. `MemorySegment` là một **giá trị Java mang address/bounds/scope**. Layout không cấp phát native memory; bạn cần `Arena` hoặc một API FFM khác để có segment thật.

~~~java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

AddressLayout layout = ValueLayout.ADDRESS;
System.out.println(layout.carrier() == MemorySegment.class); // true
~~~

Đây là snippet bên trong Java method/JShell, không phải cả một Java class. Java `int`, `long` và `MemorySegment` không phải các carrier có thể tráo đổi chỉ nhờ ép kiểu.

## 3. `ValueLayout.ADDRESS`: width, alignment và ABI

`ValueLayout.ADDRESS` là một `AddressLayout` có carrier `MemorySegment.class`, kích thước bằng một địa chỉ máy theo nền tảng, alignment theo ABI và byte order mặc định là native order.

~~~java
long bytes = ValueLayout.ADDRESS.byteSize();
long alignment = ValueLayout.ADDRESS.byteAlignment();
Class<?> carrier = ValueLayout.ADDRESS.carrier();
~~~

Một số hệ 64-bit thường có pointer width 8 byte và alignment 8; hệ 32-bit thường khác. Do đó **không hard-code width 8** và không thay layout `ADDRESS` bằng `JAVA_LONG` chỉ vì cả hai thường rộng 8 trên máy phát triển.

| Mục đích | Layout FFM | Kiểu Java sử dụng |
| --- | --- | --- |
| Native pointer (data/function pointer theo ABI/API tương ứng) | `ValueLayout.ADDRESS` | `MemorySegment` |
| Native pointer trong một struct field | `ValueLayout.ADDRESS` | `MemorySegment` khi `get`/`set` |
| Scalar Java int 32-bit | `ValueLayout.JAVA_INT` | `int` |
| Scalar Java long 64-bit | `ValueLayout.JAVA_LONG` | `long` |
| Pointer value ở byte offset không aligned trong packed format đã xác minh | `ValueLayout.ADDRESS_UNALIGNED` | `MemorySegment`; vẫn yêu cầu đủ byte |

`JAVA_LONG` biểu diễn **số nguyên** 64-bit, không phải kiểu con trỏ C portable. Pointer C cũng không tự đại diện cho size length hoặc quyền sở hữu; ví dụ `void *buffer` và `size_t length` là hai thông tin khác nhau.

`ADDRESS_UNALIGNED` chỉ nới điều kiện căn chỉnh của **ô lưu pointer**. Nó **không** làm dữ liệu được pointer trỏ tới hợp lệ, không sửa lỗi bounds và không tạo ownership. Với native struct chứa padding, phải tính vị trí fields theo ABI (`offsetof`, header thực, hoặc layout FFM tương ứng), không cộng bừa kích thước Java types.

## 4. `MemorySegment.NULL` không phải Java `null`

`MemorySegment.NULL` là một native segment có:

~~~java
System.out.println(MemorySegment.NULL.address());  // 0
System.out.println(MemorySegment.NULL.byteSize()); // 0

MemorySegment anotherNull = MemorySegment.ofAddress(0L);
System.out.println(anotherNull.address() == 0L);   // true
~~~

**C `NULL` tương ứng native address 0**, nên khi C API nhận một optional pointer, `MemorySegment.NULL` là đối số thích hợp. Java `null` nghĩa là không có object reference; nó không phải một value `MemorySegment` có address 0 và không nên được dùng thay theo suy đoán.

Bảng phân biệt:

| Giá trị | `address() == 0L` | `byteSize() == 0` | Có nghĩa là C NULL? |
| --- | --- | --- | --- |
| `MemorySegment.NULL` | true | true | Có |
| `MemorySegment.ofAddress(0L)` | true | true | Có, xét giá trị địa chỉ |
| Một raw native pointer khác 0 đọc qua `get(ADDRESS)` | false | true | **Không** |
| Segment native cấp bởi `Arena` với size 4 | thông thường false | false | Không |
| Heap segment `MemorySegment.ofArray(new byte[0])` | có thể 0 theo biểu diễn heap | true | **Không**: không phải native pointer |

**Kiểm tra null native pointer bằng `pointer.address() == 0L`, không bằng `pointer.byteSize() == 0L`.** Pointer non-null cũng có thể có wrapper size 0. Đặc biệt, đối với heap segment, `address()` có thể là offset 0 trong backing region, không phải địa chỉ vật lý; không suy ra C NULL từ heap `address()`.

### Không bao giờ dereference NULL

~~~java
try {
    MemorySegment.NULL.get(ValueLayout.JAVA_BYTE, 0);
} catch (IndexOutOfBoundsException expected) {
    System.out.println("NULL has no readable bytes");
}
~~~

Đây là snippet. API chặn đọc vì segment không có byte hợp lệ. Đừng dùng `MemorySegment.NULL.reinterpret(4)` rồi đọc: khai báo size 4 không cấp memory ở địa chỉ 0, và restricted access có thể phá memory safety.

## 5. Pointer slot và vùng dữ liệu là hai allocations khác nhau

Ví dụ C:

~~~c
int32_t value = 2026;
int32_t *pointer = &value;
~~~

Một pointer slot chứa **địa chỉ**; nơi pointer trỏ tới chứa **dữ liệu**:

~~~text
Native data region                 Pointer slot
+----------------------+          +----------------------+
| int32_t value = 2026 | <--------| address of data      |
+----------------------+          +----------------------+
    4 byte                          width = sizeof(pointer)

ValueLayout.JAVA_INT             ValueLayout.ADDRESS
~~~

Trong Java:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment data = arena.allocate(ValueLayout.JAVA_INT);
    data.set(ValueLayout.JAVA_INT, 0, 2026);

    MemorySegment slot = arena.allocate(ValueLayout.ADDRESS);
    slot.set(ValueLayout.ADDRESS, 0, data);

    MemorySegment pointer = slot.get(ValueLayout.ADDRESS, 0);

    System.out.println(pointer.address() == data.address()); // true
    System.out.println(pointer.byteSize());                   // 0
}
~~~

Đây là snippet trong Java method. `arena.allocate(ValueLayout.ADDRESS)` cấp đủ byte để **lưu một pointer-sized value**, không cấp phát pointee. `slot.set(ValueLayout.ADDRESS, 0, data)` ghi **địa chỉ của data**, không copy 2026 bytes, không di chuyển data và không chuyển ownership. `slot.get(ADDRESS,0)` đọc pointer từ slot, thông thường trả về **native segment size 0 gắn global scope**.

Đó là lý do nên dùng nguyên segment `data` để đọc/ghi khi bạn đã có nó. `pointer` chỉ có địa chỉ, không biết vùng đó có bao nhiêu byte, nên `pointer.get(JAVA_INT,0)` thường bị `IndexOutOfBoundsException`.

## 6. Chương trình Java hoàn chỉnh: đọc/ghi ADDRESS và NULL

Tạo tệp `PointerAddressDemo.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class PointerAddressDemo {
    public static void main(String[] args) {
        System.out.println("carrier="
                + (ValueLayout.ADDRESS.carrier() == MemorySegment.class));
        System.out.println("null-address=" + MemorySegment.NULL.address());
        System.out.println("null-size=" + MemorySegment.NULL.byteSize());

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment data = arena.allocate(ValueLayout.JAVA_INT);
            data.set(ValueLayout.JAVA_INT, 0, 2026);

            MemorySegment slot = arena.allocate(ValueLayout.ADDRESS);
            slot.set(ValueLayout.ADDRESS, 0, data);

            MemorySegment pointer = slot.get(ValueLayout.ADDRESS, 0);
            System.out.println("same-address="
                    + (pointer.address() == data.address()));
            System.out.println("pointer-size=" + pointer.byteSize());
            System.out.println("data-value="
                    + data.get(ValueLayout.JAVA_INT, 0));

            try {
                pointer.get(ValueLayout.JAVA_INT, 0);
                throw new AssertionError("Expected bounds failure");
            } catch (IndexOutOfBoundsException expected) {
                System.out.println("pointer-read="
                        + expected.getClass().getSimpleName());
            }

            slot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);
            MemorySegment nullPointer = slot.get(ValueLayout.ADDRESS, 0);
            System.out.println("null-in-slot="
                    + (nullPointer.address() == 0L));
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 22+; **không** phải nạp native library hoặc bật restricted native access:

~~~bash
javac -encoding UTF-8 PointerAddressDemo.java
java PointerAddressDemo
~~~

Stdout chính xác:

~~~text
carrier=true
null-address=0
null-size=0
same-address=true
pointer-size=0
data-value=2026
pointer-read=IndexOutOfBoundsException
null-in-slot=true
~~~

Giải thích: 2026 được đọc từ `data` (original segment), không phải từ raw pointer wrapper. `pointer` mang đúng address nhưng `byteSize()==0` nên dereference trực tiếp bị chặn. Đổi nội dung pointer slot thành `NULL` **không free data**. Sau khi arena đóng, cả `data` và `slot` hết hiệu lực; raw pointer đã từng chỉ tới data cũng không phải bằng chứng allocation vẫn sống.

Ví dụ cố tình không in số địa chỉ thực (vì ASLR/allocator/OS có thể thay đổi), chỉ so sánh kết quả logic ổn định.

## 7. Tại sao pointer đọc từ `ADDRESS` chỉ có size 0?

Một C pointer không nói:

- Pointee là `int`, một struct, một chuỗi NUL-terminated, hay mảng nhị phân.
- Có bao nhiêu byte phía sau địa chỉ.
- Allocator nào đã cấp và cần dùng `free` hay `library_free`.
- Địa chỉ được dùng trong callback đến khi nào.
- Pointer đã bị free, bị thay đổi bởi realloc, hoặc do một native thread khác giải phóng hay chưa.
- Vùng đó có yêu cầu alignment hoặc thread-safety thế nào.

FFM vì thế biểu diễn pointer đọc được thành segment **0 byte**, với scope global theo API: không có byte nào mặc nhiên được phép dereference.

~~~text
+------------------------------+
| pointer slot có địa chỉ X      |
+------------------------------+
                 |
          get(ADDRESS, 0)
                 v
    MemorySegment(address=X,
                  byteSize=0,
                  scope=global)
                 |
        +--------+--------+
        |                 |
     address()       get(JAVA_INT,0)
        |                 |
        X          IndexOutOfBoundsException
~~~

**Global scope không làm bộ nhớ của pointee tồn tại vĩnh viễn**. Nó chỉ mô tả scope của wrapper, không chuyển ownership của allocation đã tạo địa chỉ X. Đặc biệt, pointer được đọc từ slot có thể vẫn tồn tại như một Java object sau khi native arena tạo data đã đóng, nhưng nó trở thành **dangling address** nếu pointee đã được giải phóng.

## 8. Target layout và việc dereference có kiểm soát

Khi **đã biết chắc** native pointer trỏ tới một `int32_t` còn sống và aligned, `AddressLayout.withTargetLayout` cho phép mô tả target vùng nhớ:

~~~java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.ValueLayout;

AddressLayout pointerToInt =
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT);
~~~

Thông thường `slot.get(ValueLayout.ADDRESS, 0)` trả segment size 0; với `pointerToInt`, `slot.get(pointerToInt, 0)` trả segment kích thước **`JAVA_INT.byteSize() == 4`**. Pointer slot vẫn chiếm số byte của `ADDRESS`, không bị thay bằng int.

**`withTargetLayout` là restricted operation**: nó tin layout do caller khai báo, không tự xác minh allocation. Sai target size, null address, dangling pointer hoặc sai alignment có thể gây **JVM crash/memory corruption**. Caller cần có native-access permission (với classpath: `--enable-native-access=ALL-UNNAMED`).

### Ví dụ độc lập `TypedPointerDemo.java`

~~~java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class TypedPointerDemo {
    public static void main(String[] args) {
        // Restricted: chỉ dùng khi hiểu và kiểm soát pointee.
        AddressLayout intPointer =
                ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment data = arena.allocate(ValueLayout.JAVA_INT);
            data.set(ValueLayout.JAVA_INT, 0, 41);

            MemorySegment slot = arena.allocate(ValueLayout.ADDRESS);
            slot.set(ValueLayout.ADDRESS, 0, data);

            MemorySegment view = slot.get(intPointer, 0);
            System.out.println("view-size=" + view.byteSize());
            System.out.println("view-value="
                    + view.get(ValueLayout.JAVA_INT, 0));
        }
    }
}
~~~

Biên dịch/chạy trên JDK 22+:

~~~bash
javac -encoding UTF-8 TypedPointerDemo.java
java --enable-native-access=ALL-UNNAMED TypedPointerDemo
~~~

Stdout:

~~~text
view-size=4
view-value=41
~~~

Đây là một ca **có cơ sở để tin target hợp lệ**: chính chương trình đã cấp 4 byte bằng arena, đặt giá trị, và đọc trong khối `try` khi allocation còn sống. Không nên lưu `view` để dùng sau khi `arena.close()`; raw pointer view có scope khác original data segment nên không tự dừng đúng thời điểm nếu pointee đã bị free.

### `reinterpret` và scope

`MemorySegment.reinterpret(newSize)` và biến thể `reinterpret(newSize, arena, cleanup)` cũng là **restricted methods** để tạo bounds/scope mới cho native pointer. Cả hai không tự cấp phát vùng đích và không tự chứng minh address an toàn. Dùng overload có `Arena` có thể ràng buộc **view** vào scope mới, nhưng vẫn phải bảo đảm backing memory thật thuộc lifetime/owner đúng; không được cài cleanup giả hoặc trùng native deallocator.

**Ưu tiên:** Nếu đã có `MemorySegment data` do chính `Arena.allocate(...)` trả về, dùng `data` hoặc `data.asSlice(...)` thay vì round-trip pointer rồi `reinterpret`. Chỉ dựng view từ raw address khi thật sự cần làm việc với kết quả C API và đã có đủ hợp đồng.

## 9. Kiểm tra NULL trước khi mở rộng bounds

Một C API có thể trả pointer 0 để báo vắng dữ liệu. Phần tiêu thụ nên kiểm trước:

~~~java
// Snippet: pointer là native MemorySegment có địa chỉ từ C.
if (pointer.address() == 0L) {
    // C NULL: không dereference.
} else {
    // Chưa đủ: còn cần size, lifetime, alignment, owner hợp lệ.
}
~~~

**Non-NULL không đồng nghĩa valid**: dangling pointer hoặc pointer tới memory đã free vẫn có address khác 0. Vì vậy kiểm NULL là điều kiện cần cho nhiều API, **không phải điều kiện đủ** để truy cập an toàn.

`MemorySegment.ofAddress(someLong)` tự nó cũng chỉ tạo segment 0 byte, không xác thực pointer tồn tại. Không dùng một hằng `0x12345678L` làm địa chỉ để thử đọc trong demo: số tùy ý có thể trỏ vào vùng không hợp lệ và gây lỗi JVM khi bị reinterpret.

## 10. `T*` khác `T**`: con trỏ và ô chứa con trỏ

Một API C có thể điền pointer kết quả qua out-parameter:

~~~c
#include <stdint.h>

/* Chỉ là prototype C minh họa, chưa có implementation. */
int make_buffer(int32_t **out, size_t *count);
~~~

`out` là **pointer-to-pointer**, tức địa chỉ của một vùng lưu pointer. Đối với FFM, bạn phải cấp pointer slot rồi truyền **segment của slot** cho native function:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment outputSlot = arena.allocate(ValueLayout.ADDRESS);
    outputSlot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);

    // Native function tương ứng sẽ nhận outputSlot:
    // make_buffer(outputSlot, countSlot) -- chỉ là mô phỏng.

    MemorySegment result = outputSlot.get(ValueLayout.ADDRESS, 0);
    if (result.address() != 0L) {
        // Cần biết count, size, allocator và release function.
    }
}
~~~

Đây là **snippet khái niệm**, không thực hiện foreign downcall. Sau khi C ghi `*out`, đọc slot bằng `get(ADDRESS)` để lấy pointer value.

Phân biệt ba lời truyền:

| Truyền cho C | C thấy gì? |
| --- | --- |
| `MemorySegment.NULL` | Một **null pointer** cho argument |
| `outputSlot` | Địa chỉ một **ô đủ chứa pointer**, phù hợp argument kiểu `T **` |
| `result` | Pointer value được chứa trong slot sau khi C ghi; **không** phải address của slot |

C `size_t *count` là một **out-parameter khác** và phải khai báo theo ABI thật (không lấy `JAVA_LONG` làm đáp án chung cho mọi `size_t`). Khi lấy buffer từ C, `get(ADDRESS)` không tự biết length hay có quyền giải phóng. Đọc hợp đồng của API: caller-owned hay library-owned, lifetime bao lâu, release function nào?

## 11. ADDRESS trong `FunctionDescriptor`

Nếu C API định nghĩa:

~~~c
void *identity(void *p);
~~~

thì phần mô tả FFM (không bao gồm symbol lookup/downcall setup) có thể là:

~~~java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.ValueLayout;

FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.ADDRESS,  // C return void*
        ValueLayout.ADDRESS   // C parameter void*
);
~~~

Ở đây, kiểu **máy** của tham số và giá trị trả về là pointer. Carrier trong Java là `MemorySegment`. `FunctionDescriptor` không tạo memory, không kiểm allocation còn sống và không mã hóa ownership. Thực hiện downcall thật cần đúng C symbol, `Linker`, ABI, lifetime, và native-access permission cho các restricted operations.

Đối với các API có `const void *`, layout pointer vẫn có thể là `ADDRESS`, nhưng C `const` là **hợp đồng không sửa dữ liệu** mà FFM không tự áp đặt khi chỉ nhìn vào pointer layout. Cần tách contract read-only khỏi khả năng ghi của alias khác.

## 12. Ownership: điều gì giải phóng địa chỉ C?

**Một pointer value không sở hữu vùng nhớ**. Để code đúng, xác định ai cấp và ai phải dọn:

| Nguồn dữ liệu | Owner/lifetime | Quy tắc |
| --- | --- | --- |
| `arena.allocate(...)` | `Arena` đang dùng; với confined/shared closeable arena thì hết hiệu lực khi `close()` | Không lưu raw pointer cho native code dùng sau close |
| C `malloc` hoặc factory trả caller-owned pointer | Theo API C; thường caller được quyền release bằng native deallocator tương ứng | Dùng đúng `free`/`library_free` theo hợp đồng; chỉ release một lần |
| C library trả pointer vào internal buffer | Library sở hữu, có thể invalidate ở lần gọi tiếp theo | Không tự `free`; copy trong lifetime nếu cần giữ lại |
| Pointer tới local C stack variable sau return | Dangling | Không “sửa” bằng `ofAddress` hoặc `reinterpret`; phải sửa API C |
| Heap `MemorySegment.ofArray` | JVM quản lý Java heap | Không dùng như raw native pointer vào C nếu API không hỗ trợ |
| `MemorySegment.ofAddress(rawLong)` | Chỉ wrapper, **không có allocation/cleanup được đăng ký thêm** | Không coi Java object còn sống là pointee còn sống |

Ví dụ phản chứng:

~~~java
MemorySegment raw;
try (Arena arena = Arena.ofConfined()) {
    MemorySegment data = arena.allocate(ValueLayout.JAVA_INT);
    raw = MemorySegment.ofAddress(data.address());
}
// raw.address() có thể vẫn khác 0.
// Không dùng raw.reinterpret(4).get(JAVA_INT, 0) sau khi arena đóng!
~~~

Snippet không dereference dangling pointer. Khi arena đóng, memory nguồn đã hết hạn. `raw` có global scope nhưng không làm backing allocation tồn tại mãi. **Global scope của wrapper không phải lifetime của pointee**.

Nếu native asynchronous callback vẫn cầm pointer, chỉ đóng arena khi mọi native consumer đã hoàn thành. Nếu native library sở hữu allocator riêng, không dùng arena để giải phóng memory ngoài hợp đồng (và không gọi C `free` từ bất kỳ allocator khác một cách phỏng đoán).

### Heap memory không phải native pointer C

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment slot = arena.allocate(ValueLayout.ADDRESS);
    MemorySegment heap = MemorySegment.ofArray(new byte[] {1, 2});

    try {
        slot.set(ValueLayout.ADDRESS, 0, heap);
    } catch (IllegalArgumentException expected) {
        System.out.println("heap-not-native=true");
    }
}
~~~

Trên JDK 24, dòng in là `heap-not-native=true`. API `set(ADDRESS,...)` chỉ nhận **native segment value**; một heap segment có thể mang offset `address()` bằng 0 nhưng không phải C `NULL` hay địa chỉ vật lý của backing array. Java GC có thể di chuyển mảng; không dùng số offset heap để đưa cho C.

## 13. Bounds, alignment, lifecycle và thread-safety là các kiểm tra khác nhau

Pointer đúng ABI mới chỉ giải quyết **kiểu địa chỉ**. Để dereference hợp lệ còn cần:

1. **Bounds:** pointer phải trỏ ít nhất số byte cần đọc. `get(ADDRESS)` mặc định size 0 nhằm tránh tự suy size.
2. **Alignment:** `JAVA_INT` thường cần 4-byte aligned; `ADDRESS` cần alignment slot phù hợp. `ADDRESS_UNALIGNED` chỉ ảnh hưởng vị trí **lưu pointer**, không tự sửa pointee.
3. **Scope/lifetime:** Arena có thể đã close, C có thể đã free, native function có thể đã invalidated pointer.
4. **Thread access:** `Arena.ofConfined()` chỉ cho owner thread truy cập original segment. Dựng raw address wrapper có thể mất kiểm tra đó, **không** làm sharing an toàn.
5. **Read/write:** C `const`, FFM read-only views và native permissions là các hợp đồng khác nhau; pointer layout không tự áp đặt immutable data.
6. **Ownership:** ai free, bằng API nào, sau operation nào, và có được chuyển ownership qua FFM boundary không?

Đừng dựa vào một check như `ptr.address()!=0L` để bỏ năm điều kiện còn lại. Một con trỏ invalid vẫn có thể là một số non-zero hợp lệ về mặt bit representation.

## 14. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Dùng `ValueLayout.JAVA_LONG` thay `ADDRESS` | Đoán width theo máy hiện tại, sai pointer ABI/semantics | Dùng `ADDRESS` cho pointer |
| Truyền Java `null` cho C NULL | Không phải object `MemorySegment` mang address 0 | Dùng `MemorySegment.NULL` |
| Kiểm `byteSize()==0` để nhận diện null | Nonnull raw pointer cũng size 0 | Kiểm `address()==0L` |
| `get(ADDRESS).get(JAVA_INT,0)` lỗi | Raw pointer wrapper zero length | Giữ original segment hoặc bảo đảm bounds rồi dùng restricted target có kiểm soát |
| Cố `NULL.reinterpret(...)` để đọc | Địa chỉ 0 không chỉ vùng dữ liệu hợp lệ | Không dereference NULL |
| `withTargetLayout` trên pointer vô danh | Caller tự gán sai size; memory corruption | Chỉ dùng với C contract đáng tin |
| `ofAddress` rồi cho rằng memory thuộc arena | Wrapper không cấp phát/không gắn owner | Quản lý allocation thực sự |
| `set(ADDRESS, 0, heapSegment)` lỗi | Heap segment không phải native value | Copy dữ liệu qua native segment khi cần |
| Nhầm `T **` với `T *` | Out pointer cần slot chứa pointer | Cấp `arena.allocate(ADDRESS)` và truyền slot |
| Đóng Arena khi C còn dùng pointer | Dangling/use-after-free | Đồng bộ lifetime tới hết C work |
| Free pointer do library quản lý | Double-free/sai allocator | Theo native ownership contract |
| Tưởng global scope nghĩa là memory bất tử | Wrapper pointer không quản lý pointee | Theo dõi owner/scope của allocation nguồn |
| So sánh pointer numeric across runs | ASLR, allocator, platform thay đổi | Không hard-code raw addresses |
| Diễn giải `address()==0L` của heap như C NULL | Heap address là virtual offset, có thể 0 | Chỉ áp null-check cho native pointers |

**Một lỗi rất dễ nhầm:** `ValueLayout.ADDRESS` biểu diễn **địa chỉ C**, chứ không tự suy đó là C string UTF-8, binary buffer hay pointer tới struct. Nếu C trả `char *` mà không có length, cần biết rõ hợp đồng NUL terminator/encoding; nếu chứa dữ liệu binary, không được đọc tới byte 0 như chuỗi.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `MemorySegment.NULL` tương đương `MemorySegment.ofAddress(0L)` theo nghĩa nào?

**Đáp án:** Cả hai biểu diễn native address 0 và zero-length, tức C NULL. Không cần hay nên phụ thuộc Java object identity giữa chúng.

**Câu 2.** `byteSize()==0` chứng minh pointer là NULL không?

Không. Một nonzero pointer đọc bằng `get(ValueLayout.ADDRESS,offset)` thường cũng là zero-length wrapper. Dùng `address()==0L` trên native pointer.

**Câu 3.** Vì sao dùng `JAVA_LONG` thay `ADDRESS` không portable?

`JAVA_LONG` luôn là Java scalar 64-bit, còn `ADDRESS` chọn pointer-sized representation/alignment theo ABI, carrier là `MemorySegment`.

**Câu 4.** `slot.set(ADDRESS,0,data)` copy nội dung `data` hay ghi địa chỉ?

Chỉ **ghi địa chỉ**. `slot` có size đủ cho pointer value; `data` vẫn chứa dữ liệu và owner/lifetime cũ.

**Câu 5.** `slot.get(ADDRESS,0)` trả pointer cùng địa chỉ `data`, tại sao `pointer.get(JAVA_INT,0)` lỗi?

Vì pointer wrapper mặc định có `byteSize()==0` và **không tự biết size vùng đích**; truy cập bị `IndexOutOfBoundsException`.

**Câu 6.** `withTargetLayout(JAVA_INT)` có bảo đảm pointer hợp lệ?

Không. Nó là restricted method tin vào hợp đồng của caller; pointer invalid, NULL hoặc dangling có thể làm JVM crash/corrupt memory.

**Câu 7.** Native API nhận `int **out`. Có thể truyền trực tiếp `MemorySegment.NULL` để C ghi `*out` không?

Không. C cần **địa chỉ của pointer slot** đủ byte. Cấp `arena.allocate(ADDRESS)`, truyền slot, rồi đọc pointer bằng `slot.get(ADDRESS,0)`.

**Câu 8.** Raw pointer có global scope nhưng arena cấp nguồn đã đóng; có còn truy cập an toàn không?

Không. Global scope thuộc wrapper, không kéo dài backing allocation. Dereference sau `arena.close()` là use-after-free nguy hiểm.

**Câu 9.** Đọc ADDRESS từ C pointer khác NULL có cần làm thêm gì để truy cập data?

Có. Phải xác định **số byte**, alignment, owner, lifetime, thread access và liệu C API có cho đọc/ghi không. Với raw address, FFM không thể tự khôi phục thông tin bị thiếu.

**Câu 10.** `MemorySegment.ofArray(new byte[0])` có thể có address 0, nó là C NULL?

Không. Đây là **heap segment** với address là offset logic; không phải native null pointer. Không ép thành C pointer nếu không có cơ chế phù hợp.

## Checklist trước khi chuyển địa chỉ qua FFM

- [ ] Native signature đã được xác minh: `T *`, `T **`, hoặc scalar `size_t`?
- [ ] Dùng `ValueLayout.ADDRESS` cho pointer parameters/return/fields, không suy từ `JAVA_LONG`?
- [ ] Null pointer dùng `MemorySegment.NULL`, kiểm `address()==0L` với native pointer?
- [ ] Không kiểm null bằng `byteSize()==0`?
- [ ] Phân biệt địa chỉ **pointer slot** với địa chỉ **pointee**?
- [ ] Mọi raw pointer wrapper có size 0 đều được đối xử như **opaque address** cho đến khi có contract truy cập?
- [ ] Restricted `withTargetLayout`/`reinterpret` chỉ sử dụng khi biết chắc target và bật native access?
- [ ] Có đủ length, alignment, scope, thread ownership và quyền ghi/đọc?
- [ ] Đã xác định allocator/deallocator, tránh use-after-free/double-free?
- [ ] Đã kiểm thử NULL và non-null pointer; chương trình không hard-code số địa chỉ thực?
- [ ] Không đưa heap `MemorySegment.ofArray` trực tiếp thành C pointer?
- [ ] Khi C giữ pointer qua callback/async job, vùng nhớ được giữ sống đến khi công việc kết thúc?

## Tài liệu chính thức

1. [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `NULL`, `ofAddress`, `get/set(AddressLayout,...)`, zero-length wrappers, `reinterpret` và scope.
2. [Java SE 24 — AddressLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/AddressLayout.html): carrier `MemorySegment.class`, restricted `withTargetLayout`.
3. [Java SE 24 — ValueLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/ValueLayout.html): `ADDRESS`, `ADDRESS_UNALIGNED`, width/alignment/order.
4. [Java SE 24 — Arena](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html): allocation, lifetime, confined/shared scope.
5. [Java SE 24 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): pointer values trong FFM downcall ABI.
6. [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM API ổn định từ JDK 22.

**Kết luận:** `ValueLayout.ADDRESS` mô tả **cách lưu và truyền địa chỉ C**. `MemorySegment.NULL` mô tả **C NULL pointer có địa chỉ 0**. Nhưng raw address không chứng minh rằng pointee có vùng nhớ hợp lệ; an toàn yêu cầu xác minh rõ **bounds, lifetime, alignment và ownership** trước mọi dereference.
