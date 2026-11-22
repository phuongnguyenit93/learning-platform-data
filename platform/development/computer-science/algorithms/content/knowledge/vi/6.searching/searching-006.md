# Cận dưới (lower bound) và cận trên (upper bound)

Khi tìm kiếm trong **dãy đã sắp xếp**, câu hỏi không phải lúc nào cũng là “giá trị `x` có tồn tại không?”. Ta thường cần biết **vị trí xuất hiện đầu tiên**, **vị trí ngay sau lần xuất hiện cuối**, **số phần tử bằng một giá trị**, hoặc **bao nhiêu phần tử nằm trong một khoảng**. Hai thao tác **lower bound** và **upper bound** là nền tảng giải các câu hỏi này bằng tìm kiếm nhị phân, kể cả khi dãy chứa nhiều giá trị trùng nhau.

Bài học tập trung vào **ý nghĩa vị trí**, **điều kiện đã sắp xếp**, **bất biến vòng lặp**, **chứng minh không lệch một đơn vị**, **cách áp dụng**, **độ phức tạp** và ví dụ Java 17+ chạy độc lập. Trong ngữ cảnh này, “lower bound” và “upper bound” là tên **hai phép tìm vị trí**, không phải khái niệm cận dưới `Ω(f(n))` hay cận trên `O(f(n))` trong phân tích độ phức tạp thuật toán.

## 1. Định nghĩa chính xác trên mảng tăng dần

Cho mảng `a` dài `n`, được **sắp xếp tăng không giảm**: `a[0] ≤ a[1] ≤ ... ≤ a[n−1]`. Chỉ số bắt đầu từ `0`.

- **`lowerBound(a, x)`:** Chỉ số nhỏ nhất `i` sao cho `a[i] ≥ x`.
- **`upperBound(a, x)`:** Chỉ số nhỏ nhất `i` sao cho `a[i] > x`.

Nếu không có chỉ số thỏa điều kiện, cả hai hàm trả về **`n`**, tức vị trí ngay sau phần tử cuối. Với mảng rỗng, `n=0` nên cả hai đều trả `0`.

Hãy hiểu chúng như **hai điểm chia** trong một dãy đã sắp xếp:

- Trước `lowerBound(x)`, mọi phần tử **nhỏ hơn** `x`.
- Từ `lowerBound(x)` trở đi, mọi phần tử **lớn hơn hoặc bằng** `x`.
- Trước `upperBound(x)`, mọi phần tử **nhỏ hơn hoặc bằng** `x`.
- Từ `upperBound(x)` trở đi, mọi phần tử **lớn hơn** `x`.

Vì vậy dãy được chia thành ba đoạn **nửa mở**:

```text
[0, lowerBound(x))             : các giá trị < x
[lowerBound(x), upperBound(x)) : các giá trị = x
[upperBound(x), n)             : các giá trị > x
```

Ký hiệu `[l, r)` nghĩa là **bao gồm chỉ số `l` và loại trừ chỉ số `r`**. Đây là quy ước giúp xử lý được cả khoảng rỗng, khoảng kết thúc ở `n` và phép đếm bằng phép trừ hai đầu mút.

**Cần nhớ:** “upper bound” trả chỉ số **đầu tiên lớn hơn `x`**, không phải chỉ số cuối cùng bằng `x`. Chỉ số cuối cùng bằng `x` là `upperBound(x)−1` **nếu và chỉ nếu `x` thực sự tồn tại**.

## 2. Ví dụ trực quan với giá trị trùng nhau

Cho:

```text
Chỉ số:  0  1  2  3  4  5
Giá trị: 1  2  2  2  4  7
```

| Giá trị `x` | `lowerBound(x)`: đầu tiên `≥x` | `upperBound(x)`: đầu tiên `>x` | Số phần tử `=x` |
| --- | ---: | ---: | ---: |
| `0` | `0` | `0` | `0` |
| `1` | `0` | `1` | `1` |
| `2` | `1` | `4` | `3` |
| `3` | `4` | `4` | `0` |
| `4` | `4` | `5` | `1` |
| `7` | `5` | `6` | `1` |
| `9` | `6` | `6` | `0` |

Ví dụ `x=2`: phần tử `2` đầu tiên ở chỉ số `1`, cuối cùng ở chỉ số `3`. Do đó `lowerBound(2)=1` và `upperBound(2)=4`. Khoảng các phần tử bằng `2` là `[1,4)`, chứa đúng `4−1=3` phần tử.

Ví dụ `x=3`: không có phần tử bằng `3`. Vị trí đầu tiên chứa giá trị **ít nhất là `3`** nằm tại `4`, và vị trí đầu tiên chứa giá trị **lớn hơn `3`** cũng nằm tại `4`. Hai cận bằng nhau không có nghĩa là lỗi; nó chính là **vị trí có thể chèn `3`** để duy trì thứ tự.

Ví dụ `x=9`: không có phần tử nào `≥9` hoặc `>9`. Cả hai hàm trả `n=6`; đây là chỉ số chèn ở cuối, **không được truy cập `a[6]`**.

## 3. Tại sao có thể dùng tìm kiếm nhị phân?

Tìm kiếm nhị phân không đơn giản là “so sánh giá trị ở giữa”. Nó cần một **mệnh đề đơn điệu theo chỉ số**, có dạng:

```text
false false false ... false true true ... true
                         ^
                    first true
```

Với mảng tăng không giảm:

- `P_lower(i) = (a[i] >= x)` là `false` ở phần đầu và `true` ở phần sau. Vị trí `true` đầu tiên là lower bound.
- `P_upper(i) = (a[i] > x)` cũng có dạng `false ... true`. Vị trí `true` đầu tiên là upper bound.

Nếu tất cả điều kiện đều `false`, đáp án là `n`. Nếu điều kiện đúng ngay từ phần tử đầu, đáp án là `0`.

**Tiền điều kiện bắt buộc:** Mảng phải được sắp theo **cùng quan hệ thứ tự dùng để so sánh trong tìm kiếm**. Nếu mảng chưa sắp xếp, tính chất `false ... true` không được bảo đảm, và thuật toán có thể bỏ sót vị trí đúng. Với mảng giảm dần phải **đổi điều kiện so sánh** hoặc định nghĩa cận theo comparator tương ứng.

Không được lấy mệnh đề `a[i] == x` làm điều kiện “first true” một cách máy móc: trong dãy `[1,2,2,3]`, nó có dạng `false, true, true, false`, **không đơn điệu**. Cần dùng `>=` hoặc `>` để tìm **biên** của nhóm giá trị bằng nhau.

## 4. Mẫu tìm kiếm nhị phân với khoảng nửa mở

Dùng hai biến `lo` và `hi` để giữ **khoảng ứng viên `[lo, hi)`**. Khởi đầu `lo=0` và `hi=n`. Mỗi bước chọn `mid = lo + (hi−lo)/2` (chia nguyên), rồi loại một nửa không thể chứa biên cần tìm.

### Lower bound — phần tử đầu tiên `≥x`

```java
static int lowerBound(int[] a, int x) {
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
```

Nếu `a[mid] < x`, theo thứ tự tăng dần, **mọi chỉ số từ `lo` đến `mid` đều có giá trị nhỏ hơn `x`**, nên không thể là lower bound; loại cả `mid` và tiếp tục ở `mid+1`.

Ngược lại, nếu `a[mid] >= x`, `mid` **có thể chính là kết quả**. Ta giữ `mid` trong khoảng ứng viên bằng cách đặt `hi=mid`; không được dùng `hi=mid−1` trong mẫu nửa mở này.

### Upper bound — phần tử đầu tiên `>x`

```java
static int upperBound(int[] a, int x) {
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
```

Chỉ thay điều kiện nhánh trái từ `a[mid] < x` thành `a[mid] <= x`. Các phần tử **bằng** `x` cũng bị loại khỏi miền tìm upper bound, nên kết quả luôn nằm **sau toàn bộ nhóm bằng `x`**.

**Vì sao tính `mid` như vậy?** Công thức `(lo+hi)/2` có thể làm tràn kiểu số nguyên nếu tổng lớn. `lo+(hi−lo)/2` tránh phép cộng hai chỉ số lớn; ở đây `0≤lo≤hi≤n` nên `hi−lo` không âm và không vượt kích thước mảng.

**Khi nào dừng?** Khi `lo==hi`, khoảng `[lo,hi)` rỗng; biên đã được xác định. Vòng lặp dùng `lo<hi`, vì thế không có truy cập `a[n]` khi `n` là kết quả hợp lệ.

## 5. Chứng minh tính đúng cho lower bound

Gọi `b` là vị trí lower bound cần tìm. Để chứng minh thuật toán không chỉ “có vẻ đúng”, ta chứng minh bất biến sau mỗi vòng:

1. `0 ≤ lo ≤ hi ≤ n`.
2. Với mọi `i<lo`, có `a[i] < x`: những vị trí phía trái **chắc chắn không thỏa** điều kiện.
3. Với mọi `i≥hi` và `i<n`, có `a[i] ≥ x`: những vị trí phía phải **chắc chắn thỏa** điều kiện.
4. Biên chuyển tiếp `b` luôn nằm trong **đoạn đóng `[lo,hi]`**; `hi=n` là đáp án hợp lệ khi không có phần tử thỏa.

**Khởi tạo.** `lo=0` và `hi=n`. Hai miền đã loại ở ngoài rỗng, nên các mệnh đề về chúng đúng; `b` chắc chắn thuộc `[0,n]`.

**Duy trì.** Lấy `mid` thuộc `[lo,hi)`:

- Nếu `a[mid]<x`, do mảng tăng dần nên mọi `i≤mid` đều có `a[i]<x`. Đặt `lo=mid+1` không loại `b`; toàn bộ tiền tố mới bị loại là không thỏa.
- Nếu `a[mid]≥x`, mọi `i≥mid` đều có `a[i]≥x`. Đặt `hi=mid` giữ lại `mid`, không loại `b`; mọi vị trí từ `hi` mới về bên phải đều thỏa.

**Kết thúc.** Nếu `lo<hi`, ta có `lo≤mid<hi`. Nhánh trái tăng `lo` ít nhất một; nhánh phải giảm `hi` ít nhất một. Độ dài `hi−lo` là số nguyên không âm giảm nghiêm ngặt, nên vòng lặp dừng.

**Đúng kết quả.** Tại điểm dừng `lo=hi=p`. Mọi chỉ số trước `p` đều nhỏ hơn `x` và mọi chỉ số từ `p` đến cuối đều lớn hơn hoặc bằng `x`. Do đó `p` là **chỉ số đầu tiên thỏa `a[i]≥x`**, hoặc `p=n` nếu không có.

Chứng minh upper bound **hoàn toàn tương tự**, thay các mệnh đề thành: mọi `i<lo` có `a[i]≤x` và mọi `i≥hi` có `a[i]>x`. Kết quả là biên đầu tiên có giá trị `>x`.

Điểm then chốt là **không bỏ ứng viên `mid` ở nhánh “đã thỏa điều kiện”**. Lỗi `hi=mid−1` trong mẫu này có thể bỏ qua chính vị trí đầu tiên cần tìm.

## 6. Các bài toán suy ra trực tiếp từ hai cận

Với mảng tăng không giảm dài `n`, đặt `L=lowerBound(a,x)` và `U=upperBound(a,x)`:

| Câu hỏi | Công thức/điều kiện | Lưu ý |
| --- | --- | --- |
| Giá trị `x` có xuất hiện không? | `L<n && a[L]==x` | Kiểm tra `L<n` trước khi truy cập |
| Vị trí đầu tiên bằng `x` | `L` nếu tồn tại | Nếu không có, không thể coi `L` là vị trí xuất hiện |
| Vị trí cuối cùng bằng `x` | `U−1` nếu tồn tại | Trả chỉ số không tồn tại nếu `L==U` |
| Số phần tử nhỏ hơn `x` | `L` | Vì có đúng `L` phần tử ở chỉ số `0..L−1` |
| Số phần tử nhỏ hơn hoặc bằng `x` | `U` | Vì đoạn `[0,U)` chứa đúng các giá trị `≤x` |
| Số phần tử bằng `x` | `U−L` | Bằng 0 nếu không tồn tại |
| Số phần tử lớn hơn `x` | `n−U` | Có thể bằng 0 |
| Số phần tử lớn hơn hoặc bằng `x` | `n−L` | Có thể bằng `n` |
| Chỉ số cuối cùng có giá trị `<x` | `L−1` | Giá trị `−1` biểu thị không tồn tại |
| Chỉ số cuối cùng có giá trị `≤x` | `U−1` | Giá trị `−1` biểu thị không tồn tại |
| Vị trí chèn `x` **trước** các giá trị bằng `x` | `L` | Chèn tại `L` vẫn giữ thứ tự tăng không giảm |
| Vị trí chèn `x` **sau** các giá trị bằng `x` | `U` | Chèn tại `U` cũng giữ thứ tự tăng không giảm |

### Đếm phần tử trong một đoạn giá trị

Muốn đếm số phần tử thuộc **đoạn đóng `[low,high]`**, với `low≤high`:

```text
count(low <= a[i] <= high)
  = upperBound(a, high) - lowerBound(a, low)
```

Lý do: `lowerBound(low)` là biên đầu tiên của các giá trị có thể thuộc đoạn; `upperBound(high)` là biên ngay sau các giá trị cuối cùng có thể thuộc đoạn. Hiệu của hai vị trí chính là độ dài miền chỉ số chứa các giá trị thuộc đoạn.

Ví dụ `a=[1,2,2,2,4,7]`, `[low,high]=[2,4]`: `lowerBound(2)=1` và `upperBound(4)=5`, nên có `5−1=4` phần tử thuộc đoạn (`2,2,2,4`).

Nếu `low>high`, đoạn giá trị rỗng và đáp án quy ước là `0`; nên kiểm tra điều này trước khi trừ cận. Tránh mẹo `lowerBound(high+1)` khi `high` là `int`: `high+1` có thể **tràn số** tại `Integer.MAX_VALUE`. Dùng trực tiếp `upperBound(high)` an toàn hơn.

### Tìm khoảng tất cả các bản sao

Khoảng chỉ số **`[L,U)`** chính là các phần tử bằng `x`. Muốn xử lý từng bản sao, lặp `i` từ `L` đến `U−1`. Muốn biết chỉ có một bản sao không, kiểm tra `U−L==1`. Muốn biết có ít nhất hai bản sao không, kiểm tra `U−L>=2`.

Ví dụ trong bảng giá trị trùng, `x=2` có `L=1`, `U=4`, nên đúng ba lần xuất hiện tại `1,2,3`. Đây là một cách xử lý trùng rõ nghĩa hơn việc tìm thấy **một** vị trí bất kỳ.

## 7. Mẫu tổng quát: first true trên điều kiện đơn điệu

Hai cận là hai trường hợp của bài toán:

> Cho predicate `P(i)` đổi từ `false` sang `true` tối đa một lần theo chiều chỉ số, tìm chỉ số `i` nhỏ nhất sao cho `P(i)` đúng; nếu không có, trả `n`.

Mẫu Java tổng quát:

```java
// Đoạn minh họa: predicate.test(i) phải có dạng false...true.
static int firstTrue(int n, java.util.function.IntPredicate predicate) {
    int lo = 0;
    int hi = n;
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
```

Áp dụng:

- Lower bound: `P(i) = (a[i] >= x)`.
- Upper bound: `P(i) = (a[i] > x)`.
- Tìm vị trí đầu tiên có tổng tiền tố đạt ngưỡng `T`: `P(i) = (prefix[i] >= T)` **chỉ khi** dãy tổng tiền tố không giảm, chẳng hạn khi các số hạng đều không âm.
- Tìm dung lượng hoặc thời gian nhỏ nhất để hoàn thành một công việc: đặt `P(k) = "có thể hoàn thành trong ngưỡng k"`; chỉ dùng binary search khi chứng minh được tính đơn điệu: nếu ngưỡng `k` đủ thì mọi ngưỡng lớn hơn cũng đủ.

Không được tùy tiện áp dụng binary search cho một predicate có dạng `false,true,false`, hoặc khi tính kết quả ở ngưỡng lớn hơn có thể đảo từ đúng sang sai. **Chứng minh tính đơn điệu** là điều kiện kỹ thuật của cách tìm “đáp án nhỏ nhất thỏa”.

### Nếu mảng đã sắp giảm dần?

Với `a=[9,7,7,4,1]`, không dùng nguyên xi điều kiện tăng dần. Nếu cần **vị trí đầu tiên có giá trị `≤7`** trong mảng giảm dần, predicate là `a[i]≤7` và biên là `1`. Vị trí đầu tiên có giá trị `<7` là `3`.

Tổng quát với các đối tượng có comparator `cmp`, ý nghĩa lower bound theo **thứ tự mà comparator định nghĩa** là “vị trí đầu tiên `cmp(a[i],x) >= 0`”, upper bound là “vị trí đầu tiên `cmp(a[i],x) > 0`”. Mảng phải được sắp bằng **chính comparator đó**; với comparator đảo chiều, từ “nhỏ hơn” ở đây được hiểu **theo comparator**, không nhất thiết theo giá trị số học thông thường.

## 8. Java 17+: triển khai, tình huống biên và phép đối chiếu

Chương trình sau sử dụng mảng `int[]` **đã sắp tăng không giảm**, trả chỉ số theo quy ước `[0,n]`. Nó **không sửa mảng** trong hai phép tìm biên. Hàm kiểm thử cuối tạo mọi mảng độ dài `0..5` từ `−1,0,1`, sắp xếp từng mảng rồi đối chiếu lower/upper bound với cách quét tuyến tính trên năm giá trị đích `−2..2`.

Lưu toàn bộ mã trong tệp **BoundSearchDemo.java**:

```java
import java.util.Arrays;

public class BoundSearchDemo {
    // Mảng phải được sắp xếp tăng không giảm.
    // Trả chỉ số đầu tiên có a[i] >= x; nếu không có, trả a.length.
    static int lowerBound(int[] a, int x) {
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

    // Trả chỉ số đầu tiên có a[i] > x; nếu không có, trả a.length.
    static int upperBound(int[] a, int x) {
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

    static boolean contains(int[] a, int x) {
        int first = lowerBound(a, x);
        return first < a.length && a[first] == x;
    }

    static int countEqual(int[] a, int x) {
        return upperBound(a, x) - lowerBound(a, x);
    }

    // Đếm trong đoạn giá trị đóng [low, high].
    static int countInClosedRange(int[] a, int low, int high) {
        if (low > high) {
            return 0;
        }
        return upperBound(a, high) - lowerBound(a, low);
    }

    // Đối chiếu exhaustive trên input nhỏ.
    static int checkSmallCases() {
        int representations = 1;
        int checked = 0;
        for (int n = 0; n <= 5; n++) {
            for (int encoded = 0; encoded < representations; encoded++) {
                int[] a = new int[n];
                int code = encoded;
                for (int i = 0; i < n; i++) {
                    a[i] = code % 3 - 1;
                    code /= 3;
                }
                Arrays.sort(a);

                for (int x = -2; x <= 2; x++) {
                    int expectedLower = 0;
                    while (expectedLower < a.length
                            && a[expectedLower] < x) {
                        expectedLower++;
                    }

                    int expectedUpper = 0;
                    while (expectedUpper < a.length
                            && a[expectedUpper] <= x) {
                        expectedUpper++;
                    }

                    int actualLower = lowerBound(a, x);
                    int actualUpper = upperBound(a, x);
                    if (actualLower != expectedLower
                            || actualUpper != expectedUpper) {
                        throw new AssertionError(
                            "input=" + Arrays.toString(a)
                            + ", x=" + x
                            + ", expected=[" + expectedLower + ","
                            + expectedUpper + "]"
                            + ", actual=[" + actualLower + ","
                            + actualUpper + "]");
                    }
                    checked++;
                }
            }
            representations *= 3;
        }
        return checked;
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 2, 2, 4, 7};
        int[] before = a.clone();

        for (int x : new int[]{0, 2, 3, 7, 9}) {
            System.out.println(
                "x=" + x
                + ": lower=" + lowerBound(a, x)
                + ", upper=" + upperBound(a, x)
                + ", count=" + countEqual(a, x)
                + ", found=" + contains(a, x));
        }

        System.out.println("Count [2,4]: "
                           + countInClosedRange(a, 2, 4));
        System.out.println("Count [5,2]: "
                           + countInClosedRange(a, 5, 2));
        System.out.println("Last < 2: " + (lowerBound(a, 2) - 1));
        System.out.println("Last <= 2: " + (upperBound(a, 2) - 1));

        int[] empty = {};
        System.out.println("Empty: "
                           + lowerBound(empty, 3) + ", "
                           + upperBound(empty, 3));
        int[] extremes = {Integer.MIN_VALUE, Integer.MAX_VALUE};
        System.out.println("Upper(MAX_VALUE): "
                           + upperBound(extremes, Integer.MAX_VALUE));

        System.out.println("Input unchanged: "
                           + Arrays.equals(a, before));
        System.out.println("Exhaustive small check: OK ("
                           + checkSmallCases() + " queries)");
    }
}
```

Biên dịch, chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 BoundSearchDemo.java
java BoundSearchDemo
```

Stdout:

```text
x=0: lower=0, upper=0, count=0, found=false
x=2: lower=1, upper=4, count=3, found=true
x=3: lower=4, upper=4, count=0, found=false
x=7: lower=5, upper=6, count=1, found=true
x=9: lower=6, upper=6, count=0, found=false
Count [2,4]: 4
Count [5,2]: 0
Last < 2: 0
Last <= 2: 3
Empty: 0, 0
Upper(MAX_VALUE): 2
Input unchanged: true
Exhaustive small check: OK (1820 queries)
```

**Giải thích phép kiểm thử nhỏ:** Có `1+3+9+27+81+243=364` mảng được sinh (trước khi sort, các chuỗi giá trị có thể khác nhau dù sau sort giống nhau). Mỗi mảng được kiểm với `5` giá trị đích nên có `364×5=1.820` truy vấn. Baseline quét từ trái sang phải tìm lần đầu `≥x` và lần đầu `>x`. Hai phương pháp phải trả cùng chỉ số trong mọi truy vấn nhỏ.

Kiểm thử này giúp phát hiện lỗi lệch biên, đặc biệt khi input trống hoặc trùng nhau, nhưng **không thay thế chứng minh bất biến vòng lặp** ở phần trước. Code dùng `int` để tính `mid` an toàn theo hiệu chỉ số, và không thực hiện phép `x+1` nên xử lý được `Integer.MAX_VALUE`.

## 9. So sánh với tìm kiếm nhị phân trả một chỉ số bất kỳ

Java có `Arrays.binarySearch(a, x)` trên mảng đã sắp tăng dần. Với giá trị tồn tại nhiều lần, kết quả là **một chỉ số khớp**, không cam kết là lần xuất hiện đầu tiên hay cuối cùng. Vì thế không thể dùng chỉ số trả về trực tiếp để đếm số bản sao hoặc xác định cả đoạn bằng `x`.

Nếu giá trị không tồn tại, `Arrays.binarySearch` trả `-(insertionPoint)-1`, trong đó `insertionPoint` là chỉ số chèn duy trì thứ tự (vị trí đầu tiên lớn hơn giá trị cần tìm trong trường hợp không có giá trị bằng). Nhưng cách mã hóa số âm này **khác** với API lower/upper bound ở bài này: hai hàm tự viết luôn trả số nguyên từ `0` đến `n`, kể cả khi không tìm thấy `x`.

Điều quan trọng không phải tên hàm mà là **hợp đồng trả về**. Nếu API chỉ trả “có hay không”, không tự suy ra vị trí cận. Nếu API trả “một vị trí tìm thấy”, không tự suy ra đó là vị trí **đầu/cuối** trong nhóm trùng.

### Trong thư viện Java Collection

`Collections.binarySearch(list, key)` cũng tập trung vào tìm kiếm một vị trí khớp và mã hóa vị trí chèn khi không tìm thấy; nó không cung cấp trực tiếp hai cận cho các phần tử trùng. Với `List` không hỗ trợ truy cập ngẫu nhiên hiệu quả (như một linked list), việc gọi `get(mid)` lặp đi lặp lại có thể làm tổng thời gian tệ hơn so với mảng hoặc `ArrayList`. Khi đánh giá `O(log n)` cho binary search, cần cả **dữ liệu sắp xếp** và **truy cập vị trí giữa đủ rẻ**.

## 10. Chi phí, tiền xử lý và nhiều truy vấn

Trên một mảng đã sắp xếp và truy cập phần tử theo chỉ số trong `O(1)`:

- Mỗi lần tìm lower bound hoặc upper bound giảm ít nhất một nửa khoảng ứng viên, nên dùng **`O(log(n+1))` thời gian**, **`O(1)` bộ nhớ phụ** với triển khai vòng lặp.
- Đếm số phần tử bằng `x` cần **hai lần** tìm kiếm nhị phân; tổng vẫn là `O(log n)`.
- Đếm phần tử trong đoạn giá trị `[low,high]` cũng cần hai cận; tổng vẫn là `O(log n)`.
- Nếu cần liệt kê đủ `k` phần tử bằng `x`, bước tìm biên là `O(log n)`, nhưng **xuất `k` phần tử tốn thêm `Ω(k)` thời gian**.

Nếu input **chưa sắp xếp**, phải tính chi phí tạo bản sao (nếu cần giữ nguyên) và sắp xếp trước: thường `O(n log n)` thời gian và ít nhất `O(n)` bộ nhớ cho bản sao, cộng `O(q log n)` cho `q` truy vấn. Với chỉ một truy vấn và mảng nhỏ, quét tuyến tính `O(n)` có thể đơn giản hơn và không phải trả chi phí sort. Nếu có hàng nghìn truy vấn trên dữ liệu tĩnh, sort một lần rồi tìm hai cận nhiều lần thường đáng cân nhắc.

Các cận chỉ có ý nghĩa nếu thứ tự dữ liệu **còn hợp lệ**. Thêm/xóa/sửa phần tử có thể làm mất tính sắp xếp; phải duy trì cấu trúc dữ liệu có thứ tự hoặc sắp xếp lại trước truy vấn. Nếu phải chèn/xóa thường xuyên, mảng có thể mất `O(n)` chi phí dịch phần tử cho mỗi cập nhật dù tìm vị trí chèn là `O(log n)`. Khi đó cần xem xét cấu trúc có thứ tự hỗ trợ cập nhật và truy vấn theo mục tiêu cụ thể.

**Không nhầm với cận độ phức tạp.** Trong phân tích thuật toán, `O(f(n))` là cận trên của tốc độ tăng chi phí, `Ω(f(n))` là cận dưới, và `Θ(f(n))` mô tả cận chặt. Còn `lowerBound` và `upperBound` ở đây là **chỉ số chia dãy theo quan hệ so sánh**. Một thao tác tên “lower bound” bản thân nó có thể có độ phức tạp thời gian `O(log n)`.

## 11. Các lỗi thường gặp

**1. Nhầm dấu so sánh `<` và `<=`.** Lower bound loại các giá trị **nhỏ hơn** `x`; upper bound loại cả các giá trị **bằng** `x`. Chỉ một ký tự khác nhau nhưng ảnh hưởng trực tiếp đến số lượng phần tử trùng.

**2. Trả chỉ số cuối thay vì vị trí ngay sau cuối.** Upper bound trả `U`; nếu cần chỉ số cuối bằng `x` thì dùng `U−1` **sau khi kiểm tra tồn tại**. Nếu `x` không có, phép `U−1` có thể là chỉ số của một phần tử khác.

**3. Truy cập `a[n]` khi kết quả bằng `n`.** `n` là **sentinel hợp lệ** cho “không tìm thấy phần tử thỏa”, không phải chỉ số truy cập mảng. Muốn kiểm tra tồn tại, dùng `L<n && a[L]==x`.

**4. Trộn quy ước khoảng đóng và nửa mở.** Mẫu `[lo,hi)` đi cùng `hi=n`, `while(lo<hi)`, `hi=mid`. Mẫu `[lo,hi]` dùng bộ quy tắc khác. Không được lấy một dòng của mẫu này chèn vào mẫu kia mà không chứng minh lại.

**5. Bỏ `mid` khi nó có thể là đáp án.** Ở nhánh `a[mid]>=x` của lower bound, `mid` có thể là vị trí đầu tiên thỏa; dùng `hi=mid−1` trong mẫu nửa mở có thể loại đáp án.

**6. Không chứng minh mảng đã sắp xếp.** Một lần test đúng với input ngẫu nhiên không bảo đảm predicate đơn điệu. Mảng giảm dần hoặc comparator khác phải có định nghĩa và điều kiện so sánh tương ứng.

**7. Dùng `x+1` để thay upper bound.** Nếu `x=Integer.MAX_VALUE`, `x+1` tràn về `Integer.MIN_VALUE` với `int`; đồng thời không có “giá trị kế tiếp” rõ ràng cho nhiều kiểu dữ liệu. Tìm trực tiếp điều kiện `a[mid]>x`.

**8. Quên mảng rỗng, một phần tử, toàn phần tử bằng nhau.** Các trường hợp này bộc lộ lỗi `hi=n−1`, vòng lặp không tiến hoặc phép truy cập ngoài vùng.

**9. Nghĩ tìm kiếm nhị phân luôn nhanh hơn quét.** Với dữ liệu chưa sắp xếp, chỉ một truy vấn hoặc cấu trúc truy cập giữa chậm, chi phí tạo điều kiện sử dụng binary search có thể lớn hơn lợi ích.

**10. Dùng một kết quả từ `Arrays.binarySearch` để suy ra cả đoạn trùng.** Thư viện không cam kết chọn lần xuất hiện đầu hoặc cuối. Hãy gọi đúng hai phép tìm cận nếu bài cần ranh giới.

## 12. Bài tập rèn tư duy

**Bài 1 — Tự tính bằng tay.** Với `a=[-3,-1,-1,0,0,0,5]`, hãy tính lower/upper bound của `−4,−1,0,1,5,6`. Từ đó xác định số lần xuất hiện của `−1` và `0`.

*Gợi ý:* `lowerBound(0)=3`, `upperBound(0)=6`, số phần tử `0` là `3`.

**Bài 2 — Đếm đoạn giá trị.** Với mảng trên, đếm số phần tử thuộc `[-1,0]`, `[1,4]` và `[5,Integer.MAX_VALUE]`. Giải thích vì sao nên dùng `upperBound(high)−lowerBound(low)` thay vì `lowerBound(high+1)−lowerBound(low)`.

*Gợi ý:* Ba kết quả lần lượt là `5`, `0`, `1`.

**Bài 3 — Chứng minh bất biến.** Viết ba mệnh đề bất biến của lower bound: các vị trí phía trái không thỏa, các vị trí phía phải thỏa, đáp án nằm giữa. Chứng minh từng nhánh cập nhật và điều kiện dừng.

**Bài 4 — Tìm phía ngược.** Cho `a=[9,7,7,4,1]` đã sắp giảm dần, định nghĩa “cận đầu tiên `≤x`” và “cận đầu tiên `<x`” cho `x=7`. Viết điều kiện tương ứng trong mẫu first true, rồi tính hai kết quả.

*Gợi ý:* `1` và `3`; dấu so sánh khác bản tăng dần.

**Bài 5 — Sinh test đối chiếu.** Dùng quét tuyến tính làm oracle cho hai cận. Sinh các mảng có nhiều phần tử trùng, cả input rỗng; so sánh kết quả với binary search ở `x` nhỏ hơn min, bằng min, nằm giữa, bằng max và lớn hơn max. Phân tích tại sao test hữu ích nhưng không thay thế chứng minh tổng quát.

**Bài 6 — Quy mô truy vấn.** Có `n=100.000` giá trị chưa sắp và `q=10.000` truy vấn số lượng phần tử bằng `x`. So sánh chi phí một lần sort rồi `q` lần dùng hai cận với quét toàn mảng cho từng truy vấn. Nêu giả định dữ liệu không đổi trong các truy vấn.

**Bài 7 — Tìm đáp án bằng predicate.** Một bài có ngưỡng thời gian `T`. Nếu hoàn thành được trong `T` thì mọi ngưỡng lớn hơn đều hoàn thành được. Hãy định nghĩa predicate `feasible(T)` và nêu cách tìm thời gian nguyên nhỏ nhất khả thi bằng mẫu first true, kể cả trường hợp không có ngưỡng khả thi trong miền được cho.

## 13. Checklist áp dụng đúng

Trước khi viết lower/upper bound trong bài mới, kiểm tra:

1. Dữ liệu **đã sắp xếp theo đúng comparator** chưa? Nếu chưa, chi phí chuẩn bị là gì?
2. Cần vị trí đầu tiên `>=x` hay `>x`? Hay bài hỏi vị trí cuối `<x` / `<=x` để suy ra từ hai cận?
3. Khi không tồn tại phần tử thỏa, API trả `n` và caller có kiểm tra biên trước khi truy cập mảng không?
4. Khoảng tìm kiếm dùng `[lo,hi)` và các bước cập nhật có nhất quán với `hi=n`, `while(lo<hi)`, `hi=mid` không?
5. Điều kiện trên chỉ số có **đơn điệu false→true** không? Nếu không, binary search theo mẫu này không có cơ sở.
6. Có giá trị lặp, input rỗng, giá trị tại biên kiểu số, hoặc đoạn giá trị `low>high` không?
7. Đã chứng minh bất biến, kết thúc, tính đúng; tính cả sort, nhiều truy vấn, cập nhật và lượng output khi so sánh hiệu năng chưa?

**Tiêu chí hoàn thành:** Bạn có thể phát biểu bằng lời và ký hiệu `lowerBound(x)=first i with a[i]>=x`, `upperBound(x)=first i with a[i]>x`, tự tính ví dụ có trùng, chứng minh vòng lặp nửa mở, viết mã Java 17+ không lệch biên và dùng hai cận để tìm, đếm hoặc chèn với chi phí chính xác.
