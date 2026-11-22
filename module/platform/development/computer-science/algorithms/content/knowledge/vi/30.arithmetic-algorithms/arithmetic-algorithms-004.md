# Nhân và lũy thừa theo modulo với kiểm soát tràn

Trong **Thuật toán số học** thuộc Computer Science Algorithms, **nhân modulo** và **lũy thừa modulo** là các phép tính nền tảng. Ta cần tìm phần dư của tích a·b hoặc lũy thừa a^e theo một số nguyên dương m. Các thao tác này xuất hiện trong bài đếm tổ hợp, số học ma trận, thuật toán số lớn, mật mã học, bài toán hàm băm số học và nhiều ứng dụng khác.

Khó khăn là **tràn số ở trung gian**: mặc dù kết quả cuối luôn thuộc [0,m−1], tích a·b có thể vượt giới hạn Java long **trước khi phép lấy phần dư được thực hiện**. Viết (a*b)%m không tự tạo ra phép nhân trên số nguyên vô hạn. Tương tự, trong lũy thừa nhanh, nếu bình phương base*base bằng long rồi mới lấy %m, một giá trị trung gian có thể sai dù thuật toán trên giấy hoàn toàn đúng.

Bài **“Nhân và lũy thừa theo modulo với kiểm soát tràn”** xây một quy trình an toàn cả khi modulus tới **Long.MAX_VALUE** và a,b nhận cả **Long.MIN_VALUE**. Các bước: chuẩn hóa phần dư âm, **cộng modulo tránh tràn**, **nhân theo bit bằng double-and-add**, rồi **lũy thừa nhị phân bằng bình phương liên tiếp**. Đi kèm là chứng minh bằng bất biến, vết chạy, phân tích thời gian, các trường hợp biên và chương trình Java 17+ đã chạy với oracle BigInteger độc lập.

## 1. Phát biểu bài toán và hợp đồng dữ liệu

Trong bài, a,b là các số nguyên có thể âm, m là modulus **dương**, e là số mũ **không âm**. Hai phép tính:

~~~text
multiply(a,b,m) = phần dư chuẩn của a*b theo m.
power(a,e,m)    = phần dư chuẩn của a^e theo m.
~~~

Kết quả luôn là đại diện không âm trong **[0,m−1]**. Đây là quy ước quan trọng với toán hạng âm vì phép `%` của Java không tự trả phần dư không âm.

~~~text
Miền long:
Long.MIN_VALUE = -9223372036854775808.
Long.MAX_VALUE =  9223372036854775807.

a,b có thể là mọi long có dấu.
1 <= m <= Long.MAX_VALUE.
0 <= e <= Long.MAX_VALUE.
~~~

Nếu modulus≤0 hoặc exponent<0, chương trình ném **IllegalArgumentException**. Khi m=1, đáp án mọi phép tính modulo bằng 0. Khi e=0, bài chọn quy ước a^0=1, kể cả a=0; khi đó giá trị trả là 1 mod m. Các trường hợp này được kiểm tra tường minh, không để phụ thuộc vào hành vi tình cờ.

## 2. Đồng dư là gì?

Ta viết a≡b(mod m) khi m chia hết cho a−b. Với m>0, mỗi số nguyên có duy nhất một đại diện r thuộc [0,m−1] trong lớp đồng dư của nó.

Các đẳng thức cơ bản:

~~~text
(a+b) mod m
 = ((a mod m)+(b mod m)) mod m.

(a*b) mod m
 = ((a mod m)*(b mod m)) mod m.

a^e mod m
 = ((a mod m)^e) mod m, với e>=0.
~~~

Những biến đổi trên đúng trong **số học nguyên toán học**, không giới hạn độ rộng. Nhưng trên Java long, mỗi phép cộng/nhân trung gian phải vừa miền biểu diễn. Giảm a,b trước theo m chỉ cho x,y<m; tích x*y vẫn có thể xấp xỉ m². Vì vậy **tính chất đồng dư không tự bảo vệ khỏi tràn số**.

## 3. Java `%` với số âm và Math.floorMod

Toán tử `%` của Java trả số dư có dấu theo số bị chia. Ví dụ:

~~~text
-2 % 7 == -2.
-9 % 7 == -2.

Math.floorMod(-2,7) == 5.
Math.floorMod(-9,7) == 5.
~~~

Về đồng dư, −2≡5(mod7), nên giá trị chuẩn là 5. Có thể tự chuẩn hóa khi m>0:

~~~text
r = a % m.
if (r < 0):
    r += m.
~~~

Nếu r âm thì −m<r<0, do đó r+m nằm trong (0,m), an toàn với m là long dương. Hàm **Math.floorMod(a,m)** đã diễn đạt trực tiếp quy ước, nên chương trình dùng nó sau khi kiểm tra m>0.

**Bẫy Long.MIN_VALUE:** Math.abs(Long.MIN_VALUE) vẫn cho giá trị âm vì trị tuyệt đối toán học 9223372036854775808 không vừa kiểu long. Do đó không dùng Math.abs để chuẩn hóa a/b âm trước khi quét bit hay chia lấy dư.

## 4. Phản ví dụ overflow: kết quả sai vẫn là số dương

Chọn:

~~~text
m = Long.MAX_VALUE = 9223372036854775807.
a = b = m-1 = 9223372036854775806.
~~~

Vì a≡−1(mod m), nên:

~~~text
a*b ≡ (-1)*(-1) ≡ 1 (mod m).
Đáp án chuẩn = 1.
~~~

Nhưng phép nhân a*b trên Java long **tràn**, cho giá trị long **4**, sau đó 4%m vẫn bằng 4. Đây là trường hợp nguy hiểm: kết quả sai không âm, nhỏ hơn m và dễ bị hiểu nhầm là đúng.

~~~java
long m = Long.MAX_VALUE;
long near = m - 1;
long raw = near * near;  // 4 do overflow.
long wrong = raw % m;    // 4 (sai).
~~~

Chương trình đầy đủ phía dưới in rõ **Near-long-max naive remainder: 4** đối chiếu **Near-long-max safe product: 1**. Không thể lấy %m ở cuối để khôi phục phần thông tin đã mất khi tràn.

## 5. Tại sao lấy modulo trước khi nhân vẫn sai?

Ngay cả khi x=a mod m và y=b mod m, hai số này có thể tới m−1. Viết:

~~~text
(a*b)%m
((a%m)*(b%m))%m
~~~

đều có nguy cơ tràn ở phép nhân. Chỉ khi chứng minh x*y≤Long.MAX_VALUE mới được nhân trực tiếp. Với hai số x,y đã chuẩn hóa không âm, điều kiện đủ là y=0 hoặc x≤Long.MAX_VALUE/y, **kiểm tra trước khi nhân**.

Khi m gần Long.MAX_VALUE không có cận tích an toàn cho mọi toán hạng. Ta sẽ xây phép nhân bằng **dịch bit và phép cộng modulo**. Nhưng chính x+y cũng có thể lớn hơn Long.MAX_VALUE, nên phải giải quyết **cộng modulo** trước.

## 6. Cộng hai phần dư đã chuẩn hóa mà không tràn

Giả sử:

~~~text
m>0.
0<=x<m.
0<=y<m.
~~~

Ta cần (x+y) mod m nhưng tránh tính x+y nếu tổng có thể quá lớn. Công thức:

~~~text
addNormalized(x,y,m):
    if x >= m-y:
        return x-(m-y).
    else:
        return x+y.
~~~

**Chứng minh an toàn:** vì 0≤y<m, phép m−y thuộc [1,m], không tràn. Nếu x≥m−y, ta biết x+y≥m; thay vì cộng rồi trừ m, lấy x−(m−y)=x+y−m, không tràn và thuộc [0,m). Nếu x<m−y, suy ra x+y<m≤Long.MAX_VALUE, nên cộng trực tiếp vừa long.

**Ví dụ cực đại:** m=Long.MAX_VALUE, x=y=m−1. Khi ấy m−y=1, nên addNormalized=(m−1)−1=m−2, đúng với −1−1≡−2(mod m). Với y=0, điều kiện x≥m không đúng, kết quả x; với m=1, x=y=0, kết quả 0.

Hàm chỉ dùng cho x,y **đã ở miền chuẩn**. Trong code nó là private; nếu muốn public cần chuẩn hóa hoặc kiểm tra input.

## 7. Nhân modulo bằng double-and-add

Mọi số không âm b có biểu diễn nhị phân. Ví dụ 13=(1101)₂=8+4+1. Do đó a·13=a·8+a·4+a, và ta có thể tính từng bội a,2a,4a,8a bằng **cộng đôi**, không cần nhân trực tiếp.

~~~text
multiply(a,b,m):
    x = normalize(a,m).
    bits = normalize(b,m).
    result = 0.

    while bits>0:
        if bit thấp của bits bằng 1:
            result = addNormalized(result,x,m).

        bits = bits >>> 1.
        if bits>0:
            x = addNormalized(x,x,m).

    return result.
~~~

Giảm b modulo m trước khi đọc bit là hợp lệ vì a*b≡a*(b mod m)(mod m). Sau chuẩn hóa bits không âm, dịch phải không dấu bỏ bit thấp đã xử lý. Mọi phép cộng và nhân đôi diễn ra bằng addNormalized, nên **không tạo tích lớn**.

Nếu b chuẩn hóa bằng 0, vòng lặp không chạy, trả 0. Nếu modulus=1, cả x và bits bằng 0, nên đáp án cũng là 0.

## 8. Ví dụ nhân 11·9 modulo 13

Tích số nguyên 11·9=99, 99 mod13=8. Chạy theo bit:

~~~text
x=11, bits=9=(1001)₂, result=0.
~~~

| Vòng | bits | Bit thấp | x | result sau xử lý | x sau nhân đôi |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 9 | 1 | 11 | 11 | 9 |
| 2 | 4 | 0 | 9 | 11 | 5 |
| 3 | 2 | 0 | 5 | 11 | 10 |
| 4 | 1 | 1 | 10 | 8 | Không cần |

Các lần nhân đôi:

~~~text
11+11=22 ≡ 9 (mod13).
9+9=18 ≡ 5 (mod13).
5+5=10 (mod13).
result cuối = 11+10=21 ≡ 8.
~~~

Từng bước dùng phép cộng có điều kiện để tránh tràn. Cách tính này không thay đổi nếu x gần Long.MAX_VALUE; nó vẫn chỉ làm việc với các phần dư an toàn.

## 9. Chứng minh nhân modulo bằng bất biến

Gọi a0=normalize(a,m), b0=normalize(b,m). Ở đầu mỗi vòng giữ:

~~~text
result + x*bits ≡ a0*b0 (mod m).
~~~

**Ban đầu:** result=0, x=a0, bits=b0 nên đúng.

**Bits chẵn:** bits=2q. Đổi bits←q và x←2x(mod m). Tổng mới result+(2x)q, đồng dư tổng cũ result+x(2q).

**Bits lẻ:** bits=2q+1. Cộng x vào result; đổi bits←q, x←2x. Tổng mới (result+x)+(2x)q đồng dư result+x(2q+1).

Tất cả phép cộng và nhân đôi trong chứng minh được thực hiện modulo qua addNormalized khi cài đặt. Vì vậy bất biến đồng dư được giữ, đồng thời mỗi biến vẫn ở [0,m).

**Kết thúc:** bits=0, suy ra result≡a0*b0≡a*b(mod m). Result là đại diện chuẩn duy nhất, nên đúng. Bits giảm ít nhất một nửa qua mỗi vòng, vì thế thuật toán kết thúc sau O(log m) bước và dùng O(1) bộ nhớ phụ. Với b0 dương thuộc long, có tối đa 63 bit.

## 10. Chuẩn hóa số âm và Long.MIN_VALUE

Nếu b âm, không được lập trình theo kiểu b=−b rồi sửa dấu ở cuối: với b=Long.MIN_VALUE, phép lấy âm cũng tràn. Phương pháp của bài là:

~~~text
x    = Math.floorMod(a,m).
bits = Math.floorMod(b,m).
~~~

Khi đó x,bits đều trong [0,m), nên có thể dùng phép dịch bit bình thường.

Với m=1.000.000.007:

~~~text
-2 ≡ 1000000005 (mod m).
(-2)*3 ≡ -6 ≡ 1000000001 (mod m).
(-2)^5 ≡ -32 ≡ 999999975 (mod m).
~~~

Với m=Long.MAX_VALUE:

~~~text
Long.MIN_VALUE ≡ -1 (mod m).
Long.MIN_VALUE * (-1) ≡ 1 (mod m).
~~~

Mã Java đưa những phép tính này vào main và so BigInteger trong bộ test. Tất cả modulus từ 1 tới Long.MAX_VALUE được chấp nhận, không cần modulus nguyên tố.

## 11. Lũy thừa modulo bằng bình phương liên tiếp

Cách ngây thơ tính a^e mod m bằng e lần nhân: đúng nếu từng phép nhân modulo an toàn, nhưng thời gian O(e log m), quá chậm khi e tới 10^18.

Ta dùng:

~~~text
a^(2q) = (a²)^q.
a^(2q+1) = a*(a²)^q.
~~~

Quét từng bit của e, bình phương cơ số mỗi vòng và nhân vào kết quả khi bit thấp bằng 1.

~~~text
power(a,e,m):
    yêu cầu m>0 và e>=0.

    base=normalize(a,m).
    result=1 mod m.
    bits=e.

    while bits>0:
        if bits lẻ:
            result=multiply(result,base,m).

        bits = bits >>> 1.
        if bits>0:
            base=multiply(base,base,m).

    return result.
~~~

**Quan trọng:** phải gọi multiply **an toàn** cho cả hai phép nhân. Nếu bình phương bằng base*base%m trực tiếp, nguy cơ tràn xuất hiện trở lại.

## 12. Vết lũy thừa 7^13 modulo 23

Ta biết 13=(1101)₂=8+4+1:

~~~text
7² mod23 = 49 mod23 = 3.
7⁴ mod23 = 3² mod23 = 9.
7⁸ mod23 = 9² mod23 = 12.
~~~

| Vòng | bits | Bit thấp | base | result sau xử lý |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 13 | 1 | 7 | 7 |
| 2 | 6 | 0 | 3 | 7 |
| 3 | 3 | 1 | 9 | 17 |
| 4 | 1 | 1 | 12 | 20 |

Ở vòng 3, 7·9=63≡17(mod23); ở vòng cuối, 17·12=204≡20(mod23). Vậy **7^13 mod23=20**.

Ưu điểm của phương pháp là không tạo số nguyên 7^13 trước rồi lấy modulo. Nếu thay m bằng một số sát Long.MAX_VALUE, vẫn dùng đúng phương pháp với phép nhân an toàn.

## 13. Chứng minh lũy thừa nhị phân bằng bất biến

Gọi base0=normalize(a,m) và exp0 là số mũ ban đầu. Bất biến đầu mỗi vòng:

~~~text
result * base^bits ≡ base0^exp0 (mod m).
~~~

**Khởi tạo:** result=1 mod m, base=base0, bits=exp0 nên đúng.

**Nếu bits chẵn:** bits=2q. Không đổi result; đặt bits←q, base←base². Ta có result*(base²)^q=result*base^(2q), đồng dư như cũ.

**Nếu bits lẻ:** bits=2q+1. Đặt result←result*base, bits←q, base←base². Ta có (result*base)*(base²)^q=result*base^(2q+1), đồng dư như cũ.

Mọi phép nhân ở trạng thái thực của chương trình đều qua multiply modulo, nên kết quả giữ đồng dư và nằm trong [0,m). Khi bits=0, bất biến cho result≡base0^exp0(mod m); do đó result đúng. Số vòng O(log(e+1)), mỗi vòng gọi tối đa hai phép nhân O(log m), tổng thời gian **O(log(e+1)·log(m+1))**, bộ nhớ phụ O(1).

## 14. Modulus 1, exponent 0 và 0^0

Các trường hợp biên:

| Đầu vào | Kết quả / hành vi |
| --- | --- |
| multiply(a,b,1) | 0 |
| power(a,e,1) với e≥0 | 0 |
| power(a,0,m), m>1 | 1 |
| power(0,0,m), m>1 | 1 theo quy ước của bài |
| power(0,e,m), e>0 | 0 |
| multiply(a,0,m) | 0 |
| multiply(0,b,m) | 0 |
| power(a,-1,m) | Lỗi đầu vào |
| multiply(a,b,0) | Lỗi đầu vào |
| power(a,e,-7) | Lỗi đầu vào |

Số mũ 0 nghĩa là tích rỗng, nên result ban đầu của power phải là **1 mod m**. Nếu m=1, 1 mod1=0; vì vậy code dùng **1L % modulus**, không phải trả nguyên số 1.

Biểu thức 0^0 có cách diễn giải tùy bài toán; trong thư viện số học và nhiều bài tổ hợp, quy ước 0^0=1 giúp đồng nhất với tích rỗng. Bài chọn quy ước này tường minh thay vì khẳng định nó là ý nghĩa toán học duy nhất.

## 15. Cận tràn và Math.multiplyExact

Math.multiplyExact phát hiện overflow của phép nhân long bằng cách ném ArithmeticException. Nó không tự tính phần dư đúng trong trường hợp tích lớn hơn miền long.

Nếu muốn một fast path, có thể chuẩn hóa x,y≥0 rồi kiểm tra:

~~~text
Nếu y==0 hoặc x<=Long.MAX_VALUE/y:
    tính trực tiếp (x*y)%m.
Ngược lại:
    dùng double-and-add.
~~~

Phải kiểm tra **trước phép nhân**. Không thể tính trước rồi dùng Math.abs hoặc dấu kết quả để phát hiện vì overflow có thể cho giá trị dương, như ví dụ raw=4.

Bản demo ưu tiên cách tính thống nhất bằng double-and-add để có một đường chứng minh và kiểm thử rõ ràng.

## 16. BigInteger là lựa chọn thay thế an toàn

Khi ứng dụng không buộc lõi thuật toán phải dùng long, BigInteger của Java là lựa chọn đáng tin:

~~~java
BigInteger m = BigInteger.valueOf(modulus);

BigInteger product = BigInteger.valueOf(a).mod(m)
    .multiply(BigInteger.valueOf(b).mod(m))
    .mod(m);

BigInteger power = BigInteger.valueOf(a).mod(m)
    .modPow(BigInteger.valueOf(exponent), m);
~~~

Với modulus>0, exponent≥0, các giá trị trên là phần dư chuẩn. BigInteger thực hiện phép nhân chính xác với độ dài tăng theo dữ liệu, không bị tràn kiểu long. BigInteger.modPow tính lũy thừa modulo hiệu quả mà không xây a^e nguyên lớn.

Trong chương trình thực hành, **oracleMultiply** và **oraclePower** dùng BigInteger để kiểm chứng **hai thuật toán long riêng biệt**. Đây là kiểm thử chéo giữa hai cách tính khác nhau, tránh việc một lỗi trong công thức double-and-add tái xuất hiện ở cả hai vế so sánh.

## 17. Số mũ âm và nghịch đảo modulo

Bản API không nhận e<0. Nếu muốn định nghĩa a^(−e) modulo m, cần nghịch đảo của a theo m, tồn tại khi:

~~~text
gcd(a,m) = 1.
~~~

Ví dụ 3 có inverse modulo 11 là 4 vì 3·4=12≡1(mod11). Ngược lại 2 không có inverse modulo 4. Nếu chưa kiểm tra điều kiện tồn tại mà tự chia theo modulo, kết quả không có nghĩa đúng.

Một API mở rộng có thể tìm nghịch đảo bằng Euclid mở rộng hoặc BigInteger.modInverse, rồi dùng lũy thừa với số mũ dương. Với exponent=Long.MIN_VALUE, biểu thức −exponent cũng tràn long; cần dùng biểu diễn rộng hơn hoặc BigInteger. Vì vậy mã trong bài **từ chối mọi số mũ âm** để giữ hợp đồng nhất quán.

## 18. Độ phức tạp và lựa chọn phương pháp

| Phương pháp | Thời gian | Bộ nhớ |
| --- | --- | --- |
| Chuẩn hóa bằng Math.floorMod | O(1) word RAM | O(1) |
| addNormalized | O(1) | O(1) |
| multiply bằng double-and-add | O(log m) | O(1) |
| power bằng multiply và bình phương liên tiếp | O(log(e+1)·log(m+1)) | O(1) |
| power nhân tuần tự e lần | O(e·log m) | O(1) |

Với long, số bit dương không quá 63, nên số vòng của mỗi lời gọi được chặn. Khi phân tích theo miền số hoặc chuyển sang số nguyên có độ rộng thay đổi, biểu thức O(log m) và O(log e·log m) cho biết chính xác hơn chi phí phụ thuộc vào kích thước dữ liệu.

Nếu bài cần hàng triệu phép nhân với cùng modulus, cân nhắc fast path có kiểm tra, BigInteger, Montgomery hay Barrett. Các phương pháp reduction nhanh có điều kiện riêng và thường cần số học độ rộng lớn, không thể chỉ thay một toán tử trong công thức. Bản double-and-add là baseline dễ chứng minh, đúng trên toàn miền long.

## 19. Java 17+ hoàn chỉnh và có oracle

Lưu mã dưới đây vào **SafeModularArithmetic.java**. Hai phương thức học chính là:

- **multiply(a,b,modulus)**: chuẩn hóa a,b; nhân theo bit bằng addNormalized không tràn.
- **power(base,exponent,modulus)**: lũy thừa nhị phân; mọi bình phương và nhân đều đi qua multiply.

Các hàm hỗ trợ:

- **normalize** dùng Math.floorMod.
- **addNormalized** tính tổng hai phần dư bằng so sánh x≥m−y.
- **oracleMultiply/oraclePower** tính bằng BigInteger.
- **checkMultiply/checkPower** so kết quả với oracle và kiểm tra miền [0,m).
- **verify** chạy vét cạn, random có seed, số long cực trị và đầu vào lỗi.

Trong main có một phép **near*near** được viết trực tiếp **chỉ để làm ví dụ overflow sai**, không xuất hiện trong lõi multiply/power an toàn.

~~~java
import java.math.BigInteger;
import java.util.Random;

public final class SafeModularArithmetic {
    private SafeModularArithmetic() { }

    private static void checkModulus(long modulus) {
        if (modulus <= 0) {
            throw new IllegalArgumentException("modulus must be positive");
        }
    }

    public static long normalize(long value, long modulus) {
        checkModulus(modulus);
        return Math.floorMod(value, modulus);
    }

    private static long addNormalized(long x, long y, long modulus) {
        if (x >= modulus - y) {
            return x - (modulus - y);
        }
        return x + y;
    }

    public static long multiply(long a, long b, long modulus) {
        checkModulus(modulus);
        long x = normalize(a, modulus);
        long bits = normalize(b, modulus);
        long result = 0;
        while (bits > 0) {
            if ((bits & 1L) != 0L) {
                result = addNormalized(result, x, modulus);
            }
            bits >>>= 1;
            if (bits > 0) {
                x = addNormalized(x, x, modulus);
            }
        }
        return result;
    }

    public static long power(long base, long exponent, long modulus) {
        checkModulus(modulus);
        if (exponent < 0) {
            throw new IllegalArgumentException("negative exponent");
        }
        long x = normalize(base, modulus);
        long result = 1L % modulus;
        long bits = exponent;
        while (bits > 0) {
            if ((bits & 1L) != 0L) {
                result = multiply(result, x, modulus);
            }
            bits >>>= 1;
            if (bits > 0) {
                x = multiply(x, x, modulus);
            }
        }
        return result;
    }

    private static long oracleMultiply(long a, long b, long modulus) {
        BigInteger m = BigInteger.valueOf(modulus);
        return BigInteger.valueOf(a).mod(m)
                .multiply(BigInteger.valueOf(b).mod(m))
                .mod(m).longValueExact();
    }

    private static long oraclePower(long a, long exponent, long modulus) {
        BigInteger m = BigInteger.valueOf(modulus);
        return BigInteger.valueOf(a).mod(m)
                .modPow(BigInteger.valueOf(exponent), m)
                .longValueExact();
    }

    private static void checkMultiply(long a, long b, long modulus) {
        long actual = multiply(a, b, modulus);
        long expected = oracleMultiply(a, b, modulus);
        if (actual != expected || actual < 0 || actual >= modulus) {
            throw new AssertionError("multiply mismatch: a=" + a
                    + " b=" + b + " m=" + modulus
                    + " actual=" + actual + " expected=" + expected);
        }
    }

    private static void checkPower(long a, long exponent, long modulus) {
        long actual = power(a, exponent, modulus);
        long expected = oraclePower(a, exponent, modulus);
        if (actual != expected || actual < 0 || actual >= modulus) {
            throw new AssertionError("power mismatch: a=" + a
                    + " exponent=" + exponent + " m=" + modulus
                    + " actual=" + actual + " expected=" + expected);
        }
    }

    private static void expectInvalid(Runnable operation) {
        try {
            operation.run();
        } catch (IllegalArgumentException correct) {
            return;
        }
        throw new AssertionError("invalid input accepted");
    }

    public static void verify() {
        int exhaustiveMultiply = 0;
        int exhaustivePower = 0;
        for (long modulus = 1; modulus <= 25; modulus++) {
            for (long a = -20; a <= 20; a++) {
                for (long b = -20; b <= 20; b++) {
                    checkMultiply(a, b, modulus);
                    exhaustiveMultiply++;
                }
                for (long exponent = 0; exponent <= 32; exponent++) {
                    checkPower(a, exponent, modulus);
                    exhaustivePower++;
                }
            }
        }

        Random random = new Random(3952026L);
        int seeded = 0;
        for (int i = 0; i < 1800; i++) {
            long a = random.nextLong();
            long b = random.nextLong();
            long modulus = random.nextLong() & Long.MAX_VALUE;
            if (modulus == 0) modulus = 1;
            long exponent = random.nextLong() & Long.MAX_VALUE;
            checkMultiply(a, b, modulus);
            checkPower(a, exponent, modulus);
            seeded++;
        }

        long[] moduli = {1, 2, 3, 97, 1_000_000_007L,
                Long.MAX_VALUE - 1, Long.MAX_VALUE};
        long[] values = {Long.MIN_VALUE, Long.MIN_VALUE + 1,
                -Long.MAX_VALUE, -1, 0, 1, 2,
                Long.MAX_VALUE - 1, Long.MAX_VALUE};
        long[] exponents = {0, 1, 2, 3, 63, 64,
                1_000_000_000L, Long.MAX_VALUE};
        int boundaryMultiply = 0, boundaryPower = 0;
        for (long modulus : moduli) {
            for (long a : values) {
                for (long b : values) {
                    checkMultiply(a, b, modulus);
                    boundaryMultiply++;
                }
                for (long exponent : exponents) {
                    checkPower(a, exponent, modulus);
                    boundaryPower++;
                }
            }
        }

        expectInvalid(() -> normalize(7, 0));
        expectInvalid(() -> multiply(1, 2, -7));
        expectInvalid(() -> power(2, 4, 0));
        expectInvalid(() -> power(2, -1, 7));
        expectInvalid(() -> power(2, Long.MIN_VALUE, 7));

        System.out.println("Exhaustive products: "
                + exhaustiveMultiply + " PASS");
        System.out.println("Exhaustive powers: "
                + exhaustivePower + " PASS");
        System.out.println("Seeded product/power pairs: "
                + seeded + " PASS");
        System.out.println("Boundary products: "
                + boundaryMultiply + " PASS");
        System.out.println("Boundary powers: "
                + boundaryPower + " PASS");
        System.out.println("Invalid-input checks: PASS");
    }

    public static void main(String[] args) {
        long large = Long.MAX_VALUE;
        long near = large - 1;
        long raw = near * near;
        System.out.println("normalize(-2,7): " + normalize(-2, 7));
        System.out.println("(-2 * 3) mod 1000000007: "
                + multiply(-2, 3, 1_000_000_007L));
        System.out.println("(-2)^5 mod 1000000007: "
                + power(-2, 5, 1_000_000_007L));
        System.out.println("2^10 mod 1000000007: "
                + power(2, 10, 1_000_000_007L));
        System.out.println("Near-long-max raw multiply: " + raw);
        System.out.println("Near-long-max naive remainder: " + raw % large);
        System.out.println("Near-long-max safe product: "
                + multiply(near, near, large));
        System.out.println("Long.MIN_VALUE * (-1) mod Long.MAX_VALUE: "
                + multiply(Long.MIN_VALUE, -1, large));
        System.out.println("0^0 mod 7 by convention: " + power(0, 0, 7));
        System.out.println("a^0 mod 1: " + power(999, 0, 1));
        verify();
    }
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac SafeModularArithmetic.java
java SafeModularArithmetic
~~~

**Stdout chính xác quan sát được:**

~~~text
normalize(-2,7): 5
(-2 * 3) mod 1000000007: 1000000001
(-2)^5 mod 1000000007: 999999975
2^10 mod 1000000007: 1024
Near-long-max raw multiply: 4
Near-long-max naive remainder: 4
Near-long-max safe product: 1
Long.MIN_VALUE * (-1) mod Long.MAX_VALUE: 1
0^0 mod 7 by convention: 1
a^0 mod 1: 0
Exhaustive products: 42025 PASS
Exhaustive powers: 33825 PASS
Seeded product/power pairs: 1800 PASS
Boundary products: 567 PASS
Boundary powers: 504 PASS
Invalid-input checks: PASS
~~~

Dòng naive remainder=4 là **sai cố ý** do overflow, còn safe product=1 là đáp án đúng. Mọi dòng PASS được in sau khi đối chiếu với BigInteger; bất kỳ mismatch nào khiến chương trình ném AssertionError.

## 20. Kiểm thử vét cạn 42.025 phép nhân

Mã duyệt các giá trị:

~~~text
m từ 1 tới 25: 25 modulus.
a từ -20 tới 20: 41 giá trị.
b từ -20 tới 20: 41 giá trị.

Tổng phép nhân = 25*41*41 = 42025.
~~~

Với mỗi (a,b,m), expected do BigInteger tính chính xác sau khi chuẩn hóa; actual do hàm multiply long tính. Bộ kiểm thử còn xác nhận **0≤actual<m**.

Vét cạn bao phủ m=1, số âm, số 0, hai số trái dấu và nhiều trường hợp giá trị bằng m hay lớn hơn m. Nó đặc biệt hữu ích để phát hiện lỗi quét bit, số dư âm, nhánh cộng modulo hay phép dịch bit. Tuy nhiên số nhỏ chưa làm long tràn; phần random/boundary bên dưới tập trung vào các số lớn.

## 21. Kiểm thử vét cạn 33.825 phép lũy thừa

Giữ nguyên 25 modulus và 41 cơ số a, cho exponent từ 0 tới 32 (33 giá trị):

~~~text
Tổng phép power = 25*41*33 = 33825.
~~~

Oracle dùng BigInteger.modPow với số mũ không âm. Bộ kiểm thử bao phủ e=0, a=0, a âm, m=1, số mũ chẵn/lẻ và các cơ số có phần dư 0. Đồng thời kiểm tra kết quả luôn ở miền [0,m).

Vì bộ thử power không dựa vào hàm multiply long khác để tính đáp án, nếu cả hàm multiply và power cùng chứa lỗi overflow thì oracle BigInteger vẫn có khả năng phát hiện.

## 22. Kiểm thử random và giới hạn 64-bit

Seed cố định là **Random(3952026L)**. Chương trình sinh **1.800 bộ**, mỗi bộ gồm a,b lấy từ random.nextLong(), modulus m là một long không âm đã điều chỉnh thành dương, exponent là một long không âm. Mỗi bộ so một phép nhân và một phép lũy thừa với BigInteger.

Bộ biên khác sử dụng:

~~~text
7 modulus:
1, 2, 3, 97, 1000000007,
Long.MAX_VALUE-1, Long.MAX_VALUE.

9 toán hạng:
Long.MIN_VALUE, Long.MIN_VALUE+1,
-Long.MAX_VALUE, -1, 0, 1, 2,
Long.MAX_VALUE-1, Long.MAX_VALUE.

8 số mũ:
0, 1, 2, 3, 63, 64,
1000000000, Long.MAX_VALUE.
~~~

Vậy có **567=7·9·9** phép nhân biên và **504=7·9·8** phép lũy thừa biên. Những giá trị này chủ động kiểm tra trường hợp có thể tràn do Long.MIN_VALUE và m gần Long.MAX_VALUE. Các ca modulus bằng 0, âm, exponent âm cũng được xác nhận bị từ chối đúng hợp đồng.

## 23. Những lỗi thường gặp

1. **Viết (a*b)%m** với hai số lớn và nghĩ rằng modulo tự cứu overflow.
2. **Chuẩn hóa trước rồi vẫn nhân trực tiếp** mà không kiểm tra tích vừa long.
3. **Dùng (x+y)%m** trong double-and-add, làm tràn ở phép cộng.
4. **Tính x+y để so với m** trong điều kiện rẽ nhánh.
5. **Không đảm bảo 0≤x,y<m** trước khi gọi addNormalized.
6. **Dùng Math.abs(Long.MIN_VALUE)** và nhận giá trị âm.
7. **Đổi dấu b=−b** khi b=Long.MIN_VALUE.
8. **Nhầm `%` Java với phần dư chuẩn không âm**.
9. **Nhân đôi x*2 rồi mới lấy modulo**, gây tràn.
10. **Quên cộng x khi bit thấp của bits bằng 1**.
11. **Dịch bits hoặc bình phương sai thứ tự**, làm mất hạng.
12. **Dùng base*base%m trong power**, bỏ qua phép nhân an toàn.
13. **Khởi tạo result=1 và quên `%m`**, sai với m=1,e=0.
14. **Không quy định 0^0** cho API.
15. **Nhận m=0 vào `%` hay floorMod**, gây ngoại lệ ngoài hợp đồng.
16. **Dùng Math.pow(double)** để tính lũy thừa nguyên chính xác lớn.
17. **Cho exponent âm đi qua vòng quét bit**, không có chứng minh.
18. **Dùng phép chia modulo không kiểm tra gcd và inverse**.
19. **Tự giả định m nguyên tố** khi muốn áp dụng các định lý đặc biệt.
20. **Nghĩ overflow luôn tạo số âm**, trong ví dụ raw=4 dương nhưng sai.
21. **Chỉ test số nhỏ**, không thử modulus sát Long.MAX_VALUE.
22. **Chỉ test modulus nguyên tố**, bỏ m=1 và hợp số.
23. **Không dùng oracle độc lập** cho các tính toán số học.
24. **Đánh giá power chỉ O(log e)** mà quên mỗi multiply mất O(log m).
25. **Tối ưu reduction trước khi chứng minh**, dễ mắc lỗi carry và dấu.

## 24. Bài tập thực hành

**Bài 1 — Phản ví dụ tràn:** đặt m=Long.MAX_VALUE, a=b=m−1. Chứng minh đáp án đúng bằng 1 nhưng phép nhân long trực tiếp cho raw=4.

**Bài 2 — Chuẩn hóa:** tính floorMod(−2,7) và floorMod(Long.MIN_VALUE,Long.MAX_VALUE). So với toán tử `%` của Java.

**Bài 3 — Cộng an toàn:** chứng minh công thức addNormalized khi x≥m−y và khi x<m−y; thử y=0, m=1, x=y=m−1.

**Bài 4 — Nhân tay:** dựng bảng double-and-add cho 11·9 mod13 và đối chiếu kết quả 8.

**Bài 5 — Bất biến nhân:** giải thích vì sao result+x*bits≡a0*b0(mod m) vẫn đúng qua từng bit và vì sao thuật toán kết thúc.

**Bài 6 — Lũy thừa tay:** tính 7^13 mod23 và xác nhận kết quả 20 mà không cần tạo 7^13 nguyên.

**Bài 7 — Bất biến lũy thừa:** chứng minh result*base^bits≡base0^exp0(mod m) cho trường hợp bit thấp 0/1.

**Bài 8 — 0^0 và modulus 1:** xác định power(0,0,7) và power(0,0,1) theo quy ước đã chốt.

**Bài 9 — Số mũ âm:** tìm nghịch đảo của 3 modulo 11, giải thích tại sao 2 không có inverse modulo 4.

**Bài 10 — Oracle:** viết chương trình BigInteger so mọi a,b trong [−20,20], m trong [1,25], e trong [0,32].

**Bài 11 — Fast path:** kiểm tra x≤Long.MAX_VALUE/y trước khi nhân trực tiếp, dùng double-and-add nếu không an toàn. So lại bộ test cực trị.

**Bài 12 — Ma trận modulo:** dùng addNormalized và multiply để nhân ma trận có phần tử long rất lớn, không tràn ở cả tích và tổng.

**Bài 13 — Modulus hợp số:** thử m=8,9,10,12 và giải thích vì sao phép nhân/lũy thừa vẫn đúng mà không cần modulus nguyên tố.

**Bài 14 — Phương pháp nhanh hơn:** nghiên cứu Montgomery reduction, nêu điều kiện modulus lẻ, bất biến của phép biến đổi và kế hoạch kiểm thử bằng BigInteger.

## 25. Áp dụng trong thuật toán lớn hơn

**Tích lũy liên tiếp:** giả sử cần tính tích của n số theo modulo m. Bắt đầu result=1 mod m, sau đó thay mỗi phép nhân bằng multiply(result,a[i],m). Như vậy mọi lần cập nhật đều an toàn; nếu dùng nhân trực tiếp rồi `%`, chỉ một lần tràn đã làm sai toàn bộ kết quả phía sau.

**Fibonacci hoặc lũy thừa ma trận:** mỗi phần tử kết quả là tổng của nhiều tích. Không chỉ nhân modulo phải an toàn, mà **cộng nhiều kết quả modulo** cũng cần addNormalized; nếu cộng long trước rồi mod thì vẫn tràn. Áp dụng kỹ thuật này giúp giữ toàn bộ ma trận trong miền [0,m).

**Tổ hợp modulo:** nhiều công thức dùng giai thừa, tích hoặc nghịch đảo. Phần nhân/lũy thừa của bài không yêu cầu modulus nguyên tố; nhưng nếu công thức có chia, phải kiểm tra sự tồn tại của nghịch đảo hoặc sử dụng một thuật toán khác phù hợp modulus hợp số.

**Mã hóa và lý thuyết số:** khi modulus lớn và số lượng phép tính nhiều, BigInteger.modPow hoặc reduction tối ưu thường hiệu quả hơn. Tuy nhiên cách double-and-add là một bước học chắc chắn để hiểu lý do những triển khai khác phải giải quyết overflow, carry và miền số.

## 26. Kết luận và checklist

Trước khi dùng phép nhân hoặc lũy thừa modulo trên long, hãy tự xác nhận:

- Modulus **dương** và quy ước phần dư [0,m) được áp dụng nhất quán.
- Toán hạng âm và Long.MIN_VALUE được chuẩn hóa **không dùng Math.abs**.
- Không có phép nhân trực tiếp nào có thể vượt Long.MAX_VALUE trước khi modulo.
- addNormalized chỉ nhận các phần dư chuẩn và không thực hiện tổng nguy hiểm trước.
- multiply theo bit dùng addNormalized cho **cả cộng lẫn nhân đôi**.
- power dùng multiply an toàn cho **cả bình phương lẫn nhân vào kết quả**.
- Exponent=0, modulus=1, base=0 và exponent âm có hành vi xác định.
- Kiểm thử có oracle BigInteger, số âm, modulus hợp số và ca gần giới hạn 64-bit.

**Điểm nhớ cuối cùng:** *Kết quả modulo nhỏ không có nghĩa trung gian tính toán nhỏ*. Dùng **cộng modulo tránh tràn → double-and-add → binary exponentiation** cùng bất biến đồng dư sẽ tạo lời giải chính xác trên toàn miền long; kiểm thử BigInteger giúp phát hiện những trường hợp mà phép toán tràn cho ra một số trông hoàn toàn bình thường.
