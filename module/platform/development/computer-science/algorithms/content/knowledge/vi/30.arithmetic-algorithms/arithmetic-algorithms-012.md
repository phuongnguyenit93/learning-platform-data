# Phân tích thừa số bằng Pollard rho

> **Chủ đề:** Computer Science Algorithms → **Thuật toán số học**.  
> **Trọng tâm:** Thuật toán **Pollard rho (ρ)** tìm **ước số không tầm thường** bằng dãy giả ngẫu nhiên và ước chung lớn nhất. Phân biệt tìm một ước với phân tích hoàn chỉnh thành thừa số nguyên tố; giải thích va chạm modulo một ước chưa biết, Floyd và Brent, tình huống `gcd=1`, `gcd=n`, restart, độ phức tạp kỳ vọng, kiểm tra nguyên tố, Java 17 dùng BigInteger và kiểm thử đối chiếu phép chia thử.

## 1. Bài toán cần giải

Với số nguyên dương N>1, phân tích thừa số nguyên tố là tìm các số nguyên tố phân biệt `p1,...,pk` và số mũ nguyên dương `e1,...,ek` sao cho:

`N = p1^e1 · p2^e2 · ... · pk^ek`.

Ví dụ:

`8051 = 83 · 97`.

`10403 = 101 · 103`.

`100140049 = 10007²`.

`600851475143 = 71 · 839 · 1471 · 6857`.

Một lần **Pollard rho** thường chỉ trả về **một ước không tầm thường** d với:

`1<d<N` và `N mod d=0`.

Điều này cho một phép tách `N=d·(N/d)`. **d chưa chắc nguyên tố**, và `N/d` cũng chưa chắc nguyên tố. Phải tiếp tục phân tích cả hai mảnh và kiểm tính nguyên tố thì mới có danh sách cuối.

### 1.1. Đầu vào đặc biệt

| N | Cách hiểu/đầu ra |
|---|---|
| N=0 | Không có phân tích hữu hạn thành thừa số nguyên tố theo định nghĩa chuẩn; không chạy rho |
| N=1 | Không có thừa số nguyên tố, tích rỗng bằng 1 |
| N=-1 | Chỉ có thừa số đơn vị dấu -1 |
| N<-1 | Tách -1 rồi phân tích `|N|`, chẳng hạn `-84=-1·2²·3·7` |
| N nguyên tố | Bản thân N là một thừa số; **không có** d với 1<d<N |
| N là hợp số | Dùng chia thử các ước nhỏ, rho hoặc thuật toán khác |

Pollard rho không dùng để chứng minh N nguyên tố bằng cách “thử mãi không tìm ra ước”. Khi hết ngân sách thử, kết quả phải là **không kết luận** (*inconclusive*), không phải “prime”.

### 1.2. So với chia thử

**Chia thử** (*trial division*) kiểm tra chia hết bởi 2,3,5,... tới √N, trong tình huống xấu cần cỡ O(√N) phép thử.

Pollard rho hy vọng tìm được một thừa số nguyên tố p của N sau cỡ **O(√p)** bước theo trực giác xác suất, ngay cả khi chưa biết p. Với N=pq và p≈q≈√N, điều đó tương ứng cỡ **O(N^(1/4))** bước. Đây là lý do nó hữu ích trên các số hợp số có thừa số tương đối nhỏ, nhưng **không** phải lời giải đa thức theo số bit N cho mọi trường hợp.

## 2. Dãy modulo N và va chạm modulo p

Giả sử N có thừa số nguyên tố p **chưa biết**. Chọn hàm chuyển:

`f(x)=(x²+c) mod N`

với một tham số c, và tạo dãy:

`x0 = 2`,  
`x1 = f(x0)`,  
`x2 = f(x1)`,  
`x3 = f(x2)`, ...

Vì p chia N, nếu hai phần tử `xi` và `xj` **bằng nhau modulo p** thì:

`xi≡xj (mod p)` ⇒ `p | (xi−xj)`.

Khi đó:

`d=gcd(|xi−xj|,N)`

có thể chứa p và tiết lộ một ước của N. Ta **không cần biết p** để tính d: tất cả xi được tính mod N và gcd cũng chỉ dùng N.

### 2.1. Ba khả năng của gcd

| `d = gcd(|xi−xj|,N)` | Điều đã biết | Hành động |
|---|---|---|
| d=1 | Chưa có ước chung hữu ích | Tiếp tục đi dãy |
| `1<d<N` | Tìm được ước số thật sự | Trả d và N/d, rồi phân tích tiếp |
| d=N | Hiệu chia hết N; va chạm không giúp tách N | Thử seed/c khác; Brent có thể cứu batch |

Đặc biệt, **d=N không phải lời giải**, dù N rõ ràng chia hết cho chính nó. Một hàm phân tích nhận d=N rồi đệ quy trên d sẽ không giảm input và có thể lặp vô hạn.

`d=1` cũng **không** có nghĩa N nguyên tố. Nó chỉ cho biết cặp đang xét chưa phát hiện va chạm modulo một thừa số không tầm thường.

### 2.2. Vì sao gọi là “rho”?

Một dãy sinh bởi một hàm từ tập hữu hạn vào chính nó sẽ đi qua một **đuôi** rồi vào một **chu trình lặp lại**. Đồ thị đường đi có hình gần giống chữ Hy Lạp **ρ**: một đoạn đuôi gắn với một vòng.

Việc tìm điểm va chạm của dãy modulo những ước số ẩn chính là nguồn gốc tên **Pollard rho**. Nó không liên quan trực tiếp tới ký hiệu φ của hàm Euler.

### 2.3. Nghịch lý ngày sinh

Nếu các trạng thái mod p gần giống lấy mẫu ngẫu nhiên trong p residue, va chạm đầu tiên thường xuất hiện sau cỡ √p mẫu theo **birthday paradox**.

Điều mong muốn là va chạm đã xảy ra modulo p **nhưng chưa xảy ra đồng thời theo mọi thừa số khác**, để gcd nằm giữa 1 và N.

Đây là một mô hình **kỳ vọng** về hành vi của hàm f; không chứng minh mỗi lần chạy đều thành công sau đúng √p bước. Một đa thức, seed hoặc input không thuận lợi có thể khiến attempt thất bại.

### 2.4. Tại sao không phải thử các ước tới √N?

Pollard rho **không duyệt các ứng viên ước** 2,3,... cho tới √N. Nó tạo các residue mod N rồi thử gcd của các **hiệu dãy** với N. Gcd là cách trích xuất một ước chưa biết từ một va chạm modulo p.

## 3. Floyd: hai con trỏ rùa và thỏ

Phát hiện chu trình **Floyd** duy trì hai giá trị:

- `x` (*rùa*): đi **một** bước `x=f(x)`.
- `y` (*thỏ*): đi **hai** bước `y=f(f(y))`.

Khởi tạo x=y=x0. Sau mỗi vòng tính:

`d=gcd(|x−y|,N)`.

Nếu `1<d<N`, tìm được một ước. Nếu d=N hoặc hết giới hạn vòng, coi attempt thất bại và đổi tham số/seed.

### 3.1. Pseudocode

```text
rhoFloydAttempt(N, x0, c, iterationLimit):
    x = x0
    y = x0

    for i = 1 .. iterationLimit:
        x = (x*x+c) mod N
        y = (y*y+c) mod N
        y = (y*y+c) mod N

        d = gcd(abs(x-y),N)

        if 1 < d < N: return FOUND(d)
        if d == N: return RETRY

    return INCONCLUSIVE
```

Không được bỏ modulo N ở từng phép tính: nếu để x²+c tăng mãi, đó không còn là quỹ đạo trên tập residue hữu hạn.

### 3.2. Tính tay với N=8051

Chọn `x0=2`, `c=1`, `f(x)=(x²+1) mod8051`.

| Vòng | x (1 bước) | y (2 bước) | `|x-y|` | gcd với 8051 |
|---:|---:|---:|---:|---:|
| 0 | 2 | 2 | 0 | Chưa tính |
| 1 | 5 | 26 | 21 | 1 |
| 2 | 26 | 7474 | 7448 | 1 |
| 3 | 677 | 871 | 194 | **97** |

Ở vòng3:

`|677−871|=194=2·97`.

`gcd(194,8051)=97`.

Vì `8051/97=83`, ta tìm được:

`8051=97·83`.

Hai số 83 và 97 đều nguyên tố, nên trường hợp này đã phân tích hoàn toàn.

### 3.3. Không đòi d là ước nhỏ nhất

Trong ví dụ, Floyd với c1 tìm **97** trước, dù 83 nhỏ hơn. Kết quả vẫn đúng: d là một ước không tầm thường.

Khi so sánh hai thuật toán hoặc hai lần chạy với seed khác, không ép chúng trả **cùng một d**. Chỉ kiểm d thật sự chia N, rồi so **bản đồ thừa số nguyên tố cuối cùng**.

### 3.4. Vì sao d=N có thể xảy ra?

Khi `x==y` mod N, hiệu bằng0 và `gcd(0,N)=N`. Dãy trong không gian hữu hạn cuối cùng có thể lặp lại, nên trường hợp này phải được dự liệu. Nếu nó xảy ra trước khi tách được N, **restart** với c hoặc x0 khác.

## 4. Từ một ước tới phân tích nguyên tố đầy đủ

Thuật toán phân tích tổng quát:

```text
factorPositive(N):
    if N == 1: return

    if isPrime(N):
        recordPrime(N)
        return

    d = rhoFindNontrivialFactor(N)

    if d <= 1 or d >= N or N % d != 0:
        report INCONCLUSIVE

    factorPositive(d)
    factorPositive(N/d)
```

Điều kiện d hợp lệ **phải được kiểm trước khi đưa vào lời gọi tiếp**. Một gcd trả d=N rồi lặp `factorPositive(N)` không bao giờ tạo tiến triển.

### 4.1. Ước d cũng có thể là hợp số

Với:

`41041 = 7·11·13·41`,

một lần Brent theo c1, batch32 có thể trả d=1001:

`41041 = 41·1001`.

Nhưng:

`1001 = 7·11·13`

**không nguyên tố**. Vì vậy phải phân tích tiếp cả hai mảnh cho tới khi tất cả các mảnh cuối đều nguyên tố.

### 4.2. Dùng stack thay đệ quy

Có thể dùng `Deque<BigInteger>`:

```text
pending = [N]
while pending không rỗng:
    m = pop(pending)
    if m == 1: continue

    if isPrime(m):
        count[m]++
    else:
        d = findFactor(m)
        verify 1 < d < m and m mod d == 0
        push(d)
        push(m/d)
```

Với số nguyên tố lặp lại, tăng **số mũ** thay vì chỉ ghi nhận đã thấy số nguyên tố ấy. Ví dụ `360=2³·3²·5`, phải in số mũ 3 của 2 và 2 của 3.

### 4.3. Kiểm tích mảnh

Sau khi kết thúc:

`product = ∏ p^exponent`.

Phải kiểm `product == |N|`. Với N âm, nhân thêm -1.

Tuy nhiên **kiểm tích chưa đủ** chứng minh từng p là nguyên tố. Ví dụ 21·25=525 là phép tách đúng nhưng 21 và25 đều hợp số.

### 4.4. Prime powers

Số `100140049 = 10007²` có hai thừa số nguyên tố **trùng nhau**. Sau khi tách được d=10007, nhánh còn lại cũng bằng10007. Khi cộng map prime→exponent, kết quả phải là `10007^2`, không phải chỉ một bản ghi `10007`.

## 5. Kiểm tra nguyên tố là bước khác với Pollard rho

Pollard rho là một công cụ **tìm ước**, không phải một kiểm tra nguyên tố hoàn chỉnh. Nếu N nguyên tố thì không tồn tại `1<d<N` chia hết N; chạy Pollard quá lâu **không** trở thành chứng minh nguyên tố.

Trong Java 17 ta có:

`BigInteger.isProbablePrime(certainty)`.

Các chương trình dưới dùng `isProbablePrime(80)`.

- Khi trả `false`, n là hợp số.
- Khi trả `true`, n **có xác suất rất cao là nguyên tố**, chứ không là chứng nhận tuyệt đối cho mọi BigInteger.

Vì vậy thành phẩm phân tích bằng cách này là phân tích thành các **probable primes** với mức kiểm tra đã chọn. Nếu đề bài đòi chứng minh nguyên tố xác định, cần dùng một kiểm tra/chứng chỉ có bảo đảm phù hợp với miền input.

### 5.1. Vì sao không dùng kiểm Fermat một cơ số?

Có những **số giả nguyên tố** và số Carmichael, chẳng hạn 561, 41041, có thể vượt qua những kiểm tra kiểu Fermat đơn giản trong điều kiện nhất định. Không được kết luận “prime” chỉ vì `a^(n−1)≡1 mod n` với một cơ số tùy ý.

Miller–Rabin thường được dùng để sàng hợp số hiệu quả; nếu dùng bản xác suất, phải hiểu rõ mức chắc chắn. Không lấy vài cơ số bất kỳ rồi tuyên bố đã chứng minh mọi số nguyên rất lớn.

### 5.2. Nguyên tắc báo kết quả

Hệ thống nên phân biệt:

- **COMPOSITE_WITH_FACTOR(d):** có ước d đã xác minh.
- **PROBABLE_PRIME:** primality test trả true theo mức certainty.
- **INCONCLUSIVE:** hết budget rho chưa tìm được ước, không có bằng chứng prime.

Không biến **INCONCLUSIVE** thành **PROBABLE_PRIME** chỉ vì một attempt thất bại.

## 6. Java 17 — phân tích thừa số đầy đủ bằng Floyd

Chương trình này là một file chạy độc lập. Nó dùng:

- BigInteger để tránh overflow `x*x+c`.
- Floyd với `x=f(x)` và `y=f(f(y))`.
- Restart với `c=1..96` sau khi d=N hoặc hết 250000 vòng.
- Stack phân tích mọi mảnh, TreeMap giữ prime factors và số mũ.
- Kiểm sản phẩm và prime factors qua `isProbablePrime(80)`.
- Xử lý riêng số0, ±1, số âm.

Dãy c cố định chỉ nhằm **tái lập kết quả demo**. Khi cần xử lý dữ liệu đối kháng, nên chọn nhiều tham số ngẫu nhiên và đặt ngân sách tài nguyên rõ ràng.

Lưu thành **PollardRhoFloydFactorizationDemo.java**:

```java
import java.math.BigInteger;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.SortedMap;
import java.util.StringJoiner;
import java.util.TreeMap;

public class PollardRhoFloydFactorizationDemo {
    static final BigInteger ZERO = BigInteger.ZERO;
    static final BigInteger ONE = BigInteger.ONE;
    static final BigInteger TWO = BigInteger.TWO;
    static final BigInteger THREE = BigInteger.valueOf(3);

    static BigInteger step(BigInteger x, BigInteger c, BigInteger n) {
        return x.multiply(x).add(c).mod(n);
    }

    static BigInteger findNontrivialFactor(BigInteger n) {
        if (n.compareTo(TWO) <= 0) {
            throw new IllegalArgumentException("Composite n > 2 required");
        }
        if (n.mod(TWO).equals(ZERO)) return TWO;
        if (n.mod(THREE).equals(ZERO)) return THREE;

        for (int attempt = 1; attempt <= 96; attempt++) {
            BigInteger c = BigInteger.valueOf(attempt);
            BigInteger x = TWO, y = TWO, d = ONE;

            for (int i = 0; i < 250_000 && d.equals(ONE); i++) {
                x = step(x, c, n);
                y = step(step(y, c, n), c, n);
                d = x.subtract(y).abs().gcd(n);
            }

            if (d.compareTo(ONE) > 0 && d.compareTo(n) < 0) {
                return d;
            }
            // Nếu gcd=n hoặc hết budget, thử c mới.
        }
        throw new IllegalStateException(
                "Pollard rho inconclusive after all attempts: " + n);
    }

    static SortedMap<BigInteger, Integer> factorAbsolute(
            BigInteger value) {
        if (value.signum() < 0) {
            throw new IllegalArgumentException("Absolute value required");
        }
        SortedMap<BigInteger, Integer> answer = new TreeMap<>();
        Deque<BigInteger> pending = new ArrayDeque<>();
        if (value.compareTo(ONE) > 0) pending.addLast(value);

        while (!pending.isEmpty()) {
            BigInteger n = pending.removeLast();
            if (n.equals(ONE)) continue;

            if (n.isProbablePrime(80)) {
                answer.merge(n, 1, Integer::sum);
                continue;
            }

            BigInteger d = findNontrivialFactor(n);
            if (d.compareTo(ONE) <= 0
                    || d.compareTo(n) >= 0
                    || !n.mod(d).equals(ZERO)) {
                throw new IllegalStateException("Invalid rho divisor");
            }
            pending.addLast(d);
            pending.addLast(n.divide(d));
        }
        return answer;
    }

    static String factorsToString(
            BigInteger input,
            SortedMap<BigInteger, Integer> factors) {
        StringJoiner output = new StringJoiner(" * ");
        if (input.signum() < 0) output.add("-1");

        BigInteger product =
                input.signum() < 0 ? ONE.negate() : ONE;
        for (Map.Entry<BigInteger, Integer> entry
                : factors.entrySet()) {
            BigInteger p = entry.getKey();
            int exponent = entry.getValue();

            if (!p.isProbablePrime(80) || exponent <= 0) {
                throw new IllegalStateException(
                        "Factor is not probably prime");
            }
            product = product.multiply(p.pow(exponent));
            output.add(exponent == 1 ? p.toString()
                    : p + "^" + exponent);
        }
        if (!product.equals(input)) {
            throw new IllegalStateException("Product check failed");
        }

        if (input.equals(ONE)) return "1";
        if (input.equals(ONE.negate())) return "-1";
        return output.toString();
    }

    static void show(String literal) {
        BigInteger n = new BigInteger(literal);
        if (n.equals(ZERO)) {
            System.out.println("factor(0) = undefined");
            return;
        }
        SortedMap<BigInteger, Integer> factors =
                factorAbsolute(n.abs());
        System.out.println("factor(" + n + ") = "
                + factorsToString(n, factors));
    }

    public static void main(String[] args) {
        show("8051");
        show("10403");
        show("100140049");
        show("600851475143");
        show("360");
        show("-84");
        show("41041");
        show("1");
        show("-1");
        show("0");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 PollardRhoFloydFactorizationDemo.java
java PollardRhoFloydFactorizationDemo
```

**Stdout:**

```text
factor(8051) = 83 * 97
factor(10403) = 101 * 103
factor(100140049) = 10007^2
factor(600851475143) = 71 * 839 * 1471 * 6857
factor(360) = 2^3 * 3^2 * 5
factor(-84) = -1 * 2^2 * 3 * 7
factor(41041) = 7 * 11 * 13 * 41
factor(1) = 1
factor(-1) = -1
factor(0) = undefined
```

### 6.1. Vì sao BigInteger cần thiết?

Với long, biểu thức `x*x+c` có thể **tràn số trước khi lấy `% N`**, ngay cả khi x<N và N còn trong miền long. Sau tràn, residue không đúng và toàn dãy Pollard mất ý nghĩa.

`BigInteger.multiply().add().mod(n)` dùng số học nguyên chính xác. Đổi lại, thời gian và bộ nhớ của phép nhân/chia BigInteger phụ thuộc số bit.

### 6.2. Vì sao không đưa 0 vào stack?

0 có vô số ước và không có phân tích hữu hạn chuẩn. Đưa 0 vào chương trình rho sẽ làm phép modulo hoặc điều kiện chia không hợp lệ. Hàm `show("0")` trả `"undefined"` trước khi gọi factorAbsolute.

### 6.3. Vì sao chương trình in theo thứ tự tăng?

`TreeMap<BigInteger,Integer>` sắp các prime factors. Pollard có thể tìm được 97 rồi83, nhưng kết quả cuối sắp thành `83 * 97`. Khi so kết quả, hãy so **multiset các thừa số** chứ không so thứ tự tìm.

### 6.4. Vì sao n=1 không được cho là prime?

1 **không phải nguyên tố**. Khi `factorAbsolute(1)` trả map rỗng, `factorsToString` in `"1"` theo quy ước tích rỗng. Tương tự -1 chỉ biểu thị dấu.

### 6.5. Chặn sự cố khi rho không tìm thấy ước

Sau 96 c thử, hàm ném `IllegalStateException` với thông điệp **inconclusive**. Nó không lặng lẽ đẩy lại chính n vào stack hoặc gắn nhãn prime. Trong ứng dụng thực tế, có thể trả một kiểu kết quả `FactorFound/ProbablePrime/Inconclusive` thay ngoại lệ nếu muốn API rõ ràng.

## 7. Brent: tính gcd theo lô và cứu va chạm

Trong Floyd, ta thường tính gcd **mỗi vòng**. Với số lớn, gcd nhiều lần có thể đắt.

**Brent's cycle finding** tăng khoảng tìm theo các khối dài:

`r=1,2,4,8,...`

Giữ một mốc x, cho y tiến theo dãy rồi tích lũy hiệu trong mỗi batch m phần tử:

`q = ∏ |x−y_j| (mod N)`.

Thay vì gọi gcd riêng cho mỗi hiệu, gọi:

`g = gcd(q,N)`.

Nếu một hiệu chia hết một ước p của N, tích q cũng chia hết p, vì vậy phép gcd theo batch vẫn có cơ hội phát hiện ước.

### 7.1. Vì sao batch gcd có thể bằng N?

Nếu các hiệu trong một batch chia hết những ước nguyên tố khác nhau của N, tích của chúng có thể chia hết **tất cả** các ước chính cần thiết. Khi đó:

`gcd(q,N)=N`.

Điều này không có nghĩa mọi hiệu đơn đều vô ích. Brent có thể quay về `ys` (state tại đầu batch cuối) rồi **gcd từng hiệu**:

```text
while g == 1:
    ys = f(ys)
    g = gcd(abs(x-ys),N)
```

Nếu tìm `1<g<N`, thành công. Nếu vẫn g=N hoặc hết budget, **restart**.

### 7.2. Vì sao cần modulo N trong tích q?

Nếu không lấy modulo, tích của hàng chục/hàng trăm hiệu sẽ rất lớn. Vì gcd của q với N chỉ phụ thuộc q modulo N:

`gcd(product,N)=gcd(product mod N,N)`,

có thể cập nhật:

`q=(q*abs(x-y)) mod N`.

Kết quả gcd không đổi, trong khi kích thước q vẫn được giữ ở dưới N.

### 7.3. Floyd so với Brent

| Vấn đề | Floyd | Brent |
|---|---|---|
| Cách phát hiện | Rùa1 bước, thỏ2 bước | Khối r tăng gấp đôi |
| Gcd | Mỗi vòng thường một lần | Theo batch |
| Khi gcd=N | Restart | Thử khôi phục từng hiệu rồi restart |
| Bộ nhớ lõi | O(1) trạng thái BigInteger | O(1) trạng thái BigInteger |
| Độ khó code | Thấp | Trung bình, nhiều bất biến |
| Kết quả | Một ước không tầm thường | Một ước không tầm thường |
| Brent có luôn nhanh hơn? | Không áp dụng | **Không**; cần benchmark |

Batch size 16,32,64 là lựa chọn thực nghiệm, không có một giá trị tối ưu cho mọi N.

## 8. Java 17 — tìm một ước bằng Brent

Chương trình dưới **không phân tích hoàn toàn**, mà cố ý in **một phép tách**. Vì thế kết quả của `41041` cho thấy một mảnh **1001** còn hợp số.

Lưu thành **PollardRhoBrentDemo.java**:

```java
import java.math.BigInteger;

public class PollardRhoBrentDemo {
    static final BigInteger ZERO = BigInteger.ZERO;
    static final BigInteger ONE = BigInteger.ONE;
    static final BigInteger TWO = BigInteger.TWO;
    static final BigInteger THREE = BigInteger.valueOf(3);

    static BigInteger f(BigInteger x, BigInteger c, BigInteger n) {
        return x.multiply(x).add(c).mod(n);
    }

    static BigInteger findFactor(BigInteger n) {
        if (n.compareTo(TWO) <= 0) {
            throw new IllegalArgumentException("Composite n > 2 required");
        }
        if (n.mod(TWO).equals(ZERO)) return TWO;
        if (n.mod(THREE).equals(ZERO)) return THREE;

        final long maxSteps = 250_000L;
        final long batchSize = 32L;

        for (int attempt = 1; attempt <= 96; attempt++) {
            BigInteger c = BigInteger.valueOf(attempt);
            BigInteger x = ZERO;
            BigInteger y = TWO, ys = ZERO;
            BigInteger g = ONE;
            long r = 1L, steps = 0L;

            while (g.equals(ONE) && steps < maxSteps) {
                x = y;
                for (long i = 0; i < r && steps < maxSteps; i++) {
                    y = f(y, c, n);
                    steps++;
                }

                long k = 0;
                while (k < r && g.equals(ONE) && steps < maxSteps) {
                    ys = y;
                    BigInteger q = ONE;
                    long count = Math.min(batchSize, r - k);

                    for (long j = 0; j < count && steps < maxSteps; j++) {
                        y = f(y, c, n);
                        q = q.multiply(x.subtract(y).abs()).mod(n);
                        steps++;
                    }
                    g = q.gcd(n);
                    k += count;
                }
                r *= 2L;
            }

            if (g.equals(n)) {
                g = ONE;
                while (g.equals(ONE) && steps < maxSteps) {
                    ys = f(ys, c, n);
                    g = x.subtract(ys).abs().gcd(n);
                    steps++;
                }
            }

            if (g.compareTo(ONE) > 0 && g.compareTo(n) < 0) {
                return g;
            }
        }
        throw new IllegalStateException(
                "Brent inconclusive after all attempts: " + n);
    }

    static void show(String literal) {
        BigInteger n = new BigInteger(literal);
        if (n.isProbablePrime(80)) {
            System.out.println("Brent(" + n
                    + ") = probable prime (skip)");
            return;
        }

        BigInteger d = findFactor(n);
        if (d.compareTo(ONE) <= 0 || d.compareTo(n) >= 0
                || !n.mod(d).equals(ZERO)) {
            throw new IllegalStateException("Bad divisor");
        }

        BigInteger other = n.divide(d);
        BigInteger left = d.min(other);
        BigInteger right = d.max(other);
        System.out.println("Brent(" + n + ") = "
                + left + " * " + right);
    }

    public static void main(String[] args) {
        show("8051");
        show("10403");
        show("100140049");
        show("221");
        show("360");
        show("41041");
        show("101");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 PollardRhoBrentDemo.java
java PollardRhoBrentDemo
```

**Stdout:**

```text
Brent(8051) = 83 * 97
Brent(10403) = 101 * 103
Brent(100140049) = 10007 * 10007
Brent(221) = 13 * 17
Brent(360) = 2 * 180
Brent(41041) = 41 * 1001
Brent(101) = probable prime (skip)
```

### 8.1. Đừng gọi 1001 là “thừa số nguyên tố”

`1001=7·11·13`. Brent trả 1001 là **đúng** khi bài chỉ cần một ước không tầm thường; để hoàn tất phân tích, còn phải xử lý mảnh này.

### 8.2. Mục đích của x, y, ys, r

- x: mốc ở đầu đoạn đang so sánh.
- y: vị trí quét trong dãy.
- ys: vị trí trước batch gây `g=N`, dùng khi phục hồi.
- r: độ dài khối tăng gấp đôi.
- q: tích các hiệu trong batch modulo N.
- g: gcd của q với N.
- steps: ngân sách đã dùng, tránh một attempt chạy vô hạn.

Nếu dùng lại y/ys/q từ lần thử c trước mà không khởi tạo lại đúng, sẽ làm hỏng ý nghĩa của attempt mới.

### 8.3. Prime input

Nếu n=101, không tồn tại ước không tầm thường. Hàm show kiểm probable-prime trước và in `"probable prime (skip)"`, thay vì cố chạy rho cho tới hết mọi lượt.

### 8.4. Thuật toán Brent là tối ưu tuyệt đối?

Không. Brent thường giảm số phép gcd nhờ batch, nhưng tổng modular multiplication, số restart và trường hợp phục hồi g=N ảnh hưởng hiệu năng. Chọn biến thể theo benchmark trên kích thước input thực tế.

## 9. Restart, giới hạn tài nguyên và lựa chọn tham số

Pollard rho là **thuật toán tìm kiếm ngẫu nhiên/giả ngẫu nhiên**, nên cần chính sách thất bại minh bạch.

### 9.1. Khi nào restart?

- `d=N`: cặp con trỏ đã va chạm modulo N nhưng không tách được.
- `d=1` mãi tới giới hạn iteration/budget.
- Brent `g=N` và bước cứu không tìm được ước.
- Thời gian hoặc số phép toán vượt ngưỡng cho phép.

Mỗi lần thử cần **reset** x,y,g,steps và tham số tích lũy thích hợp.

### 9.2. Chọn polynomial

`f(x)=(x²+c) mod N` là lựa chọn phổ biến. Thử c=1,2,... là cách dễ tái lập khi học. Trong môi trường thực, dùng RNG chọn x0 và c mới để tránh các input được cố tình thiết kế nhằm gây thất bại cho một lịch thử cố định.

RNG không làm việc tìm ước trở thành một phép thử mật mã an toàn tự thân. Chức năng của nó là tạo các dãy tìm kiếm đa dạng. Với input đối kháng, cân nhắc seed ngẫu nhiên mạnh, giới hạn tài nguyên và luân chuyển thuật toán.

### 9.3. Không lập luận sai từ một attempt

Nếu 100 lần thử đều không tìm được d, kết luận hợp lệ là **chưa tìm được ước trong ngân sách**, không phải N nguyên tố. Dùng primality test riêng và/hoặc thuật toán khác.

### 9.4. Thời gian, memory, input size

Một dịch vụ cho phép phân tích số nguyên tùy ý do người dùng nhập có nguy cơ bị lạm dụng CPU. Nên đặt giới hạn bit-length, tổng số lần nhân modulo, số restart, thời gian và bộ nhớ; khi vượt giới hạn, trả trạng thái không kết luận thay vì chờ vô hạn hoặc bịa kết quả.

## 10. Độ phức tạp: số vòng và chi phí bit

### 10.1. Heuristic O(√p)

Cho p là một thừa số nguyên tố nhỏ của N. Nếu dãy modulo p hành xử gần giống ánh xạ ngẫu nhiên, thời gian tới va chạm hữu ích **kỳ vọng** khoảng O(√p) bước.

Đây không phải bảo đảm worst-case. Một số hàm và seed có thể va chạm không hữu ích hoặc thất bại trước budget.

### 10.2. Trường hợp N=pq với p≈q

Nếu p≈q≈√N, thì:

`√p≈N^(1/4)`.

Đó là cải thiện đáng kể so với chia thử √N theo **số bước**, nhưng vẫn là **hàm mũ theo số bit**: với N≈2^k, N^(1/4)≈2^(k/4).

Không được quảng bá Pollard rho là công cụ hiệu quả để phân tích mọi modulus mật mã hiện đại có kích thước đủ lớn.

### 10.3. Chi phí mỗi bước không hằng theo bit

BigInteger.multiply và BigInteger.mod làm việc trên số nhiều bit; gcd cũng có chi phí số học. Vì vậy O(√p) **số lần bước** không tự đồng nghĩa với O(√p) **bit operations**.

### 10.4. Bộ nhớ

Lõi Floyd và Brent giữ số lượng hằng các **trạng thái BigInteger** x,y,ys,q,...: O(1) số lượng biến số lớn, mỗi số chứa O(log N) bit.

Để phân tích hoàn chỉnh, cần thêm stack chứa các mảnh chưa xử lý và map số mũ. Nếu lưu mọi xi trong một Set để phát hiện cycle, bộ nhớ có thể phình rất lớn; Floyd/Brent không cần làm vậy.

### 10.5. Khi nào nên chọn thuật toán khác?

| Phương pháp | Phù hợp | Hạn chế |
|---|---|---|
| Chia thử | N nhỏ, ước nhỏ | O(√N) trong trường hợp xấu |
| Sàng nguyên tố nhỏ | Phân tích nhiều N hoặc loại prime factors nhỏ | Cần giới hạn/bộ nhớ sàng |
| Pollard rho Floyd | Cần cài ngắn, hiểu rõ gcd/cycle | Gcd thường xuyên |
| Pollard rho Brent | Muốn batch gcd để giảm overhead | Phục hồi g=N, mã khó hơn |
| ECM | Khi tìm thừa số trung bình trong số lớn | Phức tạp hơn |
| Quadratic sieve / NFS | Phân tích số rất lớn theo điều kiện chuyên biệt | Chi phí thực thi/tài nguyên cao |

## 11. Oracle độc lập bằng chia thử

Đối với N nhỏ, muốn xác minh code rho nên có một cách giải **độc lập**. Phép chia thử từng số nguyên tố tiềm năng tới √N đủ để làm oracle.

```text
trialFactor(N):
    d = 2
    while d*d <= N:
        while N % d == 0:
            count[d]++
            N /= d
        d = nextCandidate(d)

    if N > 1:
        count[N]++
```

Kết quả là map `prime -> exponent`. So map này với kết quả Pollard hoàn chỉnh.

### 11.1. Những điều nên kiểm trong mỗi case

1. Tích mọi prime powers bằng N.
2. Mỗi p cuối cùng là nguyên tố theo oracle phù hợp.
3. Nếu có một ước d được rho trả, chắc chắn `1<d<N` và `N%d=0`.
4. Không mất số mũ khi N chứa p², p³ hoặc nhiều lũy thừa.
5. Hai cài đặt có thể tìm factor theo thứ tự khác nhau nhưng map cuối phải giống nhau.
6. N=1 và N=0 tuân thủ hợp đồng đầu vào thay vì chạy vào lỗi chia/modulo.

### 11.2. Không đánh đồng brute test nhỏ với chứng minh mọi input

Kiểm tra trên 500 hay 5000 N ngẫu nhiên không thể chứng minh phương pháp luôn tìm được ước trong một budget cố định, nhất là với bán nguyên tố lớn hoặc input đối kháng. Kiểm thử giúp kiểm **bất biến triển khai**, không thay thế phân tích xác suất và chính sách lỗi.

## 12. Java 17 — đối chiếu với oracle trial division

Chương trình độc lập thứ ba so map factorization bằng **Floyd/BigInteger** với **phép chia thử long** trên 9 input cố định và 500 input sinh theo `Random` có seed. Những input thử đủ nhỏ để trial division cho kết quả xác định.

Lưu thành **PollardRhoTrialOracleDemo.java**:

```java
import java.math.BigInteger;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;
import java.util.Random;
import java.util.SortedMap;
import java.util.TreeMap;

public class PollardRhoTrialOracleDemo {
    static final BigInteger ONE = BigInteger.ONE;
    static final BigInteger TWO = BigInteger.TWO;
    static final BigInteger THREE = BigInteger.valueOf(3);
    static final BigInteger ZERO = BigInteger.ZERO;

    static BigInteger f(BigInteger x, BigInteger c, BigInteger n) {
        return x.multiply(x).add(c).mod(n);
    }

    static BigInteger rho(BigInteger n) {
        if (n.mod(TWO).equals(ZERO)) return TWO;
        if (n.mod(THREE).equals(ZERO)) return THREE;

        for (int attempt = 1; attempt <= 64; attempt++) {
            BigInteger c = BigInteger.valueOf(attempt);
            BigInteger x = TWO, y = TWO, d = ONE;

            for (int iter = 0; iter < 100_000 && d.equals(ONE); iter++) {
                x = f(x, c, n);
                y = f(f(y, c, n), c, n);
                d = x.subtract(y).abs().gcd(n);
            }
            if (d.compareTo(ONE) > 0 && d.compareTo(n) < 0) {
                return d;
            }
        }
        throw new IllegalStateException("Rho inconclusive: " + n);
    }

    static SortedMap<Long, Integer> rhoFactor(long value) {
        SortedMap<Long, Integer> result = new TreeMap<>();
        Deque<BigInteger> pending = new ArrayDeque<>();
        if (value < 2) throw new IllegalArgumentException("n >= 2");
        pending.add(BigInteger.valueOf(value));

        while (!pending.isEmpty()) {
            BigInteger n = pending.removeLast();
            if (n.equals(ONE)) continue;
            if (n.isProbablePrime(80)) {
                long factor = n.longValueExact();
                result.merge(factor, 1, Integer::sum);
                continue;
            }

            BigInteger d = rho(n);
            if (!n.mod(d).equals(ZERO)
                    || d.compareTo(ONE) <= 0
                    || d.compareTo(n) >= 0) {
                throw new IllegalStateException("Bad rho factor");
            }
            pending.addLast(d);
            pending.addLast(n.divide(d));
        }
        return result;
    }

    static SortedMap<Long, Integer> trialFactor(long value) {
        SortedMap<Long, Integer> result = new TreeMap<>();
        long n = value;

        for (long d = 2; d <= n / d; d += (d == 2 ? 1 : 2)) {
            while (n % d == 0) {
                result.merge(d, 1, Integer::sum);
                n /= d;
            }
        }
        if (n > 1) result.merge(n, 1, Integer::sum);
        return result;
    }

    static void check(long n) {
        SortedMap<Long, Integer> actual = rhoFactor(n);
        SortedMap<Long, Integer> expected = trialFactor(n);
        if (!actual.equals(expected)) {
            throw new IllegalStateException(
                    "Mismatch for " + n
                    + ": rho=" + actual + ", trial=" + expected);
        }

        BigInteger product = ONE;
        for (Map.Entry<Long, Integer> e : actual.entrySet()) {
            product = product.multiply(
                    BigInteger.valueOf(e.getKey()).pow(e.getValue()));
        }
        if (!product.equals(BigInteger.valueOf(n))) {
            throw new IllegalStateException("Wrong product for " + n);
        }
    }

    public static void main(String[] args) {
        long[] fixed = {
            2, 3, 4, 12, 8051, 10403,
            100140049, 41041, 600851475143L
        };
        for (long n : fixed) check(n);
        System.out.println("Fixed cases checked: " + fixed.length);

        Random random = new Random(4032026L);
        int count = 500;
        for (int i = 0; i < count; i++) {
            long n = 2L + random.nextInt(200_000);
            check(n);
        }
        System.out.println("Random cases checked: " + count);
        System.out.println("All factorizations match trial division: true");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 PollardRhoTrialOracleDemo.java
java PollardRhoTrialOracleDemo
```

**Stdout:**

```text
Fixed cases checked: 9
Random cases checked: 500
All factorizations match trial division: true
```

### 12.1. Vì sao phép thử long dùng `d<=n/d`?

Nếu N rất lớn, `d*d` trên long có thể overflow. Với N>0,d≥2:

`d<=n/d`

tương đương `d²<=n` nhưng không cần nhân d². Trong demo input dưới 10^12, cách này cũng bảo vệ logic khi đổi input lớn hơn.

### 12.2. Seed chỉ phục vụ tái lập test

`Random(4032026L)` sinh các số kiểm thử theo trình tự ổn định. Nó **không được dùng làm chứng nhận độ ngẫu nhiên của Pollard** trong chương trình này, vì rho thử c theo thứ tự cố định.

### 12.3. So multiset chứ không so factor đầu tiên

Pollard có thể trả 83 hoặc97 cho N=8051, hay một ước hợp số của 41041. Phần phân tích cuối sau sort và cộng exponent mới là đối tượng cần so với trial division.

## 13. Các tình huống biên

| Trường hợp | Cách xử lý |
|---|---|
| N=0 | Báo không có phân tích hữu hạn chuẩn |
| N=1 | Tích rỗng, không có prime factors |
| N=-1 | Chỉ dấu -1 |
| N âm | Tách dấu -1, phân tích |N| |
| N nguyên tố | Không có d giữa1 và N, không chạy rho nếu đã primality check |
| N chẵn | Trả d=2 ngay |
| N chia hết3 | Trả d=3 ngay sau kiểm chẵn |
| N=p² | Có thể trả d=p; cần exponent2 |
| N có p³ hoặc nhiều p lặp | Cộng đúng exponent |
| N có nhiều thừa số nguyên tố | Một lần gcd có thể trả ước hợp số |
| `gcd=1` | Chưa đủ thông tin |
| `gcd=N` | Retry hoặc cứu batch |
| Attempt hết budget | Inconclusive |
| Input rất lớn | Giới hạn bit/time/calls, dùng thuật toán khác nếu cần |
| BigInteger prime test `true` | Probable prime, không phải chứng chỉ tất định |
| N có các thừa số gần bằng nhau rất lớn | Rho có thể trở nên rất chậm |

### 13.1. Vì sao 0 không giống 1?

1 là tích rỗng của các số nguyên tố. Nhưng 0 chia hết cho **mọi số nguyên khác 0**, không có một danh sách prime powers hữu hạn xác định như các số nguyên khác 0. Không dùng cách “factor(0)=0” rồi bảo đó là một phân tích prime.

### 13.2. Vì sao một lần tách 360 chưa đủ?

Rho có thể trả 2, cho `360=2·180`. Nhưng 180 hợp số và còn 2^2·3²·5. Chỉ khi đã phân tích tiếp tất cả nhánh và cộng exponent mới ra 2³·3²·5.

### 13.3. Tính xác suất và tính đúng tách biệt

Một attempt có xác suất thành công khác nhau tùy polynomial, nhưng nếu trả `d` thỏa các điều kiện chia hết thì **bước tách là đúng xác định**. Chỗ có tính xác suất chủ yếu là **thời điểm tìm thấy d** và **primality test** nếu dùng bản xác suất.

## 14. Sai lầm thường gặp

### Lỗi 1 — Nhận d=N làm ước hợp lệ

d=N không làm input nhỏ đi. Chỉ nhận `1<d<N` rồi kiểm chia hết.

### Lỗi 2 — Gcd=1 nghĩa là N nguyên tố

Sai. Nó chỉ nói chưa có va chạm hữu ích trong cặp hiện tại.

### Lỗi 3 — Không kiểm primality trước khi tách

Nếu N prime, rho không thể tìm d không tầm thường và có thể tốn hết budget.

### Lỗi 4 — Coi d luôn nguyên tố

Gcd có thể trả hợp số như 1001. Phải phân tích tiếp.

### Lỗi 5 — Chỉ phân tích d, bỏ N/d

Làm thiếu thừa số. Stack phải xử lý cả hai mảnh.

### Lỗi 6 — Không lấy modulo mỗi bước

`f(x)=(x²+c) mod N`, không phải x²+c không giới hạn.

### Lỗi 7 — Tràn long ở x*x

Modulo sau phép nhân **không cứu được** overflow đã xảy ra trước đó. BigInteger hoặc mulMod an toàn.

### Lỗi 8 — Không dùng trị tuyệt đối khi lấy hiệu

Công thức dùng `gcd(|x−y|,N)`. Dùng `abs()` để bảo đảm tính rõ ràng.

### Lỗi 9 — Quên restart sau gcd=N

Đổi seed/c hoặc dùng recovery trong Brent; không tiếp tục cùng attempt bất tận.

### Lỗi 10 — Không giới hạn số vòng

Một lần thử có thể không tìm ra ước trong thời gian mong muốn. Cần budget và thông báo inconclusive.

### Lỗi 11 — Không reset x,y,g,q khi đổi c

Mỗi attempt phải khởi tạo trạng thái rõ ràng.

### Lỗi 12 — Cố định seed nhưng quảng bá random

Seed2, c1..96 là demo tái lập, không phải chiến lược chống input đối kháng.

### Lỗi 13 — Hứa chắc chắn sqrt(p) bước

Kỳ vọng birthday paradox không phải giới hạn worst-case cho mọi input.

### Lỗi 14 — Gọi Pollard đa thức theo số bit

N^(1/4) vẫn là hàm mũ theo log N.

### Lỗi 15 — Không tính chi phí BigInteger

Mỗi phép nhân/mod/gcd có chi phí bit, không mặc định O(1).

### Lỗi 16 — Dùng Set làm mất số mũ

N=360 cần `{2:3,3:2,5:1}`, không chỉ `{2,3,5}`.

### Lỗi 17 — Đưa N=0 vào modulo

Phải xét N=0 riêng; BigInteger.mod(0) không hợp lệ.

### Lỗi 18 — Quên dấu âm

Với N âm phải tách đơn vị -1 và phân tích trị tuyệt đối.

### Lỗi 19 — Gọi N=1 là prime

1 không phải số nguyên tố.

### Lỗi 20 — Coi probable prime là chứng chỉ nguyên tố

`isProbablePrime(certainty)` là kiểm xác suất; có thể cần chứng minh khác nếu yêu cầu chắc chắn.

### Lỗi 21 — Kiểm Fermat một cơ số rồi kết luận prime

Carmichael/pseudoprimes có thể đánh lừa kiểm yếu.

### Lỗi 22 — Brent g=N mà không có bước cứu

Batch có thể gom các ước khác nhau thành gcd=N. Thử từng hiệu từ ys hoặc restart.

### Lỗi 23 — Không mod tích q trong Brent

q lớn cực nhanh; mod N giữ tính chất gcd mà giảm kích thước.

### Lỗi 24 — Mang q từ lần thử trước

Mỗi batch/attempt phải khởi tạo q nhất quán.

### Lỗi 25 — Kiểm tích đúng mà quên prime test

Tích hợp số vẫn đúng về mặt nhân nhưng chưa là phân tích thành nguyên tố.

### Lỗi 26 — Không kiểm N%d=0

Bước tìm ước chỉ đáng tin khi d thực sự chia N.

### Lỗi 27 — So thứ tự phát hiện factor

Hai thuật toán có thể tách theo thứ tự khác nhau. So map prime powers sau sắp xếp.

### Lỗi 28 — Dùng sqrt(double) làm căn chính xác BigInteger

Double không đủ chính xác cho các số lớn. Dùng phép so nguyên hoặc thuật toán số học nguyên.

### Lỗi 29 — Hết budget rồi gắn nhãn N prime

Inconclusive không tương đương prime. Dùng primality test riêng.

### Lỗi 30 — Quên phép chia thử ước nhỏ

Kiểm 2,3 hoặc sàng nhỏ thường rẻ hơn một loạt phép BigInteger Pollard.

### Lỗi 31 — Luôn cho Brent nhanh hơn Floyd

Cần benchmark; batch có overhead và recovery.

### Lỗi 32 — Lưu mọi x_i không cần thiết

Floyd/Brent chỉ cần số hằng state; lưu Set toàn quỹ đạo có thể tốn bộ nhớ lớn.

### Lỗi 33 — Không giới hạn input người dùng

N với hàng nghìn bit có thể chiếm CPU rất lâu. Đặt budget và báo thất bại rõ.

### Lỗi 34 — Không kiểm lỗi khi đệ quy chia một ước

Nếu d==n, n/d=1 rồi tiếp tục n gây vòng lặp. Kiểm d trước.

### Lỗi 35 — Suy từ 500 bộ test rằng mọi số đều dễ

Test hữu hạn chỉ cho bằng chứng về triển khai ở các case đã chạy, không cho worst-case guarantee.

## 15. Kiểm thử mẫu có đáp án

| N hoặc tình huống | Kết quả |
|---|---|
| 8051 | 83·97 |
| 10403 | 101·103 |
| 100140049 | 10007² |
| 600851475143 | 71·839·1471·6857 |
| 360 | 2³·3²·5 |
| 41041 | 7·11·13·41 |
| -84 | -1·2²·3·7 |
| 1 | Không prime factors |
| -1 | Đơn vị dấu âm |
| 0 | Không có factorization hữu hạn chuẩn |
| 101 | Prime |
| Floyd(8051), c1,x0=2 | Vòng3 gcd=97 |
| Brent(41041), c1,batch32 | Trả một ước có thể hợp số: 1001 |
| Một attempt gcd=N | Restart |
| Một attempt hết steps với gcd1 | Inconclusive/retry |
| N=p² | Số mũ p bằng2 |
| N=2^20 | Số mũ2 bằng20 |

### 15.1. Kiểm tra kỹ lần đầu tiên trả d

Nếu `d>1`, `d<N`, `N mod d=0`, đó là một **bằng chứng chia hết xác định**. Không phụ thuộc xác suất để xác nhận việc d có phải ước của N hay không.

### 15.2. Kiểm hết các mảnh

Một factor map cuối chỉ đúng khi tích tái tạo N **và** các mảnh cuối được kiểm nguyên tố bằng công cụ đúng mức bảo đảm. Nếu mảnh còn hợp số, phải đưa lại vào stack.

### 15.3. Kiểm số âm

Với N=-84, sản phẩm xác minh phải là:

`(-1)·2²·3·7 = -84`.

Kiểm riêng phần dấu và trị tuyệt đối; đừng gọi `BigInteger.mod()` với môđun âm.

## 16. Bài tập có lời giải

### Bài 1 — Thành công một lần rho

Một d phải thỏa gì?

**Đáp án:** `1<d<N` và N chia hết d.

### Bài 2 — Tách 8051

Rho trả d=97; phần còn lại?

**Đáp án:** 83.

### Bài 3 — Gcd=1

Có thể kết luận N nguyên tố?

**Đáp án:** không. Tiếp tục hoặc restart.

### Bài 4 — Gcd=N

Có thể đệ quy tiếp trên d=N không?

**Đáp án:** không, input không giảm; restart.

### Bài 5 — Va chạm modulo p

Tại sao x≡y modp giúp tìm ước?

**Đáp án:** p chia x−y và N, nên gcd của hiệu với N chứa p.

### Bài 6 — Pollard biết p trước không?

**Đáp án:** không; tính residue modulo N và gcd trực tiếp.

### Bài 7 — Hàm f

N=8051, c=1, x0=2; x1?

**Đáp án:** 5.

### Bài 8 — Floyd rùa và thỏ

Sau vòng đầu, x=5, y?

**Đáp án:** 26.

### Bài 9 — Vòng3

Tại sao gcd(194,8051)=97?

**Đáp án:** 194=2·97, 8051=83·97.

### Bài 10 — Tên rho

**Đáp án:** quỹ đạo hàm trên tập hữu hạn có đuôi và chu trình giống hình chữ ρ.

### Bài 11 — Birthday paradox

Số bước heuristic liên hệ với p như thế nào?

**Đáp án:** cỡ √p theo mô hình ngẫu nhiên, không cam kết mọi attempt.

### Bài 12 — Semiprime cân bằng

N=pq với p≈q≈√N thì số bước heuristic?

**Đáp án:** N^(1/4).

### Bài 13 — Có đa thức theo bit length?

**Đáp án:** không; N^(1/4)≈2^(k/4) với N≈2^k.

### Bài 14 — Factor hợp số

d=1001 của N=41041 có nguyên tố không?

**Đáp án:** không, 1001=7·11·13.

### Bài 15 — 360

Factorization?

**Đáp án:** 2³·3²·5.

### Bài 16 — Chính phương

100140049?

**Đáp án:** 10007².

### Bài 17 — N âm

-84?

**Đáp án:** -1·2²·3·7.

### Bài 18 — N=1

Có prime factor không?

**Đáp án:** không.

### Bài 19 — N=0

Có factorization hữu hạn chuẩn không?

**Đáp án:** không.

### Bài 20 — Prime101

Có d với 1<d<101 chia hết 101 không?

**Đáp án:** không.

### Bài 21 — isProbablePrime

True có chứng minh nguyên tố tuyệt đối?

**Đáp án:** không; là probable prime theo certainty.

### Bài 22 — Overflow

Vì sao `(x*x+c)%N` với long nguy hiểm?

**Đáp án:** nhân tràn trước khi modulo. Dùng BigInteger hoặc mulMod an toàn.

### Bài 23 — Brent batch

Vì sao nhân q rồi gcd?

**Đáp án:** gom các hiệu để giảm số lần gcd, vẫn giữ khả năng phát hiện ước.

### Bài 24 — Brent g=N

Làm gì?

**Đáp án:** gcd từng hiệu từ ys hoặc restart.

### Bài 25 — Thử mãi thất bại

Có thể gọi N prime không?

**Đáp án:** không, chỉ inconclusive.

### Bài 26 — Kiểm d

Ba kiểm tra bắt buộc?

**Đáp án:** d>1, d<N, N%d=0.

### Bài 27 — Kiểm kết quả

Tích đúng N đã đủ đảm bảo mọi mảnh là nguyên tố?

**Đáp án:** chưa; cần primality check.

### Bài 28 — Sàng trước rho

Tại sao?

**Đáp án:** các ước nhỏ dễ tìm, giảm số phép modulo lớn.

### Bài 29 — N có ước p≈10^4

Pollard rho có thể làm cỡ bao nhiêu bước theo heuristic?

**Đáp án:** cỡ √p≈100, nhưng một attempt cụ thể không được bảo đảm.

### Bài 30 — Kiểm thử random

500 ca random có chứng minh đúng trên mọi N?

**Đáp án:** không; đó là kiểm thử triển khai, không là chứng minh tổng quát.

## 17. Checklist cuối bài

1. Có phân biệt tìm một ước và phân tích nguyên tố hoàn toàn?
2. N=0,1,-1, N âm đã xử lý?
3. N=2 hoặc chia hết 2/3 có xử lý nhanh?
4. Có kiểm prime/probable prime trước rho?
5. Có giải thích khác nhau giữa probable prime và chứng chỉ nguyên tố?
6. f(x) có tính modulo N ở mỗi bước?
7. Có dùng số học không tràn trong x²+c?
8. Floyd có x đi1 bước, y đi2 bước?
9. Gcd dùng trị tuyệt đối hiệu x−y?
10. Chỉ nhận d với 1<d<N và N%d=0?
11. Khi d=N, có retry/recovery?
12. Khi d=1 quá lâu, có budget và restart?
13. Khi hết attempts, có báo inconclusive?
14. Có reset x,y,g,q mỗi attempt?
15. Có xử lý cả hai mảnh d và N/d?
16. Nếu d hợp số, có phân tích tiếp?
17. Có lưu số mũ của các prime trùng nhau?
18. Có kiểm tích prime powers bằng |N|?
19. Có giữ dấu -1 khi N âm?
20. Có kiểm tính nguyên tố của từng mảnh cuối?
21. Trong Brent, q có được modulo N và reset mỗi batch?
22. Nếu Brent gcd batch=N, có cứu từng hiệu?
23. Có giới hạn bit length/time/budget cho input lớn?
24. Có tách demo seed cố định khỏi production randomized restart?
25. Có kiểm N prime, p², nhiều thừa số, N=0 và số âm?
26. Có thử Carmichael như 41041?
27. Có dùng oracle trial division độc lập trên input nhỏ?
28. Có hiểu O(√p) là heuristic expected steps, không là worst-case?
29. Có tính chi phí BigInteger per step?
30. Khi benchmark, có đo số gcd, modular multiplications và restarts?

**Tổng kết:** Pollard rho tạo quỹ đạo `x ↦ (x²+c) mod N`, tìm va chạm modulo một thừa số chưa biết qua `gcd(|x−y|,N)`. Floyd dùng rùa–thỏ; Brent gộp nhiều hiệu trong một batch để giảm số gcd. `d=1` nghĩa là chưa phát hiện được ước; `d=N` nghĩa là attempt không tách được; chỉ `1<d<N` mới là một ước hữu ích. Muốn **phân tích hoàn toàn thành prime powers**, phải tiếp tục cả d và N/d, kiểm từng mảnh và xác minh tích, đồng thời báo rõ mức chắc chắn của primality test và giới hạn ngân sách thực thi.
