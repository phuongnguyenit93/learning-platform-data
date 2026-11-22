# Tổng tập con và phép nén trạng thái bằng bitset

## 1. Bài toán tổng tập con (Subset Sum)

Cho mảng số nguyên `a[0..n-1]` và mục tiêu `T`. Ta hỏi **có tồn tại một tập con các chỉ số** sao cho tổng các giá trị được chọn đúng bằng `T` hay không?

Trong phiên bản được giải ở bài này:

- `a[i]` và `T` là **số nguyên không âm**.
- Mỗi phần tử ở chỉ số `i` chỉ được chọn **tối đa một lần** (mô hình **0/1**).
- Hai phần tử cùng giá trị nhưng ở hai vị trí khác nhau là **hai phần tử riêng biệt**.
- Tập con rỗng được phép, có tổng bằng `0`.
- Đầu ra chính là **true/false**, không phải số cách hay tổng lớn nhất không vượt mục tiêu. Một phiên bản phụ sẽ dựng **một tập con** nếu có.

Ví dụ:

```text
a = [3, 34, 4, 12, 5, 2]
T = 9

Chọn a[2]=4 và a[4]=5 => 4+5=9.
Hoặc chọn a[0]=3, a[2]=4, a[5]=2.

Kết quả: true.
```

Với cùng mảng và mục tiêu `30`, phần tử `34` không thể được chọn vì đã lớn hơn mục tiêu; tổng tất cả các phần tử còn lại bằng `26`, nên đáp án là **false**.

Phải phân biệt bài **0/1 Subset Sum** với bài **Coin Change / Unbounded Sum** dùng mỗi phần tử tùy ý nhiều lần. Độ dài mảng và số lần xuất hiện của từng giá trị đều có ý nghĩa. Ví dụ `[4]` không tạo được `8`, nhưng `[4,4]` tạo được `8` vì có hai phần tử riêng.

### Một vài biến thể thường gặp

| Bài toán | Mục tiêu | Thông tin cần lưu |
|---|---|---|
| Subset Sum 0/1 | Có đạt **đúng `T`** không? | Boolean / một bit cho mỗi tổng |
| Counting Subset Sum | Có bao nhiêu tập con theo chỉ số đạt `T`? | Số cách (có thể rất lớn) |
| Knapsack 0/1 | Tối đa giá trị dưới giới hạn trọng lượng | Giá trị tối ưu, không chỉ true/false |
| Partition Equal Subset Sum | Có chia làm hai nhóm bằng tổng? | Subset Sum với nửa tổng toàn dãy |
| Unbounded Sum | Có đạt `T` khi dùng mỗi mệnh giá nhiều lần? | Công thức và chiều duyệt khác |

## 2. Quy hoạch động boolean trước khi nén

Định nghĩa `dp[s]`:

> Sau khi đã xét một số phần tử đầu tiên, có thể tạo **chính xác tổng `s`** bằng một tập con của các phần tử đã xét hay không?

Với `0<=s<=T`, trạng thái cơ sở là:

```text
dp[0] = true
dp[s] = false với mọi s > 0
```

`dp[0]=true` vì **tập con rỗng** là một lựa chọn hợp lệ. Các tổng dương chưa thể đạt khi chưa xét phần tử.

Khi thêm phần tử có giá trị `x`, mọi lời giải đạt `s` thuộc một trong hai loại:

1. **Không chọn `x`:** tổng `s` đã đạt trước đó.
2. **Chọn `x`:** tổng `s-x` đã đạt trước đó và `s>=x`.

Do đó:

\[
dp_{\mathrm{new}}[s]
=dp_{\mathrm{old}}[s]\lor
\bigl(s\ge x\land dp_{\mathrm{old}}[s-x]\bigr).
\]

Điểm then chốt: cả hai phía của phép OR đều phải đọc **trạng thái trước khi dùng phần tử hiện tại**. Nếu dùng lại một trạng thái vừa được tạo bởi chính `x`, ta vô tình cho phép chọn `x` nhiều lần.

### Vì sao vòng lặp phải đi từ tổng lớn xuống tổng nhỏ?

Một mảng boolean một chiều có thể được cập nhật tại chỗ:

```java
// Mã minh họa khi x > 0.
for (int sum = target; sum >= x; sum--) {
    dp[sum] |= dp[sum - x];
}
```

Vì `sum-x<sum` và đang duyệt **giảm dần**, trạng thái `dp[sum-x]` còn là trạng thái **cũ** trong lượt xử lý phần tử `x`. Nhờ đó mỗi phần tử chỉ được sử dụng một lần.

Cách duyệt tăng dần có thể sai:

```text
a = [3], T = 6

Ban đầu chỉ dp[0]=true.

Nếu duyệt tăng:
  sum=3: dp[3] |= dp[0] => true
  sum=6: dp[6] |= dp[3] => true (dp[3] vừa được tạo)

Thuật toán sai vì coi một số 3 thành hai số 3.

Nếu duyệt giảm:
  sum=6: dp[3] còn false, dp[6] vẫn false
  sum=3: dp[0] true, dp[3] thành true

Đáp án đúng cho a=[3], T=6 là false.
```

Trong bài **0/1**, đi **giảm**; trong nhiều bài **unbounded** (dùng vô hạn), đi **tăng** để có thể tái sử dụng chính phần tử. Chiều duyệt phải xuất phát từ **ý nghĩa trạng thái**, không phải thói quen.

### Theo dõi các tổng có thể đạt

Với `a=[3,5,2]`, `T=8`:

| Đã xử lý | Các tổng có thể đạt trong `0..8` |
|---|---|
| Chưa có phần tử | `{0}` |
| Thêm `3` | `{0,3}` |
| Thêm `5` | `{0,3,5,8}` |
| Thêm `2` | `{0,2,3,5,7,8}` |

Ở lượt cuối, tổng `10=3+5+2` cũng có thể đạt về mặt toán học, nhưng không cần lưu nếu chỉ hỏi mục tiêu `T=8`.

## 3. Bitset biểu diễn một tập các tổng bằng các bit

Thay vì lưu `T+1` giá trị boolean, ta dùng một **dãy bit** `B`:

\[
bit(B,s)=1 \iff \text{có thể đạt chính xác tổng }s.
\]

- Bit `0` đại diện tổng `0`.
- Bit `1` đại diện tổng `1`.
- ...
- Bit `T` đại diện tổng `T`.

Ban đầu chỉ bit `0` bật:

```text
B = ...00000001
```

Khi thêm phần tử không âm `x`, mọi tổng cũ `s` tạo thêm tổng `s+x` nếu chọn `x`. **Dịch trái bitset `x` vị trí** chính là biến tập các tổng `R` thành `R+x`. OR với bitset cũ tương ứng lựa chọn không chọn phần tử.

Công thức:

\[
B_{\mathrm{new}}=B_{\mathrm{old}}\;|\;(B_{\mathrm{old}}\ll x).
\]

Nếu chỉ xét các tổng `0..T` thì sau mỗi bước **cắt bỏ các bit ngoài khoảng này**:

\[
B_{\mathrm{new}}
=(B_{\mathrm{old}}\;|\;(B_{\mathrm{old}}\ll x))
\;\&\;(2^{T+1}-1).
\]

Đây là phép **nén trạng thái DP**, không phải nén giá trị của đầu vào. Mỗi bit vẫn là một trạng thái logic độc lập, nhưng nhiều trạng thái được cập nhật trong một phép toán trên **từ máy**.

### Ví dụ dịch trái

Giả sử trước đó đạt `R={0,3,5}` và đang xử lý một phần tử `x=2`:

```text
R_old        = {0,3,5}
R_old + 2    = {2,5,7}
R_new        = {0,2,3,5,7}
```

Những bit `0,2,3,5,7` sau phép OR đều được bật. Bit `5` có thể được tạo theo nhiều cách, nhưng bitset chỉ lưu **có tồn tại**, không lưu số cách.

### Tại sao cắt các tổng lớn hơn mục tiêu là an toàn?

Khi mọi phần tử còn lại đều **không âm**, một tổng tạm `s>T` không thể giảm xuống đúng `T` bằng cách cộng thêm những phần tử khác. Vậy ta không cần giữ bit `s>T`.

Đây là giả định quan trọng. Ví dụ `a=[10,-7]` và `T=3` có lời giải `10+(-7)=3`; nếu cắt tổng `10` ngay sau bước đầu thì mất lời giải. **Cài đặt trong bài chỉ chấp nhận số không âm**, không âm thầm xử lý số âm bằng cách cắt bit sai.

## 4. Phần tử 0 và phần tử trùng nhau

Các trường hợp biên thường làm lộ lỗi logic:

- `a=[]`, `T=0`: **true** (tập con rỗng).
- `a=[]`, `T=1`: **false**.
- `a=[4]`, `T=8`: **false** (không được dùng lại phần tử duy nhất).
- `a=[4,4]`, `T=8`: **true** (hai chỉ số riêng).
- `a=[0,0,5]`, `T=0`: **true**.
- `a=[0,0,5]`, `T=5`: **true**.

Với `x=0`, phép dịch không làm thay đổi tập các tổng có thể đạt:

\[
B\;|\;(B\ll 0)=B.
\]

Vì thế, **có thể bỏ qua số `0` trong bài chỉ hỏi true/false**. Nhưng trong bài **đếm số tập con theo chỉ số**, hai phần tử `0` làm số cách đạt tổng `5` tăng lên `4`: chọn `5` và tùy ý chọn/bỏ mỗi số `0`. Không được bỏ số `0` nếu mục tiêu là **đếm số cách**.

Tương tự, không được loại các phần tử trùng giá trị ra khỏi mảng: mỗi **lần xuất hiện** có thể được chọn độc lập. Việc gom hai phần tử `4` thành một sẽ làm sai trường hợp `[4,4]`, `T=8`.

## 5. Dùng `long[]` để đóng gói 64 trạng thái trong một từ

Công thức `B | (B << x)` dễ đọc nhưng **Java 17 không hỗ trợ dịch trái trực tiếp cho `java.util.BitSet` bằng toán tử `<<`**. Một giá trị `long` đơn chỉ chứa 64 bit, không đủ khi `T>=64`.

Có hai hướng triển khai:

- Dùng `BigInteger`, với `shiftLeft` và `or`, rồi cắt bớt bit ngoài mục tiêu.
- Dùng mảng `long[]`. Mỗi từ chứa **64 bit**, thuận tiện để hiểu chính xác phép dịch theo từ và tránh cấp phát số lớn ở mỗi lượt.

Bài này minh họa cách thứ hai. Với một tổng `s`:

```text
wordIndex = s / 64
bitIndex  = s % 64

Bit cần kiểm tra:
  (words[wordIndex] & (1L << bitIndex)) != 0
```

Các mốc quan trọng:

| Tổng | Chỉ số từ máy | Vị trí bit trong từ |
|---:|---:|---:|
| 0 | 0 | 0 |
| 63 | 0 | 63 |
| 64 | 1 | 0 |
| 65 | 1 | 1 |
| 127 | 1 | 63 |
| 128 | 2 | 0 |

### 5.1. Dịch trái qua ranh giới 64 bit

Với một phần tử `x>0`:

```text
wordShift = x / 64
bitShift  = x % 64
src = dest - wordShift
```

Từ đích `dest` nhận phần chính:

```java
long shifted = words[src] << bitShift;
```

Nếu `bitShift>0` và `src>0`, còn phải lấy **những bit cao từ từ trước**:

```java
shifted |= words[src - 1] >>> (64 - bitShift);
```

Phải dùng `>>>` (dịch phải **không dấu**) thay vì `>>`, vì một từ `long` có thể có bit `63` bằng `1` và khi nhìn như số có dấu sẽ âm. Nhưng ta đang thao tác trên **bit**, không phải trên giá trị số học có dấu.

**Cảnh báo Java:** số bước dịch của `long` được xét theo 6 bit thấp. Vì vậy `x >>> 64` tương đương `x >>> 0`, không phải phép dịch phải 64 vị trí theo toán học lý tưởng. Chỉ lấy phần carry khi **`bitShift != 0`** để tránh lỗi này.

### 5.2. Phải cập nhật từ từ cao xuống từ thấp

Khi dịch bitset **tại chỗ**, nguồn của bit mới phải đến từ bitset trước khi xử lý `x`. Vì `x>0`, mỗi tổng nguồn nhỏ hơn tổng đích. Quét `dest` **từ chỉ số cao xuống thấp** đảm bảo các từ nguồn chưa bị cập nhật.

Nếu `wordShift=0` thì nguồn và đích có thể là **cùng một từ**. Cài đặt vẫn đọc giá trị cũ của từ đó **trước phép OR tại chính từ đích**, nên phần tử hiện tại không bị sử dụng lặp trong một lượt.

Nếu quét thấp lên cao, một bit mới bật ở từ thấp có thể được dùng làm nguồn cho từ cao ngay trong cùng lượt, biến bài toán 0/1 thành bài cho phép dùng một phần tử nhiều lần.

### 5.3. Cắt phần thừa của từ cuối

Cần `T+1` bit, số từ là:

\[
W=\left\lceil\frac{T+1}{64}\right\rceil.
\]

Khi `T` không kết thúc đúng bit `63` của một từ, phải xóa những bit lớn hơn `T` trong từ cuối:

```java
int keepBits = (target & 63) + 1;  // 1..64
if (keepBits < 64) {
    words[words.length - 1] &= (1L << keepBits) - 1L;
}
```

Với `keepBits=64`, toàn bộ từ là hợp lệ: **không cần mask**. Nếu viết `1L << 64`, Java lại coi là dịch `0`, làm mask sai.

Một từ có bit `63` bật có thể hiện ra như số âm khi in, nhưng phép `& (1L << offset)` vẫn xác định bit chính xác. **Không dùng so sánh `words[word]>0` để xét một bit.**

## 6. Java 17+: ba cách làm, một hợp đồng

Chương trình hoàn chỉnh dưới đây có:

1. `canMakeSumBoolean(a,T)` — DP boolean duyệt giảm.
2. `canMakeSumPacked(a,T)` — bitset `long[]` nén 64 tổng mỗi từ.
3. `findSubsetIndices(a,T)` — lưu thông tin tiền nhiệm để dựng **một tập chỉ số gốc** có tổng đúng `T`.

Hàm truy vết trả `Optional<List<Integer>>`: nếu không có lời giải, trả `Optional.empty()`; nếu mục tiêu `0`, trả **một danh sách rỗng hợp lệ** trong `Optional.of`. Hai trường hợp này có ý nghĩa khác nhau.

Cả ba hàm từ chối mảng `null`, số âm và mục tiêu âm. Để tránh `target+1` bị tràn trong các phương pháp cấp mảng trực tiếp, phiên bản này cũng từ chối `target=Integer.MAX_VALUE`. Dữ liệu lớn hơn RAM vẫn có thể gây hết bộ nhớ, dù các tham số hợp lệ.

Lưu tệp đúng tên **`SubsetSumBitsetDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public final class SubsetSumBitsetDemo {
    private SubsetSumBitsetDemo() {
    }

    private static void validate(int[] values, int target) {
        Objects.requireNonNull(values, "values");
        if (target < 0 || target == Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "target must be in 0..Integer.MAX_VALUE-1"
            );
        }
        for (int value : values) {
            if (value < 0) {
                throw new IllegalArgumentException(
                    "negative values are unsupported"
                );
            }
        }
    }

    // O(n*T) time, O(T) memory.
    public static boolean canMakeSumBoolean(int[] values, int target) {
        validate(values, target);
        boolean[] dp = new boolean[target + 1];
        dp[0] = true;

        for (int x : values) {
            if (x == 0 || x > target) {
                continue;
            }
            for (int sum = target; sum >= x; sum--) {
                dp[sum] |= dp[sum - x];
            }
        }
        return dp[target];
    }

    // Nén 64 trạng thái vào mỗi long.
    // Quét word giảm để phần tử hiện tại không bị dùng hai lần.
    public static boolean canMakeSumPacked(int[] values, int target) {
        validate(values, target);
        int wordCount = (target >>> 6) + 1;
        long[] words = new long[wordCount];
        words[0] = 1L; // Tổng 0 luôn có thể đạt.

        for (int x : values) {
            if (x == 0 || x > target) {
                continue;
            }

            int wordShift = x >>> 6;
            int bitShift = x & 63;

            for (int dest = wordCount - 1; dest >= 0; dest--) {
                int src = dest - wordShift;
                if (src < 0) {
                    continue;
                }

                long shifted = words[src] << bitShift;
                if (bitShift != 0 && src > 0) {
                    shifted |= words[src - 1]
                        >>> (64 - bitShift);
                }
                words[dest] |= shifted;
            }

            int keepBits = (target & 63) + 1;
            if (keepBits < 64) {
                words[wordCount - 1] &= (1L << keepBits) - 1L;
            }
        }

        int word = target >>> 6;
        int offset = target & 63;
        return (words[word] & (1L << offset)) != 0L;
    }

    // Trả một tập CHỈ SỐ GỐC (0-based), không lặp chỉ số.
    // Optional.empty(): không đạt. Optional.of([]): tổng 0 hợp lệ.
    public static Optional<List<Integer>> findSubsetIndices(
            int[] values, int target) {
        validate(values, target);
        boolean[] reachable = new boolean[target + 1];
        int[] previousSum = new int[target + 1];
        int[] pickedIndex = new int[target + 1];
        Arrays.fill(pickedIndex, -1);
        reachable[0] = true;

        for (int index = 0; index < values.length; index++) {
            int x = values[index];
            if (x == 0 || x > target) {
                continue;
            }

            for (int sum = target; sum >= x; sum--) {
                if (!reachable[sum] && reachable[sum - x]) {
                    reachable[sum] = true;
                    previousSum[sum] = sum - x;
                    pickedIndex[sum] = index;
                }
            }
        }

        if (!reachable[target]) {
            return Optional.empty();
        }

        List<Integer> result = new ArrayList<>();
        for (int sum = target; sum > 0; sum = previousSum[sum]) {
            result.add(pickedIndex[sum]);
        }
        Collections.reverse(result);
        return Optional.of(result);
    }

    public static void main(String[] args) {
        int[] sample = {3, 34, 4, 12, 5, 2};

        System.out.println("Sample target 9 (boolean): "
            + canMakeSumBoolean(sample, 9));
        System.out.println("Sample target 9 (packed): "
            + canMakeSumPacked(sample, 9));
        System.out.println("Sample target 30 (packed): "
            + canMakeSumPacked(sample, 30));

        List<Integer> indices =
            findSubsetIndices(sample, 9).orElseThrow();
        List<Integer> chosen = new ArrayList<>();
        for (int index : indices) {
            chosen.add(sample[index]);
        }
        System.out.println("Witness indices target 9: " + indices);
        System.out.println("Witness values target 9: " + chosen);

        System.out.println("Single 4 target 8: "
            + canMakeSumPacked(new int[] {4}, 8));
        System.out.println("Two 4s target 8: "
            + canMakeSumPacked(new int[] {4, 4}, 8));
        System.out.println("Zeros target 0: "
            + canMakeSumPacked(new int[] {0, 0, 5}, 0));
        System.out.println("Zeros target 5: "
            + canMakeSumPacked(new int[] {0, 0, 5}, 5));
        System.out.println("Empty target 0: "
            + canMakeSumPacked(new int[0], 0));
        System.out.println("Empty target 1: "
            + canMakeSumPacked(new int[0], 1));

        System.out.println("Cross 64 bits: "
            + canMakeSumPacked(new int[] {63, 1}, 64));
        System.out.println("Cross word carry: "
            + canMakeSumPacked(new int[] {63, 2}, 65));
        System.out.println("Near signed bit: "
            + canMakeSumPacked(new int[] {63}, 63));
        System.out.println("Two whole words: "
            + canMakeSumPacked(new int[] {64, 64}, 128));
        System.out.println("Oversized value ignored: "
            + canMakeSumPacked(new int[] {1, 1_000_000}, 1));

        boolean rejected = false;
        try {
            canMakeSumPacked(new int[] {-1, 2}, 1);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("Negative rejected: " + rejected);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 SubsetSumBitsetDemo.java
java SubsetSumBitsetDemo
```

Kết quả chuẩn:

```text
Sample target 9 (boolean): true
Sample target 9 (packed): true
Sample target 30 (packed): false
Witness indices target 9: [2, 4]
Witness values target 9: [4, 5]
Single 4 target 8: false
Two 4s target 8: true
Zeros target 0: true
Zeros target 5: true
Empty target 0: true
Empty target 1: false
Cross 64 bits: true
Cross word carry: true
Near signed bit: true
Two whole words: true
Oversized value ignored: true
Negative rejected: true
```

### Ý nghĩa của kết quả

- `[3,34,4,12,5,2]` đạt tổng `9` bằng hai phần tử tại chỉ số `2` và `4`, giá trị `4` và `5`. Mục tiêu `30` không đạt.
- Một `4` không được dùng hai lần; hai bản sao `4` ở hai chỉ số thì được chọn cả hai.
- Những giá trị `0` không thay đổi **tính khả thi**. Tập con rỗng tạo tổng `0` kể cả với đầu vào rỗng.
- Những ca `63`, `64`, `65`, `128` kiểm tra đúng chỗ giao nhau giữa hai từ 64 bit và cách xử lý bit dấu.
- Hàm `findSubsetIndices` trả một nghiệm, không hứa nghiệm duy nhất hay ít phần tử nhất. Nó lưu thông tin cha tách biệt khỏi bitset đóng gói.

### Vì sao truy vết cần lưu cha?

Khi một tổng `sum` lần đầu đạt được từ tổng cũ `sum-x`, hàm lưu chỉ số phần tử `index` và tổng trước đó. Vòng duyệt giảm bảo đảm `sum-x` chưa bị tạo bằng chính `index` ở cùng lượt. Về sau, liên kết cha của `sum` không bị ghi đè nên việc truy ngược sẽ không lặp cùng phần tử.

Ví dụ:

```text
sum=9: pickedIndex=4 (giá trị 5), previousSum=4
sum=4: pickedIndex=2 (giá trị 4), previousSum=0
sum=0: dừng

Chỉ số sau khi đảo ngược: [2,4].
Tổng các giá trị: 4+5=9.
```

Bitset cuối cùng chỉ nói **bit `9` bật**, không nói **tập con nào** bật bit này. Nếu cần lời giải cụ thể, phải lưu cha hoặc thông tin theo từng giai đoạn.

## 7. Chứng minh tính đúng

Gọi `R_i` là tập các tổng có thể tạo bằng một tập con của **`i` phần tử đầu**. Khi chưa xét phần tử nào:

\[
R_0=\{0\}.
\]

Giả sử xét thêm phần tử `x=a[i-1]`. Mọi tập con thuộc một trong hai loại:

- Không chọn `x`: tổng đã thuộc `R_{i-1}`.
- Chọn `x` đúng một lần: bỏ `x` ra còn tập con của `i-1` phần tử đầu với tổng `s` trong `R_{i-1}`; tổng mới là `s+x`.

Ngược lại, mỗi tổng thuộc một trong hai tập này đều do một tập con hợp lệ tạo ra. Vậy:

\[
R_i=R_{i-1}\cup\{s+x:s\in R_{i-1}\}.
\]

Theo quy nạp, quan hệ trên đúng sau mọi bước. DP boolean biểu diễn phép hợp bằng **OR** trên từng `dp[s]`; bitset biểu diễn phép hợp bằng **OR sau dịch trái `x`**. Vì hai thao tác mô tả cùng quan hệ tập hợp, chúng cho cùng đáp án.

### Vì sao cập nhật tại chỗ đúng?

Trong DP boolean, xét các tổng từ **cao xuống thấp**. Với `x>0`, chỉ số nguồn `s-x` nhỏ hơn chỉ số đích `s`, nên nguồn chưa bị thay trong lượt hiện tại. Trong packed bitset, quét **từ máy cao xuống thấp** vì mọi bit nguồn cũng nằm ở vị trí thấp hơn bit đích; nếu nguồn và đích trong cùng một từ, ta đọc giá trị cũ trước khi OR. Vì vậy không một bit mới nào được dùng làm tiền nhiệm cho chính phần tử vừa xử lý.

Nếu `x=0`, tập tổng khả thi không thay đổi, nên có thể bỏ qua phần tử ấy. Nếu `x>T`, vì các số khác không âm nên không có tập con nào chứa `x` mà đạt đúng `T`; bỏ qua cũng an toàn.

Cắt các tổng `>T` là đúng trong phiên bản không âm, vì thêm số không âm không làm tổng giảm. Cuối cùng, bit `T` bật **khi và chỉ khi** có tập con đạt đúng mục tiêu.

## 8. Độ phức tạp: nhanh hơn nhờ xử lý theo từ máy

Đặt `n` là số phần tử, `T` là mục tiêu, và `W=ceil((T+1)/64)` là số từ `long` cần lưu.

| Cách làm | Thời gian | Bộ nhớ phụ |
|---|---|---|
| Thử toàn bộ tập con bằng duyệt bitmask | `O(n 2^n)` nếu cộng lại từng tập; có thể tối ưu việc sinh còn `O(2^n)` | Phụ thuộc cách sinh |
| DP boolean một chiều | `O(nT)` | `O(T)` phần tử boolean |
| Packed bitset `long[]` | `O(nW)` thao tác từ máy | `O(W)` từ `long` |
| DP có mảng cha để dựng tập con | `O(nT)` | `O(T)` |
| Meet-in-the-middle | Khoảng `O(n 2^{n/2})` tùy cài đặt | Khoảng `O(2^{n/2})` |

Bản packed trong chương trình quét toàn bộ `W` từ khi xét mỗi phần tử dương `x<=T`, nên `O(nW)` là giới hạn rõ ràng trên **mô hình tính toán với từ 64 bit**. Một phép dịch/OR trên `long` xử lý cùng lúc nhiều trạng thái boolean, do đó thường tiết kiệm thời gian và bộ nhớ hơn vòng duyệt qua từng tổng.

Tuy nhiên, đây vẫn là một thuật toán **giả đa thức (pseudo-polynomial)**: thời gian phụ thuộc vào **giá trị số học `T`**, chứ không chỉ số bit `log₂T` dùng để ghi mục tiêu trong input. Nếu `T` rất lớn thì dù chia cho 64, bảng trạng thái vẫn có thể vượt RAM.

Đối với `T=1.000.000.000`, cần khoảng `15,6` triệu từ `long`, tương ứng hơn `125` MB chỉ tính phần dữ liệu thô của bitset. Không nên gọi cách làm này là “nhẹ” khi mục tiêu cực lớn.

### Chọn thuật toán thế nào?

- **`T` nhỏ hoặc vừa, `n` lớn:** DP boolean đơn giản; bitset thường nhanh hơn nếu cập nhật nhiều lần.
- **`n` nhỏ (ví dụ vài chục), `T` cực lớn:** cân nhắc **meet-in-the-middle**, chia dãy làm hai nửa, liệt kê tổng từng nửa rồi tìm hai tổng cộng lại bằng `T`.
- **Số tổng thực sự đạt được ít:** có thể thử `HashSet<Long>` quản lý các tổng đã đạt, nhưng số lượng trạng thái có thể vẫn tăng theo hàm mũ.
- **Nhiều truy vấn trên cùng một mảng:** xây bitset đến mục tiêu lớn nhất cần hỏi rồi đọc từng bit, thay vì chạy lại DP cho mỗi truy vấn.
- **Cần một tập chỉ số hoặc số cách:** bitset chỉ có bit 0/1 là chưa đủ; phải bổ sung thông tin hoặc đổi DP.

Không suy luận `O(nT/64)` là đa thức theo độ dài biểu diễn của input: kích thước `T` vẫn có thể tăng theo hàm mũ so với số bit của nó.

## 9. Những bẫy quan trọng khi mở rộng

### 9.1. Số âm

Cắt tổng lớn hơn mục tiêu chỉ đúng khi mọi giá trị không âm. Với `[10,-7]` và `T=3`, phải giữ tổng `10` để về `3` sau khi thêm `-7`. Muốn hỗ trợ số âm cần mô hình khác: chẳng hạn lưu miền tổng từ `minPossible` đến `maxPossible` với **offset**, dịch cả hai chiều và quản lý phạm vi. Miền có thể rất lớn; không được chỉ thay `x` bằng `abs(x)`.

### 9.2. Bài đếm số tập con

Với `[0,0,5]`, mục tiêu `5`, có **4** tập con theo chỉ số vì hai số `0` được chọn hoặc bỏ độc lập. Bitset chỉ lưu **true**. Nếu cần số cách, dùng DP đếm số cách (kiểu số phù hợp, có thể `BigInteger`), không lấy số lượng bit bật làm số cách.

### 9.3. Chia thành hai nhóm bằng tổng

Với các số không âm, tổng tất cả `S`. Nếu `S` lẻ thì không chia thành hai nhóm bằng nhau; nếu `S` chẵn, chỉ cần giải Subset Sum cho `T=S/2`. Ví dụ `[1,5,11,5]` có tổng `22`; chọn `11` làm một nhóm và `1+5+5` làm nhóm còn lại.

### 9.4. Tìm tổng lớn nhất không vượt giới hạn

Nếu bài hỏi **tối đa tổng không vượt `T`**, không bắt buộc bit `T` phải bật. Ta phải tìm **bit cao nhất đang bật ở vị trí `s<=T`**. Đây là mục tiêu khác với **đạt đúng `T`**, dù cùng có thể dùng bitset.

### 9.5. Biến thể có trọng số hoặc lợi nhuận

Mỗi bit chỉ cho biết tổng `s` có thể đạt. Nó **không lưu giá trị thưởng lớn nhất**, số lượng phần tử ít nhất hoặc số cách tạo tổng. Nếu cần những đại lượng này, hãy định nghĩa lại DP cho mục tiêu mới. Không thể thay một mảng `maxScore[s]` bằng bitset boolean mà vẫn giữ kết quả tối ưu điểm.

### 9.6. `BitSet` và `BigInteger` trong Java

`java.util.BitSet` có `get`, `set`, `or` nhưng không có toán tử `<<` dành cho toàn bộ bitset trong Java 17. `BigInteger.ONE` là bitset chỉ có bit `0`; có thể biểu diễn công thức với `bits.or(bits.shiftLeft(x))`, nhưng phải cắt những bit vượt mục tiêu và cân nhắc chi phí đối tượng. Dùng `long[]` giúp thấy rõ phần carry giữa các từ và việc quét giảm để giữ đúng 0/1.

## 10. Lỗi phổ biến

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Quên `dp[0]=true` | Không thể tạo các tổng dương | Khởi tạo tập con rỗng |
| Duyệt `sum` tăng dần trong 0/1 | Dùng một phần tử nhiều lần | Duyệt tổng **giảm** |
| Quét `long[]` từ thấp lên cao khi cập nhật tại chỗ | Bit mới trở thành nguồn trong cùng lượt | Quét từ **cao xuống thấp** |
| Dùng một `long` khi `T>=64` | Mất các tổng ngoài bit 63 | Dùng nhiều từ `long[]` |
| Quên phần `words[src-1] >>> (...)` | Sai khi dịch xuyên ranh giới từ | Ghép phần carry |
| Dịch `>>>64` khi `bitShift=0` | Java dịch tương đương `>>>0` | Kiểm tra `bitShift!=0` |
| Dùng `>>` thay cho `>>>` | Lan bit dấu không mong muốn | Dùng dịch phải không dấu |
| Kiểm tra `words[word] > 0` | Sai khi bit cao nhất bật, `long` âm | Dùng `&` với mask |
| Quên cắt bit `>T` | Lưu trạng thái thừa và dễ lỗi giới hạn | Mask từ cuối |
| Xóa phần tử trùng nhau | Sai vì các chỉ số khác nhau có thể cùng được chọn | Giữ mọi lần xuất hiện |
| Bỏ số 0 trong bài **đếm cách** | Sai số cách | Chỉ bỏ khi hỏi **tồn tại** |
| Hỗ trợ số âm mà vẫn cắt theo `T` | Có thể mất tổng tạm cần thiết | Đổi biểu diễn hoặc từ chối |
| Trả bitset cuối khi đề cần tập con | Không biết chỉ số nào đã chọn | Lưu cha hoặc các lớp trạng thái |
| Quên `target+1` có thể tràn `int` | Lỗi cấp phát mảng | Kiểm tra miền đầu vào |
| Cho rằng `O(nT/64)` là đa thức theo số bit của `T` | Đánh giá sai độ phức tạp | Nhớ tính giả đa thức |

## 11. Kiểm thử đối chứng

Với các mảng ngắn (ví dụ `n<=20`), có thể kiểm tra độc lập bằng vét cạn tất cả `2^n` tập chỉ số:

```text
for mỗi mask từ 0 đến 2^n-1:
    sum = 0
    for i từ 0 đến n-1:
        nếu bit i của mask bật:
            sum += a[i]
    nếu sum == T:
        kết luận có lời giải
```

Nên kiểm tra **cả ba phương pháp** của chương trình:

1. Boolean DP và packed bitset phải trả cùng `true/false`.
2. Kết quả phải khớp với vét cạn.
3. Nếu truy vết trả tập chỉ số, các chỉ số phải hợp lệ, không trùng nhau và tổng giá trị phải đúng `T`.
4. Với `T=0`, witness có thể là danh sách rỗng hợp lệ.
5. Với `T>0` không đạt, witness phải trả `Optional.empty()`.

Bắt buộc thử **`T=0`**, mảng rỗng, toàn số `0`, một phần tử không được dùng lại, nhiều giá trị bằng nhau, giá trị lớn hơn mục tiêu, số âm bị từ chối, và các mốc `63`, `64`, `65`, `127`, `128`. Các biên 64 bit làm lộ lỗi dịch, bit dấu và phần carry mà ví dụ mục tiêu nhỏ không bắt được.

Kiểm thử ngẫu nhiên với nhiều bản sao giúp phát hiện lỗi triển khai; nhưng **bất biến tập tổng `R_i` và chứng minh đọc trạng thái cũ khi cập nhật giảm** mới giải thích tính đúng cho mọi đầu vào hợp lệ.

## 12. Bài tập tự luyện

**Bài 1 — Theo dõi tổng.** Với `a=[3,5,2]` và `T=8`, liệt kê tập tổng có thể đạt sau mỗi lượt.

*Đáp án:* `{0}` → `{0,3}` → `{0,3,5,8}` → `{0,2,3,5,7,8}` sau khi cắt ở `8`.

**Bài 2 — Lỗi dùng lại phần tử.** Vì sao `a=[4]`, `T=8` phải trả `false`, còn `a=[4,4]`, `T=8` trả `true`?

*Đáp án:* bài 0/1 cho phép mỗi **chỉ số** được dùng một lần. Mảng đầu chỉ có một chỉ số; mảng sau có hai chỉ số giá trị `4`.

**Bài 3 — Dịch bit.** Nếu `R={0,2,5}` và thêm phần tử `3`, tập tổng mới là gì?

*Đáp án:* `R+3={3,5,8}`, nên `R_{\mathrm{new}}={0,2,3,5,8}` trước khi cắt mục tiêu.

**Bài 4 — Số 0 và số cách.** `a=[0,0,5]`, `T=5`, kết quả bài quyết định là gì? Có bao nhiêu tập con theo chỉ số đạt `5`?

*Đáp án:* `true`; có **4** tập con khác nhau vì hai số `0` có thể được chọn hoặc bỏ độc lập.

**Bài 5 — Biên 64 bit.** Tổng `65` được lưu ở từ `long` nào, bit nào (0-based)? Với `a=[63,2]`, nó có thể đạt không?

*Đáp án:* từ số `1`, bit số `1`; có, vì `63+2=65`.

**Bài 6 — Số âm.** Với `a=[10,-7]`, `T=3`, tại sao không được bỏ tổng `10` sau lượt đầu?

*Đáp án:* chọn thêm `-7` sẽ đưa tổng `10` về `3`. Đây là giới hạn của mô hình chỉ lưu tổng `0..T` cho các số không âm.

**Bài 7 — Chia hai nhóm.** Chứng minh `[1,5,11,5]` chia được hai nhóm bằng tổng; tìm một tập chỉ số tạo ra `11`.

*Đáp án:* tổng bằng `22`, chọn chỉ số `2` (giá trị `11`), nhóm còn lại gồm `1,5,5` cũng bằng `11`.

**Bài 8 — Lựa chọn thuật toán.** Nếu `n` nhỏ nhưng `T` khoảng `10^12`, tại sao packed bitset vẫn có thể không phù hợp?

*Gợi ý:* số từ máy vẫn tỷ lệ với `T/64`, chi phí RAM quá lớn; cân nhắc meet-in-the-middle với hai nửa tập chỉ số.

**Bài 9 — Truy vết.** Với `a=[3,34,4,12,5,2]`, kiểm tra tập chỉ số `[2,4]` có hợp lệ cho `T=9` không. Giải thích sự khác biệt giữa `Optional.empty()` và `Optional.of(emptyList())`.

*Đáp án:* `a[2]+a[4]=4+5=9`. Optional rỗng báo **không có lời giải**; một danh sách rỗng bên trong Optional báo **tập con rỗng hợp lệ** khi mục tiêu `0`.

## Ghi nhớ

**0/1 Subset Sum** hỏi có thể chọn một tập con theo chỉ số, **mỗi phần tử tối đa một lần**, có tổng đúng mục tiêu hay không. DP boolean khởi tạo `dp[0]=true` và duyệt các tổng **giảm dần** khi xét một phần tử mới.

**Bitset** mã hóa `dp[s]` bằng bit `s`. Với phần tử không âm `x`, cập nhật `B_new = B_old | (B_old << x)`, rồi cắt các bit `>T`. Trong Java 17, `long[]` chứa 64 trạng thái mỗi từ; khi cập nhật tại chỗ phải **quét từ cao xuống thấp**, ghép carry bằng `>>>` và xử lý đúng biên `63/64`. Thời gian theo từ máy khoảng `O(n ceil((T+1)/64))`, bộ nhớ `O(ceil((T+1)/64))` từ `long`.

Trước khi áp dụng, hãy xác nhận **0/1 hay dùng vô hạn**, **dữ liệu không âm**, **có cần đếm số cách hoặc truy vết không**, và **mục tiêu có đủ nhỏ để cấp bitset không**. Nén trạng thái là một tối ưu biểu diễn mạnh, nhưng vẫn phải giữ đúng bất biến của DP.
