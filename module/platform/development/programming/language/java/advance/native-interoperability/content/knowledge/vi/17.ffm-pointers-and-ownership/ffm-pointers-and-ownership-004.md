# reinterpret thay đổi biên nhìn thấy mà không xác minh vùng nhớ thực

## 1. Vấn đề trung tâm: một kích thước được khai báo không phải một kích thước đã được xác minh

Trong **Foreign Function & Memory API (FFM)**, một `MemorySegment` là cách Java nhìn vào một vùng nhớ. Mỗi segment có ít nhất ba đặc điểm quan trọng: **địa chỉ bắt đầu**, **kích thước nhìn thấy** (spatial bounds, tính bằng byte), và **scope/vòng đời** (temporal bounds). Một segment cũng chịu quy tắc truy cập theo thread và có thể được đánh dấu read-only.

`MemorySegment.reinterpret(...)` là nhóm thao tác **restricted** cho phép tạo một segment mới biểu diễn **cùng địa chỉ bộ nhớ** nhưng với kích thước nhìn thấy khác, hoặc scope khác. Điểm nguy hiểm không nằm ở cú pháp mà ở **lời khẳng định do người gọi đưa ra**: Java có thể coi view mới dài 100 byte dù vùng nhớ native thật sự chỉ được cấp 10 byte. `reinterpret` **không hỏi OS, allocator hoặc native library** để xác minh giả định ấy.

Cần ghi nhớ ngay:

> **`reinterpret(100)` không cấp phát 100 byte, không mở rộng vùng nhớ C, không sao chép dữ liệu và không chứng minh có 100 byte hợp lệ. Nó chỉ tạo một view mang metadata “100 byte” cho cùng địa chỉ.**

Nếu code sau đó đọc/ghi trong phần view vượt quá allocation thực, các kiểm tra **theo biên được khai báo** có thể cho qua, nhưng truy cập máy thật là **out-of-bounds**, có thể làm JVM crash hoặc âm thầm gây memory corruption. Java không bảo đảm một `IndexOutOfBoundsException` có thể cứu được trường hợp này.

Bài tập trung vào **JDK 22+**, khi FFM trở thành API chuẩn theo JEP 454; bản JDK 21 là FFM preview theo JEP 442 nên cần `--enable-preview` và phải đối chiếu API theo đúng version.

## 2. Ba loại biên phải phân biệt

### 2.1. Spatial bounds: kích thước mà Java nhìn thấy

Một segment có:

~~~java
long visibleBytes = segment.byteSize();
~~~

Đây là **trích đoạn** trong phương thức đã có biến `segment` hợp lệ.

Khi đọc một `int` 4 byte tại byte offset 8, API kiểm tra liệu khoảng byte 8–11 có nằm trong đoạn từ 0 tới `byteSize() - 1` hay không. Các phép đọc/ghi như `get(ValueLayout.JAVA_INT, offset)` thực hiện kiểm tra này đối với **segment được đưa vào thao tác**.

Với segment bình thường do `Arena.allocate(16)` tạo, Java biết allocation có ít nhất 16 byte và có thể chặn truy cập tại offset 16. Nhưng với `reinterpret(24)`, Java chỉ biết **view mới khai báo 24 byte**; bản thân thao tác reinterpret không kiểm tra liệu 8 byte bổ sung có tồn tại thật.

### 2.2. Temporal bounds: bộ nhớ còn sống bao lâu

`MemorySegment.scope()` xác định vòng đời mà Java dùng để kiểm tra hợp lệ. Segment gắn với `Arena.ofConfined()` không còn hợp lệ sau khi arena đóng. Segment chỉ mang global scope thì `scope().isAlive()` có thể luôn trả `true`, ngay cả khi một **native allocator riêng** đã `free` vùng nhớ ở cùng địa chỉ.

**Scope còn sống không chứng minh backing memory còn sống.** Java không thể tự biết native library đã thu hồi hoặc tái sử dụng con trỏ ở bên ngoài cơ chế sở hữu của FFM.

### 2.3. Ownership: ai chịu trách nhiệm cấp phát/giải phóng?

Ownership không đồng nhất với spatial/temporal bounds:

| Thành phần | Nó cho biết gì? | Nó không cho biết gì? |
|---|---|---|
| `segment.address()` | Địa chỉ bắt đầu | Kích thước allocation, có thể đọc/ghi hay chưa |
| `segment.byteSize()` | **Biên nhìn thấy** của view | Allocation thực có lớn tương ứng hay không nếu view bị reinterpret |
| `segment.scope()` | Biên thời gian/thống kê lifetime theo FFM | Native library đã `free` hay chưa |
| `Arena` dùng để allocate | Có thể là chủ sở hữu backing memory | Không sở hữu mọi con trỏ chỉ vì chúng được gắn với scope ấy |
| `reinterpret(newSize)` | Tạo view mới cùng địa chỉ và scope với kích thước mới | Không thực hiện `malloc`, `realloc`, `memcpy` hoặc kiểm chứng vùng nhớ |
| `reinterpret(size, arena, cleanup)` | Tạo view cùng địa chỉ, kích thước/scope đã yêu cầu và tùy chọn cleanup | Không tự động biến một con trỏ lạ thành allocation có chủ sở hữu đúng |

**Quy tắc thiết kế:** chỉ có thể mở rộng view khi có **bằng chứng đáng tin** rằng backing allocation thật sự chứa tối thiểu số byte yêu cầu, trong toàn bộ thời gian sử dụng view.

## 3. Vì sao Java nhận con trỏ native dưới dạng segment dài 0?

Một hàm C có thể trả về `void *`, `char *` hoặc `int *`. Giá trị con trỏ mang **địa chỉ**, nhưng thường **không mang kích thước allocation** hoặc thông tin “ai phải free”. Ví dụ:

~~~c
/* C signature minh họa, chưa có implementation. */
void *get_buffer(void);
~~~

Chỉ từ prototype này, Java không thể biết con trỏ trả về trỏ tới một byte, một mảng 4 KiB, hay bộ nhớ đã bị giải phóng. Vì vậy FFM thường biểu diễn con trỏ nhận từ foreign functions, upcall arguments hoặc đọc qua `ValueLayout.ADDRESS` bằng một **zero-length native segment**:

~~~text
Native pointer: 0x1234...  (chỉ mang địa chỉ)
        |
        v
FFM MemorySegment [address = 0x1234..., byteSize = 0]
        |
        | get(JAVA_BYTE, 0) -> không hợp lệ vì view có 0 byte
        |
        | reinterpret(16)  [NGƯỜI GỌI CAM KẾT có ít nhất 16 byte]
        v
FFM MemorySegment [address = 0x1234..., byteSize = 16]
        |
        | get(JAVA_INT, 12) -> nằm trong biên view
        v
Nhưng FFM KHÔNG chứng minh native allocator đã cấp đủ 16 byte!
~~~

**Zero-length** là biện pháp phòng vệ: không thể tự ý dereference một địa chỉ có độ dài chưa rõ. `reinterpret` là ranh giới mà người viết binding **chủ động nhận trách nhiệm** xác định số byte và lifetime hợp lệ.

### 3.1. Một con trỏ đọc từ memory sẽ có global scope

Theo JDK 22, nếu đọc địa chỉ qua:

~~~java
MemorySegment pointer = slot.get(ValueLayout.ADDRESS, 0);
~~~

thì `pointer` thường có **`byteSize() == 0`** và **global scope**. Scope ấy luôn alive, nhưng đây là **metadata mặc định của wrapper địa chỉ**, không phải lời bảo đảm rằng địa chỉ thực nằm trong allocation sống vô hạn.

Tương tự:

~~~java
MemorySegment pointer = MemorySegment.ofAddress(address);
~~~

trả một native segment dài 0 bao quanh địa chỉ được cung cấp. `ofAddress` **không cấp phát** và không xác minh địa chỉ. Nếu `address == 0` thì nó biểu diễn null pointer; tuyệt đối không reinterpret thành kích thước dương rồi dereference `NULL`.

Hai đoạn trên là **trích đoạn minh họa**; `slot` và `address` phải được khai báo hợp lệ trong chương trình thật.

## 4. Các overload reinterpret ở FFM chuẩn JDK 22

| API | Kết quả về kích thước | Kết quả về scope | Lưu ý |
|---|---|---|---|
| `segment.reinterpret(long newSize)` | `newSize` | **Giữ nguyên scope** của segment nguồn | Không tự xác minh backing allocation; không cấp phát |
| `segment.reinterpret(Arena arena, Consumer<MemorySegment> cleanup)` | **Giữ nguyên `byteSize()`** | Scope của arena được cung cấp | Có thể đăng ký cleanup nếu có quyền giải phóng vùng native |
| `segment.reinterpret(long newSize, Arena arena, Consumer<MemorySegment> cleanup)` | `newSize` | Scope của arena được cung cấp | Thay cả spatial và temporal bounds, cần xác minh cả hai |

Ba overload trên đều là **restricted methods** và chỉ áp dụng cho **native segments**, không phải heap segments. Nếu người gọi không có quyền native access trong chế độ JVM đang sử dụng, có thể gặp `IllegalCallerException`; `newSize < 0` gây `IllegalArgumentException` với overload có kích thước.

Trong JDK 22, code chạy từ **classpath (unnamed module)** có thể cấp quyền rõ ràng như sau:

~~~bash
javac --release 22 ReinterpretViews.java
java --enable-native-access=ALL-UNNAMED ReinterpretViews
~~~

Đây là lệnh cho ví dụ đầy đủ ở phần sau. Nếu ứng dụng ở **named module**, cấp quyền theo tên module phù hợp thay vì `ALL-UNNAMED`. Một số bản JDK dùng cảnh báo cho restricted operations khi chưa cấp quyền; dùng flag tường minh để tránh phụ thuộc vào chế độ warning/default của runtime.

**Một cách đổi view không làm thay đổi view cũ.** Các `MemorySegment` là đối tượng mô tả immutable/value-based; `reinterpret` trả về một reference mới, không sửa `byteSize()` của biến source.

## 5. Ví dụ đầu tiên — nới rộng metadata nhưng chỉ truy cập dữ liệu thật đã cấp phát

Ví dụ chạy được trên **JDK 22+** sẽ cố ý yêu cầu view 24 byte trên một allocation thật 16 byte để cho thấy **sự khác nhau giữa metadata và backing memory**. Chương trình **không bao giờ đọc hoặc ghi** phần ngoài 16 byte đã được cấp phát.

### 5.1. Tệp `ReinterpretViews.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ReinterpretViews {
    public static void main(String[] args) {
        MemorySegment wider;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment original = arena.allocate(16);

            original.setAtIndex(ValueLayout.JAVA_INT, 0, 10);
            original.setAtIndex(ValueLayout.JAVA_INT, 1, 20);
            original.setAtIndex(ValueLayout.JAVA_INT, 2, 30);
            original.setAtIndex(ValueLayout.JAVA_INT, 3, 40);

            // Một view 24 byte trên cùng allocation thật 16 byte.
            // Chỉ tạo view; KHÔNG dereference phần 16..23.
            wider = original.reinterpret(24);

            System.out.println("original bytes = " + original.byteSize());
            System.out.println("wider bytes = " + wider.byteSize());
            System.out.println("same address = "
                    + (original.address() == wider.address()));

            // Đọc trong 16 byte thực sự được cấp phát là hợp lệ.
            System.out.println("valid value = "
                    + wider.getAtIndex(ValueLayout.JAVA_INT, 3));

            // Slice an toàn trong phạm vi original: bytes 8..15.
            MemorySegment slice = original.asSlice(8, 8);
            System.out.println("slice bytes = " + slice.byteSize());
            System.out.println("slice value = "
                    + slice.getAtIndex(ValueLayout.JAVA_INT, 1));

            try {
                original.asSlice(12, 8);
                throw new AssertionError("slice must not exceed 16 bytes");
            } catch (IndexOutOfBoundsException ex) {
                System.out.println("oversized slice = rejected");
            }

            // Điều này chỉ kiểm tra view đã KHAI BÁO, không dereference.
            System.out.println("wider claims room = "
                    + (wider.byteSize() >= 20));
        }

        // reinterpret(24) giữ scope của original là arena đã đóng.
        System.out.println("wider alive after close = "
                + wider.scope().isAlive());

        try {
            wider.get(ValueLayout.JAVA_INT, 0);
            throw new AssertionError("closed scope must not be read");
        } catch (IllegalStateException ex) {
            System.out.println("after close = rejected");
        }
    }
}
~~~

### 5.2. Lệnh chạy

Chọn **JDK 22** (không phải JDK 21 preview):

~~~bash
java -version
javac -version
javac --release 22 ReinterpretViews.java
java --enable-native-access=ALL-UNNAMED ReinterpretViews
~~~

**Stdout dự kiến:**

~~~text
original bytes = 16
wider bytes = 24
same address = true
valid value = 40
slice bytes = 8
slice value = 40
oversized slice = rejected
wider claims room = true
wider alive after close = false
after close = rejected
~~~

Giải thích từng kết quả:

1. `arena.allocate(16)` cấp phát thật **16 byte**. Bốn lần `setAtIndex(JAVA_INT, i, value)` ghi bốn `int` 4 byte tại các offset 0, 4, 8 và 12.
2. `original.reinterpret(24)` **không cấp thêm 8 byte**: `original.byteSize() == 16` nhưng `wider.byteSize() == 24`. Hai view bắt đầu tại **cùng địa chỉ**.
3. `wider.getAtIndex(JAVA_INT, 3)` chỉ đọc các byte 12..15 **nằm trong allocation gốc**, nên nhận 40.
4. `original.asSlice(8, 8)` tạo sub-view trong biên thật đã biết và có hai `int`; phần tử index 1 trả 40.
5. `original.asSlice(12, 8)` cần byte 12..19 và bị **chặn** dựa trên biên gốc 16. `asSlice` khác `reinterpret` vì nó không mở rộng biên qua đoạn đã biết.
6. `wider.byteSize() >= 20` là `true` nhưng **chỉ có nghĩa view tự khai có đủ byte cho một phép đọc tại offset 16**. Ví dụ **không thực hiện phép đọc đó**.
7. Khi try-with-resources đóng `arena`, scope của `wider` cũng hết hiệu lực, nên đọc dù ở offset 0 bị từ chối bằng `IllegalStateException`.

**Tuyệt đối không thêm** `wider.get(ValueLayout.JAVA_INT, 16)` để “xem JVM có ném lỗi không”: nó nằm trong metadata 24 byte nhưng **ngoài allocation 16 byte**, có nguy cơ truy cập bộ nhớ không thuộc quyền sở hữu. Không có bảo đảm Java sẽ ném `IndexOutOfBoundsException`; chạy thử kiểu này có thể gây crash hoặc ghi/đọc dữ liệu không liên quan.

## 6. Sơ đồ “biên nhìn thấy” khác “vùng nhớ thực”

~~~text
Backing allocation thực do arena cấp phát: 16 byte

Địa chỉ gốc
    |
    v
    +----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
    |  0 |  1 |  2 |  3 |  4 |  5 |  6 |  7 |  8 |  9 | 10 | 11 | 12 | 13 | 14 | 15 |
    +----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
    <---------------------- 16 byte được cấp phát thật ------------------------------>

original.byteSize() = 16
    [------------------------------------------------------------]

wider = original.reinterpret(24)
    [------------------------------------------------------------][................]
                                                                  16..23:
                                                         metadata khai báo thêm;
                                                         KHÔNG CÓ chứng cứ
                                                         allocation thật có thêm

original.asSlice(8, 8)
                                    [----------------------------]
                                    chỉ còn 8 byte hợp lệ của original
~~~

Điểm cần nhận thức: **`byteSize()` không phải hệ thống phát hiện độ lớn vùng nhớ qua `malloc_usable_size`, OS page map hoặc C allocator**. Kết quả của `reinterpret` là **một assertion của lập trình viên**, không phải một lần xác thực. Ngay cả khi một thử nghiệm đọc vượt allocation “có vẻ thành công” do vùng nhớ bên cạnh tình cờ mapped, mã vẫn có thể sai nghiêm trọng.

## 7. Ví dụ thứ hai — con trỏ đọc từ memory có 0 byte, sau đó gắn biên được biết rõ

Một trường hợp hợp lý của `reinterpret` là Java nhận một **địa chỉ đã biết nguồn gốc và kích thước**. Để tránh phụ thuộc compiler C, ví dụ này mô phỏng native pointer bằng cách lưu địa chỉ của một allocation **do chính Java cấp phát** vào một ô memory `ADDRESS` rồi đọc lại.

### 7.1. Tệp `PointerReinterpret.java` (JDK 22+)

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class PointerReinterpret {
    public static void main(String[] args) {
        MemorySegment rawPointer;
        MemorySegment scopedView;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment numbers = arena.allocateFrom(
                    ValueLayout.JAVA_INT, 11, 22, 33, 44
            );

            // Một ô vùng nhớ chứa native pointer.
            MemorySegment slot = arena.allocate(ValueLayout.ADDRESS);
            slot.set(ValueLayout.ADDRESS, 0, numbers);

            // Đọc pointer: chỉ có địa chỉ, chưa biết độ dài.
            rawPointer = slot.get(ValueLayout.ADDRESS, 0);

            System.out.println("raw bytes = " + rawPointer.byteSize());
            System.out.println("raw scope alive = "
                    + rawPointer.scope().isAlive());

            // Kích thước chính xác lấy từ allocation do chúng ta sở hữu.
            // Scope mới trùng arena thật đã cấp phát, không có callback free.
            scopedView = rawPointer.reinterpret(
                    numbers.byteSize(), arena, null
            );

            System.out.println("scoped bytes = " + scopedView.byteSize());
            System.out.println("scoped value = "
                    + scopedView.getAtIndex(ValueLayout.JAVA_INT, 2));
        }

        System.out.println("scoped alive after close = "
                + scopedView.scope().isAlive());

        // Chú ý: rawPointer vẫn báo scope alive sau khi arena đã đóng.
        // Điều này KHÔNG làm backing memory còn hợp lệ.
        System.out.println("raw scope alive after close = "
                + rawPointer.scope().isAlive());
    }
}
~~~

Lệnh chạy:

~~~bash
javac --release 22 PointerReinterpret.java
java --enable-native-access=ALL-UNNAMED PointerReinterpret
~~~

**Stdout dự kiến:**

~~~text
raw bytes = 0
raw scope alive = true
scoped bytes = 16
scoped value = 33
scoped alive after close = false
raw scope alive after close = true
~~~

Cơ chế:

- `numbers` là allocation 16 byte thật, có scope của `arena`.
- `slot.get(ValueLayout.ADDRESS, 0)` đưa giá trị con trỏ ra thành **zero-length segment** có **global scope**. Scope toàn cục **không chứng minh backing memory có lifetime toàn cục**.
- `rawPointer.reinterpret(numbers.byteSize(), arena, null)` sử dụng kích thước **đã biết đáng tin** từ allocation và gắn view vào **chính arena sở hữu vùng nhớ**. `null` cleanup ở đây là cố ý: arena đã tự giải phóng allocation của `numbers` khi đóng, nên không thêm một bước `free` khác.
- `scopedView.getAtIndex(JAVA_INT, 2)` đọc byte 8..11 của backing 16 byte, nên cho 33.
- Sau close, `scopedView.scope().isAlive()` là `false`; ngược lại wrapper `rawPointer` vẫn có global scope và báo `true`, dù địa chỉ của nó có thể trỏ tới vùng đã bị thu hồi. **Tuyệt đối không dereference rawPointer sau close.**

Đây là trường hợp `reinterpret` **có cơ sở an toàn** vì kích thước và owner được biết từ chính allocation mà ta kiểm soát, không phải do đoán hoặc dựa trên việc chương trình “chưa crash”.

### 7.2. Cách dùng sai trong ứng dụng thực

Mẫu sau **SAI, không chạy**:

~~~java
// Một native pointer không rõ backing allocation/lifetime.
MemorySegment untrusted = MemorySegment.ofAddress(unknownAddress);
MemorySegment assumed = untrusted.reinterpret(4096);
// SAI: lập tức đọc/ghi 4096 byte như thể chúng được cấp phát thật.
// assumed.getAtIndex(ValueLayout.JAVA_INT, 1023);
~~~

Đây là **pseudocode minh họa lỗi**; biến `unknownAddress` chưa được khai báo và ví dụ cố ý không có dereference. `4096` chỉ là một con số đoán; không có cơ sở nào cho rằng native allocator cấp một page hay pointer còn hiệu lực.

## 8. Ba overload: phân biệt đổi size, đổi scope và callback cleanup

### 8.1. `reinterpret(long newSize)`

~~~java
MemorySegment resized = original.reinterpret(verifiedByteCount);
~~~

Đây là **trích đoạn** với `original` native segment và `verifiedByteCount` đã được xác thực ngoài JNI/FFM theo hợp đồng native. View mới có **cùng address và scope**; chỉ đổi `byteSize()`.

Nếu `original` thuộc arena đã được đóng thì việc reinterpret không biến backing memory sống lại. View không phải một owner mới. Nếu `newSize` vượt actual allocation, kiểm tra FFM vẫn dựa trên **newSize khai báo** và không bảo vệ phần vượt ấy.

### 8.2. `reinterpret(Arena arena, Consumer<MemorySegment> cleanup)`

~~~java
MemorySegment rebound = pointer.reinterpret(targetArena, null);
~~~

Đây là **trích đoạn**, không dùng khi `targetArena` hay `pointer` chưa được định nghĩa. API giữ nguyên kích thước, đổi **temporal bounds** theo arena mới. Nếu nguồn là pointer dài 0, view kết quả **vẫn dài 0**; không thể đọc dữ liệu chỉ vì đã đổi scope.

Đổi scope không tự động chuyển quyền sở hữu backing allocation. Nếu arena mới sống lâu hơn backing pointer thực, có thể phát sinh **use-after-free** mặc dù Java cho rằng scope vẫn alive.

### 8.3. `reinterpret(long, Arena, Consumer<MemorySegment>)`

~~~java
MemorySegment managedView = pointer.reinterpret(
        verifiedByteCount, ownerArena, cleanupAction
);
~~~

Đây là **trích đoạn**: `cleanupAction` chỉ nên được truyền khi có **hợp đồng giải phóng chính xác**. Việc thay đổi size/lifetime và đăng ký cleanup có thể tạo được một wrapper với API gần giống allocation Java, nhưng chính **lập trình viên binding** phải chứng minh:

1. `pointer` trỏ đến ít nhất `verifiedByteCount` byte hợp lệ.
2. Pointer còn sống suốt thời gian `ownerArena` tồn tại, không bị native library free sớm.
3. Cleanup action có quyền giải phóng đúng allocation đó bằng **đúng hàm giải phóng**, **đúng một lần**.
4. Không còn Java/native consumer dùng con trỏ sau khi arena đóng và callback giải phóng.

Nếu `cleanupAction == null`, phương thức **không tự biết** nên gọi C `free` hay hàm của thư viện. Nếu pointer được `malloc` ở C rồi không có cleanup/release hợp lệ, bạn có thể tạo **native memory leak**. Ngược lại, nếu pointer được cấp qua chính `Arena.allocate` mà bạn còn gọi thêm C `free` trong callback, có thể tạo **double-free**.

### 8.4. Cleanup action nhận một segment mới

Theo tài liệu JDK 22, callback cleanup nhận một **fresh segment** có **global scope**, cùng địa chỉ và kích thước tương ứng. Nó được cung cấp để gọi đúng native deallocator trong quá trình cleanup; không được lưu/đưa segment ấy cho bên ngoài dùng sau khi backing memory đã bị thu hồi.

Đặc biệt, nếu dùng `Arena.ofAuto()` làm arena đích, cleanup action **không được vô tình giữ reference** khiến arena không thể trở thành unreachable, vì như vậy runtime không thể kích hoạt dọn native memory. Đối với native code có ownership phức tạp, cân nhắc tạo một wrapper sở hữu tài nguyên với `AutoCloseable` và lifecycle minh bạch.

## 9. Sự khác nhau giữa reinterpret, asSlice và withTargetLayout

| API | Có thể làm view dài hơn backing allocation đã biết? | Có thay đổi owner/lifetime? | Cách suy nghĩ |
|---|---|---|---|
| `segment.asSlice(offset, bytes)` | **Không vượt `byteSize()` của segment nguồn** | Giữ scope nguồn | Thu hẹp/đổi điểm đầu **trong biên đã biết** |
| `segment.reinterpret(bytes)` | **Có thể khai báo dài hơn**, không được FFM xác minh | Giữ scope nguồn | Khẳng định mới về **spatial bounds** |
| `segment.reinterpret(bytes, arena, cleanup)` | **Có thể khai báo dài hơn** | Đổi scope, có optional cleanup | Khẳng định mới về **size và lifetime** |
| `ValueLayout.ADDRESS.withTargetLayout(layout)` | Thêm kích thước view khi đọc pointer | Pointer vẫn cần lifetime thật được bảo đảm | Đưa layout đích vào pointer metadata, cũng là restricted |
| `segment.asReadOnly()` | Không làm dài view | Giữ scope | Chặn ghi qua view, **không xác minh size/owner** |

**`asSlice` là lựa chọn mặc định** khi bạn chỉ cần một cửa sổ nhỏ trong một segment đã có kích thước đáng tin. Nó kiểm tra biên dựa trên `segment.byteSize()` của **nguồn**. Nếu nguồn đã là alias `reinterpret` khai báo quá lớn, `asSlice` trên alias cũng **không thể khôi phục kích thước thật**: nó chỉ biết biên alias được khai báo.

`AddressLayout.withTargetLayout(layout)` giúp tránh gọi `reinterpret` tường minh khi pointer tới dữ liệu có bố cục cố định. Tuy nhiên, **layout cũng do lập trình viên cung cấp** và phương thức này là **restricted**: một layout sai có thể làm pointer view có kích thước/kiểu không đúng với bộ nhớ thật.

`asReadOnly()` hữu ích khi muốn cấm ghi qua một view, nhưng **không ngăn native code khác thay đổi vùng nhớ** và không xác minh pointer còn alive. Một view read-only với kích thước sai vẫn có thể làm JVM đọc ngoài allocation.

## 10. Cần bằng chứng gì để reinterpret một con trỏ từ thư viện C?

Không phải mọi pointer đều nguy hiểm như nhau. Một native API tốt có thể trả **pointer và chiều dài**, hoặc trả một handle có method truy vấn size và hàm release rõ ràng.

Ví dụ thiết kế C:

~~~c
/* API minh họa; không phải chương trình C đầy đủ. */
typedef struct Buffer {
    unsigned char *data;
    size_t length;
} Buffer;

/* Hợp đồng C cần nêu rõ:
   - data trỏ đến ít nhất length byte nếu length > 0
   - ai sở hữu data
   - khi nào data hết hiệu lực
   - caller có thể ghi hay chỉ được đọc
   - hàm nào phải gọi để giải phóng (nếu caller sở hữu) */
~~~

Chỉ thấy field `length` **chưa đủ** nếu thư viện có bug, field bị untrusted data điều khiển, pointer đã được free, length bị làm tròn sai hoặc là số byte của một view khác. Tuy nhiên, một hợp đồng C rõ ràng **cho phép code Java xác minh trước** thay vì tự đoán.

### 10.1. Kiểm tra độ dài trước reinterpret

Mẫu Java sau **chỉ là trích đoạn** cho tình huống đã có `pointer`, `count`, `layout` và `ownerArena` từ native API đáng tin. Không ghép nguyên đoạn thành chương trình nếu chưa định nghĩa chúng theo C ABI:

~~~java
long maxElements = 1_000_000L;
long count = nativeCount;            // Đọc từ contract của C API.
long elementBytes = layout.byteSize();

if (count < 0 || count > maxElements) {
    throw new IllegalArgumentException("invalid element count");
}

long byteCount = Math.multiplyExact(count, elementBytes);
if (byteCount > 16L * 1024 * 1024) {
    throw new IllegalArgumentException("buffer exceeds policy limit");
}

if (byteCount > 0 && pointer.address() == 0L) {
    throw new IllegalArgumentException("null pointer with nonzero size");
}

// Điều kiện BẮT BUỘC ngoài các kiểm tra số:
// C API cam kết backing memory thật có >= byteCount bytes,
// đúng alignment và sống ít nhất tới khi ownerArena đóng.
MemorySegment view = pointer.reinterpret(byteCount, ownerArena, null);
~~~

Những bước này giúp kiểm soát **arithmetic overflow** (`Math.multiplyExact`), giới hạn tài nguyên, null pointer và kích thước logic. Nhưng chúng **không kiểm tra bằng OS** rằng pointer thật sự sở hữu `byteCount` byte. Bảo đảm cuối cùng vẫn đến từ **ABI/protocol và native owner**.

Trường hợp `count == 0` có thể dùng view dài 0 và không dereference. Không tự cộng một phần tử vào độ dài để tránh tình huống empty array nếu C API không quy định có phần tử sentinel.

### 10.2. Phải biết kích thước là byte, không phải số phần tử

Một con trỏ tới 10 giá trị `int` 32-bit có thể cần **40 byte**, không phải 10 byte. Ngược lại, nếu C API trả số byte rồi Java lại nhân thêm `sizeof(int)`, kết quả có thể bị phóng đại 4 lần.

Nên tách tên: `elementCount`, `elementByteSize`, `byteCount`, dùng `Math.multiplyExact` và kiểm tra mức tối đa trước khi tạo view. C `size_t` có độ rộng theo ABI, do đó chuyển `size_t` sang Java `long` cần hiểu kiến trúc; **không tự suy ra** mọi `size_t` trên mọi nền tảng đều 64 bit.

### 10.3. Phải biết vùng nhớ còn sống bao lâu

Một số native APIs trả pointer chỉ sống đến **lần gọi kế tiếp**, pointer tới buffer nội bộ được ghi đè, hoặc pointer chỉ hợp lệ khi lock/resource handle còn mở. Khi ấy, việc gắn pointer vào `Arena.global()` hoặc một `Arena.ofShared()` sống lâu **không kéo dài tuổi thọ thật** của backing memory.

Một con trỏ được library free từ thread C khác có thể invalid giữa hai lời gọi Java dù `view.scope().isAlive() == true`. FFM temporal checks **không thể chặn** lỗi mà native code tự tạo ngoài knowledge của arena.

### 10.4. Phải biết quyền ghi, alignment và concurrency

- **Read-only vs writable:** C API có thể trả `const char *`. FFM không tự suy ra toàn bộ C `const` từ pointer; binding nên chỉ cung cấp view chỉ đọc hoặc API không cho ghi.
- **Alignment:** `ValueLayout.JAVA_INT` hoặc struct layout có ràng buộc căn lề. Vùng nhớ đủ byte nhưng địa chỉ sai alignment có thể gây `IllegalArgumentException`.
- **Thread safety:** một view có thể được chia sẻ qua nhiều thread không có nghĩa native object bên dưới được truy cập đồng thời một cách an toàn.
- **Endianness:** bố cục số nguyên có thể phụ thuộc native byte order hoặc giao thức C; `reinterpret` không chuyển đổi endianness.
- **Struct layout:** padding/alignment giữa fields phụ thuộc ABI; `reinterpret` không làm một struct sai layout trở nên đúng.

## 11. Ba dạng sai lầm cần phân biệt: spatial, temporal và ownership

### 11.1. Spatial bug — khai báo quá số byte thực có

~~~text
C malloc: 10 byte
Java zero-length pointer
Java reinterpret(100): view cho phép tới 100 byte
Java read offset 80: Java kiểm tra view thấy OK
Native memory thực: offset 80 nằm NGOÀI allocation

Hậu quả có thể: crash JVM, đọc dữ liệu lạ, ghi hỏng memory,
không nhất thiết có IndexOutOfBoundsException.
~~~

Biện pháp: chỉ mở rộng theo **byte count được native API cam kết** và đã kiểm tra; không dùng “đoán page 4096”, “scan tới NUL vô hạn” hay “đọc thử đến khi lỗi” để tìm size.

### 11.2. Temporal bug — view còn alive nhưng backing đã được free

~~~text
Java nhận pointer từ C
Java reinterpret(size, Arena.global(), null)    // metadata luôn alive
C library free(pointer)                          // backing thực hết hiệu lực
Java view.scope().isAlive() == true              // vẫn true
Java get(view)                                    // use-after-free, nguy hiểm
~~~

Đây là **sơ đồ cảnh báo, không phải mã chạy**. Phải ràng buộc Java view lifetime **không dài hơn** lifetime thật; dùng đúng arena/cleanup và tránh native code free sớm, kể cả khi chạy nhiều threads.

### 11.3. Ownership bug — double-free hoặc leak

~~~text
Case A: C malloc -> Java reinterpret(size, arena, null)
        -> arena close nhưng không có cleanup C free
        -> C allocation có thể bị leak

Case B: Arena.allocate -> Java reinterpret(size, arena, s -> C_free(s))
        -> arena tự giải phóng allocation
        -> callback cũng cố free
        -> double-free / allocator mismatch

Case C: C malloc -> Java reinterpreted view + cleanup C free
        -> native library cũng free pointer trước đó
        -> double-free / dangling pointer
~~~

Tất cả là **mô tả lỗi**, không phải đoạn code khuyến nghị. Phải có **duy nhất một chủ sở hữu** đảm nhận deallocation và một điểm kết thúc lifecycle rõ ràng.

## 12. Nếu không biết size, hãy làm gì thay vì reinterpret bừa?

Có các hướng thay thế:

1. **Thiết kế lại API C** để trả `pointer + length`, hoặc nhận buffer do Java cấp phát với dung lượng biết trước. Đây là lựa chọn tốt nhất khi bạn kiểm soát native interface.
2. **Dùng API C truy vấn kích thước** trước khi đọc dữ liệu; nếu nó trả về số phần tử, đổi sang bytes bằng phép nhân có kiểm tra overflow.
3. **Yêu cầu native library copy dữ liệu** vào buffer do Java quản lý, hoặc sao chép ra Java array khi phải tách lifetime khỏi tài nguyên C.
4. **Dùng bounded `Arena`** (confined/shared) cho bộ nhớ cấp phát bởi Java; khi cần subrange chỉ dùng `asSlice` thay vì nới `reinterpret`.
5. **Đọc dữ liệu có kích thước cố định theo C contract** bằng `MemoryLayout` thích hợp; chỉ dùng `AddressLayout.withTargetLayout` khi layout đích thật sự chắc chắn.
6. **Chỉ chuyển con trỏ opaque trở lại native code** nếu không cần dereference ở Java; zero-length pointer là một dạng hợp lệ để chuyển địa chỉ mà không đoán bytes.
7. **Nếu chỉ có một pointer không rõ size/lifetime và không có tài liệu đáng tin**, đừng dereference trong Java: không có phép đoán an toàn trong `reinterpret`.

Một số C APIs cho phép gọi hai lần: lần đầu hỏi độ dài, lần sau yêu cầu fill vào buffer do Java cấp phát. Khi có lựa chọn như vậy, hãy ưu tiên vì dễ quản lý ownership, size và cleanup.

## 13. NULL pointer và các trường hợp biên

`MemorySegment.NULL` đại diện null address và có độ dài 0. Không biến nó thành view có kích thước dương rồi dereference. Kiểm tra `pointer.address() == 0L` trước khi dùng data có byteCount > 0.

Bảng tình huống:

| Tình huống | Điều nên làm |
|---|---|
| `byteCount == 0` | Giữ zero-length segment; không dereference |
| `pointer == NULL`, `byteCount > 0` | Báo lỗi hợp đồng/đầu vào |
| `byteCount < 0` | Báo `IllegalArgumentException` hoặc lỗi validation trước reinterpret |
| `count × elementSize` tràn `long` | `Math.multiplyExact` và xử lý lỗi, không wrap |
| `byteCount` vượt giới hạn ứng dụng | Từ chối/stream/chunk, không reinterpret dung lượng khổng lồ |
| Pointer trỏ giữa một allocation | Tính **bytes còn lại từ vị trí pointer**, không dùng toàn bộ size allocation |
| Pointer trỏ vùng chỉ đọc | Không cung cấp API ghi |
| Backing được native free trước deadline | Làm mất hiệu lực view ở tầng ứng dụng, không dereference |
| Native pointer giữ bởi callback không rõ lifetime | Tạo contract sở hữu/lifetime trước khi chuyển sang Java |

**Không dùng `reinterpret(Long.MAX_VALUE)` để “tránh bounds checks”.** Nó tăng surface nguy hiểm và không cấp thêm vùng nhớ. Thậm chí khi `reinterpret` chấp nhận một độ dài lớn không âm, việc offset + width tràn hoặc pointer arithmetic gây nguy hiểm vẫn không thể được xử lý như một allocation thật.

## 14. Các lỗi Java dự kiến không cứu được mọi native memory bug

Cần phân biệt những lỗi mà FFM **có đủ thông tin** để phát hiện với các lỗi **không thể chứng minh từ metadata**:

| Lỗi | FFM có thể phát hiện thế nào? | Giới hạn |
|---|---|---|
| Đọc ngoài `segment.byteSize()` của view | `IndexOutOfBoundsException` | Nếu view khai báo quá lớn thì check dựa trên thông tin sai |
| Đọc sau khi scope confined/shared đã đóng | `IllegalStateException` | Không phát hiện C free độc lập khi scope Java vẫn alive |
| Dùng segment confined từ thread khác | `WrongThreadException` | Shared/global không tự đồng bộ dữ liệu |
| `reinterpret(-1)` | `IllegalArgumentException` | Chặn kích thước âm, không xác minh kích thước dương |
| `reinterpret` trên heap segment | `UnsupportedOperationException` | API chỉ áp dụng native segments |
| Caller không có native access phù hợp | `IllegalCallerException` hoặc warning theo phiên bản/cấu hình | Cấp quyền không làm pointer trở nên an toàn |
| Chọn sai alignment/ValueLayout | Kiểm tra alignment/type ở mức API | Không thể suy ra toàn bộ C ABI hay ownership |
| View 100 byte trên allocation 10 byte, đọc offset 80 | **Không có chứng cứ để chặn ở spatial metadata** | Có thể crash hoặc memory corruption |

**Một kết quả không ném exception không chứng minh thao tác đúng.** Native memory lỗi đôi khi chỉ phát nổ ở request khác, thread khác hoặc quá trình GC/JIT sau đó, khiến nguyên nhân khó truy tìm.

## 15. Gợi ý kiểm thử và code review cho binding FFM

### 15.1. Tiêu chí review

Trước mỗi `reinterpret`, trả lời bằng lời hoặc comment kỹ thuật:

- **Nguồn pointer:** do `Arena.allocate`, C `malloc`, pointer vào struct, buffer nội bộ hay mapped region?
- **Độ dài:** nguồn dữ liệu nào bảo đảm `newSize`? Tính bằng byte hay element? Có kiểm tra overflow/max size?
- **Thời gian sống:** ai có thể đóng arena/free pointer? View có sống lâu hơn owner không?
- **Cleanup:** có hàm release đúng không, gọi đúng một lần chưa? `null` callback có hợp lý không?
- **Quyền và thread:** có đúng read-only/ABI/alignment và concurrency không?
- **Cờ môi trường:** module nào có quyền restricted native access? Build toolchain có đúng JDK22+ không?
- **Phương án an toàn hơn:** có thể dùng `asSlice` hoặc copy sang buffer được sở hữu tường minh không?

Nếu một câu không có câu trả lời đáng tin, hãy **đưa lại yêu cầu cho thiết kế C API hoặc native owner**, không dùng reinterpret để che thông tin thiếu.

### 15.2. Kiểm thử không chủ đích làm JVM crash

Có thể test các **trường hợp bị FFM kiểm soát rõ** mà không dereference pointer sai:

- Gọi `original.asSlice(12, 8)` trên view 16 byte, mong `IndexOutOfBoundsException`.
- Đóng `Arena.ofConfined()` rồi thử đọc view cùng scope, mong `IllegalStateException`.
- Xác nhận `reinterpret(24)` cho view dài 24 nhưng **không đọc phần 16..23** nếu backing chỉ dài 16.
- Xác nhận `slot.get(ValueLayout.ADDRESS, 0)` cho pointer view dài 0 trước khi rebind.
- Kiểm tra `Math.multiplyExact` với số lượng gây overflow, kiểm tra null pointer và giới hạn size.
- Test owner cleanup bằng counter/log và kiểm tra **đúng một lần** trong harness native được kiểm soát; không cố tình free sai địa chỉ để quan sát crash.

Để kiểm tra rò rỉ native memory, dùng metric cấp tiến trình/Native Memory Tracking hoặc công cụ phù hợp; không dựa riêng vào heap chart Java và không chạy loop đọc/ghi OOB trong tiến trình production.

### 15.3. Chạy JVM khi dùng restricted method

Hai ví dụ đầy đủ trong bài dùng FFM final JDK 22 và `reinterpret` là restricted API:

~~~bash
javac --release 22 ReinterpretViews.java
java --enable-native-access=ALL-UNNAMED ReinterpretViews

javac --release 22 PointerReinterpret.java
java --enable-native-access=ALL-UNNAMED PointerReinterpret
~~~

Cờ `--enable-native-access=ALL-UNNAMED` cấp quyền cho code ở classpath. Nếu bạn copy mã vào một **named module**, hãy chỉ định tên module phù hợp. Chính sách warning/deny của restricted operations có thể thay đổi ở các JDK mới hơn; dự án cần đối chiếu tài liệu theo runtime đang triển khai.

## 16. So sánh với JNI và native allocator truyền thống

Trong JNI, native code có thể lấy một `jbyteArray`, gọi `GetByteArrayElements` hoặc thao tác một `jobject` thông qua API JNI; các thao tác này có hợp đồng pin/copy/release khác với FFM. FFM không dùng `JNIEnv *` cho mọi downcall và không biến `malloc`/`free` của C thành Java ownership tự động.

| JNI / C | FFM | Điều phải nắm |
|---|---|---|
| `malloc(n)` cấp `n` byte | `Arena.allocate(n)` cấp memory qua FFM | Có thông tin kích thước và owner rõ nếu Java cấp phát |
| Con trỏ C thô không có size | `MemorySegment.ofAddress(address)` tạo view 0 byte | Chưa thể dereference |
| Cast con trỏ C | `reinterpret(bytes)` tạo view kích thước được khai báo | Không có runtime proof về native backing |
| `free(pointer)` theo C allocator | Cleanup action hoặc native deallocator do binding gọi | Phải đúng một chủ sở hữu và đúng allocator |
| JNI local/global refs | FFM `MemorySegment`/`Arena` | Không đồng nhất vòng đời Java object refs với off-heap memory |
| Native buffer view | `asSlice(...)` | Subrange an toàn nếu biên nguồn đáng tin |

**Không tự `free` một vùng nhớ cấp bởi `Arena.allocate`** qua C allocator tùy tiện. Trong ứng dụng gọi `malloc` của thư viện C, phải dùng đúng hàm release mà API quy định. Một view reinterpret không thay đổi cách vùng nhớ được cấp phát ban đầu.

## 17. Bài tập tự kiểm tra

1. `MemorySegment.reinterpret(100)` có cấp phát mới 100 byte hoặc hỏi OS xem backing allocation có đủ 100 byte không?
2. Nếu `original.byteSize() == 16` và `wider = original.reinterpret(24)`, điều gì chắc chắn đúng về `wider` và điều gì **chưa được chứng minh**?
3. Vì sao `original.asSlice(12, 8)` có thể bị chặn nhưng `wider.get(JAVA_INT, 16)` có thể vượt allocation thật mà không bị bounds check của view phát hiện?
4. Con trỏ trả về từ C function thường được biểu diễn dưới dạng zero-length segment để làm gì?
5. `rawPointer.scope().isAlive() == true` có chứng minh native backing đã không bị `free` không?
6. Ba overload `reinterpret` của JDK22 khác nhau ra sao về size, scope và cleanup?
7. Nếu gắn pointer do `malloc` cấp vào arena khác với `cleanup == null`, hệ thống có thể gặp vấn đề resource nào?
8. Nếu gắn callback `free` cho một pointer vốn được `Arena.allocate` quản lý, nguy cơ nào có thể xảy ra?
9. Một native API cho biết số phần tử `count` và kích thước `elementBytes`; phải kiểm tra gì trước khi đổi thành `byteCount`?
10. Một pointer trỏ giữa allocation 1 KiB, vì sao không thể tự reinterpret thành toàn bộ 1 KiB từ vị trí pointer đó?
11. `Arena.global()` có bảo đảm pointer do C trả về vẫn còn backing memory dù thư viện đã thu hồi nó?
12. `AddressLayout.withTargetLayout(layout)` giúp gì và tại sao nó cũng là restricted?
13. Tại sao cấp `--enable-native-access` không chứng minh được một `reinterpret` có size đúng?
14. Nếu native API không mô tả lifetime/size, giải pháp thiết kế nào hợp lý hơn “gọi reinterpret với số thật lớn”?
15. Trong hai chương trình mẫu, vì sao chúng **không bao giờ** thực hiện read/write ở phần backing memory không được chứng minh là tồn tại?

**Kết luận:** `reinterpret` là cách **thay đổi metadata của một view** đối với native memory: cùng địa chỉ, nhưng có thể có size/scope khác. Nó **không xác minh allocation thật**, không tạo thêm bytes và không tự đảm bảo lifetime/ownership đúng. Chỉ dùng khi đã có hợp đồng C/native rõ ràng về **số byte hợp lệ, thời gian sống, căn lề, quyền truy cập và deallocator**. Khi chỉ cần nhìn một phần allocation đã biết, `asSlice` an toàn hơn. Khi không biết size hoặc owner, **đừng dereference** con trỏ trong Java.

### Tài liệu chuẩn

- [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): giải thích zero-length pointers, spatial/temporal bounds, các overload `reinterpret` và restricted semantics.
- [Java SE 22 — FFM package (Restricted Methods)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html): lý do restricted FFM methods có thể gây JVM crash/memory corruption.
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): ownership của allocations, confined/shared/automatic/global scopes.
- [JEP 454 — Foreign Function & Memory API (Final)](https://openjdk.org/jeps/454): nền tảng API FFM chính thức ở JDK 22.
- [Dev.java — Troubleshoot Calls to Native Library Functions](https://dev.java/learn/api/io/ffm/troubleshoot/): zero-length segments, native allocation và diễn giải con trỏ an toàn theo contract.
