# Cài đặt hàng đợi bằng hai ngăn xếp và chi phí khấu hao

Một **hàng đợi (queue)** tuân theo **FIFO** (*First In, First Out*): phần tử được đưa vào trước phải được lấy ra trước. Trong khi đó, **ngăn xếp (stack)** tuân theo **LIFO** (*Last In, First Out*): phần tử được thêm sau cùng sẽ được lấy ra đầu tiên. Nghe có vẻ trái ngược, nhưng **hai stack có thể phối hợp để tạo một queue đúng nghĩa** mà không cần tự viết danh sách liên kết hay mảng vòng.

Ý tưởng then chốt là dùng một stack để **nhận phần tử mới**, một stack để **phục vụ phần tử cũ**. Chỉ khi stack phục vụ đã rỗng, ta mới chuyển lần lượt toàn bộ phần tử từ stack nhận sang stack phục vụ. Việc chuyển có thể tốn **O(n)** cho một thao tác, nhưng mỗi phần tử chỉ được chuyển **tối đa một lần**. Vì vậy, trong một chuỗi thao tác dài, `enqueue`, `dequeue` và `peek` có thời gian **O(1) khấu hao** (*amortized*).

Bài thuộc chương **Hàng đợi và deque** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, trong lộ trình học mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị. Ta sẽ học cách xác lập bất biến FIFO, thực hiện từng thao tác, phân biệt chi phí trường hợp xấu nhất với chi phí khấu hao, và chọn cấu trúc dữ liệu thích hợp theo yêu cầu thời gian, bộ nhớ.

## 1. Từ hai quy tắc đối lập đến một hàng đợi FIFO

Queue và stack khác nhau ở vị trí lấy phần tử:

| Cấu trúc | Thêm phần tử | Lấy phần tử | Quy tắc |
|---|---|---|---|
| Queue | `enqueue(x)` vào cuối | `dequeue()` ở đầu | **FIFO** |
| Stack | `push(x)` lên đỉnh | `pop()` từ đỉnh | **LIFO** |

Giả sử lần lượt thêm `A`, `B`, `C`:

```text
Hàng đợi mong muốn:
front                        rear
  ↓                            ↓
 [A] ───→ [B] ───→ [C]

Thứ tự dequeue đúng: A, rồi B, rồi C.
```

Nếu chỉ dùng **một stack** và `push(A)`, `push(B)`, `push(C)`, đỉnh stack là `C`. Lần `pop()` đầu tiên trả `C`, tức **sai quy tắc FIFO**.

Tuy nhiên, khi lấy hết các phần tử từ stack thứ nhất và lần lượt đẩy sang stack thứ hai, thứ tự bị **đảo ngược**:

```text
Stack nhận (in)              Stack phục vụ (out)
     TOP                            TOP
      ↓                              ↓
     [C]                            [A]
     [B]      chuyển lần lượt       [B]
     [A]  ────────────────────→     [C]
   BOTTOM                          BOTTOM

in trở thành rỗng. Đỉnh out là A, đúng phần tử FIFO cần lấy.
```

Việc **đảo thứ tự hai lần** là cơ sở của giải pháp: thứ tự LIFO trong `in` bị đảo khi chuyển sang `out`, để phần tử cũ nhất trở thành phần tử dễ lấy nhất ở đỉnh `out`.

## 2. Hai stack giữ vai trò khác nhau

Gọi hai stack là:

- **`in` (input stack):** mọi phần tử mới được `enqueue` đều `push` vào đỉnh stack này.
- **`out` (output stack):** mọi lần `dequeue` đều `pop` từ đỉnh stack này; `peek` cũng xem đỉnh `out`.

Nếu `out` **đang có phần tử**, ta cứ lấy từ `out`; không động tới `in`. Nếu `out` **rỗng**, ta chuyển hết các phần tử từ `in` sang `out`:

```text
while in không rỗng:
    out.push(in.pop())
```

Chỉ sau khi chuyển xong mới tiếp tục `dequeue` hoặc `peek`. Trường hợp cả hai stack đều rỗng, queue rỗng và phép lấy/xem phải báo lỗi theo hợp đồng API.

**Quy tắc quan trọng nhất:** chỉ chuyển dữ liệu **khi `out` rỗng**. Nếu chuyển ngay mỗi lần có phần tử mới, phần tử đến sau có thể nằm trên những phần tử đang chờ cũ trong `out`, làm sai FIFO. Ngoài ra, việc đảo qua lại nhiều lần sẽ phá lợi thế chi phí khấu hao.

### Mỗi stack có thứ tự từ đáy lên đỉnh

Để không nhầm trong bảng truy vết, bài viết `[A, B, C]` cho stack chứa `A` ở **đáy** và `C` ở **đỉnh**. Phần tử có thể lấy bằng `pop()` là phần tử **bên phải** trong biểu diễn này.

Khi đó, thứ tự queue logic chính là:

```text
queue = reverse(out) + in
```

Ở đây `+` là phép nối **dãy**, không phải cộng số. Với `out = [C, B]` và `in = [D, E]`:

```text
reverse(out) = [B, C]
in           = [D, E]
queue        = [B, C, D, E]
```

Nghĩa là các phần tử trong `out` (đọc từ đỉnh xuống đáy) luôn được phục vụ **trước** những phần tử còn ở `in` (đọc từ đáy lên đỉnh). Đây là **bất biến biểu diễn** quan trọng để chứng minh thuật toán đúng.

## 3. Thuật toán `enqueue(x)`

Thêm phần tử mới luôn rất đơn giản:

```text
ENQUEUE(x):
    in.push(x)
```

Ví dụ:

```text
Ban đầu:
in  = [A, B]
out = [C]

enqueue(D):
in  = [A, B, D]
out = [C]

Thứ tự queue logic:
reverse([C]) + [A, B, D] = [C, A, B, D]
```

Nếu `out` còn phần tử, phần tử đó được phục vụ trước `D`. `D` mới đến nằm ở cuối dãy logic, đúng FIFO. Không cần chuyển dữ liệu từ `in` sang `out` khi enqueue.

Theo mô hình thao tác trên stack, `enqueue` dùng đúng một lần `push` nên có **O(1)** thời gian cho thao tác stack chuẩn. Với ngăn xếp cài bằng mảng động Python `list`, `append` có **O(1) khấu hao**, do thỉnh thoảng mảng bên trong phải mở rộng.

## 4. Thuật toán `dequeue()` và `peek()`

Cả hai thao tác đều cần phần tử **cũ nhất**, tức đỉnh `out` sau khi chuẩn bị:

```text
PREPARE_FRONT():
    if out rỗng:
        while in không rỗng:
            out.push(in.pop())

DEQUEUE():
    PREPARE_FRONT()
    if out rỗng:
        báo lỗi "queue rỗng"
    return out.pop()

PEEK():
    PREPARE_FRONT()
    if out rỗng:
        báo lỗi "queue rỗng"
    return out.top()
```

**`dequeue()`** trả về và xóa một phần tử; **`peek()`** chỉ trả về giá trị, không làm thay đổi **dãy logic** của queue. Tuy nhiên, `peek()` có thể **làm thay đổi hai stack bên trong** khi lần đầu cần chuyển dữ liệu từ `in` sang `out`. Điều này hoàn toàn hợp lệ: kiểu dữ liệu trừu tượng chỉ yêu cầu nội dung và thứ tự queue không đổi, chứ không buộc bố trí vật lý giữ nguyên.

Khi `out` đang có phần tử, `dequeue`/`peek` chỉ thực hiện một phép `pop` hoặc `top`, tốn **O(1)**. Nếu `out` rỗng nhưng `in` có `k` phần tử, thao tác phải chuyển `k` phần tử với **2k thao tác stack** (một `pop` và một `push` cho mỗi phần tử), nên một lần gọi cụ thể có thể tốn **O(k)**.

## 5. Truy vết một chuỗi thao tác xen kẽ

Bắt đầu từ queue rỗng. Trong hai cột stack, phần tử **bên phải là đỉnh**. Bảng giúp phân biệt thứ tự vật lý của hai stack với thứ tự FIFO logic:

| Bước | Thao tác | `in` (đáy → đỉnh) | `out` (đáy → đỉnh) | Kết quả | Queue logic (front → rear) |
|---:|---|---|---|---|---|
| 0 | Khởi tạo | `[]` | `[]` | — | `[]` |
| 1 | `enqueue(A)` | `[A]` | `[]` | — | `[A]` |
| 2 | `enqueue(B)` | `[A, B]` | `[]` | — | `[A, B]` |
| 3 | `enqueue(C)` | `[A, B, C]` | `[]` | — | `[A, B, C]` |
| 4 | `peek()` | `[]` | `[C, B, A]` | `A` | `[A, B, C]` |
| 5 | `dequeue()` | `[]` | `[C, B]` | `A` | `[B, C]` |
| 6 | `enqueue(D)` | `[D]` | `[C, B]` | — | `[B, C, D]` |
| 7 | `enqueue(E)` | `[D, E]` | `[C, B]` | — | `[B, C, D, E]` |
| 8 | `dequeue()` | `[D, E]` | `[C]` | `B` | `[C, D, E]` |
| 9 | `dequeue()` | `[D, E]` | `[]` | `C` | `[D, E]` |
| 10 | `peek()` | `[]` | `[E, D]` | `D` | `[D, E]` |
| 11 | `dequeue()` | `[]` | `[E]` | `D` | `[E]` |
| 12 | `dequeue()` | `[]` | `[]` | `E` | `[]` |

Ở bước 4, lần đầu `peek` khiến ba phần tử `A, B, C` chuyển từ `in` sang `out`, nhưng dãy queue vẫn `[A, B, C]`. Ở bước 6–7, `D` và `E` được đưa vào `in`, trong khi `B`, `C` vẫn chờ trong `out`. Hai phần tử cũ phải được lấy **trước** các phần tử mới.

Ở bước 10, khi `out` đã trống, thuật toán mới chuyển `D` và `E`; đỉnh `out` trở thành `D`. Như vậy, mọi lần lấy thành công đều theo đúng thứ tự `A, B, C, D, E`.

### Trường hợp nên tự kiểm tra

- **Chỉ enqueue liên tiếp:** dữ liệu dồn trong `in`, lần dequeue/peek đầu tiên sẽ chuyển toàn bộ.
- **Chỉ dequeue liên tiếp:** sau một lần chuyển, các lần sau lấy trực tiếp từ `out` cho tới khi rỗng.
- **Enqueue xen kẽ khi `out` chưa rỗng:** phần tử mới vẫn phải xếp sau các phần tử cũ.
- **Queue rỗng:** cả hai stack đều rỗng; dequeue và peek phải báo đúng lỗi đã định.
- **Một phần tử:** chuyển từ `in` sang `out` rồi lấy; sau đó cả hai rỗng.
- **Giá trị trùng nhau hoặc `None`:** không dùng nội dung giá trị để nhận biết trạng thái rỗng.

## 6. Cài đặt Python hoàn chỉnh

Trong Python, `list` có thể dùng làm **stack** vì `append` thêm vào cuối và `pop()` lấy từ cuối. Chúng ta dùng **hai danh sách** riêng để hiện thực queue.

```python
class TwoStackQueue:
    def __init__(self):
        self._in = []
        self._out = []

    def __len__(self):
        return len(self._in) + len(self._out)

    def is_empty(self):
        return not self._in and not self._out

    def enqueue(self, value):
        self._in.append(value)

    def _prepare_front(self):
        if not self._out:
            while self._in:
                self._out.append(self._in.pop())

    def peek(self):
        self._prepare_front()
        if not self._out:
            raise IndexError("Không thể xem queue rỗng")
        return self._out[-1]

    def dequeue(self):
        self._prepare_front()
        if not self._out:
            raise IndexError("Không thể lấy từ queue rỗng")
        return self._out.pop()


q = TwoStackQueue()
assert q.is_empty()

q.enqueue("A")
q.enqueue("B")
q.enqueue("C")
assert len(q) == 3

assert q.peek() == "A"        # Có thể chuyển ba phần tử.
assert len(q) == 3            # Peek không làm đổi số phần tử.
assert q.dequeue() == "A"

q.enqueue("D")
q.enqueue("E")
assert [q.dequeue(), q.dequeue()] == ["B", "C"]
assert q.peek() == "D"        # Chuyển D, E khi _out rỗng.
assert [q.dequeue(), q.dequeue()] == ["D", "E"]
assert q.is_empty()
```

Trong mã trên:

- `_in` và `_out` là **chi tiết cài đặt**; người dùng chỉ thao tác qua `enqueue`, `dequeue`, `peek`, `len` và `is_empty`.
- `_prepare_front` được chia thành hàm riêng để tránh viết lặp logic chuyển stack trong hai phép lấy/xem.
- Việc chuyển chỉ xảy ra khi `_out` rỗng. Khi `_out` đang có dữ liệu, mọi phần tử mới tiếp tục nằm trong `_in`.
- `peek` dùng `_out[-1]` để đọc đỉnh mà **không xóa**.
- Kích thước có thể tính ngay bằng tổng độ dài hai stack; trong Python, `len(list)` là O(1).
- Mã minh họa sử dụng tuần tự; nó chưa phải hàng đợi đồng bộ giữa nhiều luồng.

### Thử các tình huống biên

```python
q = TwoStackQueue()

# Rỗng: lấy/xem phải báo lỗi.
for operation in (q.peek, q.dequeue):
    try:
        operation()
    except IndexError:
        pass
    else:
        raise AssertionError("Phải báo lỗi khi queue rỗng")

# Các giá trị trùng nhau vẫn là các phần tử riêng biệt.
q.enqueue(7)
q.enqueue(7)
q.enqueue(9)
assert [q.dequeue(), q.dequeue(), q.dequeue()] == [7, 7, 9]

# None là giá trị được phép lưu, không phải dấu hiệu rỗng.
q.enqueue(None)
q.enqueue("X")
assert q.peek() is None
assert q.dequeue() is None
assert q.dequeue() == "X"
assert q.is_empty()

# Có thể tái sử dụng sau khi đã lấy hết.
q.enqueue("Y")
assert q.dequeue() == "Y"
assert len(q) == 0
```

Ở queue rỗng, `peek` và `dequeue` trả lỗi rõ ràng. Nếu dùng giá trị `None` để báo rỗng, kết quả sẽ nhập nhằng khi người dùng chủ động `enqueue(None)`. Vì vậy, API nên dùng ngoại lệ hoặc kiểu kết quả biểu thị rỗng tách biệt.

## 7. Chứng minh tính đúng đắn FIFO bằng bất biến

Ta cần chứng minh mọi chuỗi thao tác hợp lệ giữ đúng thứ tự queue, kể cả khi các lần chuyển stack xảy ra sau một khoảng thời gian dài.

**Bất biến biểu diễn:**

```text
Q = reverse(out) + in
```

Trong đó `in` và `out` được viết từ **đáy lên đỉnh**, còn `Q` được viết từ **đầu đến cuối**. Đối với `out`, phần tử đỉnh được lấy trước; đối với `in`, các phần tử vẫn giữ thứ tự đến từ đáy lên đỉnh cho tới khi chuyển.

### Cơ sở

Ban đầu `in = []` và `out = []`. Do vậy `Q = []`, phù hợp với hàng đợi rỗng.

### Bước enqueue

Giả sử bất biến đúng trước khi thêm `x`:

```text
Q = reverse(out) + in
```

`enqueue(x)` chỉ `push(x)` lên đỉnh `in`, nên:

```text
in_new = in + [x]
Q_new = reverse(out) + in + [x] = Q + [x]
```

Phần tử mới nằm ở **cuối** queue, đúng hợp đồng FIFO.

### Bước chuyển stack

Chỉ chuyển khi `out` rỗng. Gọi dãy `in` từ đáy lên đỉnh là `[a₀, a₁, …, aₖ₋₁]`. Khi lấy `aₖ₋₁` ra rồi đẩy vào `out`, tiếp tục cho đến hết, ta có:

```text
in_new  = []
out_new = [a(k-1), ..., a1, a0]   (từ đáy lên đỉnh)
```

Khi đó:

```text
reverse(out_new) + in_new
= [a0, a1, ..., a(k-1)]
= Q_old
```

**Thao tác chuyển không làm đổi queue logic**, chỉ đổi vị trí lưu trữ. Sau đó, đỉnh `out` là `a₀`, tức phần tử đến sớm nhất.

### Bước dequeue và peek

Nếu `out` có phần tử, đỉnh `out` chính là phần tử đầu `Q`. `dequeue()` lấy đỉnh ấy, khiến `Q` mất đúng phần tử đầu; `peek()` chỉ đọc và giữ nguyên `Q`.

Nếu `out` rỗng, thuật toán chuyển toàn bộ `in` trước, nên lập luận trên vẫn áp dụng. Nếu cả hai rỗng, thao tác báo lỗi mà không làm thay đổi trạng thái hợp lệ.

Vì bất biến đúng lúc khởi tạo và được giữ sau mọi thao tác, cấu trúc hai stack **thực hiện đúng queue FIFO**.

## 8. Vì sao có thao tác O(n) nhưng chi phí khấu hao O(1)?

Đây là phần khác biệt quan trọng nhất giữa **chi phí của một lần gọi** và **chi phí của cả một chuỗi gọi**.

Giả sử `in` đang chứa `k` phần tử và `out` rỗng. Một lần `dequeue` hoặc `peek` cần:

- `k` lần `pop` khỏi `in`;
- `k` lần `push` vào `out`;
- một lần `pop` hoặc đọc đỉnh `out`.

Nếu coi mỗi thao tác stack có chi phí hằng số, tổng chi phí lần gọi đó là **Θ(k)**. Vì vậy **trường hợp xấu nhất của một lần dequeue/peek không phải O(1)**.

Tuy nhiên, hãy theo dõi **mỗi phần tử**:

1. Được `push` vào `in` đúng một lần khi enqueue.
2. Khi cần chuyển, bị `pop` khỏi `in` **tối đa một lần**.
3. Được `push` vào `out` **tối đa một lần**.
4. Cuối cùng bị `pop` khỏi `out` tối đa một lần khi dequeue.

Một phần tử **không bao giờ được chuyển ngược từ `out` sang `in`**. Do vậy một phần tử không thể phải gánh cùng chi phí chuyển nhiều lần.

### 8.1. Phân tích tổng (aggregate analysis)

Giả sử có `m` lời gọi thành công tới `enqueue`, `dequeue` và `peek`, trong đó có `e` lần enqueue, `d` lần dequeue và `p` lần peek, `m = e + d + p`.

| Nhóm thao tác stack bên trong | Tổng số tối đa |
|---|---:|
| `push` vào `in` khi enqueue | `e` |
| `pop` khỏi `in` khi chuyển | `e` |
| `push` vào `out` khi chuyển | `e` |
| `pop` khỏi `out` khi dequeue | `d ≤ e` |
| Đọc đỉnh `out` khi peek | `p` |

Mỗi lời gọi còn có số lần kiểm tra rỗng/hằng số. Vì thế tổng số phép toán cơ bản qua toàn bộ chuỗi được chặn bởi:

```text
O(e + e + e + d + p)
= O(e + d + p)
= O(m)
```

Ở đây `d ≤ e` nếu bắt đầu từ queue rỗng và chỉ tính các dequeue thành công; kể cả khi không cần dùng bất đẳng thức đó, `e + d + p = m` vẫn đủ cho cận trên.

Kết luận: **m lời gọi có tổng thời gian O(m)**, nên chi phí khấu hao của một lời gọi là **O(1)**. Một lần chuyển dài được “trả tiền” bởi các lần enqueue trước đó, vốn đã đặt những phần tử vào `in`.

### 8.2. Phân tích bằng hàm thế năng

Một cách chứng minh chính xác hơn là phương pháp **thế năng** (*potential method*). Ta đo chi phí thực bằng số thao tác stack, và đặt:

```text
Φ = 2 × |in|
```

Ở đây `|in|` là số phần tử hiện có trong stack `in`. Thế năng **không âm**, ban đầu bằng `0`. Chi phí khấu hao của một lời gọi được định nghĩa:

```text
amortized_cost = actual_cost + Φ_after - Φ_before
```

Phân tích từng trường hợp:

| Trường hợp | Chi phí thực (đơn vị thao tác stack/đọc đỉnh) | Thay đổi thế năng | Chi phí khấu hao |
|---|---:|---:|---:|
| `enqueue(x)` | 1 lần `push` vào `in` | `+2` | **3** |
| `dequeue()` khi `out` không rỗng | 1 lần `pop` | `0` | **1** |
| `peek()` khi `out` không rỗng | 1 lần đọc đỉnh | `0` | **1** |
| `dequeue()` khi phải chuyển `k` phần tử | `2k + 1` | `−2k` | **1** |
| `peek()` khi phải chuyển `k` phần tử | `2k + 1` | `−2k` | **1** |

Các phép kiểm tra rỗng tốn thêm một số bước hằng số, nên không ảnh hưởng kết luận tiệm cận. Khi chuyển `k` phần tử, phần “tiền dự trữ” `2k` trong `Φ` bù đúng `2k` phép `pop + push`. Bởi vậy, **mỗi thao tác có chi phí khấu hao không quá một hằng số**, dù chi phí thực của vài thao tác rất lớn.

Cộng chi phí khấu hao qua một chuỗi `m` thao tác:

```text
Σ amortized_cost
= Σ actual_cost + Φ_final - Φ_initial
```

Vì `Φ_initial = 0` và `Φ_final ≥ 0`:

```text
Σ actual_cost ≤ Σ amortized_cost = O(m)
```

Đây là một **bảo đảm toán học cho tổng chuỗi thao tác**, không phải nói rằng mọi lần dequeue đều hoàn tất trong một thời gian cố định.

## 9. Phân tích chi phí theo từng phép toán

| Phép toán | Trường hợp xấu nhất của một lần gọi | Khấu hao trên chuỗi thao tác | Bộ nhớ phụ của lần gọi |
|---|---:|---:|---:|
| `enqueue(x)` | O(1) trong mô hình stack chuẩn | **O(1)** | O(1), ngoài chỗ lưu `x` |
| `dequeue()` | **O(n)** nếu phải chuyển `n` phần tử | **O(1)** | O(1) tham chiếu tạm |
| `peek()` | **O(n)** nếu phải chuyển `n` phần tử | **O(1)** | O(1) tham chiếu tạm |
| `is_empty()` | O(1) | O(1) | O(1) |
| `len()` | O(1) nếu hai stack lưu độ dài | O(1) | O(1) |

**Bộ nhớ lưu trữ là O(n)** cho `n` phần tử đang chờ: mỗi phần tử hiện diện trong **chính xác một trong hai stack** ở thời điểm thao tác công khai hoàn tất. Không tạo ra bản sao phần tử khi chuyển; chỉ chuyển tham chiếu hoặc giá trị giữa hai stack. Bộ nhớ tạm ngoài hai stack là O(1) trong giả mã tuần tự.

Nếu dùng `list` động của Python, phần dung lượng đã cấp phát của mỗi stack có thể lớn hơn số phần tử hiện tại theo chính sách cấp phát của thư viện. Cận O(n) thường được hiểu theo số phần tử đang lưu (hoặc dung lượng đã cấp phát tỷ lệ với kích thước trong mô hình mảng động); chi tiết bộ nhớ đỉnh phụ thuộc runtime.

**Phân biệt với O(1) trường hợp xấu nhất:** nếu hệ thống đòi hỏi mỗi lần `dequeue` phải hoàn thành trong một giới hạn bước rất nhỏ, ví dụ xử lý có hạn chót nghiêm ngặt, một lần chuyển `n` phần tử có thể gây độ trễ không mong muốn. Trong trường hợp này, **mảng vòng sức chứa cố định** hoặc một thiết kế queue có bảo đảm chặt hơn có thể phù hợp hơn.

## 10. So sánh với các cách hiện thực queue khác

| Cách hiện thực | `enqueue` | `dequeue` | Bộ nhớ | Điểm cần chú ý |
|---|---|---|---|---|
| **Hai stack với chuyển dồn khi `out` rỗng** | O(1) | **O(1) khấu hao**, xấu nhất O(n) | O(n) | Dễ xây dựng từ ADT stack; đôi lúc chuyển nhiều phần tử |
| Mảng đặc với `pop(0)` | O(1) khấu hao nếu mảng động | O(n) mỗi lần xóa đầu | O(n) | Phải dịch các phần tử còn lại |
| Mảng vòng sức chứa cố định | O(1) | **O(1) trường hợp xấu nhất** | O(C) | Phải xử lý khi đầy; `C` là sức chứa |
| Mảng vòng tự mở rộng | O(1) khấu hao | O(1) | O(C) | Enqueue có thể O(n) khi cần cấp phát/sao chép |
| Danh sách liên kết đơn có `head` và `tail` | O(1) | O(1) | O(n) | Cấp phát thêm nút và lưu tham chiếu |
| `collections.deque` trong Python | O(1) cho thêm cuối | O(1) cho lấy đầu | O(n) | API có sẵn: `append` và `popleft` |

Với bảng này, thời gian được xét theo mô hình thao tác cơ bản thường dùng trong phân tích cấu trúc dữ liệu; chi phí cấp phát thực tế có thể thay đổi theo ngôn ngữ và môi trường. `C` là số ô đã cấp phát, `n` là số phần tử đang chờ.

### Vì sao học cách cài đặt bằng hai stack?

Cách này hữu ích khi một thư viện hoặc giao diện hệ thống **chỉ cung cấp stack**, nhưng bài toán cần queue. Nó cũng minh họa rõ sự khác biệt giữa **độ phức tạp trường hợp xấu nhất** và **độ phức tạp khấu hao**, một kỹ năng có ích khi học mảng động, bảng băm và các cấu trúc dữ liệu khác.

Trong Python thực tế, nếu không bị ràng buộc phải dùng hai stack, `collections.deque` thường là giải pháp trực tiếp hơn:

```python
from collections import deque

q = deque()
q.append("A")
q.append("B")

assert q.popleft() == "A"
assert q.popleft() == "B"
```

Tuy nhiên, chính khả năng dùng một cấu trúc để **xây dựng ADT khác** là điểm học thuật quan trọng của ví dụ hai stack.

## 11. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Lấy trực tiếp bằng `in.pop()` | Trở thành stack LIFO, phần tử mới nhất ra trước | Lấy từ `out`; chuyển từ `in` sang `out` khi cần |
| Chuyển mỗi khi enqueue | Phần tử mới có thể đứng trước phần tử cũ trong `out` | Mọi enqueue chỉ `push` vào `in` |
| Chuyển `in` sang `out` dù `out` đang có dữ liệu | Đảo sai thứ tự giữa phần tử cũ và mới | **Chỉ chuyển khi `out` rỗng** |
| Chuyển một phần `in` rồi dừng sớm | Phần tử cũ hơn vẫn nằm trong `in` và có thể bị phục vụ muộn | Khi bắt đầu chuyển, **chuyển hết `in`** |
| Dùng `peek` bằng cách `dequeue` rồi enqueue lại | Làm thay đổi thứ tự hoặc tăng chi phí | Chuẩn bị `out` rồi chỉ đọc đỉnh `out` |
| Nghĩ `peek` không bao giờ thay đổi lưu trữ bên trong | Bỏ qua khả năng chuyển O(n) trong một lần xem | Phân biệt bất biến ADT với trạng thái hai stack |
| Xem O(1) khấu hao là O(1) cho từng lần gọi | Đánh giá thấp độ trễ lúc chuyển nhiều phần tử | Phân tích riêng trường hợp xấu nhất O(n) |
| Quên kiểm tra cả hai stack khi xác định rỗng | Báo sai nếu `in` có phần tử nhưng `out` rỗng | Rỗng khi **cả `in` và `out` đều rỗng** |
| Dùng `None` làm tín hiệu queue rỗng | Nhầm với `None` được enqueue hợp lệ | Báo lỗi hoặc dùng kiểu kết quả tách biệt |
| Thiếu đồng bộ khi nhiều luồng cùng thao tác | Có thể mất dữ liệu hoặc sai thứ tự bởi các bước xen kẽ | Dùng queue đồng bộ hoặc cơ chế khóa thích hợp |

**Đừng chuyển ngược từ `out` sang `in`** sau mỗi lần lấy. Việc chuyển một chiều từ `in` sang `out` chính là lý do mỗi phần tử chỉ phát sinh một lần di chuyển và tổng chi phí được chặn tuyến tính.

### Chú ý khi dùng giữa nhiều luồng

Mã `TwoStackQueue` chỉ là cài đặt **tuần tự**. Việc kiểm tra rỗng rồi chuyển nhiều phần tử gồm nhiều bước, nên không tự an toàn nếu nhiều producer/consumer truy cập cùng lúc. Khi cần hàng đợi dùng giữa các luồng trong Python, có thể dùng `queue.Queue` với các thao tác `put`/`get` và cơ chế đồng bộ/chờ do thư viện cung cấp.

Nếu cần giới hạn sức chứa, bản cài bằng hai stack cũng phải bổ sung kiểm tra `len(in) + len(out)` so với sức chứa, cùng chính sách từ chối hoặc chờ rõ ràng. **Chi phí khấu hao không tự giải quyết vấn đề quá tải hoặc đồng thời.**

## 12. Tự luyện và lời giải

**Bài 1 — Truy vết FIFO.** Thực hiện `enqueue(1)`, `enqueue(2)`, `enqueue(3)`, `dequeue()`, `enqueue(4)`, `dequeue()`, `dequeue()`. Ba giá trị trả về là gì?

*Lời giải:* Lần đầu dequeue chuyển `[1, 2, 3]` từ `in` sang `out = [3, 2, 1]`, trả `1`. Sau khi enqueue `4` vào `in`, những lần lấy kế tiếp vẫn trả `2` rồi `3`. Kết quả **`1, 2, 3`**, queue còn `[4]`.

**Bài 2 — Bất biến.** Cho `in = [D, E]` và `out = [C, B]`, cả hai viết từ đáy lên đỉnh. Thứ tự dequeue dự kiến là gì?

*Lời giải:* `reverse(out) + in = [B, C] + [D, E] = [B, C, D, E]`. Hai lần lấy đầu trả `B`, `C` trước khi chuyển `D, E`.

**Bài 3 — Peek.** Ban đầu `in = [A, B, C, D]`, `out = []`. Gọi `peek()` một lần. Kết quả trả về và hai stack sau đó là gì? Queue logic có đổi không?

*Lời giải:* `peek()` chuyển hết `in` thành `out = [D, C, B, A]`, rồi trả `A`. `in = []`; dãy queue logic vẫn `[A, B, C, D]`.

**Bài 4 — Độ phức tạp một lần gọi.** Có 100.000 phần tử trong `in`, `out` rỗng. Một lần `dequeue` tiếp theo có thể mất O(1) thời gian trường hợp xấu nhất không?

*Lời giải:* **Không.** Phải thực hiện khoảng 100.000 lượt chuyển, mỗi lượt gồm `pop` và `push`, nên riêng lần gọi này có **Θ(n)** chi phí. Qua nhiều thao tác, mỗi phần tử vẫn chỉ chuyển tối đa một lần nên đạt O(1) **khấu hao**.

**Bài 5 — Tổng số lần chuyển.** Với `n` phần tử từng được enqueue và sau đó dequeue hết, mỗi phần tử có thể bị chuyển từ `in` sang `out` bao nhiêu lần?

*Lời giải:* **Tối đa một lần**. Mỗi phần tử bị `pop` khỏi `in` một lần và `push` vào `out` một lần, tổng O(n) phép chuyển cho toàn bộ `n` phần tử.

**Bài 6 — Hàm thế năng.** Vì sao chọn `Φ = 2|in|` giúp giải thích một lần chuyển `k` phần tử?

*Lời giải:* Chi phí thực chuyển là `2k` thao tác stack, còn `|in|` giảm `k` nên `Φ` giảm `2k`. Phần giảm thế năng bù chi phí chuyển, giữ chi phí khấu hao O(1).

**Bài 7 — Lựa chọn thiết kế.** Một hệ thống phải đảm bảo mỗi lần lấy phần tử mất số bước rất nhỏ ngay cả khi hàng chứa hàng triệu phần tử. Queue hai stack chuyển dồn có phải lựa chọn lý tưởng không?

*Lời giải:* **Không nhất thiết.** Lần dequeue đầu tiên khi `out` rỗng có thể phải chuyển hàng triệu phần tử. Một **mảng vòng sức chứa cố định** hoặc queue với bảo đảm thời gian trường hợp xấu nhất chặt hơn phù hợp để đáp ứng yêu cầu độ trễ từng thao tác.

**Ghi nhớ:** Hàng đợi hai stack duy trì bất biến **`Q = reverse(out) + in`**. `enqueue` luôn thêm vào `in`; `dequeue`/`peek` lấy từ `out` và **chỉ chuyển toàn bộ `in` khi `out` rỗng**. Mỗi phần tử chỉ chuyển một lần, nên dù một lần lấy/xem có thể tốn O(n), **tổng thời gian của m thao tác là O(m)** và chi phí **O(1) khấu hao mỗi thao tác**, với bộ nhớ **O(n)**.
