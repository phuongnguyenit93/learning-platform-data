# Tách nhóm số lượng trong ba lô giới hạn (Binary Splitting for Bounded Knapsack)

> **Chủ đề:** Computer Science Algorithms → Tối ưu quy hoạch động.  
> **Mục tiêu:** Nắm vững cách chuyển **ba lô giới hạn số lượng** (*bounded knapsack*) thành **ba lô 0/1 trên các nhóm bản sao**, thông qua phân tách số lượng theo lũy thừa hai `1, 2, 4, ...` và **phần dư**. Biết chứng minh không mất phương án, suy ra độ phức tạp, cài DP một chiều với chiều duyệt đúng, truy vết số lượng vật, phân biệt với ba lô 0/1 và không giới hạn, hiểu các biên số học và một kỹ thuật cạnh tranh là tối ưu hàng đợi đơn điệu.

## 1. Ba biến thể ba lô cần phân biệt

Cho sức chứa nguyên `W >= 0`. Mỗi **loại vật** `i` có:

- `w_i`: trọng lượng một bản sao, thường là số nguyên **dương**.
- `v_i`: giá trị một bản sao.
- `k_i`: số bản sao tối đa có thể lấy, là số nguyên **không âm**.

Ta tìm các số nguyên `x_i` sao cho:

`0 <= x_i <= k_i`,  
`Σ_i x_i · w_i <= W`,

và **cực đại**:

`Σ_i x_i · v_i`.

Bài này gọi là **ba lô giới hạn**, *bounded knapsack* hoặc *multiple knapsack with bounded item multiplicities* (ở đây chỉ có **một ba lô**, nhiều **bản sao của từng loại**).

| Biến thể | Số bản sao mỗi loại | Quy tắc chuyển phổ biến |
|---|---|---|
| **0/1 knapsack** | `x_i ∈ {0,1}` | Mỗi vật được chọn tối đa một lần |
| **Unbounded/complete knapsack** | `x_i >= 0`, không có giới hạn riêng | Có thể lấy lại cùng loại nhiều lần nếu còn sức chứa |
| **Bounded knapsack** | `0 <= x_i <= k_i` | Mỗi loại có giới hạn hữu hạn `k_i` |

Với `k_i=1`, loại i trở thành vật 0/1. Nếu `k_i=0`, bỏ qua loại đó. Nếu `k_i` rất lớn, nhưng `w_i>0`, ta cũng không thể lấy quá `floor(W/w_i)` bản sao dù kho có nhiều hơn.

**Điều kiện của bài học:** các chương trình Java dùng `w_i>0`, `v_i>=0`, `k_i>=0`, sức chứa không âm, giá trị/tổng giá trị phù hợp miền `long`. Điều kiện này làm rõ quy hoạch động cực đại với **quyền không chọn gì** và cho phép loại bản sao dư so với sức chứa. Các biến thể trọng lượng bằng 0, giá trị âm và yêu cầu **đúng W** được bàn riêng ở phần sau.

### 1.1. Ví dụ khởi động

Sức chứa `W=10`:

| Loại | Trọng lượng mỗi bản sao | Giá trị mỗi bản sao | Số lượng tối đa |
|---|---:|---:|---:|
| A | 3 | 5 | 4 |
| B | 2 | 4 | 3 |

Một lời giải tối ưu chọn:

- Hai bản sao A: trọng lượng `2×3=6`, giá trị `2×5=10`.
- Hai bản sao B: trọng lượng `2×2=4`, giá trị `2×4=8`.
- Tổng trọng lượng `10`, tổng giá trị **18**.

Nếu **bỏ giới hạn** số lượng của B thì có thể chọn năm bản sao B, trọng lượng 10, giá trị 20. Nhưng kho chỉ có 3 bản sao B, nên phương án giá trị 20 **không hợp lệ** cho bài bounded.

## 2. Quan hệ chuyển đầy đủ trước khi tối ưu

Trước hết hãy viết công thức chuẩn, sau đó mới biến đổi thuật toán.

Đặt `F[i][c]` là tổng giá trị tối đa khi xét **i loại đầu tiên**, sức chứa **không quá c** và mọi số lượng nằm trong giới hạn. Không phải dùng đúng c.

**Cơ sở:** `F[0][c]=0` với mọi `0<=c<=W`, vì tập rỗng luôn khả thi và giá trị là 0.

Với loại i nặng `w`, giá trị `v`, có `k` bản sao, ta có thể chọn `q` bản sao:

`0 <= q <= min(k, floor(c/w))`.

Các loại trước đó có sức chứa còn lại `c-qw`; do đó:

`F[i][c] = max_(0<=q<=min(k,floor(c/w))) { F[i-1][c-qw] + qv }`.

Đây là **quan hệ chuyển đúng theo định nghĩa** của bounded knapsack:

- `q=0` là không chọn loại i.
- Mọi `q>0` trong miền hợp lệ là chọn chính xác q bản sao loại i.
- Tiền nhiệm luôn là `F[i-1]`: các loại đã xét trước, **không tự lấy lại loại hiện tại** vượt giới hạn.

### 2.1. Vì sao cách trực tiếp có thể chậm?

Nếu duyệt mọi c từ 0 tới W, rồi thử mọi q từ 0 tới k, chi phí một loại vật là khoảng `O(W·k)`. Tổng thời gian:

`O(W · Σ_i k_i)`,

trong cách cài trực tiếp/chặn trên đơn giản, với bộ nhớ `O(W)` nếu giữ lớp trước và lớp sau.

Nếu k lớn, ví dụ một loại có 1.000.000 bản sao, vòng q có thể rất dài dù số loại nhỏ. Ta muốn **giảm số quyết định 0/1 cần xét** mà vẫn biểu diễn được mọi q hợp lệ.

### 2.2. Không dùng một lần cập nhật xuôi cho bounded

Một cách cài sai thường gặp là:

```text
for c = w .. W:
    dp[c] = max(dp[c], dp[c-w] + v)
```

Khi `c` tăng, `dp[c-w]` có thể đã chứa **chính loại vật đang xét**, nên phép chuyển cho phép lấy **không giới hạn bản sao**. Công thức này phù hợp *unbounded knapsack*, không phù hợp bounded nếu không có kiểm soát số lần chọn.

Ngược lại, nếu chỉ chạy một lần cập nhật ngược cho cả **loại** vật, ta chỉ cho phép chọn **một** bản sao, chưa tận dụng đủ `k` bản sao. Tách nhóm là cách biến k bản sao thành ít nhóm 0/1, sau đó cập nhật ngược cho **từng nhóm**.

## 3. Ý tưởng quan trọng: gộp bản sao thành các nhóm 0/1

Giả sử một loại vật có **13 bản sao giống hệt nhau**, mỗi bản sao nặng `w` và giá trị `v`.

Ta không tạo 13 vật 0/1 riêng lẻ, mà tạo các **nhóm**:

`[1, 2, 4, 6]`.

Mỗi nhóm là **một pseudo-item 0/1**: chỉ được chọn nhóm đó **một lần**. Nhóm t bản sao có:

- Trọng lượng nhóm `t·w`.
- Giá trị nhóm `t·v`.
- Số bản sao gốc được đại diện: `t`.

Tổng số bản sao trong các nhóm là `1+2+4+6=13`. Tập con các nhóm này có thể biểu diễn **mọi số lượng từ 0 đến 13**.

Ví dụ:

| Muốn lấy | Các nhóm chọn | Tổng số bản sao |
|---:|---|---:|
| 0 | Không nhóm nào | 0 |
| 1 | 1 | 1 |
| 3 | 1+2 | 3 |
| 5 | 1+4 | 5 |
| 6 | 6 | 6 |
| 8 | 2+6 hoặc 2+? (chọn cách hợp lệ) | 8 |
| 9 | 1+2+6 | 9 |
| 10 | 4+6 | 10 |
| 11 | 1+4+6 | 11 |
| 12 | 2+4+6 | 12 |
| 13 | 1+2+4+6 | 13 |

Lấy 8 bằng **2+6** là hợp lệ; nhóm cuối không nhất thiết bằng lũy thừa hai. Một số lượng có thể có **nhiều cách chọn nhóm khác nhau** (ví dụ 6 bằng nhóm 6 hoặc nhóm 2+4), nhưng đó không phải vấn đề khi bài chỉ **tối ưu tổng giá trị**: các cách đó có cùng trọng lượng và giá trị của loại vật.

### 3.1. Cách tạo nhóm tổng quát

```text
remaining = k
power = 1

while remaining > 0:
    take = min(power, remaining)
    tạo nhóm gồm take bản sao
    remaining -= take
    power *= 2
```

Ví dụ:

| k | Nhóm nhận được |
|---:|---|
| 0 | `[]` |
| 1 | `[1]` |
| 2 | `[1,1]` |
| 3 | `[1,2]` |
| 4 | `[1,2,1]` |
| 5 | `[1,2,2]` |
| 6 | `[1,2,3]` |
| 7 | `[1,2,4]` |
| 8 | `[1,2,4,1]` |
| 13 | `[1,2,4,6]` |
| 15 | `[1,2,4,8]` |

**Không mặc định nhóm cuối vẫn bằng `power`**. Nếu `remaining<power`, phải lấy đúng phần dư; nếu tạo quá số lượng có sẵn, các pseudo-item sẽ cho phép nghiệm vượt kho.

### 3.2. Vì sao đôi khi có hai nhóm cùng kích thước?

Với `k=4`, thuật toán tạo `[1,2,1]`. Hai nhóm cỡ 1 là **hai pseudo-item 0/1 khác nhau**, nên vẫn có thể chọn cả hai nhóm. Tổng là 4 và mọi số lượng `0..4` đều biểu diễn được.

Không cần ép các nhóm thành một biểu diễn số nhị phân duy nhất; ta cần **đầy đủ mọi số lượng**, không phải mã hóa số k bằng đúng các bit 1 của k.

### 3.3. Tên gọi

Kỹ thuật này thường gọi:

- **Binary splitting** hoặc **binary decomposition of multiplicities**.
- **Binary grouping**.
- **Tách nhóm theo lũy thừa 2** trong bounded/multiple knapsack.

Ý tưởng “nhị phân” nằm ở **kích thước nhóm tăng gấp đôi**, không phải trọng lượng hay giá trị của vật phải là số nhị phân.

## 4. Chứng minh mọi số lượng từ 0 đến k đều biểu diễn được

Đây là điểm chính để phép tối ưu **đúng về mặt toán học**.

### 4.1. Bổ đề về đoạn tổng liên tiếp

Giả sử các nhóm đã tạo trước đó cho phép biểu diễn **mọi số nguyên từ 0 tới S** (tổng kích thước các nhóm là S). Thêm một nhóm mới kích thước t, với:

`1 <= t <= S+1`.

Những tổng **không chọn nhóm mới** phủ `[0,S]`.

Những tổng **có chọn nhóm mới** phủ `[t,t+S]`.

Vì `t<=S+1`, hai đoạn không có khoảng trống nguyên giữa chúng. Hợp của chúng phủ liên tục:

`[0,S+t]`.

Bởi vậy, sau khi thêm nhóm t, mọi số lượng từ 0 đến S+t vẫn biểu diễn được bằng các nhóm 0/1.

### 4.2. Áp dụng cho dãy `1,2,4,...,phần dư`

Ban đầu chưa có nhóm, `S=0`, nên nhóm đầu `t=1=S+1` là hợp lệ.

Sau các nhóm đầy đủ `1,2,4,...,2^(h-1)`, tổng đã dùng là:

`S=1+2+...+2^(h-1)=2^h-1`.

Nhóm kế tiếp lấy `t=min(2^h, remaining)` nên:

`t<=2^h=S+1`.

Do bổ đề, sau mỗi nhóm ta vẫn phủ liên tục mọi số lượng `0..S`. Khi thuật toán kết thúc, tổng kích thước nhóm đúng bằng `k`, suy ra các nhóm biểu diễn được **mọi q nguyên từ 0 tới k**.

Đây là chứng minh tổng quát, không chỉ kiểm thử cho `k=13`.

### 4.3. Ánh xạ hai chiều bảo toàn nghiệm

Với mỗi loại vật i:

- Mỗi cách chọn các nhóm pseudo-item tạo ra tổng số bản sao `x_i` với `0<=x_i<=k_i` vì mỗi nhóm chỉ chọn một lần và tổng kích thước là k_i.
- Ngược lại, với mỗi `x_i` hợp lệ, bổ đề bảo đảm có một tập nhóm của loại i có tổng kích thước đúng `x_i`.

Một nhóm t đại diện chính xác `t·w_i` trọng lượng và `t·v_i` giá trị. Vì thế ánh xạ bảo toàn **mọi tổng trọng lượng, tổng giá trị** và tính khả thi trong sức chứa W.

Các loại vật độc lập về phép tách nhóm. Do vậy tập giá trị mục tiêu có thể đạt của bài pseudo-item 0/1 **bằng** tập giá trị có thể đạt của bài bounded ban đầu.

**Kết luận:** giải ba lô 0/1 trên các nhóm trả **đúng giá trị tối ưu** của bounded knapsack, không phải một heuristic và không gây mất phương án.

### 4.4. Vì sao không gây ra bản sao ảo?

Tổng trọng lượng của toàn bộ các nhóm một loại bằng `k_i·w_i`, nhưng điều quan trọng hơn là **mỗi nhóm chỉ được lấy một lần**. Nếu chạy cập nhật dung lượng **tăng dần** với một nhóm 0/1, chính nhóm đó có thể được lấy lặp nhiều lần, phá ràng buộc số lượng gốc. Tách nhóm đúng **chưa đủ** nếu chiều duyệt DP sai.

## 5. Số nhóm và độ phức tạp cải thiện

Với `k>=1`, số nhóm của thuật toán ở trên không vượt:

`floor(log₂ k)+1`.

Dễ thấy mỗi nhóm đầu sử dụng ít nhất các lũy thừa 1,2,4,..., còn nhóm cuối lấy phần dư. Số vòng vì vậy chỉ là **`O(log(k+1))`**.

Ví dụ:

| Giới hạn bản sao k | Số pseudo-item tối đa (theo cách tách nêu trên) |
|---:|---:|
| 1 | 1 |
| 2 | 2 |
| 7 | 3 |
| 8 | 4 |
| 13 | 4 |
| 1.000 | 10 |
| 1.000.000 | 20 |

Nếu tổng số nhóm sau tách là `M`, bài 0/1 trên M nhóm bằng một mảng `dp[0..W]` có:

- **Thời gian:** `O(M·(W+1))`.
- **Bộ nhớ bảng DP:** `O(W+1)`.
- **Bộ nhớ giữ nhóm:** `O(M)` nếu tạo danh sách nhóm; có thể xử lý trực tiếp từng nhóm để không cần danh sách đó.

Vì `M=O(Σ_i log(k_i+1))`, ta có chặn:

`O((W+1) · Σ_i log(k_i+1))` thời gian,

chưa tính những chi phí số học khác mô hình máy.

So sánh với thử từng số lượng:

| Phương pháp | Thời gian chặn trên | Bộ nhớ DP |
|---|---|---|
| Thử `q=0..k_i` tại mỗi c | `O((W+1)·Σ k_i)` | `O(W+1)` khi giữ hai lớp |
| Mở mỗi bản sao thành vật 0/1 | `O((W+1)·Σ k_i)` | `O(W+1)` |
| **Tách nhị phân + 0/1** | **`O((W+1)·Σ log(k_i+1))`** | **`O(W+1)`** |
| Hàng đợi đơn điệu theo lớp dư | `O(n(W+1))` với điều kiện phù hợp | `O(W+1)` |

Đây là chi phí **giả đa thức** theo W: nếu W rất lớn nhưng được biểu diễn bằng ít bit, `O(W)` chưa phải đa thức theo độ dài mã hóa nhị phân của input.

## 6. Giảm số nhóm bằng sức chứa: `k' = min(k, floor(W/w))`

Nếu `w_i>0`, không có lời giải khả thi nào dùng hơn `floor(W/w_i)` bản sao của loại i, vì chỉ riêng loại ấy đã vượt sức chứa.

Do đó trước khi tách nhóm, có thể thay:

`k_i' = min(k_i, floor(W/w_i))`.

Đây là một tối ưu **chính xác**, không phải xấp xỉ. Ví dụ có `k=1.000.000` bản sao, `w=3`, `W=10`, thì tối đa chỉ dùng `3` bản sao:

```text
k' = min(1.000.000, floor(10/3)) = 3
Nhóm cần tạo: [1,2].
```

Không phải tạo khoảng 20 nhóm trên k gốc nếu tất cả bản sao quá sức chứa đều không bao giờ được dùng.

**Chú ý biên:**

- `W=0`, `w>0` ⇒ `k'=0`, không tạo nhóm.
- `w>W` ⇒ `k'=0`, loại vật không thể chọn dù kho có nhiều bản.
- `k=0` ⇒ không tạo nhóm.
- `w=0` ⇒ **không được chia W cho w**; phải xử lý riêng.

Nếu mọi trọng lượng dương, tổng số nhóm hữu ích có thể chặn bởi:

`M = O(Σ_i log(1 + min(k_i, floor(W/w_i))))`.

Công thức này phản ánh lợi ích giảm số lượng lớn ngay từ đầu.

## 7. Từ nhóm 0/1 đến công thức DP một chiều

Sau khi tách thành M pseudo-item, mỗi nhóm `g` có trọng lượng `wg`, giá trị `vg`, được phép chọn **tối đa một lần**.

Đặt:

`dp[c] = giá trị lớn nhất khi chỉ dùng những nhóm đã xử lý và tổng trọng lượng không vượt c`.

**Cơ sở:** `dp[c]=0` cho mọi `c∈[0,W]`, vì tập rỗng khả thi.

**Chuyển cho mỗi nhóm:**

```text
for c = W downTo wg:
    dp[c] = max(dp[c], dp[c-wg] + vg)
```

**Phải duyệt `c` GIẢM DẦN**. Khi tính `dp[c]`, ô `dp[c-wg]` ở chỉ số nhỏ hơn chưa được cập nhật bằng **nhóm đang xét**. Điều đó giữ tính 0/1 của nhóm.

### 7.1. Tính đúng nhờ hai lớp lập luận

1. **Tính đúng phép tách:** các nhóm biểu diễn đầy đủ và chỉ đầy đủ số lượng `0..k_i`, đồng thời bảo toàn trọng lượng/giá trị.
2. **Tính đúng DP 0/1:** với mỗi nhóm, mọi nghiệm tối ưu hoặc **bỏ nhóm** hoặc **lấy nhóm một lần**. `max` xét đủ hai nhánh; duyệt giảm giúp tiền nhiệm nhánh lấy chỉ dùng các nhóm trước đó.

Kết hợp lại, DP một chiều trên các nhóm trả tối ưu của **bài bounded gốc**.

### 7.2. Phản ví dụ nếu duyệt tăng

Một loại có `w=2`, `v=5`, `k=1`; sức chứa `W=4`.

Sau tách có **một nhóm** `(weight=2, value=5)`.

Nếu duyệt tăng:

```text
c=2: dp[2] = 5
c=4: dp[4] = dp[2] + 5 = 10  // Dùng lại cùng một nhóm!
```

Kết quả 10 là **sai** vì chỉ có một bản sao. Duyệt giảm sẽ tính `dp[4]` trước `dp[2]`, nên `dp[4]=5`, đúng ràng buộc.

## 8. Java 17: tạo nhóm và kiểm tra đủ các số lượng

Chương trình đầu tiên chỉ kiểm tra **phép tách số lượng**, chưa làm DP trọng lượng. Chạy nó trước giúp hiểu rằng “còn dư” không có nghĩa “mất khả năng biểu diễn số bản sao”.

Lưu thành **BinaryGroupingCoverageDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;

public class BinaryGroupingCoverageDemo {
    static List<Integer> split(int count) {
        if (count < 0) {
            throw new IllegalArgumentException("Negative count");
        }

        List<Integer> groups = new ArrayList<>();
        int remaining = count;
        long power = 1L;

        while (remaining > 0) {
            int take = (int) Math.min(power, (long) remaining);
            groups.add(take);
            remaining -= take;
            power *= 2L;
        }
        return groups;
    }

    static boolean coversEveryCount(List<Integer> groups, int count) {
        boolean[] reachable = new boolean[count + 1];
        reachable[0] = true;

        // Mỗi group là 0/1, nên chạy tổng GIẢM DẦN.
        for (int g : groups) {
            for (int x = count; x >= g; x--) {
                if (reachable[x - g]) {
                    reachable[x] = true;
                }
            }
        }

        for (boolean seen : reachable) {
            if (!seen) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        List<Integer> groups13 = split(13);
        System.out.println("k=13 groups: " + groups13);
        System.out.println("Covers 0..13: "
                + coversEveryCount(groups13, 13));
        System.out.println("k=4 groups: " + split(4));
        System.out.println("k=0 groups: " + split(0));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 BinaryGroupingCoverageDemo.java
java BinaryGroupingCoverageDemo
```

Stdout:

```text
k=13 groups: [1, 2, 4, 6]
Covers 0..13: true
k=4 groups: [1, 2, 1]
k=0 groups: []
```

`coversEveryCount` chạy một DP boolean trên tổng số bản sao, dùng chiều giảm để không lấy một nhóm hai lần. Đây là **công cụ kiểm chứng ví dụ**; khi k lớn, cấp mảng `boolean[k+1]` cũng có thể tốn nhiều RAM, nên không cần chạy nó trong giải pháp bounded knapsack thực tế. Tính đúng tổng quát đã được chứng minh ở phần 4.

## 9. Java 17: tối ưu bounded knapsack bằng tách nhóm nhị phân

Ví dụ thứ hai là lời giải chính: tách nhóm **ngay khi xử lý**, cập nhật `dp` một chiều theo chiều giảm, và đối chiếu với cách thử số lượng `q` trực tiếp.

Lưu thành **BoundedBinarySplitKnapsackDemo.java**:

```java
import java.util.Objects;

public class BoundedBinarySplitKnapsackDemo {
    record Type(int weight, long value, int count) {}

    static void validate(Type[] types, int capacity) {
        Objects.requireNonNull(types, "types");
        if (capacity < 0 || capacity == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid capacity");
        }
        for (Type type : types) {
            Objects.requireNonNull(type, "type");
            if (type.weight() <= 0 || type.value() < 0
                    || type.count() < 0) {
                throw new IllegalArgumentException("Invalid item type");
            }
        }
    }

    // O((W+1) * sum log(k_i'+1)); thêm O(W) bảng DP.
    static long binarySplitBest(Type[] types, int capacity) {
        validate(types, capacity);
        long[] dp = new long[capacity + 1];

        for (Type type : types) {
            int usable = Math.min(type.count(),
                    capacity / type.weight());
            int remaining = usable;
            long power = 1L;

            while (remaining > 0) {
                int copies = (int) Math.min(power, (long) remaining);
                int groupWeight = (int) ((long) type.weight() * copies);
                long groupValue = Math.multiplyExact(
                        type.value(), (long) copies);

                // Mỗi pseudo-item là 0/1.
                for (int c = capacity; c >= groupWeight; c--) {
                    long take = Math.addExact(
                            dp[c - groupWeight], groupValue);
                    dp[c] = Math.max(dp[c], take);
                }

                remaining -= copies;
                power *= 2L;
            }
        }
        return dp[capacity];
    }

    // Oracle chậm hơn: xét trực tiếp mọi số bản sao q của từng loại.
    static long naiveBounded(Type[] types, int capacity) {
        validate(types, capacity);
        long[] previous = new long[capacity + 1];

        for (Type type : types) {
            long[] next = previous.clone();
            int usable = Math.min(type.count(),
                    capacity / type.weight());

            for (int c = 0; c <= capacity; c++) {
                int limit = Math.min(usable, c / type.weight());
                for (int q = 1; q <= limit; q++) {
                    long value = Math.addExact(
                            previous[c - q * type.weight()],
                            Math.multiplyExact(type.value(), (long) q));
                    next[c] = Math.max(next[c], value);
                }
            }
            previous = next;
        }
        return previous[capacity];
    }

    public static void main(String[] args) {
        Type[] types = {
            new Type(3, 5, 4),  // A
            new Type(2, 4, 3)   // B
        };

        System.out.println("Binary split best: "
                + binarySplitBest(types, 10));
        System.out.println("Naive bounded best: "
                + naiveBounded(types, 10));
        System.out.println("Capacity zero: "
                + binarySplitBest(types, 0));
        System.out.println("No item types: "
                + binarySplitBest(new Type[0], 10));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BoundedBinarySplitKnapsackDemo.java
java BoundedBinarySplitKnapsackDemo
```

Stdout:

```text
Binary split best: 18
Naive bounded best: 18
Capacity zero: 0
No item types: 0
```

### 9.1. Diễn giải kết quả

- Tách nhóm và cách thử trực tiếp đều trả **18**, đúng với lựa chọn hai A và hai B.
- `capacity=0` với trọng lượng các loại dương ⇒ không lấy vật, giá trị 0.
- Danh sách loại vật rỗng ⇒ chỉ có tập rỗng, giá trị 0.

### 9.2. Vì sao không tràn `int` khi tính trọng lượng nhóm ở ví dụ?

Ta trước hết giới hạn:

`usable <= floor(capacity / weight)`.

Mỗi nhóm có `copies<=usable`, vì vậy:

`copies * weight <= capacity`.

Phép nhân thực hiện với **`long` trước**, sau đó mới ép `int`, và `capacity` được kiểm tra còn nằm trong miền nguyên hợp lệ cho mảng. Với kiểu `int` ở input, giới hạn này làm trọng lượng nhóm vừa miền chỉ số.

Giá trị nhóm dùng `Math.multiplyExact(long,long)` và phép cộng DP dùng `Math.addExact(long,long)`. Nếu tràn, chương trình phát hiện bằng ngoại lệ thay vì âm thầm đổi dấu. Không có nghĩa mọi input có tổng giá trị cực lớn đều giải được bằng `long`.

### 9.3. Chi phí của hai cách

Gọi `k_i' = min(k_i, floor(W/w_i))`:

- **Binary splitting:** số pseudo-item `M = O(Σ log(k_i'+1))`. Thời gian `O((W+1)M)`, bộ nhớ `O(W+1)` vì không giữ danh sách nhóm.
- **Naive:** thử tối đa `k_i'` lượng cho mỗi sức chứa. Thời gian `O((W+1)Σ k_i')` theo chặn đơn giản, bộ nhớ `O(W+1)` cho hai lớp `previous/next`.

Với ví dụ nhỏ, hai cách có thể tốn gần như nhau; lợi ích của binary splitting rõ hơn khi một số `k_i'` lớn. Nếu `W` quá lớn, cả hai vẫn cần bảng theo W, cần xem xét phương pháp khác hoặc giới hạn dữ liệu.

### 9.4. Có thể dùng `long` cho số lượng k không?

Có thể, nhưng nếu số bản sao cần hỗ trợ vượt `int`, toàn bộ code xác thực, biến `remaining`, `copies`, việc ước lượng trọng lượng/giá trị nhóm và chính sách đầu vào đều phải được thiết kế lại đồng bộ. Không đơn giản thay `int count` bằng `long` rồi giữ các phép nhân/cast cũ.

## 10. Khi cần biết mỗi loại đã chọn bao nhiêu bản: truy vết

Hàm trả **giá trị** không tự trả được vector số lượng `x_i`. Do phiên bản 1D ghi đè trạng thái theo pseudo-item, nếu muốn truy vết trực tiếp một cách rõ ràng, ta có thể giữ **một hàng DP cho mỗi nhóm**:

`F[g][c]` = giá trị tối ưu khi xét g pseudo-item đầu tiên, sức chứa không vượt c.

Cơ sở `F[0][c]=0`.

Với nhóm g có trọng lượng `wg`, giá trị `vg`:

`F[g][c] = max(F[g-1][c], F[g-1][c-wg]+vg)` nếu `c>=wg`, ngược lại là `F[g-1][c]`.

Truy vết từ `(g=M,c=W)`:

- Nếu `F[g][c] == F[g-1][c]`, có một nghiệm tối ưu **không chọn nhóm g**; bỏ qua nhóm g (tie-break chọn bỏ).
- Nếu `F[g][c] > F[g-1][c]`, phải chọn nhóm g để có giá trị đã đạt; cộng `copies` của nhóm vào loại gốc và trừ `wg` khỏi c.

Trong bản dùng `value>=0`, quy tắc này cho một nghiệm hợp lệ; nếu nhiều nghiệm cùng tối ưu, chính sách hòa cho kết quả xác định nhưng **không nhất thiết ít vật nhất**.

### 10.1. Java 17: tái dựng số lượng từng loại

Lưu thành **BoundedBinarySplitReconstructionDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class BoundedBinarySplitReconstructionDemo {
    record Type(String id, int weight, long value, int count) {}
    record Group(int typeIndex, int copies, int weight, long value) {}
    record Result(long value, int[] counts, int usedWeight,
                  int pseudoItems) {}

    static Result solve(Type[] types, int capacity) {
        Objects.requireNonNull(types, "types");
        if (capacity < 0 || capacity == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid capacity");
        }

        List<Group> groups = new ArrayList<>();

        for (int typeIndex = 0; typeIndex < types.length; typeIndex++) {
            Type type = Objects.requireNonNull(types[typeIndex], "type");
            Objects.requireNonNull(type.id(), "id");
            if (type.weight() <= 0 || type.value() < 0
                    || type.count() < 0) {
                throw new IllegalArgumentException("Invalid item type");
            }

            int remaining = Math.min(type.count(),
                    capacity / type.weight());
            long power = 1L;

            while (remaining > 0) {
                int copies = (int) Math.min(power, (long) remaining);
                int weight = (int) ((long) copies * type.weight());
                long value = Math.multiplyExact(
                        type.value(), (long) copies);

                groups.add(new Group(typeIndex, copies, weight, value));
                remaining -= copies;
                power *= 2L;
            }
        }

        int m = groups.size();
        long[][] dp = new long[m + 1][capacity + 1];

        for (int g = 1; g <= m; g++) {
            Group group = groups.get(g - 1);
            for (int c = 0; c <= capacity; c++) {
                long best = dp[g - 1][c];
                if (c >= group.weight()) {
                    long take = Math.addExact(
                            dp[g - 1][c - group.weight()],
                            group.value());
                    best = Math.max(best, take);
                }
                dp[g][c] = best;
            }
        }

        int[] counts = new int[types.length];
        int c = capacity;
        int usedWeight = 0;

        for (int g = m; g >= 1; g--) {
            Group group = groups.get(g - 1);
            if (c >= group.weight()
                    && dp[g][c] > dp[g - 1][c]) {
                counts[group.typeIndex()] += group.copies();
                usedWeight += group.weight();
                c -= group.weight();
            }
        }

        return new Result(dp[m][capacity], counts,
                usedWeight, m);
    }

    public static void main(String[] args) {
        Type[] types = {
            new Type("A", 3, 5, 4),
            new Type("B", 2, 4, 3)
        };

        Result result = solve(types, 10);
        System.out.println("Best value: " + result.value());
        System.out.println("Counts [A, B]: "
                + Arrays.toString(result.counts()));
        System.out.println("Used weight: " + result.usedWeight());
        System.out.println("Pseudo-items: " + result.pseudoItems());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BoundedBinarySplitReconstructionDemo.java
java BoundedBinarySplitReconstructionDemo
```

Stdout:

```text
Best value: 18
Counts [A, B]: [2, 2]
Used weight: 10
Pseudo-items: 4
```

**Vì sao chỉ 4 pseudo-item?** Sau khi cắt theo sức chứa:

- Với A, `k'_A=min(4,floor(10/3))=3` ⇒ nhóm `[1,2]`.
- Với B, `k'_B=min(3,floor(10/2))=3` ⇒ nhóm `[1,2]`.

Tổng cộng `2+2=4` nhóm. Truy vết chọn nhóm 2 bản sao của A và nhóm 2 bản sao của B; trọng lượng `6+4=10`, giá trị `10+8=18`.

**Độ phức tạp:** thời gian `O((W+1)M)` như phiên bản chỉ giá trị, nhưng bảng truy vết có **`O((W+1)(M+1))` bộ nhớ** cùng `O(M)` nhóm và `O(n)` vector kết quả. Không nên tuyên bố bản truy vết cũng chỉ dùng `O(W)` bộ nhớ.

**Giới hạn:** `counts[]` lưu số lượng theo thứ tự `types[]`. Nếu đề yêu cầu ID và số lượng in theo thứ tự nào đó, hãy dựng output từ `types[i].id()` và `counts[i]`; code chỉ in mảng đếm với nhãn `[A,B]` cho dữ liệu minh họa.

## 11. Dùng đầy sức chứa hay không vượt: hai bài toán khác nhau

Ở các ví dụ trước, `dp[c]` nghĩa là **tổng trọng lượng không vượt c**, nên mọi `dp[c]` khởi tạo bằng 0 là đúng (chọn rỗng).

Nếu đề yêu cầu **đúng bằng W**, đó là bài **exact-fill bounded knapsack**. Khi chưa xét nhóm nào, chỉ trọng lượng 0 là đạt được:

```text
exact[0] = 0
exact[c>0] = -INF  (không thể đạt)
```

Chuyển với một pseudo-item 0/1 có `(wg,vg)`:

```text
for c = W downTo wg:
    if exact[c-wg] khả thi:
        exact[c] = max(exact[c], exact[c-wg] + vg)
```

Không được cộng `vg` vào trạng thái `-INF`. Nếu `exact[W]` vẫn bất khả thi, bài toán **không có nghiệm**, không phải giá trị 0.

### 11.1. Ví dụ phân biệt

Có tối đa hai bản sao A `(w=3,v=5)` và một bản sao B `(w=4,v=6)`:

- Với `W=5`, **không vượt 5**: chọn B nặng 4, giá trị 6. Nhưng **đúng 5** không thể tạo ⇒ *impossible*.
- Với `W=6`, chọn hai A, đúng 6, giá trị 10.
- Với `W=7`, chọn A+B, đúng 7, giá trị 11.
- Với `W=0`, tập rỗng dùng chính xác 0, giá trị 0.

### 11.2. Java 17: exact-fill bằng tách nhóm

Lưu thành **BoundedExactFillDemo.java**:

```java
import java.util.Arrays;
import java.util.Objects;

public class BoundedExactFillDemo {
    record Type(int weight, long value, int count) {}

    // null = không có tổ hợp dùng chính xác capacity.
    static Long bestExact(Type[] types, int capacity) {
        Objects.requireNonNull(types, "types");
        if (capacity < 0 || capacity == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid capacity");
        }

        long unreachable = Long.MIN_VALUE;
        long[] dp = new long[capacity + 1];
        Arrays.fill(dp, unreachable);
        dp[0] = 0L;

        for (Type type : types) {
            Objects.requireNonNull(type, "type");
            if (type.weight() <= 0 || type.value() < 0
                    || type.count() < 0) {
                throw new IllegalArgumentException("Invalid item type");
            }

            int remaining = Math.min(type.count(),
                    capacity / type.weight());
            long power = 1L;

            while (remaining > 0) {
                int copies = (int) Math.min(power, (long) remaining);
                int wg = (int) ((long) copies * type.weight());
                long vg = Math.multiplyExact(
                        type.value(), (long) copies);

                for (int c = capacity; c >= wg; c--) {
                    if (dp[c - wg] != unreachable) {
                        long take = Math.addExact(dp[c - wg], vg);
                        dp[c] = Math.max(dp[c], take);
                    }
                }

                remaining -= copies;
                power *= 2L;
            }
        }
        return dp[capacity] == unreachable ? null : dp[capacity];
    }

    static String show(Long value) {
        return value == null ? "impossible" : value.toString();
    }

    public static void main(String[] args) {
        Type[] types = {
            new Type(3, 5, 2),
            new Type(4, 6, 1)
        };

        System.out.println("Exact 5: " + show(bestExact(types, 5)));
        System.out.println("Exact 6: " + show(bestExact(types, 6)));
        System.out.println("Exact 7: " + show(bestExact(types, 7)));
        System.out.println("Exact 0: " + show(bestExact(types, 0)));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BoundedExactFillDemo.java
java BoundedExactFillDemo
```

Stdout:

```text
Exact 5: impossible
Exact 6: 10
Exact 7: 11
Exact 0: 0
```

**Tại sao dùng `Long.MIN_VALUE` làm sentinel được ở đây?** Mẫu chỉ chấp nhận **giá trị vật không âm** và tổng giá trị tính toán hợp lệ trong miền `long`, nên giá trị tối ưu hợp lệ không thể là `Long.MIN_VALUE`. Nếu cho phép giá trị âm hay giá trị hợp lệ có thể trùng sentinel, cần thêm `boolean[] reachable` hoặc một kiểu `OptionalLong`/cấu trúc rõ ràng.

**Không đánh đồng exact-fill với “ít nhất W”**. Một bài yêu cầu đạt ngưỡng thấp nhất W và cho phép vượt mức là một mô hình khác, có thể cần trạng thái đạt ngưỡng và phép cắt ngưỡng nếu chứng minh hợp lệ.

## 12. Trường hợp trọng lượng 0, giá trị âm và số lượng rất lớn

Các chương trình ở trên dùng `weight>0` để phép chia `W/weight` và ràng buộc số lượng hữu ích hợp lệ. Phần này giải thích cách mở rộng nếu đề có hợp đồng khác.

### 12.1. Trọng lượng bằng 0, số lượng hữu hạn

Một loại có `w=0`, `v>0`, `k>=0`:

- Lấy cả k bản sao **không tốn sức chứa** và làm tổng giá trị tăng `k·v`.
- Trong bài tối đa hóa với quyền chọn rỗng và `v>=0`, có thể cộng riêng `k·v` vào đáp án, sau khi kiểm tra tràn, hoặc tạo nhóm 0/1 có trọng lượng 0.
- **Không** dùng `floor(W/w)` vì chia cho 0.

Nếu `w=0`, `v=0`, chọn hoặc bỏ đều không đổi mục tiêu; thường bỏ qua khi chỉ cần giá trị, nhưng nếu đề yêu cầu **đếm nghiệm** thì số cách có thể thay đổi đáng kể.

### 12.2. Không giới hạn số bản sao và trọng lượng 0

Nếu loại được lấy **vô hạn lần**, `w=0` và `v>0`, mục tiêu cực đại **không có giá trị hữu hạn**: cứ lấy thêm bản sao mà không dùng thêm sức chứa. Bounded knapsack với `k` hữu hạn không gặp vô hạn này.

### 12.3. Giá trị âm

Với mục tiêu **cực đại**, trọng lượng không âm và **cho phép bỏ tất cả**, một loại có giá trị âm không giúp cải thiện đáp án. Có thể bỏ loại đó trong mô hình “không vượt sức chứa”.

Nhưng nếu đề buộc **chọn đúng số vật**, **dùng đủ trọng lượng** hoặc thỏa ràng buộc số lượng tối thiểu, một loại có giá trị âm có thể cần thiết để đạt tính khả thi. Khi đó không được tự loại giá trị âm; định nghĩa trạng thái và cơ sở phải được sửa phù hợp.

### 12.4. Count lớn nhưng W nhỏ

Với `w>0`, dùng `min(k,W/w)` trước khi tách. Một loại có 10^9 bản sao nhưng `w=100`, `W=500` chỉ cần xét tối đa 5 bản sao; tách thành `[1,2,2]`.

### 12.5. Tràn số và bộ nhớ Java

- `weight * copies` cần thực hiện qua `long` trước khi ép `int`; chỉ ép khi đã chứng minh không vượt sức chứa.
- `value * copies` và `dp[c-wg] + groupValue` có thể tràn `long`; ví dụ dùng `Math.multiplyExact` và `Math.addExact`.
- `capacity+1` với `capacity=Integer.MAX_VALUE` tràn `int`; ví dụ từ chối giá trị này nhưng vẫn cần giới hạn thực tế bộ nhớ cho W nhỏ hơn.
- Không tự tạo `k` bản sao thành mảng nếu k khổng lồ.
- `int[] dp` có thể tràn ở tổng giá trị, dù từng `value` nhỏ; `long` thường phù hợp hơn nhưng vẫn có giới hạn.

## 13. Tối ưu khác: hàng đợi đơn điệu theo lớp dư

Binary splitting rất dễ nhớ và hiệu quả, nhưng không phải cách tối ưu duy nhất cho bounded knapsack một tài nguyên. Một kỹ thuật khác đạt **`O(nW)`** với `w_i>0` là **monotone queue optimization** theo các lớp dư modulo trọng lượng.

Bắt đầu từ truy hồi theo loại vật:

`next[c] = max_(0<=q<=k, q·w<=c) { old[c-qw] + qv }`.

Với trọng lượng `w>0`, tách các sức chứa c theo cùng phần dư r:

`c = r + t·w`, với `0 <= r < w`.

Nếu đặt `u=t-q` thì:

`old[r+u·w] + (t-u)v = t·v + (old[r+u·w] - u·v)`.

Điều kiện `0<=q<=k` tương đương:

`max(0,t-k) <= u <= t`.

Vì thế:

`next[r+t·w] = t·v + max_{max(0,t-k)<=u<=t} (old[r+u·w] - u·v)`.

Đây là **cực đại trên một cửa sổ trượt** theo u. Có thể dùng deque đơn điệu để giữ các u ứng viên có giá trị điều chỉnh tốt nhất. Mỗi chỉ số vào/ra deque tối đa một lần, nên tổng cập nhật qua mọi lớp dư là `O(W+1)` cho **mỗi loại**, không phụ thuộc log k.

### 13.1. Bất biến của deque

Với r cố định, duyệt `t=0,1,...`:

1. Tính `score(t) = old[r+t·w] − t·v`.
2. Xóa từ cuối deque những chỉ số có `score` không lớn hơn score mới (vì chỉ số mới hơn tồn tại lâu hơn trong các cửa sổ tương lai).
3. Đưa t vào cuối.
4. Xóa từ đầu các chỉ số `u < t−k`, vì muốn dùng nhiều hơn k bản sao.
5. Chỉ số ở đầu deque là u có score lớn nhất trong cửa sổ hợp lệ; tính `next[r+t·w]` từ nó.

**Cực kỳ quan trọng:** một lượt xử lý loại vật phải đọc từ **mảng `old` cố định**, ghi sang **mảng `next` mới**. Nếu ngay trong vòng deque đọc lại các ô đã cập nhật của chính loại hiện tại, ta đã thay đổi công thức theo lớp, có thể dùng quá k bản sao.

### 13.2. Java 17: phiên bản monotone queue để đối chiếu

Lưu thành **BoundedMonotoneQueueDemo.java**:

```java
import java.util.ArrayDeque;
import java.util.Objects;

public class BoundedMonotoneQueueDemo {
    record Type(int weight, long value, int count) {}

    static long adjusted(long[] old, int residue, int weight,
                         int index, long value) {
        int capacity = (int) ((long) residue + (long) index * weight);
        return Math.subtractExact(old[capacity],
                Math.multiplyExact((long) index, value));
    }

    static long solve(Type[] types, int capacity) {
        Objects.requireNonNull(types, "types");
        if (capacity < 0 || capacity == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid capacity");
        }

        long[] old = new long[capacity + 1];

        for (Type type : types) {
            Objects.requireNonNull(type, "type");
            if (type.weight() <= 0 || type.value() < 0
                    || type.count() < 0) {
                throw new IllegalArgumentException("Invalid item type");
            }

            int w = type.weight();
            long value = type.value();
            int k = Math.min(type.count(), capacity / w);
            long[] next = new long[capacity + 1];

            for (int r = 0; r < Math.min(w, capacity + 1); r++) {
                ArrayDeque<Integer> deque = new ArrayDeque<>();

                int t = 0;
                for (long cap = r; cap <= capacity; cap += w, t++) {
                    int c = (int) cap;
                    long score = Math.subtractExact(old[c],
                            Math.multiplyExact((long) t, value));

                    while (!deque.isEmpty()
                            && adjusted(old, r, w,
                                    deque.peekLast(), value) <= score) {
                        deque.removeLast();
                    }
                    deque.addLast(t);

                    while (!deque.isEmpty()
                            && deque.peekFirst() < t - k) {
                        deque.removeFirst();
                    }

                    int u = deque.peekFirst();
                    next[c] = Math.addExact(
                            old[(int) ((long) r + (long) u * w)],
                            Math.multiplyExact((long) (t - u), value));
                }
            }

            old = next;
        }
        return old[capacity];
    }

    public static void main(String[] args) {
        Type[] types = {
            new Type(3, 5, 4),
            new Type(2, 4, 3)
        };

        System.out.println("Monotone queue best: "
                + solve(types, 10));
        System.out.println("Many copies, W=7: "
                + solve(new Type[]{new Type(2, 3, 20)}, 7));
        System.out.println("Capacity zero: "
                + solve(types, 0));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BoundedMonotoneQueueDemo.java
java BoundedMonotoneQueueDemo
```

Stdout:

```text
Monotone queue best: 18
Many copies, W=7: 9
Capacity zero: 0
```

**Giải thích:** đầu tiên, nghiệm 18 trùng binary splitting. Trong trường hợp một loại có 20 bản sao, trọng lượng 2, giá trị 3, sức chứa 7, ta chỉ lấy được `floor(7/2)=3` bản sao, tổng giá trị `3×3=9`.

**Độ phức tạp:** mỗi sức chứa thuộc **đúng một lớp dư**, mỗi chỉ số t được deque thêm và xóa một số hữu hạn lần; do đó `O(n(W+1))` thời gian và `O(W+1)` bộ nhớ cho hai mảng `old/next` cùng deque. Nếu mỗi phép `Math.multiplyExact` được coi là hằng số trong mô hình số nguyên máy, chặn này hợp lệ. Kỹ thuật đòi hỏi **trọng lượng dương** và chính sách xử lý tràn giống ví dụ.

Monotone queue thường có hệ số cài đặt/khó kiểm thử lớn hơn binary splitting. Khi chưa gặp giới hạn hiệu năng quá chặt, tách nhóm nhị phân thường là giải pháp **đơn giản, dễ chứng minh và dễ truy vết hơn**.

## 14. So sánh lựa chọn phương pháp theo dữ liệu

| Tình huống | Phương pháp nên cân nhắc | Lý do |
|---|---|---|
| `k_i=1` cho mọi loại | 0/1 knapsack | Không cần tách nhóm |
| `k_i` nhỏ | Lặp số bản sao hoặc tách nhóm | Cả hai dễ làm, chi phí chấp nhận được |
| `k_i` lớn, W vừa phải | **Tách nhị phân + 0/1** | `O(W Σ log(k_i'+1))`, dễ cài |
| n lớn, W vừa phải, tối ưu sát thời gian | Monotone queue | `O(nW)` với trọng lượng dương |
| W cực lớn, n nhỏ | Meet-in-the-middle/nhánh cận tùy ràng buộc | DP theo W có thể bất khả thi |
| Cần trả số lượng từng loại | Giữ lịch sử nhóm hoặc quyết định | Bản 1D chỉ giá trị chưa đủ để truy vết trực tiếp |
| Bắt buộc dùng đúng W | Exact-fill với `−INF` | Cơ sở khác at-most |
| Có nhiều giới hạn tài nguyên | DP đa chiều hoặc sparse/Pareto tùy đề | Tách nhóm vẫn được nhưng số ô tăng theo tích ngân sách |

### 14.1. Nhớ giới hạn của nhị phân khi W lớn

Giảm từ k xuống log k không làm mất yếu tố **W**. Nếu W gần 10^9, bảng `dp[W+1]` trong Java đã vượt khả năng cấp phát phổ biến, dù M rất nhỏ. Cần kiểm tra **cả số nhóm lẫn số ô trạng thái**.

### 14.2. Tách nhóm và nhiều tài nguyên

Nếu mỗi bản sao còn tiêu thụ thể tích, thời gian hoặc năng lượng, nhóm t bản sao có **vector tài nguyên** là t lần vector gốc. Tính chất biểu diễn số bản sao vẫn đúng. Sau tách, giải **0/1 knapsack đa tài nguyên** với mỗi nhóm là một pseudo-item; ví dụ hai tài nguyên `(w,volume)` thì chuyển `dp[m][v]` theo **hai vòng giảm**.

Số pseudo-item giảm xuống `O(Σ log(k_i+1))`, nhưng số trạng thái ngân sách vẫn là **tích** các giới hạn. Phải tính riêng hai nguồn chi phí này.

## 15. Các lỗi thường gặp khi dùng binary splitting

### Lỗi 1 — Bỏ phần dư

Với k=13, tạo `[1,2,4]` rồi dừng chỉ biểu diễn được tối đa 7 bản sao; mất các nghiệm lấy 8..13. **Sửa:** nhóm cuối phải lấy hết `remaining=6`.

### Lỗi 2 — Lấy nhóm cuối theo lũy thừa 2 dù quá kho

Với k=13, tạo `[1,2,4,8]` có tổng 15 bản sao, vượt k. **Sửa:** `take=min(power,remaining)`.

### Lỗi 3 — Chỉ giữ các bit 1 trong biểu diễn nhị phân của k

Nếu k=13 có bit 1 ở 8,4,1, tạo `[8,4,1]` thì không thể biểu diễn số lượng 2,3,6,... bằng cách chọn nhóm 0/1. **Sửa:** nhóm phải được tạo lần lượt `[1,2,4,6]` để phủ **mọi** số lượng tới k, không chỉ biểu diễn tổng k.

### Lỗi 4 — Duyệt sức chứa tăng

Pseudo-item là vật **0/1**, phải duyệt **giảm**. Duyệt tăng có thể dùng lại cùng nhóm và vượt giới hạn bản sao.

### Lỗi 5 — Duyệt giảm một lần trên cả loại không tách

Nếu chỉ có một cập nhật `dp[c]=max(dp[c],dp[c-w]+v)` cho mỗi **loại**, kết quả như chỉ có một bản sao, không đủ các số lượng từ 2 đến k. **Sửa:** tách thành các nhóm hoặc dùng chuyển đầy đủ theo q.

### Lỗi 6 — Tính trọng lượng và giá trị nhóm sai

Nhóm t bản sao phải có **trọng lượng `t·w` và giá trị `t·v`**. Không được nhân trọng lượng nhưng để nguyên giá trị hoặc ngược lại.

### Lỗi 7 — Quên cắt k theo sức chứa

Với `w>0`, chỉ cần số lượng đến `floor(W/w)`; không cắt vẫn có thể đúng nhưng tốn công tách/duyệt không cần thiết. Không được thực hiện phép cắt này nếu `w=0`.

### Lỗi 8 — Khởi tạo 0 cho bài exact-fill

Với yêu cầu dùng **đúng W**, `dp[W]=0` ban đầu có thể tạo nghiệm ảo. Chỉ `dp[0]=0`, còn trọng lượng dương phải là unreachable cho tới khi có chuyển hợp lệ.

### Lỗi 9 — Chuyển từ một ô unreachable

`-INF + groupValue` không phải ứng viên hợp lệ. Nếu sentinel bằng `Long.MIN_VALUE` và cộng không kiểm tra, có thể tràn. **Sửa:** kiểm tra tiền nhiệm khả thi trước.

### Lỗi 10 — Cho phép loại trọng lượng 0 trong phép chia

`W/w` gây lỗi chia 0. Với bounded `w=0`, xử lý riêng; với unbounded `w=0,v>0` không có tối ưu hữu hạn.

### Lỗi 11 — Nhầm số pseudo-item với số bản sao

Số nhóm ít **không có nghĩa** chỉ chọn được ít bản sao. Chọn một nhóm cỡ 8 nghĩa là lấy **tám bản sao cùng loại**, không phải một bản sao. Nếu cần truy vết số lượng, cộng `copies`, không cộng 1.

### Lỗi 12 — Dùng `int` cho tích lớn

`copies*weight`, `copies*value` có thể tràn trước khi ép kiểu nếu nhân dưới `int`. **Sửa:** ép lên `long` **trước phép nhân**, kiểm tra miền kết quả.

### Lỗi 13 — Bỏ chính sách hòa khi tái dựng

Khi nhiều cách đạt cùng giá trị tối ưu, nếu dùng dấu `>` thay vì `>=` khi quyết định lấy nhóm, ta chọn **bỏ** khi hòa. Đây là một cách hợp lệ, nhưng không nhất thiết trả số bản sao ít nhất hoặc thứ tự từ điển nhỏ nhất. Nếu đề yêu cầu tie-break, phải thiết kế thêm.

### Lỗi 14 — Tính thời gian chỉ theo số loại n

Một loại k lớn có thể tách thành nhiều nhóm. Độ phức tạp của binary splitting là theo **tổng số nhóm M**, không chỉ n. Dùng `O(nW)` cho bản binary splitting mà bỏ `log k` là sai nếu k không được chặn bằng hằng số.

### Lỗi 15 — Nghĩ mọi tối ưu đều là binary splitting

Monotone queue có thể đạt `O(nW)` trong bài bounded 1D với trọng lượng dương. Binary splitting là **một lựa chọn đúng**, không phải luôn là độ phức tạp tốt nhất.

## 16. Kiểm thử bằng oracle độc lập

Một cách đáng tin để kiểm chứng bounded knapsack với n nhỏ là **liệt kê số bản sao từng loại**:

```text
brute(i, remainingCapacity):
    if i == n:
        return 0
    ans = 0
    for q = 0..min(k_i, remainingCapacity / w_i):
        ans = max(ans,
                  q * v_i + brute(i+1, remainingCapacity-q*w_i))
    return ans
```

Đây là **pseudocode**, không phải chương trình Java độc lập. Với n nhỏ và k nhỏ, nó duyệt tất cả vector số lượng hợp lệ, tạo oracle độc lập so với binary splitting.

Cần đối chiếu:

1. **Giá trị:** kết quả binary splitting bằng oracle trên cùng input.
2. **Khả thi:** tổng trọng lượng của vector số lượng được truy vết không vượt W.
3. **Giới hạn:** mọi `0<=x_i<=k_i`.
4. **Giá trị truy vết:** `Σ x_i·v_i` bằng tối ưu DP.
5. **Khác biệt bài toán:** bounded không được trả kết quả của unbounded nếu kết quả sau dùng quá kho.
6. **Cơ sở:** `W=0`, không vật, `k=0`, vật nặng hơn W.
7. **Số nhóm:** tổng nhóm đúng k' và tất cả số lượng `0..k'` biểu diễn được.
8. **Số học:** với số lớn, nên kiểm tra kiểu dữ liệu/tràn và giới hạn RAM thay vì chỉ dựa kết quả thường.

### 16.1. Các bộ test cốt lõi

| Input | Bài toán | Kết quả đúng |
|---|---|---|
| A `(w=3,v=5,k=4)`, B `(2,4,3)`, W=10 | Bounded, không vượt | **18**; hai A, hai B |
| Cùng A,B nhưng bỏ k | Unbounded | **20** (năm B) |
| Một loại `(w=2,v=5,k=1)`, W=4 | Bounded | **5**, không phải 10 |
| Một loại `(w=2,v=3,k=20)`, W=7 | Bounded | **9**, lấy ba bản |
| Một loại `(w=5,v=8,k=0)`, W=10 | Bounded | **0** |
| Một loại `(w=5,v=8,k=9)`, W=4 | Bounded | **0** |
| Không có loại nào, W=10 | Bounded | **0** |
| Bất kỳ loại w dương, W=0 | Bounded | **0** |
| A `(3,5,2)`, B `(4,6,1)`, W=5 | Exact-fill | **Không có nghiệm** |
| Cùng A,B, W=6 | Exact-fill | **10** |
| Cùng A,B, W=7 | Exact-fill | **11** |
| Một loại w=0, v>0, k hữu hạn | Bounded, trường hợp mở rộng | Có thể lấy đủ k bản |
| Một loại w=0, v>0, không giới hạn k | Unbounded | Tối ưu vô hạn |

### 16.2. Vì sao các test nhỏ thường phát hiện lỗi hướng duyệt?

Với một loại duy nhất `k=1,w=2,v=5,W=4`, ba lô 0/1 phải cho 5. Nếu chương trình cho 10, chắc chắn nó đã dùng cùng nhóm hai lần hoặc có một lỗi ràng buộc tương đương.

Với một loại `k=3,w=2,v=5,W=6`, chương trình phải cho 15. Nếu chỉ cho 5, nó có thể đã cập nhật mỗi loại đúng một lần mà **quên tách nhóm**.

Bộ test một loại như vậy đặc biệt hữu ích vì loại trừ tương tác giữa nhiều loại vật; lỗi nằm ngay ở cách dùng `count` hoặc chiều vòng lặp.

## 17. Bài tập tự luyện và lời giải

### Bài 1 — Tạo nhóm

Tách `k=13` bản sao thành các nhóm 0/1 theo kỹ thuật nhị phân.

**Đáp án:** `[1,2,4,6]`. Nhóm cuối là 6, không phải 8, vì tổng phải bằng 13.

### Bài 2 — Nhóm khi k không phải số 2^p−1

Với `k=8`, vì sao không chỉ có ba nhóm `[1,2,4]`?

**Đáp án:** ba nhóm đó mới có tổng 7. Cần nhóm cuối chứa phần dư 1: `[1,2,4,1]` để biểu diễn cả số lượng 8.

### Bài 3 — Không chỉ giữ bit 1

Nếu k=13, một bạn lấy các bit 1 tạo `[8,4,1]`. Hãy đưa ra một số lượng hợp lệ không biểu diễn được.

**Đáp án:** `2`. Không thể tạo 2 từ các nhóm 8,4,1 khi mỗi nhóm chỉ chọn tối đa một lần. Cách đúng `[1,2,4,6]` biểu diễn được 2.

### Bài 4 — Cắt số lượng theo sức chứa

Một loại có k=100 bản sao, `w=7`, `W=20`. Cần xét tối đa bao nhiêu bản sao? Các nhóm là gì?

**Đáp án:** `k'=min(100,floor(20/7))=2`. Nhóm `[1,1]`. Dù có 100 bản trong kho, không thể chọn hơn 2.

### Bài 5 — Chiều duyệt

Một pseudo-item `(weight=2,value=5)` chỉ được chọn một lần, W=4. Vòng tăng cho kết quả sai nào?

**Đáp án:** sau cập nhật c=2 được 5, c=4 dùng tiếp `dp[2]+5=10`. Đó là dùng nhóm hai lần; vòng giảm mới cho 5.

### Bài 6 — Độ phức tạp

Có n loại, số bản sao tối đa loại i là k_i, sức chứa W. So sánh chặn thời gian thử q trực tiếp với binary splitting.

**Đáp án:** thử trực tiếp `O((W+1)Σ k_i)`; binary splitting `O((W+1)Σ log(k_i+1))`, hoặc thay k_i bằng `min(k_i,floor(W/w_i))` khi trọng lượng dương. Bộ nhớ bảng cho cả hai có thể là `O(W+1)`.

### Bài 7 — Truy vết số lượng

Bài mẫu W=10, A `(3,5,4)`, B `(2,4,3)`. Một nghiệm tối ưu chọn bao nhiêu mỗi loại?

**Đáp án:** `x_A=2`, `x_B=2`, tổng trọng lượng `2×3+2×2=10`, giá trị `2×5+2×4=18`. Nếu lưu theo pseudo-item thì phải cộng kích thước nhóm để khôi phục x.

### Bài 8 — Chính xác W

Với A `(3,5,k=2)` và B `(4,6,k=1)`, W=5, vì sao không thể trả 6 như bài không vượt?

**Đáp án:** B dùng trọng lượng 4 nên không **bằng** 5; không có tổ hợp trọng lượng 3/4 tạo đúng 5. Đáp án exact-fill là *impossible*. Khởi tạo `dp[c>0]=0` sẽ tạo nghiệm giả.

### Bài 9 — Trọng lượng 0

Loại X có k=3, trọng lượng 0, giá trị 7. Với bài bounded tối đa hóa và W=0, nên xử lý như thế nào?

**Đáp án:** lấy cả ba bản X, giá trị 21, vì không tốn sức chứa và số lượng hữu hạn. Không áp phép `W/w`. Nếu loại X được lấy vô hạn lần, giá trị cực đại không hữu hạn.

### Bài 10 — Hàng đợi đơn điệu

Bắt đầu từ `next[c]=max_(0<=q<=k)(old[c-qw]+qv)`. Khi đặt `c=r+tw`, `u=t-q`, biểu thức trong max sau khi tách `t·v` là gì?

**Đáp án:** `old[r+uw]−u·v` với cửa sổ `max(0,t-k)<=u<=t`. Deque đơn điệu duy trì cực đại biểu thức này trong cửa sổ, cho cập nhật O(1) khấu hao mỗi vị trí.

### Bài 11 — Nhiều chiều

Nếu mỗi bản sao còn tốn thể tích z và bị giới hạn thêm V, kỹ thuật tách nhóm còn đúng không? Chi phí DP sau tách thế nào?

**Đáp án:** vẫn đúng; nhóm t bản sao tiêu thụ `(t·w,t·z)`, giá trị `t·v`. Mỗi nhóm là 0/1, cập nhật hai chiều trọng lượng và thể tích **giảm**. Với M nhóm, chặn thời gian `O(M(W+1)(V+1))` và bộ nhớ `O((W+1)(V+1))` cho bản chỉ giá trị.

### Bài 12 — Giới hạn bộ nhớ

Với W=10^9 nhưng chỉ vài nhóm, binary splitting có bảo đảm chạy được trên JVM thông thường không?

**Đáp án:** không. M dù nhỏ nhưng mảng `dp[W+1]` có khoảng một tỷ phần tử; riêng mảng `long` thô đòi khoảng 8 GB và còn overhead, vượt rất nhiều môi trường. Phải cân nhắc phương pháp khác hoặc đặc điểm dữ liệu.

## 18. Checklist thiết kế trước khi nộp

1. **Đã xác nhận biến thể chưa?** 0/1, bounded hay unbounded; dùng không quá W hay đúng W?
2. **Thông số từng loại có đúng không?** `w_i`, `v_i`, `k_i`; giá trị và trọng lượng nhân với số bản sao.
3. **Có đặt đủ cơ sở DP?** At-most: bảng 0; exact: chỉ trọng lượng 0 đạt được.
4. **Đã xử lý `k_i=0` chưa?** Không tạo nhóm cho loại hết hàng.
5. **Với w dương, có cắt `k_i` xuống `floor(W/w_i)`?** Giữ nghiệm, giảm công việc.
6. **Nhóm tạo bằng `take=min(power,remaining)`?** Không bỏ phần dư, không lấy quá k.
7. **Mọi số q từ 0 tới k' còn biểu diễn được?** Dựa vào bổ đề các tổng liên tiếp.
8. **Tổng số bản sao nhóm đúng k'?** Không làm tăng kho.
9. **Có nhân cả trọng lượng và giá trị của nhóm không?** Pseudo-item t đại diện t bản sao.
10. **Mỗi nhóm chỉ được chọn một lần chưa?** DP một chiều phải duyệt sức chứa **giảm**.
11. **Nếu cần truy vết, có lưu đủ lịch sử/parent?** Không tự suy từ mảng 1D cuối.
12. **Nếu có trọng lượng 0, đã xử lý riêng?** Tránh chia 0 và phân biệt bounded/unbounded.
13. **Nếu có giá trị âm hoặc ràng buộc chọn tối thiểu, cơ sở có còn đúng không?** Xem lại `0` và `−INF`.
14. **Đã kiểm tra tràn số và cấp phát?** Tích group và `W+1`.
15. **Đã phát biểu đúng thời gian?** `O((W+1)M)` với `M=O(Σ log(k_i'+1))`; bộ nhớ O(W+1) khi xử lý nhóm trực tiếp.
16. **Đã so sánh brute force cho ca nhỏ?** Xác nhận giới hạn số lượng và tính khả thi.
17. **Nếu cần nhanh hơn, đã cân nhắc monotone queue?** Có thể đạt `O(nW)` nhưng khó cài hơn.
18. **Nếu nhiều tài nguyên, đã giữ mọi giới hạn?** Tách nhóm không tự loại được bùng nổ số chiều ngân sách.

**Ghi nhớ:** tách số lượng k thành các nhóm **`1,2,4,...,phần dư`**, biến mỗi nhóm thành một pseudo-item 0/1 có trọng lượng/giá trị được nhân đúng số bản sao. Bằng bổ đề các tổng liên tiếp, mọi số lượng `0..k` đều biểu diễn được, nên giá trị tối ưu của ba lô bounded **được bảo toàn**. Sau đó áp 0/1 knapsack **duyệt sức chứa giảm**, giúp giảm số lượt xử lý từ phụ thuộc tuyến tính vào số lượng bản sao xuống **logarit**; vẫn phải xét đúng điều kiện cơ sở, tài nguyên, tràn số và yêu cầu truy vết.
