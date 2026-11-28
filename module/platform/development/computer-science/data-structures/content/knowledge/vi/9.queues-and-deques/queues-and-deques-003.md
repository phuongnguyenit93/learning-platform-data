# Vì sao xóa đầu mảng bằng dịch chuyển gây chi phí tuyến tính

Trong một **hàng đợi FIFO** (*First In, First Out*), phần tử được đưa vào trước phải được lấy ra trước. Nếu biểu diễn hàng đợi bằng mảng hoặc danh sách dựa trên mảng và luôn xem ô chỉ số `0` là đầu hàng, thao tác lấy phần tử đầu thường kéo theo một công việc tốn kém: **dịch toàn bộ các phần tử còn lại sang trái một vị trí**.

Bài thuộc chương **Hàng đợi và deque** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, nơi người học xây dựng nền tảng về mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị. Qua ví dụ cụ thể này, ta sẽ học cách xác định phép toán chi phối thời gian chạy, chứng minh chi phí **O(n)** của thao tác xóa đầu và chọn cách lưu trữ đáp ứng đúng yêu cầu của bài toán.

## 1. Tại sao phần tử sau phải dịch sang trái?

Một mảng lưu các phần tử trong các vị trí được đánh chỉ số. Với biểu diễn quen thuộc của một danh sách tuyến tính, các phần tử hợp lệ được giữ liên tiếp từ chỉ số `0` đến `n - 1`:

```text
Trước khi xóa đầu:

Chỉ số        0       1       2       3       4
            +-------+-------+-------+-------+-------+
Giá trị     |   A   |   B   |   C   |   D   |   E   |
            +-------+-------+-------+-------+-------+
              ↑
            front                           rear
```

Hàng đợi có thứ tự logic `[A, B, C, D, E]`. Khi gọi `dequeue()`, hệ thống phải trả về `A` và bảo toàn thứ tự `B, C, D, E`.

Nếu cấu trúc yêu cầu **phần tử đầu mới luôn ở ô `0`** và các phần tử vẫn nằm liên tiếp, nó phải thực hiện:

```text
Xóa A và dời các phần tử:

B: chỉ số 1 → 0
C: chỉ số 2 → 1
D: chỉ số 3 → 2
E: chỉ số 4 → 3

Sau khi xóa:

Chỉ số        0       1       2       3
            +-------+-------+-------+-------+
Giá trị     |   B   |   C   |   D   |   E   |
            +-------+-------+-------+-------+
              ↑
            front                   rear
```

Như vậy, **một lần lấy đầu khiến bốn phần tử khác phải đổi vị trí**. Với `n` phần tử, số phần tử cần dịch là **`n - 1`**.

Lưu ý hai điều:

- **FIFO không bắt buộc phải dịch phần tử.** Đây là hệ quả của cách *biểu diễn* hàng đợi: luôn đặt phần tử đầu vào vị trí vật lý `0` của một mảng đặc.
- Trong một ngôn ngữ như Python, mảng bên trong `list` lưu **các tham chiếu đến đối tượng**. Xóa đầu cần dịch các tham chiếu còn lại; không nhất thiết sao chép dữ liệu bên trong từng đối tượng. Dù vậy, số vị trí phải cập nhật vẫn tăng theo độ dài danh sách.

## 2. Thuật toán xóa đầu bằng dịch chuyển

Giả sử mảng có `n > 0` phần tử hợp lệ và ta muốn trả về giá trị đầu rồi loại bỏ phần tử đó. Một thuật toán trực tiếp có thể viết như sau:

```text
DEQUEUE_SHIFT(A, n):
    if n == 0:
        báo lỗi "hàng đợi rỗng"

    result = A[0]

    for i = 1 đến n - 1:
        A[i - 1] = A[i]

    n = n - 1
    loại bỏ hoặc giải phóng ô hợp lệ cuối cũ

    return result
```

Biến `result` giữ giá trị cần trả về **trước khi** các phần tử bị ghi đè. Sau vòng lặp, phần tử cuối cũ có thể xuất hiện ở cả vị trí `n - 2` và `n - 1`; vì thế phải giảm độ dài logic và xử lý ô ngoài phạm vi hợp lệ.

Trong Python, có thể viết đúng cơ chế dịch chuyển bằng các thao tác tường minh:

```python
def dequeue_by_shifting(items):
    """Lấy phần tử đầu và dịch các phần tử còn lại sang trái."""
    if not items:
        raise IndexError("Hàng đợi rỗng")

    first = items[0]
    n = len(items)

    for i in range(1, n):
        items[i - 1] = items[i]

    items.pop()  # Bỏ bản sao cuối sau khi dịch.
    return first


queue = ["A", "B", "C", "D", "E"]
assert dequeue_by_shifting(queue) == "A"
assert queue == ["B", "C", "D", "E"]
```

Trong sử dụng thông thường, Python đã cung cấp `items.pop(0)` để trả về và loại bỏ phần tử ở vị trí `0`. Cách gọi này ngắn hơn, nhưng vẫn chịu chi phí dịch các tham chiếu còn lại:

```python
queue = ["A", "B", "C", "D", "E"]
first = queue.pop(0)

assert first == "A"
assert queue == ["B", "C", "D", "E"]
```

**Lấy giá trị `items[0]` là O(1)**; phần khiến thao tác xóa đầu tốn thời gian không phải việc đọc giá trị đầu mà là việc **duy trì tính liên tiếp của các phần tử còn lại**.

## 3. Chứng minh độ phức tạp O(n)

Xét mảng có `n` phần tử trước khi xóa đầu:

1. Kiểm tra rỗng và lưu giá trị `A[0]`: **O(1)**.
2. Duyệt `i` từ `1` đến `n - 1`: **`n - 1` lần lặp**.
3. Mỗi lần lặp gán `A[i - 1] = A[i]`: **O(1)** theo mô hình thao tác trên ô mảng.
4. Giảm độ dài logic và trả kết quả: **O(1)** theo mô hình mảng có bộ đếm kích thước.

Vì vậy, với các hằng số dương thích hợp `a` và `b`, thời gian của thuật toán có dạng:

```text
T(n) = a × (n - 1) + b

     = Θ(n)    khi n tăng
```

Tức **O(n)** là cận trên, còn **Θ(n)** nhấn mạnh rằng chi phí dịch chuyển thực sự tăng tuyến tính với `n` trong mô hình này. Trường hợp `n = 1` không cần dịch phần tử nào và chỉ tốn O(1); khi `n = 0`, hàm báo rỗng theo hợp đồng API. Những trường hợp biên này không thay đổi độ phức tạp khi `n` lớn.

Nếu thư viện dùng hàm thao tác bộ nhớ tối ưu như `memmove` thay cho vòng lặp viết tay, nó vẫn phải di chuyển lượng dữ liệu tương ứng với **`n - 1` vị trí**. Thực thi có thể nhanh hơn nhờ mã máy và xử lý theo khối, nhưng không biến công việc thành O(1) theo kích thước mảng.

### Vì sao xóa cuối thường rẻ hơn?

Nếu lấy phần tử ở cuối mảng, các phần tử phía trước không phải thay đổi chỉ số:

```text
[A, B, C, D, E]  --xóa cuối-->  [A, B, C, D]
        Không cần dịch A, B, C, D
```

Với mảng giữ bộ đếm kích thước, giảm số phần tử hợp lệ ở cuối và trả về giá trị vừa bỏ thường là **O(1)** về thao tác thuật toán. Với `Python list`, `pop()` ở cuối có chi phí O(1) khấu hao trong sử dụng thông thường; một lần thay đổi dung lượng vùng nhớ bên trong có thể phát sinh chi phí riêng.

Điều này giải thích vì sao mảng động rất thuận tiện cho **stack** (thêm/lấy tại cuối), nhưng cách cài đặt **queue** bằng `append` ở cuối và `pop(0)` ở đầu lại có chi phí không cân xứng.

## 4. Nhiều lần xóa đầu có thể gây chi phí bậc hai

Xem xét một hàng đợi có `n` phần tử và liên tục xóa đầu cho đến khi rỗng.

- Lần thứ nhất: dịch `n - 1` phần tử.
- Lần thứ hai: dịch `n - 2` phần tử.
- …
- Lần gần cuối: dịch `1` phần tử.
- Lần cuối: dịch `0` phần tử.

Tổng số vị trí phải dịch là:

```text
(n - 1) + (n - 2) + ... + 2 + 1 + 0
= n × (n - 1) / 2
= Θ(n²)
```

Ví dụ minh họa:

| Số phần tử ban đầu `n` | Số vị trí phải dịch khi xóa hết `n` phần tử |
|---:|---:|
| 5 | 10 |
| 10 | 45 |
| 1.000 | 499.500 |
| 100.000 | 4.999.950.000 |

Các con số trên là **số lần chuyển vị trí trong mô hình dịch trái trực tiếp**, không phải số lệnh máy chính xác hay thời gian chạy thực tế. Chúng cho thấy khi dữ liệu tăng lớn, việc xóa đầu lặp lại có thể tạo ra khối lượng công việc rất cao.

Nếu một hệ thống liên tục duy trì hàng đợi dài khoảng `n` phần tử bằng cách **thêm một phần tử rồi lấy một phần tử**, mỗi lần lấy đầu bằng dịch chuyển vẫn tốn O(n); với `k` lượt, tổng chi phí dịch chuyển có thể lên đến **O(k·n)**. Việc `append` thường nhanh không bù được chi phí tuyến tính lặp lại ở `pop(0)`.

### Chi phí từng thao tác khác với chi phí một chuỗi thao tác

| Tình huống | Chi phí do dịch chuyển |
|---|---|
| Xóa đầu một mảng đang có `n` phần tử | Θ(n) |
| Xóa liên tiếp toàn bộ `n` phần tử đầu | Θ(n²) |
| Xóa ở cuối, không giữ lại khoảng trống | O(1) theo mô hình bộ đếm kích thước |
| Chỉ đọc phần tử đầu, không xóa | O(1) |
| Xóa đầu từ hàng đợi dùng mảng vòng | O(1), không dịch các phần tử còn lại |

Hãy xác định đúng **phép toán thường xuyên nhất** trước khi chọn cấu trúc. Một thao tác O(n) hiếm khi xảy ra có thể không đáng lo bằng một thao tác O(n) được lặp hàng triệu lần.

## 5. Có phải dùng mảng thì dequeue luôn O(n)?

**Không.** Mảng chỉ là dạng lưu trữ; chính **bất biến về cách bố trí phần tử** quyết định số bước khi xóa đầu.

Nếu thay vì giữ đầu hàng tại ô `0`, ta lưu một chỉ số `front` trỏ tới phần tử đầu hiện hành, thao tác dequeue có thể:

1. Đọc phần tử tại `front`.
2. Bỏ tham chiếu không còn dùng, nếu cần.
3. Tăng `front` lên 1.

Không có phần tử nào phía sau phải dịch, nên việc lấy đầu chỉ tốn **O(1)**.

### Cách đơn giản: tăng chỉ số đầu

Giả sử mảng lưu `[A, B, C, D]` với `front = 0`:

```text
Bước 0: [A] [B] [C] [D]      front = 0
Bước 1: [×] [B] [C] [D]      front = 1, trả A
Bước 2: [×] [×] [C] [D]      front = 2, trả B
```

Dấu `×` chỉ vị trí không còn thuộc hàng đợi. Thứ tự logic được xác định bởi đoạn từ `front` tới cuối, thay vì bắt buộc bắt đầu tại vị trí vật lý `0`.

Tuy nhiên, nếu ta chỉ **tăng `front`** và **nối phần tử mới ở cuối mãi mãi**, vùng lưu trữ sẽ giữ những ô đã bị bỏ ở đầu. Khi thao tác lâu dài, bộ nhớ có thể tăng theo **tổng số lần thêm**, dù số phần tử đang chờ rất ít. Nếu định kỳ dồn các phần tử đang chờ trở về đầu, lần dồn đó lại tốn **O(n)**.

Vì vậy, tăng chỉ số đầu loại bỏ được việc dịch chuyển **sau mỗi dequeue**, nhưng cần thêm chiến lược **tái sử dụng các ô đã trống** để tránh lãng phí bộ nhớ.

## 6. Giải pháp phổ biến: hàng đợi mảng vòng

**Mảng vòng** (*circular array / circular buffer*) tái sử dụng ô trống ở đầu khi thao tác đến cuối mảng vật lý. Nó lưu:

- `data`: mảng có sức chứa `capacity`.
- `head`: chỉ số vật lý của phần tử đầu, nếu hàng không rỗng.
- `size`: số phần tử đang có, thỏa mãn `0 ≤ size ≤ capacity`.

Với `capacity > 0`, vị trí chèn mới ở cuối là:

```text
tail_index = (head + size) % capacity
```

Khi lấy phần tử đầu thành công:

```text
value = data[head]
data[head] = empty
head = (head + 1) % capacity
size = size - 1
```

Phép `%` là phép lấy phần dư: khi chỉ số đạt cuối mảng, nó quay về đầu mảng. Quan trọng là **không có bước dịch các phần tử đang chờ**.

### Ví dụ quay vòng

Mảng có bốn ô; ban đầu thứ tự logic là `A → B → C`:

```text
Chỉ số vật lý      0       1       2       3
                 +-------+-------+-------+-------+
Giá trị          |   A   |   B   |   C   | trống |
                 +-------+-------+-------+-------+

head = 0, size = 3
```

Lấy `A`, sau đó thêm `D` rồi thêm `E`:

```text
Sau dequeue A:   [trống] [ B ] [ C ] [trống]
                  head = 1, size = 2

Sau enqueue D:   [trống] [ B ] [ C ] [ D ]
                  head = 1, size = 3

Sau enqueue E:   [ E ] [ B ] [ C ] [ D ]
                  head = 1, size = 4
```

Mảng vật lý trông như `[E, B, C, D]`, nhưng thứ tự FIFO **đúng** vẫn là `B → C → D → E`. Phần tử `E` nằm tại ô vật lý `0` do vòng quay, không có nghĩa nó được phục vụ trước `B`.

### Cài đặt Python có sức chứa cố định

```python
class CircularQueue:
    def __init__(self, capacity):
        if capacity <= 0:
            raise ValueError("Sức chứa phải lớn hơn 0")
        self._data = [None] * capacity
        self._head = 0
        self._size = 0

    def __len__(self):
        return self._size

    def is_empty(self):
        return self._size == 0

    def is_full(self):
        return self._size == len(self._data)

    def enqueue(self, value):
        if self.is_full():
            raise OverflowError("Hàng đợi đã đầy")

        index = (self._head + self._size) % len(self._data)
        self._data[index] = value
        self._size += 1

    def peek(self):
        if self.is_empty():
            raise IndexError("Hàng đợi rỗng")
        return self._data[self._head]

    def dequeue(self):
        if self.is_empty():
            raise IndexError("Hàng đợi rỗng")

        value = self._data[self._head]
        self._data[self._head] = None  # Bỏ tham chiếu đến dữ liệu đã lấy.
        self._head = (self._head + 1) % len(self._data)
        self._size -= 1
        return value


q = CircularQueue(4)
for item in ["A", "B", "C"]:
    q.enqueue(item)

assert q.dequeue() == "A"
q.enqueue("D")
q.enqueue("E")  # Đặt E vào ô vật lý 0 đã trống.
assert q.is_full()
assert [q.dequeue(), q.dequeue(), q.dequeue(), q.dequeue()] == [
    "B", "C", "D", "E"
]
assert q.is_empty()
```

Mỗi phép `enqueue` và `dequeue` của **mảng vòng có sức chứa cố định** chỉ thực hiện một số hữu hạn phép đọc/ghi và tính chỉ số, nên đều là **O(1) trong trường hợp xấu nhất**, xét theo số phần tử.

Một số điểm cần lưu ý:

- Khi đầy, ví dụ báo `OverflowError`; một API khác có thể chọn chờ, bỏ yêu cầu hoặc mở rộng dung lượng.
- Vì biến `_size` tách biệt với các ô dữ liệu, giá trị **`None` vẫn có thể là phần tử hợp lệ**; ô trống không được xác định bằng cách kiểm tra nội dung là `None`.
- `_head` có thể khác `0` ngay cả khi vừa lấy hết mọi phần tử. Điều này hợp lệ vì `_size == 0` đã xác định trạng thái rỗng; lần chèn mới dùng công thức chỉ số tương ứng.
- Dùng mảng vòng **tự mở rộng** có thể làm chi phí `enqueue` O(n) ở thời điểm cấp phát/sao chép; với chiến lược tăng dung lượng hợp lý, chi phí thêm thường là **O(1) khấu hao**.

## 7. Chọn cấu trúc hàng đợi theo chi phí thực tế

| Cách lưu trữ | Thêm ở cuối | Lấy ở đầu | Bộ nhớ và đặc điểm |
|---|---|---|---|
| Mảng động, `append` + xóa/dịch ở `0` | O(1) khấu hao | **O(n)** | Mảng liên tiếp; dịch các vị trí còn lại |
| Mảng giữ chỉ số `front` và chỉ nối thêm cuối | O(1) khấu hao | O(1) | Cần cách thu hồi/tái dùng ô đầu; nếu không, bộ nhớ có thể tăng theo lịch sử thêm |
| Mảng vòng sức chứa cố định | O(1) | O(1) | **O(C)** cho sức chứa `C`; phải xử lý khi đầy |
| Mảng vòng tự mở rộng | O(1) khấu hao | O(1) | **O(C)**; một lần mở rộng có thể O(n) |
| Danh sách liên kết đơn có `head` và `tail` | O(1) | O(1) | **O(n)**; mỗi nút có thêm tham chiếu và chi phí cấp phát |
| `collections.deque` trong Python | O(1) | O(1) | Cấu trúc chuyên thao tác ở hai đầu |

`n` là số phần tử hiện hành, `C` là sức chứa được cấp phát; chi phí trên giả định các thao tác đọc/ghi ô và tham chiếu là hằng số.

Trong Python, lựa chọn thực tế thông dụng cho một hàng đợi FIFO là **`collections.deque`**, vì thêm cuối và lấy đầu đều hiệu quả:

```python
from collections import deque

tasks = deque()
tasks.append("Tiếp nhận")
tasks.append("Kiểm tra")
tasks.append("Phản hồi")

while tasks:
    print(tasks.popleft())
```

Đoạn mã in lần lượt:

```text
Tiếp nhận
Kiểm tra
Phản hồi
```

`deque` là **hàng đợi hai đầu**, nhưng khi dùng `append` để thêm và `popleft` để lấy, nó tuân thủ FIFO. Nếu hệ thống cần **đồng bộ giữa các luồng**, có thể cân nhắc `queue.Queue` thay cho ví dụ deque đơn giản; đây là yêu cầu vận hành khác với câu hỏi chi phí dịch chuyển.

## 8. Khi nào xóa đầu bằng dịch chuyển vẫn chấp nhận được?

Độ phức tạp O(n) không tự động khiến một cách cài đặt sai. Quyết định phụ thuộc vào **kích thước dữ liệu, tần suất xóa đầu và yêu cầu vận hành**.

Ví dụ:

- Một danh sách chỉ vài phần tử và rất hiếm khi xóa đầu có thể dùng `pop(0)` vì sự đơn giản.
- Một bộ xử lý hàng đợi có hàng chục nghìn yêu cầu và liên tục lấy việc ở đầu nên dùng cấu trúc hỗ trợ dequeue O(1).
- Nếu thuật toán phải duy trì **truy cập ngẫu nhiên theo chỉ số** và phần lớn thời gian duyệt tuần tự, mảng vẫn có ưu điểm về bố trí liên tiếp và tính cục bộ bộ nhớ; cần cân nhắc chi phí thao tác cụ thể.
- Nếu phải thường xuyên **thêm và lấy ở cả hai đầu**, một deque phù hợp hơn queue FIFO chỉ có hai phép chính.

Chi phí bộ nhớ cũng quan trọng. Mảng vòng cần vùng lưu trữ theo sức chứa; danh sách liên kết cấp phát nút linh hoạt nhưng có chi phí tham chiếu. Một mảng tự mở rộng có thể cần sao chép khi thay đổi sức chứa. **Không có một biểu diễn tốt nhất cho mọi tập thao tác.**

### Các nhầm lẫn cần tránh

| Nhận định | Điều chỉnh |
|---|---|
| “Mảng luôn khiến dequeue tốn O(n).” | Chỉ các cách cài đặt phải dịch phần tử để lấp ô đầu mới có chi phí đó; **mảng vòng** lấy đầu O(1). |
| “`pop(0)` đọc ô đầu nên phải O(1).” | Đọc ô đầu O(1), nhưng **xóa và dịch phần còn lại O(n)**. |
| “Dùng mã sao chép nhanh nên thành O(1).” | Hằng số thời gian có thể nhỏ, nhưng lượng dữ liệu dịch vẫn tăng cùng `n`. |
| “Mỗi lần thêm cuối đều O(1) tuyệt đối.” | Mảng động đôi khi phải mở rộng; thường chỉ bảo đảm **O(1) khấu hao**. |
| “Tăng `front` là xong mọi vấn đề.” | Còn phải quản lý **tái sử dụng hoặc thu hồi ô trống** để kiểm soát bộ nhớ. |
| “FIFO nghĩa là các việc sẽ hoàn thành đúng thứ tự.” | FIFO quy định **thứ tự lấy ra**; trong xử lý song song, thời điểm hoàn tất có thể khác. |

## 9. Tự kiểm tra

**Câu 1.** Mảng chứa `[5, 8, 13, 21, 34, 55]`. Nếu xóa phần tử đầu bằng cách dịch trái, phải chuyển bao nhiêu phần tử?

*Đáp án:* `6 - 1 = 5` phần tử: `8`, `13`, `21`, `34`, `55` đều dịch một ô.

**Câu 2.** Nếu một hàng đợi có `1.000` phần tử và lấy đầu đến khi rỗng bằng thuật toán dịch trái, tổng số lần dịch là bao nhiêu?

*Đáp án:* `1.000 × 999 / 2 = 499.500` lần chuyển vị trí, tương ứng độ phức tạp **Θ(n²)** của cả chuỗi.

**Câu 3.** Vì sao `queue.pop()` trên Python `list` không thay thế được `queue.pop(0)` khi yêu cầu FIFO?

*Đáp án:* `pop()` lấy ở **cuối**, nên khi `append` cũng thêm ở cuối, chuỗi thao tác trở thành **LIFO**. Hàng đợi FIFO phải lấy phần tử được thêm trước.

**Câu 4.** Mảng vòng có `capacity = 5`, `head = 4` và `size = 3`. Phần tử mới sẽ được thêm vào chỉ số vật lý nào?

*Đáp án:* `(4 + 3) % 5 = 2`. Không cần dồn các phần tử hiện tại về đầu mảng.

**Câu 5.** Tại sao có thể nói một lần xóa đầu có độ phức tạp Θ(n), còn cả quá trình xóa hết hàng có độ phức tạp Θ(n²)?

*Đáp án:* Mỗi lần xóa đầu từ hàng có `k` phần tử sẽ dịch `k - 1` vị trí. Khi `k` lần lượt giảm từ `n` xuống `1`, tổng số lần dịch là `n(n - 1)/2`.

**Ghi nhớ:** Xóa đầu một mảng đặc bằng dịch chuyển phải cập nhật **`n - 1` vị trí**, nên tốn **Θ(n)** cho một lần lấy đầu và có thể tốn **Θ(n²)** khi lặp xóa hết hàng. Nếu bài toán đòi hỏi enqueue/dequeue thường xuyên, hãy cân nhắc **mảng vòng, deque hoặc danh sách liên kết có đầu và cuối** để giữ thao tác lấy đầu ở O(1).
