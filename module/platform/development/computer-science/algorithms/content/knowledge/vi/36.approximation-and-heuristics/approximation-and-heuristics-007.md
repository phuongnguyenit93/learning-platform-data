# Nới lỏng liên tục và làm tròn lời giải

> **Chủ đề:** Computer Science Algorithms → **Xấp xỉ và kinh nghiệm**.  
> **Trọng tâm:** Biến bài toán tổ hợp có biến rời rạc thành bài toán **nới lỏng liên tục** (*continuous relaxation*, đặc biệt là LP relaxation), sử dụng nghiệm phân số làm **cận trên/cận dưới**, rồi **làm tròn** (*rounding*) thành nghiệm nguyên **khả thi** và đánh giá chất lượng bằng **tỷ lệ xấp xỉ**. Bài gồm định lý/chứng minh, integrality gap, ví dụ phản chứng làm tròn ngây thơ, vertex cover 2-approx, knapsack 1/2-approx qua fractional greedy, set cover theo tần suất f, randomized rounding, integrality của matching hai phía, lưu ý solver số thực, **4 chương trình Java 17 độc lập**, kiểm thử oracle, bài tập có đáp án và checklist.

## 1. Vì sao phải nới lỏng rồi làm tròn?

Một bài toán tổ hợp thường yêu cầu quyết định **có chọn một đối tượng hay không**. Biến quyết định:

`x_i ∈ {0,1}`

mang ý nghĩa rất cụ thể: chọn hay không chọn đỉnh, cạnh, vật phẩm, tập phủ, ca làm việc...

Các ràng buộc nguyên khiến không gian nghiệm rời rạc. Nhiều bài tối ưu nguyên trong trường hợp tổng quát là NP-hard. Nếu bỏ bớt yêu cầu nguyên:

`0 ≤ x_i ≤ 1`

ta nhận **nghiệm phân số**: x_i=0.4 có thể được hiểu như trọng lượng phân số hay xác suất được chọn, tùy kỹ thuật. Trong quy hoạch tuyến tính (*linear programming*, LP), miền nghiệm trở thành một **đa diện lồi** được mô tả bởi các bất đẳng thức tuyến tính.

Ví dụ muốn chọn ít đỉnh nhất để phủ mọi cạnh của đồ thị:

- `x_v=1` nếu chọn đỉnh v;
- với mỗi cạnh (u,v), bắt buộc `x_u+x_v≥1`;
- mục tiêu `min Σ_v x_v`.

Trong bài toán nguyên, x_v chỉ bằng0/1. Trong **LP nới lỏng**, cho x_v nằm trong [0,1]; nghiệm phân số có thể rẻ hơn hoặc bằng nghiệm nguyên.

**Hai bước không thể thiếu:**

1. Giải (hoặc lấy một nghiệm của) bài toán nới lỏng để có **thông tin cận** và một điểm phân số.
2. Thiết kế quy tắc làm tròn **bảo toàn ràng buộc** và **có chứng minh mất mát mục tiêu**.

Chỉ làm tròn `Math.round(x)` từng biến thường **không đủ**.

### 1.1. Nới lỏng không phải bỏ hết ràng buộc

Một relaxation **hợp lệ** có miền khả thi **chứa mọi nghiệm nguyên** của bài toán gốc sau khi nhúng chúng vào không gian liên tục. Các ràng buộc có thể được giữ nguyên, còn điều kiện x nguyên được bỏ đi.

Nếu một phép “nới lỏng” vô tình loại mất nghiệm nguyên hợp lệ, các kết luận về cận tối ưu có thể không còn đúng.

### 1.2. Nghiệm phân số không tự là nghiệm ứng dụng

Một vật phẩm 0/1 không được chọn 40% nếu bài yêu cầu mua nguyên chiếc. Một đỉnh của vertex cover không thể chỉ “được lấy 0.5” trong đồ thị kết quả. LP là **công cụ tính cận và dẫn đường**, không phải luôn là lời giải cuối.

### 1.3. Độ khó của việc làm tròn

Nghiệm phân số có thể thỏa tất cả bất đẳng thức, nhưng sau làm tròn:

- Một cạnh không được phủ.
- Tổng trọng lượng vượt sức chứa.
- Hai đỉnh kề nhau cùng được chọn cho tập độc lập.
- Tổng chọn không bằng số lượng bắt buộc.
- Một phần tử universe không còn thuộc tập được chọn nào.

Cần chứng minh lại **feasibility**, không chỉ kiểm các biến đã là số nguyên.

## 2. Bài toán nguyên và LP relaxation dưới dạng công thức

Xét bài toán 0/1 tối thiểu hóa:

`minimize cᵀx`

với:

`Ax ≥ b`, `x ∈ {0,1}^n`, `c_i ≥ 0`.

LP relaxation:

`minimize cᵀx`

với:

`Ax ≥ b`, `0 ≤ x_i ≤ 1`.

Mọi x nguyên khả thi vẫn thỏa LP. Do đó:

`OPT_LP ≤ OPT_IP` — **giá trị tối ưu LP là cận dưới** cho bài toán tối thiểu hóa nguyên.

Nếu là tối đa hóa:

`maximize cᵀx`,

thì mọi nghiệm nguyên cũng là nghiệm LP, nên:

`OPT_IP ≤ OPT_LP` — **giá trị tối ưu LP là cận trên**.

Hướng của bất đẳng thức rất quan trọng. Không được áp cận dưới của minimization cho maximization.

### 2.1. Nghiệm khả thi của LP khác nghiệm LP tối ưu

Giả sử có điểm phân số x^F chỉ **khả thi** nhưng chưa biết là tối ưu. Khi tối thiểu hóa:

`OPT_LP ≤ cᵀx^F`.

Điều này **không** khẳng định `cᵀx^F ≤ OPT_IP`.

Nếu một quy tắc cho:

`cost(round(x^F)) ≤ 2·cᵀx^F`,

ta mới có **cận so với giá trị của chính điểm phân số**. Muốn suy ra:

`cost(round(x*)) ≤ 2·OPT_IP`

cần x* là nghiệm **LP tối ưu** (hoặc có một bảo đảm x^F là α-approx của LP optimum).

Điểm khác biệt này là bẫy quan trọng nhất khi chứng minh thuật toán xấp xỉ từ relaxation.

### 2.2. Cận cho max khi có fractional optimum

Trong bài tối đa hóa, nếu có **cận trên U≥OPT_IP**, và thuật toán cho giá trị nguyên V≥U/α với α≥1, suy ra:

`V ≥ OPT_IP/α`.

Đối với một điểm LP khả thi bất kỳ có giá trị thấp hơn U thật, không được tự thay nó vào công thức đó rồi tuyên bố bảo đảm.

### 2.3. Thí dụ cận trên và cận dưới

Bài knapsack có `OPT_IP=20` và LP relaxation cho `OPT_LP=20`, thì LP vừa là cận trên đúng 20. Nhưng thuật toán làm tròn đơn giản có thể chỉ trả12; nghiệm vẫn hợp lệ và ≥1/2 OPT_IP.

Bài vertex cover trên chu trình bốn đỉnh có `OPT_IP=2`, `OPT_LP=2`; làm tròn **một nghiệm phân số tối ưu** có thể chọn cả bốn đỉnh, cost4. Cận dưới LP vẫn tốt, nhưng **quy tắc làm tròn** có thể trả nghiệm xa tối ưu hơn.

## 3. Integrality gap là mức yếu của relaxation

**Integrality gap** đo khoảng cách giữa optimum nguyên và optimum liên tục.

Với bài tối thiểu hóa, khi `OPT_LP>0`:

`gap = OPT_IP / OPT_LP ≥ 1`.

Với bài tối đa hóa, khi `OPT_IP>0`:

`gap = OPT_LP / OPT_IP ≥ 1`.

Nhiều tài liệu nói “integrality gap của một relaxation” là **supremum trên các instance hợp lệ**, không chỉ tỷ số của một ví dụ.

### 3.1. Vertex cover trên tam giác

Tam giác có ba đỉnh và ba cạnh. Gán phân số:

`x_0=x_1=x_2=1/2`.

Mỗi cạnh có tổng1 nên LP khả thi. Mục tiêu LP=3/2.

Bất kỳ vertex cover nguyên của tam giác phải lấy ít nhất2 đỉnh, và lấy2 là đủ:

`OPT_IP=2`, `OPT_LP=1.5`, `gap=4/3`.

Làm tròn ngưỡng≥1/2 chọn **cả ba**, cost3. Tỷ số nghiệm làm tròn so với optimum nguyên là 3/2, khác với integrality gap 4/3.

### 3.2. Vertex cover trên chu trình bốn đỉnh

Đặt x_v=1/2 tại cả bốn đỉnh. LP cost2, cũng là optimum LP. Một cover nguyên chọn hai đỉnh đối diện, cost2. Nhưng quy tắc chọn tất cả x_v≥1/2 trả cost4.

Vậy ở instance này:

- Integrality gap =1.
- Tỷ số nghiệm làm tròn / optimum =2.

**Integrality gap thấp không bảo đảm mọi quy tắc làm tròn đều tốt.**

### 3.3. Knapsack có gap gần2 ở relaxation một ràng buộc

Sức chứa 100, hai vật phẩm đều có `weight=51`, `value=51`. Bài 0/1 chọn tối đa một vật phẩm ⇒ `OPT_IP=51`.

Fractional knapsack cho lấy một vật phẩm nguyên (51) và 49/51 vật phẩm thứ hai (49), nên `OPT_LP=100`.

Gap `100/51≈1.96`, tiến gần2 trong một họ instance tương tự. Quy tắc làm tròn 1/2-approx khai thác trực tiếp cấu trúc “tối đa một vật phẩm lẻ” của fractional optimum.

### 3.4. Gap có thể rất lớn nếu relaxation yếu

Tối đa hóa tập độc lập với các ràng buộc cạnh:

`max Σ_v x_v`, `x_u+x_v≤1` cho mỗi cạnh, `0≤x_v≤1`.

Trong đồ thị đầy đủ K_n, nghiệm x_v=1/2 cho tất cả n đỉnh là khả thi phân số, có giá trị n/2, trong khi independent set nguyên tối đa chỉ có1 đỉnh. Gap ít nhất n/2.

Không thể mong **một quy tắc làm tròn tỷ lệ hằng** cho relaxation yếu này trên mọi đồ thị mà không thêm ý tưởng/ràng buộc khác.

### 3.5. Giá trị tối ưu bằng0

Nếu `OPT_LP=0` hoặc `OPT_IP=0`, tỷ số thường không được xác định hoặc cần quy ước đặc biệt. Khi báo cáo approximation, ưu tiên viết **bất đẳng thức giá trị** thay vì lấy phép chia0.

## 4. Quy trình thiết kế thuật toán relaxation + rounding

Một quy trình có kỷ luật:

1. **Mô hình hóa** bài gốc bằng biến nguyên và ràng buộc rõ nghĩa.
2. **Nới lỏng hợp lệ**: mọi nghiệm nguyên trở thành nghiệm liên tục khả thi.
3. **Giải LP tối ưu** hoặc nêu rõ mức gần tối ưu của nghiệm phân số đã có.
4. **Đọc cấu trúc nghiệm phân số**: threshold, thứ tự tỷ số, support, dual prices, half-integral vertices, xác suất.
5. **Định nghĩa quy tắc làm tròn** tạo ra biến nguyên/bộ đối tượng.
6. **Chứng minh khả thi** của nghiệm nguyên, kể cả trường hợp biên.
7. **Chứng minh mất mát mục tiêu** so với giá trị LP ở đầu vào.
8. **Nối với OPT_IP bằng hướng cận đúng**: min dùng LP lower bound, max dùng LP upper bound.
9. **Kiểm chứng triển khai** bằng oracle tối ưu trên input nhỏ và bất biến của chứng minh.
10. **Báo cáo giới hạn**: khi đầu vào LP chỉ gần tối ưu, do numerical tolerance hay có giả thiết đặc biệt, phải công bố rõ.

### 4.1. Dạng chứng minh minimization

Muốn α-approx với α≥1:

`cost(rounded) ≤ α·OPT_LP ≤ α·OPT_IP`.

Bất đẳng thức đầu là **phần việc của rounding**. Bất đẳng thức sau là **cận relaxation**.

### 4.2. Dạng chứng minh maximization

Muốn α-approx:

`value(rounded) ≥ OPT_LP/α ≥ OPT_IP/α`.

Lưu ý dấu lớn hơn: điều kiện này nói nghiệm nguyên nhận ít nhất một phần α của **cận trên LP**. Một số bài khó cần điều chỉnh/siết LP để có bound đủ mạnh.

### 4.3. Nếu LP được giải xấp xỉ

Nếu bài min và điểm phân số có `cᵀx^F ≤ β·OPT_LP`, kèm rounding:

`cost(rounded) ≤ α·cᵀx^F`

thì:

`cost(rounded) ≤ αβ·OPT_IP`.

Cần β≥1 và bảo đảm x^F **khả thi**, không chỉ residual solver nhỏ.

Với maximization, một nghiệm fractional suboptimal có thể không tạo ra **cận trên** cho optimum nguyên. Phải dùng cận dual/LP optimum đã được chứng nhận hoặc một bound khác.

## 5. Vì sao làm tròn từng biến theo 0.5 có thể thất bại?

**Quy tắc ngây thơ:**

`y_i = 1 nếu x_i≥0.5; ngược lại y_i=0`.

Nó không tự hiểu ràng buộc.

### 5.1. Constraint tổng số lượng

LP:

`x_1+x_2 ≤ 1`, `x_i∈[0,1]`.

Điểm `(0.5,0.5)` khả thi, nhưng làm tròn lên thành `(1,1)` cho tổng2>1 ⇒ **vi phạm**.

Nếu dùng `x_i>0.5` để làm tròn, nó cho `(0,0)`: khả thi nhưng có thể mất toàn bộ objective tối đa hóa trong ví dụ khác.

### 5.2. Independent set

Trên tam giác, `x_0=x_1=x_2=0.5` thỏa ràng buộc LP cạnh `x_u+x_v≤1`. Làm tròn lên chọn cả ba đỉnh ⇒ **không phải independent set**.

Lấy một đỉnh bằng một bước repair tham lam có thể tạo nghiệm khả thi, nhưng **không tự cho tỷ lệ xấp xỉ** trong đồ thị tổng quát.

### 5.3. Knapsack

Nếu tổng trọng lượng phân số vừa đúng capacity, làm tròn nhiều vật phẩm lên có thể vượt capacity. Ngược lại, làm tròn mọi vật phẩm có x<0.5 xuống có thể mất nhiều profit.

### 5.4. Điều kiện cân bằng chính xác

Ràng buộc `Σ_i x_i = k` không được bảo toàn khi làm tròn từng biến độc lập. Bài toán assignment, matching hay scheduling thường cần **làm tròn phụ thuộc** (*dependent rounding*) hoặc tận dụng cấu trúc nguyên của đa diện.

**Kết luận:** Không có phép làm tròn cố định 0.5 dùng được cho mọi IP. Quy tắc phải xuất phát từ **hướng bất đẳng thức và cấu trúc ràng buộc**.

## 6. Vertex cover: LP và làm tròn ngưỡng 1/2

Cho đồ thị vô hướng G=(V,E), mục tiêu tìm tập đỉnh C sao cho **mọi cạnh có ít nhất một đầu trong C**, tối thiểu hóa |C|.

### 6.1. Mô hình 0/1

`minimize Σ_(v∈V) x_v`

với:

`x_u+x_v≥1` cho mọi cạnh (u,v)∈E,

`x_v∈{0,1}`.

LP relaxation thay bằng `0≤x_v≤1`.

### 6.2. Quy tắc threshold

Cho nghiệm phân số LP **khả thi** x. Chọn:

`C={v | x_v≥1/2}`.

**Chứng minh khả thi:**

Với mỗi cạnh (u,v), giả sử cả hai đầu không được chọn, khi đó x_u<1/2 và x_v<1/2 ⇒ `x_u+x_v<1`, trái ràng buộc LP. Vậy ít nhất một đầu được chọn.

**Chặn cost:**

Với mọi v:

`1[v∈C] ≤ 2x_v`.

Cộng:

`|C|≤2Σ_v x_v`.

Nếu x là nghiệm **LP tối ưu**:

`|C| ≤ 2 OPT_LP ≤ 2 OPT_IP`.

Do đó là thuật toán **2-approximation** cho unweighted vertex cover.

### 6.3. Vertex cover có trọng số

Nếu mỗi đỉnh v có chi phí `w_v≥0`, mục tiêu:

`min Σ_v w_v x_v`.

Cùng threshold:

`cost(C)=Σ_{v∈C}w_v ≤ 2 Σ_v w_v x_v`.

Nếu x tối ưu LP, có 2-approx cho weighted vertex cover. Yêu cầu w_v **không âm** là thiết yếu cho bước nhân bất đẳng thức.

### 6.4. Nghiệm LP nửa nguyên

Đa diện LP vertex cover chuẩn có **các đỉnh cực biên half-integral**: có thể lấy một nghiệm tối ưu cực biên với:

`x_v∈{0,1/2,1}`.

Vì vậy demo dùng **tử số nguyên z_v=2x_v∈{0,1,2}**, kiểm:

`z_u+z_v≥2`.

Làm tròn bằng `z_v≥1` tránh mọi sai lệch floating-point ở ngưỡng0.5. Trong triển khai LP tổng quát, x có thể là số thực bất kỳ, nhưng chứng minh threshold vẫn đúng nếu điểm LP thực sự khả thi.

### 6.5. Hai ví dụ

**Tam giác:** z=(1,1,1); LP=1.5; threshold chọn3; optimum nguyên=2; cả feasibility và `cost≤2 LP` đúng.

**Chu trình bốn đỉnh:** z=(1,1,1,1); LP=2; threshold chọn4; optimum nguyên=2; tỷ số output/optimum đạt đúng2 dù LP gap=1.

Không nên diễn giải “hệ số2” thành “luôn chọn gấp đôi”. Nó là **cận trường hợp xấu nhất**.

## 7. Java 17 — làm tròn LP vertex cover và kiểm bảo đảm

Lưu **VertexCoverLpRoundingDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class VertexCoverLpRoundingDemo {
    // "twiceX[v]" is 2*x[v], hence one of 0, 1, 2.
    record Answer(int[] selected, double lpCost, int roundedCost) {}

    static Answer round(int n, int[][] edges, int[] twiceX) {
        if (n < 0 || edges == null || twiceX == null
                || twiceX.length != n) {
            throw new IllegalArgumentException("Invalid input shape");
        }
        for (int z : twiceX) {
            if (z < 0 || z > 2) {
                throw new IllegalArgumentException("Not half-integral");
            }
        }

        for (int[] edge : edges) {
            if (edge == null || edge.length != 2
                    || edge[0] < 0 || edge[1] < 0
                    || edge[0] >= n || edge[1] >= n
                    || edge[0] == edge[1]) {
                throw new IllegalArgumentException("Invalid simple edge");
            }
            if (twiceX[edge[0]] + twiceX[edge[1]] < 2) {
                throw new IllegalArgumentException("Infeasible LP point");
            }
        }

        List<Integer> selected = new ArrayList<>();
        int twiceObjective = 0;
        for (int v = 0; v < n; v++) {
            twiceObjective += twiceX[v];
            if (twiceX[v] >= 1) selected.add(v);
        }
        int[] ids = selected.stream().mapToInt(Integer::intValue).toArray();
        return new Answer(ids, twiceObjective / 2.0, ids.length);
    }

    static boolean isCover(int n, int[][] edges, int[] ids) {
        boolean[] picked = new boolean[n];
        for (int v : ids) {
            if (v < 0 || v >= n || picked[v]) return false;
            picked[v] = true;
        }
        for (int[] edge : edges) {
            if (!picked[edge[0]] && !picked[edge[1]]) return false;
        }
        return true;
    }

    // Exponential oracle for tiny graphs only; not the approximation.
    static int exactOptimum(int n, int[][] edges) {
        if (n > 20) throw new IllegalArgumentException("Oracle too large");
        int optimum = n + 1;
        for (int mask = 0; mask < (1 << n); mask++) {
            int cost = Integer.bitCount(mask);
            if (cost >= optimum) continue;
            boolean ok = true;
            for (int[] edge : edges) {
                if ((mask & (1 << edge[0])) == 0
                        && (mask & (1 << edge[1])) == 0) {
                    ok = false;
                    break;
                }
            }
            if (ok) optimum = cost;
        }
        return optimum;
    }

    public static void main(String[] args) {
        int[][] triangle = {{0, 1}, {1, 2}, {0, 2}};
        Answer t = round(3, triangle, new int[] {1, 1, 1});
        System.out.printf(Locale.ROOT,
                "triangle LP cost=%.1f%n", t.lpCost());
        System.out.println("triangle rounded cost=" + t.roundedCost());
        System.out.println("triangle cover valid="
                + isCover(3, triangle, t.selected()));
        System.out.println("triangle optimum="
                + exactOptimum(3, triangle));

        int[][] cycle = {{0, 1}, {1, 2}, {2, 3}, {3, 0}};
        Answer c = round(4, cycle, new int[] {1, 1, 1, 1});
        System.out.printf(Locale.ROOT,
                "cycle LP cost=%.1f%n", c.lpCost());
        System.out.println("cycle rounded cost=" + c.roundedCost());
        System.out.println("cycle optimum=" + exactOptimum(4, cycle));
        System.out.println("cycle cost <= 2 * LP: "
                + (c.roundedCost() <= 2.0 * c.lpCost()));

        boolean invalidRejected = false;
        try {
            round(3, triangle, new int[] {0, 0, 0});
        } catch (IllegalArgumentException ex) {
            invalidRejected = true;
        }
        System.out.println("infeasible fractional rejected="
                + invalidRejected);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 VertexCoverLpRoundingDemo.java
java VertexCoverLpRoundingDemo
```

Stdout dự kiến:

```text
triangle LP cost=1.5
triangle rounded cost=3
triangle cover valid=true
triangle optimum=2
cycle LP cost=2.0
cycle rounded cost=4
cycle optimum=2
cycle cost <= 2 * LP: true
infeasible fractional rejected=true
```

### 7.1. Giới hạn demo

Đầu vào demo là một điểm LP **đã cho**, biểu diễn half-integral; chương trình **không tự giải LP**. Với hai ví dụ, ta có thể chứng minh điểm ấy là LP tối ưu: tam giác cộng ba bất đẳng thức cạnh suy ra `2Σx≥3`; chu trình bốn đỉnh cộng hai cạnh đối diện suy ra `Σx≥2`.

Vì các điểm này là LP tối ưu, tỷ lệ2 được bảo đảm với **optimum nguyên**. Nếu người dùng đưa một điểm LP khả thi nhưng rất đắt, cùng code chỉ bảo đảm cost≤2*(giá trị điểm LP đã đưa), **không tự là 2-approx đối với OPT_IP**.

### 7.2. Vì sao exactOptimum không nằm trong thuật toán xấp xỉ?

Hàm vét cạn n≤20 dùng để **kiểm thử**. Thuật toán xấp xỉ chính chỉ duyệt cạnh để validate rồi làm tròn; không cần kiểm mọi tập 2^n. Trộn oracle với thuật toán sẽ làm sai phân tích thời gian đa thức.

## 8. Knapsack 0/1: fractional relaxation cho cận trên

Bài 0/1 knapsack:

- Có n vật phẩm, trọng lượng `w_i>0`, lợi ích `v_i≥0`.
- Sức chứa C≥0.
- Quyết định x_i∈{0,1}.
- Tối đa hóa `Σ v_i x_i` với `Σ w_i x_i≤C`.

LP relaxation thay bằng:

`0≤x_i≤1`.

### 8.1. Giải LP fractional bằng tỷ số v/w

Với trọng lượng dương, sắp vật phẩm theo mật độ lợi ích:

`d_i=v_i/w_i`

giảm dần. Trong nghiệm tối ưu fractional, ta lấy:

1. Một số vật phẩm đầu tiên **nguyên x_i=1**.
2. Có thể một vật phẩm tiếp theo **phân số 0<x_j<1**.
3. Những vật phẩm sau bằng0.

Đây là thuật toán greedy chính xác cho **fractional knapsack** (trường hợp một constraint), khác với 0/1 knapsack tổng quát.

**Chứng minh trực giác bằng trao đổi:** Nếu một vật phẩm mật độ thấp được chọn một phần nhưng vật phẩm mật độ cao chưa được lấy hết, chuyển một lượng trọng lượng nhỏ sang vật phẩm mật độ cao không giảm tổng lợi ích. Lặp trao đổi dẫn tới cấu trúc prefix và tối đa một vật phẩm phân số.

### 8.2. Loại vật phẩm quá nặng trước khi relaxation

Nếu `w_i>C`, vật phẩm đó **không thể** được chọn trong 0/1 knapsack. Đặt bắt buộc x_i=0 và loại nó trước khi giải fractional relaxation. Đây là ràng buộc hợp lệ cho **mọi nghiệm nguyên**.

Nếu để vật phẩm quá nặng tham gia LP và được lấy phân số, một item có v rất lớn có thể làm cận fractional của LP gốc **quá lỏng**, khiến chứng minh prefix-vs-best-single bị hỏng.

Tất cả vật phẩm còn lại đều có `w_i≤C`, nên **từng vật phẩm riêng lẻ** là một nghiệm nguyên khả thi.

### 8.3. Đặt tên giá trị

Với dãy đã sắp theo mật độ, giả sử:

- P = tổng lợi ích những vật phẩm lấy **nguyên vẹn trong prefix**;
- j = vật phẩm đầu tiên không thể lấy nguyên khi duyệt prefix;
- α∈(0,1) là phần có thể lấy của item j;
- B = giá trị **vật phẩm đơn lẻ tốt nhất** trong các item có w_i≤C.

Khi tồn tại item phân số:

`OPT_LP = P + α v_j ≤ P + v_j ≤ P + B`.

Lấy hai ứng viên nguyên khả thi:

1. **Prefix** có lợi ích P.
2. **Best-single** có lợi ích B.

Chọn:

`ALG=max(P,B)`.

Ta có:

`ALG ≥ (P+B)/2 ≥ OPT_LP/2 ≥ OPT_IP/2`.

Nếu tất cả vật phẩm đều vừa, P=OPT_LP=OPT_IP và thuật toán trả optimum. Nếu không có item nào vừa, nghiệm0 có lợi ích0 và điều kiện 1/2 là hiển nhiên theo bất đẳng thức, không cần chia cho OPT=0.

### 8.4. Độ phức tạp

Sắp mật độ: O(n log n) so sánh. Một lần duyệt: O(n). Bộ nhớ O(n) cho danh sách và thứ tự item; nếu cần giữ witness ID.

Đối với `int weight/value>0` có giới hạn Java, so sánh mật độ bằng tích chéo của các số `long`:

`v_a/w_a > v_b/w_b ⇔ v_a*w_b > v_b*w_a`.

Tránh `Double.compare(v_a/(double)w_a,...)` khi cần tránh tie giả do rounding. Trong bài với số nguyên lớn tùy ý, tích chéo phải dùng BigInteger.

### 8.5. Khi chỉ dùng greedy 0/1 dễ sai

Ví dụ C=10:

- Item0: w=6, v=12.
- Item1: w=6, v=12.
- Item2: w=4, v=8.

Cả ba mật độ2. Theo thứ tự ID, prefix lấy item0 rồi gặp item1 quá nặng để thêm. Prefix P=12, best single B=12, thuật toán trả12.

Nhưng optimum nguyên lấy item0 và item2, tổng weight10, value20. Thuật toán chỉ đạt 12/20=0.6, vẫn đáp ứng bảo đảm ≥1/2. Một heuristic **tiếp tục xét item sau** có thể cải thiện nghiệm ở ví dụ này, nhưng cần chứng minh riêng nếu muốn gán guarantee cho biến thể.

### 8.6. Ví dụ best-single quan trọng

C=10, item A có w2/v2 (density1), item B có w10/v9 (density0.9). Prefix fractional greedy lấy item A rồi chỉ lấy 8/10 item B:

`OPT_LP=2+0.8·9=9.2`.

Prefix nguyên P=2, nhưng best-single B=9 ⇒ output9, chính là optimum nguyên. Nếu chỉ trả prefix, một ví dụ tương tự có thể cho kết quả rất yếu.

## 9. Java 17 — fractional knapsack + làm tròn 1/2

Lưu **KnapsackFractionalRoundingDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class KnapsackFractionalRoundingDemo {
    record Item(int id, int weight, int value) {}
    record Answer(double fractionalUpper, long prefix, long bestSingle,
                  long rounded, int[] selected) {}

    static Answer solve(int capacity, int[] weights, int[] values) {
        if (capacity < 0 || weights == null || values == null
                || weights.length != values.length) {
            throw new IllegalArgumentException("Invalid knapsack");
        }

        List<Item> eligible = new ArrayList<>();
        for (int i = 0; i < weights.length; i++) {
            if (weights[i] <= 0 || values[i] < 0) {
                throw new IllegalArgumentException(
                        "Require positive weight, nonnegative value");
            }
            if (weights[i] <= capacity) {
                eligible.add(new Item(i, weights[i], values[i]));
            }
        }

        int bestIndex = -1;
        long bestValue = 0;
        for (Item item : eligible) {
            if (item.value() > bestValue) {
                bestValue = item.value();
                bestIndex = item.id();
            }
        }

        // Compare densities by exact cross multiplication of int inputs.
        eligible.sort((a, b) -> {
            long left = (long) b.value() * a.weight();
            long right = (long) a.value() * b.weight();
            int cmp = Long.compare(left, right);
            return cmp != 0 ? cmp : Integer.compare(a.id(), b.id());
        });

        long remaining = capacity;
        long prefixValue = 0;
        double fractionalUpper = 0;
        List<Integer> prefixIds = new ArrayList<>();

        for (Item item : eligible) {
            if (item.weight() <= remaining) {
                remaining -= item.weight();
                prefixValue += item.value();
                fractionalUpper += item.value();
                prefixIds.add(item.id());
            } else {
                // Fractional LP takes this fraction of the next item.
                fractionalUpper += (double) remaining
                        * item.value() / item.weight();
                break;
            }
        }

        if (prefixValue >= bestValue) {
            return new Answer(fractionalUpper, prefixValue,
                    bestValue, prefixValue,
                    prefixIds.stream().mapToInt(Integer::intValue).toArray());
        }
        return new Answer(fractionalUpper, prefixValue, bestValue,
                bestValue, new int[] {bestIndex});
    }

    static boolean feasible(int capacity, int[] weights, int[] selected) {
        long total = 0;
        boolean[] seen = new boolean[weights.length];
        for (int id : selected) {
            if (id < 0 || id >= weights.length || seen[id]) return false;
            seen[id] = true;
            total += weights[id];
        }
        return total <= capacity;
    }

    // Independent exponential oracle, for small test arrays only.
    static long exactOptimum(int capacity, int[] weights, int[] values) {
        int n = weights.length;
        if (n > 22) throw new IllegalArgumentException("Oracle too large");
        long best = 0;
        for (int mask = 0; mask < (1 << n); mask++) {
            long weight = 0, profit = 0;
            for (int i = 0; i < n; i++) {
                if ((mask & (1 << i)) != 0) {
                    weight += weights[i];
                    profit += values[i];
                }
            }
            if (weight <= capacity && profit > best) best = profit;
        }
        return best;
    }

    public static void main(String[] args) {
        int[] weightA = {6, 6, 4};
        int[] valueA = {12, 12, 8};
        Answer a = solve(10, weightA, valueA);
        long optA = exactOptimum(10, weightA, valueA);
        System.out.printf(Locale.ROOT,
                "A fractional LP=%.2f%n", a.fractionalUpper());
        System.out.println("A prefix=" + a.prefix());
        System.out.println("A best single=" + a.bestSingle());
        System.out.println("A rounded=" + a.rounded());
        System.out.println("A exact optimum=" + optA);
        System.out.println("A feasible="
                + feasible(10, weightA, a.selected()));
        System.out.println("A at least half optimum="
                + (2 * a.rounded() >= optA));

        int[] weightB = {2, 10};
        int[] valueB = {2, 9};
        Answer b = solve(10, weightB, valueB);
        System.out.printf(Locale.ROOT,
                "B fractional LP=%.2f%n", b.fractionalUpper());
        System.out.println("B selected=" + Arrays.toString(b.selected()));
        System.out.println("B rounded=" + b.rounded());

        Answer overweight = solve(10, new int[] {11, 4},
                                   new int[] {100, 5});
        System.out.println("overweight ignored="
                + (overweight.rounded() == 5));
        Answer empty = solve(0, new int[] {1}, new int[] {10});
        System.out.println("zero capacity=" + empty.rounded());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 KnapsackFractionalRoundingDemo.java
java KnapsackFractionalRoundingDemo
```

Stdout dự kiến:

```text
A fractional LP=20.00
A prefix=12
A best single=12
A rounded=12
A exact optimum=20
A feasible=true
A at least half optimum=true
B fractional LP=9.20
B selected=[1]
B rounded=9
overweight ignored=true
zero capacity=0
```

### 9.1. Các giả thiết của demo

- Trọng lượng là `int` **dương**, value là `int` **không âm**, capacity là `int` không âm.
- Mỗi item được chọn 0 hoặc1 lần.
- Item quá capacity bị loại từ cả bài 0/1 và LP của **instance đã gia cố** vì nó không thể thuộc nghiệm nguyên.
- Giá trị prefix tích lũy dùng `long`. Với mảng Java có length kiểu int và value kiểu int không âm, tổng tối đa không vượt khoảng 4.61×10^18, dưới `Long.MAX_VALUE`; so mật độ cũng dùng tích int×int an toàn trong `long`.
- Oracle vét cạn chỉ chạy với n≤22; không được tính vào độ phức tạp thuật toán xấp xỉ.

Nếu bài cho phép `weight=0`, phải xử lý các item có value dương như một lớp riêng luôn được chọn; không áp trực tiếp phép chia mật độ. Nếu value âm, tối ưu không bắt buộc chọn item, cần quy ước loại bỏ hoặc mô hình hóa lại.

### 9.2. Điều gì được bảo đảm và không bảo đảm?

Được bảo đảm: nghiệm nguyên **khả thi**, giá trị ≥1/2 tối ưu nguyên dưới các giả thiết.

Không được bảo đảm: đầu ra chính xác tối ưu; một phép `Math.round` tùy ý trên vector fractional cũng có guarantee; quy tắc prefix của bài này dùng được cho bài nhiều constraint tùy ý. Với multidimensional knapsack, cấu trúc một item phân số có thể không còn, cần thuật toán khác.

## 10. Set cover: frequency-f rounding của LP

Cho universe U gồm m phần tử và các tập S_0,...,S_(s−1) phủ universe. Muốn chọn ít tập nhất sao cho **mỗi phần tử thuộc ít nhất một tập được chọn**.

### 10.1. Bài 0/1 và LP

Biến x_j=1 nếu chọn tập S_j.

`minimize Σ_j x_j`

với:

`Σ_(j: e∈S_j) x_j ≥ 1` cho mọi e∈U,

`x_j∈{0,1}`.

LP relaxation: `0≤x_j≤1`.

Có thể thêm trọng số không âm w_j và mục tiêu `Σ w_j x_j`; cùng proof dưới đây vẫn đúng.

### 10.2. Tần suất f

Đặt:

`f=max_(e∈U) |{j : e∈S_j}|`.

Tức **mỗi phần tử xuất hiện trong không quá f tập**. Với một instance khả thi có universe không rỗng, f≥1.

### 10.3. Quy tắc threshold 1/f

Chọn tất cả tập:

`C={j : x_j≥1/f}`.

**Chứng minh phủ:** Với một e cố định, có nhiều nhất f tập chứa e. Vì tổng các x_j trong những tập ấy ≥1, nếu tất cả x_j<1/f thì tổng < f·(1/f)=1, mâu thuẫn. Vậy ít nhất một tập được chọn có chứa e.

**Chặn cost:** Với mỗi j:

`1[j∈C] ≤ f x_j`.

Nếu w_j≥0:

`Σ_(j∈C) w_j ≤ f Σ_j w_j x_j`.

Nếu x là **LP optimal**:

`cost(C) ≤ f OPT_LP ≤ f OPT_IP`.

Đây là **f-approximation** (khi f≥1) cho set cover với frequency bound f. Nếu f lớn gần s, bảo đảm kém; điều này phản ánh cấu trúc input.

### 10.4. Ví dụ ba tập

U={A,B,C}:

- S0={A,B}
- S1={B,C}
- S2={A,C}

Mỗi phần tử xuất hiện ở **hai** tập nên f=2. Điểm LP:

`x0=x1=x2=1/2`

phủ mỗi phần tử với tổng1. LP cost=1.5. Cộng ba ràng buộc phủ ta có `2Σ_j x_j≥3`, nên nghiệm này cũng là **LP optimum**.

Threshold≥1/2 chọn cả ba tập, cost3; optimum nguyên chọn hai tập, cost2. Thuật toán tuân thủ `cost≤2 OPT_IP`.

### 10.5. Trường hợp tần suất0

Nếu U có một phần tử không nằm trong **bất kỳ tập** nào, set cover **không khả thi**; LP cũng không khả thi. Không được “làm tròn” xong rồi giả vờ đã phủ.

Nếu U **rỗng**, nghiệm rỗng với cost0 là tối ưu; quy ước f=0 và trả danh sách tập được chọn rỗng, thay vì chia cho0 trong threshold.

## 11. Java 17 — set cover LP rounding chính xác theo phân số hữu hạn

Để tránh so ngưỡng floating cho ví dụ, đặt mọi x_j bằng:

`x_j = numerator[j] / denominator`

với denominator nguyên dương. Verifier kiểm feasibility bằng phép cộng nguyên:

`Σ numerator[j]≥denominator` với từng phần tử.

Ngưỡng `x_j≥1/f` tương đương:

`f·numerator[j]≥denominator`.

Lưu **FrequencySetCoverRoundingDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class FrequencySetCoverRoundingDemo {
    record Answer(int frequency, double lpCost, int[] selected,
                  int roundedCost, boolean covered) {}

    static Answer round(boolean[][] sets, int universeSize,
                        int[] numerator, int denominator) {
        if (sets == null || numerator == null || universeSize < 0
                || denominator <= 0 || numerator.length != sets.length) {
            throw new IllegalArgumentException("Invalid input");
        }
        int[] frequency = new int[universeSize];
        long[] coverage = new long[universeSize];
        long totalNumerator = 0;

        for (int s = 0; s < sets.length; s++) {
            if (sets[s] == null || sets[s].length != universeSize
                    || numerator[s] < 0 || numerator[s] > denominator) {
                throw new IllegalArgumentException("Invalid set or x");
            }
            totalNumerator += numerator[s];
            for (int e = 0; e < universeSize; e++) {
                if (sets[s][e]) {
                    frequency[e]++;
                    coverage[e] += numerator[s];
                }
            }
        }
        for (int e = 0; e < universeSize; e++) {
            if (coverage[e] < denominator) {
                throw new IllegalArgumentException("Infeasible LP point");
            }
        }

        int f = Arrays.stream(frequency).max().orElse(0);
        List<Integer> chosen = new ArrayList<>();
        for (int s = 0; s < sets.length; s++) {
            if ((long) f * numerator[s] >= denominator) {
                chosen.add(s);
            }
        }

        int[] ids = chosen.stream().mapToInt(Integer::intValue).toArray();
        boolean[] covered = new boolean[universeSize];
        for (int id : ids) {
            for (int e = 0; e < universeSize; e++) {
                if (sets[id][e]) covered[e] = true;
            }
        }
        boolean allCovered = true;
        for (boolean value : covered) {
            if (!value) allCovered = false;
        }

        return new Answer(f, (double) totalNumerator / denominator,
                          ids, ids.length, allCovered);
    }

    // Tiny-instance exhaustive test oracle only.
    static int exactOptimum(boolean[][] sets, int universeSize) {
        int n = sets.length;
        if (n > 20) throw new IllegalArgumentException("Oracle too large");
        int best = Integer.MAX_VALUE;
        for (int mask = 0; mask < (1 << n); mask++) {
            int cost = Integer.bitCount(mask);
            if (cost >= best) continue;
            boolean valid = true;
            for (int e = 0; e < universeSize && valid; e++) {
                boolean found = false;
                for (int s = 0; s < n; s++) {
                    if ((mask & (1 << s)) != 0 && sets[s][e]) {
                        found = true;
                        break;
                    }
                }
                valid = found;
            }
            if (valid) best = cost;
        }
        return best;
    }

    public static void main(String[] args) {
        boolean[][] sets = {
                {true,  true,  false},
                {false, true,  true},
                {true,  false, true}
        };

        Answer r = round(sets, 3, new int[] {1, 1, 1}, 2);
        System.out.println("frequency f=" + r.frequency());
        System.out.printf(Locale.ROOT,
                "LP objective=%.2f%n", r.lpCost());
        System.out.println("selected="
                + Arrays.toString(r.selected()));
        System.out.println("rounded cost=" + r.roundedCost());
        System.out.println("all covered=" + r.covered());
        System.out.println("cost <= f * LP="
                + (r.roundedCost() <= r.frequency() * r.lpCost()));
        System.out.println("integral optimum="
                + exactOptimum(sets, 3));

        boolean invalidRejected = false;
        try {
            round(sets, 3, new int[] {0, 0, 0}, 2);
        } catch (IllegalArgumentException ex) {
            invalidRejected = true;
        }
        System.out.println("infeasible LP rejected="
                + invalidRejected);

        Answer empty = round(new boolean[0][0], 0,
                              new int[0], 1);
        System.out.println("empty universe cost="
                + empty.roundedCost());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 FrequencySetCoverRoundingDemo.java
java FrequencySetCoverRoundingDemo
```

Stdout dự kiến:

```text
frequency f=2
LP objective=1.50
selected=[0, 1, 2]
rounded cost=3
all covered=true
cost <= f * LP=true
integral optimum=2
infeasible LP rejected=true
empty universe cost=0
```

### 11.1. Ý nghĩa của chứng nhận trong ví dụ

Do các giá trị phân số được mã hóa bằng tử số nguyên, việc kiểm tính khả thi và threshold **chính xác** trong phạm vi biểu diễn của demo. Với LP solver trả `double`, kiểm `sum≥1−EPS` có thể chấp nhận một điểm **không thật sự khả thi**. Rounding lúc ấy có thể không phủ hết, nên sau làm tròn vẫn phải kiểm **mọi phần tử được phủ**, đồng thời đánh giá tác động của numerical tolerance tới chứng minh cost.

### 11.2. Chi phí và giới hạn

Cấu trúc boolean[s][m] khiến validate/round tốn O(sm) word operations, chọn/kiểm coverage cũng O(sm) ở worst case. Oracle O(2^s sm) chỉ dùng khi s nhỏ. Chương trình không tự giải LP, nó nhận một **điểm phân số đã có**, và guarantee so với OPT chỉ áp dụng nếu điểm đó là LP tối ưu (hoặc có giới hạn gần tối ưu được chứng minh).

Nếu dùng số rất lớn tùy ý, thay kiểu int/long bằng BigInteger để tránh overflow ở phép cộng coverage và tích f·numerator; ở demo giới hạn mảng Java và int đảm bảo các tích/chuỗi cộng dưới miền `long` với giả thiết môi trường thực thi có thể cấp phát mảng.

## 12. Java 17 — phản ví dụ làm tròn ngây thơ

Để thấy **tại sao không thể thay proof bằng Math.round**, ta dùng hai điểm fractional khả thi nhưng threshold0.5 làm hỏng ràng buộc **packing**.

Lưu **RoundingPitfallsDemo.java**:

```java
public class RoundingPitfallsDemo {
    static boolean independent(int[][] edges, boolean[] picked) {
        for (int[] edge : edges) {
            if (picked[edge[0]] && picked[edge[1]]) {
                return false;
            }
        }
        return true;
    }

    static int count(boolean[] picked) {
        int result = 0;
        for (boolean value : picked) {
            if (value) result++;
        }
        return result;
    }

    public static void main(String[] args) {
        // Triangle stable-set LP has x=(1/2,1/2,1/2):
        // For every edge (u,v), x_u + x_v <= 1.
        int[][] edges = {{0, 1}, {1, 2}, {0, 2}};
        int[] twiceX = {1, 1, 1};
        boolean fractionalFeasible = true;
        for (int[] edge : edges) {
            if (twiceX[edge[0]] + twiceX[edge[1]] > 2) {
                fractionalFeasible = false;
            }
        }

        boolean[] naive = new boolean[3];
        for (int v = 0; v < 3; v++) {
            naive[v] = twiceX[v] >= 1;
        }

        // A simple greedy repair yields feasibility, not a general ratio.
        boolean[] repaired = new boolean[3];
        for (int v = 0; v < 3; v++) {
            if (!naive[v]) continue;
            repaired[v] = true;
            if (!independent(edges, repaired)) {
                repaired[v] = false;
            }
        }

        System.out.println("triangle fractional feasible="
                + fractionalFeasible);
        System.out.println("naive independent feasible="
                + independent(edges, naive));
        System.out.println("naive selected vertices=" + count(naive));
        System.out.println("greedy repair feasible="
                + independent(edges, repaired));
        System.out.println("greedy repair size=" + count(repaired));

        // x1 + x2 <= 1, x1=x2=1/2.
        int[] half = {1, 1};
        int denominator = 2;
        int fractionalSum = half[0] + half[1];
        int roundedSum = (half[0] >= 1 ? 1 : 0)
                       + (half[1] >= 1 ? 1 : 0);

        System.out.println("cardinality fractional feasible="
                + (fractionalSum <= denominator));
        System.out.println("cardinality rounded sum=" + roundedSum);
        System.out.println("cardinality rounded feasible="
                + (roundedSum <= 1));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 RoundingPitfallsDemo.java
java RoundingPitfallsDemo
```

Stdout dự kiến:

```text
triangle fractional feasible=true
naive independent feasible=false
naive selected vertices=3
greedy repair feasible=true
greedy repair size=1
cardinality fractional feasible=true
cardinality rounded sum=2
cardinality rounded feasible=false
```

**Ý nghĩa:** Với vertex cover, threshold≥1/2 hoạt động vì constraint có chiều **≥1**. Với independent set và packing/cardinality có chiều **≤1**, cùng threshold có thể tạo lời giải **bất khả thi**. Greedy repair khôi phục tính khả thi nhưng không tự cho approximation ratio trên mọi đồ thị.

## 13. Randomized rounding: dùng xác suất thay cho ngưỡng cứng

Nhiều bài có nghiệm LP x_i∈[0,1] nhưng không có quy tắc threshold đơn giản. Một kỹ thuật là **randomized rounding**: chọn biến nguyên X_i∈{0,1} với:

`Pr[X_i=1]=x_i`

hoặc một xác suất đã điều chỉnh, thường độc lập trong bản cơ bản.

### 13.1. Bảo toàn kỳ vọng

Nếu X_i Bernoulli(x_i), thì:

`E[X_i]=x_i`.

Với objective tuyến tính `Σ c_i X_i`:

`E[Σ c_i X_i]=Σ c_i x_i`.

Nhưng **kỳ vọng bằng mục tiêu LP không bảo đảm một lần làm tròn khả thi**. Ví dụ packing `X_1+X_2≤1` với x=(0.5,0.5), chọn độc lập thì có xác suất 1/4 chọn cả hai, gây vi phạm.

### 13.2. Set cover và khuếch đại xác suất

Giả sử LP set cover khả thi, universe có m≥1 phần tử. Chọn mỗi tập j độc lập với:

`p_j=min(1, c x_j)`,

trong đó `c>0` là hệ số khuếch đại.

Với phần tử e, nếu một p_j=1 ở tập chứa e thì e chắc chắn được phủ. Nếu mọi p_j<1 đối với các tập chứa e:

`Pr[e không được phủ] = ∏_(j:e∈S_j) (1−p_j)`.

Vì `1−t≤exp(−t)`:

`Pr[e chưa phủ] ≤ exp(−Σ p_j)`.

Khi chưa có p_j bị chặn về1, `Σp_j=cΣx_j≥c` nhờ ràng buộc LP. Do đó:

`Pr[e chưa phủ]≤e^(−c)`.

### 13.3. Union bound cho toàn universe

Bằng bất đẳng thức union bound:

`Pr[tồn tại e chưa phủ] ≤ Σ_e Pr[e chưa phủ] ≤ m e^(−c)`.

Chọn:

`c=ln(m/δ)` với 0<δ<1,

thì:

`Pr[không phủ hết]≤δ`.

Cùng lúc, với chi phí tập không âm w_j:

`E[cost]=Σ w_j p_j ≤ c Σ w_j x_j = c·LP_cost`.

**Cẩn thận:** “phủ hết với xác suất ≥1−δ” và “chi phí kỳ vọng≤c LP” **không có nghĩa mỗi lần chạy đều thỏa cả hai**.

### 13.4. Tạo bảo đảm về một lần chạy bằng Markov

Với t>1, từ bất đẳng thức Markov:

`Pr[cost > t c LP_cost] ≤ 1/t`.

Kết hợp union bound:

`Pr[phủ hết và cost ≤ t c LP_cost] ≥ 1−δ−1/t`.

Ví dụ δ=0.1, t=2 ⇒ xác suất **ít nhất0.4** có một lần làm tròn vừa phủ hết vừa có cost≤`2 ln(10m) LP_cost`, khi các giả thiết đúng.

Nếu x là LP optimum, cost trong lần thành công đó ≤`2 ln(10m) OPT_IP`. Có thể thử lại và **kiểm nghiệm đầu ra**, nhưng không coi một lần ngẫu nhiên thất bại là nghiệm đúng; việc bảo đảm thời gian/kỳ vọng số lần thử cần dựa vào xác suất thành công đã chứng minh.

### 13.5. Sửa những phần tử còn thiếu

Một biến thể set cover: chọn ngẫu nhiên rồi **repair** các phần tử chưa phủ. Giá repair phải được đưa vào phân tích kỳ vọng/chất lượng; không được bỏ qua chi phí sửa rồi vẫn tuyên bố bound ban đầu.

### 13.6. Ràng buộc packing

Với bài có constraint **≤capacity**, random independent chọn nhiều biến có thể vượt giới hạn. Có thể giảm các p_i, dùng Chernoff/Hoeffding để chặn tail rồi repair/alteration, hoặc dùng **dependent rounding** để bảo toàn tổng số chọn gần như chắc chắn. Mỗi kiểu bảo đảm phải được chứng minh cho bài toán cụ thể.

## 14. Dependent rounding và cấu trúc đa diện

### 14.1. Vì sao cần phụ thuộc?

Nếu một constraint yêu cầu đúng k đối tượng:

`Σ_i X_i=k`,

chọn X_i độc lập có thể cho tổng khác k. **Dependent rounding** chọn các biến có tương quan để giữ tổng/cạnh tranh tài nguyên, đồng thời cố bảo toàn xác suất biên `E[X_i]` và các thuộc tính tập trung.

Một ý tưởng phổ biến là di chuyển giữa hai biến phân số theo đường:

`(x_i,x_j) → (x_i+ε,x_j−ε)`

để giữ tổng, đẩy ít nhất một biến về0 hoặc1. Random chọn hướng với xác suất cân bằng có thể giữ kỳ vọng. Cần kiểm các constraint khác, không thể áp tùy tiện vào đa diện bất kỳ.

### 14.2. Pipage/swap rounding

Các kỹ thuật như **pipage rounding** hoặc **swap rounding** xuất hiện trong bài toán có cấu trúc matroid/submodular. Chúng không phải hàm thư viện thay thế Math.round cho mọi bài.

Chất lượng phụ thuộc tính chất của objective, ví dụ tuyến tính/submodular, và khả năng di chuyển trong miền khả thi liên tục.

### 14.3. Flow và path decomposition

Trong network flow với capacity nguyên, có thể tìm nghiệm flow nguyên qua các thuật toán phù hợp. Nếu một LP cho fractional flow, việc làm tròn từng cạnh độc lập có thể **phá bảo toàn luồng tại đỉnh**. Cần decomposition/các thủ tục làm tròn giữ tính bảo toàn.

## 15. Khi nào LP relaxation đã có nghiệm nguyên?

Không phải bài toán nào cũng có integrality gap>1.

### 15.1. Total unimodularity

Một ma trận có mọi định thức của các ma trận con vuông thuộc {-1,0,1} gọi là **totally unimodular** (TU). Với hệ bất đẳng thức thích hợp, vector vế phải nguyên và giới hạn nguyên, tính TU giúp bảo đảm **các điểm cực biên của đa diện là nguyên**.

Khi objective tuyến tính hữu hạn đạt optimum tại một cực biên, có thể tìm nghiệm LP tối ưu **nguyên**, không chịu rounding loss.

### 15.2. Bipartite matching

LP matching chuẩn trên đồ thị hai phía:

`maximize Σ_(e∈E) w_e x_e`,

với:

`Σ_(e incident v) x_e ≤ 1` cho mỗi đỉnh v,

`x_e ≥ 0`.

Trên **đồ thị hai phía**, đa diện matching này có các đỉnh nguyên; optimum LP có thể chọn nguyên. Ta cũng có thuật toán matching tổ hợp đa thức.

Trên **đồ thị không hai phía**, các constraint bậc đơn giản ấy chưa đủ mô tả convex hull của matching. Ví dụ tam giác với x_e=1/2 trên ba cạnh thỏa mọi constraint bậc, objective1.5, nhưng matching nguyên lớn nhất chỉ có1 cạnh. Các *odd-set inequalities* có vai trò trong mô tả matching polytope tổng quát.

### 15.3. LP solver có thể trả nghiệm phân số dù có nghiệm nguyên tối ưu

Khi có nhiều nghiệm tối ưu, phép phối hợp lồi của hai nghiệm nguyên tối ưu cũng có thể là **một nghiệm tối ưu phân số**. Tính integral polytope bảo đảm **tồn tại cực biên nguyên tối ưu** — không hứa mọi điểm tối ưu mà một solver trả đều nguyên.

Vì vậy cần chọn một nghiệm cực biên phù hợp, thuật toán tổ hợp, hoặc thủ tục biểu diễn/decomposition, thay vì khẳng định “bất kỳ vector LP nào cũng nguyên”.

## 16. Giải LP thực tế và lưu ý số học

### 16.1. LP giải được đa thức nhưng không có nghĩa mọi thuật toán LP đều đa thức

Với hệ số hữu tỷ mã hóa nhị phân, LP có thuật toán đa thức theo bit-length (ví dụ các phương pháp ellipsoid/interior-point với điều kiện kỹ thuật). Simplex rất hiệu quả trong nhiều ứng dụng nhưng **không có bảo đảm worst-case đa thức cho quy tắc pivot thông dụng**.

Thời gian *solve LP* là một phần của độ phức tạp toàn thuật toán, ngoài thời gian làm tròn.

### 16.2. Tolerance của solver không phải chứng chỉ toán học

LP solver thường dùng double và cho phép vi phạm nhỏ:

`Ax ≥ b−EPS`.

Nếu thật sự có một cạnh vertex cover với:

`x_u=0.499999999`, `x_v=0.499999999`,

cả hai có thể bị làm tròn xuống theo threshold≥0.5, để cạnh **không được phủ**. Một điểm chỉ gần khả thi không đáp ứng giả thiết của chứng minh.

Cần:

- Kiểm feasibility của điểm LP với tolerance phù hợp.
- Rounding bảo đảm feasibility trong môi trường số (có thể cần repair được phân tích).
- Hậu kiểm **nghiệm nguyên thực tế** bằng phép toán rời rạc.
- Báo rõ khi bound tỷ lệ cần điều chỉnh vì sai số solver.

### 16.3. Tính objective đủ an toàn

Trọng số/giá trị lớn có thể làm tràn `int`/`long` khi cộng. Nếu tham số là số nguyên lớn tùy ý, dùng BigInteger hoặc số học bội chính xác. Khi so density v/w của knapsack, dùng **tích chéo** để tránh sai thứ tự do chia floating nếu kiểu số cho phép.

### 16.4. Kết quả solver chưa chứng minh x là LP optimal

Một vector fractional thỏa constraint chỉ là nghiệm **khả thi**. Muốn dùng `cost(round)≤α OPT_LP`, cần:

- LP solver có bảo đảm về optimality (ví dụ dual bound phù hợp).
- Hoặc chứng minh optimum bằng tay như các ví dụ tam giác/chu trình.
- Hoặc có một cận β đối với điểm phân số thực sự sử dụng.

Đừng thay status `FEASIBLE` thành `OPTIMAL` chỉ vì residual primal nhỏ.

## 17. Covering và packing yêu cầu hai hướng làm tròn khác nhau

### 17.1. Covering: ràng buộc phải đủ lớn

Dạng:

`Ax ≥ b`, `A≥0`, `x≥0`.

Làm tròn **lên** có thể giúp giữ các bất đẳng thức `≥`, nhưng làm tăng chi phí minimization. Threshold/frequency/primal-dual thường tìm cách trả giá tăng **có kiểm soát**.

Vertex cover và set cover là ví dụ. Lấy mọi biến x_i>0 thành1 luôn bảo toàn feasibility trong nhiều mô hình covering, nhưng tỷ lệ cost có thể **vô hạn/không bounded** nếu x_i rất nhỏ.

### 17.2. Packing: ràng buộc không được vượt

Dạng:

`Ax ≤ b`, `A≥0`, `x≥0`.

Làm tròn **xuống** giúp giữ capacity, nhưng có thể làm mất lợi ích maximization. Knapsack prefix-vs-best-single là một thiết kế khai thác cấu trúc fractional để chặn giá trị mất.

### 17.3. Equalities và balance

Với `Ax=b`, cả làm tròn lên/xuống đều có thể phá điều kiện. Cần phương pháp giữ tổng, flow conservation, matching structure hoặc dependent rounding.

### 17.4. Dữ liệu có dấu âm

Nếu A hoặc objective có hệ số âm, các lập luận đơn điệu “làm tròn lên giữ covering” hoặc “giảm x giữ packing” có thể thất bại. Chứng minh phải xét **dấu hệ số**, không chỉ tên bài toán.

## 18. Nâng chất lượng nghiệm sau làm tròn

Một lời giải rounding có bảo đảm có thể được **cải thiện bằng heuristic** mà không phá bảo đảm nếu chỉ nhận các bước hợp lệ và không làm xấu objective.

### 18.1. Vertex cover

Sau threshold, thử bỏ từng đỉnh đã chọn; bỏ v nếu **mọi cạnh vẫn còn ít nhất một đầu được chọn**. Mỗi lần bỏ làm giảm cost, nên luôn giữ:

`cost(improved)≤cost(rounded)≤2 OPT_IP`.

Trong đồ thị chu trình bốn đỉnh, từ bốn đỉnh có thể giảm còn hai đỉnh. Nhưng local pruning không đảm bảo luôn tìm optimum.

### 18.2. Knapsack

Sau khi có ứng viên prefix/best-single, có thể thử thêm item còn vừa hoặc trao đổi item để tăng profit. Chỉ nhận nghiệm **khả thi** và profit không giảm thì vẫn giữ guarantee ≥1/2 optimum.

### 18.3. Set cover

Thử bỏ tập không cần thiết khi các phần tử vẫn được các tập khác phủ. Chi phí không tăng, vẫn giữ bound f nếu đầu vào fractional đạt giả thiết. Nếu trọng số khác nhau, phải tính lại cost đúng.

### 18.4. Repair không miễn phí

Nếu rounding ban đầu **bất khả thi**, một bước repair (ví dụ thêm toàn bộ tập phủ còn thiếu) có thể tăng cost vượt bound đã chứng minh. Cần **phân tích cả repair** nếu muốn tuyên bố approximation ratio.

### 18.5. Không đánh đồng guarantee và kết quả thực nghiệm

Một thuật toán 2-approx có thể chạy rất tốt trên dữ liệu tự nhiên, thường tìm nghiệm sát optimum. Nhưng không được kết luận “1.05-approx” từ trung bình benchmark nhỏ nếu không có chứng minh worst-case mới. Báo rõ `empirical ratio` khác `proven ratio`.

## 19. Chọn kỹ thuật theo cấu trúc

| Bài toán / cấu trúc | Relaxation | Rounding điển hình | Bảo đảm minh họa |
|---|---|---|---|
| Vertex cover | LP x_u+x_v≥1 | Chọn x_v≥1/2 | 2-approx nếu LP optimal |
| Set cover, max frequency f | LP phần tử phủ≥1 | Chọn x_j≥1/f | f-approx nếu LP optimal |
| 0/1 knapsack, 1 capacity | Fractional greedy LP | Max(prefix,best-single) | ≥1/2 OPT_IP |
| Set cover tổng quát | LP phủ≥1 | Random p=min(1,cx) + kiểm/repair | O(log m) dưới phân tích phù hợp |
| Independent set general | Edge LP x_u+x_v≤1 | Threshold0.5 ngây thơ | **Không giữ feasibility** |
| Bipartite matching | Matching LP | Tận dụng integral extreme point | Không mất ratio do relaxation |
| Flow balance | Flow LP | Decomposition/integrality | Phụ thuộc cấu trúc mạng |
| Cardinality exact k | Tổng x_i=k | Dependent rounding | Giữ tổng nếu phương pháp phù hợp |
| Multidimensional knapsack | LP nhiều capacity | Cần thuật toán riêng | Không suy 1/2 từ một item lẻ |

**Nguyên tắc:** Chọn theo **cấu trúc ràng buộc** và mục tiêu, không theo tên “LP rounding”.

## 20. Phân tích chất lượng xấp xỉ đúng chuẩn

### 20.1. Min và max

- **Minimization:** α≥1; muốn `ALG≤α OPT_IP`.
- **Maximization:** α≥1; muốn `ALG≥OPT_IP/α`.

Không nói “tỷ số ≥2” cho minimization hoặc “≤2” cho maximization mà không ghi rõ đang so `ALG/OPT` hay `OPT/ALG`.

### 20.2. Feasibility là điều kiện tiên quyết

Một lời giải có cost rất nhỏ nhưng không phủ hết đồ thị **không phải** một vertex cover và không được tính vào approximation ratio. Tương tự, knapsack vượt capacity có profit lớn không hợp lệ.

### 20.3. Worst-case vs expected ratio

Randomized rounding có thể chỉ đạt bound **theo kỳ vọng** hoặc **với xác suất cao**. Nếu lời giải đôi khi bất khả thi, phải tính xác suất/thủ tục sửa và không gọi mọi output là hợp lệ.

### 20.4. Điều kiện LP optimum

Trong định lý vertex cover/set cover, **nguồn của cận OPT_LP** là nghiệm tối ưu LP, không phải điểm bất kỳ. Nếu LP giải sai hoặc bị dừng sớm, cần dual bound/optimality gap để đưa guarantee thực tế.

### 20.5. Integrality gap tạo giới hạn cho loại phân tích

Nếu LP gap của một họ instance tăng không chặn, một chứng minh ratio hằng **chỉ dựa trên so sánh output với LP optimum** có thể không khả thi. Cần tăng cường relaxation, khai thác cấu trúc hoặc phương pháp hoàn toàn khác.

## 21. Kiểm thử độc lập bằng oracle

### 21.1. Vertex cover

Với n nhỏ (ví dụ n≤12), enumerate toàn bộ 2^n tập đỉnh để tìm optimum nguyên. Với một vector LP nửa nguyên khả thi, kiểm:

- Mọi cạnh có `z_u+z_v≥2`.
- Sau threshold, mọi cạnh vẫn được phủ.
- `roundedCost≤Σ z_v` (vì `2·LP=Σ z_v`).
- Nếu vector LP thực sự tối ưu, `roundedCost≤2·OPT_IP`.

Chỉ kiểm `cost≤2·LP của vector` **không chứng minh LP optimality**.

### 21.2. Knapsack

Với n≤20, brute force mọi tập item và so profit tốt nhất với thuật toán làm tròn. Kiểm:

- Mỗi ID được dùng tối đa1 lần.
- Tổng weight≤capacity.
- Profit bằng tổng value của ID được chọn.
- `roundedProfit≥OPT_IP/2`.
- Fractional upper bound được tính bởi greedy density và `OPT_LP≥OPT_IP`.

### 21.3. Set cover

Với số tập nhỏ, brute force mọi tập con của tập S_j. Kiểm:

- Mỗi phần tử U được phủ.
- Với x_j=num_j/denom, mỗi phần tử có `Σ num_j≥denom`.
- `roundCost·denom≤f Σ num_j` (so sánh **số nguyên**, không dùng EPS).
- Nếu đã chứng minh fractional optimum, so với `f·OPT_IP`.

### 21.4. Phản ví dụ

Với tam giác independent-set fractional0.5 trên từng đỉnh, kiểm input LP **khả thi** nhưng nghiệm threshold bất khả thi. Với cardinality x=(0.5,0.5), tổng phân số1 nhưng threshold chọn2. Những test này ngăn việc chuyển nhầm công thức covering sang packing.

### 21.5. Biến hình

- Đổi nhãn đỉnh đồ thị phải giữ optimum và guarantee khi chuyển chứng chỉ tương ứng.
- Nhân tất cả chi phí không âm với cùng c>0 không đổi các tập nghiệm tối ưu; giá trị objective nhân c.
- Thêm một item knapsack quá sức chứa không thay đổi optimum nguyên; thuật toán nên loại nó khỏi relaxation đã gia cố.
- Bỏ bớt ràng buộc LP có thể giảm cận dưới min hoặc tăng cận trên max, nhưng không tự cải thiện ratio.

### 21.6. Bộ dữ liệu biên

Kiểm đồ thị rỗng, tập universe rỗng, edge loop nếu domain cấm, item weight=0 hoặc value âm nếu domain cấm, capacity=0, rất nhiều item cùng density, LP không khả thi, một phần tử set cover không thuộc tập nào, numerator=0/denominator, và số quá giới hạn nguyên.

## 22. Những lỗi thường gặp

### Lỗi 1 — Gọi mọi nghiệm phân số là nghiệm tối ưu LP

Một nghiệm chỉ khả thi không cho cận chất lượng tương đương OPT_LP.

### Lỗi 2 — Đảo chiều cận

Min dùng LP lower bound; max dùng LP upper bound.

### Lỗi 3 — Nới lỏng làm mất nghiệm nguyên

Một relaxation đúng phải chứa toàn bộ nghiệm nguyên khả thi.

### Lỗi 4 — Tự coi x∈[0,1] là lời giải nguyên

Ứng dụng vẫn cần x∈{0,1} trừ khi bài cho phép chia nhỏ.

### Lỗi 5 — Làm tròn từng biến rồi không kiểm ràng buộc

Packing, matching, assignment, flow thường bị phá.

### Lỗi 6 — Áp threshold0.5 của vertex cover vào independent set

Một bài có `x_u+x_v≥1`, bài kia có `≤1`.

### Lỗi 7 — Chứng minh cost nhưng quên feasibility

Approximation ratio không áp cho nghiệm bất khả thi.

### Lỗi 8 — Chứng minh feasibility nhưng quên cost

Lấy tất cả đỉnh luôn phủ cạnh, nhưng chưa tự là thuật toán tốt.

### Lỗi 9 — Lấy điểm LP bất kỳ để kết luận ratio với OPT_IP

Chỉ có `cost(round)≤α cost(xF)`, chưa có `≤α OPT_IP`.

### Lỗi 10 — Nhầm integrality gap với ratio của output làm tròn

Chúng là hai tỷ số khác nhau.

### Lỗi 11 — Cho rằng gap1 thì rounding bất kỳ tối ưu

LP nguyên tối ưu vẫn có thể có nghiệm phân số khác và quy tắc làm tròn dở.

### Lỗi 12 — Coi relaxation càng lỏng càng tốt

Relaxation yếu có gap lớn, không giúp chứng minh ratio.

### Lỗi 13 — Không kiểm weights không âm trong proof cost

Với objective có hệ số âm, nhân bất đẳng thức có thể đảo/không giữ logic.

### Lỗi 14 — Vertex cover threshold lớn hơn 1/2

Một cạnh có x_u=x_v=0.5; threshold0.6 chọn **không đỉnh nào**.

### Lỗi 15 — Vertex cover threshold x≥0.5 nhưng LP có lỗi số

Nếu x_u+x_v<1 do epsilon solver, proof giữ cạnh có thể sai.

### Lỗi 16 — Bỏ qua việc LP vertex cover có nghiệm half-integral tối ưu

Trong demo mã hóa z=2x chính xác, tránh lỗi ngưỡng, nhưng không phải mọi LP solver sẽ trả đúng nửa nguyên theo biểu diễn double.

### Lỗi 17 — Nhầm fractional greedy của knapsack với thuật toán tối ưu 0/1

Greedy theo density chính xác cho fractional, không cho 0/1 tổng quát.

### Lỗi 18 — Không giữ best-single knapsack

Chỉ prefix có thể kém xa một item riêng lẻ có lợi ích lớn.

### Lỗi 19 — Không bỏ item quá capacity trước khi chứng minh 1/2

Item không thể chọn nguyên nhưng có thể được LP gốc lấy phân số và làm bound quá lỏng.

### Lỗi 20 — Cho phép weight0 rồi chia để xếp density

Cần xử lý riêng item weight0, value dương.

### Lỗi 21 — Dùng phép chia double để xếp density mà không kiểm sai số

Tích chéo nguyên/BigInteger có thể tránh tie giả với dữ liệu chính xác.

### Lỗi 22 — Cộng profit vào int gây overflow

Dùng long hoặc BigInteger tùy miền input.

### Lỗi 23 — Cho rằng knapsack nhiều constraint vẫn chỉ có một item fractional

Tính chất một constraint không chuyển nguyên sang multidimensional knapsack.

### Lỗi 24 — Set cover dùng ngưỡng 1/f nhưng tính sai f

f là **số tập tối đa chứa cùng một phần tử**, không phải số phần tử trong một tập.

### Lỗi 25 — Set cover không kiểm element bị bỏ trống

Nếu một phần tử không được tập nào chứa, LP không khả thi.

### Lỗi 26 — Với universe rỗng vẫn chia threshold cho f=0

Nên trả nghiệm rỗng cost0.

### Lỗi 27 — Gọi randomized rounding là luôn khả thi

Bernoulli độc lập có xác suất vi phạm ràng buộc.

### Lỗi 28 — Lấy kỳ vọng cost làm guarantee cho từng lần chạy

`E[cost]≤c LP` không nói mọi mẫu cost≤c LP.

### Lỗi 29 — Dùng union bound nhưng quên số phần tử m

Mọi element riêng có xác suất uncovered≤e^-c; toàn universe cần nhân m.

### Lỗi 30 — Bỏ cost của bước repair

Repair có thể làm tổng cost tăng quá chứng minh ban đầu.

### Lỗi 31 — Giả định LP solver trả chính xác mọi bất đẳng thức

Floating tolerance và dữ liệu có điều kiện xấu cần hậu kiểm.

### Lỗi 32 — Cho rằng simplex luôn đa thức worst-case

LP có thuật toán đa thức, nhưng quy tắc simplex phổ biến không có guarantee worst-case đa thức.

### Lỗi 33 — Nói TU khiến mọi điểm tối ưu đều nguyên

TU bảo đảm các extreme points nguyên dưới giả thiết; tổ hợp lồi của hai điểm nguyên tối ưu vẫn có thể phân số.

### Lỗi 34 — Matching tam giác có relaxation tích phân

Đa diện degree constraints trên graph không hai phía có thể có nghiệm fractional0.5 mỗi cạnh.

### Lỗi 35 — Gọi kết quả local search là approximation mới mà không proof

Cải thiện thực nghiệm khác với worst-case guarantee.

### Lỗi 36 — Đặt ratio bằng `ALG/OPT` khi OPT=0

Phép chia0 không có nghĩa; dùng bất đẳng thức mục tiêu.

### Lỗi 37 — Dùng brute-force oracle trong thuật toán production và vẫn bảo O(n log n)

Oracle là test riêng, không nằm trong thuật toán xấp xỉ.

### Lỗi 38 — Kiểm một bộ ví dụ rồi tuyên bố proof toàn cục

Kiểm thử tăng tin cậy triển khai, không thay thế định lý approximation.

## 23. Bài tập có đáp án

### Bài 1 — Nhận biết min/max

LP relaxation của minimization cho cận trên hay dưới so với optimum nguyên?

**Đáp án:** Cận **dưới**, `OPT_LP≤OPT_IP`.

### Bài 2 — Maximization

LP relaxation của maximization cho cận nào?

**Đáp án:** Cận **trên**, `OPT_IP≤OPT_LP`.

### Bài 3 — Nghiệm LP chỉ khả thi

Từ `cost(round(x))≤2 cost(x)` cho x khả thi LP bất kỳ, suy luôn `cost(round)≤2 OPT_IP` được không?

**Đáp án:** Không; cần x optimal LP hoặc một bound gần tối ưu đã chứng minh.

### Bài 4 — Feasibility của relaxation

Một relaxation hợp lệ phải chứa tập nghiệm nào?

**Đáp án:** Mọi nghiệm nguyên khả thi (được nhúng vào không gian liên tục).

### Bài 5 — Tỷ lệ min

2-approx minimization nghĩa là?

**Đáp án:** Nghiệm hợp lệ với `ALG≤2 OPT_IP`.

### Bài 6 — Tỷ lệ max

2-approx maximization nghĩa là?

**Đáp án:** Nghiệm hợp lệ với `ALG≥OPT_IP/2`.

### Bài 7 — Vertex cover tam giác

x=(0.5,0.5,0.5), LP objective?

**Đáp án:** 1.5.

### Bài 8 — Vertex cover tam giác, rounding

Threshold≥0.5 chọn bao nhiêu đỉnh?

**Đáp án:** 3; optimum nguyên là2.

### Bài 9 — Proof feasibility VC

Vì sao trên mỗi cạnh ít nhất một đầu x≥0.5?

**Đáp án:** Nếu cả hai <0.5, tổng <1 trái ràng buộc LP.

### Bài 10 — Proof cost VC

Vì sao cost(round)≤2Σx?

**Đáp án:** Mỗi indicator chọn đỉnh ≤2x_v; cộng các v.

### Bài 11 — Chu trình bốn đỉnh

LP optimum=2, IP optimum=2, rounding x=0.5 cả bốn chọn4. Gap LP bao nhiêu?

**Đáp án:** 1; ratio rounding so với IP là2.

### Bài 12 — Weighted VC

Trọng số không âm, threshold≥0.5 còn factor2 không?

**Đáp án:** Có, khi x là LP optimum; vì Σ w_v indicator≤2Σ w_v x_v.

### Bài 13 — Knapsack fractional

Fractional greedy sắp theo gì?

**Đáp án:** `value/weight` giảm dần khi weight>0.

### Bài 14 — Knapsack một item lẻ

Nghiệm fractional optimum của knapsack một capacity có tối đa bao nhiêu item phân số sau khi sắp density?

**Đáp án:** Có thể chọn cấu trúc với **tối đa một** item phân số.

### Bài 15 — 1/2 approximation

Với P=12, best-single=12, LP upper=20, output?

**Đáp án:** 12; đạt 60% optimum nguyên20.

### Bài 16 — Best-single quan trọng

C=10, items (w2,v2) và (w10,v9), rounded value?

**Đáp án:** 9 (chọn item thứ hai).

### Bài 17 — Item quá capacity

Vì sao lọc item w>C trước fractional LP của thuật toán 1/2?

**Đáp án:** Nó không thể thuộc bất kỳ nghiệm nguyên; giữ nó cho LP lấy phân số có thể phá chứng minh bound P+B.

### Bài 18 — Knapsack zero capacity

Với mọi weight>0 và C=0, optimum nguyên?

**Đáp án:** 0, chọn rỗng.

### Bài 19 — Set cover frequency

f là gì?

**Đáp án:** Số tập **lớn nhất** có chứa cùng một phần tử universe.

### Bài 20 — Set cover ngưỡng

Nếu f=3, threshold chọn tập có x_j ít nhất bao nhiêu?

**Đáp án:** 1/3.

### Bài 21 — Proof phủ

Vì sao ∑ x_j≥1 trên ≤f tập bảo đảm một x_j≥1/f?

**Đáp án:** Phản chứng: nếu tất cả <1/f, tổng <1.

### Bài 22 — Ví dụ set cover ba tập

Ba tập phủ cặp A/B/C, x mỗi tập0.5, LP cost và rounding cost?

**Đáp án:** LP1.5, rounding chọn3 tập, cost3; optimum nguyên2.

### Bài 23 — Universe rỗng

Chi phí tối ưu với U rỗng và chi phí tập không âm?

**Đáp án:** 0 bằng chọn không tập nào.

### Bài 24 — Independent set

Tam giác x_v=0.5 cho mọi đỉnh thỏa LP `x_u+x_v≤1`. Threshold≥0.5 có hợp lệ không?

**Đáp án:** Không; chọn cả ba, vi phạm tính độc lập.

### Bài 25 — Constraint tổng

x=(0.5,0.5), Σx≤1. Threshold≥0.5 tạo tổng bao nhiêu?

**Đáp án:** 2, vi phạm.

### Bài 26 — Random expectation

Nếu X_i là Bernoulli(x_i), E[X_i] bằng gì?

**Đáp án:** x_i.

### Bài 27 — Union bound

Mỗi trong m phần tử có Pr[uncovered]≤e^-c, toàn universe xác suất có phần tử chưa phủ chặn bởi?

**Đáp án:** `m e^-c`.

### Bài 28 — Chọn c

Muốn xác suất thiếu phủ≤δ, có thể dùng c bằng gì?

**Đáp án:** `ln(m/δ)` với m≥1, 0<δ<1.

### Bài 29 — Cost của randomized rounding

E[cost]≤c LP có bảo đảm từng lần cost≤c LP không?

**Đáp án:** Không; đó là bound kỳ vọng.

### Bài 30 — Markov

Chọn t=2, δ=0.1, xác suất có lần vừa phủ vừa cost≤2cLP ít nhất?

**Đáp án:** `1−0.1−1/2=0.4`.

### Bài 31 — TU

Vì sao matching trên đồ thị hai phía có LP optimum nguyên?

**Đáp án:** Đa diện matching ở đồ thị hai phía có extreme points nguyên nhờ cấu trúc TU/integrality.

### Bài 32 — Matching tam giác

LP degree constraints gán x_e=0.5 trên ba cạnh tam giác có giá trị1.5; matching nguyên lớn nhất?

**Đáp án:** 1.

### Bài 33 — Precision LP

Một solver báo x_u+x_v=0.999999999 trong LP VC, threshold≥0.5 có thể làm hỏng cover không?

**Đáp án:** Có, nếu cả hai x<0.5; cần kiểm/repair có phân tích.

### Bài 34 — Local improvement

Nếu đã có cover 2-approx, tiếp tục bỏ đỉnh mà vẫn giữ cover có phá guarantee không?

**Đáp án:** Không, chi phí chỉ giảm, feasibility được giữ.

### Bài 35 — Multiple constraints

Một fractional knapsack có hai constraints có nhất thiết chỉ một item phân số không?

**Đáp án:** Không, không áp trực tiếp proof của bài một constraint.

### Bài 36 — Ratio khi OPT=0

Có nên tính ALG/OPT như số thực bình thường không?

**Đáp án:** Không; dùng bất đẳng thức phù hợp và quy ước trường hợp0.

## 24. Checklist áp dụng nới lỏng và làm tròn

1. Đã nêu rõ **bài toán 0/1 nguyên** và mục tiêu min/max?
2. Đã biểu diễn ràng buộc bằng bất đẳng thức đúng hướng?
3. Relaxation có chứa **mọi nghiệm nguyên hợp lệ**?
4. Đã phân biệt LP khả thi với LP **tối ưu**?
5. Đã biết hướng cận OPT_LP so với OPT_IP?
6. Có giải thích các biến x∈[0,1] mang nghĩa gì?
7. Quy tắc rounding có được định nghĩa rõ?
8. Mỗi output sau rounding có nguyên 0/1 đúng domain?
9. Đã chứng minh **feasibility** cho mọi ràng buộc?
10. Đã chứng minh cost/value so với điểm fractional?
11. Đã liên hệ đúng với OPT_IP nhờ LP optimum hoặc dual bound?
12. Khi relaxation không tối ưu, đã định lượng yếu tố β?
13. Có xem integrality gap của relaxation?
14. Có phân biệt gap và ratio của nghiệm làm tròn?
15. Có chống lỗi threshold gần0.5 do double?
16. Với vertex cover, đã kiểm mọi cạnh `x_u+x_v≥1`?
17. Với vertex cover, threshold≥1/2 và weights không âm?
18. Có kiểm trường hợp tam giác/chu trình bốn đỉnh?
19. Với knapsack, weights dương, values không âm?
20. Có lọc item quá capacity trước fractional relaxation được dùng?
21. Có sắp density bằng phép so an toàn số học?
22. Có tính fractional upper bound và best-single?
23. Có kiểm weight của nghiệm nguyên không vượt capacity?
24. Có chứng minh `max(P,B)≥OPT_IP/2`?
25. Với set cover, đã tính f theo số tập trên mỗi element?
26. Có xác nhận universe phủ được?
27. Có dùng threshold1/f với f≥1 hoặc xử lý universe rỗng?
28. Có kiểm mọi element được ít nhất một tập đã chọn phủ?
29. Có so cost≤f·LP trước khi tuyên bố f-approx?
30. Nếu randomized, có phân biệt kỳ vọng và xác suất thành công?
31. Có sử dụng union bound và Markov đúng giả thiết?
32. Nếu repair, có cộng đầy đủ cost của repair vào phân tích?
33. Có nghĩ đến dependent rounding khi cần equality/cardinality?
34. Có tận dụng integral polytope/TU khi tồn tại?
35. Với LP solver, có kiểm primal feasibility và objective bound?
36. Có tính đến numerical tolerance của solver?
37. Có xử lý overflow của số nguyên/trọng số?
38. Có dùng oracle tối ưu brute force chỉ trên instance nhỏ?
39. Có thử dữ liệu rỗng, nghiệm0 và một số input bất khả thi?
40. Có công bố `PROVEN_RATIO`, `EMPIRICAL_RATIO` và `NO_GUARANTEE` đúng ý nghĩa?

**Kết luận:** Continuous relaxation biến bài toán rời rạc khó thành một bài toán liên tục có cấu trúc dễ phân tích hơn. Nhưng **bài toán được nới lỏng không phải lời giải nguyên**; sự khác biệt nằm ở cách **làm tròn**. Cần giữ đồng thời ba mắt xích: **(1) relaxation hợp lệ và cận đúng**, **(2) nghiệm nguyên sau làm tròn khả thi**, **(3) cost/value bị mất có chặn so với LP optimum hoặc một bound khác**. Vertex cover đạt factor2 nhờ ngưỡng1/2; set cover frequency-f đạt factor f; knapsack một capacity đạt 1/2 nhờ so prefix với best-single. Làm tròn độc lập 0.5 có thể phá packing và cardinality. Một bảo đảm xấp xỉ là **định lý có giả thiết**, không phải nhãn gắn cho một nghiệm phân số bất kỳ.
