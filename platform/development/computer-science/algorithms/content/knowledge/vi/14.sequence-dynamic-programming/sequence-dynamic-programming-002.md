# Tối ưu dãy con tăng bằng tìm kiếm nhị phân

## Mục tiêu học tập

**Dãy con tăng dài nhất** (*Longest Increasing Subsequence*, viết tắt **LIS**) là một bài toán kinh điển của **quy hoạch động trên dãy**. Bản quy hoạch động cơ bản mất `O(n²)` thời gian. Bằng cách duy trì **giá trị kết thúc nhỏ nhất của một dãy con tăng theo từng độ dài** và dùng **tìm kiếm nhị phân**, ta cải thiện thời gian xuống `O(n log(n+1))`.

Sau bài này, bạn có thể:

1. Phát biểu LIS chính xác, phân biệt **subsequence** và **subarray/substring**, tăng **nghiêm ngặt** và **không giảm**.
2. Xây công thức quy hoạch động `O(n²)`, hiểu điểm nghẽn và nhận ra trạng thái có thể nén để tối ưu.
3. Cài đặt thuật toán `tails + lower_bound` trong `O(n log(n+1))`, chứng minh bất biến và tính đúng.
4. **Khôi phục một LIS thực sự** bằng mảng chỉ số đuôi và con trỏ phần tử trước, thay vì nhầm mảng `tails` với đáp án.
5. Xử lý phần tử trùng, số âm, mảng rỗng, các cực trị của `int` và sự khác nhau giữa `lower_bound`/`upper_bound`.
6. Phân tích những yêu cầu **không thể giải chỉ bằng `tails`**, như đếm số LIS, chọn LIS từ điển nhỏ nhất, LIS có trọng số, dữ liệu động.
7. Chạy chương trình **Java 17+** hoàn chỉnh với đầu ra xác định và thiết kế kiểm thử đối chiếu.

## 1. Định nghĩa bài toán

Cho mảng số nguyên:

\[
a=(a_0,a_1,\ldots,a_{n-1}).
\]

Một **dãy con** (*subsequence*) được tạo bằng cách chọn một số chỉ số:

\[
0\le i_1<i_2<\cdots<i_k<n.
\]

Các phần tử được chọn **giữ nguyên thứ tự xuất hiện trong mảng gốc**, nhưng không nhất thiết đứng kề nhau.

Một dãy con **tăng nghiêm ngặt** (*strictly increasing*) thỏa:

\[
a[i_1]<a[i_2]<\cdots<a[i_k].
\]

**LIS** là một dãy con tăng nghiêm ngặt có độ dài `k` lớn nhất. Bài toán cơ bản thường chỉ hỏi **độ dài lớn nhất**; một phiên bản khác yêu cầu **trả lại chính dãy con hoặc các chỉ số được chọn**.

Ví dụ:

```text
Chỉ số:    0   1   2  3  4  5    6   7
Giá trị:  10   9   2  5  3  7  101  18
```

Một LIS là:

```text
Giá trị: [2, 3, 7, 18]
Chỉ số:  [2, 4, 5, 7]
Độ dài:  4
```

Cũng có LIS `[2,3,7,101]` với chỉ số `[2,4,5,6]`. Vì vậy **LIS có thể không duy nhất**, nhưng **độ dài tối đa** vẫn được xác định duy nhất.

### 1.1. Dãy con không phải đoạn con

- **Subsequence:** có thể bỏ các phần tử ở giữa, nhưng không đổi thứ tự.
- **Subarray:** phải là một đoạn **liên tiếp** của mảng.

Trong ví dụ trên, `[2,3,7,18]` là subsequence dù các chỉ số `2,4,5,7` không liên tiếp. Không thể giải LIS bằng một thuật toán chỉ tìm **đoạn liên tiếp tăng dài nhất**.

Ví dụ phản chứng:

```text
a = [1, 9, 2, 8, 3, 7]
```

Dãy con `[1,2,3,7]` có độ dài 4, trong khi không có đoạn liên tiếp tăng dài 4. Nếu nhầm hai khái niệm, kết quả sẽ sai.

### 1.2. Tăng nghiêm ngặt và không giảm

Với dãy `[1,2,2,3]`:

- **Tăng nghiêm ngặt:** chỉ chọn một trong hai số 2, độ dài LIS là **3** (ví dụ `[1,2,3]`).
- **Không giảm** (*non-decreasing*): được chọn cả hai số 2, độ dài dãy con không giảm dài nhất là **4**.

Quy ước trong bài chính là **tăng nghiêm ngặt**, tức dùng dấu `<`. Phần riêng bên dưới sẽ chỉ ra **một thay đổi của điều kiện tìm kiếm nhị phân** để giải biến thể không giảm.

### 1.3. Các trường hợp biên

| Mảng | Độ dài LIS nghiêm ngặt | Một dãy con hợp lệ |
| --- | ---: | --- |
| `[]` | 0 | `[]` |
| `[5]` | 1 | `[5]` |
| `[1,2,3,4]` | 4 | `[1,2,3,4]` |
| `[4,3,2,1]` | 1 | Bất kỳ một phần tử |
| `[2,2,2]` | 1 | `[2]` |
| `[-3,-1,-2,0]` | 3 | `[-3,-2,0]` hoặc `[-3,-1,0]` |

Nếu cần trả dãy con và có nhiều đáp án cùng độ dài, đặc tả phải nói rõ có thể chọn **bất kỳ LIS** hay phải chọn theo một quy tắc như từ điển nhỏ nhất, ưu tiên chỉ số xuất hiện sớm, v.v.

## 2. Giải pháp quy hoạch động cơ bản O(n²)

Ý tưởng tự nhiên nhất là xét **LIS kết thúc tại mỗi vị trí**.

Đặt:

\[
dp[i]=\text{độ dài LIS tăng nghiêm ngặt kết thúc đúng tại }i.
\]

Mọi dãy con tăng kết thúc tại i phải có phần tử áp chót ở một chỉ số `j<i` có `a[j]<a[i]`, hoặc chỉ chứa chính `a[i]`.

Vì thế:

\[
dp[i]=1+\max_{\substack{0\le j<i\\a[j]<a[i]}}dp[j],
\]

với quy ước max của tập rỗng bằng 0. Đáp án:

\[
L=\max_{0\le i<n}dp[i],
\]

và `L=0` khi `n=0`.

### 2.1. Giả mã

```text
LIS_QUADRATIC(a):
    n <- length(a)
    if n == 0: return 0

    for i từ 0 đến n-1:
        dp[i] <- 1

        for j từ 0 đến i-1:
            if a[j] < a[i]:
                dp[i] <- max(dp[i], dp[j] + 1)

    return max(dp[0..n-1])
```

Một ví dụ nhỏ:

```text
a      = [3, 1, 2, 5, 4]
dp     = [1, 1, 2, 3, 3]
answer = 3
```

Giải thích:

- Với `a[0]=3`, chỉ có dãy `[3]`, nên `dp[0]=1`.
- Với `a[1]=1`, không có giá trị trước đó nhỏ hơn 1, nên `dp[1]=1`.
- Với `a[2]=2`, nối 2 sau 1 tạo `[1,2]`, nên `dp[2]=2`.
- Với `a[3]=5`, có thể nối sau `[1,2]` tạo `[1,2,5]`, nên `dp[3]=3`.
- Với `a[4]=4`, có thể nối sau `[1,2]` tạo `[1,2,4]`, nên `dp[4]=3`.

**Độ phức tạp:** mỗi i xét tối đa i vị trí trước, tổng số cặp là:

\[
\sum_{i=0}^{n-1}i=\frac{n(n-1)}2=\Theta(n^2).
\]

Vì vậy thời gian `O(n²)` và bộ nhớ `O(n)` cho mảng `dp`.

Cách này dễ chứng minh và rất hữu ích làm **đối chứng kiểm thử**. Với n nhỏ, nó có thể còn đơn giản hơn bản tối ưu. Tuy nhiên, khi n lớn (chẳng hạn hàng trăm nghìn phần tử), việc xét toàn bộ cặp chỉ số thường quá tốn kém.

## 3. Từ O(n²) đến O(n log n): nhận ra trạng thái có thể nén

Ở bản DP, nhiều dãy con tăng có **cùng độ dài** nhưng **giá trị kết thúc khác nhau**. Để nối thêm phần tử mới `x`, ta không cần giữ mọi cách chọn, mà chỉ cần biết cách chọn nào có **đuôi nhỏ nhất**.

Ví dụ đã có hai dãy con tăng cùng độ dài 3:

```text
S1 = [1, 4, 9]
S2 = [1, 3, 6]
```

Với phần tử đến sau `x=7`:

- `S1` không nối thêm 7 được vì `9<7` sai.
- `S2` nối được thành `[1,3,6,7]` vì `6<7` đúng.

**Với cùng độ dài, một giá trị kết thúc nhỏ hơn không bao giờ kém lợi thế hơn khi muốn nối thêm các giá trị tương lai.**

Đây là nguyên tắc **giữ trạng thái trội (state dominance)**: trong bài tìm **độ dài** LIS, ta có thể bỏ những ứng viên có đuôi lớn hơn mà vẫn giữ một đuôi nhỏ nhất cho mỗi độ dài.

### 3.1. Định nghĩa mảng tails

Sau khi đã xử lý một tiền tố của mảng `a`, định nghĩa:

\[
tails[\ell-1]
=\min\{\text{giá trị cuối của một dãy con tăng dài }\ell\},
\]

với những độ dài `\ell` **đã đạt được**.

Nói cách khác:

- `tails[0]`: giá trị kết thúc **nhỏ nhất** của một dãy con tăng dài 1.
- `tails[1]`: giá trị kết thúc **nhỏ nhất** của một dãy con tăng dài 2.
- ...
- `tails[L-1]`: giá trị kết thúc nhỏ nhất của một dãy con tăng dài L, với L là độ dài LIS hiện tại.

**Bất biến quan trọng:** trên phần `tails[0..L)` đang dùng, các giá trị **tăng nghiêm ngặt**:

\[
tails[0]<tails[1]<\cdots<tails[L-1].
\]

Lý do: để có một dãy con tăng dài `\ell+1`, bỏ phần tử cuối sẽ được dãy con tăng dài `\ell` với đuôi nhỏ hơn đuôi ban đầu. Đuôi tối thiểu cho độ dài `\ell` vì thế cũng nhỏ hơn đuôi tối thiểu của một dãy con tăng dài `\ell+1`.

Nhờ phần `tails` đang hoạt động **đã được sắp xếp**, ta có thể dùng **tìm kiếm nhị phân** trên `tails`, **mặc dù mảng đầu vào `a` có thể hoàn toàn chưa sắp xếp**.

Đó là điểm tối ưu cốt lõi: **không tìm kiếm nhị phân trực tiếp trên mảng gốc**, mà tìm biên trên **trạng thái DP đã duy trì theo thứ tự**.

## 4. Quy tắc cập nhật tails bằng lower_bound

Với mỗi phần tử mới `x=a[i]`, tìm vị trí:

\[
p=\operatorname{lowerBound}(tails[0..L),x),
\]

tức **chỉ số đầu tiên p có `tails[p]\ge x`**. Nếu không có, `p=L`.

Sau đó:

1. Đặt `tails[p]=x`.
2. Nếu `p=L`, tăng `L` lên 1 vì ta vừa tạo ra một dãy con tăng có độ dài mới `L+1`.
3. Nếu `p<L`, chỉ thay một đuôi cũ bằng `x` nhỏ hơn hoặc bằng nó, giữ nguyên số độ dài đã đạt được.

Vì sao đúng?

- Nếu `p>0`, theo định nghĩa lower bound, `tails[p-1]<x`, nên có một dãy con tăng độ dài p kết thúc nhỏ hơn x. Nối x tạo dãy con tăng độ dài `p+1`.
- Nếu `p=0`, bản thân `[x]` là một dãy con tăng độ dài 1.
- Nếu `p<L`, đuôi ở vị trí p trước đó `>=x`, nên thay bằng x không làm mất lợi thế của trạng thái tối ưu.
- Nếu `p=L`, x lớn hơn mọi đuôi tối thiểu đang lưu, nên ta vừa tạo được dãy con tăng dài hơn 1 đơn vị.

### 4.1. Giả mã

```text
LIS_LENGTH(a):
    tails <- mảng dung lượng n
    length <- 0

    for mỗi x trong a:
        lo <- 0
        hi <- length

        while lo < hi:
            mid <- lo + (hi-lo)/2

            if tails[mid] < x:
                lo <- mid+1
            else:
                hi <- mid

        p <- lo                     // lower_bound: vị trí đầu tiên >= x
        tails[p] <- x

        if p == length:
            length <- length+1

    return length
```

Lưu ý:

- Vùng được tìm kiếm là `[0,length)`, không phải toàn bộ dung lượng mảng `tails`.
- Nếu `p=length`, ô này là vị trí mới **trong dung lượng đã cấp phát `n`**, vì ta đang xử lý tối đa n phần tử.
- `lo + (hi-lo)/2` tránh phép cộng trực tiếp `lo+hi` trong khuôn mẫu binary search.
- **Điều kiện `tails[mid]<x` là dấu nhỏ hơn nghiêm ngặt.** Vì vậy một x bằng đuôi cũ sẽ **thay đuôi**, không tạo chiều dài tăng mới.

### 4.2. Tại sao không cần sắp xếp mảng gốc?

Nếu gọi `Arrays.sort(a)` rồi lấy toàn bộ mảng đã sắp làm “dãy con tăng”, ta có thể **thay đổi thứ tự xuất hiện** của các phần tử, vi phạm định nghĩa subsequence.

Ví dụ:

```text
a = [3, 2, 1]
Mảng đã sort: [1, 2, 3]
LIS của a: độ dài 1, không phải 3
```

LIS phụ thuộc cả **giá trị** lẫn **thứ tự chỉ số**. Thuật toán `tails` duyệt các phần tử theo thứ tự gốc, chỉ dùng tìm kiếm nhị phân trên cấu trúc phụ để chọn trạng thái DP phù hợp.

## 5. Mô phỏng từng bước trên ví dụ chuẩn

Dữ liệu:

```text
a = [10, 9, 2, 5, 3, 7, 101, 18]
```

Bảng cập nhật:

| Chỉ số i | Giá trị x | Vị trí p = lower_bound | tails sau khi xử lý | L hiện tại |
| ---: | ---: | ---: | --- | ---: |
| 0 | 10 | 0 | `[10]` | 1 |
| 1 | 9 | 0 | `[9]` | 1 |
| 2 | 2 | 0 | `[2]` | 1 |
| 3 | 5 | 1 | `[2,5]` | 2 |
| 4 | 3 | 1 | `[2,3]` | 2 |
| 5 | 7 | 2 | `[2,3,7]` | 3 |
| 6 | 101 | 3 | `[2,3,7,101]` | 4 |
| 7 | 18 | 3 | `[2,3,7,18]` | 4 |

Kết quả: **LIS có độ dài 4**.

Diễn giải những bước quan trọng:

- `10→9→2`: ba lần cải thiện **đuôi tốt nhất của độ dài 1**.
- Xử lý `5`: vì `5>2`, tạo được một dãy con tăng độ dài 2, `tails=[2,5]`.
- Xử lý `3`: thay đuôi 5 bằng 3, khiến trạng thái độ dài 2 **dễ mở rộng hơn**.
- Xử lý `7`: nối sau đuôi 3, được độ dài 3.
- Xử lý `101`: tạo độ dài 4.
- Xử lý `18`: vẫn độ dài 4, nhưng đuôi 18 tốt hơn 101 nếu còn dữ liệu phía sau.

Có ít nhất hai LIS độ dài 4:

```text
[2, 3, 7, 101]
[2, 3, 7, 18]
```

Thuật toán `tails` xác định **độ dài**, nhưng phiên bản chỉ lưu các giá trị đuôi không tự cung cấp mọi chỉ số của một subsequence hoàn chỉnh. Phần sau sẽ thêm con trỏ để khôi phục một đáp án hợp lệ.

## 6. Một cạm bẫy quan trọng: tails không nhất thiết là LIS

Một lỗi rất phổ biến là chạy cập nhật `tails` rồi **trả chính mảng `tails` như một LIS của đầu vào**.

Trong nhiều ví dụ, nó tình cờ là một dãy con hợp lệ; nhưng điều đó **không được bảo đảm**.

Phản ví dụ:

```text
Input = [2, 5, 3, 4, 1]

Sau 2: tails = [2]
Sau 5: tails = [2, 5]
Sau 3: tails = [2, 3]
Sau 4: tails = [2, 3, 4]
Sau 1: tails = [1, 3, 4]
```

Ở cuối, `tails=[1,3,4]` **không phải subsequence** của input, bởi số 1 xuất hiện **sau** 3 và 4. LIS thật có thể là `[2,3,4]`, độ dài 3.

Lý do: mỗi `tails[t]` mô tả **một trạng thái tốt nhất cho độ dài t+1**, được cập nhật vào những thời điểm khác nhau. Sau các phép thay thế, các đuôi ở các độ dài khác nhau không nhất thiết nằm trên **cùng một chuỗi con trỏ tổ tiên**.

**Quy tắc:** muốn trả **độ dài** thì lưu `tails` là đủ; muốn trả **dãy con/đường chỉ số** thì phải giữ thêm **nguồn gốc của mỗi trạng thái** khi xử lý từng phần tử.

## 7. Khôi phục một LIS bằng chỉ số và predecessor

Ta giữ thêm hai mảng:

1. `tailIndex[t]`: chỉ số **trong mảng gốc** của phần tử đang đại diện cho đuôi tốt nhất của dãy con tăng dài `t+1`.
2. `previous[i]`: chỉ số phần tử được chọn đứng **ngay trước `a[i]`** trong một dãy con tăng kết thúc tại i; nếu i mở đầu dãy con, dùng `-1`.

Khi xử lý `a[i]=x` và đã tìm được vị trí `p`:

```text
if p > 0:
    previous[i] = tailIndex[p-1]
else:
    previous[i] = -1

tails[p] = x
tailIndex[p] = i

if p == length:
    length++
```

**Thứ tự thao tác rất quan trọng:** phải lấy `previous[i]` từ `tailIndex[p-1]` **trước khi ghi đè chỉ số đuôi tại p**. Vì `tailIndex[p-1]` đến từ một phần tử đã xử lý ở chỉ số nhỏ hơn i và có giá trị nhỏ hơn x, liên kết mới luôn hợp lệ cho một dãy con tăng.

Cuối cùng:

1. Bắt đầu từ `tailIndex[length-1]` — chỉ số của một đuôi tốt nhất cho LIS dài nhất.
2. Đi ngược các `previous[index]` để lấy chuỗi chỉ số.
3. Đảo ngược hoặc ghi ngược vào mảng kết quả.

### 7.1. Vết predecessor trên ví dụ

Với `[10,9,2,5,3,7,101,18]`:

| i | a[i] | p | previous[i] | Ý nghĩa |
| ---: | ---: | ---: | ---: | --- |
| 0 | 10 | 0 | -1 | Dãy độ dài 1 |
| 1 | 9 | 0 | -1 | Thay đuôi độ dài 1 |
| 2 | 2 | 0 | -1 | Thay đuôi độ dài 1 |
| 3 | 5 | 1 | 2 | Nối sau số 2 ở i=2 |
| 4 | 3 | 1 | 2 | Nối sau số 2 ở i=2 |
| 5 | 7 | 2 | 4 | Nối sau số 3 ở i=4 |
| 6 | 101 | 3 | 5 | Nối sau số 7 ở i=5 |
| 7 | 18 | 3 | 5 | Nối sau số 7 ở i=5 |

Khi kết thúc, đuôi đại diện cho độ dài 4 là chỉ số 7 (giá trị 18). Chuỗi con trỏ:

```text
7 -> 5 -> 4 -> 2 -> -1
```

Đảo ngược:

```text
Chỉ số: [2,4,5,7]
Giá trị: [2,3,7,18]
```

Đó là **một LIS thực sự**, vì:

- Chỉ số tăng nghiêm ngặt: `2<4<5<7`.
- Giá trị tăng nghiêm ngặt: `2<3<7<18`.
- Độ dài 4 bằng độ dài tối ưu.

### 7.2. Vì sao con trỏ không bị hỏng khi tails thay đổi?

`tailIndex` chứa các **đại diện hiện tại**, nhưng `previous[i]` được ghi **một lần duy nhất tại thời điểm i được xử lý**. Chỉ số này luôn trỏ về **một phần tử có chỉ số nhỏ hơn i**.

Sau này có thể thay `tailIndex[t]` để nhận một đuôi tốt hơn, nhưng ta **không sửa lại** những liên kết `previous` đã lưu. Chuỗi được chọn ở thời điểm i vẫn là một chuỗi hợp lệ trong tiền tố trước i. Vì vậy khi đi ngược từ đuôi cuối, ta khôi phục được một LIS nhất quán.

**Độ phức tạp bổ sung:** bộ nhớ `O(n)` cho `tailIndex` và `previous`; khôi phục tối đa L bước, `O(L)`. Tổng thời gian vẫn `O(n log(n+1))`.

## 8. Tìm kiếm nhị phân chính xác trên tails

Đối với LIS **tăng nghiêm ngặt**, ta cần:

\[
\operatorname{lowerBound}(tails,x)
 =\text{chỉ số đầu tiên có }tails[p]\ge x.
\]

Giả mã:

```text
LOWER_BOUND(tails, length, x):
    lo = 0
    hi = length

    while lo < hi:
        mid = lo + (hi-lo)/2

        if tails[mid] < x:
            lo = mid+1
        else:
            hi = mid

    return lo
```

Hai miền đơn điệu là:

```text
tails[t] < x             | tails[t] >= x
       false ở vị trí...? 
Thực chất: điều kiện "< x" đúng ở tiền tố,
điều kiện ">= x" đúng ở hậu tố.
```

Có thể hình dung trực tiếp trên `tails=[2,3,7,18]` và `x=5`:

```text
tails:   [2, 3, 7, 18]
          <  <  >= >=
                ^
            lower_bound = 2
```

Thay `tails[2]` bằng 5, ta có `[2,3,5,18]`, vẫn tăng nghiêm ngặt.

**Lưu ý về API Java:** `Arrays.binarySearch` trả một vị trí **bằng khóa bất kỳ** nếu có nhiều phần tử bằng nhau và không trực tiếp là một API `lower_bound`/`upper_bound` với hợp đồng chính xác như trên. Trong `tails` nghiêm ngặt đang hoạt động không có giá trị trùng, nhưng viết hàm lower bound rõ ràng vẫn giúp bảo đảm điều kiện và tái sử dụng cho các biến thể.

### 8.1. Giữ đúng phạm vi tìm kiếm

Chỉ tìm trên `tails[0..length)` — các giá trị đuôi **đã xác lập**. Nếu cấp phát mảng `int[n]` nhưng phần chưa dùng mặc định có giá trị 0, việc tìm trên **cả n phần tử** có thể xử lý các số 0 giả làm dữ liệu và khiến kết quả sai.

Với mảng có số âm, lỗi này đặc biệt dễ nhìn thấy: vùng chưa dùng toàn số 0 không có nghĩa các trạng thái DP với đuôi bằng 0 đã tồn tại.

### 8.2. Chỉ số mid và so sánh an toàn

- Dùng `mid = lo + (hi-lo)/2` để tránh cộng trực tiếp `lo+hi`.
- Dùng phép so sánh `tails[mid] < x`, **không tính `tails[mid] - x` để quyết định**, vì phép trừ hai giá trị `int` gần cực trị có thể tràn.
- `hi=length` là cận phải **không bao gồm**; không đọc `tails[length]` trong vòng tìm kiếm.
- Với mảng rỗng, `length=0`, vòng tìm kiếm không chạy và trả 0.

## 9. Chứng minh tính đúng của thuật toán O(n log n)

Ta cần chứng minh **bất biến**, **khả năng mở rộng**, **độ dài tối ưu** và **tính dừng**.

### 9.1. Bất biến chính

Sau khi xử lý `a[0..i)`:

1. `length=L` bằng độ dài lớn nhất **đã đạt được trong tiền tố đó**.
2. Với mỗi `0≤t<L`, tồn tại một dãy con tăng có độ dài `t+1` trong tiền tố, kết thúc ở `tails[t]`.
3. Trong tất cả dãy con tăng độ dài `t+1` của tiền tố, `tails[t]` là **giá trị kết thúc nhỏ nhất**.
4. Dãy các đuôi `tails[0..L)` tăng nghiêm ngặt.

Đối với phiên bản khôi phục, có thêm bất biến: `tailIndex[t]` là một chỉ số kết thúc hợp lệ có giá trị `tails[t]`, và `previous` liên kết đến các phần tử ở chỉ số nhỏ hơn với giá trị nhỏ hơn.

### 9.2. Khởi tạo

Trước khi xử lý phần tử nào, `L=0`. Không có dãy con không rỗng, nên tập các trạng thái đang lưu rỗng và bất biến đúng một cách hiển nhiên.

### 9.3. Duy trì khi thêm x

Giả sử bất biến đúng trước phần tử `x=a[i]`. Gọi `p` là chỉ số đầu tiên trong `tails` có đuôi `>=x`; nếu không có thì `p=L`.

- Nếu `p=0`, chọn dãy con chỉ gồm x, độ dài 1.
- Nếu `p>0`, ta biết `tails[p-1]<x`. Theo bất biến, có một dãy con tăng dài p kết thúc tại giá trị `tails[p-1]` ở một vị trí **đã xuất hiện trước i**. Nối thêm x tạo dãy con tăng dài `p+1` kết thúc tại x.
- Nếu `p<L`, đuôi cũ của độ dài `p+1` có giá trị `>=x`. Thay bằng x làm đuôi tối thiểu của độ dài này tốt hơn hoặc bằng trước đó. Các độ dài khác không cần đổi.
- Nếu `p=L`, x lớn hơn đuôi tối thiểu của dãy dài L. Vì vậy tạo được dãy dài `L+1` và tăng length thêm 1.

Vì `p` là vị trí biên đầu tiên, với `p>0` ta có `tails[p-1]<x`; với `p<L-1`, giá trị kế tiếp cũ `tails[p+1]>tails[p]\ge x`. Do đó sau cập nhật, mảng `tails` vẫn **tăng nghiêm ngặt** trên vùng đang dùng.

Tất cả trạng thái còn lại vẫn mô tả những dãy con hợp lệ của tiền tố mới. Không có một dãy con kết thúc tại x dài hơn `p+1`, vì điều đó sẽ cần một đuôi của dãy con tiền tố dài hơn p nhỏ hơn x, trái với định nghĩa p là lower bound trên những đuôi tối thiểu.

### 9.4. Kết thúc và tính tối ưu

Sau khi xử lý tất cả n phần tử, bất biến cho:

- Tồn tại dãy con tăng độ dài L.
- Không tồn tại dãy con tăng có độ dài vượt L, nếu không thuật toán đã phải tạo được trạng thái cho độ dài ấy ở thời điểm phần tử cuối của dãy con đó được xử lý.

Do đó `L` chính là độ dài LIS của toàn bộ đầu vào.

### 9.5. Tính dừng

- Vòng ngoài duyệt đúng n phần tử.
- Trong mỗi lần tìm kiếm nhị phân, độ dài khoảng `hi-lo` giảm nghiêm ngặt khi `lo<hi`.
- Vòng khôi phục chỉ lần ngược tối đa L con trỏ; mỗi con trỏ trỏ đến chỉ số **nhỏ hơn**, nên không có chu trình.

Thuật toán dừng với mọi mảng hữu hạn hợp lệ.

## 10. Độ phức tạp và sự đánh đổi

Đặt L là độ dài LIS, `0≤L≤n`.

| Thuật toán | Thời gian | Bộ nhớ phụ | Có thể khôi phục một LIS? |
| --- | --- | --- | --- |
| DP theo từng vị trí | `O(n²)` | `O(n)` | Có, nếu giữ `parent[i]` |
| `tails` + binary search, chỉ độ dài | `O(n log(n+1))` | `O(n)` khi cấp phát `int[n]`; chỉ L ô đang dùng | Chưa, nếu chỉ lưu giá trị |
| `tails` + `tailIndex` + `previous` | `O(n log(n+1))` | `O(n)` | Có, thêm `O(L)` để lần ngược |
| Chỉ số độ dài và tập giá trị động | `O(n log(n+1))` | `O(L)` trạng thái đuôi, nếu dùng mảng động | Không nếu không giữ con trỏ |

Với mỗi phần tử:

- Tìm biên trong tối đa L phần tử của `tails` tốn `O(log(L+1))`.
- Ghi đuôi và con trỏ tốn `O(1)`.
- Tổng trên n phần tử tốn `O(n log(n+1))`.

Nếu chỉ có một phần tử hoặc mảng rỗng, thuật toán xử lý trực tiếp mà không cần “log của 0”; ký hiệu `O(n log(n+1))` giúp mô tả chặn thuận tiện cho mọi n.

**Kết luận:** tối ưu đến từ việc **nén nhiều trạng thái DP cùng độ dài về đuôi nhỏ nhất** và **tìm vị trí thay thế bằng binary search**, không phải từ việc “bật một hàm tìm kiếm nhị phân” trên bản DP `O(n²)`.

## 11. Java 17+: chương trình chạy được và khôi phục một LIS

Lưu mã dưới tên **`LISBinarySearchDemo.java`**. Chương trình minh họa:

- DP `O(n²)` để đối chiếu.
- LIS nghiêm ngặt `O(n log(n+1))` có **chỉ số và dãy con khôi phục**.
- Biến thể **không giảm** dùng upper bound.
- Các ca phần tử trùng và mảng rỗng.
- Giữ nguyên mảng đầu vào.

```java
import java.util.Arrays;
import java.util.Objects;

public class LISBinarySearchDemo {

    public record Result(
            int length,
            int[] indices,
            int[] sequence) {
    }

    // First index in a[0..size) whose value is >= x.
    static int lowerBound(int[] a, int size, int x) {
        int lo = 0;
        int hi = size;

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

    // First index in a[0..size) whose value is > x.
    static int upperBound(int[] a, int size, int x) {
        int lo = 0;
        int hi = size;

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

    // Strictly increasing LIS with reconstruction.
    // Input is never modified.
    public static Result lisStrict(int[] input) {
        Objects.requireNonNull(input, "input");

        int n = input.length;
        int[] tails = new int[n];
        int[] tailIndex = new int[n];
        int[] previous = new int[n];
        Arrays.fill(previous, -1);

        int length = 0;

        for (int i = 0; i < n; i++) {
            int x = input[i];
            int pos = lowerBound(tails, length, x);

            if (pos > 0) {
                previous[i] = tailIndex[pos - 1];
            }

            tails[pos] = x;
            tailIndex[pos] = i;

            if (pos == length) {
                length++;
            }
        }

        int[] indices = new int[length];
        int current = length == 0 ? -1 : tailIndex[length - 1];

        for (int k = length - 1; k >= 0; k--) {
            indices[k] = current;
            current = previous[current];
        }

        int[] sequence = new int[length];
        for (int k = 0; k < length; k++) {
            sequence[k] = input[indices[k]];
        }

        return new Result(length, indices, sequence);
    }

    // Longest NON-DECREASING subsequence: equality may extend.
    public static int nonDecreasingLength(int[] input) {
        Objects.requireNonNull(input, "input");

        int[] tails = new int[input.length];
        int length = 0;

        for (int x : input) {
            int pos = upperBound(tails, length, x);
            tails[pos] = x;

            if (pos == length) {
                length++;
            }
        }

        return length;
    }

    // O(n^2) DP, useful as an independent test oracle.
    public static int quadraticLength(int[] input) {
        Objects.requireNonNull(input, "input");

        int n = input.length;
        int[] dp = new int[n];
        int answer = 0;

        for (int i = 0; i < n; i++) {
            dp[i] = 1;

            for (int j = 0; j < i; j++) {
                if (input[j] < input[i]) {
                    dp[i] = Math.max(dp[i], dp[j] + 1);
                }
            }

            answer = Math.max(answer, dp[i]);
        }

        return answer;
    }

    public static void main(String[] args) {
        int[] data = {10, 9, 2, 5, 3, 7, 101, 18};
        Result result = lisStrict(data);

        System.out.println("Input: " + Arrays.toString(data));
        System.out.println("LIS length: " + result.length());
        System.out.println("LIS indices: "
                + Arrays.toString(result.indices()));
        System.out.println("One LIS: "
                + Arrays.toString(result.sequence()));
        System.out.println("Quadratic DP length: "
                + quadraticLength(data));

        int[] duplicates = {1, 2, 2, 3};
        System.out.println("Strict [1, 2, 2, 3]: "
                + lisStrict(duplicates).length());
        System.out.println("Non-decreasing [1, 2, 2, 3]: "
                + nonDecreasingLength(duplicates));

        int[] allEqual = {2, 2, 2};
        System.out.println("Strict [2, 2, 2]: "
                + lisStrict(allEqual).length());
        System.out.println("Non-decreasing [2, 2, 2]: "
                + nonDecreasingLength(allEqual));

        System.out.println("Empty LIS length: "
                + lisStrict(new int[0]).length());
        System.out.println("Input unchanged: "
                + Arrays.toString(data));
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac LISBinarySearchDemo.java
java LISBinarySearchDemo
```

**Đầu ra chuẩn chính xác:**

```text
Input: [10, 9, 2, 5, 3, 7, 101, 18]
LIS length: 4
LIS indices: [2, 4, 5, 7]
One LIS: [2, 3, 7, 18]
Quadratic DP length: 4
Strict [1, 2, 2, 3]: 3
Non-decreasing [1, 2, 2, 3]: 4
Strict [2, 2, 2]: 1
Non-decreasing [2, 2, 2]: 3
Empty LIS length: 0
Input unchanged: [10, 9, 2, 5, 3, 7, 101, 18]
```

### 11.1. Giải thích các chi tiết dễ nhầm trong code

- `lowerBound` tìm vị trí đầu tiên có giá trị `>=x`, dùng để tính **LIS tăng nghiêm ngặt**.
- `upperBound` tìm vị trí đầu tiên có giá trị `>x`, dùng cho **dãy con không giảm** khi cho phép nối phần tử bằng nhau.
- Mảng `tails` có dung lượng n nhưng chỉ đoạn `[0,length)` hợp lệ là trạng thái DP; không tìm kiếm trên ô chưa dùng.
- `tailIndex[pos]` lưu **chỉ số của phần tử đuôi trong mảng input**, không phải giá trị x.
- `previous[i]` lưu cha tại thời điểm xây trạng thái và không được chỉnh sửa lại khi những trạng thái đuôi khác bị thay.
- Vòng khôi phục ghi ngược từ đuôi tốt nhất vào mảng `indices`, do đó kết quả trả về được sắp **theo thứ tự chỉ số tăng**.
- `Result` là record Java, có từ JDK 16 và dùng ổn trong **Java 17+**. Nó đóng gói độ dài, dãy chỉ số và dãy giá trị.
- `lisStrict` không sửa mảng `input`: các phép gán chỉ tác động lên những mảng phụ.
- `quadraticLength` tính độc lập bằng công thức DP cổ điển, hữu ích để đối chiếu ngẫu nhiên nhiều dữ liệu ngắn.
- Với `new int[0]`, mảng đuôi và con trỏ đều rỗng, vòng lặp không chạy, kết quả là `0` và hai mảng kết quả rỗng.
- So sánh dùng `<`, `<=` thay vì trừ hai `int` nên không có lỗi tràn do tính hiệu với `Integer.MIN_VALUE`/`Integer.MAX_VALUE`.
- Một dãy có thể có nhiều LIS: mã này trả **một** dãy phụ thuộc chính sách cập nhật đuôi. Đề không yêu cầu ưu tiên LIS nào nên đây là kết quả hợp lệ.

### 11.2. Điều gì thay đổi nếu phải trả một LIS không giảm?

Muốn khôi phục **một dãy con không giảm** chứ không chỉ độ dài, có thể áp dụng cùng cấu trúc `tailIndex`/`previous` nhưng thay vị trí:

```java
int pos = upperBound(tails, length, x);
```

Khi `pos>0`, ta có `tails[pos-1] <= x` (cho phép bằng nhau); chuỗi con trỏ vì thế phải thỏa **giá trị không giảm**. Không được áp dụng kiểm tra giá trị tăng nghiêm ngặt cho kết quả của biến thể không giảm.

Trong chương trình chính, hàm `nonDecreasingLength` **chỉ trả độ dài** để nhấn mạnh thay đổi một điều kiện nhị phân; nó không hứa trả chỉ số hoặc dãy khôi phục.

## 12. Vì sao lower_bound khác upper_bound ở phần tử trùng?

Đây là một trong những phần quan trọng nhất khi tối ưu LIS.

| Bài toán | Điều kiện nối | Biên tìm trong tails | Kiểm tra trong binary search |
| --- | --- | --- | --- |
| LIS **tăng nghiêm ngặt** | `previous < x` | **lower_bound**: đầu tiên `>=x` | `if tails[mid] < x then lo=mid+1` |
| Dãy con **không giảm** | `previous <= x` | **upper_bound**: đầu tiên `>x` | `if tails[mid] <= x then lo=mid+1` |

Ví dụ:

```text
Input: [2, 2, 2]
```

**LIS nghiêm ngặt, lower bound:**

```text
x=2 -> tails [2]
x=2 -> thay tails[0], vẫn [2]
x=2 -> thay tails[0], vẫn [2]
Độ dài = 1
```

**Không giảm, upper bound:**

```text
x=2 -> tails [2]
x=2 -> chèn sau mọi đuôi <=2: [2,2]
x=2 -> chèn sau mọi đuôi <=2: [2,2,2]
Độ dài = 3
```

Với biến thể không giảm, `tails` chỉ cần **không giảm**, không còn tăng nghiêm ngặt; vì vậy việc chọn upper bound mới cho phép nhân chiều dài qua các phần tử bằng nhau.

**Sai lầm thường gặp:** đổi chữ “tăng” thành “không giảm” trong mô tả mà quên đổi phép so sánh. Khi có phần tử trùng, độ dài có thể chênh lệch lớn như 1 so với n.

## 13. Truy vết một ví dụ khác với số âm

Xét:

```text
a = [3, 4, -1, 0, 6, 2, 3]
```

Bảng đuôi:

| Giá trị x | tails sau khi cập nhật | L |
| ---: | --- | ---: |
| 3 | `[3]` | 1 |
| 4 | `[3,4]` | 2 |
| -1 | `[-1,4]` | 2 |
| 0 | `[-1,0]` | 2 |
| 6 | `[-1,0,6]` | 3 |
| 2 | `[-1,0,2]` | 3 |
| 3 | `[-1,0,2,3]` | 4 |

Vậy LIS dài **4**, chẳng hạn `[-1,0,2,3]` tại các chỉ số `2,3,5,6`.

Điều này minh họa:

1. Không cần mọi phần tử ban đầu dương.
2. Tìm kiếm nhị phân hoạt động trên `tails` **đã được sắp bởi bất biến**, không cần sắp đầu vào.
3. Một giá trị âm mới có thể cải thiện đáng kể đuôi của các dãy con ngắn, tạo cơ hội nối thêm phần tử tương lai.
4. Số nhỏ nhất xuất hiện muộn không tự tạo LIS dài — còn phải tôn trọng thứ tự chỉ số.

## 14. Những yêu cầu LIS khác không được giải chỉ bằng độ dài tails

### 14.1. Đếm số lượng LIS

Với:

```text
a = [1, 3, 5, 4, 7]
```

Có hai LIS độ dài 4:

```text
[1, 3, 5, 7]
[1, 3, 4, 7]
```

Thuật toán `tails` cho **độ dài 4**, nhưng không cho biết có **hai** cách chọn. Vì mỗi độ dài chỉ giữ một đuôi nhỏ nhất nên thông tin về **số cách đạt trạng thái** có thể bị loại bỏ.

Muốn đếm số LIS theo **các bộ chỉ số** (các phần tử bằng giá trị ở vị trí khác nhau vẫn là các lựa chọn khác nhau), có thể dùng DP:

- `len[i]`: độ dài LIS kết thúc tại i.
- `count[i]`: số dãy con tăng có độ dài `len[i]` kết thúc tại i.
- Khởi tạo `len[i]=1` và `count[i]=1`.
- Với mỗi `j<i` và `a[j]<a[i]`:
  - Nếu `len[j]+1>len[i]`, cập nhật `len[i]=len[j]+1`, `count[i]=count[j]`.
  - Nếu `len[j]+1==len[i]`, cộng `count[j]` vào `count[i]`.
- Gọi `L=max_i len[i]`, đáp án số cách là `sum_{i:len[i]=L}count[i]`.

Cách này `O(n²)` thời gian. Nếu n lớn, có thể dùng **Fenwick tree hoặc segment tree trên miền giá trị đã nén**, lưu cặp `(độ dài tốt nhất, số cách)` với quy tắc kết hợp cẩn thận, thay vì dùng duy nhất `tails`.

**Lưu ý:** số cách có thể rất lớn, vượt `long`; bài toán có thể yêu cầu tính modulo, hoặc dùng `BigInteger` nếu cần số nguyên chính xác. Khi n=0, quy ước đếm số LIS rỗng có thể là 0 hoặc 1 tùy đặc tả — phải công bố.

### 14.2. LIS có trọng số

Nếu mỗi phần tử còn có trọng số lợi ích `w[i]` và mục tiêu là **tổng trọng số lớn nhất** của một dãy con tăng, bài toán không còn chỉ tối ưu **chiều dài**.

Một trạng thái như:

\[
best[i]=w[i]+\max_{\substack{j<i\\a[j]<a[i]}}best[j]
\]

phải xét cả giá trị khóa và lợi ích tích lũy. Nếu cho phép chọn dãy rỗng hoặc có trọng số âm, cần định nghĩa lại giá trị cơ sở cho chính xác. `tails` chỉ lưu đuôi nhỏ nhất theo chiều dài **không chứa đủ thông tin tổng trọng số** để giải biến thể này.

Có thể dùng DP `O(n²)`, hoặc khi phù hợp có thể nén giá trị và dùng Fenwick/segment tree để lấy tối đa của những khóa nhỏ hơn.

### 14.3. Yêu cầu LIS từ điển nhỏ nhất hoặc ưu tiên chỉ số

Phiên bản khôi phục trong mục 7 trả **một** LIS, không chứng minh nó là LIS có giá trị từ điển nhỏ nhất, cũng không nhất thiết ưu tiên chỉ số sớm nhất trong mọi trường hợp hòa.

Nếu đặc tả cần:

- Dãy LIS **từ điển nhỏ nhất**;
- Dãy chỉ số **từ điển nhỏ nhất**;
- LIS có thứ tự ổn định theo một tiêu chí phụ;
- Liệt kê **tất cả** LIS;

thì phải bổ sung trạng thái, quy tắc hòa, truy vết hoặc thuật toán chuyên dụng. Không nên thêm một phép so sánh tùy tiện khi cập nhật `tails` rồi cho rằng đã bảo đảm một quy tắc tối ưu thứ cấp.

### 14.4. LIS với nhiều thuộc tính

Ví dụ mỗi bản ghi là một hình chữ nhật `(width,height)` và phải tăng **nghiêm ngặt cả hai chiều**. Một kỹ thuật thường gặp:

1. Sắp theo `width` tăng.
2. Nếu bằng width, sắp `height` **giảm**.
3. Chạy LIS **nghiêm ngặt** trên dãy height đã sắp.

Thứ tự height giảm trong nhóm width bằng nhau giúp ngăn chọn hai bản ghi có cùng width trong một dãy tăng height nghiêm ngặt. Đây là một phép biến đổi có tiền điều kiện và cách xử lý hòa cụ thể, **không phải** “cứ sắp theo width rồi LIS height” là luôn đúng.

### 14.5. Dữ liệu cập nhật/xóa

Khi chỉ **thêm phần tử vào cuối** của một luồng, ta có thể cập nhật tails cho mỗi phần tử mới với chi phí `O(log(L+1))` và duy trì **độ dài LIS của tiền tố**.

Nhưng nếu được **xóa**, **thay giá trị**, hoặc **chèn vào giữa** những phần tử đã xử lý, các trạng thái đuôi và các quan hệ thứ tự có thể thay đổi trên diện rộng. Không thể áp dụng nguyên thao tác cập nhật một phần tử vào cuối rồi khẳng định xử lý được mọi truy vấn động với cùng thời gian.

## 15. Liên hệ với patience sorting

Thuật toán `tails` cũng thường được giải thích qua phép xếp bài **patience sorting**:

- Đọc từng lá bài theo thứ tự.
- Tìm một chồng có lá trên cùng **đầu tiên lớn hơn hoặc bằng** giá trị lá mới (trong biến thể LIS nghiêm ngặt theo quy ước này).
- Đặt lá lên chồng ấy; nếu không có chồng phù hợp, tạo chồng mới.
- Số chồng khi hoàn tất bằng độ dài LIS nghiêm ngặt.

Giá trị trên cùng của từng chồng tương ứng với phần tử `tails[t]`. Các đỉnh chồng tạo thành dãy tăng, nên có thể tìm chồng phù hợp bằng nhị phân.

**Không nhầm lẫn:** số chồng bằng **độ dài** LIS, nhưng chỉ đọc các đỉnh chồng từ trái sang phải **không luôn cho một subsequence hợp lệ**, giống phản ví dụ `[2,5,3,4,1]`. Muốn truy vết một LIS, vẫn cần lưu liên kết giữa các lá bài/chỉ số khi chúng được đặt vào chồng.

Cách nhìn patience sorting giúp hiểu vì sao thuật toán có một mảng các “đuôi tốt nhất” và vì sao mỗi phần tử chỉ cần một lần tìm biên.

## 16. Kiểm thử thuật toán và bất biến

Đối với việc viết code thật, hãy kiểm thử **không chỉ độ dài** mà cả **tính hợp lệ của dãy khôi phục**.

### 16.1. Những ca bắt buộc

| Input | LIS nghiêm ngặt | Không giảm | Một lưu ý |
| --- | ---: | ---: | --- |
| `[]` | 0 | 0 | Không truy cập index 0 |
| `[5]` | 1 | 1 | Mảng một phần tử |
| `[1,2,3,4]` | 4 | 4 | Tăng sẵn |
| `[4,3,2,1]` | 1 | 1 | Giảm hoàn toàn |
| `[2,2,2]` | 1 | 3 | Phân biệt dấu `<`/`<=` |
| `[1,2,2,3]` | 3 | 4 | Phần tử trùng |
| `[3,1,2,5,4]` | 3 | 3 | Có nhiều LIS |
| `[-3,-1,-2,0]` | 3 | 3 | Giá trị âm |
| `[10,9,2,5,3,7,101,18]` | 4 | 4 | Truy vết minh họa |
| `[3,4,-1,0,6,2,3]` | 4 | 4 | Cải thiện đuôi nhiều lần |

Nên thêm ca với `Integer.MIN_VALUE` và `Integer.MAX_VALUE` để tránh dùng phép trừ có thể tràn trong so sánh, và ca có rất nhiều phần tử trùng để kiểm tra không vượt số lượng phần tử.

### 16.2. Kiểm tra thuộc tính kết quả

Giả sử hàm trả `Result(length,indices,sequence)`. Một kết quả đúng phải thỏa:

1. `0≤length≤n`.
2. `indices.length==length` và `sequence.length==length`.
3. Với mọi k: `0≤indices[k]<n`, `sequence[k]==a[indices[k]]`.
4. Các chỉ số tăng nghiêm ngặt: `indices[k-1]<indices[k]`.
5. Các giá trị tăng nghiêm ngặt: `sequence[k-1]<sequence[k]`.
6. `length==quadraticLength(a)` nếu dùng bản DP bậc hai làm oracle trên dữ liệu nhỏ.
7. Input không thay đổi nếu hợp đồng của hàm yêu cầu điều đó.

Không chỉ kiểm tra rằng `sequence` đã được sắp tăng: một dãy đã sắp tăng nhưng **không xuất hiện theo đúng thứ tự chỉ số đầu vào** chưa chắc là subsequence hợp lệ.

### 16.3. Kiểm thử đối chiếu ngẫu nhiên

Trên nhiều mảng ngắn (ví dụ độ dài 0 đến 30, giá trị lấy trong khoảng hẹp để xuất hiện nhiều trùng):

1. Tính `quadraticLength`.
2. Tính `lisStrict`.
3. So sánh độ dài.
4. Kiểm tra mọi chỉ số và giá trị trong chuỗi được khôi phục.
5. Kiểm tra input không đổi.

Đây là kiểm thử có oracle độc lập, tốt hơn việc chỉ chạy một ví dụ thành công. Với mảng rất ngắn, có thể liệt kê mọi tập con chỉ số để brute-force LIS và dùng làm đối chứng thứ hai, nhưng chi phí tăng theo `2^n` nên không phù hợp n lớn.

### 16.4. Kiểm thử bất biến khi đang chạy

Trong một phiên bản debug, sau mỗi phần tử x, có thể khẳng định:

- `0≤length≤i+1`.
- `tails[0..length)` tăng nghiêm ngặt với LIS nghiêm ngặt.
- Nếu `length>0`, mỗi `tailIndex[t]` là chỉ số ≤i.
- `input[tailIndex[t]]==tails[t]`.
- Khi đã có con trỏ, `previous[i]` hoặc bằng -1 hoặc nhỏ hơn i; nếu khác -1 thì `input[previous[i]]<input[i]`.

Các khẳng định này không thay thế chứng minh toàn cục “đuôi nhỏ nhất cho từng độ dài”, nhưng rất hữu ích để bắt lỗi chỉ số và lỗi truy vết sớm.

## 17. Các lỗi thường gặp

1. **Nhầm subsequence với subarray**: chỉ tính đoạn tăng liên tiếp rồi trả đó là LIS.
2. **Sắp xếp input trước khi tính LIS**: làm mất thứ tự chỉ số gốc.
3. **Tìm kiếm nhị phân trên input chưa sắp xếp**, thay vì trên vùng `tails` đã được duy trì tăng.
4. **Dùng `upper_bound` cho LIS nghiêm ngặt**: các phần tử bằng nhau bị nối và làm dài sai.
5. **Dùng `lower_bound` cho dãy con không giảm**: ngăn nối các phần tử bằng nhau.
6. **Tìm trên toàn bộ mảng tails đã cấp phát**, gồm các giá trị 0 chưa sử dụng, thay vì `[0,length)`.
7. **Luôn append vào tails** thay vì **thay đuôi đầu tiên ≥x**: có thể tạo dãy không tăng hoặc đếm dài hơn thực tế.
8. **Trả tails như một LIS thực sự**: sau các lần thay đuôi, tails có thể không phải subsequence của input.
9. **Cập nhật tailIndex trước khi ghi previous**, làm mất một chỉ số cha cần dùng nếu cài đặt theo quy ước khác.
10. **Quên đặt previous[i]=-1** khi phần tử mở đầu một chuỗi.
11. **Chọn chỉ số cha không nhỏ hơn i**: có thể tạo liên kết sai thứ tự hoặc chu trình.
12. **Dùng phép trừ để so sánh hai số nguyên cực trị**, gây tràn `int`.
13. **Không xử lý mảng rỗng** rồi đọc `tailIndex[length-1]` khi `length=0`.
14. **Cho rằng chỉ có một LIS duy nhất**; trong nhiều dữ liệu có nhiều subsequence cùng độ dài tối ưu.
15. **Cho rằng tails đếm được số cách tạo LIS**; nó đã gộp bỏ nhiều ứng viên cùng độ dài.
16. **Nhầm độ phức tạp**: thuật toán có một vòng lặp n và một binary search `O(log n)` bên trong, không phải `O(n²)` vì có hai vòng lặp lồng nhau trong các hàm khác.
17. **Không giữ input nguyên vẹn theo hợp đồng** khi dùng thuật toán chọn/sắp xếp khác để “hỗ trợ” LIS.
18. **Quên khác biệt strict/non-decreasing trong phần khôi phục**, khiến dấu so sánh kiểm thử không khớp thuật toán.

## 18. Quy trình giải bài LIS trong thực tế

Khi đọc một đề liên quan đến dãy con tăng, có thể làm theo:

1. **Xác nhận kiểu dãy con:** có cần liên tiếp không? Nếu bắt buộc liên tiếp, không phải LIS tiêu chuẩn.
2. **Xác nhận quan hệ:** tăng nghiêm ngặt (`<`) hay không giảm (`<=`)?
3. **Xác nhận đầu ra:** độ dài, một dãy con, số cách, giá trị nhỏ nhất theo từ điển, hay tổng trọng số?
4. **Xác nhận ràng buộc n:** nếu n nhỏ, DP `O(n²)` dễ hiểu; nếu n lớn và chỉ cần độ dài/một đáp án, dùng tails + binary search.
5. **Chọn bất biến:** đuôi nhỏ nhất cho từng độ dài; giữ vùng tails đang hoạt động luôn có thứ tự.
6. **Nếu cần khôi phục:** thêm `tailIndex` và `previous` ngay khi xây, không suy ngược từ mảng tails cuối.
7. **Kiểm thử:** mảng rỗng, tăng, giảm, trùng, âm, cực trị; đối chiếu với DP bậc hai trên mảng ngắn.
8. **Chỉ tối ưu thêm khi yêu cầu khác:** đếm, dữ liệu động, LIS có trọng số và ràng buộc nhiều chiều có thể cần cấu trúc/thuật toán bổ sung.

## 19. Bài tập tự kiểm tra

**Bài 1 — Nhận diện định nghĩa.** Cho `a=[1,9,2,8,3,7]`. Hãy nêu một subsequence tăng nghiêm ngặt dài 4. Vì sao không thể lấy một đoạn liên tiếp dài 4 từ dãy này?

**Bài 2 — Quy hoạch động cơ bản.** Với `a=[3,1,2,5,4]`, tính `dp[i]` là độ dài LIS kết thúc tại từng i, rồi suy ra đáp án.

**Bài 3 — Vết tails.** Với `a=[10,9,2,5,3,7,101,18]`, ghi tails sau mỗi phần tử. Xác định bước nào tạo độ dài mới và bước nào chỉ cải thiện đuôi.

**Bài 4 — Phản ví dụ.** Chạy thuật toán tails với `a=[2,5,3,4,1]`. Giá trị tails cuối là gì? Vì sao không thể kết luận đây là một dãy con tăng của input?

**Bài 5 — Khôi phục.** Trong ví dụ chuẩn, nếu đuôi độ dài 4 ở chỉ số 7 và con trỏ `previous[7]=5`, `previous[5]=4`, `previous[4]=2`, `previous[2]=-1`, hãy khôi phục dãy chỉ số và dãy giá trị.

**Bài 6 — Phần tử trùng.** Với `a=[1,2,2,3]`, tính độ dài LIS nghiêm ngặt và độ dài dãy con không giảm. Tại sao hai kết quả khác nhau? Hàm nào cần dùng: lower bound hay upper bound?

**Bài 7 — Số âm.** Với `a=[3,4,-1,0,6,2,3]`, hãy tìm một LIS dài nhất. Độ dài là bao nhiêu?

**Bài 8 — Chứng minh.** Phát biểu bất biến `tails[t]`. Nếu `p` là chỉ số đầu tiên có `tails[p]≥x`, tại sao thay `tails[p]` bằng x là an toàn? Khi nào tăng length?

**Bài 9 — Đếm số LIS.** Với `a=[1,3,5,4,7]`, có bao nhiêu LIS theo bộ chỉ số, mỗi dãy dài bao nhiêu? Vì sao một mảng tails chưa đủ để biết số cách?

**Bài 10 — Chọn thuật toán.** Một bài có `n=200000`, chỉ cần độ dài LIS nghiêm ngặt. Nên cân nhắc `O(n²)` hay `O(n log n)`? Nếu thêm yêu cầu trả một LIS thực sự thì cần lưu thêm gì?

**Bài 11 — Mảng cực trị.** Với `a=[Integer.MIN_VALUE,0,Integer.MAX_VALUE]`, LIS dài bao nhiêu? Tại sao không nên dùng `tails[mid]-x` để quyết định nhánh binary search?

**Bài 12 — Dữ liệu động.** Vì sao có thể duy trì độ dài LIS khi append thêm một giá trị mới vào cuối dãy bằng một lần tìm nhị phân, nhưng không thể coi thao tác xóa phần tử tùy ý là “cập nhật tails ở một vị trí” tương tự?

### Đáp án gợi ý

1. Một LIS là `[1,2,3,7]`. Nó chọn các vị trí `0,2,4,5`, không liên tiếp; các đoạn liên tiếp của input không thể tạo độ dài 4 tăng nghiêm ngặt.
2. `dp=[1,1,2,3,3]`, đáp án `3`.
3. Tails lần lượt: `[10]`, `[9]`, `[2]`, `[2,5]`, `[2,3]`, `[2,3,7]`, `[2,3,7,101]`, `[2,3,7,18]`. Tăng length ở các bước có vị trí chèn bằng length cũ.
4. Tails cuối `[1,3,4]`. Số 1 xuất hiện cuối input, nên không thể đứng trước 3 và 4 trong một subsequence; LIS hợp lệ là `[2,3,4]`.
5. Lần ngược `7→5→4→2→-1`, đảo được chỉ số `[2,4,5,7]` và giá trị `[2,3,7,18]`.
6. Tăng nghiêm ngặt có độ dài `3` với lower bound (đầu tiên `>=x`); không giảm có độ dài `4` với upper bound (đầu tiên `>x`).
7. Độ dài `4`, ví dụ `[-1,0,2,3]` tại chỉ số `[2,3,5,6]`.
8. `tails[t]` là đuôi nhỏ nhất có thể đạt của dãy con tăng dài `t+1` trong tiền tố đã xử lý. Thay đuôi `>=x` bằng x không làm trạng thái kém đi; nếu `p=length`, tạo được độ dài mới.
9. Có **2 LIS** độ dài 4: `[1,3,5,7]` và `[1,3,4,7]`. Tails chỉ giữ một giá trị đuôi tối ưu cho mỗi độ dài, không lưu số cách.
10. Dùng thuật toán tails + binary search `O(n log n)`. Muốn khôi phục một đáp án, dùng `tailIndex` và `previous` để lưu nguồn gốc các trạng thái.
11. Độ dài `3`. Phép trừ hai `int` có thể tràn, còn phép so sánh quan hệ `<`/`<=` an toàn cho các giá trị cực trị.
12. Append chỉ thêm một phần tử cuối và có thể cập nhật từ các đuôi đã duy trì. Xóa phần tử cũ có thể làm mất một trạng thái/đường nối quan trọng và thay đổi nhiều lựa chọn tương lai; không có quy tắc thay một ô tails đơn giản cho mọi trường hợp.

## Ghi nhớ

LIS là **dãy con tăng nghiêm ngặt dài nhất nhưng không cần liên tiếp**. Công thức DP `O(n²)` xét mọi tiền tố kết thúc tại từng vị trí. Để tối ưu, thay vì giữ mọi dãy con cùng độ dài, ta chỉ giữ **đuôi nhỏ nhất có thể** trong mảng `tails`, luôn tăng nghiêm ngặt trên vùng đang hoạt động. Mỗi phần tử được đặt tại **lower_bound** (đuôi đầu tiên `>=x`), nên một lần xử lý mất `O(log n)` và toàn bài `O(n log n)`. **Tails không nhất thiết là một subsequence hợp lệ**; để trả một LIS thực sự, cần thêm **tailIndex và previous**. Nếu bài yêu cầu **không giảm**, đổi sang **upper_bound** (đầu tiên `>x`). Nếu bài hỏi **đếm số cách, trọng số, quy tắc chọn đáp án phụ hoặc cập nhật động**, phải thiết kế trạng thái/thuật toán bổ sung; không thể áp dụng máy móc bản tails chỉ lưu độ dài.
