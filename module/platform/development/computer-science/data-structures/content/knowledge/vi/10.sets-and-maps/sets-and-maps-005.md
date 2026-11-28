# Đa tập hợp và lưu số lần xuất hiện

Trong một buổi học, danh sách điểm danh có thể là `["An", "Bình", "An", "Chi", "An"]`. Nếu chuyển thành **tập hợp (set)**, ta chỉ còn biết ba người từng xuất hiện. Nhưng để trả lời **“An xuất hiện bao nhiêu lần?”**, ta phải giữ thêm một thông tin: **số lần xuất hiện của từng phần tử**.

**Đa tập hợp** (*multiset*, còn gọi là *bag*) là kiểu dữ liệu trừu tượng cho phép một giá trị xuất hiện nhiều lần. Bài học thuộc chương **Tập hợp và ánh xạ**, xây dựng trên hai ý tưởng: set mô tả sự hiện diện, còn map lưu **phần tử → số lần xuất hiện**. Ta sẽ tìm hiểu bất biến, thao tác, ví dụ Python và độ phức tạp thời gian, bộ nhớ để lựa chọn cấu trúc dữ liệu phù hợp.

## 1. Tập hợp và đa tập hợp khác nhau thế nào?

Với dãy đầu vào:

```text
["cam", "táo", "cam", "lê", "táo", "cam"]
```

Một **set** chỉ giữ tập các giá trị phân biệt: `{"cam", "táo", "lê"}`. Trong khi đó, một **multiset** giữ số lần xuất hiện:

| Phần tử | Số lần xuất hiện |
| --- | ---: |
| `cam` | 3 |
| `táo` | 2 |
| `lê` | 1 |

Ta có thể ký hiệu đa tập hợp này là `{cam×3, táo×2, lê×1}`. Ký hiệu `×3` mang nghĩa **ba bản sao của phần tử**, không phải một phần của chuỗi `"cam"`.

Cần phân biệt ba đại lượng:

- **Tổng số phần tử có tính cả bản sao**: `3 + 2 + 1 = 6`.
- **Số giá trị phân biệt**: `3`.
- **Số lần xuất hiện của một phần tử**: ví dụ `count("cam") = 3`.

Khác với list, **multiset không coi thứ tự là một phần của bản chất dữ liệu**. Hai dãy `["A", "B", "A"]` và `["A", "A", "B"]` biểu diễn cùng một multiset vì đều có `A` hai lần và `B` một lần. Nếu phải giữ thứ tự sự kiện, dùng list hoặc lưu riêng danh sách sự kiện bên cạnh các bộ đếm.

### Mô hình toán học và bất biến

Một multiset `M` trên miền giá trị `U` có thể được mô tả bằng hàm **bội số** (*multiplicity*):

```text
m_M : U → {0, 1, 2, 3, ...}
```

Trong đó `m_M(x)` là số bản sao của `x` trong `M`. Với multiset hữu hạn, chỉ có hữu hạn phần tử có bội số dương. Ta quy ước `m_M(x) = 0` khi `x` không có mặt.

Những bất biến quan trọng:

1. **Bội số là số nguyên không âm**: không có “âm ba lần xuất hiện” trong một multiset thông thường.
2. **Giá trị vắng mặt có bội số bằng 0**.
3. **Tổng kích thước** là tổng tất cả bội số dương: `size(M) = Σ m_M(x)`.
4. **Số phần tử phân biệt** là số giá trị có bội số lớn hơn 0: `distinct(M) = |{x : m_M(x) > 0}|`.

Với mô hình chuẩn hóa bằng map, ta chỉ lưu những cặp `x → count` có `count > 0`; khi đếm về 0, xóa khóa `x`. Nhờ đó, **số khóa của map bằng số phần tử phân biệt**. Đây là một quy ước hiện thực hữu ích, dù một số thư viện bộ đếm cho phép giữ cả khóa có giá trị 0 hoặc âm.

## 2. Chọn cấu trúc lưu trữ: map từ phần tử tới tần suất

Để cài multiset, ta có thể sử dụng một **map (dictionary / hash map)**:

```text
{
    "cam": 3,
    "táo": 2,
    "lê": 1
}
```

Ở đây mỗi **khóa** là một giá trị phân biệt; **giá trị** đi kèm là tần suất. Map vẫn bảo đảm **khóa duy nhất**, còn nhiều lần xuất hiện được thể hiện bằng bộ đếm tại khóa ấy.

| Cấu trúc | Dữ liệu lưu | Câu hỏi trả lời tốt |
| --- | --- | --- |
| `set` | Mỗi phần tử phân biệt một lần | “Đã gặp `x` chưa?” |
| `list` | Toàn bộ phần tử, có thứ tự và có thể lặp | “Phần tử ở vị trí thứ `i` là gì?” |
| `map[x] = count` | Mỗi giá trị phân biệt và tần suất của nó | “`x` đã xuất hiện bao nhiêu lần?” |
| `map[x] = list` | Mỗi khóa và các bản ghi liên quan | “Những bản ghi nào gắn với `x`?” |

Nếu cần **danh sách đầy đủ của từng lần xuất hiện**, bộ đếm không đủ để tái tạo thông tin như thời điểm, nguồn hoặc thứ tự. Ví dụ `{"An": 3}` không tiết lộ ba lần điểm danh diễn ra lúc nào.

### Vì sao không chỉ dùng set?

```python
values = ["A", "B", "A", "C", "A", "B"]

seen = set(values)
print(seen == {"A", "B", "C"})  # True
print(len(seen))                # 3

# Thông tin rằng A xuất hiện 3 lần đã bị mất.
```

Set rất hữu ích khi chỉ quan tâm **có/không**. Multiset phù hợp khi **số lượng bản sao** quyết định kết quả.

## 3. Các thao tác cơ bản của Multiset ADT

Ta định nghĩa các thao tác theo ngữ nghĩa một multiset hữu hạn. Các tên hàm chỉ mang tính minh họa; cách báo lỗi phụ thuộc API cụ thể.

| Thao tác | Ý nghĩa | Ảnh hưởng đến bội số |
| --- | --- | --- |
| `count(x)` | Trả số lần `x` xuất hiện | Không đổi |
| `add(x)` | Thêm một bản sao của `x` | `m(x) ← m(x) + 1` |
| `add(x, k)` | Thêm `k` bản sao, `k > 0` | `m(x) ← m(x) + k` |
| `removeOne(x)` | Xóa một bản sao nếu có | `m(x) ← m(x) − 1` khi `m(x) > 0` |
| `removeAll(x)` | Xóa toàn bộ bản sao của `x` | `m(x) ← 0` |
| `contains(x)` | Kiểm tra `m(x) > 0` | Không đổi |
| `size()` | Tổng số bản sao của mọi phần tử | Không đổi |
| `distinctSize()` | Số phần tử có bội số dương | Không đổi |
| `clear()` | Loại tất cả phần tử | Đưa mọi bội số về 0 |

Ví dụ bắt đầu từ đa tập hợp rỗng:

| Thao tác | Biểu diễn đa tập hợp | Tổng bản sao | Số giá trị phân biệt |
| --- | --- | ---: | ---: |
| Ban đầu | `{}` | 0 | 0 |
| `add("A")` | `{A×1}` | 1 | 1 |
| `add("A")` | `{A×2}` | 2 | 1 |
| `add("B", 3)` | `{A×2, B×3}` | 5 | 2 |
| `removeOne("A")` | `{A×1, B×3}` | 4 | 2 |
| `removeOne("A")` | `{B×3}` | 3 | 1 |
| `removeOne("A")` lần nữa | `{B×3}` | 3 | 1 |

**Xóa khi không có mặt** là một quyết định API: có thể trả `False`, không làm gì hoặc báo lỗi. Nhưng nếu muốn bảo toàn multiset chuẩn, không được làm bội số âm.

### Giả mã thêm và xóa có duy trì bất biến

```text
ADD(M, x, k):
    yêu cầu k là số nguyên dương
    M[x] = M.get(x, 0) + k

REMOVE_ONE(M, x):
    nếu x không có trong M:
        trả false
    nếu M[x] == 1:
        xóa khóa x khỏi M
    ngược lại:
        M[x] = M[x] - 1
    trả true
```

Với hiện thực bằng map đã chuẩn hóa, số lượng khóa tăng khi thêm **một giá trị hoàn toàn mới**, nhưng không tăng khi thêm bản sao của giá trị có sẵn. Ngược lại, xóa bản sao cuối cùng làm giảm cả tổng số bản sao và số giá trị phân biệt.

## 4. Tự cài đặt multiset bằng Python `dict`

Ví dụ sau giữ đúng bất biến “chỉ lưu số đếm dương” và duy trì biến tổng để truy vấn `total_size` nhanh:

```python
class Multiset:
    def __init__(self):
        self._counts = {}
        self._total = 0

    def count(self, item):
        return self._counts.get(item, 0)

    def contains(self, item):
        return item in self._counts

    def add(self, item, times=1):
        if not isinstance(times, int) or isinstance(times, bool) or times <= 0:
            raise ValueError("times phải là số nguyên dương")
        self._counts[item] = self.count(item) + times
        self._total += times

    def remove_one(self, item):
        current = self.count(item)
        if current == 0:
            return False
        if current == 1:
            del self._counts[item]  # Xóa khóa khi hết bản sao
        else:
            self._counts[item] = current - 1
        self._total -= 1
        return True

    def remove_all(self, item):
        current = self.count(item)
        if current == 0:
            return 0
        del self._counts[item]
        self._total -= current
        return current

    def total_size(self):
        return self._total

    def distinct_size(self):
        return len(self._counts)

    def frequencies(self):
        return self._counts.copy()  # Trả bản sao, bảo vệ bất biến nội bộ


bag = Multiset()
bag.add("cam", 3)
bag.add("táo", 2)
bag.add("lê")

assert bag.count("cam") == 3
assert bag.total_size() == 6
assert bag.distinct_size() == 3

assert bag.remove_one("lê") is True
assert bag.remove_one("lê") is False
assert bag.count("lê") == 0
assert bag.total_size() == 5
assert bag.distinct_size() == 2

assert bag.remove_all("cam") == 3
assert bag.frequencies() == {"táo": 2}
```

Trong Python, khóa của `dict` phải **hashable** và tuân thủ quy tắc băm/so sánh bằng nhau. Chuỗi và số nguyên là khóa phổ biến; list không dùng trực tiếp làm khóa `dict`. Với khóa là đối tượng tự định nghĩa, phần tham gia tính hash và kiểm tra bằng nhau phải ổn định trong khi khóa đang nằm trong map.

Để tránh người gọi vô tình làm bộ đếm âm hoặc sửa tổng số, ví dụ trên **không trả trực tiếp** dictionary nội bộ từ `frequencies()`. Thiết kế tốt cần bảo đảm bất biến được giữ qua mọi thao tác công khai.

## 5. Dùng `collections.Counter` trong Python

Thư viện chuẩn Python có `collections.Counter`, một lớp chuyên dùng để đếm các phần tử hashable:

```python
from collections import Counter

fruits = ["cam", "táo", "cam", "lê", "táo", "cam"]
counts = Counter(fruits)

print(counts["cam"])              # 3
print(counts["táo"])              # 2
print(counts["xoài"])             # 0: khóa chưa từng xuất hiện
print(counts.total())             # 6 (Python 3.10+)
print(counts.most_common(2))      # [('cam', 3), ('táo', 2)]

counts.update(["xoài", "cam"])     # Tăng mỗi phần tử thêm 1
print(counts["cam"])              # 4
print(counts["xoài"])             # 1
```

`Counter` rất thuận tiện khi thống kê tần suất; tuy nhiên, **nó linh hoạt hơn Multiset ADT chuẩn**:

- `Counter` **cho phép lưu số đếm bằng 0 hoặc âm**, chẳng hạn khi dùng `subtract` hoặc gán trực tiếp.
- `counts["missing"]` trả `0` ngay cả khi khóa chưa có; nhưng điều đó **không đồng nghĩa** khóa đã được lưu trong dictionary.
- `len(counts)` đếm các **khóa được lưu**, kể cả khóa có số đếm `0` hoặc âm, chứ không nhất thiết bằng số giá trị có bội số dương.
- Phương thức `elements()` chỉ lặp lại các phần tử có số đếm **nguyên dương**; các mục số đếm `0` và âm bị bỏ qua.

```python
from collections import Counter

c = Counter({"A": 2, "B": 0, "C": -1})

print(c["Z"])                 # 0: mặc định với khóa chưa có
print("Z" in c)               # False
print("B" in c)               # True: khóa được lưu với số đếm 0
print(len(c))                 # 3: A, B, C là các khóa được lưu
print(sorted(c.elements()))   # ['A', 'A']: chỉ bội số nguyên dương

# Chuẩn hóa thành multiset với các bội số dương
normalized = +c
print(normalized)             # Counter({'A': 2})
print(len(normalized))        # 1
```

Vì thế, khi bài toán yêu cầu **“số giá trị có số lần xuất hiện thực sự lớn hơn 0”**, có thể dùng `len(+c)` sau khi chuẩn hóa hoặc `sum(v > 0 for v in c.values())`. Toán tử `+c` là toán tử **cộng đơn ngôi** của `Counter`, tạo bộ đếm chỉ giữ số đếm dương; đừng nhầm với phép cộng hai counter.

### Tạo bộ đếm bằng tay từ dữ liệu đầu vào

```python
events = ["A", "B", "A", "C", "B", "A"]
frequency = {}

for value in events:
    frequency[value] = frequency.get(value, 0) + 1

print(frequency)                 # {'A': 3, 'B': 2, 'C': 1}
print(sum(frequency.values()))   # 6 tổng bản sao
print(len(frequency))            # 3 phần tử phân biệt
```

Với `n` lần xuất hiện đầu vào và `d` giá trị phân biệt, cách đếm bằng hash map có thời gian **trung bình `O(n)`** và bộ nhớ **`O(d)`** nếu mỗi lần tra cứu/cập nhật khóa tốn trung bình `O(1)`.

## 6. Phép toán giữa hai đa tập hợp

Với set, mỗi phần tử chỉ có trạng thái có hoặc không. Với multiset, kết quả các phép toán cần xác định **bội số của từng giá trị**.

Giả sử:

```text
A = {x×3, y×1}
B = {x×1, z×2}
```

Các phép toán thường gặp:

| Phép toán | Quy tắc bội số với mỗi `t` | Kết quả |
| --- | --- | --- |
| **Hợp theo nghĩa multiset** `A ∪ B` | `max(m_A(t), m_B(t))` | `{x×3, y×1, z×2}` |
| **Giao** `A ∩ B` | `min(m_A(t), m_B(t))` | `{x×1}` |
| **Cộng túi** `A ⊎ B` | `m_A(t) + m_B(t)` | `{x×4, y×1, z×2}` |
| **Hiệu cắt về 0** `A − B` | `max(0, m_A(t) − m_B(t))` | `{x×2, y×1}` |
| **Hiệu đối xứng theo bội số** | `|m_A(t) − m_B(t)|` | `{x×2, y×1, z×2}` |

**Hợp** và **cộng túi** không giống nhau. Nếu hai danh sách ghi nhận độc lập mỗi bên đều chứa một bản sao của `x`, việc *gộp toàn bộ sự kiện* cần phép **cộng** và tạo hai bản sao. Phép hợp theo multiset chỉ giữ số bản sao **lớn nhất** xuất hiện ở một trong hai bên.

Dùng `Counter`:

```python
from collections import Counter

a = Counter({"x": 3, "y": 1})
b = Counter({"x": 1, "z": 2})

print(a | b)  # Counter({'x': 3, 'z': 2, 'y': 1})  - hợp lấy max
print(a & b)  # Counter({'x': 1})                  - giao lấy min
print(a + b)  # Counter({'x': 4, 'z': 2, 'y': 1})  - cộng bội số
print(a - b)  # Counter({'x': 2, 'y': 1})          - hiệu cắt về 0
```

Khi `Counter` tham gia các toán tử kết hợp trên, kết quả thường **loại các mục có số đếm không dương**; riêng các phương thức biến đổi như `subtract` vẫn có thể để lại số âm. Hãy xác định rõ ứng dụng đang dùng **multiset chuẩn** hay **bộ đếm đại số được phép âm**.

### Quan hệ bao hàm của multiset

`A` là **đa tập con** của `B` khi với mọi phần tử `t`, ta có `m_A(t) ≤ m_B(t)`. Ví dụ `{x×1}` là đa tập con của `{x×3, y×1}`, nhưng `{x×4}` thì không.

Với map tần suất chỉ chứa số đếm dương, có thể kiểm tra như sau:

```python
def is_submultiset(left, right):
    return all(count <= right.get(item, 0)
               for item, count in left.items())

assert is_submultiset({"x": 2}, {"x": 3, "y": 1})
assert not is_submultiset({"x": 4}, {"x": 3, "y": 1})
```

Hàm trên giả định hai map đã được chuẩn hóa và không có số đếm âm. Nếu cần so sánh cả các khóa có số đếm âm/0 của `Counter`, phải làm rõ hợp đồng toán học riêng.

## 7. Ứng dụng: giỏ hàng và kiểm tra đủ nguyên liệu

Giỏ hàng cần lưu số lượng của từng sản phẩm. Một set mã hàng sẽ làm mất số lượng, còn map từ SKU đến số lượng giữ được toàn bộ thông tin cần thiết:

```python
cart = {
    "SP01": 3,
    "SP02": 1,
}

warehouse = {
    "SP01": 5,
    "SP02": 0,
    "SP03": 8,
}

def missing_quantities(requested, available):
    """Trả số lượng còn thiếu của mỗi mã, nếu có."""
    missing = {}
    for sku, quantity in requested.items():
        if quantity <= 0:
            raise ValueError("Số lượng yêu cầu phải dương")
        shortage = quantity - available.get(sku, 0)
        if shortage > 0:
            missing[sku] = shortage
    return missing

print(missing_quantities(cart, warehouse))  # {'SP02': 1}
```

Ở đây `"SP02": 0` nghĩa là mã tồn tại nhưng đã hết hàng, trong khi khóa vắng mặt cũng được **nghiệp vụ này** quy về lượng sẵn có `0`. Nếu hệ thống cần phân biệt “hết hàng” và “mã SKU không hợp lệ”, phải kiểm tra hiện diện của khóa riêng, sau đó mới so sánh số lượng.

Một bài toán tương tự là **đủ nguyên liệu để nấu món ăn hay không**. Với một yêu cầu công thức `required` và kho `available`, ta cần `available.get(item, 0) >= required[item]` cho mọi nguyên liệu. Đây là phép kiểm tra bao hàm theo bội số, không chỉ kiểm tra xem nguyên liệu có xuất hiện trong kho.

## 8. Ứng dụng: thống kê log và tìm sự kiện phổ biến

Một dịch vụ ghi nhận các mã sự kiện:

```python
from collections import Counter

events = [
    "LOGIN", "VIEW", "VIEW", "PAY",
    "VIEW", "LOGIN", "VIEW", "PAY",
]

counts = Counter(events)
print(counts["VIEW"])       # 4
print(counts["LOGIN"])      # 2
print(counts["PAY"])        # 2
print(counts.most_common(1))  # [('VIEW', 4)]
```

Nếu chỉ muốn biết **các loại sự kiện từng xảy ra**, một set là đủ. Nếu muốn biết **mức độ phổ biến**, cần multiset hoặc map đếm. Nếu muốn **phát hiện thời gian giữa các lượt đăng nhập**, cần lưu thêm thông tin thời điểm; tần suất đơn thuần không thể thay thế lịch sử log.

Trong một số thuật toán, ví dụ kiểm tra hai chuỗi có cùng bộ ký tự và số lần xuất hiện hay không, có thể so sánh hai bộ đếm:

```python
from collections import Counter

def are_anagrams(a, b):
    return Counter(a) == Counter(b)

print(are_anagrams("listen", "silent"))  # True
print(are_anagrams("aab", "abb"))        # False
```

Ví dụ trên so sánh **ký tự đúng như đầu vào**: chữ hoa, dấu cách và dấu tiếng Việt đều được tính theo giá trị ký tự. Nếu bài toán yêu cầu bỏ qua hoa/thường hay khoảng trắng, cần chuẩn hóa trước khi đếm.

## 9. Độ phức tạp theo số phần tử và số giá trị phân biệt

Đặt:

- `n`: tổng số lần xuất hiện trong dữ liệu đầu vào.
- `d`: số **giá trị phân biệt** đang được lưu (`d ≤ n` đối với multiset có n bản sao).
- `d_A, d_B`: số giá trị phân biệt của hai multiset.

Nếu cài bằng hash map và giả định hàm băm/phép so sánh có chi phí hằng số, các phép toán thường có chi phí:

| Thao tác | Thời gian trung bình | Bộ nhớ bổ sung |
| --- | --- | --- |
| Đếm tần suất từ `n` sự kiện | `O(n)` | `O(d)` |
| `count(x)`, `add(x)`, `removeOne(x)` | `O(1)` | `O(1)` mỗi thao tác, chưa tính mở rộng bảng |
| `removeAll(x)` chỉ xóa khóa | `O(1)` | `O(1)` |
| Tính tổng `sum(counts.values())` | `O(d)` | `O(1)` |
| Trả tổng từ biến `_total` được duy trì | `O(1)` | `O(1)` cho biến tổng |
| Lấy tất cả cặp `(x, count)` | `O(d)` | `O(d)` nếu sao chép ra cấu trúc mới |
| Hợp hoặc cộng hai bộ đếm | `O(d_A + d_B)` | Tối đa `O(d_A + d_B)` cho kết quả mới |
| Giao hai bộ đếm | Tối đa `O(d_A + d_B)` theo cách triển khai thông thường | Tối đa `O(min(d_A, d_B))` cho kết quả dương |

Đây là chi phí **trung bình/kỳ vọng** với hash map. Trong trường hợp nhiều va chạm băm, thao tác đơn lẻ có thể chậm hơn. Nếu cài bằng **cây tìm kiếm cân bằng**, tìm/thêm/xóa một phần tử thường tốn `O(log d)` và hỗ trợ duyệt theo thứ tự khóa.

**Thời gian truy xuất tổng số bản sao không mặc nhiên là `O(1)`.** Nếu chỉ giữ map `x → count`, phép cộng tất cả giá trị phải duyệt `d` khóa. Muốn truy vấn tổng thường xuyên với chi phí `O(1)`, hãy duy trì biến tổng như lớp `Multiset` ở trên và cập nhật nó cùng mỗi thao tác.

### Tiết kiệm bộ nhớ khi có rất nhiều bản sao

Giả sử có một triệu sự kiện nhưng chỉ 100 loại mã. Lưu cả triệu chuỗi tham chiếu trong list cần bộ nhớ tỷ lệ với số sự kiện, tức `O(n)`. Map tần suất chỉ cần số mục tỷ lệ với **100 giá trị phân biệt**, tức `O(d)`, chưa tính bộ nhớ của đối tượng khóa và bộ đếm. Đổi lại, map tần suất không giữ thứ tự, thời điểm hay dữ liệu riêng của từng sự kiện.

Một trường hợp khác là miền giá trị rất nhỏ, ví dụ điểm số nguyên từ `0` tới `10`. Khi đó, có thể dùng **mảng 11 bộ đếm** theo chỉ số thay vì hash map. Việc tăng `counts[score]` có chi phí `O(1)` và bộ nhớ `O(U)` với `U = 11`. Cách này tiện nếu biết trước miền khóa nhỏ, nguyên, liên tục; với giá trị đa dạng hoặc miền rất rộng và thưa, map tần suất thường linh hoạt hơn.

## 10. Những nhầm lẫn thường gặp

1. **Nhầm `len(counter)` với tổng số lần xuất hiện.** `len` là số khóa được lưu; tổng bản sao là tổng bội số, chẳng hạn `sum(counter.values())` nếu bộ đếm đã chuẩn hóa không âm hoặc `counter.total()` khi thích hợp.
2. **Nhầm set với multiset.** Set loại bỏ số lần lặp; muốn đếm phải lưu bộ đếm.
3. **Nhầm cộng multiset với phép hợp.** Phép cộng dùng tổng bội số, phép hợp dùng bội số lớn nhất; kết quả có thể khác nhau.
4. **Để số đếm âm trong multiset chuẩn.** Xóa quá số bản sao không nên tạo bội số âm; hãy xác định chính sách từ chối hoặc cắt ở 0.
5. **Không xóa khóa khi số đếm về 0.** Với cài đặt map chuẩn hóa, điều này làm `len(map)` không còn đúng với số phần tử phân biệt.
6. **Tưởng `Counter` luôn duy trì bất biến multiset chuẩn.** `Counter` cho phép số đếm âm hoặc 0; cần chuẩn hóa hoặc kiểm tra đầu vào tùy bài toán.
7. **Nhầm lưu tần suất với giữ lịch sử sự kiện.** Tần suất không lưu thứ tự, thời điểm hoặc dữ liệu cụ thể của từng bản sao.
8. **Dùng khóa có quy tắc bằng nhau không phù hợp.** Ví dụ `"sp01"` và `"SP01"` mặc định là hai chuỗi khác nhau. Nếu nghiệp vụ coi là một mã, cần chuẩn hóa khóa nhất quán trước khi tăng bộ đếm.

## 11. Tự luyện tập

**Bài 1.** Dãy `[2, 3, 2, 5, 3, 2]` có tổng bao nhiêu phần tử, bao nhiêu giá trị phân biệt và bội số của `2` là bao nhiêu?

**Bài 2.** Bắt đầu với multiset rỗng: `add("A")`, `add("A")`, `add("B", 3)`, `removeOne("A")`, `removeOne("A")`. Hãy cho biết map tần suất chuẩn hóa, tổng số bản sao và số giá trị phân biệt.

**Bài 3.** Cho `A = {x×2, y×1}`, `B = {x×1, z×3}`. Tính hợp, giao, cộng và hiệu `A − B` theo định nghĩa trong bài.

**Bài 4.** Tại sao `Counter({"A": 1, "B": 0})` có `len(...) == 2` nhưng chỉ có một phần tử phân biệt với bội số dương? Viết cách chuẩn hóa.

**Bài 5.** Thiết kế hàm kiểm tra một giỏ hàng có đủ tồn kho không. Giỏ hàng và kho đều được biểu diễn bằng map `SKU → số lượng nguyên không âm`. Điều kiện nào phải đúng với từng SKU?

**Bài 6.** Với dãy một triệu sự kiện có 50 loại mã, hãy so sánh bộ nhớ của list và map tần suất. Nêu thông tin gì bị mất khi chuyển sang map tần suất.

<details>
<summary>Đáp án gợi ý</summary>

1. Tổng `6` phần tử, `3` giá trị phân biệt (`2, 3, 5`), bội số của `2` bằng `3`.
2. Sau hai lần xóa `A`, map chuẩn hóa là `{"B": 3}`; tổng số bản sao `3`; số giá trị phân biệt `1`.
3. Hợp `{x×2, y×1, z×3}`; giao `{x×1}`; cộng `{x×3, y×1, z×3}`; hiệu `A − B = {x×1, y×1}`.
4. `Counter` vẫn lưu khóa `B` với số đếm `0`. Dùng `+c` để bỏ mọi khóa có số đếm không dương, hoặc chỉ giữ các cặp `(k, v)` với `v > 0`.
5. Với mọi SKU được yêu cầu, cần `available.get(sku, 0) >= requested[sku]`. Trước đó phải xác nhận cách xử lý SKU không hợp lệ và số lượng âm.
6. List dùng bộ nhớ theo số sự kiện `O(n)`; map tần suất dùng theo số mã phân biệt `O(d)`. Map mất thông tin thứ tự, thời điểm và dữ liệu riêng của mỗi sự kiện.

</details>

## Ghi nhớ

**Đa tập hợp (multiset/bag) giữ số lần xuất hiện của mỗi phần tử**, trong khi set chỉ giữ thông tin có mặt hay vắng mặt. Một hiện thực phổ biến là **map từ phần tử tới bộ đếm nguyên dương**, xóa khóa khi bộ đếm về 0. Hãy phân biệt **tổng bản sao** với **số giá trị phân biệt**, và phân biệt **hợp lấy bội số lớn nhất** với **phép cộng bội số**. Với hash map, quá trình đếm `n` sự kiện thường tốn `O(n)` thời gian trung bình và `O(d)` bộ nhớ, trong đó `d` là số giá trị phân biệt.
