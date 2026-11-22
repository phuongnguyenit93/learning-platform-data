# Kiểm tra giả thiết tối ưu hóa bằng phản ví dụ và lời giải gốc

## 1. Tối ưu quy hoạch động: nhanh hơn chỉ khi vẫn đúng

Khi giải một bài **quy hoạch động (Dynamic Programming, DP)**, ta thường có một công thức gốc đúng nhưng chậm, chẳng hạn:

\[
dp[i]=\min_{0\le j<i}\{dp[j]+w(j,i)\}.
\]

Nếu phải xét mọi `j<i` cho mỗi `i`, tổng số phép thử chuyển trạng thái là khoảng `n(n-1)/2`, tức **`O(n²)`**. Để tăng tốc, ta có thể muốn:

- Chỉ tìm trong một dải chỉ số hẹp hơn.
- Tin rằng chỉ số `j` tốt nhất tăng dần theo `i`.
- Dùng deque đơn điệu, cây đoạn hoặc Convex Hull Trick để tìm min nhanh hơn.
- Chia để trị trên vị trí quyết định tối ưu.
- Chỉ giữ một hàng DP thay vì toàn bộ bảng.
- Bỏ các ứng viên tưởng như không còn cần thiết.

Nhưng **mỗi tối ưu đều thay đổi cách tính hoặc lượng thông tin được giữ**. Nếu điều kiện áp dụng chưa được chứng minh, cách “nhanh hơn” có thể bỏ qua lời giải đúng và trả một kết quả trông rất hợp lý nhưng sai.

Bài học này trình bày một quy trình kiểm tra chặt chẽ:

1. Viết **lời giải gốc (baseline/reference solution)** với trạng thái và chuyển trạng thái đúng theo đề.
2. Phát biểu giả thiết tối ưu hóa thành một tính chất **có thể kiểm chứng và có thể bác bỏ**.
3. Tìm **phản ví dụ nhỏ**, gồm đầu vào và hai kết quả mâu thuẫn.
4. Đối chiếu với lời giải gốc, kiểm tra cả trạng thái trung gian, chỉ số quyết định và điều kiện biên.
5. Chỉ triển khai tối ưu khi có **chứng minh điều kiện áp dụng**, rồi kiểm thử đối chứng trên nhiều lớp dữ liệu.

**Nguyên tắc:** một triệu ca kiểm thử đúng không thay thế chứng minh tổng quát; nhưng **một phản ví dụ hợp lệ đủ bác bỏ giả thiết**.

## 2. Ví dụ nền tảng: DP trên đồ thị có hướng không chu trình

Xét các trạng thái `0,1,\ldots,n-1`, bắt đầu ở trạng thái `0` với chi phí `0`. Được phép chuyển từ **mọi `j<i`** sang `i`, và cạnh `j→i` có chi phí nguyên `w[j][i]`. Hỏi chi phí đường đi nhỏ nhất từ `0` đến từng `i`.

Đồ thị chỉ có cạnh theo hướng **chỉ số tăng**, nên không có chu trình. Chi phí cạnh có thể âm; vì không có chu trình, cách tính DP theo chỉ số vẫn hợp lệ, miễn là tổng nằm trong kiểu số.

Định nghĩa:

> `dp[i]` = tổng chi phí nhỏ nhất của một đường đi từ `0` tới đúng `i`.

**Cơ sở:**

\[
dp[0]=0.
\]

**Chuyển trạng thái:**

\[
dp[i]=\min_{0\le j<i}\{dp[j]+w[j][i]\},\qquad i\ge1.
\]

Để truy vết, lưu:

\[
parent[i]=\arg\min_{0\le j<i}\{dp[j]+w[j][i]\}.
\]

Khi nhiều `j` có cùng chi phí tốt nhất, ví dụ này chọn **chỉ số `j` nhỏ nhất** để có kết quả xác định. Đây là chính sách hòa, không phải điều kiện cần để chi phí tối ưu đúng.

### Lời giải gốc `O(n²)`

```text
dp[0] = 0
parent[0] = -1

for i = 1..n-1:
    chưa có ứng viên tốt nhất
    for j = 0..i-1:
        candidate = dp[j] + w[j][i]
        nếu chưa có ứng viên hoặc candidate nhỏ hơn best:
            best = candidate
            bestJ = j
    dp[i] = best
    parent[i] = bestJ
```

Tổng số lần xét cạnh:

\[
1+2+\cdots+(n-1)=\frac{n(n-1)}2.
\]

Vì vậy chi phí tính DP là **`O(n²)`**. Nếu lưu toàn bộ ma trận `w` đã cho, đầu vào có kích thước **`O(n²)`**; riêng các mảng `dp` và `parent` cần **`O(n)`** bộ nhớ.

**Vì sao đây là lời giải gốc đáng tin?** Mỗi đường đi tới `i` có một cạnh cuối `j→i` với `j<i`. Nếu chi phí tốt nhất tới `j` đã đúng, chỉ cần cộng cạnh cuối rồi lấy min trên **tất cả** các `j`. Không loại bất cứ ứng viên hợp lệ nào bằng một giả thiết chưa chứng minh.

Đây là chuẩn tham chiếu để kiểm tra một cách tính nhanh hơn. Tuy nhiên, lời giải gốc cũng phải được **chứng minh và kiểm thử**; đừng coi nó là tuyệt đối đúng chỉ vì chạy chậm.

## 3. Một giả thiết nghe hợp lý nhưng sai

Giả sử sau khi giải `dp[i-1]`, ta đã biết `parent[i-1]`. Một người có thể đưa ra giả thiết:

> **Giả thiết H:** Khi `i` tăng, chỉ số tiền nhiệm tối ưu không giảm, tức `parent[i]\ge parent[i-1]`. Do đó lúc tính `dp[i]` chỉ cần xét `j\ge parent[i-1]`.

Nếu H đúng, có thể cố gắng áp dụng một số kỹ thuật tối ưu dựa trên **tính đơn điệu của vị trí tối ưu**. Nhưng **H không đúng cho ma trận chi phí `w[j][i]` tùy ý**.

### Phản ví dụ chỉ có 4 trạng thái

Cho `n=4`. Các chi phí cạnh hợp lệ `j<i` là:

| Cạnh | Chi phí |
|---|---:|
| `0→1` | 0 |
| `0→2` | 10 |
| `1→2` | 0 |
| `0→3` | 0 |
| `1→3` | 10 |
| `2→3` | 10 |

Tất cả các chi phí đều **không âm**. Không có trường hợp âm hoặc tràn số nào cần đến để tạo lỗi.

Tính bằng lời giải gốc:

- `dp[0]=0`.
- `dp[1]=dp[0]+0=0`, nên `parent[1]=0`.
- `dp[2]=min(dp[0]+10,dp[1]+0)=min(10,0)=0`, nên `parent[2]=1`.
- `dp[3]=min(dp[0]+0,dp[1]+10,dp[2]+10)=min(0,10,10)=0`, nên `parent[3]=0`.

Bảng kết quả:

| i | `dp[i]` đúng | `parent[i]` đúng |
|---:|---:|---:|
| 0 | 0 | -1 |
| 1 | 0 | 0 |
| 2 | 0 | 1 |
| 3 | 0 | 0 |

Ta thấy `parent[2]=1` nhưng `parent[3]=0`: **chỉ số tối ưu giảm từ `1` về `0`**. Đây là phản ví dụ trực tiếp cho H.

Nếu dùng cách **giới hạn tìm kiếm chưa chứng minh**, thì lúc tính `i=3` chỉ xét `j\ge parent[2]=1`:

```text
Ứng viên bị bỏ:
  j=0: dp[0] + w[0][3] = 0 + 0 = 0  (TỐI ƯU)

Ứng viên còn được xét:
  j=1: dp[1] + w[1][3] = 0 + 10 = 10
  j=2: dp[2] + w[2][3] = 0 + 10 = 10

Kết quả sai: dp[3] = 10 thay vì 0.
```

Điều nguy hiểm là **đến `i=2` mọi thứ vẫn đúng**. Nếu chỉ kiểm thử các trường hợp nhỏ hơn `4`, hoặc tình cờ sinh dữ liệu mà chỉ số tối ưu không giảm, lỗi sẽ không lộ ra.

### Sai ở đâu trong lý luận?

Việc `j=1` tốt nhất cho `i=2` **không suy ra** `j=0` sẽ kém cho mọi `i` sau này. Chi phí `w[j][i]` thay đổi theo cả `j` và `i`. Một ứng viên từng tệ có thể lại tốt khi đích chuyển sang vị trí khác.

**Chỉ số `i` tăng** không đồng nghĩa với **chỉ số tối ưu `parent[i]` tăng**. Không được chuyển một quy luật quan sát được trên ví dụ sang kết luận phổ quát.

Lưu ý: phiên bản “chỉ xét `j\ge parent[i-1]`” ở đây là **một lối tắt không được chứng minh**, không phải một thuật toán Divide-and-Conquer DP đúng chuẩn. Chỉ vì một vòng lặp xét ít ứng viên hơn trên vài dữ liệu không bảo đảm tổng thời gian tốt hơn `O(n²)`, và càng không bảo đảm tính đúng.

## 4. Phát biểu giả thiết theo dạng có thể bị bác bỏ

Cách kiểm tra tốt bắt đầu bằng **một phát biểu chính xác**. Đừng viết “có lẽ kết quả tăng đều” hoặc “deque chắc chạy được”.

Thay vào đó, viết:

\[
H:\quad \forall i\in\{2,\ldots,n-1\},\quad opt[i-1]\le opt[i].
\]

Trong đó `opt[i]` là **chỉ số `j` được chọn theo một quy tắc hòa cố định** sau khi tối ưu hóa `dp[i]`.

Để H có nghĩa, phải chốt:

1. **Miền đầu vào:** `w` có tùy ý hay bị ràng buộc bởi công thức/đặc tính nào?
2. **Chỉ số và miền xét:** `j<i`, `j\le i`, hay `j` trong một đoạn khác?
3. **Mục tiêu:** lấy `min` hay `max`; có ràng buộc phụ hay không?
4. **Chính sách hòa:** nếu nhiều `j` đạt cùng min, chọn chỉ số nhỏ nhất, lớn nhất hay một quy ước khác?
5. **Tính chất cần chứng minh:** đơn điệu trên **một hàng DP**, trên **các trạng thái cùng lớp**, hay giữa nhiều lớp?
6. **Hậu quả nếu H sai:** ứng viên nào bị loại, đáp án nào sai?

### Một phản ví dụ có giá trị cần gồm những gì?

Phản ví dụ nên có thể tái lập độc lập:

```text
Input:
  n = 4
  w[0][1]=0, w[0][2]=10, w[1][2]=0
  w[0][3]=0, w[1][3]=10, w[2][3]=10

Baseline:
  dp = [0,0,0,0]
  parent = [-1,0,1,0]

Shortcut dùng giả thiết opt không giảm:
  dp = [0,0,0,10]
  parent = [-1,0,1,1]

Sai khác đầu tiên:
  i = 3; ứng viên j=0 bị bỏ, làm mất chi phí 0.
```

Không chỉ đưa một câu “thuật toán sai”. Hãy chỉ rõ **điều kiện giả thiết bị phá**, **lượt đầu tiên tạo ra sai khác**, **đáp án đúng** và **kết quả sai**.

Cũng cần tránh phản ví dụ **không hợp lệ**: nếu đề buộc `w` thỏa tính chất Monge hoặc một bất đẳng thức riêng, không được dùng ma trận tùy ý vi phạm các ràng buộc ấy để bác bỏ một thuật toán chỉ được áp dụng dưới ràng buộc đó. Phản ví dụ phải **nằm trong miền đầu vào của giả thiết đang xét**.

## 5. Lời giải gốc, bộ kiểm thử đối chứng và phép vét cạn

**Lời giải gốc** là cách tính dễ hiểu nhất còn đủ nhanh cho dữ liệu nhỏ. Với DP trên đồ thị tăng chỉ số, vòng hai lớp xét **toàn bộ** `j<i`. Nó không cần biết trước tính đơn điệu, lồi, thứ tự dốc hay cách loại ứng viên.

Một quy trình kiểm thử vững gồm ba tầng:

- **Tầng 1: chứng minh hoặc suy diễn từ định nghĩa.** Vì sao công thức DP gốc đúng? Có tiền nhiệm bị thiếu không? Trạng thái cơ sở có đúng không?
- **Tầng 2: đối chứng độc lập trên kích thước rất nhỏ.** Có thể liệt kê mọi đường đi tăng chỉ số từ `0`, tính chi phí và lấy min. Cách này **khác cấu trúc** với cách điền bảng DP nên giảm nguy cơ cùng mắc một lỗi.
- **Tầng 3: differential testing.** Chạy cả **baseline** và **optimized** trên cùng input; so `dp`, chỉ số quyết định và đáp án, nhất là ở trạng thái đầu tiên bị lệch.

### Vét cạn đường đi làm oracle thứ hai

Với `n` rất nhỏ, ta có thể liệt kê mọi chuỗi chỉ số:

\[
0=i_0<i_1<\cdots<i_t=i
\]

và tính tổng:

\[
w[i_0][i_1]+w[i_1][i_2]+\cdots+w[i_{t-1}][i_t].
\]

Lấy giá trị nhỏ nhất qua tất cả các đường đi tới `i`. Cách này có số trường hợp tăng theo hàm mũ, không dành cho `n` lớn, nhưng hữu ích để kiểm tra **chính baseline**.

Đừng chỉ kiểm tra `dp[n-1]`. Có thể một phiên bản tính sai ở trạng thái giữa nhưng tình cờ đáp án cuối vẫn trùng. So toàn bộ `dp[0..n-1]` sẽ tìm được **điểm lệch đầu tiên**, dễ thu nhỏ phản ví dụ và chẩn đoán lý do.

### Trình tự kiểm thử được khuyến nghị

1. Kiểm tra các ca nhỏ nhất: `n=1`, `n=2`, mọi chi phí bằng `0`, có nhiều ứng viên hòa.
2. Thêm chi phí lớn/nhỏ xen kẽ, chi phí âm nếu hợp đồng cho phép, và đường đi tối ưu nhảy trực tiếp.
3. Chạy vét cạn và baseline trên `n` nhỏ.
4. Chạy baseline và optimized trên `n` trung bình.
5. Sinh ngẫu nhiên **có seed cố định** để có thể tái lập.
6. Khi tìm thấy sai khác, lưu input, đáp án, trạng thái đầu tiên sai và các ứng viên bị bỏ.
7. Thu nhỏ phản ví dụ: xóa bớt trạng thái, đơn giản hóa trọng số, thay số lớn thành số nhỏ mà vẫn giữ sai khác.
8. Sau khi sửa, giữ phản ví dụ cũ làm **regression test** để lỗi không quay lại.

**Kiểm thử đối chứng rất mạnh nhưng không phải chứng minh.** Nếu tất cả ca sinh ngẫu nhiên đều qua, ta chỉ biết “chưa tìm được phản ví dụ trong tập đã thử”. Đặc biệt, tính chất tối ưu hóa như Monge, quadrangle inequality hoặc monotone opt thường là ràng buộc cấu trúc của cả **họ dữ liệu**; không thể suy ra từ vài mẫu thành công.

## 6. Một tối ưu hóa thật sự đúng: khai thác chi phí tách được

Để thấy sự khác biệt giữa “đoán đơn điệu” và “suy ra bằng đại số”, xét một **hợp đồng đầu vào hẹp hơn**:

\[
w[j][i]=fee[j]+base[i]\qquad (j<i).
\]

Trong đó:

- `fee[j]` là phụ phí **chỉ phụ thuộc tiền nhiệm `j`**.
- `base[i]` là chi phí **chỉ phụ thuộc đích `i`**.
- Mọi cạnh `j→i` với `j<i` đều tồn tại.
- Các giá trị cộng có thể âm; cần kiểm soát tràn số theo kiểu dữ liệu.

Khi đó:

\[
\begin{aligned}
dp[i]
&=\min_{0\le j<i}\{dp[j]+fee[j]+base[i]\}\\
&=base[i]+\min_{0\le j<i}\{dp[j]+fee[j]\}.
\end{aligned}
\]

Đặt:

\[
bestPrefix[i]=\min_{0\le j<i}\{dp[j]+fee[j]\}.
\]

Ta có thể duy trì **giá trị min tiền tố** và chỉ số đạt min khi duyệt `i` từ trái sang phải. Sau khi tính `dp[i]`, thêm ứng viên `dp[i]+fee[i]` vào min tiền tố **cho các trạng thái tương lai**.

Mã giả:

```text
dp[0] = 0
bestValue = dp[0] + fee[0]
bestIndex = 0

for i = 1..n-1:
    dp[i] = base[i] + bestValue
    parent[i] = bestIndex

    newKey = dp[i] + fee[i]
    if newKey < bestValue:
        bestValue = newKey
        bestIndex = i
```

Ở đây:

- **Không cần giả định `parent[i]` tăng** để bỏ ứng viên.
- Chỉ cần bất biến `bestValue=min_{j<i}(dp[j]+fee[j])`.
- Khi hòa, dùng dấu `<` để giữ chỉ số **đã có sớm hơn**, khớp cách baseline quét `j` tăng dần.
- Tổng thời gian cho `n` trạng thái là **`O(n)`**, bộ nhớ `O(n)` để lưu `dp,parent`, hoặc giảm thêm nếu chỉ cần giá trị cuối.

**Lưu ý rất quan trọng:** phiên bản tối ưu đúng **chỉ cho chi phí tách được**, không phải cho ma trận `w` tùy ý. Nếu đầu vào chỉ cung cấp `long[][] w` mà không chứng minh được `w[j][i]=fee[j]+base[i]`, không được tự ý áp dụng công thức này.

### Ví dụ có trạng thái tốt nhất thay đổi

Dùng:

```text
base = [0, 5, 2, 7, 1]
fee  = [8, -10, 4, -3, 0]

dp[0] = 0
best ban đầu = dp[0] + fee[0] = 8, index=0

i=1: dp[1] = 5 + 8 = 13
     key(1) = 13 - 10 = 3  -> best=3, index=1

i=2: dp[2] = 2 + 3 = 5
     key(2) = 5 + 4 = 9   -> giữ best=3

i=3: dp[3] = 7 + 3 = 10
     key(3) = 10 - 3 = 7  -> giữ best=3

i=4: dp[4] = 1 + 3 = 4
```

Kết quả `dp=[0,13,5,10,4]` và `parent=[-1,0,1,1,1]`, đúng bằng cách gốc `O(n²)` trên ma trận được tạo bởi `fee[j]+base[i]`.

Lý do tối ưu **không phải do thử nghiệm trùng nhau**. Công thức đại số đã chứng minh rằng mọi ứng viên chỉ khác nhau theo **khóa cố định `dp[j]+fee[j]`**, nên min tiền tố là đủ. Kiểm thử chỉ kiểm tra việc triển khai có tuân theo chứng minh hay không.

## 7. Java 17+ hoàn chỉnh: phản ví dụ, baseline và tối ưu đúng điều kiện

Chương trình dưới đây có bốn phần:

1. `baseline(long[][] w)`: giải đúng DP gốc trên ma trận chi phí đầy đủ.
2. `unprovedShortcut(long[][] w)`: **cố ý sai**; chỉ xét `j>=parent[i-1]`. Hàm này chỉ dùng để **minh họa phản ví dụ**, không được dùng làm lời giải cho dữ liệu thực.
3. `separableWeights(base,fee)`: tạo một ma trận thực sự có dạng `fee[j]+base[i]`.
4. `optimizedSeparable(base,fee)`: giải bằng **min tiền tố `O(n)`** và đối chiếu với baseline.

Mã còn sinh **400 trường hợp có seed cố định** thuộc đúng họ chi phí tách được, đối chiếu cả `dp` và `parent`. Các giá trị sinh nhỏ để tránh tràn số trong phần thử nghiệm.

**Hợp đồng ví dụ:** có ít nhất một trạng thái; mọi cạnh `j<i` tồn tại; `dp[0]=0`; chi phí `long`; nếu phép cộng vượt phạm vi `long`, `Math.addExact` ném ngoại lệ thay vì trả kết quả sai. Bản baseline kiểm tra ma trận vuông, không dùng giá trị tại hoặc dưới đường chéo.

Lưu tệp tên **`DpOptimizationAssumptionDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;
import java.util.Random;

public final class DpOptimizationAssumptionDemo {
    private DpOptimizationAssumptionDemo() {
    }

    public record Result(long[] dp, int[] parent) {
    }

    private static void checkMatrix(long[][] weight) {
        Objects.requireNonNull(weight, "weight");
        if (weight.length == 0) {
            throw new IllegalArgumentException("empty graph");
        }
        int n = weight.length;
        for (long[] row : weight) {
            if (row == null || row.length != n) {
                throw new IllegalArgumentException(
                    "weight matrix must be square"
                );
            }
        }
    }

    private static void checkSeparate(long[] base, long[] fee) {
        Objects.requireNonNull(base, "base");
        Objects.requireNonNull(fee, "fee");
        if (base.length == 0 || base.length != fee.length) {
            throw new IllegalArgumentException(
                "base and fee must have equal positive length"
            );
        }
    }

    // O(n^2): xét mọi tiền nhiệm j < i, không giả thiết opt đơn điệu.
    public static Result baseline(long[][] weight) {
        checkMatrix(weight);
        int n = weight.length;
        long[] dp = new long[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        dp[0] = 0L;

        for (int i = 1; i < n; i++) {
            boolean found = false;
            long best = 0L;
            int bestJ = -1;

            for (int j = 0; j < i; j++) {
                long candidate = Math.addExact(
                    dp[j], weight[j][i]
                );

                if (!found || candidate < best) {
                    found = true;
                    best = candidate;
                    bestJ = j;
                }
            }

            dp[i] = best;
            parent[i] = bestJ;
        }

        return new Result(dp, parent);
    }

    // CỐ Ý SAI với ma trận bất kỳ.
    // Chỉ dùng để chứng minh giả thiết opt không giảm có thể sai.
    public static Result unprovedShortcut(long[][] weight) {
        checkMatrix(weight);
        int n = weight.length;
        long[] dp = new long[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        int lastBestIndex = 0;
        for (int i = 1; i < n; i++) {
            boolean found = false;
            long best = 0L;
            int bestJ = -1;

            // Giả thiết chưa chứng minh: không xét j < lastBestIndex.
            for (int j = lastBestIndex; j < i; j++) {
                long candidate = Math.addExact(
                    dp[j], weight[j][i]
                );

                if (!found || candidate < best) {
                    found = true;
                    best = candidate;
                    bestJ = j;
                }
            }

            dp[i] = best;
            parent[i] = bestJ;
            lastBestIndex = bestJ;
        }

        return new Result(dp, parent);
    }

    // Sinh ma trận đúng loại chi phí tách được:
    // weight[j][i] = fee[j] + base[i], với j < i.
    public static long[][] separableWeights(
            long[] base, long[] fee) {
        checkSeparate(base, fee);
        int n = base.length;
        long[][] weight = new long[n][n];

        for (int j = 0; j < n; j++) {
            for (int i = j + 1; i < n; i++) {
                weight[j][i] = Math.addExact(
                    fee[j], base[i]
                );
            }
        }
        return weight;
    }

    // O(n) cho đúng họ chi phí tách được, không dùng ma trận.
    public static Result optimizedSeparable(
            long[] base, long[] fee) {
        checkSeparate(base, fee);
        int n = base.length;
        long[] dp = new long[n];
        int[] parent = new int[n];
        Arrays.fill(parent, -1);

        dp[0] = 0L;
        long bestKey = Math.addExact(dp[0], fee[0]);
        int bestIndex = 0;

        for (int i = 1; i < n; i++) {
            dp[i] = Math.addExact(base[i], bestKey);
            parent[i] = bestIndex;

            long key = Math.addExact(dp[i], fee[i]);
            if (key < bestKey) {
                bestKey = key;
                bestIndex = i;
            }
        }

        return new Result(dp, parent);
    }

    private static boolean nondecreasingOptimalIndices(
            int[] parent) {
        for (int i = 2; i < parent.length; i++) {
            if (parent[i] < parent[i - 1]) {
                return false;
            }
        }
        return true;
    }

    private static boolean sameResult(Result a, Result b) {
        return Arrays.equals(a.dp(), b.dp())
            && Arrays.equals(a.parent(), b.parent());
    }

    public static void main(String[] args) {
        long[][] counterexample = {
            {0, 0, 10, 0},
            {0, 0, 0, 10},
            {0, 0, 0, 10},
            {0, 0, 0, 0}
        };

        Result original = baseline(counterexample);
        Result shortcut = unprovedShortcut(counterexample);

        System.out.println("Counterexample baseline dp: "
            + Arrays.toString(original.dp()));
        System.out.println("Counterexample baseline parent: "
            + Arrays.toString(original.parent()));
        System.out.println("Counterexample shortcut dp: "
            + Arrays.toString(shortcut.dp()));
        System.out.println("Counterexample shortcut parent: "
            + Arrays.toString(shortcut.parent()));
        System.out.println("Monotone-opt hypothesis holds: "
            + nondecreasingOptimalIndices(original.parent()));

        long[] base = {0, 5, 2, 7, 1};
        long[] fee = {8, -10, 4, -3, 0};

        Result slow = baseline(separableWeights(base, fee));
        Result fast = optimizedSeparable(base, fee);

        System.out.println("Separable baseline dp: "
            + Arrays.toString(slow.dp()));
        System.out.println("Separable optimized dp: "
            + Arrays.toString(fast.dp()));
        System.out.println("Separable optimized parent: "
            + Arrays.toString(fast.parent()));
        System.out.println("Separable same dp and parent: "
            + sameResult(slow, fast));

        Random random = new Random(232L);
        int checked = 0;

        for (int trial = 0; trial < 400; trial++) {
            int n = 1 + random.nextInt(10);
            long[] randomBase = new long[n];
            long[] randomFee = new long[n];

            for (int i = 0; i < n; i++) {
                randomBase[i] = random.nextInt(21) - 10;
                randomFee[i] = random.nextInt(21) - 10;
            }

            Result expected = baseline(
                separableWeights(randomBase, randomFee)
            );
            Result actual = optimizedSeparable(
                randomBase, randomFee
            );

            if (!sameResult(expected, actual)) {
                throw new AssertionError(
                    "Mismatch at trial " + trial
                );
            }
            checked++;
        }

        System.out.println("Random separable checks: " + checked);

        boolean rejected = false;
        try {
            baseline(new long[0][0]);
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("Empty graph rejected: " + rejected);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 DpOptimizationAssumptionDemo.java
java DpOptimizationAssumptionDemo
```

**Đầu ra chuẩn:**

```text
Counterexample baseline dp: [0, 0, 0, 0]
Counterexample baseline parent: [-1, 0, 1, 0]
Counterexample shortcut dp: [0, 0, 0, 10]
Counterexample shortcut parent: [-1, 0, 1, 1]
Monotone-opt hypothesis holds: false
Separable baseline dp: [0, 13, 5, 10, 4]
Separable optimized dp: [0, 13, 5, 10, 4]
Separable optimized parent: [-1, 0, 1, 1, 1]
Separable same dp and parent: true
Random separable checks: 400
Empty graph rejected: true
```

### Cách diễn giải kết quả

**Nhóm phản ví dụ** chứng minh `dp[3]` đúng bằng `0`, còn hàm áp dụng giả thiết sai trả `10`. Dãy `parent` thật có `1→0` nên không đơn điệu. **Không được dùng `unprovedShortcut` trong bài toán thực**; mục đích duy nhất của hàm là minh họa lỗi.

**Nhóm chi phí tách được** cho thấy baseline và tối ưu hợp lệ cho cùng `dp` và cùng `parent`. Hai mảng khác nhau về cách thực hiện nhưng tương đương vì công thức đại số đã loại phần phụ thuộc `i` khỏi phép min.

**400 ca ngẫu nhiên** được sinh từ `base,fee` rồi xây ma trận `w[j][i]=fee[j]+base[i]`. Điều này kiểm tra đúng **miền đầu vào của tối ưu hóa**. Sinh ma trận ngẫu nhiên tùy ý rồi yêu cầu `optimizedSeparable` giải sẽ là một phép thử không phù hợp với hợp đồng của hàm.

Mã dùng `long` và `Math.addExact` để phát hiện tràn. Đừng dùng `Long.MAX_VALUE` làm “không có ứng viên” rồi cộng trực tiếp; ví dụ dùng cờ `found` ở baseline để không nhầm một giá trị hợp lệ với sentinel. Mỗi `i>=1` đều có ít nhất tiền nhiệm `j=0`, nên `found` cuối cùng luôn đúng.

## 8. Chứng minh tối ưu hợp lệ và vì sao so sánh kết quả chưa đủ

### 8.1. Chứng minh lời giải gốc

Ta chứng minh bằng quy nạp theo `i`.

**Cơ sở:** trạng thái `0` là điểm bắt đầu, chi phí `0`, nên `dp[0]=0`.

**Bước quy nạp:** giả sử mọi `dp[j]` với `j<i` đã là chi phí đường đi nhỏ nhất tới `j`. Một đường đi bất kỳ tới `i` đều có cạnh cuối từ một `j<i`. Chi phí tốt nhất của loại đường đi kết thúc bằng cạnh này là `dp[j]+w[j][i]`. Vì xét **toàn bộ** tiền nhiệm hợp lệ và lấy min, công thức cho đúng giá trị tối ưu tới `i`.

Không có chu trình vì mọi cạnh đi từ chỉ số nhỏ sang chỉ số lớn. Chi phí âm không phá chứng minh quy nạp này. Theo đó, baseline đúng trên miền đầu vào đã định nghĩa.

### 8.2. Bất biến của tối ưu min tiền tố

Giả sử chi phí tách được. Ngay trước khi tính `dp[i]`, duy trì:

\[
bestKey=\min_{0\le j<i}(dp[j]+fee[j]).
\]

Đồng thời `bestIndex` là chỉ số `j` nhỏ nhất đạt min theo quy tắc hòa.

**Cơ sở `i=1`:** mới có `j=0`, nên `bestKey=dp[0]+fee[0]` và `bestIndex=0`.

**Bước:** theo công thức chi phí tách được:

\[
dp[i]=base[i]+bestKey.
\]

Sau đó xuất hiện ứng viên mới `j=i` với khóa `dp[i]+fee[i]`. Nếu nhỏ hơn `bestKey`, cập nhật giá trị và chỉ số; nếu bằng thì giữ chỉ số cũ để khớp chính sách hòa của baseline. Do vậy, bất biến đúng trước khi tính `dp[i+1]`.

Suy ra toàn bộ `dp` và `parent` khớp baseline. Mỗi trạng thái chỉ dùng một phép so sánh min tiền tố, nên thời gian tính `O(n)`.

**Chú ý:** chứng minh này không dựa trên “dữ liệu trông có vẻ đơn điệu”. Nó dựa trên **đẳng thức đại số đúng với mọi cặp `j<i`** trong họ đầu vào tách được.

### 8.3. Kiểm thử chỉ chứng minh điều gì?

Nếu chương trình trên kiểm tra 400 ca thành công, kết luận đúng là:

> Cài đặt optimized đã khớp baseline trên 400 đầu vào tách được đã sinh.

Kết luận **không hợp lệ** là:

> Vì 400 ca đều đúng nên mọi đầu vào tùy ý đều dùng được optimized.

Khả năng áp dụng đến từ **điều kiện chi phí tách được**, được kiểm tra bằng hợp đồng và chứng minh. Kiểm thử giúp phát hiện sai sót trong mã như lệch chỉ số, xử lý hòa, cập nhật quá sớm hoặc cộng sai thứ tự.

## 9. Các giả thiết thường xuất hiện trong tối ưu DP

Mỗi kỹ thuật có một loại **bất biến hoặc tính chất cấu trúc** riêng. Không thể chỉ nhìn thấy một phép `min` là lập tức chọn công cụ.

| Kỹ thuật | Điều kiện cần kiểm tra | Phản ví dụ/lỗi điển hình |
|---|---|---|
| **Prefix min/max** | Khóa ứng viên cố định sau khi tạo; tập ứng viên là tiền tố tăng dần | Khóa thật sự phụ thuộc vào `i`, nên ứng viên cũ có thể tốt lên |
| **Deque đơn điệu** | Cửa sổ chỉ tiến về phía trước; khóa ứng viên không đổi; chỉ cần min/max | Chỉ số hết hạn quay lại, hoặc dùng sai khóa `dp[j]` |
| **Divide-and-Conquer DP optimization** | Vị trí argmin **đơn điệu trong cùng một lớp DP** với quy tắc hòa nhất quán | `opt[i+1]<opt[i]` và dải tìm kiếm bị cắt mất đáp án |
| **Knuth optimization** | Công thức chia đoạn đúng dạng, cùng các điều kiện dẫn đến giới hạn `opt[l][r-1]\le opt[l][r]\le opt[l+1][r]` | Giả định bất đẳng thức Knuth trên chi phí bất kỳ |
| **Convex Hull Trick (CHT)** | Chuyển trạng thái thành truy vấn min/max các đường thẳng; chọn biến thể phù hợp với thứ tự dốc và truy vấn | Dùng deque hull yêu cầu thứ tự dốc/truy vấn đơn điệu nhưng dữ liệu không thỏa |
| **Rolling array DP** | Chỉ phụ thuộc một số hàng trước; chiều cập nhật không dùng nhầm giá trị mới | Bài 0/1 cập nhật tổng tăng nên dùng cùng phần tử hai lần |
| **Two pointers / sliding window** | Điều kiện khả thi hoặc giá trị cần tìm thay đổi theo hướng có thể kiểm soát khi dịch biên | Biên trái cần đi lùi nhưng thuật toán chỉ tăng |
| **Binary search on answer** | Mệnh đề khả thi `feasible(x)` có tính đơn điệu theo `x` | Có `x<y<z` với khả thi đúng/sai/đúng, khiến tìm kiếm nhị phân sai |

Các dòng trong bảng là **điểm kiểm tra**, không phải bản chứng minh đầy đủ cho mọi thuật toán. Chẳng hạn, với Divide-and-Conquer DP, cần xác định rõ:

\[
dp[t][i]=\min_{j\in J(i)}\{dp[t-1][j]+C(j,i)\},
\]

rồi chứng minh `opt[t][i]` không giảm theo `i` **với `t` cố định** và chi phí tính mỗi `C(j,i)` phù hợp. Không được lấy sự đơn điệu quan sát được của `opt[t-1]` để thay cho `opt[t]`.

### 9.1. Tính Monge và bất đẳng thức tứ giác

Một ma trận `C` được gọi là **Monge** theo một quy ước phổ biến nếu với `a<b`, `c<d`:

\[
C(a,c)+C(b,d)\le C(a,d)+C(b,c),
\]

trên những tổ hợp chỉ số mà các phần tử liên quan đều có nghĩa. Tính chất này tạo cấu trúc hữu ích cho nhiều bài toán tối ưu hàng và có thể dẫn đến tính đơn điệu của argmin dưới điều kiện thích hợp.

Nhưng việc đề **không nêu hoặc không suy ra** tính chất Monge là một cảnh báo lớn. Không thể chứng minh Monge bằng cách chỉ thử vài bộ `(a,b,c,d)`. Cần suy ra từ **công thức chi phí thực tế** hoặc điều kiện đầu vào.

Đối với **Knuth**, ngoài công thức DP theo đoạn còn cần các điều kiện về hàm chi phí, thường liên quan tính Monge/quadrangle inequality và tính đơn điệu theo đoạn. Nếu không chứng minh được các điều kiện đủ, nên dùng lời giải gốc trước.

### 9.2. Ví dụ khóa thay đổi theo `i`

Xét hai ứng viên cho một chuyển trạng thái có chi phí:

\[
value(j,i)=dp[j]+(i-j)^2.
\]

Giả sử `j_1=0` với `dp[0]=0` và `j_2=2` với `dp[2]=10`.

- Ở `i=3`: ứng viên `j_1` có giá trị `9`; `j_2` có giá trị `11`. Ứng viên cũ `j_1` tốt hơn.
- Ở `i=10`: `j_1` có giá trị `100`; `j_2` có giá trị `74`. Lần này `j_2` tốt hơn.

**Thứ tự tốt–xấu đổi theo đích `i`.** Vì thế không thể giữ deque min đơn điệu dựa riêng vào `dp[j]` và xóa vĩnh viễn các ứng viên có `dp` lớn hơn. Với công thức có bình phương khoảng cách, có thể biến đổi sang dạng đường thẳng và cân nhắc CHT/Li Chao nếu thỏa các điều kiện tương ứng.

### 9.3. Rolling array: một phản ví dụ chỉ với một số

Trong bài Subset Sum **mỗi phần tử dùng tối đa một lần**, dùng `dp[s]` boolean và cập nhật tại chỗ. Nếu duyệt `s` tăng dần, phần tử vừa thêm có thể được dùng lại:

```text
a = [3], T = 6

Trước khi xét 3:
  dp[0]=true, còn lại false.

Duyệt SAI theo s tăng:
  s=3: dp[3] |= dp[0] -> true
  s=6: dp[6] |= dp[3] -> true (dp[3] vừa được cập nhật!)

Chương trình sai, cho rằng 6=3+3 dù chỉ có một phần tử 3.

Duyệt ĐÚNG theo s giảm:
  s=6: dp[3] còn false -> không bật dp[6]
  s=3: dp[0] true -> bật dp[3]

Kết quả đúng: T=6 không thể đạt.
```

Đây không phải lỗi của công thức DP hai hàng; nó là lỗi khi **nén bộ nhớ** mà không giữ đúng quan hệ “đọc hàng cũ”. Một tối ưu bộ nhớ cũng cần **chứng minh bất biến cập nhật** giống tối ưu thời gian.

### 9.4. Deque min: không được lấy ứng viên đã hết hạn

Giả sử:

\[
dp[i]=cost[i]+\min_{i-k\le j<i}dp[j].
\]

Nếu giữ chỉ số `j<i-k` trong deque, có thể chọn một tiền nhiệm mà bước nhảy dài **hơn `k`**, tạo lời giải không hợp lệ. Điều kiện xóa đúng là **`front<i-k`**; chỉ số `j=i-k` vẫn hợp lệ.

Khi áp dụng deque, cần kiểm tra **hai** lý do được xóa:

- Xóa **đầu** vì ứng viên đã ra ngoài cửa sổ.
- Xóa **đuôi** vì có ứng viên mới hơn và không kém về giá trị.

Một kiểm thử chỉ kiểm tra thứ tự giá trị nhưng không kiểm tra **giới hạn chỉ số** vẫn có thể bỏ sót lỗi.

## 10. Quy trình kiểm chứng tối ưu hóa trong một dự án Java

Một quy trình thực tế nên có những hiện vật rõ ràng, không chỉ câu “đã test”.

### Bước 1: Đóng băng định nghĩa bài toán

Viết ra đầy đủ:

- Trạng thái `dp[...]` và kết quả cần trả.
- Các lựa chọn hợp lệ, điều kiện biên và thứ tự tính.
- Trạng thái khởi tạo, trạng thái không thể đạt.
- Kiểu số, giới hạn giá trị, có chi phí âm không.
- Quy tắc hòa khi trả cả đường đi/chỉ số quyết định.

Nếu hợp đồng mơ hồ, hai thuật toán có thể cùng “đúng” nhưng đang giải **hai phiên bản khác nhau**.

### Bước 2: Viết baseline dễ chứng minh

Ưu tiên cách rõ ràng, dù `O(n²)` hoặc `O(nk)`, miễn là dữ liệu nhỏ chạy được. Không đồng thời “tối ưu” luôn baseline bằng một cấu trúc phức tạp; nếu hai hàm cùng chia sẻ một lỗi, đối chiếu sẽ không phát hiện.

Với trạng thái không thể đạt, dùng cờ khả thi hoặc sentinel an toàn; tuyệt đối không để `INF+value` bị tràn rồi tạo kết quả nhỏ giả. Đừng bỏ kiểm tra đầu vào chỉ vì baseline là công cụ kiểm thử.

### Bước 3: Viết giả thiết dưới dạng mệnh đề

Ví dụ:

```text
H1: argmin không giảm theo i trong cùng một lớp.
H2: cửa sổ chuyển chỉ tiến sang phải.
H3: key(j) không phụ thuộc i sau khi được tạo.
H4: quan hệ chi phí có dạng tách được base[i]+fee[j].
H5: mọi kết quả DP cần cho bước sau còn tồn tại
    sau khi tối ưu bộ nhớ.
```

Với mỗi giả thiết, hỏi: **trong đề bài, điều kiện nào bảo đảm nó?** Nếu câu trả lời chỉ là “các ví dụ tôi thử đều thế”, cần kiểm tra thêm trước khi dùng.

### Bước 4: Chủ động tìm phản ví dụ

Không chỉ sinh dữ liệu ngẫu nhiên đồng đều. Cần chủ động tạo:

- Các chi phí **đảo lợi thế** giữa hai tiền nhiệm khi `i` thay đổi.
- Các kết quả **bằng nhau**, nhằm kiểm tra chính sách phá hòa.
- Các trường hợp min/max nằm sát **biên cửa sổ**.
- Giá trị âm, `0`, cực trị kiểu số nếu được phép.
- Mảng ngắn `n=1,2,3,4`.
- Dữ liệu có nhiều phần tử trùng hoặc tất cả bằng nhau.
- Trạng thái có đường đi tối ưu **nhảy qua nhiều chỉ số**.
- Những cấu trúc sát ranh giới của điều kiện tối ưu, ví dụ vi phạm đúng **một** bất đẳng thức cần chứng minh.

Khi tìm thấy phản ví dụ, **thu nhỏ** nó trước khi sửa thuật toán. Một phản ví dụ bốn trạng thái như ở phần 3 dễ kiểm tra hơn một ma trận một nghìn trạng thái.

### Bước 5: So sánh toàn bộ bảng, không chỉ đáp án

Nếu `dp` hoặc `parent` khác nhau tại vị trí `i`, ghi lại:

```text
firstMismatch = i

candidateSetBaseline = mọi j hợp lệ
candidateSetOptimized = những j thuật toán nhanh còn xét
lostCandidates = candidateSetBaseline - candidateSetOptimized
bestLostValue = min giá trị của những ứng viên bị bỏ
bestRetainedValue = min giá trị của những ứng viên còn giữ
```

Nếu `bestLostValue<bestRetainedValue`, ta đã xác định một nguyên nhân cụ thể: tối ưu đã bỏ ứng viên cần thiết.

Đừng yêu cầu `parent` luôn trùng nếu hợp đồng chỉ cần **giá trị tối ưu** và hai hàm có chính sách hòa khác nhau. Trong bài kiểm tra này, hai hàm hợp lệ dùng cùng quy tắc hòa nên có thể so cả `parent`. Với bài toán chỉ cần giá trị, đúng hơn là so giá trị và kiểm tra đường đi trả về **hợp lệ và đạt giá trị ấy**.

### Bước 6: Chứng minh và đo hiệu năng riêng

**Tính đúng** và **tốc độ** là hai kiểm tra độc lập:

- Chứng minh tối ưu chỉ bỏ những ứng viên **không thể cải thiện đáp án**.
- Đếm tổng số thao tác để chứng minh độ phức tạp.
- Benchmark với dữ liệu phù hợp, làm nóng JVM, không đánh giá chỉ một lần chạy nhỏ.
- Nếu cách nhanh không đúng, **không dùng kết quả benchmark để biện minh**.

Một cách triển khai `O(n)` nhưng giải sai bài toán kém giá trị hơn một baseline `O(n²)` đúng. Đổi lại, một “tối ưu” không cải thiện được độ phức tạp hay thời gian thực tế cũng cần được đánh giá trên chi phí bảo trì và kiểm thử.

## 11. Những sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
|---|---|---|
| “Trên dữ liệu mẫu argmin luôn tăng” | Mẫu nhỏ không đại diện cho mọi input | Chứng minh cấu trúc hoặc tìm phản ví dụ |
| Áp dụng D&C DP trên một chiều chỉ vì có phép min | Không đúng giả thiết đơn điệu trong lớp DP | Viết rõ `opt[t][i]` và miền ứng viên |
| Không chốt chính sách hòa | Hai cách hợp lệ cho cùng giá trị nhưng chỉ số khác nhau | So đáp án cần thiết; quy định hòa nếu cần truy vết |
| Dùng baseline cũng đã tối ưu bằng cùng giả thiết | Cả hai hàm có thể sai giống nhau | Baseline phải xét **tất cả lựa chọn hợp lệ** |
| Chỉ so kết quả cuối | Lỗi nội bộ có thể tình cờ bị che | So trạng thái trung gian và tìm điểm lệch đầu tiên |
| Chỉ kiểm thử dữ liệu ngẫu nhiên | Hiếm gặp tình huống biên có cấu trúc | Thêm ca thiết kế và phản ví dụ nhỏ |
| Dùng phản ví dụ vi phạm ràng buộc đề | Không bác bỏ thuật toán trong miền được phép | Xác minh input hợp lệ trước khi kết luận |
| Tìm không thấy phản ví dụ rồi coi như đã chứng minh | Kiểm thử hữu hạn không bảo đảm mọi input | Tách “test pass” khỏi “định lý đã chứng minh” |
| Tối ưu hóa trước khi chốt trạng thái | Có thể thay đổi luôn bài toán | Chốt hợp đồng và công thức DP trước |
| Khóa deque/CHT thay đổi mà vẫn xóa ứng viên vĩnh viễn | Ứng viên tệ hiện tại có thể tốt về sau | Biến đổi đại số hoặc dùng cấu trúc phù hợp |
| Lầm lẫn min và max | Hướng loại ứng viên bị đảo | Đặt rõ thứ tự so sánh và kiểm thử riêng |
| Sai biên `<`/`<=` | Loại nhầm một ứng viên hợp lệ | Kiểm thử cửa sổ chạm biên |
| Nén DP một chiều cập nhật sai thứ tự | Dùng dữ liệu của lượt hiện tại làm dữ liệu cũ | Chứng minh phụ thuộc và hướng cập nhật |
| Cộng sentinel hoặc tràn số | Ứng viên giả có thể trông tốt nhất | Kiểm tra khả thi và dùng số đủ rộng |
| Khẳng định `O(n)` chỉ vì vòng ngoài một lần | Vòng trong/while có thể có chi phí đáng kể | Phân tích khấu hao hoặc đếm trạng thái |
| Quên lưu seed và phản ví dụ | Không tái hiện được lỗi | Lưu test cố định để chạy lại |
| Dùng cùng hàm tạo trạng thái sai cho cả baseline và optimized | Kết quả trùng nhưng input bị chuẩn hóa sai | Kiểm tra định nghĩa input từ một oracle độc lập |
| So `parent` dù tối ưu có tie-break khác | Báo sai lỗi dù giá trị bằng nhau | Thống nhất tie-break hoặc chỉ so phần hợp đồng yêu cầu |

## 12. Bài tập và phản ví dụ thực hành

**Bài 1 — Tự tính phản ví dụ.** Với các cạnh `0→1:0`, `0→2:10`, `1→2:0`, `0→3:0`, `1→3:10`, `2→3:10`, hãy tính `dp[]` và `parent[]`.

*Đáp án:* `dp=[0,0,0,0]`, `parent=[-1,0,1,0]`. Giả thiết `parent` không giảm sai từ `i=2` sang `i=3`.

**Bài 2 — Chỉ rõ ứng viên bị mất.** Nếu khi tính `i=3` chỉ xét `j\ge parent[2]`, kết quả sai là bao nhiêu?

*Đáp án:* chỉ còn `j=1,2`, đều cho chi phí `10`; mất `j=0` cho chi phí `0`. Kết quả sai là `10`.

**Bài 3 — Nhìn các giá trị không âm.** Phản ví dụ ở bài 1 có cạnh âm không? Vì sao điều này quan trọng?

*Đáp án:* không, mọi chi phí cạnh đều không âm. Vì vậy giả thiết đơn điệu không thể được cứu chỉ bằng điều kiện “trọng số không âm”.

**Bài 4 — Biến đổi công thức.** Cho `w[j][i]=fee[j]+base[i]`. Hãy biến đổi `dp[i]=min_j(dp[j]+w[j][i])` thành dạng dùng prefix min.

*Đáp án:* `dp[i]=base[i]+\min_{j<i}(dp[j]+fee[j])`. Khóa lưu là `dp[j]+fee[j]`.

**Bài 5 — Tính min tiền tố.** Với `base=[0,5,2,7,1]`, `fee=[8,-10,4,-3,0]`, hãy tính `dp` và `parent`.

*Đáp án:* `dp=[0,13,5,10,4]`, `parent=[-1,0,1,1,1]`.

**Bài 6 — Rolling array sai chiều.** Với 0/1 Subset Sum `a=[3]`, `T=6`, hãy chỉ ra thứ tự cập nhật tạo ra kết quả sai.

*Đáp án:* duyệt `s=3` rồi `s=6` khiến `dp[6]` đọc `dp[3]` vừa bật bởi cùng phần tử `3`. Phải duyệt tổng giảm.

**Bài 7 — Giả thiết deque.** Với `value(j,i)=dp[j]+(i-j)^2`, lấy `dp[0]=0`, `dp[2]=10`, so ứng viên `j=0` và `j=2` tại `i=3` và `i=10`.

*Đáp án:* tại `3`: `9<11` nên `j=0` tốt hơn; tại `10`: `100>74` nên `j=2` tốt hơn. Thứ tự ứng viên thay đổi; không dùng deque min theo `dp[j]` trực tiếp.

**Bài 8 — Test oracle.** Viết một hàm vét cạn liệt kê tất cả đường đi tăng chỉ số từ `0` tới `n-1` cho `n<=10`, rồi so với `baseline`. Vì sao cách này mạnh hơn việc chỉ đối chiếu baseline với một phiên bản optimized?

*Gợi ý:* hai thuật toán DP có thể cùng mắc lỗi trạng thái/khởi tạo; vét cạn được xây theo định nghĩa đường đi cung cấp một cách đối chứng khác.

**Bài 9 — Thu nhỏ phản ví dụ.** Một bộ sinh ngẫu nhiên tìm thấy `n=50` với `dpFast[n-1]!=dpSlow[n-1]`. Hãy đề xuất ba thao tác để rút về một ca dễ đọc.

*Gợi ý:* tìm vị trí sai đầu tiên; xóa các trạng thái/cạnh không ảnh hưởng tới sai khác; giảm độ lớn và số lượng giá trị riêng, giữ nguyên điều kiện phản ví dụ. Sau đó lưu thành regression test.

**Bài 10 — Đúng về đáp án, khác về chỉ số.** Một baseline và một tối ưu đều đạt chi phí `5` nhưng chọn hai `parent[i]` khác nhau. Có thể kết luận tối ưu sai không?

*Đáp án:* chưa. Nếu có nhiều tiền nhiệm cùng chi phí và đề chỉ hỏi **giá trị**, cả hai có thể đúng. Cần kiểm tra quy tắc phá hòa nếu đề yêu cầu đường đi/chỉ số cụ thể.

**Bài 11 — Khi nào dùng D&C DP?** Hãy nêu điều cần xác nhận trước khi thu hẹp miền `j` bằng kết quả `opt` của một lời giải trước đó.

*Gợi ý:* phải phát biểu rõ trạng thái theo lớp, miền ứng viên và chứng minh `opt[t][i]` đơn điệu theo `i` dưới công thức chi phí cụ thể. Quan sát trên dữ liệu mẫu không đủ.

## 13. Ghi nhớ và mẫu tư duy

**Không tối ưu bằng một giả thiết chỉ vì nó “trông đúng”.** Với DP, đường đi an toàn nhất là:

\[
\boxed{\text{Định nghĩa trạng thái}
\rightarrow \text{Baseline đúng}
\rightarrow \text{Giả thiết rõ}
\rightarrow \text{Tìm phản ví dụ}
\rightarrow \text{Chứng minh}
\rightarrow \text{Tối ưu và đối chứng}}
\]

Từ một ma trận có **bốn trạng thái và toàn chi phí không âm**, ta đã thấy chỉ số tiền nhiệm tối ưu có thể **giảm**, khiến cách cắt miền tìm kiếm theo argmin trước đó trả sai `10` thay vì `0`.

Ngược lại, khi chi phí thực sự có dạng `fee[j]+base[i]`, phép tách đại số cho phép duy trì min tiền tố với chứng minh rõ ràng và giảm thời gian **`O(n²)→O(n)`**. Điều kiện đúng **đến trước** tối ưu; kiểm thử ngẫu nhiên và ví dụ chạy được xác nhận cách cài đặt **sau** chứng minh.

**Một phản ví dụ hợp lệ bác bỏ một định đề phổ quát. Một bộ test PASS chỉ củng cố niềm tin vào cài đặt trong miền đã thử. Chứng minh cấu trúc mới bảo đảm tối ưu hóa an toàn cho mọi đầu vào thỏa điều kiện.**
