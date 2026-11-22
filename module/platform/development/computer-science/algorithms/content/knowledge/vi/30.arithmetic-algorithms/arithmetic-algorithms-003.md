# Lũy thừa nhanh bằng bình phương liên tiếp

**Lũy thừa nhanh (binary exponentiation / exponentiation by squaring)** tính a^n hoặc a^n mod m bằng cách khai thác các **bit nhị phân của số mũ** và liên tiếp **bình phương cơ số**. Thay vì phải nhân a với chính nó n lần, chỉ cần **O(log n) phép nhân**.

Đây là công cụ quan trọng trong **Thuật toán số học**: số mũ có thể đạt 10^18 hoặc lớn hơn, công thức có thể tính modulo một số nguyên, và phép lũy thừa có thể mở rộng sang **ma trận, hoán vị và các phép toán kết hợp**.

Điểm cốt lõi:

- **a^(2k) = (a^k)^2** khi số mũ chẵn.
- **a^(2k+1) = a·(a^k)^2** khi số mũ lẻ.
- Viết n dưới dạng tổng các lũy thừa của 2; chỉ nhân những thừa số ứng với **bit 1**.
- Muốn lấy modulo, rút gọn **ở mỗi phép nhân** nhưng không được để phép nhân overflow trước khi lấy dư.
- **Số mũ âm** không thuộc phép lũy thừa nguyên thông thường; trong môđun chỉ có thể dùng nghịch đảo khi tồn tại.
- Với phép nhân ma trận, phần tử đơn vị là **ma trận đơn vị I**, không phải số 1.

Bài học trình bày thuật toán lặp/đệ quy, bất biến chứng minh, phân tích độ phức tạp, ví dụ bảng bit, Java 17+ với BigInteger, phép nhân long có kiểm tra tràn, môđun, nghịch đảo và Fibonacci bằng lũy thừa ma trận.

## 1. Định nghĩa và hợp đồng đầu vào

Cho cơ số a và số mũ nguyên **n≥0**:

**a^n = a·a·...·a** với n thừa số a nếu n>0.

Khi n=0, dùng quy ước:

**a^0=1**.

Đặc biệt, trong các hàm của bài này, **0^0=1**: đây là quy ước phổ biến cho phần tử đơn vị của tích rỗng trong lập trình, không phải khẳng định mọi nhánh toán học đều dùng cùng quy ước. Nếu đề bài quy định 0^0 khác, phải theo đề.

Ví dụ:

~~~text
2^10     = 1024
(-3)^5   = -243
(-3)^6   = 729
5^0      = 1
0^7      = 0
0^0      = 1  (quy uoc cua bai)
~~~

Nếu cần **a^n mod m**, ta còn yêu cầu **m>0** và trả phần dư chuẩn trong **[0,m−1]**. Nếu n âm, bài toán khác: phải có một phép nghịch đảo thích hợp.

### Lũy thừa nguyên chính xác khác lũy thừa modulo

- **Chính xác:** trả toàn bộ số a^n, có thể cần hàng triệu chữ số.
- **Modulo:** chỉ trả phần dư a^n mod m, có thể tính rất nhanh ngay cả khi n rất lớn.

Giảm số phép nhân không loại bỏ chi phí lưu một kết quả khổng lồ. Với đề chỉ cần modulo, không nên dựng toàn bộ a^n rồi lấy phần dư.

## 2. Vì sao nhân trực tiếp O(n) không đủ?

Một vòng lặp ngây thơ:

~~~java
long result = 1L;
for (long i = 0; i < exponent; i++) {
    result *= base;
}
~~~

thực hiện **n phép nhân**. Khi n=10^12, số bước quá lớn.

Hơn nữa, trong Java phép nhân long thông thường có thể **tràn số** rồi tiếp tục chạy mà không báo lỗi. Vì thế có hai vấn đề độc lập:

1. **Số phép nhân**: O(n) so với O(log n).
2. **Miền biểu diễn**: long chỉ chứa các giá trị từ Long.MIN_VALUE tới Long.MAX_VALUE; nếu a^n vượt giới hạn, cần BigInteger hoặc chỉ tính modulo.

Bình phương liên tiếp giải quyết vấn đề đầu tiên. Kiểu dữ liệu, modulo và kiểm tra overflow giải quyết vấn đề thứ hai.

## 3. Chẵn, lẻ và cách chia đôi số mũ

Nếu n=2k:

**a^n = (a^k)²**.

Nếu n=2k+1:

**a^n = a·(a^k)²**.

Thay vì trừ n từng đơn vị, mỗi lần ta **chia n cho 2**. Số lần chia tới khi n=0 xấp xỉ số bit biểu diễn n.

Ví dụ 2^13:

~~~text
13 = 8 + 4 + 1
13 in binary = 1101

2^13 = 2^8 * 2^4 * 2^1
     = 256 * 16 * 2
     = 8192
~~~

Các lũy thừa 2¹,2²,2⁴,2⁸ được tạo bằng **bình phương liên tiếp**:

~~~text
a^1
a^2  = (a^1)^2
a^4  = (a^2)^2
a^8  = (a^4)^2
a^16 = (a^8)^2
~~~

Không cần tính từng giá trị a³, a⁵, a⁶, ... để lấy a^13.

## 4. Thuật toán lặp theo bit

Giữ ba biến:

- **result**: tích từ những bit đã xử lý.
- **factor**: lũy thừa cơ số tương ứng với bit hiện tại, bắt đầu bằng a.
- **exp**: phần số mũ chưa xử lý.

Ở mỗi vòng:

1. Nếu **exp & 1** bằng 1, nhân result với factor.
2. Bỏ bit thấp nhất: **exp >>= 1**.
3. Nếu exp vẫn dương, bình phương factor.
4. Lặp đến exp=0.

~~~text
BINARY_POWER(a, n):
    require n >= 0
    result = 1
    factor = a
    exp = n

    while exp > 0:
        if (exp & 1) != 0:
            result = result * factor

        exp = floor(exp / 2)

        if exp > 0:
            factor = factor * factor

    return result
~~~

**Vì sao bình phương chỉ khi exp>0?** Ở vòng cuối, sau khi bỏ bit thấp nhất thì không còn bit nào cần factor mới. Một phép bình phương thừa tuy không ảnh hưởng kết quả toán học nhưng có thể gây **overflow giả** khi dùng Math.multiplyExact trên long.

### Thứ tự thao tác rất quan trọng

Phải xét bit hiện tại **trước khi dịch**. Nếu dịch phải trước rồi mới kiểm tra, ta có thể bỏ sót bit thấp nhất của số mũ ban đầu.

Với n≥0, mỗi vòng chia n cho 2 chắc chắn tiến đến 0. Nếu cho n âm mà dùng dịch phải có dấu, giá trị âm có thể không về 0; vì vậy hàm lũy thừa nguyên từ chối n âm.

## 5. Truy vết 3^13 bằng bảng

Số mũ 13 viết nhị phân là 1101. Các bit từ phải sang trái là **1,0,1,1**.

| Vòng | exp đầu vòng | Bit thấp nhất | factor | result sau xét bit |
| --- | ---: | ---: | ---: | ---: |
| 1 | 13 | 1 | 3 | 3 |
| 2 | 6 | 0 | 9 | 3 |
| 3 | 3 | 1 | 81 | 243 |
| 4 | 1 | 1 | 6561 | 1594323 |

Kết quả:

**3^13 = 1594323**.

Trong vòng 2, bit bằng 0 nên result **không đổi**, nhưng factor vẫn phải bình phương để chuyển từ 3² sang 3⁴.

Trong vòng 3, bit bằng 1 nên result=3·81=243, rồi factor chuyển sang 3⁸=6561.

Trong vòng 4, bit bằng 1, result=243·6561=1594323.

### Ví dụ với cơ số âm

Với a=-3, số mũ lẻ cho kết quả âm, số mũ chẵn cho kết quả dương. Công thức vẫn đúng vì phép nhân số nguyên có tính kết hợp:

**(-3)^5=-243**, **(-3)^6=729**.

Bản thuật toán không cần nhánh đặc biệt cho dấu âm của base.

## 6. Bất biến chứng minh tính đúng

Gọi A,N là cơ số và số mũ ban đầu. Bất biến tại đầu mỗi vòng:

**result · factor^exp = A^N**.

Ban đầu result=1, factor=A, exp=N, nên hiển nhiên đúng.

Nếu exp=2k chẵn, sau khi cập nhật exp'=k và factor'=factor², ta có:

**result·(factor')^exp' = result·(factor²)^k = result·factor^(2k)**.

Nếu exp=2k+1 lẻ, ta trước hết cập nhật result'=result·factor, sau đó exp'=k, factor'=factor². Khi ấy:

**result'·(factor')^exp' = result·factor·(factor²)^k = result·factor^(2k+1)**.

Do đó bất biến được giữ sau mọi vòng. Khi exp=0, factor^0=1, suy ra:

**result=A^N**.

Chứng minh này cũng áp dụng theo **đồng dư modulo m**, vì phép nhân và rút gọn modulo bảo toàn lớp đồng dư.

## 7. Độ phức tạp O(log n)

Trong mỗi vòng, exp giảm từ n xuống floor(n/2).

~~~text
n, floor(n/2), floor(n/4), ..., 1, 0
~~~

Với n>0, có **floor(log₂ n)+1 vòng**. Mỗi vòng thực hiện O(1) phép kiểm tra bit, phép dịch và tối đa một vài phép nhân.

Vì vậy:

- **Số phép nhân:** O(log n).
- **Bộ nhớ phụ:** O(1) biến trong bản lặp nếu mỗi toán hạng được coi là kích thước cố định.

Với n=10^12, số bit chỉ khoảng 40, nhỏ hơn rất nhiều so với 10^12 lần nhân.

### BigInteger thay đổi mô hình thời gian

Khi tính a^n chính xác, độ dài toán hạng tăng theo n. Một phép nhân BigInteger không có chi phí O(1) tuyệt đối; nó phụ thuộc số bit của hai số.

Do đó phát biểu chuẩn là **O(log n) phép nhân số học**, không phải thời gian bit tổng quát O(log n) độc lập với kích thước output.

Với bài modulo m, nếu rút gọn sau từng phép nhân, độ dài các toán hạng được giới hạn theo **số bit của m**; điều này giúp tính hiệu quả hơn.

## 8. Lũy thừa modulo và rút gọn từng bước

Sử dụng:

**(x·y) mod m = ((x mod m)·(y mod m)) mod m**, với m>0.

Ta chỉ cần thay mỗi phép nhân bằng **nhân rồi lấy modulo**:

~~~text
MOD_POWER(a, n, m):
    require n >= 0 and m > 0

    result = 1 mod m
    factor = a mod m

    while n > 0:
        if (n & 1) != 0:
            result = (result * factor) mod m

        n = floor(n / 2)

        if n > 0:
            factor = (factor * factor) mod m

    return result
~~~

### Truy vết 3^13 mod1000

| Vòng | exp đầu | factor mod1000 | Bit | result mod1000 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 13 | 3 | 1 | 3 |
| 2 | 6 | 9 | 0 | 3 |
| 3 | 3 | 81 | 1 | 243 |
| 4 | 1 | 561 | 1 | 323 |

Vì 81² mod1000=561 và 243·561 mod1000=323, kết quả:

**3^13 mod1000 = 323**.

Không cần tính toàn bộ 3^13 rồi mới lấy dư. Điều này đặc biệt quan trọng khi exponent lớn hơn bất kỳ kiểu số nguyên cố định nào.

## 9. Môđun 1, số mũ 0 và cơ số âm

### m=1

Mọi số nguyên có phần dư 0 khi chia cho 1. Vì vậy:

**a^n mod1 = 0** cho n≥0, kể cả n=0 theo quy ước a^0=1 và 1 mod1=0.

Do đó khởi tạo đúng là **result=1 modm**, không phải luôn giữ số 1 chưa rút gọn.

### m=0 hoặc m<0

Bài chỉ định nghĩa modulo chuẩn với **m>0**. Java BigInteger.mod cũng yêu cầu modulus dương. Với m≤0, chương trình báo lỗi đầu vào.

### n=0

**a^0 modm = 1 modm**. Nếu m>1, kết quả 1; nếu m=1, kết quả 0.

### a=0

**0^n=0** với n>0; với n=0, bài dùng 0^0=1.

### a âm

Ví dụ (-2)^5=-32, phần dư chuẩn modulo13 là:

**(-2)^5 mod13 = 7**.

Java primitive % trên số âm có thể trả **-6**, không phải 7. Nếu cần kết quả trong [0,m−1], dùng BigInteger.mod với m dương hoặc Math.floorMod trên kiểu số nguyên phù hợp.

## 10. Overflow: lấy modulo sau phép nhân chưa chắc an toàn

Một lỗi phổ biến:

~~~java
long answer = (a * b) % mod;
~~~

Nếu a*b vượt miền long, phép nhân đã overflow **trước khi % hoạt động**. Việc lấy dư sau đó không khôi phục được kết quả số học đúng.

Có ba cách xử lý:

1. **Chứng minh cận:** nếu 0≤a,b<mod và (mod−1)²≤Long.MAX_VALUE, phép nhân long an toàn.
2. **BigInteger:** nhân và mod chính xác; phù hợp khi modulo lớn hoặc số mũ BigInteger.
3. **mulMod an toàn:** dùng thuật toán cộng/nhân đôi có kiểm soát overflow hoặc các kỹ thuật số học chuyên dụng.

Không được tự ý dùng long vì "kết quả cuối đã lấy modulo nên chắc chắn nhỏ".

### long không modulo và Math.multiplyExact

Khi cần a^n nguyên chính xác nhưng phải trả long, dùng **Math.multiplyExact** để ném ArithmeticException ngay khi phép nhân thực sự cần thiết overflow.

Lưu ý ví dụ:

- **(-2)^63=Long.MIN_VALUE**: vừa trong long.
- **2^63**: vượt Long.MAX_VALUE.

Một bản code bình phương thừa ở vòng cuối có thể gây lỗi ngay cả khi đáp án vừa long; tránh phép nhân không cần thiết.

### BigInteger không miễn giới hạn tài nguyên

BigInteger biểu diễn số nguyên có độ dài biến đổi, nhưng a^n chính xác có thể có số chữ số quá lớn. Nếu chỉ cần modulo, dùng BigInteger.modPow hoặc thuật toán modPower để không phải lưu kết quả đầy đủ.

## 11. Số mũ âm và nghịch đảo môđun

Với n>0, a^(-n)=1/a^n nếu a≠0. Trong số nguyên thông thường, 2^(-3)=1/8 **không phải số nguyên**. Vì vậy hàm powExact dùng BigInteger từ chối exponent âm.

Trong môđun m>1, ta định nghĩa:

**a^(-k) modm = (a⁻¹)^k modm**,

nhưng chỉ khi tồn tại **nghịch đảo môđun** của a.

Điều kiện:

**gcd(a,m)=1**.

Ví dụ m=11, a=3: vì 3·4=12≡1 mod11 nên nghịch đảo của 3 là 4. Khi ấy:

**3^(-2) mod11 = 4² mod11 = 5**.

Với a=6,m=9, gcd(6,9)=3, nên **6 không có nghịch đảo modulo9**. Một hàm trả một số cho 6^(-1) mod9 mà không giải thích quy ước là sai.

Java BigInteger.modInverse(modulus) tính nghịch đảo khi tồn tại và ném **ArithmeticException** nếu không có.

### Long.MIN_VALUE và dấu số mũ

Không được lấy -Long.MIN_VALUE trong long; phép đổi dấu tràn. Với số mũ âm cần lấy trị tuyệt đối, có thể biểu diễn exponent bằng BigInteger và gọi **negate()** an toàn.

### Modulo 1 khi exponent âm

Trong code minh họa, **số mũ âm với modulus=1 bị từ chối** để tránh quy ước đặc biệt về nghịch đảo trong vành tầm thường. Với exponent không âm, modulus1 vẫn cho kết quả 0.

## 12. Khi exponent vượt giới hạn long

Ví dụ:

**2^(100000000000000000000) mod97 = 61**.

Exponent này có 21 chữ số và vượt miền long. Nếu đọc bằng BigInteger, thuật toán chỉ cần xử lý khoảng vài chục bit số mũ thay vì nhân 10^20 lần.

~~~java
BigInteger exponent =
        new BigInteger("100000000000000000000");

BigInteger answer = powMod(
        BigInteger.valueOf(2),
        exponent,
        BigInteger.valueOf(97));
~~~

BigInteger.shiftRight(1) bỏ bit thấp, BigInteger.testBit(0) kiểm tra bit 0.

### Cẩn thận với phép rút gọn số mũ

Không thể tự ý thay exponent bằng exponent%(mod−1) cho mọi cơ số và mọi modulus.

Định lý Fermat cho **a^(p−1)≡1 modp** khi p nguyên tố và a không chia hết cho p. Với modulus hợp số, cần các điều kiện phù hợp như Euler/Carmichael và quan hệ gcd.

Nếu không chắc điều kiện, thuật toán bình phương liên tiếp trên exponent BigInteger vẫn đúng với n≥0 mà **không cần rút gọn exponent trước**.

## 13. Phiên bản đệ quy và lỗi tính lại nhánh

Có thể dùng chia để trị:

~~~text
POWER(a, n):
    if n == 0:
        return 1

    half = POWER(a, floor(n/2))
    square = half * half

    if n odd:
        return square * a
    else:
        return square
~~~

Điểm quan trọng là **chỉ gọi POWER(a,n/2) một lần**, rồi lưu kết quả half.

Cách viết sai:

~~~text
POWER(a,n/2) * POWER(a,n/2)
~~~

gọi lại cùng nhánh hai lần, có thể làm số phép nhân trở lại **O(n)** thay vì O(log n).

Bản đệ quy đúng có độ sâu stack **O(log n)**; bản lặp chỉ cần số biến phụ hằng số (nếu toán hạng có kích thước cố định). Java thường ưu tiên bản lặp cho đoạn code ngắn, rõ và tránh stack recursion không cần thiết.

## 14. Khái quát hóa: monoid và phép toán kết hợp

Kỹ thuật không thực sự cần số nguyên; chỉ cần một phép toán **kết hợp** và **phần tử đơn vị**:

- Số nguyên với phép nhân: đơn vị 1.
- Số nguyên modulo m với phép nhân: đơn vị 1 modm.
- Ma trận vuông với phép nhân ma trận: đơn vị I.
- Hoán vị với phép hợp thành: đơn vị là hoán vị đồng nhất.
- Một phép biến đổi được lặp n lần: phép hợp thành biến đổi.

Cấu trúc có phép toán kết hợp và đơn vị gọi là **monoid**.

Đừng nhầm **kết hợp** với **giao hoán**. Nhân ma trận nói chung không giao hoán, nhưng vẫn kết hợp, nên bình phương liên tiếp hoàn toàn hợp lệ.

Không thể áp dụng cùng công thức cho phép trừ hoặc phép chia tùy ý vì chúng **không kết hợp**.

### Phần tử đơn vị là yếu tố bắt buộc

Binary exponentiation khởi tạo result bằng phần tử đơn vị:

- Nhân số: result=1.
- Nhân modulo m: result=1 modm.
- Nhân ma trận: result=I.
- Hợp thành phép biến đổi: result là phép biến đổi đồng nhất.

Nếu đặt result=0 trong bài nhân số hay ma trận 0 trong bài nhân ma trận, đáp án thường sai ngay từ n=0.

## 15. Lũy thừa ma trận để tính Fibonacci

Xét Fibonacci:

**F₀=0, F₁=1, Fₙ₊₂=Fₙ₊₁+Fₙ**.

Đặt ma trận:

~~~text
Q = [1 1]
    [1 0]
~~~

Với n≥1:

~~~text
Q^n = [F(n+1)  F(n)  ]
      [F(n)    F(n-1)]
~~~

Với n=0, Q^0=I và phần tử (0,1) bằng 0=F₀. Vì vậy:

**Fₙ = phần tử hàng 0 cột 1 của Q^n**, với mọi n≥0.

Chứng minh bằng quy nạp: nhân Q^n với Q cho tổng F(n+1)+F(n)=F(n+2) và các phần tử tương ứng của công thức n+1.

### Vì sao hữu ích?

Dùng vòng for tính Fibonacci đến n cần O(n) phép cộng. Với lũy thừa ma trận 2×2, chỉ cần **O(log n) lần nhân ma trận**.

Mỗi nhân ma trận 2×2 có số lượng hằng số phép cộng/nhân (trong mô hình số học cố định).

Ví dụ:

~~~text
F(0)   = 0
F(10)  = 55
F(50)  = 12586269025
F(100) mod 1000000007 = 687995182
~~~

Nếu lấy Fibonacci modulo m, ta áp dụng modulo m ở **mỗi phép nhân ma trận**, tránh tạo các số lớn.

### Mở rộng cho truy hồi tuyến tính

Với xₙ=c₁xₙ₋₁+c₂xₙ₋₂, có thể viết:

~~~text
[x(n)  ]   [c1 c2] [x(n-1)]
[x(n-1)] = [1  0 ] [x(n-2)]
~~~

Từ đó nhân lũy thừa ma trận chuyển **T^k** để nhảy k bước trong O(log k) lần nhân.

Với ma trận kích thước d×d, phép nhân thông thường O(d³); lũy thừa nhanh cần O(d³ log n) thao tác số học.

## 16. Java 17+ hoàn chỉnh: lũy thừa số, modulo và ma trận

Chương trình độc lập này sử dụng:

- **powExact** cho a^n nguyên chính xác bằng BigInteger, exponent≥0.
- **powLongChecked** với Math.multiplyExact; nếu overflow thì báo lỗi.
- **powMod** cho a^n modm với số mũ BigInteger và m>0.
- **powModSigned** cho số mũ âm khi có nghịch đảo modulo.
- **Mat2.multiply** và **matrixPower** cho lũy thừa ma trận 2×2.
- **fibonacciExact** và **fibonacciMod** để minh họa monoid nhân ma trận.

**Lưu tệp:** BinaryExponentiationDemo.java

~~~java
import java.math.BigInteger;
import java.util.Objects;

public class BinaryExponentiationDemo {

    static final BigInteger ZERO = BigInteger.ZERO;
    static final BigInteger ONE = BigInteger.ONE;
    static final BigInteger TWO = BigInteger.valueOf(2L);

    static void requireNonNegative(BigInteger exponent) {
        Objects.requireNonNull(exponent, "exponent");
        if (exponent.signum() < 0) {
            throw new IllegalArgumentException(
                    "Exponent must be nonnegative");
        }
    }

    static BigInteger powExact(BigInteger base,
                               BigInteger exponent) {
        Objects.requireNonNull(base, "base");
        requireNonNegative(exponent);

        BigInteger result = ONE;
        BigInteger factor = base;
        BigInteger exp = exponent;

        while (exp.signum() > 0) {
            if (exp.testBit(0)) {
                result = result.multiply(factor);
            }

            exp = exp.shiftRight(1);
            if (exp.signum() > 0) {
                factor = factor.multiply(factor);
            }
        }
        return result;
    }

    static long powLongChecked(long base, long exponent) {
        if (exponent < 0L) {
            throw new IllegalArgumentException(
                    "Exponent must be nonnegative");
        }

        long result = 1L;
        long factor = base;
        long exp = exponent;

        while (exp > 0L) {
            if ((exp & 1L) != 0L) {
                result = Math.multiplyExact(result, factor);
            }

            exp >>>= 1;
            if (exp > 0L) {
                factor = Math.multiplyExact(factor, factor);
            }
        }
        return result;
    }

    static BigInteger powMod(BigInteger base,
                             BigInteger exponent,
                             BigInteger modulus) {
        Objects.requireNonNull(base, "base");
        Objects.requireNonNull(modulus, "modulus");
        requireNonNegative(exponent);

        if (modulus.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Modulus must be positive");
        }

        BigInteger result = ONE.mod(modulus);
        BigInteger factor = base.mod(modulus);
        BigInteger exp = exponent;

        while (exp.signum() > 0) {
            if (exp.testBit(0)) {
                result = result.multiply(factor)
                               .mod(modulus);
            }

            exp = exp.shiftRight(1);
            if (exp.signum() > 0) {
                factor = factor.multiply(factor)
                               .mod(modulus);
            }
        }
        return result;
    }

    static BigInteger powModSigned(
            BigInteger base,
            BigInteger exponent,
            BigInteger modulus) {

        Objects.requireNonNull(base, "base");
        Objects.requireNonNull(exponent, "exponent");
        Objects.requireNonNull(modulus, "modulus");

        if (modulus.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Modulus must be positive");
        }

        if (exponent.signum() >= 0) {
            return powMod(base, exponent, modulus);
        }

        if (modulus.compareTo(ONE) <= 0) {
            throw new ArithmeticException(
                    "Negative power requires modulus > 1");
        }

        BigInteger inverse = base.mod(modulus)
                                 .modInverse(modulus);

        return powMod(inverse, exponent.negate(), modulus);
    }

    record Mat2(BigInteger a, BigInteger b,
                BigInteger c, BigInteger d) {

        Mat2 multiply(Mat2 x, BigInteger mod) {
            BigInteger aa = a.multiply(x.a())
                             .add(b.multiply(x.c()));
            BigInteger bb = a.multiply(x.b())
                             .add(b.multiply(x.d()));
            BigInteger cc = c.multiply(x.a())
                             .add(d.multiply(x.c()));
            BigInteger dd = c.multiply(x.b())
                             .add(d.multiply(x.d()));

            if (mod != null) {
                aa = aa.mod(mod);
                bb = bb.mod(mod);
                cc = cc.mod(mod);
                dd = dd.mod(mod);
            }

            return new Mat2(aa, bb, cc, dd);
        }
    }

    static Mat2 matrixPower(
            Mat2 base,
            BigInteger exponent,
            BigInteger mod) {

        Objects.requireNonNull(base, "base");
        requireNonNegative(exponent);

        if (mod != null && mod.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Matrix modulus must be positive");
        }

        BigInteger unit =
                mod == null ? ONE : ONE.mod(mod);

        Mat2 result = new Mat2(unit, ZERO, ZERO, unit);
        Mat2 factor = base;
        BigInteger exp = exponent;

        while (exp.signum() > 0) {
            if (exp.testBit(0)) {
                result = result.multiply(factor, mod);
            }

            exp = exp.shiftRight(1);
            if (exp.signum() > 0) {
                factor = factor.multiply(factor, mod);
            }
        }
        return result;
    }

    static final Mat2 FIB_Q =
            new Mat2(ONE, ONE, ONE, ZERO);

    static BigInteger fibonacciExact(int n) {
        if (n < 0) {
            throw new IllegalArgumentException(
                    "Fibonacci index must be nonnegative");
        }

        return matrixPower(
                FIB_Q, BigInteger.valueOf(n), null).b();
    }

    static BigInteger fibonacciMod(
            BigInteger n,
            BigInteger modulus) {

        requireNonNegative(n);
        Objects.requireNonNull(modulus, "modulus");

        if (modulus.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Modulus must be positive");
        }

        return matrixPower(FIB_Q, n, modulus).b();
    }

    public static void main(String[] args) {
        System.out.println("Exact 2^10: "
                + powExact(TWO, BigInteger.TEN));

        System.out.println("Exact (-3)^5: "
                + powExact(BigInteger.valueOf(-3L),
                           BigInteger.valueOf(5L)));

        System.out.println("Exact 0^0: "
                + powExact(ZERO, ZERO));

        System.out.println("Checked (-2)^63: "
                + powLongChecked(-2L, 63L));

        try {
            powLongChecked(2L, 63L);
            System.out.println("Checked 2^63: FITS");
        } catch (ArithmeticException ex) {
            System.out.println("Checked 2^63: OVERFLOW");
        }

        System.out.println("Mod 3^13 % 1000: "
                + powMod(BigInteger.valueOf(3L),
                         BigInteger.valueOf(13L),
                         BigInteger.valueOf(1000L)));

        System.out.println("Mod 7^13 % 100: "
                + powMod(BigInteger.valueOf(7L),
                         BigInteger.valueOf(13L),
                         BigInteger.valueOf(100L)));

        System.out.println("Mod (-2)^5 % 13: "
                + powMod(BigInteger.valueOf(-2L),
                         BigInteger.valueOf(5L),
                         BigInteger.valueOf(13L)));

        System.out.println("Mod 123456789^123456789 % 1000000007: "
                + powMod(BigInteger.valueOf(123456789L),
                         BigInteger.valueOf(123456789L),
                         BigInteger.valueOf(1000000007L)));

        System.out.println("Mod 9^999 % 1: "
                + powMod(BigInteger.valueOf(9L),
                         BigInteger.valueOf(999L),
                         ONE));

        System.out.println("Mod 2^10^20 % 97: "
                + powMod(TWO,
                         new BigInteger("100000000000000000000"),
                         BigInteger.valueOf(97L)));

        System.out.println("Signed 3^-2 % 11: "
                + powModSigned(BigInteger.valueOf(3L),
                         BigInteger.valueOf(-2L),
                         BigInteger.valueOf(11L)));

        try {
            powModSigned(BigInteger.valueOf(6L),
                         BigInteger.valueOf(-1L),
                         BigInteger.valueOf(9L));
            System.out.println("Signed 6^-1 % 9: HAS INVERSE");
        } catch (ArithmeticException ex) {
            System.out.println("Signed 6^-1 % 9: NO INVERSE");
        }

        System.out.println("Fibonacci F(0): "
                + fibonacciExact(0));

        System.out.println("Fibonacci F(10): "
                + fibonacciExact(10));

        System.out.println("Fibonacci F(50): "
                + fibonacciExact(50));

        System.out.println("Fibonacci F(100) % 1000000007: "
                + fibonacciMod(BigInteger.valueOf(100L),
                         BigInteger.valueOf(1000000007L)));
    }
}
~~~

Chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 BinaryExponentiationDemo.java
java BinaryExponentiationDemo
~~~

**Đầu ra minh họa:**

~~~text
Exact 2^10: 1024
Exact (-3)^5: -243
Exact 0^0: 1
Checked (-2)^63: -9223372036854775808
Checked 2^63: OVERFLOW
Mod 3^13 % 1000: 323
Mod 7^13 % 100: 7
Mod (-2)^5 % 13: 7
Mod 123456789^123456789 % 1000000007: 907408795
Mod 9^999 % 1: 0
Mod 2^10^20 % 97: 61
Signed 3^-2 % 11: 5
Signed 6^-1 % 9: NO INVERSE
Fibonacci F(0): 0
Fibonacci F(10): 55
Fibonacci F(50): 12586269025
Fibonacci F(100) % 1000000007: 687995182
~~~

### Giải thích code

**powExact:** BigInteger dùng phép nhân chính xác; khi exp=0, vòng while không chạy, trả 1 (kể cả base=0 theo quy ước).

**powLongChecked:** dùng Math.multiplyExact và không bình phương thừa ở vòng cuối. Nếu một phép nhân cần thiết overflow thì ném ArithmeticException; không im lặng nhận số bị tràn.

**powMod:** chuẩn hóa base bằng BigInteger.mod, result bằng ONE.mod(modulus), sau đó luôn lấy mod ở phép nhân và bình phương. Hỗ trợ exponent BigInteger cực lớn.

**powModSigned:** nếu exponent âm, tính nghịch đảo base.mod(modulus).modInverse(modulus), rồi lũy thừa với exponent.negate(). Nếu không tồn tại nghịch đảo, API ném ArithmeticException.

**Mat2:** biểu diễn ma trận 2×2. Công thức nhân:

~~~text
[a b] [e f]   [ae+bg  af+bh]
[c d] [g h] = [ce+dg  cf+dh]
~~~

Mọi phần tử được rút gọn mod nếu có mod. Nhân ma trận kết hợp, cho phép sử dụng cùng thuật toán theo bit.

**matrixPower:** khởi tạo ma trận đơn vị; nếu modulo được yêu cầu thì chuẩn hóa 1 theo mod trước. Với n=0, kết quả là I (hoặc I modm).

**fibonacciExact/fibonacciMod:** trả phần tử (0,1) của Q^n, không đọc trực tiếp F(n+1). Kết quả F(0)=0 được xử lý đúng qua Q^0=I.

### Khi sử dụng thư viện chuẩn

BigInteger có:

- **pow(int)**: a^n chính xác nếu n là int không âm.
- **modPow(BigInteger exponent,BigInteger modulus)**: có tối ưu nội bộ cho phép toán modular exponentiation.
- **modInverse(modulus)**: tìm nghịch đảo khi tồn tại.

Nếu chỉ cần bài thực tế, những hàm thư viện đã được kiểm thử thường nên được ưu tiên. Bản tự cài trong bài nhằm **làm rõ cơ chế bình phương liên tiếp**, nhất là khi mở rộng sang ma trận hoặc monoid không phải số nguyên.

## 17. Kiểm thử bằng oracle nhân trực tiếp

Để QA thuật toán, dùng cách đơn giản nhưng **khác cơ chế**:

~~~text
SLOW_POWER(a,n):
    result = 1
    repeat n times:
        result = result * a
    return result
~~~

Với modulo:

~~~text
SLOW_MOD_POWER(a,n,m):
    result = 1 mod m
    base = a mod m
    repeat n times:
        result = (result * base) mod m
    return result
~~~

Oracle này O(n), chỉ phù hợp số mũ nhỏ, nhưng có giá trị kiểm tra cao vì không sử dụng cách xét bit hay bình phương liên tiếp.

### Kiểm tra tính chất đại số

Với u,v≥0:

**a^(u+v)=a^u·a^v**.

Sau khi lấy modulo m:

**powMod(a,u+v,m) = (powMod(a,u,m)·powMod(a,v,m)) mod m**.

Công thức này vẫn đúng với m hợp số, cơ số âm và modulo1, miễn là mọi số mũ không âm.

### Kiểm tra nghịch đảo modular

Với m>1, nếu gcd(a,m)=1, một ứng viên x là nghịch đảo nếu:

**a·x modm=1**.

Với modulus nhỏ, có thể thử x=0..m−1 để làm oracle độc lập. Nếu gcd(a,m)>1, không tồn tại x thỏa.

### Kiểm tra Fibonacci bằng vòng lặp

Thay vì dùng một phiên bản lũy thừa ma trận thứ hai, tính Fₙ qua truy hồi:

~~~text
a = 0
b = 1
repeat n times:
    (a,b) = (b,a+b)
return a
~~~

Sau đó so với phần tử (0,1) của Q^n, vừa cho kết quả chính xác vừa bắt lỗi index ma trận.

### Các ca nên thử

| Input | Kết quả cần có |
| --- | --- |
| 2^10 | 1024 |
| (-3)^5 | -243 |
| (-3)^6 | 729 |
| 0^0 | 1 theo quy ước |
| 0^7 | 0 |
| a^0 mod1 | 0 |
| 3^13 mod1000 | 323 |
| (-2)^5 mod13 | 7 |
| 3^(-2) mod11 | 5 |
| 6^(-1) mod9 | Không có nghịch đảo |
| 2^63 với long | Báo overflow |
| (-2)^63 với long | Long.MIN_VALUE |
| F₀ | 0 |
| F₁₀ | 55 |
| F₁₀₀ mod1000000007 | 687995182 |

Đừng chỉ thử a,n dương: nhiều lỗi xuất hiện ở môđun1, exponent0, base âm và ranh giới kiểu long.

## 18. Các lỗi thường gặp

1. **Nhân n lần** thay vì chia đôi exponent, làm O(n).
2. **Khởi tạo result=0** thay vì phần tử đơn vị 1.
3. **Quên trường hợp n=0**, trả sai.
4. **Không quy định 0^0** trong API.
5. **Nhân factor vào result ngay cả khi bit=0**, tính sai số mũ.
6. **Không bình phương factor** sau khi dịch số mũ.
7. **Dịch số mũ trước rồi mới xem bit**, bỏ bit thấp nhất.
8. **Không giảm exponent**, tạo vòng vô hạn.
9. **Cho exponent âm vào vòng dịch có dấu**, không về 0.
10. **Tính POWER(a,n/2) hai lần** ở bản đệ quy, làm mất lợi thế O(log n).
11. **Bình phương factor thừa ở vòng cuối**, gây overflow không cần thiết.
12. **Coi kết quả sau overflow long là số nguyên đúng**, không dùng Math.multiplyExact hoặc BigInteger.
13. **Cho rằng (a*b)%m an toàn cho mọi long**, dù tích đã có thể tràn.
14. **Dùng Math.pow(double,double) rồi ép long** cho số nguyên rất lớn, mất độ chính xác.
15. **Không chuẩn hóa cơ số âm modulo**, trả phần dư âm.
16. **Khởi tạo result=1 không mod khi m=1**, trả 1 thay vì 0 cho exponent0.
17. **Chấp nhận m=0**, phép modulo không hợp lệ.
18. **Chấp nhận m âm mà vẫn áp quy ước phần dư dương**, mâu thuẫn API.
19. **Dùng số mũ âm cho BigInteger.pow** như thể kết quả nguyên.
20. **Tính nghịch đảo khi gcd(a,m)>1**, không có nghiệm.
21. **Dùng -Long.MIN_VALUE**, overflow khi lấy trị tuyệt đối.
22. **Dùng Fermat a^(p−2) khi modulus không nguyên tố**, không có đảm bảo.
23. **Rút gọn exponent theo mod−1 vô điều kiện**, sai khi điều kiện định lý không thỏa.
24. **Lẫn môđun m với số mũ n**, thay nhầm biến trong vòng lặp.
25. **Cho rằng O(log n) phép nhân tương đương O(log n) thời gian bit**, bỏ chi phí BigInteger.
26. **Nhầm phép nhân ma trận với nhân theo từng phần tử**, trả Fibonacci sai.
27. **Khởi tạo matrix result bằng ma trận 0**, thay vì I.
28. **Coi phép nhân ma trận là giao hoán**, đảo thứ tự không có lý do.
29. **Quên lấy modulo trong nhân ma trận**, tạo số rất lớn.
30. **Lấy Fₙ từ sai vị trí của Q^n**, lệch chỉ số.
31. **Dùng phép toán không kết hợp để lũy thừa**, bất biến không còn đúng.
32. **Không thử ca biên base=0, exponent=0, modulus=1**, bỏ sót lỗi đơn vị.

## 19. Câu hỏi và bài tập tự luyện

**Câu 1.** Viết 45 dưới dạng tổng lũy thừa của 2 và mô tả a^45 bằng các factor.  
**Đáp án:** 45=(101101)₂=32+8+4+1; a^45=a^32·a^8·a^4·a.

**Câu 2.** Với n=13, thuật toán xét bit theo thứ tự nào?  
**Đáp án:** Từ thấp lên cao: 1,0,1,1.

**Câu 3.** Tại sao phải khởi tạo result=1?  
**Đáp án:** 1 là phần tử đơn vị của phép nhân và cho đáp án đúng khi n=0.

**Câu 4.** Tính 3^13 mod1000.  
**Đáp án:** 323.

**Câu 5.** Tính (-2)^5 mod13 theo phần dư chuẩn.  
**Đáp án:** 7.

**Câu 6.** Tại sao 2^63 overflow long nhưng (-2)^63 không?  
**Đáp án:** 2^63 vượt Long.MAX_VALUE, còn (-2)^63=Long.MIN_VALUE.

**Câu 7.** Tại sao không thể luôn dùng a*b%m trên long?  
**Đáp án:** a*b có thể overflow trước khi % được áp dụng.

**Câu 8.** Tại sao n=0,m=1 phải trả 0 trong hàm modPower?  
**Đáp án:** a^0=1 theo quy ước và 1 mod1=0.

**Câu 9.** 3^(-2) mod11 bằng bao nhiêu?  
**Đáp án:** 5, vì nghịch đảo của 3 là 4 và 4² mod11=5.

**Câu 10.** 6^(-1) mod9 tồn tại không?  
**Đáp án:** Không, vì gcd(6,9)=3>1.

**Câu 11.** Bất biến chính của binary exponentiation?  
**Đáp án:** result·factor^exp=a^n ban đầu, hoặc đồng dư modulo m.

**Câu 12.** Số vòng nếu n có k bit?  
**Đáp án:** Đúng k vòng với n>0.

**Câu 13.** Có thể dùng kỹ thuật này cho ma trận không giao hoán không?  
**Đáp án:** Có, vì cần tính kết hợp chứ không cần tính giao hoán.

**Câu 14.** Phần tử đơn vị của phép nhân ma trận?  
**Đáp án:** Ma trận đơn vị I.

**Câu 15.** Q=[[1,1],[1,0]]; Fₙ nằm ở đâu trong Q^n?  
**Đáp án:** Phần tử (0,1), với n≥0.

**Câu 16.** Độ phức tạp nhân ma trận d×d bằng thuật toán thường rồi lũy thừa n?  
**Đáp án:** O(d³ log n) phép toán số học.

**Câu 17.** Vì sao không cần dựng toàn bộ 2^(10^20) khi chỉ hỏi modulo97?  
**Đáp án:** Sau mỗi phép nhân đều rút gọn modulo97; chỉ cần số vòng theo số bit của exponent.

**Câu 18.** Khi n âm, hàm powExact nên làm gì?  
**Đáp án:** Từ chối hoặc chuyển sang kiểu biểu diễn hữu tỉ/thực với định nghĩa rõ; không trả nguyên sai.

**Câu 19.** Vì sao phiên bản đệ quy phải lưu half?  
**Đáp án:** Tránh tính lại cả nhánh a^(n/2) hai lần, giữ O(log n) lời gọi.

**Câu 20.** Muốn QA một hàm powMod, dùng oracle gì?  
**Đáp án:** Nhân rồi modulo n lần với n nhỏ, so kết quả trên nhiều trường hợp ngẫu nhiên.

## 20. Tổng kết và checklist áp dụng

Khi gặp bài toán a^n hoặc a^n modm:

1. Xác định **n≥0** hay có thể âm; xác định modulus có dương hay không.
2. Phân biệt cần **kết quả nguyên chính xác** với chỉ cần **phần dư**.
3. Viết **result=identity**, **factor=base** rồi duyệt từng bit exponent.
4. Bit 1: nhân result với factor; sau đó chia exponent cho 2 và bình phương factor khi còn cần.
5. Trong bài modulo, rút gọn **sau mỗi phép nhân** và bảo đảm phép nhân trung gian không overflow.
6. Với primitive long, dùng Math.multiplyExact nếu cần báo lỗi; với số lớn, dùng BigInteger.
7. Với exponent âm trong modulo, chỉ dùng nghịch đảo khi gcd(base,modulus)=1.
8. Nêu rõ trường hợp 0^0, exponent0, base0, modulus1.
9. Dùng cùng cấu trúc thuật toán cho **ma trận** hoặc monoid bất kỳ có phép toán kết hợp và phần tử đơn vị.
10. Với Fibonacci, dùng Q^n; khi chỉ cần modulo, rút gọn từng phần tử sau nhân ma trận.
11. Chứng minh tính đúng qua bất biến **result·factor^exp=a^n**.
12. Phân tích O(log n) **số phép nhân**, đồng thời ghi rõ chi phí bit nếu dùng BigInteger.
13. Kiểm thử bằng phép nhân trực tiếp O(n) cho exponent nhỏ và kiểm thử đại số cho exponent lớn.

**Cốt lõi:** bình phương liên tiếp biến việc nhân n lần thành xử lý chỉ **O(log n) bit**. Đây là một kỹ thuật ngắn gọn nhưng có sức ứng dụng rộng từ số học modulo tới truy hồi tuyến tính và các phép biến đổi lặp.
