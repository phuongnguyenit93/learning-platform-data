# Dịch trái `<<` trong Java 17+

Toán tử **dịch trái** (*left shift*) `a << n` dịch các bit của `a` sang trái một số vị trí, bổ sung **bit 0 ở bên phải** và **loại bỏ các bit tràn ra ngoài độ rộng kiểu**.

~~~java
int value = 3;             // 0000...0011
int shifted = value << 2;  // 0000...1100 = 12
~~~

Với số nguyên nhỏ, không bị tràn, `a << n` thường cho giá trị bằng `a * 2^n`. Nhưng **đây không phải phép nhân có kiểm tra tràn**: khi dịch mất bit cao hoặc làm đổi bit dấu, kết quả có thể âm, bằng 0 hoặc khác kỳ vọng toán học.

**Trọng tâm bài:** hiểu *bit được dịch*, *kiểu dữ liệu của kết quả*, *độ rộng 32/64 bit*, *khoảng dịch bị giới hạn*, và *tràn số*.

## 1. Dịch trái một bit diễn ra thế nào?

Ví dụ minh họa trên **8 bit thấp** (chỉ để dễ nhìn):

~~~text
Trước:  0000 0101   (5)
                << 1
Sau:    0000 1010   (10)
                << 2 từ giá trị 5
Sau:    0001 0100   (20)
~~~

Mỗi bit dịch `n` vị trí sang bên trái, các vị trí thấp mới được điền bằng `0`. Bit vượt qua mép trái **bị mất**.

Trong Java, toán hạng thực sự dùng cho phép dịch là **`int` 32 bit hoặc `long` 64 bit**, sau khi áp dụng *unary numeric promotion*. Không có phép dịch thực thi trực tiếp trên thanh ghi 8 bit `byte` chỉ vì biến nguồn là `byte`.

| Biểu thức | Kết quả `int` | Mẫu bit thấp minh họa |
| --- | ---: | --- |
| `3 << 2` | 12 | `0000 0011 → 0000 1100` |
| `5 << 1` | 10 | `0000 0101 → 0000 1010` |
| `-3 << 1` | −6 | `1111 1101 → 1111 1010` (8 bit thấp) |
| `0 << 12` | 0 | Tất cả bit đều bằng 0 |
| `1 << 0` | 1 | Không dịch |

Với một số âm, giá trị được biểu diễn theo **bù hai**. `-3 << 1` cho `-6` vì mẫu bù hai khi dịch trái một bit còn mang đúng giá trị đó. Đừng hiểu dấu `<<` là so sánh “nhỏ hơn hai lần”: nó là **một toán tử dịch bit**.

## 2. Chương trình Java 17+ chạy độc lập

Tạo file UTF-8 **`LeftShiftDemo.java`**:

~~~java
import java.math.BigInteger;

public class LeftShiftDemo {
    static String typeOf(int unused) {
        return "int";
    }

    static String typeOf(long unused) {
        return "long";
    }

    static String bits8(int value) {
        String s = Integer.toBinaryString(value & 0xFF);
        return "0".repeat(8 - s.length()) + s;
    }

    static String bits32(int value) {
        String s = Integer.toBinaryString(value);
        return "0".repeat(32 - s.length()) + s;
    }

    public static void main(String[] args) {
        System.out.println("== basic shifts ==");
        System.out.println("threeShiftTwo=" + (3 << 2));
        System.out.println("fiveShiftOne=" + (5 << 1));
        System.out.println("negativeShift=" + (-3 << 1));
        System.out.println("zeroShift=" + (0 << 12));
        System.out.println("oneShiftZero=" + (1 << 0));
        System.out.println("fiveBits8=" + bits8(5));
        System.out.println("tenBits8=" + bits8(5 << 1));
        System.out.println("negativeBits8=" + bits8(-3));
        System.out.println("negativeShiftBits8=" + bits8(-3 << 1));

        System.out.println("== promoted types ==");
        byte small = 3;
        short medium = 6;
        char letter = 'A';
        long large = 3L;
        System.out.println("byteResultType=" + typeOf(small << 2));
        System.out.println("byteShiftValue=" + (small << 2));
        System.out.println("shortResultType=" + typeOf(medium << 1));
        System.out.println("charShift=" + (letter << 1));
        System.out.println("longResultType=" + typeOf(large << 2));

        System.out.println("== shift distances ==");
        long distance = 33L;
        System.out.println("intByLongCount=" + (1 << distance));
        System.out.println("intBy32=" + (1 << 32));
        System.out.println("intBy33=" + (1 << 33));
        System.out.println("intByMinusOne=" + (1 << -1));
        System.out.println("longBy64=" + (1L << 64));
        System.out.println("longBy65=" + (1L << 65));

        System.out.println("== sign and overflow ==");
        System.out.println("intSignBit=" + (1 << 31));
        System.out.println("intSignBitPattern=" + bits32(1 << 31));
        System.out.println("longSignBit=" + (1L << 63));
        System.out.println("highBitShiftOne=" + (0x40000000 << 1));
        System.out.println("highBitShiftTwo=" + (0x40000000 << 2));
        System.out.println("maxIntShiftOne=" + (Integer.MAX_VALUE << 1));
        System.out.println("minIntShiftOne=" + (Integer.MIN_VALUE << 1));
        System.out.println("widenBeforeShift="
                + ((long) Integer.MAX_VALUE << 1));
        System.out.println("widenAfterShift="
                + ((long) (Integer.MAX_VALUE << 1)));

        byte narrow = 100;
        narrow <<= 1;
        System.out.println("compoundByte=" + narrow);
        System.out.println("compoundByteBits=" + bits8(narrow));

        System.out.println("== bit masks ==");
        int read = 1 << 0;
        int write = 1 << 1;
        int execute = 1 << 2;
        int permissions = read | execute;
        System.out.println("readAllowed=" + ((permissions & read) != 0));
        System.out.println("writeAllowed=" + ((permissions & write) != 0));
        System.out.println("executeAllowed=" + ((permissions & execute) != 0));
        System.out.println("groupedExpression=" + (1 << (2 + 1)));

        System.out.println("== big integers ==");
        System.out.println("bigShift="
                + BigInteger.ONE.shiftLeft(40));
    }
}
~~~

Mở PowerShell (Windows) hoặc Bash (Linux/macOS) trong thư mục chứa file; dùng **JDK 17 trở lên**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 LeftShiftDemo.java
java LeftShiftDemo
~~~

**Exact expected stdout** của riêng lệnh `java LeftShiftDemo`:

~~~text
== basic shifts ==
threeShiftTwo=12
fiveShiftOne=10
negativeShift=-6
zeroShift=0
oneShiftZero=1
fiveBits8=00000101
tenBits8=00001010
negativeBits8=11111101
negativeShiftBits8=11111010
== promoted types ==
byteResultType=int
byteShiftValue=12
shortResultType=int
charShift=130
longResultType=long
== shift distances ==
intByLongCount=2
intBy32=1
intBy33=2
intByMinusOne=-2147483648
longBy64=1
longBy65=2
== sign and overflow ==
intSignBit=-2147483648
intSignBitPattern=10000000000000000000000000000000
longSignBit=-9223372036854775808
highBitShiftOne=-2147483648
highBitShiftTwo=0
maxIntShiftOne=-2
minIntShiftOne=0
widenBeforeShift=4294967294
widenAfterShift=-2
compoundByte=-56
compoundByteBits=11001000
== bit masks ==
readAllowed=true
writeAllowed=false
executeAllowed=true
groupedExpression=8
== big integers ==
bigShift=1099511627776
~~~

Hai lệnh `-version` không có expected output cố định vì phụ thuộc bản JDK cài đặt. Chương trình không cần thư viện bên thứ ba.

## 3. Kiểu kết quả: `int` hoặc `long`, không nhất thiết là kiểu biến gốc

Java áp dụng **unary numeric promotion** cho từng toán hạng trước khi dịch:

- Toán hạng trái `byte`, `short`, `char` được nâng thành `int`; kết quả `<<` có kiểu **`int`**.
- Toán hạng trái `int` cho kết quả **`int`**; `long` cho kết quả **`long`**.
- Toán hạng phải cung cấp **khoảng cách dịch**, không quyết định kiểu kết quả. Nó cũng có thể là `long`.
- Không có phép `<<` trực tiếp cho `float`, `double`, `boolean` hay `String`.

~~~java
byte b = 3;
int x = b << 2; // 12, kiểu int.
// byte invalid = b << 2; // Lỗi: không tự gán int vào byte.

long y = 3L << 2; // 12L, kiểu long.
int z = 1 << 33L; // 2, không phải long.
~~~

Không áp dụng **binary numeric promotion** giống phép cộng số học để suy ra kiểu của toán tử dịch. Ví dụ `1 << 33L` vẫn trả `int`, vì kiểu toán hạng **trái** là `int`.

### `<<=` và phép chuyển kiểu về biến vế trái

Gán kết hợp `x <<= n` thực hiện dịch trái rồi gán lại kết quả về kiểu của `x`, có thể **thu hẹp** giá trị:

~~~java
byte value = 100;
value <<= 1; // Hợp lệ, kết quả byte là -56.
~~~

Phép dịch tạo kết quả `int 200`, sau đó gán về `byte` theo quy tắc compound assignment. `byte` có miền -128..127, nên mẫu bit thấp `11001000` được diễn giải thành **-56**.

Ngược lại, `value = value << 1;` không biên dịch nếu thiếu cast tường minh, vì biểu thức dịch có kiểu `int`.

## 4. Khoảng cách dịch phụ thuộc kiểu toán hạng trái

Java chỉ lấy **5 bit thấp** (`n & 31`) của khoảng dịch khi bên trái là `int`, và **6 bit thấp** (`n & 63`) khi bên trái là `long`. Các toán hạng hẹp `byte`/`short`/`char` được nâng thành `int` trước khi áp dụng quy tắc này.

~~~java
System.out.println(1 << 32);   // 1, vì khoảng dịch hiệu lực là 0.
System.out.println(1 << 33);   // 2, vì khoảng dịch hiệu lực là 1.
System.out.println(1L << 64);  // 1, vì khoảng dịch hiệu lực là 0.
System.out.println(1 << -1);   // -2147483648, vì -1 & 31 là 31.
~~~

Khoảng dịch âm hoặc vượt độ rộng vẫn được mask, không tự báo lỗi. Nếu `n` đến từ đầu vào và nghiệp vụ chỉ cho phép vị trí bit 0–31 hoặc 0–63, phải kiểm tra miền trước khi dịch. Bài riêng về giới hạn khoảng dịch sẽ đi sâu vào phép mask, kiểu bên trái và việc cast trước hay sau khi dịch.

## 5. Bit dấu và tràn số: `<<` không luôn là nhân đôi an toàn

`int` có 32 bit, `long` có 64 bit và đều là số nguyên **bù hai**. Khi `<<` đẩy bit 1 vào vị trí dấu hoặc làm rơi bit cao, giá trị có dấu có thể thay đổi bất ngờ:

~~~java
System.out.println(1 << 31); // Integer.MIN_VALUE = -2147483648.
System.out.println(1L << 63); // Long.MIN_VALUE.
System.out.println(0x40000000 << 1); // -2147483648.
System.out.println(0x40000000 << 2); // 0: bit cao đã bị loại.
~~~

Giải thích `1 << 31`:

~~~text
int 1:
00000000000000000000000000000001

Dịch trái 31:
10000000000000000000000000000000
^
Bit cao nhất = 1; diễn giải theo int có dấu là -2147483648.
~~~

Khi kết quả toán học vừa trong miền kiểu và không mất bit có nghĩa, dịch trái `n` vị trí phù hợp với nhân `2^n`. Nhưng với `int`, giá trị vượt miền bị **cắt về 32 bit thấp**; với `long` bị cắt về 64 bit thấp. `<<` **không ném `ArithmeticException` khi tràn**.

Ví dụ:

~~~java
int x = Integer.MAX_VALUE;
System.out.println(x << 1); // -2, không phải 4294967294.
~~~

Nếu cần phép nhân có kiểm tra tràn số, sử dụng `Math.multiplyExact` với toán hạng/kiểu phù hợp; nếu cần kết quả lớn hơn `int`, nâng kiểu **trước** khi dịch:

~~~java
int x = Integer.MAX_VALUE;
long correct = ((long) x) << 1; // 4294967294.
long tooLate = (long) (x << 1); // -2: int đã tràn trước cast.
~~~

`BigInteger.ONE.shiftLeft(40)` là một lựa chọn khi cần số nguyên rất lớn, không bị giới hạn trong 32 hoặc 64 bit (nhưng vẫn phụ thuộc tài nguyên máy).

## 6. Ứng dụng: tạo mặt nạ bit (*bit mask*)

`1 << k` đặt bit thứ `k` (đánh số từ 0, phải sang trái) thành 1; hữu ích cho các cờ trạng thái:

~~~java
int READ = 1 << 0;       // 001.
int WRITE = 1 << 1;      // 010.
int EXECUTE = 1 << 2;    // 100.

int flags = READ | EXECUTE; // 101.
boolean canRead = (flags & READ) != 0;   // true.
boolean canWrite = (flags & WRITE) != 0; // false.
~~~

Toán tử `|` kết hợp các cờ, `&` kiểm tra bit. `<<` tạo đúng vị trí bit cần dùng.

**Giới hạn:** với `int`, bit thứ 31 chính là bit dấu (`1 << 31` âm); với `long`, bit thứ 63 là bit dấu. Điều này vẫn hợp lệ với **mẫu bit** và phép `&`, nhưng dễ sai nếu đem mặt nạ đi so bằng `> 0`: giá trị âm có bit được bật vẫn có thể là mặt nạ hợp lệ. Thường hãy kiểm tra `(flags & mask) != 0`.

Nếu `k` đến từ đầu vào, xác minh `0 <= k && k < 32` khi dùng `int` hoặc `0 <= k && k < 64` khi dùng `long`, bởi Java **mask** khoảng cách dịch thay vì tự báo lỗi.

## 7. Độ ưu tiên, dấu ngoặc và so sánh với dịch phải

Toán tử `<<` có độ ưu tiên **thấp hơn `+`, `-`** nhưng **cao hơn các phép so sánh quan hệ** như `<` hoặc `>=`.

~~~java
int a = 1 << 2 + 1;     // 1 << (2 + 1) = 8.
int b = (1 << 2) + 1;   // 4 + 1 = 5.
boolean check = (1 << 3) > 5; // true.
~~~

Dùng dấu ngoặc rõ ràng trong mã cần nhiều phép toán, nhất là với các mặt nạ bit.

| Toán tử | Hướng dịch | Các bit mới được chèn |
| --- | --- | --- |
| `x << n` | Sang trái | Điền 0 ở phía phải |
| `x >> n` | Sang phải, giữ dấu | Điền bit dấu ở phía trái |
| `x >>> n` | Sang phải, không giữ dấu | Điền 0 ở phía trái |

`<<` không có biến thể riêng “dịch trái không dấu” `<<<`. Cả số âm và số dương đều được dịch trái bằng cùng quy tắc bit. Việc đọc kết quả theo dấu là do **kiểu `int` hoặc `long`**, không phải do toán tử tự chọn “dịch trái có dấu” hay “không dấu”.

## 8. Lỗi phổ biến cần tránh

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “`x << 1` lúc nào cũng giống `x * 2` theo giá trị toán học.” | Có thể tràn và mất bit |
| “`byte b; b << 1` cho kết quả `byte`.” | Kết quả có kiểu `int` sau promotion |
| “`1 << 32` cho 0 vì dịch hết 32 bit.” | Kết quả là **1** vì khoảng dịch mask |
| “`1L << 64` cho 0.” | Kết quả là **1** vì khoảng dịch mask theo 64 |
| “Khoảng dịch âm ném exception.” | Các bit thấp của khoảng dịch vẫn được dùng |
| “`1 << 31` là số dương `2147483648`.” | Trả `Integer.MIN_VALUE` (âm) |
| “Cast sang `long` sau khi dịch sẽ sửa tràn `int`.” | Phải cast **trước** khi dịch |
| “`byteValue <<= 1` và `byteValue = byteValue << 1` cùng hợp lệ.” | Dạng thứ hai cần cast |
| “`<<` ném ngoại lệ nếu bit dấu thay đổi.” | Không; tràn bị cắt theo độ rộng |
| “`1 << k` có thể dùng tùy ý với `k > 31` để cấp thêm bit.” | Không; dùng `1L`/`BigInteger` theo miền yêu cầu |

## 9. Bài tập tự kiểm tra

1. `3 << 2` bằng bao nhiêu?  
   *Đáp án:* **12** (`3 × 4`), không bị tràn.
2. `-3 << 1` cho bao nhiêu?  
   *Đáp án:* **-6** theo bù hai `int`.
3. Kiểu của `byte b = 3; var x = b << 2;` là gì?  
   *Đáp án:* `int`.
4. `1 << 32`, `1 << 33` và `1 << -1` lần lượt là gì?  
   *Đáp án:* **1**, **2**, **-2147483648**.
5. `1L << 64` và `1L << 65` bằng bao nhiêu?  
   *Đáp án:* **1L**, **2L**.
6. Tại sao `0x40000000 << 2` bằng 0?  
   *Đáp án:* Bit 1 cao bị dịch vượt khỏi độ rộng 32 bit.
7. `int x = Integer.MAX_VALUE; long y = (long) (x << 1);` — `y` bằng bao nhiêu?  
   *Đáp án:* **-2** vì tràn xảy ra trước cast.
8. Muốn tạo bit thứ 40 của một `long`, viết gì?  
   *Đáp án:* `1L << 40` (không phải `1 << 40`).
9. Vì sao nên kiểm tra mặt nạ bằng `(flags & mask) != 0` thay vì `> 0`?  
   *Đáp án:* Mặt nạ có thể bật bit dấu, khiến kết quả là số âm nhưng bit vẫn tồn tại.

## Checklist

- [ ] Hiểu `<<` dịch bit sang trái, chèn 0 ở bên phải và bỏ bit tràn phía trái.
- [ ] Nhớ kết quả sau promotion có kiểu `int` hoặc `long` dựa vào toán hạng trái.
- [ ] Biết giới hạn khoảng dịch: `int` dùng 5 bit thấp, `long` dùng 6 bit thấp.
- [ ] Nhận diện việc bit dấu thay đổi và tràn số **không tự báo lỗi**.
- [ ] Nâng kiểu lên `long` **trước** khi dịch nếu cần miền rộng hơn `int`.
- [ ] Hiểu gán `<<=` có thể thu hẹp kết quả về kiểu biến gốc.
- [ ] Dùng `1 << k` hoặc `1L << k` làm mặt nạ bit và kiểm tra `k` theo miền yêu cầu.
- [ ] Dùng dấu ngoặc để làm rõ các biểu thức kết hợp dịch, cộng và so sánh.

**Kết luận:** `<<` là **toán tử dịch bit**, không phải phép nhân chính xác vô điều kiện. Hãy luôn kiểm tra **kiểu toán hạng trái**, **khoảng dịch hiệu dụng**, **bit có thể bị mất** và **bit dấu** trước khi suy luận kết quả của phép dịch.
