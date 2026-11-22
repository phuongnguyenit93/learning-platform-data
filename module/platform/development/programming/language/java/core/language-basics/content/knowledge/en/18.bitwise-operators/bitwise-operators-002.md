# AND, OR, XOR và NOT theo từng bit trong Java

> **Java core — language-basics / Toán tử bit**  
> **Môi trường:** JDK 17+; chỉ sử dụng thư viện chuẩn Java.  
> **Mục tiêu:** Hiểu `&`, `|`, `^` và `~` trên các bit của số nguyên; đọc bảng chân trị, thao tác bit mask, xử lý đúng số âm và quy tắc nâng kiểu.

## 1. Toán tử bit hoạt động như thế nào?

Mỗi số nguyên được lưu dưới dạng dãy bit 0/1. Các phép toán bit xử lý **từng vị trí bit tương ứng** của toán hạng:

| Toán tử | Tên | Quy tắc cho từng vị trí bit |
| --- | --- | --- |
| `&` | AND | Kết quả là 1 **chỉ khi cả hai bit đều là 1** |
| `\|` | OR | Kết quả là 1 khi **ít nhất một bit là 1** |
| `^` | XOR | Kết quả là 1 khi **hai bit khác nhau** |
| `~` | NOT (bù bit) | **Đảo từng bit:** 0 → 1; 1 → 0 |

Ví dụ với hai số `int`:

~~~java
int a = 0b1100; // 12
int b = 0b1010; // 10

int and = a & b; // 0b1000 = 8
int or  = a | b; // 0b1110 = 14
int xor = a ^ b; // 0b0110 = 6
~~~

`0b` là tiền tố literal nhị phân trong Java. Dấu gạch dưới có thể giúp đọc nhóm bit, chẳng hạn `0b1100_1010`.

## 2. Bảng chân trị AND, OR, XOR, NOT

Xem `A` và `B` là **một bit đơn lẻ**:

| A | B | A AND B | A OR B | A XOR B | NOT A |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 0 | 0 | 1 |
| 0 | 1 | 0 | 1 | 1 | 1 |
| 1 | 0 | 0 | 1 | 1 | 0 |
| 1 | 1 | 1 | 1 | 0 | 0 |

`NOT A` chỉ phụ thuộc vào `A`, không phụ thuộc `B`.

Có thể hình dung phép toán theo cột bit:

~~~text
   a  = 1100  (12)
   b  = 1010  (10)
a & b = 1000  ( 8)
a | b = 1110  (14)
a ^ b = 0110  ( 6)
~~~

Từ bảng chân trị suy ra:

- `x & 0` luôn bằng 0; `x | 0` bằng `x`.
- `x ^ 0` bằng `x`; `x ^ x` bằng 0.
- `x & x` và `x | x` đều bằng `x`.

Những tính chất này hữu ích để bật, tắt, đảo và kiểm tra cờ (*flags*).

## 3. `~` đảo **toàn bộ** bit, không chỉ những bit đang nhìn thấy

Với `int`, Java sử dụng **32 bit có dấu**. Vì vậy `~a` đảo **cả 32 bit**, không chỉ bốn bit `1100` được viết trong literal:

~~~java
int a = 0b1100; // 12
System.out.println(~a); // -13, không phải 3.
~~~

Số nguyên có dấu dùng biểu diễn **bù hai** (*two's complement*). Với `int`/`long`, ta có hệ thức:

~~~text
~n == -n - 1
~12 == -13
~~~

Nếu chỉ muốn xét bốn bit thấp, dùng **mask**:

~~~java
int lowFour = (~a) & 0b1111; // 0b0011 = 3.
~~~

Đây là khác biệt giữa `~a` (đảo mọi bit của một giá trị kiểu `int`) và `(~a) & 0b1111` (giữ **4 bit thấp** sau khi đảo).

`int` có độ rộng 32 bit, `long` 64 bit. `~` không áp dụng được lên `boolean`; phủ định logic boolean dùng `!`.

## 4. Ứng dụng ngắn: đọc, bật, tắt và đảo một bit

Một *bit mask* đặt bit 1 tại vị trí cần thao tác. Từ bảng chân trị của AND, OR và XOR, có bốn quy tắc đủ để thử trên số nguyên:

```java
int flags = 0b0101;             // Bit 0 và bit 2 đang bật.
int mask = 0b0010;              // Chọn bit 1.
boolean hasBit = (flags & mask) != 0; // false.
int set = flags | mask;         // 0b0111, bật bit 1.
int cleared = flags & ~0b0100; // 0b0001, tắt bit 2.
int toggled = flags ^ 0b0001;  // 0b0100, đảo bit 0.
```

**AND lọc bit**, **OR bật bit**, **AND với NOT tắt bit**, **XOR đảo bit**. Hai phép `flags & mask` và `flags | mask` đều có kết quả là **số nguyên**, không phải `boolean`: muốn kiểm tra trong `if`, so sánh `(flags & mask) != 0` (ít nhất một bit bật) hoặc `(flags & mask) == mask` (mọi bit trong mask đều bật).

Đây chỉ là **ứng dụng trực tiếp của bảng chân trị**. Khi quản lý nhiều cờ thực tế, còn phải xem mask có bằng 0 không, cờ có nằm trong miền hợp lệ không, cách kiểm tra *any/all* và vấn đề đồng bộ; các thao tác này không được suy ra là một hệ thống phân quyền an toàn chỉ từ phép toán bit.

## 5. Kiểu dữ liệu và nâng kiểu số nguyên

Toán tử bit dành cho các kiểu **nguyên** (`byte`, `short`, `char`, `int`, `long`). Khi dùng `&`, `|`, `^` với số nguyên, Java áp dụng *binary numeric promotion*:

- Các toán hạng `byte`, `short` và `char` được nâng lên ít nhất `int`.
- Nếu một toán hạng có kiểu `long` thì phép toán số nguyên thực hiện ở kiểu `long`.
- `~` với `byte`, `short`, `char` cũng cho kết quả kiểu `int` sau khi nâng kiểu.
- `float` và `double` không được dùng với các phép toán bit này.

~~~java
byte small = 0b0000_1111; // 15
int inverse = ~small;    // -16 (int), không phải byte.
int lowEight = inverse & 0xFF; // 240: giữ 8 bit thấp.

// byte invalid = ~small; // Lỗi biên dịch: int không tự gán sang byte.
~~~

Với byte âm, Java chuyển sang `int` có mở rộng dấu trước khi thực hiện nhiều phép toán. Khi muốn biểu diễn một byte như số **không dấu trong miền 0..255**, dùng `value & 0xFF` hoặc `Byte.toUnsignedInt(value)`.

Ví dụ `long`:

~~~java
long bits = 0x1_0000_0005L;
long mask = 0x1_0000_0000L;
long highFlag = bits & mask; // 4294967296.
~~~

Hằng `L` và kiểu `long` rất quan trọng khi cờ nằm ở vị trí bit cao vượt miền `int`.

## 6. Đừng nhầm toán tử bit với toán tử logic

Trên `boolean`, Java cũng cho phép `&`, `|`, `^` nhưng chúng thực hiện **phép logic boolean**, không phải thao tác bit trên số:

~~~java
boolean a = true;
boolean b = false;
boolean both = a & b;  // false.
boolean either = a | b; // true.
boolean one = a ^ b;    // true.
boolean not = !a;      // false.
~~~

| Toán tử | Với số nguyên | Với boolean |
| --- | --- | --- |
| `&`, `\|`, `^` | AND/OR/XOR theo từng bit | AND/OR/XOR logic, **đánh giá cả hai vế** |
| `~` | Đảo bit của số nguyên | **Không hợp lệ** |
| `!` | **Không hợp lệ** | Phủ định logic |
| `&&`, `\|\|` | **Không hợp lệ** | AND/OR logic **ngắn mạch** |

Khác biệt quan trọng: `false & check()` **vẫn gọi** `check()`; `false && check()` **bỏ qua** lời gọi. Tương tự, `true | check()` vẫn gọi `check()`, còn `true || check()` không gọi.

Độ ưu tiên của các toán tử bit nhị phân là **`&` cao hơn `^`, cao hơn `|`**. Nên viết ngoặc khi trộn nhiều toán tử, đặc biệt các biểu thức mask có phép so sánh.

## 7. Ví dụ Java 17+ chạy độc lập

Tạo file **BitwiseOperatorsDemo.java**:

~~~java
public final class BitwiseOperatorsDemo {
    private static String bits4(int value) {
        String raw = Integer.toBinaryString(value & 0b1111);
        return "0".repeat(4 - raw.length()) + raw;
    }

    public static void main(String[] args) {
        int a = 0b1100; // 12
        int b = 0b1010; // 10

        System.out.println("a=" + bits4(a) + ",b=" + bits4(b));
        System.out.println("and=" + (a & b)
                + ",bits=" + bits4(a & b));
        System.out.println("or=" + (a | b)
                + ",bits=" + bits4(a | b));
        System.out.println("xor=" + (a ^ b)
                + ",bits=" + bits4(a ^ b));
        System.out.println("not=" + (~a)
                + ",low4=" + bits4(~a));
        System.out.println("notMasked=" + ((~a) & 0b1111));

        int flags = 0b0101;
        int mask = 0b0010;
        System.out.println("flags=" + bits4(flags));
        System.out.println("set=" + bits4(flags | mask));
        System.out.println("clear=" + bits4(flags & ~0b0100));
        System.out.println("toggle=" + bits4(flags ^ 0b0001));
        System.out.println("hasBit2=" + ((flags & 0b0100) != 0));
        System.out.println("allSelected=" + ((flags & 0b0101) == 0b0101));

        byte small = 0b0000_1111;
        int inverted = ~small;
        System.out.println("byteNot=" + inverted
                + ",low8=" + (inverted & 0xFF));

        long big = 0x1_0000_0005L;
        long highMask = 0x1_0000_0000L;
        System.out.println("longMask=" + (big & highMask));

        boolean yes = true, no = false;
        System.out.println("booleanAnd=" + (yes & no)
                + ",booleanOr=" + (yes | no)
                + ",booleanXor=" + (yes ^ no));
    }
}
~~~

Chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 BitwiseOperatorsDemo.java
java BitwiseOperatorsDemo
~~~

**Expected stdout chính xác:**

~~~text
a=1100,b=1010
and=8,bits=1000
or=14,bits=1110
xor=6,bits=0110
not=-13,low4=0011
notMasked=3
flags=0101
set=0111
clear=0001
toggle=0100
hasBit2=true
allSelected=true
byteNot=-16,low8=240
longMask=4294967296
booleanAnd=false,booleanOr=true,booleanXor=true
~~~

`not=-13` do `~` đảo đủ 32 bit của `int`; `low4=0011` chỉ hiển thị bốn bit thấp. `byteNot=-16` vì `byte` được nâng thành `int`; `low8=240` là tám bit thấp. Kết quả mask cho thấy cách thao tác từng cờ mà không làm thay đổi những bit không được chọn.

## 8. Lỗi thường gặp và bài tập

| Nhầm lẫn | Kết luận đúng |
| --- | --- |
| Nghĩ `~0b1100` chỉ ra `0b0011` | `~` đảo **toàn bộ 32 bit `int`**; mask mới giữ bốn bit thấp |
| Dùng `if (flags & mask)` | Java yêu cầu boolean; viết `if ((flags & mask) != 0)` |
| Dùng `~true` hoặc `!12` | `~` chỉ dùng với số nguyên, `!` dùng với boolean |
| Cho rằng `&`/`\|` trên boolean short-circuit | Không: cả hai vế đều được đánh giá |
| Gán `~byteValue` thẳng vào `byte` | Kết quả được nâng thành `int` |
| Nghĩ XOR giống OR | XOR bằng 0 khi cả hai bit đều 1 |

**Bài 1.** Tính `0b0110 & 0b1010`, `0b0110 | 0b1010` và `0b0110 ^ 0b1010`. Viết kết quả thành bốn bit.

**Bài 2.** Cho `int flags = 0b0011;`. Viết lệnh bật bit thứ ba (đếm bit thấp nhất là bit 0), tắt bit 0 và đảo bit 1.

**Bài 3.** Giải thích vì sao `~12 == -13` trong Java, còn `(~12) & 0b1111 == 3`.

**Bài 4.** Cho `byte b = 15;`. Dự đoán kiểu và giá trị của `~b`. Muốn xem tám bit thấp dưới dạng số 0..255, nên dùng phép mask nào?

**Bài 5.** So sánh `false & check()` với `false && check()` nếu `check()` tăng bộ đếm hoặc có thể ném ngoại lệ.

### Ghi nhớ

**`&` (AND), `|` (OR), `^` (XOR) kết hợp các bit; `~` (NOT) đảo mọi bit của kiểu số nguyên.** Với `int`/`long` có dấu, `~n = -n - 1`; muốn xét một số bit nhất định thì dùng mask. Với `byte`/`short`/`char`, chú ý phép nâng kiểu lên `int`. Dùng mask và ngoặc rõ ràng, phân biệt toán tử bit với logic boolean ngắn mạch.
