# Tìm kiếm theo vị từ đơn điệu

## 1. Bài toán: tìm ranh giới của một điều kiện đúng/sai

Tìm kiếm nhị phân thường được giới thiệu là tìm một giá trị trong mảng đã sắp xếp. Cách nhìn tổng quát hơn là **tìm vị trí ranh giới nơi một điều kiện Boolean (vị từ) chuyển từ sai sang đúng**, hoặc từ đúng sang sai, trên một miền có thứ tự. Điều kiện dùng để trả lời câu hỏi “ứng viên này có thỏa yêu cầu hay không?” được gọi là **vị từ P(x)**.

Ví dụ với dãy đã sắp xếp a = [1, 3, 3, 5, 8], vị từ “a[i] ≥ 4” tạo ra chuỗi kết quả theo chỉ số i:

~~~text
i:           0      1      2      3      4
a[i]:        1      3      3      5      8
P(i):       false  false  false   true   true
                                 ^
                         vi tri true dau tien = 3
~~~

Ta không cần biết giá trị cụ thể tại mọi vị trí, mà cần tận dụng việc **một khi P trở thành true thì mọi vị trí về sau cũng true**. Đây là tính đơn điệu cho phép bỏ đi một nửa miền tìm kiếm sau mỗi lần đánh giá vị từ.

Tư duy này còn áp dụng cho bài toán tối ưu: tìm sức chứa tối thiểu của tàu để vận chuyển hàng trong D ngày, tìm thời gian nhỏ nhất để hoàn thành đủ sản phẩm, tìm ngưỡng nhỏ nhất đáp ứng điều kiện, hoặc tìm giá trị lớn nhất còn khả thi. Ta không nhất thiết có một mảng kết quả Boolean; có thể **tính P(x) khi cần** bằng một hàm kiểm tra.

## 2. Định nghĩa đơn điệu và miền tìm kiếm

Giả sử miền ứng viên hữu hạn có thứ tự x0 < x1 < ... < x(n-1). Một vị từ có dạng **false rồi true** là đơn điệu không giảm nếu:

- Với mọi i < j, nếu P(xi) là true thì P(xj) cũng true.
- Tương đương, nếu P(xj) là false thì mọi i < j đều false.
- Chuỗi kết quả chỉ có thể có dạng F...F T...T, bao gồm cả trường hợp toàn F hoặc toàn T.

Khi đó ta thường tìm **ứng viên đầu tiên thỏa P**, còn gọi là first true hoặc lower boundary.

Một dạng khác là **true rồi false**, đơn điệu không tăng: T...T F...F. Khi ấy thường tìm **ứng viên cuối cùng còn thỏa P** (last true), hoặc đổi sang vị từ phủ định !P để tìm first true. Hai dạng có hướng khác nhau; không được tùy tiện dùng một điều kiện cập nhật cận cho cả hai.

| Chuỗi P(x) theo thứ tự tăng của x | Có đơn điệu theo một hướng? | Câu hỏi phù hợp |
| --- | --- | --- |
| F F F T T T | Có, false → true | First true |
| T T T F F | Có, true → false | Last true |
| F F F F | Có, false → true (không có true) | Trả dấu hiệu không tồn tại |
| T T T T | Có, false → true (mọi vị trí true) | First true là vị trí đầu |
| F T F T | Không | Không áp dụng tìm ranh giới nhị phân trực tiếp |
| T F T | Không | Không áp dụng tìm ranh giới nhị phân trực tiếp |

**Điều kiện quan trọng:** miền ứng viên phải có thứ tự và vị từ phải có tính đơn điệu **trên chính miền ấy**. Không phải mọi hàm có thể trả true/false đều đơn điệu. Ví dụ “x là số nguyên tố” không đổi một chiều khi x tăng; tìm kiếm nhị phân trực tiếp trên vị từ này không hợp lệ.

Cần nêu rõ miền để tránh kết luận sai. Vị từ P(x) = (x² ≥ 50) là đơn điệu false → true trên **số nguyên không âm**, nhưng không có dạng ấy trên toàn bộ số nguyên âm và dương. Với mảng, vị từ a[i] ≥ target chỉ đơn điệu theo i nếu a đã sắp xếp không giảm.

## 3. Mẫu chuẩn firstTrue trên chỉ số [0, n)

Hãy dùng khoảng **nửa mở [lo, hi)** cho các chỉ số chưa phân loại. Ban đầu lo = 0, hi = n; **n là vị trí canh gác (sentinel) bên ngoài mảng**, biểu thị “không tồn tại phần tử true”. Hàm tuyệt đối không đọc a[n].

Giả mã:

~~~text
firstTrue(n, P):
    lo = 0
    hi = n
    while lo < hi:
        mid = lo + (hi - lo) / 2  // chia nguyen lay phan nguyen
        if P(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo
~~~

Ý nghĩa hai nhánh:

- Nếu P(mid) là **true**, mid có thể là đáp án; tất cả vị trí lớn hơn mid không cần xét nữa vì không thể là true đầu tiên. Giữ mid bằng cách gán hi = mid.
- Nếu P(mid) là **false**, do tính đơn điệu mọi chỉ số ≤ mid cũng false, nên bỏ chúng bằng lo = mid + 1.
- Khi lo = hi, toàn bộ vùng chưa biết đã bị loại, ranh giới là lo.

Hàm trả về một chỉ số trong [0,n]. Nếu bằng n, **không có phần tử thỏa P**; người gọi phải tự xử lý trường hợp này trước khi truy cập mảng.

### Bất biến và chứng minh tính đúng

Có thể diễn đạt bất biến vòng lặp:

1. Với mọi chỉ số i < lo, P(i) = false.
2. Với mọi chỉ số i ≥ hi nhưng i < n, P(i) = true.
3. Nếu tồn tại first true trong [0,n), vị trí đó nằm trong [lo,hi]; nếu không tồn tại, ranh giới canh gác là n.

Ban đầu lo=0, hi=n nên (1) và (2) đúng hiển nhiên do các tập chỉ số tương ứng rỗng. Mỗi phép kiểm tra P(mid) cùng giả thiết đơn điệu cho phép bỏ đúng một nửa đang xét và vẫn bảo toàn bất biến. Vì mid nằm trong [lo,hi) khi lo<hi, sau mỗi bước độ dài hi-lo **giảm nghiêm ngặt**; thuật toán dừng. Tại lo=hi, không còn chỉ số chưa phân loại, nên đó là ranh giới cần tìm.

Mỗi vòng lặp đánh giá P đúng một lần và giảm gần một nửa khoảng tìm kiếm: **O(log(n+1)) lần đánh giá vị từ**, bộ nhớ phụ O(1). Nếu một lần P cần T_P thời gian, tổng chi phí là O(T_P × log(n+1)), không thể mặc định O(log n) thời gian khi bản thân P tốn O(n).

### Mô phỏng cụ thể

Cho a = [1,3,3,5,8] và P(i) = (a[i] ≥ 4):

| Bước | lo trước | hi trước | mid | P(mid) | Cập nhật |
| --- | ---: | ---: | ---: | --- | --- |
| 1 | 0 | 5 | 2 | false (3 < 4) | lo = 3 |
| 2 | 3 | 5 | 4 | true (8 ≥ 4) | hi = 4 |
| 3 | 3 | 4 | 3 | true (5 ≥ 4) | hi = 3 |

Kết thúc lo=hi=3, đúng vị trí đầu tiên có a[i] ≥ 4. Nếu mọi phần tử đều nhỏ hơn 4, hàm trả về n; nếu tất cả đều thỏa, hàm trả 0.

## 4. Lower bound, upper bound và các trường hợp trùng lặp

Trên mảng a đã sắp xếp **không giảm**:

- **Lower bound của target:** chỉ số đầu tiên i mà a[i] ≥ target. Vị từ P(i) = (a[i] ≥ target).
- **Upper bound của target:** chỉ số đầu tiên i mà a[i] > target. Vị từ P(i) = (a[i] > target).
- **Số lần xuất hiện của target:** upperBound(target) - lowerBound(target).
- **Chỉ số xuất hiện cuối của target:** upperBound(target) - 1, nhưng chỉ hợp lệ khi target thực sự tồn tại; cần kiểm tra ở lowerBound hoặc kiểm tra phần tử tại chỉ số tương ứng.
- **Kiểm tra target tồn tại:** đặt i=lowerBound(target), sau đó kiểm tra i<n và a[i]==target.

Với a=[1,3,3,5,8], lowerBound(3)=1 và upperBound(3)=3; số lần xuất hiện của 3 là 2. LowerBound(10)=5=n, cho biết không có giá trị ≥10. LowerBound(1)=0. Với mảng rỗng, cả lowerBound và upperBound trả 0, nhưng không được đọc a[0].

Điểm khác biệt so với một hàm binary search chỉ cần tìm **bất kỳ** phần tử bằng target là lower/upper bound có ngữ nghĩa rõ ràng khi có phần tử trùng. Đây cũng là lý do dùng so sánh ≥ hoặc > theo yêu cầu, không cố định một nhánh so sánh cho mọi bài.

Nếu mảng không sắp xếp, chuỗi P(i) không nhất thiết đơn điệu: ví dụ a=[3,1,4] và P(i)=(a[i]≥3) tạo T,F,T. Tìm ranh giới nhị phân có thể bỏ nhầm đáp án. Hãy sắp xếp dữ liệu nếu được phép, giữ chỉ số gốc nếu cần, hoặc chọn thuật toán khác.

## 5. Dạng ngược: tìm last true

Nếu P(x) có dạng T...T F...F, hãy định nghĩa Q(x)=!P(x), khi đó Q có dạng F...F T...T. Tìm firstTrue của Q, rồi trừ 1 để lấy **last true** của P.

Với miền chỉ số 0..n-1:

~~~text
firstFalse = firstTrue(n, i -> !P(i))
lastTrue = firstFalse - 1
~~~

Giá trị lastTrue = -1 nghĩa là không có vị trí true. Nếu mọi vị trí đều true, firstFalse=n và lastTrue=n-1. Với n=0, kết quả lastTrue=-1 cũng có ý nghĩa “không tồn tại”.

Ví dụ trong mảng tăng dần, vị từ P(i)=(a[i] ≤ target) là true rồi false. Last true của P là vị trí cuối cùng có giá trị ≤ target. Cách biến đổi thông qua phủ định hạn chế việc phải nhớ một mẫu cập nhật lo/hi riêng, nhưng chỉ hợp lệ nếu thật sự chứng minh được hướng đơn điệu.

## 6. Tìm kiếm trên đáp án (binary search on answer)

Không phải bài toán nào cũng có sẵn mảng chỉ số. Trong nhiều bài tối ưu, ta có một **ứng viên đáp án số nguyên x** và một hàm kiểm tra khả thi P(x):

- “Có thể hoàn thành nhiệm vụ trong **không quá x đơn vị thời gian** không?” Nếu có thể với x, thì với thời gian lớn hơn cũng có thể. P có dạng F...T, cần tìm x nhỏ nhất.
- “Có thể đạt **ít nhất x điểm** trong giới hạn nguồn lực không?” Nếu đạt x điểm, mọi ngưỡng điểm thấp hơn cũng đạt. P có dạng T...F, cần tìm x lớn nhất.
- “Có thể phân chia công việc sao cho **tải lớn nhất không vượt quá x** không?” Tăng x chỉ nới lỏng ràng buộc, nên P có dạng F...T.

Quy trình cốt lõi:

1. Xác định biến đáp án x, miền ứng viên nguyên [L,R], và câu hỏi khả thi P(x).
2. **Chứng minh đơn điệu** dựa trên ràng buộc của bài toán, không dựa vào quan sát vài ví dụ.
3. Tìm hai cận hợp lệ. Với bài tối thiểu hóa dạng false → true, nên biết trước một cận trên R khả thi; L là cận dưới toán học của mọi đáp án.
4. Viết hàm P(x) chính xác, bao gồm tình huống biên và dữ liệu không hợp lệ.
5. Dùng tìm kiếm nhị phân thu hẹp cận; kiểm tra kết quả thỏa P và, nếu có ứng viên ngay trước, ứng viên đó không thỏa.

**Không suy luận đơn điệu chỉ vì đáp án cần tối ưu.** Ví dụ điều kiện “tổng bằng chính xác x” chỉ đúng tại một hoặc vài giá trị x; nó không có dạng F...T trên một miền tổng quát. Khi đó tìm ranh giới nhị phân trực tiếp là sai.

## 7. Ví dụ: sức chứa tối thiểu để giao hàng trong D ngày

Cho n kiện hàng có trọng lượng dương w[0..n-1], phải giao **theo đúng thứ tự ban đầu**, không tách kiện, trong **không quá D ngày**; mỗi ngày tổng trọng lượng không vượt quá sức chứa C. Mục tiêu: tìm **C nhỏ nhất** cho phép giao hết.

Ví dụ:

~~~text
weights = [3, 2, 2, 4, 1, 4]
days = 3

C = 5: [3,2] | [2] | [4,1] | [4] => 4 ngay, khong du
C = 6: [3,2] | [2,4] | [1,4]     => 3 ngay, kha thi
dap an: 6
~~~

### Chọn miền đáp án

- **Cận dưới L = max(w):** mỗi kiện phải nằm nguyên vẹn trong một ngày, vì vậy C nhỏ hơn kiện nặng nhất chắc chắn không khả thi.
- **Cận trên R = sum(w):** có thể giao tất cả trong một ngày, nên chắc chắn khả thi với D≥1.
- Vậy đáp án thuộc [max(w), sum(w)] theo số nguyên, miễn là n>0, mọi trọng lượng dương, D≥1.

### Định nghĩa vị từ P(C)

P(C) = true nếu và chỉ nếu có thể phân chia dãy thành không quá D đoạn liên tiếp, mỗi đoạn có tổng trọng lượng ≤ C. Ta kiểm tra bằng chiến lược tham lam (greedy):

- Bắt đầu ngày thứ nhất với tải 0.
- Đọc kiện theo thứ tự. Nếu còn đủ chỗ thì thêm kiện vào ngày hiện tại.
- Nếu thêm sẽ vượt C, mở ngày mới và đưa kiện sang ngày ấy.
- Nếu số ngày cần > D thì false, ngược lại true.

Với C cố định, cách tham lam đặt nhiều kiện nhất có thể vào mỗi ngày giúp **giảm tối đa số ngày** cần thiết. Dịch ranh giới một ngày sớm hơn không thể giúp đặt được nhiều kiện hơn trên các ngày còn lại. Do vậy, nếu greedy cần quá D ngày thì không có cách phân chia theo thứ tự nào thỏa D ngày với C ấy.

**Chứng minh đơn điệu:** nếu một cách chia khả thi với C, cùng cách chia đó cũng khả thi với mọi C' ≥ C, vì tăng sức chứa không làm ngày nào bị vượt tải. Vì vậy P(C) có dạng false → true.

### Nhị phân trên cận nguyên đóng [L,R]

Khi R đã biết khả thi, có thể sử dụng:

~~~text
lo = max(weights)
hi = sum(weights)
while lo < hi:
    mid = lo + (hi - lo) / 2
    if feasible(mid):
        hi = mid       // mid co the la dap an
    else:
        lo = mid + 1   // mid qua nho
return lo
~~~

Bất biến ở đây là đáp án tối ưu luôn nằm trong [lo,hi] và hi khả thi. Nếu mid khả thi, có thể giảm cận trên tới mid; nếu mid không khả thi, mọi giá trị ≤mid cũng không khả thi, nên tăng cận dưới. Khoảng giảm nghiêm ngặt, và kết quả cuối vừa khả thi vừa nhỏ nhất.

Trong ví dụ: L=4, R=16. Các thử nghiệm theo thứ tự là C=10 (true), C=7 (true), C=5 (false), C=6 (true); thuật toán trả 6.

## 8. Java 17+: hai biến thể tìm kiếm nhị phân có thể chạy

Chương trình dưới đây minh họa cả **first true trên mảng chỉ số** và **tìm sức chứa tối thiểu trên đáp án số nguyên**. Tất cả lệnh in đều độc lập với thứ tự của Map hay ngữ cảnh vùng miền.

Lưu mã vào tệp **MonotonePredicateSearchDemo.java**:

~~~java
import java.util.Objects;
import java.util.function.IntPredicate;

public class MonotonePredicateSearchDemo {
    // Yeu cau: predicate tren chi so 0..length-1 co dang false...true.
    // Tra length neu khong co vi tri true nao.
    static int firstTrue(int length, IntPredicate predicate) {
        if (length < 0) {
            throw new IllegalArgumentException("length must be nonnegative");
        }
        Objects.requireNonNull(predicate, "predicate");

        int lo = 0;
        int hi = length; // Sentinel, khong goi predicate.test(length)
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (predicate.test(mid)) {
                hi = mid;
            } else {
                lo = mid + 1;
            }
        }
        return lo;
    }

    // Chi dung cho weights da kiem tra: day khong rong, moi weight > 0,
    // days >= 1. Day va thu tu cac kien duoc giu nguyen.
    private static boolean canShip(int[] weights, int days, long capacity) {
        int daysUsed = 1;
        long load = 0;

        for (int weight : weights) {
            if (weight > capacity) {
                return false;
            }
            if (load + weight > capacity) {
                daysUsed++;
                if (daysUsed > days) {
                    return false;
                }
                load = weight;
            } else {
                load += weight;
            }
        }
        return true;
    }

    static long minimumCapacity(int[] weights, int days) {
        if (weights == null || weights.length == 0) {
            throw new IllegalArgumentException("weights must not be empty");
        }
        if (days <= 0) {
            throw new IllegalArgumentException("days must be positive");
        }

        long lo = 0;
        long hi = 0;
        for (int weight : weights) {
            if (weight <= 0) {
                throw new IllegalArgumentException("weights must be positive");
            }
            lo = Math.max(lo, weight);
            hi += weight;
        }

        while (lo < hi) {
            long mid = lo + (hi - lo) / 2;
            if (canShip(weights, days, mid)) {
                hi = mid;
            } else {
                lo = mid + 1;
            }
        }
        return lo;
    }

    public static void main(String[] args) {
        int[] sorted = {1, 3, 3, 5, 8};

        System.out.println("first >= 3: " +
                firstTrue(sorted.length, i -> sorted[i] >= 3));
        System.out.println("first > 3: " +
                firstTrue(sorted.length, i -> sorted[i] > 3));
        System.out.println("first >= 10: " +
                firstTrue(sorted.length, i -> sorted[i] >= 10));
        System.out.println("last <= 3: " +
                (firstTrue(sorted.length, i -> sorted[i] > 3) - 1));
        System.out.println("all true: " + firstTrue(5, i -> true));
        System.out.println("all false: " + firstTrue(5, i -> false));
        System.out.println("empty: " + firstTrue(0, i -> true));

        int[] weights = {3, 2, 2, 4, 1, 4};
        System.out.println("capacity 5 feasible: " +
                canShip(weights, 3, 5));
        System.out.println("capacity 6 feasible: " +
                canShip(weights, 3, 6));
        System.out.println("minimum capacity: " +
                minimumCapacity(weights, 3));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên trong thư mục chứa tệp:

~~~bash
javac MonotonePredicateSearchDemo.java
java MonotonePredicateSearchDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
first >= 3: 1
first > 3: 3
first >= 10: 5
last <= 3: 2
all true: 0
all false: 5
empty: 0
capacity 5 feasible: false
capacity 6 feasible: true
minimum capacity: 6
~~~

### Giải thích thiết kế mã

- firstTrue chỉ kiểm tra các chỉ số từ 0 đến length-1; length là sentinel **không bao giờ được gọi vào predicate**. Với length=0, vòng lặp không chạy và kết quả là 0.
- Cả lower bound (≥) và upper bound (>) được biểu diễn bằng cùng một mẫu nhị phân. Không cần viết hai phiên bản thuật toán riêng. Chỉ khác định nghĩa vị từ.
- Sức chứa dùng long để chứa tổng trọng lượng; nếu weights là mảng int dương và có độ dài hợp lệ của Java, tổng lý thuyết nằm trong miền long. Sự chênh lệch hi-lo cũng an toàn trong các cận không âm này.
- canShip duyệt mỗi kiện O(n), mở ngày mới chỉ khi cần. Hàm chỉ được gọi sau khi minimumCapacity đã kiểm tra tính hợp lệ, trừ các lời gọi thử trong main cũng dùng đầu vào hợp lệ.
- minimumCapacity tính cận một lần O(n), sau đó kiểm tra P(C) trong O(n) cho mỗi vòng nhị phân; tổng O(n log(sum(weights)-max(weights)+1)) thời gian, bộ nhớ phụ O(1).
- Tìm kiếm không sửa weights hoặc sorted. Nếu cần xuất lịch chia kiện cụ thể, có thể chạy greedy thêm một lần sau khi đã tìm được sức chứa tối ưu.

## 9. Bài toán khác dùng vị từ đơn điệu

### Ngưỡng số học

Tìm số nguyên không âm nhỏ nhất x sao cho x² ≥ 50. Trên miền x≥0, P(x) là false rồi true; đáp án là 8 vì 7²=49<50 và 8²=64≥50. Khi cài đặt với số nguyên lớn, nhân x*x kiểu int có thể tràn, làm vị từ trả sai và phá tính đơn điệu thực tế của chương trình. Hãy chuyển sang long khi chắc chắn đủ miền hoặc so sánh bằng phép chia có kiểm soát.

### Thời gian tối thiểu để hoàn thành công việc

Giả sử nhiều máy làm việc đồng thời, máy j hoàn thành một sản phẩm mỗi t[j] đơn vị thời gian và cần ít nhất k sản phẩm. Đặt P(T): tổng số sản phẩm hoàn thành trước hoặc đúng thời điểm T ít nhất k. Vì tăng T không làm giảm số sản phẩm đã hoàn thành, P có dạng F...T. Tuy nhiên, khi tính Σ floor(T/t[j]), tổng có thể tràn; có thể dừng cộng ngay khi đạt k và chọn cận thời gian an toàn. Nếu không biết một cận trên khả thi, có thể mở rộng bằng **tăng cận theo cấp số nhân** (exponential search) cho đến khi gặp true rồi mới nhị phân, với kiểm tra tràn và miền cực đại.

### Tối đa hóa ngưỡng còn khả thi

Giả sử P(x) trả true nếu có thể đạt ít nhất x điểm với ngân sách cố định. Nếu khả thi ở x thì cũng khả thi ở mọi ngưỡng thấp hơn. P có dạng T...F; muốn tìm **x lớn nhất thỏa P**, có thể tìm firstFalse của P và lấy ứng viên ngay trước nó. Nếu dùng khoảng số nguyên đóng, một mẫu lastTrue riêng thường lấy **mid phía trên** để tránh vòng lặp vô hạn; bất kể chọn mẫu nào, phải chứng minh các cận và trường hợp không tồn tại.

## 10. Chọn biên, kiểu số và điều kiện dừng

**Miền chỉ số [0,n):** phương pháp firstTrue với sentinel n là tự nhiên vì trả đúng n nếu không có đáp án và không truy cập ngoài mảng. Hãy kiểm tra kết quả < n trước khi đọc a[index].

**Miền số nguyên đóng [L,R]:** khi tìm giá trị nhỏ nhất thỏa P và biết trước R khả thi, dùng while(lo<hi), mid lấy phần dưới, nhánh true giữ mid, nhánh false bỏ mid. Kết quả là một giá trị thật trong miền. Nếu **chưa có cận trên khả thi**, thuật toán có thể trả một giá trị không thỏa; phải xử lý trước trường hợp không có đáp án.

**Tránh tràn khi lấy midpoint:** thay vì (lo+hi)/2, dùng lo + (hi-lo)/2 khi hiệu không tràn. Trong ví dụ Java, chỉ số đều không âm và hi≤length, còn sức chứa nằm trong khoảng long không âm có tổng nhỏ hơn Long.MAX_VALUE, nên hiệu an toàn. Với miền long có cả số âm cực trị và dương cực trị, biểu thức hi-lo cũng có thể tràn; khi ấy cần tính midpoint và quản lý cận bằng kỹ thuật an toàn riêng.

**Không trộn nhánh sai:** để tìm first true, nếu mid true cần giữ mid, không được lo=mid+1. Nếu mid false cần loại mid bằng lo=mid+1, không được lo=mid. Cập nhật sai dễ làm bỏ sót ranh giới hoặc lặp vô hạn, nhất là khi hi-lo=1.

**Giá trị liên tục:** khi x là số thực thay vì số nguyên, có thể dừng khi hi-lo≤epsilon hoặc sau số vòng hữu hạn, nhưng phải xét sai số double và hiện tượng midpoint làm tròn về một cận. Không được hứa độ chính xác tùy ý khi chạm giới hạn biểu diễn. Nếu đề bài hỏi đáp án nguyên, ưu tiên tìm trên miền nguyên để không phát sinh sai số làm tròn.

**Vị từ phải ổn định:** P(x) nên là hàm xác định, không thay đổi giữa các lần gọi. Nếu P dựa vào dữ liệu bị luồng khác sửa hoặc trạng thái ngẫu nhiên, giả định đơn điệu có thể mất hiệu lực ngay trong quá trình chạy. Nếu tính P là phép toán tốn kém, tổng số lần kiểm tra nhỏ vẫn có thể dẫn đến thời gian đáng kể.

## 11. Những lỗi thường gặp và cách nhận diện

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Không chứng minh tính đơn điệu | Nhị phân có thể loại sai nửa miền | Phát biểu P, chứng minh true kéo theo true về phía cần thiết |
| Nhầm false→true với true→false | Tìm sai ranh giới | Chọn first true, first false hoặc last true đúng hướng |
| Đọc a[n] khi không tìm thấy | Truy cập ngoài phạm vi | Xem n là sentinel, kiểm tra index<n |
| Chọn sai cận trên của tìm đáp án | Không có ứng viên khả thi dù bài có đáp án | Thiết lập cận bằng lập luận toán học hoặc mở rộng có kiểm soát |
| Giữ sai mid ở nhánh true/false | Bỏ đáp án hoặc lặp vô hạn | Dùng bất biến và bảo đảm khoảng giảm nghiêm ngặt |
| Mid tính bằng (lo+hi)/2 | Có thể tràn số | Dùng công thức không tràn trong miền đã chứng minh |
| Hàm feasible trả sai vì kiểu int | Phá đơn điệu hoặc kết quả sai | Dùng long và kiểm soát cộng/nhân |
| Vị từ kiểm tra bằng thuật toán sai | Nhị phân đúng vẫn cho đáp án sai | Chứng minh riêng tính đúng của hàm kiểm tra |
| Coi O(log n) là tổng thời gian | Đánh giá thấp chi phí P(x) | Nhân số lần kiểm tra với chi phí mỗi lần |
| Bỏ qua dữ liệu rỗng/toàn true/toàn false | Trả chỉ số vô nghĩa | Công bố sentinel, hợp đồng đầu vào, kiểm thử biên |

**Điểm cần nhớ:** tìm kiếm nhị phân là một kỹ thuật thu hẹp miền ứng viên. Nó chỉ đúng khi **các đánh giá vị từ cùng quan hệ thứ tự đủ để kết luận cả một nửa miền không chứa đáp án**. Công thức tính mid không thay thế được phần lập luận đơn điệu.

## 12. Kiểm thử theo thuộc tính và bài tự luyện

Thay vì chỉ kiểm tra một đầu vào, hãy kiểm tra các điều kiện sau cho firstTrue trả i:

1. 0≤i≤n.
2. Mọi chỉ số j<i có P(j)=false.
3. Nếu i<n thì P(i)=true.
4. Nếu i=n thì mọi j<n đều false.
5. Với mọi dãy Boolean dạng F...T (bao gồm n=0), kết quả bằng số lượng giá trị false ở đầu dãy.

Với minimumCapacity trả C cho đầu vào hợp lệ:

1. C≥max(weights) và C≤sum(weights).
2. canShip(weights,D,C)=true.
3. Nếu C>max(weights), canShip(weights,D,C-1)=false.
4. Nếu D tăng, sức chứa tối thiểu **không thể tăng**; nếu tăng một trọng lượng, sức chứa tối thiểu **không thể giảm** khi các điều kiện khác giữ nguyên.
5. Dãy weights không bị thay đổi sau khi chạy.

Bài tập:

1. Với a=[1,2,2,2,6,9], tìm lowerBound(2), upperBound(2), số lần xuất hiện của 2 và first index≥7. Tự chứng minh vị từ của mỗi truy vấn là đơn điệu.
2. Cho chuỗi P theo chỉ số [F,F,F,T,T]. Tự điền bảng lo, hi, mid sau từng vòng; nếu toàn F hoặc toàn T, kết quả thay đổi thế nào?
3. Tìm số nguyên nhỏ nhất x≥0 thỏa x²≥1000, tránh tràn khi kiểm tra P(x) trên miền số nguyên lớn.
4. Với weights=[5,1,2,4,3] và D=3, tự đặt cận và kiểm tra greedy theo từng C cho đến khi tìm sức chứa nhỏ nhất. Giải thích vì sao đảo thứ tự kiện hàng có thể làm thay đổi đáp án.
5. Viết hàm lastTrue(length,P) cho P có dạng T...F bằng cách gọi firstTrue trên !P, rồi kiểm thử đầu vào n=0, toàn T, toàn F.
6. Tìm **thời gian tối thiểu** để các máy có chu kỳ [2,3,7] tạo ra ít nhất 10 sản phẩm. Định nghĩa P(T), tìm cận trên khả thi và tránh tràn khi cộng các số lượng sản phẩm.

**Tự kiểm tra cuối cùng:** khi đứng trước một bài toán mới, hãy trả lời lần lượt “Miền ứng viên là gì?”, “P(x) được kiểm tra thế nào?”, “Vì sao P đơn điệu?”, “Tìm first true hay last true?”, “Có trường hợp không có đáp án không?”, rồi mới viết vòng lặp. Đó là cách sử dụng tìm kiếm nhị phân như một công cụ suy luận về **ranh giới của vị từ đơn điệu**, thay vì ghi nhớ máy móc điều kiện so sánh.
