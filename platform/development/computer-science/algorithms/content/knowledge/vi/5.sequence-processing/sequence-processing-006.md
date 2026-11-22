# Hai con trỏ cùng chiều và ngược chiều

**Hai con trỏ (two pointers)** là kỹ thuật dùng hai vị trí để quản lý phần dữ liệu đang xét, từ đó giảm số tổ hợp phải thử. Hai biến thường được đặt tên `left` và `right`, nhưng điều quyết định không phải tên biến mà là **hướng di chuyển, bất biến và điều kiện cho phép loại bỏ ứng viên**.

Có hai hình thái chính trong xử lý dãy:

1. **Cùng chiều:** hai con trỏ đều tiến từ trái sang phải. Một con trỏ có thể mở rộng đầu phải của **cửa sổ trượt**, con trỏ kia thu hẹp đầu trái; hoặc một con trỏ **đọc** và con trỏ còn lại **ghi** kết quả tại chỗ.
2. **Ngược chiều:** một con trỏ xuất phát ở đầu trái, con trỏ kia ở đầu phải, sau đó tiến lại gần nhau. Mẫu này thường hiệu quả khi **dãy đã sắp xếp** hoặc có phép so sánh mang tính đối xứng từ hai đầu.

Một thuật toán hai con trỏ tốt trả lời được bốn câu hỏi: **trạng thái nào được duy trì; khi nào tăng/giảm mỗi con trỏ; vì sao việc bỏ qua vị trí là an toàn; và mỗi vị trí bị đi qua bao nhiêu lần?**

## 1. Hình dung hướng di chuyển

**Hai con trỏ cùng chiều trên một cửa sổ liên tiếp:**

```text
Mảng:       [2, 3, 1, 2, 4, 3]
             ^        ^
            left     right

right tăng →  thêm phần tử vào cửa sổ
left tăng  →  bỏ phần tử đầu cửa sổ
Cửa sổ đang xét là [left, right], tính cả hai đầu
```

Đầu phải `right` mở rộng vùng có thể chứa đáp án; đầu trái `left` chỉ tiến lên khi có cơ sở loại bớt các phần tử đầu. Cả hai đều không quay lại những vị trí đã bỏ.

**Hai con trỏ ngược chiều trong mảng đã sắp xếp:**

```text
Mảng:       [1, 2, 4, 6, 8, 11]
             ^              ^
            left           right

left tăng  →
             ← right giảm
Khoảng ứng viên hiện tại: [left, right]
```

Ở mẫu này, việc biết `a[left]` là giá trị nhỏ nhất và `a[right]` là giá trị lớn nhất trong khoảng cho phép đưa ra quyết định loại bỏ một đầu sau một lần so sánh.

**Một biến thể cùng chiều là đọc/ghi:**

```text
Mảng đã sắp: [1, 1, 2, 2, 3, 3]
                  → read
                 → write

read  = vị trí phần tử kế tiếp cần kiểm tra
write = vị trí tiếp theo được phép ghi vào tiền tố kết quả
```

`read` và `write` có thể không đứng liền nhau; `write` không nhất thiết là đầu một cửa sổ. Cần phân biệt hai biến thể cùng chiều này trước khi viết mã.

## 2. Chọn mẫu theo cấu trúc bài toán

| Yêu cầu | Mẫu thường dùng | Tiền điều kiện cần kiểm tra |
|---|---|---|
| Tìm đoạn liên tiếp ngắn nhất có tổng ít nhất `target` | Cùng chiều, cửa sổ trượt | Các phần tử **không âm** trong lời giải dưới đây; `target > 0` |
| Duy trì đoạn liên tiếp dài nhất thỏa một giới hạn có thể cập nhật | Cùng chiều, cửa sổ trượt | Có cách biết khi nào cửa sổ hợp lệ và thu hẹp an toàn |
| Xóa giá trị trùng trong mảng đã sắp, giữ một bản sao tại chỗ | Cùng chiều, đọc/ghi | Mảng **đã sắp không giảm** |
| Tìm hai chỉ số khác nhau có tổng bằng một số | Ngược chiều | Dãy **đã sắp không giảm**, nếu dùng quy tắc dịch con trỏ theo tổng |
| So sánh dãy đối xứng hoặc palindrome | Ngược chiều | Quy tắc so sánh hai đầu được xác định |
| Trộn hai dãy đã sắp | Hai con trỏ cùng tiến, một trên mỗi dãy | Cả hai dãy đã sắp cùng thứ tự |

Từ “hai con trỏ” không bảo đảm thời gian `O(n)` trong mọi bài toán: muốn có chặn này, phải chứng minh mỗi con trỏ chỉ dịch chuyển tổng cộng `O(n)` lần. Nếu đầu vào cần sắp xếp trước hoặc đầu ra chứa `Θ(n²)` phần tử, phải tính cả những chi phí đó.

## 3. Cùng chiều với cửa sổ trượt: tổng đoạn con

**Bài toán.** Cho mảng số nguyên **không âm** `a`, một mục tiêu `target > 0`. Hãy tìm độ dài nhỏ nhất của **đoạn con liên tiếp không rỗng** có tổng `>= target`. Nếu không có, trả `0`.

Ví dụ: `a = [2, 3, 1, 2, 4, 3]`, `target = 7`. Đáp án là `2` do đoạn `[4,3]` có tổng `7`.

Ta duy trì cửa sổ `[left, right]`, trong đó cả hai đầu đều thuộc cửa sổ; `sum` là tổng chính xác của các phần tử hiện có. Quy trình:

1. Đặt `left=0`, `sum=0`, `best` chưa có đáp án.
2. Di chuyển `right` từ `0` tới `n-1`, thêm `a[right]` vào `sum`.
3. Trong khi `sum>=target`, cập nhật `best=min(best,right-left+1)`, bỏ `a[left]` khỏi tổng rồi tăng `left`.
4. Khi tổng không còn đủ, ngừng thu hẹp và tiếp tục mở rộng `right`.

| Khi xét `right` | Phần tử mới | Các đoạn đủ tổng được thu hẹp ở bước này | Độ dài tốt nhất |
|---:|---:|---|---:|
| 0 | 2 | Chưa có | Chưa có |
| 1 | 3 | Chưa có | Chưa có |
| 2 | 1 | Chưa có | Chưa có |
| 3 | 2 | `[2,3,1,2]`, tổng 8 | 4 |
| 4 | 4 | `[3,1,2,4]` rồi `[1,2,4]` | 3 |
| 5 | 3 | `[2,4,3]` rồi `[4,3]` | **2** |

### Bất biến và chứng minh

Trong vòng lặp, `sum` luôn là tổng của cửa sổ hiện tại. Khi thêm phần tử ở đầu phải, bất biến vẫn đúng vì tổng được cộng đúng phần tử ấy. Khi tăng `left`, ta trừ chính phần tử vừa bị loại.

Nếu cửa sổ đã đủ tổng, việc thử thu hẹp từ đầu trái giúp tìm đoạn ngắn hơn với cùng đầu phải; bởi vậy phải dùng `while`, không chỉ `if`. Nếu tổng **nhỏ hơn** mục tiêu, việc tiếp tục bỏ một giá trị **không âm** ở đầu sẽ không thể làm tổng tăng để đạt mục tiêu. Ta có quyền dừng thu hẹp và chỉ tăng đầu phải. Mỗi đầu trái đã loại cũng không cần quay lại: ở những đầu phải lớn hơn sau này, giữ đầu trái cũ sẽ chỉ tạo đoạn dài hơn.

Điều kiện không âm rất quan trọng. Với `[1,-1,5]` và `target=5`, đoạn tối ưu là `[5]` dài 1. Quy trình máy móc trên sẽ gặp cả đoạn dài 3 có tổng `5`, sau khi bỏ `1` tổng giảm còn `4` nên dừng, bỏ lỡ việc bỏ tiếp `-1` để được đoạn `[5]`. Đó là **phản ví dụ** cho việc dùng cửa sổ tổng không âm với số âm. Bài toán có số âm có thể cần tiền tố tổng kết hợp deque đơn điệu hoặc thuật toán khác.

**Độ phức tạp:** `right` tăng đúng `n` lần; `left` tăng nhiều nhất `n` lần trên toàn bộ chương trình. Vì tổng số lần dịch chuyển tối đa tỷ lệ với `2n`, thời gian là `O(n)`, bộ nhớ phụ `O(1)`. Vòng `while` nằm trong `for` **không tự động tạo `O(n²)`** vì cùng một phần tử không bị bỏ hai lần.

## 4. Cùng chiều bằng con trỏ đọc và ghi

**Bài toán.** Cho mảng số nguyên đã sắp không giảm. Ghi đè tại chỗ sao cho tiền tố kết quả chứa đúng **một bản sao của mỗi giá trị**, giữ thứ tự, rồi trả độ dài tiền tố.

Ví dụ:

```text
Ban đầu:      [1, 1, 2, 2, 2, 3, 5, 5]
Sau xử lý:    [1, 2, 3, 5, ?, ?, ?, ?]
Độ dài:       4
Tiền tố hợp lệ: [1, 2, 3, 5]
```

Dấu `?` chỉ những ô không thuộc kết quả; trong bộ nhớ chúng có thể còn chứa giá trị cũ.

Với mảng không rỗng, `a[0]` luôn là phần tử đầu tiên cần giữ. Khởi tạo `write=1`, rồi chạy `read` từ `1` đến cuối:

- Nếu `a[read] == a[write-1]`, giá trị trùng với giá trị cuối đã giữ. Bỏ qua.
- Nếu `a[read] != a[write-1]`, gán `a[write]=a[read]` rồi tăng `write`.

**Bất biến:** trước mỗi bước đọc, tiền tố `a[0..write-1]` chứa đúng các giá trị phân biệt đã gặp và `write<=read`. Ghi tại `write` không phá phần tử chưa đọc, vì vị trí ghi không vượt qua vị trí đọc. Do dữ liệu đã sắp nên mọi bản sao của cùng một giá trị nằm cạnh nhau; so với giá trị cuối trong tiền tố là đủ để phát hiện trùng.

Cả `read` và `write` chỉ tăng; thuật toán chạy `O(n)` thời gian và dùng `O(1)` bộ nhớ phụ. Đây là mẫu cùng chiều **đọc/ghi**, khác với cửa sổ trượt tổng ở phần trước. Thao tác không thu nhỏ vật lý kích thước của mảng Java; chỉ `[0,write)` mới là kết quả được cam kết.

Nếu mảng **chưa sắp**, các giá trị trùng có thể nằm xa nhau; so với phần tử gần nhất đã giữ không còn đủ. Khi đó cần sửa cách giải hoặc xác định một chiến lược mới.

## 5. Ngược chiều: tìm cặp có tổng bằng mục tiêu

**Bài toán.** Cho mảng đã sắp xếp không giảm và `target`. Tìm hai **chỉ số khác nhau** `i<j` sao cho `a[i]+a[j]==target`; trả một cặp bất kỳ. Nếu không có, trả `[-1,-1]`.

Ví dụ: `a=[1,2,4,6,8,11]`, `target=10`. Một đáp án là `[1,4]` vì `2+8=10`.

Khởi tạo `left=0` và `right=n-1`. Trong khi `left<right`:

- Nếu tổng hai đầu bằng `target`: trả hai chỉ số.
- Nếu tổng **nhỏ hơn** `target`: tăng `left` để thay số nhỏ bằng số không nhỏ hơn.
- Nếu tổng **lớn hơn** `target`: giảm `right` để thay số lớn bằng số không lớn hơn.

### Tại sao di chuyển như vậy là đúng?

Giả sử `a[left]+a[right]<target`. Vì mảng không giảm, mọi `j<=right` đều có `a[left]+a[j] <= a[left]+a[right] < target`. Do đó **không có cặp hợp lệ nào sử dụng chỉ số `left` trong khoảng ứng viên**. Có thể loại đầu trái mà không mất đáp án.

Ngược lại, nếu `a[left]+a[right]>target` thì mọi `i>=left` đều thỏa `a[i]+a[right]>=a[left]+a[right]>target`. Không cặp hợp lệ nào sử dụng đầu phải; có thể giảm `right`.

Bất biến: **nếu có cặp đúng chưa tìm được, ít nhất một cặp vẫn nằm trong đoạn chỉ số `[left,right]`**. Mỗi bước bỏ một đầu không thể thuộc cặp đúng; khi hai con trỏ gặp nhau, không còn cặp hai chỉ số khác nhau. Mỗi con trỏ đi nhiều nhất `n` vị trí, nên thời gian `O(n)`, bộ nhớ phụ `O(1)`.

### Điều kiện và trường hợp biên

- **Dãy phải có thứ tự phù hợp.** Trên mảng chưa sắp `[1,7,3,5]`, `target=8`, quy tắc trên có thể bỏ lỡ cả cặp `1+7` và `3+5`.
- **Số âm hoàn toàn hợp lệ** nếu mảng đã sắp; khác với điều kiện không âm của bài cửa sổ tổng ở phần 3.
- Nếu có giá trị trùng, vẫn có thể dùng hai chỉ số khác nhau: mảng `[5,5]` với `target=10` trả `[0,1]`.
- Vòng lặp phải là `left<right`, vì `left==right` sẽ dùng một phần tử hai lần.
- Để tránh tràn kiểu khi cộng hai `int`, tính `long sum=(long)a[left]+a[right]`.
- Nếu đề yêu cầu **tất cả cặp** hoặc đếm số cặp bao gồm bản sao, cần quy tắc xử lý trùng riêng. Hàm tìm **một cặp** không tự trả mọi nghiệm.
- Nếu mảng đầu vào chưa sắp và phải giữ **chỉ số gốc**, không được sắp trực tiếp rồi trả chỉ số trên mảng mới mà quên ánh xạ vị trí ban đầu.

## 6. Chương trình Java 17+ chạy được

Chương trình sau triển khai cả ba bài đã phân tích: ngược chiều tìm tổng cặp; cùng chiều đọc/ghi nén giá trị trùng; cùng chiều cửa sổ trượt tìm độ dài nhỏ nhất. Các hàm giả định mảng **khác `null`**; điều kiện sắp xếp được ghi trong chú thích; bài cửa sổ kiểm tra giá trị âm và mục tiêu.

Lưu tệp đúng tên **`TwoPointersDemo.java`**:

```java
import java.util.Arrays;

public final class TwoPointersDemo {
    // Tiền điều kiện: sorted đã sắp xếp không giảm.
    // Trả một cặp chỉ số khác nhau hoặc [-1, -1].
    static int[] pairSumSorted(int[] sorted, long target) {
        int left = 0;
        int right = sorted.length - 1;

        while (left < right) {
            long sum = (long) sorted[left] + sorted[right];
            if (sum == target) {
                return new int[] {left, right};
            }
            if (sum < target) {
                left++;
            } else {
                right--;
            }
        }
        return new int[] {-1, -1};
    }

    // Tiền điều kiện: a đã sắp xếp không giảm.
    // Chỉ tiền tố a[0..write-1] là kết quả hợp lệ.
    static int uniqueSortedInPlace(int[] a) {
        if (a.length == 0) {
            return 0;
        }
        int write = 1;
        for (int read = 1; read < a.length; read++) {
            if (a[read] != a[write - 1]) {
                a[write] = a[read];
                write++;
            }
        }
        return write;
    }

    // Tiền điều kiện: target > 0 và mọi phần tử nums không âm.
    // Trả 0 nếu không tồn tại đoạn liên tiếp không rỗng đủ tổng.
    static int minLengthAtLeast(int[] nums, long target) {
        if (target <= 0) {
            throw new IllegalArgumentException("target must be positive");
        }
        int left = 0;
        int best = Integer.MAX_VALUE;
        long sum = 0;

        for (int right = 0; right < nums.length; right++) {
            if (nums[right] < 0) {
                throw new IllegalArgumentException(
                    "array must be non-negative"
                );
            }
            sum += nums[right];

            while (sum >= target) {
                best = Math.min(best, right - left + 1);
                sum -= nums[left];
                left++;
            }
        }
        return best == Integer.MAX_VALUE ? 0 : best;
    }

    public static void main(String[] args) {
        int[] sorted = {1, 2, 4, 6, 8, 11};
        System.out.println("Pair sum 10: "
            + Arrays.toString(pairSumSorted(sorted, 10)));
        System.out.println("Pair sum 100: "
            + Arrays.toString(pairSumSorted(sorted, 100)));

        int[] duplicates = {1, 1, 2, 2, 2, 3, 5, 5};
        int length = uniqueSortedInPlace(duplicates);
        System.out.println("Unique length: " + length);
        System.out.println("Unique prefix: "
            + Arrays.toString(Arrays.copyOf(duplicates, length)));

        int[] values = {2, 3, 1, 2, 4, 3};
        System.out.println("Min length >= 7: "
            + minLengthAtLeast(values, 7));
        System.out.println("Empty min length: "
            + minLengthAtLeast(new int[0], 7));
    }
}
```

Dùng JDK 17 trở lên để biên dịch và chạy:

```bash
javac TwoPointersDemo.java
java TwoPointersDemo
```

Kết quả chuẩn:

```text
Pair sum 10: [1, 4]
Pair sum 100: [-1, -1]
Unique length: 4
Unique prefix: [1, 2, 3, 5]
Min length >= 7: 2
Empty min length: 0
```

Giải thích: cặp ở chỉ số `1` và `4` là `2` và `8`, có tổng `10`; với `100` thì không có cặp. Tiền tố sau khi nén chứa bốn giá trị khác nhau `1,2,3,5`. Đoạn `[4,3]` dài `2` có tổng bằng `7`. Mảng rỗng không có đoạn liên tiếp không rỗng đủ điều kiện, nên hàm trả `0`.

Cả phép cộng hai phần tử và tổng cửa sổ dùng `long` để tránh tràn kiểu `int`. Nếu bài toán dùng đầu vào lớn hơn phạm vi `int` hoặc nhiều giá trị `long` có thể làm tràn tổng `long`, phải tiếp tục tính miền giá trị an toàn. Hãy phân biệt **đọc theo chỉ số** (không đổi mảng) với **nén tại chỗ** (`uniqueSortedInPlace` có thay đổi mảng đầu vào).

## 7. Chứng minh tổng thời gian gần tuyến tính

Với cùng một mảng dài `n`, ba bài ở trên đều có thời gian `O(n)` nếu **tiền điều kiện đã được bảo đảm**.

| Mẫu | Bất biến chính | Giới hạn dịch chuyển | Thời gian | Bộ nhớ phụ |
|---|---|---|---|---|
| Cửa sổ trượt cùng chiều | Tổng `sum` đúng cho cửa sổ `[left,right]` | Mỗi đầu tăng tối đa `n` lần | `O(n)` | `O(1)` |
| Đọc/ghi cùng chiều | Tiền tố `[0,write)` chứa các giá trị phân biệt đã giữ | `read` tăng `n-1` lần; `write<=read` | `O(n)` | `O(1)` |
| Ngược chiều tìm tổng cặp | Nếu còn cặp đúng, một cặp vẫn ở `[left,right]` | `left` chỉ tăng, `right` chỉ giảm | `O(n)` | `O(1)` |

**Điều kiện tiên quyết không được bỏ qua.** Nếu phải sắp xếp mảng để dùng cặp ngược chiều hoặc nén trùng, tổng thời gian có thể thành `O(n log n)` với sắp xếp so sánh điển hình; bộ nhớ phụ và khả năng giữ chỉ số gốc phụ thuộc cách cài đặt sắp xếp. Đối với bài có đầu ra là tất cả cặp hợp lệ, số lượng kết quả tự nó có thể là `Θ(n²)`, nên không thể tuyên bố xuất tất cả chỉ trong `O(n)`.

### Hai con trỏ cùng chiều trên hai dãy

Một ứng dụng liên quan là **trộn hai mảng đã sắp** bằng `i` trỏ vào mảng A và `j` trỏ vào mảng B. So sánh hai phần tử chưa xử lý; xuất phần tử nhỏ hơn rồi tăng chỉ số tương ứng. Nếu hai mảng có độ dài `n` và `m`, cả hai chỉ số cùng tiến và tổng thời gian là `O(n+m)`. Đây vẫn là tư duy loại bỏ phép so sánh dư thừa nhờ thứ tự, dù hai con trỏ không thuộc một cửa sổ của cùng một mảng.

## 8. Lỗi phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng tìm tổng cặp ngược chiều trên dãy chưa sắp | Loại nhầm đầu và bỏ sót cặp đúng | Kiểm tra/sắp xếp dữ liệu hoặc dùng phương pháp khác |
| Dùng cửa sổ tổng không âm khi có giá trị âm | Loại hoặc giữ phần tử sai, không tìm được đoạn tối ưu | Chứng minh tính đơn điệu hoặc đổi thuật toán |
| Chỉ dùng `if` khi tổng cửa sổ đủ mục tiêu | Không thử các cửa sổ ngắn hơn cùng đầu phải | Thu hẹp bằng `while` khi còn thỏa |
| Điều kiện `left<=right` khi tìm hai chỉ số khác nhau | Có thể đếm một phần tử hai lần | Dùng `left<right` |
| Không thống nhất khoảng `[left,right]` hay `[left,right)` | Lỗi lệch một chỉ số khi đếm độ dài hoặc trừ tổng | Chọn quy ước rồi dùng nhất quán |
| Dùng `a[write]` để so giá trị cuối khi `write` là vị trí ghi kế tiếp | So sánh với ô chưa thuộc tiền tố kết quả | So với `a[write-1]` |
| Trả cả mảng sau khi nén tại chỗ | Phần đuôi còn dữ liệu cũ, không phải kết quả | Chỉ sử dụng tiền tố dài `write` |
| Quên mảng rỗng hoặc mảng một phần tử | Truy cập ngoài mảng, gộp hai chỉ số thành một | Kiểm tra biên hoặc chọn điều kiện lặp tự xử lý |
| Cộng hai giá trị `int` mà không nâng kiểu | Tràn số làm sai so sánh `target` | Dùng `(long)a[left] + a[right]` |
| Thấy vòng `while` bên trong `for` là kết luận `O(n²)` | Đánh giá sai chi phí | Đếm tổng số lần mỗi con trỏ tăng trên cả thuật toán |

## 9. Bài luyện tập

**Bài 1 — Ngược chiều.** Cho dãy đã sắp `[-5,-1,0,4,7,10]` và `target=9`. Hãy mô phỏng từng lần đổi `left/right` và giải thích tại sao có thể loại một đầu.

*Đáp án:* `-5+10=5<9` nên tăng `left`; tiếp theo `-1+10=9` nên trả chỉ số `[1,5]`. Các phần tử ở đầu bị loại không thể kết hợp với bất kỳ phần tử còn lại bên phải để đạt `9`.

**Bài 2 — Cửa sổ cùng chiều.** Với `a=[1,2,1,1,3]` và `target=4`, độ dài ngắn nhất của đoạn liên tiếp không rỗng có tổng ≥ `4` là bao nhiêu?

*Đáp án:* `2`, ví dụ hai phần tử `[1,3]` cuối dãy; không có phần tử đơn lẻ nào đạt `4`.

**Bài 3 — Đọc/ghi.** Nén mảng đã sắp `[2,2,2,3,3,5,5,5,9]` tại chỗ. Tìm `write` sau khi kết thúc và tiền tố hợp lệ.

*Đáp án:* `write=4`; tiền tố `[2,3,5,9]`.

**Bài 4 — Phản ví dụ.** Giải thích vì sao `a=[1,-1,5]`, `target=5` khiến một bản cửa sổ trượt dành cho mảng không âm trả sai.

*Đáp án:* khi tổng của đoạn ba phần tử vừa đạt `5`, bỏ `1` làm tổng xuống `4` và vòng thu hẹp dừng; nếu bỏ tiếp `-1` thì tổng tăng lại thành `5`, để lộ đoạn `[5]` dài một phần tử.

**Bài 5 — Trả chỉ số gốc.** Mảng chưa sắp cần tìm hai giá trị có tổng bằng mục tiêu, đồng thời trả về chỉ số ban đầu. Nêu hai chiến lược và chi phí của chúng.

*Gợi ý:* dùng bảng băm để tìm phần bù trong `O(n)` thời gian kỳ vọng với `O(n)` bộ nhớ phụ; hoặc sắp một mảng các cặp `(giá trị, chỉ số gốc)` rồi quét ngược chiều, tổng thời gian thường `O(n log n)`. Không đánh đồng chỉ số sau sắp xếp với chỉ số ban đầu.

## Ghi nhớ

**Hai con trỏ là cách dùng bất biến để loại bỏ có chứng minh những ứng viên không cần xét.** Với **cùng chiều**, hãy nghĩ đến cửa sổ mở rộng/thu hẹp hoặc tiền tố đọc/ghi; với **ngược chiều**, hãy tìm lý do dựa trên thứ tự hoặc đối xứng để bỏ đầu trái/phải. Luôn hỏi: dữ liệu có cần sắp xếp không; dấu của số có làm hỏng tính đơn điệu không; khoảng chỉ số được tính thế nào; tại sao không bỏ sót kết quả; và tổng số bước dịch con trỏ là bao nhiêu.
