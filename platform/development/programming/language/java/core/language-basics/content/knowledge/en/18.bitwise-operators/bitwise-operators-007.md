# Mặt nạ bit để đọc, bật, tắt và đảo cờ — Java 17+

## 1. Mặt nạ bit là gì?

**Mặt nạ bit** (*bit mask*) là một số nguyên có các bit 0/1 được dùng để chọn hoặc thao tác một số vị trí bit trong một số nguyên khác. Mỗi bit có thể biểu diễn một **cờ** (*flag*) độc lập: một tính năng đang bật, một trạng thái, hoặc một thuộc tính.

Ví dụ lưu bốn cờ trong một biến `int`:

| Cờ | Bit số | Giá trị thập phân | Nhị phân 4 bit |
|---|---:|---:|---|
| `READ` | 0 | 1 | `0001` |
| `WRITE` | 1 | 2 | `0010` |
| `EXECUTE` | 2 | 4 | `0100` |
| `ADMIN` | 3 | 8 | `1000` |

~~~java
static final int READ    = 1 << 0;
static final int WRITE   = 1 << 1;
static final int EXECUTE = 1 << 2;
static final int ADMIN   = 1 << 3;

int flags = READ | WRITE; // 0001 | 0010 = 0011 (3)
~~~

Mỗi cờ có **một bit 1 riêng**, nên có thể ghép bằng `|` mà không làm mất thông tin về các cờ khác. `flags` lúc này là 3, nghĩa là READ và WRITE cùng bật.

**Bốn thao tác cốt lõi:**

- **Đọc/kiểm tra:** `flags & mask`.
- **Bật:** `flags | mask`.
- **Tắt:** `flags & ~mask`.
- **Đảo:** `flags ^ mask`.

Các phép toán dùng trên số nguyên `byte`, `short`, `char`, `int`, `long` theo quy tắc nâng kiểu của Java; ví dụ chính của bài dùng `int`.

## 2. Từ phép toán từng bit đến thao tác cờ

Bốn công thức dựa trực tiếp vào cách mỗi toán tử xử lý bit tại cùng vị trí: AND (`&`) chỉ giữ 1 khi cả hai bit là 1; OR (`|`) bật 1 nếu một bit là 1; XOR (`^`) đảo bit khi mask bằng 1; NOT (`~`) đảo mọi bit của toán hạng đã nâng kiểu.

~~~text
  flags      0101
  mask       0011
  &          0001   (lọc các bit chung)
  |          0111   (bật bit đã chọn)
  ^          0110   (đảo bit đã chọn)
~~~

Bảng chân trị đầy đủ thuộc bài về AND/OR/XOR/NOT. Ở đây điều quan trọng là **tác động lên trạng thái cờ**: dùng `&` để kiểm tra, `|` để bật, `& ~mask` để tắt, và `^` để đảo. `~` trên `int` đảo 32 bit, vì vậy thường được kết hợp với `&` hoặc một mask giới hạn vùng cần thao tác.

## 3. Đọc một cờ: AND với mask

Muốn biết cờ READ có bật:

~~~java
boolean canRead = (flags & READ) != 0;
~~~

Nếu `flags = 0b0101` (READ và EXECUTE), ta có:

~~~text
flags = 0101
READ  = 0001
&     = 0001  -> khác 0 -> READ bật
~~~

Với WRITE:

~~~text
flags = 0101
WRITE = 0010
&     = 0000  -> bằng 0 -> WRITE tắt
~~~

**Dấu ngoặc rất quan trọng để rõ ý:** viết `(flags & READ) != 0`, không viết mơ hồ `flags & READ != 0`. Trong Java, `!=` có ưu tiên cao hơn `&`; dạng không ngoặc có thể trở thành phép bitwise AND giữa `int` và `boolean` và bị lỗi biên dịch.

Nếu mask là **một bit**, hai cách sau tương đương để kiểm tra nó:

~~~java
(flags & READ) != 0
(flags & READ) == READ
~~~

Nhưng với **mask nhiều bit**, ý nghĩa của hai cách khác nhau, xem phần sau.

## 4. Đọc nhiều cờ: phân biệt “bất kỳ” và “tất cả”

Giả sử:

~~~java
int flags = READ | WRITE;       // 0011
int required = READ | EXECUTE;  // 0101
~~~

**Có ít nhất một cờ trong mask:** (*any*):

~~~java
boolean any = (flags & required) != 0; // true: READ đang bật
~~~

**Có đầy đủ tất cả cờ trong mask:** (*all*):

~~~java
boolean all = (flags & required) == required; // false: EXECUTE chưa bật
~~~

| Kiểm tra | Công thức | Khi nào true? |
|---|---|---|
| **Một cờ** | `(flags & FLAG) != 0` | Bit của FLAG bật |
| **Bất kỳ cờ nào** | `(flags & mask) != 0` | Ít nhất một bit thuộc mask bật |
| **Tất cả cờ** | `(flags & mask) == mask` | Mọi bit thuộc mask đều bật |
| **Không có cờ nào** | `(flags & mask) == 0` | Không bit nào thuộc mask bật |

**Bẫy với mask bằng 0:** `(flags & 0) == 0` **luôn true**, kể cả `flags == 0`. Vì vậy `hasAll(flags, 0)` có thể trả true theo định nghĩa toán học (không có cờ bắt buộc). Nếu API nghiệp vụ không cho phép mask rỗng, **phải validate `mask != 0`**, đừng coi kết quả true là một trạng thái quyền hợp lệ.

## 5. Bật cờ bằng OR

Bật những bit được chọn nhưng giữ nguyên các bit khác:

~~~java
flags = flags | READ;
flags |= READ; // Viết gọn, cùng mục đích với biến int đơn giản
~~~

Ví dụ:

~~~text
flags  = 0100   (EXECUTE)
mask   = 0011   (READ | WRITE)
OR     = 0111   (cả ba bật)
~~~

~~~java
int flags = EXECUTE;
flags |= READ | WRITE;
System.out.println(flags); // 7
~~~

**Tính chất idempotent:** bật một cờ đã bật **không làm thay đổi giá trị**:

~~~java
flags |= READ;
flags |= READ; // vẫn giữ READ bật, không chuyển nó thành tắt
~~~

Nếu cần **đảo** trạng thái mỗi lần gọi thì dùng XOR `^`, không dùng OR.

## 6. Tắt cờ bằng AND với NOT

Muốn tắt các bit thuộc mask mà **giữ nguyên mọi bit khác**:

~~~java
flags &= ~WRITE;
~~~

Ví dụ:

~~~text
flags        = 0111   (READ | WRITE | EXECUTE)
WRITE        = 0010
~WRITE (4bit)= 1101
AND          = 0101   (READ | EXECUTE)
~~~

Trong thực tế Java, `~WRITE` là toán tử 32 bit với `int`, không chỉ đảo 4 bit. Nhưng thao tác `flags & ~WRITE` vẫn đúng vì bit WRITE bị 0 hóa, còn những vị trí bit khác trong mask `~WRITE` là 1, nên được giữ nguyên.

~~~java
int flags = READ | WRITE | EXECUTE;
flags &= ~WRITE;
System.out.println(flags); // 5
~~~

Tắt nhiều cờ cùng lúc:

~~~java
flags &= ~(READ | EXECUTE);
~~~

**Tính chất idempotent:** tắt cờ đã tắt sẽ không làm thay đổi giá trị.

**Không dùng `flags &= WRITE` khi muốn tắt WRITE:** thao tác đó **chỉ giữ lại** bit WRITE và xóa các bit khác. Muốn xóa WRITE phải dùng `~WRITE`.

## 7. Đảo cờ bằng XOR

XOR làm bit thuộc mask **đổi trạng thái**:

- 0 thành 1.
- 1 thành 0.

~~~java
int flags = READ; // 0001
flags ^= EXECUTE; // 0101: bật EXECUTE
flags ^= EXECUTE; // 0001: tắt EXECUTE
~~~

Bảng ý nghĩa:

| Trạng thái ban đầu của một bit | OR với 1 | AND với 0 | XOR với 1 |
|---|---|---|---|
| 0 (tắt) | Bật (1) | Tắt (0) | Bật (1) |
| 1 (bật) | Giữ bật (1) | Tắt (0) | Tắt (0) |

XOR **không idempotent** đối với bit trong mask: gọi hai lần sẽ quay về trạng thái đầu.

~~~java
int state = 0;
state ^= READ;
state ^= READ;
System.out.println(state); // 0
~~~

**Không dùng XOR để “bật chắc chắn” một cờ**, vì nếu cờ đã bật thì XOR sẽ tắt nó.

## 8. Quy trình quản lý cờ minh họa

~~~mermaid
flowchart TD
    A["Bắt đầu: flags = 0000"] --> B["flags |= READ | WRITE"]
    B --> C["0011: READ và WRITE bật"]
    C --> D["flags &= ~WRITE"]
    D --> E["0001: chỉ READ bật"]
    E --> F["flags ^= EXECUTE"]
    F --> G["0101: READ và EXECUTE bật"]
    G --> H["flags ^= EXECUTE"]
    H --> I["0001: EXECUTE lại tắt"]
~~~

Đây là thao tác **bitmask trên một biến số nguyên**, không tự tạo hệ thống cấp quyền thực tế. Nếu flags biểu diễn quyền truy cập thật, việc xác thực, phân quyền, dữ liệu đầu vào đáng tin cậy và đồng bộ trạng thái vẫn cần được thiết kế riêng.

## 9. Chọn vị trí cờ bằng phép dịch `1 << position`

Thay vì viết các số magic:

~~~java
static final int READ    = 1 << 0;
static final int WRITE   = 1 << 1;
static final int EXECUTE = 1 << 2;
static final int ADMIN   = 1 << 3;
~~~

Với `int`, vị trí bit hợp lệ là **0 đến 31**; với `long`, vị trí là **0 đến 63**:

~~~java
int highestIntBit = 1 << 31;
long highLongBit = 1L << 40;
~~~

**Hai cảnh báo:**

1. `1 << 31` bằng `Integer.MIN_VALUE`, tức một số **âm** do bit dấu được bật. Nó vẫn là một mask bit hợp lệ. Kiểm tra `(flags & highestIntBit) != 0`, **không dùng `> 0`**, vì AND có thể trả giá trị âm.
2. Khoảng dịch của int lấy **5 bit thấp**, của long lấy **6 bit thấp**. `1 << 32` thực chất là `1 << 0` → kết quả 1, dễ khiến **trùng cờ**. `1L << 32` mới tạo bit thứ 32 trên long.

Nếu `position` đến từ dữ liệu động, cần tự kiểm tra `0 <= position && position < 32` (hoặc `< 64` cho long); Java không tự ném lỗi nếu dịch quá phạm vi.

## 10. `~` đảo toàn bộ chiều rộng: nhớ giới hạn vùng bit cần dùng

~~~java
int flag = READ; // 0001
System.out.println(~flag); // -2
~~~

`~1` của int không phải `1110` đơn thuần; nó đảo **32 bit**, trở thành `0xFFFFFFFE` hay -2.

Nếu chỉ quan tâm **4 bit thấp**, mask lại:

~~~java
int FOUR_BITS = 0b1111;
int invertedWithin4Bits = (~READ) & FOUR_BITS;
System.out.println(invertedWithin4Bits); // 14 = 1110
~~~

**Đừng nhầm:** `~mask` đơn lẻ tạo giá trị có các bit cao bật; đó là bình thường trong `flags & ~mask` khi mục tiêu là **giữ nguyên tất cả bit khác**. Chỉ giới hạn lại bằng `& allowedBits` khi muốn một kết quả thực sự bị ràng buộc trong một vùng bit xác định.

## 11. `byte`, bit dấu và cách đọc 8 bit không dấu

Các phép bitwise với `byte`, `short` và `char` thường **nâng toán hạng lên `int`** trước khi tính. Một `byte` âm được sign-extend khi chuyển sang int.

~~~java
byte encoded = (byte) 0b1111_0000;
System.out.println(encoded);         // -16
System.out.println(encoded & 0xFF);  // 240
~~~

- Dưới dạng `byte` có dấu, bit `11110000` là -16.
- `encoded & 0xFF` chỉ giữ 8 bit thấp, trả `int` có giá trị 240 (diễn giải byte theo kiểu unsigned).

Với `byte`, phép gán kết hợp như `byteVar |= mask` có thể **thu hẹp ngầm** từ kết quả int về byte. Nếu cần xử lý flags 8 bit nhưng muốn biểu diễn các giá trị 128–255 không âm, dùng `int` sau khi mask `& 0xFF`, hoặc một mô hình dữ liệu khác có kiểm soát miền.

## 12. Viết helper rõ ý và kiểm tra mask

Một nhóm hàm đơn giản giúp tránh lặp công thức và nhầm **any** với **all**:

~~~java
static boolean hasAny(int flags, int mask) {
    return (flags & mask) != 0;
}
static boolean hasAll(int flags, int mask) {
    return (flags & mask) == mask;
}
static int enable(int flags, int mask) {
    return flags | mask;
}
static int disable(int flags, int mask) {
    return flags & ~mask;
}
static int toggle(int flags, int mask) {
    return flags ^ mask;
}
~~~

Các helper trên **không thay đổi biến đầu vào** (Java truyền `int` theo giá trị); chúng trả trạng thái mới khi bật/tắt/đảo. Người gọi phải gán kết quả trở lại nếu muốn cập nhật:

~~~java
flags = enable(flags, READ);
~~~

Đối với API có tập cờ hợp lệ `allowed`, nên **từ chối mask bằng 0 hoặc chứa bit lạ**:

~~~java
static void requireValidMask(int mask, int allowed) {
    if (mask == 0 || (mask & ~allowed) != 0) {
        throw new IllegalArgumentException("invalid flag mask");
    }
}
~~~

- `mask == 0`: ngăn trường hợp kiểm tra “all” trả true một cách rỗng.
- `(mask & ~allowed) != 0`: phát hiện **ít nhất một bit ngoài tập cho phép**.
- Hàm không tự chứng minh người dùng có quyền bật cờ; nó chỉ **validate hình dạng mask**.

## 13. Lỗi thường gặp

| Nhầm lẫn | Hậu quả | Cách đúng |
|---|---|---|
| Kiểm tra nhiều cờ bằng `(flags & mask) != 0` rồi hiểu là “đủ hết” | Chỉ cần một bit bật đã true | Dùng `(flags & mask) == mask` |
| `hasAll(flags, 0)` có nghĩa đã được cấp quyền | Kết quả true rỗng | Cấm mask 0 nếu không hợp lệ |
| Tắt cờ bằng `flags &= mask` | Xóa các bit khác, giữ bit mask | `flags &= ~mask` |
| Bật cờ bằng `flags ^= mask` | Có thể tắt cờ đang bật | `flags |= mask` |
| Dùng `flags & mask > 0` | Nhầm ưu tiên toán tử và bit dấu | `(flags & mask) != 0` |
| `~READ` chỉ đảo 4 bit | `~` đảo toàn bộ 32 bit của int | `(~READ) & 0b1111` khi cần 4 bit |
| `1 << 31` không hợp lệ vì âm | Bit dấu có thể dùng làm cờ | Kiểm tra `!= 0`, không `> 0` |
| `1 << 32` tạo bit thứ 32 | Shift của int mask 5 bit; thành bit 0 | Dùng `1L << 32` hoặc validate vị trí |
| `byte` lưu `0xF0` là 240 | byte có dấu trả -16 | `byteValue & 0xFF` để đọc unsigned |
| Dùng `&&` giữa hai giá trị int | Không biên dịch: `&&` cần boolean | Dùng `&` bitwise, sau đó so 0 |
| Nghĩ `flags |= mask` tự thread-safe | Read–modify–write không tự nguyên tử | Đồng bộ/`AtomicInteger` nếu chia sẻ đa luồng |
| Xem bitmask là hệ thống phân quyền đủ an toàn | Bitmask chỉ mô tả trạng thái | Kiểm tra quyền phía đáng tin cậy |

## 14. Chương trình Java 17 hoàn chỉnh

Lưu file đúng tên **`BitMaskFlagsDemo.java`**:

~~~java
public final class BitMaskFlagsDemo {
    private BitMaskFlagsDemo() {}

    static final int READ = 1 << 0;
    static final int WRITE = 1 << 1;
    static final int EXECUTE = 1 << 2;
    static final int ADMIN = 1 << 3;
    static final int ALL_ALLOWED = READ | WRITE | EXECUTE | ADMIN;

    static boolean hasAny(int flags, int mask) {
        return (flags & mask) != 0;
    }

    static boolean hasAll(int flags, int mask) {
        return (flags & mask) == mask;
    }

    static int enable(int flags, int mask) {
        return flags | mask;
    }

    static int disable(int flags, int mask) {
        return flags & ~mask;
    }

    static int toggle(int flags, int mask) {
        return flags ^ mask;
    }

    static void requireValidMask(int mask, int allowed) {
        if (mask == 0 || (mask & ~allowed) != 0) {
            throw new IllegalArgumentException("invalid flag mask");
        }
    }

    public static void main(String[] args) {
        int flags = 0;
        System.out.println("initial=" + flags);

        flags = enable(flags, READ | WRITE);
        System.out.println("enabled READ|WRITE=" + flags);
        System.out.println("has READ=" + hasAny(flags, READ));
        System.out.println("has EXECUTE=" + hasAny(flags, EXECUTE));
        System.out.println("has both READ|WRITE="
                + hasAll(flags, READ | WRITE));
        System.out.println("has both READ|EXECUTE="
                + hasAll(flags, READ | EXECUTE));
        System.out.println("has any WRITE|EXECUTE="
                + hasAny(flags, WRITE | EXECUTE));

        flags = disable(flags, WRITE);
        System.out.println("disabled WRITE=" + flags);

        flags = toggle(flags, EXECUTE);
        System.out.println("toggle EXECUTE on=" + flags);
        flags = toggle(flags, EXECUTE);
        System.out.println("toggle EXECUTE off=" + flags);

        flags = enable(flags, ADMIN);
        System.out.println("enabled ADMIN=" + flags);
        flags = disable(flags, READ | ADMIN);
        System.out.println("cleared READ|ADMIN=" + flags);

        System.out.println("all with zero mask=" + hasAll(flags, 0));
        System.out.println("any with zero mask=" + hasAny(flags, 0));

        flags = enable(flags, READ | EXECUTE);
        System.out.println("current binary="
                + Integer.toBinaryString(flags));
        System.out.println("allowed binary="
                + Integer.toBinaryString(ALL_ALLOWED));
        System.out.println("~READ raw=" + (~READ));
        System.out.println("~READ within four bits="
                + ((~READ) & ALL_ALLOWED));

        byte encoded = (byte) 0b1111_0000;
        System.out.println("byte signed=" + encoded);
        System.out.println("byte unsigned=" + (encoded & 0xFF));

        int highBit = 1 << 31;
        int withHigh = highBit;
        System.out.println("high bit flag=" + withHigh);
        System.out.println("high bit detected="
                + hasAny(withHigh, highBit));
        System.out.println("high bit unsigned="
                + Integer.toUnsignedLong(withHigh));

        System.out.println("1 << 32=" + (1 << 32));
        System.out.println("1L << 32=" + (1L << 32));

        requireValidMask(READ | WRITE, ALL_ALLOWED);
        System.out.println("valid mask=accepted");
        try {
            requireValidMask(0, ALL_ALLOWED);
        } catch (IllegalArgumentException ex) {
            System.out.println("zero mask=" + ex.getMessage());
        }
        try {
            requireValidMask(1 << 4, ALL_ALLOWED);
        } catch (IllegalArgumentException ex) {
            System.out.println("unknown mask=" + ex.getMessage());
        }
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên; mở terminal tại thư mục chứa `BitMaskFlagsDemo.java`. Chương trình không dùng thư viện ngoài JDK, không cần Maven/Gradle.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 BitMaskFlagsDemo.java
java -cp . BitMaskFlagsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\BitMaskFlagsDemo.java
java -cp . BitMaskFlagsDemo
~~~

### Exact expected stdout

~~~text
initial=0
enabled READ|WRITE=3
has READ=true
has EXECUTE=false
has both READ|WRITE=true
has both READ|EXECUTE=false
has any WRITE|EXECUTE=true
disabled WRITE=1
toggle EXECUTE on=5
toggle EXECUTE off=1
enabled ADMIN=9
cleared READ|ADMIN=0
all with zero mask=true
any with zero mask=false
current binary=101
allowed binary=1111
~READ raw=-2
~READ within four bits=14
byte signed=-16
byte unsigned=240
high bit flag=-2147483648
high bit detected=true
high bit unsigned=2147483648
1 << 32=1
1L << 32=4294967296
valid mask=accepted
zero mask=invalid flag mask
unknown mask=invalid flag mask
~~~

### Giải thích nhóm kết quả

1. **Bật:** `READ|WRITE = 3`; sau khi tắt WRITE còn 1.
2. **Đọc:** `hasAny(3, WRITE|EXECUTE)` đúng vì WRITE bật, nhưng `hasAll(3, READ|EXECUTE)` sai vì EXECUTE tắt.
3. **Đảo:** XOR với EXECUTE hai lần biến `1 → 5 → 1`.
4. **Tắt nhiều:** xóa READ và ADMIN sau khi flags là 9 đưa flags về 0.
5. **Mask rỗng:** `hasAll(0,0)` true theo phép so mask; `hasAny(0,0)` false.
6. **Biểu diễn:** `flags = 5` có nhị phân `101`; `ALL_ALLOWED = 15` là `1111`.
7. **NOT:** `~1` là -2 vì đảo 32 bit; giới hạn lại 4 bit tạo 14.
8. **Byte:** mẫu bit `11110000` có `byte` ký hiệu -16, sau `& 0xFF` là 240.
9. **Bit dấu:** mask `1 << 31` mang giá trị `int` âm; kiểm tra `!= 0` vẫn chính xác.
10. **Khoảng dịch:** `1 << 32` quay lại bit 0 với `int`, còn `1L << 32` tạo bit thứ 32 trên `long`.
11. **Validation:** mask thuộc tập cho phép được chấp nhận, mask bằng 0 hoặc có bit lạ bị từ chối.

## 15. Bài tập có đáp án

### Bài A — bật và kiểm tra hai cờ

~~~java
int flags = 0;
flags |= READ | EXECUTE;
System.out.println((flags & READ) != 0);
System.out.println((flags & WRITE) != 0);
~~~

**Đáp án:**

~~~text
true
false
~~~

### Bài B — any khác all

~~~java
int flags = READ | WRITE;
int mask = READ | EXECUTE;

System.out.println((flags & mask) != 0);
System.out.println((flags & mask) == mask);
~~~

**Đáp án:**

~~~text
true
false
~~~

### Bài C — xóa một cờ, giữ cờ còn lại

~~~java
int flags = READ | WRITE | EXECUTE;
flags &= ~WRITE;
System.out.println(flags);
~~~

**Đáp án:** `5`, gồm READ và EXECUTE.

### Bài D — đảo hai lần

~~~java
int flags = READ;
flags ^= ADMIN;
flags ^= ADMIN;
System.out.println(flags);
~~~

**Đáp án:** `1`. XOR hai lần cùng mask trả về trạng thái đầu.

### Bài E — mask cao nhất của `int`

~~~java
int highest = 1 << 31;
System.out.println(highest);
System.out.println((highest & highest) != 0);
System.out.println((highest & highest) > 0);
~~~

**Đáp án:**

~~~text
-2147483648
true
false
~~~

Cờ bit dấu vẫn bật, nên **không dùng `> 0` để kiểm tra bitmask**.

### Bài F — mask zero và vị trí bit sai

Vì sao `hasAll(flags, 0)` luôn true? Vì sao `1 << 32` không đại diện bit thứ 32 của `int`?

**Đáp án:** `flags & 0` luôn bằng 0, nên so với mask 0 cho true. Với int 32 bit, Java chỉ dùng 5 bit thấp của lượng dịch: `32 & 31 = 0`, nên `1 << 32` bằng `1 << 0`. Cần validate mask/vị trí theo miền hợp lệ.

## 16. Checklist và kết luận

- [ ] Biết tạo cờ riêng bằng `1 << position` hoặc `1L << position`.
- [ ] Biết ghép các cờ bằng OR `|`.
- [ ] Biết đọc một/ít nhất một cờ bằng `(flags & mask) != 0`.
- [ ] Biết kiểm tra đủ mọi cờ bằng `(flags & mask) == mask`.
- [ ] Biết bật bằng `flags |= mask`, tắt bằng `flags &= ~mask`, đảo bằng `flags ^= mask`.
- [ ] Hiểu OR bật và AND-NOT tắt là idempotent; XOR đảo mỗi lần gọi.
- [ ] Không nhầm `~` bitwise với `!` boolean.
- [ ] Hiểu `~` đảo mọi bit của int/long; dùng mask bổ sung khi chỉ cần vùng bit thấp.
- [ ] Biết trường hợp `hasAll(flags, 0)` true và vì sao phải validate mask rỗng.
- [ ] Nhận diện bit dấu `1 << 31` và chỉ kiểm tra `!= 0`, không `> 0`.
- [ ] Hiểu `byte` có dấu và `& 0xFF` để diễn giải 8 bit không dấu.
- [ ] Validate vị trí bit: int 0–31, long 0–63.
- [ ] Không nhầm bitmask với giải pháp bảo mật hoặc đồng bộ đa luồng đầy đủ.
- [ ] Biên dịch và chạy `BitMaskFlagsDemo.java` trên Java 17+; đối chiếu chính xác stdout.

**Kết luận:** Mặt nạ bit giúp lưu nhiều cờ độc lập trong một biến số nguyên. Hãy nhớ bốn quy tắc **đọc bằng `&`**, **bật bằng `|`**, **tắt bằng `& ~`**, **đảo bằng `^`**. Khi triển khai, phân biệt kiểm tra *any/all*, kiểm soát mask 0 và bit không hợp lệ, hiểu bit dấu/độ rộng số nguyên và giữ rõ ý định nghiệp vụ.