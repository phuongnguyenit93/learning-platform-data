# Bài toán phần tử nhỏ thứ k và quy ước đánh số

**Bài toán phần tử nhỏ thứ k** (k-th smallest element, còn gọi là *k-th order statistic*) yêu cầu tìm giá trị đứng ở vị trí thứ `k` nếu các phần tử được xếp theo thứ tự không giảm. Ta thường cần **giá trị** đó, không nhất thiết phải sắp xếp toàn bộ dãy hoặc trả lại một bản dãy có thứ tự.

Điều dễ nhầm nhất không phải phép so sánh, mà là **quy ước đánh số**: trong lời đề bài, “nhỏ thứ `k`” thường đếm từ **1**; trong mảng Java, chỉ số đếm từ **0**. Ngoài ra phải xác định **phần tử trùng nhau có được tính nhiều lần hay chỉ tính giá trị phân biệt**.

Ví dụ với dãy chưa sắp:

```text
Đầu vào:           [7, 2, 7, 4, 2, 9]
Sau khi xếp tăng:  [2, 2, 4, 7, 7, 9]
Thứ hạng (1-based): 1  2  3  4  5  6
Chỉ số   (0-based): 0  1  2  3  4  5
```

Nếu **tính từng lần xuất hiện**, phần tử nhỏ thứ `3` là `4`, nhỏ thứ `2` là `2` và nhỏ thứ `5` là `7`. Nếu bài toán hỏi **giá trị phân biệt nhỏ thứ `2`**, kết quả lại là `4`, vì những giá trị khác nhau theo thứ tự là `[2,4,7,9]`.

Hai cách hiểu này **không tương đương**, đặc biệt khi đầu vào chứa nhiều phần tử trùng. Phải quyết định rõ ngay từ hợp đồng bài toán trước khi chọn thuật toán.

## 1. Định nghĩa chính xác và quy ước đánh số

Cho mảng `a` có `n` phần tử, `n>0`. Xét một hoán vị `b` của các phần tử trong `a`, đã được sắp theo thứ tự không giảm:

```text
b[0] <= b[1] <= ... <= b[n - 1]
```

Trong quy ước **thứ hạng bắt đầu từ 1**, phần tử nhỏ thứ `k` là:

```text
kthSmallest(a, k) = b[k - 1], với 1 <= k <= n.
```

Đây là phép **chọn** (selection), không phải bản thân phép sắp xếp. Một thuật toán chọn có thể chỉ tìm đúng một giá trị và để phần còn lại chưa được sắp đầy đủ.

### Bảng chuyển quy ước

| Ý nghĩa | Thứ hạng k (1-based) | Chỉ số trong mảng đã sắp (0-based) |
|---|---:|---:|
| Phần tử nhỏ nhất | `1` | `0` |
| Phần tử nhỏ thứ hai | `2` | `1` |
| Phần tử nhỏ thứ ba | `3` | `2` |
| Phần tử nhỏ nhất cuối cùng (lớn nhất) | `n` | `n - 1` |
| Phần tử lớn nhất | `1` tính từ phía lớn | `n - 1` |
| Phần tử lớn thứ hai | `2` tính từ phía lớn | `n - 2` |
| Phần tử lớn thứ k | `k` tính từ phía lớn | `n - k` |

Tóm lại:

- **Nhỏ thứ `k`, thứ hạng 1-based:** vị trí chỉ số `k - 1`.
- **Lớn thứ `k`, thứ hạng 1-based:** vị trí chỉ số `n - k` trong mảng sắp **tăng dần**.
- Nếu API nhận trực tiếp **chỉ số mục tiêu `targetIndex` từ 0**, không được trừ `1` thêm lần nữa.
- Thứ hạng hợp lệ cho cách đếm có lặp là `1 <= k <= n`. `k=0`, `k>n` hoặc mảng rỗng đều **không có đáp án** theo hợp đồng này.

Nếu đề dùng “**k-th element**”, “**index k**” hay cung cấp giá trị `k` từ API khác, phải đọc rõ nó chỉ **thứ hạng** hay **chỉ số mảng**. Hai biến thường được đặt tên khác nhau trong mã, ví dụ `rank` (1-based) và `targetIndex` (0-based), để giảm lỗi lệch một.

### Dữ liệu trùng: thứ hạng có lặp hay phân biệt?

Xét `[7,2,7,4,2,9]`:

| k | Nhỏ thứ k **tính từng lần xuất hiện** | Nhỏ thứ k **theo giá trị phân biệt** |
|---:|---:|---:|
| 1 | 2 | 2 |
| 2 | 2 | 4 |
| 3 | 4 | 7 |
| 4 | 7 | 9 |
| 5 | 7 | Không tồn tại |
| 6 | 9 | Không tồn tại |

Trong định nghĩa **order statistic thông thường**, phần tử trùng vẫn chiếm **những thứ hạng riêng**. Một giá trị `7` xuất hiện hai lần nên chiếm hai vị trí trong mảng sắp. Bài “giá trị phân biệt nhỏ thứ `k`” là bài toán khác: cần loại ảnh hưởng của bản sao trước hoặc trong khi chọn.

**Thứ hạng giá trị** và **vị trí phần tử cụ thể** cũng khác nhau: khi nhiều phần tử bằng nhau, không có một **chỉ số gốc duy nhất** được suy ra chỉ từ giá trị nhỏ thứ `k`. Nếu đề yêu cầu trả **vị trí trong mảng đầu vào**, phải quy định cách phá hòa, chẳng hạn ưu tiên chỉ số xuất hiện sớm nhất, và bảo toàn thông tin chỉ số gốc.

## 2. Phần tử nhỏ thứ k khác gì với các bài toán gần giống?

- **Tìm giá trị nhỏ thứ k:** chỉ trả một giá trị `v` đứng ở thứ hạng `k` khi tính cả bản sao.
- **Tìm k phần tử nhỏ nhất:** trả một *tập đa phần tử* gồm `k` phần tử (có thể chưa sắp); nếu có nhiều phần tử bằng ở ranh giới, phải quy định cách chọn các phần tử cụ thể khi cần chỉ số.
- **Tìm giá trị nhỏ thứ k phân biệt:** thứ hạng tính sau khi gom những giá trị bằng nhau thành một.
- **Tìm phần tử lớn thứ k:** đếm từ cuối danh sách sắp tăng; chuyển `k` sang chỉ số `n-k`.
- **Tìm trung vị (median):** một hoặc hai thứ hạng trung tâm. Với `n` lẻ, trung vị theo thứ tự là nhỏ thứ `(n+1)/2`. Với `n` chẵn, định nghĩa trung vị có thể chọn **trung vị dưới**, **trung vị trên** hoặc trung bình của hai giá trị trung tâm; cần biết đề yêu cầu cách nào.
- **Tìm phân vị (percentile/quantile):** có nhiều chuẩn nội suy và cách chọn thứ hạng; không mặc định mọi công thức phân vị tương đương với một thứ hạng nguyên.

Nếu chỉ cần giá trị thứ `k`, **sắp xếp toàn bộ dãy có thể làm nhiều việc hơn cần thiết**. Đây là động cơ dùng các thuật toán chọn chuyên dụng như Quickselect.

## 3. Giải pháp dễ hiểu nhất: sắp xếp rồi lấy vị trí

Cách trực tiếp:

1. Sắp xếp một bản sao `b` của mảng theo thứ tự không giảm.
2. Đảm bảo `1 <= k <= n`.
3. Trả `b[k-1]`.

Nếu cần lớn thứ `k`, trả `b[n-k]`. Nếu cần giá trị phân biệt nhỏ thứ `k`, duyệt mảng đã sắp và chỉ tăng bộ đếm khi gặp giá trị khác giá trị trước.

**Ưu điểm:** ngắn gọn, dễ kiểm chứng, phù hợp khi cần thêm các thứ hạng khác hoặc vốn đã phải sắp cả dữ liệu. **Nhược điểm:** thường tốn `O(n log n)` thời gian với sắp xếp so sánh; nếu sao chép mảng để giữ nguyên đầu vào thì cần `O(n)` bộ nhớ phụ. Sau khi có mảng đã sắp, một truy vấn thứ hạng cụ thể chỉ cần `O(1)` để đọc giá trị.

Chú ý: sắp xếp **ngay trên mảng đầu vào** làm thay đổi thứ tự của nó. Nếu hợp đồng yêu cầu mảng gốc giữ nguyên, hãy sao chép trước khi sắp; không nên âm thầm sửa dữ liệu mà mã gọi còn cần.

## 4. Quickselect: chỉ xử lý phía có thể chứa thứ hạng k

**Quickselect** có chung bước **phân hoạch (partition)** với Quicksort, nhưng khác ở chỗ: sau một lần phân hoạch, nó chỉ tiếp tục xử lý **một phía chứa chỉ số mục tiêu**, không đệ quy sắp cả hai phía.

Đặt `targetIndex=k-1` (theo chỉ số từ `0`). Chọn một giá trị chốt `pivot` trong đoạn chưa xử lý và chia đoạn thành:

- Các phần tử `< pivot`.
- Các phần tử `== pivot`.
- Các phần tử `> pivot`.

Với **phân hoạch ba vùng**, giả sử sau phân hoạch ta được:

```text
[lo, lt)      [lt, gt]          (gt, hi]
  < pivot      == pivot          > pivot

targetIndex < lt          → chỉ tìm phía trái
lt <= targetIndex <= gt   → đáp án bằng pivot
targetIndex > gt          → chỉ tìm phía phải
```

Do các vùng được phân theo **giá trị**, mọi phần tử bên trái đều nhỏ hơn mọi phần tử ở vùng bằng chốt, và vùng bằng chốt nhỏ hơn mọi phần tử bên phải. Những thứ hạng thuộc vùng bằng chốt đều có giá trị `pivot`. Nếu mục tiêu thuộc bên trái hoặc bên phải, phía kia **không thể chứa giá trị của thứ hạng cần tìm**, nên có thể bỏ hẳn.

### Ví dụ phân hoạch có nhiều bản sao

Cho `a=[7,2,7,4,2,9]` và `k=3`, tức `targetIndex=2`. Nếu chọn `pivot=7`, một phân hoạch ba vùng hợp lệ có thể là:

```text
[2, 4, 2] | [7, 7] | [9]
  < 7     |  = 7   | > 7
vị trí:     0 1 2     3 4    5

targetIndex = 2 nằm ở vùng < 7.
Chỉ tiếp tục chọn trong các vị trí [0, 2].
```

Lần phân hoạch tiếp theo trên `[2,4,2]` sẽ xác định nhỏ thứ ba là `4`. **Không cần hoàn thành việc sắp cả mảng**. Mảng sau Quickselect có thể không được sắp toàn bộ, nhưng giá trị trả về vẫn đúng.

**Vì sao chọn phân hoạch ba vùng?** Với rất nhiều bản sao bằng chốt, mọi vị trí ở vùng `== pivot` được giải quyết ngay. Bản phân hoạch hai vùng vẫn có thể đúng, nhưng phải xử lý chỉ số và các bản sao cẩn thận để tránh làm việc dư thừa hoặc suy thoái trên dữ liệu trùng.

### Bất biến của giai đoạn phân hoạch

Trong đoạn đang xử lý `[lo,hi]`, giữ các chỉ số `lt`, `i`, `gt` để luôn có:

```text
[lo,lt)      [lt,i)          [i,gt]          (gt,hi]
 < pivot     == pivot        chưa xét        > pivot
```

- Khi `a[i]<pivot`: đổi `a[i]` với `a[lt]`, tăng `lt` và `i`.
- Khi `a[i]==pivot`: tăng `i`.
- Khi `a[i]>pivot`: đổi `a[i]` với `a[gt]`, giảm `gt` nhưng **chưa tăng `i`** vì phần tử đổi từ cuối sang chưa được phân loại.

Mỗi bước giảm số phần tử trong vùng chưa xét, nên phân hoạch kết thúc. Mọi phép đổi chỉ thao tác trong đoạn hiện tại và bảo toàn số lần xuất hiện của từng giá trị.

### Độ phức tạp của Quickselect

Nếu sau mỗi phân hoạch, phần còn lại chứa đáp án có kích thước tối đa một tỷ lệ cố định của đoạn trước, số thao tác có dạng:

```text
T(n) = T(c*n) + O(n), với một hằng số c < 1,
nên T(n) = O(n).
```

Nếu các lần phân hoạch liên tiếp chỉ loại được rất ít phần tử, ta có thể gặp:

```text
T(n) = T(n-1) + O(n) = O(n^2).
```

Chọn chốt bằng **trung vị của ba mẫu** thường cải thiện hành vi trên nhiều đầu vào, nhưng **không bảo đảm `O(n)` trường hợp xấu nhất**. Với chốt chọn ngẫu nhiên độc lập và đều trong đoạn hiện tại, Quickselect có **thời gian kỳ vọng `O(n)`**, song trường hợp xấu nhất vẫn có thể `O(n²)`. Một chiến lược chọn chốt xác định như **median of medians (BFPRT)** có thể đạt `O(n)` xấu nhất với các giả thiết chuẩn của mô hình so sánh, đổi lại cài đặt phức tạp và hệ số thực thi có thể lớn.

Bản Quickselect bên dưới dùng vòng lặp và trung vị ba mẫu để tập trung vào cơ chế chọn thứ hạng. Vì thuật toán phân hoạch tại chỗ và không đệ quy, **bộ nhớ phụ của lõi Quickselect là `O(1)`**. Tuy nhiên, bản API giữ nguyên mảng đầu vào sẽ sao chép `n` phần tử trước, nên tổng bộ nhớ phụ thành **`O(n)`**.

## 5. Java 17+: một chương trình chạy được với bốn cách chọn

Chương trình minh họa rõ hai quy ước: đối số `rank` luôn là **thứ hạng bắt đầu từ 1**; còn `targetIndex` bên trong Quickselect là **chỉ số bắt đầu từ 0**.

Chương trình có các hàm:

- `kthSmallest(a,rank)`: trả giá trị nhỏ thứ `rank`, **tính cả bản sao** và **không thay đổi mảng đầu vào**.
- `kthSmallestInPlace(a,rank)`: cùng đáp án nhưng **cho phép thay đổi thứ tự phần tử** trong mảng được truyền vào, dùng Quickselect phân hoạch ba vùng.
- `kthLargest(a,rank)`: trả lớn thứ `rank`, tính cả bản sao, thông qua đổi `rank`.
- `kthDistinctSmallest(a,rank)`: trả giá trị **phân biệt** nhỏ thứ `rank` sau khi sắp bản sao và bỏ qua giá trị trùng.
- `kthSmallestHeap(a,rank)`: dùng **max-heap có đúng tối đa `rank` phần tử** làm lời giải thay thế, thuận lợi khi `rank` nhỏ và dữ liệu được đọc tuần tự.

Với các hàm có thứ hạng theo từng lần xuất hiện, mảng rỗng, `rank<1` hoặc `rank>n` được báo bằng `IllegalArgumentException`. Với phiên bản phân biệt, `rank` vượt số **giá trị khác nhau** cũng không hợp lệ.

Lưu tệp dưới tên **`KthSmallestDemo.java`**:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.PriorityQueue;

public final class KthSmallestDemo {
    private KthSmallestDemo() {
    }

    private static void requireRank(int[] a, int rank) {
        if (a == null) {
            throw new IllegalArgumentException("array must not be null");
        }
        if (rank < 1 || rank > a.length) {
            throw new IllegalArgumentException(
                "rank must be between 1 and array length"
            );
        }
    }

    // Xếp thứ hạng 1-based, tính mọi bản sao.
    // Không thay đổi mảng đầu vào.
    public static int kthSmallest(int[] a, int rank) {
        requireRank(a, rank);
        int[] copy = Arrays.copyOf(a, a.length);
        return kthSmallestInPlace(copy, rank);
    }

    // Lõi Quickselect: 1-based rank -> 0-based targetIndex.
    // Mảng a có thể bị hoán đổi thứ tự; KHÔNG nhất thiết được sắp.
    public static int kthSmallestInPlace(int[] a, int rank) {
        requireRank(a, rank);

        int targetIndex = rank - 1;
        int lo = 0;
        int hi = a.length - 1;

        while (lo <= hi) {
            int mid = lo + (hi - lo) / 2;
            int pivot = medianOfThree(a[lo], a[mid], a[hi]);

            int lt = lo;
            int i = lo;
            int gt = hi;

            // [lo,lt) < pivot
            // [lt,i) == pivot
            // [i,gt] chưa xét
            // (gt,hi] > pivot
            while (i <= gt) {
                if (a[i] < pivot) {
                    swap(a, i, lt);
                    i++;
                    lt++;
                } else if (a[i] > pivot) {
                    swap(a, i, gt);
                    gt--;
                    // Chưa tăng i: a[i] mới chưa được phân loại.
                } else {
                    i++;
                }
            }

            if (targetIndex < lt) {
                hi = lt - 1;
            } else if (targetIndex > gt) {
                lo = gt + 1;
            } else {
                return a[targetIndex]; // Bằng pivot.
            }
        }

        throw new IllegalStateException("unreachable for a valid rank");
    }

    private static int medianOfThree(int x, int y, int z) {
        if (x < y) {
            if (y < z) {
                return y;
            }
            return x < z ? z : x;
        }
        if (x < z) {
            return x;
        }
        return y < z ? z : y;
    }

    private static void swap(int[] a, int i, int j) {
        int tmp = a[i];
        a[i] = a[j];
        a[j] = tmp;
    }

    // Lớn thứ rank (1-based), tính cả bản sao.
    public static int kthLargest(int[] a, int rank) {
        requireRank(a, rank);
        return kthSmallest(a, a.length - rank + 1);
    }

    // Nhỏ thứ rank trong các GIÁ TRỊ PHÂN BIỆT.
    // Không thay đổi mảng đầu vào.
    public static int kthDistinctSmallest(int[] a, int rank) {
        if (a == null) {
            throw new IllegalArgumentException("array must not be null");
        }
        if (rank < 1) {
            throw new IllegalArgumentException("rank must be positive");
        }

        int[] copy = Arrays.copyOf(a, a.length);
        Arrays.sort(copy);
        int distinctCount = 0;

        for (int i = 0; i < copy.length; i++) {
            if (i == 0 || copy[i] != copy[i - 1]) {
                distinctCount++;
                if (distinctCount == rank) {
                    return copy[i];
                }
            }
        }
        throw new IllegalArgumentException(
            "rank exceeds number of distinct values"
        );
    }

    // Max-heap giữ rank phần tử nhỏ nhất đã thấy.
    // Mỗi bản sao vẫn được tính một lần xuất hiện.
    public static int kthSmallestHeap(int[] a, int rank) {
        requireRank(a, rank);
        PriorityQueue<Integer> heap =
            new PriorityQueue<>(Comparator.reverseOrder());

        for (int value : a) {
            if (heap.size() < rank) {
                heap.offer(value);
            } else if (value < heap.peek()) {
                heap.poll();
                heap.offer(value);
            }
        }
        return heap.peek();
    }

    public static void main(String[] args) {
        int[] data = {7, 2, 7, 4, 2, 9};
        int[] sorted = Arrays.copyOf(data, data.length);
        Arrays.sort(sorted);

        System.out.println("Sorted: " + Arrays.toString(sorted));
        System.out.println("Smallest rank 1: " + kthSmallest(data, 1));
        System.out.println("Smallest rank 2: " + kthSmallest(data, 2));
        System.out.println("Smallest rank 3: " + kthSmallest(data, 3));
        System.out.println("Smallest rank 5: " + kthSmallest(data, 5));
        System.out.println("Largest rank 2: " + kthLargest(data, 2));
        System.out.println("Distinct rank 2: "
            + kthDistinctSmallest(data, 2));
        System.out.println("Heap rank 3: "
            + kthSmallestHeap(data, 3));

        int[] work = Arrays.copyOf(data, data.length);
        System.out.println("In place rank 3: "
            + kthSmallestInPlace(work, 3));
        System.out.println("Original: " + Arrays.toString(data));

        int[] withNegative = {-5, -5, 0, 8};
        System.out.println("Negative rank 1: "
            + kthSmallest(withNegative, 1));
        System.out.println("Negative rank 4: "
            + kthSmallest(withNegative, 4));
        System.out.println("Singleton: "
            + kthSmallest(new int[] {42}, 1));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac KthSmallestDemo.java
java KthSmallestDemo
```

Kết quả chuẩn:

```text
Sorted: [2, 2, 4, 7, 7, 9]
Smallest rank 1: 2
Smallest rank 2: 2
Smallest rank 3: 4
Smallest rank 5: 7
Largest rank 2: 7
Distinct rank 2: 4
Heap rank 3: 4
In place rank 3: 4
Original: [7, 2, 7, 4, 2, 9]
Negative rank 1: -5
Negative rank 4: 8
Singleton: 42
```

### Giải thích kết quả

- Thứ hạng `1` và `2` đều là `2` vì **hai bản sao của giá trị `2` chiếm hai vị trí đầu**. Thứ hạng `3` là `4`; thứ hạng `5` là `7`.
- Lớn thứ `2` là `7`: trong dãy tăng, đó là chỉ số `n - 2 = 4`. Việc đếm từ phía lớn không xóa bản sao.
- Phân biệt nhỏ thứ `2` là `4` vì `[2,4,7,9]` mới là các giá trị được đếm.
- Heap và Quickselect trả cùng giá trị `4` cho nhỏ thứ `3`, dù cách tổ chức dữ liệu khác nhau.
- `kthSmallest` sao chép dữ liệu nên mảng `data` sau các truy vấn vẫn ở thứ tự ban đầu. `kthSmallestInPlace` được gọi trên `work`, có thể thay đổi thứ tự trong `work` nhưng không làm thay đổi `data`.
- Số âm được so sánh theo thứ tự số bình thường. Một phần tử duy nhất có thứ hạng hợp lệ duy nhất là `1`.

**Lưu ý về Java:** mã dùng so sánh `<`, `>` và `==` đối với `int`, không dùng phép trừ hai số để quyết định thứ tự nên tránh lỗi **tràn `int` khi tính `a-b`**. Nếu chọn kiểu dữ liệu hoặc comparator khác, cần áp dụng quan hệ thứ tự nhất quán và tránh so sánh bằng phép trừ có thể tràn.

## 6. Vì sao Quickselect và heap cho đúng thứ hạng?

### Bất biến chọn của Quickselect

Giả sử đang tìm chỉ số `targetIndex` trong một dãy đã bị phân hoạch qua nhiều vòng. Ở đầu vòng lặp, những vùng đã bỏ được bảo đảm **không thể chứa phần tử đứng tại thứ hạng mục tiêu** của toàn bộ đa tập ban đầu.

Sau một lần chia ba vùng `<pivot`, `==pivot`, `>pivot`:

1. Mọi giá trị trong vùng trái không lớn hơn bất kỳ giá trị nào ở vùng giữa/phải.
2. Vùng giữa gồm đúng các giá trị `pivot`; mọi vị trí có chỉ số từ `lt` tới `gt` có **giá trị thứ hạng bằng `pivot`**.
3. Vùng phải có giá trị lớn hơn chốt; nếu mục tiêu ở vùng trái, vùng phải không thể chứa đáp án và ngược lại.

Vì mọi thao tác chỉ **hoán đổi phần tử**, đa tập giá trị không đổi. Sau mỗi bước, thuật toán hoặc trả đúng chốt nếu `targetIndex` nằm ở vùng bằng nhau, hoặc giới hạn miền cần xử lý vào đúng một phía chứa thứ hạng mục tiêu. Kích thước miền giảm bởi vì chốt xuất hiện trong đoạn hiện tại và tạo một vùng bằng nhau không rỗng. Vì vậy thuật toán kết thúc và trả đúng giá trị bậc `k`.

Đặc biệt, Quickselect **không bảo đảm thứ tự giữa các phần tử còn lại**, và việc mảng có phần tử ở vị trí `k-1` đã đúng sau chọn **không có nghĩa toàn bộ mảng đã sắp xếp**.

### Bất biến của max-heap kích thước k

Sau khi xem `t` phần tử đầu tiên, heap chứa một đa tập gồm **`min(t,k)` giá trị nhỏ nhất đã thấy**, tính cả các lần xuất hiện. Nếu có ít hơn `k` phần tử, đưa tất cả vào. Khi heap đã có `k` phần tử, **đỉnh heap là giá trị lớn nhất trong `k` giá trị nhỏ nhất đã giữ**.

Nếu phần tử mới `x` nhỏ hơn đỉnh, loại đỉnh rồi chèn `x`: ta đã thay một ứng viên lớn bằng ứng viên nhỏ hơn. Nếu `x>=đỉnh`, phần tử mới không thể cải thiện tập `k` giá trị nhỏ nhất; có thể bỏ qua nó. Với giá trị bằng nhau ở ranh giới, giữ bản sao nào không ảnh hưởng **giá trị** phần tử thứ `k`, miễn là số bản sao trong heap được tính đúng.

Sau khi đọc hết `n` phần tử (`n>=k`), đỉnh heap chính là giá trị nhỏ thứ `k`. Phương pháp này hữu ích nếu dữ liệu đến theo **luồng**, vì không cần lưu toàn bộ mảng: chỉ cần heap chứa tối đa `k` phần tử.

## 7. So sánh các phương án theo giới hạn tài nguyên

Giả sử `n` phần tử, `1<=k<=n`; so sánh `int` tốn `O(1)`.

| Phương pháp | Thời gian | Bộ nhớ phụ | Khi nào hữu ích |
|---|---|---|---|
| Sắp một bản sao, đọc `[k-1]` | `O(n log n)` thông thường | `O(n)` cho bản sao; còn chi phí của thuật toán sắp | Đơn giản, nhiều truy vấn thứ hạng, cần toàn bộ dãy có thứ tự |
| Quickselect phân hoạch tại chỗ | Thường `O(n)` khi chia đủ cân đối; **xấu nhất `O(n²)`** | `O(1)` với bản lặp | Chỉ cần một thứ hạng; chấp nhận thay thứ tự mảng |
| Quickselect trên bản sao | Giống Quickselect lõi | `O(n)` vì sao chép | Chỉ cần một thứ hạng nhưng phải giữ nguyên mảng gốc |
| Quickselect chốt ngẫu nhiên | **Kỳ vọng `O(n)`**, xấu nhất `O(n²)` | `O(1)` ngoài nguồn sinh số ngẫu nhiên với bản lặp | Giảm phụ thuộc vào mẫu đầu vào; vẫn cần hiểu bảo đảm kỳ vọng |
| Median of medians (BFPRT) | **`O(n)` xấu nhất** khi triển khai đúng | Phụ thuộc triển khai | Cần bảo đảm tuyến tính chặt chẽ |
| Max-heap kích thước `k` | `O(n log k)` với `k>=2`, `O(n)` với `k=1` | `O(k)` | `k` nhỏ, dữ liệu đến tuần tự hoặc khó lưu cả mảng |
| Đếm tần suất trong miền giá trị nhỏ | `O(n+U)` với miền giá trị `U` có thể cấp phát | `O(U)` | Khóa nguyên nằm trong miền nhỏ, biết giới hạn |

Các bảng độ phức tạp cần đọc theo **đúng hợp đồng**: `k` nhỏ thứ theo số lần xuất hiện, không phải thứ `k` trong các giá trị phân biệt. Nếu cần phân biệt, phải tính thêm công việc xác định giá trị nào đã xuất hiện.

### Lưu ý về độ phức tạp heap

Với max-heap có không quá `k` phần tử, mỗi thao tác chèn/xóa mất `O(log k)` khi `k>=2`; sau `n` phần tử, tổng chi phí là `O(n log k)` theo cách viết thông dụng. Với `k=1`, thuật toán chỉ giữ giá trị nhỏ nhất, nên dùng `O(n)` thời gian và `O(1)` bộ nhớ. **Không viết `O(n log 1)=O(0)`**: công việc đọc dữ liệu vẫn phải diễn ra.

Nếu cần **lớn thứ `k` trong luồng**, dùng **min-heap kích thước `k`** và giữ `k` phần tử lớn nhất; đỉnh là lớn thứ `k`. Đừng dùng nhầm max-heap khi đổi hướng thứ hạng.

### Một lựa chọn nữa: tìm nhị phân trên miền giá trị

Nếu biết miền giá trị số nguyên `[minValue,maxValue]`, có thể định nghĩa hàm `countLessOrEqual(x)` đếm số phần tử `<=x`. Hàm đếm này **không giảm** khi `x` tăng. Giá trị nhỏ thứ `k` là số nguyên nhỏ nhất `x` sao cho `countLessOrEqual(x)>=k`.

Đây là **tìm kiếm nhị phân trên đáp án**, với khoảng `O(log R)` phép kiểm tra cho độ rộng miền `R` và mỗi lần đếm thường tốn `O(n)`; tổng thời gian khoảng `O(n log R)`, bộ nhớ phụ có thể `O(1)`. Cần tính trung điểm bằng kiểu đủ lớn để tránh tràn số. Phương án này thường chỉ đáng cân nhắc khi phép đếm nhanh hơn nhờ cấu trúc bài toán hoặc miền giá trị đặc biệt, không phải tự động tốt hơn Quickselect.

## 8. Cách xác định đáp án khi có nhiều giá trị bằng nhau

Với `b` là mảng đã sắp, nếu `v=b[k-1]` thì có thể mô tả thứ hạng bằng hai số:

- `L`: số phần tử **nhỏ hơn** `v`.
- `E`: số phần tử **bằng** `v`.

Khi đó `v` là giá trị nhỏ thứ `k` **khi và chỉ khi**:

```text
L < k <= L + E.
```

Ví dụ, dãy `[2,2,4,7,7,9]` với `v=7` có `L=3` và `E=2`, nên `7` chiếm các thứ hạng `4` và `5`. Công thức này là một cách kiểm tra đáp án hiệu quả **mà không cần định nghĩa chính xác bản sao nào của `7` là “thứ tư” hoặc “thứ năm”**.

Khi bài toán dùng **distinct rank**, số lần xuất hiện `E` không còn quyết định số thứ hạng mà `v` chiếm: mọi bản sao của `v` chỉ tạo ra **một giá trị phân biệt**. Vì thế không thể đổi từ bài rank có lặp sang bài rank phân biệt chỉ bằng một phép sửa `k-1` hay `n-k`; cần thay cách đếm.

### Quy ước phần tử bằng nhau và chỉ số gốc

Nếu đề chỉ trả **giá trị**, trả `7` cho thứ hạng `4` hoặc `5` là đầy đủ. Nếu đề yêu cầu trả **đúng một bản ghi cụ thể** có khóa `7`, việc phá hòa phải được nêu rõ, ví dụ theo cặp khóa `(value, originalIndex)`. Khi đó thứ tự so sánh không chỉ theo `value` nữa; vị trí của bản ghi sau khi chọn được xác định bởi cả khóa và chỉ số gốc.

Không suy diễn rằng Quickselect là **stable selection**: các lần `swap` có thể đảo thứ tự tương đối giữa những bản ghi có khóa bằng nhau. Tính ổn định không cần thiết nếu mục tiêu chỉ là giá trị nhỏ thứ `k`, nhưng có thể cần thiết khi trả danh sách các bản ghi có thứ tự.

## 9. Các trường hợp biên và lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Nhầm `k` 1-based thành chỉ số mảng | Trả nhỏ thứ `k+1` hoặc vượt cuối mảng | Đặt `targetIndex=k-1` đúng **một lần** |
| Dùng `n-k+1` như chỉ số 0-based của lớn thứ `k` | Lệch một đơn vị | Chỉ số từ 0 của lớn thứ `k` là `n-k` |
| Gọi “nhỏ thứ k phân biệt” nhưng đếm cả bản sao | Sai khi trùng giá trị | Loại/đếm giá trị phân biệt theo hợp đồng |
| Quên kiểm tra `k<1`, `k>n`, hoặc mảng rỗng | Truy cập sai chỉ số hoặc trả kết quả vô nghĩa | Kiểm tra điều kiện đầu vào trước chọn |
| Chọn một chốt rồi đệ quy **cả hai** phía | Thực hiện Quicksort, làm thừa việc | Quickselect chỉ xử lý phía chứa `targetIndex` |
| Đổi phần tử `>pivot` rồi tăng ngay `i` | Bỏ qua phần tử chưa phân loại mới chuyển sang | Giảm `gt`, kiểm tra lại vị trí `i` |
| Trả `a[k-1]` sau khi phân hoạch một lần bất kỳ | Chưa chắc mục tiêu thuộc vùng bằng chốt | Chỉ trả nếu `lt<=targetIndex<=gt` |
| Tin rằng Quickselect luôn `O(n)` | Đánh giá thiếu trường hợp phân hoạch cực lệch | Phân biệt kỳ vọng/trường hợp thường và trường hợp xấu |
| Trả mảng sau Quickselect như thể đã sắp | Những phần tử khác có thể chưa đúng thứ tự | Chỉ cam kết giá trị được chọn, không cam kết sắp cả mảng |
| Sửa trực tiếp mảng đầu vào khi người gọi cần giữ nguyên | Làm mất thứ tự gốc | Tạo bản sao hoặc làm rõ phương thức `InPlace` |
| Dùng heap sai chiều | Trả lớn thứ `k` thay vì nhỏ thứ `k` | Nhỏ thứ `k`: max-heap giữ `k` nhỏ nhất |
| Dùng `a-b` làm comparator với số nguyên lớn | Có thể tràn `int`, sai thứ tự | Dùng `Integer.compare(a,b)` hoặc toán tử so sánh trực tiếp |
| Chỉ thử dữ liệu gồm các giá trị khác nhau | Không thấy lỗi xử lý bản sao | Kiểm thử mảng toàn bằng nhau và nhiều bản sao |
| Nhầm “giá trị thứ k” với “k giá trị đầu” | Đầu ra sai hình dạng | Xác nhận cần một giá trị hay một bộ sưu tập |

### Kiểm thử đối chứng

Với các mảng nhỏ, cách kiểm tra đáng tin là:

1. Sao chép mảng ban đầu.
2. Sắp bản sao bằng một thư viện phù hợp.
3. Với mọi `k` hợp lệ từ `1` đến `n`, so sánh `kthSmallest(a,k)` với `sorted[k-1]`.
4. So sánh `kthLargest(a,k)` với `sorted[n-k]`.
5. Với bản phân biệt, đi qua mảng đã sắp và chỉ giữ một lần cho mỗi giá trị.
6. Nếu dùng bản `InPlace`, kiểm tra mảng sau đó vẫn chứa **cùng đa tập giá trị**, ngay cả khi thứ tự khác.

Thử các trường hợp: mảng rỗng; mảng một phần tử; toàn bộ phần tử bằng nhau; đã tăng dần; giảm dần; nhiều số âm; `Integer.MIN_VALUE` và `Integer.MAX_VALUE`; `k=1`; `k=n`; `k` nằm đúng giữa một vùng nhiều bản sao; và giá trị `k` không hợp lệ.

**Kiểm thử ngẫu nhiên** giúp phát hiện lỗi trong cài đặt, nhưng **chứng minh bất biến của phân hoạch và điều kiện thứ hạng** là cơ sở để tin thuật toán đúng cho mọi đầu vào hợp lệ.

## 10. Bài luyện tập

**Bài 1 — Đổi hệ chỉ số.** Mảng dài `n=12`. Nếu đề yêu cầu nhỏ thứ `k=4`, chỉ số mục tiêu của Quickselect là bao nhiêu? Nếu yêu cầu lớn thứ `k=4`, chỉ số trong mảng đã sắp tăng là bao nhiêu?

*Đáp án:* nhỏ thứ tư có chỉ số `3`; lớn thứ tư có chỉ số `12-4=8`.

**Bài 2 — Có lặp và phân biệt.** Cho `[5,1,5,2,2,8,2]`. Tìm nhỏ thứ `4` tính cả bản sao, và giá trị phân biệt nhỏ thứ `3`.

*Đáp án:* sắp tăng được `[1,2,2,2,5,5,8]`, nên nhỏ thứ `4` là `2`. Các giá trị phân biệt là `[1,2,5,8]`, nên nhỏ thứ `3` phân biệt là `5`.

**Bài 3 — Tính điều kiện thứ hạng.** Với dãy `[3,3,3,6,8,8,10]`, xác định `L` và `E` cho `v=8`. Những thứ hạng nào có giá trị bằng `8`?

*Đáp án:* `L=4`, `E=2`, nên `8` chiếm thứ hạng `5` và `6` vì `4<k<=6`.

**Bài 4 — Chọn cách làm.** Có `n=5.000.000` số nguyên đọc tuần tự, cần biết nhỏ thứ `10` và RAM hạn chế. Phương pháp nào thường phù hợp giữa sắp toàn bộ, Quickselect trên bản sao và max-heap kích thước `10`?

*Gợi ý:* max-heap chứa tối đa `10` phần tử có bộ nhớ `O(10)` và quét một lần; Quickselect hoặc sắp bản sao thường cần giữ nhiều dữ liệu hơn. Cần kiểm tra yêu cầu có cho phép đọc tuần tự không và dữ liệu có được lưu để truy cập ngẫu nhiên không.

**Bài 5 — Chứng minh Quickselect.** Tại sao sau phân hoạch ba vùng, nếu `targetIndex` nằm trong `[lt,gt]` thì trả `pivot` là đúng dù các phần tử ở hai phía chưa được sắp?

*Gợi ý:* mọi phần tử bên trái nhỏ hơn chốt, mọi phần tử ở giữa bằng chốt, mọi phần tử bên phải lớn hơn chốt; như vậy tất cả vị trí thuộc vùng bằng chốt có cùng giá trị thứ hạng chính xác.

**Bài 6 — Bảo đảm thời gian.** Nêu khác biệt giữa Quickselect chọn chốt bằng trung vị ba mẫu, Quickselect chọn chốt ngẫu nhiên, và phiên bản chọn chốt median-of-medians về độ phức tạp.

*Gợi ý:* trung vị ba mẫu vẫn có thể `O(n²)` xấu nhất; chọn chốt ngẫu nhiên độc lập cho `O(n)` kỳ vọng nhưng xấu nhất vẫn `O(n²)`; median-of-medians có thể đạt `O(n)` xấu nhất khi triển khai đúng.

## Ghi nhớ

**Phần tử nhỏ thứ `k` thường là giá trị ở chỉ số `k-1` của dãy đã sắp tăng, tính cả bản sao.** Với **lớn thứ `k`**, chỉ số là `n-k`. Hãy làm rõ ngay **thứ hạng 1-based hay chỉ số 0-based**, **có đếm bản sao không**, **cần giá trị hay chỉ số gốc**, và **có được sửa mảng đầu vào không**.

Nếu chỉ cần một thứ hạng, **Quickselect** có thể tránh sắp toàn bộ và thường xử lý hiệu quả nhờ chỉ tiếp tục ở phía chứa đáp án; cần nhớ chặn xấu nhất phụ thuộc chiến lược chọn chốt. Nếu `k` nhỏ hoặc dữ liệu đến theo luồng, **max-heap kích thước `k`** là phương án hữu ích. Nếu cần rất nhiều thứ hạng hoặc toàn bộ thứ tự, **sắp xếp** có thể đơn giản và thích hợp hơn.
