# Đếm nghịch thế bằng phép trộn (Counting Inversions with Merge Sort)

**Nghịch thế (inversion)** là một cặp vị trí có thứ tự trong dãy mà thứ tự giá trị của chúng bị đảo so với thứ tự tăng dần. Cho mảng `a` dài `n`, một cặp chỉ số `(i,j)` là nghịch thế khi và chỉ khi:

\[
0 \le i < j < n \quad \text{và} \quad a[i] > a[j].
\]

**Bài toán:** đếm **tổng số cặp chỉ số** thỏa điều kiện trên. Cần trả **một số lượng**, không phải danh sách tất cả các cặp. Các phần tử bằng nhau **không tạo nghịch thế** vì dấu so sánh là `>`, không phải `>=`. Các lần xuất hiện khác nhau của cùng một giá trị vẫn là các phần tử ở vị trí khác nhau, vì vậy phải đếm theo **cặp vị trí**, không đếm theo cặp giá trị phân biệt.

Ví dụ:

```text
Chỉ số:  0  1  2  3  4
Mảng:   [2, 4, 1, 3, 5]

Các cặp nghịch thế (giá trị):
  (2,1)  từ chỉ số (0,2)
  (4,1)  từ chỉ số (1,2)
  (4,3)  từ chỉ số (1,3)

Tổng = 3.
```

Nếu thử toàn bộ `n(n-1)/2` cặp chỉ số, ta có cách làm `O(n²)` rất dễ hiểu. Nhưng với `n` lớn, có thể đếm nhanh hơn bằng **chia để trị (divide and conquer)** kết hợp **bước trộn của Merge Sort**, đạt `O(n log n)` thời gian.

Điểm then chốt là: khi **hai nửa đã được sắp tăng dần**, một phép so sánh có thể xác định ngay **nhiều cặp nghịch thế cùng lúc**, không cần duyệt từng cặp.

## 1. Hiểu đúng “nghịch thế”

Xét một vài trường hợp để xác định rõ hợp đồng bài toán:

| Dãy ban đầu | Số nghịch thế | Giải thích |
|---|---:|---|
| `[]` | 0 | Không có cặp chỉ số |
| `[7]` | 0 | Một phần tử không tạo cặp |
| `[1,2,3,4]` | 0 | Đã không giảm |
| `[4,3,2,1]` | 6 | Mọi cặp `i<j` đều có `a[i]>a[j]` |
| `[2,4,1,3,5]` | 3 | Các cặp `(2,1)`, `(4,1)`, `(4,3)` |
| `[3,3,2,2]` | 4 | Mỗi trong hai số `3` đứng trước mỗi trong hai số `2` |
| `[2,2,2]` | 0 | Các giá trị bằng nhau không tính |
| `[-1,-3,2]` | 1 | Chỉ `-1 > -3` |
| `[2,1,2,1]` | 3 | Hai bản sao `2` tạo ba cặp với các số `1` phía sau |

Đếm nghịch thế có thể diễn giải như một thước đo **độ lệch khỏi thứ tự không giảm**. Số nghịch thế bằng `0` khi và chỉ khi dãy đã không giảm. Số lớn nhất trên `n` phần tử là:

\[
\frac{n(n-1)}{2},
\]

đạt được khi tất cả phần tử **phân biệt** và được sắp giảm nghiêm ngặt. Nếu có các giá trị trùng nhau, một số cặp sẽ không thể là nghịch thế, nên mức tối đa trên chính đa tập giá trị đó có thể thấp hơn công thức trên.

**Lưu ý:** nghịch thế không nhất thiết là hai phần tử **kề nhau**. Trong `[3,1,2]` có hai nghịch thế `(3,1)` và `(3,2)`, dù chỉ có một cặp kề nhau sai thứ tự ở mảng ban đầu. Chỉ đếm các cặp kề nhau không giải quyết được bài toán.

## 2. Chia bài toán thành ba loại cặp

Giả sử đang xử lý đoạn chỉ số nửa mở `[lo,hi)` của mảng, chọn vị trí giữa:

```text
mid = lo + (hi - lo) / 2

Đoạn trái:  [lo, mid)
Đoạn phải: [mid, hi)
```

Mỗi cặp nghịch thế trong đoạn thuộc **đúng một** trong ba loại:

1. **Nghịch thế ở nửa trái:** cả `i` và `j` đều thuộc `[lo,mid)`.
2. **Nghịch thế ở nửa phải:** cả hai chỉ số đều thuộc `[mid,hi)`.
3. **Nghịch thế cắt qua ranh giới (cross inversion):** `i` thuộc nửa trái và `j` thuộc nửa phải. Vì mọi chỉ số bên trái nhỏ hơn mọi chỉ số bên phải, điều kiện `i<j` tự động đúng; chỉ cần xét `a[i]>a[j]`.

Do ba loại **không giao nhau và bao phủ tất cả cặp**, ta có:

\[
\text{inv}(lo,hi)
= \text{inv}(lo,mid)
+ \text{inv}(mid,hi)
+ \text{cross}(lo,mid,hi).
\]

Ta đệ quy tính nghịch thế của từng nửa, đồng thời **sắp xếp từng nửa** để bước trộn có thể đếm nhanh những nghịch thế cắt qua ranh giới.

Đây là sự kết hợp của hai công việc trong một hàm:

- Trả về **số nghịch thế** của đoạn theo trạng thái trước khi sắp.
- Biến đoạn đó thành **dãy không giảm** để lần trộn ở cấp trên xử lý hiệu quả.

Cần hiểu rằng sắp xếp là **công cụ phụ trợ** để đếm; nó không phải đáp án chính. Nếu API yêu cầu giữ nguyên đầu vào, hãy đếm trên một bản sao.

## 3. Mấu chốt: đếm các cặp cắt ngang trong lúc trộn

Giả sử hai nửa đã được sắp tăng:

```text
Trái:  [2, 4]
Phải: [1, 3, 5]

Khi trộn tăng dần:
  2 > 1  → chọn 1 từ nửa phải; cộng 2 nghịch thế
           vì cả 2 và 4 còn lại bên trái đều > 1.
  2 <= 3 → chọn 2 từ nửa trái; không cộng.
  4 > 3  → chọn 3 từ nửa phải; cộng 1 nghịch thế
           vì chỉ còn 4 bên trái và 4 > 3.
  4 <= 5 → chọn 4 từ nửa trái; không cộng.
  Sau đó lấy 5.

Mảng sau trộn: [1, 2, 3, 4, 5]
Số nghịch thế cắt ngang: 2 + 1 = 3.
```

Trong bước trộn, ta có:

- `i` trỏ tới phần tử chưa xử lý đầu tiên ở nửa trái `[lo,mid)`.
- `j` trỏ tới phần tử chưa xử lý đầu tiên ở nửa phải `[mid,hi)`.
- `write` trỏ vị trí tiếp theo trong mảng tạm.
- Hai nửa đã sắp theo thứ tự **không giảm**.

Ở mỗi lượt:

**Trường hợp A — `a[i] <= a[j]`**

Chọn `a[i]` vào mảng tạm và tăng `i`. Vì `a[j]` là giá trị **nhỏ nhất còn lại** của nửa phải và `a[i] <= a[j]`, phần tử `a[i]` không lớn hơn bất cứ phần tử nào còn lại bên phải. Vậy **không có nghịch thế cắt ngang** bắt đầu bằng `a[i]` với các phần tử chưa xử lý của nửa phải. Không cộng gì.

Dấu **`<=`** là quan trọng: nếu bằng nhau, ta lấy từ trái trước để không đếm nhầm phần tử bằng nhau thành nghịch thế. Việc này cũng giúp phép trộn ổn định theo thứ tự xuất hiện, dù việc ổn định không phải yêu cầu để trả về số lượng.

**Trường hợp B — `a[i] > a[j]`**

Chọn `a[j]` vào mảng tạm và tăng `j`. Vì nửa trái đã sắp, mọi phần tử còn lại ở các chỉ số `i,i+1,...,mid-1` đều thỏa:

\[
a[i] \le a[i+1] \le \cdots \le a[mid-1],
\]

nên khi `a[i] > a[j]`, **toàn bộ `mid-i` phần tử chưa xử lý của nửa trái cũng lớn hơn `a[j]`**. Mỗi phần tử ấy nằm trước `a[j]` theo vị trí ở hai nửa gốc, nên tạo một nghịch thế cắt ngang.

Vì vậy, cộng **`mid - i`** ngay trong một bước, không phải cộng `1`.

```java
if (a[i] <= a[j]) {
    temp[write++] = a[i++];
} else {
    inversions += mid - i;   // Đếm tất cả phần tử trái còn lại > a[j].
    temp[write++] = a[j++];
}
```

Sau khi một bên đã hết phần tử, sao chép toàn bộ phần còn lại của bên kia. Không cộng thêm nghịch thế tại bước sao chép phần dư vì **mọi cặp cắt ngang cần đếm đều đã được xử lý** khi phần tử bên phải được đưa vào trộn trước những phần tử lớn hơn còn lại bên trái.

Cuối cùng, sao chép đoạn đã trộn từ mảng tạm về mảng chính để đoạn `[lo,hi)` có thứ tự, chuẩn bị cho cấp đệ quy phía trên.

## 4. Ví dụ cụ thể: chia và trộn `[2,4,1,3,5]`

Ta chia theo ranh giới giữa hai nửa:

```text
                        [2,4,1,3,5]
                        /         \
                    [2,4]        [1,3,5]
                    /   \         /   \
                  [2]   [4]     [1]   [3,5]
                                          / \
                                        [3] [5]
```

Ở cấp thấp nhất, đoạn một phần tử có **0 nghịch thế** và tự nó đã được sắp.

- Trộn `[2]` với `[4]`: không có nghịch thế cắt ngang; đoạn trái trở thành `[2,4]`.
- Trộn `[3]` với `[5]`: không có nghịch thế; đoạn trở thành `[3,5]`.
- Trộn `[1]` với `[3,5]`: không có nghịch thế; đoạn phải trở thành `[1,3,5]`.
- Trộn `[2,4]` với `[1,3,5]`:
  - `2>1`, cộng `2`;
  - `2<=3`, không cộng;
  - `4>3`, cộng `1`;
  - các phần tử còn lại không tạo thêm nghịch thế cắt ngang.

Tổng từ hai nửa là `0+0`, số cặp cắt ngang là `3`, vậy kết quả cuối cùng là **`3`**.

Điều quan trọng là đếm theo **vị trí gốc tương ứng với mỗi nửa đệ quy**, không đếm các cặp của mảng đã sắp ở cuối. Bản thân việc sắp làm mọi nghịch thế biến mất, nhưng **biến đếm** đã lưu lại chính xác số cặp nghịch thế của đầu vào trước khi sắp.

## 5. Chương trình Java 17+ chạy được

Ví dụ dưới đây có hai API có chủ đích khác nhau:

- `countInversions(input)`: **không sửa mảng gốc**; sao chép trước khi đếm và sắp.
- `countAndSort(a)`: đếm nghịch thế của thứ tự ban đầu rồi **sắp xếp trực tiếp mảng được truyền vào**. Phương pháp này vẫn dùng một **mảng tạm `O(n)`**, nên không gọi nó là “sắp xếp tại chỗ với bộ nhớ phụ `O(1)`”.

Cả hai trả `long` để giữ số cặp có thể vượt phạm vi `int`. Đầu vào `null` bị từ chối bằng `IllegalArgumentException`; mảng rỗng, một phần tử và giá trị trùng đều hợp lệ.

Lưu toàn bộ chương trình vào **`InversionCountDemo.java`**:

```java
import java.util.Arrays;

public final class InversionCountDemo {
    private InversionCountDemo() {
    }

    // Giữ nguyên mảng đầu vào; trả số nghịch thế của mảng đó.
    public static long countInversions(int[] input) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }
        int[] copy = Arrays.copyOf(input, input.length);
        return countAndSort(copy);
    }

    // Trả số nghịch thế của a ở thời điểm gọi,
    // đồng thời sắp xếp a tăng dần khi hoàn thành.
    public static long countAndSort(int[] a) {
        if (a == null) {
            throw new IllegalArgumentException("array must not be null");
        }
        int[] temp = new int[a.length];
        return sortAndCount(a, temp, 0, a.length);
    }

    // Đoạn nửa mở [lo, hi): lo được lấy, hi không được lấy.
    // Khi trả về: a[lo..hi) đã được sắp và số nghịch thế là chính xác.
    private static long sortAndCount(
            int[] a, int[] temp, int lo, int hi) {
        if (hi - lo <= 1) {
            return 0L;
        }

        int mid = lo + (hi - lo) / 2;

        long count = sortAndCount(a, temp, lo, mid);
        count += sortAndCount(a, temp, mid, hi);

        // Hai nửa [lo,mid) và [mid,hi) hiện đã có thứ tự.
        int i = lo;
        int j = mid;
        int write = lo;

        while (i < mid && j < hi) {
            if (a[i] <= a[j]) {
                // Bằng nhau không là nghịch thế.
                temp[write++] = a[i++];
            } else {
                // a[i], ..., a[mid-1] đều > a[j].
                count += (long) (mid - i);
                temp[write++] = a[j++];
            }
        }

        while (i < mid) {
            temp[write++] = a[i++];
        }
        while (j < hi) {
            temp[write++] = a[j++];
        }

        // Chỉ sao chép lại đoạn [lo,hi) vừa trộn.
        System.arraycopy(temp, lo, a, lo, hi - lo);
        return count;
    }

    public static void main(String[] args) {
        int[] sample = {2, 4, 1, 3, 5};
        System.out.println("Sample count: "
                + countInversions(sample));
        System.out.println("Original: "
                + Arrays.toString(sample));

        int[] work = Arrays.copyOf(sample, sample.length);
        System.out.println("Count and sort: "
                + countAndSort(work));
        System.out.println("Sorted: "
                + Arrays.toString(work));

        System.out.println("Duplicates: "
                + countInversions(new int[] {3, 3, 2, 2}));
        System.out.println("All equal: "
                + countInversions(new int[] {7, 7, 7}));
        System.out.println("Already sorted: "
                + countInversions(new int[] {1, 2, 2, 3}));
        System.out.println("Reverse five: "
                + countInversions(new int[] {5, 4, 3, 2, 1}));
        System.out.println("Mixed signs: "
                + countInversions(new int[] {-1, -3, 2}));
        System.out.println("Empty: "
                + countInversions(new int[0]));
        System.out.println("Singleton: "
                + countInversions(new int[] {42}));

        // Cần long: 100000 * 99999 / 2 > Integer.MAX_VALUE.
        int n = 100_000;
        int[] reverse = new int[n];
        for (int index = 0; index < n; index++) {
            reverse[index] = n - index;
        }
        System.out.println("Reverse 100000: "
                + countInversions(reverse));
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac InversionCountDemo.java
java InversionCountDemo
```

**Đầu ra chính xác:**

```text
Sample count: 3
Original: [2, 4, 1, 3, 5]
Count and sort: 3
Sorted: [1, 2, 3, 4, 5]
Duplicates: 4
All equal: 0
Already sorted: 0
Reverse five: 10
Mixed signs: 1
Empty: 0
Singleton: 0
Reverse 100000: 4999950000
```

Giải thích các kết quả đáng chú ý:

- `countInversions(sample)` trả `3` nhưng **`sample` vẫn là `[2,4,1,3,5]`**, vì thuật toán tạo bản sao trước khi xử lý.
- `countAndSort(work)` trả cùng số `3` và làm `work` trở thành `[1,2,3,4,5]`. Chạy lại `countAndSort(work)` ngay sau đó sẽ trả `0`, vì **thứ tự đầu vào của lần gọi thứ hai đã thay đổi**.
- `[3,3,2,2]` có bốn nghịch thế: hai vị trí chứa `3` đều đứng trước hai vị trí chứa `2`. Hai số `3` bằng nhau không tạo nghịch thế với nhau, hai số `2` cũng vậy.
- `[7,7,7]` và `[1,2,2,3]` có `0` nghịch thế vì không có cặp chỉ số trước–sau nào thỏa `a[i]>a[j]`.
- Dãy đảo ngược gồm 100.000 giá trị phân biệt có `100000 × 99999 / 2 = 4.999.950.000` nghịch thế, lớn hơn giới hạn `2.147.483.647` của `int`; `long` mới giữ được kết quả này.

### Tại sao dùng `long` thay vì `int`?

Số cặp chỉ số nhiều nhất là `n(n-1)/2`. Với `n=65.537`, giá trị đó đã là `2.147.516.416`, vượt `Integer.MAX_VALUE=2.147.483.647`. Nếu dùng biến đếm `int`, tổng có thể **tràn số và cho kết quả sai** dù logic phân hoạch/trộn hoàn toàn đúng.

Trong mã, `count` là `long` và phép tăng sử dụng `(long)(mid-i)`. Không cần dùng kiểu số thực. Nếu muốn tự tính giới hạn lý thuyết cho một kích thước `n` kiểu `int`, nên thực hiện ép kiểu **trước phép nhân**:

```java
long maxPossible = (long) n * (n - 1) / 2;
```

Nếu viết `n*(n-1)` trong `int` rồi mới gán sang `long`, kết quả có thể đã tràn trước khi gán.

Đối với mảng Java mà độ dài `n` là `int`, số cặp toán học tối đa `n(n-1)/2` vẫn nằm trong giới hạn `long`. Bộ nhớ để thực sự cấp một mảng rất lớn là vấn đề độc lập với kiểu trả về.

## 6. Chứng minh tính đúng bằng quy nạp

Ta chứng minh hợp đồng của `sortAndCount(a,temp,lo,hi)`:

> Khi hàm kết thúc, đoạn `a[lo..hi)` được sắp **không giảm**, chứa đúng các phần tử của đoạn tại thời điểm gọi, và giá trị trả về là **số nghịch thế trong thứ tự của đoạn trước lời gọi**.

**Cơ sở quy nạp:** nếu đoạn có độ dài `0` hoặc `1`, không tồn tại cặp `i<j`. Hàm trả `0L` và đoạn vốn đã được sắp; hợp đồng đúng.

**Giả thiết quy nạp:** với hai nửa nhỏ hơn, lời gọi đệ quy đã trả đúng số nghịch thế **nội bộ** của mỗi nửa và biến từng nửa thành dãy không giảm, không thay đổi đa tập giá trị của nửa đó.

**Bước trộn:**

1. Mọi nghịch thế của đoạn nằm hoàn toàn ở trái, hoàn toàn ở phải, hoặc cắt ngang. Ba tập cặp này phân biệt nên có thể cộng số lượng mà không đếm trùng.
2. Các nghịch thế nội bộ của trái và phải đã được đệ quy đếm đúng theo giả thiết.
3. Khi `a[i]<=a[j]`, phần tử trái hiện tại không tạo nghịch thế với phần tử phải chưa xử lý nào; không tăng bộ đếm là đúng.
4. Khi `a[i]>a[j]`, mọi phần tử trái từ `i` đến `mid-1` đều lớn hơn `a[j]`; chúng tạo **chính xác `mid-i` cặp cắt ngang** mới được phát hiện khi lấy `a[j]`. Mỗi phần tử phải được lấy đúng một lần, nên mỗi cặp cắt ngang được đếm đúng một lần.
5. Việc luôn lấy phần tử nhỏ hơn (ưu tiên bên trái khi bằng nhau) tạo mảng tạm không giảm. Sao chép lại đoạn bảo toàn các giá trị ban đầu, chỉ thay thứ tự.

Vì thế tổng `leftCount+rightCount+crossCount` bằng đúng tổng số nghịch thế, còn đoạn được sắp chính xác. Hợp đồng đúng cho đoạn đang xét. Theo quy nạp, lời gọi ở gốc `[0,n)` trả số nghịch thế của toàn mảng ban đầu.

### Bất biến trong lúc trộn

Trước mỗi lần lặp:

- `temp[lo..write)` đã chứa những phần tử nhỏ nhất trong hai nửa ở số lượng tương ứng, theo thứ tự không giảm.
- `a[i..mid)` và `a[j..hi)` là phần chưa lấy của hai nửa đã sắp.
- `count` đã ghi nhận tất cả cặp cắt ngang mà **phần tử phải** của cặp đã được đưa vào mảng tạm trước một phần tử trái lớn hơn đang chờ.

Nếu một nửa hết, phần còn lại đã có thứ tự và không tạo thêm cặp cắt ngang chưa ghi nhận. Sau khi sao chép, `write=hi` và toàn bộ đoạn được trộn xong.

Sự chính xác này phụ thuộc vào hai điều: **các nửa phải được sắp trước khi trộn**, và **điều kiện nghịch thế phải là lớn hơn nghiêm ngặt**. Nếu bỏ một điều, phép cộng `mid-i` có thể không còn chính xác.

## 7. Độ phức tạp: vì sao nhanh hơn hai vòng lặp?

Gọi `T(n)` là số công việc cho một đoạn dài `n`. Hai nửa có tổng kích thước `n`; bước trộn chỉ duyệt mỗi phần tử một số lần hằng số, nên tốn `Θ(n)`. Ta có truy hồi gần đúng:

\[
T(n)=2T(n/2)+\Theta(n),
\]

suy ra bằng định lý Master hoặc xét cây đệ quy:

\[
T(n)=\Theta(n\log n) \quad (n\ge 2).
\]

Với `n` không phải lũy thừa của hai, hai nửa có thể chênh nhau một phần tử; kết quả tiệm cận vẫn như vậy.

**Trực giác theo các tầng trộn:** có khoảng `log₂n` tầng phân chia. Ở một tầng, tổng độ dài các đoạn cần trộn không vượt `n`; do đó tổng công việc là khoảng `n×log₂n`. Cách làm này không tạo ra một vòng lặp riêng cho từng cặp nghịch thế. Một bước `count += mid-i` có thể đếm hàng nghìn cặp khi các phần tử của nửa trái đều lớn hơn phần tử phải đang xét.

| Phương pháp | Thời gian | Bộ nhớ phụ | Ghi chú |
|---|---|---|---|
| Thử mọi cặp `i<j` | `Θ(n²)` | `O(1)` | Đơn giản, tốt để đối chiếu đầu vào nhỏ |
| Đếm bằng trộn như chương trình | `Θ(n log n)` với `n≥2` | `Θ(n)` mảng tạm; `O(log n)` ngăn xếp | Vừa đếm vừa sắp, hoạt động tốt với số âm và trùng |
| Đếm trên bản sao `countInversions` | `Θ(n log n)` với `n≥2` | `Θ(n)` cho bản sao và mảng tạm | Giữ nguyên thứ tự mảng người gọi |
| Fenwick Tree + nén tọa độ | Thường `O(n log n)` | `O(n)` | Phương án khác khi cần thống kê tần suất theo thứ hạng |

**Bộ nhớ:** mã tạo một `temp[]` dài `n` đúng một lần cho toàn bộ cây đệ quy, không tạo mảng mới trong mỗi bước trộn. Mức sâu đệ quy khoảng `O(log n)`, nên bộ nhớ ngoài mảng đầu vào là **`Θ(n)`**, bị chi phối bởi mảng tạm. API không sửa mảng gốc còn tạo thêm một bản sao dài `n`; tổng vẫn là `Θ(n)` nhưng hệ số bộ nhớ lớn hơn.

**Không phải sắp xếp tại chỗ `O(1)` bộ nhớ phụ:** dù `countAndSort` sắp trực tiếp trong mảng được truyền vào, nó vẫn dùng `temp[]`. “Có sửa mảng đầu vào” và “sắp xếp in-place với bộ nhớ phụ hằng số” là hai khái niệm khác nhau.

### Tính toán theo giới hạn thời gian

Với `n=100.000`, số cặp có thể lên tới khoảng **5 tỷ**. Thử mọi cặp cần khoảng `5×10^9` lần kiểm tra trong trường hợp tệ, dễ quá chậm. Đếm bằng trộn chỉ xử lý khoảng `n log₂n` bước ở mức tiệm cận. Không suy ra thời gian chạy chính xác theo giây từ ký hiệu Big-O; thời gian còn phụ thuộc JVM, CPU, bộ nhớ và dữ liệu.

## 8. Cách đếm khác và các tình huống thực tế

### 8.1. Hai vòng lặp: chuẩn đối chiếu dễ kiểm tra

Mã giả:

```text
answer = 0
for i từ 0 đến n-1:
    for j từ i+1 đến n-1:
        if a[i] > a[j]:
            answer++
```

Cách này dùng `O(1)` bộ nhớ phụ, dễ chứng minh đúng vì xét mọi cặp `i<j` đúng một lần, nhưng có `Θ(n²)` thời gian. Hữu ích khi `n` nhỏ hoặc để **kiểm thử đối chứng** thuật toán chia để trị.

Nếu viết thành Java, biến `answer` vẫn nên là `long` ngay cả khi hai vòng lặp đủ đơn giản về mặt logic.

### 8.2. Fenwick Tree (Binary Indexed Tree)

Một hướng khác là duyệt dãy **từ phải sang trái**, lưu số lần xuất hiện của các giá trị đã thấy. Khi đang ở `a[i]`, số nghịch thế có đầu trái `i` chính là số phần tử **đã gặp ở bên phải có giá trị nhỏ hơn nghiêm ngặt `a[i]`**.

Nếu nén các giá trị phân biệt thành thứ hạng `1..U` theo thứ tự tăng, Fenwick Tree có thể:

1. Truy vấn tổng số phần tử đã gặp có thứ hạng **nhỏ hơn `rank(a[i])`**, tức `prefixSum(rank-1)`.
2. Cộng số đó vào `answer`.
3. Tăng tần suất tại `rank(a[i])` lên `1`.

Mỗi truy vấn/cập nhật mất `O(log U)`; nén tọa độ thường cần sắp các giá trị và tổng thời gian thành `O(n log n)`. **Nhớ dùng `rank-1`**, không phải `rank`, nếu cần loại các giá trị bằng nhau khỏi số nghịch thế.

Fenwick Tree có giá trị khi bài toán mở rộng sang các truy vấn đếm tần suất; còn với một mảng tĩnh cần một tổng nghịch thế, phép trộn là cách diễn giải rất tự nhiên của **chia để trị**.

### 8.3. Quan hệ với số lần hoán đổi kề nhau

Mỗi lần đổi chỗ **hai phần tử kề nhau đang sai thứ tự** sẽ giảm số nghịch thế đi đúng `1`. Vì vậy, số nghịch thế bằng số lần **hoán đổi kề nhau tối thiểu** để đưa mảng về thứ tự không giảm. Đó cũng là số lần đổi chỗ mà phiên bản Bubble Sort chuẩn thực hiện nếu chỉ đổi khi phần tử trái lớn hơn phần tử phải.

Nhưng số nghịch thế **không** bằng số lần hoán đổi tối thiểu khi cho phép đổi **hai vị trí bất kỳ**; một phép đổi xa có thể sửa nhiều nghịch thế cùng lúc. Đừng nhầm hai loại thao tác.

### 8.4. Khi bài toán thay đổi định nghĩa cặp

Điều kiện chuẩn là `i<j` và `a[i]>a[j]`. Nếu đề thay thành `a[i]>=a[j]`, hoặc một bất đẳng thức tỷ lệ như `a[i]>2a[j]`, đó là **bài toán đếm cặp khác**. Tư duy chia để trị có thể vẫn hữu ích, nhưng phép so sánh và cách đếm chéo phải được thiết kế lại; không thể tự đổi `<=` thành `<` trong phép trộn rồi coi mọi logic vẫn đúng mà không chứng minh.

Ví dụ, với điều kiện **`>=`**, hai giá trị bằng nhau có thể được tính; nhưng nếu phép trộn đặt bằng nhau theo một phía khác, cần kiểm tra rằng mọi cặp cắt ngang bằng nhau được đếm **đúng một lần**. Các biến thể đặc biệt nên được mô tả và chứng minh riêng.

## 9. Lỗi phổ biến

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Viết `a[i]>=a[j]` để đếm nghịch thế chuẩn | Đếm thừa các cặp giá trị bằng nhau | Dùng điều kiện nghiêm ngặt `a[i]>a[j]`; trong trộn ưu tiên trái khi `a[i]<=a[j]` |
| Khi `a[i]>a[j]` chỉ cộng `1` | Bỏ sót những phần tử trái còn lại cũng lớn hơn `a[j]` | Cộng **`mid-i`** |
| Cộng `hi-j` thay vì `mid-i` | Đếm sai vì số phần tử còn lại bên phải không phải số phần tử trái lớn hơn | Hiểu rõ chỉ số `mid` là cuối nửa trái và `i` là con trỏ trái |
| Đếm các cặp trước khi hai nửa được sắp | Không có cơ sở kết luận tất cả phần tử trái còn lại đều lớn hơn | Đệ quy sắp **cả hai nửa trước** khi trộn |
| Dùng biến kết quả `int` | Tràn số với khoảng trên 65 nghìn phần tử đảo ngược | Trả `long`, cộng bằng `long` |
| Tính `n*(n-1)/2` bằng `int` trước khi ép kiểu | Phép nhân đã tràn trước khi gán | Dùng `(long)n*(n-1)/2` |
| Sai quy ước đoạn `[lo,hi)` | Bỏ sót hoặc đọc vượt phần tử cuối | Giữ `mid` là đầu nửa phải, `hi` là cận không lấy |
| Quên sao chép `temp[lo..hi)` về `a` | Lần trộn cấp trên nhận nửa chưa được sắp | Sao chép chính xác đoạn đã trộn sau mỗi lần xử lý |
| Tạo mảng tạm mới trong từng lời gọi | Cấp phát dư, ảnh hưởng hiệu năng và bộ nhớ | Tạo một `temp` chung và truyền xuống đệ quy |
| Quên rằng API đếm có thể sắp lại mảng | Làm thay đổi dữ liệu người gọi không mong muốn | Phân biệt bản sao `countInversions` và bản sửa `countAndSort` |
| Chỉ đếm các cặp kề nhau | Bỏ sót nghịch thế không kề | Đếm các cặp bất kỳ `i<j` |
| Kiểm thử chỉ với phần tử phân biệt | Không thấy lỗi xử lý bằng nhau | Thử dãy toàn bằng nhau, nhiều bản sao xen kẽ |
| So sánh số nguyên bằng `a[i]-a[j]` | Có thể tràn số nguyên và đảo dấu | Dùng toán tử `<`, `>`, `<=` trực tiếp |

## 10. Kiểm thử đối chứng có hệ thống

Có thể xác nhận thuật toán bằng cách viết một hàm đơn giản thử tất cả các cặp cho `n` nhỏ, rồi so với kết quả đếm bằng trộn:

```java
// Mã minh họa đối chứng, không phải chương trình độc lập.
static long countBruteForce(int[] a) {
    long total = 0L;
    for (int i = 0; i < a.length; i++) {
        for (int j = i + 1; j < a.length; j++) {
            if (a[i] > a[j]) {
                total++;
            }
        }
    }
    return total;
}
```

Kiểm thử nên có:

1. **Biên:** mảng rỗng, một phần tử, hai phần tử theo cả hai thứ tự.
2. **Đã tăng / đã giảm:** kết quả `0` và `n(n-1)/2` nếu các giá trị phân biệt.
3. **Giá trị trùng:** toàn bằng nhau, cặp trùng ở mỗi nửa, nhiều bản sao ở hai nửa khác nhau.
4. **Số âm và số cực trị:** thử `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `-1`, `0` để tránh lỗi so sánh.
5. **Không làm hỏng đầu vào:** sau `countInversions`, mảng ban đầu phải giữ nguyên từng phần tử.
6. **Có sắp ở API sửa mảng:** sau `countAndSort`, mảng phải không giảm và chứa đúng **đa tập giá trị** ban đầu.
7. **Tràn số đếm:** mảng giảm dần dài `100.000` phải có `4.999.950.000` nghịch thế.

Với mỗi mảng nhỏ được sinh ngẫu nhiên, so kết quả hàm `countInversions` với `countBruteForce`; nếu lệch, in cả mảng và các giá trị dự kiến/nhận được. Phép kiểm tra đối chứng đặc biệt hữu ích để bắt lỗi ở chỉ số `mid`, lỗi `<=` và lỗi sao chép mảng tạm. Tuy nhiên, **chứng minh bằng quy nạp và bất biến trộn** mới là cơ sở tổng quát cho mọi đầu vào hợp lệ.

## 11. Bài tập tự luyện

**Bài 1 — Liệt kê cặp.** Với `a=[4,1,3,2]`, hãy liệt kê toàn bộ nghịch thế, không chỉ số lượng.

*Đáp án:* `(4,1)`, `(4,3)`, `(4,2)`, `(3,2)`, tổng **`4`**.

**Bài 2 — Giá trị trùng.** Với `a=[2,2,1,1]`, có bao nhiêu nghịch thế? Hai phần tử bằng nhau có tạo cặp không?

*Đáp án:* hai số `2` đứng trước hai số `1`, nên có `2×2=4` nghịch thế; không đếm `(2,2)` hay `(1,1)`.

**Bài 3 — Đếm khi trộn.** Hai nửa đã sắp là `L=[1,5,8]` và `R=[2,3,9]`. Hãy ghi các thời điểm cần cộng vào `count` khi trộn.

*Đáp án:* khi lấy `2` từ nửa phải, còn `5,8` ở nửa trái nên cộng `2`; khi lấy `3`, vẫn còn `5,8` nên cộng `2`; tổng nghịch thế cắt ngang là **`4`**.

**Bài 4 — Phân tích thời gian.** Vì sao hai lời gọi đệ quy cộng với một vòng trộn tuyến tính tạo `O(n log n)` chứ không phải `O(n²)`? Nêu số tầng và tổng số phần tử được xử lý ở một tầng.

*Gợi ý:* có khoảng `log₂n` tầng. Tổng độ dài các đoạn trộn trong cùng tầng là `O(n)`; nhân hai đại lượng cho `O(n log n)`.

**Bài 5 — Kiểm tra miền số.** Tính số nghịch thế lớn nhất của dãy gồm `100.000` số nguyên phân biệt. Nó có vừa `int` không?

*Đáp án:* `100000×99999/2=4.999.950.000`, vượt `Integer.MAX_VALUE`, phải dùng `long`.

**Bài 6 — Phân biệt hợp đồng.** Giải thích sự khác nhau giữa `countInversions(a)` và `countAndSort(a)` trong chương trình. Nếu gọi `countAndSort(a)` hai lần liên tiếp trên cùng một mảng, lần thứ hai trả gì?

*Đáp án:* hàm đầu tạo bản sao nên giữ nguyên `a`; hàm sau sửa `a` thành dãy không giảm. Sau lần đầu, mảng đã được sắp nên lần gọi thứ hai trả **`0`**.

**Bài 7 — Liên hệ hoán đổi.** Với dãy `[3,1,2]` có `2` nghịch thế, hãy tìm một chuỗi hoán đổi **kề nhau** ngắn nhất để sắp tăng.

*Đáp án:* đổi `[3,1,2] → [1,3,2] → [1,2,3]`, đúng **2** hoán đổi kề nhau.

## Ghi nhớ

**Nghịch thế là cặp chỉ số `i<j` có `a[i]>a[j]`; dấu lớn hơn nghiêm ngặt loại các cặp bằng nhau.** Khi chia dãy thành hai nửa, mọi cặp nghịch thế nằm **trong trái, trong phải hoặc cắt qua hai nửa**. Đệ quy đếm và sắp từng nửa; trong lúc trộn, nếu `a[i]>a[j]` thì **cộng ngay `mid-i`** vì toàn bộ phần trái chưa xử lý đều lớn hơn phần tử phải đang xét.

Nhờ vậy, phép trộn vừa bảo toàn thứ tự cần cho cấp trên vừa đếm số cặp cắt ngang, cho tổng thời gian **`Θ(n log n)`**, bộ nhớ phụ **`Θ(n)`** và kết quả kiểu **`long`** đủ chứa số cặp lớn. Hãy kiểm tra kỹ **ranh giới nửa mở, xử lý dấu bằng, sao chép mảng tạm và tác dụng của việc sắp xếp lên dữ liệu đầu vào**.
