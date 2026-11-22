# Kiểm tra ranh giới đoạn, thứ tự sự kiện và trạng thái sau mỗi truy vấn

> **Chủ đề:** Computer Science Algorithms → **Truy vấn và ngoại tuyến**.  
> **Mục tiêu:** Đảm bảo mỗi truy vấn offline dùng **đúng ranh giới**, **đúng thứ tự sự kiện**, **đúng phiên bản trạng thái** và được trả về theo **thứ tự đầu vào**. Bài trình bày đoạn nửa mở `[L,R)`, sweep line theo END/START/QUERY, nén tọa độ và Fenwick theo timeline, Mo's algorithm cùng bất biến cửa sổ, cây thời gian với DSU rollback, các phản ví dụ, oracle và **bốn chương trình Java 17 độc lập** có lệnh chạy và stdout.

## 1. Đặt hợp đồng truy vấn trước khi tối ưu

Lỗi khó thấy nhất của bài truy vấn không phải lúc nào cũng do cấu trúc dữ liệu sai. Một thuật toán có thể rất nhanh nhưng trả lời sai câu hỏi khi nhầm:

1. **Ranh giới:** `[L,R]` khác `[L,R)`; điểm tại R có thể thuộc hoặc không thuộc đoạn.
2. **Thứ tự sự kiện:** Nếu đoạn kết thúc và đoạn khác bắt đầu đúng tọa độ x, QUERY tại x thấy cập nhật nào?
3. **Trạng thái:** QUERY ở thời điểm t phải thấy những UPDATE nào? Offline sort có làm mất thứ tự gốc không?

Trước khi lập trình cần xác định: index từ0 hay1, đoạn rỗng hợp lệ hay không, query có cập nhật xen kẽ hay chỉ đọc dữ liệu tĩnh, sự kiện cùng timestamp xử lý trước/sau query, và output có cần đúng ID gốc không.

**Nguyên tắc:** Được phép thay đổi **thứ tự tính toán**, không được thay đổi **ngữ nghĩa trạng thái của một truy vấn**.

### 1.1. Hai trục tọa độ khác nhau

Một truy vấn thường mang:

- **Vị trí không gian:** x hoặc `[L,R)`.
- **Thời điểm/phiên bản:** t của event hay update.
- **ID gốc:** vị trí truy vấn trong input.

Ví dụ cùng QUERY x=3 ở t=2 và t=8 có thể trả khác nhau. Sort theo x không cho phép quên t. Sort theo block Mo không cho phép quên ID.

## 2. Chuẩn hóa đoạn nửa mở [L,R)

Trong toàn bài, trừ khi nói khác, đoạn là:

`[L,R)={i | L≤i<R}`.

Với mảng n phần tử, input hợp lệ cần `0≤L≤R≤n`.

| Đoạn | Phần tử | Độ dài |
|---|---|---:|
| `[0,0)` | Không có | 0 |
| `[0,1)` | 0 | 1 |
| `[2,5)` | 2,3,4 | 3 |
| `[n,n)` | Không có | 0 |
| `[0,n)` | Toàn bộ mảng | n |

Ưu điểm:

- Hai đoạn `[a,b)` và `[b,c)` không chồng lặp.
- Độ dài bằng `R−L`.
- Vòng lặp Java `for (int i=L; i<R; i++)` duyệt đúng phần tử.
- Có đoạn rỗng `[L,L)`.
- Tổng từ prefix sum là `prefix[R]−prefix[L]`.

### 2.1. Chuyển từ đoạn đóng [L,R]

Với **chỉ số nguyên** `[L,R]` trong miền a[0..n−1], chuyển thành `[L,R+1)`. Không áp công thức cộng1 cho **tọa độ số thực liên tục**.

Khi R có thể bằng `Integer.MAX_VALUE`, biểu thức `R+1` kiểu int tràn. Dùng long trước khi cộng:

```java
long endExclusive = (long) rightInclusive + 1L;
```

### 2.2. Tại chính hai endpoint

- `[L,R)` chứa `x=L` nếu L<R.
- `[L,R)` **không chứa** `x=R`.
- `[L,L)` không chứa L hay bất kỳ điểm nào.
- `R=n` là biên loại trừ hợp lệ; **a[n] không tồn tại**.

Cần test x=L−1,L,R−1,R,R+1 khi có thể biểu diễn.

### 2.3. Không tạo sự kiện cho đoạn rỗng

Nếu UPDATE `[3,3)` có delta100, đó là no-op. Trong sweep END→START→QUERY, việc tạo END và START cùng điểm cho đoạn rỗng có thể khiến QUERY đọc tăng100 sai. **Bỏ qua khoảng rỗng trước khi tạo sự kiện.**

### 2.4. Nén tọa độ không giữ độ dài

Nén `[-2,0,3,5,6]` thành rank `[0,1,2,3,4]` chỉ giữ thứ tự. Rank(5)−rank(3)=1, nhưng tọa độ thật cách nhau2. Nếu bài cần diện tích/tổng độ dài, phải giữ khoảng cách thật giữa các mốc.

## 3. Bất biến phải đúng trước mỗi QUERY

Đặt `S(q)` là trạng thái logic mà query q yêu cầu. Ngay trước khi ghi `answer[q.id]`, cấu trúc dữ liệu phải biểu diễn **đúng S(q)**.

- Sweep: `active` bằng tổng weight của tất cả đoạn chứa tọa độ x.
- Fenwick timeline: chỉ những UPDATE có thời gian nhỏ hơn t đã được áp dụng.
- Mo: frequency map bằng đúng phân phối giá trị trong `[L,R)`.
- DSU rollback: tập cạnh được union chính xác là những cạnh còn active ở lá t.

Kết quả final có thể tình cờ đúng khi trạng thái trung gian sai. Vì vậy phải đối chiếu **mỗi query**, không chỉ so tổng cuối.

Ví dụ:

```text
0: ADD [0,3) +5
1: QUERY x=2 -> 5
2: ADD [2,5) +7
3: QUERY x=2 -> 12
```

Nếu xử lý tất cả UPDATE trước QUERY, cả hai đều trả12 — sai phiên bản ở t=1.

## 4. Sweep line: END, START và QUERY cùng tọa độ

Bài tĩnh: mỗi đoạn `[L,R)` có trọng số w, cần trả:

`answer(x) = Σ weight` của mọi đoạn thỏa `L≤x<R`.

Tạo event:

- `END` tại R: cộng `−w`.
- `START` tại L: cộng `+w`.
- `QUERY` tại x: đọc `active`.

Tại cùng một tọa độ x, quy tắc rõ ràng là:

`END (phase0) → START (phase1) → QUERY (phase2)`.

Với `[0,3)` weight5 và `[3,6)` weight7, query x=3 phải là7. QUERY trước END đếm thừa đoạn cũ; QUERY trước START bỏ sót đoạn mới.

**Chú ý:** Với tổng cộng thuần túy, END/START có thể đổi chỗ nếu cả hai đều **trước QUERY** vì phép cộng giao hoán. Nhưng chọn một chính sách nhất quán giảm lỗi khi mở rộng sang trạng thái khác.

### 4.1. Comparator an toàn

Sort theo (tọa độ, phase, ID). Dùng `Integer.compare` hoặc `Comparator.comparingInt`. Không dùng `a.x-b.x`: phép trừ int có thể overflow nếu x âm/dương cực trị.

### 4.2. Thứ tự truy vấn gốc

Sweep xử lý query theo x tăng dần, nhưng phải ghi `answer[id]` theo ID đầu vào. Nếu input query `[3,-2,0]`, không được in ngay thành thứ tự tọa độ `[-2,0,3]`.

### 4.3. Tương đương với delta

Có thể cộng dồn `delta[L]+=w`, `delta[R]-=w`, quét x tăng dần và xử lý mọi delta tại x **trước** các query tại x. Với số học nguyên chính xác, đây là cùng ngữ nghĩa nửa mở.

## 5. Ví dụ sweep ở ranh giới nhạy

| ID | Khoảng | Weight |
|---|---|---:|
| I0 | `[-2,3)` | 5 |
| I1 | `[0,5)` | 2 |
| I2 | `[3,3)` | 100, nhưng rỗng |
| I3 | `[3,6)` | −1 |

Truy vấn theo input:

`[3,-2,0,5,6,2,3,-3]`.

Kết quả:

`[1,5,7,-1,0,7,1,0]`.

Giải thích:

- x=−2: I0 chứa ⇒ 5.
- x=0,2: I0+I1 ⇒ 7.
- x=3: I0 hết, I3 bắt đầu, I1 còn ⇒ 2−1=1.
- x=5: I1 hết ⇒ chỉ I3, −1.
- x=6: I3 hết ⇒ 0.
- x=−3: chưa có đoạn ⇒ 0.
- I2 rỗng không bao giờ đóng góp100.

## 6. Java 17 — quét sự kiện và kiểm bằng oracle

Lưu **OfflineIntervalSweepDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class OfflineIntervalSweepDemo {
    record Interval(int left, int right, long weight) {}
    record Event(int x, int phase, long delta, int id) {}

    static long[] solve(List<Interval> intervals, int[] queries) {
        if (intervals == null || queries == null)
            throw new IllegalArgumentException("Null input");
        List<Event> events = new ArrayList<>();
        for (Interval it : intervals) {
            if (it == null || it.left() > it.right())
                throw new IllegalArgumentException("Invalid range");
            if (it.left() == it.right()) continue;
            events.add(new Event(it.right(), 0, -it.weight(), -1));
            events.add(new Event(it.left(), 1, it.weight(), -1));
        }
        for (int id = 0; id < queries.length; id++)
            events.add(new Event(queries[id], 2, 0, id));

        events.sort(Comparator.comparingInt(Event::x)
                .thenComparingInt(Event::phase)
                .thenComparingInt(Event::id));

        long active = 0;
        long[] ans = new long[queries.length];
        for (Event e : events) {
            if (e.phase() == 2) ans[e.id()] = active;
            else active += e.delta();
        }
        return ans;
    }

    static long[] slow(List<Interval> intervals, int[] queries) {
        long[] ans = new long[queries.length];
        for (int id = 0; id < queries.length; id++) {
            long sum = 0;
            for (Interval it : intervals)
                if (it.left() <= queries[id] && queries[id] < it.right())
                    sum += it.weight();
            ans[id] = sum;
        }
        return ans;
    }

    public static void main(String[] args) {
        List<Interval> it = List.of(
                new Interval(-2, 3, 5),
                new Interval(0, 5, 2),
                new Interval(3, 3, 100),
                new Interval(3, 6, -1));
        int[] q = {3, -2, 0, 5, 6, 2, 3, -3};

        long[] ans = solve(it, q);
        System.out.println("answers=" + Arrays.toString(ans));
        for (int id = 0; id < q.length; id++)
            System.out.printf("Q%d x=%d -> %d%n", id, q[id], ans[id]);
        System.out.println("oracle match="
                + Arrays.equals(ans, slow(it, q)));

        boolean rejected = false;
        try {
            solve(List.of(new Interval(5, 4, 1)), q);
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        System.out.println("reversed range rejected=" + rejected);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 OfflineIntervalSweepDemo.java
java OfflineIntervalSweepDemo
```

Stdout:

```text
answers=[1, 5, 7, -1, 0, 7, 1, 0]
Q0 x=3 -> 1
Q1 x=-2 -> 5
Q2 x=0 -> 7
Q3 x=5 -> -1
Q4 x=6 -> 0
Q5 x=2 -> 7
Q6 x=3 -> 1
Q7 x=-3 -> 0
oracle match=true
reversed range rejected=true
```

**Chứng minh đúng:** Khi QUERY tại x, mọi event có tọa độ nhỏ hơn x đã chạy, và mọi END/START tại x chạy trước QUERY. Do đó `active=Σ_{L≤x<R}w`, đúng biểu thức oracle.

**Độ phức tạp:** Với m interval không rỗng và q query, có 2m+q event. Sort O((m+q)log(m+q)), quét O(m+q), bộ nhớ O(m+q). Oracle O(mq) chỉ dùng test.

**Giới hạn số:** `-Long.MIN_VALUE` và tổng `long` vượt miền biểu diễn sẽ overflow. Với dữ liệu lớn cần `Math.negateExact`, `Math.addExact` hoặc BigInteger.

## 7. Coordinate compression + Fenwick

Nếu tọa độ cách nhau hàng tỷ đơn vị, không cấp phát mảng phủ toàn trục. Thu thập mọi L,R của UPDATE và x của QUERY, sort và unique, gán rank từ0.

Cập nhật `[L,R)` với delta d tương đương:

`diff[L]+=d; diff[R]-=d`.

Truy vấn tại x trả prefix các delta có tọa độ **≤x**:

`value(x)=Σ_{coordinate≤x} diff[coordinate]`.

Điểm quan trọng: tại x=R, delta `−d` đã được tính, khiến đoạn kết thúc tại R không còn tác động.

### 7.1. Chỉ nén offline, nhưng replay theo t gốc

Nén tọa độ được thực hiện trên toàn bộ danh sách thao tác. Sau đó xử lý UPDATE và QUERY **theo thứ tự input**. Không áp dụng update tương lai cho query quá khứ.

### 7.2. Fenwick dùng 1-based nội bộ

Rank0 là chỉ số 0-based của tọa độ sau nén. Fenwick add/prefix bắt đầu tại `rank0+1`, di chuyển bằng `i+=i&-i` hoặc `i-=i&-i`. Nếu quên +1, ở rank0 có thể sai hoặc vòng lặp không tiến.

### 7.3. No-op và overflow

`[L,L)` phải bỏ qua; hai delta đối nghịch cùng điểm gây thao tác vô ích và có thể overflow tạm thời. `−delta` cũng overflow khi delta bằng Long.MIN_VALUE. Demo dùng delta an toàn.

## 8. Timeline cập nhật và truy vấn cùng tọa độ

| t | Thao tác | Kết quả |
|---:|---|---:|
| 0 | UPDATE `[-2,3)` +5 | |
| 1 | QUERY x=−2 | 5 |
| 2 | QUERY x=3 | 0 |
| 3 | UPDATE `[0,3)` +7 | |
| 4 | QUERY x=0 | 12 |
| 5 | UPDATE `[3,5)` −2 | |
| 6 | QUERY x=3 | −2 |
| 7 | QUERY x=4 | −2 |
| 8 | UPDATE `[1,1)` +999 | No-op |
| 9 | QUERY x=1 | 12 |
| 10 | UPDATE `[-2,3)` −5 | |
| 11 | QUERY x=0 | 7 |
| 12 | QUERY x=−2 | 0 |

Hai query x=3 có đáp án khác ở t=2 và t=6. Đây là test chống lỗi áp dụng tất cả UPDATE trước tất cả QUERY.

## 9. Java 17 — range add / point query theo dòng thời gian

Lưu **RangeAddPointTimelineDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.TreeSet;

public class RangeAddPointTimelineDemo {
    record Op(char type, int l, int r, long delta) {
        static Op update(int l, int r, long delta) {
            return new Op('U', l, r, delta);
        }
        static Op query(int x) {
            return new Op('Q', x, x, 0);
        }
    }
    static final class Fenwick {
        final long[] tree;
        Fenwick(int n) { tree = new long[n + 1]; }
        void add(int rank0, long delta) {
            for (int i = rank0 + 1; i < tree.length; i += i & -i)
                tree[i] += delta;
        }
        long prefixInclusive(int rank0) {
            long ans = 0;
            for (int i = rank0 + 1; i > 0; i -= i & -i)
                ans += tree[i];
            return ans;
        }
    }

    static List<String> solve(Op[] ops) {
        if (ops == null) throw new IllegalArgumentException("Null");
        TreeSet<Integer> coordinates = new TreeSet<>();
        for (Op op : ops) {
            if (op == null) throw new IllegalArgumentException("Null op");
            if (op.type() == 'U') {
                if (op.l() > op.r())
                    throw new IllegalArgumentException("Reversed range");
                coordinates.add(op.l());
                coordinates.add(op.r());
            } else if (op.type() == 'Q') {
                coordinates.add(op.l());
            } else throw new IllegalArgumentException("Bad op");
        }

        int[] coords = coordinates.stream()
                .mapToInt(Integer::intValue).toArray();
        Fenwick fw = new Fenwick(coords.length);
        List<String> result = new ArrayList<>();

        for (int t = 0; t < ops.length; t++) {
            Op op = ops[t];
            if (op.type() == 'U') {
                if (op.l() == op.r()) continue;
                int l = Arrays.binarySearch(coords, op.l());
                int r = Arrays.binarySearch(coords, op.r());
                fw.add(l, op.delta());
                fw.add(r, -op.delta());
            } else {
                int at = Arrays.binarySearch(coords, op.l());
                long value = fw.prefixInclusive(at);
                result.add("Q t=" + t + " x=" + op.l()
                        + " -> " + value);
            }
        }
        return result;
    }

    static List<String> slow(Op[] ops) {
        List<String> result = new ArrayList<>();
        for (int t = 0; t < ops.length; t++) {
            Op q = ops[t];
            if (q.type() != 'Q') continue;
            long value = 0;
            for (int j = 0; j < t; j++) {
                Op u = ops[j];
                if (u.type() == 'U'
                        && u.l() <= q.l() && q.l() < u.r())
                    value += u.delta();
            }
            result.add("Q t=" + t + " x=" + q.l()
                    + " -> " + value);
        }
        return result;
    }

    public static void main(String[] args) {
        Op[] ops = {
            Op.update(-2, 3, 5), Op.query(-2), Op.query(3),
            Op.update(0, 3, 7), Op.query(0),
            Op.update(3, 5, -2), Op.query(3), Op.query(4),
            Op.update(1, 1, 999), Op.query(1),
            Op.update(-2, 3, -5), Op.query(0), Op.query(-2)
        };

        List<String> ans = solve(ops);
        for (String line : ans) System.out.println(line);
        System.out.println("timeline oracle match="
                + ans.equals(slow(ops)));

        boolean rejected = false;
        try {
            solve(new Op[] {Op.update(5, 4, 1)});
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        System.out.println("reversed update rejected=" + rejected);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 RangeAddPointTimelineDemo.java
java RangeAddPointTimelineDemo
```

Stdout:

```text
Q t=1 x=-2 -> 5
Q t=2 x=3 -> 0
Q t=4 x=0 -> 12
Q t=6 x=3 -> -2
Q t=7 x=4 -> -2
Q t=9 x=1 -> 12
Q t=11 x=0 -> 7
Q t=12 x=-2 -> 0
timeline oracle match=true
reversed update rejected=true
```

**Invariant:** Mỗi QUERY thời điểm t đọc Fenwick chứa đúng các delta của UPDATE có index j<t. Vì `+delta` tại L, `−delta` tại R, prefix tại x nhận d nếu và chỉ nếu L≤x<R. Hàm slow quét lại các UPDATE trước t là oracle độc lập.

**Độ phức tạp:** O(TlogT) nén tọa độ; mỗi UPDATE hai Fenwick add O(logM), QUERY một prefix O(logM), với M số mốc phân biệt. Bộ nhớ O(T+M) do lưu thao tác để nén offline; slow O(T²) chỉ dùng test.

## 10. Mo's algorithm — reorder query nhưng giữ đáp án

Với mảng **tĩnh** a dài n và q truy vấn `[L,R)`, Mo's algorithm:

1. Chia L thành block độ dài B≈√n.
2. Sort truy vấn theo `block(L)` và R. Có thể đảo thứ tự R ở block lẻ để giảm dịch chuyển.
3. Duy trì cửa sổ hiện tại `[curL,curR)`.
4. Thêm/xóa phần tử để đưa cửa sổ tới đúng đoạn query.
5. Ghi `answer[q.originalId]` khi cửa sổ đã đúng.

Bài thực hành: số lượng **giá trị phân biệt** (*distinct count*) trong đoạn.

### 10.1. Invariant frequency

`frequency[value]` là số lần xuất hiện của value trong `[curL,curR)`.

Do đó:

`Σ_value frequency[value]=curR−curL`.

`distinct` là số khóa có frequency>0. Xóa khóa khi frequency trở về0.

### 10.2. Di chuyển an toàn

```text
while curL > L: add(a[--curL])
while curR < R: add(a[curR++])
while curL < L: remove(a[curL++])
while curR > R: remove(a[--curR])
```

**Mở rộng trước co lại**: nếu cửa sổ đầu `[0,0)` và query đầu `[7,8)`, co trái trước sẽ remove các phần tử chưa từng add. Dãy trên tránh lỗi này.

### 10.3. Tiền tố/hậu tố rất quan trọng

- Kéo phải: `add(a[curR++])`.
- Kéo trái: `add(a[--curL])`.
- Bỏ trái: `remove(a[curL++])`.
- Bỏ phải: `remove(a[--curR])`.

Đổi chỗ tiền tăng/hậu tăng sẽ thêm hoặc bỏ sai vị trí ở biên.

### 10.4. Không áp trực tiếp khi có UPDATE

Mo cơ bản chỉ giải trên mảng tĩnh. Nếu có sửa a[i] xen kẽ, phải thêm chiều thời gian (Mo with modifications) và apply/undo updates, hoặc chọn cấu trúc khác.

## 11. Ví dụ Mo và các query rỗng

Mảng:

`a=[4,1,4,2,1,3,2,3]`.

Các query theo input:

| ID | Đoạn | Distinct |
|---:|---|---:|
| Q0 | `[0,8)` | 4 |
| Q1 | `[0,1)` | 1 |
| Q2 | `[1,5)` | 3 |
| Q3 | `[3,3)` | 0 |
| Q4 | `[4,8)` | 3 |
| Q5 | `[2,7)` | 4 |
| Q6 | `[7,8)` | 1 |
| Q7 | `[0,0)` | 0 |
| Q8 | `[8,8)` | 0 |
| Q9 | `[5,8)` | 2 |

Đáp án:

`[4,1,3,0,3,4,1,0,0,2]`.

Các query `[3,3)`, `[0,0)` và `[8,8)` là ba biên rỗng khác nhau. Nếu xử lý `[n,n)` như truy cập a[n], chương trình sẽ sai.

## 12. Java 17 — Mo distinct và kiểm trạng thái sau mỗi query

Lưu **MoRangeDistinctAuditDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class MoRangeDistinctAuditDemo {
    record Query(int l, int r, int id) {}

    static final class Window {
        final Map<Integer, Integer> freq = new HashMap<>();
        int distinct = 0, total = 0;

        void add(int x) {
            int count = freq.getOrDefault(x, 0);
            if (count == 0) distinct++;
            freq.put(x, count + 1);
            total++;
        }
        void remove(int x) {
            Integer count = freq.get(x);
            if (count == null || count <= 0)
                throw new AssertionError("Removed absent value");
            if (count == 1) {
                freq.remove(x);
                distinct--;
            } else {
                freq.put(x, count - 1);
            }
            total--;
        }
        void audit(int l, int r) {
            if (total != r - l || distinct != freq.size())
                throw new AssertionError("Wrong window state");
            for (int count : freq.values())
                if (count <= 0) throw new AssertionError("Bad frequency");
        }
    }

    static int[] solve(int[] a, int[][] ranges) {
        if (a == null || ranges == null)
            throw new IllegalArgumentException("Null");
        int n = a.length;
        List<Query> qs = new ArrayList<>();
        for (int id = 0; id < ranges.length; id++) {
            int[] q = ranges[id];
            if (q == null || q.length != 2
                    || q[0] < 0 || q[0] > q[1] || q[1] > n)
                throw new IllegalArgumentException("Invalid range");
            qs.add(new Query(q[0], q[1], id));
        }
        final int block = Math.max(1, (int) Math.sqrt(Math.max(1, n)));
        qs.sort((x, y) -> {
            int bx = x.l() / block, by = y.l() / block;
            if (bx != by) return Integer.compare(bx, by);
            int cmp = (bx & 1) == 0
                    ? Integer.compare(x.r(), y.r())
                    : Integer.compare(y.r(), x.r());
            return cmp != 0 ? cmp : Integer.compare(x.id(), y.id());
        });

        Window window = new Window();
        int left = 0, right = 0;
        int[] ans = new int[ranges.length];

        for (Query q : qs) {
            while (left > q.l()) window.add(a[--left]);
            while (right < q.r()) window.add(a[right++]);
            while (left < q.l()) window.remove(a[left++]);
            while (right > q.r()) window.remove(a[--right]);

            if (left != q.l() || right != q.r())
                throw new AssertionError("Wrong window bounds");
            window.audit(left, right);
            ans[q.id()] = window.distinct;
        }
        return ans;
    }

    static int[] slow(int[] a, int[][] ranges) {
        int[] ans = new int[ranges.length];
        for (int id = 0; id < ranges.length; id++) {
            Set<Integer> values = new HashSet<>();
            for (int i = ranges[id][0]; i < ranges[id][1]; i++)
                values.add(a[i]);
            ans[id] = values.size();
        }
        return ans;
    }

    public static void main(String[] args) {
        int[] a = {4, 1, 4, 2, 1, 3, 2, 3};
        int[][] ranges = {
            {0, 8}, {0, 1}, {1, 5}, {3, 3}, {4, 8},
            {2, 7}, {7, 8}, {0, 0}, {8, 8}, {5, 8}
        };
        int[] ans = solve(a, ranges);
        System.out.println("distinct=" + Arrays.toString(ans));
        for (int id = 0; id < ans.length; id++)
            System.out.printf("Q%d [%d,%d) -> %d%n",
                    id, ranges[id][0], ranges[id][1], ans[id]);
        System.out.println("Mo oracle match="
                + Arrays.equals(ans, slow(a, ranges)));

        boolean rejected = false;
        try {
            solve(a, new int[][] {{7, 9}});
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        System.out.println("invalid query rejected=" + rejected);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 MoRangeDistinctAuditDemo.java
java MoRangeDistinctAuditDemo
```

Stdout:

```text
distinct=[4, 1, 3, 0, 3, 4, 1, 0, 0, 2]
Q0 [0,8) -> 4
Q1 [0,1) -> 1
Q2 [1,5) -> 3
Q3 [3,3) -> 0
Q4 [4,8) -> 3
Q5 [2,7) -> 4
Q6 [7,8) -> 1
Q7 [0,0) -> 0
Q8 [8,8) -> 0
Q9 [5,8) -> 2
Mo oracle match=true
invalid query rejected=true
```

**Invariant trước answer[id]:** `left=q.l`, `right=q.r`, sum(freq)=right−left và mọi count dương. Oracle `HashSet(a[L:R])` kiểm toàn bộ đáp án theo ID.

Sort O(qlogq), số thao tác add/remove theo block order tiêu chuẩn xấp xỉ O((n+q)√n) khi n và q có quy mô thường gặp. Mỗi update frequency O(1) kỳ vọng với HashMap; oracle O(nq) chỉ dùng test.

## 13. Khoảng sống trên trục thời gian

Offline dynamic connectivity dùng thao tác:

- `+ (u,v)`: thêm cạnh.
- `- (u,v)`: xóa cạnh.
- `? (u,v)`: hỏi liên thông.

Chọn thời điểm t là **operation index**, mỗi t chứa đúng một thao tác. Trạng thái tại t được định nghĩa là trạng thái **sau khi thao tác t đã hoàn tất**.

Cạnh ADD ở a và REMOVE ở b sống trên:

`[a,b)`.

- Có hiệu lực từ a.
- Không còn tại b sau REMOVE.
- Nếu chưa bị REMOVE, kết thúc tại T (số thao tác): `[a,T)`.

Tại QUERY ở index t, mọi update index nhỏ hơn t đã có hiệu lực. Khi log có nhiều event cùng timestamp thực, phải định nghĩa thứ tự thứ cấp trước khi gán index.

### 13.1. Lỗi biên thời gian

Dùng `[a,b]` khiến cạnh đã xóa vẫn xuất hiện ở lá b. Dùng `[a+1,b)` có thể bỏ trạng thái ngay sau ADD. Khoảng đúng phụ thuộc rõ ràng vào semantics “trạng thái sau sự kiện”.

## 14. Cây phân đoạn theo thời gian và DSU rollback

DSU thông thường hỗ trợ union, không xóa cạnh trực tiếp. Với input offline:

1. Ghép mỗi ADD với REMOVE để tạo các khoảng sống.
2. Phân hoạch mỗi khoảng sống thành O(logT) node của segment tree `[0,T)`.
3. DFS: vào node thì union các cạnh gắn ở node.
4. Tại lá t, answer QUERY dựa trên DSU hiện tại.
5. Rời node thì **rollback** về snapshot đã lưu trước union.

**Chứng minh:** Một cạnh active ở t khi và chỉ khi đường root→lá t đi qua đúng một node của phân hoạch lưu cạnh đó. DSU ở lá nối đúng các cạnh active. Rollback loại mọi union chỉ thuộc nhánh trước.

### 14.1. Vì sao tắt path compression?

DSU rollback union-by-size ghi:

- Root con bị gắn.
- Root nhận.
- Size cũ của root nhận.

Rollback LIFO khôi phục parent root con và size cũ. Nếu find path-compress sửa nhiều parent mà không log, rollback không khôi phục đủ. Union-by-size không compression vẫn cho chiều cao cây O(logn).

### 14.2. Domain của demo

- Đồ thị đơn vô hướng, mọi cạnh active có tối đa một bản sao.
- `(u,v)` và `(v,u)` là cùng cạnh.
- Duplicate ADD, unmatched REMOVE và self-loop update bị từ chối.
- QUERY `(u,u)` hợp lệ và luôn true.
- Nếu muốn multigraph, cần edge IDs hoặc đếm reference; không áp thẳng mô hình single edge.

## 15. Ví dụ 21 thao tác, 12 câu hỏi

| t | Thao tác | QUERY result |
|---:|---|---|
| 0 | + (0,1) | |
| 1 | ? (0,1) | true |
| 2 | ? (0,2) | false |
| 3 | + (1,2) | |
| 4 | ? (0,2) | true |
| 5 | + (3,4) | |
| 6 | ? (0,4) | false |
| 7 | − (0,1) | |
| 8 | ? (0,2) | false |
| 9 | + (2,3) | |
| 10 | ? (1,4) | true |
| 11 | − (1,2) | |
| 12 | ? (1,4) | false |
| 13 | ? (2,4) | true |
| 14 | − (3,4) | |
| 15 | ? (2,4) | false |
| 16 | + (0,4) | |
| 17 | ? (0,4) | true |
| 18 | − (0,4) | |
| 19 | ? (0,4) | false |
| 20 | ? (0,0) | true |

Những ranh giới cần hiểu:

- t=10: 1–2–3–4 tạo kết nối.
- t=12: đã xóa cạnh 1–2, 1 không nối4.
- t=13: 2 vẫn nối4 qua 2–3–4.
- t=15: đã xóa 3–4 nên 2 không nối4.
- t=20: đỉnh0 tự liên thông bằng đường đi độ dài0.

## 16. Java 17 — dynamic connectivity và rollback

Lưu **OfflineDynamicConnectivityAuditDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class OfflineDynamicConnectivityAuditDemo {
    record Op(char kind, int u, int v) {}
    record Edge(int u, int v) {
        static Edge of(int a, int b) {
            return a < b ? new Edge(a, b) : new Edge(b, a);
        }
    }
    record Change(int child, int root, int oldSize) {}

    static final class Dsu {
        final int[] parent, size;
        final ArrayDeque<Change> history = new ArrayDeque<>();
        Dsu(int n) {
            parent = new int[n];
            size = new int[n];
            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }
        int find(int x) {
            while (parent[x] != x) x = parent[x];
            return x;
        }
        void unite(int u, int v) {
            int a = find(u), b = find(v);
            if (a == b) return;
            if (size[a] < size[b]) {
                int temp = a; a = b; b = temp;
            }
            history.push(new Change(b, a, size[a]));
            parent[b] = a;
            size[a] += size[b];
        }
        int snapshot() { return history.size(); }
        void rollback(int mark) {
            while (history.size() > mark) {
                Change c = history.pop();
                parent[c.child()] = c.child();
                size[c.root()] = c.oldSize();
            }
        }
        boolean connected(int u, int v) {
            return find(u) == find(v);
        }
    }

    static void addInterval(List<Edge>[] tree, int node,
                            int l, int r, int ql, int qr, Edge edge) {
        if (qr <= l || r <= ql) return;
        if (ql <= l && r <= qr) {
            tree[node].add(edge);
            return;
        }
        int m = l + (r - l) / 2;
        addInterval(tree, node * 2, l, m, ql, qr, edge);
        addInterval(tree, node * 2 + 1, m, r, ql, qr, edge);
    }

    static void dfs(List<Edge>[] tree, int node, int l, int r,
                    Op[] ops, Dsu dsu, boolean[] answer) {
        int mark = dsu.snapshot();
        for (Edge edge : tree[node])
            dsu.unite(edge.u(), edge.v());

        if (r - l == 1) {
            Op op = ops[l];
            if (op.kind() == '?')
                answer[l] = dsu.connected(op.u(), op.v());
        } else {
            int m = l + (r - l) / 2;
            dfs(tree, node * 2, l, m, ops, dsu, answer);
            dfs(tree, node * 2 + 1, m, r, ops, dsu, answer);
        }
        dsu.rollback(mark);
    }

    static boolean[] solve(int n, Op[] ops) {
        if (n < 0 || ops == null)
            throw new IllegalArgumentException("Invalid");
        int T = ops.length;
        @SuppressWarnings("unchecked")
        List<Edge>[] tree = (List<Edge>[]) new List[
                4 * Math.max(1, T)];
        for (int i = 0; i < tree.length; i++)
            tree[i] = new ArrayList<>();

        Map<Edge, Integer> opened = new HashMap<>();
        for (int t = 0; t < T; t++) {
            Op op = ops[t];
            if (op == null || op.u() < 0 || op.v() < 0
                    || op.u() >= n || op.v() >= n
                    || "+-?".indexOf(op.kind()) < 0)
                throw new IllegalArgumentException("Bad operation");
            if (op.kind() == '?') continue;
            if (op.u() == op.v())
                throw new IllegalArgumentException("Self-loop update");
            Edge edge = Edge.of(op.u(), op.v());

            if (op.kind() == '+') {
                if (opened.putIfAbsent(edge, t) != null)
                    throw new IllegalArgumentException("Duplicate add");
            } else {
                Integer start = opened.remove(edge);
                if (start == null)
                    throw new IllegalArgumentException("Unmatched remove");
                addInterval(tree, 1, 0, T, start, t, edge);
            }
        }
        for (Map.Entry<Edge, Integer> e : opened.entrySet())
            addInterval(tree, 1, 0, T,
                    e.getValue(), T, e.getKey());

        boolean[] answer = new boolean[T];
        if (T > 0) dfs(tree, 1, 0, T, ops, new Dsu(n), answer);
        return answer;
    }

    // Test oracle: active edge set plus BFS per query.
    static boolean reachable(int n, Set<Edge> edges, int src, int dst) {
        boolean[] seen = new boolean[n];
        ArrayDeque<Integer> q = new ArrayDeque<>();
        seen[src] = true;
        q.add(src);
        while (!q.isEmpty()) {
            int current = q.remove();
            if (current == dst) return true;
            for (Edge e : edges) {
                int next = -1;
                if (e.u() == current) next = e.v();
                else if (e.v() == current) next = e.u();
                if (next >= 0 && !seen[next]) {
                    seen[next] = true;
                    q.add(next);
                }
            }
        }
        return false;
    }

    static boolean[] slow(int n, Op[] ops) {
        Set<Edge> active = new HashSet<>();
        boolean[] answer = new boolean[ops.length];
        for (int t = 0; t < ops.length; t++) {
            Op op = ops[t];
            Edge edge = Edge.of(op.u(), op.v());
            if (op.kind() == '+') active.add(edge);
            else if (op.kind() == '-') active.remove(edge);
            else answer[t] = reachable(n, active, op.u(), op.v());
        }
        return answer;
    }

    public static void main(String[] args) {
        Op[] ops = {
            new Op('+', 0, 1), new Op('?', 0, 1),
            new Op('?', 0, 2), new Op('+', 1, 2),
            new Op('?', 0, 2), new Op('+', 3, 4),
            new Op('?', 0, 4), new Op('-', 0, 1),
            new Op('?', 0, 2), new Op('+', 2, 3),
            new Op('?', 1, 4), new Op('-', 1, 2),
            new Op('?', 1, 4), new Op('?', 2, 4),
            new Op('-', 3, 4), new Op('?', 2, 4),
            new Op('+', 0, 4), new Op('?', 0, 4),
            new Op('-', 0, 4), new Op('?', 0, 4),
            new Op('?', 0, 0)
        };
        boolean[] ans = solve(5, ops);
        for (int t = 0; t < ops.length; t++) {
            Op op = ops[t];
            if (op.kind() == '?')
                System.out.printf("Q t=%d (%d,%d) -> %s%n",
                        t, op.u(), op.v(), ans[t]);
        }
        System.out.println("rollback oracle match="
                + Arrays.equals(ans, slow(5, ops)));

        boolean rejected = false;
        try {
            solve(3, new Op[] {new Op('-', 0, 1)});
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        System.out.println("unmatched remove rejected=" + rejected);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 OfflineDynamicConnectivityAuditDemo.java
java OfflineDynamicConnectivityAuditDemo
```

Stdout:

```text
Q t=1 (0,1) -> true
Q t=2 (0,2) -> false
Q t=4 (0,2) -> true
Q t=6 (0,4) -> false
Q t=8 (0,2) -> false
Q t=10 (1,4) -> true
Q t=12 (1,4) -> false
Q t=13 (2,4) -> true
Q t=15 (2,4) -> false
Q t=17 (0,4) -> true
Q t=19 (0,4) -> false
Q t=20 (0,0) -> true
rollback oracle match=true
unmatched remove rejected=true
```

**Invariant:** Ở mỗi lá t, DFS áp dụng chính xác các cạnh có khoảng sống chứa t. Rollback về snapshot trước khi rời node đảm bảo không có union của nhánh khác rò sang phiên bản mới.

Tổng cạnh lưu trong cây O(ElogT) cho E lần ADD hợp lệ. DSU union-by-size không path compression có find O(logn). Có thể nêu bound tổng O((T+ElogT)logn) theo mô hình map trung bình O(1), bộ nhớ O(T+ElogT+n). Oracle BFS chỉ dùng test.

## 17. Trường hợp nhiều event cùng timestamp

Một timestamp vật lý có thể chứa nhiều UPDATE và QUERY. Ví dụ:

```text
time=10 REMOVE edge(1,2)
time=10 ADD edge(2,3)
time=10 QUERY connected(1,3)
```

Nếu hợp đồng yêu cầu QUERY nhìn **sau tất cả thay đổi** tại timestamp10, phải thực hiện hai update trước QUERY. Nếu yêu cầu trạng thái ngay trước timestamp10, QUERY phải chạy trước. Nếu yêu cầu giữ thứ tự xuất hiện trong log, không được đổi thứ tự đó.

**Không tồn tại một tie-breaking comparator đúng cho mọi bài.** Phải xác định semantics trước khi tạo rank/index thời gian.

## 18. Prefix sum khác difference array

Prefix sum cho range sum:

`prefix[0]=0; prefix[i+1]=prefix[i]+a[i]`.

Vậy:

`sum([L,R))=prefix[R]−prefix[L]`.

Ví dụ a=[2,5,7,1], prefix=[0,2,7,14,15]. Tổng `[1,3)` là14−2=12.

Difference array cho range add:

`diff[L]+=d; diff[R]-=d`.

Sau khi prefix diff, nhận **mức cộng lên từng phần tử**, không phải mảng dữ liệu cuối nếu tồn tại mảng nền a.

Trong timeline có UPDATE/QUERY xen kẽ, nếu xây prefix diff từ đầu sau mỗi query có thể tốn O(nq). Fenwick trong phần9 duy trì prefix delta hiệu quả hơn sau khi nén tọa độ offline.

## 19. QA độc lập và kiểm thử biến hình

Oracle phải độc lập với thuật toán chính:

| Thuật toán | Oracle | Đối chiếu |
|---|---|---|
| Sweep | Duyệt tất cả đoạn và kiểm `L≤x<R` | Từng answer[id] |
| Fenwick timeline | Duyệt các UPDATE j<t chứa x | Từng query(t,x) |
| Mo distinct | HashSet trên a[L:R] | Từng ID gốc |
| DSU rollback | Replay active edges, BFS mỗi QUERY | Từng thời điểm t |

Các trường hợp quan trọng:

- Tọa độ tại L, R, L−1, R+1.
- Đoạn rỗng; `[n,n)`; toàn mảng `[0,n)`.
- Hai đoạn nối nhau cùng endpoint.
- Tọa độ âm, trọng số âm, đồng thời nhiều query cùng x.
- Query cùng x trước và sau update.
- Mo bắt đầu `[0,0)` rồi chuyển tới `[n−1,n)`.
- Nhiều lần ADD/REMOVE cùng cạnh, nhưng không duplicate active.
- Query liên thông ngay sau REMOVE; query `(u,u)`.

### 19.1. Metamorphic tests

Những biến đổi không nên đổi đáp án (khi giữ đúng domain):

1. Đổi thứ tự QUERY tĩnh rồi gắn lại originalId.
2. Tách một đoạn `[L,R)` thành `[L,M)` và `[M,R)` cùng weight.
3. Thêm interval rỗng.
4. Đổi tọa độ đồng loạt bởi c nếu không overflow.
5. Đổi nhãn giá trị trong Mo bằng ánh xạ một-một.
6. Đổi nhãn đỉnh nhất quán trong dynamic connectivity.
7. Thêm cặp ADD/REMOVE không có QUERY ở giữa.
8. Đổi block size Mo phù hợp.

### 19.2. Test phải so từng câu

So **tập** đáp án là không đủ: nếu Q0 và Q1 bị tráo kết quả thì tập vẫn có thể giống nhau. Dùng `answer[id]`, `answer[t]`, hoặc cặp `(queryId,result)` để đối chiếu.

### 19.3. Test không thay định lý

Bộ test ngẫu nhiên giúp phát hiện lỗi triển khai. Bảo đảm tổng quát đến từ bất biến: event ordering đúng, delta telescoping, Mo window đúng, và canonical intervals + rollback đúng. Không suy từ 8.200 ca đúng rằng mọi input đều đúng nếu chưa có lập luận.

## 20. Các lỗi triển khai thường gặp

1. Nhầm `[L,R]` và `[L,R)`; đếm thừa điểm R.
2. Coi `[L,L)` là đoạn có một phần tử.
3. Cho R=n nhưng lại truy cập a[n].
4. Tính R+1 bằng int và overflow.
5. Trong sweep, QUERY chạy trước END.
6. Trong sweep, QUERY chạy trước START.
7. Không loại interval rỗng trước khi tạo event.
8. Comparator dùng phép trừ tọa độ int.
9. Sort query rồi in theo thứ tự xử lý, không giữ originalId.
10. Nén rank rồi dùng chênh rank như chiều dài tọa độ thật.
11. Quên thêm x của QUERY vào tập tọa độ nén.
12. Fenwick thiếu cộng1 khi chuyển rank0 sang 1-based.
13. Prefix tại x=R không tính delta kết thúc.
14. Áp dụng future UPDATE trước QUERY quá khứ.
15. Gộp mọi QUERY cùng x bất chấp thời gian khác nhau.
16. Không bỏ qua range update rỗng.
17. Co cửa sổ Mo trước khi đã add, xóa absent.
18. Dùng ++R và R++ sai trong thao tác Mo.
19. Giữ frequency=0 trong map và đếm distinct sai.
20. Frequency âm mà không assert.
21. Mo cửa sổ có tổng đúng nhưng endpoints sai.
22. Mo tĩnh áp vào mảng có update mà không có chiều thời gian.
23. Quên ghi `answer[q.id]`.
24. Dùng DSU thường để xóa cạnh.
25. Dùng `[add,remove]` thay `[add,remove)`.
26. Dùng `[add+1,remove)` mà bỏ trạng thái sau ADD.
27. Không normalize (u,v) và (v,u).
28. Cho duplicate ADD mà không quy định multigraph.
29. Cho unmatched REMOVE.
30. Path compression thay parent mà không được rollback.
31. Quên snapshot trước union của node.
32. Không rollback sau xử lý nhánh trái.
33. Đưa cạnh vào mọi node giao đoạn thay vì canonical nodes.
34. Query connected(u,u)=false khi đồ thị rỗng.
35. Không xử lý n=0/T=0.
36. Tự đoán thứ tự các sự kiện same-timestamp.
37. Chỉ so multiset answer, không so ID/time.
38. Tổng weight/delta overflow nhưng coi như kết quả hợp lệ.
39. Đưa oracle O(T²) vào thuật toán production rồi vẫn báo complexity nhanh.
40. Test chỉ trạng thái cuối, không test sau từng QUERY.
41. Không phân biệt thời gian vật lý và index thao tác.
42. Đổi comparator làm thay ngữ nghĩa bài toán.
43. Tin random tests thay chứng minh invariant.
44. Không công bố liệu QUERY dùng phiên bản trước hay sau cùng timestamp.

## 21. Bài tập có đáp án

### Bài 1 — Nửa mở

`[2,5)` chứa chỉ số nào? **Đáp án:** 2,3,4.

### Bài 2 — Độ dài

Độ dài `[2,5)`? **Đáp án:** 3.

### Bài 3 — Rỗng

`[4,4)` chứa mấy phần tử? **Đáp án:** 0.

### Bài 4 — Biên cuối

Với n=8, `[8,8)` có hợp lệ không? **Đáp án:** Có, rỗng.

### Bài 5 — Đóng sang nửa mở

`[2,5]` nguyên chuyển thành gì? **Đáp án:** `[2,6)`.

### Bài 6 — Overflow

R=MAX_INT, `R+1` trong int có an toàn không? **Đáp án:** Không, cần long.

### Bài 7 — Đúng R

Đoạn `[0,3)` có chứa x=3? **Đáp án:** Không.

### Bài 8 — Hai đoạn

`[0,3)` và `[3,6)` có chung phần tử? **Đáp án:** Không.

### Bài 9 — Tie order

QUERY tại x=3 chạy sau gì? **Đáp án:** END và START ở x=3 theo hợp đồng.

### Bài 10 — Interval rỗng

`[3,3)` weight100 có tác động ở x=3? **Đáp án:** Không.

### Bài 11 — Sweep ví dụ

Trong bốn interval mẫu, query x=3? **Đáp án:** 1.

### Bài 12 — Sweep biên

Trong mẫu, query x=5? **Đáp án:** −1.

### Bài 13 — Thứ tự output

Có được in query theo thứ tự sort? **Đáp án:** Không nếu contract yêu cầu thứ tự input.

### Bài 14 — Nén

Tọa độ `[-2,0,3,5]` nén thành bao nhiêu rank? **Đáp án:** 4.

### Bài 15 — Rank và khoảng cách

Rank(5)−rank(3)=1 có nghĩa tọa độ cách1? **Đáp án:** Không, khoảng cách thật2.

### Bài 16 — Diff

ADD `[0,3)` +7 tạo delta gì? **Đáp án:** +7 tại0, −7 tại3.

### Bài 17 — Prefix query

Query điểm x=R phải tính delta END ở R? **Đáp án:** Có.

### Bài 18 — Timeline

Sau UPDATE `[−2,3)` +5, query x=3? **Đáp án:** 0.

### Bài 19 — Cùng x khác thời gian

Trong mẫu, x=3 tại t=2 và t=6 lần lượt? **Đáp án:** 0 và −2.

### Bài 20 — Future update

UPDATE ở t=10 có tác động QUERY t=7? **Đáp án:** Không.

### Bài 21 — Mo rỗng

Distinct `[3,3)`? **Đáp án:** 0.

### Bài 22 — Mo đầy

Trong mảng `[4,1,4,2,1,3,2,3]`, distinct `[0,8)`? **Đáp án:** 4.

### Bài 23 — Mo `[2,7)`

Distinct bằng bao nhiêu? **Đáp án:** 4.

### Bài 24 — Mo cuối

Distinct `[8,8)` với n=8? **Đáp án:** 0.

### Bài 25 — Frequency

Tổng count trong Mo bằng gì? **Đáp án:** `curR−curL`.

### Bài 26 — Remove

Frequency từ1 về0? **Đáp án:** Xóa khóa, giảm distinct.

### Bài 27 — Mo ID

Sau sort query, lưu đáp án ở đâu? **Đáp án:** `answer[originalId]`.

### Bài 28 — Mo có updates

Dùng nguyên Mo tĩnh được không? **Đáp án:** Không.

### Bài 29 — Đời cạnh

ADD t=3, REMOVE t=9, active interval? **Đáp án:** `[3,9)`.

### Bài 30 — Sau REMOVE

Tại t=9 cạnh còn không? **Đáp án:** Không.

### Bài 31 — Rollback

Vì sao không path compress? **Đáp án:** Phải log thay đổi parent nếu muốn rollback đúng.

### Bài 32 — Snapshot

Sau node DFS, rollback về đâu? **Đáp án:** Mark trước các union của node.

### Bài 33 — Vô hướng

(2,5) và (5,2) là mấy cạnh? **Đáp án:** Một.

### Bài 34 — Self-connectivity

connected(4,4) khi không cạnh? **Đáp án:** True.

### Bài 35 — Connectivity t10

Ở t=10, connected(1,4)? **Đáp án:** True.

### Bài 36 — Connectivity t12

Ở t=12, connected(1,4)? **Đáp án:** False.

### Bài 37 — Prefix sum

a=[2,5,7,1], sum `[1,3)`? **Đáp án:** 12.

### Bài 38 — Comparator

Dùng `Integer.compare` thay phép trừ vì sao? **Đáp án:** Tránh overflow.

### Bài 39 — Query after same timestamp

Có một thứ tự mặc định cho QUERY và UPDATE cùng timestamp? **Đáp án:** Không, phải dựa đặc tả.

### Bài 40 — Oracle

Vì sao so BFS theo từng query DSU? **Đáp án:** Để kiểm độc lập tập cạnh active ở đúng thời điểm.

## 22. Checklist QA trước khi kết luận đúng

1. Đã công bố đoạn đóng/nửa mở?
2. Đã công bố 0-based/1-based?
3. Có xử lý `[L,L)`?
4. Có cho phép R=n mà không truy cập a[n]?
5. Có validate L≤R?
6. Có chống overflow R+1?
7. Có test x=L và x=R?
8. Có test L−1/R+1?
9. Có quy định query đọc trước/sau update?
10. Có phase ordering END/START/QUERY?
11. Có loại event của đoạn rỗng?
12. Comparator có tránh phép trừ overflow?
13. Có giữ originalId?
14. Output có trả theo originalId?
15. Sweep active có đúng theo oracle?
16. Có interval liền kề cùng endpoint?
17. Có trọng số âm/0?
18. Coordinate compression có sort+unique?
19. Có thu cả tọa độ query?
20. Có tránh coi rank là độ dài?
21. Fenwick có 1-based nội bộ?
22. ADD có +delta tại L/−delta tại R?
23. Prefix query tính inclusive?
24. Update rỗng có là no-op?
25. Timeline replay đúng thứ tự thao tác?
26. Có test cùng x ở hai thời điểm?
27. Có oracle timeline độc lập?
28. Mo window có dùng `[L,R)`?
29. Mo mở rộng trước co?
30. Mo có không frequency âm?
31. Mo xóa key count0?
32. Mo có test `[0,0)`/`[n,n)`?
33. Mo có giữ originalId sau sort?
34. Có oracle HashSet?
35. Có tránh dùng Mo tĩnh cho update?
36. Edge vô hướng đã normalize?
37. ADD/REMOVE đã validate?
38. Cạnh active trên `[add,remove)`?
39. Open edge có end=T?
40. Cây thời gian dùng canonical intervals?
41. DSU rollback không nén đường đi?
42. Có snapshot và rollback mỗi node?
43. Có query ngay sau ADD/REMOVE?
44. Có query connected(u,u)?
45. Có test nối–tách–nối lại?
46. Có oracle BFS từng query?
47. Có xử lý input rỗng?
48. Có kiểm overflow weight/delta?
49. Có phân biệt timestamp với operation index?
50. Có tách oracle khỏi thuật toán nhanh?
51. Có đối chiếu từng query theo ID/time?
52. Có chứng minh invariant thay vì chỉ tin test?

**Kết luận:** Tính đúng của truy vấn ngoại tuyến phụ thuộc vào **đúng tập phần tử `[L,R)`**, **đúng pha sự kiện**, và **đúng phiên bản dữ liệu tại mỗi query**. Sweep, Fenwick, Mo và DSU rollback là bốn cách tái tạo trạng thái khác nhau; tất cả đều cần bản hợp đồng biên rõ ràng, giữ ID gốc, và kiểm với oracle đơn giản đúng tại ranh giới hoặc sau thao tác cập nhật/xóa.
