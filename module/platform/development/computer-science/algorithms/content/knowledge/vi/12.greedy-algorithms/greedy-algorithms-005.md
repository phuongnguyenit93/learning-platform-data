# Lập lịch chọn nhiều khoảng không giao nhau nhất

## 1. Bài toán và mục tiêu

Cho `n` công việc (hoạt động, cuộc họp, tác vụ) trên **một tài nguyên duy nhất**, mỗi công việc `i` chiếm một khoảng thời gian từ `start[i]` đến `end[i]`. Ta muốn chọn **nhiều công việc nhất có thể** sao cho không có hai công việc được chọn bị chồng lấn thời gian.

Đây là **bài toán chọn hoạt động (activity selection)** hay **lập lịch khoảng không giao nhau tối đa** (*interval scheduling maximization*), một ví dụ kinh điển cho **thuật toán tham lam (greedy)**.

Điểm quan trọng là **tối đa số lượng khoảng được chọn**, không phải tổng thời gian làm việc, doanh thu, mức ưu tiên hay số phút rảnh. Với phiên bản chuẩn **mỗi khoảng có giá trị như nhau: 1 công việc**, chiến lược tối ưu là:

> **Sắp các khoảng theo thời điểm kết thúc tăng dần; lần lượt chọn khoảng kết thúc sớm nhất còn tương thích với các khoảng đã chọn.**

Lý do trực giác: một công việc kết thúc càng sớm thì càng dành nhiều không gian thời gian cho những công việc tiếp theo. Tuy nhiên, trực giác này cần được chứng minh bằng **lập luận trao đổi (exchange argument)** để bảo đảm đúng cho mọi đầu vào hợp lệ.

### Quy ước khoảng trong bài

Để tránh nhầm lẫn về thời điểm tiếp xúc, bài dùng **khoảng nửa mở** `[start,end)`:

- Thời điểm `start` được tính là đang chiếm dụng.
- Thời điểm `end` không còn bị chiếm dụng.
- Hai khoảng `[a,b)` và `[b,c)` **không giao nhau**, nên có thể chọn liền nhau.
- Mọi công việc đều có **thời lượng dương**: `start < end`. Khoảng rỗng `[t,t)` không nằm trong hợp đồng phiên bản này.
- Thời gian có thể âm, bằng `0` hoặc dương; chỉ cần so sánh được và không bị thay đổi trong lúc chạy.

Với một lịch đã chọn có kết thúc cuối cùng tại `lastEnd`, một khoảng mới `[s,e)` tương thích khi **`s >= lastEnd`**.

Nếu hệ thống thực tế coi khoảng **đóng** `[start,end]`, hai công việc cùng chạm mốc `end=start` sẽ giao nhau tại điểm đó. Khi đó phải yêu cầu **`s > lastEnd`** (hoặc chuẩn hóa mọi khoảng về cùng một định nghĩa). Không dùng hai quy ước trong một lời giải mà không nói rõ.

## 2. Ví dụ trực quan

Xét 11 công việc sau, mỗi công việc có tên và một khoảng nửa mở:

| Công việc | Bắt đầu | Kết thúc | Khoảng |
|---|---:|---:|---|
| A | 1 | 4 | `[1,4)` |
| B | 3 | 5 | `[3,5)` |
| C | 0 | 6 | `[0,6)` |
| D | 5 | 7 | `[5,7)` |
| E | 3 | 9 | `[3,9)` |
| F | 5 | 9 | `[5,9)` |
| G | 6 | 10 | `[6,10)` |
| H | 8 | 11 | `[8,11)` |
| I | 8 | 12 | `[8,12)` |
| J | 2 | 14 | `[2,14)` |
| K | 12 | 16 | `[12,16)` |

Danh sách này đã ở thứ tự kết thúc tăng dần. Quét từ trên xuống và chọn khi `start >= lastEnd`:

| Đang xét | Điều kiện so với `lastEnd` | Quyết định | Kết thúc cuối sau bước |
|---|---|---|---:|
| A `[1,4)` | Chưa chọn gì | **Chọn A** | 4 |
| B `[3,5)` | `3 < 4` | Bỏ | 4 |
| C `[0,6)` | `0 < 4` | Bỏ | 4 |
| D `[5,7)` | `5 >= 4` | **Chọn D** | 7 |
| E `[3,9)` | `3 < 7` | Bỏ | 7 |
| F `[5,9)` | `5 < 7` | Bỏ | 7 |
| G `[6,10)` | `6 < 7` | Bỏ | 7 |
| H `[8,11)` | `8 >= 7` | **Chọn H** | 11 |
| I `[8,12)` | `8 < 11` | Bỏ | 11 |
| J `[2,14)` | `2 < 11` | Bỏ | 11 |
| K `[12,16)` | `12 >= 11` | **Chọn K** | 16 |

Kết quả: chọn **A, D, H, K**, tổng cộng **4 công việc**. Ta có:

```text
A: [1, 4)
D:      [5, 7)
H:            [8, 11)
K:                      [12, 16)

Các khoảng không giao nhau; 4 là số lượng tối đa.
```

**Tối ưu không đồng nghĩa duy nhất.** Có thể tồn tại cách chọn khác cũng đạt `4` công việc. Thuật toán chỉ cần trả **một lịch tối ưu**, không bắt buộc tìm mọi lịch tối ưu.

## 3. Thuật toán tham lam theo thời điểm kết thúc sớm nhất

### Các bước

1. Kiểm tra từng khoảng có `start < end` và thông tin đầu vào hợp lệ.
2. Sắp xếp các khoảng theo `end` tăng dần. Khi hai khoảng có cùng `end`, có thể đặt quy tắc phụ theo `start` rồi tên/ID để kết quả tái lập được; quy tắc phụ **không ảnh hưởng tính tối ưu của số lượng**.
3. Khởi tạo lịch được chọn là rỗng, thời điểm kết thúc cuối `lastEnd` là một giá trị nhỏ hơn hoặc bằng mọi thời điểm bắt đầu khả dĩ.
4. Quét các khoảng theo thứ tự đã sắp:
   - Nếu `start >= lastEnd`, **chọn** khoảng đó và đặt `lastEnd=end`.
   - Nếu `start < lastEnd`, **bỏ qua**, vì khoảng mới chồng với khoảng gần nhất đã chọn.
5. Trả danh sách đã chọn và số lượng `selected.size()`.

Vì ta quét theo `end` tăng dần và mỗi khoảng có thời lượng dương, `end` của những khoảng được chọn tăng nghiêm ngặt. Do đó chỉ cần kiểm tra với **khoảng được chọn gần nhất**, không cần so từng khoảng mới với toàn bộ những khoảng đã chọn: nếu `start` của khoảng mới không nhỏ hơn `lastEnd` thì nó cũng không giao với mọi khoảng đã chọn trước đó.

### Mã giả

```text
selectMaximumNonOverlapping(intervals):
    sort intervals by ascending end

    selected = []
    lastEnd = -infinity

    for interval in intervals:
        if interval.start >= lastEnd:
            selected.append(interval)
            lastEnd = interval.end

    return selected
```

Biến `-infinity` ở mã giả có nghĩa là **chưa có ràng buộc trước đó**. Trong Java, ta có thể dùng `Long.MIN_VALUE` nếu thời gian kiểu `long`; vì mọi `start` đều lớn hơn hoặc bằng giá trị thấp nhất này, khoảng đầu tiên luôn đủ điều kiện. Một lựa chọn khác là dùng biến boolean `hasSelected` rồi luôn chọn khoảng đầu tiên, tránh phụ thuộc sentinel.

### Bất biến khi quét

Sau khi xử lý một tiền tố của danh sách sắp theo `end`:

- `selected` là một tập các khoảng **đôi một không giao nhau**, theo thứ tự đã chọn.
- `lastEnd` là thời điểm kết thúc của khoảng cuối trong `selected` (hoặc trạng thái chưa chọn).
- Trong số các khoảng đã xét, `selected` có số lượng tối đa; đồng thời tồn tại một phương án tối ưu tương thích với mọi lựa chọn tham lam đã thực hiện.

Mệnh đề sau cần lập luận trao đổi ở phần chứng minh. Hai mệnh đề đầu có thể kiểm tra trực tiếp từ điều kiện `start >= lastEnd` và thao tác cập nhật `lastEnd`.

## 4. Tại sao phải chọn kết thúc sớm, không phải bắt đầu sớm?

**Chọn bắt đầu sớm nhất** có thể chặn những công việc ngắn có thể xếp nối tiếp:

```text
L = [0,10)
A = [1, 2)
B = [2, 3)
C = [3, 4)

Nếu chọn công việc bắt đầu sớm nhất:
  Chọn L → không thể chọn A, B, C → 1 công việc.

Nếu chọn công việc kết thúc sớm nhất:
  Chọn A, rồi B, rồi C → 3 công việc.
```

**Chọn thời lượng ngắn nhất** cũng không bảo đảm tối ưu:

```text
A = [1,4)  độ dài 3
B = [4,7)  độ dài 3
C = [3,5)  độ dài 2

Nếu chọn khoảng ngắn nhất đầu tiên:
  Chọn C → A và B đều giao với C → được 1.

Nếu chọn kết thúc sớm nhất:
  Chọn A, rồi B → được 2.
```

**Chọn khoảng ít xung đột nhất với các khoảng khác** cũng không phải quy tắc chuẩn có thể khẳng định tối ưu mà không có chứng minh riêng. Số xung đột toàn cục và tính tương thích với lịch đã chọn là hai tính chất khác nhau.

**Chọn theo thời điểm kết thúc sớm nhất** có điều đặc biệt: sau khi chọn nó, phần còn lại là một **bài toán con cùng dạng**, gồm những khoảng bắt đầu không trước thời điểm nó kết thúc. Quyết định tham lam có thể được đưa vào một phương án tối ưu bằng phép trao đổi.

## 5. Chứng minh tối ưu bằng phép trao đổi (exchange argument)

Ta chứng minh thuật toán luôn tìm được **số khoảng không giao nhau lớn nhất** trong bài toán không trọng số.

Giả sử tập khoảng khả dụng `S` không rỗng. Gọi:

- `g` là khoảng có **thời điểm kết thúc nhỏ nhất** trong `S` (lựa chọn tham lam).
- `O=(o_1,o_2,\ldots,o_k)` là một lịch tối ưu bất kỳ, sắp theo thứ tự thời gian, gồm `k` khoảng không giao nhau.

Vì `g` kết thúc sớm nhất trong các khoảng khả dụng nên:

\[
end(g)\le end(o_1).
\]

Ta thay khoảng đầu tiên `o_1` của lịch `O` bằng `g`:

\[
O'=(g,o_2,\ldots,o_k).
\]

Có hai điều phải kiểm tra:

1. **Số lượng không đổi:** `O'` vẫn chứa `k` khoảng, vì chỉ thay một khoảng bằng một khoảng.
2. **Tính khả thi được giữ:** do `O` khả thi nên mọi khoảng sau `o_1` bắt đầu không trước `end(o_1)`. Mà `end(g)\le end(o_1)`, nên các khoảng sau cũng bắt đầu không trước `end(g)` và **không giao với `g`**.

Nếu `g` đã có trong `O`, ta chọn một biểu diễn `O` bắt đầu bằng `g` khi `g` là khoảng kết thúc sớm nhất trong đó; phép trao đổi vẫn cho thấy tồn tại một phương án tối ưu chứa `g` ở đầu. Như vậy, **ít nhất một phương án tối ưu có lựa chọn đầu tiên giống tham lam**.

Sau khi chọn `g`, các khoảng còn được phép chọn phải có `start >= end(g)`. Những khoảng bắt đầu sớm hơn mốc này không thể đưa vào lịch đã chọn. Ta được **bài toán con cùng cấu trúc**, với ít khoảng hơn.

Áp dụng lập luận trên lặp lại cho bài toán con: có một lịch tối ưu bắt đầu bằng lựa chọn tham lam hiện tại; sau đó lại có một lịch tối ưu bắt đầu bằng toàn bộ tiền tố đã chọn, v.v. Khi không còn khoảng tương thích, lịch tham lam có cùng số lượng với một lịch tối ưu. Vậy nó tối ưu.

**Ý nghĩa của chứng minh:** việc một khoảng kết thúc sớm “có vẻ để lại nhiều thời gian” chỉ là trực giác. Phép trao đổi nêu rõ *vì sao* thay khoảng đầu trong một lời giải tối ưu bằng lựa chọn tham lam **không làm hỏng** lịch còn lại. Đây chính là tính chất lựa chọn tham lam (*greedy-choice property*).

### Các trường hợp hòa thời điểm kết thúc

Nếu hai khoảng có cùng `end` thì chọn bất kỳ một khoảng nào ở thời điểm đầu đều có cùng cận kết thúc cho phần công việc sau. Do đó chọn theo `start` hoặc tên khi hòa `end` chỉ làm kết quả **xác định** hơn; số lượng tối đa vẫn giữ được.

Ví dụ:

```text
A = [1,4)
B = [2,4)
C = [4,5)

Chọn A rồi C: 2 công việc.
Chọn B rồi C: 2 công việc.
```

Đây là lý do chúng ta có thể dùng bộ so sánh `end`, sau đó `start` và `name` trong ví dụ Java mà không làm thay đổi bảo đảm tối ưu.

## 6. Java 17+ hoàn chỉnh

Chương trình sau nhận danh sách `Interval` và trả **một danh sách khoảng được chọn**, không chỉ số lượng. Cài đặt:

- Dùng `record Interval` chứa tên, `start` và `end`.
- Kiểm tra `name` khác `null` và `start < end` ngay khi tạo khoảng; các khoảng rỗng hoặc thời gian đảo bị từ chối.
- Sao chép danh sách đầu vào trước khi sắp, nên **không sửa thứ tự danh sách người gọi**.
- Sắp theo `end`, sau đó `start` rồi `name` để đầu ra có thể tái lập.
- Dùng `Long.MIN_VALUE` làm trạng thái `lastEnd` ban đầu; hoạt động cả với thời điểm âm.
- Chọn khoảng mới khi `interval.start() >= lastEnd`.

Đặt tên tệp đúng là **`IntervalSchedulingDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public final class IntervalSchedulingDemo {
    private IntervalSchedulingDemo() {
    }

    public record Interval(String name, long start, long end) {
        public Interval {
            Objects.requireNonNull(name, "name");
            if (start >= end) {
                throw new IllegalArgumentException(
                    "Require start < end for a nonempty interval"
                );
            }
        }

        @Override
        public String toString() {
            return name + "[" + start + "," + end + ")";
        }
    }

    // Chọn số lượng tối đa khoảng [start,end) không giao nhau.
    // Không thay đổi thứ tự List đầu vào.
    public static List<Interval> selectMaximum(
            List<Interval> intervals) {
        Objects.requireNonNull(intervals, "intervals");

        List<Interval> sorted = new ArrayList<>(intervals);
        for (Interval interval : sorted) {
            Objects.requireNonNull(interval, "interval");
        }

        sorted.sort(
            Comparator.comparingLong(Interval::end)
                .thenComparingLong(Interval::start)
                .thenComparing(Interval::name)
        );

        List<Interval> selected = new ArrayList<>();
        long lastEnd = Long.MIN_VALUE;

        for (Interval interval : sorted) {
            if (interval.start() >= lastEnd) {
                selected.add(interval);
                lastEnd = interval.end();
            }
        }
        return selected;
    }

    public static void main(String[] args) {
        List<Interval> sample = List.of(
            new Interval("A", 1, 4),
            new Interval("B", 3, 5),
            new Interval("C", 0, 6),
            new Interval("D", 5, 7),
            new Interval("E", 3, 9),
            new Interval("F", 5, 9),
            new Interval("G", 6, 10),
            new Interval("H", 8, 11),
            new Interval("I", 8, 12),
            new Interval("J", 2, 14),
            new Interval("K", 12, 16)
        );
        List<Interval> answer = selectMaximum(sample);
        System.out.println("Max count: " + answer.size());
        System.out.println("Selected: " + answer);

        // Các mốc chạm nhau được phép theo khoảng [start,end).
        List<Interval> touching = List.of(
            new Interval("P", -3, 0),
            new Interval("Q", 0, 2),
            new Interval("R", 2, 5),
            new Interval("S", 4, 6)
        );
        System.out.println("Touching: " + selectMaximum(touching));

        // Một khoảng dài không nên chặn ba khoảng ngắn.
        List<Interval> nested = List.of(
            new Interval("Long", 0, 10),
            new Interval("S1", 0, 3),
            new Interval("S2", 3, 7),
            new Interval("S3", 7, 10)
        );
        System.out.println("Nested: " + selectMaximum(nested));

        // Hai khoảng cùng kết thúc: chọn theo start, rồi name.
        List<Interval> ties = List.of(
            new Interval("B", 2, 4),
            new Interval("A", 1, 4),
            new Interval("C", 4, 5)
        );
        System.out.println("Same finish: " + selectMaximum(ties));

        System.out.println("Empty: " + selectMaximum(List.of()));
        System.out.println("Single: " + selectMaximum(
            List.of(new Interval("Only", -9, -3))
        ));

        boolean invalidRejected = false;
        try {
            new Interval("Bad", 5, 5);
        } catch (IllegalArgumentException expected) {
            invalidRejected = true;
        }
        System.out.println("Invalid rejected: " + invalidRejected);
    }
}
```

**Biên dịch và chạy** bằng JDK 17 hoặc mới hơn:

```bash
javac IntervalSchedulingDemo.java
java IntervalSchedulingDemo
```

**Đầu ra chuẩn:**

```text
Max count: 4
Selected: [A[1,4), D[5,7), H[8,11), K[12,16)]
Touching: [P[-3,0), Q[0,2), R[2,5)]
Nested: [S1[0,3), S2[3,7), S3[7,10)]
Same finish: [A[1,4), C[4,5)]
Empty: []
Single: [Only[-9,-3)]
Invalid rejected: true
```

### Giải thích chương trình và kết quả

- `sample` có 11 khoảng, chọn **A, D, H, K**. Mọi cặp kề nhau trong kết quả đều thỏa `start(next) >= end(previous)`; thuật toán chọn được tối đa **4** khoảng.
- `touching` cho thấy `P[-3,0)` và `Q[0,2)` được chọn liên tiếp, vì `0>=0`. `R[2,5)` tiếp tục tương thích, còn `S[4,6)` giao với `R` nên bị bỏ.
- `nested` có khoảng `Long[0,10)` nhưng ba khoảng `S1,S2,S3` kết thúc lần lượt tại `3,7,10`. Chọn ba khoảng ngắn cho **3** hoạt động, tốt hơn chọn riêng khoảng dài.
- `ties` có A và B cùng kết thúc ở `4`, nên hàm dùng `start` để xác định thứ tự A trước B, chọn A rồi C. Nếu hòa mà chọn B thay A, vẫn đạt số lượng tối đa `2`.
- Danh sách rỗng được trả nguyên dạng rỗng; một khoảng hợp lệ duy nhất luôn được chọn.
- `start=end` bị từ chối để giữ hợp đồng **khoảng không rỗng**, không đánh đồng trường hợp này với một cuộc họp thời lượng bằng `0`.
- Các lần chọn chỉ lấy tham chiếu tới `Interval` bất biến; `selectMaximum` không thay đổi thứ tự `sample` và không thay đổi thời gian của các phần tử.

Dấu ngoặc hiển thị ở `Selected: [A[1,4), ...]` gồm **ngoặc vuông ngoài** của `List.toString()` và ký hiệu `[start,end)` bên trong mỗi `Interval`. Đây là định dạng do ví dụ chủ động định nghĩa, không phải một kiểu dữ liệu lịch đặc biệt của Java.

## 7. Độ phức tạp thời gian và bộ nhớ

Với `n` khoảng:

1. **Sắp xếp:** `O(n log n)` thời gian trong trường hợp xấu nhất của một thuật toán sắp xếp so sánh hiệu quả; trong ví dụ Java dùng `List.sort` với comparator của JDK.
2. **Quét sau khi sắp:** đúng một vòng qua `n` phần tử, mỗi bước so sánh và cập nhật `O(1)`; tổng `O(n)`.
3. **Tổng thời gian:** **`O(n log n)`** cho quy trình tổng quát.
4. **Bộ nhớ:** bản ví dụ sao chép danh sách `O(n)` và có thể lưu tối đa `n` khoảng trong `selected`, nên **`O(n)` bộ nhớ phụ**, chưa tính bộ nhớ tạm nội bộ của thuật toán sắp. Không cần cấp lưới theo độ dài trục thời gian.
5. Nếu đầu vào **đã sắp theo kết thúc tăng dần**, có thể bỏ bước sort và chỉ quét, đạt **`O(n)`** thời gian.

Một số người chỉ quan tâm **số lượng** thay vì lịch chi tiết. Khi đó có thể tăng biến `count` thay vì lưu danh sách `selected`. Nếu sắp tại chỗ được phép thì có thể giảm bộ nhớ đầu ra, nhưng phải xem xét bộ nhớ tạm của thư viện sắp và quyền sửa dữ liệu người gọi. Không nên nói bản mã hiện tại chỉ tốn `O(1)` bộ nhớ: nó có sao chép danh sách và lưu kết quả.

**Độ lớn thời gian không quan trọng đối với số vòng lặp.** Thời điểm có thể là `-1.000.000.000` hoặc `+1.000.000.000` mà thuật toán vẫn chỉ cần sắp `n` cặp `(start,end)`, không phải duyệt từng đơn vị thời gian. Đây là ưu điểm của cách xử lý **theo sự kiện/khoảng** thay vì mô phỏng mọi mốc trên trục thời gian.

### Một bảng so sánh cách tiếp cận

| Cách làm | Ý tưởng | Chi phí điển hình | Độ tin cậy tối ưu |
|---|---|---|---|
| Thử mọi tập con | Xét tất cả `2^n` cách chọn, kiểm tra tương thích | Mũ theo `n` | Đúng nếu xét toàn bộ; chỉ dùng làm đối chứng nhỏ |
| Chọn bắt đầu sớm nhất | Xếp theo `start`, chọn cái đầu hợp lệ | `O(n log n)` | **Không bảo đảm tối ưu** |
| Chọn thời lượng ngắn nhất | Xếp theo `end-start` | `O(n log n)` | **Không bảo đảm tối ưu** |
| **Chọn kết thúc sớm nhất** | Xếp theo `end`, lấy khoảng tương thích | **`O(n log n)`** | **Tối ưu** khi mọi khoảng có trọng số bằng nhau |
| Quy hoạch động có trọng số | Sắp theo `end` và tối ưu chọn/bỏ | Thường `O(n log n)` | Dành cho mục tiêu **tổng giá trị**, không chỉ số lượng |

### Thứ tự trả về

Các khoảng trong kết quả xuất hiện theo **thời điểm kết thúc tăng dần**, cũng chính là thứ tự lịch trình. Đây là một danh sách hợp lệ; **không bảo đảm giữ thứ tự ban đầu** của danh sách đầu vào. Nếu bài toán yêu cầu trả **chỉ số gốc**, cần lưu ID/chỉ số gốc trong bản ghi `Interval` khi xây danh sách; sắp xếp tham chiếu mà không mang theo ID sẽ làm mất thông tin vị trí gốc.

## 8. Các biến thể rất dễ nhầm với bài toán chuẩn

### 8.1. Khoảng có trọng số: không dùng tham lam kết thúc sớm

Nếu mỗi công việc có `weight`, `profit` hoặc `score` khác nhau và mục tiêu là **tối đa tổng trọng số**, chọn kết thúc sớm nhất **có thể sai**.

Ví dụ:

```text
L: [0,10), weight = 100
A: [0, 3), weight =   1
B: [3, 7), weight =   1
C: [7,10), weight =   1

Tham lam theo kết thúc sớm chọn A, B, C:
  Số lượng = 3; tổng weight = 3.

Nếu mục tiêu là tối đa weight, chọn L:
  Số lượng = 1; tổng weight = 100.
```

Bài toán có trọng số thường dùng **quy hoạch động**. Sắp các công việc theo `end`. Với công việc thứ `i`, tìm `p(i)` là công việc kết thúc muộn nhất trong những công việc đứng trước `i` mà vẫn tương thích: `end(p(i)) <= start(i)` theo quy ước nửa mở.

Khi đó đặt `OPT(i)` là tổng trọng số lớn nhất trong `i` công việc đầu, ta có:

\[
OPT(i)=\max(OPT(i-1),\ weight_i+OPT(p(i))).
\]

Đây là **weighted interval scheduling**, một bài toán liên quan nhưng khác hợp đồng. Với trọng số đều bằng `1`, tham lam kết thúc sớm giải phiên bản không trọng số đơn giản và nhanh hơn về cấu trúc cài đặt.

### 8.2. Tối đa tổng thời gian chiếm dụng

Nếu mục tiêu là **tổng độ dài những khoảng được chọn**, lời giải có thể khác tối đa số lượng. Ví dụ:

```text
Long = [0,10)  độ dài 10
A    = [0, 3)  độ dài 3
B    = [3, 6)  độ dài 3
C    = [6, 9)  độ dài 3
```

Chọn A, B, C đạt **3 công việc** nhưng tổng thời gian là `9`. Chọn Long đạt **1 công việc** nhưng tổng thời gian là `10`. Thuật toán trong bài chỉ tối đa **số lượng**, không hứa tối đa **tổng thời lượng**.

### 8.3. Bao nhiêu phòng/máy để chứa mọi công việc?

Nếu phải thực hiện **tất cả** công việc nhưng được dùng nhiều phòng hoặc nhiều máy, bài toán là **interval partitioning**, không phải chọn tối đa một tập không giao nhau. Mục tiêu có thể là **số tài nguyên tối thiểu** để phục vụ mọi khoảng; một phương án phổ biến là sắp theo `start` và dùng min-heap các thời điểm kết thúc đang sử dụng. Quy tắc “chọn kết thúc sớm nhất” của bài này không trực tiếp giải câu hỏi số phòng cần có.

### 8.4. Số khoảng giao nhau cực đại tại một thời điểm

Bài toán tìm **mức chồng lấn tối đa** của mọi khoảng cũng khác. Có thể dùng sweep line với sự kiện bắt đầu/kết thúc, lưu ý ở cùng thời điểm thì với khoảng `[start,end)`, các sự kiện kết thúc nên được xử lý trước các sự kiện bắt đầu để tránh đếm nhầm khoảng chỉ chạm nhau là chồng lấn.

### 8.5. Có điều kiện nghỉ hoặc chuyển đổi giữa công việc

Nếu sau mỗi công việc phải nghỉ thêm `gap` đơn vị thời gian, hai khoảng chỉ tương thích khi:

```text
next.start >= previous.end + gap
```

Cần dùng kiểu số đủ rộng và tránh tràn trong phép cộng. Nếu `gap` là hằng số không âm chung cho mọi cặp, một dạng tham lam tương tự vẫn có thể chứng minh bằng trao đổi sau khi cập nhật định nghĩa khả thi. Nhưng nếu thời gian chuyển đổi **phụ thuộc cặp công việc**, hoặc có ràng buộc tài nguyên/phụ thuộc, bài toán có thể không còn thỏa tính chất lựa chọn tham lam đơn giản.

## 9. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Sắp theo `start` thay vì `end` | Có thể chọn một khoảng dài và bỏ nhiều khoảng ngắn | Sắp theo **kết thúc tăng dần** |
| Chọn khoảng ngắn nhất | Khoảng ngắn ở giữa có thể chặn hai khoảng nối tiếp | Dùng **kết thúc sớm nhất**, không phải độ dài nhỏ nhất |
| Dùng `start > lastEnd` với khoảng `[start,end)` | Bỏ các khoảng chạm ranh giới dù hợp lệ | Dùng **`start >= lastEnd`** |
| Dùng `start >= lastEnd` với khoảng đóng `[start,end]` | Chọn hai khoảng có chung một mốc thời gian | Quy định rõ kiểu khoảng; với khoảng đóng dùng **`>`** |
| Đếm tối đa số lượng nhưng tự gọi là tối đa doanh thu | Sai mục tiêu khi có trọng số | Tách bài không trọng số và weighted scheduling |
| Không ghi nhận quy ước khoảng rỗng | `[t,t)` có thể được hiểu khác nhau | Trong bài này yêu cầu **`start < end`** |
| Chỉ kiểm tra tương thích với khoảng **trước trong đầu vào** | Có thể kiểm tra sai vì thứ tự đầu vào không phải lịch được chọn | Kiểm tra với **`lastEnd` của khoảng đã chọn cuối** |
| Quên cập nhật `lastEnd` sau khi chọn | Có thể chọn các khoảng giao nhau | Cập nhật bằng `end` ngay khi thêm |
| Cập nhật `lastEnd` cả khi bỏ | Loại nhầm những khoảng còn tương thích | Chỉ cập nhật khi **chọn** |
| Dùng `int` và so sánh bằng `x.end-y.end` | Phép trừ có thể tràn số | Dùng `Comparator.comparingLong` / `Long.compare` |
| Tuyên bố khoảng được chọn là duy nhất | Có thể có nhiều lịch tối ưu cùng số lượng | Trả một phương án tối ưu, dùng tie-break để xác định kết quả |
| Tự sửa danh sách đầu vào khi không được yêu cầu | Thứ tự đầu vào bị thay đổi | Sao chép trước khi sắp |
| Không giữ ID/chỉ số gốc | Không thể trả lại vị trí ban đầu đúng | Lưu ID cùng mỗi khoảng nếu đề cần |
| Thời điểm âm nhưng khởi tạo `lastEnd=0` | Có thể bỏ qua khoảng kết thúc trước `0` | Chọn vô cực âm tương ứng kiểu dữ liệu hoặc xử lý “chưa chọn” |
| Không kiểm tra công việc có `start >= end` | Định nghĩa khoảng có thể không như thuật toán dự tính | Xác nhận hợp đồng, trong mã từ chối khoảng không dương |

### Ghi nhớ khác biệt giữa “bỏ” và “chọn”

Khi một khoảng mới giao với khoảng đã chọn cuối, thuật toán **bỏ qua** nó và giữ nguyên `lastEnd`. Nếu cập nhật `lastEnd` bằng thời điểm kết thúc của một khoảng **đã bị bỏ**, ta vô tình tạo ra ràng buộc từ công việc **không thực hiện**. Điều đó có thể làm mất một lịch tối ưu.

Ví dụ: đã chọn `[1,4)`; gặp `[2,100)` thì bỏ. Nếu sai lầm cập nhật `lastEnd=100`, các khoảng `[5,6)`, `[6,7)` sẽ bị bỏ oan. Đúng ra `lastEnd` vẫn là `4` và có thể chọn cả hai khoảng đó.

## 10. Kiểm thử và đối chứng tính tối ưu

Một kiểm thử tốt phải kiểm tra cả **tính khả thi** lẫn **số lượng tối ưu**:

1. **Rỗng và một khoảng:** kết quả tương ứng `0` và `1`.
2. **Khoảng chạm nhau:** `[1,3)` và `[3,5)` chọn được cả hai.
3. **Khoảng hoàn toàn nằm trong nhau:** nếu một khoảng dài bao nhiều khoảng ngắn nối tiếp, phải chọn các khoảng ngắn khi số lượng lớn hơn.
4. **Mọi khoảng giao nhau:** chỉ chọn tối đa một.
5. **Không có khoảng nào giao nhau:** chọn được tất cả.
6. **Cùng `end` và cùng `start`:** kiểm tra tie-break và tính tương thích.
7. **Thời điểm âm và cực trị `long`:** không khởi tạo sai `lastEnd`, không trừ hai thời điểm để so sánh.
8. **Đầu vào chưa sắp hoặc đảo thứ tự:** phải trả số lượng tối ưu không phụ thuộc thứ tự cung cấp.
9. **Đầu vào không hợp lệ:** `start>=end`, `null`, hoặc phần tử `null` phải bị từ chối đúng hợp đồng.

### Đối chứng bằng vét cạn với n nhỏ

Với `n` nhỏ (chẳng hạn `n<=15`), có thể xét mọi tập con `2^n`:

- Giữ một tập con nếu các khoảng trong đó **đôi một không giao nhau**.
- Tính số phần tử lớn nhất trong tất cả tập con hợp lệ.
- So sánh với số lượng thuật toán tham lam trả về.

Đây không phải cách tính cho đầu vào lớn vì chi phí tăng theo hàm mũ, nhưng là **oracle kiểm thử** rất mạnh: trên những mảng ngẫu nhiên nhỏ, đối chiếu tham lam với tối ưu vét cạn sẽ giúp phát hiện lỗi ranh giới, hướng sắp xếp và xử lý khoảng chạm nhau.

**Cách kiểm tra một lịch được trả về:** sắp chính lịch đó theo thời điểm bắt đầu (hoặc xác nhận các khoảng đang theo kết thúc tăng) và kiểm tra với mọi cặp liền kề `start(next) >= end(previous)`. Với các khoảng hợp lệ có thời lượng dương và kết quả theo thứ tự thời gian, tính chất này đủ bảo đảm **không có cặp nào giao nhau**.

## 11. Bài tập tự luyện

**Bài 1 — Mốc chạm nhau.** Cho `A=[1,3)`, `B=[3,5)`, `C=[2,4)`. Theo quy ước nửa mở, chọn được nhiều nhất bao nhiêu khoảng? Thuật toán kết thúc sớm chọn khoảng nào?

*Đáp án:* chọn **2** khoảng: A rồi B. C giao với cả A và B.

**Bài 2 — Vì sao chọn bắt đầu sớm sai?** Cho `L=[0,10)`, `A=[1,2)`, `B=[2,3)`, `C=[3,4)`. So sánh lựa chọn bắt đầu sớm với kết thúc sớm.

*Đáp án:* bắt đầu sớm chọn L được `1`; kết thúc sớm chọn A, B, C được `3`.

**Bài 3 — Thứ tự hòa.** Cho `A=[1,4)`, `B=[2,4)`, `C=[4,5)`. Có cần luôn chọn A thay B để tối ưu số lượng không?

*Đáp án:* không. Cả A+C và B+C đều gồm `2` khoảng. Quy tắc phụ chỉ khiến đầu ra dự đoán được.

**Bài 4 — Quy ước khoảng.** Hai cuộc họp là `[9,10]` và `[10,11]` theo **khoảng đóng**. Chúng có giao nhau không? Nếu đổi sang `[9,10)` và `[10,11)` thì sao?

*Đáp án:* khoảng đóng giao tại thời điểm `10`; khoảng nửa mở không giao. Vì vậy điều kiện chọn kế tiếp phụ thuộc quy ước.

**Bài 5 — Mục tiêu thay đổi.** Cho `L=[0,10)` trọng số `100`, `A=[0,3)`, `B=[3,7)` và `C=[7,10)` đều trọng số `1`. Tối đa số lượng và tối đa tổng trọng số có cùng lời giải không?

*Đáp án:* không. Tối đa số lượng chọn A, B, C (`3` việc); tối đa trọng số chọn L (trọng số `100`).

**Bài 6 — Bất biến.** Giả sử `lastEnd=4`, đã chọn `[1,4)`, rồi xét `[2,100)`, `[5,6)`, `[6,7)`. Thuật toán xử lý thế nào?

*Đáp án:* bỏ `[2,100)` mà **không sửa `lastEnd`**, sau đó chọn `[5,6)` và `[6,7)`.

**Bài 7 — Tự viết kiểm thử.** Viết một hàm vét cạn cho tối đa `12` khoảng nửa mở có `start<end`; sinh nhiều bộ khoảng ngẫu nhiên và kiểm tra `selectMaximum` trả đúng số lượng tối đa. Hãy thử thêm các trường hợp `start<0` và nhiều `end` bằng nhau.

*Gợi ý:* duyệt các bitmask từ `0` đến `(1<<n)-1`, trích các khoảng được chọn, sắp chúng theo `start` rồi kiểm tra điều kiện tương thích. Lấy max kích thước của các mask hợp lệ.

## Ghi nhớ

**Bài toán chọn nhiều khoảng không giao nhau nhất trên một tài nguyên với mọi công việc có trọng số bằng nhau được giải tối ưu bằng cách luôn chọn khoảng kết thúc sớm nhất còn tương thích.** Sắp theo `end` tăng dần, quét từng khoảng, chọn khi `start>=lastEnd` theo quy ước `[start,end)`, rồi chỉ cập nhật `lastEnd` khi thật sự chọn.

Phép trao đổi chứng minh rằng thay khoảng đầu trong một lịch tối ưu bằng khoảng kết thúc sớm nhất **không làm mất khả năng chọn các khoảng sau**, nên có thể tiếp tục tham lam trên bài toán con. Thuật toán có thời gian **`O(n log n)`** khi cần sắp xếp và **`O(n)`** nếu đã sắp. Cần phân biệt rõ **khoảng nửa mở/đóng**, **tối đa số lượng với tối đa trọng số**, và **bỏ khoảng với cập nhật trạng thái** để tránh áp dụng sai.
