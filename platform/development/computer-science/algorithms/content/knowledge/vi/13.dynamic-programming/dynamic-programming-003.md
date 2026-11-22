# Thiết kế quan hệ chuyển và điều kiện cơ sở

> **Chủ đề:** Computer Science Algorithms → Quy hoạch động.  
> **Mục tiêu:** Tự xác định **trạng thái** của quy hoạch động (*dynamic programming, DP*), suy ra **quan hệ chuyển** từ những quyết định cuối hoặc đầu, đặt **điều kiện cơ sở** đúng với ý nghĩa trạng thái, biểu diễn trạng thái không khả thi, chọn thứ tự tính không tạo vòng phụ thuộc và chứng minh lời giải đúng. Các ví dụ dùng Java 17+ với lệnh biên dịch, stdout và phân tích độ phức tạp.

## 1. Vì sao thiết kế trạng thái và điều kiện cơ sở quan trọng?

Quy hoạch động giải một bài toán bằng cách dùng kết quả của các **bài toán con**. Thay vì tính lại cùng trạng thái nhiều lần, ta lưu giá trị của trạng thái đó bằng **memoization** (trên xuống) hoặc **tabulation** (dưới lên).

Điều khó nhất thường **không** phải viết vòng `for`, mà là trả lời ba câu hỏi:

1. **`dp[...]` có nghĩa chính xác là gì?** Là số cách, chi phí nhỏ nhất, giá trị lớn nhất, độ dài dãy hay có thể đạt được?
2. **Từ những trạng thái nào tính được trạng thái hiện tại?** Đây là **quan hệ chuyển** (*transition/recurrence*).
3. **Những trạng thái nào đã biết đáp án mà không cần chuyển?** Đây là **điều kiện cơ sở** (*base cases*).

Nếu ba phần đó không nhất quán, code có thể chạy không lỗi nhưng trả số sai.

Ví dụ, trong bài đổi tiền với mệnh giá không giới hạn, nếu `dp[x]` có nghĩa là **số đồng tối thiểu để tạo đúng tổng x**, thì `dp[0]=0`: không cần đồng nào để tạo tổng 0. Nhưng trong bài đếm **số cách** tạo một tổng, `ways[0]=1`: có đúng **một cách chọn không gì cả** để tạo tổng 0. Cùng chỉ số 0 nhưng điều kiện cơ sở khác vì **ngữ nghĩa trạng thái khác**.

Cần phân biệt:

- **Subproblem (bài toán con):** phiên bản nhỏ hơn hoặc đơn giản hơn của bài toán ban đầu.
- **State (trạng thái):** bộ tham số mô tả chính xác thông tin còn cần biết để giải bài toán con.
- **Transition (chuyển):** công thức nối giá trị trạng thái với các trạng thái tiền nhiệm.
- **Base (cơ sở):** giá trị đã biết trực tiếp.
- **Evaluation order (thứ tự tính):** bảo đảm mọi trạng thái tiền nhiệm có giá trị trước khi dùng.
- **Answer extraction (lấy đáp án):** biết chính xác ô hoặc tổ hợp ô nào là lời giải cuối.

### 1.1. DP khác việc viết đệ quy bất kỳ

Một chương trình gọi chính nó chưa chắc có DP. Chẳng hạn Fibonacci đệ quy ngây thơ tính `fib(n-1)` và `fib(n-2)` liên tục lặp lại các giá trị. DP bổ sung **lưu kết quả các trạng thái đã giải**, hoặc tính chúng một lần theo thứ tự hợp lệ.

Ngược lại, nếu mỗi bài toán con chỉ được tạo một lần (ví dụ duyệt một cây không có chung node), memoization có thể không đem lại lợi ích lớn. Không phải mọi bài toán đều có cách mô hình DP có số trạng thái đủ nhỏ.

## 2. Quy trình thiết kế từ đề bài đến công thức

Một quy trình đáng tin cậy:

1. **Chốt mục tiêu và tập nghiệm khả thi.** Cần cực tiểu, cực đại, đếm hay kiểm tra tồn tại? Có giới hạn “mỗi vật một lần”, vật được lấy nhiều lần, chỉ đi xuống/phải, hay cho phép đi ngược?
2. **Chọn thứ tự phân rã.** Có thể xét “bước cuối”, “vật cuối”, “ký tự cuối”, “ô cuối”, “điểm chia” hoặc “quyết định đầu tiên”.
3. **Định nghĩa trạng thái bằng một câu hoàn chỉnh.** Ví dụ: `dp[i][c]` là giá trị lớn nhất khi **chỉ được xét i vật đầu** và sức chứa **không quá c**.
4. **Liệt kê tất cả lựa chọn hợp lệ.** Chọn/không chọn, đi từ trên/trái, đổi một ký tự, bỏ một ký tự. Các lựa chọn phải **đủ** và không tạo nghiệm giả.
5. **Viết công thức chuyển** và điều kiện để mỗi nhánh chuyển hợp lệ.
6. **Đặt các trạng thái cơ sở và bất khả thi.** Giá trị `0`, `1`, `+∞`, `−∞`, `false` hay trạng thái không tồn tại phải khớp ý nghĩa của `dp`.
7. **Kiểm tra hướng phụ thuộc và thứ tự tính.** Dùng DFS+memo khi trạng thái phụ thuộc về phía nhỏ hơn; tabulation phải tính tiền nhiệm trước hậu nhiệm.
8. **Xác định đáp án, phép truy vết và độ phức tạp.** Một số bài cần thêm mảng “quyết định” để dựng lại nghiệm, không chỉ giá trị tối ưu.

**Mẫu diễn đạt nên viết ra trước code:**

```text
State:
    dp[i][...] = ý nghĩa chính xác và phạm vi các lựa chọn.

Transition:
    dp[state] = phép kết hợp của những tiền nhiệm hợp lệ.

Base:
    các trạng thái đã biết trực tiếp; các trạng thái không thể đạt.

Order:
    thứ tự duyệt bảo đảm tiền nhiệm được tính trước.

Answer:
    ô hoặc tập ô cho đáp án sau khi xử lý toàn bộ input.
```

Một công thức chuyển thiếu **điều kiện áp dụng** có thể truy cập chỉ số âm, dùng vật quá sức chứa, đi xuyên vật cản hoặc tái sử dụng vật mà đề cấm.

## 3. Năm kiểu giá trị cơ sở dễ nhầm

| Loại bài DP | Ý nghĩa trạng thái | Cơ sở thường gặp | Vì sao |
|---|---|---|---|
| Đếm số cách | `ways[x]` = số cách đạt x | `ways[0]=1` | Có một cách rỗng |
| Chi phí nhỏ nhất | `cost[x]` = chi phí tối thiểu đạt x | `cost[0]=0`, trạng thái chưa đạt `INF` | Không làm gì tốn 0; đường không có không được chọn |
| Giá trị lớn nhất với quyền **không chọn** | `best[0][c]` | `0` | Không có vật ⇒ chọn rỗng, giá trị 0 |
| Tối đa hóa nhưng **phải chọn/đạt chính xác** | `best[x]` | Có thể cần `−INF` cho x không đạt | Không được biến phương án vô hiệu thành giá trị 0 |
| Đường đi trên lưới có vật cản | `ways[r][c]` | Ô xuất phát hợp lệ có 1 cách; ô chặn có 0 | Ô xuất phát không cần đến từ ô trước |

Không có “một giá trị khởi tạo DP luôn đúng”. Ví dụ `0` phù hợp với **cực đại và được phép chọn rỗng**, nhưng sai cho **cực tiểu chi phí** nếu trạng thái chưa đạt bị xem nhầm là chi phí 0.

### 3.1. Giá trị bất khả thi khác trạng thái chưa tính

Đây là hai tình huống hoàn toàn khác:

- **Đã tính và biết không thể đạt:** ví dụ không đổi được tổng 7 bằng các đồng `{4,6}`.
- **Chưa tính giá trị:** ví dụ `memo[7]` chưa được đệ quy thăm tới.

Với top-down, nếu dùng `-1` làm sentinel “chưa tính”, phải chắc chắn đáp án hợp lệ **không thể** là `-1`. Nếu bài cho phép giá trị âm, hãy dùng mảng `boolean[] computed`, kiểu đóng hộp `Integer[]` với `null`, hoặc một trạng thái riêng.

Với min-DP, đặt `INF` và luôn **kiểm tra trước khi cộng**, vì `INF + cost` có thể tràn kiểu số. Một số bài có chi phí âm hợp lệ, nên cần phân biệt “không thể đạt” với số âm có nghĩa.

### 3.2. Cơ sở không phải lúc nào cũng ở chỉ số 0

Ở một bài giải đoạn `[l,r]`, trường hợp `l==r` có thể là cơ sở. Ở DP trên cây, node `null` có thể là cơ sở. Ở một trò chơi lấy lượt, không còn lượt đi có thể mang kết quả thắng/thua xác định. Trong DP dạng tiền tố, hàng hoặc cột `0` thường mô tả tiền tố rỗng; **không nhất thiết** là dòng code bắt đầu tính ở phần tử đầu.

Hãy phát biểu cơ sở theo **ý nghĩa bài toán** rồi mới chọn chỉ số mảng.

## 4. Ví dụ 1 — Đếm cách leo bậc thang: cơ sở `ways[0]=1`

**Bài toán:** có cầu thang gồm `n` bậc; ở mỗi bước được leo **1 hoặc 2 bậc**. Đếm số **chuỗi bước đi** dẫn chính xác đến bậc n.

**Trạng thái:**

`ways[i]` = số chuỗi bước 1 hoặc 2 có tổng đúng `i`, với `i>=0`.

**Phân tích bước cuối:**

- Nếu bước cuối dài 1, trước đó đã đến bậc `i-1`: có `ways[i-1]` cách.
- Nếu bước cuối dài 2, trước đó đã đến bậc `i-2`: có `ways[i-2]` cách.

Hai trường hợp **không giao nhau**, vì bước cuối là 1 hoặc 2. Tất cả đường đi hợp lệ phải thuộc một trong hai. Vì vậy:

`ways[i] = ways[i-1] + ways[i-2]`, với `i>=2`.

**Cơ sở:**

- `ways[0]=1`: đúng một chuỗi rỗng, không bước nào.
- `ways[1]=1`: chỉ chuỗi `[1]`.
- Đầu vào âm: không được định nghĩa trong bài này; báo lỗi thay vì thử truy cập `dp[-1]`.

### 4.1. Java 17: tính lặp với `BigInteger`

Lưu thành **StairWaysDpDemo.java**:

```java
import java.math.BigInteger;

public class StairWaysDpDemo {
    static BigInteger countWays(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("Negative number of stairs");
        }
        if (n == 0 || n == 1) {
            return BigInteger.ONE;
        }

        BigInteger prev2 = BigInteger.ONE; // ways[0]
        BigInteger prev1 = BigInteger.ONE; // ways[1]

        for (int i = 2; i <= n; i++) {
            BigInteger current = prev1.add(prev2);
            prev2 = prev1;
            prev1 = current;
        }
        return prev1;
    }

    public static void main(String[] args) {
        System.out.println("n=0: " + countWays(0));
        System.out.println("n=1: " + countWays(1));
        System.out.println("n=5: " + countWays(5));
        System.out.println("n=10: " + countWays(10));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 StairWaysDpDemo.java
java StairWaysDpDemo
```

Stdout:

```text
n=0: 1
n=1: 1
n=5: 8
n=10: 89
```

Với `n=5`, có tám chuỗi bước hợp lệ. Sử dụng `BigInteger` tránh **tràn số kết quả** vốn xảy ra nếu n lớn mà dùng `int`/`long`. Phân tích dưới mô hình coi phép cộng số nhỏ là hằng số có `O(n)` lần lặp, bộ nhớ **hai giá trị DP**. Khi `BigInteger` dài hơn theo n, chi phí mỗi phép cộng và số bit lưu **không còn O(1)**; hãy phân biệt số lượt chuyển với độ phức tạp bit.

**Bất biến:** trước lượt `i`, `prev2=ways[i-2]` và `prev1=ways[i-1]`. Tính `current` theo quan hệ chuyển, dịch hai biến sang trạng thái kế tiếp. Sau lượt `n`, `prev1=ways[n]`.

### 4.2. Vì sao `ways[0]=0` làm sai cả dãy?

Nếu đặt sai `ways[0]=0` nhưng vẫn đặt `ways[1]=1`, ta có `ways[2]=1` (chỉ tính `[1,1]`, bỏ `[2]`), trong khi đáp án đúng là 2. Cơ sở “chuỗi rỗng là một cách” cần thiết để mọi cách có bước cuối 2 được đếm.

**Câu hỏi kiểm tra:** nếu đề chỉ hỏi có tồn tại đường đi không, trạng thái cần là boolean; nếu đề yêu cầu tổng số **bậc có thể đặt chân lên** thay vì chuỗi bước, công thức cần được xét lại. Ngữ nghĩa trạng thái quyết định công thức.

## 5. Ví dụ 2 — Đếm đường đi lưới với vật cản

**Bài toán:** một lưới `rows × cols`, ô `0` đi được, ô `1` bị chặn. Xuất phát tại `(0,0)`, mỗi bước chỉ đi **xuống** hoặc **sang phải**, đếm số đường đi đến ô dưới cùng bên phải.

**Trạng thái:**

`ways[r][c]` = số đường đi từ `(0,0)` đến ô `(r,c)` tuân thủ quy tắc, với chỉ số bắt đầu từ 0.

**Chuyển:**

- Nếu `(r,c)` bị chặn, `ways[r][c]=0`.
- Nếu là ô xuất phát và không chặn, `ways[0][0]=1`.
- Với ô đi được khác ô xuất phát:

`ways[r][c] = ways[r-1][c] + ways[r][c-1]`.

Các chỉ số ngoài lưới được hiểu là có **0 cách**, không được truy cập mảng âm. Mọi đường đi đến ô `(r,c)` phải có bước cuối đi từ **trên** hoặc **trái**, hai trường hợp phân biệt và bao phủ mọi đường hợp lệ.

**Thứ tự tính:** duyệt hàng từ trên xuống, cột từ trái sang phải; khi xét `(r,c)`, ô trên và ô trái (nếu tồn tại) đều đã được tính.

### 5.1. Java 17: lưới có vật cản

Lưu thành **GridPathsDpDemo.java**:

```java
import java.math.BigInteger;
import java.util.Objects;

public class GridPathsDpDemo {
    // 0 = ô đi được, 1 = ô bị chặn.
    static BigInteger countPaths(int[][] grid) {
        Objects.requireNonNull(grid, "grid");
        int rows = grid.length;
        if (rows == 0) {
            return BigInteger.ZERO;
        }
        Objects.requireNonNull(grid[0], "row 0");
        int cols = grid[0].length;
        if (cols == 0) {
            return BigInteger.ZERO;
        }

        BigInteger[][] ways = new BigInteger[rows][cols];
        for (int r = 0; r < rows; r++) {
            if (grid[r] == null || grid[r].length != cols) {
                throw new IllegalArgumentException("Not a rectangular grid");
            }
            for (int c = 0; c < cols; c++) {
                int cell = grid[r][c];
                if (cell != 0 && cell != 1) {
                    throw new IllegalArgumentException("Cell must be 0 or 1");
                }
                if (cell == 1) {
                    ways[r][c] = BigInteger.ZERO;
                } else if (r == 0 && c == 0) {
                    ways[r][c] = BigInteger.ONE;
                } else {
                    BigInteger fromTop = r > 0
                            ? ways[r - 1][c] : BigInteger.ZERO;
                    BigInteger fromLeft = c > 0
                            ? ways[r][c - 1] : BigInteger.ZERO;
                    ways[r][c] = fromTop.add(fromLeft);
                }
            }
        }
        return ways[rows - 1][cols - 1];
    }

    public static void main(String[] args) {
        int[][] grid = {
            {0, 0, 0},
            {0, 1, 0},
            {0, 0, 0}
        };
        System.out.println("Center blocked: " + countPaths(grid));
        System.out.println("Start blocked: " + countPaths(new int[][]{{1}}));
        System.out.println("One clear cell: " + countPaths(new int[][]{{0}}));
        System.out.println("Empty grid: " + countPaths(new int[0][0]));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 GridPathsDpDemo.java
java GridPathsDpDemo
```

Stdout:

```text
Center blocked: 2
Start blocked: 0
One clear cell: 1
Empty grid: 0
```

Lưới `3×3` với ô giữa bị chặn có hai đường đi: men theo cạnh trên rồi xuống, hoặc men theo cạnh trái rồi sang phải. Ví dụ này tính **số đường đi**, không phải đường ngắn nhất; nếu được phép đi lên/trái tự do, đồ thị trạng thái có thể xuất hiện chu trình và công thức quét lưới một lượt không còn đúng.

**Chi phí:** có `rows·cols` ô, mỗi ô thực hiện một số hữu hạn phép lấy/chuyển trạng thái; số lần chuyển là `O(rows·cols)`, bảng chứa `O(rows·cols)` giá trị. Vì dùng `BigInteger`, độ phức tạp bit của phép cộng phụ thuộc kích thước số đường đi. Nếu chỉ cần kết quả modulo `M>0`, có thể lưu `int`/`long` và cộng có kiểm soát tràn.

### 5.2. Cơ sở và biên không thể nhập nhằng

- Ô xuất phát **đi được**: `1`, không phải `0`.
- Ô xuất phát **bị chặn**: `0`.
- Ô đích **bị chặn**: `0` do phép chuyển của ô chặn.
- Ô ngoài lưới: đóng góp `0`.
- Lưới rỗng: ví dụ quy ước trả `0`, không phải một đường đi.

Một code sai thường khởi tạo `ways[0][0]=1` **trước khi kiểm tra vật cản**, khiến cả ô xuất phát bị chặn vẫn có một đường đi giả.

## 6. Ví dụ 3 — Đổi tiền ít đồng nhất: `INF` và trạng thái không đạt

**Bài toán:** có mệnh giá nguyên dương `coins[]`, được dùng **không giới hạn số đồng mỗi mệnh giá**, cần tạo đúng tổng `amount` bằng số đồng ít nhất.

**Trạng thái:**

`dp[x]` = số đồng **ít nhất** để tạo chính xác tổng `x` với những mệnh giá được phép dùng. Nếu không thể tạo, `dp[x]=INF`.

**Quyết định cuối:** nếu đồng tiền cuối có mệnh giá `c`, trước đó phải tạo đúng `x-c` bằng số đồng tối thiểu. Do đó:

`dp[x] = min(dp[x-c] + 1)` trên mọi `c>0`, `c<=x` và `dp[x-c]` khả thi.

**Cơ sở:**

- `dp[0]=0`: không cần đồng nào để tạo tổng 0.
- `dp[x>0]=INF` trước khi xét các chuyển.
- `dp[x]` không có nghĩa nếu `x<0`; chỉ xét `c<=x`.

**Ví dụ:** `{1,3,4}`, `amount=6`.

```text
dp[0] = 0
dp[1] = 1  (1)
dp[2] = 2  (1 + 1)
dp[3] = 1  (3)
dp[4] = 1  (4)
dp[5] = 2  (4 + 1)
dp[6] = 2  (3 + 3)
```

Quy tắc tham lam “lấy đồng lớn nhất trước” cho `4+1+1` (3 đồng), nhưng DP xét mọi lựa chọn đồng cuối, tìm đúng `3+3` (2 đồng).

### 6.1. Java 17: giá trị tối ưu và tái dựng nghiệm

Lưu thành **MinCoinsDpDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class MinCoinsDpDemo {
    record Result(int count, List<Integer> chosen) {}

    static Result solve(int[] coins, int amount) {
        Objects.requireNonNull(coins, "coins");
        if (amount < 0 || amount == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Invalid amount");
        }
        for (int c : coins) {
            if (c <= 0) {
                throw new IllegalArgumentException("Coin must be positive");
            }
        }

        // Nếu số đồng tồn tại, không cần nhiều hơn amount
        // khi mọi mệnh giá là số nguyên dương.
        int inf = amount + 1;
        int[] dp = new int[amount + 1];
        int[] lastCoin = new int[amount + 1];
        Arrays.fill(dp, inf);
        dp[0] = 0;

        for (int x = 1; x <= amount; x++) {
            for (int coin : coins) {
                if (coin <= x && dp[x - coin] != inf) {
                    int candidate = dp[x - coin] + 1;
                    if (candidate < dp[x]) {
                        dp[x] = candidate;
                        lastCoin[x] = coin;
                    }
                }
            }
        }

        if (dp[amount] == inf) {
            return new Result(-1, List.of());
        }

        List<Integer> chosen = new ArrayList<>();
        int remaining = amount;
        while (remaining > 0) {
            int coin = lastCoin[remaining];
            chosen.add(coin);
            remaining -= coin;
        }
        return new Result(dp[amount], chosen);
    }

    public static void main(String[] args) {
        Result result = solve(new int[]{1, 3, 4}, 6);
        System.out.println("Min coins for 6: " + result.count());
        System.out.println("Coins: " + result.chosen());
        System.out.println("Impossible 7: "
                + solve(new int[]{4, 6}, 7).count());
        System.out.println("Zero amount: "
                + solve(new int[]{4, 6}, 0).count());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MinCoinsDpDemo.java
java MinCoinsDpDemo
```

Stdout:

```text
Min coins for 6: 2
Coins: [3, 3]
Impossible 7: -1
Zero amount: 0
```

`lastCoin[x]` ghi **đồng cuối cùng của một phương án tối ưu** để tái dựng nghiệm bằng cách liên tục trừ mệnh giá đã lưu. Trường hợp không đạt trả số đồng `-1`, danh sách rỗng. Trường hợp tổng 0 trả `0`, cũng có danh sách rỗng nhưng mang ý nghĩa **khả thi**, khác với không đạt.

**Vì sao `INF=amount+1` hợp lệ ở đây?** Với mệnh giá **nguyên dương** và mục tiêu tổng **không âm**, nếu tạo được tổng x, số đồng không thể lớn hơn x, bởi mỗi đồng góp ít nhất 1. Do đó với `x<=amount`, `amount+1` lớn hơn mọi số đồng trong một nghiệm hợp lệ. Khi amount quá lớn, giới hạn độ dài mảng/bộ nhớ vẫn có thể gây lỗi; ví dụ từ chối `Integer.MAX_VALUE` để tránh tràn khi cộng 1, nhưng **không cam kết** mọi amount thấp hơn đều cấp phát được trên JVM.

**Không cộng vô điều kiện với INF:** nhánh `dp[x-coin] != inf` loại bỏ trạng thái không khả thi trước khi lấy `+1`. Nếu dùng `Integer.MAX_VALUE` làm INF, biểu thức `INF+1` có thể tràn thành số âm rất nhỏ và đánh lừa phép `min`.

**Độ phức tạp:** với `m=coins.length`, `A=amount`, có `A` trạng thái và tối đa `m` chuyển mỗi trạng thái: thời gian `O(A·m)` cộng chi phí tái dựng tối đa `O(A)`, bộ nhớ `O(A)`. Đây là thuật toán **giả đa thức** theo trị số `A`, không phải theo số bit để ghi A.

### 6.2. Phân biệt hai bài đổi tiền

Nếu đề hỏi **ít đồng nhất**, chuyển là `min` và cơ sở `dp[0]=0`. Nếu hỏi **có bao nhiêu cách đổi**, chuyển là phép cộng `+`, cơ sở `ways[0]=1`, và phải xác định **thứ tự đồng có phân biệt không**.

- Đếm **tổ hợp** không quan tâm thứ tự đồng: thường duyệt **đồng bên ngoài**, **tổng tăng dần bên trong**.
- Đếm **chuỗi đồng** có quan tâm thứ tự: thường duyệt **tổng bên ngoài**, thử đồng bên trong.

Ví dụ với mệnh giá `{1,2}`, tổng 3:

- Tổ hợp: `{1,1,1}`, `{1,2}` ⇒ **2** cách.
- Chuỗi: `[1,1,1]`, `[1,2]`, `[2,1]` ⇒ **3** cách.

Hai truy hồi có thể trông giống nhau nhưng **thứ tự cập nhật và ngữ nghĩa “cách”** làm đáp án khác.

## 7. Ví dụ 4 — Ba lô 0/1 so với ba lô không giới hạn

**Bài toán 0/1:** có `n` vật, vật `i` nặng `weight[i]>0`, giá trị `value[i]>=0`, sức chứa `W`. Mỗi vật chỉ được chọn **tối đa một lần**; chọn một tập vật không vượt trọng lượng `W`, cực đại tổng giá trị.

Một trạng thái dễ chứng minh:

`dp[i][c]` = giá trị lớn nhất khi chỉ xét **i vật đầu** và sức chứa **không quá c**.

**Điều kiện cơ sở:**

`dp[0][c]=0` với mọi `0<=c<=W`; không có vật nào để lấy. Nếu mọi trọng lượng dương thì `dp[i][0]=0`.

**Chuyển từ quyết định về vật thứ i:**

- **Không lấy vật i:** `dp[i-1][c]`.
- **Lấy vật i**, chỉ nếu `weight[i]<=c`: `dp[i-1][c-weight[i]] + value[i]`.

Từ đó:

`dp[i][c] = max(dp[i-1][c], dp[i-1][c-weight[i]]+value[i])` nếu vật vừa sức; nếu không, `dp[i][c]=dp[i-1][c]`.

Cả hai trường hợp đều dùng hàng `i-1` vì vật i **không thể được dùng lại**.

### 7.1. Nén bảng từ 2D xuống 1D: chiều vòng lặp quyết định ngữ nghĩa

Đặt `dp[c]` là giá trị tối ưu đã xử lý **tập vật ở những lượt trước** (theo nghĩa 0/1). Khi xử lý một vật:

```text
for c = W xuống weight[i]:
    dp[c] = max(dp[c], dp[c-weight[i]] + value[i])
```

**Duyệt sức chứa GIẢM DẦN** giữ được bất biến: khi tính `dp[c]`, giá trị `dp[c-weight[i]]` ở chỉ số nhỏ hơn **chưa được cập nhật bởi vật i hiện tại**, nên vật i chỉ xuất hiện một lần.

Nếu đổi thành duyệt **TĂNG DẦN**:

```text
for c = weight[i] lên W:
    dp[c] = max(dp[c], dp[c-weight[i]] + value[i])
```

thì `dp[c-weight[i]]` có thể đã chứa chính vật i vừa thêm ở lượt hiện tại. Ta đã chuyển sang bài **unbounded knapsack**: mỗi loại vật có thể được lấy **nhiều lần**. Đây là ví dụ điển hình cho việc **công thức trông giống nhau nhưng phụ thuộc cập nhật khác**.

### 7.2. Java 17: cùng input, khác hướng vòng lặp

Lưu thành **KnapsackTransitionsDemo.java**:

```java
import java.util.Objects;

public class KnapsackTransitionsDemo {
    static void validate(int[] weight, int[] value, int capacity) {
        Objects.requireNonNull(weight, "weight");
        Objects.requireNonNull(value, "value");
        if (weight.length != value.length || capacity < 0) {
            throw new IllegalArgumentException("Invalid dimensions");
        }
        for (int i = 0; i < weight.length; i++) {
            if (weight[i] <= 0 || value[i] < 0) {
                throw new IllegalArgumentException("Invalid item");
            }
        }
    }

    static int best01(int[] weight, int[] value, int capacity) {
        validate(weight, value, capacity);
        int[] dp = new int[capacity + 1]; // Chọn rỗng có giá trị 0.

        for (int i = 0; i < weight.length; i++) {
            for (int c = capacity; c >= weight[i]; c--) {
                dp[c] = Math.max(
                    dp[c], dp[c - weight[i]] + value[i]);
            }
        }
        return dp[capacity];
    }

    static int bestUnbounded(int[] weight, int[] value,
                             int capacity) {
        validate(weight, value, capacity);
        int[] dp = new int[capacity + 1];

        for (int i = 0; i < weight.length; i++) {
            for (int c = weight[i]; c <= capacity; c++) {
                dp[c] = Math.max(
                    dp[c], dp[c - weight[i]] + value[i]);
            }
        }
        return dp[capacity];
    }

    public static void main(String[] args) {
        int[] weight = {2, 3};
        int[] value = {3, 4};

        System.out.println("0/1 capacity 4: "
                + best01(weight, value, 4));
        System.out.println("Unbounded capacity 4: "
                + bestUnbounded(weight, value, 4));
        System.out.println("0/1 capacity 0: "
                + best01(weight, value, 0));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 KnapsackTransitionsDemo.java
java KnapsackTransitionsDemo
```

Stdout:

```text
0/1 capacity 4: 4
Unbounded capacity 4: 6
0/1 capacity 0: 0
```

Với sức chứa 4:

- **0/1:** chỉ có thể lấy vật nặng 2 giá trị 3 **hoặc** vật nặng 3 giá trị 4; kết quả **4**.
- **Unbounded:** có thể lấy **hai bản sao** vật nặng 2, tổng trọng lượng 4 và giá trị **6**.

**Phân tích:** `n` vật, `W+1` mức sức chứa, mỗi cặp có `O(1)` chuyển theo mô hình số nguyên máy. Thời gian `O(nW)`, bộ nhớ `O(W)`. Nếu giá trị có thể cộng vượt miền `int`, dùng `long` hoặc kiểu số phù hợp và kiểm tra giới hạn. Với `capacity=Integer.MAX_VALUE`, cấp `capacity+1` còn có nguy cơ tràn `int`; API thực tế cần giới hạn sức chứa bằng tài nguyên và kiểu chỉ số.

**Tính đúng nén 1D:** sau khi xử lý i vật, `dp[c]` bằng tối ưu khi chỉ xét i vật theo ràng buộc đã nêu. Khi xử lý vật kế tiếp với c giảm, nhánh lấy vật luôn đọc giá trị tiền nhiệm ở trạng thái **chưa dùng vật mới**; phép `max` xét đủ hai trường hợp lấy/không lấy. Vòng tăng của unbounded hợp lệ vì nhánh thêm vật có thể tiếp tục cộng nhiều bản sao của cùng một loại.

### 7.3. “Không quá W” khác “chính xác W”

Trong ví dụ, `dp[c]` nghĩa là dùng **tổng trọng lượng <= c**, vì thế `dp[c]=0` ban đầu hợp lệ khi chọn rỗng. Nếu đề yêu cầu **tổng trọng lượng đúng bằng W**, một số sức chứa không đạt được và phải dùng trạng thái không khả thi (`−INF` khi cực đại, với kiểm tra trước khi cộng). Giữ toàn bộ mảng bằng 0 trong bài **chính xác W** sẽ tạo nghiệm giả.

## 8. Ví dụ 5 — Dãy con chung dài nhất (LCS): cơ sở tiền tố rỗng

**Bài toán:** cho hai chuỗi `a`, `b`; tìm **độ dài dãy con chung dài nhất** (*longest common subsequence*, LCS). Dãy con cho phép bỏ một số ký tự nhưng **giữ thứ tự tương đối**, không cần liền kề.

**Trạng thái:**

`dp[i][j]` = độ dài LCS giữa **i ký tự đầu** của `a` và **j ký tự đầu** của `b`.

Lưu ý i và j là **độ dài tiền tố**, không phải chỉ số ký tự; ký tự cuối của tiền tố tương ứng là `a.charAt(i-1)` và `b.charAt(j-1)`.

**Cơ sở:** tiền tố rỗng không có dãy con chung khác rỗng:

`dp[0][j]=0` và `dp[i][0]=0`.

**Chuyển:**

- Nếu hai ký tự cuối **bằng nhau**, có thể chọn chúng làm cuối một LCS:  
  `dp[i][j]=dp[i-1][j-1]+1`.
- Nếu hai ký tự cuối **khác nhau**, một LCS không thể dùng đồng thời cả hai ký tự cuối; bỏ ít nhất một phía:  
  `dp[i][j]=max(dp[i-1][j], dp[i][j-1])`.

**Thứ tự:** i tăng từ 1, j tăng từ 1; tất cả trạng thái tiền nhiệm ở hàng trên, cột trái hoặc đường chéo trên-trái đã được tính.

### 8.1. Java 17: tính độ dài và truy vết một LCS

Lưu thành **LcsDpDemo.java**:

```java
import java.util.Objects;

public class LcsDpDemo {
    static String oneLcs(String a, String b) {
        Objects.requireNonNull(a, "a");
        Objects.requireNonNull(b, "b");

        int n = a.length();
        int m = b.length();
        int[][] dp = new int[n + 1][m + 1];

        for (int i = 1; i <= n; i++) {
            for (int j = 1; j <= m; j++) {
                if (a.charAt(i - 1) == b.charAt(j - 1)) {
                    dp[i][j] = dp[i - 1][j - 1] + 1;
                } else {
                    dp[i][j] = Math.max(
                            dp[i - 1][j], dp[i][j - 1]);
                }
            }
        }

        // Truy vết từ (n,m) về các trạng thái cơ sở.
        StringBuilder reversed = new StringBuilder();
        int i = n, j = m;
        while (i > 0 && j > 0) {
            if (a.charAt(i - 1) == b.charAt(j - 1)) {
                reversed.append(a.charAt(i - 1));
                i--;
                j--;
            } else if (dp[i - 1][j] >= dp[i][j - 1]) {
                i--;
            } else {
                j--;
            }
        }
        return reversed.reverse().toString();
    }

    public static void main(String[] args) {
        String first = oneLcs("ABCBDAB", "BDCABA");
        System.out.println("LCS length: " + first.length());
        System.out.println("One LCS: " + first);
        System.out.println("Empty LCS: [" + oneLcs("", "XYZ") + "]");
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 LcsDpDemo.java
java LcsDpDemo
```

Stdout:

```text
LCS length: 4
One LCS: BCBA
Empty LCS: []
```

Trong ví dụ, có thể có **nhiều LCS** dài 4. Chính sách khi hòa `dp[i-1][j] >= dp[i][j-1]` chọn đi lên, tạo ra một LCS cụ thể (`BCBA`). Nếu đổi chính sách hòa, vẫn có thể nhận dãy khác cùng độ dài tối ưu.

**Vì sao truy vết đúng?** Khi hai ký tự cuối bằng nhau, chuyển chéo cộng 1 cho một ký tự thuộc lời giải; khi khác nhau, ta di chuyển tới trạng thái tiền nhiệm có cùng độ dài tối ưu. Số ký tự đã thu đúng bằng `dp[n][m]` và xuất hiện theo thứ tự khi đảo lại chuỗi đã xây ngược.

**Chi phí:** `O(nm)` phép so sánh/chuyển và `O(nm)` ô nhớ; truy vết tối đa `O(n+m)` bước. Nếu chỉ cần **độ dài** và không cần truy vết, có thể nén còn hai hàng `O(min(n,m))` ô bằng cách chọn chiều ngắn làm chiều cột. Nhưng nếu phải dựng lại một LCS, không thể tùy tiện bỏ toàn bộ thông tin tiền nhiệm mà vẫn dùng nguyên cách truy vết trên.

**Giới hạn văn bản:** `String.length()` và `charAt()` trong Java làm việc trên **đơn vị UTF-16**, không phải lúc nào cũng tương ứng một ký tự Unicode theo góc nhìn người dùng. Nếu yêu cầu LCS theo **code point** hoặc cụm ký tự có dấu, phải chuyển biểu diễn và chuẩn hóa phù hợp.

### 8.2. Chứng minh chuyển của LCS

Lập luận theo cặp độ dài `(i,j)`:

- Khi một tiền tố rỗng, đáp án 0 là hiển nhiên.
- Nếu `a[i-1]==b[j-1]`, có tồn tại một LCS của hai tiền tố dùng hai ký tự cuối tương ứng; thêm ký tự đó vào LCS tối ưu của hai tiền tố ngắn hơn cho độ dài tối ưu, nên bằng `dp[i-1][j-1]+1`.
- Nếu khác nhau, một dãy con chung không thể đồng thời kết thúc bằng cả hai ký tự cuối không bằng nhau; ít nhất một trong hai ký tự cuối bị bỏ. Vì vậy nghiệm thuộc một trong hai bài con `(i-1,j)` hoặc `(i,j-1)`; lấy `max` là vừa đủ vừa không bỏ nghiệm tối ưu.

Chứng minh **không chỉ nói** “vì code xét hai nhánh nên đúng”; nó phải liên hệ hai nhánh với **mọi dãy con chung có thể có**.

## 9. Ví dụ 6 — Khoảng cách chỉnh sửa: cơ sở không bằng nhau

**Bài toán:** biến chuỗi `source` thành `target` bằng ba thao tác, mỗi thao tác giá 1:

- Chèn một ký tự.
- Xóa một ký tự.
- Thay một ký tự bằng ký tự khác.

Cần **số thao tác nhỏ nhất** (*Levenshtein edit distance*).

**Trạng thái:**

`dp[i][j]` = số thao tác nhỏ nhất để biến **i ký tự đầu** của `source` thành **j ký tự đầu** của `target`.

**Điều kiện cơ sở:**

- `dp[0][j]=j`: từ chuỗi rỗng, phải **chèn j ký tự**.
- `dp[i][0]=i`: để thành chuỗi rỗng, phải **xóa i ký tự**.
- `dp[0][0]=0`.

**Chuyển:**

Nếu ký tự cuối bằng nhau, không cần sửa ký tự cuối:

`dp[i][j]=dp[i-1][j-1]`.

Nếu khác nhau:

`dp[i][j]=1+min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])`.

Tương ứng **xóa** ký tự cuối của nguồn, **chèn** ký tự cuối của đích hoặc **thay** ký tự cuối.

### 9.1. Java 17: edit distance

Lưu thành **EditDistanceDpDemo.java**:

```java
import java.util.Objects;

public class EditDistanceDpDemo {
    static int distance(String source, String target) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(target, "target");

        int n = source.length();
        int m = target.length();
        int[][] dp = new int[n + 1][m + 1];

        for (int i = 0; i <= n; i++) {
            dp[i][0] = i;
        }
        for (int j = 0; j <= m; j++) {
            dp[0][j] = j;
        }

        for (int i = 1; i <= n; i++) {
            for (int j = 1; j <= m; j++) {
                if (source.charAt(i - 1) == target.charAt(j - 1)) {
                    dp[i][j] = dp[i - 1][j - 1];
                } else {
                    dp[i][j] = 1 + Math.min(
                            dp[i - 1][j],
                            Math.min(dp[i][j - 1], dp[i - 1][j - 1]));
                }
            }
        }
        return dp[n][m];
    }

    public static void main(String[] args) {
        System.out.println("kitten -> sitting: "
                + distance("kitten", "sitting"));
        System.out.println("empty -> abc: " + distance("", "abc"));
        System.out.println("same -> same: "
                + distance("same", "same"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 EditDistanceDpDemo.java
java EditDistanceDpDemo
```

Stdout:

```text
kitten -> sitting: 3
empty -> abc: 3
same -> same: 0
```

Một chuỗi sửa từ `"kitten"` sang `"sitting"` là **thay** `k→s`, **thay** `e→i`, rồi **chèn** `g`: ba thao tác. Bảng DP tìm số nhỏ nhất, không nhất thiết tự lưu **chuỗi thao tác**; muốn tái dựng phải đi ngược bảng và kiểm tra chuyển đã tạo giá trị.

**Chi phí:** `O(nm)` thời gian và `O(nm)` bộ nhớ, nơi n/m là độ dài chuỗi tính bằng đơn vị `char`. Nếu chỉ cần số thao tác, có thể nén bảng còn hai hàng `O(min(n,m))` bằng cách chọn chiều ngắn làm chiều cột và dùng biến giữ giá trị chéo cũ. Không dùng thuật toán này để tự khẳng định khoảng cách theo ngữ nghĩa tiếng Việt/Unicode grapheme mà không định nghĩa trước đơn vị ký tự.

### 9.2. Vì sao không đặt hàng đầu bằng 0 như LCS?

Cả LCS và edit distance đều có `dp[i][j]` trên **hai tiền tố chuỗi**, nhưng ý nghĩa khác:

- LCS với một tiền tố rỗng: độ dài dãy con chung là **0**.
- Edit distance từ tiền tố rỗng đến một tiền tố dài j: phải **chèn j ký tự**.

Việc bê nguyên điều kiện cơ sở của LCS sang edit distance làm một loạt ô đầu sai, kéo theo phần lớn bảng còn lại sai. **Tên và kích thước bảng không quyết định base; nghĩa của trạng thái mới quyết định base.**

## 10. Top-down và bottom-up: cùng công thức, khác cách đánh giá

Sau khi có `dp[state]` và quan hệ chuyển, ta có hai phong cách.

### 10.1. Top-down với memoization

Một hàm `solve(state)`:

1. Nếu state là cơ sở, trả giá trị cơ sở.
2. Nếu state đã tính, trả cache.
3. Tính các trạng thái tiền nhiệm bằng lời gọi đệ quy.
4. Kết hợp theo công thức chuyển, lưu cache rồi trả.

Mẫu giả mã:

```text
solve(s):
    if s là trạng thái cơ sở:
        return base(s)
    if computed[s]:
        return memo[s]

    result = giá trị khởi tạo hợp với bài toán
    for p trong các tiền nhiệm hợp lệ của s:
        result = combine(result, solve(p), chi phí chuyển)

    computed[s] = true
    memo[s] = result
    return result
```

`computed` tách **chưa tính** khỏi **đã tính và có giá trị 0 hoặc âm**. Nếu đồ thị phụ thuộc có chu trình, đệ quy có thể vô hạn; DP chuẩn cần phụ thuộc đi về các trạng thái nhỏ hơn hoặc một cách xử lý chu trình được chứng minh.

**Ưu điểm:** tính **những trạng thái thực sự cần** để lấy đáp án. **Nhược điểm:** có thể tốn stack sâu, tràn `StackOverflowError` nếu chuỗi phụ thuộc quá dài; chi phí lời gọi/hàm băm cũng cần xét.

### 10.2. Bottom-up với tabulation

Thay vì gọi đệ quy, đi qua các trạng thái theo một **thứ tự topo của phụ thuộc**:

```text
khởi tạo tất cả base
for s theo thứ tự sao cho mọi p của s đã tính:
    dp[s] = combine(dp[p] của các p hợp lệ)
return dp[target]
```

Trong coin change, `dp[x]` phụ thuộc `dp[x-c]` với `c>0`, nên duyệt **x tăng dần** là đúng. Trong lưới chỉ đi xuống/phải, `(r,c)` phụ thuộc ô trên/trái, nên duyệt hàng từ trên xuống và cột từ trái sang phải là đúng. Trong LCS, `(i,j)` phụ thuộc chỉ số i/j nhỏ hơn, nên hai vòng tăng dần là đúng.

**Không phải lúc nào duyệt `i` rồi `j` cũng đúng:** nếu một trạng thái phụ thuộc vào **giá trị lớn hơn**, phải đổi thứ tự hoặc định nghĩa lại trạng thái. Ví dụ DP đoạn `dp[l][r]` có thể cần tất cả các **đoạn ngắn hơn** trước; cách duyệt tự nhiên là theo **độ dài đoạn tăng dần**, rồi theo vị trí bắt đầu.

### 10.3. Số trạng thái chưa phải độ phức tạp cuối cùng

Nếu có `S` trạng thái cần tính và mỗi trạng thái xét tối đa `D` chuyển, thời gian thường là `O(S·D)` **chưa kể chi phí của một chuyển**. Bộ nhớ là `O(S)` khi lưu một giá trị trên mỗi trạng thái, cộng thông tin truy vết và stack nếu dùng memo.

Ví dụ:

- Đổi tiền: `S≈A`, `D≈m` mệnh giá ⇒ `O(A·m)`.
- LCS: `S≈nm`, `D≤3` ⇒ `O(nm)`.
- DP theo tập con: `S≈2^n`, mỗi state thử n lựa chọn ⇒ `O(n·2^n)` dù code dùng bitmask nhỏ gọn.
- Interval DP với trạng thái `dp[l][r]` có `O(n²)` trạng thái, nếu thử mọi điểm chia có `O(n)` chuyển ⇒ thường `O(n³)`.

Cần tách **số trạng thái**, **số chuyển** và **chi phí xử lý chuyển**. Không đánh đồng “một bảng 2D” với `O(n²)` nếu mỗi ô còn chạy vòng tìm kiếm `O(n)`.

## 11. DP trên đoạn: cơ sở là đoạn rỗng hoặc một phần tử

Xét bài **matrix-chain multiplication**: có n ma trận `A1,...,An`, ma trận `Ai` có kích thước `p[i-1] × p[i]`. Chọn cách đặt ngoặc nhân sao cho số phép nhân vô hướng ít nhất, **không** đổi thứ tự các ma trận.

**Trạng thái:**

`cost[l][r]` = số phép nhân nhỏ nhất để tính tích `A_l × ... × A_r`, với `1<=l<=r<=n`.

**Cơ sở:**

`cost[i][i]=0`: một ma trận đơn lẻ không cần nhân với ma trận khác.

**Chuyển qua điểm tách cuối `k`:**

`cost[l][r] = min_{l<=k<r} (cost[l][k] + cost[k+1][r] + p[l-1]*p[k]*p[r])`.

Tích hai kết quả bên trái và phải có số phép nhân vô hướng bằng tích ba kích thước trong công thức; cả hai đoạn con phải được tính tối ưu trước đó.

**Thứ tự:** duyệt `length=2..n`, với mỗi độ dài xét mọi `l`, `r=l+length-1`, thử `k=l..r-1`. Cơ sở độ dài 1 đã có; mọi đoạn con trong chuyển có **độ dài ngắn hơn** đoạn hiện tại.

**Ví dụ:** ba ma trận có kích thước `10×30`, `30×5`, `5×60`:

- `(A1×A2)×A3`: `10×30×5 + 10×5×60 = 1500+3000 = 4500`.
- `A1×(A2×A3)`: `30×5×60 + 10×30×60 = 9000+18000 = 27000`.

Do đó `cost[1][3]=4500`. Nếu chỉ chọn **nhân hai ma trận có một kích thước nhỏ** mà không xét điểm tách tối ưu của các đoạn, có thể bỏ phương án toàn cục tốt nhất.

Đoạn này minh họa quan hệ chuyển và cơ sở, **không phải** chương trình Java độc lập. Với các chiều rất lớn, phải tránh tràn khi tính tích ba kích thước (dùng `long`/số lớn và kiểm tra phù hợp).

**Chi phí:** `O(n²)` trạng thái và tối đa `O(n)` điểm chia mỗi trạng thái ⇒ `O(n³)` thời gian, `O(n²)` bộ nhớ.

## 12. DP trên đồ thị có hướng không chu trình (DAG)

Trong một **DAG**, có thể tính số đường đi hoặc chi phí tối ưu theo **thứ tự topo** của các đỉnh.

Ví dụ có đỉnh nguồn `s`, đặt:

`dist[v]` = độ dài ngắn nhất của một đường từ `s` đến `v`.

- **Cơ sở:** `dist[s]=0`; các đỉnh khác bắt đầu `INF`.
- **Chuyển/relax:** với cạnh `u→v` trọng số `w`, nếu `dist[u]` khả thi, cập nhật `dist[v]=min(dist[v], dist[u]+w)`.
- **Thứ tự:** duyệt `u` theo topo; mọi cạnh đi tới `v` đến từ một đỉnh xuất hiện trước `v`.

Đồ thị có **trọng số âm** vẫn có thể tính shortest path bằng DP topo nếu thật sự là **DAG**; không có chu trình nên không có vấn đề đường đi lặp vô hạn. Điều này khác với Dijkstra, nơi điều kiện cạnh **không âm** quan trọng.

**Không áp nguyên công thức một lượt cho đồ thị có chu trình:** nếu đồ thị không có topo, các phụ thuộc có thể tạo vòng, và cần thuật toán khác hoặc trạng thái bổ sung. DP hoạt động tốt khi ta xây được **thứ tự giải các phụ thuộc có hướng**.

Nếu chỉ muốn đếm số đường đi DAG, thay `min` bằng cộng số cách, đặt `ways[s]=1`; cập nhật theo cạnh `ways[v] += ways[u]`. Đây lại là ví dụ cơ sở **1** cho “một cách rỗng ở nguồn”, khác shortest path cơ sở **0** cho chi phí.

## 13. Tối ưu bộ nhớ mà không phá quan hệ chuyển

Có ba dạng phổ biến:

### 13.1. Chỉ cần một vài giá trị trước đó

Bài leo bậc chỉ cần `ways[i-1]` và `ways[i-2]`, nên hai biến đủ. Không cần mảng `ways[0..n]` nếu chỉ lấy số cách tại n và không cần truy vết.

### 13.2. Bảng 2D phụ thuộc hàng trước

LCS hoặc edit distance có thể tính với **hai hàng** nếu chỉ cần giá trị cuối. Nhưng khi tối ưu phải lưu đúng giá trị **đường chéo cũ** (`dp[i-1][j-1]`) trước khi nó bị ghi đè. Chỉ thay `int[][]` bằng `int[]` mà không điều chỉnh thứ tự và biến phụ có thể tạo công thức sai.

### 13.3. Mảng 1D cần đi xuôi hoặc ngược

0/1 knapsack: duyệt **c giảm dần** để mỗi vật dùng tối đa một lần. Unbounded knapsack: duyệt **c tăng dần** để cho phép dùng nhiều bản sao. Một thay đổi “tối ưu bộ nhớ” có thể vô tình **thay đổi ý nghĩa bài toán**, không chỉ tốc độ.

### 13.4. Khi cần truy vết nghiệm

Nếu chỉ lưu giá trị tối ưu, đôi khi không thể khôi phục nghiệm theo cách trực tiếp:

- Min coins: lưu `lastCoin[x]` hoặc tái kiểm tra mệnh giá thỏa `dp[x]=dp[x-coin]+1`.
- LCS: giữ bảng đầy đủ hoặc dùng thuật toán tái dựng đặc biệt; ví dụ trên đi ngược bảng `dp`.
- Knapsack: lưu quyết định từng vật hoặc duy trì bảng/trạng thái đủ để xác định đã lấy vật nào.
- Matrix chain: lưu `split[l][r]` để tái dựng dấu ngoặc.

**Bộ nhớ trả kết quả** cũng phải tính: nếu nghiệm chứa k phần tử, việc tạo danh sách output tự nó có thể cần `Ω(k)` vùng chứa, dù bảng DP đã nén.

## 14. Chứng minh tính đúng của một quan hệ chuyển

Một cách chứng minh thường dùng **quy nạp trên thứ tự phụ thuộc trạng thái**.

Mẫu tổng quát:

1. **Cơ sở:** mọi trạng thái đầu được khởi tạo đúng trực tiếp từ định nghĩa.
2. **Giả thiết quy nạp:** mọi trạng thái tiền nhiệm đã được tính đúng.
3. **Tính đủ của phân trường hợp:** mọi nghiệm hợp lệ của trạng thái hiện tại thuộc **ít nhất một** trường hợp được xét trong chuyển.
4. **Tính hợp lệ của mỗi chuyển:** mỗi cách kết hợp tiền nhiệm với quyết định mới tạo ra **một nghiệm hợp lệ** của trạng thái hiện tại.
5. **Chọn phép kết hợp đúng:** `min` chọn tối ưu chi phí nhỏ, `max` chọn tối ưu giá trị lớn, `sum` đếm các lớp nghiệm **không trùng lặp**, `or` kiểm tra có ít nhất một phương án.
6. **Thứ tự tính:** tiền nhiệm không tham chiếu ngược tới trạng thái chưa thể xác định; tất cả các trạng thái mục tiêu được tính sau cơ sở.
7. **Kết luận:** trạng thái đáp án được tính đúng theo định nghĩa.

### 14.1. Khi đếm số cách phải tránh đếm trùng

Nếu cộng số cách ở nhiều nhánh chuyển, các trường hợp phải **rời nhau** hoặc phải có cách loại bỏ đếm trùng. Với leo bậc, “bước cuối là 1” và “bước cuối là 2” rời nhau. Với đường đi lưới, “bước cuối từ trên” và “bước cuối từ trái” rời nhau. Nhưng nếu chia nghiệm bằng hai đặc điểm có thể **đồng thời** đúng, cộng `waysA+waysB` sẽ đếm một nghiệm hai lần.

### 14.2. Khi cực tiểu phải tránh nghiệm ảo

Nếu `INF` đại diện “chưa thể đạt”, một chuyển phải đọc **tiền nhiệm khả thi** trước khi cộng chi phí. Nếu dùng `dp[x]=0` cho tất cả x trong bài min coins, ứng viên từ một trạng thái không đạt sẽ có chi phí 1, khiến hàng loạt tổng bị coi là khả thi sai.

### 14.3. Khi tối đa hóa phải biết có được bỏ chọn không

Nếu bài knapsack cho phép chọn **không gì**, hàng cơ sở 0 là nghiệm hợp lệ. Nếu đề yêu cầu **chọn ít nhất một vật** hay **đúng trọng lượng W**, đặt mọi trạng thái 0 có thể trả lời sai. Cần mở rộng trạng thái hoặc dùng `−INF` cho trạng thái không đạt.

### 14.4. Tính dừng của top-down

Mỗi chuyển đệ quy phải tiến về **trạng thái được xếp thấp hơn theo một đại lượng không thể giảm mãi** (ví dụ tổng x giảm, độ dài tiền tố giảm, kích thước đoạn giảm). Nếu `coin=0` trong min coins, chuyển `dp[x]→dp[x]` tạo vòng phụ thuộc; vì thế ví dụ bắt buộc mệnh giá **dương**. Kiểm tra điều kiện này là phần của **chứng minh dừng**, không chỉ xác thực dữ liệu.

## 15. Lỗi thường gặp khi thiết kế DP

### 15.1. Định nghĩa trạng thái không rõ “chính xác” hay “không quá”

`dp[c]` là tối ưu khi dùng **đúng c** trọng lượng hay **không vượt c**? Hai định nghĩa có cơ sở và trạng thái bất khả thi khác nhau. Nếu không ghi rõ, rất dễ để tất cả ô mặc định 0 rồi sinh nghiệm không hợp lệ.

### 15.2. Chọn trạng thái thiếu thông tin

Ví dụ một trò chơi có lượt hiện tại quyết định các nước đi được phép. Nếu chỉ lưu `dp[position]` mà không lưu `turn`, hai tình huống khác nhau có thể bị nhập làm một. Cần chứng minh rằng những trạng thái được gộp có **cùng tương lai và cùng mục tiêu**.

### 15.3. Viết chuyển chỉ cho một lựa chọn

Min coins có thể dùng đồng cuối bất kỳ; chỉ thử đồng lớn nhất là tham lam, không phải DP xét toàn bộ lựa chọn. 0/1 knapsack phải xét **lấy và không lấy** vật. Một chuyển thiếu trường hợp có thể bỏ nghiệm tối ưu.

### 15.4. Viết chuyển tạo nghiệm không hợp lệ

Không kiểm tra `coin<=x` dẫn tới chỉ số âm; không kiểm tra `weight<=capacity` có thể lấy vật quá sức; bỏ kiểm tra vật cản tạo đường đi xuyên tường. Luôn ghi điều kiện của chuyển **trước** khi tính toán.

### 15.5. Dùng giá trị cơ sở sai

- Đếm cách mà đặt `ways[0]=0` có thể triệt tiêu tất cả cách.
- Min coins mà đặt `dp[x>0]=0` tạo chi phí ảo.
- Edit distance mà đặt hàng/cột đầu 0 thay vì i/j sẽ đánh giá sai chuỗi rỗng.
- 0/1 exact capacity mà đặt mọi sức chứa là 0 khiến trọng lượng không đạt bị xem là nghiệm hợp lệ.

### 15.6. Đổi hướng vòng lặp khi nén DP

Trong knapsack 0/1, duyệt sức chứa tăng làm vật được dùng lại trong cùng lượt. Hướng vòng lặp **là một phần của chứng minh**, không phải lựa chọn tùy ý.

### 15.7. Đọc trạng thái chưa tính hoặc dùng lại dữ liệu đã ghi

Khi tính một ô 2D, phải xác định các ô tiền nhiệm đã có. Khi nén 1D, phải phân biệt giá trị của **hàng trước** với giá trị **hàng hiện tại**. Vòng lặp đúng cú pháp vẫn có thể sai quan hệ phụ thuộc.

### 15.8. Sentinel trùng đáp án hợp lệ

Nếu dùng `-1` báo “chưa tính”, nhưng tối ưu hợp lệ có thể bằng `-1`, memo sẽ tính lại hoặc đọc sai. Dùng cờ `computed` hoặc sentinel được chứng minh ngoài miền.

### 15.9. Tràn số và cộng với vô cùng

Dùng `Integer.MAX_VALUE` rồi cộng `1` sẽ tràn thành âm. Đếm số cách bằng `int` có thể tràn âm. Với `BigInteger`, không tràn giá trị nhưng có chi phí tính và cấp phát lớn hơn. Luôn chọn kiểu số theo giới hạn bài toán.

### 15.10. Không xét trường hợp rỗng

Chuỗi rỗng, lưới 0 hàng/cột, `amount=0`, `capacity=0`, danh sách vật rỗng đều có thể là đầu vào hợp lệ. Điều kiện cơ sở tốt phải giải thích được các trường hợp này; đừng để lỗi `ArrayIndexOutOfBoundsException` quyết định câu trả lời.

### 15.11. Lẫn đếm cách với tìm tối ưu

Một trạng thái số cách dùng `+`, một trạng thái tối ưu nhỏ nhất dùng `min`; trong một bài có cả hai yêu cầu (ví dụ số đường ngắn nhất và số đường đạt khoảng cách đó), có thể cần **hai giá trị trong cùng trạng thái** và logic cập nhật khi bằng nhau.

### 15.12. Nhầm DP có vòng với phụ thuộc vòng

Top-down mà `solve(x)` lại gọi `solve(x)` trước khi có giá trị hợp lệ có thể đệ quy vô hạn. Tabulation chỉ hợp lệ nếu tồn tại thứ tự mà mọi tiền nhiệm đã tính. Với đồ thị có chu trình, không thể tùy tiện gán topo hay tính một lượt.

### 15.13. Quên chi phí tái dựng nghiệm

Tìm giá trị tối ưu `dp[target]` chưa chắc đáp ứng đề nếu yêu cầu danh sách đồng/vật, dãy con hay đường đi. Cần mảng quyết định hoặc chiến lược lần ngược, và tính cả vùng chứa kết quả.

### 15.14. So sánh với brute force nhưng không chứng minh

Một bộ random test không chứng minh thuật toán đúng mọi input. Nên dùng brute force cho trường hợp nhỏ để **tìm phản ví dụ**, còn tính đúng tổng quát cần chứng minh bao phủ lựa chọn, cơ sở và quy nạp.

## 16. Kiểm thử theo ngữ nghĩa, không chỉ theo số mẫu

| Bài | Input | Kết quả | Điều cần xác minh |
|---|---|---|---|
| Leo bậc 1/2 | `n=0` | `1` | Chuỗi bước rỗng |
| Leo bậc 1/2 | `n=5` | `8` | Tổng hai trường hợp bước cuối |
| Lưới | `[[0]]` | `1` | Ô xuất phát cũng là đích |
| Lưới | `[[1]]` | `0` | Ô xuất phát chặn |
| Lưới | Lưới 3×3, giữa chặn | `2` | Không đi qua vật cản |
| Min coins | `{1,3,4}`, `6` | `2` | Không dùng greedy thay DP |
| Min coins | `{4,6}`, `7` | Không đạt, `-1` | Sentinel |
| Min coins | `{4,6}`, `0` | `0` | Tổng rỗng |
| 0/1 knapsack | W=4, vật `(2,3)`, `(3,4)` | `4` | Vật tối đa một lần |
| Unbounded knapsack | Cùng input | `6` | Có thể dùng hai bản sao vật nặng 2 |
| LCS | `"ABCBDAB"`, `"BDCABA"` | Độ dài `4` | Nhiều nghiệm cùng tối ưu |
| LCS | `""`, `"XYZ"` | `0` | Tiền tố rỗng |
| Edit distance | `"kitten"`, `"sitting"` | `3` | Ba loại thao tác |
| Edit distance | `""`, `"abc"` | `3` | Hàng/cột cơ sở i/j |

### 16.1. Dùng oracle cho bộ dữ liệu nhỏ

- Đổi tiền: với amount nhỏ, có thể liệt kê tổ hợp hoặc dùng BFS trên các tổng để xác nhận số đồng tối thiểu.
- Ba lô 0/1: với n nhỏ (`n<=20` để minh họa), liệt kê `2^n` tập con, kiểm tra sức chứa rồi so sánh giá trị lớn nhất.
- Leo bậc: liệt kê các chuỗi bước 1/2 có tổng n với n nhỏ.
- LCS: liệt kê dãy con của một chuỗi ngắn rồi kiểm tra có là dãy con của chuỗi còn lại không, tìm độ dài lớn nhất.
- Đường lưới: DFS đếm đường cho lưới nhỏ và chỉ đi xuống/phải.

Oracle hữu ích vì **độc lập** với cách cài DP; nếu chính oracle dùng chung công thức sai thì việc khớp kết quả chưa đủ bằng chứng. Cần kiểm tra trường hợp biên và các giá trị bất khả thi riêng.

### 16.2. Theo dõi bảng sau mỗi bước

Khi kết quả sai, in hoặc quan sát bảng của **một input rất nhỏ** (ví dụ amount=6, lưới 2×3, hai chuỗi dài 3). Hỏi lần lượt:

1. Giá trị cơ sở có đúng không?
2. Mỗi ô ứng với câu định nghĩa trạng thái nào?
3. Tiền nhiệm có đúng chỉ số và đã được tính chưa?
4. Phép kết hợp có đúng tối ưu/đếm/tồn tại không?
5. Trạng thái “không thể đạt” có bị nhầm với `0` hoặc “chưa tính” không?
6. Có vô tình tái sử dụng vật/đồng do hướng vòng lặp không?

Việc đối chiếu bảng nhỏ thường tìm lỗi nhanh hơn chỉ đo thời gian chương trình.

## 17. Bài tập tự luyện có đáp án

### Bài 1 — Đặt cơ sở cho số cách

Cho bài leo n bậc bằng bước 1 hoặc 2. Một bạn viết `ways[0]=0`, `ways[1]=1`. Hãy nêu điểm sai và tính `ways[2]` đúng.

**Đáp án:** `ways[0]` phải bằng `1`, tương ứng chuỗi không bước. Khi đó `ways[2]=ways[1]+ways[0]=1+1=2`: `[1,1]` và `[2]`.

### Bài 2 — Min coins và trạng thái không đạt

Có các đồng `{4,6}`, cần tổng `7`. Nếu dùng `dp[x]=0` cho mọi x trước khi chạy, vì sao sai?

**Đáp án:** giá trị 0 cho x>0 bị hiểu là có thể tạo tổng x bằng 0 đồng; từ đó `dp[x-coin]+1` tạo “nghiệm” từ tổng chưa đạt. Phải đặt `INF` cho x>0, `dp[0]=0`, và không cộng từ tiền nhiệm INF.

### Bài 3 — Không quá W và chính xác W

Cho một vật nặng 3, giá trị 10, sức chứa W=2. Nếu mục tiêu cực đại với tổng trọng lượng **không vượt 2**, đáp án là gì? Nếu yêu cầu chọn tập có tổng trọng lượng **chính xác 2**, đáp án thế nào?

**Đáp án:** không vượt 2 ⇒ chọn rỗng, giá trị `0`. Chính xác 2 ⇒ **không có nghiệm**, cần sentinel/trạng thái bất khả thi, không được trả 0.

### Bài 4 — Hướng nén knapsack

Có một vật nặng 2, giá trị 3, sức chứa 4. Duyệt c **tăng** trong một mảng `dp[c]` sẽ cho tối ưu bao nhiêu?

**Đáp án:** cho `6` vì lấy hai bản sao (unbounded). Nếu là 0/1, phải duyệt c **giảm**, kết quả `3`.

### Bài 5 — Thay đổi phép kết hợp trong lưới

Lưới không vật cản, chỉ được đi phải/xuống. Nếu mỗi ô có chi phí và muốn **đường có tổng chi phí nhỏ nhất**, nên thay quan hệ chuyển đếm cách bằng gì?

**Đáp án:** đổi từ **cộng số cách** sang **min chi phí**:

`cost[r][c] = cellCost[r][c] + min(cost[r-1][c], cost[r][c-1])`

trên các tiền nhiệm hợp lệ. Cơ sở `cost[0][0]=cellCost[0][0]`, ngoài lưới và ô không đạt coi `INF`; kiểm tra INF trước khi cộng. Công thức phải điều chỉnh khi có vật cản.

### Bài 6 — Cơ sở khác nhau cho cùng bảng 2D

Với hai chuỗi a,b, tại sao `LCS[0][j]=0` nhưng `EditDistance[0][j]=j`?

**Đáp án:** LCS của tiền tố rỗng với bất kỳ chuỗi là dãy rỗng dài 0; edit distance phải chèn j ký tự để biến rỗng thành tiền tố đích dài j. Ý nghĩa khác → cơ sở khác.

### Bài 7 — Dữ liệu có thể âm

Một DP tối đa hóa lợi nhuận có thể cho đáp án `-1` ở trạng thái hợp lệ. Có nên dùng `memo[state]=-1` để báo chưa tính không?

**Đáp án:** không an toàn, vì `-1` có thể là đáp án đã tính. Dùng cờ riêng `computed[state]`, `null` ở kiểu đóng hộp, hoặc sentinel được chứng minh nằm ngoài miền hợp lệ.

### Bài 8 — Tính chi phí một bảng

DP có `O(n²)` trạng thái đoạn `(l,r)` và mỗi trạng thái thử tối đa `O(n)` điểm tách. Chi phí tổng và bộ nhớ là bao nhiêu nếu mỗi thử tách tốn O(1)?

**Đáp án:** thời gian `O(n³)`, bộ nhớ `O(n²)` để lưu các trạng thái, cộng thông tin truy vết nếu lưu điểm chia.

### Bài 9 — Không tính vòng phụ thuộc

Trong coin change, nếu cho phép mệnh giá `0`, phương trình `dp[x]=min(dp[x],dp[x-0]+1)` có điều gì đáng ngờ với top-down?

**Đáp án:** tham chiếu từ `dp[x]` đến **chính nó**, phá thứ tự giải nếu đệ quy chưa đánh dấu đã tính. Bài coin change chuẩn giới hạn mệnh giá **dương**; đồng mệnh giá 0 cũng không giúp giảm số đồng trong bài min, nên cần xác thực loại bỏ.

### Bài 10 — Tái dựng lời giải

Một bảng min coins chỉ chứa `dp[amount]=2`. Giá trị 2 đã đủ để biết chắc hai mệnh giá nào được chọn chưa?

**Đáp án:** chưa. Cần mảng quyết định `lastCoin[]` hoặc lần ngược các chuyển thỏa `dp[x]=dp[x-c]+1`. Có thể tồn tại nhiều tổ hợp tối ưu khác nhau; cần thêm quy tắc hòa nếu muốn một nghiệm xác định.

## 18. Checklist trước khi nộp lời giải DP

1. **Đã phát biểu mục tiêu và ràng buộc đầy đủ chưa?** Đếm/đạt được/cực tiểu/cực đại; chọn rỗng, chọn đúng tổng, dùng vật một lần hay không giới hạn?
2. **Câu định nghĩa `dp[...]` có rõ không?** Biết chính xác trạng thái đại diện input prefix, sức chứa, tổng, chỉ số hay lượt nào?
3. **Có đủ thông tin trong trạng thái không?** Hai tình huống gộp làm một có thật sự có cùng lựa chọn tương lai không?
4. **Mọi chuyển đều hợp lệ?** Không truy cập âm, vượt dung lượng, đi qua vật cản, dùng vật quá số lần, bỏ kiểm tra tiền nhiệm không đạt.
5. **Mọi nghiệm đều được xét?** Phân nhánh lấy/bỏ, đồng cuối, bước cuối, ký tự cuối hoặc điểm chia có bao phủ toàn bộ?
6. **Phép kết hợp phù hợp?** `min`, `max`, `+`, `OR` và cách xử lý khi các trường hợp đếm trùng?
7. **Cơ sở mang ý nghĩa gì?** Đường đi rỗng một cách; chi phí rỗng bằng 0; tiền tố rỗng có LCS 0; edit distance hàng đầu bằng độ dài.
8. **Trạng thái không đạt/không tính đã được phân biệt?** INF/−INF, cờ `computed`, `null`, tránh tràn khi cộng.
9. **Có thứ tự phụ thuộc hợp lệ không?** Top-down tiến về cơ sở; bottom-up tính tiền nhiệm trước; DP đoạn thường theo độ dài.
10. **Nén bộ nhớ có giữ nguyên ý nghĩa chuyển không?** Nhất là vòng ngược của 0/1 và vòng xuôi của unbounded.
11. **Đáp án cuối ở đâu?** `dp[n]`, `dp[n][m]`, `dp[n][W]`, hay max/min trên một hàng?
12. **Có cần truy vết không?** Lưu lựa chọn và tính thêm chi phí đầu ra khi cần.
13. **Độ phức tạp tính đủ chưa?** Số trạng thái × số chuyển × chi phí mỗi chuyển, bộ nhớ, stack, số lớn và giới hạn tài nguyên.
14. **Đã kiểm tra ca biên và phản ví dụ?** Đầu vào rỗng, chỉ một phần tử, không đạt, trùng, số âm nếu được phép, nhiều nghiệm tối ưu và sai lệch 0/1/unbounded.
15. **Có chứng minh bằng quy nạp trên phụ thuộc không?** Cơ sở đúng, mỗi lựa chọn hợp lệ, không bỏ nghiệm, kết hợp đúng và thứ tự tính đúng.

**Ghi nhớ:** muốn viết DP chính xác, hãy bắt đầu từ **ngữ nghĩa trạng thái**, phân tích **quyết định cuối/đầu** để tìm quan hệ chuyển, rồi đặt **điều kiện cơ sở đúng với bài toán**. Cơ sở `0`, `1` hoặc `INF` không phải mẹo cú pháp; mỗi giá trị đại diện một mệnh đề toán học khác nhau. Cuối cùng phải tính theo đúng thứ tự phụ thuộc và giữ nguyên ý nghĩa bài toán khi tối ưu bộ nhớ.
