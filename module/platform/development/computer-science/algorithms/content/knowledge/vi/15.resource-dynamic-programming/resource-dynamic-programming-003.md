# Ba lô có số lượng giới hạn

## 1. Phát biểu bài toán và ví dụ

Bài toán **ba lô có số lượng giới hạn (bounded knapsack)** cho n loại vật phẩm và sức chứa ba lô W. Loại i có trọng lượng nguyên wᵢ, giá trị vᵢ và số bản sao tối đa qᵢ. Cần chọn số bản sao nguyên xᵢ từ 0 đến qᵢ để tối đa tổng giá trị trong khi tổng trọng lượng không vượt W:

~~~text
Maximize  Σ xᵢ · vᵢ
Subject to Σ xᵢ · wᵢ ≤ W
           0 ≤ xᵢ ≤ qᵢ
           xᵢ nguyên
~~~

Ví dụ W=10:

| Loại | Trọng lượng | Giá trị | Số lượng có sẵn |
| --- | ---: | ---: | ---: |
| A | 3 | 6 | 2 |
| B | 4 | 7 | 2 |
| C | 2 | 3 | 3 |

Chọn 2A+1B dùng 2·3+4=10 trọng lượng, thu giá trị 2·6+7=**19**. Đó là giá trị tối ưu cho ví dụ này. Không thể chọn 3A vì q_A=2; không thể chọn ba B dù còn muốn tăng điểm vì q_B=2.

Đây là quy hoạch động theo **tài nguyên sức chứa**. Một trạng thái biểu diễn mức sức chứa cho phép, còn quyết định là chọn bao nhiêu bản sao một loại. Bài toán khác 0/1 knapsack (mỗi vật phẩm tối đa một bản sao) và complete/unbounded knapsack (cho phép chọn không giới hạn trong sức chứa).

## 2. Hợp đồng và tiền điều kiện

Trong bài và chương trình Java 17:

- W là số nguyên không âm; mỗi loại có wᵢ **nguyên dương**, qᵢ nguyên không âm.
- Giá trị vᵢ có thể âm, bằng 0 hoặc dương.
- Được phép chọn **tập rỗng** với trọng lượng 0, giá trị 0.
- Chỉ yêu cầu **trọng lượng ≤ W**, không buộc dùng hết W.
- Đầu ra gồm tổng giá trị lớn nhất; khi cần truy vết, trả thêm số bản sao mỗi loại và tổng trọng lượng thực tế.
- Hai loại được phân biệt theo vị trí đầu vào, ngay cả khi trọng lượng/giá trị giống nhau.
- Giữ nguyên danh sách đầu vào. Nếu W quá lớn để cấp phát bảng, bài toán cần phương án tài nguyên khác.
- Khi giá trị trung gian vượt kiểu số đang sử dụng, phải báo lỗi hoặc dùng kiểu số lớn, không lặng lẽ để tràn.

Bản triển khai **không hỗ trợ wᵢ=0**: nó cần phép chia W/wᵢ để cắt hạn mức hiệu dụng. Đối với bounded knapsack tổng quát, loại trọng lượng 0 có thể tiền xử lý riêng: nếu giá trị dương, chọn hết qᵢ bản sao; nếu không dương, bỏ khi cho phép chọn rỗng. Trọng lượng âm không thuộc mô hình tài nguyên chuẩn.

Với mục tiêu ≤W, vật phẩm có vᵢ<0 không giúp ích: bỏ nó vẫn hợp lệ và cho giá trị tốt hơn. Vật phẩm vᵢ=0 cũng không làm tăng giá trị; ví dụ chọn quy ước **bỏ các loại có giá trị không dương**. Quy tắc đó không dùng được nếu yêu cầu **đúng W** hoặc phải chọn một số lượng tối thiểu.

## 3. Không nhầm với 0/1 và unbounded knapsack

| Bài toán | Số bản sao mỗi loại | Hướng cập nhật DP một chiều |
| --- | --- | --- |
| 0/1 | 0 hoặc 1 | Giảm dần sức chứa để không dùng lại |
| Unbounded | Không hạn chế ngoài sức chứa | Tăng dần để cho phép dùng lại |
| Bounded | 0 đến qᵢ | Xử lý hạn mức bằng số bản sao hoặc nhóm nhị phân |

Giả sử chỉ có một loại w=2, v=5, W=6:

- Nếu 0/1, kết quả 5.
- Nếu bounded với q=2, kết quả 10.
- Nếu unbounded, kết quả 15.

Dùng vòng cập nhật **tăng dần** như unbounded cho một loại bounded sẽ cho phép số bản sao vượt qᵢ. Đây là lỗi rất thường gặp.

## 4. Công thức DP theo loại và sức chứa

Đặt F[i][c] là tổng giá trị lớn nhất với **i loại đầu**, khi được phép dùng **không quá c đơn vị trọng lượng**. Trạng thái gốc:

~~~text
F[0][c] = 0, với 0 ≤ c ≤ W
~~~

Bởi vì tập rỗng là một nghiệm hợp lệ ở mọi sức chứa.

Với loại i có wᵢ>0, vᵢ, qᵢ:

~~~text
F[i][c] =
    max ( F[i-1][c-k*wᵢ] + k*vᵢ )
    với k = 0..min(qᵢ, floor(c/wᵢ))
~~~

Chọn k=0 nghĩa là bỏ loại i. Chọn k>0 dùng k bản sao và để lại sức chứa c−k·wᵢ cho **những loại trước đó**. Vì công thức luôn tham chiếu F[i−1], nó không dùng lại loại i ngoài số k đã quyết định.

Ví dụ loại A: w=3, v=6, q=2, tại c=7:

~~~text
F[i][7] = max(
    F[i-1][7],
    F[i-1][4] + 6,
    F[i-1][1] + 12
)
~~~

Không được thử k=3. Không được truy cập sức chứa âm.

**Chứng minh truy hồi:** một nghiệm hợp lệ dùng một số k cụ thể trong khoảng đã cho. Cố định k thì phần vật phẩm còn lại chỉ lấy từ i−1 loại, với sức chứa c−k·wᵢ; theo định nghĩa F, lựa chọn tối ưu cho phần còn lại là F[i−1][c−k·wᵢ]. Lấy max trên tất cả k hợp lệ bao trùm mọi nghiệm và không tạo nghiệm không hợp lệ.

## 5. Giải trực tiếp và giới hạn hiệu dụng

Cách cài đặt rõ nhất là hai hàng previous/current; với mỗi i, c duyệt mọi k theo công thức trên. Có thể chỉ giữ hai hàng O(W) bộ nhớ khi cần mỗi giá trị tối ưu.

Cận thời gian:

~~~text
O(W * Σᵢ (min(qᵢ, floor(W/wᵢ)) + 1))
~~~

Nếu số bản sao nhiều, số lựa chọn k khiến giải thuật chậm. Ta có thể cắt giảm hạn mức trước:

~~~text
effectiveᵢ = min(qᵢ, floor(W / wᵢ))
~~~

Không nghiệm nào dùng quá W/wᵢ bản sao vì riêng trọng lượng loại đó đã vượt W. Vì vậy thay qᵢ bằng effectiveᵢ **không làm mất nghiệm khả thi**.

Một cách đơn giản nữa là biến mỗi bản sao thành một vật phẩm 0/1 rồi dùng vòng cập nhật giảm dần. Nó đúng nhưng tốn O(W·Σ effectiveᵢ) thời gian. Với qᵢ=1.000.000.000 mà W=3, w=1, chỉ cần xét 3 bản sao hiệu dụng, không phải một tỷ; song khi W lớn vẫn nên dùng kỹ thuật nhanh hơn.

## 6. Phân rã nhị phân để giảm về 0/1 knapsack

**Binary splitting** thay t bản sao hiệu dụng bằng các **nhóm** kích thước 1,2,4,8,… và một nhóm phần dư. Mỗi nhóm là một vật phẩm 0/1 độc lập:

~~~text
groupWeight = copies * wᵢ
groupValue  = copies * vᵢ
~~~

Ví dụ t=13 được tách thành các nhóm có số bản sao [1,2,4,6]. Chọn/bỏ mỗi nhóm biểu diễn được **mọi số nguyên từ 0 tới 13**, không vượt 13 vì tổng kích thước nhóm bằng 13.

Giải thích: các nhóm 1,2,4,…,2^(h−1) biểu diễn được mọi số trong [0,2^h−1]. Nhóm dư r≤2^h bổ sung đoạn [r,r+2^h−1]; hai đoạn giao nhau hoặc nối tiếp nên phủ đủ [0,t].

Mỗi loại được tách thành O(log(t+1)) nhóm, thay cho t bản sao. Gọi K là tổng số nhóm của các loại có giá trị dương. Khi đó bài toán trở thành **0/1 knapsack trên K nhóm**.

**Điểm rất quan trọng khi đếm số nghiệm:** biểu diễn các nhóm có thể không duy nhất. Với t=2, có hai nhóm [1,1]; chọn nhóm đầu hoặc nhóm sau đều là chọn **một bản sao của cùng loại**. Phân nhóm đúng để tối ưu giá trị, nhưng nếu đếm số cách chọn **số lượng từng loại**, không được áp dụng trực tiếp thuật toán đếm số nghiệm 0/1 trên các nhóm vì có thể đếm trùng nghiệm gốc.

## 7. DP một chiều trên các nhóm

Đặt dp[c] là giá trị tốt nhất khi trọng lượng không vượt c. Khởi tạo dp[c]=0 cho mọi c.

Với nhóm g có trọng lượng gw>0, giá trị gv:

~~~text
for c = W downTo gw:
    dp[c] = max(dp[c], dp[c-gw] + gv)
~~~

Vòng duyệt **giảm dần** là bắt buộc. Khi cập nhật dp[c], dp[c−gw] vẫn là giá trị của **giai đoạn trước nhóm g**, vì c−gw<c chưa được cập nhật ở lượt này. Do đó nhóm g chỉ được lấy tối đa một lần.

Nếu duyệt **tăng dần**, cùng một nhóm có thể được dùng nhiều lần trong một lượt cập nhật; giới hạn số bản sao bị phá.

Sau tất cả nhóm, đáp án là dp[W]. Vì dp[c] ứng với **trọng lượng không quá c**, ban đầu 0 cho phép nghiệm rỗng; không bắt buộc dùng đủ W. Đây là điểm khác với bài toán **exact-fill**.

## 8. Truy vết một nghiệm tối ưu

Để chỉ trả giá trị tối ưu, một mảng dp[W+1] đủ. Muốn biết mỗi loại đã lấy bao nhiêu bản sao, cần ghi lại quyết định **theo giai đoạn nhóm**.

Cách dễ kiểm tra:

1. Tạo bảng boolean take[g][c] cho mỗi nhóm g và sức chứa c.
2. Khi chọn nhóm g làm dp[c] **tăng nghiêm ngặt**, đánh dấu take[g][c]=true.
3. Khi hai lựa chọn **hòa giá trị**, giữ phương án trước, take[g][c] vẫn false.
4. Duyệt ngược g từ K−1 về 0, bắt đầu remaining=W.
5. Nếu take[g][remaining] là true, cộng copies của nhóm vào số bản sao loại tương ứng và giảm remaining đi groupWeight.

Bảng take ghi lại lựa chọn của **mỗi giai đoạn**. Không được chỉ lưu một mảng parent[c] trỏ về những trạng thái dp tiếp tục bị ghi đè về sau: các con trỏ đó có thể trỏ tới phiên bản quyết định đã thay đổi, khiến truy vết ghép các lựa chọn không đồng thời tồn tại.

Đối với ví dụ A/B/C, truy vết đúng:

~~~text
Counts [A, B, C] = [2, 1, 0]
Used weight     = 2*3 + 1*4 = 10
Best value      = 2*6 + 1*7 = 19
~~~

Bảng quyết định tốn O(KW) boolean; **phiên bản có truy vết không còn dùng O(W) bộ nhớ**.

## 9. Java 17: chương trình chạy độc lập

Mỗi loại là Item(name, weight, value, limit). Chương trình có hai phương thức:

- bestValueOnly: chỉ tối ưu giá trị, sử dụng mảng dp một chiều.
- solve: tối ưu và truy vết số lượng theo thứ tự loại đầu vào.

Cả hai sử dụng cùng phân rã nhị phân. Số lượng âm, trọng lượng bằng 0 hoặc âm, capacity âm bị từ chối; đầu vào null bị từ chối. Dùng Math.addExact/Math.multiplyExact để tránh tràn giá trị âm thầm. capacity=0 hợp lệ.

Lưu tệp **BoundedKnapsackExample.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class BoundedKnapsackExample {
    private BoundedKnapsackExample() {}

    public record Item(
            String name, int weight, long value, int limit) {}

    public record Solution(
            long bestValue, int usedWeight, List<Integer> counts) {}

    private record Chunk(
            int itemIndex, int copies, int weight, long value) {}

    private static List<Chunk> makeChunks(
            List<Item> items, int capacity) {
        Objects.requireNonNull(items, "items");
        if (capacity < 0 || capacity == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("invalid capacity");
        }

        List<Chunk> chunks = new ArrayList<>();
        for (int i = 0; i < items.size(); i++) {
            Item item = Objects.requireNonNull(items.get(i), "item");
            Objects.requireNonNull(item.name(), "item.name");
            if (item.weight() <= 0 || item.limit() < 0) {
                throw new IllegalArgumentException(
                        "weight <= 0 or limit < 0");
            }

            // Valid only for the <= capacity, optional-empty variant.
            if (item.value() <= 0) {
                continue;
            }

            int remaining = Math.min(
                    item.limit(), capacity / item.weight());
            long bundle = 1L;

            while (remaining > 0) {
                int copies = (int) Math.min(bundle, remaining);
                int groupWeight = Math.multiplyExact(
                        copies, item.weight());
                long groupValue = Math.multiplyExact(
                        item.value(), (long) copies);

                chunks.add(new Chunk(
                        i, copies, groupWeight, groupValue));
                remaining -= copies;
                bundle *= 2L;
            }
        }
        return chunks;
    }

    public static long bestValueOnly(
            List<Item> items, int capacity) {
        List<Chunk> chunks = makeChunks(items, capacity);
        long[] dp = new long[capacity + 1];

        for (Chunk g : chunks) {
            for (int c = capacity; c >= g.weight(); c--) {
                long candidate = Math.addExact(
                        dp[c - g.weight()], g.value());
                if (candidate > dp[c]) {
                    dp[c] = candidate;
                }
            }
        }
        return dp[capacity];
    }

    public static Solution solve(
            List<Item> items, int capacity) {
        List<Chunk> chunks = makeChunks(items, capacity);
        long[] dp = new long[capacity + 1];
        boolean[][] take =
                new boolean[chunks.size()][capacity + 1];

        for (int g = 0; g < chunks.size(); g++) {
            Chunk chunk = chunks.get(g);
            for (int c = capacity; c >= chunk.weight(); c--) {
                long candidate = Math.addExact(
                        dp[c - chunk.weight()], chunk.value());
                // On ties, keep the previously stored solution.
                if (candidate > dp[c]) {
                    dp[c] = candidate;
                    take[g][c] = true;
                }
            }
        }

        int[] countArray = new int[items.size()];
        int remaining = capacity;

        for (int g = chunks.size() - 1; g >= 0; g--) {
            if (take[g][remaining]) {
                Chunk chunk = chunks.get(g);
                countArray[chunk.itemIndex()] += chunk.copies();
                remaining -= chunk.weight();
            }
        }

        List<Integer> counts = new ArrayList<>();
        for (int amount : countArray) {
            counts.add(amount);
        }
        return new Solution(
                dp[capacity],
                capacity - remaining,
                List.copyOf(counts));
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A", 3, 6, 2),
                new Item("B", 4, 7, 2),
                new Item("C", 2, 3, 3));

        Solution main = solve(items, 10);
        System.out.println("Best value: " + main.bestValue());
        System.out.println("Counts [A, B, C]: " + main.counts());
        System.out.println("Used weight: "
                + main.usedWeight() + "/10");
        System.out.println("Value only: "
                + bestValueOnly(items, 10));

        Solution tie = solve(List.of(
                new Item("X", 2, 3, 2),
                new Item("Y", 4, 6, 1)), 4);
        System.out.println("Tie: value=" + tie.bestValue()
                + ", counts=" + tie.counts());

        Solution negative = solve(List.of(
                new Item("D", 2, -4, 3),
                new Item("E", 5, 8, 1)), 5);
        System.out.println("Negative: value="
                + negative.bestValue()
                + ", counts=" + negative.counts());

        Solution large = solve(List.of(
                new Item("G", 1, 2, 1_000_000_000)), 3);
        System.out.println("Huge limit: value="
                + large.bestValue()
                + ", counts=" + large.counts());

        Solution zero = solve(items, 0);
        System.out.println("Zero capacity: value="
                + zero.bestValue()
                + ", counts=" + zero.counts());

        try {
            solve(List.of(new Item("bad", 0, 5, 1)), 5);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Zero weight: IllegalArgumentException");
        }
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 BoundedKnapsackExample.java
java BoundedKnapsackExample
~~~

Stdout dự kiến chính xác:

~~~text
Best value: 19
Counts [A, B, C]: [2, 1, 0]
Used weight: 10/10
Value only: 19
Tie: value=6, counts=[2, 0]
Negative: value=8, counts=[0, 1]
Huge limit: value=6, counts=[3]
Zero capacity: value=0, counts=[0, 0, 0]
Zero weight: IllegalArgumentException
~~~

Với Tie, lấy hai X cho giá trị 6 hoặc một Y cũng có giá trị 6. Vì code **không thay đổi quyết định khi hòa**, nó trả [2,0]; đây là một trong các nghiệm tối ưu, không phải cách duy nhất. Với Huge limit, sức chứa 3 khiến hạn mức một tỷ được giảm xuống chỉ còn 3 bản sao, không gây một tỷ vòng lặp.

## 10. Chứng minh tính đúng của thuật toán tối ưu hóa

**Bước 1 — Tương đương số lượng:** mỗi nhóm nhị phân góp một số bản sao không âm; tổng tất cả nhóm bằng hạn mức hiệu dụng t. Do đó chọn một tập con nhóm không bao giờ vượt t. Ngược lại, mọi k∈[0,t] biểu diễn được bằng tập con nhóm, nên không mất bất kỳ số lượng nào có thể chọn trong bài toán gốc. Giá trị và trọng lượng của nhóm bằng tổng của đúng số bản sao ấy.

**Bước 2 — DP 0/1 đúng:** trước nhóm đầu tiên, nghiệm rỗng tối ưu với mọi sức chứa và dp[c]=0. Giả sử dp cũ đúng. Với nhóm g, mọi nghiệm hợp lệ hoặc không lấy g (giá trị dp_old[c]), hoặc lấy đúng một g (giá trị dp_old[c−gw]+gv). Vòng giảm dần bảo đảm tham chiếu tới dp_old. Chọn max của hai trường hợp cho đúng dp mới. Quy nạp theo số nhóm chứng minh dp[W] tối ưu.

**Bước 3 — Truy vết đúng:** take[g][c] ghi việc lựa chọn nhóm g đã cải thiện nghiệm của giai đoạn ấy dựa trên giai đoạn trước. Đi từ nhóm cuối về nhóm đầu giữ đúng trạng thái sức chứa tương ứng, và mỗi nhóm được xét tối đa một lần. Số bản sao theo loại là tổng copies của các nhóm được lấy, không vượt qᵢ; tổng trọng lượng không vượt W, tổng giá trị bằng dp[W].

Khi hòa, giữ nghiệm cũ vẫn tối ưu; quy tắc này chỉ chọn một nghiệm xác định trong nhiều nghiệm. Lập luận trên không đòi tất cả giá trị phải dương, nhưng **bước bỏ các nhóm có giá trị không dương** chỉ hợp lệ vì cho phép nghiệm rỗng và ràng buộc ≤W.

## 11. Độ phức tạp và chi phí lưu vết

Gọi tᵢ=min(qᵢ, floor(W/wᵢ)), K là số nhóm từ các loại có giá trị dương.

| Phương pháp | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| DP thử mọi số k | O(W·Σ(tᵢ+1)) | O(W) với hai hàng |
| Tạo riêng từng bản sao 0/1 | O(W·Σtᵢ) | O(W) khi chỉ trả giá trị |
| Phân rã nhị phân + dp 1D | O(WK) | O(W+K) |
| Phân rã + truy vết take[K][W+1] | O(WK) | O(WK+W+K+n) |
| Hàng đợi đơn điệu theo phần dư | O(nW), trong mô hình số học O(1) | O(W) hoặc hơn tùy truy vết |

Thông thường K=O(Σ log(tᵢ+1)); nếu tᵢ=0 thì loại đó không tạo nhóm. Công đoạn sắp xếp **không bắt buộc** trong binary splitting, khác một số thuật toán tham lam.

Ngay cả khi W còn vừa kiểu int, không phải máy nào cũng cấp phát được dp[W+1], đặc biệt bảng take có K hàng. Đây là thuật toán **giả đa thức** theo W: nếu W được biểu diễn bằng b bit, W có thể lớn theo hàm mũ của b. Không nên gọi thời gian O(nW) là đa thức theo *độ dài bit đầu vào* mà không nêu mô hình.

Nếu giá trị vượt phạm vi long, Math.addExact có thể báo ArithmeticException. Dùng BigInteger có thể khắc phục giới hạn biểu diễn nhưng làm chi phí phép cộng phụ thuộc độ dài số.

## 12. Tối ưu O(nW) bằng hàng đợi đơn điệu: khi nào cần?

Một cải tiến nâng cao tránh sinh K nhóm bằng cách xét **các sức chứa cùng phần dư modulo trọng lượng wᵢ**. Với một loại (w,v,q), từ hàng DP cũ:

~~~text
new[c] = max over k=0..min(q,floor(c/w)):
             old[c-k*w] + k*v
~~~

Cố định phần dư r∈[0,w), viết c=r+jw, đặt t=j−k:

~~~text
new[r+j*w] =
    j*v + max over t ∈ [max(0,j-q),j]:
                (old[r+t*w] - t*v)
~~~

Biểu thức trong ngoặc là **giá trị cần lấy max trên một cửa sổ trượt** của chỉ số t. Duy trì một deque có giá trị giảm dần và loại các chỉ số quá cũ tạo O(1) khấu hao cho mỗi vị trí, tổng O(W) cho một loại và O(nW) cho n loại.

Đây là tối ưu hữu ích khi W tương đối nhỏ nhưng hạn mức nhiều, tuy nhiên code phức tạp hơn, nhất là lúc cần truy vết. Nó **không** có nghĩa bài toán mất yếu tố giả đa thức: vẫn cần xét nhiều trạng thái sức chứa theo W.

## 13. Biến thể yêu cầu đúng sức chứa W

Bài toán **exact-fill bounded knapsack** khác bản trong Java:

- Bắt buộc Σxᵢwᵢ= W.
- Nghiệm rỗng chỉ hợp lệ khi W=0.
- Giá trị âm có thể phải chọn để lấp đủ trọng lượng.
- Phải phân biệt trạng thái **không thể đạt** với trạng thái có điểm 0 hoặc âm.

Khởi tạo 0/1 DP đúng sức chứa:

~~~text
reachable[0] = true,  dp[0] = 0
reachable[c] = false với mọi c > 0

Khi xét nhóm trọng lượng gw:
    c duyệt giảm từ W xuống gw
    chỉ chuyển nếu reachable[c-gw] == true
    cập nhật best/reachable[c] khi có nghiệm tốt hơn
~~~

Không thể tái sử dụng nguyên si chương trình Java vì chương trình bỏ các loại giá trị âm và khởi tạo dp[c]=0 cho mọi c. Ví dụ W=3, chỉ có một loại w=3, v=−5, q=1: bài toán **≤W** chọn rỗng với giá trị 0, còn bài toán **đúng W** phải chọn bản sao ấy với giá trị −5.

Một biến thể khác yêu cầu chọn **chính xác T vật phẩm** hoặc đáp ứng hai tài nguyên đồng thời. Khi đó trạng thái có thể cần thêm chiều số vật phẩm hoặc tài nguyên; không tự suy ra kết quả từ DP một chiều hiện tại.

## 14. Kiểm thử với oracle liệt kê toàn bộ

Với n và qᵢ nhỏ, tạo lời giải tham chiếu bằng đệ quy thử lần lượt mọi số bản sao k của từng loại:

~~~text
brute(i, weight, value):
    if i == n:
        nếu weight <= W:
            cập nhật best
        return

    for k = 0 .. qᵢ:
        if weight + k*wᵢ <= W:
            brute(i+1, weight+k*wᵢ, value+k*vᵢ)
~~~

Số tổ hợp có thể là tích (qᵢ+1), nên đây **chỉ là oracle kiểm thử cho đầu vào nhỏ**, không phải thuật toán sản xuất.

Các ca quan trọng:

| Đầu vào | Kết quả cần xác nhận |
| --- | --- |
| A(3,6,2), B(4,7,2), C(2,3,3), W=10 | Giá trị 19, có nghiệm [2,1,0] |
| X(2,3,2), Y(4,6,1), W=4 | Giá trị 6, có thể có nhiều nghiệm |
| D(2,−4,3), E(5,8,1), W=5 | Giá trị 8, không chọn D |
| G(1,2,1.000.000.000), W=3 | Giá trị 6, chọn 3 |
| W=0, mọi w>0 | Giá trị 0, số bản sao đều 0 |
| Tất cả q=0 | Giá trị 0 |
| Loại có w>W | Không thể chọn loại ấy |
| Loại có v=0 | Có thể bỏ, không làm giảm tối ưu |
| Trọng lượng 0 hoặc q âm | IllegalArgumentException |
| Danh sách rỗng | Giá trị 0 |

Với kết quả có truy vết, cần kiểm tra **mọi ràng buộc**, không chỉ best: mỗi count[i] nguyên trong [0,qᵢ], tổng trọng lượng ≤W, tổng giá trị của counts bằng best và danh sách gốc không đổi.

Vì một bài toán có thể có **nhiều nghiệm tối ưu**, oracle không nên buộc các vector counts trùng nhau. Nó nên so giá trị tối ưu và tính hợp lệ của nghiệm trả về.

## 15. Những lỗi thường gặp và checklist

Các lỗi phổ biến:

1. **Dùng vòng tăng dần cho một nhóm 0/1:** nhóm bị dùng lại không giới hạn.
2. **Không giới hạn theo qᵢ:** biến bounded thành unbounded.
3. **Duyệt k rồi dùng ngay trạng thái cùng loại một cách tùy tiện:** có thể lặp bản sao ngoài k dự định.
4. **Quên k=0:** ép chọn loại mới dù không có lợi.
5. **Coi dp[c] là giá trị với đúng trọng lượng c** trong khi đã khởi tạo dp[c]=0 toàn bộ.
6. **Bỏ vật phẩm âm trong bài toán exact-fill:** có thể bỏ nghiệm hợp lệ duy nhất.
7. **Tính groupWeight/groupValue bằng kiểu quá nhỏ:** tràn trước khi DP chạy.
8. **Chỉ lưu parent[c] trong DP ghi đè mà không lưu phiên bản:** dễ truy vết tổ hợp không hợp lệ.
9. **Nhầm binary splitting tối ưu giá trị với đếm số nghiệm:** nhóm có thể có biểu diễn số lượng trùng nhau.
10. **Không tính bảng take vào bộ nhớ:** bản có truy vết dùng O(KW), không phải O(W).
11. **Cho rằng O(nW) luôn nhanh:** W là giá trị số có thể rất lớn.
12. **Chỉ kiểm tra tổng điểm mà bỏ giới hạn số lượng và trọng lượng:** có thể trả điểm của một nghiệm không khả thi.

Checklist trước khi áp dụng:

- [ ] Bài là 0/1, bounded hay unbounded?
- [ ] Sức chứa cần dùng **không quá W** hay **đúng W**?
- [ ] Nghiệm rỗng có hợp lệ không?
- [ ] Đã xác định wᵢ>0, qᵢ≥0, cách xử lý giá trị âm và trọng lượng 0?
- [ ] Đã cắt qᵢ thành min(qᵢ, floor(W/wᵢ))?
- [ ] Nếu phân nhóm nhị phân, tổng copies các nhóm có đúng hạn mức hiệu dụng?
- [ ] Mỗi nhóm 0/1 được cập nhật theo **chiều giảm dần**?
- [ ] Nếu cần truy vết, đã lưu quyết định theo giai đoạn và tính đủ bộ nhớ?
- [ ] Đã kiểm thử bằng brute force trên các trường hợp nhỏ?
- [ ] Đã xử lý tràn số, W quá lớn và phân biệt tối ưu giá trị với đếm số nghiệm?

**Kết luận:** ba lô có số lượng giới hạn là DP tối ưu theo sức chứa và hạn mức số bản sao. Công thức trực tiếp thử mọi k từ 0 đến qᵢ; **phân rã nhị phân** biến mỗi loại thành O(log qᵢ) nhóm 0/1 và cập nhật dp theo sức chứa **giảm dần**. Điều kiện ≤W, khả năng chọn rỗng, cách xử lý trọng số/giá trị không dương và yêu cầu truy vết phải được nêu rõ để tránh dùng đúng mã nhưng giải sai biến thể bài toán.
