# Cấu trúc an toàn luồng và các thao tác có thể xen kẽ

## 1. Một cấu trúc đúng khi chạy một luồng chưa chắc đúng khi chạy nhiều luồng

Giả sử nền tảng học tập còn **một chỗ trống** cho một buổi thực hành. Hai người dùng đăng ký gần như đồng thời. Nếu hai luồng cùng đọc “còn một chỗ”, rồi cả hai cùng giảm số chỗ còn lại, hệ thống có thể xác nhận **hai đăng ký cho một chỗ**.

Một chương trình tuần tự thường thực hiện:

```text
Kiểm tra còn chỗ → giảm số chỗ → xác nhận đăng ký
```

Khi nhiều luồng cùng truy cập **dữ liệu có thể thay đổi**, thứ tự thực tế có thể xen kẽ:

```text
Luồng T1                         Luồng T2
--------                         --------
đọc số chỗ = 1
                                 đọc số chỗ = 1
kiểm tra 1 >= 1: ĐÚNG
                                 kiểm tra 1 >= 1: ĐÚNG
giảm số chỗ: 1 → 0
                                 giảm số chỗ: 0 → -1
xác nhận                        xác nhận
```

Mỗi luồng riêng lẻ dường như đã làm đúng thứ tự. **Sai lầm nằm ở việc ba bước không được thực hiện như một thao tác nguyên tử đối với các luồng khác.**

Trong chương **Truy cập đồng thời**, ta cần hiểu một **cấu trúc an toàn luồng (thread-safe data structure)** thực sự bảo vệ điều gì, các thao tác nào có thể xen kẽ, và khi nào phải đồng bộ **cả một chuỗi thao tác** thay vì chỉ chọn một collection được quảng cáo là an toàn luồng.

**Kết quả mong đợi:** sau bài này, bạn có thể phân tích một lịch xen kẽ, phát hiện lost update và check-then-act, xác định ranh giới nguyên tử, sử dụng lock/condition/queue phù hợp, giữ nhất quán các chỉ mục và đánh đổi tính đúng đắn với chi phí chờ đợi.

## 2. Luồng, thao tác và lịch xen kẽ

Một **luồng (thread)** là một luồng thực thi trong tiến trình. Nhiều luồng có thể chia sẻ các đối tượng trong cùng không gian địa chỉ. Trên một máy nhiều lõi, chúng có thể chạy **song song**; ngay cả khi không chạy song song vật lý, bộ lập lịch vẫn có thể **chuyển qua lại** giữa các luồng.

Với hai luồng T1 và T2, một lịch thực thi có thể là:

```text
T1: đọc x
T2: đọc x
T2: tính x + 1
T1: tính x + 1
T1: ghi x
T2: ghi x
```

Đây là **interleaving (xen kẽ)**: các bước của hai thao tác được trộn vào nhau, nhưng thứ tự nội bộ của mỗi thao tác vẫn được giữ theo những bảo đảm của môi trường thực thi.

**Không nên giả định** rằng một dòng mã nguồn là một bước không thể chia nhỏ. Ví dụ `x += 1` thường có thể được hiểu về mặt logic như **đọc → tính → ghi**, chứ không tự tạo một giao dịch nguyên tử.

Hai tình huống cần phân biệt:

- **Truy cập chỉ đọc:** nếu cấu trúc và mọi đối tượng được đọc thực sự bất biến trong suốt quá trình, nhiều luồng đọc đồng thời thường dễ xử lý hơn.
- **Truy cập có ghi:** nếu có thao tác thêm/xóa/sửa, phải xét liệu một lần đọc có thể thấy trạng thái đang cập nhật dở hay không.

Một chương trình **không có data race ở cấp bộ nhớ** vẫn có thể mắc **race condition ở cấp logic** nếu nhiều thao tác đơn lẻ an toàn nhưng được ghép sai cách. Ngược lại, ở những ngôn ngữ có mô hình bộ nhớ chặt chẽ, truy cập xung đột thiếu đồng bộ còn có thể vi phạm chính quy tắc về sự nhìn thấy và thứ tự bộ nhớ.

## 3. “An toàn luồng” bảo đảm đến mức nào?

Khi nói một `queue`, `map` hoặc `set` an toàn luồng, phải trả lời chính xác:

> Những **thao tác công khai** nào có thể được gọi đồng thời mà vẫn duy trì bất biến và trả kết quả theo hợp đồng của cấu trúc?

Ví dụ, một `ConcurrentMap` có thể bảo đảm mỗi lần `get(k)` và `put(k,v)` riêng lẻ là an toàn. Điều đó **không** tự bảo đảm đoạn:

```text
if map.get(k) == NONE:
    map.put(k, make_value())
```

chỉ tạo một giá trị khi có hai luồng cùng thực hiện. Cả hai có thể cùng thấy khóa đang vắng, cùng gọi `make_value()` và cùng ghi.

Hãy phân biệt các cấp bảo đảm:

| Cấp độ | Ý nghĩa | Ví dụ rủi ro còn lại |
| --- | --- | --- |
| Cấu trúc không bị hỏng | Các trường nội bộ không rơi vào trạng thái bất hợp lệ | Hai luồng vẫn có thể ghi đè kết quả nhau |
| Thao tác đơn lẻ nguyên tử | Một lệnh `get`, `put`, `enqueue` có hiệu ứng trọn vẹn theo API | Chuỗi `get → kiểm tra → put` vẫn xen kẽ |
| **Tuyến tính hóa được (linearizable)** | Mỗi thao tác có thể xem như xảy ra tại một điểm tức thời giữa lúc gọi và trả kết quả, tôn trọng thứ tự thời gian thực của thao tác không chồng lấp | Một **giao dịch gồm nhiều thao tác** vẫn cần bảo vệ riêng |
| Giao dịch nhiều bước | Một nhóm đọc/ghi liên quan được xem là một đơn vị | Phải quy định khóa, rollback, cô lập và xử lý lỗi |

**Linearizability** là một thuộc tính của **lịch sử lời gọi và kết quả theo đặc tả trừu tượng**, không phải đồng nghĩa “mọi phương thức có lock”. Có thể xây cấu trúc tuyến tính hóa được bằng lock, cơ chế nguyên tử hoặc thuật toán không dùng mutex thông thường.

**Thread-safe** cũng không tự có nghĩa là **lock-free**, **wait-free**, công bằng hay nhanh dưới tải. Một cấu trúc dùng một mutex duy nhất có thể rất đúng nhưng khiến nhiều luồng phải chờ.

## 4. Race condition số 1: mất lần cập nhật (lost update)

Giả sử `counter=0`. Hai luồng cùng tăng bộ đếm một lần:

| Bước | T1 | T2 | Giá trị trong bộ nhớ |
| --- | --- | --- | ---: |
| 1 | Đọc `counter=0` | | 0 |
| 2 | | Đọc `counter=0` | 0 |
| 3 | Tính `0+1=1` | | 0 |
| 4 | | Tính `0+1=1` | 0 |
| 5 | Ghi 1 | | 1 |
| 6 | | Ghi 1 | 1 |

Sau **hai lần tăng**, kết quả là **1 thay vì 2**. Một lần cập nhật đã bị mất.

```python
# Không dùng để bảo đảm đúng khi nhiều luồng chạy đồng thời.
counter = 0

def increase_unsafe():
    global counter
    counter += 1  # Không nên coi là giao dịch nguyên tử đa luồng.
```

Lỗi này không thể giải quyết đơn giản bằng cách “tăng tốc CPU” hoặc “cho các luồng chạy cách xa nhau một chút”. Tính đúng đắn phải đúng đối với **mọi lịch xen kẽ hợp lệ**, không chỉ lịch tình cờ xảy ra trong lần thử.

### Bảo vệ bằng khóa loại trừ tương hỗ

```python
from threading import Lock

class SafeCounter:
    def __init__(self):
        self._value = 0
        self._lock = Lock()

    def increase(self):
        with self._lock:
            self._value += 1
            return self._value

    def read(self):
        with self._lock:
            return self._value
```

`with self._lock` bảo đảm chỉ một luồng tại một thời điểm vào đoạn cập nhật của **chính đối tượng counter ấy**. Cả `increase` **và** `read` đều đồng bộ theo cùng khóa để người đọc không dựa vào một hợp đồng không nhất quán.

Không được tùy ý truy cập `obj._value` từ mã khác rồi cho rằng lớp vẫn an toàn luồng; an toàn luồng ở đây là **hợp đồng dùng qua các phương thức công khai**.

## 5. Race condition số 2: kiểm tra trước, hành động sau

Một mẫu rất phổ biến là **check-then-act** hay **TOCTOU (time-of-check to time-of-use)**:

```text
if item chưa có trong set:
    thêm item vào set
    phát một sự kiện "đã đăng ký"
```

Kể cả khi `contains` và `add` đều an toàn riêng lẻ, hai luồng có thể cùng thấy mục chưa tồn tại. Kết quả:

- Set cuối cùng vẫn chỉ có **một** mục.
- Nhưng ứng dụng có thể **phát hai email** hoặc trừ tiền hai lần nếu hành động phụ xảy ra bên ngoài thao tác nguyên tử.

Tương tự với kho hàng, không thể kiểm tra `stock >= quantity` rồi **mở khóa trước khi trừ tồn kho**.

Một ví dụ minh họa xen kẽ một cách có chủ đích:

```python
from threading import Barrier, Thread

remaining = 1
gate = Barrier(2)

def reserve_unsafe():
    global remaining
    if remaining >= 1:
        gate.wait()    # Buộc cả hai luồng vượt qua bước kiểm tra.
        remaining -= 1

threads = [Thread(target=reserve_unsafe) for _ in range(2)]
for t in threads:
    t.start()
for t in threads:
    t.join()

print(remaining)  # -1: hai lần trừ đã vượt qua cùng điều kiện.
```

`Barrier` ở đây chỉ là công cụ **tái hiện lỗi** trong môi trường thử nghiệm; nó **không** phải biện pháp làm phép đặt chỗ trở nên an toàn. Cách đúng là bảo vệ **kiểm tra và cập nhật** bằng cùng một cơ chế đồng bộ.

## 6. Python: một API đặt chỗ thực hiện nguyên tử

Lớp sau biểu diễn kho hàng. Đơn vị nghiệp vụ cần nguyên tử là **kiểm tra đủ hàng rồi trừ**, không phải riêng phép đọc hay phép ghi.

```python
from concurrent.futures import ThreadPoolExecutor
from threading import Lock


class KhoAnToan:
    def __init__(self, initial):
        if any(type(q) is not int or q < 0 for q in initial.values()):
            raise ValueError("Số lượng ban đầu phải là số nguyên không âm")
        self._items = dict(initial)  # Sao chép, không giữ dict đầu vào.
        self._lock = Lock()

    def dat_cho(self, sku, quantity=1):
        if type(quantity) is not int or quantity <= 0:
            raise ValueError("Số lượng đặt phải là số nguyên dương")
        with self._lock:
            if sku not in self._items:
                raise KeyError(sku)
            if self._items[sku] < quantity:
                return False
            self._items[sku] -= quantity
            return True

    def nhap_them(self, sku, quantity):
        if type(quantity) is not int or quantity <= 0:
            raise ValueError("Số lượng nhập phải là số nguyên dương")
        with self._lock:
            if sku not in self._items:
                raise KeyError(sku)
            self._items[sku] += quantity

    def snapshot(self):
        # Trả bản sao, tránh cho bên ngoài sửa trực tiếp dict nội bộ.
        with self._lock:
            return dict(self._items)


kho = KhoAnToan({"ve-01": 1})
with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(
        lambda _: kho.dat_cho("ve-01"), range(2)
    ))

print(sum(results))             # 1: chính xác một lần thành công
print(kho.snapshot()["ve-01"])  # 0: không âm
```

**Điểm quan trọng:**

- Hai luồng có thể gọi `dat_cho` cùng lúc, nhưng chỉ một luồng thực hiện **toàn bộ** bước kiểm tra–trừ trong `with self._lock`.
- `snapshot` cũng lấy cùng khóa. Nếu trả trực tiếp `self._items`, bên gọi có thể sửa dữ liệu mà không qua lock và phá bất biến.
- Số lần đặt chỗ thành công bằng 1; **không bảo đảm luồng nào thắng**. Khóa loại trừ tương hỗ thông thường không tự cam kết FIFO/công bằng.
- Khóa chỉ bảo vệ **trạng thái của đối tượng này trong cùng tiến trình**, không tự đồng bộ với bản sao của kho trong tiến trình khác hoặc cơ sở dữ liệu ở máy khác.

Đây là ví dụ tập trung vào an toàn luồng trong bộ nhớ; giao dịch giữa nhiều dịch vụ, lưu bền vững và chống đặt chỗ trùng ở cấp hệ thống cần cơ chế nhất quán tương ứng.

## 7. Quy tắc đặt ranh giới nguyên tử

Để đánh giá một thao tác, hãy hỏi:

1. **Bất biến là gì?** Ví dụ `remaining >= 0` hoặc “mỗi edge ID có đúng hai mục chỉ mục tương ứng”.
2. **Đầu vào nào cùng tham gia quyết định?** Với đặt chỗ: lượng hàng đang có và lượng hàng yêu cầu.
3. **Dữ liệu nào phải thay đổi cùng nhau?** Với đồ thị có hướng: bảng cung, chỉ mục cung ra và chỉ mục cung vào.
4. **Đọc nào cần cùng một thời điểm logic?** Khi xuất báo cáo tồn kho nhiều SKU, có cần một snapshot của tất cả SKU không?
5. **Ai được phép đọc/ghi dữ liệu?** Có đường truy cập nào bỏ qua khóa hoặc trả đối tượng có thể thay đổi bên trong không?

Một cách nhìn là coi mỗi API như một **giao dịch nhỏ trên bộ nhớ**:

```text
lock
    xác thực trạng thái liên quan
    quyết định
    thay đổi tất cả trường liên quan
    tạo giá trị trả về
unlock
```

Giữ đoạn găng (critical section) **đủ rộng để bao trọn bất biến** nhưng tránh đưa vào đó những công việc không cần thiết như truy vấn mạng, gửi email hoặc chờ người dùng. Gọi mã bên ngoài khi đang giữ lock có thể gây chờ lâu, reentrancy hoặc deadlock.

**Atomicity không phải rollback:** nếu việc cập nhật ba cấu trúc bị lỗi cấp phát sau khi đã sửa hai cấu trúc, mutex có thể ngăn luồng khác quan sát trạng thái giữa chừng, nhưng không tự khôi phục trạng thái trước lỗi. Nếu cần an toàn trước thất bại, phải có chính sách rollback, xây trạng thái tạm hoặc giao dịch phù hợp.

## 8. Nhìn thấy bộ nhớ và thứ tự thực thi

Đồng bộ không chỉ là “hai luồng không cùng ghi”. Nó còn liên quan đến việc **luồng đọc có nhìn thấy các thay đổi đã công bố không**.

Ví dụ một luồng khởi tạo đối tượng gồm hai trường `a,b` rồi đặt cờ `ready=True`, luồng khác thấy `ready` và đọc `a,b`. Nếu không có cơ chế đồng bộ đúng của ngôn ngữ và runtime, không nên tự suy ra rằng mọi trường đã được công bố an toàn chỉ từ một cờ Boolean thông thường.

Khái niệm quan trọng là **happens-before**: một quan hệ thứ tự được bảo đảm bởi mô hình bộ nhớ, chẳng hạn thông qua thao tác khóa, release/acquire hoặc primitive đồng bộ phù hợp. Quan hệ này giúp xác định khi nào những ghi trước đó phải nhìn thấy được ở luồng đọc sau.

Những điều cần nhớ:

- **Mutex/lock** thường vừa cung cấp loại trừ tương hỗ vừa có quy tắc công bố bộ nhớ theo runtime.
- **Atomic variable** có thể hỗ trợ đọc/ghi hoặc compare-and-swap nguyên tử cho **một biến**, nhưng không tự duy trì bất biến trải trên nhiều trường.
- **`volatile`** trong một số ngôn ngữ có thể cung cấp bảo đảm hiển thị/thứ tự, nhưng không biến chuỗi `read → increment → write` thành nguyên tử. Cần xét đúng mô hình bộ nhớ ngôn ngữ cụ thể.
- **GIL của một phiên bản trình thông dịch Python** không phải hợp đồng tổng quát rằng nhiều phương thức hay một dòng Python ghép là nguyên tử. Không dựa vào chi tiết triển khai GIL để bảo vệ tính đúng đắn, nhất là khi có extension, I/O, runtime hoặc chế độ thực thi khác.

Không nên trộn các cam kết của **Java, C++, Python và hệ quản trị cơ sở dữ liệu** thành một quy tắc chung; cách công bố bộ nhớ và primitive có thể khác nhau.

## 9. Những cấu trúc và cơ chế đồng bộ thường gặp

| Cơ chế | Cách dùng | Đánh đổi cần xem |
| --- | --- | --- |
| **Mutex/Lock** | Bảo vệ một đoạn găng cập nhật chung | Dễ lý luận; nhiều luồng tranh cùng lock phải chờ |
| **RLock (khóa tái nhập)** | Cùng luồng có thể vào lại một lock qua chuỗi lời gọi | Thuận tiện trong thiết kế gọi lồng nhau, nhưng không sửa lỗi khóa sai thứ tự |
| **Read–write lock** | Cho phép nhiều người đọc cùng lúc, ghi phải độc quyền | Cần chính sách ưu tiên; có thể starvation hoặc chi phí quản lý cao |
| **Khóa phân đoạn (striped/per-bucket)** | Chia map thành nhiều vùng khóa | Ghi độc lập có thể song song; thao tác toàn map khó lấy snapshot nhất quán |
| **Atomic/CAS** | Thay đổi trạng thái nhỏ theo điều kiện | Thuật toán lock-free phức tạp, có retry và vấn đề ABA |
| **Queue an toàn luồng** | Trao đổi dữ liệu producer–consumer | `put/get` an toàn riêng; quy tắc đóng queue, hủy và hoàn thành việc vẫn phải thiết kế |
| **Bất biến/snapshot (immutable)** | Người đọc dùng một phiên bản không bị sửa tại chỗ | Có chi phí sao chép hoặc quản lý nhiều phiên bản |
| **Truyền thông điệp/ownership** | Một chủ sở hữu xử lý thao tác lên trạng thái, luồng khác gửi yêu cầu | Giảm chia sẻ ghi trực tiếp, đổi lại có queue và độ trễ phản hồi |

### Thread-safe khác lock-free và wait-free

- **Thread-safe:** đúng khi các lời gọi đồng thời tuân thủ hợp đồng.
- **Lock-free:** trong một hệ thống còn tiến triển, luôn có **ít nhất một thao tác** có thể hoàn thành sau hữu hạn bước của hệ thống; không có bảo đảm mỗi luồng cụ thể sẽ không bị đói.
- **Wait-free:** **mỗi thao tác** của một luồng hoàn thành sau số bước hữu hạn theo mô hình thuật toán, không phụ thuộc các luồng khác có bị tạm dừng hay không.

Một `queue` dùng mutex có thể thread-safe mà **không** lock-free. Một thuật toán CAS lock-free vẫn có thể khiến một luồng lặp lại nhiều lần vì tranh chấp.

## 10. Queue an toàn luồng và mô hình producer–consumer

Queue là ví dụ tự nhiên vì nhiều luồng có thể **sản xuất** hoặc **tiêu thụ** tác vụ.

Trong Python, `queue.Queue` hỗ trợ phối hợp đa luồng với `put`, `get` và cơ chế chờ khi đầy/rỗng. Không nên tự dùng một `list` rồi liên tục làm:

```text
if len(items) > 0:
    items.pop(0)
```

mà cho rằng `len` và `pop` là một bước nguyên tử. Nếu nhiều consumer cùng kiểm tra, queue có thể đã rỗng khi một consumer thực hiện `pop`.

Ví dụ một producer, một consumer, một tín hiệu kết thúc (sentinel):

```python
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

tasks = Queue(maxsize=2)
STOP = object()  # Một sentinel riêng trong cùng tiến trình.


def producer():
    for value in [10, 20, 30, 40]:
        tasks.put(value)  # Chờ nếu queue đạt giới hạn.
    tasks.put(STOP)


def consumer():
    while True:
        item = tasks.get()  # Chờ nếu queue rỗng.
        try:
            if item is STOP:
                return
            print("Xử lý:", item)
        finally:
            tasks.task_done()  # Báo hoàn tất đúng một lần cho mỗi get.


with ThreadPoolExecutor(max_workers=2) as pool:
    p = pool.submit(producer)
    c = pool.submit(consumer)
    p.result()
    tasks.join()  # Chờ đủ các mục đã put được đánh dấu task_done.
    c.result()
```

Trong ví dụ này, **mỗi mục được lấy khỏi queue một lần**, và `Queue` phối hợp an toàn luồng trong cùng tiến trình. Tuy nhiên, **an toàn của cấu trúc queue không bảo đảm tác vụ nghiệp vụ xử lý “đúng một lần” khi có lỗi/crash**. Nếu cần thực thi chính xác một lần qua tiến trình hoặc mạng, cần thêm cơ chế xác nhận, idempotency, lưu bền vững và phục hồi.

Một vài lưu ý:

- Với **n consumer**, mỗi consumer thường cần tín hiệu dừng hoặc một giao thức đóng queue rõ ràng; gửi một sentinel cho một consumer chưa đủ cho n consumer.
- `Queue.empty()` và `Queue.qsize()` chỉ phản ánh trạng thái ở một thời điểm; sau khi gọi, luồng khác có thể thay đổi queue ngay. Không dùng `if not q.empty(): q.get()` làm giao thức không chặn; thay vào đó dùng `get_nowait()` và xử lý ngoại lệ `Empty`, hoặc dùng `get(timeout=...)`.
- `task_done()` và `join()` theo dõi **số tác vụ chưa báo hoàn tất**, khác với việc queue đang rỗng. Gọi `task_done` thiếu hoặc thừa có thể khiến chương trình sai hoặc chờ vô hạn.
- Nếu worker có thể ném ngoại lệ, quy trình cần chính sách thông báo lỗi, hủy công việc và kết thúc thread; ví dụ ngắn chỉ minh họa đồng bộ queue, chưa phải hàng đợi sản xuất đầy đủ.

## 11. Condition: chờ điều kiện, không chờ một lần thông báo

Một **condition variable** kết hợp điều kiện logic với lock. Nó cho phép luồng chờ **tới khi điều kiện được kiểm tra lại là đúng**.

Ví dụ queue có giới hạn dung lượng, minh họa tinh gọn:

```python
from collections import deque
from threading import Condition


class BoundedQueue:
    def __init__(self, capacity):
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("capacity phải dương")
        self._capacity = capacity
        self._items = deque()
        self._cv = Condition()

    def put(self, value):
        with self._cv:
            while len(self._items) >= self._capacity:
                self._cv.wait()    # Nhả lock khi chờ; lấy lại khi thức dậy.
            self._items.append(value)
            self._cv.notify_all()  # Có thể có consumer đang chờ.

    def get(self):
        with self._cv:
            while not self._items:
                self._cv.wait()
            item = self._items.popleft()
            self._cv.notify_all()  # Có thể có producer đang chờ.
            return item
```

Tại sao dùng **`while` chứ không dùng `if`**?

1. Một luồng được đánh thức **không có nghĩa** điều kiện vẫn đúng khi luồng ấy giành lại lock.
2. Có thể có nhiều consumer cùng được đánh thức, nhưng chỉ một consumer lấy phần tử cuối cùng.
3. Nhiều API condition cho phép **thức dậy không do thông báo trực tiếp (spurious wakeup)** hoặc yêu cầu lập trình viên kiểm tra lại điều kiện.

`wait()` phải được gọi trong quy trình sở hữu lock/condition thích hợp. Nó **tạm nhả khóa khi chờ**, nếu không producer sẽ không thể vào để thêm dữ liệu.

Mã này cố tình tối giản: chưa có timeout, đóng queue, hủy luồng, xử lý lỗi hay chính sách công bằng. Khi chỉ cần producer–consumer trong Python, hãy cân nhắc `queue.Queue` thay vì tự tái tạo đầy đủ những chi tiết ấy.

## 12. Deadlock, starvation và thứ tự lấy nhiều khóa

### Deadlock: hai luồng chờ nhau

Giả sử có hai lock `L_A` và `L_B`:

```text
T1: giữ L_A                  T2: giữ L_B
T1: chờ lấy L_B              T2: chờ lấy L_A
       └──────────── chờ vòng tròn ────────────┘
```

Không luồng nào có thể tiến lên nếu cả hai cùng giữ khóa hiện tại và chờ khóa còn lại.

Một biện pháp phổ biến là quy định **thứ tự lấy khóa toàn cục**:

```text
Mọi luồng cần đồng thời L_A và L_B đều:
    lấy L_A
    lấy L_B
    thao tác
    nhả theo thứ tự ngược
```

Khi có nhiều khóa theo ID đối tượng, có thể sắp các ID theo một thứ tự nhất quán trước khi lấy. Không được dùng thứ tự khác nhau ở các đường mã.

**Nhưng:** chỉ có thứ tự khóa vẫn chưa giải quyết mọi lỗi. Một callback thực hiện khi đang giữ lock có thể cố lấy khóa khác và tạo chu trình khóa nằm ngoài thiết kế ban đầu. Khóa tái nhập `RLock` chỉ cho phép **cùng luồng** lấy lại cùng khóa; nó **không** chữa deadlock giữa hai luồng lấy hai khóa theo thứ tự đối nghịch.

### Starvation và công bằng

- **Starvation:** một luồng cứ bị những luồng khác vượt qua, không hoàn tất dù hệ thống vẫn tiến triển.
- **Lock convoy:** nhiều luồng cùng chờ một lock nóng, làm giảm thông lượng.
- **Livelock:** các luồng liên tục thay đổi trạng thái hoặc thử lại nhưng không hoàn thành công việc có ích.
- **Priority inversion:** luồng ưu tiên cao chờ tài nguyên do luồng ưu tiên thấp giữ, có thể bị các luồng khác ảnh hưởng.

Một lock hoặc một queue thread-safe **không mặc nhiên bảo đảm FIFO hay không starvation**. Nếu ứng dụng yêu cầu tính công bằng, phải chọn primitive và cơ chế xếp lịch đáp ứng hợp đồng ấy.

## 13. Ví dụ nâng cao: một đồ thị có hướng với hai chỉ mục đồng bộ

Giả sử một cấu trúc đồ thị lưu đồng thời:

```text
vertices         : tập ID đỉnh
edges[eid]       : (source, target)
out_ids[source]  : tập các edge_id cung đi ra
in_ids[target]   : tập các edge_id cung đi vào
```

Với một cung `e=(u→v)`, bất biến là:

\[
e\in out\_ids[u]\quad\text{và}\quad e\in in\_ids[v].
\]

Nếu một luồng thêm e mà luồng khác chạy BFS hoặc truy vấn cung vào **giữa hai lần cập nhật**, nó có thể quan sát hai chỉ mục không tương đương nhau.

Một cách triển khai đơn giản và dễ kiểm chứng là dùng **một khóa chung** để bảo vệ cả bảng đỉnh, bảng cạnh và hai chỉ mục. Dưới đây là phiên bản trong bộ nhớ để minh họa; mỗi thao tác thay đổi được thực hiện trong một đoạn găng.

```python
from threading import RLock


class DoThiDongThoi:
    def __init__(self):
        self._lock = RLock()
        self._vertices = set()
        self._edges = {}    # eid -> (u, v)
        self._out = {}      # u -> set(edge_id)
        self._incoming = {} # v -> set(edge_id)
        self._next_id = 0

    def add_vertex(self, u):
        if not isinstance(u, str) or not u:
            raise ValueError("ID đỉnh phải là chuỗi không rỗng")
        with self._lock:
            if u in self._vertices:
                raise ValueError("Đỉnh đã tồn tại")
            self._vertices.add(u)
            self._out[u] = set()
            self._incoming[u] = set()

    def add_edge(self, u, v):
        with self._lock:
            if u not in self._vertices or v not in self._vertices:
                raise KeyError("Đầu mút không tồn tại")
            eid = self._next_id
            self._next_id += 1
            self._edges[eid] = (u, v)
            self._out[u].add(eid)
            self._incoming[v].add(eid)
            return eid

    def _remove_edge_locked(self, eid):
        # Chỉ gọi trong đoạn găng đã giữ self._lock.
        u, v = self._edges[eid]
        self._out[u].remove(eid)
        self._incoming[v].remove(eid)
        del self._edges[eid]

    def remove_edge(self, eid):
        with self._lock:
            self._remove_edge_locked(eid)

    def remove_vertex(self, u):
        with self._lock:
            if u not in self._vertices:
                raise KeyError(u)
            # Khuyên u->u xuất hiện ở cả out/in: hợp ID tránh xóa hai lần.
            related = self._out[u] | self._incoming[u]
            for eid in related:
                self._remove_edge_locked(eid)
            del self._out[u]
            del self._incoming[u]
            self._vertices.remove(u)

    def snapshot(self):
        # Bản sao bất biến chỉ gồm ID và các cặp str;
        # có thể đọc sau khi đã nhả khóa.
        with self._lock:
            return (
                frozenset(self._vertices),
                tuple(
                    (eid, u, v)
                    for eid, (u, v) in self._edges.items()
                ),
            )

    def check_invariants(self):
        with self._lock:
            assert self._vertices == set(self._out)
            assert self._vertices == set(self._incoming)
            assert sum(map(len, self._out.values())) == len(self._edges)
            assert sum(map(len, self._incoming.values())) == len(self._edges)
            for eid, (u, v) in self._edges.items():
                assert u in self._vertices and v in self._vertices
                assert eid in self._out[u]
                assert eid in self._incoming[v]
            return True


g = DoThiDongThoi()
for u in "ABC":
    g.add_vertex(u)

e0 = g.add_edge("A", "B")
e1 = g.add_edge("A", "B")  # Cung song song, ID khác nhau.
e2 = g.add_edge("B", "B")  # Khuyên.
e3 = g.add_edge("B", "C")
before = g.snapshot()
assert len(before[0]) == 3 and len(before[1]) == 4

g.remove_vertex("B")
after = g.snapshot()
assert len(after[0]) == 2 and len(after[1]) == 0
assert g.check_invariants()
assert len(before[1]) == 4  # Snapshot cũ không đổi.
```

**Cách đọc ví dụ:**

- Một cung xuất hiện **một lần trong bảng edges**, một ID trong chỉ mục `out` và một ID trong `incoming`.
- `remove_vertex("B")` lấy hợp các ID vào/ra, nên khuyên B→B không bị xóa hai lần. Cung song song e0/e1 vẫn phân biệt.
- `snapshot()` sao chép toàn bộ tập đỉnh và bảng cung khi đang giữ khóa; sau khi nhả khóa, các giá trị `frozenset`, `tuple`, `str`, `int` không bị sửa tại chỗ qua API này.
- Người đọc có thể xây danh sách kề và chạy BFS từ snapshot **ngoài lock**, tránh giữ khóa chung xuyên suốt toàn bộ thuật toán.

**Giới hạn quan trọng:** đây là mô hình đơn tiến trình, dữ liệu nội bộ không được sửa trực tiếp, và cập nhật không tự có rollback nếu lỗi tài nguyên xảy ra ở giữa. Hàm `check_invariants` dùng `assert` cho phát triển; trong Python, các assert có thể bị bỏ qua ở chế độ tối ưu hóa. Nếu cần bảo đảm bền vững hoặc nhiều tiến trình, phải dùng công cụ giao dịch/đồng bộ phù hợp.

### Đọc snapshot mà không cầm khóa lâu

Một phép duyệt dài có thể làm mọi writer chờ nếu giữ khóa suốt BFS. Thay vào đó:

1. Giữ khóa trong một khoảng ngắn **đủ để sao chép trạng thái nhất quán**.
2. Nhả khóa.
3. Dựng danh sách kề từ snapshot và chạy BFS/DFS ngoài khóa.

Bản snapshot là **một phiên bản hợp lệ ở thời điểm lấy**, nhưng không nhất thiết là **trạng thái mới nhất** khi BFS kết thúc.

Nếu sao chép toàn đồ thị tốn `O(n+m)` thì khoảng giữ khóa vẫn có thể đáng kể với dữ liệu lớn. Có thể cân nhắc **immutable snapshots, copy-on-write, versioning hoặc khóa đọc–ghi** để tối ưu theo yêu cầu workload; điều đó làm thiết kế phức tạp hơn, không miễn phí.

## 14. Chọn mức khóa (lock granularity) và đánh đổi hiệu năng

Có thể chọn:

- **Một khóa toàn cấu trúc (coarse-grained):** đơn giản, dễ xác định bất biến và điểm tuyến tính hóa, nhưng ít song song khi có nhiều ghi.
- **Một khóa cho mỗi bucket/đỉnh (fine-grained):** hai thao tác trên vùng độc lập có thể chạy đồng thời, nhưng thêm/xóa cạnh nối hai đỉnh phải lấy nhiều khóa **theo thứ tự nhất quán**.
- **Read–write lock:** hợp với nhiều đọc ít ghi khi runtime có primitive phù hợp; snapshot nhiều vùng vẫn phải giữ một phiên bản logic.
- **Immutable/copy-on-write:** người đọc không cần giữ lock suốt khi duyệt snapshot; writer tốn sao chép hoặc quản lý phiên bản.
- **Lock-free/atomic:** có thể giảm một số hình thức chờ nhưng yêu cầu thiết kế và chứng minh rất cẩn thận, nhất là quản lý vòng đời đối tượng và bộ nhớ.

### Một số chi phí tiệm cận

| Thao tác | Chi phí bản thân cấu trúc, không tranh chấp | Điều thay đổi khi đồng thời |
| --- | --- | --- |
| Đọc/cập nhật bộ đếm có lock | `O(1)` | Thêm thời gian lấy khóa và chờ luồng khác |
| `put/get` queue thread-safe | Thường `O(1)` cho bước thao tác hàng đợi phù hợp | `put` có thể **chờ không giới hạn** khi đầy, `get` khi rỗng |
| Thêm một cung vào bảng hash và hai set | `O(1)` kỳ vọng/phân bổ | Tranh lock và các thao tác sửa chỉ mục cần cùng phạm vi |
| Xóa đỉnh có p cung ra và q cung vào bằng hai chỉ mục | `O(p+q)` kỳ vọng với hash set | Phải giữ nhất quán trong suốt thao tác, có thể khóa lâu |
| Sao chép snapshot đỉnh/cung | `O(n+m)` | Writer chờ khóa hoặc phải dùng thiết kế snapshot phức tạp hơn |
| BFS/DFS trên danh sách kề snapshot | `O(n+m)` cho duyệt toàn đồ thị | Không tranh khóa ghi nếu snapshot đã độc lập |

**Không nên viết “thao tác thread-safe là `O(1)` thời gian thực”** chỉ vì phần tính toán bên trong ngắn. Big-O thường đo **số bước làm việc**, chưa tính thời gian một luồng bị treo, chờ lock, bị preempt hay chờ điều kiện.

Lựa chọn phụ thuộc **tỷ lệ đọc/ghi, số luồng, độ nóng của khóa, kích thước dữ liệu và yêu cầu nhất quán**. Cấu trúc nhanh nhất khi chỉ chạy một luồng không nhất thiết nhanh nhất khi bị tranh chấp.

## 15. Atomic/CAS, ABA và các cập nhật phức hợp

**Compare-and-swap (CAS)** về ý tưởng thực hiện:

```text
CAS(location, expected, new_value):
    nếu location vẫn bằng expected:
        ghi new_value một cách nguyên tử
        trả THÀNH CÔNG
    nếu không:
        không ghi
        trả THẤT BẠI
```

CAS hữu ích cho một số thuật toán concurrent stack, queue hoặc bảng băm. Nhưng **một CAS trên một biến** không tự cập nhật nguyên tử **nhiều biến liên quan**.

### Vấn đề ABA

Giả sử một luồng đọc trạng thái con trỏ là A, tạm dừng. Luồng khác thay A→B rồi B→A. Khi luồng đầu chạy lại, nó thấy giá trị **vẫn là A** và có thể tưởng chưa có gì thay đổi.

```text
Thời điểm T1 đọc: A
T2 thay:         A → B → A
T1 kiểm tra:     vẫn là A, nhưng trạng thái đã đổi hai lần
```

Một số thiết kế dùng **đếm phiên bản, con trỏ gắn tag hoặc cơ chế quản lý vòng đời đối tượng** để xử lý. Cách giải cụ thể còn phụ thuộc ngôn ngữ, trình cấp phát, bộ nhớ và thuật toán.

**Không nên tự cài một cấu trúc lock-free chỉ bằng cách đổi mutex thành vài biến Boolean.** Đúng đắn còn liên quan đến memory ordering, reclaim bộ nhớ, ABA, tiến triển dưới tranh chấp và chứng minh linearizability.

## 16. Kiểm thử đồng thời: tìm lịch xen kẽ xấu thay vì chỉ chạy nhiều lần

Một chương trình concurrency có thể vượt qua hàng nghìn lần chạy thử mà vẫn có race condition hiếm. Vì vậy, kiểm thử nên kết hợp:

1. **Bất biến sau thao tác:** tồn kho không âm, tổng tiền không tự sinh ra, mỗi edge ID có đúng các chỉ mục tương ứng.
2. **Tạo lịch xen kẽ có chủ đích:** dùng `Barrier` hoặc cơ chế test để buộc hai luồng cùng vượt qua một bước kiểm tra trước cập nhật.
3. **Tải cao và đa dạng:** nhiều producer/consumer, số luồng khác nhau, dữ liệu có khóa nóng, queue đầy/rỗng.
4. **Timeout và khả năng tiến triển:** kiểm tra deadlock, chờ vô hạn, starvation; không chỉ đúng kết quả cuối.
5. **Snapshot giữa các cập nhật:** đảm bảo một lần đọc được một trạng thái logic, không phải nửa mới nửa cũ.
6. **Mô hình tuần tự làm chuẩn:** đối chiếu kết quả thao tác với một chuỗi thực thi tuần tự hợp lệ theo đặc tả.
7. **Công cụ chuyên dụng:** với ngôn ngữ/hệ sinh thái hỗ trợ, dùng race detector, stress test, model checker hoặc kiểm tra linearizability phù hợp.

### Ví dụ kiểm tra một cấu trúc chỗ trống

Nếu ban đầu có `k` chỗ và `p` yêu cầu đặt mỗi yêu cầu một chỗ, tất cả cùng chạy qua `KhoAnToan.dat_cho`, sau khi kết thúc phải có:

\[
successes=\min(k,p),
\qquad
remaining=k-successes
\]

khi không có thao tác nhập thêm hoặc hủy yêu cầu và mọi lời gọi đều hoàn thành bình thường.

Các kết quả `True/False` có thể xuất hiện theo thứ tự khác nhau giữa các lần chạy; **bất biến tổng** mới là tiêu chí đúng. Ngoài bất biến tổng, cần xác nhận không có lời gọi thành công nào bị thực hiện **hai lần** do logic retry.

**Giới hạn của bài:** việc tự xây một bài kiểm thử hữu hạn không phải bằng chứng hình thức rằng mọi lịch thực thi đều đúng. Với cấu trúc lock-free hoặc hệ thống phân tán, có thể cần đặc tả và công cụ kiểm tra mạnh hơn.

## 17. Những nhầm lẫn thường gặp

1. **“Mỗi dòng mã là một thao tác nguyên tử.”** Sai: `x += 1` hay `if x then y` có thể là nhiều bước.
2. **“Map thread-safe thì mọi chuỗi get–check–put đều thread-safe.”** Sai: phải có thao tác ghép nguyên tử hoặc khóa bao trọn.
3. **“Set không có bản ghi trùng nên hành động phụ cũng chỉ xảy ra một lần.”** Sai: hai luồng có thể cùng phát sự kiện trước khi ghi vào set.
4. **“Có GIL nên không cần đồng bộ.”** Không đúng như một hợp đồng portable hoặc cho các cập nhật nhiều bước; cần xem runtime và API cụ thể.
5. **“Dữ liệu không bị hỏng tức là mọi kết quả nghiệp vụ đều đúng.”** Sai: cấu trúc có thể hợp lệ nhưng mất cập nhật hoặc đặt quá số chỗ.
6. **“Chỉ writer cần lock, reader không cần.”** Không đúng nếu reader cần snapshot nhất quán hoặc không có cơ chế đọc an toàn khác.
7. **“Một lời gọi nguyên tử làm cả quy trình gồm ba lời gọi nguyên tử.”** Không: ranh giới nguyên tử của từng lời gọi không tự hợp thành một giao dịch.
8. **“`Queue.empty()` trước `get()` bảo đảm không chờ.”** Sai: một consumer khác có thể lấy phần tử cuối giữa hai lần gọi.
9. **“Thức dậy từ Condition nghĩa là điều kiện chắc chắn vẫn đúng.”** Sai: luôn kiểm tra lại bằng `while`.
10. **“RLock giải quyết mọi deadlock.”** Sai: nó chỉ hỗ trợ cùng luồng lấy lại khóa đó; deadlock liên quan nhiều khóa vẫn có thể xảy ra.
11. **“Thread-safe nghĩa là lock-free hoặc công bằng.”** Sai: đây là các thuộc tính khác nhau.
12. **“Dùng nhiều khóa luôn nhanh hơn một khóa.”** Chưa chắc: chi phí quản lý, deadlock và tranh chấp có thể tăng.
13. **“CAS một biến bảo đảm nhất quán mọi trường của đối tượng.”** Sai: bất biến nhiều trường cần thuật toán hoặc đồng bộ riêng.
14. **“BFS đọc đồ thị đang cập nhật vẫn là BFS của một snapshot nào đó.”** Không bảo đảm nếu không có thiết kế nhất quán/phiên bản.
15. **“Sao chép tham chiếu một dict là tạo snapshot độc lập.”** Sai: nếu còn đối tượng lồng nhau có thể thay đổi, bản sao nông vẫn có thể chia sẻ dữ liệu.
16. **“Một bộ đếm có lock là `O(1)` thời gian phản hồi dưới mọi tải.”** Không: thời gian chờ khóa phụ thuộc cạnh tranh và lịch lập lịch.
17. **“Một Queue an toàn luồng bảo đảm xử lý chính xác một lần qua crash.”** Không: cần giao thức, idempotency và lưu bền vững.
18. **“Test vài nghìn lần không lỗi thì chắc chắn không có race.”** Không: lỗi phụ thuộc lịch xen kẽ hiếm và mô hình bộ nhớ.

## 18. Tự kiểm tra

**Câu 1.** Hai luồng cùng đọc `counter=0`, mỗi luồng tính `counter+1` rồi cùng ghi 1. Kết quả là gì và lỗi thuộc loại nào?

**Đáp án:** Kết quả cuối có thể là **1 thay vì 2**: **lost update**, vì chuỗi đọc–tính–ghi không được bảo vệ như một thao tác nguyên tử.

**Câu 2.** Một concurrent map bảo đảm `get` và `put` riêng lẻ an toàn. `if get(k)==None: put(k,v)` có tự bảo đảm chỉ một luồng tạo `v` không?

**Đáp án:** **Không.** Hai luồng có thể cùng thấy k vắng. Cần API nguyên tử như `compute-if-absent` đúng hợp đồng, hoặc khóa bảo vệ cả quyết định và ghi; còn phải xem ngữ nghĩa callback nếu tạo giá trị có tác dụng phụ.

**Câu 3.** Vì sao `KhoAnToan.dat_cho` phải giữ lock trong cả bước kiểm tra đủ hàng lẫn bước trừ số lượng?

**Đáp án:** Nếu nhả khóa giữa hai bước, hai yêu cầu có thể cùng đọc lượng hàng cũ và cùng được chấp nhận; bất biến tồn kho không âm bị phá.

**Câu 4.** Nếu `Queue.empty()` trả `False`, `Queue.get()` ngay sau đó có chắc không chờ khi có hai consumer không?

**Đáp án:** **Không.** Consumer khác có thể lấy phần tử cuối ngay sau lần kiểm tra. Dùng `get_nowait()` và xử lý `Empty`, hoặc `get(timeout=...)`, thay vì tự ghép hai lời gọi để suy ra trạng thái không đổi.

**Câu 5.** Condition thức dậy sau `notify_all()`. Vì sao phải dùng vòng `while` kiểm tra lại điều kiện?

**Đáp án:** Khi lấy lại lock, điều kiện có thể đã bị luồng khác thay đổi; ngoài ra một số môi trường cho phép thức dậy không do thông báo. `while` duy trì bất biến trước khi tiếp tục.

**Câu 6.** Hai luồng lần lượt giữ `L_A` và `L_B` rồi chờ khóa còn lại có thể gặp lỗi gì? Nêu một cách phòng tránh.

**Đáp án:** **Deadlock.** Quy định mọi đường mã lấy khóa theo cùng một thứ tự toàn cục (ví dụ `L_A` rồi `L_B`), hoặc thiết kế để tránh giữ đồng thời nhiều khóa.

**Câu 7.** Có thể gọi một cấu trúc dùng mutex là thread-safe và lock-free đồng thời chỉ dựa vào việc nó chạy đúng không?

**Đáp án:** Không. **Thread-safe** là thuộc tính đúng đắn; **lock-free** là bảo đảm tiến triển không phụ thuộc một luồng giữ mutex bị dừng. Dùng mutex thông thường không đủ để đạt thuộc tính lock-free.

**Câu 8.** Trong đồ thị có hướng giữ `edges/out/in`, thêm cung `u→v` cần cập nhật những gì trong cùng ranh giới nguyên tử?

**Đáp án:** Bản ghi `edges[e]`, `out[u]` và `in[v]` cùng những bộ đếm/chỉ mục phụ tương ứng. Nếu một phía thiếu ID, một truy vấn có thể nhìn thấy dữ liệu mâu thuẫn.

**Câu 9.** Khi xóa đỉnh B có một cung khuyên `B→B`, tại sao hợp `out[B] | in[B]` hữu ích?

**Đáp án:** ID của khuyên có mặt trong cả hai tập nhưng chỉ là **một cung**; hợp tập ID giúp xóa khuyên đúng một lần, không báo lỗi xóa trùng.

**Câu 10.** Một luồng sao chép bảng đỉnh và bảng cung trong cùng lock, rồi nhả lock trước khi BFS trên bản sao. BFS có bảo đảm phản ánh cập nhật xảy ra **sau** lúc chụp không?

**Đáp án:** Không. Nó phản ánh **snapshot tại thời điểm sao chép**, có thể cũ khi BFS kết thúc; bù lại quá trình duyệt không phải giữ khóa chung xuyên suốt.

**Câu 11.** Cho thao tác cộng số lượng trong `dict` có độ phức tạp `O(1)` kỳ vọng nếu không tranh chấp. Khi nhiều luồng tranh một lock, thời gian trả lời có chắc `O(1)` theo thời gian đồng hồ không?

**Đáp án:** **Không.** Chi phí công việc bên trong và **thời gian chờ khóa/lịch lập lịch** là hai yếu tố khác nhau; thời gian chờ có thể lớn hoặc không có cận hữu hạn nếu bị starvation.

**Câu 12.** Atomic CAS trên một con trỏ có thể nhầm trạng thái nào khi thấy `A→B→A`?

**Đáp án:** **ABA**: giá trị cuối vẫn là A nhưng đã có cập nhật trung gian. Tùy thuật toán cần số phiên bản, tagged pointer hoặc cơ chế kiểm soát vòng đời đối tượng.

**Câu 13.** Một cấu trúc có thể bảo toàn trạng thái nội bộ nhưng vẫn cho hai người đặt cùng một chỗ cuối cùng không?

**Đáp án:** **Có.** Nếu các thao tác đơn lẻ hợp lệ nhưng logic `check-then-act` bị xen kẽ, dữ liệu nghiệp vụ có thể sai. Cần định nghĩa thao tác đặt chỗ thành một đơn vị nguyên tử.

**Câu 14.** Vì sao không nên coi hàng nghìn lượt stress test thành công là bằng chứng không có race condition?

**Đáp án:** Vì những lịch xen kẽ gây lỗi có thể rất hiếm hoặc phụ thuộc phần cứng/runtime. Cần kết hợp kiểm tra bất biến, lịch xen kẽ có chủ đích, công cụ race detection hoặc kiểm chứng theo đặc tả.

**Ghi nhớ:** **Cấu trúc an toàn luồng không làm mọi chuỗi thao tác trên nó tự trở thành nguyên tử.** Hãy xác định **bất biến cần bảo vệ**, tìm những bước có thể xen kẽ, chọn **ranh giới đồng bộ** bao trọn kiểm tra và cập nhật, đồng thời bảo đảm người đọc thấy dữ liệu đã công bố một cách nhất quán. Mutex, condition, queue, snapshot, read–write lock và atomic/CAS giải quyết **những nhu cầu khác nhau**; lựa chọn phụ thuộc kiểu truy vấn và mức tranh chấp. Với cấu trúc có nhiều chỉ mục như đồ thị, cập nhật các bảng liên quan như **một trạng thái logic** hoặc đọc từ **snapshot nhất quán**. Đánh giá cả **tính đúng đắn, khả năng tiến triển, độ phức tạp và thời gian chờ**, không chỉ xem mỗi phương thức có dùng lock hay không.
