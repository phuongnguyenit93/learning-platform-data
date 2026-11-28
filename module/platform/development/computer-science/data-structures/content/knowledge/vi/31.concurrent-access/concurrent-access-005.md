# Thao tác nguyên tử và điểm tuyến tính hóa

## 1. Một thao tác “xảy ra tại một thời điểm” nghĩa là gì?

Giả sử nền tảng học tập còn đúng **một suất** tham gia buổi thực hành. Hai luồng đồng thời gọi `dang_ky("lop-A")`. Hợp đồng mong muốn là: **chỉ một lời gọi trả thành công**, lời gọi còn lại trả hết chỗ, dù cả hai bắt đầu gần như cùng lúc.

Ta muốn hành vi của hai lời gọi **có thể giải thích như thể chúng được thực hiện lần lượt** trên cùng một trạng thái: lần đầu giảm số chỗ từ 1 xuống 0; lần sau thấy 0 và thất bại.

Đó là động cơ của hai khái niệm:

- **Thao tác nguyên tử (atomic operation)** ở cấp đặc tả: người quan sát không thấy một thao tác bị chia thành các bước trung gian làm sai hợp đồng.
- **Điểm tuyến tính hóa (linearization point)**: một **thời điểm logic** nằm giữa lúc lời gọi bắt đầu và lúc nó trả về, tại đó ta có thể coi **toàn bộ hiệu ứng của lời gọi** xảy ra tức thời.

Ví dụ, nếu một phương thức bảo vệ kiểm tra–trừ số chỗ bằng mutex, ta có thể chọn bước cập nhật số chỗ khi giữ mutex làm điểm tuyến tính hóa của lời gọi thành công.

**Nhưng:** mỗi phương thức `get` và `put` nguyên tử **không tự làm** một chuỗi `get → kiểm tra → put` trở thành nguyên tử. Để xử lý đúng, trước tiên cần xác định **thao tác trừu tượng nào** là đơn vị người dùng đang yêu cầu.

Bài này thuộc chương **Truy cập đồng thời** của mô-đun **Cấu trúc dữ liệu**. Những khái niệm dưới đây áp dụng cho stack, queue, bảng băm, cây, đồ thị, bộ đếm và các trạng thái nghiệp vụ phức hợp.

## 2. Phân biệt bước mã máy, phương thức và thao tác logic

Trong lập trình, từ “nguyên tử” có thể được dùng ở những cấp độ khác nhau:

| Cấp | Ví dụ | Có gì được bảo đảm? |
| --- | --- | --- |
| Truy cập bộ nhớ nguyên tử | Atomic load/store của một biến theo kiểu atomic | Không quan sát giá trị bị xé; còn phải xét thứ tự và hiển thị bộ nhớ |
| Lệnh read-modify-write nguyên tử | `fetch_add`, `compare_exchange` | Một bước cập nhật có điều kiện hay tăng biến được thực hiện nguyên tử theo API |
| **Phương thức của cấu trúc** | `push(x)`, `try_pop()`, `put_if_absent(k,v)` | Một lời gọi tuân thủ đặc tả bất chấp lời gọi đồng thời |
| **Nghiệp vụ gồm nhiều bước** | `reserve_if_available`, `transfer(A,B,q)` | Cả kiểm tra và những cập nhật liên quan được coi là một thao tác logic |
| **Giao dịch nhiều nguồn** | Trừ kho, ghi đơn hàng, phát sự kiện | Cần cơ chế giao dịch/bền vững tương ứng; mutex trong RAM chưa đủ |

Ví dụ phép tăng bộ đếm:

```python
x = x + 1
```

Về logic, nó có thể gồm:

```text
r = read(x)
r = r + 1
write(x, r)
```

Nếu hai luồng đều đọc `x=0`, chúng có thể cùng ghi `x=1` thay vì kết quả đúng `x=2`. Một dòng nguồn không phải bằng chứng cho tính nguyên tử của toàn phép tăng.

Ngược lại, một phương thức thực hiện **nhiều dòng** vẫn có thể là thao tác nguyên tử ở cấp API nếu có một giao thức đồng bộ phù hợp và mọi người truy cập đều tuân thủ.

## 3. Lịch sử lời gọi: invocation và response

Để nói chính xác về tuyến tính hóa, ta mô tả các sự kiện của những lời gọi đồng thời.

- **Invocation:** lời gọi một phương thức bắt đầu, kèm đối số.
- **Response:** lời gọi trả về giá trị, hoặc lỗi được định nghĩa trong đặc tả.
- **Operation:** cặp invocation–response của một lời gọi hoàn thành.

Ký hiệu một thao tác `op_i` có khoảng thực thi:

\[
I_i=[inv_i,\;res_i].
\]

Ví dụ với stack ban đầu rỗng:

```text
Thời gian     1    2    3    4    5    6
              |----|----|----|----|----|
T1: push(X)   [───────────────] trả OK
T2: pop()          [────────────────] trả X
```

Vì hai khoảng **chồng lấp**, ta có thể tuyến tính hóa `push(X)` trước `pop()`, ngay cả nếu `pop()` bắt đầu khi `push` chưa trả về.

Ngược lại, nếu `push(X)` **đã trả về** rồi `pop()` **mới bắt đầu**, thứ tự thực tế bắt buộc là `push(X)` trước `pop()`.

Định nghĩa quan hệ thứ tự thời gian thực:

\[
op_i\prec_{rt} op_j
\quad\text{khi}\quad
res_i < inv_j.
\]

Nếu hai thao tác chồng lấp, quan hệ `\prec_{rt}` **không bắt buộc** sắp chúng với nhau. Một lịch tuyến tính hóa có thể chọn thứ tự phù hợp với **kết quả trả về và đặc tả cấu trúc**.

**Lưu ý:** “thứ tự thời gian thực” ở đây nói về **thứ tự invocation/response của các lời gọi**, không phải quy định “luồng nào bắt đầu trước thì luôn phải thắng”.

## 4. Định nghĩa tuyến tính hóa được

Một lịch sử các lời gọi **linearizable (tuyến tính hóa được)** nếu ta có thể đặt các thao tác vào một thứ tự tuần tự sao cho:

1. **Mỗi thao tác xuất hiện đúng một lần** với đối số, kết quả và hiệu ứng theo đặc tả của cấu trúc.
2. **Thứ tự thời gian thực được tôn trọng:** nếu A đã hoàn thành trước khi B bắt đầu, A phải đứng trước B.
3. Những thao tác **chồng lấp** có thể được sắp theo thứ tự nào đó, nhưng thứ tự được chọn phải giải thích được **toàn bộ kết quả quan sát**.
4. Mỗi thao tác hoàn thành có thể được gán một điểm logic **nằm trong chính khoảng invocation–response của nó**.

Có thể hình dung:

```text
Lịch sử thật:
A: [----------------]
B:      [-------------]
C:                        [--------]

Thứ tự logic có thể:
B ---- A ---- C     (nếu B và A chồng lấp, kết quả phù hợp)
hoặc
A ---- B ---- C     (nếu kết quả phù hợp)

Không được:
C ---- A ---- B     nếu C bắt đầu sau khi cả A và B đã trả về.
```

Các điểm tuyến tính hóa là công cụ để **chứng minh** sự tồn tại của một thứ tự như vậy. Chúng có thể trùng một thao tác máy cụ thể, hoặc là **điểm trừu tượng** khi thao tác trở nên có hiệu lực theo hợp đồng. Không phải mọi thuật toán concurrent đều có **một dòng mã cố định** làm điểm tuyến tính hóa trong mọi lịch thực thi.

### Điểm tuyến tính hóa không phải thời điểm bắt đầu hay kết thúc mặc định

Không thể chọn tùy tiện “khi gọi” hoặc “khi trả về” cho mọi thao tác. Thời điểm được chọn phải bảo đảm **kết quả của các lời gọi chồng lấp** khớp với một thực thi tuần tự hợp lệ.

Ví dụ, một phép `pop()` thành công không thể được xem là xảy ra **trước mọi phép push tạo phần tử mà nó trả về**, nếu stack trước đó rỗng và không có thao tác nào khác.

## 5. Lịch đúng và lịch sai với stack

Stack hoạt động theo quy tắc **LIFO**. Ban đầu stack rỗng, không có thao tác nền.

### Lịch H1: đúng

| Thời điểm | T1 | T2 |
| ---: | --- | --- |
| 1 | Bắt đầu `push(X)` | |
| 2 | | Bắt đầu `pop()` |
| 3 | `push(X)` trả `OK` | |
| 4 | | `pop()` trả `X` |

Hai thao tác **chồng lấp** tại khoảng [2,3]. Thứ tự tuần tự `push(X) → pop()` hợp lệ vì `pop` lấy được X. Có thể chọn điểm logic của push trước điểm logic của pop.

### Lịch H2: sai

| Thời điểm | T1 | T2 |
| ---: | --- | --- |
| 1 | Bắt đầu `push(X)` | |
| 2 | `push(X)` trả `OK` | |
| 3 | | Bắt đầu `pop()` |
| 4 | | `pop()` trả `EMPTY` |

Không có tác vụ nào khác. Bắt buộc `push(X)` đứng trước `pop()`, vì push trả về trước khi pop bắt đầu. Stack sau push chứa X, nên pop **không thể** trả EMPTY theo đặc tả của `try_pop`.

**Đây là một phản ví dụ tuyến tính hóa:** không tìm được thứ tự hợp lệ cho hai lời gọi, dù giả sử cả hai phương thức riêng lẻ “không làm hỏng” cấu trúc nội bộ.

### Lịch H3: chồng lấp không đồng nghĩa thứ tự ngẫu nhiên

Nếu `pop()` trả EMPTY **trước khi** một `push(X)` chồng lấp hoàn tất, vẫn có thể có lịch hợp lệ **pop trước push**. Cần xét cụ thể invocation, response và kết quả; chỉ thấy “hai luồng chạy đồng thời” chưa đủ kết luận đúng/sai.

## 6. Queue: tuyến tính hóa phải tôn trọng FIFO

Queue hỗ trợ `enqueue(x)` và `try_dequeue()` với quy tắc **FIFO**.

Ban đầu rỗng, lần lượt hoàn thành:

```text
enqueue(A) -> OK
enqueue(B) -> OK
try_dequeue() -> B
```

Nếu không có dequeue hoặc thao tác loại bỏ A ở giữa, lịch trên **không thể tuyến tính hóa được**: cả hai enqueue đã hoàn thành trước dequeue; queue phải trả **A**, không phải B.

Ngược lại, nếu hai lần enqueue **chồng lấp**, thứ tự FIFO có thể là A rồi B **hoặc** B rồi A tùy thứ tự tuyến tính hóa được chọn; kết quả dequeue phải nhất quán với thứ tự ấy.

**Điểm đáng chú ý:** tính tuyến tính hóa là thuộc tính của **toàn lịch sử lời gọi và giá trị trả về**. Nó không có nghĩa mỗi luồng phải quan sát cùng một thứ tự “đến trước” dựa trên thời điểm bắt đầu.

## 7. Một cài đặt queue dùng mutex và điểm tuyến tính hóa

Ví dụ Python sau lưu dữ liệu bằng `collections.deque` và dùng **một Lock** để bảo vệ cả nội dung và phép kiểm tra rỗng.

```python
from collections import deque
from threading import Lock


class LinearizableQueue:
    def __init__(self):
        self._items = deque()
        self._lock = Lock()

    def enqueue(self, value):
        with self._lock:
            self._items.append(value)
            # Có thể chọn append làm điểm tuyến tính hóa.
            return "OK"

    def try_dequeue(self):
        with self._lock:
            if not self._items:
                # Điểm tuyến tính hóa của EMPTY là kiểm tra rỗng
                # khi đã giữ cùng lock.
                return False, None

            value = self._items.popleft()
            # Điểm tuyến tính hóa của dequeue thành công là popleft.
            return True, value

    def size(self):
        with self._lock:
            return len(self._items)


q = LinearizableQueue()
print(q.enqueue("A"))       # OK
print(q.enqueue("B"))       # OK
print(q.try_dequeue())      # (True, 'A')
print(q.try_dequeue())      # (True, 'B')
print(q.try_dequeue())      # (False, None)
print(q.size())             # 0

q.enqueue(None)
print(q.try_dequeue())      # (True, None): None là dữ liệu hợp lệ.
```

Tại sao trả cặp `(success, value)` thay vì chỉ `None`? Vì `None` có thể là **giá trị thật** của queue. Một API cần phân biệt rõ **queue rỗng** và **phần tử có giá trị None**.

Khi giữ lock, `enqueue`/`try_dequeue`/`size` không thể quan sát những cập nhật nửa chừng từ các phương thức khác **cũng dùng lock này**. Vì vậy, ta chọn các điểm:

| Thao tác | Điểm tuyến tính hóa có thể chọn |
| --- | --- |
| `enqueue(x)` | Lúc `append(x)` dưới lock |
| `try_dequeue()` thành công | Lúc `popleft()` dưới lock |
| `try_dequeue()` trả rỗng | Lúc kiểm tra `not self._items` dưới lock |
| `size()` | Lúc đọc `len(self._items)` dưới lock |

**Không phải “lúc lấy khóa” luôn là điểm đúng:** `enqueue` chưa thêm phần tử tại thời điểm vừa vào đoạn găng; chọn `append` rõ hơn. Quan trọng là điểm được chọn nằm trong lời gọi và làm tất cả kết quả khớp với queue tuần tự.

Độ phức tạp công việc `append`/`popleft` của deque thường `O(1)` (phân bổ cho append theo mô hình thư viện); nhưng **thời gian chờ lock** không được cận này bao phủ. Cấu trúc thread-safe chưa chắc là cấu trúc có thông lượng cao nhất khi nhiều luồng tranh chấp.

## 8. Queue chờ và điểm tuyến tính hóa của thao tác blocking

Một `Queue.get()` chặn cho đến khi có phần tử có lịch sử:

```text
T1: get() bắt đầu và chờ vì queue rỗng
T2: enqueue(X) bắt đầu
T2: enqueue(X) hoàn thành
T1: get() lấy X rồi trả về
```

Ta **không** tuyến tính hóa `get()` tại thời điểm nó bắt đầu chờ, vì khi đó queue rỗng và chưa có X để lấy. Có thể tuyến tính hóa `get()` tại thời điểm **nó thực sự loại X ra khỏi queue**.

Một `get()` có thể chờ lâu, nhưng nếu đã trả về, điểm tuyến tính hóa của lần gọi hoàn thành phải nằm trong khoảng invocation–response. Việc chờ là thuộc tính **tiến triển/liveness**, khác với tính **an toàn/safety** của thứ tự trả kết quả.

Nếu một blocking `get()` bị hủy hoặc timeout, cần định nghĩa **rõ hợp đồng**: có thể trả lỗi, không loại phần tử, hoặc trong một vài API có trạng thái “đã lấy nhưng trả kết quả bị gián đoạn”. Không thể suy ra điểm tuyến tính hóa chỉ từ tên phương thức.

Trong Python `queue.Queue`, `empty()` và `qsize()` chỉ phản ánh trạng thái tại một thời điểm; gọi `if not q.empty(): q.get()` không tạo một thao tác thử lấy nguyên tử. Hãy dùng `get_nowait()` và xử lý ngoại lệ `Empty` khi không muốn chờ.

## 9. Bộ đếm nguyên tử: bước cập nhật khác bước đọc–sửa–ghi

Cho bộ đếm bắt đầu từ 0; hai luồng cùng tăng một lần. Một triển khai ngây thơ:

```text
T1: read 0
T2: read 0
T1: write 1
T2: write 1
```

Kết quả là 1, dù hai thao tác `increment()` đều báo hoàn tất. Không có thứ tự tuần tự nào của hai lần tăng từ 0 cho kết quả cuối là 1.

### Dùng mutex

```python
from threading import Lock


class AtomicCounter:
    def __init__(self, initial=0):
        self._value = initial
        self._lock = Lock()

    def increment(self):
        with self._lock:
            self._value += 1
            return self._value

    def read(self):
        with self._lock:
            return self._value
```

Có thể chọn bước gán giá trị mới dưới lock làm điểm tuyến tính hóa cho `increment`, và bước đọc `_value` dưới lock cho `read`. Nếu hai luồng tăng từ 0, kết quả trả về của hai lần `increment()` là **1 và 2** theo một thứ tự nào đó; một lần `read()` sau cả hai phải thấy 2.

### Dùng primitive atomic read-modify-write

Trong ngôn ngữ/thư viện cung cấp `fetch_add(1)` nguyên tử, bước read-modify-write có thể là điểm tuyến tính hóa. Tuy nhiên, phải phân biệt **giá trị cũ** (nhiều `fetch_add` trả về) với **giá trị mới** theo đặc tả API.

Không nên cố giả lập CAS hoặc fetch-add bằng `if` và gán biến thường rồi đặt tên hàm `atomic_increment`. **Đặt tên không tạo bảo đảm nguyên tử.**

## 10. CAS: điểm tuyến tính hóa ở bước so sánh–ghi nguyên tử

**Compare-and-swap (CAS)** thử thay giá trị `expected` bằng `desired` **chỉ nếu** vị trí hiện hành vẫn bằng `expected`.

Mã giả cho phép đặt một chỗ:

```text
reserve_one(stock_atomic):
    loop:
        old = atomic_load(stock_atomic)
        if old == 0:
            return false
        if compare_exchange(stock_atomic, old, old - 1):
            return true
        # Người khác đã thay đổi stock: đọc lại và xét lại.
```

Giả sử stock ban đầu là 1:

```text
T1: load -> 1
T2: load -> 1
T1: CAS(1 -> 0) thành công
T2: CAS(1 -> 0) thất bại
T2: load -> 0, trả false
```

- Lời gọi **thành công** có thể tuyến tính hóa tại CAS thành công.
- Lời gọi **thất bại vì hết hàng** có thể tuyến tính hóa tại lần `atomic_load` đọc được 0, với điều kiện giá trị 0 có ý nghĩa theo đặc tả và thuật toán.
- CAS thất bại do giá trị đổi thường chỉ là **bước thử nội bộ**; phương thức đặt chỗ chưa kết thúc, có thể lặp lại và không cần tuyến tính hóa tại mỗi lần thử.

**CAS một biến không tự bảo đảm nguyên tử cho nhiều trường.** Nếu phải vừa giảm `stock` vừa ghi `reservation_id` vào bảng, cần thêm giao thức nhất quán cho thao tác ghép.

### Memory ordering và vấn đề ABA

Atomicity của CAS chưa kể toàn bộ yêu cầu **nhìn thấy bộ nhớ**. Nếu `stock` là một con trỏ tới cấu trúc dữ liệu mới, cách công bố các trường cấu trúc phụ thuộc quy tắc acquire/release và mô hình bộ nhớ của ngôn ngữ. Không thể chỉ dùng biến thường và coi nó như primitive atomic.

**ABA**: một luồng đọc A, luồng khác thay A→B→A, khiến phép CAS so sánh A có thể thành công dù trạng thái đã thay đổi. Với stack lock-free, ABA có thể làm hỏng thao tác pop nếu không có cơ chế tagged pointer, version hoặc quản lý vòng đời node phù hợp.

## 11. Điểm tuyến tính hóa của thao tác thất bại

Không chỉ thao tác thành công mới cần điểm tuyến tính hóa. Một `try_pop()` trả EMPTY hoặc `put_if_absent` trả “đã tồn tại” cũng là **kết quả có thể quan sát**.

Ví dụ stack rỗng:

```text
T1: try_pop() -> EMPTY
T2: push(X)   -> OK
```

Nếu T1 và T2 **chồng lấp**, kết quả EMPTY có thể hợp lệ khi chọn điểm logic của T1 **trước** push. Nhưng nếu `push(X)` **đã trả** trước khi `try_pop()` bắt đầu, EMPTY là sai nếu không có pop khác.

Trong thuật toán dùng lock:

- `try_pop()` thất bại có thể tuyến tính hóa tại lần **kiểm tra stack rỗng** trong lock.
- `insert_if_absent(k,v)` thất bại có thể tuyến tính hóa tại lần **kiểm tra khóa đã tồn tại** trong lock.
- `reserve_if_available(q)` thất bại có thể tuyến tính hóa tại lần **kiểm tra lượng còn lại nhỏ hơn q** trong lock.

**Không gán mọi thao tác thất bại cho thời điểm trả về một cách máy móc.** Cần xác định trạng thái nào biện minh cho kết quả thất bại, và thời điểm quan sát trạng thái đó có thuộc khoảng lời gọi hay không.

### Ngoại lệ và hợp đồng API

Một lời gọi trả ngoại lệ cần có đặc tả: ngoại lệ có nghĩa “không thay đổi trạng thái”, “có thể đã thay đổi một phần”, hay “tình trạng không xác định”? Nếu hợp đồng hứa **failure atomicity** (thất bại không tạo hiệu ứng), triển khai phải có cách khôi phục hoặc công bố nguyên vẹn.

Mutex chỉ ngăn **luồng khác cùng dùng mutex** quan sát trạng thái đang cập nhật; nó **không** tự rollback khi có `MemoryError` hay khi tiến trình chết giữa thao tác.

## 12. Ví dụ check-then-act: từng lời gọi đúng nhưng cả quy trình sai

Một bảng băm concurrent có thể bảo đảm `get` và `put` nguyên tử riêng lẻ. Bên gọi lại viết:

```text
if map.get(k) == MISSING:
    map.put(k, create_value())
```

Hai luồng có thể:

```text
T1: get(k) -> MISSING
T2: get(k) -> MISSING
T1: create_value() -> v1
T2: create_value() -> v2
T1: put(k,v1)
T2: put(k,v2)
```

Mỗi `get` và `put` đều có thể có điểm tuyến tính hóa hợp lệ theo đặc tả map. Nhưng thao tác nghiệp vụ **“chỉ tạo giá trị nếu khóa chưa có”** không tuyến tính hóa được theo hợp đồng **một người chiến thắng** nếu cả hai bên gọi đều báo “mình vừa tạo mới”.

Giải pháp có thể là API `put_if_absent`/`compute_if_absent` có bảo đảm phù hợp, hoặc lock bao trọn **kiểm tra–tạo/cập nhật**.

**Thận trọng với callback:** một số thư viện có thể gọi hàm tạo giá trị **nhiều lần** rồi chỉ công bố một kết quả. Không suy ra từ `put_if_absent` rằng callback có tác dụng phụ như gửi email hay thanh toán **chắc chắn chỉ chạy một lần**.

### Queue và stack

Tương tự:

```text
if not queue.empty():
    item = queue.get()
```

Hai phương thức có thể đúng riêng lẻ, nhưng một consumer khác lấy phần tử cuối giữa chúng khiến `get()` chặn. Với stack, `if size()>0: pop()` có thể trở thành `pop` trên stack rỗng. Tạo thao tác `try_dequeue`/`try_pop` nguyên tử giải quyết đúng **đơn vị hành vi** hơn việc ghép hai lời gọi.

## 13. Chuyển tiền: nhiều ghi nhưng một điểm logic

Xét hai tài khoản A=70, B=30, tổng tiền 100. Phương thức `transfer(A,B,30)` cần bảo đảm:

\[
A\ge0,\quad B\ge0,\quad A+B=100.
\]

Một cài đặt khóa chung:

```python
from threading import Lock


class Ledger:
    def __init__(self, initial):
        if any(type(v) is not int or v < 0 for v in initial.values()):
            raise ValueError("Số dư phải là số nguyên không âm")
        self._balance = dict(initial)
        self._lock = Lock()

    def transfer(self, src, dst, amount):
        if type(amount) is not int or amount <= 0:
            raise ValueError("amount phải dương")
        if src == dst:
            raise ValueError("Hai tài khoản phải khác nhau")
        with self._lock:
            if src not in self._balance or dst not in self._balance:
                raise KeyError("Tài khoản không tồn tại")
            if self._balance[src] < amount:
                return False
            self._balance[src] -= amount
            self._balance[dst] += amount
            return True

    def snapshot(self):
        with self._lock:
            return tuple(sorted(self._balance.items()))


ledger = Ledger({"A": 70, "B": 30})
assert ledger.transfer("A", "B", 30) is True
assert ledger.snapshot() == (("A", 40), ("B", 60))
```

Lệnh trừ A chạy **trước** lệnh cộng B. Nhưng vì `snapshot()` và các phương thức khác đều giữ cùng lock, không ai qua API nhìn thấy trạng thái trung gian `(40,30)`.

Vì vậy ta có thể chọn **một thời điểm logic bên trong đoạn găng sau khi quyết định hợp lệ và trước khi nhả lock** làm điểm tuyến tính hóa của `transfer`. Chọn chính xác dòng trừ hay dòng cộng không quan trọng nếu tất cả lời gọi đều tương tác qua một mutex và chúng ta chứng minh được **cùng một thứ tự quan sát**.

**Giới hạn:** nếu một đoạn mã bên ngoài trực tiếp đọc `ledger._balance` không giữ lock, nó đã phá hợp đồng. Nếu lỗi xảy ra giữa hai lần cập nhật, mutex không tự khôi phục số dư cũ; cần xử lý lỗi/rollback hoặc cách công bố trạng thái mới an toàn hơn.

## 14. Snapshot: một phép đọc gồm nhiều trường cũng cần tuyến tính hóa

Giả sử T1 cần báo cáo tổng số dư, nên làm:

```text
a = get_balance("A")
b = get_balance("B")
return a + b
```

Nếu `get_balance` là những lời gọi tuyến tính hóa được **riêng lẻ**, lịch sau vẫn hợp lệ cho chúng:

```text
T1: get(A) -> 70
T2: transfer(A,B,30) -> OK, trạng thái thành (40,60)
T1: get(B) -> 60
T1: báo tổng = 130
```

`130` không phản ánh **bất kỳ trạng thái tuần tự nào của ledger** trong ví dụ, dù cả hai lần đọc đều hợp lệ. Nếu T1 công bố một phương thức `read_total()` với đặc tả trả tổng tại **một thời điểm logic**, triển khai ghép hai lần đọc trên có thể không tuyến tính hóa được.

Giải pháp: đọc đủ trạng thái liên quan trong **một đoạn găng chung**, hoặc đọc từ **một snapshot bất biến** có phiên bản.

Đối với snapshot nhiều trường:

- Nếu **không ai sửa các trường** khi reader đang sao chép trong lock, có thể chọn bất kỳ thời điểm thích hợp trong khoảng lock được giữ làm điểm tuyến tính hóa.
- Nếu chỉ khóa từng trường riêng lẻ, một bản sao chắp vá có thể không tương ứng với trạng thái nào.
- Nếu có cơ chế **optimistic snapshot**, phép kiểm tra phiên bản phải thật sự chứng minh reader không dùng dữ liệu thay đổi không an toàn; hai lần đọc `version` đơn giản không tự đủ nếu writer không tuân thủ giao thức công bố phù hợp.

**Snapshot nhất quán ≠ snapshot mới nhất**. Một reader đã nhận phiên bản V1 có thể duyệt nhiều phút trong khi writer công bố V2. Kết quả vẫn có thể đúng **cho V1** theo hợp đồng.

## 15. Đồ thị: một cung nằm trong nhiều chỉ mục

Một đồ thị có hướng có thể lưu:

```text
vertices = {A, B, C, ...}
edges[eid] = (source, target)
out[source] = tập edge_id đi ra
incoming[target] = tập edge_id đi vào
```

Khi thêm `e=(A→B)`, cần cập nhật **cả ba chỗ**: `edges[e]`, `out[A]`, `incoming[B]`.

Nếu thao tác `add_edge` chỉ bảo vệ từng set riêng rồi nhả lock ở giữa, một reader có thể thấy cạnh ở `out[A]` nhưng không thấy ở `incoming[B]`.

Một cài đặt đơn giản dùng lock toàn đồ thị:

```python
from threading import Lock


class DirectedGraph:
    def __init__(self, vertices):
        self._lock = Lock()
        self._vertices = set(vertices)
        self._edges = {}
        self._out = {v: set() for v in self._vertices}
        self._incoming = {v: set() for v in self._vertices}
        self._next_id = 0

    def add_edge(self, source, target):
        with self._lock:
            if source not in self._vertices or target not in self._vertices:
                raise KeyError("Đầu mút không tồn tại")
            eid = self._next_id
            self._next_id += 1
            self._edges[eid] = (source, target)
            self._out[source].add(eid)
            self._incoming[target].add(eid)
            return eid

    def snapshot(self):
        with self._lock:
            return (
                frozenset(self._vertices),
                tuple(
                    (eid, source, target)
                    for eid, (source, target) in self._edges.items()
                ),
            )


g = DirectedGraph(["A", "B", "C"])
e0 = g.add_edge("A", "B")
e1 = g.add_edge("A", "B")  # Hai cung song song, ID khác nhau.
e2 = g.add_edge("B", "B")  # Khuyên.
assert e0 != e1 != e2
assert len(g.snapshot()[1]) == 3
```

Ở đây, mỗi `add_edge` hợp lệ có một vị trí logic trong khoảng nó giữ khóa; snapshot chỉ thấy **trước** hoặc **sau** toàn bộ thao tác ấy, không thấy nửa bảng `edges` mới và nửa chỉ mục cũ.

Nếu chính sách là **đồ thị đơn** (không cung song song), thao tác đúng không phải là `has_edge` nguyên tử **rồi** `add_edge` nguyên tử tách rời. Phải xây `add_edge_if_absent` với **kiểm tra không tồn tại và cập nhật các chỉ mục trong cùng giao thức nguyên tử**.

Khi dùng khóa theo đỉnh, phải đồng bộ cả **nguồn, đích, bảng edges, cấp edge ID và vòng đời đỉnh**, tránh deadlock bằng thứ tự khóa nhất quán. Khuyên `u→u` chỉ có **một edge ID** nhưng xuất hiện ở cả chỉ mục vào và ra; không khóa hai lần một mutex không tái nhập cho cùng đỉnh.

## 16. Thứ tự thời gian thực, sequential consistency và serializability

Những thuật ngữ thường bị trộn lẫn:

| Khái niệm | Phạm vi và ý nghĩa |
| --- | --- |
| **Linearizability** | Lịch các lời gọi trên cấu trúc có thể giải thích như thao tác tức thời; **giữ thứ tự thời gian thực** của lời gọi không chồng lấp |
| **Sequential consistency** | Có một thứ tự tuần tự giữ thứ tự thao tác **trong từng luồng**, nhưng không nhất thiết giữ thứ tự thời gian thực giữa những luồng |
| **Serializability** | Lịch giao dịch tương đương một thứ tự tuần tự của **các giao dịch**, thường xét xung đột/đọc–ghi và kết quả theo đặc tả cơ sở dữ liệu |
| **Strict serializability** | Serializability **và** tôn trọng thứ tự thời gian thực của giao dịch không chồng lấp; gần với linearizability ở cấp giao dịch |
| **Atomicity trong ACID** | Giao dịch hoàn tất tất cả hoặc không để lại hiệu ứng theo hợp đồng lỗi/rollback của DB; không đồng nghĩa riêng với linearizability |

### Một ví dụ phân biệt linearizability với sequential consistency

Hai luồng chia sẻ một biến ban đầu 0:

```text
T1: write(1) hoàn thành
T2: read() bắt đầu sau khi T1 đã hoàn thành → trả 0
```

Nếu không có các ràng buộc khác, một thứ tự tuần tự `read(0) → write(1)` có thể giữ thứ tự trong từng luồng, nên có thể **phù hợp sequential consistency**. Nhưng nó **vi phạm linearizability** vì `write(1)` đã hoàn thành **trước khi** `read()` bắt đầu và không có ghi nào khác đưa giá trị về 0.

Linearizability mạnh hơn ở chỗ bảo toàn thứ tự thời gian thực. Tuy nhiên, **không đồng nghĩa với độ bền dữ liệu** sau crash: bộ nhớ RAM có thể mất toàn bộ sau sự cố dù những lời gọi trước đó tuyến tính hóa được.

## 17. Phương thức tuyến tính hóa được vẫn không tự tạo giao dịch nhiều bước

Giả sử map có `get(k)` và `put(k,v)` tuyến tính hóa được. Bên gọi:

```text
old = map.get(k)
if old < max_value:
    map.put(k, old + 1)
```

Tính tuyến tính hóa của từng lần `get` và `put` **không đủ** để tạo một thao tác `increment_if_below_limit` tuyến tính hóa được. Hai luồng có thể dùng cùng `old`, dẫn tới **lost update** hoặc báo thành công vượt quota.

Tương tự, trong đồ thị:

```text
if not graph.has_edge(u,v):
    graph.add_edge(u,v)
```

Nếu hai luồng cùng thấy chưa có cạnh, chúng có thể tạo **cạnh song song** trái chính sách đồ thị đơn.

**Nguyên tắc API:** đưa **đơn vị quyết định** cần nguyên tử thành **một phương thức công khai**, ví dụ `reserve_if_available`, `increment_if_below_limit`, `put_if_absent` hoặc `add_edge_if_absent`.

Linearizability có tính **cục bộ (locality)**: nếu các đối tượng độc lập đều tuyến tính hóa được, lịch sử của hệ thống các đối tượng ấy có thể tuyến tính hóa ở cấp từng đối tượng. Nhưng điều đó **không** làm một quy trình **gồm nhiều lời gọi tới nhiều đối tượng** tự có tính nguyên tử giao dịch. Khi bất biến trải trên hai tài khoản hay hai cấu trúc, vẫn cần giao thức commit/khóa/giao dịch ở cấp cao hơn.

## 18. Điểm tuyến tính hóa và bảo đảm tiến triển là hai trục khác nhau

Một phương thức có thể tuyến tính hóa được nhưng **chờ vô hạn** nếu lock do luồng bị dừng giữ mãi. Vì vậy cần phân biệt **tính an toàn (safety)** và **khả năng tiến triển (liveness)**:

| Thuộc tính | Câu hỏi chính |
| --- | --- |
| Linearizability | Những lời gọi đã hoàn thành có kết quả khớp một lịch tuần tự hợp lệ không? |
| Deadlock freedom | Có loại trừ một số kiểu chờ vòng tròn khiến không ai tiến lên không? |
| Starvation freedom | Mỗi luồng đang chờ có cơ hội hoàn tất không? |
| Lock-free | Hệ thống còn tiến triển: trong những điều kiện mô hình đã nêu, có **ít nhất một** thao tác hoàn tất sau hữu hạn bước của hệ thống |
| Wait-free | **Mỗi thao tác** của mỗi luồng hoàn tất sau số bước hữu hạn theo mô hình, không phụ thuộc việc luồng khác bị chậm |

Một queue dùng mutex có thể **linearizable** nhưng không **lock-free**. Một thuật toán dùng CAS có thể **lock-free** nhưng vẫn sai về thứ tự FIFO hoặc có lỗi ABA, nên không **linearizable**.

Khi đánh giá, phải hỏi **cả hai**:

1. Những thao tác hoàn thành có **đúng ngữ nghĩa** không?
2. Hệ thống có **tiếp tục hoàn thành công việc** khi tranh chấp, bị tạm dừng hoặc lỗi không?

Tính công bằng trong lịch lập lịch, fairness của lock và giới hạn thời gian chờ cũng không tự đi theo linearizability.

## 19. Kiểm thử lịch sử: tìm một thứ tự tuần tự phù hợp

Một cách kiểm tra mạnh hơn so với chỉ nhìn trạng thái cuối là ghi lại các sự kiện:

```text
thread, operation, arguments, invocation_time,
response_time, returned_value
```

Với **một lịch sử nhỏ, hoàn chỉnh**, có thể thử tìm một thứ tự tuần tự sao cho:

- Các thao tác **không chồng lấp** được xếp theo thứ tự thời gian thực.
- Mọi kết quả khớp đặc tả tuần tự của cấu trúc.

Ví dụ dưới đây là **bộ kiểm tra minh họa dành cho stack nhỏ**. Nó tìm bằng quay lui và có thể tốn rất nhiều thời gian khi có nhiều thao tác; không phải model checker sản xuất.

```python
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Op:
    name: str               # "push" hoặc "pop"
    argument: str | None     # Giá trị push; pop không có argument.
    result: str              # "OK", "EMPTY" hoặc giá trị pop trả về.
    start: int               # Thời điểm invocation trong cùng thang đo.
    end: int                 # Thời điểm response.


def step_stack(stack, op):
    if op.name == "push":
        return stack + (op.argument,), "OK"
    if op.name == "pop":
        if not stack:
            return stack, "EMPTY"
        return stack[:-1], stack[-1]
    raise ValueError("Thao tác không được hỗ trợ")


def find_linearization(operations):
    ops = tuple(operations)
    n = len(ops)
    for op in ops:
        if op.start >= op.end:
            raise ValueError("start phải trước end")

    # Những thao tác đã TRẢ trước khi i BẮT ĐẦU phải đứng trước i.
    predecessors = tuple(
        tuple(j for j in range(n)
              if j != i and ops[j].end < ops[i].start)
        for i in range(n)
    )
    all_done = (1 << n) - 1

    @lru_cache(maxsize=None)
    def search(done, stack):
        if done == all_done:
            return ()

        for i, op in enumerate(ops):
            if (done >> i) & 1:
                continue
            if any(not ((done >> j) & 1)
                   for j in predecessors[i]):
                continue
            new_stack, expected = step_stack(stack, op)
            if expected != op.result:
                continue

            suffix = search(done | (1 << i), new_stack)
            if suffix is not None:
                return (i,) + suffix
        return None

    return search(0, ())


# H1: push và pop CHỒNG LẤP; push có thể tuyến tính hóa trước.
good = [
    Op("push", "X", "OK", 1, 4),
    Op("pop", None, "X", 3, 5),
]
print(find_linearization(good))  # (0, 1)

# H2: push đã xong trước khi pop bắt đầu; pop không thể rỗng.
bad = [
    Op("push", "X", "OK", 1, 2),
    Op("pop", None, "EMPTY", 3, 4),
]
print(find_linearization(bad))   # None
```

**Cách đọc:** nếu có thứ tự phù hợp, hàm trả một tuple chỉ số thao tác làm **chứng cứ**, ví dụ `(0,1)`. Nếu không tìm được, trả `None` và lịch sử nhỏ đó **không tuyến tính hóa được theo mô hình stack đã chọn**.

**Giới hạn của bộ kiểm tra:**

- Chỉ hỗ trợ thao tác **đã hoàn thành**, stack bắt đầu rỗng, không có tác động ngoài danh sách `operations`; pending operation và crash đòi xử lý lịch sử phức tạp hơn.
- Không đo/đảm bảo điều gì về lập lịch hoặc quan hệ bộ nhớ nội bộ; chỉ kiểm tra **kết quả được ghi lại**.
- Các giá trị pop trong ví dụ là chuỗi và `"EMPTY"` được dành riêng cho kết quả rỗng; một hệ thống cho phép đẩy chính chuỗi `"EMPTY"` cần API kết quả phân biệt rõ, như `(success,value)`.
- Các thời điểm trong dữ liệu test phải dùng **cùng thang đo logic/đồng hồ**; so timestamp từ các máy không đồng bộ có thể làm sai ràng buộc thời gian thực.
- Quay lui có thể phải xét rất nhiều thứ tự, **tăng theo cấp số tổ hợp hoặc giai thừa** trong tình huống xấu; dùng cho lịch ngắn, không phải hàng triệu thao tác.

Có thể thay `step_stack` bằng mô hình tuần tự của queue, map hay bộ đếm để kiểm tra lịch sử những cấu trúc đó, với các kiểu kết quả và quy tắc tương ứng.

## 20. Điểm tuyến tính hóa trong thiết kế không dùng một mutex chung

Với mutex toàn cấu trúc, cách chứng minh thường thẳng: không có hai lời gọi công khai cùng vào đoạn găng, nên một thao tác có thể chọn điểm logic khi cập nhật/đọc trạng thái.

Với **fine-grained locking**, mỗi bucket hoặc đỉnh có lock riêng, **một thao tác có thể phải lấy nhiều lock** để bảo vệ bất biến toàn cấu trúc. Chỉ định điểm tuyến tính hóa trở nên khó hơn:

- Một `put(k)` có thể sửa bucket rồi tăng `size`. Nếu `size()` là API công khai, nó phải tuân theo giao thức đồng bộ tương thích.
- Một `rehash` chuyển nhiều khóa từ bảng cũ sang bảng mới. Người đọc phải có cách nhìn một trạng thái logic hợp lệ trong cả quá trình chuyển.
- Một `add_edge(u,v)` sửa bảng cạnh, chỉ mục ra và chỉ mục vào. Các API đọc từng phía không được thấy một lần thêm “nửa chừng” nếu hợp đồng yêu cầu tuyến tính hóa ở cấp đồ thị.
- Một `delete_vertex(v)` có thể xóa nhiều cạnh vào/ra và làm thay đổi ánh xạ ID; phải quy định thời điểm xóa có hiệu lực.

Trong thuật toán **lock-free**, điểm tuyến tính hóa có thể nằm ở một CAS công bố nút mới, một bước chuyển trạng thái hoặc có thể **phụ thuộc kết quả tranh chấp**; không phải lúc nào đọc mã cũng thấy một dòng “điểm tuyến tính hóa” hiển nhiên.

**Cách chứng minh hữu ích:**

1. Xác định đặc tả tuần tự và bất biến của từng thao tác công khai.
2. Liệt kê trạng thái dùng chung, các bước đọc/ghi và vùng có thể xen kẽ.
3. Chỉ ra thời điểm thao tác trở nên có hiệu lực đối với tất cả quan sát hợp lệ.
4. Chứng minh điểm ấy nằm trong khoảng invocation–response.
5. Chứng minh thứ tự các điểm tôn trọng thứ tự thời gian thực và tất cả kết quả.
6. Xử lý cả **lời gọi thất bại, cạnh tranh, exception, hủy bỏ và điều kiện biên** theo hợp đồng.

## 21. Bộ nhớ, ngoại lệ và sự công bố an toàn

**Linearizability là bảo đảm về kết quả thao tác**, nhưng để triển khai đúng trong hệ thống cụ thể còn cần:

- **Memory visibility:** luồng khác thấy đủ các trường đã được khởi tạo khi tham chiếu đối tượng được công bố. Acquire/release hoặc lock phù hợp có thể tạo quan hệ happens-before theo runtime.
- **Vòng đời đối tượng:** một luồng không được đọc một nút đã bị giải phóng/reuse. Với cấu trúc lock-free, có thể cần hazard pointers, epoch reclamation hoặc cơ chế runtime quản lý bộ nhớ.
- **Failure atomicity:** nếu API hứa thất bại không đổi trạng thái, phải đảm bảo rollback/công bố chỉ sau khi dựng đủ, không chỉ nhả mutex.
- **Tính bền vững (durability):** thao tác trả thành công không tự tồn tại sau crash; cần ghi bền hoặc giao dịch nếu ứng dụng yêu cầu.
- **Độc lập với GIL:** một phiên bản Python có GIL không phải bằng chứng cho tính nguyên tử của nhiều phương thức ghép, nhất là khi I/O, extension hoặc runtime thay đổi.

Khi tạo cấu trúc bất biến mới, một chiến lược phổ biến là **dựng đầy đủ → xác thực → công bố một tham chiếu phiên bản theo cơ chế đồng bộ đúng**. Người đọc giữ handle của phiên bản và không thấy dữ liệu đang xây dở. Nhưng snapshot có thể là **phiên bản cũ**, và phiên bản cũ chỉ được thu hồi khi không còn reader sử dụng.

## 22. Độ phức tạp: điểm tuyến tính hóa không làm biến mất tranh chấp

Cho `n` phần tử hoặc đỉnh, `m` cung/cạnh:

| Thao tác | Công việc thường gặp khi không tranh chấp | Chi phí liên quan đồng thời |
| --- | --- | --- |
| `enqueue/try_dequeue` trên deque với mutex | `O(1)` theo thao tác deque thông thường | Chờ lock; lần thử lấy rỗng cũng phải đồng bộ |
| `increment/read` một bộ đếm dùng lock | `O(1)` | Thời gian chờ mutex, có thể bị preempt |
| `reserve_if_available` một số lượng | `O(1)` | Nhiều luồng tranh khóa nóng |
| `put_if_absent` với hash map phù hợp | `O(1)` **kỳ vọng** khi không rehash lớn | Tranh bucket/stripe, resize, callback và retry |
| `add_edge(u,v)` với ba hash index | `O(1)` kỳ vọng/phân bổ nếu đã có ID | Đòi hỏi đồng bộ tất cả chỉ mục |
| Snapshot n đỉnh, m cạnh | `O(n+m)` thời gian và bộ nhớ | Giữ lock lâu hoặc công bố phiên bản |
| CAS retry loop | `O(1)` **mỗi lần thử** | Số lần thử không cố định dưới tranh chấp |
| Kiểm tra tuyến tính hóa bằng quay lui | Có thể tăng theo **giai thừa** số thao tác | Chỉ thích hợp lịch sử nhỏ |

Phân biệt:

\[
T_{\mathrm{response}}
\approx T_{\mathrm{wait}}+T_{\mathrm{work}}+T_{\mathrm{coordination}}.
\]

Cận Big-O thường nói về **công việc** chứ không bảo đảm thời gian đồng hồ nếu luồng phải chờ. Chọn đúng điểm tuyến tính hóa là vấn đề **tính đúng đắn**; chọn khóa toàn cục, striped lock, CAS hay snapshot còn là bài toán **hiệu năng và khả năng tiến triển**.

Khi benchmark cần đo không chỉ throughput mà còn **p95/p99 latency, lock wait/hold time, tỷ lệ retry, bộ nhớ và trạng thái dưới khóa nóng**.

## 23. Những nhầm lẫn thường gặp

1. **“Mỗi dòng mã là nguyên tử.”** Sai: thao tác logic có thể gồm nhiều bước đọc/ghi.
2. **“Thao tác có mutex tức là mọi quy trình dùng nó đều nguyên tử.”** Sai: mỗi lời gọi có mutex riêng không tự gộp thành một giao dịch.
3. **“Linearization point phải là thời điểm invocation.”** Sai: điểm có thể nằm ở bất kỳ thời điểm hợp lệ trong khoảng invocation–response.
4. **“Hai lời gọi chồng lấp phải xếp theo thứ tự bắt đầu.”** Sai: có thể xếp theo thứ tự phù hợp đặc tả và kết quả.
5. **“Nếu A hoàn thành trước B bắt đầu, có thể tuyến tính hóa B trước A.”** Sai: vi phạm thứ tự thời gian thực.
6. **“Mọi thuật toán concurrent có một dòng mã cố định là điểm tuyến tính hóa.”** Không: một số thuật toán có điểm phụ thuộc lịch thực thi.
7. **“Một lời gọi thất bại không cần điểm tuyến tính hóa.”** Sai: EMPTY, FULL hay ALREADY_EXISTS là kết quả cần giải thích.
8. **“Lấy lock xong là thao tác đã có hiệu lực.”** Chưa chắc: hiệu ứng thường chỉ xảy ra tại bước đọc/ghi được bảo vệ.
9. **“Queue thread-safe nghĩa là FIFO theo thời điểm bắt đầu enqueue.”** Sai khi các enqueue chồng lấp; FIFO theo thứ tự tuyến tính hóa.
10. **“`empty()` rồi `get()` là một thao tác thử lấy.”** Sai: consumer khác có thể chen giữa.
11. **“Bộ đếm có atomic load/store thì `x=x+1` tự nguyên tử.”** Sai: cần atomic read-modify-write hoặc khóa cả phép tăng.
12. **“Một CAS trên một biến bảo vệ được bất biến nhiều trường.”** Sai nếu không có giao thức bổ sung.
13. **“CAS thất bại một lần là toàn bộ phương thức đã thất bại.”** Không nhất thiết: đó có thể là bước thử nội bộ trước khi retry.
14. **“Hai phép đọc an toàn thì tổng của chúng là snapshot.”** Sai: có thể ghép hai phiên bản.
15. **“Tính tuyến tính hóa của map.get và map.put tự làm register-if-absent tuyến tính hóa được.”** Sai: cần API nguyên tử ở cấp nghiệp vụ.
16. **“Sequential consistency và linearizability giống nhau.”** Sai: linearizability bảo toàn thứ tự thời gian thực.
17. **“ACID atomicity là tên khác của linearizability.”** Sai: ACID atomicity nói về toàn bộ hay không có hiệu ứng của giao dịch; mô hình nhất quán là vấn đề khác.
18. **“Linearizable đồng nghĩa lock-free/wait-free.”** Sai: đúng đắn và tiến triển là hai trục khác nhau.
19. **“Có lock thì ngoại lệ/crash tự rollback.”** Sai: lock không tự hoàn tác hay ghi bền.
20. **“Một snapshot đúng là snapshot mới nhất khi thuật toán kết thúc.”** Không: nó có thể cũ nhưng nhất quán.
21. **“Chạy nhiều lần không lỗi chứng minh mọi lịch sử đều tuyến tính hóa được.”** Không: cần tạo lịch xấu, kiểm tra kết quả và dùng công cụ xác minh.
22. **“Chỉ cần kiểm tra trạng thái cuối.”** Sai: có thể có hai lời gọi cùng báo thành công dù giá trị cuối tình cờ đúng.

## 24. Tự kiểm tra

**Câu 1.** Điểm tuyến tính hóa nằm trong khoảng thời gian nào của một lời gọi?

**Đáp án:** Trong khoảng từ **invocation đến response** của chính lời gọi; tại đó có thể coi hiệu ứng trừu tượng của lời gọi xảy ra tức thời trong một lịch tuần tự hợp lệ.

**Câu 2.** Một `push(X)` đã trả `OK` trước khi `pop()` bắt đầu; stack ban đầu rỗng và không có thao tác khác. `pop()` có thể trả EMPTY trong lịch tuyến tính hóa được không?

**Đáp án:** **Không.** Thứ tự thời gian thực buộc push trước pop; pop phải trả X.

**Câu 3.** Hai lần `enqueue(A)` và `enqueue(B)` chồng lấp. FIFO có bắt buộc A được dequeue trước B chỉ vì A bắt đầu trước không?

**Đáp án:** Không. Khi hai lời gọi chồng lấp, thứ tự tuyến tính hóa có thể chọn A trước hoặc B trước nếu các kết quả quan sát khác vẫn phù hợp.

**Câu 4.** Với `LinearizableQueue.try_dequeue()`, điểm tuyến tính hóa của kết quả EMPTY ở đâu?

**Đáp án:** Tại **bước kiểm tra queue rỗng** trong cùng lock bảo vệ queue, không phải tại một lần `empty()` riêng bên ngoài.

**Câu 5.** Hai luồng cùng gọi `increment()` lên bộ đếm 0, cả hai trả `1` nhưng bộ đếm cuối bằng 1. Có tuyến tính hóa được theo đặc tả tăng rồi trả giá trị mới không?

**Đáp án:** Không. Theo bất kỳ thứ tự tuần tự nào, hai kết quả phải là **1 và 2**, trạng thái cuối bằng 2.

**Câu 6.** Một lần `reserve_one` dùng CAS thành công đổi stock 1→0. Điểm tuyến tính hóa tự nhiên là bước nào?

**Đáp án:** **CAS thành công** làm thay đổi giá trị từ 1 thành 0 một cách nguyên tử.

**Câu 7.** Nếu CAS thất bại do luồng khác đã cập nhật stock, có phải phương thức đặt chỗ phải tuyến tính hóa ngay tại CAS thất bại không?

**Đáp án:** Không. Đó có thể là **lần thử nội bộ**; phương thức tiếp tục đọc lại và thử lại hoặc kết thúc tùy điều kiện.

**Câu 8.** Vì sao hai lần `get_balance` đều tuyến tính hóa được nhưng một phép cộng bên ngoài có thể trả 130 khi tổng thực luôn 100?

**Đáp án:** Vì hai lần đọc có thể xảy ra ở **hai thời điểm logic khác nhau**, trước và sau một chuyển khoản. Muốn tổng nhất quán phải có API snapshot/tổng nguyên tử.

**Câu 9.** Điểm tuyến tính hóa của `transfer(A,B,q)` với mutex có nhất thiết là dòng trừ A không?

**Đáp án:** Không nhất thiết. Có thể chọn một **điểm logic phù hợp trong đoạn găng** khi toàn bộ thao tác được nhìn như một bước; không lời gọi cùng giao thức nào được quan sát trạng thái trung gian.

**Câu 10.** Với đồ thị có bảng `edges/out/in`, tại sao không chỉ khóa riêng `out[u]` khi thêm cung?

**Đáp án:** Còn phải giữ `edges[e]` và `in[v]` cùng phiên bản hợp lệ. Khóa chỉ một phía có thể cho reader thấy cung tồn tại ở phía ra nhưng chưa có ở phía vào.

**Câu 11.** Linearizability mạnh hơn sequential consistency ở ràng buộc nào?

**Đáp án:** Nó **giữ thứ tự thời gian thực** của các lời gọi không chồng lấp, ngoài việc có một lịch tuần tự khớp đặc tả.

**Câu 12.** Một queue dùng mutex có thể tuyến tính hóa được nhưng không lock-free không?

**Đáp án:** **Có.** Mutex cho tính đúng đắn nhưng một luồng bị dừng khi giữ lock có thể chặn các luồng khác; lock-free là bảo đảm tiến triển khác.

**Câu 13.** Một `put_if_absent` bảo đảm chỉ một giá trị được công bố. Có suy ra callback tạo giá trị chắc chắn chạy đúng một lần không?

**Đáp án:** Không. Cần đọc hợp đồng thư viện về **số lần gọi callback** khi có tranh chấp/retry, nhất là nếu callback có tác dụng phụ.

**Câu 14.** Một lịch kiểm tra tuyến tính hóa cho stack gồm 2 thao tác: `push(X)` bắt đầu lúc 1 trả lúc 4, `pop()` bắt đầu lúc 3 trả X lúc 5. Có thể tuyến tính hóa được không?

**Đáp án:** Có. Hai lời gọi chồng lấp, có thể đặt push trước pop, đúng đặc tả LIFO.

**Câu 15.** Nếu một thao tác cầm lock rồi gặp `MemoryError` giữa hai lần ghi, lock có tự khôi phục trạng thái trước thao tác không?

**Đáp án:** Không. Cần chính sách rollback, chuẩn bị dữ liệu trước khi công bố hoặc tạo trạng thái mới hợp lệ rồi publish; mutex không tự có failure atomicity.

**Câu 16.** Vì sao chỉ đo thời gian thực thi `O(1)` của CAS không đủ để dự đoán độ trễ `reserve_one`?

**Đáp án:** Vì lời gọi có thể **retry nhiều lần** khi tranh chấp; thêm thời gian chờ/lập lịch, nên số lần thử và thời gian phản hồi không được cận của **một lần CAS** bảo đảm.

**Câu 17.** Kiểm tra trạng thái cuối của queue có đủ chứng minh lịch lời gọi tuyến tính hóa được không?

**Đáp án:** Không. Cần xét **thứ tự invocation–response, giá trị dequeue trả về và thứ tự thời gian thực**. Trạng thái cuối đúng có thể che lịch trả kết quả sai.

**Ghi nhớ:** **Thao tác nguyên tử** là đơn vị mà người dùng có thể quan sát như một bước; **điểm tuyến tính hóa** là thời điểm logic trong khoảng invocation–response giải thích hiệu ứng của bước ấy. Muốn chứng minh **linearizability**, phải tìm được một thứ tự tuần tự phù hợp đặc tả **và** tôn trọng các lời gọi không chồng lấp theo thời gian thực. Mutex, CAS, queue, stack, hash map, snapshot và đồ thị nhiều chỉ mục có thể có những điểm tuyến tính hóa khác nhau, kể cả cho lời gọi thất bại. **Đúng từng phương thức không tự làm đúng một chuỗi phương thức ghép**; hãy đưa bất biến nghiệp vụ vào ranh giới API nguyên tử. Cuối cùng, phân biệt **tính đúng của lịch sử**, **khả năng tiến triển**, **thời gian chờ**, **failure atomicity** và **độ bền dữ liệu**.
