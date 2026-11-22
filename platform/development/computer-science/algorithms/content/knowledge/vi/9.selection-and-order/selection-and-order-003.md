# Quickselect và việc chỉ tiếp tục trên một phần phân hoạch

**Quickselect** là thuật toán tìm **phần tử nhỏ thứ k** theo một thứ hạng cụ thể mà không phải sắp xếp toàn bộ mảng. Thuật toán dùng bước **phân hoạch** (*partition*) tương tự Quicksort: chọn một giá trị pivot, tổ chức các phần tử nhỏ hơn pivot về bên trái và các phần tử lớn hơn pivot về bên phải. Điểm phân biệt quan trọng nhất là **Quicksort xử lý cả hai phía để sắp xếp toàn bộ; Quickselect chỉ xử lý tiếp đúng một phía có thể chứa thứ hạng cần tìm**. Khi thứ hạng nằm trong nhóm phần tử bằng pivot, Quickselect trả lời ngay.

Với pivot ngẫu nhiên đều trong đoạn đang xét, Quickselect có **thời gian kỳ vọng O(n)**, còn trường hợp xấu nhất vẫn **O(n²)**. Phiên bản lặp, phân hoạch trực tiếp trên mảng có thể dùng **O(1) bộ nhớ phụ**, nhưng **thay đổi vị trí các phần tử** và không tạo ra mảng đã sắp xếp.

Bài học giải thích định nghĩa thứ hạng, ba vùng phân hoạch, lý do chỉ tiếp tục một phía, cách xử lý nhiều khóa trùng nhau, bất biến và chứng minh tính đúng, phân tích thời gian, ví dụ Java 17+ chạy được, các tình huống biên và lỗi cài đặt.

## 1. Thứ hạng k được hiểu như thế nào?

Cho mảng số nguyên a gồm n phần tử. Nếu sắp xếp toàn bộ thành mảng b theo thứ tự không giảm, **thứ hạng k (0-based)** là giá trị:

\[
b[k], \qquad 0 \le k < n.
\]

Ví dụ:

\[
a=[9,1,5,3,5,7,5,2],\quad
b=[1,2,3,5,5,5,7,9].
\]

| k (0-based) | Thứ hạng theo cách gọi từ 1 | Giá trị |
|---:|---|---:|
| 0 | Nhỏ thứ nhất | 1 |
| 1 | Nhỏ thứ hai | 2 |
| 2 | Nhỏ thứ ba | 3 |
| 3 | Nhỏ thứ tư | 5 |
| 4 | Nhỏ thứ năm | 5 |
| 5 | Nhỏ thứ sáu | 5 |
| 6 | Nhỏ thứ bảy | 7 |
| 7 | Nhỏ thứ tám/lớn nhất | 9 |

Các giá trị trùng nhau **vẫn được tính riêng theo số lần xuất hiện**. Ba bản sao 5 chiếm ba thứ hạng 3, 4, 5. Nếu đề yêu cầu “nhỏ thứ tư” theo cách đánh số 1-based, chương trình dùng k=3. Nếu muốn “giá trị phân biệt nhỏ thứ tư”, đó là **một đề bài khác**, cần loại bản sao trước hoặc thay đổi cách đếm.

Quickselect thường trả **giá trị theo thứ hạng**, không đảm bảo trả bản ghi xuất hiện đầu tiên khi có các khóa bằng nhau. Nếu muốn chỉ số gốc hoặc cần ổn định của bản ghi, phải bổ sung tiêu chí hòa.

Khi n=0 hoặc k nằm ngoài [0,n-1], không có thứ hạng hợp lệ. Thuật toán cần từ chối yêu cầu ngay, thay vì cố đọc một pivot không tồn tại.

## 2. Quicksort và Quickselect khác nhau ở đâu?

**Quicksort** phân hoạch rồi tiếp tục sắp xếp **cả hai phía**, vì đầu ra là toàn bộ mảng có thứ tự. **Quickselect** chỉ cần xác định giá trị tại một vị trí k của mảng đã sắp tưởng tượng, nên không cần sắp chính xác các phần tử khác.

Ví dụ chọn giá trị nhỏ thứ tư của a=[9,1,5,3,5,7,5,2]. Nếu biết có đúng 3 giá trị nhỏ hơn 5, tiếp theo là 3 bản sao bằng 5, thì giá trị nhỏ thứ tư chắc chắn bằng 5. Không cần sắp thứ tự 1,2,3 hay 7,9.

| Tiêu chí | Quicksort | Quickselect |
|---|---|---|
| Kết quả | Mảng đã sắp | Một giá trị theo hạng k |
| Sau phân hoạch | Sắp các phía còn chưa có thứ tự | **Chỉ tiếp tục phía chứa k**, hoặc dừng |
| Thời gian kỳ vọng với pivot ngẫu nhiên | O(n log n) | **O(n)** |
| Trường hợp xấu nhất với pivot liên tục xấu | O(n²) | **O(n²)** |
| Sau khi hoàn thành | Các giá trị được sắp | Các vùng đã phân hoạch nhưng chưa chắc được sắp |

Đây là ý tưởng tiết kiệm công việc quan trọng: **một phía không chứa đáp án không còn lý do để xử lý**. Thuật toán cũng có thể dùng vòng lặp thay cho lời gọi đệ quy, vì chỉ có duy nhất một nhánh cần theo tiếp.

## 3. Phân hoạch ba vùng cho khóa trùng

Chọn **giá trị pivot** từ một phần tử trong đoạn đang tìm kiếm [left,right], với hai biên đều được tính. Phân hoạch **ba vùng** (*three-way partition*, Dutch National Flag) thuận lợi khi mảng có nhiều giá trị bằng nhau.

Dùng ba chỉ số **lt**, **i**, **gt**. Ban đầu:

\[
lt=left,\quad i=left,\quad gt=right.
\]

Trong quá trình phân hoạch, bảo toàn các vùng sau:

\[
\begin{aligned}
[left,lt) &: \text{mọi phần tử } <pivot,\\
[lt,i) &: \text{mọi phần tử } =pivot,\\
[i,gt] &: \text{chưa kiểm tra},\\
(gt,right] &: \text{mọi phần tử } >pivot.
\end{aligned}
\]

Lặp khi i<=gt:

1. Nếu **a[i]<pivot**: đổi chỗ a[i] với a[lt], rồi tăng cả **lt** và **i**.
2. Nếu **a[i]>pivot**: đổi chỗ a[i] với a[gt], giảm **gt** và **không tăng i**.
3. Nếu **a[i]==pivot**: tăng **i**.

Vì sao ở nhánh thứ hai phải giữ i? Phần tử được hoán đổi từ vị trí gt về vị trí i **chưa được phân loại**; nó có thể nhỏ, bằng hoặc lớn hơn pivot. Nếu tăng i ngay, ta có thể bỏ sót một phần tử sai vùng. Ở nhánh thứ nhất, vị trí lt trước khi đổi thuộc vùng bằng pivot (hoặc trùng i khi vùng bằng rỗng), nên tăng i không làm bỏ qua phần tử chưa phân loại.

Khi kết thúc, i>gt và đoạn đang xét trở thành:

\[
[left,lt-1] <pivot,\qquad
[lt,gt] =pivot,\qquad
[gt+1,right] >pivot.
\]

**Không có yêu cầu sắp xếp bên trong mỗi vùng.** Ví dụ nhóm nhỏ hơn pivot có thể chứa 3,1,2 theo thứ tự bất kỳ, miễn mọi giá trị đều nhỏ hơn pivot. Hoán đổi trực tiếp cũng không đảm bảo giữ thứ tự tương đối của bản ghi có cùng khóa; thuật toán không ổn định theo nghĩa sắp xếp.

### Mô phỏng với pivot bằng 5

Xét lại mảng [9,1,5,3,5,7,5,2]. Khi chọn pivot=5, sau phân hoạch ta biết chắc:

| Phần | Giá trị thuộc nhóm | Chỉ số trong mảng sau phân hoạch |
|---|---|---|
| Nhỏ hơn 5 | 1,2,3 | 0,1,2 |
| Bằng 5 | 5,5,5 | 3,4,5 |
| Lớn hơn 5 | 7,9 | 6,7 |

Thứ tự nội bộ các nhóm có thể khác; các **biên** thì xác định: lt=3, gt=5.

- **k=1:** chỉ giữ nhóm nhỏ hơn, tức các chỉ số [0,2].
- **k=4:** k nằm trong [3,5], trả **5** ngay.
- **k=6:** chỉ giữ nhóm lớn hơn, tức các chỉ số [6,7].

Không phải tiếp tục cả hai phía. Khi k ở vùng bằng pivot, giá trị cần tìm đã biết mà không cần sắp xếp thêm.

## 4. Quy tắc chỉ tiếp tục một phần phân hoạch

Giữ hai biên **left, right** bao quanh phần chưa giải quyết. Sau khi phân hoạch, sử dụng:

~~~text
if k < lt:
    right = lt - 1      // Chỉ còn nhóm nhỏ hơn pivot.
else if k > gt:
    left = gt + 1       // Chỉ còn nhóm lớn hơn pivot.
else:
    return pivot        // k thuộc nhóm bằng pivot.
~~~

**Quan trọng:** k là **chỉ số tuyệt đối 0-based trong toàn mảng** và không thay đổi sau các lần phân hoạch. Nếu k=6 và đoạn được giữ là [6,7], vẫn so **k=6** với các chỉ số lt,gt trong toàn mảng. Chỉ những triển khai sử dụng k **tương đối với mảng con** mới cần thay đổi k khi dịch biên trái; không được trộn hai hệ quy chiếu.

Nếu nhiều phần tử bằng pivot, tất cả chúng xuất hiện trong vùng [lt,gt]. Điều này cho phép trả ngay đối với mọi thứ hạng thuộc vùng ấy và tránh phân hoạch lặp lại nhiều bản sao giống nhau.

**Phần bị loại không cần sắp xếp.** Chỉ cần biết nó nằm hoàn toàn về phía nhỏ hơn hoặc lớn hơn phần đang giữ. Đó là cơ sở của Quickselect.

## 5. Mã giả hoàn chỉnh

~~~text
quickselect(a, k):              // k đánh số từ 0
    if a rỗng or k < 0 or k >= n:
        báo lỗi

    left = 0
    right = n - 1

    while left <= right:
        pivot = a[vị_trí_ngẫu_nhiên_trong_[left,right]]

        lt = left
        i = left
        gt = right

        while i <= gt:
            if a[i] < pivot:
                swap(a[i], a[lt])
                lt++
                i++
            else if a[i] > pivot:
                swap(a[i], a[gt])
                gt--
                // Không tăng i ở nhánh này.
            else:
                i++

        if k < lt:
            right = lt - 1
        else if k > gt:
            left = gt + 1
        else:
            return pivot

    báo lỗi bất biến lập trình
~~~

Bước phân hoạch có ít nhất **một phần tử bằng pivot**, vì pivot được chọn từ trong đoạn thật. Vì vậy, nếu không trả ngay, mỗi lần thu hẹp đều bỏ ít nhất một phần tử. Vòng ngoài không thể chạy vô hạn với k hợp lệ.

Cửa sổ **[left,right] là đoạn đóng**: việc đặt right=lt-1 hoặc left=gt+1 loại toàn bộ vùng bằng và vùng không cần thiết. Nếu thay bằng right=lt hoặc left=gt, có thể giữ lại một vị trí không thuộc nhánh cần tìm, dẫn đến lỗi biên hoặc giảm tiến triển không như chứng minh.

## 6. Chứng minh tính đúng

### Bất biến phân hoạch

Ban đầu vùng nhỏ, vùng bằng và vùng lớn đều rỗng; mọi phần tử trong [left,right] chưa phân loại. Bất biến bốn vùng ở phần 3 đúng.

Mỗi nhánh của vòng i<=gt làm giảm số phần tử chưa phân loại đúng một: hoặc tăng i, hoặc giảm gt. Các phần tử được chuyển sang vùng phù hợp theo so sánh với pivot. Vì vậy, sau hữu hạn bước, vùng chưa phân loại rỗng và các đoạn [left,lt-1], [lt,gt], [gt+1,right] thỏa quan hệ <, =, > pivot.

### Bất biến lựa chọn thứ hạng

Trước vòng ngoài đầu tiên, thứ hạng k thuộc mảng đầy đủ. Sau mỗi bước thu hẹp, các phần đã loại nằm hoàn toàn về phía thứ hạng thấp hơn hoặc cao hơn các ứng viên giữ lại, nên giá trị ở thứ hạng k chỉ còn phụ thuộc vào đoạn [left,right] đang xét.

Sau phân hoạch:

- Nếu k<lt, tất cả phần bằng và lớn hơn pivot đều không thể giữ thứ hạng nhỏ như vậy; **chỉ vùng nhỏ hơn** còn có thể chứa đáp án.
- Nếu lt<=k<=gt, vị trí thứ hạng k nằm trong vùng mà mọi phần tử đều bằng pivot; **trả pivot là đúng**.
- Nếu k>gt, mọi phần nhỏ hơn hoặc bằng pivot thuộc các vị trí thứ hạng thấp; **chỉ vùng lớn hơn** còn liên quan.

Không có nhánh nào loại bỏ đáp án. Nếu chưa trả kết quả, khoảng tìm kiếm giảm độ dài ít nhất một, nên vòng ngoài kết thúc sau hữu hạn lần phân hoạch. Từ đó Quickselect trả đúng giá trị ở thứ hạng k.

**Lưu ý:** chứng minh không yêu cầu sắp nội bộ các phần tử đã loại; chỉ cần quan hệ thứ tự **giữa các vùng**.

## 7. Java 17+: Quickselect ngẫu nhiên, ba vùng, không đệ quy

Triển khai sau nhận mảng int và k 0-based; phân hoạch trực tiếp trên mảng và dùng **ThreadLocalRandom** chọn vị trí pivot ngẫu nhiên trong đoạn đang xét. Giá trị trả về **không phụ thuộc cách pivot được chọn**, dù trạng thái mảng trung gian có thể khác giữa các lần chạy. Trong main, các lần gọi dùng bản sao để giữ nguyên dữ liệu ban đầu.

Lưu tệp **QuickselectDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;

public class QuickselectDemo {
    static void swap(int[] a, int x, int y) {
        int temp = a[x];
        a[x] = a[y];
        a[y] = temp;
    }

    // k is zero-based. The input array is modified.
    static int kthSmallest(int[] a, int k) {
        Objects.requireNonNull(a, "array");
        if (k < 0 || k >= a.length) {
            throw new IllegalArgumentException("k must be in [0, n-1]");
        }

        int left = 0;
        int right = a.length - 1;

        while (left <= right) {
            int pivotIndex = ThreadLocalRandom.current()
                .nextInt(left, right + 1);
            int pivot = a[pivotIndex];

            int lt = left;
            int i = left;
            int gt = right;

            while (i <= gt) {
                if (a[i] < pivot) {
                    swap(a, lt, i);
                    lt++;
                    i++;
                } else if (a[i] > pivot) {
                    swap(a, i, gt);
                    gt--;
                } else {
                    i++;
                }
            }

            if (k < lt) {
                right = lt - 1;
            } else if (k > gt) {
                left = gt + 1;
            } else {
                return pivot;
            }
        }

        throw new IllegalStateException("unreachable for valid k");
    }

    public static void main(String[] args) {
        int[] data = {9, 1, 5, 3, 5, 7, 5, 2};

        System.out.println("Input: " + Arrays.toString(data));
        System.out.println("Rank 0: " + kthSmallest(data.clone(), 0));
        System.out.println("Rank 3: " + kthSmallest(data.clone(), 3));
        System.out.println("Rank 4: " + kthSmallest(data.clone(), 4));
        System.out.println("Rank 6: " + kthSmallest(data.clone(), 6));
        System.out.println("Rank 7: " + kthSmallest(data.clone(), 7));
        System.out.println("All equal: "
            + kthSmallest(new int[] {4, 4, 4, 4}, 2));
        System.out.println("Negative: "
            + kthSmallest(new int[] {-8, 3, 0, -1}, 1));
        System.out.println("Original intact: " + Arrays.toString(data));
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac QuickselectDemo.java
java QuickselectDemo
~~~

**Stdout chính xác:**

~~~text
Input: [9, 1, 5, 3, 5, 7, 5, 2]
Rank 0: 1
Rank 3: 5
Rank 4: 5
Rank 6: 7
Rank 7: 9
All equal: 4
Negative: -1
Original intact: [9, 1, 5, 3, 5, 7, 5, 2]
~~~

**Các lưu ý trong mã:**

- **nextInt(left, right+1)** lấy chỉ số ngẫu nhiên từ left đến right, vì cận phải của API là loại trừ. Chỉ số right không vượt **a.length-1**, nên right+1 không vượt giới hạn int đối với mảng Java.
- Kết quả của kthSmallest là **giá trị**, không phải chỉ số ban đầu của bản ghi.
- So sánh trực tiếp bằng <, >, == thay vì lấy hiệu a[i]-pivot, tránh tràn số int khi gặp Integer.MIN_VALUE và Integer.MAX_VALUE.
- Phân hoạch ba vùng xử lý tốt trường hợp mọi giá trị bằng nhau: sau một lượt quét, nhóm bằng phủ toàn đoạn và hàm trả ngay.
- **a.clone()** ở main là cách tránh làm biến đổi dữ liệu gốc khi thử nhiều hạng; bản thân thuật toán hoán đổi **tại chỗ**. Nếu clone, nơi gọi phải cộng chi phí **O(n) thời gian và O(n) bộ nhớ** cho bản sao.
- Null bị từ chối bằng NullPointerException qua Objects.requireNonNull; mảng rỗng và k ngoài [0,n-1] bị từ chối bằng IllegalArgumentException.
- Sau khi gọi trực tiếp kthSmallest(a,k), mảng **không bảo đảm sắp tăng**. Không được dùng nó như một mảng đã sắp để tìm kiếm nhị phân nếu chưa sắp riêng.

## 8. Vì sao thời gian kỳ vọng là O(n)?

Với m phần tử trong đoạn hiện tại, bước phân hoạch ba vùng duyệt vùng chưa xét bằng cách tăng i hoặc giảm gt, nên tốn **\(\Theta(m)\)** công việc.

Nếu những pivot liên tiếp chia đoạn gần cân bằng, chỉ một phía được tiếp tục, nên tổng kích thước các đoạn có dạng:

\[
n,\ n/2,\ n/4,\ n/8,\ldots
\]

Tổng công việc phân hoạch:

\[
cn+c(n/2)+c(n/4)+\cdots<2cn=O(n).
\]

Đây là một **minh họa** cho những lần chia tốt, không có nghĩa mọi pivot đều chia đôi.

Khi pivot được chọn **đều ngẫu nhiên trong đoạn đang xét**, với các phần tử phân biệt, xác suất pivot có hạng rơi vào phần giữa của đoạn là một hằng số dương (xấp xỉ một nửa cho phần giữa 50% hạng). Trong bước thuận lợi đó, phía còn lại có kích thước không vượt khoảng \(3m/4\). Nhờ xác suất thuận lợi không đổi và chi phí mỗi bước tuyến tính theo đoạn còn lại, tổng công việc có **kỳ vọng tuyến tính** theo n:

\[
\mathbb{E}[T(n)]=O(n).
\]

Với nhiều phần tử trùng khóa, phân hoạch ba vùng có thể dừng nhanh hơn khi k thuộc nhóm bằng pivot. ThreadLocalRandom sử dụng bộ sinh giả ngẫu nhiên; lý thuyết kỳ vọng dùng mô hình pivot được chọn ngẫu nhiên đều, không bảo đảm thời gian cố định cho **từng lần chạy cụ thể**.

### Trường hợp xấu nhất O(n²)

Nếu pivot luôn là phần tử cực nhỏ hoặc cực lớn của đoạn mà k cần tiếp tục ở phía còn lại, mỗi lần có thể chỉ loại **một** phần tử. Các lần phân hoạch phải xử lý lần lượt n, n-1, n-2,... phần tử. Tổng:

\[
n+(n-1)+(n-2)+\cdots+1=\Theta(n^2).
\]

Ví dụ, nếu một quy tắc chọn pivot cố định liên tục chọn phần tử nhỏ nhất trong khi đang tìm phần tử lớn nhất, các đoạn thu hẹp rất chậm. Pivot ngẫu nhiên giúp giảm xác suất chọn xấu liên tiếp, nhưng **không làm biến mất trường hợp xấu nhất**.

Để có cận trên **O(n) ở trường hợp xấu nhất**, có các phương pháp lựa chọn pivot có bảo đảm, như **median of medians (BFPRT)**, hoặc những chiến lược lai (*introselect*) phù hợp. Mã Java ở phần 7 là randomized Quickselect, không phải thuật toán BFPRT.

### Bộ nhớ phụ

- Với vòng lặp và hoán đổi tại chỗ: **O(1)** biến con trỏ/pivot, không tính mảng đầu vào.
- Với cài đặt đệ quy một phía: bộ nhớ ngăn xếp phụ thuộc số mức; trường hợp xấu nhất có thể **O(n)** khung lời gọi.
- Nếu cần giữ nguyên mảng, phải tạo bản sao **O(n)**; đây là chi phí của hợp đồng bảo toàn đầu vào, khác với bộ nhớ phụ của bản thân hàm tại chỗ.

## 9. Khi nào chọn Quickselect?

| Phương pháp | Thích hợp khi | Đánh đổi |
|---|---|---|
| Sắp xếp toàn bộ rồi đọc b[k] | Cần toàn bộ thứ tự hoặc **nhiều truy vấn k** trên cùng dữ liệu | Sắp so sánh đầy đủ thường O(n log n) |
| **Randomized Quickselect** | Cần một giá trị theo hạng k, có thể thay đổi mảng | O(n) kỳ vọng, O(n²) xấu nhất |
| Heap giữ k+1 giá trị nhỏ nhất | k nhỏ và dữ liệu được xử lý theo luồng | Thường O(n log(k+1)) thời gian, O(k+1) bộ nhớ |
| Counting/tần suất | Khóa nguyên thuộc miền giá trị R nhỏ | Có thể tìm hạng trong O(n+R), dùng O(R) bộ nhớ đếm |
| Median of medians | Cần đảm bảo cận xấu nhất tuyến tính | O(n) worst-case với thuật toán đúng, thường phức tạp hơn |

Nếu cần tìm **giá trị lớn thứ r** khi r đếm từ 1, có thể gọi hàm nhỏ thứ **n-r** (k 0-based), sau khi kiểm tra 1<=r<=n.

Nếu cần **k phần tử nhỏ nhất** chứ không chỉ phần tử ở hạng k-1, Quickselect có thể xác định ngưỡng và phân vùng, nhưng nhóm k phần tử được lấy ra **không mặc nhiên có thứ tự**. Nếu người dùng yêu cầu kết quả đã sắp, cần sắp riêng các phần tử được chọn.

## 10. Các trường hợp biên

| Trường hợp | Hành vi cần xác minh |
|---|---|
| n=0 | Không có thứ hạng hợp lệ; phải báo lỗi |
| k<0 hoặc k>=n | Báo lỗi trước khi đọc pivot |
| n=1, k=0 | Trả phần tử duy nhất |
| k=0 | Trả giá trị nhỏ nhất |
| k=n-1 | Trả giá trị lớn nhất |
| Mọi giá trị bằng nhau | Vùng bằng pivot phủ toàn bộ; trả ngay sau một lượt phân hoạch |
| Nhiều bản sao của giá trị ở thứ hạng k | Trả cùng một giá trị cho mọi k nằm trong nhóm bằng |
| Giá trị âm và hai đầu miền int | So sánh trực tiếp tránh phép trừ có thể tràn |
| Mảng tăng hoặc giảm sẵn | Kết quả phải đúng; pivot ngẫu nhiên giúp giảm thiên lệch của quy tắc cố định |
| Yêu cầu không sửa đầu vào | Dùng clone hoặc lựa chọn thuật toán khác; tính cả chi phí sao chép |
| Các bản ghi có khóa bằng nhau nhưng payload khác | Kết quả giá trị đúng không đồng nghĩa ổn định hoặc chọn được bản ghi hòa theo tiêu chí khác |

Trong kiểm thử, có thể đối chiếu Quickselect với việc **sắp một bản sao** rồi đọc phần tử tại k. Với nhiều mảng ngẫu nhiên nhỏ, duyệt qua mọi k hợp lệ; bổ sung những ca nhiều trùng lặp, dãy đã sắp, dãy đảo ngược, số âm và giá trị cực trị int. Đối chiếu này kiểm tra toàn bộ thuật toán, không chỉ một ví dụ thuận lợi.

## 11. Lỗi thường gặp

1. **Tiếp tục cả hai phía**, làm công việc thừa giống Quicksort dù chỉ cần một thứ hạng.
2. **Giữ sai phía:** k<lt cần phần nhỏ, k>gt cần phần lớn, k nằm trong [lt,gt] trả ngay.
3. **Nhầm k 1-based với 0-based:** phần tử nhỏ thứ nhất ứng với k=0 trong mã Java.
4. **Không xử lý nhóm bằng pivot:** nhiều bản sao có thể khiến thuật toán hai vùng xử lý thừa hoặc xác định hạng không rõ.
5. **Tăng i sau khi đổi a[i] với a[gt]**, khiến phần tử mới ở i chưa được xét.
6. **Dùng điều kiện i<gt** và bỏ qua vị trí cuối của vùng chưa phân loại.
7. **Nhầm biên đoạn đóng:** phần nhỏ là [left,lt-1], phần bằng [lt,gt], phần lớn [gt+1,right].
8. **Thay đổi k theo biên mới** khi mã vẫn dùng chỉ số tuyệt đối toàn mảng.
9. **Cho rằng mọi lần phân hoạch đều chia gần đều:** pivot cực trị có thể chỉ loại một phần tử.
10. **Tuyên bố O(n) cho mọi đầu vào:** Quickselect ngẫu nhiên chỉ được bảo đảm kỳ vọng O(n), xấu nhất có thể O(n²).
11. **Cho rằng mảng đã sắp sau khi chọn:** Quickselect không sắp đầy đủ những vùng khác.
12. **Quên tác dụng phụ hoán đổi:** phải sao chép khi không được phép sửa mảng nguồn.
13. **Không tính chi phí clone:** bộ nhớ phụ tại chỗ O(1), nhưng bản sao O(n).
14. **So sánh bằng phép trừ int:** có thể tràn, hãy dùng các toán tử so sánh.
15. **Không kiểm tra k hợp lệ**, đặc biệt với mảng rỗng.

## 12. Bài tập tự kiểm tra

**Bài 1.** Cho [8,2,5,1,5,6], pivot=5. Vùng nhỏ hơn, bằng và lớn hơn gồm bao nhiêu phần tử? Với k=3, Quickselect cần xử lý tiếp không?

*Đáp án:* Mỗi vùng có 2 phần tử; nhóm bằng pivot chiếm chỉ số 2..3, nên k=3 trả **5** ngay.

**Bài 2.** Sau phân hoạch có lt=4, gt=6. Hãy cho biết bước xử lý với k=2, k=5 và k=8.

*Đáp án:* k=2 thì right=3. k=5 thì trả pivot. k=8 thì left=7.

**Bài 3.** Tại sao khi a[i]>pivot, sau hoán đổi với a[gt], i không tăng?

*Đáp án:* Giá trị chuyển tới i từ gt chưa được phân loại, có thể thuộc bất kỳ vùng nào. Phải xét lại a[i] ở vòng tiếp theo.

**Bài 4.** Với 8 giá trị, muốn phần tử **nhỏ thứ tư** theo cách gọi từ 1, phải truyền k bao nhiêu?

*Đáp án:* **k=3**.

**Bài 5.** Vì sao Quickselect có kỳ vọng O(n) nhưng Quicksort ngẫu nhiên có kỳ vọng O(n log n)?

*Đáp án:* Sau phân hoạch, Quickselect chỉ giải quyết **một phía** chứa k; Quicksort giải cả hai phía để sắp toàn bộ. Tổng số phần tử phải xử lý của Quickselect qua những phân hoạch ngẫu nhiên có kỳ vọng tuyến tính.

**Bài 6.** Sau khi chạy kthSmallest, có được dùng mảng đã hoán đổi như mảng sắp xếp không?

*Đáp án:* **Không.** Hàm chỉ bảo đảm giá trị đúng thứ hạng k; các vùng khác có thể chưa được sắp.

**Tóm tắt:** Quickselect phân hoạch quanh pivot, biết thứ hạng k thuộc phía nhỏ hơn, phía lớn hơn hay nhóm bằng pivot, rồi **chỉ tiếp tục trên một phía** hoặc dừng. Phân hoạch **ba vùng** xử lý khóa trùng hiệu quả; chọn pivot ngẫu nhiên cho **O(n) thời gian kỳ vọng** và phiên bản lặp tại chỗ dùng **O(1) bộ nhớ phụ**, nhưng vẫn có trường hợp xấu nhất O(n²) và có thể làm thay đổi mảng đầu vào.