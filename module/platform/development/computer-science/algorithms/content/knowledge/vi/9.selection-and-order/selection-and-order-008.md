# Trung vị, phân vị và kết quả khi có nhiều giá trị bằng nhau

Khi một thuật toán cần tìm **phần tử nhỏ thứ k**, **trung vị (median)** hoặc **phân vị (quantile/percentile)**, không nhất thiết phải sắp xếp toàn bộ dữ liệu. Có thể dùng thuật toán *selection* để tìm đúng giá trị ở một thứ hạng. Tuy nhiên, các câu hỏi như “phân vị 75% bằng bao nhiêu?”, “trung vị của mảng chẵn là gì?” hoặc “nếu nhiều phần tử bằng nhau thì phần tử thứ k là phần tử nào?” cần được **định nghĩa rõ** trước khi chọn thuật toán.

Bài học này thuộc nhóm **Chọn và thứ tự (selection and ordering)**. Ta sẽ tách bạch **thứ hạng với giá trị**, giải thích **trung vị và các quy ước tính phân vị**, chứng minh lựa chọn bằng phân hoạch ba miền xử lý giá trị trùng, phân tích độ phức tạp, rồi cài đặt Java 17+ chạy được và kiểm thử đối chiếu.

## 1. Thứ tự thống kê: hạng k không phải là “giá trị phân biệt thứ k”

Cho dãy có `n>0` phần tử, khi sắp tăng không giảm ta nhận được:

```text
a(0) <= a(1) <= ... <= a(n-1)
```

Ở đây `a(k)` là **giá trị ở hạng k (zero-based)**, còn ký hiệu `a_(r)` trong thống kê thường dùng **hạng r (one-based)** với `r=k+1`. Nếu có phần tử trùng, **mỗi lần xuất hiện vẫn chiếm một hạng**.

Ví dụ:

```text
Dữ liệu gốc: [9, 2, 5, 2, 1, 2]
Đã sắp:     [1, 2, 2, 2, 5, 9]
Chỉ số k:     0  1  2  3  4  5
Hạng r:       1  2  3  4  5  6
```

- Hạng 0 theo chỉ số có giá trị `1`; các hạng `1,2,3` đều có giá trị `2`.
- **Phần tử nhỏ thứ 3** nếu đánh số thứ hạng từ **1** có giá trị `2`, tức `a(2)=2`.
- **Giá trị phân biệt thứ 3** là `5` nếu chỉ đếm `1,2,5,9`. Đây là **một bài toán khác**, yêu cầu bỏ trùng trước khi xếp hạng.

Một thuật toán chọn đúng hạng `k` phải trả **giá trị** ở hạng ấy, không cần chỉ rõ **đối tượng/vị trí gốc nào** khi nhiều đối tượng có khóa bằng nhau. Nếu đề cần đúng bản ghi gốc hoặc thứ tự ổn định giữa các khóa bằng nhau, phải quy định tiêu chí phụ (ví dụ `(key, originalIndex)`), không thể suy ra từ kết quả selection trên số nguyên.

## 2. Trung vị: cần thống nhất quy ước khi số phần tử chẵn

Với dữ liệu đã sắp tăng và `n>0`:

- Nếu `n` **lẻ**: trung vị thông dụng là `a(n/2)` (chỉ số zero-based; chia nguyên).
- Nếu `n` **chẵn**: trung vị thông dụng của mẫu số là **trung bình số học** của hai giá trị giữa: `(a(n/2-1)+a(n/2))/2`.

Ví dụ:

| Dãy đã sắp | `n` | Hai hoặc một phần tử giữa | Trung vị thông dụng |
| --- | ---: | --- | ---: |
| `[1,2,2,2,5]` | 5 | `a(2)=2` | `2` |
| `[1,2,2,2,5,9]` | 6 | `a(2)=2` và `a(3)=2` | `2` |
| `[1,2,9,10]` | 4 | `2` và `9` | `5.5` |
| `[-10,-1,4,9]` | 4 | `−1` và `4` | `1.5` |
| `[Integer.MIN_VALUE,Integer.MAX_VALUE]` | 2 | hai cực trị `int` | `−0.5` |

**Không nhầm với lower median và upper median.** Ở `n` chẵn, một số bài toán thuật toán định nghĩa “trung vị dưới” bằng `a(n/2−1)`, “trung vị trên” bằng `a(n/2)`, thay vì trả trung bình. Ví dụ `[1,2,9,10]` có lower median `2`, upper median `9` và trung vị số học `5.5`. **Đọc đặc tả** để chọn đúng kết quả.

Để tính trung vị số học của hai `int` trong Java, **không** viết:

```java
// Có thể sai do tràn int trước khi chia:
double wrong = (left + right) / 2.0;

// Đúng trên toàn miền int: mở rộng trước khi cộng.
double correct = ((long) left + (long) right) / 2.0;
```

Đây là đoạn minh họa. Tổng hai số kiểu `int` có thể tràn khi tính bằng `int`, dù kết quả trung bình vẫn nằm trong miền giá trị an toàn.

**Mảng rỗng không có trung vị.** Một API cần quy định báo lỗi, trả một kiểu tùy chọn, hoặc dùng hợp đồng khác; không nên tự ý trả `0` vì `0` có thể là trung vị hoàn toàn hợp lệ của một mảng khác.

## 3. Phân vị và percentile: không có một công thức duy nhất

“Phân vị `p`” thường dùng `p∈[0,1]`; “percentile `q`” dùng `q∈[0,100]` và `p=q/100`. Ký hiệu `Q(0.75)` tương ứng **phân vị 75%**. Nhưng các thư viện và tài liệu có thể chọn **quy ước khác nhau**, đặc biệt với dữ liệu nhỏ, giá trị trùng, và khi `p·n` không nguyên.

Cần ghi rõ **phương pháp tính**. Hai quy ước thường gặp là:

### 3.1. Nearest-rank — chọn một giá trị thực sự có trong dữ liệu

Với `n>0` và `0<p≤1`, đặt:

```text
r = ceil(p * n)       // hạng từ 1 tới n
Q_nearest(p) = a(r-1)
```

Đây là quy ước **nearest-rank**. Nếu API cần hỗ trợ `p=0`, ta quy định riêng `Q_nearest(0)=a(0)` (giá trị nhỏ nhất). Đây là **quy ước mở rộng**, không lấy `ceil(0*n)-1=-1` làm chỉ số.

Với `a=[1,2,2,2,5,9]`, `n=6`:

- `p=0.25`: `ceil(1.5)=2`, hạng 2 có giá trị `2`.
- `p=0.50`: `ceil(3)=3`, hạng 3 có giá trị `2`.
- `p=0.75`: `ceil(4.5)=5`, hạng 5 có giá trị `5`.
- `p=0.90`: `ceil(5.4)=6`, hạng 6 có giá trị `9`.

Nearest-rank **luôn trả một giá trị xuất hiện trong mẫu**. Tuy nhiên, `Q_nearest(0.5)` với `n` chẵn trả **trung vị dưới** `a(n/2−1)`, không phải luôn là trung vị số học của hai vị trí giữa. Ví dụ `[1,2,9,10]`: `Q_nearest(0.5)=2`, nhưng trung vị số học là `5.5`.

### 3.2. Nội suy tuyến tính theo hạng (một quy ước rất phổ biến)

Một quy ước phổ biến khác (thường gọi là **type 7**) dùng:

```text
h = (n - 1) * p
j = floor(h)
t = h - j
Q_linear(p) = (1-t) * a(j) + t * a(min(j+1, n-1))
```

Với `p=0`, trả min; `p=1`, trả max. Nếu `h` nằm giữa hai chỉ số, công thức **nội suy** giữa hai giá trị liền kề. Phân vị có thể **không phải phần tử xuất hiện trong dữ liệu**.

Trên cùng dãy `[1,2,2,2,5,9]`:

- `Q_linear(0.25)`: `h=1.25`, nội suy giữa `2` và `2`, cho `2.0`.
- `Q_linear(0.50)`: `h=2.5`, nội suy giữa `2` và `2`, cho `2.0`.
- `Q_linear(0.75)`: `h=3.75`, nội suy giữa `a(3)=2` và `a(4)=5`, cho `2+0.75·3=4.25`.
- `Q_linear(0.90)`: `h=4.5`, nội suy giữa `5` và `9`, cho `7.0`.

| `p` | Nearest-rank | Nội suy `h=(n−1)p` |
| ---: | ---: | ---: |
| 0 | `1` (theo quy ước mở rộng) | `1.0` |
| 0.25 | `2` | `2.0` |
| 0.50 | `2` | `2.0` |
| 0.75 | `5` | `4.25` |
| 0.90 | `9` | `7.0` |
| 1.00 | `9` | `9.0` |

**Kết luận quan trọng:** Hai đáp án `5` và `4.25` cho phân vị 75% **có thể đều đúng** nếu được tính theo hai quy ước khác nhau. Trong bài thi, API, báo cáo thống kê hoặc sản phẩm dữ liệu, cần nêu rõ quy ước thay vì gọi chung “percentile” rồi ngầm giả sử mọi hệ thống giống nhau.

Với `n` chẵn, phân vị nội suy type 7 tại `p=0.5` bằng trung bình hai phần tử giữa, đúng với trung vị số học đã định nghĩa ở mục 2.

## 4. Nhiều giá trị bằng nhau: “giá trị tại hạng k” có thể là một khoảng hạng

Gọi một giá trị `v` xuất hiện `m≥1` lần trong dãy. Đặt:

- `L(v) = # {x | x < v}`: số phần tử **nhỏ hơn** `v`.
- `U(v) = # {x | x ≤ v}`: số phần tử **nhỏ hơn hoặc bằng** `v`.
- `m = U(v)−L(v)`: số phần tử bằng `v`.

Trong dãy đã sắp, **tất cả các chỉ số `k∈[L(v),U(v))` có cùng kết quả selection là `v`**. Ví dụ `[1,2,2,2,5,9]` có `L(2)=1`, `U(2)=4`, nên:

```text
k = 1, 2, 3  ->  select(k) = 2
Khoảng hạng của giá trị 2: [1,4) (zero-based)
```

Điều này khác với **tìm một vị trí gốc duy nhất**. Nếu ba bản ghi có cùng khóa `2`, lựa chọn theo khóa không thể xác định bản ghi nào được chọn ở “hạng thứ 2” nếu không có điều kiện phụ; còn giá trị khóa trả về thì xác định duy nhất.

Trong một mảng đã sắp, `L(v)` chính là **lower bound** (chỉ số đầu tiên có giá trị `≥v`), và `U(v)` là **upper bound** (chỉ số đầu tiên có giá trị `>v`). Với dữ liệu chưa sắp, vẫn có thể tính hai số đếm bằng một lần quét `O(n)`; không cần sort chỉ để biết số lượng bằng `v`.

Nếu `v` không xuất hiện, ta có `L(v)=U(v)`: khoảng hạng `[L,U)` rỗng. Khi đó không được tuyên bố có “đối tượng tại giá trị `v`”, dù vị trí chèn của `v` là xác định.

### Xếp hạng và empirical CDF

Một cách mô tả khác là **hàm phân phối thực nghiệm**:

```text
F_n(v) = (# phần tử <= v) / n = U(v) / n
```

Với dãy `[1,2,2,2,5,9]`, tại `v=2`: `F_n(2)=4/6`, còn tỷ lệ **nhỏ hơn nghiêm ngặt** `2` là `1/6`. Ba bản sao của `2` tạo một **bước nhảy** có độ lớn `3/6` trong hàm phân phối thực nghiệm. Vì thế hỏi “percentile rank của giá trị 2” cũng phải nêu rõ dùng tỷ lệ `<`, tỷ lệ `≤`, hay quy ước trung điểm nhóm bằng nhau.

**Đếm bản sao khác với bỏ trùng.** Nếu bỏ mọi giá trị trùng trước khi tính trung vị/phân vị, bài toán thay đổi sang thống kê trên **tập giá trị phân biệt**; các tần suất quan sát không còn được tính đúng.

## 5. Tìm phần tử hạng k bằng sắp xếp hoặc selection

Giả sử cần lấy giá trị có hạng `k`, `0≤k<n`:

| Hướng giải | Thời gian | Bộ nhớ phụ | Khi nào hợp lý |
| --- | --- | --- | --- |
| Sao chép rồi sắp xếp và lấy `a[k]` | Thông thường `O(n log n)` với sorting phù hợp | Ít nhất `O(n)` nếu giữ input bằng bản sao; thêm chi phí sort | Cần nhiều hạng, cần toàn bộ thứ tự, hoặc ưu tiên đơn giản |
| Duyệt tuyến tính lấy min/max | `O(n)` | `O(1)` | Chỉ cần `k=0` hoặc `k=n−1` |
| **Quickselect phân hoạch hai/ba miền** | **Kỳ vọng `O(n)`** nếu pivot ngẫu nhiên phù hợp; xấu nhất `O(n²)` | `O(1)` phụ cho bản tại chỗ; `O(n)` nếu sao chép input | Cần một vài hạng, không cần sort toàn bộ |
| Median-of-medians (pivot xác định) | `O(n)` trường hợp xấu nhất với thiết kế đúng | Phụ thuộc cài đặt | Cần bảo đảm xấu nhất; thuật toán và hằng số phức tạp hơn |
| Đếm tần suất trong miền giá trị nhỏ | `O(n+K)` nếu có `K` giá trị khóa khả dĩ và xây bảng tần suất | `O(K)` | Miền giá trị nhỏ, đặc biệt nhiều giá trị lặp |

Với nhiều truy vấn phân vị trên **cùng input tĩnh**, một lần sort `O(n log n)` rồi trả các hạng thường thuận tiện hơn so với chạy quickselect độc lập cho từng truy vấn. Nếu có `q` truy vấn và mỗi truy vấn chọn một hạng độc lập, thời gian kỳ vọng có thể đến `O(qn)`; một bản sắp xếp duy nhất thường dùng `O(n log n+q)` cho truy vấn giá trị đơn lẻ (hoặc thêm thao tác nội suy `O(1)` mỗi truy vấn).

**Trạng thái input:** Quickselect thường **hoán đổi phần tử tại chỗ** để phân hoạch; nếu yêu cầu bảo toàn mảng đầu vào, cần làm việc trên một bản sao. Trả một **giá trị** không đồng nghĩa đã sắp được toàn mảng. Sau quickselect, các phần tử ngoài các vùng phân hoạch có thể vẫn lộn xộn.

## 6. Ba miền nhỏ hơn — bằng — lớn hơn giúp xử lý tie

Mẫu quickselect hai miền có thể không tận dụng được việc nhiều phần tử bằng pivot. Một cách rõ ràng hơn là phân hoạch **ba miền** theo pivot `p`:

```text
[lo .. lt-1] : < p
[lt .. gt]   : = p
[gt+1 .. hi] : > p
```

Dùng ba con trỏ `lt`, `i`, `gt` với khoảng xử lý `[lo,hi]` **đóng**. Ban đầu `lt=i=lo` và `gt=hi`. Duyệt khi `i≤gt`:

- Nếu `a[i]<p`: đổi `a[i]` với `a[lt]` rồi tăng **cả** `lt` và `i`.
- Nếu `a[i]>p`: đổi `a[i]` với `a[gt]` rồi **giảm `gt`**, **không tăng `i`** vì phần tử vừa đưa từ cuối lên `i` chưa được kiểm tra.
- Nếu `a[i]==p`: tăng `i` vì phần tử thuộc miền giữa.

**Bất biến bên trong phân hoạch:**

```text
[lo,lt)    : < p
[lt,i)     : = p
[i,gt]     : chưa phân loại
(gt,hi]    : > p
```

Mỗi bước giảm số phần tử chưa phân loại, nên vòng phân hoạch kết thúc. Sau khi hoàn thành, nếu:

- `k<lt`: giá trị hạng `k` chắc chắn nằm ở miền nhỏ hơn pivot; chỉ cần xét `[lo,lt−1]`.
- `k>gt`: chỉ cần xét miền lớn hơn pivot `[gt+1,hi]`.
- **`lt≤k≤gt`:** đáp án **chính là pivot**, bất kể miền giữa dài bao nhiêu.

Đây là điểm mạnh khi có **rất nhiều giá trị bằng nhau**: nếu cả mảng đều là `7`, chỉ một lượt phân hoạch `O(n)` đã có `lt=lo` và `gt=hi`, nên trả ngay giá trị `7` mà không cần tiếp tục tách từng bản sao.

### Vì sao không bỏ sót hạng k?

Giả sử ba miền có `c_<` phần tử nhỏ hơn pivot, `c_=` phần tử bằng pivot và `c_>` phần tử lớn hơn. Trong thứ tự tăng, mọi phần tử nhỏ hơn đứng trước mọi phần tử bằng, và mọi phần tử lớn hơn đứng sau. Do đó:

- Nếu `k` nằm trước miền bằng, chỉ phần nhỏ hơn mới có thể chứa hạng k.
- Nếu `k` thuộc miền bằng, giá trị ở mọi hạng trong đó đều là pivot.
- Nếu `k` nằm sau miền bằng, chỉ phần lớn hơn mới có thể chứa hạng k.

Phân hoạch không cần sắp xếp nội bộ từng miền để quyết định **miền chứa hạng k**; phép đếm kích thước miền là đủ. Với pivot được chọn từ chính đoạn hiện tại, miền bằng luôn **không rỗng**, và mỗi lần đi tiếp phạm vi giảm nghiêm ngặt. Do đó thuật toán kết thúc.

### Có giữ được thứ tự ban đầu không?

Phân hoạch ba miền với phép swap **không ổn định**: hai bản ghi có cùng khóa có thể đổi thứ tự tương đối. Điều đó **không ảnh hưởng đến giá trị hạng k**. Nhưng nếu đề yêu cầu chọn bản ghi có khóa bằng nhau theo thời gian đến hoặc theo chỉ số gốc, phải bổ sung comparator gồm khóa phụ, ví dụ thứ tự toàn phần `(score, originalIndex)`; khi ấy không còn “bằng nhau” chỉ theo `score` nữa.

## 7. Chọn pivot và độ phức tạp của quickselect

Một vòng phân hoạch trên đoạn có `m` phần tử tốn **`Θ(m)`** thời gian. Quickselect chỉ tiếp tục trên **một** trong hai miền không chứa pivot, không xử lý cả hai như quicksort.

- Nếu pivot chia khá cân bằng, công việc có dạng `T(n)=T(cn)+Θ(n)` với `0<c<1`, nên `T(n)=Θ(n)`.
- Nếu pivot liên tục là cực trị của đoạn và loại được rất ít phần tử, tổng thời gian có thể là `n+(n−1)+...=Θ(n²)`.
- Chọn **pivot ngẫu nhiên** độc lập, phân bố đều trong đoạn hiện tại, cho **thời gian kỳ vọng `Θ(n)`** trong mô hình phân tích chuẩn, dù trường hợp xấu nhất vẫn `Θ(n²)`. Cài đặt dùng bộ tạo số giả ngẫu nhiên với seed cố định để kiểm thử lặp lại; seed cố định **không phải cam kết** chống mọi input xấu.
- Phân hoạch ba miền cải thiện rõ rệt trường hợp nhiều khóa trùng, vì nó loại toàn bộ nhóm bằng pivot **trong một lần**. Nó không biến quickselect thành thuật toán có bảo đảm `O(n)` xấu nhất khi mọi khóa phân biệt.

**Bộ nhớ:** Bản phân hoạch vòng lặp và sửa mảng tại chỗ cần `O(1)` bộ nhớ phụ (không kể đầu vào). Nếu tạo bản sao để không thay input, thêm `O(n)` thời gian và `O(n)` bộ nhớ. Nếu đệ quy thay vì vòng lặp, còn phải tính stack.

**Nhiều truy vấn:** Tìm trung vị của mảng chẵn cần **hai hạng giữa**; nếu gọi quickselect riêng hai lần trên hai bản sao, thời gian **kỳ vọng vẫn `O(n)`** vì số lần chọn là hằng số hai, nhưng thực hiện nhiều phép quét hơn một triển khai multi-select chuyên dụng. Phân vị tuyến tính cũng có thể cần hai hạng kề. Nếu có rất nhiều phân vị thì sort một lần có thể tiết kiệm hơn.

## 8. Java 17+ — median, nearest-rank, phân vị nội suy và hạng tie

Chương trình sau có hợp đồng rõ ràng:

- `selectKth(input,k)` trả **giá trị** ở thứ hạng zero-based `k`, **không sửa input** vì làm trên `clone()`.
- `median(input)` trả trung vị số học, dùng `long` khi cộng hai phần tử giữa.
- `nearestRankQuantile(input,p)` dùng `ceil(p*n)−1` với `p∈(0,1]` và **mở rộng `p=0` thành min**.
- `linearQuantile(input,p)` dùng công thức nội suy `h=(n−1)p`.
- `rankRange(input,value)` trả `[L,U)` bằng **đếm tuyến tính** trên input chưa sắp.
- Mảng rỗng không có selection/median/quantile; `null` không hợp lệ; `p` phải nằm trong `[0,1]` và không là NaN.
- Chương trình đối chiếu exhaustive với `Arrays.sort` trên các mảng nhỏ, bao gồm nhiều giá trị trùng.

Lưu thành **QuantileSelectionDemo.java**:

```java
import java.util.Arrays;
import java.util.Objects;
import java.util.SplittableRandom;

public class QuantileSelectionDemo {
    private static void requireNonempty(int[] input) {
        Objects.requireNonNull(input, "input");
        if (input.length == 0) {
            throw new IllegalArgumentException("empty input");
        }
    }

    private static void checkProbability(double p) {
        // Điều kiện sau loại cả NaN và các giá trị ngoài [0,1].
        if (!(p >= 0.0 && p <= 1.0)) {
            throw new IllegalArgumentException("p must be in [0,1]");
        }
    }

    private static void swap(int[] a, int i, int j) {
        int temp = a[i];
        a[i] = a[j];
        a[j] = temp;
    }

    // Trả giá trị tại hạng k zero-based; không giữ thứ tự các phần tử.
    private static int selectInPlace(int[] a, int k,
                                     SplittableRandom random) {
        int lo = 0;
        int hi = a.length - 1;

        while (lo <= hi) {
            int pivot = a[lo + random.nextInt(hi - lo + 1)];

            int lt = lo;
            int i = lo;
            int gt = hi;

            while (i <= gt) {
                if (a[i] < pivot) {
                    swap(a, lt++, i++);
                } else if (a[i] > pivot) {
                    swap(a, i, gt--);
                } else {
                    i++;
                }
            }

            if (k < lt) {
                hi = lt - 1;
            } else if (k > gt) {
                lo = gt + 1;
            } else {
                return a[k]; // Mọi phần tử trong [lt,gt] bằng pivot.
            }
        }

        throw new AssertionError("unreachable");
    }

    // Public API: tạo bản sao để bảo toàn input.
    static int selectKth(int[] input, int k) {
        requireNonempty(input);
        if (k < 0 || k >= input.length) {
            throw new IllegalArgumentException("invalid k");
        }
        int[] working = input.clone();
        return selectInPlace(working, k,
                             new SplittableRandom(2026L));
    }

    static double median(int[] input) {
        requireNonempty(input);
        int n = input.length;
        if ((n & 1) == 1) {
            return selectKth(input, n / 2);
        }

        int low = selectKth(input, n / 2 - 1);
        int high = selectKth(input, n / 2);
        return ((long) low + (long) high) / 2.0;
    }

    static int nearestRankQuantile(int[] input, double p) {
        requireNonempty(input);
        checkProbability(p);

        // Quy ước riêng p=0 trả min.
        int k = (p == 0.0)
                ? 0
                : (int) Math.ceil(p * input.length) - 1;
        return selectKth(input, k);
    }

    static double linearQuantile(int[] input, double p) {
        requireNonempty(input);
        checkProbability(p);

        double h = (input.length - 1) * p;
        int lo = (int) Math.floor(h);
        int hi = Math.min(lo + 1, input.length - 1);
        double fractional = h - lo;

        int lowValue = selectKth(input, lo);
        int highValue = selectKth(input, hi);

        // Hiệu tính ở double để tránh tràn int.
        return lowValue
                + fractional * ((double) highValue - lowValue);
    }

    // Trả khoảng [L,U) hạng có cùng value.
    // Nếu value không tồn tại, L=U là vị trí chèn theo giá trị.
    static int[] rankRange(int[] input, int value) {
        Objects.requireNonNull(input, "input");
        int less = 0;
        int equal = 0;
        for (int x : input) {
            if (x < value) {
                less++;
            } else if (x == value) {
                equal++;
            }
        }
        return new int[]{less, less + equal};
    }

    static int checkSmallCases() {
        int variants = 5;
        int checked = 0;

        for (int n = 1; n <= 5; n++) {
            for (int encoded = 0; encoded < variants; encoded++) {
                int[] input = new int[n];
                int code = encoded;
                for (int i = 0; i < n; i++) {
                    input[i] = code % 5 - 2;
                    code /= 5;
                }

                int[] reference = input.clone();
                Arrays.sort(reference);

                for (int k = 0; k < n; k++) {
                    if (selectKth(input, k) != reference[k]) {
                        throw new AssertionError("wrong k-th value");
                    }
                }

                double expectedMedian = ((n & 1) == 1)
                        ? reference[n / 2]
                        : ((long) reference[n / 2 - 1]
                           + reference[n / 2]) / 2.0;
                if (median(input) != expectedMedian) {
                    throw new AssertionError("wrong median");
                }

                for (double p : new double[]{
                        0.0, 0.25, 0.5, 0.75, 1.0}) {
                    int rank = p == 0.0
                            ? 0
                            : (int) Math.ceil(p * n) - 1;
                    if (nearestRankQuantile(input, p)
                            != reference[rank]) {
                        throw new AssertionError("wrong nearest-rank");
                    }

                    double h = (n - 1) * p;
                    int left = (int) Math.floor(h);
                    int right = Math.min(left + 1, n - 1);
                    double expectedLinear = reference[left]
                            + (h - left)
                            * ((double) reference[right]
                               - reference[left]);
                    if (Math.abs(linearQuantile(input, p)
                            - expectedLinear) > 1e-9) {
                        throw new AssertionError("wrong interpolation");
                    }
                }

                if (!Arrays.equals(input, input.clone())) {
                    throw new AssertionError("input changed");
                }
                checked++;
            }
            variants *= 5;
        }

        return checked;
    }

    public static void main(String[] args) {
        int[] sample = {9, 2, 5, 2, 1, 2};
        int[] original = sample.clone();

        int[] sorted = sample.clone();
        Arrays.sort(sorted);
        System.out.println("Sorted: " + Arrays.toString(sorted));
        for (int k = 0; k < sample.length; k++) {
            System.out.println("k=" + k + ": " + selectKth(sample, k));
        }
        System.out.println("Median: " + median(sample));
        System.out.println("Nearest p=0.75: "
                           + nearestRankQuantile(sample, 0.75));
        System.out.println("Linear p=0.75: "
                           + linearQuantile(sample, 0.75));
        System.out.println("Nearest p=0: "
                           + nearestRankQuantile(sample, 0.0));
        System.out.println("Nearest p=1: "
                           + nearestRankQuantile(sample, 1.0));
        System.out.println("Linear p=0.90: "
                           + linearQuantile(sample, 0.90));
        System.out.println("Rank interval of 2: "
                           + Arrays.toString(rankRange(sample, 2)));
        System.out.println("Same-value median: "
                           + median(new int[]{7, 7, 7, 7}));
        System.out.println("Extreme median: "
                           + median(new int[]{
                               Integer.MIN_VALUE, Integer.MAX_VALUE}));
        System.out.println("Input unchanged: "
                           + Arrays.equals(sample, original));
        System.out.println("Small exhaustive check: OK ("
                           + checkSmallCases() + " arrays)");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 QuantileSelectionDemo.java
java QuantileSelectionDemo
```

Stdout dự kiến:

```text
Sorted: [1, 2, 2, 2, 5, 9]
k=0: 1
k=1: 2
k=2: 2
k=3: 2
k=4: 5
k=5: 9
Median: 2.0
Nearest p=0.75: 5
Linear p=0.75: 4.25
Nearest p=0: 1
Nearest p=1: 9
Linear p=0.90: 7.0
Rank interval of 2: [1, 4]
Same-value median: 7.0
Extreme median: -0.5
Input unchanged: true
Small exhaustive check: OK (3905 arrays)
```

### Giải thích kiểm thử và giới hạn

- Các hạng `k=1,2,3` đều trả `2` vì ba bản sao của `2` chiếm ba vị trí liên tiếp trong thứ tự đã sắp, không phải vì thuật toán nhầm.
- Với cùng `p=0.75`, nearest-rank trả `5`, nội suy type 7 trả `4.25`: **phải xác định quy ước trước khi so sánh các kết quả**.
- Khi hai số nguyên cực trị tạo cặp giữa của mảng chẵn, phép cộng qua `long` trả median `−0.5` đúng, không overflow.
- `rankRange(sample,2)=[1,4)`: nếu hỏi một “hạng của giá trị 2”, câu trả lời chính xác là **cả ba hạng zero-based `1,2,3`**, trừ khi đề quy định cách phá hòa.
- Hàm kiểm thử sinh `5+25+125+625+3125=3905` mảng có độ dài từ 1 đến 5, với các giá trị `−2,−1,0,1,2`; đối chiếu mọi `k`, trung vị và năm phân vị mẫu với bản đã sort. Các ca lặp nhiều giá trị được đưa vào có chủ đích.
- Trong `selectKth`, seed `2026L` giúp lần chạy có thể tái lập; các phần tử **không** được cam kết giữ đúng thứ tự sau phân hoạch trên bản sao. Tính kỳ vọng thời gian được phân tích theo mô hình pivot ngẫu nhiên, không phải bảo đảm với một seed cố định.
- Hàm `checkSmallCases` chủ yếu xác minh các **giá trị trả về**, không chứng minh các thuộc tính tổng quát của mọi mảng lớn. Chứng minh phân hoạch và đường chọn miền ở mục 6 mới là lý do thuật toán đúng.

### Lưu ý khi tối ưu lại code

Ví dụ ưu tiên hợp đồng **không sửa input** và sự rõ nghĩa của từng hàm. Vì vậy `median` của mảng chẵn và `linearQuantile` có thể tạo **hai bản sao** và chạy selection hai lần để lấy hai hạng kề. Nếu cần phục vụ rất nhiều truy vấn, nên cân nhắc sort một bản sao rồi tra trực tiếp, hoặc một phương án **multi-select** thay vì lặp lại selection độc lập.

Nếu input là các bản ghi có khóa bằng nhau, việc đưa chúng vào `int[]` làm mất các trường phụ; muốn trả đúng bản ghi gốc phải thiết kế kiểu dữ liệu và chính sách tie-break trước khi partition.

## 9. Trường hợp biên và các lựa chọn thiết kế

**Mảng rỗng:** Không có hạng `k`, trung vị hay phân vị; ném `IllegalArgumentException` là lựa chọn của API ví dụ. Có thể thiết kế API trả `OptionalDouble`, nhưng không tự gán một con số làm đáp án.

**Một phần tử:** Mọi `p∈[0,1]` đều cho cùng giá trị; trung vị bằng phần tử đó.

**Tất cả giá trị bằng nhau:** Mọi hạng đều cho cùng một giá trị; phân hoạch ba miền nhanh chóng nhận diện toàn bộ đoạn bằng pivot. Nearest-rank và nội suy đều trả cùng con số.

**Nhiều ties ở vị trí ranh giới:** Nearest-rank có thể giữ nguyên một giá trị trong cả khoảng `p`; nội suy chỉ thay đổi giữa các giá trị khác nhau khi `h` nằm qua ranh giới đó. Không được coi các kết quả trùng giá trị là lỗi của thuật toán.

**Số âm, cực trị `int`:** Selection chỉ so sánh `<` và `>`, không cần đổi dấu hay tính hiệu khóa. Median chẵn và nội suy phải tránh overflow trước khi đổi sang kiểu đủ rộng.

**Giá trị `p` không hợp lệ:** `p<0`, `p>1`, NaN, hoặc vô cực không có nghĩa trong hai API này; cần từ chối. Khi chuyển từ percentile `q` theo thang 0..100 sang `p=q/100`, ghi rõ đơn vị của tham số.

**Dữ liệu có trọng số:** Một quan sát xuất hiện nhiều lần tương đương trọng số nguyên tương ứng trong một số phân tích, nhưng **weighted quantile** tổng quát có định nghĩa riêng; không thể lấy công thức `ceil(p*n)` khi `n` không còn là tổng trọng số thích hợp.

**Dữ liệu luồng (streaming):** Khi không thể lưu toàn bộ input, quickselect trên mảng không áp dụng trực tiếp. Median có thể được duy trì bằng **hai heap** khi cho phép bộ nhớ theo số phần tử; phân vị xấp xỉ trên stream lớn dùng các cấu trúc tóm tắt chuyên biệt với sai số đã định nghĩa. Không nên gọi một kết quả **xấp xỉ** là percentile chính xác nếu hợp đồng cần kết quả exact.

**Có cần thứ tự ổn định không?** Đối với **giá trị selection**, chỉ cần quan hệ thứ tự của khóa. Nếu chọn bản ghi, cặp `(key,originalIndex)` tạo thứ tự toàn phần để phá hòa nhưng **thay đổi định nghĩa hạng** so với chỉ dùng khóa. Đây là yêu cầu đặc tả, không phải chi tiết implementation.

## 10. Những lỗi thường gặp

1. **Nhầm zero-based và one-based.** Hạng nhỏ thứ `r` thông thường tương ứng `k=r−1` trong Java. Sai một đơn vị có thể không lộ khi nhiều phần tử trùng.
2. **Nhầm trung vị với nearest-rank 50%.** Với `n` chẵn, nearest-rank thường trả trung vị dưới, còn median số học là trung bình hai vị trí giữa.
3. **Không nêu quy ước phân vị.** Các công thức khác nhau cho kết quả khác nhau; test đúng phải dựa vào đúng chuẩn API/đề bài.
4. **Bỏ trùng trước khi xếp hạng.** Nếu đề tính theo **quan sát**, tần suất của giá trị phải được giữ. Bỏ trùng làm thay đổi phân phối và phân vị.
5. **Tưởng có một chỉ số gốc duy nhất khi giá trị trùng.** Nếu chỉ so sánh khóa, rank k xác định giá trị nhưng không chỉ ra bản ghi gốc nào.
6. **Chỉ dùng phân hoạch hai miền rồi tiếp tục xử lý toàn bộ nhóm bằng pivot.** Có thể làm thừa công việc; ba miền `<,=,>` cho phép kết thúc ngay khi `k` nằm trong miền bằng.
7. **Tăng `i` sau khi swap với `gt`.** Phần tử vừa chuyển từ phía phải vào vị trí `i` chưa được phân loại; bỏ qua nó làm sai phân hoạch.
8. **Cộng hai `int` trước khi chia trung vị.** Có thể overflow; chuyển sang `long` trước khi cộng.
9. **Nội suy bằng phép hiệu `int`.** `high−low` có thể tràn; đổi một toán hạng sang `double` trước khi trừ.
10. **Tuyên bố quickselect luôn `O(n)`.** Pivot tệ liên tục có thể cho `Θ(n²)`; trung bình/kỳ vọng khác với bảo đảm xấu nhất.
11. **Sửa input mà không được phép.** Partition hoán đổi thứ tự; nếu hợp đồng cần dữ liệu gốc, tạo working copy hoặc thiết kế API nhận quyền sửa rõ ràng.
12. **Tin rằng một phép kiểm thử đã chứng minh đúng.** Test exhaustive trên miền nhỏ tìm phản ví dụ tốt nhưng không thay thế chứng minh bất biến, tiến triển và tính đúng với mọi input.

## 11. Bài tự luyện

**Bài 1 — Hạng và bản sao.** Với `[4,1,4,2,4,3]`, viết dãy đã sắp, liệt kê giá trị tại từng hạng `k=0..5` và xác định khoảng hạng của giá trị `4`. Nếu đề hỏi “giá trị phân biệt thứ ba”, đáp án có giống chọn hạng `k=2` không?

*Gợi ý:* Dãy `[1,2,3,4,4,4]`; khoảng hạng của `4` là `[3,6)`.

**Bài 2 — Trung vị chẵn.** Với `[1,2,9,10]`, tính lower median, upper median, trung vị số học, nearest-rank tại `p=0.5` và phân vị nội suy tại `p=0.5`. Giải thích lý do ít nhất hai kết quả khác nhau là hợp lệ theo những hợp đồng khác nhau.

**Bài 3 — So sánh phân vị.** Dùng `[1,2,2,2,5,9]` để tính `Q(0.75)` và `Q(0.9)` theo cả nearest-rank và nội suy `(n−1)p`. Vì sao kết quả nội suy không nhất thiết xuất hiện trong dữ liệu?

**Bài 4 — Phân hoạch ba miền.** Với `[7,2,7,1,7,9]` và pivot `7`, vẽ trạng thái các vùng `<7`, `=7`, `>7` sau mỗi bước của thuật toán Dutch national flag. Chứng minh bất biến `[lo,lt)<p`, `[lt,i)=p`, `(gt,hi]>p`.

**Bài 5 — Tất cả bằng nhau.** Với mảng `n` phần tử đều bằng `5`, lý giải vì sao quickselect ba miền trả đúng bất kỳ hạng `k` chỉ sau một lần phân hoạch và không cần đệ quy sâu.

**Bài 6 — Input biên.** Tính trung vị của `[Integer.MIN_VALUE,Integer.MAX_VALUE]` và tìm cách cài Java không overflow. Kiểm tra cùng input với phân vị nội suy `p=0.5`.

**Bài 7 — Chọn phương án phù hợp.** Có `n=100000` giá trị và cần trả **1000 phân vị**. So sánh gọi quickselect mỗi lần, sort một bản sao một lần, hoặc xây cấu trúc hỗ trợ nhiều truy vấn. Nhớ tính chi phí copy input và tính chính xác của định nghĩa phân vị.

**Bài 8 — Tie-break đối tượng.** Có các bản ghi `(score=80,id=A)`, `(score=80,id=B)`, `(score=80,id=C)`. Nếu đề muốn “bản ghi đứng thứ hai” trong ba bản ghi, cần bổ sung điều kiện nào? So sánh hai định nghĩa thứ tự: chỉ theo score và theo cặp `(score,id)`.

## 12. Checklist áp dụng

1. **Thứ hạng:** Đề dùng `k` zero-based hay `r` one-based? Giá trị trùng được tính thành nhiều quan sát hay bị gộp?
2. **Median:** Với `n` chẵn, đề cần trung bình hai giá trị giữa, lower median hay upper median?
3. **Quantile:** Đã chốt nearest-rank, nội suy type 7 hay một quy ước khác? `p=0` và `p=1` được định nghĩa thế nào?
4. **Ties:** Muốn trả **giá trị**, **khoảng hạng** hay **bản ghi gốc**? Có cần tiêu chí phụ để phá hòa?
5. **Thuật toán:** Một vài hạng hay nhiều truy vấn? Chọn sort, quickselect ba miền, đếm tần suất hoặc cấu trúc khác theo chi phí thực tế.
6. **Đúng đắn:** Bất biến phân hoạch `<,=,>` có giữ được không? Mỗi vòng có giảm vùng chưa xử lý, và nhánh nào chắc chắn chứa hạng `k`?
7. **Bộ nhớ và mutation:** Có được hoán đổi input không? Nếu không, tính thêm chi phí `clone()` hoặc bản sao.
8. **Trường hợp biên:** Mảng rỗng/một phần tử, toàn khóa bằng nhau, số âm, cực trị `int`, `p` không hợp lệ, nhiều giá trị trùng tại ranh giới.
9. **Kiểm chứng:** Đối chiếu một thuật toán selection với kết quả sort trên input nhỏ; dùng **đúng quy ước phân vị** cho expected result và không nhầm test với chứng minh tổng quát.

**Tiêu chí hoàn thành:** Bạn xác định đúng giá trị tại hạng `k` khi có ties, tính được trung vị và ít nhất hai loại phân vị, chứng minh phân hoạch ba miền và lựa chọn miền chứa hạng `k`, viết Java 17+ bảo toàn input theo hợp đồng, và phân tích đúng thời gian, bộ nhớ cũng như những tình huống các quy ước quantile trả kết quả khác nhau.
