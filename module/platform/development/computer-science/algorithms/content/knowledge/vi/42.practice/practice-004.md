# Kết hợp sắp xếp, hai con trỏ và xử lý theo sự kiện

## Mục tiêu học tập

Ba kỹ thuật **sắp xếp (sorting)**, **hai con trỏ (two pointers)** và **xử lý theo sự kiện (event processing / sweep line)** thường kết hợp trong bài toán cặp phần tử, lịch thời gian, giao các khoảng và đếm đối tượng hoạt động đồng thời.

- Sorting tạo thứ tự để khai thác tính đơn điệu.
- Two pointers quét hai dãy có thứ tự mà không cần thử mọi cặp.
- Sweep line sắp các mốc thay đổi, cập nhật trạng thái khi đi qua từng sự kiện.

Bài học triển khai ba ví dụ: đếm cặp có tổng không vượt ngưỡng; giao của hai danh sách khoảng đã sắp xếp và không chồng lấn; tìm số khoảng hoạt động đồng thời lớn nhất. Chương trình Java 17+ ở cuối có lời giải tối ưu, oracle vét cạn độc lập, kiểm thử ngẫu nhiên tái lập và stdout xác định.

---

## 1. Chọn mô hình và quy ước trước khi viết thuật toán

Hãy xác định:

1. Đối tượng là số, cặp chỉ số, khoảng thời gian hay sự kiện?
2. Điều kiện là tổng ≤K hay <K? Khoảng là đóng [s,e] hay nửa mở [s,e)?
3. Đầu ra là số lượng, giá trị lớn nhất, danh sách nghiệm hay một witness cụ thể?
4. Input có thể rỗng, âm, trùng, không sort, hoặc có giá trị lớn tới đâu?

Quy ước khoảng rất quan trọng. Với khoảng nửa mở [s,e), thời điểm s được tính, thời điểm e không được tính. Vì thế hai khoảng [1,2) và [2,3) **không giao nhau**. Với khoảng đóng [1,2] và [2,3], chúng giao nhau tại 2.

Một comparator có tie-break không rõ có thể làm sai cả thuật toán dù phần quét đúng. Không dựa vào thứ tự tình cờ khi nhiều phần tử có cùng key.

### 1.1. Vì sao sort hữu ích?

Dãy chưa có thứ tự:

```text
[8, 1, 5, 2, 9]
```

Sau khi sort tăng:

```text
[1, 2, 5, 8, 9]
```

Khi dãy tăng, nếu tổng của phần tử nhỏ nhất A[i] với phần tử lớn nhất B[j] đã quá lớn, thì ghép B[j] với mọi phần tử A còn lại cũng không thể hợp lệ. Một phép so sánh loại được cả cột, thay vì thử từng cặp.

### 1.2. Độ phức tạp cơ bản

- Sort n phần tử: thường O(n log n).
- Quét một dãy: O(n).
- Quét hai dãy với hai con trỏ: O(n+m) nếu không phải sort.
- Tạo 2n sự kiện, sort và sweep: O(n log n).

Nếu input đã sort theo đúng khóa cần dùng, không sort lại.

---

## 2. Bài toán A: đếm cặp có tổng không vượt quá K

Cho hai mảng số nguyên A và B. Đếm số cặp **chỉ số** (i,j) sao cho:

\[
\boxed{A[i]+B[j]\le K}.
\]

Hai vị trí khác nhau có cùng giá trị vẫn là hai phần tử khác nhau. Vì thế cặp chỉ số được đếm riêng.

### 2.1. Ví dụ

```text
A = [1, 4, 2]
B = [3, 0, 5, 2]
K = 5
```

Sort hai mảng:

```text
A = [1, 2, 4]
B = [0, 2, 3, 5]
```

- Với A=1, B=0,2,3 hợp lệ: 3 cặp.
- Với A=2, B=0,2,3 hợp lệ: 3 cặp.
- Với A=4, chỉ B=0 hợp lệ: 1 cặp.

Kết quả là:

\[
\boxed{3+3+1=7}.
\]

### 2.2. Oracle vét cạn O(nm)

Thử trực tiếp tất cả cặp:

```text
count = 0
for i = 0..n-1:
    for j = 0..m-1:
        if A[i] + B[j] <= K:
            count++
return count
```

Cách này dễ chứng minh đúng, không phụ thuộc sort hay hai con trỏ, nên là oracle tốt cho input nhỏ.

### 2.3. Sort + two pointers

Sort A và B tăng dần. Đặt i=0 và j=m−1. Lặp khi i<n và j≥0.

Nếu:

\[
A[i]+B[j]\le K,
\]

thì do B tăng dần, mọi B[0..j] đều không lớn hơn B[j]. Tất cả j+1 phần tử ấy ghép với A[i] đều hợp lệ. Cộng j+1 vào count rồi tăng i.

Ngược lại, nếu:

\[
A[i]+B[j]>K,
\]

mọi phần tử A còn lại đều ≥A[i]. Vì vậy không phần tử A còn lại nào ghép với B[j] cho tổng ≤K. Bỏ cột j bằng cách giảm j.

### 2.4. Mã giả

```text
sort(A)
sort(B)
i = 0
j = m - 1
count = 0

while i < n and j >= 0:
    if A[i] + B[j] <= K:
        count += j + 1
        i++
    else:
        j--

return count
```

### 2.5. Invariant và chứng minh

Tại đầu mỗi vòng, miền cặp chưa quyết định là:

\[
A[i..n-1]\times B[0..j].
\]

- Nếu A[i]+B[j]≤K, toàn bộ hàng i trong miền này hợp lệ; cộng đúng j+1 cặp rồi bỏ hàng.
- Nếu tổng >K, toàn bộ cột j không hợp lệ; bỏ cột.
- Không cặp nào được đếm hai lần vì mỗi hàng A[i] chỉ xử lý một lần.
- Không cặp hợp lệ nào bị bỏ vì mỗi lần loại một hàng/cột đều có chứng minh.

Mỗi vòng tăng i hoặc giảm j, nên có tối đa n+m bước.

### 2.6. Độ phức tạp và số học

Sort hai mảng tốn O(n log n + m log m); quét tốn O(n+m). Bộ nhớ phụ O(n+m) cho hai bản sao đã sort.

Nếu phần tử là int, phải ép sang long **trước phép cộng**:

```java
long sum = (long) a[i] + b[j];
```

Viết long sum = a[i] + b[j] vẫn có thể tràn int trước khi gán. Với dữ liệu long có nguy cơ vượt giới hạn, dùng Math.addExact hoặc BigInteger theo đặc tả.

Biến thể tổng <K chỉ đổi phép so sánh. Đếm cặp giá trị phân biệt là bài khác với đếm cặp chỉ số, cần xử lý duplicate riêng.

---

## 3. Bài toán B: giao của hai danh sách khoảng đã sort

Mỗi khoảng là nửa mở [start,end), start<end. Trong **từng danh sách**, các khoảng đã sort theo start và không chồng lấn; có thể chạm nhau ở biên.

Ví dụ:

```text
A = [[0,3), [5,8), [10,12)]
B = [[1,2), [2,6), [7,11)]
```

Ta muốn liệt kê mọi phần giao không rỗng giữa một khoảng của A và một khoảng của B.

### 3.1. Giao của hai khoảng

Với X=[a_s,a_e), Y=[b_s,b_e):

\[
lo=\max(a_s,b_s),\qquad hi=\min(a_e,b_e).
\]

Giao không rỗng khi:

\[
\boxed{lo<hi}.
\]

Kết quả ví dụ:

```text
[[1,2), [2,3), [5,6), [7,8), [10,11)]
```

Hai giao [1,2) và [2,3) chạm nhau nhưng vẫn là hai phần giao riêng, không có phần tử chung tại 2.

### 3.2. Oracle vét cạn

Với mỗi khoảng A[i], thử tất cả B[j], tính max(start), min(end), thêm giao nếu lo<hi. Oracle này O(nm), không dựa vào thứ tự hay quyết định bỏ khoảng của lời giải hai con trỏ.

### 3.3. Two pointers O(n+m)

Đặt i và j ở đầu hai danh sách. Mỗi vòng:

1. Tính giao của A[i] và B[j].
2. Nếu lo<hi, thêm phần giao.
3. Lưu endA=A[i].end và endB=B[j].end.
4. Nếu endA≤endB, tăng i.
5. Nếu endB≤endA, tăng j.

Nếu end bằng nhau, cả hai con trỏ cùng tăng.

### 3.4. Vì sao bỏ khoảng kết thúc sớm là an toàn?

Giả sử endA≤endB. Do B đã sort và không chồng lấn:

\[
B[j+1].start\ge B[j].end.
\]

Suy ra:

\[
A[i].end\le B[j].end\le B[j+1].start.
\]

A[i] không thể giao với B[j+1] hoặc khoảng B nào về sau. Vì vậy bỏ A[i] là an toàn. Lập luận đối xứng nếu endB≤endA.

Mỗi vòng tăng ít nhất một con trỏ; tổng số bước O(n+m), ngoài chi phí tạo k kết quả là O(k).

### 3.5. Precondition quan trọng

Two pointers ở đây yêu cầu mỗi danh sách **đã sort và không chồng lấn nội bộ**. Nếu danh sách có khoảng lồng nhau, việc bỏ khoảng kết thúc sớm có thể bỏ mất giao với khoảng về sau. Khi ấy cần merge/chuẩn hóa trước hoặc dùng thuật toán sweep phù hợp.

Mã Java kiểm tra precondition và từ chối danh sách sai thay vì trả kết quả thiếu.

---

## 4. Bài toán C: maximum overlap bằng event sweep

Cho n khoảng nửa mở [start,end), start<end. Tìm số khoảng hoạt động đồng thời lớn nhất.

Ứng dụng: số phòng họp tối thiểu, kết nối đồng thời, job đang chạy, nhân viên đang trực hoặc xe đang thuê.

### 4.1. Chuyển khoảng thành event

Mỗi khoảng [s,e) tạo:

- Event (s,+1): một khoảng bắt đầu.
- Event (e,−1): một khoảng kết thúc.

Sort event theo time. Khi quét, cập nhật active += delta. Sau mỗi START, cập nhật best=max(best,active).

### 4.2. Tie-order cho khoảng nửa mở

Tại đúng thời điểm e, khoảng [s,e) đã kết thúc. Vì vậy nếu một khoảng kết thúc tại t và khoảng khác bắt đầu tại t, chúng không đồng thời.

**Cùng timestamp phải xử lý END trước START.**

Trong mã, delta của END là −1 và delta của START là +1. Sort time tăng dần, rồi delta tăng dần sẽ đặt −1 trước +1.

Ví dụ:

```text
[0,2)
[2,4)
```

Maximum overlap là 1, không phải 2.

### 4.3. Ví dụ

```text
[1,4)
[2,5)
[4,7)
[3,4)
[7,9)
```

Tại t=1 active=1; t=2 active=2; t=3 active=3. Tại t=4, hai END được xử lý trước START: active từ 3 xuống 1 rồi lên 2. Cực đại vẫn là:

\[
\boxed{3}.
\]

### 4.4. Chứng minh

Giữa hai timestamp, không có khoảng bắt đầu hoặc kết thúc nên active không đổi. Tại một timestamp, với quy ước nửa mở, ta loại tất cả khoảng kết thúc trước rồi thêm các khoảng bắt đầu. Sau START, active chính là số khoảng chứa thời điểm đó. Active chỉ tăng ở START, nên cực đại mới chỉ có thể xuất hiện sau một START. Quét tất cả event vì vậy tìm được maximum.

Tạo 2n event O(n), sort O(n log n), sweep O(n); tổng O(n log n) thời gian và O(n) bộ nhớ.

### 4.5. Nếu dùng khoảng đóng [s,e]

Với khoảng đóng, [1,2] và [2,3] giao nhau tại 2. Tie-order phải đổi thành **START trước END**, đồng thời cập nhật peak trong pha START trước khi trừ END. Không trộn hai quy ước.

Khoảng rỗng start==end bị từ chối trong bài này.

---

## 5. Hai con trỏ và sweep line khác nhau thế nào?

**Two pointers** duy trì hai vị trí hiện tại trong hai dãy đã sort. Mỗi bước so sánh hai đối tượng rồi loại một phía dựa trên tính đơn điệu.

**Sweep line** duy trì một trạng thái tổng hợp trên trục thời gian/tọa độ. Mỗi đối tượng đóng góp event tại các mốc thay đổi.

Một bài maximum overlap có thể viết bằng event list hoặc hai danh sách start/end đã sort và hai con trỏ. Event list linh hoạt hơn khi có nhiều loại event hoặc payload; hai mảng riêng có thể tiết kiệm đối tượng event.

Với sweep line phức tạp, trạng thái active có thể cần Fenwick tree, segment tree, balanced BST, priority queue hoặc interval tree. Sweep line xác định thứ tự sự kiện; cấu trúc phụ hỗ trợ truy vấn trạng thái.

### 5.1. Coordinate compression

Nếu tọa độ rất lớn nhưng chỉ có ít mốc, sort các tọa độ xuất hiện và ánh xạ về chỉ số 0..k−1. Thứ tự được bảo toàn:

\[
x<y\iff index(x)<index(y).
\]

Kết hợp compression với Fenwick/segment tree hữu ích khi sweep cần truy vấn độ phủ hoặc số sự kiện trên đoạn.

---

## 6. Comparator và lỗi số học

Không viết comparator bằng phép trừ:

```java
// Nguy cơ overflow:
(x, y) -> x.end - y.end
```

Dùng Integer.compare hoặc Comparator.comparingInt; với long dùng Comparator.comparingLong. Nếu cần tie-break, nối comparator theo đúng thứ tự ưu tiên.

Với pair counting, cast trước khi cộng hai int. Với active count, bảo đảm số khoảng không vượt miền int; nếu dùng trọng số lớn, dùng long và kiểm tra overflow.

---

## 7. Java 17+: chương trình tổng hợp chạy độc lập

Tệp: **SortTwoPointersSweepDemo.java**.

Chương trình có ba lời giải tối ưu:

- countPairsAtMost: sort hai bản sao mảng rồi đếm cặp bằng two pointers.
- intersections: two pointers trên hai danh sách khoảng đã sort và không chồng lấn.
- maximumOverlapHalfOpen: sort event theo time, END trước START, rồi quét active.

Có ba oracle độc lập:

- brutePairCount: thử tất cả cặp chỉ số.
- bruteIntersections: thử mọi cặp khoảng.
- bruteMaximumOverlap: đếm trực tiếp số khoảng chứa từng thời điểm bắt đầu.

Kiểm thử dùng seed cố định: 10.000 ca pair count, 5.000 ca maximum overlap, 5.000 cặp danh sách intersections.

### 7.1. Mã nguồn hoàn chỉnh

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.StringJoiner;
import java.util.SplittableRandom;

public final class SortTwoPointersSweepDemo {

    private static final long SEED = 20261110L;

    public record Interval(long start, long end) {
        public Interval {
            if (start >= end) {
                throw new IllegalArgumentException(
                        "Expected start < end for [start,end)");
            }
        }
    }

    private record Event(long time, int delta) {
    }

    // Count index pairs, not distinct value pairs.
    // Inputs may be unsorted; sort independent copies.
    public static long countPairsAtMost(
            int[] left, int[] right, long limit) {

        if (left == null || right == null) {
            throw new IllegalArgumentException(
                    "Input arrays must not be null");
        }

        int[] a = left.clone();
        int[] b = right.clone();
        Arrays.sort(a);
        Arrays.sort(b);

        int i = 0;
        int j = b.length - 1;
        long count = 0L;

        while (i < a.length && j >= 0) {
            long sum = (long) a[i] + b[j];

            if (sum <= limit) {
                count = Math.addExact(count, (long) j + 1L);
                i++;
            } else {
                j--;
            }
        }

        return count;
    }

    // Independent O(n*m) oracle.
    public static long brutePairCount(
            int[] left, int[] right, long limit) {

        if (left == null || right == null) {
            throw new IllegalArgumentException(
                    "Input arrays must not be null");
        }

        long count = 0L;
        for (int x : left) {
            for (int y : right) {
                if ((long) x + y <= limit) {
                    count = Math.addExact(count, 1L);
                }
            }
        }
        return count;
    }

    private static void validateIntervals(Interval[] intervals) {
        if (intervals == null) {
            throw new IllegalArgumentException(
                    "Intervals must not be null");
        }
        for (Interval interval : intervals) {
            if (interval == null) {
                throw new IllegalArgumentException("Null interval");
            }
        }
    }

    // Each list must already be sorted and internally disjoint.
    private static void validateDisjointSorted(
            List<Interval> intervals) {

        if (intervals == null) {
            throw new IllegalArgumentException(
                    "Interval list must not be null");
        }

        boolean first = true;
        long previousEnd = 0L;

        for (Interval current : intervals) {
            if (current == null) {
                throw new IllegalArgumentException("Null interval");
            }
            if (!first && current.start() < previousEnd) {
                throw new IllegalArgumentException(
                        "Intervals must be sorted and disjoint");
            }
            previousEnd = current.end();
            first = false;
        }
    }

    // O(n+m) after both lists are sorted and disjoint.
    public static List<Interval> intersections(
            List<Interval> left, List<Interval> right) {

        validateDisjointSorted(left);
        validateDisjointSorted(right);

        List<Interval> result = new ArrayList<>();
        int i = 0;
        int j = 0;

        while (i < left.size() && j < right.size()) {
            Interval a = left.get(i);
            Interval b = right.get(j);

            long lo = Math.max(a.start(), b.start());
            long hi = Math.min(a.end(), b.end());

            if (lo < hi) {
                result.add(new Interval(lo, hi));
            }

            long endA = a.end();
            long endB = b.end();

            if (endA <= endB) {
                i++;
            }
            if (endB <= endA) {
                j++;
            }
        }

        return result;
    }

    // Independent O(n*m) pairwise oracle.
    public static List<Interval> bruteIntersections(
            List<Interval> left, List<Interval> right) {

        validateDisjointSorted(left);
        validateDisjointSorted(right);

        List<Interval> result = new ArrayList<>();

        for (Interval a : left) {
            for (Interval b : right) {
                long lo = Math.max(a.start(), b.start());
                long hi = Math.min(a.end(), b.end());
                if (lo < hi) {
                    result.add(new Interval(lo, hi));
                }
            }
        }

        result.sort(
                Comparator.comparingLong(Interval::start)
                        .thenComparingLong(Interval::end));
        return result;
    }

    // Maximum simultaneous overlap for half-open intervals.
    // At equal times, END (-1) precedes START (+1).
    public static int maximumOverlapHalfOpen(
            Interval[] intervals) {

        validateIntervals(intervals);

        List<Event> events = new ArrayList<>();
        for (Interval interval : intervals) {
            events.add(new Event(interval.start(), +1));
            events.add(new Event(interval.end(), -1));
        }

        events.sort(
                Comparator.comparingLong(Event::time)
                        .thenComparingInt(Event::delta));

        int active = 0;
        int best = 0;

        for (Event event : events) {
            active += event.delta();

            if (active < 0) {
                throw new IllegalStateException(
                        "Active count became negative");
            }
            if (event.delta() > 0) {
                best = Math.max(best, active);
            }
        }

        return best;
    }

    // Independent oracle: check all interval start times.
    public static int bruteMaximumOverlap(
            Interval[] intervals) {

        validateIntervals(intervals);
        int best = 0;

        for (Interval candidate : intervals) {
            long time = candidate.start();
            int active = 0;

            for (Interval interval : intervals) {
                if (interval.start() <= time
                        && time < interval.end()) {
                    active++;
                }
            }
            best = Math.max(best, active);
        }

        return best;
    }

    private static String formatIntervals(
            List<Interval> intervals) {

        StringJoiner joiner =
                new StringJoiner(", ", "[", "]");

        for (Interval x : intervals) {
            joiner.add(
                    "[" + x.start() + "," + x.end() + ")");
        }
        return joiner.toString();
    }

    private static void verifyPairs(
            int[] a, int[] b, long limit, String context) {

        long expected = brutePairCount(a, b, limit);
        long actual = countPairsAtMost(a, b, limit);

        if (expected != actual) {
            throw new AssertionError(
                    context
                    + " A=" + Arrays.toString(a)
                    + " B=" + Arrays.toString(b)
                    + " K=" + limit
                    + " expected=" + expected
                    + " actual=" + actual);
        }
    }

    private static void verifyOverlap(
            Interval[] intervals, String context) {

        int expected = bruteMaximumOverlap(intervals);
        int actual = maximumOverlapHalfOpen(intervals);

        if (expected != actual) {
            throw new AssertionError(
                    context
                    + " intervals=" + Arrays.toString(intervals)
                    + " expected=" + expected
                    + " actual=" + actual);
        }
    }

    private static void verifyIntersections(
            List<Interval> a, List<Interval> b,
            String context) {

        List<Interval> expected = bruteIntersections(a, b);
        List<Interval> actual = intersections(a, b);

        if (!expected.equals(actual)) {
            throw new AssertionError(
                    context + " A=" + a + " B=" + b
                    + " expected=" + expected
                    + " actual=" + actual);
        }
    }

    private static long randomPairTests(
            SplittableRandom random, int trials) {

        for (int t = 0; t < trials; t++) {
            int n = random.nextInt(0, 13);
            int m = random.nextInt(0, 13);
            int[] a = new int[n];
            int[] b = new int[m];

            for (int i = 0; i < n; i++) {
                a[i] = random.nextInt(-10, 11);
            }
            for (int j = 0; j < m; j++) {
                b[j] = random.nextInt(-10, 11);
            }

            long limit = random.nextInt(-15, 16);
            verifyPairs(a, b, limit,
                    "seed=" + SEED + " pairTrial=" + t);
        }

        return trials;
    }

    private static long randomOverlapTests(
            SplittableRandom random, int trials) {

        for (int t = 0; t < trials; t++) {
            int n = random.nextInt(0, 13);
            Interval[] intervals = new Interval[n];

            for (int i = 0; i < n; i++) {
                long start = random.nextInt(-5, 11);
                long end = start + random.nextInt(1, 8);
                intervals[i] = new Interval(start, end);
            }

            verifyOverlap(intervals,
                    "seed=" + SEED + " overlapTrial=" + t);
        }

        return trials;
    }

    // Generate sorted, internally disjoint intervals.
    private static List<Interval> randomDisjointList(
            SplittableRandom random) {

        int n = random.nextInt(0, 9);
        List<Interval> result = new ArrayList<>();
        long cursor = random.nextInt(-10, 1);

        for (int i = 0; i < n; i++) {
            cursor += random.nextInt(0, 4);
            long start = cursor;
            long end = start + random.nextInt(1, 5);
            result.add(new Interval(start, end));
            cursor = end;
        }

        return result;
    }

    private static long randomIntersectionTests(
            SplittableRandom random, int trials) {

        for (int t = 0; t < trials; t++) {
            List<Interval> a = randomDisjointList(random);
            List<Interval> b = randomDisjointList(random);
            verifyIntersections(a, b,
                    "seed=" + SEED + " intersectionTrial=" + t);
        }

        return trials;
    }

    public static void main(String[] args) {
        int[] a = {1, 4, 2};
        int[] b = {3, 0, 5, 2};

        System.out.println(
                "Pair count <= 5: "
                + countPairsAtMost(a, b, 5));

        Interval[] meetings = {
                new Interval(1, 4),
                new Interval(2, 5),
                new Interval(4, 7),
                new Interval(3, 4),
                new Interval(7, 9)
        };

        System.out.println(
                "Maximum concurrent half-open intervals: "
                + maximumOverlapHalfOpen(meetings));

        Interval[] touching = {
                new Interval(0, 2),
                new Interval(2, 4)
        };

        System.out.println(
                "Touching intervals maximum: "
                + maximumOverlapHalfOpen(touching));

        List<Interval> left = List.of(
                new Interval(0, 3),
                new Interval(5, 8),
                new Interval(10, 12));

        List<Interval> right = List.of(
                new Interval(1, 2),
                new Interval(2, 6),
                new Interval(7, 11));

        System.out.println(
                "Intersections: "
                + formatIntervals(intersections(left, right)));

        SplittableRandom random =
                new SplittableRandom(SEED);

        System.out.println(
                "Random pair-count cases: "
                + randomPairTests(random, 10_000) + " PASS");

        System.out.println(
                "Random overlap cases: "
                + randomOverlapTests(random, 5_000) + " PASS");

        System.out.println(
                "Random intersection cases: "
                + randomIntersectionTests(random, 5_000)
                + " PASS");

        System.out.println(
                "Empty pair count: "
                + countPairsAtMost(
                        new int[0], new int[] {1, 2}, 5));

        System.out.println(
                "Empty overlap: "
                + maximumOverlapHalfOpen(new Interval[0]));

        boolean invalidIntervalRejected = false;
        try {
            new Interval(2, 2);
        } catch (IllegalArgumentException ex) {
            invalidIntervalRejected = true;
        }

        System.out.println(
                "Invalid interval rejected: "
                + invalidIntervalRejected);

        boolean invalidListRejected = false;
        try {
            intersections(
                    List.of(
                            new Interval(3, 4),
                            new Interval(0, 1)),
                    List.of());
        } catch (IllegalArgumentException ex) {
            invalidListRejected = true;
        }

        System.out.println(
                "Invalid disjoint-list order rejected: "
                + invalidListRejected);
    }
}
```

### 7.2. Biên dịch và chạy

Yêu cầu JDK 17 trở lên:

```bash
javac SortTwoPointersSweepDemo.java
java SortTwoPointersSweepDemo
```

**Stdout kỳ vọng:**

```text
Pair count <= 5: 7
Maximum concurrent half-open intervals: 3
Touching intervals maximum: 1
Intersections: [[1,2), [2,3), [5,6), [7,8), [10,11)]
Random pair-count cases: 10000 PASS
Random overlap cases: 5000 PASS
Random intersection cases: 5000 PASS
Empty pair count: 0
Empty overlap: 0
Invalid interval rejected: true
Invalid disjoint-list order rejected: true
```

### 7.3. Giải thích các kiểm thử

- Pair count clone rồi sort hai mảng; oracle lặp mọi cặp trực tiếp. Duplicate được tính theo chỉ số.
- Intersections yêu cầu hai danh sách sort và disjoint; oracle thử mọi cặp khoảng, sau đó sort output.
- Maximum overlap dùng event comparator cho lời giải tối ưu; oracle đếm trực tiếp số khoảng chứa từng start time.
- Hai khoảng chạm biên [0,2),[2,4) có maximum overlap 1.
- Input rỗng cho pair count và overlap trả 0.
- Khoảng start==end và danh sách không đúng thứ tự bị từ chối.

Với khoảng nửa mở, active chỉ tăng tại start và giảm tại end. Một maximum dương xuất hiện ngay sau một start, nên oracle chỉ cần thử các thời điểm start. Oracle này không dùng event list hay comparator của lời giải sweep.

Seed cố định giúp tái lập chuỗi input. Khi mismatch, vẫn nên lưu input cụ thể và số thứ tự test, vì generator có thể thay đổi trong tương lai.

---

## 8. Kiểm thử biên và mở rộng

### 8.1. Pair counting

Nên thử:

| A | B | K | Kết quả |
| --- | --- | ---: | ---: |
| [] | [1] | 5 | 0 |
| [1] | [] | 5 | 0 |
| [1] | [2] | 3 | 1 |
| [1,1] | [2,2] | 3 | 4 |
| [-3,0,5] | [-2,2] | 0 | 3 |
| [Integer.MIN_VALUE] | [Integer.MAX_VALUE] | -1 | 1 |

Ca cuối phát hiện việc cộng int trước khi cast sang long.

### 8.2. Intersections

Thử hai danh sách rỗng, một danh sách rỗng, hai khoảng chỉ chạm biên, khoảng chứa khoảng khác, thời gian âm, khoảng trùng và input không sort/overlap nội bộ.

### 8.3. Maximum overlap

Thử không có khoảng, một khoảng, các khoảng rời nhau, cùng bắt đầu, cùng kết thúc, chạm biên, lồng nhau, thời gian âm và start==end.

### 8.4. Các biến thể

- Đếm cặp có tổng trong [L,R]: count(sum≤R) trừ count(sum<L). Cẩn thận L−1 có thể tràn nếu L=Long.MIN_VALUE.
- Đếm cặp có hiệu không quá K: sort một mảng, dùng hai con trỏ với invariant phù hợp.
- Merge hai dãy sort: chọn phần tử nhỏ hơn ở đầu hai dãy rồi tăng con trỏ tương ứng.
- Meeting rooms: sort theo start và dùng min-heap (end,roomId) để tái sử dụng phòng khi end≤start.
- Sweep line hình học: sự kiện theo x, cấu trúc phụ duy trì trạng thái theo y.
- Event simulation: priority queue lấy event sớm nhất; cùng timestamp cần quy tắc thứ tự rõ ràng.

### 8.5. Khi nào cần cấu trúc dữ liệu phụ?

Nếu trạng thái active chỉ là số lượng, một biến đếm là đủ. Nếu cần truy vấn độ phủ theo đoạn, số đối tượng theo tọa độ hoặc giá trị lớn nhất trên miền đang hoạt động, có thể dùng Fenwick tree, segment tree, balanced BST, priority queue hoặc interval tree.

---

## 9. Lỗi thường gặp

1. Dùng two pointers trên dãy chưa sort mà không có chứng minh tính đơn điệu.
2. Sort rồi quên chỉ số gốc nếu output cần vị trí ban đầu.
3. Dùng phép trừ trong comparator, có thể overflow.
4. Không có tie-break khi cùng key.
5. Cộng hai int trước khi ép sang long.
6. Nhầm cặp chỉ số với cặp giá trị phân biệt.
7. Cộng j thay vì j+1, bỏ sót B[0].
8. Khi tổng quá lớn, tăng i thay vì giảm j.
9. Không xử lý mảng rỗng.
10. Dùng hai con trỏ giao khoảng trên danh sách chồng lấn.
11. Tăng sai con trỏ trong interval intersection.
12. Đọc endA sau khi đã tăng i, vô tình so khoảng kế tiếp.
13. Không tăng cả hai con trỏ khi end bằng nhau.
14. Nhầm khoảng đóng [s,e] với nửa mở [s,e).
15. Xử lý START trước END cho khoảng nửa mở, tạo peak giả.
16. Xử lý END trước START cho khoảng đóng, bỏ peak tại điểm chung.
17. Cập nhật max trước khi thêm START.
18. Quên trừ active tại END.
19. Event delta không nhất quán khiến active âm.
20. Không tie-break sự kiện cùng timestamp.
21. Duyệt mọi đơn vị thời gian thay vì chỉ các mốc event.
22. Dùng start==end mà không định nghĩa khoảng rỗng.
23. Sort input tại chỗ dù caller cần giữ thứ tự.
24. Oracle dùng cùng comparator/logic với fast.
25. Chỉ test số dương, bỏ số âm và ngưỡng âm.
26. Không test duplicate.
27. Không test khoảng chạm biên.
28. Không test nhiều event cùng thời điểm.
29. Chỉ test khoảng không giao nhau, bỏ khoảng lồng nhau.
30. Sinh danh sách interval sai precondition nhưng vẫn gọi two pointers.
31. Không kiểm tra tính hợp lệ của output giao.
32. Random không seed khiến mismatch khó tái hiện.
33. Không lưu input cụ thể khi test thất bại.
34. Dùng sweep line cho bài mà hai con trỏ đã đủ.
35. Dùng two pointers cho trạng thái động làm mất invariant.
36. Tuyên bố O(n) nhưng bỏ qua chi phí sort.
37. Không kiểm tra overflow của count/active.
38. Nhầm maximum overlap với số phòng đã cấp mà không chứng minh.
39. Không quy định thứ tự event cùng timestamp.
40. Không nêu output khi input rỗng hoặc không có giao.

---

## 10. Bài tập tự kiểm tra

### Bài 1
Vì sao sorting có thể giúp giảm độ phức tạp từ O(nm) xuống O(n log n + m log m)?

### Bài 2
Trong bài đếm cặp, vì sao khi A[i]+B[j]≤K ta cộng j+1?

### Bài 3
Khi tổng A[i]+B[j]>K, tại sao phải giảm j?

### Bài 4
Với A=[1,2,4], B=[0,2,3,5], K=5, có bao nhiêu cặp chỉ số?

### Bài 5
Vì sao cần ép sang long trước khi cộng hai int?

### Bài 6
Nếu muốn đếm cặp có tổng <K, cần đổi điều kiện nào?

### Bài 7
Hai dãy đã sort, số bước quét tối đa là bao nhiêu?

### Bài 8
Hai khoảng [1,2) và [2,3) có giao không?

### Bài 9
Công thức phần giao của [a_s,a_e) và [b_s,b_e)?

### Bài 10
Khi nào giao hai khoảng không rỗng?

### Bài 11
Vì sao two pointers giao interval cần danh sách sorted và disjoint?

### Bài 12
Nếu A[i].end < B[j].end, con trỏ nào tăng?

### Bài 13
Nếu hai end bằng nhau, con trỏ nào tăng?

### Bài 14
Mỗi con trỏ tăng tối đa bao nhiêu lần trong intersections?

### Bài 15
Với khoảng [s,e), tạo những event nào?

### Bài 16
Tại cùng timestamp của khoảng nửa mở, END hay START xử lý trước?

### Bài 17
Vì sao [0,2) và [2,4) có maximum overlap 1?

### Bài 18
Với [1,4),[2,5),[4,7),[3,4),[7,9), maximum overlap là bao nhiêu?

### Bài 19
Vì sao maximum overlap nửa mở đạt tại một start time?

### Bài 20
Độ phức tạp event sort + sweep là gì?

### Bài 21
Nếu dùng khoảng đóng [s,e], tie-order đổi ra sao?

### Bài 22
Vì sao comparator x.end-y.end có thể sai?

### Bài 23
Tại sao lưu endA/endB trước khi tăng con trỏ?

### Bài 24
Oracle pair count độc lập với two pointers ở điểm nào?

### Bài 25
Oracle maximum overlap đếm trực tiếp tại những thời điểm nào?

### Bài 26
Danh sách interval không sort có thể gọi trực tiếp two pointers không?

### Bài 27
Nếu các khoảng trong một danh sách chồng lấn, cần làm gì?

### Bài 28
Coordinate compression bảo toàn thuộc tính nào?

### Bài 29
Khi nào sweep line cần cấu trúc dữ liệu phụ?

### Bài 30
Khi nào event list hữu ích hơn hai mảng start/end?

### Bài 31
Vì sao duplicate trong pair count vẫn được tính riêng?

### Bài 32
Nếu đề yêu cầu cặp giá trị phân biệt, có dùng ngay count index pairs không?

### Bài 33
Vì sao test interval cần ca chạm biên?

### Bài 34
Nêu phản ví dụ cho greedy chọn khoảng theo earliest start.

### Bài 35
Vì sao random test cần seed cố định?

### Bài 36
Nếu oracle và fast cùng dùng comparator sai, test có thể PASS giả không?

### Bài 37
Hai khoảng chạm biên nửa mở có cần cùng phòng không?

### Bài 38
Với n=0 interval, maximum overlap là bao nhiêu?

### Bài 39
Nếu END làm active âm, nên làm gì?

### Bài 40
Phân biệt trạng thái mà two pointers và sweep line duy trì.

### Đáp án gợi ý

1. Sort tạo thứ tự đơn điệu; mỗi bước loại một hàng/cột thay vì thử mọi cặp.
2. Vì mọi B[0..j]≤B[j] đều hợp lệ với A[i].
3. B[j] quá lớn cho A[i] và mọi A còn lại lớn hơn.
4. 7.
5. Nếu cộng trước trong int, overflow xảy ra trước phép gán.
6. Đổi <=K thành <K.
7. Tối đa n+m lần tăng con trỏ.
8. Không, chúng chỉ chạm biên.
9. [max(a_s,b_s), min(a_e,b_e)).
10. Khi max(start)<min(end).
11. Chứng minh bỏ khoảng kết thúc sớm dựa vào thứ tự và tính không chồng lấn.
12. Tăng i.
13. Tăng cả i và j.
14. i tối đa n lần, j tối đa m lần.
15. (s,+1) và (e,-1).
16. END trước START.
17. Tại t=2 khoảng đầu đã hết trước khi khoảng sau bắt đầu.
18. 3.
19. active chỉ tăng tại start, còn end chỉ giảm.
20. O(n log n).
21. START trước END và cập nhật peak trong pha START.
22. Phép trừ int có thể overflow.
23. Tránh đọc nhầm end của khoảng mới sau khi tăng i.
24. Oracle thử mọi cặp trực tiếp, không sort hay loại hàng/cột.
25. Tại start của từng khoảng.
26. Không, phải sort hoặc từ chối theo contract.
27. Merge/chuẩn hóa trước hoặc dùng sweep khác.
28. Thứ tự <, =, > của tọa độ.
29. Khi active cần truy vấn/cập nhật phức tạp hơn một biến đếm.
30. Khi event có nhiều loại, payload hoặc tie-order.
31. Đặc tả đếm cặp chỉ số nên hai vị trí là hai cặp khác nhau.
32. Không, cần xử lý duplicate theo yêu cầu.
33. Để kiểm tra đúng quy tắc < và <=.
34. [0,10),[1,2),[2,3),[3,4); earliest start chỉ lấy một, optimum là ba.
35. Để tái hiện input và mismatch.
36. Có; hai triển khai cùng lỗi vẫn khớp.
37. Không; có thể tái sử dụng phòng.
38. 0.
39. Kiểm tra event, tie-order và input; báo lỗi invariant thay vì tiếp tục.
40. Two pointers duy trì hai vị trí trong các dãy; sweep line duy trì trạng thái active trên trục thời gian/tọa độ.

---

## Ghi nhớ

**Sorting** tạo thứ tự, **two pointers** tận dụng tính đơn điệu, **event sweep** cập nhật trạng thái tại các mốc thay đổi.

- Đếm cặp tổng ≤K: sort hai mảng; nếu tổng đủ nhỏ thì cộng j+1, nếu quá lớn thì giảm j.
- Giao hai danh sách interval: tính [max(start),min(end)), bỏ khoảng kết thúc sớm; mỗi danh sách phải sort và không chồng lấn.
- Maximum overlap: START +1, END −1; với [start,end), xử lý END trước START.
- Comparator phải an toàn số học và có tie-break rõ.
- Mọi điều kiện <, <= phải khớp định nghĩa khoảng.
- Dùng oracle vét cạn độc lập và random seed cố định để đối chiếu lời giải tối ưu.

\[
\boxed{
\text{Mô hình đúng}
+\text{thứ tự đúng}
+\text{invariant đúng}
+\text{tie-order đúng}
+\text{kiểm thử độc lập}
}
\]

mới tạo nên một lời giải kết hợp sorting, two pointers và event processing đáng tin cậy.
