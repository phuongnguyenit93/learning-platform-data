# Chọn top-k bằng heap kích thước giới hạn

> **Chủ đề:** Computer Science Algorithms → Chọn và thứ tự.  
> **Mục tiêu:** Dùng heap chỉ chứa tối đa `k` phần tử để chọn `k` giá trị lớn nhất hoặc nhỏ nhất từ một dãy hay luồng dữ liệu; chứng minh đúng bằng bất biến; phân tích `O(n log(k+1))` thời gian, `O(k)` bộ nhớ; xử lý giá trị trùng, điểm bằng nhau, biên `k=0`, truy vấn phần tử thứ k và lựa chọn giữa heap, sắp xếp toàn bộ, quickselect.

## 1. Bài toán top-k là gì?

Cho dãy `n` phần tử và một số nguyên `k`, ta cần chọn **đúng k phần tử tốt nhất** theo một thứ tự đã định:

- **Top-k lớn nhất:** chọn `k` giá trị lớn nhất; ví dụ top 3 của `[5,1,9,4,7,2,8]` là `[9,8,7]` nếu xuất theo chiều giảm.
- **Top-k nhỏ nhất:** chọn `k` giá trị nhỏ nhất; với cùng dãy là `[1,2,4]` theo chiều tăng.
- **Top-k bản ghi:** chọn theo trường như điểm số hoặc thời gian, có thể thêm quy tắc phụ để xử lý các điểm bằng nhau.
- **Phần tử lớn thứ k (*k-th largest*):** chỉ cần biết ngưỡng xếp hạng ở vị trí `k` theo thứ tự giảm, không nhất thiết xuất đầy đủ `k` phần tử.

Trong bài học này, **giá trị trùng được tính theo số lần xuất hiện**, trừ khi đề yêu cầu “k giá trị *phân biệt*”. Ví dụ với `[9,9,7,4]`, top 2 thông thường là `[9,9]` và phần tử lớn thứ 2 là `9`; còn nếu yêu cầu **phân biệt**, hai giá trị lớn nhất là `[9,7]`. Hai bài có đặc tả khác nhau.

Với đầu vào là mảng tĩnh, các ví dụ Java dưới đây chọn hợp đồng **`0 <= k <= n`**. Nếu `k=0`, kết quả rỗng; nếu `k=n`, chọn toàn bộ phần tử; nếu `k>n` hoặc `k<0`, báo lỗi đầu vào. Với luồng dữ liệu chưa biết số phần tử cuối cùng, một bộ theo dõi top-k có thể giữ *tối đa k* phần tử cho tới khi đã nhận đủ dữ liệu; kết quả tạm thời có ít hơn k phần tử là hợp lệ.

### 1.1. Chọn top-k khác sắp xếp toàn bộ

Nếu chỉ cần vài phần tử tốt nhất, **không nhất thiết phải biết thứ tự giữa mọi phần tử còn lại**. Có ba dạng kết quả khác nhau:

1. **Tập/multiset top-k, không cần sắp:** chỉ cần chọn đúng những phần tử tốt nhất, thứ tự xuất tùy ý.
2. **Danh sách top-k đã sắp:** sau khi chọn phải sắp riêng `k` phần tử đó.
3. **Ngưỡng k-th:** chỉ cần một phần tử ở thứ hạng `k`, tức phần tử “tệ nhất” trong nhóm k tốt nhất.

Heap giới hạn kích thước phù hợp cả ba, nhưng chi phí **xuất danh sách đã sắp** và chi phí **chọn** phải được tính tách bạch. Một `PriorityQueue` của Java không tự cung cấp thứ tự từ tốt nhất đến kém nhất khi lặp bằng `for-each`.

## 2. Tại sao phải dùng heap theo hướng “ngược” với mục tiêu?

Heap là cây nhị phân gần hoàn chỉnh thường được cài bằng mảng:

- **Min-heap:** phần tử nhỏ nhất nằm ở gốc, có thể xem bằng `peek()`.
- **Max-heap:** phần tử lớn nhất nằm ở gốc.

Trong Java 17, `java.util.PriorityQueue` mặc định là **min-heap** theo thứ tự tự nhiên. Đưa một `Comparator.reverseOrder()` vào constructor để có hành vi **max-heap** với số nguyên.

Quy tắc của **heap kích thước tối đa k**:

- Để giữ **k phần tử lớn nhất**, dùng **min-heap**. Gốc là phần tử **nhỏ nhất trong nhóm đang giữ** — tức phần tử dễ bị loại nhất.
- Để giữ **k phần tử nhỏ nhất**, dùng **max-heap**. Gốc là phần tử **lớn nhất trong nhóm đang giữ** — cũng là phần tử dễ bị loại nhất.

Đây là điểm dễ nhầm: ta không đặt phần tử tốt nhất ở gốc mà đặt **phần tử kém nhất trong nhóm đã chọn** ở gốc. Nhờ vậy, khi có phần tử mới, chỉ cần so sánh với gốc để quyết định nó có xứng đáng thay thế hay không.

### 2.1. Top-k lớn nhất: quy trình min-heap

Với mỗi giá trị `x` lần lượt đến:

1. Nếu `k=0`, không giữ phần tử nào.
2. Nếu heap đang có ít hơn `k` phần tử, thêm `x` vào heap.
3. Nếu heap đã có đúng `k` phần tử, lấy `threshold = heap.peek()` (giá trị **nhỏ nhất** đang giữ):
   - `x > threshold`: bỏ phần tử nhỏ nhất bằng `poll()` và thêm `x` bằng `offer()`.
   - `x <= threshold`: bỏ qua `x` vì nó không cải thiện nhóm `k` giá trị lớn nhất.

Khi các giá trị bằng nhau, việc bỏ qua phần tử mới bằng ngưỡng **không làm sai multiset giá trị top-k**: cả hai lựa chọn chứa cùng một giá trị. Tuy nhiên, nếu các phần tử là **bản ghi khác nhau có cùng khóa**, cần một quy tắc hòa rõ ràng để quyết định bản ghi nào được chọn; phần 6 sẽ xử lý.

**Pseudocode:**

```text
topKLargest(values, k):
    H = min-heap rỗng
    for each x in values:
        if k == 0:
            continue
        if size(H) < k:
            offer(H, x)
        else if x > peek(H):
            poll(H)       // Bỏ giá trị nhỏ nhất đang giữ
            offer(H, x)
    return H             // H chứa đúng top-k nhưng chưa có thứ tự xuất
```

Nếu cần kết quả giảm dần, lấy các phần tử của heap rồi sắp riêng chúng; **không** giả định `for-each` trên `PriorityQueue` cho kết quả đã sắp.

### 2.2. Theo dõi từng bước

Với `values = [5,1,9,4,7,2,8]`, `k=3`:

| Giá trị mới | Quyết định | Ba giá trị đang giữ (viết theo thứ tự tăng để dễ nhìn) | `peek()` |
|---|---|---|---:|
| `5` | Heap chưa đầy → thêm | `[5]` | 5 |
| `1` | Heap chưa đầy → thêm | `[1,5]` | 1 |
| `9` | Heap chưa đầy → thêm | `[1,5,9]` | 1 |
| `4` | `4>1` → thay 1 bằng 4 | `[4,5,9]` | 4 |
| `7` | `7>4` → thay 4 bằng 7 | `[5,7,9]` | 5 |
| `2` | `2<=5` → bỏ qua | `[5,7,9]` | 5 |
| `8` | `8>5` → thay 5 bằng 8 | `[7,8,9]` | 7 |

Cuối cùng, nhóm đúng là `{7,8,9}`. Nếu yêu cầu xuất giảm dần, trả `[9,8,7]`. Các hàng trong bảng **chỉ biểu diễn các phần tử đã giữ theo thứ tự tăng để minh họa**, không phải thứ tự lưu nội bộ trong mảng heap.

Quan sát hai tính chất:

- Heap **không vượt quá `k` phần tử**, bất kể luồng dài tới đâu.
- Một khi heap đã đầy, **ngưỡng `peek()` không giảm** theo thời gian khi tìm top-k lớn nhất: chỉ thay gốc khi tìm được giá trị lớn hơn. Đây là cơ sở để bỏ qua những giá trị nhỏ hơn ngưỡng.

## 3. Java 17: top-k lớn nhất, có số âm và giá trị trùng

Lưu thành **TopKLargestDemo.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public class TopKLargestDemo {
    static List<Integer> topKLargest(int[] values, int k) {
        Objects.requireNonNull(values, "values");

        if (k < 0 || k > values.length) {
            throw new IllegalArgumentException("Expected 0 <= k <= n");
        }
        if (k == 0) {
            return List.of();
        }

        // Min-heap: phần tử nhỏ nhất trong nhóm top-k ở gốc.
        PriorityQueue<Integer> heap = new PriorityQueue<>();

        for (int value : values) {
            if (heap.size() < k) {
                heap.offer(value);
            } else if (value > heap.peek()) {
                heap.poll();
                heap.offer(value);
            }
        }

        // Duyệt PriorityQueue KHÔNG bảo đảm đã sắp xếp.
        List<Integer> result = new ArrayList<>(heap);
        result.sort(Comparator.reverseOrder());
        return result;
    }

    public static void main(String[] args) {
        int[] values = {4, 1, 9, 2, 8, 9, 3, 6};
        System.out.println("Top 4: " + topKLargest(values, 4));

        int[] mixed = {-4, -1, -7, -1, 3};
        System.out.println("Top 3: " + topKLargest(mixed, 3));
        System.out.println("Top 0: " + topKLargest(values, 0));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 TopKLargestDemo.java
java TopKLargestDemo
```

Stdout:

```text
Top 4: [9, 9, 8, 6]
Top 3: [3, -1, -1]
Top 0: []
```

**Các đặc tính cần hiểu:**

- `[9,9]` và `[-1,-1]` đều giữ nguyên **số lần xuất hiện** của những giá trị được chọn.
- Mảng nguồn **không bị thay đổi**.
- Với `k=0`, hàm trả rỗng ngay và không tạo heap hay đọc giá trị từng phần tử.
- Trong quá trình chọn, heap chỉ chứa tối đa `k` số nguyên; việc sắp kết quả cuối tạo một danh sách có kích thước `k` và tốn thêm thời gian.
- `Objects.requireNonNull` từ chối mảng `null`. Giá trị `k>n` bị từ chối rõ ràng thay vì trả ít hơn k phần tử một cách âm thầm.
- Java tự đóng gói `int` thành `Integer` trong `PriorityQueue<Integer>`; các cấp phát và chi phí bộ nhớ thực tế của đối tượng là một phần quan trọng khi xử lý luồng rất lớn.

### 3.1. Tại sao `peek()` là phần tử lớn thứ k?

Khi đã xử lý ít nhất `k` phần tử, heap chứa đúng **k phần tử lớn nhất trong prefix đã thấy**, tính cả các lần xuất hiện. Trong nhóm đó, phần tử nhỏ nhất chính là **giá trị lớn thứ k** của prefix.

Ví dụ top 4 từ `[4,1,9,2,8,9,3,6]` là `[9,9,8,6]`; gốc min-heap là `6`, tức giá trị lớn thứ tư.

Nếu **chỉ cần giá trị lớn thứ k**, có thể trả `heap.peek()` sau khi xử lý toàn bộ mảng mà không cần sắp danh sách kết quả; điều đó loại bỏ bước `O(k log k)` cho output. Cần `1 <= k <= n`. Khi `k=0`, khái niệm “phần tử thứ 0” không có nghĩa.

### 3.2. Mã độc lập để tìm k-th largest

Lưu thành **KthLargestDemo.java**:

```java
import java.util.PriorityQueue;

public class KthLargestDemo {
    static int kthLargest(int[] values, int k) {
        if (values == null || k < 1 || k > values.length) {
            throw new IllegalArgumentException("Expected 1 <= k <= n");
        }

        PriorityQueue<Integer> heap = new PriorityQueue<>();

        for (int value : values) {
            if (heap.size() < k) {
                heap.offer(value);
            } else if (value > heap.peek()) {
                heap.poll();
                heap.offer(value);
            }
        }
        return heap.peek();
    }

    public static void main(String[] args) {
        int[] values = {5, 2, 9, 1, 9, 3};
        System.out.println("3rd largest: " + kthLargest(values, 3));
        System.out.println("1st largest: " + kthLargest(values, 1));
        System.out.println("6th largest: " + kthLargest(values, 6));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 KthLargestDemo.java
java KthLargestDemo
```

Stdout:

```text
3rd largest: 5
1st largest: 9
6th largest: 1
```

**Lưu ý:** đây là **giá trị lớn thứ k có tính trùng**. Với `[9,9,5]`, phần tử lớn thứ 2 là `9`, không phải `5`. Nếu bài yêu cầu phần tử **phân biệt** lớn thứ k, phải thay đặc tả và cách xử lý giá trị trùng.

## 4. Chứng minh tính đúng bằng bất biến

Cần chứng minh không chỉ rằng heap có kích thước `k`, mà còn rằng **những phần tử ở lại đúng là k giá trị lớn nhất**.

Gọi `S_t` là **đa tập** gồm `t` phần tử đầu tiên của đầu vào và `H_t` là đa tập phần tử heap sau khi đọc `t` phần tử. Mệnh đề:

> Sau `t` phần tử, `H_t` chứa đúng `min(t,k)` giá trị lớn nhất của `S_t`, có tính số lần xuất hiện; nếu có hòa tại ranh giới thì các bản sao cùng giá trị được xem là tương đương về khóa.

### 4.1. Cơ sở

Với `t=0`, cả `S_0` và heap đều rỗng, mệnh đề đúng. Nếu `k=0`, heap luôn rỗng, cũng đúng với định nghĩa top-0.

### 4.2. Khi heap chưa đầy

Nếu `t<k`, heap chứa toàn bộ `t` giá trị đã đọc. Giá trị mới `x` được thêm vào, nên heap chứa toàn bộ `t+1` phần tử đầu tiên; đó chính là `min(t+1,k)=t+1` giá trị lớn nhất có thể giữ.

### 4.3. Khi heap đã đầy

Giả sử heap chứa đúng top-k của `S_t`, và `r=peek(H_t)` là giá trị nhỏ nhất trong nhóm.

- Nếu **`x<=r`**, trong `S_t ∪ {x}` đã có ít nhất `k` phần tử lớn hơn hoặc bằng `r`, nên `x` không thể làm **giá trị** top-k tốt hơn. Giữ nguyên heap vẫn cho đúng multiset k giá trị lớn nhất. Nếu `x=r`, có thể đổi **danh tính** bản sao ranh giới nhưng multiset giá trị không đổi.
- Nếu **`x>r`**, phần tử mới `x` tốt hơn phần tử kém nhất hiện đang giữ. Thay **một** bản sao của `r` bằng `x` tạo đúng top-k của `S_t ∪ {x}`: tất cả phần tử khác trong heap vốn không kém `r`, còn những phần tử bị loại trước đây không lớn hơn ngưỡng cũ. Do đó không có phần tử bị loại nào phải được đưa lại.

Mệnh đề được bảo toàn ở mọi bước. Sau `n` phần tử, heap chứa đúng top-k của toàn bộ đầu vào. **Bước sắp cuối chỉ thay thứ tự**, không làm mất hay thêm phần tử.

### 4.4. Tính dừng

Vòng `for` đọc mỗi phần tử đúng một lần. Mỗi `offer`, `poll`, `peek` trên một heap hữu hạn đều kết thúc. Bộ nhớ heap không vượt quá `k`; quá trình chèn/sàng xuống chỉ đi qua chiều cao `O(log(k+1))`. Vì thế thuật toán kết thúc với mọi mảng hợp lệ hữu hạn.

**Bài học về bất biến:** cấu trúc min-heap chỉ bảo đảm gốc là phần tử nhỏ nhất **trong heap**, không tự bảo đảm heap là top-k của **tất cả đầu vào**. Để chứng minh lựa chọn đúng, phải thêm bất biến về k phần tử lớn nhất đã thấy và giải thích hai trường hợp `x<=r` / `x>r`.

## 5. Top-k nhỏ nhất: đảo hướng của heap

Khi cần giữ **k giá trị nhỏ nhất**, phần tử dễ loại nhất trong nhóm là **lớn nhất**. Dùng **max-heap kích thước k**:

- Nếu heap chưa đầy, thêm phần tử mới.
- Nếu đã đầy và `x < heap.peek()`, bỏ giá trị **lớn nhất** trong nhóm rồi thêm `x`.
- Nếu `x >= heap.peek()`, bỏ qua.
- Muốn trả danh sách tăng dần, sắp riêng `k` phần tử giữ lại.

Lưu thành **TopKSmallestDemo.java**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public class TopKSmallestDemo {
    static List<Integer> topKSmallest(int[] values, int k) {
        Objects.requireNonNull(values, "values");
        if (k < 0 || k > values.length) {
            throw new IllegalArgumentException("Expected 0 <= k <= n");
        }

        // Max-heap: gốc là phần tử LỚN NHẤT đang giữ.
        PriorityQueue<Integer> heap =
                new PriorityQueue<>(Comparator.reverseOrder());

        for (int value : values) {
            if (heap.size() < k) {
                heap.offer(value);
            } else if (k > 0 && value < heap.peek()) {
                heap.poll();
                heap.offer(value);
            }
        }

        List<Integer> result = new ArrayList<>(heap);
        Collections.sort(result);
        return result;
    }

    public static void main(String[] args) {
        int[] values = {7, -3, 2, 2, 10, 0, -3, 9};

        System.out.println("Smallest 3: " + topKSmallest(values, 3));
        System.out.println("Smallest 1: " + topKSmallest(values, 1));
        System.out.println("Smallest 0: " + topKSmallest(values, 0));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TopKSmallestDemo.java
java TopKSmallestDemo
```

Stdout:

```text
Smallest 3: [-3, -3, 0]
Smallest 1: [-3]
Smallest 0: []
```

Điều kiện `k > 0` ở nhánh so sánh tránh gọi `peek()` trên heap rỗng khi `k=0`. Đây là một cách viết khác với cách **trả sớm** ở ví dụ top-k lớn nhất.

Nếu chỉ cần **phần tử nhỏ thứ k**, khi heap đã chứa k phần tử thì `heap.peek()` là giá trị lớn nhất **trong k giá trị nhỏ nhất**, tức phần tử nhỏ thứ k. Quy nạp chứng minh tương tự top-k lớn nhất, chỉ đảo hướng bất đẳng thức và kiểu heap.

## 6. Top-k bản ghi khi điểm số bằng nhau

Với `int[]`, các giá trị bằng nhau không có danh tính riêng. Với dữ liệu thực tế — người chơi, giao dịch, kết quả tìm kiếm, sự kiện — **hai bản ghi có cùng điểm không nhất thiết hoán đổi tùy ý được**.

Giả sử bài toán yêu cầu:

1. **Điểm cao hơn tốt hơn**.
2. Nếu điểm bằng nhau, **bản ghi đến sớm hơn tốt hơn**.
3. Xuất kết quả theo điểm giảm, rồi thời điểm đến tăng.

Ta cần một quan hệ thứ tự **tổng quát, nhất quán** để xác định bản ghi nào là “tệ nhất” ở gốc heap.

Đặt `arrival` là chỉ số tăng dần theo lúc nhận, không trùng nhau. Trong **min-heap của k bản ghi tốt nhất**, comparator **tệ hơn đứng trước**:

- `score` nhỏ hơn đứng trước;
- khi `score` bằng nhau, `arrival` **lớn hơn** (đến muộn hơn) đứng trước.

Khi có bản ghi mới, chỉ thay gốc nếu comparator cho biết bản ghi mới **tốt hơn** gốc. Nếu tương đương hoàn toàn theo quy tắc thứ tự, có thể giữ bản ghi cũ để không cập nhật vô ích.

### 6.1. Java 17: lựa chọn xác định ở ranh giới hòa

Lưu thành **TopKRecordsDemo.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public class TopKRecordsDemo {
    record Item(String id, int score, int arrival) {
        @Override
        public String toString() {
            return id + ":" + score;
        }
    }

    static List<Item> topK(Item[] items, int k) {
        Objects.requireNonNull(items, "items");
        if (k < 0 || k > items.length) {
            throw new IllegalArgumentException("Expected 0 <= k <= n");
        }
        if (k == 0) {
            return List.of();
        }

        // Tệ nhất ở đầu: điểm thấp; nếu hòa, người đến muộn.
        Comparator<Item> worstFirst = (a, b) -> {
            int cmp = Integer.compare(a.score(), b.score());
            if (cmp != 0) {
                return cmp;
            }
            return Integer.compare(b.arrival(), a.arrival());
        };

        PriorityQueue<Item> heap = new PriorityQueue<>(worstFirst);
        for (Item item : items) {
            Objects.requireNonNull(item, "item");
            if (heap.size() < k) {
                heap.offer(item);
            } else if (worstFirst.compare(item, heap.peek()) > 0) {
                heap.poll();
                heap.offer(item);
            }
        }

        List<Item> result = new ArrayList<>(heap);
        result.sort(worstFirst.reversed()); // Điểm giảm; đến sớm trước.
        return result;
    }

    public static void main(String[] args) {
        Item[] events = {
            new Item("A", 90, 0),
            new Item("B", 95, 1),
            new Item("C", 90, 2),
            new Item("D", 95, 3),
            new Item("E", 88, 4)
        };
        System.out.println("Top 3: " + topK(events, 3));

        Item[] ties = {
            new Item("A", 10, 0),
            new Item("B", 10, 1),
            new Item("C", 10, 2)
        };
        System.out.println("Top 2 ties: " + topK(ties, 2));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TopKRecordsDemo.java
java TopKRecordsDemo
```

Stdout:

```text
Top 3: [B:95, D:95, A:90]
Top 2 ties: [A:10, B:10]
```

**Vì sao A được giữ thay vì C ở top 3 đầu?** Hai bản ghi cùng điểm `90`, nhưng A đến lúc `0`, sớm hơn C đến lúc `2`. Theo quy tắc hòa, A tốt hơn C. Ở ví dụ thứ hai, top 2 đều có điểm `10`, chọn hai bản ghi đến sớm A và B.

**Điều kiện cần của mã:** `arrival` phải phản ánh chính xác thứ tự đến và **duy nhất** cho mỗi bản ghi; danh sách không chứa `null`. Nếu người dùng có thể thay `arrival` hoặc dùng timestamp trùng, hãy thêm khóa phụ cuối cùng (ID duy nhất) để tạo thứ tự xác định. Comparator dùng `Integer.compare`, không dùng `a.score()-b.score()` vì phép trừ có thể tràn khi gặp `Integer.MIN_VALUE` hoặc `Integer.MAX_VALUE`.

**Điểm tinh tế:** “ổn định” khi **sắp xếp toàn bộ** nghĩa là không đảo thứ tự phần tử bằng khóa. Khi **chọn top-k**, trước tiên phải định nghĩa rõ **ai được chọn khi hòa đúng ở ranh giới k**; chỉ yêu cầu sắp output ổn định không quyết định bản ghi bị loại. Quy tắc đến sớm trước làm việc chọn trở nên xác định.

### 6.2. Khi đề yêu cầu “lấy tất cả ai bằng ngưỡng”

Không phải bài toán nào cũng yêu cầu **đúng k bản ghi**. Nếu yêu cầu “tất cả bản ghi có điểm **ít nhất bằng** điểm ở hạng k”, số kết quả có thể **lớn hơn k** khi nhiều người cùng điểm với ngưỡng.

Một heap chỉ chứa k bản ghi là đủ để **tìm ngưỡng điểm**, nhưng nếu muốn trả **tất cả** những bản ghi hòa ngưỡng, phải có cách lưu lại/phát lại dữ liệu nguồn hoặc giữ thêm các bản ghi bằng ngưỡng. Với luồng chỉ đọc một lần, nhu cầu xuất toàn bộ các bản ghi hòa có thể buộc dùng thêm bộ nhớ vượt `O(k)`, hoặc cần một lần đọc thứ hai. Không được khẳng định thuật toán giới hạn đúng k phần tử đã giải luôn bài “gồm toàn bộ hòa ngưỡng”.

## 7. Streaming top-k: không cần giữ toàn bộ luồng

Với log sự kiện, giao dịch, cảm biến hoặc điểm số đến dần, ta thường không biết trước `n` và không muốn lưu tất cả. Một min-heap kích thước k có thể cập nhật **ngay khi nhận mỗi giá trị**.

Điều kiện vận hành:

- Bộ nhớ giữ heap là `O(k)` dù đã đọc hàng triệu phần tử.
- Mỗi giá trị mới chỉ cần xử lý bằng phép `peek`, `poll`, `offer`, không cần sắp xếp lại toàn bộ lịch sử.
- Tại thời điểm đã đọc `t` phần tử, bộ theo dõi giữ `min(t,k)` giá trị lớn nhất đã thấy.
- Sau khi đọc chưa đủ k, `peek()` chỉ là giá trị nhỏ nhất **đã thấy**, chưa thể gọi đó là “phần tử lớn thứ k” của luồng.
- Mỗi lần muốn hiển thị **danh sách đã sắp**, tạo snapshot và sắp riêng k phần tử. Nếu làm sau **mọi lần offer**, chi phí xuất kết quả lặp lại có thể rất lớn; chỉ lấy snapshot khi cần.

### 7.1. Java 17: bộ theo dõi cập nhật dần

Lưu thành **TopKStreamingDemo.java**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class TopKStreamingDemo {
    static final class TopKTracker {
        private final int limit;
        private final PriorityQueue<Integer> heap =
                new PriorityQueue<>();

        TopKTracker(int limit) {
            if (limit < 0) {
                throw new IllegalArgumentException("Negative limit");
            }
            this.limit = limit;
        }

        void offer(int value) {
            if (limit == 0) {
                return;
            }
            if (heap.size() < limit) {
                heap.offer(value);
            } else if (value > heap.peek()) {
                heap.poll();
                heap.offer(value);
            }
        }

        List<Integer> snapshotDescending() {
            List<Integer> result = new ArrayList<>(heap);
            result.sort(Comparator.reverseOrder());
            return result;
        }
    }

    public static void main(String[] args) {
        TopKTracker tracker = new TopKTracker(3);

        for (int value : new int[]{5, 1, 7}) {
            tracker.offer(value);
        }
        System.out.println("After 3: " + tracker.snapshotDescending());

        for (int value : new int[]{4, 9, -2}) {
            tracker.offer(value);
        }
        System.out.println("After 6: " + tracker.snapshotDescending());

        TopKTracker empty = new TopKTracker(0);
        empty.offer(99);
        System.out.println("Limit 0: " + empty.snapshotDescending());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 TopKStreamingDemo.java
java TopKStreamingDemo
```

Stdout:

```text
After 3: [7, 5, 1]
After 6: [9, 7, 5]
Limit 0: []
```

**Ý nghĩa:** trước khi xử lý `4,9,-2`, top 3 là `[7,5,1]`. Số `4` thay `1`, số `9` thay `4`, còn `-2` bị bỏ qua. Kết quả cuối cùng giữ đúng `[9,7,5]` dù không lưu toàn bộ sáu số.

**Giới hạn:** bộ theo dõi này xử lý **luồng chỉ thêm**, không hỗ trợ xóa bất kỳ phần tử lịch sử nào hay cửa sổ trượt (*sliding window*) một cách tự động. Khi một giá trị lớn hết hạn khỏi cửa sổ, giá trị từng bị bỏ qua trước đây có thể cần trở lại; một heap top-k thông thường không còn giữ nó. Bài top-k trong cửa sổ trượt cần thiết kế khác (chẳng hạn multiset/cấu trúc cây và quản lý phần tử hết hạn).

**Lưu ý đồng thời:** `PriorityQueue` không được thiết kế để nhiều luồng sửa đồng thời mà không có đồng bộ hóa. Nếu ứng dụng nhiều luồng cùng gọi `offer` hoặc `snapshotDescending`, phải bảo vệ trạng thái bằng lock hoặc xử lý các sự kiện trên một luồng sở hữu dữ liệu; không tự suy ra thread-safety từ việc dùng class Java chuẩn.

## 8. Phân tích độ phức tạp và chi phí thực tế

Ký hiệu `n` là tổng phần tử đầu vào, `k` là giới hạn heap (`0<=k<=n` với mảng tĩnh).

### 8.1. Chi phí duy trì heap

Heap chứa **không quá k** phần tử:

- `peek()` lấy gốc trong `O(1)`.
- `offer()`/`poll()` có chặn xấu nhất `O(log(k+1))` cho kích thước heap không vượt k.
- Mỗi phần tử mới được xem xét một lần; trong trường hợp cần thay thế, có tối đa một `poll` và một `offer`.

Vì vậy chi phí duy trì top-k là **`O(n log(k+1))`** cho `k>=1`, với `k=1` trở thành `O(n)` vì log 2 là hằng số. Riêng trường hợp `k=0` được cài đặt trả ngay: thời gian `O(1)` sau khi kiểm tra tham số. Nếu có bước duyệt đầu vào để kiểm tra điều kiện khác, chi phí kiểm tra đó phải tính thêm.

Bộ nhớ làm việc là **`O(k)`** cho heap, không tính mảng nguồn. Với `PriorityQueue<Integer>`, ngoài `k` tham chiếu còn có thể có các đối tượng `Integer` do boxing; Big-O vẫn `O(k)` nhưng hệ số bộ nhớ/cấp phát đáng xem xét.

### 8.2. Nếu cần danh sách top-k có thứ tự

Tạo một bản sao heap rồi sắp `k` phần tử mất **`O(k log(k+1))` thời gian** và **`O(k)` bộ nhớ đầu ra**. Tổng:

`O(n log(k+1) + k log(k+1))`.

Với `k<=n`, chặn này thường viết gọn `O(n log(k+1))`; nhưng tách hai thành phần giúp hiểu chi phí khi liên tục xuất snapshot. Nếu **chỉ cần giá trị lớn thứ k**, không cần sắp đầu ra, cứ lấy `peek()` sau lượt cuối trong `O(1)`.

### 8.3. Những trường hợp biên

| Trường hợp | Hành vi | Chi phí |
|---|---|---|
| `k=0` | Trả rỗng/không giữ gì | `O(1)` nếu trả sớm |
| `k=1` | Chỉ giữ max hoặc min đã thấy | `O(n)` thời gian, `O(1)` bộ nhớ |
| `1<k<<n` | Heap nhỏ, nhiều phần tử bị bỏ qua | Chọn tốt cho dữ liệu rất lớn |
| `k=n` | Giữ tất cả phần tử | Heap `O(n)` bộ nhớ; duy trì `O(n log n)` theo cách chèn từng phần tử |
| `k>n` | API mảng ví dụ báo lỗi | Đề khác có thể quy định “lấy tối đa k” |
| Nhiều khóa bằng nhau | Phải nêu rõ tính trùng và quy tắc hòa | Có thể chọn bản sao khác dù cùng giá trị |

`PriorityQueue` có thể tự mở rộng vùng lưu trữ khi `offer`, nhưng số phần tử còn giữ được kiểm soát bởi k. Nếu một luồng tiếp tục chạy vô hạn, tổng thời gian tích lũy vẫn tăng theo số sự kiện, chỉ **bộ nhớ trạng thái** được giới hạn.

### 8.4. Nếu k rất nhỏ hoặc rất lớn

- `k=1`: chỉ cần một biến `best`, không nhất thiết tạo heap; mỗi phần tử so sánh với `best`.
- `k` nhỏ hơn `n` nhiều bậc: heap giới hạn kích thước tránh sắp toàn bộ và có lợi cho streaming.
- `k≈n`: bộ nhớ gần `O(n)`, thời gian `O(n log n)`; sắp xếp toàn bộ có thể đơn giản hơn hoặc có hằng số tốt hơn.
- `k` rất lớn mà RAM không đủ: heap không tạo ra phép màu; `O(k)` vẫn có thể không phù hợp. Có thể dùng các thuật toán chọn trên dữ liệu ngoài RAM hoặc kỹ thuật nhiều lượt tùy điều kiện.

## 9. So sánh heap top-k với sort và quickselect

| Phương pháp | Muốn lấy top-k | Thời gian điển hình | Bộ nhớ/phù hợp |
|---|---|---|---|
| **Sắp xếp toàn bộ** | Sắp cả `n`, lấy `k` đầu | `O(n log n)` với sort so sánh phù hợp | Dễ làm, có sẵn kết quả đã sắp |
| **Heap giới hạn k** | Chỉ giữ k tốt nhất trong lúc duyệt | `O(n log(k+1))`, thêm sort k nếu cần | **`O(k)`**, hỗ trợ dữ liệu đến dần |
| **Quickselect/partition** | Tìm ranh giới hạng k, tách nhóm | Kỳ vọng `O(n)` với pivot ngẫu nhiên/phân phối thích hợp; bản đơn giản có thể xấu nhất `O(n²)` | Thường làm trên mảng tại chỗ; không online theo cách heap |
| **Xây heap trên toàn bộ n** | Trích k phần tử lớn nhất từ max-heap | Heapify `O(n)` + k lần lấy `O(k log n)` | Cần giữ/được phép sửa n phần tử |
| **Đếm/phân phối khóa** | Trực tiếp đếm miền giá trị hạn chế | Phụ thuộc kích thước miền `K` | Có lợi khi miền khóa nhỏ và đã biết |

**Phân biệt thao tác:** quickselect thường chỉ bảo đảm **phân hoạch** sao cho nhóm top-k đã nằm phía phù hợp, **chưa nhất thiết có thứ tự bên trong nhóm**. Nếu cần xuất top-k theo thứ tự, còn phải sắp `k` phần tử được chọn, tốn thêm `O(k log k)` trong mô hình so sánh.

Nếu chỉ muốn ngưỡng k-th và toàn bộ mảng đã nằm trong bộ nhớ, quickselect có thể hiệu quả hơn heap khi có điều kiện và chấp nhận mô hình chi phí của nó. Nếu luồng dữ liệu quá lớn để giữ hết, heap giới hạn k có ưu điểm cấu trúc rõ rệt: **xử lý một lần, O(k) bộ nhớ làm việc**.

**Không nhầm với k-way merge:** trộn `k` dãy đã sắp xếp cũng dùng heap kích thước k, nhưng mỗi phần tử heap là **đầu của một nguồn**, dùng để chọn phần tử nhỏ nhất tiếp theo **trên nhiều nguồn**; bài này dùng heap để **giữ k ứng viên tốt nhất** trong số các phần tử đã thấy. Cùng cấu trúc dữ liệu, bất biến và ý nghĩa của k khác nhau.

## 10. Các biến thể và quy tắc đầu vào

### 10.1. “Top k phần tử” khác “top k giá trị phân biệt”

Ví dụ dãy `[10,10,8,7]`:

```text
Top 2 theo lần xuất hiện: [10,10]
Top 2 phân biệt:           [10,8]
Giá trị lớn thứ 2:         10
Giá trị phân biệt lớn thứ 2: 8
```

Muốn top-k **phân biệt**, phải tránh lưu hai bản sao cùng giá trị. Có thể kết hợp heap với tập chứa các giá trị đang được chọn; nếu muốn thống kê dữ liệu toàn phần hay biết tần suất, còn cần cấu trúc theo dõi riêng. Phải chứng minh lại bất biến theo **tập giá trị phân biệt**, không bê nguyên chứng minh về đa tập khi số lần xuất hiện không còn được tính.

Một `HashSet` ghi nhận **mọi giá trị từng gặp** có thể chiếm `O(u)` bộ nhớ với `u` là số giá trị phân biệt đầu vào, không còn là `O(k)` chỉ vì heap giới hạn k. Nếu dùng set chỉ đồng bộ với các giá trị **đang giữ** trong heap, phải cập nhật set chính xác khi `poll()` hoặc `offer()` và kiểm tra phần tử trùng trước khi thêm.

### 10.2. Top-k theo điểm tổng hợp

Nếu “tốt hơn” được định nghĩa bằng nhiều trường như `(score DESC, timestamp ASC, id ASC)`, hãy viết **một comparator nhất quán** theo thứ tự ưu tiên đó. Heap cần comparator ngược, đưa ứng viên **kém nhất** lên gốc; khi xuất kết quả, đảo lại thứ tự.

Nếu điểm là số thực, cần chỉ rõ cách xử lý `NaN`, `Infinity`, số âm 0 và dương 0; dùng comparator chuẩn như `Double.compare` với chính sách nghiệp vụ rõ ràng thay vì phép trừ dấu phẩy động rồi ép về `int`.

### 10.3. Top-k theo độ đo khoảng cách

Các bài “k điểm gần gốc tọa độ nhất” thường dùng **max-heap** giữ k khoảng cách nhỏ nhất, nhưng cần cẩn thận khi tính `x*x + y*y`: với `int`, bình phương có thể tràn. Nếu miền tọa độ phù hợp, ép sang `long` trước khi nhân (`(long)x*x`); nếu dữ liệu lớn đến mức vượt `long`, dùng so sánh/kiểu số thích hợp khác. Thường không cần tính căn bậc hai vì so sánh bình phương khoảng cách bảo toàn thứ tự các khoảng cách không âm.

### 10.4. Top-k theo tần suất

Muốn “k giá trị xuất hiện thường xuyên nhất”, cần **đếm tần suất trước** bằng `Map<Value,Integer>` rồi chọn k cặp `(value,count)` có count cao nhất bằng min-heap. Bộ nhớ toàn thuật toán có thể là `O(u+k)` với `u` giá trị phân biệt, không phải `O(k)` nếu map đếm phải giữ hết u tần suất. Bài toán heavy hitters trên luồng rất lớn có thuật toán xấp xỉ và giới hạn khác; không được gọi kết quả xấp xỉ là top-k chính xác nếu không có bảo đảm.

### 10.5. Top-k theo thời gian/cửa sổ trượt

Nếu bài toán nói “top-k trong **10 phút gần nhất**” hoặc “top-k của **w phần tử mới nhất**”, trạng thái phải biết phần tử nào hết hạn. Heap giới hạn k chỉ giữ những phần tử tốt nhất **từ đầu luồng** nên không đủ nếu phần tử lớn nhất hết hạn và phần tử từng bị bỏ qua trở nên quan trọng. Cần bổ sung cấu trúc cho tất cả phần tử đang còn trong cửa sổ, cơ chế xóa/lazy deletion, hoặc cấu trúc cân bằng quản lý hai nhóm. Khi ấy bộ nhớ có thể phụ thuộc `w`, không chỉ k.

## 11. Các lỗi thường gặp khi cài bằng `PriorityQueue`

### Lỗi 1: Dùng max-heap để giữ top-k lớn nhất

Một max-heap giữ k phần tử có gốc **lớn nhất**. Nếu loại gốc khi quá k, ta đang loại phần tử tốt nhất, khiến tập kết quả sai. **Top-k lớn nhất cần min-heap** để loại phần tử **nhỏ nhất** trong nhóm.

### Lỗi 2: Không giới hạn kích thước

Nếu chỉ `offer` tất cả n phần tử rồi `poll` k phần tử, heap có kích thước `O(n)` và không còn lợi thế bộ nhớ `O(k)`. Có thể đúng kết quả trong vài biến thể, nhưng **không** đáp ứng yêu cầu heap kích thước giới hạn.

### Lỗi 3: Tưởng `PriorityQueue` được sắp hoàn toàn

Heap chỉ bảo đảm phần tử ưu tiên nhất ở `peek()`/`poll()`. Iterator, `toArray()` và `new ArrayList<>(heap)` **không có thứ tự sắp xếp bảo đảm**. Muốn list giảm/tăng, gọi `sort` trên bản sao hoặc liên tục `poll` theo thứ tự thích hợp.

### Lỗi 4: Thiếu chính sách xử lý hòa ngưỡng

Với giá trị số giống nhau, chọn bất kỳ bản sao nào cho cùng multiset giá trị. Với bản ghi, chọn sai danh tính ở biên k làm kết quả khác nhau qua lần chạy. Dùng khóa phụ như `arrival` hoặc ID duy nhất để có comparator xác định.

### Lỗi 5: Không kiểm tra `k=0`

Nếu heap rỗng, `peek()` trả `null` và phép unboxing so sánh với `int` có thể ném `NullPointerException`. Hãy trả rỗng sớm hoặc kiểm tra `k>0` trước khi đọc gốc.

### Lỗi 6: Không định nghĩa `k>n` hoặc `k<0`

API có thể từ chối, lấy tối đa số phần tử hiện có, hoặc chờ đến khi luồng đủ k; mỗi cách hợp lệ cho một bài toán khác nhau. Nhưng phải **đặt hợp đồng rõ ràng**, không tự chọn rồi quên báo.

### Lỗi 7: So sánh bằng phép trừ

Không viết `return a.score()-b.score()` để so sánh mọi số nguyên `int`, vì có thể tràn và vi phạm tính bắc cầu. Dùng `Integer.compare`, `Comparator.comparingInt` hoặc `Comparator.reverseOrder()`.

### Lỗi 8: Nhầm thứ tự xuất với thứ tự ưu tiên nội bộ

Min-heap top-k lớn nhất có gốc là **phần tử lớn thứ k**, không phải lớn thứ nhất. Nếu muốn in top-k giảm dần, sắp bản sao trước; nếu cứ `poll` min-heap sẽ nhận giá trị từ nhỏ đến lớn trong nhóm được chọn.

### Lỗi 9: Phân tích nhầm bộ nhớ vì đã sắp output

Trạng thái heap giữ `O(k)` phần tử, nhưng `snapshot` thêm mảng/lists `O(k)` và phép sắp `O(k log k)`. Nếu lưu toàn bộ các snapshot theo thời gian, tổng bộ nhớ có thể tăng vượt xa `O(k)`.

### Lỗi 10: Coi heap giới hạn là cấu trúc xóa tùy ý

`PriorityQueue.remove(Object)` không phải phép xóa một phần tử bất kỳ với cùng độ phức tạp như `poll()`; trong Java việc tìm phần tử cần xóa có thể tốn tuyến tính theo kích thước heap. Với cửa sổ trượt hoặc phần tử thay đổi điểm, cần cấu trúc/index hoặc lazy deletion phù hợp.

### Lỗi 11: Dùng comparator thay đổi theo thời gian

Heap phụ thuộc một thứ tự nhất quán. Nếu đối tượng bên trong heap bị sửa trường `score` sau khi chèn, quan hệ heap có thể không còn đúng vì `PriorityQueue` không tự tái sắp. Cần xóa/cập nhật/chèn lại đúng cách, hoặc lưu bản ghi/khóa bất biến.

### Lỗi 12: Không phân biệt bài toán chính xác với xấp xỉ

“Top-k” thông thường nghĩa là chính xác theo toàn bộ đầu vào. Nếu dùng thuật toán phác họa/ước lượng trên luồng (như heavy hitters), phải công bố sai số và điều kiện bảo đảm. Không được lấy kết quả xấp xỉ rồi gắn nhãn chính xác mà không chứng minh.

## 12. Kiểm thử có chủ đích

| Dãy | k | Top-k lớn nhất đã sắp | Mục đích |
|---|---:|---|---|
| `[7,2,9,4,9,1,6]` | 3 | `[9,9,7]` | Giữ trùng; ngưỡng lớn thứ k là 7 |
| `[5]` | 1 | `[5]` | Một phần tử |
| `[5]` | 0 | `[]` | Không được gọi `peek()` trên heap rỗng |
| `[-9,-1,-5]` | 2 | `[-1,-5]` | Toàn số âm |
| `[3,3,3,3]` | 2 | `[3,3]` | Toàn bằng nhau |
| `[1,2,3,4]` | 4 | `[4,3,2,1]` | `k=n`, không mất phần tử |
| `[]` | 0 | `[]` | Đầu vào rỗng |
| `[1,2]` | 3 | Báo lỗi theo API tĩnh | `k>n` không hợp lệ |

Với **top-k nhỏ nhất**, có thể đối chiếu cách làm với phép sắp tăng toàn bộ đầu vào rồi lấy `k` giá trị đầu. Với **top-k lớn nhất**, so sánh với phép sắp giảm toàn bộ rồi lấy k phần tử đầu. Đây là một **oracle kiểm thử** tốt cho đầu vào nhỏ và dữ liệu ngẫu nhiên, dù không phải cách chọn tối ưu cho bài toán lớn.

Cần kiểm tra thêm:

- Dữ liệu có nhiều giá trị bằng ngưỡng.
- Kích thước `k=1`, `k=n`, `k=0` và dữ liệu trống.
- Các giá trị `Integer.MIN_VALUE` và `Integer.MAX_VALUE` nếu comparator dùng số nguyên.
- Các bản ghi hòa điểm nhưng khác thứ tự đến, kiểm tra đúng **danh tính được giữ**.
- Đảm bảo heap chưa bao giờ có hơn k phần tử.
- Đối chiếu kết quả **đa tập**: tần suất của mỗi giá trị trong top-k phải đúng với việc sắp và lấy k phần tử.

## 13. Bài tập luyện tập có đáp án

### Bài 1 — Theo dõi min-heap

Cho `a=[10,3,8,12,1,9,6]`, `k=3`. Sau mỗi phần tử, viết nhóm top-3 đang giữ và ngưỡng.

**Đáp án minh họa (nhóm được viết tăng dần):**

```text
10  -> [10]       ngưỡng 10
3   -> [3,10]     ngưỡng 3
8   -> [3,8,10]   ngưỡng 3
12  -> [8,10,12]  ngưỡng 8
1   -> [8,10,12]  ngưỡng 8
9   -> [9,10,12]  ngưỡng 9
6   -> [9,10,12]  ngưỡng 9
```

Top-3 cuối cùng nếu xuất giảm dần là `[12,10,9]`.

### Bài 2 — Chọn đúng loại heap

Muốn giữ 5 **giá trị nhỏ nhất** của một luồng dài hàng triệu số, heap nào đặt phần tử cần loại nhanh nhất tại gốc?

**Đáp án:** **max-heap** kích thước 5. Gốc là giá trị **lớn nhất trong 5 giá trị nhỏ nhất đang giữ**; chỉ thay nếu giá trị mới nhỏ hơn gốc.

### Bài 3 — Giá trị thứ k và trùng

Dãy `[8,8,8,5,3]`, `k=3`. Giá trị lớn thứ 3 là bao nhiêu? Ba giá trị phân biệt lớn nhất là gì?

**Đáp án:** lớn thứ 3 theo lần xuất hiện là `8`; ba giá trị **phân biệt** lớn nhất là `[8,5,3]`. Hai yêu cầu không thể dùng chung một đặc tả không đổi.

### Bài 4 — Quy tắc hòa bản ghi

Ba bản ghi có cùng điểm `90`: `(A,arrival=1)`, `(B,arrival=2)`, `(C,arrival=3)`. Nếu `k=2` và khi hòa ưu tiên đến sớm, chọn ai?

**Đáp án:** A và B. Comparator của heap đưa **B hoặc C, tùy nhóm đã giữ** lên gốc theo `arrival` lớn hơn; khi C đến, C kém hơn B nên không thay được. Sau khi sắp kết quả, thứ tự A rồi B.

### Bài 5 — Phân tích tài nguyên

Cho `n=10^7`, `k=20`, chỉ cần 20 giá trị lớn nhất trên một luồng.

**Đáp án:** min-heap giữ tối đa 20 giá trị, xử lý `O(n log(21))` theo mô hình heap và bộ nhớ trạng thái `O(20)`, thay vì giữ cả `10^7` giá trị trong RAM chỉ để sắp. Nếu phải xuất top-20 giảm dần, sắp thêm 20 giá trị, chi phí rất nhỏ so với đọc toàn luồng.

### Bài 6 — Cửa sổ trượt

Cho top-2 của các giá trị trong **ba phần tử mới nhất**. Vì sao heap top-k chỉ thêm như các ví dụ trên là chưa đủ?

**Đáp án:** khi giá trị lớn bị loại khỏi cửa sổ, các giá trị đã bỏ qua trong quá khứ nhưng **vẫn còn nằm trong cửa sổ** có thể phải vào top-2. Heap chỉ lưu hai giá trị tốt nhất toàn lịch sử, không giữ đầy đủ ứng viên của cửa sổ để khôi phục.

### Bài 7 — So sánh quickselect và heap

Có mảng lớn đã nằm hoàn toàn trong RAM, cần ngưỡng phần tử lớn thứ k **một lần**, không cần lưu danh sách top-k để truy vấn liên tục. Vì sao quickselect đáng cân nhắc?

**Đáp án:** quickselect có thời gian kỳ vọng `O(n)` khi pivot chọn phù hợp và có thể phân hoạch ngay trong mảng; heap top-k tốn `O(n log(k+1))` và giữ `O(k)` phần tử. Đổi lại quickselect không trực tiếp là thuật toán **streaming**, có thể sửa mảng và bản triển khai đơn giản có trường hợp xấu `O(n²)`.

## 14. Checklist triển khai theo đề bài

Trước khi viết code top-k, hãy xác định:

1. **“Tốt nhất” nghĩa là gì?** Lớn nhất, nhỏ nhất, điểm nhiều trường hay khoảng cách?
2. **Trùng lặp có được tính không?** K giá trị theo lần xuất hiện hay k giá trị phân biệt?
3. **Hòa ở ranh giới k xử lý ra sao?** Chọn bất kỳ bản ghi, ưu tiên đến sớm, ID nhỏ hơn, hay trả tất cả các bản ghi bằng ngưỡng?
4. **Kết quả cần thứ tự không?** Chỉ cần k-th hay cần danh sách đã sắp? Một heap không tự cho thứ tự lặp.
5. **Dữ liệu nằm ở đâu?** Mảng tĩnh, luồng chỉ đọc một lần, hay cửa sổ trượt có xóa phần tử?
6. **K có hợp lệ không?** Xử lý `k=0`, `k=1`, `k=n`, `k>n`, `n=0` theo hợp đồng.
7. **Chọn heap nào?** Top-k lớn nhất → min-heap; top-k nhỏ nhất → max-heap.
8. **Comparator có an toàn không?** Không dùng phép trừ số nguyên dễ tràn; phải có thứ tự nhất quán, khóa trong heap không bị sửa ngầm.
9. **Giới hạn bộ nhớ và thời gian?** Chọn heap `O(k)` để tránh giữ toàn bộ luồng; thêm chi phí sắp output nếu có.
10. **Đã chứng minh bất biến chưa?** Sau mỗi prefix, heap chứa đúng `min(k,t)` phần tử tốt nhất đã thấy; gốc là phần tử kém nhất trong nhóm; chỉ thay khi ứng viên mới tốt hơn.

**Ghi nhớ:** một **heap kích thước giới hạn** không sắp xếp mọi phần tử. Nó giữ **chính xác k ứng viên tốt nhất đã thấy**, đưa **ứng viên kém nhất trong nhóm** lên gốc để loại bỏ nhanh khi gặp phần tử tốt hơn. Cách này đặc biệt hữu ích với **k nhỏ, n lớn hoặc dữ liệu đến dần**. Muốn áp dụng đúng phải xác định rõ **thứ tự, giá trị trùng, cách hòa ở ranh giới k** và phân biệt công việc **chọn** với công việc **sắp kết quả**.
