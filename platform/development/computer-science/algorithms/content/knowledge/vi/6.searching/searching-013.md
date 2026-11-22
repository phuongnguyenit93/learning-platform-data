# Tránh tràn khi tính trung điểm và lỗi lệch một đơn vị

**Tìm kiếm nhị phân** (*binary search*) thường được mô tả bằng vài dòng: chọn phần tử giữa, so sánh và loại một nửa khoảng tìm kiếm. Nhưng việc xác định “giữa” bằng phép cộng số nguyên và dịch biên sai một vị trí có thể khiến chương trình trả sai kết quả, truy cập ngoài mảng hoặc lặp vô hạn. Hai lỗi đặc biệt quan trọng là **tràn số nguyên khi tính trung điểm** (*integer overflow*) và **lỗi lệch một đơn vị** (*off-by-one*).

Bài học này giải thích cách thiết kế các biên tìm kiếm, chứng minh thuật toán kết thúc, xử lý phần tử trùng nhau và viết mã Java 17+ có thể kiểm tra bằng những ca biên khó. Các kỹ thuật cũng áp dụng cho tìm kiếm nhị phân trên miền đáp án có điều kiện khả thi đơn điệu.

## 1. Điều kiện để tìm kiếm nhị phân đúng

Trên mảng sắp xếp **không giảm** (các phần tử bằng nhau được phép đứng cạnh nhau), mục tiêu có thể là:

- Tìm **một vị trí bất kỳ** chứa khóa cần tìm.
- Tìm **vị trí đầu tiên** chứa khóa, gọi là *first occurrence*.
- Tìm **vị trí cuối cùng** chứa khóa, gọi là *last occurrence*.
- Tìm **lower bound**: chỉ số đầu tiên mà giá trị không nhỏ hơn khóa, tức phần tử có giá trị \(\ge x\).
- Tìm **upper bound**: chỉ số đầu tiên mà giá trị lớn hơn khóa, tức phần tử có giá trị \(>x\).

Nếu mảng đã sắp xếp không giảm, mệnh đề \(a[i]\ge x\) luôn có dạng **false, false, ..., true, true** theo chỉ số i. Mệnh đề \(a[i]>x\) cũng vậy. Tìm điểm chuyển từ false sang true là cách diễn đạt thống nhất và dễ chứng minh của tìm kiếm nhị phân.

Nếu dữ liệu chưa được sắp xếp hoặc điều kiện không đơn điệu, việc bỏ nửa khoảng dựa trên một lần so sánh có thể làm mất đáp án. **Tối ưu cách tính trung điểm không thể cứu một thuật toán sử dụng sai giả thiết về dữ liệu.**

## 2. Vì sao trung điểm thông thường có thể tràn?

Công thức quen thuộc:

\[
mid=\frac{left+right}{2}
\]

thường được viết trong Java thành:

~~~java
int mid = (left + right) / 2; // Dễ tràn với int
~~~

Java dùng kiểu **int có dấu 32 bit**, nhận giá trị từ \(-2^{31}\) đến \(2^{31}-1\). Phép cộng int tràn sẽ tạo ra giá trị theo biểu diễn 32 bit; Java không tự nâng kết quả thành long và không báo ngoại lệ. Vì vậy, dù left và right đều là chỉ số không âm hợp lệ, tổng của chúng có thể vượt Integer.MAX_VALUE.

**Ví dụ cụ thể:**

~~~text
left  = 1_800_000_000
right = 2_000_000_000

Tổng toán học = 3_800_000_000
Tổng int bị tràn = -494_967_296

(left + right) / 2 trong Java = -247_483_648  (SAI)
Trung điểm toán học             = 1_900_000_000  (ĐÚNG)
~~~

Một chỉ số âm có thể khiến phép truy cập mảng lỗi, hoặc khiến biên di chuyển sai dẫn tới kết quả không đúng. Điều nguy hiểm là với mảng nhỏ, công thức ngây thơ vẫn chạy bình thường; lỗi chỉ xuất hiện ở đầu vào lớn hoặc miền đáp án rộng.

Với bất biến **\(0\le left\le right\le \mathrm{Integer.MAX\_VALUE}\)**, công thức an toàn là:

~~~java
int mid = left + (right - left) / 2;
~~~

Vì \(0\le right-left\le\mathrm{Integer.MAX\_VALUE}\), phép trừ không tràn. Giá trị \((right-left)/2\) không âm và không vượt quá \(right-left\), nên \(mid\le right\); phép cộng cuối không tràn. Công thức chọn **trung điểm thấp** (*lower midpoint*), tức \(\lfloor(left+right)/2\rfloor\).

Cách viết **left + (right-left)/2** phụ thuộc vào giả thiết khoảng và kiểu dữ liệu. **Không dùng máy móc** khi left có thể âm lớn và right dương lớn: hiệu right-left khi đó cũng có thể tràn int. Chẳng hạn left = Integer.MIN_VALUE, right = Integer.MAX_VALUE thì hiệu toán học vượt miền int.

Nếu cần tìm trong **miền int có dấu bất kỳ**, nâng lên long **trước khi trừ**:

~~~java
int left = Integer.MIN_VALUE;
int right = Integer.MAX_VALUE;

long distance = (long) right - (long) left;
int mid = (int) ((long) left + distance / 2L);
~~~

Ở đây khoảng cách được tính bằng long nên không tràn. Công thức chọn trung điểm thấp theo khoảng cách từ left và cho một giá trị nằm giữa hai biên int; việc ép ngược lại int an toàn do mid vẫn nằm trong miền int. Trường hợp miền tìm kiếm được biểu diễn bằng long rộng gần hết miền 64 bit cần lập luận riêng để tránh tràn phép hiệu long.

**Một lỗi liên quan:** dùng phép trừ để so sánh số nguyên, ví dụ điều kiện a[mid] - target < 0. Phép trừ cũng có thể tràn. Nên viết **a[mid] < target**, **a[mid] > target** hoặc dùng Integer.compare, không biến so sánh thành phép trừ mà không chứng minh được khoảng giá trị.

## 3. Chọn nhất quán một kiểu khoảng tìm kiếm

Hai quy ước thường dùng là **đoạn đóng** \([left,right]\) và **đoạn nửa mở** \([left,right)\). Cả hai đều đúng nếu khởi tạo, điều kiện vòng lặp và cách cập nhật biên đi cùng một quy ước.

| Quy tắc | Đoạn đóng \([left,right]\) | Nửa mở \([left,right)\) |
|---|---|---|
| Biên trái ban đầu | 0 | 0 |
| Biên phải ban đầu | n - 1 | n |
| Phần tử còn cần xét | left đến right, có cả hai biên | left đến right - 1 |
| Điều kiện còn ứng viên | left <= right | left < right |
| Số phần tử trong khoảng | right - left + 1 | right - left |
| Điều kiện dừng | left > right nếu không tìm thấy | left == right khi thu hẹp điểm chèn |
| Nguy cơ thường gặp | Dùng right = mid khi đã loại mid | Dùng right = n để truy cập a[right] |

**Khoảng đóng** thuận tiện khi cần tìm một phần tử đúng bằng khóa và trả **-1** nếu không có. **Khoảng nửa mở** thuận tiện khi cần tìm biên đầu tiên thỏa điều kiện, trả về một vị trí chèn trong phạm vi \([0,n]\).

Phải coi left, right như phần của **bất biến**, không chỉ là biến đếm. Ví dụ, khi tìm lower bound, right = n là **biên loại trừ**, hoàn toàn hợp lệ dù a[n] không tồn tại. Không được truy cập a[right] mà phải luôn đảm bảo mid < right <= n.

## 4. Tìm một vị trí bằng đoạn đóng

Với mảng tăng không giảm, thuật toán tìm **một** vị trí có giá trị bằng target:

~~~text
left = 0
right = n - 1

while left <= right:
    mid = left + (right - left) / 2

    if a[mid] == target:
        return mid
    else if a[mid] < target:
        left = mid + 1
    else:
        right = mid - 1

return -1
~~~

**Bất biến:** nếu target có mặt trong mảng và chưa tìm thấy, thì vẫn có ít nhất một vị trí bằng target trong đoạn đóng \([left,right]\). Khi a[mid] < target, mọi vị trí \(i\le mid\) có giá trị không lớn hơn a[mid], nên không thể chứa target; phải chuyển left đến **mid + 1**. Khi a[mid] > target, phải chuyển right đến **mid - 1**.

Tại mỗi lần lặp mà chưa trả kết quả, mid bị loại khỏi khoảng. Do đó số vị trí còn lại giảm và vòng lặp kết thúc. Khi left > right, khoảng ứng viên rỗng và có thể trả -1.

**Đừng dùng right = mid** ở nhánh a[mid] > target trong mô hình này khi vẫn giữ while left <= right: mid chưa bị loại; nếu left = right = mid và a[mid] > target, hai biên không đổi, dẫn đến vòng lặp vô hạn.

**Đầu vào rỗng:** nếu n = 0, right = -1, điều kiện left <= right sai ngay; hàm trả -1 mà không truy cập mảng. Đây là lý do quan trọng phải kiểm tra chính xác điều kiện dừng.

Tìm kiếm theo đoạn đóng **không đảm bảo** vị trí đầu tiên hay cuối cùng khi có giá trị trùng: nó trả vị trí đầu tiên **theo thứ tự thử trung điểm**, có thể nằm giữa một nhóm phần tử bằng nhau.

## 5. Lower bound bằng đoạn nửa mở

**Lower bound** của target là chỉ số nhỏ nhất i thỏa \(a[i]\ge target\). Nếu không tồn tại, đáp án bằng **n**. Công thức dùng khoảng nửa mở:

~~~text
left = 0
right = n

while left < right:
    mid = left + (right - left) / 2

    if a[mid] < target:
        left = mid + 1
    else:
        right = mid

return left
~~~

Ba vùng được phân định trong quá trình chạy:

- **[0, left):** đã biết mọi phần tử đều **< target**.
- **[left, right):** vùng chưa xác định, vẫn có thể chứa điểm chuyển.
- **[right, n):** đã biết mọi phần tử đều **>= target**.

Ban đầu left = 0, right = n nên hai vùng đã xác định đều rỗng: bất biến đúng. Nếu a[mid] < target, nhờ mảng không giảm, các phần tử tới mid đều < target, nên có thể chuyển left = mid+1. Nếu a[mid] >= target, vị trí mid **có thể chính là điểm chuyển**, nên phải giữ lại bằng right = mid, không phải mid-1.

Vì left < right, trung điểm thấp luôn thỏa left <= mid < right. Cập nhật left = mid+1 hoặc right = mid đều khiến độ dài khoảng chưa xác định giảm; thuật toán kết thúc khi left == right. Khi đó mọi phần tử ở trước left nhỏ hơn target, mọi phần tử từ left trở đi (nếu có) đều >= target, nên left chính là lower bound.

**Upper bound** tương tự nhưng tìm chỉ số đầu tiên có giá trị **> target**, bằng cách thay điều kiện trong nhánh tiến left:

~~~text
if a[mid] <= target:
    left = mid + 1
else:
    right = mid
~~~

Vì lowerBound và upperBound đều có thể trả n, phải kiểm tra chỉ số trước khi đọc phần tử. Ví dụ:

~~~text
first = lowerBound(a, target)
if first < n AND a[first] == target:
    tìm thấy vị trí đầu tiên là first
else:
    không có target

after = upperBound(a, target)
last = after - 1
if last >= 0 AND a[last] == target:
    tìm thấy vị trí cuối cùng là last
else:
    không có target
~~~

Những điều kiện kiểm tra a[first] và a[last] chỉ đúng khi chỉ số nằm trong phạm vi; trong Java, toán tử **&&** đánh giá ngắn mạch từ trái sang phải nên giúp tránh truy cập ngoài mảng.

## 6. Lỗi lệch một đơn vị xuất hiện như thế nào?

Lỗi *off-by-one* xảy ra khi điều kiện dừng, biên trái/phải hoặc phép cập nhật sai đi đúng một đơn vị. Một thay đổi rất nhỏ có thể dẫn đến sai kết quả hoặc không kết thúc.

| Tình huống sai | Hậu quả | Cách đúng |
|---|---|---|
| Đoạn nửa mở nhưng đặt right = n - 1 | Bỏ mất vị trí cuối hoặc vị trí chèn n | Bắt đầu right = n |
| Đoạn đóng nhưng đặt right = n | Có khả năng truy cập a[n] | Bắt đầu right = n - 1 |
| Đoạn đóng, nhánh a[mid] < target đặt left = mid | mid không bị loại khi left = mid | Dùng left = mid + 1 |
| Đoạn đóng, nhánh a[mid] > target đặt right = mid | Không tiến triển khi left = right = mid | Dùng right = mid - 1 |
| Lower bound, a[mid] >= target đặt right = mid - 1 | Có thể bỏ chính phần tử đầu tiên thỏa điều kiện | Dùng right = mid |
| Lower bound, a[mid] < target đặt left = mid | Có thể lặp vô hạn khi right = left + 1 | Dùng left = mid + 1 |
| Chỉ dùng a[lowerBound] == target, không kiểm tra lowerBound < n | Truy cập ngoài mảng nếu mọi giá trị đều < target | Kiểm tra biên trước |
| Dùng while left < right cho tìm đúng bằng target trên đoạn đóng nhưng không kiểm tra phần tử còn lại | Có thể bỏ sót ứng viên cuối | Dùng while left <= right hoặc xử lý phần tử còn lại riêng |

**Ví dụ lặp vô hạn:** left = 4, right = 5 và mid = (4+5)/2 = 4. Nếu thuật toán dùng nhánh “đúng thì left = mid”, left vẫn bằng 4 và right vẫn bằng 5; những lần lặp sau lặp lại trạng thái cũ.

Nếu bài toán tìm **vị trí cuối cùng thỏa điều kiện** với quy tắc left = mid, cần chọn **trung điểm cao** (*upper midpoint*) để bảo đảm mid > left khi left < right:

\[
mid=\left\lceil \frac{left+right}{2}\right\rceil.
\]

Đừng viết máy móc **left + (right - left + 1) / 2** bằng int: hiệu right-left có thể bằng Integer.MAX_VALUE, và cộng 1 khiến biểu thức trong ngoặc tràn dù hiệu ban đầu an toàn. Với giả thiết \(0\le left\le right\le\mathrm{Integer.MAX\_VALUE}\), dùng:

~~~java
int gap = right - left;
int mid = left + gap / 2 + gap % 2; // Trung điểm cao an toàn
~~~

Vì gap không âm, phần dư gap % 2 chỉ là 0 hoặc 1; mid không vượt right. Đây là công thức cho biến thể thực sự cần giữ left = mid. Với lower bound thông thường, **trung điểm thấp + left = mid+1 hoặc right = mid** đã đảm bảo tiến triển và đơn giản hơn.

## 7. Java 17+: cài đặt an toàn, xử lý trùng và phần tử vắng mặt

Ví dụ đầy đủ dùng một mảng đã sắp xếp không giảm. Ta cài ba phép toán: tìm một vị trí bất kỳ, lowerBound và upperBound. Hai hàm đầu/cuối xuất hiện được xây dựng trên hai biên. Chương trình cũng in phép tính trung điểm sai và đúng để đối chiếu.

Lưu vào tệp **BinarySearchBoundaries.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class BinarySearchBoundaries {
    static int findAny(int[] a, int target) {
        Objects.requireNonNull(a, "array");
        int left = 0;
        int right = a.length - 1;

        while (left <= right) {
            int mid = left + (right - left) / 2;
            if (a[mid] == target) {
                return mid;
            }
            if (a[mid] < target) {
                left = mid + 1;
            } else {
                right = mid - 1;
            }
        }
        return -1;
    }

    static int lowerBound(int[] a, int target) {
        Objects.requireNonNull(a, "array");
        int left = 0;
        int right = a.length;

        while (left < right) {
            int mid = left + (right - left) / 2;
            if (a[mid] < target) {
                left = mid + 1;
            } else {
                right = mid;
            }
        }
        return left;
    }

    static int upperBound(int[] a, int target) {
        Objects.requireNonNull(a, "array");
        int left = 0;
        int right = a.length;

        while (left < right) {
            int mid = left + (right - left) / 2;
            if (a[mid] <= target) {
                left = mid + 1;
            } else {
                right = mid;
            }
        }
        return left;
    }

    static int firstIndex(int[] a, int target) {
        int i = lowerBound(a, target);
        return i < a.length && a[i] == target ? i : -1;
    }

    static int lastIndex(int[] a, int target) {
        int i = upperBound(a, target) - 1;
        return i >= 0 && a[i] == target ? i : -1;
    }

    public static void main(String[] args) {
        int[] a = {
            Integer.MIN_VALUE, -4, -4, 0,
            2, 2, 2, Integer.MAX_VALUE
        };

        System.out.println("Array: " + Arrays.toString(a));
        System.out.println("First 2: " + firstIndex(a, 2));
        System.out.println("Last 2: " + lastIndex(a, 2));
        System.out.println("Lower bound 1: " + lowerBound(a, 1));
        System.out.println("Upper bound -4: " + upperBound(a, -4));
        System.out.println("Find missing 3: " + findAny(a, 3));
        System.out.println("Lower bound MAX: "
            + lowerBound(a, Integer.MAX_VALUE));
        System.out.println("Lower bound empty: "
            + lowerBound(new int[0], 7));

        int left = 1_800_000_000;
        int right = 2_000_000_000;
        System.out.println("Unsafe midpoint: " + ((left + right) / 2));
        System.out.println("Safe midpoint: " + (left + (right - left) / 2));
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac BinarySearchBoundaries.java
java BinarySearchBoundaries
~~~

**Stdout chính xác:**

~~~text
Array: [-2147483648, -4, -4, 0, 2, 2, 2, 2147483647]
First 2: 4
Last 2: 6
Lower bound 1: 4
Upper bound -4: 3
Find missing 3: -1
Lower bound MAX: 7
Lower bound empty: 0
Unsafe midpoint: -247483648
Safe midpoint: 1900000000
~~~

Các kết quả cần giải thích:

- Giá trị 2 xuất hiện ở ba vị trí 4, 5, 6. **lowerBound(a,2) = 4** và **upperBound(a,2) = 7**, nên vị trí đầu là 4, vị trí cuối là \(7-1=6\).
- Giá trị 1 không xuất hiện, nhưng lowerBound(a,1) = 4 là điểm chèn đúng để mảng vẫn tăng không giảm.
- Các giá trị -4 ở chỉ số 1 và 2, nên upperBound(a,-4) = 3.
- Không có số 3; findAny trả -1. Không được nhầm giá trị trả về của lowerBound (vị trí chèn) với “đã tìm thấy”.
- Mảng rỗng có lower bound bằng 0 và không được truy cập phần tử nào.
- Phép tính trung điểm thông thường tràn int; phép tính từ khoảng cách cho kết quả 1.900.000.000 chính xác dù hai biên lớn.
- **Integer.MIN_VALUE** và **Integer.MAX_VALUE** trong mảng không ảnh hưởng đến thuật toán, vì mã dùng phép so sánh trực tiếp thay vì hiệu a[mid]-target.

Đầu vào của ba hàm tìm kiếm được giả định **đã sắp xếp không giảm**. Mã cố ý không sắp xếp hoặc kiểm tra lại mảng tại mỗi lời gọi, vì kiểm tra như vậy sẽ mất O(n) thời gian và thay đổi hợp đồng sử dụng tìm kiếm nhị phân.

## 8. Chứng minh kết thúc và độ phức tạp

Đặt độ dài đoạn chưa giải quyết là \(d\).

**Với lower bound nửa mở:**

- Ban đầu \(d=right-left=n\).
- Khi left < right thì \(d\ge1\).
- Trung điểm thấp thỏa \(left\le mid<right\).
- Nhánh left = mid+1 làm d mới bằng \(right-mid-1\), nhỏ hơn d.
- Nhánh right = mid làm d mới bằng \(mid-left\), cũng nhỏ hơn d.

Do d là số nguyên không âm và giảm nghiêm ngặt khi còn lặp, vòng lặp bắt buộc kết thúc. Sự thu hẹp xấp xỉ một nửa mỗi lần cho **O(log(n+1))** phép so sánh khi n >= 0. Bộ nhớ phụ là **O(1)** ngoài mảng đầu vào; không có ngăn xếp đệ quy.

**Với tìm đúng bằng khóa trên đoạn đóng:** mỗi vòng lặp hoặc trả kết quả, hoặc loại bỏ mid và giữ không quá khoảng một nửa số ứng viên. Nếu không tìm thấy, left vượt right; bộ nhớ phụ vẫn O(1), thời gian O(log(n+1)).

Khi nói “độ phức tạp O(log n)” trong tài liệu, thường ngầm giả định n >= 1; viết log(n+1) giúp bao gồm ca mảng rỗng mà không cần sử dụng log 0.

**Về tính đúng của lower bound:** bất biến rằng mọi vị trí bên trái left có giá trị < target và mọi vị trí từ right đến n-1 có giá trị >= target được duy trì sau mỗi phép cập nhật. Khi left = right, vị trí này phân chia chính xác hai miền, nên là chỉ số đầu tiên đạt >= target hoặc n nếu không tồn tại. Lập luận tương tự với dấu <= chứng minh upper bound.

## 9. Tìm kiếm nhị phân trên đáp án: vẫn phải giữ bất biến

Tìm kiếm nhị phân không chỉ áp dụng cho mảng. Giả sử có hàm **feasible(x)** kiểm tra một mức tài nguyên x có đáp ứng yêu cầu hay không, và tính khả thi là đơn điệu: nếu x khả thi thì mọi y >= x cũng khả thi.

Để tìm **giá trị nhỏ nhất khả thi** trong miền số nguyên không âm [low, high], nếu đã biết high là khả thi và đáp án nằm trong miền này:

~~~text
while low < high:
    mid = low + (high - low) / 2

    if feasible(mid):
        high = mid     // Mid có thể là đáp án
    else:
        low = mid + 1  // Mid chắc chắn không đạt

return low
~~~

Đây là cùng cấu trúc lower bound, nhưng giá trị được kiểm tra thông qua feasible(mid) thay vì đọc a[mid].

**Đặc tả không thể thiếu:** phải có ít nhất một đáp án khả thi trong khoảng (ví dụ high đã khả thi), và feasible phải đơn điệu theo chiều đã chọn. Nếu high không khả thi, thuật toán trên có thể trả một số **không khả thi**, dù mọi phép tính biên đều đúng. Nếu low âm và high dương lớn, cần sửa phép tính mid để không tràn hiệu như đã bàn ở phần 2.

Đối với bài toán **tìm giá trị lớn nhất còn khả thi** khi feasible tạo một miền true ở bên trái và false ở bên phải, chiều cập nhật đảo lại; thường cần **trung điểm cao** nếu giữ low = mid để bảo đảm không lặp vô hạn. Trước khi viết mã, nên xác định rõ loại biên cần tìm: *first true*, *last true*, *first >= target*, hay *last <= target*.

## 10. Bộ kiểm thử tập trung vào biên

Các ca thử sau nên được áp dụng cho lowerBound, upperBound, firstIndex và lastIndex; khi cần, so sánh với một phép quét tuyến tính đơn giản để xác nhận.

| Mảng | Khóa | lowerBound | upperBound | Vị trí đầu | Vị trí cuối |
|---|---:|---:|---:|---:|---:|
| [] | 5 | 0 | 0 | -1 | -1 |
| [3] | 3 | 0 | 1 | 0 | 0 |
| [3] | 2 | 0 | 0 | -1 | -1 |
| [3] | 4 | 1 | 1 | -1 | -1 |
| [2,2,2] | 2 | 0 | 3 | 0 | 2 |
| [1,3,5] | 0 | 0 | 0 | -1 | -1 |
| [1,3,5] | 4 | 2 | 2 | -1 | -1 |
| [1,3,5] | 9 | 3 | 3 | -1 | -1 |
| [-5,-1,0,8] | -1 | 1 | 2 | 1 | 1 |
| [MIN,0,MAX] | MAX | 2 | 3 | 2 | 2 |

Trong hàng cuối, **MIN = Integer.MIN_VALUE** và **MAX = Integer.MAX_VALUE**. Với mảng cực lớn, có thể không dễ cấp phát trong môi trường kiểm thử; vẫn nên kiểm tra riêng phép tính mid bằng cặp biên lớn như ví dụ Java để bắt lỗi tràn chỉ số.

Ngoài các ca cụ thể, có thể kiểm tra ba thuộc tính với một mảng đã sắp xếp bất kỳ:

1. **0 <= lowerBound <= upperBound <= n.**
2. Với \(p=lowerBound(a,x)\), mọi i < p đều có a[i] < x, còn mọi i >= p đều có a[i] >= x.
3. Với \(q=upperBound(a,x)\), mọi i < q đều có a[i] <= x, còn mọi i >= q đều có a[i] > x.

Các thuộc tính này phát hiện nhiều lỗi lệch một đơn vị ngay cả khi chỉ số trả về trông có vẻ hợp lý.

## 11. Các lỗi thường gặp và cách phòng tránh

- **Dùng (left+right)/2 cho hai biên int lớn:** thay bằng left+(right-left)/2 khi bảo đảm 0 <= left <= right; nếu miền có cả số âm lớn, tính khoảng cách trên long.
- **Nâng kiểu quá muộn:** biểu thức (long)(right-left) vẫn đã tràn int trước khi ép kiểu. Phải viết (long)right - (long)left.
- **Nhầm quy ước đoạn đóng và nửa mở:** cặp khởi tạo, điều kiện lặp, cập nhật biên phải thống nhất với nhau.
- **Không loại bỏ mid trong nhánh đã chứng minh mid sai:** có thể làm khoảng không thu hẹp và lặp vô hạn.
- **Loại bỏ mid khi mid có thể là đáp án biên:** ví dụ dùng right=mid-1 cho lower bound ở nhánh a[mid]>=target làm mất phần tử đạt ngưỡng đầu tiên.
- **Quên kiểm tra chỉ số n:** lowerBound có thể hợp lệ khi trả n, nhưng a[n] luôn là truy cập ngoài phạm vi.
- **Không xử lý trùng lặp:** phép tìm bằng thông thường không bảo đảm first/last; dùng lowerBound/upperBound để xác định hai biên.
- **Tính trung điểm cao bằng right-left+1 trên int:** phép +1 có thể tràn; tính gap trước và cộng phần dư gap%2 để làm tròn lên.
- **So sánh bằng phép trừ a[mid]-target:** phép trừ int cũng có thể tràn; so sánh trực tiếp.
- **Bỏ kiểm tra điều kiện đơn điệu của predicate:** nếu true/false xen kẽ, thuật toán loại nửa miền không có cơ sở.
- **Chỉ thử mảng lớn ngẫu nhiên:** lỗi off-by-one lộ rõ hơn trên n=0, n=1, hai phần tử, toàn giá trị bằng nhau và khóa nằm ngoài miền giá trị.
- **Tính đúng vòng lặp nhưng sai hợp đồng:** lower bound là vị trí chèn, không có nghĩa khóa đã tồn tại; phải kiểm tra bằng điều kiện biên và so sánh bằng.

## 12. Bài tập tự kiểm tra

**Bài 1.** Với left = 1.800.000.000 và right = 2.000.000.000, công thức trung điểm nào đúng trong Java int? Tại sao?

**Đáp án:** left + (right-left)/2 = 1.900.000.000. Hiệu right-left = 200.000.000 nằm trong int, còn tổng left+right vượt Integer.MAX_VALUE nên bị tràn trước khi chia.

**Bài 2.** Với mảng [1,2,2,2,4] và khóa 2, hãy tìm lowerBound và upperBound.

**Đáp án:** lowerBound = 1; upperBound = 4; ba vị trí bằng 2 là 1,2,3. Khoảng chứa các phần tử bằng khóa là **[lowerBound,upperBound)**.

**Bài 3.** Trong lower bound nửa mở, khi a[mid] >= target, vì sao phải đặt right = mid thay vì mid-1?

**Đáp án:** mid có thể chính là phần tử **đầu tiên** đạt >= target. Loại mid sẽ có nguy cơ làm mất đáp án; dùng right=mid giữ ứng viên và vẫn làm khoảng nhỏ đi.

**Bài 4.** Một vòng lặp dùng while left < right, mid là trung điểm thấp, và ở một nhánh chỉ cập nhật left = mid. Điều gì xảy ra nếu right = left+1 và nhánh đó được chọn?

**Đáp án:** mid = left, hai biên không đổi, vòng lặp có thể chạy mãi. Cần cập nhật left=mid+1 khi mid đã bị loại, hoặc chọn trung điểm cao nếu biến thể thật sự phải giữ left=mid và bất biến cho phép.

**Bài 5.** Lower bound có thể trả n không? Có được đọc a[n] để xác nhận khóa không?

**Đáp án:** Có thể trả n khi không phần tử nào >= target; đó là vị trí chèn sau phần tử cuối. Không được đọc a[n] vì chỉ số hợp lệ của mảng là 0..n-1.

**Ghi nhớ:** An toàn của tìm kiếm nhị phân không nằm ở một công thức mid riêng lẻ mà ở **cả bộ ba: miền giá trị không tràn, bất biến khoảng, và cập nhật biên bảo đảm tiến triển**. Đặc tả rõ ràng loại đáp án cần tìm (bằng khóa, lower bound, upper bound, first/last) giúp loại bỏ phần lớn lỗi lệch một đơn vị ngay từ thiết kế.