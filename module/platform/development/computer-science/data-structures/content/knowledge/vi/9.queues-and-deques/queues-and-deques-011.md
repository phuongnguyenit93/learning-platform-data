# Cài đặt ngăn xếp bằng hàng đợi và đánh đổi phép toán

**Ngăn xếp (stack)** tuân theo quy tắc **LIFO** (*Last In, First Out*): phần tử được thêm sau cùng sẽ được lấy ra trước. Ngược lại, **hàng đợi (queue)** tuân theo **FIFO** (*First In, First Out*): phần tử được thêm trước sẽ được lấy ra trước. Khi chỉ được dùng các thao tác của queue, liệu có thể hiện thực stack không?

**Có.** Ta có thể dùng một hoặc hai hàng đợi và chủ động **đảo thứ tự phục vụ bằng cách chuyển hoặc quay vòng phần tử**. Điểm đáng học là phải chọn *lúc nào trả chi phí*:

- **Ưu tiên lấy nhanh:** mỗi lần `push` sắp lại thứ tự, có thể mất **O(n)**; `pop` và `top` sau đó **O(1)**.
- **Ưu tiên thêm nhanh:** `push` chỉ thêm cuối queue **O(1)**; mỗi lần `pop` hoặc `top` có thể phải chuyển **O(n)** phần tử.

Bài thuộc chương **Hàng đợi và deque** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, nơi người học xây dựng nền tảng từ mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị. Bài nhấn mạnh **bất biến**, **hợp đồng phép toán**, **chi phí thời gian/bộ nhớ**, và cách lựa chọn cấu trúc dữ liệu phù hợp. Đặc biệt, hãy phân biệt phép đổi chỗ tốn O(n) ở mỗi lần gọi với khái niệm **khấu hao**: những cách hiện thực đơn giản dưới đây **không mặc nhiên có O(1) khấu hao cho cả push lẫn pop**.

## 1. Ràng buộc bài toán: chỉ dùng giao diện hàng đợi

### Stack cần cung cấp những gì?

Gọi stack logic được viết từ **đáy đến đỉnh** là `S = [A, B, C]`. Khi đó:

| Phép stack | Ý nghĩa | Ví dụ với `S = [A, B, C]` |
|---|---|---|
| `push(X)` | Thêm `X` lên đỉnh | `[A, B, C, X]` |
| `pop()` | Lấy và bỏ phần tử đỉnh | Trả `C`, còn `[A, B]` |
| `top()` / `peek()` | Xem đỉnh nhưng không xóa | Trả `C`, giữ `[A, B, C]` |
| `is_empty()` | Kiểm tra rỗng | `False` |
| `size()` | Đếm số phần tử | `3` |

**Bất biến LIFO:** khi các phần tử chưa bị lấy ra, phần tử `push` gần nhất phải nằm trên mọi phần tử được `push` trước đó. Không được lấy phần tử đáy khi vẫn còn phần tử nằm trên nó.

### Queue cho phép những gì?

Để đánh giá đúng bài toán, giả định mỗi queue chỉ hỗ trợ:

- `enqueue(x)`: thêm `x` vào **cuối**.
- `dequeue()`: lấy và xóa phần tử ở **đầu**.
- `front()`: xem phần tử đầu mà không xóa.
- `is_empty()` và `size()`: truy vấn trạng thái.

Việc `enqueue/dequeue` tốn O(1) được giả định theo **queue ADT đã được cài đặt hiệu quả**, ví dụ mảng vòng hoặc `collections.deque` với `append` và `popleft`. Nếu underlying queue vốn dùng `list.pop(0)` và phải dịch mảng, độ phức tạp toàn bộ giải pháp sẽ thay đổi.

**Không được dùng `pop_back()` hay `appendleft()` để “lách” yêu cầu:** các thao tác ấy thuộc về **deque**, không phải queue FIFO thông thường. Nếu được lấy trực tiếp ở cuối, ta đã có thể dùng deque làm stack mà không cần thuật toán chuyển phần tử.

## 2. Ý tưởng cốt lõi: quay vòng các phần tử

Queue được biểu diễn từ **đầu (front)** sang **cuối (rear)**:

```text
front                           rear
  |                               |
  v                               v
 [ A ] ──→ [ B ] ──→ [ C ]

dequeue() trả A
enqueue(X) tạo [A, B, C, X]
```

Ta có thể **đưa phần tử ở đầu xuống cuối** bằng hai thao tác queue hợp lệ:

```text
enqueue(dequeue())
```

Ví dụ:

```text
[A, B, C]  --lấy A rồi thêm lại-->  [B, C, A]
[B, C, A]  --lấy B rồi thêm lại-->  [C, A, B]
[C, A, B]  --lấy C rồi thêm lại-->  [A, B, C]
```

Đây là phép **quay vòng một bước**. Thực hiện `k` lần quay tạo phép quay `k` vị trí mà không truy cập ngẫu nhiên, không đổi tổng số phần tử và không phá trật tự tương đối theo vòng.

Từ thao tác đơn giản này, ta có **hai phương án một queue** với hai cách tổ chức bất biến khác nhau.

## 3. Phương án A: `push` tốn O(n), `pop` nhanh O(1)

### 3.1. Bất biến: đỉnh stack luôn ở đầu queue

Giữ queue `q` theo thứ tự **từ đỉnh stack xuống đáy stack**.

Ví dụ stack logic từ đáy lên đỉnh là `[A, B, C]`, thì queue phải là:

```text
Stack logic (đáy → đỉnh): [A, B, C]

Queue vật lý (front → rear):
front                      rear
  |                          |
  v                          v
 [C] ──→ [B] ──→ [A]
  ↑
đỉnh stack, sẵn sàng dequeue()
```

Khi đó:

- `pop()` chỉ cần `dequeue()` ở đầu: **O(1)**.
- `top()` chỉ cần `front()`: **O(1)**.
- Nhưng `push(x)` phải đưa phần tử `x` **lên đầu queue**, trong khi queue chỉ được thêm ở cuối.

Ta thực hiện việc này bằng cách thêm `x` vào cuối rồi quay **đúng số phần tử cũ**.

### 3.2. Thuật toán push

Giả sử trước khi thêm có `n` phần tử:

```text
PUSH(x):
    n = q.size()
    q.enqueue(x)

    repeat n times:
        q.enqueue(q.dequeue())
```

Sau khi thêm `x`, queue tạm thời chứa `[top, …, bottom, x]`. Quay `n` lần sẽ chuyển toàn bộ `n` phần tử cũ xuống phía sau `x`, biến `x` thành phần tử đầu.

Ví dụ:

```text
Trước push(D), queue đang là [C, B, A] (C là đỉnh).

1. enqueue(D)             [C, B, A, D]
2. chuyển C xuống cuối    [B, A, D, C]
3. chuyển B xuống cuối    [A, D, C, B]
4. chuyển A xuống cuối    [D, C, B, A]

Sau push(D):
front -> [D, C, B, A] -> rear
          ↑
       đỉnh mới
```

**Chi phí:** một lần `enqueue(x)` cộng `n` lần `dequeue` và `n` lần `enqueue`. Theo mô hình queue cơ bản O(1), `push` tốn **Θ(n + 1)**; `pop` và `top` tốn **Θ(1)** khi không rỗng.

### 3.3. Giả mã pop, top và rỗng

```text
POP():
    if q.is_empty():
        báo lỗi stack rỗng
    return q.dequeue()

TOP():
    if q.is_empty():
        báo lỗi stack rỗng
    return q.front()

IS_EMPTY():
    return q.is_empty()
```

Vì bất biến bảo đảm **đầu queue chính là đỉnh stack**, các phép này không cần quay hay chuyển phần tử.

### 3.4. Truy vết

Viết queue từ **đầu đến cuối**, stack logic từ **đáy đến đỉnh**:

| Bước | Phép stack | Queue sau thao tác | Stack logic | Kết quả |
|---:|---|---|---|---|
| 0 | Khởi tạo | `[]` | `[]` | — |
| 1 | `push(A)` | `[A]` | `[A]` | — |
| 2 | `push(B)` | `[B, A]` | `[A, B]` | — |
| 3 | `push(C)` | `[C, B, A]` | `[A, B, C]` | — |
| 4 | `top()` | `[C, B, A]` | `[A, B, C]` | `C` |
| 5 | `pop()` | `[B, A]` | `[A, B]` | `C` |
| 6 | `push(D)` | `[D, B, A]` | `[A, B, D]` | — |
| 7 | `pop()` | `[B, A]` | `[A, B]` | `D` |
| 8 | `pop()` | `[A]` | `[A]` | `B` |
| 9 | `pop()` | `[]` | `[]` | `A` |

Ở bước 3, ba lần `push` phải xoay queue lần lượt 0, 1 và 2 bước. Ở bước 5, ta chỉ lấy ngay phần tử đầu `C`. Các kết quả pop là `C, D, B, A`, đúng với thứ tự push xen kẽ.

## 4. Mã Python: một queue, ưu tiên pop nhanh

Dùng `collections.deque` làm **bộ nhớ hiện thực queue FIFO**, nhưng **chỉ thao tác qua `append` (thêm cuối), `popleft` (lấy đầu), `d[0]` (xem đầu) và `len`**.

```python
from collections import deque


class StackWithCostlyPush:
    """Stack dùng một queue: push O(n), pop/top O(1)."""

    def __init__(self):
        self._q = deque()

    def __len__(self):
        return len(self._q)

    def is_empty(self):
        return not self._q

    def push(self, value):
        old_size = len(self._q)
        self._q.append(value)

        # Đưa tất cả phần tử cũ xuống sau phần tử mới.
        for _ in range(old_size):
            self._q.append(self._q.popleft())

    def pop(self):
        if self.is_empty():
            raise IndexError("Không thể pop từ stack rỗng")
        return self._q.popleft()

    def top(self):
        if self.is_empty():
            raise IndexError("Không thể top từ stack rỗng")
        return self._q[0]


s = StackWithCostlyPush()
s.push("A")
s.push("B")
s.push("C")

assert len(s) == 3
assert s.top() == "C"
assert s.pop() == "C"

s.push("D")
assert [s.pop(), s.pop(), s.pop()] == ["D", "B", "A"]
assert s.is_empty()
```

Hàm `top` chỉ **xem phần tử đầu**, một thao tác hợp lệ của queue. Tuy ví dụ đọc trực tiếp `_q[0]` để biểu đạt `front()` của `deque` Python, cấu trúc trừu tượng vẫn không dùng phép lấy từ cuối.

**Kiểm tra với một phần tử:** khi `old_size = 0`, vòng quay chạy 0 lần. Queue nhận `x` đúng một lần; `top` và `pop` đều trả `x`.

## 5. Phương án B: `push` nhanh O(1), `pop` tốn O(n)

### 5.1. Bất biến: đỉnh stack luôn ở cuối queue

Ta giữ queue theo **thứ tự push từ cũ tới mới**, tức từ **đáy stack đến đỉnh stack**:

```text
Stack logic (đáy → đỉnh): [A, B, C]

Queue vật lý (front → rear):
front                      rear
  |                          |
  v                          v
 [A] ──→ [B] ──→ [C]
                         ↑
                      đỉnh stack
```

Vì phần tử mới cần nằm ở đỉnh, `push(x)` chỉ cần:

```text
PUSH(x):
    q.enqueue(x)
```

Đây là **O(1)** theo mô hình queue cơ bản. Nhưng giờ đỉnh stack nằm ở **cuối queue**, không phải đầu. Để lấy nó mà chỉ dùng FIFO, ta phải đưa các phần tử cũ lần lượt từ đầu xuống cuối, rồi mới lấy phần tử mới nhất.

### 5.2. Thuật toán pop bằng quay n − 1 lần

Giả sử queue chứa `n > 0` phần tử:

```text
POP():
    if q.is_empty():
        báo lỗi stack rỗng

    repeat q.size() - 1 times:
        q.enqueue(q.dequeue())

    return q.dequeue()
```

Với `q = [A, B, C, D]`:

```text
Ban đầu:                 [A, B, C, D]
Quay 1:                  [B, C, D, A]
Quay 2:                  [C, D, A, B]
Quay 3:                  [D, A, B, C]
Lấy đầu: trả D, còn       [A, B, C]
```

Sau khi pop, các phần tử chưa bị lấy **trở về thứ tự cũ** `[A, B, C]`. Điều đó duy trì bất biến “đáy đến đỉnh” cho lần push/pop tiếp theo.

- `push(x)`: **Θ(1)**.
- `pop()` khi có `n` phần tử: **Θ(n)** do cần `n − 1` lần quay, ngoài một lần lấy.
- `is_empty()` và `size()`: **Θ(1)**.

### 5.3. Top không xóa: phải khôi phục đúng thứ tự

Nếu chỉ được dùng queue ADT **không hỗ trợ đọc cuối**, `top()` cũng cần O(n). Cách làm là quay `n − 1` lần để đỉnh đến đầu, lấy nó ra, rồi thêm lại **vào cuối**:

```text
TOP():
    if q.is_empty():
        báo lỗi stack rỗng

    repeat q.size() - 1 times:
        q.enqueue(q.dequeue())

    value = q.dequeue()
    q.enqueue(value)         # Khôi phục thứ tự queue ban đầu.
    return value
```

Ví dụ:

```text
Trước top:             [A, B, C]
Quay hai lần:          [C, A, B]
Lấy C rồi thêm lại:    [A, B, C]
Trả C, queue không đổi thứ tự và độ dài.
```

**Đừng nhầm `q[-1]` của Python với phép `front` của queue.** Nếu được phép truy cập trực tiếp phần tử cuối của `collections.deque`, việc xem top sẽ là O(1); nhưng đó là **giao diện phong phú hơn queue ADT đã quy định**. Trong phần này ta cố ý không dùng truy cập cuối để bảo toàn ràng buộc “chỉ dùng thao tác FIFO”.

### 5.4. Truy vết

| Bước | Phép stack | Queue sau thao tác | Stack logic | Giá trị trả về |
|---:|---|---|---|---|
| 0 | Khởi tạo | `[]` | `[]` | — |
| 1 | `push(A)` | `[A]` | `[A]` | — |
| 2 | `push(B)` | `[A, B]` | `[A, B]` | — |
| 3 | `push(C)` | `[A, B, C]` | `[A, B, C]` | — |
| 4 | `top()` | `[A, B, C]` | `[A, B, C]` | `C` |
| 5 | `pop()` | `[A, B]` | `[A, B]` | `C` |
| 6 | `push(D)` | `[A, B, D]` | `[A, B, D]` | — |
| 7 | `pop()` | `[A, B]` | `[A, B]` | `D` |
| 8 | `pop()` | `[A]` | `[A]` | `B` |
| 9 | `pop()` | `[]` | `[]` | `A` |

Cùng một tập lời gọi cho ra cùng kết quả stack như phương án A, nhưng **phần tử mới nhất được chuyển ra đầu khi lấy**, thay vì chuyển ra đầu ngay lúc thêm.

## 6. Mã Python: một queue, ưu tiên push nhanh

```python
from collections import deque


class StackWithCostlyPop:
    """Stack dùng một queue: push O(1), pop/top O(n)."""

    def __init__(self):
        self._q = deque()

    def __len__(self):
        return len(self._q)

    def is_empty(self):
        return not self._q

    def push(self, value):
        self._q.append(value)

    def _rotate_to_latest(self):
        if not self._q:
            raise IndexError("Stack rỗng")
        for _ in range(len(self._q) - 1):
            self._q.append(self._q.popleft())

    def pop(self):
        self._rotate_to_latest()
        return self._q.popleft()

    def top(self):
        self._rotate_to_latest()
        result = self._q.popleft()
        self._q.append(result)  # Trả phần tử về cuối để giữ nguyên stack.
        return result


s = StackWithCostlyPop()
for value in ["A", "B", "C"]:
    s.push(value)

assert s.top() == "C"
assert len(s) == 3
assert s.top() == "C"  # Gọi top nhiều lần vẫn không đổi thứ tự.

assert s.pop() == "C"
s.push("D")
assert [s.pop(), s.pop(), s.pop()] == ["D", "B", "A"]
assert s.is_empty()
```

Đây là cài đặt **dùng tuần tự**, không có đồng bộ khi nhiều luồng cùng sửa cấu trúc. Về API, `top()` không lấy phần tử khỏi stack; nhưng nội bộ nó thực hiện một số lần dequeue/enqueue trước khi khôi phục trạng thái cũ.

## 7. Dùng hai queue thay vì một queue

Bài toán cũng có thể dùng **hai hàng đợi**, thường gọi `main` và `helper`. Tùy lựa chọn, ta thực hiện việc chuyển phần tử khi push hoặc khi pop.

### 7.1. Hai queue, push tốn O(n)

Giữ `main` với **đỉnh stack ở đầu**:

1. Đưa phần tử mới `x` vào queue trống `helper`.
2. Lấy lần lượt mọi phần tử cũ từ `main`, thêm vào `helper`.
3. Hoán đổi vai trò hai queue; `main` mới có `x` ở đầu.

```text
PUSH(x):
    helper.enqueue(x)

    while main không rỗng:
        helper.enqueue(main.dequeue())

    swap(main, helper)

POP():
    if main rỗng: báo lỗi
    return main.dequeue()
```

Ví dụ `main = [C, B, A]`, `helper = []`:

```text
helper nhận D:            [D]
chuyển C, B, A:           [D, C, B, A]
sau khi đổi vai:
main = [D, C, B, A],      helper = []
```

**Mỗi push có O(n)** với `n` phần tử cũ; **pop/top O(1)**. Đổi hai tham chiếu queue là O(1), không cần sao chép cấu trúc trong bước swap.

### 7.2. Hai queue, pop tốn O(n)

Giữ `main` theo thứ tự **đáy đến đỉnh**, đỉnh ở cuối:

1. `push(x)`: `main.enqueue(x)`.
2. Khi `pop`, chuyển **mọi phần tử trừ phần tử cuối** từ `main` sang `helper`.
3. Lấy phần tử cuối còn lại ở `main` (bây giờ nằm tại đầu).
4. Đổi vai `main` và `helper`; queue mới giữ đúng thứ tự các phần tử còn lại.

```text
POP():
    if main rỗng: báo lỗi

    while main.size() > 1:
        helper.enqueue(main.dequeue())

    result = main.dequeue()
    swap(main, helper)
    return result
```

Với `main = [A, B, C]`, ta chuyển `A` rồi `B` sang helper, lấy `C`, cuối cùng `main = [A, B]`. Như vậy **push O(1), pop O(n)**.

Muốn `top` **không làm thay đổi dãy logic**, có thể chuyển tất cả trừ phần tử cuối, lấy giá trị cuối và thêm nó vào cuối `helper`, rồi đổi vai. Cách ấy cũng tốn O(n) theo giao diện queue cơ bản.

### 7.3. Ví dụ Python với hai queue và push tốn kém

```python
from collections import deque


class StackWithTwoQueues:
    """Hai queue: push O(n), pop/top O(1)."""

    def __init__(self):
        self._main = deque()
        self._helper = deque()

    def __len__(self):
        return len(self._main)

    def push(self, value):
        self._helper.append(value)

        while self._main:
            self._helper.append(self._main.popleft())

        self._main, self._helper = self._helper, self._main

    def pop(self):
        if not self._main:
            raise IndexError("Stack rỗng")
        return self._main.popleft()

    def top(self):
        if not self._main:
            raise IndexError("Stack rỗng")
        return self._main[0]


s = StackWithTwoQueues()
for x in [10, 20, 30]:
    s.push(x)

assert s.top() == 30
assert [s.pop(), s.pop(), s.pop()] == [30, 20, 10]
assert len(s) == 0
s.push(40)
assert s.pop() == 40
```

`helper` ở trạng thái rỗng sau mỗi lần `push` hoàn chỉnh vì các phần tử cũ đã được chuyển hết khỏi `main` trước khi hoán đổi vai. Đây là điều kiện cần duy trì cho lần thêm tiếp theo. Cài đặt hai queue dùng **O(n)** bộ nhớ chứa dữ liệu (phân bố giữa các queue trong lúc thao tác); không nhân bản đối tượng phần tử.

## 8. Bảng so sánh các phương án

Với `n` là số phần tử hiện có **trước** lời gọi và giả định mỗi thao tác queue cơ bản tốn O(1):

| Cách hiện thực stack | `push(x)` | `pop()` | `top()` | Trật tự queue chính |
|---|---:|---:|---:|---|
| **Một queue, ưu tiên pop** | **Θ(n + 1)** | **Θ(1)** | **Θ(1)** | Đỉnh nằm ở **đầu** |
| **Một queue, ưu tiên push** | **Θ(1)** | **Θ(n)** | **Θ(n)** | Đỉnh nằm ở **cuối** |
| **Hai queue, ưu tiên pop** | **Θ(n + 1)** | **Θ(1)** | **Θ(1)** | `main` có đỉnh ở đầu |
| **Hai queue, ưu tiên push** | **Θ(1)** | **Θ(n)** | **Θ(n)** theo giao diện queue cơ bản | `main` có đỉnh ở cuối |

Bộ nhớ chứa dữ liệu trong cả bốn cách là **O(n)**. Một queue thường đơn giản hơn về số cấu trúc cần lưu; hai queue có thể dễ diễn giải bằng thao tác chuyển riêng rẽ. Mục tiêu chọn thuật toán là quyết định **phép nào cần nhanh** theo mẫu truy cập của ứng dụng.

### Một số đánh đổi quan trọng

- Nếu `pop` và `top` rất thường xuyên, nhưng `push` hiếm, phương án **ưu tiên pop** có thể phù hợp.
- Nếu nhiều lần `push` xảy ra trước khi cần lấy, phương án **ưu tiên push** giảm chi phí của từng lần thêm; đổi lại lần lấy có thể phải quay/chuyển nhiều phần tử.
- Nếu yêu cầu **cả push và pop O(1) trong trường hợp xấu nhất**, một stack bình thường dùng mảng động hoặc danh sách liên kết sẽ trực tiếp hơn; việc xây từ queue chỉ để học cách biến đổi ADT và phân tích đánh đổi.
- Nếu ràng buộc là **chỉ được dùng queue FIFO**, không nên âm thầm dùng thao tác truy cập cuối của deque hoặc xóa ở cuối Python `list` trong lời giải.

## 9. Phân biệt chi phí từng phép với tổng của một chuỗi phép

Ở phương án **ưu tiên pop**, khi stack có `n` phần tử, `push(x)` phải quay `n` phần tử cũ. Hãy thực hiện **m lần push liên tiếp** từ stack rỗng:

```text
Push 1: quay 0 lần
Push 2: quay 1 lần
Push 3: quay 2 lần
...
Push m: quay m - 1 lần

Tổng số lần quay:
0 + 1 + 2 + ... + (m - 1)
= m(m - 1) / 2
= Θ(m²)
```

Vì vậy, tính trên chuỗi m lần push này, **chi phí trung bình mỗi push là Θ(m)**, không phải O(1) khấu hao.

Tương tự, ở phương án **ưu tiên push**, nếu push m phần tử rồi **pop m lần liên tiếp**, các lần pop phải quay `m - 1, m - 2, …, 0` bước. Tổng số lần quay cũng là:

```text
(m - 1) + (m - 2) + ... + 1 + 0
= m(m - 1) / 2
= Θ(m²)
```

Do đó, các cách cài đặt “quay hết queue” trong bài **không đạt O(1) khấu hao cho cả hai phép trên mọi chuỗi thao tác**.

### Vì sao khác với queue cài bằng hai stack?

Có một thuật toán nổi tiếng **queue từ hai stack** đạt `enqueue`/`dequeue` O(1) khấu hao vì **mỗi phần tử chuyển từ stack vào sang stack ra tối đa một lần**. Trong giải pháp **stack từ queue** kiểu quay đã trình bày, cùng một phần tử có thể bị quay/chuyển **lặp lại nhiều lần** qua những lần push hoặc pop khác nhau.

Ví dụ, phương án ưu tiên pop: khi push thêm phần tử mới, **mọi phần tử cũ** đều bị đưa từ đầu xuống cuối một lần. Nếu tiếp tục push, chúng lại bị quay thêm, nên không thể áp dụng lập luận “mỗi phần tử chỉ chuyển một lần” của queue hai stack.

Đó là lý do không nên kết luận đối xứng rằng **stack bằng hai queue cũng có O(1) khấu hao** chỉ vì **queue bằng hai stack** có tính chất ấy.

## 10. Chứng minh tính đúng đắn bằng bất biến

### 10.1. Phương án ưu tiên pop: đỉnh ở đầu

Định nghĩa `reverse(q)` là dãy `q` đọc từ cuối về đầu. Nếu queue `q` được ghi từ front đến rear và stack logic `S` từ đáy đến đỉnh, bất biến là:

```text
S = reverse(q)
```

**Cơ sở:** `q = []` và `S = []`, nên bất biến đúng.

**Khi push(x):** giả sử trước đó `q = [sₙ₋₁, …, s₁, s₀]`. Sau `enqueue(x)` rồi quay `n` phần tử cũ, `q_new = [x, sₙ₋₁, …, s₀]`. Vì thế `reverse(q_new) = [s₀, …, sₙ₋₁, x]`, đúng stack sau push.

**Khi pop():** phần tử đầu `q` là phần tử cuối `S` (đỉnh). `dequeue()` lấy đúng nó và dãy còn lại khớp stack sau pop. `top()` chỉ đọc đầu nên giữ nguyên bất biến.

### 10.2. Phương án ưu tiên push: đỉnh ở cuối

Bất biến đơn giản hơn:

```text
S = q
```

Trong đó cả hai dãy được ghi từ **đáy đến đỉnh** hoặc **front đến rear** tương ứng.

**Khi push(x):** thêm `x` vào cuối queue, nên `S_new = S + [x]`, đúng push của stack.

**Khi pop():** giả sử `q = [s₀, …, sₙ₋₂, sₙ₋₁]`. Quay `n - 1` lần đưa `sₙ₋₁` lên đầu, các phần tử còn lại trở thành `[s₀, …, sₙ₋₂]` ở phía sau theo đúng thứ tự. Sau `dequeue()`, giá trị trả về là `sₙ₋₁` và queue còn `[s₀, …, sₙ₋₂]`, trùng stack sau pop.

**Khi top():** cũng quay `n - 1` lần, lấy `sₙ₋₁` ra rồi thêm trở lại cuối, khiến queue khôi phục `[s₀, …, sₙ₋₁]`. Giá trị trả về đúng đỉnh, nội dung và thứ tự stack không đổi.

Theo quy nạp, cả hai phương án đều cho đúng LIFO trong mọi chuỗi thao tác hợp lệ.

## 11. Tình huống biên, tính an toàn và sai lầm thường gặp

### Rỗng, một phần tử và dữ liệu đặc biệt

- **Rỗng:** `pop` và `top` phải báo lỗi rõ ràng; không được cố dequeue một phần tử không tồn tại.
- **Một phần tử:** `push`/`pop` hoạt động dù số lần quay bằng 0; sau pop, queue rỗng.
- **Giá trị trùng nhau:** `push(5)` hai lần tạo hai phần tử riêng biệt; không được dùng giá trị để suy ra số phần tử.
- **Giá trị `None`:** nếu được phép thêm vào stack, `top` và `pop` phải trả `None` như dữ liệu hợp lệ, còn thao tác trên stack rỗng báo lỗi hoặc dùng kiểu kết quả khác.
- **Số phần tử lớn:** phiên bản pop tốn O(n) có thể gây độ trễ lớn ở một lời gọi khi queue chứa nhiều phần tử.

Có thể bổ sung những kiểm tra sau cho cả hai lớp Python:

```python
for stack_type in (StackWithCostlyPush, StackWithCostlyPop):
    s = stack_type()

    for operation in (s.top, s.pop):
        try:
            operation()
        except IndexError:
            pass
        else:
            raise AssertionError("Phải báo lỗi khi stack rỗng")

    s.push(None)
    s.push(None)
    s.push(7)

    assert s.top() == 7
    assert [s.pop(), s.pop(), s.pop()] == [7, None, None]
    assert s.is_empty()

    s.push("K")
    assert s.pop() == "K"
```

### Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `q.dequeue()` ngay sau `q.enqueue(x)` mà không sắp thứ tự | Được FIFO, không phải LIFO | Chọn bất biến đỉnh ở đầu hoặc ở cuối rồi tuân thủ |
| Phương án push tốn kém: quay `n + 1` lần thay vì `n` | Phần tử mới quay khỏi đầu, sai thứ tự stack | Đếm **số phần tử cũ** trước khi thêm |
| Phương án pop tốn kém: quay `n` lần thay vì `n − 1` | Phần tử cũ nhất lại trở về đầu | Quay đúng `size − 1` lần |
| `top` của phương án pop tốn kém lấy ra nhưng không thêm lại | Mất phần tử dù chỉ muốn xem | Sau khi lấy đỉnh để xem, thêm nó lại vào cuối |
| Khi dùng hai queue, quên đổi vai `main` và `helper` | Phần tử nằm ở queue phụ, thao tác sau trả sai | Swap hai tham chiếu sau khi chuyển xong |
| Dùng `deque.pop()` lấy cuối để “tối ưu” | Vượt khỏi ràng buộc queue FIFO | Chỉ dùng enqueue cuối, dequeue đầu, front, size |
| Không kiểm tra rỗng trước `top/pop` | Ngoại lệ không rõ nguồn hoặc thao tác sai | Định nghĩa hợp đồng rỗng tường minh |
| Nghĩ O(n) đôi khi thì O(1) khấu hao | Đánh giá sai tổng chi phí chuỗi thao tác | Đếm số lần quay trên cả chuỗi m phép |
| Dùng queue underlying có dequeue O(n) | Chi phí thuật toán lồng thêm chi phí dịch mảng | Chọn queue FIFO với các phép cơ bản O(1) |
| Nhiều luồng cùng thao tác mà không có đồng bộ | Thứ tự quay/chuyển bị xen kẽ, sai LIFO | Dùng cơ chế khóa hoặc cấu trúc đồng bộ phù hợp |

### Chọn giải pháp trong thực tế

Cài stack từ queue thường là **bài tập chuyển đổi ADT** hoặc một bài toán bị ràng buộc thư viện thao tác. Nếu không có ràng buộc “chỉ dùng queue”, một stack dùng mảng động hoặc danh sách liên kết thường đơn giản hơn và hỗ trợ `push/pop/top` hiệu quả. Trong Python, một `list` thường đã đủ để làm stack:

```python
stack = []
stack.append("A")   # push
stack.append("B")
assert stack[-1] == "B"   # top
assert stack.pop() == "B"
assert stack.pop() == "A"
```

Dùng `list` như stack là ví dụ **không thuộc** ràng buộc “chỉ dùng queue”; nó giúp thấy vì sao đôi khi nên chọn cấu trúc dữ liệu **phù hợp với thao tác cần thực hiện**, thay vì ép một ADT mô phỏng ADT khác.

## 12. Câu hỏi tự luyện và đáp án

**Bài 1 — Quay khi push.** Dùng phương án ưu tiên pop với queue `q = [C, B, A]`, tức `C` đang là đỉnh. Sau `push(D)`, queue phải là gì và cần bao nhiêu lần quay?

*Đáp án:* Thêm `D` vào cuối `[C, B, A, D]` rồi quay **3 lần**, được **`[D, C, B, A]`**. `pop()` tiếp theo trả `D`.

**Bài 2 — Quay khi pop.** Dùng phương án ưu tiên push với queue `q = [A, B, C, D]`. Để pop đúng đỉnh, cần quay bao nhiêu lần? Sau thao tác còn gì?

*Đáp án:* Quay **3 lần** để được `[D, A, B, C]`, rồi dequeue trả `D`. Queue còn **`[A, B, C]`**.

**Bài 3 — Top mà không xóa.** Với phương án ưu tiên push, queue `[4, 8, 15]`. Thực hiện `top()` chỉ dùng queue ADT sẽ trả giá trị nào và trạng thái cuối ra sao?

*Đáp án:* Quay hai lần thành `[15, 4, 8]`, lấy `15` rồi thêm lại cuối, được `[4, 8, 15]`. Kết quả **15**, queue không đổi về mặt nội dung/thứ tự.

**Bài 4 — Chọn phương án.** Một tác vụ chỉ thêm phần tử thỉnh thoảng nhưng kiểm tra `top()` rất nhiều lần. Trong các cài đặt một queue đã học, phương án nào thường phù hợp hơn?

*Đáp án:* **Ưu tiên pop**: `top()` O(1), còn `push` O(n). Cần cân nhắc cả tần suất push và số phần tử hiện hữu.

**Bài 5 — Đếm tổng phép quay.** Thực hiện `m = 5` lần push liên tiếp từ rỗng với phương án ưu tiên pop. Tổng số lần quay là bao nhiêu?

*Đáp án:* `0 + 1 + 2 + 3 + 4 = 10` lần. Với m tổng quát, số lần quay là `m(m − 1)/2 = Θ(m²)`.

**Bài 6 — Hai queue.** `main = [B, A]` với đỉnh `B` ở đầu, `helper` rỗng. Khi dùng phương án hai queue ưu tiên pop và `push(C)`, trước khi đổi vai, `helper` chứa gì?

*Đáp án:* Đầu tiên `helper = [C]`, sau chuyển `B` và `A` thành **`[C, B, A]`**. Đổi vai để queue này trở thành `main`.

**Bài 7 — Khấu hao.** Tại sao không thể lấy lập luận O(1) khấu hao của queue bằng hai stack rồi áp dụng ngay cho stack bằng queue quay vòng?

*Đáp án:* Trong queue hai stack, **mỗi phần tử chỉ chuyển tối đa một lần** giữa hai stack. Trong stack bằng queue quay vòng, **một phần tử có thể bị quay nhiều lần** qua các lần push/pop khác nhau; các chuỗi phép có thể tốn Θ(m²).

**Bài 8 — Bất biến.** Nếu phương án ưu tiên pop có queue `q = [D, C, B, A]`, hãy viết dãy stack logic từ đáy đến đỉnh. `top()` và `pop()` sẽ trả gì?

*Đáp án:* Stack logic là **`[A, B, C, D]`**. Cả `top()` và `pop()` đều trả **`D`**, nhưng chỉ `pop()` xóa `D` và để lại queue `[C, B, A]`.

**Ghi nhớ:** Ngăn xếp có thể được cài bằng queue FIFO bằng cách **quay vòng phần tử** hoặc **chuyển giữa hai queue**. Nếu đặt **đỉnh ở đầu**, ta trả chi phí O(n) khi `push` để `pop/top` nhanh O(1). Nếu đặt **đỉnh ở cuối**, `push` O(1) nhưng `pop/top` phải di chuyển O(n) phần tử. Hai cách đều đúng LIFO nhưng **không có bảo đảm O(1) khấu hao cho cả hai phép trên mọi chuỗi thao tác**; đó là đánh đổi cần hiểu trước khi chọn giải pháp.
