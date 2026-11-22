# Loại bỏ trạng thái tương đương và trạng thái bị trội

Trong **quy hoạch động (dynamic programming – DP)**, một bài toán có thể sinh rất nhiều trạng thái trung gian. Đôi khi hai lịch sử khác nhau dẫn đến **cùng một thông tin đủ để quyết định phần việc còn lại**; đôi khi một trạng thái tuy khác nhưng **không thể tạo ra kết quả tốt hơn** trạng thái khác. Nếu giữ tất cả, thuật toán có thể lãng phí rất nhiều thời gian và bộ nhớ. Nếu xóa sai, thuật toán sẽ bỏ mất đáp án tối ưu.

Hai kỹ thuật thuộc nhóm **tối ưu quy hoạch động** là:

- **Gộp trạng thái tương đương (equivalent states):** giữ một đại diện khi những trạng thái có cùng khả năng mở rộng và cùng kết quả liên quan đến mục tiêu.
- **Loại trạng thái bị trội (dominance pruning):** bỏ một trạng thái khi có trạng thái khác không tiêu tốn nhiều tài nguyên hơn, có giá trị mục tiêu không kém, và **mọi quyết định tương lai của trạng thái bị bỏ đều có thể được mô phỏng**.

Bài học dùng bài toán **ba lô 0/1 (0/1 knapsack)** để trình bày quan hệ trội và **biên Pareto (Pareto frontier/skyline)**. Sau đó mở rộng sang đường đi với tài nguyên, lập lịch, DP bitmask, bài toán đếm phương án và phục dựng nghiệm. Chương trình Java 17+ cuối bài cài đặt đầy đủ bộ lọc, in trạng thái sau từng lượt, đối chiếu kết quả với DP chuẩn và chạy bộ kiểm thử tái lập.

## 1. Bài toán mô hình: ba lô 0/1

Có `n` món đồ. Món `i` có trọng lượng nguyên dương `w[i]`, giá trị không âm `v[i]`. Một món có thể được chọn **không quá một lần**. Ba lô có sức chứa nguyên không âm `C`. Ta cần chọn một tập món sao cho:

~~~text
sum(weight of chosen items) <= C
maximize sum(value of chosen items)
~~~

Tập rỗng luôn được phép, có trọng lượng 0 và giá trị 0. Bài toán này **khác** bài bắt buộc dùng hết dung lượng, khác ba lô không giới hạn và khác bài đếm mọi tập món hợp lệ.

Sau khi xét xong `i` món đầu, mỗi phương án từng phần được mô tả bằng:

~~~text
(i, usedWeight, totalValue, history)
~~~

- `i`: đã xử lý các món có chỉ số từ 0 đến `i-1`. Các món `i..n-1` là lựa chọn còn lại.
- `usedWeight`: tài nguyên đã dùng, phải không vượt `C`.
- `totalValue`: giá trị hiện tại.
- `history`: tập món đã chọn hoặc con trỏ để phục dựng nghiệm. Nếu chỉ hỏi **giá trị tối ưu**, có thể không cần giữ history.

Điều kiện **cùng lớp i** là rất quan trọng. Hai trạng thái ở hai lớp khác nhau, dù cùng `usedWeight` và `totalValue`, có thể **khác tập món còn được phép chọn**, nên không được tự động gộp.

### Sinh lớp tiếp theo

Từ mỗi trạng thái ở lớp `i`, có hai lựa chọn đối với món i:

1. **Không chọn:** giữ nguyên trọng lượng và giá trị.
2. **Chọn:** nếu `usedWeight+w[i] <= C`, tăng trọng lượng thêm `w[i]`, tăng giá trị thêm `v[i]`.

Tất cả trạng thái của lớp `i+1` phải được sinh từ **lớp i cũ**. Nếu vừa tạo trạng thái mới rồi dùng ngay nó để chọn lại món i, ta đã biến ba lô 0/1 thành bài toán cho phép dùng món nhiều lần.

## 2. Tương đương theo tương lai, không chỉ theo hình thức

Hai lịch sử tại cùng lớp `i` có thể được xem là **tương đương để tối ưu** khi chúng cho cùng khả năng tiếp tục và cùng đóng góp ban đầu đối với hàm mục tiêu.

Ví dụ có hai món giống nhau:

~~~text
item 0: weight=2, value=5
item 1: weight=2, value=5
capacity=2

Chọn item 0, bỏ item 1 -> (i=2, weight=2, value=5)
Bỏ item 0, chọn item 1 -> (i=2, weight=2, value=5)
~~~

Nếu chỉ cần **giá trị tối ưu**, cả hai lịch sử còn cùng những món tương lai, cùng trọng lượng đã dùng và cùng giá trị. Giữ một đại diện là đủ.

Nhưng nếu yêu cầu **đếm số cách chọn tập món tối ưu**, hai nghiệm `{0}` và `{1}` là **hai tập khác nhau**. Gộp rồi chỉ giữ “1 cách” sẽ sai; trạng thái đếm phải **cộng số cách** của những lịch sử tương ứng. Nếu cần liệt kê tất cả nghiệm, không thể xóa mất lịch sử riêng biệt.

| Đầu ra yêu cầu | Gộp hai lịch sử cùng trạng thái |
| --- | --- |
| Chỉ giá trị tối ưu | Giữ một đại diện. |
| Một tập món tối ưu bất kỳ | Giữ một đại diện **kèm đường truy vết đúng**. |
| Số nghiệm tối ưu | Gộp giá trị nhưng phải **tổng hợp số cách**. |
| Tất cả nghiệm tối ưu | Không được bỏ các lịch sử cần liệt kê. |
| Một nghiệm có tie-break đặc biệt | Đại diện phải giữ đúng điều kiện phụ của tie-break. |

**Memoization** cũng dùng trạng thái đủ thông tin để tránh tính lặp, nhưng tập trung vào **tránh giải lại cùng bài toán con**. Gộp trạng thái và dominance pruning liên quan đến việc **giảm tập các phương án từng phần cần lưu**. Không nên xem hai khái niệm là hoàn toàn đồng nhất.

## 3. Định nghĩa trạng thái bị trội

Ở **cùng lớp i** của bài ba lô 0/1, xét hai trạng thái:

~~~text
A = (weightA, valueA)
B = (weightB, valueB)

A dominates B if:
    weightA <= weightB
    valueA >= valueB
and at least one inequality is strict.
~~~

Nếu cả trọng lượng và giá trị **bằng nhau**, ta gộp hai đại diện tương đương. Nếu A dùng **không nhiều trọng lượng hơn** mà đã thu **không ít giá trị hơn**, B có thể bị loại khi mục tiêu tối đa giá trị dưới ràng buộc trọng lượng **không vượt C**.

Ví dụ:

~~~text
A = (2, 5)
B = (3, 4)

2 <= 3 and 5 >= 4
=> A trội B; bỏ B là an toàn.
~~~

Nhưng `P=(0,0)` và `Q=(2,5)` **không so sánh được**: P ít trọng lượng hơn nhưng ít giá trị hơn. P có thể dành sức chứa để lấy một món nặng và giá trị lớn ở lớp tiếp theo. Vì vậy không được chỉ dựa vào `totalValue` hiện tại để xóa P.

### Chứng minh loại B không mất nghiệm tối ưu

Giả sử A trội B và hai trạng thái có **cùng tập món tương lai**. Xét **một tập bất kỳ X** gồm những món còn được phép chọn, sao cho mở rộng B bằng X là hợp lệ:

~~~text
weightB + weight(X) <= C
~~~

Vì `weightA <= weightB`, suy ra:

~~~text
weightA + weight(X)
    <= weightB + weight(X)
    <= C
~~~

Do đó **cùng lựa chọn X cũng hợp lệ khi xuất phát từ A**. Mặt khác, vì `valueA >= valueB`:

~~~text
valueA + value(X) >= valueB + value(X)
~~~

Vậy với **mọi cách hoàn thiện từ B**, đều có một cách hoàn thiện từ A **không kém về giá trị**. Xóa B không thể làm mất giá trị tối ưu toàn cục.

Chứng minh vừa dùng bốn giả thiết: **cùng tương lai**, tài nguyên nhỏ hơn không gây bất lợi, tài nguyên/điểm số **được cộng theo cùng quy tắc**, và mục tiêu cho phép **dùng không hết sức chứa**. Nếu một trong những giả thiết ấy thay đổi, cần chứng minh lại quan hệ trội.

## 4. Biên Pareto: tập trạng thái không bị trội

**Biên Pareto (Pareto frontier)** gồm các trạng thái không bị một trạng thái khác trội. Với trọng lượng cần **nhỏ** và giá trị cần **lớn**, những điểm trên biên thể hiện các đánh đổi chưa thể loại an toàn.

Cho các trạng thái:

~~~text
(0,0), (2,5), (3,4), (4,7), (5,9), (6,12)
~~~

Trạng thái `(3,4)` bị `(2,5)` trội. Các điểm còn lại đều có trọng lượng tăng đi kèm giá trị tăng, nên không thể so sánh trội nhau:

~~~text
Frontier = (0,0), (2,5), (4,7), (5,9), (6,12)
~~~

Không được tự động xóa `(0,0)`: nó có **tài nguyên còn lại nhiều nhất**, dù giá trị hiện tại là 0.

### Cách lọc nhanh khi chỉ có weight và value

Bộ lọc Pareto cho hai đại lượng này có thể thực hiện bằng hai pha:

1. **Cùng trọng lượng:** giữ trạng thái có giá trị **cao nhất**; nếu hai trạng thái có cùng trọng lượng và giá trị, giữ một đại diện theo quy tắc phá hòa.
2. **Trọng lượng tăng dần:** duyệt các trạng thái đã gộp theo `weight` tăng; chỉ giữ điểm có `value` **cao hơn mọi điểm nhẹ hơn đã gặp**.

Tại một trọng lượng đang xét, nếu giá trị `<=bestValueSeen` thì một điểm có trọng lượng **không lớn hơn** đã đạt giá trị **không thấp hơn**; trạng thái hiện tại bị trội. Ngược lại, một điểm đạt kỷ lục giá trị mới **không bị bất kỳ điểm nhẹ hơn nào trội**.

Sau lọc, khi trọng lượng tăng, **giá trị tăng nghiêm ngặt**. Điều đó là một bất biến hữu ích để kiểm tra cài đặt.

## 5. Mô phỏng lớp DP trên ví dụ cụ thể

Xét bốn món:

| Chỉ số | Trọng lượng | Giá trị |
| ---: | ---: | ---: |
| 0 | 2 | 5 |
| 1 | 3 | 4 |
| 2 | 4 | 7 |
| 3 | 5 | 8 |

Sức chứa `C=7`, mỗi món chọn tối đa một lần.

**Ban đầu:**

~~~text
S0: [(0,0)]
~~~

**Sau món 0 (2,5):**

~~~text
Ứng viên: (0,0), (2,5)
S1:       (0,0), (2,5)
Số trạng thái: 2
~~~

**Sau món 1 (3,4):**

~~~text
Ứng viên: (0,0), (2,5), (3,4), (5,9)
Loại:     (3,4), vì bị (2,5) trội
S2:       (0,0), (2,5), (5,9)
Số trạng thái: 3
~~~

**Sau món 2 (4,7):** có thể sinh `(4,7)` từ rỗng và `(6,12)` từ `(2,5)`. Không thể lấy thêm món này từ `(5,9)` vì tổng trọng lượng thành 9 > 7.

~~~text
S3: (0,0), (2,5), (4,7), (5,9), (6,12)
Số trạng thái: 5
~~~

**Sau món 3 (5,8):** trạng thái mới `(5,8)` bị trạng thái `(5,9)` có sẵn trội. Trạng thái `(7,13)` từ `(2,5)` được giữ.

~~~text
S4: (0,0), (2,5), (4,7), (5,9), (6,12), (7,13)
Số trạng thái: 6
~~~

Kết quả tối ưu là **13**, bằng cách chọn **món 0 và món 3**: trọng lượng `2+5=7`, giá trị `5+8=13`. Số trạng thái còn sống sau từng món là **[2,3,5,6]**, nhưng đó không phải số nghiệm tối ưu hoặc số cách chọn món.

Đặc biệt, ở S2 trạng thái `(5,9)` phải được giữ dù nặng hơn `(2,5)`, vì nó **có giá trị lớn hơn**. Chỉ giữ một trạng thái “tốt nhất tạm thời” sẽ làm mất những đánh đổi có thể dẫn đến nghiệm tốt ở tương lai.

## 6. Giả mã sinh trạng thái và loại trội

~~~text
ALGORITHM KNAPSACK_FRONTIER_01(weights, values, C)
    REQUIRE C >= 0
    REQUIRE weights[i] > 0, values[i] >= 0
    frontier <- [(weight=0, value=0)]

    FOR i FROM 0 TO n-1 DO
        candidates <- COPY(frontier)  // Bỏ món i.

        FOR EACH state s IN frontier DO
            IF s.weight + weights[i] <= C THEN
                APPEND (
                    weight = s.weight + weights[i],
                    value = s.value + values[i]
                ) TO candidates
            END IF
        END FOR

        bestByWeight <- EMPTY MAP

        FOR EACH s IN candidates DO
            IF s.weight NOT IN bestByWeight OR
               s.value > bestByWeight[s.weight].value THEN
                bestByWeight[s.weight] <- s
            END IF
        END FOR

        SORT bestByWeight STATES BY weight ASCENDING

        nextFrontier <- EMPTY LIST
        bestValueSeen <- NEGATIVE_INFINITY

        FOR EACH s IN sorted states DO
            IF s.value > bestValueSeen THEN
                APPEND s TO nextFrontier
                bestValueSeen <- s.value
            END IF
        END FOR

        frontier <- nextFrontier
    END FOR

    RETURN max value in frontier
END ALGORITHM
~~~

**Bất biến sau mỗi lớp i:** với mọi trạng thái khả thi đã hình thành từ i món, tồn tại trong frontier một trạng thái có trọng lượng **không lớn hơn** và giá trị **không thấp hơn**. Như vậy, mọi phương án tương lai từ trạng thái bị loại có thể được một đại diện giữ lại thay thế mà không giảm điểm số.

**Cơ sở:** lớp 0 có đúng `(0,0)`.

**Bước quy nạp:** giả sử invariant đúng ở lớp i. Khi xét món i, mỗi trạng thái có hai lựa chọn bỏ/chọn. Nếu trạng thái X đã bị một trạng thái Y trội ở lớp i, bỏ cùng món i hoặc chọn cùng món i từ Y giữ được bất đẳng thức trọng lượng/giá trị và điều kiện sức chứa; vì thế không cần khôi phục X. Tạo đủ ứng viên từ những trạng thái được giữ và lọc dominance ở lớp i+1 tiếp tục bảo toàn tính chất. Khi xử lý hết n món, frontier chắc chắn còn một trạng thái đạt **giá trị tối ưu**.

Lập luận này cũng cho thấy **vì sao không được sinh từ một frontier đang thêm trực tiếp**: lớp i+1 sẽ vô tình dùng một món nhiều lần, không còn ứng với phép mở rộng hợp lệ trong chứng minh.

## 7. Java 17+ chạy được: Pareto frontier và DP tham chiếu

Chương trình dùng `record State` bất biến lưu trọng lượng, giá trị, con trỏ tới trạng thái trước và chỉ số món vừa chọn. Khi bỏ món, nó giữ lại chính trạng thái cũ. Khi chọn món, nó tạo một node mới chỉ trỏ đến **trạng thái lớp trước**, vì vậy không dùng một món hai lần.

`TreeMap` giữ trạng thái tốt nhất tại mỗi trọng lượng theo thứ tự trọng lượng tăng. Sau đó bộ lọc chỉ giữ những điểm đạt **kỷ lục mới về giá trị**. `referenceKnapsack` là DP 0/1 thông thường quét dung lượng từ lớn xuống nhỏ. `verifyChosen` kiểm tra đường truy vết có tổng trọng lượng hợp lệ, giá trị đúng và không chọn trùng chỉ số. Bộ kiểm thử dùng seed cố định, tạo 200 đầu vào nhỏ và so sánh kết quả với DP tham chiếu.

Tạo tệp **`DominancePruningDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Random;
import java.util.TreeMap;

public class DominancePruningDemo {
    record State(int weight, long value, State previous, int pickedItem) {}
    record Result(long bestValue, List<Integer> items,
                  List<Integer> frontierSizes) {}

    private static void validate(int[] weights, long[] values,
                                 int capacity) {
        Objects.requireNonNull(weights, "weights");
        Objects.requireNonNull(values, "values");

        if (capacity < 0 || weights.length != values.length) {
            throw new IllegalArgumentException("Invalid dimensions");
        }

        for (int i = 0; i < weights.length; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException(
                        "Weights positive, values nonnegative");
            }
        }
    }

    private static List<State> prune(List<State> candidates) {
        TreeMap<Integer, State> bestByWeight = new TreeMap<>();

        // Cùng trọng lượng: giữ giá trị lớn nhất.
        // Hòa hoàn toàn: giữ đại diện gặp trước.
        for (State s : candidates) {
            State old = bestByWeight.get(s.weight());
            if (old == null || s.value() > old.value()) {
                bestByWeight.put(s.weight(), s);
            }
        }

        List<State> kept = new ArrayList<>();
        long bestValueSeen = Long.MIN_VALUE;

        // Duyệt trọng lượng tăng và bỏ giá trị không đạt kỷ lục.
        for (Map.Entry<Integer, State> entry :
                bestByWeight.entrySet()) {
            State s = entry.getValue();
            if (s.value() > bestValueSeen) {
                kept.add(s);
                bestValueSeen = s.value();
            }
        }
        return kept;
    }

    public static Result frontierKnapsack(int[] weights, long[] values,
                                          int capacity) {
        validate(weights, values, capacity);
        List<State> frontier = new ArrayList<>();
        frontier.add(new State(0, 0L, null, -1));
        List<Integer> sizes = new ArrayList<>();

        for (int item = 0; item < weights.length; item++) {
            // Sao chép các trạng thái BỎ món hiện tại.
            List<State> candidates = new ArrayList<>(frontier);

            // Chỉ duyệt frontier của lớp cũ khi CHỌN món hiện tại.
            for (State s : frontier) {
                if (s.weight() <= capacity - weights[item]) {
                    candidates.add(new State(
                            s.weight() + weights[item],
                            Math.addExact(s.value(), values[item]),
                            s, item));
                }
            }

            frontier = prune(candidates);
            sizes.add(frontier.size());
        }

        State best = frontier.get(0);
        for (State s : frontier) {
            if (s.value() > best.value()) {
                best = s;
            }
        }

        List<Integer> selected = new ArrayList<>();
        for (State cursor = best;
                cursor != null && cursor.pickedItem() >= 0;
                cursor = cursor.previous()) {
            selected.add(cursor.pickedItem());
        }
        Collections.reverse(selected);
        return new Result(best.value(), List.copyOf(selected),
                List.copyOf(sizes));
    }

    public static long referenceKnapsack(int[] weights, long[] values,
                                         int capacity) {
        validate(weights, values, capacity);
        if (capacity == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Capacity too large");
        }

        long[] dp = new long[capacity + 1];

        for (int item = 0; item < weights.length; item++) {
            for (int c = capacity; c >= weights[item]; c--) {
                dp[c] = Math.max(dp[c],
                        Math.addExact(dp[c - weights[item]],
                                      values[item]));
            }
        }
        return dp[capacity];
    }

    private static void verifyChosen(Result result, int[] weights,
                                     long[] values, int capacity) {
        boolean[] seen = new boolean[weights.length];
        long usedWeight = 0L;
        long totalValue = 0L;

        for (int i : result.items()) {
            if (i < 0 || i >= weights.length || seen[i]) {
                throw new AssertionError("Invalid reconstruction");
            }
            seen[i] = true;
            usedWeight += weights[i];
            totalValue = Math.addExact(totalValue, values[i]);
        }

        if (usedWeight > capacity ||
                totalValue != result.bestValue()) {
            throw new AssertionError("Invalid result");
        }
    }

    private static void printCase(String name, int[] weights,
                                  long[] values, int capacity) {
        Result r = frontierKnapsack(weights, values, capacity);
        verifyChosen(r, weights, values, capacity);
        System.out.println(name + "=" + r.bestValue()
                + " items=" + r.items()
                + " sizes=" + r.frontierSizes());
    }

    private static void crossCheck() {
        Random random = new Random(2026L);

        for (int test = 0; test < 200; test++) {
            int n = random.nextInt(8);
            int capacity = random.nextInt(16);
            int[] weights = new int[n];
            long[] values = new long[n];

            for (int i = 0; i < n; i++) {
                weights[i] = 1 + random.nextInt(8);
                values[i] = random.nextInt(16);
            }

            Result r = frontierKnapsack(weights, values, capacity);
            verifyChosen(r, weights, values, capacity);

            if (r.bestValue() !=
                    referenceKnapsack(weights, values, capacity)) {
                throw new AssertionError("Mismatch at test " + test);
            }
        }
        System.out.println("crossCheck=PASS (200 cases)");
    }

    public static void main(String[] args) {
        int[] weights = {2, 3, 4, 5};
        long[] values = {5, 4, 7, 8};

        printCase("main", weights, values, 7);
        System.out.println("reference=" +
                referenceKnapsack(weights, values, 7));

        printCase("sameWeight", new int[]{2, 2},
                new long[]{3, 5}, 2);
        printCase("equivalent", new int[]{2, 2},
                new long[]{5, 5}, 2);
        printCase("dominated", new int[]{2, 3},
                new long[]{5, 4}, 3);
        printCase("zeroCapacity", new int[]{2, 3},
                new long[]{5, 4}, 0);
        printCase("empty", new int[0], new long[0], 7);

        crossCheck();
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac DominancePruningDemo.java
java DominancePruningDemo
~~~

**Đầu ra chính xác:**

~~~text
main=13 items=[0, 3] sizes=[2, 3, 5, 6]
reference=13
sameWeight=5 items=[1] sizes=[2, 2]
equivalent=5 items=[0] sizes=[2, 2]
dominated=5 items=[0] sizes=[2, 2]
zeroCapacity=0 items=[] sizes=[1, 1]
empty=0 items=[] sizes=[]
crossCheck=PASS (200 cases)
~~~

**Giải thích từng kết quả:**

- `main`: chọn món 0 và 3 được tổng giá trị 13, dùng đúng trọng lượng 7; các kích thước frontier sau bốn lượt là 2, 3, 5, 6.
- `reference`: DP 0/1 dùng mảng cho cùng kết quả 13.
- `sameWeight`: hai món trọng lượng 2 có giá trị 3 và 5, sức chứa 2; giữ món chỉ số 1 vì nó có giá trị cao hơn.
- `equivalent`: hai món giống hệt trọng lượng/giá trị, sức chứa chỉ đủ một món. Hai lịch sử được gộp; cách phá hòa hiện tại chọn món 0.
- `dominated`: trạng thái `(weight=3,value=4)` bị `(weight=2,value=5)` trội; kết quả giữ món 0.
- `zeroCapacity`: mọi món nặng hơn 0, frontier luôn chỉ còn trạng thái rỗng.
- `empty`: không có món, giá trị tối ưu 0, danh sách đã chọn và danh sách kích thước frontier sau mỗi món đều rỗng.
- `crossCheck`: 200 trường hợp có seed xác định; chương trình chỉ in PASS sau khi tất cả đều khớp DP tham chiếu và đường truy vết không chọn trùng món.

Bộ lọc dùng `TreeMap` theo trọng lượng, không dùng phép trừ số nguyên dễ tràn trong comparator. `Math.addExact` báo tràn `long` thay vì âm thầm thay đổi giá trị tối ưu. Các phương pháp không sửa mảng `weights` hay `values` gốc.

## 8. Phân tích thời gian, bộ nhớ và trường hợp xấu

Gọi `F_i` là số trạng thái Pareto sau i món, `F_max=max(F_i)`. Tại mỗi lượt, số ứng viên không quá `2F_i`.

- Sinh ứng viên từ frontier cũ: **O(F_i)**.
- Gộp theo trọng lượng bằng `TreeMap`: **O(F_i log(F_i+1))**.
- Quét loại trạng thái bị trội: **O(F_i)**.
- Tổng thời gian: **O(sum_i F_i log(F_i+1))**, có chặn trên **O(n·F_max·log(F_max+1))**.
- Bộ nhớ cho riêng frontier và danh sách ứng viên của một lượt: **O(F_max)**.

Nếu trọng lượng nguyên và `0≤usedWeight≤C`, sau gộp không thể có hơn **C+1 trọng lượng khác nhau**. Nhưng nếu C rất lớn, điều đó không bảo đảm ít trạng thái.

**Pareto pruning không luôn nhanh.** Chọn n món có trọng lượng và giá trị lần lượt là `1,2,4,...,2^(n-1)`, đặt `C=2^n-1`. Mỗi tập con tạo một tổng trọng lượng khác nhau, và giá trị **bằng chính trọng lượng**. Một trạng thái nhẹ hơn luôn có giá trị thấp hơn, nên **không trạng thái nào trội trạng thái khác**. Có thể tồn tại **2^n trạng thái Pareto**.

So sánh với DP ba lô theo sức chứa:

| Phương pháp | Thời gian | Bộ nhớ DP chính | Khi phù hợp |
| --- | --- | --- | --- |
| DP mảng một chiều | **O(nC)** | **O(C)** | C đủ nhỏ để cấp mảng và quét mọi dung lượng. |
| Lưu frontier Pareto | **O(n·F_max·log(F_max+1))** chặn trên | **O(F_max)** nếu chỉ giữ cặp số | C lớn nhưng số trạng thái không bị trội nhỏ. |
| Vét cạn mọi tập con | **O(2^n)** phương án | Tùy cách duyệt | Làm nghiệm tham chiếu cho n nhỏ. |

**Phục dựng có chi phí riêng:** mã Java lưu `previous` cho các node bất biến. Một node bị loại khỏi frontier có thể vẫn được một node còn lại tham chiếu gián tiếp, nên số đối tượng lịch sử tồn tại có thể nhiều hơn frontier hiện thời; chặn trên có thể đạt **O(n·F_max)** đối tượng qua nhiều lượt. Nếu chỉ cần giá trị tối ưu, bỏ các con trỏ lịch sử sẽ tiết kiệm bộ nhớ.

Cả DP mảng và frontier này đều xử lý mỗi món một lần, nhưng mức độ hiệu quả phụ thuộc cách biểu diễn tài nguyên và phân phối trạng thái, không có một phương pháp thắng trong mọi trường hợp.

## 9. Các tình huống KHÔNG được áp dụng phép trội trên

### 9.1. Bắt buộc dùng đúng trọng lượng C

Quan hệ `weightA<=weightB` an toàn khi dùng **không vượt C**. Nếu buộc **dùng đúng C**, nhẹ hơn có thể là bất lợi vì các món còn lại không đủ để lấp phần chênh lệch.

Phản ví dụ rất cụ thể:

~~~text
Capacity phải dùng chính xác: C=6
Món 0 = (weight=2, value=10)
Món 1 = (weight=3, value=9)
Món 2 = (weight=3, value=0), chưa được xét
~~~

Sau khi xét hai món đầu, có các trạng thái `(0,0),(2,10),(3,9),(5,19)`. Nếu áp dụng quy tắc của bài **≤C**, trạng thái `(3,9)` sẽ bị `(2,10)` trội và bị xóa.

Nhưng với yêu cầu **đúng trọng lượng 6**, một cách hợp lệ là chọn **món 1 và món 2**: trọng lượng `3+3=6`, giá trị 9. Nếu xóa `(3,9)`, trạng thái `(2,10)` khi thêm món 2 chỉ có trọng lượng 5; trạng thái `(5,19)` thêm món 2 thì vượt 6; không còn trạng thái nào đủ đúng 6. Phép loại trội đã xóa mất nghiệm khả thi. Do vậy phải **thay quan hệ trội**, không dùng quy tắc của bài `≤C` cho bài `=C`.

### 9.2. Đếm tất cả phương án hoặc nghiệm tối ưu

Ở `{(2,5),(2,5)}` với sức chứa 2, chọn chỉ món 0 hoặc chỉ món 1 là **hai tập riêng biệt**. Nếu đề hỏi số tập tối ưu thì đáp án 2, không phải 1. Gộp hai lịch sử đồng trạng thái mà không giữ số cách sẽ sai.

### 9.3. Khác tập quyết định tương lai

Giả sử hai trạng thái có cùng `weight=2` và `value=5`, nhưng một trạng thái **chưa xét** món rất lợi `(weight=1,value=100)`, còn trạng thái kia đã xét và bỏ qua món ấy. Chúng **không tương đương**, vì khả năng mở rộng khác nhau. Tương tự, trong bài chọn đường đi không được thăm lặp đỉnh, trạng thái có thể phải giữ **tập đỉnh đã thăm**, không chỉ chi phí và vị trí.

### 9.4. Giữ K trạng thái theo heuristic

Chỉ giữ K trạng thái có giá trị cao nhất hoặc xóa điểm có trọng lượng lớn hơn một ngưỡng tùy ý **không phải** dominance pruning đã chứng minh. Đây có thể là heuristic/beam search và có thể **mất tối ưu**. Nếu chấp nhận xấp xỉ, phải nói rõ bảo đảm, sai số hoặc giới hạn của thuật toán.

**Branch-and-bound** lại là một kỹ thuật khác: cắt nhánh khi một **cận trên đã được chứng minh** không thể vượt đáp án tốt nhất hiện có. Không gọi mọi cách cắt nhánh là “loại trạng thái bị trội”.

## 10. Ứng dụng ngoài ba lô

### Đường đi với tài nguyên

Trong bài tìm đường từ nguồn đến đích với giới hạn nhiên liệu, tại **cùng một đỉnh u**, xét nhãn `A=(fuelUsedA,costA)` và `B=(fuelUsedB,costB)`. Nếu cần **tối thiểu chi phí**, và A dùng không nhiều nhiên liệu hơn, chi phí không cao hơn, thì A có thể trội B **nếu** mọi đường tiếp tục từ u đều khả dụng như nhau và tài nguyên/chi phí cộng độc lập. Mọi đường đi tiếp từ B đều có thể áp dụng từ A mà không vượt giới hạn và không đắt hơn.

Nếu hai nhãn ở **hai đỉnh khác nhau**, không được gộp chỉ vì giống chi phí và nhiên liệu. Các cạnh đi tiếp có thể khác.

### Lập lịch

Trong một mô hình có thể chờ, trạng thái `(finishTime,profit)` có thể bị trội bởi trạng thái **kết thúc sớm hơn hoặc bằng** và **lợi ích cao hơn hoặc bằng**, miễn mọi công việc còn lại như nhau và kết thúc sớm không tạo hình phạt. Nếu bài bắt buộc bắt đầu chính xác lúc nào đó, cấm chờ hoặc có chi phí chờ, cần xem xét lại.

### DP bitmask và vị trí

Ở TSP, trạng thái `dp[mask][last]` phụ thuộc vào **tập đã thăm** và **đỉnh hiện tại**. Hai đường đến cùng `mask,last` có thể gộp bằng cách giữ chi phí thấp nhất. Nhưng hai trạng thái có cùng chi phí mà **khác last** không tương đương: giá cạnh đi tới đỉnh kế tiếp có thể khác. Cũng không được tự kết luận mask nhỏ hơn trội mask lớn hơn.

### Nhiều tài nguyên

Nếu phải giữ cả **trọng lượng**, **thể tích** và **năng lượng**, một trạng thái chỉ trội trạng thái khác khi không kém về **mọi tiêu chí liên quan** (và cùng quyền lựa chọn tương lai). Quan hệ này là **thứ tự bộ phận**, thường có nhiều điểm không so sánh được. Với từ ba chiều trở lên, cách lọc trọng lượng tăng + running maximum của giá trị **không còn đủ**.

## 11. Phục dựng nghiệm và tie-break

Khi chỉ cần số tối ưu, một trạng thái có thể là cặp `(weight,value)`. Nếu cần **một tập món**, phải giữ thông tin nguồn gốc các phép chọn. Trong Java:

~~~text
State(weight, value, previous, pickedItem)
~~~

Khi chọn món i, trạng thái mới trỏ về một trạng thái **lớp trước**. Khi bỏ món i, giữ trạng thái cũ. Đi theo chuỗi `previous` từ nghiệm tối ưu sẽ thu các chỉ số món theo thứ tự giảm dần; đảo chuỗi cho thứ tự chọn tăng dần.

Trạng thái cần **bất biến** để một node đã lưu không bị thay lịch sử khi lọc những lớp tiếp theo. Nếu dùng một đối tượng mutable chia sẻ giữa các lớp rồi sửa `previous`, có thể vô tình tạo đường truy vết chọn lại một món hoặc khớp sai giá trị.

Nếu một bài đòi nghiệm **ít món nhất khi đồng giá trị**, hoặc nghiệm **từ điển nhỏ nhất**, phép loại trội phải tính tới tiêu chí phá hòa này. Việc giữ ngẫu nhiên một đại diện vẫn tìm đúng **giá trị tối ưu**, nhưng chưa chắc trả đúng nghiệm theo quy tắc phụ.

Một trạng thái cùng trọng lượng nhưng giá trị lớn hơn trội trạng thái giá trị thấp hơn đối với **mục tiêu chỉ tối đa tổng giá trị**. Nhưng nếu còn hàm mục tiêu phụ như giảm số món, cần mô hình hóa **thứ tự ưu tiên đa tiêu chí** một cách nhất quán.

## 12. Quy trình chứng minh và kiểm thử quy tắc cắt tỉa

Trước khi loại trạng thái ở một bài DP mới, thực hiện:

1. **Định nghĩa đủ trạng thái:** ghi rõ lớp/tiến độ, vị trí, mask, ngân sách, thời gian và các ràng buộc ảnh hưởng tương lai.
2. **Định nghĩa quan hệ trội:** với mọi thuộc tính, ghi rõ cần nhỏ hơn hay lớn hơn.
3. **Chứng minh khả năng mở rộng:** với **mọi** cách hoàn thiện X từ B, chỉ ra một cách hoàn thiện từ A không kém.
4. **Kiểm tra yêu cầu đầu ra:** giá trị tối ưu, một nghiệm hay đếm/đặc tả tie-break.
5. **So với lời giải tham chiếu:** dùng DP không cắt tỉa hoặc vét cạn cho bài nhỏ, kể cả các trường hợp biên.
6. **Theo dõi kích thước frontier:** phát hiện dữ liệu làm số trạng thái tăng rất lớn.
7. **Tính đủ bộ nhớ:** cả trạng thái đang hoạt động lẫn lịch sử/truy vết còn giữ.

Các ca kiểm thử quan trọng:

| Ca | Điều cần xác minh |
| --- | --- |
| Không có món | Đáp án 0, frontier chỉ có trạng thái khởi đầu. |
| Sức chứa 0 | Không món trọng lượng dương nào được chọn. |
| Hai món cùng trọng lượng, khác giá trị | Giữ đại diện giá trị cao hơn. |
| Hai món cùng trọng lượng và giá trị | Có thể gộp cho tối ưu; đếm cách phải giữ multiplicity. |
| Món nặng hơn nhưng ít giá trị hơn | Loại nếu cùng lớp và cùng tương lai. |
| Món nhẹ hơn nhưng ít giá trị hơn | Không được tự động loại. |
| Tất cả giá trị bằng 0 | Trạng thái rỗng đủ cho giá trị tối ưu. |
| Nhiều điểm Pareto không so sánh được | Không xóa điểm chỉ vì giá trị thấp hơn. |
| Yêu cầu dùng đúng C | Phải có quan hệ lọc khác; quy tắc `≤C` có thể sai. |

Kiểm thử ngẫu nhiên có seed cố định chỉ hỗ trợ phát hiện lỗi triển khai. **Chứng minh đúng tổng quát** vẫn đến từ lập luận mỗi trạng thái bị bỏ được một đại diện giữ lại mô phỏng không kém trong mọi phần mở rộng.

## 13. Sai lầm phổ biến

1. **So sánh trạng thái ở hai lớp khác nhau** mà không xét tập món còn lại.
2. **Chỉ dùng điểm số hiện tại** để chọn một trạng thái duy nhất, không giữ các đánh đổi về tài nguyên.
3. **Nhầm tương đương với bị trội:** cùng trọng lượng nhưng khác giá trị là dominance, không phải hai đại diện có cùng kết quả.
4. **Gộp trạng thái khi cần đếm cách** nhưng bỏ mất số lượng lịch sử.
5. **Dùng quy tắc trọng lượng nhẹ hơn cho bài bắt buộc đúng trọng lượng**, làm mất đường hoàn thiện hợp lệ.
6. **Dùng mảng candidates đang thêm làm nguồn cho cùng món**, khiến một món 0/1 có thể được chọn nhiều lần.
7. **Quên giới hạn sức chứa** trước khi sinh trạng thái chọn món.
8. **Không gộp cùng trọng lượng** trước bước quét skyline, giữ nhiều trạng thái thừa.
9. **Lọc running maximum khi chưa sắp theo trọng lượng**, loại nhầm điểm Pareto.
10. **Sử dụng sai dấu min/max** cho bài tối đa giá trị hoặc tối thiểu chi phí.
11. **Tự giả định frontier luôn nhỏ**, quên trường hợp có `2^n` trạng thái nondominated.
12. **Không tính bộ nhớ con trỏ lịch sử**, dù frontier chỉ lưu ít điểm.
13. **Không kiểm tra tràn số nguyên**, khiến quan hệ giá trị và thứ tự trội bị sai.
14. **Gộp nhãn ở hai vị trí khác nhau** trong đường đi có tài nguyên.
15. **Bỏ qua điều kiện phụ của tie-break**, trả nghiệm có giá trị đúng nhưng không đáp ứng yêu cầu thứ tự.
16. **Đánh đồng heuristic cắt bớt K nhãn với loại trội an toàn**, rồi tuyên bố tối ưu tuyệt đối.
17. **Không phân biệt một nghiệm tối ưu với số nghiệm tối ưu**, nhất là khi có món trùng.
18. **Cho rằng kiểm thử 200 lần thay thế chứng minh**, trong khi kiểm thử chỉ phát hiện một phần lỗi.

## 14. Bài tập có lời giải

**Bài 1.** Ở cùng lớp i, A=(weight 4,value 10), B=(weight 6,value 8). A có trội B trong bài ba lô `weight≤C` không? **Lời giải:** có, vì 4≤6 và 10≥8; mọi tập món còn lại khả thi từ B cũng khả thi từ A và có tổng giá trị không thấp hơn.

**Bài 2.** A=(0,0), B=(2,5). Có thể xóa A vì B có nhiều giá trị hơn không? **Lời giải:** không; A còn nhiều sức chứa hơn, nên có thể chọn một món rất nặng và giá trị cao ở tương lai.

**Bài 3.** Với hai món (2,5) và (3,4), C=7, frontier sau hai lượt là gì? **Lời giải:** `[(0,0),(2,5),(5,9)]`; trạng thái `(3,4)` bị `(2,5)` trội.

**Bài 4.** Với bốn món (2,5),(3,4),(4,7),(5,8) và C=7, tối ưu là bao nhiêu? **Lời giải:** 13, chọn món 0 và 3; frontier sau bốn món có 6 điểm.

**Bài 5.** Hai món giống nhau (2,5), C=2. Nếu hỏi số tập món tối ưu, đáp án bằng mấy? **Lời giải:** 2 tập, chọn chỉ món 0 hoặc chỉ món 1. Gộp hai lịch sử mà không cộng số cách sẽ sai.

**Bài 6.** Tại sao cùng trọng lượng nhưng giá trị lớn hơn có thể thay thế trạng thái giá trị nhỏ hơn? **Lời giải:** cả hai còn đúng lượng tài nguyên và tập quyết định tương lai giống nhau; mọi phần mở rộng từ trạng thái kém hơn có thể áp dụng cho trạng thái tốt hơn với tổng giá trị cao hơn.

**Bài 7.** Vì sao sau khi sắp trọng lượng tăng có thể bỏ giá trị không cao hơn `bestValueSeen`? **Lời giải:** đã có trạng thái nhẹ hơn hoặc bằng mà đạt giá trị không thấp hơn; trạng thái mới bị trội.

**Bài 8.** Với n món có trọng lượng=giá trị lần lượt 1,2,4,...,2^(n-1), C=2^n-1, frontier có thể lớn đến bao nhiêu? **Lời giải:** `2^n` điểm, vì mỗi tập con có tổng trọng lượng khác nhau và giá trị cũng bằng tổng trọng lượng; không cặp nào trội nhau.

**Bài 9.** Với bài buộc đúng C=6, các món (2,10),(3,9),(3,0), có được loại (3,9) vì (2,10) nhẹ hơn không? **Lời giải:** không; chỉ (3,9)+(3,0) tạo đủ trọng lượng 6, còn (2,10) cộng món cuối chỉ thành 5.

**Bài 10.** Hai nhãn đường đi có cùng nhiên liệu và chi phí, nhưng ở hai đỉnh khác nhau, có thể gộp không? **Lời giải:** không mặc định; các cạnh đi tiếp và đường tới đích có thể khác nhau.

**Bài 11.** Chỉ cần giá trị tối ưu thì có cần giữ `previous` không? **Lời giải:** không. Dùng frontier chỉ chứa trọng lượng và giá trị, tránh giữ nhiều node lịch sử.

**Bài 12.** Một thuật toán giữ 100 trạng thái có giá trị lớn nhất ở mỗi bước mà không xét trọng lượng. Nó có được bảo đảm tìm tối ưu không? **Lời giải:** không; đây là cắt tỉa heuristic, có thể bỏ mất điểm nhẹ hơn và lợi thế về tài nguyên.

**Bài 13.** Tại sao chỉ sinh nhãn chọn món i từ frontier lớp trước? **Lời giải:** vì trong 0/1 knapsack, mỗi món được chọn tối đa một lần; nếu dùng nhãn vừa sinh trong cùng lượt sẽ có thể chọn món i hai lần.

**Bài 14.** Một trạng thái dùng ít tài nguyên hơn nhưng có chi phí cao hơn có trội trạng thái khác trong bài tối thiểu chi phí không? **Lời giải:** chưa chắc; đó là một đánh đổi tài nguyên–chi phí không so sánh được.

## 15. Checklist khi tối ưu trạng thái DP

1. **Đầu ra là gì?** Giá trị tối ưu, một nghiệm, số nghiệm hay toàn bộ nghiệm?
2. **Trạng thái đã đủ thông tin về tương lai chưa?** Cùng lớp i, vị trí, tập còn lại và mọi ràng buộc quan trọng?
3. **Quan hệ trội đúng chiều chưa?** Tài nguyên muốn ít, lợi ích muốn nhiều hoặc chi phí muốn ít.
4. **Có chứng minh được phép thay thế mọi phần mở rộng không?** Nếu không, đừng xóa trạng thái.
5. **Ràng buộc dùng ≤C hay phải đúng =C?** Quan hệ trội có thể thay đổi hoàn toàn.
6. **Có gộp trọng lượng bằng nhau đúng cách không?** Giữ giá trị tốt nhất, hoặc cộng số cách nếu bài cần.
7. **Có giữ cả những trạng thái đánh đổi không so sánh được không?** Đó chính là nội dung frontier Pareto.
8. **Có tránh dùng lại một món 0/1 ngay trong cùng lượt không?** Chỉ sinh từ frontier lớp trước.
9. **Có kiểm soát chi phí O(F log F) và trường hợp F rất lớn không?** Pareto pruning không luôn nhanh hơn DP mảng.
10. **Có cần phục dựng không?** Nếu có, lưu lịch sử bất biến và tính đủ bộ nhớ.
11. **Có kiểm thử với DP tham chiếu hoặc vét cạn trên dữ liệu nhỏ chưa?** Chú ý trùng trạng thái, không có món, sức chứa 0.
12. **Có phân biệt cắt tỉa có chứng minh và heuristic xấp xỉ không?** Không tuyên bố tối ưu tuyệt đối cho quy tắc chưa được chứng minh.

**Ghi nhớ:** một trạng thái bị loại an toàn không phải vì nó “trông yếu”, mà vì **mọi cách hoàn thiện của nó đều có thể được một trạng thái còn lại mô phỏng không kém**. Hai lịch sử chỉ có thể gộp khi chúng **tương đương đối với thông tin tương lai và yêu cầu đầu ra**. Việc chứng minh điều này là cốt lõi của tối ưu quy hoạch động.
