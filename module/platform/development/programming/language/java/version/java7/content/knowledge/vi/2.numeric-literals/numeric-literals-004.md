# Biểu diễn mặt nạ và tổ hợp cờ bit trong Java

## 1. Mặt nạ bit là gì, dùng để làm gì?

Một số nguyên có nhiều vị trí bit, mỗi vị trí có thể mang giá trị `0` hoặc `1`. **Cờ bit (bit flag)** dùng một vị trí bit để biểu diễn một lựa chọn độc lập, còn **mặt nạ bit (bit mask)** là mẫu bit dùng để chọn, kiểm tra hoặc thay đổi một hay nhiều vị trí đó. **Tổ hợp cờ** là kết quả gộp nhiều cờ thành cùng một giá trị nguyên.

Ví dụ, ứng dụng có bốn tính năng độc lập:

| Cờ | Vị trí bit | Mặt nạ nhị phân | Giá trị thập phân |
| --- | ---: | --- | ---: |
| `READ` | 0 | `0b0001` | 1 |
| `WRITE` | 1 | `0b0010` | 2 |
| `EXECUTE` | 2 | `0b0100` | 4 |
| `ARCHIVE` | 3 | `0b1000` | 8 |

Khi một bản ghi có `READ` và `WRITE`, giá trị của nó là `0b0011` (3). Nếu có thêm `EXECUTE`, giá trị trở thành `0b0111` (7). Mỗi bit lưu trạng thái bật/tắt của **một cờ riêng**, nhờ đó tổ hợp có thể được xử lý bằng toán tử bit.

Từ Java 7, Java cho phép viết trực tiếp literal nhị phân bằng `0b` hoặc `0B`. Cú pháp này **vẫn hợp lệ trong Java hiện nay** và rất phù hợp khi đọc mặt nạ ngắn. Với nhiều bit, literal thập lục phân (`0x...`) hoặc biểu thức dịch bit cũng có thể rõ ràng hơn. Đây chỉ là cách biểu diễn giá trị trong mã nguồn; `0b0100`, `4` và `0x4` đều biểu diễn cùng một số.

Các trường hợp sử dụng điển hình: trạng thái on/off độc lập, cờ tùy chọn cấu hình, mặt nạ sự kiện, thao tác bit trong giao thức nhị phân, và đóng gói một số trường nhỏ vào một từ số nguyên. Với quyền truy cập thực tế, các cờ chỉ là cách lưu/biểu diễn; việc cho phép thao tác phải được kiểm tra ở phía hệ thống đáng tin cậy.

## 2. Tạo cờ đúng: mỗi cờ là một lũy thừa của hai

Một cờ độc lập phải có **chính xác một bit bằng 1**, nghĩa là có giá trị `2^n` với vị trí `n` tính từ 0. Có thể định nghĩa theo hai cách tương đương:

```java
static final int READ    = 0b0001;  // 1
static final int WRITE   = 0b0010;  // 2
static final int EXECUTE = 0b0100;  // 4
static final int ARCHIVE = 0b1000;  // 8
```

Hoặc biểu diễn tường minh vị trí bit:

```java
static final int READ    = 1 << 0;
static final int WRITE   = 1 << 1;
static final int EXECUTE = 1 << 2;
static final int ARCHIVE = 1 << 3;
```

Toán tử `<<` dịch trái, nên `1 << 3` tạo giá trị `0b1000`. Cách này hữu ích khi có nhiều cờ hoặc vị trí bit được quy định rõ trong giao thức. `static final` giúp đặt tên cho ý nghĩa của từng cờ và tránh rải các số nguyên khó hiểu trong chương trình.

Không dùng giá trị `3` làm một **cờ độc lập**: `3 = 0b0011` đã là **tổ hợp** của hai cờ `1` và `2`. Nếu hai cờ sử dụng chồng cùng một bit thì không thể phân biệt chúng khi kiểm tra. Giá trị `0` thường có nghĩa **không bật cờ nào**, không phải một cờ bật được. Tổ hợp `READ | WRITE` có giá trị 3, nhưng bản thân 3 không nên được cấp một tên cờ đơn như `THIRD_FLAG`.

## 3. Sáu thao tác cốt lõi với cờ bit

Giả sử:

```java
int flags = READ | WRITE;  // 0b0011
```

| Ý định | Biểu thức Java | Ý nghĩa |
| --- | --- | --- |
| Gộp nhiều cờ | `READ | WRITE` | `|` (OR) bật các bit xuất hiện trong ít nhất một toán hạng |
| Bật cờ | `flags |= EXECUTE` | Bật bit `EXECUTE`, giữ nguyên những bit khác |
| Kiểm tra một cờ | `(flags & READ) != 0` | `&` (AND) giữ những bit chung; khác 0 tức cờ đang bật |
| Kiểm tra **mọi** cờ trong nhóm | `(flags & required) == required` | Tất cả bit trong `required` đều phải bật |
| Kiểm tra **bất kỳ** cờ nào trong nhóm | `(flags & required) != 0` | Ít nhất một bit trong `required` phải bật |
| Tắt cờ | `flags &= ~WRITE` | `~` đảo tất cả bit của mặt nạ; `&` giữ các bit còn lại |
| Đảo trạng thái | `flags ^= EXECUTE` | `^` (XOR) đảo bit được chỉ định: 0 thành 1, 1 thành 0 |

Bảng có bảy thao tác vì **kiểm tra đủ tất cả** và **kiểm tra có ít nhất một** là hai yêu cầu khác nhau, không được gộp nhầm.

### Gộp và bật cờ bằng OR (`|`)

```text
READ      0001
WRITE     0010
---------------- OR
          0011
EXECUTE   0100
---------------- OR
          0111
```

`flags |= EXECUTE` tương đương `flags = flags | EXECUTE`. Bật cùng một cờ hai lần không tạo hiệu ứng phụ: bit vẫn là 1. Do đó OR phù hợp khi yêu cầu chắc chắn **bật** cờ.

### Kiểm tra cờ bằng AND (`&`)

```java
boolean hasRead = (flags & READ) != 0;
boolean hasBoth = (flags & (READ | WRITE)) == (READ | WRITE);
boolean hasEither = (flags & (WRITE | EXECUTE)) != 0;
boolean hasNone = (flags & (WRITE | EXECUTE)) == 0;
```

Lưu ý: `hasBoth` yêu cầu cả hai bit đều bật, còn `hasEither` chỉ yêu cầu ít nhất một bit. Với `flags = 0b0001` thì `hasBoth` là `false` và `hasEither` cũng là `false`.

**Đối với nhóm nhiều cờ, `(flags & required) != 0` không có nghĩa là tất cả đã bật.** Nếu muốn yêu cầu cả `READ` và `WRITE` thì cần so sánh với chính `required`. Khi `required == 0`, biểu thức kiểm tra tất cả `(flags & required) == required` luôn đúng theo quy tắc tập rỗng; nếu ứng dụng không chấp nhận yêu cầu rỗng, cần kiểm tra điều đó riêng.

### Tắt cờ bằng AND với NOT (`& ~`)

```text
flags         0111  (READ | WRITE | EXECUTE)
WRITE         0010
~WRITE       ...1101  (đảo tất cả 32 bit của int)
AND           0101  (READ | EXECUTE)
```

`flags &= ~WRITE` **chỉ xóa bit WRITE**, vẫn bảo toàn các cờ còn lại. Toán tử `~` có thể tạo số `int` âm vì đảo cả 32 bit; đó là hành vi bình thường, không phải lỗi của kỹ thuật xóa bit. Tắt một bit đã tắt sẽ không thay đổi kết quả.

### Đảo bit bằng XOR (`^`)

`flags ^= EXECUTE` đổi trạng thái hiện tại của `EXECUTE`; thực hiện lần nữa sẽ khôi phục trạng thái cũ. XOR phù hợp khi chủ ý **đảo**, chẳng hạn bật/tắt hiển thị bằng một thao tác chuyển đổi. Khi yêu cầu chắc chắn bật hoặc chắc chắn tắt, nên dùng `|=` hoặc `&= ~` để kết quả không phụ thuộc trạng thái ban đầu.

`^` là XOR theo bit trong Java, **không phải phép lũy thừa**. Để tính lũy thừa hai theo bit cho vị trí hợp lệ, dùng `1 << n`; không viết `2 ^ n` với ý nghĩa `2^n`.

## 4. Chương trình Java 17+ chạy độc lập

Ví dụ dưới đây kết hợp cả các thao tác cờ và một trường hai bit riêng, đồng thời in kết quả nhị phân đủ tám vị trí để dễ kiểm tra. Bốn bit thấp dùng cho các cờ; bit 4 và 5 dùng cho trường `mode`. Cần phân biệt rõ hai vùng bit này để không ghi đè lẫn nhau.

Tạo tệp **`BitMaskDemo.java`**:

```java
public class BitMaskDemo {
    private static final int READ = 1 << 0;
    private static final int WRITE = 1 << 1;
    private static final int EXECUTE = 1 << 2;
    private static final int ARCHIVE = 1 << 3;

    private static final int MODE_SHIFT = 4;
    private static final int MODE_MASK = 0b0011_0000;

    private static String bits8(int value) {
        return String.format("%8s", Integer.toBinaryString(value & 0xFF))
                .replace(' ', '0');
    }

    private static boolean hasAll(int flags, int required) {
        return (flags & required) == required;
    }

    public static void main(String[] args) {
        int flags = READ | WRITE;

        System.out.println("ban dau: " + bits8(flags));
        System.out.println("co READ: " + hasAll(flags, READ));
        System.out.println("co ca READ va WRITE: "
                + hasAll(flags, READ | WRITE));
        System.out.println("co EXECUTE: " + hasAll(flags, EXECUTE));

        flags |= EXECUTE;
        System.out.println("them EXECUTE: " + bits8(flags));

        flags &= ~WRITE;
        System.out.println("bo WRITE: " + bits8(flags));

        flags ^= EXECUTE;
        System.out.println("dao EXECUTE: " + bits8(flags));
        System.out.println("co WRITE hoac EXECUTE: "
                + ((flags & (WRITE | EXECUTE)) != 0));
        System.out.println("so bit bat: " + Integer.bitCount(flags));

        int mode = 2;
        int packed = flags | (mode << MODE_SHIFT);
        System.out.println("packed: " + bits8(packed));
        System.out.println("mode: "
                + ((packed & MODE_MASK) >>> MODE_SHIFT));

        packed = (packed & ~MODE_MASK) | (1 << MODE_SHIFT);
        System.out.println("mode sau cap nhat: "
                + ((packed & MODE_MASK) >>> MODE_SHIFT));
        System.out.println("packed sau cap nhat: " + bits8(packed));
    }
}
```

Biên dịch và chạy:

```bash
javac BitMaskDemo.java
java BitMaskDemo
```

Kết quả chuẩn:

```text
ban dau: 00000011
co READ: true
co ca READ va WRITE: true
co EXECUTE: false
them EXECUTE: 00000111
bo WRITE: 00000101
dao EXECUTE: 00000001
co WRITE hoac EXECUTE: false
so bit bat: 1
packed: 00100001
mode: 2
mode sau cap nhat: 1
packed sau cap nhat: 00010001
```

Diễn giải theo thứ tự:

1. `READ | WRITE` tạo `00000011`; bit 0 và bit 1 cùng bật.
2. `|= EXECUTE` bật bit 2, thành `00000111`.
3. `&= ~WRITE` xóa bit 1, thành `00000101`.
4. `^= EXECUTE` đảo bit 2 từ 1 xuống 0, chỉ còn `READ`: `00000001`. Vì không có `WRITE` hoặc `EXECUTE`, phép kiểm tra `!= 0` trả `false` và `Integer.bitCount` trả 1.
5. `mode = 2` được đưa vào bit 4–5, nên giá trị ghép là `00100001`. Mặt nạ `MODE_MASK` lấy đúng hai bit rồi `>>> 4` đưa chúng về vị trí thấp nhất, trả 2.
6. Cập nhật `mode` từ 2 thành 1 bằng cách xóa vùng bit 4–5 cũ rồi ghi vùng mới, tạo `00010001`; cờ `READ` vẫn được giữ.

Hàm `bits8` chỉ dùng để **định dạng in minh họa**: `Integer.toBinaryString` tự nó không thêm số 0 ở đầu. `value & 0xFF` lấy tám bit thấp, nên không dùng hàm này để kiểm tra toàn bộ 32 bit của một `int` lớn.

## 5. Đóng gói nhiều trường bit trong một số nguyên

Đóng gói trường bit (bit field) khác với tập cờ độc lập ở chỗ **một nhóm nhiều bit cùng biểu diễn một giá trị**. Ví dụ:

```text
Bit:        7 6 | 5 4 | 3 2 1 0
Ý nghĩa:   dự phòng | mode | các cờ
                    (2 bit) (4 bit)
```

Với `mode` dùng hai bit ở vị trí 4–5, giá trị hợp lệ là 0–3. Đặt:

```java
int modeShift = 4;
int modeMask  = 0b0011_0000;
int flagsMask = 0b0000_1111;
```

Các thao tác chính:

```java
// Giả sử đã định nghĩa READ = 0b0001, WRITE = 0b0010.
int flags = READ | WRITE;               // 00000011
int mode = 2;                            // 10 (hai bit)
int packed = flags | (mode << 4);        // 00100011

int decodedFlags = packed & flagsMask;   // 00000011
int decodedMode = (packed & modeMask) >>> modeShift; // 2

int newMode = 1;
packed = (packed & ~modeMask)
        | ((newMode << modeShift) & modeMask); // 00010011
```

**Quy trình đúng:** (1) xác định mỗi trường chiếm những vị trí bit nào, (2) tạo mặt nạ đúng độ rộng, (3) trước khi ghi một trường thì xóa các bit cũ của trường, (4) dịch và giới hạn giá trị mới về mặt nạ, (5) khi đọc thì dùng AND + dịch ngược. Các mặt nạ của những trường **không được chồng lấn**.

Khi nhận `newMode` từ dữ liệu đầu vào, **kiểm tra miền giá trị trước khi ghi**:

```java
if (newMode < 0 || newMode > 3) {
    throw new IllegalArgumentException("mode must be 0..3");
}
```

Biểu thức `(newMode << 4) & modeMask` sẽ cắt mất bit nằm ngoài vùng của `mode`; nếu không kiểm tra giới hạn, dữ liệu không hợp lệ có thể bị biến thành một giá trị khác mà chương trình không phát hiện. Thao tác đóng gói cần có hợp đồng rõ ràng về vị trí bit, độ rộng, giá trị hợp lệ và phiên bản định dạng khi trao đổi dữ liệu.

## 6. Độ rộng kiểu, bit dấu và phép dịch: những giới hạn cần biết

Các toán tử `&`, `|`, `^`, `~`, `<<`, `>>`, `>>>` hoạt động trên kiểu số nguyên. Với `byte`, `short` và `char`, các toán hạng thường được **nâng lên `int`** khi tính toán. Mặt nạ viết bằng `int` có 32 bit; mặt nạ `long` có 64 bit.

### Khi cần nhiều hơn 32 cờ

```java
int lowFlag = 1 << 5;
long highFlag = 1L << 40;
```

Với `long`, phải bắt đầu từ `1L`. Viết `1 << 40` **không** tạo bit 40, vì khoảng dịch của `int` chỉ sử dụng năm bit thấp của số bước dịch: `40` được xử lý tương đương `8`. Với `long`, khoảng dịch dùng sáu bit thấp; `1L << 40` mới là bit 40 đúng ý định.

Có thể dùng cả bit cao nhất của `int` (`1 << 31`) hay `long` (`1L << 63`) làm cờ, nhưng kết quả số học sẽ âm vì đây là các kiểu **có dấu**. Điều đó không ngăn chúng biểu diễn mặt nạ; chỉ cần tránh kiểm tra bằng `> 0` và ưu tiên `(flags & mask) != 0`. Đối với vị trí bit do người dùng cung cấp, kiểm tra giới hạn `0..31` cho `int` hoặc `0..63` cho `long` trước khi dịch.

### Vì sao phải phân biệt `>>` với `>>>`?

- `>>` dịch phải **giữ bit dấu**: khi số âm, các bit mới bên trái được điền bằng 1.
- `>>>` dịch phải **điền 0 bên trái**: phù hợp khi muốn trích giá trị bit không dấu, đặc biệt nếu trường nằm gần bit dấu.

Ví dụ:

```java
int high = 1 << 31;            // Integer.MIN_VALUE, bit 31 bằng 1
int arithmetic = high >> 31;  // -1
int logical = high >>> 31;    // 1
```

Trước khi trích một trường, tốt nhất áp dụng mặt nạ rồi dịch về bên phải theo đúng sơ đồ bit.

### Với `byte` phải chú ý mở rộng dấu

```java
byte b = (byte) 0b1111_0000;    // -16 dưới dạng byte có dấu
int promoted = b;               // -16, mở rộng dấu khi chuyển sang int
int eightBits = b & 0xFF;       // 240, lấy tám bit thấp theo cách nhìn không dấu
```

Không thể gán trực tiếp `byte b = 0b1111_0000;` vì literal `int` có giá trị 240, nằm ngoài miền `byte` (-128 đến 127). Nếu muốn giữ và xem tám bit như giá trị 0–255, dùng `b & 0xFF` hoặc `Byte.toUnsignedInt(b)`. Cả hai cách đều còn được sử dụng trong Java hiện đại.

## 7. Chọn bit mask hay cấu trúc dữ liệu khác?

Mặt nạ `int`/`long` rất phù hợp khi phải giữ tương thích với **định dạng số nguyên đã được quy định**, lưu cấu hình gọn, hoặc xử lý giao thức và các bit có vị trí xác định. Tuy nhiên, không phải tập tùy chọn nào cũng nên được biến thành cờ số nguyên.

**`EnumSet`** thường dễ bảo trì hơn khi các trạng thái là **một tập những giá trị enum có tên**:

```java
import java.util.EnumSet;

enum Permission { READ, WRITE, EXECUTE, ARCHIVE }

// Đoạn này nằm trong phương thức, sau khi enum đã được khai báo.
EnumSet<Permission> enabled = EnumSet.of(Permission.READ, Permission.WRITE);
enabled.add(Permission.EXECUTE);
boolean hasWrite = enabled.contains(Permission.WRITE); // true
enabled.remove(Permission.WRITE);
```

Lợi ích: trình biên dịch kiểm tra kiểu, IDE hỗ trợ tên enum, không cần tự cấp số bit hoặc viết phép AND/OR. Khi cần lưu ra giao thức có định dạng bit cụ thể, vẫn phải định nghĩa việc chuyển đổi giữa các giá trị enum và vị trí bit; không tự coi ordinal của enum là hợp đồng lưu trữ ổn định.

**`BitSet`** phù hợp khi số lượng vị trí bit thay đổi hoặc có thể lớn hơn 64:

```java
import java.util.BitSet;

BitSet enabled = new BitSet();
enabled.set(2);               // Bật bit 2
enabled.set(100);             // Bật bit 100
boolean bit100 = enabled.get(100); // true
enabled.clear(2);             // Tắt bit 2
enabled.flip(100);            // Đảo bit 100
```

`BitSet` có các phép giao/hợp `and`, `or`, `xor` và truy vấn `cardinality`, nhưng là đối tượng **có thể thay đổi**; nếu nhiều luồng cùng thay đổi, cần một cơ chế đồng bộ thích hợp. `EnumSet` cũng có thể thay đổi; không coi hai loại tập này là an toàn để sửa đồng thời mà không phối hợp.

**Quy tắc chọn:** sử dụng cờ nguyên khi cần thao tác bit và vị trí bit có ý nghĩa; sử dụng `EnumSet` khi tập trạng thái là những hằng enum nghiệp vụ; dùng `BitSet` khi cần nhiều chỉ số bit và thao tác tập hợp linh hoạt. Với trạng thái có thể loại trừ nhau như `DRAFT`/`PUBLISHED`/`ARCHIVED`, nên cân nhắc **một enum duy nhất**, thay vì ba cờ độc lập cho phép tổ hợp vô lý.

## 8. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Đặt hai cờ cùng giá trị `0b0010` | Không thể phân biệt hai cờ | Mỗi cờ đơn là một bit riêng: `1 << n` |
| Dùng `flags + mask` để bật cờ | Bật lặp có thể gây nhớ sang bit khác | Dùng `flags | mask` |
| Kiểm tra nhóm bằng `(flags & mask) != 0` nhưng yêu cầu **mọi** cờ | Chấp nhận nhầm trường hợp chỉ một cờ bật | So sánh `(flags & mask) == mask` |
| Viết `flags & mask == mask` không có ngoặc | Sai kiểu/cú pháp vì độ ưu tiên toán tử | Viết `(flags & mask) == mask` |
| Dùng XOR để bảo đảm bật cờ | Cờ đã bật bị tắt | Dùng OR `|=` |
| Dùng `1 << 40` để tạo cờ ở bit 40 | `int` chỉ dùng năm bit thấp của bước dịch | Dùng `1L << 40`, kiểm tra vị trí |
| Dùng `> 0` để phát hiện cờ ở bit dấu | Mặt nạ có thể là số âm | Dùng `(flags & mask) != 0` |
| Ghi trường nhiều bit bằng OR mà không xóa giá trị cũ | Bit cũ có thể giữ nguyên và làm sai kết quả | Xóa vùng bằng `& ~mask` rồi mới OR giá trị mới |
| Dùng `Integer.toBinaryString` để kiểm tra đúng số chữ số mà không đệm | Chuỗi thường thiếu số 0 đầu | Tự đệm khi trình bày hoặc dùng định dạng cố định |
| Nhiều luồng cùng `flags |= MASK` trên một biến chia sẻ | Thao tác đọc–sửa–ghi có thể mất cập nhật | Đồng bộ hoặc dùng `AtomicInteger.getAndUpdate(current -> current | MASK)` |

Ở dòng cuối, toán tử bit vẫn đúng nhưng `flags |= MASK` **không phải một thao tác nguyên tử** khi nhiều luồng cùng sửa biến. Việc dùng `volatile` đơn độc cũng không biến phép đọc–sửa–ghi thành nguyên tử.

Đối với dữ liệu từ mạng/tệp, còn cần quy định **thứ tự byte** (byte order), **vị trí bit** và **độ rộng số**. Mặt nạ Java mô tả cách xử lý một giá trị số học; cách các byte được truyền hoặc lưu phải được thống nhất riêng giữa các bên.

## 9. Bài tập thực hành và đáp án

**Bài 1.** Với `READ=0b0001`, `WRITE=0b0010`, `EXECUTE=0b0100`, giá trị `READ | EXECUTE` bằng bao nhiêu? Biểu thức `(flags & (READ | WRITE)) == (READ | WRITE)` với `flags` đó là đúng hay sai?

**Bài 2.** Ban đầu `flags = 0b1110`. Hãy viết biểu thức **bật** `READ` và **tắt** `EXECUTE`, rồi tính kết quả.

**Bài 3.** Một trường `priority` hai bit nằm tại bit 6–7 của số nguyên. Viết mặt nạ, cách ghi giá trị 3 sau khi xóa giá trị cũ, và cách đọc lại.

**Bài 4.** Tại sao `1 << 32` không tạo cờ mới ở bit 32? Cần dùng biểu thức nào?

**Đáp án và giải thích:**

1. `READ | EXECUTE = 0b0101 = 5`. Kiểm tra *cả READ và WRITE* trả `false` vì `WRITE` (bit 1) bằng 0.
2. `flags |= READ;` tạo `0b1111`; tiếp theo `flags &= ~EXECUTE;` tạo `0b1011` (11). Mọi bit khác vẫn nguyên.
3. `int mask = 0b1100_0000;`, `int shift = 6;`, `word = (word & ~mask) | ((3 << shift) & mask);`, `int priority = (word & mask) >>> shift;`, kết quả `priority = 3`. Trước khi ghi, kiểm tra giá trị 0–3.
4. Phép dịch `int` chỉ dùng năm bit thấp của lượng dịch nên `1 << 32` bằng `1 << 0`. Để biểu diễn bit 32, dùng `1L << 32`.

**Điểm cần nhớ:** Một cờ độc lập tương ứng một bit khác biệt; `|` dùng để gộp/bật, `&` để chọn/kiểm tra, `& ~` để xóa, `^` để đảo, còn `<<`/`>>>` hỗ trợ đặt và trích vị trí bit. Khi tạo nhiều trường bit, cần quy định mặt nạ không chồng lấn, kiểm tra độ rộng kiểu và miền giá trị; chỉ dùng các cú pháp và API vẫn được Java hiện đại hỗ trợ.