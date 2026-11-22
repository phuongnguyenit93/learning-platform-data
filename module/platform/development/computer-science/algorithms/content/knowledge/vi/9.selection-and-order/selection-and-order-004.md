# Chọn pivot ngẫu nhiên và bảo đảm theo kỳ vọng

Trong các thuật toán **chọn phần tử theo thứ hạng (selection)** và **sắp xếp dựa trên phân hoạch**, một quyết định nhỏ có thể thay đổi rất lớn thời gian chạy: chọn phần tử **pivot (chốt)** nào để phân chia dãy? Nếu pivot liên tục nằm sát một đầu của thứ tự, thuật toán có thể xử lý gần như toàn bộ dãy hết lần này đến lần khác. Nếu pivot thường chia dãy thành các phần tương đối cân bằng, lượng công việc giảm đáng kể.

**Chọn pivot ngẫu nhiên (randomized pivot selection)** là cách chọn một vị trí trong đoạn đang xét bằng phép lấy mẫu ngẫu nhiên, thay vì luôn chọn đầu, cuối hoặc vị trí cố định. Khi mỗi vị trí có cơ hội được chọn như nhau và lựa chọn không bị đối thủ dự đoán/điều khiển, ta có các **bảo đảm theo kỳ vọng (expected guarantees)**: *randomized Quickselect* chọn một phần tử theo thứ hạng trong **O(n) thời gian kỳ vọng**, còn *randomized Quicksort* sắp xếp trong **O(n log n) thời gian kỳ vọng**. Tuy vậy, **trường hợp xấu nhất của cả hai vẫn có thể là O(n²)**.

Bài này tập trung vào **lý do chọn pivot ngẫu nhiên, phân hoạch ba hướng khi có khóa trùng, chứng minh tính đúng đắn, cách hiểu kỳ vọng, giới hạn bảo đảm và triển khai Java 17+**. Không nhầm ngẫu nhiên hóa với một cam kết tuyệt đối rằng lần chạy nào cũng nhanh.

## 1. Pivot, phân hoạch và vai trò trong thuật toán

Với đoạn mảng `A[lo..hi]` (hai cận **bao gồm**), chọn một giá trị pivot `p`. Phép **phân hoạch (partition)** sắp lại chính đoạn đó thành các vùng có tính chất:

- Mọi giá trị trong vùng trái **nhỏ hơn `p`**.
- Các giá trị **bằng `p`** nằm ở vùng giữa.
- Mọi giá trị trong vùng phải **lớn hơn `p`**.

Nếu phần tử ở vị trí khác được chọn làm pivot, các vùng có thể thay đổi kích thước; việc chọn pivot không thay đổi yêu cầu phải bảo toàn đầy đủ phần tử đầu vào.

Ví dụ, với `A = [8, 2, 4, 4, 9, 1, 6]` và pivot `p = 4`, ba **nhóm giá trị** cần có là:

| Nhóm | Các giá trị | Số phần tử |
| --- | --- | ---: |
| Nhỏ hơn 4 | `2, 1` | 2 |
| Bằng 4 | `4, 4` | 2 |
| Lớn hơn 4 | `8, 9, 6` | 3 |

Thứ tự **bên trong từng nhóm** không bắt buộc được giữ nguyên nếu thuật toán chỉ yêu cầu phân hoạch. Sau bước này, các vị trí thứ hạng 0 và 1 thuộc nhóm nhỏ hơn 4, vị trí 2 và 3 có giá trị 4, còn vị trí 4–6 thuộc nhóm lớn hơn 4.

- **Quickselect** chỉ cần phần đoạn chứa thứ hạng đích, nên có thể **bỏ hai vùng không liên quan** sau mỗi lần phân hoạch.
- **Quicksort** cần sắp cả vùng nhỏ hơn và lớn hơn pivot, nhưng **không cần xử lý lại vùng bằng pivot** trong phân hoạch ba hướng.

Điều cốt lõi là **phân hoạch chính xác**; ngẫu nhiên hóa chỉ quyết định pivot nào được đưa vào phép phân hoạch.

## 2. Vì sao pivot cố định có thể gây O(n²)?

Xét một Quickselect dùng pivot là **phần tử đầu** của đoạn. Nếu mảng đang tăng dần và mục tiêu là phần tử lớn nhất, pivot đầu luôn nhỏ nhất: sau mỗi lần, thuật toán bỏ được chỉ một phần tử và giữ lại đoạn có `n-1` phần tử. Chi phí phân hoạch lần lượt xấp xỉ:

```text
n + (n - 1) + (n - 2) + ... + 2 + 1
= n(n + 1) / 2
= Θ(n²)
```

Tương tự, Quicksort chọn pivot đầu hoặc cuối liên tục trên một dãy có trật tự bất lợi có thể tạo các phân hoạch cực kỳ mất cân bằng, và tổng thời gian thành Θ(n²).

**Không phải mọi mảng đã sắp đều gây chậm cho mọi phiên bản**: điều này phụ thuộc cách chọn pivot và cách phân hoạch. Chọn phần tử giữa theo **vị trí** là một chiến lược khác, nhưng phần tử ở vị trí giữa không nhất thiết là trung vị theo **giá trị**; với dữ liệu có chủ đích, nó cũng có thể tạo phân hoạch mất cân bằng.

Ngược lại, một pivot có thứ hạng gần trung vị tạo hai vùng tương đối cân bằng. Với Quicksort, điều đó làm độ sâu của cây chia nhỏ đi; với Quickselect, nó khiến đoạn đang xét nhỏ đi nhanh hơn.

## 3. Chọn pivot ngẫu nhiên đúng nghĩa

Trong mỗi đoạn chỉ số `[lo, hi]`, hãy chọn **đều** một chỉ số `r` thuộc đoạn này:

```text
r <- RANDOM_INTEGER_UNIFORMLY(lo, hi)
pivot <- A[r]
```

Nếu đoạn dài `m = hi-lo+1`, mỗi vị trí có xác suất `1/m` được chọn. Với các khóa phân biệt, điều này cũng làm mỗi **thứ hạng** trong đoạn có xác suất bằng nhau. Với khóa trùng, nhiều vị trí có cùng giá trị pivot; phân hoạch ba hướng xử lý nhóm trùng đúng và thường có lợi.

Trong Java 17, có thể viết:

```java
int pivotIndex = lo + random.nextInt(hi - lo + 1);
int pivot = a[pivotIndex];
```

Đây là **đoạn minh họa**, không phải một chương trình Java độc lập. `random` là một đối tượng `java.util.Random` đã được tạo và `lo <= hi`. Khi truy cập chỉ số của một mảng Java hợp lệ, `hi-lo+1` là kích thước đoạn và dương. `Random.nextInt(bound)` trả một số nguyên từ 0 đến `bound-1`; cộng `lo` cho phép lấy vị trí trong đoạn cần xử lý.

**Chọn ngẫu nhiên mỗi lần phân hoạch** khác với **xáo trộn mảng một lần rồi chọn pivot cố định**. Với khóa phân biệt và xáo trộn thực sự đều, hai cách có thể dẫn đến những phân phối thứ hạng pivot phù hợp cho phân tích; nhưng chi phí tạo số ngẫu nhiên, sao chép/xáo trộn và xử lý khóa trùng có thể khác. Không cần xáo trộn toàn mảng chỉ để chọn pivot ngẫu nhiên.

**Cần phân biệt ngẫu nhiên giả và ngẫu nhiên thật:** `java.util.Random` là bộ sinh số **giả ngẫu nhiên** có trạng thái. Với cùng seed và cùng chuỗi lệnh gọi, lựa chọn có thể được tái tạo để kiểm thử. Bảo đảm kỳ vọng của thuật toán được phát biểu trong **mô hình phân tích** xem mỗi lần pivot được chọn đều, đủ độc lập với dữ liệu và lịch sử cần thiết. Seed cố định giúp tái lập thí nghiệm nhưng không biến một lần chạy thành bảo đảm trường hợp xấu nhất, cũng không cung cấp tính khó dự đoán cho mục đích bảo mật.

## 4. Phân hoạch ba hướng để xử lý phần tử trùng

Phép phân hoạch **Dutch National Flag** dùng ba chỉ số `lt`, `i`, `gt` trên đoạn `[lo,hi]`, duy trì bốn vùng:

| Vùng | Bất biến |
| --- | --- |
| `[lo, lt)` | Mọi phần tử nhỏ hơn pivot. |
| `[lt, i)` | Mọi phần tử bằng pivot. |
| `[i, gt]` | Chưa phân loại. |
| `(gt, hi]` | Mọi phần tử lớn hơn pivot. |

Giả mã:

```text
ALGORITHM PARTITION_THREE_WAY(A, lo, hi, pivot)
    lt <- lo
    i <- lo
    gt <- hi

    WHILE i <= gt DO
        IF A[i] < pivot THEN
            SWAP(A[lt], A[i])
            lt <- lt + 1
            i <- i + 1
        ELSE IF A[i] > pivot THEN
            SWAP(A[i], A[gt])
            gt <- gt - 1
        ELSE
            i <- i + 1
        END IF
    END WHILE

    RETURN (lt, gt)
END ALGORITHM
```

Hai cận trả về **bao gồm** vùng bằng pivot, tức `A[lt..gt]` đều bằng pivot. Khi `A[i] > pivot`, không tăng `i` vì phần tử từ `A[gt]` vừa đổi đến `i` chưa được kiểm tra. Ngược lại, khi `A[i] < pivot`, phần tử đi từ `lt` sang `i` (nếu `lt<i`) thuộc vùng bằng pivot đã biết, nên có thể tăng cả hai con trỏ.

**Bất biến** được duy trì sau mỗi nhánh; khi `i>gt`, vùng chưa phân loại rỗng nên ba vùng đúng. Mỗi vòng hoặc tăng `i`, hoặc giảm `gt`, khiến số phần tử chưa phân loại giảm một, do vậy phép phân hoạch chắc chắn kết thúc. Với đoạn dài `m`, chi phí **O(m) thời gian và O(1) bộ nhớ phụ**.

So với phân hoạch hai hướng chỉ tách `< pivot` và `>= pivot`, ba hướng đặc biệt có ích khi có nhiều giá trị **bằng pivot**: vùng bằng pivot có thể được bỏ qua hoàn toàn khi chọn thứ hạng hoặc tiếp tục sắp xếp. Nếu toàn mảng cùng một giá trị, một lần phân hoạch đủ kết thúc Quickselect và Quicksort ba hướng.

## 5. Randomized Quickselect: chọn phần tử nhỏ thứ k

**Bài toán:** cho mảng số nguyên `A` dài `n>0` và thứ hạng **`k` tính từ 0**, tìm giá trị sẽ nằm tại chỉ số `k` nếu toàn mảng được sắp **không giảm**. Ví dụ, phần tử có `k=0` là giá trị nhỏ nhất; `k=n-1` là giá trị lớn nhất. Khi có giá trị trùng, nhiều thứ hạng có thể trả cùng một giá trị; mục tiêu là **giá trị**, không phải danh tính của một bản ghi gốc.

Không cần sắp toàn bộ mảng. Với đoạn đang xét `[lo,hi]`, chọn pivot ngẫu nhiên và phân hoạch ba hướng nhận `[lt,gt]`:

- Nếu `k < lt`, chỉ cần xử lý đoạn **`[lo, lt-1]`**.
- Nếu `lt <= k <= gt`, kết quả là **pivot**; tất cả phần tử ở vị trí thứ hạng này đều có giá trị pivot.
- Nếu `k > gt`, chỉ cần xử lý đoạn **`[gt+1, hi]`**.

```text
ALGORITHM RANDOMIZED_QUICKSELECT(A, k)
    REQUIRE 0 <= k < LENGTH(A)
    lo <- 0
    hi <- LENGTH(A) - 1

    LOOP
        r <- RANDOM_INTEGER_UNIFORMLY(lo, hi)
        pivot <- A[r]
        (lt, gt) <- PARTITION_THREE_WAY(A, lo, hi, pivot)

        IF k < lt THEN
            hi <- lt - 1
        ELSE IF k > gt THEN
            lo <- gt + 1
        ELSE
            RETURN pivot
        END IF
    END LOOP
END ALGORITHM
```

**Bất biến chọn thứ hạng:** kết quả có thứ hạng toàn cục `k` vẫn nằm trong **đoạn hiện tại**, còn các phần tử ngoài đoạn đã được phân tách theo quan hệ nhỏ hơn/lớn hơn trong những lần phân hoạch trước. Vì vậy, không cần trừ lại `k` khi giữ chỉ số tuyệt đối của mảng; nếu đổi sang chỉ số **tương đối** của đoạn con mới, lại phải cập nhật `k` tương ứng.

**Tính đúng:** phân hoạch đặt mọi phần tử nhỏ hơn pivot trước vùng bằng pivot và mọi phần tử lớn hơn phía sau. Nếu `k` rơi vào vùng bằng, giá trị pivot là đúng theo thứ hạng. Nếu ngoài vùng bằng, thứ hạng ấy chỉ có thể thuộc đúng một vùng còn lại. Lặp lại đến khi tìm thấy.

**Tính kết thúc:** mỗi lần phân hoạch đưa ít nhất một phần tử vào vùng bằng pivot, rồi hoặc trả kết quả hoặc thu hẹp đoạn một cách nghiêm ngặt. Vì đoạn chỉ có hữu hạn phần tử, thuật toán kết thúc với mọi chuỗi pivot hợp lệ, **kể cả khi pivot liên tục rất xấu**; ngẫu nhiên hóa quyết định chi phí, không quyết định khả năng kết thúc.

## 6. Vì sao Quickselect có O(n) thời gian kỳ vọng?

Hãy cố định trước một đầu vào có `n` khóa phân biệt và một thứ hạng đích. Xét kỳ vọng theo **các lựa chọn pivot ngẫu nhiên của chính thuật toán**, chứ **không cần** giả định đầu vào là một mảng ngẫu nhiên.

Một lần phân hoạch đoạn dài `m` mất O(m). Nếu pivot có thứ hạng nằm trong **nửa giữa** của đoạn (từ khoảng 25% đến 75%), thì dù thứ hạng cần tìm nằm bên nào, đoạn còn lại có kích thước tối đa khoảng `3m/4`. Vì pivot được chọn đều, xác suất một pivot như vậy là một **hằng số dương**, xấp xỉ 1/2 (bỏ qua sai khác làm tròn cho m nhỏ).

Có thể xem một số pivot liên tiếp là các “lần thử” để gặp pivot đủ cân bằng. Số lần thử kỳ vọng đến khi có pivot tốt là một hằng số, trong khi mỗi lần thử trên đoạn kích thước `m` chỉ tốn O(m). Sau một pivot tốt, kích thước giảm theo hệ số không đổi. Bởi vậy có thể chặn tổng kỳ vọng bằng một chuỗi hình học:

```text
E[T(n)] <= C*n + C*(3n/4) + C*(3n/4)^2 + ...
         = O(n)
```

Dòng trên là **ý tưởng lập luận theo các pha**, không phải lịch kích thước của mọi lần chạy riêng lẻ; hằng số `C` hấp thụ chi phí kỳ vọng của các lần thử trong mỗi pha.

**Kết luận phân tích:**

- **Thời gian kỳ vọng của randomized Quickselect:** **O(n)** so sánh/xử lý với các phép toán khóa O(1) và pivot chọn đều.
- **Trường hợp xấu nhất:** **Θ(n²)** nếu liên tục chọn những pivot cực đoan, khiến đoạn giảm một phần tử mỗi lần.
- **Bộ nhớ phụ:** bản **lặp tại chỗ** chỉ cần O(1) biến/chỉ số cùng trạng thái RNG kích thước cố định, không cần ngăn xếp đệ quy.
- **Không có mâu thuẫn với cận dưới Ω(n log n) cho sắp xếp so sánh:** Quickselect chỉ chọn **một thứ hạng**, không tạo ra thứ tự đầy đủ của `n` phần tử.

Tính ngẫu nhiên giúp tránh việc **một thứ tự đầu vào cố định** luôn đánh bại chiến lược chọn pivot cố định, nhưng không xóa khả năng rơi vào chuỗi lựa chọn bất lợi.

## 7. Randomized Quicksort: kỳ vọng O(n log n)

Quicksort khác Quickselect ở chỗ sau phân hoạch phải sắp **cả hai vùng ngoài vùng bằng pivot**.

```text
ALGORITHM RANDOMIZED_QUICKSORT(A, lo, hi)
    IF lo >= hi THEN
        RETURN
    END IF

    r <- RANDOM_INTEGER_UNIFORMLY(lo, hi)
    pivot <- A[r]
    (lt, gt) <- PARTITION_THREE_WAY(A, lo, hi, pivot)

    RANDOMIZED_QUICKSORT(A, lo, lt - 1)
    RANDOMIZED_QUICKSORT(A, gt + 1, hi)
END ALGORITHM
```

**Tính đúng:** vùng bằng pivot đã ở giữa hai vùng có khóa nhỏ hơn và lớn hơn. Nếu hai vùng ngoài được sắp đúng, toàn bộ đoạn sẽ không giảm. Chứng minh quy nạp theo chiều dài đoạn; mỗi lời gọi con xử lý ít phần tử hơn đoạn cha. Không cần sắp lại vùng bằng pivot.

**Bảo đảm theo kỳ vọng với các khóa phân biệt:** nếu pivot có thứ hạng `j` được chọn đều trong `0..n-1`, hai đoạn con có kích thước `j` và `n-1-j`. Trong một mô hình chi phí so sánh phù hợp:

```text
E[T(n)] =
    O(n) + (1/n) * SUM(j = 0..n-1) [
        E[T(j)] + E[T(n-1-j)]
    ]

Suy ra: E[T(n)] = O(n log n).
```

Dữ liệu nhiều khóa trùng thường được xử lý hiệu quả hơn bằng phân hoạch ba hướng vì nhóm bằng pivot không cần đi vào các lời gọi tiếp theo. Trường hợp **tất cả khóa bằng nhau**, phép phân hoạch ba hướng kết thúc sau một lần quét O(n), thay vì sinh những bài toán con lớn chứa toàn khóa bằng nhau.

**Trường hợp xấu nhất vẫn Θ(n²)** khi pivot liên tục chia rất lệch trên dữ liệu có nhiều khóa phân biệt. Trong phiên bản đệ quy ngây thơ, ngăn xếp có thể sâu O(n). Có thể giảm độ sâu stack xuống O(log n) **ngay cả trong trường hợp xấu nhất về chuỗi pivot** bằng cách luôn **đệ quy xử lý nhánh nhỏ hơn trước** và dùng vòng lặp để xử lý nhánh lớn hơn; chương trình Java bên dưới áp dụng kỹ thuật đó. Nó bảo đảm **bộ nhớ stack O(log n)**, không biến thời gian xấu nhất O(n²) thành O(n log n).

### Kỳ vọng không đồng nghĩa với bảo đảm trường hợp xấu nhất

| Thuật toán và cách chọn pivot | Thời gian kỳ vọng với giả định ngẫu nhiên đúng | Thời gian trường hợp xấu nhất |
| --- | --- | --- |
| Quickselect, pivot đều ngẫu nhiên | O(n) | Θ(n²) |
| Quicksort, pivot đều ngẫu nhiên | O(n log n) | Θ(n²) |
| Quicksort pivot cố định đầu/cuối | Không có bảo đảm từ ngẫu nhiên hóa | Θ(n²) trên dữ liệu bất lợi |
| Phân hoạch ba hướng của một đoạn | O(m) cho mỗi lần xử lý đoạn dài m | O(m) |

**Thời gian kỳ vọng** là trung bình theo phân phối các lần rút pivot giả định, cho đầu vào đã cố định. Nó **không có nghĩa** kết quả từng lần chạy bị chặn bằng số đó. Nếu cần bảo đảm tệ nhất cho lựa chọn theo thứ hạng, có thuật toán chọn pivot xác định như **median of medians (BFPRT)** với O(n) trường hợp xấu nhất trong mô hình so sánh; đổi lại độ phức tạp triển khai và hằng số thực tế có thể lớn hơn. Với sắp xếp, một chiến lược kiểu **introsort** có thể chuyển sang heap sort khi phân hoạch quá sâu để tránh O(n²) trong trường hợp xấu nhất.

## 8. Java 17+: Quickselect và Quicksort chọn pivot ngẫu nhiên

Chương trình sau chứa **cài đặt đầy đủ** của hai thuật toán. Nó dùng `java.util.Random` được truyền vào, giúp người gọi chọn seed để kiểm thử tái lập. Kết quả in ra chỉ là **giá trị thứ hạng và dãy đã sắp**, nên chính xác không phụ thuộc pivot cụ thể đã được rút trong quá trình chạy.

- `kthSmallestInPlace` trả giá trị ở thứ hạng 0-based và **có thể đổi thứ tự mảng đầu vào**.
- `randomizedQuickSort` sắp xếp mảng đầu vào **không giảm**.
- `partition3` dùng ba vùng `<`, `=`, `>` và trả về hai cận **bao gồm** vùng bằng.
- `quickSortRange` đệ quy trên đoạn **nhỏ hơn**, lặp trên đoạn **lớn hơn**, giới hạn độ sâu stack.

Tạo tệp **`RandomPivotDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;
import java.util.Random;

public class RandomPivotDemo {
    record Band(int lt, int gt) {}

    private static void swap(int[] a, int i, int j) {
        int temp = a[i];
        a[i] = a[j];
        a[j] = temp;
    }

    private static Band partition3(int[] a, int lo, int hi, int pivot) {
        int lt = lo;
        int i = lo;
        int gt = hi;

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

        return new Band(lt, gt);
    }

    public static int kthSmallestInPlace(int[] a, int k, Random random) {
        Objects.requireNonNull(a, "array");
        Objects.requireNonNull(random, "random");
        if (k < 0 || k >= a.length) {
            throw new IllegalArgumentException("k must be in 0..n-1");
        }

        int lo = 0;
        int hi = a.length - 1;

        while (lo <= hi) {
            int pivotIndex = lo + random.nextInt(hi - lo + 1);
            int pivot = a[pivotIndex];
            Band equal = partition3(a, lo, hi, pivot);

            if (k < equal.lt()) {
                hi = equal.lt() - 1;
            } else if (k > equal.gt()) {
                lo = equal.gt() + 1;
            } else {
                return pivot;
            }
        }

        throw new AssertionError("Valid rank must be found");
    }

    public static void randomizedQuickSort(int[] a, Random random) {
        Objects.requireNonNull(a, "array");
        Objects.requireNonNull(random, "random");
        quickSortRange(a, 0, a.length - 1, random);
    }

    private static void quickSortRange(
            int[] a, int lo, int hi, Random random) {
        while (lo < hi) {
            int pivotIndex = lo + random.nextInt(hi - lo + 1);
            int pivot = a[pivotIndex];
            Band equal = partition3(a, lo, hi, pivot);

            int leftSize = equal.lt() - lo;
            int rightSize = hi - equal.gt();

            if (leftSize < rightSize) {
                // Đệ quy nhánh nhỏ, lặp nhánh lớn.
                quickSortRange(a, lo, equal.lt() - 1, random);
                lo = equal.gt() + 1;
            } else {
                quickSortRange(a, equal.gt() + 1, hi, random);
                hi = equal.lt() - 1;
            }
        }
    }

    public static void main(String[] args) {
        int[] original = {8, 2, 4, 4, 9, 1, 6};

        System.out.println("k0=" + kthSmallestInPlace(
                original.clone(), 0, new Random(1)));
        System.out.println("k3=" + kthSmallestInPlace(
                original.clone(), 3, new Random(2)));
        System.out.println("k6=" + kthSmallestInPlace(
                original.clone(), 6, new Random(3)));

        int[] sorted = original.clone();
        randomizedQuickSort(sorted, new Random(4));
        System.out.println("sorted=" + Arrays.toString(sorted));

        int[] allEqual = {5, 5, 5, 5, 5};
        System.out.println("allEqual=" + kthSmallestInPlace(
                allEqual, 2, new Random(5)));

        int[] signed = {-2, -8, 0, -2, 6};
        System.out.println("signedK2=" + kthSmallestInPlace(
                signed, 2, new Random(6)));

        int[] empty = {};
        randomizedQuickSort(empty, new Random(7));
        System.out.println("empty=" + Arrays.toString(empty));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac RandomPivotDemo.java
java RandomPivotDemo
```

Đầu ra chính xác:

```text
k0=1
k3=4
k6=9
sorted=[1, 2, 4, 4, 6, 8, 9]
allEqual=5
signedK2=-2
empty=[]
```

**Vì sao đầu ra xác định?** Mỗi lời gọi Quickselect trả giá trị ở một thứ hạng xác định theo toán học; bất kể chọn pivot nào hợp lệ, giá trị ấy giống nhau. Quicksort tạo mảng sắp không giảm nên dãy số nguyên hiển thị cũng xác định. Các seed 1–7 chỉ giúp tái lập chuỗi pivot khi gỡ lỗi; ta không in thứ tự pivot hay số lần so sánh vốn có thể thay đổi nếu đổi seed.

**Độ phức tạp bộ nhớ:**

- `kthSmallestInPlace` lặp trực tiếp trên mảng: **O(1)** bộ nhớ phụ đồng thời, không tính mảng do người gọi truyền vào.
- `randomizedQuickSort` dùng **O(log n)** stack trong trường hợp xấu nhất nhờ đệ quy chỉ trên nhánh nhỏ hơn; một `Band` kích thước cố định cho mỗi tầng không làm đổi bậc.
- Các lời gọi **`original.clone()` ở `main`** tạo mảng sao chép O(n) để minh họa các lần thử độc lập; đây là chi phí của **chương trình kiểm thử**, không thuộc thân hai thuật toán sắp/chọn. Nếu cần bảo toàn input trong ứng dụng, sao chép mảng cũng có chi phí O(n).
- Bản Quicksort này dùng hoán đổi nên **không ổn định** đối với các bản ghi có khóa bằng nhau, dù sắp các số nguyên vẫn cho kết quả không giảm.

**Các trường hợp biên:** `randomizedQuickSort` chấp nhận mảng rỗng/một phần tử. `kthSmallestInPlace` yêu cầu `n>0` và `0≤k<n`, nên mảng rỗng hoặc thứ hạng ngoài miền bị báo lỗi. Cả hai yêu cầu mảng và đối tượng `Random` khác `null`.

## 9. Tính ngẫu nhiên, dữ liệu đối kháng và độ tin cậy

**Đầu vào cố định trước khi bốc pivot:** bảo đảm kỳ vọng không yêu cầu dữ liệu đầu vào có phân phối ngẫu nhiên. Với một mảng cố định bất kỳ, miễn các vị trí pivot được chọn đều theo mô hình phân tích, pivot trung tâm có xác suất đủ lớn giúp tránh chuỗi tệ một cách **trung bình qua các lần chạy**.

**Người tấn công thích nghi:** nếu bên ngoài có thể biết hoặc tác động trực tiếp đến trạng thái sinh số ngẫu nhiên, thậm chí sắp xếp/chọn dữ liệu tương ứng với các pivot sắp được chọn, giả định **rút pivot độc lập với đầu vào** không còn phù hợp. Một PRNG với seed cố định không phải cơ chế bảo vệ chống đầu vào cố ý gây tốn tài nguyên.

**Xáo trộn không đều:** chọn `r` theo quy tắc thiên lệch, chẳng hạn chỉ chọn từ vài vị trí đầu, hoặc sử dụng modulo một cách sơ sài khiến một số vị trí xuất hiện nhiều hơn, có thể làm phân tích xác suất không còn đúng như giả thiết. Với Java, dùng API `nextInt(bound)` hoặc API số nguyên ngẫu nhiên giới hạn tương ứng thay vì tự viết phép chọn vị trí thiếu kiểm chứng.

**Trường hợp xấu vẫn tồn tại:** với khóa phân biệt, xác suất gặp nhiều pivot cực đoan liên tiếp nhỏ trong mô hình rút đều, nhưng không bằng 0. Nếu ứng dụng đòi hỏi **giới hạn thời gian tệ nhất** hoặc tránh một truy vấn chiếm tài nguyên quá lâu, có thể kết hợp giới hạn độ sâu/thời gian và một thuật toán dự phòng phù hợp. Bảo đảm kỳ vọng là một thuộc tính phân tích, không phải thay thế cho kiểm soát tài nguyên.

### So sánh chiến lược chọn pivot

| Chiến lược | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Đầu hoặc cuối đoạn | Đơn giản, không cần sinh số ngẫu nhiên | Dễ gặp chia lệch trên một số thứ tự đầu vào. |
| Vị trí giữa | Chi phí chọn thấp | Vị trí giữa không có nghĩa giá trị là trung vị; vẫn có dữ liệu bất lợi. |
| Median-of-three | Giảm một số trường hợp lệch bằng cách chọn trung vị của ba mẫu | Vẫn là heuristic, không bảo đảm pivot cân bằng cho mọi mảng. |
| **Chỉ số ngẫu nhiên đều** | Đạt phân tích kỳ vọng cho từng đầu vào cố định dưới giả định ngẫu nhiên phù hợp | Tốn chi phí RNG và vẫn có worst-case O(n²). |
| Median-of-medians | Có thể cung cấp chọn thứ hạng O(n) trong trường hợp xấu nhất | Cài đặt và hằng số thực tế phức tạp hơn. |

Không có một chiến lược pivot duy nhất luôn tốt nhất cho mọi ràng buộc. Với nhiều bản ghi trùng, **cách phân hoạch** quan trọng không kém cách chọn pivot; lựa chọn một pivot ngẫu nhiên nhưng vẫn tách đôi theo cách không xử lý khóa bằng nhau tốt có thể gây công việc thừa.

## 10. Cách kiểm chứng tính đúng và đo hiệu năng

Khi viết Quickselect/Quicksort ngẫu nhiên, nên kiểm tra **hai loại thuộc tính độc lập**:

1. **Kết quả luôn đúng**, bất kể pivot nào được chọn: phân hoạch bảo toàn tất cả giá trị và thứ tự giữa ba vùng, trả đúng thứ hạng hoặc sắp đúng.
2. **Chi phí theo phân phối lựa chọn pivot:** số lần so sánh, tổng độ dài đoạn được phân hoạch, chiều sâu xử lý; chạy nhiều seed trên cùng một đầu vào để quan sát, không dùng một lần chạy để “chứng minh” độ phức tạp kỳ vọng.

Các bộ thử đáng có:

| Kiểu đầu vào | Mục tiêu kiểm thử |
| --- | --- |
| Mảng rỗng, một phần tử | Hành vi đặc tả; quickselect phải từ chối k không hợp lệ. |
| Tăng dần, giảm dần | Tránh phụ thuộc pivot cố định bất lợi; luôn trả đúng giá trị. |
| Tất cả bằng nhau | Phân hoạch ba hướng gom toàn bộ nhóm bằng pivot và kết thúc nhanh. |
| Nhiều phần tử trùng | Rank trong đoạn bằng pivot phải trả đúng, không phân hoạch lại nhóm bằng. |
| Số âm, số 0, số dương | So sánh theo giá trị nguyên đúng, không dùng giả định số dương. |
| k=0 và k=n−1 | Chọn min/max đúng; không lỗi lệch một chỉ số. |
| Mảng lớn, nhiều seed | Quan sát phân phối chi phí, lỗi tràn chỉ số/cận và độ sâu stack. |

Để tự kiểm tra kết quả Quickselect cho một mảng có thể sao chép, tạo một bản sao rồi dùng `Arrays.sort` trên bản sao và so sánh giá trị `k` với kết quả `kthSmallestInPlace`. Đây là **bộ kiểm thử tham chiếu**, không phải thuật toán chọn nhanh trong bài toán gốc.

Nếu đo số lần so sánh, phải chỉ rõ đo trong **phân hoạch**, không trộn chi phí sao chép dữ liệu, tạo RNG và in log; nhiều lần chạy với seed khác nhau mới cho thông tin về phân phối chi phí thực nghiệm. Kết quả đo không thay thế chứng minh kỳ vọng.

## 11. Lỗi phổ biến khi phân tích và cài đặt

1. **Nhầm kỳ vọng với worst-case:** O(n) kỳ vọng không có nghĩa mọi lần Quickselect tốn tối đa c·n.
2. **Nhầm xác suất đến từ đầu vào:** thuật toán ngẫu nhiên hóa có bảo đảm kỳ vọng cho **đầu vào cố định** theo các lần chọn pivot của nó, không cần mảng đầu vào được tạo ngẫu nhiên.
3. **Chỉ chọn pivot đầu và gọi là randomized:** một thuật toán không có lựa chọn ngẫu nhiên hợp lệ thì không thể dựa vào chứng minh randomized pivot.
4. **Chọn pivot ngoài đoạn đang xét:** phải rút chỉ số trong `[lo,hi]`, không phải từ toàn mảng ở mỗi lượt.
5. **Quên xử lý khóa bằng nhau:** phân hoạch hai hướng có thể tiếp tục xử lý rất nhiều giá trị bằng pivot; ba hướng giúp loại cả vùng bằng.
6. **Trong Quickselect, cập nhật `k` sai:** khi dùng chỉ số tuyệt đối không được tùy tiện trừ `lo`; khi chuyển sang chỉ số tương đối phải cập nhật đúng.
7. **Trong ba hướng, tăng `i` sau khi đổi với `gt`:** giá trị vừa chuyển đến chưa được kiểm tra, có thể để sai nhóm.
8. **Bỏ mất phần tử khi swap:** dùng hoán đổi đúng với biến tạm, không ghi đè dữ liệu trước khi lưu.
9. **Suy ra Quicksort ổn định:** bản hoán đổi ba hướng thông thường không giữ thứ tự tương đối của bản ghi bằng khóa.
10. **Quên stack đệ quy:** một Quicksort phân hoạch tại chỗ vẫn có thể tốn nhiều bộ nhớ do đệ quy; chương trình minh họa xử lý nhánh nhỏ để hạn chế stack.
11. **Sao chép input nhưng công bố O(1) bộ nhớ tổng:** bản sao `clone()` dài `n` vẫn là O(n) nếu được tính cho toàn quy trình.
12. **Tin rằng seed cố định là bảo đảm chống dữ liệu đối kháng:** PRNG tái lập được có ích cho kiểm thử nhưng không khiến thời gian worst-case biến mất.
13. **Đưa giá trị trùng vào công thức các khóa phân biệt mà không xét lại:** chứng minh trực giác dựa trên thứ hạng phân biệt cần điều chỉnh khi có nhiều khóa bằng nhau; dùng ba hướng để xử lý đúng vùng bằng.
14. **Đo một lần chạy rồi tuyên bố đã chứng minh kỳ vọng:** kỳ vọng là phát biểu toán học về các lựa chọn ngẫu nhiên, cần lập luận xác suất hoặc kiểm chứng thống kê được thiết kế cẩn thận.

## 12. Bài tập tự luyện có lời giải

**Bài 1.** Với mảng `[8,2,4,4,9,1,6]`, chọn `pivot=4`. Các nhóm sau phân hoạch ba hướng chứa những giá trị nào? **Đáp án:** nhóm nhỏ hơn `[2,1]`, nhóm bằng `[4,4]`, nhóm lớn hơn `[8,9,6]`, mỗi nhóm có thể có thứ tự nội bộ khác. Thứ hạng 2 và 3 đều trả giá trị 4.

**Bài 2.** Vì sao Quickselect chỉ đệ quy hoặc lặp tiếp một bên, trong khi Quicksort xử lý hai bên? **Đáp án:** Quickselect chỉ tìm một thứ hạng `k` nằm trong đúng một vùng hoặc vùng bằng pivot; Quicksort phải sắp mọi phần tử ở cả hai vùng còn lại.

**Bài 3.** Tại sao chọn pivot đầu trên một mảng tăng dần có thể làm Quickselect tìm giá trị lớn nhất tốn Θ(n²)? **Đáp án:** mỗi pivot là nhỏ nhất của đoạn hiện tại, chỉ loại một phần tử; tổng công việc `n+(n-1)+...+1=Θ(n²)`.

**Bài 4.** Nếu pivot được chọn đều và thuộc nửa giữa của thứ hạng với xác suất hằng, điều đó giúp gì? **Đáp án:** ở những lần như vậy, đoạn Quickselect còn lại tối đa khoảng 3/4 kích thước cũ; số lần thử kỳ vọng để có một pivot như thế là hằng, nên tổng kỳ vọng qua các mức giảm hình học là O(n).

**Bài 5.** Mảng `[5,5,5,5,5]`, chọn `k=2`: Quickselect ba hướng trả gì? **Đáp án:** 5. Vùng bằng pivot bao phủ cả mảng sau một lần phân hoạch O(n).

**Bài 6.** Quicksort ngẫu nhiên có bảo đảm O(n log n) thời gian với mọi chuỗi pivot không? **Đáp án:** không; bảo đảm ở đây là **kỳ vọng**. Một chuỗi pivot lệch cực đoan vẫn có thể dẫn tới Θ(n²).

**Bài 7.** Vì sao trong mã Java chọn nhánh nhỏ để đệ quy giúp O(log n) stack ngay cả khi hai nhánh mất cân bằng? **Đáp án:** mỗi lần **đệ quy**, nhánh được gọi có kích thước không vượt một nửa đoạn hiện tại; phần lớn hơn được xử lý bằng vòng lặp tại tầng hiện hữu. Số lần có thể lồng lời gọi như vậy bị chặn bởi O(log n).

**Bài 8.** Khi mảng đã có thứ tự tăng dần, ngẫu nhiên hóa pivot có cần **xáo trộn toàn bộ mảng** trước không? **Đáp án:** không. Rút chỉ số pivot đều trong **mỗi đoạn con** là một cách đủ để có mô hình lựa chọn pivot ngẫu nhiên.

**Bài 9.** Với `k=0` trên mảng `[-2,-8,0,-2,6]`, đáp án Quickselect là gì? **Đáp án:** `-8`. Với `k=2`, đáp án là `-2`, do dãy tăng dần là `[-8,-2,-2,0,6]`.

**Bài 10.** Nếu một ứng dụng cần **bảo đảm tệ nhất** O(n) để chọn một thứ hạng bất kỳ, randomized Quickselect trong bài đã đủ chưa? **Đáp án:** chưa; cần cơ chế chọn pivot có bảo đảm worst-case phù hợp, chẳng hạn median-of-medians, hoặc một chiến lược dự phòng đúng theo ràng buộc ứng dụng.

## 13. Checklist áp dụng vào bài chọn và thứ tự

Trước khi cài đặt, hãy trả lời:

1. **Đang chọn một thứ hạng hay sắp toàn bộ?** Quickselect và Quicksort chia sẻ partition nhưng lượng việc tiếp tục khác nhau.
2. **Thứ hạng bắt đầu ở 0 hay 1?** Xác định rõ miền hợp lệ của `k` và cách quy đổi.
3. **Pivot được chọn thế nào?** Khi dùng kỳ vọng, phải biết phân phối lựa chọn và giả định về dữ liệu/lịch sử.
4. **Có nhiều giá trị bằng nhau không?** Dùng phân hoạch ba hướng để giữ nhóm bằng rõ ràng.
5. **Bất biến có đúng không?** Vùng đã phân loại luôn thỏa quan hệ với pivot, thứ hạng đích vẫn thuộc đoạn được giữ, và các đoạn con nhỏ đi.
6. **Cần bảo đảm thời gian nào?** Kỳ vọng O(n)/O(n log n) khác với worst-case Θ(n²); cân nhắc fallback nếu giới hạn tệ nhất quan trọng.
7. **Bộ nhớ phụ và sửa input?** Kiểm tra stack, bản sao mảng và việc truyền bộ sinh số ngẫu nhiên.
8. **Kiểm thử đủ loại dữ liệu?** Rỗng, một phần tử, tất cả bằng nhau, đã sắp, đảo ngược, nhiều số trùng, số âm và những thứ hạng biên.

**Ghi nhớ:** pivot ngẫu nhiên không thay đổi **định nghĩa kết quả** của Quickselect/Quicksort; nó thay đổi **phân phối kích thước bài toán con**, nhờ đó có bảo đảm tốt **theo kỳ vọng** cho một đầu vào cố định. Một thuật toán tốt vẫn phải phân hoạch đúng, xử lý khóa trùng và nói rõ sự khác biệt giữa chi phí kỳ vọng và trường hợp xấu nhất.
