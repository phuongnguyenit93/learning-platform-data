# Tính kết hợp, phần tử đơn vị, phép nghịch đảo và tính lũy đẳng

Trong truy vấn đoạn (*range query*), ta thường nhận một dãy `a` rồi hỏi tổng, giá trị nhỏ nhất, lớn nhất, XOR hoặc một dạng tổng hợp trên các phần tử **liên tiếp**. Hai cấu trúc dữ liệu cùng trả lời truy vấn đoạn có thể khác nhau rất lớn về cách hoạt động: **prefix sum** trừ hai tiền tố; **segment tree** ghép kết quả của các đoạn con; **sparse table** có thể ghép cả hai đoạn **chồng lấn**.

Sự khác biệt không nằm ở tên cấu trúc mà nằm ở **tính chất đại số của phép gộp**:

- **Tính kết hợp (associativity):** cho phép đổi cách **đặt ngoặc** khi gộp các phần liên tiếp.
- **Phần tử đơn vị (identity):** cho phép biểu diễn một **đoạn rỗng** mà không làm đổi kết quả.
- **Phép nghịch đảo (inverse):** trong cấu trúc thích hợp, cho phép **khử một tiền tố** khỏi tiền tố lớn hơn.
- **Tính lũy đẳng (idempotence):** cho phép gộp lại cùng một kết quả mà **không thay đổi giá trị**, hữu ích với những đoạn chồng lấn.

Bài thuộc chương **Truy vấn đoạn** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Lộ trình mô-đun xây dựng nền tảng về mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị; trọng tâm là **bất biến**, **thao tác** và **độ phức tạp thời gian/bộ nhớ** để chọn cấu trúc phù hợp với bài toán. Ở đây, ta xuất phát từ hợp đồng truy vấn, kiểm tra từng tính chất, sau đó giải thích vì sao các thuật toán truy vấn đoạn đúng hoặc sai.

## 1. Mô hình truy vấn đoạn và quy ước sử dụng

Xét mảng có `n` phần tử:

```text
a = [a[0], a[1], ..., a[n-1]]
```

Trong toàn bài, trừ khi nêu khác đi, ta dùng **chỉ số bắt đầu từ 0 và đoạn nửa mở `[l,r)`**:

```text
0 <= l <= r <= n

a[l:r] = các phần tử a[l], a[l+1], ..., a[r-1]
```

Đoạn `[l,l)` là **rỗng** và có độ dài 0; `[0,n)` là toàn bộ mảng. Nếu đề bài dùng đoạn đóng 1-based `[L,R]`, phải đổi thành `[L-1,R)` trước khi dùng API nội bộ.

Với phép toán nhị phân `⊕` trên miền giá trị `S`, ta muốn định nghĩa:

```text
Q(l,r) = a[l] ⊕ a[l+1] ⊕ ... ⊕ a[r-1]
```

Ví dụ:

```text
Chỉ số:   0   1   2   3   4   5
Giá trị:  4  -1   7   2   9   3

[2,5) có phần tử [7,2,9]
sum([2,5)) = 18
min([2,5)) = 2
max([2,5)) = 9
```

Các phép tính trên có thể cùng nhìn vào một đoạn nhưng **không cho phép tối ưu theo cùng một cách**.

### Ba câu hỏi trước khi chọn cấu trúc

1. **Đầu ra là gì?** Một số, một chuỗi, một ma trận, hay bộ thống kê?
2. **Phép gộp hai đoạn con có đúng không?** Kết quả của `[l,m)` và `[m,r)` có thể kết hợp thành kết quả `[l,r)`?
3. **Cần những thao tác nào?** Chỉ truy vấn tĩnh, cập nhật điểm, cập nhật đoạn, hay cả ba?

Bài này tập trung vào câu hỏi thứ hai. Câu trả lời chính xác quyết định khi nào có thể dùng prefix, segment tree, sparse table và cách xử lý đoạn rỗng.

## 2. Tính kết hợp: được thay đổi ngoặc, không được tự ý đổi thứ tự

Phép `⊕` trên `S` có **tính kết hợp** nếu với mọi `x,y,z` trong miền:

```text
(x ⊕ y) ⊕ z = x ⊕ (y ⊕ z)
```

Ví dụ, phép cộng số nguyên có tính kết hợp:

```text
(4 + 7) + 2 = 4 + (7 + 2) = 13
```

Phép lấy min, max, gcd, XOR, AND, OR bit và phép ghép chuỗi cũng có tính kết hợp khi miền và phép toán được xác định thích hợp.

### Vì sao cần tính kết hợp trong truy vấn đoạn?

Một cấu trúc như segment tree không quét từng phần tử theo một chuỗi ngoặc cố định. Nó lưu kết quả đã gộp của nhiều đoạn con:

```text
Đoạn [0,6)
       /    \
   [0,3)   [3,6)
    /  \     /   \
 ...
```

Kết quả ở nút cha được tính:

```text
value([l,r)) = value([l,m)) ⊕ value([m,r))
```

Do tính kết hợp, cách chia đoạn thành các nhóm **không làm thay đổi kết quả**. Không có tính kết hợp, kết quả có thể phụ thuộc hình dạng cây.

### Phản ví dụ: phép trừ không kết hợp

```text
(10 - 4) - 2 = 4
10 - (4 - 2) = 8
```

Bởi vậy, không được xây một cây gộp “phép trừ” rồi giả định bất kỳ cách chia đoạn nào cũng tương đương với phép trừ từ trái sang phải.

Một phép tính có thứ tự ngoặc cố định vẫn có thể lập trình được, nhưng **hợp đồng của phép gộp phải mã hóa đủ thông tin** để phép kết hợp tại các đoạn con là đúng.

### Tính kết hợp không phải tính giao hoán

Phép `⊕` **giao hoán** (*commutative*) nếu:

```text
x ⊕ y = y ⊕ x
```

Hai tính chất này khác nhau. Ghép chuỗi là ví dụ:

```text
("ab" + "cd") + "ef" = "ab" + ("cd" + "ef") = "abcdef"

"ab" + "cd" = "abcd"
"cd" + "ab" = "cdab"
```

Ghép chuỗi **kết hợp**, nhưng **không giao hoán**.

**Hệ quả cho truy vấn đoạn:** có thể gộp `Q(l,m) ⊕ Q(m,r)`, nhưng không được tùy ý đảo thành `Q(m,r) ⊕ Q(l,m)`. Thứ tự trái–phải phải được bảo toàn nếu phép gộp không giao hoán.

## 3. Phần tử đơn vị: giá trị đại diện cho đoạn rỗng

Một phần tử `e` là **đơn vị hai phía** của `⊕` nếu với mọi `x`:

```text
e ⊕ x = x
x ⊕ e = x
```

Nhờ vậy, ta có thể định nghĩa:

```text
Q(l,l) = e
```

và công thức ghép đoạn vẫn đúng khi một bên rỗng:

```text
Q(l,r) = Q(l,l) ⊕ Q(l,r)
       = e ⊕ Q(l,r)
       = Q(l,r)
```

### Ví dụ những phần tử đơn vị

| Phép toán | Miền/giả định | Đơn vị `e` | Kiểm tra |
|---|---|---|---|
| Cộng | Số nguyên | `0` | `0+x=x` |
| Nhân | Số | `1` | `1*x=x` |
| XOR bit | Số nguyên | `0` | `x xor 0=x` |
| AND bit | Số nguyên không âm có `b` bit | Mặt nạ `2^b-1` | `x AND mask=x` |
| OR bit | Số không âm | `0` | `x OR 0=x` |
| Min | Số có mở rộng `+∞` | `+∞` | `min(+∞,x)=x` |
| Max | Số có mở rộng `-∞` | `-∞` | `max(-∞,x)=x` |
| GCD | Số nguyên không âm | `0` | `gcd(0,x)=x` |
| Ghép chuỗi | Chuỗi | `""` | `""+x=x+""=x` |
| Nối danh sách | Danh sách | Danh sách rỗng | Nối với rỗng không đổi |

**Đơn vị phải thuộc miền được chọn.** Ví dụ `+∞` không thuộc tập số nguyên hữu hạn; khi dùng min trên số nguyên hữu hạn, ta phải **mở rộng miền** hoặc có cách biểu diễn đoạn rỗng riêng.

### Đơn vị khác phần tử hấp thụ

Một phần tử `z` gọi là **hấp thụ** nếu `z ⊕ x = z = x ⊕ z`. Nó không phải là đơn vị chỉ vì kết quả dễ nhận ra.

Ví dụ:

```text
Cộng:          0 là đơn vị.
Nhân:          0 là hấp thụ, 1 là đơn vị.
Min:          +∞ là đơn vị, -∞ là hấp thụ trong miền mở rộng.
AND Boolean:   True là đơn vị, False là hấp thụ.
OR Boolean:    False là đơn vị, True là hấp thụ.
```

Nhầm phần tử đơn vị với phần tử hấp thụ là lỗi thường gặp khi viết base case hoặc khởi tạo nút padding trong segment tree.

### Có thể cấm đoạn rỗng ở API công khai

Mặc dù `min(+∞,x)=x` cho phép dùng `+∞` làm đơn vị trong thuật toán, một API `range_min(l,r)` vẫn có thể **báo lỗi khi `l=r`**, vì người dùng mong một giá trị thật trong đoạn. Cần phân biệt **đơn vị nội bộ** với **hợp đồng trả kết quả cho đoạn rỗng**.

## 4. Monoid: tính kết hợp cộng với đơn vị

Một tập `S` cùng phép `⊕` và phần tử `e` tạo thành **monoid** khi:

1. **Đóng:** gộp hai phần tử thuộc `S` cho kết quả vẫn thuộc `S`.
2. **Kết hợp:** `(x⊕y)⊕z=x⊕(y⊕z)`.
3. **Có đơn vị:** `e⊕x=x⊕e=x`.

Ta không bắt buộc phép toán giao hoán hoặc có nghịch đảo.

Ví dụ monoid:

- Số nguyên với phép cộng và đơn vị 0.
- Chuỗi với phép nối và đơn vị chuỗi rỗng.
- Số nguyên không âm với phép min, nếu thêm ký hiệu `+∞` làm đơn vị.
- Các bộ `(sum,count)` với phép cộng từng thành phần, đơn vị `(0,0)`.

### Vì sao monoid là hợp đồng của segment tree?

Một nút segment tree lưu kết quả tổng hợp của một đoạn. Nếu hai đoạn liên tiếp không chồng lấn là `A` rồi `B`, nút cha lưu:

```text
aggregate(A + B) = aggregate(A) ⊕ aggregate(B)
```

Tính kết hợp cho phép ghép các nhóm theo nhiều hình dạng cây. Đơn vị giúp biểu diễn những đoạn trống, nút padding và những tích lũy ban đầu chưa có dữ liệu.

Với mọi `l <= m <= r`, hai đoạn kề nhau `[l,m)` và `[m,r)` hợp thành `[l,r)` theo đúng thứ tự:

```text
Q(l,r) = Q(l,m) ⊕ Q(m,r)
```

Đẳng thức này dựa trên **tính kết hợp và quy ước ghép trái trước phải**, không yêu cầu giao hoán.

**Không cần nghịch đảo** để làm việc này: min/max, ghép chuỗi và nhiều phép khác đều có thể dùng segment tree dù không có cách “trừ” một kết quả tiền tố.

### Phần tử đơn vị có thể là một kiểu trạng thái

Nếu một miền không có đơn vị tự nhiên, có thể dùng bản tóm tắt bổ sung cờ `empty`:

```text
EMPTY ⊕ X = X
X ⊕ EMPTY = X
```

Nhưng đây là **thiết kế miền dữ liệu mới**, không phải tự động tìm ra đơn vị trong miền gốc. Ví dụ trả min trên đoạn rỗng có thể dùng `None` làm trạng thái “không có dữ liệu”, đồng thời quy định phép gộp xử lý trạng thái ấy rõ ràng.

## 5. Phép nghịch đảo: khử một phần kết quả

Với monoid `(S,⊕,e)`, phần tử `x` có **nghịch đảo hai phía** `x⁻¹` nếu:

```text
x⁻¹ ⊕ x = e
x ⊕ x⁻¹ = e
```

Ví dụ:

- Phép cộng trên **số nguyên**: nghịch đảo của `x` là `-x`.
- Phép XOR bit: mỗi `x` là nghịch đảo của chính nó vì `x xor x=0`.
- Phép nhân trên **số hữu tỉ khác 0**: nghịch đảo của `x` là `1/x`.
- Hoán vị với phép hợp thành: nghịch đảo là hoán vị đảo, và phép hợp thành **không nhất thiết giao hoán**.

Không phải monoid nào cũng có nghịch đảo cho **mọi** phần tử.

### Nhóm (group) là gì?

Một **group** gồm phép kết hợp, phần tử đơn vị và **nghịch đảo cho mọi phần tử của miền**, với tính đóng. Nếu phép toán còn giao hoán, ta có **nhóm giao hoán (abelian group)**.

| Miền và phép toán | Có đơn vị? | Mọi phần tử có nghịch đảo? | Nhận xét |
|---|---|---|---|
| `(ℤ,+)` | Có, 0 | Có, `-x` | Nhóm giao hoán |
| `(ℕ,+)` | Có, 0 | **Không trong ℕ** | Muốn trừ có thể mở sang ℤ |
| Số nguyên với nhân | Có, 1 | Không, ví dụ 0 và 2 | Không phải group |
| Số hữu tỉ khác 0 với nhân | Có, 1 | Có, `1/x` | Group |
| XOR các bit-vector cùng độ dài | Có, 0 | Có, mỗi phần tử tự nghịch đảo | Nhóm giao hoán |
| Min với `+∞` | Có | **Không** | Không thể khử min tiền tố |
| Ghép chuỗi | Có, chuỗi rỗng | **Không** | Kết hợp nhưng không nghịch đảo tổng quát |

**Điểm tinh tế:** một phép có thể cho phép khử trên một **miền lớn hơn** mà không cho phép khử trong miền ban đầu. Ví dụ cộng các số không âm tạo monoid; để lấy hiệu hai tổng tiền tố, ta thực hiện phép trừ trong số nguyên hoặc số thực thích hợp.

## 6. Từ nghịch đảo đến truy vấn đoạn bằng prefix

Cho một dãy trong group `(S,⊕,e)`. Định nghĩa các tiền tố:

```text
P[0] = e
P[i+1] = P[i] ⊕ a[i]
```

Với đoạn `[l,r)`, gọi:

```text
R = a[l] ⊕ ... ⊕ a[r-1]
```

Do tính kết hợp và thứ tự trái–phải:

```text
P[r] = P[l] ⊕ R
```

Nhân/gộp **nghịch đảo của P[l] ở bên trái** hai vế:

```text
P[l]⁻¹ ⊕ P[r]
= P[l]⁻¹ ⊕ (P[l] ⊕ R)
= (P[l]⁻¹ ⊕ P[l]) ⊕ R
= e ⊕ R
= R
```

Vậy công thức tổng quát là:

```text
Q(l,r) = inverse(P[l]) ⊕ P[r]
```

Đối với **cộng**, `inverse(x)=-x` nên:

```text
sum([l,r)) = P[r] - P[l]
```

Đối với **XOR**, nghịch đảo là chính nó nên:

```text
xor([l,r)) = P[l] xor P[r]
```

### Thứ tự phép nghịch đảo đặc biệt quan trọng

Trong một group **không giao hoán**, `inverse(P[l]) ⊕ P[r]` không thể tự ý đảo thành `P[r] ⊕ inverse(P[l])`. Công thức đúng phụ thuộc định nghĩa tiền tố **tích từ trái sang phải**.

Đây là lý do không được suy rằng “có nghịch đảo” đồng nghĩa “thứ tự ghép không quan trọng”.

### Đoạn rỗng

Khi `l=r`:

```text
Q(l,l) = inverse(P[l]) ⊕ P[l] = e
```

Bởi vậy, công thức prefix xử lý đoạn rỗng một cách tự nhiên.

## 7. Python: prefix tổng và prefix XOR

Trước tiên, dùng một hàm kiểm tra biên để tránh Python slicing âm hoặc đoạn bị đảo biên:

```python
def validate_range(n, l, r):
    if type(l) is not int or type(r) is not int:
        raise TypeError("Chỉ số biên phải là số nguyên")
    if not 0 <= l <= r <= n:
        raise IndexError("Đoạn [l,r) không hợp lệ")


class PrefixSum:
    def __init__(self, values):
        self._data = tuple(values)
        self._prefix = [0]

        for value in self._data:
            self._prefix.append(self._prefix[-1] + value)

    def query(self, l, r):
        validate_range(len(self._data), l, r)
        return self._prefix[r] - self._prefix[l]


a = [4, -1, 7, 2, 9, 3]
sum_query = PrefixSum(a)

assert sum_query.query(2, 5) == 18
assert sum_query.query(0, 6) == 24
assert sum_query.query(3, 3) == 0
assert sum_query.query(6, 6) == 0
```

Với XOR:

```python
class PrefixXor:
    def __init__(self, values):
        self._data = tuple(values)
        self._prefix = [0]

        for value in self._data:
            self._prefix.append(self._prefix[-1] ^ value)

    def query(self, l, r):
        validate_range(len(self._data), l, r)
        return self._prefix[l] ^ self._prefix[r]


xor_query = PrefixXor([5, 3, 7, 2])

assert xor_query.query(1, 4) == (3 ^ 7 ^ 2) == 6
assert xor_query.query(0, 4) == (5 ^ 3 ^ 7 ^ 2)
assert xor_query.query(2, 2) == 0
```

**Chi phí:** xây `n+1` giá trị tiền tố trong O(n) thời gian/bộ nhớ và trả truy vấn trong O(1), nếu phép gộp/nghịch đảo trên một giá trị có chi phí hằng số.

**Điều kiện tĩnh:** dữ liệu được sao chép thành `tuple` trong ví dụ. Sau khi tạo prefix, cập nhật một phần tử của dữ liệu gốc không tự thay đổi tiền tố. Muốn dùng cho dữ liệu động, cần cập nhật/rebuild bảng hoặc chọn cấu trúc khác.

### Vì sao không có công thức tương tự cho min?

Với:

```text
a = [1, 9, 5]
b = [1, 7, 8]
```

Các prefix min (không tính đơn vị `+∞`) đều là:

```text
[1,1,1]
```

Nhưng:

```text
min(a[1:3]) = 5
min(b[1:3]) = 7
```

Chỉ từ min tiền tố, ta **không khử được** phần tử `1` phía trước để biết min của phần đuôi. Không có phép nghịch đảo tổng quát cho min.

## 8. Prefix trong group không giao hoán: hoán vị

Để thấy rõ **nghịch đảo không yêu cầu giao hoán**, xét các hoán vị trên tập `{0,1,2}`. Một hoán vị được biểu diễn bằng tuple `p`, trong đó `p[i]` là ảnh của `i`.

Định nghĩa phép gộp:

```text
compose(p,q)(i) = p(q(i))
```

Phép hợp thành hoán vị có tính kết hợp, có đơn vị `(0,1,2)`, có nghịch đảo, nhưng **không giao hoán nói chung**.

```python
IDENTITY3 = (0, 1, 2)


def compose(p, q):
    """Thực hiện q trước, rồi p."""
    return tuple(p[q[i]] for i in range(3))


def inverse_perm(p):
    inv = [None] * 3
    for i, mapped in enumerate(p):
        inv[mapped] = i
    return tuple(inv)


def group_prefix(values, identity, op):
    prefix = [identity]
    for value in values:
        prefix.append(op(prefix[-1], value))
    return prefix


def group_range_query(prefix, l, r, op, inverse):
    validate_range(len(prefix) - 1, l, r)
    return op(inverse(prefix[l]), prefix[r])


p = (1, 0, 2)  # Đổi chỗ 0 và 1.
q = (0, 2, 1)  # Đổi chỗ 1 và 2.
r = (2, 1, 0)  # Đổi chỗ 0 và 2.

assert compose(p, q) != compose(q, p)
assert compose(p, IDENTITY3) == p
assert compose(inverse_perm(p), p) == IDENTITY3

prefix = group_prefix([p, q, r], IDENTITY3, compose)

assert group_range_query(
    prefix, 1, 3, compose, inverse_perm
) == compose(q, r)
assert group_range_query(
    prefix, 2, 2, compose, inverse_perm
) == IDENTITY3
```

Đoạn mã này dùng hoán vị **đúng ba phần tử**, đủ để minh họa toán học. Với hoán vị kích thước `m`, một phép hợp thành/nghịch đảo tốn O(m), nên truy vấn trên tiền tố cũng không còn O(1) tính theo `m` nếu `m` là biến đầu vào. Độ phức tạp O(1) mỗi truy vấn chỉ đúng khi **chi phí một phép toán group được coi là O(1)**.

### Bài học từ ví dụ hoán vị

Ta có thể dùng prefix ngay cả với phép toán **không giao hoán**, miễn là:

- Có tính kết hợp.
- Có đơn vị.
- Có nghịch đảo thích hợp.
- Giữ **đúng thứ tự** khi xây và khử.

Công thức `inverse(P[l]) ⊕ P[r]` là quan hệ chính xác cho cách định nghĩa prefix của bài.

## 9. Tính lũy đẳng: gộp lại chính mình không đổi

Phép `⊕` có tính **lũy đẳng (idempotent)** khi:

```text
x ⊕ x = x
```

với mọi `x` trong miền.

Ví dụ:

```text
min(5,5) = 5
max(5,5) = 5
gcd(6,6) = 6               (với số nguyên không âm)
5 AND 5 = 5
5 OR 5 = 5
```

Ngược lại:

```text
5 + 5 = 10       != 5
5 xor 5 = 0     != 5
"ab" + "ab" = "abab" != "ab"
```

Vì vậy, tổng, XOR và nối chuỗi **không lũy đẳng** nói chung.

### Tính lũy đẳng có nghĩa gì đối với các đoạn chồng lấn?

Nếu đã tính một kết quả `x` cho một vùng dữ liệu, gộp lại **chính kết quả x** sẽ không đổi. Nhờ đó, đối với phép **kết hợp và lũy đẳng**, việc một **khối liên tiếp** xuất hiện hai lần trong hai đoạn chồng lấn có thể được khử ở mức kết quả của khối ấy.

**Đây không phải tính nghịch đảo.** Lũy đẳng cho phép **lặp lại không ảnh hưởng** trong cách gộp thích hợp; nghịch đảo cho phép **hủy một phần kết quả** để lấy phần còn lại. Hai khả năng hoàn toàn khác nhau.

### Min/Max/GCD và miền xác định

- Min và max lũy đẳng trên một miền có thứ tự phù hợp.
- GCD thường xét **số nguyên không âm**, vì `gcd(x,x)=x` trên miền ấy. Với số nguyên âm, `gcd(-6,-6)=6` không bằng `-6`.
- AND/OR bit trên các bit-vector cùng độ dài đều lũy đẳng.
- Với `NaN` trong dữ liệu số thực, các quy tắc so sánh/min có thể phụ thuộc cách cài đặt; phải xác định chính sách xử lý giá trị không hợp lệ.

## 10. Tính lũy đẳng không đồng nghĩa tính giao hoán

Về mặt logic, hai phát biểu độc lập:

```text
Giao hoán:       x ⊕ y = y ⊕ x
Lũy đẳng:        x ⊕ x = x
```

Phép cộng là **giao hoán nhưng không lũy đẳng**. Có phép **lũy đẳng nhưng không giao hoán**; ví dụ phép chọn toán hạng trái:

```text
x ⊕ y = x
```

Khi đó:

```text
x ⊕ x = x                 (lũy đẳng)
(x ⊕ y) ⊕ z = x            (kết hợp)
x ⊕ y = x, y ⊕ x = y       (không giao hoán nếu x != y)
```

Phép chọn trái tự nó **không có đơn vị hai phía** trên miền nhiều hơn một phần tử, nhưng ví dụ đủ để phân biệt các tính chất.

Một phép vừa **kết hợp, giao hoán, lũy đẳng** thường được xem là phép gộp của một **bán dàn (semilattice)** theo quan hệ thứ tự tương ứng; min/max là những ví dụ quen thuộc. Bài truy vấn đoạn không bắt buộc người học nhớ tên trừu tượng này, nhưng cần nhận ra tính lũy đẳng để biết khi nào **được phép dùng đoạn chồng lấn**.

## 11. Sparse table: ứng dụng trực tiếp của tính lũy đẳng

Với mảng **tĩnh** và phép gộp **kết hợp, lũy đẳng**, *sparse table* có thể trả truy vấn đoạn không rỗng trong **O(1)** thời gian sau bước tiền xử lý O(n log n).

Ý tưởng:

```text
st[k][i] = kết quả gộp đoạn [i, i + 2^k)
```

Xây từ các khối ngắn hơn:

```text
st[0][i] = a[i]

st[k][i] = st[k-1][i] ⊕ st[k-1][i + 2^(k-1)]
```

Hai nửa này **kề nhau, không chồng lấn**, nên tính kết hợp là đủ cho bước xây.

### Trả lời truy vấn bằng hai khối có thể chồng lấn

Cho đoạn không rỗng `[l,r)`, độ dài `len=r-l`. Đặt:

```text
k = floor(log2(len))
s = 2^k
```

Lấy hai khối độ dài `s`:

```text
Khối trái:  [l, l+s)
Khối phải:  [r-s, r)
```

Do `s <= len < 2s`, hai khối phủ toàn bộ đoạn truy vấn, nhưng **có thể chồng lấn**.

Ví dụ:

```text
a = [5, 2, 6, 3, 1, 7, 4, 8]
Query [1,7) có 6 phần tử.

k = floor(log2(6)) = 2
s = 4

Khối trái  [1,5): [2,6,3,1]
Khối phải  [3,7): [3,1,7,4]

Vùng chồng lấn: [3,5) = [3,1]
```

Truy vấn min:

```text
min([1,7))
  = min(min([1,5)), min([3,7)))
  = min(1,1)
  = 1
```

Vì **min lũy đẳng**, hai phần tử trong vùng chồng lấn không làm sai kết quả.

### Vì sao tổng không dùng cách này được?

Với cùng ví dụ:

```text
sum([1,7)) = 2+6+3+1+7+4 = 23

sum([1,5)) = 2+6+3+1 = 12
sum([3,7)) = 3+1+7+4 = 15

12 + 15 = 27   (SAI)
```

Các giá trị ở vị trí 3 và 4 đã bị **cộng hai lần**, tổng dư `3+1=4`. Phép cộng **không lũy đẳng**, nên sparse table với **hai khối chồng lấn** không thể dùng nguyên xi cho tổng.

**Lưu ý:** điều này không có nghĩa **mọi** cấu trúc tiền xử lý tĩnh O(1) cho phép kết hợp đều cần lũy đẳng. Có các biến thể như **disjoint sparse table** dùng những khối **không chồng lấn** cho phép kết hợp tổng quát. Tính lũy đẳng là điều kiện quan trọng đối với **cách truy vấn hai khối phủ chồng lấn nêu ở đây**.

## 12. Python: sparse table cho phép kết hợp và lũy đẳng

Hàm sau nhận phép `op` từ người gọi, nhưng **hợp đồng của nó yêu cầu op vừa kết hợp vừa lũy đẳng**. Không có cơ chế tự chứng minh hai tính chất từ một hàm Python tùy ý.

```python
class IdempotentSparseTable:
    def __init__(self, values, op):
        self.n = len(values)
        self.op = op
        self.table = [list(values)]

        level = 1
        while (1 << level) <= self.n:
            half = 1 << (level - 1)
            width = 1 << level
            previous = self.table[-1]

            current = [
                op(previous[i], previous[i + half])
                for i in range(self.n - width + 1)
            ]
            self.table.append(current)
            level += 1

    def query(self, l, r):
        validate_range(self.n, l, r)
        if l == r:
            raise ValueError("Sparse table này yêu cầu đoạn không rỗng")

        k = (r - l).bit_length() - 1
        width = 1 << k
        return self.op(
            self.table[k][l],
            self.table[k][r - width],
        )


a = [5, 2, 6, 3, 1, 7, 4, 8]
rmq = IdempotentSparseTable(a, min)
rmax = IdempotentSparseTable(a, max)

assert rmq.query(1, 7) == 1
assert rmq.query(1, 3) == 2
assert rmq.query(0, 8) == 1
assert rmax.query(1, 7) == 7

try:
    rmq.query(3, 3)
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối đoạn min rỗng")
```

**Độ phức tạp** với phép gộp O(1):

- Xây bảng cho các độ dài `1,2,4,8,...`: **O(n log n)** thời gian/bộ nhớ.
- Mỗi truy vấn không rỗng: **O(1)**, dùng hai ô bảng và một phép gộp.
- Không có cơ chế cập nhật động trong phiên bản này; thay đổi mảng có thể khiến bảng lỗi thời, cần xây lại hoặc thiết kế khác.

### Có cần đơn vị cho cách truy vấn này không?

Truy vấn ở trên **không nhận đoạn rỗng**, nên không cần `identity` ở hàm `query`. Với một segment tree cho min, người ta thường thêm `+∞` làm đơn vị để gộp các nhánh rỗng. Đây là **khác biệt của thiết kế API**, không mâu thuẫn về mặt toán học.

## 13. Segment tree: tính kết hợp và đơn vị là đủ

Khác sparse table dùng hai khối có thể chồng lấn, **segment tree** chia một đoạn thành các đoạn con **không giao nhau**. Khi truy vấn, thuật toán ghép những đoạn được chọn theo thứ tự.

Vì vậy, với phép gộp `⊕`:

- Cần **tính kết hợp** để cách chia/ngoặc không làm đổi kết quả.
- Có **đơn vị** để khởi tạo tích lũy và xử lý nhánh không có phần tử.
- **Không yêu cầu nghịch đảo**.
- **Không yêu cầu lũy đẳng**.
- **Không yêu cầu giao hoán**, miễn là giữ đúng thứ tự các đoạn.

Ví dụ:

```text
sum:           kết hợp +, đơn vị 0
min:           kết hợp min, đơn vị +∞ (miền mở rộng)
max:           kết hợp max, đơn vị -∞
string concat: kết hợp nối, đơn vị ""
```

### Hai tích lũy để giữ đúng thứ tự

Với segment tree lặp, khi duyệt từ hai đầu của `[l,r)`, thường dùng:

```text
left_acc  = e
right_acc = e

Khi lấy một khối từ phía trái:
    left_acc = left_acc ⊕ block

Khi lấy một khối từ phía phải:
    right_acc = block ⊕ right_acc

Kết quả = left_acc ⊕ right_acc
```

Nếu dùng `right_acc = right_acc ⊕ block`, ta có thể đảo thứ tự các khối ở phía phải, gây sai với phép **không giao hoán** như nối chuỗi.

## 14. Python: segment tree tổng quát cho monoid

Đây là một triển khai đơn giản dùng kích thước lá làm tròn lên lũy thừa của 2. Các ô padding nhận **đơn vị** nên không làm đổi kết quả.

```python
class MonoidSegmentTree:
    def __init__(self, values, op, identity):
        self.n = len(values)
        self.op = op
        self.identity = identity

        size = 1
        while size < self.n:
            size *= 2
        self.size = size

        self.tree = [identity] * (2 * size)
        for i, value in enumerate(values):
            self.tree[size + i] = value

        for i in range(size - 1, 0, -1):
            self.tree[i] = op(
                self.tree[2 * i],
                self.tree[2 * i + 1],
            )

    def query(self, l, r):
        validate_range(self.n, l, r)

        l += self.size
        r += self.size
        left_acc = self.identity
        right_acc = self.identity

        while l < r:
            if l & 1:
                left_acc = self.op(left_acc, self.tree[l])
                l += 1

            if r & 1:
                r -= 1
                right_acc = self.op(self.tree[r], right_acc)

            l //= 2
            r //= 2

        return self.op(left_acc, right_acc)

    def point_assign(self, i, value):
        if type(i) is not int or not 0 <= i < self.n:
            raise IndexError("Chỉ số cập nhật không hợp lệ")

        position = self.size + i
        self.tree[position] = value
        position //= 2

        while position >= 1:
            self.tree[position] = self.op(
                self.tree[2 * position],
                self.tree[2 * position + 1],
            )
            position //= 2


sum_tree = MonoidSegmentTree([4, -1, 7, 2, 9, 3], lambda x,y: x+y, 0)

assert sum_tree.query(2, 5) == 18
assert sum_tree.query(3, 3) == 0

sum_tree.point_assign(3, 10)
assert sum_tree.query(2, 5) == 26

words = MonoidSegmentTree(
    ["a", "b", "c", "d", "e"],
    lambda x,y: x+y,
    "",
)

assert words.query(1, 4) == "bcd"
assert words.query(0, 5) == "abcde"
assert words.query(2, 2) == ""

words.point_assign(2, "XY")
assert words.query(1, 4) == "bXYd"
```

**Vì sao ví dụ chuỗi quan trọng?** Phép nối **không giao hoán**; nếu mã xây/truy vấn đảo trái–phải thì `"bXYd"` có thể biến thành chuỗi sai. Các kiểm tra với tổng số đơn thuần không phát hiện được lỗi thứ tự đó.

**Chi phí:** xây O(n), bộ nhớ O(n), truy vấn O(log n), cập nhật một điểm O(log n) theo mô hình mỗi `op` O(1). Đối với nối chuỗi Python, phép `x+y` có thể sao chép toàn bộ ký tự của hai chuỗi, nên chi phí thực còn phụ thuộc **độ dài dữ liệu**; cận O(log n) ở đây đếm **số phép gộp**, không phải tự động là chi phí byte.

### Vì sao segment tree cho tổng vẫn đúng dù cộng không lũy đẳng?

Các nút được chọn để trả lời một truy vấn tạo thành **phân hoạch không chồng lấn** của `[l,r)`. Không có vùng nào được gộp hai lần. Vì thế phép cộng chỉ cần kết hợp và đơn vị; không cần tính lũy đẳng.

## 15. Một ví dụ tổng hợp không phải số: trung bình

**Trung bình cộng** của hai đoạn không thể được gộp đúng bằng cách **lấy trung bình của hai trung bình** nếu hai đoạn có số phần tử khác nhau.

Ví dụ:

```text
Đoạn trái:  [10]       -> trung bình 10, có 1 phần tử
Đoạn phải: [2, 4, 6]  -> trung bình 4, có 3 phần tử

Trung bình toàn đoạn:
(10 + 2 + 4 + 6) / 4 = 5.5

Lấy (10 + 4) / 2 = 7   (SAI)
```

Thay vì lưu riêng `average`, ta lưu **bộ `(sum,count)`**:

```text
identity = (0,0)

combine((s1,c1),(s2,c2)) = (s1+s2, c1+c2)
```

Đây là một monoid vì cộng từng thành phần là kết hợp và `(0,0)` là đơn vị.

```python
def combine_sum_count(left, right):
    return (left[0] + right[0], left[1] + right[1])


data = [10, 2, 4, 6]
summaries = [(x, 1) for x in data]

tree = MonoidSegmentTree(
    summaries,
    combine_sum_count,
    (0, 0),
)

total, count = tree.query(0, 4)
assert (total, count) == (22, 4)
assert total / count == 5.5

sub_total, sub_count = tree.query(1, 4)
assert (sub_total, sub_count) == (12, 3)
assert sub_total / sub_count == 4

empty_total, empty_count = tree.query(2, 2)
assert (empty_total, empty_count) == (0, 0)
# Không chia cho count=0 khi hỏi trung bình đoạn rỗng.
```

Cách này cho thấy có những truy vấn **không có phép gộp đơn giản trên câu trả lời cuối**, nhưng vẫn có thể xây được **bản tóm tắt đủ thông tin có phép gộp kết hợp**. Câu trả lời trung bình chỉ được tính **sau khi** gộp xong tổng và số lượng.

## 16. Một bài toán có cả lũy đẳng và nghịch đảo?

Hai tính chất không phải là hai điều kiện “càng nhiều càng tốt”. Chúng phục vụ **mục đích khác nhau**, và trên một miền có group, lũy đẳng dẫn đến kết quả rất đặc biệt.

Giả sử phép `⊕` tạo **group** với đơn vị `e`, đồng thời lũy đẳng:

```text
x ⊕ x = x
```

Gộp nghịch đảo `x⁻¹` vào bên trái:

```text
x⁻¹ ⊕ (x ⊕ x) = x⁻¹ ⊕ x
(e ⊕ x) = e
x = e
```

Do đó **mọi phần tử của group phải bằng đơn vị e**. Nói cách khác, một **group lũy đẳng** chỉ có thể là **group tầm thường một phần tử**.

Đây là lý do những phép điển hình thường chia hai nhóm:

- **Tổng/XOR:** có nghịch đảo, nhưng không lũy đẳng.
- **Min/Max/GCD:** lũy đẳng, nhưng không có nghịch đảo group tổng quát.

Kết luận này dựa trên **mọi phần tử đều có nghịch đảo** và phép toán đúng trên cùng miền. Nó không cấm một phép chỉ có một số phần tử đặc biệt vừa tự lũy đẳng vừa khả nghịch (thường chỉ đơn vị).

## 17. Tính chất cần cho các kỹ thuật khác nhau

| Kỹ thuật | Kết hợp | Đơn vị | Nghịch đảo | Lũy đẳng | Ghi chú |
|---|---|---|---|---|---|
| Quét trái sang phải theo một thứ tự ngoặc cố định | Không bắt buộc | Hữu ích cho đoạn rỗng | Không | Không | Mã tự quy định cách đặt ngoặc |
| Segment tree gộp các đoạn rời | **Có** | **Có** trong giao diện monoid | Không | Không | Giữ thứ tự nếu không giao hoán |
| Prefix với khử tiền tố | **Có** | **Có** | **Có**, trong group phù hợp | Không | Công thức `P[l]⁻¹⊕P[r]` |
| Sparse table hai khối chồng lấn | **Có** | Không bắt buộc nếu chỉ hỏi đoạn không rỗng | Không | **Có** | Min/max/gcd là ví dụ |
| Disjoint sparse table (biến thể khác) | **Có** | Theo thiết kế | Không | **Không bắt buộc** | Dùng các phần không chồng lấn |
| Mảng hiệu cộng đoạn offline | Có trên phép cộng | Có | Có phép trừ | Không | Phục hồi bằng cộng dồn |
| Fenwick tree cho cộng điểm/tổng đoạn | Có | Có | Có để khử prefix khi hỏi đoạn | Không | Trường hợp phổ biến là cộng/XOR |
| Lazy segment tree cho cập nhật đoạn | Có cho phép gộp query | Có | Không tự động | Không tự động | Cần thêm phép tác động và quy tắc hợp thành |

Bảng nêu các **hợp đồng phổ biến** để học cấu trúc dữ liệu, không khẳng định mọi biến thể chuyên biệt chỉ có đúng các điều kiện này.

### Lưu ý về Fenwick tree

Fenwick tree rất thuận tiện với tổng đoạn và cập nhật điểm. Có thể xem các phép tổng hợp trên group giao hoán là mô hình quen thuộc. Với các phép **không giao hoán** hoặc **không có nghịch đảo**, cách cài đặt/update và khả năng khử prefix cần xem xét riêng; không nên dùng ví dụ Fenwick cộng số để suy rằng mọi phép kết hợp đều hỗ trợ giống nhau.

## 18. Phép gộp truy vấn và phép cập nhật là hai tầng khác nhau

Khi chuyển từ **truy vấn tĩnh** sang **cập nhật đoạn**, tính kết hợp/đơn vị của query **chưa đủ** để triển khai lazy propagation.

Ví dụ với phép **cộng `delta` vào mọi phần tử trong một đoạn độ dài `len`**:

- Nếu nút lưu **tổng**, giá trị tổng tăng **`delta * len`**.
- Nếu nút lưu **min**, giá trị min tăng **`delta`**, vì tất cả phần tử đều cùng tăng.
- Nếu nút lưu **max**, giá trị max tăng **`delta`**.
- Nếu nút lưu **số phần tử**, giá trị này **không đổi**.

Đó là quy tắc **tác động của update lên bản tóm tắt**. Nó cần được chứng minh riêng với phép tổng hợp đã chọn.

### Hợp thành nhiều cập nhật

Hai lần cộng liên tiếp:

```text
add(delta1) rồi add(delta2)
= add(delta1 + delta2)
```

Các cập nhật cộng có thể tích lũy bằng một số.

Nhưng khi có **gán cả đoạn** và **cộng cả đoạn**:

```text
assign(5) rồi add(3)  -> giá trị cuối = 8
add(3) rồi assign(5)  -> giá trị cuối = 5
```

Thứ tự cập nhật **không thể đổi tùy ý**. Cách lưu lazy tag phải giữ đúng quy tắc hợp thành thao tác, có thể không giao hoán.

**Tính lũy đẳng của min không có nghĩa cập nhật cộng đoạn cũng lũy đẳng.** `min(x,x)=x` là tính chất của **query combine**, trong khi `add(3)` hai lần làm tăng tổng cộng 6, không phải 3.

## 19. Những giới hạn toán học và số học trong thực tế

Các tính chất ở trên được định nghĩa **chính xác** trong một miền toán học. Khi lập trình, miền số và chi phí phép toán cũng quan trọng.

### Số thực máy và sai số

Phép cộng số thực dấu phẩy động có thể **không kết hợp ở mức bit** do làm tròn:

```text
(1e16 + (-1e16)) + 1.0  -> có thể là 1.0
1e16 + ((-1e16) + 1.0)  -> có thể là 0.0
```

Vì vậy, segment tree cộng số thực có thể cho kết quả khác một chút so với cộng tuyến tính. Điều đó không phủ nhận tính kết hợp của **phép cộng số thực toán học**; nó là giới hạn của biểu diễn máy.

Nếu ứng dụng đòi kết quả bit-for-bit hoặc độ ổn định số học cao, cần định nghĩa sai số chấp nhận, quy tắc cộng hoặc dùng kiểu số thích hợp.

### Phép nhân và phép chia

Có thể viết:

```text
product([l,r)) = prefix_product[r] / prefix_product[l]
```

**chỉ khi** các phần tử/tiền tố có nghịch đảo thích hợp và phép chia đáng tin cậy. Nếu `prefix_product[l]=0`, không thể chia; số thực có thể tràn, thiếu chính xác hoặc suy biến khi tích quá lớn/nhỏ.

Không nên dùng “prefix product + chia” như lời giải tổng quát khi dữ liệu có thể chứa 0.

### Số nguyên modulo

Trong số học modulo `m`, một phần tử `x` có nghịch đảo nhân **chỉ khi `gcd(x,m)=1`**. Ví dụ modulo 8, phần tử 2 không có nghịch đảo nhân, dù phép nhân modulo 8 vẫn kết hợp và có đơn vị 1.

Với modulo nguyên tố `p`, các phần tử khác 0 có nghịch đảo nhân; nhưng 0 vẫn không có. Vì vậy, miền và ràng buộc dữ liệu phải được nêu rõ trước khi dùng công thức nghịch đảo.

### Khóa và giá trị không bình thường

Với phép min/max, nếu có `NaN` hoặc giá trị không so sánh được, cần quy ước xử lý. Một phép gộp chỉ “thường chạy đúng” chưa chắc thỏa các tính chất toán học mong muốn trên **mọi** giá trị đầu vào.

## 20. Kiểm thử tính chất bằng ví dụ nhỏ

Khi thiết kế một phép gộp mới, hãy kiểm thử:

1. **Đóng miền:** `op(x,y)` có tạo giá trị hợp lệ không?
2. **Kết hợp:** `op(op(x,y),z)==op(x,op(y,z))`.
3. **Đơn vị:** `op(e,x)==x` và `op(x,e)==x`.
4. **Nghịch đảo nếu cần:** `op(inv(x),x)==e` và `op(x,inv(x))==e`.
5. **Lũy đẳng nếu cần:** `op(x,x)==x`.
6. **Thứ tự nếu không giao hoán:** kết quả gộp các đoạn trái–phải phải đúng.

### Một bộ kiểm tra hữu hạn bằng Python

```python
from itertools import product


def check_associative(samples, op):
    return all(
        op(op(x, y), z) == op(x, op(y, z))
        for x, y, z in product(samples, repeat=3)
    )


def check_identity(samples, op, identity):
    return all(
        op(identity, x) == x and op(x, identity) == x
        for x in samples
    )


def check_idempotent(samples, op):
    return all(op(x, x) == x for x in samples)


numbers = [0, 1, 3, 7]

assert check_associative(numbers, min)
assert check_idempotent(numbers, min)
assert check_identity(numbers, min, float("inf"))

assert check_associative(numbers, lambda x,y: x+y)
assert check_identity(numbers, lambda x,y: x+y, 0)
assert not check_idempotent(numbers, lambda x,y: x+y)

assert not check_associative(
    numbers, lambda x,y: x-y
)
```

Đây là **kiểm thử trên tập mẫu**, không phải chứng minh với toàn bộ miền vô hạn. Một phép có thể vượt qua vài test mà vẫn sai ở dữ liệu chưa thử. Với cấu trúc dữ liệu dùng trong sản phẩm, cần kết hợp **chứng minh bất biến** và kiểm thử trên nhiều tình huống biên.

### Test cấu trúc đối chiếu với quét trực tiếp

```python
values = [5, 2, 6, 3, 1, 7, 4, 8]
min_tree = MonoidSegmentTree(values, min, float("inf"))
min_sparse = IdempotentSparseTable(values, min)

for l in range(len(values)):
    for r in range(l + 1, len(values) + 1):
        expected = min(values[l:r])
        assert min_tree.query(l, r) == expected
        assert min_sparse.query(l, r) == expected

# Segment tree có đơn vị cho phép hỏi đoạn rỗng.
assert min_tree.query(4, 4) == float("inf")
```

Kiểm tra mọi đoạn của một mảng nhỏ giúp bắt các lỗi **off-by-one**, thiếu phần tử, tính sai phần tử đơn vị hoặc chọn nhầm khối trong sparse table.

## 21. Bất biến và chứng minh cho hai công thức trọng tâm

### 21.1. Công thức prefix nhờ nghịch đảo

Đặt:

```text
P[0] = e
P[i+1] = P[i] ⊕ a[i]
```

Quy nạp theo `i` cho thấy `P[i]` là gộp của các phần tử `[0,i)` theo thứ tự trái sang phải.

Với `l<=r`, tính kết hợp cho:

```text
P[r] = P[l] ⊕ Q(l,r)
```

Nếu phép toán là group, gộp nghịch đảo **ở bên trái**:

```text
Q(l,r) = inverse(P[l]) ⊕ P[r]
```

Bảo đảm này bao gồm đoạn rỗng nhờ `inverse(P[l])⊕P[l]=e`.

### 21.2. Sparse table phủ chồng lấn nhờ lũy đẳng

Với đoạn không rỗng `[l,r)`, chọn `s` là lũy thừa 2 lớn nhất không vượt `r-l`. Hai đoạn:

```text
A = [l,l+s)
B = [r-s,r)
```

phủ toàn bộ truy vấn. Gọi các phần **không chồng lấn** bên trái, vùng **chồng lấn** và phần không chồng lấn bên phải là `X,Y,Z`.

Khi ấy kết quả của hai khối có dạng:

```text
Q(A) = Q(X) ⊕ Q(Y)
Q(B) = Q(Y) ⊕ Q(Z)
```

Gộp:

```text
Q(A) ⊕ Q(B)
= Q(X) ⊕ Q(Y) ⊕ Q(Y) ⊕ Q(Z)
= Q(X) ⊕ Q(Y) ⊕ Q(Z)
= Q(l,r)
```

Đẳng thức thứ hai dùng **lũy đẳng trên giá trị tổng hợp `Q(Y)`**; các bước đổi ngoặc dùng **tính kết hợp**. Không cần đảo vị trí dữ liệu, và không phải mọi phép toán đều thỏa bước khử `Q(Y)⊕Q(Y)`.

Nếu vùng chồng lấn rỗng thì hai đoạn kề nhau, không có phần nào bị gộp hai lần; kết quả vẫn đúng.

## 22. Những nhầm lẫn phổ biến

| Nhầm lẫn | Hậu quả | Cách sửa |
|---|---|---|
| Coi kết hợp giống giao hoán | Đảo trái/phải với phép nối chuỗi | Giữ đúng thứ tự, chỉ đổi ngoặc |
| Coi kết hợp tức có nghịch đảo | Dùng prefix min rồi cố trừ | Chỉ khử khi có nghịch đảo thích hợp |
| Coi có đơn vị tức mọi phần tử có nghịch đảo | Dùng phép nhân trên miền chứa 0 | Xác định rõ group và phần tử khả nghịch |
| Nhầm đơn vị và phần tử hấp thụ | Base case cho min/max/nhân sai | Kiểm tra `op(e,x)=x` ở cả hai phía |
| Dùng `0` làm min của đoạn rỗng | Kết quả sai khi mọi phần tử dương | Dùng `+∞`/trạng thái rỗng hoặc báo lỗi |
| Coi giao hoán tức lũy đẳng | Dùng sparse table chồng lấn cho sum | Cần `op(x,x)=x` |
| Coi lũy đẳng tức nghịch đảo | Thử lấy min đoạn bằng hiệu hai min tiền tố | Min không khử được tiền tố |
| Gộp hai khối overlap cho tổng | Đếm trùng vùng giao nhau | Dùng các khối rời hoặc prefix |
| Coi idempotent nghĩa phần tử trùng nhau biến mất khỏi dữ liệu | Hiểu sai cấu trúc/đếm | Chỉ kết quả của phép gộp thỏa tính chất |
| Quên đoạn rỗng trong API | Lỗi không xác định với min hoặc avg | Nêu rõ đơn vị và chính sách empty |
| Segment tree chỉ có một accumulator | Có thể đảo khối ở bên phải | Dùng tích lũy trái và phải đúng thứ tự |
| Gộp hai trung bình bằng trung bình của hai trung bình | Sai khi số mẫu khác nhau | Lưu `(sum,count)` |
| Sử dụng prefix sau cập nhật mà không làm mới | Kết quả lỗi thời | Duy trì/rebuild hoặc dùng cấu trúc động |
| Gọi O(log n) mọi phép nối chuỗi | Không tính chi phí sao chép ký tự | Xem chi phí thực của `op` |
| Coi số thực máy kết hợp tuyệt đối | Sai khác do làm tròn | Nêu mô hình và sai số |
| Cho rằng có tính chất query là đủ cho lazy update | Cập nhật đoạn sai công thức | Đặc tả thêm tác động/hợp thành update |
| Trộn 1-based đóng với 0-based nửa mở | Sai biên và đoạn rỗng | Chuẩn hóa về `[l,r)` một lần |

## 23. Bài tập tự luyện có lời giải

**Bài 1 — Phân loại.** Phép cộng số nguyên có kết hợp, đơn vị, nghịch đảo, lũy đẳng không?

*Lời giải:* Có **kết hợp**, **đơn vị 0** và **nghịch đảo `-x`**; không lũy đẳng vì `5+5≠5`.

**Bài 2 — Min.** Phép min trên miền số mở rộng có những tính chất nào?

*Lời giải:* **Kết hợp, giao hoán, lũy đẳng**, có **đơn vị `+∞`**, nhưng không có nghịch đảo group tổng quát.

**Bài 3 — Đơn vị.** Tìm phần tử đơn vị cho phép XOR, ghép chuỗi và nhân số.

*Lời giải:* XOR có đơn vị **0**, ghép chuỗi có **`""`**, nhân số có **1**.

**Bài 4 — Hấp thụ.** Vì sao `0` không phải đơn vị phép nhân?

*Lời giải:* `0*x=0`, không bằng `x` nói chung. `0` là **phần tử hấp thụ**; đơn vị phép nhân là 1.

**Bài 5 — Không kết hợp.** Tính `(10-4)-2` và `10-(4-2)` để xác định phép trừ có kết hợp không.

*Lời giải:* Kết quả lần lượt **4** và **8**. Phép trừ không kết hợp.

**Bài 6 — Ghép chuỗi.** Có thể dùng monoid nối chuỗi để gộp kết quả hai đoạn không chồng lấn không? Có được đổi thứ tự không?

*Lời giải:* **Có** thể gộp do kết hợp và có đơn vị rỗng; **không** được đảo hai đoạn vì ghép chuỗi không giao hoán.

**Bài 7 — Prefix sum.** Với `a=[4,-1,7,2,9,3]`, hãy tính `P` và tổng `[2,5)`.

*Lời giải:* `P=[0,4,3,10,12,21,24]`; kết quả `P[5]-P[2]=21-3=18`.

**Bài 8 — Prefix XOR.** Với `a=[5,3,7,2]`, XOR đoạn `[1,4)` là bao nhiêu?

*Lời giải:* `3 xor 7 xor 2 = 6`; có thể tính `prefix_xor[1] xor prefix_xor[4]`.

**Bài 9 — Prefix min.** Tại sao không thể trừ hai prefix min để lấy min trên đoạn bất kỳ?

*Lời giải:* Min không có phép nghịch đảo để khử phần đã nằm trước biên trái. Prefix min có thể mất thông tin về giá trị bên trong một đoạn con.

**Bài 10 — Sparse table.** Truy vấn `[1,7)` dài 6 phần tử. Nếu dùng hai khối lũy thừa 2 lớn nhất không quá 6, mỗi khối có độ dài bao nhiêu?

*Lời giải:* `2^floor(log2(6))=4`. Hai khối là **`[1,5)`** và **`[3,7)`**, có phần chồng lấn `[3,5)`.

**Bài 11 — Overlap.** Với `a=[5,2,6,3,1,7,4,8]`, tổng hai khối ở bài 10 là 27 trong khi tổng toàn đoạn là 23. Vì sao?

*Lời giải:* Hai khối đếm trùng **`3+1=4`** ở vị trí 3 và 4. Tổng không lũy đẳng.

**Bài 12 — Chọn cấu trúc.** Dữ liệu tĩnh, rất nhiều truy vấn min không rỗng, không cập nhật. Tại sao sparse table phù hợp?

*Lời giải:* Min **kết hợp và lũy đẳng**, nên có thể gộp hai khối overlap. Sau O(n log n) tiền xử lý, mỗi truy vấn O(1).

**Bài 13 — Segment tree.** Có cần phép nghịch đảo để dùng segment tree tính min hoặc nối chuỗi không?

*Lời giải:* **Không.** Phép gộp các đoạn rời cần kết hợp và đơn vị trong giao diện đã trình bày, không cần nghịch đảo.

**Bài 14 — Trung bình.** Hai đoạn có tổng/số lượng lần lượt `(10,1)` và `(12,3)`. Hỏi trung bình của đoạn ghép.

*Lời giải:* Ghép thành `(22,4)` rồi lấy `22/4=5,5`. Không lấy trung bình của hai trung bình.

**Bài 15 — Đoạn rỗng.** Giá trị đơn vị nào nên trả cho tổng của `[l,l)`? Có nhất thiết trả `+∞` cho min đoạn rỗng tại API công khai không?

*Lời giải:* Tổng rỗng dùng **0**. Min có thể dùng **`+∞` nội bộ**, nhưng API công khai có thể **báo lỗi** khi đoạn rỗng.

**Bài 16 — Nghịch đảo không giao hoán.** Với định nghĩa `P[r]=P[l]⊕R`, công thức nào đúng trong group không giao hoán?

*Lời giải:* **`R=inverse(P[l])⊕P[r]`**. Không tự ý đổi thành `P[r]⊕inverse(P[l])`.

**Bài 17 — Hai tính chất.** Một phép trên group đồng thời lũy đẳng có thể có hai phần tử khác nhau không?

*Lời giải:* **Không.** Từ `x⊕x=x` khử một `x` bằng nghịch đảo suy ra `x=e` cho mọi x; group chỉ có một phần tử.

**Bài 18 — Query và update.** Với tổng đoạn, cộng `delta` vào mọi phần tử của đoạn dài `len` làm tổng thay đổi bao nhiêu?

*Lời giải:* **`delta*len`**. Quy tắc này nói về tác động của update lên bản tóm tắt, là điều kiện riêng ngoài tính kết hợp của phép cộng.

**Bài 19 — Tính giao hoán.** Phép chọn trái `x⊕y=x` có lũy đẳng và kết hợp không? Có giao hoán không?

*Lời giải:* **Có lũy đẳng và kết hợp**, nhưng **không giao hoán** khi `x≠y`.

**Bài 20 — Sai số máy.** Vì sao một thuật toán gộp tổng số thực theo cây có thể cho kết quả bit-for-bit khác vòng lặp?

*Lời giải:* Dấu phẩy động **làm tròn**, nên phép cộng ở máy không tuyệt đối kết hợp. Cách đặt ngoặc khác nhau có thể làm đổi vài bit kết quả.

## 24. Tổng kết: chọn cấu trúc từ tính chất phép gộp

Bốn thuộc tính này có vai trò khác nhau:

- **Kết hợp:** đổi cách **đặt ngoặc**, cho phép gộp những đoạn liên tiếp theo nhiều cách; là nền tảng của segment tree.
- **Đơn vị:** đại diện cho **đoạn rỗng**, khởi tạo tích lũy và các ô padding; kết hợp + đơn vị tạo **monoid**.
- **Nghịch đảo:** trong một group phù hợp, cho phép **khử tiền tố** bằng công thức `Q(l,r)=inverse(P[l])⊕P[r]`; cộng và XOR là các ví dụ quen thuộc.
- **Lũy đẳng:** `x⊕x=x`, cho phép kỹ thuật **hai khối chồng lấn** trong sparse table thông thường; min, max và gcd trên miền phù hợp là ví dụ.

Đừng nhầm kết hợp với giao hoán, nghịch đảo với lũy đẳng, hay phép gộp của truy vấn với phép tác động của cập nhật. Với **mỗi loại range query**, hãy nêu rõ **miền dữ liệu, phép toán, phần tử đơn vị, chính sách đoạn rỗng, thứ tự trái–phải và loại cập nhật**. Những hợp đồng ấy quyết định cách chọn thuật toán và giải thích được vì sao một tối ưu là đúng — hoặc vì sao nó sẽ đếm trùng, mất thông tin hay trả kết quả sai.
