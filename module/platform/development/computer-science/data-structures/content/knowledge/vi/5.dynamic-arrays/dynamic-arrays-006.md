# Vì sao tăng dung lượng từng đơn vị có thể gây chi phí bậc hai

Mảng động (*dynamic array*) dùng một vùng lưu trữ liên tiếp để truy cập phần tử theo chỉ số nhanh và có thể thay vùng lưu trữ bằng vùng lớn hơn khi cần thêm phần tử. Một ý tưởng có vẻ tiết kiệm bộ nhớ là: **mỗi lần mảng đầy, chỉ cấp phát thêm đúng một ô**. Chính sách này giữ cho bộ đệm không có ô thừa sau mỗi lần thêm, nhưng khiến việc thêm nhiều phần tử trở nên rất tốn kém.

Với cách tăng `capacity` từ `c` lên `c + 1` khi đầy, xây dựng một mảng bằng `n` lần thêm cuối liên tiếp có thể mất **Θ(n²)** thời gian chỉ vì phải sao chép dữ liệu cũ nhiều lần. Bài học này giải thích chính xác điều gì bị sao chép, cách tính tổng chi phí, vì sao không được nhầm chi phí của *một lần thêm* với *cả chuỗi thêm*, và cách chọn chiến lược mở rộng phù hợp hơn.

## 1. Mảng động có hai con số cần phân biệt

Trong một cách cài đặt phổ biến, mảng động quản lý:

| Thành phần | Ý nghĩa |
| --- | --- |
| `buffer` | Mảng nền chứa các ô đã cấp phát, được lưu liên tiếp |
| `size` | Số phần tử hiện có về mặt logic |
| `capacity` | Số ô mà vùng lưu trữ hiện tại có thể chứa |

Bất biến cần giữ là:

\[
0\le \text{size}\le \text{capacity}.
\]

Các chỉ số phần tử hợp lệ nằm trong đoạn `[0, size)`. Nếu `size < capacity`, thao tác thêm cuối chỉ ghi vào `buffer[size]` và tăng `size`: **O(1)**. Nếu `size = capacity`, vị trí `buffer[size]` chưa tồn tại trong vùng cấp phát hiện tại, nên cấu trúc phải tìm chỗ chứa mới trước khi thêm.

Vấn đề của bài nằm ở quyết định **tăng `capacity` lên bao nhiêu** trong lần cấp phát mới. Nếu luôn chọn chính xác một ô thêm, dung lượng sẽ là:

```text
0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> ...
```

Trong ví dụ này, ta giả định khởi đầu `size = capacity = 0`, chỉ thực hiện thao tác thêm ở cuối, không xóa phần tử, và mỗi lần vùng lưu trữ đầy thì cấp phát vùng mới lớn hơn **đúng một ô**.

## 2. Minh họa trực quan: mỗi lần thêm đều sao chép lại phần trước

Giả sử muốn lần lượt thêm sáu giá trị `10, 20, 30, 40, 50, 60`. Vì `capacity` luôn bằng `size` sau mỗi lần thêm, bộ đệm lại đầy ngay sau thao tác. Lần thêm tiếp theo bắt buộc cấp phát lại:

```text
append(10)
  buffer cũ:   []
  buffer mới:  [10]                         sao chép 0 phần tử

append(20)
  buffer cũ:   [10]
  buffer mới:  [10][20]                     sao chép 1 phần tử

append(30)
  buffer cũ:   [10][20]
  buffer mới:  [10][20][30]                 sao chép 2 phần tử

append(40)
  buffer cũ:   [10][20][30]
  buffer mới:  [10][20][30][40]             sao chép 3 phần tử

append(50)
  buffer cũ:   [10][20][30][40]
  buffer mới:  [10][20][30][40][50]         sao chép 4 phần tử

append(60)
  buffer cũ:   [10][20][30][40][50]
  buffer mới:  [10][20][30][40][50][60]     sao chép 5 phần tử
```

Mỗi lần thêm gồm hai loại công việc:

1. **Sao chép phần tử cũ** từ bộ đệm cũ sang bộ đệm mới, với số phần tử bằng `size` trước khi thêm.
2. **Ghi phần tử mới** vào ô cuối và tăng `size` lên một.

Bảng chi phí của sáu lần thêm:

| Lần thêm thứ `k` | `size` trước khi thêm | `capacity` mới | Số phần tử cũ được sao chép | Số lần ghi phần tử mới |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0 | 1 | 0 | 1 |
| 2 | 1 | 2 | 1 | 1 |
| 3 | 2 | 3 | 2 | 1 |
| 4 | 3 | 4 | 3 | 1 |
| 5 | 4 | 5 | 4 | 1 |
| 6 | 5 | 6 | 5 | 1 |
| **Tổng** | | | **15** | **6** |

Với sáu phần tử, cấu trúc thực hiện **15 lần sao chép phần tử cũ** và **6 lần ghi phần tử mới**. Càng thêm nhiều, chi phí sao chép của lần thêm tiếp theo càng lớn.

## 3. Chứng minh tổng chi phí Θ(n²) bằng cấp số cộng

Gọi `n` là số phần tử được thêm vào một mảng ban đầu rỗng. Ở lần thêm thứ `k`, mảng đã chứa `k - 1` phần tử. Chính sách tăng đúng một ô bắt buộc sao chép tất cả `k - 1` phần tử đó.

Số lần sao chép qua cả `n` lần thêm là:

\[
\begin{aligned}
S(n)
&=\sum_{k=1}^{n}(k-1)\\
&=0+1+2+\cdots+(n-1)\\
&=\frac{n(n-1)}{2}.
\end{aligned}
\]

Với `n` đủ lớn, biểu thức bậc hai `n(n-1)/2` tăng cùng bậc với `n²`:

\[
S(n)=\Theta(n^2).
\]

Ngoài những lần sao chép, mỗi thao tác `append` còn ghi phần tử mới một lần. Nếu mô hình tính mỗi lần ghi hoặc sao chép một ô là một đơn vị công, tổng công ghi là:

\[
T(n)=S(n)+n
=\frac{n(n-1)}{2}+n
=\frac{n(n+1)}{2}
=\Theta(n^2).
\]

Như vậy, **`n` lần thêm cuối từ mảng rỗng có tổng chi phí Θ(n²)** với chính sách cấp phát tăng đúng một ô. Chỉ riêng công sao chép đã đủ để chứng minh cận dưới bậc hai trong mô hình này. Việc cấp phát/khởi tạo vùng mới và giải phóng bộ đệm cũ còn có thể tạo thêm chi phí thực tế, nhưng không làm kết luận trở nên tốt hơn.

### Một số con số dễ hình dung

| Số phần tử được thêm `n` | Tổng phần tử cũ bị sao chép `n(n-1)/2` | Tổng ghi mới + sao chép `n(n+1)/2` |
| ---: | ---: | ---: |
| 5 | 10 | 15 |
| 10 | 45 | 55 |
| 100 | 4.950 | 5.050 |
| 1.000 | 499.500 | 500.500 |
| 10.000 | 49.995.000 | 50.005.000 |

Khi tăng số phần tử mục tiêu từ 1.000 lên 10.000 (gấp 10), số bản sao tăng từ 499.500 lên 49.995.000 (xấp xỉ gấp 100). Đây là dấu hiệu đặc trưng của tăng trưởng bậc hai.

## 4. Một cách đếm khác: phần tử đến sớm bị sao chép nhiều lần

Không cần cộng theo *lần thêm*, ta cũng có thể nhìn từ phía *từng phần tử*. Khi thêm `n` phần tử theo chính sách trên:

- Phần tử thứ nhất phải được sao chép ở các lần thêm thứ `2, 3, \ldots, n`: tổng cộng `n - 1` lần.
- Phần tử thứ hai được sao chép `n - 2` lần.
- Phần tử thứ ba được sao chép `n - 3` lần.
- ...
- Phần tử thứ `n` chưa bao giờ bị sao chép, vì không còn thao tác thêm nào sau nó.

Tổng số bản sao cũng là:

\[
(n-1)+(n-2)+\cdots+1+0=\frac{n(n-1)}2.
\]

Cách nhìn này chỉ ra **nguyên nhân trực tiếp** của chi phí bậc hai: các phần tử được thêm từ sớm bị chuyển đi chuyển lại nhiều lần qua các vùng nhớ mới. Vấn đề không phải là mảng động truy cập theo chỉ số chậm; vấn đề là chính sách cấp phát lại quá thường xuyên khiến dữ liệu cũ liên tục bị sao chép.

## 5. Phân biệt chi phí của một lần thêm và của cả chuỗi

Khi nói về độ phức tạp, phải chỉ rõ đối tượng được phân tích:

| Đối tượng phân tích | Chính sách tăng từng ô |
| --- | --- |
| Một lần `append` khi còn chỗ dự trữ | O(1) |
| Một lần `append` khi có `m` phần tử và `size = capacity = m` | Θ(m) cho sao chép và ghi trong mô hình chi phí ô |
| Cả `n` lần `append` từ mảng rỗng, luôn cấp phát thêm một ô khi đầy | Θ(n²) |
| Chi phí **khấu hao** trên mỗi lần trong chuỗi `n` thao tác đó | Θ(n) |

Từ tổng `T(n)=\Theta(n²)`, chia cho số thao tác `n` cho ta chi phí khấu hao:

\[
\frac{T(n)}{n}=\Theta(n).
\]

Điều này khác với **O(1) khấu hao** của mảng động thường gặp khi dung lượng tăng theo hệ số cố định lớn hơn 1. Cụm từ “mảng động thêm cuối O(1) khấu hao” luôn cần đi kèm giả định thích hợp về **chính sách tăng trưởng**.

Ngoài ra, không nên diễn giải rằng *một thao tác append có độ phức tạp O(n²)*: một lần mở rộng với `n` phần tử cũ chỉ cần sao chép khoảng `n` phần tử, tức **O(n)**. Chính **nhiều lần mở rộng liên tiếp** làm tổng chi phí của chuỗi tăng đến bậc hai.

## 6. Đối chiếu với tăng dung lượng theo cấp số nhân

Một lựa chọn phổ biến là khi bộ đệm đầy thì tăng lên gấp đôi:

```text
Nếu capacity == 0:  newCapacity = 1
Nếu capacity > 0:   newCapacity = 2 * capacity
```

Lúc này `capacity` thay đổi như sau:

```text
0 -> 1 -> 2 -> 4 -> 8 -> 16 -> 32 -> ...
```

Các lần mở rộng sẽ sao chép lần lượt `0, 1, 2, 4, 8, 16, ...` phần tử cũ. Dù mỗi lần mở rộng lớn khá tốn công, **số lần phải mở rộng thưa hơn**. Tổng số bản sao trong `n` lần thêm bị chặn bởi tổng cấp số nhân và nhỏ hơn `2n`:

\[
1+2+4+\cdots+2^r=2^{r+1}-1<2n
\]

với `2^r` là dung lượng cũ lớn nhất đã phải sao chép và `2^r<n`. Khi chưa từng sao chép, tổng bằng 0.

Vì thêm `n` phần tử mới còn cần `n` lần ghi, tổng công của `n` lần thêm là **O(n)**. Chia đều cho `n` thao tác: **O(1) khấu hao** cho mỗi lần thêm cuối. Một lần phải cấp phát lại vẫn có thể mất O(n), nhưng phần lớn các lần thêm chỉ tốn O(1).

### So sánh bằng số liệu

Với hai chính sách cùng bắt đầu từ `capacity = 0`:

| `n` lần thêm | Tăng từng ô: số bản sao | Nhân đôi: số bản sao | Dung lượng cuối khi nhân đôi |
| ---: | ---: | ---: | ---: |
| 6 | 15 | 7 | 8 |
| 8 | 28 | 7 | 8 |
| 10 | 45 | 15 | 16 |
| 1.000 | 499.500 | 1.023 | 1.024 |

Với `n = 1.000`, chính sách tăng từng ô thực hiện gần nửa triệu lần sao chép phần tử cũ; nhân đôi chỉ cần sao chép 1.023 phần tử cũ trên tất cả các đợt mở rộng. Đổi lại, chính sách nhân đôi tại thời điểm đó có **24 ô dự trữ**.

Đây không phải bảo đảm rằng nhân đôi luôn nhanh hơn một tỷ lệ cụ thể trên mọi máy. Chi phí cấp phát, sao chép đối tượng và quản lý bộ nhớ phụ thuộc môi trường. Bảng chứng minh **sự khác biệt về tốc độ tăng của tổng công việc**.

## 7. Mã Java để thấy tổng số phần tử bị sao chép

Chương trình sau dùng cùng một lớp mảng động số nguyên, chỉ thay quy tắc chọn dung lượng mới. Hai chế độ có chung cách thêm: khi đầy, tạo mảng mới, sao chép toàn bộ `size` phần tử cũ rồi thêm giá trị mới.

```java
import java.util.Arrays;

public class OneSlotGrowthDemo {
    static class IntDynamicArray {
        private int[] buffer = new int[0];
        private int size = 0;
        private final boolean doubleCapacity;
        private long copiedElements = 0;
        private int allocations = 0;

        IntDynamicArray(boolean doubleCapacity) {
            this.doubleCapacity = doubleCapacity;
        }

        void append(int value) {
            if (size == buffer.length) {
                int oldCapacity = buffer.length;
                int newCapacity;

                if (doubleCapacity) {
                    if (oldCapacity > Integer.MAX_VALUE / 2) {
                        throw new IllegalStateException("Capacity too large");
                    }
                    newCapacity = oldCapacity == 0 ? 1 : oldCapacity * 2;
                } else {
                    if (oldCapacity == Integer.MAX_VALUE) {
                        throw new IllegalStateException("Capacity too large");
                    }
                    newCapacity = oldCapacity + 1;
                }

                // size == oldCapacity ở mỗi lần mở rộng trong ví dụ.
                int[] newBuffer = Arrays.copyOf(buffer, newCapacity);
                copiedElements += size;
                allocations++;
                buffer = newBuffer;
            }

            buffer[size] = value;
            size++;
        }

        String stats() {
            return "size=" + size
                + ", capacity=" + buffer.length
                + ", copied=" + copiedElements
                + ", allocations=" + allocations;
        }
    }

    public static void main(String[] args) {
        for (int n : new int[] {10, 1000}) {
            IntDynamicArray growByOne = new IntDynamicArray(false);
            IntDynamicArray growByTwo = new IntDynamicArray(true);

            for (int i = 0; i < n; i++) {
                growByOne.append(i);
                growByTwo.append(i);
            }

            System.out.println("n=" + n);
            System.out.println("Tang 1 o:  " + growByOne.stats());
            System.out.println("Nhan doi:  " + growByTwo.stats());
        }
    }
}
```

Kết quả dự kiến:

```text
n=10
Tang 1 o:  size=10, capacity=10, copied=45, allocations=10
Nhan doi:  size=10, capacity=16, copied=15, allocations=5
n=1000
Tang 1 o:  size=1000, capacity=1000, copied=499500, allocations=1000
Nhan doi:  size=1000, capacity=1024, copied=1023, allocations=11
```

Biến `copiedElements` ở đây đo số **phần tử logic cũ** phải sao chép, chưa bao gồm chi phí khởi tạo ô dự trữ, thao tác cấp phát bộ nhớ, thu gom rác hay thời gian chạy thực tế. Với `int[]`, `Arrays.copyOf` tạo mảng mới và sao chép các giá trị số nguyên. Với một mảng tham chiếu đối tượng, sao chép thường chỉ chuyển các tham chiếu, không nhân bản sâu đối tượng.

Cài đặt Java minh họa không phải bộ sưu tập hoàn chỉnh: nó chưa có `get`, xóa hoặc chèn giữa. Với mảng thực tế, giới hạn dung lượng do runtime quy định có thể thấp hơn `Integer.MAX_VALUE` và thao tác cấp phát còn có thể thất bại vì không đủ bộ nhớ.

## 8. Vậy tăng từng ô có ưu điểm gì không?

Có: khi chỉ thêm và không xóa, nếu luôn cấp phát đúng một ô thêm mỗi lần đầy thì sau mỗi lần thêm sẽ có `capacity = size`. Ở trạng thái ổn định, **không còn ô lưu trữ dư**.

Tuy nhiên, việc “không dư ô” cần được hiểu thận trọng. Tại mỗi lần thay bộ đệm, chương trình thường phải đồng thời giữ:

- Bộ đệm cũ có `k - 1` ô.
- Bộ đệm mới có `k` ô.

Trong lúc chuyển sang mảng có `k` phần tử, tổng số ô của hai vùng có thể là `2k - 1`, chưa tính các chi phí khác. Với môi trường thu gom rác, vùng cũ còn có thể chưa được thu hồi ngay. Như vậy, chính sách tăng từng ô không có nghĩa là **bộ nhớ đỉnh** luôn thấp nhất.

| Tiêu chí | Tăng một ô khi đầy | Nhân đôi khi đầy |
| --- | --- | --- |
| Số ô dư sau mỗi lần thêm từ mảng rỗng | 0 | Có thể có ô dự trữ |
| Số lần mở rộng trong `n` lần thêm | `n` | O(log n) |
| Tổng phần tử cũ phải sao chép | Θ(n²) | O(n) |
| Thêm cuối, chi phí khấu hao | Θ(n) trên chuỗi `n` lần thêm | O(1) |
| Bộ nhớ vùng ô ở trạng thái ổn định | Θ(n), hệ số gần 1 | Θ(n), có thể lớn hơn số phần tử |
| Chi phí cấp phát và thu hồi | Diễn ra rất thường xuyên | Ít lần hơn |

Ở bảng này, `O(log n)` là số lần mở rộng dung lượng hình học trong quá trình thêm `n` phần tử. Cả hai chính sách đều cần **Θ(n) bộ nhớ ổn định** để chứa `n` phần tử; điểm khác nhau là hằng số của lượng bộ nhớ dự trữ và công sao chép.

### Khi biết trước số phần tử cần thêm

Nếu biết chắc cần khoảng 10.000 phần tử, cấp phát trước một bộ đệm có đủ chỗ cho chúng có thể là lựa chọn hợp lý. Lúc này cấu trúc có thể thêm 10.000 phần tử mà **không cần cấp phát lại trong chuỗi thêm**, dù ban đầu đã xin nhiều ô.

Đây là cách làm khác về bản chất với “cấp phát lại thêm một ô sau mỗi lần thêm”. Một số thư viện hỗ trợ `reserve` hoặc `ensureCapacity` để chuẩn bị sức chứa; những thao tác ấy **không tự tăng `size`** hay tạo thêm phần tử logic.

Ví dụ, `std::vector::reserve(k)` trong C++ và `ArrayList.ensureCapacity(k)` trong Java có thể giúp giảm số lần mở rộng nếu biết trước nhu cầu. Việc dành sẵn chỗ có thể cần một lần cấp phát và sao chép, nhưng tránh nhiều đợt lặp lại sau đó.

## 9. Tránh các nhầm lẫn thường gặp

1. **“Mảng động vốn luôn có thêm cuối O(1) khấu hao.”** Cần xét chính sách tăng dung lượng. Tăng từng đơn vị làm tổng chi phí của một chuỗi dài trở thành Θ(n²).
2. **“Chi phí Θ(n²) xảy ra trong một lần thêm.”** Không. Mỗi lần thêm phải sao chép tối đa số phần tử hiện có, tức O(n); Θ(n²) là **tổng chi phí** khi lặp lại nhiều lần theo chính sách tăng từng ô.
3. **“Bộ đệm không dư ô tức là không tốn thêm bộ nhớ.”** Mỗi lần cấp phát lại có thể tạm thời giữ cả bộ đệm cũ và mới; chi phí quản lý cũng tồn tại.
4. **“Tăng từng ô đồng nghĩa thêm chỉ tốn O(1).”** O(1) chỉ áp dụng khi còn chỗ sẵn. Với chính sách đang xét, ngay sau lần thêm trước bộ đệm đã đầy, nên lần tiếp theo phải sao chép.
5. **“Tăng dung lượng thêm một số ô cố định khác 1 là đủ.”** Nếu luôn chỉ cộng một hằng số `d > 0` khi đầy, số lần mở rộng vẫn tỷ lệ với `n` và tổng số phần tử phải sao chép vẫn là Θ(n²) khi `d` cố định.
6. **“Chỉ nhìn số lần cấp phát là đủ.”** Một lần cấp phát khi mảng đã có rất nhiều phần tử có thể phải sao chép nhiều ô. Cần tính cả **tần suất** và **kích thước** của mỗi lần mở rộng.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Bắt đầu với `size = capacity = 0`, luôn tăng dung lượng thêm một ô khi đầy. Sau khi thêm năm phần tử, đã phải sao chép bao nhiêu phần tử cũ qua tất cả các lần mở rộng?

**Đáp án:** `0 + 1 + 2 + 3 + 4 = 10` phần tử cũ. Cuối cùng `size = capacity = 5`.

**Câu 2.** Khi thêm phần tử thứ 101 theo chính sách tăng từng ô, lần thêm này sao chép bao nhiêu phần tử cũ? Độ phức tạp riêng của nó là gì?

**Đáp án:** Sao chép 100 phần tử cũ, ghi phần tử thứ 101. Độ phức tạp của lần thêm là Θ(100) theo số phần tử hiện có, tổng quát là O(m) với `m` phần tử trước thao tác.

**Câu 3.** Một chương trình thực hiện 1.000 lần thêm cuối từ mảng rỗng, mỗi lần phải mở rộng thêm một ô. Tổng số phần tử cũ bị sao chép bằng bao nhiêu?

**Đáp án:** `1.000 × 999 / 2 = 499.500`. Đây là tổng bậc hai theo số thao tác.

**Câu 4.** Cùng 1.000 lần thêm đó, nếu mảng tăng gấp đôi dung lượng mỗi khi đầy (khởi đầu bằng một ô), tổng phần tử cũ được sao chép bằng bao nhiêu?

**Đáp án:** Các lần sao chép chứa `1, 2, 4, ..., 512` phần tử, nên tổng là `1.023`. Dung lượng cuối là 1.024 ô.

**Câu 5.** Nếu mảng dùng chính sách tăng dung lượng thêm đúng 10 ô mỗi lần đầy, vì sao với `n` đủ lớn tổng thời gian thêm cuối vẫn có thể là Θ(n²)?

**Đáp án:** Cứ khoảng 10 lần thêm thì lại phải sao chép phần tử cũ. Có Θ(n) lần mở rộng, trong đó kích thước dữ liệu phải sao chép tăng tuyến tính. Tổng các lượng sao chép là một cấp số cộng bậc hai khi 10 là hằng số không phụ thuộc `n`.

**Câu 6.** Có phải muốn tránh tổng chi phí Θ(n²) thì nhất thiết phải nhân đôi `capacity`?

**Đáp án:** Không. Bất kỳ quy tắc tăng hình học với **hệ số cố định lớn hơn 1** đều có thể cho thêm cuối O(1) khấu hao trong điều kiện phân tích phù hợp. Nhân đôi dễ cài đặt và dễ chứng minh, nhưng không phải hệ số duy nhất.

**Câu 7.** Nếu biết trước cần thêm đúng 500 phần tử và có thể cấp phát trước 500 ô, phần công sao chép do mở rộng bộ đệm trong chuỗi thêm là bao nhiêu?

**Đáp án:** Bằng 0, giả sử việc dành sẵn bộ đệm đã thành công và không có thao tác khác thay đổi dung lượng. Ta vẫn phải ghi 500 phần tử mới, nhưng không phải mở rộng trong lúc thêm.

Khi phân tích mảng động, hãy đặt câu hỏi **“mỗi lần hết chỗ, cấu trúc cấp phát lại bao nhiêu ô và phải chuyển bao nhiêu phần tử cũ?”**. Việc tăng từng đơn vị khiến nhiều phần tử bị sao chép lặp lại và tạo tổng chi phí Θ(n²) sau `n` lần thêm. Cấp phát dư theo hệ số hoặc dành sẵn chỗ khi biết nhu cầu giúp giảm số đợt sao chép, đánh đổi một lượng bộ nhớ dự trữ để cải thiện hiệu năng.
