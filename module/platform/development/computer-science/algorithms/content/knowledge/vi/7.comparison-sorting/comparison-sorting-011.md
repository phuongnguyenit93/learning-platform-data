# Introsort và cách kết hợp nhiều chiến lược sắp xếp

Một thuật toán sắp xếp thường có ưu điểm trong một số tình huống và nhược điểm trong những tình huống khác. **Quicksort** thường nhanh trong thực tế nhờ phân hoạch tại chỗ, nhưng có thể chậm tới bậc `O(n²)` nếu liên tục chọn điểm chia lệch. **Heapsort** bảo đảm `O(n log n)` ở trường hợp xấu nhất nhưng thường có cách truy cập bộ nhớ kém thuận lợi hơn. **Insertion sort** có bậc `O(n²)` trên đoạn dài, song rất đơn giản và có chi phí cố định thấp khi đoạn còn ít phần tử.

**Introsort (introspective sort)** kết hợp ưu điểm của các chiến lược này:

1. **Bắt đầu bằng phân hoạch kiểu Quicksort** để tận dụng tốc độ thường tốt.
2. **Theo dõi ngân sách độ sâu phân hoạch**. Nếu đã phân hoạch quá sâu mà đoạn còn lớn, **chuyển sang Heapsort** để bảo vệ giới hạn thời gian xấu nhất.
3. **Dùng Insertion sort cho các đoạn nhỏ**, nơi một thuật toán đơn giản thường tiết kiệm chi phí hơn việc tiếp tục chia nhỏ.

Đây là một ví dụ về **thiết kế thuật toán lai (hybrid algorithm)**: chọn chiến lược theo trạng thái của bài toán thay vì bắt một thuật toán đơn lẻ giải quyết mọi kích thước và phân bố dữ liệu. Việc thay đổi chiến lược phải giữ nguyên hợp đồng sắp xếp: kết quả cuối cùng **không giảm**, gồm **đúng các phần tử đầu vào**, kể cả các bản sao.

## 1. So sánh vai trò của ba thuật toán

| Chiến lược | Ý tưởng cốt lõi | Thời gian thường quan tâm | Điểm mạnh và giới hạn |
|---|---|---|---|
| Quicksort | Chọn một giá trị chốt `pivot`, chia phần tử nhỏ/lớn hơn chốt, rồi xử lý các đoạn con | `O(n log n)` trong tình huống phân hoạch đủ cân đối; xấu nhất `O(n²)` nếu không có cơ chế cứu | Phân hoạch tại chỗ, thuận lợi trong nhiều dữ liệu thực tế; dễ suy thoái vì điểm chia lệch |
| Heapsort | Xây **max-heap**, liên tiếp đưa phần tử lớn nhất về cuối vùng cần sắp | `Θ(n log n)` ở trường hợp xấu nhất | Có chặn trên chặt chẽ và bộ nhớ phụ `O(1)` với bản lặp; truy cập bộ nhớ thường kém liền mạch hơn |
| Insertion sort | Chèn từng phần tử vào tiền tố đã có thứ tự | `O(k²)` trên đoạn dài `k`; `O(k)` nếu đã sắp | Cấu trúc nhỏ gọn, phù hợp đoạn rất ngắn hoặc gần có thứ tự |
| **Introsort** | Quicksort trước, Heapsort khi cạn ngân sách sâu, Insertion sort cho đoạn ngắn | **`O(n log n)` xấu nhất** cho `n≥2` | Kết hợp hiệu quả thực tế và bảo đảm lý thuyết; cần cài đặt ranh giới và chuyển chiến lược đúng |

Bậc tiệm cận chỉ cho biết tốc độ tăng khi đầu vào lớn. Các ngưỡng cắt cụ thể chịu ảnh hưởng bởi bộ xử lý, bộ nhớ đệm, cách chọn `pivot`, kiểu dữ liệu và chi phí so sánh. Chẳng hạn `16` hay `24` phần tử là lựa chọn triển khai có thể đo đạc và điều chỉnh, **không phải hằng số bắt buộc của định nghĩa Introsort**.

### Vì sao không chỉ dùng Quicksort?

Giả sử một kiểu chọn chốt liên tục tạo phân hoạch kích thước `0` và `n-1`. Số công việc có dạng:

\[
T(n)=T(n-1)+\Theta(n),
\]

nên `T(n)=Θ(n²)`. Chọn chốt ngẫu nhiên hoặc lấy trung vị của ba mẫu có thể cải thiện hành vi thường gặp, nhưng **không tự bảo đảm giới hạn xấu nhất `O(n log n)`** cho mọi đầu vào. Introsort kiểm soát rủi ro đó bằng một thuật toán dự phòng có bảo đảm: Heapsort.

### Vì sao Insertion sort lại có mặt trong một thuật toán `O(n log n)`?

Với một đoạn chỉ khoảng vài phần tử, việc chọn chốt, phân hoạch và quản lý lời gọi có thể tốn chi phí cố định không nhỏ. Insertion sort chỉ cần các thao tác so sánh và dịch chuyển đơn giản. Nếu giới hạn độ dài các đoạn xử lý bằng Insertion sort là một hằng số `K`, tổng thời gian của toàn bộ các đoạn nhỏ vẫn bị chặn bởi `O(nK)=O(n)`, nên không làm hỏng bảo đảm `O(n log n)` của Introsort.

## 2. Luồng điều phối của Introsort

Một phiên bản tiêu biểu áp dụng cho dãy `a[0..n-1]`:

```text
introSort(a):
    nếu n < 2: kết thúc
    depthLimit = 2 * floor(log2(n))
    sortRange(a, 0, n, depthLimit)

sortRange(a, from, to, depthLimit):
    nếu đoạn còn rất ngắn:
        insertionSort(a, from, to)
        kết thúc

    nếu depthLimit == 0:
        heapSort(a, from, to)
        kết thúc

    chọn pivot và phân hoạch đoạn
    gọi sortRange trên các phần cần sắp tiếp
        với depthLimit - 1
```

Ta dùng **khoảng nửa mở `[from,to)`**: chỉ số `from` được lấy, chỉ số `to` không được lấy. Độ dài đoạn bằng `to-from`. Một đoạn rỗng có `from==to`. Thống nhất quy ước giúp tránh lỗi bỏ sót phần tử đầu/cuối.

**Thứ tự ưu tiên:** nếu đoạn đã ngắn, Insertion sort là đủ; nếu đoạn vẫn dài và ngân sách độ sâu đã hết, dùng Heapsort; nếu chưa chạm hai điều kiện đó, tiếp tục phân hoạch kiểu Quicksort.

Ngân sách phổ biến là `2⌊log₂n⌋`. Đây là **số lần phân hoạch được phép dọc một đường xử lý**, không phải kích thước mảng và không phải bộ đếm số lần so sánh. Khi gọi các nhánh con, ngân sách giảm. Nếu chỉ một nhánh bị lệch liên tiếp, nhánh đó sớm hết ngân sách và được xử lý bằng Heapsort. Các đoạn con không nhất thiết chuyển chiến lược cùng lúc.

Một số triển khai công nghiệp có cách tối ưu khác: ngưỡng Insertion sort, chọn `pivot` và quản lý ngăn xếp đều có thể thay đổi. Điều định nghĩa ý tưởng Introsort là **bắt đầu với thuật toán thực dụng và chuyển sang phương án có chặn xấu nhất khi dấu hiệu suy thoái xuất hiện**.

## 3. Phân hoạch ba vùng để xử lý phần tử trùng

Quicksort cơ bản thường phân hoạch thành hai phía so với `pivot`. Khi nhiều giá trị bằng nhau, việc liên tục xử lý lại các phần tử trùng có thể gây công việc không cần thiết. Bản minh họa trong bài dùng **phân hoạch ba vùng (three-way partition)**:

- `[from,lt)` chứa các giá trị **nhỏ hơn** `pivot`.
- `[lt,gt+1)` chứa các giá trị **bằng** `pivot` sau khi phân hoạch xong.
- `[gt+1,to)` chứa các giá trị **lớn hơn** `pivot`.

Trong lúc quét, thêm con trỏ `i` để duy trì bất biến:

```text
[from ... lt)   [lt ... i)    [i ... gt]    (gt ... to)
   < pivot       = pivot       chưa xét       > pivot
```

Ban đầu `lt=i=from` và `gt=to-1`. Khi `i<=gt`:

1. Nếu `a[i]<pivot`, đổi chỗ `a[i]` với `a[lt]`, rồi tăng cả `lt` và `i`.
2. Nếu `a[i]==pivot`, chỉ tăng `i`.
3. Nếu `a[i]>pivot`, đổi chỗ `a[i]` với `a[gt]` rồi giảm `gt`; **không tăng `i`**, bởi phần tử vừa đổi từ cuối sang chưa được phân loại.

Ví dụ, với `pivot=4`, phân hoạch dãy `[4,2,4,7,1,4,9]` có thể tạo các vùng tương đương với:

```text
[2, 1] | [4, 4, 4] | [9, 7]
 < 4   |    = 4    |  > 4
```

Sau phân hoạch, **không cần sắp lại vùng bằng chốt** vì mọi giá trị ở đó đã bằng nhau. Chỉ hai vùng nhỏ hơn và lớn hơn cần xử lý tiếp. Nếu toàn bộ đoạn đều bằng `pivot`, vòng phân hoạch duyệt đoạn một lần rồi cả hai vùng con đều rỗng. Điều này rất hữu ích cho dãy chứa nhiều bản sao.

Trong mã, `pivot` được chọn bằng **giá trị trung vị của ba mẫu**: phần tử đầu, phần tử giữa và phần tử cuối của đoạn. Đây là một cách chọn chốt thường được dùng để giảm nguy cơ chọn một cực trị quá hiển nhiên; nó **không bảo đảm** phân hoạch luôn cân đối. Tính đúng đến từ việc mỗi phần tử được đặt đúng vùng, còn bảo đảm thời gian xấu nhất đến từ Heapsort dự phòng.

## 4. Heapsort dự phòng và Insertion sort trên đoạn con

### Heapsort cho đoạn `[from,to)`

Nếu ngân sách độ sâu về `0` trong khi đoạn vẫn lớn, ta sắp **chỉ đoạn con đó** bằng Heapsort. Không được vô tình sắp toàn bộ mảng lại từ đầu hoặc thay đổi các phần tử nằm ngoài khoảng được giao.

Max-heap được biểu diễn bằng chỉ số **tương đối** với `from`:

- Nút tương đối `r` có con trái `2r+1` và con phải `2r+2` nếu những vị trí đó nhỏ hơn kích thước heap.
- Giá trị thực trong mảng là `a[from+r]`.
- Sau khi xây heap, `a[from]` là giá trị lớn nhất còn lại trong vùng heap.
- Đổi gốc với vị trí cuối của heap rồi giảm kích thước heap và vun lại để đưa giá trị lớn tiếp theo về đúng vị trí.

Bước xây heap mất `O(k)` cho đoạn dài `k`, và các lần lấy cực đại có tổng `O(k log k)`. Bản cài đặt dưới đây thực hiện `siftDown` bằng vòng lặp, nên bộ nhớ phụ của Heapsort là `O(1)`.

### Insertion sort khi đoạn nhỏ

Với đoạn dài không quá `16` phần tử, ta duyệt từ trái sang phải, giữ một tiền tố đã sắp và chèn phần tử mới vào đúng vị trí bằng cách dịch những giá trị lớn hơn sang phải.

Bất biến của Insertion sort: trước mỗi vòng xử lý `i`, tiền tố `a[from..i-1]` đã có thứ tự không giảm và chứa đúng các phần tử ban đầu của tiền tố đó. Sau khi dịch các phần tử lớn hơn và chèn `a[i]` cũ, tiền tố tăng thêm một phần tử mà vẫn có thứ tự.

Mặc dù riêng một đoạn dài `k` có thể tốn `Θ(k²)`, việc cố định `k<=16` khiến mỗi đoạn tốn công việc bị chặn bằng một hằng số. Tổng chi phí trên các đoạn nhỏ vì vậy tỷ lệ tuyến tính với số phần tử.

## 5. Chương trình Java 17+ hoàn chỉnh

Mã sau là **một bản Introsort minh họa**, không phụ thuộc thư viện sắp xếp. Nó kết hợp:

- Quicksort với **trung vị ba mẫu** và **phân hoạch ba vùng**.
- Heapsort khi hết ngân sách độ sâu.
- Insertion sort cho đoạn có không quá `16` phần tử.
- Đệ quy **chỉ trên đoạn nhỏ hơn** và vòng lặp để xử lý đoạn lớn hơn nhằm giới hạn số khung lời gọi.

Kết quả sắp xếp tăng dần, **ngay trên mảng đầu vào**. Hàm công khai quy định `null` là đầu vào không hợp lệ và ném `IllegalArgumentException`. Mảng rỗng hoặc một phần tử hợp lệ và không cần xử lý.

Lưu dưới tên **`IntroSortDemo.java`**:

```java
import java.util.Arrays;

public final class IntroSortDemo {
    private static final int INSERTION_THRESHOLD = 16;

    private IntroSortDemo() {
    }

    public static void introSort(int[] a) {
        if (a == null) {
            throw new IllegalArgumentException("array must not be null");
        }
        if (a.length < 2) {
            return;
        }

        // floor(log2(n)) cho n >= 2; không dùng log số thực.
        int floorLog2 = 31 - Integer.numberOfLeadingZeros(a.length);
        int depthLimit = 2 * floorLog2;
        sortRange(a, 0, a.length, depthLimit);
    }

    // Xử lý khoảng nửa mở [from, to).
    private static void sortRange(
            int[] a, int from, int to, int depthLimit) {
        while (to - from > INSERTION_THRESHOLD) {
            if (depthLimit == 0) {
                heapSort(a, from, to);
                return;
            }
            depthLimit--;

            int mid = from + (to - from) / 2;
            int pivot = medianOfThree(a[from], a[mid], a[to - 1]);

            int lt = from;
            int i = from;
            int gt = to - 1;

            // [from,lt): < pivot
            // [lt,i): == pivot
            // [i,gt]: chưa xét
            // (gt,to): > pivot
            while (i <= gt) {
                if (a[i] < pivot) {
                    swap(a, lt, i);
                    lt++;
                    i++;
                } else if (a[i] > pivot) {
                    swap(a, i, gt);
                    gt--;
                    // Chưa tăng i: giá trị đổi từ cuối chưa xét.
                } else {
                    i++;
                }
            }

            // [lt,gt+1) đã bằng pivot, không cần sắp nữa.
            int leftLength = lt - from;
            int rightLength = to - (gt + 1);

            // Chỉ đệ quy vào đoạn nhỏ hơn.
            if (leftLength < rightLength) {
                sortRange(a, from, lt, depthLimit);
                from = gt + 1;
            } else {
                sortRange(a, gt + 1, to, depthLimit);
                to = lt;
            }
            // Vòng while tiếp tục xử lý đoạn lớn hơn.
        }

        insertionSort(a, from, to);
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

    private static void insertionSort(int[] a, int from, int to) {
        if (to - from < 2) {
            return;
        }
        for (int i = from + 1; i < to; i++) {
            int value = a[i];
            int j = i - 1;
            while (j >= from && a[j] > value) {
                a[j + 1] = a[j];
                j--;
            }
            a[j + 1] = value;
        }
    }

    // Heapsort chỉ trong [from,to), chỉ số heap là tương đối.
    private static void heapSort(int[] a, int from, int to) {
        int length = to - from;

        // Xây max-heap từ các nút cha, đi từ dưới lên.
        for (int root = length / 2 - 1; root >= 0; root--) {
            siftDown(a, from, root, length);
        }

        for (int end = length - 1; end > 0; end--) {
            swap(a, from, from + end);
            siftDown(a, from, 0, end);
        }
    }

    private static void siftDown(
            int[] a, int base, int root, int heapSize) {
        // Nút ở nửa sau không có con; điều kiện này cũng
        // tránh tính 2*root+1 khi root quá lớn.
        while (root < heapSize / 2) {
            int child = 2 * root + 1;
            if (child + 1 < heapSize
                    && a[base + child] < a[base + child + 1]) {
                child++;
            }
            if (a[base + root] >= a[base + child]) {
                return;
            }
            swap(a, base + root, base + child);
            root = child;
        }
    }

    private static void swap(int[] a, int i, int j) {
        int temp = a[i];
        a[i] = a[j];
        a[j] = temp;
    }

    public static void main(String[] args) {
        int[] mixed = {
            9, 4, 7, 3, 8, 1, 2, 5, 6, 0, 9,
            3, -2, 12, 10, 11, 4, 7, 5, 5, 1
        };
        introSort(mixed);
        System.out.println("Mixed: " + Arrays.toString(mixed));

        // Chủ động đặt độ sâu bằng 0 để kiểm tra nhánh cứu
        // bằng Heapsort; đây là kiểm thử hàm nội bộ.
        int[] forcedHeap = {
            19, 8, 14, 3, 0, 11, 5, 18, 7, 12,
            4, 16, 1, 10, 6, 17, 2, 13, 9, 15
        };
        sortRange(forcedHeap, 0, forcedHeap.length, 0);
        System.out.println("Heap fallback: "
                + Arrays.toString(forcedHeap));

        int[] allEqual = new int[40];
        Arrays.fill(allEqual, 7);
        introSort(allEqual);
        boolean allSeven = true;
        for (int x : allEqual) {
            if (x != 7) {
                allSeven = false;
                break;
            }
        }
        System.out.println("All equal: " + allSeven);

        int[] reverse = new int[32];
        for (int i = 0; i < reverse.length; i++) {
            reverse[i] = reverse.length - 1 - i;
        }
        introSort(reverse);
        System.out.println("Reverse endpoints: "
                + reverse[0] + ", " + reverse[reverse.length - 1]);

        int[] already = {-3, -1, 0, 5, 5, 9};
        introSort(already);
        System.out.println("Already sorted: "
                + Arrays.toString(already));

        int[] empty = {};
        introSort(empty);
        System.out.println("Empty length: " + empty.length);

        int[] one = {42};
        introSort(one);
        System.out.println("One: " + Arrays.toString(one));
    }
}
```

Dùng JDK 17 trở lên:

```bash
javac IntroSortDemo.java
java IntroSortDemo
```

Kết quả chuẩn:

```text
Mixed: [-2, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 5, 6, 7, 7, 8, 9, 9, 10, 11, 12]
Heap fallback: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
All equal: true
Reverse endpoints: 0, 31
Already sorted: [-3, -1, 0, 5, 5, 9]
Empty length: 0
One: [42]
```

**Cách đọc ví dụ:**

- `mixed` có số âm, số dương và nhiều bản sao. Kết quả vẫn giữ nguyên **tần suất** từng giá trị và có thứ tự không giảm.
- `forcedHeap` có `20 > 16` phần tử và gọi `sortRange` với ngân sách `0`, vì vậy thực sự đi qua nhánh **Heapsort dự phòng**. Đây là kiểm thử chủ động đường xử lý nội bộ, không phải lời gọi API thông thường.
- `allEqual` kiểm tra dãy có nhiều giá trị trùng. Phân hoạch ba vùng loại cả đoạn bằng chốt mà không phải chia lại từng bản sao.
- `reverse` kiểm tra dữ liệu ban đầu giảm dần; `already` kiểm tra dữ liệu đã tăng; `empty` và `one` xác nhận các trường hợp biên.

### Tại sao mã chỉ đệ quy vào một phía?

Sau phân hoạch, hai phía `< pivot` và `> pivot` độc lập. Thay vì gọi đệ quy cả hai phía, `sortRange` **gọi đệ quy cho phía nhỏ hơn** rồi thay `from` hoặc `to` để xử lý phía lớn hơn ngay trong vòng `while` hiện tại.

Vì phía được đệ quy có kích thước không quá một nửa đoạn đang xử lý, **số khung đệ quy đồng thời** bị chặn bởi `O(log n)`. Kỹ thuật này làm giảm rủi ro ngăn xếp sâu ngay cả trước khi tính đến ngân sách độ sâu. Toàn bộ chương trình vẫn có bộ nhớ phụ `O(log n)` do ngăn xếp, mặc dù các thao tác phân hoạch, Heap và Insertion không cấp thêm mảng.

## 6. Phân tích tính đúng

Để chứng minh Introsort đúng, cần kiểm tra từng thành phần và việc chuyển đổi giữa chúng.

**(1) Phân hoạch giữ nguyên tập phần tử.** Mỗi bước phân hoạch chỉ hoán đổi phần tử trong `[from,to)`, nên không thêm hoặc làm mất giá trị. Bất biến bốn vùng bảo đảm khi `i>gt`, mọi phần tử bên trái nhỏ hơn chốt, ở giữa bằng chốt và bên phải lớn hơn chốt. Vì thế, nếu sắp hai vùng ngoài thì toàn bộ đoạn đã sắp.

**(2) Phân hoạch không mắc kẹt.** Mỗi lượt xử lý hoặc tăng `i` hoặc giảm `gt`, nên số phần tử chưa xét `gt-i+1` giảm sau mỗi lượt. Kết thúc có ít nhất một phần tử ở vùng bằng chốt vì giá trị `pivot` được chọn từ chính đoạn. Các lời gọi tiếp theo xử lý đoạn nhỏ hơn đoạn ban đầu, hoặc gặp điều kiện dừng.

**(3) Insertion sort đúng trên đoạn nhỏ.** Bất biến tiền tố đã sắp và thao tác chèn đúng vị trí bảo đảm đoạn `[from,to)` có thứ tự sau khi thuật toán kết thúc. Nó chỉ dịch chuyển và chèn lại các phần tử đã có trong chính đoạn, nên bảo toàn đa tập giá trị.

**(4) Heapsort đúng trên đoạn được giao.** Max-heap có phần tử lớn nhất ở gốc. Mỗi lần đổi gốc với vị trí cuối của heap, một phần tử lớn nhất được đưa vào cuối vùng chưa sắp; sau khi giảm `end` và vun lại, phần đuôi đã sắp tiếp tục được mở rộng. Kết thúc cả đoạn có thứ tự và mọi hoán đổi đều nằm trong giới hạn `[from,to)`.

**(5) Chuyển chiến lược không phá bất biến.** Ở mọi lần gọi `sortRange`, các phần tử ngoài đoạn đã được đặt vào những vùng đúng theo các phân hoạch tổ tiên. Việc thay thuật toán xử lý **phần còn lại của cùng đoạn** chỉ hoán vị những phần tử trong đoạn ấy. Dù chọn Insertion sort, Heapsort hay tiếp tục Quicksort, kết quả hợp đồng cuối cùng vẫn đúng.

**(6) Thuật toán kết thúc.** Phân hoạch giảm kích thước đoạn hoặc giảm ngân sách độ sâu. Khi đoạn đủ nhỏ, Insertion sort xử lý hữu hạn bước; khi ngân sách bằng `0`, Heapsort kết thúc sau các vòng lặp hữu hạn. Vì vậy không có đường xử lý nào kéo dài vô hạn trên đầu vào hữu hạn hợp lệ.

**Giới hạn phạm vi của khẳng định:** đây là sắp xếp `int[]` theo thứ tự số tự nhiên. Nếu thay thành sắp xếp đối tượng với bộ so sánh tùy chọn, cần bộ so sánh **nhất quán** với quan hệ thứ tự (đặc biệt tính bắc cầu); bộ so sánh tự mâu thuẫn làm mất cơ sở chứng minh.

## 7. Tại sao Introsort có chặn xấu nhất `O(n log n)`?

Đặt `n` là số phần tử, `K=16` là ngưỡng đoạn nhỏ và `D=2⌊log₂n⌋` là ngân sách phân hoạch ban đầu.

**Giai đoạn Quicksort.** Mỗi lần phân hoạch một đoạn dài `m` chỉ duyệt đoạn đó số lần tỷ lệ với `m`, tức `O(m)`. Trên một mức phân hoạch, các đoạn được xử lý không chồng lặp, nên tổng số phần tử được quét tối đa `n`. Trên bất kỳ nhánh nào, số mức phân hoạch không vượt `D=O(log n)`. Do đó tổng chi phí phân hoạch bị chặn bởi **`O(n log n)`**, kể cả nếu các điểm chia rất lệch.

**Giai đoạn Heapsort.** Những đoạn được chuyển sang Heap là các đoạn **rời nhau** còn sót lại sau phân hoạch. Một đoạn dài `m` được Heapsort sắp trong `O(m log m)`. Tổng qua mọi đoạn Heap không vượt bậc `O(n log n)` vì tổng độ dài các đoạn này không lớn hơn `n`.

**Giai đoạn Insertion sort.** Những đoạn còn lại có nhiều nhất `K` phần tử mỗi đoạn. Mỗi đoạn độ dài `m<=K` tốn `O(mK)`; cộng lại không vượt `O(nK)`. Khi `K` là hằng số, phần này là `O(n)`.

Cộng ba loại công việc cho giới hạn xấu nhất **`O(n log n)`** khi `n>=2`. Trường hợp thường gặp với phân hoạch khá cân đối cũng có bậc `O(n log n)`. Với toàn bộ phần tử bằng nhau, phân hoạch ba vùng có thể xử lý toàn đoạn trong `O(n)` ở bản minh họa này; đó là tình huống thuận lợi, không thay đổi chặn xấu nhất.

| Tiêu chí | Với bản Introsort ở trên |
|---|---|
| Thời gian xấu nhất | `O(n log n)` với `n>=2` |
| Thời gian thường gặp | Gần `O(n log n)`, phụ thuộc dữ liệu và chi phí thao tác |
| Phân hoạch trên dãy toàn phần tử bằng nhau | `O(n)` khi đoạn đủ dài để dùng ba vùng |
| Bộ nhớ phụ | `O(log n)` ngăn xếp; không có mảng phụ tỷ lệ với `n` |
| Sắp xếp tại chỗ | **Có**, trong nghĩa không cần mảng phụ kích thước `Θ(n)` |
| Ổn định (stable) | **Không bảo đảm** |
| Bảo đảm số phần tử và tần suất | **Có**, vì chỉ hoán đổi/dịch chuyển trong mảng |

### Tại chỗ khác với ổn định

**Tại chỗ (in-place)** nói về bộ nhớ; **ổn định (stable)** nói về thứ tự tương đối giữa các phần tử có khóa bằng nhau. Introsort thường không ổn định vì các phép hoán đổi trong phân hoạch và Heapsort có thể đảo vị trí các bản ghi có khóa bằng nhau.

Ví dụ, hai bản ghi `(điểm=8, tên=A)` và `(điểm=8, tên=B)` ban đầu theo thứ tự A rồi B. Một thuật toán ổn định bắt buộc giữ A trước B sau khi sắp theo điểm; bản Introsort minh họa **không hứa** điều đó. Với mảng `int[]`, các bản sao bằng nhau trông giống hệt nhau nên không thể quan sát vấn đề ổn định từ giá trị số đơn thuần.

Nếu đề bài cần tính ổn định, nên chọn cách sắp xếp có hợp đồng ổn định hoặc đưa chỉ số xuất hiện ban đầu vào khóa so sánh một cách có chủ đích. Điều đó có thể thay đổi chi phí bộ nhớ và cấu trúc dữ liệu.

## 8. Khi nào nên dùng và điều gì cần cân nhắc?

**Phù hợp với Introsort khi:**

- Cần **sắp xếp so sánh trên dữ liệu tổng quát** với giới hạn xấu nhất chặt chẽ.
- Muốn tận dụng đặc tính thực dụng của Quicksort nhưng không chấp nhận một chuỗi phân hoạch lệch làm chi phí tăng tới `Θ(n²)`.
- Có thể sắp xếp tại chỗ và không bắt buộc ổn định.
- Dữ liệu có kích thước rất khác nhau; đoạn nhỏ đáng được xử lý bằng chiến lược riêng.

**Không tự động là lựa chọn tốt nhất khi:**

- Cần **stable sort** cho bản ghi có khóa bằng nhau; phải xác định hợp đồng này trước.
- Dữ liệu có đặc điểm cho phép sắp xếp không dựa trên so sánh, ví dụ các khóa nguyên trong miền nhỏ: Counting sort hoặc Radix sort có thể phù hợp hơn khi xét cả giới hạn bộ nhớ.
- Dữ liệu đã có nhiều đoạn có thứ tự sẵn và thuật toán thích nghi khai thác được những đoạn đó; một giải pháp kiểu trộn có nhận diện run có thể có lợi.
- Dữ liệu lớn hơn RAM và chi phí đọc/ghi trở thành yếu tố chính; cần tính tới sắp xếp ngoài bộ nhớ.
- Thư viện chuẩn đã cung cấp sắp xếp đúng hợp đồng; trong phần mềm thực tế, thường ưu tiên thư viện đã được kiểm thử và tối ưu kỹ, rồi mới tự viết một bản Introsort khi cần kiểm soát cụ thể.

**Không suy diễn thuật toán thư viện từ ví dụ:** chương trình Java này là một cài đặt minh họa tự viết. Sự tồn tại của `Arrays.sort` không có nghĩa mọi kiểu mảng/đối tượng và mọi phiên bản Java đều dùng chính ba chiến lược hoặc ngưỡng `16` như mã trên.

## 9. Lỗi phổ biến khi kết hợp thuật toán

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ chọn `pivot` tốt hơn rồi tuyên bố xấu nhất `O(n log n)` | Đầu vào đối kháng vẫn có thể làm Quicksort lệch liên tục | Theo dõi độ sâu và dùng thuật toán dự phòng có chặn thực sự |
| Quên giảm `depthLimit` sau phân hoạch | Không kích hoạt Heap đúng lúc | Giảm ngân sách cho mỗi mức phân hoạch |
| Chuyển sang Heap nhưng sắp toàn mảng | Phá phân tách đoạn của những nhánh khác, gây công việc dư hoặc lỗi | Truyền đúng `[from,to)` và chỉ thao tác trong đoạn |
| Đổi phần tử `> pivot` nhưng tăng ngay `i` | Bỏ qua phần tử chưa xét vừa đổi từ cuối | Giảm `gt` và kiểm tra lại `a[i]` |
| Quên vùng `== pivot` | Sắp lại nhiều bản sao vô ích | Phân hoạch ba vùng, chỉ xử lý hai vùng khác chốt |
| Không thống nhất khoảng `[from,to)` | Lệch chỉ số, bỏ phần tử cuối hoặc truy cập ngoài mảng | Dùng `to-from`, `to-1` nhất quán |
| Tính chỉ số giữa bằng `(from+to)/2` | Tổng hai chỉ số có thể tràn `int` | Dùng `from+(to-from)/2` |
| Tính con heap bằng `2*root+1` khi `root` bất kỳ | Có thể tràn số hoặc truy cập vượt vùng heap | Kiểm tra còn con trước; dùng chỉ số tương đối với `from` |
| Dùng Insertion sort cho đoạn quá lớn | Chi phí `O(k²)` bắt đầu chi phối | Giữ ngưỡng nhỏ, đo thực tế nếu cần điều chỉnh |
| Tuyên bố bản Introsort ổn định | Các bản ghi bằng khóa có thể bị đảo thứ tự | Kiểm tra hợp đồng stable và đổi giải pháp nếu cần |
| Bỏ qua kiểm thử nhiều giá trị bằng nhau | Có thể lặp phân hoạch vô ích hoặc sai logic ba vùng | Thử dãy toàn trùng và dãy có rất nhiều bản sao |
| Chỉ kiểm tra dữ liệu ngẫu nhiên | Không phát hiện đường dự phòng ít khi được kích hoạt | Thử nhánh Heapsort chủ động và các dạng dữ liệu biên |

### Kiểm thử có ý nghĩa

Vì Introsort là thuật toán lai, kiểm thử nên bao quát **các đường xử lý**, không chỉ một vài đầu vào:

1. **Rỗng và một phần tử:** không truy cập ngoài giới hạn.
2. **Đoạn nhỏ:** đảm bảo Insertion sort giữ thứ tự và tần suất.
3. **Đoạn lớn nhiều bản sao:** đảm bảo phân hoạch ba vùng xử lý đúng.
4. **Mảng tăng dần, giảm dần, gần sắp xếp, toàn bằng nhau:** phát hiện thiên lệch của `pivot` và lỗi ranh giới.
5. **Có số âm, `Integer.MIN_VALUE`, `Integer.MAX_VALUE`:** kiểm tra so sánh không dùng phép trừ hai giá trị có thể tràn.
6. **Heapsort trên đoạn con có `from>0`:** bảo đảm các phần tử nằm ngoài đoạn không bị thay đổi.
7. **Cạn ngân sách độ sâu:** gọi đường Heap một cách có kiểm soát như ví dụ, xác nhận chiến lược dự phòng hoạt động.
8. **Đối chiếu nhiều mảng ngẫu nhiên:** so kết quả với một trình sắp xếp đáng tin và kiểm tra cả **thứ tự** lẫn **đa tập giá trị**.

Chỉ kiểm tra `a[i]<=a[i+1]` là chưa đủ: một chương trình làm mất hoặc nhân đôi phần tử vẫn có thể cho mảng có thứ tự. Đối chiếu với một bản sắp chuẩn hoặc kiểm tra tần suất giá trị giúp phát hiện lỗi bảo toàn dữ liệu.

## 10. Bài tập tự luyện

**Bài 1 — Lựa chọn chiến lược.** Với `n=64` và ngưỡng `K=16`, ngân sách ban đầu `2⌊log₂64⌋` là bao nhiêu? Nếu một nhánh vẫn dài hơn `16` sau khi dùng hết ngân sách, bước tiếp theo là gì?

*Đáp án đối chiếu:* ngân sách `12`; nhánh còn lớn chuyển sang Heapsort, không tiếp tục phân hoạch Quicksort.

**Bài 2 — Bất biến ba vùng.** Giả sử `pivot=5` và một vị trí `a[i]>5`. Vì sao sau khi đổi `a[i]` với `a[gt]` ta được phép giảm `gt` nhưng **không** tăng ngay `i`?

*Gợi ý:* giá trị vừa chuyển từ `gt` sang `i` chưa được phân loại; nếu tăng `i` sẽ có nguy cơ bỏ sót nó.

**Bài 3 — Tính đúng của dự phòng.** Tại sao dùng Heapsort để sắp một đoạn con không làm mất những bảo đảm đã đạt được qua các lần phân hoạch ở phía trên?

*Gợi ý:* đoạn con chỉ chứa những giá trị thuộc vùng `< pivot` hoặc `> pivot` theo các bất biến tổ tiên; Heapsort hoán đổi **bên trong đoạn ấy**, nên không thay đổi các quan hệ giữa những vùng đã phân chia.

**Bài 4 — Tổng chi phí.** Nếu có rất nhiều đoạn nhỏ, mỗi đoạn dài tối đa `K` và được sắp bằng Insertion sort `O(K²)`, vì sao tổng chi phí không tự biến thành `O(n²)`?

*Gợi ý:* tổng độ dài các đoạn không vượt `n`. Mỗi đoạn dài `m<=K` tốn `O(mK)`, nên tổng là `O(nK)`; khi `K` cố định thì `O(n)`.

**Bài 5 — Ổn định.** Cho các bản ghi `(8,A)`, `(3,C)`, `(8,B)` và sắp tăng theo khóa số. Một kết quả nào chứng minh thuật toán không ổn định?

*Đáp án:* `(3,C),(8,B),(8,A)` vẫn có thứ tự theo khóa nhưng đã đảo hai bản ghi khóa `8` so với đầu vào.

**Bài 6 — Kiểm thử đoạn Heap.** Hãy tạo mảng có các giá trị đánh dấu cố định ở ngoài `[from,to)`, gọi riêng Heapsort trên đoạn giữa và kiểm tra rằng hai vùng ngoài không bị chỉnh sửa.

*Gợi ý:* dùng mảng có đầu/cuối là những giá trị dễ nhận biết, chọn `from>0`, `to<a.length`, rồi kiểm tra toàn bộ vùng ngoài đoạn trước và sau khi sắp.

## Ghi nhớ

**Introsort là một cơ chế điều phối các chiến lược theo tình huống:** dùng Quicksort để phân hoạch hiệu quả, chuyển sang Heapsort nếu nhánh phân hoạch quá sâu, và dùng Insertion sort cho đoạn ngắn. Cần hiểu đồng thời **bất biến phân hoạch, ngân sách độ sâu, ranh giới đoạn con và hợp đồng sắp xếp**. Sự kết hợp đúng giúp có **`O(n log n)` trong trường hợp xấu nhất**, bộ nhớ ngăn xếp `O(log n)` và hành vi thực tế tốt trên nhiều kiểu dữ liệu, dù thuật toán không mặc nhiên ổn định.
