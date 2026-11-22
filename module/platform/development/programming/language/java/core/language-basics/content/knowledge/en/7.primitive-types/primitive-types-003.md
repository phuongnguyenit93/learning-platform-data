# Số nguyên có dấu và biểu diễn bù hai trong Java

> **Java core — language-basics / Kiểu nguyên thủy**  
> **Môi trường:** JDK 17 trở lên; không cần thư viện ngoài.  
> **Mục tiêu:** Hiểu bit dấu và quy tắc **bù hai (two's complement)** của `byte`, `short`, `int`, `long`; tự đọc một mẫu bit thành số dương/âm; nhận ra tràn số, mở rộng dấu và sự khác nhau giữa dịch phải có dấu/không dấu.


## 1. Vì sao cùng mẫu bit có thể mang số âm?

Bốn kiểu số nguyên có dấu của Java có độ rộng cố định: `byte` **8 bit**, `short` **16 bit**, `int` **32 bit**, `long` **64 bit**. Với `n` bit, miền giá trị là `-2^(n-1)` đến `2^(n-1)-1`. Bài trước đã dùng những miền này để chọn kiểu và nhận biết phép chuyển kiểu; ở đây ta tìm hiểu **vì sao** bù hai tạo ra chúng.

Ở độ rộng xác định, bit cao nhất bằng 1 báo một giá trị âm theo **bù hai**. Tuy nhiên không được đọc bảy bit còn lại như độ lớn rồi đặt dấu trừ (*sign-magnitude*). Chẳng hạn, mẫu `1000_0000` của `byte` mang giá trị **-128**, trong khi `0111_1111` là **127**. `char` cũng rộng 16 bit nhưng là **code unit UTF-16 không dấu**, không theo miền của `short`.

## 2. Cách đọc mẫu bit bù hai

Đừng chỉ xem bit cao nhất là dấu rồi cộng độ lớn của các bit còn lại như cách *sign-magnitude*. Với bù hai `n` bit, ta có quy tắc đọc mẫu bit:

- Nếu bit cao nhất là **0**, giá trị bằng số không dấu của mẫu bit.
- Nếu bit cao nhất là **1**, lấy giá trị **không dấu** của mẫu bit rồi **trừ 2^n**.

Ví dụ ở độ rộng **8 bit**:

| Bit pattern | Giá trị không dấu | Giá trị `byte` có dấu |
| --- | ---: | ---: |
| `0000_0000` | 0 | 0 |
| `0000_0101` | 5 | 5 |
| `0111_1111` | 127 | 127 |
| `1000_0000` | 128 | -128 |
| `1111_1011` | 251 | -5 |
| `1111_1111` | 255 | -1 |

Ví dụ `1111_1011` là 251 theo cách hiểu không dấu; dưới dạng `byte` 8-bit có dấu, giá trị là **251 - 256 = -5**.

### Tạo biểu diễn âm bằng đảo bit rồi cộng 1

Để tìm mẫu bit của **-5** từ **+5** trong 8 bit:

~~~text
+5:                  0000 0101
Đảo từng bit:        1111 1010
Cộng 1:              1111 1011    => -5
~~~

Phép đảo bit rồi cộng một là cách minh họa bù hai khi độ rộng bit **được cố định**. Java có **một biểu diễn số 0** duy nhất trong bù hai: `0000_0000`; không có dạng “âm không” riêng cho số nguyên.

Do chia đôi không gian mẫu bit, kiểu 8-bit có giá trị nhỏ nhất **-128** nhưng giá trị lớn nhất chỉ **127**. Không có số `+128` kiểu `byte`. Vì vậy `-Byte.MIN_VALUE` khi được tính ở độ rộng `int` cho ra 128; việc ép kết quả trở lại `byte` sẽ cho -128.

## 3. Chương trình Java 17+ kiểm chứng

Tạo tệp **TwosComplementDemo.java**:

~~~java
public final class TwosComplementDemo {
    private static String bits8(int value) {
        String bits = Integer.toBinaryString(value & 0xFF);
        return "0".repeat(8 - bits.length()) + bits;
    }

    public static void main(String[] args) {
        byte five = 5;
        byte minusFive = -5;
        byte highBit = (byte) 0x80;

        System.out.println("five=" + bits8(five));
        System.out.println("minusFive=" + bits8(minusFive));
        System.out.println("minusOne=" + bits8(-1));
        System.out.println("highBit=" + bits8(highBit));
        System.out.println("byteRange=" + Byte.MIN_VALUE
                + ".." + Byte.MAX_VALUE);

        System.out.println("highBitAsByte=" + highBit);
        System.out.println("signExtendedHex="
                + Integer.toHexString(highBit));
        System.out.println("maskedHex="
                + Integer.toHexString(highBit & 0xFF));
        System.out.println("unsignedByteFF="
                + Byte.toUnsignedInt((byte) 0xFF));

        int max = Integer.MAX_VALUE;
        System.out.println("overflow=" + (max + 1));
        try {
            Math.addExact(max, 1);
        } catch (ArithmeticException exception) {
            System.out.println("addExact=overflow");
        }

        System.out.println("signedShift=" + (-8 >> 1));
        System.out.println("unsignedShift=" + (-8 >>> 1));
        System.out.println("intMinusOneHex="
                + Integer.toHexString(-1));
    }
}
~~~

Biên dịch và chạy trong Bash, PowerShell hoặc Command Prompt từ thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 TwosComplementDemo.java
java TwosComplementDemo
~~~

**Expected output (chính xác):**

~~~text
five=00000101
minusFive=11111011
minusOne=11111111
highBit=10000000
byteRange=-128..127
highBitAsByte=-128
signExtendedHex=ffffff80
maskedHex=80
unsignedByteFF=255
overflow=-2147483648
addExact=overflow
signedShift=-4
unsignedShift=2147483644
intMinusOneHex=ffffffff
~~~

Hàm `bits8` lấy **8 bit thấp** bằng `& 0xFF` rồi thêm các số 0 ở đầu. Cách này quan trọng vì `Integer.toBinaryString(-5)` không trả chuỗi 8 bit: tham số là `int`, nên biểu diễn của -5 có **32 bit**.

## 4. Mở rộng dấu, ép kiểu và mẫu bit

Khi chuyển một số nguyên âm từ kiểu hẹp sang kiểu rộng hơn, Java **mở rộng dấu** (*sign extension*): những bit mới ở đầu được điền bằng bit dấu.

Ví dụ:

~~~java
byte b = (byte) 0x80; // 1000_0000, có dấu là -128.
int n = b;             // n vẫn là -128.
~~~

Ở `byte`, `b` có mẫu 8 bit `1000_0000`. Sau khi gán sang `int`, `n` có mẫu 32 bit `0xFFFF_FF80` (hệ 16: `ffffff80` khi in qua `Integer.toHexString`).

Ngược lại, `b & 0xFF` cho giá trị `int` **128**, vì mặt nạ chỉ giữ 8 bit thấp và các bit cao của kết quả được xóa. Đó là cách xem mẫu 8 bit dưới góc nhìn không dấu; nó **không đổi kiểu `byte` thành unsigned**.

| Biểu thức Java | Giá trị / kết quả | Vì sao |
| --- | --- | --- |
| `(byte) 0xFF` | -1 | Giữ 8 bit thấp: `11111111` |
| `(byte) 0x80` | -128 | Bit dấu 8-bit bằng 1 |
| `((byte) 0xFF) & 0xFF` | 255 | Thao tác `&` diễn ra ở `int` và dùng mask |
| `Byte.toUnsignedInt((byte) 0xFF)` | 255 | Diễn giải 8 bit dưới dạng không dấu |
| `Integer.toHexString(-1)` | `ffffffff` | Biểu diễn toàn bộ 32 bit của `int` -1 |

**Lưu ý về literal:** `0xFF` trong Java tự nó là một literal `int` có giá trị **255**, không phải `byte` -1. Chỉ sau phép ép kiểu `(byte) 0xFF`, 8 bit thấp mới được diễn giải thành -1. Tương tự, literal `0xFFFF_FFFF` là giá trị `int` -1 vì chiếm đủ 32 bit với bit dấu 1.

## 5. Phép toán, tràn số và đổi dấu

Với số nguyên Java, kết quả của các phép tính `int`/`long` có độ rộng cố định. Nếu vượt giới hạn, phép tính số nguyên thông thường **quay vòng theo 2^n**; Java không tự ném exception chỉ vì phép cộng bị tràn.

Ví dụ:

~~~java
int max = Integer.MAX_VALUE;  // 2147483647
int wrapped = max + 1;
System.out.println(wrapped);  // -2147483648
~~~

Trước phép cộng, bit pattern của `max` là `0x7FFF_FFFF`. Cộng 1 cho `0x8000_0000`, được đọc là **Integer.MIN_VALUE** theo bù hai.

Muốn **phát hiện** tràn đối với phép cộng/trừ/nhân `int`/`long`, dùng `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`: các hàm này ném `ArithmeticException` khi vượt miền biểu diễn.

### Hai trường hợp đáng chú ý

- `-Integer.MIN_VALUE` vẫn là **Integer.MIN_VALUE** khi tính dưới dạng `int`: giá trị dương tương ứng `2147483648` nằm ngoài phạm vi `int`. `Math.negateExact(Integer.MIN_VALUE)` ném `ArithmeticException`.
- `Math.abs(Integer.MIN_VALUE)` cũng cho ra **giá trị âm** Integer.MIN_VALUE. Không giả định `abs` luôn cho số không âm ở biên nhỏ nhất của kiểu nguyên.

Trong các biểu thức có `byte` hoặc `short`, nhiều toán tử số học sẽ **nâng kiểu về `int`** trước khi tính. Vì thế `-Byte.MIN_VALUE` (trong biểu thức số học thông thường) là `int` **128**, không phải một `byte` bị tràn; chỉ sau ép `(byte)` mới còn 8 bit và thành -128.

## 6. Dịch bit `>>` và `>>>`

Với số âm:

- `x >> k`: **dịch phải số học**, thêm các bit 1 vào phía trái để **giữ bit dấu**.
- `x >>> k`: **dịch phải logic**, thêm các bit 0 vào phía trái; với số âm, kết quả có thể là số dương lớn.

Ví dụ từ `TwosComplementDemo`:

~~~java
System.out.println(-8 >> 1);  // -4
System.out.println(-8 >>> 1); // 2147483644
~~~

`-8` trong `int` là `0xFFFF_FFF8`. Dịch số học một bit cho `0xFFFF_FFFC` (-4); dịch logic một bit cho `0x7FFF_FFFC` (2147483644).

Hai toán tử làm việc theo **độ rộng toán hạng sau quy tắc nâng kiểu**. Nếu dịch một `byte`, biểu thức trước tiên dùng `int`; đừng suy luận kết quả `>>>` có độ rộng 8 bit.

## 7. Bẫy phổ biến và hướng sửa

| Cách hiểu hoặc hiện tượng | Điều đúng |
| --- | --- |
| “Bit cao nhất bằng 1 nên lấy 7 bit còn lại rồi thêm dấu trừ.” | Sai: Java dùng **bù hai**, không dùng sign-magnitude |
| “`0xFF` là `byte` -1.” | Sai: literal này là `int` 255; `(byte) 0xFF` mới là -1 |
| “Biến `byte` âm mở rộng thành `int` có giá trị dương.” | Sai: phép mở rộng kiểu giữ giá trị có dấu bằng **sign extension** |
| “`Integer.MAX_VALUE + 1` ném lỗi tự động.” | Sai: phép cộng `int` thông thường bị tràn, cho Integer.MIN_VALUE |
| “`Math.abs` luôn không âm.” | Sai tại Integer.MIN_VALUE/Long.MIN_VALUE |
| “`>>` và `>>>` cho kết quả giống nhau trên số âm.” | Sai: một bên điền bit dấu, một bên điền 0 |
| “`char` là signed 16-bit giống `short`.” | Sai: `char` là đơn vị mã UTF-16 **không dấu** |

## 8. Bài tập tự luyện

**Bài 1:** Dùng quy tắc 8 bit để tìm biểu diễn bù hai của -6. Kiểm tra bằng `Integer.toBinaryString((-6) & 0xFF)`; nếu muốn đúng 8 ký tự, cần thêm bao nhiêu số 0 ở đầu?

**Bài 2:** Phân loại `0x7F`, `0x80` và `0xFF` khi dùng dạng `int`, rồi dự đoán kết quả của từng biểu thức sau ép `(byte)`.

**Bài 3:** Vì sao `int n = (byte) 0xFF;` cho `n = -1`, nhưng `int n = 0xFF;` cho `n = 255`? Mô tả bước ép xuống 8 bit và mở rộng dấu về 32 bit.

**Bài 4:** Tính `Integer.MAX_VALUE + 1` và `Math.addExact(Integer.MAX_VALUE, 1)`. Cách nào cho giá trị, cách nào báo lỗi?

**Bài 5:** Với số `-8`, vẽ bốn byte của `int` rồi thực hiện `>> 1` và `>>> 1`; lý giải hai đầu ra khác nhau.

### Ghi nhớ

**Java `byte`/`short`/`int`/`long` đều có dấu và biểu diễn bằng bù hai.** Với `n` bit, mẫu có bit cao nhất 1 được đọc là **giá trị không dấu trừ 2^n**; miền là **-2^(n-1) đến 2^(n-1)-1**. Mở rộng kiểu âm giữ nguyên dấu; ép hẹp giữ các bit thấp; phép tính số nguyên có thể tràn mà không báo lỗi nếu không dùng API kiểm tra; `>>` và `>>>` khác nhau ở cách điền bit khi dịch phải.
