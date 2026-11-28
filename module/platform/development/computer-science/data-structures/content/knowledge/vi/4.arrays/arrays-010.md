# Tìm kiếm tuyến tính và nhị phân nhìn từ yêu cầu biểu diễn

## 1. Không chỉ chọn thuật toán: phải nhìn vào cách lưu dữ liệu

Giả sử hệ thống lưu số điểm bài kiểm tra của một nhóm học viên:

```text
Chỉ số:    0   1   2   3   4   5   6
Điểm:     [8,  3,  9,  5,  3, 10,  7]
```

Khi hỏi “điểm `5` xuất hiện ở đâu?”, ta có thể **đọc lần lượt từng giá trị** cho đến khi gặp `5`. Đây là *tìm kiếm tuyến tính* (*linear search*). Nếu cần trả lời câu hỏi này trên dữ liệu đã sắp xếp:

```text
Chỉ số:    0   1   2   3   4   5   6
Điểm:     [3,  3,  5,  7,  8,  9, 10]
```

Ta có thể so sánh với phần tử ở giữa và loại bỏ một nửa phạm vi ứng viên, tức *tìm kiếm nhị phân* (*binary search*).

Điểm cốt lõi không phải “nhị phân luôn nhanh hơn tuyến tính”. **Độ phức tạp còn phụ thuộc dữ liệu được biểu diễn và truy cập thế nào.** Một danh sách liên kết tuy đã sắp xếp nhưng không cho phép nhảy thẳng đến phần tử giữa trong thời gian hằng số; một luồng dữ liệu chỉ đọc tuần tự có thể chưa biết độ dài và không cho phép quay lại. Ngược lại, mảng dù chưa sắp xếp vẫn hỗ trợ đọc phần tử theo chỉ số `O(1)`, nhưng điều đó không tự biến việc tìm theo *giá trị* thành `O(1)`.

Sau bài này, bạn sẽ có thể:

- Phân biệt yêu cầu biểu diễn của tìm tuyến tính và tìm nhị phân.
- Giải thích vai trò của **thứ tự**, **khả năng truy cập trực tiếp**, **miền chỉ số** và **bất biến tìm kiếm**.
- Viết hai thuật toán với giao diện rõ ràng, xử lý trường hợp rỗng, không tìm thấy và giá trị trùng.
- Phân tích chi phí tìm kiếm trên mảng, danh sách liên kết, deque và luồng dữ liệu.
- Tính cả chi phí sắp xếp, xây chỉ mục, cập nhật và bộ nhớ trước khi chọn cấu trúc.

Đây là phần kiến thức của chương **Mảng** trong học phần **Cấu trúc dữ liệu**, nơi việc hiểu bất biến, thao tác và độ phức tạp thời gian/bộ nhớ giúp lựa chọn giữa mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị.

## 2. Xác định chính xác yêu cầu truy vấn

Với dãy `A` gồm `n` phần tử và một giá trị mục tiêu `x`, các câu hỏi có thể khác nhau:

| Câu hỏi | Kết quả mong muốn | Hệ quả đối với thuật toán |
|---|---|---|
| “Có `x` không?” | `True` hoặc `False` | Có thể dừng ngay khi gặp một phần tử khớp |
| “`x` nằm ở đâu lần đầu?” | Chỉ số đầu tiên hoặc không tìm thấy | Phải xác định quy ước thứ tự và chỉ số |
| “Có bao nhiêu `x`?” | Số lần xuất hiện | Thường phải quét hết, hoặc khai thác thứ tự/chỉ mục |
| “Liệt kê mọi vị trí của `x`” | Danh sách chỉ số | Cần thời gian ít nhất tỷ lệ số kết quả |
| “Vị trí đầu tiên có giá trị `>= x`?” | Cận trái (*lower bound*) | Thích hợp cho dãy không giảm |

Phép `A[i]` có **đầu vào là chỉ số** `i`; tìm kiếm theo giá trị nhận `x` và chưa biết `i`. Với dãy chưa sắp xếp, không tồn tại công thức chung nào để suy ra vị trí từ giá trị.

Trong các ví dụ dưới đây, ta dùng chỉ số bắt đầu từ `0`. Nếu biểu diễn theo mảng có độ dài `n`, một chỉ số phần tử hợp lệ phải thỏa:

\[
0\le i<n.
\]

Vị trí `n` đôi khi được dùng làm **cận phải của khoảng** hoặc **vị trí chèn cuối**, nhưng không phải chỉ số của phần tử hiện có.

## 3. Tìm kiếm tuyến tính đòi hỏi điều gì từ biểu diễn?

**Ý tưởng:** đi qua các phần tử theo một thứ tự xác định, so sánh với `x` và dừng khi đã thỏa yêu cầu.

Để trả lời “có `x` hay không?”, tìm kiếm tuyến tính chỉ cần hai khả năng:

1. Lấy được phần tử tiếp theo từ nguồn dữ liệu.
2. Kiểm tra điều kiện khớp với `x`.

Nó **không yêu cầu dữ liệu đã sắp xếp**, **không cần biết trước độ dài** và **không bắt buộc truy cập ngẫu nhiên theo chỉ số**. Vì vậy, thuật toán phù hợp với mảng, danh sách liên kết, iterator, luồng đọc tuần tự hoặc các bản ghi đang được gửi đến.

### 3.1. Mã Python làm việc với dữ liệu duyệt được

```python
from collections.abc import Iterable


def linear_find_first(source: Iterable[int], target: int) -> int | None:
    """Vị trí đầu tiên trong thứ tự duyệt, hoặc None nếu không có."""
    for position, value in enumerate(source):
        if value == target:
            return position
    return None


values = [8, 3, 9, 5, 3, 10, 7]
print(linear_find_first(values, 5))  # 3
print(linear_find_first(values, 4))  # None
print(linear_find_first([], 5))      # None

# Nguồn sinh phần tử theo yêu cầu, không cần chứa sẵn toàn dãy.
stream = (x * x for x in range(6))
print(linear_find_first(stream, 16))  # 4
```

Với generator, vị trí được trả về là **thứ tự trong phần dữ liệu đã duyệt của lần gọi đó**, không nhất thiết là chỉ số của một mảng lưu ở đâu đó. Generator có thể bị **tiêu thụ** trong quá trình tìm; khi muốn tìm lại từ đầu, phải có khả năng tạo nguồn mới hoặc lưu dữ liệu.

Nếu không tìm thấy, thuật toán phải đi hết nguồn hữu hạn để kết luận. Với **luồng vô hạn**, việc không gặp `x` không đồng nghĩa có thể kết luận “không tồn tại” sau một thời gian hữu hạn; cần giới hạn số phần tử hoặc điều kiện dừng khác.

### 3.2. Độ phức tạp tuyến tính

Giả sử mỗi lần lấy phần tử tiếp theo và so sánh đều tốn `O(1)`, nguồn chứa hữu hạn `n` phần tử:

| Trường hợp | Số phần tử cần xét | Thời gian |
|---|---:|---|
| Phần tử đầu tiên khớp | `1` | `O(1)` |
| Phần tử cuối cùng mới khớp | `n` | `O(n)` |
| Không có `x` | `n` | `O(n)` |
| Mỗi vị trí khớp đầu tiên là đồng khả năng | Trung bình `(n+1)/2` phép kiểm tra | `O(n)` |

Tìm vị trí đầu tiên thường cần **`O(1)` bộ nhớ phụ**, không tính bộ nhớ nguồn. Nếu phải **liệt kê `k` vị trí**, cần ít nhất `O(k)` chỗ để lưu kết quả, nếu lưu chúng vào danh sách. Với nguồn là iterator, thuật toán vẫn chỉ cần lần lượt duyệt; không cần chép toàn bộ `n` phần tử.

**Điểm mạnh của tuyến tính** là yêu cầu biểu diễn tối thiểu. **Giới hạn** là ở trường hợp xấu nhất, nếu chưa có thông tin nào giúp loại trừ phần chưa xem, thuật toán phải kiểm tra mọi phần tử.

## 4. Tìm kiếm nhị phân cần những điều kiện nào?

Tìm nhị phân không chỉ đơn thuần là “chọn phần tử giữa”. Muốn loại bỏ một nửa dãy một cách **đúng đắn và hiệu quả**, ta cần xem xét những điều kiện sau.

### Điều kiện 1: Có quy luật giúp loại trừ nửa phạm vi

Đối với tìm giá trị trên mảng, quy luật thông dụng là **sắp xếp không giảm**:

\[
A[0]\le A[1]\le\cdots\le A[n-1].
\]

Nếu `A[mid] < x`, mọi phần tử ở các vị trí `<= mid` cũng nhỏ hơn `x`, nên không thể là vị trí đầu tiên có giá trị `>= x`. Nếu `A[mid] >= x`, có thể loại bỏ các vị trí phía sau `mid` khi tìm *cận trái*.

Mấu chốt thực sự là tính **đơn điệu của điều kiện cần tìm**: các vị trí không thỏa đứng trước, các vị trí thỏa đứng sau. Dãy giá trị được sắp xếp là một cách bảo đảm điều này.

### Điều kiện 2: Biết phạm vi đang tìm

Thuật toán tìm nhị phân trên mảng thường bắt đầu với độ dài `n` và một đoạn chỉ số `[0,n)`. Nó phải phân biệt giữa **phần tử thực** và **cận loại trừ**; đây là lý do quy ước khoảng nửa kín giúp tránh lỗi lệch một đơn vị.

Khi nguồn dữ liệu là một stream không biết điểm cuối, không thể tự nhiên lấy chỉ số giữa của toàn bộ dữ liệu như đối với mảng có độ dài đã biết.

### Điều kiện 3: Truy cập phần tử giữa đủ nhanh

Nếu biết `mid` mà có thể đọc `A[mid]` trong `O(1)`, mỗi lần so sánh có chi phí hằng số. Số lần so sánh cần thiết chỉ khoảng `O(\log n)`.

Nhưng nếu phải đi tuần tự từ đầu để tới `mid`, lợi thế số lần so sánh không còn đồng nghĩa lợi thế **thời gian tổng thể**. Đây là lý do nhị phân rất phù hợp với mảng có truy cập trực tiếp theo chỉ số, nhưng không phải lựa chọn tự nhiên cho danh sách liên kết.

**Bộ nhớ vật lý liên tiếp là một cách phổ biến để có truy cập `O(1)`, nhưng không phải điều kiện logic bắt buộc.** Một cấu trúc không lưu phần tử trong một khối liên tiếp nhưng vẫn cung cấp phép lấy phần tử tại chỉ số với chi phí `O(1)` cũng có thể tận dụng tìm nhị phân. Ngược lại, một giao diện có cú pháp `obj[i]` nhưng phải đi tuần tự để tới `i` thì chưa đáp ứng yêu cầu thời gian.

### Điều kiện 4: Khóa và phép so sánh phải nhất quán

Dãy phải được sắp theo **chính khóa và thứ tự** mà thuật toán sử dụng. Sắp bản ghi theo điểm không cho phép tìm nhị phân theo mã học viên. Nếu sắp tăng dần nhưng điều kiện so sánh của thuật toán dành cho giảm dần, việc loại bỏ nửa dãy sẽ sai.

Trong trường hợp tổng quát, phép so sánh phải có hành vi phù hợp với quan hệ thứ tự dùng để sắp xếp; những giá trị không so sánh nhất quán (ví dụ một số trường hợp dữ liệu số chứa `NaN`) cần quy tắc xử lý riêng.

### Điều kiện 5: Bất biến không bị phá trong khi tìm

Khi một tác vụ đang tìm kiếm, dãy không được thay đổi theo cách làm sai thứ tự hoặc làm thay đổi các vị trí mà thuật toán đã suy luận. Việc sửa mảng cùng lúc từ luồng khác mà không đồng bộ có thể khiến kết quả không còn hợp lệ, kể cả khi mã tìm nhị phân tự nó đúng.

## 5. Tìm nhị phân bằng khoảng nửa kín và bất biến

Ta xây dựng hàm **`lower_bound`**: trả về vị trí nhỏ nhất `p` sao cho `A[p] >= x`. Nếu mọi phần tử nhỏ hơn `x`, kết quả là `n`. Nhờ đó thuật toán xử lý tự nhiên cả các giá trị **trùng lặp**.

```python
from collections.abc import Sequence


def lower_bound(values: Sequence[int], target: int) -> int:
    """Tiền điều kiện: values đã được sắp xếp không giảm."""
    left, right = 0, len(values)

    while left < right:
        mid = left + (right - left) // 2

        if values[mid] < target:
            left = mid + 1
        else:
            right = mid

    return left


sorted_values = [2, 4, 4, 4, 7, 10]
print(lower_bound(sorted_values, 4))   # 1
print(lower_bound(sorted_values, 5))   # 4
print(lower_bound(sorted_values, 11))  # 6
print(lower_bound([], 4))              # 0
```

Việc khai báo kiểu `Sequence` cho biết hàm cần khả năng lấy độ dài và truy cập theo chỉ số. **Kiểu giao diện không bảo đảm chi phí `O(1)` cho mọi cách triển khai**; đánh giá độ phức tạp dưới đây giả định truy cập `values[mid]` là hằng số, như với `list` hoặc `tuple` Python.

### 5.1. Hiểu từng vòng lặp

Với `A=[2,4,4,4,7,10]` và `target=5`:

| Lần | `left` | `right` | `mid` | `A[mid]` | Cập nhật |
|---:|---:|---:|---:|---:|---|
| 1 | 0 | 6 | 3 | 4 | `left=4` vì `4<5` |
| 2 | 4 | 6 | 5 | 10 | `right=5` vì `10>=5` |
| 3 | 4 | 5 | 4 | 7 | `right=4` vì `7>=5` |

Khi `left==right==4`, vòng lặp dừng. Đây là vị trí chèn `5` để giữ thứ tự, **không phải** vị trí một phần tử bằng `5`, bởi `5` không có trong mảng.

### 5.2. Bất biến giải thích tính đúng

Sau mỗi vòng, duy trì:

\[
0\le left\le right\le n.
\]

Mọi vị trí **đứng trước** `left` đều có giá trị `< target`; mọi vị trí **từ** `right` đến cuối (nếu có) đều có giá trị `>= target`. Như vậy, vị trí đầu tiên có giá trị `>= target` chỉ có thể ở miền biên chưa xác định `[left,right]`, trong đó `n` cũng được phép là đáp án.

- Khi `values[mid] < target`, do dãy không giảm, mọi chỉ số `<= mid` đều không thể là cận trái. Đặt `left=mid+1` là an toàn.
- Khi `values[mid] >= target`, có thể giữ `mid` làm ứng viên và loại các chỉ số lớn hơn bằng `right=mid`.
- Khi `left<right`, luôn có `left<=mid<right<=n`, nên `values[mid]` là truy cập hợp lệ và độ dài đoạn ứng viên giảm.

Vì vậy thuật toán kết thúc và trả đúng cận trái.

### 5.3. Từ cận trái đến kiểm tra tồn tại

```python
def contains_sorted(values: Sequence[int], target: int) -> bool:
    pos = lower_bound(values, target)
    return pos < len(values) and values[pos] == target


data = [2, 4, 4, 4, 7, 10]
print(contains_sorted(data, 4))  # True
print(contains_sorted(data, 5))  # False
print(contains_sorted([], 4))    # False
```

Phải kiểm tra `pos < n` **trước** khi đọc `values[pos]`. Khi `pos=n`, đó là một cận chèn hợp lệ nhưng không phải chỉ số phần tử hiện có.

## 6. Giá trị trùng nhau, cận trái và cận phải

Tìm nhị phân theo điều kiện bằng nhau đơn thuần có thể tìm được **một** phần tử khớp, nhưng không bảo đảm đó là lần xuất hiện đầu tiên. Trên mảng không giảm, mọi phần tử bằng `x` nằm trong một đoạn liên tiếp:

```text
Chỉ số:    0   1   2   3   4   5
Giá trị:  [2,  4,  4,  4,  7, 10]
                └── [1, 4) ──┘
```

Gọi:

- `lo = lower_bound(A,x)`: vị trí đầu tiên có giá trị `>= x`.
- `hi = upper_bound(A,x)`: vị trí đầu tiên có giá trị `> x`.

Khi đó, mọi giá trị bằng `x` nằm trong `[lo,hi)`, số lần xuất hiện là `hi-lo`.

```python
from bisect import bisect_left, bisect_right

values = [2, 4, 4, 4, 7, 10]
lo = bisect_left(values, 4)
hi = bisect_right(values, 4)
print(lo, hi)       # 1 4
print(hi - lo)      # 3

lo = bisect_left(values, 5)
hi = bisect_right(values, 5)
print(lo, hi)       # 4 4: không có 5
```

Trên mảng truy cập trực tiếp, hai cận được tính với **`O(\log n)` lần so sánh**. Việc xuất ra đủ `k` phần tử khớp vẫn cần ít nhất `O(k)` thời gian; thuật toán không thể trả một triệu phần tử trong thời gian hằng số chỉ vì đã tìm được ranh giới của đoạn.

## 7. Mảng, danh sách liên kết, deque và luồng: cùng thuật toán có còn nhanh?

Độ phức tạp phải tính chi phí **truy cập phần tử mà thuật toán cần**, không chỉ số lần thực hiện điều kiện so sánh.

| Biểu diễn | Lấy phần tử kế tiếp | Lấy phần tử ở chỉ số `i` | Dữ liệu có thể sắp xếp? | Chi phí tìm kiếm phù hợp |
|---|---|---|---|---|
| Mảng liên tiếp / mảng động (`list`, `vector`) | `O(1)` mỗi bước | `O(1)` | Có thể duy trì sắp xếp | Tuyến tính `O(n)`; nhị phân `O(\log n)` khi đã sắp |
| Danh sách liên kết đơn | `O(1)` qua liên kết kế tiếp | `O(i)` từ đầu; xấu nhất `O(n)` | Có | Quét tuyến tính `O(n)`; nhảy tới giữa không `O(1)` |
| `collections.deque` của Python | Hiệu quả khi duyệt và thêm/lấy ở đầu/cuối | Truy cập giữa có thể `O(n)` | Có thể chứa dữ liệu đang tăng | Nhị phân theo chỉ số không đạt bảo đảm `O(\log n)` |
| Iterator hoặc stream đọc tuần tự | Thường `O(1)` mỗi phần tử | Thường không có hoặc không thể quay lại | Có thể được phát theo thứ tự | Tuyến tính tự nhiên; nhị phân cần đổi giao diện/biểu diễn |
| Bộ đệm số đã sắp, hỗ trợ chỉ số trực tiếp | `O(1)` mỗi bước | `O(1)` | Có | Nhị phân `O(\log n)` theo mô hình RAM |

### Tại sao danh sách liên kết đã sắp vẫn không lý tưởng cho nhị phân?

```text
Mảng:          [2] [4] [7] [9] [12] [16] [20]
                0   1   2   3    4    5    6
                      A[3] truy cập ngay

Danh sách nối:  2 -> 4 -> 7 -> 9 -> 12 -> 16 -> 20
                Muốn đến nút giữa phải đi theo các liên kết
```

Nếu cài “tìm nhị phân” bằng cách gọi hàm lấy nút thứ `mid` từ đầu trong mỗi bước, mỗi lần lấy giữa có thể mất `O(n)`, dẫn đến **`O(n\log n)` là một cận trên thô** cho cách cài đặt ấy; xét các đường đi cụ thể, nhiều cách chia đoạn có thể đạt `O(n)` tổng thời gian nhưng **không thu được lợi thế `O(\log n)` của mảng**. Một phép duyệt tuyến tính trên danh sách liên kết đã sắp là `O(n)`, đơn giản hơn và thường thích hợp hơn.

Đây không phải là nói “không thể viết thuật toán chia đôi trên danh sách liên kết”. Ta có thể tìm nút giữa bằng hai con trỏ chạy nhanh/chậm hoặc dùng các mốc, nhưng **tổng chi phí đi qua liên kết** vẫn phải được tính. Nếu cần tra cứu theo khóa rất thường xuyên với dữ liệu được cập nhật, cây tìm kiếm cân bằng hoặc một chỉ mục khác thường hợp lý hơn.

### Truy cập theo chỉ số khác với lưu liên tiếp

Nhị phân chỉ cần **giao diện truy cập vị trí nhanh và một thứ tự thích hợp**, không nhất thiết phần tử phải nằm trong đúng một khối byte liên tiếp. Nhưng bố trí liên tiếp thường giúp cache hoạt động tốt hơn; ngược lại, dữ liệu được lưu trên đĩa hoặc qua mạng có thể khiến một lần đọc phần tử giữa mất nhiều thời gian do *seek*, tải trang hoặc truy vấn từ xa.

Khi chi phí đọc một vị trí là `T_{access}(n)` và chi phí so sánh là `T_{cmp}`, tìm nhị phân bằng truy cập theo chỉ số có cận dạng:

\[
O\big((T_{access}(n)+T_{cmp})\log(n+1)\big).
\]

Nếu `T_{access}(n)=O(1)` và `T_{cmp}=O(1)`, ta thu được kết quả quen thuộc. Nhưng nếu truy cập vị trí `i` phải duyệt liên kết hoặc giải nén nhiều dữ liệu, chi phí tổng thể có thể lớn hơn.

## 8. Có thể tìm tuyến tính nhanh hơn nhờ dữ liệu đã sắp xếp không?

**Có, trong một số đầu vào**, nhưng cận xấu nhất vẫn là `O(n)`. Trên dãy không giảm, ta có thể dừng khi thấy phần tử lớn hơn mục tiêu vì các phần tử phía sau không thể bằng mục tiêu.

```python
def linear_find_sorted(values: list[int], target: int) -> int | None:
    """Duyệt tuần tự; values phải sắp không giảm."""
    for i, value in enumerate(values):
        if value == target:
            return i
        if value > target:
            return None
    return None


print(linear_find_sorted([2, 4, 7, 9, 12], 5))   # None (dừng ở 7)
print(linear_find_sorted([2, 4, 7, 9, 12], 12))  # 4
```

Điều này có ích khi dữ liệu sắp xếp **nhưng chỉ có thể duyệt tuần tự**, như danh sách liên kết hoặc stream đã được sắp. Một phép quét có thể dừng sớm, trong khi nhị phân trên cấu trúc không hỗ trợ truy cập vị trí vẫn phải trả giá cho việc đến giữa.

Nếu dãy chưa sắp xếp, câu lệnh `if value > target: return None` không hợp lệ: một giá trị lớn ở đầu không loại trừ một giá trị bằng mục tiêu ở cuối.

## 9. Chi phí biến dữ liệu thành biểu diễn hỗ trợ tìm kiếm

Giả sử có `n` bản ghi **chưa sắp xếp** và dự kiến có `q` lần truy vấn kiểm tra sự tồn tại của một khóa:

### Phương án A: tìm tuyến tính mỗi lần

- Không cần chuẩn bị.
- Mỗi truy vấn mất `O(n)` trong trường hợp xấu nhất.
- Tổng `q` truy vấn: `O(qn)`.
- Bộ nhớ phụ mỗi truy vấn: `O(1)` nếu chỉ cần trả về một chỉ số/cờ tồn tại.

### Phương án B: sắp xếp một lần, rồi tìm nhị phân

- Sắp xếp so sánh tổng quát: thường `O(n\log n)`.
- Mỗi truy vấn: `O(\log n)` với truy cập chỉ số và so sánh hằng số.
- Tổng: `O(n\log n+q\log n)`.
- Bộ nhớ phụ khi sắp xếp tùy thuật toán; nếu tạo bản sao để giữ thứ tự gốc, cần thêm `O(n)` ô tham chiếu hoặc dữ liệu.

Khi `q` đủ lớn và dữ liệu ít cập nhật, chi phí chuẩn bị có thể được bù. Nhưng nếu phải giữ thứ tự gốc như lịch sử giao dịch, việc **sắp xếp trực tiếp mảng gốc sẽ làm thay đổi ý nghĩa các vị trí**. Khi cần tìm vị trí ban đầu, nên lưu thêm chỉ số gốc hoặc định danh bền vững.

### Phương án C: xây bảng băm theo khóa

- Xây chỉ mục thường mất `O(n)` thời gian kỳ vọng và `O(n)` bộ nhớ.
- Tra sự tồn tại theo khóa thường `O(1)` thời gian trung bình (không bảo đảm trong mọi trường hợp va chạm băm).
- Không tự hỗ trợ truy vấn có thứ tự như “mọi khóa trong khoảng `[a,b]`”.
- Cần đồng bộ chỉ mục khi các bản ghi thay đổi hoặc bị xóa.

### Bảng so sánh

| Cách tiếp cận | Chuẩn bị | Một truy vấn tồn tại | Bộ nhớ phụ chính | Phù hợp khi |
|---|---|---|---|---|
| Duyệt tuyến tính | Không | `O(n)` xấu nhất | `O(1)` | Ít truy vấn, nguồn chỉ duyệt tuần tự |
| Sắp mảng + nhị phân | `O(n\log n)` | `O(\log n)` | Tùy cách sắp; bản sao `O(n)` | Nhiều truy vấn và cần thứ tự hoặc truy vấn cận |
| Chỉ mục bảng băm | `O(n)` kỳ vọng | `O(1)` trung bình | `O(n)` | Nhiều truy vấn khóa chính xác, không cần duy trì thứ tự |
| Cây tìm kiếm cân bằng | Cài đặt/xây cấu trúc theo khóa | `O(\log n)` | `O(n)` nút và liên kết | Vừa tra theo thứ tự, vừa thêm/xóa thường xuyên |

**Sắp xếp không làm chèn/xóa ở giữa mảng trở thành nhanh.** Chèn một giá trị mới đúng vị trí trong mảng đã sắp có thể tìm vị trí bằng nhị phân `O(\log n)`, nhưng vẫn phải dịch `O(n)` ô trong trường hợp xấu nhất. Khi các cập nhật diễn ra nhiều, chi phí duy trì biểu diễn có thể quan trọng hơn chi phí một lần tìm.

## 10. Trường hợp bản ghi: sắp theo khóa nào?

Xét danh sách học viên theo thứ tự đăng ký:

```python
students = [
    {"id": "SV12", "score": 8},
    {"id": "SV07", "score": 5},
    {"id": "SV30", "score": 9},
    {"id": "SV15", "score": 5},
]
```

Mục tiêu là tìm học viên có điểm `5` nhưng vẫn giữ thứ tự đăng ký của `students`. Nếu sắp trực tiếp danh sách theo điểm, chỉ số trong danh sách gốc sẽ bị thay đổi. Ta có thể tạo **chỉ mục phụ** gồm `(điểm, chỉ_số_gốc)`:

```python
from bisect import bisect_left, bisect_right

by_score = sorted(
    (student["score"], index)
    for index, student in enumerate(students)
)

print(by_score)  # [(5, 1), (5, 3), (8, 0), (9, 2)]

scores = [score for score, _ in by_score]
lo = bisect_left(scores, 5)
hi = bisect_right(scores, 5)

original_indices = [index for _, index in by_score[lo:hi]]
print(original_indices)              # [1, 3]
print([students[i]["id"] for i in original_indices])  # ['SV07', 'SV15']
```

Ở đây:

- `students` vẫn giữ thứ tự đăng ký.
- `by_score` được sắp theo `score` rồi `index`; cặp khóa làm thứ tự xác định khi trùng điểm.
- `scores` là dãy khóa không giảm để tìm hai cận. Tìm cận mất `O(\log n)`; thu thập `k` kết quả cần thêm `O(k)` thời gian và bộ nhớ.
- Xây chỉ mục ban đầu mất `O(n\log n)` thời gian cho bước sắp xếp và `O(n)` bộ nhớ.

Nếu điểm học viên thay đổi, `by_score` và `scores` có thể không còn khớp với dữ liệu gốc; chương trình phải cập nhật hoặc xây lại chỉ mục trước khi tìm. Một chỉ mục phụ nhanh mà **không được duy trì đúng** sẽ cho kết quả sai.

Ngoài ra, không thể dùng `scores` đã sắp theo `score` để tìm nhị phân theo `id`. Muốn tra `id`, cần một chỉ mục theo `id` hoặc cấu trúc khác phù hợp.

## 11. Tìm kiếm nhị phân tổng quát trên điều kiện đơn điệu

Thứ tự tăng dần của các giá trị là một trường hợp cụ thể. Về bản chất, tìm nhị phân có thể tìm **ranh giới chuyển từ sai sang đúng** của một điều kiện đơn điệu trên các vị trí:

```text
Chỉ số:      0  1  2  3  4  5  6  7
Điều kiện:   F  F  F  T  T  T  T  T
                      ↑ vị trí đầu tiên đúng
```

Chẳng hạn, muốn tìm mức dung lượng nhỏ nhất đáp ứng một tải công việc, nếu điều kiện “dung lượng `c` đủ” có tính đơn điệu (đủ ở mức `c` thì cũng đủ ở mọi mức lớn hơn), ta có thể tìm ranh giới theo **miền giá trị** mà không cần có sẵn mảng các đáp án.

```python
from collections.abc import Callable


def first_true(lo: int, hi: int, predicate: Callable[[int], bool]) -> int:
    """Tìm cận đầu tiên True trên các số nguyên [lo, hi).

    Điều kiện: predicate đơn điệu False rồi True.
    Nếu không có True, trả về hi.
    """
    while lo < hi:
        mid = lo + (hi - lo) // 2
        if predicate(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo


threshold = 37
print(first_true(0, 100, lambda capacity: capacity >= threshold))  # 37
print(first_true(0, 30, lambda capacity: capacity >= threshold))   # 30
```

Ở đây, **yêu cầu biểu diễn** đã đổi từ “có mảng đã sắp và truy cập `A[mid]`” thành “có **miền chỉ số/đáp án hữu hạn** và **hàm kiểm tra điều kiện đơn điệu**”. Nếu mỗi lần kiểm tra `predicate(mid)` tốn `T` thời gian, tổng chi phí là khoảng `O(T\log(hi-lo+1))`, không phải tự động `O(\log n)` với một mảng không tồn tại.

Nếu tính đơn điệu không đúng, ví dụ kết quả điều kiện là `False, True, False, True`, thuật toán có thể loại bỏ nhầm đáp án. Tính đơn điệu là điều kiện đúng đắn, còn chi phí tính `predicate` quyết định hiệu năng.

## 12. Các trường hợp biên và lỗi tư duy thường gặp

| Lỗi hoặc tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tìm nhị phân trên mảng chưa sắp | Không có quy luật loại trừ một nửa | Duyệt tuyến tính hoặc sắp/chỉ mục hóa trước |
| Dãy sắp theo `score` nhưng tìm theo `id` | Khóa tìm khác khóa sắp | Dùng chỉ mục theo đúng khóa |
| Có trùng giá trị và trả về `mid` bất kỳ | Chưa định nghĩa lần xuất hiện nào cần tìm | Dùng lower/upper bound |
| Tìm được vị trí chèn `n` rồi đọc `A[n]` | Nhầm ranh giới với chỉ số phần tử | Kiểm tra `pos < n` trước khi truy cập |
| Mảng rỗng | Đọc `A[0]` khi không có phần tử | Vòng lặp nhị phân trả `0`, tuyến tính trả không tìm thấy |
| Dùng nhị phân trên danh sách liên kết vì nó “đã sắp” | Lấy nút giữa không `O(1)` | Tính cả chi phí đi theo liên kết; cân nhắc quét hoặc đổi cấu trúc |
| Stream chỉ đọc một chiều | Không thể nhảy tới giữa hoặc quay lại | Tìm tuyến tính; muốn nhị phân cần lưu/truy cập lại dữ liệu |
| Không tính chi phí sắp xếp | So sánh một truy vấn `O(n)` với `O(\log n)` thiếu công bằng | Cộng chi phí chuẩn bị khi dữ liệu chưa sắp |
| Sắp mảng gốc mà vẫn dùng chỉ số cũ | Vị trí của bản ghi thay đổi | Giữ định danh/chỉ số gốc hoặc sắp bản sao |
| Cập nhật dữ liệu nhưng không cập nhật chỉ mục | Bất biến và kết quả tra cứu bị sai | Bảo trì hoặc xây lại chỉ mục |
| Dùng `in` trên Python `list` đã sắp và mong `O(\log n)` | `in` vẫn quét tuyến tính | Dùng `bisect` hay thuật toán nhị phân phù hợp |
| Bỏ qua chi phí so sánh khóa dài | Một phép so sánh chưa chắc `O(1)` | Tính thêm chi phí so sánh hoặc tiền xử lý khóa |
| Có dữ liệu `NaN` hoặc quan hệ so sánh không nhất quán | Quy luật thứ tự bị phá | Chuẩn hóa và xác định phép so sánh có tính nhất quán |
| Sửa dãy đồng thời khi đang tìm | Bất biến tìm kiếm có thể không còn đúng | Dùng snapshot, khóa hoặc quy tắc đồng bộ |

Nếu thuật toán sai, hãy kiểm tra theo thứ tự: **truy vấn muốn trả về điều gì?**, **dữ liệu có bất biến nào?**, **lấy phần tử giữa mất bao lâu?**, **khoảng tìm kiếm và cận có đúng không?**.

## 13. Bài tập tự kiểm tra

**Bài 1.** Cho `A=[9,2,7,2,5]`. Có được dùng tìm nhị phân để tìm `7` trực tiếp không? Nếu dùng tìm tuyến tính, vị trí đầu tiên của `2` là bao nhiêu?

**Bài 2.** Mảng `B=[1,3,3,3,8,11]` đã sắp không giảm. Tính `lower_bound(B,3)`, `upper_bound(B,3)` và số lần xuất hiện của `3`.

**Bài 3.** Với cùng mảng `B`, thuật toán `lower_bound(B,7)` trả về gì? Có được đọc `B[pos]` ngay để kết luận phần tử bằng `7` không?

**Bài 4.** Vì sao một danh sách liên kết đã sắp không tự động cho phép tìm nhị phân trong `O(\log n)` thời gian? Phép toán nào có chi phí cao?

**Bài 5.** Một nguồn là generator sinh số theo thứ tự, không cho lấy `source[i]`. Nên bắt đầu với thuật toán nào nếu chỉ cần kiểm tra sự tồn tại của `x`? Khi nào có thể dừng sớm nếu nguồn đã sắp không giảm?

**Bài 6.** Có `n` bản ghi chưa sắp xếp và `q` lần tìm khóa. So sánh tổng thời gian tuyến tính `O(qn)` với việc sắp trước và tìm nhị phân `O(n\log n+q\log n)`. Với ít truy vấn, cách nào có thể hợp lý hơn? Vì sao?

**Bài 7.** Một mảng `records` sắp theo `price`. Có thể tìm nhị phân theo `product_id` hay không? Cần thay đổi gì để hỗ trợ truy vấn theo `product_id`?

**Bài 8.** Giải thích vì sao thuật toán `first_true(0,100,p)` cần `p` đơn điệu. Cho ví dụ một điều kiện không đơn điệu khiến cách chia đôi không đúng.

**Bài 9.** Một phần tử của dãy truy cập ngẫu nhiên mất `O(\log n)` thời gian và phép so sánh `O(1)`. Nếu áp dụng thuật toán nhị phân dựa trên chỉ số, tổng thời gian có cận trên dạng nào? Có còn `O(\log n)` không?

**Bài 10.** Mảng `C=[]` và mảng `D=[4]`. Hãy nêu kết quả `lower_bound(C,4)`, `lower_bound(D,4)`, `lower_bound(D,5)`. Kết quả nào là vị trí chèn cuối?

### Đáp án gợi ý

1. Không, vì `A` chưa sắp. Tìm tuyến tính trả vị trí đầu tiên của `2` là chỉ số `1`.
2. `lower_bound(B,3)=1`, `upper_bound(B,3)=4`; có `4-1=3` phần tử bằng `3`.
3. Trả `4`, nơi phần tử `8` đứng đầu nhóm `>=7`. Phải kiểm tra `B[pos] == 7` và `pos < n`; ở đây `8 != 7` nên không tìm thấy.
4. Muốn lấy phần tử giữa phải đi qua các liên kết, thường tốn `O(n)` theo vị trí; số lần so sánh ít không đủ bảo đảm tổng thời gian `O(\log n)`.
5. Dùng tìm tuyến tính trên iterator. Nếu nguồn đã sắp không giảm, gặp một giá trị `>x` là có thể kết luận không tồn tại `x` ở phần còn lại.
6. Ít truy vấn thì tuyến tính có thể hợp lý hơn vì không mất chi phí sắp, không thay đổi thứ tự và dùng ít bộ nhớ phụ. Với nhiều truy vấn trên dữ liệu ổn định, sắp + nhị phân có thể tiết kiệm tổng thời gian.
7. Không, vì khóa sắp và khóa cần tìm khác nhau. Có thể tạo chỉ mục khác sắp theo `product_id` hoặc dùng bảng băm `product_id → record`.
8. Nếu `p` thay đổi theo dạng `False, True, False, True`, một kết quả ở giữa không chứng minh toàn bộ một nửa có cùng trạng thái; phép loại bỏ nửa dãy có thể bỏ mất vị trí `True` đầu tiên.
9. Khoảng `O(\log n)` lần lấy chỉ số, mỗi lần `O(\log n)`, nên tổng cận trên là `O((\log n)^2)` khi `n>=2`, không còn bảo đảm `O(\log n)`.
10. `lower_bound(C,4)=0`; `lower_bound(D,4)=0`; `lower_bound(D,5)=1`. Kết quả `0` của mảng rỗng và `1` của `D` đều là vị trí chèn cuối tương ứng.

## 14. Ghi nhớ

**Tìm kiếm tuyến tính** chỉ cần khả năng duyệt và so sánh, nên phù hợp với cả mảng chưa sắp xếp, danh sách liên kết và nguồn tuần tự; trường hợp xấu nhất thường là `O(n)`. **Tìm kiếm nhị phân** cần một **quy luật đơn điệu** để loại trừ nửa phạm vi và một cách **lấy phần tử/kiểm tra điều kiện ở giữa đủ nhanh**; với mảng đã sắp xếp, có truy cập chỉ số `O(1)`, thuật toán đạt `O(\log n)`. Dữ liệu được sắp nhưng không hỗ trợ truy cập trực tiếp chưa chắc tìm nhị phân nhanh hơn quét tuyến tính. Khi lựa chọn, hãy tính cả **chi phí biểu diễn, chuẩn bị, so sánh, duy trì thứ tự/chỉ mục và xuất kết quả**, thay vì chỉ so sánh hai công thức độ phức tạp của vòng lặp.
