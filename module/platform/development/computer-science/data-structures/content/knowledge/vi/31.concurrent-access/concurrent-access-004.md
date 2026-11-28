# Vì sao từng phép toán an toàn chưa đủ cho một chuỗi kiểm tra–cập nhật

## 1. Một chỗ trống, hai yêu cầu đăng ký hợp lệ

Một lớp học chỉ còn **một chỗ**. Hai người học cùng bấm đăng ký. Hệ thống dùng một bảng an toàn luồng để lưu `remaining["course-A"]=1` và triển khai:

```text
if remaining.get("course-A") > 0:
    remaining.set("course-A", remaining.get("course-A") - 1)
    return "ĐĂNG KÝ THÀNH CÔNG"
return "HẾT CHỖ"
```

Giả sử cả `get` và `set` đều **an toàn khi được gọi đồng thời**. Ta có thể kết luận thao tác đăng ký an toàn không? **Không.** Hai luồng có thể cùng đọc còn chỗ trước khi một luồng cập nhật, nên cả hai đều được báo thành công.

Một cấu trúc dữ liệu **không bị hỏng bộ nhớ** không đồng nghĩa nghiệp vụ **không thể nhận hai yêu cầu cho một chỗ**. Lỗi nằm ở **chuỗi quyết định dựa trên trạng thái cũ rồi mới thay đổi trạng thái**.

Trong chương **Truy cập đồng thời**, đây là vấn đề nền tảng khi áp dụng bảng băm, set, queue, stack, danh sách liên kết và đồ thị vào hệ thống nhiều luồng. Hiểu cấu trúc dữ liệu là chưa đủ; cần hiểu **bất biến**, **ranh giới nguyên tử** và **điểm có thể xen kẽ** của từng thao tác.

Sau bài này, bạn có thể:

- Phân biệt một **phương thức đơn lẻ an toàn luồng** với một **quy trình gồm nhiều phương thức**.
- Dựng lịch xen kẽ dẫn tới **check-then-act**, **TOCTOU**, **lost update** và **trạng thái đọc không nhất quán**.
- Chọn **API nguyên tử theo nghiệp vụ**, khóa bao trọn, CAS/kiểm tra phiên bản hoặc giao dịch cơ sở dữ liệu.
- Kiểm thử các trường hợp tranh chấp và lý giải chi phí thời gian/bộ nhớ khi đồng bộ.

## 2. “Phép toán an toàn” là một hợp đồng có phạm vi

Giả sử một concurrent map cung cấp ba phương thức:

```text
get(k)     # trả về giá trị hiện có
put(k, v)  # ghi hoặc thay giá trị
remove(k)  # xóa khóa
```

Nếu mỗi lời gọi được bảo đảm **linearizable (tuyến tính hóa được)**, thì kết quả của *mỗi lời gọi* có thể được hiểu như nó xảy ra tại một thời điểm logic duy nhất giữa lúc bắt đầu và lúc trả về.

Nhưng chuỗi:

```text
x = get(k)
if x < limit:
    put(k, x + 1)
```

gồm **hai lời gọi khác nhau và một quyết định ở giữa**. Không có bảo đảm rằng giá trị của khóa vẫn là `x` khi `put` chạy.

| Điều được bảo đảm | Điều **không** tự được bảo đảm |
| --- | --- |
| `get(k)` không làm hỏng cấu trúc khi chạy đồng thời | Giá trị đọc ra không thể thay đổi ngay sau khi `get` trả về |
| `put(k,v)` hoàn tất một lần ghi hợp lệ | Giá trị `v` vẫn phù hợp với trạng thái lúc ghi |
| `contains(k)` phản ánh trạng thái tại một thời điểm logic | `contains(k)` và `insert(k)` hợp lại là một giao dịch |
| `queue.get()` lấy một mục an toàn | `queue.empty()` trước đó dự báo được kết quả của lần `get()` |
| `set.add(x)` không thêm bản sao trùng trong set | Bên ngoài chỉ phát một email/thực hiện một thanh toán |
| `counter.read()` đọc nhất quán một giá trị | `read() + 1` rồi `write()` là phép tăng nguyên tử |

**Tính an toàn không tự “cộng dồn” qua những lời gọi tách rời.** Nếu một nghiệp vụ phải đọc–kiểm tra–cập nhật như một đơn vị, cần thiết kế chính đơn vị ấy thành một **thao tác nguyên tử** theo hợp đồng.

### An toàn bộ nhớ, đúng bất biến và linearizability là những điều khác nhau

- **An toàn bộ nhớ:** không truy cập dữ liệu hỏng hay cấu trúc nội bộ sai theo mô hình runtime.
- **Bất biến cấu trúc:** ví dụ bảng băm giữ được các khóa, queue giữ đúng `head/tail/size`.
- **Bất biến nghiệp vụ:** ví dụ số chỗ không âm, không đăng ký trùng, tổng số dư được bảo toàn.
- **Linearizability:** lịch sử các lời gọi và kết quả phù hợp với một thứ tự tuần tự hợp lệ tôn trọng thời gian thực của những lời gọi không chồng lấp.

Một `ConcurrentMap` có thể tuyến tính hóa được ở cấp `get`/`put` nhưng một phương thức `register()` tự ghép hai lệnh ấy vẫn **không** tuyến tính hóa được theo đặc tả “mỗi chỗ chỉ được bán một lần”.

## 3. Lịch xen kẽ: hai luồng cùng vượt qua điều kiện

Xét hai luồng T1, T2, số chỗ ban đầu bằng 1. Ta tách một lần đăng ký thành:

```text
R: đọc remaining
C: kiểm tra remaining > 0
W: giảm remaining và xác nhận
```

Một lịch xen kẽ có thể là:

| Bước | Luồng T1 | Luồng T2 | Số chỗ hiện có |
| ---: | --- | --- | ---: |
| 1 | Đọc 1 | | 1 |
| 2 | | Đọc 1 | 1 |
| 3 | Kiểm tra: còn chỗ | | 1 |
| 4 | | Kiểm tra: còn chỗ | 1 |
| 5 | Giảm từ 1 xuống 0 | | 0 |
| 6 | | Giảm từ 0 xuống -1 | -1 |
| 7 | Báo thành công | Báo thành công | -1 |

Nếu hai lần giảm được cài theo kiểu đọc giá trị cũ rồi **ghi lại** `0`, số chỗ cuối còn có thể bằng **0** thay vì -1, nhưng hệ thống vẫn báo **hai lần thành công**: đó là một biến thể **lost update**. Vì vậy, **chỉ nhìn giá trị cuối của biến** không đủ xác minh mọi lời gọi có đúng kết quả.

Điểm chung của cả hai biến thể: quyết định “còn chỗ” ở bước 3/4 **không còn chắc đúng** ở thời điểm mỗi luồng thực hiện cập nhật.

Ta không thể khắc phục chỉ bằng:

- Thêm một lần `get` trước khi ghi — giữa lần kiểm tra mới và thao tác ghi vẫn có khe xen kẽ.
- `sleep` để “cho luồng kia xong trước” — không có hợp đồng về thứ tự lịch thực thi.
- Đặt cả `get` lẫn `set` trên một concurrent map — mỗi lời gọi vẫn có ranh giới nguyên tử riêng.
- Chạy thử vài nghìn lần và không quan sát lỗi — không chứng minh mọi lịch xen kẽ đều an toàn.

## 4. Check-then-act và TOCTOU

Mẫu tổng quát:

```text
if điều_kiện_trên_trạng_thái_chung():
    thực_hiện_hành_động_thay_đổi_trạng_thái_chung()
```

Đây là **check-then-act**. Khi trạng thái chung có thể đổi sau phép kiểm tra nhưng trước hành động, ta gặp **TOCTOU (time-of-check to time-of-use)**.

### Những tình huống phổ biến

| Cấu trúc hoặc API | Chuỗi có nguy cơ | Bất biến bị đe dọa |
| --- | --- | --- |
| Tập `set` | `if x not in set: add(x); send_email()` | Một email cho mỗi lần đăng ký mới |
| Bảng băm | `if key not in map: map[key]=make_value()` | Một đối tượng/phiên khởi tạo theo khóa |
| Kho hàng | `if stock>=q: stock-=q` | Tồn kho không âm, không bán quá chỗ |
| Queue | `if not empty(): get()` | Không block ngoài dự kiến, không xử lý lỗi rỗng |
| Stack | `if size()>0: pop()` | Không pop từ stack đã bị luồng khác làm rỗng |
| Cache | `if expired: recompute(); replace` | Không công bố kết quả cũ đè bản mới |
| Đồ thị | `if not has_edge(u,v): add_edge(u,v)` | Không có cung trùng nếu đồ thị đơn |
| Cơ sở dữ liệu | `SELECT count...; INSERT...` | Không vượt quota/unique constraint |

**Không phải mọi check-then-act đều sai.** Nó có thể đúng nếu dữ liệu **bất biến trong suốt đoạn ấy**, một luồng là **chủ sở hữu duy nhất**, hoặc có một **giao thức đồng bộ** giữ điều kiện đúng tới khi cập nhật. Vấn đề là **thiếu chứng minh bảo đảm đó**.

### Check-then-act khác lost update như thế nào?

- **Check-then-act:** quyết định hành động dựa trên một điều kiện có thể hết hiệu lực.
- **Lost update:** hai thao tác ghi dựa trên cùng giá trị cũ khiến kết quả của một thao tác bị ghi đè.
- Một chương trình có thể mắc **cả hai**: cùng thấy `stock=1`, cùng tính `stock-1=0`, cả hai ghi 0 và cả hai xác nhận.

## 5. Python: tái hiện lỗi dù từng phương thức có khóa

Ta cố ý tạo hai phương thức **an toàn riêng lẻ**: đọc số chỗ và trừ một chỗ. Sau đó ghép chúng sai ở phía gọi.

```python
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock


class KhoPhepDon:
    def __init__(self, so_cho):
        self._remaining = so_cho
        self._lock = Lock()

    def con_lai(self):
        with self._lock:
            return self._remaining

    def tru_mot(self):
        with self._lock:
            self._remaining -= 1


kho = KhoPhepDon(1)
gate = Barrier(2)


def dat_cho_khong_an_toan():
    if kho.con_lai() >= 1:
        # Chỉ trong TEST: buộc cả hai luồng cùng vượt kiểm tra.
        gate.wait()
        kho.tru_mot()
        return True
    return False


with ThreadPoolExecutor(max_workers=2) as pool:
    f1 = pool.submit(dat_cho_khong_an_toan)
    f2 = pool.submit(dat_cho_khong_an_toan)
    outcomes = [f1.result(), f2.result()]

print(outcomes)           # [True, True]
print(kho.con_lai())     # -1
```

**Vì sao ví dụ tái hiện được lỗi?** `Barrier(2)` buộc cả hai luồng dừng tại một điểm **sau khi đã kiểm tra thấy còn chỗ**. Chỉ khi cả hai đã vượt qua điều kiện, chúng mới được phép giảm. Mỗi lần giảm có lock, nhưng lock ấy **không bao trùm** quyết định ở bước trước.

**Chú ý:** đây là **mã thử nghiệm** được thiết kế để chỉ ra lỗi, không phải mẫu code đăng ký thực tế. Barrier phải được bố trí ở nơi cả hai luồng chắc chắn có thể tới; đặt `gate.wait()` **bên trong cùng một lock** sẽ khiến luồng thứ hai không vào được barrier, dễ tạo deadlock nhân tạo.

Điều cần chứng minh không chỉ là `remaining >= 0` sau mọi lượt test, mà còn là **số lần trả thành công không vượt số chỗ ban đầu**.

## 6. Đúng ở cấp nghiệp vụ: cung cấp một thao tác `reserve_if_available`

Thay vì để bên gọi tự ghép `read` và `decrement`, cấu trúc nên cung cấp **một phương thức nguyên tử theo ý nghĩa nghiệp vụ**:

```python
from concurrent.futures import ThreadPoolExecutor
from threading import Lock


class KhoDatCho:
    def __init__(self, so_cho):
        if type(so_cho) is not int or so_cho < 0:
            raise ValueError("Số chỗ phải là số nguyên không âm")
        self._remaining = so_cho
        self._lock = Lock()

    def reserve_if_available(self, quantity=1):
        if type(quantity) is not int or quantity <= 0:
            raise ValueError("quantity phải là số nguyên dương")

        with self._lock:
            if self._remaining < quantity:
                return False
            self._remaining -= quantity
            return True

    def remaining(self):
        with self._lock:
            return self._remaining


kho = KhoDatCho(1)
with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(
        lambda _: kho.reserve_if_available(), range(2)
    ))

print(sum(results))            # 1
print(kho.remaining())         # 0
```

Ở đây, ranh giới nguyên tử gồm **cả bước kiểm tra lẫn bước trừ**. Một lời gọi thành công chỉ khi nó đã thực hiện được bước trừ dưới khóa; lời gọi còn lại nhìn thấy trạng thái mới và trả `False`.

Bất biến của cấu trúc:

\[
remaining\ge 0,\qquad
successes\le initial\_stock
\]

nếu mỗi lần thành công đặt một chỗ và không có thao tác nạp/trả chỗ nào khác.

**Điểm tuyến tính hóa** có thể được xem tại bước trừ số chỗ khi đang giữ lock; các lời gọi đồng bộ khác không thể xen vào giữa kiểm tra và bước ấy.

### Vì sao API này tốt hơn `get` + `put`?

- **Ranh giới bất biến là một phương thức**, nên bên gọi không cần tự biết cách khóa dữ liệu bên trong.
- Người dùng API nhận **kết quả thành công/thất bại**, thay vì phải suy ra từ trạng thái có thể thay đổi ngay.
- Dễ viết test rằng có tối đa `initial_stock` lần thành công với nhiều luồng.
- Có thể thay cách lưu `remaining` trong tương lai bằng atomic integer, bảng băm phân đoạn hoặc database mà không đổi ý nghĩa nghiệp vụ.

**Giới hạn:** đây là mô hình **một tiến trình, một đối tượng**, không tự đồng bộ các máy chủ có bản sao kho riêng. Mutex không cung cấp lưu bền hay rollback trước sự cố tài nguyên giữa chừng.

## 7. Một điểm khó hơn: hai phép đọc đều an toàn nhưng tạo snapshot sai

Giả sử có hai tài khoản A và B, tổng tiền bằng 100. Một writer chuyển 30 từ A sang B **nguyên tử** theo API:

```text
Trước: (A,B) = (70,30)
Sau:   (A,B) = (40,60)
```

Một reader gọi hai phương thức an toàn riêng:

```text
x = ledger.get_balance("A")
y = ledger.get_balance("B")
return x + y
```

Có thể xảy ra:

```text
Reader: get(A) -> 70
Writer: transfer(A,B,30) hoàn thành -> (40,60)
Reader: get(B) -> 60
Reader: tổng 130
```

**Không phương thức đơn nào sai.** `get(A)` tuyến tính hóa trước khi chuyển, `get(B)` tuyến tính hóa sau khi chuyển; mỗi kết quả hợp lệ theo thời điểm riêng. Sai lầm là coi **hai lần đọc của hai phiên bản** như một snapshot chung.

Một API `ledger.snapshot_balances()` phải đọc đủ hai số dư trong cùng đoạn găng (hoặc từ cùng phiên bản bất biến). Khi đó tổng chỉ có thể là 100 nếu không có nạp/rút ngoài.

**Bài học tổng quát:** tính nguyên tử phải bao trọn **đơn vị quan sát** của người đọc, không chỉ đơn vị cập nhật của người ghi.

## 8. Bảng băm: `contains` và `insert` không tạo ra `put_if_absent`

Một ví dụ phổ biến:

```python
if cache.get(key) is None:
    cache.put(key, expensive_build())
```

Giả sử `get` và `put` đều thread-safe. Hai luồng vẫn có thể cùng gọi `expensive_build()`, rồi ghi đè kết quả của nhau.

Các cách thiết kế tốt hơn:

1. Dùng thao tác thư viện **`put_if_absent`, `compute_if_absent` hoặc `setdefault`** nếu *hợp đồng cụ thể* bảo đảm nguyên tử cần thiết trong runtime sử dụng.
2. Đưa việc kiểm tra và ghi vào **cùng lock** trên một đối tượng chứa dữ liệu.
3. Dùng **khóa theo key/stripe** nếu có thể bảo vệ đúng vòng đời key, công bố kết quả và hoạt động resize.
4. Dùng **future/promise cho cùng khóa** để các luồng cùng chờ một lần tính toán đang thực hiện, khi hệ thống cần “single flight”.

### Phải đọc kỹ hợp đồng của callback

Có thư viện cho phép `compute_if_absent` gọi **hàm tạo giá trị** nhiều lần trong những tình huống tranh chấp, retry hoặc lỗi. Nó có thể chỉ bảo đảm **một giá trị được công bố**, không bảo đảm callback tạo giá trị chạy đúng một lần.

Nếu `expensive_build()` chỉ tạo dữ liệu thuần và không có tác dụng phụ, tính lại có thể chấp nhận. Nhưng nếu callback **gửi email, thanh toán hoặc đăng ký dịch vụ ngoài**, số lần callback chạy là yêu cầu nghiệp vụ riêng; không thể suy ra từ tính nguyên tử của thao tác cập nhật map.

Ngoài ra, dùng `None` để biểu thị khóa chưa tồn tại có thể nhập nhằng nếu chính `None` là một giá trị hợp lệ. API kiểm tra vắng mặt phải có quy ước rõ ràng.

## 9. Set: không có mục trùng vẫn có thể có tác dụng phụ trùng

Giả sử một tập `registered_ids` không cho phần tử trùng:

```text
if user_id not in registered_ids:
    registered_ids.add(user_id)
    send_welcome_email(user_id)
```

Với hai luồng:

```text
T1: contains(user) -> False
T2: contains(user) -> False
T1: add(user)       -> inserted
T2: add(user)       -> already present
T1: send email
T2: send email
```

Set cuối cùng **đúng về số phần tử**, nhưng lại có **hai email**. Đây là lỗi ở **kết quả và tác dụng phụ**, không nhất thiết ở cấu trúc set.

Giải pháp ở cấp API:

```text
inserted = register_if_absent(user_id)
if inserted:
    schedule_welcome_email(user_id)
```

`register_if_absent` cần kiểm tra và chèn như **một thao tác nguyên tử**, rồi trả `True` chỉ cho luồng thực sự chèn lần đầu.

**Nhưng còn một ranh giới khác:** nếu ghi đăng ký thành công rồi chương trình bị crash **trước khi gửi email**, thư có thể bị mất. Nếu gửi email **trước khi commit**, có thể gửi thư cho đăng ký không thành công. Khi cần cam kết bền vững qua hệ thống ngoài, cân nhắc **transactional outbox**, idempotency key, xử lý retry và theo dõi trạng thái gửi.

Khóa trong bộ nhớ không tự giải quyết tính đúng đắn qua **nhiều tiến trình hay dịch vụ**.

## 10. Queue và stack: kiểm tra rỗng rồi lấy là một cuộc đua

Một lỗi thường gặp với queue:

```python
# Không an toàn như một quy trình ghép khi có nhiều consumer.
if not queue.empty():
    item = queue.get()
```

`empty()` có thể trả `False` tại thời điểm gọi. Trước khi `get()` chạy, một consumer khác có thể lấy **mục cuối cùng**, làm `get()` **chặn** (nếu là phiên bản blocking).

Trong Python, khi cần thử lấy mà **không chờ**, hãy dùng phương thức hỗ trợ kiểm tra và lấy trong cùng thao tác:

```python
from queue import Empty, Queue

q = Queue()
q.put("task-1")

try:
    item = q.get_nowait()  # Hoặc q.get(block=False).
except Empty:
    item = None
else:
    try:
        print("Xử lý:", item)
    finally:
        q.task_done()
```

`get_nowait()` tự quyết định “có mục hay không” và lấy một mục theo hợp đồng đồng thời của Queue; không phụ thuộc một lần `empty()` trước đó.

**Không đồng nhất an toàn queue với xử lý nghiệp vụ đúng một lần:** nếu worker crash sau `get` nhưng trước khi hoàn thành, queue trong bộ nhớ không tự gửi lại tác vụ hay bảo đảm exactly-once qua crash.

Tương tự với stack:

```text
if stack.size() > 0:
    return stack.pop()
```

Nếu `size` và `pop` là hai lời gọi an toàn riêng, một luồng khác có thể pop mục cuối giữa chúng. Cần `try_pop()` **đơn nhất** trả “rỗng” hoặc phần tử, hay một giao thức khóa bao trọn cả kiểm tra–lấy.

## 11. Đặt nhiều món hàng: bất biến trải trên nhiều khóa

Giả sử đơn hàng cần **2 vé A và 1 vé B**, kho có A=2, B=1. Một thao tác đơn hàng hợp lệ phải:

- Chỉ chấp nhận khi **cả hai** mã đều đủ.
- Trừ số lượng của **cả hai** mã nếu thành công.
- **Không** trừ bất kỳ mã nào nếu thất bại.
- Không cho số lượng tồn kho âm.

Nếu chỉ dùng từng phép `get(A)`, `decrement(A)`, `get(B)`, `decrement(B)` an toàn đơn lẻ, hai đơn có thể xen kẽ làm kho âm hoặc tạo **đơn hàng thành công một phần**.

### Python: đặt cả giỏ hàng dưới một khóa

```python
from concurrent.futures import ThreadPoolExecutor
from threading import Lock


class KhoNhieuMa:
    def __init__(self, initial):
        if not isinstance(initial, dict):
            raise TypeError("initial phải là dict")
        if any(type(q) is not int or q < 0 for q in initial.values()):
            raise ValueError("Số lượng tồn phải là số nguyên không âm")
        self._stock = dict(initial)
        self._lock = Lock()

    def dat_gio(self, order):
        if not isinstance(order, dict) or not order:
            raise ValueError("Đơn hàng phải là dict không rỗng")
        if any(type(q) is not int or q <= 0 for q in order.values()):
            raise ValueError("Số lượng đặt phải là số nguyên dương")

        with self._lock:
            if any(sku not in self._stock for sku in order):
                raise KeyError("Mã hàng không tồn tại")
            if any(self._stock[sku] < qty
                   for sku, qty in order.items()):
                return False

            for sku, qty in order.items():
                self._stock[sku] -= qty
            return True

    def snapshot(self):
        with self._lock:
            return dict(self._stock)


kho = KhoNhieuMa({"A": 2, "B": 1})
order = {"A": 2, "B": 1}

with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(
        lambda _: kho.dat_gio(order), range(2)
    ))

print(sum(results))       # 1
print(kho.snapshot())     # {'A': 0, 'B': 0}
```

Trên hai lời gọi đồng thời, **chính xác một đơn thành công**; đơn còn lại thấy kho không đủ và không trừ thêm bất kỳ mã nào.

**Giới hạn mô hình:** `order` được bên gọi truyền như một dict; ví dụ giả định bên gọi không sửa dict ấy đồng thời trong lúc `dat_gio` kiểm tra hoặc duyệt. Trong API thực, có thể chuyển đầu vào thành một cấu trúc bất biến đã xác thực trước khi thao tác. Mã không tự cung cấp rollback nếu gặp lỗi tài nguyên bất thường giữa các lần gán trong vùng găng.

Nếu kho rất lớn và cần nhiều đơn hàng cho các mã độc lập, có thể dùng **khóa theo mã hoặc stripe**, nhưng mỗi đơn nhiều mã phải lấy **đủ các khóa liên quan theo thứ tự cố định** và người đọc tổng kho phải có giao thức snapshot tương thích.

## 12. Khóa phải bao trùm chính điều kiện ra quyết định

Chọn `Lock` không khó; khó là xác định **phạm vi**.

Một cách sai:

```text
lock
    remaining = stock[sku]
unlock

if remaining >= quantity:
    lock
        stock[sku] -= quantity
    unlock
    return success
```

Hai đoạn riêng biệt đều đồng bộ, nhưng giá trị `remaining` **không còn được bảo vệ** giữa hai đoạn.

Một cách đúng với một mutex:

```text
lock
    if stock[sku] < quantity:
        return failure
    stock[sku] -= quantity
    return success
unlock
```

Nếu có nhiều điều kiện, ví dụ tài khoản còn tiền, chỗ còn trống, học viên chưa đăng ký, thì tập dữ liệu cần khóa có thể trải trên **nhiều cấu trúc**. Phải có một **giao thức commit** bảo đảm mọi điều kiện còn đúng vào thời điểm công bố kết quả.

### Giữ đoạn găng đủ rộng nhưng không tùy tiện kéo dài

Nên thực hiện bên ngoài lock những công việc **không phụ thuộc trạng thái chung**: phân tích dữ liệu đầu vào bất biến, định dạng thông báo, tính toán thuần túy. Nhưng những tiền điều kiện như `remaining > 0`, “khóa chưa tồn tại” hoặc “ID còn hợp lệ” thường phải kiểm tra **trong đoạn găng** hoặc được **kiểm tra lại ở thời điểm commit**.

Không gọi dịch vụ mạng, email hoặc callback chưa kiểm soát trong lock chỉ để “làm tất cả nguyên tử”: nó có thể giữ lock lâu, chặn luồng khác và gây deadlock; hơn nữa mutex nội bộ cũng không làm giao dịch với dịch vụ ngoài tự nguyên tử.

## 13. So sánh các cách khắc phục

| Cách giải quyết | Thích hợp | Đánh đổi |
| --- | --- | --- |
| **API ghép nguyên tử** như `reserve_if_available` | Cần đúng một hành động phụ thuộc điều kiện | Giao diện phải phản ánh nhu cầu nghiệp vụ |
| **Mutex toàn cấu trúc** | Ít dữ liệu, nhiều bất biến chung, cần dễ chứng minh | Tranh chấp khi nhiều thao tác độc lập |
| **Khóa theo key/bucket/stripe** | Nhiều thao tác độc lập trên vùng khác nhau | Multi-key, resize, vòng đời khóa và deadlock phức tạp |
| **Atomic read-modify-write / CAS** | Một trạng thái nhỏ, phép cập nhật biểu diễn được bằng CAS | Retry, memory ordering, ABA, không tự bảo vệ đa trường |
| **Optimistic version check** | Đọc/tính thử ngoài lock, xung đột tương đối ít | Phải kiểm tra phiên bản và commit nguyên tử; retry |
| **Snapshot bất biến / copy-on-write** | Nhiều reader cần snapshot nhất quán | Chi phí bản sao/phiên bản, quản lý vòng đời |
| **Transaction và constraint của DB** | Nhiều tiến trình/thiết bị cùng ghi vào một kho bền vững | Chi phí giao dịch, cô lập, deadlock/retry và lỗi mạng |
| **Single-owner/actor** | Muốn tránh chia sẻ ghi trực tiếp | Mọi yêu cầu vào cùng hàng đợi/chủ sở hữu, có thể thành nút thắt |

**Công cụ nào đúng phụ thuộc phạm vi bất biến.** Nếu giới hạn là một số nguyên trong cùng tiến trình, atomic/CAS có thể thích hợp. Nếu giới hạn là “không quá 20 học viên và chỉ một bản ghi đăng ký trên nhiều máy chủ”, cần xác định giao dịch ở nơi **quyền quyết định chung** được duy trì.

## 14. CAS: thay đổi có điều kiện thay vì đọc rồi ghi mù

**Compare-and-swap (CAS)** là ý tưởng “chỉ ghi giá trị mới nếu giá trị hiện hành vẫn bằng giá trị dự kiến”, với bước so sánh và ghi là **một thao tác nguyên tử**.

Mã giả đặt chỗ một đơn vị:

```text
function reserve_one_atomic(stock):
    while true:
        old = atomic_load(stock)
        if old == 0:
            return false
        if CAS(stock, expected=old, desired=old-1):
            return true
        # CAS thất bại: có luồng khác đã thay đổi trạng thái,
        # đọc lại và xét điều kiện lần nữa.
```

Nếu ban đầu `stock=1`, hai luồng có thể cùng đọc `old=1`, nhưng **chỉ một CAS** đổi được 1→0. CAS của luồng còn lại thất bại, sau đó nó đọc 0 và trả `False`.

**Điều không được suy ra:**

- Chỉ dùng CAS với **một biến** không tự cập nhật nguyên tử hai số dư hay ba bảng chỉ mục đồ thị.
- CAS có thể cần **thử lại nhiều lần** khi tranh chấp; không bảo đảm từng lời gọi riêng luôn hoàn tất nhanh.
- Cần tuân thủ **memory ordering** và giao diện atomic của ngôn ngữ/runtime, không tự mô phỏng CAS bằng một lần `if` rồi gán biến thường.
- Nếu giá trị/con trỏ đổi A→B→A, một thuật toán chỉ so sánh “hiện vẫn là A” có thể gặp **vấn đề ABA**; tùy cấu trúc cần số phiên bản, tagged pointer hoặc quản lý vòng đời đối tượng.

Mã giả này không phải đoạn Python tiêu chuẩn có CAS built-in cho mọi kiểu dữ liệu; nó mô tả nguyên lý khi ngôn ngữ/thư viện cung cấp primitive tương ứng.

## 15. Kiểm tra phiên bản: đọc lạc quan, ghi có xác nhận

Một chiến lược khác là gắn **version** vào trạng thái. Quy trình:

1. Lấy snapshot nhất quán kèm `version=v`.
2. Tính toán dự kiến từ snapshot ở ngoài khóa.
3. Khi ghi, **trong cùng một giao thức nguyên tử**, kiểm tra `version` hiện tại còn bằng v.
4. Nếu bằng v và tiền điều kiện vẫn thỏa → cập nhật và tăng version.
5. Nếu khác v → từ chối hoặc đọc lại/tính lại.

Ví dụ Python thể hiện check-and-commit với lock:

```python
from threading import Lock


class CounterPhienBan:
    def __init__(self, value=0):
        if type(value) is not int or value < 0:
            raise ValueError("value phải là số nguyên không âm")
        self._value = value
        self._version = 0
        self._lock = Lock()

    def snapshot(self):
        with self._lock:
            return self._version, self._value

    def try_increment(self, expected_version, limit):
        if type(limit) is not int or limit < 0:
            raise ValueError("limit phải không âm")
        with self._lock:
            if expected_version != self._version:
                return "CONFLICT"
            if self._value >= limit:
                return "FULL"
            self._value += 1
            self._version += 1
            return "OK"


c = CounterPhienBan()
v1, value1 = c.snapshot()     # (0, 0)
v2, value2 = c.snapshot()     # (0, 0)
print(c.try_increment(v1, 1))  # OK
print(c.try_increment(v2, 1))  # CONFLICT
print(c.snapshot())            # (1, 1)
```

Cả hai quyết định ban đầu dựa vào version 0. Sau khi một thao tác thành công, version đã thành 1; thao tác cũ thứ hai **không được âm thầm áp dụng**.

**Không đủ:** đọc `version` ở đầu quy trình rồi kiểm tra lại bằng một lệnh thường **trước** khi mở khóa để ghi. Phải có bước **check-and-commit không thể xen kẽ**.

Chi phí của optimistic concurrency là khả năng **xung đột và retry**. Nếu nhiều luồng tranh cùng một bản ghi nóng, nhiều lần tính thử có thể bị bỏ; với nghiệp vụ có tác dụng phụ, retry càng phải được kiểm soát.

## 16. Database: khóa trong tiến trình không bảo vệ toàn hệ thống

Nếu hai máy chủ có **hai đối tượng `KhoDatCho` riêng** nhưng cùng bán một chỗ trong cơ sở dữ liệu, mutex của máy A **không khóa** dữ liệu trong tiến trình của máy B.

Ở cấp cơ sở dữ liệu, một thao tác giảm kho có điều kiện có thể được thể hiện (cú pháp SQL mang tính minh họa):

```sql
UPDATE inventory
SET remaining = remaining - 1
WHERE sku = :sku AND remaining >= 1;
```

Sau lệnh, kiểm tra **số hàng được cập nhật**:

- `1` hàng: điều kiện còn chỗ đúng tại thời điểm cập nhật và bản ghi được sửa theo cơ chế đồng thời của DB.
- `0` hàng: không có bản ghi phù hợp hoặc số chỗ không đủ.

Điều này tốt hơn mẫu `SELECT remaining` rồi ra quyết định ở ứng dụng và `UPDATE` vô điều kiện. Với **đơn gồm nhiều SKU** hoặc **ghi đăng ký + trừ kho**, vẫn cần **giao dịch** thích hợp và các ràng buộc toàn vẹn phù hợp.

Ví dụ ngăn đăng ký trùng có thể dựa vào **unique constraint** trên `(course_id, learner_id)`. Nhưng unique constraint chỉ bảo vệ **tính duy nhất**, không tự bảo vệ quota tổng số học viên: phải phối hợp với điều kiện cập nhật quota hoặc cơ chế giao dịch tương ứng.

**Cần xét mức cô lập transaction, deadlock, serialization failure và retry** của hệ quản trị sử dụng. Không nên khẳng định một câu SQL hay một mức cô lập bất kỳ giải quyết mọi điều kiện xuyên nhiều bản ghi.

### Tác dụng phụ sau commit

Nếu cần gửi email sau khi trừ kho, hãy phân biệt:

- **Commit thành công** của dữ liệu nghiệp vụ.
- **Phát hành sự kiện/email** ra hệ thống bên ngoài.
- **Retry** sau timeout, mất kết nối hoặc tiến trình chết.

Mô hình transactional outbox và idempotency key thường hữu ích để tránh mất sự kiện hoặc thực thi tác dụng phụ trùng khi gửi lại. “Exactly once” ở cấp hệ thống phân tán cần một hợp đồng rõ ràng, không thể suy ra từ mutex của map.

## 17. Cấu trúc dữ liệu đồ thị: kiểm tra không trùng rồi cập nhật nhiều chỉ mục

Bài toán đồ thị đơn có hướng: **không cho hai cung cùng cặp `(u,v)`**. Một cài đặt có thể làm:

```text
if not graph.has_arc(u, v):
    graph.add_arc(u, v)
```

Giả sử cả hai lời gọi trên đều khóa và an toàn riêng lẻ. Hai luồng có thể cùng thấy “chưa có cung”, rồi cùng thêm, làm xuất hiện **hai cung song song** trái với chính sách đồ thị đơn.

Nếu đồ thị còn giữ bảng cạnh chuẩn `edges` và hai chỉ mục `out[u]`, `in[v]`, việc thêm một cung hợp lệ phải bảo vệ **cả việc xác định không trùng và cập nhật đồng bộ các bảng**.

### Python: một API `add_arc_if_absent`

```python
from threading import Lock


class DoThiDonDongThoi:
    def __init__(self, vertices):
        self._lock = Lock()
        self._vertices = set(vertices)
        self._edges = {}  # eid -> (u, v)
        self._out = {u: set() for u in self._vertices}
        self._incoming = {u: set() for u in self._vertices}
        self._next_eid = 0

    def add_arc_if_absent(self, u, v):
        with self._lock:
            if u not in self._vertices or v not in self._vertices:
                raise KeyError("Đầu mút không tồn tại")
            if any(self._edges[eid][1] == v
                   for eid in self._out[u]):
                return None   # Đã có cung u -> v.

            eid = self._next_eid
            self._next_eid += 1
            self._edges[eid] = (u, v)
            self._out[u].add(eid)
            self._incoming[v].add(eid)
            return eid

    def snapshot(self):
        with self._lock:
            return (
                frozenset(self._vertices),
                tuple(
                    (eid, u, v)
                    for eid, (u, v) in self._edges.items()
                ),
            )


g = DoThiDonDongThoi(["A", "B", "C"])
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(
        lambda _: g.add_arc_if_absent("A", "B"), range(2)
    ))

print(sum(result is not None for result in results))  # 1
print(len(g.snapshot()[1]))                           # 1
```

Bằng cách đặt **kiểm tra tồn tại và ba thay đổi** trong cùng lock, đồ thị tránh được cả **cung trùng trái chính sách** lẫn việc người đọc qua API thấy chỉ mục thiếu một phía.

Chi phí kiểm tra ở ví dụ là `O(outdeg(u))` vì quét các ID trong `_out[u]`. Muốn tra cặp `(u,v)` nhanh hơn, có thể thêm chỉ mục hash theo cặp đầu mút, nhưng nó phải được **cập nhật trong cùng ranh giới bất biến**.

**Giới hạn:** mẫu cố tình đơn giản, chưa hỗ trợ xóa đỉnh/cung, xử lý `MemoryError`/rollback hay sửa đồ thị ở nhiều tiến trình. Lock bảo vệ sự xen kẽ của những luồng **tuân thủ API**, không tự phục hồi các ghi dở khi có lỗi tài nguyên.

## 18. Cập nhật nhiều vùng: chọn ranh giới khóa theo bất biến

Một bảng băm phân đoạn có thể có khóa riêng cho mỗi bucket. Điều này hữu ích khi hai thao tác chỉ ảnh hưởng hai bucket khác nhau. Nhưng nếu một hành động cần thay đổi hai tài khoản `A` và `B`, nó cần một giao thức như:

```text
indices = sorted(unique(stripe(A), stripe(B)))

acquire tất cả lock theo thứ tự tăng
try:
    kiểm tra tiền điều kiện trên cả A và B
    cập nhật cả hai số dư
finally:
    release các lock theo thứ tự ngược
```

**Không** lấy khóa nguồn rồi nhả, sau đó mới lấy khóa đích; đó lại là hai đoạn riêng, mở khe xen kẽ.

Một giao thức lấy nhiều lock phải lưu ý:

- **Thứ tự khóa toàn cục:** ngăn deadlock khi hai luồng cập nhật A→B và B→A.
- **Khử trùng lock:** nếu A và B thuộc cùng stripe, không được cố lấy hai lần một mutex không tái nhập.
- **Vòng đời khóa và dữ liệu:** xóa/chèn key, resize/rehash có thể làm key đổi vị trí hoặc khóa bảo vệ.
- **Người đọc toàn cấu trúc:** muốn snapshot chính xác phải theo một giao thức tương thích, không đọc từng bucket rồi ghép tùy thời điểm.
- **Bất biến metadata:** tổng số phần tử, bộ đếm, trạng thái resize có thể là dữ liệu dùng chung ngoài các bucket.

Khóa chi tiết thường tăng mức song song khi các thao tác **thật sự độc lập**. Nếu mọi luồng cùng tranh một khóa nóng, chia nhiều bucket không giải quyết nút thắt.

## 19. Những điểm dễ quên: callback, ngoại lệ, phiên bản và tính tiến triển

### Callback có thể chạy lâu hoặc chạy nhiều lần

Một API `compute_if_absent` có callback gọi tới hệ thống bên ngoài có thể gây tranh chấp dài hoặc tác dụng phụ trùng nếu thư viện retry. Cần biết callback **được phép chạy mấy lần**, có chạy dưới lock không và có thể tái nhập hay không.

### Mutex không tự rollback khi có ngoại lệ

```text
with lock:
    edges[e] = (u, v)
    out[u].add(e)
    # Lỗi cấp phát ở đây
    incoming[v].add(e)
```

Nếu bước cuối lỗi, `with` nhả lock khi thoát nhưng đồ thị vẫn **không nhất quán**. Tính nguyên tử trước **sự xen kẽ luồng** không đồng nghĩa tính nguyên tử trước **ngoại lệ hoặc crash**. Cần chuẩn bị dữ liệu, rollback đúng, hoặc dựng bản trạng thái mới rồi chỉ công bố khi đã hợp lệ.

### Kiểm tra phiên bản cần phối hợp với công bố dữ liệu

Nếu chỉ tăng version sau một chuỗi ghi nhưng người đọc có thể thấy các trường mới **trước khi** thấy version mới, một lần kiểm tra bằng version đơn giản có thể không đủ. Cần mô hình bộ nhớ, snapshot hoặc giao thức đọc–ghi phù hợp; không tự lấy một số version không đồng bộ làm bằng chứng rằng mọi trường nhất quán.

### An toàn luồng khác công bằng và không chờ

Mutex bảo đảm những luồng tuân thủ sẽ không cùng vào vùng găng, nhưng **không tự bảo đảm** luồng nào giành được khóa trước. Một thao tác có ít bước làm việc vẫn có thể chờ rất lâu dưới tranh chấp. CAS có thể phải retry liên tục; các khái niệm **thread-safe**, **lock-free**, **wait-free**, **fairness** là những bảo đảm khác nhau.

### Trạng thái bất biến có thể đơn giản hóa bài toán

Nếu dữ liệu không bị sửa tại chỗ và reader chỉ đọc **snapshot hoàn chỉnh**, nhiều thao tác đọc không cần khóa từng bước. Writer tạo phiên bản mới, kiểm tra hợp lệ và công bố một cách an toàn. Đổi lại phải quản lý bộ nhớ, thời điểm snapshot và độ mới của kết quả.

## 20. Độ phức tạp: số bước ngắn không có nghĩa thời gian phản hồi ngắn

Giả sử `dict` và `set` có tra cứu kỳ vọng `O(1)` với phép băm phù hợp:

| Phương pháp | Số bước làm việc cơ bản | Chi phí/giới hạn thêm |
| --- | --- | --- |
| `get(k)` rồi `put(k,v)` tách rời | Hai thao tác `O(1)` kỳ vọng | **Không đủ đúng đắn** cho check-then-act |
| `reserve_if_available` dưới một mutex | `O(1)` nếu chỉ có một số đếm | Chờ khóa; dưới tranh chấp độ trễ có thể lớn |
| Đặt giỏ `q` mã hàng bằng một lock | `O(q)` kỳ vọng sau xác thực | Khóa toàn kho trong lúc xử lý |
| Kiểm tra cặp cung bằng quét `out[u]` | `O(outdeg(u))` | Chi phí tăng với bậc đỉnh; lock giữ lâu hơn |
| Chỉ mục hash `(u,v)` + commit nguyên tử | `O(1)` kỳ vọng cho tra cứu | Cần cập nhật **cả chỉ mục phụ** và bảng gốc |
| Snapshot đồ thị n đỉnh, m cung | `O(n+m)` thời gian và bộ nhớ | Có thể cần khóa/phiên bản, snapshot có thể cũ |
| CAS trên một số nguyên | Mỗi thử `O(1)` theo mô hình primitive | Số lần retry phụ thuộc tranh chấp |
| Optimistic version check | Kiểm tra/commit nhỏ sau khi tính | Nhiều xung đột có thể tăng chi phí tính lại |

Cần phân biệt **độ phức tạp công việc** với **thời gian đồng hồ**:

\[
T_{\mathrm{response}}
=
T_{\mathrm{waiting}}+
T_{\mathrm{work}}+
T_{\mathrm{coordination}}.
\]

Ký hiệu Big-O cho `T_work` không tự cho cận của `T_waiting` nếu luồng bị preempt, starvation hoặc chờ một lock do luồng khác giữ.

Nếu giữ lock trong khi thực hiện thao tác mạng hay callback dài, phần `T_waiting` có thể lớn dù cấu trúc dữ liệu có lookup kỳ vọng hằng số. Tối ưu nên dựa trên **đo lock wait time, hold time, throughput, p95/p99 latency** và phân bố khóa nóng.

## 21. Kiểm thử đúng đắn: chủ động tạo lịch làm hỏng lời giải sai

### 21.1. Ép hai luồng cùng đi qua bước kiểm tra

`Barrier` trong ví dụ mục 5 giúp tái hiện một lịch lỗi cụ thể. Những kiểm thử tương tự có thể tạo điểm dừng sau `contains` trước `insert` hoặc giữa hai phép đọc của báo cáo.

**Không đặt barrier trong lock theo cách khiến luồng thứ hai không thể tới điểm chờ**, vì lúc đó bài test tự tạo deadlock.

### 21.2. Đối chiếu cả kết quả từng lời gọi

Với kho ban đầu có một chỗ và hai yêu cầu đồng thời, điều kiện đúng là:

\[
\#successes=1,\qquad remaining=0,
\]

khi hai lời gọi đều hoàn thành và không có nạp/trả thêm.

Chỉ kiểm tra `remaining==0` không đủ: một kiểu lost update có thể khiến **hai lời gọi cùng báo thành công** dù biến cuối vẫn bằng 0.

Với đăng ký duy nhất, cần kiểm tra cả tập ID cuối **và** số lần một tác dụng phụ được lên lịch. Với đồ thị đơn, cần kiểm tra **số cung theo cặp (u,v)**, bảng cạnh và chỉ mục hai chiều.

### 21.3. Kiểm tra lịch sử theo đặc tả tuần tự

Một cách mạnh hơn là ghi lại thời điểm bắt đầu/kết thúc, đối số và giá trị trả về của mỗi lời gọi, rồi hỏi:

> Có một thứ tự tuần tự hợp lệ, tôn trọng những lời gọi không chồng lấp, có thể giải thích tất cả kết quả này không?

Đó là ý tưởng kiểm tra **linearizability**. Đối với `reserve_if_available` với một chỗ, không có thứ tự tuần tự hợp lệ nào cho **hai lời gọi đều thành công** nếu không có lần nhập thêm.

### 21.4. Kiểm tra cả trường hợp lỗi và khả năng tiến triển

Nên thử:

- Nhiều luồng cùng tranh **một khóa nóng**.
- Nhiều yêu cầu trên các khóa khác nhau.
- Đơn hàng nhiều SKU, khóa theo hai vùng, trường hợp một vùng hết hàng.
- Cache value có thể là `None` và callback có tác dụng phụ.
- Queue rỗng, timeout, nhiều consumer.
- Ngoại lệ khi đang chuẩn bị/cập nhật, lỗi rollback.
- Các snapshot chụp trong lúc writer thay đổi liên tục.
- Deadlock, starvation và retry quá nhiều.

Stress test thành công rất có ích nhưng **không chứng minh** mọi lịch xen kẽ đều đúng; khi có thể, kết hợp kiểm chứng bất biến và công cụ race/model checking của hệ sinh thái.

## 22. Những nhầm lẫn thường gặp

1. **“`get` và `put` an toàn nên `get→if→put` cũng nguyên tử.”** Sai: có khe xen kẽ giữa các lời gọi.
2. **“Kết quả cuối đúng nghĩa là mọi lời gọi đúng.”** Sai: lost update có thể giấu hai lần thành công sai.
3. **“`sleep` trước khi ghi sẽ tránh race.”** Không có bảo đảm thứ tự lịch chạy như mong muốn.
4. **“Thêm một lần kiểm tra trước cập nhật là đủ.”** Nếu lần kiểm tra và commit vẫn tách rời, race vẫn tồn tại.
5. **“Một concurrent set không có bản ghi trùng thì email cũng chỉ gửi một lần.”** Sai: các luồng có thể cùng quyết định gửi.
6. **“`put_if_absent` bảo đảm callback tạo giá trị chỉ chạy một lần trong mọi thư viện.”** Phải kiểm tra hợp đồng cụ thể, nhất là với retry và tác dụng phụ.
7. **“`queue.empty()` quyết định lần `get()` ngay sau sẽ không chờ.”** Sai: consumer khác có thể lấy mục cuối.
8. **“`size()>0` rồi `pop()` của stack là một thao tác nguyên tử.”** Sai nếu là hai lời gọi riêng.
9. **“Khóa riêng bước đọc và riêng bước ghi là đủ.”** Không: phải bao trọn việc kiểm tra/ra quyết định/cập nhật.
10. **“Chỉ writer cần đồng bộ, reader tổng cứ đọc từng trường.”** Sai nếu cần snapshot một thời điểm logic.
11. **“Lock của một tiến trình bảo vệ dữ liệu ở mọi máy chủ.”** Không: cần giao dịch/ràng buộc của nguồn dữ liệu chung.
12. **“`SELECT` rồi `UPDATE` vô điều kiện giống một UPDATE có điều kiện.”** Không, vì điều kiện có thể đổi giữa hai câu lệnh.
13. **“CAS một biến tự bảo vệ được giao dịch trên nhiều biến.”** Không: bất biến đa trường cần giao thức phù hợp.
14. **“Đọc version rồi ghi là optimistic concurrency an toàn.”** Chưa đủ: check-and-commit phải nguyên tử.
15. **“Xóa/ghi trong mutex tự rollback khi ngoại lệ.”** Sai: mutex chỉ giải quyết xen kẽ, không tự hoàn tác.
16. **“Dùng khóa theo key thì không cần khóa cho thao tác nhiều key.”** Sai: phải bảo vệ đủ vùng tham gia bất biến và tránh deadlock.
17. **“Có GIL nghĩa là chuỗi Python nhiều dòng được thực hiện nguyên tử.”** Không có hợp đồng tổng quát như vậy.
18. **“Atomicity nghĩa là luôn cập nhật trạng thái mới nhất khi reader kết thúc.”** Snapshot có thể nhất quán nhưng cũ.
19. **“`O(1)` thao tác dữ liệu nghĩa là `O(1)` thời gian phản hồi.”** Chờ lock hoặc retry không nằm trong cận công việc cơ bản.
20. **“Vài nghìn lượt test không lỗi là đã loại trừ race.”** Không: lịch lỗi có thể hiếm, cần kiểm tra lịch có chủ đích và đặc tả.

## 23. Tự kiểm tra

**Câu 1.** `ConcurrentMap.get(k)` và `put(k,v)` đều tuyến tính hóa được. Vì sao `if get(k)==None: put(k,new)` chưa bảo đảm chỉ một luồng tạo giá trị?

**Đáp án:** Vì hai luồng có thể cùng đọc trạng thái vắng **trước** khi một lần ghi xảy ra. Tính nguyên tử của **mỗi lời gọi** không tự gộp chúng thành một giao dịch.

**Câu 2.** Có một chỗ, hai luồng cùng kiểm tra thấy còn chỗ rồi mỗi luồng giảm một lần. Hai bất biến nào dễ bị phá?

**Đáp án:** `remaining>=0` có thể bị phá, và `successes<=initial_stock` bị phá nếu cả hai đều trả thành công. Ngay khi giá trị cuối được ghi đè thành 0, số lần thành công vẫn có thể sai.

**Câu 3.** Mục đích của `Barrier(2)` trong ví dụ lỗi là gì? Có nên đặt nó trong cùng lock của kho không?

**Đáp án:** Nó ép hai luồng **cùng vượt qua kiểm tra** để tạo lịch xen kẽ xấu. Không nên đặt trong một lock chỉ cho một luồng vào, vì luồng kia không thể tới barrier và bài test tự deadlock.

**Câu 4.** Vì sao `reserve_if_available` phải kiểm tra số chỗ và trừ trong cùng đoạn găng?

**Đáp án:** Để điều kiện “còn đủ chỗ” vẫn đúng khi bước trừ được công bố. Nếu tách hai bước, luồng khác có thể dùng hết chỗ giữa chúng.

**Câu 5.** Hai phương thức `get_balance(A)`, `get_balance(B)` đều an toàn. Vì sao tổng có thể là 130 khi tổng thật luôn 100?

**Đáp án:** Reader có thể đọc A **trước** một lần chuyển khoản và B **sau** chuyển khoản. Hai giá trị hợp lệ riêng lẻ nhưng thuộc hai phiên bản khác nhau.

**Câu 6.** Concurrent set cuối cùng chỉ chứa một ID người học. Điều đó có chứng minh hệ thống chỉ gửi một email chào mừng không?

**Đáp án:** Không. Hai luồng có thể cùng thấy ID vắng rồi cùng lên lịch/gửi email. Cần thao tác đăng ký nguyên tử trả “vừa mới thêm” và giao thức tác dụng phụ phù hợp.

**Câu 7.** `Queue.empty()` trả `False`. `Queue.get()` ngay sau có chắc không bị chặn không?

**Đáp án:** Không. Một consumer khác có thể lấy mục cuối. Dùng `get_nowait()` và xử lý `Empty` hoặc `get(timeout=...)`.

**Câu 8.** Một đơn gồm 2 vé A và 1 vé B. Nếu A đủ nhưng B hết, phương thức `dat_gio` an toàn phải cập nhật kho thế nào?

**Đáp án:** **Không trừ bất kỳ mã nào** và trả thất bại. Quyết định cả giỏ hàng và bước trừ phải cùng nằm trong một ranh giới nguyên tử.

**Câu 9.** Trong vòng CAS đặt chỗ, hai luồng cùng thấy `old=1`. Có thể có hai CAS thành công đổi 1→0 mà không có lần nhập lại không?

**Đáp án:** Không, nếu CAS thật sự nguyên tử trên cùng biến. Chỉ một CAS đổi giá trị từ 1 thành 0; CAS sau với expected=1 phải thất bại.

**Câu 10.** Vì sao đọc `version=5` rồi ghi vài trường sau đó không tự là một optimistic transaction?

**Đáp án:** Vì writer khác có thể thay trạng thái sau lần đọc version. Phải có bước **kiểm tra version và commit nguyên tử**, đồng thời bảo đảm snapshot được đọc nhất quán.

**Câu 11.** Hai máy chủ cùng sửa kho trong một database. Vì sao `threading.Lock` của từng máy không đủ?

**Đáp án:** Mỗi lock chỉ điều phối luồng truy cập **đối tượng trong tiến trình của máy đó**. Hai tiến trình/máy cần cơ chế cập nhật có điều kiện, transaction/constraint của nguồn dữ liệu chung.

**Câu 12.** Đồ thị đơn có `has_arc(u,v)` và `add_arc(u,v)` đều an toàn riêng lẻ. Vì sao vẫn có thể tạo cung song song?

**Đáp án:** Hai luồng có thể cùng thấy cung chưa tồn tại rồi cùng thêm. Phải thực hiện `add_arc_if_absent` nguyên tử và cập nhật mọi chỉ mục liên quan trong cùng giao thức.

**Câu 13.** Khi đặt nhiều khóa cho thao tác chuyển giữa hai vùng, cần hai quy tắc quan trọng nào?

**Đáp án:** **Lấy đủ khóa cùng lúc** cho các vùng tham gia bất biến và **sắp khóa theo một thứ tự toàn cục**, đồng thời khử trùng khi hai vùng dùng cùng lock.

**Câu 14.** Tại sao không nên gọi thanh toán mạng trực tiếp trong callback `compute_if_absent` mà chưa hiểu hợp đồng thư viện?

**Đáp án:** Callback có thể bị gọi lại trong retry hoặc chạy lâu dưới khóa; tác dụng phụ có thể xảy ra nhiều lần hoặc khóa chặn lâu. Cần giao thức side effect/idempotency riêng.

**Câu 15.** Một cấu trúc dùng mutex cập nhật `edges` và `out` nhưng bị `MemoryError` trước khi cập nhật `in`. Sau khi nhả lock, trạng thái có tự đúng lại không?

**Đáp án:** Không. Mutex không tự rollback. Cần chuẩn bị/công bố nguyên tử, hoặc cơ chế hoàn tác khi lỗi; phải xử lý cả an toàn trước xen kẽ và an toàn trước thất bại.

**Câu 16.** Nếu chỉ chạy hàng nghìn test song song mà không thấy lỗi, có thể tuyên bố mọi lịch đều tuyến tính hóa được không?

**Đáp án:** Không. Cần tạo lịch kiểm tra có chủ đích, kiểm tra kết quả từng lời gọi và bất biến, đồng thời đối chiếu lịch sử với một đặc tả tuần tự hợp lệ.

**Ghi nhớ:** **Một chuỗi kiểm tra–cập nhật chỉ an toàn khi điều kiện được bảo vệ tới thời điểm thay đổi trạng thái.** `get`, `put`, `contains`, `empty` hay `pop` an toàn riêng lẻ **không làm** chuỗi `đọc → kiểm tra → hành động` trở thành nguyên tử. Hãy đưa **đơn vị nghiệp vụ** thành API ghép như `reserve_if_available` hoặc `add_arc_if_absent`, hay dùng lock, CAS, kiểm tra phiên bản/commit và transaction phù hợp. Người đọc nhiều trường cũng cần **snapshot nhất quán**; tác dụng phụ ngoài tiến trình cần giao thức riêng. Kiểm tra đúng đắn phải xét **kết quả từng lời gọi, bất biến toàn trạng thái, lịch xen kẽ, khả năng tiến triển và lỗi ngoại lệ** — không chỉ nhìn dữ liệu cuối cùng hay chạy thử khi ít tranh chấp.
