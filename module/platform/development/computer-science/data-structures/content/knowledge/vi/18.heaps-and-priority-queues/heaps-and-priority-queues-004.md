# Thêm phần tử bằng đẩy lên

Trong một **hàng đợi ưu tiên** (*priority queue*), công việc quan trọng nhất được chọn trước theo **khóa ưu tiên**. Khi cài đặt hàng đợi ưu tiên bằng **heap nhị phân** (*binary heap*), phần tử ưu tiên nhất nằm ở gốc, nhưng toàn bộ cây **không nhất thiết được sắp xếp**.

Vậy khi thêm một phần tử mới vào heap, làm thế nào để vừa giữ cây **gần đầy đủ**, vừa bảo đảm quan hệ ưu tiên giữa các nút? Câu trả lời là thao tác **đẩy lên** (*sift-up*, còn gọi là *bubble-up* hoặc *percolate-up*): đặt phần tử mới tại vị trí cuối mảng rồi liên tục so sánh với cha; nếu phần tử mới ưu tiên hơn cha, đổi chỗ với cha và tiếp tục đi lên.

Bài thuộc chương **Heap và hàng đợi ưu tiên** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Theo định hướng học cấu trúc dữ liệu qua **bất biến, thao tác và độ phức tạp thời gian/bộ nhớ**, chúng ta sẽ phân tích chính xác vì sao thuật toán đẩy lên đúng, khi nào dừng, tốn bao nhiêu chi phí và những lỗi thường gặp khi cài đặt.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhắc lại hai bất biến của heap nhị phân: **hình dạng cây gần đầy đủ** và **quan hệ thứ tự heap**.
- Giải thích vì sao phần tử mới phải được đặt vào **cuối mảng**, không chèn tùy ý vào giữa.
- Tính chỉ số cha bằng công thức **(i − 1) // 2** khi dùng mảng bắt đầu từ 0.
- Mô phỏng từng lượt so sánh và hoán đổi khi **push** một khóa mới vào min-heap và max-heap.
- Nêu điều kiện dừng khi đến gốc hoặc khi cha không còn vi phạm bất biến.
- Trình bày bất biến vòng lặp và giải thích vì sao chỉ cần kiểm tra các cạnh trên đường từ nút mới tới gốc.
- Cài đặt **push/sift_up**, **peek**, và kiểm tra heap bằng Python.
- Phân tích trường hợp tốt nhất, xấu nhất và chi phí mở rộng **mảng động**.
- Xử lý khóa bằng nhau, payload không so sánh được và thứ tự ổn định khi hòa ưu tiên.
- Nhận biết sự khác biệt giữa **sift-up** khi thêm mới và **sift-down** khi lấy gốc.

## 2. Vì sao heap cần bước đẩy lên?

**Binary heap** là một cây nhị phân có hai thuộc tính.

### 2.1. Bất biến hình dạng

Cây **gần đầy đủ** (*complete binary tree*): tất cả các mức trước mức cuối đều đầy, và mức cuối được lấp **từ trái sang phải**, không để lỗ trống trước một nút đang có.

Ví dụ:

~~~text
          3
        /   \
       5     4
      / \   /
     9   8 7
~~~

Nếu thêm một nút mới, vị trí hợp lệ tiếp theo là **con phải của nút có khóa 4**, bởi đó là vị trí còn trống đầu tiên theo thứ tự mức:

~~~text
          3
        /   \
       5     4
      / \   / \
     9   8 7   X
~~~

Không được tự đặt X vào một nhánh sâu hơn hay chuyển thành con của 9, vì như vậy sẽ phá cấu trúc gần đầy đủ.

### 2.2. Bất biến thứ tự

Với **min-heap**, mỗi nút cha có khóa **nhỏ hơn hoặc bằng** khóa của từng nút con:

\[
key(parent) \leq key(child).
\]

Với **max-heap**, mỗi cha có khóa **lớn hơn hoặc bằng** khóa của từng con:

\[
key(parent) \geq key(child).
\]

Cả hai quan hệ cho phép **khóa bằng nhau**. Min-heap không yêu cầu con trái nhỏ hơn con phải; max-heap cũng không yêu cầu toàn bộ mảng giảm dần.

**Vấn đề khi thêm nút mới:** Ta giữ được hình dạng cây bằng cách đặt nút mới vào ô tiếp theo, nhưng nút ấy có thể có khóa ưu tiên hơn cha. Ví dụ, đặt khóa 2 làm con của nút khóa 4 tạo quan hệ **4 > 2**, vi phạm min-heap. Chúng ta chỉ cần sửa **quan hệ thứ tự**, không thay hình dạng.

## 3. Biểu diễn mảng và công thức tìm cha

Heap nhị phân thường được lưu trong một **mảng theo thứ tự mức** (*level-order*). Các nút được đánh số từ trái sang phải, lần lượt theo từng mức.

~~~text
Cây:
                  (0) 3
                  /   \
             (1) 5   (2) 4
              / \      /
         (3) 9 (4) 8 (5) 7

Mảng 0-based:
index:  0  1  2  3  4  5
value: [3, 5, 4, 9, 8, 7]
~~~

Với một nút ở chỉ số **i** trong mảng 0-based:

| Quan hệ | Công thức | Điều kiện |
| --- | --- | --- |
| Gốc | 0 | Heap không rỗng |
| Cha | **(i − 1) // 2** | **i > 0** |
| Con trái | **2i + 1** | Chỉ tồn tại nếu chỉ số nhỏ hơn n |
| Con phải | **2i + 2** | Chỉ tồn tại nếu chỉ số nhỏ hơn n |

Trong đó **n** là số phần tử heap, còn **//** là phép chia nguyên trong Python.

Khi thêm phần tử mới vào cuối mảng ban đầu có n phần tử, nút mới mang chỉ số **i = n**. Bước đầu tiên của sift-up luôn so sánh nút đó với cha ở **(n − 1) // 2**, trừ khi heap trước khi thêm rỗng.

### Lưu ý quan trọng: gốc không có cha

Với **i = 0**, công thức số học trong Python cho ra **(0 − 1) // 2 = −1**, nhưng **−1 không phải chỉ số cha**. Python cho phép truy cập a[-1] như phần tử cuối list, khiến lỗi này có thể rất khó phát hiện.

Do đó, điều kiện **i > 0** phải được kiểm tra **trước** khi lấy cha.

### Phân biệt 0-based với 1-based

Một số giáo trình đánh số gốc là 1. Khi ấy:

~~~text
0-based: parent(i) = (i - 1) // 2
1-based: parent(i) = i // 2
~~~

Không được lấy công thức 1-based áp dụng cho list Python có gốc tại a[0]. Trong bài này, mọi thuật toán dùng **0-based**.

## 4. Hợp đồng của thao tác push

Ở mức **kiểu dữ liệu trừu tượng (ADT)**, thêm một phần tử vào min-priority queue có thể gọi là **insert** hoặc **push**. Khi cài bằng min-heap, một thao tác push thành công cần bảo đảm:

1. Hàng đợi chứa **thêm đúng một entry** so với trước.
2. Những entry cũ vẫn còn; không phần tử nào bị thất lạc.
3. **Hình dạng heap** vẫn là một cây gần đầy đủ.
4. **Quan hệ cha ≤ con** đúng với mọi cạnh.
5. Nếu gốc được chọn làm phần tử ưu tiên nhất, **peek** trả về một entry có khóa nhỏ nhất.
6. Thứ tự giữa các entry có khóa bằng nhau tuân thủ chính sách của ứng dụng, nếu chính sách ấy được quy định.

Heap có thể lưu **giá trị số** hoặc các bản ghi gồm **priority và payload**. Khi chỉ xét giá trị số, mỗi số tự đóng vai trò khóa ưu tiên. Khi dùng entry phức hợp, thao tác sift-up phải so sánh **khóa**, không tùy tiện so sánh các trường dữ liệu không liên quan.

**Push không phải thao tác giữ nguyên chỉ số các phần tử cũ.** Các entry cũ trên đường đi từ nút mới tới gốc có thể bị đổi vị trí. Vì vậy, nếu ứng dụng đang lưu một bảng ánh xạ **ID → chỉ số heap**, mỗi lần hoán đổi phải cập nhật bảng ấy.

## 5. Hai pha của thao tác thêm phần tử

### Pha A: đặt vào cuối mảng

Giả sử min-heap ban đầu:

~~~text
a = [3, 5, 4, 9, 8, 7]
~~~

Ta muốn thêm khóa **2**. Trước hết:

~~~python
a.append(2)
i = len(a) - 1
~~~

Mảng trở thành:

~~~text
index:  0  1  2  3  4  5  6
value: [3, 5, 4, 9, 8, 7, 2]
                         ▲
                       i = 6
~~~

Hình dạng gần đầy đủ được giữ nguyên vì phần tử mới ở đúng ô kế tiếp. Tuy nhiên, nút i = 6 có cha **p = 2** mang khóa **4**, nên bất biến min-heap bị vi phạm tại cạnh **4 → 2**.

### Pha B: đẩy lên (sift-up)

Khi **i > 0**:

1. Tính **p = (i − 1) // 2**.
2. Nếu **a[p] ≤ a[i]**, cha đã không lớn hơn nút hiện tại: **dừng**.
3. Nếu **a[p] > a[i]**, **hoán đổi a[p] và a[i]**.
4. Cập nhật **i = p**, rồi lặp tiếp.

Pseudocode:

~~~text
push_min(heap, x):
    thêm x vào cuối heap
    i = len(heap) - 1

    while i > 0:
        p = (i - 1) // 2

        if heap[p] <= heap[i]:
            break

        hoán đổi heap[p] và heap[i]
        i = p
~~~

**Thứ tự các thao tác quan trọng:** Tính cha trước khi so sánh; kiểm tra **i > 0** để không lấy cha của gốc; cập nhật i về **vị trí mới** của entry vừa đi lên, không giữ nguyên chỉ số cũ sau hoán đổi.

## 6. Mô phỏng chi tiết: push(2) vào min-heap

Giả sử heap ban đầu hợp lệ:

~~~text
                3
              /   \
             5     4
            / \   /
           9   8 7

Mảng: [3, 5, 4, 9, 8, 7]
~~~

Thêm 2 vào cuối:

~~~text
                3
              /   \
             5     4
            / \   / \
           9   8 7   2

a = [3, 5, 4, 9, 8, 7, 2]
i = 6
~~~

### Lượt 1: so sánh với cha ở chỉ số 2

~~~text
i = 6
p = (6 - 1) // 2 = 2
a[i] = 2
a[p] = 4

2 < 4 nên đổi chỗ.
~~~

Sau đổi:

~~~text
a = [3, 5, 2, 9, 8, 7, 4]
           ▲
          i = 2
~~~

### Lượt 2: so sánh với cha ở chỉ số 0

~~~text
i = 2
p = (2 - 1) // 2 = 0
a[i] = 2
a[p] = 3

2 < 3 nên đổi chỗ.
~~~

Sau đổi:

~~~text
a = [2, 5, 3, 9, 8, 7, 4]
     ▲
    i = 0
~~~

Đã tới gốc, vòng lặp dừng. Cây cuối cùng:

~~~text
                2
              /   \
             5     3
            / \   / \
           9   8 7   4
~~~

Các quan hệ đúng:

~~~text
2 <= 5; 2 <= 3
5 <= 9; 5 <= 8
3 <= 7; 3 <= 4
~~~

Bảng trạng thái:

| Giai đoạn | i trước lượt | p | So sánh | Mảng sau lượt |
| --- | ---: | ---: | --- | --- |
| Append | 6 | 2 | Chưa sửa | [3, 5, 4, 9, 8, 7, 2] |
| Lượt 1 | 6 | 2 | 2 < 4, đổi | [3, 5, 2, 9, 8, 7, 4] |
| Lượt 2 | 2 | 0 | 2 < 3, đổi | [2, 5, 3, 9, 8, 7, 4] |
| Dừng | 0 | Không có | Đã tới gốc | [2, 5, 3, 9, 8, 7, 4] |

Có **hai lần hoán đổi**, không phải hai lần duyệt toàn bộ heap. Khi đi lên, chỉ những nút trên **đường tổ tiên** từ vị trí mới đến gốc có khả năng phải xét.

## 7. Những tình huống dừng khác nhau

Không phải thao tác push nào cũng cần đưa khóa lên gốc.

### 7.1. Không cần đổi chỗ

Heap ban đầu:

~~~text
a = [2, 5, 3, 9, 8, 7]
~~~

Thêm khóa **10**:

~~~text
a = [2, 5, 3, 9, 8, 7, 10]
                         ▲
                        i=6
~~~

Cha của i = 6 là p = 2, có khóa 3. Vì **3 ≤ 10**, heap vẫn hợp lệ, nên **sift-up dừng ngay**.

Chi phí so sánh sau append trong trường hợp này là **Θ(1)**.

### 7.2. Đổi một lần rồi dừng

Ban đầu:

~~~text
a = [1, 5, 6, 9, 8, 7]
~~~

Thêm khóa **4**:

~~~text
append 4 → [1, 5, 6, 9, 8, 7, 4]

i=6, p=2: 4 < 6, đổi.
a = [1, 5, 4, 9, 8, 7, 6]

i=2, p=0: 1 <= 4, dừng.
~~~

Ví dụ thứ hai cho thấy khóa mới có thể đi lên **một mức**, rồi dừng khi gặp cha không lớn hơn nó.

### 7.3. Heap rỗng

~~~text
Trước: []
Push(7)
Sau:   [7]
~~~

Phần tử mới ở i = 0, **không có cha**. Vòng sift-up không chạy. Heap một nút tự thỏa bất biến thứ tự.

### 7.4. Heap một nút

~~~text
Trước: [8]
Push(5)
Append: [8, 5]
So sánh 5 < 8, đổi.
Sau:   [5, 8]
~~~

Lúc này có đúng một phép hoán đổi. Nếu thay bằng push(9), mảng sau append [8, 9] vốn đã hợp lệ, nên không đổi.

### 7.5. Khóa bằng nhau

~~~text
Trước: [2, 3, 2]
Push(2) → [2, 3, 2, 2]
~~~

Nút mới i = 3 có cha i = 1, khóa 3. Đổi lên i = 1:

~~~text
[2, 2, 2, 3]
~~~

Tại i = 1, cha i = 0 có khóa 2, **bằng** khóa mới. Với min-heap, quan hệ **2 ≤ 2** đã đúng, nên dừng.

**Khóa bằng nhau là hợp lệ**, không có lý do phải đổi chỗ chỉ vì giá trị bằng nhau. Việc dừng khi bằng cũng giảm số phép hoán đổi không cần thiết, nhưng **không tự làm cho toàn bộ heap ổn định theo thứ tự đến**.

## 8. Bất biến vòng lặp: vì sao chỉ cần đi theo một đường?

Để chứng minh thao tác push đúng, ta xét heap **trước khi thêm** đã hợp lệ.

### 8.1. Sau append, chỉ một cạnh mới có thể sai

Trước khi thêm, mọi cặp cha–con đều đúng. Thêm một nút lá mới ở cuối:

- Không thay đổi quan hệ giữa bất kỳ hai nút cũ nào.
- Giữ hình dạng gần đầy đủ.
- Chỉ tạo ra **một quan hệ cha–con mới**, giữa nút mới và cha của nó.

Vì vậy, nếu bất biến min-heap bị vi phạm, lỗi ban đầu chỉ nằm ở **cạnh từ cha đến nút mới**.

### 8.2. Khi hoán đổi nút mới với cha

Giả sử nút mới có khóa x, cha có khóa p và **x < p**, nên hai nút phải đổi vị trí.

Trước hoán đổi, p là cha của x, các cây con cũ của p đã hợp lệ. Vì **x < p**, sau hoán đổi:

- x lên làm cha của p, nên quan hệ mới **x ≤ p** đúng.
- Nếu p có nút con còn lại y, trước đó **p ≤ y**. Do x < p, suy ra **x ≤ y**, nên quan hệ x với y cũng đúng.
- Nút p bị đẩy xuống vị trí trước đó của x. Các liên kết trong cây con dưới p vẫn đúng theo bất biến bước trước.
- Khả năng vi phạm còn lại chỉ là giữa **x và cha mới của x** ở mức cao hơn.

Chương trình không cần quét toàn bộ các nút: **mọi vị trí ngoài đường đi lên vẫn thỏa bất biến**.

### 8.3. Bất biến vòng lặp có thể phát biểu

> Ở đầu mỗi lượt, heap có hình dạng gần đầy đủ. Tất cả các quan hệ cha–con đều đúng, **trừ khả năng cạnh nối entry vừa được đẩy lên tại chỉ số i với cha của nó**. Entry đó vẫn là một trong những phần tử ban đầu cộng phần tử mới; không entry nào bị mất hay nhân đôi.

Khởi tạo: sau append, chỉ cạnh của nút mới với cha có thể sai.

Duy trì: nếu cạnh sai, hoán đổi đưa entry mới lên một mức và khôi phục quan hệ ở vị trí cũ. Cạnh có thể sai duy nhất di chuyển theo entry mới lên phía gốc.

Kết thúc: hoặc i = 0 nên entry mới không có cha, hoặc cha ≤ entry hiện tại. Do đó không còn cạnh vi phạm; **min-heap hợp lệ**.

### 8.4. Vì sao thuật toán chắc chắn dừng?

Khi có hoán đổi, i được cập nhật thành **(i − 1) // 2**, luôn **nhỏ hơn i** với i > 0. Chỉ số liên tục giảm về phía gốc và mỗi lượt đi lên đúng một mức. Vì chiều cao heap hữu hạn, số lượt tối đa hữu hạn.

Với n phần tử sau push, chiều cao là **⌊log₂ n⌋**, nên nhiều nhất O(log n) lần đi lên.

## 9. Cài đặt Python: thao tác push cho min-heap

Ví dụ sau sử dụng Python 3.10 trở lên. Ta tự triển khai thuật toán thay vì dùng thư viện **heapq**, để thấy rõ công thức cha và cách hoán đổi.

~~~python
from __future__ import annotations


class BinaryMinHeap:
    def __init__(self):
        self._data: list[int] = []

    def __len__(self) -> int:
        return len(self._data)

    def is_empty(self) -> bool:
        return len(self._data) == 0

    def push(self, value: int) -> None:
        """Thêm khóa mới bằng append rồi sift-up."""
        self._data.append(value)
        index = len(self._data) - 1

        while index > 0:
            parent = (index - 1) // 2

            # Cha đã nhỏ hơn hoặc bằng nút: đủ điều kiện dừng.
            if self._data[parent] <= self._data[index]:
                break

            # Đổi vị trí hai entry, không đổi số lượng nút.
            self._data[parent], self._data[index] = (
                self._data[index], self._data[parent]
            )
            index = parent

    def peek(self) -> int:
        """Xem khóa nhỏ nhất mà không xóa."""
        if not self._data:
            raise IndexError("Heap rỗng")
        return self._data[0]

    def as_list(self) -> list[int]:
        """Trả bản sao để người gọi không sửa trực tiếp heap."""
        return list(self._data)

    def check_invariants(self) -> None:
        """Kiểm tra mọi quan hệ cha <= con."""
        for index in range(1, len(self._data)):
            parent = (index - 1) // 2
            assert self._data[parent] <= self._data[index]


heap = BinaryMinHeap()

# Heap rỗng -> một nút.
assert heap.is_empty()
heap.push(3)
heap.check_invariants()
assert heap.peek() == 3
assert heap.as_list() == [3]

# Xây min-heap ban đầu bằng các lần push.
for number in [5, 4, 9, 8, 7]:
    heap.push(number)
    heap.check_invariants()

assert heap.as_list() == [3, 5, 4, 9, 8, 7]

# Đẩy khóa mới qua hai mức lên gốc.
heap.push(2)
heap.check_invariants()
assert heap.as_list() == [2, 5, 3, 9, 8, 7, 4]
assert heap.peek() == 2
assert len(heap) == 7

# Phần tử mới lớn hơn cha: không cần đổi chỗ.
heap.push(10)
heap.check_invariants()
assert heap.as_list() == [2, 5, 3, 9, 8, 7, 4, 10]

# Khóa trùng vẫn được phép.
heap.push(2)
heap.check_invariants()
assert len(heap) == 9
assert heap.peek() == 2

# Phần tử mới ưu tiên nhất có thể lên gốc.
heap.push(-1)
heap.check_invariants()
assert heap.peek() == -1

# Hàm as_list không cho người dùng sửa trực tiếp _data.
snapshot = heap.as_list()
snapshot[0] = 999
assert heap.peek() == -1
~~~

Những điểm cần quan sát:

- **append** bảo toàn hình dạng cây gần đầy đủ vì thêm đúng vị trí cuối.
- **sift-up** sửa liên kết ưu tiên qua các hoán đổi trên mảng, không tạo đối tượng nút cây.
- Mỗi phần tử cũ được giữ lại; len tăng đúng 1 sau mỗi push.
- **peek** trả về a[0], tức khóa nhỏ nhất, trong O(1).
- **check_invariants** duyệt từ chỉ số 1 tới n − 1, dùng cho học tập/gỡ lỗi; chi phí Θ(n), không nên tính vào bản thân push O(log n) nếu không chạy sau mỗi thao tác.

### Một phiên bản tách hàm _sift_up

Khi ứng dụng cần dùng lại thao tác đẩy lên (ví dụ giảm khóa của một entry đã biết chỉ số), có thể tách phần sửa bất biến:

~~~python
def _sift_up(self, index: int) -> None:
    while index > 0:
        parent = (index - 1) // 2
        if self._data[parent] <= self._data[index]:
            return
        self._data[parent], self._data[index] = (
            self._data[index], self._data[parent]
        )
        index = parent

def push(self, value: int) -> None:
    self._data.append(value)
    self._sift_up(len(self._data) - 1)
~~~

Hai phương thức trên là **phiên bản thay thế/bổ sung của phần thao tác tương ứng trong lớp**, không phải mã cần định nghĩa ở ngoài và gọi độc lập. Khi đưa vào lớp, không nên giữ hai định nghĩa push trùng tên.

## 10. Tự xây trace để kiểm tra vị trí từng lượt

Để kiểm chứng trực quan và giảng giải thuật toán, có thể ghi lại mảng sau **mỗi lần hoán đổi**. Phiên bản dưới đây không dùng heapq và chỉ phục vụ quan sát:

~~~python
def push_with_trace(heap: list[int], value: int):
    """Thay đổi heap tại chỗ, trả lịch sử các trạng thái."""
    heap.append(value)
    index = len(heap) - 1
    trace = [("append", index, list(heap))]

    while index > 0:
        parent = (index - 1) // 2
        if heap[parent] <= heap[index]:
            trace.append(("stop", index, list(heap)))
            break

        heap[parent], heap[index] = heap[index], heap[parent]
        index = parent
        trace.append(("swap", index, list(heap)))
    else:
        trace.append(("root", index, list(heap)))

    return trace


a = [3, 5, 4, 9, 8, 7]
history = push_with_trace(a, 2)

assert history[0] == ("append", 6, [3, 5, 4, 9, 8, 7, 2])
assert history[1] == ("swap", 2, [3, 5, 2, 9, 8, 7, 4])
assert history[2] == ("swap", 0, [2, 5, 3, 9, 8, 7, 4])
assert history[3][0] == "root"
assert a == [2, 5, 3, 9, 8, 7, 4]
~~~

Hàm trace cố ý tạo **bản sao toàn bộ mảng mỗi lượt** bằng list(heap). Vì vậy, nó **không còn là cài đặt push O(1) bộ nhớ phụ** như phiên bản chuẩn. Với tối đa O(log n) trạng thái, mỗi bản sao n phần tử, trace có thể tốn **O(n log n)** thời gian/bộ nhớ để lưu lịch sử.

Đây là sự khác biệt giữa **thuật toán cốt lõi** và **mã công cụ phục vụ giảng dạy/gỡ lỗi**.

## 11. Max-heap: cùng hình dạng, đảo chiều phép so sánh

Một **max-heap** có bất biến **cha ≥ con**, nên thao tác thêm vẫn gồm hai pha: append vào cuối và sift-up. Khác biệt duy nhất trong logic cốt lõi là điều kiện hoán đổi.

Min-heap:

~~~text
Nếu a[index] < a[parent] thì đổi chỗ.
Dừng khi a[parent] <= a[index].
~~~

Max-heap:

~~~text
Nếu a[index] > a[parent] thì đổi chỗ.
Dừng khi a[parent] >= a[index].
~~~

Ví dụ:

~~~text
Max-heap ban đầu:
a = [9, 7, 8, 4, 3, 6]

Push(10):
append → [9, 7, 8, 4, 3, 6, 10]

i=6, p=2: 10 > 8
swap   → [9, 7, 10, 4, 3, 6, 8]

i=2, p=0: 10 > 9
swap   → [10, 7, 9, 4, 3, 6, 8]
~~~

Phần tử mới lên gốc vì nó có khóa lớn hơn mọi tổ tiên trên đường đi.

Cài đặt ngắn gọn:

~~~python
class BinaryMaxHeap:
    def __init__(self):
        self._data = []

    def push(self, value):
        self._data.append(value)
        index = len(self._data) - 1

        while index > 0:
            parent = (index - 1) // 2
            if self._data[parent] >= self._data[index]:
                break

            self._data[parent], self._data[index] = (
                self._data[index], self._data[parent]
            )
            index = parent

    def peek(self):
        if not self._data:
            raise IndexError("Heap rỗng")
        return self._data[0]

    def as_list(self):
        return list(self._data)


max_heap = BinaryMaxHeap()
for value in [9, 7, 8, 4, 3, 6]:
    max_heap.push(value)

assert max_heap.as_list() == [9, 7, 8, 4, 3, 6]
max_heap.push(10)
assert max_heap.as_list() == [10, 7, 9, 4, 3, 6, 8]
assert max_heap.peek() == 10
~~~

**Công thức chỉ số cha/con không đổi** khi chuyển từ min-heap sang max-heap. Chỉ **quan hệ ưu tiên giữa cha và con** được đảo chiều.

## 12. Khi heap lưu entry có priority và payload

Trong ứng dụng thực tế, phần tử có thể là một bản ghi:

~~~text
Task:
  id       = "job-17"
  priority = 2
  payload  = dữ liệu cần xử lý
~~~

Điều được so sánh khi sift-up phải là **priority** (và các trường tie-breaker được quy định). Nếu so sánh trực tiếp payload, chương trình có thể:

- Xếp sai thứ tự nghiệp vụ.
- Gây **TypeError** với payload không hỗ trợ so sánh.
- Cho kết quả không ổn định khi priority bằng nhau.

### 12.1. Khóa trùng và tính ổn định

Trong min-heap thông thường, hai entry khóa 2 đều hợp lệ ở vị trí cha/con bất kỳ miễn quan hệ cha ≤ con đúng. Thuật toán sift-up dùng phép so sánh **strict** (chỉ đổi khi child < parent), nhưng điều đó **không tự bảo đảm FIFO giữa tất cả entry khóa bằng nhau** sau các lần push/pop.

Nếu hệ thống cần cùng priority thì **vào trước ra trước**, hãy dùng khóa so sánh kép:

~~~text
(priority, sequence_number, payload)
~~~

Trong đó sequence_number tăng theo thứ tự push và duy nhất trong hàng đợi. Với tuple Python, priority được so sánh trước; nếu bằng nhau, sequence quyết định; payload không cần so sánh.

### 12.2. Cài đặt sift-up cho entry ổn định

Ví dụ sau minh họa trực tiếp mảng heap gồm các entry **(priority, sequence, payload)**. Khi so sánh, chỉ xét **hai thành phần đầu**.

~~~python
from itertools import count


class StableMinHeap:
    def __init__(self):
        self._data = []
        self._sequence = count()

    def push(self, priority: int, payload) -> None:
        entry = (priority, next(self._sequence), payload)
        self._data.append(entry)
        index = len(self._data) - 1

        while index > 0:
            parent = (index - 1) // 2
            parent_key = self._data[parent][:2]
            child_key = self._data[index][:2]

            if parent_key <= child_key:
                break

            self._data[parent], self._data[index] = (
                self._data[index], self._data[parent]
            )
            index = parent

    def peek(self):
        if not self._data:
            raise IndexError("Heap rỗng")
        priority, _seq, payload = self._data[0]
        return priority, payload

    def as_list(self):
        return list(self._data)

    def check_invariants(self):
        for index in range(1, len(self._data)):
            parent = (index - 1) // 2
            assert self._data[parent][:2] <= self._data[index][:2]


class Task:
    def __init__(self, title):
        self.title = title


q = StableMinHeap()
a = Task("A")
b = Task("B")
c = Task("C")

q.push(3, a)
q.push(1, b)
q.push(1, c)
q.check_invariants()

assert q.peek() == (1, b)
assert len(q.as_list()) == 3
~~~

Ví dụ tập trung vào **push** và **peek**. Muốn hoàn thiện ADT với pop, phải bổ sung thao tác lấy gốc và **sift-down**, vẫn so sánh đúng **(priority, sequence)**.

### 12.3. Sửa priority của một entry đã có không giống push

Nếu ứng dụng chỉ thay priority trong một payload đã nằm trong heap, mảng sẽ **không tự tổ chức lại**. Một thao tác **decrease-key** trên min-heap có thể cần sift-up từ vị trí entry cũ; muốn làm vậy hiệu quả thì phải **biết chỉ số hiện tại của entry**, thường qua handle và bảng ánh xạ.

Khi heap đang lưu entry và các lần swap đổi vị trí, bảng ánh xạ **ID → index** cũng phải cập nhật tương ứng. Một hàm push chuẩn không cần bảng ấy, nhưng API cập nhật khóa theo ID có thể cần.

## 13. Độ phức tạp: số lượt, so sánh và bộ nhớ

Với heap có **n phần tử trước khi thêm**, sau append có n + 1 phần tử. Độ sâu tối đa của phần tử mới trong cây gần đầy đủ là:

\[
h = \left\lfloor \log_2(n+1) \right\rfloor.
\]

Mỗi lần hoán đổi, i tiến lên **một mức**. Vì vậy:

- **Số lần hoán đổi tối đa:** O(log(n + 1)).
- **Số lần so sánh khóa:** O(log(n + 1)).
- **Thời gian sift-up xấu nhất:** O(log(n + 1)).
- **Bộ nhớ phụ của sift-up:** O(1).

Nếu khóa mới đã thỏa điều kiện với cha, sift-up chỉ cần **một lần so sánh**, nên thời gian tốt nhất là **Θ(1)**.

### 13.1. Phân tích khi heap rỗng hoặc rất nhỏ

| Kích thước trước push | Tình huống | Số lần so sánh/hoán đổi do sift-up |
| ---: | --- | --- |
| n = 0 | Thêm phần tử đầu tiên | 0 / 0 |
| n = 1 | Thêm phần tử thứ hai | Tối đa 1 / 1 |
| n = 2 | Thêm phần tử thứ ba | Tối đa 1 / 1 |
| n = 6 | Thêm phần tử thứ bảy | Tối đa 2 / 2 |
| n = 14 | Thêm phần tử thứ mười lăm | Tối đa 3 / 3 |

Số mức của nút cuối tăng theo logarit, không tăng theo n. Vì vậy, một heap lớn không cần dịch toàn bộ phần tử mỗi khi thêm mới.

### 13.2. Chi phí append trong mảng động

Khi mô tả **push của binary heap O(log n)**, ta thường phân tích thao tác so sánh/hoán đổi với giả định thêm cuối mảng có chi phí khấu hao O(1).

Nhưng **một lần append cụ thể của mảng động** đôi khi phải mở rộng vùng nhớ và sao chép các entry hiện có, tốn O(n) trong trường hợp xấu nhất của riêng lần đó. Vì thế:

- Với mảng đã cấp phát đủ dung lượng, push có cận trên **O(log n)**.
- Với mảng động mở rộng theo cấp số nhân thông thường, push có chi phí **O(log n) khấu hao**; một lời gọi có thể đắt hơn vì tái cấp phát.
- Bộ nhớ tổng của heap là **O(n)** để lưu n entry; bộ nhớ phụ dùng cho các biến index/parent/swap là **O(1)**, không tính vùng chứa mảng được mở rộng.

Đây là khác biệt giữa **độ phức tạp thuật toán heap** và **chi phí quản lý vùng nhớ của cấu trúc mảng động**.

### 13.3. So sánh với thao tác khác

| Thao tác trong min-heap | Thời gian theo mô hình heap | Ghi chú |
| --- | --- | --- |
| Peek gốc | Θ(1) | Không sửa heap |
| Push với sift-up | O(log n) | Best case Θ(1) cho sift-up |
| Pop gốc với sift-down | O(log n) | Đi từ gốc xuống một đường |
| Heapify từ dưới lên | Θ(n) | Sửa các cây con từ nút trong cuối |
| Tìm khóa bất kỳ | O(n) xấu nhất | Heap không phải mảng đã sắp |
| Kiểm tra toàn bộ bất biến | Θ(n) | Không cần trong mọi push |
| Sao chép snapshot của mảng | Θ(n) | Chi phí phục vụ hiển thị/kiểm thử |

## 14. Phân biệt đẩy lên và đẩy xuống

Hai hướng sửa heap dễ bị nhầm vì cùng dùng phép đổi chỗ giữa cha và con.

| Tình huống | Hướng cần xem xét | Vì sao? |
| --- | --- | --- |
| **Thêm nút mới ở cuối** | **Sift-up** | Nút mới có thể ưu tiên hơn cha |
| **Lấy gốc rồi đưa phần tử cuối lên gốc** | **Sift-down** | Gốc mới có thể kém ưu tiên hơn một con |
| **Giảm khóa của entry đã có** trong min-heap | Thường sift-up | Khóa mới có thể nhỏ hơn cha |
| **Tăng khóa của entry đã có** trong min-heap | Thường sift-down | Khóa mới có thể lớn hơn con |
| **Bottom-up heapify** | Sift-down trên các nút trong | Mỗi cây con được sửa từ dưới lên |

Khi push vào heap hợp lệ, **không cần sift-down từ gốc**: những nhánh cũ vẫn hợp lệ, chỉ đường từ entry mới đi lên có thể vi phạm.

Tương tự, sau khi pop gốc và đưa phần tử cuối lên vị trí 0, **sift-up từ gốc** không có ý nghĩa vì gốc không có cha. Phải kiểm tra các con theo hướng đi xuống.

## 15. Những lỗi dễ mắc khi cài đặt

| Sai sót | Hậu quả | Cách tránh |
| --- | --- | --- |
| Chèn entry mới vào một vị trí tùy ý trong mảng | Phá bất biến hình dạng cây gần đầy đủ | Luôn append cuối mảng trước |
| Dùng parent = i // 2 cho mảng 0-based | Tính sai cha ở nhiều vị trí | Dùng **(i − 1) // 2** |
| Lấy parent khi i = 0 | Python có thể dùng a[-1] sai nghĩa | Kiểm tra **i > 0** trước |
| Dùng khóa con lớn hơn cha để đổi trong min-heap | Làm sai quan hệ cha ≤ con | Min-heap chỉ đổi khi con nhỏ hơn cha |
| Đổi với cha nhưng quên **i = parent** | Lặp mãi hoặc so sánh sai vị trí | Cập nhật i theo vị trí mới của entry |
| Chỉ hoán đổi giá trị priority, không hoán đổi cả entry | Priority tách khỏi payload | Hoán đổi **toàn bộ entry** |
| So sánh payload không hỗ trợ thứ tự | TypeError khi khóa hòa | So sánh key, thêm sequence nếu cần |
| Dùng <= để buộc swap khi khóa bằng nhau | Tăng số swap không cần thiết; không giải quyết ổn định | Dừng khi cha ≤ con |
| Cho rằng push sắp xếp cả mảng | Kết luận sai về thứ tự các phần tử | Chỉ bất biến cha–con được bảo đảm |
| Không kiểm tra rỗng trước peek | IndexError không có thông báo rõ | Định nghĩa lỗi rỗng trong API |
| Sửa trực tiếp mảng heap từ bên ngoài | Bất biến heap có thể hỏng | Đóng gói dữ liệu, cung cấp API |
| Đổi khóa entry hiện có mà không sửa vị trí | Heap không còn hợp lệ | Dùng decrease-key/increase-key |
| Có map ID → index nhưng không cập nhật sau swap | Handle trỏ sai entry | Đồng bộ map ở mỗi lần hoán đổi |
| Gọi check_invariants Θ(n) sau mỗi push nhưng báo push O(log n) | Phân tích tổng thời gian sai | Tách chi phí kiểm thử khỏi push cơ bản |
| Lưu bản sao mảng ở mỗi lượt trace nhưng báo O(1) bộ nhớ | Bỏ qua chi phí logging | Phân biệt trace với thuật toán cốt lõi |
| Nhầm best case O(1) với worst case O(1) | Đánh giá thiếu chuỗi swap lên gốc | Worst case O(log n) |

### Cách tự kiểm tra bằng tay

Với một lần push cụ thể:

1. Viết mảng trước và sau append cùng chỉ số i của phần tử mới.
2. Tính **parent(i)** bằng chia nguyên.
3. So sánh **a[parent]** và **a[i]**, nhớ quy ước min hay max.
4. Nếu đổi, viết mảng mới và cập nhật **i = parent**.
5. Tiếp tục cho tới khi i = 0 hoặc không cần đổi.
6. Kiểm tra tất cả các cặp cha–con trong mảng cuối.

Thử với **heap rỗng, một nút, khóa rất nhỏ, khóa rất lớn và khóa bằng nhau** để lộ lỗi trường hợp biên.

## 16. Ứng dụng: thêm công việc mới vào hàng đợi ưu tiên

Giả sử hệ thống xử lý yêu cầu:

~~~text
(priority=1) Khắc phục dịch vụ
(priority=2) Gửi thông báo khẩn
(priority=5) Tạo báo cáo
~~~

Khi có công việc mới có priority = 0:

1. Hệ thống tạo một entry gồm khóa và dữ liệu.
2. Thêm entry vào cuối mảng heap.
3. Sift-up cho entry mới đi lên nếu có khóa nhỏ hơn các cha trên đường đi.
4. Sau khi sửa, entry priority = 0 có thể nằm ở gốc và trở thành công việc được chọn tiếp theo.

**Điều này không có nghĩa công việc đang chạy phải bị gián đoạn.** Heap chỉ xác định phần tử ưu tiên nhất **trong các entry đang chờ**; quy tắc preemption, thời điểm lấy công việc và điều phối thực thi thuộc về hệ thống lập lịch.

Một ứng dụng mô phỏng sự kiện rời rạc có thể dùng **timestamp** làm khóa min-heap. Khi thêm một sự kiện diễn ra sớm hơn các sự kiện đã chờ, sift-up đưa nó về phía gốc; khi hệ thống pop, sự kiện có thời gian nhỏ nhất được lấy trước.

Trong thuật toán đồ thị như Dijkstra hoặc Prim, hàng đợi ưu tiên cũng thường dùng heap. Tuy nhiên, **thêm entry mới** khác **giảm khóa entry đang tồn tại**. Nếu cần cập nhật một entry cụ thể theo ID, hệ thống cần cơ chế định vị và duy trì vị trí, hoặc chiến lược thêm ứng viên mới rồi loại entry lỗi thời khi lấy.

## 17. Bài tập tự luyện có đáp án

**Bài 1 — Công thức cha.** Trong mảng 0-based, nút mới được append ở i = 11. Cha của nó có chỉ số nào?

*Đáp án:* (11 − 1) // 2 = **5**.

**Bài 2 — Heap rỗng.** Thêm khóa 7 vào min-heap rỗng. Có cần hoán đổi không?

*Đáp án:* Không. Mảng là **[7]**, nút mới ở gốc i = 0, không có cha.

**Bài 3 — Một nút.** Min-heap [8], push(5) tạo mảng nào?

*Đáp án:* Append thành [8, 5]; 5 < 8 nên đổi chỗ; kết quả **[5, 8]**.

**Bài 4 — Không cần đẩy.** Min-heap [2, 5, 3, 9, 8, 7], push(10) có mảng cuối là gì?

*Đáp án:* **[2, 5, 3, 9, 8, 7, 10]**. Nút mới có cha khóa 3 ≤ 10 nên dừng sau kiểm tra đầu.

**Bài 5 — Hai lần hoán đổi.** Thêm khóa 2 vào [3, 5, 4, 9, 8, 7]. Nêu các mảng sau từng swap.

*Đáp án:* Sau append [3, 5, 4, 9, 8, 7, 2]; swap với 4 thành **[3, 5, 2, 9, 8, 7, 4]**; swap với 3 thành **[2, 5, 3, 9, 8, 7, 4]**.

**Bài 6 — Một lần hoán đổi.** Thêm 4 vào min-heap [1, 5, 6, 9, 8, 7]. Mảng cuối?

*Đáp án:* Append [1, 5, 6, 9, 8, 7, 4]; đổi 4 với 6; gặp cha gốc 1 ≤ 4 nên dừng. Kết quả **[1, 5, 4, 9, 8, 7, 6]**.

**Bài 7 — Khóa bằng nhau.** Với min-heap [2, 3, 2], push(2) có kết quả nào nếu chỉ đổi khi con < cha?

*Đáp án:* Append [2, 3, 2, 2]; đổi 2 với 3 ở i = 1, gặp gốc 2 bằng nhau nên dừng; kết quả **[2, 2, 2, 3]**.

**Bài 8 — Vì sao append cuối?** Điều gì có thể sai nếu thay vì append cuối ta tạo một con tùy ý dưới một nút lá?

*Đáp án:* Cây có thể không còn gần đầy đủ, vì vị trí lấp từ trái sang phải bị phá. Công thức vị trí cha/con trong mảng không còn tương ứng với cây được mô tả.

**Bài 9 — Bất biến sau append.** Nếu heap ban đầu hợp lệ và ta chỉ append một nút mới, tại sao không cần kiểm tra mọi cạnh trong heap?

*Đáp án:* Các nút cũ và quan hệ giữa chúng không đổi. Chỉ **cạnh cha–nút mới** có thể vi phạm. Sau mỗi swap, nguy cơ vi phạm chỉ di chuyển theo nút mới lên một mức.

**Bài 10 — Điều kiện dừng.** Min-heap có i > 0, a[parent] = 6 và a[i] = 6. Có cần swap không?

*Đáp án:* Không, vì **6 ≤ 6**. Khóa bằng nhau đáp ứng bất biến min-heap.

**Bài 11 — Max-heap.** Bắt đầu với [9, 7, 8, 4, 3, 6], push(10) có kết quả?

*Đáp án:* Append [9, 7, 8, 4, 3, 6, 10]; đổi với 8 rồi 9; kết quả **[10, 7, 9, 4, 3, 6, 8]**.

**Bài 12 — Chiều cao.** Heap sau push có n = 31 phần tử. Nút cuối có độ sâu tối đa bao nhiêu?

*Đáp án:* **⌊log₂31⌋ = 4** cạnh từ gốc, nên sift-up cần nhiều nhất 4 lần hoán đổi.

**Bài 13 — Số lượt.** Vì sao sift-up không thể đi lên quá nhiều lần hơn chiều cao cây?

*Đáp án:* Mỗi lần swap, i thay bằng cha có độ sâu nhỏ hơn đúng một. Một nút chỉ có thể đi tối đa từ mức hiện tại tới gốc.

**Bài 14 — Heap không phải mảng đã sắp.** [2, 5, 3, 9, 8, 7, 4] có phải min-heap dù 5 > 3 không?

*Đáp án:* Có. Mọi cha đều ≤ các con trực tiếp của mình; không cần so sánh theo thứ tự trái–phải giữa các nhánh.

**Bài 15 — Best case và worst case.** Độ phức tạp thời gian của sift-up khi nút mới đã hợp lệ với cha là bao nhiêu, và khi phải lên gốc là bao nhiêu?

*Đáp án:* **Θ(1)** trong trường hợp đầu; **O(log n)** ở trường hợp sau, và có thể đạt Θ(log n) cho dãy khóa cần đi hết đường lên gốc.

**Bài 16 — Mảng động.** Vì sao một lần push trên list động có thể tốn O(n) dù sift-up chỉ O(log n)?

*Đáp án:* Append đôi khi phải mở rộng vùng nhớ và sao chép các entry. Theo phân tích khấu hao của mảng động tăng dung lượng theo cấp số nhân, append O(1) khấu hao, nên push vẫn O(log n) khấu hao.

**Bài 17 — Hoán đổi entry.** Heap chứa entry (priority, payload). Vì sao không được chỉ đổi priority giữa cha và con mà giữ payload ở chỗ cũ?

*Đáp án:* Như vậy khóa ưu tiên sẽ không còn gắn với công việc đúng. Phải hoán đổi **nguyên entry** hoặc duy trì quan hệ priority–payload nhất quán.

**Bài 18 — Hòa khóa và FIFO.** Nếu hai công việc cùng priority được push theo thứ tự A, B, min-heap thông thường có bảo đảm pop A trước B không?

*Đáp án:* Không. Muốn ổn định, có thể dùng khóa so sánh **(priority, sequence_number)** tăng dần theo thứ tự push.

**Bài 19 — Chọn hướng sửa.** Tại sao thêm nút mới thường dùng sift-up thay vì sift-down?

*Đáp án:* Nút mới nằm ở lá và có thể nhỏ hơn cha trong min-heap. Lỗi có thể đi dọc đường tổ tiên; nó không có con để đẩy xuống.

**Bài 20 — Đổi khóa của nút đang có.** Một entry min-heap ở chỉ số 5 giảm priority từ 8 xuống 1. Có phải thao tác push mới không?

*Đáp án:* Không nhất thiết. Đây là thao tác **decrease-key** trên một entry đã tồn tại. Nếu biết chỉ số hiện tại và các bất biến khác đúng, có thể chạy sift-up từ chỉ số 5; phải cập nhật metadata vị trí nếu có.

**Bài 21 — Đọc lỗi cha của gốc.** Vì sao kết quả parent(0) = -1 của phép chia Python có thể nguy hiểm khi dùng trực tiếp cho a[-1]?

*Đáp án:* Python xem -1 là chỉ số phần tử cuối, không phải cha gốc. Nếu không kiểm tra i > 0, thuật toán sẽ so sánh sai và có thể làm hỏng heap.

**Bài 22 — Mô phỏng một lần khác.** Min-heap [1, 4, 3, 8, 6, 5] thêm khóa 2. Hãy ghi kết quả.

*Đáp án:* Append thành [1, 4, 3, 8, 6, 5, 2]. 2 < 3 nên đổi với nút i = 2: [1, 4, 2, 8, 6, 5, 3]. Cha mới là 1 ≤ 2 nên dừng; kết quả **[1, 4, 2, 8, 6, 5, 3]**.

**Ghi nhớ:** Thêm phần tử vào binary heap gồm **append cuối mảng để giữ cây gần đầy đủ** và **sift-up theo chỉ số cha để khôi phục thứ tự heap**. Với min-heap 0-based, lặp khi **i > 0** và đổi chỗ nếu **a[i] < a[(i − 1)//2]**, cập nhật i về cha; với max-heap đảo chiều so sánh. Thuật toán chỉ xét đường từ nút mới tới gốc nên dùng **O(log n) thời gian xấu nhất** cho các phép so sánh/hoán đổi và **O(1) bộ nhớ phụ**. Khi dùng mảng động, cần phân biệt chi phí append khấu hao với chi phí của một lần mở rộng vùng nhớ.
