# Heapsort và lựa chọn phần tử qua heap

## 1. Bài toán và vai trò của heap

Khi xử lý một tập phần tử, ta có thể gặp hai loại yêu cầu gần nhau nhưng không giống nhau:

1. **Sắp xếp toàn bộ**: đưa n phần tử về thứ tự tăng dần hoặc giảm dần.
2. **Lựa chọn theo thứ hạng**: tìm phần tử nhỏ/lớn thứ k, giữ k phần tử lớn nhất (top-k), hoặc liên tục lấy phần tử có độ ưu tiên cao nhất.

**Heap** (đống) là cấu trúc dữ liệu giúp truy cập phần tử cực trị nhanh mà không phải duy trì toàn bộ tập ở thứ tự đã sắp xếp. Từ cùng một ý tưởng heap, ta có:

- **Heapsort**: tạo max-heap trên mảng, liên tục chuyển phần tử lớn nhất về cuối mảng để sắp xếp tăng dần; độ phức tạp xấu nhất O(n log n), bộ nhớ phụ O(1) với cài đặt tại chỗ.
- **Lựa chọn phần tử qua heap**: giữ một min-heap kích thước k để tìm phần tử lớn thứ k hoặc top-k lớn nhất mà không cần sắp xếp toàn bộ n phần tử; thường O(n log(k+1)) thời gian và O(k) bộ nhớ.
- **Trích k phần tử lớn nhất từ max-heap**: xây heap O(n), sau đó lấy cực đại k lần với chi phí O(k log n); hữu ích khi cần khai thác dãy ngay trong mảng có thể bị thay đổi.

Điểm cần phân biệt: **heap không phải mảng được sắp xếp**. Nó chỉ bảo đảm quan hệ giữa nút cha với các con, không bảo đảm mọi nút anh em hoặc mọi phần tử ở cùng mức có thứ tự.

## 2. Binary heap: cấu trúc và bất biến

Heap nhị phân (binary heap) là **cây nhị phân hoàn chỉnh**: mọi mức trừ mức cuối đều đầy, các nút ở mức cuối được điền liên tiếp từ trái sang phải. Tính chất này cho phép lưu các nút liên tục trong một mảng, không cần đối tượng nút hay con trỏ.

Với mảng đánh chỉ số từ 0, một nút ở chỉ số i có:

~~~text
parent(i) = (i - 1) / 2          (i > 0)
left(i)   = 2 * i + 1
right(i)  = 2 * i + 2
~~~

Chỉ số con chỉ hợp lệ nếu nhỏ hơn kích thước heap đang xét.

**Max-heap** duy trì bất biến a[parent] ≥ a[child] với mọi cạnh cha-con; vì vậy phần tử lớn nhất nằm ở a[0]. **Min-heap** dùng chiều ngược lại, cha ≤ con, nên phần tử nhỏ nhất ở gốc. Hai bất biến đều cho phép giá trị trùng.

Ví dụ mảng [9, 7, 8, 2, 4, 5] là một max-heap:

~~~text
            9
          /   \
         7     8
        / \   /
       2   4 5
~~~

Nhưng [9, 7, 8, 2, 4, 5] **không phải** dãy tăng dần hay giảm dần. Phần tử thứ hai của mảng không nhất thiết là phần tử lớn thứ hai: hai con của gốc có thể nằm ở bất kỳ thứ tự nào với nhau. Chỉ khi gốc được đưa ra và heap được khôi phục, gốc mới lại là cực đại của các phần tử còn lại.

### Các thao tác nền tảng

| Thao tác | Ý nghĩa | Chi phí với heap có n phần tử |
| --- | --- | --- |
| peek | Xem cực trị ở gốc, không xóa | O(1) |
| offer/insert | Thêm nút ở cuối rồi đẩy lên (sift-up) | O(log n) |
| poll/extract | Lấy gốc, đưa phần tử cuối lên gốc rồi đẩy xuống (sift-down) | O(log n) |
| sift-down | Khôi phục thuộc tính heap khi gốc một cây con có thể sai | O(log n) |
| build heap từ dưới lên | Biến mảng tùy ý thành heap | O(n) |
| Tra một giá trị tùy ý | Không tận dụng được thứ tự toàn cục | O(n) trong trường hợp tổng quát |

Chi phí logarit đến từ chiều cao cây hoàn chỉnh là O(log n). Việc chỉ đọc cực trị O(1) là khác biệt cơ bản với việc phải tìm kiếm một giá trị bất kỳ, vốn không được heap hỗ trợ nhanh.

## 3. Hai phép điều chỉnh: sift-up và sift-down

### Sift-up khi chèn

Để thêm x vào một heap động, đặt x vào vị trí cuối cùng. Nếu nó phá quan hệ với cha, hoán đổi với cha; tiếp tục đến khi đúng hoặc đạt gốc.

- Min-heap: đẩy lên khi x nhỏ hơn cha.
- Max-heap: đẩy lên khi x lớn hơn cha.
- Trong trường hợp x đi qua toàn bộ chiều cao heap, cần O(log n) lần so sánh/hoán đổi.

Ví dụ với max-heap [9, 7, 8, 2, 4, 5], thêm 10 ở cuối tạo [9, 7, 8, 2, 4, 5, 10]. So sánh 10 với cha 8, đổi thành [9, 7, 10, 2, 4, 5, 8]; tiếp tục đổi với 9, thành [10, 7, 9, 2, 4, 5, 8], là max-heap hợp lệ.

### Sift-down khi lấy gốc hoặc dựng heap

Nếu gốc của một cây con có thể nhỏ hơn con (đối với max-heap), ta chọn **đứa con lớn hơn** và hoán đổi với gốc nếu cần. Sau đó lặp ở vị trí mới. Việc chọn con lớn hơn là bắt buộc: chọn nhầm con nhỏ hơn có thể để gốc nhỏ hơn con còn lại và làm hỏng max-heap.

Ví dụ max-heap [10, 7, 9, 2, 4, 5, 8]. Lấy 10 ra, đưa 8 lên gốc: [8, 7, 9, 2, 4, 5]. So sánh gốc 8 với hai con 7 và 9, đổi với 9: [9, 7, 8, 2, 4, 5], là max-heap trở lại.

### Điều kiện dùng sift-down

Sift-down đúng khi **các cây con dưới nút đang xét đã là heap**. Nó giải quyết vị trí gốc sai trong khi phần còn lại của cây con đúng; đây chính là cơ sở của thuật toán build-heap từ dưới lên.

Trong mảng 0-based, các nút từ n/2 đến n-1 là lá, nên đã tự thỏa thuộc tính heap. Ta chỉ cần xét các nút cha theo thứ tự:

~~~text
for i = floor(n / 2) - 1 down to 0:
    siftDown(a, i, n)
~~~

Mỗi lượt khôi phục heap ở một cây con sau khi hai cây con bên dưới đã được xây dựng. Kết thúc ở i=0, toàn bộ mảng trở thành max-heap.

## 4. Vì sao build-heap từ dưới lên là O(n), không phải O(n log n)?

Mỗi lần sift-down riêng lẻ tốn nhiều nhất O(log n), nhưng không phải nút nào cũng phải đi nhiều mức:

- Gần một nửa số nút là **lá**, không cần dịch chuyển.
- Khoảng một phần tư số nút nằm gần lá, có thể dịch chuyển tối đa khoảng một mức.
- Chỉ rất ít nút gần gốc có khả năng dịch chuyển O(log n) mức.

Nếu nhóm theo độ cao h, tổng công xấp xỉ:

~~~text
O(n * (1/2^1 * 0 + 1/2^2 * 1 + 1/2^3 * 2 + ...))
= O(n * sum(h / 2^h))
= O(n)
~~~

Chuỗi tổng theo h hội tụ đến một hằng số, nên xây heap bằng cách sift-down từ dưới lên tốn **O(n)**. Ngược lại, nếu xây heap bằng cách chèn từng phần tử độc lập, có thể tốn O(n log n).

Đây là khác biệt quan trọng khi phân tích heapsort: toàn bộ quá trình là **O(n) để dựng heap + O(n log n) để lấy cực trị**, không phải O(n log n) cho riêng bước dựng từ dưới lên.

Ví dụ với [4, 1, 7, 3, 8, 5], n=6:

~~~text
Khoi tao:           [4, 1, 7, 3, 8, 5]
siftDown tai i=2:   [4, 1, 7, 3, 8, 5]   (7 >= 5)
siftDown tai i=1:   [4, 8, 7, 3, 1, 5]   (1 doi voi 8)
siftDown tai i=0:   [8, 4, 7, 3, 1, 5]   (4 doi voi 8)
~~~

Mảng cuối là max-heap: 8 ở gốc, hai con 4 và 7, và các nút con đều không lớn hơn cha tương ứng.

## 5. Heapsort tăng dần: từng bước và bất biến

Heapsort tăng dần sử dụng **max-heap**. Nếu dùng min-heap rồi chuyển cực tiểu về cuối bằng cùng thủ tục, kết quả sẽ theo chiều ngược.

Quy trình:

1. Xây max-heap trên toàn bộ n phần tử, chi phí O(n).
2. Hoán đổi a[0] (cực đại của heap) với a[end], phần tử cuối của vùng heap hiện tại.
3. Rút kích thước heap về end: phần tử ở a[end] đã về đúng vị trí của mảng đã sắp.
4. Sift-down từ gốc trong vùng [0,end) để khôi phục max-heap.
5. Lặp cho đến khi vùng heap chỉ còn một phần tử.

Giả mã:

~~~text
heapSort(a):
    n = length(a)
    for i = floor(n/2) - 1 down to 0:
        siftDownMax(a, i, n)

    for end = n - 1 down to 1:
        swap(a[0], a[end])
        siftDownMax(a, 0, end)
~~~

Trong vòng lặp thứ hai, **end là chỉ số phần tử vừa được đưa về cuối**, còn kích thước heap mới chính là end; chỉ xử lý các chỉ số 0..end-1. Không được tiếp tục sift-down trên toàn bộ n phần tử vì sẽ phá vùng đã sắp.

### Bất biến của pha trích cực đại

Tại đầu mỗi vòng lặp, mảng được chia thành hai đoạn:

- **Tiền tố [0,end]** (theo chỉ số đóng trước khi hoán đổi) là max-heap.
- **Hậu tố (end,n)** đã được sắp tăng dần và chứa các phần tử lớn nhất đã trích ra; mỗi phần tử trong hậu tố không nhỏ hơn mọi phần tử còn trong heap.

Hoán đổi đưa phần tử lớn nhất trong tiền tố đến end, nên nó thuộc đúng vị trí trong hậu tố cuối cùng. Sau khi thu hẹp heap, sift-down chỉ khôi phục bất biến trong tiền tố; hậu tố không bị động tới. Sau n-1 lượt, toàn bộ mảng tăng dần.

### Phân tích độ phức tạp

- Dựng max-heap: O(n).
- Có n-1 lần trích cực đại; mỗi lần hoán đổi O(1) và sift-down O(log n).
- Tổng thời gian: **O(n log n) trong trường hợp xấu nhất** với n đủ lớn; heap có cấu trúc không phụ thuộc dữ liệu đầu vào có sắp xếp hay chưa.
- Bộ nhớ phụ: **O(1)** nếu dùng mảng đầu vào và sift-down lặp, như ví dụ bên dưới. Nếu sao chép mảng để giữ nguyên dữ liệu gốc, bản sao tốn O(n), không còn là O(1) cho toàn bộ thao tác của người gọi.
- Tính ổn định: **không ổn định (not stable)**. Hai phần tử bằng khóa có thể đổi thứ tự xuất hiện tương đối sau các phép hoán đổi xa.

Heapsort có bảo đảm thời gian xấu nhất tốt và không cần bộ nhớ phụ tuyến tính, nhưng trong thực tế thường có locality bộ nhớ kém hơn một số cách sắp xếp khác và nhiều phép so sánh/hoán đổi; **O(n log n)** không bảo đảm luôn nhanh nhất với mọi n.

## 6. Lựa chọn phần tử lớn thứ k bằng min-heap kích thước k

Cho n giá trị và số nguyên k với 1 ≤ k ≤ n. Nếu sắp toàn bộ dãy **giảm dần**, phần tử lớn thứ k là phần tử tại chỉ số k-1. Ở đây, **các giá trị trùng được tính theo số lần xuất hiện**, trừ khi đề bài yêu cầu “lớn thứ k phân biệt”.

Ví dụ dãy [7, 1, 9, 3, 9, 2]:

~~~text
Sap giam dan: [9, 9, 7, 3, 2, 1]
k = 1: 9
k = 2: 9     (vi trung lap duoc tinh hai lan)
k = 3: 7
k = 4: 3
~~~

Nếu chỉ cần phần tử lớn thứ k, không nhất thiết phải sắp n phần tử. Ta giữ **min-heap có nhiều nhất k phần tử**, biểu diễn k giá trị lớn nhất đã thấy:

1. Nếu heap chưa đủ k phần tử, thêm x vào heap.
2. Nếu heap đã đủ k phần tử và x > heap.peek(), bỏ phần tử nhỏ nhất trong heap rồi thêm x.
3. Nếu x ≤ heap.peek(), giữ nguyên heap.
4. Khi đã duyệt hết, **heap.peek() chính là giá trị lớn thứ k** (với k≥1).

Vì sao dùng **min-heap** để chọn các giá trị **lớn nhất**? Gốc là phần tử **nhỏ nhất trong nhóm k phần tử lớn nhất đã chọn**, tức phần tử yếu nhất cần loại khi xuất hiện ứng viên tốt hơn. Đây là ứng viên thay thế được truy cập O(1).

### Bất biến lựa chọn

Sau khi xét t phần tử:

- Nếu t<k, heap chứa đúng các t phần tử đã thấy.
- Nếu t≥k, đa tập phần tử trong heap là **k phần tử lớn nhất** của t phần tử đã thấy, tính cả bản sao trùng.
- Phần tử ở gốc là nhỏ nhất trong k phần tử đang chọn.

Khi phần tử mới x không lớn hơn gốc, nó không thể thay thế bất kỳ phần tử nào trong nhóm top-k (do mọi phần tử trong heap ≥ gốc). Khi x lớn hơn gốc, loại gốc và đưa x vào giúp giữ đúng k phần tử lớn nhất. Bất biến đúng sau mỗi bước. Sau khi duyệt hết n phần tử, gốc là phần tử lớn thứ k.

**Độ phức tạp:** có n lượt xét; mỗi lượt thay hoặc thêm vào heap O(log k) ở trường hợp xấu nhất, nên tổng O(n log(k+1)); với k=1, thuật toán thực chất là theo dõi max trong O(n). Bộ nhớ phụ O(k). So với sắp toàn bộ O(n log n), cách này hữu ích khi k nhỏ hơn n rất nhiều hoặc dữ liệu đến theo luồng.

## 7. Lấy danh sách top-k và các biến thể lựa chọn

Nếu cần **cả k phần tử lớn nhất**, ta có thể dùng cùng min-heap k phần tử. Tuy nhiên, thứ tự lặp (iterator) của PriorityQueue **không phải thứ tự tăng hay giảm**; để xuất kết quả đã sắp giảm dần, cần đưa k giá trị sang danh sách rồi sắp xếp O(k log k).

- **Top-k lớn nhất, giữ trùng:** min-heap kích thước k.
- **Top-k nhỏ nhất, giữ trùng:** max-heap kích thước k; loại phần tử **lớn nhất** đang giữ khi gặp ứng viên nhỏ hơn.
- **Phần tử lớn thứ k phân biệt:** cần loại trùng trước (ví dụ HashSet hoặc tập có thứ tự), sau đó chọn trên các **giá trị phân biệt**. K lúc này phải ≤ số giá trị phân biệt.
- **Trích k phần tử lớn nhất từ max-heap:** build-heap O(n), trích k lần O(k log n), tổng O(n+k log n); thường thay đổi mảng và có thể phù hợp khi k nhỏ mà đầu vào cho phép sửa.
- **Sắp xếp tất cả rồi lấy k phần tử:** O(n log n) thời gian; đơn giản nếu vẫn cần toàn bộ mảng đã sắp.
- **Quickselect:** có thể tìm thứ hạng với thời gian trung bình O(n) trong một số cách chọn pivot nhưng trường hợp xấu nhất của bản đơn giản là O(n²); nếu cần top-k đã sắp xếp, vẫn cần sắp các k phần tử kết quả. Không thể khẳng định heap là lựa chọn tốt nhất cho mọi k.

**Chú ý thứ tự và tính ổn định:** nếu hai phần tử có cùng điểm nhưng gắn kèm id hoặc thời gian đến, yêu cầu top-k có thể cần quy tắc hòa rõ ràng. Một heap so sánh duy nhất theo điểm không tự giữ thứ tự đến; hãy dùng comparator xét điểm và khóa phụ (chẳng hạn số thứ tự ban đầu) nếu cần kết quả xác định.

### Khi nào k quá nhỏ hoặc quá lớn?

Với k=1, chỉ cần quét tìm max O(n), O(1) bộ nhớ; heap là không cần thiết nếu không có yêu cầu phát triển khác. Với k gần n, heap k phần tử phải giữ gần toàn bộ dữ liệu và thực hiện nhiều thao tác logarit; sắp xếp toàn bộ có thể đơn giản hơn. Với n lớn nhưng k nhỏ, heap k phần tử dùng bộ nhớ O(k) và giữ được ứng viên liên tục trong khi đọc từng giá trị, phù hợp xử lý luồng.

## 8. Java 17+: Heapsort và lựa chọn top-k độc lập

Ví dụ sử dụng **mảng int[]** để cài đặt heapsort tại chỗ bằng max-heap, và PriorityQueue<Integer> là min-heap để chọn k giá trị lớn nhất. Mảng truyền vào hàm heapSort bị sắp xếp tại chỗ; hai hàm lựa chọn **không sửa** mảng đầu vào.

Lưu mã thành **HeapSortSelectionDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;

public class HeapSortSelectionDemo {

    // a[0..size-1] la vung heap dang xet.
    // Hai cay con cua root da thoa man tinh chat max-heap.
    private static void siftDownMax(int[] a, int root, int size) {
        while (root < size / 2) {
            int child = 2 * root + 1; // Con trai chac chan ton tai.
            if (child + 1 < size && a[child + 1] > a[child]) {
                child++;               // Chon con lon hon.
            }
            if (a[root] >= a[child]) {
                break;
            }
            swap(a, root, child);
            root = child;
        }
    }

    private static void swap(int[] a, int i, int j) {
        int temp = a[i];
        a[i] = a[j];
        a[j] = temp;
    }

    public static void heapSort(int[] a) {
        if (a == null) {
            throw new IllegalArgumentException("array must not be null");
        }

        int n = a.length;
        for (int i = n / 2 - 1; i >= 0; i--) {
            siftDownMax(a, i, n);
        }

        for (int end = n - 1; end > 0; end--) {
            swap(a, 0, end);
            siftDownMax(a, 0, end);
        }
    }

    // Goi voi 1 <= k <= a.length. Giup giu k gia tri lon nhat.
    private static PriorityQueue<Integer> largestKHeap(int[] a, int k) {
        PriorityQueue<Integer> minHeap = new PriorityQueue<>();

        for (int value : a) {
            if (minHeap.size() < k) {
                minHeap.offer(value);
            } else if (value > minHeap.peek()) {
                minHeap.poll();
                minHeap.offer(value);
            }
        }
        return minHeap;
    }

    public static int kthLargest(int[] a, int k) {
        if (a == null) {
            throw new IllegalArgumentException("array must not be null");
        }
        if (k < 1 || k > a.length) {
            throw new IllegalArgumentException("k must be in [1, length]");
        }
        return largestKHeap(a, k).peek();
    }

    public static List<Integer> topKLargestSorted(int[] a, int k) {
        if (a == null) {
            throw new IllegalArgumentException("array must not be null");
        }
        if (k < 0 || k > a.length) {
            throw new IllegalArgumentException("k must be in [0, length]");
        }
        if (k == 0) {
            return List.of();
        }

        List<Integer> result = new ArrayList<>(largestKHeap(a, k));
        result.sort(Comparator.reverseOrder());
        return result;
    }

    public static void main(String[] args) {
        int[] original = {7, 1, 9, 3, 9, 2};
        int[] sorted = original.clone();
        heapSort(sorted);

        System.out.println("sorted = " + Arrays.toString(sorted));
        System.out.println("original = " + Arrays.toString(original));
        System.out.println("third largest = " + kthLargest(original, 3));
        System.out.println("top 4 = " + topKLargestSorted(original, 4));
        System.out.println("top 0 = " + topKLargestSorted(original, 0));

        int[] negatives = {-5, -1, -8, -1};
        heapSort(negatives);
        System.out.println("negative sorted = " + Arrays.toString(negatives));

        try {
            kthLargest(original, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid k = " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên trong thư mục chứa tệp:

~~~bash
javac HeapSortSelectionDemo.java
java HeapSortSelectionDemo
~~~

**Stdout chính xác:**

~~~text
sorted = [1, 2, 3, 7, 9, 9]
original = [7, 1, 9, 3, 9, 2]
third largest = 7
top 4 = [9, 9, 7, 3]
top 0 = []
negative sorted = [-8, -5, -1, -1]
invalid k = k must be in [1, length]
~~~

### Phân tích tính đúng của cài đặt

- Vòng while trong siftDownMax chỉ chạy khi nút root còn con trái. Phép thử root < size/2 tương đương 2*root+1 < size với kích thước không âm, đồng thời tránh tính chỉ số con khi không tồn tại; trong miền này phép nhân không tràn int.
- Ta so sánh với cả hai con và chọn con lớn hơn; nếu a[root] ≥ con lớn hơn thì thuộc tính max-heap tại root đã đúng. Nếu chưa đúng, hoán đổi rồi tiếp tục ở cây con vừa nhận phần tử nhỏ hơn.
- Vòng dựng heap bắt đầu từ nút cha cuối n/2-1, đưa tất cả cây con về max-heap theo thứ tự từ dưới lên. Nó chạy hợp lệ với n=0 hoặc n=1 vì bắt đầu với i âm và bỏ qua vòng nếu không cần thiết.
- Vòng heapsort luôn đưa cực đại của tiền tố hiện tại sang vị trí end rồi giảm kích thước heap, nên hậu tố không bị thay đổi. Kết quả là thứ tự tăng dần, kể cả số âm và các giá trị trùng nhau.
- Trong largestKHeap, minHeap.peek() là giá trị nhỏ nhất trong các ứng viên top-k hiện tại. Hàm được gọi chỉ khi k≥1; nhánh topKLargestSorted(k=0) trả kết quả rỗng ngay, tránh đọc peek từ heap rỗng.
- Cả kthLargest và topKLargestSorted đếm các giá trị trùng theo số lượng xuất hiện. Với original, hai số 9 đứng đầu thứ hạng, nên phần tử lớn thứ ba là 7; top-4 là [9,9,7,3].
- Comparator.reverseOrder() dùng so sánh hợp lệ cho Integer. Nếu tự tạo comparator cho số nguyên, dùng Integer.compare(b,a) thay vì b-a để tránh tràn.

### Độ phức tạp của từng hàm

| Hàm | Thời gian | Bộ nhớ phụ | Có sửa mảng đầu vào? |
| --- | --- | --- | --- |
| heapSort(a) | O(n log n) | O(1) | Có |
| kthLargest(a,k) | O(n log(k+1)) | O(k) | Không |
| topKLargestSorted(a,k) | O(n log(k+1) + k log k) với k≥1 | O(k) | Không |

Việc main dùng original.clone() phát sinh bản sao O(n) để vẫn in nguyên mảng ban đầu. Đó là chi phí của yêu cầu giữ dữ liệu nguồn, **không phải** bộ nhớ phụ nội tại của thuật toán heapsort trên mảng đã được cung cấp.

## 9. Những trường hợp biên và hợp đồng đầu vào

| Trường hợp | Heapsort | Tìm kthLargest / top-k |
| --- | --- | --- |
| Mảng null | Từ chối; ví dụ ném IllegalArgumentException | Từ chối tương tự |
| Mảng rỗng | Sắp xếp thành mảng rỗng hợp lệ | kthLargest không có k hợp lệ; top-k với k=0 cho [] |
| Một phần tử | Không cần hoán đổi | kthLargest(a,1) trả phần tử đó |
| Có số âm | So sánh số nguyên bình thường; vẫn đúng | Min-heap/top-k vẫn đúng |
| Có phần tử trùng | Được giữ đủ số bản sao | KthLargest đếm theo vị trí trong dãy đã sắp, không loại trùng |
| k=0 | Không liên quan | kthLargest báo lỗi; topKLargestSorted trả [] |
| k>n hoặc k<0 | Không liên quan | Báo lỗi đầu vào |
| Tất cả giá trị bằng nhau | Kết quả vẫn đúng nhưng thứ tự gắn với id không ổn định | k-th trả cùng giá trị; nếu cần thứ tự theo id phải đặt comparator |
| Giá trị Integer.MIN_VALUE/MAX_VALUE | Không phải cộng hoặc trừ để so sánh | Dùng so sánh/Integer.compare; tránh comparator kiểu b-a |
| Yêu cầu không sửa đầu vào | Phải sao chép trước rồi heapsort bản sao | Hai hàm heap selection ở ví dụ vốn không sửa mảng |

**Độ ổn định:** với bản ghi (score,id), nếu hai score bằng nhau mà muốn giữ thứ tự id ban đầu, heapsort thông thường không giữ được. Sự ổn định không quan trọng với int[] chỉ chứa giá trị, nhưng quan trọng khi sắp các bản ghi. Cần chọn thuật toán ổn định hoặc bổ sung quy tắc so sánh theo chỉ số gốc nếu nghiệp vụ yêu cầu.

**Tính xác định:** PriorityQueue không cam kết iteration có thứ tự, nên topKLargestSorted phải sắp danh sách kết quả. Nếu cần duy trì thứ tự đến trong trường hợp bằng ưu tiên, lưu thêm sequence number và so sánh khóa phụ.

## 10. So sánh với các chiến lược khác

| Nhu cầu | Cách thường cân nhắc | Lý do / đánh đổi |
| --- | --- | --- |
| Sắp xếp toàn bộ với bảo đảm O(n log n) xấu nhất và O(1) phụ | Heapsort tại chỗ | Không ổn định, locality có thể kém |
| Sắp xếp toàn bộ theo thứ tự ổn định | Merge sort hoặc cách sắp xếp ổn định phù hợp kiểu dữ liệu | Thường cần thêm bộ nhớ |
| Cần chỉ một phần tử lớn thứ k khi k rất nhỏ | Min-heap kích thước k | O(n log(k+1)), bộ nhớ O(k) |
| Cần top-k từ nguồn streaming | Min-heap kích thước k | Không cần giữ toàn bộ n giá trị |
| Cần k phần tử lớn nhất từ một mảng có thể sửa | Build max-heap rồi trích k lần | O(n+k log n); có thể dùng chính mảng làm heap |
| Cần một thứ hạng trong mảng, không cần sắp cả dãy | Quickselect | Thời gian kỳ vọng tuyến tính ở phiên bản pivot phù hợp; xấu nhất của cách cơ bản có thể O(n²) |
| Cần mọi phần tử đã sắp và nhiều truy vấn thứ hạng | Sắp xếp một lần | O(n log n) rồi truy cập theo chỉ số O(1) |
| Chỉ cần max/min một lần | Quét tuyến tính | O(n) thời gian, O(1) bộ nhớ, không cần heap |

Chọn cấu trúc theo thao tác thực tế: heap hữu ích khi liên tục lấy cực trị hoặc duy trì nhóm ưu tiên; nếu chỉ cần truy cập phần tử ở chỉ số i, một mảng đã có dữ liệu là đủ. Nếu cần tìm một khóa bằng nhau tùy ý, heap không đảm bảo tra nhanh như HashMap.

### Heap nhị phân có bảo đảm gì và không bảo đảm gì?

- **Có:** gốc là min/max theo quy tắc so sánh; chèn và trích gốc O(log n); xây từ mảng O(n).
- **Không:** toàn mảng đã sắp; các phần tử anh em có thứ tự; tìm một giá trị tùy ý O(log n); iteration của PriorityQueue cho kết quả đã sắp; tự duy trì thứ tự ổn định khi khóa trùng.
- **Đối với Java:** PriorityQueue mặc định là min-heap theo natural ordering. Để lấy phần tử lớn nhất trước, có thể dùng PriorityQueue<>(Comparator.reverseOrder()). Không nên coi PriorityQueue là heap của các tham chiếu thay đổi khóa tùy ý trong lúc ở heap; thay đổi khóa mà không tái tổ chức có thể phá thứ tự ưu tiên.

## 11. Kiểm thử theo bất biến và thuộc tính

Không chỉ kiểm tra output của vài ví dụ. Có thể xác minh tính chất của thuật toán:

1. **Sau build-heap:** với mọi i>0, a[(i-1)/2] ≥ a[i] trong max-heap.
2. **Sau mỗi bước heapsort:** hậu tố đã sắp tăng dần; mọi phần tử trong hậu tố không nhỏ hơn phần tử còn trong heap.
3. **Sau heapsort:** a[i]≤a[i+1] với mọi i hợp lệ; số lần xuất hiện của mỗi giá trị phải giống mảng ban đầu.
4. **Sau khi xử lý t phần tử trong heap chọn top-k:** heap có min(k,t) phần tử và chứa đúng các phần tử lớn nhất của tiền tố, tính cả bản sao.
5. **Kth largest:** nếu sắp toàn bộ bản sao theo chiều giảm dần để làm đối chứng, kết quả phải bằng phần tử thứ k, với 1≤k≤n.
6. **Top-k:** danh sách có k phần tử, sắp giảm dần, đa tập phần tử bằng k giá trị đầu của dãy đối chứng giảm dần.
7. **Không sửa mảng:** các hàm lựa chọn giữ nguyên các phần tử đầu vào; riêng heapSort phải được gọi trên bản sao nếu cần bảo toàn.

Bộ thử tối thiểu:

| Dữ liệu | Điều cần kiểm tra |
| --- | --- |
| [] | heapSort hợp lệ, topK(0)=[], kthLargest không có k hợp lệ |
| [5] | sorted=[5], kthLargest(1)=5 |
| [-8,-3,-10] | sorted=[-10,-8,-3], kthLargest(2)=-8 |
| [4,4,4] | topK(2)=[4,4] và k-th không mất phần tử trùng |
| [7,1,9,3,9,2] | sorted=[1,2,3,7,9,9], thứ ba lớn nhất=7 |
| [Integer.MIN_VALUE, Integer.MAX_VALUE] | so sánh vẫn đúng, không tràn comparator |
| Dãy tăng sẵn / giảm sẵn | Heapsort đúng, vẫn O(n log n) xấu nhất |
| k=n | kthLargest trả min, top-k chứa toàn bộ n giá trị đã sắp giảm |
| k=0, k<0, k>n | Hành vi phù hợp hợp đồng từng API |

**Lỗi thường gặp:** nhầm min-heap với max-heap, lấy nhầm con khi sift-down, tiếp tục heapify cả hậu tố đã sắp, khởi tạo heap bằng n lần chèn nhưng công bố O(n) cho build, quên các giá trị trùng, coi peek là phần tử lớn thứ k dù heap chưa có k phần tử, dùng iterator của PriorityQueue như kết quả đã sắp, và đếm chi phí top-k mà quên bước sắp xếp k phần tử đầu ra.

## 12. Bài tập áp dụng

1. Tự dựng max-heap từ [4,1,7,3,8,5] theo thứ tự i=floor(n/2)-1,...,0, rồi mô phỏng **hai** lượt trích cực đại. Tại mỗi bước ghi rõ vùng heap và vùng hậu tố đã sắp.
2. Viết heapsort theo thứ tự **giảm dần** bằng min-heap. Giải thích việc hoán đổi cực tiểu về cuối tạo ra kết quả giảm dần ra sao.
3. Cho [6,1,5,6,2,7,3], tìm phần tử lớn thứ 4 và top-4 lớn nhất bằng min-heap kích thước 4; ghi rõ trạng thái heap sau mỗi phần tử.
4. Với top-k **nhỏ nhất**, sửa chiến lược thành max-heap kích thước k. Chứng minh việc bỏ giá trị lớn nhất trong nhóm đang chọn là hợp lý.
5. Thực hiện truy vấn k-th largest với **k-th distinct**: giải thích lý do [9,9,7] có phần tử lớn thứ hai bằng 9 nhưng phần tử lớn thứ hai phân biệt là 7.
6. Hãy so sánh chi phí của (a) heapsort toàn bộ, (b) min-heap kích thước k, (c) build max-heap rồi trích k lần, với n=1.000.000 và k=20; nêu cả khả năng sửa dữ liệu gốc.
7. Thiết kế top-k bản ghi theo điểm, hòa điểm thì ưu tiên id nhỏ hơn; công bố comparator và kiểm tra rằng thứ tự kết quả không phụ thuộc iteration của heap.

**Ghi nhớ:** để sắp xếp tăng dần bằng heapsort, xây **max-heap** và chuyển cực đại về cuối vùng chưa sắp. Để chọn k giá trị **lớn nhất** mà không sắp toàn bộ, giữ **min-heap kích thước k** để dễ loại ứng viên nhỏ nhất. Cả hai dựa trên một bất biến heap đơn giản nhưng phục vụ những thao tác và đánh đổi khác nhau.
