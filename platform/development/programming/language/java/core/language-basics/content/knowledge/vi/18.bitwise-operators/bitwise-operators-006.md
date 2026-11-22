# Numeric promotion khi thao tác trên `byte`, `short` hoặc `char` — Java 17+

Trong Java, nhiều toán tử số học và bit **không tính trực tiếp trên độ rộng 8 bit hoặc 16 bit**, dù toán hạng là `byte`, `short` hay `char`. Trước khi tính, Java áp dụng **numeric promotion** (*nâng kiểu số*) và thường biến các toán hạng này thành **`int` 32 bit**.

~~~java
byte b = 5;
int shifted = b << 1; // 10, kiểu int.
int inverted = ~b;    // -6, kiểu int.
~~~

**Điểm cốt lõi:** Phân biệt ba bước:

1. **Nâng kiểu toán hạng** từ `byte`/`short`/`char` lên `int`.
2. **Tính toán** trên kiểu đã nâng, ví dụ AND bit, XOR bit hoặc dịch bit.
3. **Chuyển kiểu khi gán kết quả** (nếu biến đích là kiểu hẹp): có thể cần cast, hoặc `op=` sẽ thu hẹp ngầm.

Không suy luận rằng kết quả `b << 1` hay `~b` có kiểu `byte` chỉ vì biến `b` là `byte`.

## 1. Bảng tổng quan

| Kiểu nguồn | Độ rộng | Miền giá trị | Khi chuyển sang `int` |
| --- | ---: | --- | --- |
| `byte` | 8 bit | −128 đến 127 | **Mở rộng dấu** (*sign extension*) |
| `short` | 16 bit | −32.768 đến 32.767 | **Mở rộng dấu** |
| `char` | 16 bit | 0 đến 65.535 | **Mở rộng với bit 0** (*zero extension*) |

`char` là **đơn vị mã UTF-16 không dấu**, không phải kiểu “ký tự có dấu”. Ví dụ `char c = (char) 0xFFFF;` khi chuyển sang `int` cho **65535**, trong khi `short s = -1;` cho **-1**, mặc dù cả hai đều có 16 bit 1 ở độ rộng ban đầu.

### Những toán tử liên quan

| Toán tử | Quy tắc nâng kiểu | Kiểu kết quả |
| --- | --- | --- |
| `+x`, `-x`, `~x` | **Unary numeric promotion** | `int` nếu `x` là `byte`/`short`/`char` |
| `x << n`, `x >> n`, `x >>> n` | **Unary numeric promotion riêng cho hai toán hạng** | Kiểu của toán hạng **trái sau nâng kiểu** |
| `x & y`, `x \| y`, `x ^ y` khi là phép **bit trên số nguyên** | **Binary numeric promotion** | Thường là `int`; thành `long` nếu có toán hạng `long` |
| `x + y`, `x - y`, `x * y` | **Binary numeric promotion** | Thường là `int` với các kiểu nhỏ |
| `x &= y`, `x <<= n` (gán kết hợp) | Tính theo kiểu được nâng, sau đó **chuyển về kiểu của x** | Kiểu của biến bên trái |

Cùng ký hiệu `&`, `|`, `^` còn có nghĩa logic khi cả hai toán hạng là `boolean`. Bài này xét **trường hợp số nguyên**, không phải phép toán boolean.

## 2. Demo Java 17+ tự chứa, chạy bằng CLI

Tạo file UTF-8 **`BitPromotionDemo.java`**:

~~~java
public class BitPromotionDemo {
    static String kind(int unused) {
        return "int";
    }

    static String kind(long unused) {
        return "long";
    }

    static String bits8(int value) {
        String bits = Integer.toBinaryString(value & 0xFF);
        return "0".repeat(8 - bits.length()) + bits;
    }

    static String bits16(int value) {
        String bits = Integer.toBinaryString(value & 0xFFFF);
        return "0".repeat(16 - bits.length()) + bits;
    }

    public static void main(String[] args) {
        byte b = 5;
        short s = 9;
        char c = 'A';

        System.out.println("== int promotion ==");
        System.out.println("byteShiftType=" + kind(b << 1));
        System.out.println("byteShift=" + (b << 1));
        System.out.println("shortShiftType=" + kind(s << 2));
        System.out.println("shortShift=" + (s << 2));
        System.out.println("charShiftType=" + kind(c << 1));
        System.out.println("charShift=" + (c << 1));
        System.out.println("byteAndShortType=" + kind(b & s));
        System.out.println("byteAndShort=" + (b & s));
        System.out.println("charXorByteType=" + kind(c ^ b));
        System.out.println("charXorByte=" + (c ^ b));
        System.out.println("plusByteType=" + kind(+b));
        System.out.println("minusByte=" + (-b));
        System.out.println("notByte=" + (~b));
        System.out.println("notChar=" + (~c));

        System.out.println("== sign vs zero extension ==");
        byte signedByte = -1;
        short signedShort = -2;
        char unsignedChar = (char) 0xFFFF;
        System.out.println("byteAsInt=" + (int) signedByte);
        System.out.println("byteHex="
                + Integer.toHexString(signedByte));
        System.out.println("byteBits8=" + bits8(signedByte));
        System.out.println("unsignedByte=" + (signedByte & 0xFF));
        System.out.println("shortAsInt=" + (int) signedShort);
        System.out.println("shortBits16=" + bits16(signedShort));
        System.out.println("unsignedShort="
                + Short.toUnsignedInt(signedShort));
        System.out.println("charAsInt=" + (int) unsignedChar);
        System.out.println("charRight15=" + (unsignedChar >> 15));
        System.out.println("shortRight15=" + (signedShort >> 15));
        System.out.println("charShiftLeft=" + (unsignedChar << 1));

        System.out.println("== shift semantics ==");
        System.out.println("byteLogicalRight="
                + (signedByte >>> 1));
        System.out.println("shortArithmeticRight="
                + (signedShort >> 1));
        long distance = 33L;
        System.out.println("byteLongDistanceType="
                + kind(b << distance));
        System.out.println("byteLongDistance="
                + (b << distance));
        System.out.println("intShiftToSignBit="
                + (b << 31));

        System.out.println("== compound assignments ==");
        byte narrow = 100;
        int promoted = narrow << 1;
        narrow <<= 1;
        System.out.println("promotedValue=" + promoted);
        System.out.println("compoundByteValue=" + narrow);
        System.out.println("compoundByteBits=" + bits8(narrow));

        byte masked = -1;
        masked &= 0x0F;
        System.out.println("compoundAndByte=" + masked);

        char movedChar = 'A';
        movedChar <<= 1;
        System.out.println("compoundCharCode=" + (int) movedChar);

        short medium = 30_000;
        int promotedShort = medium << 1;
        medium <<= 1;
        System.out.println("promotedShort=" + promotedShort);
        System.out.println("compoundShort=" + medium);

        System.out.println("== long promotion and wrappers ==");
        System.out.println("byteAndLongType="
                + kind(signedByte & 0xFFL));
        System.out.println("byteAndLongValue="
                + (signedByte & 0xFFL));

        Byte boxed = null;
        try {
            int unused = boxed & 0xFF;
            System.out.println("unexpected=" + unused);
        } catch (NullPointerException ex) {
            System.out.println("boxedNull=NullPointerException");
        }
    }
}
~~~

Dùng **JDK 17+**, mở PowerShell hoặc Bash trong thư mục chứa file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 BitPromotionDemo.java
java BitPromotionDemo
~~~

**Expected stdout chính xác** của riêng lệnh `java BitPromotionDemo`:

~~~text
== int promotion ==
byteShiftType=int
byteShift=10
shortShiftType=int
shortShift=36
charShiftType=int
charShift=130
byteAndShortType=int
byteAndShort=1
charXorByteType=int
charXorByte=68
plusByteType=int
minusByte=-5
notByte=-6
notChar=-66
== sign vs zero extension ==
byteAsInt=-1
byteHex=ffffffff
byteBits8=11111111
unsignedByte=255
shortAsInt=-2
shortBits16=1111111111111110
unsignedShort=65534
charAsInt=65535
charRight15=1
shortRight15=-1
charShiftLeft=131070
== shift semantics ==
byteLogicalRight=2147483647
shortArithmeticRight=-1
byteLongDistanceType=int
byteLongDistance=10
intShiftToSignBit=-2147483648
== compound assignments ==
promotedValue=200
compoundByteValue=-56
compoundByteBits=11001000
compoundAndByte=15
compoundCharCode=130
promotedShort=60000
compoundShort=-5536
== long promotion and wrappers ==
byteAndLongType=long
byteAndLongValue=255
boxedNull=NullPointerException
~~~

Đầu ra của `java -version`, `javac -version` phụ thuộc môi trường và không thuộc khối stdout cố định. Chương trình sử dụng API Java chuẩn, không yêu cầu thư viện bên ngoài.

## 3. Unary numeric promotion trong các phép dịch và phép `~`

Với các toán tử dịch `<<`, `>>`, `>>>`, Java nâng **từng toán hạng** theo quy tắc *unary numeric promotion*. Một `byte`, `short` hoặc `char` ở bên trái trở thành `int`, nên kiểu kết quả là **`int`**.

~~~java
byte b = 5;
int result = b << 2; // 20, int.
// byte wrong = b << 2; // Lỗi: không thể gán int vào byte.
~~~

**Khoảng dịch được xác định theo kiểu toán hạng trái đã nâng:**

- Với `int`: chỉ dùng **5 bit thấp** của khoảng dịch (`n & 31`).
- Với `long`: chỉ dùng **6 bit thấp** (`n & 63`).

~~~java
byte b = 5;
long count = 33L;
int shifted = b << count; // 10, vì kiểu trái là int và 33 & 31 = 1.
~~~

`count` là `long` **không làm kết quả thành `long`**. Đây là khác biệt quan trọng so với phép cộng hai ngôi, nơi hai toán hạng có thể cùng được nâng lên kiểu rộng hơn.

**Phép `~` cũng thực hiện unary numeric promotion**:

~~~java
byte b = 5;
int inverted = ~b; // -6 (đảo 32 bit của int 5).
~~~

Phép `~b` không chỉ đảo 8 bit ban đầu. Nếu `b == 5`, sau nâng kiểu `int` ta có 32-bit `...00000101`, đảo toàn bộ 32 bit thành mẫu bù hai của **-6**.

## 4. Binary numeric promotion với `&`, `|`, `^` kiểu số

Với toán hạng số nguyên, `&`, `|`, `^` áp dụng **binary numeric promotion** trước khi tính.

~~~java
byte a = 5;      // 00000101
short b = 9;     // 0000000000001001

int andResult = a & b; // 1.
int orResult = a | b;  // 13.
int xorResult = a ^ b; // 12.
~~~

Kết quả có kiểu **`int`** vì cả hai toán hạng hẹp đều được nâng lên `int`.

| Toán hạng | Kiểu kết quả | Ví dụ |
| --- | --- | --- |
| `byte & short` | `int` | `5 & 9` = 1 |
| `char ^ byte` | `int` | `65 ^ 5` = 68 |
| `short \| int` | `int` | Nâng `short` thành `int` |
| `byte & long` | `long` | Nâng `byte` thành `long` |
| `char & long` | `long` | Nâng `char` thành `long` |

Khi có `long`, phép toán bit chạy trên **64 bit**. Ví dụ `byte b = -1; long x = b & 0xFFL;` cho 255 vì `b` được mở rộng dấu thành `long -1`, rồi AND với mask `255L`.

### Đừng nhầm toán tử bit và toán tử logic

`&`, `|` và `^` cũng áp dụng trên hai toán hạng `boolean`. Khi là số nguyên, chúng xử lý **từng bit**; khi là boolean, kết quả là boolean. `&&` và `||` chỉ dùng cho boolean và có tính **ngắn mạch**, không có tác dụng trên `int`.

## 5. Mở rộng dấu và mở rộng với số 0

### `byte` và `short` âm: sign extension

~~~java
byte b = -1;
int x = b; // -1.
~~~

Minh họa mẫu bit:

~~~text
byte -1:    11111111
int  -1:    11111111111111111111111111111111
~~~

Java mở rộng bằng **bit 1** vì nguồn có dấu âm. Do đó `Integer.toHexString(b)` in `ffffffff` chứ không in `ff`.

Nếu muốn chỉ xem 8 bit thấp không dấu, dùng mask:

~~~java
int unsigned = b & 0xFF; // 255.
int same = Byte.toUnsignedInt(b); // 255.
~~~

Với `short`, dùng `s & 0xFFFF` hoặc `Short.toUnsignedInt(s)` để đọc 16 bit thấp dưới dạng không dấu.

### `char`: zero extension

~~~java
char c = (char) 0xFFFF;
int x = c; // 65535.
~~~

Mẫu bit:

~~~text
char:        1111111111111111
int:         00000000000000001111111111111111
~~~

`char` không phải số nguyên âm, dù bit cao nhất của mẫu 16 bit là 1. Vì thế:

~~~java
char c = (char) 0xFFFF;
short s = -2;

System.out.println(c >> 15); // 1.
System.out.println(s >> 15); // -1.
~~~

`c` nâng lên `int` không âm nên `>>` chèn bit 0 ở đầu. `s` nâng lên `int -2` nên `>>` lấp bit 1 ở đầu để giữ dấu.

### Vì sao `byte >>> 1` đôi khi có giá trị rất lớn?

~~~java
byte b = -1;
int x = b >>> 1; // 2147483647.
~~~

`b` được mở rộng dấu thành **`int -1`**, gồm 32 bit 1. `>>> 1` điền bit 0 phía trái và dịch còn 31 bit 1, tạo **2147483647**; không phải 127.

Nếu muốn xem dịch logic trên **8 bit nguồn**:

~~~java
int unsignedShift = (b & 0xFF) >>> 1; // 127.
~~~

Ở đây mask `0xFF` **xóa các bit mở rộng dấu trước khi dịch**. Đặt mask sau phép dịch có thể cho kết quả khác trong một số biểu thức; hãy chọn thứ tự theo đúng độ rộng dữ liệu mong muốn.

## 6. Gán kết hợp có thể thu hẹp kết quả về kiểu gốc

Phép toán thường có thể cho `int` trong khi phép gán kết hợp `op=` cho phép **thu hẹp về kiểu biến trái**:

~~~java
byte b = 100;
int result = b << 1; // 200.
b <<= 1;             // hợp lệ, b thành -56.

// b = b << 1;       // Lỗi biên dịch nếu không cast.
b = (byte) (b << 1); // Cast tường minh nếu muốn viết dạng mở rộng.
~~~

Vì miền `byte` là -128..127, `int 200` khi thu về 8 bit thấp thành `11001000`, đọc có dấu là **-56**.

Điều tương tự xảy ra với `short` và `char`:

~~~java
short s = 30_000;
int promoted = s << 1; // 60000.
s <<= 1;               // short -5536.

char c = 'A';
c <<= 1; // char có mã đơn vị 130.
~~~

Với phép toán bit, `byte b = -1; b &= 0x0F;` cũng hợp lệ và trả **15**, do kết quả được gán trở về kiểu `byte`.

**Đừng coi việc biên dịch được là bằng chứng không mất dữ liệu.** Toán tử compound assignment như `<<=`, `&=`, `|=`, `^=` có chuyển kiểu ngầm về biến gốc. Nếu cần giữ kết quả đầy đủ, lưu vào `int` hoặc `long` trước khi thu hẹp.

## 7. Wrapper, `null` và kiểu kết quả

Nếu số được đóng gói trong `Byte`, `Short` hoặc `Character`, toán tử số sẽ **unbox** trước khi numeric promotion.

~~~java
Byte boxed = 5;
int shifted = boxed << 1; // 10.
~~~

Wrapper null không chứa giá trị số để unbox:

~~~java
Byte missing = null;
// int value = missing & 0xFF; // Ném NullPointerException.
~~~

Một biến `Byte` không biến `&` thành phép toán trên đối tượng tham chiếu. Nó vẫn là phép toán số nguyên khi được unbox bình thường.

`var` cũng theo **kiểu của biểu thức khởi tạo**:

~~~java
byte b = 5;
var x = b << 1; // x có kiểu int.
var y = ~b;     // y có kiểu int.
~~~

Không thể suy luận kiểu `byte` cho `x` chỉ vì đầu vào là `byte`.

## 8. Bẫy thường gặp

| Nhầm lẫn | Quy tắc đúng |
| --- | --- |
| “`byte << 1` trả kiểu `byte`.” | Toán hạng trái nâng thành `int`; kết quả `int` |
| “`~byte` chỉ đảo 8 bit.” | Nâng lên `int` trước; `~` đảo **32 bit** |
| “`short & char` trả `short`.” | Hai toán hạng nâng lên `int`; kết quả `int` |
| “Khoảng dịch `long` làm kết quả dịch thành `long`.” | Kiểu kết quả phụ thuộc **toán hạng trái** |
| “`char` có bit cao là 1 nghĩa là số âm.” | `char` không dấu, mở rộng với bit 0 |
| “`byte -1 >>> 1` trả 127.” | Trả **2147483647** do mở rộng dấu thành `int` |
| “`byteValue <<= 1` luôn giữ giá trị toán học chính xác.” | Có thể thu hẹp, mất bit và đổi dấu |
| “`Byte null` tự được coi như số 0.” | Unboxing null ném `NullPointerException` |
| “`var x = b << 1` suy ra kiểu của `b`.” | Suy ra kiểu của **biểu thức**, thường là `int` |

## 9. Bài tập tự kiểm tra

1. `byte b = 7; var x = b << 1;` — kiểu và giá trị của `x`?  
   *Đáp án:* `int`, giá trị **14**.
2. `byte b = 5; int n = ~b;` — `n` bằng bao nhiêu?  
   *Đáp án:* **-6**, vì đảo bit của `int 5`.
3. `byte a = 5; short b = 9; var n = a & b;` — kiểu và giá trị?  
   *Đáp án:* `int`, giá trị **1**.
4. `char c = (char) 0xFFFF; int x = c;` — `x` là bao nhiêu?  
   *Đáp án:* **65535**, vì `char` zero-extend.
5. `short s = -2; int x = s >> 15;` — `x` bằng bao nhiêu?  
   *Đáp án:* **-1**, do sign extension.
6. `byte b = -1; int x = b >>> 1;` — `x` bằng bao nhiêu?  
   *Đáp án:* **2147483647**.
7. `byte b = 100; b <<= 1;` — `b` bằng bao nhiêu?  
   *Đáp án:* **-56**, do thu hẹp `int 200` về `byte`.
8. `char c = 'A'; c <<= 1;` — mã số của `c` là gì?  
   *Đáp án:* **130**.
9. `byte b = 5; long n = 33L; var x = b << n;` — kiểu và giá trị `x`?  
   *Đáp án:* `int` và **10**; khoảng dịch `33 & 31 = 1`.

## Checklist

- [ ] Nhớ `byte`/`short`/`char` thường nâng thành `int` trước khi thao tác bit.
- [ ] Phân biệt **unary numeric promotion** của `~` và dịch bit với **binary numeric promotion** của `&`/`|`/`^`.
- [ ] Biết `byte`/`short` **mở rộng dấu**, `char` **mở rộng với 0**.
- [ ] Hiểu kiểu kết quả dịch phụ thuộc kiểu **toán hạng trái**, không do kiểu khoảng dịch.
- [ ] Nhận ra `byte >>> 1` thực sự có thể chạy trên `int` 32 bit sau sign extension.
- [ ] Đánh giá mất dữ liệu khi dùng `<<=`, `&=` và các gán kết hợp về kiểu hẹp.
- [ ] Kiểm tra `null` trước khi unbox wrapper.
- [ ] Dùng mask `0xFF`/`0xFFFF` hoặc API unsigned khi cần xem dữ liệu không dấu.

**Kết luận:** Trong các phép bit Java, `byte`, `short` và `char` thường là **nguồn dữ liệu 8/16 bit**, nhưng **phép toán thực tế thực hiện trên `int` 32 bit**. Theo dõi **promotion**, **sign/zero extension** và **narrowing khi gán lại** sẽ giúp tránh các kết quả tưởng như bất ngờ.
