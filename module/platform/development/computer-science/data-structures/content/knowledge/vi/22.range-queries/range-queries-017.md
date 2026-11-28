# So sánh mảng tiền tố, bảng thưa, Fenwick và cây đoạn

## 1. Vì sao cùng là truy vấn đoạn nhưng cần nhiều cấu trúc dữ liệu?

Một mảng có thể phục vụ nhiều loại câu hỏi:

- **Tổng đoạn:** tổng doanh thu từ ngày `l` đến trước ngày `r`.
- **Giá trị nhỏ nhất đoạn:** nhiệt độ thấp nhất trong khoảng thời gian đó.
- **Cập nhật điểm:** tăng doanh thu tại một ngày sau khi ghi nhận giao dịch muộn.
- **Cập nhật đoạn:** cộng một khoản điều chỉnh cho nhiều ngày liên tiếp.

Mặc dù đều nói về một đoạn của mảng, các yêu cầu này dẫn đến những cách tổ chức dữ liệu rất khác nhau. Trong chương **Truy vấn đoạn** của học phần cấu trúc dữ liệu, bốn công cụ thường gặp là **mảng tiền tố (prefix sum)**, **bảng thưa (sparse table)**, **cây Fenwick (Binary Indexed Tree, BIT)** và **cây đoạn (segment tree)**.

Mục tiêu là biết chúng dựa trên bất biến nào, trả lời được kiểu truy vấn nào, cập nhật với chi phí bao nhiêu và dùng bao nhiêu bộ nhớ, từ đó chọn cấu trúc phù hợp với bài toán cụ thể.

Trong toàn bài, mảng `A` có `n` phần tử, chỉ số ngoài giao diện bắt đầu từ `0`, các đoạn đều ở dạng **nửa mở** `[l, r)` với `0 ≤ l ≤ r ≤ n`. Đoạn rỗng `[l, l)` có tổng bằng `0`. Ví dụ xuyên suốt:

~~~text
Chỉ số:     0  1  2  3  4  5  6  7
A:         2  1  3  4  0  5  2  6
                      |--------|
Truy vấn [2,6):        3 + 4 + 0 + 5 = 12
Min trên [2,6):        min(3,4,0,5) = 0
~~~

## 2. Ba thuộc tính cần xác định trước khi chọn

Trước khi chọn cấu trúc, hãy phân biệt **dữ liệu có thay đổi không**, **phép gộp là gì** và **cần trả lời loại truy vấn nào**.

### Phép toán kết hợp

Một phép gộp `⊕` là **kết hợp** nếu:

\[
(a \oplus b) \oplus c = a \oplus (b \oplus c).
\]

Tổng, min, max, gcd và phép XOR đều có tính kết hợp. Nhờ đó, ta có thể chia `[l, r)` thành các phần liền nhau, tính kết quả từng phần rồi gộp lại. Cây đoạn được xây dựng dựa trên tính chất này. Khi dùng cây đoạn để tính kết quả trên đoạn rỗng, còn cần một **phần tử trung hòa** `e` thỏa mãn `e ⊕ x = x ⊕ e = x`: tổng dùng `0`, min có thể dùng `+∞`, max dùng `-∞`.

### Có phép nghịch đảo không?

Với phép cộng, ta có thể trừ hai tổng tiền tố:

\[
\operatorname{sum}(l,r)
= \operatorname{prefix}(r) - \operatorname{prefix}(l).
\]

Phép trừ là nghịch đảo của phép cộng. Điều tương tự không áp dụng cho min: biết min của `[0, r)` và min của `[0, l)` không cho phép suy ra min của `[l, r)`. Mảng tổng tiền tố và Fenwick chuẩn đặc biệt thuận tiện cho tổng và những phép toán tiền tố có thể loại phần trước bằng phép nghịch đảo, chẳng hạn XOR.

### Phép gộp có lũy đẳng không?

Một phép toán **lũy đẳng** nếu `x ⊕ x = x`. Ví dụ, `min(x, x) = x` và `max(x, x) = x`. Nhưng `x + x` thường khác `x`.

Đây là điều kiện cho phép sparse table trả lời min/max trên một đoạn bằng cách gộp **hai khối có thể chồng lên nhau** mà không đếm sai phần giao.

| Phép gộp | Kết hợp | Có thể loại tiền tố bằng nghịch đảo | Lũy đẳng |
| --- | :---: | :---: | :---: |
| Tổng số nguyên | Có | Có (trừ) | Không |
| XOR | Có | Có (XOR) | Không |
| Min | Có | Không | Có |
| Max | Có | Không | Có |
| GCD (giá trị chuẩn hóa không âm) | Có | Không | Có |

Các tính chất đại số giải thích nhiều lựa chọn về cấu trúc dữ liệu: công cụ nào dựa vào phép trừ tiền tố, công cụ nào cho phép các đoạn chồng nhau, và công cụ nào chỉ cần gộp các đoạn kề nhau.

## 3. Mảng tiền tố: nhanh nhất khi cần tổng trên dữ liệu tĩnh

Tạo mảng `P` có `n+1` phần tử:

\[
P[0]=0,\qquad
P[i+1]=P[i]+A[i]\quad (0\le i<n).
\]

Khi đó `P[r]` là tổng trên `[0, r)`, nên:

\[
\boxed{\operatorname{sum}(l,r)=P[r]-P[l]}.
\]

Với mảng ví dụ:

~~~text
A:  2  1  3  4  0  5  2  6
P:  0  2  3  6 10 10 15 17 23

sum(2,6) = P[6] - P[2] = 15 - 3 = 12
~~~

**Bất biến:** `P[i] = A[0] + \cdots + A[i-1]`. Xây dựng mất `O(n)` thời gian và `O(n)` bộ nhớ; truy vấn tổng bất kỳ mất `O(1)`.

Nếu thay đổi `A[k]` thêm `d`, mọi `P[i]` với `i > k` đều phải tăng `d`. Cập nhật trực tiếp các giá trị tiền tố có thể mất `O(n)`. Vì vậy mảng tiền tố rất thích hợp khi **không có cập nhật**, hoặc dữ liệu chỉ thỉnh thoảng được dựng lại theo lô.

Mảng tiền tố cho các phép có nghịch đảo (ví dụ tổng, XOR) cần phân biệt với **prefix min**: dù có thể tính min của các tiền tố, không thể lấy hiệu để biết min của một đoạn nằm giữa.

## 4. Bảng thưa: trả lời min/max trên mảng bất biến

Sparse table tiền xử lý các khối có độ dài là lũy thừa của 2. Với truy vấn min, định nghĩa:

\[
ST[k][i] = \min(A[i],A[i+1],\ldots,A[i+2^k-1]),
\]

với điều kiện `i+2^k\le n`. Tầng `k=0` chứa chính các phần tử; các tầng sau được tính bằng:

\[
ST[k][i]
=\min\bigl(ST[k-1][i],\,ST[k-1][i+2^{k-1}]\bigr).
\]

Để hỏi min trên đoạn không rỗng `[l,r)`, đặt `k=\lfloor\log_2(r-l)\rfloor`. Hai khối dài `2^k` bắt đầu tại `l` và kết thúc tại `r` sẽ phủ toàn bộ đoạn:

\[
\boxed{\operatorname{min}(l,r)
=\min\bigl(ST[k][l],ST[k][r-2^k]\bigr)}.
\]

Hai khối có thể giao nhau. Điều này **an toàn đối với min/max** vì phần tử bị xét hai lần không làm đổi kết quả.

Ví dụ, với `[2,7)` có độ dài 5, chọn `2^k=4`. Ta lấy min của `[2,6)` và `[3,7)`. Hai khối chồng nhau tại `[3,6)` nhưng min vẫn đúng.

**Không được áp dụng công thức hai khối chồng nhau cho tổng.** Với `A=[5,4,3]`, tổng `[0,3)` bằng 12, trong khi lấy tổng của `[0,2)` và `[1,3)` cho kết quả `(5+4)+(4+3)=16` vì đếm phần tử giữa hai lần.

**Chi phí:** `O(n\log n)` thời gian xây, `O(n\log n)` ô lưu trữ, min/max/gcd trên đoạn không rỗng trong `O(1)`. Nếu có một cập nhật điểm bất kỳ, các bảng con chứa điểm đó có thể bị sai; cách triển khai sparse table thông thường **không phù hợp để cập nhật trực tuyến**, thường phải dựng lại với chi phí `O(n\log n)`.

Với tổng hoặc phép kết hợp không lũy đẳng, sparse table thường có thể gộp các **khối không chồng nhau** theo các bit của độ dài đoạn trong `O(\log n)` mỗi truy vấn. Một biến thể khác là *disjoint sparse table*, cho truy vấn `O(1)` với nhiều phép kết hợp bất kỳ sau `O(n\log n)` tiền xử lý; đó là một cấu trúc khác với công thức hai khối chồng nhau ở trên.

## 5. Fenwick tree: tổng đoạn khi có cập nhật điểm

Fenwick tree (BIT) lưu các tổng theo một cách khác. Dùng mảng nội bộ đánh số từ **1**, `bit[i]` chứa tổng của đoạn:

\[
(i-\operatorname{lowbit}(i),\ i],\qquad
\operatorname{lowbit}(i)=i\mathbin{\&}(-i).
\]

Đây là biểu thức trên **chỉ số 1-based**, nghĩa là `bit[6]` chứa tổng các vị trí 5 và 6; `bit[8]` chứa tổng các vị trí 1 đến 8.

Để tính tổng tiền tố của `r` phần tử đầu, bắt đầu từ `i=r`, cộng `bit[i]` rồi lặp `i -= lowbit(i)` cho đến `i=0`. Các đoạn được lấy không giao nhau và phủ đúng tiền tố. Để cộng `d` tại chỉ số bên ngoài `k` (0-based), bắt đầu `i=k+1`, cộng `d` vào `bit[i]` rồi lặp `i += lowbit(i)`.

~~~text
Tổng [0,6):
  bit[6] quản lý [5,6] (1-based)
  bit[4] quản lý [1,4] (1-based)
  Hai khối hợp lại thành [1,6].

Tổng [2,6) = tổng [0,6) - tổng [0,2).
~~~

**Bất biến:** mỗi `bit[i]` bằng tổng của khối dài `lowbit(i)` kết thúc ở vị trí `i`. Một phần tử được lưu trong `O(\log n)` khối liên quan. Vì vậy cập nhật điểm, tổng tiền tố và tổng đoạn đều mất `O(\log n)`; bộ nhớ `O(n)`. Có thể xây BIT từ mảng trong `O(n)` bằng cách cộng dồn sang cha theo thứ tự tăng, thay vì `n` lần cập nhật `O(\log n)`.

BIT chuẩn phù hợp nhất với **cộng điểm, tổng đoạn**. Nếu cần **cộng đoạn, tổng đoạn**, có biến thể dùng hai BIT trên mảng sai phân: cập nhật và truy vấn mỗi thao tác vẫn `O(\log n)`. Nhưng BIT chuẩn không tự động hỗ trợ min đoạn tùy ý cùng cập nhật tăng/giảm; một số biến thể min Fenwick chỉ đúng với các ràng buộc cập nhật đặc biệt.

## 6. Cây đoạn: linh hoạt khi cần cập nhật và nhiều kiểu gộp

Cây đoạn chia mỗi đoạn thành hai nửa và lưu kết quả gộp tại nút cha. Với phép tổng:

~~~text
                         [0,8): 23
                       /            \
                 [0,4): 10        [4,8): 13
                  /     \          /     \
             [0,2): 3 [2,4): 7 [4,6): 5 [6,8): 8
                ...      ...       ...      ...
~~~

**Bất biến:** kết quả tại mỗi nút bằng kết quả phép gộp trên toàn bộ các phần tử của đoạn nút ấy. Với tổng, `tree[v]=tree[2v]+tree[2v+1]` khi dùng cách đánh số cây từ gốc 1.

Một cập nhật điểm chỉ tác động tới nút lá và các tổ tiên của nó. Truy vấn đoạn tách thành những đoạn con rời nhau, rồi gộp các kết quả. Hai thao tác đều có độ phức tạp `O(\log n)`. Cây tĩnh xây trong `O(n)`, cần `O(n)` bộ nhớ.

Khác với Fenwick dùng để tổng, cây đoạn có thể dùng phép gộp **min, max, gcd, tổng, XOR**, hoặc các trạng thái phức tạp hơn như tổng và tổng tiền tố lớn nhất, miễn phép gộp có tính kết hợp và thứ tự gộp được giữ đúng.

**Lazy propagation** mở rộng cây đoạn cho các cập nhật đoạn. Chẳng hạn, nếu cộng `d` vào toàn bộ đoạn một nút có độ dài `len`, tổng của nút tăng thêm `d \times len`. Nút ghi thêm nhãn `lazy += d` để trì hoãn cập nhật các con cho tới khi cần đi xuống. Với cơ chế lazy đúng, cộng đoạn và hỏi tổng đoạn đều `O(\log n)` mỗi thao tác. Các bài toán gán đoạn hoặc kết hợp nhiều loại cập nhật cần định nghĩa quy tắc hợp nhất lazy cẩn thận.

Chi phí đổi lại là mã dài hơn, nhiều nút hơn Fenwick và nhiều trường hợp biên phải xử lý. Đối với miền chỉ số cực lớn, thưa, có thể cấp phát nút theo nhu cầu bằng **cây đoạn động**, giữ độ sâu `O(\log U)` cho miền có độ dài `U`.

## 7. Bảng so sánh độ phức tạp

Các chi phí dưới đây áp dụng cho **triển khai tiêu chuẩn** trên mảng có `n` phần tử. “Cập nhật điểm” là cộng một lượng vào một phần tử; “truy vấn đoạn” là phép thường dùng nhất của cấu trúc.

| Cấu trúc | Tiền xử lý / xây | Truy vấn đoạn | Cập nhật điểm | Bộ nhớ |
| --- | --- | --- | --- | --- |
| Mảng tổng tiền tố | `O(n)` | Tổng `O(1)` | `O(n)` | `O(n)` |
| Sparse table min/max | `O(n\log n)` | Min/max `O(1)` | Thường dựng lại `O(n\log n)` | `O(n\log n)` |
| Fenwick tree (BIT) | `O(n)` nếu xây trực tiếp | Tổng `O(\log n)` | `O(\log n)` | `O(n)` |
| Cây đoạn tĩnh | `O(n)` | Tổng/min/max/... `O(\log n)` | `O(\log n)` | `O(n)` |

Nếu nhiệm vụ có **cập nhật đoạn**, cần nêu rõ loại cập nhật và truy vấn trước khi kết luận:

| Yêu cầu | Hướng xử lý |
| --- | --- |
| Cộng đoạn, hỏi giá trị điểm | BIT trên mảng sai phân hoặc cây đoạn lazy |
| Cộng đoạn, hỏi tổng đoạn | Hai BIT hoặc cây đoạn lazy |
| Cộng đoạn, hỏi min/max đoạn | Cây đoạn lazy lưu min/max và nhãn cộng |
| Gán đoạn, hỏi tổng đoạn | Cây đoạn lazy với nhãn gán (có quy tắc ghi đè) |
| Chỉ hỏi tổng đoạn, hoàn toàn không cập nhật | Mảng tổng tiền tố |
| Chỉ hỏi min/max, hoàn toàn không cập nhật | Sparse table |

Không nên diễn giải bảng thành “cấu trúc có truy vấn nhanh nhất luôn tốt nhất”. Sparse table truy vấn `O(1)` nhưng tốn tiền xử lý và không thuận tiện cho cập nhật. Với cùng truy vấn tổng, BIT và cây đoạn đều `O(\log n)` nhưng BIT thường ít bộ nhớ và đơn giản hơn.

## 8. Cài đặt Python cho cùng một dữ liệu

Các ví dụ sau sử dụng Python 3, chỉ số **0-based** ở giao diện, đoạn `[l,r)`. Mảng dữ liệu khởi tạo được coi là độc lập giữa các cấu trúc. Mỗi lớp kiểm tra chỉ số để tránh dùng sai miền.

### 8.1. Mảng tổng tiền tố

~~~python
class PrefixSum:
    def __init__(self, data: list[int]) -> None:
        self.n = len(data)
        self.p = [0]
        for x in data:
            self.p.append(self.p[-1] + x)

    def query(self, left: int, right: int) -> int:
        if not (0 <= left <= right <= self.n):
            raise IndexError("Invalid range")
        return self.p[right] - self.p[left]
~~~

### 8.2. Sparse table cho RMQ (range minimum query)

~~~python
class SparseTableMin:
    def __init__(self, data: list[int]) -> None:
        if not data:
            raise ValueError("Sparse table needs a nonempty array")
        self.n = len(data)
        self.st = [data[:]]

        k = 1
        while (1 << k) <= self.n:
            half = 1 << (k - 1)
            previous = self.st[k - 1]
            full_len = 1 << k
            current = [
                min(previous[i], previous[i + half])
                for i in range(self.n - full_len + 1)
            ]
            self.st.append(current)
            k += 1

    def query(self, left: int, right: int) -> int:
        if not (0 <= left < right <= self.n):
            raise IndexError("RMQ requires a nonempty valid range")
        k = (right - left).bit_length() - 1
        width = 1 << k
        return min(self.st[k][left], self.st[k][right - width])
~~~

Hàm min không được hỏi trên đoạn rỗng nếu chưa định nghĩa riêng phần tử trung hòa; mã chọn báo lỗi. Bảng này **không có thao tác cập nhật** vì các khối đã tiền xử lý sẽ không tự thay đổi.

### 8.3. Fenwick tree cho cộng điểm và tổng đoạn

~~~python
class Fenwick:
    def __init__(self, data: list[int]) -> None:
        self.n = len(data)
        self.bit = [0] * (self.n + 1)

        # Xây O(n), thay vì n lần gọi add().
        for i, value in enumerate(data, start=1):
            self.bit[i] += value
            parent = i + (i & -i)
            if parent <= self.n:
                self.bit[parent] += self.bit[i]

    def add(self, index: int, delta: int) -> None:
        if not (0 <= index < self.n):
            raise IndexError("Invalid index")
        i = index + 1
        while i <= self.n:
            self.bit[i] += delta
            i += i & -i

    def prefix(self, right: int) -> int:
        """Tổng [0, right)."""
        if not (0 <= right <= self.n):
            raise IndexError("Invalid prefix")
        answer = 0
        i = right
        while i > 0:
            answer += self.bit[i]
            i -= i & -i
        return answer

    def query(self, left: int, right: int) -> int:
        if not (0 <= left <= right <= self.n):
            raise IndexError("Invalid range")
        return self.prefix(right) - self.prefix(left)
~~~

Điểm cần nhớ là **chỉ số giao diện** `index` từ `0`, còn bên trong BIT phải dùng `index + 1`; nếu để vòng lặp cập nhật bắt đầu từ 0, `i & -i = 0` sẽ khiến vòng lặp không tiến triển.

### 8.4. Cây đoạn lặp cho cộng điểm và tổng đoạn

~~~python
class SegmentTreeSum:
    def __init__(self, data: list[int]) -> None:
        self.n = len(data)
        self.size = 1
        while self.size < self.n:
            self.size *= 2

        self.tree = [0] * (2 * self.size)
        for i, value in enumerate(data):
            self.tree[self.size + i] = value
        for i in range(self.size - 1, 0, -1):
            self.tree[i] = self.tree[2 * i] + self.tree[2 * i + 1]

    def add(self, index: int, delta: int) -> None:
        if not (0 <= index < self.n):
            raise IndexError("Invalid index")
        i = self.size + index
        self.tree[i] += delta
        i //= 2
        while i:
            self.tree[i] = self.tree[2 * i] + self.tree[2 * i + 1]
            i //= 2

    def query(self, left: int, right: int) -> int:
        if not (0 <= left <= right <= self.n):
            raise IndexError("Invalid range")
        left += self.size
        right += self.size
        answer = 0

        while left < right:
            if left & 1:
                answer += self.tree[left]
                left += 1
            if right & 1:
                right -= 1
                answer += self.tree[right]
            left //= 2
            right //= 2
        return answer
~~~

Đoạn mã cây đoạn ở đây chỉ minh họa **cập nhật điểm, truy vấn tổng**. Để hỗ trợ cập nhật đoạn trong `O(\log n)`, cần thêm các nhãn lazy và cơ chế đẩy/lưu nhãn nhất quán.

### 8.5. Kiểm tra chung và hành vi sau cập nhật

~~~python
a = [2, 1, 3, 4, 0, 5, 2, 6]

prefix = PrefixSum(a)
sparse = SparseTableMin(a)
fenwick = Fenwick(a)
segment = SegmentTreeSum(a)

assert prefix.query(2, 6) == 12
assert sparse.query(2, 6) == 0
assert fenwick.query(2, 6) == 12
assert segment.query(2, 6) == 12

# Cộng 8 vào A[4]: từ 0 thành 8.
fenwick.add(4, 8)
segment.add(4, 8)

assert fenwick.query(2, 6) == 20
assert segment.query(2, 6) == 20

# Hai cấu trúc tĩnh vẫn phản ánh dữ liệu trước cập nhật.
assert prefix.query(2, 6) == 12
assert sparse.query(2, 6) == 0
# Nếu dựng lại trên mảng mới, min [2,6) sẽ bằng 3.
~~~

Ví dụ làm rõ một điểm thường bị bỏ qua: các cấu trúc không tự động chia sẻ cập nhật. Hai lệnh `fenwick.add` và `segment.add` cập nhật hai đối tượng riêng biệt; bảng tiền tố và sparse table chỉ biết nội dung đã dùng khi xây.

## 9. Cách chọn theo từng kiểu bài toán

### Tình huống A — Báo cáo tổng trên dữ liệu đã chốt

Có một triệu số liệu theo ngày; người dùng thực hiện rất nhiều truy vấn tổng theo các khoảng nhưng không sửa dữ liệu. **Mảng tiền tố** cần `O(n)` tiền xử lý rồi mỗi truy vấn chỉ một phép trừ, phù hợp hơn việc dùng Fenwick hoặc cây đoạn với truy vấn `O(\log n)`.

### Tình huống B — Hỏi min/max trên lịch sử bất biến

Có một mảng nhiệt độ lịch sử không chỉnh sửa, cần trả lời số lượng lớn truy vấn nhiệt độ thấp nhất trên đoạn. **Sparse table** cần nhiều bộ nhớ hơn để tiền xử lý nhưng mỗi RMQ chỉ hai lần đọc bảng và một phép min, độ phức tạp `O(1)`.

### Tình huống C — Điểm số thay đổi liên tục, hỏi tổng trên khoảng

Hệ thống nhận các thay đổi điểm số từng người và hỏi tổng của một dải chỉ số. **Fenwick** là lựa chọn gọn: mỗi lần cập nhật và hỏi tổng mất `O(\log n)`. Nếu cần **gán giá trị mới**, có thể giữ thêm mảng giá trị hiện tại và cập nhật bằng `delta = new - old`.

### Tình huống D — Thay đổi dữ liệu và hỏi min/max hoặc trạng thái phức tạp

Mỗi thao tác có thể thay điểm số, rồi hỏi điểm lớn nhất trên khoảng, hoặc hỏi tổng tiền tố lớn nhất của một đoạn. **Cây đoạn** thích hợp vì có thể tự thiết kế một trạng thái nút và phép gộp kết hợp để duy trì kết quả.

### Tình huống E — Cộng hàng loạt trên đoạn

Nếu cần cộng `d` cho `[l,r)` và hỏi tổng, **hai Fenwick** là phương án hiệu quả khi chỉ có phép cộng/tổng. Nếu còn yêu cầu min/max, gán đoạn hoặc kết hợp những loại cập nhật khác, **cây đoạn lazy** thường dễ mở rộng hơn.

### Tình huống F — Miền chỉ số rất lớn nhưng thưa

Với miền gồm hàng nghìn tỷ chỉ số mà chỉ có một phần nhỏ được cập nhật, dựng các cấu trúc kích thước `O(n)` theo miền gốc có thể không khả thi. Khi đó cân nhắc **nén tọa độ** nếu biết trước các chỉ số/ràng buộc đoạn, hoặc **cây đoạn động** nếu các chỉ số xuất hiện trực tuyến. Với bài toán tổng trên khoảng sau nén tọa độ, phải bảo toàn **độ dài thật của từng khoảng**.

## 10. Những lỗi và giới hạn cần tránh

1. **Nhầm đoạn đóng với đoạn nửa mở.** Nếu truy vấn `[l,r]` trên chỉ số nguyên, cần chuyển thành `[l,r+1)` (khi `r+1` vẫn nằm trong miền biểu diễn). Không trộn quy ước.
2. **Lẫn chỉ số 0-based và 1-based trong Fenwick.** Đầu vào dùng 0-based, mảng `bit` dùng 1-based và chỉ số 0 không bao giờ được cập nhật.
3. **Dùng bảng thưa hai khối chồng nhau cho tổng.** Cách gộp này chỉ cho kết quả đúng với các phép thích hợp như min/max/gcd.
4. **Tưởng sparse table hỗ trợ cập nhật điểm nhanh.** Sau thay đổi dữ liệu, những giá trị tiền xử lý có thể không còn đúng; nếu cập nhật thường xuyên hãy xem xét cây đoạn.
5. **Đặt sai phần tử trung hòa của cây đoạn.** Với min, dùng 0 làm giá trị cho đoạn không giao có thể làm sai kết quả khi mọi phần tử dương. Hãy dùng `+∞` hoặc một quy ước tương đương phù hợp.
6. **Áp dụng BIT cộng/tổng trực tiếp cho min/max động.** Phép min không có phép trừ tiền tố; cần thuật toán khác hoặc điều kiện cập nhật riêng.
7. **Bỏ qua giới hạn số nguyên.** Tổng đoạn có thể vượt kiểu số nguyên 32-bit ở các ngôn ngữ có kiểu cố định; chọn 64-bit hoặc kiểu rộng hơn nếu cần.
8. **Giả định các phần tử phải dương.** Prefix sum, Fenwick tổng và cây đoạn tổng vẫn hoạt động khi phần tử hoặc lượng cập nhật âm. Nhưng các bài toán *tìm chỉ số bằng prefix sum tăng dần* cần thêm giả thiết (chẳng hạn tần suất không âm).
9. **Đánh giá chỉ một truy vấn.** Độ phức tạp tổng thể còn phụ thuộc số truy vấn `q` và số cập nhật `u`: với mảng tĩnh, prefix tốn `O(n+q)` cho tổng; với Fenwick, tổng chi phí điển hình là `O(n+(q+u)\log n)`.

## 11. Bài luyện tập có định hướng

**Bài 1 — Chọn cấu trúc.** Với mỗi trường hợp sau, chọn một trong bốn công cụ và giải thích theo loại truy vấn, tần suất cập nhật và bộ nhớ:

- 500.000 giá trị bất biến; 2.000.000 truy vấn tổng đoạn.
- 100.000 giá trị bất biến; 1.000.000 truy vấn min đoạn.
- 100.000 giá trị; xen kẽ 200.000 lần cộng điểm và hỏi tổng.
- 100.000 giá trị; xen kẽ gán điểm và hỏi min đoạn.

*Gợi ý đáp án:* lần lượt là mảng tiền tố, sparse table, Fenwick và cây đoạn.

**Bài 2 — Tính tay.** Cho `A=[3,1,4,1,5,9]`. Lập `P` và tính tổng `[1,5)`. Sau đó cộng `2` tại chỉ số 3 và cho biết những ô `P` cần cập nhật nếu vẫn dùng mảng tiền tố.

*Đáp án kiểm tra:* `P=[0,3,4,8,9,14,23]`; tổng ban đầu `1+4+1+5=11`. Sau cập nhật, các `P[i]` với `i\ge 4` tăng 2.

**Bài 3 — Truy vết Fenwick.** Với `n=8`, hãy liệt kê các ô BIT được cập nhật khi gọi `add(2,5)` (chỉ số ngoài 0-based). Hãy liệt kê các ô được đọc khi gọi `prefix(7)`.

*Đáp án kiểm tra:* cập nhật tại ô 3, 4, 8; đọc ô 7, 6, 4.

**Bài 4 — Giải thích điều kiện lũy đẳng.** Cho `A=[8,2,7,3,6]` và đoạn `[0,5)`. Hãy chỉ ra hai khối dài 4 dùng trong sparse table. Vì sao lấy min của chúng đúng, còn cộng tổng của hai khối thì sai?

**Bài 5 — Kiểm chứng cài đặt.** Sinh mảng nhỏ với cả số âm, so sánh mọi truy vấn tổng `[l,r)` của PrefixSum, Fenwick, SegmentTreeSum với kết quả `sum(A[l:r])`. Sau các lần cập nhật điểm ngẫu nhiên, chỉ kiểm tra Fenwick và SegmentTreeSum với mảng gốc đã cập nhật; kiểm tra SparseTableMin bằng `min(A[l:r])` khi chưa có cập nhật.

## 12. Ghi nhớ khi thiết kế

Cách chọn có thể bắt đầu bằng ba câu hỏi: **có cập nhật không; phép gộp là gì; cập nhật trên điểm hay cả đoạn?** Nếu dữ liệu tĩnh và cần tổng, chọn mảng tiền tố; nếu tĩnh và cần min/max, chọn sparse table; nếu có cập nhật điểm và cần tổng, Fenwick thường gọn nhất; nếu cần cập nhật cùng truy vấn linh hoạt, chọn cây đoạn. Với cập nhật đoạn, xem xét biến thể hai BIT hoặc cây đoạn lazy. Việc hiểu **bất biến**, **tính kết hợp**, **phép nghịch đảo** và **tính lũy đẳng** giúp giải thích được vì sao mỗi cấu trúc làm tốt những việc khác nhau, thay vì chỉ ghi nhớ bảng độ phức tạp.
