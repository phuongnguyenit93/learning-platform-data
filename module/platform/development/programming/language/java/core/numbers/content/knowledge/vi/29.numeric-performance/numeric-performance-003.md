# Chi phí số học BigInteger theo độ dài toán hạng

## 1. Vì sao cùng một phép toán nhưng thời gian chạy khác nhau?

`int` và `long` có độ rộng cố định (32 và 64 bit); còn `java.math.BigInteger` lưu số nguyên có độ chính xác tùy ý, miễn là đủ bộ nhớ và nằm trong giới hạn biểu diễn của thư viện. Hai lời gọi:

~~~java
BigInteger small = BigInteger.valueOf(123);
BigInteger large = BigInteger.ONE.shiftLeft(1_000_000);
BigInteger a = small.multiply(small);
BigInteger b = large.multiply(large);
~~~

cùng gọi `multiply` nhưng **lượng dữ liệu phải xử lý hoàn toàn khác nhau**. Số thứ nhất chỉ cần ít bit, số thứ hai có hơn một triệu bit; tích của số thứ hai có khoảng hai triệu bit. Ngoài phép nhân, JVM còn cần lưu và quản lý dữ liệu kết quả, vùng tạm, cấp phát và thu gom rác.

Do vậy “mỗi phép cộng/nhân/chia BigInteger tốn O(1)” là sai nếu đầu vào có độ dài thay đổi. Chi phí phụ thuộc vào **số bit hoặc số từ (limb) biểu diễn độ lớn toán hạng**, loại phép toán, hình dạng toán hạng (một bên ngắn hay hai bên dài), thuật toán được chọn và môi trường chạy.

**Mục tiêu:** biết ước lượng bậc tăng chi phí theo độ dài, phân biệt số bit với giá trị số học, tránh kết quả trung gian phình to, và đo bằng benchmark phù hợp trước khi tối ưu.

## 2. Độ dài toán hạng: bitLength và số limb

Với số nguyên dương `x`, `x.bitLength()` là số bit tối thiểu cần để biểu diễn độ lớn theo nhị phân. Ví dụ:

| Giá trị | Dạng nhị phân (rút gọn) | `bitLength()` |
|---|---|---:|
| `0` | `0` | 0 |
| `1` | `1` | 1 |
| `7` | `111` | 3 |
| `8` | `1000` | 4 |
| `255` | `11111111` | 8 |
| `256` | `100000000` | 9 |

Với **số âm**, `BigInteger.bitLength()` có định nghĩa phù hợp biểu diễn two's complement, không đơn giản luôn là số bit của trị tuyệt đối. Chẳng hạn `BigInteger.valueOf(-1).bitLength() == 0`, trong khi `abs().bitLength() == 1`. Khi phân tích **chi phí phụ thuộc độ lớn toán hạng**, dùng `x.abs().bitLength()` cho cả số âm và dương nếu đang muốn đo số bit của trị tuyệt đối.

Trong OpenJDK, độ lớn BigInteger được giữ bằng các nhóm từ máy (limb, hiện thường là các phần tử `int` 32 bit) cùng dấu. Với giá trị khác 0 và `n` bit độ lớn, số limb xấp xỉ:

~~~text
L = ceil(n / 32)
~~~

Đây là **mô hình giải thích chi phí trên triển khai OpenJDK**, không phải hợp đồng công khai yêu cầu mọi JVM phải lưu bằng mảng `int[]` 32 bit. Thuật toán có thể làm việc với dữ liệu tạm, mảng khác và các đường xử lý riêng cho trường hợp đặc biệt.

Điểm quan trọng là phân biệt hai thước đo:

- **Giá trị số học:** `10^1000` lớn hơn `10^100` theo phép so sánh.
- **Kích thước biểu diễn:** `10^1000` cần xấp xỉ `1000 × log2(10) ≈ 3322` bit. Thuật toán xử lý dữ liệu theo độ dài biểu diễn này.

Một số có một triệu chữ số thập phân không chỉ “lớn hơn” số có mười chữ số; nó đòi nhiều thao tác trên các từ máy và bộ nhớ hơn rất nhiều.

## 3. Ước lượng độ phức tạp theo số từ máy

Đặt `n`, `m` là số limb (hoặc tương đương số bit theo hệ số hằng) của hai toán hạng, với `n ≥ m ≥ 1`. Bảng sau mô tả **bậc chi phí điển hình**, không hứa hẹn thời gian chính xác của mọi phiên bản JDK:

| Phép toán | Quy mô chi phí thường gặp | Điều cần nhớ |
|---|---|---|
| `signum()`, một vài truy vấn metadata | Thường O(1) | Phụ thuộc dữ liệu đã lưu/được cache |
| `compareTo(b)`, `equals(b)` | Tối đa O(n) trong trường hợp kích thước tương đương | Có thể kết luận sớm nhờ dấu, độ dài hoặc limb khác đầu tiên |
| `add(b)`, `subtract(b)` | O(max(n, m)) trong trường hợp thông thường | Phải xử lý carry/borrow qua các limb |
| `negate()`, `abs()` | Có đường xử lý nhẹ; không suy ra luôn sao chép toàn bộ | BigInteger bất biến, tối ưu nội bộ tùy triển khai |
| `shiftLeft(k)`, `shiftRight(k)` | Phụ thuộc số limb của đầu vào/kết quả và lượng dịch | Dịch trái lớn có thể tạo số và vùng nhớ rất lớn |
| `and`, `or`, `xor`, `not` | Thường tỉ lệ độ dài dữ liệu cần xử lý | Ngữ nghĩa bitwise với dấu âm là two's complement |
| `multiply(b)` kiểu nhân từng chữ số | O(nm), nếu n≈m thì O(n²) | Thuật toán nhanh hơn có thể được chọn cho số lớn |
| `pow(exponent)` | Phụ thuộc exponent, độ dài kết quả và chi phí nhân | Kết quả có thể tăng rất nhanh |
| `divide`, `remainder` | Phụ thuộc cả số bị chia và số chia; thường nặng hơn phép cộng | Có nhiều thuật toán và trường hợp đặc biệt |
| `gcd`, `modInverse` | Nhiều bước chia/biến đổi tùy giá trị | Không cố định chỉ bởi một độ dài chung |
| `modPow` | Phụ thuộc độ dài modulus, exponent và số phép nhân/rút gọn môđun | Tránh tạo trực tiếp `base.pow(e)` cực lớn |

Đây là các quy luật để **xác định điểm nóng tiềm năng**, không phải bảng đo latency. Đầu vào có cấu trúc đặc biệt (0, 1, lũy thừa của 2, một toán hạng rất ngắn) và đường tối ưu của JDK có thể làm kết quả thực tế khác mô hình trung bình.

**Phân biệt n và m:** nhân một số 4096 bit với số 8 bit có bài toán khác nhân hai số đều 4096 bit. Không đánh đồng cả hai là “phép nhân số 4096 bit” mà quên độ dài toán hạng thứ hai.

## 4. Cộng và trừ: gần tuyến tính theo độ dài

Cộng hai số lớn có thể được hình dung như cộng theo từng limb, mang theo bit nhớ:

~~~text
A = [a0, a1, a2, ..., an-1]
B = [b0, b1, b2, ..., bm-1]
=> cộng các limb tương ứng và truyền carry
~~~

Nếu hai số có khoảng `n` limb, trường hợp thông thường tốn công việc tuyến tính theo `n`. Các tình huống có carry chạy dài (ví dụ cộng 1 vào số toàn bit 1) cần chạm tới nhiều limb.

Ví dụ:

~~~java
BigInteger allOnes = BigInteger.ONE.shiftLeft(256)
        .subtract(BigInteger.ONE);
BigInteger nextPowerOfTwo = allOnes.add(BigInteger.ONE);

System.out.println(allOnes.bitLength());      // 256
System.out.println(nextPowerOfTwo.bitLength()); // 257
~~~

Dù chỉ cộng **1**, kết quả thay đổi 256 bit thấp và tạo thêm một bit ở đầu. Không thể suy từ toán hạng `BigInteger.ONE` rất ngắn rằng phép cộng luôn có chi phí hằng số, hoặc số kết quả không tăng độ dài.

Với các phép `add/subtract` lặp hàng triệu lần trên số ngày càng lớn, mỗi bước có thể đắt hơn bước trước, dù vòng lặp không đổi câu lệnh Java. Nếu chỉ cần đếm giá trị nằm trong `long`, `long` thường đơn giản và nhẹ hơn; chỉ dùng `BigInteger` khi phạm vi số thực sự đòi hỏi.

## 5. Nhân: từ O(n²) đến Karatsuba và Toom-Cook

Nhân theo cách phổ thông từng limb của số thứ nhất với từng limb của số thứ hai có chi phí **O(nm)**; khi hai độ dài xấp xỉ nhau là **O(n²)**. Nếu tăng gấp đôi số limb của cả hai toán hạng, mô hình nhân phổ thông có thể tăng số phép xử lý cặp limb khoảng bốn lần. Đây là **ước lượng bậc độ phức tạp**, không khẳng định runtime thực tế luôn đúng 4×.

Các thuật toán cho số lớn có thể giảm số phép nhân con:

- **Karatsuba:** tách đôi toán hạng, dùng ba tích con thay vì bốn, độ phức tạp với toán hạng cân bằng xấp xỉ **O(n^log₂3) ≈ O(n^1.585)**.
- **Toom-Cook ba phần:** có thể đạt khoảng **O(n^log₃5) ≈ O(n^1.465)** cho cách phân chia phù hợp.
- **Nhân phổ thông:** có ít overhead, thường có lợi cho số nhỏ.

OpenJDK 17 có các đường xử lý nhân phổ thông, Karatsuba và Toom-Cook, cùng ngưỡng thực nghiệm để lựa chọn. **Ngưỡng và cách lựa chọn là chi tiết triển khai**, có thể thay đổi theo phiên bản và distribution JDK; không thiết kế tính đúng của chương trình dựa vào một ngưỡng hard-code hoặc đảm bảo 4×/2× khi tăng số bit.

Với hai số dương khác 0 có độ dài bit `a` và `b`, tích có bit length thuộc khoảng:

~~~text
a + b - 1 <= product.bitLength() <= a + b
~~~

Ví dụ nhân số 256 bit với số 257 bit thường cần tới 513 bit; đó là **độ dài kết quả**, không phải số phép toán CPU. Ngay cả khi thuật toán nhân nhanh hơn, bộ nhớ để chứa kết quả vẫn tăng theo độ dài của tích.

### Bình phương không nhất thiết tốn như nhân hai toán hạng độc lập

`x.multiply(x)` có thể được tối ưu bởi thuật toán bình phương chuyên biệt trong OpenJDK. Vì nhiều tích con trùng nhau khi hai toán hạng giống nhau, mã thư viện có thể giảm overhead. Tuy nhiên, không viết một giả định về tỷ lệ tốc độ không được đo trên JDK triển khai thực tế. Kết quả `x.pow(2)` và `x.multiply(x)` giống nhau về mặt số học, nhưng đường code, trường hợp đặc biệt và chi phí có thể khác.

## 6. Chia, remainder và gcd: không thể đánh giá chỉ bằng số bit số bị chia

Chia một `BigInteger` lớn cho số nhỏ khác chia cho một số gần bằng độ lớn của nó. Thuật toán chia theo limb có thể phải ước lượng thương, nhân trừ và sửa phần dư nhiều lần. OpenJDK 17 có các đường xử lý chia kiểu truyền thống và Burnikel–Ziegler cho trường hợp toán hạng đủ dài.

Với:

~~~java
BigInteger quotient = dividend.divide(divisor);
BigInteger remainder = dividend.remainder(divisor);
~~~

hai phép gọi độc lập có thể gây công việc trùng lặp. Khi cần **cả thương và dư**, dùng:

~~~java
BigInteger[] qr = dividend.divideAndRemainder(divisor);
BigInteger quotient = qr[0];
BigInteger remainder = qr[1];
~~~

Đây là đoạn dùng bên trong phương thức, với `dividend`/`divisor` là `BigInteger` và divisor khác 0. `divideAndRemainder` cho phép thư viện tính chung hai kết quả, có thể giảm công việc so với hai lời gọi độc lập; không suy ra luôn nhanh hơn bao nhiêu phần trăm.

Một số điều cần nhớ:

1. Chia cho **0** ném `ArithmeticException`; tính hiệu năng không có ý nghĩa khi tiền điều kiện không được thỏa.
2. `divide` chia số nguyên, làm tròn thương **về 0**; `remainder` giữ dấu tương ứng với số bị chia (khác `mod`, vốn yêu cầu môđun dương và cho dư không âm).
3. Nếu divisor có độ dài lớn hơn dividend về trị tuyệt đối thì thương nguyên bằng 0; có thể là đường xử lý rẻ.
4. `gcd` thường liên quan nhiều bước biến đổi theo các giá trị trung gian. Số bit đầu vào quan trọng, nhưng cấu trúc số và số vòng thuật toán cũng ảnh hưởng runtime.

Không thay `divide(x)` bằng `shiftRight(k)` trừ khi **bạn đã chứng minh** x là lũy thừa 2 và kiểm tra ngữ nghĩa số âm: `shiftRight` mang hành vi dịch số có dấu, trong khi `divide` làm tròn về 0. Ví dụ `-3 >> 1` là `-2`, còn `-3 / 2` là `-1`.

## 7. Lũy thừa làm độ dài kết quả bùng nổ

Nếu `a` có độ lớn lớn hơn 1, phép `a.pow(e)` có thể làm số bit kết quả tăng theo **e × log₂|a|**. Với trường hợp `a = 2^k`, kết quả là `2^(ke)`, có bit length `ke + 1`. Một số phép nhân có thể sử dụng lũy thừa bằng bình phương liên tiếp, nhưng **không thể bỏ qua kích thước kết quả khổng lồ** nếu mục đích là giữ toàn bộ lũy thừa.

Ví dụ:

~~~java
BigInteger two = BigInteger.TWO;
BigInteger huge = two.pow(1_000_000);
System.out.println(huge.bitLength()); // 1000001
~~~

Số có khoảng một triệu bit này yêu cầu chừng 125 KB chỉ để chứa các bit độ lớn tối thiểu, chưa kể mảng, object, kết quả tạm và việc cấp phát/copy. Đây là ước lượng dung lượng bit, **không phải kích thước chính xác trên heap**.

Với bài toán chỉ cần **phần dư** của `base^exponent mod modulus`, tránh xây dựng toàn bộ `base.pow(exponent)` rồi `mod(modulus)`. Dùng:

~~~java
BigInteger result = base.modPow(exponent, modulus);
~~~

`modPow` tính lũy thừa môđun qua các bước tối ưu, trong đó giá trị trung gian được giảm theo modulus thay vì nhất thiết phải chứa toàn bộ số mũ khổng lồ. Chi phí vẫn phụ thuộc lớn vào số bit của modulus, số bit exponent và cơ chế nhân/rút gọn môđun. Không nói `modPow` là O(1) chỉ vì **độ dài kết quả** bị chặn bởi modulus.

Ví dụ toán học với exponent dương và modulus dương:

~~~java
BigInteger base = BigInteger.TWO;
BigInteger modulus = BigInteger.valueOf(97);
BigInteger e = BigInteger.valueOf(1_000);

boolean same = base.modPow(e, modulus)
        .equals(base.pow(1_000).mod(modulus));
System.out.println(same); // true
~~~

Đoạn này chỉ để đối chiếu kết quả với exponent **nhỏ đủ để minh họa**. Trong chương trình thật nếu exponent cực lớn, việc tạo `pow` rồi lấy `mod` có thể tiêu tốn thời gian/bộ nhớ nghiêm trọng.

## 8. Chương trình Java 17+ quan sát kích thước kết quả

Lưu thành **`BigIntegerLengthDemo.java`**:

~~~java
import java.math.BigInteger;

public class BigIntegerLengthDemo {
    private static int magnitudeBits(BigInteger x) {
        return x.abs().bitLength();
    }

    public static void main(String[] args) {
        BigInteger one = BigInteger.ONE;
        BigInteger a = one.shiftLeft(256).subtract(one);
        BigInteger b = one.shiftLeft(257).subtract(one);

        System.out.println("a bits = " + magnitudeBits(a));
        System.out.println("b bits = " + magnitudeBits(b));
        System.out.println("a+a bits = " + magnitudeBits(a.add(a)));
        System.out.println("a*b bits = " + magnitudeBits(a.multiply(b)));
        System.out.println("a^3 bits = " + magnitudeBits(a.pow(3)));

        BigInteger modulus = BigInteger.valueOf(97);
        BigInteger base = BigInteger.valueOf(2);
        BigInteger exponent = BigInteger.valueOf(1_000);
        boolean sameModularResult = base.modPow(exponent, modulus)
                .equals(base.pow(1_000).mod(modulus));
        System.out.println("modPow matches = " + sameModularResult);

        System.out.println("negative -1 magnitude bits = "
                + magnitudeBits(BigInteger.valueOf(-1)));
        System.out.println("negative -1 bitLength = "
                + BigInteger.valueOf(-1).bitLength());
    }
}
~~~

Chạy:

~~~bash
javac BigIntegerLengthDemo.java
java BigIntegerLengthDemo
~~~

Stdout đã kiểm chứng:

~~~text
a bits = 256
b bits = 257
a+a bits = 257
a*b bits = 513
a^3 bits = 768
modPow matches = true
negative -1 magnitude bits = 1
negative -1 bitLength = 0
~~~

Vì `a = 2^256 - 1` và `b = 2^257 - 1`, tích có bit length 513. Bình phương/cubing số gần lũy thừa 2 cũng cho kết quả có số bit tăng gần tuyến tính theo số mũ. Chương trình **không đo thời gian**; nó minh họa kích thước dữ liệu mà các thuật toán số học phải xử lý.

## 9. Immutable BigInteger, allocation và memory pressure

`BigInteger` là bất biến. Phần lớn phép toán sinh giá trị kết quả mới; JVM có thể sử dụng lại hằng, trả lại cùng tham chiếu trong một số nhánh hoặc tối ưu cấp phát, nên đừng khẳng định **mỗi lời gọi chắc chắn cấp phát đúng một đối tượng mới**. Dù vậy, vòng lặp tạo giá trị lớn liên tục có thể dẫn đến:

- Nhiều vùng dữ liệu kết quả và mảng limb tạm.
- Sao chép/ghi các limb dù phép toán nhìn như một dòng Java.
- Allocation rate tăng, heap chiếm nhiều chỗ hơn và tần suất GC tăng.
- Áp lực cache/băng thông bộ nhớ khi toán hạng dài.
- Sự chênh lệch thời gian do JIT compiler, CPU, GC và phân phối kích thước đầu vào.

Ví dụ cộng dồn:

~~~java
BigInteger sum = BigInteger.ZERO;
for (int i = 1; i <= 1_000_000; i++) {
    sum = sum.add(BigInteger.valueOf(i));
}
~~~

Đây là đoạn minh họa trong phương thức (import `java.math.BigInteger`). `sum` được cập nhật qua nhiều giá trị bất biến, có thể tạo nhiều object tạm. Nếu tổng bảo đảm vừa `long`, cộng bằng `long` rồi chuyển thành BigInteger ở biên có thể giảm chi phí; **chỉ được làm vậy khi chứng minh không overflow** và yêu cầu domain cho phép.

Ví dụ khi chỉ đếm số lượng request (không cần số nguyên vô hạn), `long` hoặc primitive/atomic tương ứng có thể phù hợp hơn. Khi tính giai thừa, tổ hợp hoặc mật mã nơi kích thước số vượt `long`, BigInteger có giá trị vì giữ kết quả chính xác, nhưng phải kiểm soát số bước và kích thước trung gian.

### Tránh chuyển đổi chuỗi trong vòng lặp nóng

~~~java
// Không nên parse lại cùng một hằng thập phân trong hot loop:
BigInteger a = new BigInteger("123456789012345678901234567890");

// Khi đối số vừa long, biểu diễn đơn giản hơn:
BigInteger b = BigInteger.valueOf(42L);
~~~

Chuyển từ chuỗi thập phân dài sang số nhị phân/limb có chi phí xử lý dữ liệu. Chuyển ngược qua `toString()` cũng tốn thời gian và có thể tạo chuỗi cực lớn. Đừng dùng `toString().length()` để “đo độ lớn” bên trong vòng lặp; dùng `abs().bitLength()` khi cần thước đo nhị phân, và tránh gọi các thao tác đo không cần thiết trong đoạn code tính toán hiệu năng.

Không để `System.out.println(hugeBigInteger)` trở thành một phần của benchmark nhân/chia: lúc đó thời gian format và ghi console có thể áp đảo phép toán mà bạn định đo.

## 10. Chi phí biểu diễn kết quả và giữ trung gian ở độ dài hợp lý

Một số quy tắc gần đúng khi toán hạng dương:

| Phép toán | Độ dài kết quả |
|---|---|
| `a.add(b)` | Tối đa `max(bits(a), bits(b)) + 1` |
| `a.subtract(b)` | Trị tuyệt đối kết quả có thể nhỏ hoặc gần bằng toán hạng lớn nhất |
| `a.multiply(b)` với a,b khác 0 | Từ `bits(a) + bits(b) - 1` đến `bits(a) + bits(b)` |
| `a.shiftLeft(k)` với a dương khác 0, k≥0 | `bits(a) + k` |
| `a.mod(m)` với m dương | Kết quả từ 0 đến `m - 1`, nên bit length không vượt `bits(m)` |
| `a.pow(e)` với e không âm | Có thể có độ dài tăng tỉ lệ với e |

Các công thức theo `bits()` ở bảng dùng **độ dài bit của trị tuyệt đối**. Trường hợp 0, 1, số âm và các tối ưu đặc biệt cần xét riêng. `BigInteger` có giới hạn triển khai và bộ nhớ thực tế; cụm “arbitrary precision” không có nghĩa cho phép cấp phát vô hạn.

Khi xử lý nhiều bước, cần nghĩ tới **giá trị trung gian lớn nhất**, không chỉ giá trị đầu vào/đầu ra. Ví dụ để tính `(a × b) mod m`, nếu `a` và `b` đều gần độ dài modulus, một tích trung gian có thể dài gần gấp đôi modulus trước khi giảm. Các thuật toán modular chuyên dụng có thể sử dụng cách biểu diễn và giảm trung gian hiệu quả hơn cho nhiều phép lặp.

Khi số bit tăng theo từng vòng lặp, tổng chi phí của cả quá trình là tổng chi phí từng bước:

~~~text
TotalCost = Cost(size_1) + Cost(size_2) + ... + Cost(size_k)
~~~

Không chỉ lấy số vòng lặp nhân với một hằng số nếu kích thước toán hạng thay đổi. Ví dụ giai thừa `n!` tăng số chữ số theo n; dùng cùng một phép nhân nhưng độ dài một toán hạng tiếp tục tăng theo n.

## 11. Đo hiệu năng thực tế: JMH và những bẫy benchmark

Phân tích O(n) và O(n²) là mô hình bậc tăng, **không thay thế đo trên tải thực tế**. JVM có JIT, tối ưu nội tuyến, escape analysis, cấp phát theo vùng, GC và các đường xử lý nội bộ dựa vào kích thước. Để so sánh đáng tin, nên dùng **Java Microbenchmark Harness (JMH)** với fork, warmup, measurement và `Blackhole` đúng cách.

Một thiết kế benchmark tốt:

1. **Giữ cả hai toán hạng:** ví dụ 64/64, 256/256, 1024/1024, 4096/4096 bit; thêm 4096/64 để so sánh trường hợp một toán hạng ngắn.
2. **Kiểm soát nội dung:** các số cùng bit length nhưng có cấu trúc rất khác (toàn bit 1, số ngẫu nhiên, lũy thừa 2) có thể chạy theo đường xử lý khác nhau. Không lấy một số 0 hoặc 1 để thay cho số lớn ngẫu nhiên.
3. **Tách từng phép toán:** benchmark add, multiply, divide, modPow ở các nhóm riêng; không để dựng BigInteger, parse chuỗi, random, format số hay ghi console trong phần đo nếu mục tiêu là phép toán.
4. **Không cho JIT loại bỏ kết quả:** tiêu thụ kết quả qua `Blackhole` hoặc sink được thiết kế phù hợp; không viết vòng lặp với kết quả không dùng.
5. **Tránh phụ thuộc vòng trước:** nếu mỗi iteration cập nhật kết quả ngày càng dài, bạn đang đo một **thuật toán tăng kích thước**, không so chi phí một phép nhân của các kích thước cố định. Cả hai loại đều có ích nhưng trả lời câu hỏi khác nhau.
6. **Ghi môi trường:** phiên bản JDK, CPU, heap, GC, JMH version, fork/iteration, số phép đo, phân phối input, nguồn dữ liệu và ngưỡng thuật toán.
7. **Báo kết quả có biến thiên:** ns/op hoặc ops/s cùng sai số/độ phân tán; không dùng một lần `System.nanoTime()` để cam kết “phép nhân số 4096 bit mất đúng X ns”.

### Ví dụ JMH minh họa ý tưởng

Đây là **đoạn benchmark cần JMH dependency và JMH annotation processor**, không thể biên dịch chỉ với JDK nếu chưa thêm JMH vào dự án. Lưu trong file `BigIntegerMultiplyBenchmark.java` thuộc mã benchmark của dự án:

~~~java
import java.math.BigInteger;
import java.util.Random;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
public class BigIntegerMultiplyBenchmark {
    @Param({"128", "512", "2048", "4096"})
    public int bits;

    private BigInteger left;
    private BigInteger right;

    @Setup(Level.Trial)
    public void setup() {
        Random random = new Random(12345L);
        left = new BigInteger(bits, random).setBit(bits - 1);
        right = new BigInteger(bits, random).setBit(bits - 1);
    }

    @Benchmark
    public void multiply(Blackhole blackhole) {
        blackhole.consume(left.multiply(right));
    }
}
~~~

`@Param` khiến JMH chạy các cấu hình kích thước riêng, `@Setup` loại việc sinh dữ liệu khỏi đoạn đo, và `Blackhole` tiêu thụ kết quả. Với kích thước khác nhau, throughput có thể thay đổi không trơn vì JDK đổi chiến lược thuật toán, tối ưu CPU/JVM và hoạt động GC. Đây chỉ là một benchmark minh họa **nhân hai toán hạng có cùng bit length**, chưa bao phủ chia, modular exponentiation hay phép nhân lệch kích thước. Không so sánh JDK/CPU bằng một số đo lấy từ máy khác.

Để benchmark JMH thật sự chạy, dự án cần cấu hình thư viện `org.openjdk.jmh:jmh-core` và annotation processor `jmh-generator-annprocess`, sau đó chạy bằng launcher JMH phù hợp build tool. Không khẳng định lớp trên chạy độc lập bằng `javac` chỉ với JDK tiêu chuẩn.

## 12. Chiến lược tối ưu theo đúng nguồn chi phí

**Giữ phạm vi giá trị thực sự cần thiết.** Nếu yêu cầu chỉ tới `long`, dùng primitive khi có kiểm tra overflow. Nếu nghiệp vụ có thể vượt `long`, dùng BigInteger; đừng đổi sang `double` để tăng tốc khi cần số nguyên chính xác vì `double` không biểu diễn chính xác mọi số nguyên lớn.

**Ưu tiên thuật toán thay vì mẹo cục bộ.** Tránh triển khai nhân BigInteger lặp quá nhiều khi có biểu thức toán học tốt hơn: ví dụ thuật toán lũy thừa theo bình phương, divide-and-conquer, tính tổ hợp có khử ước chung, giảm sớm qua modulus khi đúng về mặt toán học. Tuy nhiên, giữ đúng semantics phép toán (đặc biệt số âm, chia nguyên, dư và overflow nếu chuyển kiểu).

**Tái sử dụng hằng và tránh parse thừa.** Dùng `BigInteger.ZERO`, `ONE`, `TWO` và `valueOf(long)`; xây dữ liệu lớn một lần ngoài hot loop nếu nó không đổi. Tránh chuyển qua chuỗi khi thao tác toán học có API trực tiếp.

**Đọc đúng chi phí của số trung gian.** Bài toán đầu ra ngắn không đồng nghĩa đường tính tự động rẻ; `base.pow(hugeExponent).mod(modulus)` có thể tạo kết quả khổng lồ trước khi rút gọn, trong khi `modPow` là cách thiết kế đúng cho lũy thừa môđun.

**Tách ứng dụng đồng thời và thuật toán số học.** Nếu nhiều thread cùng cập nhật một `BigInteger` qua biến chia sẻ, tính immutable của đối tượng không khiến thao tác `current = current.add(ONE)` trở thành atomic. Cần đồng bộ hoặc thao tác atomic với cập nhật điều kiện phù hợp; chi phí tranh chấp lock/GC và việc tăng bit length đều ảnh hưởng tổng throughput.

**Chú ý an toàn tài nguyên.** Với dữ liệu bên ngoài, giới hạn độ dài input/bit, số vòng lặp, exponent và các phép toán có thể làm kết quả tăng cực nhanh. Với dịch trái số bit rất lớn, lũy thừa lớn hoặc chuỗi decimal hàng triệu ký tự, nguy cơ dùng quá nhiều bộ nhớ/time không phải do kết quả sai. Kiểm tra bounds trước khi cấp phát và dùng timeout/quota ở cấp hệ thống nếu cần.

**Đối với mật mã:** BigInteger phục vụ số học chính xác nhưng thời gian của nhiều phép toán phụ thuộc kích thước và nội dung toán hạng; không coi các phép toán thông thường là constant-time. Khi xử lý bí mật, chọn thư viện/triển khai mật mã đã được xem xét về timing side channel và các yêu cầu an toàn khác; hiệu năng đơn thuần không đủ làm tiêu chí.

## 13. Lỗi phổ biến

- **Coi BigInteger như int có độ dài vô hạn nhưng chi phí O(1):** toán hạng lớn làm tăng số limb và cấp phát.
- **So thời gian với input 0/1 rồi suy ra cho mọi số dài:** giá trị đặc biệt có đường tối ưu khác.
- **Cho rằng nhân luôn O(n²):** đó là nhân phổ thông; JDK có thể đổi sang thuật toán nhanh hơn ở kích thước lớn.
- **Khẳng định Karatsuba bắt đầu ở đúng một bit length cố định:** ngưỡng nằm trong triển khai, tính theo limb và các điều kiện khác, không phải API contract.
- **Chỉ xét một toán hạng:** phép nhân/chia phụ thuộc hình dạng cả hai toán hạng.
- **Tính `pow` cực lớn chỉ để lấy modulo:** thiếu kiểm soát kết quả trung gian; xem `modPow`.
- **Gọi `divide` và `remainder` riêng khi cần cả hai:** có thể trùng công việc; xem `divideAndRemainder`.
- **Benchmark bao gồm `new BigInteger(String)`, `toString` hoặc `println`:** đo nhầm chi phí chuyển đổi và I/O.
- **Dùng `System.nanoTime` một lần để kết luận phức tạp thuật toán:** JIT, GC, noise và thay đổi đường code có thể chi phối mẫu.
- **Quên bộ nhớ:** kết quả và vùng tạm có thể rất lớn dù một API chỉ trả một biến.
- **Lấy `bitLength()` trực tiếp trên số âm để đo bit trị tuyệt đối:** ví dụ -1 cho bitLength 0; dùng `abs().bitLength()` khi đó là thước đo mong muốn.
- **Thay chia số âm cho lũy thừa 2 bằng shiftRight:** khác hướng làm tròn.

## 14. Bài tập và gợi ý

**Bài 1.** Hai số dương đều 1024 bit, rồi tăng mỗi số lên 2048 bit. Nếu chỉ xét phép nhân kiểu phổ thông O(n²) với hai toán hạng cân bằng, lượng công việc tương đối thay đổi khoảng bao nhiêu? Vì sao không được biến tỷ lệ đó thành cam kết đo thực tế?

**Bài 2.** Vì sao phép cộng `(2^256 - 1) + 1` có thể cần xử lý nhiều limb, dù toán hạng thứ hai rất ngắn? Bit length kết quả là bao nhiêu?

**Bài 3.** Muốn tính `2^100000000 mod 97`, nên dùng `pow().mod()` hay `modPow()`? Giải thích theo kích thước dữ liệu trung gian.

**Bài 4.** Với phép nhân một toán hạng 4096 bit và một toán hạng 32 bit, vì sao không nên so trực tiếp với nhân hai số 4096 bit rồi kết luận mọi phép nhân “4096 bit” đều giống nhau?

**Bài 5.** `BigInteger.valueOf(-1).bitLength()` bằng bao nhiêu? Nếu muốn ước lượng độ dài của độ lớn toán hạng, viết biểu thức nào?

**Bài 6.** Thiết kế benchmark JMH đo thời gian phép nhân các cặp 128×128, 1024×1024 và 4096×64 bit. Những thứ gì cần loại khỏi phần đo để đảm bảo đo gần đúng riêng phép nhân?

**Gợi ý đáp án:**

1. Mô hình O(n²) dự đoán khoảng **4 lần** khi cả hai độ dài tăng gấp đôi; triển khai có thể dùng Karatsuba/Toom-Cook, cache và GC khác nhau, nên cần benchmark để biết tỷ lệ thực tế.
2. Carry có thể lan qua chuỗi limb; kết quả bằng `2^256`, có **257 bit**.
3. Dùng `modPow` để tránh tạo và giữ số `2^100000000` đầy đủ khi chỉ cần số dư.
4. Nhân phổ thông có chi phí O(nm), nên cả hai toán hạng ảnh hưởng; đường tối ưu thực tế cũng có thể khác.
5. `-1.bitLength()` theo ý nghĩa đối tượng là **0**; dùng `x.abs().bitLength()` để đo magnitude (trả 1 cho -1).
6. Sinh toán hạng trước trong `@Setup`, tiêu thụ kết quả qua `Blackhole`, có warmup/fork, không parse/format/log trong phần đo; ghi rõ JDK/CPU/config.

## Tài liệu tham khảo

- Java SE 17, BigInteger API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html
- OpenJDK 17, mã nguồn BigInteger (các đường nhân/chia và ngưỡng lựa chọn): https://github.com/openjdk/jdk17/blob/master/src/java.base/share/classes/java/math/BigInteger.java
- OpenJDK JMH project: https://github.com/openjdk/jmh

**Ghi nhớ:** độ dài của **cả hai toán hạng và kết quả trung gian** quyết định rất nhiều tới chi phí BigInteger. Ước lượng bằng số bit/limb để chọn thuật toán, và đo bằng benchmark chuẩn trên tải thực để ra quyết định tối ưu.
