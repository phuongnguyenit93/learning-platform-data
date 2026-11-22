# Khoảng đóng, nửa mở và cách cập nhật hai biên

Trong các thuật toán **tìm kiếm nhị phân (binary search)**, ý tưởng “mỗi lần bỏ khoảng một nửa dữ liệu” chưa đủ để viết chương trình đúng. Ta còn phải quyết định **hai biên trái/phải đang biểu diễn tập ứng viên nào**, điều kiện vòng lặp là gì, phần tử giữa có được giữ lại hay loại bỏ, và kết quả được trả về sau khi hai biên gặp nhau.

Hai quy ước thường gặp là **khoảng đóng [left, right]** và **khoảng nửa mở [left, right)**. Cả hai đều đúng nếu được dùng nhất quán. Lỗi thường đến từ việc lấy cách khởi tạo của một quy ước nhưng dùng điều kiện dừng hoặc công thức cập nhật của quy ước còn lại.

Bài học tập trung vào việc viết, chứng minh và kiểm tra các phép cập nhật **left** và **right** trong bài toán tìm kiếm, đặc biệt là tìm một vị trí thỏa điều kiện đầu tiên hoặc cuối cùng.

## 1. Hai cách mô tả khoảng ứng viên

Giả sử a là mảng có n phần tử, được đánh chỉ số từ 0 đến n − 1.

| Quy ước | Tập chỉ số ứng viên | Độ dài | Rỗng khi | Toàn bộ mảng |
| --- | --- | --- | --- | --- |
| Đóng [l, r] | l, l+1, ..., r | r − l + 1 nếu l ≤ r | l > r | l = 0, r = n − 1 |
| Nửa mở [l, r) | l, l+1, ..., r−1 | r − l | l = r | l = 0, r = n |

**Khoảng đóng [l, r]** chứa cả hai đầu mút. Nếu chỉ còn một ứng viên thì l = r và vòng lặp vẫn phải có cơ hội xét phần tử đó. Muốn loại bỏ cả vị trí giữa ở phía phải, đặt r = mid − 1; muốn loại bỏ cả vị trí giữa ở phía trái, đặt l = mid + 1.

**Khoảng nửa mở [l, r)** chứa l nhưng **không chứa r**. Nếu chỉ còn một ứng viên thì r = l + 1. Khi muốn **giữ mid làm ứng viên** ở phần bên phải, đặt r = mid; khi chắc chắn mid không thể là đáp án và muốn bỏ cả phần bên trái tới mid, đặt l = mid + 1.

Ví dụ với n = 5:

~~~text
Chỉ số mảng:       0   1   2   3   4
Khoảng đóng:      [1, 3]  -> 1, 2, 3
Khoảng nửa mở:    [1, 4)  -> 1, 2, 3
Khoảng đóng rỗng: [2, 1]
Khoảng nửa mở rỗng: [2, 2)
~~~

Hai khoảng [1, 3] và [1, 4) mô tả **cùng một tập chỉ số**. Nhưng giá trị biên phải khác nhau. Khi thay đổi quy ước, mọi nơi dùng biên phải cũng phải được điều chỉnh: khởi tạo, điều kiện dừng, tính mid, cập nhật, ý nghĩa kết quả và kiểm thử.

**Quy tắc ưu tiên:** hãy ghi rõ tập ứng viên bằng ký hiệu khoảng ngay trước vòng lặp; từ đó mới suy ra câu lệnh cập nhật. Không nên thuộc lòng một mẫu if/else mà bỏ qua ý nghĩa của khoảng.

## 2. Trường hợp đơn giản: tìm một giá trị bằng x

Giả sử mảng a **đã sắp xếp không giảm**: a[i] ≤ a[i+1]. Mục tiêu là tìm **một vị trí bất kỳ** chứa x; nếu không có trả −1. Đây là **exact match**, khác bài toán tìm vị trí đầu tiên có giá trị ≥ x khi xuất hiện các phần tử trùng nhau.

### 2.1. Khoảng đóng [left, right]

Khởi tạo left = 0, right = n − 1. Khi left ≤ right thì khoảng vẫn có ít nhất một ứng viên.

~~~text
left = 0
right = n - 1

while left <= right:
    mid = left + (right - left) / 2
    if a[mid] == x:
        return mid
    else if a[mid] < x:
        left = mid + 1
    else:
        right = mid - 1

return -1
~~~

Khi a[mid] < x, vì mảng đã sắp xếp, mọi chỉ số ≤ mid đều chứa giá trị < x; có thể bỏ hẳn phần ấy. Khi a[mid] > x, mọi chỉ số ≥ mid đều chứa giá trị > x; có thể bỏ hẳn phần ấy. Vì mid **đã được kiểm tra không bằng x**, cả hai nhánh đều loại bỏ mid.

Với n = 0, right = −1, vòng lặp không chạy và kết quả là −1. Với một phần tử, left = right = 0 nên điều kiện **left ≤ right** vẫn cho phép kiểm tra phần tử duy nhất.

**Lưu ý:** nếu có nhiều phần tử bằng x, đoạn mã có thể trả bất kỳ chỉ số khớp nào được gặp trước. Nó không cam kết vị trí khớp đầu tiên.

### 2.2. Khoảng nửa mở [left, right)

Khởi tạo left = 0, right = n và lặp khi left < right.

~~~text
left = 0
right = n

while left < right:
    mid = left + (right - left) / 2
    if a[mid] == x:
        return mid
    else if a[mid] < x:
        left = mid + 1
    else:
        right = mid

return -1
~~~

Ở nhánh a[mid] > x, đặt right = mid, nên khoảng mới là [left, mid); **mid không còn thuộc tập ứng viên** dù không viết mid − 1. Đây là hệ quả của định nghĩa đầu phải không bao gồm. Vì mid < right trong mọi lần lặp, kích thước khoảng giảm. Khi a[mid] < x, bỏ mid và mọi vị trí bên trái bằng left = mid + 1.

Hai phiên bản tìm đúng cùng loại kết quả, nhưng phép cập nhật biên phải khác nhau. Với mảng chưa sắp xếp, kết luận “có thể loại cả nửa khoảng” không hợp lệ.

## 3. Tìm ranh giới quan trọng hơn tìm một phần tử

Trong nhiều bài, câu hỏi thực tế không phải “có x hay không?” mà là:

- **lower_bound(x):** vị trí đầu tiên có a[i] ≥ x.
- **upper_bound(x):** vị trí đầu tiên có a[i] > x.
- **last_less(x):** vị trí cuối cùng có a[i] < x.
- **last_less_or_equal(x):** vị trí cuối cùng có a[i] ≤ x.

Với mảng sắp xếp, các vị trí thỏa bất đẳng thức tạo thành **một đoạn liên tiếp**. Có thể tìm ranh giới giữa hai nhóm mà không cần duyệt toàn bộ.

Quy ước trả về:
- Nếu không có vị trí thỏa điều kiện **đầu tiên**, trả **n**, là vị trí chèn ngay sau phần tử cuối.
- Nếu không có vị trí thỏa điều kiện **cuối cùng**, trả **−1**, là vị trí giả ngay trước phần tử đầu.
- Cả −1 và n là **giá trị chỉ số biên logic**, không được dùng trực tiếp để truy cập a[−1] hoặc a[n].

Lấy a = [1, 2, 2, 2, 5] và x = 2:

~~~text
Chỉ số:           0   1   2   3   4
Giá trị:          1   2   2   2   5
a[i] < 2:        Đ   S   S   S   S
a[i] >= 2:       S   Đ   Đ   Đ   Đ
a[i] <= 2:       Đ   Đ   Đ   Đ   S
a[i] > 2:        S   S   S   S   Đ

lower_bound(2) = 1
upper_bound(2) = 4
Số lần xuất hiện của 2 = 4 - 1 = 3
Vị trí cuối có a[i] < 2 = 1 - 1 = 0
Vị trí cuối có a[i] <= 2 = 4 - 1 = 3
~~~

Điểm cốt lõi: các mệnh đề a[i] ≥ x và a[i] > x biến từ **sai sang đúng** một lần khi i tăng. Đó là điều kiện **đơn điệu** cho bài toán tìm vị trí đầu tiên thỏa predicate.

## 4. Lower bound bằng khoảng nửa mở

Đặc tả: với a đã sắp xếp không giảm, tìm chỉ số nhỏ nhất i sao cho a[i] ≥ x; không tồn tại thì trả n.

~~~text
left = 0
right = n

while left < right:
    mid = left + (right - left) / 2
    if a[mid] < x:
        left = mid + 1
    else:
        right = mid

return left
~~~

### Vì sao nhánh cập nhật không giống exact match?

- Nếu a[mid] < x, **mid chắc chắn không phải lời giải**. Mọi vị trí ≤ mid cũng không thể là lời giải, nên đặt left = mid + 1.
- Nếu a[mid] ≥ x, **mid có thể chính là lời giải đầu tiên**. Ta không được loại bỏ mid. Với khoảng [left, right), đặt right = mid giữ mid như biên phải chưa vượt qua: khoảng mới là [left, mid), thoạt nhìn không chứa mid, vậy tại sao lại đúng?

Điểm cần làm rõ: phiên bản lower bound ở trên dùng [left, right) như **khoảng chứa những vị trí còn cần kiểm tra**, còn right có thể đồng thời là **ứng viên trả lời nhỏ nhất đã biết**. Nếu a[mid] ≥ x, right = mid ghi nhận mid là một cận trả lời hợp lệ. Dù mid không còn nằm trong [left, right) để kiểm tra tiếp, nó vẫn còn được giữ trong **biến right**; thuật toán chỉ tìm xem có vị trí đúng nào nhỏ hơn mid hay không. Khi left = right, trả chỉ số cận này.

Một cách diễn đạt bất biến **chính xác và thuận tiện hơn**:
1. Mọi chỉ số i < left đều có a[i] < x.
2. Mọi chỉ số i thỏa right ≤ i < n đều có a[i] ≥ x.
3. 0 ≤ left ≤ right ≤ n.

Như vậy đoạn [left, right) chính là **vùng chưa phân loại** giữa hai miền đã biết. Khi kiểm tra mid:
- Nếu a[mid] < x, cả [left, mid] thuộc miền sai, dịch left tới mid + 1.
- Nếu a[mid] ≥ x, cả [mid, right) thuộc miền đúng, kéo right về mid.

Mỗi vòng lặp thu nhỏ khoảng chưa phân loại; bất biến vẫn đúng. Khi left = right, mọi vị trí trước left đều sai và mọi vị trí từ left tới cuối đều đúng, nên left chính là chỉ số đầu tiên thỏa điều kiện (hoặc n khi tất cả sai).

### Theo dõi từng bước

Với a = [1, 2, 2, 2, 5], x = 2:

| Bước | left | right | mid | a[mid] | Cập nhật |
| --- | ---: | ---: | ---: | ---: | --- |
| Ban đầu | 0 | 5 | – | – | Miền chưa phân loại [0, 5) |
| 1 | 0 | 5 | 2 | 2 | a[mid] ≥ 2 → right = 2 |
| 2 | 0 | 2 | 1 | 2 | a[mid] ≥ 2 → right = 1 |
| 3 | 0 | 1 | 0 | 1 | a[mid] < 2 → left = 1 |
| Kết thúc | 1 | 1 | – | – | Trả 1 |

Dãy có nhiều phần tử bằng 2, nhưng kết quả là **vị trí đầu tiên**, không phải chỉ số bất kỳ của giá trị 2.

## 5. Cùng bài toán bằng khoảng đóng

Vẫn tìm lower_bound, nhưng lần này dùng khoảng chưa phân loại **[left, right]** với right = n − 1.

~~~text
left = 0
right = n - 1

while left <= right:
    mid = left + (right - left) / 2
    if a[mid] < x:
        left = mid + 1
    else:
        right = mid - 1

return left
~~~

Vì tất cả vị trí ≥ mid đã được xác định là có giá trị ≥ x, nhánh thứ hai có thể bỏ qua việc kiểm tra lại mid và đặt right = mid − 1. Thông tin “các vị trí từ mid trở đi đều đúng” được giữ bằng bất biến:

1. Mọi chỉ số i < left đều có a[i] < x.
2. Mọi chỉ số i > right và i < n đều có a[i] ≥ x.
3. 0 ≤ left ≤ right + 1 ≤ n, ngoại trừ khi right = −1 thì right + 1 = 0 vẫn hợp lệ.

Khi vòng lặp kết thúc, left = right + 1; các vị trí trước left đều sai, còn các vị trí từ left trở đi đều đúng. Do đó **return left** chính xác. Không cần lưu biến answer riêng.

Theo cùng ví dụ:

| Bước | left | right | mid | a[mid] | Cập nhật |
| --- | ---: | ---: | ---: | ---: | --- |
| Ban đầu | 0 | 4 | – | – | [0, 4] |
| 1 | 0 | 4 | 2 | 2 | right = 1 |
| 2 | 0 | 1 | 0 | 1 | left = 1 |
| 3 | 1 | 1 | 1 | 2 | right = 0 |
| Kết thúc | 1 | 0 | – | – | Trả left = 1 |

**So sánh ngay tại nhánh đúng:**
- Nửa mở [left, right): **right = mid**.
- Đóng [left, right]: **right = mid − 1**.

Cả hai đều giữ đủ thông tin về đáp án. Nhưng nếu dùng **right = mid − 1** trong thuật toán nửa mở, có thể bỏ nhầm ứng viên đầu tiên; nếu dùng **right = mid** với điều kiện **left ≤ right** của khoảng đóng, có thể lặp vô hạn khi left = right = mid và điều kiện a[mid] ≥ x vẫn đúng.

## 6. Upper bound và các ranh giới khác

Để tìm vị trí đầu tiên có a[i] > x, chỉ cần thay điều kiện phân nhánh:

~~~text
left = 0
right = n

while left < right:
    mid = left + (right - left) / 2
    if a[mid] <= x:
        left = mid + 1
    else:
        right = mid

return left
~~~

Đó là **upper_bound**. So sánh hai hàm:

| Hàm | Điều kiện làm tăng left | Kết quả |
| --- | --- | --- |
| lower_bound(x) | a[mid] < x | Vị trí đầu tiên có a[i] ≥ x |
| upper_bound(x) | a[mid] ≤ x | Vị trí đầu tiên có a[i] > x |

Nếu mảng đã sắp xếp không giảm:
- Số phần tử **nhỏ hơn x** = lower_bound(x).
- Số phần tử **nhỏ hơn hoặc bằng x** = upper_bound(x).
- Số phần tử **bằng x** = upper_bound(x) − lower_bound(x).
- Vị trí cuối cùng có giá trị **nhỏ hơn x** = lower_bound(x) − 1.
- Vị trí cuối cùng có giá trị **≤ x** = upper_bound(x) − 1.
- x có xuất hiện hay không: lower_bound(x) < n **và** a[lower_bound(x)] == x, cần kiểm tra chỉ số hợp lệ trước khi truy cập.

Không cần tự tạo thêm vòng tìm kiếm phức tạp cho từng biến thể nếu có thể suy ra chúng từ hai ranh giới chuẩn.

### Khi nào dùng mid lệch phải?

Một biến thể khác duy trì đoạn đóng gồm những **ứng viên cuối cùng còn có thể đúng** và cập nhật left = mid khi mid vẫn là ứng viên. Nếu dùng mid = floor((left + right)/2) với left + 1 = right, ta có mid = left; câu lệnh left = mid **không làm biên di chuyển**, dẫn tới lặp vô hạn.

Để tìm **vị trí đúng cuối cùng** trong một dãy predicate dạng đúng → sai, một cách an toàn thường là tìm vị trí **sai đầu tiên**, rồi trừ 1. Nếu bắt buộc dùng khuôn **left = mid** để giữ mid, hãy chọn **mid nghiêng phải**:

~~~text
mid = left + (right - left + 1) / 2
~~~

và phải xác định bất biến lẫn điều kiện kết thúc tương ứng. Công thức này không thay thế được việc chứng minh: nó chỉ bảo đảm mid > left khi left < right, nhờ đó nhánh left = mid tiến lên. Với bài học cơ bản, suy ra ranh giới cuối từ lower_bound/upper_bound thường dễ hiểu và ít sai hơn.

## 7. Java 17: hai quy ước, hai ranh giới và kiểm thử đối chiếu

Chương trình dưới đây có:
- Lower bound bằng **khoảng nửa mở**.
- Lower bound bằng **khoảng đóng**.
- Upper bound bằng **khoảng nửa mở**.
- Tìm một vị trí bằng x bằng **khoảng đóng**.
- Lời giải tuyến tính làm **chuẩn đối chiếu** trên nhiều mảng nhỏ đã sắp xếp.

~~~java
import java.util.Arrays;

public class BinarySearchIntervalsDemo {
    static int lowerHalfOpen(int[] a, int x) {
        int left = 0;
        int right = a.length;
        while (left < right) {
            int mid = left + (right - left) / 2;
            if (a[mid] < x) {
                left = mid + 1;
            } else {
                right = mid;
            }
        }
        return left;
    }

    static int lowerClosed(int[] a, int x) {
        int left = 0;
        int right = a.length - 1;
        while (left <= right) {
            int mid = left + (right - left) / 2;
            if (a[mid] < x) {
                left = mid + 1;
            } else {
                right = mid - 1;
            }
        }
        return left;
    }

    static int upperHalfOpen(int[] a, int x) {
        int left = 0;
        int right = a.length;
        while (left < right) {
            int mid = left + (right - left) / 2;
            if (a[mid] <= x) {
                left = mid + 1;
            } else {
                right = mid;
            }
        }
        return left;
    }

    static int exactClosed(int[] a, int x) {
        int left = 0;
        int right = a.length - 1;
        while (left <= right) {
            int mid = left + (right - left) / 2;
            if (a[mid] == x) {
                return mid;
            }
            if (a[mid] < x) {
                left = mid + 1;
            } else {
                right = mid - 1;
            }
        }
        return -1;
    }

    static int linearLower(int[] a, int x) {
        for (int i = 0; i < a.length; i++) {
            if (a[i] >= x) {
                return i;
            }
        }
        return a.length;
    }

    static int linearUpper(int[] a, int x) {
        for (int i = 0; i < a.length; i++) {
            if (a[i] > x) {
                return i;
            }
        }
        return a.length;
    }

    static int checked = 0;

    static void verifyArray(int[] a) {
        for (int x = -2; x <= 2; x++) {
            int expectedLower = linearLower(a, x);
            int expectedUpper = linearUpper(a, x);
            if (lowerHalfOpen(a, x) != expectedLower
                    || lowerClosed(a, x) != expectedLower
                    || upperHalfOpen(a, x) != expectedUpper) {
                throw new AssertionError(
                    "a=" + Arrays.toString(a) + ", x=" + x
                );
            }
            checked++;
        }
    }

    // Sinh mọi mảng không giảm độ dài 0..4 trên {-1, 0, 1}.
    static void enumerateSorted(int[] a, int index, int minDigit) {
        if (index == a.length) {
            verifyArray(a);
            return;
        }
        for (int digit = minDigit; digit <= 2; digit++) {
            a[index] = digit - 1;
            enumerateSorted(a, index + 1, digit);
        }
    }

    static void show(int[] a, int x) {
        int lb = lowerHalfOpen(a, x);
        int ub = upperHalfOpen(a, x);
        if (lb != lowerClosed(a, x)) {
            throw new AssertionError("Different lower bounds");
        }
        System.out.println("x=" + x + " lower=" + lb
                + " upper=" + ub + " count=" + (ub - lb));
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 2, 2, 5};
        System.out.println("a=" + Arrays.toString(a));
        show(a, 0);
        show(a, 2);
        show(a, 3);
        show(a, 9);

        System.out.println("exact(5)=" + exactClosed(a, 5));
        System.out.println("exact(4)=" + exactClosed(a, 4));
        System.out.println("emptyLower="
                + lowerHalfOpen(new int[0], 2));

        for (int n = 0; n <= 4; n++) {
            enumerateSorted(new int[n], 0, 0);
        }
        System.out.println("checked=" + checked);
    }
}
~~~

Lưu vào **BinarySearchIntervalsDemo.java**, sau đó chạy:

~~~bash
javac BinarySearchIntervalsDemo.java
java BinarySearchIntervalsDemo
~~~

Kết quả chính xác:

~~~text
a=[1, 2, 2, 2, 5]
x=0 lower=0 upper=0 count=0
x=2 lower=1 upper=4 count=3
x=3 lower=4 upper=4 count=0
x=9 lower=5 upper=5 count=0
exact(5)=4
exact(4)=-1
emptyLower=0
checked=175
~~~

**Vì sao có 175 lần đối chiếu?** Với mỗi độ dài n từ 0 đến 4, số mảng không giảm trên ba giá trị −1, 0, 1 là C(n + 2, 2), lần lượt bằng 1, 3, 6, 10, 15. Tổng có 35 mảng. Mỗi mảng được thử với 5 truy vấn x từ −2 đến 2, nên **35 × 5 = 175** phép đối chiếu. Cả hai cách cài lower bound và cách cài upper bound được so với kết quả quét tuyến tính độc lập.

Kiểm thử vét cạn nhỏ này phát hiện nhiều lỗi biên nhưng chỉ bao phủ miền hữu hạn đã sinh. Bằng chứng cho mọi mảng hợp lệ vẫn phải dựa vào **bất biến**, việc thu hẹp khoảng sau mỗi vòng lặp và tính chất sắp xếp của đầu vào.

Trong ví dụ, phép thử exact(5) chỉ có một vị trí khớp nên trả 4; exact(4) không tồn tại nên trả −1. Đối với x = 2, đừng kỳ vọng exactClosed luôn trả 1: đó là bài toán **tìm một vị trí khớp**, khác với lower bound.

## 8. Trường hợp biên quyết định tính đúng đắn

Với mảng a đã sắp xếp không giảm:

| Đầu vào | lower_bound | upper_bound | Điều cần kiểm tra |
| --- | ---: | ---: | --- |
| a = [], x = 7 | 0 | 0 | Không truy cập a[0] khi rỗng |
| a = [5], x = 4 | 0 | 0 | Đầu vào có một phần tử lớn hơn x |
| a = [5], x = 5 | 0 | 1 | Phân biệt ≥ và > |
| a = [5], x = 6 | 1 | 1 | Trả n khi không có giá trị thỏa |
| a = [2, 2, 2], x = 2 | 0 | 3 | Toàn bộ phần tử trùng |
| a = [1, 3], x = 2 | 1 | 1 | Vị trí chèn dù không có x |
| a = [-4, -1, 3], x = -2 | 1 | 1 | Có số âm, vẫn sắp xếp đúng |
| a = [1, 2, 2, 2, 5], x = 2 | 1 | 4 | Nhiều giá trị bằng x |
| a = [1, 2, 2, 2, 5], x = 9 | 5 | 5 | Biên trả về bằng n |

Một số kiểm thử đặc biệt quan trọng:
- **Chỉ còn một ứng viên:** khoảng đóng có left = right; khoảng nửa mở có right = left + 1. Cần chắc chắn vòng lặp vẫn xử lý đúng trường hợp này.
- **Mảng rỗng:** khoảng đóng ban đầu [0, −1] rỗng; nửa mở [0, 0) rỗng.
- **Không có giá trị thỏa predicate:** lower_bound và upper_bound đều có thể trả n. Không được lấy a[n].
- **Tất cả giá trị thỏa predicate:** cận đầu là 0. Không được lấy a[−1] khi tính vị trí trước đó.
- **Giá trị trùng:** là bài thử tốt nhất để phân biệt điều kiện < và ≤.
- **Dữ liệu có cực trị int:** so sánh trực tiếp a[mid] với x không cần trừ hai giá trị, tránh tràn số do cách viết comparator bằng hiệu.

Nếu đề bài đảm bảo n ≥ 1, mảng rỗng không phải đầu vào hợp lệ trong **đặc tả ấy**, nhưng vẫn có thể dùng để kiểm tra tính phòng vệ của thư viện khi mong muốn hỗ trợ n = 0.

## 9. Lỗi cập nhật hai biên phổ biến

### 9.1. Dùng điều kiện của khoảng đóng cho khoảng nửa mở

Đoạn nửa mở khởi tạo right = n; nếu vẫn lặp với left ≤ right, lúc left = right = n có thể tính mid = n rồi truy cập a[n], vượt chỉ số. Với khoảng nửa mở hãy sử dụng **left < right** trong hai thuật toán ở trên.

### 9.2. Giữ mid ở nhánh không tiến triển

Giả sử đang tìm giá trị đúng đầu tiên trên [left, right) và viết right = mid − 1 khi điều kiện đúng. Khi phần tử ở mid chính là giá trị đúng đầu tiên, việc giảm thêm 1 có thể loại nhầm kết quả. Đúng phải là **right = mid**.

Ngược lại, với đoạn đóng [left, right] và while left ≤ right, nếu nhánh đúng đặt right = mid mà không có tình huống trả về, khi left = right = mid, right không đổi; vòng lặp không kết thúc.

### 9.3. Bỏ nhầm phần tử cuối do điều kiện dừng

Nếu dùng đoạn đóng nhưng lặp **while left < right**, lúc chỉ còn một ứng viên (left = right) vòng lặp dừng trước khi xử lý nó. Khi tìm exact match, điều này có thể trả “không tìm thấy” dù phần tử cuối đang xét bằng x.

### 9.4. Nhầm < và ≤

Với tìm lower bound, điều kiện chuyển left là **a[mid] < x**. Nếu đổi thành **a[mid] ≤ x**, thuật toán trở thành upper bound.

Phản ví dụ nhỏ nhất có thể là a = [2], x = 2:
- lower_bound đúng = 0;
- phiên bản dùng ≤ trả 1.

### 9.5. Tính mid gây tràn số

Viết:

~~~text
mid = (left + right) / 2
~~~

có thể tràn kiểu int khi left + right vượt Integer.MAX_VALUE. Khi 0 ≤ left ≤ right và hai biên là chỉ số hợp lệ theo miền đang xét, hãy ưu tiên:

~~~text
mid = left + (right - left) / 2
~~~

Trong binary search theo **miền giá trị** có thể bao gồm cả số âm, số dương cực lớn hoặc các đầu mút long, cần thiết kế phép tính mid không tràn ở mọi trung gian, hoặc dùng kiểu lớn hơn để tính. Công thức trên an toàn cho các biên chỉ số không âm theo ràng buộc đã nêu, không phải lời bảo đảm cho mọi cặp số nguyên bất kỳ.

### 9.6. Không chứng minh tính đơn điệu

Binary search tìm ranh giới đòi hỏi predicate có dạng sai → đúng hoặc đúng → sai theo thứ tự khảo sát. Ví dụ với mảng **chưa sắp xếp** [3, 1, 2] và điều kiện a[i] ≥ 2, dãy predicate đúng → sai → đúng, nên không có một ranh giới duy nhất để các quy tắc loại nửa khoảng hoạt động. Đây là dữ liệu vi phạm **tiền điều kiện mảng đã sắp xếp**, không phải phản ví dụ bác bỏ thuật toán trên miền đầu vào hợp lệ.

## 10. Quy trình suy ra nhánh cập nhật thay vì học thuộc

Có thể tự thiết kế một vòng binary search bằng các câu hỏi sau:

1. **Đáp án là gì?** Một phần tử bằng x, vị trí đúng đầu tiên, vị trí đúng cuối cùng, hay giá trị tối ưu?
2. **Tập ứng viên hiện tại là gì?** Viết rõ [left, right] hay [left, right), r có được bằng n không?
3. **Bất biến nào giữ được?** Các vị trí đã loại trái/phải phải được phân loại rõ và không thể chứa lời giải cần tìm.
4. **Sau khi kiểm tra mid, điều gì đã chắc chắn sai?** Nếu mid không thể là đáp án, mới được bỏ mid. Nếu mid có thể là đáp án, phải giữ thông tin về nó ở biên hoặc biến answer.
5. **Mỗi nhánh có làm khoảng hẹp lại không?** Đảm bảo điều kiện dừng được tiến gần hơn sau mỗi vòng.
6. **Kết thúc thì left và right có quan hệ gì?** Khoảng đóng rỗng khi left = right + 1; nửa mở rỗng khi left = right. Giá trị trả về phải có ý nghĩa theo hậu điều kiện, kể cả 0, −1 hoặc n.
7. **Thử các ca ranh giới nhỏ:** n = 0, n = 1, có trùng, không thỏa, tất cả thỏa, x ngoài hai đầu, và giá trị vừa bằng ngưỡng.

Một cách đặt giả thiết phổ quát cho tìm ranh giới:

~~~text
P(0), P(1), ..., P(n-1)
F, F, ..., F, T, T, ..., T
                 ^
             first true
~~~

Ta có thể dùng khuôn nửa mở:

~~~text
left = 0
right = n

while left < right:
    mid = left + (right - left) / 2
    if P(mid) == false:
        left = mid + 1
    else:
        right = mid

return left
~~~

Nếu **không có true**, trả n; nếu **toàn true**, trả 0. Đây là một khuôn áp dụng được cho nhiều bài “tìm chỉ số đầu tiên thỏa điều kiện”, không giới hạn tìm trong mảng. Tuy nhiên **P phải đơn điệu** và việc tính P(mid) phải đúng theo đặc tả.

### Tìm kiếm nhị phân trên đáp án

Đôi khi mid không phải chỉ số mảng mà là một **giá trị ứng viên** cho mục tiêu tối ưu. Ví dụ cần tìm dung lượng nhỏ nhất đủ để hoàn thành công việc; P(capacity) là “có thể hoàn thành với dung lượng này”, thường có dạng false → true. Ta cũng cần xác định miền ứng viên, quy ước khoảng, tính đơn điệu và cách cập nhật mid tương tự.

Nhưng cận số học có thể lớn và có overflow; với bài này cần kiểm soát kiểu số và các phép tính của hàm P, nhất là phép cộng/tích của nhiều đại lượng. Không được tùy tiện thay cận phải thành max + 1 nếu max là giá trị lớn nhất của kiểu dữ liệu.

## 11. Khi nào chọn khoảng đóng, khi nào chọn nửa mở?

Không có quy ước nào luôn nhanh hơn về độ phức tạp. Cả hai thu hẹp khoảng ứng viên khoảng một nửa trong mỗi bước, tốn **O(log(n + 1))** phép so sánh và O(1) bộ nhớ bổ sung cho phiên bản lặp.

Khoảng đóng [l, r] dễ nhìn đối với bài **tìm một phần tử bằng x**: left = 0, right = n − 1, while left ≤ right, loại mid bằng ±1 sau khi biết không trùng. Nó cũng phù hợp khi muốn mô tả một đoạn mà cả hai đầu đều là chỉ số hợp lệ (nếu đoạn chưa rỗng).

Khoảng nửa mở [l, r) thường tiện cho **tìm vị trí chèn/ranh giới**: left = 0, right = n, while left < right; trả left có thể bằng n. Cách này nhất quán với độ dài r − l và với nhiều API dùng phạm vi nửa mở.

Nhưng quyết định quan trọng hơn là **giữ nguyên quy ước trong toàn bộ vòng lặp**. Không chuyển từ lặp với left < right sang left ≤ right hoặc từ right = mid sang right = mid − 1 chỉ vì thấy một mẫu code trên mạng.

## 12. Bài tập và lời giải kiểm tra

**Bài 1.** Cho a = [1, 2, 2, 2, 5] và x = 2. Hãy xác định lower_bound, upper_bound, số lần xuất hiện của x và vị trí cuối cùng có giá trị < x.

*Đáp án:* lower_bound = 1, upper_bound = 4, số lần xuất hiện = 4 − 1 = 3, vị trí cuối có giá trị < 2 là 0.

**Bài 2.** Trong thuật toán lower bound nửa mở, vì sao khi a[mid] ≥ x phải đặt right = mid chứ không phải right = mid − 1?

*Đáp án:* mid có thể là ranh giới đầu tiên cần tìm. Biến right đại diện cận đã biết mọi phần tử từ đó trở đi thỏa điều kiện. Đặt right = mid ghi nhận đúng cận, đồng thời tiếp tục tìm ứng viên sớm hơn; trừ 1 có thể làm mất cận đúng.

**Bài 3.** Cho a = [4], x = 4. So sánh trạng thái kết thúc của hai biến thể lower bound.

*Đáp án:* Nửa mở khởi tạo [0, 1); kiểm tra mid = 0, đặt right = 0, kết thúc left = right = 0. Đóng khởi tạo [0, 0]; kiểm tra mid = 0, đặt right = −1, kết thúc left = 0, right = −1. Cả hai trả 0.

**Bài 4.** Cho a = [1, 3, 5], x = 4. Tại sao lower_bound là 2 dù a[2] không bằng 4?

*Đáp án:* Đây là vị trí đầu tiên chứa giá trị ≥ 4 (a[2] = 5), đồng thời là vị trí chèn 4 mà không phá thứ tự. Lower bound không đòi hỏi phần tử phải bằng x.

**Bài 5.** Một vòng lặp dùng left = 0, right = n − 1, while left ≤ right; khi điều kiện tại mid đúng thì right = mid. Hãy tìm dữ liệu nhỏ khiến vòng lặp không tiến triển.

*Đáp án:* Với a = [5] và x = 5 trong bài lower bound, left = right = mid = 0, a[mid] ≥ x, right vẫn 0; vòng lặp không thay đổi. Với khoảng đóng phải đặt right = mid − 1.

**Bài 6.** Hãy tự viết upper bound trên khoảng đóng và xác minh với a = [], [2], [2, 2] và a = [1, 2, 2, 3].

*Định hướng:* Khởi tạo left = 0, right = n − 1; khi a[mid] ≤ x thì left = mid + 1; ngược lại right = mid − 1; trả left. Điều kiện này tìm vị trí đầu tiên có a[i] > x.

## Ghi nhớ

- **Khoảng đóng [left, right]:** thường khởi tạo [0, n − 1], lặp với **left ≤ right**, loại mid ở phải bằng **right = mid − 1**.
- **Khoảng nửa mở [left, right):** thường khởi tạo [0, n), lặp với **left < right**, khi mid nằm phía đúng của ranh giới thì dùng **right = mid**.
- Khi điều kiện tại mid chắc chắn sai đối với ranh giới đầu tiên, đặt **left = mid + 1**.
- **Lower bound** dùng điều kiện **a[mid] < x** để dịch trái; **upper bound** dùng **a[mid] ≤ x**.
- Kiểm tra tính đơn điệu, bất biến, tiến triển và ca rỗng/một phần tử/trùng/không tìm thấy trước khi tin vào một công thức cập nhật hai biên.
- Giá trị trả về 0, −1 hoặc n có thể là **biên logic hợp lệ**; phải kiểm tra phạm vi trước khi truy cập mảng.