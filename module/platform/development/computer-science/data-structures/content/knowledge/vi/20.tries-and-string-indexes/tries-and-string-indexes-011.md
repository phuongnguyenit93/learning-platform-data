# Mảng hậu tố và mảng tiền tố chung dài nhất

> **Chương:** Trie và chỉ mục chuỗi · **Bài học:** Mảng hậu tố và mảng tiền tố chung dài nhất

Cho văn bản `banana`, mẫu `ana` xuất hiện ở vị trí 1 và 3. Nếu cần tìm hàng triệu mẫu trên cùng một văn bản, việc quét từ trái sang phải cho từng mẫu có thể lặp lại nhiều công việc. Cây hậu tố tổ chức các hậu tố thành một cây; còn **mảng hậu tố** (*suffix array*, viết tắt `SA`) chọn biểu diễn gọn hơn: lưu **các vị trí bắt đầu của hậu tố theo thứ tự từ điển**.

Khi đã biết thứ tự hậu tố, ta thường muốn biết **hai hậu tố đứng cạnh nhau giống nhau được bao nhiêu ký hiệu đầu**. Đó là nhiệm vụ của **mảng tiền tố chung dài nhất** (*Longest Common Prefix array*, viết tắt `LCP`). Hai mảng `SA` và `LCP` bổ sung cho nhau: `SA` sắp các hậu tố để tìm bằng tìm kiếm nhị phân, còn `LCP` ghi lại mức chia sẻ tiền tố để hỗ trợ các bài toán về chuỗi con lặp, số chuỗi con khác nhau và so sánh hậu tố.

Bài thuộc chương **Trie và chỉ mục chuỗi** của mô-đun Cấu trúc dữ liệu (`COMPUTER_SCIENCE_DATA_STRUCTURES`). Mục tiêu rộng của mô-đun là hiểu mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị qua bất biến, thao tác và độ phức tạp. Bài này minh họa một tư duy quan trọng: có thể thay một cấu trúc cây nhiều con trỏ bằng **hai mảng chỉ số**, miễn ta xác định rõ thứ tự, ý nghĩa từng ô và chi phí truy vấn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **hậu tố**, **chuỗi con liên tiếp** và **tiền tố chung** của hai chuỗi.
2. Tự tính `SA` và `LCP` của `banana` và giải thích các giá trị bằng bảng hậu tố đã sắp.
3. Phát biểu bất biến `SA` là một **hoán vị** của các vị trí bắt đầu hậu tố, được xếp theo thứ tự từ điển.
4. Phát biểu quy ước `LCP[0]=0` và `LCP[r]=lcp(s[SA[r-1]:],s[SA[r]:])` với `r≥1`.
5. Xây `SA` bằng **prefix doubling** và phân tích vì sao bản dùng `sort` thông thường có độ phức tạp O(n log² n).
6. Xây `LCP` bằng thuật toán **Kasai** trong O(n) thời gian sau khi biết `SA`.
7. Dùng **hai lần tìm kiếm nhị phân** để xác định khoảng hậu tố bắt đầu bằng một mẫu.
8. Đếm và liệt kê vị trí xuất hiện, kể cả các lần xuất hiện **chồng lấn**.
9. Tính số chuỗi con khác nhau bằng tổng độ dài hậu tố trừ tổng `LCP`.
10. Tìm một chuỗi con lặp dài nhất từ giá trị `LCP` lớn nhất.
11. Dùng **RMQ** (*Range Minimum Query*) trên `LCP` để tìm độ dài tiền tố chung của hai hậu tố bất kỳ.
12. Đánh giá chi phí bộ nhớ, Unicode, vị trí byte/code point và lựa chọn giữa suffix array, suffix tree hoặc tìm kiếm trực tiếp.

## 2. Hậu tố, tiền tố và chuỗi con liên tiếp

Cho `s` có `n` ký hiệu, đánh số từ `0` tới `n-1`. Trong Python, `s[i:j]` lấy các ký hiệu ở vị trí từ `i` đến **trước** `j`.

- **Tiền tố** (*prefix*) của `s`: `s[:j]`, với `0≤j≤n`.
- **Hậu tố** (*suffix*) của `s`: `s[i:]`, với `0≤i≤n`.
- **Chuỗi con liên tiếp** (*substring*) của `s`: `s[i:j]`, với `0≤i≤j≤n`.

Hậu tố `s[n:]` là chuỗi rỗng. Trong bài này, **mảng hậu tố chính** chỉ lưu `n` hậu tố **không rỗng**, tức các vị trí `0,\ldots,n-1`. Đó là một quy ước phổ biến; một số tài liệu hoặc thuật toán chọn thêm hậu tố rỗng hoặc một ký hiệu kết thúc.

### 2.1. Một ví dụ nhỏ

```text
s = "banana"

Vị trí:  0 1 2 3 4 5
Ký hiệu: b a n a n a
```

Tất cả hậu tố không rỗng:

| Vị trí `i` | Hậu tố `s[i:]` |
| ---: | --- |
| 0 | `banana` |
| 1 | `anana` |
| 2 | `nana` |
| 3 | `ana` |
| 4 | `na` |
| 5 | `a` |

Mẫu `ana` xuất hiện tại vị trí `i` khi `s[i:]` **bắt đầu bằng** `ana`. Cả hậu tố `anana` ở vị trí 1 và `ana` ở vị trí 3 đều thỏa.

### 2.2. Chuỗi con không phải subsequence

`bnn` có thể được lấy từ `banana` bằng việc chọn ký tự ở các vị trí không liền nhau, nhưng **không phải chuỗi con liên tiếp** của `banana`.

Suffix array trong bài chỉ mục **chuỗi con liên tiếp**, không trực tiếp phục vụ mọi subsequence.

### 2.3. Vì sao tìm substring quy về tìm suffix?

Với một mẫu `p` dài `m`:

\[
p=s[i:i+m]
\iff s[i:]\text{ bắt đầu bằng }p.
\]

Do đó, nếu ta có một cách tìm nhanh các hậu tố bắt đầu bằng `p`, ta đồng thời tìm được tất cả vị trí mà `p` xuất hiện trong `s`.

## 3. Mảng hậu tố `SA` là gì?

Định nghĩa:

\[
SA=[i_0,i_1,\ldots,i_{n-1}]
\]

sao cho `SA` là hoán vị của `0,\ldots,n-1` và:

\[
s[SA[0]:] < s[SA[1]:] < \cdots < s[SA[n-1]:]
\]

theo thứ tự từ điển của các dãy ký hiệu.

### 3.1. Sắp các hậu tố của `banana`

| Thứ hạng `r` | `SA[r]` | Hậu tố tại vị trí đó |
| ---: | ---: | --- |
| 0 | 5 | `a` |
| 1 | 3 | `ana` |
| 2 | 1 | `anana` |
| 3 | 0 | `banana` |
| 4 | 4 | `na` |
| 5 | 2 | `nana` |

Vậy:

```text
SA = [5, 3, 1, 0, 4, 2]
```

Đây là **mảng chỉ số**, không phải mảng chứa các chuỗi `a, ana, anana, ...`.

### 3.2. Quy tắc một hậu tố là tiền tố của hậu tố khác

`a` đứng **trước** `ana` vì chúng giống nhau ở ký hiệu đầu `a`, nhưng hậu tố thứ nhất **kết thúc sớm hơn**.

Tương tự `na < nana`. Nếu chỉ so sánh cho đến khi hết chuỗi ngắn và coi hai chuỗi bằng nhau, thứ tự hậu tố sẽ sai.

### 3.3. Mảng đảo `rank`

Định nghĩa:

\[
rank[SA[r]]=r.
\]

`rank[i]` cho biết hậu tố bắt đầu tại vị trí `i` **đứng thứ mấy** trong `SA`.

Với `banana`:

```text
i:       0 1 2 3 4 5
SA:      5 3 1 0 4 2
rank:    3 2 5 1 4 0
```

Ví dụ:

- `SA[2]=1`: hậu tố hạng 2 bắt đầu ở vị trí 1.
- `rank[1]=2`: hậu tố bắt đầu vị trí 1 có hạng 2.

Lưu ý `SA[i]` và `rank[i]` **không có cùng ý nghĩa**. Nhầm hai mảng là một lỗi rất thường gặp khi viết Kasai hoặc RMQ.

### 3.4. Trường hợp chuỗi rỗng

Nếu `s=""` thì `n=0` và:

```text
SA = []
rank = []
```

Không có hậu tố không rỗng để đưa vào mảng. Các API tìm mẫu rỗng sẽ được xử lý riêng theo hợp đồng sau.

## 4. Có cần ký hiệu kết thúc `$` không?

Không bắt buộc đối với **định nghĩa và mã xây `SA` của bài này**. Chúng ta so sánh trực tiếp các hậu tố của `s`, kể cả quy tắc chuỗi ngắn hơn đứng trước khi nó là tiền tố.

Tuy nhiên, trong suffix tree hoặc một số thuật toán xây suffix array, người ta có thể thêm **ký hiệu kết thúc duy nhất** nhỏ hơn mọi ký hiệu dữ liệu.

### 4.1. Hai quy ước trên cùng ví dụ

Không thêm ký hiệu kết thúc:

```text
s = "banana"
SA = [5, 3, 1, 0, 4, 2]
```

Nếu `T="banana$"`, với `$` là ký hiệu mới nhỏ hơn mọi ký hiệu dữ liệu và đưa cả hậu tố `"$"` vào:

```text
T = "banana$"
SA_T = [6, 5, 3, 1, 0, 4, 2]
```

Hậu tố chỉ có `$` đứng đầu. Thứ tự tương đối của sáu hậu tố bắt đầu trong văn bản gốc không thay đổi ở ví dụ này.

**Quan trọng:** thuật toán chính ở các mục tiếp theo **không thêm `$`**, nên `SA` luôn có đúng `n` phần tử. Không được lấy `SA_T` bảy phần tử rồi lắp vào một công thức hay một đoạn mã đang giả định `SA` sáu phần tử mà không điều chỉnh.

### 4.2. Mẫu rỗng vẫn cần quy ước riêng

Ta chọn:

\[
occurrences("")=[0,1,\ldots,n].
\]

Tức mẫu rỗng xuất hiện tại `n+1` **ranh giới**, bao gồm sau ký hiệu cuối. Trong khi đó `SA` chỉ giữ các vị trí bắt đầu hậu tố không rỗng `0,\ldots,n-1`. Đây là lý do hàm truy vấn **phải xử lý mẫu rỗng riêng**.

## 5. Tại sao lưu chỉ số thay vì lưu tất cả hậu tố?

Các hậu tố có độ dài:

\[
n,\ n-1,\ \ldots,\ 1.
\]

Tổng số ký hiệu nếu **sao chép tất cả hậu tố** là:

\[
n+(n-1)+\cdots+1
=\frac{n(n+1)}2
=\Theta(n^2).
\]

Trong khi đó, `SA` chỉ cần `n` chỉ số bắt đầu, cộng với văn bản gốc `s` được lưu một lần.

### 5.1. Đếm ô dữ liệu theo mô hình

Với `n=100\,000`:

- Số hậu tố: 100.000.
- Tổng độ dài các bản sao hậu tố: `100\,000\cdot100\,001/2=5\,000\,050\,000` ký hiệu.
- Số vị trí trong `SA`: **100.000**.
- Số vị trí trong `LCP`: **100.000**.

Nếu một chỉ số chiếm một từ máy, hai mảng có O(n) từ máy. Các chi tiết về byte thực tế còn phụ thuộc kiểu số nguyên, overhead container và runtime.

### 5.2. Một cách dựng dễ hiểu nhưng không tiết kiệm

```python
def suffix_array_naive(text):
    return sorted(
        range(len(text)),
        key=lambda i: text[i:]
    )
```

Mã này đúng về thứ tự từ điển, nhưng `text[i:]` tạo chuỗi hậu tố mới trong Python. Phần dữ liệu tạo tạm có thể có tổng chiều dài Θ(n²), và các phép so sánh chuỗi cũng có thể đắt.

Đây là **mô hình tham chiếu để kiểm thử trên dữ liệu nhỏ**, không phải thuật toán nên dùng để xây chỉ mục lớn.

### 5.3. Không tạo chuỗi mới không tự làm thời gian tuyến tính

Một thuật toán có thể chỉ lưu các chỉ số nhưng vẫn **so sánh ký hiệu của cùng một hậu tố nhiều lần**. Bộ nhớ ít hơn và thời gian xây nhanh hơn là hai mục tiêu phải phân tích riêng.

## 6. Xây mảng hậu tố bằng cách nhân đôi độ dài so sánh

Một thuật toán cơ bản và có tính giáo dục cao là **prefix doubling** (*nhân đôi tiền tố*).

Ý tưởng:

1. Mỗi hậu tố được xếp hạng theo **một số ký hiệu đầu**.
2. Ở vòng tiếp theo, dùng cặp thứ hạng để xếp theo **đoạn dài gấp đôi**.
3. Khi tất cả thứ hạng đã phân biệt được các hậu tố, `SA` đã hoàn chỉnh.

Ta dùng `k` là độ dài đoạn đang được so sánh. Ban đầu có thể lấy `k=1` theo ký hiệu đầu. Để xét đoạn dài `2k`, khóa sắp của hậu tố bắt đầu tại `i` là:

\[
key_k(i)=(rank_k[i],rank_k[i+k]).
\]

Nếu `i+k≥n`, ta dùng một giá trị canh gác **`-1`**, nhỏ hơn mọi thứ hạng hợp lệ.

### 6.1. Vì sao cặp thứ hạng là đủ?

Đoạn dài `2k` có hai nửa, mỗi nửa dài tối đa `k`:

```text
s[i : i+2k]
  = s[i:i+k] + s[i+k:i+2k]
```

Nếu `rank_k` đã biểu diễn thứ tự của các đoạn dài `k`, so sánh hai cặp thứ hạng tương ứng là đủ để sắp các đoạn dài `2k`.

Vì các số hạng của cặp là **số nguyên**, mỗi phép so cặp có giá O(1) trong mô hình từ máy thích hợp. Ta tránh việc so đi so lại toàn bộ những đoạn ký tự dài trong mỗi lần sort.

### 6.2. Giá trị canh gác `-1`

Khi đoạn thứ hai vượt quá cuối văn bản, ta đặt `rank_k[i+k]=-1`.

Ví dụ `s="ana"`, hậu tố `"a"` phải đứng trước `"ana"`. Khi so sánh đoạn dài 2, hậu tố cuối có nửa thứ hai **đã hết** nên cần thứ hạng nhỏ hơn mọi ký hiệu thực.

Với rank hợp lệ không âm, `-1` là lựa chọn đơn giản để bảo toàn quy tắc kết thúc sớm.

### 6.3. Khi nào dừng?

Sau một lần sắp, gán các hạng mới từ 0 trở lên:

- Hai hậu tố có cặp thứ hạng **giống nhau** thì cùng hạng tạm.
- Cặp khác nhau thì hạng tăng thêm 1.

Nếu hạng lớn nhất bằng `n-1`, đã có `n` hạng phân biệt cho `n` hậu tố: thứ tự hoàn chỉnh, có thể dừng.

Nếu chưa, nhân đôi `k` và lặp.

## 7. Vết prefix doubling trên `banana`

Với văn bản:

```text
i:    0 1 2 3 4 5
s[i]: b a n a n a
```

### 7.1. Vòng k=1: so hai ký hiệu đầu

Khóa sắp được biểu diễn bằng cặp ký hiệu hoặc cặp hạng:

| `i` | Hai ký hiệu đầu | Nhận xét |
| ---: | --- | --- |
| 0 | `ba` | Bắt đầu bằng b |
| 1 | `an` | Bắt đầu bằng a |
| 2 | `na` | Bắt đầu bằng n |
| 3 | `an` | Tạm hòa với vị trí 1 |
| 4 | `na` | Tạm hòa với vị trí 2 |
| 5 | `a + hết` | Hậu tố ngắn hơn `an` |

Thứ tự sau vòng này:

```text
SA = [5, 1, 3, 0, 2, 4]
```

Các thứ hạng tạm theo vị trí `i`:

```text
rank_2 = [2, 1, 3, 1, 3, 0]
```

Hậu tố ở vị trí 1 và 3 vẫn cùng hạng vì hai ký hiệu đầu đều là `an`. Hậu tố ở vị trí 2 và 4 cũng cùng hạng vì đều bắt đầu `na`.

### 7.2. Vòng k=2: so bốn ký hiệu đầu

Dùng `rank_2` của hai nửa độ dài 2:

| `i` | Cặp `(rank_2[i],rank_2[i+2])` |
| ---: | --- |
| 0 | `(2,3)` |
| 1 | `(1,1)` |
| 2 | `(3,3)` |
| 3 | `(1,0)` |
| 4 | `(3,-1)` |
| 5 | `(0,-1)` |

Sắp các cặp tăng dần cho:

```text
SA = [5, 3, 1, 0, 4, 2]
```

Lúc này mọi hạng đã khác nhau. Đây cũng là thứ tự hậu tố đầy đủ của `banana`, nên có thể dừng.

### 7.3. Bất biến qua các vòng

Sau khi xử lý đoạn dài `2k`, những hạng đã tạo cho biết thứ tự từ điển của các đoạn độ dài `2k` (có thể ngắn hơn khi tới cuối chuỗi).

Nếu hai hậu tố vẫn hòa hạng, thuật toán cần xét đoạn dài hơn; nếu không còn hòa, thứ tự đã đủ để sắp toàn bộ hậu tố.

**Không cần tạo các chuỗi `s[i:i+2k]`** để làm khóa sort; chỉ dùng cặp số nguyên lấy từ mảng hạng.

## 8. Cài đặt Python: xây `SA` bằng prefix doubling

Mã sau xử lý văn bản `str` Python theo **Unicode code point**, không thêm ký hiệu kết thúc và trả về đúng `n` chỉ số.

```python
def build_suffix_array(text):
    """Xây SA của các hậu tố không rỗng của text.

    Kết quả là hoán vị các vị trí 0..n-1,
    sắp theo thứ tự từ điển của text[i:].
    """
    if not isinstance(text, str):
        raise TypeError("text phải là str")

    n = len(text)
    if n == 0:
        return []

    sa = list(range(n))
    # ord cho thứ tự code point, mọi hạng ban đầu >= 0.
    rank = [ord(ch) for ch in text]
    gap = 1

    while True:
        # So hai nửa độ dài gap; -1 là đã hết chuỗi.
        sa.sort(
            key=lambda i: (
                rank[i],
                rank[i + gap] if i + gap < n else -1,
            )
        )

        new_rank = [0] * n

        for r in range(1, n):
            prev = sa[r - 1]
            cur = sa[r]

            prev_pair = (
                rank[prev],
                rank[prev + gap] if prev + gap < n else -1,
            )
            cur_pair = (
                rank[cur],
                rank[cur + gap] if cur + gap < n else -1,
            )

            new_rank[cur] = (
                new_rank[prev] + int(prev_pair != cur_pair)
            )

        rank = new_rank

        # Các hạng 0..n-1 đều khác nhau.
        if rank[sa[-1]] == n - 1:
            return sa

        gap *= 2
```

### 8.1. Ví dụ sử dụng

```python
assert build_suffix_array("") == []
assert build_suffix_array("a") == [0]
assert build_suffix_array("banana") == [5, 3, 1, 0, 4, 2]
assert build_suffix_array("aaaa") == [3, 2, 1, 0]
assert build_suffix_array("abab") == [2, 0, 3, 1]
```

Kiểm tra `abab`:

```text
2: ab
0: abab
3: b
1: bab
```

Hậu tố `ab` đứng trước `abab`, `b` đứng trước `bab`. Đây là một trường hợp kiểm tra đúng quy tắc kết thúc sớm.

### 8.2. Vì sao là O(n log² n) trong bản này?

Mỗi vòng:

- Tạo khóa sắp theo cặp hạng O(1) từ máy mỗi phần tử.
- Dùng `sa.sort` trên `n` vị trí, tối đa O(n log n) phép so cặp ở trường hợp xấu.
- Tính lại hạng trong O(n).

Số vòng tối đa O(log(n+1)) do `gap` được nhân đôi. Bởi vậy, trong mô hình từ máy với so số nguyên O(1):

\[
T_{\mathrm{build}}=O(n\log^2(n+1)).
\]

Bộ nhớ ngoài văn bản gốc là O(n) phần tử cho `sa`, `rank`, `new_rank` và vùng làm việc của sort.

### 8.3. Có thể xây nhanh hơn không?

Có. Dùng **radix/counting sort** cho cặp hạng ở mỗi vòng có thể giảm thời gian mỗi vòng xuống O(n) trong điều kiện bảng hạng thích hợp, cho một thuật toán prefix doubling O(n log n).

Còn có các họ thuật toán xây mảng hậu tố tuyến tính như SA-IS hoặc DC3/skew trong các giả định phù hợp. Không nên gọi bản dùng `sort` thông thường ở trên là O(n log n) chỉ vì các khóa so sánh là cặp số nguyên.

## 9. Mảng LCP: tiền tố chung của hai hậu tố kề nhau

Định nghĩa `lcp(x,y)` là độ dài của **tiền tố chung dài nhất** giữa hai chuỗi `x` và `y`.

Với `SA` đã sắp:

\[
LCP[0]=0,
\]

\[
LCP[r]=lcp\big(s[SA[r-1]:],s[SA[r]:]\big),
\qquad 1\le r<n.
\]

Ta chọn quy ước **LCP[r] so hậu tố ở hạng r với hạng r−1**. Một số tài liệu dùng mảng dài `n-1` với `LCP[r]` so hậu tố ở hạng `r` và `r+1`. Hai cách chỉ **lệch chỉ số**, nhưng không được trộn lẫn.

### 9.1. LCP của `banana`

| `r` | `SA[r]` | Hậu tố | `LCP[r]` | Giải thích |
| ---: | ---: | --- | ---: | --- |
| 0 | 5 | `a` | 0 | Không có hậu tố đứng trước |
| 1 | 3 | `ana` | 1 | `a` chung với `a` |
| 2 | 1 | `anana` | 3 | `ana` chung với `ana` |
| 3 | 0 | `banana` | 0 | `anana` và `banana` khác ngay đầu |
| 4 | 4 | `na` | 0 | `banana` và `na` khác ngay đầu |
| 5 | 2 | `nana` | 2 | `na` chung với `nana` |

Vậy:

```text
SA  = [5, 3, 1, 0, 4, 2]
LCP = [0, 1, 3, 0, 0, 2]
```

### 9.2. Ý nghĩa của `LCP[r]`

- `LCP[r]=0`: hai hậu tố kề nhau khác ký hiệu đầu.
- `LCP[r]=k>0`: chúng có cùng đúng `k` ký hiệu đầu, rồi khác ký hiệu tiếp theo hoặc một hậu tố kết thúc.
- `LCP[r]` không phải **độ dài hậu tố**.
- `LCP[r]` không phải LCP giữa hai hậu tố ở vị trí gốc `r-1` và `r`; nó so theo **thứ hạng trong SA**.

### 9.3. Chặn hiển nhiên

Với `r≥1`:

\[
0\le LCP[r]\le
\min(n-SA[r-1],n-SA[r]).
\]

Nếu LCP vượt độ dài của một trong hai hậu tố, dữ liệu hoặc công thức chắc chắn sai.

## 10. Cách tính LCP trực tiếp và vì sao có thể chậm

Một cách dễ viết là xét từng cặp hậu tố kề nhau và đếm số ký hiệu chung:

```python
def lcp_length(text, i, j):
    n = len(text)
    h = 0

    while (
        i + h < n
        and j + h < n
        and text[i + h] == text[j + h]
    ):
        h += 1

    return h


def lcp_array_naive(text, sa):
    n = len(text)
    if n == 0:
        return []

    lcp = [0] * n
    for r in range(1, n):
        lcp[r] = lcp_length(text, sa[r - 1], sa[r])

    return lcp
```

Mã này đơn giản và đúng, phù hợp để đối chiếu trên văn bản ngắn. Nhưng có thể nhiều cặp hậu tố kề nhau chia sẻ **những đoạn rất dài**, khiến cùng ký hiệu bị so sánh lặp lại.

Ví dụ `s="aaaaaa..."`, các hậu tố gần nhau có LCP rất lớn. Tổng lượng ký hiệu so sánh của cách trực tiếp có thể đạt Θ(n²).

Ta cần tận dụng quan hệ giữa **những hậu tố bắt đầu ở vị trí liên tiếp của văn bản**, thay vì tính mỗi LCP từ 0.

## 11. Ý tưởng thuật toán Kasai trong O(n)

**Kasai** xây `LCP` trong **thời gian tuyến tính** sau khi đã có `SA`.

Đầu vào:

- Văn bản `s` dài `n`.
- `SA` là hoán vị vị trí hậu tố theo thứ tự từ điển.

Bước chuẩn bị tạo `rank`:

\[
rank[SA[r]]=r.
\]

Sau đó duyệt các vị trí văn bản `i=0,1,\ldots,n-1` — **không duyệt theo thứ tự `SA`**.

### 11.1. Tham số `h`

`h` là số ký hiệu chung đầu đã biết hoặc có thể tái sử dụng từ lượt trước.

Với hậu tố bắt đầu ở `i` và hạng `r=rank[i]`:

- Nếu `r=0`, không có hậu tố đứng trước trong SA, đặt `h=0`.
- Nếu `r>0`, lấy `j=SA[r-1]`.
- Tiếp tục so `s[i+h]` với `s[j+h]` khi còn trong biên và bằng nhau.
- Ghi `LCP[r]=h`.
- Trước khi sang `i+1`, giảm `h` đi 1 nếu `h>0`.

### 11.2. Vì sao có thể bắt đầu ở `h-1`?

Nếu hai hậu tố có chung `h` ký hiệu đầu, sau khi bỏ ký hiệu đầu của chúng, hai hậu tố đuôi vẫn có chung ít nhất `h-1` ký hiệu. Dựa trên tính chất thứ tự từ điển và quan hệ giữa các hậu tố kề nhau, Kasai chứng minh có thể dùng `h-1` làm cận dưới thích hợp cho lượt kế tiếp trong quá trình duyệt vị trí `i`.

Trực giác: **dịch điểm bắt đầu đi một ký hiệu thì độ dài tiền tố chung đã biết giảm nhiều nhất một**, nếu không thay đổi cặp theo cách làm mất cận dưới tương ứng. Cách triển khai dùng `rank` và hậu tố liền trước bảo toàn điều kiện cần cho giá trị `h` tái sử dụng.

Đây là bất biến quan trọng của Kasai, không phải một mẹo cắt vòng lặp tùy tiện.

### 11.3. Tại sao tổng thời gian O(n)?

Ở mỗi bước `i`:

- `h` có thể **tăng** trong vòng `while`.
- Kết thúc lượt, `h` giảm tối đa 1.
- Các lượt `i` chỉ có `n` lần, và `h` không thể vượt `n`.

Phân tích khấu hao cho thấy tổng số lần tăng `h` qua mọi lượt là O(n); phần việc còn lại trong mỗi lượt là O(1). Do đó:

\[
T_{\mathrm{Kasai}}=O(n)
\]

trong mô hình đọc/so sánh ký hiệu và truy cập mảng O(1).

## 12. Cài đặt Python: `LCP` bằng Kasai

```python
def build_lcp(text, sa):
    """Trả (lcp, rank) theo quy ước lcp[0]=0.

    sa phải là hoán vị hậu tố đúng thứ tự.
    """
    n = len(text)
    if len(sa) != n:
        raise ValueError("SA phải có đúng n phần tử")

    rank = [0] * n
    for r, start in enumerate(sa):
        rank[start] = r

    lcp = [0] * n
    h = 0

    for i in range(n):
        r = rank[i]

        if r == 0:
            h = 0
            continue

        j = sa[r - 1]

        while (
            i + h < n
            and j + h < n
            and text[i + h] == text[j + h]
        ):
            h += 1

        lcp[r] = h

        if h > 0:
            h -= 1

    return lcp, rank
```

### 12.1. Ví dụ chạy

```python
s = "banana"
sa = build_suffix_array(s)
lcp, rank = build_lcp(s, sa)

assert sa == [5, 3, 1, 0, 4, 2]
assert lcp == [0, 1, 3, 0, 0, 2]
assert rank == [3, 2, 5, 1, 4, 0]
assert all(rank[sa[r]] == r for r in range(len(s)))
```

### 12.2. Chuỗi lặp nhiều ký hiệu

Với `s="aaaaa"`:

```text
SA  = [4, 3, 2, 1, 0]
LCP = [0, 1, 2, 3, 4]
```

Kiểm tra:

```python
sa = build_suffix_array("aaaaa")
lcp, rank = build_lcp("aaaaa", sa)

assert sa == [4, 3, 2, 1, 0]
assert lcp == [0, 1, 2, 3, 4]
```

Đây là dữ liệu mà phương pháp so LCP từ đầu cho từng cặp dễ lặp lại nhiều lần so ký hiệu, trong khi Kasai vẫn có bảo đảm O(n).

### 12.3. Phân biệt hai lần sử dụng `rank`

- Trong **prefix doubling**, `rank` là **thứ hạng tạm của các đoạn dài k** và thay đổi qua vòng.
- Trong **Kasai**, `rank` là **mảng nghịch đảo của SA cuối cùng**.

Cả hai gọi là rank nhưng có vai trò và thời điểm khác nhau. Nếu vô tình đưa rank chưa hoàn chỉnh vào Kasai, kết quả có thể sai.

## 13. Tìm một mẫu bằng khoảng hậu tố liên tiếp

Giả sử cần tìm tất cả lần xuất hiện của `p` trong `s`. Các hậu tố bắt đầu bằng cùng `p` xuất hiện trong một **khoảng liên tiếp** của `SA`.

### 13.1. Tại sao các hậu tố khớp nằm liền nhau?

Thứ tự hậu tố là thứ tự từ điển. Những chuỗi bắt đầu bằng `p` có phần đầu giống hệt nhau. Một hậu tố `x` không bắt đầu bằng `p` chỉ có thể:

- Nhỏ hơn nhóm khớp `p`, hoặc
- Lớn hơn nhóm khớp `p`,

theo ký hiệu đầu tiên nơi nó khác `p` (kể cả trường hợp `x` hết trước `p`). Nó **không thể chen vào giữa hai hậu tố cùng bắt đầu bằng `p`**.

Vì vậy tồn tại khoảng nửa mở:

\[
SA[left:right]
\]

chứa chính xác các vị trí xuất hiện của mẫu không rỗng.

### 13.2. So sánh hậu tố với mẫu theo quan hệ ba chiều

Ta định nghĩa:

```text
compare(suffix, pattern) =
    -1  nếu suffix nhỏ hơn pattern về từ điển
     0  nếu suffix bắt đầu bằng toàn bộ pattern
    +1  nếu suffix lớn hơn pattern về từ điển
```

Chú ý giá trị 0 **không có nghĩa hai chuỗi bằng nhau toàn bộ**. Nó nghĩa **mẫu là tiền tố của hậu tố**.

Ví dụ:

| Hậu tố | Mẫu `ana` | Kết quả |
| --- | --- | ---: |
| `a` | `ana` | -1 |
| `ana` | `ana` | 0 |
| `anana` | `ana` | 0 |
| `banana` | `ana` | +1 |
| `na` | `ana` | +1 |

Theo `SA`, những kết quả `-1` đứng trước các kết quả `0`, và các kết quả `+1` đứng sau.

### 13.3. Hai lần binary search

- Tìm `left`: vị trí đầu tiên có `compare≥0`.
- Tìm `right`: vị trí đầu tiên có `compare>0`.

Khoảng `[left,right)` là toàn bộ hậu tố khớp mẫu.

Đây là một áp dụng điển hình của **lower bound** và **upper bound** trên một dãy đã sắp.

## 14. Mã Python: so sánh mẫu, tìm khoảng và xuất vị trí

Mã sau ghép các hàm xây `SA` và `LCP` vào một lớp chỉ mục.

### 14.1. Lớp chỉ mục

```python
class SuffixArrayIndex:
    def __init__(self, text):
        if not isinstance(text, str):
            raise TypeError("text phải là str")

        self.text = text
        self.sa = build_suffix_array(text)
        self.lcp, self.rank = build_lcp(text, self.sa)

    @staticmethod
    def _check_pattern(pattern):
        if not isinstance(pattern, str):
            raise TypeError("pattern phải là str")

    def _compare_at(self, suffix_start, pattern):
        """-1, 0, +1; 0 nghĩa suffix bắt đầu bằng pattern."""
        s = self.text
        n = len(s)
        m = len(pattern)
        j = 0

        while j < m and suffix_start + j < n:
            a = s[suffix_start + j]
            b = pattern[j]

            if a < b:
                return -1
            if a > b:
                return 1
            j += 1

        if j == m:
            return 0

        # Hậu tố hết trước khi mẫu hết.
        return -1

    def _match_range(self, pattern):
        """Khoảng [left,right) các hậu tố khớp prefix."""
        size = len(self.sa)
        low = 0
        high = size

        # Lower bound: compare >= 0.
        while low < high:
            mid = (low + high) // 2
            value = self._compare_at(self.sa[mid], pattern)

            if value < 0:
                low = mid + 1
            else:
                high = mid

        left = low
        low = left
        high = size

        # Upper bound: compare > 0.
        while low < high:
            mid = (low + high) // 2
            value = self._compare_at(self.sa[mid], pattern)

            if value <= 0:
                low = mid + 1
            else:
                high = mid

        return left, low

    def contains(self, pattern):
        self._check_pattern(pattern)

        if pattern == "":
            return True

        left, right = self._match_range(pattern)
        return left < right

    def count(self, pattern):
        self._check_pattern(pattern)

        # Chuỗi rỗng có n+1 ranh giới.
        if pattern == "":
            return len(self.text) + 1

        left, right = self._match_range(pattern)
        return right - left

    def occurrences(self, pattern):
        """Mọi vị trí khớp, tăng theo vị trí văn bản."""
        self._check_pattern(pattern)

        if pattern == "":
            return list(range(len(self.text) + 1))

        left, right = self._match_range(pattern)
        return sorted(self.sa[left:right])
```

### 14.2. Vì sao `_compare_at` không tạo chuỗi hậu tố?

Hàm không dùng `self.text[suffix_start:]`. Thay vào đó, nó đọc các ký hiệu của văn bản tại `suffix_start+j` và ký hiệu mẫu tại `j`.

Mỗi phép so sánh giữa một hậu tố với mẫu dài `m` tốn **O(m+1)** phép kiểm tra ký hiệu trong trường hợp xấu, nhưng không yêu cầu tạo một bản sao hậu tố.

### 14.3. Vì sao `occurrences` phải sắp kết quả?

Thứ tự trong `SA[left:right]` là **thứ tự từ điển của các hậu tố**, không phải thứ tự vị trí trong văn bản.

Với `banana` và `ana`:

```text
Các hậu tố khớp theo SA:
ana    (vị trí 3)
anana  (vị trí 1)

SA[left:right] = [3, 1]
```

Hợp đồng `occurrences` trong bài muốn `[1,3]`, vì vậy cần `sorted`. Nếu giao diện chấp nhận thứ tự từ điển hậu tố, có thể bỏ bước sắp và trả luôn lát cắt chỉ số.

### 14.4. Khi mẫu không tồn tại

Hai binary search vẫn tìm được `left=right`, tức một khoảng rỗng. Không cần ngoại lệ riêng. Ví dụ `"xyz"` không xuất hiện trong `banana` thì `count("xyz")=0` và `occurrences("xyz")=[]`.

## 15. Kiểm thử truy vấn và trường hợp biên

Đặt các đoạn này sau khi đã khai báo `build_suffix_array`, `build_lcp` và `SuffixArrayIndex`.

### 15.1. Văn bản `banana`

```python
index = SuffixArrayIndex("banana")

assert index.sa == [5, 3, 1, 0, 4, 2]
assert index.lcp == [0, 1, 3, 0, 0, 2]

assert index.contains("ana")
assert index.contains("ban")
assert index.contains("banana")
assert not index.contains("bananas")
assert not index.contains("xyz")

assert index.occurrences("ana") == [1, 3]
assert index.occurrences("an") == [1, 3]
assert index.occurrences("na") == [2, 4]
assert index.occurrences("a") == [1, 3, 5]
assert index.occurrences("ban") == [0]
assert index.occurrences("banana") == [0]
assert index.occurrences("xyz") == []

assert index.count("ana") == 2
assert index.count("na") == 2
assert index.count("a") == 3
assert index.count("banana") == 1
assert index.count("z") == 0
```

### 15.2. Mẫu rỗng

```python
assert index.contains("")
assert index.count("") == 7
assert index.occurrences("") == [0, 1, 2, 3, 4, 5, 6]
```

Chuỗi `banana` dài 6 code point, có 7 **ranh giới** để đặt một mẫu rỗng.

### 15.3. Các lần xuất hiện chồng lấn

```python
repeat = SuffixArrayIndex("aaaaa")

assert repeat.sa == [4, 3, 2, 1, 0]
assert repeat.lcp == [0, 1, 2, 3, 4]

assert repeat.occurrences("a") == [0, 1, 2, 3, 4]
assert repeat.occurrences("aa") == [0, 1, 2, 3]
assert repeat.occurrences("aaa") == [0, 1, 2]
assert repeat.occurrences("aaaa") == [0, 1]
assert repeat.occurrences("aaaaa") == [0]
assert repeat.occurrences("aaaaaa") == []
```

Mẫu `aa` xuất hiện tại 0, 1, 2 và 3 trong `aaaaa`; các đoạn được **phép chồng lấn**.

### 15.4. Chuỗi rỗng và một ký hiệu

```python
empty = SuffixArrayIndex("")

assert empty.sa == []
assert empty.lcp == []
assert empty.contains("")
assert empty.count("") == 1
assert empty.occurrences("") == [0]
assert not empty.contains("a")
assert empty.occurrences("a") == []

one = SuffixArrayIndex("x")
assert one.sa == [0]
assert one.lcp == [0]
assert one.occurrences("x") == [0]
assert one.occurrences("xx") == []
```

Những trường hợp này giúp phát hiện lỗi vòng lặp dùng `log n` hoặc truy cập `sa[0]` khi `n=0`.

## 16. Đếm số chuỗi con phân biệt nhờ `SA` và `LCP`

Một ứng dụng rất đẹp của hai mảng là **đếm số chuỗi con liên tiếp khác nhau** của văn bản, không kể chuỗi rỗng.

### 16.1. Số tiền tố của mỗi hậu tố

Hậu tố bắt đầu ở vị trí `SA[r]` có độ dài:

\[
n-SA[r].
\]

Mỗi tiền tố không rỗng của hậu tố đó là một chuỗi con của văn bản. Nếu xét riêng hậu tố này, có `n-SA[r]` ứng viên.

Nhưng khi đi theo thứ tự từ điển của `SA`, một số tiền tố của hậu tố hiện tại **đã xuất hiện** ở những hậu tố trước.

### 16.2. Vì sao chỉ trừ LCP với hậu tố liền trước?

Các hậu tố được sắp theo thứ tự từ điển. Những hậu tố có chung một tiền tố `p` nằm **liền nhau trong một khoảng**.

Nếu một tiền tố của hậu tố thứ `r` đã xuất hiện trong một hậu tố đứng trước, thì tồn tại một hậu tố **ngay trước** ở thứ hạng `r-1` có chung tiền tố ít nhất dài như vậy. Nói cách khác, **LCP lớn nhất của hậu tố hiện tại với bất kỳ hậu tố trước nó** đạt được ở hậu tố kề trước.

Vì thế `LCP[r]` chính là số tiền tố ngắn nhất đã được tính; chỉ các tiền tố dài hơn mới bổ sung chuỗi con phân biệt mới.

Số chuỗi con mới ở thứ hạng `r`:

\[
(n-SA[r])-LCP[r].
\]

### 16.3. Công thức tổng quát

\[
D=
\sum_{r=0}^{n-1}
\left((n-SA[r])-LCP[r]\right).
\]

Vì `SA` là hoán vị của `0,\ldots,n-1`, tổng độ dài các hậu tố bằng `n(n+1)/2`:

\[
\boxed{
D=\frac{n(n+1)}2-\sum_{r=0}^{n-1}LCP[r].
}
\]

Đây là số **chuỗi con liên tiếp khác nhau và không rỗng**.

### 16.4. Ví dụ `banana`

`n=6`, tổng độ dài hậu tố là:

\[
\frac{6\cdot7}{2}=21.
\]

Tổng `LCP`:

\[
0+1+3+0+0+2=6.
\]

Vậy:

\[
D=21-6=15.
\]

Có thể kiểm tra theo độ dài:

| Độ dài | Các chuỗi con phân biệt | Số lượng |
| ---: | --- | ---: |
| 1 | `b, a, n` | 3 |
| 2 | `ba, an, na` | 3 |
| 3 | `ban, ana, nan` | 3 |
| 4 | `bana, anan, nana` | 3 |
| 5 | `banan, anana` | 2 |
| 6 | `banana` | 1 |
| **Tổng** |  | **15** |

### 16.5. Hàm Python

Bổ sung vào lớp `SuffixArrayIndex`:

```python
    def count_distinct_substrings(self):
        """Không đếm chuỗi rỗng."""
        n = len(self.text)
        return n * (n + 1) // 2 - sum(self.lcp)
```

Kiểm tra:

```python
assert index.count_distinct_substrings() == 15
assert SuffixArrayIndex("aaaaa").count_distinct_substrings() == 5
assert SuffixArrayIndex("").count_distinct_substrings() == 0
```

`aaaaa` chỉ có năm chuỗi con phân biệt không rỗng: `a,aa,aaa,aaaa,aaaaa`.

## 17. Tìm chuỗi con lặp dài nhất từ `max(LCP)`

Một chuỗi con `p` được gọi là **lặp** nếu nó xuất hiện ít nhất hai lần ở hai vị trí bắt đầu khác nhau; các lần xuất hiện **có thể chồng lấn**.

Nếu hai hậu tố cùng bắt đầu bằng `p`, chúng có LCP ít nhất bằng `|p|`. Vì vậy độ dài chuỗi con lặp dài nhất chính là:

\[
\max_{0\le r<n}LCP[r].
\]

### 17.1. Vì sao chỉ xét hậu tố kề nhau?

Nếu có hai hậu tố bất kỳ có tiền tố chung dài `k`, mọi hậu tố nằm giữa chúng trong thứ tự từ điển cũng phải bắt đầu bằng tiền tố dài `k`. Do đó ít nhất một cặp hậu tố **kề nhau** có LCP dài `k`. Vậy giá trị lớn nhất của `LCP` mảng đủ để tìm chuỗi con lặp dài nhất.

### 17.2. Ví dụ `banana`

`LCP=[0,1,3,0,0,2]` nên giá trị lớn nhất là 3. Hai hậu tố liên quan:

```text
ana     (vị trí 3)
anana   (vị trí 1)
^^^
```

Chuỗi con lặp dài nhất là `ana`, xuất hiện tại 1 và 3.

### 17.3. Hàm Python

Bổ sung vào `SuffixArrayIndex`:

```python
    def longest_repeated_substring(self):
        """Trả một chuỗi con lặp dài nhất, hoặc ''."""
        if not self.lcp:
            return ""

        best_len = max(self.lcp)
        if best_len == 0:
            return ""

        # Chọn lần xuất hiện đầu trong SA nếu hòa độ dài.
        r = self.lcp.index(best_len)
        start = self.sa[r]
        return self.text[start:start + best_len]
```

Kiểm tra:

```python
assert index.longest_repeated_substring() == "ana"
assert SuffixArrayIndex("aaaaa").longest_repeated_substring() == "aaaa"
assert SuffixArrayIndex("abcd").longest_repeated_substring() == ""
```

Nếu có nhiều chuỗi con lặp dài nhất khác nhau, hàm trả **một** kết quả; trong mã này, đó là kết quả ứng với **vị trí đầu tiên trong mảng LCP đạt cực đại**. Không khẳng định đây là chuỗi con lặp có hai vị trí cách xa nhau nhất hay thỏa thêm ràng buộc không chồng lấn.

### 17.4. Không chồng lấn là bài toán khác

Trong `aaaaa`, chuỗi `aaaa` xuất hiện ở 0 và 1 nhưng hai lần này **chồng lấn**. Nếu yêu cầu hai lần xuất hiện không giao nhau, không thể chỉ trả `max(LCP)`; phải kiểm tra khoảng cách hai vị trí xuất hiện và có thể dùng thêm cấu trúc dữ liệu để tối ưu.

## 18. LCP của hai hậu tố bất kỳ bằng RMQ trên `LCP`

Mảng `LCP` trực tiếp chỉ chứa độ dài chung của **các cặp kề nhau** theo `SA`. Nhưng nó cũng giúp tính LCP giữa **hai hậu tố bất kỳ**.

Gọi `a=rank[i]` và `b=rank[j]`, giả sử `a<b`. Khi đó:

\[
lcp(s[i:],s[j:])
=\min_{a<r\le b}LCP[r].
\]

Đây chính là một truy vấn **giá trị nhỏ nhất trên đoạn** (*Range Minimum Query — RMQ*).

### 18.1. Ví dụ `banana`

Hai hậu tố bắt đầu ở 1 và 3:

```text
s[1:] = anana
s[3:] = ana
```

Chúng có LCP dài 3. Theo rank:

```text
rank[1] = 2
rank[3] = 1
```

Nên:

\[
lcp(s[1:],s[3:])=\min(LCP[2])=3.
\]

Hai hậu tố `s[2:]="nana"` và `s[4:]="na"` có rank 5 và 4, nên LCP bằng `LCP[5]=2`.

### 18.2. Ví dụ có nhiều thứ hạng nằm giữa

Nếu `rank[i]=a` và `rank[j]=b` cách xa nhau, mọi cặp kề nhau trong đoạn `[a+1,b]` phải giữ tiền tố chung để hai đầu đoạn cùng giữ được nó.

Chỉ cần **một chỗ LCP nhỏ** giữa đoạn là hai hậu tố ở hai đầu không thể chung tiền tố dài hơn mức đó. Đó là trực giác của phép lấy **min** trên `LCP`.

### 18.3. Khi i=j

Nếu so một hậu tố với chính nó:

\[
lcp(s[i:],s[i:])=n-i.
\]

Không cần gọi RMQ trên đoạn rỗng.

### 18.4. RMQ trực tiếp và RMQ tiền xử lý

Nếu dùng:

```python
minimum = min(lcp[a + 1:b + 1])
```

thời gian một truy vấn có thể O(b−a). Khi có rất nhiều truy vấn, ta có thể xây **sparse table**:

- Tiền xử lý O(n log n) thời gian.
- Bộ nhớ O(n log n) ô.
- Truy vấn RMQ O(1) phép so số nguyên.

Có những kỹ thuật RMQ với O(n) bộ nhớ và O(1) truy vấn trong các mô hình phù hợp, nhưng sparse table dễ học và dễ kiểm tra hơn.

## 19. Cài đặt RMQ bằng sparse table

### 19.1. Cấu trúc bảng

Mỗi ô `table[k][i]` lưu min trên khoảng độ dài `2^k` bắt đầu ở `i`:

\[
table[k][i]=
\min(LCP[i],\ldots,LCP[i+2^k-1]).
\]

Với `k≥1`:

\[
table[k][i]=
\min(table[k-1][i],table[k-1][i+2^{k-1}]).
\]

Một truy vấn `[left,right)` có chiều dài `length` chọn `k=\lfloor\log_2 length\rfloor`, rồi lấy min của **hai khoảng độ dài `2^k`** phủ hết đoạn; chúng có thể chồng lên nhau, nhưng lấy min vẫn đúng.

### 19.2. Mã Python

```python
class LCPSparseRMQ:
    def __init__(self, lcp):
        n = len(lcp)

        self.logs = [0] * (n + 1)
        for i in range(2, n + 1):
            self.logs[i] = self.logs[i // 2] + 1

        self.table = []

        if n == 0:
            return

        self.table.append(list(lcp))
        k = 1

        while (1 << k) <= n:
            prev = self.table[k - 1]
            half = 1 << (k - 1)
            width = 1 << k

            row = [
                min(prev[i], prev[i + half])
                for i in range(n - width + 1)
            ]

            self.table.append(row)
            k += 1

    def range_min(self, left, right):
        """Min trên lcp[left:right], đoạn không rỗng."""
        n = len(self.logs) - 1

        if not (0 <= left < right <= n):
            raise ValueError("RMQ cần 0 <= left < right <= n")

        length = right - left
        k = self.logs[length]
        block = 1 << k

        return min(
            self.table[k][left],
            self.table[k][right - block],
        )

    def suffix_lcp(self, text, sa, rank, i, j):
        """LCP của text[i:] và text[j:]."""
        n = len(text)

        if not (0 <= i < n and 0 <= j < n):
            raise IndexError("vị trí hậu tố ngoài miền")

        if i == j:
            return n - i

        a = rank[i]
        b = rank[j]

        if a > b:
            a, b = b, a

        return self.range_min(a + 1, b + 1)
```

### 19.3. Kiểm tra

```python
s = "banana"
sa = build_suffix_array(s)
lcp, rank = build_lcp(s, sa)
rmq = LCPSparseRMQ(lcp)

assert rmq.suffix_lcp(s, sa, rank, 1, 3) == 3
assert rmq.suffix_lcp(s, sa, rank, 2, 4) == 2
assert rmq.suffix_lcp(s, sa, rank, 0, 2) == 0
assert rmq.suffix_lcp(s, sa, rank, 1, 1) == 5
```

Ở `suffix_lcp(s,sa,rank,1,1)`, hậu tố bắt đầu tại 1 là `anana` dài 5. Hàm trả đúng 5 thay vì thử truy vấn RMQ trên đoạn rỗng.

### 19.4. Cân nhắc bộ nhớ

Nếu chỉ cần `count`, `occurrences` và `longest_repeated_substring`, không nhất thiết phải xây sparse table. Nó hữu ích khi có **nhiều truy vấn LCP giữa hai vị trí** hoặc một thuật toán cao hơn cần RMQ thường xuyên.

Đừng thêm bảng O(n log n) ô chỉ vì “LCP có thể dùng RMQ”; hãy xác định workload.

## 20. Phân tích độ phức tạp và giả định

Giả sử `n` ký hiệu trong văn bản, mẫu dài `m`, có `occ` vị trí khớp. Các công thức dưới dùng mô hình truy cập một ký hiệu, so sánh hai ký hiệu và so sánh các chỉ số vừa từ máy trong O(1).

| Thao tác | Thời gian | Bộ nhớ phụ |
| --- | --- | --- |
| Xây `SA` bằng `sort` prefix doubling trong bài | O(n log²(n+1)) | O(n) từ máy |
| Xây `LCP` bằng Kasai khi đã có `SA` | O(n) | O(n) |
| Tìm khoảng hậu tố khớp mẫu | O(m log(n+1)) | O(1) vùng biến cục bộ |
| Kiểm tra mẫu có xuất hiện | O(m log(n+1)) | O(1) |
| Đếm số lần xuất hiện từ khoảng | O(m log(n+1)) | O(1) |
| Liệt kê vị trí theo thứ tự SA | O(m log(n+1)+occ) | O(occ) cho danh sách |
| Liệt kê vị trí tăng theo văn bản | O(m log(n+1)+occ log(occ+1)) | O(occ) |
| Đếm chuỗi con phân biệt khi đã có LCP | O(n) | O(1) ngoài các mảng |
| Tìm một chuỗi con lặp dài nhất khi đã có LCP | O(n) | O(1) biến phụ, cộng chuỗi kết quả |
| Xây sparse table RMQ trên LCP | O(n log(n+1)) | O(n log(n+1)) |
| RMQ LCP hai hậu tố khi đã có sparse table | O(1) | O(1) |

### 20.1. Trường hợp m=0

Biểu thức `O(m log(n+1))` thường dùng cho mẫu không rỗng. Với mẫu rỗng:

- `contains("")` và `count("")` hoàn thành O(1).
- `occurrences("")` tạo `n+1` vị trí nên tốn Θ(n+1) thời gian và bộ nhớ kết quả.

Muốn một công thức bao quát cả việc khởi tạo và kiểm tra biến, có thể viết `O((m+1)log(n+1))` cho việc tìm khoảng trên `SA` với `n≥1`, nhưng vẫn phải xử lý **đầu ra** riêng.

### 20.2. So sánh chuỗi không phải O(1) trong mọi mô hình

Mã `_compare_at` có thể phải đọc tới `m` ký hiệu trên mỗi lần tìm nhị phân. Vì vậy độ phức tạp là **O(m log n)**, không chỉ O(log n).

Có các kỹ thuật kết hợp LCP/RMQ với tìm kiếm nhị phân để tránh so lại các tiền tố dài, đạt những chặn tốt hơn trong các giả định phù hợp. Tuy nhiên, **chỉ xây sẵn `LCP` không tự làm hàm `_match_range` ở mục 14 trở thành O(m+log n)**; muốn hưởng lợi phải thay đổi thuật toán so sánh.

### 20.3. Dùng mô hình nào với Python?

Python `str` chứa Unicode và `int` có thể lớn. Thời gian thật chịu ảnh hưởng của:

- Cấp phát danh sách và tuple khóa sort.
- Quản lý đối tượng và bộ nhớ của Timsort.
- Mức trùng lặp và độ dài các mẫu.
- Truy cập cache, số lượng truy vấn và số kết quả.
- Độ rộng chỉ số và cách mã hóa ký tự.

Độ phức tạp mô tả **xu hướng tăng**, không phải số mili giây cho một cấu hình máy cụ thể.

## 21. Unicode, chuẩn hóa và đơn vị vị trí

Mã ở trên dùng `str` Python, nên ký hiệu được so sánh và các chỉ số `SA`/`occurrences` tính theo **Unicode code point**.

### 21.1. Byte UTF-8 và code point không cùng vị trí

```python
text = "bàn"

print(len(text))                 # Số code point.
print(len(text.encode("utf-8"))) # Số byte UTF-8.
```

Nếu yêu cầu trả **offset byte** để làm việc với một tệp UTF-8, không thể dùng thẳng các chỉ số code point do `SuffixArrayIndex` trả.

Có thể xây chỉ mục trực tiếp trên `bytes` với thuật toán thích hợp, hoặc giữ **bảng ánh xạ code point → byte offset**.

### 21.2. Chuẩn hóa tổ hợp dấu

```python
import unicodedata

a = "bàn"
b = "ba\u0300n"

assert a != b
assert unicodedata.normalize("NFC", a) == (
    unicodedata.normalize("NFC", b)
)
```

Nếu sản phẩm muốn coi hai biểu diễn là cùng từ, phải chuẩn hóa:

1. **Toàn bộ văn bản** trước khi xây `SA`.
2. **Mọi mẫu** theo cùng quy tắc trước khi tìm.

Nếu chuẩn hóa chỉ một phía, các mẫu hiển thị giống nhau có thể không khớp.

### 21.3. Chuẩn hóa có thể đổi vị trí

Khi đổi từ dạng tách dấu sang dạng dựng sẵn, số code point có thể thay đổi. Vị trí xuất hiện trong văn bản đã chuẩn hóa không mặc nhiên là vị trí trong văn bản nguồn.

Muốn tô sáng văn bản gốc, cần lưu **ánh xạ offset** hoặc một quy tắc truy hồi vị trí tương ứng.

### 21.4. Sắp theo code point không giống collation ngôn ngữ

`build_suffix_array` dùng `ord` và phép so sánh `str` theo code point Unicode. Đây là **thứ tự từ điển theo code point**, không phải thứ tự từ điển tiếng Việt theo locale/collation.

Nếu muốn xếp chuỗi theo quy tắc ngôn ngữ tự nhiên, cần thiết kế lại quan hệ so sánh và đặc tả rõ ảnh hưởng đến tìm tiền tố. Không thể đổi một comparator sau khi xây mà kỳ vọng `SA` cũ vẫn được sắp đúng.

## 22. Đối chiếu với mô hình tham chiếu và kiểm thử bất biến

Với thuật toán chỉ mục, kiểm tra kết quả trên vài mẫu chưa đủ. Nên kiểm tra độc lập cả **hoán vị `SA`**, **thứ tự hậu tố**, **`rank` nghịch đảo**, **`LCP`**, rồi mới thử tìm mẫu.

### 22.1. Đối chiếu `SA` với cách sắp hậu tố đơn giản

```python
def validate_sa_and_lcp(text):
    sa = build_suffix_array(text)
    lcp, rank = build_lcp(text, sa)
    n = len(text)

    assert sorted(sa) == list(range(n))
    assert sa == sorted(
        range(n),
        key=lambda i: text[i:]
    )

    assert len(lcp) == n
    assert len(rank) == n

    for r, start in enumerate(sa):
        assert rank[start] == r

        if r == 0:
            assert lcp[r] == 0
        else:
            expected = lcp_length(
                text, sa[r - 1], sa[r]
            )
            assert lcp[r] == expected


for s in [
    "", "a", "banana", "aaaaaa",
    "abababa", "mississippi", "aababa",
    "bàn", "🍎a🍎", "xyz",
]:
    validate_sa_and_lcp(s)
```

Ở đây `text[i:]` và `lcp_length` cố ý phục vụ **kiểm thử trên dữ liệu nhỏ**. Đừng dùng bộ kiểm tra này làm thành phần phục vụ truy vấn trong hệ thống lớn.

### 22.2. Đối chiếu số lần xuất hiện bằng quét chuỗi

```python
def naive_occurrences(text, pattern):
    if pattern == "":
        return list(range(len(text) + 1))

    m = len(pattern)
    return [
        i
        for i in range(len(text) - m + 1)
        if text[i:i + m] == pattern
    ]


for s in ["", "banana", "aaaa", "abababa", "mississippi"]:
    index = SuffixArrayIndex(s)

    patterns = [
        "", "a", "aa", "an", "ana", "na",
        "aba", "issi", "miss", "xyz", s,
    ]

    for p in patterns:
        expected = naive_occurrences(s, p)

        assert index.occurrences(p) == expected
        assert index.count(p) == len(expected)
        assert index.contains(p) == bool(expected)
```

Cách quét `naive_occurrences` có thể tốn O(nm) thời gian trong trường hợp xấu do cắt và so chuỗi, nhưng làm **oracle kiểm thử** độc lập phù hợp.

### 22.3. Kiểm tra đếm chuỗi con phân biệt

```python
def naive_distinct_substrings(text):
    n = len(text)
    return len({
        text[i:j]
        for i in range(n)
        for j in range(i + 1, n + 1)
    })


for s in ["", "a", "aaaa", "banana", "abab", "abc"]:
    index = SuffixArrayIndex(s)

    assert (
        index.count_distinct_substrings()
        == naive_distinct_substrings(s)
    )
```

Cách dùng `set` ở trên có thể chiếm rất nhiều bộ nhớ trên văn bản dài; đây chỉ là **bài kiểm thử tính đúng**.

### 22.4. Thứ tự các bước thử nghiệm

Trước tiên kiểm thử `SA`, sau đó mới `LCP`. Nếu `SA` sai, Kasai có thể tạo mảng nhìn có vẻ hợp lý nhưng thật ra không còn là LCP của các hậu tố kề nhau đúng thứ tự.

Sau đó thử khoảng binary search bằng nhiều mẫu không có kết quả, mẫu là hậu tố, mẫu dài hơn văn bản và mẫu chỉ xuất hiện ở vị trí cuối.

## 23. Những sai lầm thường gặp

| Phát biểu hoặc cách làm sai | Vấn đề | Cách sửa |
| --- | --- | --- |
| “`SA` là danh sách tất cả chuỗi hậu tố.” | Lưu chuỗi có thể tốn Θ(n²) ký hiệu. | Lưu **chỉ số bắt đầu** trong văn bản duy nhất. |
| “`SA[r]` là thứ hạng của vị trí `r`.” | Nhầm `SA` với `rank`. | `SA[r]` là vị trí; `rank[i]` là thứ hạng. |
| “Hậu tố ngắn và dài có cùng tiền tố thì bằng nhau.” | Sai thứ tự từ điển. | Hậu tố kết thúc sớm đứng trước. |
| “Mọi `SA` phải có `n+1` phần tử.” | Có nhiều quy ước sentinel/hậu tố rỗng. | Nêu rõ bài dùng `n` hậu tố không rỗng. |
| “Chỉ cần sort `text[i:]` để có bộ nhớ O(n).” | Cắt chuỗi tạo bản sao hậu tố lớn. | Dùng chỉ số và hạng tiền tố. |
| “Prefix doubling dùng `sort` là O(n log n).” | Mỗi vòng sort O(n log n), có O(log n) vòng. | Phân tích O(n log² n) cho bản mã. |
| “Kasai duyệt theo thứ tự `SA`.” | Mất bất biến tái sử dụng `h`. | Duyệt vị trí văn bản `i=0..n-1`. |
| “`LCP[r]` so hậu tố `s[r-1:]` và `s[r:]`.” | LCP định nghĩa theo **thứ hạng**. | Dùng `SA[r-1]` và `SA[r]`. |
| “Không cần ghi quy ước `LCP[0]`.” | Dễ lệch một ô khi dùng công thức. | Bài dùng `LCP[0]=0` và `LCP[r]` với hậu tố trước. |
| “Tìm mẫu trong SA chỉ cần một binary search.” | Cần biết **cả hai biên** của các hậu tố khớp. | Tìm lower/upper bound. |
| “So sánh hậu tố với mẫu là O(1).” | Có thể cần đọc tới `m` ký hiệu. | Chặn O(m log n) cho binary search cơ bản. |
| “`SA[left:right]` đã theo vị trí xuất hiện tăng.” | Thực ra là thứ tự từ điển hậu tố. | `sorted` nếu API cần chỉ số tăng. |
| “Mẫu rỗng có n vị trí vì SA dài n.” | Chuỗi rỗng có `n+1` ranh giới theo hợp đồng. | Xử lý riêng. |
| “Chỉ số byte và code point như nhau.” | UTF-8 có ký hiệu nhiều byte. | Ghi rõ đơn vị và ánh xạ offset. |
| “LCP lớn nhất cho lặp không chồng lấn.” | Hai đoạn lặp có thể giao nhau. | Bổ sung ràng buộc khoảng cách vị trí. |
| “Có LCP thì LCP của hai hậu tố bất kỳ O(1) ngay.” | Cần RMQ hoặc duyệt đoạn LCP. | Tiền xử lý RMQ nếu có nhiều truy vấn. |
| “Cây hậu tố và mảng hậu tố có cùng chi phí byte.” | Cây giữ nhiều nút/con trỏ; mảng giữ chỉ số. | So bộ nhớ thực tế và workload. |
| “SA tuyến tính chỉ nhờ không sao chép hậu tố.” | Thời gian xây còn phụ thuộc thuật toán sắp. | Phân biệt giảm bộ nhớ với tăng tốc xây. |

## 24. Bài tập vận dụng có gợi ý giải

### Bài 1 — Liệt kê và sắp hậu tố

Cho `s="aba"`. Liệt kê tất cả hậu tố không rỗng và tính `SA`.

**Gợi ý:** Các hậu tố: vị trí 0 `aba`, 1 `ba`, 2 `a`. Thứ tự `a<aba<ba`, nên `SA=[2,0,1]`.

### Bài 2 — Tính LCP

Với `s="aba"` và `SA=[2,0,1]`, tính `LCP` theo quy ước bài học.

**Gợi ý:** `LCP[0]=0`, `lcp(a,aba)=1`, `lcp(aba,ba)=0`. Kết quả `[0,1,0]`.

### Bài 3 — Hoán vị và rank

Với `SA=[5,3,1,0,4,2]`, hãy tính `rank`.

**Gợi ý:** Đặt `rank[SA[r]]=r` cho `r=0..5`. Kết quả `[3,2,5,1,4,0]`.

### Bài 4 — Suffix array và sentinel

Với `banana` và `banana$` (trong đó `$` là ký hiệu nhỏ nhất), hai `SA` khác nhau thế nào?

**Gợi ý:** Bản không sentinel có 6 phần tử `[5,3,1,0,4,2]`; bản có hậu tố `"$"` có 7 phần tử `[6,5,3,1,0,4,2]`.

### Bài 5 — Tổng số ký hiệu hậu tố

Với văn bản dài 10 ký hiệu, nếu lưu riêng bản sao tất cả hậu tố không rỗng, tổng độ dài là bao nhiêu?

**Gợi ý:** `10+9+\cdots+1=55` ký hiệu. Tổng quát Θ(n²).

### Bài 6 — Ký hiệu canh gác trong doubling

Tại sao rank của đoạn đã hết văn bản nên là `-1`, không phải một số lớn hơn tất cả hạng thật?

**Gợi ý:** Hậu tố ngắn hơn là tiền tố của hậu tố dài hơn phải đứng **trước** hậu tố dài hơn.

### Bài 7 — Độ phức tạp xây

Prefix doubling có O(log n) vòng; mỗi vòng sort O(n log n) và tính rank O(n). Tổng thời gian là gì?

**Gợi ý:** O(n log² n). Nếu mỗi vòng dùng radix/counting sort tuyến tính trong mô hình phù hợp, có thể giảm xuống O(n log n).

### Bài 8 — Tại sao Kasai giảm h?

Tại sao sau khi tính LCP cho hậu tố bắt đầu `i`, Kasai thường giảm `h` đi 1 trước khi xét `i+1`?

**Gợi ý:** Bỏ một ký hiệu đầu của các hậu tố có tiền tố chung `h` thì phần chung còn ít nhất `h-1`; thuật toán tận dụng cận dưới này theo bất biến của nó.

### Bài 9 — LCP của chuỗi lặp

Với `s="aaaa"`, tính `SA` và `LCP`.

**Gợi ý:** `SA=[3,2,1,0]`, `LCP=[0,1,2,3]`.

### Bài 10 — Khoảng khớp mẫu

Trong `banana`, các hậu tố bắt đầu bằng `ana` nằm ở hạng nào của SA và các vị trí thực là gì?

**Gợi ý:** Hạng 1 và 2, nên khoảng `[left,right)=[1,3)`, `SA[1:3]=[3,1]`. Sau sắp vị trí thành `[1,3]`.

### Bài 11 — Mẫu rỗng

Văn bản dài 6 ký hiệu. Theo hợp đồng của bài, `occurrences("")` có bao nhiêu phần tử, dù SA chỉ có 6?

**Gợi ý:** 7 vị trí: `0,1,2,3,4,5,6`.

### Bài 12 — Đếm chuỗi con phân biệt

Với `s="banana"`, tính số chuỗi con liên tiếp phân biệt không rỗng từ `LCP`.

**Gợi ý:** Tổng độ dài hậu tố 21, tổng `LCP` bằng 6, nên `D=15`.

### Bài 13 — Đếm trong văn bản toàn ký hiệu a

`s="aaaaa"` có bao nhiêu chuỗi con phân biệt không rỗng? Hãy dùng cả cách liệt kê và công thức.

**Gợi ý:** Chỉ có `a,aa,aaa,aaaa,aaaaa`, tổng 5. Công thức `15-(0+1+2+3+4)=5`.

### Bài 14 — Chuỗi lặp dài nhất

Với `banana`, `max(LCP)=3`. Chuỗi con lặp dài nhất là gì và ở đâu?

**Gợi ý:** `ana`, vị trí 1 và 3. Hai lần xuất hiện được phép chồng lấn.

### Bài 15 — RMQ của hai hậu tố

Cho `rank[1]=2`, `rank[3]=1` và `LCP[2]=3` trong `banana`. LCP của `s[1:]` và `s[3:]` bằng bao nhiêu?

**Gợi ý:** Min của `LCP[2:3]`, tức 3.

### Bài 16 — Sparse table có đáng dùng không?

Một hệ chỉ cần tìm mẫu và đếm substring phân biệt một lần. Có nên tự động xây RMQ O(n log n) ô không?

**Gợi ý:** Không nhất thiết. Chỉ nên thêm sparse table khi có nhiều truy vấn LCP giữa các hậu tố tùy ý hoặc thuật toán khác cần RMQ thường xuyên.

### Bài 17 — Đơn vị vị trí Unicode

Nếu `SA` xây trên Python `str` có ký tự tiếng Việt, các chỉ số `SA` có phải offset byte UTF-8 không?

**Gợi ý:** Không; chúng là vị trí **code point**. Cần ánh xạ sang byte nếu hệ thống xử lý file UTF-8 hoặc giao diện khác dùng đơn vị khác.

### Bài 18 — Chọn giữa SA, suffix tree và quét trực tiếp

Một ứng dụng có văn bản dài bất biến và rất nhiều truy vấn substring. Ứng dụng khác có văn bản ngắn, chỉ vài truy vấn. Bạn sẽ cân nhắc phương án nào?

**Gợi ý:** Ứng dụng nhiều truy vấn có thể hưởng lợi từ SA hoặc suffix tree; SA dùng mảng chỉ số gọn nhưng binary search so mẫu mất O(m log n) trong bản cơ bản. Ứng dụng nhỏ/ít truy vấn có thể quét trực tiếp để tránh tiền xử lý. Cần đo RAM, thời gian dựng, số mẫu và số vị trí xuất.

## 25. Checklist thiết kế chỉ mục SA + LCP

```text
1. Hợp đồng văn bản:
   - Ký hiệu là byte, code point hay grapheme?
   - Có chuẩn hóa Unicode trước khi xây không?
   - Văn bản có thay đổi sau khi xây chỉ mục?
   - Có đưa hậu tố rỗng/sentinel vào SA không?

2. Mảng hậu tố:
   - SA có đúng n phần tử và là hoán vị 0..n-1?
   - s[SA[r]:] tăng theo từ điển?
   - rank[SA[r]] = r?
   - Khi hậu tố là tiền tố của hậu tố khác, chuỗi ngắn đứng trước?

3. Xây chỉ mục:
   - Prefix doubling dùng sort O(n log² n) hay radix sort O(n log n)?
   - Có tạo text[i:] hoặc lát cắt dài trong vòng sort không?
   - Bộ nhớ của SA, rank, new_rank được tính riêng?
   - Có cần thuật toán tuyến tính cho đầu vào rất lớn?

4. Mảng LCP:
   - Quy ước LCP[0] = 0?
   - LCP[r] so SA[r-1] với SA[r]?
   - Có dùng rank đảo để chạy Kasai O(n)?
   - Đã kiểm thử với ký hiệu lặp, prefix và text rỗng?

5. Truy vấn mẫu:
   - Comparator trả 0 khi pattern là tiền tố của suffix?
   - Lower bound tìm compare >= 0?
   - Upper bound tìm compare > 0?
   - SA[left:right] nằm theo thứ tự suffix, không theo vị trí?
   - Mẫu rỗng có n+1 vị trí theo hợp đồng?

6. Ứng dụng LCP:
   - Số substring phân biệt: n(n+1)/2 - sum(LCP)?
   - Chuỗi lặp dài nhất: max(LCP) có cho phép chồng lấn?
   - LCP hai suffix bất kỳ: RMQ giữa hai rank?
   - Có cần sparse table O(n log n) bộ nhớ không?

7. Kiểm chứng và vận hành:
   - Có so SA với bản sorted text[i:] trên mẫu nhỏ?
   - Có so LCP Kasai với phép đếm LCP trực tiếp?
   - Có so occurrences với quét chuỗi độc lập?
   - Byte offset và code point offset có được phân biệt?
   - Có đo thời gian xây, RAM giữ lại và độ trễ nhiều mẫu?
```

## 26. Tổng kết

**Mảng hậu tố `SA`** lưu các vị trí bắt đầu hậu tố theo thứ tự từ điển; nó không cần giữ các bản sao chuỗi hậu tố. **Mảng `LCP`** ghi độ dài tiền tố chung giữa những hậu tố đứng cạnh nhau trong `SA` theo một quy ước chỉ số nhất quán.

Từ hai mảng đó, ta có thể:

- **Tìm mẫu:** hai lần binary search xác định một khoảng liên tiếp các hậu tố bắt đầu bằng mẫu; trả các vị trí xuất hiện.
- **Đếm chuỗi con phân biệt:** lấy tổng độ dài hậu tố trừ tổng LCP, tức `n(n+1)/2−∑LCP`.
- **Tìm chuỗi con lặp dài nhất:** lấy giá trị LCP lớn nhất, nếu cho phép các lần xuất hiện chồng lấn.
- **Hỏi LCP của hai hậu tố bất kỳ:** tìm giá trị nhỏ nhất trên một đoạn của LCP, có thể tiền xử lý RMQ.

Điều cần giữ rõ là **mô hình chi phí**: prefix doubling dùng sort của bài có O(n log² n) thời gian, Kasai có O(n), tìm mẫu cơ bản bằng binary search có O(m log n), và việc xuất `occ` vị trí cần thêm công việc theo số kết quả. Không nên nhầm **O(n) ô nhớ của SA/LCP** với việc mọi cách xây, mọi truy vấn đều tuyến tính.

Một chỉ mục tốt không chỉ có thuật toán đúng mà còn cần bất biến `SA/rank/LCP` rõ ràng, quy ước hậu tố rỗng nhất quán, đơn vị offset Unicode chính xác và bộ kiểm thử đối chiếu độc lập. Đó là nền tảng để lựa chọn mảng hậu tố, cây hậu tố hoặc tìm kiếm trực tiếp theo quy mô dữ liệu và workload.
