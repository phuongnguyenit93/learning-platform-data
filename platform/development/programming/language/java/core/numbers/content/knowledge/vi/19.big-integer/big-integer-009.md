# Phép bit trên số nguyên có độ dài mở rộng với BigInteger trong Java

`java.math.BigInteger` biểu diễn **số nguyên có độ chính xác tùy ý** (*arbitrary precision*), không bị cố định trong 32 bit của `int` hoặc 64 bit của `long`. Ngoài cộng, trừ, nhân, chia, lớp này cung cấp các phép **AND, OR, XOR, NOT, dịch bit và thao tác từng bit**. Các phép đó hữu ích khi làm việc với cờ trạng thái lớn, bitset, giao thức nhị phân, biểu diễn số nguyên rất lớn và thuật toán số học.

Nhưng có khác biệt quan trọng: phép bit của `BigInteger` hoạt động **như thể giá trị được lưu dưới dạng bù hai (*two's complement*) với các bit dấu ảo kéo dài vô hạn**. Đặc biệt, `not()` của một số dương có thể trả số âm, dịch phải số âm giữ dấu, và `BigInteger` **không có phép dịch phải không dấu `>>>`**. Nếu bài toán thật sự đòi một từ máy có độ rộng 8, 16, 32 hay 256 bit, lập trình viên phải tự áp **mặt nạ giới hạn độ rộng**.

Bài học thuộc mục **BigInteger** trong Java Core. Các ví dụ sử dụng Java 17+ và giải thích cả giá trị thập phân, bit nhị phân, bit dấu, kết quả chính xác và các bẫy thường gặp.

## 1. Khởi tạo BigInteger và tư duy bit không giới hạn độ rộng

`BigInteger` là class bất biến (*immutable*). Sử dụng constructor nhận chuỗi và radix hoặc `valueOf(long)`:

~~~java
import java.math.BigInteger;

BigInteger a = new BigInteger("101101", 2); // nhị phân 101101 = 45
BigInteger b = new BigInteger("011110", 2); // nhị phân 011110 = 30
BigInteger hex = new BigInteger("FF", 16);  // 255
BigInteger small = BigInteger.valueOf(45L);
~~~

Radix hợp lệ từ 2 đến 36, và chuỗi phải tuân thủ cú pháp của constructor. `new BigInteger("101101", 2)` là cú pháp đúng, còn `new BigInteger("0b101101", 2)` không tự chấp nhận tiền tố `0b`. `toString(2)` cho chuỗi biểu diễn theo cơ số 2, ví dụ `"101101"` đối với số dương 45.

Một số `BigInteger` dương có thể có hàng nghìn hoặc hàng triệu bit. Trong biểu thức toán học, phép bit vẫn được định nghĩa trên **hai số nguyên có dấu**, không phải trên hai mảng byte với kích thước cố định. Khi cần lưu thành gói tin hay thao tác cờ trong một độ rộng xác định, phải chọn rõ độ rộng trước.

**Điểm mấu chốt về âm:** số âm được xem như có vô hạn bit 1 ở đầu trong biểu diễn bù hai. Số `-1` được hình dung `...11111111`, còn `0` là `...00000000`. Dấu ba chấm biểu diễn **bit ảo** của mô hình toán học, không có nghĩa JVM thật sự cấp phát vô hạn bộ nhớ.

## 2. AND, OR, XOR và AND-NOT

Với `a = 45` và `b = 30`:

~~~text
a = 101101₂  (45)
b = 011110₂  (30)
--------------
& = 001100₂  (12)
| = 111111₂  (63)
^ = 110011₂  (51)
~~~

Các phương thức tương ứng:

| Thao tác | BigInteger API | Quy tắc từng bit | Kết quả ví dụ |
| --- | --- | --- | --- |
| AND | `a.and(b)` | 1 chỉ khi cả hai bit đều 1 | 12 |
| OR | `a.or(b)` | 1 khi ít nhất một bit là 1 | 63 |
| XOR | `a.xor(b)` | 1 khi hai bit khác nhau | 51 |
| AND NOT | `a.andNot(b)` | `a & ~b` | 33 |
| NOT | `a.not()` | Đảo tất cả bit theo mô hình bù hai | Phụ thuộc a; có thể âm |

~~~java
BigInteger a = new BigInteger("101101", 2);
BigInteger b = new BigInteger("011110", 2);

BigInteger intersection = a.and(b); // 12
BigInteger combined = a.or(b);      // 63
BigInteger differences = a.xor(b);  // 51
BigInteger removed = a.andNot(b);   // 33
~~~

Với các bit cờ, `and(mask)` thường dùng để lấy những bit được chọn; `or(mask)` bật một nhóm bit; `andNot(mask)` tắt một nhóm bit; `xor(mask)` lật trạng thái một nhóm bit. Các phép nhị phân này **không mutate `a` hoặc `b`**; chúng tạo `BigInteger` kết quả mới.

Nếu hai toán hạng khác độ dài hoặc có dấu khác nhau, BigInteger thực hiện phép logic theo **mô hình mở rộng dấu** của hai số. Không cần tự điền 0 hoặc 1 để hai số có cùng độ rộng trước khi gọi `and`, `or` và `xor`, trừ khi bài toán yêu cầu mô phỏng bitvector độ rộng cố định.

## 3. NOT là bẫy lớn nhất: `not()` không phải đảo N bit

Trong một bitvector **8 bit**, đảo bit của `00000101₂` được `11111010₂`, nghĩa là **250 nếu xem như unsigned**. Nhưng `BigInteger.valueOf(5).not()` trả **-6**, không phải 250:

~~~java
BigInteger five = BigInteger.valueOf(5);
System.out.println(five.not()); // -6
~~~

Vì mô hình là bù hai có dấu được mở rộng vô hạn, đẳng thức toán học đúng với mọi số nguyên `x` là:

~~~text
~x = -x - 1
~5 = -6
~-1 = 0
~~~

Nếu muốn **đảo trong 8 bit**, cần tạo mask `0xFF = 255` rồi chỉ giữ tám bit thấp:

~~~java
BigInteger mask8 =
        BigInteger.ONE.shiftLeft(8).subtract(BigInteger.ONE);
BigInteger inverted8 = five.not().and(mask8);
// inverted8 = 250 (nhị phân 11111010 trong 8 bit)
~~~

Tổng quát, với độ rộng `w > 0`, mặt nạ là `2^w - 1`:

~~~java
static BigInteger mask(int width) {
    if (width <= 0) {
        throw new IllegalArgumentException("width must be positive");
    }
    return BigInteger.ONE.shiftLeft(width).subtract(BigInteger.ONE);
}
~~~

Phương thức trên **chỉ là đoạn minh họa**, cần đặt trong một class và giới hạn `width` hợp lý theo tài nguyên. Một ví dụ `width` rất lớn có thể tiêu thụ nhiều bộ nhớ; độ dài tùy ý không có nghĩa chi phí thực thi không giới hạn.

Với cùng mặt nạ, biểu thức `value.and(mask)` cũng là cách lấy phần dư **không âm** trong phạm vi `0..2^w-1` của biểu diễn w-bit: `BigInteger.valueOf(-1).and(mask8)` trả 255. Đây là **phép chiếu sang bitvector unsigned w-bit**, không làm số nguyên âm ban đầu biến mất.

## 4. Dịch trái và dịch phải: dấu được bảo toàn theo quy tắc số học

`shiftLeft(n)` tương tự `<<` và `shiftRight(n)` tương tự `>>` của số nguyên có dấu. Dịch trái n bit thường nhân giá trị với `2^n`; dịch phải n bit tương đương **lấy floor khi chia cho `2^n`**, rất quan trọng với số âm.

~~~java
BigInteger a = BigInteger.valueOf(45);
BigInteger left = a.shiftLeft(3);  // 360 = 45 * 8
BigInteger right = a.shiftRight(2); // 11 = floor(45 / 4)

BigInteger negative = BigInteger.valueOf(-3);
BigInteger arithmeticRight = negative.shiftRight(1); // -2
~~~

Với `-3 >> 1`, kết quả là `-2` vì quy tắc làm tròn xuống khi dịch số học, **không phải `-1`** theo phép chia `-3 / 2` của số nguyên Java, vốn chia lấy phần nguyên về phía 0.

So với primitive `int`/`long`, BigInteger có một số khác biệt:

- Khoảng dịch `n` không bị lấy modulo 32/64 như số bit của primitive. Ví dụ `BigInteger.ONE.shiftLeft(32)` là `4294967296`, không quay lại 1.
- BigInteger cho phép **khoảng dịch âm**: `shiftLeft(-2)` tương đương dịch phải 2 bit; `shiftRight(-2)` tương đương dịch trái 2 bit.
- Các bit dấu ảo được kéo dài khi dịch phải; `BigInteger.valueOf(-1).shiftRight(100)` vẫn là `-1`.
- Dịch trái số lớn có thể tạo giá trị/khối dữ liệu rất lớn; nên giới hạn số bit theo nghiệp vụ và tài nguyên.

Ví dụ:

~~~java
BigInteger a = BigInteger.valueOf(45);
a.shiftLeft(-2);  // 11 (cùng hướng với shiftRight(2))
a.shiftRight(-2); // 180 (cùng hướng với shiftLeft(2))
~~~

**Không có `BigInteger.unsignedShiftRight` hay toán tử `>>>` dành cho `BigInteger`.** Với số có bit dấu ảo 1 kéo dài vô hạn, việc “đẩy 0 vào từ phía trái” thiếu định nghĩa nếu không chọn trước một độ rộng từ máy. Để mô phỏng unsigned right shift ở độ rộng `w`, chuẩn hóa bằng mask rồi `shiftRight` trên giá trị không âm trong `0..2^w-1`.

## 5. Thao tác bit thứ n: `testBit`, `setBit`, `clearBit` và `flipBit`

Trong các API thao tác bit riêng lẻ, **bit 0 là bit thấp nhất (LSB)**. Ví dụ `45 = 101101₂` có các bit 0, 2, 3 và 5 bằng 1.

| Phương thức | Ý nghĩa |
| --- | --- |
| `testBit(n)` | Đọc trạng thái bit n (boolean) |
| `setBit(n)` | Trả về số mới với bit n được đặt thành 1 |
| `clearBit(n)` | Trả về số mới với bit n được đặt thành 0 |
| `flipBit(n)` | Trả về số mới với bit n bị đảo |
| `getLowestSetBit()` | Trả về vị trí bit 1 thấp nhất; trả `-1` đối với số 0 |

~~~java
BigInteger a = BigInteger.valueOf(45); // 101101₂
boolean bit3 = a.testBit(3);            // true
BigInteger withBit1 = a.setBit(1);      // 47
BigInteger withoutBit3 = a.clearBit(3); // 37
BigInteger flippedBit2 = a.flipBit(2);  // 41
~~~

`a` vẫn bằng 45 sau các lời gọi vì `BigInteger` bất biến. Nếu muốn lưu kết quả, hãy gán lại: `a = a.setBit(1);`. Chỉ số bit phải là số nguyên **không âm**; `testBit(-1)`, `setBit(-1)`, `clearBit(-1)` hoặc `flipBit(-1)` sẽ ném `ArithmeticException`.

**Với số âm**, test bit ở rất xa phía trái vẫn có thể trả true do sign extension:

~~~java
BigInteger minusOne = BigInteger.valueOf(-1);
boolean highBit = minusOne.testBit(100); // true
~~~

Không suy diễn rằng `minusOne` phải có ít nhất 101 bit vật lý đang được lưu. Các bit cao là một phần **mô hình bù hai vô hạn**.

## 6. `bitLength()`, `bitCount()` và `getLowestSetBit()`

Ba phương thức này **không thay thế nhau**:

- `bitLength()` trả số bit cần cho biểu diễn bù hai **tối thiểu, loại trừ bit dấu**. Với số dương, gần với độ dài biểu diễn nhị phân thông thường; ví dụ 256 cần 9 bit.
- `bitCount()` đếm số bit trong biểu diễn bù hai **khác bit dấu**. Với số không âm, đây là số bit 1; với số âm, đây là số bit 0 hữu hạn khác các bit 1 dấu kéo dài vô hạn.
- `getLowestSetBit()` trả chỉ số của bit 1 thấp nhất, hay `-1` nếu giá trị là 0.

~~~java
BigInteger a = BigInteger.valueOf(45); // 101101₂

a.bitLength(); // 6
a.bitCount();  // 4
BigInteger.valueOf(40).getLowestSetBit(); // 3
BigInteger.ZERO.getLowestSetBit();        // -1
~~~

Các trường hợp dễ nhầm:

| Giá trị | `bitLength()` | `bitCount()` | Vì sao? |
| --- | ---: | ---: | --- |
| `0` | 0 | 0 | Không có bit 1 |
| `45` | 6 | 4 | `101101₂` có 6 bit, bốn bit 1 |
| `256` | 9 | 1 | `1` theo sau bởi 8 bit 0 |
| `-1` | 0 | 0 | Dãy dấu ảo `...111111`; không có bit khác dấu |
| `-8` | 3 | 3 | Dãy bù hai `...11111000`; ba bit 0 thấp khác bit dấu |

Vì vậy **`bitLength(-1) == 0` không có nghĩa -1 là 0 hoặc không có bit 1**. Nếu thuật toán đòi độ dài bit của một số *unsigned* hoặc độ dài bit của một field trong giao thức, hãy chuẩn hóa về số không âm và áp dụng định nghĩa độ rộng của field đó.

## 7. Mô phỏng từ máy w-bit bằng mask: AND, NOT, shift và rotate

Khi đọc một word/bitfield với **độ rộng cố định**, đầu tiên tạo mask và chuẩn hóa:

~~~java
int width = 8;
BigInteger modulus = BigInteger.ONE.shiftLeft(width);
BigInteger mask = modulus.subtract(BigInteger.ONE);

BigInteger unsigned = BigInteger.valueOf(-1).and(mask); // 255
BigInteger inverted = BigInteger.valueOf(5).not().and(mask); // 250
BigInteger unsignedRight = unsigned.shiftRight(1); // 127
~~~

Với một đầu vào không âm đã giới hạn, `shiftRight` dịch 0 vào phần trái vì giá trị không có dấu âm. Việc **AND với mask trước khi dịch** có ý nghĩa quan trọng với các đầu vào âm.

Ví dụ **xoay trái (rotate-left) trong 8 bit** của `0x81`:

~~~java
BigInteger mask8 =
        BigInteger.ONE.shiftLeft(8).subtract(BigInteger.ONE);
BigInteger word = new BigInteger("10000001", 2); // 0x81 = 129

BigInteger rotated = word.shiftLeft(1).and(mask8)
        .or(word.shiftRight(7));
// rotated = 3 (binary 00000011)
~~~

Đây là phép xoay trái một bit **được cài trên bitvector 8-bit**, không phải phương thức rotate trực tiếp của `BigInteger`. Nếu muốn xoay một khoảng `n` bất kỳ, trước tiên chuẩn hóa `n` theo `width`, xử lý riêng độ rộng 0 không hợp lệ và mask lại kết quả. Khi dùng bitvector cho giao thức, cần ghi rõ **endianness khi chuyển sang byte**, bit numbering, signedness và width.

Một trường hợp bit-field khác là trích bốn bit ở vị trí 4–7:

~~~java
BigInteger packetWord = new BigInteger("AB3", 16);
BigInteger fourBits = packetWord.shiftRight(4)
        .and(BigInteger.valueOf(15));
// fourBits = 11 (0xB)
~~~

Nếu word chứa nhiều trường với offset và độ dài cố định, nên viết hàm trích field có kiểm tra offset/width, thay vì rải các con số mask khó hiểu khắp mã nguồn.

## 8. `toByteArray()` và signed/unsigned bytes

`BigInteger.toByteArray()` trả **mảng byte big-endian biểu diễn bù hai có dấu, có đủ bit dấu**. Vì vậy số dương có bit cao nhất của byte đầu bằng 1 có thể cần một byte `0x00` ở đầu để tránh bị giải thích thành số âm.

~~~java
BigInteger value = BigInteger.valueOf(255);
byte[] signedBytes = value.toByteArray();
// Mảng bytes: [0, -1] trong cách in Arrays.toString(...)
~~~

Ở Java, `byte` có dấu nên byte `0xFF` khi in kiểu `byte` trở thành `-1`. Hai cách dựng `BigInteger` từ cùng dãy byte `0xFF` mang ý nghĩa khác nhau:

~~~java
byte[] raw = {(byte) 0xFF};

BigInteger signed = new BigInteger(raw);    // -1
BigInteger unsigned = new BigInteger(1, raw); // 255
~~~

Constructor `new BigInteger(byte[])` nhận **bù hai có dấu**, còn constructor `new BigInteger(signum, magnitude)` nhận **dấu riêng và độ lớn magnitude**, với `signum = 1` cho số dương. Đừng mặc định cả hai cách nhận raw bytes tương đương.

`toByteArray()` không trả một mảng byte **unsigned có độ dài cố định**. Nếu giao thức đòi đúng 16 hoặc 32 byte, cần:

1. Kiểm tra giá trị có vừa miền unsigned/signed tương ứng không.
2. Xác định byte order (API này trả big-endian).
3. Kiểm tra và loại byte 0 dấu bổ sung khi **an toàn** và khi giao thức muốn unsigned magnitude.
4. Đệm thêm `0x00` về đúng chiều để đủ độ dài, hoặc chuyển sang two's complement width-bit theo đặc tả của giao thức.

Đừng tùy tiện loại một byte đầu chỉ vì bằng 0 nếu giao thức cần giữ độ dài hoặc chính sách signedness khác.

## 9. Ví dụ Java 17+ hoàn chỉnh và kết quả thực thi

Lưu file `BigIntegerBitsDemo.java`:

~~~java
import java.math.BigInteger;
import java.util.Arrays;

public class BigIntegerBitsDemo {
    public static void main(String[] args) {
        BigInteger a = new BigInteger("101101", 2);
        BigInteger b = new BigInteger("011110", 2);
        BigInteger mask8 =
                BigInteger.ONE.shiftLeft(8).subtract(BigInteger.ONE);

        System.out.println("a = " + a);
        System.out.println("b = " + b);
        System.out.println("a & b = " + a.and(b));
        System.out.println("a | b = " + a.or(b));
        System.out.println("a ^ b = " + a.xor(b));
        System.out.println("a andNot b = " + a.andNot(b));
        System.out.println("not 5 = "
                + BigInteger.valueOf(5).not());
        System.out.println("not 5 in 8 bits = "
                + BigInteger.valueOf(5).not().and(mask8));

        System.out.println("a << 3 = " + a.shiftLeft(3));
        System.out.println("a >> 2 = " + a.shiftRight(2));
        System.out.println("-3 >> 1 = "
                + BigInteger.valueOf(-3).shiftRight(1));
        System.out.println("-1 testBit(100) = "
                + BigInteger.valueOf(-1).testBit(100));
        System.out.println("-1 & 255 = "
                + BigInteger.valueOf(-1).and(mask8));

        System.out.println("a testBit(3) = " + a.testBit(3));
        System.out.println("a setBit(1) = " + a.setBit(1));
        System.out.println("a clearBit(3) = " + a.clearBit(3));
        System.out.println("a flipBit(2) = " + a.flipBit(2));

        System.out.println("bitLength(256) = "
                + BigInteger.valueOf(256).bitLength());
        System.out.println("bitLength(-1) = "
                + BigInteger.valueOf(-1).bitLength());
        System.out.println("bitCount(a) = " + a.bitCount());
        System.out.println("bitCount(-1) = "
                + BigInteger.valueOf(-1).bitCount());
        System.out.println("lowest set bit(40) = "
                + BigInteger.valueOf(40).getLowestSetBit());
        System.out.println("a binary = " + a.toString(2));

        byte[] one = {(byte) 0xFF};
        System.out.println("from signed byte = "
                + new BigInteger(one));
        System.out.println("from unsigned byte = "
                + new BigInteger(1, one));
        System.out.println("255 bytes = "
                + Arrays.toString(BigInteger.valueOf(255).toByteArray()));

        BigInteger x = new BigInteger("10000001", 2);
        System.out.println("rotate left 8-bit 0x81 = "
                + x.shiftLeft(1).and(mask8).or(x.shiftRight(7)));
        System.out.println("a unchanged = " + a);
    }
}
~~~

Lệnh biên dịch và chạy trên Java 17+:

~~~bash
javac BigIntegerBitsDemo.java
java BigIntegerBitsDemo
~~~

Stdout chính xác:

~~~text
a = 45
b = 30
a & b = 12
a | b = 63
a ^ b = 51
a andNot b = 33
not 5 = -6
not 5 in 8 bits = 250
a << 3 = 360
a >> 2 = 11
-3 >> 1 = -2
-1 testBit(100) = true
-1 & 255 = 255
a testBit(3) = true
a setBit(1) = 47
a clearBit(3) = 37
a flipBit(2) = 41
bitLength(256) = 9
bitLength(-1) = 0
bitCount(a) = 4
bitCount(-1) = 0
lowest set bit(40) = 3
a binary = 101101
from signed byte = -1
from unsigned byte = 255
255 bytes = [0, -1]
rotate left 8-bit 0x81 = 3
a unchanged = 45
~~~

Các dòng đầu kiểm tra chính xác AND/OR/XOR/AND-NOT. Các dòng `not`, `shiftRight`, `testBit(100)` cho thấy **mô hình bù hai vô hạn**, còn các dòng mask/rotate cho thấy cách trở lại thế giới **bitvector 8-bit**. Dòng cuối chứng minh `BigInteger` là immutable: các kết quả bitwise được tạo mới mà không thay đổi `a`.

## 10. So sánh với `int`, `long` và `BitSet`

| Đặc tính | `int`/`long` | `BigInteger` | `java.util.BitSet` |
| --- | --- | --- | --- |
| Độ rộng | Cố định 32/64 bit | Mở rộng theo giá trị | Bitset linh hoạt |
| Ngữ nghĩa dấu | Bù hai có dấu | Bù hai với sign extension ảo | Thường dùng tập bit không âm theo vị trí |
| Cú pháp toán tử | `&`, `|`, `^`, `~`, `<<`, `>>`, `>>>` | Phương thức `and`, `or`, `xor`, `not`, `shiftLeft`, `shiftRight` | API set/clear/flip/get và phép tập hợp |
| Dịch phải không dấu | Có `>>>` | Không có trực tiếp | Không phải số nguyên signed |
| Giá trị sau thao tác | Primitive value | Object bất biến mới | `BitSet` thường sửa trạng thái bên trong |

**Chọn `BigInteger`** khi đối tượng chính là một **số nguyên lớn** và cần cả số học lẫn phép bit. **Chọn `BitSet`** khi đối tượng chính là **tập các vị trí boolean**, cần bật/tắt nhiều bit và muốn API cấu trúc dữ liệu; `BitSet` có ngữ nghĩa và mutability khác `BigInteger`. **Chọn `int`/`long`** khi độ rộng cố định và hành vi overflow/unsigned dịch được quy định rõ.

Không thay thế các loại này theo cảm giác “đều chứa bit”: hãy xem yêu cầu signedness, kích thước, tính bất biến, định dạng xuất và semantics của bit cao.

## 11. Bẫy về hiệu năng, bộ nhớ và an toàn

**Độ dài mở rộng vẫn có giới hạn thực tế.** Dịch `BigInteger.ONE.shiftLeft(1_000_000)` có thể tạo một số rất lớn và phải phân bổ bộ nhớ; việc nhận width/bit index tùy ý từ người dùng mà không kiểm tra có thể dẫn đến tiêu hao tài nguyên. Java có thể ném ngoại lệ cho giá trị/độ dài không được hỗ trợ hoặc không còn tài nguyên.

**Không có nghĩa mọi phép bit là thời gian hằng số.** Những phép trên BigInteger thường phụ thuộc kích thước giá trị/biểu diễn. Khi dùng BigInteger cho mật mã, phải cân nhắc cả yêu cầu **constant-time**, rò rỉ thời gian và thư viện mật mã chuyên dụng; không thể suy ra an toàn về side-channel chỉ từ việc số có độ chính xác tùy ý.

**Chuyển về primitive có thể mất bit.** `intValue()` và `longValue()` có thể làm mất các bit cao; nếu cần chắc chắn không mất thông tin thì dùng `intValueExact()`, `longValueExact()` phù hợp và xử lý `ArithmeticException` khi vượt miền.

**Không dùng `bitLength()` như một giới hạn bảo mật cho raw byte unsigned khi số âm vẫn được chấp nhận.** Hãy kiểm tra `signum() >= 0` và giá trị có nằm trong miền định dạng hay không. Với số unsigned w-bit, miền thường là `0 <= x < 2^w`; áp mask để diễn giải/trích bit khác với **từ chối** đầu vào vượt miền.

**Không tự dùng `xor` làm thuật toán mã hóa bảo mật.** XOR là phép bit cơ bản, không phải tự thân một giao thức mật mã an toàn. Phương pháp mã hóa/hashing/kiểm chữ ký cần thuật toán và thư viện được thiết kế cho mục đích đó.

## 12. Những sai lầm phổ biến

1. **Cho rằng `BigInteger` có đúng 64 bit vì tạo từ `long`.** Nó mang giá trị số và có thể mở rộng qua các phép toán sau đó.
2. **Kỳ vọng `BigInteger.valueOf(5).not()` trả 250 như NOT trên 8 bit.** `not()` có nghĩa `~5 = -6`; muốn 250 phải áp mask 8-bit.
3. **Coi số âm có một số lượng bit dấu hữu hạn do `bitLength()` báo.** Bit dấu ảo trong bù hai được sign-extend vô hạn.
4. **Gọi `shiftRight` là dịch phải không dấu.** Với số âm nó là dịch phải số học, giữ dấu; không có `>>>` trực tiếp trên BigInteger.
5. **Giả định shift distance của BigInteger bị lấy modulo 32/64.** Khác primitive, BigInteger không sử dụng cơ chế masking khoảng dịch ấy.
6. **Cho rằng `-3.shiftRight(1)` là -1 vì phép chia nguyên -3/2 cho -1.** Dịch phải âm dùng làm tròn xuống, ra -2.
7. **Giả sử `bitCount()` luôn là số bit 1 hữu hạn.** Với số âm, nó đếm bit khác bit dấu; `bitCount(-1) == 0`.
8. **Cho rằng `bitLength(-1) == 0` tức số không có bit 1.** -1 có các bit dấu ảo bằng 1; bitLength là định nghĩa khác.
9. **Quên gán kết quả `setBit`, `clearBit`, `flipBit`.** BigInteger bất biến, biến gốc không đổi.
10. **Dùng chỉ số bit âm hoặc độ rộng nhập không kiểm soát.** Chỉ số âm ném `ArithmeticException`; chỉ số cực lớn có thể tạo áp lực bộ nhớ.
11. **Hiểu `toByteArray()` là unsigned bytes cố định.** Nó trả signed two's-complement big-endian, có thể có byte dấu `0x00`.
12. **Nhầm `new BigInteger(bytes)` với `new BigInteger(1, bytes)`.** Với `0xFF`, hai cách cho -1 và 255.
13. **Dùng `toString(2)` để mong thấy N bit bù hai của số âm.** Chuỗi cơ số 2 của số âm có dấu trừ và trị tuyệt đối, không phải dãy bit w-bit cố định.
14. **Lấy mask và tưởng đầu vào vượt miền đã được xác thực.** Mask cắt bit cao; nếu dữ liệu vượt giới hạn phải báo lỗi thì hãy kiểm tra trước, không âm thầm loại thông tin.

## 13. Câu hỏi luyện tập

**1.** Vì sao `BigInteger.valueOf(5).not()` trả -6 thay vì 250? Làm sao lấy NOT của 5 trong 8 bit?

**Đáp án:** Theo bù hai vô hạn `~x = -x-1`. Dùng `BigInteger.valueOf(5).not().and(BigInteger.ONE.shiftLeft(8).subtract(BigInteger.ONE))` để lấy 250.

**2.** Tính `BigInteger.valueOf(45).and(BigInteger.valueOf(30))`, `or` và `xor`.

**Đáp án:** Lần lượt 12, 63 và 51; viết hai số ở nhị phân `101101` và `011110` để kiểm từng cột.

**3.** `BigInteger.valueOf(-3).shiftRight(1)` trả bao nhiêu, và vì sao khác `-3 / 2` trong Java?

**Đáp án:** -2, vì dịch phải số học tương đương lấy floor khi chia cho 2, trong khi chia số nguyên Java hướng về 0.

**4.** `BigInteger.valueOf(-1).testBit(100)` là true hay false? Điều đó có tạo một mảng 101 bit không?

**Đáp án:** True do các bit dấu ảo 1 kéo dài; không ngụ ý object vật lý có đúng 101 bit.

**5.** `BigInteger.valueOf(-1).bitCount()` và `bitLength()` đều cho bao nhiêu?

**Đáp án:** Đều 0 theo định nghĩa khác nhau của hai phương thức. Đây không phải số 0 về mặt giá trị.

**6.** Cùng mảng byte một phần tử `0xFF`, vì sao `new BigInteger(bytes)` và `new BigInteger(1, bytes)` khác nhau?

**Đáp án:** Constructor đầu đọc bù hai có dấu (-1), constructor sau đọc magnitude không âm với signum dương (255).

**7.** BigInteger có phép dịch phải không dấu trực tiếp như `>>>` không? Muốn thực hiện trên word 8-bit âm thì sao?

**Đáp án:** Không. Cần chọn width 8, áp mask `0xFF` để diễn giải giá trị thành 0..255, sau đó gọi `shiftRight` trên số không âm.

**8.** Khi nào phải dùng `intValueExact()` thay vì `intValue()`?

**Đáp án:** Khi việc mất các bit cao là lỗi, cần phát hiện và từ chối số BigInteger vượt miền `int` thay vì âm thầm cắt bớt.

## Tài liệu tham khảo

- [Oracle Java SE 21 — BigInteger API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html): ý nghĩa phép bit, sign extension, shift distance âm, `bitCount`, `bitLength` và `toByteArray`.
- [Java Language Specification `15.19 — Shift Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.19): quy tắc dịch bit primitive để đối chiếu.
- [Java Language Specification `15.22 — Bitwise and Logical Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.22).
- [Oracle Java SE 21 — BitSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/BitSet.html): so sánh ngữ nghĩa tập bit và mutability với số nguyên BigInteger.
