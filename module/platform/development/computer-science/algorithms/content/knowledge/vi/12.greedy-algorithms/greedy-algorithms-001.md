# Lựa chọn cục bộ và yêu cầu tối ưu toàn cục

> **Chủ đề:** Computer Science Algorithms → Tham lam.  
> **Mục tiêu:** Phân biệt quyết định **tốt nhất tại thời điểm hiện tại** với lời giải **tối ưu toàn cục**; hiểu các điều kiện cần chứng minh trước khi dùng thuật toán tham lam (*greedy*), biết chứng minh bằng lập luận trao đổi (*exchange argument*) hoặc “luôn đi trước” (*stays ahead*), nhận diện phản ví dụ và cài đặt một số ứng dụng đúng bằng Java 17+.

## 1. Từ quyết định cục bộ đến lời giải toàn cục

Một **bài toán tối ưu** thường có ba thành phần:

1. **Tập phương án khả thi:** những lời giải đáp ứng tất cả ràng buộc.
2. **Hàm mục tiêu:** đại lượng cần cực đại hoặc cực tiểu, chẳng hạn số công việc hoàn thành, tổng lợi nhuận, chi phí đường đi hoặc trọng lượng cây khung.
3. **Yêu cầu tối ưu toàn cục:** tìm một phương án khả thi có giá trị mục tiêu tốt nhất trong **toàn bộ** các phương án khả thi.

Thuật toán **tham lam** (*greedy algorithm*) xây dựng lời giải từng bước. Ở mỗi bước, nó chọn một phương án **có vẻ tốt nhất theo tiêu chí cục bộ** và thường **không quay lại thay đổi** những quyết định đã chốt.

Ví dụ, muốn chọn nhiều cuộc họp không chồng nhau, ta có thể ưu tiên cuộc họp **kết thúc sớm nhất**. Trực giác: cuộc họp kết thúc sớm để lại nhiều thời gian cho những cuộc sau. Nhưng **trực giác không phải chứng minh**; phải chứng minh rằng lựa chọn này không làm mất khả năng đạt số cuộc họp tối đa.

Điểm cần nhớ:

- **Cục bộ** là một quyết định dựa trên trạng thái và ứng viên tại bước hiện tại.
- **Toàn cục** là chất lượng của **cả lời giải hoàn chỉnh**.
- “Mỗi bước đều tốt nhất theo tiêu chí cục bộ” **không tự động** suy ra “toàn bộ lời giải tốt nhất”.
- Một greedy đúng cho **mục tiêu này** có thể sai cho một mục tiêu gần giống, ví dụ chọn nhiều cuộc họp nhất khác với chọn tổng **giá trị** cuộc họp lớn nhất.

### 1.1. Ví dụ cho thấy nguy cơ của lựa chọn cục bộ

Đổi tiền với các mệnh giá `{1,3,4}`, cần tạo tổng `6` với **ít đồng nhất**.

Quy tắc “luôn lấy đồng lớn nhất không vượt số tiền còn lại”:

```text
Số tiền: 6
Lấy 4 → còn 2
Lấy 1 → còn 1
Lấy 1 → còn 0

Greedy: 4 + 1 + 1 = 6, dùng 3 đồng.
```

Nhưng lời giải tốt hơn là:

```text
3 + 3 = 6, chỉ dùng 2 đồng.
```

Vậy greedy **cục bộ** “chọn mệnh giá lớn nhất trước” tạo được lời giải **khả thi** nhưng **không tối ưu toàn cục** cho hệ mệnh giá này. Đây là phản ví dụ, không phải lỗi cài đặt.

Ngược lại, trong **bài toán ba lô phân số** (*fractional knapsack*), quy tắc chọn vật có **giá trị trên một đơn vị trọng lượng cao nhất** trước lại tối ưu, vì ta được phép lấy một phần vật. Nếu đổi sang ba lô **0/1** (mỗi vật chỉ lấy toàn bộ hoặc không lấy), cùng quy tắc có thể sai. Chính **đặc tả phương án khả thi** quyết định tính đúng của tham lam.

## 2. Khuôn mẫu thiết kế một thuật toán tham lam

Một thuật toán tham lam có thể được mô tả bằng các bước:

1. **Xác định trạng thái đã chọn:** prefix của lời giải, tập cạnh, tổng trọng lượng, thời điểm kết thúc gần nhất.
2. **Liệt kê ứng viên:** những lựa chọn chưa dùng còn có thể xét.
3. **Xác định tính khả thi:** thêm một ứng viên có vi phạm ràng buộc không?
4. **Đặt tiêu chí ưu tiên cục bộ:** kết thúc sớm, chi phí thấp, mật độ giá trị cao, khoảng cách nhỏ...
5. **Chọn ứng viên tốt nhất theo tiêu chí**, nhưng chỉ chấp nhận nếu vẫn khả thi.
6. **Cập nhật trạng thái** mà không sửa các lựa chọn đã được xác nhận (theo bản greedy cơ bản).
7. **Dừng** khi không còn ứng viên hoặc đã đáp ứng yêu cầu.

Pseudocode tổng quát:

```text
greedy(candidates):
    solution = trạng thái ban đầu
    sắp xếp/đặt ưu tiên cho candidates nếu cần

    for candidate theo thứ tự ưu tiên:
        if có thể thêm candidate mà không phá ràng buộc:
            đưa candidate vào solution
            cập nhật trạng thái

    return solution
```

Đoạn này **chưa phải** một thuật toán tối ưu cho mọi bài toán: nó chỉ là **khuôn triển khai**. Một tiêu chí ưu tiên sai có thể tạo kết quả rất kém dù các thao tác thêm/loại đều đúng.

### 2.1. Ba câu hỏi bắt buộc

Trước khi tin một quy tắc greedy, hãy hỏi:

- **Feasibility (khả thi):** liệu mọi bước được chấp nhận có giữ đúng ràng buộc không?
- **Greedy-choice property (tính chất lựa chọn tham lam):** có bảo đảm **tồn tại** một nghiệm tối ưu chứa lựa chọn tham lam ở bước hiện tại không?
- **Optimal substructure (cấu trúc con tối ưu):** sau khi cố định lựa chọn đúng đắn đó, phần còn lại có thể giải tối ưu như **một bài toán con cùng kiểu** không?

Hai tính chất sau là **nghĩa vụ chứng minh**, không phải các nhãn có thể gắn tự do. Chứng minh tối ưu con **một mình** chưa đủ để kết luận greedy đúng: nhiều bài có DP và cấu trúc con tối ưu nhưng vẫn không thể chọn cục bộ mà không xét tương lai.

### 2.2. Điều gì phải được chứng minh?

Một lời giải greedy hoàn chỉnh thường cần:

1. **Tính khả thi:** mọi tập/chuỗi quyết định đầu ra tuân thủ đề bài.
2. **Tính dừng:** thuật toán kết thúc sau số bước hữu hạn.
3. **Tính tối ưu:** giá trị mục tiêu đầu ra bằng tối ưu toàn cục.
4. **Độ phức tạp:** tính cả bước sắp xếp/heap/tìm kiếm, không chỉ vòng chọn.
5. **Quy tắc hòa:** khi hai ứng viên “tốt ngang nhau”, việc chọn cái nào có ảnh hưởng đến chứng minh và đầu ra không?

Một bản cài đặt cho ra đáp án đúng ở nhiều ví dụ nhỏ vẫn **không thay thế** chứng minh cho mọi đầu vào hợp lệ.

## 3. Bài toán chọn lịch nhiều công việc nhất

Cho `n` hoạt động, hoạt động `i` có thời điểm bắt đầu `start_i` và kết thúc `end_i` với `start_i < end_i`.

Dùng quy ước **nửa mở** `[start_i,end_i)`:

- Hai hoạt động `A=[1,4)` và `B=[4,7)` **không xung đột** vì A kết thúc đúng lúc B bắt đầu.
- Hai hoạt động `A=[1,4)` và `B=[3,6)` **xung đột** vì có khoảng thời gian chung.
- Mỗi hoạt động có giá trị **đơn vị**: mục tiêu là **chọn số hoạt động nhiều nhất**, không phải tối đa tổng tiền.

**Quy tắc tham lam đúng:** trong các hoạt động có thể chọn tiếp theo, ưu tiên hoạt động **kết thúc sớm nhất**.

Cách cài đặt đơn giản: sắp xếp tất cả hoạt động theo `end` tăng dần, sau đó quét từ trái sang phải và chấp nhận hoạt động có `start >= lastEnd` (thời điểm kết thúc của hoạt động đã chọn gần nhất).

### 3.1. Vì sao không ưu tiên bắt đầu sớm nhất hoặc thời lượng ngắn nhất?

Ví dụ:

```text
A = [1,10)
B = [2,3)
C = [3,4)
D = [4,5)
```

- Chọn **bắt đầu sớm nhất**: lấy A, không thể lấy B/C/D → **1** hoạt động.
- Chọn **kết thúc sớm nhất**: lấy B, C, D → **3** hoạt động.

Cách chọn “khoảng ngắn nhất” cũng **không có bảo đảm chung** vì hoạt động ngắn có thể nằm giữa và chặn hai hoạt động ở hai bên. Ví dụ:

```text
L = [0,3)     thời lượng 3
M = [2,4)     thời lượng 2
R = [3,6)     thời lượng 3
```

Chọn M vì ngắn nhất cho 1 hoạt động; chọn L rồi R cho 2 hoạt động. Độ dài nhỏ nhất không đồng nghĩa với **điểm kết thúc thuận lợi nhất**.

### 3.2. Truy vết từng bước

Dùng danh sách:

```text
A [1,4)    B [3,5)    C [0,6)    D [5,7)
E [3,9)    F [5,9)    G [6,10)   H [8,11)
I [8,12)   J [2,14)   K [12,16)
```

Khi sắp theo thời điểm kết thúc tăng dần rồi quét:

| Ứng viên | Thời điểm kết thúc | Quyết định | Thời điểm kết thúc cuối |
|---|---:|---|---:|
| A `[1,4)` | 4 | Chọn | 4 |
| B `[3,5)` | 5 | Loại, `3<4` | 4 |
| C `[0,6)` | 6 | Loại, `0<4` | 4 |
| D `[5,7)` | 7 | Chọn, `5>=4` | 7 |
| E `[3,9)` | 9 | Loại | 7 |
| F `[5,9)` | 9 | Loại | 7 |
| G `[6,10)` | 10 | Loại | 7 |
| H `[8,11)` | 11 | Chọn | 11 |
| I `[8,12)` | 12 | Loại | 11 |
| J `[2,14)` | 14 | Loại | 11 |
| K `[12,16)` | 16 | Chọn | 16 |

Kết quả A, D, H, K có **4** hoạt động, không giao nhau.

Chú ý: với các hoạt động cùng thời điểm kết thúc, tiêu chí phụ có thể chọn thứ tự ổn định, chẳng hạn `start` tăng rồi ID. Khi mọi hoạt động có `start < end` và cùng `end`, chọn hoạt động kết thúc sớm nhất ở nhóm hòa vẫn có bảo đảm theo chứng minh trao đổi; nếu đề có điều kiện phụ riêng phải xét lại.

## 4. Java 17: chọn hoạt động bằng thời điểm kết thúc sớm

Lưu thành **ActivitySelectionGreedy.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public class ActivitySelectionGreedy {
    record Activity(String id, int start, int end) {
        @Override
        public String toString() {
            return id + "[" + start + "," + end + ")";
        }
    }

    static List<Activity> select(Activity[] input) {
        Objects.requireNonNull(input, "input");
        Activity[] sorted = input.clone(); // Không thay đổi mảng nguồn.

        for (Activity a : sorted) {
            Objects.requireNonNull(a, "activity");
            if (a.start() >= a.end()) {
                throw new IllegalArgumentException("Require start < end");
            }
        }

        Arrays.sort(sorted,
                Comparator.comparingInt(Activity::end)
                          .thenComparingInt(Activity::start)
                          .thenComparing(Activity::id));

        List<Activity> result = new ArrayList<>();
        long lastEnd = Long.MIN_VALUE;

        for (Activity a : sorted) {
            if (a.start() >= lastEnd) {
                result.add(a);
                lastEnd = a.end();
            }
        }
        return result;
    }

    public static void main(String[] args) {
        Activity[] activities = {
            new Activity("A", 1, 4),
            new Activity("B", 3, 5),
            new Activity("C", 0, 6),
            new Activity("D", 5, 7),
            new Activity("E", 3, 9),
            new Activity("F", 5, 9),
            new Activity("G", 6, 10),
            new Activity("H", 8, 11),
            new Activity("I", 8, 12),
            new Activity("J", 2, 14),
            new Activity("K", 12, 16)
        };

        List<Activity> chosen = select(activities);
        System.out.println("Chosen: " + chosen);
        System.out.println("Count: " + chosen.size());
        System.out.println("Empty: " + select(new Activity[0]));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ActivitySelectionGreedy.java
java ActivitySelectionGreedy
```

Stdout:

```text
Chosen: [A[1,4), D[5,7), H[8,11), K[12,16)]
Count: 4
Empty: []
```

**Giải thích kỹ thuật:**

- `Arrays.sort` sắp bản sao theo `end` tăng, sau đó theo `start`, rồi ID để kết quả xác định.
- `lastEnd` dùng `long` khởi tạo bằng `Long.MIN_VALUE`, nên ngay cả hoạt động hợp lệ bắt đầu tại `Integer.MIN_VALUE` vẫn được xem xét đúng. Nếu dùng `int lastEnd=0` thì sẽ **loại sai** hoạt động có thời gian âm.
- Điều kiện `start>=lastEnd` tương ứng khoảng nửa mở; nếu bài dùng các khoảng đóng với quy ước không được đụng đầu mút, điều kiện có thể phải đổi thành `start>lastEnd`.
- `Activity` là `record` Java 17 nên các trường truy cập bằng `a.start()`, `a.end()`; `id` ở ví dụ được giả định không `null`, nếu muốn API chặt hơn có thể xác thực cả ID.
- Hàm không sửa dữ liệu nguồn và trả `List<Activity>` chứa **bản ghi được chọn**, không chỉ số lượng.

**Độ phức tạp:** sao chép mảng `O(n)`, sắp theo `end` `O(n log n)`, quét chọn `O(n)`, nên thời gian tổng **`O(n log n)`**, bộ nhớ ngoài đầu vào `O(n)` cho bản sao và danh sách kết quả. Nếu đầu vào **đã sắp theo `end`** và cho phép quét trực tiếp, bước chọn chỉ mất `O(n)` thời gian và có thể giữ bộ nhớ làm việc `O(1)` ngoài bộ nhớ lưu output.

## 5. Chứng minh tính tối ưu bằng lập luận trao đổi (*exchange argument*)

Xét bài chọn **số lượng hoạt động không xung đột tối đa** trên các khoảng nửa mở. Gọi `g` là hoạt động có **thời điểm kết thúc sớm nhất** trong những hoạt động hợp lệ của bước hiện tại.

Ta chứng minh: **tồn tại một phương án tối ưu chứa `g`**.

1. Lấy một lời giải tối ưu bất kỳ `OPT`, gồm các hoạt động được sắp theo thứ tự bắt đầu hoặc kết thúc.
2. Gọi `o` là hoạt động đầu tiên trong `OPT` (hoạt động có kết thúc sớm nhất của lời giải).
3. Vì `g` kết thúc sớm nhất trong tất cả ứng viên, `end(g) <= end(o)`.
4. Thay `o` bằng `g`: mọi hoạt động tiếp theo của `OPT` bắt đầu **không sớm hơn** `end(o)` (do không chồng nhau), nên cũng bắt đầu không sớm hơn `end(g)`. Vì vậy chúng vẫn không xung đột với `g`.
5. Số lượng hoạt động vẫn bằng số lượng ban đầu. Do đó lời giải sau trao đổi vẫn tối ưu và có chứa `g`.

Khi đã chọn `g`, bài toán còn lại là chọn nhiều hoạt động nhất trong số những hoạt động có `start >= end(g)` — **một bài toán cùng cấu trúc nhưng nhỏ hơn**. Áp dụng lập luận trao đổi lặp lại ở các bước còn lại; theo quy nạp, toàn bộ lịch do greedy dựng lên là tối ưu.

**Hai phần khác nhau của chứng minh:**

- **Greedy-choice property:** có một nghiệm tối ưu **có thể bắt đầu bằng** `g`.
- **Optimal substructure:** khi cố định `g`, tối ưu tổng bằng `1 +` tối ưu của phần hoạt động còn lại không xung đột.

Bất biến “các hoạt động đã chọn không giao nhau” chỉ chứng minh **khả thi**, chưa chứng minh **tối ưu**. Bước thay thế `o` bằng `g` mới là lý do không mất nghiệm tối ưu.

### 5.1. Chứng minh bằng “luôn đi trước” (*stays ahead*)

Một cách tương đương: gọi `g_1,g_2,...` là dãy hoạt động greedy chọn, và `o_1,o_2,...` là các hoạt động của một lời giải khả thi khác có cùng thứ tự thời gian.

Chứng minh bằng quy nạp rằng với mỗi `j` mà cả hai dãy đều có hoạt động thứ `j`:

`end(g_j) <= end(o_j)`.

- `j=1`: greedy chọn hoạt động kết thúc sớm nhất.
- Bước `j`: nếu `end(g_(j-1)) <= end(o_(j-1))`, hoạt động `o_j` bắt đầu sau `end(o_(j-1))` nên **cũng khả thi** sau `g_(j-1)`. Greedy chọn hoạt động khả thi kết thúc sớm nhất, vì vậy `end(g_j) <= end(o_j)`.

Nếu có một lịch khác dài hơn lịch greedy, sau hoạt động thứ `k` của greedy vẫn còn hoạt động thứ `k+1` của lịch kia. Vì greedy kết thúc không muộn hơn hoạt động thứ `k` bên kia, hoạt động tiếp theo ấy còn khả thi cho greedy — mâu thuẫn với việc greedy đã dừng. Do đó greedy đạt số lượng tối đa.

Cả hai kiểu chứng minh đều có ích: **trao đổi** chứng minh có nghiệm tối ưu chứa lựa chọn; **luôn đi trước** chứng minh greedy không mất lợi thế về trạng thái cho các bước tương lai.

## 6. Khi thay đổi mục tiêu, cùng quy tắc greedy có thể sai

Bây giờ mỗi hoạt động có **trọng số/lợi nhuận** `weight_i`, và mục tiêu là tối đa **tổng trọng số**, không phải số lượng hoạt động.

Ví dụ:

```text
A = [0,2), weight=2
B = [2,4), weight=2
C = [0,4), weight=10
```

- Chọn kết thúc sớm nhất sẽ lấy A rồi B → tổng trọng số `2+2=4`.
- Lời giải tối ưu theo trọng số chọn C → tổng trọng số `10`.

Thuật toán chọn nhiều hoạt động nhất không giải được **weighted interval scheduling**. Bài có trọng số thường dùng **quy hoạch động** sau khi sắp theo thời điểm kết thúc:

`dp[i] = max(dp[i-1], weight[i] + dp[p(i)])`

trong đó `p(i)` là hoạt động có chỉ số lớn nhất kết thúc không muộn hơn lúc bắt đầu của hoạt động `i` (xét các hoạt động trước `i`). Lấy hoặc bỏ hoạt động `i` đều được xem xét nên có thể tránh lựa chọn cục bộ sai.

**Không phải vì bài có “cấu trúc con tối ưu” mà greedy chắc chắn đúng:** cả bài có và không có trọng số đều chia thành bài toán con, nhưng bài có trọng số thiếu tính chất lựa chọn tham lam theo tiêu chí kết thúc sớm nhất.

### 6.1. Tham lam sai trong đổi tiền với mệnh giá tùy ý

Hệ mệnh giá `{1,3,4}`, cần đổi `6`: lấy lớn nhất trước cho `[4,1,1]` (3 đồng), tối ưu là `[3,3]` (2 đồng).

Với **một số hệ mệnh giá chuẩn hóa** (*canonical coin systems*), chọn mệnh giá lớn nhất trước có thể đúng; tuy nhiên không được lấy ví dụ một hệ mệnh giá rồi kết luận cho **mọi** hệ mệnh giá.

Quan trọng: quy tắc “lấy đồng lớn nhất” đảm bảo **khả thi** khi có đồng mệnh giá `1`, nhưng không đảm bảo **ít đồng nhất**.

## 7. Java 17: phản ví dụ đổi tiền và đối chiếu quy hoạch động

Lưu thành **GreedyCoinCounterexample.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class GreedyCoinCounterexample {
    // Preconditions: coins giảm dần, dương; có mệnh giá 1.
    static List<Integer> greedy(int[] coins, int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        List<Integer> chosen = new ArrayList<>();
        int remaining = amount;

        for (int coin : coins) {
            if (coin <= 0) {
                throw new IllegalArgumentException("Coin must be positive");
            }
            while (coin <= remaining) {
                chosen.add(coin);
                remaining -= coin;
            }
        }
        if (remaining != 0) {
            throw new IllegalArgumentException("Amount not representable");
        }
        return chosen;
    }

    // Tìm số đồng tối thiểu khi mỗi mệnh giá dùng không giới hạn.
    static int minCoinsDp(int[] coins, int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        final int INF = amount + 1; // Ví dụ amount nhỏ, không tràn int.
        int[] dp = new int[amount + 1];
        Arrays.fill(dp, INF);
        dp[0] = 0;

        for (int total = 1; total <= amount; total++) {
            for (int coin : coins) {
                if (coin > 0 && coin <= total && dp[total - coin] < INF) {
                    dp[total] = Math.min(dp[total], dp[total - coin] + 1);
                }
            }
        }
        return dp[amount] == INF ? -1 : dp[amount];
    }

    public static void main(String[] args) {
        int[] coins = {4, 3, 1};
        int amount = 6;

        List<Integer> greedyChoice = greedy(coins, amount);
        System.out.println("Greedy coins: " + greedyChoice);
        System.out.println("Greedy count: " + greedyChoice.size());
        System.out.println("DP optimum count: " + minCoinsDp(coins, amount));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 GreedyCoinCounterexample.java
java GreedyCoinCounterexample
```

Stdout:

```text
Greedy coins: [4, 1, 1]
Greedy count: 3
DP optimum count: 2
```

Bản DP tính `dp[total]` bằng cách thử **mọi lựa chọn đồng tiền cuối cùng** hợp lệ; với tổng `6`, lựa chọn 3 rồi 3 cho số đồng tối thiểu 2.

**Phân tích:** tham lam quét mệnh giá và có thể lặp thêm từng đồng trong output, nên chi phí phụ thuộc số đồng xuất ra; DP dùng `O(amount × numberOfDenominations)` thời gian và `O(amount)` bộ nhớ. Đây là độ phức tạp **giả đa thức** theo trị số `amount`, không phải theo số chữ số nhị phân của `amount`.

**Giới hạn ví dụ:** `INF=amount+1` và mảng dài `amount+1` chỉ phù hợp khi `amount` đủ nhỏ để không tràn `int`/khả năng cấp phát; chương trình dùng `amount=6`. Với API tổng quát cần kiểm tra miền trước khi cấp phát, xác thực tất cả mệnh giá dương, và xác định chính sách khi không thể đổi được số tiền.

## 8. Ba lô phân số: trường hợp greedy theo tỷ lệ là đúng

Cho các vật `i` với:

- Giá trị `v_i >= 0`.
- Trọng lượng `w_i > 0`.
- Sức chứa ba lô `W >= 0`.
- Có thể lấy một **phần bất kỳ** của mỗi vật: `0 <= x_i <= 1`.

Mục tiêu cực đại:

`Σ v_i x_i`, với ràng buộc `Σ w_i x_i <= W`.

**Quy tắc greedy:** sắp vật theo **mật độ giá trị** `v_i/w_i` từ cao đến thấp. Lấy toàn bộ vật có mật độ cao nhất trước, và nếu sức chứa còn lại ít hơn trọng lượng vật tiếp theo thì **lấy một phần** vừa đủ.

Ví dụ:

```text
Vật A: value=60,  weight=10 → mật độ 6
Vật B: value=100, weight=20 → mật độ 5
Vật C: value=120, weight=30 → mật độ 4
Sức chứa W=50
```

Chọn:

```text
Lấy toàn bộ A: 10 trọng lượng, giá trị 60
Lấy toàn bộ B: 20 trọng lượng, giá trị 100
Còn 20 sức chứa, lấy 20/30 vật C: giá trị 80
Tổng: 50 trọng lượng, giá trị 240
```

Chứng minh tối ưu dựa trên **trao đổi theo lượng trọng lượng**. Giả sử một lời giải khả thi dùng một lượng dương trọng lượng của vật có mật độ thấp `d_low`, trong khi vẫn còn khả năng dùng thêm một lượng trọng lượng của vật có mật độ cao hơn `d_high>d_low`. Chuyển `δ` đơn vị trọng lượng từ vật thấp sang vật cao (chọn `δ` đủ nhỏ để không vượt giới hạn) làm tổng trọng lượng không đổi, còn giá trị tăng:

`δ (d_high - d_low) > 0`.

Vậy không có lời giải tối ưu nào cần giữ trọng lượng ở vật có mật độ thấp trong khi vật có mật độ cao hơn chưa được lấy tối đa. Lặp lại phép trao đổi cho ta một lời giải tối ưu tuân thủ thứ tự mật độ giảm dần; chính là kết quả của greedy.

**Điều kiện quyết định:** vật có thể **chia nhỏ liên tục**. Nếu chỉ được lấy `0` hoặc `1` toàn bộ vật, phép chuyển `δ` không còn hợp lệ; chứng minh sụp đổ.

### 8.1. Java 17: ba lô phân số có thể chạy

Lưu thành **FractionalKnapsackGreedy.java**:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.Objects;

public class FractionalKnapsackGreedy {
    record Item(String id, int value, int weight) {}

    static double solve(Item[] items, int capacity) {
        Objects.requireNonNull(items, "items");
        if (capacity < 0) {
            throw new IllegalArgumentException("Negative capacity");
        }

        Item[] sorted = items.clone();
        for (Item item : sorted) {
            Objects.requireNonNull(item, "item");
            if (item.weight() <= 0 || item.value() < 0) {
                throw new IllegalArgumentException("Invalid item");
            }
        }

        Arrays.sort(sorted, (a, b) -> {
            double da = (double) a.value() / a.weight();
            double db = (double) b.value() / b.weight();
            int byDensity = Double.compare(db, da);
            return byDensity != 0 ? byDensity : a.id().compareTo(b.id());
        });

        double remaining = capacity;
        double totalValue = 0.0;

        for (Item item : sorted) {
            if (remaining <= 0.0) {
                break;
            }

            double usedWeight = Math.min(remaining, item.weight());
            totalValue += usedWeight * item.value() / item.weight();
            remaining -= usedWeight;

            System.out.printf(Locale.US, "Take %s: %.1f / %d%n",
                    item.id(), usedWeight, item.weight());
        }
        return totalValue;
    }

    public static void main(String[] args) {
        Item[] items = {
            new Item("A", 60, 10),
            new Item("B", 100, 20),
            new Item("C", 120, 30)
        };
        double optimum = solve(items, 50);
        System.out.printf(Locale.US, "Total value: %.1f%n", optimum);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FractionalKnapsackGreedy.java
java FractionalKnapsackGreedy
```

Stdout:

```text
Take A: 10.0 / 10
Take B: 20.0 / 20
Take C: 20.0 / 30
Total value: 240.0
```

**Chi phí:** sao chép/sắp `n` vật theo mật độ là `O(n log n)`, quét lấy vật `O(n)`, bộ nhớ dùng cho bản sao là `O(n)` cộng chi phí sắp xếp của thư viện. Với đầu vào đã sắp theo mật độ, bước chọn thực tế là `O(n)`.

**Lưu ý kỹ thuật và mô hình:**

- Mật độ được tính với phép chia `double`, không phải chia nguyên; ví dụ hợp lệ với giá trị/trọng lượng `int` không âm và trọng lượng dương. Với dữ liệu số học đòi hỏi độ chính xác tuyệt đối, cần so sánh tỷ số bằng phép nhân chéo **không tràn**, chẳng hạn kiểu số lớn phù hợp; `double` có thể hòa các tỷ số rất gần nhau do làm tròn.
- Trong bản ghi minh họa, `id` giả định không `null`. Điều kiện `value>=0` tránh các vật có giá trị âm; lấy không hết sức chứa vẫn là lựa chọn hợp lệ nếu hết vật có ích.
- `System.out.printf(Locale.US,...)` bảo đảm dấu thập phân `.` ở stdout như ví dụ, bất kể máy đang dùng locale khác.
- Dữ liệu đầu vào không bị sửa vì thuật toán sắp bản sao mảng. Với vật có mật độ bằng nhau, đổi chỗ hai vật không làm đổi tổng giá trị nếu trọng lượng và ràng buộc phân số giống như mô hình trên.

### 8.2. Cùng dữ liệu nhưng bài toán 0/1 bị sai

Nếu mỗi vật chỉ được lấy **toàn bộ hoặc không lấy** và `W=50`:

- Chọn mật độ cao nhất: A trọng lượng 10, B trọng lượng 20, còn 20 nên **không thể lấy C** trọng lượng 30 → tổng giá trị `60+100=160`.
- Phương án tốt hơn: B+C có trọng lượng `20+30=50`, giá trị `100+120=220`.

Đó là phản ví dụ cho việc áp dụng nguyên quy tắc mật độ vào **0/1 knapsack**. Bài toán 0/1 thường dùng quy hoạch động, meet-in-the-middle, branch-and-bound hoặc thuật toán khác tùy miền ràng buộc.

**Không nhầm:** “greedy chọn vật giá trị lớn nhất” cũng không được chứng minh đúng cho 0/1; thay đổi tiêu chí ưu tiên không tự tạo ra greedy-choice property.

## 9. Cây khung nhỏ nhất: greedy nhờ tính chất lát cắt

Trên đồ thị vô hướng **liên thông** có trọng số cạnh, một **cây khung nhỏ nhất** (*minimum spanning tree*, MST) là tập `V-1` cạnh nối tất cả `V` đỉnh, không tạo chu trình, có tổng trọng số nhỏ nhất.

Thuật toán **Kruskal** là một ví dụ tham lam đúng:

1. Sắp mọi cạnh theo trọng số **tăng dần**.
2. Duyệt lần lượt; nếu cạnh nối **hai thành phần liên thông khác nhau** trong tập cạnh đã chọn, **thêm** cạnh đó.
3. Nếu thêm sẽ tạo chu trình, **bỏ qua**.
4. Dừng khi đã chọn `V-1` cạnh (nếu đồ thị liên thông).

**Vì sao có cơ sở tối ưu?** Dựa trên **tính chất lát cắt** (*cut property*): với một lát cắt không có cạnh đã chọn băng qua, một cạnh nhẹ nhất băng qua lát cắt là lựa chọn **an toàn**, nghĩa là có một MST chứa các cạnh đã chọn và cạnh mới. Với Kruskal, khi một cạnh nhẹ nhất hiện còn nối hai thành phần khác nhau, ta có thể dùng tính chất này hoặc lập luận trao đổi để khẳng định việc thêm nó không loại bỏ mọi MST tối ưu.

### 9.1. Ý tưởng chứng minh trao đổi cho Kruskal

Giả sử `F` là các cạnh đã chọn trước đó và **tồn tại** một MST `M` chứa `F`. Chọn cạnh `e=(u,v)` nhỏ nhất tiếp theo mà hai đầu nằm ở **hai thành phần khác nhau** của `F`.

- Nếu `e` đã thuộc `M`, lựa chọn an toàn.
- Nếu `e` chưa thuộc `M`, thêm `e` vào cây `M` tạo **một chu trình**. Trên chu trình đó tồn tại ít nhất một cạnh `f` băng qua lát cắt chia thành phần `F` chứa `u` với các đỉnh còn lại.
- Vì `e` là cạnh nhẹ nhất có thể nối hai thành phần ở thời điểm này, `w(e)<=w(f)` (hai đầu `f` nằm ở các thành phần khác nhau của `F`).
- Thay `f` bằng `e` giữ cho đồ thị là cây khung, không làm tăng tổng trọng số, và vẫn chứa mọi cạnh trong `F` vì `f` băng qua các thành phần của `F`, không thể thuộc `F`.
- Kết quả là một MST chứa `F ∪ {e}`. Bất biến “có một MST chứa toàn bộ các cạnh greedy đã chọn” tiếp tục đúng.

Khi `F` có `V-1` cạnh, nó đã là cây khung; bất biến suy ra đây là MST. Kết luận đúng ngay cả khi trọng số **trùng nhau** hoặc **âm**, miễn các giả thiết về đồ thị và thuật toán được giữ.

**Quan trọng:** “cứ lấy cạnh rẻ nhất” mà **không kiểm tra chu trình** có thể tạo tập cạnh sai. Kruskal chọn cạnh rẻ nhất **an toàn đối với cấu trúc rừng đang xây**, không chỉ chọn cạnh có trọng số nhỏ.

### 9.2. Java 17: Kruskal dùng Disjoint Set Union

Lưu thành **KruskalGreedyDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class KruskalGreedyDemo {
    record Edge(int u, int v, int weight) {
        @Override
        public String toString() {
            return u + "-" + v + "(" + weight + ")";
        }
    }

    static final class DSU {
        private final int[] parent;
        private final int[] rank;

        DSU(int n) {
            parent = new int[n];
            rank = new int[n];
            for (int i = 0; i < n; i++) {
                parent[i] = i;
            }
        }

        int find(int x) {
            if (parent[x] != x) {
                parent[x] = find(parent[x]);
            }
            return parent[x];
        }

        boolean union(int a, int b) {
            int ra = find(a), rb = find(b);
            if (ra == rb) {
                return false; // Thêm cạnh này sẽ tạo chu trình.
            }
            if (rank[ra] < rank[rb]) {
                parent[ra] = rb;
            } else if (rank[ra] > rank[rb]) {
                parent[rb] = ra;
            } else {
                parent[rb] = ra;
                rank[ra]++;
            }
            return true;
        }
    }

    static List<Edge> minimumSpanningTree(int vertices, List<Edge> edges) {
        if (vertices < 1) {
            throw new IllegalArgumentException("Require at least one vertex");
        }

        List<Edge> sorted = new ArrayList<>(edges);
        sorted.sort(Comparator.comparingInt(Edge::weight)
                .thenComparingInt(Edge::u)
                .thenComparingInt(Edge::v));

        DSU dsu = new DSU(vertices);
        List<Edge> chosen = new ArrayList<>();

        for (Edge edge : sorted) {
            if (edge.u() < 0 || edge.u() >= vertices
                    || edge.v() < 0 || edge.v() >= vertices) {
                throw new IllegalArgumentException("Invalid endpoint");
            }
            if (dsu.union(edge.u(), edge.v())) {
                chosen.add(edge);
                if (chosen.size() == vertices - 1) {
                    break;
                }
            }
        }

        if (chosen.size() != vertices - 1) {
            throw new IllegalArgumentException("Disconnected graph");
        }
        return chosen;
    }

    public static void main(String[] args) {
        List<Edge> edges = Arrays.asList(
            new Edge(0, 1, 1),
            new Edge(1, 2, 2),
            new Edge(2, 3, 3),
            new Edge(0, 3, 4),
            new Edge(0, 2, 5)
        );

        List<Edge> mst = minimumSpanningTree(4, edges);
        long weight = 0L;
        for (Edge edge : mst) {
            weight += edge.weight();
        }

        System.out.println("MST edges: " + mst);
        System.out.println("MST weight: " + weight);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 KruskalGreedyDemo.java
java KruskalGreedyDemo
```

Stdout:

```text
MST edges: [0-1(1), 1-2(2), 2-3(3)]
MST weight: 6
```

**Độ phức tạp:** với `V` đỉnh và `E` cạnh, sắp xếp cạnh tốn `O(E log E)`, DSU với nén đường đi và union-by-rank xử lý gần hằng số trung bình được mô tả bằng `O(E α(V))` cho các thao tác, nên toàn thuật toán thường ghi **`O(E log E)`** thời gian. Bộ nhớ ngoài đầu vào là `O(E+V)` vì mã sao chép danh sách cạnh, giữ danh sách đã chọn và mảng DSU.

Nếu đồ thị **không liên thông**, mã ném ngoại lệ; nếu mục tiêu là **rừng khung nhỏ nhất** trên đồ thị bất kỳ, cần đổi hợp đồng đầu ra và bỏ yêu cầu đúng `V-1` cạnh.

## 10. Đường đi ngắn nhất: Dijkstra và giới hạn của tham lam

Dijkstra là ví dụ greedy khác: ở mỗi bước, chọn đỉnh **chưa cố định** có khoảng cách tạm thời nhỏ nhất tính từ nguồn và **chốt** khoảng cách của nó.

Với đồ thị có **trọng số cạnh không âm**, khi đỉnh `u` có khoảng cách tạm thời nhỏ nhất, không thể có một đường đi qua các đỉnh chưa chốt rồi quay về tạo khoảng cách **nhỏ hơn** cho `u`: đoạn đi thêm qua các cạnh không âm không thể giảm tổng độ dài so với khoảng cách tạm thời tối thiểu đang xét. Đây là trực giác của bất biến “khoảng cách của các đỉnh đã chốt là tối ưu”.

**Tại sao trọng số không âm quan trọng?** Xét các cạnh có hướng:

```text
S → B:  2
S → C:  5
C → B: -10
```

- Từ S, khoảng cách tạm thời của B là `2`, của C là `5`.
- Dijkstra chuẩn sẽ **chốt B trước C** vì `2<5`.
- Nhưng đường đi S→C→B có tổng `5 + (-10) = -5`, **ngắn hơn 2**.

Vậy suy luận an toàn khi chốt B **không còn đúng**. Thuật toán xử lý cạnh âm cần điều kiện và phương pháp khác, ví dụ Bellman–Ford khi không có chu trình âm đạt được gây vô hạn âm.

**Không suy rộng:** một số cài đặt dùng priority queue có thể thêm lại đỉnh hoặc không đánh dấu cố định đúng kiểu Dijkstra; điều đó không làm định lý Dijkstra với cạnh âm trở nên đúng. Phải phát biểu thuật toán, chính sách chốt và các tiền điều kiện chính xác.

Trong MST, cạnh âm không gây vấn đề với Kruskal, nhưng trong shortest path, cạnh âm lại phá chứng minh chốt nhãn của Dijkstra. **Các thuật toán tham lam khác nhau có các điều kiện đúng khác nhau**.

## 11. Khung chứng minh tham lam: trao đổi, luôn đi trước và cấu trúc khả thi

### 11.1. Lập luận trao đổi

Dùng khi có thể biến đổi một nghiệm tối ưu bất kỳ thành nghiệm tối ưu **không kém** mà chứa quyết định của greedy.

Mẫu:

1. Chọn một nghiệm tối ưu `OPT`.
2. Xác định lựa chọn đầu tiên của greedy là `g`.
3. Nếu `OPT` đã có `g`, tốt.
4. Nếu không, tìm đối tượng `o` trong `OPT` có thể thay bằng `g`.
5. Chứng minh phương án sau thay thế **vẫn khả thi**.
6. Chứng minh giá trị mục tiêu **không kém**.
7. Suy ra có một nghiệm tối ưu chứa `g`, rồi xét bài toán còn lại.

**Không được bỏ bước khả thi**: một lựa chọn có điểm số cao hơn nhưng làm hỏng ràng buộc thì phép trao đổi không có nghĩa.

### 11.2. “Luôn đi trước” theo một thước đo

Dùng khi có một **thước đo trạng thái** sao cho sau mỗi `j` quyết định, greedy không bất lợi hơn một lời giải khác.

Ví dụ chọn lịch: sau `j` hoạt động, thời điểm kết thúc cuối của greedy **không muộn hơn** thời điểm kết thúc thứ `j` của bất kỳ lịch khả thi có ít nhất `j` hoạt động. Điều đó bảo đảm mọi bước tiếp theo mà lịch khác thực hiện được cũng còn khả thi cho greedy.

**Không chọn thước đo tùy ý:** “đi trước” phải liên hệ trực tiếp tới khả năng kéo dài thành lời giải hoặc mục tiêu toàn cục.

### 11.3. Cấu trúc kiểu matroid

Trong một số bài toán, các tập con khả thi thỏa các tính chất **di truyền** (bỏ phần tử vẫn khả thi) và **trao đổi** (*exchange*) của một matroid. Khi đó, với trọng số phù hợp, việc duyệt phần tử theo trọng số rồi thêm khi vẫn độc lập có thể tạo nghiệm tối ưu theo định lý greedy của matroid.

Ví dụ, **tập cạnh không tạo chu trình** trong một đồ thị là một hệ độc lập kiểu matroid đồ thị; đây là góc nhìn cấu trúc giải thích Kruskal. Tuy nhiên, không phải mọi ràng buộc chọn phần tử đều tạo matroid. Các lịch khoảng thời gian không chồng nhau nói chung không thể cứ sắp theo **trọng số** rồi chọn vì thiếu tính chất trao đổi cần thiết, như phản ví dụ lịch có trọng số.

Không cần dùng lý thuyết matroid để giải các bài cơ bản, nhưng biết rằng có **định lý về cấu trúc khả thi** giúp tránh quan niệm “tham lam đúng chỉ nhờ trực giác”.

### 11.4. Chứng minh bất biến khả thi và tối ưu là hai việc khác nhau

Một bất biến như:

> “Mỗi lần thêm một cạnh, không tạo chu trình.”

chỉ chứng minh rừng hiện tại hợp lệ. Để kết luận MST, còn cần tính chất lát cắt/trao đổi. Tương tự, “các hoạt động đã chọn không chồng nhau” không nói gì về việc đã chọn **nhiều nhất** hay chưa.

**Mẫu kiểm tra:** tách hai cột trong bài giải: bên trái là **vì sao kết quả hợp lệ**, bên phải là **vì sao không thể có kết quả tốt hơn**.

## 12. Khi greedy đúng cho chọn cục bộ nhưng không cho đầu ra khác

Ngay cả khi greedy tối ưu một **giá trị mục tiêu**, cần kiểm tra yêu cầu đầu ra cụ thể:

- **Chọn số hoạt động tối đa:** thuật toán chọn kết thúc sớm nhất có thể trả một lịch tối ưu, nhưng không nhất thiết là **lịch tối ưu duy nhất**.
- **Cây khung nhỏ nhất:** đồ thị có trọng số bằng nhau có thể có **nhiều MST** cùng tổng trọng số; thứ tự hòa có thể làm thay đổi tập cạnh nhưng không thay đổi trọng số tối ưu.
- **Ba lô phân số:** nếu nhiều vật có cùng mật độ, các phân bổ phần vật khác nhau có thể cho cùng tổng giá trị.
- **Đổi tiền:** nếu muốn **danh sách đồng** thay vì chỉ số lượng, DP phải có thêm thông tin tái dựng nghiệm; `dp[amount]` một mình chỉ lưu giá trị tối ưu.
- **Đường đi ngắn nhất:** nhiều đường đi có cùng độ dài; bài yêu cầu đường đi có ít cạnh nhất khi hòa thì cần quy tắc phụ hoặc tối ưu từ điển rõ ràng.

Đề bài cần xác định **một nghiệm tối ưu bất kỳ**, **nghiệm xác định theo quy tắc phụ**, hay **liệt kê mọi nghiệm tối ưu**. Ba yêu cầu có thể có chi phí rất khác nhau.

## 13. Greedy và quy hoạch động: điểm khác biệt thực tế

| Đặc điểm | Greedy | Quy hoạch động (DP) |
|---|---|---|
| Cách ra quyết định | Chọn một quyết định cục bộ và tiếp tục | Xét/so sánh nhiều quyết định qua trạng thái |
| Điều kiện để tối ưu | Cần greedy-choice property và lập luận đúng | Cần trạng thái/quan hệ chuyển chính xác và cấu trúc con |
| Khả năng quay lại | Thường không sửa quyết định đã chốt | Giá trị tối ưu được lưu so sánh giữa nhiều nhánh |
| Tài nguyên | Có thể rất gọn, thường sort + scan/heap | Phụ thuộc số trạng thái và số chuyển |
| Ví dụ điển hình | Chọn lịch không trọng số, fractional knapsack, MST | Đổi tiền mệnh giá bất kỳ, lịch có trọng số, 0/1 knapsack |

Cần thận trọng: DP không “tự động đúng” nếu chọn sai trạng thái hoặc quan hệ chuyển; greedy cũng có thể dùng dữ liệu phụ, heap, DSU và sắp xếp mà vẫn là greedy vì **cách chốt quyết định** là cục bộ.

### 13.1. Khi nào nên thử greedy trước?

Greedy đáng thử khi:

- Một quyết định có thể làm giảm bài toán còn lại mà **không hại chất lượng tối ưu**, có thể chứng minh bằng trao đổi.
- Các phương án khả thi có cấu trúc giống chọn hoạt động, chọn cạnh an toàn của rừng, hoặc chọn tỷ lệ giá trị liên tục.
- Đầu vào lớn, muốn thuật toán `O(n log n)` hoặc `O(n)` sau khi sắp, và có thể chứng minh tiêu chí chọn đúng.

Nhưng nếu **không tìm được chứng minh**, hãy cố tìm **phản ví dụ nhỏ** trước khi triển khai hoặc nộp kết luận. Một greedy có phản ví dụ chỉ là heuristic, trừ khi bài chấp nhận nghiệm xấp xỉ.

### 13.2. Greedy xấp xỉ khác greedy tối ưu

Một số bài toán khó không có greedy luôn tối ưu, nhưng một quy tắc tham lam vẫn có **bảo đảm xấp xỉ**. Ví dụ, một số phiên bản bài toán phủ tập (*set cover*) dùng chiến lược chọn tập bao phủ nhiều phần tử chưa phủ nhất theo chi phí để đạt bảo đảm xấp xỉ theo log kích thước tập cần phủ.

Khi đó phải phát biểu rõ: thuật toán **khả thi** và có **tỷ lệ xấp xỉ được chứng minh**, **không phải** lời giải tối ưu tuyệt đối. Không được gọi heuristic bất kỳ là “tối ưu” nếu chỉ thấy kết quả khá tốt trên vài bộ test.

## 14. Độ phức tạp của các bài greedy trong bài học

| Bài toán | Quy tắc | Chi phí thường dùng | Bộ nhớ phụ điển hình |
|---|---|---|---|
| Chọn hoạt động tối đa | Kết thúc sớm nhất, rồi quét | `O(n log n)` do sort; `O(n)` nếu đầu vào đã theo thứ tự end | `O(n)` khi sao chép dữ liệu và giữ output |
| Fractional knapsack | Mật độ giá trị giảm dần | `O(n log n)` do sort | `O(n)` khi sao chép thứ tự |
| Kruskal MST | Cạnh nhẹ nhất không tạo chu trình | `O(E log E + E α(V))` | `O(E+V)` trong mã ví dụ |
| Dijkstra với heap nhị phân | Chốt đỉnh có nhãn nhỏ nhất | Thường `O((V+E) log V)` theo cách cài đặt heap thích hợp | Thường `O(V+E)` tính cả cấu trúc đồ thị/heap |
| Đổi tiền greedy | Đồng lớn nhất trước | Phụ thuộc số mệnh giá và số đồng được xuất | Phụ thuộc số đồng output |
| Đổi tiền DP theo amount | Xét mọi mệnh giá tại từng tổng | `O(amount × m)` với `m` mệnh giá | `O(amount)` |

Bảng là các chặn/đặc trưng thuật toán theo cài đặt và giả định thích hợp, **không phải** cam kết về mọi cách viết thư viện. Với Dijkstra, có nhiều biến thể priority queue và cách xử lý phần tử trùng; khi đẩy nhiều bản sao vào heap mà không có `decrease-key`, một chặn an toàn thường xét theo số lần đẩy/nhổ và kích thước heap thực tế, ví dụ `O((V+E) log(V+E))`. Hãy nêu phiên bản cụ thể nếu cần phân tích chặt.

Trong Java, `Arrays.sort` và `Comparator` xử lý bản ghi theo cơ chế khác sắp số nguyên; với một comparator nhất quán và dữ liệu nhỏ hay lớn, các ví dụ ở đây dùng cách sắp **`O(n log n)` tiệm cận**. Tránh đánh giá toàn thuật toán chỉ dựa trên vòng `for` chọn ứng viên mà bỏ chi phí sort.

## 15. Kiểm thử greedy bằng phản ví dụ và oracle

Kiểm thử không thay thế chứng minh, nhưng cực kỳ hữu ích để **bác bỏ** một tiêu chí tham lam sai.

### 15.1. Liệt kê hết với dữ liệu nhỏ

Với `n` hoạt động nhỏ (`n<=20` để minh họa), có thể xét tất cả `2^n` tập con, bỏ các tập xung đột và tìm số phần tử lớn nhất. So sánh kết quả greedy với **oracle vét cạn** trên nhiều bộ dữ liệu nhỏ.

- Nếu tìm được một bộ mà greedy kém hơn oracle, tiêu chí **sai**.
- Nếu không tìm thấy, chỉ có **bằng chứng kiểm thử**, chưa chứng minh cho mọi đầu vào.
- Dữ liệu sinh phải đúng hợp đồng: hoạt động có `start<end`, quy tắc giao nhau rõ ràng, xử lý trùng và ngưỡng đúng.

Tương tự, với hệ mệnh giá nhỏ và số tiền nhỏ, dùng DP để đối chiếu số đồng greedy; với ba lô 0/1 nhỏ, liệt kê tập con để tìm phản ví dụ chọn mật độ.

### 15.2. Thiết kế phản ví dụ có mục tiêu

Các kiểu dữ liệu nên thử:

1. **Lựa chọn cục bộ chiếm tài nguyên lớn:** một hoạt động dài bắt đầu sớm chặn nhiều hoạt động ngắn.
2. **Nhiều phần tử có điểm bằng nhau:** kiểm tra tie-breaking có khiến thay đổi nghiệm đúng hay không.
3. **Phần tử có tỷ lệ đẹp nhưng khối lượng lớn:** với 0/1 knapsack, nó có thể cản một tổ hợp tốt hơn.
4. **Mệnh giá không có tính chất chuẩn:** đồng lớn nhất trước có thể tốn nhiều đồng hơn.
5. **Biên giá trị:** mảng rỗng, một phần tử, số âm ở thuật toán có cho phép hay không, sức chứa bằng 0.
6. **Ràng buộc thay đổi nhỏ:** thêm trọng số, cấm chia vật, cạnh âm, khoảng đóng thay nửa mở; một thay đổi có thể phá chứng minh cũ.

### 15.3. Kiểm tra ba tầng kết quả

Với mọi lời giải greedy cần kiểm tra:

- **Khả thi:** không vi phạm constraint (không chồng hoạt động, không vượt sức chứa, không tạo chu trình).
- **Giá trị:** tổng số hoạt động, tổng lợi nhuận, tổng trọng số MST hoặc khoảng cách đáp ứng mục tiêu.
- **Tối ưu:** nếu có oracle nhỏ hoặc chứng minh, giá trị greedy không kém mọi phương án khả thi.

Ví dụ một lời giải hoạt động có 4 cuộc họp hợp lệ chỉ được gọi **tối ưu** khi có chứng minh rằng không thể chọn 5 cuộc hợp lệ; số 4 một mình chưa đủ.

## 16. Các sai lầm thường gặp khi suy luận về tham lam

### 16.1. “Cứ lấy lớn nhất hoặc nhỏ nhất” mà không biết tiêu chí đúng

Chọn phần tử lớn nhất có thể hợp với mục tiêu này nhưng sai với mục tiêu khác. Ví dụ đổi tiền `{1,3,4}` với số tiền 6 chứng minh ngay rằng chọn mệnh giá lớn nhất không luôn tối thiểu số đồng.

### 16.2. Chỉ chứng minh lời giải khả thi

Một lịch không trùng nhau chưa chắc có **nhiều hoạt động nhất**; một rừng không chu trình chưa chắc có **trọng số nhỏ nhất**. Cần chứng minh tối ưu, thường qua trao đổi hoặc bất biến tối ưu.

### 16.3. Dùng “cấu trúc con tối ưu” làm chứng minh duy nhất

0/1 knapsack và weighted interval scheduling có cách lập DP theo bài toán con nhưng greedy đơn giản vẫn sai. Cần chứng minh rằng **lựa chọn cụ thể của greedy** có thể nằm trong một nghiệm tối ưu.

### 16.4. Trao đổi làm thay đổi tính khả thi

Thay một hoạt động bằng hoạt động khác phải bảo đảm không xung đột với hoạt động còn lại. Thay cạnh trong MST phải giữ cây liên thông, không chu trình. Nếu bỏ bước này, lập luận trao đổi không hợp lệ.

### 16.5. Thay đổi giả thiết mà giữ nguyên chứng minh

Greedy fractional knapsack dựa vào phép chuyển **một phần trọng lượng**. Trong 0/1 knapsack, không được chuyển `δ` tùy ý. Dijkstra dựa vào cạnh không âm; cạnh âm có thể tạo đường đi rẻ hơn sau khi đỉnh đã chốt.

### 16.6. Nhầm nhiệm vụ tối đa số lượng và tối đa tổng giá trị

Chọn hoạt động theo `end` sớm giải bài **unweighted**. Thêm `weight_i` mà giữ nguyên code có thể trả lịch ít lợi nhuận hơn tối ưu rất nhiều.

### 16.7. Không làm rõ ranh giới khoảng thời gian

Với khoảng `[start,end)`, điều kiện tiếp theo là `next.start>=previous.end`. Nếu đề quy định hai công việc chạm đầu mút vẫn xung đột, phải đổi điều kiện. Quy tắc giao nhau khác làm thay đổi tập phương án khả thi.

### 16.8. Bỏ tính chi phí sort/heap/DSU

Thuật toán greedy có thể chỉ quét một lần sau khi đã sắp, nhưng bước sort vẫn là `O(n log n)`. Kruskal còn dùng DSU để kiểm tra an toàn của cạnh; không thể chỉ ghi chi phí duyệt `E` cạnh.

### 16.9. So sánh số nguyên bằng phép trừ gây tràn

Không viết `(a,b)->a.end()-b.end()` cho mọi giá trị `int`; có thể tràn và phá thứ tự comparator. Dùng `Integer.compare`, `Comparator.comparingInt`, hoặc phép so sánh được xác thực.

### 16.10. Bỏ qua quy tắc hòa và kết quả xác định

Khi nhiều lựa chọn có cùng điểm, các nghiệm tối ưu có thể khác nhau. Nếu hệ thống cần kết quả lặp lại, thêm khóa phụ nhất quán (thời điểm, ID) và kiểm tra chính sách hòa có còn đáp ứng yêu cầu tối ưu hay không.

### 16.11. Lẫn lộn đồ thị có hướng và vô hướng

Kruskal/MST được xác định cho **đồ thị vô hướng** theo mô hình chuẩn. Không áp dụng nguyên mã đó để tìm một “cây khung có hướng” tối ưu; bài toán nhánh cây có hướng có thuật toán khác và ràng buộc khác.

### 16.12. Gọi thuật toán xấp xỉ là “tối ưu”

Một heuristic có thể nhanh và cho đáp án tốt trên nhiều test nhưng chưa chắc đạt tối ưu. Nếu có chỉ tiêu xấp xỉ hoặc được phép sai số, phải trình bày **độ bảo đảm** thay vì dùng từ “luôn tối ưu”.

## 17. Bài tập tự luyện có lời giải

### Bài 1 — Chọn lịch

Các khoảng nửa mở:

```text
A [0,2)
B [1,3)
C [2,4)
D [3,5)
E [4,6)
```

Dùng quy tắc kết thúc sớm nhất để chọn tối đa số hoạt động.

**Đáp án:** A `[0,2)`, C `[2,4)`, E `[4,6)` → 3 hoạt động. Các đầu mút chạm nhau không xung đột do quy ước nửa mở.

### Bài 2 — Chứng minh sai của tiêu chí bắt đầu sớm nhất

Cho A `[1,10)`, B `[2,3)`, C `[3,4)`, D `[4,5)`. Vì sao chọn bắt đầu sớm nhất sai?

**Đáp án:** chọn A chỉ được 1 hoạt động; B,C,D chọn được 3. Một phản ví dụ đủ bác bỏ quy tắc “luôn tối ưu”.

### Bài 3 — Trao đổi trong chọn lịch

Giả sử `g` là hoạt động kết thúc sớm nhất trong toàn bộ danh sách; `o` là hoạt động đầu tiên của một lịch tối ưu. Cần so sánh đại lượng nào để bảo đảm thay `o` bằng `g` không làm hỏng các hoạt động sau?

**Đáp án:** `end(g)<=end(o)`. Vì hoạt động tiếp theo bắt đầu không trước `end(o)`, nó cũng bắt đầu không trước `end(g)`, nên không xung đột khi thay.

### Bài 4 — Weighted scheduling

Với A `[0,2)` lợi nhuận 2, B `[2,4)` lợi nhuận 2, C `[0,4)` lợi nhuận 10, chọn kết thúc sớm nhất có tối ưu không?

**Đáp án:** không. A+B được tổng 4, trong khi chọn C được 10. Mục tiêu thay đổi phá chứng minh của bài không trọng số.

### Bài 5 — Đổi tiền

Mệnh giá `{1,3,4}`, số tiền 6. Greedy và tối ưu dùng bao nhiêu đồng?

**Đáp án:** greedy chọn `[4,1,1]` (3), tối ưu `[3,3]` (2). Không thể khẳng định greedy đúng cho mọi hệ mệnh giá.

### Bài 6 — Ba lô phân số và 0/1

Với các vật A `(value=60,weight=10)`, B `(100,20)`, C `(120,30)`, `W=50`:

- Nếu được lấy phân số, giá trị tối ưu theo greedy là bao nhiêu?
- Nếu chỉ lấy nguyên vật, chọn theo mật độ giảm có đạt tối ưu không?

**Đáp án:** phân số đạt `240` (A+B+`2/3` C). Với 0/1, greedy mật độ chọn A+B được `160`, nhưng B+C được `220`, nên không tối ưu.

### Bài 7 — Kruskal

Đồ thị vô hướng có các cạnh `(0,1,1)`, `(1,2,2)`, `(2,3,3)`, `(0,3,4)`, `(0,2,5)`. Kruskal chọn cạnh nào, tổng trọng số?

**Đáp án:** `(0,1,1)`, `(1,2,2)`, `(2,3,3)`; tổng `1+2+3=6`. Sau khi có 3 cạnh cho 4 đỉnh, cây khung đã hoàn thành.

### Bài 8 — Dijkstra cạnh âm

Với `S→B=2`, `S→C=5`, `C→B=-10`, tại sao không thể chốt B ở khoảng cách 2 theo Dijkstra chuẩn?

**Đáp án:** đường đi `S→C→B` có tổng `-5`, nhỏ hơn 2. Cạnh âm phá tính chất an toàn của lựa chọn khoảng cách tạm thời nhỏ nhất.

### Bài 9 — Nhận diện loại chứng minh

Một bạn chỉ chứng minh “mọi cạnh Kruskal thêm vào đều nối hai thành phần khác nhau”. Bạn đó đã chứng minh MST tối ưu chưa?

**Đáp án:** chưa. Điều kiện đó bảo đảm **không tạo chu trình**; còn phải chứng minh **không thể giảm tổng trọng số**, thường dùng tính chất lát cắt hoặc trao đổi với một MST.

### Bài 10 — Bài toán có nhiều nghiệm tối ưu

Nếu hai hoạt động có cùng thời điểm kết thúc và cùng khả năng nối tiếp, việc chọn một trong hai có thể tạo hai lịch khác nhau cùng số lượng. Có bắt buộc chỉ có một đáp án duy nhất không?

**Đáp án:** không, trừ khi đề quy định quy tắc hòa hoặc yêu cầu danh sách xác định. Thuật toán vẫn có thể đạt giá trị mục tiêu tối ưu với nhiều nghiệm.

## 18. Checklist trước khi nộp một thuật toán tham lam

1. **Viết đúng mục tiêu toàn cục:** cực đại số lượng, tổng giá trị, cực tiểu chi phí hay khoảng cách?
2. **Định nghĩa tính khả thi:** khoảng nửa mở/đóng, vật có chia được không, cạnh có tạo chu trình không, ràng buộc dấu của trọng số?
3. **Đề xuất một lựa chọn cục bộ cụ thể:** kết thúc sớm, mật độ lớn nhất, cạnh nhẹ nhất an toàn, nhãn khoảng cách nhỏ nhất.
4. **Chọn dữ liệu sắp xếp/ưu tiên phù hợp:** comparator nhất quán, an toàn tràn và quy tắc hòa rõ ràng.
5. **Chứng minh khả thi:** sau mỗi quyết định, trạng thái vẫn đáp ứng ràng buộc.
6. **Chứng minh an toàn của lựa chọn:** có một nghiệm tối ưu có thể chứa quyết định ấy, thường qua **exchange argument** hoặc **stays ahead**.
7. **Chứng minh bài toán còn lại:** sau khi cố định lựa chọn, phần dư có đúng cấu trúc để tiếp tục greedy không?
8. **Kiểm tra phản ví dụ:** thử bản trọng số, bản 0/1, hệ mệnh giá lạ, cạnh âm, đầu vào biên và hòa.
9. **Xác định nghiệm đầu ra:** một nghiệm tối ưu bất kỳ, nghiệm theo tie-breaker hay tất cả nghiệm?
10. **Phân tích đủ chi phí:** sort, heap, DSU, quét, bộ nhớ bản sao/output.
11. **Kiểm thử nhỏ với oracle:** brute force/DP trên bộ nhỏ để tìm lỗi, nhưng không coi test là chứng minh.
12. **Phát biểu chính xác bảo đảm:** tối ưu tuyệt đối, tối ưu kỳ vọng, xấp xỉ có tỷ lệ, hay chỉ là heuristic.

**Ghi nhớ:** một thuật toán tham lam đưa ra **lựa chọn cục bộ**, nhưng đề bài yêu cầu **tối ưu toàn cục**. Khoảng cách giữa hai khái niệm chỉ được nối bằng một **chứng minh đúng với ràng buộc cụ thể**. Chọn hoạt động kết thúc sớm nhất, lấy vật theo mật độ trong ba lô phân số hay thêm cạnh an toàn nhẹ nhất trong Kruskal là các quy tắc có cơ sở trao đổi; lấy đồng lớn nhất cho mọi hệ tiền hoặc chọn vật theo mật độ trong ba lô 0/1 thì không.
