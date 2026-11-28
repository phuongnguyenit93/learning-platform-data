# Hàng đợi vòng bằng mảng và chỉ số quay vòng

Trong một **hàng đợi FIFO** (*First In, First Out*), phần tử được đưa vào trước sẽ được lấy ra trước. Nếu dùng mảng và luôn đặt đầu hàng ở chỉ số `0`, việc xóa đầu có thể phải dịch `n - 1` phần tử, làm phép `dequeue` tốn **O(n)**. **Hàng đợi vòng** (*circular queue*, còn gọi là *ring buffer*) giải quyết nhược điểm này bằng cách lưu **chỉ số đầu hàng** và **quay vòng chỉ số** khi đi đến cuối mảng vật lý. Nhờ đó, cả thêm cuối và lấy đầu đều có thể thực hiện trong **O(1)** mà không phải dồn các phần tử.

Bài thuộc chương **Hàng đợi và deque** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Trong lộ trình xây dựng nền tảng cấu trúc dữ liệu qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, việc hiểu hàng đợi vòng giúp ta phân biệt **trật tự logic** với **vị trí lưu trữ**, thiết lập bất biến đúng và đánh giá chi phí thời gian, bộ nhớ để chọn cách cài đặt phù hợp.

## 1. Từ mảng tuyến tính đến mảng vòng

Giả sử mảng có **sức chứa** `C = 5`, đang lưu ba phần tử `A`, `B`, `C` theo thứ tự đến:

```text
Chỉ số vật lý:     0     1     2     3     4
                 +-----+-----+-----+-----+-----+
Nội dung:        |  A  |  B  |  C  |  ·  |  ·  |
                 +-----+-----+-----+-----+-----+
                   ↑           ↑
                 front        rear

Thứ tự logic: A → B → C
```

Khi lấy `A`, ta muốn `B` trở thành phần tử đầu. Có hai cách:

- **Dồn dữ liệu về đầu:** chuyển `B` về ô `0`, `C` về ô `1`. Nếu có `n` phần tử, việc dịch có thể cần `n - 1` lần gán.
- **Giữ dữ liệu và dời con trỏ đầu:** coi `head = 1` là vị trí của `B`; chỉ cần đánh dấu ô `0` không còn thuộc hàng đợi.

Cách thứ hai giúp lấy đầu O(1), nhưng nếu tiếp tục chỉ tăng chỉ số mà không tái sử dụng các ô trống, ta sẽ sớm đi hết mảng. Mảng vòng xem **sau ô cuối là ô đầu**: với `C = 5`, chỉ số hợp lệ quay theo chu trình `0 → 1 → 2 → 3 → 4 → 0 → 1 → …`.

Vì vậy, “vòng” nói đến **quy tắc tính chỉ số**, không có nghĩa các phần tử phải bị hoán đổi hoặc sao chép thành vòng.

## 2. Trạng thái tối thiểu và hợp đồng phép toán

Trong cách cài đặt dùng một mảng có sức chứa cố định, ta duy trì:

| Ký hiệu | Ý nghĩa | Điều kiện |
|---|---|---|
| `data` | Mảng vật lý gồm `C` ô | `C > 0` |
| `head` | Chỉ số vật lý của phần tử đầu, nếu hàng không rỗng | `0 ≤ head < C` |
| `size` | Số phần tử đang có | `0 ≤ size ≤ C` |
| `tail_index` | Vị trí **sẽ dùng cho lần enqueue tiếp theo** | `(head + size) % C` |

Trong biểu diễn này, `tail_index` **được tính khi cần**, không nhất thiết lưu thành trường riêng. Nó chỉ tới **ô sẽ chèn**, khác với “ô chứa phần tử cuối” trong trạng thái không rỗng. Khi `size > 0`, chỉ số của phần tử cuối hiện hành là `(head + size - 1) % C`.

Các phép toán queue phải tuân thủ hợp đồng:

| Phép toán | Hành vi | Trường hợp biên |
|---|---|---|
| `enqueue(x)` | Thêm `x` vào cuối hàng | Nếu `size == C`: báo đầy hoặc xử lý theo chính sách |
| `dequeue()` | Trả về và loại bỏ phần tử ở đầu | Nếu `size == 0`: báo rỗng |
| `peek()` | Xem phần tử đầu mà không xóa | Nếu `size == 0`: báo rỗng |
| `is_empty()` | Trả đúng khi `size == 0` | Không sửa trạng thái |
| `is_full()` | Trả đúng khi `size == C` | Áp dụng cho hàng có sức chứa giới hạn |
| `len()` / `size()` | Trả số phần tử hiện có | Không cần duyệt mảng |

**Bất biến FIFO:** thứ tự hàng đợi là dãy bắt đầu tại `data[head]`, rồi đi qua các ô `(head + 1) % C`, `(head + 2) % C`, …, cho đến đủ `size` phần tử. Vị trí lưu trong mảng vật lý có thể khác hẳn thứ tự ấy.

### Công thức ánh xạ chỉ số logic sang vật lý

Đánh số các phần tử đang chờ bằng chỉ số logic `j`, với `0 ≤ j < size`, tính từ đầu hàng:

```text
physical_index(j) = (head + j) % C
```

Khi đó:

- Phần tử đầu nằm ở `physical_index(0) = head`.
- Phần tử thứ hai nằm ở `(head + 1) % C`.
- Phần tử cuối nằm ở `physical_index(size - 1)`, nếu không rỗng.
- Ô chèn tiếp theo là `physical_index(size)`, **chỉ khi còn chỗ**.

Hợp đồng kiểu dữ liệu trừu tượng FIFO chỉ quan tâm dãy logic. Các công thức trên là chi tiết của **cách cài đặt mảng vòng**.

## 3. Phép modulo tạo ra chỉ số quay vòng

Với chỉ số không âm và `C > 0`, biểu thức `i % C` trả về phần dư trong khoảng từ `0` đến `C - 1`. Nếu ta tiến một ô sau vị trí `C - 1`:

```text
next_index = (C - 1 + 1) % C = 0
```

Ví dụ khi `C = 5`:

| Biểu thức | Kết quả | Ý nghĩa |
|---|---:|---|
| `(0 + 1) % 5` | 1 | Tiến sang ô 1 |
| `(3 + 1) % 5` | 4 | Tiến sang ô cuối |
| `(4 + 1) % 5` | 0 | Quay về đầu mảng |
| `(4 + 3) % 5` | 2 | Đi ba bước từ ô 4 |
| `(2 + 5) % 5` | 2 | Đi một vòng đầy trở lại ô 2 |

Dù `head` đã quay lại ô `0` nhiều lần, thứ tự FIFO vẫn đúng vì ta chỉ tiến đầu hàng khi **dequeue**, và chỉ thêm phần tử vào vị trí sau phần tử cuối hiện hành khi **enqueue**.

## 4. Thêm phần tử: `enqueue(x)`

Với cách lưu `head + size`, thuật toán có ba bước chính khi còn chỗ:

1. Tính `index = (head + size) % C`.
2. Ghi `data[index] = x`.
3. Tăng `size` lên một đơn vị.

```text
ENQUEUE(x):
    if size == C:
        báo lỗi "hàng đợi đầy"

    index = (head + size) % C
    data[index] = x
    size = size + 1
```

Không cần dịch bất kỳ phần tử nào. `head` **không đổi** khi enqueue; thứ tự phần tử đã tồn tại giữ nguyên, phần tử mới trở thành phần tử cuối.

**Trường hợp hàng rỗng:** `size = 0`, nên vị trí thêm mới là `(head + 0) % C = head`. Ta không buộc `head` phải đặt lại bằng `0` sau mỗi lần hàng rỗng. Chỉ cần `head` luôn là chỉ số hợp lệ, công thức sẽ tiếp tục làm việc.

**Trường hợp hàng đầy:** khi `size == C`, mọi ô vật lý đang được dùng. Phải xác định rõ chính sách: ném ngoại lệ, trả kết quả báo đầy, chờ chỗ trống hoặc tự mở rộng mảng. Ví dụ trong bài dùng mảng **sức chứa cố định** và báo lỗi khi đầy.

## 5. Lấy phần tử: `dequeue()`

Nếu hàng đợi không rỗng, phần tử cần lấy nằm ngay tại `data[head]`:

1. Lưu giá trị hiện tại tại `head` để trả về.
2. Xóa tham chiếu ở ô đó, nếu phù hợp với cách quản lý bộ nhớ.
3. Chuyển `head` sang `(head + 1) % C`.
4. Giảm `size` đi một đơn vị.

```text
DEQUEUE():
    if size == 0:
        báo lỗi "hàng đợi rỗng"

    result = data[head]
    data[head] = EMPTY
    head = (head + 1) % C
    size = size - 1
    return result
```

Trong giả mã, `EMPTY` chỉ việc dọn ô vật lý đã bỏ; **không được dùng giá trị ô để suy ra hàng rỗng**, vì `None` hay các giá trị đặc biệt khác có thể chính là dữ liệu hợp lệ. Trạng thái rỗng được xác định bằng `size == 0`.

Trái với thao tác xóa đầu bằng cách dịch mảng, phép `dequeue` này chỉ sửa một số lượng cố định ô và chỉ số, nên có chi phí **O(1)**.

**Trường hợp còn một phần tử:** sau khi lấy, `size = 0`. `head` vẫn có thể trỏ tới bất kỳ chỉ số hợp lệ nào; lần enqueue mới sẽ ghi tại vị trí ấy. Không có con trỏ nút `tail` nào cần xóa như trong danh sách liên kết đơn.

## 6. Truy vết chi tiết khi chỉ số quay vòng

Ta dùng mảng có `C = 5`. Dấu `·` thể hiện ô không thuộc hàng đợi, còn các giá trị in trong mảng là dữ liệu ở **vị trí vật lý**.

| Bước | Thao tác | Kết quả trả về | Mảng vật lý `[0,1,2,3,4]` | `head` | `size` | Thứ tự FIFO |
|---:|---|---|---|---:|---:|---|
| 0 | Khởi tạo | — | `[·, ·, ·, ·, ·]` | 0 | 0 | `[]` |
| 1 | `enqueue(A)` | — | `[A, ·, ·, ·, ·]` | 0 | 1 | `[A]` |
| 2 | `enqueue(B)` | — | `[A, B, ·, ·, ·]` | 0 | 2 | `[A, B]` |
| 3 | `enqueue(C)` | — | `[A, B, C, ·, ·]` | 0 | 3 | `[A, B, C]` |
| 4 | `dequeue()` | `A` | `[·, B, C, ·, ·]` | 1 | 2 | `[B, C]` |
| 5 | `enqueue(D)` | — | `[·, B, C, D, ·]` | 1 | 3 | `[B, C, D]` |
| 6 | `enqueue(E)` | — | `[·, B, C, D, E]` | 1 | 4 | `[B, C, D, E]` |
| 7 | `dequeue()` | `B` | `[·, ·, C, D, E]` | 2 | 3 | `[C, D, E]` |
| 8 | `enqueue(F)` | — | `[F, ·, C, D, E]` | 2 | 4 | `[C, D, E, F]` |
| 9 | `enqueue(G)` | — | `[F, G, C, D, E]` | 2 | 5 | `[C, D, E, F, G]` |
| 10 | `peek()` | `C` | `[F, G, C, D, E]` | 2 | 5 | `[C, D, E, F, G]` |

Tại **bước 8**, vị trí chèn `F` là:

```text
(head + size) % C
= (2 + 3) % 5
= 0
```

Tại **bước 9**, vị trí chèn `G` là `(2 + 4) % 5 = 1`. Lúc đó mảng **vật lý** là `[F, G, C, D, E]`, còn thứ tự **logic** từ `head = 2` là `C → D → E → F → G`.

Hình dung bước 9:

```text
Chỉ số vật lý:   0     1     2     3     4
                +-----+-----+-----+-----+-----+
data:           |  F  |  G  |  C  |  D  |  E  |
                +-----+-----+-----+-----+-----+
                            ↑
                          head = 2

Đường đọc logic từ head:
       2(C) → 3(D) → 4(E) → 0(F) → 1(G)
```

Lúc này **hàng đã đầy** vì `size == C == 5`. Gọi `enqueue(H)` phải báo đầy theo hợp đồng của phiên bản sức chứa cố định. `peek()` vẫn trả `C` mà không đổi trạng thái.

## 7. Cài đặt Python hoàn chỉnh

Ví dụ sau cài đặt **hàng đợi vòng sức chứa cố định** bằng `list` làm bộ nhớ vật lý. Nó dùng `_head` và `_size`, còn vị trí thêm mới được tính bằng công thức modulo.

```python
class CircularQueue:
    def __init__(self, capacity):
        if capacity <= 0:
            raise ValueError("capacity phải là số nguyên dương")
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
            raise IndexError("Không thể xem hàng đợi rỗng")
        return self._data[self._head]

    def dequeue(self):
        if self.is_empty():
            raise IndexError("Không thể lấy từ hàng đợi rỗng")

        value = self._data[self._head]
        self._data[self._head] = None
        self._head = (self._head + 1) % len(self._data)
        self._size -= 1
        return value

    def to_list(self):
        """Trả về các phần tử theo thứ tự FIFO để quan sát trạng thái."""
        capacity = len(self._data)
        return [
            self._data[(self._head + i) % capacity]
            for i in range(self._size)
        ]


q = CircularQueue(5)

for item in ["A", "B", "C"]:
    q.enqueue(item)

assert q.dequeue() == "A"
q.enqueue("D")
q.enqueue("E")
assert q.dequeue() == "B"
q.enqueue("F")
q.enqueue("G")

assert q.is_full()
assert q.peek() == "C"
assert q.to_list() == ["C", "D", "E", "F", "G"]
assert len(q) == 5
assert [q.dequeue() for _ in range(5)] == ["C", "D", "E", "F", "G"]
assert q.is_empty()

q.enqueue(None)  # None là dữ liệu hợp lệ, không đồng nghĩa hàng rỗng.
assert len(q) == 1
assert q.dequeue() is None
assert q.is_empty()
```

Các lựa chọn cần hiểu trong đoạn mã:

- **`len(self._data)` là sức chứa**, trong khi **`self._size` là số phần tử thực có**. Hai đại lượng này không thể dùng thay nhau.
- `is_full` kiểm tra `size == capacity`, còn `is_empty` kiểm tra `size == 0`; không suy ra trạng thái chỉ bằng nội dung một ô.
- Khi dequeue, gán `None` vào ô cũ để bỏ tham chiếu đến đối tượng không còn ở hàng. Nếu đối tượng được lưu là `None` thật, biến `size` vẫn phân biệt được nó với hàng rỗng.
- `to_list()` được thêm để **quan sát và kiểm tra**; nó duyệt `size` phần tử, do đó tốn O(n) thời gian và O(n) bộ nhớ cho danh sách kết quả. Điều này không làm thay đổi độ phức tạp O(1) của `enqueue`, `dequeue` và `peek`.
- Mã ví dụ hoạt động tuần tự; truy cập đồng thời giữa các luồng cần cơ chế đồng bộ riêng.

### Trường hợp biên với sức chứa bằng 1

Nếu `C = 1`, chỉ có chỉ số `0`. Mọi phép tăng chỉ số đều cho `(0 + 1) % 1 = 0`, nhưng hàng vẫn hoạt động đúng:

```python
single = CircularQueue(1)
assert single.is_empty()

single.enqueue("X")
assert single.is_full()
assert single.dequeue() == "X"
assert single.is_empty()

single.enqueue("Y")
assert single.dequeue() == "Y"
```

Đây là một bài kiểm tra hữu ích: thiết kế nào nhầm **`head == tail_index`** với “chắc chắn rỗng” sẽ gặp lỗi trong tình huống này.

## 8. Phân biệt trạng thái rỗng và đầy

Với kiểu lưu `head + size`, cách phân biệt rõ ràng:

```text
Rỗng: size == 0
Đầy:  size == capacity
```

Khi xét vị trí chèn tiếp theo:

```text
tail_index = (head + size) % capacity

Nếu rỗng: size = 0        ⇒ tail_index = head
Nếu đầy:  size = capacity ⇒ tail_index = head
```

Vậy **`tail_index == head` xuất hiện ở cả trạng thái rỗng và đầy**. Chỉ nhìn hai chỉ số không đủ để phân biệt.

Có những cách biểu diễn khác:

1. **Lưu `size`:** dùng đủ cả `C` ô để chứa phần tử; cần cập nhật thêm bộ đếm khi thêm/lấy.
2. **Chừa một ô trống:** dùng `head` và `tail` với quy ước `head == tail` là rỗng, còn `(tail + 1) % C == head` là đầy. Khi đó mảng `C` ô chỉ chứa tối đa `C - 1` phần tử.
3. **Thêm cờ trạng thái:** dùng chỉ số kết hợp cờ đầy/rỗng; phải bảo đảm cập nhật cờ ở mọi nhánh.

Không có công thức “đầy” hay “rỗng” chung cho mọi biến thể nếu chưa biết **quy ước về `head`, `tail` và sức chứa hữu dụng**. Bài này chọn cách thứ nhất vì bất biến rõ ràng và không lãng phí một ô.

### Bất biến cần duy trì

Với `C > 0`:

- `0 ≤ head < C`.
- `0 ≤ size ≤ C`.
- Nếu `size > 0`, có đúng `size` vị trí logic, lần lượt là `(head + j) % C` với `j = 0, 1, …, size - 1`.
- Các vị trí logic ấy chứa các phần tử theo **đúng thứ tự enqueue chưa bị dequeue**.
- Nếu `size < C`, ô chèn tại `(head + size) % C` không thuộc dãy phần tử đang chờ; nếu `size == C` thì không có ô trống.
- Hàng rỗng không có phần tử đầu hợp lệ; giá trị còn lại trong các ô ngoài dãy logic (nếu cài đặt không dọn ô) không được xem là dữ liệu đang chờ.

Các bất biến này giúp kiểm tra tính đúng đắn mà không cần dựa vào giả định rằng hàng đợi luôn chiếm một đoạn liên tiếp từ chỉ số `0`.

## 9. Tại sao phép thêm và lấy vẫn giữ FIFO?

Có thể chứng minh bằng quy nạp theo số phép toán thành công.

**Cơ sở.** Lúc khởi tạo, `size = 0` nên dãy logic rỗng; FIFO đúng hiển nhiên.

**Bước enqueue.** Giả sử dãy logic hiện tại là `[q₀, q₁, …, qₖ₋₁]` và `k < C`. Vị trí thêm mới là `(head + k) % C`, ngay **sau** `k` vị trí logic đang dùng. Ghi `x` vào đó tạo dãy mới `[q₀, q₁, …, qₖ₋₁, x]`; thứ tự cũ không đổi, phần tử mới nằm cuối.

**Bước dequeue.** Nếu `k > 0`, phần tử được lấy ra là `data[head] = q₀`. Sau khi đặt `head = (head + 1) % C` và giảm `size` xuống `k - 1`, dãy logic mới là `[q₁, …, qₖ₋₁]`. Phần tử được thêm sớm nhất trong số phần tử còn chờ trở thành đầu hàng.

**Bước peek.** Chỉ đọc `data[head]`, không thay đổi trạng thái.

Vì mọi thao tác thành công đều duy trì thứ tự, hàng đợi vòng thực hiện đúng hợp đồng FIFO. Việc “quay” chỉ số không ảnh hưởng đến lập luận vì các vị trí logic luôn được tính **theo modulo cùng một sức chứa**.

## 10. Phân tích độ phức tạp thời gian và bộ nhớ

Với `n = size` và `C = capacity`:

| Thao tác | Thời gian | Bộ nhớ phụ phát sinh | Giải thích |
|---|---:|---:|---|
| `enqueue(x)`, còn chỗ | **O(1)** | O(1) | Một lần tính modulo, ghi ô, tăng bộ đếm |
| `dequeue()`, không rỗng | **O(1)** | O(1) | Đọc/xóa một ô, tăng chỉ số đầu, giảm bộ đếm |
| `peek()` | **O(1)** | O(1) | Truy cập trực tiếp `data[head]` |
| `is_empty()`, `is_full()`, `len()` | **O(1)** | O(1) | Kiểm tra bộ đếm |
| Xem toàn bộ `n` phần tử theo thứ tự FIFO | **O(n)** | O(n) nếu tạo bản sao | Phải đọc `n` phần tử |
| Khởi tạo mảng `C` ô | **O(C)** | **O(C)** | Cấp phát và khởi tạo vùng chứa |

**Bộ nhớ lưu trữ của toàn bộ hàng đợi là O(C)**: mảng có `C` ô và ba thông tin trạng thái chính (tham chiếu mảng, `head`, `size`). Mỗi thao tác enqueue/dequeue sử dụng thêm O(1) bộ nhớ. Nếu `C` được chọn theo quy mô dữ liệu, có thể diễn đạt mức lưu trữ là O(C) hoặc O(n) khi sức chứa tỷ lệ với số phần tử.

Đối với phiên bản **sức chứa cố định**, các phép thêm và lấy có O(1) ngay cả trong **trường hợp xấu nhất** của phép toán thành công, theo mô hình truy cập mảng và số học chỉ số chi phí hằng số. Không có bước dịch `n - 1` phần tử.

Nếu đổi sang **mảng vòng có tự mở rộng**, khi đầy có thể cấp phát mảng lớn hơn và chép lại `n` phần tử theo thứ tự logic:

```text
for j = 0 ... size - 1:
    new_data[j] = old_data[(head + j) % old_capacity]

head = 0
data = new_data
```

Lần mở rộng đó tốn **O(n)**, nhưng nếu dung lượng tăng theo hệ số, ví dụ gấp đôi, thì một chuỗi các lần enqueue có chi phí **O(1) khấu hao cho mỗi lần thêm**. Cần phân biệt kết luận này với O(1) **trường hợp xấu nhất** của phiên bản cố định. Việc thu nhỏ dung lượng, nếu có, cần chính sách phù hợp để tránh lặp mở rộng/thu nhỏ liên tục.

## 11. So sánh với các cách lưu hàng đợi khác

| Cách cài đặt | `enqueue` | `dequeue` | Đặc điểm đáng chú ý |
|---|---|---|---|
| Mảng đặc, xóa đầu bằng dịch trái | O(1) khấu hao nếu mảng động | **O(n)** | Giữ đầu tại chỉ số 0; xóa đầu phải dồn các phần tử |
| Mảng vòng sức chứa cố định | **O(1)** | **O(1)** | Tái dùng ô cũ; yêu cầu xử lý trường hợp đầy |
| Mảng vòng tự mở rộng | O(1) khấu hao | O(1) | Thỉnh thoảng phải cấp phát và chép O(n) phần tử |
| Danh sách liên kết đơn có `head` và `tail` | **O(1)** | **O(1)** | Số nút linh hoạt, thêm chi phí liên kết/cấp phát từng nút |
| `collections.deque` trong Python | **O(1)** | **O(1)** | Có sẵn thao tác hiệu quả ở cả hai đầu |

Mảng vòng phù hợp khi muốn **bộ nhớ theo sức chứa dự kiến**, truy cập nhanh vào ô đầu và tái sử dụng vùng chứa. Danh sách liên kết không yêu cầu mảng liên tục nhưng mỗi nút có chi phí bộ nhớ và cấp phát riêng.

**Deque** (*double-ended queue*) tổng quát hơn queue FIFO: cho phép thêm và lấy ở **cả hai đầu**. Hàng đợi vòng trong bài chỉ định nghĩa thêm ở cuối và lấy ở đầu, nhưng một mảng vòng cũng có thể mở rộng để hỗ trợ đầy đủ thao tác deque bằng cách dịch `head` lùi một ô theo modulo khi thêm ở đầu và thay đổi chỉ số phía cuối khi lấy ở cuối.

## 12. Ứng dụng và giới hạn trong thực tế

**Bộ đệm nhận dữ liệu.** Một thiết bị hoặc tiến trình liên tục nhận mẫu dữ liệu và hệ thống khác lấy mẫu ra theo thứ tự đến. Mảng vòng tái sử dụng vùng nhớ cố định và tránh dịch toàn bộ phần tử sau mỗi lần đọc.

**Hàng chờ tác vụ có giới hạn.** Một hệ thống đặt sức chứa tối đa cho các tác vụ chờ xử lý. Khi đầy, ứng dụng phải đưa ra quyết định: chặn người gửi, báo lỗi, bỏ tác vụ mới hoặc áp dụng một chính sách bỏ dữ liệu cũ đã được quy định. Queue thông thường trong bài **không tự ghi đè phần tử đầu** khi đầy; làm vậy sẽ thay đổi hợp đồng và có thể mất dữ liệu chưa xử lý.

**BFS trong đồ thị.** Duyệt theo chiều rộng có thể dùng queue để lấy các đỉnh theo thứ tự phát hiện. Mảng vòng phát huy hiệu quả khi có sức chứa phù hợp, đồng thời giúp thuật toán tránh chi phí O(n) lặp lại của việc xóa đầu mảng bằng dịch chuyển.

**Hệ thống thời gian thực hoặc nhúng.** Sức chứa biết trước và số bước xử lý cố định giúp dự đoán chi phí mỗi thao tác, miễn là các yêu cầu về đồng thời và xử lý đầy/rỗng đã được giải quyết.

Những giới hạn cần lưu ý:

- **Sức chứa hữu hạn:** phải chủ động chọn `C` và cách báo đầy. Nếu khối lượng đến liên tục lớn hơn tốc độ xử lý, hàng đợi có thể đầy dù dequeue O(1).
- **Đồng thời:** mảng vòng đơn giản không tự bảo đảm an toàn khi nhiều luồng đồng thời thêm/lấy. Những biến thể lock-free cần thêm cơ chế đồng bộ bộ nhớ và quy tắc quản lý chỉ số.
- **Thứ tự hoàn thành:** FIFO bảo đảm thứ tự **lấy việc**, không tự bảo đảm thứ tự công việc **kết thúc** nếu xử lý song song.
- **Lưu trữ dữ liệu:** bộ đếm `size` và `head` phải luôn đồng bộ với những thao tác thực sự thành công; ngoại lệ ở giữa quá trình cập nhật có thể phá bất biến nếu API được mở rộng phức tạp hơn.

## 13. Lỗi thường gặp khi cài đặt

| Lỗi | Hậu quả | Cách kiểm tra |
|---|---|---|
| Tăng chỉ số mà quên `% C` | Truy cập ra ngoài mảng sau khi đến ô cuối | Thử `head = C - 1` rồi dequeue |
| Dùng `head == tail_index` để kết luận rỗng | Nhầm hàng **đầy** thành rỗng | Kiểm tra cả `size = 0` và `size = C` |
| Dùng `data[head] is None` để xác định rỗng | Nhầm dữ liệu `None` hợp lệ với ô trống | Thử `enqueue(None)` và `dequeue()` |
| Tính ô thêm là `(head + size - 1) % C` | Ghi đè phần tử cuối thay vì thêm mới | Thử enqueue hai phần tử liên tiếp |
| Giảm `size` trước rồi lấy sai vị trí đầu | Trả sai phần tử hoặc đảo thứ tự | Đối chiếu với mô hình FIFO sau mỗi bước |
| Quên cập nhật `size` khi thêm/lấy | Báo đầy/rỗng sai, đọc ô ngoài dãy logic | Kiểm tra `0 ≤ size ≤ C` |
| Không kiểm tra đầy trước khi ghi | Ghi đè dữ liệu chưa được dequeue | Thử thêm phần tử thứ `C + 1` |
| Giả định hàng rỗng thì `head` phải bằng 0 | Loại nhầm trạng thái hợp lệ hoặc reset thừa | Lấy hết hàng sau nhiều lần quay vòng |
| Nhầm sức chứa vật lý với số phần tử | Truy vấn size sai, tính index sai | Kiểm tra `len(queue)` sau mọi thao tác |

Khi có lỗi thứ tự, cách hiệu quả là tự viết dãy FIFO mong đợi bên cạnh mảng vật lý, rồi theo dõi `head` và `size` sau từng phép toán. Dãy mong đợi sẽ cho biết ngay phần tử nào cần được trả về, dù ô vật lý trông không theo thứ tự.

## 14. Bài tập tự kiểm tra

**Bài 1 — Chọn chỉ số chèn.** Mảng vòng có `C = 6`, `head = 4` và `size = 3`. Phần tử mới sẽ được chèn tại ô nào?

*Lời giải:* `(4 + 3) % 6 = 1`. Các phần tử đang chờ chiếm ba vị trí logic `4, 5, 0`; ô `1` là vị trí tiếp theo.

**Bài 2 — Truy vết FIFO.** Hàng đợi `C = 4` khởi tạo rỗng với `head = 0`. Thực hiện `enqueue(10)`, `enqueue(20)`, `enqueue(30)`, `dequeue()`, `enqueue(40)`, `enqueue(50)`. Mảng vật lý, `head`, `size` và thứ tự lấy ra là gì?

*Lời giải:* Lần dequeue trả `10`. Trạng thái cuối có mảng vật lý `[50, 20, 30, 40]`, `head = 1`, `size = 4`. Thứ tự FIFO là `20 → 30 → 40 → 50`. Hàng đang đầy.

**Bài 3 — Rỗng hay đầy?** Với `C = 5` và `head = 2`, ta tính được `tail_index = 2`. Có thể khẳng định hàng rỗng không?

*Lời giải:* **Không.** Có thể `size = 0` (rỗng) **hoặc** `size = 5` (đầy). Cần kiểm tra `size` hoặc thông tin trạng thái tương đương.

**Bài 4 — Độ phức tạp.** Hai hàng đợi cùng có `n` phần tử: A xóa đầu bằng dịch trái; B dùng mảng vòng sức chứa cố định. Nêu số phần tử bị dịch và thời gian của một lần dequeue trong hai cách.

*Lời giải:* A phải dịch `n - 1` phần tử, mất **Θ(n)** khi `n` lớn. B chỉ đọc ô đầu, tăng `head` theo modulo và giảm `size`, mất **O(1)**.

**Bài 5 — Sức chứa một ô.** Với `C = 1`, sau khi enqueue một phần tử, chỉ số thêm tiếp theo vẫn bằng `head`. Vì sao không thể thêm tiếp?

*Lời giải:* Vì `size == C == 1`, hàng **đầy**. Trùng chỉ số không nói lên việc ô đang trống hay có dữ liệu; phải kiểm tra bộ đếm trước khi ghi.

**Điểm cần nhớ:** Hàng đợi vòng giữ nguyên các phần tử trong mảng và quay vòng **chỉ số** bằng phép modulo. Bất biến `0 ≤ size ≤ C`, công thức `(head + size) % C` cho ô chèn và `(head + 1) % C` cho đầu mới cho phép duy trì FIFO với **enqueue/dequeue O(1)** và bộ nhớ **O(C)** khi sức chứa cố định.
