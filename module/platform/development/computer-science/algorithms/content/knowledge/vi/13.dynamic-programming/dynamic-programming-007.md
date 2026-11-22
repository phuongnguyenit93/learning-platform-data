# Trạng thái không thể đạt và giá trị khởi tạo trong quy hoạch động

**Quy hoạch động (Dynamic Programming, DP)** lưu lời giải của những **trạng thái con** rồi kết hợp chúng theo một công thức chuyển trạng thái. Nhưng không phải trạng thái nào trong bảng cũng có thể xuất hiện từ trạng thái xuất phát hợp lệ. Một sai lầm rất phổ biến là **khởi tạo tất cả các ô bằng `0` mà không xét ý nghĩa của `0`**, khiến trạng thái không thể đạt bị nhầm thành một lời giải hợp lệ.

Hãy phân biệt ngay ba câu hỏi:

1. **Trạng thái biểu diễn điều gì?** Ví dụ `dp[s]` có thể là số đồng xu tối thiểu để đạt **chính xác** tổng `s`, số cách tạo tổng `s`, hoặc điểm số lớn nhất của một đường đi đạt chính xác `s`.
2. **Trạng thái nào là cơ sở có thật?** Chẳng hạn tổng `0` đạt được bằng cách không chọn đồng xu nào; đây là một trường hợp hợp lệ và có thể làm gốc cho các bước chuyển.
3. **Trạng thái nào chưa thể đạt?** Ví dụ chỉ có bước tăng `2` và `4` thì tổng `3` không thể được tạo thành. Không được coi nó là một lời giải có chi phí `0` chỉ vì mảng Java mặc định chứa các số `0`.

**Nguyên tắc chung:** *giá trị khởi tạo phải khớp với phép toán của công thức chuyển và phải phân biệt được trạng thái có lời giải với trạng thái không có lời giải*. Không tồn tại một sentinel phù hợp cho mọi bài DP.

## 1. Thế nào là một trạng thái không thể đạt?

Giả sử bài toán có tập trạng thái `S`, trạng thái xuất phát `s_0` và các phép chuyển hợp lệ. Một trạng thái `s` gọi là **có thể đạt (reachable)** nếu tồn tại ít nhất một chuỗi phép chuyển hợp lệ từ `s_0` tới `s`. Nếu không có chuỗi nào như vậy, `s` là **không thể đạt (unreachable)**.

Ví dụ, từ tổng `0` chỉ được cộng `2` hoặc `5`, mỗi bước dùng tùy ý số lần:

```text
Bắt đầu: 0
Các bước hợp lệ: +2 hoặc +5

Có thể đạt:   0, 2, 4, 5, 6, 7, 8, 9, 10, ...
Không đạt:    1, 3

Đường đi tới 7: 0 -> 2 -> 5?  (sai: 2 -> 5 là +3)
Đường đi đúng:  0 -> 2 -> 4 -> 6?  (+2 hợp lệ)
                0 -> 5 -> 7       (+5, rồi +2)
```

Một trạng thái không thể đạt không có nghĩa là chương trình **chưa tính** trạng thái đó. Đây là hai khái niệm riêng:

- **Unreachable:** đã xét đúng những khả năng hợp lệ nhưng **không tồn tại** lời giải.
- **Uncomputed / chưa tính:** thuật toán chưa thực hiện phép tính hoặc lời gọi đệ quy cho trạng thái ấy.
- **Reachable with value 0:** tồn tại lời giải và giá trị tối ưu hoặc số liệu của lời giải đúng bằng `0`. Trường hợp này có thật trong nhiều bài toán.

Cần phân biệt cả ba vì một sentinel như `-1`, `0` hay `null` có thể có ý nghĩa khác tùy hợp đồng DP. Trong **DP đệ quy có ghi nhớ (memoization)**, cờ `visited`/`computed` biểu thị **đã tính** khác với cờ `reachable` biểu thị **có lời giải**.

### Định nghĩa trạng thái phải nói rõ “chính xác” hay “không vượt quá”

Với `dp[s]` là **chi phí tối thiểu để tạo chính xác tổng `s`**, trạng thái `3` có thể không đạt khi chỉ có bước `2` và `4`.

Nhưng với `dp[b]` là **giá trị lớn nhất khi dùng không quá `b` đơn vị ngân sách**, phương án **không làm gì** có thể hợp lệ ở **mọi** mức ngân sách, nên một số trạng thái có giá trị cơ sở `0`. Không được bê nguyên cách khởi tạo của bài **không vượt quá** sang bài **chính xác** hoặc ngược lại.

## 2. Ba kiểu DP và ba giá trị khởi tạo khác nhau

Ta thường gặp ba kiểu bài toán:

| Loại DP | Ý nghĩa `dp[s]` | Trạng thái cơ sở `s=0` | Biểu diễn không thể đạt |
|---|---|---|---|
| **Tối thiểu hóa (min)** | Chi phí/số bước ít nhất để đạt đúng `s` | `0` | `+∞` hoặc một sentinel `INF` hợp lệ |
| **Tối đa hóa (max)** | Điểm cao nhất trong các đường đi đạt đúng `s` | `0` | `-∞` hoặc cờ `reachable=false` |
| **Đếm số cách (count)** | Số chuỗi thao tác hợp lệ đạt đúng `s` | `1` cho chuỗi rỗng | `0` cách |
| **Khả thi (boolean)** | Có tồn tại đường đi đạt đúng `s`? | `true` | `false` |

Đây không phải “bảng thần chú”. Tất cả giá trị chỉ đúng **khi trạng thái mang chính xác ý nghĩa đã mô tả**. Nếu bài toán bắt buộc dùng ít nhất một thao tác, có phí khởi động, trạng thái xuất phát bị chặn hoặc có nhiều điểm bắt đầu thì **cơ sở phải thay đổi tương ứng**.

### Vì sao min thường dùng `INF`?

Khi lấy `min`, một trạng thái không có phương án nào phải **không thắng** một phương án có chi phí hữu hạn. Trong số học mở rộng, `min(x,+∞)=x`. Vì vậy, trước khi có đường chuyển hợp lệ, ta có thể hiểu chi phí của trạng thái là `+∞`.

### Vì sao max thường dùng `-INF`?

Khi lấy `max`, một trạng thái không có phương án nào không nên thắng điểm số của một phương án thật, kể cả điểm số **âm**. Trong số học mở rộng, `max(x,-∞)=x`. Nếu khởi tạo max DP bằng `0` cho tất cả trạng thái, điểm số âm hợp lệ như `-7` có thể bị thay sai bởi `0` của một trạng thái không tồn tại.

### Vì sao đếm cách dùng `0`, còn cơ sở dùng `1`?

Trong DP đếm số cách, một trạng thái không đạt có **0 cách**. Nhưng từ tổng `0` tới chính nó có **một chuỗi thao tác rỗng**. Chuỗi rỗng là đơn vị của phép ghép chuỗi; vì vậy:

\[
ways[0]=1,\qquad ways[s]=0\quad (s>0)\text{ trước khi chuyển}.
\]

Nếu đặt `ways[0]=0`, một công thức đếm chỉ cộng từ các trạng thái trước sẽ lan truyền toàn `0`, kể cả khi đáp án đúng khác `0`.

**Tuy nhiên:** nếu đếm **theo modulo `M`**, giá trị `ways[s] % M = 0` có thể xuất hiện ngay cả khi có rất nhiều cách; khi đó **không thể** dùng một kết quả modulo bằng `0` để suy ra trạng thái không đạt. Cần cờ khả thi riêng nếu thuật toán còn cần biết có ít nhất một cách hay không.

## 3. Ví dụ min DP: số đồng xu ít nhất để tạo đúng tổng

Cho các mệnh giá nguyên dương trong tập `coins`, mỗi mệnh giá được phép dùng **không giới hạn số lần**. Cần số đồng xu tối thiểu để tạo **chính xác** tổng nguyên không âm `target`. Nếu không thể tạo, trả “không thể đạt” thay vì tự coi là `0` đồng xu.

Đặt `dp[s]` là số đồng xu ít nhất để tạo đúng `s`. Công thức:

\[
dp[0]=0,
\]

\[
dp[s]=\min_{\substack{c\in coins\\c\le s\\dp[s-c]\ne INF}}
          \{dp[s-c]+1\},\qquad s\ge 1.
\]

Nếu không có mệnh giá `c` nào dẫn từ một trạng thái đạt được tới `s`, giữ `dp[s]=INF`.

**Vì sao cần điều kiện `dp[s-c]!=INF`?** Giá trị `INF` chỉ là ký hiệu trong chương trình, không phải chi phí của một lời giải thật. Nếu lấy `INF+1` để tạo ứng viên, ta có thể đếm nhầm một đường đi không tồn tại; nếu sentinel ở sát giới hạn kiểu số, còn có nguy cơ **tràn số**.

### Bảng ví dụ với `coins={2,5}`

| Tổng s | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `dp[s]` | 0 | INF | 1 | INF | 2 | 1 | 3 | 2 |

- `dp[0]=0` vì không lấy đồng nào.
- `dp[1]=INF` và `dp[3]=INF` vì không thể tạo đúng các tổng đó.
- `dp[4]=2` qua `2+2`; `dp[5]=1` qua một đồng `5`.
- `dp[7]=2` qua `2+5`.
- Khi tính `dp[6]`, ta có thể dùng `dp[4]+1=3`, **không** được dùng `dp[1]+1` vì `dp[1]` không thể đạt.

**Phản ví dụ cho khởi tạo sai:** nếu Java tạo `new int[target+1]` và để mọi ô mặc định `0`, với mệnh giá `{4,6}` và tổng `7`, giá trị `dp[7]=0` sẽ giống “cần 0 đồng xu” dù thực tế không thể tạo `7`. Dùng `0` làm giá trị khởi tạo ở những trạng thái chưa đạt là sai với định nghĩa **min số đồng xu cho tổng chính xác**.

### Chiến lược cài đặt

- Khởi tạo toàn bộ `dp` bằng một sentinel `INF` đủ lớn.
- Gán riêng `dp[0]=0`.
- Duyệt `s` tăng từ `1` tới `target`. Vì mọi `c>0`, `s-c<s` nên trạng thái phụ thuộc đã được tính.
- Chỉ cập nhật từ `dp[s-c]` nếu nó **thật sự đạt được**.
- Cuối cùng, nếu `dp[target]==INF` thì trả “không thể đạt”; ngược lại trả số đồng xu tối thiểu.

Điều kiện `c>0` là một **tiền điều kiện** của mô hình này. Nếu cho phép mệnh giá `0` hoặc âm, tính thứ tự duyệt và định nghĩa số cách/đường đi có thể thay đổi; không áp dụng lại công thức này như thể mọi chuyển đều đi từ trạng thái nhỏ hơn.

## 4. Ví dụ max DP: trạng thái đạt được có điểm số âm

Xét bài toán: bắt đầu với tổng chi phí `0`. Mỗi lần chọn một thao tác có **chi phí nguyên dương** `cost` và **điểm thưởng/phạt nguyên** `reward`, được chọn thao tác nhiều lần. Cần đạt **đúng** tổng chi phí `target` và tối đa tổng điểm. Điểm có thể **âm**.

Đặt:

- `reachable[s]`: có ít nhất một chuỗi thao tác tạo đúng tổng chi phí `s` không?
- `best[s]`: điểm tối đa **chỉ có ý nghĩa khi `reachable[s]==true`**.

Khởi tạo:

```text
reachable[0] = true
best[0] = 0

reachable[s] = false, s > 0
best[s] có thể để 0 mặc định, nhưng TUYỆT ĐỐI không đọc
nó như một đáp án khi reachable[s] == false.
```

Với thao tác `(cost,reward)`, nếu `cost<=s` và `reachable[s-cost]` thì:

\[
candidate=best[s-cost]+reward.
\]

Nếu `s` chưa đạt, ta có thể gán `best[s]=candidate` và bật cờ. Nếu `s` đã đạt, đặt `best[s]=\max(best[s],candidate)`.

### Ví dụ mọi điểm đều âm

Có hai thao tác:

- `A=(cost=2,reward=-5)`.
- `B=(cost=3,reward=-2)`.

Bảng kết quả:

| Tổng chi phí s | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| Có thể đạt? | Có | Không | Có | Có | Có | Có | Có |
| `best[s]` khi đạt | 0 | — | -5 | -2 | -10 | -7 | -4 |

Với `target=5`, chỉ có cách chọn một thao tác A và một thao tác B (theo thứ tự nào cũng được), tổng điểm **`-7`**. Với `target=6`, tốt nhất là B+B đạt **`-4`**, tốt hơn A+A+A đạt `-15`.

Nếu sai lầm khởi tạo `best[s]=0` và dùng trực tiếp `max(best[s],candidate)` mà **không có cờ khả thi**, giá trị `0` của trạng thái chưa đạt sẽ thắng các điểm âm `-5`, `-2` và `-7`. Kết quả có vẻ “không làm gì” nhưng lại vi phạm yêu cầu **đạt đúng chi phí mục tiêu**.

### Có thể dùng `-INF` thay cờ không?

Có, nếu chứng minh được rằng **mọi điểm số hợp lệ đều lớn hơn sentinel**, và phép tính `dp[prev]+reward` không vượt miền số. Nhưng chọn một số “rất âm” tùy ý rồi cộng vào nó là một nguồn lỗi:

- Giá trị “rất âm” có thể trùng hoặc lớn hơn một **điểm số âm hợp lệ**.
- Cộng số âm vào `Long.MIN_VALUE` có thể **tràn số** và cho kết quả dương.
- Kiểm tra bằng `== sentinel` có thể nhầm với một giá trị đạt được bằng số học nếu không bảo vệ miền giá trị.

Ví dụ Java bên dưới dùng **`boolean[] reachable` + `long[] best`**, giúp biểu diễn “không đạt” **tách biệt hẳn** khỏi mọi điểm số hợp lệ. Không phải chọn một sentinel thích hợp cho điểm max.

## 5. Ví dụ DP đếm: trạng thái không thể đạt có 0 cách

Giả sử có các bước tăng nguyên dương **phân biệt** `steps`. Từ tổng `0`, ta có thể dùng từng bước nhiều lần và **thứ tự các bước được tính là khác nhau**. Đặt `ways[s]` là số chuỗi bước có tổng đúng `s`.

Khởi tạo và chuyển:

\[
ways[0]=1,\qquad ways[s]=0 \ (s>0),
\]

\[
ways[s]=\sum_{\substack{c\in steps\\c\le s}}ways[s-c]
\quad\text{cho }s\ge 1.
\]

Với `steps={1,2}`:

| Tổng s | 0 | 1 | 2 | 3 | 4 | 5 |
|---:|---:|---:|---:|---:|---:|---:|
| `ways[s]` | 1 | 1 | 2 | 3 | 5 | 8 |

Có **5** chuỗi bước tạo đúng `4`:

```text
1+1+1+1
1+1+2
1+2+1
2+1+1
2+2
```

Nếu chỉ có các bước `{2,4}`, tổng `3` có **0 cách**; đó là một kết quả đếm đúng, không cần trả `INF`.

**Phải phân biệt “chuỗi có thứ tự” với “tổ hợp không xét thứ tự”.** Với `{1,2}` và tổng `4`:

- Nếu **thứ tự quan trọng**, có `5` cách như trên.
- Nếu **thứ tự không quan trọng**, chỉ có `3` cách: bốn đồng `1`; hai đồng `1` và một đồng `2`; hai đồng `2`.

Trong phiên bản đếm **chuỗi có thứ tự**, vòng ngoài duyệt tổng `s`, vòng trong duyệt từng bước `c`. Nếu chuyển sang vòng ngoài duyệt mệnh giá và vòng trong duyệt tổng tăng, bạn đang tính **tổ hợp không thứ tự** trong mô hình unlimited coin chuẩn. Cùng một khởi tạo `ways[0]=1` nhưng khác **ý nghĩa trạng thái** dẫn đến công thức/chiều duyệt khác.

### Vì sao ví dụ Java dùng `BigInteger`?

Số chuỗi bước thường tăng rất nhanh, có thể vượt `int` và `long`. Chẳng hạn với `{1,2}`, `ways[s]` đi theo dãy Fibonacci. Nếu chỉ cần đáp án modulo một số `M`, có thể dùng số nguyên và lấy modulo đúng cách; nhưng nếu cần số lượng **chính xác**, `BigInteger` tránh tràn số do đếm.

Nếu dùng Java `BigInteger[]`, cần khởi tạo từng phần tử bằng `BigInteger.ZERO`: mảng tham chiếu `new BigInteger[n]` mặc định chứa **`null`**, không phải đối tượng đại diện cho số `0`. Sau đó đặt `ways[0]=BigInteger.ONE`. Đây là một dạng lỗi khởi tạo khác với lỗi sentinel trong mảng `int[]`.

## 6. Java 17+ chạy được: ba hợp đồng DP cạnh nhau

Chương trình dưới đây chứa ba bài toán độc lập, mỗi bài minh họa một cách biểu diễn “không đạt” thích hợp:

1. `minCoins` — **min**: `INF` cho trạng thái không đạt, `0` cho tổng cơ sở.
2. `countOrderedWays` — **count**: `0` cách cho tổng không đạt, `1` cách cho chuỗi rỗng.
3. `maxRewardExact` — **max**: cờ `reachable` riêng để phân biệt điểm âm hợp lệ với trạng thái không đạt.

**Quy ước và kiểm tra đầu vào:**

- Tổng mục tiêu `target` phải không âm và đủ nhỏ để cấp mảng `target+1`; ví dụ chủ động từ chối `Integer.MAX_VALUE` để tránh tràn `target+1`.
- Mệnh giá/bước trong hai bài đầu phải là **số nguyên dương, không trùng nhau**. Các giá trị trùng được từ chối vì trong bài **đếm**, hai mục giống hệt nhau không nên làm tăng số cách giả tạo.
- Trong bài max, mọi thao tác có `cost>0`; có thể có nhiều thao tác cùng chi phí nhưng khác điểm thưởng.
- Những thao tác ở đây được phép dùng **không giới hạn số lần**. Không áp dụng nguyên công thức cho mô hình mỗi thao tác chỉ dùng một lần mà không thay đổi chiều duyệt.
- Trạng thái chưa đạt ở API min/max được trả bằng `OptionalLong.empty()`; không quy ước một số như `-1` là “không đạt”, vì `-1` có thể là **điểm hợp lệ** trong bài max.
- Mã không hứa xử lý các `target` cực lớn ngoài giới hạn bộ nhớ thực tế của máy.

Lưu thành tệp **`DpUnreachableDemo.java`**:

```java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.Objects;
import java.util.OptionalLong;

public final class DpUnreachableDemo {
    private static final long INF = Long.MAX_VALUE / 4;

    private DpUnreachableDemo() {
    }

    private static void checkTarget(int target) {
        if (target < 0 || target == Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "target must be nonnegative and fit target + 1"
            );
        }
    }

    // Mỗi mệnh giá/bước phải dương và không trùng.
    private static int[] positiveDistinct(int[] values) {
        Objects.requireNonNull(values, "values");
        int[] copy = Arrays.copyOf(values, values.length);
        Arrays.sort(copy);

        for (int i = 0; i < copy.length; i++) {
            if (copy[i] <= 0) {
                throw new IllegalArgumentException(
                    "step size must be positive"
                );
            }
            if (i > 0 && copy[i] == copy[i - 1]) {
                throw new IllegalArgumentException(
                    "duplicate step size"
                );
            }
        }
        return copy;
    }

    // Tối thiểu số đồng xu tạo CHÍNH XÁC target.
    // Trả empty khi không đạt.
    public static OptionalLong minCoins(int target, int[] coins) {
        checkTarget(target);
        int[] steps = positiveDistinct(coins);

        long[] dp = new long[target + 1];
        Arrays.fill(dp, INF);
        dp[0] = 0L;

        for (int sum = 1; sum <= target; sum++) {
            for (int coin : steps) {
                if (coin > sum) {
                    break;
                }
                if (dp[sum - coin] == INF) {
                    continue; // Không chuyển từ trạng thái không đạt.
                }
                long candidate = dp[sum - coin] + 1L;
                if (candidate < dp[sum]) {
                    dp[sum] = candidate;
                }
            }
        }
        return dp[target] == INF
            ? OptionalLong.empty()
            : OptionalLong.of(dp[target]);
    }

    // Đếm chuỗi bước CÓ THỨ TỰ, dùng mỗi bước tùy ý số lần.
    // BigInteger biểu diễn số cách chính xác, không modulo.
    public static BigInteger countOrderedWays(
            int target, int[] stepsInput) {
        checkTarget(target);
        int[] steps = positiveDistinct(stepsInput);

        BigInteger[] ways = new BigInteger[target + 1];
        Arrays.fill(ways, BigInteger.ZERO);
        ways[0] = BigInteger.ONE; // Một chuỗi rỗng.

        for (int sum = 1; sum <= target; sum++) {
            for (int step : steps) {
                if (step > sum) {
                    break;
                }
                ways[sum] = ways[sum].add(ways[sum - step]);
            }
        }
        return ways[target];
    }

    public record Move(int cost, int reward) {
        public Move {
            if (cost <= 0) {
                throw new IllegalArgumentException(
                    "move cost must be positive"
                );
            }
        }
    }

    // Tối đa tổng điểm khi đạt CHÍNH XÁC target.
    // Điểm có thể âm; dùng reachable riêng, không dùng -INF.
    public static OptionalLong maxRewardExact(
            int target, Move[] moves) {
        checkTarget(target);
        Objects.requireNonNull(moves, "moves");
        for (Move move : moves) {
            Objects.requireNonNull(move, "move");
        }

        long[] best = new long[target + 1];
        boolean[] reachable = new boolean[target + 1];
        reachable[0] = true;
        best[0] = 0L;

        for (int sum = 1; sum <= target; sum++) {
            for (Move move : moves) {
                int cost = move.cost();
                if (cost > sum || !reachable[sum - cost]) {
                    continue;
                }

                long candidate =
                    best[sum - cost] + (long) move.reward();

                if (!reachable[sum] || candidate > best[sum]) {
                    reachable[sum] = true;
                    best[sum] = candidate;
                }
            }
        }

        return reachable[target]
            ? OptionalLong.of(best[target])
            : OptionalLong.empty();
    }

    private static String show(OptionalLong result) {
        return result.isPresent()
            ? Long.toString(result.getAsLong())
            : "unreachable";
    }

    public static void main(String[] args) {
        System.out.println("Min {1,5,7}, target 11: "
            + show(minCoins(11, new int[] {1, 5, 7})));
        System.out.println("Min {4,6}, target 7: "
            + show(minCoins(7, new int[] {4, 6})));
        System.out.println("Min {4,6}, target 8: "
            + show(minCoins(8, new int[] {4, 6})));
        System.out.println("Min {}, target 0: "
            + show(minCoins(0, new int[0])));

        System.out.println("Ways {1,2}, target 4: "
            + countOrderedWays(4, new int[] {1, 2}));
        System.out.println("Ways {2,4}, target 3: "
            + countOrderedWays(3, new int[] {2, 4}));
        System.out.println("Ways {}, target 0: "
            + countOrderedWays(0, new int[0]));

        Move[] moves = {
            new Move(2, -5),
            new Move(3, -2)
        };
        System.out.println("Max reward exact 5: "
            + show(maxRewardExact(5, moves)));
        System.out.println("Max reward exact 1: "
            + show(maxRewardExact(1, moves)));
        System.out.println("Max reward exact 6: "
            + show(maxRewardExact(6, moves)));
        System.out.println("Max reward exact 0: "
            + show(maxRewardExact(0, moves)));

        boolean rejected = false;
        try {
            minCoins(5, new int[] {0, 2});
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("Zero step rejected: " + rejected);
    }
}
```

Biên dịch và chạy bằng **JDK 17 hoặc mới hơn**:

```bash
javac DpUnreachableDemo.java
java DpUnreachableDemo
```

**Đầu ra chuẩn:**

```text
Min {1,5,7}, target 11: 3
Min {4,6}, target 7: unreachable
Min {4,6}, target 8: 2
Min {}, target 0: 0
Ways {1,2}, target 4: 5
Ways {2,4}, target 3: 0
Ways {}, target 0: 1
Max reward exact 5: -7
Max reward exact 1: unreachable
Max reward exact 6: -4
Max reward exact 0: 0
Zero step rejected: true
```

### Giải thích đầu ra và tính an toàn

- `minCoins({1,5,7},11)=3`: có thể dùng `5+5+1`, và không có phương án chỉ một hoặc hai đồng xu đạt đúng `11`.
- `minCoins({4,6},7)` không đạt vì không có tổ hợp số nguyên không âm của `4` và `6` bằng `7`; hàm trả `OptionalLong.empty()`, được hiển thị thành `unreachable`.
- `minCoins({4,6},8)=2` qua `4+4`. Khi `target=0`, không dùng đồng nào là phương án hợp lệ nên trả `0` ngay cả khi tập mệnh giá rỗng.
- `countOrderedWays({1,2},4)=5`; `countOrderedWays({2,4},3)=0`. Tập bước rỗng vẫn có đúng **một** chuỗi rỗng đạt tổng `0`.
- Bài max trả **`-7`** cho `target=5` dù điểm âm; đây là một **đáp án hợp lệ**. `target=1` mới là không thể đạt. `target=6` trả `-4` khi chọn hai thao tác chi phí `3`; `target=0` trả `0`.
- Mệnh giá `0` bị từ chối vì điều kiện bước dương bảo đảm mỗi lần chuyển đi từ tổng nhỏ tới tổng lớn. Với bài đếm có bước `0` được lặp không giới hạn, số chuỗi thao tác có thể vô hạn; không thể tái sử dụng trực tiếp công thức đếm hữu hạn.
- Hai API tối ưu trả `OptionalLong` thay vì “một số đặc biệt” từ bên ngoài; điều đó ngăn người gọi vô tình nhầm giá trị `0`, `-1` hoặc điểm âm hợp lệ với trạng thái không đạt.

**Về tràn số:** Trong `minCoins`, sentinel `INF=Long.MAX_VALUE/4` được dùng chỉ trong phạm vi không âm, và mã **kiểm tra `dp[sum-coin]!=INF` trước khi cộng**. Với mệnh giá nguyên dương và `target` hợp lệ đủ để cấp mảng, số đồng xu tối thiểu không vượt `target`, nhỏ hơn rất nhiều so với `INF`. Trong `maxRewardExact`, điểm mỗi bước là `int` và số bước không thể vượt `target` vì mọi chi phí ít nhất là `1`; tổng điểm thực tế nằm trong giới hạn `long` đối với miền `target` kiểu `int`. Trong `countOrderedWays`, `BigInteger` không tràn số đếm; bộ nhớ và thời gian vẫn có giới hạn thực tế.

## 7. Bất biến và chứng minh tính đúng

Một bài DP đúng không chỉ nhờ công thức có vẻ hợp lý; ta cần bảo đảm **khởi tạo đúng, chỉ chuyển từ trạng thái hợp lệ và xử lý các phụ thuộc theo thứ tự phù hợp**.

### 7.1. Min số đồng xu

**Bất biến:** sau khi tính xong `dp[s]`, với mọi tổng `t<=s`, `dp[t]` bằng số đồng xu tối thiểu tạo đúng `t` nếu tồn tại cách tạo; nếu không tồn tại thì `dp[t]=INF`.

Cơ sở `t=0` đúng: dùng `0` đồng để tạo tổng `0`. Giả sử tất cả tổng nhỏ hơn `s` đã được tính đúng. Bất kỳ cách tạo tổng `s` nào đều có một đồng cuối cùng mệnh giá `c`; phần trước đó phải tạo đúng `s-c`. Vì `c>0`, đây là trạng thái nhỏ hơn đã tính. Lấy min của `dp[s-c]+1` trên **những trạng thái `s-c` có thể đạt** tìm đúng số đồng tối thiểu. Nếu không có tiền nhiệm khả thi nào, không thể tạo `s` và giữ `INF`. Theo quy nạp, bảng min đúng.

### 7.2. Đếm chuỗi bước có thứ tự

**Bất biến:** sau khi tính `ways[s]`, giá trị này đúng bằng số chuỗi thao tác tạo tổng `s`.

Tổng `0` có đúng một chuỗi rỗng. Với `s>0`, mọi chuỗi kết thúc bằng **một bước cuối `c`** thuộc tập bước phân biệt, và tiền tố của nó tạo đúng `s-c`. Các tập chuỗi được chia theo **bước cuối** là rời nhau; tổng số chuỗi bằng tổng `ways[s-c]`. Nếu không có chuỗi nào, tổng rỗng bằng `0`. Vì `c>0`, các tiền tố đã được tính trước. Điều này chứng minh công thức đếm có thứ tự.

### 7.3. Max điểm với cờ khả thi

**Bất biến:** sau khi tính `s`, `reachable[s]` đúng khi có ít nhất một chuỗi thao tác đạt tổng `s`. Nếu đúng, `best[s]` là điểm lớn nhất trong tất cả các chuỗi ấy.

Tổng `0` đạt được qua chuỗi rỗng với điểm `0`. Mọi chuỗi đạt `s>0` phải có thao tác cuối với chi phí `c>0`, phần trước đó đạt `s-c`. Chỉ những `s-c` có `reachable=true` mới tạo ứng viên hợp lệ. Mỗi ứng viên có điểm `best[s-c]+reward`. Lấy max qua toàn bộ ứng viên cho điểm tốt nhất; nếu không có ứng viên, cờ khả thi giữ `false`. Vì bước luôn giảm tổng khi đi ngược lại, giả thiết quy nạp đủ để kết luận.

**Kết luận quan trọng:** một trạng thái `best[s]` có thể chứa `0` do giá trị mặc định của Java nhưng **không mang nghĩa** nếu `reachable[s]==false`. Cách dùng **hai mảng song song** là một hình thức tách *sự tồn tại của lời giải* khỏi *giá trị của lời giải*.

## 8. Memoization: “chưa tính” khác “không đạt”

Với DP **bottom-up**, ta biết thứ tự tính và có thể dùng giá trị ban đầu để biểu diễn không đạt. Với DP **top-down có ghi nhớ**, phải trả lời thêm: một trạng thái đã được gọi và tính xong hay chưa?

Giả sử muốn tính một điểm tối ưu có thể âm. Nếu dùng:

```java
// Mã minh họa rút gọn: CÁCH SAI khi giá trị hợp lệ có thể bằng -1.
if (memo[state] != -1) {
    return memo[state];
}
```

thì khi giá trị tối ưu thật bằng `-1`, chương trình sẽ tưởng chưa tính và tính lại. Nếu `-1` còn được dùng cho “không đạt”, có thể nhầm lẫn **ba** trường hợp: chưa tính, không đạt và đạt với giá trị `-1`.

Một cách thiết kế chặt chẽ là tách:

```text
computed[state]  = đã tính trạng thái này chưa?
reachable[state] = trạng thái này có lời giải không?
value[state]     = kết quả tối ưu, CHỈ hợp lệ nếu reachable=true
```

Khi gọi một trạng thái:

1. Nếu `computed[state]` đã đúng, trả kết quả đã lưu (bao gồm cả kết quả “không đạt”).
2. Nếu chưa tính, xét trạng thái cơ sở và các phép chuyển hợp lệ.
3. Lưu `reachable` và `value` tương ứng rồi đặt `computed=true`.
4. Ở các lượt gọi sau, không tính lại dù kết quả trước đó là không thể đạt.

Với mô hình DP theo **đồ thị có chu trình**, chỉ thêm một mảng `computed` sau khi tính xong chưa đủ để giải mọi trường hợp: còn phải kiểm soát **trạng thái đang xét** hoặc dùng thuật toán phù hợp với chu trình. Các ví dụ trong bài có bước chi phí dương và xử lý theo tổng tăng, nên đồ thị phụ thuộc là **không chu trình**.

### Khi nào `-1` là sentinel an toàn?

Nếu chứng minh được **mọi đáp án hợp lệ đều không âm**, ví dụ số bước tối thiểu của một bài toán, `-1` có thể được dùng để báo “không thể đạt” **ở giao diện bên ngoài**. Tuy nhiên, nếu cùng một mảng top-down còn dùng `-1` cho “chưa tính”, ta lại gặp hai ý nghĩa khác nhau. Tốt nhất chọn hai dấu hiệu phân biệt hoặc tách biến trạng thái.

Với **đường đi điểm âm**, `-1` có thể là một đáp án hợp lệ. Không được chọn `-1` làm dấu hiệu không đạt nếu không có cờ bổ sung.

## 9. Biên giới, lưới, đường đi và các bài toán khác

Nguyên tắc khởi tạo còn xuất hiện trong nhiều dạng DP.

### 9.1. Đường đi tối đa trên lưới có vật cản

Giả sử chỉ được đi **sang phải hoặc xuống dưới** từ ô `(0,0)`. Mỗi ô có thể có điểm âm; một số ô bị chặn. Đặt `dp[r][c]` là điểm tối đa để đến ô `(r,c)`, chỉ xét đường đi hợp lệ.

- Nếu ô xuất phát bị chặn, **mọi trạng thái đều không thể đạt**.
- Nếu ô xuất phát hợp lệ, khởi tạo `dp[0][0]=score[0][0]`, không phải tự động bằng `0` nếu ô xuất phát có điểm.
- Mỗi ô khác chỉ nhận ứng viên từ ô phía trên hoặc bên trái **nếu tiền nhiệm thật sự có thể đạt** và ô hiện tại không bị chặn.
- Nếu cả hai tiền nhiệm đều không đạt, ô hiện tại giữ trạng thái không đạt.
- Vì điểm có thể âm, dùng `reachable[r][c]` hoặc `-INF` an toàn; **không** lấy max với `0` của một đường đi “tự xuất hiện”.

Lưới có một đường đi dài nhận điểm `-10` vẫn là một đường đi hợp lệ. Nếu đích bị chặn hoặc cô lập, kết quả phải là **không đạt**, không phải tự động `0`.

### 9.2. DP 0/1 Knapsack “chính xác trọng lượng”

Khi `dp[w]` là giá trị cao nhất với **tổng trọng lượng bằng đúng `w`**, khởi tạo `dp[0]=0` và các trọng lượng dương là **không đạt**. Với mỗi món hàng dùng tối đa một lần, vòng cập nhật theo trọng lượng thường phải duyệt **giảm dần** để không dùng lại chính món hàng vừa cập nhật.

Nếu bài toán đổi thành **tổng trọng lượng không vượt `W`**, người giải có thể định nghĩa một bảng khác mà phương án rỗng hợp lệ cho mọi ngân sách và giá trị `0` có ý nghĩa. Vì vậy, **chiều duyệt, khởi tạo và trạng thái đều phải theo hợp đồng**, không dựa vào chữ “knapsack” đơn thuần.

### 9.3. Đường đi ngắn nhất trên DAG

Với đồ thị có hướng không chu trình (DAG), có thể đặt `dist[source]=0`, mọi đỉnh khác `INF`, rồi duyệt các đỉnh theo **thứ tự topo**. Chỉ thử nới lỏng cạnh đi ra từ đỉnh có khoảng cách hữu hạn. Nếu một đỉnh không thể đến từ nguồn, `dist[v]` vẫn là `INF`.

Nếu cạnh có trọng số âm, phép cộng sentinel không an toàn càng dễ gây lỗi; phải **kiểm tra đỉnh nguồn của cạnh có thể đạt trước khi cộng**. Đây là DP trên thứ tự topo. Không tự suy ra rằng thuật toán Dijkstra sẽ phù hợp với trọng số âm: đó là bài toán và điều kiện thuật toán khác.

### 9.4. DP đếm với modulo

Khi tính `ways[s]` modulo `M`:

```text
ways[s] = (tổng số cách) mod M
```

thì `ways[s]=0` chỉ nói rằng số cách chia hết cho `M` hoặc thật sự bằng `0`. Ví dụ có `M` cách khác nhau thì kết quả modulo là `0` nhưng trạng thái **có thể đạt**. Nếu bạn cần dùng thông tin “có ít nhất một cách” để điều khiển chuyển trạng thái khác, hãy lưu **`reachable` riêng** thay vì suy từ giá trị modulo.

## 10. Chọn sentinel an toàn và tránh tràn số

Dùng sentinel số học cần có **cơ sở giới hạn đầu vào**.

### Sentinel cho bài min

Với bài số đồng xu, chọn `INF=Long.MAX_VALUE/4` vì giá trị hợp lệ là số đồng xu không âm, và trong mô hình mệnh giá dương, một nghiệm tối ưu không thể dùng quá `target` đồng khi `target` là số nguyên không âm khả thi. Điều này tạo khoảng cách lớn giữa giá trị thật và sentinel trong phạm vi ví dụ.

Trong một bài min chi phí tổng quát, nếu chi phí có thể cực lớn hoặc âm, cần **chứng minh** một cận trên/cận dưới thật. Nếu không chứng minh được sentinel không trùng đáp án hợp lệ, dùng cờ `reachable` hoặc kiểu `OptionalLong`/đối tượng kết quả sẽ rõ nghĩa hơn.

### Sentinel cho bài max

`Long.MIN_VALUE` thường được dùng để biểu diễn `-INF`, nhưng không được cộng trực tiếp vào nó:

```java
// Sai nếu prev == Long.MIN_VALUE và reward âm:
long candidate = prev + reward;

// Đúng về mặt tồn tại trạng thái: kiểm tra trước.
if (prevIsReachable) {
    long candidate = prev + reward;
    // Sau đó mới so sánh/cập nhật.
}
```

Kiểm tra khả thi **chưa tự bảo đảm không tràn** khi tổng các giá trị hợp lệ vượt kiểu số. Với điểm/cost lớn hơn phạm vi mô hình ví dụ, cần dùng `Math.addExact` để phát hiện tràn hoặc kiểu số đủ rộng; nếu cần số nguyên không giới hạn, cân nhắc `BigInteger`.

### Đừng biến dấu báo lỗi thành giá trị thật

Giá trị trả về `-1` hay `INF` có thể tiện, nhưng phải có quy ước không va chạm. Các API trong mã dùng `OptionalLong` để người gọi phải xử lý hai khả năng: **có một giá trị `long` hợp lệ** hoặc **không có lời giải**. Trong Java:

```java
// Ví dụ dùng API trong chương trình ở trên.
OptionalLong answer = DpUnreachableDemo.minCoins(
    7, new int[] {4, 6}
);
if (answer.isPresent()) {
    System.out.println(answer.getAsLong());
} else {
    System.out.println("unreachable");
}
```

Đoạn trên là **mã sử dụng thư viện/lớp `DpUnreachableDemo` đã khai báo**, không phải một chương trình độc lập. Nếu gọi `getAsLong()` trên `OptionalLong.empty()` mà không kiểm tra, Java sẽ ném `NoSuchElementException`.

## 11. Độ phức tạp và ý nghĩa của khởi tạo

Gọi `T` là `target` và `m` là số bước/mệnh giá/thao tác hợp lệ:

| Bài toán | Thời gian | Bộ nhớ phụ | Biểu diễn không đạt |
|---|---|---|---|
| Min số đồng xu không giới hạn | `O(m log m + Tm)` với bản kiểm tra/sắp mệnh giá | `O(T+m)` | `INF`, chỉ cộng từ tiền nhiệm hữu hạn |
| Đếm chuỗi có thứ tự | `O(m log m + Tm)` phép cộng số | `O(T+m)` đối tượng `BigInteger`, chưa kể độ dài bit | `BigInteger.ZERO`, cơ sở `ONE` |
| Max điểm với chi phí chính xác | `O(Tm)` | `O(T+m)` gồm hai mảng và đầu vào | `reachable=false` |
| Memoization tổng quát | Phụ thuộc số trạng thái/nhánh chuyển thực sự được thăm | Phụ thuộc bảng nhớ và ngăn xếp | Tách “computed” và “reachable” |

Với `BigInteger`, mỗi phép cộng không có chi phí cố định khi số cách có nhiều chữ số, nên bảng trên đếm **số phép cộng**, không phải thời gian bit-level chính xác. Khi `T=0`, các vòng theo tổng từ `1` tới `T` không chạy, nhưng kết quả cơ sở vẫn phải đúng.

Việc **khởi tạo bảng** cũng tốn chi phí: `Arrays.fill(dp,INF)` cần `O(T)` thời gian, và cấp phát mảng dài `T+1` cần `O(T)` bộ nhớ. Không bỏ qua chi phí này khi đánh giá mô hình với miền trạng thái lớn.

Nếu tập trạng thái cực lớn nhưng chỉ có ít trạng thái đạt được, có thể cân nhắc **sparse DP** bằng Map hoặc memoization để chỉ lưu những trạng thái cần thiết. Khi đó phải phân biệt khóa không tồn tại trong Map là **chưa được lưu** với kết quả đã tính là **không thể đạt**.

## 12. Lỗi thường gặp và cách kiểm tra

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| Khởi tạo mọi `dp[s]=0` trong bài min tổng chính xác | Trạng thái không đạt bị xem là chi phí `0` | Dùng `INF`, đặt riêng `dp[0]=0` |
| Dùng `0` làm mức mặc định của max DP có điểm âm | “Lời giải giả `0`” thắng điểm âm hợp lệ | Dùng `-INF` an toàn hoặc `reachable[]` |
| Đặt `ways[0]=0` | Không có nguồn để sinh các chuỗi hợp lệ | Đặt `ways[0]=1` cho chuỗi rỗng |
| Đặt `ways[s]=null` rồi gọi `add` | `NullPointerException` trong Java | `Arrays.fill(ways,BigInteger.ZERO)` |
| Chuyển từ `INF` mà không kiểm tra | Tạo ứng viên từ trạng thái không tồn tại, có thể tràn | Kiểm tra tiền nhiệm khả thi trước khi cộng |
| Dùng một dấu `-1` cho vừa “chưa tính” vừa “không đạt” | Memoization không phân biệt hai tình trạng | Dùng `computed[]` và `reachable[]` riêng |
| Coi số cách modulo bằng `0` là không đạt | Có thể có số cách dương chia hết cho modulo | Lưu khả thi riêng nếu cần |
| Dùng `int` cho số cách hoặc số điểm tích lũy lớn | Tràn số dù công thức chuyển đúng | `BigInteger` cho số cách chính xác; `long` cho điểm trong miền an toàn |
| Cho phép bước `0` trong bài đếm chuỗi không giới hạn | Có thể tạo vô số chuỗi cùng tổng, phá mô hình phụ thuộc | Kiểm tra bước dương hoặc đổi mô hình |
| Quên kiểm tra `target<0` hoặc `target+1` tràn | Cấp mảng sai hoặc ngoại lệ ngoài ý định | Kiểm tra miền trước cấp phát |
| Duyệt sai chiều với bài mỗi vật chỉ dùng một lần | Tái sử dụng vật đã chọn trong cùng lượt | Chọn chiều duyệt theo 0/1 hay unbounded |
| Dùng khởi tạo của “không vượt quá” cho “chính xác” | Tính một phương án thiếu ngân sách thành đạt đúng mục tiêu | Viết rõ ý nghĩa trạng thái trước khi khởi tạo |
| Coi mọi trạng thái đã lưu đều có đường đi | Có thể trả giá trị rác/giá trị mặc định | Giữ thông tin `reachable` hoặc sentinel có chứng minh |
| Lấy `max` của một tập ứng viên rỗng thành `0` | Tưởng có phương án điểm `0` | Kết quả là không đạt, không phải số `0` |
| Không kiểm thử mục tiêu `0` | Bỏ sót cơ sở quan trọng nhất | Thử cả tập thao tác rỗng, `target=0` và `target>0` |

### Checklist khi thiết kế một bảng DP mới

Trước khi viết vòng lặp, nên trả lời:

1. **Trạng thái `dp[state]` có nghĩa chính xác là gì?** Giá trị cho tổng chính xác, ngân sách tối đa, số bước, số đường đi, hay khả thi?
2. **Trạng thái xuất phát nào hợp lệ?** Có một hay nhiều gốc? Giá trị cơ sở là `0`, `1` hay giá trị từ ô/đỉnh xuất phát?
3. **Những trạng thái nào ban đầu không thể đạt?** Biểu diễn bằng `INF`, `-INF`, `false`, `0` cách, hay đối tượng kết quả?
4. **Chuyển trạng thái có tiền điều kiện gì?** Có phải kiểm tra trạng thái trước đã đạt, chỉ số trong miền, không dùng vật hai lần và chi phí dương?
5. **Thứ tự tính có bảo đảm mọi tiền nhiệm đã biết?** Duyệt tăng/giảm, thứ tự topo, đệ quy có nhớ hay xử lý chu trình riêng?
6. **Dấu hiệu “chưa tính” có va chạm với đáp án hợp lệ không?** Đặc biệt khi đáp án có thể bằng `0` hoặc âm.
7. **Kiểu số và sentinel có đủ an toàn?** Có giới hạn đầu vào để chứng minh không tràn và không va chạm không?
8. **Trạng thái đích có thể không đạt không?** API trả gì, và người gọi phải xử lý ra sao?

## 13. Bài tập tự luyện

**Bài 1 — Giá trị khởi tạo.** Với số đồng xu tối thiểu tạo đúng tổng `s` bằng mệnh giá `{3,5}`, hãy ghi giá trị khởi tạo đúng của `dp[0]` và `dp[s]` cho `s>0`. Tổng `1` và `8` có kết quả gì?

*Đáp án:* `dp[0]=0`, mọi `s>0` ban đầu là `INF`. Tổng `1` không thể đạt; tổng `8` có kết quả `2` qua `3+5`.

**Bài 2 — Max điểm âm.** Có thao tác `(cost=2,reward=-5)` và `(cost=3,reward=-2)` dùng không giới hạn. Kết quả tối đa khi tổng chi phí phải đúng `5` và `6` là bao nhiêu? Vì sao không phải `0`?

*Đáp án:* đúng `5` có điểm `-7`; đúng `6` có điểm tốt nhất `-4`. `0` chỉ là điểm của chuỗi rỗng ở tổng `0`, không phải một lời giải cho các tổng `5` hoặc `6`.

**Bài 3 — Đếm cách.** Từ tổng `0` chỉ được cộng `1` hoặc `2`, cần đếm chuỗi bước có thứ tự để đạt `3`. Đặt `ways[0]` là bao nhiêu và tìm `ways[3]`.

*Đáp án:* `ways[0]=1`. Có ba chuỗi `1+1+1`, `1+2`, `2+1` nên `ways[3]=3`.

**Bài 4 — Trạng thái chưa tính.** Một hàm memoization trả điểm tối ưu có thể là `-1`. Tại sao không nên dùng `memo[state]==-1` để biểu thị “chưa tính” trong khi cũng lưu chính kết quả `-1` vào ô đó?

*Đáp án:* mỗi lần tra cứu sẽ hiểu nhầm giá trị hợp lệ `-1` thành chưa tính, khiến tính lại và có thể vi phạm giả định memoization. Dùng cờ `computed` riêng.

**Bài 5 — Số cách modulo.** Có đúng `10` cách đạt một trạng thái, nhưng DP lưu số cách modulo `5`. Giá trị bảng là bao nhiêu? Có thể kết luận trạng thái không đạt không?

*Đáp án:* giá trị modulo là `0`; **không**, vì thực tế có `10` cách. Nếu cần biết khả thi, lưu thông tin riêng.

**Bài 6 — Bước không dương.** Bài đếm chuỗi bước có thứ tự cho phép dùng bước `0` vô hạn lần. Vì sao công thức `ways[s]=Σways[s-c]` không còn là công thức bottom-up hữu hạn đơn giản?

*Gợi ý:* khi `c=0`, công thức phụ thuộc lại chính `ways[s]`; có thể chèn tùy ý số bước `0` vào mỗi chuỗi mà không đổi tổng, sinh vô số chuỗi.

**Bài 7 — Lưới có vật cản.** Trên lưới đi phải/xuống, cả ô ngay bên phải và ngay bên dưới điểm xuất phát đều bị chặn. Đích không phải ô xuất phát. Có nên đặt điểm tối đa tại đích bằng `0` không?

*Đáp án:* không. Đích **không thể đạt**, cần báo không có đường đi. `0` chỉ có ý nghĩa nếu tồn tại một đường đi hợp lệ với tổng điểm `0`.

**Bài 8 — Tự kiểm thử.** Hãy sinh các tập mệnh giá dương nhỏ và so `minCoins` với BFS trên tổng `0..T`; so `countOrderedWays` với cách đệ quy liệt kê chuỗi khi `T` nhỏ; với bài max, hãy liệt kê mọi chuỗi có tổng chi phí chính xác `T` và đối chiếu điểm tốt nhất. Kiểm tra cả trường hợp **không có chuỗi**, **chuỗi rỗng**, và **điểm âm**.

## Ghi nhớ

**DP không chỉ là công thức chuyển; khởi tạo và biểu diễn trạng thái không thể đạt là một phần của chứng minh tính đúng.** Với **min**, khởi tạo chưa đạt bằng `INF` và chỉ cộng từ tiền nhiệm hữu hạn. Với **max**, dùng `-INF` có kiểm soát hoặc tách `reachable[]` để không nhầm đáp án âm với giá trị mặc định `0`. Với **count**, trạng thái không đạt có `0` cách nhưng trạng thái cơ sở thường có **`1` cách là chuỗi rỗng**.

Đặc biệt, **“chưa tính”, “không thể đạt” và “đạt được với kết quả bằng 0/âm” là ba tình trạng khác nhau**. Khi xác định rõ chúng, kiểm tra hợp lệ trước mỗi chuyển, chọn đúng thứ tự duyệt và kiểm soát tràn số, bảng DP mới phản ánh đúng lời giải của bài toán.
