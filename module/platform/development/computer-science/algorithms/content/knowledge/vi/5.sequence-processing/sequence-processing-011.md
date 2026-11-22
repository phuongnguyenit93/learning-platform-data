# Phân hoạch dãy và gom nhóm tại chỗ

**Phân hoạch dãy (array partitioning)** là sắp xếp lại các phần tử sao cho chúng nằm trong những **vùng liên tiếp** thỏa một tiêu chí, chẳng hạn số chẵn đứng trước số lẻ, số nhỏ hơn một mốc đứng trước số lớn hơn hoặc bằng mốc, hay chia dữ liệu thành ba nhóm nhỏ hơn/bằng/lớn hơn giá trị chốt. Phân hoạch thường là một bước hỗ trợ bên trong thuật toán lớn hơn, ví dụ quicksort, quickselect và các bài toán lọc dữ liệu.

**Tại chỗ (in-place)** nghĩa là thuật toán thao tác trực tiếp trên dãy đầu vào và chỉ cần lượng **bộ nhớ phụ O(1)** trong các ví dụ của bài. Việc đổi chỗ phần tử có thể làm thay đổi thứ tự xuất hiện ban đầu; vì vậy phải phân biệt yêu cầu **phân nhóm** với yêu cầu **phân nhóm ổn định**.

## 1. Đặc tả chính xác của phân hoạch

Cho mảng `A` dài `n` và một điều kiện phân loại `P(x)` nhận kết quả đúng/sai. Bài toán **phân hoạch hai nhóm** yêu cầu tìm ranh giới `k` sao cho:

- Các phần tử trong đoạn chỉ số **`[0, k)`** đều thỏa `P`.
- Các phần tử trong đoạn **`[k, n)`** đều không thỏa `P`.
- Kết quả chứa **đúng các phần tử ban đầu, kể cả số lần trùng lặp**; thuật toán chỉ được đổi vị trí.
- Nếu yêu cầu in-place, các thao tác sắp xếp lại diễn ra trên chính mảng `A`, không tạo một mảng phụ có kích thước tăng theo `n`.

Quy ước đoạn **`[a, b)`** gồm chỉ số `a, a+1, ..., b-1`, không gồm `b`. Nhờ cách viết này, `k` vừa là vị trí bắt đầu nhóm thứ hai vừa là **số phần tử thuộc nhóm thứ nhất**.

Ví dụ, phân hoạch theo điều kiện `P(x) = x chẵn` với `A = [4, 5, 2, 1, 6, 3]` có thể cho `[4, 2, 6, 1, 5, 3]` và `k = 3`. Đầu ra này đúng vì ba giá trị đầu chẵn và ba giá trị sau lẻ. **Phân hoạch không yêu cầu mỗi nhóm phải được sắp xếp tăng dần.**

Hai mảng kết quả khác nhau vẫn có thể cùng thỏa đặc tả. Nếu bài toán còn yêu cầu **giữ thứ tự tương đối của các phần tử trong mỗi nhóm** thì phải ghi rõ tính ổn định (stability).

## 2. Kỹ thuật hai con trỏ (two pointers)

Một cách phân hoạch tại chỗ là giữ hai con trỏ `left` và `right` ở hai đầu **đoạn chưa phân loại**. Trong quá trình chạy, dãy được chia thành ba vùng:

| Vùng | Ý nghĩa |
| --- | --- |
| `A[0 .. left-1]` | Đã xác nhận thuộc nhóm thứ nhất, thỏa `P`. |
| `A[left .. right]` | Chưa phân loại, cần tiếp tục xử lý. |
| `A[right+1 .. n-1]` | Đã xác nhận thuộc nhóm thứ hai, không thỏa `P`. |

Các vùng rỗng là hợp lệ. Ban đầu `left = 0`, `right = n-1`: toàn mảng nằm trong vùng chưa phân loại.

Quy tắc xử lý:

1. Nếu `A[left]` thỏa `P`, giữ nguyên phần tử ở phía trái và tăng `left`.
2. Nếu `A[left]` không thỏa `P`, đổi chỗ `A[left]` với `A[right]`, sau đó giảm `right`. Phần tử không thỏa `P` đã được đưa vào vùng phải.
3. **Chưa tăng `left` ở bước 2**, vì phần tử vừa chuyển từ `right` sang `left` chưa được kiểm tra.
4. Dừng khi `left > right`; trả `left` làm ranh giới.

Giả mã:

```text
ALGORITHM PARTITION(A, P)
    left <- 0
    right <- LENGTH(A) - 1

    WHILE left <= right DO
        IF P(A[left]) THEN
            left <- left + 1
        ELSE
            SWAP(A[left], A[right])
            right <- right - 1
        END IF
    END WHILE

    RETURN left
END ALGORITHM
```

`P` trong giả mã là một phép kiểm tra xác định cho mỗi phần tử, không phải ký hiệu bắt buộc của Java. Điều kiện `left <= right` cho phép xử lý phần tử cuối cùng khi hai con trỏ gặp nhau, kể cả trường hợp nhóm thứ nhất hoặc thứ hai rỗng.

### Mô phỏng với số chẵn và số lẻ

Lấy `A = [4, 2, 5, 1, 6, 3]`, `P(x)` là “`x` chẵn”:

| Trạng thái | `left` | `right` | Hành động |
| --- | ---: | ---: | --- |
| `[4, 2, 5, 1, 6, 3]` | 0 | 5 | `4` chẵn: tăng `left` lên 1. |
| `[4, 2, 5, 1, 6, 3]` | 1 | 5 | `2` chẵn: tăng `left` lên 2. |
| `[4, 2, 5, 1, 6, 3]` | 2 | 5 | `5` lẻ: đổi `5` với `3`, giảm `right` xuống 4. |
| `[4, 2, 3, 1, 6, 5]` | 2 | 4 | `3` lẻ: đổi `3` với `6`, giảm `right` xuống 3. |
| `[4, 2, 6, 1, 3, 5]` | 2 | 3 | `6` chẵn: tăng `left` lên 3. |
| `[4, 2, 6, 1, 3, 5]` | 3 | 3 | `1` lẻ: đổi vị trí 3 với chính nó, giảm `right` xuống 2. |

Lúc này `left = 3 > right = 2`, trả `k = 3`. Mảng sau xử lý là **`[4, 2, 6, 1, 3, 5]`**. Việc đổi chỗ một phần tử với chính nó không làm dữ liệu sai; có thể tối ưu tránh thao tác này nhưng không cần thiết cho tính đúng đắn.

## 3. Vì sao hai con trỏ đúng và luôn kết thúc?

Một thuật toán phân hoạch phải bảo đảm hai đặc tính độc lập: **không đặt sai nhóm** và **không chạy vô hạn**.

**Bất biến vòng lặp:** trước mỗi lượt, tất cả phần tử thuộc `[0,left)` thỏa `P`, mọi phần tử thuộc `(right,n)` không thỏa `P`, còn đoạn `[left,right]` chưa được khẳng định.

- **Khởi tạo:** hai vùng đã phân loại đều rỗng nên bất biến đúng.
- **Duy trì:** nếu `P(A[left])` đúng, đưa phần tử đó vào vùng trái bằng cách tăng `left`. Nếu sai, đổi nó sang vị trí `right`; sau khi giảm `right`, vùng phải vừa mở rộng chứa một phần tử không thỏa `P`. Giá trị được đưa về `left` vẫn nằm trong vùng chưa phân loại và sẽ được kiểm tra sau.
- **Kết thúc:** khi `left > right`, vùng chưa phân loại rỗng. Hai vùng còn lại chính là phân hoạch thỏa đặc tả với ranh giới `k = left`.

Phép `SWAP` chỉ hoán đổi hai phần tử, nên **không làm mất, thêm hoặc nhân bản giá trị**. Đó là lý do đầu ra giữ đúng tập đa trị (multiset) của đầu vào.

Đặt số phần tử chưa phân loại là `U = max(0, right - left + 1)`. Mỗi lượt lặp hoặc tăng `left` một đơn vị, hoặc giảm `right` một đơn vị, nên khi còn phần tử, `U` giảm đúng một. Do `U` là số nguyên không âm, vòng lặp chắc chắn dừng. Với mảng dài `n`, vòng lặp thực hiện tối đa `n` lượt: **thời gian O(n)**, **bộ nhớ phụ O(1)**. Đổi chỗ phần tử chỉ cần một biến tạm.

## 4. Cài đặt Java 17+: phân hoạch hai nhóm và ba nhóm

Tạo tệp **`InPlacePartitionDemo.java`**. Chương trình có hai thuật toán: đặt số chẵn trước số lẻ và phân chia ba nhóm so với một giá trị chốt (pivot).

```java
import java.util.Arrays;

public class InPlacePartitionDemo {
    public static int evenFirst(int[] a) {
        if (a == null) {
            throw new IllegalArgumentException("a must not be null");
        }

        int left = 0;
        int right = a.length - 1;

        while (left <= right) {
            if ((a[left] & 1) == 0) {
                left++;
            } else {
                swap(a, left, right);
                right--;
            }
        }

        return left;
    }

    public static int[] threeWay(int[] a, int pivot) {
        if (a == null) {
            throw new IllegalArgumentException("a must not be null");
        }

        int lt = 0;
        int i = 0;
        int gt = a.length - 1;

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

        return new int[] {lt, gt + 1};
    }

    private static void swap(int[] a, int i, int j) {
        int temp = a[i];
        a[i] = a[j];
        a[j] = temp;
    }

    public static void main(String[] args) {
        int[] a = {4, 2, 5, 1, 6, 3};
        int k = evenFirst(a);
        System.out.println("evenSplit=" + k);
        System.out.println("evenGrouped=" + Arrays.toString(a));

        int[] b = {4, 2, 5, 2, 7, 2, 1};
        int[] bounds = threeWay(b, 2);
        System.out.println("threeWayBounds=" + Arrays.toString(bounds));
        System.out.println("threeWayGrouped=" + Arrays.toString(b));

        int[] c = {-3, -2, 0, 7, 4};
        int negativeSplit = evenFirst(c);
        System.out.println("negativeSplit=" + negativeSplit);
        System.out.println("negativeGrouped=" + Arrays.toString(c));
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac InPlacePartitionDemo.java
java InPlacePartitionDemo
```

Đầu ra xác định của chương trình:

```text
evenSplit=3
evenGrouped=[4, 2, 6, 1, 3, 5]
threeWayBounds=[1, 4]
threeWayGrouped=[1, 2, 2, 2, 7, 5, 4]
negativeSplit=3
negativeGrouped=[4, -2, 0, 7, -3]
```

**Giải thích về số âm:** điều kiện `(a[left] & 1) == 0` kiểm tra bit thấp nhất để phân biệt chẵn/lẻ với cả số âm và số không trong biểu diễn số nguyên Java. Dùng `x % 2 == 0` cũng kiểm tra chẵn đúng; riêng kiểm tra số lẻ bằng `x % 2 == 1` là **sai với số lẻ âm** trong Java, vì `-3 % 2 == -1`.

**Giải thích về ranh giới:** `evenFirst` trả vị trí bắt đầu của nhóm lẻ, đồng thời là số lượng số chẵn. `threeWay` trả mảng hai phần tử `{lt, gt+1}` để chỉ hai ranh giới giữa ba vùng. Mảng ranh giới có độ dài cố định là 2, nên vẫn chỉ cần O(1) bộ nhớ phụ.

Chương trình xử lý trực tiếp mảng đã được truyền vào. Người gọi quan sát được các phần tử bị đổi chỗ, ngay cả khi chỉ số ranh giới được trả về dưới dạng một giá trị riêng.

## 5. Phân hoạch ba hướng (Dutch National Flag)

Khi dữ liệu cần chia **ba nhóm**, ví dụ nhỏ hơn, bằng và lớn hơn một pivot, thuật toán ba hướng thường hiệu quả hơn việc chỉ phân tách hai nhóm rồi tiếp tục tìm những phần tử bằng pivot. Kỹ thuật này còn được biết đến với tên **Dutch National Flag**.

Với `pivot`, đặc tả kết quả gồm ba đoạn liên tiếp:

- `A[0 .. lt-1]`: mọi giá trị **`< pivot`**.
- `A[lt .. gt]`: mọi giá trị **`== pivot`**.
- `A[gt+1 .. n-1]`: mọi giá trị **`> pivot`**.

Trong quá trình chạy, dùng ba chỉ số `lt`, `i`, `gt` để duy trì bốn vùng:

| Vùng trong khi chạy | Bất biến |
| --- | --- |
| `[0, lt)` | Đã phân loại: nhỏ hơn pivot. |
| `[lt, i)` | Đã phân loại: bằng pivot. |
| `[i, gt]` | Chưa phân loại. |
| `(gt, n)` | Đã phân loại: lớn hơn pivot. |

Giả mã:

```text
ALGORITHM THREE_WAY_PARTITION(A, pivot)
    lt <- 0
    i <- 0
    gt <- LENGTH(A) - 1

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

    RETURN (lt, gt + 1)
END ALGORITHM
```

**Vì sao ở nhánh lớn hơn pivot không tăng `i`?** Phần tử đổi từ `A[gt]` sang `A[i]` chưa được kiểm tra. Nếu tăng `i` ngay, ta có thể bỏ sót một phần tử chưa phân loại. Ngược lại, trong nhánh nhỏ hơn pivot, giá trị đổi từ `A[lt]` (nếu `lt < i`) thuộc nhóm bằng pivot, nên sau khi tăng cả `lt` và `i`, hai vùng đã phân loại vẫn đúng.

Với `A = [4, 2, 5, 2, 7, 2, 1]` và `pivot = 2`, mảng có thể biến đổi:

```text
Ban đầu:       [4, 2, 5, 2, 7, 2, 1]
4 > 2:         [1, 2, 5, 2, 7, 2, 4]
1 < 2:         [1, 2, 5, 2, 7, 2, 4]
2 = 2:         [1, 2, 5, 2, 7, 2, 4]
5 > 2:         [1, 2, 2, 2, 7, 5, 4]
2 = 2:         [1, 2, 2, 2, 7, 5, 4]
2 = 2:         [1, 2, 2, 2, 7, 5, 4]
7 > 2:         [1, 2, 2, 2, 7, 5, 4]
Kết quả:       [1, 2, 2, 2, 7, 5, 4]
Ranh giới:     [1, 4]
```

Hai ranh giới trả về là **`[1, 4]`**; các đoạn là `[0,1)` nhỏ hơn 2, `[1,4)` bằng 2 và `[4,7)` lớn hơn 2. Một nhóm có thể rỗng, ví dụ không có phần tử bằng pivot thì hai ranh giới bằng nhau.

**Chứng minh kết thúc:** số phần tử chưa phân loại là `gt - i + 1` khi `i ≤ gt`. Mỗi lượt hoặc tăng `i`, hoặc giảm `gt`, nên độ dài vùng chưa biết giảm một. Vì vậy thời gian là **O(n)** trong trường hợp xấu nhất với phép so sánh/đổi chỗ hằng số, và bộ nhớ phụ **O(1)**.

Phân hoạch ba hướng **không sắp xếp tăng dần** các phần tử trong từng nhóm. Nó hữu ích khi dữ liệu có nhiều giá trị trùng pivot, chẳng hạn một bước chia vùng trong quicksort ba hướng, nhưng không nên nhầm kết quả phân hoạch với mảng đã sắp xếp.

## 6. Tại chỗ và ổn định là hai yêu cầu khác nhau

**Phân hoạch ổn định (stable partition)** giữ nguyên thứ tự tương đối ban đầu của các phần tử trong **cùng một nhóm**.

Ví dụ, phân nhóm chẵn trước lẻ trên `[5, 2, 3, 4, 1]`:

- Đầu vào có nhóm chẵn xuất hiện lần lượt là `[2, 4]` và nhóm lẻ là `[5, 3, 1]`.
- Kết quả ổn định phải có thứ tự các nhóm đúng như thế, tức **`[2, 4, 5, 3, 1]`**.
- Kỹ thuật đổi chỗ hai đầu ở mục 2 **không cam kết** giữ thứ tự bên trong mỗi nhóm, mặc dù vẫn phân hoạch đúng.

Một cách phân hoạch ổn định đơn giản là quét mảng và ghi phần tử thỏa điều kiện vào mảng phụ trước, rồi ghi các phần tử còn lại sau. Cách này dễ đạt **O(n)** thời gian nhưng sử dụng **O(n)** bộ nhớ phụ, nên không phải in-place theo nghĩa bộ nhớ phụ O(1).

Vẫn có cách phân hoạch **vừa ổn định vừa tại chỗ** với thuật toán đơn giản, nhưng thường phải đánh đổi thời gian. Ví dụ, quét từ trái sang phải; khi gặp phần tử chẵn, **dịch phải toàn bộ đoạn phần tử lẻ đã thấy** một vị trí để chèn phần tử chẵn vào ranh giới. Giả mã:

```text
ALGORITHM STABLE_EVEN_FIRST_IN_PLACE(A)
    boundary <- 0

    FOR i FROM 0 TO LENGTH(A) - 1 DO
        IF IS_EVEN(A[i]) THEN
            chosen <- A[i]
            j <- i

            WHILE j > boundary DO
                A[j] <- A[j - 1]
                j <- j - 1
            END WHILE

            A[boundary] <- chosen
            boundary <- boundary + 1
        END IF
    END FOR

    RETURN boundary
END ALGORITHM
```

Dịch chuyển chỉ tác động đến đoạn đã quét, nên thứ tự các phần tử lẻ vẫn giữ, còn các phần tử chẵn được chèn theo đúng thứ tự xuất hiện. Thuật toán dùng **O(1)** bộ nhớ phụ nhưng trong trường hợp nhiều phần tử chẵn phải vượt qua nhiều phần tử lẻ, tổng số lần dịch chuyển có thể là **O(n²)**.

Không nên kết luận phân hoạch ổn định in-place luôn bắt buộc O(n²): có những thuật toán tinh vi hơn. Điều cần nhớ là **không thể mặc nhiên gán tính ổn định cho thuật toán hoán đổi hai đầu O(n)**; yêu cầu ổn định phải được xét riêng khi chọn hoặc thiết kế thuật toán.

## 7. Một số trường hợp biên cần kiểm tra

| Trường hợp | Kỳ vọng phân hoạch chẵn–lẻ | Ranh giới `k` |
| --- | --- | ---: |
| `[]` | Mảng vẫn rỗng. | 0 |
| `[2, 4]` | Tất cả phần tử nằm nhóm chẵn. | 2 |
| `[1, 3]` | Tất cả phần tử nằm nhóm lẻ (thứ tự có thể thay đổi). | 0 |
| `[0]` | Số 0 là chẵn. | 1 |
| `[-3, -2, 0, 7, 4]` | Ba số chẵn `-2,0,4` được đưa lên đầu. | 3 |
| `[5]` | Một số lẻ; nhóm chẵn rỗng. | 0 |

Trong ba hướng, phải kiểm tra ít nhất: mảng rỗng, mọi phần tử `< pivot`, mọi phần tử `== pivot`, mọi phần tử `> pivot`, các giá trị trùng lặp và pivot không xuất hiện trong mảng. Trả về ranh giới phải nhất quán dù một hoặc hai nhóm rỗng.

Nếu một thuật toán dùng chỉ số cuối **bao gồm** phần tử (inclusive), còn thuật toán khác dùng cận cuối **loại trừ** (exclusive), việc chuyển đổi không cẩn thận dễ làm sai một phần tử. Trong bài, các khoảng kết quả đều dùng dạng `[start,end)` để giảm nhầm lẫn.

## 8. Khi nào áp dụng cách nào?

| Bài toán | Cách tiếp cận | Ưu điểm, giới hạn |
| --- | --- | --- |
| Chia hai nhóm theo `P(x)` và không cần giữ thứ tự | Hai con trỏ với đoạn chưa phân loại | O(n) thời gian, O(1) bộ nhớ phụ. |
| Chia ba nhóm `<, =, >` theo pivot | Ba hướng Dutch National Flag | Một lượt quét, O(n), O(1), hiệu quả khi nhiều giá trị trùng pivot. |
| Phải giữ thứ tự trong từng nhóm và có thể dùng bộ nhớ phụ | Quét hai lượt vào mảng đệm | Đơn giản, O(n) thời gian, O(n) bộ nhớ phụ. |
| Phải giữ thứ tự nhưng bộ nhớ phụ O(1) | Chèn tại ranh giới bằng dịch chuyển | Dễ hiểu, O(1) bộ nhớ phụ nhưng có thể O(n²) thời gian. |
| Cần toàn bộ mảng tăng dần | Thuật toán sắp xếp phù hợp | Phân hoạch chỉ là bước trung gian, chưa giải quyết mục tiêu sắp xếp. |
| Cần tìm phần tử thứ `k` theo thứ tự | Thuật toán lựa chọn sử dụng phân hoạch | Phân hoạch hỗ trợ giảm miền xét; cần phân tích thêm lựa chọn pivot và trường hợp xấu nhất. |

Đối với bài toán có nhiều loại hơn ba, có thể đếm kích thước từng nhóm rồi bố trí các đoạn hoặc sử dụng các thuật toán phân phối khác. Khi số nhóm thay đổi theo đầu vào, **bộ nhớ lưu các bộ đếm/ranh giới** phải được tính vào chi phí, không tự nhận là O(1).

## 9. Lỗi thường gặp và cách tự kiểm tra

1. **Tăng cả hai con trỏ sau mỗi lần hoán đổi:** phần tử vừa chuyển đến chưa được kiểm tra có thể bị bỏ sót. Cần duy trì đúng ranh giới vùng chưa phân loại.
2. **Nhầm `left < right` và `left <= right`:** nếu dùng điều kiện khác, phải bảo đảm phần tử cuối khi hai con trỏ gặp nhau vẫn được phân loại.
3. **Đổi chỗ nhưng làm mất dữ liệu:** cần dùng biến tạm hoặc phép hoán đổi đúng; không gán đè một phần tử trước khi lưu giá trị cũ.
4. **Đếm sai nhóm với dữ liệu âm:** trong Java, `x % 2 == 1` không nhận ra `-3` là số lẻ; dùng `(x & 1) != 0` hoặc `x % 2 != 0`.
5. **Tăng `i` sau khi đổi một giá trị lớn hơn pivot với `A[gt]` trong ba hướng:** giá trị mới ở `i` chưa được phân loại và có thể bị bỏ sót.
6. **Nhầm kết quả phân hoạch với kết quả sắp xếp:** điều kiện nhóm đúng không yêu cầu giá trị trong nhóm tăng/giảm.
7. **Bỏ quên tính ổn định:** kết quả đúng theo tiêu chí nhóm vẫn có thể sai nếu bài toán yêu cầu giữ thứ tự ban đầu.
8. **Tạo mảng phụ rồi gọi là O(1) bộ nhớ:** nếu kích thước mảng phụ tăng theo `n`, chi phí là O(n), ngay cả khi chạy nhanh.
9. **Không xét dãy rỗng, một phần tử hoặc tất cả cùng một nhóm:** đây là những trường hợp dễ làm sai chỉ số và điều kiện dừng.
10. **Bỏ qua bất biến:** trước khi tối ưu số phép đổi chỗ, hãy mô tả rõ vùng nào đã đúng và vùng nào chưa xử lý.

## 10. Bài tập tự kiểm tra có lời giải

**Câu 1.** Sau phân hoạch chẵn–lẻ tại chỗ của `[4,2,5,1,6,3]` theo mã Java ở trên, ranh giới và kết quả là gì? **Đáp án:** `k=3`, kết quả `[4,2,6,1,3,5]`.

**Câu 2.** Vì sao nhánh gặp số lẻ ở `A[left]` không tăng `left` sau khi hoán đổi? **Đáp án:** phần tử được chuyển từ `A[right]` sang `A[left]` có thể chẵn hoặc lẻ và chưa được xét; tăng ngay có thể để lại số lẻ trong vùng chẵn.

**Câu 3.** Với `A=[3,3,3]` và pivot `3`, `threeWay` trả ranh giới nào? **Đáp án:** `[0,3]`. Vùng nhỏ hơn và lớn hơn pivot rỗng, toàn bộ ba phần tử ở nhóm bằng pivot.

**Câu 4.** Với `A=[]`, `evenFirst` và `threeWay(A,2)` trả gì? **Đáp án:** lần lượt `0` và `[0,0]`; không có phần tử nào để xử lý.

**Câu 5.** Phân hoạch `[5,2,3,4,1]` sao cho chẵn trước lẻ **và giữ thứ tự tương đối**. Đáp án là gì? **Đáp án:** `[2,4,5,3,1]`. Nếu dùng thuật toán hai con trỏ, không thể mặc nhiên khẳng định tính ổn định.

**Câu 6.** Vì sao phân hoạch ba hướng có thể kết thúc sau O(n) lượt dù khi gặp `> pivot` không tăng `i`? **Đáp án:** mỗi lượt hoặc `i` tăng hoặc `gt` giảm; độ dài vùng `[i,gt]` chưa phân loại vì thế giảm một.

**Câu 7.** Khi bài toán yêu cầu các số tăng dần, có thể chỉ gọi `threeWay` với pivot `2` rồi coi như đã sắp xếp không? **Đáp án:** không. Ba nhóm được đặt đúng vị trí tương đối nhưng các phần tử trong nhóm `<2` và `>2` vẫn có thể chưa có thứ tự.

## 11. Quy trình áp dụng vào một bài xử lý dãy mới

Trước khi cài đặt, hãy viết rõ **tiêu chí nhóm**, **số nhóm**, **có yêu cầu giữ thứ tự không** và **có cho phép sửa trực tiếp đầu vào không**. Tiếp theo chọn quy ước ranh giới (ưu tiên đoạn nửa mở), đặt bất biến cho các vùng đã phân loại và vùng chưa biết, rồi xây dựng nhánh cập nhật chỉ số sao cho vùng chưa biết **nhỏ đi ở mỗi lượt**.

Sau đó mô phỏng một mảng có phần tử ở tất cả nhóm, một mảng có nhiều phần tử trùng và các biên rỗng/một phần tử. Khi kết thúc, kiểm tra cả **tiêu chí nhóm**, **số lượng từng giá trị được bảo toàn**, **ranh giới trả về** và **chi phí bộ nhớ thật sự**. Bốn kiểm tra này giúp phân biệt một phép hoán đổi có vẻ hợp lý với một thuật toán phân hoạch đúng.
