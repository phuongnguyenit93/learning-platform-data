# Tính tổ hợp theo modulo và giả thiết về môđun

**Chủ đề:** Computer Science Algorithms · Thuật toán số học

## 1. Tại sao môđun quyết định thuật toán?

Số tổ hợp chập k của n, ký hiệu C(n,k) hoặc \(\binom{n}{k}\), đếm số cách chọn k phần tử không xét thứ tự từ n phần tử phân biệt. Khi 0≤k≤n:

\[
\binom{n}{k}=\frac{n!}{k!(n-k)!}.
\]

Bài toán lập trình yêu cầu **C(n,k) mod m**, trong đó m là một số nguyên dương. Giá trị C(n,k) có thể lớn hơn mọi kiểu số nguyên cố định; lấy phần dư giúp trả lời ngắn gọn. Nhưng điều đó **không có nghĩa có thể lấy modulo mọi giai thừa rồi chia như phép chia thông thường**.

Trước khi chọn công thức, cần kiểm tra:
1. **m có nguyên tố không?** Phép nghịch đảo dựa trên Fermat đòi môđun nguyên tố.
2. **Nếu m=p là nguyên tố, n có nhỏ hơn p không?** Với n≥p, n!≡0 (mod p), không có nghịch đảo.
3. **Mẫu số cần chia có khả nghịch không?** a có nghịch đảo mod m khi và chỉ khi gcd(a,m)=1.
4. **Có bao nhiêu truy vấn và kích thước n,k?** Một bảng giai thừa thích hợp cho nhiều truy vấn với giới hạn n, còn Pascal DP hoặc BigInteger có thể dễ kiểm chứng hơn cho truy vấn nhỏ và môđun hợp số.

Bài học lần lượt trình bày **Pascal DP cho mọi môđun dương**, **factorial/inverse factorial cho p nguyên tố với n<p**, **định lý Lucas cho n lớn khi p nguyên tố**, và **BigInteger/prime powers/CRT cho môđun hợp số**. Mã Java 17 chủ động kiểm tra những giả thiết có thể gây sai đáp án.

## 2. Định nghĩa và trường hợp biên

Với n≥0, ta quy ước:

\[
C(n,0)=C(n,n)=1,
\qquad C(n,k)=0\text{ nếu }k<0\text{ hoặc }k>n.
\]

Công thức đối xứng:

\[
C(n,k)=C(n,n-k).
\]

Nhờ vậy trong phép tính tích, có thể lấy r=min(k,n−k), giảm số bước lặp.

**Công thức Pascal** với 0<k<n:

\[
\boxed{C(n,k)=C(n-1,k-1)+C(n-1,k)}.
\]

Chứng minh: chọn một phần tử phân biệt x. Một nhóm k phần tử hoặc chứa x (chọn thêm k−1 trong n−1 phần tử còn lại), hoặc không chứa x (chọn k trong n−1 phần tử). Hai trường hợp rời nhau và bao phủ mọi tổ hợp.

### Môđun 1 không giống môđun nguyên tố

Với m=1, mọi số nguyên có phần dư bằng 0:

~~~text
C(0,0) = 1, nhưng C(0,0) mod 1 = 0
C(5,2) = 10, nhưng C(5,2) mod 1 = 0
~~~

Môđun 1 là số nguyên dương hợp lệ cho Pascal và BigInteger rồi mod, nhưng **không phải số nguyên tố** và không được dùng công thức nghịch đảo Fermat.

Trong các API Java của bài:
- n<0: từ chối bằng IllegalArgumentException.
- k<0 hoặc k>n: trả 0 theo quy ước tổ hợp.
- m≤0: từ chối vì môđun không hợp lệ.
- Bảng tiền xử lý cho n tới N: từ chối truy vấn n vượt N, không âm thầm truy cập sai bảng.

## 3. Phép chia modulo có thực sự tồn tại?

Trong số nguyên:

\[
C(6,2)=\frac{6\cdot5}{2}=15.
\]

Còn modulo 12, phép chia cho 2 **không được định nghĩa bằng một nghịch đảo**, vì không tồn tại x sao cho 2x≡1 (mod 12).

Muốn thực hiện phép chia cho b modulo m, cần tìm b^−1 thỏa:

\[
b\cdot b^{-1}\equiv1\pmod m.
\]

Điều kiện cần và đủ:

\[
\boxed{\gcd(b,m)=1}.
\]

Ví dụ:
- b=3, m=8: nghịch đảo tồn tại và bằng 3, vì 3×3≡1 (mod 8).
- b=2, m=12: không có nghịch đảo vì gcd(2,12)=2.

Phương trình 2x≡6 (mod 12) có hai lớp nghiệm x≡3 và x≡9 (mod 12). Không có một phép “chia 6 cho 2 modulo 12” xác định duy nhất. Tuy nhiên, **C(6,2) mod 12 vẫn bằng 3**, vì đó là phần dư của tổ hợp nguyên 15. Lỗi ở cách lấy nghịch đảo không tồn tại, không phải ở định nghĩa kết quả.

### Fermat nhỏ, không phải phép màu cho mọi môđun

Nếu p **nguyên tố** và a không chia hết cho p, định lý Fermat nhỏ cho:

\[
a^{p-1}\equiv1\pmod p.
\]

Suy ra:

\[
\boxed{a^{-1}\equiv a^{p-2}\pmod p}
\]

với **hai điều kiện đồng thời**: p nguyên tố và a mod p khác 0.

Ví dụ modulo 7, inverse(3)=5 vì 3×5=15≡1 (mod 7). Lũy thừa 3^(7−2)=3^5 cũng cho 5 modulo 7.

Phản ví dụ với m=8 hợp số: 3 vẫn có nghịch đảo bằng 3, nhưng 3^(8−2)=3^6≡1 (mod 8), **không phải nghịch đảo**. Thay p bằng m trong số m−2 là sai về mặt toán học.

Với m hợp số, có thể dùng **Euclid mở rộng** để tìm nghịch đảo khi gcd(a,m)=1. Nhưng nếu gcd khác 1 thì không có nghịch đảo, dù dùng Euclid hay lũy thừa.

## 4. Phương pháp Pascal DP: không bao giờ cần phép chia

Từ công thức Pascal, sau khi lấy modulo m:

\[
C(n,k)\bmod m=
(C(n-1,k-1)+C(n-1,k))\bmod m.
\]

Phương pháp này đúng với **mọi m≥1**, bất kể nguyên tố hay hợp số.

Dùng mảng dp[0..r], r=min(k,n−k):
1. dp[0]=1 mod m.
2. Với mỗi hàng i từ 1 đến n, cập nhật j từ min(i,r) **giảm dần** về 1:
   \[
   dp[j]=(dp[j]+dp[j-1])\bmod m.
   \]
3. Trả dp[r].

**Lý do duyệt từ phải sang trái:** dp[j] và dp[j−1] phải đều thuộc hàng Pascal trước. Nếu duyệt j tăng dần, dp[j−1] đã là giá trị hàng mới, làm sai công thức.

Ví dụ:

~~~text
C(6,2) = 15; 15 mod 12 = 3
C(10,3) = 120; 120 mod 8 = 0
C(0,0) = 1; 1 mod 1 = 0
~~~

Không trường hợp nào cần môđun nguyên tố.

**Độ phức tạp:** O(nr) phép cộng modulo và O(r) bộ nhớ, với r=min(k,n−k). Với n lớn hàng tỷ, ngay cả r=1 thì số vòng theo n quá lớn, nên Pascal chỉ hợp khi n vừa phải.

### Tránh overflow ngay trong phép cộng

Nếu a,b đã trong [0,m−1] và m gần Long.MAX_VALUE, a+b có thể tràn long **trước khi lấy phần dư**. Dùng quy tắc:

~~~text
if a >= m-b:
    answer = a - (m-b)
else:
    answer = a+b
~~~

Trong nhánh đầu, kết quả bằng a+b−m nhưng không tính tổng dễ tràn. Trong nhánh sau, a+b<m nên không tràn. Code áp dụng quy tắc này cho mọi môđun long dương.

## 5. Khi p nguyên tố và n<p: factorial/inverse factorial

Với p nguyên tố và **n<p**, tất cả các số 1,2,...,n đều khác 0 modulo p. Do đó n!, k!, (n−k)! đều **khả nghịch**.

Đặt:
- fact[i] = i! mod p.
- invFact[i] = (i!)^−1 mod p.

Khi 0≤k≤n<p:

\[
\boxed{C(n,k)\equiv fact[n]\cdot invFact[k]\cdot invFact[n-k]\pmod p}.
\]

### Tiền xử lý một bảng cho nhiều truy vấn

Cho giới hạn N, bắt buộc **N<p**.

- fact[0]=1 và fact[i]=fact[i−1]×i mod p.
- Tính invFact[N]=fact[N]^(p−2) mod p bằng lũy thừa nhị phân.
- Với i=N,N−1,...,1, tính invFact[i−1]=invFact[i]×i mod p.

Vì i! = (i−1)!×i, từ nghịch đảo i! nhân với i thu được nghịch đảo (i−1)!.

Chi phí:
- O(N) phép nhân để xây factorial.
- O(log p) phép nhân cho một nghịch đảo.
- O(N) phép nhân để suy ra các inverse factorial còn lại.
- O(N) bộ nhớ.
- Sau tiền xử lý, mỗi truy vấn trong bảng dùng O(1) phép nhân modulo.

Các cận trên đếm phép toán ở mức cao; nếu dùng BigInteger cho phép nhân an toàn, một phép toán còn phụ thuộc độ dài bit của p.

### Ví dụ p=7

Có thể xây bảng đến N=6 vì 6<7.

~~~text
C(5,2)=10 => 3 mod 7
C(6,3)=20 => 6 mod 7
~~~

### Tại sao không được lấy N≥p?

Khi n≥p, n! chứa thừa số p nên:

\[
n!\equiv0\pmod p.
\]

**Zero không có nghịch đảo modulo p.**

Phản ví dụ:

\[
C(8,7)=8\equiv1\pmod7.
\]

Nhưng 8! và 7! đều bằng 0 modulo 7, nên công thức dùng invFact[8] hay invFact[7] hoàn toàn không hợp lệ. Một chương trình có thể chạy ra 0 do nghịch đảo giả của 0, nhưng đáp án thật là 1.

Lưu ý tinh tế: nếu n≥p nhưng **k<p**, công thức tích k thừa số ở tử chia k! vẫn có thể tính trong modulo p, bởi k! khả nghịch. Điều kiện n<p ở đây là điều kiện cho **bảng giai thừa đến n**; nó không có nghĩa mọi cách tính C(n,k) đều thất bại khi n≥p.

## 6. Định lý Lucas khi n có thể lớn hơn p

Với p nguyên tố, viết n và k dưới dạng chữ số cơ số p:

\[
n=n_0+n_1p+n_2p^2+\cdots,
\qquad
k=k_0+k_1p+k_2p^2+\cdots.
\]

**Định lý Lucas**:

\[
\boxed{C(n,k)\equiv\prod_{i\ge0}C(n_i,k_i)\pmod p}.
\]

Mỗi chữ số n_i,k_i nhỏ hơn p. Nếu có một chữ số k_i>n_i thì C(n_i,k_i)=0, và toàn bộ kết quả bằng 0.

### Ví dụ 1: C(8,7) mod 7

Viết ở cơ số 7:

~~~text
8 = (11) base 7: digits [1,1] từ thấp lên cao
7 = (10) base 7: digits [0,1] từ thấp lên cao
~~~

Vậy C(8,7)≡C(1,0)×C(1,1)=1 modulo 7.

### Ví dụ 2: C(10,3) mod 7

~~~text
10 = (13) base 7: digits [3,1]
 3 = (03) base 7: digits [3,0]
~~~

Vậy C(10,3)≡C(3,3)×C(1,0)=1 modulo 7. Thực tế C(10,3)=120 và 120 mod 7=1.

### Ví dụ 3: C(100,30) mod 7

~~~text
100 = (202) base 7: digits [2,0,2]
 30 = (042) base 7: digits [2,4,0]
~~~

Chữ số thứ hai từ phải có k_i=4>n_i=0, nên C(100,30)≡**0** (mod 7).

### Chi phí của Lucas

Có O(log_p(n+1)) cặp chữ số. Nếu p nhỏ, có thể dựng bảng factorial/invFact đến p−1 để tính mỗi C(n_i,k_i) nhanh. Tuy nhiên, nếu p rất lớn, bảng kích thước O(p) có thể không phù hợp.

Bản Java trong bài tính từng C(n_i,k_i) bằng tích:
- r_i=min(k_i,n_i−k_i).
- Tích tử n_i−r_i+1 đến n_i modulo p.
- Tích mẫu 1 đến r_i modulo p.
- Lấy nghịch đảo mẫu bằng Fermat.

Vì r_i<p, mẫu không chứa thừa số p nên có nghịch đảo. Chi phí tùy thuộc **tổng các r_i**, có thể rất lớn với p cỡ 10^9 và chữ số k_i gần p/2. **Lucas đúng về toán học không có nghĩa mọi cách cài Lucas đều nhanh**.

Lucas **yêu cầu p nguyên tố**; không được thay p bằng 8 hoặc 12 rồi cho rằng công thức chữ số vẫn đúng.

## 7. Môđun hợp số: Pascal, BigInteger hay prime powers + CRT?

Khi m hợp số, factorial của các mẫu số có thể không khả nghịch. Có ba hướng phổ biến.

### 7.1. Dùng Pascal DP

Không có phép chia nên kết quả đúng với mọi m≥1. Phù hợp n,k vừa phải.

### 7.2. Tính tổ hợp nguyên chính xác bằng BigInteger rồi mod

Đặt r=min(k,n−k) và result=1. Với i từ 1 đến r:

\[
result\gets result\cdot\frac{n-r+i}{i}.
\]

Phép tính được thực hiện theo thứ tự **nhân BigInteger rồi chia BigInteger**, **trước khi lấy modulo**. Sau bước i, result=C(n−r+i,i), luôn là số nguyên; do đó phép chia ở mỗi bước là chia chính xác, không mất phần dư.

~~~text
result = 1
for i=1..r:
    result = (result * (n-r+i)) / i   // số nguyên chính xác
return result mod m
~~~

Đây **không phải phép chia trong vành modulo m** nên không yêu cầu inverse(i,m).

Ví dụ:
- C(6,2)=15, modulo 12 được 3.
- C(10,3)=120, modulo 8 được 0.
- C(200,100) modulo 1.000.000.006 được **98.670.600**.

Ưu điểm: dễ hiểu, đúng với mọi m≥1 và rất hữu ích làm oracle kiểm thử. Hạn chế: số tổ hợp nguyên có thể rất lớn; dù chỉ có r vòng, mỗi phép nhân/chia BigInteger có chi phí theo độ dài bit của số trung gian.

### 7.3. Phân tích m thành các lũy thừa nguyên tố

Với m lớn, nhiều truy vấn, có thể phân tích:

\[
m=\prod_i p_i^{e_i}.
\]

Các \(p_i^{e_i}\) là những môđun đôi một nguyên tố cùng nhau. Ta:
1. Tính C(n,k) mod từng p_i^{e_i} bằng thuật toán phù hợp.
2. Ghép các kết quả bằng **Định lý phần dư Trung Hoa (CRT)** thành số duy nhất trong [0,m−1].

Ví dụ m=12=4×3 và C(6,2)=15:

~~~text
15 mod 4 = 3
15 mod 3 = 0
CRT: x ≡ 3 (mod 4), x ≡ 0 (mod 3)
=> x ≡ 3 (mod 12)
~~~

**Không áp dụng Lucas nguyên bản cho modulo 4**, vì 4 không nguyên tố.

### 7.4. Vì sao modulo p^e cần tách thừa số p?

Định lý Legendre:

\[
v_p(n!)=\sum_{j\ge1}\left\lfloor\frac{n}{p^j}\right\rfloor.
\]

Số mũ của p trong tổ hợp là:

\[
v_p(C(n,k))=v_p(n!)-v_p(k!)-v_p((n-k)!).
\]

Nếu số mũ này ≥e, tổ hợp bằng 0 modulo p^e. Nếu nhỏ hơn e, cần **tách các thừa số p** khỏi những giai thừa, chỉ lấy nghịch đảo phần **nguyên tố cùng nhau với p**, rồi nhân lại p với số mũ thích hợp.

Một thuật toán nhanh còn cần xử lý tích các số không chia hết cho p, chu kỳ theo lũy thừa nguyên tố và bước CRT. Đây là phần mở rộng không thể thay thế bằng cách dùng công thức Fermat với môđun p^e.

### 7.5. So sánh lựa chọn

| Điều kiện | Phương pháp | Rủi ro cần tránh |
|---|---|---|
| m≥1 bất kỳ, n vừa phải | Pascal DP | O(n min(k,n−k)) |
| m≥1 bất kỳ, min(k,n−k) nhỏ | BigInteger exact rồi mod | Số trung gian rất lớn nếu k lớn |
| p nguyên tố, n≤N<p, nhiều truy vấn | fact/invFact | Không dùng nếu N≥p |
| p nguyên tố, n có thể ≥p | Lucas | Chi phí từng chữ số có thể cao |
| m hợp số, n,k lớn, nhiều truy vấn | Prime powers + CRT | Phải tính đúng modulo p^e |
| Cần chia cho b modulo m | Euclid mở rộng nếu gcd(b,m)=1 | Không được chia khi b không khả nghịch |

## 8. Tránh overflow khi nhân modulo Java long

Ngay cả khi đầu ra nhỏ hơn môđun, phép nhân **trước khi lấy phần dư** có thể tràn long.

Ví dụ nếu a,b gần 10^18, tích a×b vượt 64-bit. Dùng biểu thức (a*b)%m với long sẽ không bảo toàn tích toán học ban đầu.

Chương trình Java dùng:
- Cộng modulo bằng hàm addMod không tạo tổng dễ tràn.
- Nhân modulo bằng BigInteger.multiply rồi BigInteger.mod.
- Nghịch đảo Fermat bằng BigInteger.modPow.
- Tính tổ hợp nguyên bằng BigInteger.divide chính xác trước modulo.

Đây là lựa chọn ưu tiên **tính đúng**. Với hệ thống cần hàng triệu phép nhân modulo, có thể tối ưu bằng thuật toán nhân modulo chuyên dụng, nhưng phải kiểm thử tràn số và điều kiện đầu vào.

Trong Java, toán tử phần dư với số âm có thể tạo kết quả âm. Nếu đầu vào cho phép âm, cần quy ước phần dư không âm, ví dụ Math.floorMod hoặc BigInteger.mod. Bài này sử dụng những số dư nội bộ luôn không âm.

## 9. Java 17 độc lập, có kiểm tra giả thiết

Bốn API:
- **pascal(n,k,m):** mọi m nguyên dương.
- **exactMod(n,k,m):** mọi m nguyên dương, dùng BigInteger.
- **PrimeTable(N,p).choose(n,k):** bắt buộc p nguyên tố, N<p.
- **lucas(n,k,p):** bắt buộc p nguyên tố, xử lý cả n≥p.

Để không phụ thuộc thư viện ngoài, code kiểm tra nguyên tố long bằng **trial division** tới căn bậc hai. Kiểm tra này chính xác nhưng O(√p), chậm cho p cực lớn; chỉ phù hợp minh họa, ví dụ p=7 hoặc p=1.000.000.007. Trong hệ thống lớn nên dùng kiểm tra nguyên tố nhanh được chứng minh cho miền dữ liệu hoặc coi tính nguyên tố là điều kiện đã được bảo đảm bởi đề bài.

Lưu thành **BinomialModuloDemo.java**:

~~~java
import java.math.BigInteger;

public final class BinomialModuloDemo {
    private BinomialModuloDemo() {
    }

    private static void requireModulus(long m) {
        if (m <= 0) {
            throw new IllegalArgumentException(
                    "Modulus must be positive");
        }
    }

    private static void requireN(long n) {
        if (n < 0) {
            throw new IllegalArgumentException(
                    "n must be nonnegative");
        }
    }

    // 0 <= a,b < m; không tạo phép cộng tràn long.
    private static long addMod(long a, long b, long m) {
        long rest = m - b;
        return a >= rest ? a - rest : a + b;
    }

    private static long mulMod(long a, long b, long m) {
        return BigInteger.valueOf(a)
                .multiply(BigInteger.valueOf(b))
                .mod(BigInteger.valueOf(m))
                .longValueExact();
    }

    // Chính xác với long dương, O(sqrt(p)) trong trường hợp xấu.
    private static boolean isPrime(long p) {
        if (p < 2) {
            return false;
        }
        if (p % 2 == 0) {
            return p == 2;
        }
        for (long d = 3; d <= p / d; d += 2) {
            if (p % d == 0) {
                return false;
            }
        }
        return true;
    }

    private static void requirePrime(long p) {
        if (!isPrime(p)) {
            throw new IllegalArgumentException(
                    "Modulus must be prime");
        }
    }

    // Caller bảo đảm p nguyên tố, 1 <= a < p.
    private static long inversePrime(long a, long p) {
        if (a <= 0 || a >= p) {
            throw new IllegalArgumentException(
                    "Residue not invertible");
        }
        return BigInteger.valueOf(a)
                .modPow(BigInteger.valueOf(p - 2),
                        BigInteger.valueOf(p))
                .longValueExact();
    }

    // Pascal: n>=0, mọi m>=1; k ngoài [0,n] trả 0.
    public static long pascal(int n, int k, long m) {
        requireModulus(m);
        requireN(n);
        if (k < 0 || k > n) {
            return 0;
        }

        int r = Math.min(k, n - k);
        long[] dp = new long[r + 1];
        dp[0] = 1 % m;

        for (long row = 1; row <= n; row++) {
            int upto = (int) Math.min(row, (long) r);
            for (int j = upto; j >= 1; j--) {
                dp[j] = addMod(dp[j], dp[j - 1], m);
            }
        }
        return dp[r];
    }

    // Tính C(n,k) trên số nguyên trước khi mod.
    public static long exactMod(long n, long k, long m) {
        requireModulus(m);
        requireN(n);
        if (k < 0 || k > n) {
            return 0;
        }

        long r = Math.min(k, n - k);
        BigInteger result = BigInteger.ONE;

        if (r > 0) {
            for (long i = 1; ; i++) {
                // n-r+i <= n, không tràn long.
                long factor = n - r + i;
                result = result
                        .multiply(BigInteger.valueOf(factor))
                        .divide(BigInteger.valueOf(i));

                if (i == r) {
                    break;
                }
            }
        }
        return result.mod(BigInteger.valueOf(m))
                .longValueExact();
    }

    // Bảng factorial chỉ cho N<p, p nguyên tố.
    public static final class PrimeTable {
        private final long prime;
        private final int maxN;
        private final long[] fact;
        private final long[] invFact;

        public PrimeTable(int maxN, long prime) {
            requirePrime(prime);
            if (maxN < 0 || maxN == Integer.MAX_VALUE
                    || (long) maxN >= prime) {
                throw new IllegalArgumentException(
                        "Require 0 <= N < p");
            }

            this.prime = prime;
            this.maxN = maxN;
            fact = new long[maxN + 1];
            invFact = new long[maxN + 1];

            fact[0] = 1;
            for (int i = 1; i <= maxN; i++) {
                fact[i] = mulMod(fact[i - 1], i, prime);
            }

            invFact[maxN] = inversePrime(
                    fact[maxN], prime);

            for (int i = maxN; i >= 1; i--) {
                invFact[i - 1] = mulMod(
                        invFact[i], i, prime);
            }
        }

        public long choose(int n, int k) {
            if (n < 0 || n > maxN) {
                throw new IllegalArgumentException(
                        "n outside precomputed range");
            }
            if (k < 0 || k > n) {
                return 0;
            }
            return mulMod(
                    mulMod(fact[n], invFact[k], prime),
                    invFact[n - k], prime);
        }
    }

    // Một chữ số Lucas, 0 <= k <= n < p.
    private static long digitChoose(
            long n, long k, long p) {
        long r = Math.min(k, n - k);
        if (r == 0) {
            return 1;
        }

        long numerator = 1;
        long denominator = 1;

        for (long i = 1; ; i++) {
            numerator = mulMod(
                    numerator, n - r + i, p);
            denominator = mulMod(
                    denominator, i, p);
            if (i == r) {
                break;
            }
        }
        return mulMod(
                numerator, inversePrime(denominator, p), p);
    }

    // Lucas với số n bất kỳ, p nguyên tố.
    public static long lucas(long n, long k, long p) {
        requireN(n);
        requirePrime(p);

        if (k < 0 || k > n) {
            return 0;
        }

        long answer = 1;
        while (n > 0 || k > 0) {
            long ni = n % p;
            long ki = k % p;

            if (ki > ni) {
                return 0;
            }

            answer = mulMod(
                    answer, digitChoose(ni, ki, p), p);
            n /= p;
            k /= p;
        }
        return answer;
    }

    public static void main(String[] args) {
        System.out.println("Pascal C(6,2) mod 12: "
                + pascal(6, 2, 12));
        System.out.println("Exact C(6,2) mod 12: "
                + exactMod(6, 2, 12));
        System.out.println("Pascal C(10,3) mod 8: "
                + pascal(10, 3, 8));
        System.out.println("Pascal C(0,0) mod 1: "
                + pascal(0, 0, 1));
        System.out.println("Exact C(0,0) mod 1: "
                + exactMod(0, 0, 1));

        PrimeTable table7 = new PrimeTable(6, 7);
        System.out.println("Prime C(5,2) mod 7: "
                + table7.choose(5, 2));
        System.out.println("Prime C(6,3) mod 7: "
                + table7.choose(6, 3));
        System.out.println("Prime invalid k: "
                + table7.choose(6, 7));

        PrimeTable tableLarge =
                new PrimeTable(5, 1_000_000_007L);
        System.out.println("Prime C(5,2) mod 1000000007: "
                + tableLarge.choose(5, 2));

        System.out.println("Lucas C(8,7) mod 7: "
                + lucas(8, 7, 7));
        System.out.println("Lucas C(10,3) mod 7: "
                + lucas(10, 3, 7));
        System.out.println("Lucas C(100,30) mod 7: "
                + lucas(100, 30, 7));
        System.out.println("Lucas C(14,7) mod 7: "
                + lucas(14, 7, 7));

        System.out.println("Exact C(200,100) mod 1000000006: "
                + exactMod(200, 100, 1_000_000_006L));
        System.out.println("Exact C(1000000000,2) mod 12: "
                + exactMod(1_000_000_000L, 2, 12));

        try {
            new PrimeTable(7, 7);
            System.out.println("Reject N >= p: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject N >= p: true");
        }

        try {
            new PrimeTable(5, 8);
            System.out.println("Reject composite: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject composite: true");
        }

        try {
            pascal(-1, 0, 7);
            System.out.println("Reject negative n: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject negative n: true");
        }

        try {
            exactMod(5, 2, 0);
            System.out.println("Reject modulus zero: false");
        } catch (IllegalArgumentException expected) {
            System.out.println("Reject modulus zero: true");
        }

        System.out.println("Invalid k mod 9: "
                + pascal(5, 8, 9));
    }
}
~~~

### 9.1. Biên dịch và chạy

Với JDK 17 hoặc mới hơn, lưu file đúng tên và chạy:

~~~bash
javac -encoding UTF-8 BinomialModuloDemo.java
java BinomialModuloDemo
~~~

**Stdout dự kiến:**

~~~text
Pascal C(6,2) mod 12: 3
Exact C(6,2) mod 12: 3
Pascal C(10,3) mod 8: 0
Pascal C(0,0) mod 1: 0
Exact C(0,0) mod 1: 0
Prime C(5,2) mod 7: 3
Prime C(6,3) mod 7: 6
Prime invalid k: 0
Prime C(5,2) mod 1000000007: 10
Lucas C(8,7) mod 7: 1
Lucas C(10,3) mod 7: 1
Lucas C(100,30) mod 7: 0
Lucas C(14,7) mod 7: 2
Exact C(200,100) mod 1000000006: 98670600
Exact C(1000000000,2) mod 12: 0
Reject N >= p: true
Reject composite: true
Reject negative n: true
Reject modulus zero: true
Invalid k mod 9: 0
~~~

### 9.2. Ý nghĩa từng phương pháp

**pascal:** không sử dụng chia nên đúng với mọi môđun m≥1, kể cả hợp số và m=1. Duyệt j từ phải qua trái để không ghi đè dữ liệu hàng Pascal trước.

**exactMod:** mỗi bước dùng BigInteger nhân rồi chia chính xác trên số nguyên, sau đó mới lấy modulo. Không cần nghịch đảo modulo, nhưng số trung gian có thể rất lớn nếu k lớn.

**PrimeTable:** xác minh nguyên tố, từ chối N≥p, xây fact và invFact. Một nghịch đảo của fact[N] được tính bằng Fermat; các invFact trước đó được suy ngược bằng nhân. Truy vấn ngoài vùng bảng bị từ chối.

**lucas:** bóc chữ số n_i,k_i trong cơ số p. Nếu k_i>n_i, trả 0. Với chữ số hợp lệ, mẫu số 1×2×...×r<p không chứa thừa số p, nên có nghịch đảo Fermat.

**mulMod:** nhân BigInteger trước khi mod, nên không overflow long. Nếu cần tối ưu tốc độ cho p cố định, có thể thay bằng kỹ thuật nhân modulo an toàn khác sau khi kiểm thử đầy đủ.

**isPrime:** thử các ước lẻ từ 3 đến căn p bằng điều kiện d≤p/d, tránh d*d tràn. Đây là phép thử đúng nhưng không hiệu quả cho p cực lớn; bài dùng nó để không che giấu giả thiết nguyên tố.

**Không có phép chia modulo hợp số không điều kiện.** Nếu gcd của mẫu với m khác 1, phải đổi phương pháp thay vì gọi inverse trên mẫu ấy.

## 10. Kiểm thử bằng oracle độc lập

Với n nhỏ, dùng BigInteger tính C(n,k) **chính xác**, rồi lấy phần dư để làm oracle. Các bước kiểm thử:
1. Sinh n,k và môđun m≥1.
2. Tính C(n,k) chính xác bằng công thức tích/đối xứng.
3. Đối chiếu với Pascal cho mọi m.
4. Nếu p nguyên tố và N<p, đối chiếu thêm PrimeTable.
5. Nếu p nguyên tố, đối chiếu Lucas kể cả trường hợp n≥p.
6. Kiểm tra ngoại lệ khi N≥p, p hợp số, n âm, m≤0.
7. Kiểm tra tính đối xứng C(n,k)=C(n,n−k) và recurrence Pascal.

### Bảng test định hướng

| Trường hợp | Đáp án |
|---|---|
| C(5,2) mod 7 | 3 |
| C(6,3) mod 7 | 6 |
| C(8,7) mod 7 | 1 dù n≥p |
| C(10,3) mod 7 | 1 |
| C(100,30) mod 7 | 0 do có chữ số Lucas không đủ |
| C(14,7) mod 7 | 2 |
| C(6,2) mod 12 | 3, không dùng inverse 2 |
| C(10,3) mod 8 | 0 |
| C(200,100) mod 1000000006 | 98670600 |
| C(0,0) mod 1 | 0 |
| k<0 hoặc k>n | 0 theo hợp đồng |
| Bảng factorial N≥p | Từ chối |
| Bảng factorial p hợp số | Từ chối |
| n âm hoặc m≤0 | Từ chối |

Các test ngẫu nhiên nên gồm môđun 1, 2, 3, 4, 5, 6, 8, 9, 12, 97 và một nguyên tố lớn, để lộ lỗi không phân biệt prime/composite. Với Lucas, dùng các p nhỏ 2,3,5,7,11,13,17,97 và n trải qua nhiều bội p, để bắt lỗi khi n≥p.

Đánh giá cả độ phức tạp: Pascal O(n min(k,n−k)) có thể không phù hợp với n khổng lồ; Exact BigInteger cần bộ nhớ cho số tổ hợp; bảng factorial O(N); Lucas nhân theo từng chữ số có thể tốn nhiều bước.

## 11. Sai lầm thường gặp

1. **Dùng phép chia thường sau khi lấy modulo** như thể phần dư là phân số.
2. **Dùng Fermat a^(m−2) với m hợp số**.
3. **Không kiểm tra gcd(a,m)=1** trước khi cần nghịch đảo.
4. **Dùng invFact[n] khi n≥p**, dù fact[n]≡0.
5. **Cho rằng p nguyên tố là đủ cho mọi bảng factorial**, quên N<p.
6. **Áp dụng Lucas nguyên bản cho p^e hoặc hợp số m**.
7. **Tính factorial đến p−1 khi p cực lớn** mà không xét RAM.
8. **Khẳng định Lucas luôn chạy nhanh**, dù chữ số r_i có thể gần p/2.
9. **Cập nhật Pascal từ trái qua phải**, lấy nhầm giá trị hàng mới.
10. **Quên C(n,k)=C(n,n−k)**, lặp dư.
11. **Trả 1 cho C(0,0) mod1**, quên phần dư modulo 1 phải bằng 0.
12. **Quên k ngoài [0,n] trả 0** theo quy ước API.
13. **Nhân hoặc cộng long rồi mới lấy modulo sau khi đã overflow**.
14. **Dùng BigInteger.divide sau khi đã lấy modulo**, nhầm phép chia nguyên với phép nghịch đảo.
15. **Bỏ qua chữ số k_i>n_i trong Lucas**, trả khác 0 khi đáng ra 0.
16. **Làm CRT theo các môđun không nguyên tố cùng nhau** mà không kiểm tra điều kiện.
17. **Không xử lý prime powers trong m hợp số**, chỉ áp dụng Lucas cho từng thừa số p rồi cho rằng đủ.
18. **Xem mọi số dư khác 0 modulo m hợp số đều khả nghịch**.
19. **Không kiểm thử môđun hợp số hoặc n≥p**, khiến công thức sai giả thiết vẫn qua test ASCII tương đương dễ.
20. **Không tính chi phí xác minh nguyên tố hoặc phân tích m** trong lựa chọn hiệu năng.
21. **Quên chuẩn hóa số dư của số âm** nếu API cho đầu vào âm.
22. **Chỉ kiểm tra kết quả mẫu**, bỏ chứng minh điều kiện tồn tại nghịch đảo.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Khi nào b có nghịch đảo modulo m?

**Đáp án:** Khi và chỉ khi gcd(b,m)=1.

**Câu 2.** C(6,2) mod 12 có bằng 3 không, dù inverse(2,12) không tồn tại?

**Đáp án:** Có. C(6,2)=15, 15 mod12=3. Tính chính xác rồi lấy phần dư khác với phép chia bên trong modulo.

**Câu 3.** Điều kiện dùng a^(p−2) làm nghịch đảo?

**Đáp án:** p nguyên tố và a không chia hết cho p.

**Câu 4.** Bảng factorial/invFact đòi điều kiện nào?

**Đáp án:** p nguyên tố và giới hạn N<p; nếu N≥p thì N!≡0 không khả nghịch.

**Câu 5.** Vì sao C(8,7) mod7 bằng 1 nhưng bảng fact đến 8 không dùng được?

**Đáp án:** 8! và 7! đều chia hết cho 7; Lucas tính C(8,7)≡C(1,0)C(1,1)=1.

**Câu 6.** Lucas hoạt động trên môđun nào?

**Đáp án:** Nguyên tố p; nó phân tích n,k thành chữ số cơ số p.

**Câu 7.** Nếu k_i>n_i trong một chữ số Lucas?

**Đáp án:** Kết quả bằng 0 modulo p.

**Câu 8.** Pascal DP có yêu cầu m nguyên tố không?

**Đáp án:** Không. Nó chỉ dùng phép cộng, đúng với mọi m nguyên dương.

**Câu 9.** Vì sao Pascal cần duyệt j giảm dần?

**Đáp án:** Để cả hai giá trị dp[j] và dp[j−1] vẫn thuộc hàng Pascal trước.

**Câu 10.** BigInteger exactMod có cần nghịch đảo modulo không?

**Đáp án:** Không. Nó chia chính xác trong số nguyên rồi lấy phần dư sau cùng.

**Câu 11.** CRT giúp gì khi môđun hợp số?

**Đáp án:** Ghép kết quả modulo các lũy thừa nguyên tố đôi một nguyên tố cùng nhau thành kết quả modulo m.

**Câu 12.** Tại sao phải tách số mũ của p trong bài modulo p^e?

**Đáp án:** Vì các thừa số chia hết cho p không khả nghịch modulo p^e, nên cần xử lý chúng riêng.

**Câu 13.** Vì sao (a*b)%m dùng long vẫn có thể sai?

**Đáp án:** Tích a*b có thể tràn trước khi lấy phần dư.

**Câu 14.** Với rất nhiều truy vấn cùng p nguyên tố và n<p, nên làm gì?

**Đáp án:** Tiền xử lý fact/invFact đến N<p, mỗi truy vấn sau đó cần O(1) phép nhân modulo.

**Câu 15.** Nếu p rất lớn, Lucas có nhất thiết nhanh không?

**Đáp án:** Không. Tính mỗi tổ hợp chữ số bằng tích trực tiếp có thể cần gần p/2 bước.

**Câu 16.** C(0,0) mod1 là bao nhiêu?

**Đáp án:** 0, mặc dù C(0,0)=1 trước khi lấy modulo.

**Ghi nhớ:** Với bài tổ hợp modulo, **giả thiết về môđun là một phần của thuật toán**. Pascal và BigInteger exact dùng được với mọi m≥1; factorial/invFact yêu cầu **p nguyên tố và N<p**; Lucas xử lý n≥p khi p nguyên tố; còn môđun hợp số tổng quát có thể cần **phân tích prime powers + CRT**. Không chia trong modulo nếu mẫu số không có nghịch đảo.
