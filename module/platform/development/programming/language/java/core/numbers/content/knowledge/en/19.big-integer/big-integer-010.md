# BigInteger: bitLength, bitCount, testBit, setBit và shift trong Java

`java.math.BigInteger` biểu diễn **số nguyên có dấu với độ chính xác tùy ý**, thay vì bị giới hạn ở 32 bit (`int`) hoặc 64 bit (`long`). Không chỉ cộng, trừ và nhân số lớn, lớp này còn hỗ trợ **quan sát và chỉnh sửa bit**.

Những phương thức cần nắm:

| Phương thức | Mục đích |
| --- | --- |
| `bitLength()` | Số bit trong biểu diễn bù hai tối thiểu, **không tính bit dấu** |
| `bitCount()` | Số bit **khác bit dấu** trong biểu diễn bù hai |
| `testBit(n)` | Kiểm tra bit ở chỉ số n có bằng 1 không |
| `setBit(n)` | Trả giá trị mới có bit n được đặt thành 1 |
| `clearBit(n)` | Trả giá trị mới có bit n bằng 0 |
| `flipBit(n)` | Trả giá trị mới với bit n bị đảo |
| `shiftLeft(n)` | Dịch trái; với n dương tương đương nhân \(2^n\) |
| `shiftRight(n)` | Dịch phải số học, **mở rộng bit dấu**; với n dương tương đương làm tròn xuống khi chia \(2^n\) |

**Điểm cốt lõi:** các phép toán bit của `BigInteger` sử dụng mô hình **bù hai có mở rộng dấu vô hạn** (*infinite sign extension*). Số âm có các bit cao được xem là 1, không phải 0. Vì thế `BigInteger.bitCount(-1)` bằng **0** chứ không bằng 32 hay 64; và `shiftRight` trên số âm có thể cho kết quả khác `divide`.

## 1. Khởi tạo BigInteger và tính bất biến

```java
import java.math.BigInteger;

BigInteger a = BigInteger.valueOf(45);
BigInteger fromBinary = new BigInteger("101101", 2); // 45
BigInteger huge = new BigInteger("123456789012345678901234567890");
BigInteger zero = BigInteger.ZERO;
BigInteger one = BigInteger.ONE;
```

`BigInteger` là **immutable**: các phép toán không sửa đối tượng đang có; chúng trả về đối tượng/giá trị kết quả.

```java
BigInteger x = BigInteger.valueOf(5); // 101₂
x.setBit(1); // kết quả 7 bị bỏ qua; x vẫn là 5
System.out.println(x); // 5

x = x.setBit(1);
System.out.println(x); // 7
```

Một cách viết như `x.shiftLeft(10);` rồi bỏ qua kết quả thường là bug. Với giá trị cần cập nhật, hãy dùng `x = x.shiftLeft(10);`.

“Độ chính xác tùy ý” không có nghĩa tài nguyên vô hạn: số rất lớn có thể không đủ bộ nhớ hoặc vượt giới hạn kích thước của implementation. Các vị trí bit vẫn dùng tham số `int`.

## 2. Chỉ số bit: đếm từ phải sang trái, bắt đầu ở 0

`45` có biểu diễn nhị phân dương `101101₂`:

```text
Vị trí:  5 4 3 2 1 0
Bit:     1 0 1 1 0 1
         ^       ^ ^
       bit 5   bit 2/0
```

Bit 0 là bit thấp nhất, có trọng số \(2^0=1\). Bit 5 có trọng số \(2^5=32\). Các vị trí bật trong 45 là `0, 2, 3, 5`.

```java
BigInteger x = BigInteger.valueOf(45);
System.out.println(x.testBit(0)); // true
System.out.println(x.testBit(1)); // false
System.out.println(x.testBit(5)); // true
System.out.println(x.testBit(6)); // false
```

`toString(2)` in ký tự theo thứ tự **bit cao trước**, còn `testBit(0)` đọc **bit thấp nhất**; không lấy vị trí ký tự trong chuỗi làm chỉ số bit trực tiếp.

Với số dương, các bit cao ngoài độ dài có nghĩa là 0. Với số âm, các bit cao là **1** theo quy tắc bù hai có mở rộng dấu.

## 3. bitLength(): độ rộng không tính bit dấu

Theo Javadoc Java 17, `bitLength()` trả **số bit của biểu diễn bù hai tối thiểu trừ một bit dấu**. Với số không âm, đó chính là số chữ số nhị phân cần để biểu diễn độ lớn, ngoại trừ zero trả 0.

| Giá trị | Nhị phân | `bitLength()` |
| ---: | --- | ---: |
| 0 | 0 | 0 |
| 1 | 1 | 1 |
| 7 | 111 | 3 |
| 8 | 1000 | 4 |
| 45 | 101101 | 6 |
| 127 | 1111111 | 7 |
| 128 | 10000000 | 8 |
| \(2^{100}\) | 1 theo sau 100 zero | 101 |

```java
System.out.println(BigInteger.ZERO.bitLength()); // 0
System.out.println(BigInteger.valueOf(45).bitLength()); // 6
System.out.println(BigInteger.ONE.shiftLeft(100).bitLength()); // 101
```

Với `x > 0`, có thể hình dung kết quả bằng \(\lfloor\log_2(x)\rfloor+1\). **Không** đổi số cực lớn thành `double` rồi lấy logarit để tính số bit, bởi phép chuyển kiểu có thể mất precision hoặc thành Infinity.

### Số âm khác gì?

Số âm được hiểu theo bù hai, với vô hạn bit 1 ở phía cao. Với `x < 0`, `bitLength(x)` bằng độ dài nhị phân của `-x-1`:

| Giá trị | `bitLength()` | Gợi ý |
| ---: | ---: | --- |
| -1 | 0 | `-(-1)-1 = 0` |
| -2 | 1 | Giá trị bù là 1 |
| -3 | 2 | Giá trị bù là 2 |
| -4 | 2 | Giá trị bù là 3 |
| -8 | 3 | Giá trị bù là 7 |
| -45 | 6 | Giá trị bù là 44 |
| -128 | 7 | Vừa biểu diễn signed 8-bit |
| -129 | 8 | Không vừa biểu diễn signed 8-bit |

```java
System.out.println(BigInteger.valueOf(-1).bitLength()); // 0
System.out.println(BigInteger.valueOf(-8).bitLength()); // 3
System.out.println(BigInteger.valueOf(-45).bitLength()); // 6
```

**Không dùng `bitLength() == 0` để kiểm tra giá trị bằng 0:** `-1` cũng có bitLength bằng 0! Nếu cần kiểm tra zero, dùng `x.signum() == 0` hoặc `x.equals(BigInteger.ZERO)`.

### bitLength không tự cho số byte serializing signed

`BigInteger.valueOf(128).bitLength()` bằng 8, nhưng biểu diễn signed bù hai theo byte phải có **bit dấu 0** tách biệt với bit 7 là 1, nên `toByteArray()` có thể xuất thêm byte 0 ở đầu. Nếu truyền dữ liệu nhị phân, cần xác định signed/unsigned, số byte cố định hay biến đổi, byte order và padding. Không lấy `bitLength()/8` làm độ dài mảng byte signed một cách máy móc.

## 4. bitCount(): đếm bit khác bit dấu

Đối với số **không âm**, bit dấu là 0, nên `bitCount()` bằng số bit 1 của biểu diễn nhị phân:

```java
BigInteger x = BigInteger.valueOf(45); // 101101₂
System.out.println(x.bitCount()); // 4
```

Đối với **số âm**, các bit cao bằng 1 vô hạn. Javadoc không yêu cầu đếm vô hạn bit 1, mà yêu cầu đếm **bit khác với bit dấu** — tức số bit 0 hữu hạn trong biểu diễn bù hai của số âm.

| Giá trị | `bitLength()` | `bitCount()` | Diễn giải |
| ---: | ---: | ---: | --- |
| 0 | 0 | 0 | Không có bit 1 |
| 45 | 6 | 4 | Bốn bit 1 |
| -1 | 0 | 0 | Tất cả bit đều 1 |
| -2 | 1 | 1 | Một bit 0 khác dấu |
| -3 | 2 | 1 | Một bit 0 khác dấu |
| -4 | 2 | 2 | Hai bit 0 khác dấu |
| -8 | 3 | 3 | Ba bit 0 khác dấu |
| -45 | 6 | 3 | `~(-45) = 44 = 101100₂` có ba bit 1 |

Với `x < 0`, có thể hình dung `x.not()` là số không âm `-x-1`. Khi đó `x.bitCount()` bằng số bit 1 của số bổ sung dương này.

```java
BigInteger neg = BigInteger.valueOf(-45);
System.out.println(neg.bitCount()); // 3
System.out.println(neg.not().bitCount()); // 3
```

### Đừng nhầm Integer.bitCount với BigInteger.bitCount

```java
System.out.println(Integer.bitCount(-1)); // 32
System.out.println(BigInteger.valueOf(-1).bitCount()); // 0
```

`Integer.bitCount(int)` đếm các bit 1 trong **một từ máy 32-bit**. `BigInteger.bitCount()` đếm bit **khác sign bit** trong mô hình số nguyên tùy ý. Đây là hai hợp đồng hoàn toàn khác nhau, không phải lỗi Java.

Nếu bài toán của bạn thực sự là đếm 1 bit trong **64 bit thấp**, hãy quy định độ rộng, mask đúng 64 bit rồi dùng thuật toán đếm popcount phù hợp.

## 5. testBit(n): đọc một bit với mở rộng dấu

`testBit(n)` trả `true` nếu bit thứ n bằng 1, `false` nếu bằng 0.

```java
BigInteger x = new BigInteger("101101", 2);
System.out.println(x.testBit(0));   // true
System.out.println(x.testBit(1));   // false
System.out.println(x.testBit(5));   // true
System.out.println(x.testBit(100)); // false
```

Với số âm:

```java
BigInteger minusOne = BigInteger.ONE.negate();
System.out.println(minusOne.testBit(0));   // true
System.out.println(minusOne.testBit(100)); // true
```

**Bit cao của số âm không tự về 0.** Vì thế nếu số âm đang đại diện cho một tập các cờ bit hữu hạn, bạn rất dễ nhận nhầm cờ ở vị trí lớn là bật.

`testBit(-1)` sẽ ném `ArithmeticException` vì **địa chỉ bit âm không hợp lệ**. Quy tắc này cũng áp dụng cho `setBit(-1)`, `clearBit(-1)` và `flipBit(-1)`.

## 6. setBit, clearBit, flipBit: chỉnh sửa giá trị mới

| Phương thức | Quy tắc | Tương đương về bit |
| --- | --- | --- |
| `setBit(n)` | Đặt bit n thành 1 | OR với \(2^n\) |
| `clearBit(n)` | Xóa bit n về 0 | AND với NOT \(2^n\) |
| `flipBit(n)` | Đảo bit n | XOR với \(2^n\) |

Ví dụ `x = 45 = 101101₂`:

```java
BigInteger x = BigInteger.valueOf(45);

BigInteger set = x.setBit(1);     // 47 = 101111₂
BigInteger clear = x.clearBit(2); // 41 = 101001₂
BigInteger flip = x.flipBit(3);   // 37 = 100101₂

System.out.println(x);     // 45 (không thay đổi)
System.out.println(set);   // 47
System.out.println(clear); // 41
System.out.println(flip);  // 37
```

`setBit(n)` với bit đã là 1, hoặc `clearBit(n)` với bit đã là 0, **không đổi giá trị**. `flipBit(n)` đảo trạng thái; flip hai lần ở cùng vị trí khôi phục giá trị cũ.

### Dựng bit cao

```java
BigInteger twoTo100 = BigInteger.ZERO.setBit(100);
System.out.println(twoTo100.bitLength()); // 101
```

Kết quả là \(2^{100}\), khác hẳn mã primitive `1 << 100`: do toán tử shift của `int` dùng 5 bit thấp của số lượng dịch, `1 << 100` tương đương `1 << 4`, kết quả **16**. Với BigInteger dùng `setBit(100)` hoặc `BigInteger.ONE.shiftLeft(100)`.

### Với số âm, set/clear có thể có kết quả không trực giác

```java
BigInteger negOne = BigInteger.ONE.negate();
System.out.println(negOne.setBit(100)); // -1
System.out.println(negOne.clearBit(3)); // -9
```

Ở giá trị -1, mọi bit đều là 1; set thêm bit 100 không đổi gì. Xóa bit 3 loại trọng số 8 khỏi -1 theo hai bù, nên thành -9. Khi dùng BigInteger làm **bitset**, ưu tiên số không âm hoặc mask một độ rộng đã quy định, nếu không việc mở rộng dấu gây nhầm lẫn.

## 7. shiftLeft(n): dịch trái chính xác

Với số lượng dịch `n >= 0`, `shiftLeft(n)` tương ứng nhân với \(2^n\):

```java
BigInteger x = BigInteger.valueOf(45);
System.out.println(x.shiftLeft(3)); // 360 = 45 * 8
System.out.println(BigInteger.valueOf(-13).shiftLeft(2)); // -52
```

```text
45      =    101101₂
45 << 3 = 101101000₂ = 360
```

Không có wrap-around tại 32/64 bit như primitive `int` và `long`. Tuy nhiên kết quả dịch cực lớn có thể tiêu thụ bộ nhớ lớn hoặc vượt giới hạn implementation. `shiftLeft(0)` giữ nguyên giá trị. Đây vẫn là phép trên BigInteger immutable: không sửa object gốc.

## 8. shiftRight(n): dịch phải số học và làm tròn xuống

Với `n >= 0`, `shiftRight(n)` có ngữ nghĩa **arithmetic right shift** với mở rộng bit dấu. Về giá trị, nó bằng:

\[
\operatorname{floor}\left(\frac{x}{2^n}\right).
\]

Với số không âm:

```java
System.out.println(BigInteger.valueOf(45).shiftRight(2)); // 11
```

Nhưng với **số âm**, cần phân biệt phép chia BigInteger:

```java
BigInteger neg = BigInteger.valueOf(-13);

System.out.println(neg.shiftRight(2)); // -4
System.out.println(neg.divide(BigInteger.valueOf(4))); // -3
```

Bởi \(-13/4=-3.25\), `shiftRight(2)` làm tròn **về âm vô cực** ra -4, trong khi `divide(4)` làm tròn thương **về zero** ra -3.

| Số gốc | Phép toán | Kết quả |
| --- | --- | ---: |
| 13 | `shiftRight(2)` | 3 |
| -13 | `shiftRight(2)` | -4 |
| -13 | `divide(4)` | -3 |
| 45 | `shiftRight(2)` | 11 |
| 45 | `shiftRight(100)` | 0 |
| -13 | `shiftRight(100)` | -1 |

```java
System.out.println(BigInteger.valueOf(45).shiftRight(100)); // 0
System.out.println(BigInteger.valueOf(-13).shiftRight(100)); // -1
```

Dịch phải số âm rất xa trở thành -1 do bit dấu tiếp tục là 1. Nếu bạn cần tính **chia lấy phần nguyên về zero** đối với số âm, không thay `divide` bằng `shiftRight` trừ khi bạn đã chứng minh không có phần dư hoặc đáp ứng quy tắc floor.

## 9. Số lượng dịch âm và trường hợp lỗi

Javadoc của `shiftLeft(int)` và `shiftRight(int)` chấp nhận **khoảng dịch âm**, khi đó hướng dịch bị đảo:

| API | Ý nghĩa |
| --- | --- |
| `x.shiftLeft(3)` | Dịch trái 3 |
| `x.shiftRight(3)` | Dịch phải 3 |
| `x.shiftLeft(-3)` | Dịch phải 3 |
| `x.shiftRight(-3)` | Dịch trái 3 |

```java
BigInteger x = BigInteger.valueOf(45);
System.out.println(x.shiftLeft(-2)); // 11, cùng giá trị x.shiftRight(2)
```

**Số lượng dịch âm khác địa chỉ bit âm**:

- `x.shiftLeft(-1)` hợp lệ, đổi thành dịch phải.
- `x.testBit(-1)`, `x.setBit(-1)`, `x.clearBit(-1)` và `x.flipBit(-1)` ném `ArithmeticException`.

Đừng dựa vào `1 << 100` hoặc quy tắc mask shift count của primitive để suy ra `BigInteger.shiftLeft(100)`. Những API này khác nhau về độ rộng và ý nghĩa.

Với các chỉ số cực lớn, dù kiểu tham số là `int`, chương trình vẫn phải hạn chế theo ngân sách bộ nhớ/thời gian; không cấp phát số bit hàng tỷ chỉ vì người dùng cung cấp số n hợp lệ về mặt cú pháp.

## 10. getLowestSetBit và mask độ rộng cố định

Phương thức bổ trợ `getLowestSetBit()` tìm vị trí bit 1 thấp nhất, hoặc -1 khi giá trị bằng zero:

```java
System.out.println(BigInteger.valueOf(40).getLowestSetBit()); // 3 (40 = 101000₂)
System.out.println(BigInteger.ZERO.getLowestSetBit());       // -1
```

Với các thao tác trên **n bit thấp**, có thể tạo mask giá trị \(2^n-1\):

```java
int n = 4;
BigInteger mask = BigInteger.ONE.shiftLeft(n).subtract(BigInteger.ONE);
// mask = 15 = 1111₂

BigInteger lastFour = BigInteger.valueOf(-1).and(mask);
// 15: chỉ lấy bốn bit thấp của -1
```

Với `n == 0`, mask là zero. Ứng dụng phải bảo đảm `n >= 0` và không quá lớn. Sau khi mask, giá trị được hiểu như một **vector bit không âm**, giúp tránh nhầm lẫn từ bit dấu vô hạn của số nguyên âm.

Cần biết sự khác nhau giữa kiểu mô hình: `BigInteger` dùng khi cần **giá trị số nguyên** có dấu hoặc lũy thừa hai lớn; `java.util.BitSet` có thể phù hợp hơn khi mô hình là tập vị trí bit không âm thay đổi thường xuyên.

## 11. Chương trình Java 17+ độc lập

Tạo file **`BigIntegerBitDemo.java`**:

```java
import java.math.BigInteger;

public class BigIntegerBitDemo {
    public static void main(String[] args) {
        BigInteger x = BigInteger.valueOf(45);
        BigInteger negative = x.negate();

        System.out.println("positiveBinary=" + x.toString(2));
        System.out.println("positiveBitLength=" + x.bitLength());
        System.out.println("positiveBitCount=" + x.bitCount());
        System.out.println("negativeBinary=" + negative.toString(2));
        System.out.println("negativeBitLength=" + negative.bitLength());
        System.out.println("negativeBitCount=" + negative.bitCount());

        BigInteger minusOne = BigInteger.ONE.negate();
        System.out.println("minusOneBitLength=" + minusOne.bitLength());
        System.out.println("minusOneBitCount=" + minusOne.bitCount());
        System.out.println("minusEightBitLength=" +
                BigInteger.valueOf(-8).bitLength());
        System.out.println("minusEightBitCount=" +
                BigInteger.valueOf(-8).bitCount());

        System.out.println("testBit0=" + x.testBit(0));
        System.out.println("testBit1=" + x.testBit(1));
        System.out.println("testBit5=" + x.testBit(5));
        System.out.println("highNegativeBit=" + minusOne.testBit(100));

        System.out.println("setBit1=" + x.setBit(1));
        System.out.println("clearBit2=" + x.clearBit(2));
        System.out.println("flipBit3=" + x.flipBit(3));
        System.out.println("originalUnchanged=" + x);
        System.out.println("highBitLength=" +
                BigInteger.ZERO.setBit(100).bitLength());

        System.out.println("shiftLeftThree=" + x.shiftLeft(3));
        System.out.println("shiftRightTwo=" + x.shiftRight(2));
        BigInteger minusThirteen = BigInteger.valueOf(-13);
        System.out.println("negativeShiftRight=" +
                minusThirteen.shiftRight(2));
        System.out.println("negativeDivide=" +
                minusThirteen.divide(BigInteger.valueOf(4)));
        System.out.println("negativeShiftDistance=" + x.shiftLeft(-2));
        System.out.println("farPositiveShift=" + x.shiftRight(100));
        System.out.println("farNegativeShift=" +
                minusThirteen.shiftRight(100));

        System.out.println("lowestSetBit40=" +
                BigInteger.valueOf(40).getLowestSetBit());
        System.out.println("lowestSetBitZero=" +
                BigInteger.ZERO.getLowestSetBit());
        System.out.println("negativeClearBit3=" + minusOne.clearBit(3));
        System.out.println("negativeBit3AfterClear=" +
                minusOne.clearBit(3).testBit(3));

        try {
            x.testBit(-1);
            System.out.println("negativeBitIndex=missed");
        } catch (ArithmeticException ex) {
            System.out.println("negativeBitIndex=ArithmeticException");
        }

        BigInteger mask = BigInteger.ONE.shiftLeft(4)
                .subtract(BigInteger.ONE);
        System.out.println("lowFourMask=" + mask);
        System.out.println("maskedNegative=" +
                BigInteger.valueOf(-1).and(mask));
        System.out.println("primitiveShift100=" + (1 << 100));
    }
}
```

Biên dịch và chạy:

```bash
javac BigIntegerBitDemo.java
java BigIntegerBitDemo
```

Output:

```text
positiveBinary=101101
positiveBitLength=6
positiveBitCount=4
negativeBinary=-101101
negativeBitLength=6
negativeBitCount=3
minusOneBitLength=0
minusOneBitCount=0
minusEightBitLength=3
minusEightBitCount=3
testBit0=true
testBit1=false
testBit5=true
highNegativeBit=true
setBit1=47
clearBit2=41
flipBit3=37
originalUnchanged=45
highBitLength=101
shiftLeftThree=360
shiftRightTwo=11
negativeShiftRight=-4
negativeDivide=-3
negativeShiftDistance=11
farPositiveShift=0
farNegativeShift=-1
lowestSetBit40=3
lowestSetBitZero=-1
negativeClearBit3=-9
negativeBit3AfterClear=false
negativeBitIndex=ArithmeticException
lowFourMask=15
maskedNegative=15
primitiveShift100=16
```

Các dòng quan trọng:

- `negativeBitCount=3` và `minusOneBitCount=0`: `bitCount` ở số âm đếm bit **khác dấu**, không đếm bit 1 trong 32/64 bit.
- `highNegativeBit=true`: bit 100 của -1 bằng 1 vì **mở rộng dấu**.
- `negativeShiftRight=-4` so với `negativeDivide=-3`: dịch phải dùng **floor**, phép chia nguyên dùng **truncate toward zero**.
- `primitiveShift100=16` khác việc đặt bit 100 trong `BigInteger`.
- `negativeBitIndex=ArithmeticException`: chỉ số bit âm bị từ chối, dù **khoảng dịch âm** được cho phép.

## 12. Lỗi thường gặp và checklist

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “`bitCount(-1)` có vô hạn bit 1 nên trả vô hạn.” | Javadoc đếm số bit **khác sign bit**; kết quả là 0. |
| “`BigInteger.bitCount(-1)` giống `Integer.bitCount(-1)`.” | Sai: kết quả tương ứng là 0 và 32. |
| “`bitLength() == 0` chỉ xảy ra với zero.” | Sai: -1 cũng trả 0. |
| “`toString(2)` của số âm in toàn bộ bù hai.” | Sai: in dấu trừ và độ lớn, không in sign extension vô hạn. |
| “Bit 100 của -1 phải là 0 vì số -1 nhỏ.” | Sai: số âm có bit cao là 1. |
| “`setBit(n)` thay đổi object hiện tại.” | Sai: BigInteger immutable; lưu kết quả trả về. |
| “`1 << 100` tạo bit 100.” | Sai: `int` che bớt số lượng dịch; kết quả 16. |
| “`shiftRight(2)` và `divide(4)` luôn bằng nhau.” | Sai khi số âm và có phần dư. |
| “`shiftLeft(-2)` sẽ ném exception.” | Sai: khoảng dịch âm đảo hướng; **bit index âm** mới bị từ chối. |
| “Dịch phải số âm đủ xa cho 0.” | Sai: có thể cho -1 do sign extension. |
| “BigInteger không bao giờ hết khả năng lưu.” | Vẫn giới hạn bộ nhớ và kích thước đối tượng. |
| “`bitLength()/8` cho số byte signed cần thiết.” | Cần xét sign, padding và encoding. |

Checklist:

1. **Xác định đầu vào có âm hay không:** nếu dùng làm cờ bit, cân nhắc mask độ rộng hoặc quy ước không âm.
2. **Đếm bit đúng nghĩa:** `bitLength` đo độ dài không tính sign; `bitCount` đếm bit khác sign.
3. **Kiểm tra chỉ số:** `testBit`/`setBit`/`clearBit`/`flipBit` cần n không âm.
4. **Nhớ bất biến:** dùng `x = x.setBit(n)` thay vì bỏ kết quả.
5. **Dùng BigInteger để dựng bit lớn:** `BigInteger.ONE.shiftLeft(n)`, không phải `1 << n`.
6. **Với số âm, phân biệt floor và truncate:** `shiftRight` không thay được `divide` trong mọi trường hợp.
7. **Giới hạn tài nguyên:** n lớn có thể tiêu tốn bộ nhớ dù cú pháp hợp lệ.
8. **Serialize theo contract:** chọn signed/unsigned, endian, độ rộng và leading padding minh bạch.

**Ghi nhớ:** Những phương thức bit của `BigInteger` đều dựa trên **số nguyên có dấu bù hai, mở rộng bit dấu vô hạn**. Phần lớn hiểu lầm xuất phát từ việc áp dụng trực giác về một từ máy `int`/`long` có kích thước cố định sang số nguyên tùy ý.

Tài liệu chuẩn: [Oracle Java 17 BigInteger Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html).