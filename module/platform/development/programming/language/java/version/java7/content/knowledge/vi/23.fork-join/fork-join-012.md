# So sánh thuật toán song song với kết quả tuần tự — Fork/Join trong Java

## 1. Hai câu hỏi hoàn toàn khác nhau

Khi chuyển một thuật toán từ vòng lặp tuần tự sang **Fork/Join**, không nên chỉ chạy chương trình và thấy nó kết thúc rồi kết luận “song song đúng” hoặc “song song nhanh”. Phải trả lời **hai câu hỏi tách biệt**:

1. **Tính đúng (correctness):** Với **cùng đầu vào** và **cùng quy ước kết quả**, thuật toán song song có cho đầu ra **tương đương** thuật toán tuần tự không? Có bỏ sót, lặp phần tử, ghi đè dữ liệu, tràn số, thay thứ tự xử lý hay không?
2. **Hiệu năng (performance):** Sau khi đã xác nhận tính đúng, phiên bản song song có nhanh hơn bản tuần tự **trong điều kiện đo công bằng** không? Kích thước dữ liệu, threshold, số worker, cách khởi tạo input, JIT/GC, phần cứng và chi phí fork/join ảnh hưởng thế nào?

Một sự thật quan trọng: **song song không tự động nhanh hơn**, và **đúng kết quả không đồng nghĩa không có race condition** nếu bài test chưa đủ bao phủ. Hơn nữa, với phép toán dấu phẩy động, một phép reduce song song hợp lệ có thể **không bằng từng bit** với thứ tự cộng tuần tự do quy tắc làm tròn.

~~~text
Cùng dữ liệu gốc, cố định / có seed
             |
     +-------+-------+
     |               |
     v               v
Sequential oracle    Fork/Join implementation
     |               |
     +------+- ------+
            |
     So sánh kết quả
            |
       Sai? -> dừng, chẩn đoán index/range/overflow/race
            |
          Đúng
            |
     Warm-up / JMH benchmark / đo nhiều lần
            |
     Báo cả median, độ biến thiên, speedup, context
~~~

**Phạm vi:** `ForkJoinPool`, `RecursiveTask<V>`, `RecursiveAction`, `fork()`, `join()` là API từ Java 7 và vẫn được hỗ trợ. Các chương trình dưới đây là **Java 17+**, đã được biên dịch bằng `javac -encoding UTF-8 --release 17` và kiểm tra stdout trên JDK 17. Tài liệu chính thức được đối chiếu với Java SE 26 và OpenJDK JMH. Bài tránh hướng dẫn dựa trên API legacy hoặc kết luận hiệu năng không kiểm chứng.

### Mục tiêu học

- Xây một **sequential reference** đơn giản, độc lập để làm oracle.
- Giữ cùng dữ liệu đầu vào, cùng miền giá trị, cùng định nghĩa kết quả và cùng yêu cầu side effect.
- Kiểm tra đoạn rỗng, một phần tử, dữ liệu âm, duplicate, kích thước lẻ, threshold và overflow.
- Dùng seeded/property-style tests để thử nhiều đầu vào tái lập được.
- Dùng `Arrays.equals`, `Arrays.mismatch` và so sánh cấu trúc kết quả.
- Thử những thuật toán khác nhau: sum, histogram, max, sort, biến đổi mảng, đếm số nguyên tố, streams.
- Hiểu **không giao nhau các range** và tính thuần của subtask.
- Phân biệt integer equivalence và floating-point numerical equivalence.
- Hiểu threshold/parallelism ảnh hưởng overhead nhưng không được đổi kết quả toán học.
- Dùng `System.nanoTime()` cho thử nghiệm nhỏ và **JMH** cho microbenchmark đáng tin cậy.
- Diễn giải speedup, giới hạn bởi phần tuần tự và chi phí chia việc.

## 2. Thế nào mới là “cùng kết quả”?

Tùy bài toán, “bằng nhau” có các nghĩa khác nhau:

| Đầu ra | Quy tắc so sánh phù hợp |
| --- | --- |
| `long` tính tổng nguyên không overflow | `sequential == parallel` |
| `int[]` đã sắp xếp | `Arrays.equals(seq,par)`, có thể dùng `Arrays.mismatch` |
| `long[256]` histogram | So sánh **từng bin**, tổng các bin và các biên |
| `OptionalInt` maximum | Hai kết quả cùng present/empty, và cùng giá trị nếu present |
| `double` reduce | Phân tích thứ tự cộng, NaN/Infinity/signed zero, chọn hợp đồng dung sai nếu thích hợp |
| Biến đổi mảng tại chỗ | So sánh hai **bản sao độc lập** của cùng dữ liệu gốc |
| Kết quả chứa danh sách | Xác định có yêu cầu thứ tự không; nếu là tập thì so sánh theo semantics tập |
| Thuật toán có side effects | So sánh cả trạng thái cuối, số lần tác động, không chỉ giá trị return |

Khi bài toán yêu cầu **thứ tự** (ví dụ kết quả sắp xếp tăng dần), không được lấy `new HashSet<>(list)` để che mất lỗi duplicate và thứ tự. Ngược lại, với kết quả mang nghĩa tập hợp, yêu cầu “phải cùng thứ tự hoàn thành tasks” là sai vì worker scheduling không được bảo đảm.

### 2.1. Reference oracle phải độc lập và dễ kiểm tra

Tránh viết “thuật toán tuần tự” bằng cách gọi cùng cây Fork/Join nhưng với parallelism bằng một, rồi dùng nó kiểm thử chính cây đó. Hai bản có thể cùng mắc một bug ở split hoặc combine.

Một oracle tốt cho sum:

~~~java
static long sequentialSum(int[] a) {
    long sum = 0;
    for (int value : a) {
        sum += value;
    }
    return sum;
}
~~~

Đây là method minh họa trong một class, không phải chương trình độc lập. Nó duyệt mỗi phần tử **một lần** và không có recursion. Sau đó so với Fork/Join decomposition bằng `[lo,hi)`.

Nếu input lớn và có thể tràn `long`, phải đổi cả **định nghĩa kết quả** (ví dụ `BigInteger` hoặc kiểm tra `Math.addExact`), không âm thầm so hai giá trị cùng bị overflow rồi gọi là đúng.

### 2.2. Cùng dữ liệu nghĩa là gì?

- Với phép đọc không thay dữ liệu như sum/max, hai thuật toán có thể đọc cùng immutable input **sau khi các lần chạy đã hoàn tất**.
- Với sort hoặc transform làm thay đổi dữ liệu tại chỗ, phải tạo **hai bản sao từ dữ liệu gốc**.
- Không để thuật toán song song đọc mảng trong lúc thread khác vẫn đang sửa mảng.
- Nếu dùng random input, chọn **seed cố định** để tái lập lỗi, và ghi seed khi báo bug.
- Không so thời gian nếu bản tuần tự phải chuẩn bị input còn bản song song lại nhận sẵn input.
- Không đưa một mảng đã sort bởi phép thử trước vào phép thử tiếp nếu muốn so cùng workload.

## 3. Cây Fork/Join để tính tổng: bảo đảm không trùng, không sót

Mẫu chia đoạn nửa mở:

~~~text
Root [0,7)
       |
       +--- [0,3) --- indexes 0,1,2
       |
       +--- [3,7) --- indexes 3,4,5,6

Length = hi - lo
mid = lo + (hi - lo) / 2
Base case: length <= threshold (threshold >= 1)
~~~

**Bất biến quan trọng:**

1. Mỗi task có `0 <= lo <= hi <= a.length`.
2. Nếu chia, `lo < mid < hi` để cả hai children nhỏ hơn parent.
3. Hợp của `[lo,mid)` và `[mid,hi)` **đúng bằng** `[lo,hi)`.
4. Hai vùng **không giao nhau**.
5. Leaf tính đủ dữ liệu trên đoạn của chính nó.
6. Parent chỉ combine sau khi child cần thiết đã hoàn tất.

Với tổng, combine là phép cộng. Với histogram, combine là cộng tương ứng từng bin. Với transform, children viết vào hai dải index riêng; parent chỉ chờ completion.

**Vì sao phải thử đầu vào lẻ?** Với n=7, mid=3; nếu một nhánh dùng [0,3] và nhánh còn lại [3,7], index 3 sẽ bị xử lý hai lần. Với các test chỉ dài 2,4,8 và toàn các số giống nhau, lỗi này đôi khi bị che khuất.

## 4. Ví dụ 1 — Đối chiếu tổng tuần tự và Fork/Join

Tạo `SumComparisonDemo.java`:

~~~java
import java.util.concurrent.*;

public class SumComparisonDemo {
    static long sequential(int[] a) {
        long sum = 0;
        for (int x : a) sum += x;
        return sum;
    }

    static final class SumTask extends RecursiveTask<Long> {
        final int[] a;
        final int lo, hi, threshold;

        SumTask(int[] a, int lo, int hi, int threshold) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected Long compute() {
            int n = hi - lo;
            if (n <= threshold) {
                long s = 0;
                for (int i = lo; i < hi; i++) s += a[i];
                return s;
            }

            int mid = lo + n / 2;
            SumTask left = new SumTask(a, lo, mid, threshold);
            left.fork();
            long right = new SumTask(
                    a, mid, hi, threshold).compute();

            return left.join() + right;
        }
    }

    static long parallel(int[] a, ForkJoinPool pool) {
        return pool.invoke(new SumTask(a, 0, a.length, 2));
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            int[] a = {4, -2, 7, 5, 1, -3, 8};
            long s = sequential(a);
            long p = parallel(a, pool);

            System.out.println("sequential=" + s);
            System.out.println("parallel=" + p);
            System.out.println("equal=" + (s == p));

            int[] empty = {};
            int[] single = {42};
            System.out.println("emptyEqual=" +
                    (sequential(empty) == parallel(empty, pool)));
            System.out.println("singleEqual=" +
                    (sequential(single) == parallel(single, pool)));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 SumComparisonDemo.java
java SumComparisonDemo
~~~

Stdout đã kiểm chứng:

~~~text
sequential=20
parallel=20
equal=true
emptyEqual=true
singleEqual=true
~~~

**Phân tích:**

- Oracle tuần tự không dùng Fork/Join và không chia range.
- `SumTask` dùng base case khi n<=2, không tạo task cho mỗi phần tử khi đã đủ nhỏ.
- `left.fork()` tạo khả năng thực thi đồng thời; parent tự `compute()` nhánh phải rồi mới `join()` nhánh trái.
- `pool.invoke` trả kết quả khi root hoàn tất.
- Cả mảng mẫu, mảng rỗng và mảng một phần tử đều khớp.
- Đây mới là **ba kiểm thử nhỏ**, chưa chứng minh code đúng cho mọi input hoặc nhanh hơn.

**Không suy diễn:** Kết quả `true` của một lần chạy không cho biết đã thực sự dùng bao nhiêu CPU cores. Và chỉ đặt `ForkJoinPool(2)` không bảo đảm sẽ có speedup so với vòng for đơn giản.

## 5. Test case matrix: không chỉ dùng happy path

Một test suite tối thiểu nên bao phủ:

| Nhóm | Ví dụ | Loại bug dễ phát hiện |
| --- | --- | --- |
| Empty | `[]` | Base case truy cập phần tử không tồn tại |
| Singleton | `[42]` | Split không tiến triển |
| Toàn âm | `[-5,-7,-9]` | Max/sentinel sai, sign bug |
| Toàn zero | `[0,0,0,0]` | Xử lý không cần thiết, nhưng không phát hiện mọi bug |
| Giá trị biên | `Integer.MAX_VALUE, Integer.MIN_VALUE` | Tràn int, casting |
| Dài lẻ | 7 hoặc 31 phần tử | Off-by-one tại mid |
| Dài chẵn | 2,4,8 phần tử | Phân hoạch cân bằng |
| Duplicate | Nhiều giá trị lặp | Sort ổn định theo quy tắc, histogram |
| Sát threshold | `t-1,t,t+1` | Chọn nhánh dừng sai |
| Threshold khác nhau | 1,2,3,5,17 | Kết quả không được đổi theo mức chia |
| Nhiều lần chạy | Lặp lại với cùng seed | Phát hiện một số bug đồng thời |
| Input không hợp lệ | null, range đảo, threshold 0 | Validation, không treo |
| Overflow | Giá trị vượt long | Chính sách lỗi rõ ràng |

**Nếu có mutate input**, tạo snapshot trước khi chạy rồi kiểm tra sự bất biến hoặc expected mutation sau khi chạy. Không chỉ kiểm tra sum vì một lỗi ghi đè có thể tình cờ tạo cùng tổng.

## 6. Ví dụ 2 — 35 phép kiểm chứng qua trường hợp biên

Tạo `EdgeCaseMatrixDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;

public class EdgeCaseMatrixDemo {
    static class SumTask extends RecursiveTask<Long> {
        final int[] a;
        final int lo, hi, t;

        SumTask(int[] a, int lo, int hi, int t) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.t = t;
        }

        @Override
        protected Long compute() {
            int n = hi - lo;
            if (n <= t) {
                long sum = 0;
                for (int i = lo; i < hi; i++) sum += a[i];
                return sum;
            }

            int m = lo + n / 2;
            SumTask left = new SumTask(a, lo, m, t);
            left.fork();
            long right = new SumTask(a, m, hi, t).compute();
            return left.join() + right;
        }
    }

    static long sequential(int[] a) {
        long s = 0;
        for (int x : a) s += x;
        return s;
    }

    public static void main(String[] args) {
        int[][] cases = {
                {}, {42}, {-5, -7, -9}, {0, 0, 0, 0},
                {Integer.MAX_VALUE, Integer.MIN_VALUE, 1},
                {1, 2, 3, 4, 5, 6, 7},
                {9, -9, 5, -5, 3, -3, 1, -1}
        };
        int[] thresholds = {1, 2, 3, 5, 17};
        int checks = 0;
        boolean good = true;
        boolean preserved = true;

        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            for (int[] test : cases) {
                int[] copy = test.clone();
                long expected = sequential(test);

                for (int t : thresholds) {
                    long actual = pool.invoke(
                            new SumTask(test, 0, test.length, t));
                    good &= (expected == actual);
                    checks++;
                }

                preserved &= Arrays.equals(test, copy);
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("cases=" + cases.length);
        System.out.println("checks=" + checks);
        System.out.println("allMatch=" + good);
        System.out.println("inputPreserved=" + preserved);
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 EdgeCaseMatrixDemo.java
java EdgeCaseMatrixDemo
~~~

Stdout:

~~~text
cases=7
checks=35
allMatch=true
inputPreserved=true
~~~

Có 7 bộ dữ liệu × 5 ngưỡng = **35 lần** so sánh. `inputPreserved=true` chứng minh test này không thấy mutation của mảng gốc. Nhưng code vẫn cần kiểm thử trên input lớn và kiểm tra các loại lỗi khác (ví dụ overflow long hay race ở thuật toán ghi dữ liệu) nếu nghiệp vụ yêu cầu.

### 6.1. Vì sao không chỉ test tổng?

Nếu split sai nhưng hai phần bằng nhau về mặt giá trị, phép tổng vẫn có thể tình cờ khớp. Ví dụ bỏ qua một giá trị +5 nhưng xử lý trùng một giá trị +5 khác: tổng không đổi, nhưng histogram và dữ liệu từng vị trí đã sai. Vì vậy test nhiều **loại bất biến**: tổng, đếm, tập giá trị, histogram, kích thước và đối chiếu từng phần tử khi có thể.

## 7. Property-style testing với seed cố định

Để tìm lỗi ở kích thước và giá trị không dự đoán trước, tạo nhiều mảng bằng `SplittableRandom(seed)`. Chọn vài seed rõ ràng và ghi chúng vào test. Mỗi input được dùng cho nhiều threshold:

~~~text
Seeds:       1, 7, 42, 2026
Sizes:       0, 1, 2, 3, 7, 31, 256, 1000
Thresholds:  1, 8, 64

Tổng checks = 4 × 8 × 3 = 96
~~~

Nếu có failure, in/log seed, size, threshold, expected, actual và/hoặc mismatch index. **Seed cố định giúp tái lập**, nhưng không thay thế test ngẫu nhiên với seed mới trong CI ở một job khác.

### 7.1. Cẩn thận với dữ liệu ngẫu nhiên trong benchmark

- Khi đo, không sinh random **bên trong** phần cần đo nếu mục tiêu chỉ là đánh giá thuật toán.
- Hai bản phải đọc **cùng một mảng** hoặc hai bản sao tương đương.
- Với sort/mutation, tái tạo hai bản sao từ input chưa thay đổi trước mỗi phép thử.
- Tránh chỉ chọn dữ liệu đã sắp xếp hoặc toàn zero trừ khi đó là workload thật.
- Test tính đúng và benchmark nên chạy ở **hai chế độ riêng**, để test assertions và logging không làm méo timing.

## 8. Ví dụ 3 — 96 phép so sánh có thể tái lập

Tạo `SeededPropertyCheckDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;

public class SeededPropertyCheckDemo {
    static final class Task extends RecursiveTask<Long> {
        final int[] a;
        final int lo, hi, threshold;

        Task(int[] a, int lo, int hi, int threshold) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected Long compute() {
            int n = hi - lo;
            if (n <= threshold) {
                long sum = 0;
                for (int i = lo; i < hi; i++) sum += a[i];
                return sum;
            }

            int m = lo + n / 2;
            Task left = new Task(a, lo, m, threshold);
            left.fork();
            long right = new Task(
                    a, m, hi, threshold).compute();

            return left.join() + right;
        }
    }

    public static void main(String[] args) {
        long[] seeds = {1, 7, 42, 2026};
        int[] sizes = {0, 1, 2, 3, 7, 31, 256, 1000};
        int[] thresholds = {1, 8, 64};
        int checks = 0;
        boolean allMatch = true;

        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            for (long seed : seeds) {
                SplittableRandom rnd = new SplittableRandom(seed);

                for (int size : sizes) {
                    int[] a = new int[size];
                    long expected = 0;

                    for (int i = 0; i < a.length; i++) {
                        a[i] = rnd.nextInt(-1000, 1001);
                        expected += a[i];
                    }

                    for (int threshold : thresholds) {
                        long actual = pool.invoke(
                                new Task(
                                        a, 0, a.length, threshold));
                        allMatch &= (expected == actual);
                        checks++;
                    }
                }
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("seedCount=" + seeds.length);
        System.out.println("sizeCount=" + sizes.length);
        System.out.println("checks=" + checks);
        System.out.println("allMatch=" + allMatch);
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 SeededPropertyCheckDemo.java
java SeededPropertyCheckDemo
~~~

Stdout:

~~~text
seedCount=4
sizeCount=8
checks=96
allMatch=true
~~~

**Giải thích:** Với mỗi seed, `SplittableRandom` tạo các mảng trong khoảng giá trị -1000..1000. Oracle sum được cộng bằng vòng for đơn giản. Fork/Join được chạy ba lần với cùng input và những threshold khác nhau. Nếu kết quả đổi khi đổi threshold, rất có thể có lỗi split, combine, overflow policy hoặc shared state.

**Điểm giới hạn:** 96 checks là một **bộ test minh họa hữu hạn**. Nó không thay thế test các khoảng dữ liệu khổng lồ, kiểm thử khi nhiều requests cùng chạy, hoặc kiểm chứng thuật toán ở cấp chứng minh hình thức.

## 9. Đối chiếu hai phép sort phải so **từng phần tử**

Java có `Arrays.sort` tuần tự và `Arrays.parallelSort` dùng cơ chế parallel trong các trường hợp phù hợp. Đối với `int[]` sắp xếp tăng dần, cả hai phải cho **cùng thứ tự giá trị**. Đây là ví dụ tốt để học cách so kết quả trước khi quan tâm performance.

**Quan trọng về phiên bản:** `Arrays.parallelSort` được giới thiệu từ Java 8, hiện vẫn được hỗ trợ. Nó không phải API gốc của Java 7, nhưng hoàn toàn phù hợp Special Note vì bài dùng **kiến thức Java hiện hành** trong ngữ cảnh Fork/Join.

### 9.1. So sánh bằng Arrays.equals và Arrays.mismatch

- `Arrays.equals(a,b)` trả true nếu hai mảng primitive có cùng length và các phần tử tương ứng bằng nhau theo quy tắc API.
- `Arrays.mismatch(a,b)` trả index lệch đầu tiên hoặc `-1` nếu không có lệch (API từ Java 9).
- Không dùng `a == b` để so nội dung, vì đó là phép so **tham chiếu đối tượng**.
- Không chỉ so tổng hoặc `hashCode` vì có thể collision hoặc nhiều hoán vị cho cùng checksum.
- Với object arrays, xác định comparator và việc null, duplicate, tie-breaking để so đúng semantics.

## 10. Ví dụ 4 — Arrays.sort so với Arrays.parallelSort

Tạo `ParallelSortComparisonDemo.java`:

~~~java
import java.util.*;

public class ParallelSortComparisonDemo {
    public static void main(String[] args) {
        int[] sample = {7, -2, 7, 0, 9, 2, -2};

        int[] expected = sample.clone();
        int[] actual = sample.clone();

        Arrays.sort(expected);
        Arrays.parallelSort(actual);

        System.out.println("sorted=" +
                Arrays.toString(actual));
        System.out.println("smallEqual=" +
                Arrays.equals(expected, actual));
        System.out.println("firstMismatch=" +
                Arrays.mismatch(expected, actual));

        int[][] boundaries = {
                {}, {1}, {4, 4, 4, 4}, {5, 4, 3, 2, 1}
        };
        boolean boundariesEqual = true;

        for (int[] input : boundaries) {
            int[] a = input.clone();
            int[] b = input.clone();

            Arrays.sort(a);
            Arrays.parallelSort(b);
            boundariesEqual &= Arrays.equals(a, b);
        }

        System.out.println("boundaryCasesEqual=" +
                boundariesEqual);

        SplittableRandom random =
                new SplittableRandom(245);
        int[] larger = new int[10000];

        for (int i = 0; i < larger.length; i++) {
            larger[i] = random.nextInt(-100000, 100001);
        }

        int[] x = larger.clone();
        int[] y = larger.clone();

        Arrays.sort(x);
        Arrays.parallelSort(y);

        System.out.println("largeEqual=" +
                Arrays.equals(x, y));
        System.out.println("sourceUnchanged=" +
                Arrays.equals(larger, larger.clone()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ParallelSortComparisonDemo.java
java ParallelSortComparisonDemo
~~~

Stdout:

~~~text
sorted=[-2, -2, 0, 2, 7, 7, 9]
smallEqual=true
firstMismatch=-1
boundaryCasesEqual=true
largeEqual=true
sourceUnchanged=true
~~~

**Phân tích:**

1. Hai mảng đầu ra được `clone()` từ **cùng sample**.
2. `Arrays.sort(expected)` chạy trước trên một copy.
3. `Arrays.parallelSort(actual)` chạy trên copy khác, không được hưởng dữ liệu đã sort trước.
4. `Arrays.equals` kiểm tra **toàn bộ** kết quả.
5. `Arrays.mismatch` bổ sung index lỗi đầu tiên nếu có.
6. Test thêm mảng rỗng, một phần tử, trùng và đảo chiều.
7. Mảng 10.000 phần tử từ seed cố định mở rộng phạm vi input.

**Không suy diễn:** API `parallelSort` có thể dùng xử lý tuần tự cho mảng nhỏ; chữ "parallel" trong tên **không đảm bảo** mọi lần chạy tạo worker song song. Điều kiện tối ưu, cut-off và pool là chi tiết implementation.

Nguồn: [Oracle Java SE 26 — Arrays](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html).

## 11. Khi hai mảng khác nhau: báo vị trí lỗi đầu tiên

Chỉ biết `equal=false` thường chưa đủ để debug. Với các thuật toán xử lý mảng, in index lỗi đầu tiên và giá trị hai phía giúp phát hiện:

- Range bị lệch một phần tử.
- Output bị ghi trùng ở boundary.
- Task chỉ xử lý nửa đầu.
- Sai thứ tự merge.
- Cùng giá trị nhưng bị đảo vị trí.
- Một phần dữ liệu còn trạng thái cũ.

## 12. Ví dụ 5 — Chẩn đoán bằng Arrays.mismatch

Tạo `MismatchDiagnosisDemo.java`:

~~~java
import java.util.*;

public class MismatchDiagnosisDemo {
    public static void main(String[] args) {
        int[] expected = {2, 4, 6, 8, 10};
        int[] actual = {2, 4, 999, 8, 10};

        int mismatch = Arrays.mismatch(expected, actual);

        System.out.println("equal=" +
                Arrays.equals(expected, actual));
        System.out.println("firstMismatch=" + mismatch);
        System.out.println("expectedAt=" + expected[mismatch]);
        System.out.println("actualAt=" + actual[mismatch]);
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 MismatchDiagnosisDemo.java
java MismatchDiagnosisDemo
~~~

Stdout:

~~~text
equal=false
firstMismatch=2
expectedAt=6
actualAt=999
~~~

Trong production, chỉ truy cập `expected[mismatch]` khi mismatch là index hợp lệ của cả hai mảng. Nếu độ dài khác nhau, `Arrays.mismatch` có thể trả độ dài mảng ngắn hơn; khi đó một bên **không có phần tử** tại index ấy. Ví dụ trên có cùng length và mismatch ở giữa, nên truy cập an toàn.

### 12.1. Gợi ý thông báo failure có thể tái hiện

Khi test thất bại, ghi:

~~~text
algorithm=parallelSort
seed=245
length=10000
threshold=not-applicable
expectedLength=10000
actualLength=10000
firstMismatchIndex=...
expectedValue=...
actualValue=...
javaVersion=...
cpuCount=...
~~~

Đây là **mẫu log minh họa**, không phải stdout cố định. Không log toàn bộ dữ liệu nhạy cảm vào hệ thống production. Trong test local, có thể lưu input nhỏ nhất làm regression fixture.

## 13. Tại sao histogram là test tốt hơn chỉ kiểm tra tổng?

Histogram đếm số lần xuất hiện của từng byte 0..255. Nó có 256 bins nên một lỗi chồng lấn ở split có thể làm biến đổi **một vài bins** mà tổng vẫn trùng ngẫu nhiên.

Với mỗi byte `b`, index bin đúng là:

~~~java
int index = b & 0xff;
~~~

Vì kiểu `byte` trong Java là signed -128..127, việc sử dụng `b` trực tiếp như index có thể âm. Mask `0xff` chuyển cách diễn giải sang 0..255.

Mẫu Fork/Join:

- Leaf đếm histogram riêng.
- Hai subtasks trả về hai mảng histogram **không dùng chung**.
- Parent `join()`, rồi cộng hai histogram tương ứng từng bin.
- Không có shared counters cập nhật bởi nhiều worker mà không đồng bộ.
- Kiểm tra `sum(histogram) == input.length` và `Arrays.equals(seqBins,parBins)`.

## 14. Ví dụ 6 — Histogram tuần tự và song song

Tạo `HistogramComparisonDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;

public class HistogramComparisonDemo {
    static long[] sequential(byte[] a) {
        long[] bins = new long[256];
        for (byte b : a) bins[b & 0xff]++;
        return bins;
    }

    static final class Task extends RecursiveTask<long[]> {
        final byte[] a;
        final int lo, hi, threshold;

        Task(byte[] a, int lo, int hi, int threshold) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected long[] compute() {
            int n = hi - lo;

            if (n <= threshold) {
                long[] bins = new long[256];
                for (int i = lo; i < hi; i++) {
                    bins[a[i] & 0xff]++;
                }
                return bins;
            }

            int mid = lo + n / 2;
            Task left = new Task(a, lo, mid, threshold);
            left.fork();

            long[] right = new Task(
                    a, mid, hi, threshold).compute();
            long[] lhs = left.join();

            for (int i = 0; i < 256; i++) {
                lhs[i] += right[i];
            }
            return lhs;
        }
    }

    public static void main(String[] args) {
        byte[] data = new byte[4096];
        for (int i = 0; i < data.length; i++) {
            data[i] = (byte) (i % 4);
        }

        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            long[] expected = sequential(data);
            long[] actual = pool.invoke(
                    new Task(data, 0, data.length, 128));

            long total = Arrays.stream(actual).sum();
            long distinct = Arrays.stream(actual)
                    .filter(v -> v > 0).count();

            System.out.println("histogramEqual=" +
                    Arrays.equals(expected, actual));
            System.out.println("total=" + total);
            System.out.println("bin0=" + actual[0]);
            System.out.println("bin3=" + actual[3]);
            System.out.println("bin255=" + actual[255]);
            System.out.println("distinctBins=" + distinct);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 HistogramComparisonDemo.java
java HistogramComparisonDemo
~~~

Stdout:

~~~text
histogramEqual=true
total=4096
bin0=1024
bin3=1024
bin255=0
distinctBins=4
~~~

**Cơ chế:** Mỗi nhánh tạo histogram riêng; parent chỉ thay đổi `lhs` **sau khi** `left.join()` đã hoàn tất, và `right` là kết quả của compute trực tiếp đã xong. Việc tái sử dụng `lhs` để combine an toàn trong cây này vì nó không đồng thời bị child còn chạy thay đổi.

**Hiệu năng:** Mỗi leaf cấp phát `long[256]`, mỗi combine cộng 256 bins. Với lượng dữ liệu rất nhỏ, overhead của nhiều mảng và combine có thể lớn hơn một vòng for tuần tự. So kết quả trước; nếu benchmark cho thấy chậm, tăng threshold hoặc đổi layout/chiến lược bộ đệm phù hợp thay vì sửa ngẫu nhiên logic.

## 15. Side effects: phải so hai bản sao độc lập

Nếu thuật toán biến đổi dữ liệu tại chỗ, **không** được:

~~~java
sequentialTransform(data);
parallelTransform(data); // Đầu vào đã bị biến đổi lần đầu!
~~~

Đây là **mã sai có chủ ý**, không phải chương trình độc lập. Ví dụ biến đổi `x -> 2*x+1` sẽ cho hai kết quả khác nhau đơn giản vì input đã bị sửa, không liên quan tính đúng của parallel implementation.

Cần:

~~~java
int[] sequentialCopy = original.clone();
int[] parallelCopy = original.clone();

sequentialTransform(sequentialCopy);
parallelTransform(parallelCopy);

// Arrays.equals(sequentialCopy, parallelCopy)
~~~

Trong thuật toán song song ghi mảng, mỗi subtask chỉ ghi vào vùng `[lo,hi)` **không chồng lấn**. Không chia range mơ hồ rồi cho nhiều workers cùng cập nhật một index.

## 16. Ví dụ 7 — RecursiveAction và đối chiếu mảng biến đổi

Tạo `ActionComparisonDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;

public class ActionComparisonDemo {
    static void sequential(int[] a) {
        for (int i = 0; i < a.length; i++) {
            a[i] = Math.addExact(
                    Math.multiplyExact(a[i], 2), 1);
        }
    }

    static final class Task extends RecursiveAction {
        final int[] a;
        final int lo, hi, threshold;

        Task(int[] a, int lo, int hi, int threshold) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected void compute() {
            int n = hi - lo;
            if (n <= threshold) {
                for (int i = lo; i < hi; i++) {
                    a[i] = Math.addExact(
                            Math.multiplyExact(a[i], 2), 1);
                }
                return;
            }

            int mid = lo + n / 2;
            invokeAll(
                    new Task(a, lo, mid, threshold),
                    new Task(a, mid, hi, threshold));
        }
    }

    public static void main(String[] args) {
        int[] original = {-3, -1, 0, 2, 5, 7};
        int[] seq = original.clone();
        int[] par = original.clone();

        sequential(seq);

        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            pool.invoke(new Task(
                    par, 0, par.length, 2));

            System.out.println("sequential=" +
                    Arrays.toString(seq));
            System.out.println("parallel=" +
                    Arrays.toString(par));
            System.out.println("equal=" +
                    Arrays.equals(seq, par));
            System.out.println("originalUntouched=" +
                    Arrays.equals(
                            original, new int[]{-3, -1, 0, 2, 5, 7}));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ActionComparisonDemo.java
java ActionComparisonDemo
~~~

Stdout:

~~~text
sequential=[-5, -1, 1, 5, 11, 15]
parallel=[-5, -1, 1, 5, 11, 15]
equal=true
originalUntouched=true
~~~

**Giải thích:** `RecursiveAction` có `compute()` trả `void`. Hai nhánh `invokeAll` xử lý những **vùng độc lập**, không cần kết quả return; root chỉ hoàn tất sau children. Test so toàn bộ mảng đầu ra và xác nhận mảng gốc vẫn nguyên vẹn.

**Lưu ý exception:** `Math.multiplyExact`/`Math.addExact` báo tràn số, nhưng những index xử lý trước khi lỗi có thể đã bị sửa. Fork/Join không tự rollback mutation; nếu cần cập nhật nguyên tử, thiết kế đầu ra tạm và publish sau khi tất cả thành công.

## 17. Maximum: quy tắc cho mảng rỗng phải nhất quán

Một sai lầm thường gặp là viết:

~~~java
int max = 0;
for (int x : array) max = Math.max(max, x);
~~~

Đây là **mã minh họa sai** khi toàn bộ số âm: nó trả 0 dù dữ liệu không chứa 0. Nếu input rỗng, maximum thực sự **không xác định**. Hai bản tuần tự/song song phải nhất quán theo một trong hai hợp đồng:

- Trả `OptionalInt.empty()` khi không có phần tử.
- Hoặc từ chối empty input bằng exception rõ ràng.
- Với input không rỗng, lấy phần tử đầu tiên làm giá trị khởi tạo.

Dùng `OptionalInt` làm cho test mảng rỗng và dữ liệu âm có ý nghĩa.

## 18. Ví dụ 8 — So sánh maximum với OptionalInt

Tạo `MaxComparisonDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;

public class MaxComparisonDemo {
    static OptionalInt sequential(int[] a) {
        if (a.length == 0) return OptionalInt.empty();

        int m = a[0];
        for (int i = 1; i < a.length; i++) {
            m = Math.max(m, a[i]);
        }
        return OptionalInt.of(m);
    }

    static final class Task
            extends RecursiveTask<OptionalInt> {
        final int[] a;
        final int lo, hi, t;

        Task(int[] a, int lo, int hi, int t) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.t = t;
        }

        @Override
        protected OptionalInt compute() {
            int n = hi - lo;
            if (n <= t) {
                if (n == 0) return OptionalInt.empty();

                int m = a[lo];
                for (int i = lo + 1; i < hi; i++) {
                    m = Math.max(m, a[i]);
                }
                return OptionalInt.of(m);
            }

            int mid = lo + n / 2;
            Task left = new Task(a, lo, mid, t);
            left.fork();

            OptionalInt right =
                    new Task(a, mid, hi, t).compute();
            OptionalInt lhs = left.join();

            if (lhs.isEmpty()) return right;
            if (right.isEmpty()) return lhs;

            return OptionalInt.of(
                    Math.max(lhs.getAsInt(), right.getAsInt()));
        }
    }

    public static void main(String[] args) {
        int[] negative = {-10, -3, -25, -4, -9};
        int[] empty = {};

        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            OptionalInt s = sequential(negative);
            OptionalInt p = pool.invoke(
                    new Task(
                            negative, 0, negative.length, 2));

            OptionalInt se = sequential(empty);
            OptionalInt pe = pool.invoke(
                    new Task(empty, 0, 0, 2));

            System.out.println("sequential=" +
                    s.orElseThrow());
            System.out.println("parallel=" +
                    p.orElseThrow());
            System.out.println("same=" + s.equals(p));
            System.out.println("emptyBothMissing=" +
                    (se.isEmpty() && pe.isEmpty()));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 MaxComparisonDemo.java
java MaxComparisonDemo
~~~

Stdout:

~~~text
sequential=-3
parallel=-3
same=true
emptyBothMissing=true
~~~

Không so max bằng cách lấy `orElse(0)` ở hai phía; làm vậy che mất sự khác nhau giữa **có giá trị 0** và **không có giá trị**.

## 19. Tổng double: đúng thuật toán vẫn có thể không bằng bit

Đối với số thực IEEE 754, phép cộng nói chung **không có tính kết hợp chính xác**:

~~~text
(a + b) + c  có thể khác  a + (b + c)
~~~

Thuật toán tuần tự và Fork/Join có thể tạo **thứ tự nhóm phép tính khác nhau**:

~~~text
Input: [1e16, 1, -1e16, 1]

Sequential:
    (((0 + 1e16) + 1) - 1e16) + 1
    -> 1.0 trên double (1 bị làm tròn ở bước 1e16 + 1)

Parallel với threshold 2:
    left  = 1e16 + 1     -> 1e16
    right = -1e16 + 1    -> -1e16
    left + right         -> 0.0
~~~

Cả hai là cách tính floating-point khác nhau, **không nhất thiết là race condition**. Không đặt ra tiêu chí `exactEqual=true` vô điều kiện khi parallel reduce thay đổi grouping.

### 19.1. Chọn hợp đồng so sánh số thực

- Nếu nghiệp vụ yêu cầu **bitwise/reproducible exact decimal**, xét `BigDecimal` với scale/rounding được định nghĩa hoặc thuật toán summation ổn định, không đơn giản xem `double` như số thực toán học.
- Nếu chấp nhận sai khác số, định nghĩa **absolute/relative tolerance theo miền giá trị**, không chọn epsilon chung cho mọi dataset.
- `NaN`, `Infinity` và `+0.0/-0.0` cần được xử lý theo semantics nghiệp vụ.
- `Double.compare` có semantics riêng cho NaN và signed zero; `==` cũng không giống hoàn toàn.
- Nếu phép combine phụ thuộc thứ tự, kết quả song song có thể không phù hợp yêu cầu dù chạy nhanh.
- Test cả dữ liệu có **cancellation**: giá trị dương/âm rất lớn gần triệt tiêu nhau.

Nguồn: [Oracle Java SE 26 — Arrays.parallelPrefix(double)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html), Javadoc ghi rõ phép toán dấu phẩy động không nhất thiết có kết quả y hệt chạy tuần tự.

## 20. Ví dụ 9 — Chứng minh khác biệt thứ tự cộng double

Tạo `FloatingOrderDemo.java`:

~~~java
import java.util.concurrent.*;

public class FloatingOrderDemo {
    static double sequential(double[] a) {
        double sum = 0;
        for (double x : a) sum += x;
        return sum;
    }

    static final class Task extends RecursiveTask<Double> {
        final double[] a;
        final int lo, hi, threshold;

        Task(double[] a, int lo, int hi, int threshold) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected Double compute() {
            int n = hi - lo;
            if (n <= threshold) {
                double s = 0;
                for (int i = lo; i < hi; i++) s += a[i];
                return s;
            }

            int mid = lo + n / 2;
            Task left = new Task(
                    a, lo, mid, threshold);
            left.fork();

            double right = new Task(
                    a, mid, hi, threshold).compute();
            return left.join() + right;
        }
    }

    public static void main(String[] args) {
        double[] data = {1e16, 1.0, -1e16, 1.0};
        double s = sequential(data);

        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            double p = pool.invoke(
                    new Task(
                            data, 0, data.length, 2));

            System.out.println("sequential=" + s);
            System.out.println("parallel=" + p);
            System.out.println("exactEqual=" +
                    (Double.compare(s, p) == 0));
            System.out.println("absoluteDifference=" +
                    Math.abs(s - p));
            System.out.println("withinExampleTolerance=" +
                    (Math.abs(s - p) <= 1.0));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 FloatingOrderDemo.java
java FloatingOrderDemo
~~~

Stdout:

~~~text
sequential=1.0
parallel=0.0
exactEqual=false
absoluteDifference=1.0
withinExampleTolerance=true
~~~

**Lưu ý rất quan trọng:** Dung sai 1.0 ở ví dụ này **chỉ là phép minh họa** để thấy việc chọn tolerance làm thay kết luận. Nó **không phải** ngưỡng mặc định tốt hoặc khuyến nghị cho dữ liệu tài chính/khoa học. Hãy xác định mức lỗi chấp nhận từ bài toán, xét cả absolute và relative error, special values và nhu cầu reproducibility. Không được diễn giải `withinExampleTolerance=true` là chứng minh hai cách tính tương đương trong mọi ứng dụng.

## 21. Threshold thay đổi số tasks, không được làm đổi ý nghĩa

Trong một cây chia đôi của `RecursiveTask`:

- `threshold` thấp: nhiều leaf tasks, nhiều `fork/join`/allocations, overhead có thể rất lớn.
- `threshold` cao: ít task hơn, có thể không đủ công việc phân phối nhiều workers.
- `threshold` hợp lý: leaf đủ lớn để amortize overhead nhưng vẫn tạo đủ parallelism.
- **Kết quả tính đúng** phải giữ nguyên khi thay threshold, trừ các phép toán như floating-point có luật làm tròn/thứ tự khác hoặc thuật toán định nghĩa behavior phụ thuộc grouping.

Nếu đổi threshold mà tổng `long` trong miền không overflow đổi giá trị, đó là **dấu hiệu có bug**: split, range, join, mutable state, hoặc lỗi logic ở base case.

Đừng đồng nhất số `leaf tasks` với số `threads`. Một pool hai workers có thể xử lý hàng nghìn tasks; các tasks được xếp lịch và work-stealing theo runtime.

## 22. Ví dụ 10 — Đổi threshold và so cùng oracle

Tạo `ThresholdSweepComparisonDemo.java`:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class ThresholdSweepComparisonDemo {
    static final class Task extends RecursiveTask<Long> {
        final int[] a;
        final int lo, hi, t;
        final AtomicInteger leaves;

        Task(
                int[] a, int lo, int hi,
                int t, AtomicInteger leaves) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.t = t;
            this.leaves = leaves;
        }

        @Override
        protected Long compute() {
            int n = hi - lo;
            if (n <= t) {
                leaves.incrementAndGet();
                long s = 0;
                for (int i = lo; i < hi; i++) s += a[i];
                return s;
            }

            int mid = lo + n / 2;
            Task left = new Task(
                    a, lo, mid, t, leaves);
            left.fork();

            long right = new Task(
                    a, mid, hi, t, leaves).compute();
            return left.join() + right;
        }
    }

    public static void main(String[] args) {
        int[] a = new int[2048];
        long expected = 0;
        for (int i = 0; i < a.length; i++) {
            a[i] = i - 1024;
            expected += a[i];
        }

        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            System.out.println("sequential=" + expected);

            for (int t : new int[]{1, 32, 256}) {
                AtomicInteger leaves = new AtomicInteger();

                long answer = pool.invoke(
                        new Task(
                                a, 0, a.length, t, leaves));

                System.out.println(
                        "threshold=" + t
                        + " leaves=" + leaves.get()
                        + " equal=" + (answer == expected));
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ThresholdSweepComparisonDemo.java
java ThresholdSweepComparisonDemo
~~~

Stdout:

~~~text
sequential=-1024
threshold=1 leaves=2048 equal=true
threshold=32 leaves=64 equal=true
threshold=256 leaves=8 equal=true
~~~

**Giải thích:** 2.048 phần tử được chia nhị phân đều; threshold thấp nhất tạo 2.048 leaf tasks, threshold 256 chỉ còn 8 leaves. Tất cả cho tổng `-1024`. Mã không đo tốc độ; nó kiểm thử **độ đúng nhất quán** khi thay granularity.

`AtomicInteger` chỉ dùng đếm lá để giải thích; trong benchmark hiệu năng thật, nên tránh instrument mỗi leaf bằng shared atomic nếu hoạt động đo đó không phải workload cần đánh giá.

## 23. Cùng phép tính CPU-bound mới là đối tượng so công bằng

Một ví dụ tính tổng array rất rẻ có thể khiến bản song song thua vì overhead. Để hiểu tình huống có khả năng hưởng lợi, có thể thử một bài CPU-bound hơn, chẳng hạn đếm số nguyên tố từ 2 đến N.

Để oracle độc lập:

~~~java
static boolean isPrime(int x) {
    if (x < 2) return false;
    for (int d = 2; d <= x / d; d++) {
        if (x % d == 0) return false;
    }
    return true;
}
~~~

Dùng điều kiện `d <= x / d` để tránh overflow từ `d*d` với int lớn. Vòng lặp sequential đếm từ 2 tới N. Fork/Join chỉ chia khoảng các số ứng viên, mỗi leaf cũng dùng cùng logic primality. Điều này kiểm tra **chia việc và combine**, nhưng vẫn có thể bỏ sót bug **chung** trong hàm `isPrime`; nếu yêu cầu chắc chắn hơn, thêm danh sách các số nguyên tố đã biết hoặc oracle độc lập khác.

### 23.1. Lựa chọn oracle theo cấp độ test

- **Unit test split/combine:** Được dùng chung hàm tính primality ở leaf để kiểm tra partitioning.
- **Integration test end-to-end:** Đối chiếu với một reference độc lập hoặc bộ kết quả chuẩn.
- **Regression test:** Lưu seed và input từng gây lỗi.
- **Stress test:** Chạy cùng operation nhiều lần với mức parallelism khác nhau để tìm race, không phải để đo tốc độ.

## 24. Ví dụ 11 — Đếm số nguyên tố, so tuần tự với Fork/Join

Tạo `PrimeCountComparisonDemo.java`:

~~~java
import java.util.concurrent.*;

public class PrimeCountComparisonDemo {
    static boolean isPrime(int x) {
        if (x < 2) return false;
        for (int d = 2; d <= x / d; d++) {
            if (x % d == 0) return false;
        }
        return true;
    }

    static int sequential(int from, int to) {
        int count = 0;
        for (int i = from; i < to; i++) {
            if (isPrime(i)) count++;
        }
        return count;
    }

    static final class Task extends RecursiveTask<Integer> {
        final int lo, hi, threshold;

        Task(int lo, int hi, int threshold) {
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected Integer compute() {
            int n = hi - lo;
            if (n <= threshold) {
                return sequential(lo, hi);
            }

            int mid = lo + n / 2;
            Task left =
                    new Task(lo, mid, threshold);
            left.fork();

            int right = new Task(
                    mid, hi, threshold).compute();
            return right + left.join();
        }
    }

    public static void main(String[] args) {
        final int limit = 10000;
        int expected = sequential(2, limit + 1);

        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            System.out.println("limit=" + limit);
            System.out.println("sequential=" + expected);
            System.out.println("threshold128Equal=" +
                    (expected == pool.invoke(
                            new Task(2, limit + 1, 128))));
            System.out.println("threshold1024Equal=" +
                    (expected == pool.invoke(
                            new Task(2, limit + 1, 1024))));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 PrimeCountComparisonDemo.java
java PrimeCountComparisonDemo
~~~

Stdout:

~~~text
limit=10000
sequential=1229
threshold128Equal=true
threshold1024Equal=true
~~~

Có **1.229** số nguyên tố không vượt quá 10.000. Bài dùng số này làm một fixture kiểm tra sanity; nếu triển khai cần xử lý N rất lớn, kiểm soát input/range, thuật toán primality và khả năng overflow cũng là một phần thiết kế.

**Không mặc định sẽ nhanh:** Một thuật toán có thể CPU-bound nhưng vẫn quá nhỏ để phần trăm chi phí fork/join đáng kể. Phải benchmark với nhiều kích thước và môi trường thật.

## 25. Cùng công việc nhưng khác API: vòng lặp, stream tuần tự và parallel stream

Ngoài việc tự viết `RecursiveTask`, Java còn có `Stream.parallel()`. Với phép tính reduce có tính kết hợp và không có side effects, bạn có thể dùng:

~~~java
long sequential =
        Arrays.stream(values).asLongStream().sum();

long parallel =
        Arrays.stream(values).asLongStream().parallel().sum();
~~~

Đây là hai dòng minh họa trong một phương thức đã có `int[] values`.

**Quan trọng:** Parallel streams thường sử dụng ForkJoin common pool trong JDK implementation, nhưng API stream không buộc mọi developer kiểm soát thread scheduling giống như một `ForkJoinPool` riêng. Không giả định parallel stream luôn nhanh, không dùng stateful lambdas sửa biến shared, và lưu ý phép cộng `int` có thể overflow khác với ý định nếu không chuyển sang `long` trước.

## 26. Ví dụ 12 — Vòng for, stream thường và parallel stream

Tạo `StreamComparisonDemo.java`:

~~~java
import java.util.*;

public class StreamComparisonDemo {
    public static void main(String[] args) {
        int[] values = {1, 2, 3, 4, -5, 6, 7};

        long expected = 0;
        for (int x : values) expected += x;

        long streamSequential =
                Arrays.stream(values)
                        .asLongStream()
                        .sum();

        long streamParallel =
                Arrays.stream(values)
                        .asLongStream()
                        .parallel()
                        .sum();

        System.out.println("loop=" + expected);
        System.out.println("streamSequential=" + streamSequential);
        System.out.println("streamParallel=" + streamParallel);
        System.out.println("same=" +
                (expected == streamSequential
                        && expected == streamParallel));
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 StreamComparisonDemo.java
java StreamComparisonDemo
~~~

Stdout:

~~~text
loop=18
streamSequential=18
streamParallel=18
same=true
~~~

**Giới hạn:** Đây là phép tổng nhỏ và có kết quả bằng nhau, không chứng minh stream parallel nhanh. Với dữ liệu ít, overhead thường vượt lợi ích; với `double` thì thứ tự reduce có thể thay kết quả bitwise. Thử các data shapes, CPU profiles và công việc thực.

Nguồn: [Oracle Java SE 26 — Stream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html), [IntStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html).

## 27. Nhất quán khi lỗi: không chỉ so “đầu ra thành công”

Khi dữ liệu sai, hai thuật toán nên có **hợp đồng lỗi** nhất quán:

- `threshold < 1`: từ chối để không chia vô hạn.
- `lo < 0`, `lo > hi` hoặc `hi > length`: từ chối range sai.
- `array == null`: từ chối null rõ ràng.
- Tổng vượt `long` nếu bài yêu cầu chính xác: dùng `Math.addExact` để ném ArithmeticException, hoặc `BigInteger`.
- Leaf ném lỗi: parent join/invoke không âm thầm trả kết quả giả.
- Tác vụ đang chạy có thể đã xử lý một phần state trước khi failure; nếu có mutation, cần quy tắc rollback/publish rõ.

Đôi khi hai implementation đều “cho cùng số” chỉ vì cùng **tràn số**. Nếu nghiệp vụ cần tổng chính xác, đó **không phải một bài test pass hợp lệ**.

### 27.1. Vì sao không chỉ bắt ArithmeticException từ một nhánh?

Một worker khác có thể khiến exception đi qua `join` với wrapping/stack trace khác. Khi kiểm thử một nguyên nhân nghiệp vụ xác định, có thể duyệt cause chain và kiểm tra type; khi chạy production, không nên nuốt exception hoặc bỏ qua task sibling đang hoạt động.

## 28. Ví dụ 13 — Validate input và so chính sách overflow

Tạo `ValidationAndOverflowDemo.java`:

~~~java
import java.util.concurrent.*;

public class ValidationAndOverflowDemo {
    static final class Task extends RecursiveTask<Long> {
        final long[] a;
        final int lo, hi, t;

        Task(long[] a, int lo, int hi, int t) {
            if (a == null) {
                throw new NullPointerException("a");
            }
            if (t < 1) {
                throw new IllegalArgumentException(
                        "threshold");
            }
            if (lo < 0 || hi < lo || hi > a.length) {
                throw new IndexOutOfBoundsException(
                        "range");
            }

            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.t = t;
        }

        @Override
        protected Long compute() {
            int n = hi - lo;
            if (n <= t) {
                long sum = 0;
                for (int i = lo; i < hi; i++) {
                    sum = Math.addExact(sum, a[i]);
                }
                return sum;
            }

            int mid = lo + n / 2;
            Task left = new Task(a, lo, mid, t);
            left.fork();

            long right = new Task(
                    a, mid, hi, t).compute();

            return Math.addExact(left.join(), right);
        }
    }

    public static void main(String[] args) {
        boolean badThreshold = false;
        boolean badRange = false;
        boolean seqOverflow = false;
        boolean parOverflow = false;

        try {
            new Task(new long[]{1}, 0, 1, 0);
        } catch (IllegalArgumentException e) {
            badThreshold = true;
        }

        try {
            new Task(new long[]{1}, 1, 0, 1);
        } catch (IndexOutOfBoundsException e) {
            badRange = true;
        }

        try {
            Math.addExact(Long.MAX_VALUE, 1);
        } catch (ArithmeticException e) {
            seqOverflow = true;
        }

        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            try {
                pool.invoke(new Task(
                        new long[]{Long.MAX_VALUE, 1},
                        0, 2, 1));
            } catch (RuntimeException e) {
                for (Throwable p = e;
                     p != null; p = p.getCause()) {
                    if (p instanceof ArithmeticException) {
                        parOverflow = true;
                        break;
                    }
                }
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("badThresholdRejected=" +
                badThreshold);
        System.out.println("badRangeRejected=" +
                badRange);
        System.out.println("sequentialOverflow=" +
                seqOverflow);
        System.out.println("parallelOverflow=" +
                parOverflow);
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 ValidationAndOverflowDemo.java
java ValidationAndOverflowDemo
~~~

Stdout:

~~~text
badThresholdRejected=true
badRangeRejected=true
sequentialOverflow=true
parallelOverflow=true
~~~

**Điểm cần nhớ:** Với phép cộng exact, nếu một cách grouping tạo intermediate sum vượt phạm vi nhưng kết quả toán học cuối cùng vẫn nằm trong phạm vi, hai cách có thể khác nhau về **vị trí phát hiện lỗi**. Nếu yêu cầu cộng nguyên chính xác cho mọi grouping lớn, `BigInteger` là lựa chọn rõ ràng hơn. Đừng coi `Math.addExact` là phép cộng có thể hoán đổi tùy ý mà không quan tâm overflow trung gian.

## 29. So hiệu năng: tại sao System.nanoTime một lần dễ sai?

Đo một lần như sau:

~~~java
long t = System.nanoTime();
long result = parallel(input);
System.out.println(System.nanoTime() - t);
~~~

Đây chỉ là **đo thăm dò**, không phải microbenchmark nghiêm túc. Nhiều yếu tố gây nhiễu:

- **JIT warm-up:** lần đầu JVM phải load class, compile/hotspot code, tạo worker threads.
- **GC:** cấp phát task objects và arrays có thể kích hoạt collection.
- **CPU frequency/thermal:** máy nóng, pin, power management, background jobs.
- **Thread pool creation:** nếu tính cả `new ForkJoinPool` ở một phía nhưng không ở phía kia, so sánh sai mục tiêu.
- **Data cache effects:** mảng đọc lần đầu khác mảng vừa được xử lý.
- **Order bias:** luôn đo sequential trước rồi parallel sau có thể làm một phía được hưởng warm cache.
- **Dead-code elimination:** nếu không quan sát/consume kết quả, JIT có thể tối ưu bỏ bớt phép tính.
- **Bản thân instrumentation:** println/logging trong `compute` làm sai lệch tỷ lệ thời gian.
- **Sample quá ít:** một lần đo không có độ phân tán và dễ dính outlier.
- **Fork/Join scheduling:** n khác nhau và CPU cores khác nhau cho overhead khác nhau.
- **Parallel interference:** nhiều benchmark chạy chung máy hoặc shared commonPool làm dữ liệu không ổn định.

Vì vậy phải kiểm tra correctness **trước**, đo nhiều lần, warm-up, sử dụng đầu vào đại diện và báo điều kiện đo. Cho microbenchmark JVM, ưu tiên **JMH của OpenJDK**.

## 30. Cách đọc speedup đúng

Gọi:

- `T_seq`: thời gian của thuật toán tuần tự.
- `T_par`: thời gian của thuật toán song song với cùng input/semantics.

Định nghĩa:

\[
\text{speedup} = \frac{T_{\text{seq}}}{T_{\text{par}}}
\]

- `speedup > 1`: phiên bản song song nhanh hơn **trong phép đo ấy**.
- `speedup = 1`: tương đương về thời gian đo.
- `speedup < 1`: phiên bản song song chậm hơn.
- `2.0×` nghĩa là `T_par` bằng một nửa `T_seq`, không phải "nhanh thêm 200%" theo mọi cách dùng ngôn ngữ.

Ví dụ số **minh họa**, không phải benchmark của bài:

| T_seq | T_par | Speedup | Kết luận |
| --- | --- | --- | --- |
| 100 ms | 50 ms | 2.0× | Parallel nhanh gấp đôi trong phép đo |
| 100 ms | 100 ms | 1.0× | Ngang nhau |
| 100 ms | 200 ms | 0.5× | Parallel chậm gấp đôi |

Đừng lấy số từ máy người khác làm performance guarantee. Điều quan trọng là đo dưới điều kiện thực tế và trả lời vì sao parallel nhanh/chậm với kích thước đó.

### 30.1. Amdahl's Law: phần tuần tự giới hạn speedup

Nếu tỷ lệ `s` của công việc bắt buộc tuần tự, và phần còn lại chạy trên `p` workers lý tưởng, giới hạn tham khảo:

\[
S(p) \leq \frac{1}{s + (1-s)/p}
\]

Ví dụ nếu 20% thời gian không thể song song hóa, ngay cả vô hạn workers cũng không vượt mức xấp xỉ 5× trong mô hình lý tưởng. Trong thực tế còn có overhead fork/join, synchronization, cache/memory bandwidth và cost combine, khiến speedup nhỏ hơn.

Không dùng Amdahl như công thức tiên đoán chính xác timing; nó chỉ giải thích vì sao thêm threads không bảo đảm tăng tốc tuyến tính.

## 31. Ví dụ 14 — Đo thăm dò có warm-up và median

Để quan sát ý tưởng, chương trình sau:

1. Tạo một input có seed cố định **ngoài vùng đo**.
2. Tạo một ForkJoinPool dùng lại nhiều lần.
3. Xác nhận kết quả tuần tự/song song khớp.
4. Warm-up cả hai implementation.
5. Thu 13 lượt đo, đảo thứ tự sequential/parallel theo lượt.
6. Lấy **median** thay vì coi một phép đo duy nhất là chân lý.
7. Báo `speedup = medianSeqNs / medianParNs`.

**Đây vẫn chỉ là đo thăm dò, không thay JMH.**

Tạo `TimingExplorationDemo.java`:

~~~java
import java.util.*;
import java.util.concurrent.*;

public class TimingExplorationDemo {
    static volatile long sink;

    static long sequential(int[] a) {
        long sum = 0;
        for (int x : a) sum += x;
        return sum;
    }

    static final class Task extends RecursiveTask<Long> {
        final int[] a;
        final int lo, hi, threshold;

        Task(int[] a, int lo, int hi, int t) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.threshold = t;
        }

        @Override
        protected Long compute() {
            int n = hi - lo;
            if (n <= threshold) {
                long s = 0;
                for (int i = lo; i < hi; i++) s += a[i];
                return s;
            }

            int mid = lo + n / 2;
            Task left = new Task(a, lo, mid, threshold);
            left.fork();

            long right = new Task(
                    a, mid, hi, threshold).compute();
            return right + left.join();
        }
    }

    static long parallel(int[] a, ForkJoinPool pool) {
        return pool.invoke(
                new Task(a, 0, a.length, 8192));
    }

    static long median(long[] a) {
        long[] copy = a.clone();
        Arrays.sort(copy);
        return copy[copy.length / 2];
    }

    public static void main(String[] args) {
        int[] a = new int[262144];
        SplittableRandom rnd = new SplittableRandom(245);

        for (int i = 0; i < a.length; i++) {
            a[i] = rnd.nextInt(-1000, 1001);
        }

        ForkJoinPool pool = new ForkJoinPool(
                Math.min(4,
                        Runtime.getRuntime()
                                .availableProcessors()));

        try {
            long expected = sequential(a);
            boolean correct = (expected == parallel(a, pool));

            for (int i = 0; i < 12; i++) {
                sink = sequential(a);
                sink = parallel(a, pool);
            }

            final int rounds = 13;
            long[] seq = new long[rounds];
            long[] par = new long[rounds];

            for (int i = 0; i < rounds; i++) {
                if ((i & 1) == 0) {
                    long t = System.nanoTime();
                    long s = sequential(a);
                    seq[i] = System.nanoTime() - t;
                    if (s != expected) {
                        throw new AssertionError(
                                "sequential changed");
                    }

                    t = System.nanoTime();
                    long p = parallel(a, pool);
                    par[i] = System.nanoTime() - t;
                    if (p != expected) {
                        throw new AssertionError(
                                "parallel mismatch");
                    }
                    sink = s ^ p;
                } else {
                    long t = System.nanoTime();
                    long p = parallel(a, pool);
                    par[i] = System.nanoTime() - t;
                    if (p != expected) {
                        throw new AssertionError(
                                "parallel mismatch");
                    }

                    t = System.nanoTime();
                    long s = sequential(a);
                    seq[i] = System.nanoTime() - t;
                    if (s != expected) {
                        throw new AssertionError(
                                "sequential changed");
                    }
                    sink = p ^ s;
                }
            }

            long seqMedian = median(seq);
            long parMedian = median(par);

            System.out.println("correct=" + correct);
            System.out.println("rounds=" + rounds);
            System.out.println("medianSequentialNs=" +
                    seqMedian);
            System.out.println("medianParallelNs=" +
                    parMedian);

            System.out.printf(Locale.ROOT,
                    "speedupSequentialOverParallel=%.3f%n",
                    parMedian > 0
                            ? (double) seqMedian / parMedian
                            : Double.NaN);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 TimingExplorationDemo.java
java TimingExplorationDemo
~~~

**Dạng stdout** (ba giá trị thời gian và speedup **khác nhau theo máy/lần chạy**):

~~~text
correct=true
rounds=13
medianSequentialNs=<số nanosecond đo được>
medianParallelNs=<số nanosecond đo được>
speedupSequentialOverParallel=<tỷ số đo được>
~~~

Các dấu ngoặc nhọn chỉ mô tả phần **giá trị biến thiên**, không phải output cố định của Java. Một lượt chạy thực tế đã cho `correct=true` và `rounds=13`; số timing không được xem là định mức hoặc tiêu chuẩn.

**Cảnh báo về benchmark này:** Việc dùng biến `volatile sink`, warm-up và median giúp nhìn thấy một số vấn đề, nhưng không kiểm soát đầy đủ JIT, dead-code elimination, measurement harness, fork JVMs, GC, interference, pinning, perf counters hoặc statistical significance. Khi cần báo cáo performance, dùng **JMH** và review code benchmark riêng.

## 32. JMH: chuẩn tốt hơn cho JVM microbenchmark

**JMH (Java Microbenchmark Harness)** là dự án OpenJDK giúp đo các method Java/JVM với warm-up, measurement iterations, forks, state setup và các công cụ giảm sai lệch. Đây là **công cụ hiện hành**, không phải phần API chuẩn của `java.base`; muốn chạy JMH phải thêm dependency và annotation processor của project JMH.

Các nguyên tắc:

1. Dùng **JMH fixture** với input tạo trong `@Setup`, **không** sinh random trong mỗi lời gọi benchmark trừ khi random là workload cần đo.
2. Tạo cả benchmark sequential và parallel nhận đầu vào tương đương.
3. Dùng `@Param` để quét size/threshold/parallelism, thay vì chọn một điểm.
4. Cấu hình `@Warmup`, `@Measurement`, `@Fork` và output mode phù hợp.
5. Trả kết quả hoặc dùng `Blackhole.consume(...)` để chống loại bỏ tính toán.
6. Với phép sort, chuẩn bị bản sao cho mỗi invocation theo lifecycle phù hợp, tránh lần sau đo mảng đã sorted.
7. Nếu dùng pool riêng, tạo ở state setup và shutdown ở teardown **ngoài đoạn đo**, trừ khi mục tiêu thật sự là đo cả chi phí tạo pool.
8. Chạy benchmark trên môi trường đủ ổn định, không coi một lượt là kết luận.
9. Đối chiếu correctness với test suite **riêng**, đừng cố thay unit test bằng JMH.
10. Report Java version, CPU cores, OS, heap/GC, data generation, benchmark mode, task threshold, score/error và số forks.

Nguồn chính thức: [OpenJDK JMH trên GitHub](https://github.com/openjdk/jmh) và [OpenJDK Code Tools](https://openjdk.org/projects/code-tools/jmh).

### 32.1. Mẫu setup JMH dành cho người đã dùng Maven

Theo hướng dẫn project JMH, có thể bootstrap một project benchmark riêng bằng Maven archetype. Các lệnh bên dưới **không phải lệnh javac cho 14 chương trình của bài** và cần Maven/JMH tải từ repositories.

~~~bash
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DgroupId=org.sample -DartifactId=forkjoin-bench -Dversion=1.0

cd forkjoin-bench
mvn clean verify
java -jar target/benchmarks.jar
~~~

Đây là quy trình **tham khảo**, không tuyên bố đã chạy Maven/JMH trong kiểm thử Java 17 ở bài này. Khi viết JMH classes, cần imports `org.openjdk.jmh.annotations.*` và dependency/annotation processing tương ứng. Không tự đoán version dependency hiện hành; dùng phiên bản JMH phù hợp được xác minh tại project chính thức.

### 32.2. Kết luận hiệu năng phải có điều kiện

Một báo cáo tốt không chỉ viết "parallel nhanh hơn 3 lần". Nó nên trình bày:

~~~text
Input shape:      int[] random, seeded, length = ...
Workload:         sum / count primes / sort / histogram
JDK / VM flags:   ...
OS / CPU:         ...
ForkJoinPool:     custom parallelism = ...
Threshold:        ...
Reference result: ...
Correctness:      all cases PASS
Benchmark:        JMH mode, warm-up, forks, iterations ...
Sequential score: ... (units + error)
Parallel score:   ... (units + error)
Speedup:          T_seq/T_par for comparable latency measurements
Limitations:      GC/cache/contention/CPU load/variance
~~~

Đây là **mẫu report**, các dấu ba chấm là những trường ứng dụng phải đo/điền từ JMH, không phải dữ liệu giả định.

## 33. Test tính đúng có thể tìm được race condition không?

Có thể tìm được **một số** race nhưng không bảo đảm không tồn tại race. Fork/Join thường an toàn hơn khi mỗi task:

- Đọc immutable input.
- Chỉ truy cập `[lo,hi)` của mình nếu có mutation.
- Trả partial result riêng thay vì ghi vào shared `int total`.
- Chờ child qua `join()` trước khi combine.
- Tránh dùng chung mutable `ArrayList`, `HashMap` và counters không đồng bộ.
- Không tạo dependency có chu kỳ.
- Không thay đổi input cùng lúc từ thread ngoài pool.
- Xử lý exception/cancellation có policy rõ.

Ví dụ sai:

~~~java
// Mã minh họa sai: nhiều worker ghi shared total không đồng bộ.
sharedTotal += partialSum;
~~~

Kết quả có thể **thỉnh thoảng** trùng baseline rồi lại sai trong một lần chạy khác. Đừng bắt đầu từ `Thread.sleep` để “chữa” race. Hãy thiết kế reduce với return values rồi join, hoặc dùng cấu trúc đồng bộ thích hợp khi nghiệp vụ thật sự cần shared state.

### 33.1. Tách lỗi thuật toán và lỗi lịch chạy

- Nếu kết quả sai **cùng một cách** bất kể parallelism, thường kiểm tra split/loop/combine.
- Nếu sai **không ổn định**, đặc biệt khi tăng threads, xem xét shared mutable state và memory visibility.
- Nếu chỉ khác với `double` khi grouping thay đổi, xem xét rounding và numerical semantics trước khi gán lỗi race.
- Nếu chỉ sai trên empty/singleton, kiểm tra base case.
- Nếu chỉ sai với length lẻ, kiểm tra mid/off-by-one.
- Nếu chỉ sai với MAX/MIN, kiểm tra overflow và sentinel.
- Nếu chỉ sai sau nhiều rounds benchmark, kiểm tra có sử dụng lại mảng **đã bị mutate** hay không.

## 34. Lựa chọn thuật toán để benchmark công bằng

Không nên đo một bản làm việc khác bản còn lại. Ví dụ:

| So sánh | Công bằng khi nào? |
| --- | --- |
| Vòng for sum vs RecursiveTask sum | Cùng input, cùng kiểu số, cùng overflow semantics |
| `Arrays.sort` vs `Arrays.parallelSort` | Hai mảng mới copy từ một input gốc, cùng comparator |
| Sequential histogram vs Fork/Join histogram | Cùng số bins và cách xử lý signed byte |
| Sequential transform vs RecursiveAction | Hai bản sao riêng, cùng phép biến đổi |
| Prime count loop vs RecursiveTask | Cùng miền [from,to), cùng primality semantics |
| Sequential stream vs parallel stream | Pipeline tương đương, stateless, associative |
| Double sum | Xác định loại equivalence trước: exact vs tolerance |
| Custom ForkJoinPool vs commonPool | Ghi nhận pool/parallelism khác nhau và workloads chia sẻ |

Một số lựa chọn optimization có thể làm thay semantics: approximation, bỏ phần tử, đổi algorithm từ exact sang probabilistic hoặc dùng integer arithmetic không cùng overflow policy. Nếu vậy, đó là **bài toán khác**, không nên tính speedup như hai triển khai tương đương mà không giải thích trade-off.

## 35. Những sai lầm thường gặp khi so sánh

| Sai lầm | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Chỉ so thời gian, không so kết quả | Song song có thể trả sai mà vẫn “nhanh” | Assertions trước benchmarking |
| Dùng một input bị mutate hai lần | Hai thuật toán nhận dữ liệu khác | Clone/input reset |
| Dùng `a==b` cho mảng | So tham chiếu, không so content | `Arrays.equals` |
| Chỉ so checksum/tổng cho sort | Có thể hoán vị sai mà tổng vẫn giống | So từng phần tử |
| Không test mảng rỗng | Dễ bỏ sót base case | Empty/singleton cases |
| Chỉ test mảng dài chẵn | Che off-by-one với odd mid | Test 3,7,31... |
| Không test âm/MAX/MIN | Có thể sai sentinel hoặc overflow | Boundary fixtures |
| Cùng bug trong oracle và parallel | False confidence | Oracle đơn giản/độc lập |
| Dùng `double==double` vô điều kiện | Grouping làm tròn khác | Định nghĩa numerical equivalence |
| Dùng tolerance quá lớn | Che sai nghiêm trọng | Domain-specific error budget |
| Bỏ qua NaN/Infinity/signed zero | Kết quả đặc biệt có semantics khác | Test special cases |
| Fork task nhưng quên join | Đọc kết quả khi chưa sẵn | Join/invokeAll đúng |
| Ghi chung `int total` | Data race | Reduce partial values |
| Gọi pool.invoke một lần rồi kết luận nhanh | JIT/GC/scheduling nhiễu | Warm-up/JMH |
| So sau khi in log trong leaf | Logging chi phối timing | Không log trong phép đo |
| Tạo pool cho mỗi task | Overhead không liên quan workload | Tái dùng pool |
| Sinh random trong vùng đo | Đo thêm random generator | Setup ngoài measurement |
| Chạy sequential luôn trước | Cache/order bias | JMH hoặc đảo thứ tự có kiểm soát |
| Không consume result | JIT có thể tối ưu bỏ tính toán | JMH Blackhole/return |
| Một seed duy nhất | Thiếu khả năng bắt edge cases | Matrix + nhiều seeds |
| Chọn threshold sau một lần đo | Overfit nhiễu | Sweep + thống kê |
| Dùng commonPool đang bị app khác tải | Không cùng điều kiện | Isolate/ghi nhận contention |
| Chỉ report speedup, không có đơn vị | Khó tái lập | Report mode, units, errors, hardware |
| Kết luận parallel luôn nhanh hơn | Overhead có thể cao | Benchmark mỗi workload |

## 36. Checklist trước khi công bố thuật toán song song tốt hơn

**Correctness**

1. Có oracle tuần tự đơn giản, độc lập?
2. Có dùng **cùng data** và cùng semantics?
3. Có test empty/singleton/odd/duplicates/negative/MAX/MIN?
4. Có kiểm tra tất cả phần tử/bin, không chỉ checksum?
5. Có verify input preservation hoặc mutation expected?
6. Có thử nhiều seeds, sizes và thresholds?
7. Có test overflow và giá trị không hợp lệ?
8. Có bảo đảm split ranges không chồng lấn và không thiếu?
9. Có xử lý exceptions từ leaf/child/root?
10. Có hiểu floating-point grouping không luôn exact?
11. Có test race với nhiều parallelism và repeated runs?
12. Có regression fixture khi tìm thấy một case sai?

**Performance**

13. Có cùng workload, cùng input shape và data layout?
14. Có tách generation/setup/clone/pool creation khỏi vùng đo khi phù hợp?
15. Có warm-up và nhiều phép đo/forks?
16. Có dùng JMH cho microbenchmark nghiêm túc?
17. Có consume kết quả để không bị dead-code elimination?
18. Có tránh logging, assertions và I/O trong timed compute?
19. Có kiểm soát CPU load và common pool contention?
20. Có ghi rõ heap/GC/JDK/OS/CPU/parallelism?
21. Có sweep threshold và số workers?
22. Có xét overhead combine, allocations, work stealing?
23. Có báo median/score và độ biến thiên, không chỉ một con số?
24. Có baseline tuần tự và speedup tính cùng đơn vị?
25. Có kết luận **cho workload đo** thay vì khái quát mọi ứng dụng?

## 37. Câu hỏi tự kiểm tra

**1.** Vì sao phải so tính đúng trước timing?  
**Đáp án:** Bản song song có thể sai nhưng nhanh; timing khi sai không có ý nghĩa.

**2.** Reference oracle tốt cho sum là gì?  
**Đáp án:** Vòng for đơn giản, độc lập với Fork/Join split tree.

**3.** Dùng `a==b` cho hai `int[]` có đúng không?  
**Đáp án:** Không; dùng `Arrays.equals`.

**4.** Muốn biết index khác đầu tiên dùng API nào?  
**Đáp án:** `Arrays.mismatch` (Java 9+).

**5.** Vì sao phải clone mảng trước sort comparison?  
**Đáp án:** Bởi sort thay input tại chỗ; hai bản phải nhận data ban đầu tương đương.

**6.** Phân hoạch [lo,hi) tại mid cần thỏa điều gì?  
**Đáp án:** [lo,mid) và [mid,hi) không giao nhau, hợp bằng đoạn cha, cùng bảo đảm tiến triển.

**7.** Vì sao kiểm tra n=7 có ích?  
**Đáp án:** Dữ liệu lẻ giúp bắt off-by-one ở split.

**8.** Threshold đổi có nên làm đổi tổng nguyên hợp lệ?  
**Đáp án:** Không; nếu đổi phải điều tra logic/overflow/race.

**9.** Một kết quả test bằng nhau có chứng minh không có race?  
**Đáp án:** Không.

**10.** Dùng `sharedTotal += partial` an toàn không?  
**Đáp án:** Không nếu nhiều workers ghi mà không đồng bộ.

**11.** Histogram nên kiểm tra gì ngoài tổng?  
**Đáp án:** Toàn bộ 256 bins và input length.

**12.** Maximum của mảng rỗng là 0 đúng không?  
**Đáp án:** Không; có thể dùng `OptionalInt.empty()`.

**13.** Vì sao tổng double song song có thể khác tuần tự?  
**Đáp án:** Thứ tự nhóm phép cộng khác, floating-point rounding không có tính kết hợp chính xác.

**14.** Dung sai 1.0 có dùng cho mọi double comparisons được không?  
**Đáp án:** Không; phải định nghĩa từ miền dữ liệu.

**15.** JMH là gì?  
**Đáp án:** Java Microbenchmark Harness của OpenJDK, hỗ trợ đo JVM microbenchmarks có kiểm soát hơn.

**16.** `System.nanoTime()` đo một lần có chứng minh speedup không?  
**Đáp án:** Không; bị ảnh hưởng bởi JIT, GC, warm-up, cache, scheduling...

**17.** Speedup tính thế nào?  
**Đáp án:** `T_seq / T_par` với hai thời gian tương đương.

**18.** Speedup 0.5× nghĩa gì?  
**Đáp án:** Bản song song mất thời gian gấp đôi bản tuần tự theo phép đo.

**19.** Có nên tạo ForkJoinPool trong mỗi compute?  
**Đáp án:** Không; nên quản lý pool theo vòng đời ứng dụng.

**20.** Parallel stream có bắt buộc nhanh hơn stream thường?  
**Đáp án:** Không.

**21.** `Arrays.parallelSort` có tự tạo song song cho mọi mảng nhỏ không?  
**Đáp án:** Không đảm bảo.

**22.** Overflow xử lý ra sao nếu cần tính chính xác?  
**Đáp án:** `Math.addExact` hoặc `BigInteger` theo yêu cầu; kiểm tra intermediate overflow.

**23.** Seed cố định có ích gì?  
**Đáp án:** Giúp tái hiện failure với cùng input generation.

**24.** Vì sao phải đo nhiều threshold?  
**Đáp án:** Chi phí task overhead và độ song song thay theo granularity.

**25.** Ba tiêu chí quan trọng nhất?  
**Đáp án:** **Cùng semantics và data → so kết quả đầy đủ → benchmark có phương pháp**.

## 38. Tài liệu chính thức và đọc thêm

- [Oracle Java SE 26 — ForkJoinPool](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work-stealing, invoke/submit, commonPool, parallelism và scheduling.
- [Oracle Java SE 26 — ForkJoinTask](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): fork/join/invokeAll, exception/cancellation, tránh blocking.
- [Oracle Java SE 26 — RecursiveTask](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/RecursiveTask.html): compute trả giá trị, divide-and-conquer patterns.
- [Oracle Java SE 26 — RecursiveAction](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/RecursiveAction.html): compute void, thao tác trên các ranges độc lập.
- [Oracle Java SE 26 — Arrays](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html): equals/mismatch/sort/parallelSort và parallelPrefix(double) caveat.
- [Oracle Java SE 26 — SplittableRandom](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/SplittableRandom.html): tạo input ngẫu nhiên có seed, không dùng làm nguồn bí mật bảo mật.
- [Oracle Java SE 26 — OptionalInt](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/OptionalInt.html): so sánh max với dữ liệu rỗng.
- [Oracle Java SE 26 — Math](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html): addExact/multiplyExact và overflow.
- [Oracle Java SE 26 — BigInteger](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigInteger.html): phép toán số nguyên không giới hạn độ dài thông thường.
- [Oracle Java SE 26 — Stream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): parallel reduction và side-effect-free pipeline.
- [Oracle Java SE 26 — IntStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html): asLongStream, sum và parallel stream.
- [Oracle Java SE 26 — Future](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html): get(timeout), cancellation và exception semantics.
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh): benchmark annotations, warm-up, measurement, JVM forks, Maven archetype.
- [Oracle Java SE 17 — ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): đối chiếu với API JDK 17 dùng trong các bài chạy thử.
- [Oracle Java SE 7 — ForkJoinPool](https://docs.oracle.com/javase/7/docs/api/java/util/concurrent/ForkJoinPool.html): API bắt nguồn từ Java 7, không thay cho Javadoc hiện hành.

**Tóm tắt:** Khi chuyển một thuật toán sang Fork/Join, đừng bắt đầu bằng việc đo milliseconds. Xây **oracle tuần tự đáng tin**, tạo **cùng input**, so **toàn bộ kết quả và side effects**, thử input rỗng/âm/lẻ/lớn, nhiều thresholds và seeds. Phân biệt **khác biệt số thực do grouping** với lỗi race/logic. Chỉ khi correctness đã đạt yêu cầu mới **benchmark** bằng phương pháp phù hợp (ưu tiên JMH cho microbenchmarks), báo speedup với **điều kiện và độ biến thiên** rõ ràng.