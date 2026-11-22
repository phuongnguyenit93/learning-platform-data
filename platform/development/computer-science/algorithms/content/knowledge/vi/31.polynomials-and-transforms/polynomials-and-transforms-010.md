# Ứng dụng tích chập vào đếm cặp và phân bố tổng

## 1. Động cơ: từ hai dãy đến mọi tổng có thể có

Cho hai dãy số nguyên A và B. Với mỗi số nguyên s, cần đếm số cặp **chỉ số** (i,j), i thuộc A và j thuộc B, thỏa A[i]+B[j]=s. Hai phần tử có cùng giá trị nhưng khác chỉ số vẫn là các lựa chọn khác nhau. Nếu |A|=n và |B|=m, ta có tổng cộng n*m cặp.

Ví dụ: A=[-1,0,0,2] và B=[0,1,1]. Tổng các hệ số theo s là:

| s | -1 | 0 | 1 | 2 | 3 |
|---:|---:|---:|---:|---:|---:|
| Số cặp | 1 | 4 | 4 | 1 | 2 |

Kiểm tra 1+4+4+1+2=12=4*3. Giá trị s=0 có 4 cặp: từ -1+1 có 2 cặp và từ 0+0 có 2 cặp. Tích chập giúp xây **toàn bộ phân bố tổng** thay vì tính riêng từng s.

## 2. Histogram, đa thức sinh và công thức tích chập

Đặt fA[x] là số lần giá trị x xuất hiện trong A; fB[y] tương tự. Số cặp có tổng s là:

**C[s] = tổng theo mọi x của fA[x] * fB[s-x].**

Bởi một cặp có tổng s và phần tử đầu bằng x thì phần tử thứ hai phải bằng s-x; có fA[x] cách chọn chỉ số đầu và fB[s-x] cách chọn chỉ số sau. Các nhóm theo x rời nhau, nên cộng lại cho đúng tổng số cặp.

Nếu các giá trị không âm, viết đa thức sinh F_A(z)=sum fA[x]*z^x và F_B(z)=sum fB[y]*z^y. Hệ số của z^s trong tích F_A(z)*F_B(z) chính là C[s].

Trong thuật toán mảng, nếu a dài p, b dài q, tích chập tuyến tính c dài p+q-1:

**c[k] = sum a[i]*b[j] với i+j=k.**

Đây là phép nhân đa thức, **không phải nhân từng cặp phần tử cùng chỉ số**.

### 2.1. Ví dụ nhân từng hệ số

Histogram theo offset của A là [1,2,0,1], ứng với giá trị -1,0,1,2. Histogram của B là [1,2], ứng với 0,1. Nhân:

```text
a=[1,2,0,1], b=[1,2]
c=[1,4,4,1,2]

c[0]=1*1=1
c[1]=1*2+2*1=4
c[2]=2*2+0*1=4
c[3]=0*2+1*1=1
c[4]=1*2=2
```

Chỉ số kết quả k tương ứng tổng s = min(A)+min(B)+k. Ở ví dụ này offset bằng -1 nên c[1] ứng với tổng 0.

### 2.2. Số âm và dịch gốc

Với minA=min(A), maxA=max(A), ta tạo mảng a[i] lưu tần suất của giá trị minA+i, i từ 0 tới maxA-minA. B tương tự. Kết quả c[k] ứng với tổng **minA+minB+k**. Tính offset/tổng bằng long để tránh tràn khi hai phần tử int có trị tuyệt đối lớn.

Nhờ dịch gốc, không có chỉ số âm trong mảng. Nhưng nếu min=-10^9 và max=10^9, histogram đặc sẽ cực lớn dù chỉ có vài phần tử. Khi miền giá trị rộng và thưa nên dùng Map sparse; không cố cấp phát mảng hàng tỷ ô.

## 3. Ba kiểu đếm cặp không được đánh đồng

### 3.1. Cặp giữa hai dãy khác nhau

Cross(A,B): (i,j) với i trong A, j trong B. Tích chập fA*fB là đáp án; tổng c[s]=|A|*|B|. Nếu A hoặc B rỗng, phân bố rỗng và tổng cặp bằng 0.

### 3.2. Cặp có thứ tự trong cùng một dãy

Với dãy X dài n, C=f*f đếm **tất cả cặp (i,j)**, bao gồm i=j và hai thứ tự (i,j), (j,i). Tổng mọi hệ số là n^2, không phải n(n-1)/2.

### 3.3. Cặp hai chỉ số phân biệt i<j

Đường chéo i=j đóng góp một lần tại tổng 2*X[i]. Gọi D[s] là số chỉ số i có 2*X[i]=s. Khi một giá trị v xuất hiện f[v] lần, **D[2*v]+=f[v]**, không phải cộng một lần duy nhất.

Sau khi trừ D khỏi C, mỗi cặp hai chỉ số phân biệt vẫn xuất hiện theo hai thứ tự, nên:

**U[s] = (C[s] - D[s]) / 2**.

U[s] đếm cặp i<j, và tổng U[s]=n(n-1)/2. Từng C[s]-D[s] **phải chẵn**, là bất biến hữu ích để phát hiện lỗi.

### 3.4. Ví dụ với phần tử trùng nhau

X=[1,1,2,3], histogram f=[2,1,1] ở các giá trị 1,2,3.

```text
Tổng s                      2  3  4  5  6
C=f*f (gồm i=j)            4  4  5  2  1
D (chỉ các i=j)            2  0  1  0  1
C-D                         2  4  4  2  0
U=(C-D)/2                  1  2  2  1  0
```

Phân bố i<j là {2=1, 3=2, 4=2, 5=1}, có đúng 6 cặp. Hai số 1 ở **hai chỉ số khác nhau** vẫn tạo cặp tổng 2. Đề yêu cầu **hai giá trị phân biệt** là bài toán khác với yêu cầu **hai chỉ số phân biệt**.

## 4. Phân bố tổng xác suất

Nếu hai biến ngẫu nhiên X,Y **độc lập** và nhận giá trị nguyên, với PMF pX[k]=P(X=k), pY[k]=P(Y=k), ta có:

P(X+Y=s)=sum pX[k]*pY[s-k].

Đây vẫn là tích chập, nhưng hệ số là xác suất thực, tổng toàn bộ hệ số phải bằng 1 nếu hai PMF hợp lệ. Ví dụ X có xác suất (0.5,0.5) cho 0,1; Y có xác suất (0.25,0.75):

```text
P(X+Y=0)=0.125
P(X+Y=1)=0.500
P(X+Y=2)=0.375
Tổng=1.000
```

**Độc lập là điều kiện cần trong công thức này khi chỉ biết hai phân phối biên.** Nếu phụ thuộc, cần phân phối chung P(X=x,Y=y). NTT nguyên modulo số nguyên tố không trực tiếp tính xác suất thực; có thể dùng tích chập trực tiếp số thực hoặc FFT với kiểm soát sai số.

## 5. Tích chập trực tiếp O(p*q)

```text
c = mảng zero dài p+q-1
for i=0..p-1:
    for j=0..q-1:
        c[i+j] += a[i]*b[j]
```

Độ phức tạp thời gian O(p*q), bộ nhớ O(p+q) cho kết quả. Đây là thuật toán dễ chứng minh, không có sai số floating-point, phù hợp dữ liệu nhỏ và làm oracle cho biến đổi nhanh. Khi dùng long trong Java, Math.multiplyExact/Math.addExact giúp phát hiện tràn thay vì trả giá trị sai.

Với nhiều truy vấn tổng s, xây sẵn c rồi trả lời mỗi truy vấn O(1). Nếu chỉ hỏi **một** tổng s, có thể dùng HashMap tần suất B và duyệt A, cộng freqB[s-A[i]] trong O(n+m) kỳ vọng, thường đơn giản hơn dựng toàn bộ tích chập.

## 6. NTT: tăng tốc nhưng phải chứng minh tính exact

**NTT** (Number Theoretic Transform) thực hiện biến đổi như FFT trong trường modulo một số nguyên tố. Sau biến đổi, nhân hệ số từng vị trí rồi biến đổi nghịch thu được tích chập **theo modulo P**.

Mã chọn **P=998244353**, căn nguyên thủy 3, hỗ trợ độ dài biến đổi N lũy thừa 2 với N<=2^23. Để tính **linear convolution** từ hai mảng dài p và q, phải zero-pad đến N>=p+q-1; nếu thiếu padding sẽ tính cyclic convolution và trộn nhầm các tổng.

Các bước: (1) sao chép/pad a,b; (2) NTT thuận; (3) nhân từng hệ số modulo P; (4) NTT nghịch và chuẩn hóa bằng nghịch đảo N modulo P; (5) lấy p+q-1 hệ số đầu.

### 6.1. Một môđun không mặc định cho số đếm nguyên chính xác

Nếu hệ số đúng bằng P+7, NTT một môđun chỉ trả 7. Vì vậy **không** được dùng số dư như số đếm thật khi chưa có cận.

Với hai histogram không âm, mọi hệ số đều <= totalA*totalB = |A|*|B|. Điều kiện đủ **|A|*|B| < P** chứng minh mọi hệ số trong [0,P-1] và do đó khôi phục exact bằng một môđun. Điều kiện này bảo thủ nhưng đơn giản và an toàn.

Trong mã, convolveNTTExact từ chối trường hợp thiếu cận hoặc độ dài N không hợp lệ. convolveExact dùng NTT chỉ khi an toàn; nếu không, fallback tích chập trực tiếp với long chính xác (có thể chậm). Muốn cả tốc độ và exact với hệ số rất lớn, có thể dùng **nhiều NTT primes + CRT** khi tích môđun lớn hơn cận hệ số, hoặc cách tính nguyên lớn thích hợp.

### 6.2. Phép nhân modulo và kiểu long

Hai số dư <998244353 nên tích của chúng <10^18, nhỏ hơn Long.MAX_VALUE (~9.22*10^18); tính long rồi % P an toàn. Điều này chỉ chứng minh **không tràn phép nhân số dư**, không chứng minh mọi hệ số thật nhỏ hơn P.

### 6.3. Độ phức tạp

Với histograms dài p, q và N là lũy thừa hai ít nhất p+q-1: NTT O(N log N) thời gian, O(N) bộ nhớ; schoolbook O(p*q) thời gian, O(p+q) bộ nhớ. Thời gian dựng histogram O(|A|+|B|+p+q). Nếu cần fallback schoolbook khi totalPairs>=P, không được quảng cáo toàn bộ thuật toán này là O(N log N) trong mọi trường hợp.

## 7. Chọn thuật toán theo miền giá trị

**Dense histogram:** phù hợp với dải giá trị hẹp, kể cả có số âm; nhanh cho nhiều truy vấn tổng.

**Sparse Map:** khi có ít giá trị phân biệt nhưng khoảng cách rất xa, dùng Map<Long,Long> tần suất, nhân trên các cặp khóa phân biệt O(uA*uB) rồi cộng vào Map tổng. Không cần cấp phát đến max-min+1.

**HashMap hai-sum:** phù hợp khi chỉ hỏi một tổng đích, không cần toàn bộ phân bố.

**FFT thực:** hỗ trợ hệ số thực nhưng có sai số floating-point; nếu cần đếm chính xác số nguyên lớn, cân nhắc NTT+CRT hoặc schoolbook/BigInteger.

**NTT modulo:** tuyệt đối phân biệt **đếm modulo P** với **đếm exact**. Với phép tính trên tần suất không âm, cận tổng số cặp là cách dễ kiểm tra exact.

## 8. Hợp đồng của chương trình

Chương trình Java 17 bên dưới nhận các dãy int, lưu các tổng dưới dạng long và các tần suất/số cặp dạng long. Histogram đặc giới hạn **dải max-min+1<=100000** để tránh hết bộ nhớ. Nếu dữ liệu thưa quá rộng, ném IllegalArgumentException với hướng dẫn dùng sparse counting; đây là chính sách demo, không phải hạn chế của tích chập về mặt toán học.

API:

- cross(A,B) đếm cặp chỉ số giữa hai dãy;
- orderedAll(X) đếm tất cả (i,j), kể cả self i=j;
- unorderedDistinct(X) trả đếm i<j bằng trừ diagonal rồi chia hai;
- Distribution.get(sum) truy vấn một tổng theo offset;
- convolveNaive và convolveNTTExact hỗ trợ kiểm thử độc lập về nhân hệ số;
- Oracle TreeMap duyệt trực tiếp các cặp **chỉ số gốc**, không dùng histogram.

Để kiểm thử độ chính xác NTT, bản demo sinh các histogram độ dài 128 có hệ số 0..3, tích số lần xuất hiện nhỏ hơn MOD; đối chiếu 180 lần NTT với schoolbook.


## 9. Java 17+ đầy đủ — PairSumConvolutionDemo

Tạo tệp `PairSumConvolutionDemo.java`. Chương trình chạy trên JDK 17 trở lên, không cần thư viện ngoài.

```java
import java.util.Arrays;
import java.util.Map;
import java.util.Objects;
import java.util.Random;
import java.util.StringJoiner;
import java.util.TreeMap;

public final class PairSumConvolutionDemo {
    private PairSumConvolutionDemo() {}

    static final long MOD = 998_244_353L;
    static final long ROOT = 3L;
    static final int MAX_NTT_N = 1 << 23;
    static final int MAX_WIDTH = 100_000;

    public record Distribution(long offset, long[] count) {
        public long get(long sum) {
            long index = sum - offset;
            if (index < 0 || index >= count.length) return 0;
            return count[(int) index];
        }

        public long total() {
            long result = 0;
            for (long x : count) result = Math.addExact(result, x);
            return result;
        }

        @Override
        public String toString() {
            StringJoiner out = new StringJoiner(", ", "{", "}");
            for (int i = 0; i < count.length; i++) {
                if (count[i] != 0) {
                    out.add((offset + i) + "=" + count[i]);
                }
            }
            return out.toString();
        }
    }

    private record Hist(long min, long[] freq) {}

    private static Hist histogram(int[] data) {
        Objects.requireNonNull(data, "data");
        if (data.length == 0) return new Hist(0, new long[0]);

        int lo = data[0], hi = data[0];
        for (int x : data) {
            lo = Math.min(lo, x);
            hi = Math.max(hi, x);
        }

        long width = (long) hi - (long) lo + 1;
        if (width > MAX_WIDTH) {
            throw new IllegalArgumentException(
                "value span too wide: use sparse counting"
            );
        }

        long[] freq = new long[(int) width];
        for (int x : data) {
            freq[(int) ((long) x - lo)]++;
        }
        return new Hist(lo, freq);
    }

    private static long sumNonnegative(long[] a) {
        long result = 0;
        for (long x : a) {
            if (x < 0) throw new IllegalArgumentException(
                "frequency must not be negative"
            );
            result = Math.addExact(result, x);
        }
        return result;
    }

    public static long[] convolveNaive(
            long[] a, long[] b) {
        if (a.length == 0 || b.length == 0) return new long[0];

        int size = Math.addExact(a.length, b.length - 1);
        long[] c = new long[size];

        for (int i = 0; i < a.length; i++) {
            for (int j = 0; j < b.length; j++) {
                long term = Math.multiplyExact(a[i], b[j]);
                c[i + j] = Math.addExact(c[i + j], term);
            }
        }
        return c;
    }

    private static long power(long base, long exp) {
        long result = 1;
        while (exp > 0) {
            if ((exp & 1) != 0) {
                result = result * base % MOD;
            }
            base = base * base % MOD;
            exp >>= 1;
        }
        return result;
    }

    private static void transform(long[] a, boolean inverse) {
        int n = a.length;

        // Bit-reversal permutation.
        for (int i = 1, j = 0; i < n; i++) {
            int bit = n >> 1;
            while ((j & bit) != 0) {
                j ^= bit;
                bit >>= 1;
            }
            j ^= bit;

            if (i < j) {
                long tmp = a[i]; a[i] = a[j]; a[j] = tmp;
            }
        }

        for (int len = 2; len <= n; len <<= 1) {
            long wlen = power(ROOT, (MOD - 1) / len);
            if (inverse) wlen = power(wlen, MOD - 2);

            for (int start = 0; start < n; start += len) {
                long w = 1;
                int half = len >> 1;

                for (int j = 0; j < half; j++) {
                    long u = a[start + j];
                    long v = a[start + j + half] * w % MOD;

                    long add = u + v;
                    if (add >= MOD) add -= MOD;

                    long sub = u - v;
                    if (sub < 0) sub += MOD;

                    a[start + j] = add;
                    a[start + j + half] = sub;
                    w = w * wlen % MOD;
                }
            }
        }

        if (inverse) {
            long invN = power(n, MOD - 2);
            for (int i = 0; i < n; i++) {
                a[i] = a[i] * invN % MOD;
            }
        }
    }

    // Exact only after proving every coefficient < MOD.
    public static long[] convolveNTTExact(
            long[] a, long[] b) {
        if (a.length == 0 || b.length == 0) return new long[0];

        int needed = Math.addExact(a.length, b.length - 1);
        long countA = sumNonnegative(a);
        long countB = sumNonnegative(b);

        if (countA == 0 || countB == 0) {
            return new long[needed];
        }
        if (countA > (MOD - 1) / countB) {
            throw new IllegalArgumentException(
                "one NTT modulus cannot certify exact counts"
            );
        }

        int n = 1;
        while (n < needed && n < MAX_NTT_N) n <<= 1;
        if (n < needed) {
            throw new IllegalArgumentException(
                "NTT length exceeds 2^23"
            );
        }

        long[] fa = new long[n];
        long[] fb = new long[n];
        for (int i = 0; i < a.length; i++) fa[i] = a[i] % MOD;
        for (int i = 0; i < b.length; i++) fb[i] = b[i] % MOD;

        transform(fa, false);
        transform(fb, false);

        for (int i = 0; i < n; i++) {
            fa[i] = fa[i] * fb[i] % MOD;
        }

        transform(fa, true);
        return Arrays.copyOf(fa, needed);
    }

    private static long[] convolveExact(
            long[] a, long[] b) {
        if (a.length == 0 || b.length == 0) return new long[0];

        int size = Math.addExact(a.length, b.length - 1);
        if (size <= 128) return convolveNaive(a, b);

        long countA = sumNonnegative(a);
        long countB = sumNonnegative(b);

        int n = 1;
        while (n < size && n < MAX_NTT_N) n <<= 1;

        if (countB > 0
                && countA <= (MOD - 1) / countB
                && n >= size) {
            return convolveNTTExact(a, b);
        }

        // Exact fallback, possibly slower than NTT.
        return convolveNaive(a, b);
    }

    public static Distribution cross(int[] a, int[] b) {
        Hist ha = histogram(a);
        Hist hb = histogram(b);

        if (ha.freq().length == 0 || hb.freq().length == 0) {
            return new Distribution(0, new long[0]);
        }

        return new Distribution(
            ha.min() + hb.min(),
            convolveExact(ha.freq(), hb.freq())
        );
    }

    public static Distribution orderedAll(int[] x) {
        Hist h = histogram(x);
        if (h.freq().length == 0) {
            return new Distribution(0, new long[0]);
        }

        return new Distribution(
            2L * h.min(),
            convolveExact(h.freq(), h.freq())
        );
    }

    // Count index pairs i<j (no self-pair, no double-order).
    public static Distribution unorderedDistinct(int[] x) {
        Hist h = histogram(x);
        if (h.freq().length == 0) {
            return new Distribution(0, new long[0]);
        }

        long[] c = convolveExact(h.freq(), h.freq());

        // Remove diagonal (i,i) at sum 2*x[i].
        for (int i = 0; i < h.freq().length; i++) {
            c[2 * i] -= h.freq()[i];
        }

        for (int i = 0; i < c.length; i++) {
            if (c[i] < 0 || (c[i] & 1) != 0) {
                throw new AssertionError(
                    "diagonal/parity invariant failed"
                );
            }
            c[i] /= 2;
        }

        return new Distribution(2L * h.min(), c);
    }

    // Oracle: loop over original indices, not histograms.
    private static Map<Long, Long> bruteCross(
            int[] a, int[] b) {
        Map<Long, Long> out = new TreeMap<>();
        for (int x : a) {
            for (int y : b) {
                out.merge((long) x + y, 1L, Long::sum);
            }
        }
        return out;
    }

    private static Map<Long, Long> bruteUnordered(int[] x) {
        Map<Long, Long> out = new TreeMap<>();
        for (int i = 0; i < x.length; i++) {
            for (int j = i + 1; j < x.length; j++) {
                out.merge((long) x[i] + x[j], 1L, Long::sum);
            }
        }
        return out;
    }

    private static void verify(
            Distribution actual,
            Map<Long, Long> expected, long total) {
        for (Map.Entry<Long, Long> e : expected.entrySet()) {
            if (actual.get(e.getKey()) != e.getValue()) {
                throw new AssertionError(
                    "wrong sum=" + e.getKey()
                );
            }
        }
        if (actual.total() != total) {
            throw new AssertionError("wrong total pairs");
        }
    }

    public static void main(String[] args) {
        int[] a = {-1, 0, 0, 2};
        int[] b = {0, 1, 1};
        int[] x = {1, 1, 2, 3};

        Distribution ab = cross(a, b);
        Distribution all = orderedAll(x);
        Distribution unique = unorderedDistinct(x);

        System.out.println("Cross A x B: " + ab);
        System.out.println("Cross total=" + ab.total());
        System.out.println("Cross sum=0: " + ab.get(0));
        System.out.println("Ordered all X: " + all);
        System.out.println("Ordered total=" + all.total());
        System.out.println("Unordered i<j X: " + unique);
        System.out.println("Unordered total=" + unique.total());
        System.out.println(
            "Empty cross: " + cross(new int[0], b)
        );

        verify(ab, bruteCross(a, b), 12);
        verify(unique, bruteUnordered(x), 6);

        Random random = new Random(416L);

        for (int trial = 0; trial < 2_500; trial++) {
            int[] left = new int[random.nextInt(9)];
            int[] right = new int[random.nextInt(9)];

            for (int i = 0; i < left.length; i++) {
                left[i] = random.nextInt(11) - 5;
            }
            for (int j = 0; j < right.length; j++) {
                right[j] = random.nextInt(11) - 5;
            }

            verify(cross(left, right),
                bruteCross(left, right),
                (long) left.length * right.length);
        }

        for (int trial = 0; trial < 2_500; trial++) {
            int[] v = new int[random.nextInt(10)];
            for (int i = 0; i < v.length; i++) {
                v[i] = random.nextInt(11) - 5;
            }

            long n = v.length;
            verify(unorderedDistinct(v),
                bruteUnordered(v), n * (n - 1) / 2);
        }

        for (int trial = 0; trial < 180; trial++) {
            long[] f = new long[128];
            long[] g = new long[128];
            for (int i = 0; i < 128; i++) {
                f[i] = random.nextInt(4);
                g[i] = random.nextInt(4);
            }

            if (!Arrays.equals(
                    convolveNTTExact(f, g),
                    convolveNaive(f, g))) {
                throw new AssertionError(
                    "NTT trial=" + trial
                );
            }
        }

        System.out.println("Brute random cross: 2500 PASS");
        System.out.println("Brute random unordered: 2500 PASS");
        System.out.println("NTT exact vs naive: 180 PASS");
    }
}
```

Biên dịch và chạy trong JDK 17+:

```bash
javac -encoding UTF-8 PairSumConvolutionDemo.java
java PairSumConvolutionDemo
```

**Đầu ra chuẩn:**

```text
Cross A x B: {-1=1, 0=4, 1=4, 2=1, 3=2}
Cross total=12
Cross sum=0: 4
Ordered all X: {2=4, 3=4, 4=5, 5=2, 6=1}
Ordered total=16
Unordered i<j X: {2=1, 3=2, 4=2, 5=1}
Unordered total=6
Empty cross: {}
Brute random cross: 2500 PASS
Brute random unordered: 2500 PASS
NTT exact vs naive: 180 PASS
```


## 10. Chứng minh tính đúng

**Cross:** mỗi cặp chỉ số (i,j) tạo đúng một cặp giá trị x=A[i],y=B[j] với x+y=s; nó đóng góp đúng một trong fA[x]*fB[y]. Ngược lại, fA[x]*fB[y] liệt kê mọi cách chọn chỉ số có hai giá trị đó. Cộng theo x+y=s không bỏ sót và không đếm trùng. Vì vậy hệ số tích chập là số cặp.

**Unordered i<j:** tích f*f đếm đủ n² cặp có thứ tự kể cả self. Đường chéo có đúng f[v] cặp tại mỗi tổng 2v. Loại đường chéo còn n(n-1) cặp ordered i!=j. Hai thứ tự (i,j),(j,i) tương ứng một tập hai chỉ số, cùng tổng; chia hai cho chính xác n(n-1)/2 cặp i<j. Tính chẵn của từng hệ số sau trừ diagonal là hệ quả bắt buộc.

**NTT exact:** NTT tính hệ số theo modulo MOD. Mọi hệ số histogram đều không âm và không vượt totalA*totalB. Nếu bound này nhỏ hơn MOD, số dư modulo trùng hệ số nguyên thật. Nếu không chứng minh được, chương trình không dùng số dư làm đáp án nguyên; fallback sang phép nhân trực tiếp với kiểm tra tràn.

## 11. Kiểm thử và các tình huống biên

Oracle TreeMap<Long,Long> đếm **trực tiếp các cặp chỉ số gốc**, độc lập với histogram, convolution và NTT. Chương trình kiểm 2.500 cặp dãy ngẫu nhiên và 2.500 dãy tự ghép, có số âm, số 0, giá trị trùng và mảng rỗng. NTT được thử riêng 180 lần trên hai histogram 128 hệ số, so exact với schoolbook.

Những kiểm tra nên có:

```text
A=[-1,0,0,2], B=[0,1,1] => {-1:1,0:4,1:4,2:1,3:2}
X=[1,1,2,3], i<j        => {2:1,3:2,4:2,5:1}
X=[1,1,2,3], all ordered => {2:4,3:4,4:5,5:2,6:1}
A=[] hoặc B=[]          => không có cặp
X=[] hoặc X=[7], i<j    => không có cặp
A=[Integer.MAX_VALUE], B=[Integer.MAX_VALUE]
  => tổng=4294967294 (long), có 1 cặp
```

Độ dài mảng trả về là p+q-1 với hai histogram không rỗng. Khi một dãy rỗng, bản demo trả phân bố rỗng. Không đánh đồng kiểm thử với chứng minh: chứng minh ở mục 2,3,10 mới bảo đảm mọi đầu vào trong hợp đồng.

## 12. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ tính giá trị phân biệt, bỏ tần suất | Thiếu cặp khi trùng | Nhân số lần xuất hiện |
| Nhân a[i]*b[i] thay vì mọi i+j=k | Sai tích chập | Cộng đúng các hệ số |
| Quên offset âm | Sai tổng tương ứng c[k] | minA+minB+k |
| Cộng hai int rồi mới cast long | Tràn tổng | Cast trước khi cộng |
| Dùng f*f trực tiếp cho i<j | Đếm i=j và hai thứ tự | Trừ diagonal, chia 2 |
| Trừ 1 tại 2v khi v trùng nhiều lần | Loại thiếu self-pairs | Trừ f[v] |
| Chia C[s] cho 2 trước khi trừ diagonal | Làm sai cặp tự ghép | (C-D)/2 |
| Nhầm cặp chỉ số và cặp giá trị khác nhau | Sai yêu cầu | Đọc rõ i<j hay x!=y |
| Histogram đặc trên miền rất thưa | Hết RAM | Sparse Map |
| NTT không padding đủ | Tích chập vòng | N>=p+q-1 |
| NTT một prime rồi xem kết quả modulo là exact | Sai khi hệ số >=MOD | Chứng minh bound hoặc CRT |
| Dùng floating FFT và làm tròn không kiểm soát | Sai đếm nguyên lớn | NTT exact/CRT hoặc schoolbook |
| Không kiểm tra tổng hệ số | Dễ bỏ qua lỗi tần suất | Cross=n*m; i<j=n(n-1)/2 |
| Convolution xác suất khi X,Y phụ thuộc | PMF tổng sai | Dùng phân phối chung |
| Chỉ test dãy dương không có duplicates | Bỏ sót lỗi diagonal/offset | Brute random theo chỉ số |

## 13. Bài tập có đáp án

**Bài 1.** A=[0,0], B=[1,1,1], có bao nhiêu cặp tổng 1? *Đáp án:* 6.

**Bài 2.** A=[-1,0,0,2], B=[0,1,1]. Phân bố tổng? *Đáp án:* {-1:1,0:4,1:4,2:1,3:2}.

**Bài 3.** Vì sao c[k]=sum a[i]*b[k-i]? *Đáp án:* mỗi cặp chỉ số có tổng k có đúng một giá trị đầu i và giá trị sau k-i.

**Bài 4.** Mảng tích chập tuyến tính độ dài bao nhiêu? *Đáp án:* p+q-1 khi p,q dương.

**Bài 5.** Cross hai dãy 5 phần tử có tổng số cặp bao nhiêu? *Đáp án:* 25.

**Bài 6.** Với X=[1,1,2,3], f*f tại tổng 4? *Đáp án:* 5 cặp ordered gồm self (2,2).

**Bài 7.** Với X ấy, số cặp i<j tổng 4? *Đáp án:* 2.

**Bài 8.** Vì sao trừ f[v] tại tổng 2v? *Đáp án:* vì có f[v] chỉ số tự ghép (i,i).

**Bài 9.** Công thức i<j? *Đáp án:* U[s]=(C[s]-D[s])/2.

**Bài 10.** Tổng số cặp i<j của n=10? *Đáp án:* 45.

**Bài 11.** Với X=[7] thì i<j có cặp nào? *Đáp án:* không.

**Bài 12.** Với A=[-3], B=[-4], tổng và offset? *Đáp án:* -7 và hệ số c[0]=1.

**Bài 13.** Vì sao tính tổng hai int bằng long? *Đáp án:* để không tràn ở phép cộng.

**Bài 14.** Vì sao phải zero-pad NTT? *Đáp án:* để nhận linear convolution, không phải cyclic.

**Bài 15.** P=998244353 có vai trò gì? *Đáp án:* là prime thân thiện với NTT lũy thừa 2 đến 2^23, primitive root 3.

**Bài 16.** Nếu số cặp tối đa là 1000, một NTT prime có exact không? *Đáp án:* có vì mọi hệ số <=1000<MOD.

**Bài 17.** Hệ số thật MOD+7, đầu ra NTT một prime? *Đáp án:* 7, không phải số nguyên exact.

**Bài 18.** Làm gì nếu bound vượt MOD? *Đáp án:* nhiều prime+CRT có bound, hoặc tích chập nguyên exact.

**Bài 19.** Dữ liệu [-10^9,10^9], histogram đặc có phù hợp? *Đáp án:* không, dùng Map sparse.

**Bài 20.** Nếu chỉ hỏi một tổng, thuật toán thay thế? *Đáp án:* HashMap tần suất và lượt duyệt dãy.

**Bài 21.** X,Y phụ thuộc, có tích chập PMF biên được không? *Đáp án:* không, cần joint PMF.

**Bài 22.** Hai PMF [0.5,0.5] và [0.25,0.75], xác suất tổng 1? *Đáp án:* 0.5.

**Bài 23.** Vì sao C-D chẵn từng hệ số? *Đáp án:* (i,j) và (j,i) là hai thứ tự của cùng tập chỉ số phân biệt.

**Bài 24.** Vì sao brute theo chỉ số làm oracle tốt? *Đáp án:* độc lập với histogram, offset, NTT và sửa đường chéo.

## 14. Checklist trước khi nộp

1. Đề hỏi cặp **chỉ số** hay **giá trị**, có thứ tự hay i<j?
2. Có tính self-pair i=j không, và có phần tử trùng?
3. Histogram đã nhân đúng tần suất các bản sao?
4. Có dịch offset khi giá trị âm, và tổng được tính bằng long?
5. Đã chọn dense histogram hay sparse Map theo span dữ liệu?
6. Kết quả linear convolution có p+q-1 ô và NTT đủ padding?
7. NTT được xem là modulo hay exact? Nếu exact, đã chứng minh bound?
8. Khi i<j có trừ đúng diagonal f[v] tại 2v rồi chia 2?
9. Đã kiểm tra tổng hệ số cross=n*m và i<j=n(n-1)/2?
10. Có test mảng rỗng, một phần tử, âm, trùng và giới hạn int?
11. Có đối chiếu với oracle duyệt chỉ số thay vì một bản NTT khác?
12. Với xác suất, hai biến có độc lập và tổng PMF bằng 1?

## Ghi nhớ

**Cross:** C[s] = tổng theo x của fA[x]*fB[s-x].

**Một dãy i<j:** U[s] = (C[s] - D[s])/2, C=f*f, D[2v]=f[v].

**NTT:** tăng tốc tích chập dày nhưng mặc định tính **modulo P**. Muốn đếm số nguyên chính xác phải chứng minh bound hoặc dùng CRT/phép nhân exact khác.

Chứng minh đúng từ các cặp chỉ số, không nhầm thứ tự, tự ghép hay số lần xuất hiện; sau đó lựa chọn thuật toán thích hợp theo **miền giá trị và số truy vấn**.
