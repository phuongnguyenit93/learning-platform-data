# Wavelet tree cho dãy ký hiệu và truy vấn tần suất

## 1. Động cơ: tìm tần suất ký hiệu trong một đoạn

Giả sử hệ thống lưu một chuỗi sự kiện, mỗi sự kiện thuộc một loại ký hiệu. Một truy vấn thường gặp là: **ký hiệu `c` xuất hiện bao nhiêu lần giữa hai vị trí `l` và `r - 1`?**

~~~text
Chỉ số:  0 1 2 3 4 5
S:       b a n a n a

frequency("a", [1, 5)) = 2   # a ở vị trí 1 và 3
frequency("n", [0, 6)) = 2   # n ở vị trí 2 và 4
~~~

Nếu quét từng phần tử, mỗi truy vấn có thể mất `O(r-l)`. Nếu xây một mảng tiền tố tần suất cho **từng** ký hiệu trong bảng chữ cái có `σ` ký hiệu, ta có thể trả lời trong `O(1)` nhưng tốn đến `O(nσ)` ô đếm.

**Wavelet tree** (cây wavelet) giải quyết bài toán bằng cách chia **miền giá trị** thành hai nửa, đồng thời ghi lại thứ tự các phần tử được đưa sang mỗi nửa. Nhờ vậy, cấu trúc hỗ trợ những thao tác quan trọng:

- `frequency(c, l, r)`: đếm số lần ký hiệu `c` xuất hiện trong `S[l:r]`.
- `rank(c, r)`: đếm số lần `c` xuất hiện trong tiền tố `S[0:r]`.
- `access(i)`: khôi phục ký hiệu ở vị trí `i`.
- `kth(l, r, k)`: tìm ký hiệu nhỏ thứ `k` (tính từ 1) trong đoạn.
- `count_less(c, l, r)`: đếm các ký hiệu có giá trị nhỏ hơn `c` trong đoạn.
- `range_count(a, b, l, r)`: đếm các ký hiệu `x` sao cho `a ≤ x < b` trong đoạn.

Với bảng chữ cái có `σ` giá trị phân biệt, các phép này có thể thực hiện trong `O(\log σ)` thời gian trên wavelet tree cân bằng được trang bị thao tác đếm tiền tố hiệu quả.

Trong chương **Biểu diễn gọn** của học phần cấu trúc dữ liệu, wavelet tree là ví dụ về sự đánh đổi giữa thời gian và bộ nhớ: ta tận dụng cấu trúc của dãy và miền ký hiệu để hỗ trợ nhiều truy vấn thay vì lưu riêng một bảng tần suất đầy đủ cho mỗi ký hiệu. Khi học cây, mảng và các cấu trúc truy vấn, cần nắm rõ **bất biến**, **cách ánh xạ chỉ số**, **độ phức tạp** và **cách hiện thực bitvector**.

## 2. Quy ước và các khái niệm nền tảng

Cho dãy `S[0], S[1], \ldots, S[n-1]` dài `n`. Gọi `Σ` là tập các ký hiệu phân biệt trong dãy, `σ=|Σ|`. Giả sử ký hiệu có thứ tự toàn phần để ta có thể so sánh giá trị; nếu không, cần quy định thứ tự trước.

Toàn bộ các khoảng vị trí dùng dạng **nửa mở** `[l,r)` với `0 ≤ l ≤ r ≤ n`. Ví dụ, `[1,5)` chứa các vị trí 1, 2, 3, 4 và dài `4`. Vị trí trong code bắt đầu từ **0**. Riêng tham số `k` của truy vấn `kth` bắt đầu từ **1**.

### Nén ký hiệu thành mã có thứ tự

Wavelet tree thường chia một **miền mã ký hiệu** thay vì chia dựa vào giá trị ký tự gốc. Với dãy ví dụ `S = "banana"`:

| Ký hiệu | Mã sau nén |
| --- | ---: |
| `a` | 0 |
| `b` | 1 |
| `n` | 2 |

Dãy mã là:

~~~text
S:    b a n a n a
Mã:  1 0 2 0 2 0
~~~

Ta nén theo thứ tự tăng dần: `a < b < n` tương đương `0 < 1 < 2`. Do đó phép đếm theo khoảng giá trị và tìm phần tử nhỏ thứ `k` vẫn giữ đúng kết quả sau nén.

### Rank trên bitvector

Ở mỗi nút, ta ghi một bit cho mỗi phần tử trong dãy con của nút:

- Bit `0`: phần tử đi sang **con trái**, nơi giữ nửa dưới của miền giá trị.
- Bit `1`: phần tử đi sang **con phải**, nơi giữ nửa trên.

Định nghĩa `rank_0(B, i)` là số bit `0` trong tiền tố `B[0:i]` và `rank_1(B, i)` là số bit `1` trong tiền tố ấy. Với `0 ≤ i ≤ |B|`:

\[
\operatorname{rank}_0(B,i)+\operatorname{rank}_1(B,i)=i.
\]

Để dạy và cài đặt đơn giản, ta có thể lưu mảng tiền tố `P[i]=rank_0(B,i)`. Khi đó `rank_1(B,i)=i-P[i]`. Một biểu diễn bitvector nén có thể hỗ trợ `rank` hiệu quả với ít bộ nhớ hơn nhiều so với mảng số nguyên tiền tố.

## 3. Cây được tạo như thế nào?

Mỗi nút quản lý một **khoảng giá trị** `[lo,hi]` trong miền mã ký hiệu, và một **dãy con** lấy từ dãy gốc sau những bước phân hoạch trước đó. Nếu `lo=hi` thì đây là lá, tất cả ký hiệu trong dãy con có cùng mã.

Nếu `lo < hi`, đặt:

\[
mid = \left\lfloor\frac{lo+hi}{2}\right\rfloor.
\]

Ta phân nhóm các phần tử theo mã:

- Mã `≤ mid` chuyển sang con trái `[lo,mid]`.
- Mã `> mid` chuyển sang con phải `[mid+1,hi]`.

**Giữ nguyên thứ tự tương đối** giữa các phần tử chuyển sang cùng một con (*stable partition*). Đây là yêu cầu thiết yếu: các vị trí trong một đoạn sau phân hoạch phải được ánh xạ đúng sang các đoạn liên tiếp tại từng con.

### Ví dụ từng tầng với `"banana"`

Miền mã ban đầu là `[0,2]`, mốc giữa là `1`. Ký hiệu `a,b` vào trái; `n` vào phải.

~~~text
                              S = b a n a n a
                            miền mã [0,2]
                          B = 0 0 1 0 1 0
                         /                 \
               trái: b a a a             phải: n n
                miền [0,1]               miền [2,2]
               B = 1 0 0 0                  lá n
               /         \
         trái: a a a    phải: b
          miền [0,0]    miền [1,1]
              lá a          lá b
~~~

Tại gốc, mảng số lượng phần tử sang trái của từng tiền tố là:

~~~text
Vị trí tiền tố i: 0 1 2 3 4 5 6
P_gốc[i]:       0 1 2 2 3 3 4
~~~

Tại nút trái `"baaa"`, mảng là:

~~~text
Vị trí tiền tố i: 0 1 2 3 4
P_trái[i]:      0 0 1 2 3
~~~

**Chú ý:** các nút lưu **dãy con đã phân hoạch**, không đơn thuần là lát cắt chỉ số liên tục của dãy ban đầu. Nhưng nhờ giữ thứ tự ổn định, mỗi đoạn truy vấn `[l,r)` tại một nút vẫn chuyển thành một đoạn liên tiếp trong con.

## 4. Bất biến quan trọng: ánh xạ đoạn từ cha xuống con

Giả sử ở một nút, ta đang quan tâm đến đoạn vị trí cục bộ `[l,r)` trong dãy con của nút. Gọi `P[i]` là số phần tử chuyển trái trong `i` phần tử đầu tiên.

**Đoạn tương ứng ở con trái** có chỉ số:

\[
\boxed{[P[l],\,P[r])}.
\]

**Đoạn tương ứng ở con phải** có chỉ số:

\[
\boxed{[l-P[l],\,r-P[r])}.
\]

Số ký hiệu đi sang trái trong đoạn cha là `P[r]-P[l]`; số ký hiệu đi sang phải là:

\[
(r-l)-(P[r]-P[l]).
\]

**Vì sao ánh xạ đúng?** Trong `l` phần tử đầu tiên của dãy con, có đúng `P[l]` phần tử vào trái và `l-P[l]` phần tử vào phải. Đến vị trí `r`, những số lượng này lần lượt là `P[r]` và `r-P[r]`. Phân hoạch ổn định nên các phần tử thuộc đoạn cha tiếp tục tạo thành một đoạn liên tiếp trong mỗi dãy con, với đúng các biên nêu trên.

### Truy vết một truy vấn

Xét `frequency("a", 1, 5)` trên `S="banana"`:

1. Ở gốc, truy vấn `[1,5)` có ký hiệu `a,n,a,n`. Vì mã `a=0≤1`, ta đi trái. Mảng `P_gốc` cho đoạn mới `[P[1],P[5])=[1,3)`.
2. Ở nút trái `"baaa"`, truy vấn cục bộ `[1,3)` tương ứng `"aa"`. Mã `a=0≤0` nên tiếp tục trái: `[P_trái[1],P_trái[3])=[0,2)`.
3. Đến lá `a`, độ dài đoạn là `2-0=2`. Vậy tần suất cần tìm là **2**.

Nhờ bất biến ánh xạ, mỗi tầng chỉ cần tra cứu vài giá trị tiền tố, không cần quét lại các phần tử trong đoạn.

## 5. Các truy vấn cốt lõi

### 5.1. Đếm tần suất ký hiệu và rank

Để tính `frequency(c,l,r)`, bắt đầu ở gốc với đoạn `[l,r)`, rồi dựa vào mã `c` để chọn nhánh trái hoặc phải. Ánh xạ đoạn theo công thức ở trên tại mỗi tầng. Nếu đến lá của `c`, kết quả bằng độ dài đoạn cục bộ. Nếu đoạn rỗng hoặc `c` không thuộc bảng chữ cái, kết quả bằng `0`.

\[
\operatorname{rank}(c,r)=\operatorname{frequency}(c,0,r),
\]

và:

\[
\operatorname{frequency}(c,l,r)=
\operatorname{rank}(c,r)-\operatorname{rank}(c,l).
\]

Với cây cân bằng và `rank_0` ở mỗi tầng có chi phí `O(1)`, ta đi qua `O(\log \sigma)` tầng nên thời gian truy vấn là `O(\log \sigma)`.

### 5.2. Truy cập ký hiệu tại một vị trí

Để tìm `access(i)`, tại mỗi nút xét bit `B[i]`:

- Nếu bit là 0, chuyển sang con trái với `i' = P[i]`.
- Nếu bit là 1, chuyển sang con phải với `i' = i-P[i]`.

Lặp lại đến lá. Giá trị mã tại lá chính là ký hiệu của vị trí `i` trong dãy ban đầu.

Với `"banana"`, `access(2)` đi từ bit `1` ở gốc sang con phải và trả về `"n"`.

### 5.3. Phần tử nhỏ thứ `k` trong đoạn

Truy vấn `kth(l,r,k)` yêu cầu `1≤k≤r-l`. Tại mỗi nút, tính:

\[
leftCount=P[r]-P[l].
\]

Nếu `k≤leftCount`, phần tử cần tìm nằm trong con trái và giữ nguyên `k`. Ngược lại, nó nằm trong con phải, có thứ hạng mới `k' = k-leftCount`. Sau đó ánh xạ `[l,r)` sang con được chọn.

Ví dụ, trong toàn bộ `"banana"`, dãy sau khi sắp thứ tự là `a,a,a,b,n,n`. Do đó:

~~~text
kth(0,6,1) = "a"
kth(0,6,4) = "b"
kth(0,6,6) = "n"
~~~

Wavelet tree không sắp xếp toàn bộ đoạn cho mỗi truy vấn; nó đếm số phần tử nằm trong nửa dưới của miền ký hiệu tại từng tầng để định vị thứ hạng.

### 5.4. Đếm ký hiệu nhỏ hơn ngưỡng

Để tính `count_less(c,l,r)`, ta xem miền giá trị mỗi nút so với ngưỡng `c`:

- Nếu toàn bộ miền của nút có giá trị `≥c`, đóng góp là 0.
- Nếu toàn bộ miền của nút có giá trị `<c`, đóng góp là `r-l`.
- Nếu miền cắt qua ngưỡng, ánh xạ đoạn sang hai con, rồi cộng kết quả từ các con.

Vì ở mỗi độ sâu có tối đa một nhánh cần đi tiếp qua ranh giới ngưỡng; các nhánh còn lại được nhận toàn bộ hoặc bỏ qua, thời gian là `O(\log \sigma)` với cây cân bằng.

Ví dụ:

~~~text
count_less("n", 0, 6) = 4  # a: 3 lần, b: 1 lần
count_less("b", 1, 5) = 2  # chỉ có a ở vị trí 1, 3
~~~

Từ đó, **đếm ký hiệu trong khoảng giá trị** `[a,b)` trên một đoạn vị trí được viết thành:

\[
\operatorname{rangeCount}(a,b,l,r)
=\operatorname{countLess}(b,l,r)
-\operatorname{countLess}(a,l,r).
\]

Ví dụ `range_count("a","n",0,6)=4` vì chỉ tính các ký hiệu `a` và `b`, không tính `n`.

## 6. Cài đặt Python tự chứa để quan sát cây

Phiên bản sau sử dụng **mảng tiền tố số nguyên tại mỗi nút** để làm rõ cơ chế `rank_0`. Nó hỗ trợ ký hiệu là các giá trị **so sánh được và hashable** như số nguyên hoặc chuỗi. Sắp xếp bảng chữ cái và ánh xạ ký hiệu sang mã theo thứ tự. Dãy được xem là **bất biến** sau khi xây cây.

Mảng Python trong ví dụ chủ ý dễ học, **chưa phải biểu diễn bitvector nén sát giới hạn bộ nhớ**. Phần tiếp theo phân tích sự khác biệt đó.

~~~python
from __future__ import annotations
from bisect import bisect_left


class _WaveletNode:
    __slots__ = ("lo", "hi", "prefix_left", "left", "right")

    def __init__(self, codes: list[int], lo: int, hi: int):
        self.lo = lo
        self.hi = hi
        self.left: _WaveletNode | None = None
        self.right: _WaveletNode | None = None

        # Tại lá, mọi phần tử đều có chung mã; không cần chia thêm.
        if lo == hi:
            self.prefix_left = None
            return

        mid = (lo + hi) // 2
        left_codes: list[int] = []
        right_codes: list[int] = []
        self.prefix_left = [0]

        # Phân hoạch ổn định và ghi rank_0 của từng tiền tố.
        for code in codes:
            if code <= mid:
                left_codes.append(code)
                self.prefix_left.append(self.prefix_left[-1] + 1)
            else:
                right_codes.append(code)
                self.prefix_left.append(self.prefix_left[-1])

        if left_codes:
            self.left = _WaveletNode(left_codes, lo, mid)
        if right_codes:
            self.right = _WaveletNode(right_codes, mid + 1, hi)


class WaveletTree:
    """Wavelet tree tĩnh; đoạn vị trí [left, right), k bắt đầu từ 1."""

    def __init__(self, symbols: list):
        self.n = len(symbols)
        self.alphabet = sorted(set(symbols))
        self._code = {
            value: index for index, value in enumerate(self.alphabet)
        }

        if self.n == 0:
            self.root: _WaveletNode | None = None
        else:
            codes = [self._code[symbol] for symbol in symbols]
            self.root = _WaveletNode(
                codes, 0, len(self.alphabet) - 1
            )

    def _check_range(self, left: int, right: int) -> None:
        if not (0 <= left <= right <= self.n):
            raise IndexError("Đoạn vị trí không hợp lệ")

    def frequency(self, symbol, left: int, right: int) -> int:
        """Đếm số lần symbol xuất hiện trong [left, right)."""
        self._check_range(left, right)
        if left == right or symbol not in self._code:
            return 0

        target = self._code[symbol]
        node = self.root

        while node is not None and node.lo < node.hi:
            mid = (node.lo + node.hi) // 2
            prefix = node.prefix_left
            left_before = prefix[left]
            left_until = prefix[right]

            if target <= mid:
                left, right = left_before, left_until
                node = node.left
            else:
                left -= left_before
                right -= left_until
                node = node.right

            if left == right:
                return 0

        return right - left if node is not None else 0

    def rank(self, symbol, right: int) -> int:
        """Số lần symbol xuất hiện trong tiền tố [0, right)."""
        return self.frequency(symbol, 0, right)

    def access(self, index: int):
        """Lấy ký hiệu tại vị trí index (0-based)."""
        if not (0 <= index < self.n):
            raise IndexError("Chỉ số không hợp lệ")

        node = self.root
        while node.lo < node.hi:
            prefix = node.prefix_left
            goes_left = prefix[index + 1] > prefix[index]

            if goes_left:
                index = prefix[index]
                node = node.left
            else:
                index -= prefix[index]
                node = node.right

        return self.alphabet[node.lo]

    def kth(self, left: int, right: int, k: int):
        """Ký hiệu nhỏ thứ k trong [left, right), k tính từ 1."""
        self._check_range(left, right)
        if not (1 <= k <= right - left):
            raise ValueError("k phải thuộc [1, right - left]")

        node = self.root
        while node.lo < node.hi:
            prefix = node.prefix_left
            left_before = prefix[left]
            left_until = prefix[right]
            left_count = left_until - left_before

            if k <= left_count:
                left, right = left_before, left_until
                node = node.left
            else:
                k -= left_count
                left -= left_before
                right -= left_until
                node = node.right

        return self.alphabet[node.lo]

    def count_less(self, symbol, left: int, right: int) -> int:
        """Đếm x < symbol trong đoạn vị trí [left, right)."""
        self._check_range(left, right)
        if left == right:
            return 0

        # Vị trí chèn cũng đúng với ngưỡng không có trong dãy.
        limit = bisect_left(self.alphabet, symbol)
        return self._count_less(self.root, left, right, limit)

    def _count_less(
        self,
        node: _WaveletNode | None,
        left: int,
        right: int,
        limit: int,
    ) -> int:
        if node is None or left == right or node.lo >= limit:
            return 0
        if node.hi < limit:
            return right - left

        prefix = node.prefix_left
        left_before = prefix[left]
        left_until = prefix[right]

        return (
            self._count_less(
                node.left, left_before, left_until, limit
            )
            + self._count_less(
                node.right,
                left - left_before,
                right - left_until,
                limit,
            )
        )

    def range_count(
        self, low, high, left: int, right: int
    ) -> int:
        """Đếm low <= x < high trong [left, right)."""
        self._check_range(left, right)
        if low > high:
            raise ValueError("Cận giá trị low phải <= high")
        return (
            self.count_less(high, left, right)
            - self.count_less(low, left, right)
        )
~~~

### Chạy thử các phép truy vấn

~~~python
tree = WaveletTree(list("banana"))

assert tree.frequency("a", 1, 5) == 2
assert tree.frequency("n", 0, 6) == 2
assert tree.frequency("z", 0, 6) == 0
assert tree.rank("a", 4) == 2

assert tree.access(0) == "b"
assert tree.access(2) == "n"
assert tree.kth(0, 6, 4) == "b"
assert tree.kth(1, 5, 2) == "a"

assert tree.count_less("n", 0, 6) == 4
assert tree.count_less("b", 1, 5) == 2
assert tree.range_count("a", "n", 0, 6) == 4

# Đoạn rỗng: truy vấn đếm cho kết quả 0.
assert tree.frequency("a", 2, 2) == 0
assert tree.range_count("a", "z", 0, 0) == 0

# Dãy rỗng vẫn có thể được khởi tạo:
empty = WaveletTree([])
assert empty.frequency("a", 0, 0) == 0
~~~

### Vì sao `kth` vẫn đúng khi có ký hiệu trùng nhau?

Giả sử đoạn hỏi gồm `[a,n,a,n]`. Số phần tử ở nửa giá trị thấp nhất bằng `2`. Nếu hỏi phần tử thứ `1` hoặc `2`, ta đi về phía `a`; nếu hỏi thứ `3` hoặc `4`, ta bỏ qua hai phần tử `a` bằng phép `k -= left_count` và tiếp tục đi phía `n`. Các ký hiệu trùng không cần được đánh số lại riêng rẽ vì ta chỉ quan tâm đến **thứ hạng của giá trị**, không cần vị trí gốc của phần tử được chọn.

## 7. Phân tích thời gian và bộ nhớ

Đặt `h=\lceil\log_2\sigma\rceil` với `σ≥2`. Với `σ=1`, cây chỉ gồm lá nên các truy vấn hợp lệ là `O(1)`. Các giá trị dưới đây tính theo giả thiết có thể đọc `rank_0(B,i)` của bitvector trong `O(1)` thời gian.

| Thao tác | Thời gian | Giải thích |
| --- | --- | --- |
| Nén bảng chữ cái | `O(n\log n)` tổng quát | Sắp xếp các ký hiệu khác nhau và ánh xạ sang mã; có thể nhanh hơn nếu miền giá trị đã chuẩn hóa. |
| Xây các tầng wavelet | `O(n\log\sigma)` | Mỗi phần tử tham gia tối đa một nút tại mỗi tầng. |
| `frequency`, `rank` | `O(\log\sigma)` | Chỉ đi theo nhánh của ký hiệu. |
| `access`, `kth` | `O(\log\sigma)` | Đi qua một đường từ gốc xuống lá. |
| `count_less` | `O(\log\sigma)` | Mỗi tầng chỉ có tối đa một nhánh giao ranh giới ngưỡng. |
| `range_count` | `O(\log\sigma)` | Hiệu của hai truy vấn `count_less`. |

Mỗi phần tử tại mỗi tầng góp một bit vào các bitvector của tầng đó. Vì vậy, phần dữ liệu phân hướng đi tiêu tốn khoảng:

\[
n\lceil\log_2\sigma\rceil\quad\text{bit}
\]

trong giới hạn trên đơn giản cho cây cân bằng; chưa tính chỉ mục hỗ trợ `rank`, thông tin điều hướng cây, ánh xạ bảng chữ cái và phần quản lý bộ nhớ.

**Điểm phân biệt quan trọng:** đoạn mã Python phía trên lưu `prefix_left` dưới dạng **mảng số nguyên** tại mỗi nút, nên chi phí khoảng `O(n\log\sigma)` **ô số nguyên**, cộng `O(\sigma)` nút và bảng mã. Một ô số nguyên Python tốn nhiều byte, vì thế đây là cách cài đặt phục vụ học tập, không phải cấu trúc thực sự *succinct* theo số bit.

Trong bản triển khai chuyên dụng, người ta lưu các bit của mỗi tầng/nút thành **bitvector đóng gói**, kết hợp cấu trúc hỗ trợ `rank` bằng bảng đếm theo khối hoặc kỹ thuật succinct. Khi đó có thể tiến gần `n\log_2\sigma` bit cho phần dãy, với phần phụ trợ `rank` và điều hướng tùy thiết kế. Không thể kết luận toàn bộ bộ nhớ đúng bằng `n\log_2\sigma` bit nếu chưa tính các phụ trợ đó.

Nếu cần một cấu trúc thực tế rất gọn cho tập ký hiệu lớn, **wavelet matrix** là biến thể bố trí các bitvector theo tầng, thường tránh nhiều con trỏ và phù hợp với thao tác `rank`. Khái niệm và bất biến về ánh xạ chỉ số vẫn liên quan chặt chẽ tới wavelet tree.

## 8. Chứng minh các truy vấn dựa vào bất biến

Ta chứng minh theo độ cao cây:

**Bất biến phân hoạch:** với mọi nút, dãy con của nút gồm đúng các phần tử từ cha có mã thuộc miền giá trị của nút; thứ tự tương đối giữa chúng được bảo toàn. Điều này đúng tại gốc. Khi phân hoạch sang trái/phải bằng cách duyệt các phần tử từ đầu đến cuối và thêm vào danh sách tương ứng, tính chất tiếp tục đúng tại hai con.

**Bất biến ánh xạ:** với đoạn `[l,r)` của nút, các phần tử đi trái được giữ trong `[P[l],P[r])` và các phần tử đi phải được giữ trong `[l-P[l],r-P[r])`. Điều này đúng vì `P[t]` đếm đúng số phần tử sang trái trong tiền tố dài `t`.

Từ hai bất biến trên:

1. **Frequency:** khi đi theo mã của ký hiệu `c`, ta không bỏ sót bất kỳ lần xuất hiện nào của `c`, cũng không giữ phần tử mang mã khác tại lá; số lần xuất hiện đúng bằng độ dài đoạn ở lá.
2. **Access:** bit tại chỉ số đang xét cho biết chính xác phần tử ở vị trí ấy được chuyển sang con nào; công thức ánh xạ điểm dẫn tới đúng phần tử tương ứng ở con. Đến lá thì biết giá trị ký hiệu.
3. **K-th:** mọi mã ở con trái không lớn hơn bất kỳ mã nào ở con phải. Nếu thứ hạng `k` không vượt số phần tử đi trái, kết quả nằm bên trái; ngược lại bỏ qua toàn bộ phần trái và giảm thứ hạng đi đúng số ấy. Quy nạp đến lá cho kết quả chính xác.
4. **Count-less:** miền giá trị mỗi nút là liên tục và có thứ tự. Với miền hoàn toàn dưới ngưỡng, ta đếm cả đoạn; với miền không dưới ngưỡng, ta bỏ qua; còn lại phân hoạch thành hai con với đoạn tương ứng chính xác. Hai tập con không giao nhau nên cộng số đếm không gây trùng lặp.

Như vậy tính đúng đắn không phụ thuộc vào việc phần tử ban đầu có lặp hay không, miễn phân hoạch ổn định và mảng `P` được xây đúng.

## 9. So sánh với các cấu trúc dữ liệu khác

| Cấu trúc | Điểm mạnh | Hạn chế/điều kiện |
| --- | --- | --- |
| Quét dãy trực tiếp | Không cần tiền xử lý; đơn giản | Đếm trên đoạn dài `m` mất `O(m)`. |
| Mảng tiền tố cho từng ký hiệu | `O(1)` cho tần suất của một ký hiệu trên đoạn | Cần `O(n\sigma)` ô nếu lưu bảng đầy đủ. |
| Bảng băm đếm tần suất toàn dãy | Đếm được mỗi ký hiệu trong toàn dãy | Không trực tiếp trả lời tần suất trên đoạn vị trí bất kỳ. |
| Cây đoạn lưu bảng đếm | Hỗ trợ một số kiểu cập nhật và truy vấn theo đoạn | Nếu lưu đủ `σ` số đếm ở từng nút, bộ nhớ lớn; dạng thưa tùy thiết kế có chi phí khác. |
| Wavelet tree tĩnh | Tần suất theo đoạn, rank, access, k-th, đếm theo khoảng giá trị; tiết kiệm hơn bảng `n\times\sigma` | Cần xây trước; cập nhật tùy ý không được hỗ trợ hiệu quả bởi cấu trúc tĩnh cơ bản. |

**Không nhầm wavelet tree với cây đoạn.** Cây đoạn chia **miền vị trí** rồi gộp kết quả lên cha; wavelet tree chia **miền giá trị**, đồng thời bảo tồn ánh xạ các đoạn vị trí qua bitvector. Vì thế wavelet tree phù hợp tự nhiên với câu hỏi “bao nhiêu giá trị bằng `c`, nhỏ hơn `c` hoặc thuộc `[a,b)` trong đoạn vị trí?”.

**Không nhầm với Huffman coding.** Cây wavelet cân bằng ở đây chia theo miền mã nên độ sâu khoảng `\log_2\sigma`. Biến thể *Huffman-shaped wavelet tree* dùng hình dạng theo tần suất có thể tiết kiệm không gian trên phân bố không đều, nhưng chiều sâu theo từng ký hiệu thay đổi và các phân tích phải nêu rõ giả thiết.

## 10. Những lỗi triển khai thường gặp

1. **Không giữ phân hoạch ổn định.** Nếu sắp xếp lại các phần tử bên trong một con theo giá trị, ánh xạ vị trí từ cha sang con có thể không còn đúng.
2. **Sai quy ước của `rank`.** Ở đây `P[i]` đếm số bit 0 trong tiền tố **`[0,i)`**, không tính vị trí `i`. Vì thế `P` phải có `length+1` phần tử.
3. **Đảo công thức ánh xạ con phải.** Khoảng đúng là `[l-P[l], r-P[r])`, không phải `[P[l],P[r])`.
4. **Quên nén miền ký hiệu.** Nếu giá trị là `10^9` nhưng chỉ có vài ký hiệu phân biệt, phân chia trên toàn miền số nguyên không cần thiết; nén theo thứ tự giúp chiều cao phụ thuộc `σ`.
5. **Nhầm thứ hạng `k` với chỉ số mảng.** Ví dụ này chọn `k=1` là phần tử nhỏ nhất, trong khi `access(0)` là phần tử đầu tiên theo vị trí.
6. **Không kiểm tra ký hiệu vắng mặt.** Với `frequency`, nếu ký hiệu không xuất hiện trong dãy thì phải trả 0. Với `count_less`, ngưỡng không nhất thiết xuất hiện: cần tìm vị trí chèn theo thứ tự.
7. **Hỏi phần tử nhỏ thứ `k` trên đoạn rỗng.** `kth` chỉ hợp lệ khi `1≤k≤r-l`; đoạn rỗng không có phần tử để chọn.
8. **Đánh đồng mảng tiền tố Python với bitvector nén.** Cùng là thuật toán wavelet tree nhưng số byte thực tế có thể khác nhau đáng kể.
9. **Tưởng cây tĩnh tự cập nhật khi dãy thay đổi.** Sửa một ký hiệu có thể thay đổi các bit phân hoạch và ánh xạ ở nhiều tầng; cần xây lại hoặc sử dụng biến thể wavelet động có cấu trúc `rank/select` hỗ trợ cập nhật.
10. **Bỏ qua thứ tự ký hiệu.** Các truy vấn `kth` và `count_less` phải dùng thứ tự nhất quán. Với chuỗi tiếng Việt có dấu, thứ tự so sánh chuỗi mặc định của Python theo mã Unicode có thể không trùng thứ tự từ điển mong muốn; khi cần, hãy định nghĩa phép ánh xạ theo thứ tự nghiệp vụ trước khi xây cây.

## 11. Bài tập thực hành

**Bài 1 — Xây cây bằng tay.** Cho `S=[2,0,3,1,2,0,1]`, miền ký hiệu `[0,3]`. Viết bitvector tại gốc theo quy ước `0` đi trái, rồi tạo hai dãy con. Tính mảng `P` tại gốc.

*Đáp án đối chiếu:* mốc giữa `mid=1`. Bitvector là `1 0 1 0 1 0 0`, dãy con trái là `[0,1,0,1]`, phải là `[2,3,2]`; `P=[0,0,1,1,2,2,3,4]`.

**Bài 2 — Ánh xạ đoạn.** Trên dãy bài 1, ánh xạ đoạn gốc `[1,6)` sang cả hai con. Sau đó tính `frequency(0,1,6)` bằng cách đi theo đường đến lá.

*Đáp án đối chiếu:* đoạn trái `[0,3)`; đoạn phải `[1,3)`; kết quả tần suất của 0 bằng `2`.

**Bài 3 — Chọn phần tử thứ k.** Với dãy `S=[5,1,5,2,1,4,2]`, hãy tìm `kth(1,7,4)` và giải thích các quyết định đi trái/phải.

*Đáp án đối chiếu:* đoạn là `[1,5,2,1,4,2]`; sau sắp xếp thành `[1,1,2,2,4,5]`, phần tử thứ 4 là `2`.

**Bài 4 — Đếm theo khoảng giá trị.** Với dãy bài 3, hỏi có bao nhiêu giá trị `x` trong `S[0:7]` thỏa `2≤x<5`. Viết phép trừ hai `count_less`.

*Đáp án đối chiếu:* `x=2` có 2 lần, `x=4` có 1 lần, kết quả 3.

**Bài 5 — Kiểm chứng bằng mô phỏng.** Với dãy số nguyên nhỏ sinh ngẫu nhiên, đối chiếu:

- `frequency(c,l,r)` với `S[l:r].count(c)`.
- `access(i)` với `S[i]`.
- `kth(l,r,k)` với `sorted(S[l:r])[k-1]`.
- `count_less(c,l,r)` với số phần tử `x<c` trong `S[l:r]`.

Thử thêm dãy rỗng, dãy chỉ có một ký hiệu, các đoạn `[l,l)`, ký hiệu âm và ngưỡng không có trong dãy. Mục tiêu không chỉ so khớp kết quả mà còn giải thích vì sao ánh xạ chỉ số ở mỗi tầng giữ đúng ý nghĩa truy vấn.

**Bài 6 — Thiết kế tiết kiệm bộ nhớ.** Nếu `n=10^6` và `σ=256`, hãy ước lượng số bit dữ liệu phân hướng ở cây cân bằng trước khi tính phụ trợ `rank` và metadata. So sánh về bậc độ lớn với bảng `(n+1)\sigma` số đếm 32-bit.

*Đáp án đối chiếu:* `\lceil\log_2 256\rceil=8` nên phần bit phân hướng có khoảng `8\times10^6` bit, tương đương khoảng `1,000,000` byte; bảng tiền tố tần suất đầy đủ cần khoảng `(1,000,001)\times256\times4 \approx 1.024\times10^9` byte. Đây chỉ là so sánh phần dữ liệu thô; bộ nhớ phụ trợ và hiện thực cụ thể có thể làm thay đổi con số thực tế.

## 12. Tổng kết

Wavelet tree tổ chức lại một dãy ký hiệu thông qua việc **chia đôi miền giá trị** và lưu thông tin **phân hoạch ổn định** ở từng nút. Bất biến cốt lõi là ánh xạ đoạn `[l,r)` tại nút cha sang `[P[l],P[r])` ở con trái hoặc `[l-P[l],r-P[r])` ở con phải, trong đó `P[i]` đếm số phần tử đi trái trong `i` phần tử đầu.

Từ bất biến này, cây hỗ trợ rank, frequency, access, k-th và đếm theo khoảng giá trị trong `O(\log\sigma)` với cấu trúc đếm tiền tố hiệu quả. Sự khác biệt giữa **mảng số nguyên tiền tố dễ cài đặt** và **bitvector đóng gói hỗ trợ rank** là chìa khóa để hiểu vì sao wavelet tree thuộc nhóm cấu trúc biểu diễn gọn. Khi lựa chọn cho ứng dụng thực tế, cần cân nhắc bảng chữ cái, số lượng truy vấn, việc dữ liệu có cập nhật hay không và chi phí bộ nhớ thực tế của cách cài đặt.
