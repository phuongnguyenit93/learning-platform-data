# Nhiều tài nguyên và sự gia tăng số chiều

> **Chủ đề:** Computer Science Algorithms → Quy hoạch động tài nguyên.  
> **Mục tiêu:** Biết thiết kế quy hoạch động (*dynamic programming, DP*) khi một lựa chọn đồng thời tiêu thụ **nhiều tài nguyên** như tiền, thời gian, trọng lượng, thể tích hoặc số ký hiệu `0`/`1`. Hiểu vì sao số chiều của trạng thái tăng, cách viết chuyển 0/1 và không giới hạn, cơ sở và trạng thái không khả thi, hướng cập nhật khi nén bộ nhớ, chi phí `O(n∏(B_j+1))`, khôi phục lời giải và giới hạn của tối ưu trạng thái thưa/Pareto. Ví dụ dùng Java 17+.

## 1. Một giới hạn và nhiều giới hạn khác nhau thế nào?

Trong bài toán **ba lô 0/1 một tài nguyên**, mỗi vật có:

- Trọng lượng `w[i]`.
- Giá trị `value[i]`.
- Sức chứa `W`.

Ta thường định nghĩa:

`dp[c]` = tổng giá trị lớn nhất có thể đạt khi dùng những vật đã xét và **không vượt quá** sức chứa `c`.

Với nhiều tài nguyên, một vật có thể vừa tốn **trọng lượng**, vừa chiếm **thể tích**, vừa tốn **thời gian**. Ví dụ giới hạn tổng trọng lượng là `6` và tổng thể tích là `5`:

| Vật | Trọng lượng | Thể tích | Giá trị |
|---|---:|---:|---:|
| A | 3 | 2 | 6 |
| B | 2 | 3 | 7 |
| C | 4 | 1 | 8 |
| D | 1 | 2 | 5 |

Mục tiêu: chọn một **tập vật**, mỗi vật **tối đa một lần**, sao cho:

`Σ weight[i] <= 6` và `Σ volume[i] <= 5`,

đồng thời **cực đại** `Σ value[i]`.

Chọn B và C tiêu thụ trọng lượng `2+4=6`, thể tích `3+1=4`, tổng giá trị `7+8=15`: đây là tối ưu của ví dụ.

**Không được cộng hai sức chứa thành một:** một vật nhẹ nhưng cồng kềnh có thể vi phạm thể tích, trong khi vật nặng nhưng gọn có thể vi phạm trọng lượng. Ràng buộc `weight <= W` và `volume <= V` phải được giữ **đồng thời**.

### 1.1. Vì sao `dp[c]` một chiều không còn đủ?

Giả sử `dp[c]` chỉ lưu giá trị tốt nhất khi đã dùng một mức trọng lượng. Hai phương án có cùng trọng lượng còn lại nhưng dùng **thể tích khác nhau** có thể có khả năng chọn vật tiếp theo khác nhau. Gộp hai phương án như vậy có nguy cơ loại một phương án dẫn đến tối ưu về sau.

Do đó trạng thái cần ghi lại **toàn bộ thông tin về tài nguyên** có thể ảnh hưởng các bước tiếp:

`dp[m][v]` = giá trị lớn nhất với giới hạn trọng lượng `m` **và** giới hạn thể tích `v` khi xét một tập vật đã xác định.

Đây là **hai chiều tài nguyên**, không tính chiều “số vật đã xét” nếu ta nén từng lớp vật vào cùng một bảng.

### 1.2. Nhớ đúng đơn vị của số chiều

Có hai cách nói đều đúng nhưng cần phân biệt:

- `dp[i][m][v]` là **bảng 3 chiều**: chỉ số `i` của số vật đã xét cộng **2 chiều tài nguyên**.
- Khi nén chiều `i`, ta có `dp[m][v]`: **bảng 2 chiều**, vẫn biểu diễn **2 tài nguyên**.

Nói “bài hai tài nguyên phải dùng bảng ba chiều” là **không hoàn toàn đúng**: bảng ba chiều dễ chứng minh và truy vết, còn bảng hai chiều có thể đủ nếu cập nhật đúng hướng.

## 2. Mô hình tổng quát với d tài nguyên

Cho `n` đối tượng. Mỗi đối tượng `i` có:

- Giá trị hoặc lợi nhuận `p_i`.
- Vector tiêu thụ `r_i = (r_i1,r_i2,...,r_id)` không âm.
- Vector ngân sách `B = (B_1,B_2,...,B_d)` không âm.

Trong biến thể **0/1**, lựa chọn `x_i ∈ {0,1}`. Bài toán cực đại:

`maximize Σ p_i x_i`

với **từng tài nguyên**:

`Σ r_ij x_i <= B_j`, cho mọi `j=1..d`.

Một **trạng thái ngân sách** là một điểm trong tích Descartes:

`(c_1,c_2,...,c_d)` với `0 <= c_j <= B_j`.

Số tổ hợp ngân sách có thể có là:

`S = (B_1+1)(B_2+1)...(B_d+1) = ∏_(j=1)^d (B_j+1)`.

Nếu mỗi giới hạn đều bằng `B`, thì `S=(B+1)^d`. Đây là **sự gia tăng số chiều** (*curse of dimensionality*) trong DP: thêm một ràng buộc tạo thêm một trục trạng thái.

Ví dụ khi **mỗi ngân sách bằng 100**:

| Số tài nguyên d | Số trạng thái ngân sách |
|---:|---:|
| 1 | `101` |
| 2 | `101² = 10.201` |
| 3 | `101³ = 1.030.301` |
| 4 | `101⁴ = 104.060.401` |

Nếu mỗi ô lưu `long` 8 byte, riêng **giá trị thô** của bảng 4 chiều ở dòng cuối đã vượt **832 MB**, chưa tính overhead mảng Java, tham chiếu, bộ đệm, GC và đầu vào. Một bảng theo cả `i` còn nhân thêm khoảng `n+1` lần.

**Mấu chốt:** số chiều không tăng **thời gian mỗi chuyển** quá nhiều trong ví dụ đơn giản; nó làm **số trạng thái có thể tăng theo tích các giới hạn**. Thuật toán là **giả đa thức** theo giá trị ngân sách; nếu ngân sách được mã hóa nhị phân, số ô có thể rất lớn so với số bit của input.

## 3. Thiết kế quan hệ chuyển cho ba lô 0/1 hai tài nguyên

Ta xét lần lượt `n` vật và tạm dùng bảng đầy đủ để suy luận.

Định nghĩa:

> `F[i][m][v]` là **giá trị lớn nhất** khi chỉ được dùng `i` vật đầu, mỗi vật tối đa một lần, tổng trọng lượng **không quá m** và tổng thể tích **không quá v**.

Đây là định nghĩa **hai giới hạn “không quá”**, không phải dùng chính xác m, v.

### 3.1. Cơ sở

Khi chưa xét vật nào (`i=0`), có thể chọn tập rỗng:

`F[0][m][v] = 0` cho mọi `0<=m<=W`, `0<=v<=V`.

Vì cho phép bỏ tất cả vật và giả sử lợi nhuận không âm, nghiệm rỗng giá trị 0 luôn khả thi. Không dùng `−∞` cho mọi trạng thái của hàng `i=0` trong phiên bản **không vượt ngân sách**.

### 3.2. Hai quyết định với vật i

Gọi vật i có trọng lượng `w`, thể tích `t`, giá trị `p`.

1. **Không lấy vật i**: giá trị tối ưu là `F[i−1][m][v]`.
2. **Lấy vật i** nếu **cả** `w<=m` **và** `t<=v`: giá trị là `F[i−1][m−w][v−t]+p`.

Kết hợp:

```text
F[i][m][v] = F[i-1][m][v]

if m >= w[i] AND v >= volume[i]:
    F[i][m][v] = max(
        F[i][m][v],
        F[i-1][m-w[i]][v-volume[i]] + p[i]
    )
```

**Vì sao phải dùng lớp `i−1` ở cả hai nhánh?** Mỗi vật chỉ được dùng một lần. Tiền nhiệm khi “lấy vật i” phải là lời giải **không chứa vật i**; nếu dùng chính lớp i theo cách cho phép tái sử dụng, ta đã đổi sang bài ba lô không giới hạn.

### 3.3. Ví dụ một chuyển

Xét vật C `(w=4,v=1,p=8)` tại ngân sách `(m=6,v=5)`.

- Không lấy C: giá trị tối ưu sau hai vật A,B là **13** (lấy A+B, trọng lượng 5, thể tích 5).
- Lấy C: phần ngân sách còn lại `(2,4)`. Từ A,B, chọn B `(2,3,7)` được giá trị 7, nên tổng `7+8=15`.

Do đó `F[3][6][5] = max(13,15)=15`. Vật D sau đó không cải thiện đáp án vì mọi tổ hợp chứa D ở điều kiện ngân sách này đều đạt không quá 15.

### 3.4. Khi nào một nhánh chuyển không hợp lệ?

Nếu `w>m` **hoặc** `t>v`, không được lấy vật. Đừng chỉ kiểm tra `w<=m` rồi truy cập `F[i-1][m-w][v-t]`: chỉ số thể tích có thể âm.

Nếu một vật **không tiêu thụ một loại tài nguyên**, ví dụ `w=0,t=2`, vẫn cần giữ cả hai điều kiện. Trong 0/1, vật tiêu thụ `(0,0)` có thể được chọn **đúng một lần** nếu lợi nhuận dương; còn với phiên bản **không giới hạn**, vật tiêu thụ `(0,0)` và giá trị dương gây tối ưu **vô hạn**.

## 4. Nén lớp vật: DP 2D và hai vòng duyệt ngược

Nếu chỉ cần **giá trị tối ưu**, không nhất thiết giữ mọi lớp `i`. Ta duy trì:

`dp[m][v]` = tối ưu khi dùng những vật **đã xử lý trước lượt hiện tại**, với ngân sách `(m,v)`.

Với mỗi vật:

```text
for m = W downTo weight:
    for v = V downTo volume:
        dp[m][v] = max(dp[m][v],
                       dp[m-weight][v-volume] + value)
```

**Tại sao phải duyệt NGƯỢC cả hai chiều?**

Nếu `weight>0`, tiền nhiệm `(m-weight, v-volume)` có chỉ số `m` **nhỏ hơn** và sẽ được xét **sau** trong vòng m giảm; nó vẫn là kết quả của các vật trước.

Nếu `weight=0` nhưng `volume>0`, tiền nhiệm thuộc **cùng hàng m** nhưng có `v` nhỏ hơn và sẽ được xét **sau** trong vòng v giảm; vẫn chưa dùng vật mới.

Nếu cả hai tiêu thụ bằng 0 trong một bài **0/1**, một ô được cập nhật đúng một lần khi xử lý vật đó; nó vẫn không thể tự lặp vô hạn chỉ vì `dp[m][v]` xuất hiện ở cả hai vế. Tuy nhiên, code có tính phí/cộng lợi nhuận phải bảo đảm không tràn số.

Cùng một bất biến cốt lõi: **mỗi phép chuyển của vật hiện tại đọc một trạng thái chưa được cải thiện bởi chính vật hiện tại**, ngoại trừ trường hợp tiêu thụ `(0,0)` mà một lần cập nhật cùng ô tương ứng với việc chọn vật đúng một lần.

Nếu đổi thành duyệt **xuôi cả hai chiều**, ta thường cho phép dùng **lặp lại** vật ngay trong một lượt, tức đang cài bài **unbounded** khác.

## 5. Java 17: ba lô 0/1 hai tài nguyên bằng bảng 2D

Lưu thành **TwoResourceKnapsackDemo.java**:

```java
import java.util.Objects;

public class TwoResourceKnapsackDemo {
    record Item(String id, int mass, int volume, long value) {}

    static long bestValue(Item[] items, int maxMass, int maxVolume) {
        Objects.requireNonNull(items, "items");
        if (maxMass < 0 || maxVolume < 0) {
            throw new IllegalArgumentException("Negative budget");
        }

        long[][] dp = new long[maxMass + 1][maxVolume + 1];

        for (Item item : items) {
            Objects.requireNonNull(item, "item");
            if (item.mass() < 0 || item.volume() < 0
                    || item.value() < 0) {
                throw new IllegalArgumentException("Invalid item");
            }

            for (int m = maxMass; m >= item.mass(); m--) {
                for (int v = maxVolume; v >= item.volume(); v--) {
                    long take = dp[m - item.mass()][v - item.volume()]
                            + item.value();
                    dp[m][v] = Math.max(dp[m][v], take);
                }
            }
        }
        return dp[maxMass][maxVolume];
    }

    public static void main(String[] args) {
        Item[] items = {
            new Item("A", 3, 2, 6),
            new Item("B", 2, 3, 7),
            new Item("C", 4, 1, 8),
            new Item("D", 1, 2, 5)
        };

        System.out.println("Best value: " + bestValue(items, 6, 5));
        System.out.println("No items: "
                + bestValue(new Item[0], 6, 5));
        System.out.println("Zero budgets: "
                + bestValue(items, 0, 0));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 TwoResourceKnapsackDemo.java
java TwoResourceKnapsackDemo
```

Stdout:

```text
Best value: 15
No items: 0
Zero budgets: 0
```

Vật B+C đạt giá trị `15`, trọng lượng `6`, thể tích `4`, thỏa **cả hai** giới hạn. Mảng `items` không bị sửa.

**Chi phí:** `n` vật, `(W+1)(V+1)` ô ngân sách, mỗi lượt cập nhật tối đa một lần mỗi ô. Thời gian **`O(n(W+1)(V+1))`**, bộ nhớ **`O((W+1)(V+1))`** số `long`. Với W,V ít nhất 1, thường viết gọn `O(nWV)` và `O(WV)`; cách viết có `+1` chính xác hơn khi một ngân sách bằng 0.

**Giới hạn của demo:** mảng `long[][]` vẫn có thể quá lớn để cấp phát; phép `maxMass+1` hoặc `maxVolume+1` cũng phải được giới hạn khi đưa API vào hệ thống thực tế để tránh tràn `int`. Tổng giá trị được giả định còn trong miền `long`; với dữ liệu cực lớn cần kiểm tra tràn hoặc dùng kiểu số phù hợp.

**Tính ổn định của trạng thái:** bảng dùng `Math.max`, không lưu danh tính vật đã lấy. Nếu nhiều tập vật cùng giá trị tối ưu, kết quả số là xác định nhưng chưa có thông tin để trả một tập vật cụ thể.

## 6. Chứng minh tính đúng của 0/1 DP nhiều tài nguyên

Chứng minh từ bảng đầy đủ `F[i][m][v]` bằng quy nạp theo i.

**Cơ sở:** với i=0, không có vật, tập rỗng là phương án duy nhất, giá trị 0. `F[0][m][v]=0` chính xác.

**Bước quy nạp:** giả sử mọi giá trị lớp `i-1` đều tối ưu. Với một lời giải khả thi từ i vật đầu:

- Nếu **không chứa vật i**, nó là một nghiệm ở trạng thái `F[i-1][m][v]`, nên không thể tốt hơn tối ưu của trạng thái này.
- Nếu **chứa vật i**, tổng chi phí tài nguyên phải còn cho phép vật đó, và các vật còn lại chỉ đến từ `i-1` vật đầu, với ngân sách `m-w`, `v-t`. Giá trị phần còn lại không vượt `F[i-1][m-w][v-t]`, nên tổng không vượt nhánh “lấy”.
- Hai nhánh **bao phủ mọi nghiệm** và mỗi nhánh tạo một nghiệm **khả thi** từ trạng thái con đã được chứng minh tối ưu. Lấy `max` là đúng tối ưu toàn cục.

Bởi quy nạp, `F[n][W][V]` là giá trị tối ưu của bài toán.

**Nén 2D đúng vì sao?** Sau khi kết thúc một lượt vật i, bảng `dp[m][v]` chính là lớp `F[i][m][v]`. Nhờ hướng duyệt giảm, các tiền nhiệm trong nhánh lấy vẫn mang giá trị lớp `F[i-1]` như công thức. Vì vậy nén không làm thay đổi ý nghĩa của quan hệ chuyển.

**Nhấn mạnh:** câu “mỗi ô có max nên tối ưu” không đủ chứng minh. Phải chứng minh **mọi phương án tối ưu** nằm trong nhánh lấy hoặc không lấy và các chuyển không dùng quá tài nguyên hay dùng vật hai lần.

## 7. Khác biệt 0/1 và không giới hạn: thay đổi chiều quét

Nếu có thể lấy **nhiều bản sao của mỗi loại vật**, ta đang giải **ba lô không giới hạn** (*unbounded knapsack*) với nhiều tài nguyên.

Vẫn có thể dùng bảng `dp[m][v]` theo ngân sách không vượt. Với mỗi **loại vật** tiêu thụ `(w,t)` và giá trị `p`:

```text
for m = w upTo W:
    for v = t upTo V:
        dp[m][v] = max(dp[m][v],
                       dp[m-w][v-t] + p)
```

Duyệt **TĂNG** cho phép tiền nhiệm đã chứa **chính loại vật đang xử lý**, nghĩa là có thể lấy tiếp một bản sao.

Nếu `w=0,t>0`, tiền nhiệm có cùng m nhưng v nhỏ hơn, được tính trước do v tăng. Nếu `w>0,t=0`, tiền nhiệm có m nhỏ hơn, được tính ở vòng m trước đó. Nếu `w=t=0` và `p>0`, có thể lấy vô hạn bản sao mà không tốn tài nguyên ⇒ **không có giá trị tối ưu hữu hạn**; ví dụ Java dưới đây từ chối loại vật này.

**Ví dụ:**

```text
Sức chứa: mass=6, volume=4
Loại A: mass=2, volume=1, value=4
Loại B: mass=3, volume=2, value=7

0/1: lấy A+B → mass 5, volume 3, value 11.
Không giới hạn: lấy B+B → mass 6, volume 4, value 14.
```

Không thể lấy hai bản sao B trong bài 0/1; nếu code 0/1 lại trả 14 thì đã dùng sai hướng cập nhật hoặc một trạng thái tiền nhiệm đã được cập nhật bằng vật hiện tại.

### 7.1. Java 17: so sánh hai chế độ

Lưu thành **TwoResourceUsageModesDemo.java**:

```java
import java.util.Objects;

public class TwoResourceUsageModesDemo {
    record Item(int mass, int volume, long value) {}

    static long best(Item[] items, int massBudget, int volumeBudget,
                     boolean unbounded) {
        Objects.requireNonNull(items, "items");
        if (massBudget < 0 || volumeBudget < 0) {
            throw new IllegalArgumentException("Negative budget");
        }

        long[][] dp = new long[massBudget + 1][volumeBudget + 1];

        for (Item item : items) {
            Objects.requireNonNull(item, "item");
            if (item.mass() < 0 || item.volume() < 0
                    || item.value() < 0
                    || (item.mass() == 0 && item.volume() == 0)) {
                throw new IllegalArgumentException("Invalid item");
            }

            if (unbounded) {
                // Duyệt tăng: cho phép lấy tiếp cùng một loại.
                for (int m = item.mass(); m <= massBudget; m++) {
                    for (int v = item.volume(); v <= volumeBudget; v++) {
                        dp[m][v] = Math.max(dp[m][v],
                            dp[m - item.mass()][v - item.volume()]
                            + item.value());
                    }
                }
            } else {
                // Duyệt giảm: mỗi vật chỉ lấy tối đa một lần.
                for (int m = massBudget; m >= item.mass(); m--) {
                    for (int v = volumeBudget; v >= item.volume(); v--) {
                        dp[m][v] = Math.max(dp[m][v],
                            dp[m - item.mass()][v - item.volume()]
                            + item.value());
                    }
                }
            }
        }
        return dp[massBudget][volumeBudget];
    }

    public static void main(String[] args) {
        Item[] items = {
            new Item(2, 1, 4),
            new Item(3, 2, 7)
        };

        System.out.println("0/1: " + best(items, 6, 4, false));
        System.out.println("Unbounded: " + best(items, 6, 4, true));
        System.out.println("Empty input: "
                + best(new Item[0], 6, 4, true));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TwoResourceUsageModesDemo.java
java TwoResourceUsageModesDemo
```

Stdout:

```text
0/1: 11
Unbounded: 14
Empty input: 0
```

Ở cả hai chế độ, bảng dùng hai chiều ngân sách; **không phải số chiều thay đổi**, mà **ý nghĩa cách tái sử dụng loại vật** và **hướng cập nhật** khác nhau.

**Chi phí:** với `n` loại vật và hai ngân sách W,V, cả hai chế độ có chặn `O(n(W+1)(V+1))` thời gian và `O((W+1)(V+1))` bộ nhớ. Không được kết luận rằng unbounded có giá trị tối ưu hữu hạn khi có vật tốn 0 mọi tài nguyên và lợi nhuận dương.

## 8. Nếu cần biết đã chọn những vật nào: giữ lại chiều i

Bảng 2D nén cho **giá trị** rất tiện, nhưng sau khi ghi đè từng lớp vật, ta đã mất thông tin của nhiều trạng thái tiền nhiệm. Không thể luôn lần ngược từ `dp[W][V]` bằng cách tự đoán vật cuối.

Một cách dễ chứng minh để **truy vết** là giữ:

`F[i][m][v]` với `i=0..n`.

Sau khi tính xong, đi ngược `i=n..1`:

- Nếu `F[i][m][v] == F[i-1][m][v]`, **bỏ vật i** là một quyết định tối ưu (kể cả có cách lấy cũng tối ưu bằng nhau).
- Nếu `F[i][m][v] > F[i-1][m][v]`, nhánh “lấy vật i” đã cải thiện giá trị: ghi vật i vào đáp án và giảm `(m,v)` đi mức tiêu thụ của nó.

Phép `>` chọn **bỏ vật khi hòa**. Điều này tạo một nghiệm xác định theo thứ tự vật, nhưng không có nghĩa nghiệm ấy tối ưu từ điển theo ID hay dùng ít vật nhất khi cùng giá trị.

### 8.1. Java 17: bảng 3D và truy vết

Lưu thành **TwoResourceReconstructionDemo.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class TwoResourceReconstructionDemo {
    record Item(String id, int mass, int volume, long value) {}
    record Result(long value, List<String> chosenIds,
                  int usedMass, int usedVolume) {}

    static Result solve(Item[] items, int maxMass, int maxVolume) {
        Objects.requireNonNull(items, "items");
        if (maxMass < 0 || maxVolume < 0) {
            throw new IllegalArgumentException("Negative budget");
        }

        int n = items.length;
        long[][][] dp = new long[n + 1][maxMass + 1][maxVolume + 1];

        for (int i = 1; i <= n; i++) {
            Item item = Objects.requireNonNull(items[i - 1], "item");
            Objects.requireNonNull(item.id(), "id");

            if (item.mass() < 0 || item.volume() < 0
                    || item.value() < 0) {
                throw new IllegalArgumentException("Invalid item");
            }

            for (int m = 0; m <= maxMass; m++) {
                for (int v = 0; v <= maxVolume; v++) {
                    long best = dp[i - 1][m][v];
                    if (m >= item.mass() && v >= item.volume()) {
                        long take = dp[i - 1][m - item.mass()]
                                          [v - item.volume()]
                                + item.value();
                        best = Math.max(best, take);
                    }
                    dp[i][m][v] = best;
                }
            }
        }

        int m = maxMass, v = maxVolume;
        int usedMass = 0, usedVolume = 0;
        List<String> chosen = new ArrayList<>();

        for (int i = n; i >= 1; i--) {
            Item item = items[i - 1];
            if (dp[i][m][v] > dp[i - 1][m][v]) {
                chosen.add(item.id());
                m -= item.mass();
                v -= item.volume();
                usedMass += item.mass();
                usedVolume += item.volume();
            }
        }
        Collections.reverse(chosen);
        return new Result(dp[n][maxMass][maxVolume],
                chosen, usedMass, usedVolume);
    }

    public static void main(String[] args) {
        Item[] items = {
            new Item("A", 3, 2, 6),
            new Item("B", 2, 3, 7),
            new Item("C", 4, 1, 8),
            new Item("D", 1, 2, 5)
        };

        Result answer = solve(items, 6, 5);
        System.out.println("Best value: " + answer.value());
        System.out.println("Chosen IDs: " + answer.chosenIds());
        System.out.println("Used mass: " + answer.usedMass());
        System.out.println("Used volume: " + answer.usedVolume());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TwoResourceReconstructionDemo.java
java TwoResourceReconstructionDemo
```

Stdout:

```text
Best value: 15
Chosen IDs: [B, C]
Used mass: 6
Used volume: 4
```

**Bất biến truy vết:** tại lớp i và ngân sách `(m,v)` hiện tại, tồn tại một nghiệm tối ưu của các vật `1..i` có giá trị `F[i][m][v]`. Nếu hai lớp có cùng giá trị, bỏ vật i vẫn đạt tối ưu. Nếu lớp i lớn hơn lớp i−1, mọi nghiệm tối ưu phải chứa vật i; giảm ngân sách theo vật đó đưa về tiền nhiệm đã được chứng minh tối ưu. Lặp tới lớp 0 sẽ lấy được một nghiệm khả thi và có đúng giá trị tối ưu.

**Chi phí:** thời gian **`O(n(W+1)(V+1))`**, bộ nhớ **`O((n+1)(W+1)(V+1))`** số `long`, cộng danh sách output. Chiều i này làm bộ nhớ lớn hơn bản 2D ở phần 5 khoảng n lần. Nếu RAM hạn chế, có thể lưu quyết định nén bit, tính lại một số lớp, chia để trị khi truy vết hoặc dùng cấu trúc khác, nhưng phải chứng minh đúng và tính thêm chi phí.

## 9. Bài kinh điển “Ones and Zeroes”: hai loại tài nguyên đếm được

Cho danh sách các **chuỗi nhị phân**; muốn chọn nhiều chuỗi nhất sao cho tổng số ký tự `0` không vượt M và tổng số ký tự `1` không vượt N. **Mỗi chuỗi dùng tối đa một lần**.

Đây là ba lô 0/1 hai tài nguyên:

- Một chuỗi là một vật.
- Trọng lượng tài nguyên thứ nhất = số ký tự `'0'`.
- Trọng lượng tài nguyên thứ hai = số ký tự `'1'`.
- Giá trị mỗi chuỗi = **1**, vì mục tiêu chọn số chuỗi tối đa.

Đặt:

`dp[z][o]` = số chuỗi chọn nhiều nhất từ những chuỗi đã xét, với tối đa `z` số 0 và `o` số 1.

Với một chuỗi có `cnt0`, `cnt1`:

`dp[z][o] = max(dp[z][o], dp[z-cnt0][o-cnt1]+1)`,

với `z>=cnt0`, `o>=cnt1`; **cả hai chiều đi giảm** vì chuỗi chỉ được chọn một lần.

Ví dụ:

```text
Các chuỗi: ["10", "0001", "111001", "1", "0"]
Giới hạn: 5 số 0, 3 số 1
Kết quả: chọn tối đa 4 chuỗi.
```

Một lựa chọn đạt 4 là `"10"`, `"0001"`, `"1"`, `"0"`: tổng số 0 là `1+3+0+1=5`, tổng số 1 là `1+1+1+0=3`, vừa đủ hai ngân sách.

### 9.1. Java 17: đếm số 0 và số 1

Lưu thành **BinaryStringsTwoBudgetsDemo.java**:

```java
import java.util.Objects;

public class BinaryStringsTwoBudgetsDemo {
    static int maxStrings(String[] strings, int maxZeros, int maxOnes) {
        Objects.requireNonNull(strings, "strings");
        if (maxZeros < 0 || maxOnes < 0) {
            throw new IllegalArgumentException("Negative budget");
        }

        int[][] dp = new int[maxZeros + 1][maxOnes + 1];

        for (String s : strings) {
            Objects.requireNonNull(s, "string");
            int zeros = 0;
            int ones = 0;

            for (int i = 0; i < s.length(); i++) {
                char c = s.charAt(i);
                if (c == '0') {
                    zeros++;
                } else if (c == '1') {
                    ones++;
                } else {
                    throw new IllegalArgumentException("Only 0 and 1");
                }
            }

            for (int z = maxZeros; z >= zeros; z--) {
                for (int o = maxOnes; o >= ones; o--) {
                    dp[z][o] = Math.max(
                            dp[z][o], dp[z - zeros][o - ones] + 1);
                }
            }
        }
        return dp[maxZeros][maxOnes];
    }

    public static void main(String[] args) {
        String[] example = {"10", "0001", "111001", "1", "0"};
        System.out.println("5 zeros, 3 ones: "
                + maxStrings(example, 5, 3));

        System.out.println("1 zero, 1 one: "
                + maxStrings(new String[]{"10", "0", "1"}, 1, 1));

        System.out.println("One empty string: "
                + maxStrings(new String[]{""}, 0, 0));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 BinaryStringsTwoBudgetsDemo.java
java BinaryStringsTwoBudgetsDemo
```

Stdout:

```text
5 zeros, 3 ones: 4
1 zero, 1 one: 2
One empty string: 1
```

**Vì sao chuỗi rỗng vẫn được chọn?** `""` tiêu thụ `(0,0)` và có giá trị 1, nhưng là **một vật 0/1**, không phải một loại được dùng vô hạn. Mỗi ô chỉ được xử lý **một lần cho chuỗi đó**, nên tăng tối đa 1. Nếu có k chuỗi rỗng **khác nhau** trong input thì có thể chọn đủ k chuỗi, phù hợp yêu cầu mỗi phần tử đầu vào tối đa một lần.

**Chi phí:** nếu tổng số ký tự của các chuỗi là L và có s chuỗi, bước đếm tốn `O(L)`; phần DP tốn `O(s(M+1)(N+1))` thời gian, `O((M+1)(N+1))` bộ nhớ. Khi chỉ nói `O(sMN)` mà bỏ L, ta đã quên chi phí đọc/đếm tài nguyên của từng chuỗi.

## 10. Từ hai chiều lên ba chiều và d chiều

Giả sử mỗi công việc cần:

- Tiền `costMoney`.
- Thời gian `costTime`.
- Năng lượng `costEnergy`.

Với ba ngân sách `(A,B,C)` và mỗi công việc chỉ chọn một lần, ta có bảng nén:

`dp[a][b][c]` = giá trị lớn nhất từ các công việc đã xét, tiêu thụ không quá `(a,b,c)`.

Quan hệ chuyển theo một công việc có vector `(x,y,z)` và lợi nhuận p:

```text
for a = A downTo x:
    for b = B downTo y:
        for c = C downTo z:
            dp[a][b][c] = max(
                dp[a][b][c],
                dp[a-x][b-y][c-z] + p
            )
```

Đây là **pseudocode** minh họa cấu trúc chuyển, không phải một chương trình Java độc lập. Cần kiểm tra từng ngân sách không âm, giới hạn cấp phát và việc cộng giá trị không tràn kiểu.

**Thời gian:** `O(n(A+1)(B+1)(C+1))`.  
**Bộ nhớ sau nén:** `O((A+1)(B+1)(C+1))`.  
**Nếu giữ lớp i:** bộ nhớ `O((n+1)(A+1)(B+1)(C+1))`.

Với **d tài nguyên**, lặp qua mọi vector ngân sách và cập nhật:

`O(n∏_(j=1)^d(B_j+1))` trạng thái/chuyển,

khi mỗi vật có đúng **hai lựa chọn lấy/bỏ**, và việc so sánh/đọc một trạng thái được coi hằng số; thao tác đọc hoặc ghi vector d chiều tự nó có thể có chi phí `O(d)` nếu d không phải hằng số.

**Không phải bài nào nhiều đặc trưng cũng cần nhiều chiều DP.** Chỉ thêm trục nếu đặc trưng đó là thông tin cần để xác định **những lựa chọn tương lai** hoặc điều kiện tối ưu. Nếu một tài nguyên là hàm xác định của tài nguyên khác, có thể tồn tại cách loại chiều phụ; phải chứng minh việc loại bỏ không gộp hai trạng thái có tương lai khác nhau.

## 11. Vì sao gọi là bùng nổ số chiều?

Giả sử có `d` tài nguyên, mỗi giới hạn là `B`. Một bảng đặc có `(B+1)^d` ô. Nếu B cố định 100:

```text
d=1:      101 ô
d=2:   10.201 ô
d=3: 1.030.301 ô
d=4: 104.060.401 ô
```

Thêm một chiều từ d lên d+1 làm số trạng thái **nhân thêm (B+1)**, không chỉ cộng thêm B.

Tuy nhiên phải phát biểu chính xác:

- Với **d cố định** và các ngân sách nhỏ, DP nhiều chiều vẫn có thể thực tế và rất hữu ích.
- Với **d tăng**, hoặc ngân sách lớn dù d=2, bảng đặc có thể quá tốn RAM/thời gian.
- Độ phức tạp theo **giá trị ngân sách** là giả đa thức, không phải đa thức theo độ dài mã hóa nhị phân của ngân sách khi số bit đầu vào nhỏ hơn nhiều so với giá trị.
- Các giới hạn rất khác nhau (`B1=5`, `B2=10^9`) làm tích trạng thái vẫn cực lớn; không thể lấy trung bình ngân sách rồi ước lượng.

**Ví dụ thực tế:** quản lý dự án có 8 loại hạn mức (ngày công, chi phí, CPU, RAM, I/O, nhân sự, rủi ro, băng thông). Đưa cả 8 loại thành 8 chiều nguyên rời rạc có thể khiến bảng đặc không khả thi. Đây là lúc phải cân nhắc tính thiết yếu của mỗi ràng buộc, tính chất dữ liệu và chiến lược giải khác, không nhất thiết cố viết thêm 8 vòng `for`.

## 12. DP thưa (*sparse DP*): chỉ lưu trạng thái đã đạt được

Thay vì cấp phát mọi ô ngân sách `(m,v)`, ta có thể lưu những **vector tài nguyên thực sự được sử dụng** bởi các tập vật đã xét.

Một trạng thái thưa:

`(usedMass, usedVolume) -> bestValue`.

Ở đây ngữ nghĩa khác bảng **không quá**:

- Khóa `(m,v)` nghĩa là một tập vật sử dụng **chính xác m và v** đơn vị tài nguyên.
- Giá trị lưu là giá trị tốt nhất trong các tập đã xét **với cùng vector sử dụng đó**.
- Nếu một vector không có trong map thì **chưa có nghiệm đạt vector ấy**, không phải mặc nhiên giá trị 0.

**Cơ sở:** map chứa duy nhất `(0,0)->0` khi chưa xét vật.

Với một vật có vector `(w,t)`, giá trị p:

1. **Bỏ vật:** giữ lại các trạng thái cũ.
2. **Lấy vật:** với mỗi trạng thái cũ `(m,v)->score`, nếu `(m+w,v+t)` không vượt ngân sách, cập nhật trạng thái mới với giá trị `score+p`.
3. Các vector dùng tài nguyên như nhau được gộp bằng `max` giá trị.

**Quan trọng:** phải tạo `next` từ **snapshot của map cũ**, hoặc cơ chế tương đương bảo đảm mỗi vật **chỉ được lấy một lần**. Nếu lặp cập nhật lên cùng map và dùng ngay trạng thái mới cho cùng vật, có thể vô tình tạo unbounded knapsack.

### 12.1. Loại bỏ trạng thái bị áp đảo (*Pareto dominance*)

Giả sử hai trạng thái sau cùng một số vật đã xét:

- A tiêu thụ `(m_A,v_A)` và đạt giá trị `p_A`.
- B tiêu thụ `(m_B,v_B)` và đạt giá trị `p_B`.

Nếu:

`m_A <= m_B`, `v_A <= v_B` và `p_A >= p_B`

với **ít nhất một bất đẳng thức nghiêm**, thì A **áp đảo B**.

Vì A dùng **không nhiều hơn mọi tài nguyên** và đạt **không ít giá trị hơn**, bất kỳ tập vật còn lại nào có thể thêm sau B cũng có thể thêm sau A, và kết quả từ A không kém B. Vậy B có thể bị loại **mà không mất giá trị tối ưu**, miễn A và B đã xét **cùng tập vật đầu vào** và các ràng buộc còn lại chỉ phụ thuộc vector tài nguyên cùng giá trị cộng thêm.

Đây là một lý do để giữ **biên Pareto** (*Pareto frontier*): chỉ các trạng thái chưa bị trạng thái khác áp đảo.

**Điều kiện áp dụng:** dominance theo hai tài nguyên như trên đúng khi mục tiêu là cực đại giá trị, tài nguyên được tiêu thụ không âm, các lựa chọn tương lai phụ thuộc **chỉ** vào tài nguyên còn lại và những vật chưa xét. Nếu bài có ràng buộc thứ tự, deadline cá nhân, trạng thái vị trí hay mục tiêu nhiều tiêu chí, dominance có thể cần thêm chiều hoặc không còn hợp lệ.

### 12.2. Java 17: sparse DP kèm Pareto pruning

Lưu thành **SparseParetoTwoResourcesDemo.java**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class SparseParetoTwoResourcesDemo {
    record Item(int mass, int volume, long value) {}
    record State(int mass, int volume) {}
    record Result(long value, int frontierSize) {}

    static Map<State, Long> paretoPrune(Map<State, Long> states) {
        List<Map.Entry<State, Long>> all =
                new ArrayList<>(states.entrySet());
        Map<State, Long> kept = new HashMap<>();

        // Minh họa đơn giản: so từng cặp, O(S^2).
        for (Map.Entry<State, Long> candidate : all) {
            State a = candidate.getKey();
            long valueA = candidate.getValue();
            boolean dominated = false;

            for (Map.Entry<State, Long> other : all) {
                State b = other.getKey();
                long valueB = other.getValue();

                boolean noMoreResources =
                        b.mass() <= a.mass() && b.volume() <= a.volume();
                boolean noLessValue = valueB >= valueA;
                boolean strictlyBetter =
                        b.mass() < a.mass()
                        || b.volume() < a.volume()
                        || valueB > valueA;

                if (noMoreResources && noLessValue && strictlyBetter) {
                    dominated = true;
                    break;
                }
            }
            if (!dominated) {
                kept.put(a, valueA);
            }
        }
        return kept;
    }

    static Result solve(Item[] items, int maxMass, int maxVolume) {
        Objects.requireNonNull(items, "items");
        if (maxMass < 0 || maxVolume < 0) {
            throw new IllegalArgumentException("Negative budget");
        }

        Map<State, Long> frontier = new HashMap<>();
        frontier.put(new State(0, 0), 0L);

        for (Item item : items) {
            Objects.requireNonNull(item, "item");
            if (item.mass() < 0 || item.volume() < 0
                    || item.value() < 0) {
                throw new IllegalArgumentException("Invalid item");
            }

            // Snapshot: không lấy vật hiện tại nhiều lần.
            Map<State, Long> next = new HashMap<>(frontier);

            for (Map.Entry<State, Long> entry : frontier.entrySet()) {
                State old = entry.getKey();
                long m = (long) old.mass() + item.mass();
                long v = (long) old.volume() + item.volume();

                if (m <= maxMass && v <= maxVolume) {
                    State target = new State((int) m, (int) v);
                    long candidate = entry.getValue() + item.value();
                    next.merge(target, candidate, Long::max);
                }
            }

            frontier = paretoPrune(next);
        }

        long best = 0L;
        for (long value : frontier.values()) {
            best = Math.max(best, value);
        }
        return new Result(best, frontier.size());
    }

    public static void main(String[] args) {
        Item[] items = {
            new Item(3, 2, 6),
            new Item(2, 3, 7),
            new Item(4, 1, 8),
            new Item(1, 2, 5)
        };

        Result result = solve(items, 6, 5);
        System.out.println("Sparse best: " + result.value());
        System.out.println("Pareto states: " + result.frontierSize());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SparseParetoTwoResourcesDemo.java
java SparseParetoTwoResourcesDemo
```

Stdout:

```text
Sparse best: 15
Pareto states: 9
```

Với bốn vật của ví dụ, bảng đặc có `(6+1)(5+1)=42` ô ngân sách. Sau khi xử lý và lọc dominance, phiên bản sparse lưu **9 trạng thái không bị áp đảo**; nó vẫn tìm đúng giá trị tối ưu **15**. Con số 9 đặc thù dữ liệu ví dụ, **không phải** cam kết kích thước biên Pareto của mọi input.

**Độ phức tạp:** nếu `S_i` là số trạng thái trước lượt i, việc sinh ứng viên có khoảng `O(S_i)` thao tác map kỳ vọng trong điều kiện hash phù hợp. Phiên bản `paretoPrune` so mọi cặp và tốn **`O(S_i²)`** với S_i là số ứng viên ở lượt đó. Tổng có thể xấp xỉ `O(Σ S_i²)` cho phép lọc minh họa, **không mặc nhiên nhanh hơn** bảng đặc. Với nhiều chiều hoặc nhiều trạng thái không bị áp đảo, Pareto frontier cũng có thể rất lớn (thậm chí tăng theo số tập con).

**Khi nào nên dùng:** nếu ngân sách lớn nhưng số trạng thái thực sự đạt/không bị áp đảo **nhỏ**, sparse DP có thể giảm bộ nhớ đáng kể. Với ngân sách nhỏ và d=2, bảng đặc có thể nhanh hơn rất nhiều vì mảng truy cập liên tục và không có overhead HashMap/prune.

**Rủi ro Java:** `State` là `record` bất biến nên dùng làm key HashMap an toàn. Nếu dùng một đối tượng **có thể sửa** các trường tham gia `equals/hashCode`, rồi sửa sau khi đưa vào map, sẽ làm mất tính nhất quán khóa. Tổng giá trị `long` vẫn có thể tràn nếu input quá lớn; mẫu giả định tổng vừa kiểu.

## 13. Bảng đặc, bảng thưa và Pareto: cách chọn

| Phương án | Trạng thái | Chi phí/công dụng | Khó khăn |
|---|---|---|---|
| **Dense 2D** | Mọi ngân sách `(m,v)` | Đơn giản, nhanh nếu ngân sách nhỏ; `O(nWV)` | Tốn bộ nhớ theo tích ngân sách |
| **Dense 3D theo i,m,v** | Mọi lớp vật và ngân sách | Dễ khôi phục nghiệm, chứng minh rõ | Bộ nhớ nhân thêm `n` |
| **Sparse exact-used** | Chỉ vector tài nguyên đạt được | Không cấp phát ô không thể đạt | Số trạng thái có thể lớn; HashMap overhead |
| **Sparse + Pareto** | Chỉ trạng thái chưa bị áp đảo | Có thể loại nhiều vector vô ích | Cần chứng minh dominance; prune có thể đắt |
| **Meet-in-the-middle** | Chia vật thành hai nhóm, liệt kê phương án | Hữu ích khi n tương đối nhỏ, ngân sách rất lớn | Có thể cần `O(2^(n/2))` trạng thái và kỹ thuật ghép nhiều chiều |
| **Xấp xỉ / làm tròn ngân sách** | Gộp các mức tài nguyên | Có thể giảm số trạng thái | Mất bảo đảm chính xác hoặc khả thi nếu làm tròn sai |

**Không có phương án luôn tốt nhất.** Chọn theo số vật, giới hạn từng tài nguyên, số tài nguyên, mật độ trạng thái khả thi, nhu cầu truy vết và yêu cầu nghiệm **chính xác hay xấp xỉ**.

### 13.1. Cơ chế Pareto có thể gặp bẫy

Giả sử A dùng `(2,4)` đạt 10 và B dùng `(3,3)` đạt 11. B dùng **ít thể tích hơn** nhưng **nhiều trọng lượng hơn** A; chưa ai áp đảo ai. Không được chỉ so tổng tài nguyên `(m+v)` vì hai nguồn lực có giới hạn **độc lập**.

Nếu A dùng `(2,2)` đạt 10 và B dùng `(3,4)` đạt 9, A rõ ràng áp đảo B. Khi các vật tương lai giống nhau, B không thể dẫn đến giá trị tốt hơn A.

Khi hai trạng thái có **cùng** vector tài nguyên, chỉ giữ giá trị **lớn nhất** ở vector đó. Đây là gộp trạng thái chính xác và có thể thực hiện trước cả bước so dominance.

## 14. “Không quá” và “chính xác”: điều kiện cơ sở khác nhau

Đây là lỗi thiết kế DP đặc biệt thường gặp.

### 14.1. Hai ngân sách không vượt mức cho phép

Với ngữ nghĩa:

`best[m][v] = giá trị lớn nhất khi dùng không quá m và không quá v`,

tập rỗng luôn hợp lệ. Với lợi nhuận không âm, khởi tạo:

`best[m][v] = 0` cho mọi m,v

là đúng ở lớp chưa xét vật nào.

### 14.2. Phải dùng chính xác cả hai tài nguyên

Nếu bài yêu cầu **tổng trọng lượng đúng m** và **thể tích đúng v**, trạng thái phải khác:

`exact[m][v] = giá trị tối ưu của một tập vật tiêu thụ đúng (m,v)`.

Cơ sở:

```text
exact[0][0] = 0
exact[m][v] = -INF   với mọi (m,v) khác (0,0)
```

Khi lấy vật, chỉ cộng giá trị từ tiền nhiệm **đang khả thi**, không cộng bừa vào `−INF` khiến tràn số hoặc sinh nghiệm ảo.

**Ví dụ:** chỉ có một vật `(mass=2, volume=1, value=5)` và ngân sách `(3,3)`.

- Yêu cầu **không quá** `(3,3)`: chọn vật, giá trị 5.
- Yêu cầu **chính xác** `(3,3)`: **không có nghiệm**, dù bảng `best[3][3]` đã có giá trị 5.

Cùng kích thước mảng và vòng lặp có thể trả lời **hai bài toán khác nhau** tùy định nghĩa trạng thái, cơ sở và cách lấy đáp án.

### 14.3. Tối thiểu hóa chi phí để đạt mục tiêu

Nếu muốn **ít chi phí nhất** để đạt đồng thời một số yêu cầu (chẳng hạn ít người nhất để phủ ít nhất A kỹ năng loại 1 và B kỹ năng loại 2), DP thường dùng **`min`** và trạng thái không đạt là **`+INF`**. Nếu vượt yêu cầu được phép, có thể dùng kỹ thuật **cắt ngưỡng** (*cap/saturation*):

`newA = min(A, oldA + contributedA)`,  
`newB = min(B, oldB + contributedB)`,

để gom mọi giá trị vượt yêu cầu thành trạng thái đã đạt. Nhưng việc cắt ngưỡng chỉ hợp lệ nếu mọi mức vượt đều **tương đương đối với tương lai và mục tiêu**. Không tự dùng saturation trong bài giới hạn **không được vượt**: ở đó vượt ngân sách phải **loại**, không phải quy về bằng ngưỡng.

## 15. Những kỹ thuật làm giảm kích thước trạng thái

### 15.1. Loại tài nguyên dư thừa khi có chứng minh

Nếu mọi vật có `volume[i]=2*mass[i]` và ngân sách thể tích V, thì giới hạn thể tích chỉ tương đương với:

`Σ mass[i] <= floor(V/2)`.

Ta có thể thay hai giới hạn `(W,V)` bằng một giới hạn:

`Σ mass[i] <= min(W, floor(V/2))`.

Khi ấy DP một chiều có thể giải chính xác. Nhưng nếu các vật **không đồng nhất tỉ lệ**, không được cộng gộp như trên.

### 15.2. Chặn ngân sách bằng tổng tiêu thụ tối đa

Với bài 0/1, không vật nào được dùng hai lần. Nếu tổng trọng lượng tất cả vật là `T_mass` và tổng thể tích là `T_volume`, ngân sách lớn hơn các tổng này không tạo thêm lựa chọn:

`effectiveW=min(W,T_mass)`,  
`effectiveV=min(V,T_volume)`.

Cách này có thể giảm kích thước bảng khi W,V lớn nhưng tài nguyên các vật nhỏ. Tuy nhiên phải tính các tổng bằng kiểu đủ rộng để tránh tràn số.

### 15.3. Chọn chiều lưu/cách biểu diễn

Một số bài có thể DP theo **giá trị đạt được** thay vì ngân sách, lưu **mức tài nguyên tối thiểu** tương ứng. Với nhiều tài nguyên, một giá trị đạt được có thể có **nhiều vector tài nguyên không so sánh được**, nên không phải lúc nào chỉ lưu một vector tốt nhất là đủ. Lúc đó có thể cần **tập Pareto** các vector cho từng mức giá trị.

### 15.4. Thay đổi độ chính xác có kiểm soát

Có thể chia ngân sách thành các mốc lớn hơn hoặc xấp xỉ chi phí để giảm số trạng thái, nhưng làm tròn lên/xuống có thể khiến:

- Một phương án ban đầu khả thi bị loại.
- Một phương án vượt ngân sách được coi nhầm hợp lệ.
- Giá trị tối ưu bị thay đổi.

Chỉ dùng khi đề **cho phép xấp xỉ**, đồng thời phát biểu rõ **bảo đảm sai số và tính khả thi**. Không được đổi cách mã hóa tài nguyên rồi khẳng định vẫn là thuật toán chính xác.

### 15.5. Khi n nhỏ nhưng ngân sách khổng lồ

Với n nhỏ, **liệt kê tập con** `2^n` hoặc **meet-in-the-middle** có thể phù hợp hơn bảng DP phụ thuộc ngân sách. Meet-in-the-middle tách n vật làm hai nhóm, liệt kê khoảng `2^(n/2)` vector mỗi bên và ghép trong phạm vi ngân sách; thao tác ghép đa tài nguyên cần kỹ thuật tìm kiếm/lọc phù hợp, không tự cho thời gian tuyến tính theo số trạng thái.

## 16. Kiểm tra biên và độ tin cậy khi cài Java

### 16.1. Ngân sách 0

Nếu mọi vật tiêu thụ dương ở ít nhất một tài nguyên và ngân sách mọi chiều đều 0, chỉ tập rỗng khả thi, giá trị tối ưu 0.

Nhưng trong 0/1, vật tiêu thụ `(0,0)` và có giá trị dương **vẫn được chọn** một lần, nên đáp án có thể lớn hơn 0 ngay cả khi mọi ngân sách là 0. Trong unbounded, loại vật `(0,0)` lợi nhuận dương khiến đáp án vô hạn, phải xử lý rõ.

### 16.2. Giá trị âm

Nếu cho phép **bỏ mọi vật** và tối đa hóa, vật có giá trị âm thường không có lợi khi tài nguyên tiêu thụ không âm. Các code mẫu yêu cầu lợi nhuận không âm để hợp đồng đơn giản. Nếu bài yêu cầu **chọn đúng k vật** hoặc **phải đạt ít nhất một điều kiện**, giá trị âm có thể cần xét; bảng khởi tạo toàn 0 khi ấy không nhất thiết đúng.

### 16.3. Tràn số

- Tính `maxMass+1`, `maxVolume+1` khi dùng `int` có thể tràn ở biên `Integer.MAX_VALUE`.
- Tổng lợi nhuận nhiều vật có thể vượt `long`.
- Tổng trọng lượng/thể tích có thể tràn `int` trước khi so ngân sách.
- Với sparse DP, cộng tài nguyên trước bằng `long` rồi mới ép chỉ số `int` nếu không vượt ngân sách.

Các chương trình mẫu là ví dụ thuật toán với ngân sách và giá trị nhỏ. API sản xuất cần hạn mức cấp phát và kiểm tra số học/giới hạn JVM theo tình huống.

### 16.4. Không dùng `HashMap` như mảng có thứ tự

`HashMap` không bảo đảm thứ tự duyệt. Độ dài/tập frontier có thể xác định, nhưng nếu muốn in trạng thái theo thứ tự từ điển ngân sách, phải sắp keys hoặc chọn cấu trúc có thứ tự. **Không** đặt giả định thuật toán vào thứ tự lặp HashMap.

### 16.5. Không tự coi trạng thái sparse vắng mặt bằng 0

Trong bản sparse exact-used, map ban đầu chỉ có `(0,0)->0`. Một trạng thái `(3,4)` vắng mặt nghĩa là chưa có tập vật nào dùng **chính xác** `(3,4)` từ các vật đã xét. Nếu `getOrDefault(key,0)` rồi chuyển như thể trạng thái có thể đạt, ta tạo nghiệm giả.

### 16.6. Biên Pareto không luôn nhỏ

Với d tài nguyên, nhiều phương án có thể đánh đổi giữa các tài nguyên, không có phương án nào tốt hơn toàn diện. Biên Pareto có thể rất lớn; thao tác lọc cặp `O(S²)` có thể chậm hơn dùng bảng dense. Cần benchmark và ước lượng số trạng thái thực trên dữ liệu mục tiêu.

### 16.7. Chỉ chọn đối tượng một lần

Bất kể dùng bảng 2D, 3D hay map, **0/1** phải bảo đảm chuyển “lấy” dùng **trạng thái trước khi xét đối tượng hiện tại**. Lặp xuôi tại chỗ hoặc cập nhật map ngay trong cùng vòng duyệt có thể dùng lại vật.

## 17. Phương pháp kiểm thử và oracle

Với n nhỏ, liệt kê mọi tập con là oracle độc lập cho bài 0/1:

```text
best = 0
for mask in [0, 2^n):
    usedMass = usedVolume = value = 0
    for each item i:
        if bit i của mask == 1:
            cộng các tài nguyên và giá trị của item i
    if usedMass <= W AND usedVolume <= V:
        best = max(best, value)
```

Thời gian `O(n·2^n)`, phù hợp **test nhỏ**, không phải giải pháp cho n lớn. Có thể so sánh kết quả của:

- Oracle vét cạn.
- Dense 2D.
- Dense 3D có truy vết.
- Sparse exact-used/Pareto.

Với cùng input và hợp đồng, bốn bản phải có **cùng giá trị tối ưu**. Nếu có yêu cầu trả tập vật, kiểm thêm: không lặp một vật, tổng từng loại tài nguyên không vượt ngưỡng, tổng giá trị bằng optimum.

### 17.1. Những bộ test quan trọng

| Input/hợp đồng | Kết quả hoặc điều kiện |
|---|---|
| Không có vật, ngân sách không âm | Giá trị 0 |
| Một vật đủ cả hai ngân sách | Có thể chọn vật nếu giá trị không âm |
| Vật đủ trọng lượng nhưng **vượt thể tích** | Không được chọn |
| Vật đủ thể tích nhưng **vượt trọng lượng** | Không được chọn |
| Hai vật cùng dùng vừa ngân sách | Có thể chọn cả hai nếu tối ưu |
| Có vật `(0,0,p>0)` trong 0/1 | Được lấy **một lần** |
| Có loại `(0,0,p>0)` trong unbounded | Tối ưu không hữu hạn |
| Hai nghiệm có giá trị bằng nhau | Cần chính sách hòa khi truy vết |
| Cùng vector tài nguyên, giá trị khác nhau | Sparse chỉ giữ giá trị lớn hơn |
| Hai vector đánh đổi mass/volume | Không được loại một vector tùy tiện |
| Yêu cầu dùng **chính xác** ngân sách | Dùng cơ sở unreachable khác bài “không quá” |
| Mọi ngân sách đều lớn | Kiểm tra kích thước trạng thái trước cấp phát |

### 17.2. Kiểm thử trực tiếp bộ dữ liệu của bài

Với A `(3,2,6)`, B `(2,3,7)`, C `(4,1,8)`, D `(1,2,5)`, W=6, V=5:

- Chọn B+C: `(mass=6,volume=4,value=15)`, khả thi.
- Chọn A+B: `(5,5,13)`, kém hơn.
- Chọn C+D: `(5,3,13)`, kém hơn.
- Chọn A+C: `(7,3,14)`, **không khả thi** vì trọng lượng 7 vượt W=6.
- Chọn B+D: `(3,5,12)`, khả thi nhưng kém hơn.

Vét cạn 16 tập con xác nhận không có nghiệm khả thi nào đạt quá 15. Một test chỉ so giá trị 15 mà không xác minh đủ hai ràng buộc vẫn có thể bỏ sót lỗi “quên kiểm tra thể tích”.

## 18. Bài tập tự luyện có đáp án

### Bài 1 — Chọn số chiều

Một công việc có chi phí tiền và thời gian độc lập, có hai ngân sách W và T. Viết trạng thái DP 0/1 đầy đủ và trạng thái sau nén lớp công việc.

**Đáp án:** đầy đủ `F[i][w][t]` = tối ưu trong i công việc đầu với tiền không quá w và thời gian không quá t. Nén `dp[w][t]` là lớp đã xét hiện tại. Truy hồi lấy/bỏ dùng `F[i-1]`; sau nén phải duyệt w,t giảm.

### Bài 2 — Ngân sách vừa đủ một chiều

Vật X nặng 2, thể tích 8, giá trị 20. Giới hạn W=3, V=7. Có được chọn X không?

**Đáp án:** **không**. Dù trọng lượng phù hợp, thể tích 8 vượt V=7. Mọi chiều ngân sách đều phải thỏa.

### Bài 3 — Giá trị tối ưu với hai tài nguyên

Với bốn vật A/B/C/D trong phần 1, W=6, V=5, tập nào đạt tối ưu?

**Đáp án:** B và C, dùng `(6,4)`, giá trị `15`. A+C vi phạm trọng lượng, A+B và C+D chỉ đạt 13.

### Bài 4 — Hướng vòng lặp

Mỗi vật chỉ được chọn một lần; đang dùng bảng `dp[m][v]` nén. Nếu duyệt m,v tăng, rủi ro gì?

**Đáp án:** tiền nhiệm có thể đã được cải thiện bởi **vật hiện tại**, cho phép lấy nhiều bản sao của nó. Duyệt **cả hai chiều giảm** để bảo toàn trạng thái 0/1.

### Bài 5 — Hai loại bài ba lô

Với A `(2,1,4)`, B `(3,2,7)`, ngân sách `(6,4)`, giá trị 0/1 và không giới hạn lần lượt bao nhiêu?

**Đáp án:** 0/1 là `11` nhờ A+B; không giới hạn là `14` nhờ B+B.

### Bài 6 — Nhân số trạng thái

Nếu có 3 tài nguyên, mỗi ngân sách bằng 20, bảng nén có bao nhiêu trạng thái?

**Đáp án:** `(20+1)³ = 21³ = 9.261` ô. Nếu giữ thêm chiều i với n vật, số ô là `(n+1)·9.261`.

### Bài 7 — Bài đếm chuỗi nhị phân

Với `["10","0","1"]`, tối đa 1 ký tự 0 và 1 ký tự 1, chọn nhiều nhất bao nhiêu chuỗi?

**Đáp án:** **2**: chọn `"0"` và `"1"`. Chọn `"10"` dùng hết cả hai ngân sách nhưng chỉ có 1 chuỗi.

### Bài 8 — Điều kiện cơ sở

Tại sao bảng tối đa hóa lợi nhuận **không vượt** ngân sách có thể khởi tạo tất cả ô bằng 0, nhưng bảng yêu cầu tiêu thụ **chính xác** hai ngân sách thì không?

**Đáp án:** với “không vượt”, chọn rỗng khả thi trong mọi ngân sách; với “chính xác”, chỉ `(0,0)` đạt được bằng tập rỗng. Những vector còn lại ban đầu **không đạt** và cần sentinel `−INF`/trạng thái unreachable.

### Bài 9 — Dominance

Hai trạng thái từ cùng một prefix vật: A dùng `(2,2)` được 10, B dùng `(3,4)` được 9. Có thể loại trạng thái nào?

**Đáp án:** loại **B**, vì A dùng không nhiều hơn tài nguyên ở mọi chiều và có giá trị cao hơn. Mọi tập vật tương lai thêm sau B cũng thêm được sau A.

### Bài 10 — Không so tổng hai tài nguyên

A dùng `(2,4)` đạt 10, B dùng `(3,3)` đạt 11. Có thể loại một trạng thái chỉ vì tổng tài nguyên đều bằng 6 không?

**Đáp án:** **không**. B tốn trọng lượng nhiều hơn nhưng thể tích ít hơn; hai phương án đánh đổi, có thể hữu ích khác nhau khi chọn vật về sau.

### Bài 11 — Truy vết

Một bảng `dp[m][v]` nén chỉ còn giá trị tối ưu. Vì sao không thể lấy một tập vật tối ưu bằng cách tùy tiện chọn những vật vừa đủ và có giá trị lớn?

**Đáp án:** thông tin **lớp vật trước khi cập nhật** đã bị ghi đè; phép max không cho biết đường chuyển nào tạo ra ô hiện tại. Giữ `F[i][m][v]` hoặc thông tin quyết định đủ để truy vết.

### Bài 12 — Bùng nổ số chiều

Với 4 ngân sách đều bằng 100, bảng long đặc có bao nhiêu ô và khoảng bao nhiêu byte dữ liệu thô?

**Đáp án:** `101⁴=104.060.401` ô. Mỗi `long` 8 byte ⇒ **832.483.208 byte**, chưa kể overhead và các bản sao.

## 19. Checklist trước khi triển khai DP nhiều tài nguyên

1. **Mục tiêu có chính xác không?** Cực đại giá trị, cực tiểu số bước, đếm cách hay chỉ cần kiểm tra tồn tại?
2. **Mỗi nguồn lực là gì?** Trọng lượng, thể tích, thời gian, tiền, số 0, số 1; đơn vị phải nhất quán.
3. **Là ràng buộc “không quá”, “ít nhất” hay “chính xác”?** Từng loại đòi cơ sở và cách xử lý biên khác nhau.
4. **Một vật/loại được dùng bao nhiêu lần?** 0/1 hay unbounded? Điều này quyết định lớp tiền nhiệm và hướng vòng lặp.
5. **Trạng thái đã đủ thông tin cho tương lai chưa?** Có cần thêm số vật đã xét, vị trí, deadline hoặc trạng thái điều kiện khác?
6. **Có cần tất cả chiều tài nguyên không?** Chỉ bỏ chiều sau khi chứng minh nó dư thừa hoặc xác định bởi chiều khác.
7. **Đã định nghĩa mọi điều kiện cơ sở chưa?** Tập rỗng, trạng thái không đạt, ngân sách 0, input rỗng.
8. **Chuyển có kiểm tra tất cả ngân sách không?** Không chỉ trọng lượng mà cả thể tích/thời gian/các giới hạn còn lại.
9. **Với 0/1, tiền nhiệm có thật từ lớp vật trước chưa?** Nén bảng thì duyệt giảm theo những chiều tài nguyên.
10. **Với unbounded, có loại vật tiêu thụ 0 mọi tài nguyên mà lợi nhuận dương không?** Nếu có, tối ưu có thể vô hạn.
11. **Đã tính số trạng thái theo tích chưa?** `S=∏(B_j+1)`, và tính chi phí thời gian, bộ nhớ, overhead mảng/Map.
12. **Có cần truy vết không?** Dense đầy đủ, decision trace hoặc kỹ thuật lưu parent thích hợp.
13. **Sparse/dominance có đúng với các lựa chọn tương lai không?** Chỉ loại trạng thái nếu không dùng nhiều hơn mọi tài nguyên, không ít giá trị hơn và có cùng những lựa chọn còn lại.
14. **Có nguy cơ tràn kiểu hoặc hết RAM không?** Kiểm tra `B+1`, tích các chiều, tổng lợi nhuận, casting chỉ số.
15. **Đã thử bộ test phân biệt 0/1 và unbounded chưa?** Dùng một vật có thể lấy nhiều lần để phát hiện vòng lặp sai.
16. **Đã đối chiếu bằng vét cạn trên n nhỏ chưa?** Kiểm tra giá trị, tính khả thi từng tài nguyên và nghiệm truy vết.
17. **Có phát biểu đúng độ phức tạp không?** Pseudopolynomial theo ngân sách, không nói chung “đa thức nhanh” theo mọi cách mã hóa.
18. **Đề có cho phép xấp xỉ không?** Nếu không, không được làm tròn tài nguyên rồi coi như kết quả vẫn chính xác.

**Ghi nhớ:** nhiều tài nguyên tạo thành **vector ngân sách**, và mỗi tài nguyên độc lập thường thêm **một chiều trạng thái**. Ba lô 0/1 với hai tài nguyên có thể giải bằng `dp[m][v]` duyệt giảm, thời gian `O(n(W+1)(V+1))`, bộ nhớ `O((W+1)(V+1))`; muốn khôi phục nghiệm dễ dàng có thể giữ thêm chiều vật. Với d tài nguyên, số ô là **tích** các giới hạn, gây **bùng nổ số chiều**. Bảng thưa và Pareto có thể giúp nếu trạng thái khả thi ít, nhưng không thay thế việc chứng minh **ngữ nghĩa, tính đúng, điều kiện cơ sở và chi phí thực**.
