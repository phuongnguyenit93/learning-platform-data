# Truy cập theo chỉ số và giới hạn của tìm kiếm theo giá trị

## 1. Hai câu hỏi khác nhau về cùng một mảng

Giả sử một phòng thí nghiệm lưu số mẫu đã xử lý trong năm ca làm việc:

```text
Chỉ số ca:        0    1    2    3    4
Số mẫu A[i]:    [18,  25,  12,  25,  30]
```

Ta có thể đặt hai câu hỏi:

- **Truy cập theo chỉ số:** “Ca ở chỉ số `3` xử lý bao nhiêu mẫu?” Biết ngay vị trí `3`, nên chỉ cần đọc `A[3]`, nhận `25`.
- **Tìm kiếm theo giá trị:** “Ca nào đã xử lý `25` mẫu?” Đầu vào là giá trị `25`; cần tìm vị trí tương ứng. Trong ví dụ có **hai** vị trí, `1` và `3`.

Hai thao tác có đầu vào và nhiệm vụ khác nhau. Mảng liên tiếp hỗ trợ truy cập theo chỉ số rất nhanh, nhưng **không tự động hỗ trợ tìm một giá trị nhanh như vậy**.

Sau bài học, bạn có thể:

1. Phân biệt thao tác `A[i]` với việc tìm `i` thỏa `A[i] == x`.
2. Giải thích vì sao truy cập chỉ số thường là `O(1)`, còn tìm kiếm theo giá trị trên mảng chưa sắp xếp có trường hợp xấu nhất `O(n)`.
3. Viết tìm kiếm tuyến tính và xử lý đúng trường hợp không tìm thấy, mảng rỗng và giá trị trùng nhau.
4. Biết khi nào có thể dùng tìm kiếm nhị phân trên mảng đã sắp xếp và khi nào nên tạo bảng băm phụ.
5. Đánh giá đánh đổi giữa thời gian tìm kiếm, chi phí chuẩn bị, bộ nhớ và cập nhật dữ liệu.

Đây là một phân biệt cốt lõi khi học **cấu trúc dữ liệu**. Từ mảng, danh sách liên kết, stack, queue đến bảng băm, cây, heap và đồ thị, mỗi cấu trúc hỗ trợ các kiểu truy cập khác nhau với độ phức tạp thời gian và bộ nhớ khác nhau. Chọn cấu trúc phù hợp nghĩa là chọn theo **câu hỏi ứng dụng cần trả lời thường xuyên nhất**.

## 2. Truy cập theo chỉ số: chỉ số là đầu vào

Cho mảng `A` có `n` phần tử, chỉ số bắt đầu từ `0`. Phép truy cập `A[i]` nhận chỉ số `i` và trả về giá trị tại vị trí đó. Điều kiện truy cập hợp lệ là:

\[
0 \le i < n
\]

Trong mảng liên tiếp có các ô lưu trữ cùng kích thước `s` byte, địa chỉ ô `i` có thể tính trực tiếp:

\[
\operatorname{addr}(A[i])=\operatorname{base}(A)+i\times s
\]

Với `base(A)` là địa chỉ ô đầu tiên, phép tính này không cần duyệt qua các ô đứng trước `i`. Do đó truy cập theo chỉ số thường mất **`O(1)` thời gian** theo mô hình RAM. Việc gán lại giá trị vào một vị trí đã biết cũng thường là `O(1)`:

```python
counts = [18, 25, 12, 25, 30]

print(counts[3])  # 25: đọc ca ở chỉ số 3
counts[2] = 14    # cập nhật ca ở chỉ số 2
print(counts)     # [18, 25, 14, 25, 30]
```

`O(1)` mô tả số bước tăng theo `n`, không hứa hẹn thời gian đo được luôn bằng nhau. Truy cập thực tế còn phụ thuộc bộ nhớ đệm, kiểm tra giới hạn và cách cài đặt ngôn ngữ. `list` trong Python, chẳng hạn, thường là một mảng động chứa **tham chiếu đến đối tượng**; các đối tượng ấy không nhất thiết nằm cạnh nhau, nhưng truy cập phần tử bằng chỉ số vẫn có tính chất thời gian hằng số thông thường.

Nếu `n = 5`, `counts[5]` vượt quá phần tử cuối. Trong Python, `counts[-1]` có nghĩa đặc biệt là phần tử cuối, nhưng đây là quy tắc riêng của ngôn ngữ. Khi thiết kế thuật toán với chỉ số không âm, vẫn cần kiểm tra `0 <= i < n` để tránh hiểu nhầm đầu vào âm.

## 3. Tìm theo giá trị: chưa biết chỉ số

Giả sử cần tìm giá trị `x` trong mảng. Bài toán lúc này là tìm một hoặc nhiều chỉ số thuộc tập:

\[
S_x=\{i\mid 0\le i<n\;\text{và}\;A[i]=x\}
\]

Tập `S_x` có thể có:

- **Không phần tử:** `x` không xuất hiện.
- **Một phần tử:** `x` xuất hiện đúng một lần.
- **Nhiều phần tử:** giá trị `x` lặp lại ở các vị trí khác nhau.

Với `A = [18, 25, 12, 25, 30]`, ta có `S_25 = {1, 3}`, còn `S_99` rỗng. Vì nhiều chỉ số có thể cùng mang một giá trị, ánh xạ từ chỉ số sang giá trị **không nhất thiết có ánh xạ ngược duy nhất**. Cú pháp `A[i]` không cung cấp một công thức chung để tính `i` từ `A[i]`.

Một điểm dễ nhầm: **biết giá trị `25` không có nghĩa có thể truy cập `A[25]` để tìm nó**. `25` là dữ liệu cần tìm, còn chỉ số hợp lệ của mảng chỉ từ `0` đến `4`. Đánh đồng giá trị với chỉ số có thể vừa gây lỗi vượt giới hạn, vừa tạo ra kết quả sai về mặt ý nghĩa.

Trong mảng **chưa sắp xếp, không có chỉ mục phụ và không biết thêm quy luật về dữ liệu**, cách bảo đảm tìm đúng là kiểm tra các phần tử. Từ một vài phần tử đã xem, ta không thể suy ra chắc chắn giá trị cần tìm có nằm ở phần chưa xem hay không.

## 4. Tìm kiếm tuyến tính (*linear search*)

Tìm kiếm tuyến tính đọc lần lượt các phần tử và so sánh với giá trị mục tiêu. Để trả về **vị trí đầu tiên**, ta dừng tại lần khớp đầu tiên:

```python
def find_first(values: list[int], target: int) -> int | None:
    for i in range(len(values)):
        if values[i] == target:
            return i
    return None


data = [18, 25, 12, 25, 30]
print(find_first(data, 25))  # 1
print(find_first(data, 30))  # 4
print(find_first(data, 99))  # None
print(find_first([], 25))    # None
```

Đặc tả của hàm rất quan trọng: trả về **chỉ số đầu tiên** nếu có, hoặc `None` nếu không có. Trả về `None` tránh nhầm với chỉ số âm của Python. Một giao diện khác có thể dùng `-1` để biểu diễn “không tìm thấy”; khi ấy phải kiểm tra kết quả **trước** khi dùng nó để truy cập mảng, vì `values[-1]` lại là phần tử cuối trong Python.

Ví dụ diễn biến tìm `30`:

| Bước | Chỉ số kiểm tra | Giá trị đọc | So với `30` | Kết quả |
|---:|---:|---:|---|---|
| 1 | `0` | `18` | Khác | Tiếp tục |
| 2 | `1` | `25` | Khác | Tiếp tục |
| 3 | `2` | `12` | Khác | Tiếp tục |
| 4 | `3` | `25` | Khác | Tiếp tục |
| 5 | `4` | `30` | Bằng | Trả về `4` |

### Độ phức tạp của tìm kiếm tuyến tính

| Tình huống | Số phần tử tối đa phải kiểm tra | Độ phức tạp |
|---|---:|---|
| Giá trị ở đầu mảng không rỗng | `1` | Tốt nhất `O(1)` |
| Giá trị ở cuối mảng | `n` | Xấu nhất `O(n)` |
| Giá trị không có trong mảng | `n` | `O(n)` |
| Vị trí khớp đầu tiên phân bố đều trên `n` vị trí | Trung bình `(n+1)/2` | `O(n)` |

Đối với mảng rỗng, vòng lặp chạy `0` lần và trả về `None`. Tìm kiếm trên mảng kích thước `n` dùng thêm **`O(1)` bộ nhớ phụ** nếu chỉ giữ một chỉ số và một vài biến đơn giản.

Lý do giới hạn xấu nhất là `O(n)` không xuất phát từ việc mảng truy cập chậm, mà từ việc **chưa biết chỉ số cần truy cập**. Mỗi lần đọc `A[i]` có thể mất `O(1)`, nhưng để kết luận “không có `x`”, thuật toán cần loại trừ cả `n` vị trí nếu không có thông tin phụ.

### Kiểm tra sự tồn tại, vị trí đầu tiên và tất cả vị trí

Các yêu cầu “có hay không”, “ở đâu lần đầu” và “ở những đâu” không giống nhau:

```python
data = [18, 25, 12, 25, 30]

exists = 25 in data            # True
first = data.index(25)         # 1; ném ValueError nếu không tồn tại
count = data.count(25)         # 2
positions = [i for i, v in enumerate(data) if v == 25]  # [1, 3]
```

Trên `list` chưa có chỉ mục phụ, thao tác kiểm tra `in`, tìm bằng `index`, đếm bằng `count` và duyệt để thu thập vị trí đều có **`O(n)` trong trường hợp xấu nhất**. Thu thập danh sách kết quả còn cần `O(k)` bộ nhớ để lưu `k` chỉ số khớp, với `0 <= k <= n`. `index` trả về chỉ số đầu tiên nhưng sẽ phát sinh `ValueError` nếu không tìm thấy; cần xử lý ngoại lệ nếu dữ liệu mục tiêu có thể vắng mặt.

Không nên nói “tìm tất cả vị trí” là `O(1)` chỉ vì giá trị đầu tiên xuất hiện sớm: ngay cả khi phát hiện một phần tử khớp, thuật toán vẫn phải xét các phần tử còn lại để bảo đảm không bỏ sót.

## 5. Ví dụ thực tế: tìm một học sinh theo điểm số

Một lớp học lưu điểm theo thứ tự trong danh sách:

```text
Chỉ số:       0     1     2     3     4
Mã học sinh: HS01  HS02  HS03  HS04  HS05
Điểm:         8     10     7     8     9
```

Nếu giáo viên hỏi “điểm của học sinh ở vị trí số `3` là bao nhiêu?”, có thể đọc ngay `scores[3]` trong `O(1)` nếu danh sách và quy ước chỉ số đã biết. Nếu hỏi “những học sinh nào đạt điểm `8`?”, ta phải tìm **tất cả** vị trí mà giá trị bằng `8`: chỉ số `0` và `3`.

Đoạn mã sau diễn đạt rõ sự khác biệt:

```python
student_ids = ["HS01", "HS02", "HS03", "HS04", "HS05"]
scores = [8, 10, 7, 8, 9]

# Đã biết vị trí: truy cập O(1).
known_index = 3
print(student_ids[known_index], scores[known_index])  # HS04 8

# Chỉ biết điểm: tìm các vị trí khớp, O(n).
result = [student_ids[i] for i, score in enumerate(scores) if score == 8]
print(result)  # ['HS01', 'HS04']
```

Ví dụ cũng cho thấy: **chỉ số là vị trí hiện tại, không phải định danh bền vững của học sinh**. Nếu thêm học sinh vào đầu mảng, các chỉ số cũ thay đổi. Đối với tra cứu theo mã học sinh qua nhiều lần thêm, xóa, một bảng băm ánh xạ `mã → hồ sơ` thường phù hợp hơn một chỉ số tạm thời.

## 6. Sắp xếp dữ liệu có giúp tìm nhanh hơn không?

Khi mảng được **sắp xếp theo đúng tiêu chí tìm kiếm**, ta có thể dùng **tìm kiếm nhị phân** (*binary search*). Mỗi bước so sánh với phần tử ở giữa rồi loại bỏ khoảng một nửa đoạn còn lại. Ví dụ với:

```text
Mảng đã sắp xếp: [3, 7, 7, 9, 11, 15, 18]
Chỉ số:           0  1  2  3   4   5   6
```

Muốn tìm vị trí đầu tiên có giá trị `>= target`, ta có thể dùng **lower bound**:

```python
def lower_bound(values: list[int], target: int) -> int:
    """Chỉ dùng khi values đã sắp xếp không giảm."""
    left, right = 0, len(values)

    while left < right:
        middle = left + (right - left) // 2
        if values[middle] < target:
            left = middle + 1
        else:
            right = middle

    return left


sorted_values = [3, 7, 7, 9, 11, 15, 18]
pos = lower_bound(sorted_values, 7)
if pos < len(sorted_values) and sorted_values[pos] == 7:
    print(pos)  # 1: vị trí đầu tiên có giá trị 7
else:
    print("Không tìm thấy")
```

Thuật toán trên chạy `O(log n)` ở trường hợp xấu nhất và dùng `O(1)` bộ nhớ phụ. Nếu kết quả bằng `n`, đó là **vị trí chèn cuối**, không phải chỉ số phần tử hiện có; phải kiểm tra `pos < n` trước khi truy cập. Với `values = []`, hàm trả về `0` và phép kiểm tra sau đó xác nhận không tìm thấy.

Trong Python, thư viện chuẩn có `bisect.bisect_left(values, target)` cung cấp vị trí tương tự trên dãy được sắp xếp. Phép tìm vị trí là `O(log n)` theo số lần so sánh, nhưng điều kiện **mảng đã sắp xếp** là bắt buộc để kết quả có ý nghĩa.

### Chi phí và giới hạn của việc sắp xếp

Nếu dữ liệu ban đầu chưa sắp xếp, cần tính cả bước chuẩn bị. Sắp xếp so sánh tổng quát thường có chi phí `O(n log n)`; việc đó chỉ đáng làm cho mục đích tìm kiếm khi có đủ nhiều truy vấn hoặc dữ liệu vốn đã được giữ theo thứ tự.

Hơn nữa, **chỉ số sau khi sắp xếp là chỉ số trong thứ tự mới**. Nếu ứng dụng cần chỉ số ở mảng ban đầu, phải lưu cặp `(giá trị, chỉ số gốc)` trước khi sắp xếp. Với dữ liệu có giá trị trùng nhau, tìm được một vị trí bằng nhị phân cũng chưa đồng nghĩa đã lấy hết mọi vị trí; có thể dùng hai cận trái/phải để xác định đoạn các giá trị bằng nhau rồi duyệt đoạn ấy.

Ví dụ:

```python
from bisect import bisect_left, bisect_right

values = [3, 7, 7, 9, 11, 15, 18]  # đã sắp xếp
left = bisect_left(values, 7)
right = bisect_right(values, 7)
print(left, right)        # 1 3
print(values[left:right]) # [7, 7]
```

Hai phép tìm cận có `O(log n)` thời gian; **tạo bản sao lát cắt** `values[left:right]` tốn thêm `O(k)` thời gian và bộ nhớ với `k = right - left`. Nếu chỉ cần số lần xuất hiện, tính `right - left` là đủ. Thêm hoặc xóa giữa một mảng liên tiếp đã sắp xếp vẫn có thể cần dịch chuyển `O(n)` phần tử để duy trì thứ tự.

## 7. Tìm nhiều lần: có nên tạo bảng băm phụ?

Khi phải tìm giá trị rất nhiều lần trên một mảng ít thay đổi, có thể xây **chỉ mục ngược**: ánh xạ từ mỗi giá trị đến danh sách các vị trí mà nó xuất hiện. Bảng băm (*hash table*) có thể triển khai chỉ mục ấy:

```python
def build_positions(values: list[int]) -> dict[int, list[int]]:
    positions: dict[int, list[int]] = {}
    for i, value in enumerate(values):
        positions.setdefault(value, []).append(i)
    return positions


data = [18, 25, 12, 25, 30]
by_value = build_positions(data)

print(by_value.get(25, []))  # [1, 3]
print(by_value.get(99, []))  # []
```

Với các khóa có thể băm (*hashable*) và giả định băm hoạt động tốt:

- Duyệt `n` phần tử để **xây chỉ mục** tốn `O(n)` thời gian kỳ vọng và `O(n)` bộ nhớ phụ.
- Tra cứu **danh sách vị trí** theo một khóa thường tốn `O(1)` thời gian trung bình để lấy tham chiếu đến danh sách; nếu cần duyệt hoặc sao chép `k` kết quả thì thêm `O(k)`.
- Trong những tình huống va chạm băm bất lợi, thao tác bảng băm có thể chậm hơn; không nên hiểu `O(1)` trung bình là bảo đảm tuyệt đối cho mọi đầu vào.

Chi phí cập nhật cần được xét riêng. Nếu thay `data[2]` từ `12` thành `25`, chỉ mục phải xóa vị trí `2` khỏi nhóm `12` và thêm vào nhóm `25`. Nếu **chèn hoặc xóa ở giữa mảng**, nhiều phần tử dịch sang chỉ số mới; chỉ mục lưu chỉ số có thể phải cập nhật hàng loạt, mất `O(n)` hoặc hơn tùy cách tổ chức kết quả. Với dữ liệu thay đổi liên tục, một chỉ mục tự quản lý có thể tạo thêm độ phức tạp và nguy cơ không đồng bộ.

Nếu bài toán thực chất là “tìm hồ sơ theo **mã định danh duy nhất**”, bảng băm dạng `id → record` có thể dùng trực tiếp mà không cần xây danh sách vị trí của một mảng. Đó là lựa chọn cấu trúc dữ liệu theo khóa nghiệp vụ, khác với việc tìm một giá trị bất kỳ nằm trong mảng.

## 8. So sánh ba cách tìm theo giá trị

Giả sử cần hỏi về sự xuất hiện của một giá trị trong `n` phần tử. Bảng sau phân biệt chi phí chuẩn bị, một lần truy vấn và chi phí lưu thêm:

| Phương án | Điều kiện / chuẩn bị | Thời gian một truy vấn | Bộ nhớ phụ | Đánh đổi chính |
|---|---|---|---|---|
| **Duyệt tuyến tính** | Không cần sắp xếp hay tạo chỉ mục | Xấu nhất `O(n)` | `O(1)` nếu chỉ tìm vị trí đầu tiên | Dễ làm, phù hợp ít truy vấn và dữ liệu thay đổi |
| **Tìm kiếm nhị phân** | Mảng đã sắp xếp theo khóa; nếu chưa, cần chuẩn bị, thường `O(n log n)` | `O(log n)` để xác định vị trí hoặc cận | `O(1)` cho thuật toán tìm lặp | Tốt cho nhiều truy vấn, nhưng duy trì thứ tự khi thêm/xóa có thể tốn `O(n)` |
| **Bảng băm phụ** | Xây chỉ mục từ giá trị sang vị trí; thường `O(n)` kỳ vọng | Trung bình `O(1)` để tra khóa, cộng `O(k)` nếu xuất `k` kết quả | `O(n)` | Tra cứu nhanh nhưng cần duy trì chỉ mục khi dữ liệu đổi |

Các số liệu trên nói về truy vấn tìm giá trị; **truy cập `A[i]` khi đã biết chỉ số vẫn thường là `O(1)`** ở cả mảng có hoặc không có sắp xếp. Thao tác tìm và thao tác truy cập là hai phép toán khác nhau.

Nếu có `q` truy vấn độc lập trên mảng tĩnh, cách nhìn sơ bộ về tổng thời gian là:

\[
\begin{aligned}
\text{Tuyến tính:}&\quad O(qn)\\
\text{Sắp xếp + tìm nhị phân:}&\quad O(n\log n+q\log n)\\
\text{Xây bảng băm + tra cứu:}&\quad O(n+q)\;\text{(trung bình, nếu mỗi truy vấn chỉ cần kiểm tra tồn tại)}
\end{aligned}
\]

Đây là các ước lượng theo mô hình tổng quát, **không tính chi phí xuất toàn bộ các kết quả khớp** và giả định các phép so sánh/băm cơ bản là chi phí hằng số. Nếu phải trả về mọi vị trí chứa cùng giá trị, mọi phương án đều có thêm chi phí tối thiểu `O(k)` cho `k` kết quả được xuất ra.

## 9. Các tình huống biên và lỗi dễ mắc

| Tình huống | Sai lầm | Hành vi đúng |
|---|---|---|
| Mảng rỗng | Truy cập `A[0]` trước khi kiểm tra | Trả “không tìm thấy” mà không đọc phần tử |
| Giá trị không tồn tại | Dùng chỉ số nhận được mà không kiểm tra | Trả `None`/cờ trạng thái rõ ràng, hoặc xử lý ngoại lệ |
| Có giá trị lặp | Nghĩ tìm được một chỉ số là tìm được tất cả | Định nghĩa rõ tìm đầu tiên, cuối cùng, tất cả hay đếm |
| Đầu vào là `x`, không phải `i` | Viết `A[x]` để kiểm tra giá trị `x` | Duyệt/tìm trong dữ liệu hoặc tra bảng băm phụ |
| Mảng chưa sắp xếp | Áp dụng tìm kiếm nhị phân | Chỉ dùng nhị phân sau khi bảo đảm thứ tự hợp lệ |
| Sắp xếp mảng | Tưởng chỉ số sau sắp xếp giữ nguyên ý nghĩa | Ghi nhớ chỉ số gốc nếu cần |
| Python trả `-1` khi không tìm thấy (theo quy ước tự chọn) | Dùng `A[-1]` và lấy nhầm phần tử cuối | Kiểm tra trạng thái trước khi truy cập |
| Mảng bị chèn/xóa sau khi tạo chỉ mục | Tiếp tục dùng các vị trí cũ | Cập nhật hoặc xây lại chỉ mục phụ |
| Cần liệt kê `k` kết quả | Báo tổng truy vấn chỉ `O(1)` | Cộng tối thiểu `O(k)` để xuất kết quả |

Trong chương trình thực tế, phần khó không chỉ là viết vòng lặp tìm kiếm mà còn là **định nghĩa chính xác điều cần trả về**: một chỉ số, tập chỉ số, số lần xuất hiện, một đối tượng hay chỉ một giá trị Boolean.

## 10. Cách lựa chọn trong một bài toán cụ thể

Hãy xét hệ thống lưu một triệu cảm biến, mỗi cảm biến có mã định danh, nhiệt độ hiện tại và vị trí trong danh sách hiển thị.

Nếu giao diện cần lấy **cảm biến ở dòng thứ `i`** trong danh sách, mảng là lựa chọn tự nhiên vì có truy cập vị trí trực tiếp. Nếu cần tìm **mọi cảm biến có nhiệt độ bằng `30`** và yêu cầu này chỉ thỉnh thoảng xuất hiện, một vòng duyệt `O(n)` có thể đủ đơn giản và đúng. Nếu cần tra **một cảm biến theo mã duy nhất** hàng nghìn lần mỗi giây, bảng băm `mã → cảm biến` thường phù hợp hơn. Nếu thường xuyên hỏi các cảm biến có nhiệt độ **trong một khoảng**, dữ liệu được sắp xếp theo nhiệt độ hoặc một cấu trúc chỉ mục thứ tự có thể thuận lợi hơn vì hỗ trợ tìm cận và xử lý truy vấn đoạn.

Không có một cấu trúc tối ưu cho mọi thao tác. Trước khi chọn giải pháp, hãy trả lời: dữ liệu có được sắp xếp không, có nhiều giá trị trùng không, có bao nhiêu truy vấn, dữ liệu thay đổi bao lâu một lần, và giới hạn bộ nhớ phụ là bao nhiêu? Những yếu tố này quyết định việc đầu tư thời gian chuẩn bị để tăng tốc tra cứu có đáng hay không.

## 11. Bài tập tự kiểm tra

Cho mảng `B = [6, 2, 6, 9, 1, 6]` và quy ước chỉ số bắt đầu từ `0`:

1. `B[3]` bằng bao nhiêu? Vì sao truy cập này khác với tìm giá trị `3`?
2. Tìm **chỉ số đầu tiên** có giá trị `6`; sau đó tìm **tất cả** chỉ số có giá trị `6`.
3. Nếu tìm giá trị `7` bằng tuyến tính, cần kiểm tra tối đa bao nhiêu phần tử để kết luận không tìm thấy? Độ phức tạp là gì?
4. Có thể áp dụng tìm kiếm nhị phân trực tiếp trên `B` không? Nếu sắp xếp tăng dần được `[1, 2, 6, 6, 6, 9]`, vị trí đầu tiên của `6` trong thứ tự mới là gì?
5. Nếu tạo bảng băm ánh xạ `giá trị → danh sách chỉ số`, mục ứng với khóa `6` nên chứa gì? Khi chèn một phần tử mới ở đầu mảng, điều gì xảy ra với các chỉ số cũ?
6. Đánh giá chi phí tìm một giá trị trong mảng chưa sắp xếp nếu có một truy vấn so với khi có hàng nghìn truy vấn và không có thao tác cập nhật; có cần luôn tạo bảng băm không?

### Gợi ý đáp án

1. `B[3] = 9`. Số `3` ở đây là vị trí; tìm giá trị `3` yêu cầu kiểm tra các phần tử và không có kết quả trong `B`.
2. Chỉ số đầu tiên là `0`; tất cả vị trí là `[0, 2, 5]`.
3. Cần kiểm tra `6` phần tử để kết luận không có `7`; thời gian `O(n)` trong trường hợp xấu nhất.
4. Không, vì `B` chưa sắp xếp. Trong mảng sắp xếp mới, vị trí đầu tiên có `6` là `2`; nó **không phải** một ánh xạ trực tiếp về chỉ số `2` trong dữ liệu ban đầu.
5. Mục `6` chứa `[0, 2, 5]`. Chèn ở đầu khiến mọi phần tử cũ dịch sang phải một vị trí, do đó chỉ mục lưu vị trí phải được cập nhật hoặc xây lại.
6. Với một truy vấn, duyệt tuyến tính thường đơn giản và tránh chi phí chuẩn bị. Với rất nhiều truy vấn trên dữ liệu tĩnh, một chỉ mục có thể tiết kiệm thời gian tổng thể, nhưng cần xét bộ nhớ, chi phí xây chỉ mục và kiểu truy vấn. Không có yêu cầu phải luôn tạo bảng băm.

## 12. Ghi nhớ

**Truy cập theo chỉ số** nhận đầu vào là vị trí `i` và đọc `A[i]`; mảng liên tiếp cho phép thực hiện thao tác này trong thời gian thường là `O(1)`. **Tìm theo giá trị** nhận đầu vào là `x` và phải xác định vị trí nào có `A[i] == x`; trên mảng chưa sắp xếp, không có chỉ mục phụ, tìm tuyến tính có trường hợp xấu nhất `O(n)`. Để tăng tốc tìm kiếm, có thể tận dụng thứ tự đã sắp xếp bằng tìm kiếm nhị phân `O(log n)` hoặc xây bảng băm phụ với tra cứu trung bình `O(1)`; cả hai đều có điều kiện sử dụng và chi phí duy trì. Luôn đánh giá thao tác chính, số lượng truy vấn, tần suất cập nhật, giá trị trùng lặp và bộ nhớ trước khi chọn cấu trúc dữ liệu.
