# Lựa chọn cách chia cân bằng và ảnh hưởng của lệch kích thước

## 1. Phạm vi: “chia để trị” không đồng nghĩa với “chia đôi”

**Chia để trị (divide and conquer)** giải bài toán lớn bằng cách chia thành các bài toán con nhỏ hơn, giải chúng rồi tổng hợp kết quả. Ví dụ: merge sort chia mảng thành hai nửa, quicksort phân hoạch theo pivot, binary search chỉ tiếp tục một nửa, quickselect chỉ tiếp tục phần chứa thứ hạng cần tìm.

Khi phân tích thuật toán, phải phân biệt ba đại lượng:

1. **Tỷ lệ chia**: một bài toán kích thước n được chia thành các phần có kích thước bao nhiêu?
2. **Số nhánh thật sự giải**: xử lý cả hai phần, hay chỉ một phần?
3. **Công việc ngoài đệ quy**: chi phí chọn điểm chia, phân hoạch, trộn hoặc kết hợp kết quả ở mỗi bước là O(1), O(n) hay một hàm khác?

Nếu một trong ba yếu tố đổi, độ phức tạp có thể đổi dù sơ đồ cây trông gần giống nhau. Do đó không có quy tắc “hễ cân bằng thì O(n log n)” hoặc “hễ lệch thì O(n²)” áp dụng cho mọi thuật toán.

**Ba kiểu chia cần phân biệt:**
- **Gần cân bằng:** hai phần có kích thước xấp xỉ n/2.
- **Lệch theo tỷ lệ cố định:** chẳng hạn 1:3, hai phần có kích thước khoảng n/4 và 3n/4. Phần lớn nhất vẫn co theo một tỷ lệ nhỏ hơn 1 **không đổi** ở mỗi bước.
- **Suy biến:** một phần có kích thước O(1), phần còn lại khoảng n−O(1); ví dụ tách 1 phần tử và tiếp tục với n−1 phần tử. Nhánh lớn co rất chậm.

Chia 1:3 và chia 1:(n−1) đều “không đều”, nhưng có thể dẫn tới kết quả hoàn toàn khác nhau.

## 2. Viết truy hồi đúng trước khi đánh giá cân bằng

Giả sử thuật toán tạo **hai bài toán con và giải cả hai**. Với kích thước a và n−a, một mô hình là:

\[
T(n)=T(a)+T(n-a)+M(n),\qquad 1\le a<n,
\]

trong đó \(M(n)\) là chi phí chia/gộp tại nút hiện tại.

Quicksort có một điểm cần lưu ý: pivot sau phân hoạch được đặt đúng vị trí và **không nằm trong hai đoạn đệ quy**. Nếu phía trái có a phần tử thì phía phải có n−1−a phần tử. Truy hồi tương ứng:

\[
T(n)=T(a)+T(n-1-a)+\Theta(n),\quad 0\le a<n.
\]

Việc ghi rõ n−1 giúp đếm chính xác số phần tử và độ sâu; khi phân tích bậc tăng trưởng, chênh lệch một pivot thường không thay đổi kết luận.

Ngược lại, **binary search và quickselect chỉ tiếp tục một nhánh**, nên truy hồi có dạng:

\[
T(n)=T(m)+M(n),
\]

với m là kích thước nhánh thật sự cần giải. Không được dùng truy hồi hai nhánh chỉ vì ở bước đầu bài toán được chia làm hai phần.

**Điều kiện dừng:** n=0 hoặc n=1 thường là cơ sở của đệ quy. Nếu mã không giảm kích thước bài toán hoặc quên điều kiện dừng, cây có thể đệ quy vô hạn bất kể tỷ lệ chia mong muốn.

## 3. Hai nhánh với công việc tuyến tính: so sánh ba tỷ lệ chia

Xét lớp bài toán có phần việc chia/gộp kích thước n tốn \(\Theta(n)\), điển hình là mergesort với phép merge hoặc quicksort với phép partition.

### 3.1. Cân bằng gần 1:1

Với n là lũy thừa của 2 để dễ hình dung:

\[
T(n)=2T(n/2)+cn,\qquad T(1)=\Theta(1).
\]

Tại mỗi mức đệ quy, tổng kích thước các đoạn đang xử lý không vượt quá n. Mức đầu có tổng chi phí cn; mức tiếp theo có hai đoạn n/2, tổng vẫn cn; mức kế có bốn đoạn n/4, tổng vẫn cn.

Số mức chia tới kích thước 1 xấp xỉ \(\log_2 n\). Vì vậy:

\[
\boxed{T(n)=\Theta(n\log n)}.
\]

Độ sâu nhánh lớn nhất \(\Theta(\log n)\). Làm tròn ở các n lẻ không thay đổi kết luận. Lưu ý rằng kết quả này gắn với **việc giải cả hai nhánh** và **chi phí tuyến tính ở mỗi nút**, không phải chỉ với hành động chia đôi.

### 3.2. Lệch 1:3 nhưng theo tỷ lệ cố định

Giả sử \(\alpha\) là một hằng số nằm giữa 0 và 1/2, độc lập với n. Hai phần có kích thước gần \(\alpha n\) và \((1-\alpha)n\). Khi \(\alpha=1/4\), tỷ lệ là 1:3:

\[
T(n)=T(\alpha n)+T((1-\alpha)n)+cn.
\]

Nhánh lớn nhất ở mỗi mức chỉ còn khoảng \((1-\alpha)n\). Sau h mức, nó có kích thước khoảng \(n(1-\alpha)^h\). Vì \(1-\alpha<1\) là hằng số, chiều cao vẫn O(log n).

Mỗi mức tiêu tốn không quá O(n) công việc. Đồng thời, với tỷ lệ hai phía bị chặn xa khỏi 0 và 1 và mỗi nút có chi phí \(\Theta(\text{kích thước nút})\), có \(\Omega(\log n)\) mức hoạt động đủ lớn để tạo tổng công việc \(\Omega(n\log n)\). Kết luận:

\[
\boxed{T(n)=\Theta(n\log n)}.
\]

**Điểm quan trọng:** Lệch 1:3 **không** tự động làm thuật toán thành O(n²). Tuy cùng bậc với chia đôi, nhánh lớn thường sâu hơn, có thể gây thêm chi phí hằng số, nhiều mức trên đường găng và mất cân bằng tải giữa các worker.

Câu “theo tỷ lệ cố định” là điều kiện thiết yếu. Nếu tỷ lệ phần nhỏ dần về 0 khi n tăng, kết luận \(\Theta(n\log n)\) không còn tự động đúng.

### 3.3. Suy biến 1:(n−1)

Nếu mỗi bước chỉ loại một phần tử, phần lớn còn n−1, công việc phân hoạch/gộp tại bước đó tốn cn:

\[
T(n)=T(n-1)+cn+\Theta(1).
\]

Khai triển tạo tổng \(cn+c(n-1)+\cdots+2c\), tức:

\[
\boxed{T(n)=\Theta(n^2)}.
\]

Độ sâu có thể tới \(\Theta(n)\). Trong quicksort, tình huống này xuất hiện khi pivot liên tục là giá trị nhỏ nhất hoặc lớn nhất của đoạn hiện tại, khiến một phía rỗng và phía kia chứa n−1 phần tử.

| Cách chia cho bài toán hai nhánh, làm Θ(n) việc ở mỗi nút | Nhánh lớn nhất | Độ sâu | Tổng thời gian |
|---|---|---|---|
| Gần 1:1 | khoảng n/2 | Θ(log n) | Θ(n log n) |
| Tỷ lệ 1:3 cố định | khoảng 3n/4 | Θ(log n), hằng số cao hơn | Θ(n log n) |
| Gần 1:(n−1) | n−1 | Θ(n) | Θ(n²) |

Bảng này mô tả **mô hình hai nhánh với công việc mỗi nút Θ(n)**. Đừng chuyển kết luận sang truy hồi có một nhánh hay chi phí mỗi nút khác.

## 4. Chỉ giải một nhánh: binary search và quickselect

### 4.1. Binary search

Binary search trên dãy đã sắp so sánh với phần tử giữa rồi chỉ tiếp tục vùng còn có thể chứa khóa. Mỗi bước làm Θ(1) công việc ngoài nhánh đệ quy.

- Chia cân bằng: \(T(n)=T(\lfloor n/2\rfloor)+\Theta(1)=\Theta(\log n)\).
- Nếu mỗi bước chỉ bỏ được một phần tử: \(T(n)=T(n-1)+\Theta(1)=\Theta(n)\).

Đây là lý do vị trí **giữa** phù hợp với binary search: nhánh giữ lại có kích thước tối đa khoảng n/2. Trong Java, với chỉ số hợp lệ không âm, tính midpoint dạng **left + (right − left) / 2** giúp tránh khả năng tràn khi cộng left+right.

### 4.2. Quickselect

Quickselect tìm phần tử có thứ hạng k bằng cách phân hoạch theo pivot rồi chỉ tiếp tục **một** phía chứa hạng cần tìm. Mỗi lượt partition cần Θ(n) thao tác theo kích thước đoạn.

- Chia tốt ở mỗi lượt: \(T(n)=T(n/2)+cn=\Theta(n)\) bởi tổng n+n/2+n/4+...=O(n).
- Suy biến liên tục: \(T(n)=T(n-1)+cn=\Theta(n^2)\).

Quickselect với pivot ngẫu nhiên có thời gian **kỳ vọng** tuyến tính trong mô hình chuẩn, nhưng vẫn có trường hợp xấu nhất Θ(n²). Phải phân biệt “kỳ vọng” với “bảo đảm mọi đầu vào”.

### 4.3. Hai nhánh nhưng mỗi nút chỉ làm O(1)

Giả sử một thủ tục giải cả hai nhánh với công việc ngoài lời gọi đệ quy Θ(1), mỗi lá xử lý hằng số, và mỗi phép chia tạo hai nhánh không rỗng. Cây có Θ(n) lá/nút, nên tổng thời gian Θ(n) cho cả chia cân bằng lẫn lệch. Dù vậy, **độ sâu** vẫn có thể đổi từ Θ(log n) sang Θ(n).

Điều này cho thấy cây lệch chưa đủ kết luận tổng thời gian xấu hơn bậc; cần xem **chi phí từng nút**.

## 5. Quicksort: thứ hạng pivot quyết định độ cân bằng

Quicksort chọn pivot, dùng partition đặt pivot vào vị trí cuối cùng trong thứ tự sắp xếp, rồi giải hai đoạn còn lại.

**Cân bằng được xác định bởi kích thước hai phía *sau partition*, không phải vị trí vật lý dùng để lấy pivot.** Chọn phần tử giữa mảng làm pivot không có nghĩa giá trị của nó nằm gần trung vị; nó vẫn có thể là nhỏ nhất hoặc lớn nhất.

- Pivot có thứ hạng gần giữa: hai phần gần n/2, số lần phân hoạch trên một đường đi khoảng log n.
- Pivot luôn cực trị: một phía n−1, phía kia rỗng, tạo tổng \(\Theta(n^2)\) phép xử lý phân hoạch.
- Nhiều phần tử bằng pivot: nếu partition hai phía dùng điều kiện “≤ pivot”, tất cả phần tử bằng nhau có thể đi cùng một phía, gây suy biến dù dữ liệu không được sắp sẵn.

**Các chiến lược chọn pivot:**

| Chiến lược | Lợi ích | Điều không được suy diễn |
|---|---|---|
| Pivot đầu/cuối | Rất dễ cài đặt | Không tránh đầu vào đã sắp |
| Pivot lấy ở vị trí giữa mảng | Có thể giảm vài mẫu dễ gặp | Không bảo đảm giá trị gần trung vị |
| Median-of-three (trung vị của đầu, giữa, cuối) | Thường cải thiện trên nhiều dữ liệu thực tế | Không bảo đảm cân bằng trong trường hợp xấu nhất |
| Pivot ngẫu nhiên | Giảm phụ thuộc vào thứ tự dữ liệu cố định; quicksort có kỳ vọng O(n log n) | Vẫn có trường hợp xấu nhất O(n²) |
| Phân hoạch ba phía (<, =, >) | Tách riêng nhóm bằng pivot, hữu ích khi nhiều khóa trùng | Không tự bảo đảm mọi phép chia đều cân bằng |
| Introsort | Đổi chiến lược khi độ sâu vượt ngưỡng, nhằm bảo đảm độ phức tạp xấu nhất phù hợp | Phức tạp hơn quicksort minh họa |

**Mergesort chuẩn** khác quicksort ở chỗ chia theo chỉ số gần n/2 **không phụ thuộc giá trị phần tử**. Bất kể mảng ban đầu tăng, giảm hay ngẫu nhiên, hai bài toán con vẫn gần bằng nhau; phép merge tuyến tính dẫn tới Θ(n log n). Bản mergesort dùng bộ đệm trộn thông thường cần O(n) bộ nhớ phụ, ngoài O(log n) stack.

## 6. Ví dụ Java 17+: cùng giá trị, hai dạng cây đệ quy

Ta dùng **quicksort Lomuto với pivot cuối đoạn** để quan sát số lần so sánh. Một bộ dữ liệu được sắp thứ tự có chủ ý để pivot cuối là **trung vị của đoạn ở mọi mức**; một bộ khác tăng sẵn, khiến pivot cuối liên tục là cực đại.

- **Balanced input:** [1,3,2,6,7,5,4]. Pivot đầu là 4; sau partition, hai phía đều dài 3. Phía trái có pivot 2, phía phải có pivot 6, nên đều chia thành hai đoạn dài 1.
- **Skewed input:** [1,2,3,4,5,6,7]. Pivot là 7 rồi 6 rồi 5..., mỗi lần chỉ loại một phần tử.
- **All equal input:** [5,5,5,5]. Partition Lomuto dưới đây dùng “≤ pivot”, nên phần tử bằng pivot tập trung về phía trái; thuật toán vẫn đúng nhưng chia suy biến.

Bộ đếm chỉ ghi **số lần kiểm tra a[j] ≤ pivot**, số phân hoạch của đoạn có ít nhất hai phần tử, và **mức phân hoạch sâu nhất** bắt đầu từ 1. Không đếm lời gọi đệ quy vào đoạn rỗng hoặc một phần tử trong chỉ số deepestPartitionLevel.

Lưu tệp **BalancedSplitQuickSortDemo.java**:

~~~java
import java.util.Arrays;

public final class BalancedSplitQuickSortDemo {
    private BalancedSplitQuickSortDemo() {
    }

    static final class Stats {
        long comparisons;
        int partitions;
        int deepestPartitionLevel;
    }

    private static void swap(int[] a, int i, int j) {
        int old = a[i];
        a[i] = a[j];
        a[j] = old;
    }

    // Lomuto partition: pivot là phần tử cuối đoạn.
    private static int partition(int[] a, int left, int right,
                                 Stats stats) {
        int pivot = a[right];
        int nextSmall = left;

        for (int j = left; j < right; j++) {
            stats.comparisons++;
            if (a[j] <= pivot) {
                swap(a, nextSmall, j);
                nextSmall++;
            }
        }

        swap(a, nextSmall, right);
        return nextSmall;
    }

    private static void quickSort(int[] a, int left, int right,
                                  int level, Stats stats) {
        if (left >= right) {
            return;
        }

        stats.partitions++;
        stats.deepestPartitionLevel =
                Math.max(stats.deepestPartitionLevel, level);

        int p = partition(a, left, right, stats);
        quickSort(a, left, p - 1, level + 1, stats);
        quickSort(a, p + 1, right, level + 1, stats);
    }

    private static void run(String label, int[] values) {
        Stats stats = new Stats();
        quickSort(values, 0, values.length - 1, 1, stats);
        System.out.println(label + ": " + Arrays.toString(values)
                + " | comparisons=" + stats.comparisons
                + ", partitions=" + stats.partitions
                + ", deepestPartitionLevel="
                + stats.deepestPartitionLevel);
    }

    public static void main(String[] args) {
        run("Balanced", new int[] {1, 3, 2, 6, 7, 5, 4});
        run("Skewed", new int[] {1, 2, 3, 4, 5, 6, 7});
        run("All equal", new int[] {5, 5, 5, 5});
        run("Empty", new int[] {});
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac BalancedSplitQuickSortDemo.java
java BalancedSplitQuickSortDemo
~~~

Stdout:

~~~text
Balanced: [1, 2, 3, 4, 5, 6, 7] | comparisons=10, partitions=3, deepestPartitionLevel=2
Skewed: [1, 2, 3, 4, 5, 6, 7] | comparisons=21, partitions=6, deepestPartitionLevel=6
All equal: [5, 5, 5, 5] | comparisons=6, partitions=3, deepestPartitionLevel=3
Empty: [] | comparisons=0, partitions=0, deepestPartitionLevel=0
~~~

**Giải thích từng mẫu:**
- Balanced: đoạn dài 7 tốn 6 lần so sánh; hai đoạn dài 3 tiếp theo tốn 2 lần mỗi đoạn. Tổng là **6+2+2=10**. Có ba lần partition và hai mức có partition.
- Skewed: các đoạn cần partition có độ dài 7, 6, 5, 4, 3, 2, tương ứng 6+5+4+3+2+1=**21** lần so sánh, sáu lần partition và sáu mức có partition.
- All equal: độ dài đoạn cần partition lần lượt 4,3,2, nên có 3+2+1=**6** lần so sánh.
- Empty: điều kiện dừng tác động ngay; không partition và không so sánh.

Cả hai mẫu Balanced và Skewed đều trả mảng [1,2,3,4,5,6,7]; sự khác biệt nằm ở **cây đệ quy và lượng công việc**. Đây là mô phỏng nhỏ có kiểm soát, không phải bằng chứng mọi dữ liệu ngẫu nhiên đều cân bằng.

**Giới hạn chương trình:** phiên bản này cố tình dùng pivot cuối và đệ quy hai nhánh để làm rõ sự suy biến. Với đầu vào lớn bất lợi, stack có thể sâu O(n) và gây StackOverflowError; mã được dùng như ví dụ học thuật, không phải lựa chọn mặc định cho dữ liệu kích thước rất lớn.

## 7. Cân bằng còn ảnh hưởng đến bộ nhớ stack và đường găng

### 7.1. Độ sâu stack khác với tổng thời gian

Một lời gọi đệ quy cần khung ngăn xếp chứa tham số, biến cục bộ và địa chỉ quay lại. Trong quicksort đệ quy hai phía:

- Cây gần cân bằng có độ sâu O(log n).
- Cây suy biến có độ sâu O(n).

Thời gian thực hiện và stack phải được phân tích độc lập. Một cây có tổng công việc Θ(n) vẫn có thể sâu n, trong khi mergesort chia đôi có stack O(log n) nhưng cần thêm O(n) bộ đệm để trộn.

### 7.2. Đệ quy trên nhánh nhỏ, lặp trên nhánh lớn

Trong quicksort, có thể chỉ **gọi đệ quy với nhánh nhỏ hơn**, đồng thời xử lý **nhánh lớn hơn bằng vòng lặp**. Mỗi mức *gọi đệ quy thật sự* khi đó đi vào đoạn có tối đa khoảng một nửa phần tử, giúp bảo đảm **O(log n)** khung stack, kể cả khi một pivot tạo nhánh lớn n−1.

Tuy nhiên, nếu pivot vẫn liên tục là cực trị, tổng công việc phân hoạch vẫn là Θ(n²). Đổi cấu trúc đệ quy **giải quyết vấn đề stack chứ không tự sửa thời gian**.

### 7.3. Công việc song song

Nếu hai nhánh độc lập có thể được xử lý song song, chia gần bằng nhau thường giúp phân tải tốt hơn. Một nhánh rất nhỏ và một nhánh rất lớn có thể khiến một worker rảnh trong khi worker khác còn xử lý lâu.

Nhưng cân bằng theo **số phần tử** chưa chắc bằng cân bằng theo **chi phí thực tế**: một nhánh có thể chứa phần tử khó xử lý hơn, nhiều cạnh đồ thị hơn hoặc nhiều phép kiểm tra hơn. Trong bài toán song song cần xét chi phí tạo tác vụ, đồng bộ, merge, giới hạn tài nguyên và đường găng — không chỉ so sánh kích thước phần tử.

## 8. Cách lựa chọn phép chia khi thiết kế

Trước khi cài đặt thuật toán chia để trị:

1. **Xác định thước đo kích thước:** n là số phần tử, số cạnh, diện tích hay một đại lượng chi phối chi phí?
2. **Viết truy hồi theo số nhánh thực sự xử lý:** một nhánh hay hai nhánh, mỗi nhánh lớn bao nhiêu?
3. **Tách phần việc ngoài đệ quy:** O(1), Θ(n) hay phải tính cả bước merge/partition phức tạp hơn?
4. **Hỏi tỷ lệ chia có được bảo đảm không:** pivot ngẫu nhiên chỉ cho bảo đảm kỳ vọng, còn chia theo chỉ số như mergesort có tỷ lệ gần 1:1 theo thiết kế.
5. **Dự phòng dữ liệu có trùng khóa:** phân hoạch ba phía có thể phù hợp hơn phân hoạch hai phía khi nhiều giá trị bằng nhau.
6. **Kiểm tra độ sâu stack và bộ nhớ bổ sung:** tránh suy từ “sắp tại chỗ” rằng stack luôn là O(1).
7. **Phân biệt tính đúng với tối ưu:** một phép chia lệch có thể vẫn sắp đúng nhưng mất nhiều công việc hơn.
8. **Xem xét song song hóa:** hai phần cân bằng giúp phân tải, nhưng không bỏ qua overhead.

**Khi benchmark**, nên đo trên mảng tăng, giảm, ngẫu nhiên, đảo thứ tự, gần sắp, tất cả bằng nhau và nhiều phần tử trùng. Ghi số phần tử hai phía sau partition, số lượt so sánh, độ sâu tối đa và thời gian chạy. Không đánh giá chiến lược pivot chỉ từ một dãy ngẫu nhiên thuận lợi.

### Ví dụ các nguyên tắc đối chiếu

| Bài toán | Số nhánh được giải | Công việc tại nút | Tác động của chia |
|---|---|---|---|
| Mergesort | Hai | Θ(n) để merge | Chia gần đôi theo chỉ số tạo Θ(n log n) |
| Quicksort | Hai sau khi bỏ pivot | Θ(n) để partition | Cân bằng Θ(n log n), suy biến Θ(n²) |
| Binary search | Một | Θ(1) | Co nửa cho Θ(log n); co một đơn vị cho Θ(n) |
| Quickselect | Một | Θ(n) | Co nửa cho Θ(n); suy biến cho Θ(n²) |
| Hai nhánh với việc ngoài nút Θ(1) và lá Θ(1) | Hai | Θ(1) | Tổng có thể Θ(n) dù độ sâu khác nhau |

## 9. Lỗi thường gặp

1. **Đánh đồng mọi kiểu lệch với n−1:** lệch 1:3 cố định vẫn cho logarithmic depth, khác hoàn toàn 1:(n−1).
2. **Kết luận chỉ từ chiều cao cây:** phải cộng chi phí của tất cả nút ở mỗi mức.
3. **Bỏ qua chỉ một nhánh được giải:** binary search và quickselect không có cùng truy hồi với mergesort.
4. **Quên pivot đã được loại khi viết truy hồi quicksort:** hai đoạn còn lại cộng n−1 phần tử.
5. **Dùng vị trí giữa làm bằng chứng pivot là trung vị giá trị:** vị trí và thứ hạng không đồng nghĩa.
6. **Tin rằng random pivot không bao giờ suy biến:** nó có xác suất gây các phép chia xấu; bảo đảm là kỳ vọng, không phải từng lượt.
7. **Cho rằng median-of-three bảo đảm O(n log n) worst-case:** đây chỉ là heuristic.
8. **Không xét tất cả phần tử bằng nhau:** Lomuto dùng ≤ có thể liên tục tạo nhánh n−1.
9. **Bỏ qua dữ liệu rỗng, một phần tử và việc làm tròn:** dễ gây vòng đệ quy không tiến triển.
10. **Đồng nhất stack với bộ nhớ phụ toàn thuật toán:** mergesort có bộ đệm O(n), quicksort có stack phụ thuộc độ lệch.
11. **Cho rằng tối ưu stack đồng thời tối ưu thời gian:** đệ quy nhánh nhỏ chỉ giảm stack; phép partition xấu vẫn có thể lặp O(n) tầng.
12. **So sánh thuật toán chỉ bằng Big O:** cùng Θ(n log n) vẫn có khác biệt hằng số, cache, cấp phát và mức độ song song.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Với hai nhánh, mỗi nút làm Θ(n) việc, chia đều 1:1 và chia cố định 1:3 có khác bậc thời gian không?

**Đáp án:** Không. Cả hai đều Θ(n log n). Chia 1:3 có nhánh dài hơn và có thể có hằng số chi phí lớn hơn, nhưng tỷ lệ co của nhánh lớn nhất vẫn nhỏ hơn 1 không đổi.

**Câu 2.** Vì sao quicksort với pivot cực trị liên tục có thời gian Θ(n²)?

**Đáp án:** Sau mỗi lượt phân hoạch Θ(n), chỉ loại được một pivot; phần cần làm tiếp dài n−1. Tổng n+(n−1)+...+2 là Θ(n²).

**Câu 3.** Hai công thức \(T(n)=T(n/2)+\Theta(1)\) và \(T(n)=T(n/2)+\Theta(n)\) cho kết quả gì?

**Đáp án:** Công thức thứ nhất Θ(log n), như binary search. Công thức thứ hai Θ(n), như quickselect khi nhánh được chọn luôn nhỏ đi gần một nửa.

**Câu 4.** Tại sao hai mảng chứa cùng các số 1..7 trong Java demo có 10 và 21 phép so sánh?

**Đáp án:** Mảng [1,3,2,6,7,5,4] làm pivot cuối có thứ hạng giữa tại ba đoạn cần partition, tổng 6+2+2=10. Mảng [1,2,3,4,5,6,7] luôn lấy cực đại, tổng 6+5+4+3+2+1=21.

**Câu 5.** Nếu chỉ đệ quy nhánh nhỏ và lặp nhánh lớn, quicksort có bảo đảm O(n log n) thời gian không?

**Đáp án:** Không. Cải tiến bảo đảm O(log n) khung stack, nhưng với pivot suy biến, tổng công việc vẫn có thể Θ(n²).

**Câu 6.** Khi nào chia gần 1:1 theo số phần tử chưa đủ để cân bằng tải khi chạy song song?

**Đáp án:** Khi chi phí trên mỗi phần tử không đều, hoặc có khác biệt về chi phí I/O, phân hoạch, đồng bộ và gộp. Cần ước lượng **công việc**, không chỉ số phần tử.

**Ghi nhớ:** Muốn đánh giá tác động của phép chia, hãy viết đúng **tỷ lệ kích thước**, **số nhánh thật sự giải** và **chi phí mỗi bước**. Chia cân bằng thường giảm chiều sâu và cải thiện hiệu năng, nhưng lệch theo tỷ lệ cố định chưa phải suy biến; việc nhánh lớn chỉ giảm một phần tử qua mỗi lượt mới là trường hợp điển hình gây chi phí bậc hai khi mỗi lượt làm Θ(n) việc.
