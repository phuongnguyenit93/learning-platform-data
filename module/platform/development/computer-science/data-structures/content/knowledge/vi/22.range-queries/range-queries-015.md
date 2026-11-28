# Cây đoạn động cho miền chỉ số lớn và thưa

## 1. Bài toán: miền chỉ số rất lớn nhưng chỉ một phần nhỏ được dùng

Giả sử một hệ thống lưu số lượt truy cập theo từng mili giây trong khoảng từ `0` đến `10^12 - 1`. Ban đầu mọi thời điểm đều có giá trị bằng `0`. Hệ thống phải xử lý trực tuyến hai thao tác:

- **Cập nhật đoạn**: cộng `d` vào tất cả giá trị tại các chỉ số thuộc `[l, r)`.
- **Truy vấn đoạn**: tính tổng các giá trị tại các chỉ số thuộc `[l, r)`.

Chẳng hạn, ba chỉ số quanh `700_000_000_000` có hoạt động, còn gần như toàn bộ miền chỉ số chưa từng được đụng đến. Nếu xây cây đoạn thông thường trên một mảng có `10^12` phần tử, bộ nhớ sẽ vượt xa nhu cầu thực tế. Một cây đoạn động (*dynamic segment tree*, còn gọi là *implicit segment tree*) chỉ tạo nút khi cập nhật thực sự cần đi vào vùng tương ứng.

Chủ đề thuộc chương **Truy vấn đoạn**: ta vẫn sử dụng nguyên lý chia đôi, lưu thông tin tổng hợp và trả lời truy vấn trên đoạn của cây đoạn, nhưng thay đổi cách cấp phát bộ nhớ để phục vụ dữ liệu lớn, thưa và có thể xuất hiện trực tuyến. Đây cũng là ví dụ về việc chọn cấu trúc dữ liệu theo bất biến, độ phức tạp thời gian và chi phí bộ nhớ.

Mọi đoạn trong bài dùng quy ước **nửa mở** `[l, r)`: bao gồm `l`, không bao gồm `r`. Miền gốc hữu hạn `[LO, HI)` chứa các chỉ số nguyên; đặt `U = HI - LO > 0`.

## 2. Từ cây đoạn tĩnh đến cây đoạn động

Trong cây đoạn tĩnh, mỗi nút đại diện cho một đoạn `[L, R)`. Nếu `R - L > 1`, ta chia tại `M = ⌊(L + R) / 2⌋` thành hai đoạn `[L, M)` và `[M, R)`. Mỗi nút lưu thông tin có thể gộp từ hai con, ví dụ tổng. Cây thường được dựng từ đầu bằng mảng `4U` ô hoặc một cấu trúc tương đương, vì thế cần `O(U)` bộ nhớ.

Cây đoạn động **giữ nguyên ý nghĩa của mỗi đoạn**, nhưng ban đầu chưa có nút nào. Khi một cập nhật chạm tới một đoạn chưa được biểu diễn, ta tạo nút cho đoạn ấy; những nhánh chưa từng cần đến vẫn được hiểu ngầm là mang giá trị ban đầu bằng `0`.

Ví dụ, với miền `[0, 16)`, một lần cộng trên `[11, 13)` chỉ đi qua các nhánh liên quan đến hai chỉ số 11 và 12. Ta không cần tạo toàn bộ 16 lá. Còn nếu cộng trên toàn miền `[0, 16)`, có thể chỉ cần **một nút gốc** lưu cập nhật cho cả đoạn.

Một nút không nhất thiết phải lưu `L` và `R`: hàm đệ quy có thể truyền hai biên này trong lúc đi xuống. Mỗi nút chỉ cần hai tham chiếu con và dữ liệu tổng hợp. Không có con trái hoặc phải đồng nghĩa với việc nhánh đó chưa có cập nhật riêng.

### Minh họa đường đi

Giả sử miền `[0, 8)` và thao tác cộng `5` lên `[2, 4)`:

~~~text
                       [0,8)
                      /     \
                  [0,4)     (chưa tạo)
                 /     \
           (chưa tạo)  [2,4) +5
             [0,2)
~~~

Các nút `[0,8)`, `[0,4)` và `[2,4)` được tạo dọc đường cập nhật. Nút `[2,4)` có thể ghi nhận cả đoạn bằng một phép cộng; không cần tạo riêng lá 2 và lá 3.

## 3. Bất biến của nút và cơ chế lazy không cần đẩy xuống

Để vừa hỗ trợ **cộng trên đoạn** vừa hỗ trợ **tổng trên đoạn**, mỗi nút `v` đại diện cho `[L, R)` lưu:

| Trường | Ý nghĩa |
| --- | --- |
| `left`, `right` | Con trái/phải; có thể chưa tồn tại (`None`). |
| `total` | Tổng đóng góp của các cập nhật được lưu trong **toàn bộ cây con** của `v` lên `[L, R)`. |
| `lazy` | Giá trị cộng đều cho **mọi chỉ số trong `[L, R)`** được ghi nhận ngay tại `v` và chưa phân bổ xuống hai con. |

Ta dùng một biến thể lazy propagation đặc biệt: **giữ `lazy` tại nút, không bắt buộc tạo con để đẩy lazy xuống**. Bất biến của mỗi nút đã tồn tại là:

\[
\operatorname{total}(v)
= \operatorname{total}(v.left)
+ \operatorname{total}(v.right)
+ \operatorname{lazy}(v)\,(R-L).
\]

Trong công thức trên, `total` của con chưa tồn tại được hiểu bằng `0`. Phần `lazy(v)` đại diện cho một lớp cộng đều phủ toàn bộ đoạn của nút, còn hai con biểu diễn những thay đổi *bổ sung* trong các nửa tương ứng.

**Khi cập nhật phủ trọn nút**, ta chỉ cần:

~~~text
node.total += delta * (R - L)
node.lazy  += delta
~~~

**Khi cập nhật chỉ giao một phần**, ta đi xuống các con cần thiết, rồi tính lại:

~~~text
node.total = total(left) + total(right) + node.lazy * (R - L)
~~~

Lưu ý: không được bỏ mất thành phần `node.lazy * (R - L)` khi tính lại. Nếu trước đó nút đã được cộng trên toàn đoạn, giá trị `lazy` vẫn thuộc về nút cha ngay cả sau khi ta cập nhật con.

**Khi truy vấn**, biến `carry` mang tổng các giá trị `lazy` của tổ tiên trên đường đi. Với nút `v` được lấy trọn, đáp án là `node.total + carry * (R - L)`. Nếu nút chưa tồn tại, tất cả các chỉ số trong phần giao truy vấn với đoạn của nút chỉ chịu ảnh hưởng của `carry`; đáp án phần ấy là `carry * độ_dài_phần_giao`. Khi truy vấn đi xuống, truyền `carry + node.lazy` cho con.

Thiết kế này có hai lợi ích: không cần thao tác *push* để tạo hai con trong lúc truy vấn; mỗi truy vấn chỉ đọc dữ liệu, hoàn toàn không tăng số nút.

## 4. Cài đặt Python hoàn chỉnh

Mã sau áp dụng cho Python 3.10 trở lên. Nó hỗ trợ cộng trên đoạn, lấy tổng đoạn, cả truy vấn điểm và miền chỉ số âm. Không cần dựng cây từ một mảng ban đầu; tất cả giá trị khởi tạo đều bằng 0.

~~~python
from __future__ import annotations


class _Node:
    __slots__ = ("left", "right", "total", "lazy")

    def __init__(self) -> None:
        self.left: _Node | None = None
        self.right: _Node | None = None
        self.total = 0
        self.lazy = 0


class DynamicSegmentTree:
    """Range add + range sum trên các chỉ số nguyên [lo, hi)."""

    def __init__(self, lo: int, hi: int) -> None:
        if lo >= hi:
            raise ValueError("Miền chỉ số phải không rỗng")
        self.lo = lo
        self.hi = hi
        self.root: _Node | None = None
        self.node_count = 0  # Chỉ để quan sát bộ nhớ đang dùng

    def _check_range(self, left: int, right: int) -> None:
        if not (self.lo <= left <= right <= self.hi):
            raise IndexError("Đoạn nằm ngoài miền chỉ số")

    def add(self, left: int, right: int, delta: int) -> None:
        """Cộng delta lên mỗi chỉ số trong [left, right)."""
        self._check_range(left, right)
        if left == right or delta == 0:
            return
        self.root = self._add(
            self.root, self.lo, self.hi, left, right, delta
        )

    def _add(
        self,
        node: _Node | None,
        seg_l: int,
        seg_r: int,
        ql: int,
        qr: int,
        delta: int,
    ) -> _Node | None:
        if qr <= seg_l or seg_r <= ql:
            return node

        if node is None:
            node = _Node()
            self.node_count += 1

        if ql <= seg_l and seg_r <= qr:
            node.total += delta * (seg_r - seg_l)
            node.lazy += delta
            return node

        mid = (seg_l + seg_r) // 2
        if ql < mid:
            node.left = self._add(
                node.left, seg_l, mid, ql, qr, delta
            )
        if qr > mid:
            node.right = self._add(
                node.right, mid, seg_r, ql, qr, delta
            )

        left_sum = 0 if node.left is None else node.left.total
        right_sum = 0 if node.right is None else node.right.total
        node.total = (
            left_sum + right_sum + node.lazy * (seg_r - seg_l)
        )
        return node

    def range_sum(self, left: int, right: int) -> int:
        """Tổng các giá trị trong [left, right)."""
        self._check_range(left, right)
        if left == right:
            return 0
        return self._sum(
            self.root, self.lo, self.hi, left, right, carry=0
        )

    def _sum(
        self,
        node: _Node | None,
        seg_l: int,
        seg_r: int,
        ql: int,
        qr: int,
        carry: int,
    ) -> int:
        if qr <= seg_l or seg_r <= ql:
            return 0

        if node is None:
            # Nhánh trống vẫn nhận cập nhật từ các tổ tiên.
            overlap = min(seg_r, qr) - max(seg_l, ql)
            return carry * overlap

        if ql <= seg_l and seg_r <= qr:
            return node.total + carry * (seg_r - seg_l)

        mid = (seg_l + seg_r) // 2
        carry += node.lazy
        answer = 0
        if ql < mid:
            answer += self._sum(
                node.left, seg_l, mid, ql, qr, carry
            )
        if qr > mid:
            answer += self._sum(
                node.right, mid, seg_r, ql, qr, carry
            )
        return answer

    def add_at(self, index: int, delta: int) -> None:
        """Cộng delta cho một chỉ số."""
        self.add(index, index + 1, delta)

    def get(self, index: int) -> int:
        """Giá trị tại một chỉ số."""
        return self.range_sum(index, index + 1)
~~~

### Ví dụ chạy

~~~python
tree = DynamicSegmentTree(0, 10**12)
p = 700_000_000_000

tree.add(p, p + 3, 5)       # Các vị trí p, p+1, p+2 đều thành 5
tree.add(p + 1, p + 2, 2)   # Riêng vị trí p+1 thành 7

assert tree.get(p) == 5
assert tree.get(p + 1) == 7
assert tree.range_sum(p, p + 3) == 17
assert tree.range_sum(0, p) == 0
assert tree.range_sum(0, 10**12) == 17

before = tree.node_count
assert tree.range_sum(p, p + 2) == 12
assert tree.node_count == before  # Truy vấn không cấp phát nút
~~~

Giá trị quan sát được quanh `p`:

| Chỉ số | Sau lần cộng thứ nhất | Sau lần cộng thứ hai |
| --- | ---: | ---: |
| `p` | 5 | 5 |
| `p + 1` | 5 | 7 |
| `p + 2` | 5 | 5 |
| Tất cả vị trí còn lại | 0 | 0 |

Kết quả trên không phụ thuộc vào số lượng `10^12` vị trí của miền. Độ sâu tối đa chỉ khoảng `⌈log₂(10^12)⌉ = 40`.

## 5. Theo dõi bất biến qua một trường hợp dễ sai

Xét miền nhỏ `[0, 8)`, ban đầu toàn bộ bằng `0`.

**Bước 1:** Cộng `3` trên `[0, 8)`. Chỉ có nút gốc:

~~~text
[0,8): lazy = 3, total = 24
~~~

**Bước 2:** Cộng `5` trên `[2, 4)`. Nút gốc vẫn giữ `lazy = 3`; nhánh `[0,4)` và nút `[2,4)` ghi nhận phần cộng bổ sung. Nút `[2,4)` có `lazy = 5`, `total = 10`. Vì thế:

~~~text
total([0,4)) = 10
total([0,8)) = 10 + 0 + 3 * 8 = 34
~~~

**Bước 3:** Truy vấn `[2, 4)`. Khi đi từ gốc xuống nhánh, ta mang `carry = 3`. Nút `[2,4)` đã lưu `total = 10`, nên kết quả là `10 + 3 × 2 = 16`, đúng bằng `8 + 8`.

**Bước 4:** Truy vấn `[6, 8)`. Nhánh này chưa tồn tại, nhưng `carry = 3`. Ta trả về `3 × 2 = 6`, không được trả `0` chỉ vì gặp con trống.

Bài học quan trọng ở đây là: **một con trống không đồng nghĩa với giá trị thực bằng 0 nếu các tổ tiên có lazy**. Nó chỉ có nghĩa là nhánh không có đóng góp riêng ngoài những gì đã được lưu tại tổ tiên.

## 6. Vì sao thuật toán đúng?

Ta chứng minh hai bất biến cho các thao tác, bắt đầu từ cây rỗng.

**Bất biến tổng:** với mỗi nút hiện hữu `v` quản lý `[L, R)`, tổng phần đóng góp của các cập nhật được lưu tại `v` và các hậu duệ bằng

\[
T(v) = T(v.left) + T(v.right) + \mathrm{lazy}(v)(R-L).
\]

Ban đầu không có nút, mọi tổng mặc định bằng 0. Nếu cập nhật phủ toàn đoạn của `v`, mỗi trong `R-L` phần tử tăng `d`, nên tăng `T(v)` thêm `d(R-L)` và tăng `lazy(v)` thêm `d`; đẳng thức vẫn đúng. Nếu cập nhật phủ một phần, các con được cập nhật đệ quy và `T(v)` được tính lại theo chính đẳng thức trên. Vì vậy bất biến được duy trì sau mọi cập nhật.

**Bất biến truy vấn:** khi hàm `_sum` đến đoạn `[L, R)` với tham số `carry`, mọi phần tử trong đoạn đều đã nhận thêm `carry` từ các tổ tiên, ngoài các đóng góp ghi tại cây con hiện tại. Nếu nút tồn tại và truy vấn phủ trọn, kết quả đúng là `T(v) + carry(R-L)`. Nếu nút không tồn tại, chỉ còn đóng góp từ tổ tiên, nên ta trả `carry` nhân độ dài giao. Nếu truy vấn chỉ phủ một phần, hai nửa chia đúng đoạn cần tính; truyền thêm `lazy(v)` cho mỗi con bảo đảm không bỏ sót đóng góp tại nút hiện tại. Cộng hai kết quả con cho ta tổng đúng.

Lập luận quy nạp theo độ cao của đoạn cho thấy `range_sum` luôn trả đúng tổng sau mọi chuỗi cập nhật hợp lệ.

## 7. Phân tích thời gian và bộ nhớ

Gọi `U = HI - LO` là độ dài miền và `k` là số lần cập nhật đoạn (có thể bằng 0).

| Hoạt động | Độ phức tạp | Giải thích |
| --- | --- | --- |
| Khởi tạo | `O(1)` thời gian, `O(1)` bộ nhớ | Chưa tạo nút. |
| Cộng trên đoạn | `O(log U)` | Mỗi tầng chỉ có tối đa hai nhánh giao một phần ở hai biên; các nhánh khác được cập nhật trọn. |
| Tính tổng đoạn | `O(log U)` | Xử lý trọn các nhánh nằm bên trong và đi sâu ở biên; nhánh trống kết thúc ngay. |
| Cộng/lấy giá trị tại một điểm | `O(log U)` | Là trường hợp đoạn dài 1. |
| Tổng số nút đã cấp phát | `O(k log U)` trong trường hợp xấu nhất | Mỗi cập nhật tạo nhiều nhất `O(log U)` nút mới; không vượt quá kích thước cây tĩnh tương ứng. |
| Ngăn xếp đệ quy | `O(log U)` | Mỗi lần đệ quy chia đôi đoạn. |

Thời gian ở đây tính theo các phép toán số nguyên có chi phí hằng số trong mô hình RAM. Trong Python, số nguyên có độ dài không bị cố định nên số học trên số cực lớn vẫn có chi phí phụ thuộc kích thước biểu diễn.

Nếu miền dài `10^12` nhưng chỉ vài trăm cập nhật, cây đoạn động có thể tiết kiệm bộ nhớ rất lớn so với cây tĩnh. Tuy nhiên, nếu cập nhật nhiều vị trí rải khắp miền, số nút có thể tăng đáng kể. Các đối tượng Python còn có chi phí quản lý bộ nhớ cho từng nút; `__slots__` giúp giảm phần overhead nhưng không loại bỏ chi phí này.

## 8. Lựa chọn cây đoạn động hay cấu trúc khác?

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Miền nhỏ, số phần tử đã biết | Cây đoạn tĩnh | Cấp phát liên tục, đơn giản, thường nhanh hơn. |
| Miền cực lớn, cập nhật/truy vấn xuất hiện trực tuyến | **Cây đoạn động** | Không phải biết trước những chỉ số sẽ xuất hiện. |
| Biết trước mọi tọa độ và ranh giới cập nhật/truy vấn | Nén tọa độ rồi dùng cây đoạn | Giảm số đoạn phải biểu diễn; phải bảo toàn **độ dài thật** của từng khoảng khi tính tổng. |
| Chỉ cần cộng điểm và lấy tổng tiền tố/đoạn, biết trước tọa độ hoặc nén được | Fenwick tree (BIT) | Cài đặt gọn, ít overhead. |
| Mảng bất biến, chỉ truy vấn min/max/gcd trên đoạn | Sparse table hoặc cấu trúc tiền xử lý tương ứng | Không cần chịu chi phí cập nhật động. |
| Cần nhiều phiên bản lịch sử của cây sau mỗi cập nhật | Cây đoạn persistent | Phải sao chép đường đi và quản lý phiên bản; không đồng nghĩa với cây đoạn động thông thường. |

**Phân biệt với nén tọa độ:** nếu các vị trí 10, 100 và 1.000.000 là những điểm rời rạc, việc ánh xạ chúng thành 0, 1 và 2 có thể phù hợp cho truy vấn điểm. Nhưng với cập nhật cộng trên *mọi chỉ số* của đoạn `[10, 1_000_000)`, mỗi khoảng sau nén có độ dài thật khác nhau. Nếu cộng tổng bằng số đoạn đã nén mà quên độ dài gốc, kết quả sẽ sai. Cây đoạn động giữ trực tiếp các biên số nguyên thật nên tránh lỗi đó.

Nếu bài toán chỉ cập nhật điểm trên một bản đồ có ít khóa được dùng và chỉ cần tra cứu từng khóa, một bảng băm có thể đủ. Cây đoạn động hữu ích khi cần **kết hợp các vị trí theo khoảng**, kể cả khoảng có nhiều chỉ số chưa từng được cập nhật.

## 9. Những lỗi triển khai thường gặp

1. **Nhầm `[l, r]` với `[l, r)`.** Trong mã này, cập nhật một điểm `x` phải dùng `[x, x+1)`. Mọi hàm phải thống nhất cùng một quy ước.
2. **Quên đóng góp lazy của cha khi tính lại tổng.** Sau khi cập nhật con, công thức vẫn phải cộng `node.lazy * (seg_r - seg_l)`.
3. **Trả 0 ngay khi gặp nút chưa tồn tại.** Một nút trống vẫn có thể nhận lazy từ tổ tiên. Hàm truy vấn cần mang biến `carry`.
4. **Đẩy lazy bằng cách tạo con trong truy vấn.** Cách đó có thể đúng nếu cài đặt nhất quán, nhưng làm phát sinh nút dù chỉ đọc. Thiết kế đang dùng tránh điều này.
5. **Chia đoạn nhưng không bảo đảm tiến triển.** Chỉ chia khi đoạn dài hơn 1; với chỉ số nguyên và cập nhật hợp lệ, lá dài 1 sẽ luôn là trường hợp phủ trọn hoặc không giao.
6. **Quên miền gốc phải được xác định.** Cây động tiết kiệm nút, nhưng vẫn cần một khoảng gốc hữu hạn `[LO, HI)`. Nếu không biết cận trước, phải chọn cận đủ rộng hoặc dùng cơ chế mở rộng gốc một cách nhất quán.
7. **Tràn số trong ngôn ngữ có kiểu nguyên cố định.** Với C++/Java, tích `delta * độ_dài_đoạn` và tổng có thể vượt giới hạn kiểu đang dùng. Công thức tính trung điểm kiểu `L + (R - L) / 2` giảm nguy cơ tràn khi cộng hai biên, nhưng bản thân `R - L` cũng phải nằm trong miền số biểu diễn được; có thể cần kiểu rộng hơn.
8. **Không kiểm tra cập nhật/truy vấn nằm trong miền.** Mã ví dụ chủ động báo lỗi với khoảng ngoài `[lo, hi)`. Nếu bài toán yêu cầu tự cắt biên, cần định nghĩa rõ quy tắc cắt trước khi cài đặt.

## 10. Luyện tập và tự kiểm tra

**Bài 1 — Truy vết lazy.** Trên miền `[0, 8)`, lần lượt cộng `2` trên `[0, 8)`, cộng `-1` trên `[1, 3)`, rồi hỏi tổng `[0, 4)` và `[4, 8)`. Hãy mô tả giá trị `lazy` ở gốc và cách `carry` được truyền.

*Đáp án kiểm tra:* bốn vị trí đầu có tổng `2 + 1 + 1 + 2 = 6`; bốn vị trí cuối có tổng `8`. Nút gốc vẫn giữ `lazy = 2`, trong khi nhánh chứa `[1,3)` ghi nhận mức cộng bổ sung `-1`.

**Bài 2 — Cập nhật điểm.** Vì sao hai thao tác `add_at(x, 4)` và `add(x, x+1, 4)` tương đương? Hãy chứng minh `get(x)` trả đúng giá trị sau nhiều cập nhật đoạn chồng nhau.

**Bài 3 — Đánh giá lựa chọn.** Cho `U = 10^15`, một triệu thao tác trực tuyến với nhiều đoạn rất nhỏ. Hãy phân tích giới hạn trên về số nút, rủi ro bộ nhớ trong Python và khả năng chọn giải pháp khác nếu biết trước tất cả thao tác.

**Bài 4 — Mở rộng.** Nếu muốn hỗ trợ *gán toàn bộ đoạn bằng một giá trị* thay vì cộng, tại sao không thể chỉ dùng công thức `lazy += delta`? Hãy đề xuất trạng thái `has_assign`/`assign_value`, quy tắc ghi đè cập nhật cũ và cách kết hợp phép gán với phép cộng.

**Bài 5 — Kiểm chứng ngẫu nhiên.** Trên miền nhỏ `[-10, 10)`, đối chiếu kết quả của cây đoạn động với một mảng 20 phần tử qua nhiều cập nhật và truy vấn ngẫu nhiên, gồm cả đoạn rỗng, chỉ số âm, số cộng âm và các khoảng phủ toàn miền. Mỗi lần truy vấn, kiểm tra số nút không tăng.

## 11. Ghi nhớ

Cây đoạn động áp dụng khi **miền chỉ số rất lớn nhưng các thao tác chỉ chạm tới một phần nhỏ**, đặc biệt khi truy vấn và cập nhật xuất hiện trực tuyến. Nó vẫn chia đoạn như cây đoạn truyền thống, nhưng chỉ cấp phát những nút thực sự cần thiết. Với tổng đoạn và cộng đoạn, cách giữ `lazy` tại nút và truyền `carry` khi truy vấn vừa giữ đúng bất biến tổng, vừa cho phép truy vấn mà không phát sinh nút. Độ phức tạp điển hình là `O(log U)` cho mỗi thao tác và `O(k log U)` nút sau `k` lần cập nhật trong trường hợp xấu nhất; việc chọn nó cần cân nhắc chi phí của từng nút và khả năng nén tọa độ khi dữ liệu đã biết trước.
