# BigInteger.pow, sqrt, sqrtAndRemainder và gcd trong Java

## 1. Mục tiêu bài học

**java.math.BigInteger** là lớp số nguyên có độ chính xác tùy ý trong Java. Thay vì bị giới hạn ở 32 bit của int hoặc 64 bit của long, nó có thể biểu diễn và tính toán số nguyên rất lớn trong giới hạn bộ nhớ và khả năng xử lý của môi trường.

Bài này tập trung vào bốn phương thức:

- **pow(int exponent)**: tính lũy thừa nguyên với số mũ nguyên **không âm**.
- **sqrt()**: lấy **căn bậc hai nguyên**, tức phần nguyên dưới của căn bậc hai số không âm.
- **sqrtAndRemainder()**: đồng thời lấy **căn bậc hai nguyên** và **phần dư** so với bình phương căn nguyên.
- **gcd(BigInteger val)**: ước chung lớn nhất (greatest common divisor) của hai số nguyên, kể cả đầu vào âm hoặc 0.

Điểm chung là **kết quả nguyên chính xác**, không cần đổi sang double và không phải chấp nhận mất chữ số do số dấu phẩy động. Bạn sẽ học định nghĩa, giới hạn đầu vào, trường hợp biên, cách kết hợp các phương thức, tối ưu có căn cứ và kiểm thử bằng chương trình Java 17+.

## 2. Ôn lại BigInteger: bất biến và tính toán chính xác

Tạo BigInteger bằng chuỗi thập phân hoặc một giá trị long:

~~~java
import java.math.BigInteger;

BigInteger a = new BigInteger("123456789012345678901234567890");
BigInteger b = BigInteger.valueOf(42);
BigInteger sum = a.add(b);
~~~

Các phép tính **không sửa** a và b. BigInteger là kiểu đối tượng **immutable**: mỗi phương thức trả về một giá trị kết quả theo quy tắc API, còn toán hạng ban đầu không đổi. Với các hằng hay dùng, sử dụng **BigInteger.ZERO**, **ONE**, **TWO**, **TEN** (TWO có từ Java 9).

Đừng viết:

~~~java
// Không hợp lệ: BigInteger không có phép cộng toán tử + giữa các đối tượng.
// BigInteger invalid = a + b;
~~~

Hãy dùng a.add(b), a.multiply(b), a.pow(...). Đặc tính bất biến cũng có nghĩa:

~~~java
BigInteger x = BigInteger.valueOf(3);
x.pow(4);                 // kết quả bị bỏ qua
System.out.println(x);   // vẫn là 3
BigInteger y = x.pow(4);  // 81
~~~

### Vì sao không chuyển qua double?

Dạng double chỉ có khoảng **53 bit chính xác** trong significand; các số nguyên lớn không luôn được biểu diễn đúng. Ví dụ một số có hàng trăm chữ số có thể vượt hẳn miền hữu hạn của double. Khi muốn căn bậc hai nguyên hoặc gcd **chính xác** trên số lớn, hãy giữ dữ liệu ở BigInteger, không đi qua Math.sqrt(double).

## 3. So sánh nhanh bốn API

| Phương thức | Input | Output | Ý nghĩa toán học | Trường hợp cần lưu ý |
| --- | --- | --- | --- | --- |
| **a.pow(e)** | e kiểu **int**, e ≥ 0 | BigInteger | a^e chính xác | e âm → ArithmeticException |
| **n.sqrt()** | n ≥ 0 | BigInteger | floor(√n) | n âm → ArithmeticException |
| **n.sqrtAndRemainder()** | n ≥ 0 | BigInteger[2] | [s, n−s²], s=floor(√n) | n âm → ArithmeticException |
| **a.gcd(b)** | a, b là BigInteger | BigInteger | gcd(|a|,|b|) không âm | gcd(0,0) = 0 |

**pow** đã có từ các phiên bản Java rất sớm. **sqrt** và **sqrtAndRemainder** được giới thiệu từ **Java 9**; trong Java 17 chúng có sẵn. **gcd** cũng có sẵn trong Java 17.

Chữ **floor** nghĩa là lấy số nguyên lớn nhất không vượt giá trị thực. Với n=200, √200 xấp xỉ 14.142..., nên kết quả **sqrt() bằng 14**, không phải số thập phân 14.142.

## 4. pow(int exponent): lũy thừa số nguyên chính xác

Với BigInteger a và số mũ e không âm:

\[
a^e = \underbrace{a\times a\times\dots\times a}_{e\text{ thừa số}}
\]

Phương thức:

~~~java
BigInteger base = BigInteger.valueOf(12);
BigInteger result = base.pow(5); // 248832
~~~

Kết quả là BigInteger chính xác. Không có overflow 32/64 bit trong phép nhân nội bộ theo cách int hoặc long thường gặp; tuy nhiên nếu kết quả quá lớn so với bộ nhớ hay giới hạn triển khai, thao tác vẫn có thể không thực hiện được.

### Số mũ là int, không phải BigInteger

Chữ ký là **BigInteger pow(int exponent)**:

~~~java
BigInteger x = BigInteger.valueOf(7);
BigInteger y = x.pow(4); // 2401
~~~

Không có overload **pow(BigInteger)** với ý nghĩa lũy thừa tổng quát. Nếu bạn có một BigInteger làm số mũ, phải thiết kế lại thuật toán hoặc chuyển về int với kiểm tra **intValueExact()** nếu thật sự thỏa giới hạn. Không biến một số mũ cực lớn thành int bằng intValue() rồi cho rằng kết quả vẫn đúng: thao tác đó có thể mất bit.

### Dấu âm theo tính chẵn lẻ của số mũ

\[
(-3)^4=81,\qquad (-3)^5=-243
\]

~~~java
BigInteger minusThree = BigInteger.valueOf(-3);
BigInteger even = minusThree.pow(4); // 81
BigInteger odd = minusThree.pow(5);  // -243
~~~

Đối với cơ số âm, số mũ chẵn tạo kết quả không âm, số mũ lẻ tạo kết quả âm. Với cơ số dương, kết quả dương khi số mũ dương.

### Các trường hợp 0 và số mũ 0

Trong API BigInteger:

~~~java
BigInteger a = BigInteger.ZERO.pow(0); // 1
BigInteger b = BigInteger.ZERO.pow(5); // 0
BigInteger c = BigInteger.TEN.pow(0);  // 1
~~~

Theo quy ước của phép lũy thừa nguyên trong API, **0.pow(0) trả BigInteger.ONE**. Đừng nhầm quy ước lập trình này với việc tìm giới hạn giải tích tại (0,0): đó là câu hỏi toán học khác.

### Số mũ âm là không hợp lệ

~~~java
BigInteger base = BigInteger.valueOf(2);
// base.pow(-1) -> ArithmeticException
~~~

Đối với số nguyên, **2^−1=1/2** không còn thuộc tập số nguyên. BigInteger.pow không trả phân số hoặc số thập phân, và **ném ArithmeticException khi exponent < 0**. Nếu bài toán cần số mũ âm, hãy thiết kế biểu diễn phân số/BigDecimal hoặc thuật toán cụ thể; không ép kiểu ngầm.

### pow khác Math.pow

| Đặc điểm | BigInteger.pow | Math.pow |
| --- | --- | --- |
| Cơ số | BigInteger | double |
| Số mũ | int không âm | double |
| Kết quả | BigInteger nguyên chính xác | double, có thể làm tròn |
| Số cực lớn | Không bị chặn bởi 64 bit, vẫn có giới hạn tài nguyên | Có thể overflow thành Infinity |
| Số mũ âm | Không hỗ trợ; ArithmeticException | Có hỗ trợ theo ngữ nghĩa double |

Ví dụ **BigInteger.TEN.pow(20)** cho chính xác **100000000000000000000**. Dùng **Math.pow(10,20)** trả một double có biểu diễn riêng, và khi áp dụng sang số nguyên lớn nói chung không có bảo đảm giữ mọi chữ số.

### Không tự dùng vòng lặp nhân ngây thơ cho kết quả khổng lồ

Có thể viết vòng lặp nhân để minh họa toán học, nhưng BigInteger.pow đã được tối ưu theo đặc điểm kiểu. Một số mũ rất lớn có thể tạo kết quả có hàng triệu bit hoặc hơn. Với **input không đáng tin cậy**, kiểm tra số mũ và giới hạn độ dài kết quả **trước** khi chạy; không dựa vào việc BigInteger có độ chính xác tùy ý để bỏ giới hạn tài nguyên.

## 5. sqrt(): căn bậc hai nguyên, không phải căn thập phân

Với n là BigInteger không âm, đặt:

\[
s=\lfloor\sqrt n\rfloor
\]

Khi đó s là **số nguyên không âm lớn nhất thỏa s² ≤ n**. Định nghĩa tương đương:

\[
s^2\le n <(s+1)^2
\]

Ví dụ:

| n | √n trong toán học | n.sqrt() |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 1 | 1 | 1 |
| 2 | xấp xỉ 1.414... | 1 |
| 15 | xấp xỉ 3.873... | 3 |
| 16 | 4 | 4 |
| 17 | xấp xỉ 4.123... | 4 |
| 81 | 9 | 9 |
| 200 | xấp xỉ 14.142... | 14 |

~~~java
BigInteger n = BigInteger.valueOf(200);
BigInteger floorRoot = n.sqrt(); // 14
~~~

**sqrt() không trả double**, không làm tròn đến số nguyên gần nhất, cũng không lấy ceiling. Nó lấy **floor** của căn bậc hai không âm.

### Tại sao phải dùng BigInteger.sqrt thay vì Math.sqrt(double)?

Nếu n có hàng chục hoặc hàng trăm chữ số, việc chuyển sang double có thể **làm tròn n**, thậm chí thành **Infinity**. Áp dụng Math.sqrt lên giá trị đã đổi kiểu rồi cast kết quả về long/int không thể khôi phục thông tin đã mất.

Ngay cả khi double còn hữu hạn, phép làm tròn có thể khiến căn của một số rất gần số chính phương trở thành một số nguyên **không đúng**. BigInteger.sqrt tính đúng kết quả nguyên của **chính n**, không dựa vào xấp xỉ double làm kết quả đầu ra.

### sqrt của số âm

~~~java
BigInteger negative = BigInteger.valueOf(-4);
// negative.sqrt() -> ArithmeticException
~~~

BigInteger là số nguyên thực có dấu, không phải số phức. Với **n < 0**, sqrt() ném **ArithmeticException**. Hãy kiểm tra **n.signum() >= 0** nếu giao diện cần lỗi có thông điệp riêng.

### Kiểm tra số chính phương

Số chính phương là số dạng k² với k nguyên. Với n ≥ 0:

~~~java
static boolean isPerfectSquare(BigInteger n) {
    if (n.signum() < 0) {
        return false;
    }
    BigInteger s = n.sqrt();
    return s.multiply(s).equals(n);
}
~~~

Đây là phương thức minh họa cần đặt bên trong class và import **java.math.BigInteger**. Với n=81, s=9, phép so sánh trả true. Với n=200, s=14, 14²=196 khác 200, trả false.

Một cách có thể tận dụng API tiếp theo là dùng **sqrtAndRemainder()[1].signum() == 0** trên n không âm.

## 6. sqrtAndRemainder(): lấy đồng thời căn nguyên và phần dư

Với n ≥ 0:

\[
s=\lfloor\sqrt n\rfloor,\qquad r=n-s^2
\]

**BigInteger.sqrtAndRemainder()** trả **mảng BigInteger[] gồm chính xác hai phần tử**:

- **result[0]** là s, căn bậc hai nguyên.
- **result[1]** là r, phần dư khi trừ đi s².

~~~java
BigInteger n = BigInteger.valueOf(200);
BigInteger[] pair = n.sqrtAndRemainder();

BigInteger s = pair[0]; // 14
BigInteger r = pair[1]; // 4
~~~

Phải gọi **r = n−s²**, **không phải** phép chia lấy dư như **n % s**. Ví dụ 200 chia 14 dư 4 trùng ngẫu nhiên trong ví dụ này, nhưng về tổng quát hai định nghĩa không đồng nhất.

Lấy n=99 để thấy rõ:

~~~java
BigInteger[] pair = BigInteger.valueOf(99).sqrtAndRemainder();
// s = 9, r = 99-81 = 18
// Nhưng 99 % 9 = 0. Hai loại "remainder" khác nhau.
~~~

### Các bất biến toán học quan trọng

Do s=floor(√n):

\[
s^2\le n <(s+1)^2=s^2+2s+1
\]

Suy ra:

\[
n=s^2+r,\qquad 0\le r<2s+1
\]

Vì r nguyên, có thể viết **0 ≤ r ≤ 2s**.

Dùng bất biến này để kiểm tra kết quả:

~~~java
BigInteger[] qr = n.sqrtAndRemainder();
BigInteger s = qr[0];
BigInteger r = qr[1];

boolean exactReconstruction = s.pow(2).add(r).equals(n);
boolean validRange = r.signum() >= 0
        && r.compareTo(s.shiftLeft(1).add(BigInteger.ONE)) < 0;
~~~

Đoạn code minh họa nằm trong method với **n ≥ 0** đã khai báo; **shiftLeft(1)** nhân s với 2. Mọi bước đều là BigInteger, không lo tràn int/long trong phép nhân/tổng.

### Khi nào dùng sqrtAndRemainder thay sqrt?

- Cần đồng thời **căn nguyên** và **phần dư**.
- Cần kiểm tra **số chính phương** (r=0).
- Cần một bất biến đầu ra để kiểm thử thuật toán số nguyên.
- Muốn biết n nằm **cách bình phương nguyên lớn nhất không vượt n bao xa**.

Ví dụ:

| n | s = floor(√n) | r = n−s² | n là số chính phương? |
| ---: | ---: | ---: | --- |
| 0 | 0 | 0 | Có |
| 1 | 1 | 0 | Có |
| 2 | 1 | 1 | Không |
| 81 | 9 | 0 | Có |
| 99 | 9 | 18 | Không |
| 200 | 14 | 4 | Không |

sqrtAndRemainder() cũng **ném ArithmeticException cho số âm**. Nếu chỉ cần s, dùng sqrt() là trực tiếp và rõ ràng hơn.

## 7. gcd(BigInteger): ước chung lớn nhất

**gcd** là viết tắt của **greatest common divisor**, tiếng Việt là **ước chung lớn nhất**. Đối với hai số nguyên a, b không cùng bằng 0, gcd(a,b) là số nguyên dương lớn nhất chia hết cả hai.

Ví dụ:

~~~java
BigInteger a = BigInteger.valueOf(54);
BigInteger b = BigInteger.valueOf(24);
BigInteger g = a.gcd(b); // 6
~~~

Các ước chung dương của 54 và 24 gồm 1, 2, 3, 6; số lớn nhất là 6.

### Số âm không làm gcd âm

**BigInteger.gcd** luôn trả số **không âm**, về bản chất:

\[
\gcd(a,b)=\gcd(|a|,|b|)
\]

~~~java
BigInteger g = BigInteger.valueOf(-54)
        .gcd(BigInteger.valueOf(24)); // 6
~~~

Nếu cả hai toán hạng khác 0, gcd trả số dương. Với một toán hạng 0, gcd trả độ lớn tuyệt đối của toán hạng còn lại.

### Các trường hợp zero

| a | b | a.gcd(b) |
| ---: | ---: | ---: |
| 54 | 24 | 6 |
| −54 | 24 | 6 |
| 0 | 24 | 24 |
| 0 | −24 | 24 |
| 0 | 0 | **0** |
| 101 | 24 | 1 |

Trong lý thuyết số có thể có những cách nói khác nhau về gcd(0,0), nhưng **API BigInteger.gcd(0,0) định nghĩa trả 0**. Không tự ném exception cho trường hợp này nếu muốn bám sát hành vi API.

**Gcd bằng 1** nghĩa là hai số **nguyên tố cùng nhau** (*coprime*), không nhất thiết từng số đều là số nguyên tố.

### Vì sao gcd phù hợp với số rất lớn?

Thuật toán Euclid dựa trên phép chia lấy dư:

\[
\gcd(a,b)=\gcd(b,a\bmod b)
\]

Lặp cho đến khi số dư bằng 0. Java cung cấp BigInteger.gcd đã triển khai sẵn, nên không cần tự viết phiên bản dựa trên int/long rồi vô tình overflow hoặc làm mất các chữ số lớn.

Ví dụ nếu đầu vào có hàng trăm chữ số, không chuyển về long để tính gcd. Giữ BigInteger và gọi a.gcd(b).

## 8. Ứng dụng kết hợp: rút gọn phân số bằng gcd

Cho phân số a/b với **b ≠ 0**. Nếu g=gcd(a,b) thì:

\[
\frac{a}{b}=\frac{a/g}{b/g}
\]

Ví dụ **84/30** có gcd bằng 6 nên rút gọn thành **14/5**:

~~~java
BigInteger numerator = BigInteger.valueOf(84);
BigInteger denominator = BigInteger.valueOf(30);

if (denominator.signum() == 0) {
    throw new ArithmeticException("Zero denominator");
}
BigInteger g = numerator.gcd(denominator);
BigInteger reducedNumerator = numerator.divide(g);   // 14
BigInteger reducedDenominator = denominator.divide(g); // 5
~~~

Đây là đoạn minh họa bên trong method. BigInteger.divide chia nguyên và ở đây **chia hết** vì g là ước chung.

Để có biểu diễn phân số chuẩn, thường quy định **mẫu số dương**: nếu denominator âm, đổi dấu cả tử và mẫu trước hoặc sau bước rút gọn. Nếu numerator=0, gcd(0,b)=|b|, nên phân số 0/b có thể chuẩn hóa thành 0/1 (khi đã chuẩn hóa dấu mẫu).

**Cảnh báo:** gcd(0,0)=0, nhưng 0/0 vẫn là phân số không hợp lệ; phải kiểm tra mẫu số bằng 0 **trước** khi chia cho gcd.

## 9. Ứng dụng kết hợp: bội chung nhỏ nhất (LCM)

Bội chung nhỏ nhất của hai số nguyên a, b có thể tính từ gcd:

\[
\operatorname{lcm}(a,b)=
\begin{cases}
0,&a=0\text{ hoặc }b=0\\
\left|\frac{a}{\gcd(a,b)}\times b\right|,&\text{ngược lại}
\end{cases}
\]

Để tránh tạo ra trung gian lớn hơn mức cần thiết, **chia cho gcd trước rồi mới nhân**:

~~~java
static BigInteger lcm(BigInteger a, BigInteger b) {
    if (a.signum() == 0 || b.signum() == 0) {
        return BigInteger.ZERO;
    }
    return a.divide(a.gcd(b)).multiply(b).abs();
}
~~~

Đây là phương thức minh họa cần đặt bên trong class. Ví dụ lcm(84,30)=420; với đầu vào âm, **abs()** đảm bảo kết quả không âm. Với BigInteger, nhân không bị overflow kiểu long nhưng vẫn có chi phí bộ nhớ/CPU, nên giảm trung gian có ích.

## 10. pow với số rất lớn: giới hạn CPU và bộ nhớ

Có thể tạo giá trị **10^1.000.000** bằng BigInteger.TEN.pow(1_000_000) nếu môi trường đủ tài nguyên, nhưng kết quả sẽ có hơn một triệu chữ số thập phân. Vấn đề không còn là overflow 64 bit mà là:

- Kích thước đối tượng, nhu cầu heap và bộ nhớ tạm.
- Thời gian tính lũy thừa và thời gian chuyển giá trị sang chuỗi.
- Khả năng bị người dùng lợi dụng số mũ cực lớn làm tiêu hao tài nguyên.
- Giới hạn nội bộ của BigInteger và cấu hình JVM.

Một ước lượng gần đúng cho a khác 0, |a|>1 và số mũ e:

\[
\operatorname{bitLength}(|a^e|)
\approx e\log_2|a|+1
\]

Đây là **ước lượng kích thước**, không phải công thức đếm bit chính xác cho mọi n. Nếu parse một số mũ do người dùng gửi, đặt hạn mức theo ngữ cảnh ứng dụng **trước khi gọi pow**.

Nếu chỉ cần **a^e modulo m**, đừng tạo toàn bộ a^e rồi mới lấy remainder: dùng **BigInteger.modPow(exponent, modulus)** theo hợp đồng của nó để tiết kiệm tài nguyên. modPow là một API khác, đặc biệt hữu ích trong thuật toán modulo và mật mã; nó **không phải** phép lũy thừa nguyên thuần của bài này.

## 11. sqrt của số khổng lồ: không dùng căn double làm đáp án

Với n có hàng trăm chữ số, **sqrt()** cho kết quả nguyên đúng theo giá trị n. Ví dụ:

~~~java
BigInteger n = BigInteger.TEN.pow(40);
BigInteger s = n.sqrt();
// s bằng 10^20 = 100000000000000000000
~~~

Khi n là số chính phương, sqrtAndRemainder trả phần dư 0. Với số không chính phương, phần dư cho biết khoảng cách từ n đến bình phương s², và luôn nhỏ hơn 2s+1.

Một bài toán phổ biến là kiểm tra n có phải số chính phương trước khi phân tích thêm. Dùng **n.signum() < 0** để từ chối miền không hợp lệ, rồi:

~~~java
boolean perfect = n.sqrtAndRemainder()[1].signum() == 0;
~~~

Đoạn này cần n là BigInteger **không âm** và đã được khai báo. Không so sánh kết quả Math.sqrt(n.doubleValue()) với số nguyên lớn, vì doubleValue() có thể mất chính xác hoặc thành Infinity.

## 12. Dấu và exception: bảng kiểm biên

| Tình huống | Kết quả/hành vi |
| --- | --- |
| **BigInteger.valueOf(12).pow(5)** | 248832 |
| **BigInteger.valueOf(-3).pow(4)** | 81 |
| **BigInteger.valueOf(-3).pow(5)** | −243 |
| **BigInteger.ZERO.pow(0)** | 1 |
| **a.pow(-1)** | **ArithmeticException** |
| **BigInteger.ZERO.sqrt()** | 0 |
| **BigInteger.valueOf(200).sqrt()** | 14 |
| **BigInteger.valueOf(200).sqrtAndRemainder()** | [14, 4] |
| **BigInteger.valueOf(-1).sqrt()** | **ArithmeticException** |
| **BigInteger.valueOf(-1).sqrtAndRemainder()** | **ArithmeticException** |
| **BigInteger.valueOf(-54).gcd(BigInteger.valueOf(24))** | 6 |
| **BigInteger.ZERO.gcd(BigInteger.ZERO)** | 0 |

Nếu đối số là tham chiếu **null**, không coi nó là số 0. Tùy phương thức và vị trí null, chương trình có thể ném NullPointerException; khi xử lý dữ liệu bên ngoài, hãy kiểm tra null riêng trước các phép tính.

## 13. Kiểm tra đúng bằng bất biến thay vì chỉ so output

Một số điều kiện QA hữu ích:

- **pow**: với e chẵn, a.pow(e) không âm; với e lẻ, dấu kết quả theo dấu a; a.pow(0)=1.
- **sqrt**: s=n.sqrt() thì s≥0, s²≤n và (s+1)²>n.
- **sqrtAndRemainder**: n=s²+r, r≥0, r<2s+1; n chính phương khi r=0.
- **gcd**: g≥0, nếu g>0 thì a.remainder(g)=0 và b.remainder(g)=0; gcd(a,b)=gcd(b,a)=gcd(|a|,|b|); gcd(a,0)=|a|.
- **Bất biến**: a, b, n vẫn giữ giá trị ban đầu sau khi gọi các phương thức.

Kiểm thử cả **0, 1, số âm (nếu API cho phép), số chính phương và số sát hai phía số chính phương**, cũng như các số có hàng trăm chữ số. Với phép kiểm thử property-based, giới hạn kích thước n/e để bộ kiểm thử không tiêu thụ quá nhiều tài nguyên.

**Đừng chỉ kiểm tra giá trị dạng chuỗi rồi bỏ qua loại exception.** Điều kiện exponent âm của pow và radicand âm của sqrt là một phần hợp đồng API cần test.

## 14. Khác biệt phiên bản và cú pháp API

Tất cả ví dụ chạy độc lập ở đây hướng đến **Java 17+**:

- **BigInteger.pow(int)** nhận số mũ nguyên kiểu int không âm.
- **BigInteger.sqrt()** và **sqrtAndRemainder()** có từ **Java 9**, không có trong các bản Java 8 cũ.
- **BigInteger.gcd(BigInteger)** trả số không âm.
- **BigInteger.TWO** xuất hiện từ Java 9; nếu cần tương thích Java 8, dùng BigInteger.valueOf(2).

BigInteger không hỗ trợ operator overloading của toán tử **^** để tính lũy thừa. Trong Java, **^** trên kiểu nguyên thủy là phép XOR theo bit, **không phải** phép nâng lũy thừa. Để tính 2^10, viết **BigInteger.valueOf(2).pow(10)**, không viết 2 ^ 10.

Tương tự, không có phương thức **BigInteger.sqrt(double precision)** hay **pow(BigInteger exponent)** phù hợp với những ý nghĩa đơn giản trên. Dùng đúng chữ ký trong tài liệu API và thiết kế lại khi bài toán có loại đầu vào khác.

## 15. Chương trình Java 17+ chạy độc lập

Tạo tệp **BigIntegerOperationsDemo.java** với mã sau:

~~~java
import java.math.BigInteger;
import java.util.Arrays;

public class BigIntegerOperationsDemo {
    static void show(String label, BigInteger value) {
        System.out.println(label + ": " + value);
    }

    public static void main(String[] args) {
        BigInteger twelve = BigInteger.valueOf(12);
        BigInteger negativeThree = BigInteger.valueOf(-3);

        show("12^5", twelve.pow(5));
        show("(-3)^5", negativeThree.pow(5));
        show("(-3)^4", negativeThree.pow(4));
        show("10^20", BigInteger.TEN.pow(20));
        show("0^0", BigInteger.ZERO.pow(0));

        BigInteger n = BigInteger.valueOf(200);
        BigInteger[] pair = n.sqrtAndRemainder();

        show("floor sqrt(200)", n.sqrt());
        System.out.println("sqrtAndRemainder(200): "
                + Arrays.toString(pair));
        show("reconstruct(200)", pair[0].pow(2).add(pair[1]));

        BigInteger square = BigInteger.valueOf(123456789).pow(2);
        show("perfect-square root", square.sqrt());
        System.out.println("sqrtAndRemainder(81): "
                + Arrays.toString(
                        BigInteger.valueOf(81).sqrtAndRemainder()));

        show("gcd(-54, 24)",
                BigInteger.valueOf(-54).gcd(BigInteger.valueOf(24)));
        show("gcd(0, -24)",
                BigInteger.ZERO.gcd(BigInteger.valueOf(-24)));
        show("gcd(0, 0)",
                BigInteger.ZERO.gcd(BigInteger.ZERO));
        show("gcd(101, 24)",
                BigInteger.valueOf(101).gcd(BigInteger.valueOf(24)));

        show("sqrt(10^40)", BigInteger.TEN.pow(40).sqrt());

        try {
            negativeThree.pow(-1);
        } catch (ArithmeticException e) {
            System.out.println("negative exponent: ArithmeticException");
        }

        try {
            BigInteger.valueOf(-1).sqrt();
        } catch (ArithmeticException e) {
            System.out.println(
                    "negative square root: ArithmeticException");
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 BigIntegerOperationsDemo.java
java BigIntegerOperationsDemo
~~~

Stdout:

~~~text
12^5: 248832
(-3)^5: -243
(-3)^4: 81
10^20: 100000000000000000000
0^0: 1
floor sqrt(200): 14
sqrtAndRemainder(200): [14, 4]
reconstruct(200): 200
perfect-square root: 123456789
sqrtAndRemainder(81): [9, 0]
gcd(-54, 24): 6
gcd(0, -24): 24
gcd(0, 0): 0
gcd(101, 24): 1
sqrt(10^40): 100000000000000000000
negative exponent: ArithmeticException
negative square root: ArithmeticException
~~~

### Phân tích kết quả chương trình

1. **12^5** được tính là 248832. Trong Java, ký hiệu **^** ở phần tên nhãn chỉ là văn bản; để tính lũy thừa dùng phương thức pow.
2. **(-3)^5** âm, còn **(-3)^4** dương theo quy tắc số mũ lẻ/chẵn.
3. **10^20** là một số nguyên lớn được in đủ chữ số nhờ BigInteger, không có dạng ký pháp khoa học của double.
4. **0^0** trả 1 đúng quy ước API BigInteger.
5. **sqrt(200)** trả 14, còn **sqrtAndRemainder** trả [14,4], vì 14²=196 và 200−196=4.
6. Dòng reconstruct(200) kiểm tra bất biến **n=s²+r**.
7. Bình phương của 123456789 là số chính phương; sqrt lấy lại chính xác 123456789.
8. **sqrtAndRemainder(81)** có r=0 nên 81 là số chính phương.
9. gcd xử lý dấu âm, zero và cặp coprime đúng quy tắc.
10. Với số lớn 10^40, sqrt trả chính xác 10^20.
11. pow với exponent âm và sqrt với n âm đều ném **ArithmeticException**; chương trình bắt để minh họa mà không dừng sớm.

Những giá trị trên được kiểm tra bằng API BigInteger trên JDK. Các method sử dụng đều có trong Java 17.

## 16. Những lỗi phổ biến và cách tránh

| Lỗi | Tại sao sai | Hướng đúng |
| --- | --- | --- |
| Dùng toán tử **^** để tính số mũ | Trong Java ^ là XOR, không phải phép lũy thừa | Dùng **pow(int)** |
| Gọi **pow(-1)** để tính nghịch đảo | Số mũ âm không được chấp nhận | Biểu diễn phân số hoặc số thập phân theo bài toán |
| Chuyển n lớn sang double rồi Math.sqrt | Có thể mất độ chính xác/Infinity | Dùng **BigInteger.sqrt()** |
| Nghĩ sqrt(200) sẽ là 14.142... | API trả căn **nguyên** | Dùng BigDecimal.sqrt nếu thật sự cần căn thập phân và quy tắc precision |
| Nghĩ sqrt sẽ làm tròn gần nhất | sqrt lấy floor, không phải round | Kiểm tra s²≤n<(s+1)² |
| Cho rằng remainder là n % s | sqrtAndRemainder trả **n−s²** | Xác định đúng bất biến |
| Lấy phần tử thứ nhất của mảng làm remainder | Kết quả [0] là căn, [1] là dư | Gán rõ biến root/remainder |
| Kiểm tra n chính phương chỉ bằng Math.sqrt(n.doubleValue()) | Sai ở số lớn gần bình phương | Dùng sqrtAndRemainder()[1] == 0 |
| Gọi sqrt cho số âm mà không có chính sách | ArithmeticException | Kiểm tra signum trước |
| Nghĩ gcd(-54,24) = -6 | API trả số không âm | Kết quả =6 |
| Nghĩ gcd(0,0) ném exception | API định nghĩa kết quả 0 | Test trường hợp zero |
| Dùng gcd trước khi kiểm tra mẫu phân số bằng 0 | 0/0 vẫn không hợp lệ | Validate denominator != 0 |
| Nhân a*b rồi chia gcd để tính lcm với long | Có thể overflow long | BigInteger và chia gcd trước khi nhân |
| Bỏ qua kết quả **x.pow(e)** | BigInteger immutable | Gán đối tượng trả về |
| Chạy pow với exponent cực lớn từ input | Tốn nhiều bộ nhớ/CPU | Giới hạn exponent và kích cỡ output |
| Dùng BigInteger.pow cho a^e mod m | Tạo số trung gian lớn không cần thiết | Cân nhắc **modPow** |
| Dùng hằng BigInteger.TWO trên Java 8 | TWO có từ Java 9 | Java 17 hỗ trợ; Java 8 dùng valueOf(2) |

## 17. Bài tập thực hành

**Bài 1.** Tính 7^4 bằng BigInteger. Phương thức nào cần gọi?

*Đáp án:* **BigInteger.valueOf(7).pow(4)**, kết quả **2401**.

**Bài 2.** Giá trị **BigInteger.ZERO.pow(0)** là bao nhiêu? **BigInteger.TEN.pow(-1)** thì sao?

*Đáp án:* Trường hợp đầu trả **BigInteger.ONE (1)**; trường hợp sau ném **ArithmeticException** vì exponent âm.

**Bài 3.** Cho n=99, sqrtAndRemainder trả gì?

*Đáp án:* √99 nằm giữa 9 và 10, s=9, r=99−81=18, nên trả **[9,18]**. Phần dư này không phải 99%9.

**Bài 4.** Cho n=81, làm thế nào biết n chính phương mà không dùng double?

*Đáp án:* **n.sqrtAndRemainder()[1].signum() == 0** (với n là BigInteger không âm) hoặc so **n.sqrt().pow(2).equals(n)**.

**Bài 5.** gcd(-54, 24) và gcd(0,0) trả bao nhiêu?

*Đáp án:* **6** và **0** theo hợp đồng BigInteger.gcd.

**Bài 6.** Vì sao không lấy BigInteger.valueOf(101).gcd(BigInteger.valueOf(24)) bằng 101? Kết quả là gì?

*Đáp án:* 101 và 24 không có ước chung dương nào ngoài 1, nên gcd bằng **1**.

**Bài 7.** Rút gọn phân số 84/30 bằng gcd được bao nhiêu?

*Đáp án:* gcd(84,30)=6; tử mới 84/6=14, mẫu mới 30/6=5, tức **14/5**.

**Bài 8.** LCM của 84 và 30 bằng bao nhiêu? Nên tính theo thứ tự nào?

*Đáp án:* **420**. Lấy **84/gcd(84,30)=14**, sau đó nhân 30. Trong mã BigInteger nên xử lý đầu vào zero và dấu.

**Bài 9.** Vì sao cần giới hạn pow khi nhận cơ số và số mũ từ request HTTP, dù dùng BigInteger?

*Đáp án:* Kết quả có thể dài hàng triệu hoặc hàng tỷ bit, gây áp lực bộ nhớ/CPU và thậm chí vượt giới hạn triển khai. BigInteger không có nghĩa tài nguyên vô hạn.

**Bài 10.** Với n=200, chứng minh phần dư từ sqrtAndRemainder nằm trong khoảng cho phép.

*Đáp án:* s=14, r=4. **0≤4<2×14+1=29**, và **14²+4=200**.

## 18. Tài liệu tham khảo chính thức

- [BigInteger Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): chữ ký và hợp đồng **pow(int)**, **sqrt()**, **sqrtAndRemainder()**, **gcd(BigInteger)**, cùng những phương thức hỗ trợ.
- [BigDecimal Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): cân nhắc khi cần kết quả căn ở dạng thập phân thay vì căn nguyên; **sqrt(MathContext)** yêu cầu độ chính xác và quy tắc làm tròn.
- [Java SE 17 Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): đối chiếu **Math.sqrt(double)** với căn nguyên BigInteger và các giới hạn double.
- [Java Language Specification SE 17 — Integer Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.1): các giới hạn int/long và phép tính nguyên thủy.
