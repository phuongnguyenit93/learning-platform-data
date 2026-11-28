# Nén danh sách số tăng dần và biểu diễn Elias–Fano

## 1. Vì sao danh sách số đã sắp xếp có thể nén tốt?

Một chỉ mục tìm kiếm, danh sách ID tài liệu, tập vị trí xuất hiện của từ trong văn bản hay tập các mốc thời gian có thể được lưu dưới dạng dãy số nguyên **tăng nghiêm ngặt**:

```text
2, 3, 7, 13, 14, 25
```

Nếu mọi số nằm trong miền `[0,U)`, cách trực tiếp là dùng `⌈log₂ U⌉` bit cho mỗi số. Chẳng hạn, với `U=32`, sáu số trên cần `6 × 5 = 30` bit khi lưu cố định 5 bit/số, chưa tính phần quản lý mảng.

Tuy nhiên, thứ tự tăng dần mang một bất biến mạnh: khi biết các phần tử trước, giá trị của phần tử tiếp theo phải lớn hơn chúng. Vì vậy, số dãy hợp lệ ít hơn rất nhiều so với số dãy bất kỳ. **Elias–Fano** tận dụng tính đơn điệu này để lưu các giá trị bằng hai phần *bit thấp* và *bit cao*, sử dụng một bitvector cho phần cao.

Biểu diễn này đặc biệt hấp dẫn khi danh sách **tĩnh hoặc ít cập nhật**, cần đọc phần tử thứ `i` nhanh, và có thể cần các truy vấn như tìm phần tử đầu tiên không nhỏ hơn `x` (*lower bound*), phần tử liền trước (*predecessor*) hoặc liền sau (*successor*).

Trong chương **Biểu diễn gọn** của học phần cấu trúc dữ liệu, đây là một ví dụ về cách chọn biểu diễn dựa trên **bất biến của dữ liệu**, cũng như đánh đổi giữa bộ nhớ, truy cập ngẫu nhiên và chi phí cập nhật.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Tách một danh sách tăng dần thành hai dãy *low*/*high* và tạo bitvector cao theo quy ước rõ ràng.
- Giải mã phần tử thứ `i` từ phép `select₁` và các bit thấp.
- Hiểu cách khoanh vùng một phần tử theo phần cao để trả lời `lower_bound`.
- Tính được số bit của hai thành phần và nhận ra các phần phụ trợ chưa được tính trong dung lượng lý thuyết.
- So sánh Elias–Fano với mảng số nguyên, bitmap và nén khoảng cách (*delta/gap encoding*).

## 2. Quy ước dữ liệu và cách chọn tham số

Ta xét dãy gồm `n ≥ 1` **số nguyên phân biệt, tăng nghiêm ngặt**:

\[
0 \le x_0 < x_1 < \cdots < x_{n-1} < U,
\]

trong đó `U` là **cận trên không bao gồm** (*exclusive upper bound*), không phải giá trị cuối cùng trong dãy. Vì các giá trị phân biệt trong `[0,U)` nên `1 \le n \le U`.

Nếu dãy chứa số âm, có thể trừ một mốc cố định trước khi mã hóa rồi cộng lại khi giải mã. Nếu dãy rỗng, cần quy ước biểu diễn riêng. Các biến thể Elias–Fano cũng có thể xử lý dãy không giảm với phần tử trùng nhau, nhưng bài này xét dãy **tăng nghiêm ngặt** để các thao tác trên tập số dễ hiểu.

Chọn số bit thấp:

\[
\ell = \left\lfloor\log_2\left(\frac{U}{n}\right)\right\rfloor,\qquad
w = 2^\ell.
\]

Vì `U/n \ge 1` nên `\ell \ge 0`. Nếu `\ell = 0` thì `w=1` và phần thấp của mọi số có độ dài **0 bit**; trường hợp này hoàn toàn hợp lệ.

Với mỗi số `x_i`, chia thành hai phần:

\[
h_i = \left\lfloor\frac{x_i}{w}\right\rfloor,
\qquad
l_i = x_i \bmod w.
\]

Như vậy:

\[
x_i = h_i \cdot w + l_i,\qquad 0\le l_i < w.
\]

- **Low:** lưu lần lượt `l_i` bằng đúng `\ell` bit/số.
- **High:** lưu dãy `h_i` (không giảm vì `x_i` tăng) dưới dạng bitvector đặc biệt.

Số giá trị cao có thể có là:

\[
H = \left\lceil\frac{U}{w}\right\rceil,
\]

ứng với các “nhóm cao” `0,1,\ldots,H-1`. Mỗi nhóm cao `b` chứa các giá trị gốc trong `[bw,(b+1)w)`, cắt theo miền `[0,U)`.

**Trực giác:** số bit thấp `\ell` giữ lại vị trí bên trong một nhóm có độ rộng `w`. Phần cao chỉ cần chỉ ra mỗi phần tử thuộc nhóm nào. Thứ tự tăng dần cho phép lưu phần cao bằng bitvector thay cho một số nguyên riêng ở mỗi vị trí.

## 3. Tạo bitvector high: mã hóa vị trí bằng bit 1

Đánh số phần tử dãy từ `i=0`. Elias–Fano đặt **bit `1` thứ `i+1`** ở vị trí:

\[
p_i = h_i + i.
\]

Các vị trí của bitvector cũng được đánh số từ **0**. Ta tạo bitvector `B` dài đúng:

\[
|B| = H+n,
\]

đặt `B[p_i]=1` cho mọi `i`, và đặt các vị trí khác bằng `0`.

Vì `h_i` không giảm, các vị trí `p_i=h_i+i` **tăng nghiêm ngặt**, nên không có hai bit `1` trùng vị trí. Bitvector chứa chính xác `n` bit `1` và `H` bit `0`.

Có thể hình dung một bit `0` là ranh giới kết thúc một nhóm cao. Nếu một nhóm cao có nhiều phần tử, sẽ có nhiều bit `1` liên tiếp trước bit `0` tương ứng; nếu nhóm trống, chỉ có bit `0`.

### Ví dụ tự xây từ đầu

Cho:

\[
X=[2,3,7,13,14,25],\qquad U=32,\qquad n=6.
\]

Vì `\lfloor\log_2(32/6)\rfloor=2`, ta có `\ell=2`, `w=4` và `H=\lceil32/4\rceil=8`.

| `i` | `x_i` | `h_i=\lfloor x_i/4\rfloor` | `l_i=x_i\bmod4` | Low (2 bit) | `p_i=h_i+i` |
|---:|---:|---:|---:|:---:|---:|
| 0 | 2 | 0 | 2 | `10` | 0 |
| 1 | 3 | 0 | 3 | `11` | 1 |
| 2 | 7 | 1 | 3 | `11` | 3 |
| 3 | 13 | 3 | 1 | `01` | 6 |
| 4 | 14 | 3 | 2 | `10` | 7 |
| 5 | 25 | 6 | 1 | `01` | 11 |

Phần thấp là sáu cặp bit, tổng cộng 12 bit:

```text
Low theo thứ tự:   10 | 11 | 11 | 01 | 10 | 01
Chuỗi low:         101111011001
```

Bitvector cao dài `H+n=8+6=14` bit, có bit `1` tại các vị trí `0,1,3,6,7,11`:

```text
Vị trí (0-based):   0 1 2 3 4 5 6 7 8 9 10 11 12 13
Bit B:              1 1 0 1 0 0 1 1 0 0  0  1  0  0

B = 11010011000100
```

Số bit cấu trúc và dữ liệu thấp trong ví dụ là:

\[
n\ell+(H+n)=6\cdot2+(8+6)=26\text{ bit}.
\]

So với 30 bit khi dùng 5 bit/số, ví dụ nhỏ này chỉ tiết kiệm 4 bit. Mục tiêu của ví dụ là làm rõ cách mã hóa; mức tiết kiệm có ý nghĩa hơn khi `U` lớn, `n` đủ lớn và ta chọn triển khai bitvector phù hợp.

**Quan trọng:** không nên nhầm `U=32` với giá trị lớn nhất `25`. Nếu biết tất cả phần tử đều nhỏ hơn `26`, có thể chọn `U=26`, tính lại `\ell,H` và mã hóa theo miền mới.

## 4. Giải mã bằng select₁

Quy ước `select_1(B,k)` là **vị trí tính từ 0** của bit `1` thứ `k` trong `B`, trong đó `k` bắt đầu từ **1**. Như vậy, bit `1` ứng với phần tử `i` nằm tại:

\[
select_1(B,i+1)=h_i+i.
\]

Suy ra:

\[
\boxed{h_i=select_1(B,i+1)-i}
\]

và:

\[
\boxed{x_i=\bigl(select_1(B,i+1)-i\bigr)\cdot 2^\ell+l_i.}
\]

Từng bước để lấy `x_3` (phần tử thứ tư):

1. Từ `B`, bit `1` thứ tư nằm ở vị trí `select_1(B,4)=6`.
2. Vì `i=3`, phần cao là `h_3=6-3=3`.
3. Đọc cặp bit thấp thứ tư `01`, tức `l_3=1`.
4. Khôi phục `x_3=3\cdot4+1=13`.

Tương tự, để lấy `x_5`: bit `1` thứ sáu ở vị trí `11`, nên `h_5=11-5=6`; low là `01`, vậy `x_5=25`.

Khi bitvector được hỗ trợ phép `select_1` trong `O(1)` thời gian và có thể đọc một trường low `\ell` bit trong `O(1)`, **truy cập theo thứ tự `i`** cũng thực hiện được trong `O(1)` trên mô hình từ máy thích hợp. Dãy Elias–Fano nhờ đó có lợi thế rõ rệt so với cách chỉ lưu hiệu giữa hai số liên tiếp rồi phải cộng dồn từ đầu để tìm phần tử thứ `i`.

## 5. Tìm nhanh theo giá trị: nhóm cao và các bit 0

Ngoài truy cập theo chỉ số, ta còn muốn tìm **vị trí phần tử đầu tiên không nhỏ hơn `q`**, ký hiệu `lower_bound(q)`. Nếu không có phần tử thỏa mãn, kết quả là `n`.

Đặt `b=\lfloor q/w\rfloor`. Nếu `0\le q<U` thì mọi phần tử có phần cao nhỏ hơn `b` chắc chắn nhỏ hơn `q`; mọi phần tử có phần cao lớn hơn `b` chắc chắn lớn hơn `q`. Vậy chỉ cần xem các phần tử thuộc **nhóm cao `b`**, tìm theo bit thấp trong nhóm này.

### 5.1. Xác định khoảng chỉ số của một nhóm cao

Đặt `C(b)` là **số phần tử có high nhỏ hơn `b`**. Theo định nghĩa, `C(0)=0` và `C(H)=n`.

Dùng `select_0(B,b)` để chỉ **vị trí tính từ 0** của bit `0` thứ `b` (với `b\ge1`). Trước bit `0` thứ `b` có đúng `b-1` bit `0`, do đó số bit `1` đứng trước nó là:

\[
\boxed{C(b)=select_0(B,b)-(b-1),\qquad 1\le b\le H.}
\]

Nhóm cao `b` (với `0\le b<H`) chiếm khoảng **chỉ số phần tử**:

\[
\boxed{[C(b),C(b+1)).}
\]

Trong ví dụ, các vị trí bit `0` là `2,4,5,8,9,10,12,13`, nên:

```text
Nhóm cao b:  0 1 2 3 4 5 6 7
C(b):        0 2 3 3 5 5 5 6
C(b+1):      2 3 3 5 5 5 6 6

Các giá trị:
b=0: [2, 3]
b=1: [7]
b=2: []
b=3: [13, 14]
b=4: []
b=5: []
b=6: [25]
b=7: []
```

Lưu ý: khi tìm một nhóm cao rỗng, `C(b)=C(b+1)`; công thức vẫn đúng.

### 5.2. Lower bound và predecessor/successor

Với `0\le q<U`, tính:

\[
b=\lfloor q/w\rfloor,\qquad t=q\bmod w.
\]

Thực hiện:

1. Tìm `a=C(b)` và `z=C(b+1)`.
2. Trong đoạn các phần thấp `l_a,\ldots,l_{z-1}`, tìm vị trí đầu tiên có `l_i\ge t` bằng tìm kiếm nhị phân.
3. Trả về chỉ số đó. Nếu không có phần tử đủ lớn trong nhóm này, chỉ số nhận được là `z`, tức phần tử đầu tiên của nhóm cao lớn hơn, hoặc `n` nếu đã hết dãy.

Vì dãy `x_i` tăng nghiêm ngặt, **các low trong cùng một nhóm cao tăng nghiêm ngặt**, nên phép tìm kiếm nhị phân trên một nhóm là hợp lệ.

Ví dụ với `q=12`: `b=3`, `t=0`. Khoảng nhóm cao số `3` là `[C(3),C(4))=[3,5)`, có low `[1,2]`, tương ứng `[13,14]`. Phần tử đầu tiên có low không nhỏ hơn `0` là `13` ở chỉ số `3`, nên `lower_bound(12)=3`.

Với `q=15`: vẫn ở nhóm `3` nhưng `t=3`. Cả low `1` và `2` đều nhỏ hơn `3` nên kết quả là chỉ số `5`, giá trị `25`. Như vậy:

- `successor(q)` (phần tử nhỏ nhất `\ge q`) là `x_{lower\_bound(q)}` nếu chỉ số này nhỏ hơn `n`.
- `predecessor(q)` (phần tử lớn nhất `\le q`) là `x_{lower\_bound(q+1)-1}` nếu chỉ số không âm.
- Số phần tử **nhỏ hơn** `q` chính là `lower_bound(q)`; đây là một dạng `rank` trên tập tăng dần.

Nếu `q\le0` thì `lower_bound(q)=0`. Nếu `q\ge U` thì `lower_bound(q)=n`. Các điều kiện biên này giúp truy vấn vẫn đúng khi ngưỡng nằm ngoài miền mã hóa.

**Phân biệt chi phí:** Elias–Fano cơ bản cho truy cập theo **chỉ số** nhanh nhờ `select_1`. Tìm theo **giá trị** còn phải định vị nhóm cao và tìm trong các low thuộc nhóm. Với `select_0` nhanh và tìm kiếm nhị phân, chi phí là `O(1+\log(m+1))` cho `m` phần tử trong nhóm đang xét; không nên tự động coi mọi truy vấn predecessor/successor của mọi cách triển khai Elias–Fano đều có `O(1)` trong trường hợp xấu nhất.

## 6. Mã Python minh họa

Lớp dưới đây làm rõ các thao tác. Để dễ kiểm tra bằng mắt, nó dựng chuỗi bit high và giữ danh sách **vị trí các bit `1`/`0` bằng số nguyên Python**. Những danh sách phụ này giúp `select` nhanh trong ví dụ, nhưng **không phải một bitvector succinct thực thụ**.

~~~python
from bisect import bisect_left


class EliasFano:
    def __init__(self, values, universe):
        values = list(values)
        if type(universe) is not int or universe <= 0:
            raise ValueError("universe phải là số nguyên dương")
        if not values:
            raise ValueError("Ví dụ này yêu cầu dãy không rỗng")
        if any(type(x) is not int for x in values):
            raise TypeError("Các giá trị phải là số nguyên")
        if (values[0] < 0 or values[-1] >= universe
                or any(values[i] <= values[i - 1]
                       for i in range(1, len(values)))):
            raise ValueError("Dãy phải tăng nghiêm ngặt trong [0, U)")

        self.n = len(values)
        self.universe = universe

        # floor(log2(U/n)) tính được bằng phép toán số nguyên
        self.ell = (universe // self.n).bit_length() - 1
        self.base = 1 << self.ell
        self.num_high_groups = (
            universe + self.base - 1
        ) // self.base  # ceil(U/base)

        self.lows = [x % self.base for x in values]
        bits = ["0"] * (self.num_high_groups + self.n)

        for i, x in enumerate(values):
            high = x // self.base
            pos = high + i
            bits[pos] = "1"

        self.high_bits = "".join(bits)

        # Bảng chọn trực tiếp để minh họa; chi phí bộ nhớ lớn.
        self.one_positions = [
            p for p, bit in enumerate(bits) if bit == "1"
        ]
        self.zero_positions = [
            p for p, bit in enumerate(bits) if bit == "0"
        ]

    def __len__(self):
        return self.n

    def select(self, i):
        """Lấy x_i với i bắt đầu từ 0."""
        if not 0 <= i < self.n:
            raise IndexError("Chỉ số nằm ngoài dãy")
        high = self.one_positions[i] - i
        return high * self.base + self.lows[i]

    def _count_high_below(self, b):
        """C(b): số phần tử có phần cao nhỏ hơn b."""
        if b == 0:
            return 0
        # zero_positions[b-1] là select_0(B,b) theo 0-based
        return self.zero_positions[b - 1] - (b - 1)

    def lower_bound(self, q):
        """Chỉ số đầu tiên i thỏa x_i >= q; trả n nếu không có."""
        if q <= 0:
            return 0
        if q >= self.universe:
            return self.n

        b, low = divmod(q, self.base)
        start = self._count_high_below(b)
        end = self._count_high_below(b + 1)

        # Trong cùng một high, các low vẫn tăng nghiêm ngặt.
        return bisect_left(self.lows, low, start, end)

    def successor(self, q):
        """Giá trị nhỏ nhất >= q, hoặc None."""
        i = self.lower_bound(q)
        return self.select(i) if i < self.n else None

    def predecessor(self, q):
        """Giá trị lớn nhất <= q, hoặc None."""
        i = self.lower_bound(q + 1) - 1
        return self.select(i) if i >= 0 else None


ef = EliasFano([2, 3, 7, 13, 14, 25], universe=32)
assert ef.ell == 2
assert ef.base == 4
assert ef.high_bits == "11010011000100"
assert ef.lows == [2, 3, 3, 1, 2, 1]
assert [ef.select(i) for i in range(len(ef))] == [
    2, 3, 7, 13, 14, 25
]

assert ef.lower_bound(12) == 3    # x_3 = 13
assert ef.lower_bound(15) == 5    # x_5 = 25
assert ef.lower_bound(26) == 6    # không có số >= 26
assert ef.successor(15) == 25
assert ef.predecessor(15) == 14
assert ef.predecessor(0) is None
assert ef.successor(30) is None

# Trường hợp mọi số trong [0, U) đều có mặt: ell = 0
dense = EliasFano([0, 1, 2, 3], universe=4)
assert dense.ell == 0
assert [dense.select(i) for i in range(4)] == [0, 1, 2, 3]
~~~

Trong cài đặt minh họa này, việc dựng chuỗi bit mất `O(n+H)` thời gian và các bảng vị trí dùng thêm `O(n+H)` **số nguyên Python**. Với chỉ mục `select_0/select_1` trên bitvector đóng gói, cấu trúc thực tế có thể tiết kiệm bộ nhớ hơn nhiều.

**Dùng trong hệ thống thật:** phần low thường được đóng gói thành các trường đúng `\ell` bit; phần high là bitvector có chỉ mục `select`. Một số triển khai còn thêm chỉ mục để tăng tốc `predecessor` hoặc hỗ trợ thao tác khác. Vì thế cùng được gọi là “Elias–Fano” nhưng số byte thực tế và hiệu năng vẫn tùy cách cài đặt.

## 7. Vì sao mã hóa và giải mã đúng?

Có ba bất biến đáng chú ý:

**Bất biến 1 — phần high không giảm.** Vì `x_i<x_{i+1}` và phép chia nguyên cho `w>0` bảo toàn thứ tự không giảm, ta có `h_i\le h_{i+1}`.

**Bất biến 2 — vị trí bit 1 tăng nghiêm ngặt.** Với `p_i=h_i+i`:

\[
p_{i+1}-p_i=(h_{i+1}-h_i)+1\ge1.
\]

Do đó mỗi phần tử có đúng một bit `1` riêng, và `select_1(B,i+1)=p_i`.

**Bất biến 3 — số phần tử trước một nhóm bằng số bit 1 trước ranh giới.** Bit `0` thứ `b` khép lại toàn bộ các nhóm cao nhỏ hơn `b`. Trước bit ấy có `b-1` bit `0`, nên trong `select_0(B,b)` vị trí đứng trước nó có đúng `select_0(B,b)-(b-1)` bit `1`, tức `C(b)` phần tử.

Từ bất biến 2, giải mã bằng `h_i=p_i-i` rồi ghép lại với `l_i` nhận đúng `x_i`. Từ bất biến 3, ta tìm được khoảng các phần tử có cùng high. Trong khoảng này, thứ tự tăng của `x_i` đồng nghĩa với thứ tự tăng của low; vì thế tìm kiếm nhị phân tìm đúng `lower_bound`.

Tính đúng đắn của các phép truy vấn dựa vào những quan hệ này; các chỉ mục `select` chỉ thay đổi **tốc độ tính**, không làm thay đổi ý nghĩa dãy đã mã hóa.

## 8. Phân tích số bit và độ phức tạp

Biểu diễn cốt lõi có:

- `n\ell` bit thấp, vì mỗi phần tử dùng `\ell` bit.
- `n+H` bit cao, gồm `n` bit `1` và `H` bit `0`.

Vậy tổng là:

\[
\boxed{S=n\ell+n+\left\lceil\frac{U}{2^\ell}\right\rceil\text{ bit}.}
\]

Với `\ell=\lfloor\log_2(U/n)\rfloor`, ta có:

\[
n\le\frac{U}{2^\ell}<2n.
\]

Do đó `H\le2n` và:

\[
S\le n\ell+3n.
\]

Một chặn gọn hơn (tính đến làm tròn) là:

\[
S\le n\log_2(U/n)+2n+1.
\]

Vì vậy phần mã hóa có cỡ `n\log_2(U/n)+O(n)` bit. Đây là lợi thế lớn khi `U` rộng so với số lượng giá trị `n`. Tuy nhiên, **không được nhầm công thức này với tổng RAM thực tế**: còn có metadata `n,U,\ell`, chỉ mục `select`, căn chỉnh bit và các chi phí của ngôn ngữ/thư viện.

Nếu `U` rất lớn, `n` nhỏ, Elias–Fano giảm đáng kể số bit so với lưu trực tiếp `n\log_2 U` bit. Nếu dãy rất dày (gần như chứa hết `[0,U)`), **bitmap thông thường dài `U` bit** có thể tiết kiệm hơn mã hóa Elias–Fano với tham số mặc định.

### Ví dụ về số bit

Với `U=2^{32}` và `n=2^{20}`:

\[
\ell=\left\lfloor\log_2(2^{32}/2^{20})\right\rfloor=12,
\qquad w=2^{12},
\qquad H=2^{20}.
\]

Khi đó phần low tốn `12n` bit, high tốn `2n` bit, tổng `14n` bit, tức `14 \times 2^{20}=14\,680\,064` bit ≈ `1.75 MiB`. Lưu cố định 32 bit/số sẽ tốn `32n` bit = `4 MiB`. Cả hai con số đều **chưa tính** metadata và chỉ mục truy vấn.

| Công việc | Chi phí điển hình | Điều kiện |
|---|---|---|
| Mã hóa từ danh sách đã tăng | `O(n+H)` thời gian | Khởi tạo `H+n` bit và `n` phần low |
| Đọc `x_i` | `O(1)` | `select_1` và truy cập low nhanh |
| Tìm `C(b)` | `O(1)` | `select_0` nhanh |
| `lower_bound(q)` | `O(1+\log(m+1))` | `m` phần tử trong nhóm cao `\lfloor q/w\rfloor`; dùng tìm kiếm nhị phân low |
| `successor/predecessor` | Như `lower_bound`, cộng một lần đọc phần tử | Cần xử lý khi không có kết quả |
| Duyệt tuần tự các giá trị | `O(n)` | Có thể dùng `select_1` từng phần tử hoặc giải mã tuần tự |
| Chèn/xóa tùy ý | Không phải thế mạnh của cấu trúc tĩnh | Có thể phải cập nhật nhiều bit và chỉ mục |

Các chỉ mục `select` có thể thiết kế với phần phụ trợ nhỏ trên bitvector trong mô hình thích hợp. Ngược lại, lưu trực tiếp mọi vị trí bit `0` và `1` bằng số nguyên máy như trong Python là dùng `O(n+H)` **từ máy**, lớn hơn đáng kể so với chuỗi bit lõi.

## 9. Khi nào nên chọn Elias–Fano?

| Biểu diễn | Lợi thế | Giới hạn |
|---|---|---|
| Mảng số nguyên cố định độ rộng | Truy cập `x_i` trực tiếp, cập nhật một phần tử đơn giản nếu còn giữ thứ tự | Tốn gần `n\lceil\log_2 U\rceil` bit cho dữ liệu |
| Danh sách khoảng cách (*gap/delta encoding*) | Có thể rất gọn khi các khoảng cách nhỏ | Tìm phần tử thứ `i` thường phải giải mã/cộng dồn hoặc bổ sung điểm lấy mẫu |
| Bitmap trên miền `[0,U)` | Dễ đánh dấu có/không; `rank/select` có thể giúp tìm phần tử theo thứ tự | Tốn `U` bit, bất lợi khi tập rất thưa |
| Elias–Fano | Nén theo mật độ `U/n`, hỗ trợ truy cập theo thứ tự tốt với `select` | Cập nhật không thuận tiện; truy vấn theo giá trị còn cần xử lý nhóm và chỉ mục |
| Cây tìm kiếm cân bằng | Chèn/xóa/tìm theo giá trị linh hoạt | Liên kết, cấp phát và cân bằng cây thường tốn bộ nhớ hơn cho tập tĩnh |

**Những tình huống phù hợp:** danh sách ID bài đăng trong inverted index, vị trí xuất hiện của token trong một chuỗi, các offset của đoạn dữ liệu trong tệp lớn, hoặc ID tăng dần trong cấu trúc đã xây xong. Các ứng dụng này thường đọc danh sách nhiều lần trong khi nội dung ít thay đổi.

**Những tình huống cần cân nhắc:** nếu dữ liệu liên tục thêm/xóa ở giữa, cần sửa nhiều bit hoặc tái xây; nếu `U` quá nhỏ so với `n`, bitmap có thể hợp lý hơn; nếu danh sách chứa nhiều số trùng thì phải xác định phiên bản mã hóa hỗ trợ dãy không giảm; nếu cần tra cứu theo giá trị với độ trễ nghiêm ngặt, phải đánh giá cả chỉ mục `select_0` và chi phí tìm trong nhóm cao.

## 10. Những lỗi thường gặp

1. **Lấy `U` là giá trị lớn nhất thay vì cận trên loại trừ.** Nếu giá trị lớn nhất là `25` thì `U` tối thiểu phải bằng `26`, không phải `25`.
2. **Nhầm chỉ số phần tử và vị trí bit.** Phần tử có chỉ số `i` từ `0` tương ứng với bit `1` thứ `i+1`; công thức là `h_i=select_1(B,i+1)-i`.
3. **Bỏ các nhóm cao không có phần tử.** Nhóm trống vẫn tạo một bit `0`, nhờ đó `C(b)` mới xác định được ranh giới cho mọi nhóm.
4. **Cho rằng tất cả low đều tăng.** Dãy low có thể giảm khi chuyển sang nhóm cao mới (ví dụ `3,1` từ `x=7` sang `x=13`). Low chỉ tăng **bên trong cùng một nhóm high**.
5. **Lấy phần cao và phần thấp theo số bit tùy ý mà không lưu `\ell`.** Bên giải mã phải biết cùng một `\ell` hoặc có cách suy ra nó từ metadata.
6. **Không xử lý `\ell=0`.** Lúc này không có bit thấp nào để đọc; giá trị `x_i` bằng phần cao `h_i`.
7. **Đồng nhất số bit lõi với dung lượng ứng dụng.** Chuỗi bit, bảng chọn, metadata và overhead đối tượng cần được đo riêng.
8. **Khẳng định predecessor luôn `O(1)`.** Độ phức tạp tùy thiết kế chỉ mục và thuật toán tìm trong nhóm cao.
9. **Lấy danh sách chưa sắp xếp làm đầu vào.** Công thức bit `p_i=h_i+i` dựa vào phần cao không giảm; cần sắp xếp/chuẩn hóa dữ liệu trước.
10. **Thay đổi giá trị làm mất thứ tự mà không kiểm tra.** Dạng cơ bản ở đây dành cho dãy tĩnh tăng nghiêm ngặt; sửa một giá trị có thể làm hỏng cả giả thiết mã hóa.

## 11. Tự luyện tập

**Bài 1 — Tách bit cao/thấp.** Với `X=[1,4,6,11]` và `U=16`, tính `n,\ell,w,H`, các dãy high/low và vị trí `p_i`. Viết bitvector high.

**Bài 2 — Giải mã.** Với ví dụ chính `X=[2,3,7,13,14,25]`, cho biết `select_1(B,5)` và khôi phục `x_4` mà không nhìn trực tiếp giá trị đã cho.

**Bài 3 — Khoanh vùng nhóm.** Tính `C(3)` và `C(4)` từ các vị trí bit `0` của ví dụ chính. Sau đó trả lời `lower_bound(14)`, `successor(15)` và `predecessor(12)`.

**Bài 4 — Đánh đổi bộ nhớ.** Với `U=64` và `n=8`, tính `\ell,H` và số bit lõi Elias–Fano. So với số bit khi lưu từng số cố định 6 bit.

**Bài 5 — Tập rất dày.** Nếu `U=n=16` và tập chứa toàn bộ `0,1,\ldots,15`, Elias–Fano cơ bản dùng bao nhiêu bit? Một bitmap dùng bao nhiêu bit? Tại sao cần chọn biểu diễn theo mật độ thực tế?

**Bài 6 — Thiết kế truy vấn.** Giải thích vì sao tìm kiếm nhị phân trên **toàn bộ** mảng low có thể sai, còn tìm kiếm nhị phân trên `low[C(b):C(b+1)]` thì đúng.

<details>
<summary>Đáp án đối chiếu</summary>

- **Bài 1:** `n=4`, `U/n=4`, `\ell=2`, `w=4`, `H=4`. High `[0,1,1,2]`; low `[1,0,2,3]`. Vị trí `p=[0,2,3,5]`. Bitvector dài 8 với bit `1` tại `0,2,3,5`: `B=10110100`.
- **Bài 2:** `select_1(B,5)=7`; `h_4=7-4=3`, low thứ năm là `10` = 2, nên `x_4=3\cdot4+2=14`.
- **Bài 3:** `C(3)=5-(3-1)=3` và `C(4)=8-(4-1)=5`. `lower_bound(14)=4` (chỉ số của 14); `successor(15)=25`; `predecessor(12)=7`.
- **Bài 4:** `\ell=3`, `w=8`, `H=8`; Elias–Fano dùng `8\cdot3+(8+8)=40` bit lõi, mảng số cố định dùng `8\cdot6=48` bit.
- **Bài 5:** `\ell=0`, `H=16`, tổng `16+16=32` bit, còn bitmap chỉ dùng `16` bit. Với tập quá dày, bitmap có thể hiệu quả hơn.
- **Bài 6:** Khi high tăng, low có thể quay về giá trị nhỏ; ví dụ high chuyển từ `1` sang `3` thì low đổi từ `3` (số 7) xuống `1` (số 13). Trong cùng một high, thứ tự của `x_i` chính là thứ tự low, nên đoạn low của nhóm được sắp tăng.

</details>

## 12. Ghi nhớ

Elias–Fano mã hóa dãy tăng nghiêm ngặt bằng `x_i=h_i2^\ell+l_i`, lưu `l_i` trong `\ell` bit và đặt bit `1` tại `p_i=h_i+i` trên bitvector dài `n+\lceil U/2^\ell\rceil`. Nhờ `select_1`, ta lấy lại `x_i`; nhờ các bit `0`, ta xác định nhanh ranh giới mỗi nhóm high để hỗ trợ truy vấn theo giá trị. Đây là sự kết hợp giữa một **bất biến có thứ tự**, một **biểu diễn bit** và các **chỉ mục truy vấn**: ba thành phần cần được tính tách biệt khi đánh giá cả tính đúng đắn lẫn bộ nhớ thực tế.
