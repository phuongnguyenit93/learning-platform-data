# Nhận diện bài toán con, bước chia và bước kết hợp

## 1. Bức tranh tổng quát về chia để trị

**Chia để trị (divide and conquer)** là kỹ thuật tổ chức thuật toán thành ba giai đoạn: **chia** bài toán lớn thành bài toán con nhỏ hơn, **giải** các bài toán con bằng cùng ý tưởng hoặc bằng trường hợp cơ sở, rồi **kết hợp** kết quả con để thu được kết quả đúng của bài toán ban đầu.

Đây không chỉ là việc cắt một mảng thành hai phần. Muốn chia để trị đúng, phải trả lời ba câu hỏi: (1) kết quả con có cùng ý nghĩa với kết quả cha hay không, (2) mọi trường hợp của bài toán cha đã được các nhánh hoặc bước kết hợp xử lý chưa, (3) kích thước có thực sự giảm để đệ quy kết thúc không?

Ví dụ cần sắp xếp [8, 3, 5, 1] tăng dần:

1. **Chia:** tách thành [8, 3] và [5, 1].
2. **Trị:** giải hai bài toán sắp xếp nhỏ hơn, được [3, 8] và [1, 5].
3. **Kết hợp:** trộn hai dãy đã sắp, được [1, 3, 5, 8].
4. **Cơ sở:** đoạn có không quá một phần tử vốn đã được sắp.

Nếu chỉ nối [3, 8] và [1, 5] thành [3, 8, 1, 5] thì kết quả vẫn sai: bước kết hợp phải đảm bảo hậu điều kiện của bài toán cha, chứ không đơn thuần ghép các bộ nhớ lại.

Trong thực tế, giai đoạn combine có thể rất rẻ như lấy min của hai số, tốn tuyến tính như trộn hai nửa đã sắp, hoặc phải xét **các phương án đi qua ranh giới** như khi tìm đoạn con liên tiếp có tổng lớn nhất.

## 2. Nhận diện bài toán con từ đề bài

Một **bài toán con (subproblem)** là phiên bản nhỏ hơn của bài toán đang giải, có cùng dạng đầu ra và tiêu chí đúng, áp dụng trên một phần dữ liệu hoặc miền giá trị.

Ví dụ:

| Bài toán cha | Đầu vào con | Đầu ra con cần có | Bước kết hợp |
| --- | --- | --- | --- |
| Tính tổng một dãy | Nửa trái và nửa phải | Tổng mỗi nửa | Cộng hai tổng |
| Tìm min/max | Hai đoạn | Cực trị mỗi đoạn | min/min hoặc max/max |
| Merge sort | Hai nửa mảng | Hai nửa đã sắp | Merge ổn định |
| Binary search | Một nửa miền tìm kiếm | Chỉ số/kết quả tìm kiếm | Trả tiếp kết quả, không trộn |
| Maximum subarray | Hai nửa dãy | Tổng đoạn con tốt nhất từng nửa | So với phương án cắt qua giữa |
| Đếm nghịch thế | Hai nửa dãy | Số nghịch thế và dãy đã sắp của mỗi nửa | Đếm cặp chéo khi merge |
| Quicksort | Hai vùng sau phân hoạch quanh pivot | Hai vùng đã sắp | Không cần trộn nếu phân hoạch đúng |

Muốn tự nhận diện bài toán con, hãy xác định chính xác:

- **Miền đầu vào:** chỉ số [lo, hi), cây con, khoảng tọa độ, một tập điểm, hoặc miền ứng viên.
- **Dạng câu trả lời:** một giá trị, mảng đã sắp, cặp chỉ số, tập nghiệm, hoặc tóm tắt thống kê.
- **Độ lớn giảm:** số phần tử, độ cao cây, số bit, số mũ, độ dài khoảng.
- **Thông tin phục vụ combine:** kết quả con đã đủ chưa, hay cần trả thêm tổng tiền tố, hậu tố, vị trí, hoặc cấu trúc phụ?
- **Tính độc lập và tính lặp:** hai nhánh có xử lý vùng khác nhau không; có tính đi tính lại cùng trạng thái không?

Hai nửa dãy không chồng nhau về chỉ số chưa có nghĩa nghiệm tối ưu chỉ nằm hoàn toàn trong một nửa. Trong maximum subarray, đoạn tốt nhất có thể kéo dài từ cuối nửa trái sang đầu nửa phải. Bước kết hợp phải xử lý trường hợp này.

**Phân biệt với quy hoạch động:** Fibonacci đệ quy ngây thơ gọi F(n-1) và F(n-2), dẫn đến nhiều trạng thái F(k) bị tính lặp. Nếu các bài toán con trùng nhau đáng kể, lưu kết quả qua memoization hoặc tabulation có thể hiệu quả hơn. Merge sort chuẩn có hai miền chỉ số tách biệt tại từng nút và không tái tính cùng một miền.

## 3. Bước chia và biểu diễn khoảng chỉ số

Với mảng Java, khoảng **nửa mở [lo, hi)** rất thuận tiện:

- Gồm các chỉ số lo, lo+1, ..., hi-1.
- Độ dài bằng hi-lo; rỗng nếu lo==hi.
- Mid = lo + (hi-lo)/2.
- Hai nửa là [lo, mid) và [mid, hi); chúng không giao nhau, hợp của chúng là [lo, hi).
- Với hi-lo>1, hai nửa đều nhỏ hơn đoạn cha, vì mid nằm hẳn bên trong.

~~~text
[lo, hi)             la doan cha
[lo, mid)            la doan con trai
[mid, hi)            la doan con phai

lo <= mid <= hi
length(left) + length(right) = length(parent)
~~~

Dùng cùng một quy ước xuyên suốt để tránh lỗi bỏ sót hoặc lặp phần tử ở mid. Nếu dùng đoạn đóng [lo,hi], công thức chia và base case phải được điều chỉnh nhất quán; không được trộn hai quy ước.

**Điều kiện dừng (base case)** không chỉ ngăn đệ quy vô hạn mà còn phải là lời giải đúng của trường hợp nhỏ nhất. Trong merge sort, đoạn có 0/1 phần tử đã được sắp. Với bài toán đoạn con có tổng lớn nhất **không cho đoạn rỗng**, đoạn một phần tử phải trả chính giá trị phần tử đó, dù giá trị âm. Trả 0 sẽ ngầm cho phép đoạn rỗng và làm sai dãy toàn âm.

### Cân bằng và phân hoạch

Không phải lúc nào cũng chia đúng một nửa:

- Merge sort thường chia gần đều để giữ chiều cao cây đệ quy O(log n).
- Quicksort chọn pivot và phân hoạch. Nếu pivot tạo hai nửa gần cân bằng, thời gian điển hình O(n log n); nếu liên tục tạo hai miền 0 và n-1, thời gian xấu nhất O(n²).
- Binary search chỉ giải **một nhánh** sau phép so sánh, nên mỗi bước làm kích thước miền ứng viên giảm gần một nửa.
- Với cây, một bài toán con có thể là cây con trái/phải; chúng không nhất thiết cân bằng về số nút.

Một thiết kế chia hợp lệ phải bảo đảm mỗi lời gọi con nhỏ hơn cha, phần tử hoặc nghiệm bị bỏ qua phải có lý do, và bước kết hợp có đủ dữ liệu cần thiết.

## 4. Bước kết hợp: phân loại nghiệm trước khi viết mã

Khi nhận được các lời giải con đúng, ta cần chứng minh lời giải cha được hình thành từ chúng. Hãy **liệt kê các vị trí có thể có của nghiệm** đối với ranh giới chia.

### Kết hợp một số

Nếu bài toán là tổng dãy, sum(cha) = sum(trái) + sum(phải). Nếu tìm min, min(cha) = min(min(trái), min(phải)). Combine O(1) và hầu như không có trường hợp xuyên biên đặc biệt.

Điều này không tự làm thuật toán nhanh hơn một vòng lặp tuyến tính. Điểm mạnh có thể nằm ở cấu trúc đệ quy dễ chứng minh hoặc khả năng xử lý nhiều phần độc lập song song.

### Merge: kết hợp hai dãy đã sắp

Cho L và R đã sắp tăng dần. Dùng hai con trỏ i, j:

1. So sánh phần tử hiện tại ở L[i] và R[j].
2. Đưa phần tử nhỏ hơn vào buffer đầu ra rồi tăng con trỏ phía đó.
3. Nếu bằng nhau và yêu cầu ổn định, lấy phần tử từ **nửa trái trước**.
4. Khi hết một phía, chuyển các phần tử còn lại của phía kia.
5. Ghi kết quả trở về đúng đoạn cha.

Bất biến trong khi merge: đoạn đã ghi vào buffer là phần tử nhỏ nhất trong đa tập đã được xét và đang tăng dần; mỗi phần tử được ghi đúng một lần. Do hai nửa đều được sắp, phần tử nhỏ nhất chưa dùng luôn nằm ở đầu một trong hai nửa. Combine O(n) theo kích thước đoạn cha.

### Crossing: kết hợp nghiệm băng qua ranh giới

Với **maximum subarray sum**, đoạn con phải **liên tiếp và không rỗng**. Mỗi nghiệm của đoạn cha rơi đúng vào một trong ba loại:

1. Nằm hoàn toàn bên trái mid.
2. Nằm hoàn toàn bên phải mid.
3. Có phần tử ở cả hai phía của mid.

Hai loại đầu do hai đệ quy trả về. Loại thứ ba được biểu diễn bằng:

~~~text
bestCross = bestSuffix(left) + bestPrefix(right)
answer    = max(bestLeft, bestRight, bestCross)
~~~

bestSuffix(left) là tổng lớn nhất của một hậu tố **không rỗng** kết thúc ở mid-1. bestPrefix(right) là tổng lớn nhất của một tiền tố **không rỗng** bắt đầu ở mid. Ghép hai đoạn này cho một đoạn liên tiếp xuyên ranh giới; ngược lại, mọi đoạn xuyên ranh giới phải gồm đúng một hậu tố trái và một tiền tố phải. Như vậy phép kết hợp đã xét **đầy đủ** mọi ứng viên.

Không được thay bestCross bằng bestLeft + bestRight: hai đoạn con tối ưu riêng biệt có thể không chạm nhau, nên việc cộng chúng không nhất thiết tạo đoạn liên tiếp.

Để tính bestSuffix, quét từ mid-1 về lo; để tính bestPrefix, quét từ mid đến hi-1. Mỗi lượt duyệt tuyến tính, tổng combine O(hi-lo), bộ nhớ biến cục bộ O(1).

## 5. Khi kết quả của con chưa đủ: thiết kế một tóm tắt mạnh hơn

Bài toán maximum subarray có thể được giải bằng cách quét crossing ở mỗi nút. Nhưng nếu muốn **kết hợp hai đoạn đã tính trước chỉ trong O(1)**, có thể yêu cầu mỗi bài toán con trả bốn trường:

- **sum**: tổng toàn đoạn.
- **prefix**: tổng tiền tố không rỗng tốt nhất.
- **suffix**: tổng hậu tố không rỗng tốt nhất.
- **best**: tổng đoạn con liên tiếp không rỗng tốt nhất.

Với hai đoạn A và B đứng kề nhau, ta có:

~~~text
sum(A+B)    = sum(A) + sum(B)
prefix(A+B) = max(prefix(A), sum(A) + prefix(B))
suffix(A+B) = max(suffix(B), sum(B) + suffix(A))
best(A+B)   = max(best(A), best(B), suffix(A) + prefix(B))
~~~

Với đoạn một phần tử [x], cả bốn giá trị đều bằng x. Công thức đúng cả khi x âm, miễn là định nghĩa **không cho đoạn rỗng** được giữ xuyên suốt.

Đây là ví dụ cho kỹ năng quan trọng khi nhận diện bài toán con: **đầu ra con phải chứa đủ thông tin để combine**. Nếu chỉ giữ best thì không biết cực trị của đoạn băng qua ranh giới; bổ sung prefix/suffix giải quyết vấn đề.

Cấu trúc tóm tắt này cũng là cơ sở xây segment tree cho truy vấn tổng đoạn con lớn nhất trên nhiều khoảng. Nó thể hiện sự liên quan giữa chia để trị và cấu trúc dữ liệu phân đoạn, nhưng không đồng nghĩa với mọi thuật toán chia để trị đều cần segment tree.

## 6. Chứng minh tính đúng bằng quy nạp

Một thuật toán chia để trị thường được chứng minh **theo kích thước đầu vào**:

1. **Cơ sở:** khi dữ liệu đủ nhỏ, hàm trả đáp án chính xác.
2. **Giả thiết quy nạp:** mọi lời gọi con với kích thước nhỏ hơn n đều đúng.
3. **Chia hợp lệ:** các lời gọi con nhận đúng miền cần thiết và đều có kích thước nhỏ hơn.
4. **Kết hợp đầy đủ:** dùng kết quả con đúng, xử lý mọi trường hợp xuyên biên (nếu có), bảo toàn dữ liệu và tạo kết quả đúng cho cha.
5. **Kết thúc:** kích thước giảm nghiêm ngặt nên cuối cùng tới cơ sở.

**Đối với merge sort:** hai nửa đã sắp theo giả thiết quy nạp. Vì phần tử nhỏ nhất còn lại luôn ở đầu một trong hai dãy, thủ tục merge lần lượt chọn đúng phần tử nhỏ nhất. Khi cả hai hết, toàn bộ đoạn cha được sắp tăng dần, chứa đủ các phần tử gốc. Nếu so sánh hai khóa bằng nhau chọn bên trái trước thì kết quả ổn định.

**Đối với maximum subarray:** một đoạn con bất kỳ nằm trái, nằm phải hoặc xuyên mid; không có loại thứ tư. Hai nhánh giải tối ưu hai loại đầu, còn quét hậu tố/trước tố giải loại cuối. Lấy max ba đáp án vì thế tối ưu trên toàn đoạn.

**Tính dừng:** nếu hi-lo>1 thì mid nằm trong (lo,hi), hai lời gọi con đều ngắn hơn. Base case cho hi-lo≤1 trong merge sort hoặc ==1 trong maximum subarray ngăn không cho đệ quy gọi lại cùng đoạn vô hạn.

Chứng minh **tính đúng** phải tách khỏi phân tích **chi phí**. Một thuật toán có thể đúng mà quá chậm, hoặc nhanh nhưng bỏ quên nghiệm xuyên ranh giới.

## 7. Phương trình truy hồi và ước lượng độ phức tạp

Gọi T(n) là thời gian giải bài toán kích thước n. Nếu có a bài toán con tương đương cỡ n/b và công việc ngoài lời gọi con là f(n), dạng truy hồi thường gặp:

~~~text
T(n) = a * T(n/b) + f(n)
~~~

Lưu ý n có thể lẻ, kích thước thật dùng floor/ceil. Với các thuật toán chia lệch hoặc có đầu vào phụ thuộc dữ liệu, không nên máy móc áp dụng dạng n/b.

| Thuật toán | Truy hồi đại diện | Thời gian |
| --- | --- | --- |
| Binary search | T(n)=T(n/2)+O(1) | O(log n) |
| Tính sum/min/max bằng hai nửa | T(n)=2T(n/2)+O(1) | O(n) |
| Merge sort | T(n)=2T(n/2)+O(n) | O(n log n) |
| Maximum subarray quét crossing | T(n)=2T(n/2)+O(n) | O(n log n) |
| Lũy thừa nhanh, phép nhân O(1) | T(n)=T(n/2)+O(1) | O(log n) theo số mũ |
| Quicksort bị lệch cực đại | T(n)=T(n-1)+O(n) | O(n²) |

**Vì sao merge sort là O(n log n)?** Cây đệ quy gần cân bằng có O(log n) mức; trong một mức, các đoạn rời nhau và tổng số phần tử được trộn là O(n); do đó công việc tổng O(n) nhân O(log n). Không thể kết luận mọi thuật toán chia đôi đều O(log n): binary search giải **một** nửa, còn merge sort giải **cả hai** nửa.

**Bộ nhớ** cũng phải được phân tích:

- Merge sort với một buffer chung n phần tử sử dụng O(n) bộ nhớ phụ và stack O(log n).
- Maximum subarray dùng quét crossing không cần mảng phụ, nhưng đệ quy có stack O(log n) nhờ chia cân bằng.
- Binary search đệ quy cần stack O(log n), trong khi biến thể lặp có thể dùng O(1).
- Quicksort lệch nặng có thể sâu O(n), gây StackOverflowError với đầu vào lớn nếu cài đặt không có biện pháp giới hạn.

Master theorem có thể giúp giải một số truy hồi dạng chuẩn, nhưng trước đó phải **đếm đúng số nhánh, kích thước và chi phí combine**, thay vì suy luận theo tên thuật toán.

## 8. Ví dụ Java 17 chạy độc lập: merge sort và maximum subarray

Ví dụ minh họa hai phong cách combine thực sự khác nhau: trộn dãy tăng dần và xét nghiệm vượt qua ranh giới. Mã dùng khoảng [lo,hi) và tính midpoint an toàn trong phạm vi chỉ số mảng Java.

Lưu dưới tên **DivideConquerDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class DivideConquerDemo {
    // Tra mang moi da sap; giu nguyen input.
    static int[] mergeSorted(int[] input) {
        Objects.requireNonNull(input, "input");
        int[] a = input.clone();
        int[] buffer = new int[a.length];
        sortRange(a, buffer, 0, a.length);
        return a;
    }

    private static void sortRange(int[] a, int[] buffer, int lo, int hi) {
        if (hi - lo <= 1) {
            return;
        }

        int mid = lo + (hi - lo) / 2;
        sortRange(a, buffer, lo, mid);
        sortRange(a, buffer, mid, hi);
        merge(a, buffer, lo, mid, hi);
    }

    // Hai nua [lo,mid) va [mid,hi) da sap.
    private static void merge(
            int[] a, int[] buffer, int lo, int mid, int hi) {
        int i = lo, j = mid, w = lo;

        while (i < mid && j < hi) {
            if (a[i] <= a[j]) {
                buffer[w++] = a[i++]; // Lay trai truoc khi bang nhau.
            } else {
                buffer[w++] = a[j++];
            }
        }
        while (i < mid) {
            buffer[w++] = a[i++];
        }
        while (j < hi) {
            buffer[w++] = a[j++];
        }
        System.arraycopy(buffer, lo, a, lo, hi - lo);
    }

    // Tong lon nhat cua doan con lien tiep KHONG RONG.
    static long maximumSubarraySum(int[] input) {
        Objects.requireNonNull(input, "input");
        if (input.length == 0) {
            throw new IllegalArgumentException("array must not be empty");
        }
        return bestRange(input, 0, input.length);
    }

    private static long bestRange(int[] a, int lo, int hi) {
        if (hi - lo == 1) {
            return a[lo];
        }

        int mid = lo + (hi - lo) / 2;
        long left = bestRange(a, lo, mid);
        long right = bestRange(a, mid, hi);

        long running = 0L;
        long suffix = Long.MIN_VALUE;
        for (int i = mid - 1; i >= lo; i--) {
            running += a[i];
            suffix = Math.max(suffix, running);
        }

        running = 0L;
        long prefix = Long.MIN_VALUE;
        for (int i = mid; i < hi; i++) {
            running += a[i];
            prefix = Math.max(prefix, running);
        }

        return Math.max(Math.max(left, right), suffix + prefix);
    }

    public static void main(String[] args) {
        int[] source = {8, 3, 5, 1, 3};
        System.out.println("sorted = " +
                Arrays.toString(mergeSorted(source)));
        System.out.println("original = " + Arrays.toString(source));

        int[] data = {-2, 1, -3, 4, -1, 2, 1, -5, 4};
        System.out.println("maximum sum = " + maximumSubarraySum(data));
        System.out.println("all negative = " +
                maximumSubarraySum(new int[]{-8, -3, -5}));
        System.out.println("empty sorted = " +
                Arrays.toString(mergeSorted(new int[0])));

        try {
            maximumSubarraySum(new int[0]);
        } catch (IllegalArgumentException e) {
            System.out.println("empty maximum: " + e.getMessage());
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên** trong thư mục chứa tệp:

~~~bash
javac DivideConquerDemo.java
java DivideConquerDemo
~~~

**Stdout chính xác:**

~~~text
sorted = [1, 3, 3, 5, 8]
original = [8, 3, 5, 1, 3]
maximum sum = 6
all negative = -3
empty sorted = []
empty maximum: array must not be empty
~~~

### Diễn giải mã

**mergeSorted** sao chép mảng nên không thay đổi input. Hàm sortRange chia [lo,hi) thành hai phần cho đến base case dài 0/1. Hàm merge dùng hai con trỏ và buffer chung, luôn đặt phần tử nhỏ hơn tiếp theo; khi bằng nhau lấy phía trái trước. Kết quả tăng dần; thời gian O(n log n), bộ nhớ phụ O(n), stack O(log n).

**maximumSubarraySum** từ chối dãy rỗng vì không cho đoạn rỗng. Với một phần tử, kết quả chính là giá trị ấy, nên dãy toàn âm vẫn đúng. bestRange tính hai đáp án con, quét hậu tố không rỗng lớn nhất của trái và tiền tố không rỗng lớn nhất của phải, rồi lấy max ba loại. Thời gian O(n log n), stack O(log n), không cấp phát thêm mảng.

Các biến tổng dùng **long** để tránh tràn int khi có nhiều phần tử giá trị lớn. Với một mảng Java int[] hợp lệ, tổng toán học của một đoạn đủ nằm trong miền long; điều này không mặc nhiên đúng nếu dữ liệu là long[] hoặc một luồng không giới hạn.

Bài toán maximum subarray chỉ yêu cầu tổng tối ưu còn có **Kadane O(n), O(1)**; giải pháp chia để trị ở đây làm rõ vai trò của kết hợp crossing và cách chứng minh, không phải tuyên bố nó tốt nhất cho mọi tình huống.

Nếu muốn trả luôn chỉ số [start,end) của đoạn tối ưu, phải bổ sung chỉ số vào kết quả con và định nghĩa rõ cách hòa khi nhiều đoạn có cùng tổng. Không được chỉ trả tổng rồi suy đoán chỉ số từ nó.

## 9. Sự khác nhau giữa chia để trị, đệ quy và quy hoạch động

Ba khái niệm này liên quan nhưng không đồng nhất:

- **Đệ quy** là kỹ thuật lập trình khi hàm gọi lại chính nó (trực tiếp hoặc gián tiếp); không tự xác định chiến lược phân chia hoặc combine.
- **Chia để trị** là chiến lược giải bài toán bằng các phần nhỏ hơn, thường dùng đệ quy nhưng có thể mô phỏng bằng stack hoặc xử lý bottom-up.
- **Quy hoạch động** là chiến lược khai thác bài toán con lặp lại và tính chất tối ưu con, lưu/truy hồi kết quả để tránh tính lại, hoặc xây bảng theo thứ tự phụ thuộc.

Merge sort chia hai nửa không chồng nhau; Fibonacci đệ quy ngây thơ có nhiều trạng thái trùng lặp; maximum subarray một lần có thể dùng chia để trị, nhưng nếu nhiều truy vấn cập nhật xen kẽ thì segment tree với kết quả tóm tắt bốn trường có thể phù hợp hơn.

Khi các bài toán con có sự phụ thuộc dữ liệu lớn, “chia” không nhất thiết giúp song song hóa. Ngay cả với hai nhánh độc lập, triển khai song song có chi phí tạo tác vụ, đồng bộ và bộ nhớ; cần giới hạn kích thước nhỏ để tránh overhead lớn hơn lợi ích.

## 10. Quy trình thiết kế khi gặp đề bài mới

1. **Viết hợp đồng đầu vào/đầu ra.** Một số, một mảng, một cặp chỉ số hay tóm tắt? Dữ liệu rỗng có hợp lệ không?
2. **Đề xuất kích thước bài toán.** Thường là hi-lo đối với dãy hoặc số nút đối với cây.
3. **Xác định base case.** Với cỡ nhỏ nhất, kết quả gì là đúng?
4. **Chia bằng quy tắc chính xác.** Nêu rõ các biên và tránh phần tử bị bỏ/trùng.
5. **Nhận diện loại nghiệm.** Chỉ ở trái, chỉ ở phải, hay có phần vượt ranh giới?
6. **Thiết kế kết quả con đủ mạnh.** Có cần thêm tổng, prefix, suffix, cặp chỉ số, cây kết quả hoặc buffer?
7. **Chứng minh combine.** Nếu các kết quả con đúng thì vì sao kết quả cha đúng và bảo toàn dữ liệu?
8. **Viết truy hồi.** Đếm bao nhiêu lời gọi con, kích thước mỗi lời gọi, và công việc chia/kết hợp.
9. **Kiểm thử dữ liệu biên.** Rỗng, một phần tử, mọi phần tử âm, trùng nhau, cực trị số nguyên và kích thước lẻ.
10. **Đánh giá giải pháp thay thế.** Chia để trị có thực sự lợi hơn quét một lần, sắp xếp trực tiếp hoặc quy hoạch động không?

### Khung giả mã

~~~text
solve(problem):
    if isBaseCase(problem):
        return solveDirectly(problem)

    subproblems = divide(problem)
    answers = []
    for subproblem in subproblems:
        answers.add(solve(subproblem))
    return combine(problem, answers)
~~~

Đây là **giả mã mô hình**, không phải chương trình Java hoàn chỉnh. Một bài toán cụ thể phải định nghĩa rõ isBaseCase, divide, combine cùng bất biến của chúng; số nhánh có thể là một, hai hoặc nhiều hơn.

## 11. Lỗi điển hình

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Lời gọi con không giảm kích thước | Đệ quy vô hạn hoặc tràn stack | Chứng minh giảm hi-lo, thêm base case |
| Trộn khoảng đóng và nửa mở | Bỏ sót/trùng phần tử mid | Dùng nhất quán [lo,mid), [mid,hi) |
| Chỉ nối hai nửa đã sắp | Toàn dãy chưa chắc tăng dần | Thực hiện merge |
| Quên nghiệm xuyên ranh giới | Maximum subarray hoặc đếm cặp sai | Phân loại nghiệm, xử lý crossing |
| Cộng bestLeft và bestRight trong maximum subarray | Ghép hai đoạn không liền nhau | Cộng bestSuffixLeft và bestPrefixRight |
| Base case trả 0 cho mọi số âm | Sai quy ước đoạn không rỗng | Trả giá trị phần tử ở base case |
| Chỉ giữ kết quả con quá ít thông tin | Không tính được kết quả cha | Bổ sung trường tóm tắt phục vụ combine |
| Coi mọi bài toán chia đôi là O(log n) | Đánh giá thấp chi phí | Đếm nhánh và công việc từng tầng |
| Copy mảng con liên tục | Tốn bộ nhớ/thời gian | Truyền chỉ số, dùng buffer phù hợp |
| Không tính bộ nhớ stack/buffer | Công bố sai độ phức tạp bộ nhớ | Phân biệt stack, đầu ra, cấp phát phụ |
| Quicksort chọn pivot tệ | Phân hoạch quá lệch | Phân tích worst case, cải thiện pivot |
| Không giữ ổn định khi khóa bằng nhau | Đảo thứ tự bản ghi cùng khóa | Chọn phía trái trước khi merge nếu cần |

Một cách kiểm tra nhanh: trong mỗi lời gọi, hãy viết rõ **bất biến đã biết trước combine** và **hậu điều kiện phải đúng sau combine**. Nếu không chứng minh được mối nối giữa hai câu này, thuật toán còn thiếu lập luận quan trọng.

## 12. Kiểm thử theo tính chất và bài tập

### Các thuộc tính cần xác minh

**Merge sort:**

- Mảng đầu ra không giảm tại mọi cặp phần tử liên tiếp.
- Giữ nguyên số lần xuất hiện của từng giá trị, kể cả giá trị trùng và âm.
- Không sửa input với API mergeSorted vì đã clone.
- Đoạn 0/1 phần tử là base case; không có lỗi biên ở n lẻ.
- Với biến thể bản ghi có cùng khóa, nếu dùng <= lấy trái trước thì giữ thứ tự xuất hiện tương đối của bản ghi bằng khóa.

**Maximum subarray:**

- Với dãy một phần tử [x], đáp án bằng x.
- Với dãy toàn âm, đáp án bằng cực đại của dãy, không tự trả 0.
- Với dãy nhỏ có thể đối chiếu brute force O(n²) bằng cách xét mọi đoạn không rỗng.
- Khi có số dương và số âm lẫn nhau, crossing phải tạo đoạn liên tiếp.
- Không sửa input; kết quả dùng long với sum có thể vượt miền int.

### Bộ ca kiểm thử

| Đầu vào | Kết quả |
| --- | --- |
| [] | mergeSorted trả []; maximumSubarraySum báo lỗi |
| [5] | mergeSorted trả [5]; maximumSubarraySum trả 5 |
| [-8,-3,-5] | maximumSubarraySum trả -3 |
| [8,3,5,1,3] | mergeSorted trả [1,3,3,5,8] |
| [4,4,4] | mergeSorted giữ ba bản sao |
| [-2,1,-3,4,-1,2,1,-5,4] | maximumSubarraySum trả 6 |
| [Integer.MAX_VALUE,Integer.MAX_VALUE] | maximumSubarraySum trả 4294967294 bằng long |
| Mảng tăng sẵn/giảm sẵn | mergeSorted vẫn đúng và O(n log n) với cài đặt đã cho |
| null | Cả hai hàm từ chối qua Objects.requireNonNull |

### Bài tập tự luyện

1. Vẽ cây đệ quy merge sort của [8,3,5,1,3]. Ghi các đoạn [lo,hi) ở từng nút và các lần merge theo thứ tự. Kiểm tra không bỏ phần tử khi n lẻ.
2. Tính tổng dãy bằng chia hai nửa: viết base case và công thức combine; dùng quy nạp chứng minh đúng. So sánh độ phức tạp với quét một lần.
3. Mô phỏng maximum subarray trên [-2,1,-3,4,-1,2,1,-5,4]; ở nút gốc tìm bestLeft, bestRight và bestCross rồi giải thích kết quả cuối.
4. Đếm số cặp nghịch thế (i<j và a[i]>a[j]) bằng merge sort; khi lấy một phần tử từ nửa phải trước phần tử hiện tại của nửa trái, có bao nhiêu cặp chéo mới được đếm?
5. Phân tích T(n)=T(n/2)+O(1), T(n)=2T(n/2)+O(1), T(n)=2T(n/2)+O(n) bằng cây đệ quy; giải thích vì sao số nhánh là yếu tố quan trọng.
6. Tạo cấu trúc tóm tắt (sum,prefix,suffix,best) cho mỗi đoạn và chứng minh công thức combine, kể cả khi mọi số âm.
7. Vì sao quicksort chọn pivot luôn là giá trị nhỏ nhất có thể bị O(n²)? Vẽ kích thước các bài toán con theo từng cấp.

**Kết luận:** trước khi dùng đệ quy, hãy xác định **bài toán con nào giữ nguyên hợp đồng**, **cách chia nào làm chúng nhỏ hơn**, và **bước kết hợp nào bảo toàn kết quả đúng**, bao gồm trường hợp đi qua ranh giới. Sau khi chứng minh được những điều ấy, phương trình truy hồi mới cho phép đánh giá chính xác hiệu năng thuật toán.
