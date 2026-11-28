# Mảng có thứ tự và mảng không có thứ tự

## 1. Hai cách tổ chức cùng một tập dữ liệu

Giả sử một cửa hàng lưu số lượng sản phẩm bán được trong năm ngày. Hai mảng sau chứa cùng các giá trị:

```text
Mảng chưa sắp xếp U:
Chỉ số       0   1   2   3   4
Giá trị     [9,  3, 12,  5,  5]

Mảng tăng dần S:
Chỉ số       0   1   2   3   4
Giá trị     [3,  5,  5,  9, 12]
```

Ở mảng `U`, vị trí có thể phản ánh **thứ tự ghi nhận** các ngày; giá trị không tuân theo quy luật tăng hoặc giảm. Ở mảng `S`, vị trí phản ánh **thứ tự theo giá trị**: phần tử phía trước không lớn hơn phần tử phía sau. Việc sắp xếp đã thay đổi ý nghĩa của chỉ số: `U[0] = 9` nhưng `S[0] = 3`.

Trong bài này:

- **Mảng có thứ tự** (*sorted array*) là mảng mà các phần tử được duy trì theo một **quy tắc sắp xếp** xác định, ví dụ không giảm theo giá trị hoặc theo một khóa.
- **Mảng không có thứ tự** (*unsorted array*) là mảng **không có bất biến sắp xếp** cần được duy trì; nó vẫn có các phần tử ở những vị trí có thứ tự chỉ số rõ ràng.

Điểm thứ hai rất quan trọng: “không có thứ tự” **không có nghĩa là không có chỉ số, bị lưu ngẫu nhiên trong bộ nhớ hay không thể duyệt theo thứ tự**. Cả `U` và `S` đều là mảng và đều có thể truy cập `A[i]` theo vị trí.

Sau bài học, bạn có thể giải thích bất biến sắp xếp, so sánh chi phí tìm/chèn/xóa/cập nhật, áp dụng tìm kiếm nhị phân đúng điều kiện, xử lý giá trị trùng lặp và chọn cách tổ chức dữ liệu theo số lượng truy vấn cùng tần suất cập nhật.

Đây là một bài của chương **Mảng** trong học phần **Cấu trúc dữ liệu**. Tư duy về bất biến và đánh đổi giữa thời gian, bộ nhớ ở đây là nền tảng để lựa chọn danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị cho những bài toán khác nhau.

## 2. Bất biến của mảng được sắp xếp

Với mảng `A` có `n` phần tử, chỉ số bắt đầu từ `0`, bất biến **không giảm** (*non-decreasing*) là:

\[
A[i] \le A[i+1]\qquad\text{với mọi }0\le i<n-1
\]

Nói cách khác, phần tử trước không lớn hơn phần tử sau. Ta cho phép các giá trị **bằng nhau**, như hai số `5` trong `S`. Điều này khác với **tăng nghiêm ngặt** (*strictly increasing*), khi phải có `A[i] < A[i+1]` và không được có giá trị trùng.

| Tình huống | Có thỏa bất biến không giảm? | Lý do |
|---|---|---|
| `[1, 3, 3, 8]` | Có | Mỗi phần tử không lớn hơn phần tử tiếp theo |
| `[1, 2, 3, 4]` | Có | Tăng nghiêm ngặt cũng là không giảm |
| `[5, 5, 5]` | Có | Các phần tử bằng nhau được phép |
| `[2, 7, 4, 9]` | Không | `7 > 4` vi phạm quy tắc |
| `[]` hoặc `[7]` | Có | Không có cặp kề nhau nào vi phạm |

Cũng có thể sắp xếp **không tăng** (*non-increasing*) theo thứ tự giảm dần, hoặc sắp xếp bản ghi theo khóa như `score`, `created_at`, `student_id`. Muốn dùng thuật toán đúng, phải biết chính xác quy tắc nào đang được duy trì; công thức và ví dụ tiếp theo giả định **không giảm**.

Một mảng chưa sắp xếp *có thể tình cờ chứa những giá trị đang tăng dần*. Điều khác biệt nằm ở **cam kết của cấu trúc hoặc chương trình**: nếu không có bất biến sắp xếp, thao tác cập nhật tiếp theo có thể làm dữ liệu mất trật tự, và thuật toán không được dựa vào thứ tự ấy.

### Sắp xếp theo khóa không có nghĩa là mọi trường đều tăng

Giả sử dữ liệu là các bản ghi `(mã, điểm)`:

```text
[(SV03, 7), (SV01, 8), (SV09, 8), (SV02, 10)]
```

Mảng được sắp theo **điểm**, nên `7 <= 8 <= 8 <= 10`. Mã học sinh không cần tăng dần. Nếu câu hỏi là “tìm bản ghi có mã `SV02`”, điều kiện “đã sắp theo điểm” không giúp tìm nhị phân theo **mã**; hai tác vụ dùng hai khóa khác nhau.

Nếu phải bảo toàn thứ tự xuất hiện ban đầu của các bản ghi có khóa bằng nhau, có thể dùng **sắp xếp ổn định** (*stable sort*): những bản ghi cùng khóa giữ nguyên thứ tự tương đối. Tính ổn định của thuật toán sắp xếp là một thuộc tính riêng, không tự suy ra từ bất biến `<=`.

## 3. Truy cập theo chỉ số: hai loại mảng đều nhanh

Nếu đã biết `i` hợp lệ (`0 <= i < n`), cả mảng được sắp xếp và chưa sắp xếp đều đọc `A[i]` trong **`O(1)` thời gian** đối với cách biểu diễn mảng có truy cập trực tiếp theo chỉ số.

Trong mảng liên tiếp chứa các ô cố định kích thước `s` byte, địa chỉ ô được tính như sau:

\[
\operatorname{address}(A[i])=\operatorname{base}(A)+i\times s
\]

Thứ tự **giá trị** không xuất hiện trong công thức địa chỉ. Việc `A[0] <= A[1]` hay không không làm thay đổi khả năng tính trực tiếp vị trí của ô `i`.

```python
unsorted_values = [9, 3, 12, 5, 5]
sorted_values = [3, 5, 5, 9, 12]

print(unsorted_values[2])  # 12
print(sorted_values[2])    # 5
```

Thứ tự dữ liệu chỉ phát huy lợi thế rõ nhất khi **chưa biết chỉ số** và cần tìm theo giá trị hoặc một khoảng giá trị.

## 4. Tìm theo giá trị trên mảng không có thứ tự

Khi cần tìm giá trị `x` trong mảng chưa sắp xếp, việc đọc `A[0]` không cho phép loại trừ phần cuối mảng: dù `A[0] < x` hay `A[0] > x`, giá trị `x` vẫn có thể ở bất kỳ vị trí nào chưa đọc. Cách tổng quát là **tìm kiếm tuyến tính** (*linear search*).

```python
def linear_search(values: list[int], target: int) -> int | None:
    """Trả về vị trí đầu tiên của target, hoặc None nếu không có."""
    for index, value in enumerate(values):
        if value == target:
            return index
    return None


values = [9, 3, 12, 5, 5]
print(linear_search(values, 12))  # 2
print(linear_search(values, 5))   # 3
print(linear_search(values, 7))   # None
print(linear_search([], 5))       # None
```

- **Tốt nhất:** phần tử đầu tiên khớp, cần một phép so sánh, `O(1)`.
- **Xấu nhất:** phần tử ở cuối hoặc không tồn tại, phải kiểm tra `n` phần tử, `O(n)`.
- **Bộ nhớ phụ:** `O(1)` nếu chỉ lưu chỉ số hoặc kết quả đơn lẻ.

Nếu cần tìm **tất cả** các chỉ số của giá trị `5`, ta phải duyệt hết và thu được `[3, 4]`. Thu thập `k` kết quả cần thêm `O(k)` bộ nhớ và ít nhất `O(k)` thời gian để xuất chúng.

Việc mảng không sắp xếp vẫn có thể có những **quy luật khác**: nếu phần tử có thể được tính từ vị trí, hoặc nếu đã có bảng băm phụ, không nhất thiết phải tìm tuyến tính. Đánh giá `O(n)` ở đây áp dụng cho trường hợp tổng quát **không có bất biến hoặc chỉ mục nào hỗ trợ tìm theo giá trị**.

## 5. Mảng có thứ tự cho phép tìm kiếm nhị phân

Với mảng không giảm, khi so sánh `x` với phần tử giữa:

- Nếu phần tử giữa **nhỏ hơn** `x`, mọi phần tử nằm trước hoặc tại giữa cũng nhỏ hơn `x`; có thể loại bỏ nửa trái.
- Nếu phần tử giữa **lớn hơn hoặc bằng** `x`, vị trí đầu tiên không nhỏ hơn `x` phải nằm ở giữa hoặc bên trái; có thể loại bỏ các vị trí phía sau giữa.

Đây là cơ sở của **tìm kiếm nhị phân** (*binary search*). Ta sẽ tìm *lower bound*: chỉ số đầu tiên có giá trị `>= target`.

```python
def lower_bound(values: list[int], target: int) -> int:
    """values phải được sắp theo thứ tự không giảm."""
    left, right = 0, len(values)  # Đoạn ứng viên [left, right)

    while left < right:
        middle = left + (right - left) // 2
        if values[middle] < target:
            left = middle + 1
        else:
            right = middle

    return left


values = [3, 5, 5, 9, 12]
print(lower_bound(values, 5))   # 1
print(lower_bound(values, 8))   # 3 (vị trí chèn 8)
print(lower_bound(values, 20))  # 5 (vị trí sau phần tử cuối)
```

Trong mỗi vòng lặp, bất biến phạm vi là `0 <= left <= right <= n`; đoạn đang xét thu hẹp mà vẫn giữ vị trí *lower bound* cần tìm. Khi `left < right`, `middle < n` nên phép đọc `values[middle]` hợp lệ. Mỗi bước giảm khoảng ứng viên gần một nửa, vì vậy thuật toán tốn **`O(log n)` thời gian** với `n >= 2` (các mảng nhỏ hoặc rỗng xử lý trong thời gian hằng số), và **`O(1)` bộ nhớ phụ** ở bản lặp.

**Chỉ số trả về không nhất thiết chỉ vào phần tử bằng mục tiêu.** Khi tìm `8`, kết quả `3` chỉ là vị trí có thể chèn `8` để giữ thứ tự. Muốn kiểm tra sự tồn tại, phải kiểm tra cả giới hạn và giá trị:

```python
def contains_sorted(values: list[int], target: int) -> bool:
    position = lower_bound(values, target)
    return position < len(values) and values[position] == target


print(contains_sorted([3, 5, 5, 9, 12], 5))  # True
print(contains_sorted([3, 5, 5, 9, 12], 8))  # False
```

**Điều kiện bắt buộc:** nếu mảng chưa sắp xếp hoặc đã bị một cập nhật phá vỡ thứ tự, kết quả nhị phân không đáng tin. Nếu mảng được sắp **giảm dần**, phải thay đổi quy tắc so sánh tương ứng. Trong Python, biểu thức `target in values` đối với kiểu `list` vẫn kiểm tra tuyến tính `O(n)` ở trường hợp xấu nhất, dù các phần tử đang được sắp xếp; muốn tận dụng thứ tự phải gọi thuật toán tìm nhị phân hoặc giao diện thư viện thích hợp.

## 6. Giá trị trùng nhau: tìm một vị trí và tìm cả đoạn

Mảng không giảm có thể chứa cùng giá trị ở nhiều vị trí liên tiếp:

```text
Giá trị: [2,  5,  5,  5,  9, 12]
Chỉ số:   0   1   2   3   4   5
                 └── các số 5 nằm trong đoạn [1, 4)
```

Một phép tìm nhị phân thông thường có thể chỉ trả về *một* vị trí khớp, không nhất thiết là vị trí đầu tiên. Để tìm đoạn các phần tử bằng `x`, hãy tính:

- `left` (*lower bound*): vị trí đầu tiên có giá trị `>= x`.
- `right` (*upper bound*): vị trí đầu tiên có giá trị `> x`.

Khi ấy, tất cả các phần tử bằng `x` nằm trong khoảng nửa kín **`[left, right)`**, và số lần xuất hiện là `right - left`.

```python
from bisect import bisect_left, bisect_right

scores = [2, 5, 5, 5, 9, 12]
left = bisect_left(scores, 5)
right = bisect_right(scores, 5)
print(left, right)   # 1 4
print(right - left)  # 3

missing_left = bisect_left(scores, 7)
missing_right = bisect_right(scores, 7)
print(missing_left == missing_right)  # True: không có số 7
```

Hai phép tìm cận trên mảng không giảm cần `O(log n)` thời gian; đếm phần tử chỉ cần phép trừ `O(1)`. Nhưng nếu phải **trả về đủ `k` bản ghi khớp**, chi phí lấy hoặc xuất kết quả vẫn là `O(k)`. Các giá trị trùng có thể cần thêm khóa phụ, như `(điểm, mã học sinh)`, nếu ứng dụng muốn một thứ tự xác định giữa các bản ghi cùng điểm.

## 7. Chèn vào mảng chưa sắp xếp

Không có bất biến sắp xếp, ta có thể **thêm vào cuối** mà không cần tìm vị trí đúng theo giá trị:

```python
values = [9, 3, 12, 5, 5]
values.append(7)
print(values)  # [9, 3, 12, 5, 5, 7]
```

Với mảng động có đủ sức chứa, ghi thêm vào cuối mất `O(1)`. Khi phải cấp phát vùng chứa lớn hơn, một lần thêm có thể tốn `O(n)`, nhưng với cơ chế tăng sức chứa theo tỷ lệ, thêm cuối thường đạt **`O(1)` khấu hao** (*amortized*).

Nếu yêu cầu là **chèn đúng tại vị trí `i` mà vẫn bảo toàn thứ tự xuất hiện của các phần tử cũ**, mảng chưa sắp xếp cũng phải dịch các phần tử từ `i` đến `n-1` sang phải, tốn `O(n)` trong trường hợp xấu nhất. “Không sắp xếp theo giá trị” **không có nghĩa** được tùy tiện đổi thứ tự thời gian hoặc thứ tự nghiệp vụ mà ứng dụng cần giữ.

## 8. Chèn vào mảng có thứ tự

Với mảng đã sắp tăng dần, giá trị mới phải được đặt đúng vị trí để **duy trì bất biến**.

Ví dụ chèn `7` vào `[3, 5, 5, 9, 12]`:

```text
Trước:     [ 3 | 5 | 5 | 9 | 12 | _ ]    n = 5
Tìm vị trí:            ↑ chèn trước 9, tại i = 3
Dịch phải: [ 3 | 5 | 5 | 9 |  9 | 12]
Ghi 7:     [ 3 | 5 | 5 | 7 |  9 | 12]    n = 6
```

Có hai giai đoạn:

1. **Tìm vị trí chèn** bằng tìm nhị phân: `O(log n)`.
2. **Dịch các ô từ vị trí chèn về cuối** để tạo chỗ: tối đa `O(n)`, cộng chi phí cấp phát lại nếu mảng động đầy.

Tổng thời gian trong trường hợp xấu nhất là **`O(n)`**, dù bước tìm vị trí chỉ tốn `O(log n)`.

```python
from bisect import bisect_left, insort_left

sorted_values = [3, 5, 5, 9, 12]
position = bisect_left(sorted_values, 7)
print(position)  # 3

insort_left(sorted_values, 7)
print(sorted_values)  # [3, 5, 5, 7, 9, 12]
```

`insort_left` tìm vị trí theo thứ tự rồi chèn vào `list`. Tổng chi phí vẫn **`O(n)`**, vì `list.insert` có thể phải dịch nhiều ô. Khi chèn một giá trị bằng phần tử đã tồn tại, `bisect_left` chọn vị trí **trước** nhóm bằng nhau, còn `bisect_right` chọn vị trí **sau** nhóm ấy. Đây là quy ước đặt phần tử trùng; nếu cần bảo đảm tính ổn định cho các bản ghi có khóa bằng nhau, hãy chọn cách đặt phù hợp với yêu cầu nghiệp vụ.

**Ngoại lệ có lợi:** nếu giá trị mới `x >= A[n-1]` và mảng không rỗng đang sắp không giảm, chỉ cần thêm cuối; thao tác này có thể có chi phí `O(1)` khấu hao. Với mảng rỗng, thêm phần tử đầu tiên cũng không cần dịch.

## 9. Xóa phần tử: tìm nhanh chưa chắc xóa nhanh

Nếu biết trước chỉ số `i` và **phải giữ nguyên thứ tự các phần tử còn lại**, cả hai loại mảng đều phải dồn `n-i-1` phần tử phía sau sang trái. Xóa đầu hoặc giữa tốn `O(n)` trong trường hợp xấu nhất, còn xóa cuối thường `O(1)`.

Nếu chỉ biết **giá trị** cần xóa:

| Mảng | Tìm vị trí cần xóa | Xóa sau khi tìm vị trí | Tổng trường hợp xấu nhất |
|---|---|---|---|
| Chưa sắp xếp, giữ thứ tự phần tử cũ | Tuyến tính `O(n)` | Dịch trái `O(n)` | `O(n)` |
| Đã sắp không giảm | Nhị phân `O(log n)` | Dịch trái `O(n)` | `O(n)` |

Chẳng hạn, xóa một số `5` khỏi `[3, 5, 5, 9, 12]` cần tìm chỉ số `1` hoặc `2`, rồi thu gọn mảng để được `[3, 5, 9, 12]`. Mảng vẫn sắp vì xóa một phần tử không làm sai quan hệ không giảm giữa các phần tử còn lại.

Khi **không cần giữ thứ tự** của mảng chưa sắp xếp, có một cách xóa nhanh nếu **đã biết chỉ số**: thay ô cần xóa bằng phần tử cuối và bỏ ô cuối. Thao tác này tốn `O(1)` thời gian (thường gặp với mảng động) nhưng làm thay đổi thứ tự hiện tại:

```python
values = [9, 3, 12, 5, 5]
index = 1
values[index] = values[-1]
values.pop()
print(values)  # [9, 5, 12, 5]
```

**Không dùng cách này cho mảng đã sắp**, vì thay phần tử giữa bằng giá trị cuối có thể phá vỡ bất biến sắp xếp. Hơn nữa, nếu phải tìm giá trị trước khi xóa trên mảng chưa sắp, tổng chi phí vẫn có thể là `O(n)` do bước tìm kiếm.

## 10. Cập nhật một phần tử có thể phá vỡ trật tự

Gán `A[i] = x` trên mảng chưa sắp xếp thường là `O(1)` và không vi phạm bất biến sắp xếp nào. Với mảng có thứ tự, phép gán vẫn nhanh về mặt ghi ô nhưng **không bảo đảm mảng còn sắp**.

```text
Trước: [3, 5, 5, 9, 12]   (đúng)
Gán A[1] = 11
Sau:   [3,11, 5, 9, 12]   (sai vì 11 > 5)
```

Để giữ bất biến không giảm khi thay `A[i]` bằng `x`, có thể kiểm tra hai phần tử lân cận:

\[
(i=0\;\text{hoặc}\;A[i-1]\le x)
\quad\text{và}\quad
(i=n-1\;\text{hoặc}\;x\le A[i+1])
\]

Nếu cả hai điều kiện đúng, phép gán trực tiếp là an toàn. Nếu sai, phải định vị lại phần tử (hoặc sắp xếp lại), thường có bước dịch `O(n)`.

Một cách đơn giản trong Python là xóa phần tử cũ rồi chèn giá trị mới bằng vị trí tìm nhị phân:

```python
from bisect import insort_right

def replace_sorted_at(values: list[int], index: int, new_value: int) -> None:
    """Giữ list ở thứ tự không giảm sau khi thay phần tử tại index."""
    if not 0 <= index < len(values):
        raise IndexError("Chỉ số không hợp lệ")
    values.pop(index)                  # Có thể dịch O(n) ô
    insort_right(values, new_value)    # Tìm O(log n), chèn O(n)


data = [3, 5, 5, 9, 12]
replace_sorted_at(data, 1, 11)
print(data)  # [3, 5, 9, 11, 12]
```

Đổi vị trí của phần tử có thể ảnh hưởng đến mối liên hệ giữa **chỉ số** và đối tượng nghiệp vụ. Nếu các phần tử là bản ghi có định danh, hãy luôn giữ định danh cùng dữ liệu khi di chuyển; không sử dụng chỉ số trong mảng sắp xếp làm mã định danh ổn định.

## 11. Đánh đổi khi có nhiều truy vấn

Sắp xếp một mảng có `n` phần tử bằng thuật toán so sánh hiệu quả thường cần **`O(n log n)` thời gian**; lượng bộ nhớ phụ phụ thuộc thuật toán và thư viện. Trong Python, `list.sort()` sắp xếp tại chỗ về mặt danh sách (không tạo `list` kết quả khác), nhưng có thể dùng thêm bộ nhớ tạm; `sorted(values)` tạo danh sách mới.

```python
original = [9, 3, 12, 5, 5]
ordered = sorted(original)

print(original)  # [9, 3, 12, 5, 5]: giữ nguyên
print(ordered)   # [3, 5, 5, 9, 12]
```

Giả sử mảng gần như không thay đổi và có `q` truy vấn **kiểm tra sự tồn tại của giá trị**:

\[
\begin{aligned}
\text{Duyệt tuyến tính mỗi lần:}&\quad O(qn)\\
\text{Sắp xếp một lần, rồi tìm nhị phân:}&\quad O(n\log n+q\log n)
\end{aligned}
\]

Cách thứ hai có thể tiết kiệm thời gian khi `q` đủ lớn. Tuy nhiên, sắp xếp **có thể làm mất thứ tự ban đầu**; nếu thứ tự ghi nhận phải được giữ, hãy sắp một bản sao, giữ kèm chỉ số gốc, hoặc sử dụng chỉ mục phụ. Việc sắp mảng không trực tiếp cải thiện tra cứu bằng **mã định danh khác với khóa sắp xếp**.

Nếu dữ liệu có rất nhiều lần **chèn, xóa, cập nhật ở giữa**, việc duy trì mảng sắp xếp có thể tốn `O(n)` sau mỗi thao tác, khiến lợi thế tìm nhị phân không đủ bù. Lúc ấy có thể cân nhắc:

- **Bảng băm** khi nhiệm vụ chủ yếu là tra theo khóa và không cần thứ tự giá trị; tra cứu trung bình thường `O(1)`, đổi lại thêm bộ nhớ cho chỉ mục.
- **Cây tìm kiếm cân bằng** khi cần vừa duy trì thứ tự vừa tìm, chèn, xóa theo khóa thường `O(log n)`, với chi phí con trỏ và cấu trúc nút.
- **Heap** khi chỉ cần lấy phần tử nhỏ nhất/lớn nhất nhiều lần, thay vì tìm mọi giá trị hay duyệt toàn bộ mảng đã sắp; phần tử ưu tiên nhất ở gốc, cập nhật heap thường `O(log n)`.

Không có lựa chọn nào tốt nhất cho mọi yêu cầu. Cần xem đồng thời thời gian thực hiện, bộ nhớ, tần suất cập nhật và kiểu truy vấn.

## 12. Bảng so sánh thao tác

Giả sử hai mảng đều dùng cách lưu trữ hỗ trợ truy cập trực tiếp; mảng được sắp theo thứ tự không giảm, mảng còn lại không có chỉ mục phụ. `n` là số phần tử hiện tại.

| Thao tác | Mảng chưa sắp xếp | Mảng có thứ tự |
|---|---|---|
| Đọc `A[i]` khi đã biết chỉ số | `O(1)` | `O(1)` |
| Tìm một giá trị bất kỳ | `O(n)` xấu nhất bằng duyệt | `O(log n)` bằng tìm nhị phân |
| Đếm số lần xuất hiện của một giá trị | `O(n)` | `O(log n)` bằng hai cận trên mảng đã sắp |
| Lấy nhỏ nhất/lớn nhất, với `n > 0` | `O(n)` nếu chưa có thông tin phụ | `O(1)` ở đầu/cuối mảng tăng dần |
| Thêm giá trị mới | Cuối mảng: `O(1)` khấu hao | Tìm chỗ `O(log n)` + dịch `O(n)`, tổng `O(n)` xấu nhất |
| Xóa theo vị trí, giữ thứ tự các phần tử còn lại | `O(n)` xấu nhất | `O(n)` xấu nhất |
| Xóa theo giá trị, giữ thứ tự | Tìm `O(n)` + dịch `O(n)` | Tìm `O(log n)` + dịch `O(n)` |
| Gán giá trị tại vị trí `i` | `O(1)` | Gán `O(1)` nếu vẫn đúng thứ tự; trường hợp cần đặt lại vị trí có thể `O(n)` |
| Duyệt đủ `n` phần tử | `O(n)` | `O(n)` |

Mỗi hàng mô tả thao tác và điều kiện cụ thể: chẳng hạn, **đếm** bằng hai cận là `O(log n)`, nhưng xuất ra `k` phần tử có cùng giá trị vẫn cần thêm `O(k)`. Với mảng động, một lần cấp phát lại có thể làm thao tác thêm cuối đắt hơn mức trung bình khấu hao. Chi phí so sánh được xem là hằng số trong bảng.

## 13. Ví dụ chọn cách lưu trong ứng dụng thực tế

Một ứng dụng có danh sách các lần đo nhiệt độ:

```text
Thời điểm: 08:00   08:01   08:02   08:03
Giá trị:     31      28      30      28
```

**Nhu cầu A: hiển thị lịch sử theo thời gian.** Giữ mảng theo thứ tự ghi nhận `[31, 28, 30, 28]` phù hợp. Người dùng cuộn các bản ghi theo vị trí, dữ liệu mới chỉ cần thêm cuối. Sắp xếp trực tiếp theo nhiệt độ sẽ làm mất thứ tự thời gian của lịch sử.

**Nhu cầu B: thỉnh thoảng hỏi “có bản ghi nào bằng 30°C không?”.** Duyệt tuyến tính có thể đủ đơn giản, đặc biệt nếu dữ liệu nhỏ.

**Nhu cầu C: thường xuyên hỏi “bao nhiêu bản ghi có nhiệt độ từ 28°C đến 30°C?”.** Có thể tạo **bản sao sắp theo nhiệt độ**: `[28, 28, 30, 31]`, rồi dùng hai cận tìm kiếm nhị phân để xác định số phần tử trong khoảng. Khi dữ liệu thay đổi, bản sao này phải được cập nhật hoặc xây lại.

**Nhu cầu D: tìm theo mã cảm biến duy nhất.** Sắp theo nhiệt độ không hỗ trợ trực tiếp tìm mã cảm biến. Nếu đây là truy vấn chính, bảng băm từ mã đến bản ghi có thể hợp lý hơn.

Chọn cách lưu dựa trên **khóa cần tra, thứ tự cần bảo toàn và số lần cập nhật**, thay vì chỉ nhìn một cột độ phức tạp.

## 14. Những sai lầm thường gặp

1. **Hiểu mảng chưa sắp xếp là không có vị trí.** Mọi phần tử vẫn có chỉ số; chỉ không có quy luật giá trị tăng/giảm bắt buộc.
2. **Dùng tìm nhị phân trên mảng chưa sắp xếp.** Việc loại một nửa dựa trên bất biến sắp xếp; thiếu bất biến thì thuật toán có thể bỏ mất kết quả.
3. **Nhầm tìm nhanh với chèn/xóa nhanh.** Mảng có thứ tự tìm vị trí `O(log n)`, nhưng dịch phần tử khi chèn/xóa vẫn có thể mất `O(n)`.
4. **Mặc định mảng sắp không có giá trị trùng.** Dãy không giảm cho phép trùng; muốn tìm hết phải dùng đoạn `[lower_bound, upper_bound)` hoặc duyệt nhóm khớp.
5. **Coi `x in sorted_list` của Python là tìm nhị phân.** `in` trên `list` thường là tìm tuyến tính.
6. **Gán tùy ý vào mảng đã sắp rồi tiếp tục tìm nhị phân.** Một phần tử mới ở sai vị trí có thể phá bất biến và làm kết quả tìm kiếm sai.
7. **Sắp xếp bản ghi nhưng làm mất định danh gốc.** Khi vị trí thay đổi, phải lưu mã hoặc chỉ số gốc nếu ứng dụng còn cần tham chiếu đến đối tượng ban đầu.
8. **Cho rằng mảng chưa sắp xếp luôn được xóa bằng đổi chỗ với phần tử cuối.** Cách đó chỉ đúng nếu không cần giữ thứ tự thời gian, thứ tự nhập hoặc các quy tắc nghiệp vụ khác.

## 15. Bài tập tự kiểm tra

Cho mảng chưa sắp xếp `U = [10, 4, 8, 4, 7]` và bản sắp không giảm `S = [4, 4, 7, 8, 10]`.

1. `U[3]` và `S[3]` là bao nhiêu? Cả hai thao tác đọc theo chỉ số có độ phức tạp nào?
2. Tìm giá trị `7` trong `U` bằng tìm tuyến tính. Trong trường hợp xấu nhất, thuật toán có thể cần kiểm tra bao nhiêu phần tử?
3. Tìm giá trị `4` trong `S` bằng lower bound. Chỉ số đầu tiên là bao nhiêu? Có bao nhiêu lần xuất hiện?
4. Nếu cần chèn `6` vào `S` và vẫn giữ bất biến không giảm, mảng mới là gì? Có bao nhiêu phần tử cũ phải dịch phải nếu vùng đệm đủ chỗ?
5. Nếu chèn `6` vào cuối `U`, mảng mới là gì? Chi phí khấu hao của thao tác thêm cuối trên mảng động thường là bao nhiêu?
6. Thay `S[0]` bằng `9` có giữ đúng thứ tự không giảm không? Đề xuất cách khôi phục bất biến.
7. Một hệ thống cần truy vấn hàng nghìn lần theo giá trị trên tập dữ liệu ít thay đổi, nhưng vẫn phải giữ lịch sử theo thứ tự nhập. Bạn sẽ chọn cách tổ chức dữ liệu nào và vì sao?

### Đáp án gợi ý

1. `U[3] = 4`, `S[3] = 8`. Cả hai truy cập theo chỉ số thường là `O(1)`.
2. Giá trị `7` nằm ở `U[4]`. Trường hợp xấu nhất phải kiểm tra `5` phần tử, tức `O(n)`.
3. Lower bound của `4` là `0`; upper bound là `2`; số lần xuất hiện là `2`.
4. `[4, 4, 6, 7, 8, 10]`. Vị trí chèn `i = 2` trong mảng dài `5`, nên dịch `5 - 2 = 3` phần tử (`7, 8, 10`).
5. `[10, 4, 8, 4, 7, 6]`. Thêm cuối có chi phí `O(1)` khấu hao khi vùng chứa được mở rộng theo tỷ lệ.
6. Không; `[9, 4, 7, 8, 10]` vi phạm `9 <= 4`. Có thể xóa phần tử ở vị trí `0` rồi chèn `9` đúng chỗ, thu được `[4, 7, 8, 9, 10]`.
7. Giữ mảng gốc theo thứ tự nhập và tạo một **bản sao đã sắp xếp** hoặc chỉ mục phụ phục vụ truy vấn. Cách đó không làm mất thứ tự lịch sử; cần tính thêm bộ nhớ và chi phí đồng bộ mỗi khi dữ liệu thay đổi.

## 16. Ghi nhớ

**Mảng có thứ tự** duy trì một bất biến như `A[i] <= A[i+1]`, nhờ đó có thể tìm theo giá trị bằng tìm kiếm nhị phân trong `O(log n)` và truy vấn cận hiệu quả. **Mảng không có thứ tự** không duy trì bất biến sắp xếp nên tìm theo giá trị tổng quát thường cần duyệt `O(n)`, nhưng thêm cuối đơn giản và thường đạt `O(1)` khấu hao. Cả hai đều hỗ trợ truy cập `A[i]` theo chỉ số trong `O(1)`. Đổi lại, mảng có thứ tự phải trả chi phí duy trì trật tự khi chèn, xóa, cập nhật; các thao tác này có thể cần dịch `O(n)` phần tử. Hãy chọn cách tổ chức dựa vào **loại truy vấn, yêu cầu thứ tự, lượng cập nhật và bộ nhớ**, đồng thời kiểm tra bất biến trước khi áp dụng thuật toán tìm kiếm.
