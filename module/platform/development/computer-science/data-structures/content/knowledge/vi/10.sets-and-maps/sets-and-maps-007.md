# Hợp, giao, hiệu và kiểm tra quan hệ tập con

Một nền tảng học tập cần kết hợp danh sách học viên của hai lớp, tìm những người học **cả hai** lớp, xác định người **chỉ học lớp A**, hoặc kiểm tra liệu một học viên đã hoàn thành **tất cả môn tiên quyết** hay chưa. Bốn nhu cầu ấy tương ứng với các thao tác trên **tập hợp (set)**: **hợp**, **giao**, **hiệu** và **kiểm tra quan hệ tập con**.

Trong chương **Tập hợp và ánh xạ** của module cấu trúc dữ liệu, set là kiểu dữ liệu trừu tượng chỉ lưu **các phần tử phân biệt**. Bài này tập trung vào việc xác định chính xác kết quả của các phép toán, áp dụng chúng bằng Python, suy luận từ bất biến và đánh giá chi phí thời gian, bộ nhớ khi chọn cách cài đặt.

## 1. Ôn lại mô hình set và ký hiệu

Một **tập hợp** là một bộ các phần tử phân biệt, không có thứ tự mang ý nghĩa toán học. Chẳng hạn:

- `A = {1, 2, 3, 4}`.
- `B = {3, 4, 5}`.
- `3 ∈ A`: số `3` thuộc tập `A`.
- `5 ∉ A`: số `5` không thuộc tập `A`.
- `|A| = 4`: tập `A` có bốn phần tử.
- `∅`: tập rỗng, không chứa phần tử nào.

Hai tập hợp bằng nhau khi **chứa đúng cùng các phần tử**, bất kể thứ tự liệt kê:

```text
{1, 2, 3} = {3, 1, 2}
{1, 1, 2} = {1, 2}
```

Trong ví dụ thứ hai, số `1` được viết hai lần không tạo thêm phần tử mới. Điều này khác với **đa tập hợp (multiset)**, nơi số lần xuất hiện được lưu riêng.

### Ví dụ xuyên suốt

Ta dùng hai tập sau để tính toán:

```text
A = {1, 2, 3, 4}
B = {3, 4, 5}

Chỉ thuộc A:    {1, 2}
Thuộc cả hai:   {3, 4}
Chỉ thuộc B:    {5}
```

Ba vùng này **không giao nhau** và khi kết hợp lại tạo ra toàn bộ tập `A ∪ B`. Đây là cách hữu ích để hình dung các phép toán thay vì ghi nhớ máy móc.

## 2. Phép hợp: lấy các phần tử thuộc ít nhất một tập

**Hợp** (*union*) của `A` và `B`, ký hiệu `A ∪ B`, gồm mọi phần tử nằm trong **A hoặc B hoặc cả hai**.

Định nghĩa:

> `x ∈ A ∪ B` khi và chỉ khi `x ∈ A` **hoặc** `x ∈ B`.

Với ví dụ:

```text
A       = {1, 2, 3, 4}
B       = {3, 4, 5}
A ∪ B   = {1, 2, 3, 4, 5}
```

Hai phần tử `3` và `4` được liệt kê một lần vì set giữ tính duy nhất.

### Python

```python
a = {1, 2, 3, 4}
b = {3, 4, 5}

union_by_operator = a | b
union_by_method = a.union(b)

assert union_by_operator == {1, 2, 3, 4, 5}
assert union_by_method == union_by_operator

print(sorted(union_by_operator))  # [1, 2, 3, 4, 5]
print(sorted(a))                  # [1, 2, 3, 4]: a không đổi
```

Toán tử `|` tạo **một set kết quả mới**. Trong Python, `a.union(b)` cũng tạo set mới; nó không sửa `a` hoặc `b`.

Nếu muốn **cập nhật trực tiếp** tập `a`, có thể dùng `a.update(b)` hoặc `a |= b`:

```python
a = {1, 2, 3}
b = {3, 4}

a.update(b)
assert a == {1, 2, 3, 4}
```

Lệnh cập nhật tại chỗ có tác động lên đối tượng `a`. Nếu những phần khác của chương trình cùng giữ tham chiếu đến `a`, chúng cũng sẽ quan sát nội dung đã thay đổi.

### Khi nào dùng phép hợp?

- Gộp mã học viên từ hai lớp để lấy **danh sách học viên phân biệt**.
- Gộp tập từ khóa của nhiều tài liệu.
- Kết hợp các đỉnh đã thăm trong hai lượt duyệt đồ thị.

Phép hợp không cho biết **mỗi phần tử xuất hiện ở bao nhiêu nguồn**. Nếu cần thông tin ấy, dùng map đếm tần suất hoặc multiset.

## 3. Phép giao: lấy các phần tử thuộc cả hai tập

**Giao** (*intersection*) của `A` và `B`, ký hiệu `A ∩ B`, gồm các phần tử xuất hiện trong **cả A và B**.

Định nghĩa:

> `x ∈ A ∩ B` khi và chỉ khi `x ∈ A` **và** `x ∈ B`.

Với ví dụ:

```text
A       = {1, 2, 3, 4}
B       = {3, 4, 5}
A ∩ B   = {3, 4}
```

### Python

```python
a = {1, 2, 3, 4}
b = {3, 4, 5}

common = a & b
assert common == {3, 4}
assert common == a.intersection(b)

# Hai nhóm không có phần tử chung
assert {1, 2}.isdisjoint({3, 4})
assert ({1, 2} & {3, 4}) == set()
```

Nếu giao bằng tập rỗng, hai tập gọi là **rời nhau** (*disjoint*):

```text
A ∩ B = ∅
```

Trong Python, `a.isdisjoint(b)` trực tiếp kiểm tra điều kiện ấy mà không cần tạo một set giao mới. Nó thường phù hợp khi chỉ quan tâm **có phần tử chung nào không**, chứ không cần danh sách phần tử chung.

### Bài toán thực tế

Giả sử:

```python
python_students = {"HV01", "HV02", "HV03"}
algorithms_students = {"HV02", "HV03", "HV05"}

both = python_students & algorithms_students
print(sorted(both))  # ['HV02', 'HV03']
```

Giao cho biết hai học viên học **cả Python lẫn Thuật toán**. Nếu cần tìm người tham gia **ít nhất một lớp**, dùng hợp; đây là hai câu hỏi nghiệp vụ khác nhau.

## 4. Phép hiệu: lấy phần tử thuộc tập đầu nhưng không thuộc tập sau

**Hiệu** (*difference*) của `A` và `B`, ký hiệu `A − B` hoặc `A \\ B` trong một số tài liệu toán học, gồm những phần tử **thuộc A nhưng không thuộc B**.

Định nghĩa:

> `x ∈ A − B` khi và chỉ khi `x ∈ A` **và** `x ∉ B`.

Với ví dụ:

```text
A − B = {1, 2}
B − A = {5}
```

**Thứ tự của toán hạng rất quan trọng:** nói chung `A − B ≠ B − A`. Đây là khác biệt lớn so với phép hợp và giao.

### Python

```python
a = {1, 2, 3, 4}
b = {3, 4, 5}

only_a = a - b
only_b = b - a

assert only_a == {1, 2}
assert only_b == {5}
assert a.difference(b) == only_a
```

Phép hiệu phù hợp để trả lời câu hỏi **“còn thiếu những gì?”**:

```python
required_topics = {"arrays", "hashing", "trees", "graphs"}
completed_topics = {"arrays", "hashing", "python"}

missing_topics = required_topics - completed_topics
print(sorted(missing_topics))  # ['graphs', 'trees']
```

Ta lấy tập **yêu cầu** trừ tập **đã hoàn thành**, vì cần tìm các yêu cầu chưa đáp ứng. Nếu viết ngược lại, `completed_topics - required_topics`, kết quả `{"python"}` là nội dung đã học nhưng không nằm trong yêu cầu: câu hỏi hoàn toàn khác.

### Hiệu đối xứng: phần tử chỉ thuộc đúng một phía

Một phép toán liên quan là **hiệu đối xứng** (*symmetric difference*), ký hiệu `A △ B` hoặc `A Δ B`. Nó gồm những phần tử chỉ nằm trong **một trong hai** tập, không nằm trong cả hai:

```text
A △ B = (A − B) ∪ (B − A)
      = {1, 2, 5}
```

```python
a = {1, 2, 3, 4}
b = {3, 4, 5}

assert a ^ b == {1, 2, 5}
assert a.symmetric_difference(b) == (a - b) | (b - a)
```

Khác với hiệu, hiệu đối xứng **có tính giao hoán**: `A △ B = B △ A`.

## 5. Kiểm tra quan hệ tập con

Tập `A` là **tập con** của `B`, ký hiệu `A ⊆ B`, nếu **mọi phần tử của A cũng nằm trong B**.

Định nghĩa:

> `A ⊆ B` khi và chỉ khi với mọi `x`, nếu `x ∈ A` thì `x ∈ B`.

Điểm cần chú ý: `A ⊆ B` **không yêu cầu A nhỏ hơn B**. Một tập luôn là tập con của chính nó:

```text
{1, 2} ⊆ {1, 2, 3}       đúng
{1, 2} ⊆ {1, 2}          đúng
{1, 4} ⊆ {1, 2, 3}       sai vì 4 không thuộc tập bên phải
```

Nếu `A ⊆ B` và `A ≠ B`, ta nói `A` là **tập con thực sự** (*proper subset*) của `B`, ký hiệu `A ⊊ B` hoặc `A ⊂ B` theo quy ước một số tài liệu. Để tránh nhầm ký hiệu `⊂` giữa các nguồn, hãy nêu rõ khi nào yêu cầu “tập con thực sự”.

### Các toán tử Python

```python
required = {"arrays", "hashing"}
completed = {"arrays", "hashing", "trees"}

assert required <= completed                # Tập con, cho phép bằng
assert required.issubset(completed)
assert required < completed                 # Tập con thực sự

assert completed >= required                # Tập cha / tập bao
assert completed.issuperset(required)
assert completed > required                 # Tập cha thực sự

assert required <= required                 # True: mọi tập con của chính nó
assert not (required < required)            # True: không là tập con thực sự
```

Trong Python:

| Ký hiệu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `a <= b` | `a` là tập con của `b`, **có thể bằng** | `{1} <= {1, 2}` |
| `a < b` | `a` là tập con thực sự của `b` | `{1} < {1, 2}` |
| `a >= b` | `a` bao hàm `b` | `{1, 2} >= {1}` |
| `a > b` | `a` bao hàm thực sự `b` | `{1, 2} > {1}` |
| `a == b` | Hai tập bằng nhau | `{1, 2} == {2, 1}` |

Không nhầm các toán tử trên với **so sánh thứ tự số học** hoặc so sánh các tập theo kích thước. Chẳng hạn `{1, 3}` và `{1, 2}` đều có hai phần tử, nhưng không tập nào là tập con của tập kia:

```python
left = {1, 3}
right = {1, 2}

assert not (left <= right)
assert not (right <= left)
assert len(left) == len(right) == 2
```

Hai tập như vậy được gọi là **không so sánh được theo quan hệ bao hàm**.

### Tập rỗng và trường hợp biên

Với mọi tập `S`:

- `∅ ⊆ S`: tập rỗng luôn là tập con của mọi tập.
- `S ⊆ S`: mọi tập là tập con của chính nó.
- `∅ ⊊ S` đúng khi `S` **không rỗng**.
- `S ⊆ ∅` chỉ đúng nếu `S = ∅`.

Giải thích `∅ ⊆ S`: không tồn tại phần tử nào trong `∅` vi phạm điều kiện “mọi phần tử của tập bên trái đều ở tập bên phải”.

```python
empty = set()                    # {} là dict rỗng, không phải set
values = {1, 2}

assert empty <= values
assert empty <= empty
assert empty < values
assert not (empty < empty)
assert not (values <= empty)
```

### Kiểm tra đã đáp ứng đủ yêu cầu

Một ứng dụng có thể xác định xem học viên đã hoàn thành tất cả nội dung tiên quyết:

```python
prerequisites = {"arrays", "hashing"}
learned = {"arrays", "hashing", "trees"}

ready = prerequisites <= learned
print(ready)  # True

missing = prerequisites - learned
print(sorted(missing))  # []

assert ready == (len(missing) == 0)
```

Để biết **đủ hay chưa**, kiểm tra tập con. Để biết **thiếu cụ thể nội dung nào**, dùng phép hiệu. Một API phù hợp tùy việc người gọi cần giá trị boolean hay danh sách thiếu.

## 6. Bảng tổng hợp bốn thao tác

Cho `A = {1, 2, 3, 4}` và `B = {3, 4, 5}`:

| Phép toán | Điều kiện một phần tử `x` được chọn | Kết quả |
| --- | --- | --- |
| Hợp `A ∪ B` | `x ∈ A` **hoặc** `x ∈ B` | `{1, 2, 3, 4, 5}` |
| Giao `A ∩ B` | `x ∈ A` **và** `x ∈ B` | `{3, 4}` |
| Hiệu `A − B` | `x ∈ A` **và** `x ∉ B` | `{1, 2}` |
| Hiệu `B − A` | `x ∈ B` **và** `x ∉ A` | `{5}` |
| Hiệu đối xứng `A △ B` | `x` thuộc đúng một tập | `{1, 2, 5}` |
| Tập con `{3, 4} ⊆ A` | Mọi phần tử bên trái đều có trong `A` | `True` |
| Tập con `A ⊆ B` | Mọi phần tử `A` đều có trong `B` | `False` |

Nếu chỉ cần định nghĩa thao tác, có thể dùng **bảng chân trị** đối với một phần tử đại diện:

| `x ∈ A` | `x ∈ B` | `x ∈ A ∪ B` | `x ∈ A ∩ B` | `x ∈ A − B` | `x ∈ A △ B` |
| --- | --- | --- | --- | --- | --- |
| Không | Không | Không | Không | Không | Không |
| Có | Không | Có | Không | Có | Có |
| Không | Có | Có | Không | Không | Có |
| Có | Có | Có | Có | Không | Không |

Quan hệ tập con không phải phép chọn ra các phần tử: nó là **một mệnh đề về toàn bộ hai tập**, trả đúng hoặc sai.

## 7. Các tính chất toán học giúp kiểm tra tính đúng đắn

Các đẳng thức dưới đây đúng với mọi tập hợp `A, B, C` theo nghĩa toán học, miễn là phép bằng nhau được xác định nhất quán.

| Tính chất | Đẳng thức | Ý nghĩa |
| --- | --- | --- |
| Giao hoán của hợp | `A ∪ B = B ∪ A` | Đảo hai tập không đổi kết quả hợp |
| Giao hoán của giao | `A ∩ B = B ∩ A` | Đảo hai tập không đổi giao |
| Kết hợp của hợp | `(A ∪ B) ∪ C = A ∪ (B ∪ C)` | Có thể nhóm các phép hợp |
| Kết hợp của giao | `(A ∩ B) ∩ C = A ∩ (B ∩ C)` | Có thể nhóm các phép giao |
| Lũy đẳng | `A ∪ A = A`, `A ∩ A = A` | Lặp cùng tập không tạo phần tử mới |
| Phần tử đơn vị | `A ∪ ∅ = A`, `A ∩ ∅ = ∅` | Hợp/giao với tập rỗng |
| Hiệu chính nó | `A − A = ∅` | Không phần tử nào chỉ thuộc A mà không thuộc A |
| Phân phối | `A ∩ (B ∪ C) = (A ∩ B) ∪ (A ∩ C)` | Phân rã điều kiện “và / hoặc” |
| Phân phối | `A ∪ (B ∩ C) = (A ∪ B) ∩ (A ∪ C)` | Một luật phân phối khác |
| Phân chia | `A = (A − B) ∪ (A ∩ B)` | Mọi phần tử A hoặc không thuộc B, hoặc thuộc B |

Một quan hệ quan trọng liên quan trực tiếp đến bài này:

> `A ⊆ B` khi và chỉ khi `A − B = ∅`.

Cũng tương đương với `A ∩ B = A` hoặc `A ∪ B = B`.

### Kiểm tra bằng Python

```python
a = {1, 2, 3}
b = {2, 3, 4}
c = {3, 4, 5}

assert (a | b) == (b | a)
assert (a & b) == (b & a)
assert (a | b) | c == a | (b | c)
assert a & (b | c) == (a & b) | (a & c)

assert a == (a - b) | (a & b)
assert ({2, 3} <= a) == (len({2, 3} - a) == 0)
```

Các tính chất này có ích khi **kiểm thử một triển khai set tự viết**, vì chúng cung cấp nhiều điều kiện kiểm tra độc lập với một ví dụ cụ thể.

### Bổ sung: bù tập hợp và luật De Morgan

Nếu đã chọn **tập vũ trụ `U`** là toàn bộ phần tử đang xét, phần bù của `A` trong `U` được định nghĩa là `U − A`. Khi đó:

```text
U − (A ∪ B) = (U − A) ∩ (U − B)
U − (A ∩ B) = (U − A) ∪ (U − B)
```

Ví dụ tập vũ trụ các học viên trong một khóa học được xác định trước, ta có thể tìm người **không học lớp A hoặc B** bằng cách lấy `U` trừ tập hợp của hai lớp. Không thể suy ra phần bù một cách đầy đủ nếu **chưa xác định tập vũ trụ**.

## 8. Cách cài đặt phép toán bằng thao tác thành viên

Set ADT chỉ quy định **kết quả đúng**, không áp đặt một cấu trúc lưu trữ duy nhất. Để hiểu thuật toán, giả sử có thao tác `contains(x)` và `insert(x)`. Phép hợp có thể cài như sau:

```text
UNION(A, B):
    result = một set rỗng
    với mỗi x trong A:
        INSERT(result, x)
    với mỗi x trong B:
        INSERT(result, x)
    trả result
```

Phép giao có thể **duyệt tập nhỏ hơn**, tra cứu trong tập lớn hơn:

```text
INTERSECTION(A, B):
    nếu |A| > |B|:
        đổi chỗ A và B
    result = một set rỗng
    với mỗi x trong A:
        nếu CONTAINS(B, x):
            INSERT(result, x)
    trả result
```

Phép hiệu `A − B` phải duyệt các phần tử **của A**:

```text
DIFFERENCE(A, B):
    result = một set rỗng
    với mỗi x trong A:
        nếu không CONTAINS(B, x):
            INSERT(result, x)
    trả result
```

Kiểm tra tập con chỉ cần một phần tử `x` thuộc `A` nhưng không thuộc `B` để kết luận **sai**:

```text
IS_SUBSET(A, B):
    nếu |A| > |B|:
        trả false
    với mỗi x trong A:
        nếu không CONTAINS(B, x):
            trả false
    trả true
```

Những giả mã này là một **cách triển khai**, không nhất thiết trùng với các tối ưu bên trong thư viện cụ thể. Điều kiện `|A| > |B|` được dùng để kết luận nhanh rằng `A` không thể là tập con `B` với set hữu hạn.

## 9. Độ phức tạp thời gian và bộ nhớ

Gọi `n = |A|` và `m = |B|`. Giả sử mỗi thao tác kiểm tra/thêm phần tử của **hash set** tốn **trung bình `O(1)`**, đồng thời việc băm hoặc so sánh một phần tử có chi phí cơ bản hằng số.

| Thao tác | Thuật toán minh họa | Thời gian trung bình | Bộ nhớ bổ sung |
| --- | --- | --- | --- |
| Hợp `A ∪ B` | Duyệt cả hai tập và thêm vào kết quả | `O(n + m)` | Tối đa `O(n + m)` |
| Giao `A ∩ B` | Duyệt tập nhỏ, tra cứu trong tập lớn | `O(min(n, m))` | Tối đa `O(min(n, m))` |
| Hiệu `A − B` | Duyệt A, chỉ giữ phần tử không ở B | `O(n)` | Tối đa `O(n)` |
| Hiệu đối xứng | Xử lý hai hiệu hoặc duyệt hai tập | `O(n + m)` | Tối đa `O(n + m)` |
| Tập con `A ⊆ B` | Duyệt A, dừng nếu tìm thấy phần tử thiếu | Xấu nhất theo trung bình tra cứu: `O(n)` | `O(1)` |
| Kiểm tra rời nhau | Duyệt tập nhỏ, dừng nếu tìm thấy phần tử chung | Tối đa `O(min(n, m))` theo giả định trên | `O(1)` |

**Cách đọc bảng:** Đây là chi phí của **các thuật toán được mô tả** dưới giả định tra cứu hash set trung bình hằng số. Một thư viện có thể chọn thuật toán khác và có độ phức tạp cụ thể khác, nhất là với phép hiệu hoặc các phép cập nhật tại chỗ.

Lưu ý:

1. Thời gian `O(1)` cho hash set là **trung bình/kỳ vọng**, không phải cam kết cho mọi khóa. Va chạm băm có thể làm một thao tác chậm hơn, và tái băm khi mở rộng bảng có thể tốn `O(n)` cho một lần.
2. Chi phí xây một **set kết quả mới** khác với chi phí của phép chỉ trả về `True`/`False`. Ví dụ `a.issubset(b)` không cần tạo tập mới, còn `a - b == set()` tạo tập hiệu (nếu viết như vậy).
3. Các câu lệnh `sorted(result)` trong ví dụ phục vụ hiển thị nhất quán; **sắp xếp** tập kết quả gồm `r` phần tử mất thêm khoảng `O(r log r)` thời gian và không phải chi phí nội tại của phép toán set.
4. Nếu các phần tử là chuỗi rất dài hoặc đối tượng phức tạp, chi phí tính hash/so sánh không còn nhất thiết là hằng số.
5. Một **tree set** dùng cây tìm kiếm cân bằng thường có thao tác thành viên/thêm `O(log n)`; nếu cài phép giao bằng cách duyệt tập nhỏ và tra cứu cây lớn, chi phí có thể là `O(min(n, m) log(max(n, m) + 1))` thay vì `O(min(n, m))`. Ngược lại, hai tập đã sắp xếp có thể được xử lý bằng cách duyệt phối hợp phù hợp.

### Tại sao thường duyệt tập nhỏ khi lấy giao?

Giả sử `A` có 100 khóa và `B` có một triệu khóa. Nếu chỉ cần giao hai hash set và chọn cách duyệt tập nhỏ, ta chỉ cần khoảng 100 lần kiểm tra thành viên ở tập lớn. Duyệt toàn bộ triệu khóa rồi kiểm tra trong tập nhỏ vẫn đúng, nhưng làm nhiều việc hơn.

Trong Python, `set.intersection` và các phép liên quan có tối ưu riêng; khi phân tích thuật toán tự cài, nguyên tắc **duyệt phía nhỏ nếu kết quả cần phần tử chung** là một lựa chọn hữu ích.

## 10. Thực hành các trường hợp biên và các phép cập nhật tại chỗ

### Phép toán với tập rỗng và tập bằng nhau

```python
empty = set()
a = {1, 2}

assert (a | empty) == a
assert (a & empty) == set()
assert (a - empty) == a
assert (empty - a) == set()

assert (a | a) == a
assert (a & a) == a
assert (a - a) == set()
assert a <= a
assert not (a < a)
```

### Các phương thức tạo mới và thay đổi tại chỗ

| Mục đích | Tạo set kết quả mới | Sửa tập bên trái |
| --- | --- | --- |
| Hợp | `a | b`, `a.union(b)` | `a |= b`, `a.update(b)` |
| Giao | `a & b`, `a.intersection(b)` | `a &= b`, `a.intersection_update(b)` |
| Hiệu | `a - b`, `a.difference(b)` | `a -= b`, `a.difference_update(b)` |
| Hiệu đối xứng | `a ^ b`, `a.symmetric_difference(b)` | `a ^= b`, `a.symmetric_difference_update(b)` |

Cách dùng:

```python
available = {"A", "B", "C"}
reserved = {"B", "C"}

remaining = available - reserved
assert remaining == {"A"}
assert available == {"A", "B", "C"}  # Toán tử - không sửa available

available.difference_update(reserved)
assert available == {"A"}           # Đã sửa tại chỗ
```

Đặc biệt chú ý trường hợp **biến tham chiếu đến cùng một set**:

```python
first = {1, 2, 3}
alias = first

first.intersection_update({2, 3})
assert alias == {2, 3}   # alias nhìn thấy thay đổi vì cùng đối tượng
```

Nếu cần giữ bản gốc, dùng toán tử tạo kết quả mới hoặc chủ động sao chép `copy()`.

### Kiểu phần tử và tính duy nhất

Python set dựa trên băm nên phần tử phải **hashable**:

```python
valid = {(1, 2), (2, 3)}  # tuple chứa phần tử hashable
# invalid = {[1, 2]}     # TypeError: list không hashable

assert {1, 2} == {2, 1}
assert len({1, 1, 2}) == 2
```

Quy tắc so sánh phần tử quyết định tính duy nhất: `"a"` và `"A"` là hai chuỗi khác nhau theo mặc định; nếu ứng dụng muốn coi như cùng mã, phải **chuẩn hóa đầu vào** trước khi xây set.

## 11. Bài toán tổng hợp: điều kiện hoàn thành khóa học

Giả sử hệ thống có các nhóm kiến thức bắt buộc cho hai chương trình:

```python
backend_required = {"arrays", "hashing", "trees", "graphs"}
data_required = {"arrays", "hashing", "graphs", "statistics"}

learned = {"arrays", "hashing", "trees", "python"}
```

Ta muốn trả lời nhiều câu hỏi, mỗi câu bằng một phép toán phù hợp.

**1. Kiến thức cần cho ít nhất một chương trình**

```python
all_requirements = backend_required | data_required
print(sorted(all_requirements))
# ['arrays', 'graphs', 'hashing', 'statistics', 'trees']
```

**2. Kiến thức bắt buộc của cả hai chương trình**

```python
shared_requirements = backend_required & data_required
print(sorted(shared_requirements))
# ['arrays', 'graphs', 'hashing']
```

**3. Kiến thức chỉ chương trình backend yêu cầu**

```python
only_backend = backend_required - data_required
print(sorted(only_backend))  # ['trees']
```

**4. Học viên đã đủ điều kiện cho backend chưa? Thiếu gì?**

```python
is_ready = backend_required <= learned
missing = backend_required - learned

print(is_ready)         # False
print(sorted(missing))  # ['graphs']
```

Ở đây `learned` có mục `python` nằm ngoài yêu cầu backend, nhưng điều đó **không làm mất tính đủ điều kiện**; để đạt điều kiện chỉ cần chứa **mọi phần tử bắt buộc**, không yêu cầu hai tập bằng nhau.

### Hàm kiểm tra tiên quyết có thể tái sử dụng

```python
def check_prerequisites(required, learned):
    required_set = set(required)
    learned_set = set(learned)

    missing = required_set - learned_set
    return {
        "ready": not missing,
        "missing": missing,
        "shared": required_set & learned_set,
    }

result = check_prerequisites(
    ["arrays", "hashing", "graphs"],
    ["arrays", "hashing", "python"],
)

assert result["ready"] is False
assert result["missing"] == {"graphs"}
assert result["shared"] == {"arrays", "hashing"}
```

Hàm chuyển đầu vào thành set nên **loại bản sao trùng**; đó là hành vi mong muốn khi mỗi kiến thức chỉ cần hoàn thành một lần. Nếu nghiệp vụ yêu cầu học một môn **nhiều lần** hoặc tính số tín chỉ, phải dùng cấu trúc khác, chẳng hạn map định lượng hoặc multiset.

## 12. Các lỗi thường gặp

1. **Nhầm hợp với phép nối danh sách.** Hợp không giữ bản sao trùng và không bảo đảm thứ tự; nếu muốn giữ các lượt xuất hiện, phải dùng list hoặc multiset.
2. **Nhầm giao với phép hợp.** Giao đòi hỏi phần tử thuộc **cả hai** tập; hợp chỉ cần thuộc ít nhất một.
3. **Đảo ngược phép hiệu.** `required - learned` là thứ còn thiếu; `learned - required` là thứ đã học nhưng không bắt buộc.
4. **Tưởng hiệu có tính giao hoán.** Nói chung `A - B` khác `B - A`.
5. **Nhầm tập con với tập con thực sự.** `a <= a` đúng nhưng `a < a` sai; thứ tự trong so sánh tập cũng không phải thứ tự số học.
6. **Đoán tập con chỉ bằng kích thước.** `|A| ≤ |B|` là điều kiện cần, **không đủ** để `A ⊆ B`: vẫn phải kiểm tra từng phần tử.
7. **Cho rằng tập rỗng không là tập con.** `∅ ⊆ S` đúng với mọi tập `S`.
8. **Nhầm một phép cập nhật tại chỗ với phép tạo mới.** `difference_update` sửa đối tượng, trong khi `difference` tạo kết quả mới.
9. **Giả định duyệt set luôn theo thứ tự chèn.** Set Python không có bảo đảm thứ tự; sắp xếp kết quả để hiển thị khi cần.
10. **Cho rằng mọi phép toán tập hợp đều `O(1)`.** Tra cứu thành viên trong hash set thường `O(1)` trung bình, nhưng tạo hợp, giao hoặc hiệu phải xử lý nhiều phần tử.

## 13. Tự luyện tập

**Bài 1.** Cho `A = {1, 2, 4, 6}` và `B = {2, 3, 4, 5}`. Tính `A ∪ B`, `A ∩ B`, `A - B`, `B - A` và `A △ B`.

**Bài 2.** Cho `X = {2, 4}`, `Y = {1, 2, 3, 4}`. Kiểm tra `X ⊆ Y`, `X ⊊ Y`, `Y ⊆ X` và `X ∩ Y = X`.

**Bài 3.** Với `A = ∅` và `B = {7}`, những mệnh đề nào đúng: `A ⊆ B`, `A ⊊ B`, `B ⊆ A`, `A ∪ B = B`, `A ∩ B = ∅`?

**Bài 4.** Một khóa học yêu cầu tập `required = {"array", "stack", "queue"}`. Học viên có `completed = {"array", "queue", "tree"}`. Viết một biểu thức Python xác định các mục chưa hoàn thành và một biểu thức xác định học viên đã đủ điều kiện hay chưa.

**Bài 5.** Giả sử `|A| = 12`, `|B| = 8` và `|A ∩ B| = 3`. Tính `|A ∪ B|` và `|A - B|`, giải thích tại sao.

**Bài 6.** Chọn một cách thực hiện có lợi khi lấy giao hai hash set có kích thước lần lượt `100` và `1.000.000`. Phân tích độ phức tạp trung bình của cách đó.

**Bài 7.** Xây dựng hàm `difference_report(a, b)` trả ba set: chỉ thuộc `a`, chỉ thuộc `b` và thuộc cả hai. Đầu vào là hai iterable các phần tử hashable. Kiểm tra rằng hợp của ba kết quả bằng `set(a) | set(b)` khi đầu vào là các list có giá trị trùng.

<details>
<summary>Đáp án tham khảo</summary>

1. `A ∪ B = {1, 2, 3, 4, 5, 6}`; `A ∩ B = {2, 4}`; `A - B = {1, 6}`; `B - A = {3, 5}`; `A △ B = {1, 3, 5, 6}`.
2. `X ⊆ Y` đúng; `X ⊊ Y` đúng; `Y ⊆ X` sai; `X ∩ Y = X` đúng.
3. Đúng: `A ⊆ B`, `A ⊊ B`, `A ∪ B = B`, `A ∩ B = ∅`. Sai: `B ⊆ A`.
4. `required - completed` cho `{"stack"}`; `required <= completed` cho `False`.
5. `|A ∪ B| = |A| + |B| - |A ∩ B| = 12 + 8 - 3 = 17` vì phần giao đã bị đếm hai lần. `|A - B| = |A| - |A ∩ B| = 12 - 3 = 9`.
6. Duyệt tập có 100 phần tử, kiểm tra mỗi phần tử trong tập lớn. Với hash set và giả định tra cứu trung bình `O(1)`, cách làm này cần tối đa khoảng 100 lượt kiểm tra; tổng quát, chi phí trung bình là `O(min(n, m))` với `n` và `m` là kích thước hai tập.
7. Một lời giải:

```python
def difference_report(a, b):
    left = set(a)
    right = set(b)
    return left - right, right - left, left & right

sample_a = [1, 1, 2, 3]
sample_b = [3, 4, 4]
only_a, only_b, both = difference_report(sample_a, sample_b)

assert only_a == {1, 2}
assert only_b == {4}
assert both == {3}
assert only_a | only_b | both == set(sample_a) | set(sample_b)
```

</details>

## Ghi nhớ

**Hợp** lấy phần tử thuộc **ít nhất một tập**; **giao** lấy phần tử thuộc **cả hai**; **hiệu `A − B`** lấy phần tử **thuộc A nhưng không thuộc B**; và **`A ⊆ B`** kiểm tra liệu **mọi phần tử A có trong B** hay không. Quan hệ tập con cho phép hai tập bằng nhau; tập con thực sự thì không. Khi dùng hash set, thời gian thực hiện phụ thuộc số phần tử phải duyệt và số lần tra cứu thành viên, chứ không chỉ là một phép toán ký hiệu. Hiểu rõ kết quả, bất biến và chi phí giúp áp dụng set chính xác trong xử lý dữ liệu, kiểm tra điều kiện học tập và thuật toán đồ thị.
