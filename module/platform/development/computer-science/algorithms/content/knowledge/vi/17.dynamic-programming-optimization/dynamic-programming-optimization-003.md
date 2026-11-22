# Hàng đợi đơn điệu để tối ưu cửa sổ chuyển trong quy hoạch động

## 1. Bài toán: chuyển trạng thái chỉ nhìn lại một cửa sổ

Trong nhiều bài toán **quy hoạch động (Dynamic Programming, DP)**, khi tính trạng thái `dp[i]`, ta không cần xét tất cả trạng thái `j<i` mà chỉ được phép chuyển từ một số trạng thái gần nhất, ví dụ **`k` trạng thái ngay trước**.

Xét một bài toán cụ thể: có `n` vị trí đánh số `0,1,\ldots,n-1`, vị trí `i` có chi phí `cost[i]` (có thể âm). Bắt đầu ở vị trí `0`, mỗi bước nhảy **tiến về phía trước** từ vị trí `j` đến `i` khi:

\[
1\le i-j\le k.
\]

Mỗi vị trí được đặt chân tới phải trả chi phí của vị trí đó, **bao gồm vị trí bắt đầu `0`**. Cần tìm **tổng chi phí nhỏ nhất** để đến vị trí `n-1`; có thể cần khôi phục **một đường đi tối ưu**.

Định nghĩa:

> `dp[i]` là tổng chi phí nhỏ nhất của một đường đi hợp lệ từ `0` tới đúng vị trí `i`, có tính `cost[i]`.

Với `n>=1`, `k>=1`:

\[
dp[0]=cost[0],
\]

\[
dp[i]=cost[i]+\min_{\max(0,i-k)\le j<i}dp[j]
\quad (1\le i<n).
\]

Công thức này là trọng tâm bài học. Để đến `i`, bước cuối phải đi từ một trong các vị trí `i-k,\ldots,i-1` (giới hạn dưới bằng `0`). Vì chi phí trả ở `i` là cố định, ta chỉ cần tìm **giá trị `dp[j]` nhỏ nhất trong cửa sổ trượt**.

Nếu mỗi `i` duyệt toàn bộ `k` trạng thái trước để tìm min thì thời gian lên tới **`O(nk)`**. Khi `n` lớn và `k` gần `n`, cách này có thể gần `O(n²)`. Bằng **hàng đợi hai đầu đơn điệu (monotonic deque)**, ta duy trì đúng giá trị min của cửa sổ trong **tổng `O(n)` thời gian**.

**Phân biệt:** deque không làm “tham lam chọn chi phí vị trí nhỏ nhất”. Nó chọn **trạng thái DP có chi phí tích lũy tối ưu nhất**, và tính đúng vẫn đến từ công thức DP. Deque chỉ là cấu trúc dữ liệu trả lời nhanh phép min/max theo cửa sổ.

## 2. Ví dụ và so sánh với quét trực tiếp

Cho:

```text
Chỉ số:    0  1  2  3  4  5  6
cost:     [6, 4, 7, 2, 3, 5, 1]
k = 3
```

Ta được phép nhảy tiến tối đa ba vị trí. Theo công thức:

| i | Các chỉ số tiền nhiệm được phép | Min `dp[j]` | `cost[i]` | `dp[i]` | Chọn cha |
|---:|---|---:|---:|---:|---:|
| 0 | Bắt đầu | — | 6 | 6 | -1 |
| 1 | `[0]` | 6 | 4 | 10 | 0 |
| 2 | `[0,1]` | 6 | 7 | 13 | 0 |
| 3 | `[0,1,2]` | 6 | 2 | 8 | 0 |
| 4 | `[1,2,3]` | 8 | 3 | 11 | 3 |
| 5 | `[2,3,4]` | 8 | 5 | 13 | 3 |
| 6 | `[3,4,5]` | 8 | 1 | 9 | 3 |

Kết quả là **`dp[6]=9`**, với một đường đi tối ưu:

```text
Vị trí:   0 ─────→ 3 ─────→ 6
Chi phí:  6        2        1

Tổng = 6 + 2 + 1 = 9.
Mỗi bước nhảy dài 3, hợp lệ vì k=3.
```

Dãy DP là `[6,10,13,8,11,13,9]`. Để tính `dp[6]`, ta lấy min của `dp[3]=8`, `dp[4]=11` và `dp[5]=13`; **không** được xét `dp[0]=6` vì vị trí `0` đã nằm ngoài cửa sổ chuyển cho `i=6`.

Cách chậm luôn thực hiện vòng lặp:

```text
for i = 1..n-1:
    best = +infinity
    for j = max(0, i-k)..i-1:
        best = min(best, dp[j])
    dp[i] = cost[i] + best
```

Vòng trong lặp tới `k` lần trên mỗi `i`. Ta muốn thay nó bằng thao tác lấy min từ **đầu một deque**, nhưng phải bảo đảm các phần tử trong deque vẫn **hợp lệ về chỉ số** và **có thứ tự về giá trị DP**.

## 3. Hàng đợi đơn điệu là gì?

Một **deque** (*double-ended queue*) hỗ trợ thêm/xóa ở cả đầu và cuối với chi phí hằng số bình quân theo cấu trúc triển khai. Trong Java, `ArrayDeque<Integer>` là lựa chọn thường dùng để lưu **chỉ số** của các trạng thái DP ứng viên.

Với bài **tìm min**, ta duy trì deque chứa các chỉ số `j` thỏa các bất biến:

1. **Chỉ số tăng dần từ đầu đến cuối deque.** Các trạng thái được thêm theo thứ tự thời gian/chỉ số.
2. **Giá trị `dp[j]` tăng nghiêm ngặt từ đầu đến cuối deque** nếu ta loại phần tử cuối có `dp[back]>=dp[new]`. Vị trí ở đầu có `dp` nhỏ nhất.
3. **Các chỉ số quá hạn đã được loại khỏi đầu trước khi truy vấn:** tại thời điểm tính `dp[i]`, mọi chỉ số còn lại đều thuộc `[max(0,i-k),i-1]`.
4. **Những ứng viên đã bị loại vì kém hơn không thể trở thành lựa chọn tốt hơn về sau**, nhờ cửa sổ di chuyển từ trái sang phải.

Điều thứ tư là lý do ta không cần giữ mọi trạng thái. Một chỉ số cũ `j` có thể bị loại khi có chỉ số mới hơn `p>j` mà `dp[p]<=dp[j]`: về sau, bất cứ lúc nào `j` còn nằm trong cửa sổ, `p` cũng còn nằm trong cửa sổ và có giá trị không lớn hơn. Vậy `j` không bao giờ cần làm ứng viên tốt nhất nữa.

### Trực giác về hai đầu deque

- **Đầu deque (front):** nơi đọc ứng viên min hiện tại, cũng là nơi bỏ các chỉ số **quá hạn**.
- **Cuối deque (back):** nơi loại những ứng viên cũ có `dp` **không tốt hơn** ứng viên mới, sau đó thêm chỉ số mới.

Với bài tìm **max**, ta đảo chiều điều kiện đơn điệu: giữ giá trị `dp` **giảm** từ đầu đến cuối, loại cuối khi `dp[back]<=dp[new]`; đầu deque khi đó là max.

Bảng so sánh:

| Mục tiêu cửa sổ | Thứ tự giá trị từ đầu đến cuối | Bỏ cuối khi thêm `i` | Truy vấn |
|---|---|---|---|
| **Min** | Tăng nghiêm ngặt | `dp[back] >= dp[i]` | `dp[front]` |
| **Max** | Giảm nghiêm ngặt | `dp[back] <= dp[i]` | `dp[front]` |

Ở cả hai trường hợp, điều kiện hết hạn **theo chỉ số** là giống nhau; chỉ điều kiện **theo giá trị** ở đuôi thay đổi.

## 4. Quy trình cập nhật deque cho mỗi trạng thái

Giả sử đã tính `dp[0],\ldots,dp[i-1]` và chuẩn bị tính `dp[i]`. Deque đang chứa những ứng viên được giữ từ các bước trước.

**Bước A — Loại tiền nhiệm hết hạn ở đầu.**

Cửa sổ của `i` là:

\[
L_i=\max(0,i-k),\qquad R_i=i-1.
\]

Chỉ số nào **`<i-k`** thì không được phép chuyển tới `i`, nên phải xóa khỏi đầu:

```java
while (!deque.isEmpty() && deque.peekFirst() < i - k) {
    deque.removeFirst();
}
```

Chú ý dấu **`<`**, không phải `<=`. Nếu `j=i-k` thì `i-j=k`, bước nhảy dài đúng `k` vẫn hợp lệ; không được xóa.

**Bước B — Đọc trạng thái tốt nhất và tính `dp[i]`.**

Sau khi loại hết hạn, đầu deque là chỉ số có `dp` nhỏ nhất trong cửa sổ:

```java
int bestPrevious = deque.peekFirst();
dp[i] = Math.addExact(dp[bestPrevious], cost[i]);
parent[i] = bestPrevious;
```

`Math.addExact` phát hiện tràn số `long` và ném ngoại lệ thay vì âm thầm cho đáp án sai. Nếu bài toán bảo đảm mọi tổng đều nằm trong `long`, có thể cộng trực tiếp, nhưng phải dựa trên giới hạn đầu vào có thật.

**Bước C — Loại phần tử cuối bị ứng viên mới thống trị.**

Trạng thái `i` vừa tính sẽ trở thành một ứng viên cho các trạng thái **tương lai**. Ta xóa khỏi cuối các chỉ số có DP lớn hơn hoặc bằng `dp[i]`:

```java
while (!deque.isEmpty()
        && dp[deque.peekLast()] >= dp[i]) {
    deque.removeLast();
}
deque.addLast(i);
```

Tại thời điểm này `i` **chưa được** làm tiền nhiệm cho chính nó; chỉ thêm `i` **sau khi tính xong `dp[i]`**. Nếu thêm trước khi truy vấn, chương trình có thể tạo phép chuyển tự thân không hợp lệ `i→i`.

**Thứ tự chuẩn của một lượt:**

1. Loại hết hạn ở đầu.
2. Đọc min ở đầu, tính `dp[i]` và `parent[i]`.
3. Loại các giá trị kém hơn ở cuối.
4. Thêm `i` vào cuối cho các lượt sau.

Với `n>=1` và `k>=1`, deque không rỗng lúc đọc: ít nhất vị trí `i-1` là một tiền nhiệm hợp lệ. Các thao tác bỏ ở đuôi luôn để lại một ứng viên mới hơn không kém ứng viên bị bỏ; không thể mất toàn bộ những ứng viên hợp lệ mà chưa có phần thay thế.

## 5. Mô phỏng deque trên ví dụ

Ta dùng ký hiệu `j:v` nghĩa là chỉ số `j` có giá trị `dp[j]=v`. Deque liệt kê từ **đầu sang cuối**.

Dữ liệu: `cost=[6,4,7,2,3,5,1]`, `k=3`.

| Lượt | Việc làm | Deque sau khi thêm `i` | `dp[i]` |
|---:|---|---|---:|
| Khởi tạo 0 | `dp[0]=6` | `[0:6]` | 6 |
| 1 | Đầu là `0:6`, tính `10`, thêm `1` | `[0:6, 1:10]` | 10 |
| 2 | Đầu vẫn `0:6`, tính `13` | `[0:6, 1:10, 2:13]` | 13 |
| 3 | Đầu `0:6`, tính `8`; xóa đuôi `2:13`, `1:10` | `[0:6, 3:8]` | 8 |
| 4 | Xóa đầu `0:6` vì `0<4-3`, lấy `3:8`, tính `11` | `[3:8, 4:11]` | 11 |
| 5 | Lấy `3:8`, tính `13` | `[3:8, 4:11, 5:13]` | 13 |
| 6 | Lấy `3:8`, tính `9`; bỏ đuôi `5:13`, `4:11` | `[3:8, 6:9]` | 9 |

Điểm đáng chú ý tại `i=3`: hai chỉ số `1` và `2` bị loại vì chỉ số mới `3` vừa **mới hơn** vừa có `dp[3]=8` **nhỏ hơn** `dp[1]=10` và `dp[2]=13`. Tương lai không cần chúng nữa.

Tại `i=4`, chỉ số `0` có `dp[0]=6` nhỏ nhất về mặt số học, nhưng đã **quá hạn** vì bước nhảy `0→4` có độ dài `4>k`. Không thể giữ `0` rồi lấy min sai.

Tại `i=6`, phần tử `3` vẫn hợp lệ vì `6-3=3=k`. Do đó phải dùng điều kiện xóa **`index < i-k`**, không phải `index <= i-k`.

### Vì sao không cần sắp lại deque?

Ứng viên mới luôn có chỉ số lớn hơn mọi ứng viên trước. Sau khi xóa phần cuối có `dp` không nhỏ hơn giá trị mới, chỉ cần thêm vào đuôi là giá trị DP trong deque lại tăng nghiêm ngặt. Các thao tác chỉ thêm/xóa ở **hai đầu**, không cần tìm kiếm nhị phân hay sắp xếp.

## 6. Java 17+ hoàn chỉnh, có truy vết đường đi

Chương trình sau giải đúng bài nhảy tiến tối đa `k` với chi phí tại mỗi vị trí (cho phép âm):

- `solve`: sử dụng **`ArrayDeque<Integer>`**, trả chi phí tối thiểu và một dãy chỉ số của đường đi.
- `solveQuadratic`: thực hiện công thức DP bằng cách duyệt tất cả tiền nhiệm trong cửa sổ, dùng làm lời giải **đối chứng** cho đầu vào nhỏ.
- Mỗi bước thêm đúng **một** chỉ số vào deque và xóa các chỉ số cũ chỉ khi cần.
- Khi nhiều ứng viên có giá trị DP bằng nhau, điều kiện `>=` ở đuôi **giữ ứng viên mới hơn**. Nhờ vậy kết quả đường đi có tính xác định theo quy tắc này, nhưng **không hứa** tối thiểu số bước nhảy trong những đường đi có cùng chi phí.

Quy ước API:

- Mảng `cost` khác `null` và **không rỗng**.
- `maxJump>=1`, không cần nhỏ hơn chiều dài mảng. Nếu `maxJump` lớn hơn số vị trí còn lại thì cửa sổ tự được giới hạn bởi `0`.
- Chi phí là `long`, có thể âm, bằng `0` hoặc dương; tổng phải nằm trong miền `long`. Dùng `Math.addExact` để phát hiện tràn.
- Với một vị trí duy nhất, đường đi chỉ gồm `[0]` và đáp án là `cost[0]`.
- Dùng danh sách chỉ số **0-based**. Đường đi phải bắt đầu `0`, kết thúc `n-1` và mỗi bước nhảy không vượt `maxJump`.

Đặt tên tệp **`MonotonicQueueDpDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.List;
import java.util.Objects;

public final class MonotonicQueueDpDemo {
    private MonotonicQueueDpDemo() {
    }

    public record Answer(long minCost, List<Integer> path) {
        public Answer {
            path = List.copyOf(path);
        }
    }

    private static void checkInput(long[] cost, int maxJump) {
        Objects.requireNonNull(cost, "cost");
        if (cost.length == 0) {
            throw new IllegalArgumentException("cost must not be empty");
        }
        if (maxJump < 1) {
            throw new IllegalArgumentException("maxJump must be positive");
        }
    }

    // Thời gian O(n); dp và parent lưu O(n) phần tử.
    public static Answer solve(long[] cost, int maxJump) {
        checkInput(cost, maxJump);
        int n = cost.length;

        long[] dp = new long[n];
        int[] parent = new int[n];
        Deque<Integer> deque = new ArrayDeque<>();

        dp[0] = cost[0];
        parent[0] = -1;
        deque.addLast(0);

        for (int i = 1; i < n; i++) {
            // Chỉ những chỉ số j >= i - maxJump được phép.
            while (!deque.isEmpty()
                    && deque.peekFirst() < i - maxJump) {
                deque.removeFirst();
            }

            // Luôn tồn tại tiền nhiệm vì maxJump >= 1.
            int bestPrevious = deque.peekFirst();
            dp[i] = Math.addExact(dp[bestPrevious], cost[i]);
            parent[i] = bestPrevious;

            // Deque min: loại ứng viên cũ lớn hơn hoặc bằng.
            while (!deque.isEmpty()
                    && dp[deque.peekLast()] >= dp[i]) {
                deque.removeLast();
            }
            deque.addLast(i);
        }

        List<Integer> reversed = new ArrayList<>();
        for (int at = n - 1; at != -1; at = parent[at]) {
            reversed.add(at);
        }
        Collections.reverse(reversed);
        return new Answer(dp[n - 1], reversed);
    }

    // DP O(n*k) để đối chiếu tính đúng trên dữ liệu nhỏ.
    public static long solveQuadratic(long[] cost, int maxJump) {
        checkInput(cost, maxJump);
        long[] dp = new long[cost.length];
        dp[0] = cost[0];

        for (int i = 1; i < cost.length; i++) {
            int left = Math.max(0, i - maxJump);
            long best = dp[left];

            for (int j = left + 1; j < i; j++) {
                if (dp[j] < best) {
                    best = dp[j];
                }
            }
            dp[i] = Math.addExact(best, cost[i]);
        }
        return dp[cost.length - 1];
    }

    public static void main(String[] args) {
        long[] sample = {6, 4, 7, 2, 3, 5, 1};

        Answer example = solve(sample, 3);
        System.out.println("Example min: " + example.minCost());
        System.out.println("Example path: " + example.path());
        System.out.println("Slow check: "
            + solveQuadratic(sample, 3));

        Answer oneStep = solve(sample, 1);
        System.out.println("Jump 1 min: " + oneStep.minCost());
        System.out.println("Jump 1 path: " + oneStep.path());

        Answer largeJump = solve(sample, 100);
        System.out.println("Jump 100 min: " + largeJump.minCost());
        System.out.println("Jump 100 path: " + largeJump.path());

        Answer negative = solve(
            new long[] {5, -2, 8, -4, 3, 1}, 2
        );
        System.out.println("Negative costs min: "
            + negative.minCost());
        System.out.println("Negative costs path: "
            + negative.path());

        Answer tied = solve(new long[] {0, 0, 0, 0}, 2);
        System.out.println("Ties min: " + tied.minCost());
        System.out.println("Ties path: " + tied.path());

        Answer single = solve(new long[] {-7}, 2);
        System.out.println("Single min: " + single.minCost());
        System.out.println("Single path: " + single.path());

        boolean rejected = false;
        try {
            solve(new long[] {1, 2}, 0);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("Zero jump rejected: " + rejected);
    }
}
```

Biên dịch và chạy bằng **JDK 17 hoặc mới hơn**:

```bash
javac -encoding UTF-8 MonotonicQueueDpDemo.java
java MonotonicQueueDpDemo
```

**Đầu ra chuẩn:**

```text
Example min: 9
Example path: [0, 3, 6]
Slow check: 9
Jump 1 min: 28
Jump 1 path: [0, 1, 2, 3, 4, 5, 6]
Jump 100 min: 7
Jump 100 path: [0, 6]
Negative costs min: 0
Negative costs path: [0, 1, 3, 5]
Ties min: 0
Ties path: [0, 1, 2, 3]
Single min: -7
Single path: [0]
Zero jump rejected: true
```

### Đọc các kết quả đặc biệt

- `k=3`: đường đi `0→3→6` có tổng `6+2+1=9`, tối ưu.
- `k=1`: chỉ nhảy sang vị trí kế tiếp, buộc đi qua **mọi vị trí**, tổng `28`.
- `k=100` lớn hơn chiều dài mảng: có thể nhảy `0→6` và trả `7`; số lượng vị trí trong cửa sổ tự bị giới hạn bởi các chỉ số đã tồn tại.
- Với mảng `[5,-2,8,-4,3,1]`, chi phí **âm** vẫn hợp lệ; đường đi `0→1→3→5` có tổng `5-2-4+1=0`. Deque so sánh **giá trị DP tích lũy** nên không cần chi phí của từng vị trí phải không âm.
- Với mọi chi phí bằng `0`, có nhiều đường đi cùng đạt `0`. Quy tắc loại `>=` ở đuôi giữ các chỉ số mới hơn, cho đường đi `[0,1,2,3]` trong ví dụ. Một đường đi khác cùng chi phí cũng hợp lệ.
- `n=1` không có bước nhảy nào; trả đúng chi phí vị trí bắt đầu. `maxJump=0` bị từ chối theo hợp đồng.
- `Math.addExact` được dùng để tránh tràn `long` âm thầm. Nếu dữ liệu lớn tới mức tổng thật vượt `long`, chương trình ném `ArithmeticException` thay vì trả giá trị sai.

### Vì sao lưu `parent[]` vẫn đúng dù ứng viên bị xóa khỏi deque?

Khi tính `dp[i]`, `parent[i]` được gán **trước** khi đẩy `i` vào deque. Xóa một chỉ số khỏi deque chỉ có nghĩa nó không còn cần làm ứng viên **cho các trạng thái tương lai**; nó **không xóa** giá trị `dp` hay chỉ số cha đã lưu của các trạng thái cũ. Vì vậy có thể truy vết từ `n-1` theo `parent[]` về `0` mà không phụ thuộc những ứng viên còn lại trong deque ở cuối vòng lặp.

## 7. Chứng minh tính đúng của deque đơn điệu

Ta tách thành hai phần: công thức DP đúng, và deque trả đúng min của cửa sổ.

### 7.1. Chứng minh công thức DP bằng quy nạp

**Cơ sở `i=0`:** chỉ có đường đi bắt đầu và kết thúc tại `0`, trả chi phí `cost[0]`. Do đó `dp[0]=cost[0]`.

**Bước quy nạp:** giả sử `dp[j]` đúng cho mọi `j<i`. Mọi đường đi hợp lệ tới `i>0` phải có một bước cuối từ `j` với `1<=i-j<=k`. Tổng chi phí đường đi đó bằng tổng chi phí tới `j` cộng `cost[i]`. Đường đi tốt nhất tới `j` có chi phí `dp[j]` theo giả thiết, nên lựa chọn tối ưu tới `i` đúng bằng:

\[
cost[i]+\min_{\max(0,i-k)\le j<i}dp[j].
\]

Vì `k>=1`, tập tiền nhiệm không rỗng. Công thức đúng với mọi `i`.

### 7.2. Khi nào được xóa một ứng viên ở cuối?

Giả sử `j<p` và `dp[j]>=dp[p]`. Khi xét một trạng thái tương lai `t>p`:

- Nếu `j` còn hợp lệ trong cửa sổ, tức `j>=t-k`, thì vì `p>j`, ta cũng có `p>=t-k`.
- Vì `p<t`, `p` là một tiền nhiệm hợp lệ.
- `dp[p]<=dp[j]` nên chọn `p` không tệ hơn chọn `j` về giá trị min.

Vậy `j` bị **thống trị (dominated)** bởi `p`: sau khi có `p`, `j` không cần được giữ làm ứng viên tốt nhất trong bất kỳ cửa sổ tương lai nào.

Đây là lý do xóa đuôi khi `dp[back]>=dp[i]` là an toàn. Khi hai giá trị bằng nhau, ứng viên mới hơn được giữ: nó **hết hạn muộn hơn**, nên ít nhất không kém về mặt tìm giá trị tối ưu. Nếu bài còn yêu cầu phá hòa theo **chỉ số sớm nhất** hoặc theo đường đi từ điển nhỏ nhất, phải xem lại chính sách xóa dấu bằng.

### 7.3. Vì sao đầu deque luôn là min hợp lệ?

Các chỉ số được thêm theo thứ tự tăng dần. Những chỉ số nhỏ hơn `i-k` chỉ có thể nằm ở **phía đầu**, nên việc xóa từ đầu loại hết phần tử hết hạn.

Các phần tử còn lại có `dp` tăng từ đầu tới cuối. Mọi ứng viên đã bị loại ở đuôi từng có một ứng viên **mới hơn và không lớn hơn** thay thế. Khi ứng viên thay thế lại bị loại, quan hệ thống trị được duy trì qua chuỗi thay thế. Vì thế việc bỏ ứng viên kém không làm mất khả năng tìm min của cửa sổ.

Đầu deque là ứng viên có giá trị nhỏ nhất trong tất cả ứng viên còn hợp lệ. Thay min của phép chuyển DP bằng `dp[deque.peekFirst()]` là chính xác. Ghép với chứng minh công thức DP, `solve` trả đúng chi phí tối ưu.

### Bất biến cần nhớ

Ngay trước khi tính `dp[i]`:

1. Deque chứa các chỉ số tăng dần và nhỏ hơn `i`.
2. Sau khi bỏ hết hạn, mọi chỉ số trong deque nằm trong `[max(0,i-k),i-1]`.
3. Các giá trị `dp[j]` của các chỉ số trong deque tăng nghiêm ngặt.
4. Mỗi chỉ số tiền nhiệm hợp lệ không còn trong deque đã bị một chỉ số mới hơn, không tệ hơn, thống trị.

Bốn điều đó đủ để khẳng định **đầu deque chính là min trong cửa sổ**.

## 8. Vì sao tổng thời gian là `O(n)`?

Nhìn riêng một lượt, vòng `while` bỏ đuôi có thể chạy nhiều lần. Nếu chỉ nhân số vòng lặp, ta có thể lầm tưởng tổng thời gian vẫn `O(n²)`. Phân tích đúng là **phân tích khấu hao (amortized analysis)**:

- Mỗi chỉ số `i` được **thêm vào deque đúng một lần**.
- Mỗi chỉ số có thể bị xóa **nhiều nhất một lần**, ở đầu do hết hạn **hoặc** ở đuôi do bị thống trị. Một khi đã bị xóa, chỉ số đó không bao giờ được thêm lại.
- Vì thế có tối đa `n` lần thêm và `n` lần xóa trên toàn bộ quá trình.
- Đọc đầu/đuôi, kiểm tra điều kiện và cập nhật `dp[i]` có chi phí `O(1)` mỗi lần.

Tổng chi phí các thao tác trên deque là **`O(n)`**, cộng với việc tính và truy vết `O(n)`, nên:

\[
\boxed{\text{Thời gian }O(n)}.
\]

Trong code có mảng `dp[]` và `parent[]` dài `n` để truy vết: bộ nhớ tổng là **`O(n)`**. Riêng deque chứa các chỉ số còn liên quan tới cửa sổ, cùng với chỉ số mới được thêm, nên có tối đa **`O(\min(n,k+1))`** phần tử.

Nếu **chỉ cần giá trị cuối** và các ứng viên có thể lưu dưới dạng cặp `(index,value)`, ta có thể không giữ toàn bộ `dp[]` hay `parent[]`, dùng **`O(\min(n,k+1))` bộ nhớ** cho deque và vài biến. Tuy nhiên, khi cần **truy vết đường đi**, phải lưu đủ thông tin cha `O(n)` hoặc một cấu trúc tương đương.

| Cách tính | Thời gian | Bộ nhớ phụ | Ghi chú |
|---|---|---|---|
| Quét mọi tiền nhiệm hợp lệ | `O(nk)`, chặn trên bởi `O(n²)` | `O(n)` nếu lưu toàn bộ `dp` | Dễ hiểu, tốt làm oracle |
| Deque đơn điệu, chỉ cần min cuối | `O(n)` | `O(\min(n,k+1))` | Lưu cặp chỉ số–giá trị trong deque |
| Deque đơn điệu có truy vết như mã | **`O(n)`** | **`O(n)`** | Lưu `dp[]` và `parent[]` |
| Dùng cây đoạn (segment tree) | `O(n\log n)` thường gặp | `O(n)` | Linh hoạt hơn với một số loại cập nhật/truy vấn |
| Heap min có xóa lười | `O(n\log n)` thường gặp | Có thể `O(n)` | Phải loại phần tử hết hạn khi truy vấn |

Deque có lợi thế khi **cửa sổ trượt theo chỉ số tăng**, **ứng viên được đưa vào một lần theo thứ tự**, và ta chỉ cần **min hoặc max của một khóa cố định**.

## 9. Điều kiện áp dụng và giới hạn

Không phải mọi công thức DP có cửa sổ đều dùng deque đơn điệu được.

### 9.1. Trường hợp áp dụng trực tiếp

Dạng chuẩn:

\[
dp[i]=g(i)+\min_{j\in[L_i,R_i]}key(j),
\]

trong đó:

- `key(j)` **cố định sau khi trạng thái `j` được tạo**, không thay đổi khi `i` tăng.
- Các ứng viên đến theo chỉ số tăng dần.
- Biên trái `L_i` chỉ đi **sang phải hoặc đứng yên**, nên ứng viên đã hết hạn không quay lại.
- Biên phải `R_i` cũng được xử lý theo thứ tự tiến, không đột ngột quay lùi để đưa lại ứng viên cũ.
- `g(i)` không phụ thuộc vào `j`, nên có thể đưa ra ngoài phép min.

Trong bài nhảy của chúng ta:

```text
g(i) = cost[i]
key(j) = dp[j]
L_i = max(0, i-k)
R_i = i-1
```

Cửa sổ dịch sang phải đúng một vị trí mỗi lượt, nên thuật toán đơn giản nhất.

### 9.2. Phép biến đổi trước khi dùng deque

Một công thức có thể trông phức tạp nhưng tách được phần phụ thuộc `i` và `j`. Ví dụ:

\[
dp[i]=base[i]+
\min_{j\in[i-k,i-1]}\bigl(dp[j]+P[i]-P[j]\bigr).
\]

Vì `P[i]` không phụ thuộc `j`:

\[
dp[i]=base[i]+P[i]+
\min_{j\in[i-k,i-1]}\bigl(dp[j]-P[j]\bigr).
\]

Khi đó dùng deque theo **`key(j)=dp[j]-P[j]`**, không phải theo `dp[j]`. Đây là một kỹ năng quan trọng trong **tối ưu chuyển DP**: tìm cách viết mỗi ứng viên thành một **khóa cố định khi được thêm vào**.

Tương tự, nếu có một phụ phí cố định `fee[j]` của tiền nhiệm:

\[
dp[i]=base[i]+\min_j(dp[j]+fee[j]),
\]

ta duy trì deque theo `dp[j]+fee[j]`. Đừng lấy deque min theo `dp[j]` rồi cộng `fee[j]` của một ứng viên bất kỳ: thứ tự giữa các ứng viên có thể thay đổi.

### 9.3. Khi deque đơn điệu không đủ

Nếu giá trị ứng viên phụ thuộc vào trạng thái hiện tại theo một cách **không tách được**:

\[
dp[i]=\min_j\bigl(dp[j]+(i-j)^2\bigr),
\]

thứ tự tốt–xấu giữa hai ứng viên có thể thay đổi khi `i` tăng. Một ứng viên bị đánh giá kém tại thời điểm này có thể trở thành tốt hơn sau đó. Khi ấy, việc xóa đuôi chỉ dựa trên `dp[j]` có thể sai. Có thể cần biến đổi đại số và công cụ khác như **Convex Hull Trick**, **Li Chao Tree** hoặc phương pháp phù hợp với tính chất bài toán.

Nếu cửa sổ chuyển có thể **dịch ngược lại** và một chỉ số bị loại do hết hạn có thể lại hợp lệ, deque trượt một chiều cũng không xử lý trực tiếp được. Với các truy vấn min/max trên đoạn tùy ý và cập nhật động, cây đoạn hoặc cấu trúc khác thường phù hợp hơn.

Nếu bài yêu cầu **tổng** của cửa sổ, deque min/max không phải công cụ tự nhiên; **prefix sum** hoặc cửa sổ cộng dồn thường đơn giản hơn. Với **median**, **k-th smallest**, hay các thống kê thứ tự khác, cần cấu trúc dữ liệu khác.

## 10. Xử lý hòa, dấu âm và trạng thái không thể đạt

### 10.1. Hai ứng viên có giá trị DP bằng nhau

Trong code:

```java
while (!deque.isEmpty()
        && dp[deque.peekLast()] >= dp[i]) {
    deque.removeLast();
}
```

Dấu `>=` khiến **ứng viên mới hơn** giữ lại khi hai giá trị bằng nhau. Điều này đúng cho mục tiêu **chỉ tối ưu tổng chi phí**, vì ứng viên mới vừa không đắt hơn, vừa tồn tại lâu hơn trong những cửa sổ tương lai.

Nếu mục tiêu thứ cấp là **ít bước nhảy nhất**, **chỉ số tiền nhiệm nhỏ nhất**, hoặc **đường đi từ điển nhỏ nhất**, chính sách hòa phải được xét lại. Có thể cần so sánh cặp khóa `(cost, secondaryCriterion)` hoặc lưu thêm thông tin. **Không** mặc nhiên khẳng định cách xóa `>=` sẽ tối ưu mọi tiêu chí phụ.

Nếu đổi điều kiện thành `>` (chỉ bỏ ứng viên thật sự lớn hơn), deque có thể giữ nhiều ứng viên bằng giá trị; đầu deque thường là ứng viên cũ hơn. Giá trị **min** vẫn đúng, nhưng đường đi trả về và số lượng ứng viên được giữ có thể khác.

### 10.2. Chi phí vị trí có thể âm

Một điểm dễ nhầm: thuật toán này **không cần `cost[i]>=0`**. Các giá trị `dp[i]` cũng có thể âm hoặc không đơn điệu khi `i` tăng. Ta chỉ yêu cầu:

- Mọi phép chuyển tiến từ chỉ số nhỏ sang chỉ số lớn, nên các tiền nhiệm đã được tính.
- Khóa `dp[j]` của một ứng viên **không thay đổi sau khi được thêm**.
- Cửa sổ trượt về bên phải.

Ví dụ `cost=[5,-2,8,-4,3,1]`, `k=2` có đường đi `0→1→3→5` và tổng `0`. Không được dùng **Dijkstra** hay suy luận về độ dài đường đi không âm ở đây. Đây là một DP trên thứ tự chỉ số, **không có chu trình**.

### 10.3. Trạng thái bị chặn và không thể đạt

Ví dụ chính bảo đảm mỗi vị trí có thể đạt khi `k>=1` vì ta luôn có thể tiến một vị trí. Nhưng trong biến thể có **vị trí cấm**, tập ứng viên hợp lệ có thể rỗng. Khi đó:

- Không thêm các trạng thái `j` **không thể đạt** vào deque.
- Sau khi bỏ hết hạn, nếu deque rỗng, đánh dấu `dp[i]` là **không thể đạt**, không được gọi `peekFirst()` như thể có ứng viên.
- Không cộng một sentinel `INF` vào `cost[i]` mà không kiểm tra; có thể tạo giá trị giả hoặc tràn.
- Nếu vị trí hiện tại bị cấm, không tạo trạng thái tại đó.
- Khi muốn khôi phục đường đi, chỉ truy vết nếu đích thật sự có thể đạt.

Đừng dùng `dp[i]=0` để báo không thể đạt trong bài tối thiểu hóa nếu chi phí đường đi hợp lệ có thể bằng `0`. Có thể dùng `boolean[] reachable` riêng hoặc một sentinel có chứng minh miền giá trị.

### 10.4. Chỉ số và thời điểm hết hạn

Tại `i`, tiền nhiệm có chỉ số `j` hợp lệ đúng khi:

\[
i-k\le j\le i-1.
\]

Đoạn này **bao gồm hai đầu** trong chỉ số. Vì vậy:

- Bỏ chỉ số `j<i-k`.
- Giữ `j=i-k`.
- Chỉ thêm `i` **sau** khi đã tính `dp[i]`.
- `k=1` khiến cửa sổ chỉ gồm `i-1`.
- `k>=n` khiến có thể xét mọi trạng thái trước, nhưng deque vẫn đúng.

Nếu thay bài toán bằng cửa sổ `[i-k,i)` trong ký hiệu nửa mở, nó tương đương các tiền nhiệm `i-k,\ldots,i-1`. Không lẫn dấu `<`, `<=` giữa hai cách viết.

## 11. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Không xóa chỉ số hết hạn | Lấy min từ trạng thái nhảy xa hơn `k` | Bỏ đầu khi `front < i-k` |
| Bỏ khi `front <= i-k` | Xóa nhầm bước nhảy dài **đúng `k`** | Dùng dấu `<` |
| Thêm `i` trước khi tính `dp[i]` | Có thể tự dùng trạng thái `i` làm tiền nhiệm | Tính trước, thêm sau |
| Lưu chỉ giá trị `dp` mà không lưu chỉ số | Không biết khi nào ứng viên hết hạn | Lưu chỉ số hoặc cặp `(index,value)` |
| Với min lại loại đuôi khi `dp[back] <= dp[i]` | Giữ ứng viên tệ và bỏ ứng viên tốt | Min: bỏ khi **`dp[back]>=dp[i]`** |
| Với max vẫn dùng điều kiện của min | Đầu deque không còn là giá trị max | Max: bỏ khi **`dp[back]<=dp[i]`** |
| Quên xử lý hòa | Đường đi có thể khác mong muốn | Chốt rõ chính sách `>=` hay `>` |
| Dùng `cost[j]` thay vì `dp[j]` làm khóa | Quên chi phí đã tích lũy trước vị trí `j` | Duy trì khóa **đúng trong công thức chuyển** |
| Khi giá trị ứng viên phụ thuộc `i` vẫn dùng deque cố định | Có thể xóa ứng viên sẽ tốt lên sau này | Biến đổi khóa hoặc chọn cấu trúc khác |
| Cứ thấy vòng `while` lồng `for` là kết luận `O(n²)` | Bỏ qua việc mỗi chỉ số chỉ bị xóa một lần | Phân tích khấu hao `O(n)` |
| Khởi tạo deque rỗng khi bắt đầu `i=1` | Không có tiền nhiệm cho trạng thái đầu tiên | Thêm chỉ số `0` trước vòng lặp |
| Dùng `int` cho chi phí tích lũy lớn | Có thể tràn số | Dùng `long`, kiểm tra giới hạn/`Math.addExact` |
| Quên `parent[]` khi cần đường đi | Có giá trị tối ưu nhưng không dựng được lời giải | Lưu cha ngay khi tính `dp[i]` |
| Bị chặn/hết tiền nhiệm mà vẫn gọi `peekFirst()` | `NullPointerException` hoặc tính sai | Kiểm tra deque rỗng trong biến thể có trạng thái không đạt |
| Bảo rằng bản code có bộ nhớ `O(k)` | Sai vì còn lưu `dp[]` và `parent[]` | Bản có truy vết là **`O(n)`** |
| Dùng `LinkedList` chỉ vì tên “queue” | Có thể tốn overhead nút không cần thiết | Ưu tiên `ArrayDeque` cho hai đầu |
| Trộn quy tắc khoảng đóng/nửa mở | Lỗi lệch một ở biên cửa sổ | Định nghĩa rõ `[max(0,i-k),i-1]` |

## 12. Kiểm thử và đối chứng

Cách kiểm tra đáng tin cậy là giữ một phiên bản **`O(nk)`** đơn giản, rồi so với deque trên nhiều dữ liệu nhỏ. Hàm `solveQuadratic` trong chương trình chính là oracle cho cùng công thức chuyển.

### Các trường hợp cần có

1. **Một vị trí:** `n=1`, trả `cost[0]`, đường đi `[0]`.
2. **`k=1`:** phải đi qua mọi vị trí; tổng là tổng toàn bộ mảng.
3. **`k>=n`:** có thể nhảy xa, cửa sổ mở rộng mà không truy cập âm.
4. **Nhiều chi phí bằng nhau:** kiểm tra giá trị tối ưu và chính sách hòa.
5. **Chi phí âm:** phép min trên `dp` vẫn đúng, không giả định các giá trị không âm.
6. **Cửa sổ hết hạn đúng tại `i-k`:** bắt lỗi `<`/`<=`.
7. **Một giá trị DP mới nhỏ hơn nhiều ứng viên:** vòng xóa đuôi có thể xóa nhiều phần tử trong một lượt nhưng tổng chi phí vẫn tuyến tính.
8. **Chi phí rất lớn:** dùng `long` và bảo đảm dữ liệu thật sự nằm trong miền số. Thử riêng tình huống tràn để thấy `Math.addExact` báo lỗi.
9. **Đầu vào rỗng, `null` hoặc `k=0`:** ngoại lệ theo hợp đồng, không trả kết quả vô nghĩa.
10. **Tính hợp lệ của đường đi:** bắt đầu `0`, kết thúc `n-1`, chỉ số tăng nghiêm ngặt, mọi bước nhảy trong `1..k`, tổng chi phí các vị trí được chọn bằng `Answer.minCost`.

### Sinh dữ liệu nhỏ

Có thể sinh hàng nghìn mảng chi phí với cả số âm/dương, `k` ngẫu nhiên từ `1` tới `n+3`. Trên mỗi mảng:

- Tính `fast=solve(cost,k).minCost()`.
- Tính `slow=solveQuadratic(cost,k)`.
- Khẳng định `fast==slow`.
- Duyệt đường đi từ kết quả nhanh, kiểm tra khoảng nhảy và tổng chi phí.
- Thử cả mảng mà tất cả giá trị bằng nhau để phát hiện lỗi phá hòa.

Khi kết quả khác nhau, in lại toàn bộ `cost`, `k`, đường đi và bảng `dp` để xác định lỗi. Bản kiểm thử tham chiếu `O(nk)` đủ nhanh cho `n` nhỏ và độc lập với cấu trúc deque, nên phát hiện tốt những lỗi biên.

### Kiểm thử bằng vét cạn với n rất nhỏ

Nếu `n<=15`, còn có thể liệt kê mọi đường đi tăng chỉ số từ `0` tới `n-1` mà mỗi bước không vượt `k`, tính tổng chi phí rồi lấy min. So sánh ba kết quả **vét cạn, DP quét và DP deque** giúp kiểm tra cả công thức lẫn cấu trúc dữ liệu.

Tuy nhiên, **kiểm thử không thay thế chứng minh**: điều đảm bảo tính đúng tổng quát vẫn là công thức DP, quy tắc thống trị ứng viên và bất biến chỉ số/giá trị của deque.

## 13. Bài tập tự luyện

**Bài 1 — Tự lập bảng.** Với `cost=[6,4,7,2,3,5,1]`, `k=3`, tính toàn bộ `dp[]` và một đường đi tối ưu.

*Đáp án:* `dp=[6,10,13,8,11,13,9]`; đường đi `[0,3,6]`, tổng `9`.

**Bài 2 — Vì sao cần xóa đầu?** Ở `i=4` của ví dụ trên, vì sao không được dùng `dp[0]=6` dù đây là giá trị nhỏ nhất của `dp[0..3]`?

*Đáp án:* bước `0→4` dài `4` vượt `k=3`. Cửa sổ tại `i=4` chỉ gồm `j=1,2,3`.

**Bài 3 — Dấu so sánh.** Với `k=3` và `i=6`, `j=3` có hợp lệ không? Nếu điều kiện xóa là `j<=i-k`, lỗi gì xảy ra?

*Đáp án:* `6-3=3` nên hợp lệ. Dùng `<=` sẽ xóa nhầm tiền nhiệm `3`, có thể làm mất đường đi tối ưu.

**Bài 4 — Ứng viên bị thống trị.** Giả sử `j=2,p=5` và `dp[2]=11`, `dp[5]=7`. Vì sao có thể loại `2` khi `5` được thêm trong bài min cửa sổ trượt?

*Đáp án:* `5` mới hơn, có giá trị thấp hơn, và bất kỳ cửa sổ tương lai nào còn chứa `2` đều chứa `5` nếu thời điểm truy vấn lớn hơn `5`. `2` không thể tốt hơn `5` nữa.

**Bài 5 — Dữ liệu âm.** Với `cost=[5,-2,8,-4,3,1]`, `k=2`, tìm một đường đi chi phí tối thiểu.

*Đáp án:* `0→1→3→5`, tổng `5-2-4+1=0`. Deque vẫn đúng dù chi phí âm.

**Bài 6 — Chuyển sang max.** Nếu bài yêu cầu **tổng thưởng lớn nhất** thay vì chi phí nhỏ nhất, cần đổi điều kiện loại ứng viên ở đuôi thế nào?

*Đáp án:* giữ giá trị ứng viên theo thứ tự **giảm**; loại đuôi khi `dp[back]<=dp[i]`, đầu deque cho max.

**Bài 7 — Biến đổi khóa.** Cho:

\[
dp[i]=base[i]+
\min_{j\in[i-k,i-1]}\bigl(dp[j]+P[i]-P[j]\bigr).
\]

Hãy tách phần phụ thuộc `i` và xác định khóa để đưa vào deque.

*Đáp án:* `dp[i]=base[i]+P[i]+\min_j(dp[j]-P[j])`; duy trì **`key(j)=dp[j]-P[j]`**.

**Bài 8 — Hòa giá trị.** Nếu `dp[old]=dp[new]` với `old<new`, vì sao giữ ứng viên mới là an toàn cho **giá trị min**, nhưng có thể làm thay đổi đường đi được khôi phục?

*Đáp án:* ứng viên mới hết hạn không sớm hơn và có giá trị không lớn hơn; tuy vậy hai chỉ số có thể dẫn tới chuỗi `parent[]` khác nhau, dù tổng chi phí tối ưu như nhau.

**Bài 9 — Phân tích khấu hao.** Tại sao vòng `while` có thể xóa nhiều phần tử trong một lượt mà toàn thuật toán vẫn `O(n)`?

*Đáp án:* mỗi chỉ số được thêm một lần và chỉ có thể bị xóa một lần. Tổng số thao tác thêm/xóa trên toàn bộ chương trình là `O(n)`.

**Bài 10 — Nhận diện bài không phù hợp.** Nếu công thức chuyển là `dp[i]=min_j(dp[j]+(i-j)^2)`, tại sao không thể mặc định dùng deque min theo `dp[j]`?

*Đáp án:* độ tốt của `j` còn phụ thuộc `i` qua hạng `(i-j)^2`; thứ tự ứng viên có thể thay đổi khi `i` tăng. Cần biến đổi và chứng minh riêng hoặc dùng cấu trúc phù hợp.

## Ghi nhớ

**Hàng đợi đơn điệu tối ưu các phép chuyển DP mà mỗi trạng thái cần lấy min hoặc max của một cửa sổ ứng viên trượt theo thứ tự chỉ số.** Với:

\[
dp[i]=cost[i]+\min_{\max(0,i-k)\le j<i}dp[j],
\]

ta lưu **chỉ số** của các ứng viên trong một deque. Ở mỗi `i`: **bỏ chỉ số quá hạn ở đầu**, **đọc min**, **tính `dp[i]` và lưu cha**, **loại ứng viên kém hơn ở cuối**, rồi **thêm `i`**.

Cửa sổ min giữ `dp` tăng từ đầu tới cuối; cửa sổ max giữ `dp` giảm. Mỗi chỉ số thêm đúng một lần và bị xóa nhiều nhất một lần nên tổng thời gian là **`O(n)`**, thay cho `O(nk)` của cách quét. Khi cần dựng đường đi, lưu `parent[]`; khi chỉ cần giá trị có thể giảm bộ nhớ xuống theo kích thước cửa sổ.

Muốn áp dụng đúng, hãy kiểm tra **biên hết hạn `j<i-k`, khóa ứng viên cố định theo `j`, hướng min/max, chính sách hòa, trạng thái không thể đạt và tràn số**. Deque là công cụ tối ưu phép truy vấn; **định nghĩa DP và chứng minh ứng viên bị thống trị mới quyết định tính đúng**.
