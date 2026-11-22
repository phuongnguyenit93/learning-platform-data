# Mã hóa tập trạng thái bằng mặt nạ bit

Trong nhiều bài **quy hoạch động cấu trúc**, thông tin quyết định bước tiếp theo không chỉ là một chỉ số hay một tổng tiền, mà là **những đối tượng nào đã được chọn, đã thăm hoặc đã sử dụng**. Ví dụ: đã giao những công việc nào cho nhân viên, đã ghé những thành phố nào, hay những phần tử nào đã nằm trong tập con đang xét. Nếu chỉ có một số nhỏ đối tượng (thường vài chục hoặc ít hơn), ta có thể biểu diễn toàn bộ tập đó bằng các bit của một số nguyên. Kỹ thuật này gọi là **mặt nạ bit (bitmask)**.

Mỗi bit tương ứng một đối tượng; bit bằng **1** nghĩa là đối tượng thuộc tập, bit bằng **0** nghĩa là chưa thuộc tập. Một tập con được mã hóa thành một số nguyên, nên ta có thể kiểm tra, thêm, bớt phần tử hoặc truy cập trạng thái DP rất nhanh.

**Cảnh báo quan trọng:** Bitmask **không tự động** làm bài toán chạy nhanh theo đa thức. Có `2^n` tập con của `n` đối tượng, nên DP trên mọi mask thường là thuật toán **hàm mũ theo `n`**. Bitmask giúp tổ chức trạng thái rõ, tiết kiệm bộ nhớ so với lưu tập đối tượng tùy ý và giảm hằng số thao tác; phải luôn đánh giá ngưỡng `n` thực tế.

Bài học này giải thích cách mã hóa tập, các phép toán bit cốt lõi trong Java 17+, cách duyệt tập con, công thức DP theo tập đã chọn, bài **phân công công việc tối ưu**, **đường Hamilton ngắn nhất**, **tổng trên mọi tập con (SOS DP)**, chứng minh tính đúng và kiểm thử độc lập.

## 1. Một tập hợp có thể biến thành một số nguyên như thế nào?

Cho tập đối tượng có chỉ số từ `0` đến `n−1`:

```text
U = {0, 1, ..., n-1}
```

Với tập con `S⊆U`, đặt:

```text
mask(S) = sum(2^i), với mọi i thuộc S
```

Bit thứ `i` (tính từ phải sang trái, bắt đầu ở 0) là 1 **nếu và chỉ nếu** `i∈S`.

Ví dụ `n=4`:

| Tập con `S` | Nhị phân 4 bit | Số nguyên mask |
| --- | --- | ---: |
| `{}` | `0000` | `0` |
| `{0}` | `0001` | `1` |
| `{1}` | `0010` | `2` |
| `{0,2}` | `0101` | `5` |
| `{0,2,3}` | `1101` | `13` |
| `{0,1,2,3}` | `1111` | `15` |

Với `n` bit, số mask hợp lệ là từ **`0` đến `(1<<n)−1`** (trong biểu thức Java, chỉ dùng trực tiếp công thức đó khi `n` đủ nhỏ để phép dịch không tràn kiểu số). Tổng số mask là **`2^n`** vì mỗi trong `n` bit có hai lựa chọn độc lập: 0 hoặc 1.

**Ánh xạ là một-một:** Hai tập con khác nhau phải khác ở ít nhất một phần tử, nên khác ở ít nhất một bit và có mask khác nhau. Ngược lại, đọc các vị trí bit bằng 1 sẽ khôi phục đúng tập ban đầu. Đây là cơ sở để dùng `dp[mask]` làm **mảng trạng thái theo tập con**.

### Mask là tập, không phải thứ tự

`{1,3}` và `{3,1}` có cùng mask vì **tập không mang thứ tự**. Nếu bài toán còn cần biết **đối tượng nào được chọn cuối cùng** (đường đi, chuỗi thao tác), mask **một mình không đủ**; thường phải có thêm một biến như `last`:

```text
dp[mask][last]
```

Nếu bài cần ghi lại **thứ tự đầy đủ của lựa chọn**, có thể dựng lại từ thông tin cha (`parent`) hoặc dùng trạng thái khác. **Không nhầm tập đã chọn với hoán vị đã chọn.**

## 2. Các phép toán bit thiết yếu

Đặt `bit(i)=1<<i` với `i` là chỉ số bit hợp lệ và dùng `int` an toàn khi `0≤i≤30` cho mask không âm. Trong code Java ở bài này, các thuật toán dùng `n≤20` hoặc `n≤15` để hạn chế **số trạng thái cần cấp phát**, thấp hơn nhiều so với giới hạn kiểu số.

| Mục đích | Biểu thức Java | Diễn giải |
| --- | --- | --- |
| Kiểm tra phần tử `i` thuộc tập | `(mask & (1 << i)) != 0` | Lấy AND để xét bit `i` |
| Thêm phần tử `i` | `mask \| (1 << i)` | OR đặt bit thành 1 |
| Xóa phần tử `i` | `mask & ~(1 << i)` | AND với bit bổ sung để xóa |
| Đảo trạng thái của `i` | `mask ^ (1 << i)` | XOR làm 0→1, 1→0 |
| Đếm số phần tử | `Integer.bitCount(mask)` | Số bit 1 trong `int` |
| Tập rỗng | `mask == 0` | Không có bit 1 |
| Tập đầy đủ của `n` phần tử | `(1 << n) - 1` | `n` bit thấp nhất đều là 1 |
| Phần tử còn lại | `fullMask & ~mask` | Lấy các bit thuộc miền `U` nhưng chưa chọn |
| Lấy bit 1 thấp nhất | `mask & -mask` | Chỉ giữ bit 1 thấp nhất khi `mask!=0` |
| Xóa bit 1 thấp nhất | `mask & (mask - 1)` | Giảm số bit 1 đi một |
| Lấy chỉ số bit 1 thấp nhất | `Integer.numberOfTrailingZeros(mask)` | Chỉ dùng làm chỉ số khi `mask!=0` |
| Kiểm tra `A` là tập con của `B` | `(A & B) == A` | Mọi bit 1 của `A` cũng có trong `B` |
| Giao của hai tập | `A & B` | Bit xuất hiện trong cả hai |
| Hợp của hai tập | `A \| B` | Bit xuất hiện ở ít nhất một tập |
| Hiệu `A\B` | `A & ~B` | Giữ bit của A không thuộc B |

Khi viết Markdown, ký hiệu `\|` trong cột biểu thức là toán tử **bitwise OR** của Java; không phải phép OR logic `||`. Trong mã Java thực tế dùng ký hiệu `|` bình thường.

### Ví dụ với `mask=13`

`13=1101₂` biểu diễn tập `{0,2,3}`:

```text
mask = 13                    // 1101
mask & (1 << 2) != 0         // true, có phần tử 2
mask | (1 << 1)             // 1111 = 15, thêm phần tử 1
mask & ~(1 << 2)            // 1001 = 9, xóa phần tử 2
mask ^ (1 << 1)             // 1111 = 15, đảo bit 1
Integer.bitCount(mask)      // 3
mask & -mask                // 0001 = 1, bit thấp nhất
mask & (mask-1)             // 1100 = 12, bỏ bit thấp nhất
fullMask & ~mask            // 0010 = 2, phần tử chưa chọn
```

**Xóa và toggle khác nhau:** `mask & ~(1<<i)` đảm bảo bit `i` bằng 0, kể cả khi nó đã bằng 0. `mask ^ (1<<i)` **đảo** bit: nếu bit đang bằng 0, nó trở thành 1. Không dùng toggle để “xóa” khi chưa chứng minh bit đang có trong mask.

### Đừng quên giới hạn kiểu số và toán tử dịch của Java

Java `int` có **32 bit**, `long` có **64 bit**. Các phép dịch `int` chỉ dùng 5 bit thấp của số vị trí dịch (tương đương modulo 32), còn với `long` chỉ dùng 6 bit thấp (modulo 64):

```java
1 << 32     // Bằng 1 << 0, không phải 2^32.
1L << 64    // Bằng 1L << 0.
1 << 31     // Bit dấu bật; kết quả int âm.
1L << 31    // long dương, khác 1 << 31.
```

Vì vậy phải **xác thực `n` trước khi tạo `1<<n`**, không dùng `1<<n` khi `n≥31` để cấp phát một mảng `2^n` phần tử. Ngay cả `n=30`, một mảng hàng tỷ phần tử cũng thường **không khả thi về RAM**.

Nếu muốn lưu tối đa khoảng **63 bit không dấu theo tập hợp** bằng `long`, phải lập trình rõ tình huống bit dấu và các giới hạn dịch; dễ hiểu nhất là giữ `n≤62` nếu cần mask long **không âm** và công thức `(1L<<n)-1`. Nếu `n` lớn hơn, cân nhắc `BitSet` hoặc cấu trúc tập thích hợp. **`BitSet` không giải quyết được bài toán số lượng `2^n` trạng thái** nếu DP vẫn cần duyệt mọi tập con.

Khi thao tác độ ưu tiên dễ nhầm, dùng ngoặc:

```java
boolean selected = (mask & (1 << i)) != 0;
int remaining = fullMask & ~mask;
```

Không viết công thức thiếu ngoặc rồi dựa vào trí nhớ về độ ưu tiên của toán tử `&`, `==`, `<<` hoặc `^`.

## 3. Duyệt các bit 1 và các tập con của một mask

### 3.1. Duyệt từng phần tử đã chọn

Cách đơn giản duyệt mọi chỉ số từ `0..n−1` và kiểm tra bit; thời gian `O(n)` kể cả khi tập chỉ có một phần tử. Khi mask thưa, dùng kỹ thuật lấy bit 1 thấp nhất:

```java
int remaining = mask;
while (remaining != 0) {
    int bit = remaining & -remaining;
    int index = Integer.numberOfTrailingZeros(bit);
    // Xử lý phần tử index.
    remaining &= remaining - 1;
}
```

Đoạn trên có **số vòng đúng bằng `popcount(mask)`**. Toán tử `remaining & -remaining` dựa trên biểu diễn bù hai, hoạt động với số nguyên trong Java; ví dụ code chỉ dùng mask không âm.

### 3.2. Duyệt các phần tử chưa chọn

Nếu `full=(1<<n)-1` và `mask` chứa các bit đã chọn, đặt `available=full & ~mask`. Duyệt các bit 1 trong `available` để sinh **các đối tượng có thể chọn tiếp**.

Đây là lõi của nhiều công thức DP:

```text
for each mask:
    available = full & ~mask
    for each bit i in available:
        next = mask | (1 << i)
        relax(dp[next], dp[mask] + cost(mask,i))
```

**Bất biến:** `next` có đúng **một phần tử mới** so với `mask`, do `i` chỉ được chọn từ các bit đang bằng 0. Vì vậy `popcount(next)=popcount(mask)+1`. Các cạnh phụ thuộc đi từ tập nhỏ sang tập lớn, tạo **DAG trạng thái**; có thể duyệt `mask` tăng dần vì thêm một bit 1 luôn làm số mask tăng.

### 3.3. Duyệt mọi tập con không rỗng của một mask

Đoạn mã kinh điển:

```java
for (int sub = mask; sub != 0; sub = (sub - 1) & mask) {
    // sub là một tập con không rỗng của mask.
}
```

Với `mask=13` (`1101₂`, ba bit 1), các `sub` lần lượt là:

```text
13 (1101) -> 12 (1100) -> 9 (1001) -> 8 (1000)
           -> 5 (0101) -> 4 (0100) -> 1 (0001)
```

Có đúng **`2^3−1=7` tập con không rỗng**, gồm cả chính `mask`. Nếu muốn tính cả tập rỗng, xử lý `sub=0` **riêng**; không viết vòng tự giảm từ 0 rồi AND mask vì có thể quay lại mask và tạo vòng vô hạn.

**Không được gọi các giá trị `sub` trên là “tập con thực sự (proper subset)”** nếu vòng bắt đầu từ `mask`, vì có chứa chính `mask`. Một tập con thực sự phải khác `mask` và có thể bao gồm tập rỗng tùy định nghĩa toán học.

### Vì sao duyệt mọi cặp (mask, submask) có thể là `O(3^n)`?

Nếu chạy:

```text
for every mask in [0,2^n):
    for every sub subset of mask:
        process(mask,sub)
```

Với mỗi phần tử trong `U`, có **ba trạng thái** trong một cặp `(mask,sub)`: nằm ngoài `mask`, nằm trong `mask` nhưng ngoài `sub`, hoặc nằm trong cả hai. Do đó số cặp `sub⊆mask⊆U` đúng bằng **`3^n`** khi bao gồm tập rỗng. Nếu chỉ duyệt `sub` khác rỗng, số cặp là **`3^n−2^n`**, vì có `2^n` cặp với `sub=0`.

**Đánh đổi:** Dùng bitmask không làm vòng lặp submask lồng trong mọi mask thành `O(n2^n)`. Phải phân biệt `2^n` mask, `n2^n` chuyển trạng thái thêm một bit và `3^n` cặp mask/submask.

## 4. Thiết kế DP theo tập: ý nghĩa trạng thái quyết định chiều chuyển

Mẫu phổ biến:

```text
dp[mask] = đáp án tốt nhất sau khi đã chọn đúng tập mask.
```

Ví dụ `n` công việc khác nhau, ở mỗi bước chọn một công việc chưa dùng. Nếu số bước đã hoàn thành là `k=popcount(mask)`, ta biết bước kế tiếp là `k` mà không cần lưu `k` trong state. Cần chứng minh:

1. Mọi đường đi tới cùng `mask` có cùng số bước `popcount(mask)`.
2. Những lựa chọn hợp lệ tương lai chỉ phụ thuộc vào `mask` (và dữ liệu cố định), **không phụ thuộc thứ tự quá khứ**.
3. Giá trị tốt nhất ở `mask` có thể kết hợp với mọi lựa chọn tiếp theo theo một công thức cộng chi phí, `min` hoặc `max` phù hợp.

Khi ba điều trên đúng, có thể **gộp các đường đi có cùng mask** vào một ô DP mà vẫn giữ tối ưu. Nếu tương lai còn phụ thuộc **đỉnh cuối**, **thời điểm**, **năng lượng** hoặc biến nào khác, phải **mở rộng state** tương ứng.

### Khởi tạo đúng cho bài toán tối ưu

Ví dụ tìm chi phí tối thiểu:

```text
dp[0] = 0
dp[mask != 0] = INF

for each reachable mask:
    for each legal next choice:
        dp[nextMask] = min(dp[nextMask], dp[mask] + transitionCost)
```

Ở đây `INF` là giá trị **không thể đạt được**, không phải đáp án 0. Với chi phí có thể bằng 0, khởi tạo mọi ô bằng 0 sẽ cho kết quả sai vì trạng thái chưa từng đạt được có vẻ có chi phí bằng 0. Khi dùng `long`, chọn sentinel đủ lớn và **không cộng chi phí nếu trạng thái là `INF`** để tránh overflow.

Với bài **đếm số cách**, dùng `ways[0]=1` và cộng số cách từ mỗi trạng thái. Với bài **khả thi**, dùng `boolean` và OR. Toán tử kết hợp phụ thuộc đúng câu hỏi; “bitmask DP” chỉ nói về **mã hóa state**, không quyết định hàm mục tiêu.

### Tại sao thường duyệt mask tăng dần?

Nếu mỗi chuyển tiếp thêm ít nhất một bit `0→1` và không xóa bit, thì `nextMask > mask` theo giá trị nguyên không âm. Duyệt `mask=0..full` bảo đảm nguồn được tính trước đích trong DAG. Nếu công thức chuyển tiếp **xóa phần tử**, nên duyệt chiều ngược hoặc dùng thứ tự theo số bit/quan hệ phụ thuộc đã chứng minh. Không đảo chiều tùy ý.

## 5. Bài toán phân công công việc tối ưu: một chiều `dp[mask]`

Có `n` người `0..n−1` và `n` công việc `0..n−1`. Mỗi người nhận **đúng một** công việc, mỗi công việc giao cho **đúng một** người. Biết chi phí `cost[person][job]≥0`. Tìm tổng chi phí nhỏ nhất.

### State

```text
dp[mask] = chi phí nhỏ nhất để giao k người đầu tiên
           (người 0..k-1) cho đúng tập công việc mask,
           với k = popcount(mask).
```

Không cần lưu `k` riêng: mọi cách tới `mask` có đúng `k` công việc đã giao, nên người tiếp theo luôn là người `k`.

**Cơ sở:** `dp[0]=0`, còn các mask khác ban đầu `INF`.

**Chuyển tiếp:** Nếu `k<n`, chọn một công việc `job` chưa thuộc mask:

```text
next = mask | (1 << job)
dp[next] = min(dp[next], dp[mask] + cost[k][job])
```

**Đáp án:** `dp[(1<<n)-1]`, khi mọi công việc đã được giao.

### Ví dụ có ba người

```text
           job0 job1 job2
person0:     9    2    7
person1:     6    4    3
person2:     5    8    1
```

Một cách tối ưu:

```text
person0 -> job1, cost 2
person1 -> job0, cost 6
person2 -> job2, cost 1

Tổng = 2 + 6 + 1 = 9
```

Các mask đi qua:

```text
000 (0): chưa giao ai; dp=0
010 (2): giao người 0 cho job1; dp=2
011 (3): giao người 1 cho job0; dp=8
111 (7): giao người 2 cho job2; dp=9
```

Trong bài này, lưu thêm `parentMask[next]` và `parentJob[next]` khi một chuyển tiếp **cải thiện** `dp[next]`. Từ mask đầy đủ, lần ngược các parent cho phép khôi phục công việc của từng người.

### Tính đúng và độ phức tạp

- Bất biến: `dp[mask]` là chi phí nhỏ nhất trong tất cả cách gán **`popcount(mask)` người đầu** vào đúng các job có bit 1. Đúng ở mask rỗng; thêm một job chưa dùng tạo đúng cách gán hợp lệ cho người tiếp theo.
- Mọi cách gán đầy đủ đều có thể được tạo bằng chuỗi thêm từng job theo thứ tự người. Vì mỗi bước giữ **min** của mọi nguồn có thể, nghiệm `dp[full]` là tối ưu.
- Có `2^n` mask. Mỗi mask xét tối đa `n` job, nên **`O(n2^n)` thời gian**; mảng `dp` và parent chiếm **`O(2^n)` bộ nhớ** (cộng ma trận cost `O(n²)` được cho sẵn).
- Khi `n=0`, có đúng một cách gán rỗng với chi phí `0`. Với các chi phí không âm, không có trạng thái bất khả thi vì ma trận vuông đầy đủ và mọi job được phép gán.

Mô hình này đặc biệt phù hợp khi `n` nhỏ (ví dụ không vượt quá khoảng 20 tùy RAM/thời gian). Với `n` lớn, thuật toán phân công có các phương pháp chuyên biệt như **Hungarian algorithm** chạy trong thời gian đa thức; không nên dùng `2^n` chỉ vì bitmask dễ hiểu.

## 6. Vì sao đường đi Hamilton cần `dp[mask][last]`?

Một **đường Hamilton (Hamiltonian path)** đi qua mỗi đỉnh của đồ thị **đúng một lần**; thứ tự đỉnh có ý nghĩa vì cạnh nối phụ thuộc vào **đỉnh cuối hiện tại**.

Xét hai đường đã đi qua cùng tập `{0,1,2}`:

```text
0 -> 1 -> 2      kết thúc ở 2
2 -> 1 -> 0      kết thúc ở 0
```

Cả hai có cùng mask `111₂`, nhưng **các cạnh có thể đi tiếp** và chi phí nối đến đỉnh mới phụ thuộc `last`. Nếu gộp vào một `dp[mask]` duy nhất, ta có thể giữ đường rẻ hơn hiện tại nhưng kết thúc ở đỉnh bất lợi cho phần còn lại, và bỏ lỡ nghiệm tối ưu.

### State và công thức đúng

Với đồ thị có `n` đỉnh, cạnh `w[u][v]≥0` nếu tồn tại; trong ví dụ, `−1` là **không có cạnh**:

```text
dp[mask][last] =
   chi phí thấp nhất của một đường đi qua đúng các đỉnh mask,
   mỗi đỉnh một lần, và kết thúc ở đỉnh last thuộc mask.
```

Nếu **cho phép bắt đầu ở bất kỳ đỉnh nào**:

```text
dp[1<<v][v] = 0, với mọi v
```

Các ô khác là `INF`. Từ trạng thái đạt được `(mask,last)`, chọn `next` chưa thăm **và có cạnh** `last→next`:

```text
nextMask = mask | (1 << next)

dp[nextMask][next] =
    min(dp[nextMask][next],
        dp[mask][last] + w[last][next])
```

Đáp án đường Hamilton ngắn nhất là:

```text
min(dp[full][last]), với mọi last
```

Nếu tất cả đều `INF` thì **không tồn tại đường Hamilton** theo hướng cạnh được phép; API mẫu trả `−1` và thứ tự rỗng. Đường Hamilton khác với **chu trình Hamilton**: chu trình còn phải có cạnh **quay về đỉnh xuất phát**, và bài toán người du lịch (**TSP tour**) thường cố định điểm xuất phát để tránh đếm lặp các phép quay vòng.

### Chi phí và phát biểu đúng

- Có nhiều nhất `n·2^n` cặp `(mask,last)`, trong đó các cặp `last∉mask` là không hợp lệ.
- Mỗi cặp có thể xét tối đa `n` ứng viên `next`.
- Thời gian **`O(n²2^n)`**, bộ nhớ bảng và parent **`O(n2^n)`**.
- Đường đầu tiên gồm một đỉnh có chi phí 0; với `n=0`, ví dụ quy ước đường rỗng có chi phí 0.
- Nếu có cạnh âm nhưng đồ thị và số bước vẫn hữu hạn, công thức DP có thể cần phân tích lại sentinel/giới hạn số học; chương trình minh họa chủ động chỉ chấp nhận **chi phí không âm** hoặc `−1` báo thiếu cạnh.

### Minh họa trên 4 đỉnh

Giả sử đồ thị vô hướng (lưu dưới dạng hai cạnh có hướng bằng trọng số) có:

```text
      0   1   2   3
0:   -1   3   8   7
1:    3  -1   2   6
2:    8   2  -1   1
3:    7   6   1  -1
```

Đường `3→2→1→0` có chi phí `1+2+3=6`; đường ngược `0→1→2→3` cũng có chi phí `6`. Nếu bộ quy tắc phá hòa chọn **đỉnh kết thúc nhỏ nhất**, một cách giải có thể trả `[3,2,1,0]`. Không được mặc định mọi đồ thị vô hướng đều có đường Hamilton hoặc đường Hamilton bằng TSP tour.

## 7. Duyệt mọi submask và tổng trên mọi tập con (SOS DP)

Một bài khác thường gặp là: đã cho giá trị `f[mask]` cho **mỗi mask**, cần tính:

```text
F[mask] = sum(f[sub]) trên mọi sub ⊆ mask,
          bao gồm cả sub = 0 và sub = mask.
```

Nếu với mỗi `mask` ta duyệt mọi `sub` rồi cộng trực tiếp, tổng số cặp có thể tới `3^n`. Khi yêu cầu **tính tất cả `F[mask]`**, có thể dùng **sum over subsets DP (SOS DP)** theo từng bit trong **`O(n2^n)`**:

```text
F = bản sao của f

for bit = 0 .. n-1:
    for mask = 0 .. 2^n-1:
        if mask có bit:
            F[mask] += F[mask ^ (1<<bit)]
```

### Giải thích vì sao công thức SOS đúng

Sau khi xử lý một nhóm các bit đầu, `F[mask]` chứa tổng `f[sub]` của những `sub` có thể có hoặc bỏ **các bit đã xử lý**, nhưng bắt buộc giữ nguyên những bit chưa xử lý đang hiện diện trong `mask`.

Khi xử lý bit `b` có trong mask, tách các submask theo hai nhóm **rời nhau**:

- Có chứa bit `b`: đang nằm ở `F[mask]`.
- Không chứa bit `b`: lấy từ `F[mask ^ (1<<b)]`.

Cộng hai nhóm đúng một lần. Sau khi xử lý đủ `n` bit, mọi bit đang bật trong mask đều có thể được giữ hoặc bỏ, nên `F[mask]` là tổng trên **toàn bộ các submask**.

### Ví dụ

Với `n=3`, lấy `f[mask]=Integer.bitCount(mask)`:

```text
f[0..7] = [0,1,1,2,1,2,2,3]

F[5] = f[0]+f[1]+f[4]+f[5]
     = 0+1+1+2 = 4

F[7] = tổng f[0..7] = 12
```

SOS DP tổng quát hóa nhiều công thức kết hợp các tập con. Tùy phép toán, có các biến thể đếm trên **supermask**, dùng min/max hay phép kết hợp khác. Không tự thay phép cộng bằng mọi toán tử mà chưa chứng minh thuộc tính và bất biến của phép đó.

**Độ phức tạp:** `O(n2^n)` phép cộng và `O(2^n)` vị trí lưu. Với `long`, phải đảm bảo tổng không tràn nếu bài cần chính xác; chương trình mẫu chỉ kiểm thử các giá trị nhỏ.

## 8. Các lựa chọn biểu diễn state khác và ranh giới thực tế

| Tình huống | Cách thường hợp lý | Nhận xét |
| --- | --- | --- |
| `n≤20`, cần xét nhiều tập con | `int mask` + `long[]/int[] dp` | `2^20=1.048.576` trạng thái; vẫn phải dự toán RAM |
| `n≈25..30`, chỉ vài trạng thái reachable | `int mask` + `HashMap<Integer,...>` | Tránh cấp phát mọi mask, nhưng **không** làm số trạng thái tiềm năng nhỏ đi |
| `n≤62`, chỉ cần biểu diễn một tập | `long mask` không âm | Dùng `1L<<i`; không thể cấp phát `dp[1L<<n]` một cách máy móc |
| `n` rất lớn, ít bit bật | `BitSet` hoặc tập hợp thưa | Thao tác tập có thể hiệu quả, nhưng DP trên mọi tập con vẫn thường bất khả thi |
| Bài có thêm `last`, `capacity`, `turn` | `dp[mask][last]` hoặc trạng thái tổ hợp | Không được bỏ thông tin làm thay đổi tương lai |
| Bài phân công `n` lớn | Thuật toán đa thức chuyên biệt | Bitmask DP tăng theo `2^n`, không phù hợp mọi kích thước |
| Bài đường đi gần Hamilton trên `n` lớn | Ràng buộc/thủ thuật cắt nhánh, meet-in-the-middle, thuật toán đặc thù | Cần đánh giá đúng đắn và giới hạn riêng |

Để hình dung sự tăng trưởng:

| `n` | Số mask `2^n` |
| ---: | ---: |
| 10 | 1.024 |
| 15 | 32.768 |
| 20 | 1.048.576 |
| 25 | 33.554.432 |
| 30 | 1.073.741.824 |

Số mask tăng gấp đôi với mỗi đối tượng mới. Nếu `dp[mask][last]` còn lưu `n` giá trị cho mỗi mask, số ô bậc `n·2^n`, chưa kể parent hoặc phần overhead của mảng Java. Vì vậy việc “mask nằm vừa trong `int`” **không có nghĩa DP sẽ nằm vừa trong bộ nhớ**.

### Top-down memoization hay bottom-up?

Có thể viết top-down:

```text
solve(mask, last):
    nếu trạng thái đã có trong memo: trả kết quả
    nếu đạt điều kiện kết thúc: trả base
    đáp án = kết hợp từ các lựa chọn bit chưa dùng
    lưu đáp án theo (mask,last)
    trả kết quả
```

Ưu điểm: chỉ mở những trạng thái reachable và diễn đạt trực tiếp ý tưởng đệ quy. Nhược điểm: cần cache, xử lý trạng thái không thể đạt, có stack đệ quy và có thể tràn stack khi độ sâu lớn. Bottom-up phù hợp khi các trạng thái tăng theo `popcount(mask)` hoặc phép thêm bit, và có đủ RAM cho bảng.

**Một mask có thể đại diện cho state đã chọn hoặc state còn lại.** Cả hai đúng nếu định nghĩa nhất quán; sai lầm là lập công thức trên “đã chọn” rồi khi cài đặt lại hiểu mask như “chưa chọn”, dẫn đến đảo điều kiện bit.

## 9. Chương trình Java 17+ đầy đủ

Ví dụ **BitmaskStateDemo.java** bao gồm:

1. Các phép tập hợp bit cơ bản: thêm, xóa, kiểm tra, duyệt các phần tử và submask.
2. **Minimum assignment** bằng `dp[mask]`, trả chi phí tối ưu và mảng `jobForPerson` truy vết.
3. **Minimum Hamiltonian path** bằng `dp[mask][last]`, cho phép bắt đầu ở bất kỳ đỉnh nào, dùng `−1` cho cạnh không tồn tại, trả một đường đi tối ưu.
4. **SOS DP**: tính tổng của `f[sub]` trên các submask của từng mask.
5. **Kiểm thử đối chiếu độc lập**: nghiệm phân công với liệt kê hoán vị, đường Hamilton với liệt kê hoán vị đỉnh, SOS với duyệt submask thô, và tính chất vòng lặp submask.

Các hàm có giới hạn số đỉnh **cố ý** để tránh cấp phát `2^n` quá lớn trong ví dụ; `n=0` được hỗ trợ với quy ước nghiệm rỗng có chi phí 0.

### Mã nguồn hoàn chỉnh

```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Random;

public class BitmaskStateDemo {
    private static final long INF = Long.MAX_VALUE / 4;

    record Assignment(long cost, int[] jobForPerson) {}
    record Path(long cost, int[] order) {}
    record Verification(int assignments, int paths,
                        int sosMasks, int submaskMasks) {}

    static void checkN(int n, int maximum) {
        if (n < 0 || n > maximum) {
            throw new IllegalArgumentException(
                "n outside allowed state budget");
        }
    }

    static int add(int mask, int i) {
        return mask | (1 << i);
    }

    static int remove(int mask, int i) {
        return mask & ~(1 << i);
    }

    static boolean contains(int mask, int i) {
        return (mask & (1 << i)) != 0;
    }

    static int[] members(int mask) {
        int[] result = new int[Integer.bitCount(mask)];
        int k = 0;
        for (int remaining = mask; remaining != 0;
                remaining &= remaining - 1) {
            result[k++] =
                Integer.numberOfTrailingZeros(remaining);
        }
        return result;
    }

    static int[] nonEmptySubmasksDescending(int mask) {
        int count = (1 << Integer.bitCount(mask)) - 1;
        int[] result = new int[count];
        int index = 0;
        for (int sub = mask; sub != 0;
                sub = (sub - 1) & mask) {
            result[index++] = sub;
        }
        return result;
    }

    // cost[person][job] >= 0; n<=20 để giới hạn 2^n trạng thái.
    static Assignment minAssignment(int[][] cost) {
        if (cost == null) {
            throw new IllegalArgumentException("null cost");
        }
        int n = cost.length;
        checkN(n, 20);
        for (int[] row : cost) {
            if (row == null || row.length != n) {
                throw new IllegalArgumentException("not square");
            }
            for (int value : row) {
                if (value < 0) {
                    throw new IllegalArgumentException("negative cost");
                }
            }
        }

        int states = 1 << n;
        int full = states - 1;
        long[] dp = new long[states];
        int[] previousMask = new int[states];
        int[] chosenJob = new int[states];
        Arrays.fill(dp, INF);
        Arrays.fill(chosenJob, -1);
        dp[0] = 0L;

        for (int mask = 0; mask < states; mask++) {
            int person = Integer.bitCount(mask);
            if (person == n || dp[mask] == INF) {
                continue;
            }

            int available = full & ~mask;
            for (int rest = available; rest != 0;
                    rest &= rest - 1) {
                int job = Integer.numberOfTrailingZeros(rest);
                int next = mask | (1 << job);
                long candidate = dp[mask] + cost[person][job];

                if (candidate < dp[next]) {
                    dp[next] = candidate;
                    previousMask[next] = mask;
                    chosenJob[next] = job;
                }
            }
        }

        int[] jobForPerson = new int[n];
        int current = full;
        for (int person = n - 1; person >= 0; person--) {
            jobForPerson[person] = chosenJob[current];
            current = previousMask[current];
        }
        return new Assignment(dp[full], jobForPerson);
    }

    // Đường Hamilton ngắn nhất; mọi đỉnh có thể là điểm đầu.
    // -1 nghĩa là không có cạnh; trọng số còn lại >=0.
    static Path minHamiltonianPath(int[][] edge) {
        if (edge == null) {
            throw new IllegalArgumentException("null graph");
        }
        int n = edge.length;
        checkN(n, 15);
        for (int[] row : edge) {
            if (row == null || row.length != n) {
                throw new IllegalArgumentException("not square");
            }
            for (int weight : row) {
                if (weight < -1) {
                    throw new IllegalArgumentException("bad weight");
                }
            }
        }
        if (n == 0) {
            return new Path(0L, new int[0]);
        }

        int states = 1 << n;
        int full = states - 1;
        long[][] dp = new long[states][n];
        int[][] parent = new int[states][n];
        for (int mask = 0; mask < states; mask++) {
            Arrays.fill(dp[mask], INF);
            Arrays.fill(parent[mask], -1);
        }
        for (int v = 0; v < n; v++) {
            dp[1 << v][v] = 0L;
        }

        for (int mask = 1; mask < states; mask++) {
            for (int ending = 0; ending < n; ending++) {
                if (!contains(mask, ending)
                        || dp[mask][ending] == INF) {
                    continue;
                }
                int available = full & ~mask;
                for (int rest = available; rest != 0;
                        rest &= rest - 1) {
                    int next = Integer.numberOfTrailingZeros(rest);
                    int w = edge[ending][next];
                    if (w == -1) {
                        continue;
                    }
                    int nextMask = mask | (1 << next);
                    long candidate = dp[mask][ending] + w;
                    if (candidate < dp[nextMask][next]) {
                        dp[nextMask][next] = candidate;
                        parent[nextMask][next] = ending;
                    }
                }
            }
        }

        long best = INF;
        int end = -1;
        for (int v = 0; v < n; v++) {
            if (dp[full][v] < best) {
                best = dp[full][v];
                end = v;
            }
        }
        if (end == -1) {
            return new Path(-1L, new int[0]);
        }

        int[] order = new int[n];
        int mask = full;
        int v = end;
        for (int i = n - 1; i >= 0; i--) {
            order[i] = v;
            int before = parent[mask][v];
            mask ^= 1 << v;
            v = before;
        }
        return new Path(best, order);
    }

    // F[mask] = tổng base[sub] với mọi sub ⊆ mask.
    static long[] subsetSumsSOS(long[] base, int n) {
        checkN(n, 20);
        if (base == null || base.length != (1 << n)) {
            throw new IllegalArgumentException("wrong base length");
        }
        long[] result = base.clone();
        for (int bit = 0; bit < n; bit++) {
            for (int mask = 0; mask < result.length; mask++) {
                if ((mask & (1 << bit)) != 0) {
                    result[mask] +=
                        result[mask ^ (1 << bit)];
                }
            }
        }
        return result;
    }

    // Oracle phân công: liệt kê các hoán vị công việc.
    static long bruteAssignment(int[][] cost,
                                int person, int used) {
        if (person == cost.length) {
            return 0L;
        }
        long best = INF;
        for (int job = 0; job < cost.length; job++) {
            if ((used & (1 << job)) == 0) {
                long candidate = cost[person][job]
                        + bruteAssignment(
                            cost, person + 1, used | (1 << job));
                best = Math.min(best, candidate);
            }
        }
        return best;
    }

    // Oracle đường Hamilton: xét mọi hoán vị đỉnh.
    static long brutePath(int[][] edge, int[] permutation,
                          int depth, int used, long running) {
        if (depth == edge.length) {
            return running;
        }
        long best = INF;
        for (int v = 0; v < edge.length; v++) {
            if ((used & (1 << v)) != 0) {
                continue;
            }
            if (depth > 0 && edge[permutation[depth - 1]][v] == -1) {
                continue;
            }
            permutation[depth] = v;
            long extra = depth == 0
                    ? 0L : edge[permutation[depth - 1]][v];
            best = Math.min(
                best, brutePath(
                    edge, permutation, depth + 1,
                    used | (1 << v), running + extra));
        }
        return best;
    }

    static boolean validAssignment(int[][] cost, Assignment a) {
        int n = cost.length;
        if (a.jobForPerson().length != n) {
            return false;
        }
        int used = 0;
        long total = 0L;
        for (int i = 0; i < n; i++) {
            int job = a.jobForPerson()[i];
            if (job < 0 || job >= n || contains(used, job)) {
                return false;
            }
            used = add(used, job);
            total += cost[i][job];
        }
        return used == (1 << n) - 1 && total == a.cost();
    }

    static boolean validPath(int[][] edge, Path path) {
        int n = edge.length;
        if (path.cost() == -1L) {
            return path.order().length == 0;
        }
        if (path.order().length != n) {
            return false;
        }
        int seen = 0;
        long total = 0;
        for (int i = 0; i < n; i++) {
            int v = path.order()[i];
            if (v < 0 || v >= n || contains(seen, v)) {
                return false;
            }
            seen = add(seen, v);
            if (i > 0) {
                int w = edge[path.order()[i - 1]][v];
                if (w == -1) {
                    return false;
                }
                total += w;
            }
        }
        return seen == (1 << n) - 1 && total == path.cost();
    }

    static Verification verifySmallCases() {
        Random random = new Random(2026L);
        int assignments = 0;
        int paths = 0;
        int sosMasks = 0;
        int submaskMasks = 0;

        // 6 độ dài 0..5 x 50 ma trận = 300 ca.
        for (int n = 0; n <= 5; n++) {
            for (int trial = 0; trial < 50; trial++) {
                int[][] cost = new int[n][n];
                for (int i = 0; i < n; i++) {
                    for (int j = 0; j < n; j++) {
                        cost[i][j] = random.nextInt(10);
                    }
                }
                Assignment actual = minAssignment(cost);
                long expected = bruteAssignment(cost, 0, 0);
                if (actual.cost() != expected
                        || !validAssignment(cost, actual)) {
                    throw new AssertionError("assignment");
                }
                assignments++;
            }
        }

        // 6 độ dài 0..5 x 25 đồ thị có hướng = 150 ca.
        for (int n = 0; n <= 5; n++) {
            for (int trial = 0; trial < 25; trial++) {
                int[][] edge = new int[n][n];
                for (int i = 0; i < n; i++) {
                    for (int j = 0; j < n; j++) {
                        edge[i][j] = i == j || random.nextInt(5) == 0
                                ? -1 : random.nextInt(9);
                    }
                }
                Path actual = minHamiltonianPath(edge);
                long brute = brutePath(edge, new int[n], 0, 0, 0L);
                long expected = brute == INF ? -1L : brute;
                if (actual.cost() != expected
                        || !validPath(edge, actual)) {
                    throw new AssertionError("Hamilton path");
                }
                paths++;
            }
        }

        // Mọi mask ở các kích thước n=0..5: 63 mask SOS.
        for (int n = 0; n <= 5; n++) {
            int states = 1 << n;
            long[] base = new long[states];
            for (int mask = 0; mask < states; mask++) {
                base[mask] = (mask * 7 + n) % 9 - 4;
            }
            long[] result = subsetSumsSOS(base, n);
            for (int mask = 0; mask < states; mask++) {
                long expected = base[0];
                for (int sub = mask; sub != 0;
                        sub = (sub - 1) & mask) {
                    expected += base[sub];
                }
                if (result[mask] != expected) {
                    throw new AssertionError("SOS");
                }
                sosMasks++;
            }
        }

        // Mọi mask của n=0..6: 127 mask.
        for (int n = 0; n <= 6; n++) {
            for (int mask = 0; mask < (1 << n); mask++) {
                int[] subs = nonEmptySubmasksDescending(mask);
                int count = (1 << Integer.bitCount(mask)) - 1;
                if (subs.length != count) {
                    throw new AssertionError("submask count");
                }
                int prior = Integer.MAX_VALUE;
                for (int sub : subs) {
                    if (sub == 0 || sub >= prior
                            || (sub & mask) != sub) {
                        throw new AssertionError("bad submask");
                    }
                    prior = sub;
                }
                submaskMasks++;
            }
        }
        return new Verification(
            assignments, paths, sosMasks, submaskMasks);
    }

    public static void main(String[] args) {
        int mask = 0;
        mask = add(mask, 0);
        mask = add(mask, 2);
        mask = add(mask, 3);
        int full = (1 << 4) - 1;
        System.out.println("Mask: " + mask
                           + " | members=" + Arrays.toString(members(mask))
                           + " | count=" + Integer.bitCount(mask));
        System.out.println("Contains 2: " + contains(mask, 2));
        System.out.println("Remove 2: " + remove(mask, 2));
        System.out.println("Available: " + (full & ~mask));
        System.out.println("Submasks: "
                           + Arrays.toString(
                               nonEmptySubmasksDescending(mask)));

        int[][] costs = {
            {9, 2, 7},
            {6, 4, 3},
            {5, 8, 1}
        };
        Assignment assignment = minAssignment(costs);
        System.out.println("Assignment: cost=" + assignment.cost()
                           + " jobs=" + Arrays.toString(
                               assignment.jobForPerson()));

        int[][] edges = {
            {-1, 3, 8, 7},
            {3, -1, 2, 6},
            {8, 2, -1, 1},
            {7, 6, 1, -1}
        };
        Path path = minHamiltonianPath(edges);
        System.out.println("Hamilton path: cost=" + path.cost()
                           + " order=" + Arrays.toString(path.order()));

        long[] values = new long[8];
        for (int s = 0; s < values.length; s++) {
            values[s] = Integer.bitCount(s);
        }
        long[] sos = subsetSumsSOS(values, 3);
        System.out.println("SOS(mask=5): " + sos[5]);
        System.out.println("SOS(mask=7): " + sos[7]);

        Path unreachable = minHamiltonianPath(
            new int[][]{
                {-1, -1, -1},
                {-1, -1, -1},
                {-1, -1, -1}
            });
        System.out.println("No Hamilton path: " + unreachable.cost());
        System.out.println("Empty assignment: "
                           + minAssignment(new int[0][0]).cost());

        Verification checked = verifySmallCases();
        System.out.println(
            "Verified: " + checked.assignments() + " assignments, "
            + checked.paths() + " paths, "
            + checked.sosMasks() + " SOS masks, "
            + checked.submaskMasks() + " submask masks");
    }
}
```

Biên dịch/chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 BitmaskStateDemo.java
java BitmaskStateDemo
```

Stdout dự kiến:

```text
Mask: 13 | members=[0, 2, 3] | count=3
Contains 2: true
Remove 2: 9
Available: 2
Submasks: [13, 12, 9, 8, 5, 4, 1]
Assignment: cost=9 jobs=[1, 0, 2]
Hamilton path: cost=6 order=[3, 2, 1, 0]
SOS(mask=5): 4
SOS(mask=7): 12
No Hamilton path: -1
Empty assignment: 0
Verified: 300 assignments, 150 paths, 63 SOS masks, 127 submask masks
```

### Giải thích kết quả và kiểm thử

- Mask `13` biểu diễn tập `{0,2,3}`. Khi xóa phần tử `2` còn mask `9`, và phần còn thiếu trong miền 4 phần tử là mask `2`, tức `{1}`.
- Vòng submask của mask `13` tạo đúng **7 tập con không rỗng**, theo thứ tự số nguyên giảm, và không lặp.
- Phân công ba người chọn các job `[1,0,2]`, tổng `2+6+1=9`. Mảng `jobForPerson` sắp theo **chỉ số người**, không phải theo thứ tự trị giá của job.
- Đường Hamilton `[3,2,1,0]` thăm mỗi đỉnh đúng một lần, có tổng chi phí `1+2+3=6`. Nếu nhiều đường đạt cùng chi phí, quy tắc cập nhật chỉ khi **nhỏ hơn nghiêm ngặt** cùng thứ tự duyệt xác định **một** nghiệm hợp lệ; không khẳng định mọi thuật toán sẽ trả cùng thứ tự.
- `SOS(mask=5)` cộng giá trị cho các submask `0,1,4,5`; `SOS(mask=7)` cộng cả 8 submask. Đáp án `4` và `12` kiểm tra công thức tổng trên tập.
- Đồ thị không có cạnh giữa các đỉnh (với `n=3`) không có đường Hamilton, nên API trả chi phí `−1`; bài toán n=0 có nghiệm phân công rỗng giá 0.
- Bộ kiểm thử tạo **300 ma trận chi phí** của kích thước `0..5`, đối chiếu nghiệm DP với **duyệt toàn bộ hoán vị công việc**; **150 đồ thị có hướng** kích thước `0..5`, so với duyệt hoán vị đỉnh; **63 mask SOS** so với cộng mọi submask trực tiếp; **127 mask** để kiểm số lượng, tính thuộc tập và thứ tự duyệt submask. Mã còn kiểm chứng rằng bản truy vết assignment/path thực sự có tổng chi phí được báo.
- Các kiểm thử trên miền nhỏ là **thực nghiệm xác nhận**, không thay thế chứng minh quy hoạch động bằng bất biến và quan hệ phụ thuộc ở phần trước. Trong chương trình thật cần kiểm tra thêm giới hạn RAM và độ lớn số học trên kích thước tối đa.

### Chi tiết kỹ thuật đáng chú ý

**Không sửa dữ liệu caller:** `minAssignment` chỉ đọc `cost[][]` và `minHamiltonianPath` chỉ đọc `edge[][]`. Các mảng `dp`, `parent` và kết quả truy vết được cấp phát mới. `subsetSumsSOS` dùng `base.clone()` nên không biến đổi giá trị đầu vào.

**Độ an toàn số học:** Chi phí input là `int` không âm, cộng trong `long` và `INF=Long.MAX_VALUE/4`. Với giới hạn `n≤20` hoặc `15`, tổng của tối đa `n` số `int` không âm không vượt `INF`. Dùng `dp==INF` để bỏ qua trạng thái không đạt, tránh cộng thêm chi phí vào sentinel.

**Cấu trúc mảng:** Mỗi ô `long[][]` và `int[][]` trong Java còn có overhead cấp phát mảng con. Việc lưu cả bảng và parent của Hamilton `n=15` cần RAM đáng kể, nhưng hợp lý hơn rất nhiều so với cố tính `n=30`. Ngưỡng `n≤20` và `n≤15` là **guard của ví dụ**, không phải giới hạn tuyệt đối của thuật toán.

**Bit count và thứ tự mask:** Hàm phân công lấy `person=Integer.bitCount(mask)` để xác định người kế tiếp; các trạng thái chỉ chuyển bằng **thêm một bit**. Vì vậy duyệt mask tăng dần bảo đảm các trạng thái nguồn đã được xét trước, dù không được sắp theo số bit.

**Tổng SOS có thể âm:** Chương trình kiểm thử sử dụng cả giá trị `base[mask]` âm, chứng tỏ công thức SOS ở đây là tổng đại số, không chỉ đếm số phần tử. Bản chương trình vẫn cần `long` đủ lớn để tổng không tràn nếu dùng dữ liệu thật.

## 10. Tính đúng và phân tích chi phí theo từng lớp

Một cách tự đánh giá bài toán bitmask DP:

| Kỹ thuật | Số trạng thái | Số chuyển tiếp/công việc | Bộ nhớ |
| --- | ---: | ---: | ---: |
| Đọc/thêm/bỏ một bit | 1 | `O(1)` | `O(1)` |
| Duyệt toàn bộ `n` bit của một mask | 1 | `O(n)` | `O(1)` |
| Duyệt bit 1 của mask | 1 | `O(popcount(mask))` | `O(1)` |
| Liệt kê mọi submask của một mask có `k` bit 1 | `2^k` | `O(2^k)` | `O(1)` phụ nếu xử lý trực tiếp từng submask |
| Duyệt mọi cặp (mask, submask) | `2^n` mask | `Θ(3^n)` cặp nếu gồm sub rỗng | `O(1)` phụ cho vòng lặp, không tính dữ liệu kết quả |
| Minimum assignment DP | `2^n` mask | `O(n2^n)` | `O(2^n)` cho dp + parent |
| Hamiltonian path DP | `O(n2^n)` | `O(n²2^n)` | `O(n2^n)` |
| SOS subset sums | `2^n` | `O(n2^n)` | `O(2^n)` |

### Cách tính tổng số chuyển tiếp “thêm một bit”

Với mỗi phần tử `i`, có `2^(n−1)` mask **không chứa `i`**. Khi thêm `i` từ các mask đó, có đúng:

```text
n * 2^(n-1)
```

cạnh chuyển tiếp trong **toàn bộ đồ thị tập con** khi chỉ xét phép thêm đúng một bit. Đây là `Θ(n2^n)`, không phải `Θ(n²2^n)`. Bài Hamilton thêm một biến `last`, làm số cặp phải xét lớn hơn một cấp `n`, nên thời gian bậc `O(n²2^n)`.

### Vì sao thuật toán dừng?

Khi chuyển trạng thái bằng cách thêm đúng một bit chưa bật, `popcount(mask)` tăng **nghiêm ngặt**. Không thể thêm quá `n` bit, do đó không có vòng phụ thuộc. Base case là mask rỗng (assignment) hoặc các mask chỉ gồm một bit (Hamilton). Mọi trạng thái có thể nhận giá trị chỉ từ các trạng thái nhỏ hơn theo số bit.

SOS DP không “thêm đối tượng được chọn” theo cùng nghĩa; nó có **vòng ngoài theo vị trí bit**, mỗi bước tổng hợp hai lớp submask rời nhau. Bất biến đúng nằm ở **những bit đã xử lý**, không phải số đối tượng được chọn.

## 11. Các lỗi phổ biến và cách tránh

**1. Nhầm bit thứ `i` với `2*i` hoặc `i`.** Muốn bật bit thứ `i` phải dùng `1<<i`, không phải `mask|i` hay `mask+(i)`. Khi thêm phần tử vào set, dùng OR; phép cộng chỉ tương đương khi đã chắc bit chưa bật.

**2. Dùng `1<<n` với n lớn mà không kiểm tra.** `int` shift theo modulo 32; `1<<31` âm và `1<<32` quay về 1. Dùng ràng buộc và kiểm tra bộ nhớ trước khi cấp phát DP.

**3. Dùng `^` để xóa phần tử không chắc có.** XOR đảo bit, có thể vô tình **thêm** phần tử chưa có. Xóa bằng `mask & ~(1<<i)`.

**4. Quên giới hạn full mask khi lấy phần bù.** `~mask` đảo **mọi bit của int**, kể cả các bit ngoài miền `n`. Dùng `full & ~mask`.

**5. Duyệt submask khi mask=0 sai cách.** Vòng `sub=(sub−1)&mask` phải có điều kiện kết thúc và xử lý `0` riêng nếu cần; tránh vòng vô hạn.

**6. Gọi `Integer.numberOfTrailingZeros(0)` rồi dùng làm chỉ số.** Trên `int`, hàm trả `32` cho 0; đó không phải chỉ số phần tử hợp lệ trong mask. Chỉ dùng trong vòng đảm bảo `rest!=0`.

**7. Dùng mỗi `dp[mask]` cho bài còn phụ thuộc đỉnh cuối.** Tập đã thăm không mô tả đủ hướng đi tiếp trong Hamilton; cần `dp[mask][last]`.

**8. Khởi tạo mọi DP bằng 0 cho bài tìm min.** Giá trị 0 là chi phí có nghĩa; trạng thái chưa đạt phải là `INF` hoặc có cờ reachable.

**9. Duyệt theo thứ tự không tôn trọng phụ thuộc.** Khi thêm bit, mask tăng; khi bớt bit, hướng duyệt phải phù hợp. Không đọc trạng thái chưa được tính xong.

**10. Sai kích thước state.** Với `n` đối tượng có `2^n` mask, chỉ số từ `0..2^n−1`. Không cấp phát `new long[n]` rồi truy cập bằng mask.

**11. Nhầm Hamilton path với Hamilton cycle/TSP tour.** Đường đi không cần quay về điểm đầu; TSP tour cần khép vòng và thường cố định start. Kết quả và công thức khác nhau.

**12. Quên đồ thị có hướng hoặc thiếu cạnh.** Với ma trận `w[u][v]`, không tự suy ra `w[v][u]` bằng nhau nếu đề là đồ thị có hướng. Sentinel `−1` phải được kiểm tra trước khi cộng.

**13. Sai khi truy vết.** Parent phải được lưu khi `dp[next]` cải thiện. Nếu chỉ lưu chi phí mà không lưu đường đi, không thể dựng lại bằng cách đọc giá trị trả về một cách tùy ý.

**14. Bỏ qua tràn `long` trong tổng SOS hoặc điểm tối ưu.** `long` rộng hơn `int` nhưng không vô hạn. Cần ràng buộc input hoặc `BigInteger` tùy đặc tả.

**15. Khẳng định bitmask DP là “nhanh” cho n=30 vì mask vừa int.** `2^30` trạng thái quá lớn cho đa số ứng dụng. Tối ưu kiểu dữ liệu không đổi bản chất tăng trưởng hàm mũ.

**16. Quên phân biệt “tập” và “dãy chọn”.** Mask `{0,2,3}` không lưu thứ tự `0→2→3`; nếu thứ tự ảnh hưởng tương lai hoặc kết quả, cần bổ sung biến hoặc parent.

**17. Tưởng duyệt submask lồng nhau chỉ `O(n2^n)`.** Trường hợp tổng quát duyệt mọi cặp mask/submask có `3^n` cặp; dùng SOS DP hoặc công thức khác khi phù hợp.

## 12. Bài tập thực hành

**Bài 1 — Đọc và thao tác mask.** Với `n=5`, mã hóa `S={0,2,4}` thành số nguyên và chuỗi bit. Thêm phần tử 1, xóa phần tử 2, tìm phần tử còn thiếu trong tập đầy đủ. Tại sao `mask^bit(2)` không phải phép xóa an toàn?

**Bài 2 — Liệt kê tập con.** Với `mask=13`, viết lần lượt tất cả submask khác 0 được tạo bởi `(sub−1)&mask`. Vì sao có đúng 7 giá trị? Nếu cần cả tập rỗng, bổ sung nó ở đâu?

**Bài 3 — Số cặp mask/submask.** Chứng minh bằng ba lựa chọn trên mỗi phần tử rằng số cặp `sub⊆mask⊆U` bằng `3^n`. Số cặp khi cấm sub rỗng là bao nhiêu?

**Bài 4 — Phân công.** Cho ba người và chi phí `[[9,2,7],[6,4,3],[5,8,1]]`. Liệt kê sáu hoán vị job và tổng chi phí của từng cái; đối chiếu với `dp[mask]` và một nghiệm tối ưu `[1,0,2]` giá 9.

**Bài 5 — Thiết kế state.** Hai đường cùng ghé `{0,1,2}` nhưng kết thúc ở 0 và 2. Vì sao `dp[mask]` không đủ để tìm đường Hamilton ngắn nhất? Viết một chuyển tiếp đúng bằng `dp[mask][last]`.

**Bài 6 — Đồ thị không có đường Hamilton.** Với ba đỉnh và chỉ một cạnh `0→1`, tính kết quả min Hamiltonian path. Vì sao trả `−1` khác với đường đi có chi phí 0?

**Bài 7 — SOS DP.** Đặt `n=3`, `f[mask]=popcount(mask)`. Viết `F[mask]` cho mọi mask theo cách duyệt submask thô và theo ba lượt xử lý bit. Kiểm chứng `F[5]=4`, `F[7]=12`.

**Bài 8 — Chênh lệch độ phức tạp.** So sánh `n2^n` với `n²2^n` và `3^n` cho `n=10,15,20`. Vì sao không thể chỉ nhìn số trạng thái mà bỏ qua số cạnh chuyển tiếp?

**Bài 9 — Giới hạn Java.** Thử dự đoán kết quả `1<<31`, `1<<32`, `1L<<31` và `1L<<64`. Vì sao phải phân biệt `int` với `long`? Khi nào `BitSet` giúp biểu diễn tập nhưng không cứu được việc lưu `2^n` ô DP?

**Bài 10 — Thay đổi mục tiêu.** Chuyển assignment tìm min sang đếm số cách giao việc thỏa điều kiện cho phép của mỗi người. Viết `ways[0]=1` và chuyển tiếp cộng số cách cho job chưa dùng; khi nào hai đường gán có cùng mask được phép cộng?

**Bài 11 — TSP chu trình.** Từ DP Hamilton path, cố định điểm xuất phát `s` và thêm cạnh quay về `s` để tạo tour. Chỉ ra những thay đổi trong base case và cách tính đáp án; không nhầm chi phí tour với path.

**Bài 12 — Kiểm thử độc lập.** Sinh ma trận chi phí `n≤5` và đồ thị có hướng `n≤5`, so sánh bitmask DP với liệt kê mọi hoán vị. Với SOS, so sánh trên mọi mask với duyệt submask trực tiếp; kiểm tra cả tập rỗng.

## 13. Checklist trước khi dùng bitmask DP

1. **State là tập gì?** Bit 1 nghĩa là đã chọn, đã thăm hay đang còn? Mọi phép toán và base case dùng nhất quán không?
2. **Có cần nhớ thêm lịch sử?** Nếu đỉnh cuối/biến tài nguyên ảnh hưởng tương lai, `dp[mask]` có đủ không?
3. **Miền mask được giới hạn?** `n` là bao nhiêu; `1<<n` có an toàn và khả thi về RAM không?
4. **Phép toán bit đúng?** Có dùng AND/OR/XOR theo đúng ý nghĩa; phần bù có được chặn bằng `fullMask` không?
5. **Bất biến DP rõ?** Giá trị `dp[mask]` hoặc `dp[mask][last]` đại diện cho những lời giải nào?
6. **Chuyển tiếp chỉ tới trạng thái hợp lệ?** Chọn bit chưa bật, không lặp đối tượng, kiểm tra điều kiện cạnh và chi phí?
7. **Khởi tạo đúng?** Có base state, `INF` cho unreachable, quy ước với tập rỗng/đồ thị rỗng?
8. **Thứ tự tính tôn trọng phụ thuộc?** Thêm bit, bớt bit, hay SOS theo vòng bit; có chu trình phụ thuộc không?
9. **Độ phức tạp tính cả transitions?** `O(n2^n)`, `O(n²2^n)` hoặc `O(3^n)` tùy công thức thật?
10. **Đủ bộ nhớ và đúng kiểu số?** Bảng `long[]`, `long[][]`, parent, overhead Java, nguy cơ overflow?
11. **Có cần đường đi/nghiệm cụ thể?** Nếu có, lưu parent và kiểm tra truy vết với đầu vào gốc.
12. **Kiểm thử bằng oracle độc lập?** Assignment/Hamilton bằng hoán vị, SOS bằng duyệt submask thô, các trường hợp biên `n=0`, `n=1` và không có cạnh.

**Tiêu chí hoàn thành:** Bạn có thể chuyển qua lại giữa tập con và mặt nạ bit, dùng chính xác các phép toán cơ bản, duyệt tập con và bit chưa chọn, thiết kế `dp[mask]` hoặc `dp[mask][last]` theo thông tin thực sự ảnh hưởng đến tương lai, chứng minh các chuyển tiếp không thiếu/trùng, phân tích `2^n`/`n2^n`/`3^n` và xây một chương trình Java 17+ có kiểm thử độc lập phù hợp với ngân sách RAM.
