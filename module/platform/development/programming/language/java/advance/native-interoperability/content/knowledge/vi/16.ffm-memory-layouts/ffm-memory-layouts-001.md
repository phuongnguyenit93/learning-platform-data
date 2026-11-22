# ValueLayout trong Java FFM: kiểu carrier, kích thước và căn chỉnh dữ liệu

Khi Java đọc/ghi một vùng bộ nhớ ngoài heap hay truyền đối số cho hàm C qua Foreign Function & Memory API (FFM), câu hỏi không chỉ là “giá trị này có kiểu `int` không?”. Bạn còn phải biết **cần bao nhiêu byte để biểu diễn nó**, **địa chỉ nào được phép đặt giá trị đó**, **thứ tự byte ra sao**, và **kiểu Java nào xuất hiện ở bên gọi**. `java.lang.foreign.ValueLayout` mô tả chính các đặc điểm ấy.

Bài thuộc nhóm **Bố trí dữ liệu** của Java Native Interoperability. Trọng tâm là ba thuộc tính:

- `carrier()`: **kiểu Java** dùng để mang một giá trị qua API FFM, ví dụ `int.class`, `double.class` hay `MemorySegment.class`.
- `byteSize()`: **số byte** của một giá trị theo layout; không phải số phần tử, số bit hay kích thước của một Java object.
- `byteAlignment()`: **ràng buộc căn chỉnh địa chỉ/offset theo byte**, ví dụ số nguyên 4 byte được truy cập ở địa chỉ bội số của 4 khi dùng `ValueLayout.JAVA_INT`.

Bài hướng dẫn thêm `order()`, `withOrder(...)`, `withByteAlignment(...)`, các `JAVA_*` layout, `ADDRESS`, cách đọc/ghi `MemorySegment`, `VarHandle`, cấu trúc C có padding, ánh xạ kiểu C theo ABI và lỗi thường gặp. Có **một ví dụ Java hoàn chỉnh chạy với JDK 22+ không cần viết C**, và **một chương trình C11 độc lập** để so sánh struct layout theo compiler thật.

> **Phạm vi phiên bản:** `java.lang.foreign.ValueLayout` trở thành API chuẩn từ **JDK 22** (JEP 454). Java 21 có phiên bản FFM preview; Java 17 dùng API incubator khác. Không lấy mã `java.lang.foreign.*` ở đây và chạy nguyên trạng với JDK 17/21. Mã Java ở phần thực hành yêu cầu JDK 22 trở lên.

## 1. ValueLayout nằm ở đâu trong mô hình FFM?

~~~text
Java value (int, long, double, MemorySegment...)
                    |
                    | ValueLayout:
                    |   carrier()
                    |   byteSize()
                    |   byteAlignment()
                    |   order()
                    v
MemorySegment + byte offset -----------------> native/heap memory bytes
                    |
                    | MemoryLayout:
                    |   structLayout(...)
                    |   sequenceLayout(...)
                    |   unionLayout(...)
                    |   paddingLayout(...)
                    v
       Layout phức hợp mô tả struct, array, union

Linker + FunctionDescriptor (nếu gọi hàm C)
                    |
                    | C ABI, không chỉ Java carrier
                    v
               Native function
~~~

`MemorySegment` biểu diễn một **vùng nhớ liên tiếp có kích thước và lifetime**, chẳng hạn vùng cấp bằng `Arena.ofConfined()` hoặc một view trên mảng Java. Bản thân nó không tuyên bố “bốn byte từ offset 8 là một int hay float”. Bạn cung cấp `ValueLayout` để đọc/ghi bằng đúng biểu diễn mong muốn:

~~~java
// Mảnh Java minh họa, giả định segment còn sống,
// có ít nhất 12 byte writable và offset 8 đủ alignment.
segment.set(ValueLayout.JAVA_INT, 8, 42);
int value = segment.get(ValueLayout.JAVA_INT, 8);
~~~

Với `JAVA_INT`: carrier `int`, kích thước 4 byte, alignment 4 byte. Java API sẽ kiểm tra bounds, trạng thái scope, quyền thread và alignment theo layout. Nếu thay `JAVA_INT` bằng `JAVA_FLOAT` ở cùng vùng nhớ, bạn đang **diễn giải cùng các byte theo kiểu khác**, không phải “ép kiểu” Java `int` sang `float`.

`ValueLayout` là một **giá trị mô tả dữ liệu**, không phải vùng nhớ. Tạo một layout không cấp phát memory và không tạo object C. `MemoryLayout` là kiểu cha; ngoài scalar values còn có `SequenceLayout`, `StructLayout`, `UnionLayout` và `PaddingLayout`. `ValueLayout` là một nhánh dành cho các giá trị scalar/address có Java carrier tương ứng.

## 2. Ba thuộc tính cốt lõi: carrier, size và alignment

Giả sử:

~~~java
ValueLayout.OfInt layout = ValueLayout.JAVA_INT;

Class<?> type = layout.carrier(); // int.class
long size = layout.byteSize();    // 4 byte
long align = layout.byteAlignment(); // 4 byte
~~~

Đây là mảnh Java minh họa; ví dụ chạy độc lập nằm ở phần 10.

### 2.1. `carrier()` là kiểu Java, không phải “tên kiểu C”

`carrier()` trả `Class<?>` của kiểu mà Java sẽ nhận/truyền khi dùng layout. Với `JAVA_INT` thì carrier là `int.class`, nên `MemorySegment.get(ValueLayout.JAVA_INT, offset)` trả `int` và `set(..., intValue)` nhận `int`. Với `JAVA_DOUBLE`, carrier là `double.class`. Với `ValueLayout.ADDRESS`, carrier là `MemorySegment.class`: địa chỉ native được biểu diễn phía Java dưới dạng segment/address object, **không phải** `long` hay `Object` tùy ý.

Sự phân biệt này đặc biệt quan trọng khi tạo FFM `FunctionDescriptor`: các `ValueLayout` trong descriptor ảnh hưởng Java `MethodHandle` type của downcall/upcall. Nếu bạn mô tả C `int32_t` bằng `JAVA_LONG` (carrier `long`, width 8 byte) thay vì một layout 4 byte phù hợp, bạn có thể tạo ra **sai ABI** dù tên hàm C đúng.

**Carrier là một kiểu Java**, không bao hàm signedness, kích thước `long` của C trên mọi OS, bitfield semantics, nullable contract hoặc bộ mã Unicode. Các yếu tố ấy phải được xác định từ C header, ABI và tài liệu giao thức.

### 2.2. `byteSize()` là chiều rộng biểu diễn **một** giá trị

`JAVA_INT.byteSize() == 4` nghĩa là một giá trị dùng bốn byte; `JAVA_LONG.byteSize() == 8` nghĩa là tám byte. Với `ADDRESS`, width phụ thuộc kích thước native pointer của nền tảng, thường 4 byte trên target 32-bit hoặc 8 byte trên target 64-bit.

Nếu một mảng native có 100 phần tử `int32_t` và mỗi phần tử tương ứng `JAVA_INT`, lượng dữ liệu là `100 * JAVA_INT.byteSize()` = 400 byte, **không phải** 100 byte. Khi nhân count với size, kiểm tra overflow nếu count đến từ input lớn hoặc không tin cậy.

`byteSize()` không nói gì về số byte của một Java object `Integer` hay metadata JVM, cũng không cấp phép bạn đo một Java `int[]` trực tiếp bằng C pointer. Java heap object/array có layout do JVM quản lý và khác hẳn raw native memory.

### 2.3. `byteAlignment()` ràng buộc địa chỉ truy cập

Alignment 4 có nghĩa vùng truy cập của một giá trị phải bắt đầu tại **địa chỉ chia hết cho 4**; offset còn phải kết hợp với alignment thực tế của base address. Với `JAVA_INT`, các offset 0, 4, 8... trong **segment có base alignment phù hợp** là hợp lệ; offset 1 không hợp lệ cho aligned int access.

Alignment là một số lũy thừa của 2, không nhất thiết bằng `byteSize()`. Đặc biệt theo tài liệu **JDK 22**, `JAVA_LONG` và `JAVA_DOUBLE` luôn có kích thước 8 byte nhưng alignment của hai hằng có thể là 4 byte ở nền tảng 32-bit và 8 byte ở 64-bit. Đừng suy diễn `byteAlignment() == byteSize()` cho mọi `ValueLayout`.

Có thể yêu cầu điều chỉnh constraint bằng `withByteAlignment(long)`; điều này **tạo layout mới**, không làm CPU tự sửa alignment của một pointer. Nếu C ABI/struct yêu cầu alignment 8, bạn phải bảo đảm vùng nhớ/offset phù hợp, không chỉ đổi một con số trong mô tả.

## 3. Những ValueLayout có sẵn trong JDK 22

Các hằng ở `ValueLayout` dùng tên `JAVA_*` vì carrier và kích thước được định nghĩa theo kiểu Java. Các giá trị thông thường:

| Hằng | `carrier()` | `byteSize()` | Alignment trong JDK 22 |
| --- | --- | ---: | --- |
| `JAVA_BOOLEAN` | `boolean.class` | 1 | 1 |
| `JAVA_BYTE` | `byte.class` | 1 | 1 |
| `JAVA_CHAR` | `char.class` | 2 | 2 |
| `JAVA_SHORT` | `short.class` | 2 | 2 |
| `JAVA_INT` | `int.class` | 4 | 4 |
| `JAVA_LONG` | `long.class` | 8 | Theo địa chỉ native: thường 4 hoặc 8 |
| `JAVA_FLOAT` | `float.class` | 4 | 4 |
| `JAVA_DOUBLE` | `double.class` | 8 | Theo địa chỉ native: thường 4 hoặc 8 |
| `ADDRESS` | `MemorySegment.class` | Kích thước pointer: thường 4/8 | Theo pointer: thường 4/8 |

Đừng xem bảng này là một bảng ánh xạ trực tiếp cho **mọi kiểu C**. Ví dụ:

- Java `char` là **một code unit UTF-16 16-bit**, không mặc định bằng C `char` (thường 1 byte) hay `wchar_t` (kích thước phụ thuộc nền tảng).
- Java `boolean` có một `ValueLayout.JAVA_BOOLEAN` kích thước 1 byte trong API, nhưng C `bool`/`_Bool` nên được đối chiếu theo **canonical layout của linker ABI đích**, không theo suy đoán từ tên.
- C `long` thường 64-bit trên Linux x64 (LP64) nhưng **32-bit trên Windows x64 (LLP64)**. Java `long` luôn có carrier 64-bit; `JAVA_LONG` không phải ánh xạ tự động cho mọi C `long`.
- C `size_t` và kiểu pointer phụ thuộc kiến trúc; một `int` Java không thể gánh mọi giá trị unsigned 64-bit mà không có chính sách xử lý.
- Unsigned C integer thường dùng **cùng kích thước storage layout** với signed tương ứng, nhưng code Java phải tự giải thích khoảng giá trị unsigned, mask/convert hoặc dùng kiểu rộng hơn khi cần.

Các hằng `JAVA_CHAR_UNALIGNED`, `JAVA_SHORT_UNALIGNED`, `JAVA_INT_UNALIGNED`, `JAVA_LONG_UNALIGNED`, `JAVA_FLOAT_UNALIGNED`, `JAVA_DOUBLE_UNALIGNED` và `ADDRESS_UNALIGNED` cũng tồn tại. Chúng giảm alignment constraint xuống 1 byte, **không làm thay đổi carrier hay size**. Chỉ dùng khi biểu diễn dữ liệu thực sự có alignment yếu hoặc packed; việc truy cập unaligned có thể kém hiệu năng hoặc không portable khi tương tác native ABI.

### 3.1. Vì sao không thể chỉ nhìn kiểu Java?

Cứ thấy Java `long` rồi đặt `JAVA_LONG` là chưa đủ. Có ít nhất ba lớp:

1. **Java carrier:** khi đọc hoặc gọi `MethodHandle`, phía Java dùng `long.class` hay `int.class`.
2. **Memory layout:** một giá trị trải bao nhiêu byte, ở byte order và alignment nào.
3. **Target ABI:** C function/struct trên OS/compiler/CPU nào quy định độ rộng, padding, register passing, return strategy và calling convention.

FFM mô tả nhiều thông tin trong Java, nhưng bạn vẫn phải đọc C header (hoặc dùng binding generator như jextract khi phù hợp) và kiểm chứng với compiler đúng target. “Java int và C int đều 4 byte” phổ biến trên các ABI JDK hỗ trợ nhưng không phải giấy phép bỏ qua ABI contract của thư viện.

## 4. Endianness: `order()` và `withOrder(...)`

Một giá trị 32-bit `0x01020304` gồm bốn byte. Trong **big-endian**, thứ tự từ địa chỉ thấp đến cao là `01 02 03 04`; trong **little-endian** là `04 03 02 01`. `ValueLayout` có `order()` để mô tả thứ tự byte, mặc định những hằng `JAVA_*` dùng `ByteOrder.nativeOrder()`.

~~~java
ValueLayout.OfInt bigEndian =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);

// Mảnh minh họa: buffer có >= 4 byte và căn chỉnh >=4.
buffer.set(bigEndian, 0, 0x01020304);
~~~

`withOrder(...)` trả layout mới, **không làm thay đổi nội dung của một segment đang có**. Khi bạn dùng layout khác để đọc cùng bốn byte, kết quả số có thể khác nhau. Sự thay đổi là cách **diễn giải/cất dữ liệu**, không phải phép cast `Integer.reverseBytes(...)` tại mức Java object.

Đừng trộn byte order giao thức mạng (thường big-endian) với native order của C ABI. Với file binary định dạng cố định, dùng `withOrder(ByteOrder.BIG_ENDIAN/LITTLE_ENDIAN)` theo file spec. Với native struct trao đổi qua local linker, dùng native order/canonical layouts và tuân thủ ABI đích.

Với layout một byte như `JAVA_BYTE`, thay đổi endianness không tạo khác biệt về thứ tự byte của giá trị đơn lẻ. Với multi-byte scalars thì rất quan trọng.

## 5. `withByteAlignment(...)`, unaligned layout và các lỗi căn chỉnh

Một layout có ba thông tin mà coder dễ đánh đồng: **byteSize**, **byteAlignment**, và **base address + offset**. Một segment có 12 byte không có nghĩa mọi offset từ 0 đến 8 đều hợp lệ để đọc `JAVA_INT` 4-byte:

~~~java
// Mảnh ví dụ: arena đang sống, raw được cấp với base alignment 4.
MemorySegment raw = arena.allocate(12, 4);

raw.set(ValueLayout.JAVA_INT_UNALIGNED, 1, 123);
int value = raw.get(ValueLayout.JAVA_INT_UNALIGNED, 1); // Hợp lệ

// raw.get(ValueLayout.JAVA_INT, 1) sẽ gặp lỗi alignment.
~~~

`JAVA_INT_UNALIGNED` vẫn có size 4 và carrier `int.class` nhưng alignment 1, nên vùng byte 1–4 hợp lệ về mặt **layout constraint**. `JAVA_INT` có alignment 4; khi base aligned 4 mà offset = 1, truy cập theo layout đó gây `IllegalArgumentException`.

Nếu offset = 9 trên segment 12 byte, dù dùng unaligned layout cũng không được đọc một int 4 byte: vùng 9..12 vượt biên; FFM báo `IndexOutOfBoundsException`. **Giảm alignment không nới kích thước vùng nhớ.**

`withByteAlignment(3)` không hợp lệ vì constraint cần là lũy thừa 2; các giá trị như 1, 2, 4, 8 là ứng viên có thể hợp lệ về cú pháp, nhưng phải phù hợp với dữ liệu và ABI. `withByteAlignment(1)` giống những hằng `*_UNALIGNED` tương ứng khi giữ cùng các thuộc tính khác.

**Không dùng unaligned layout để che lỗi struct:** nếu C struct có padding do compiler, cố đọc member ở offset 1 với `JAVA_INT_UNALIGNED` có thể “đọc được” một số byte nhưng đó **không phải** field C đúng. Phải sửa sơ đồ layout và offset của struct, không chỉ giảm constraint.

## 6. Đọc/ghi MemorySegment bằng byte offset hoặc element index

Có hai phong cách:

~~~java
// Mảnh minh họa: numbers chứa tối thiểu 3 int,
// base đúng alignment và arena chưa đóng.
numbers.set(ValueLayout.JAVA_INT, 0, 7);
numbers.set(ValueLayout.JAVA_INT, 4, 8);
numbers.set(ValueLayout.JAVA_INT, 8, 9);

int secondByByteOffset =
        numbers.get(ValueLayout.JAVA_INT, 4);       // 8
int secondByElementIndex =
        numbers.getAtIndex(ValueLayout.JAVA_INT, 1); // 8
~~~

`get(layout, offset)` và `set(layout, offset, value)` nhận **byte offset**. `getAtIndex(layout, index)` và `setAtIndex(layout, index, value)` nhận **element index**, tự scale theo `layout.byteSize()`. Nếu bạn dùng `index=4` cho int array bốn phần tử, cách thứ hai đòi element thứ năm và có thể vượt biên; cách thứ nhất chỉ trỏ tới byte thứ 4 (phần tử thứ hai).

Với một dãy có stride khác size (ví dụ struct có padding), **không** tự giả định index×size của field là stride của record. Dùng `SequenceLayout`/`StructLayout` đúng hoặc offset tính từ toàn bộ record layout.

### 6.1. ValueLayout tạo VarHandle với carrier và offset rõ ràng

~~~java
VarHandle intHandle = ValueLayout.JAVA_INT.varHandle();

// Coordinate types của VarHandle này: (MemorySegment, long).
intHandle.set(numbers, 4L, 456);
int received = (int) intHandle.get(numbers, 4L);
~~~

`VarHandle` trả về có **value type** là carrier (`int.class`) và **coordinates** là segment + `long` byte offset. Nó áp dụng alignment constraint và scope/bounds checks như truy cập segment theo layout. Đây không phải “raw pointer trực tiếp bỏ qua kiểm tra”.

`MemoryLayout.varHandle(PathElement...)` cũng tồn tại để truy cập field trong struct/sequence theo **layout path**, thay vì tự cộng các magic offsets. Trong trường hợp một scalar đơn lẻ, `ValueLayout.varHandle()` đơn giản và tránh dựng path không cần thiết. Khi chuyển sang struct, xem thêm `byteOffset(...)` ở mục 8.

### 6.2. Lựa chọn giữa `get/set` và `VarHandle`

- **Đọc/ghi từng scalar đơn giản:** `segment.get(layout, byteOffset)` và `segment.set(...)` dễ đọc.
- **Chương trình tái sử dụng nhiều lần một layout/field:** `VarHandle` có thể được giữ như metadata và dùng để truy cập nhiều segments cùng shape; đừng giữ nó cùng segment đã đóng rồi dùng sai scope.
- **Struct/sequence có path:** `MemoryLayout.varHandle(...)` hoặc `byteOffset(...)` làm code ít phụ thuộc vào offsets hard-code.
- **Truy cập đồng thời/atomic:** không suy rằng một layout hợp lệ tự bảo đảm synchronization. Dùng access modes được VarHandle hỗ trợ và đồng bộ đúng theo contract; thao tác unaligned hoặc composite không tự có atomic semantics.

## 7. ValueLayout không tự tạo padding trong C struct

Đây là bẫy lớn của data layout. Xét struct C11:

~~~c
#include <stdint.h>

struct Record {
    uint8_t tag;
    int32_t value;
};
~~~

Trên các ABI thông dụng nơi `int32_t` có alignment 4, compiler đặt:

~~~text
byte offset:    0   1   2   3   4   5   6   7
contents:      tag pad pad pad [   value      ]
field size:      1     +3          +4
struct size:                       8 byte
struct align:                      4 byte
~~~

Không được mô tả bằng:

~~~java
// SAI đối với struct thông dụng ở trên: thiếu padding.
MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        ValueLayout.JAVA_INT.withName("value"));
~~~

Trong JDK 22, `MemoryLayout.structLayout(...)` **không tự chèn padding**. Hơn nữa, trường `JAVA_INT` cần bắt đầu ở offset align4; việc đặt ngay sau một byte thường khiến hàm factory từ chối layout không phù hợp alignment, thay vì “âm thầm sửa thành C struct”.

Mô tả có padding tường minh:

~~~java
MemoryLayout RECORD = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("tag"),
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT.withName("value")
);
~~~

Các tính chất của layout này:

- `RECORD.byteSize() == 8`: tổng 1 + 3 + 4.
- `RECORD.byteAlignment() == 4`: lớn nhất trong các member alignments.
- `RECORD.byteOffset(PathElement.groupElement("tag")) == 0`.
- `RECORD.byteOffset(PathElement.groupElement("value")) == 4`.

`MemoryLayout.paddingLayout(3)` chiếm ba byte **không mang trường dữ liệu**. Padding không phải giá trị bạn cần copy/tính toán; khi serialize và so sánh record, padding có thể chứa byte chưa khởi tạo hoặc khác nhau giữa các compiler/process. Đừng gửi byte padding thừa ra giao thức công khai nếu không có quy định rõ.

**Tail padding:** Một C struct có thể được compiler thêm byte ở cuối để kích thước mỗi element của một mảng struct tôn trọng alignment. Với layout Java phải khai báo kích thước/stride cuối phù hợp với C `sizeof(struct)`. Ví dụ struct có `int32_t` rồi `uint8_t` có thể cần ba byte padding ở cuối trên ABI align4. Không chỉ nghĩ về padding *giữa* fields.

### 7.1. Cách kiểm chứng layout từ C compiler

Đối với C header thực, dùng `sizeof`, `_Alignof` và `offsetof` (C11) để so sánh với Java `byteSize/byteAlignment/byteOffset`; không dựa vào phỏng đoán. `#pragma pack`, `__attribute__((packed))`, compiler flags và OS ABI có thể thay đổi cách đặt field; **FFM layout phải khớp binary được link**, không chỉ khớp hình dung ban đầu.

Bản C runnable để đo struct nằm ở mục 12. Đối với bài phức tạp, công cụ tạo binding như `jextract` có thể giảm lỗi nhập layout thủ công, nhưng vẫn phải review ownership, API version và ABI.

## 8. Dùng ValueLayout trong SequenceLayout và GroupLayout

`ValueLayout` là các viên gạch của memory layout phức hợp.

### 8.1. Array liên tiếp của ba int32

~~~java
// Mảnh Java minh họa:
MemoryLayout THREE_INTS =
        MemoryLayout.sequenceLayout(3, ValueLayout.JAVA_INT);

System.out.println(THREE_INTS.byteSize());      // 12
System.out.println(THREE_INTS.byteAlignment()); // 4
~~~

Size là 3×4=12 byte; alignment là alignment của element layout. `Arena.allocate(THREE_INTS)` có thể tạo một segment đúng size/alignment, rồi `getAtIndex(JAVA_INT, i)` truy cập các elements liên tục.

Cần khác biệt với **pointer tới C array**: ValueLayout không biết một pointer C đang có ít nhất ba phần tử hay không. `ValueLayout.ADDRESS` chỉ mô tả **giá trị địa chỉ**; bounds của vùng nó trỏ tới phải được chứng minh/thiết lập riêng, không tự rút ra từ “địa chỉ 8 byte”.

### 8.2. Struct và union

- `MemoryLayout.structLayout(...)` đặt fields liên tiếp theo layout bạn cung cấp; phải thêm padding để khớp C ABI.
- `MemoryLayout.unionLayout(...)` cho các member chung điểm bắt đầu; size của union là size lớn nhất trong các member layouts. C compiler có thể thêm tail alignment/padding; xác minh với target.
- `MemoryLayout.paddingLayout(n)` biểu diễn khoảng trống được bỏ qua khi đọc giá trị.
- `MemoryLayout.PathElement.groupElement("fieldName")` cho phép lấy `byteOffset(...)` hoặc tạo var handle tới field được đặt tên.

Khi một C function nhận **struct by value**, không chỉ nhớ offset fields: ABI còn quyết định cách truyền/nhận struct qua registers/stack và layout phải thỏa điều kiện linker. Một struct bạn đọc được từ `MemorySegment` không chắc là descriptor hợp lệ để truyền by value nếu size/alignment/padding không khớp target. Dùng `Linker.canonicalLayouts()` cho scalar C và so sánh `sizeof/offsetof` cho group C.

## 9. ValueLayout liên quan gì tới Linker, FunctionDescriptor và C ABI?

Một định nghĩa hàm C:

~~~c
#include <stdint.h>

/* C ABI ví dụ, không phải JNI entry point */
int32_t twice_i32(int32_t input);
~~~

Có thể được mô tả về return/argument layouts trong FFM bằng:

~~~java
// Mảnh minh họa: tạo descriptor, chưa lookup hoặc gọi native function.
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT, // C int32_t return
        ValueLayout.JAVA_INT  // C int32_t input
);
~~~

Khi `Linker.downcallHandle(...)` tạo `MethodHandle` dựa trên function descriptor, ValueLayout góp phần xác định **Java carrier** và **ABI signature**. Với descriptor trên, carrier int là phù hợp cho cả hai vị trí. Nhưng nếu C function nhận `long` thay `int32_t`, không được tự giữ `JAVA_INT` hay tự đổi sang `JAVA_LONG` mà không kiểm tra platform.

FFM native linker cung cấp:

~~~java
// Mảnh minh họa chạy trên JDK 22+, không phải toàn chương trình.
MemoryLayout cLong =
        Linker.nativeLinker().canonicalLayouts().get("long");
MemoryLayout cSizeT =
        Linker.nativeLinker().canonicalLayouts().get("size_t");
~~~

`canonicalLayouts()` trả mapping cho các kiểu C được ABI hỗ trợ. Ví dụ trên Linux x64, C `long` thường tương ứng `JAVA_LONG`; trên Windows x64 thường tương ứng `JAVA_INT`. `size_t` thường 64-bit trên 64-bit và 32-bit trên 32-bit. Khi cần mapping chính xác, tra theo native linker và C header thay vì nhân bản assumptions cho mọi target.

**Lưu ý quyền native access:** việc tạo layout/đọc một memory segment có scope hợp lệ không đồng nghĩa đã thực hiện foreign function call. Các **restricted operations** như `Linker.downcallHandle`, `SymbolLookup.libraryLookup`, `Linker.upcallStub` thường đòi `--enable-native-access` cho module gọi chúng theo chính sách của JDK. Ví dụ chính ở mục 10 không gọi thư viện ngoài hay restricted downcall; vì vậy không cần cấp native access chỉ để chạy các phép đọc/ghi `MemorySegment` do `Arena` cấp.

### 9.1. Vì sao pointer không phải `JAVA_LONG`?

Trên JVM 64-bit, `ADDRESS.byteSize()` thường 8, `JAVA_LONG.byteSize()` cũng 8. **Bằng kích thước không có nghĩa cùng ABI semantic.** `ADDRESS.carrier()` là `MemorySegment.class`, trong khi `JAVA_LONG.carrier()` là `long.class`. `FunctionDescriptor` của C pointer phải dùng `ADDRESS`, không dùng `JAVA_LONG` chỉ vì kích thước trên một target giống nhau.

Trên target 32-bit, pointer 4 byte trong khi Java `long` vẫn 8 byte: nhầm này còn làm sai cả size. `AddressLayout` còn hỗ trợ gắn target layout khi muốn mô tả pointer tới một vùng có shape xác định; tuy nhiên target layout không tự cấp phát memory hoặc chứng minh pointer bên C còn sống. Nếu C trả một địa chỉ, Java phải xử lý ownership, nullability, access bounds và native lifetime tương ứng.

## 10. Ví dụ Java 22+ đầy đủ: đo layout, ghi bytes và kiểm tra alignment

Tạo **một tệp** `ValueLayoutDemo.java` trong thư mục rỗng, không khai báo package. Không có mã C hay thư viện native đi kèm; ví dụ này minh họa đúng chức năng mô tả/bộ nhớ của `ValueLayout`.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;
import java.nio.ByteOrder;

public final class ValueLayoutDemo {
    public static void main(String[] args) {
        ValueLayout.OfInt nativeInt = ValueLayout.JAVA_INT;
        ValueLayout.OfInt bigEndian =
                ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);

        System.out.println("carrier=" +
                nativeInt.carrier().getSimpleName());
        System.out.println("size=" + nativeInt.byteSize());
        System.out.println("alignment=" + nativeInt.byteAlignment());
        System.out.println("nativeOrder=" +
                (nativeInt.order() == ByteOrder.nativeOrder()));
        System.out.println("addressCarrier=" +
                ValueLayout.ADDRESS.carrier().getSimpleName());

        MemoryLayout recordLayout = MemoryLayout.structLayout(
                ValueLayout.JAVA_BYTE.withName("tag"),
                MemoryLayout.paddingLayout(3),
                ValueLayout.JAVA_INT.withName("value")
        );
        long tagOffset = recordLayout.byteOffset(
                PathElement.groupElement("tag"));
        long valueOffset = recordLayout.byteOffset(
                PathElement.groupElement("value"));

        System.out.println("recordSize=" + recordLayout.byteSize());
        System.out.println("recordAlignment=" +
                recordLayout.byteAlignment());
        System.out.println("tagOffset=" + tagOffset);
        System.out.println("valueOffset=" + valueOffset);

        MemorySegment closedLater;
        try (Arena arena = Arena.ofConfined()) {
            // Cấp phát đúng base alignment 4, đủ 8 byte.
            MemorySegment numbers = arena.allocate(8, 4);
            closedLater = numbers;

            // Bất kể native little/big endian,
            // layout BIG_ENDIAN ghi đúng 01 02 03 04.
            numbers.set(bigEndian, 0, 0x01020304);
            String bytes = String.format("%02X %02X %02X %02X",
                    numbers.get(ValueLayout.JAVA_BYTE, 0) & 0xFF,
                    numbers.get(ValueLayout.JAVA_BYTE, 1) & 0xFF,
                    numbers.get(ValueLayout.JAVA_BYTE, 2) & 0xFF,
                    numbers.get(ValueLayout.JAVA_BYTE, 3) & 0xFF);
            System.out.println("bigEndianBytes=" + bytes);

            numbers.set(nativeInt, 4, 123);
            System.out.println("getAtByte4=" +
                    numbers.get(nativeInt, 4));
            System.out.println("getAtIndex1=" +
                    numbers.getAtIndex(nativeInt, 1));

            VarHandle intHandle = nativeInt.varHandle();
            intHandle.set(numbers, 4L, 456);
            System.out.println("varHandle=" +
                    (int) intHandle.get(numbers, 4L));

            MemorySegment record = arena.allocate(recordLayout);
            record.set(ValueLayout.JAVA_BYTE, tagOffset, (byte) 7);
            record.set(nativeInt, valueOffset, 77);
            System.out.println("recordTag=" +
                    record.get(ValueLayout.JAVA_BYTE, tagOffset));
            System.out.println("recordValue=" +
                    record.get(nativeInt, valueOffset));

            MemorySegment raw = arena.allocate(12, 4);
            raw.set(ValueLayout.JAVA_INT_UNALIGNED, 1, 1234);
            System.out.println("unalignedRead=" +
                    raw.get(ValueLayout.JAVA_INT_UNALIGNED, 1));

            try {
                raw.get(nativeInt, 1); // Offset 1 sai alignment 4.
                System.out.println("alignmentRejected=false");
            } catch (IllegalArgumentException expected) {
                System.out.println("alignmentRejected=true");
            }

            try {
                raw.get(nativeInt, 12); // Bắt đầu tại byte cuối + 1.
                System.out.println("boundsRejected=false");
            } catch (IndexOutOfBoundsException expected) {
                System.out.println("boundsRejected=true");
            }
        }

        try {
            closedLater.get(ValueLayout.JAVA_INT, 0);
            System.out.println("closedRejected=false");
        } catch (IllegalStateException expected) {
            System.out.println("closedRejected=true");
        }
    }
}
~~~

### 10.1. Lệnh biên dịch và chạy

JDK 22 trở lên:

~~~sh
javac ValueLayoutDemo.java
java ValueLayoutDemo
~~~

Windows Command Prompt hoặc PowerShell cũng dùng chính hai lệnh trên. Xác nhận phiên bản JDK trước:

~~~sh
java -version
javac -version
~~~

**Không thêm `--enable-preview`**: `java.lang.foreign` là API chính thức từ JDK 22. Ví dụ không làm downcall/upcall, do đó cũng không cần flag `--enable-native-access` chỉ để dùng `Arena` và `MemorySegment`. Nếu sau này thêm restricted native operations, phải cấu hình native-access đúng module/JDK.

### 10.2. Stdout dự kiến

~~~text
carrier=int
size=4
alignment=4
nativeOrder=true
addressCarrier=MemorySegment
recordSize=8
recordAlignment=4
tagOffset=0
valueOffset=4
bigEndianBytes=01 02 03 04
getAtByte4=123
getAtIndex1=123
varHandle=456
recordTag=7
recordValue=77
unalignedRead=1234
alignmentRejected=true
boundsRejected=true
closedRejected=true
~~~

Kết quả được thiết kế độc lập với CPU endianness: `ByteOrder.BIG_ENDIAN` cố định cách ghi bốn byte, còn `nativeOrder=true` chỉ kiểm tra layout chuẩn dùng thứ tự byte của host. Không in `ValueLayout.ADDRESS.byteSize()` hay `JAVA_LONG.byteAlignment()` dưới dạng hằng trong stdout, vì những thuộc tính này phụ thuộc nền tảng.

**Điều gì đã được chứng minh?**

1. `nativeInt.carrier()` là Java primitive `int.class`, size 4, alignment 4.
2. Đọc bằng byte offset 4 hoặc element index 1 đều lấy phần tử int thứ hai, nhưng con số đầu vào cho hai API có **đơn vị khác nhau**.
3. `VarHandle` mang Java carrier và byte-offset coordinate; dùng lại để đọc/ghi vào segment.
4. `Record` cần ba byte padding tường minh để trường `value` ở offset 4 và tổng size 8.
5. Với cùng vùng `raw`, layout unaligned cho phép offset 1 còn layout mặc định từ chối offset này.
6. Bounds check ngăn việc đọc bốn byte bắt đầu ở offset 12 của segment 12 byte.
7. `Arena.ofConfined()` đóng xong thì segment hết hiệu lực; thao tác Java sau đó bị từ chối thay vì âm thầm đọc vùng nhớ đã giải phóng.

**Giới hạn của ví dụ:** FFM kiểm tra accesses *từ Java*; ví dụ không chứng minh một C function nhận pointer sai là an toàn. Ví dụ cũng không tự đo ABI của C compiler. Phần sau chỉ ra cách xác minh layout C nếu cần tương tác thư viện thật.

## 11. Đọc kết quả đúng theo đơn vị: byte, bit, element và pointer

Hãy đặt các câu hỏi trước mỗi `segment.get/set`:

- **Offset hay index?** `get(JAVA_INT, 4)` đọc tại byte offset 4; `getAtIndex(JAVA_INT, 4)` đọc từ byte offset 16.
- **Byte size?** `JAVA_DOUBLE.byteSize() == 8` nghĩa là cần tám byte của segment, không phải tám Java elements.
- **Alignment?** Bắt đầu tại địa chỉ/offset có bội của `byteAlignment()` khi layout yêu cầu; segment base phải đúng căn chỉnh.
- **Byte order?** Native order hay một giao thức quy định BIG_ENDIAN/LITTLE_ENDIAN?
- **Signedness?** `JAVA_BYTE` carrier `byte` của Java là signed; C `uint8_t` có miền 0..255, cần `value & 0xFF` khi diễn giải dạng unsigned.
- **Address?** Nếu đọc `ADDRESS`, giá trị Java là `MemorySegment` biểu diễn pointer; không giả định nó có kích thước của vùng pointee hoặc lifetime độc lập.
- **Lifetime?** Arena còn mở không? Đây có phải thread được phép truy cập một confined segment không?
- **Ownership?** Segment được arena sở hữu hay trỏ vào malloc buffer của C? `Arena.close()` chỉ có thể tự quản lý phần tài nguyên thuộc scope tương ứng; không tự gọi C `free` cho mọi pointer trả về.

Một sai lệch rất phổ biến là tính `byteOffset = elementIndex + JAVA_INT.byteSize()` thay vì `elementIndex * JAVA_INT.byteSize()`; sai số này càng khó thấy khi array nhỏ. Với dữ liệu cấu trúc, dùng layout path/array element offset helpers thay vì công thức thủ công nếu có thể.

## 12. Chương trình C11 độc lập để kiểm chứng kích thước/alignment thật

Khi cần ánh xạ dữ liệu C, hãy hỏi compiler: `sizeof`, `_Alignof` và `offsetof` là công cụ xác minh cụ thể trên hệ điều hành/target.

Tạo `layout_contract.c`:

~~~c
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

struct Record {
    uint8_t tag;
    int32_t value;
};

int main(void) {
    printf("int32Size=%zu\n", sizeof(int32_t));
    printf("recordSize=%zu\n", sizeof(struct Record));
    printf("recordAlign=%zu\n", (size_t)_Alignof(struct Record));
    printf("tagOffset=%zu\n", offsetof(struct Record, tag));
    printf("valueOffset=%zu\n", offsetof(struct Record, value));
    return 0;
}
~~~

Linux/macOS dùng compiler có C11:

~~~sh
cc -std=c11 -Wall -Wextra -Wpedantic layout_contract.c -o layout_contract
./layout_contract
~~~

Windows với MSVC hỗ trợ C11, chạy từ Developer Command Prompt:

~~~bat
cl /nologo /std:c11 /W4 layout_contract.c
layout_contract.exe
~~~

Trên ABI x86_64/arm64 thông dụng, stdout thường là:

~~~text
int32Size=4
recordSize=8
recordAlign=4
tagOffset=0
valueOffset=4
~~~

Đây là **kết quả kỳ vọng trên ABI thông dụng**, không phải sự bảo đảm trên mọi compiler, packed setting hay kiến trúc. `int32_t` nếu tồn tại có chính xác 32 bit, nhưng cách căn chỉnh composite types cần được xác nhận bằng chương trình trên. Nếu C output khác `recordLayout.byteSize()/byteAlignment()/byteOffset(...)` trong Java, không chuyển struct giữa hai bên cho đến khi điều chỉnh mô tả đúng.

Tệp C này chạy **độc lập**, không yêu cầu JNI/FFM và không tạo shared library. Nó chỉ đo C ABI layout. Java sample ở mục 10 cũng chạy độc lập, không cần load `layout_contract`. Hai chương trình phục vụ hai nhiệm vụ kiểm tra khác nhau.

### 12.1. Khi nào phải kiểm tra tail padding?

Một C struct có dạng:

~~~c
struct Packet {
    int32_t id;
    uint8_t flag;
};
~~~

Trên ABI align4, `id` ở offset0 (4 byte), `flag` ở offset4 (1 byte), thường có **3 byte tail padding** để `sizeof(struct Packet) == 8`. Nếu layout Java chỉ cộng 4+1=5 byte, khi đưa nhiều record thành C array, stride sẽ sai. Cần layout mô tả đầy đủ 8 byte (bao gồm padding cuối), rồi xác minh `sizeof` bằng compiler của binary thật.

Với `#pragma pack(1)` hoặc một struct có C compiler extension, alignment/offset có thể khác. Không tự gán `*_UNALIGNED` theo thói quen: packed representation phải được xác nhận từ C target và native library đang chạy.

## 13. Lỗi thường gặp và cách sửa

| Triệu chứng / anti-pattern | Vấn đề thật | Cách sửa |
| --- | --- | --- |
| `carrier() == int.class` nên suy `C long` cũng là 4 byte | Java carrier không định nghĩa C ABI | Dùng `Linker.canonicalLayouts()` và header/compiler |
| `JAVA_LONG.byteAlignment()` luôn bằng 8 | Trên JDK 22, alignment còn phụ thuộc platform | Đọc `byteAlignment()` trên JVM đích |
| Lấy `JAVA_INT.byteSize()==4` rồi đọc ở byte offset 1 | Thiếu alignment mặc định 4 | Dùng offset aligned hoặc layout unaligned nếu dữ liệu thật là packed |
| `withByteAlignment(1)` “sửa” dữ liệu struct thiếu padding | Không đổi field offset đúng theo C ABI | Bổ sung padding/mô tả struct chính xác |
| `withOrder(BIG_ENDIAN)` nhưng tưởng buffer tự chuyển byte đã ghi trước | Layout chỉ quy định encoding tại access | Đọc/ghi lại bằng layout đúng order theo giao thức |
| `getAtIndex(JAVA_INT, 4)` bị hiểu là byte thứ 4 | Index element, không phải byte offset | Dùng `get(JAVA_INT, 4)` nếu muốn offset4 |
| Dùng `JAVA_CHAR` cho C `char*` UTF-8 | Java char 16-bit; C char thường 8-bit | Biểu diễn buffer byte và encoding có length rõ ràng |
| Dùng `JAVA_LONG` cho C pointer vì cùng 8 byte trên x64 | Pointer carrier và ABI khác long | Dùng `ValueLayout.ADDRESS` |
| Mô tả `structLayout(BYTE, INT)` không padding | Factory không tự align fields | Thêm `paddingLayout(...)` theo `offsetof` |
| C `long` trên Windows x64 mô tả bằng `JAVA_LONG` | Windows LLP64 C long 32-bit | Lấy canonical `"long"`/header ABI |
| Dùng layout đúng nhưng `Arena` đã đóng | Memory segment không còn alive | Bảo đảm owner/lifetime và truy cập trong scope |
| Confined segment đọc từ thread khác | Thread access không hợp lệ | Đọc ở owner thread, hoặc dùng arena thích hợp |
| C giữ pointer sau khi Java đóng arena | Native use-after-free | Dừng native users trước khi close arena |
| C gọi `free` trên memory do Java Arena sở hữu | Hai owner giải phóng cạnh tranh | Xác định rõ ai cấp/ai free; không double-free |
| Mô tả `ValueLayout.ADDRESS` rồi tự dereference mọi địa chỉ | Pointer không chứng minh region size/lifetime | Xác thực bounds/ownership trước khi truy cập pointee |
| Cho rằng FFM khiến mọi C code memory-safe | Bounds ở Java không bảo vệ C tùy ý | Test, sanitizer, ABI verification, API contract |

### 13.1. Hai lỗi phải phân biệt rõ

**Alignment error:** truy cập vẫn nằm trong segment theo số byte nhưng bắt đầu tại vị trí không thỏa `layout.byteAlignment()`. FFM Java access có thể ném `IllegalArgumentException`. Đừng dùng unchecked native pointer để “né” alignment check khi dữ liệu không thực sự unaligned-safe.

**Bounds error:** phép đọc cần vượt vùng `segment.byteSize()`, dù offset đã aligned. FFM Java access ném `IndexOutOfBoundsException`. Chuyển sang `JAVA_INT_UNALIGNED` **không** sửa lỗi vượt biên.

Lỗi khi arena đã đóng là **scope/lifetime error** (thường `IllegalStateException`), còn truy cập confined segment từ sai thread có thể ném `WrongThreadException`. Bốn nhóm lỗi này phản ánh **bốn điều kiện độc lập** cần bảo đảm.

## 14. Bài luyện tập có đáp án và tiêu chí kiểm chứng

1. **Đơn vị:** Segment có 16 byte. `getAtIndex(JAVA_INT, 2)` bắt đầu ở byte offset nào? Trả lời: `2*4=8`; cần byte 8..11 và alignment phù hợp.
2. **Kiểu:** `ValueLayout.ADDRESS.carrier()` là gì? Trả lời: `MemorySegment.class`, không phải `long.class`, kể cả khi pointer rộng 8 byte.
3. **Order:** Ghi `0x01020304` bằng `JAVA_INT.withOrder(BIG_ENDIAN)`. Bốn byte đầu là gì? Trả lời: `01 02 03 04`.
4. **Alignment:** Dùng `JAVA_INT` ở byte offset 2 trên một segment base aligned4. Có hợp lệ? Không; aligned int access đòi offset phù hợp alignment4.
5. **Unaligned:** Dùng `JAVA_INT_UNALIGNED` ở offset2 với segment size4. Có hợp lệ? Không; tuy alignment1 nhưng cần byte2..5, vượt biên.
6. **Struct:** C struct gồm `uint8_t kind; int32_t value;` theo ABI align4. Offset trường value là mấy? Thường 4; kiểm chứng với `offsetof`.
7. **Tail padding:** C struct gồm `int32_t id; uint8_t flag;` theo ABI align4. Vì sao `sizeof` thường là 8 thay vì5? Để stride của array elements vẫn align4.
8. **C long:** Vì sao không dùng Java `JAVA_LONG` cho C `long` trên mọi OS? Vì `long` C thường rộng32 trên Windows x64 nhưng64 trên Linux x64.
9. **Lifetime:** Dùng `Arena.ofConfined()` rồi giữ `MemorySegment` sau try-with-resources, đọc được không? Không; scope đã đóng.
10. **FFM function:** C `int32_t calculate(int32_t)` mô tả layout nào cho tham số/trả? `JAVA_INT` khi ABI định nghĩa kiểu đúng int32_t và layout tương thích; nếu dùng C `long` thì xét canonical mapping.
11. **Signedness:** C `uint8_t` chứa 255 đọc vào Java `byte` thành bao nhiêu? Bit pattern là `0xFF`, Java `byte` diễn giải là -1; `b & 0xFF` ra 255.
12. **Unknown pointer:** C trả `void *`, FFM `ADDRESS` trả Java carrier gì, và tại sao không thể tự đọc 100 byte? `MemorySegment`; pointer value chưa chứng minh region extent/ownership nên cần contract native riêng.

Đáp án phải được đối chiếu với **đơn vị**, **layout**, **ABI** và **lifetime**, không chỉ nhìn số byte. Các câu về struct và C type có điều kiện về target ABI, vì portable Java wrapper phải làm việc với binary thực, không phải giả thiết một hệ điều hành duy nhất.

## 15. Checklist trước khi dùng ValueLayout trong dự án

- **Phiên bản:** JDK baseline có `java.lang.foreign.ValueLayout` chuẩn (JDK22+) chưa? Nếu Java 17/21, đã tách ví dụ incubator/preview đúng version chưa?
- **Carrier:** `carrier()` là primitive Java đúng hay `MemorySegment` cho pointer? MethodHandle type có khớp không?
- **Size:** `byteSize()` phản ánh số byte **một** giá trị; đã chuyển count sang byte size an toàn và xử lý overflow chưa?
- **Alignment:** Base segment và mọi byte offset có đáp ứng `byteAlignment()`? Có đang lạm dụng `*_UNALIGNED` che sai layout không?
- **Byte order:** Dữ liệu là native ABI hay network/file format? `order()`/`withOrder(...)` có khớp không?
- **Composite:** `structLayout` đã thêm padding/tail padding cần thiết? `byteOffset(...)` có khớp `offsetof` thật không?
- **Pointer:** `ADDRESS` không bị nhầm với `JAVA_LONG`; null/size/ownership của pointee có được xác định rõ?
- **C ABI:** Với `long`, `size_t`, `wchar_t`, `bool`, struct/callback, đã đối chiếu canonical layouts và header/compiler đích chưa?
- **Lifetime:** Arena có còn alive khi đọc/ghi/downcall? Native code có đang giữ pointer sau arena close không?
- **Thread:** Confined/shared arena có phù hợp caller threads? Không có access từ sai thread?
- **Safety:** Có test misalignment, out-of-bounds, closed-scope, wrong-endianness, unsigned values và dữ liệu struct packed không?
- **Native access:** Nếu thêm `Linker.downcallHandle`, `SymbolLookup.libraryLookup` hay `upcallStub`, đã cấp quyền native access cho đúng module theo JDK deployment chưa?
- **Build/verify:** Có run Java demo thực trên target JDK, so sánh C `sizeof/alignof/offsetof` và kiểm tra native library đúng OS/CPU/ABI chưa?

**Kết luận:** `ValueLayout` không chỉ là “tên kiểu dữ liệu”. Nó gắn **Java carrier** với **độ rộng byte**, **ràng buộc căn chỉnh** và **thứ tự byte** để FFM đọc/ghi memory có cấu trúc. Khi xuống C ABI, bạn còn phải đối chiếu **cách compiler thật bố trí dữ liệu** và quản lý **lifetime** của vùng nhớ. Phân biệt những lớp này sẽ ngăn được lỗi sai offset, sai kiểu carrier, sai padding, sai endianness và nhiều crash khó chẩn đoán.

### Tài liệu tham khảo chính thức (JDK 22)

- Oracle, [`ValueLayout` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): `carrier`, `order`, hằng `JAVA_*`, `ADDRESS` và alignment khác nhau theo nền tảng.
- Oracle, [`MemoryLayout` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): `byteSize`, `byteAlignment`, `structLayout`, `paddingLayout`, `sequenceLayout`, `byteOffset`, var handles.
- Oracle, [`MemorySegment` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `get/set`, `getAtIndex/setAtIndex`, bounds, alignment, scope và thread checks.
- Oracle, [`Arena` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): cấp phát memory đúng layout/alignment và thời hạn scope.
- Oracle, [`Linker` API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): C ABI mappings, `canonicalLayouts`, `FunctionDescriptor`, downcall/upcall.
- OpenJDK, [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM chính thức từ JDK 22.