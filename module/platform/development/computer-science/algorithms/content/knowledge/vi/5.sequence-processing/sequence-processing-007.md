# Cửa sổ trượt có độ dài cố định

**Cửa sổ trượt có độ dài cố định** (*fixed-size sliding window*) là kỹ thuật xử lý các **đoạn liên tiếp gồm đúng k phần tử** trong một dãy. Thay vì tính lại thông tin của từng đoạn từ đầu, ta giữ một trạng thái của cửa sổ hiện tại, **bỏ đóng góp của phần tử rời cửa sổ** và **thêm đóng góp của phần tử mới đi vào**. Với những đại lượng cập nhật được trong O(1), chẳng hạn tổng, kỹ thuật này giúp giảm thời gian từ O(nk) xuống **O(n)**.

Đây là một **mẫu thiết kế thuật toán** trong chủ đề xử lý dãy. Dãy đầu vào có thể lưu bằng mảng, danh sách hoặc chuỗi; cửa sổ là một **khoảng chỉ số liên tục**, không nhất thiết là một mảng con được sao chép. Khái niệm “cửa sổ” chỉ cách chọn nhóm phần tử đang xét và quy tắc dịch chuyển nó.

## 1. Bài toán mẫu và cách biểu diễn cửa sổ

Cho mảng `a` có n phần tử và một số nguyên `k` thỏa **1 ≤ k ≤ n**. Cần tìm **tổng lớn nhất trong mọi đoạn liên tiếp có đúng k phần tử**.

Ví dụ:

```text
a = [2, -1, 3, 4, -2, 5, 1]
k = 3

Cửa sổ 0: [ 2, -1,  3]               tổng 4
Cửa sổ 1:     [-1,  3,  4]           tổng 6
Cửa sổ 2:         [ 3,  4, -2]       tổng 5
Cửa sổ 3:             [ 4, -2,  5]   tổng 7  <- lớn nhất
Cửa sổ 4:                 [-2, 5, 1] tổng 4
```

Mỗi cửa sổ có đúng k phần tử; các cửa sổ có thể **chồng lấn** nhau. Với chỉ số bắt đầu `s`, cửa sổ là:

- **Dạng đoạn đóng:** `[s, s + k - 1]`, gồm cả hai đầu.
- **Dạng đoạn nửa mở:** `[s, s + k)`, gồm s và không gồm `s + k`.
- Chỉ số bắt đầu hợp lệ: `s = 0, 1, ..., n - k`.
- **Số cửa sổ:** `n - k + 1` khi `1 ≤ k ≤ n`.

Vì k **cố định**, khi dịch sang phải một vị trí, ta luôn **bỏ đúng một phần tử bên trái** và **thêm đúng một phần tử bên phải**. Đây là điểm phân biệt với cửa sổ trượt có độ dài thay đổi, nơi hai con trỏ có thể di chuyển độc lập để thỏa một điều kiện.

### Vì sao cách làm ngây thơ chậm hơn?

Một cách trực tiếp là duyệt từng vị trí s, rồi tính tổng k phần tử `a[s] ... a[s+k-1]`. Có `n - k + 1` cửa sổ, mỗi cửa sổ cần k phép cộng, nên thời gian **O((n - k + 1)k)**. Khi k cỡ n/2, đây là O(n²). Tuy nhiên nếu k = 1 hoặc k = n thì cận cụ thể có thể vẫn O(n), vì vậy không nên khẳng định cách ngây thơ luôn “O(n²)” với mọi giá trị k.

Kỹ thuật cửa sổ trượt tái sử dụng kết quả của cửa sổ trước và làm ít thao tác hơn nhiều.

## 2. Công thức trượt: trừ phần tử ra, cộng phần tử vào

Đặt `S(s)` là tổng của cửa sổ bắt đầu tại s:

```text
S(s) = a[s] + a[s+1] + ... + a[s+k-1]
```

Cửa sổ kế tiếp, bắt đầu tại `s+1`, bỏ `a[s]` và thêm `a[s+k]`. Vì các phần tử giữa được giữ nguyên:

**Công thức chuyển trạng thái:**

```text
S(s+1) = S(s) - a[s] + a[s+k]
```

Công thức chỉ áp dụng khi **còn cửa sổ tiếp theo**, tức `s+1 ≤ n-k`. Để tránh dùng nhầm chỉ số, có thể viết theo biến `right` là chỉ số phần tử **mới đi vào**:

```java
windowSum += a[right];         // Thêm đầu phải mới
windowSum -= a[right - k];     // Bỏ đầu trái cũ
```

Ở đây `right` chạy từ k đến n − 1; cửa sổ mới bắt đầu tại `right - k + 1`.

Ví dụ k=3 và tổng đầu tiên là 4:

- Sang cửa sổ 1: `4 - a[0] + a[3] = 4 - 2 + 4 = 6`.
- Sang cửa sổ 2: `6 - a[1] + a[4] = 6 - (-1) + (-2) = 5`.
- Sang cửa sổ 3: `5 - a[2] + a[5] = 5 - 3 + 5 = 7`.
- Sang cửa sổ 4: `7 - a[3] + a[6] = 7 - 4 + 1 = 4`.

Việc có **số âm** không làm công thức sai. Ta cộng/trừ đúng phần tử đi vào/đi ra, không dựa trên giả định tổng sẽ tăng hay giảm khi dịch cửa sổ.

## 3. Quy trình triển khai từng bước

Với `1 ≤ k ≤ n`:

1. **Khởi tạo:** Tính tổng của k phần tử đầu tiên, ứng với cửa sổ `[0, k)`. Công việc này tốn O(k).
2. **Ghi nhận cửa sổ đầu:** Nếu tìm tổng lớn nhất, đặt `bestSum = windowSum` và `bestStart = 0`.
3. **Dịch cửa sổ:** Với từng `right = k, k+1, ..., n-1`, cộng `a[right]` và trừ `a[right-k]`.
4. **Cập nhật kết quả:** Sau khi trượt, cửa sổ mới bắt đầu ở `right-k+1`. So sánh tổng hiện tại với kết quả tốt nhất hoặc ghi kết quả của cửa sổ vào đầu ra.
5. **Trả kết quả:** Với bài tìm cực đại, trả tổng tốt nhất cùng chỉ số bắt đầu; nếu trả mọi cửa sổ, cần bộ nhớ để lưu toàn bộ kết quả.

Pseudo-code dễ chuyển sang nhiều ngôn ngữ:

```text
require 1 <= k <= n
sum = sum(a[0], ..., a[k-1])
best = sum
bestStart = 0

for right = k .. n-1:
    sum = sum - a[right-k] + a[right]
    start = right-k+1
    if sum > best:
        best = sum
        bestStart = start

return (best, bestStart)
```

Ở đoạn trên dùng dấu `>` (không dùng `>=`) để **giữ cửa sổ xuất hiện sớm nhất nếu có nhiều cửa sổ cùng tổng lớn nhất**. Nếu yêu cầu chọn cửa sổ xuất hiện muộn nhất, phải thay điều kiện hoặc xác định quy tắc hòa khác một cách rõ ràng.

### Hai kiểu viết chỉ số

Cả hai đều đúng nếu dùng nhất quán:

- **Theo điểm bắt đầu s:** Tính S(0); khi s đi từ 1 đến n-k, cập nhật `sum += a[s+k-1] - a[s-1]`.
- **Theo điểm phải mới right:** Tính S(0); khi right đi từ k đến n-1, cập nhật `sum += a[right] - a[right-k]`.

Không pha trộn `s` và `right` trong một phép tính mà không chỉ rõ ý nghĩa. Sai lệch 1 ở chỉ số là lỗi phổ biến nhất của kỹ thuật này.

## 4. Chứng minh tính đúng bằng bất biến vòng lặp

Ta chứng minh thuật toán tìm tổng cửa sổ lớn nhất đúng trên mọi mảng có n phần tử với `1 ≤ k ≤ n`.

**Bất biến 1 — Tổng cửa sổ:** Sau khi khởi tạo và sau mỗi lần trượt, biến `windowSum` bằng **tổng đúng k phần tử của cửa sổ hiện tại**.

- **Cơ sở:** Vòng lặp khởi tạo cộng chính xác `a[0], ..., a[k-1]`, nên bất biến đúng cho cửa sổ đầu.
- **Bước duy trì:** Giả sử `windowSum = S(s)`. Cửa sổ mới `[s+1, s+k+1)` giữ chung k−1 phần tử, chỉ bỏ a[s] và thêm a[s+k]. Gán `windowSum = windowSum - a[s] + a[s+k]`, nên `windowSum = S(s+1)`.
- **Kết luận:** Theo quy nạp, tổng được tính đúng cho **mọi** cửa sổ.

**Bất biến 2 — Kết quả tốt nhất:** Sau khi xem xét cửa sổ hiện tại, `bestSum` là tổng lớn nhất trong **tất cả các cửa sổ đã duyệt**; `bestStart` là vị trí xuất hiện đầu tiên đạt tổng ấy.

- **Cơ sở:** Chỉ mới xét cửa sổ đầu nên best nhận đúng giá trị đầu tiên, vị trí 0.
- **Bước duy trì:** Nếu tổng mới lớn hơn best, cập nhật cả tổng lẫn vị trí. Nếu nhỏ hơn hoặc bằng, giữ best; đặc biệt khi bằng thì giữ vị trí sớm hơn.
- **Kết thúc:** Mỗi bước trượt tăng chỉ số bắt đầu đúng 1, từ 0 đến n−k. Sau khi xét `n-k+1` cửa sổ, best là đáp án tối ưu toàn cục theo quy tắc hòa đã chọn.

**Chứng minh kết thúc:** Vòng lặp tính tổng đầu có k lượt hữu hạn. Vòng trượt có n−k lượt hữu hạn. Có thể chọn đại lượng giảm `V = n - right` trong vòng trượt (trước mỗi lượt `right < n`), giảm 1 khi `right` tăng. Vì vậy thuật toán kết thúc.

Điểm quan trọng: bất biến **tổng cửa sổ** chỉ cho biết phép tính trượt đúng; bất biến **kết quả tốt nhất** mới chứng minh cách chọn đáp án đúng.

## 5. Phân tích thời gian và bộ nhớ

Giả sử truy cập một phần tử mảng và phép cộng/trừ số nguyên có chi phí O(1):

| Phần việc | Số lần / chi phí |
| --- | --- |
| Kiểm tra k và n | O(1) |
| Khởi tạo tổng cửa sổ đầu | O(k) |
| Dịch từ cửa sổ đầu tới cuối | n − k lần, mỗi lần O(1) |
| Cập nhật best | O(1) trong mỗi lần dịch |
| **Tổng thời gian** | **O(k + (n-k)) = O(n)** |
| **Bộ nhớ phụ khi chỉ trả best** | **O(1)** |
| **Bộ nhớ nếu lưu tổng của mọi cửa sổ** | **O(n-k+1)** cho mảng kết quả |

Với n≥k≥1, thuật toán phải đọc mọi phần tử có thể ảnh hưởng đến kết quả, nên trong mô hình tổng quát việc quét O(n) là hợp lý. Một vòng lặp chỉ có O(n) lượt **chưa đủ** để khẳng định O(n) thời gian nếu trạng thái mỗi cửa sổ là cấu trúc cần tính lại bằng O(k) hoặc O(log k) thao tác. Phải phân tích **chi phí cập nhật** thực sự.

Nếu dùng `long[]` hoặc trả danh sách các cửa sổ, không gian của **đầu ra** phải được tách khỏi **bộ nhớ phụ để vận hành**. Kỹ thuật tính tổng trượt chỉ cần một biến `long`, nhưng việc yêu cầu trả về mọi tổng buộc phải cấp phát n−k+1 ô.

### So sánh với prefix sum

**Mảng tổng tiền tố** (*prefix sums*) lưu `prefix[i] = a[0] + ... + a[i-1]`, nên tổng cửa sổ `[s, s+k)` bằng `prefix[s+k] - prefix[s]`. Tiền xử lý O(n), mỗi truy vấn tổng đoạn O(1), thêm bộ nhớ O(n).

- Với **một lần quét tất cả cửa sổ có cùng k**, rolling sum thường đơn giản hơn, chỉ O(1) bộ nhớ phụ.
- Với **nhiều truy vấn tổng đoạn tùy ý** hoặc nhiều k khác nhau trên dãy không đổi, prefix sum có thể tiện lợi hơn.
- Nếu dãy bị cập nhật phần tử liên tục, prefix sum tĩnh cần xử lý lại hoặc dùng cấu trúc dữ liệu hỗ trợ cập nhật/truy vấn như Fenwick tree hay segment tree. Đây là nhu cầu khác với việc trượt một cửa sổ cố định.

## 6. Biến thể phổ biến vẫn giữ k cố định

### 6.1 Tổng nhỏ nhất, trung bình và số cửa sổ thỏa ngưỡng

Từ `windowSum`:

- **Tổng nhỏ nhất:** Khởi tạo `minSum` bằng tổng cửa sổ đầu, rồi cập nhật nếu `windowSum < minSum`.
- **Trung bình trượt:** Trung bình cửa sổ bằng `windowSum / k`. Dùng chia số thực để không mất phần thập phân, ví dụ `(double) windowSum / k`.
- **Đếm cửa sổ thỏa ngưỡng:** Sau mỗi lần có tổng, nếu `windowSum >= threshold` thì tăng bộ đếm. Kết quả đếm không cần lưu các tổng riêng lẻ.
- **Phát hiện một cửa sổ thỏa điều kiện:** Có thể dừng sớm nếu chỉ yêu cầu tìm bất kỳ cửa sổ nào, nhưng điều kiện có thể không mang tính đơn điệu khi dãy có số âm.

Mỗi bài cần xác định rõ “đúng k phần tử”, điều kiện so sánh, và yêu cầu xử lý trường hợp bằng nhau.

### 6.2 Số giá trị phân biệt trong mỗi cửa sổ

Với dãy `[2,1,2,3,1]`, k=3, các cửa sổ:

```text
[2,1,2] -> 2 giá trị phân biệt
[1,2,3] -> 3 giá trị phân biệt
[2,3,1] -> 3 giá trị phân biệt
```

Không thể cập nhật **số lượng phần tử phân biệt** chỉ bằng trừ 1/cộng 1 đơn giản, vì giá trị rời cửa sổ có thể còn bản sao khác ở bên trong. Cần cấu trúc **bảng tần suất** (*frequency map*):

1. Đếm tần suất k phần tử trong cửa sổ đầu.
2. Khi trượt, giảm tần suất của phần tử rời; nếu về 0 thì xóa khỏi bảng.
3. Tăng tần suất phần tử đi vào.
4. Số khóa đang có tần suất dương chính là số giá trị phân biệt hiện tại.

Với `HashMap<Integer,Integer>`, chi phí cập nhật trung bình/kỳ vọng O(1) mỗi lượt, nên cả bài O(n) kỳ vọng, dùng O(min(k, U)) bộ nhớ cho bảng tần suất với U là số giá trị khác nhau có thể xuất hiện, cộng O(n−k+1) nếu phải trả về mọi số lượng. Các thao tác bảng băm không được bảo đảm O(1) tuyệt đối trong mọi trường hợp.

### 6.3 Cực đại/cực tiểu trong từng cửa sổ

Không thể dùng quy tắc “cực đại mới = cực đại cũ − phần tử cũ + phần tử mới”. Khi giá trị lớn nhất rời cửa sổ, phải tìm ứng viên lớn nhất còn lại.

- Quét lại mỗi cửa sổ: O(nk) với cách trực tiếp.
- Dùng **deque đơn điệu** chứa chỉ số ứng viên theo thứ tự giá trị giảm dần: tổng thời gian O(n) và bộ nhớ O(k), vì mỗi chỉ số được đưa vào và loại khỏi deque tối đa một lần.
- Dùng cây cân bằng/multiset: thường O(n log k), đổi lại tiện hỗ trợ một số loại cập nhật/truy vấn.

Đây vẫn là **cửa sổ có k phần tử**, nhưng **trạng thái cần giữ** và thuật toán cập nhật đã khác. “Sliding window O(n)” chỉ đúng khi cấu trúc và cách duy trì đại lượng đáp ứng độ phức tạp tương ứng.

## 7. Chương trình Java 17+ hoàn chỉnh

Chương trình sau minh họa: tổng của tất cả cửa sổ k phần tử, cửa sổ có tổng lớn nhất kèm khoảng chỉ số, đếm số cửa sổ vượt ngưỡng, và số giá trị phân biệt mỗi cửa sổ. Dùng `long` cho tổng để tránh tràn khi cộng nhiều giá trị `int`; kết quả trung bình cần ép kiểu sang `double`. Tất cả phương thức thống nhất **chỉ nhận k từ 1 đến n**, vì bài toán không định nghĩa cửa sổ có độ dài 0 hoặc dài hơn dãy.

Lưu toàn bộ thành tệp **`FixedSlidingWindow.java`**:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.Locale;

public class FixedSlidingWindow {
    record BestWindow(long sum, int start, int endExclusive) {}

    static void requireValidWindow(int[] a, int k) {
        if (a == null) {
            throw new IllegalArgumentException("array must not be null");
        }
        if (k <= 0 || k > a.length) {
            throw new IllegalArgumentException("require 1 <= k <= length");
        }
    }

    static long[] allWindowSums(int[] a, int k) {
        requireValidWindow(a, k);
        long[] result = new long[a.length - k + 1];
        long sum = 0;
        for (int i = 0; i < k; i++) {
            sum += a[i];
        }
        result[0] = sum;

        for (int right = k; right < a.length; right++) {
            sum += a[right];
            sum -= a[right - k];
            result[right - k + 1] = sum;
        }
        return result;
    }

    static BestWindow maxSumWindow(int[] a, int k) {
        requireValidWindow(a, k);
        long sum = 0;
        for (int i = 0; i < k; i++) {
            sum += a[i];
        }

        long bestSum = sum;
        int bestStart = 0;
        for (int right = k; right < a.length; right++) {
            sum += a[right];
            sum -= a[right - k];
            int start = right - k + 1;
            if (sum > bestSum) {
                bestSum = sum;
                bestStart = start;
            }
        }
        return new BestWindow(bestSum, bestStart, bestStart + k);
    }

    static int countSumsAtLeast(int[] a, int k, long threshold) {
        requireValidWindow(a, k);
        long sum = 0;
        for (int i = 0; i < k; i++) {
            sum += a[i];
        }
        int count = sum >= threshold ? 1 : 0;
        for (int right = k; right < a.length; right++) {
            sum += a[right];
            sum -= a[right - k];
            if (sum >= threshold) {
                count++;
            }
        }
        return count;
    }

    static int[] distinctCounts(int[] a, int k) {
        requireValidWindow(a, k);
        Map<Integer, Integer> freq = new HashMap<>();
        int[] result = new int[a.length - k + 1];

        for (int i = 0; i < k; i++) {
            freq.merge(a[i], 1, Integer::sum);
        }
        result[0] = freq.size();

        for (int right = k; right < a.length; right++) {
            int leaving = a[right - k];
            int newCount = freq.get(leaving) - 1;
            if (newCount == 0) {
                freq.remove(leaving);
            } else {
                freq.put(leaving, newCount);
            }

            freq.merge(a[right], 1, Integer::sum);
            result[right - k + 1] = freq.size();
        }
        return result;
    }

    public static void main(String[] args) {
        int[] values = {2, -1, 3, 4, -2, 5, 1};
        int k = 3;

        long[] sums = allWindowSums(values, k);
        BestWindow best = maxSumWindow(values, k);
        System.out.println("All sums: " + Arrays.toString(sums));
        System.out.println("Best: sum=" + best.sum()
                + ", range=[" + best.start()
                + ", " + best.endExclusive() + ")");
        System.out.println("Count sums >= 5: "
                + countSumsAtLeast(values, k, 5));
        System.out.println("Average of best: "
                + String.format(Locale.ROOT, "%.2f",
                        (double) best.sum() / k));
        System.out.println("Distinct counts: "
                + Arrays.toString(distinctCounts(
                        new int[]{2, 1, 2, 3, 1}, 3)));
        System.out.println("All-negative best: "
                + maxSumWindow(new int[]{-5, -2, -8}, 2).sum());
        System.out.println("Tie earliest start: "
                + maxSumWindow(new int[]{1, 2, 1, 2}, 2).start());
        System.out.println("k equals n: "
                + Arrays.toString(allWindowSums(
                        values, values.length)));
    }
}
```

Biên dịch và chạy:

```bash
javac FixedSlidingWindow.java
java FixedSlidingWindow
```

Kết quả chính xác:

```text
All sums: [4, 6, 5, 7, 4]
Best: sum=7, range=[3, 6)
Count sums >= 5: 3
Average of best: 2.33
Distinct counts: [2, 3, 3]
All-negative best: -7
Tie earliest start: 0
k equals n: [12]
```

**Giải thích kết quả:** Có 5 cửa sổ độ dài 3 và các tổng lần lượt là 4, 6, 5, 7, 4. Tổng lớn nhất 7 ứng với đoạn nửa mở `[3,6)`, tức các phần tử `[4,-2,5]`. Ba cửa sổ có tổng ít nhất 5. Trung bình cửa sổ tốt nhất là 7/3, in hai chữ số thập phân thành 2.33. Dãy `[2,1,2,3,1]` cho lần lượt 2, 3, 3 giá trị phân biệt. Với toàn số âm, best **phải khởi tạo từ cửa sổ đầu**; khởi tạo bằng 0 sẽ cho kết quả sai.

**Chi phí của từng phương thức:**

- `maxSumWindow` và `countSumsAtLeast`: O(n) thời gian và O(1) bộ nhớ phụ.
- `allWindowSums`: O(n) thời gian; O(n−k+1) bộ nhớ cho mảng kết quả.
- `distinctCounts`: O(n) **kỳ vọng** khi thao tác bảng băm có thời gian kỳ vọng O(1); bảng tần suất O(k) trong trường hợp xấu nhất, cộng O(n−k+1) cho kết quả. Cụ thể số khóa của bảng không quá k; không tăng vô hạn vì khóa có tần suất 0 được xóa.

Tệp dùng cấu trúc `record` có từ Java 16 nên **Java 17+** chạy được.

## 8. Trường hợp biên, lỗi chỉ số và lựa chọn hợp đồng API

| Trường hợp | Kết quả hoặc cách xử lý hợp lý |
| --- | --- |
| `k = 1` | Có đúng n cửa sổ, mỗi cửa sổ là một phần tử; tổng lớn nhất bằng phần tử lớn nhất |
| `k = n` | Có đúng một cửa sổ, tổng là tổng toàn dãy; vòng trượt không chạy |
| `k = 0` | Không có cửa sổ độ dài dương; ví dụ này **ném IllegalArgumentException** |
| `k > n` | Không có cửa sổ gồm k phần tử; ví dụ này **ném IllegalArgumentException** |
| `k < 0` | Độ dài không hợp lệ; ví dụ này **ném IllegalArgumentException** |
| Mảng rỗng `n = 0` | Với hợp đồng k ≥ 1, không có k hợp lệ; ví dụ từ chối |
| Mảng null | Ví dụ từ chối bằng `IllegalArgumentException` |
| Toàn số âm | Khởi tạo best từ cửa sổ đầu, không mặc định 0 |
| Nhiều cửa sổ cùng tổng tốt nhất | Ví dụ giữ vị trí **sớm nhất** vì chỉ cập nhật khi tổng lớn hơn |
| Tổng `int` có thể tràn | Dùng `long` cho biến cộng dồn và kết quả tổng |
| Một phần tử đi ra có nhiều bản sao | Với bảng tần suất, chỉ xóa khóa khi bộ đếm về 0 |

**Cảnh báo off-by-one:** Với `right = k`, phần tử vào là `a[k]` và phần tử rời là `a[0]`; vị trí bắt đầu sau trượt bằng 1. Với `right = n-1`, cửa sổ cuối bắt đầu `n-k`. Vòng lặp chỉ chạy nếu `right < n`; nếu dùng `right <= n` sẽ truy cập vượt mảng.

**Không cấp phát lại đoạn con cho mỗi cửa sổ:** Việc dùng `Arrays.copyOfRange(a, start, start + k)` ở mọi lượt sao chép k phần tử và có thể đẩy thời gian cùng lượng cấp phát lên O(nk). Trượt cửa sổ cần **chỉ số và trạng thái cập nhật**, không cần tạo một mảng mới cho từng đoạn.

**Số học và độ chính xác:** Biến tổng kiểu `int` có thể tràn ngay khi cộng vài giá trị lớn; ví dụ tính tổng hai phần tử `Integer.MAX_VALUE` không vừa `int`. Với mảng `int[]` và kích thước mảng hợp lệ của Java, `long` đủ biểu diễn tổng nguyên của các phần tử; nếu dữ liệu là kiểu có độ chính xác hoặc độ lớn khác, chọn kiểu số tương ứng. Với trung bình, phép chia nguyên `sum / k` làm mất phần thập phân; ép sang `double` nếu chấp nhận kết quả gần đúng.

## 9. Phân biệt cửa sổ cố định và cửa sổ biến đổi

Ví dụ: “Tìm **tổng lớn nhất của đúng k phần tử liên tiếp**” là cửa sổ cố định. “Tìm **đoạn ngắn nhất** có tổng ít nhất T” không xác định sẵn độ dài; đây có thể là cửa sổ thay đổi độ dài, với điều kiện riêng để dịch hai đầu.

| Thuộc tính | Cửa sổ cố định | Cửa sổ biến đổi độ dài |
| --- | --- | --- |
| Độ dài | Luôn đúng k | Phụ thuộc điều kiện bài toán |
| Đầu trái/đầu phải | Cùng dịch 1 sau khi đủ k phần tử | Có thể tiến độc lập |
| Công thức cập nhật tổng | Bỏ đúng một, thêm đúng một | Có thể thêm nhiều/bỏ nhiều theo điều kiện |
| Ví dụ điển hình | Trung bình mọi k ngày, tổng lớn nhất k phần tử | Đoạn con ngắn nhất thỏa ngưỡng dưới giả định thích hợp |
| Rủi ro lập luận | Sai biên, sai k, quên cửa sổ đầu | Độ đơn điệu, số âm, điều kiện thu hẹp |

Không nên dùng chiến lược “mở rộng tới khi đủ, rồi thu hẹp khi tổng đạt ngưỡng” cho mọi dãy có số âm mà không chứng minh tính đơn điệu. Ngược lại, cửa sổ độ dài k cố định **vẫn hoạt động chính xác với số âm**, bởi mỗi phép chuyển luôn là một phép cộng/trừ đại số.

## 10. Những sai lầm thường gặp và cách sửa

1. **Quên tính cửa sổ đầu:** Nếu chỉ cập nhật trong vòng `right = k .. n-1` mà không xét tổng khởi tạo, sẽ bỏ mất vị trí bắt đầu 0. Với k=n còn có thể không xét cửa sổ nào.
2. **Trừ nhầm phần tử:** Với right là phần tử mới, phải trừ `a[right-k]`, không phải `a[right-k+1]`. Phần tử ở chỉ số `right-k+1` thuộc cửa sổ mới.
3. **Cộng vượt biên:** Phần tử mới cuối cùng là `a[n-1]`. Kiểm tra `right < n` và `1 ≤ k ≤ n`.
4. **Khởi tạo best bằng 0:** Sai với các tổng cửa sổ đều âm; dùng chính tổng cửa sổ đầu.
5. **Nhầm giữa độ dài k và số cửa sổ:** Số cửa sổ là n−k+1, không phải n hoặc n−k.
6. **Quên giữ quy tắc hòa:** Cập nhật bằng `>` giữ cửa sổ tối ưu đầu tiên; `>=` sẽ lấy cửa sổ xuất hiện sau cùng trong những cửa sổ bằng nhau.
7. **Coi mọi thống kê đều cập nhật được trong O(1):** Tổng có phép cập nhật đơn giản; maximum per window cần cấu trúc khác nếu muốn nhanh.
8. **Quên đầu ra cũng tốn bộ nhớ:** Trả một tổng tốt nhất dùng O(1) bộ nhớ phụ, nhưng trả n−k+1 tổng cần mảng kết quả.
9. **Dùng giá trị `int` cho tổng lớn:** Có thể tràn dù từng phần tử đều là int hợp lệ; dùng long.
10. **Xóa khóa tần suất quá sớm:** Với các phần tử trùng nhau, giá trị ra khỏi cửa sổ có thể vẫn xuất hiện ở vị trí khác; phải giảm bộ đếm trước, xóa khi bằng 0.
11. **Không phân biệt “liên tiếp” và “chọn tùy ý”:** Sliding window chỉ xét các đoạn con liên tiếp; bài chọn k phần tử bất kỳ là một bài toán khác.
12. **Không chứng minh trạng thái được duy trì:** Một đoạn mã chạy vài test nhỏ chưa bảo đảm đúng; bất biến tổng cửa sổ là cơ sở để tin công thức với mọi k hợp lệ.

## 11. Bài tập tự kiểm tra có đáp án

**Bài 1.** Cho `a = [1, 4, -3, 2, 6]` và k = 2. Liệt kê mọi tổng cửa sổ, tổng lớn nhất và vị trí bắt đầu (đếm từ 0).

**Đáp án:** Các cửa sổ có tổng `5, 1, -1, 8`. Tổng lớn nhất **8**, từ vị trí **3**, tương ứng đoạn `[2, 6]`.

**Bài 2.** Với n=12, k=5, có bao nhiêu cửa sổ và bao nhiêu lần trượt sau khi tính cửa sổ đầu?

**Đáp án:** Có `12−5+1 = 8` cửa sổ; sau khởi tạo có `12−5 = 7` lần trượt.

**Bài 3.** Vì sao khi có số âm, tổng cửa sổ sau khi trượt có thể tăng hoặc giảm, nhưng thuật toán vẫn đúng?

**Đáp án:** Bản chất thuật toán là thay đúng phần tử ra/vào: `S(s+1)=S(s)-a[s]+a[s+k]`. Công thức không dựa vào dấu của số hạng, nên luôn cho tổng của cửa sổ mới.

**Bài 4.** Xét `a = [-10, -3, -5]`, k=2. Nếu khởi tạo `best = 0` thì lỗi gì xảy ra?

**Đáp án:** Các tổng thực tế là `-13` và `-8`; cực đại đúng là **-8** tại vị trí 1. Khởi tạo bằng 0 trả sai vì 0 không phải tổng của bất kỳ cửa sổ hợp lệ nào.

**Bài 5.** Với `a = [4, 4, 1, 4]`, k=2, vì sao bảng tần suất cần đếm chứ không chỉ dùng một tập hợp rồi xóa phần tử ra?

**Đáp án:** Cửa sổ đầu `[4,4]` chứa hai bản sao 4. Khi trượt thành `[4,1]`, một số 4 rời đi nhưng vẫn còn một số 4 trong cửa sổ. Xóa 4 khỏi tập hợp ngay khi thấy phần tử rời sẽ làm mất thông tin về bản sao còn lại; bảng tần suất giảm 2 xuống 1 nên vẫn giữ khóa 4.

**Bài 6.** Cần trả về **tổng của mọi cửa sổ** trong mảng lớn. Vì sao thuật toán có thể dùng O(n) thời gian nhưng O(n−k+1) bộ nhớ?

**Đáp án:** Mỗi cửa sổ kế tiếp chỉ cần O(1) phép tính, nhưng có n−k+1 kết quả phải giữ. Phần bộ nhớ cho kết quả không thể tính là O(1) nếu yêu cầu trả về toàn bộ mảng tổng.

**Bài 7.** Cửa sổ cực đại theo phần tử (không phải tổng) có thể cập nhật bằng công thức trừ/cộng tổng không?

**Đáp án:** Không. Khi phần tử cực đại rời cửa sổ, phải biết phần tử lớn kế tiếp còn lại. Một deque đơn điệu giúp giải quyết tất cả cực đại cửa sổ độ dài k trong O(n) thời gian, O(k) bộ nhớ.

## Ghi nhớ

Cửa sổ trượt độ dài cố định luôn xét **đúng k phần tử liên tiếp**. Tính cửa sổ đầu, sau đó dịch từng bước bằng quy tắc **“trừ giá trị đi ra, cộng giá trị đi vào”** khi thống kê có thể cập nhật như tổng; ghi nhận kết quả ở cả cửa sổ đầu và các cửa sổ sau. Chỉ số đúng, xử lý k hợp lệ, bất biến tổng, cách khởi tạo best và phân tích bộ nhớ đầu ra là những điểm quyết định để có lời giải vừa đúng vừa hiệu quả.
