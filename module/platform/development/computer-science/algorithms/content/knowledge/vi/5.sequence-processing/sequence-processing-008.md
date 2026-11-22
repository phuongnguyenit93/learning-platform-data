# Cửa sổ trượt có độ dài thay đổi và điều kiện đơn điệu

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện khi nào có thể dùng **cửa sổ trượt độ dài thay đổi** (variable-size sliding window) để xử lý một đoạn liên tiếp trong dãy.
2. Phát biểu chính xác **điều kiện đơn điệu** giúp hai con trỏ chỉ di chuyển về phía trước mà vẫn tìm đủ đáp án.
3. Thiết kế và chứng minh ba mẫu bài: **đoạn dài nhất thỏa giới hạn**, **đoạn ngắn nhất đạt ngưỡng**, và **đếm số đoạn thỏa ràng buộc**.
4. Cài đặt Java 17+ có thể chạy được, sử dụng tổng cửa sổ và bảng tần suất.
5. Phân biệt **độ phức tạp $O(n)$ của toàn bộ quá trình** với số vòng lặp `while` bên trong; biết lúc nào dữ liệu âm hoặc điều kiện không đơn điệu làm kỹ thuật sai.

## 1. Cửa sổ trượt độ dài thay đổi là gì?

Cho dãy $a[0],a[1],\ldots,a[n-1]$. Một **cửa sổ** là đoạn liên tiếp $a[L..R]$, bao gồm cả hai đầu, có độ dài:

\[
\operatorname{length}(L,R)=R-L+1.
\]

Ta duy trì hai chỉ số:

- `R` (right): mở rộng cửa sổ bằng cách nhận thêm phần tử ở bên phải.
- `L` (left): thu hẹp cửa sổ bằng cách bỏ phần tử ở bên trái.

Với cửa sổ không rỗng, điều kiện chỉ số là $0\le L\le R<n$. Ta cũng có thể dùng **cửa sổ rỗng** khi $L=R+1$, độ dài bằng 0. Trạng thái phụ thường gồm `sum`, `frequency map`, số phần tử phân biệt hoặc thống kê cập nhật được khi thêm/bớt một phần tử.

Hình dung:

```text
Dãy:       2   1   3   2   4   1
Chỉ số:    0   1   2   3   4   5
                  L       R
Cửa sổ:          [3, 2, 4]
Mở rộng:                         R tăng sang phải
Thu hẹp:           L tăng sang phải, bỏ phần tử đầu cửa sổ
```

Ví dụ trên biểu diễn cửa sổ $L=2,R=4$, tổng $3+2+4=9$, độ dài $3$. Ta **không cần tính lại tổng từ đầu**: khi đưa $a[R+1]$ vào, cộng giá trị đó; khi bỏ $a[L]$, trừ giá trị đó. Nếu mỗi thao tác cập nhật mất $O(1)$, việc di chuyển hai con trỏ tối đa $n$ bước mỗi con trỏ sẽ dẫn đến tổng thời gian $O(n)$.

**Nhưng không phải mọi bài toán đoạn con đều dùng được cách này.** Điểm quyết định là tính chất đơn điệu của điều kiện trên cửa sổ và khả năng duy trì trạng thái đúng khi mở rộng/thu hẹp.

### Ba kiểu yêu cầu thường gặp

| Đầu ra cần tìm | Ví dụ | Khi điều kiện đơn điệu thích hợp |
| --- | --- | --- |
| **Dài nhất còn hợp lệ** | Đoạn dài nhất có tổng không quá ngân sách $B$ khi các phần tử không âm | Mở rộng bên phải; nếu vi phạm thì thu từ trái cho đến khi hợp lệ; cập nhật độ dài lớn nhất |
| **Ngắn nhất đạt ngưỡng** | Đoạn ngắn nhất có tổng ít nhất $S>0$ khi các phần tử không âm | Mở rộng cho đến khi đủ ngưỡng; khi hợp lệ thì ghi nhận và tiếp tục thu từ trái |
| **Đếm tất cả đoạn hợp lệ** | Số đoạn có không quá $K$ giá trị phân biệt | Với mỗi đầu phải $R$, nếu tập vị trí đầu hợp lệ tạo thành một đoạn liên tiếp, có thể cộng trực tiếp số vị trí đầu hợp lệ |

Một **đoạn con liên tiếp** (contiguous subarray/subsequence theo cách gọi trong ngữ cảnh này) không phải một tập con tùy ý. Ví dụ `[2,4]` lấy từ các vị trí không liền nhau trong `[2,1,4]` không phải cửa sổ liên tiếp.

## 2. “Điều kiện đơn điệu” có nghĩa chính xác là gì?

Gọi $P(L,R)$ là mệnh đề “cửa sổ $a[L..R]$ hợp lệ”. Với một đầu phải cố định $R$, điều ta cần là việc thay đổi $L$ theo **một chiều** làm tính hợp lệ chuyển trạng thái theo **một hướng có thể dự đoán**; đồng thời phần tử mới ở bên phải không làm các vị trí đầu từng bị loại trở nên cần thiết trở lại đối với bài toán đang giải.

Ví dụ, giả sử tất cả $a[i]\ge0$:

- Khi **tăng $R$**, tổng cửa sổ **không giảm**.
- Khi **tăng $L$** (bỏ phần tử trái), tổng cửa sổ **không tăng**.

Từ đó xuất hiện hai dạng đơn điệu khác nhau:

**Dạng A: $P(L,R): \operatorname{sum}(L,R)\le B$ với $B\ge0$.**

Với $R$ cố định, nếu cửa sổ từ $L$ đã hợp lệ, mọi cửa sổ bắt đầu **muộn hơn** (bỏ nhiều phần tử đầu) cũng hợp lệ. Các vị trí đầu hợp lệ tạo thành một **hậu tố** của tập vị trí bắt đầu $0,1,\ldots,R$:

```text
Các vị trí L ứng với một R cố định:
0  1  2  3  4  5
X  X  X  ✓  ✓  ✓
         ^
         L nhỏ nhất hợp lệ
```

Do đó, có thể di chuyển `L` sang phải cho đến khi cửa sổ hợp lệ; cửa sổ còn lại là **dài nhất kết thúc ở $R$**. Với bài đếm, số cửa sổ không rỗng hợp lệ kết thúc ở $R$ bằng $R-L+1$.

**Dạng B: $P(L,R): \operatorname{sum}(L,R)\ge S$ với $S>0$.**

Với $R$ cố định, nếu một cửa sổ đã đạt ngưỡng thì việc mở rộng nó về **bên trái** (thêm các số không âm) cũng đạt ngưỡng. Các vị trí đầu hợp lệ tạo thành một **tiền tố**:

```text
Các vị trí L ứng với một R cố định:
0  1  2  3  4  5
✓  ✓  ✓  X  X  X
      ^
      L lớn nhất còn hợp lệ, tức cửa sổ ngắn nhất đạt ngưỡng
```

Ta liên tục ghi nhận ứng viên rồi thu trái **trong khi còn đạt ngưỡng**. Cửa sổ hợp lệ cuối cùng trước khi rơi xuống dưới ngưỡng là cửa sổ ngắn nhất kết thúc ở $R$.

**Không được dùng cùng một điều kiện `while` cho mọi bài.** Với bài “dài nhất và không vượt $B$”, thu cửa sổ khi **không hợp lệ**. Với bài “ngắn nhất và đạt $S$”, thu cửa sổ khi **đang hợp lệ** để tìm đoạn còn ngắn hơn.

Tính đơn điệu của **điều kiện cửa sổ** không đòi hỏi dãy đầu vào đã sắp xếp. Chẳng hạn `[2,1,3,2,4,1]` không tăng dần, nhưng tất cả phần tử không âm nên tổng vẫn thay đổi đơn điệu khi thêm/bớt từ hai đầu.

## 3. Mẫu A — Đoạn dài nhất có tổng không vượt ngân sách

**Bài toán:** cho mảng `a` gồm các số nguyên **không âm**, và ngân sách $B\ge0$. Tìm độ dài lớn nhất của đoạn con liên tiếp **không rỗng** có tổng $\le B$. Nếu không có đoạn không rỗng thỏa điều kiện hoặc mảng rỗng, trả 0.

Đặc tả này chấp nhận cả phần tử bằng 0; tổng cần lưu bằng `long` để tránh tràn khi cộng nhiều giá trị `int`.

### Giả mã

```text
LONGEST_AT_MOST(a, B):
    yêu cầu: a không null; mọi a[i] >= 0; B >= 0
    L <- 0
    sum <- 0
    best <- 0

    for R <- 0 đến n - 1:
        sum <- sum + a[R]             // mở rộng phải
        while sum > B:
            sum <- sum - a[L]         // bỏ phần tử trái cũ
            L <- L + 1
        best <- max(best, R - L + 1)  // lúc này hợp lệ

    return best
```

### Vết thực thi

Với `a = [2,1,3,2,4,1]` và $B=7$:

| $R$ | Phần tử thêm | Tổng ngay sau thêm | Hành động thu trái | Cửa sổ hợp lệ sau khi thu | Độ dài | `best` |
| ---: | ---: | ---: | --- | --- | ---: | ---: |
| 0 | 2 | 2 | Không | `[2]` | 1 | 1 |
| 1 | 1 | 3 | Không | `[2,1]` | 2 | 2 |
| 2 | 3 | 6 | Không | `[2,1,3]` | 3 | 3 |
| 3 | 2 | 8 | Bỏ 2 | `[1,3,2]`, tổng 6 | 3 | 3 |
| 4 | 4 | 10 | Bỏ 1 rồi bỏ 3 | `[2,4]`, tổng 6 | 2 | 3 |
| 5 | 1 | 7 | Không | `[2,4,1]` | 3 | 3 |

**Đáp án: 3.** Cửa sổ có thể dài 3 ở nhiều vị trí; bài toán chỉ yêu cầu độ dài nên không cần quy tắc chọn giữa các cửa sổ cùng độ dài. Nếu yêu cầu **vị trí** hoặc **nội dung đoạn**, phải bổ sung quy tắc hòa, ví dụ lấy đoạn xuất hiện sớm nhất.

### Vì sao đúng?

Bất biến sau khi kết thúc vòng `while` cho mỗi $R$:

1. `sum` đúng bằng tổng $a[L]+\cdots+a[R]$ (hoặc 0 khi cửa sổ rỗng).
2. Cửa sổ hiện tại thỏa tổng $\le B$.
3. $L$ là **vị trí bắt đầu nhỏ nhất còn hợp lệ** của đoạn kết thúc tại $R$.

Điều 3 có thể chứng minh quy nạp: ở bước $R-1$, mọi vị trí bắt đầu nhỏ hơn $L$ đều cho tổng vượt $B$. Khi thêm phần tử mới $a[R]\ge0$, chúng vẫn vượt $B$, nên không cần quay `L` về trái. Nếu tổng mới vượt $B$, việc tăng `L` lần lượt loại các vị trí đầu không hợp lệ; đến khi dừng, vị trí mới là nhỏ nhất hợp lệ.

Cửa sổ bắt đầu sớm nhất trong các cửa sổ hợp lệ kết thúc tại $R$ cũng là cửa sổ **dài nhất** trong số đó. Tính `best` trên tất cả đầu phải $R$ vì thế tìm ra độ dài tối ưu toàn cục.

**Khi $B=0$:** các đoạn chỉ chứa số 0 vẫn hợp lệ. Ví dụ `[0,0,5]` cho kết quả 2. Không được giả định cứ $B=0$ thì đáp án bằng 0.

## 4. Mẫu B — Đoạn ngắn nhất có tổng đạt ngưỡng

**Bài toán:** cho mảng `a` có các số nguyên không âm và ngưỡng $S>0$. Tìm độ dài **nhỏ nhất** của đoạn con liên tiếp không rỗng có tổng $\ge S$. Nếu không có, trả `-1`.

Điều kiện $S>0$ bảo đảm cửa sổ rỗng có tổng 0 **không đạt ngưỡng**; nhờ đó vòng thu trái sẽ dừng trước khi vượt ra ngoài đoạn đang xét. Nếu nghiệp vụ cho phép $S\le0$, cần định nghĩa rõ có chấp nhận cửa sổ rỗng hay không và dùng một thuật toán/hợp đồng phù hợp.

### Giả mã

```text
SHORTEST_AT_LEAST(a, S):
    yêu cầu: a không null; mọi a[i] >= 0; S > 0
    L <- 0
    sum <- 0
    best <- +vo_cung

    for R <- 0 đến n - 1:
        sum <- sum + a[R]

        while sum >= S:                       // cửa sổ đang hợp lệ
            best <- min(best, R - L + 1)       // ghi nhận trước
            sum <- sum - a[L]
            L <- L + 1                         // thử cửa sổ ngắn hơn

    if best == +vo_cung:
        return -1
    return best
```

### Vết thực thi

Với `a = [2,3,1,2,4,3]` và $S=7$:

- Khi $R=3$, cửa sổ `[2,3,1,2]` có tổng 8, độ dài 4. Ghi nhận 4, bỏ 2 còn tổng 6 nên dừng thu.
- Khi $R=4$, thêm 4 được cửa sổ `[3,1,2,4]` tổng 10, dài 4. Bỏ 3 còn `[1,2,4]` tổng 7, dài 3; ghi nhận 3. Bỏ 1 còn tổng 6 nên dừng.
- Khi $R=5$, thêm 3 được `[2,4,3]` tổng 9, dài 3. Bỏ 2 còn `[4,3]` tổng 7, dài **2**; ghi nhận 2. Bỏ 4 còn tổng 3 nên dừng.

Kết quả cuối: **2**, tương ứng đoạn `[4,3]`.

### Vì sao đúng?

Với một $R$ cố định, khi tổng đã đạt $S$, bỏ dần phần tử không âm bên trái có thể giữ tổng đạt ngưỡng hoặc làm tổng giảm xuống dưới ngưỡng; một khi dưới ngưỡng, bỏ thêm sẽ không thể làm nó tăng trở lại. Vì vậy, vòng `while` xét lần lượt các cửa sổ hợp lệ kết thúc ở $R$, từ dài đến ngắn, và dừng ngay sau cửa sổ hợp lệ ngắn nhất.

Một đoạn hợp lệ với đầu phải sớm hơn đã được xét ở những vòng trước; một đoạn kết thúc sau sẽ được xét ở vòng tương ứng. Những vị trí `L` đã bị loại ở các bước trước không thể tạo ra **đáp án ngắn hơn** bằng cách kéo dài đầu phải: chúng đã thuộc một cửa sổ hợp lệ có đầu phải sớm hơn hoặc đã được xét khi thu trái. Do đó, giá trị nhỏ nhất của tất cả ứng viên được cập nhật là đáp án toàn cục.

Khác với mẫu A, với mẫu B việc thu trái **khi điều kiện đang đúng** là cần thiết để không bỏ lỡ cửa sổ ngắn nhất. Nếu dừng ngay sau khi tìm được một cửa sổ đạt ngưỡng, thuật toán chỉ tìm được một nghiệm hợp lệ, không bảo đảm tối ưu.

## 5. Mẫu C — Đếm cửa sổ có không quá $K$ giá trị phân biệt

**Bài toán:** cho dãy số nguyên bất kỳ, kể cả âm và trùng nhau, cùng $K\ge0$. Đếm số **đoạn con liên tiếp không rỗng** có **không quá $K$ giá trị khác nhau**.

Ở đây không phụ thuộc dấu của phần tử. Ta duy trì bảng tần suất `freq[value]` và số khóa có tần suất dương:

- Thêm `a[R]`: tăng tần suất của giá trị ấy.
- Nếu có hơn $K$ giá trị phân biệt, bỏ từng `a[L]` khỏi bảng; tần suất về 0 thì xóa khóa.
- Khi còn không quá $K$ khóa, tất cả cửa sổ bắt đầu tại các vị trí $L,L+1,\ldots,R$ đều hợp lệ, vì bỏ thêm phần tử không thể làm tăng số giá trị phân biệt.

Tại một $R$ cố định, số cửa sổ hợp lệ kết thúc ở $R$ bằng:

\[
R-L+1.
\]

Cộng số này qua tất cả $R$ sẽ đếm mỗi cửa sổ **đúng một lần**, bởi mỗi cửa sổ có đúng một chỉ số kết thúc. Vì số cửa sổ có thể đạt $n(n+1)/2$, đáp án nên dùng `long`.

### Giả mã

```text
COUNT_AT_MOST_K_DISTINCT(a, K):
    yêu cầu: a không null; K >= 0
    L <- 0
    answer <- 0
    freq <- bản đồ tần suất rỗng

    for R <- 0 đến n - 1:
        tăng freq[a[R]] thêm 1

        while số khóa trong freq > K:
            giảm freq[a[L]] đi 1
            nếu tần suất trở thành 0:
                xóa khóa
            L <- L + 1

        answer <- answer + (R - L + 1)

    return answer
```

Ví dụ `a=[1,2,1,2,3]`, $K=2$:

| $R$ | Giá trị thêm | Cửa sổ dài nhất hợp lệ kết thúc tại $R$ | Số đoạn được cộng |
| ---: | ---: | --- | ---: |
| 0 | 1 | `[1]` | 1 |
| 1 | 2 | `[1,2]` | 2 |
| 2 | 1 | `[1,2,1]` | 3 |
| 3 | 2 | `[1,2,1,2]` | 4 |
| 4 | 3 | `[2,3]` sau khi thu trái | 2 |

Tổng: $1+2+3+4+2=\boxed{12}$ đoạn có không quá 2 giá trị phân biệt.

**Đếm đúng $K$ giá trị phân biệt.** Với $K\ge1$:

\[
\operatorname{exactlyK}(a,K)
=\operatorname{atMostK}(a,K)
-\operatorname{atMostK}(a,K-1).
\]

Các cửa sổ có không quá $K-1$ giá trị phân biệt là tập con của những cửa sổ có không quá $K$ giá trị; phép trừ giữ lại chính xác những cửa sổ có đúng $K$ giá trị. Trong ví dụ, `atMost(2)=12`, `atMost(1)=5` (chỉ năm cửa sổ một phần tử), nên `exactly(2)=7`.

Với $K=0$, không có đoạn **không rỗng** nào có đúng 0 giá trị phân biệt. Ta có thể định nghĩa đáp án đúng 0 là 0; ví dụ chương trình bên dưới yêu cầu $K\ge1$ cho hàm `exactlyKDistinct` để công thức gọi $K-1$ luôn thuộc miền hợp lệ. Bảng tần suất vẫn xử lý được số âm vì các giá trị được dùng làm **khóa**, không dùng để tính tổng.

### Bất biến quan trọng khi dùng bản đồ tần suất

Sau mỗi lần cập nhật cửa sổ, mọi khóa trong `freq` phải có giá trị dương và đúng bằng số lần xuất hiện của khóa ấy trong $a[L..R]$. Nếu xóa một phần tử mà không giảm tần suất, hoặc để lại khóa có giá trị 0, `freq.size()` có thể sai, khiến thuật toán đếm không chính xác.

Các kỹ thuật `atMost(K)` và `exactly(K)` không giới hạn ở “phân biệt”: chúng có thể áp dụng cho những tiêu chí đơn điệu khác, **nếu** ta chứng minh tập cửa sổ hợp lệ lồng nhau và có thể duy trì trạng thái khi tăng hai con trỏ.

## 6. Java 17+ — Ba mẫu trong một chương trình

Tệp **`SlidingWindowDemo.java`** sau là chương trình đầy đủ, biên dịch và chạy bằng Java 17 trở lên. Hai phương thức liên quan đến **tổng** kiểm tra dữ liệu không âm, còn phương thức đếm giá trị phân biệt chấp nhận số âm. Code không sửa mảng đầu vào.

```java
import java.util.HashMap;
import java.util.Map;

public class SlidingWindowDemo {
    // Longest non-empty subarray whose sum is <= budget.
    // Requires non-negative elements and budget >= 0.
    static int longestSumAtMost(int[] a, long budget) {
        if (a == null || budget < 0) {
            throw new IllegalArgumentException(
                    "array must be non-null and budget >= 0");
        }

        int left = 0;
        int best = 0;
        long sum = 0;

        for (int right = 0; right < a.length; right++) {
            if (a[right] < 0) {
                throw new IllegalArgumentException(
                        "array must contain non-negative elements");
            }

            sum += a[right];

            while (sum > budget) {
                sum -= a[left];
                left++;
            }

            best = Math.max(best, right - left + 1);
        }

        return best;
    }

    // Shortest non-empty subarray whose sum is >= target.
    // Returns -1 if no such subarray exists.
    static int shortestSumAtLeast(int[] a, long target) {
        if (a == null || target <= 0) {
            throw new IllegalArgumentException(
                    "array must be non-null and target > 0");
        }

        int left = 0;
        int best = Integer.MAX_VALUE;
        long sum = 0;

        for (int right = 0; right < a.length; right++) {
            if (a[right] < 0) {
                throw new IllegalArgumentException(
                        "array must contain non-negative elements");
            }

            sum += a[right];

            while (sum >= target) {
                best = Math.min(best, right - left + 1);
                sum -= a[left];
                left++;
            }
        }

        return best == Integer.MAX_VALUE ? -1 : best;
    }

    // Count non-empty subarrays with at most k distinct values.
    static long atMostKDistinct(int[] a, int k) {
        if (a == null || k < 0) {
            throw new IllegalArgumentException(
                    "array must be non-null and k >= 0");
        }

        Map<Integer, Integer> freq = new HashMap<>();
        int left = 0;
        long answer = 0;

        for (int right = 0; right < a.length; right++) {
            freq.merge(a[right], 1, Integer::sum);

            while (freq.size() > k) {
                int value = a[left];
                int remaining = freq.get(value) - 1;

                if (remaining == 0) {
                    freq.remove(value);
                } else {
                    freq.put(value, remaining);
                }

                left++;
            }

            answer += right - left + 1L;
        }

        return answer;
    }

    // Count subarrays with exactly k distinct values (k >= 1).
    static long exactlyKDistinct(int[] a, int k) {
        if (a == null || k < 1) {
            throw new IllegalArgumentException(
                    "array must be non-null and k >= 1");
        }

        return atMostKDistinct(a, k)
                - atMostKDistinct(a, k - 1);
    }

    public static void main(String[] args) {
        int[] forLongest = {2, 1, 3, 2, 4, 1};
        int[] forShortest = {2, 3, 1, 2, 4, 3};
        int[] forDistinct = {1, 2, 1, 2, 3};

        System.out.println(
                "Longest sum <= 7: "
                + longestSumAtMost(forLongest, 7));
        System.out.println(
                "Shortest sum >= 7: "
                + shortestSumAtLeast(forShortest, 7));
        System.out.println(
                "At most 2 distinct: "
                + atMostKDistinct(forDistinct, 2));
        System.out.println(
                "Exactly 2 distinct: "
                + exactlyKDistinct(forDistinct, 2));
    }
}
```

Lưu đúng tên tệp `SlidingWindowDemo.java`, sau đó chạy:

```bash
javac SlidingWindowDemo.java
java SlidingWindowDemo
```

Kết quả chuẩn chính xác:

```text
Longest sum <= 7: 3
Shortest sum >= 7: 2
At most 2 distinct: 12
Exactly 2 distinct: 7
```

**Giải thích những điểm dễ sai trong code:**

- `left` và `right` là chỉ số, tăng một chiều; không phải hai vòng lặp duyệt độc lập tất cả cặp chỉ số.
- Với `longestSumAtMost`, chỉ cập nhật `best` **sau khi** cửa sổ đã được thu về hợp lệ.
- Với `shortestSumAtLeast`, phải cập nhật `best` **trước khi** loại phần tử trái và thử rút ngắn.
- Khi ngân sách $B\ge0$ và mọi phần tử không âm, `longestSumAtMost` có thể thu đến cửa sổ rỗng; lúc này tổng 0 không vượt ngân sách nên vòng `while` dừng và không đọc ngoài mảng.
- Với ngưỡng $S>0$, `shortestSumAtLeast` cũng không tiếp tục thu trái sau khi cửa sổ đã rỗng: tổng rỗng 0 nhỏ hơn $S$.
- `HashMap` phải xóa khóa khi tần suất về 0 để `freq.size()` thực sự là số giá trị phân biệt.
- Toán tử `1L` trong phép đếm buộc phép cộng/chuyển kiểu phù hợp với kết quả `long`. Nếu dùng `int` cho tổng số cửa sổ, kết quả có thể tràn khi $n$ lớn.
- Hai phương thức dùng tổng kiểm tra tính không âm ngay trong quá trình duyệt; với đầu vào không hợp lệ, chúng ném ngoại lệ. Việc kiểm tra sớm toàn bộ mảng trước vòng lặp cũng được nếu muốn tách kiểm tra dữ liệu và thuật toán.
- Dùng kiểu `long` cho `sum` giúp an toàn khi cộng nhiều số nguyên `int` không âm trong mảng Java khả thi; không cần giả định tổng vừa trong `int`.

## 7. Tại sao có vòng while lồng nhau mà vẫn là $O(n)$?

Nhìn bề ngoài, vòng `while` nằm trong vòng `for` có thể gợi ý thời gian $O(n^2)$. Nhưng trong thuật toán này:

- `right` đi từ 0 đến $n-1$, tăng đúng $n$ lần.
- `left` **không bao giờ giảm** và mỗi lần lặp `while` lại tăng ít nhất 1; trên toàn bộ hàm nó tăng tối đa $n$ lần.
- Mỗi phần tử được thêm vào cửa sổ tối đa một lần và được bỏ ra khỏi cửa sổ tối đa một lần.

Do đó tổng số lần cập nhật thêm/bỏ trên **toàn bộ chuỗi** là $O(n)$, dù một vòng `for` có thể thu nhiều lần. Với cập nhật tổng bằng phép cộng/trừ hằng số thời gian, hai bài toán tổng ở trên có:

| Phương thức | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| `longestSumAtMost` | $O(n)$ | $O(1)$ |
| `shortestSumAtLeast` | $O(n)$ | $O(1)$ |
| `atMostKDistinct` | Kỳ vọng $O(n)$ với thao tác bảng băm có chi phí trung bình $O(1)$ | $O(\min(n,K+1))$ khóa trong bảng |
| `exactlyKDistinct` | Kỳ vọng $O(n)$ do gọi `atMostKDistinct` hai lần | $O(\min(n,K+1))$ khóa |

Phân tích bảng băm là theo giả định thao tác tra cứu/cập nhật trung bình $O(1)$. Nếu cần bảo đảm worst-case bất kể chất lượng băm hoặc đầu vào đối kháng, phải xét cấu trúc từ điển thay thế hay chặn riêng của triển khai cụ thể; không được coi mọi thao tác `HashMap` luôn $O(1)$ trong mọi trường hợp.

Cách đếm số lần di chuyển con trỏ là một dạng **phân tích khấu hao** trên toàn chuỗi. Mỗi vòng `while` có thể chạy nhiều lần, nhưng tổng các lượt của nó không vượt số lần `left` có thể tiến, tức $n$. Đây là lý do không được chỉ nhìn cấu trúc lồng vòng lặp rồi kết luận bậc hai.

## 8. Khi nào điều kiện không đơn điệu và cửa sổ trượt thất bại?

### 8.1. Tổng có số âm: phần tử thêm vào có thể làm tổng giảm

Khi mảng có số âm, việc tăng `R` có thể **giảm** tổng; việc tăng `L` có thể **tăng** tổng (nếu bỏ số âm). Hai quan hệ đơn điệu trong mục 2 không còn bảo đảm.

**Phản ví dụ cho đoạn dài nhất có tổng $\le B$.**

`a = [8,-4]`, $B=5$. Nếu dùng `LONGEST_AT_MOST` mà bỏ điều kiện không âm:

1. Gặp 8, tổng 8 > 5; thuật toán loại 8, cửa sổ trở thành rỗng.
2. Gặp -4, chỉ xét cửa sổ `[-4]` dài 1.
3. Nhưng đoạn `[8,-4]` có tổng 4 $\le5$ và dài **2**.

Thuật toán sai vì nó loại vị trí bắt đầu 0 quá sớm. Khi số -4 xuất hiện, một cửa sổ trước đó không hợp lệ **trở nên hợp lệ**; con trỏ trái chỉ tiến không thể khôi phục vị trí đã bỏ.

**Phản ví dụ cho đoạn ngắn nhất có tổng $\ge S$.**

`a = [1,-1,5]`, $S=5$. Khi nhận phần tử 5, toàn bộ cửa sổ có tổng 5 và độ dài 3. Thuật toán ghi 3 rồi bỏ số 1, làm tổng còn 4 nên dừng thu. Nó bỏ lỡ cửa sổ `[5]` dài **1**, vì muốn đến đó còn phải bỏ -1, điều sẽ làm tổng tăng lên 5. Đây chính là điều không được phép xảy ra khi ta dựa vào tính đơn điệu.

**Hướng thay thế:** với bài ngắn nhất có tổng ít nhất $S$ và phần tử có thể âm, một kỹ thuật là **tổng tiền tố + hàng đợi hai đầu đơn điệu (monotonic deque)**, có thể đạt $O(n)$ với thiết kế đúng. Với các điều kiện khác, cần cấu trúc dữ liệu/phương pháp khác (tổng tiền tố, nhị phân hóa đáp án khi có điều kiện, cây hoặc bảng chỉ mục…). Không áp dụng máy móc cửa sổ trượt nếu chưa chứng minh điều kiện liên tục/đơn điệu.

### 8.2. Điều kiện phụ thuộc thứ tự hoặc lịch sử không thể cập nhật đơn giản

Ví dụ “đoạn có **chính xác** $K$ giá trị phân biệt” không luôn hợp lệ chỉ bằng cách nhìn một cửa sổ rồi co cho đến khi đạt đúng $K$: sau khi co có thể đi từ hơn $K$ xuống dưới $K$, và nhiều điểm bắt đầu hợp lệ có thể bị bỏ qua nếu chỉ đếm một cửa sổ. Ta giải bài **đếm chính xác** bằng hiệu hai bài **đếm không quá** $K$ và $K-1$, mỗi bài có điều kiện đơn điệu phù hợp.

Tương tự, một điều kiện trên tỷ lệ, trung bình, tích (nhất là có số 0 và số âm) hoặc sự xuất hiện theo thứ tự đặc biệt cần được kiểm chứng riêng. Không phải cứ dùng hai con trỏ là có thể thu cửa sổ đúng bằng cách bỏ một phần tử.

### 8.3. Đừng nhầm hai khái niệm có chữ “đơn điệu”

- **Điều kiện đơn điệu của cửa sổ:** thay đổi ranh giới theo hướng nhất định cho phép nhận biết các đầu cửa sổ hợp lệ tạo thành vùng liên tiếp, hỗ trợ tiến `left` một chiều.
- **Hàng đợi đơn điệu (monotonic deque):** một cấu trúc dữ liệu giữ phần tử hoặc chỉ số theo thứ tự giá trị để truy vấn min/max hay xử lý tổng tiền tố.

Hai ý tưởng có thể phối hợp, nhưng không đồng nghĩa. Bài này tập trung vào **điều kiện đơn điệu** và hai con trỏ; việc dùng deque phải có bất biến và phân tích riêng.

## 9. Checklist thiết kế một bài cửa sổ trượt

Trước khi viết code, tự trả lời:

1. **Đối tượng đầu ra** là độ dài, vị trí, giá trị, một cửa sổ, hay số lượng cửa sổ? Có yêu cầu không rỗng không?
2. **Cửa sổ** có bắt buộc liên tiếp không? Dữ liệu có âm, 0, trùng lặp, rỗng, `null` không?
3. **Điều kiện hợp lệ** có thật sự đơn điệu khi mở rộng/phá bỏ đầu cửa sổ theo giả định dữ liệu không?
4. Với mỗi `right`, ta muốn cửa sổ **dài nhất**, **ngắn nhất** hay **đếm tất cả**? Từ đó xác định thu khi `invalid` hay thu khi `valid`.
5. **Trạng thái duy trì** là gì: tổng, tần suất, số loại, min/max? Thêm/bỏ có cập nhật đúng và đủ nhanh không?
6. **Bất biến** sau mỗi lần thu là gì? Vì sao không cần giảm `left`?
7. **Trường hợp biên:** $n=0$, $K=0$, $B=0$, $S\le0$, không có nghiệm, nhiều nghiệm cùng độ dài, ngưỡng lớn hơn tổng toàn dãy?
8. **Kiểu số và độ phức tạp:** tổng có cần `long` không, số cửa sổ có cần `long` không, bảng băm có giả định hiệu năng gì?
9. **Kiểm thử đối chiếu:** trên dãy nhỏ, có thể duyệt mọi $O(n^2)$ cửa sổ bằng cách đơn giản và so kết quả với phương pháp tối ưu không?

### Những lỗi cài đặt thường gặp

- Cập nhật `best` khi cửa sổ **chưa** được sửa về hợp lệ trong bài “dài nhất không vượt ngưỡng”.
- Chỉ thu một lần bằng `if` thay cho `while`; một phần tử mới có thể khiến phải loại **nhiều** phần tử trái.
- Với bài “ngắn nhất đạt ngưỡng”, không cập nhật đáp án **trước** khi thu, dẫn đến bỏ qua cửa sổ vừa hợp lệ.
- Lệch chỉ số: dùng $R-L$ thay cho $R-L+1$ khi cả hai đầu đều được tính.
- Quên xóa khóa tần suất bằng 0, khiến số giá trị phân biệt bị đếm sai.
- Dùng dữ liệu âm cho logic dựa trên tổng không âm, hoặc nhập ngưỡng $S\le0$ vào thuật toán giả định $S>0$.
- Dùng `int` cho tổng hoặc số lượng cửa sổ có thể vượt giới hạn số nguyên 32 bit.
- Nhầm “đếm tất cả cửa sổ” với “chỉ đếm cửa sổ dài nhất kết thúc ở mỗi `right`”. Khi tính `atMost`, phải cộng $R-L+1$, không chỉ cộng 1.
- Khẳng định $O(n^2)$ chỉ vì có vòng `while` lồng vòng `for`, bỏ qua việc hai con trỏ tăng tổng cộng tối đa $2n$ lần.

## 10. Bài tập tự kiểm tra

**Bài 1 — Dài nhất.** Với `a = [0,0,5,0]` và $B=0$, đoạn dài nhất có tổng không vượt $B$ dài bao nhiêu? Vì sao phải cho phép phần tử 0 trong lập luận đơn điệu?

**Bài 2 — Ngắn nhất.** Với `a = [2,3,1,2,4,3]` và $S=7$, liệt kê các lần cập nhật `best` khi $R=3,4,5$. Kết quả tối ưu là gì?

**Bài 3 — Đếm đoạn.** Cho `a=[1,2,1,2,3]`. Tính số đoạn có **không quá** 2 giá trị phân biệt, số đoạn có **không quá** 1 giá trị phân biệt, và số đoạn có **đúng** 2 giá trị phân biệt.

**Bài 4 — Phản ví dụ.** Xét `a=[8,-4]` và $B=5$. Giải thích vì sao quy trình “tổng vượt $B$ thì thu trái ngay” làm mất nghiệm tối ưu.

**Bài 5 — Độ phức tạp.** Trong chương trình duyệt dãy dài $n$, tại sao vòng `while` bên trong `for` không khiến số lần tăng `left` vượt $n$? Nếu dùng bảng tần suất băm, cần giả định gì để nói thời gian kỳ vọng $O(n)$?

**Bài 6 — Chính xác K.** Tại sao không thể chỉ viết `while (distinct != K)` rồi tăng một biến đếm ở mỗi `right` để đếm đúng $K$ giá trị phân biệt? Hãy nêu cách chuyển bài toán thành hai điều kiện “không quá”.

### Đáp án gợi ý

1. **2**, là đoạn `[0,0]`. Thêm/bớt số 0 không đổi tổng nhưng vẫn **không phá** tính đơn điệu không giảm/không tăng.
2. Ở $R=3$, ghi 4. Ở $R=4$, xét 4 rồi 3. Ở $R=5$, xét 3 rồi 2. Nhỏ nhất là **2** với đoạn `[4,3]`.
3. `atMost(2)=12`, `atMost(1)=5`, nên `exactly(2)=12-5=7`.
4. Phần tử 8 bị loại ngay khi đứng một mình; khi -4 xuất hiện, đoạn `[8,-4]` có tổng 4 và độ dài 2. Vì tổng có thể giảm khi mở rộng phải nên bỏ đầu cũ không an toàn.
5. `left` chỉ tăng và luôn trong phạm vi từ 0 đến $n$; tổng số lần tăng nhiều nhất $n$. Với HashMap, cần giả định thao tác cập nhật/tra cứu có chi phí trung bình hằng số.
6. Một `right` có thể có **nhiều** đầu trái tạo đoạn đúng $K$; điều kiện `distinct != K` không bảo đảm vùng hợp lệ được đếm đầy đủ. Sử dụng `exactlyK = atMostK - atMost(K-1)`.

## Ghi nhớ

Cửa sổ trượt độ dài thay đổi đạt hiệu quả khi **tính hợp lệ của cửa sổ có cấu trúc đơn điệu** và trạng thái có thể cập nhật lúc thêm/bỏ phần tử. Với các số **không âm**, bài **dài nhất có tổng $\le B$** thu trái khi **vượt ngưỡng**; bài **ngắn nhất có tổng $\ge S>0$** thu trái khi **đã đạt ngưỡng** để thử ngắn hơn. Với bài đếm có **không quá $K$ giá trị phân biệt**, mỗi đầu phải đóng góp đúng $R-L+1$ cửa sổ. Thời gian tuyến tính đến từ việc mỗi con trỏ chỉ tiến một chiều; khi điều kiện đơn điệu bị phá (ví dụ bởi số âm), phải đổi hướng tiếp cận và chứng minh lại tính đúng.
