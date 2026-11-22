# Median of medians và lựa chọn pivot có bảo đảm

Khi bài toán yêu cầu **giá trị nhỏ thứ k** của một dãy, ta không nhất thiết phải sắp xếp toàn bộ dãy. Thuật toán chọn theo thứ hạng (*selection*) chỉ cần xác định một **order statistic** cụ thể. Quickselect dùng phép phân hoạch theo **pivot** để loại bỏ những phần tử không thể chứa đáp án; thường nhanh, nhưng có thể rơi vào trường hợp xấu nhất **Θ(n²)** khi pivot liên tục quá lệch.

**Median of medians** (BFPRT, theo tên Blum–Floyd–Pratt–Rivest–Tarjan) là một kỹ thuật **chọn pivot mang bảo đảm**: chia dữ liệu thành nhóm 5, lấy trung vị của từng nhóm rồi dùng trung vị của các trung vị làm pivot. Pivot này không nhất thiết là trung vị chính xác của toàn mảng, nhưng bảo đảm có đủ nhiều phần tử ở hai phía để quá trình lựa chọn chỉ mất **O(n) thời gian ngay cả ở trường hợp xấu nhất**.

Bài này giải thích đặc tả bài toán, cách phân nhóm, chứng minh mức loại bỏ khoảng 30%, công thức truy hồi, cập nhật hai biên phân hoạch, chương trình Java 17 có kiểm thử, các trường hợp biên và khi nào nên áp dụng.

## 1. Đặc tả: tìm giá trị tại thứ hạng k

**Đầu vào:** mảng `a` có `n ≥ 1` số nguyên, có thể âm, dương hoặc trùng nhau; một chỉ số `k` với `0 ≤ k < n`. **Đầu ra:** giá trị ở chỉ số `k` nếu mảng được sắp xếp không giảm. Đây là **rank 0-based**.

Ví dụ:

~~~text
Dữ liệu:        [7, 2, 9, 2, 5]
Sắp để đối chiếu: [2, 2, 5, 7, 9]
k=0 -> 2; k=1 -> 2; k=2 -> 5; k=4 -> 9
~~~

Đầu ra là **giá trị**, không phải chỉ số của một bản ghi trong mảng gốc. Khi các giá trị bằng nhau, chúng được tính theo **số lần xuất hiện**. Nếu đề hỏi “phần tử nhỏ thứ t” theo thứ tự bắt đầu từ **1**, truyền `k=t−1` vào API bắt đầu từ 0.

Gọi kết quả là `v`, đặc tả có thể diễn đạt không cần sắp xếp:

~~~text
count(a[i] < v) <= k < count(a[i] <= v)
~~~

Điều kiện này quan trọng khi xuất hiện nhiều phần tử bằng `v`. Không thể đòi đúng `k` phần tử **nhỏ hơn nghiêm ngặt** `v`: ví dụ [2,2,2], k=2 vẫn có kết quả 2, mặc dù không có phần tử nào < 2.

Với n=0 hoặc k ngoài [0,n), không tồn tại giá trị thứ k theo hợp đồng này. Hàm Java ví dụ sẽ ném `IllegalArgumentException` để báo tiền điều kiện sai.

**Phân biệt selection và sorting:** sắp xếp toàn bộ tạo ra thứ tự của **mọi** phần tử. Selection chỉ cần một thứ hạng. Nếu sau đó phải trả lời hàng nghìn truy vấn thứ hạng độc lập trên dữ liệu cố định, sắp xếp một lần có thể thuận lợi hơn việc chọn lại từng lần.

## 2. Tại sao pivot làm thay đổi độ phức tạp?

Giả sử đang tìm giá trị thứ `k` trong đoạn. Chọn pivot `p`, rồi chia thành ba miền:

~~~text
L: mọi phần tử < p
E: mọi phần tử = p
G: mọi phần tử > p
~~~

Sau phân hoạch:
- Nếu k thuộc miền L, bỏ toàn bộ E và G rồi tiếp tục trong L.
- Nếu k thuộc miền E, **trả p** ngay.
- Nếu k thuộc miền G, bỏ L và E rồi tiếp tục trong G, với thứ hạng tương ứng nếu dùng cách đánh chỉ số cục bộ.

Một bước phân hoạch làm O(m) công việc trên m phần tử. Nếu pivot gần trung vị, nhánh lớn nhất chỉ khoảng m/2; tổng công việc gần `m+m/2+m/4+...`, tức O(m).

Ngược lại, nếu luôn chọn phần tử **nhỏ nhất** làm pivot để tìm phần tử lớn nhất, sau mỗi lần chỉ bỏ được một phần tử:

~~~text
Kích thước: n, n-1, n-2, ..., 2, 1
Tổng công việc ≈ n + (n-1) + ... + 1 = Θ(n²)
~~~

Tình huống đối xứng có thể xảy ra với quickselect chọn pivot cuối trên mảng tăng dần khi tìm phần tử nhỏ nhất. Một pivot cố định theo đầu/cuối dữ liệu dễ bị đầu vào đối kháng làm mất cân bằng.

**Quickselect chọn pivot ngẫu nhiên** có thời gian **O(n) kỳ vọng** theo mô hình chuẩn, nhưng vẫn có những chuỗi ngẫu nhiên hiếm gặp dẫn tới nhánh rất lệch và trường hợp xấu nhất O(n²). Median of medians không dựa vào may mắn của pivot để đưa ra cận thời gian.

## 3. Median of medians: quy trình nhóm 5

Xét một đoạn hiện có `m` phần tử. Quy trình:

1. Chia liên tiếp thành các nhóm **tối đa 5 phần tử**. Nhóm cuối có thể chứa 1–4 phần tử.
2. Sắp từng nhóm nhỏ; lấy **giá trị giữa** làm trung vị nhóm. Nhóm đủ 5 có trung vị là phần tử thứ 3 sau sắp. Với nhóm cuối kích thước chẵn, có thể nhất quán chọn trung vị thấp hoặc cao.
3. Gom các trung vị nhóm thành một dãy gồm `g=ceil(m/5)` phần tử.
4. Dùng chính phương pháp selection quyết định để tìm **trung vị của dãy trung vị**; gọi kết quả là `p`.
5. Phân hoạch toàn bộ đoạn gốc theo `p`, thành ba miền **< p, = p, > p**.
6. Chỉ đệ quy trên miền có thể chứa thứ hạng mong muốn; trả ngay nếu thứ hạng nằm trong miền bằng.

Đoạn có tối đa 5 phần tử là **base case**: sắp đoạn nhỏ rồi lấy phần tử tại thứ hạng thích hợp. Không cần tiếp tục phân nhóm khi chỉ còn ít phần tử.

**Chi phí lấy các trung vị nhóm:** mỗi nhóm tối đa 5 phần tử, nên sắp nhóm bằng insertion sort có chi phí bị chặn bởi một hằng số; có khoảng m/5 nhóm. Tổng chi phí sắp nhóm, ghi trung vị và phân hoạch vẫn là **O(m)**. Chỉ riêng việc chọn **trung vị của các trung vị** mới tạo ra bài toán đệ quy trên khoảng m/5 phần tử.

### Vì sao ưu tiên nhóm 5?

Trong nhóm 5 sau sắp:

~~~text
v1 <= v2 <= v3 <= v4 <= v5
             ^
          trung vị
~~~

Ít nhất **3 giá trị ≤ v3** và ít nhất **3 giá trị ≥ v3**. Khi kết hợp các nhóm có trung vị nằm một phía của pivot, ta suy ra có đủ nhiều phần tử toàn cục nằm phía ấy.

Nhóm 5 cân bằng giữa chi phí tìm trung vị nhóm và chất lượng pivot. Không được tự suy rằng mọi kích thước nhóm đều có cùng chứng minh; các kích thước khác cần phân tích riêng. Đặc biệt, việc thay 5 bằng 3 trong cùng phép truy hồi đơn giản không còn cho ngay tổng hệ số bài toán con <1 như dưới đây.

## 4. Ví dụ chọn pivot trên 15 phần tử

Cho mảng:

~~~text
[12, 3, 5, 7, 4, 19, 26, 6, 1, 8, 11, 2, 17, 9, 10]
~~~

Chia thành ba nhóm, sắp riêng:

| Nhóm | Trước sắp | Sau sắp | Trung vị |
| --- | --- | --- | ---: |
| 1 | [12,3,5,7,4] | [3,4,5,7,12] | 5 |
| 2 | [19,26,6,1,8] | [1,6,8,19,26] | 8 |
| 3 | [11,2,17,9,10] | [2,9,10,11,17] | 10 |

Dãy trung vị nhóm là **[5,8,10]**; trung vị của dãy này là **8**, nên chọn **p=8**.

Phân hoạch trên toàn mảng theo p cho ba tập giá trị:

~~~text
Nhỏ hơn 8: [3, 5, 7, 4, 6, 1, 2]       (7 phần tử)
Bằng 8:    [8]                          (1 phần tử)
Lớn hơn 8: [12, 19, 26, 11, 17, 9, 10] (7 phần tử)
~~~

Thứ tự bên trong từng miền chỉ mang tính minh họa: một thuật toán phân hoạch tại chỗ có thể tạo thứ tự khác, miễn **mọi phần tử vào đúng miền**.

Nếu `k=7` (phần tử thứ 8 theo cách đếm từ 1), chỉ số này nằm trong miền bằng pivot, nên trả **8**. Nếu `k=0`, ta chỉ cần tiếp tục phía các phần tử nhỏ hơn. Nếu `k=14`, đáp án nằm phía lớn hơn.

Trong ví dụ này 8 cũng tình cờ là **trung vị thật của toàn bộ 15 phần tử**. Nhưng thuật toán **không bảo đảm** median of medians trùng trung vị toàn cục ở mọi đầu vào; nó chỉ bảo đảm pivot **không quá lệch**, đủ để đạt độ phức tạp tuyến tính.

## 5. Chứng minh loại được khoảng 30% phần tử

Gọi `n` là số phần tử trong đoạn đang xét, `p` là median of medians và `g≈n/5` là số trung vị nhóm.

**Bước 1.** Vì p là trung vị của dãy g trung vị nhóm, ít nhất **khoảng một nửa** số trung vị nhóm không nhỏ hơn p; và ít nhất khoảng một nửa không lớn hơn p.

**Bước 2.** Mỗi nhóm **đầy đủ 5 phần tử** có trung vị ≥ p chứa ít nhất 3 phần tử ≥ p: chính trung vị và hai phần tử không nhỏ hơn trung vị. Tương tự, mỗi nhóm đầy đủ có trung vị ≤ p chứa ít nhất 3 phần tử ≤ p.

**Bước 3.** Ta có thể bỏ qua một nhóm cuối chưa đủ 5 và một số điều chỉnh hằng số ở ranh giới nhóm mà không đổi tỷ lệ tiệm cận. Kết quả:

\[
\#\{a_i\le p\}\ge \frac{3n}{10}-O(1),\qquad
\#\{a_i\ge p\}\ge \frac{3n}{10}-O(1).
\]

Một cận quen dùng là **ít nhất khoảng 3n/10 − 6** phần tử ở mỗi phía theo bất đẳng thức **không chặt** (≤ hoặc ≥), tùy cách làm tròn ở nhóm cuối.

**Bước 4.** Nếu thứ hạng cần tìm nằm trong miền **< p**, ta loại được tất cả phần tử **≥ p**, ít nhất khoảng 30% n. Nếu thứ hạng thuộc miền **> p**, ta loại được mọi phần tử **≤ p**, cũng ít nhất khoảng 30% n. Nếu nằm trong miền **= p**, ta trả p ngay. Vậy nhánh còn xử lý nhiều nhất **7n/10 + O(1)** phần tử.

### Trường hợp các phần tử trùng nhau

Không được diễn giải nhầm thành “ít nhất 30% nhỏ hơn **nghiêm ngặt** pivot và 30% lớn hơn **nghiêm ngặt** pivot”. Nếu tất cả phần tử bằng nhau thì không có phần tử nào nhỏ hơn hay lớn hơn nghiêm ngặt. Bằng chứng dùng **≤ và ≥**, và phân hoạch ba phía **loại nguyên miền bằng** hoặc trả kết quả. Đây là lý do phiên bản ba phía vừa đúng vừa tránh lặp vô ích trên dữ liệu nhiều khóa trùng.

### Truy hồi thời gian

Trong một lời gọi trên n phần tử:
- Chọn pivot cần lời gọi selection trên khoảng **n/5** trung vị nhóm.
- Sau phân hoạch, xử lý **tối đa 7n/10+O(1)** phần tử ở **một** phía chứa k.
- Việc chia nhóm, sắp các nhóm kích thước tối đa 5 và phân hoạch tốn **O(n)**.

Vì vậy:

\[
T(n)\le T(\lceil n/5\rceil)+T(7n/10+O(1))+cn.
\]

Nếu bỏ sai số hằng số để thấy cấu trúc, tổng tỷ lệ hai bài toán con là **1/5 + 7/10 = 9/10 < 1**. Có thể chứng minh bằng thế hoặc cộng công việc theo các mức rằng `T(n)=O(n)` ở trường hợp xấu nhất. Bài chọn thứ hạng tổng quát cũng có cận dưới Ω(n) trong mô hình so sánh thích hợp, nên thuật toán đạt **Θ(n) worst-case**.

Khác với quicksort, quickselect **chỉ tiếp tục một nhánh sau phân hoạch**, không phải cả hai nhánh. Lời gọi trên n/5 trung vị là để tìm pivot, không phải để sắp một nửa còn lại.

Bảo đảm O(n) là về tăng trưởng tiệm cận. Nó **không có nghĩa** BFPRT luôn nhanh hơn quickselect ngẫu nhiên trong thực nghiệm: việc phân nhóm và chọn trung vị đệ quy có thể làm tăng hằng số thời gian.

## 6. Phân hoạch ba phía và cập nhật các biên

Dùng khoảng **nửa mở [left,right)** chứa các ứng viên còn xét và hai biên `lt`, `gt`:

~~~text
[left, lt)      : các phần tử < pivot
[lt, scan)      : các phần tử = pivot
[scan, gt)      : chưa phân loại
[gt, right)     : các phần tử > pivot
~~~

Bắt đầu: `lt=left`, `scan=left`, `gt=right`. Lặp khi `scan<gt`:

- Nếu `a[scan]<pivot`: đổi với `a[lt]`, tăng cả `lt` và `scan`.
- Nếu `a[scan]==pivot`: tăng `scan`.
- Nếu `a[scan]>pivot`: giảm `gt`, đổi với `a[gt]`, **không tăng scan**, vì giá trị vừa chuyển từ bên phải vào vị trí scan chưa được kiểm tra.

Kết thúc: đoạn [scan,gt) rỗng; ta có đúng ba miền [left,lt), [lt,gt), [gt,right).

Nếu hàm giữ chỉ số `rank` **tuyệt đối trong mảng hiện tại** qua tất cả lời gọi, thì:
- `rank<lt`: tìm trong **[left,lt)**.
- `rank>=gt`: tìm trong **[gt,right)**.
- `lt<=rank<gt`: trả giá trị pivot.

Không cần quy đổi rank mỗi lần vì các phép hoán đổi chỉ xảy ra bên trong đoạn đang xét và vùng ngoài đã bị loại ở những bước trước.

**Bất biến** giúp tránh lỗi thường gặp: biến `gt` là đầu miền **> pivot**, do đó nhánh đi phải phải dùng `rank>=gt`; còn `right` là biên nửa mở, không được đọc `a[right]`. Việc tăng `scan` khi vừa đổi với phần tử ở gt có thể bỏ qua một phần tử chưa phân loại và làm kết quả sai.

## 7. Java 17: median of medians tại chỗ và kiểm thử

Chương trình độc lập sau gồm lõi **`selectInPlace`** (thay đổi mảng) và API **`kthSmallest`** (clone mảng để giữ dữ liệu đầu vào). Nó sắp từng nhóm ≤5 bằng insertion sort, gom trung vị về đầu đoạn, tìm median of medians, phân hoạch ba phía rồi chỉ tiếp tục đoạn có thể chứa rank.

~~~java
import java.util.Arrays;

public class MedianOfMediansDemo {
    // Sắp đoạn nửa mở [from, to), chỉ gọi với tối đa 5 phần tử.
    static void insertionSortSmall(int[] a, int from, int to) {
        for (int i = from + 1; i < to; i++) {
            int key = a[i];
            int j = i - 1;
            while (j >= from && a[j] > key) {
                a[j + 1] = a[j];
                j--;
            }
            a[j + 1] = key;
        }
    }

    static void swap(int[] a, int i, int j) {
        if (i != j) {
            int temp = a[i];
            a[i] = a[j];
            a[j] = temp;
        }
    }

    // left <= rank < right, đoạn [left, right) nửa mở.
    static int selectInPlace(int[] a, int left, int right, int rank) {
        int length = right - left;

        if (length <= 5) {
            insertionSortSmall(a, left, right);
            return a[rank];
        }

        int groups = 0;

        // Gom một trung vị mỗi nhóm 5 vào đầu đoạn.
        for (int start = left; start < right; ) {
            int end = start + Math.min(5, right - start);
            insertionSortSmall(a, start, end);
            int middle = start + (end - start - 1) / 2;
            swap(a, left + groups, middle);
            groups++;
            start = end;
        }

        // Nhóm chẵn lấy trung vị trên của dãy các trung vị.
        int pivot = selectInPlace(
            a, left, left + groups, left + groups / 2
        );

        int lt = left;
        int scan = left;
        int gt = right;

        // DNF: nhỏ hơn | bằng | chưa xét | lớn hơn.
        while (scan < gt) {
            if (a[scan] < pivot) {
                swap(a, lt, scan);
                lt++;
                scan++;
            } else if (a[scan] > pivot) {
                gt--;
                swap(a, scan, gt);
                // Không tăng scan: phần tử mới chưa được kiểm tra.
            } else {
                scan++;
            }
        }

        if (rank < lt) {
            return selectInPlace(a, left, lt, rank);
        }
        if (rank >= gt) {
            return selectInPlace(a, gt, right, rank);
        }
        return a[rank];
    }

    // Trả giá trị nhỏ thứ rank, giữ nguyên mảng của người gọi.
    public static int kthSmallest(int[] values, int rank) {
        if (values == null || rank < 0 || rank >= values.length) {
            throw new IllegalArgumentException("Invalid rank or array");
        }
        int[] copy = values.clone();
        return selectInPlace(copy, 0, copy.length, rank);
    }

    static long checked = 0;

    static void verify(int[] input) {
        int[] sorted = input.clone();
        Arrays.sort(sorted);
        for (int rank = 0; rank < input.length; rank++) {
            int[] work = input.clone();
            int actual = selectInPlace(work, 0, work.length, rank);
            if (actual != sorted[rank]) {
                throw new AssertionError(
                    "input=" + Arrays.toString(input)
                    + ", rank=" + rank
                    + ", expected=" + sorted[rank]
                    + ", actual=" + actual
                );
            }
            checked++;
        }
    }

    // Sinh mọi mảng độ dài n trên tập {-1, 0, 1}.
    static void enumerate(int[] a, int index) {
        if (index == a.length) {
            verify(a);
            return;
        }
        for (int value = -1; value <= 1; value++) {
            a[index] = value;
            enumerate(a, index + 1);
        }
    }

    public static void main(String[] args) {
        int[] sample = {
            12, 3, 5, 7, 4, 19, 26, 6,
            1, 8, 11, 2, 17, 9, 10
        };
        int[] original = sample.clone();

        System.out.println("sample=" + Arrays.toString(sample));
        for (int rank : new int[]{0, 7, 14}) {
            System.out.println(
                "k=" + rank + " value=" + kthSmallest(sample, rank)
            );
        }
        System.out.println(
            "inputPreserved=" + Arrays.equals(original, sample)
        );

        // n=1..6: tổng 6015 phép so sánh với Arrays.sort.
        for (int n = 1; n <= 6; n++) {
            enumerate(new int[n], 0);
        }

        // Bài kiểm thử 31 phần tử: kích hoạt đệ quy nhóm sâu hơn.
        int[] longer = new int[31];
        for (int i = 0; i < longer.length; i++) {
            longer[i] = (i * 17) % 19 - 9;
        }
        verify(longer);

        System.out.println("checked=" + checked);
    }
}
~~~

Lưu thành **MedianOfMediansDemo.java** và chạy với JDK 17+:

~~~bash
javac MedianOfMediansDemo.java
java MedianOfMediansDemo
~~~

**Đầu ra chính xác:**

~~~text
sample=[12, 3, 5, 7, 4, 19, 26, 6, 1, 8, 11, 2, 17, 9, 10]
k=0 value=1
k=7 value=8
k=14 value=26
inputPreserved=true
checked=6046
~~~

### Phân tích 6.046 phép kiểm thử

Với mỗi n từ 1 đến 6, chương trình sinh **toàn bộ** `3^n` mảng trên ba giá trị −1, 0, 1; ở mỗi mảng, kiểm tra **tất cả n chỉ số rank** hợp lệ bằng cách đối chiếu kết quả với phần tử ở cùng vị trí của một bản sao đã sắp.

\[
\sum_{n=1}^{6} n3^n=3+18+81+324+1215+4374=6015.
\]

Mảng `longer` dài 31 được kiểm tra ở toàn bộ **31 thứ hạng**, nên số kiểm thử là **6015 + 31 = 6046**. Những mảng trên −1,0,1 bao gồm trường hợp đã sắp, đảo ngược, tất cả bằng nhau và rất nhiều giá trị trùng, còn mảng 31 phần tử kiểm tra thêm những lời gọi chọn pivot đệ quy.

Một điểm kỹ thuật của mã: khi gom trung vị nhóm thứ `g` vào vị trí `left+g`, đích nằm trong các nhóm **đã xử lý**, không phải nhóm tiếp theo bắt đầu ở `left+5g`. Bởi vậy bước gom không phá những nhóm chưa xử lý. Mọi bước chỉ sắp nhóm hoặc hoán đổi, không thêm/bớt giá trị.

**Giới hạn kiểm thử:** việc 6046 ca nhỏ đều khớp là kiểm thử chức năng, **không thay thế chứng minh O(n) trong trường hợp xấu nhất**. Bằng chứng về thời gian dựa trên tỷ lệ loại bỏ và truy hồi, còn tính đúng dựa trên bất biến phân hoạch.

## 8. Vì sao thuật toán trả đúng phần tử thứ k?

Chứng minh tách hai vấn đề:

**Tính đúng của pivot:** median of medians chọn một **giá trị có mặt trong đoạn**. Bản thân pivot không cần là trung vị thật để quickselect đúng; pivot bảo đảm ở đây phục vụ giới hạn thời gian.

**Tính đúng của phân hoạch:** sau khi vòng DNF kết thúc, mảng trong đoạn [left,right) gồm ba miền: tất cả < pivot, tất cả = pivot, tất cả > pivot. Mọi phép swap bảo toàn đa tập giá trị.

**Tính đúng của chọn nhánh:** vì thứ tự giữa ba miền đúng theo giá trị, giá trị có thứ hạng tuyệt đối `rank` nằm trong đúng một trong ba miền. Nếu thuộc miền bằng, giá trị cần trả là pivot; nếu thuộc một phía, các giá trị bên còn lại không thể thay đổi kết quả và có thể bỏ qua.

**Tính kết thúc:** nếu đoạn dài hơn 5, nhóm bằng có ít nhất một phần tử do pivot đến từ đoạn. Vì vậy nhánh tiếp theo (nếu có) có kích thước nhỏ hơn đoạn gốc; base case sắp và trả trực tiếp khi còn ≤5 phần tử. Số phần tử hữu hạn nên thuật toán kết thúc.

Kết hợp lại, lời gọi `selectInPlace` trả đúng giá trị thứ `rank` mà không cần sắp toàn bộ. Điểm mấu chốt là **giữ đúng cận nửa mở**, giữ rank tuyệt đối và không làm sai bất biến khi hoán đổi với đầu miền > pivot.

## 9. Chi phí bộ nhớ và tác động lên dữ liệu đầu vào

Phiên bản cốt lõi dùng mảng gốc để sắp từng nhóm 5, gom trung vị và phân hoạch, vì vậy **không tạo thêm một mảng trung vị n/5 phần tử**. Với cách cài tại chỗ này, mỗi mức gọi hàm dùng một số biến cục bộ hằng số; stack đệ quy có độ sâu **O(log n)** trong phân tích chuẩn.

Tuy nhiên, **hàm công khai `kthSmallest` dùng `values.clone()`**, nên để giữ nguyên mảng đầu vào, nó cấp thêm **O(n)** bộ nhớ cho bản sao. Điều này không làm đổi cận thời gian O(n) nhưng làm tăng bộ nhớ phụ của API công khai.

| Phiên bản | Có thay đổi dữ liệu đầu vào? | Bộ nhớ phụ |
| --- | --- | --- |
| Lõi lựa chọn tại chỗ trên mảng | Có | O(log n) stack, O(1) biến mỗi mức |
| Hàm bọc sao chép mảng trước khi chọn | Không | O(n) bản sao, cộng stack |
| Sắp bản sao rồi lấy phần tử thứ k | Không | Phụ thuộc thuật toán sắp và bản sao |

Lưu ý: lựa chọn tại chỗ **không ổn định** đối với bản ghi có khóa bằng nhau, và không tạo ra một mảng đã sắp. Không được lấy lại `a[i]` ở những vị trí khác và cho rằng chúng đã đúng thứ tự sau khi chọn ra một rank.

Nếu bài toán muốn **thứ hạng của một bản ghi cụ thể**, cần định nghĩa khóa so sánh và cách phá hòa, ví dụ khóa ghép `(score, originalIndex)`. Khi chỉ trả về **giá trị k-th**, các bản ghi ngang khóa không cần phân biệt danh tính.

## 10. Chọn thuật toán nào trong thực tế?

| Phương án | Thời gian | Tính chất pivot | Lúc nên cân nhắc |
| --- | --- | --- | --- |
| Sắp bằng thuật toán O(n log n) rồi truy cập k | O(n log n) | Không sử dụng selection pivot | Cần nhiều thứ hạng hoặc cả dãy đã sắp |
| Quickselect pivot đầu/cuối | O(n²) xấu nhất | Dễ bị dữ liệu đối kháng làm lệch | Học cơ chế; không có bảo đảm tốt |
| Quickselect pivot ngẫu nhiên | O(n) kỳ vọng; O(n²) xấu nhất | Có tính ngẫu nhiên | Một vài truy vấn, chú trọng tốc độ thực tế |
| BFPRT median of medians | **O(n) xấu nhất** | Loại khoảng 30% ở mỗi mức | Cần bảo đảm thời gian theo lý thuyết |
| Min-heap giữ k+1 phần tử | O(n log(k+1)) | Không dùng pivot | k nhỏ; dữ liệu có thể xử lý dạng luồng |

Nếu chỉ cần **min hoặc max**, một lần quét O(n) với O(1) bộ nhớ còn đơn giản hơn median of medians. Nếu k nằm sát đầu dãy, heap kích thước k+1 có thể phù hợp. Nếu có nhiều truy vấn trên cùng dữ liệu, việc sắp một lần rồi truy cập mỗi vị trí O(1) có thể kinh tế hơn. Không chọn BFPRT chỉ vì nó có Big-O tốt mà bỏ qua hằng số và số lần sử dụng.

**Introselect** là hướng kết hợp: ban đầu dùng cách chọn pivot nhanh, theo dõi mức độ phân hoạch lệch hoặc độ sâu rồi chuyển sang một phương pháp có bảo đảm. Muốn tuyên bố một cài đặt introselect đạt cận worst-case cụ thể, phải xác nhận **fallback thực sự được dùng** và phân tích nó, không chỉ dựa vào tên gọi.

### Median of medians và quicksort

Quicksort xử lý **cả hai nhánh** sau khi phân hoạch, còn quickselect xử lý **một nhánh**. Vì thế không thể kết luận “quicksort dùng pivot median of medians là O(n)” chỉ từ kết quả BFPRT. Trong mô hình so sánh, sắp xếp tổng quát cần Ω(n log n) phép so sánh trường hợp xấu nhất; pivot bảo đảm có thể giúp tránh phân hoạch cực lệch nhưng vẫn cần xử lý nhiều nhánh và tính chi phí chọn pivot.

## 11. Trường hợp biên và lỗi phổ biến

### Bộ ca quan trọng

| Đầu vào | k | Kết quả đúng | Mục tiêu kiểm tra |
| --- | ---: | ---: | --- |
| [5] | 0 | 5 | Base case một phần tử |
| [2,1] | 0 | 1 | Cực tiểu |
| [2,1] | 1 | 2 | Cực đại |
| [4,4,4,4] | 2 | 4 | Tất cả phần tử bằng nhau |
| [3,1,3,2] | 2 | 3 | Rank tính cả phần tử trùng |
| [-7,2,0,-1] | 1 | -1 | Số âm |
| [10,9,8,7,6,5] | 3 | 8 | Dữ liệu đảo thứ tự |
| [1,2,3,4,5,6] | 3 | 4 | Dữ liệu đã tăng |
| [Integer.MIN_VALUE,0,Integer.MAX_VALUE] | 1 | 0 | Cực trị số nguyên |
| [] | 0 | Không hợp lệ | Không tồn tại rank |

Thêm các trường hợp có n=6,7,11,25,31 để kiểm tra nhóm cuối thiếu phần tử, một bước pivot đệ quy và những mức lồng nhau. Dùng nhiều giá trị bằng nhau, tất cả giá trị bằng nhau, chuỗi tăng/giảm, cùng một giá trị k ở cả gần đầu/gần giữa/gần cuối.

### Sai lầm 1: lẫn rank 0-based và thứ tự 1-based

Phần tử **nhỏ thứ t** theo ngôn ngữ tự nhiên thường tương ứng `rank=t-1`. Với [2,2,5] và t=2, rank=1 cho 2; rank=2 cho 5 là sai yêu cầu.

### Sai lầm 2: tin rằng pivot được chọn là trung vị toàn cục

Median of medians chỉ bảo đảm **tỷ lệ loại bỏ**. Nó không tự trả ngay kết quả trung vị toàn mảng. Phải thực hiện phân hoạch rồi đi tiếp đúng nhánh theo k.

### Sai lầm 3: bỏ qua nhóm còn ít hơn 5 phần tử

Một mảng 17 phần tử có ba nhóm đủ 5 và một nhóm 2. Nhóm cuối vẫn phải được xử lý theo quy ước; bỏ nó làm mất các giá trị, khiến lựa chọn rank có thể sai.

### Sai lầm 4: sai điều kiện biên của DNF

Sau khi đổi phần tử từ vị trí `gt-1` về `scan`, **không tăng scan ngay**. Phần tử vừa chuyển chưa được phân loại. Đúng là giảm gt, swap rồi lặp lại với scan hiện tại.

### Sai lầm 5: bỏ sót vùng bằng pivot

Với nhiều khóa trùng, phân hoạch hai phía đơn giản có thể tiếp tục trên đoạn lớn không cần thiết. Sử dụng ba miền <, =, > cho phép trả ngay hoặc loại toàn bộ nhóm ngang khóa.

### Sai lầm 6: đệ quy cả hai bên

Bài chỉ cần **một thứ hạng k**. Sau khi phân hoạch, một trong hai bên (hoặc nhóm bằng) chứa đáp án; xử lý cả hai phía là công việc dư và làm thay đổi truy hồi thời gian.

### Sai lầm 7: bỏ qua bộ nhớ của API clone

Phân hoạch tại chỗ không cần mảng phụ O(n) cho lõi, nhưng hàm `kthSmallest` trong ví dụ **có clone** nên toàn API dùng O(n) bộ nhớ phụ. Phải trình bày chính xác hợp đồng nào đang được phân tích.

### Sai lầm 8: chứng minh 30% bằng dấu < và >

Tỷ lệ bảo đảm tính theo **≤ pivot** và **≥ pivot**; với tất cả phần tử trùng, số phần tử < hoặc > pivot có thể bằng 0. Phải dùng 3-way partition để loại vùng bằng tương ứng.

### Sai lầm 9: thử nghiệm vài mảng rồi coi như chứng minh worst-case

Kiểm thử phát hiện lỗi chỉ số và cài đặt; chỉ phép đếm nhóm 5 và truy hồi thời gian mới chứng minh O(n) cho mọi đầu vào hợp lệ trong mô hình phân tích.

### Sai lầm 10: đánh đồng lựa chọn với sắp xếp

Sau khi trả giá trị thứ k, những phần tử còn lại chưa nhất thiết có thứ tự tăng dần. Không được dùng đầu ra của selection như thể toàn mảng đã được sort.

## 12. Bài tập tự luyện và đáp án

**Bài 1 — xác định thứ hạng.** Với [7,2,9,2,5], giá trị nhỏ thứ 1, thứ 3 và thứ 5 (đếm từ 1) là gì?

*Đáp án:* 2, 5, 9; rank tương ứng 0,2,4.

**Bài 2 — lấy trung vị nhóm.** Trên 15 phần tử trong ví dụ phần 4, hãy tính trung vị của từng nhóm 5 và pivot.

*Đáp án:* Ba trung vị là 5,8,10; pivot là 8. Trong ví dụ này k=7 trả 8.

**Bài 3 — chứng minh ba phần tử.** Một nhóm sau sắp là [1,4,6,8,11]. Nếu pivot p≤6, có ít nhất bao nhiêu phần tử trong nhóm ≥p?

*Đáp án:* Ít nhất 3: 6,8,11. Đây là viên gạch trong chứng minh khoảng 30% n.

**Bài 4 — nhánh sau phân hoạch.** Sau khi phân hoạch có `lt=8`, `gt=12`. Rank=10 và rank=12 đi đâu?

*Đáp án:* Rank=10 thuộc [8,12), trả pivot; rank=12 thuộc [12,right), đi nhánh lớn hơn pivot.

**Bài 5 — so sánh truy hồi.** Vì sao `T(n)≤T(n/5)+T(7n/10)+O(n)` cho O(n), còn `T(n)=T(n−1)+O(n)` có thể là Θ(n²)?

*Đáp án:* Hai bài toán con của truy hồi đầu có tổng tỷ lệ kích thước <1 nên công việc các mức giảm hình học; truy hồi sau giữ n−1 phần tử, tích lũy n+(n−1)+...+1.

**Bài 6 — dữ liệu trùng.** Với mảng gồm một triệu số 4, pivot=4. Số phần tử < và > pivot là bao nhiêu? Điều đó có mâu thuẫn bảo đảm O(n) không?

*Đáp án:* Cả hai bằng 0, nhưng nhóm = pivot chứa một triệu phần tử. Phân hoạch ba phía trả ngay cho mọi k hợp lệ, nên không có mâu thuẫn.

**Bài 7 — chọn phương pháp.** Bài toán chỉ cần trung vị của dữ liệu có thể bị tạo đối kháng, yêu cầu cận thời gian xấu nhất tuyến tính. Dùng pivot cố định đầu mảng, quickselect ngẫu nhiên hay BFPRT?

*Định hướng:* BFPRT cung cấp bảo đảm O(n) worst-case. Quickselect ngẫu nhiên chỉ bảo đảm O(n) kỳ vọng, có thể nhanh hơn trong thực tế. Pivot cố định có thể gặp O(n²).

**Bài 8 — bảo toàn dữ liệu.** Vì sao API công khai dùng clone, và nếu bỏ clone thì điều gì thay đổi?

*Đáp án:* Clone bảo toàn thứ tự của mảng người dùng nhưng tốn O(n) bộ nhớ. Bỏ clone giúp lõi thao tác trên mảng gốc với bộ nhớ thấp hơn, nhưng thứ tự các phần tử đầu vào sẽ thay đổi.

## Kết luận

**Median of medians** chọn pivot có bảo đảm bằng cách **sắp các nhóm tối đa 5, lấy trung vị nhóm, chọn trung vị của các trung vị và phân hoạch ba phía**. Cách đếm trung vị nhóm chứng minh mỗi bước có thể loại khoảng **3n/10−O(1)** phần tử khỏi nhánh tiếp tục, nên:

\[
T(n)\le T(n/5)+T(7n/10+O(1))+O(n)=O(n).
\]

Đây là **bảo đảm trường hợp xấu nhất** cho thuật toán chọn thống kê thứ tự, khác với **thời gian kỳ vọng tuyến tính** của quickselect ngẫu nhiên. Cần luôn thống nhất chỉ số k, quy ước khoảng [left,right), bất biến phân hoạch và cách xử lý phần tử trùng. Khi chọn triển khai trong thực tế, cân nhắc thêm chi phí hằng số, bộ nhớ và số truy vấn thứ hạng thay vì chỉ dựa vào nhãn độ phức tạp.
