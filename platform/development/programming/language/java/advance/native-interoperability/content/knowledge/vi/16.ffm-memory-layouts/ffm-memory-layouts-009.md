# Kiểm chứng sizeof, alignof và offsetof bằng một chương trình C đi kèm

## 1. Mục tiêu: lấy ABI thực tế làm chuẩn, không đoán layout từ Java

Khi Java gọi thư viện C thông qua **Foreign Function & Memory API (FFM)** hoặc JNI, một cấu trúc dữ liệu C thường được mô tả lại dưới dạng **`MemoryLayout`** của Java. Sai một byte đệm (padding), một yêu cầu căn chỉnh (alignment) hoặc một offset của trường cũng có thể khiến Java đọc sai dữ liệu, native function nhận sai tham số hoặc nghiêm trọng hơn là truy cập bộ nhớ không hợp lệ.

Ba phép kiểm C cần dùng:

- **`sizeof(T)`**: số byte bộ nhớ cần cho một đối tượng kiểu `T`, **gồm cả padding** bên trong và cuối cấu trúc.
- **`_Alignof(T)`**: yêu cầu căn chỉnh của kiểu `T` theo C11, tính bằng byte. Macro `alignof(T)` của `<stdalign.h>` cũng được hỗ trợ trong C11; đến C23 `alignof` là keyword.
- **`offsetof(T, field)`**: vị trí bắt đầu của thành viên `field`, tính bằng byte từ đầu một đối tượng kiểu `T`; macro chuẩn ở `<stddef.h>`.

Ba phép này đo **đúng quy tắc layout mà C compiler đang áp dụng**. Đối chiếu với ba phép FFM tương ứng trong Java 22+:

| C11 | Java FFM (JDK 22+) | Ý nghĩa |
| --- | --- | --- |
| `sizeof(Packet)` | `PACKET.byteSize()` | Kích thước toàn struct |
| `_Alignof(Packet)` | `PACKET.byteAlignment()` | Yêu cầu căn chỉnh của struct |
| `offsetof(Packet, count)` | `PACKET.byteOffset(PathElement.groupElement("count"))` | Vị trí trường `count` |
| `sizeof(Packet[2]) / 2` | `MemoryLayout.sequenceLayout(2, PACKET).byteSize() / 2` | Bước nhảy giữa hai phần tử trong mảng |
| `offsetof(Envelope, packet.count)` | `ENVELOPE.byteOffset(groupElement("packet"), groupElement("count"))` | Vị trí trường lồng nhau |

**Nguyên tắc:** `MemoryLayout.structLayout(...)` **không tự chèn padding** theo C compiler. Java phải mô tả rõ byte đệm, hoặc dùng cách tạo layout được chứng minh là đúng với header/ABI thực tế. Không lấy `MemoryLayout.byteSize()` “trông hợp lý” làm bằng chứng layout khớp C.

Đến cuối bài, bạn sẽ có **một chương trình C11 chạy độc lập** (`abi_probe.c`), **một chương trình Java 22+ chạy độc lập** (`LayoutVerify22.java`), cách so sánh kết quả bằng `diff` và quy trình áp dụng cho struct thật trong thư viện native.

## 2. Bối cảnh phiên bản và môi trường kiểm thử

Ví dụ được thiết kế cho:

- **C11** với GCC/Clang trên **Linux x86-64**, ABI thông dụng của nền tảng này; `cc`/`gcc` là trình biên dịch được dùng ở ví dụ.
- **JDK 22 trở lên**, dùng FFM API đã final trong `java.lang.foreign` (JEP 454). Không dùng `jdk.incubator.foreign` hoặc `--enable-preview`.
- Java và chương trình C chạy trên **cùng hệ điều hành, kiến trúc và ABI**. So khớp output từ C compiler Linux/x86-64 với JVM Windows/x64 là không có giá trị xác nhận cùng layout.
- C compiler dùng quy tắc alignment tự nhiên, **không** bật `#pragma pack`, `__attribute__((packed))`, `-fpack-struct` hoặc tùy chọn ABI tùy biến.

Ví dụ dùng `uint8_t`, `uint32_t` và `double`. Trên Linux/x86-64 thông thường:

| C type | Kích thước (byte) | C11 alignment (byte) | FFM layout tương ứng trong ví dụ |
| --- | ---: | ---: | --- |
| `uint8_t` | 1 | 1 | `ValueLayout.JAVA_BYTE` |
| `uint32_t` | 4 | 4 | `ValueLayout.JAVA_INT` |
| `double` | 8 | 8 | `ValueLayout.JAVA_DOUBLE` |

**Giới hạn quan trọng:** `uint32_t` là số nguyên **không dấu**, còn Java `int` có dấu. Hai kiểu có thể cùng **kích thước, alignment và biểu diễn 32 bit** trên ABI đang kiểm nhưng không có cùng ngữ nghĩa giá trị. Khi đọc giá trị lớn hơn `Integer.MAX_VALUE`, dùng `Integer.toUnsignedLong(...)` hoặc cách biểu diễn không dấu có chủ đích. Còn `double` phải đối chiếu ABI và floating-point representation, không chỉ đoán từ tên kiểu.

Trên nền tảng khác, kết quả `_Alignof(double)`, sizeof/alignment của pointer, `long` hay quy ước layout có thể khác. **Output ví dụ ở bài là kết quả dự kiến trên Linux/x86-64**, không phải bảo đảm C standard quy định mọi machine đều phải giống.

## 3. Struct mẫu để nhìn rõ padding

Định nghĩa C:

~~~c
#include <stdint.h>

typedef struct Packet {
    uint8_t  kind;
    uint32_t count;
    double   factor;
    uint8_t  enabled;
} Packet;
~~~

Thứ tự khai báo thành viên phải giữ nguyên khi mô tả FFM. Với alignment Linux/x86-64 thông thường, các bytes được xếp như sau:

~~~text
Byte offset
0          1      4             8                    16 17          24
| kind: 1  | pad:3 | count: 4    | factor: 8          |enabled| pad: 7 |
+----------+-------+-------------+--------------------+-------+--------+
^                                ^                                      ^
struct start (offset 0)      factor starts (8)                    next Packet
                                                                     starts (24)

sizeof(Packet)      = 24
_Alignof(Packet)    = 8
offsetof(kind)      = 0
offsetof(count)     = 4
offsetof(factor)    = 8
offsetof(enabled)   = 16
~~~

C compiler cần chèn **ba byte trước `count`**: `kind` tốn một byte, nhưng `uint32_t` phải bắt đầu ở offset chia hết cho 4. Trường `factor` bắt đầu ở offset 8 nên đã đạt alignment 8, không cần padding thêm trước trường. Trường `enabled` bắt đầu offset 16. Sau đó còn **bảy byte tail padding** để kích thước struct là bội của alignment 8.

Đây là lý do `sizeof(Packet)` không phải tổng `1 + 4 + 8 + 1 = 14`; kích thước thật dự kiến là **24**.

### Vì sao tail padding quan trọng?

Mảng C:

~~~c
Packet items[2];
~~~

Hai phần tử nằm liên tiếp theo stride `sizeof(Packet)`. Nếu phần tử thứ hai bắt đầu tại offset 14 thì `factor` trong phần tử thứ hai có thể không còn alignment 8. C compiler thêm tail padding để **mỗi phần tử kế tiếp** bắt đầu ở offset hợp lệ.

Với C layout ví dụ:

~~~text
items[0]: offsets  0..23
items[1]: offsets 24..47
total sizeof(items) = 48
stride = sizeof(Packet) = 24
~~~

Khi làm FFM `MemoryLayout.sequenceLayout(n, PACKET)`, **`PACKET.byteSize()` cũng phải bao gồm tail padding**. Chỉ khớp offsets của các trường trong *một* instance nhưng bỏ tail padding sẽ khiến phần tử thứ hai bị truy cập sai.

## 4. Chương trình C11 hoàn chỉnh: `abi_probe.c`

Tạo tệp **`abi_probe.c`** đúng nội dung sau:

~~~c
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef struct Packet {
    uint8_t  kind;
    uint32_t count;
    double   factor;
    uint8_t  enabled;
} Packet;

typedef struct Envelope {
    uint8_t prefix;
    Packet  packet;
} Envelope;

int main(void) {
    Packet sample = {0};

    printf("packet.size=%zu\n", sizeof(Packet));
    printf("packet.align=%zu\n", (size_t)_Alignof(Packet));

    printf("kind.offset=%zu\n",
           offsetof(Packet, kind));
    printf("count.offset=%zu\n",
           offsetof(Packet, count));
    printf("factor.offset=%zu\n",
           offsetof(Packet, factor));
    printf("enabled.offset=%zu\n",
           offsetof(Packet, enabled));

    printf("kind.size=%zu\n", sizeof sample.kind);
    printf("count.size=%zu\n", sizeof sample.count);
    printf("factor.size=%zu\n", sizeof sample.factor);
    printf("enabled.size=%zu\n", sizeof sample.enabled);

    printf("count.align=%zu\n", (size_t)_Alignof(uint32_t));
    printf("factor.align=%zu\n", (size_t)_Alignof(double));

    printf("array.stride=%zu\n", sizeof(Packet[2]) / 2);

    printf("envelope.size=%zu\n", sizeof(Envelope));
    printf("envelope.align=%zu\n", (size_t)_Alignof(Envelope));
    printf("envelope.packet.offset=%zu\n",
           offsetof(Envelope, packet));
    printf("envelope.packet.count.offset=%zu\n",
           offsetof(Envelope, packet.count));

    return 0;
}
~~~

### 4.1. Build và chạy

~~~bash
cc -std=c11 -Wall -Wextra -Wpedantic \
  -o abi_probe abi_probe.c

./abi_probe
~~~

`-std=c11` kích hoạt chuẩn C11 để `_Alignof` có định nghĩa chuẩn. `-Wall -Wextra -Wpedantic` giúp phát hiện nhiều vấn đề khi dùng GCC/Clang. Không thêm flag “packed” nếu header gốc không yêu cầu packed.

**Output dự kiến trên Linux/x86-64 thông thường:**

~~~text
packet.size=24
packet.align=8
kind.offset=0
count.offset=4
factor.offset=8
enabled.offset=16
kind.size=1
count.size=4
factor.size=8
enabled.size=1
count.align=4
factor.align=8
array.stride=24
envelope.size=32
envelope.align=8
envelope.packet.offset=8
envelope.packet.count.offset=12
~~~

Đoạn `Envelope` cho thấy **struct lồng nhau** cũng có padding:

~~~c
typedef struct Envelope {
    uint8_t prefix;  /* offset 0 */
    Packet  packet;  /* offset 8 do Packet cần alignment 8 */
} Envelope;
~~~

Trong `Envelope`, `packet.count` bắt đầu tại offset `8 + 4 = 12`. `offsetof(Envelope, packet.count)` cho phép kiểm chứng nested member designator trong trường hợp này; khác với việc dùng sai macro `offsetof` cho bit-field.

### 4.2. Vì sao dùng `%zu`?

Kết quả `sizeof`, `_Alignof` và `offsetof` có kiểu `size_t`, không phải mặc định `int`. Format `%zu` là conversion specifier cho `size_t` trong C99+ và phù hợp C11.

Tránh:

~~~c
/* Không an toàn khi size_t không có cùng representation với int. */
printf("%d\n", sizeof(Packet));
~~~

Dùng `%d` cho một `size_t` là không khớp kiểu của variadic argument, gây hành vi không xác định theo hợp đồng `printf`. Cũng không nên ép `size_t` về `int` khi in các cấu trúc có thể rất lớn.

### 4.3. `sizeof` không chạy qua bộ nhớ để đếm

Trong trường hợp thông thường `sizeof(Packet)`, `sizeof sample.count` là phép toán được C compiler xác định từ type và layout. Nó không cần đi qua từng byte runtime. Với `sizeof` trên **variable-length arrays (VLA)**, một số biểu thức kích thước được tính khi chạy; bài này cố ý chỉ dùng loại struct hoàn chỉnh có layout xác định lúc biên dịch.

`_Alignof(Packet)` cũng cho biết **yêu cầu alignment của kiểu**, không phải “địa chỉ của một biến Packet cụ thể chia hết cho bao nhiêu lớn nhất”. Một biến có thể tình cờ nằm ở địa chỉ căn chỉnh mạnh hơn mức yêu cầu; điều đó không đổi hợp đồng ABI.

## 5. Java FFM: mô tả đúng C struct bằng `MemoryLayout`

Với JDK 22+, ta mô hình hóa `Packet` bằng `MemoryLayout.structLayout`. **Không để API đoán padding:** Java FFM yêu cầu bạn đưa các đoạn `paddingLayout` vào đúng vị trí.

~~~java
// Trích đoạn Java 22+, class/import đầy đủ ở phần 6.
StructLayout PACKET = MemoryLayout.structLayout(
    ValueLayout.JAVA_BYTE.withName("kind"),
    MemoryLayout.paddingLayout(3),
    ValueLayout.JAVA_INT.withName("count"),
    ValueLayout.JAVA_DOUBLE.withName("factor"),
    ValueLayout.JAVA_BYTE.withName("enabled"),
    MemoryLayout.paddingLayout(7)
).withName("Packet");
~~~

Tổng số bytes: `1 + 3 + 4 + 8 + 1 + 7 = 24`.

Alignment tự nhiên của layout là **8**, do trường `ValueLayout.JAVA_DOUBLE` có alignment 8 trên nền tảng đã nêu. Các layout `JAVA_BYTE`, `JAVA_INT` và `JAVA_DOUBLE` dùng kích thước lần lượt 1, 4 và 8 bytes. Trong ví dụ này, `StructLayout` có các phần tử được chèn padding sao cho từng trường bắt đầu ở offset phù hợp.

Các offsets Java:

~~~java
// Trích đoạn dùng biến PACKET như trên.
long a = PACKET.byteOffset(PathElement.groupElement("kind"));    // 0
long b = PACKET.byteOffset(PathElement.groupElement("count"));   // 4
long c = PACKET.byteOffset(PathElement.groupElement("factor"));  // 8
long d = PACKET.byteOffset(PathElement.groupElement("enabled")); // 16
~~~

**Chú ý:** Kích thước một `StructLayout` là tổng kích thước các member layouts mà bạn cung cấp. `structLayout` **không tự thêm padding để align phần tử tiếp theo**. Ví dụ thiếu padding:

~~~java
// Minh họa lỗi JDK 22+; không phải bố cục hợp lệ của Packet.
MemoryLayout wrong = MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE.withName("kind"),
        ValueLayout.JAVA_INT.withName("count"));
~~~

Vì `JAVA_INT` bắt đầu ở offset 1, layout có thể bị từ chối bằng `IllegalArgumentException` do vi phạm alignment, thay vì tự chèn ba byte. Nếu đổi `JAVA_INT.withByteAlignment(1)` cho “hết lỗi”, bạn có thể tạo một layout kiểu packed **không đúng ABI của struct gốc**. Sửa chuẩn là chèn padding đúng theo output C.

### 5.1. Dùng `PathElement.groupElement` để chọn member

FFM cung cấp:

~~~java
// Trích đoạn đã có PACKET và PathElement:
long offset = PACKET.byteOffset(
        PathElement.groupElement("factor"));

long fieldSize = PACKET.select(
        PathElement.groupElement("factor"))
        .byteSize();
~~~

`groupElement("factor")` chỉ hoạt động nếu layout con có `withName("factor")`. Tên trong Java là **metadata phục vụ truy vấn layout**, không tự làm C struct có trường tương ứng. Việc gán nhầm tên hoặc thứ tự vẫn tạo code compile được nhưng offset có thể sai; hãy so sánh với `offsetof` từ C.

Bạn cũng có thể tạo `VarHandle` theo path để đọc/ghi field:

~~~java
// Minh họa API Java 22+, chưa phải chương trình độc lập.
var handle = PACKET.varHandle(
        PathElement.groupElement("count"));

int count = (int) handle.get(segment, 0L);
handle.set(segment, 0L, 10);
~~~

Với `VarHandle` tạo từ layout path, `0L` là **base offset coordinate**; API sẽ cộng offset của `count`. Đừng vô tình cộng offset vào base **lần nữa**, nếu không sẽ double-offset. Chương trình đầy đủ dưới đây dùng `segment.get/set` với offset đã tính một lần để tránh nhầm lẫn này.

## 6. Chương trình Java 22+ hoàn chỉnh: `LayoutVerify22.java`

Tạo tệp **`LayoutVerify22.java`**. Chương trình có hai chế độ:

- **Không đối số:** in đúng 17 dòng cùng key và cùng thứ tự như `abi_probe.c` để có thể chạy `diff` tự động.
- **`--memory`:** in 17 dòng layout như trên, sau đó cấp phát native memory, ghi/đọc các trường để chứng minh offset được sử dụng hợp lệ.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemoryLayout.PathElement;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.ValueLayout;

public final class LayoutVerify22 {
    private static final StructLayout PACKET =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_BYTE.withName("kind"),
                    MemoryLayout.paddingLayout(3),
                    ValueLayout.JAVA_INT.withName("count"),
                    ValueLayout.JAVA_DOUBLE.withName("factor"),
                    ValueLayout.JAVA_BYTE.withName("enabled"),
                    MemoryLayout.paddingLayout(7)
            ).withName("Packet");

    private static final StructLayout ENVELOPE =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_BYTE.withName("prefix"),
                    MemoryLayout.paddingLayout(7),
                    PACKET.withName("packet")
            ).withName("Envelope");

    private static long offset(String field) {
        return PACKET.byteOffset(
                PathElement.groupElement(field));
    }

    private static void out(String key, long number) {
        System.out.println(key + "=" + number);
    }

    private static void printLayout() {
        out("packet.size", PACKET.byteSize());
        out("packet.align", PACKET.byteAlignment());

        out("kind.offset", offset("kind"));
        out("count.offset", offset("count"));
        out("factor.offset", offset("factor"));
        out("enabled.offset", offset("enabled"));

        out("kind.size", ValueLayout.JAVA_BYTE.byteSize());
        out("count.size", ValueLayout.JAVA_INT.byteSize());
        out("factor.size", ValueLayout.JAVA_DOUBLE.byteSize());
        out("enabled.size", ValueLayout.JAVA_BYTE.byteSize());

        out("count.align", ValueLayout.JAVA_INT.byteAlignment());
        out("factor.align", ValueLayout.JAVA_DOUBLE.byteAlignment());

        out("array.stride",
                MemoryLayout.sequenceLayout(2, PACKET)
                        .byteSize() / 2);

        out("envelope.size", ENVELOPE.byteSize());
        out("envelope.align", ENVELOPE.byteAlignment());
        out("envelope.packet.offset",
                ENVELOPE.byteOffset(
                        PathElement.groupElement("packet")));
        out("envelope.packet.count.offset",
                ENVELOPE.byteOffset(
                        PathElement.groupElement("packet"),
                        PathElement.groupElement("count")));
    }

    private static void memoryExercise() {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment record = arena.allocate(PACKET);

            record.set(ValueLayout.JAVA_BYTE,
                    offset("kind"), (byte) 7);
            record.set(ValueLayout.JAVA_INT,
                    offset("count"), 9);
            record.set(ValueLayout.JAVA_DOUBLE,
                    offset("factor"), 1.5d);
            record.set(ValueLayout.JAVA_BYTE,
                    offset("enabled"), (byte) 1);

            System.out.println("memory.kind="
                    + Byte.toUnsignedInt(
                            record.get(ValueLayout.JAVA_BYTE,
                                    offset("kind"))));
            System.out.println("memory.count="
                    + Integer.toUnsignedLong(
                            record.get(ValueLayout.JAVA_INT,
                                    offset("count"))));
            System.out.println("memory.factor="
                    + record.get(ValueLayout.JAVA_DOUBLE,
                            offset("factor")));
            System.out.println("memory.enabled="
                    + Byte.toUnsignedInt(
                            record.get(ValueLayout.JAVA_BYTE,
                                    offset("enabled"))));
        }
    }

    public static void main(String[] args) {
        if (args.length > 1 ||
                (args.length == 1 && !args[0].equals("--memory"))) {
            throw new IllegalArgumentException(
                    "Usage: java LayoutVerify22 [--memory]");
        }

        printLayout();

        if (args.length == 1) {
            memoryExercise();
        }
    }
}
~~~

### 6.1. Biên dịch và chạy

~~~bash
javac LayoutVerify22.java
java LayoutVerify22
~~~

**Stdout dự kiến trên Linux/x86-64** — giống 17 dòng từ C:

~~~text
packet.size=24
packet.align=8
kind.offset=0
count.offset=4
factor.offset=8
enabled.offset=16
kind.size=1
count.size=4
factor.size=8
enabled.size=1
count.align=4
factor.align=8
array.stride=24
envelope.size=32
envelope.align=8
envelope.packet.offset=8
envelope.packet.count.offset=12
~~~

Chạy thêm chế độ ghi/đọc:

~~~bash
java LayoutVerify22 --memory
~~~

Sau 17 dòng layout, chương trình sẽ in thêm:

~~~text
memory.kind=7
memory.count=9
memory.factor=1.5
memory.enabled=1
~~~

Giải thích:

- `arena.allocate(PACKET)` cấp phát native memory có kích thước và alignment của layout trong phạm vi confined arena.
- `record.set(ValueLayout.JAVA_INT, offset("count"), 9)` ghi số vào đúng offset 4 theo Java model; `get` đọc lại qua layout tương ứng.
- `Byte.toUnsignedInt` giúp in `uint8_t`-like value dưới dạng số 0–255, thay vì nhầm Java `byte` có dấu.
- `Integer.toUnsignedLong` dùng để diễn giải các bit của Java `int` theo nghĩa unsigned 32-bit ở mức giá trị đọc được.
- `try (Arena arena = Arena.ofConfined())` giúp giải phóng allocation sau khi test; không trả `MemorySegment` ra ngoài lifetime.

**Lưu ý về phạm vi chứng minh:** Ghi và đọc *bằng chính cùng Java layout* cho kết quả đúng **chưa đủ** để chứng minh tương thích C. Java có thể tự ghi rồi tự đọc thành công ngay cả khi layout khác hoàn toàn C. Bằng chứng quan trọng hơn là so sánh **`sizeof`, `_Alignof`, `offsetof` của C** với **`byteSize`, `byteAlignment`, `byteOffset` của Java**. Với dữ liệu thật, thêm test hai chiều Java→C và C→Java để xác nhận ý nghĩa giá trị cũng khớp.

## 7. Kiểm chứng tự động bằng `diff` thay vì nhìn bằng mắt

Tạo cả hai executable từ đúng cùng checkout/source version và cùng môi trường target. Trên Linux:

~~~bash
cc -std=c11 -Wall -Wextra -Wpedantic \
  -o abi_probe abi_probe.c

javac LayoutVerify22.java

./abi_probe > c.layout
java LayoutVerify22 > java.layout

diff -u c.layout java.layout
~~~

**Kết quả khi khớp:** `diff -u` không in dòng nào và trả exit status `0`. Trong CI, một status khác `0` nên làm fail bước ABI validation.

Để nhìn rõ status:

~~~bash
diff -u c.layout java.layout
echo "diff_exit=$?"
~~~

Stdout cuối cùng khi hai file giống nhau:

~~~text
diff_exit=0
~~~

Nếu output khác, `diff` cho biết dòng nào bị mismatch. Ví dụ **một lỗi giả định có chủ đích**:

~~~diff
-packet.size=24
+packet.size=17
~~~

Điều đó có thể xuất hiện nếu Java model bỏ tail padding hoặc nhóm các member không đúng thứ tự. **Không sửa bằng cách ép phép so sánh bỏ qua dòng ấy**; phải truy từ C ABI thực tới member offsets và đúng `MemoryLayout.paddingLayout(...)`.

Thường nên giữ một bản output đo được từ C trong artifact CI của **mỗi target ABI**, thay vì chỉ check một số dự kiến in sẵn trong tài liệu. Khi phát triển đa nền tảng, chạy probe bằng compiler/linker thực trên từng platform; **không copy kết quả Linux/x86-64 thành expected cho Windows/x64 hoặc ARM**.

### 7.1. Vì sao dùng hai chương trình tách biệt?

- C probe độc lập với JVM và không gọi `java.lang.foreign`; nó kiểm tra **compiler view** của `Packet` và `Envelope`.
- Java verifier không gọi native library; nó kiểm tra **mô hình layout Java định truyền sang C**.
- So sánh hai output giúp phát hiện khác biệt trước khi gọi một function native thật sự, tránh crash vì struct layout sai.
- Khi cần kiểm tra ABI trên một machine cụ thể, cả hai có thể được build/run trong cùng job CI để tránh so nhầm kiến trúc.

### 7.2. Độ chính xác của phép so sánh

Phép so sánh chỉ chứng minh **các đại lượng đã đo** khớp trên môi trường đó. Nó không tự chứng minh:

- Số nguyên signed/unsigned có semantics tương thích mọi giá trị.
- Endianness/bitfield order/float representation đã khớp.
- Packing/options khi build **thư viện thực** giống options khi build C probe.
- Native memory lifetime và thread confinement đúng.
- Pointer còn sống, đúng scope, đúng allocation/free ownership.
- Calling convention, `FunctionDescriptor` và cách pass struct by value khớp ABI.

Muốn test sâu hơn, thêm native function nhận/trả `Packet`, kiểm tra giá trị trên cả hai phía theo hợp đồng thư viện, và build bằng **cùng headers/cờ compiler** như thư viện sản xuất.

## 8. Giải thích toán học của padding

Tại một trường C có yêu cầu alignment `a`, offset kế tiếp thường phải được làm tròn lên thành một bội thích hợp của `a`. Trong mô hình struct tự nhiên của ví dụ, có thể dùng:

\[
\operatorname{alignUp}(x,a)=\left\lceil \frac{x}{a}\right\rceil a
\]

Áp dụng:

| Trường | Offset đang có | Alignment | Offset sau làm tròn | Size | Offset sau trường |
| --- | ---: | ---: | ---: | ---: | ---: |
| `kind` | 0 | 1 | 0 | 1 | 1 |
| `count` | 1 | 4 | 4 | 4 | 8 |
| `factor` | 8 | 8 | 8 | 8 | 16 |
| `enabled` | 16 | 1 | 16 | 1 | 17 |
| Kết thúc struct | 17 | struct alignment 8 | 24 | — | 24 |

Từ bảng:

- **Internal padding** giữa `kind` và `count` = `4 − 1 = 3` bytes.
- Không có padding giữa `count` và `factor` = `8 − 8 = 0`.
- **Tail padding** sau `enabled` = `24 − 17 = 7` bytes.
- Tổng member sizes = 14 bytes.
- Tổng padding = 3 + 7 = 10 bytes.
- Tổng `sizeof(Packet) = 14 + 10 = 24` bytes.

Cách tính trên phản ánh **mô hình ABI tự nhiên** của ví dụ, không nên xem là công thức portable thay thế C compiler trong mọi trường hợp. Packed attributes, explicit alignment, ABI extensions và đặc thù compiler có thể làm kết quả khác. Vì thế bài tập bắt đầu bằng **C probe đo thực tế**, chứ không bắt đầu bằng giả định rằng công thức luôn đúng.

### 8.1. FFM không tự “align-up” từng field

FFM Java:

~~~java
// Lỗi: JAVA_INT yêu cầu alignment 4 nhưng đang ở offset 1.
MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE,
        ValueLayout.JAVA_INT);
~~~

Không được kỳ vọng factory `structLayout` tự thêm `paddingLayout(3)`. Đặc tả JDK 22 ghi rõ cần chèn padding khi cần; layout không phù hợp alignment có thể bị từ chối.

Lời giải:

~~~java
// JDK 22+, minh họa:
MemoryLayout.structLayout(
        ValueLayout.JAVA_BYTE,
        MemoryLayout.paddingLayout(3),
        ValueLayout.JAVA_INT);
~~~

**Nhưng** kết quả mới dài `1+3+4=8`; đối với struct thật có nhiều trường tiếp theo, bạn còn phải tính cả những khoảng padding tiếp theo và **tail padding** của struct cuối cùng. Đừng chỉ sửa exception đầu tiên và dừng kiểm chứng.

## 9. `sizeof`: đo cả kích thước struct, mảng và trường

### 9.1. `sizeof(T)` khác tổng member sizes

Ví dụ `Packet`:

~~~c
/* Đoạn C11 minh họa nằm trong cùng file/translation unit. */
size_t full = sizeof(Packet);         /* dự kiến 24 */
size_t part = sizeof(uint8_t)
            + sizeof(uint32_t)
            + sizeof(double)
            + sizeof(uint8_t);       /* dự kiến 14 */
~~~

Sự khác biệt giữa 24 và 14 chính là internal/tail padding trong ABI ví dụ. `sizeof(Packet)` là phép cần dùng để cấp phát buffer hoặc tính stride cho **array of structs**.

### 9.2. `sizeof(array)` khác `sizeof(pointer)`

~~~c
/* Trích đoạn C11 minh họa, không độc lập. */
Packet samples[3];
Packet *pointer = samples;

size_t arrayBytes   = sizeof samples;    /* 3 * sizeof(Packet) */
size_t pointerBytes = sizeof pointer;    /* kích thước con trỏ */
~~~

Trên Linux/x86-64 thường là `arrayBytes=72` và `pointerBytes=8`, nhưng giá trị `sizeof(pointer)` không tự quyết định bố cục `Packet`. Một mảng được truyền vào tham số function dạng `Packet items[]` sẽ **decay thành pointer**, nên `sizeof(items)` bên trong function không còn là kích thước toàn mảng.

Trong Java FFM, `MemoryLayout.sequenceLayout(3, PACKET).byteSize()` tương đương logic **3 phần tử**. `ValueLayout.ADDRESS.byteSize()` chỉ liên quan carrier của **một pointer**, không phải kích thước mọi cấu trúc phía sau pointer.

### 9.3. `sizeof` trên mảng lồng nhau

C:

~~~c
Packet matrix[2][3];
// sizeof(matrix) = 2 * 3 * sizeof(Packet) trên ABI đang đo.
~~~

FFM:

~~~java
// JDK 22+ trích đoạn, PACKET đã được định nghĩa.
MemoryLayout matrix = MemoryLayout.sequenceLayout(
        2, MemoryLayout.sequenceLayout(3, PACKET));
~~~

Đừng coi C `Packet[2][3]` là layout của `Packet**`. Mảng C này là vùng liên tục có stride theo `sizeof(Packet)`; pointer-to-pointer là mô hình khác hoàn toàn.

## 10. `_Alignof`: kiểm tra yêu cầu alignment, không chỉ byteSize

### 10.1. `sizeof(T)` bằng nhau vẫn có thể khác alignment

Hai layout có cùng size 8 không mặc định có cùng alignment:

~~~text
C struct A: sizeof(A) = 8, alignof(A) = 4
C struct B: sizeof(B) = 8, alignof(B) = 8
~~~

Cả hai đều “dài 8 bytes”, nhưng vị trí hợp lệ trong memory, quy tắc aggregate và khi truyền qua native ABI có thể khác. So sánh `byteSize()` mà bỏ `byteAlignment()` là thiếu.

FFM:

~~~java
// JDK 22+ minh họa ý nghĩa hai metadata:
long bytes = layout.byteSize();
long requiredAlignment = layout.byteAlignment();
~~~

Nếu cần layout với alignment không mặc định, `withByteAlignment(long)` có thể thay metadata alignment. Tuy vậy **đổi alignment trên Java layout không làm thay đổi C struct thật**. C compiler/header là nguồn kiểm chứng. Chỉ ép alignment để “cho diff qua” mà không kiểm tra C có thể gây bug khó thấy.

### 10.2. `_Alignof` với kiểu khác nhau

C11:

~~~c
/* Chỉ minh họa; các giá trị đo phải lấy từ compiler target. */
_Alignof(char);
_Alignof(uint32_t);
_Alignof(double);
_Alignof(Packet);
~~~

Một số compiler có thể in sizeof giống nhau cho hai kiểu nhưng alignment khác. `_Alignof(T)` là property của **kiểu T**; không nên đo bằng cách lấy address của một biến, bởi địa chỉ thực có thể được đặt ở boundary căn chỉnh mạnh hơn yêu cầu.

Trong C23, `alignof` là keyword; trong C11 có thể include `<stdalign.h>` và dùng macro `alignof` tương đương. Để rõ mốc C11 và tránh phụ thuộc macro, chương trình đi kèm dùng trực tiếp **`_Alignof`**.

## 11. `offsetof`: đi vào đúng member, kể cả struct lồng nhau

### 11.1. Member offset khác pointer arithmetic tùy tiện

C11:

~~~c
/* Trích đoạn kiểm tra field offsets từ header thật. */
offsetof(Packet, kind);
offsetof(Packet, count);
offsetof(Packet, factor);
offsetof(Packet, enabled);
~~~

Đây là macro chuẩn được thiết kế cho mục đích xác định offset. Không nên viết:

~~~c
/* SAI/không portable: cố lấy địa chỉ từ một null pointer. */
size_t offset = (size_t)&(((Packet*)0)->count);
~~~

Dù nhiều compiler có extension cho một số biểu thức như vậy, tự dereference qua null pointer không phải giải pháp portable. Dùng `offsetof`, vốn được triển khai theo cách phù hợp với compiler.

### 11.2. Nested field

C:

~~~c
offsetof(Envelope, packet);        /* dự kiến 8  */
offsetof(Envelope, packet.count);  /* dự kiến 12 */
~~~

Java:

~~~java
// JDK 22+, ENVELOPE là nested StructLayout có member named "packet".
long packetStart = ENVELOPE.byteOffset(
        PathElement.groupElement("packet"));

long nestedCount = ENVELOPE.byteOffset(
        PathElement.groupElement("packet"),
        PathElement.groupElement("count"));
~~~

Chọn đúng **nested layout path**. Với `ENVELOPE`, chỉ gọi `groupElement("count")` ở cấp ngoài sẽ sai vì `count` là member của `Packet`, không phải member trực tiếp của `Envelope`.

### 11.3. Không dùng `offsetof` trên bit-field

C:

~~~c
/* C11 ví dụ minh họa; KHÔNG gọi offsetof(Flags, a). */
typedef struct Flags {
    unsigned int a : 3;
    unsigned int b : 5;
} Flags;
~~~

Bit-fields có cách bố trí **bit-level** và quy tắc compiler/ABI riêng; không thể lấy địa chỉ bit-field bằng `&obj.a` và `offsetof` không áp dụng. Nếu API C có bitfields, việc tạo Java layout đúng đòi hỏi tìm hiểu packing, bit order, storage unit, compiler conventions và dùng masks/shifts hoặc getter C thay vì coi bit-field như byte-aligned `ValueLayout` riêng.

## 12. Biến thể ABI: vì sao không đo một máy rồi dùng mọi nơi?

Ba yếu tố quyết định bản C:

1. **Header/thư viện thật:** field types, thứ tự, nested arrays, macros, `#pragma pack`, conditional typedefs.
2. **Compiler/ABI/cờ build:** GCC/Clang/MSVC, kiến trúc x86-64/ARM64/32-bit, packing, alignment và calling convention.
3. **Phiên bản build:** header có thể thay đổi theo feature macros hoặc version của thư viện.

Ví dụ những thay đổi có thể làm output probe khác:

- Thay `uint32_t` thành C `long`: trên Linux/x64 thường 8 bytes, Windows/x64 thường 4 bytes.
- Thay `uint8_t` bằng enum: kích thước enum và ABI quy định có thể khác giả định.
- Thêm `#pragma pack(push, 1)` xung quanh struct: offset 4 có thể thành 1; alignment toàn struct có thể giảm.
- Dùng `_Alignas(16)`/attribute alignment: struct size/align có thể tăng.
- Dùng compiler flags ảnh hưởng ABI: C probe và thư viện có thể không còn tương thích nếu build khác flags.
- Dùng `long double` hoặc SIMD vector: alignment và representation tùy nền tảng rất đáng kể.
- Dùng conditional field trong header: phiên bản/tham số build quyết định layout thực.

Đó là lý do quy trình nên **biên dịch probe bằng đúng C compiler, flags và header** mà native binary production dùng. Nếu code Java chạy trên nhiều OS, cần **một bộ expected C measurements theo từng target ABI** hoặc kiểm tra động khi build/package.

### 12.1. Kiểu pointer và `size_t`

Không mặc định `sizeof(void*) == sizeof(long)`. Điều này thường đúng trên LP64 Linux/x86-64 nhưng có thể sai trên LLP64 Windows/x64.

C probe thêm:

~~~c
/* Thêm vào main nếu struct chứa pointers hoặc size_t. */
printf("pointer.size=%zu\n", sizeof(void*));
printf("pointer.align=%zu\n", (size_t)_Alignof(void*));
printf("size_t.size=%zu\n", sizeof(size_t));
printf("size_t.align=%zu\n", (size_t)_Alignof(size_t));
~~~

Java FFM JDK 22+ có `ValueLayout.ADDRESS` để biểu diễn pointer-sized C address. Với `size_t` hoặc C `long`, kiểm tra `Linker.nativeLinker().canonicalLayouts()` và C ABI; không gắn `ValueLayout.JAVA_LONG` như một chân lý đa nền tảng. Một số ABI có nhiều C typedef names đại diện các widths khác nhau, nên descriptor/layout phải xác định theo loại C thật, không theo tên Java gần giống.

### 12.2. Endianness và unsigned

Hai layout có cùng `sizeof/alignof/offsetof` vẫn có thể khác **cách diễn giải byte**. Ví dụ Java `ValueLayout.JAVA_INT` dùng native byte order mặc định, trong khi `withOrder(ByteOrder.BIG_ENDIAN)` có thể thay cách diễn giải byte của layout khi đọc/ghi.

Nếu thư viện C nhận network packet hoặc file format có byte order cố định, bạn cần kiểm tra **format specification** và áp dụng layout order đúng; không thể kết luận chỉ từ việc `byteSize` bằng `sizeof`.

C `uint32_t` có giá trị tới `2^32 − 1`; Java `int` signed chỉ tới `2^31 − 1`. Layout khớp nhưng ý nghĩa giá trị có thể cần xử lý bằng `Integer.toUnsignedLong`, masks hoặc type phù hợp.

## 13. Packed structs: khi alignment tự nhiên không còn đúng

Xét C code dùng compiler extension:

~~~c
/* Minh họa GCC/Clang-specific, không phải C11 portable. */
typedef struct __attribute__((packed)) PackedPacket {
    uint8_t  kind;
    uint32_t count;
    double   factor;
    uint8_t  enabled;
} PackedPacket;
~~~

Một GCC/Clang target thông dụng có thể cho:

~~~text
sizeof(PackedPacket)      = 14
_Alignof(PackedPacket)    = 1
offsetof(count)           = 1
offsetof(factor)          = 5
offsetof(enabled)         = 13
~~~

Đây là **biến thể do extension** chứ không phải `Packet` tự nhiên ở phần 3. C code đọc packed fields có thể phải xử lý unaligned access tùy kiến trúc/compiler; trên một số CPU, việc tạo raw pointer tới member không căn chỉnh rồi dereference sai có thể nguy hiểm.

Java có thể cần `ValueLayout.JAVA_INT_UNALIGNED` hoặc layout có `withByteAlignment(1)`, cộng lại padding/offset theo đúng C output. **Không** lén thay `JAVA_INT` bằng unaligned chỉ để bỏ `IllegalArgumentException` trong thiết kế vốn không packed.

Với MSVC, `#pragma pack` hoặc platform-specific definitions, cần probe trên đúng compiler đó. Nếu thư viện C muốn ABI portable, cân nhắc expose getter/setter hoặc hàm serialize thay vì công khai packed struct layout không ổn định.

## 14. Cần kiểm tra thêm những loại layout phức tạp nào?

### 14.1. Union

C union có các thành viên **chồng lên nhau từ offset 0**; `sizeof(union)` và alignment phụ thuộc member lớn nhất cùng quy tắc padding ABI. Trong FFM dùng `MemoryLayout.unionLayout(...)`, không dùng `structLayout(...)`.

~~~c
/* C11 minh họa: union, không nằm trong probe chính. */
typedef union Number {
    uint32_t integer;
    double   floating;
} Number;
~~~

~~~java
// Java 22+ minh họa kiểu layout tương ứng theo ABI giả định.
MemoryLayout NUMBER = MemoryLayout.unionLayout(
        ValueLayout.JAVA_INT.withName("integer"),
        ValueLayout.JAVA_DOUBLE.withName("floating")
).withName("Number");
~~~

Phải kiểm `sizeof(Number)` và `_Alignof(Number)` bằng C. Đừng suy rằng kích thước union luôn đúng bằng kích thước một trường duy nhất mà bỏ alignment.

### 14.2. Flexible array member

~~~c
/* C99+ minh họa kiểu có trailing flexible array. */
typedef struct Message {
    uint32_t length;
    uint8_t  payload[];
} Message;
~~~

`sizeof(Message)` **không bao gồm** bytes của mảng động theo chiều dài payload. Offset của `payload` được lấy bằng `offsetof(Message, payload)`; kích thước allocation thực khi chứa N bytes cần được tính theo hợp đồng và yêu cầu alignment. Với FFM, không dùng `sequenceLayout(0,...)` hoặc `sizeof(Message)` làm bảo đảm toàn bộ vùng payload đã cấp phát; phải tính tổng size và bounds chính xác.

### 14.3. Pointer members và ownership

~~~c
/* C11 minh họa; pointer không phải inline char array. */
typedef struct View {
    const char *data;
    size_t length;
} View;
~~~

FFM có thể mô hình hóa member `data` bằng `ValueLayout.ADDRESS`, nhưng việc đọc `data` từ native struct trả **một pointer value**, không có nghĩa Java có quyền đọc tùy ý length bytes. Cần hợp đồng chỉ rõ pointer do ai cấp phát, có NUL terminator không, có valid bounds không, khi nào bị free và liệu Java phải tạo restricted view hay copy.

**Không** biến một pointer thành dữ liệu inlined để “đủ size” khi so sánh struct. Và không dùng `reinterpret` để đoán kích thước pointer target nếu chưa được API C xác nhận.

### 14.4. Nested arrays

C:

~~~c
typedef struct Grid {
    uint8_t  tag;
    uint32_t cells[3];
} Grid;
~~~

FFM dùng `MemoryLayout.sequenceLayout(3, ValueLayout.JAVA_INT)` tại vị trí offset đã căn chỉnh và phải chèn padding trước mảng nếu cần. `offsetof(Grid, cells)` cho biết offset bắt đầu, `sizeof(((Grid*)0)->cells)` hoặc `sizeof(uint32_t[3])` cho kích thước mảng inline; tránh nhầm nó thành `uint32_t*`.

Với các layout phức tạp, làm C probe **từng field** trước khi tạo layout Java; không cố diễn giải cả struct bằng một `ByteBuffer` không kiểm chứng.

## 15. C11 compile-time assertions làm hàng rào ABI

C probe cho số liệu runtime, còn `_Static_assert` giúp từ chối build ngay nếu layout không đúng một ABI đã công bố. Ví dụ dành **riêng** cho Linux/x86-64 layout tự nhiên của bài:

~~~c
/* Minh họa bổ sung vào TU C đã định nghĩa Packet.
   Chỉ bật khi dự án chủ ý khóa ABI này. */
_Static_assert(sizeof(Packet) == 24, "Packet size changed");
_Static_assert(_Alignof(Packet) == 8, "Packet alignment changed");
_Static_assert(offsetof(Packet, count) == 4, "count offset changed");
_Static_assert(offsetof(Packet, factor) == 8, "factor offset changed");
_Static_assert(offsetof(Packet, enabled) == 16, "enabled offset changed");
~~~

Đừng đặt các giá trị số này thành “chuẩn C portable”. Nếu target khác có ABI đúng nhưng layout khác, `_Static_assert` trên sẽ fail theo thiết kế, và dự án phải cập nhật contract cho target đó.

Bản tương ứng trong Java có thể check programmatically:

~~~java
// Java 22+, minh họa trong scope có PACKET và offset(...).
if (PACKET.byteSize() != 24 ||
        PACKET.byteAlignment() != 8 ||
        offset("count") != 4 ||
        offset("factor") != 8 ||
        offset("enabled") != 16) {
    throw new IllegalStateException("FFM Packet layout mismatch");
}
~~~

Nhưng **so sánh output C và Java trên build target** mạnh hơn việc chỉ hardcode các con số mà C compiler chưa đo. Tốt nhất: C probe là nguồn kiểm chứng, Java layout là triển khai, CI so hai bên và test memory values.

## 16. Các lỗi phổ biến khi làm bài kiểm chứng này

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tính `sizeof` bằng tổng kích thước fields | Bỏ internal/tail padding | Lấy `sizeof(struct)` thật bằng C probe |
| Chỉ so `sizeof`, không so align/offset | Các fields có thể bị đặt sai dù total size giống | So cả `_Alignof` và từng `offsetof` |
| Tin `structLayout` tự thêm padding | Có thể bị từ chối do alignment hoặc offset sai | Chèn `paddingLayout` tường minh |
| Chèn padding trước fields nhưng quên padding cuối | `sequenceLayout`/array stride sai | So `sizeof(T[2]) / 2` với `layout.byteSize()` |
| So output C chạy trên Linux với Java trên Windows | Hai ABI khác | Cùng target OS/architecture/toolchain |
| C probe include header khác native library | ABI probe không đại diện binary production | Dùng cùng header, flags và version |
| Ép `withByteAlignment(1)` để “tránh exception” | Đổi layout thành packed giả | Đo C alignment và giữ đúng ABI |
| Dùng `sizeof(pointer)` thay `sizeof(array)` | Thiếu kích thước nhiều phần tử | Probe đúng type mảng, tính stride |
| Dùng `%d` in `size_t` | Format/argument type mismatch | Dùng `%zu` |
| Dùng `offsetof` cho bit-fields | Không hợp lệ vì bit-field không addressable | Đổi sang C accessor/mask theo ABI |
| Đọc `uint32_t` như signed Java int mà không chuyển | Các giá trị lớn bị âm | `Integer.toUnsignedLong` hoặc unsigned contract |
| Chỉ đọc/ghi Java với cùng layout rồi tự nhận khớp C | Lỗi offset Java có thể tự triệt tiêu | So với output probe C và test two-way |
| Dùng raw pointer sau khi close arena | Use-after-free/native crash | Giữ đúng lifetime và ownership |
| Đo trên compiler debug nhưng thư viện build packed | Khác flags/ABI | Probe khớp production toolchain |
| Ghi vào tail padding rồi dựa vào nội dung đó | Padding không mang ý nghĩa field hợp đồng | Chỉ đọc/ghi named fields, không phụ thuộc byte padding |
| Nhầm `byteAlignment` với độ rộng của `JAVA_INT` | Size4 không phải mọi ABI align4 | Đo `_Alignof` kiểu C đúng target |

## 17. Quy trình thực tế cho một thư viện native không do bạn viết

1. **Tìm struct thật** từ public C header được binary của thư viện sử dụng. Kiểm tra typedefs, `#ifdef`, packing macros và version.
2. Tạo `abi_probe.c` include **header thật** thay vì copy một struct viết lại bằng tay khi kiểm production. Copy lại định nghĩa có thể giấu khác biệt.
3. Chạy probe với compiler/flags/cross-compiler đúng target. Nếu dùng cross-compile không thể thực thi binary trên host, chạy trên target hoặc qua runner/emulator đáng tin.
4. Ghi số liệu `sizeof`, `_Alignof`, `offsetof` và kích thước của các member types. Nếu struct chứa nested arrays, unions hoặc pointers, đo thêm các đặc điểm tương ứng.
5. Dựng FFM `MemoryLayout.structLayout/unionLayout/sequenceLayout`, chèn `paddingLayout` theo C ABI. Chọn đúng `ValueLayout`, order, alignment và các pointer layouts.
6. Chạy chương trình Java mô tả layout và `diff` với output probe. Nếu mismatch, sửa **layout Java hoặc build target**, không sửa C output thành con số tưởng tượng.
7. Thử native interoperability thật trên một instance: C tạo dữ liệu → Java đọc; Java ghi → C đọc. Kiểm tra fields, signed/unsigned, floating point, pointer ownership, arrays và lifetime.
8. Đưa kiểm chứng vào CI cho các target thực sự hỗ trợ. Khi header, compiler flags hoặc architecture thay đổi, probe phải chạy lại thay vì tin snapshot cũ.
9. Khi API hỗ trợ hủy/shutdown, không cho một C callback dùng pointer từ arena sau khi `arena.close()`.
10. Ghi rõ target ABI và giới hạn kiểm chứng trong tài liệu của binding.

### Gợi ý tổ chức build cho CI

~~~text
binding/
  native/
    include/
      mylibrary.h
    abi_probe.c       # include header thật
  java/
    LayoutVerify22.java
  scripts/
    verify-abi.sh    # build C + Java rồi diff output
~~~

Đây là **cấu trúc minh họa**, không yêu cầu dự án phải có những thư mục này. Với chương trình mẫu bài học, chỉ cần hai tệp `abi_probe.c` và `LayoutVerify22.java`, không cần thư viện C chung hoặc JNI library.

## 18. Checklist trước khi đánh dấu một C layout đã được kiểm chứng

- [ ] C probe dùng `sizeof`, `_Alignof`/`alignof` và `offsetof` từ header chuẩn đúng cách.
- [ ] `%zu` được dùng cho mọi kết quả `size_t`.
- [ ] C program được build với cùng C ABI/compiler flags như native library cần tích hợp.
- [ ] `Packet` có đủ **internal padding và tail padding**.
- [ ] Java `PACKET.byteSize()` bằng `sizeof(Packet)`.
- [ ] Java `PACKET.byteAlignment()` bằng `_Alignof(Packet)`.
- [ ] Mọi `byteOffset(groupElement(field))` bằng `offsetof(Packet, field)`.
- [ ] `sequenceLayout` stride bằng `sizeof(Packet)`.
- [ ] Nested offsets trong `Envelope` cũng khớp.
- [ ] Không dùng metadata `byteSize/byteAlignment` để suy ra byte order/value semantics.
- [ ] Đã kiểm tra signed vs unsigned và định dạng float/pointer khi cần.
- [ ] Không dùng `offsetof` cho bitfields.
- [ ] Khi struct packed hoặc có alignment extension, probe đúng compiler target và mô tả Java chính xác.
- [ ] Không để segment hoặc native pointer vượt quá lifetime arena.
- [ ] CI so sánh hai output **tự động**, fail khi có mismatch.
- [ ] Nếu có thay đổi header/version, đã đo lại thay vì giữ những số cũ.

## 19. Câu hỏi tự kiểm tra

1. Vì sao tổng kích thước bốn thành viên `Packet` là 14 bytes nhưng `sizeof(Packet)` thường là 24 bytes trên Linux/x86-64?
2. `_Alignof(Packet)` đo tính chất gì? Có giống lấy địa chỉ một biến Packet rồi đếm số bit 0 cuối không?
3. `offsetof(Packet, count)` bằng bao nhiêu trong ví dụ và vì sao?
4. Trường `enabled` bắt đầu ở offset 16 và kết thúc ở 17. Vì sao struct lại có tổng size 24?
5. Java `MemoryLayout.structLayout` có tự thêm padding trước `JAVA_INT` không?
6. `MemoryLayout.paddingLayout(3)` đo theo bits hay bytes trong JDK 22?
7. Lý do phải so `byteAlignment()` và từng `byteOffset(...)` thay vì chỉ `byteSize()`?
8. Làm sao đo offset của `Envelope.packet.count` từ C và Java?
9. Nếu `diff` không in gì và trả status 0, điều đó chứng minh được gì? Những điều gì chưa chứng minh?
10. Java `int` và C `uint32_t` có cùng semantics mọi giá trị không?
11. Có thể áp dụng expected `packet.size=24` của Linux/x86-64 vào mọi nền tảng không?
12. Vì sao packed C struct có thể cần Java unaligned layouts?
13. `offsetof` có hợp lệ cho bit-field không?
14. Trong Java chế độ `--memory`, việc ghi rồi đọc lại đúng giá trị đã chứng minh layout khớp C chưa?
15. Tại sao `sizeof(Packet[2]) / 2` là phép kiểm bổ ích?
16. Vì sao chương trình C probe production nên include header thật thay vì chép lại struct?
17. Trong FFM, `VarHandle` tạo từ layout path và `MemorySegment.get` với offset có điểm khác gì cần tránh?
18. Nếu một native function nhận pointer tới segment, có thể cho C giữ pointer sau khi arena đóng không?

**Đáp án gợi ý:** (1) 3 bytes internal và 7 bytes tail padding; (2) alignment requirement của kiểu C, không phải địa chỉ ngẫu nhiên; (3) 4, phải căn `uint32_t` theo bội của 4; (4) tail padding để sizeof là bội của align8 và array stride đúng; (5) không; (6) bytes; (7) cùng size vẫn có thể sai field layout và alignment; (8) `offsetof(Envelope, packet.count)` và nested `byteOffset` path; (9) các đại lượng đo khớp trên target đó, chưa xác minh toàn bộ ABI/endianness/ownership; (10) không; (11) không, phụ thuộc target ABI; (12) compiler giảm alignment, Java phải phản ánh chính xác; (13) không; (14) chưa, vì hai thao tác cùng dùng một Java layout; (15) kiểm tra stride/tail padding; (16) tránh định nghĩa bị lệch với binary; (17) `VarHandle` path cộng offset nội bộ, không cộng tay lần nữa; (18) không, sẽ có nguy cơ dangling pointer/use-after-free.

## 20. Tài liệu tham khảo chuẩn

- [Oracle Java SE 22 — `MemoryLayout`, `structLayout`, `paddingLayout`, `byteOffset`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html)
- [Oracle Java SE 22 — `StructLayout`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/StructLayout.html)
- [Oracle Java SE 22 — `ValueLayout`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [Oracle Java SE 22 — `MemorySegment`, `get/set` và `byteSize`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Oracle Java SE 22 — `Arena`, `allocate` và lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API (Final), JDK 22](https://openjdk.org/jeps/454)
- [C reference — `sizeof`](https://en.cppreference.com/w/c/language/sizeof)
- [C reference — `_Alignof` / `alignof`](https://en.cppreference.com/w/c/language/alignof)
- [C reference — `offsetof`](https://en.cppreference.com/w/c/types/offsetof)
- [C reference — Objects, alignment và padding](https://en.cppreference.com/w/c/language/object)

**Kết luận:** Một Java FFM struct layout chỉ đáng tin khi **C compiler thực tế xác nhận** kích thước, alignment, offsets và stride của layout đó. Hãy dùng chương trình C11 `sizeof` + `_Alignof` + `offsetof`, mô tả tường minh padding trong `MemoryLayout.structLayout`, chạy Java verifier trên cùng target ABI và so output tự động. Đừng đoán field offsets theo cảm tính, đừng dùng `structLayout` như thể nó tự padding, và đừng kết luận “interop an toàn” chỉ vì Java tự ghi/đọc thành công.
