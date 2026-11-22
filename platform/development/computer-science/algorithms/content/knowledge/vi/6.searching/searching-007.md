# Tìm vị trí chèn và xử lý phần tử trùng

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **tìm một phần tử**, **tìm vị trí chèn**, **tìm vị trí xuất hiện đầu tiên/cuối cùng** và **đếm số phần tử trùng** trong một dãy đã sắp xếp.
2. Hiểu chính xác hai hàm biên **lower bound** (vị trí đầu tiên có giá trị lớn hơn hoặc bằng khóa) và **upper bound** (vị trí đầu tiên có giá trị lớn hơn khóa).
3. Dùng đoạn nửa mở `[lower, upper)` để tìm toàn bộ nhóm phần tử bằng nhau mà không phải duyệt cả dãy.
4. Chọn rõ chính sách **chèn trước** hay **chèn sau** những phần tử có khóa bằng nhau; giữ đúng thứ tự và dữ liệu.
5. Cài đặt Java 17+ với chỉ số an toàn, giải thích bất biến, tính dừng, độ phức tạp và kiểm thử trường hợp biên.

## 1. Vì sao “tìm vị trí” có thể có nhiều đáp án?

Xét mảng số nguyên **đã sắp xếp không giảm**:

```text
Giá trị:  1   2   2   2   4   7
Chỉ số:   0   1   2   3   4   5
```

Với khóa cần tìm `x = 2`, có ba chỉ số chứa cùng giá trị: `1`, `2` và `3`.

- “**Có phần tử bằng 2 hay không?**” chỉ yêu cầu một giá trị Boolean.
- “**Tìm một vị trí chứa 2**” cho phép trả `1`, `2` hoặc `3` nếu đặc tả không yêu cầu chọn vị trí cụ thể.
- “**Vị trí đầu tiên của 2**” bắt buộc là `1`.
- “**Vị trí cuối cùng của 2**” bắt buộc là `3`.
- “**Số lần xuất hiện của 2**” bằng `3`.
- “**Chèn 2 vào đâu để mảng vẫn được sắp xếp?**” có nhiều vị trí hợp lệ: từ `1` đến `4`, tùy chính sách xử lý phần tử trùng.

Tìm kiếm nhị phân thông thường có thể tìm ra **một** chỉ số bằng khóa, nhưng nếu có phần tử trùng thì chỉ số đó không nhất thiết là lần xuất hiện đầu tiên hay cuối cùng. Muốn một kết quả xác định để kiểm thử và tích hợp API, ta phải đặc tả rõ vị trí biên cần tìm.

Trong bài này, chỉ số bắt đầu từ **0**, dãy sắp xếp **tăng dần có thể trùng** (nondecreasing), và mọi khoảng chỉ số `[L, R)` có nghĩa: **bao gồm L, không bao gồm R**.

## 2. Hai vị trí biên cơ bản

Cho mảng `a` có độ dài `n` đã sắp xếp sao cho:

\[
a[0]\le a[1]\le\cdots\le a[n-1].
\]

Với một khóa `x`, định nghĩa:

**Lower bound — `lowerBound(a, x)`:**

\[
L=\min\{i\in[0,n)\mid a[i]\ge x\},
\]

và nếu không có chỉ số thỏa thì `L = n`. Nghĩa là **vị trí đầu tiên chứa phần tử lớn hơn hoặc bằng x**; cũng chính là vị trí đầu tiên có thể chèn `x` **trước những phần tử bằng x**.

**Upper bound — `upperBound(a, x)`:**

\[
U=\min\{i\in[0,n)\mid a[i]>x\},
\]

và nếu không có chỉ số thỏa thì `U = n`. Nghĩa là **vị trí đầu tiên chứa phần tử lớn hơn x**; cũng là vị trí đầu tiên có thể chèn `x` **sau tất cả phần tử bằng x**.

Hai hàm này **luôn trả về chỉ số từ `0` đến `n`**, kể cả khi không tìm thấy khóa. Giá trị `n` là vị trí chèn **sau phần tử cuối**, không phải một chỉ số có thể truy cập bằng `a[n]`.

Ví dụ mảng `a = [1, 2, 2, 2, 4, 7]`:

| Khóa `x` | `lowerBound` (L) | `upperBound` (U) | Nhóm bằng khóa `[L,U)` | Số lần xuất hiện |
| ---: | ---: | ---: | --- | ---: |
| 0 | 0 | 0 | Rỗng | 0 |
| 1 | 0 | 1 | `[0,1)` | 1 |
| 2 | 1 | 4 | `[1,4)` | 3 |
| 3 | 4 | 4 | Rỗng | 0 |
| 4 | 4 | 5 | `[4,5)` | 1 |
| 7 | 5 | 6 | `[5,6)` | 1 |
| 8 | 6 | 6 | Rỗng | 0 |

Với `x=2`, hình dung hai biên:

```text
          lowerBound=1         upperBound=4
               |                  |
Chỉ số    0    1    2    3    4    5
Giá trị   1    2    2    2    4    7
          <x   =x   =x   =x   >x   >x
               [ nhóm bằng x )
```

Với `x=3`, không có phần tử bằng 3, nhưng **cả hai biên đều là 4**; chèn 3 vào chỉ số 4 sẽ tạo dãy `[1,2,2,2,3,4,7]`.

### Những công thức suy ra từ hai biên

Đặt `L = lowerBound(a, x)` và `U = upperBound(a, x)`:

| Yêu cầu | Kết quả / điều kiện |
| --- | --- |
| Có phần tử bằng `x`? | `L < n && a[L] == x`; phải kiểm tra `L < n` trước khi đọc `a[L]` |
| Vị trí đầu tiên bằng `x` | `L`, nếu có; nếu không trả quy ước “không thấy”, ví dụ `-1` |
| Vị trí cuối cùng bằng `x` | `U - 1`, **chỉ khi `U > L`** |
| Số phần tử bằng `x` | `U - L` |
| Tất cả vị trí bằng `x` | Các chỉ số trong `[L, U)` |
| Vị trí đầu tiên có giá trị `>= x` | `L`, có thể bằng `n` nếu không tồn tại |
| Vị trí đầu tiên có giá trị `> x` | `U`, có thể bằng `n` nếu không tồn tại |
| Vị trí cuối cùng có giá trị `< x` | `L - 1`, nếu `L > 0` |
| Vị trí cuối cùng có giá trị `<= x` | `U - 1`, nếu `U > 0` |
| Vị trí chèn `x` trước những giá trị bằng nó | `L` |
| Vị trí chèn `x` sau những giá trị bằng nó | `U` |

Lưu ý: khi **không có khóa `x`**, `L=U` và tập `[L,U)` rỗng. Lúc ấy `U-1` có thể là vị trí của một phần tử **nhỏ hơn** `x`, nên không được dùng công thức “vị trí cuối cùng bằng khóa” nếu chưa kiểm tra `U>L`.

Đối với **mảng trống** `n=0`, cả hai hàm trả `0`; truy cập `a[0]` sẽ sai, nhưng chèn vào vị trí `0` hoàn toàn hợp lệ.

## 3. Tại sao tìm kiếm nhị phân dùng được?

Hai hàm biên dựa vào tính **đơn điệu** của một mệnh đề trên mảng đã sắp xếp.

Với lower bound, chia các vị trí thành hai miền:

```text
Vị trí có a[i] < x      | Vị trí có a[i] >= x
        false            |          true
-------------------------|---------------------
                  lowerBound
```

Vì mảng sắp xếp không giảm, khi đã gặp một giá trị `>=x` thì mọi phần tử ở bên phải cũng `>=x`. Ta cần tìm **ranh giới false → true**, hoặc `n` nếu không có true.

Với upper bound, chỉ thay mệnh đề:

```text
Vị trí có a[i] <= x     | Vị trí có a[i] > x
        false            |          true
-------------------------|---------------------
                  upperBound
```

Tìm kiếm nhị phân không cần truy cập từng phần tử: tại vị trí giữa `mid`, một phép so sánh đủ để loại bỏ khoảng bên trái hoặc bên phải. Nhưng điều đó chỉ đúng khi **miền false và miền true không xen kẽ**.

**Tiền điều kiện then chốt:** toàn bộ dãy phải sắp xếp theo **cùng một quy tắc so sánh với truy vấn**. Dãy `[2,1,2,4]` không thỏa tiền điều kiện tăng dần; code vẫn có thể chạy nhưng kết quả không được bảo đảm.

### Quy ước khoảng tìm kiếm nửa mở

Dùng `lo` và `hi` để biểu diễn khoảng còn chưa xác định `[lo, hi)`.

- Ban đầu `lo = 0`, `hi = n`.
- Trong vòng lặp, luôn bảo đảm `0 <= lo <= hi <= n`.
- Chọn `mid = lo + (hi - lo) / 2`. Công thức này tránh phép cộng trực tiếp `lo + hi` có thể tràn số nguyên trong thuật toán tổng quát.
- Với lower bound: nếu `a[mid] < x`, đặt `lo = mid + 1`; ngược lại đặt `hi = mid`.
- Với upper bound: nếu `a[mid] <= x`, đặt `lo = mid + 1`; ngược lại đặt `hi = mid`.
- Khi `lo == hi`, trả `lo`.

**Chỉ một khác biệt về điều kiện so sánh** (`<` so với `<=`) đã thay đổi ranh giới cần tìm. Đây là điểm dễ sai nhất khi xử lý phần tử trùng.

## 4. Giả mã cho lower bound và upper bound

### 4.1. Lower bound — phần tử đầu tiên `>=x`

```text
LOWER_BOUND(a, x):
    yêu cầu: a đã sắp xếp không giảm
    lo <- 0
    hi <- length(a)

    while lo < hi:
        mid <- lo + (hi - lo) / 2   // chia nguyên
        if a[mid] < x:
            lo <- mid + 1
        else:
            hi <- mid

    return lo
```

### 4.2. Upper bound — phần tử đầu tiên `>x`

```text
UPPER_BOUND(a, x):
    yêu cầu: a đã sắp xếp không giảm
    lo <- 0
    hi <- length(a)

    while lo < hi:
        mid <- lo + (hi - lo) / 2
        if a[mid] <= x:
            lo <- mid + 1
        else:
            hi <- mid

    return lo
```

Hai hàm đều có **độ phức tạp thời gian `O(log(n+1))`**, dùng **`O(1)` bộ nhớ phụ** đối với mảng hỗ trợ truy cập chỉ số `O(1)`. Việc gọi cả hai để lấy đoạn `[L,U)` vẫn có thời gian `O(log(n+1))` vì chỉ thực hiện hai tìm kiếm nhị phân.

Nếu muốn **trả về đầy đủ `k` phần tử bằng khóa**, ngoài hai lần tìm kiếm còn phải duyệt hoặc sao chép `k=U-L` phần tử; thời gian khi đó là `O(log(n+1)+k)` (chưa tính các chi phí xử lý riêng khác).

## 5. Từng bước chạy: khóa có phần tử trùng

Với `a=[1,2,2,2,4,7]`, `x=2`, ta có `n=6`.

**Lower bound:**

| Lượt | `lo` | `hi` | `mid` | `a[mid]` | Quyết định |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 0 | 6 | 3 | 2 | `2>=2`, đặt `hi=3` |
| 2 | 0 | 3 | 1 | 2 | `2>=2`, đặt `hi=1` |
| 3 | 0 | 1 | 0 | 1 | `1<2`, đặt `lo=1` |

Kết thúc tại `lo=hi=1`. Vị trí đầu tiên có giá trị `>=2` là **1**.

**Upper bound:**

| Lượt | `lo` | `hi` | `mid` | `a[mid]` | Quyết định |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 0 | 6 | 3 | 2 | `2<=2`, đặt `lo=4` |
| 2 | 4 | 6 | 5 | 7 | `7>2`, đặt `hi=5` |
| 3 | 4 | 5 | 4 | 4 | `4>2`, đặt `hi=4` |

Kết thúc tại `lo=hi=4`. Vị trí đầu tiên có giá trị `>2` là **4**.

Vậy các phần tử bằng 2 chiếm đoạn nửa mở **`[1,4)`**, gồm chỉ số 1, 2, 3; số phần tử bằng 2 là `4-1=3`.

## 6. Chứng minh tính đúng và tính dừng

Một thuật toán tìm biên phải giải thích tại sao **không bỏ qua đáp án**.

### Bất biến lower bound

Trong suốt vòng lặp, duy trì:

1. Các vị trí `i < lo` đều có `a[i] < x`.
2. Các vị trí `i >= hi` đều có `a[i] >= x`.
3. Ranh giới đang tìm nằm trong khoảng `[lo, hi]`; `lo` và `hi` có thể bằng `n`.

Ban đầu `lo=0` và `hi=n`, hai miền đã phân loại rỗng nên bất biến đúng.

Nếu `a[mid] < x`, do mảng không giảm, **mọi vị trí `i <= mid`** đều có giá trị `< x`. Vì vậy cập nhật `lo=mid+1` không thể loại mất vị trí đầu tiên `>=x`.

Nếu `a[mid] >= x`, do mảng không giảm, **mọi vị trí `i >= mid`** đều có giá trị `>=x`. Vì vậy cập nhật `hi=mid` vẫn giữ ranh giới cần tìm trong miền chưa quyết định.

Đến khi `lo=hi`, mọi phần tử **trước lo** đều nhỏ hơn `x` và mọi phần tử **từ lo trở đi** đều lớn hơn hoặc bằng `x`. Vậy `lo` chính là lower bound.

### Bất biến upper bound

Thay hai miền đã phân loại thành:

1. Các vị trí `i < lo` đều có `a[i] <= x`.
2. Các vị trí `i >= hi` đều có `a[i] > x`.

Nếu `a[mid] <= x` thì mọi phần tử trước `mid` cũng `<=x`, nên có thể đặt `lo=mid+1`. Nếu `a[mid]>x` thì mọi phần tử sau `mid` cũng `>x`, nên đặt `hi=mid`. Khi hai đầu gặp nhau, ta nhận được vị trí đầu tiên `>x`.

### Vì sao vòng lặp luôn dừng?

Mỗi lần lặp có `lo<hi` và `mid` nằm trong `[lo,hi)`. Sau cập nhật:

- `lo=mid+1` làm `lo` tăng ít nhất 1, hoặc
- `hi=mid` làm `hi` giảm ít nhất 1.

Do đó độ rộng `hi-lo` giảm nghiêm ngặt, luôn không âm và ban đầu bằng `n`. Vòng lặp phải dừng sau hữu hạn bước. Mỗi bước loại bỏ khoảng một nửa miền chưa quyết định, nên số bước là logarithmic theo `n`.

Các chứng minh trên áp dụng cả khi `x` nhỏ hơn mọi phần tử (kết quả 0), lớn hơn mọi phần tử (kết quả `n`), khi tất cả phần tử giống nhau và khi mảng rỗng.

## 7. Vị trí chèn: trước hay sau nhóm phần tử bằng nhau?

Để **giữ mảng tăng dần**, bất cứ vị trí `p` nào thỏa `L <= p <= U` đều có thể chèn `x` vào mà không phá thứ tự **theo giá trị**. Tuy nhiên, nếu có nhiều phần tử trùng, chọn vị trí nào sẽ ảnh hưởng đến thứ tự các bản ghi.

Hai chính sách xác định phổ biến:

| Chính sách | Vị trí chèn | Ý nghĩa |
| --- | ---: | --- |
| **Chèn trước nhóm bằng nhau** | `lowerBound(a,x)` | Phần tử mới xuất hiện trước tất cả phần tử có cùng khóa |
| **Chèn sau nhóm bằng nhau** | `upperBound(a,x)` | Phần tử mới xuất hiện sau tất cả phần tử có cùng khóa |

Trong ví dụ có ba số 2, chèn thêm 2 vào **chỉ số 1** hoặc **chỉ số 4** đều tạo ra cùng chuỗi giá trị `[1,2,2,2,2,4,7]`. Nhưng với bản ghi có danh tính khác nhau, hai lựa chọn khác về ý nghĩa.

Ví dụ dãy đã sắp xếp theo **điểm tăng dần**:

```text
(An, 70), (Binh, 80), (Chi, 80), (Dung, 90)
```

Thêm `(Em, 80)`:

- Dùng **lower bound theo điểm**: `An, Em, Binh, Chi, Dung`.
- Dùng **upper bound theo điểm**: `An, Binh, Chi, Em, Dung`.

Nếu muốn giữ **thứ tự đến trước–đến sau trong nhóm đồng điểm**, chính sách thường là **chèn sau nhóm bằng nhau** (upper bound). Khi đó các bản ghi cũ vẫn đứng trước bản ghi mới trong cùng nhóm khóa. Đây là một lựa chọn nghiệp vụ về thứ tự ổn định theo thời điểm chèn, **không phải** yêu cầu bắt buộc của mọi thao tác chèn có sắp xếp.

Nếu mỗi bản ghi còn có khóa phụ `id` và dãy đã sắp xếp theo `(score, id)`, thì biên phải được tìm **theo đúng bộ khóa đó**. Chỉ so sánh `score` trong khi giả định thứ tự theo `(score,id)` có thể đưa ra nhóm hòa khác với ý định.

### Chèn có giữ nguyên dữ liệu cũ không?

Có hai cách triển khai phổ biến:

- **Tạo mảng mới:** cấp phát độ dài `n+1`, sao chép tiền tố `[0,p)`, ghi `x` tại `p`, rồi sao chép hậu tố `[p,n)` dịch sang phải một vị trí. Mảng gốc giữ nguyên.
- **Chèn tại chỗ vào vùng có đủ capacity:** dịch các phần tử `p..n-1` sang phải từ cuối về đầu rồi ghi `x`. Phải có vị trí trống; mảng Java `int[]` có chiều dài cố định nên nếu đang dùng đủ `n` ô thì phải tạo mảng khác hoặc dùng cấu trúc động như `ArrayList`.

**Phân tích chi phí:** tìm `p` chỉ `O(log(n+1))` so sánh, nhưng thao tác sao chép/dịch phần tử có thể cần `Θ(n)` thời gian. Với cách tạo mảng mới, tốn `Θ(n)` bộ nhớ cho kết quả. Do đó **tìm vị trí chèn nhanh không có nghĩa là chèn vào mảng luôn nhanh**.

## 8. Java 17+: chương trình hoàn chỉnh

Tệp sau tên **`BoundsDemo.java`**, biên dịch được bằng JDK 17+ mà không cần thư viện ngoài. Giao diện yêu cầu mảng đã sắp xếp không giảm. Ví dụ dùng `Objects.requireNonNull` để chặn mảng `null`, còn kiểm tra thứ tự mảng được coi là **tiền điều kiện** của hàm thay vì quét kiểm tra trong mỗi truy vấn.

```java
import java.util.Arrays;
import java.util.Objects;

public class BoundsDemo {

    // First index i with a[i] >= x, or a.length.
    public static int lowerBound(int[] a, int x) {
        Objects.requireNonNull(a, "a");

        int lo = 0;
        int hi = a.length;

        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;

            if (a[mid] < x) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }

        return lo;
    }

    // First index i with a[i] > x, or a.length.
    public static int upperBound(int[] a, int x) {
        Objects.requireNonNull(a, "a");

        int lo = 0;
        int hi = a.length;

        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;

            if (a[mid] <= x) {
                lo = mid + 1;
            } else {
                hi = mid;
            }
        }

        return lo;
    }

    public static boolean contains(int[] a, int x) {
        int lower = lowerBound(a, x);
        return lower < a.length && a[lower] == x;
    }

    // Returns a NEW sorted array. The original input stays unchanged.
    public static int[] insertSorted(
            int[] a, int x, boolean afterEquals) {

        int position = afterEquals
                ? upperBound(a, x)
                : lowerBound(a, x);

        int[] result = new int[a.length + 1];

        System.arraycopy(a, 0, result, 0, position);
        result[position] = x;
        System.arraycopy(
                a, position,
                result, position + 1,
                a.length - position);

        return result;
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 2, 2, 4, 7};
        System.out.println("Original: " + Arrays.toString(a));

        int[] queries = {0, 2, 3, 7, 8};
        for (int x : queries) {
            int lower = lowerBound(a, x);
            int upper = upperBound(a, x);
            int count = upper - lower;

            System.out.printf(
                    "x=%d: lower=%d, upper=%d, count=%d, found=%b%n",
                    x, lower, upper, count, contains(a, x));
        }

        System.out.println(
                "Insert 2 before equals at " + lowerBound(a, 2)
                + ": " + Arrays.toString(
                        insertSorted(a, 2, false)));

        System.out.println(
                "Insert 2 after equals at " + upperBound(a, 2)
                + ": " + Arrays.toString(
                        insertSorted(a, 2, true)));

        System.out.println(
                "Insert 3 at " + lowerBound(a, 3)
                + ": " + Arrays.toString(
                        insertSorted(a, 3, false)));

        int[] empty = {};
        System.out.printf(
                "Empty: lower=%d, upper=%d%n",
                lowerBound(empty, 5),
                upperBound(empty, 5));
    }
}
```

Biên dịch và chạy từ thư mục chứa `BoundsDemo.java`:

```bash
javac BoundsDemo.java
java BoundsDemo
```

**Đầu ra chuẩn chính xác:**

```text
Original: [1, 2, 2, 2, 4, 7]
x=0: lower=0, upper=0, count=0, found=false
x=2: lower=1, upper=4, count=3, found=true
x=3: lower=4, upper=4, count=0, found=false
x=7: lower=5, upper=6, count=1, found=true
x=8: lower=6, upper=6, count=0, found=false
Insert 2 before equals at 1: [1, 2, 2, 2, 2, 4, 7]
Insert 2 after equals at 4: [1, 2, 2, 2, 2, 4, 7]
Insert 3 at 4: [1, 2, 2, 2, 3, 4, 7]
Empty: lower=0, upper=0
```

Lưu ý rằng hai dòng chèn giá trị 2 cho **cùng một mảng giá trị sau chèn**, bởi các giá trị trùng không mang danh tính. Dòng mô tả **vị trí** cho thấy khác biệt. Đối với bản ghi như `(id, score)`, vị trí đó quyết định bản ghi mới đứng trước hay sau những bản ghi đã tồn tại có cùng điểm.

### Vì sao code này tránh được lỗi phổ biến?

- `lo` khởi tạo 0 và `hi` khởi tạo bằng **`a.length`**, phù hợp khoảng nửa mở. Nhờ đó trả `n` khi phải chèn cuối dãy.
- `mid = lo + (hi - lo) / 2` không cộng trực tiếp hai đầu có thể lớn.
- `lowerBound` dùng `a[mid] < x`; `upperBound` dùng `a[mid] <= x`. Không trộn hai điều kiện.
- `contains` kiểm tra `lower < a.length` trước khi truy cập mảng, tránh lỗi ngoài biên khi khóa lớn hơn mọi phần tử.
- `insertSorted` sao chép đúng `position` phần tử tiền tố và `a.length-position` phần tử hậu tố; không làm mất phần tử trùng.
- Dùng `System.arraycopy` chỉ thay đổi vị trí lưu của giá trị, không đổi thứ tự tương đối giữa các phần tử cũ.
- Trường hợp mảng trống hoạt động tự nhiên: `lower=upper=0`, chèn vào vị trí 0 tạo mảng một phần tử.
- Mã không kiểm tra mảng có thực sự đã sắp xếp hay chưa; điều đó được yêu cầu ở hợp đồng đầu vào. Nếu cần API tự xác minh, phải thêm bước kiểm tra thứ tự `O(n)` hoặc thiết kế lớp luôn duy trì bất biến mảng đã sắp xếp.

## 9. Java Arrays.binarySearch và trường hợp phần tử trùng

Thư viện chuẩn cung cấp `Arrays.binarySearch(int[] a, int key)` cho mảng nguyên sắp xếp tăng dần.

- **Nếu có khóa:** trả một chỉ số chứa giá trị bằng khóa, **không bảo đảm là lần đầu hay lần cuối** trong nhóm trùng. Vì vậy không lấy trực tiếp kết quả dương để thay `lowerBound` hay `upperBound`.
- **Nếu không có khóa:** trả giá trị âm `-(insertionPoint) - 1`. Với khóa vắng mặt, điểm chèn là vị trí của phần tử đầu tiên lớn hơn khóa, hoặc `n` nếu không có; do khóa vắng mặt, lower và upper trùng nhau.
- Để khôi phục điểm chèn khi trả về âm: `insertionPoint = -result - 1`.

Ví dụ `[1,2,2,2,4,7]` tìm khóa 3: khóa không có, vị trí chèn là 4, nên `Arrays.binarySearch(a,3)` trả `-5`. Nhưng tìm khóa 2 có thể trả **một trong các chỉ số 1, 2, 3**; không nên viết test đòi chỉ số cố định.

`Collections.binarySearch` cũng chỉ bảo đảm tìm được một phần tử bằng khóa hoặc giá trị mã hóa điểm chèn, chứ không hứa tìm phần tử trùng đầu/cuối. Với danh sách truy cập ngẫu nhiên chậm, chi phí thực tế của tìm kiếm có thể khác với mảng; cần xét cấu trúc dữ liệu cụ thể.

Trong những API trả về “một kết quả trùng bất kỳ”, muốn ràng buộc **đầu tiên/ cuối cùng/ đếm** thì dùng hai hàm biên hoặc một thuật toán bảo đảm cùng hợp đồng.

## 10. Phần tử trùng theo khóa so sánh và bản ghi có nhiều trường

Với kiểu số nguyên, “bằng nhau” thường là giá trị `==`. Với đối tượng, điều kiện trùng phải nói rõ:

- **Trùng toàn bộ bản ghi**: các trường nội dung được chọn đều bằng nhau.
- **Trùng theo khóa tìm kiếm**: chẳng hạn hai hóa đơn cùng ngày, hai sinh viên cùng điểm, hai đơn hàng cùng mã khách.
- **Trùng theo Comparator**: comparator cho kết quả 0; quan hệ đó có thể **khác** với `equals` của đối tượng.

Ví dụ:

```text
(An, score=70)
(Binh, score=80)
(Chi, score=80)
(Dung, score=90)
```

Nếu dãy sắp theo **`score` tăng dần**, truy vấn `score=80` cho:

- `lowerBoundScore=1`.
- `upperBoundScore=3`.
- Nhóm bằng điểm gồm `Binh` và `Chi`, bất kể `id` khác nhau.

Nếu thay comparator thành bộ khóa `(score tăng dần, id tăng dần)`, hai bản ghi có cùng `score` nhưng khác `id` không còn “bằng nhau theo toàn bộ comparator”. Để lấy **tất cả bản ghi có cùng score**, không thể gọi hai bound bằng một đối tượng `(score=80,id=bất kỳ)` rồi cho rằng đoạn đó đúng nhóm điểm; phải tìm theo **mệnh đề trên trường score** hoặc dùng cặp khóa biên phù hợp.

Với chuỗi, phép so sánh cũng cần đồng nhất: phân biệt hoa/thường, chuẩn hóa Unicode và quy tắc locale có thể khiến các giá trị “trông giống nhau” được xếp khác nhau. Với số thực, cần xử lý riêng `NaN` và quy tắc so sánh nhất quán, ví dụ dùng `Double.compare` nếu phù hợp hợp đồng; không tự cho rằng các phép `<`, `<=` trên `double` có thể tạo một thứ tự toàn phần khi có `NaN`.

**Nguyên tắc:** sort, tìm kiếm và chèn phải dùng **cùng một quan hệ thứ tự**. Nếu quan hệ thay đổi, các giả định về vị trí biên sẽ không còn đúng.

## 11. Khi nào nên dùng hai bound, khi nào cần công cụ khác?

| Nhiệm vụ | Cách giải | Thời gian với mảng sắp xếp |
| --- | --- | --- |
| Kiểm tra `x` có tồn tại | `lowerBound` và kiểm tra phần tử tại `L` | `O(log(n+1))` |
| Tìm bản ghi đầu tiên có khóa `>=x` | `lowerBound` | `O(log(n+1))` |
| Tìm bản ghi đầu tiên có khóa `>x` | `upperBound` | `O(log(n+1))` |
| Đếm số phần tử bằng `x` | `upperBound - lowerBound` | `O(log(n+1))` |
| Trả đủ `k` phần tử bằng `x` | Tìm hai bound, rồi duyệt `[L,U)` | `O(log(n+1)+k)` |
| Chèn vào mảng đã sắp xếp | Tìm vị trí `O(log(n+1))`, sau đó dịch/sao chép | Tổng `O(n)` trong trường hợp chung |
| Tìm khóa trong mảng **chưa** sắp xếp | Duyệt tuyến tính, hoặc sắp xếp trước nếu có nhiều truy vấn | Duyệt một lần `O(n)`; sắp xếp có chi phí chuẩn bị riêng |

Nếu chỉ truy vấn một lần trên dãy chưa sắp xếp, sắp xếp toàn bộ `O(n log n)` để rồi tìm nhị phân có thể tốn hơn duyệt tuyến tính `O(n)`. Khi có rất nhiều truy vấn trên cùng dữ liệu, chi phí sắp xếp ban đầu có thể được bù lại.

Nếu ứng dụng có nhiều lượt **chèn** và **xóa** xen kẽ, duy trì một mảng sắp xếp có thể tốn nhiều lần dịch chuyển. Có thể cần cấu trúc cây cân bằng hoặc chỉ mục chuyên dụng; lựa chọn phải xét yêu cầu truy vấn **vị trí/rank**, vì nhiều cấu trúc tìm khóa nhanh nhưng **không tự hỗ trợ** tìm thứ hạng theo chỉ số.

### Mảng giảm dần

Hai định nghĩa ở trên giả định **tăng dần không giảm**. Với dãy giảm dần, không thể giữ nguyên điều kiện `<`/`<=` rồi kỳ vọng kết quả đúng. Ví dụ nếu muốn tìm vị trí đầu tiên có `a[i] <= x` trong dãy không tăng, cần tìm ranh giới của mệnh đề khác và đổi phép so sánh tương ứng. Hãy phát biểu rõ loại thứ tự trước khi viết code.

## 12. Kiểm thử biên và thuộc tính

Nên kiểm thử cả các mảng đặc biệt, không chỉ một trường hợp điển hình.

| Mảng | Khóa | Lower | Upper | Số lần trùng | Ghi chú |
| --- | ---: | ---: | ---: | ---: | --- |
| `[]` | 5 | 0 | 0 | 0 | Mảng rỗng |
| `[2]` | 2 | 0 | 1 | 1 | Một phần tử bằng khóa |
| `[2]` | 1 | 0 | 0 | 0 | Chèn trước |
| `[2]` | 3 | 1 | 1 | 0 | Chèn sau |
| `[2,2,2]` | 2 | 0 | 3 | 3 | Mọi phần tử trùng |
| `[2,2,2]` | 1 | 0 | 0 | 0 | Nhỏ hơn tất cả |
| `[2,2,2]` | 3 | 3 | 3 | 0 | Lớn hơn tất cả |
| `[-5,-2,-2,0,8]` | -2 | 1 | 3 | 2 | Có số âm và phần tử trùng |
| `[1,2,2,2,4,7]` | 3 | 4 | 4 | 0 | Khóa thiếu giữa dãy |

Ngoài bảng ví dụ, có thể dùng **kiểm thử thuộc tính** trên nhiều mảng sắp xếp được tạo ra:

1. Kết quả luôn thỏa `0 <= lower <= upper <= n`.
2. Với mọi `i < lower`: `a[i] < x`; với mọi `i >= lower`: `a[i] >= x`.
3. Với mọi `i < upper`: `a[i] <= x`; với mọi `i >= upper`: `a[i] > x`.
4. Tất cả phần tử trong `[lower,upper)` bằng `x`; số phần tử trùng phải bằng `upper-lower`.
5. Mảng sau `insertSorted` có độ dài `n+1`, vẫn sắp xếp không giảm, chứa đủ từng lần xuất hiện của các giá trị cũ cộng một `x`; mảng nguồn không thay đổi.
6. Trường hợp khóa không có phải cho `lower==upper`. Trường hợp có khóa phải cho `lower<upper`.

Một cách kiểm thử đối chiếu trên mảng nhỏ là **duyệt tuyến tính** để tìm phần tử đầu tiên `>=x` và đầu tiên `>x`, rồi so với hàm tìm nhị phân. Cách tuyến tính chậm hơn trên mảng lớn nhưng rất hữu ích làm **oracle** độc lập trong test.

### Các lỗi thường gặp

- Dùng điều kiện `a[mid] == x` rồi trả ngay, khiến kết quả là **một** vị trí trùng bất kỳ chứ không phải lần đầu/cuối.
- Dùng `a[mid] < x` cho cả hai bound nên `upper` bị sai khi có nhiều giá trị bằng `x`.
- Trộn khoảng `[lo,hi)` với khoảng đóng `[lo,hi]`, gây off-by-one hoặc truy cập `a[n]`.
- Gán `hi=mid-1` theo thói quen của một phiên bản tìm kiếm nhị phân khác, dù bất biến đang yêu cầu giữ `mid` làm ứng viên.
- Quên rằng kết quả bằng `n` là **vị trí chèn hợp lệ** nhưng **không phải vị trí phần tử hợp lệ**.
- Tính vị trí cuối bằng `upper-1` khi khóa **không có**, rồi nhận nhầm một phần tử nhỏ hơn khóa.
- Tìm đúng biên nhưng chèn tại chỗ bằng cách dịch từ **trái sang phải**, có thể ghi đè dữ liệu chưa được sao chép; khi dịch phải tại chỗ phải đi từ cuối về đầu.
- Dùng so sánh bằng phép trừ như `a[mid]-x` có thể tràn `int` nếu hai số gần các cực trị; nên dùng phép so sánh quan hệ hoặc `Integer.compare`.
- Tìm nhị phân trên dữ liệu chưa sắp xếp hoặc dùng comparator khác với comparator đã sắp xếp.
- Nhầm tốc độ tìm vị trí `O(log n)` với tốc độ chèn mảng `O(n)`.

## 13. Bài tập tự kiểm tra

**Bài 1.** Cho `a=[1,2,2,2,4,7]`. Với các khóa `0,2,3,8`, hãy viết lower, upper, số lần xuất hiện và vị trí chèn trước/sau nhóm bằng nhau.

**Bài 2.** Cho `a=[-3,-3,-1,0,0,5]`. Tìm khoảng nửa mở chứa toàn bộ giá trị `0`, số lần xuất hiện và vị trí cuối cùng bằng `0`.

**Bài 3.** Một hàm “tìm kiếm nhị phân” trả vị trí 2 khi tìm `2` trong mảng `[1,2,2,2,4,7]`. Kết quả này có sai không nếu yêu cầu là “một vị trí bất kỳ”? Có đúng không nếu yêu cầu “vị trí đầu tiên”?

**Bài 4.** Xét danh sách bản ghi `[(A,70),(B,80),(C,80),(D,90)]` đã sắp xếp theo điểm. Hãy xác định vị trí chèn `(E,80)` để (a) E đứng trước mọi bản ghi 80 điểm, (b) E đứng sau mọi bản ghi 80 điểm.

**Bài 5.** Vì sao cả lower và upper đều có thể bằng `n`? Khi đó phép `a[lower] == x` có hợp lệ không?

**Bài 6.** Nếu có `k` phần tử trùng, vì sao trả **toàn bộ** k phần tử không thể chỉ tốn `O(log n)` thời gian trong mô hình phải liệt kê từng kết quả?

**Bài 7.** Hãy viết bất biến cho lower bound khi dùng khoảng nửa mở. Tại sao nhánh `a[mid] >= x` phải đặt `hi=mid` thay vì `hi=mid-1`?

### Đáp án gợi ý

1. Với `0`: `L=U=0`, trùng 0, chèn 0. Với `2`: `L=1`, `U=4`, trùng 3, chèn trước ở 1 hoặc sau ở 4. Với `3`: `L=U=4`, trùng 0, chèn 4. Với `8`: `L=U=6`, trùng 0, chèn 6.
2. `L=3`, `U=5`, khoảng `[3,5)`, có 2 số 0; vị trí cuối bằng 0 là `4`.
3. Không sai nếu chấp nhận bất kỳ vị trí bằng 2; sai nếu yêu cầu lần đầu, vì chỉ số đầu tiên là `1`.
4. Chèn trước tại chỉ số `1`; chèn sau tại chỉ số `3`.
5. Khi không có phần tử thỏa tiêu chí `>=x` hoặc `>x`, hàm trả `n`. Không được đọc `a[n]`; phải kiểm tra `lower<n` trước.
6. Việc xuất từng phần tử có chi phí ít nhất `\Omega(k)`, nên giới hạn tự nhiên là `O(log(n+1)+k)`.
7. Các chỉ số nhỏ hơn `lo` đều `<x`, các chỉ số từ `hi` trở đi đều `>=x`; khi `a[mid]>=x`, chính `mid` còn có thể là lower bound nên phải giữ nó trong miền ứng viên bằng `hi=mid`.

## Ghi nhớ

Với mảng **đã sắp xếp tăng dần**, **lower bound** là chỉ số đầu tiên có phần tử `>=x`, còn **upper bound** là chỉ số đầu tiên có phần tử `>x`. Hai biên tạo đoạn `[L,U)` chứa **đúng tất cả phần tử bằng khóa**; số lần xuất hiện bằng `U-L`. Muốn chèn trước phần tử trùng thì dùng `L`, chèn sau thì dùng `U`. Cả hai biên có thể bằng `n`, nên phải phân biệt **vị trí chèn** với **chỉ số truy cập hợp lệ**. Tìm biên bằng nhị phân tốn `O(log(n+1))`, nhưng chèn vào mảng thường vẫn tốn `O(n)` do phải dịch hoặc sao chép các phần tử.
