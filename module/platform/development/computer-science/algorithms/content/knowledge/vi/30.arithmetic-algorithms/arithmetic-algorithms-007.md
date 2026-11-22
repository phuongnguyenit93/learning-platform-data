# Sàng Eratosthenes và đánh dấu theo bội

## 1. Bài toán và ý tưởng cốt lõi

Cho số nguyên không âm **n**, cần xác định **mọi số nguyên tố trong đoạn [0, n]**, hoặc xây dựng một bảng để trả lời nhanh câu hỏi: số x (0 ≤ x ≤ n) có phải số nguyên tố không?

**Số nguyên tố** là số nguyên **lớn hơn 1** chỉ có đúng hai ước dương là 1 và chính nó. Ví dụ 2, 3, 5, 7, 11 là nguyên tố. **Hợp số** là số nguyên lớn hơn 1 nhưng có nhiều hơn hai ước dương; chẳng hạn 4=2×2, 6=2×3, 9=3×3. **Số 0 và 1 không phải số nguyên tố và cũng không phải hợp số.**

Sàng Eratosthenes (Sieve of Eratosthenes) không kiểm tra từng số bằng chia thử độc lập. Nó dùng một bảng dấu và lần lượt **đánh dấu những bội của số nguyên tố** để loại các hợp số.

~~~text
Gia su n = 30:

2  3  4  5  6  7  8  9  10 11 12 13 14 15 16
17 18 19 20 21 22 23 24 25 26 27 28 29 30

Sau sang:
2  3  5  7  11 13 17 19 23 29
~~~

Một bảng boolean là đủ:

~~~text
isPrime[x] = true  neu x la nguyen to
isPrime[x] = false neu x khong la nguyen to
~~~

Sàng cho một tiền xử lý khoảng **O(n log log n) thời gian** và **O(n) bộ nhớ**. Sau đó truy vấn `isPrime[x]` trong phạm vi đã sàng tốn O(1) thời gian. Đây là lựa chọn hiệu quả khi phải trả lời nhiều câu hỏi về tính nguyên tố hoặc liệt kê tất cả nguyên tố tới một giới hạn vừa với RAM.

### Những quy ước cần chốt

- **Cận n là bao gồm:** sàng tới n nghĩa là xét cả x=n.
- **Mảng có n+1 phần tử:** chỉ số từ 0 tới n.
- **0 và 1 phải luôn false.**
- **2 là số nguyên tố đầu tiên**, đồng thời là số nguyên tố chẵn duy nhất.
- Nếu n=0 hoặc n=1, danh sách nguyên tố là rỗng.
- Nếu n âm, API trong bài xem là đầu vào không hợp lệ và ném `IllegalArgumentException`.
- Mọi chi phí thời gian/bộ nhớ đều phụ thuộc n; không tự chạy sàng thường tới những n quá lớn so với giới hạn bộ nhớ.

## 2. Cơ chế đánh dấu theo bội

Bắt đầu bằng giả thiết **mọi x≥2 đều là nguyên tố**, rồi loại dần những số có ước nguyên tố nhỏ.

Đầu tiên chọn p=2, số nguyên tố nhỏ nhất. Các bội lớn hơn chính nó là:

~~~text
4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30
~~~

Tất cả đều là hợp số vì chia hết cho 2 và lớn hơn 2. **Không đánh dấu số 2 là hợp số.**

Tiếp theo, số chưa bị đánh dấu nhỏ nhất là p=3. Các bội của 3 từ 9 tới 30:

~~~text
9, 12, 15, 18, 21, 24, 27, 30
~~~

Trong đó 12, 18, 24, 30 đã bị đánh dấu ở lượt p=2. Những số **mới chuyển từ chưa đánh dấu sang hợp số** là:

~~~text
9, 15, 21, 27
~~~

Tiếp theo p=4 đã bị đánh dấu, nên **không xử lý 4 như cơ sở sàng**. Với p=5, đánh dấu các bội từ 25:

~~~text
25, 30
~~~

Chỉ **25** mới được đánh dấu; 30 đã bị loại trước.

Ta đã xử lý hết mọi cơ sở nguyên tố không vượt √30 (gần 5,47), nên kết thúc. Những chỉ số ≥2 còn true chính là:

~~~text
[2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
~~~

### Bảng truy vết với n=30

| Cơ sở p | Bắt đầu tại p² | Các bội thực sự duyệt | Mới đánh dấu | Số mới |
| ---: | ---: | --- | --- | ---: |
| 2 | 4 | 4,6,8,…,30 | 4,6,8,10,12,14,16,18,20,22,24,26,28,30 | 14 |
| 3 | 9 | 9,12,15,18,21,24,27,30 | 9,15,21,27 | 4 |
| 5 | 25 | 25,30 | 25 | 1 |

Tổng cộng có **24 lượt truy cập bội** (14+8+2), nhưng chỉ **19 hợp số khác nhau** được đánh dấu mới (14+4+1). Trong 29 số từ 2 đến 30, có 10 nguyên tố và 19 hợp số, khớp kết quả.

Phân biệt **số lần duyệt bội** với **số phần tử lần đầu bị đánh dấu** là quan trọng khi đọc trace hoặc phân tích thời gian. Một số hợp số bị truy cập nhiều lần vì chúng có nhiều ước nguyên tố.

## 3. Vì sao bắt đầu từ p² thay vì 2p?

Khi xử lý một cơ sở nguyên tố p, có thể đánh dấu mọi bội 2p,3p,4p,…, nhưng như vậy làm lại nhiều việc đã xong.

Xét một bội **k·p** với 2 ≤ k < p:

- Số k có một ước nguyên tố q ≤ k < p.
- Vì vậy k·p cũng chia hết cho q.
- Khi vòng sàng xử lý cơ sở q nhỏ hơn p, k·p đã được đánh dấu.

Do đó **mọi bội p·k với 2≤k<p đã bị loại trước**. Bội nhỏ nhất có thể cần xét mới là **p²**.

Ví dụ:

~~~text
p = 5

2p = 10  da bi danh dau boi 2
3p = 15  da bi danh dau boi 3
4p = 20  da bi danh dau boi 2
5p = 25  bat dau tu day
6p = 30  da bi danh dau boi 2 nhung co the duyet lai
~~~

Bắt đầu tại p² **không có nghĩa mọi bội từ p² đều mới**. Ví dụ 30 đã bị đánh dấu trước, nhưng vòng p=5 vẫn truy cập 30; thao tác `isPrime[30]=false` lần nữa là an toàn.

### Tại sao vẫn tăng mỗi bước p?

Các số cần loại là các **bội** của p. Sau p², các bội kế tiếp là p²+p, p²+2p, …; vì thế bước tăng chính xác bằng p.

~~~text
multiple = p*p
while multiple <= n:
    isPrime[multiple] = false
    multiple += p
~~~

Bắt đầu từ p² rồi tăng 1 sẽ đánh dấu cả số **không chia hết cho p**, gây sai. Bắt đầu p rồi tăng p sẽ đánh dấu chính số nguyên tố p, cũng sai.

## 4. Vì sao chỉ xử lý p ≤ √n?

Mọi hợp số x>1 có thể viết x=a·b với 1<a≤b. Khi đó:

~~~text
a*a <= a*b = x
=> a <= sqrt(x)
~~~

Ít nhất một ước của x không vượt √x. Trong các ước nhỏ ấy tồn tại một **ước nguyên tố q**, nên:

~~~text
q <= sqrt(x) <= sqrt(n)
~~~

Vì vậy mọi hợp số x≤n đều có một ước nguyên tố p≤√n. Khi xử lý p, x là bội của p và đã được đánh dấu trước hoặc sẽ được đánh dấu trong vòng bội của p.

**Không cần xử lý cơ sở p>√n.** Nếu thử bắt đầu từ p² thì p²>n, không còn bội nào trong phạm vi sàng.

### Không cần gọi Math.sqrt trong vòng lặp

Một dạng Java an toàn với n không âm là:

~~~java
for (int p = 2; p <= n / p; p++) {
    if (!isPrime[p]) {
        continue;
    }
    // Mark multiples from p*p.
}
~~~

Điều kiện `p <= n/p` tương đương p²≤n với p>0, nhưng **không phải nhân p*p bằng int**, nên tránh tràn khi kiểm giới hạn.

Ví dụ ranh giới:

- n=24: p=5 không được xử lý vì 25>24.
- n=25: p=5 được xử lý để đánh dấu 25.
- n=49: p=7 được xử lý để đánh dấu 49.
- n=50: p=7 vẫn được xử lý, chỉ cần đánh dấu 49 trong miền tới 50.
- n=2 hoặc n=3: không cơ sở p≥2 nào có p²≤n; cả 2 và 3 đã được giữ true.

Nếu viết `p < sqrt(n)` thay vì `p <= sqrt(n)` và dùng số thực không cẩn thận, có thể bỏ lỡ **bình phương của số nguyên tố** ở ranh giới.

## 5. Giả mã Sàng Eratosthenes chuẩn

~~~text
sieve(n):
    require n >= 0

    isPrime[0..n] = true
    isPrime[0] = false
    if n >= 1:
        isPrime[1] = false

    for p = 2 while p*p <= n:
        if isPrime[p] == false:
            continue

        for multiple = p*p; multiple <= n; multiple += p:
            isPrime[multiple] = false

    return isPrime
~~~

Trong code thực tế, dùng phép so `p <= n/p` và kiểu `long` cho `multiple` để tránh overflow.

### Invariant khi duyệt cơ sở

Trước khi xét p, các số hợp trong phạm vi có **ước nguyên tố nhỏ hơn p** đã bị đánh dấu. Vì không có số nguyên tố nào từng bị đánh dấu nhầm, nếu `isPrime[p]` vẫn true thì p chính là số nguyên tố và thích hợp để làm cơ sở đánh dấu.

Nếu p đã false, tức nó là hợp số và các bội của nó cũng sẽ có ước nguyên tố nhỏ hơn; không cần xử lý p lần nữa.

### Hai cách đặt tên bảng

Một số tài liệu dùng `isComposite[x]`, khởi đầu false và đặt true khi gặp bội, trong khi bài này dùng `isPrime[x]`, khởi đầu true cho x≥2 và đặt false khi gặp bội.

Hai cách đều được, nhưng phải **giữ nhất quán**:

~~~text
isPrime[x]     true = nguyen to
isComposite[x] true = hop so
~~~

Không lấy một mảng composite rồi trả trực tiếp như một mảng prime. Đối với 0,1, cần xử lý riêng ở cả hai quy ước.

## 6. Java 17: cài đặt hoàn chỉnh và có thể chạy

Mã sau chứa:

- `sieve(n)`: tạo `boolean[] isPrime` cho **[0,n]**.
- `primesUpTo(n)`: liệt kê các nguyên tố theo thứ tự tăng.
- `countPrimesUpTo(n)`: đếm số nguyên tố không vượt n.
- `prefixPrimeCounts(...)`: chuẩn bị số lượng nguyên tố trong [0,x] để trả lời truy vấn theo khoảng.
- `sieveWithTrace(30)`: in các bội **lần đầu mới bị đánh dấu** trong từng lượt p.
- `isPrimeTrialDivision(x)`: oracle độc lập để đối chiếu kết quả.
- `verifySmallLimits(200)`: kiểm mọi cặp (n,x) với 0≤n≤200 và 0≤x≤n, tổng **20.301 cặp**.

**Lưu nguyên khối sau thành tệp `EratosthenesMultiplesDemo.java`:**

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class EratosthenesMultiplesDemo {

    // All indices 0..limit are included.
    public static boolean[] sieve(int limit) {
        return sieveInternal(limit, false);
    }

    // Trace marks only values becoming composite for the first time.
    private static boolean[] sieveInternal(
            int limit, boolean trace) {

        if (limit < 0) {
            throw new IllegalArgumentException(
                    "limit must be >= 0");
        }
        // Creating an array of limit+1 would overflow int here.
        if (limit == Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                    "limit too large for an array");
        }

        boolean[] isPrime = new boolean[limit + 1];
        Arrays.fill(isPrime, true);

        isPrime[0] = false;
        if (limit >= 1) {
            isPrime[1] = false;
        }

        // p <= limit/p avoids overflow of p*p in the condition.
        for (int p = 2; p <= limit / p; p++) {
            if (!isPrime[p]) {
                continue;
            }

            List<Integer> newlyMarked =
                    trace ? new ArrayList<>() : null;

            // Use long so multiple += p cannot overflow int.
            for (long multiple = (long) p * p;
                    multiple <= limit; multiple += p) {

                int m = (int) multiple;
                if (trace && isPrime[m]) {
                    newlyMarked.add(m);
                }
                isPrime[m] = false;
            }

            if (trace) {
                System.out.println(
                        "base p=" + p
                        + ", first=" + ((long) p * p)
                        + ", newlyMarked=" + newlyMarked);
            }
        }

        return isPrime;
    }

    public static List<Integer> primesUpTo(int limit) {
        boolean[] flags = sieve(limit);
        List<Integer> result = new ArrayList<>();

        for (int value = 2; value < flags.length; value++) {
            if (flags[value]) {
                result.add(value);
            }
        }

        return List.copyOf(result);
    }

    public static int countPrimesUpTo(int limit) {
        boolean[] flags = sieve(limit);
        int count = 0;
        for (int value = 2; value < flags.length; value++) {
            if (flags[value]) {
                count++;
            }
        }
        return count;
    }

    // prefix[x] = number of primes in [0,x].
    public static int[] prefixPrimeCounts(boolean[] isPrime) {
        int[] prefix = new int[isPrime.length];
        int count = 0;

        for (int x = 0; x < isPrime.length; x++) {
            if (isPrime[x]) {
                count++;
            }
            prefix[x] = count;
        }

        return prefix;
    }

    // Independent O(sqrt(x)) primality oracle.
    private static boolean isPrimeTrialDivision(int x) {
        if (x < 2) {
            return false;
        }
        for (int divisor = 2; divisor <= x / divisor;
                divisor++) {
            if (x % divisor == 0) {
                return false;
            }
        }
        return true;
    }

    // Validate every (limit,x) with limit in 0..200 and x in 0..limit.
    private static int verifySmallLimits(int maxLimit) {
        int checked = 0;

        for (int limit = 0; limit <= maxLimit; limit++) {
            boolean[] flags = sieve(limit);

            for (int x = 0; x <= limit; x++) {
                boolean expected = isPrimeTrialDivision(x);
                if (flags[x] != expected) {
                    throw new AssertionError(
                            "Mismatch limit=" + limit
                            + ", x=" + x);
                }
                checked++;
            }
        }

        return checked;
    }

    public static void main(String[] args) {
        for (int n : new int[] {0, 1, 2, 10, 30}) {
            System.out.println(
                    "primes <= " + n + " = " + primesUpTo(n));
        }

        System.out.println(
                "count <= 100 = " + countPrimesUpTo(100));
        System.out.println(
                "count <= 1000 = " + countPrimesUpTo(1000));

        boolean[] table = sieve(100);
        System.out.println(
                "97 is prime = " + table[97]);
        System.out.println(
                "1 is prime = " + table[1]);

        int[] prefix = prefixPrimeCounts(sieve(30));
        System.out.println(
                "primes in [10,30] = "
                + (prefix[30] - prefix[9]));

        System.out.println("marking <= 30:");
        sieveInternal(30, true);

        System.out.println(
                "oracle (n,x) pairs = " + verifySmallLimits(200));

        try {
            sieve(-1);
        } catch (IllegalArgumentException e) {
            System.out.println("negative limit: "
                    + e.getMessage());
        }
    }
}
~~~

**Lệnh biên dịch và chạy** (JDK 17 trở lên):

~~~bash
javac EratosthenesMultiplesDemo.java
java EratosthenesMultiplesDemo
~~~

**Stdout chính xác của chương trình:**

~~~text
primes <= 0 = []
primes <= 1 = []
primes <= 2 = [2]
primes <= 10 = [2, 3, 5, 7]
primes <= 30 = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
count <= 100 = 25
count <= 1000 = 168
97 is prime = true
1 is prime = false
primes in [10,30] = 6
marking <= 30:
base p=2, first=4, newlyMarked=[4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]
base p=3, first=9, newlyMarked=[9, 15, 21, 27]
base p=5, first=25, newlyMarked=[25]
oracle (n,x) pairs = 20301
negative limit: limit must be >= 0
~~~

### Vì sao chương trình chạy độc lập?

- Tên tệp và tên `public class` đều là `EratosthenesMultiplesDemo`.
- Chỉ sử dụng `Arrays`, `ArrayList` và `List` từ JDK.
- Không cần nhập dữ liệu qua console hoặc tải tệp phụ.
- `isPrime[0]` luôn false; `isPrime[1]` chỉ truy cập khi mảng dài ít nhất 2.
- Không đánh dấu chính cơ sở p; vòng bội bắt đầu từ p².
- `p <= limit / p` tránh overflow trong kiểm tra điều kiện.
- `multiple` là `long` để không tràn khi tính p² hoặc tăng bội.
- `sieveInternal(30,true)` in **chỉ những phần tử mới đánh dấu**, dù vẫn duyệt lại các hợp số như 12,18,24,30.
- `verifySmallLimits(200)` dùng chia thử độc lập, nên có thể phát hiện lỗi sai trong logic sàng.

### Giới hạn lưu trữ

`limit + 1` vẫn phải là độ dài mảng hợp lệ và bộ nhớ thực tế phải đủ. Mã chủ động từ chối `Integer.MAX_VALUE` vì phép cộng 1 vượt giới hạn int. Tuy nhiên n rất lớn nhưng nhỏ hơn giá trị đó vẫn có thể làm JVM ném `OutOfMemoryError`; guard chống tràn **không phải cam kết RAM luôn đủ**.

Đầu ra `List<Integer>` còn tốn bộ nhớ cho tất cả các số nguyên tố được liệt kê. Nếu chỉ cần **đếm**, dùng `countPrimesUpTo`; nếu cần nhiều truy vấn tính nguyên tố, giữ lại `boolean[]` đã sàng thay vì chạy lại mỗi lần.

## 7. Chứng minh tính đúng

Để chứng minh sàng, cần chỉ ra hai điều: **không số nguyên tố nào bị loại nhầm** và **mọi hợp số trong [2,n] đều bị loại**.

### Mệnh đề 1: các số bị đánh dấu đều là hợp số

Một lần đánh dấu xảy ra với `multiple = p*p + t*p = p*(p+t)` trong đó p≥2 và t≥0. Hai thừa số đều ≥2, nên multiple là hợp số. Do đó thuật toán không bao giờ đánh dấu một số nguyên tố.

Điều này đúng ngay cả nếu một hợp số bị đánh dấu lặp lại. Đặt false thêm lần nữa không ảnh hưởng tính đúng.

### Mệnh đề 2: mọi hợp số đều bị đánh dấu

Cho x≤n là hợp số. Gọi p là **ước nguyên tố nhỏ nhất** của x. Khi đó p≤√x≤√n: nếu p>√x thì x/p<√x, trái với việc p là ước nguyên tố nhỏ nhất vì x/p>1 sẽ có một ước nguyên tố nhỏ hơn p.

Vì x chia hết cho p, viết x=p·k. Do p là ước nguyên tố nhỏ nhất, ta phải có k≥p; nếu k<p thì k>1 có ước nguyên tố nhỏ hơn p. Vậy x≥p².

Khi vòng ngoài tới cơ sở p, cờ `isPrime[p]` vẫn true theo mệnh đề 1. Vòng bội bắt đầu ở p² và bước p, nên sẽ đi qua x và đánh dấu false.

**Suy ra:** sau khi các p≤√n đã được xử lý, đúng những số nguyên tố từ 2 đến n vẫn true.

### Mệnh đề 3: điều kiện dừng là đủ

Mọi hợp số có ước nguyên tố p≤√n, như vừa chứng minh. Vì vậy không cần duyệt cơ sở p>√n. Dừng ở `p<=n/p` không bỏ sót hợp số nào.

### Hệ quả cho 0 và 1

Chứng minh trên áp dụng cho số ≥2. Số 0 và 1 được gán false trực tiếp trước vòng ngoài, theo đúng định nghĩa số nguyên tố.

## 8. Phân tích độ phức tạp

### Chi phí khởi tạo

Tạo mảng `boolean[n+1]` và `Arrays.fill(...,true)` tốn **O(n)** thời gian và **O(n)** bộ nhớ cho các cờ. Đặt 0,1 false là O(1).

### Chi phí đánh dấu

Chỉ các p nguyên tố không vượt √n mới có vòng bội. Với mỗi p, số lượt duyệt bội không vượt khoảng n/p. Tổng lượt được chặn bởi:

~~~text
sum over primes p <= sqrt(n) of O(n/p)

= O(n * sum over primes p<=sqrt(n) of 1/p)
~~~

Từ kết quả cổ điển về tổng nghịch đảo các số nguyên tố, tổng trên tăng cỡ **log log n**, nên tổng thời gian sàng là **O(n log log n)**.

Nếu chưa dùng kết quả số học đó, có thể lấy cận sơ cấp yếu hơn bằng cách cộng trên **mọi số nguyên** p≥2 thay vì chỉ nguyên tố:

~~~text
O(n * sum_{p=2}^{sqrt(n)} 1/p)
= O(n log n)
~~~

Cận O(n log n) đúng nhưng không sắc bằng O(n log log n). Không được nhầm sàng Eratosthenes chuẩn với O(n²) chỉ vì có hai vòng lặp lồng nhau.

### Chi phí xuất kết quả

- Trả về bảng boolean: O(n) bộ nhớ và O(n log log n) thời gian tiền xử lý.
- Lấy tất cả nguyên tố: quét bảng O(n), lưu π(n) số nguyên tố, tốn O(π(n)) bộ nhớ đầu ra.
- Tính số nguyên tố: quét bảng thêm O(n), dùng O(1) biến ngoài bảng.
- Xây prefixCount: O(n) thời gian và O(n) bộ nhớ thêm; mỗi truy vấn đếm trên đoạn sau đó O(1).
- Truy vấn `isPrime[x]`: O(1) nếu 0≤x≤n và bảng đã có.

Nếu sàng lại từ đầu cho **mỗi truy vấn**, chi phí thực tế bị nhân với số lần hỏi. Với nhiều truy vấn, nên xây bảng **một lần** rồi tái sử dụng.

### Số bội đã duyệt không bằng số hợp số

Với n=30, có 19 hợp số nhưng tổng lượt duyệt bội là 24. Sự chênh lệch là những bội có nhiều ước nguyên tố, chẳng hạn 30 bị duyệt ở cả p=2,3,5. Đây là lý do phân tích thời gian phải tính **mỗi lần truy cập** chứ không chỉ đếm số vị trí bị chuyển false lần đầu.

## 9. Tối ưu bộ nhớ bằng cách chỉ lưu số lẻ

Ngoại trừ 2, mọi số nguyên tố đều **lẻ**. Vì thế có thể cắt gần một nửa số cờ nếu chỉ lưu các số lẻ ≥3.

Một cách ánh xạ:

~~~text
index = (oddValue - 3) / 2
oddValue = 2*index + 3

index 0 -> 3
index 1 -> 5
index 2 -> 7
index 3 -> 9
index 4 -> 11
...
~~~

Dùng `isCompositeOdd[index] = true` nghĩa là số lẻ tương ứng đã bị đánh dấu là hợp số.

Vòng sàng odd-only:

~~~text
for odd prime p = 3 while p*p <= n:
    if p is already marked composite:
        continue

    for multiple = p*p; multiple <= n; multiple += 2*p:
        mark multiple as composite
~~~

**Bước tăng là 2p**, không phải p, vì từ p² (lẻ) thì p²+p là số chẵn đã biết hợp số; chỉ cần đánh dấu những **bội lẻ** tiếp theo.

### Ví dụ p=3

~~~text
3*3 = 9
3*5 = 15
3*7 = 21
3*9 = 27

Buoc tang 2*p = 6
~~~

Các bội chẵn như 12,18,24,30 không cần lưu. Số 2 được xử lý riêng: là nguyên tố nếu n≥2.

### Ưu điểm và đánh đổi

Odd-only vẫn chạy khoảng O(n log log n), nhưng dùng gần **n/2 cờ** và giảm một phần thao tác. Đổi lại:

- Phải ánh xạ giữa số nguyên và chỉ số mảng.
- Phải xử lý số 2 riêng.
- Cần chú ý n=0,1,2 và các cận chẵn/lẻ.
- Vẫn cần bộ nhớ tỷ lệ với n; không phù hợp khi n quá lớn.
- Cần dùng `long` cho p² và bội nếu giá trị có nguy cơ tràn int.

Hãy ưu tiên bản toàn bộ số để học và kiểm chứng trước, rồi tối ưu odd-only khi profiling cho thấy cần thiết.

## 10. BitSet: n bit khác với n boolean

Một `boolean[]` Java có một phần tử cho mỗi số từ 0 tới n. Trên JVM thường mỗi phần tử boolean dùng cỡ một byte, nhưng đặc tả Java không buộc kích thước vật lý chính xác. Ngoài ra còn có overhead đối tượng mảng.

Nếu bộ nhớ quan trọng, Java `BitSet` lưu các cờ theo bit, giúp giảm đáng kể footprint so với một mảng boolean thông thường:

~~~java
import java.util.BitSet;

BitSet composite = new BitSet(n + 1);
// composite.get(x) = true means x has been marked composite.
~~~

Tuy nhiên chọn BitSet chỉ thay **cấu trúc lưu cờ**, không thay toán học của sàng:

- Vẫn cần xử lý 0,1.
- Vẫn chỉ dùng cơ sở nguyên tố tới √n.
- Vẫn đánh dấu từ p², bước p (hoặc 2p với odd-only).
- Nếu dùng `BitSet`, nên ghi rõ true là **composite** hay **prime** để tránh đảo nghĩa.

`BitSet` có overhead phương thức và thao tác bit; benchmark thực tế phụ thuộc JVM, n và pattern truy cập. Đừng mặc định nó nhanh hơn mọi trường hợp chỉ vì dùng ít RAM.

## 11. Sàng phân đoạn khi [0,n] quá lớn

Sàng Eratosthenes cơ bản cần mảng độ dài n+1. Nếu chỉ muốn nguyên tố trong một khoảng **[L,R]** với R rất lớn nhưng chiều rộng R−L+1 vừa phải, có thể dùng **segmented sieve (sàng phân đoạn)**:

1. Sàng các nguyên tố cơ sở p≤√R bằng sàng thường.
2. Cấp phát bảng cho **chỉ đoạn [L,R]**.
3. Với mỗi p, đánh dấu các bội p thuộc đoạn.
4. Loại riêng mọi giá trị nhỏ hơn 2.
5. Những vị trí còn lại là nguyên tố trong đoạn.

Đối với một p, bội đầu tiên cần đánh dấu trong đoạn là:

~~~text
first = max(p*p, ceil(L/p)*p)
~~~

**Lý do phải lấy max với p²:** nếu L nhỏ hơn p², bội đầu tiên trong đoạn có thể chính là p, và đánh dấu nó sẽ xóa nhầm số nguyên tố p.

**Lý do cần ceil(L/p):** chỉ duyệt các bội thực sự nằm trong [L,R], không bắt đầu ở 0 hay p² nếu đoạn nằm rất xa.

Ví dụ [100,120], cơ sở p=2:

~~~text
first = max(4, 100) = 100
mark 100, 102, 104, ..., 120
~~~

Với p=3:

~~~text
first = max(9, 102) = 102
mark 102, 105, 108, 111, 114, 117, 120
~~~

Giá trị `ceil(L/p)*p` phải được tính bằng số nguyên đủ rộng và kiểm overflow, nhất là nếu L hoặc R gần giới hạn `long`. Với L≥0, có thể dùng phép chia thương và phần dư rồi tăng thương khi dư khác 0; vẫn phải bảo vệ phép nhân trở lại nếu vượt miền dữ liệu.

### Độ phức tạp

Đặt B=R−L+1 là độ rộng đoạn. Một phân tích thông dụng: sàng cơ sở tới √R cần khoảng O(√R log log R) thời gian và O(√R) bộ nhớ, đánh dấu đoạn cần khoảng O(B log log R) thao tác trên các cơ sở; bộ nhớ đoạn O(B). Với nhiều đoạn liên tiếp, các nguyên tố cơ sở có thể được tái sử dụng.

Sàng phân đoạn là phần **mở rộng của nguyên lý đánh dấu theo bội**, không phải cứ gọi hàm sàng thường tới R rồi cắt mảng. Nếu R cực lớn, còn cần xử lý chính xác phép tính √R và tránh tràn số ở các mốc bội.

## 12. Sàng nguyên tố khác sàng ước nguyên tố nhỏ nhất (SPF)

Bảng `isPrime[]` trả lời: **x có phải nguyên tố?** Nó không trực tiếp cho các thừa số nguyên tố của x.

Nếu bài cần phân tích thừa số nguyên tố cho nhiều số, có thể tiền xử lý mảng:

~~~text
spf[x] = smallest prime factor of x
~~~

Ví dụ:

~~~text
spf[12] = 2
spf[15] = 3
spf[49] = 7
~~~

Có thể xây SPF bằng ý tưởng sàng và sử dụng để phân tích một số x bằng cách lặp:

~~~text
while x > 1:
    p = spf[x]
    output p
    x = x / p
~~~

SPF và sàng Eratosthenes có liên hệ nhưng **không đồng nhất** về dữ liệu lưu trữ. `boolean[] isPrime` chỉ có một bit/cờ cho tính nguyên tố, trong khi SPF lưu một giá trị thừa số. Nếu chỉ hỏi nguyên tố, sàng boolean đơn giản và thường tiết kiệm hơn.

Cũng có **linear sieve** thiết kế để mỗi hợp số được gán thừa số nhỏ nhất theo cơ chế khác và đạt O(n) thời gian, với lưu trữ O(n). Đó là thuật toán riêng, không nên gọi vòng đánh dấu theo bội của Eratosthenes là “linear sieve” chỉ vì có hai vòng lặp.

## 13. Chọn công cụ cho từng dạng bài toán

| Nhu cầu | Cách làm phù hợp | Ghi chú |
| --- | --- | --- |
| Liệt kê mọi nguyên tố ≤n, n vừa RAM | Sàng Eratosthenes | O(n log log n), O(n) bộ nhớ |
| Hàng trăm nghìn truy vấn x≤n có phải prime | Tiền xử lý `isPrime[]` một lần | O(1) mỗi truy vấn |
| Hàng nghìn truy vấn đếm prime trong [L,R] với R≤n | Sàng rồi prefix counts | O(1) mỗi truy vấn sau O(n) tiền xử lý |
| Chỉ kiểm một x nhỏ/vừa | Chia thử tới √x | Không cần cấp mảng lớn |
| Tìm prime trong [L,R], R rất lớn, đoạn ngắn | Segmented sieve | Dùng prime cơ sở tới √R |
| Phân tích thừa số nhiều số ≤n | SPF sieve | Lưu thêm thừa số nhỏ nhất |
| n vừa nhưng memory hạn chế | Odd-only hoặc BitSet | Giảm bộ nhớ cờ |
| Kiểm một số nguyên 64-bit rất lớn | Thuật toán kiểm nguyên tố thích hợp như Miller–Rabin | Không lập mảng tới x |

Mỗi phương pháp có phạm vi. Sàng không thay thế trực tiếp mọi phép kiểm nguyên tố 64-bit; chia thử một lần cũng không hiệu quả khi phải liệt kê hàng triệu số nguyên tố liên tiếp.

## 14. Lỗi thường gặp khi đánh dấu bội

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đặt `isPrime[1]=true` | 1 bị nhận nhầm là nguyên tố | Gán 0,1 false |
| Không xử lý n=0 | Truy cập index 1 vượt mảng | Kiểm n>=1 trước khi gán 1 |
| Khởi đầu vòng bội từ p | Đánh dấu chính p là hợp số | Bắt đầu p² |
| Bắt đầu 2p không tối ưu nhưng nói là sai | Nhầm tính đúng với hiệu năng | 2p vẫn đúng nếu bỏ p; p² tốt hơn |
| Tăng bội bằng 1 | Đánh dấu cả số không chia hết p | Bước tăng p |
| Không bỏ qua p composite | Duyệt bội dư thừa | Chỉ xử lý nếu isPrime[p] true |
| Dừng p<√n | Có thể bỏ p=√n khi n là chính phương | Dùng p≤n/p |
| Duyệt p lên tới n | Làm thừa nhiều vòng cơ sở | Chỉ p≤√n |
| Sàng n nhưng cấp mảng dài n | Truy cập isPrime[n] vượt mảng | Cấp n+1 |
| Dùng `p*p` bằng int khi n lớn | Tràn và truy cập sai | Dùng long |
| Dùng `multiple += p` bằng int gần giới hạn | Overflow/vòng lặp sai | Biến multiple kiểu long |
| Đếm lượt duyệt như số hợp số mới | Thống kê sai | Phân biệt visited/mới marked |
| Dùng cờ composite nhưng trả như prime | Kết quả đảo ngược | Đặt tên và quy ước rõ |
| Tạo sàng lại cho mọi query | Tốn thời gian lớn | Tái sử dụng bảng |
| Lập bảng n cực lớn bất chấp RAM | OutOfMemoryError | Segmented/BitSet/odd-only |
| Không ràng buộc x trong [0,n] | ArrayIndexOutOfBounds | Kiểm miền truy vấn |
| Trộn inclusive/exclusive bounds | Thiếu prime bằng n | Ghi rõ [0,n] |
| Dùng bước p trong odd-only | Đụng các bội chẵn không lưu | Dùng bước 2p |
| Bỏ xử lý prime2 trong odd-only | Thiếu nguyên tố chẵn duy nhất | Xuất 2 riêng |
| Segmented sieve chỉ dùng ceil(L/p)*p | Có thể đánh dấu nhầm p | max(p²,first multiple) |
| Không loại 0,1 trong segment | Báo 0 hoặc 1 nguyên tố | Xử lý riêng |
| Dùng `Math.sqrt` rồi ép int cho mọi long | Có thể sai ranh giới lớn | Kiểm/correct integer sqrt |
| Dùng boolean[] rồi nói mỗi phần tử đúng 1 bit | Dự toán RAM sai | Phân biệt array/BitSet |
| Gọi Eratosthenes là linear sieve | Đánh giá sai complexity | O(n log log n) cho bản chuẩn |

## 15. Kiểm thử tính đúng bằng dữ liệu nhỏ

Một thuật toán sàng dễ viết ngắn nhưng có nhiều lỗi off-by-one. Vì vậy nên dùng **oracle chia thử độc lập** trên các n nhỏ.

### Oracle chia thử

Số x≥2 là nguyên tố nếu không có ước nào d từ 2 tới √x:

~~~text
isPrimeSlow(x):
    if x < 2:
        return false
    for d=2 while d*d <= x:
        if x mod d == 0:
            return false
    return true
~~~

Trong Java nên dùng `d<=x/d` để tránh overflow trong d*d. Oracle O(√x) không phải lựa chọn nhanh cho hàng triệu truy vấn, nhưng đáng tin cậy trên miền nhỏ để kiểm sàng.

### Kiểm mọi cặp (n,x)

Trong chương trình mẫu:

~~~text
for n=0..200:
    flags=sieve(n)
    for x=0..n:
        assert flags[x] == isPrimeTrialDivision(x)
~~~

Tổng số cặp là:

~~~text
1+2+...+201
= 201*202/2
= 20301
~~~

Việc kiểm nhiều n khác nhau phát hiện lỗi phụ thuộc vào **giới hạn sàng**, ví dụ bỏ qua p ở n=p², chứ không chỉ kiểm một bảng n=200.

### Các số mốc đã biết

| n | Các nguyên tố hoặc số lượng |
| ---: | --- |
| 0 | [] |
| 1 | [] |
| 2 | [2] |
| 3 | [2,3] |
| 4 | [2,3] |
| 10 | [2,3,5,7] |
| 25 | 9 số nguyên tố |
| 30 | 10 số nguyên tố |
| 49 | 15 số nguyên tố |
| 100 | 25 số nguyên tố |
| 1.000 | 168 số nguyên tố |
| 10.000 | 1.229 số nguyên tố |

Đặc biệt n=25 và n=49 giúp bắt lỗi bỏ qua **bình phương số nguyên tố** ở cuối phạm vi. 25=5² và 49=7² phải bị đánh dấu composite. Số lượng prime≤25 là 9; số lượng prime≤49 là 15.

### Property-based tests

1. `flags.length == n+1`.
2. `flags[0] == false`, và nếu n≥1 thì `flags[1]==false`.
3. Với mọi x≥2 còn true, không có ước d từ 2 tới √x.
4. Với mọi x composite, tồn tại p prime với p|x và p≤√x.
5. `countPrimesUpTo(n)` bằng số true trong [2,n].
6. Các prime xuất ra tăng dần và không trùng.
7. Với n lớn hơn m, tiền tố `sieve(n)[0..m]` bằng `sieve(m)` nếu cùng quy ước.
8. Số lượng prime không giảm khi tăng n; chỉ tăng 1 khi n mới là prime.
9. Trong trace n=30, số newlyMarked 14+4+1=19 và số visits 14+8+2=24.
10. Không có prime nào bị đánh dấu.
11. Với p composite, không cần mở rộng vòng bội riêng.
12. Không có truy cập ngoài đoạn [0,n], kể cả n=0,1.
13. Nếu bổ sung prefix counts, `prefix[R]−prefix[L−1]` khớp đếm thủ công trên [L,R].
14. Khi dùng segmented sieve, kết quả đoạn phải bằng slice của sieve thường trên các R vừa RAM.

### Kiểm thử ngẫu nhiên

Sinh n ngẫu nhiên trong [0,5000], so bảng với chia thử; ưu tiên giá trị gần bình phương nguyên tố, các số hoàn toàn chẵn, số có nhiều ước và số nguyên tố gần n. Với cận lớn, kiểm tính chất và vài kết quả đã biết; benchmark thời gian **không** thay thế chứng minh đúng.

## 16. Những tình huống biên và an toàn kiểu dữ liệu

### n âm, n=0, n=1

Bài định nghĩa `sieve(n)` với n không âm. Với âm, ném `IllegalArgumentException`. Với 0, mảng dài 1, chỉ `isPrime[0]=false`. Với 1, mảng dài 2, cả 0 và 1 false. Không truy cập phần tử 1 nếu n=0.

### n đúng bằng bình phương nguyên tố

Các số 4,9,25,49,121,... phải được đánh dấu khi p tương ứng được xét. Điều kiện p≤n/p là quan trọng. Nếu vòng ngoài viết p<n/p hoặc p<sqrt(n), có thể dừng quá sớm ở những ranh giới này.

### Nhiều bội trùng

Một hợp số như 30 có các ước nguyên tố 2,3,5; việc gán false nhiều lần an toàn. Nếu cần **đếm số hợp số**, đếm số phần tử false ở [2,n], không cộng mọi vòng bội trực tiếp.

### Tràn số khi tính p² hoặc tăng bội

`int` trong Java có giới hạn. Với n rất lớn, biểu thức int `p*p` hoặc `multiple+=p` có nguy cơ tràn, tạo chỉ số âm hoặc vòng lặp vô hạn. Dùng:

~~~java
for (int p = 2; p <= n / p; p++) {
    if (isPrime[p]) {
        for (long multiple = (long) p * p;
                multiple <= n; multiple += p) {
            isPrime[(int) multiple] = false;
        }
    }
}
~~~

Vẫn phải cấp phát được mảng và kiểm `limit+1` không overflow int. Với dữ liệu tới 64-bit, bản sàng thường không thực tế; chọn segmented sieve hoặc kiểm nguyên tố phù hợp.

### OutOfMemoryError

Giới hạn mảng hợp lệ không đồng nghĩa máy còn đủ RAM. Một bảng hàng trăm triệu phần tử có thể chiếm rất nhiều bộ nhớ; danh sách nguyên tố, prefix counts và JVM overhead còn cộng thêm. Tối ưu bằng BitSet, odd-only, segmented sieve hoặc thay bài toán nếu cần.

## 17. Mở rộng: truy vấn khoảng và prefix counts

Sau khi có `isPrime[0..n]`, có thể dựng:

~~~text
prefix[x] = so luong so nguyen to trong [0,x]
prefix[x] = prefix[x-1] + (isPrime[x] ? 1 : 0)
~~~

Với khoảng [L,R] (0≤L≤R≤n):

~~~text
primeCount(L,R) =
    prefix[R]                     neu L=0
    prefix[R] - prefix[L-1]       neu L>0
~~~

Ví dụ [10,30] chứa 11,13,17,19,23,29, nên đếm được **6**. Chương trình Java in đúng kết quả này từ prefix của sàng n=30.

### Đếm nhiều truy vấn

Nếu có Q truy vấn đếm khoảng cùng miền [0,n]:

- Tiền xử lý sàng: O(n log log n).
- Dựng prefix: O(n).
- Mỗi truy vấn: O(1), tổng O(Q).
- Bộ nhớ: O(n) cho bảng cộng O(n) cho prefix.

Nếu chỉ có vài truy vấn, prefix có thể không cần; quét các vị trí cũng đúng nhưng mỗi truy vấn tốn độ dài đoạn. Nếu truy vấn là các khoảng có R rất lớn, cân nhắc segmented sieve hoặc cấu trúc/bài toán chuyên sâu hơn.

## 18. Bài tập thực hành

1. Định nghĩa số nguyên tố, hợp số và giải thích vì sao 0,1 không phải prime.
2. Liệt kê tất cả các số nguyên tố ≤30 bằng tay.
3. Dùng bảng n=30, ghi mọi bội được duyệt khi p=2,3,5.
4. Phân biệt số lượt bội được duyệt (24) và số hợp số mới đánh dấu (19).
5. Chứng minh các bội 2p,3p,...,(p−1)p đã bị đánh dấu trước lượt p.
6. Giải thích vì sao mọi hợp số ≤n có ước nguyên tố ≤√n.
7. Viết giả mã sàng với `isPrime[]` và ngữ nghĩa true/false rõ ràng.
8. Đổi sang mảng `isComposite[]`; kiểm xử lý 0,1.
9. Cài sàng n=0,1,2,3 và không truy cập sai chỉ số.
10. Dùng n=25 và n=49 để kiểm điều kiện dừng.
11. So O(n²) của kiểm mọi rotation/đoạn không liên quan với O(n log log n) của sàng; giải thích vì sao hai vòng lặp không tự suy ra O(n²).
12. Cài chương trình in 25 prime đầu tiên, dùng sàng với một giới hạn đủ lớn đã biết hoặc tăng giới hạn có kiểm soát.
13. Dựng prefix counts và trả số prime trong [10,30].
14. Với Q=10000 truy vấn isPrime[x], đo khác biệt giữa tái sử dụng một bảng và sàng lại mỗi lần.
15. Viết oracle chia thử O(√x), kiểm mọi x≤1000.
16. Sinh 100 giới hạn n ngẫu nhiên và so sàng với oracle.
17. Cài odd-only sieve, ánh xạ index t tới giá trị 2t+3.
18. Giải thích vì sao odd-only tăng bội 2p chứ không phải p.
19. Dùng `BitSet` để lưu composite flags; so memory với boolean[].
20. Sàng phân đoạn [100,120], liệt kê các nguyên tố trong đoạn.
21. Tính first=max(p²,ceil(L/p)p) và giải thích vì sao cần max.
22. Cài SPF cho mọi x≤n và so với boolean isPrime về thông tin lưu.
23. Xử lý `n=Integer.MAX_VALUE` mà không tràn khi cấp mảng; giải thích vì sao vẫn không nên sàng thường tới n ấy.
24. Chứng minh không một số nguyên tố nào bị đánh dấu bởi một bước `multiple=p*(p+t)` với p≥2,t≥0.
25. Viết kiểm thử `sieve(n)` giữ đúng tiền tố khi tăng n.
26. Đếm các số nguyên tố ≤100,≤1000,≤10000 và đối chiếu 25,168,1229.
27. Thiết kế tối ưu không lưu danh sách prime nếu chỉ cần count.
28. Phân tích bộ nhớ khi vừa lưu boolean flags, prefix int[] và danh sách List<Integer>.
29. So sánh khi nào một phép chia thử có lợi hơn cả quá trình sàng.
30. Giải thích vì sao không được gọi sàng Eratosthenes chuẩn là linear sieve.

## 19. Checklist áp dụng

- Bài yêu cầu prime≤n hay prime<n? Có rõ cận bao gồm không?
- Đã gán 0 và 1 **không nguyên tố** chưa?
- Mảng có đủ n+1 phần tử chưa?
- Vòng cơ sở chỉ chạy khi p²≤n và chỉ với p chưa bị đánh dấu chưa?
- Vòng bội bắt đầu tại p², tăng đúng p chưa?
- Đã dùng `long` để tránh tràn khi tính bội và `n/p` để kiểm ranh giới chưa?
- Đã kiểm n=0,1,2, n là bình phương prime và n rất lớn chưa?
- Có phân biệt số lần bội được truy cập với số hợp số mới đánh dấu không?
- Khi có nhiều truy vấn, bảng sàng có được tái sử dụng không?
- Nếu cần đếm khoảng, prefix counts được xây đúng và kiểm giới hạn không?
- Có tính đủ bộ nhớ của flags, prefix và danh sách output không?
- Nếu n quá lớn, đã cân nhắc odd-only, BitSet hoặc segmented sieve chưa?
- Nếu bài chỉ hỏi một số 64-bit lớn, có cân nhắc phép kiểm nguyên tố chuyên biệt thay vì cấp mảng tới số đó không?
- Có đối chiếu bằng phép chia thử độc lập trên các miền nhỏ và các mốc đã biết không?

## 20. Tổng kết

Sàng Eratosthenes dựa trên một ý tưởng đơn giản nhưng rất mạnh: **đánh dấu những bội của mỗi số nguyên tố cơ sở** để loại toàn bộ hợp số. Khi tới p, các bội nhỏ hơn p² đã có ước nguyên tố nhỏ hơn p và đã bị xử lý; vì vậy vòng đánh dấu **bắt đầu ở p²**. Mọi hợp số ≤n có ước nguyên tố không vượt √n, nên chỉ cần xử lý **các p≤√n**.

Kết quả là bảng tính nguyên tố cho [0,n] với **O(n log log n) thời gian, O(n) bộ nhớ**, giúp truy vấn O(1) sau tiền xử lý. Ví dụ n=30 dùng cơ sở p=2,3,5, duyệt tổng 24 bội, lần đầu loại 19 hợp số và còn 10 nguyên tố. Trong Java cần đặc biệt chú ý **0,1**, cận **bao gồm n**, `p<=n/p`, bội dùng `long`, và kiểm thử bằng oracle chia thử. Khi quy mô dữ liệu lớn, các biến thể **odd-only, BitSet và segmented sieve** tiếp tục sử dụng nguyên lý đánh dấu theo bội trong khi đánh đổi tốc độ, bộ nhớ và độ phức tạp cài đặt.
