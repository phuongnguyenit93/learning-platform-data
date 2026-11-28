# Bảo vệ bất biến khi nhiều luồng cùng đọc hoặc cập nhật

## 1. Bất biến đúng sau một thao tác chưa chắc đúng khi thao tác bị xen kẽ

Giả sử một hệ thống có hai ví điện tử A và B, tổng tiền là 100 đơn vị. Người dùng chuyển 30 đơn vị từ A sang B. Trong chương trình một luồng, ta có thể viết:

```text
A = A - 30
B = B + 30
```

Nếu ban đầu A=70, B=30, kết quả đúng là A=40, B=60. **Tổng A+B vẫn bằng 100**.

Nhưng có một khoảng ngắn **giữa hai lệnh**: sau khi giảm A mà chưa tăng B, trạng thái trong bộ nhớ có thể là A=40, B=30. Nếu luồng báo cáo đọc hai số dư ngay lúc đó, nó sẽ thấy **tổng bằng 70**, một kết quả không tương ứng với bất kỳ giao dịch chuyển tiền đã hoàn thành nào.

Cấu trúc dữ liệu có thể hoàn toàn hợp lệ ở mức từng biến số nguyên, nhưng đã vi phạm **bất biến liên quan nhiều trường**.

Bài thuộc chương **Truy cập đồng thời**, kết nối kiến thức cấu trúc dữ liệu (mảng, danh sách liên kết, stack, queue, bảng băm, cây, đồ thị) với yêu cầu bảo toàn **bất biến, chi phí thao tác và trạng thái quan sát được** khi nhiều luồng cùng đọc/ghi.

**Mục tiêu:** sau bài này, bạn biết cách xác định bất biến, phân tích lịch xen kẽ, chọn phạm vi đồng bộ của người đọc và người ghi, bảo vệ chỉ mục liên quan, dùng snapshot/phiên bản khi phù hợp, và phân biệt tính đúng đắn với tốc độ dưới tranh chấp.

## 2. Bất biến là một mệnh đề về *toàn bộ trạng thái*

Gọi trạng thái của cấu trúc là `S`. **Bất biến (invariant)** là điều kiện `I(S)` mà mọi **trạng thái đã công bố hợp lệ** phải thỏa mãn.

Ví dụ:

| Cấu trúc | Bất biến tiêu biểu |
| --- | --- |
| Ví tiền hai tài khoản | Mỗi số dư không âm, tổng tiền không đổi khi chỉ có thao tác chuyển khoản |
| Stack | `size` bằng số phần tử có thể lấy theo chuỗi con trỏ từ `top` |
| Queue | `head/tail/size` cùng mô tả đúng các mục đang chờ |
| Danh sách liên kết đôi | Nếu `u.next = v` thì `v.prev = u` ở những nút liên quan |
| Bảng băm | Mỗi khóa đang hoạt động có thể được tìm lại theo quy tắc băm và thăm dò |
| Cây tìm kiếm | Quan hệ thứ tự khóa và các liên kết cha/con nhất quán |
| Đồ thị có hướng | Mỗi cung `e=(u→v)` có bản ghi trong `edges`, xuất hiện đúng ở `out[u]` và `in[v]` |
| Snapshot mảng/CSR | Offset không giảm, offset cuối bằng số mục dữ liệu và ID–chỉ số còn hợp lệ |

Với ví tiền chỉ có chuyển khoản:

\[
I(S) \equiv (A \ge 0) \land (B \ge 0) \land (A+B = C),
\]

trong đó `C` là tổng tiền cố định. Nếu có nạp/rút từ bên ngoài, phải mở rộng bất biến để tính những dòng tiền đó; không được tự giữ `C` cố định trong mọi nghiệp vụ.

Với đồ thị có hướng `G=(V,E)`:

\[
\sum_{u\in V}|out[u]| =
\sum_{v\in V}|in[v]| = |E|=m,
\]

khi mỗi chỉ mục lưu một ID cho mỗi cung đi ra/đi vào. Đây là **điều kiện cần nhưng chưa đủ**: còn phải kiểm tra **mỗi ID nằm đúng nguồn và đích**, kể cả khi có khuyên và cung song song.

**Quy tắc quan trọng:** bất biến là điều kiện của **toàn trạng thái logic**, không nhất thiết là điều kiện của một biến hay một lời gọi đơn lẻ.

## 3. Xen kẽ làm người đọc nhìn thấy trạng thái không nhất quán

Xét chuyển 30 từ A=70 sang B=30:

| Thời điểm | Luồng ghi T1 | Luồng đọc T2 | Trạng thái quan sát |
| --- | --- | --- | --- |
| 1 | Bắt đầu chuyển tiền | | A=70, B=30 |
| 2 | Ghi A=40 | | A=40, B=30 tạm thời |
| 3 | | Đọc A=40 | |
| 4 | | Đọc B=30 | T2 tính tổng 70 |
| 5 | Ghi B=60 | | A=40, B=60 |
| 6 | Kết thúc | | Tổng lại là 100 |

Kết quả tổng 70 là một **ảnh ghép hai phần của giao dịch chưa hoàn tất**.

Một lỗi khác xảy ra ngay cả khi từng lần đọc là nguyên tử:

```text
T2: đọc A=70
T1: chuyển 30 từ A sang B, hoàn thành (A=40, B=60)
T2: đọc B=60
T2: báo tổng = 130
```

Trong trường hợp thứ hai, người đọc không bắt gặp trạng thái bên trong giao dịch. Nó chỉ **đọc hai thời điểm khác nhau**. Vì vậy, bảo vệ từng phép đọc bằng một lock riêng rồi nhả lock giữa các lần đọc cũng **chưa đủ** nếu báo cáo yêu cầu **một snapshot nhất quán**.

Để tránh lỗi, phải xác định phạm vi của cả **người ghi lẫn người đọc**:

- Chuyển khoản cần cập nhật hai số dư như **một thao tác logic**.
- Báo cáo cần quan sát hai số dư **ở cùng một thời điểm logic**.
- Cả hai phải tuân thủ cùng một giao thức đồng bộ hoặc một cơ chế snapshot có bảo đảm tương đương.

## 4. Khái niệm nguyên tử, tuyến tính hóa và nhìn thấy bộ nhớ

### 4.1. Thao tác nguyên tử ở cấp API

Một thao tác **nguyên tử theo nghĩa trừu tượng** không cho những lời gọi khác quan sát trạng thái trung gian gây vi phạm hợp đồng. Trong một cài đặt dùng mutex, các bước bên trong đoạn găng vẫn xảy ra **tuần tự theo máy**, nhưng những lời gọi cùng tuân thủ khóa đó không được xen vào để quan sát nửa chừng.

**Atomicity không có nghĩa “một dòng lệnh”**. Đoạn `balance[A] -= amount; balance[B] += amount` gồm nhiều truy cập bộ nhớ, nhưng có thể là một thao tác nguyên tử theo API nếu được bảo vệ đúng.

### 4.2. Linearizability

Một lịch sử các lời gọi **tuyến tính hóa được (linearizable)** nếu có thể sắp các thao tác như thể mỗi thao tác xảy ra tại một điểm tức thời trong khoảng từ lúc được gọi đến khi trả kết quả, đồng thời giữ thứ tự thời gian thực của các lời gọi không chồng lấp.

Với ví tiền, từ góc nhìn người gọi, thao tác `transfer(A,B,30)` phải tạo một bước chuyển từ (70,30) sang (40,60), **không có** trạng thái công khai (40,30).

Lưu ý: **linearizability của từng phương thức không làm một chuỗi phương thức ghép bên ngoài tự thành giao dịch**. Hai lần gọi `get_balance(A)` và `get_balance(B)` riêng lẻ vẫn có thể phản ánh hai thời điểm khác nhau.

### 4.3. Visibility và happens-before

Loại trừ tương hỗ chưa phải toàn bộ câu chuyện. Các luồng còn phải có quy tắc **công bố và nhìn thấy** những thay đổi đã ghi. Trong nhiều mô hình bộ nhớ, thao tác release/acquire của lock và các primitive đồng bộ tạo quan hệ **happens-before** thích hợp.

Không nên tự dùng một biến Boolean `ready` không đồng bộ rồi suy luận rằng toàn bộ đối tượng đã sẵn sàng trên mọi runtime. Cũng không nên dựa vào một chi tiết cài đặt GIL của Python để chứng minh tính nguyên tử của chuỗi cập nhật nhiều trường.

**Nguyên tắc:** dùng hợp đồng đồng bộ được hỗ trợ của **ngôn ngữ/runtime/collection cụ thể**, không suy đoán từ thứ tự các dòng mã nguồn.

## 5. Khoanh vùng dữ liệu được bảo vệ và chủ sở hữu khóa

Một thiết kế dễ lý luận có:

```text
Đối tượng SoCai
  ├── _balances  (dict ID → số dư)
  ├── _version   (phiên bản của trạng thái)
  └── _lock      (bảo vệ CẢ _balances và _version)
```

**Hợp đồng của lớp:** các trường có dấu gạch dưới chỉ được truy cập khi đã giữ `_lock` hoặc thông qua các phương thức công khai đã thực hiện đồng bộ. Không trả trực tiếp dict nội bộ cho người gọi.

Các câu hỏi phải trả lời khi thiết kế:

1. **Bất biến nào thuộc về một đối tượng?** Ví dụ tổng tiền và không có số dư âm.
2. **Những trường nào tham gia cùng bất biến?** Nhiều số dư, version, các chỉ mục phụ.
3. **Ai có thể sửa chúng?** Chỉ các phương thức đã khóa, hay có đường đi vòng qua khóa?
4. **Người đọc cần thấy gì?** Một số dư tức thời, hay ảnh chụp nhiều số dư cùng phiên bản?
5. **Thao tác nào được phép thất bại?** Thiếu tiền, sai ID, lỗi tài nguyên hoặc callback bất ngờ.

**Không bao giờ coi việc gắn một lock vào đối tượng là đủ** nếu mã khác vẫn trực tiếp sửa `obj._balances` hoặc giữ một tham chiếu mutable tới dữ liệu bên trong. Khóa chỉ có hiệu lực khi **mọi đường truy cập cần đồng bộ đều tuân thủ cùng giao thức**.

## 6. Ví dụ Python: bảo toàn số dư và tổng tiền khi chuyển khoản

Ví dụ sử dụng `threading.Lock`; mọi số dư đều là số nguyên không âm. Không dùng số thực dấu phẩy động cho ví dụ tiền để tránh vấn đề sai số biểu diễn.

```python
from concurrent.futures import ThreadPoolExecutor
from threading import Lock


class SoCai:
    def __init__(self, initial):
        if not isinstance(initial, dict) or not initial:
            raise ValueError("Cần bảng tài khoản không rỗng")
        for account, amount in initial.items():
            if not isinstance(account, str) or not account:
                raise ValueError("ID tài khoản không hợp lệ")
            if type(amount) is not int or amount < 0:
                raise ValueError("Số dư phải là số nguyên không âm")

        self._balances = dict(initial)  # Không giữ tham chiếu dict đầu vào.
        self._version = 0
        self._lock = Lock()

    def transfer(self, source, target, amount, expected_version=None):
        if type(amount) is not int or amount <= 0:
            raise ValueError("Số tiền phải là số nguyên dương")
        if source == target:
            raise ValueError("Nguồn và đích phải khác nhau")

        # Cả kiểm tra điều kiện và hai lần ghi thuộc một đoạn găng.
        with self._lock:
            if source not in self._balances or target not in self._balances:
                raise KeyError("Tài khoản không tồn tại")
            if expected_version is not None:
                if expected_version != self._version:
                    return "XUNG_DOT"

            if self._balances[source] < amount:
                return "HET_TIEN"

            self._balances[source] -= amount
            self._balances[target] += amount
            self._version += 1
            return "OK"

    def snapshot(self):
        # Copy giá trị + version trong CÙNG một đoạn găng.
        # tuple gồm các cặp (str, int) không bị sửa qua API này.
        with self._lock:
            ver = self._version
            entries = tuple(self._balances.items())
        return ver, tuple(sorted(entries))

    def total(self):
        _, entries = self.snapshot()
        return sum(value for _, value in entries)


so_cai = SoCai({"A": 10, "B": 0})

with ThreadPoolExecutor(max_workers=2) as executor:
    results = list(executor.map(
        lambda _: so_cai.transfer("A", "B", 7), range(2)
    ))

print(sorted(results))       # ['HET_TIEN', 'OK']
print(so_cai.snapshot())     # (1, (('A', 3), ('B', 7)))
print(so_cai.total())        # 10

v, _ = so_cai.snapshot()     # v = 1
print(so_cai.transfer("B", "A", 2, expected_version=v))
# OK: chuyển thành A=5, B=5, version=2
print(so_cai.transfer("B", "A", 1, expected_version=v))
# XUNG_DOT: lần kiểm tra version=1 đã cũ.
print(so_cai.snapshot())     # (2, (('A', 5), ('B', 5)))
```

### Vì sao mẫu này giữ được bất biến?

- Hai lời gọi chuyển 7 cùng tranh **cùng một lock**. Khi lần đầu thành công, A chỉ còn 3, nên lần còn lại phải trả `"HET_TIEN"`.
- Không cam kết **luồng nào** thành công, chỉ cam kết **đúng một lần thành công**.
- Tổng A+B không đổi sau các chuyển khoản hoàn thành. `snapshot()` đọc bản sao của tất cả số dư và phiên bản ở **cùng một đoạn găng**, nên không ghép dữ liệu từ nhiều thời điểm.
- `expected_version` cho phép từ chối một quyết định dựa trên **snapshot cũ** thay vì âm thầm ghi đè cập nhật mới.
- Snapshot trả giá trị bất biến dạng tuple, không phơi lộ dict có thể thay đổi của lớp.

**Giới hạn minh họa:** lock bảo vệ dữ liệu trong **một đối tượng và một tiến trình**. Nó không đồng bộ hai máy chủ, cơ sở dữ liệu hoặc những bản sao riêng của `SoCai`. Mã cũng chưa xử lý khả năng khôi phục sau lỗi tài nguyên trong lúc cập nhật hai trường; mutex **không** tự cung cấp rollback hoặc tính bền vững.

## 7. Người đọc cũng phải tham gia giao thức nhất quán

Một API có thể có `read_A()` và `read_B()`, mỗi hàm giữ lock riêng rồi trả một số dư. Các hàm ấy có thể **an toàn riêng lẻ** nhưng biểu thức ngoài lớp:

```python
total = ledger.read_A() + ledger.read_B()
```

vẫn có thể ghép hai lần đọc khác thời điểm. Muốn tổng của **một thời điểm logic**, phải cung cấp API như `ledger.snapshot()` hoặc `ledger.total()` thực hiện đọc toàn bộ trạng thái liên quan dưới cùng cơ chế đồng bộ.

### Ba mức yêu cầu đọc

| Nhu cầu | Mức bảo đảm |
| --- | --- |
| Đọc một phần tử độc lập | Một phép đọc an toàn theo hợp đồng collection |
| Đọc nhiều trường phải tương quan | Một snapshot hoặc đoạn găng cho toàn bộ trường |
| Đọc một cấu trúc rất lớn trong thời gian dài | Snapshot có phiên bản, copy-on-write, hoặc giao thức đọc phù hợp |

Nếu chỉ cần hiển thị một thông tin ước lượng, ứng dụng có thể chấp nhận dữ liệu hơi cũ, **nhưng phải ghi rõ mô hình nhất quán**. Không thể áp dụng cùng giả định “đọc gần đúng được” cho báo cáo tài chính, cấu trúc cân bằng, khóa ngoại, hay quy trình cập nhật chỉ mục bắt buộc đồng bộ.

**Snapshot nông chưa chắc độc lập:** `dict(original)` sao chép các khóa và tham chiếu giá trị. Nếu giá trị là một `list` hoặc đối tượng mutable, cả bản sao lẫn bản gốc vẫn có thể chia sẻ cùng phần tử. Mã `SoCai` chỉ lưu `str → int` nên các cặp chụp bằng tuple có thể được xem là độc lập với những cập nhật số dư sau đó.

## 8. Nhiều bất biến liên quan: không thể khóa từng trường một cách tùy tiện

Một thiết kế có hai lock riêng, `lock_A` cho A và `lock_B` cho B, **chưa đủ** để làm chuyển khoản nguyên tử nếu thực hiện:

```text
lock_A
    A -= amount
unlock_A

lock_B
    B += amount
unlock_B
```

Người đọc tổng có thể chen giữa và thấy trạng thái tạm. Muốn dùng khóa phân tán, phải:

1. Xác định **toàn bộ dữ liệu tham gia thao tác**.
2. Nắm **đủ các khóa tương ứng cùng lúc** trước khi sửa hoặc đọc nhiều trường.
3. Dùng một **thứ tự khóa nhất quán toàn hệ thống** để tránh deadlock.
4. Giữ khóa tới khi **bất biến liên quan đã được khôi phục**.

Ví dụ với các tài khoản có ID có thể sắp thứ tự:

```text
keys = sort([source_id, target_id])

lock(keys[0])
lock(keys[1])
try:
    xác minh cả hai số dư
    cập nhật cả hai
finally:
    unlock(keys[1])
    unlock(keys[0])
```

Đó là **mã giả**, không phải cơ chế khóa giao dịch tự động của Python. Phải cài đúng cả việc thay đổi tập tài khoản, xóa tài khoản, reentrancy, lỗi khóa và người đọc toàn sổ cái.

**Một khóa chung** có thể kém khả năng song song hơn nhưng dễ chứng minh hơn. Đầu tiên hãy xây bản đúng với phạm vi khóa rõ ràng; chỉ giảm độ hạt khóa khi có dữ liệu đo lường cho thấy lock trở thành nút thắt.

## 9. Bảo vệ bất biến của danh sách liên kết, stack và queue

### 9.1. Danh sách liên kết đôi

Giả sử `A ↔ B`, chèn nút X vào giữa:

```text
Trước:  A.next = B, B.prev = A

Sau:
        A.next = X
        X.prev = A
        X.next = B
        B.prev = X
```

Bất biến mong muốn của các nút còn hoạt động:

\[
u.next=v \Longrightarrow v.prev=u,
\]

và tương tự chiều ngược lại theo chính sách nút đầu/cuối.

Khi cập nhật nhiều con trỏ, một người đọc duyệt ngược có thể nhìn thấy `A.next=X` nhưng `X.prev` chưa được gán, hoặc `B.prev` chưa được đổi. Nếu API cho phép người đọc duyệt đồng thời, cần bảo vệ cả **thao tác ghép liên kết** và **cách đọc**.

### 9.2. Stack

Một stack thường có `top` và `size`. Khi push:

```text
new.next = top
top = new
size += 1
```

Nếu một luồng pop chen vào giữa các bước, `top`, chuỗi nút và `size` có thể không còn khớp. Trong thiết kế dùng mutex, ranh giới push/pop phải bao trọn các trường liên quan.

### 9.3. Queue

Queue thường có `head`, `tail` và đôi khi `size` hoặc một mảng vòng với `head_index/tail_index`. Enqueue một mục có thể làm thay đổi **đuôi, liên kết cuối và bộ đếm**. Kiểm tra `if not queue.empty(): queue.get()` không an toàn thành một thao tác ghép khi có consumer khác.

Dùng API **`get_nowait()` và xử lý ngoại lệ rỗng**, hoặc blocking `get(timeout=...)` theo hợp đồng queue, thay vì suy ra kết quả tương lai từ `empty()`.

**Bài học chung:** chỉ vì thao tác `pointer = node` ngắn không có nghĩa chuỗi thay đổi nhiều con trỏ/counter trở nên nguyên tử.

## 10. Bảng băm: bất biến quan trọng khi chèn, xóa và rehash

Trong bảng băm, dữ liệu có thể nằm ở bucket hoặc vị trí thăm dò theo `hash(key)`. Khi đồng thời cập nhật:

- Chèn một khóa có thể sửa bucket, size và trạng thái ô.
- Xóa trong open addressing có thể tạo **tombstone**; không thể tùy tiện biến ô thành “chưa từng dùng” nếu làm đứt chuỗi thăm dò.
- Resize/rehash có thể phải cấp mảng mới và **di chuyển nhiều mục**; trong lúc đó có thể tồn tại hai bảng ở những giai đoạn khác nhau.
- Một khóa không nên “biến mất” khỏi cả hai bảng đối với người đọc theo hợp đồng nhất quán, chỉ vì đang chuyển chỗ.

### Ví dụ lịch lỗi khi rehash

```text
Writer: tạo table_new
Writer: chuyển một nửa các khóa sang table_new
Reader: thấy table_new và tìm khóa k chưa chuyển
Reader: kết luận k không tồn tại  ← sai
Writer: chuyển nốt và hoàn thành
```

Một cách đơn giản là:

1. Dựng `table_new` từ một trạng thái đầu vào **không thay đổi trong quá trình dựng**, hoặc có giao thức ghi thay đổi trong lúc dựng.
2. Chỉ **công bố** bảng mới khi nó đã hợp lệ.
3. Đảm bảo người đọc giữ được một phiên bản hợp lệ trong suốt truy vấn.
4. Thu hồi bảng cũ chỉ khi không còn người đọc cần nó, theo cơ chế vòng đời của runtime.

**Không nên suy ra rằng chỉ gán một tham chiếu bảng mới là giải pháp portable cho mọi ngôn ngữ**: việc công bố tham chiếu, hiển thị các dữ liệu được khởi tạo, quản lý bộ nhớ và thu hồi bảng cũ vẫn cần đồng bộ đúng.

Cấu trúc concurrent hash map có thể dùng khóa bucket, khóa phân đoạn, bảng phiên bản hoặc thuật toán chuyên biệt. Chọn cấu trúc có **hợp đồng cập nhật/duyệt rõ ràng** sẽ an toàn hơn tự chắp vá một hash map thường.

## 11. Cây và đồ thị: bất biến trải qua nhiều liên kết

### Cây tìm kiếm/cây cân bằng

Một phép xoay cây (rotation) có thể thay đổi **nhiều con trỏ cha/con** và đôi khi chiều cao, màu hoặc kích thước cây con. Nếu một luồng tìm kiếm đồng thời đi qua các con trỏ đang đổi, nó có thể đi sai nhánh, bỏ qua nút hoặc quan sát cây vi phạm thứ tự.

Ví dụ đối với BST:

\[
\forall x \in left(u): key(x)<key(u),
\quad
\forall y \in right(u): key(y)>key(u)
\]

trong mô hình không có khóa trùng. Với cây cân bằng, còn có bất biến màu/chiều cao. Người đọc không được mặc nhiên coi mỗi con trỏ mới là một phiên bản cây hợp lệ nếu writer chưa hoàn tất xoay và cập nhật metadata.

### Đồ thị có nhiều chỉ mục

Một đồ thị có hướng có thể lưu:

```text
vertices                 tập ID đỉnh
edges[eid] = (u, v)      bảng cung chuẩn
out[u]                   tập edge ID đi ra từ u
incoming[v]              tập edge ID đi vào v
```

Khi thêm cung `e=(u→v)`, phải thực hiện:

```text
edges[e] = (u, v)
out[u].add(e)
incoming[v].add(e)
```

Nếu người đọc truy vấn `out[u]` sau bước 2 và `incoming[v]` trước bước 3, nó có thể thấy cùng một cung **chỉ xuất hiện ở một phía**.

Để giữ nhất quán, có hai hướng cơ bản:

- Dùng **một khóa chung** cho những cập nhật và lần đọc cần thấy cả nhiều bảng; hoặc
- Dùng **snapshot/mô hình phiên bản** mà tất cả chỉ mục thuộc cùng trạng thái logic.

Nếu có **cung song song**, mỗi cung cần ID riêng, không được chỉ dùng cặp đầu mút làm khóa duy nhất. Nếu có **khuyên `u→u`**, ID phải có mặt ở cả `out[u]` và `incoming[u]` nhưng là một cung duy nhất trong `edges`.

## 12. Python: đồ thị cập nhật an toàn và đọc từ snapshot độc lập

Ví dụ dưới đây tập trung vào **bất biến đa chỉ mục** và việc tách **người đọc** khỏi các cập nhật dài. Bảng `_edges` là nơi chứa bản ghi `(source,target)`; hai bảng `_out` và `_incoming` chỉ lưu **edge ID**.

```python
from threading import Lock


class DoThiNhatQuan:
    def __init__(self):
        self._lock = Lock()
        self._vertices = set()
        self._edges = {}       # eid -> (source, target)
        self._out = {}         # source -> set(edge_id)
        self._incoming = {}    # target -> set(edge_id)
        self._next_eid = 0

    def them_dinh(self, u):
        if not isinstance(u, str) or not u:
            raise ValueError("ID đỉnh phải là chuỗi không rỗng")
        with self._lock:
            if u in self._vertices:
                raise ValueError("Đỉnh đã tồn tại")
            self._vertices.add(u)
            self._out[u] = set()
            self._incoming[u] = set()

    def them_cung(self, u, v):
        with self._lock:
            if u not in self._vertices or v not in self._vertices:
                raise KeyError("Đỉnh nguồn/đích không tồn tại")

            eid = self._next_eid
            self._next_eid += 1
            self._edges[eid] = (u, v)
            self._out[u].add(eid)
            self._incoming[v].add(eid)
            return eid

    def _xoa_cung_dang_khoa(self, eid):
        u, v = self._edges[eid]
        self._out[u].remove(eid)
        self._incoming[v].remove(eid)
        del self._edges[eid]

    def xoa_cung(self, eid):
        with self._lock:
            self._xoa_cung_dang_khoa(eid)

    def xoa_dinh(self, u):
        with self._lock:
            if u not in self._vertices:
                raise KeyError(u)
            # Khuyên có cùng ID ở out/in, chỉ xóa đúng một lần.
            lien_quan = self._out[u] | self._incoming[u]
            for eid in lien_quan:
                self._xoa_cung_dang_khoa(eid)
            del self._out[u]
            del self._incoming[u]
            self._vertices.remove(u)

    def thong_ke(self):
        # Tất cả trường của kết quả đến từ một trạng thái chung.
        with self._lock:
            m = len(self._edges)
            tong_ra = sum(len(ids) for ids in self._out.values())
            tong_vao = sum(len(ids) for ids in self._incoming.values())
            return m, tong_ra, tong_vao

    def snapshot(self):
        # Chỉ chứa kiểu bất biến (str, int, tuple), đã copy trong lock.
        with self._lock:
            vertices = frozenset(self._vertices)
            edge_records = tuple(
                (eid, u, v)
                for eid, (u, v) in self._edges.items()
            )
        return vertices, edge_records

    def kiem_tra_bat_bien(self):
        with self._lock:
            assert self._vertices == set(self._out)
            assert self._vertices == set(self._incoming)
            assert sum(map(len, self._out.values())) == len(self._edges)
            assert sum(map(len, self._incoming.values())) == len(self._edges)
            for eid, (u, v) in self._edges.items():
                assert u in self._vertices and v in self._vertices
                assert eid in self._out[u]
                assert eid in self._incoming[v]
            for u, ids in self._out.items():
                for eid in ids:
                    assert self._edges[eid][0] == u
            for v, ids in self._incoming.items():
                for eid in ids:
                    assert self._edges[eid][1] == v
            return True


g = DoThiNhatQuan()
for v in "ABCD":
    g.them_dinh(v)

e0 = g.them_cung("A", "B")
e1 = g.them_cung("A", "B")  # Cung song song.
e2 = g.them_cung("B", "C")
e3 = g.them_cung("C", "A")  # Chu trình.
e4 = g.them_cung("B", "B")  # Khuyên.

before = g.snapshot()
print(g.thong_ke())          # (5, 5, 5)
print(g.kiem_tra_bat_bien()) # True

g.xoa_dinh("B")
after = g.snapshot()
print(g.thong_ke())          # (1, 1, 1), chỉ còn e3: C -> A
print(after[0])              # frozenset({'A','C','D'}) (thứ tự không cố định)
print(after[1])              # ((3, 'C', 'A'),)
print(len(before[1]))        # 5: snapshot cũ không đổi.
print(g.kiem_tra_bat_bien()) # True
```

### Tại sao chỉ mục phải được cập nhật cùng một giao thức?

- Tạo `e0` và `e1` cùng A→B không làm mất cung song song vì mọi chỉ mục đều lưu **ID**.
- Xóa B dùng **hợp các tập ID** để khuyên e4 không bị xóa hai lần.
- Khi `thong_ke()` lấy khóa, nó không thể đọc `m` ở trạng thái mới nhưng `tong_vao` ở trạng thái cũ do thao tác cập nhật khác đang chạy.
- `snapshot()` trả bộ dữ liệu chỉ gồm những giá trị bất biến. Người đọc có thể dựng danh sách kề và chạy BFS từ bản sao mà **không giữ khóa ghi suốt quá trình duyệt**.
- Đỉnh D vẫn xuất hiện trong snapshot vì được giữ trong bảng V dù cô lập.

**Lưu ý giới hạn:** lock chỉ ngăn **luồng khác cũng tuân thủ lock** quan sát trạng thái trung gian. Nếu một thao tác gặp `MemoryError` sau khi đã thay đổi một phần chỉ mục, lock **không tự rollback**. Lớp cũng giả định không có mã nào sửa trực tiếp các thuộc tính nội bộ. `assert` phục vụ kiểm chứng khi phát triển, có thể bị vô hiệu hóa khi chạy Python với tùy chọn tối ưu hóa.

### Chi phí tạo snapshot

Với `n` đỉnh và `m` cung, sao chép bảng đỉnh/cung tốn `O(n+m)` thời gian và bộ nhớ cho mỗi snapshot. Người đọc có thể xử lý bản sao mà không tranh lock sau thời điểm chụp, nhưng **snapshot có thể đã cũ** khi xử lý xong.

Nếu nhiều người đọc và đồ thị rất lớn, có thể cần chiến lược khác: copy-on-write, cây/đồ thị bất biến, chỉ mục có phiên bản hoặc một read–write lock tùy yêu cầu. Các thiết kế ấy làm phức tạp việc công bố phiên bản và thu hồi bộ nhớ.

## 13. Optimistic concurrency: đọc phiên bản, xác thực rồi ghi

Không phải mọi thao tác cần giữ lock trong suốt quá trình tính toán. Một mẫu là:

1. **Chụp trạng thái** `S` và số phiên bản `v` một cách nhất quán.
2. Tính phương án thay đổi dự kiến ở ngoài khóa.
3. Khi chuẩn bị ghi, **kiểm tra phiên bản hiện tại vẫn bằng v** và thực hiện thay đổi như một giao dịch nhỏ.
4. Nếu phiên bản đã đổi, **từ chối hoặc tính lại** theo chính sách ứng dụng.

Mẫu `SoCai.transfer(..., expected_version=v)` ở mục 6 minh họa bước **kiểm tra phiên bản và ghi dưới cùng lock**:

```text
T1 đọc snapshot v=5
T2 cập nhật, phiên bản thành v=6
T1 đề nghị cập nhật dựa trên v=5
T1 kiểm tra dưới lock: 5 != 6 → XUNG_DOT
```

Đây là một hình thức **kiểm soát cập nhật lạc quan**, không đồng nghĩa với thuật toán lock-free.

**Không hợp lệ:** đọc `version` không đồng bộ rồi tự sửa nhiều trường khi thấy version “không đổi”. Phiên bản và cập nhật phải có một cơ chế **check-and-commit nguyên tử**; nếu không, hai writer có thể cùng xác nhận số phiên bản cũ và cùng ghi.

**Lưu ý về retry:** thao tác tạo đối tượng bên ngoài, trừ tiền thật hoặc gửi email có thể gây tác dụng phụ. Không nên đưa tác dụng phụ không thể hoàn tác vào đoạn tính thử sẽ phải chạy lại khi có xung đột. Nếu cần gửi sự kiện sau khi ghi thành công, phải thiết kế cơ chế ghi sự kiện/idempotency theo yêu cầu nghiệp vụ.

## 14. Immutable snapshot, copy-on-write và quản lý phiên bản

Một cách khác để bảo vệ người đọc là **không sửa trạng thái mà họ đang đọc**.

```text
              snapshot V1 (đầy đủ, bất biến)
Reader R1  ------------------------► dùng V1

Writer W: tạo V2 từ V1 → kiểm tra bất biến V2 → công bố V2

              snapshot V2 (đầy đủ, bất biến)
Reader R2  ------------------------► dùng V2
```

Lúc này, R1 và R2 có thể nhìn thấy hai phiên bản khác nhau, nhưng **mỗi người thấy một phiên bản nhất quán**.

Nguyên tắc để mô hình hoạt động:

- Không sửa các nút/cạnh/mảng mà một reader cũ còn dùng. Nếu cấu trúc có chia sẻ phần con, các phần được chia sẻ phải **thực sự bất biến**, không chỉ bất biến ở lớp vỏ.
- Việc **công bố phiên bản mới** phải có cơ chế đồng bộ đúng mô hình bộ nhớ và bảo đảm không bị công bố nửa chừng.
- Reader cần lấy được **một handle snapshot hợp lệ** trong suốt thời gian xử lý.
- Quản lý vòng đời của V1 sau khi công bố V2: không được thu hồi vùng nhớ khi vẫn còn reader sử dụng.

Với cấu trúc persistent tree, thay đổi thường chỉ tạo bản sao các nút trên đường cập nhật và dùng chung phần cây bất biến. Với đồ thị hoặc các chỉ mục phức tạp, hiệu quả phụ thuộc cấu trúc được chọn; không phải mọi phép cập nhật đều rẻ hay sao chép hằng số.

### Snapshot nhất quán không đồng nghĩa trạng thái mới nhất

Nếu reader đang duyệt V1 và writer đã công bố V2, kết quả BFS của reader là kết quả **trên V1**. Nó không phải kết quả mới nhất của V2, nhưng vẫn có thể **đúng theo hợp đồng snapshot**.

Điều này quan trọng với báo cáo, lập kế hoạch và xử lý phân tích nhiều phút: **tính nhất quán** và **tính cập nhật tức thời** là hai thuộc tính khác nhau.

## 15. Lỗi ngoại lệ: mutex không thay thế giao dịch hay rollback

Một đoạn cập nhật có khóa có thể vẫn gặp lỗi:

```text
with lock:
    cập nhật bảng cạnh
    cập nhật chỉ mục out
    LỖI CẤP PHÁT
    chưa cập nhật chỉ mục in
```

Sau khi thoát khỏi `with` do ngoại lệ, lock được nhả nhưng bất biến **vẫn bị phá**.

Các chiến lược cần cân nhắc:

1. **Xác thực trước:** từ chối ID sai, số tiền không đủ, cặp đầu mút không tồn tại trước khi sửa.
2. **Chuẩn bị dữ liệu ngoài vùng trạng thái chung:** cấp phát đối tượng/bộ đệm cần thiết trước khi thay đổi dữ liệu đang công bố.
3. **Tạo bản sao hợp lệ rồi công bố:** phù hợp với copy-on-write khi chi phí sao chép chấp nhận được.
4. **Rollback có kịch bản rõ:** nếu thất bại giữa các bước, hoàn tác tất cả thay đổi đã làm; bản thân rollback cũng cần được thiết kế cho lỗi và tình huống bất thường.
5. **Giao dịch của hệ quản trị dữ liệu:** khi thông tin nằm trong cơ sở dữ liệu, dùng cơ chế transaction/constraint tương ứng thay vì chỉ mutex trong một tiến trình.

**Không được hứa rằng mọi chương trình dùng `with lock` đều có tính nguyên tử trước crash hoặc sự cố nguồn điện**. Mutex giải quyết cạnh tranh truy cập trong bộ nhớ, không mặc nhiên đảm bảo khôi phục, lưu bền hay đúng khi nhiều tiến trình/máy cùng sửa.

## 16. Condition: bất biến của trạng thái chờ cũng phải được bảo vệ

Giả sử một queue có giới hạn dung lượng. Điều kiện cho phép producer đưa thêm phần tử là:

\[
len(queue) < capacity.
\]

Khi queue đầy, producer phải chờ. Nhưng việc chờ phải gắn với **cùng lock bảo vệ queue**:

```python
from collections import deque
from threading import Condition


class HangDoiGioiHan:
    def __init__(self, capacity):
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("capacity phải dương")
        self._capacity = capacity
        self._items = deque()
        self._cv = Condition()

    def put(self, value):
        with self._cv:
            while len(self._items) >= self._capacity:
                self._cv.wait()      # Nhả lock khi đợi, lấy lại khi thức.
            self._items.append(value)
            self._cv.notify_all()

    def get(self):
        with self._cv:
            while not self._items:
                self._cv.wait()
            result = self._items.popleft()
            self._cv.notify_all()
            return result
```

Dùng **`while`**, không chỉ `if`, vì sau khi luồng thức dậy và giành lại lock, luồng khác có thể đã thay đổi queue. Primitive condition cũng có thể cho phép các lần thức dậy cần **kiểm tra lại điều kiện**.

`wait()` nhả lock trong lúc chờ để producer/consumer khác có thể thay đổi điều kiện. Nếu giữ lock khi chờ, bên còn lại có thể không bao giờ làm điều kiện trở thành đúng.

Ví dụ là bản tối giản, **chưa có giao thức đóng queue, timeout, hủy tác vụ hoặc công bằng**. Trong Python, `queue.Queue` thường phù hợp hơn khi cần producer–consumer thông thường.

## 17. Deadlock, starvation và thứ tự khóa trong thao tác đa đối tượng

### Deadlock

```text
T1: khóa A, chờ khóa B
T2: khóa B, chờ khóa A
```

Hai luồng có thể chờ nhau vô hạn. Một quy tắc phòng tránh cơ bản là **thứ tự khóa toàn cục** (ví dụ theo ID tài khoản tăng dần). Mọi đường mã muốn khóa A và B phải lấy cùng thứ tự.

### Starvation

Ngay cả khi không deadlock, một luồng có thể liên tục thua tranh chấp và chờ rất lâu. `Lock` thông thường không tự cung cấp hợp đồng công bằng FIFO. Một thao tác có phần xử lý `O(1)` vẫn có thể có **thời gian phản hồi không có cận hữu hạn** nếu phải chờ lock hoặc bị hệ điều hành tạm dừng.

### Callback và tái nhập

Không nên tùy tiện gọi callback của người dùng khi đang giữ khóa nội bộ: callback có thể gọi ngược vào cùng cấu trúc, cố lấy lock khác hoặc chờ một luồng đang cần khóa hiện tại.

`RLock` cho phép **cùng một luồng** lấy lại cùng khóa nhiều lần, nhưng không chữa deadlock giữa những khóa **khác nhau**. Nếu dùng RLock, vẫn cần xác định rõ thứ tự khóa, trạng thái trung gian và điểm các bất biến được khôi phục.

## 18. Chi phí: số bước thuật toán khác thời gian phải chờ

Giả sử bảng hash và set có tra cứu `O(1)` kỳ vọng. Một thao tác thêm cung vào ba bảng có số bước kỳ vọng hằng số, **khi không tranh chấp và không cần mở rộng cấu trúc lớn**. Nhưng khi nhiều luồng chạy:

\[
T_{\text{phản hồi}}
\approx T_{\text{chờ khóa}} + T_{\text{thao tác}} + T_{\text{điều phối}}.
\]

`T_chờ khóa` không được Big-O của bảng hash bao phủ.

| Thiết kế | Công việc cơ bản | Đánh đổi đồng thời |
| --- | --- | --- |
| Một mutex cho toàn cấu trúc | Đọc/ghi đơn giản, bất biến dễ chứng minh | Nhiều reader có thể phải chờ writer và ngược lại |
| Khóa cho từng phần/bucket | Thao tác trên phần độc lập có thể song song | Thao tác nhiều phần cần thứ tự khóa và giao thức nhất quán |
| Read–write lock | Cho phép nhiều đọc đồng thời khi không có writer | Có chi phí quản lý, chính sách ưu tiên và nguy cơ starvation |
| Copy-on-write | Người đọc snapshot không bị writer sửa tại chỗ | Sao chép, công bố phiên bản, quản lý bộ nhớ |
| Optimistic version check | Tránh giữ lock trong giai đoạn tính thử | Có thể nhiều lần retry dưới tranh chấp |
| Cấu trúc lock-free | Một số bảo đảm tiến triển không phụ thuộc mutex | Cần chứng minh memory ordering, ABA và vòng đời bộ nhớ |

Ví dụ với đồ thị ở mục 12:

- Thêm một cung vào `dict` và hai `set`: `O(1)` kỳ vọng/phân bổ nếu ID đã hợp lệ.
- Xóa đỉnh với `p` cung ra và `q` cung vào: `O(p+q)` kỳ vọng, nhờ hai chỉ mục và hợp ID.
- Kiểm tra toàn bộ bất biến bằng quét các bảng: `O(n+m)` kỳ vọng.
- Chụp snapshot: `O(n+m)` thời gian/bộ nhớ.
- BFS/DFS trên danh sách kề dựng từ snapshot: `O(n+m)` cho duyệt toàn đồ thị.

Nếu kiểm tra **mọi bất biến toàn bộ** sau **mỗi lần thêm cung** dưới lock, chi phí mỗi thao tác không còn `O(1)` kỳ vọng. Có thể kiểm tra chi tiết trong test, định kỳ, hoặc theo mẫu, tùy mức tin cậy cần thiết.

**Không nên đánh đổi tính đúng đắn lấy tốc độ bằng cách bỏ đồng bộ chỉ vì benchmark ít tranh chấp cho kết quả nhanh hơn.**

## 19. Kiểm thử bất biến khi lịch thực thi khó đoán

Một bài test đồng thời hiệu quả nên có nhiều lớp:

### 19.1. Mô hình tham chiếu tuần tự

Xây một phiên bản **đơn luồng**, dễ kiểm tra của cùng API. Khi chạy nhiều thao tác có kết quả trả về, đối chiếu xem lịch sử đó có thể tương đương với **một thứ tự tuần tự hợp lệ** (theo đặc tả) hay không.

Đối với linearizability, còn phải giữ thứ tự của các lời gọi **không chồng lấp thời gian**. Kiểm tra chỉ tổng kết quả cuối chưa đủ để chứng minh lịch sử tuyến tính hóa được.

### 19.2. Xen kẽ có chủ đích

Dùng `Barrier`, hook kiểm thử hoặc bộ lập lịch mô phỏng để ép hai luồng cùng đọc dữ liệu trước khi một luồng ghi. Điều này giúp tái hiện lost update, check-then-act hoặc trường hợp người đọc ghép nhiều thời điểm.

Không đặt barrier không thể hoàn thành bên trong một đoạn găng mà luồng còn lại phải vào cùng khóa mới tới được barrier: bài test có thể **tự tạo deadlock** không phản ánh lỗi ban đầu.

### 19.3. Kiểm tra theo bất biến

Sau chuỗi cập nhật có thể kiểm tra:

- Không số dư nào âm; tổng tiền ban đầu bằng tổng hiện hành khi chỉ có chuyển khoản.
- `sum(out_degrees)=sum(in_degrees)=m` trong đồ thị có hướng.
- Mọi edge ID ở `out` và `in` đều trỏ đúng đầu mút trong `edges`.
- Không còn cung trỏ tới đỉnh đã bị xóa.
- Snapshot không thay đổi sau khi bản chuẩn được cập nhật.
- Dữ liệu mà người đọc nhận được tương ứng với **một phiên bản hợp lệ**.

Hãy kiểm tra **theo từng ID và liên kết**, không chỉ kiểm tra số lượng. Hai lỗi khác nhau có thể làm số tổng vẫn bằng nhau.

### 19.4. Kiểm tra khả năng tiến triển

Test cả trường hợp:

- Có nhiều reader và một writer.
- Nhiều writer tranh cùng khóa nóng.
- Queue đầy, queue rỗng, luồng bị hủy, thao tác có timeout.
- Một thao tác cần hai khóa theo nhiều thứ tự đầu vào.
- Reader giữ snapshot cũ trong lúc writer cập nhật nhiều lần.

Stress test là công cụ quan trọng nhưng **không chứng minh không còn race**. Với hệ sinh thái phù hợp, dùng thêm race detector, model checker hoặc kiểm tra lịch sử theo đặc tả.

## 20. Những ngộ nhận thường gặp

1. **“Một biến có đọc/ghi nguyên tử thì bất biến nhiều biến tự đúng.”** Sai: bất biến trải trên nhiều biến cần giao thức chung.
2. **“Writer dùng lock là đủ, reader cứ đọc trực tiếp.”** Sai khi reader cần nhìn trạng thái nhất quán và không có cơ chế đọc khác.
3. **“Mỗi hàm get_balance có lock, vậy get_A()+get_B() là snapshot.”** Sai: hai lời gọi có thể đọc hai thời điểm khác nhau.
4. **“Hai lock riêng cho hai tài khoản bảo đảm chuyển khoản nguyên tử.”** Chưa đủ nếu không giữ **cả hai** trong cùng giai đoạn giao dịch.
5. **“Có lock thì lỗi cấp phát sẽ rollback.”** Sai: mutex không tự hoàn tác những thay đổi đã thực hiện.
6. **“Một dict copy luôn tạo snapshot sâu.”** Sai: bản sao nông có thể còn chia sẻ các giá trị mutable.
7. **“Trạng thái sau cập nhật đúng thì mọi reader giữa chừng chắc chắn đúng.”** Sai: reader có thể thấy trạng thái trung gian.
8. **“Bảng băm rehash có thể công bố bảng mới ngay khi chuyển nửa khóa.”** Sai: reader có thể tìm hụt khóa chưa chuyển.
9. **“Xóa đỉnh chỉ cần xóa danh sách cung đi ra.”** Sai: còn các cung đi vào và những chỉ mục khác.
10. **“Mọi cung về cùng cặp đầu mút là một cung.”** Sai trong đa đồ thị: edge ID khác nhau vẫn là liên kết khác nhau.
11. **“Cung khuyên trong out/in phải xóa hai lần.”** Sai: một cung ID xuất hiện ở hai chỉ mục, nên khử trùng ID khi xóa liên đới.
12. **“Version check trước lock đủ tránh cập nhật cũ.”** Sai: kiểm tra phiên bản và commit phải nằm trong một giao thức nguyên tử.
13. **“Copy-on-write nghĩa là người đọc luôn nhận trạng thái mới nhất.”** Sai: có thể giữ một snapshot cũ nhưng nhất quán.
14. **“RLock ngăn được mọi deadlock.”** Sai: còn thứ tự giữa nhiều khóa và callback.
15. **“Có GIL nên mọi thao tác đa trường của Python đều nguyên tử.”** Không có hợp đồng như vậy cho các quy trình ghép.
16. **“O(1) thao tác đồng nghĩa O(1) thời gian chờ dưới tranh chấp.”** Sai: thời gian chờ phụ thuộc lịch thực thi và các luồng khác.
17. **“Kiểm tra tổng độ lớn của hai chỉ mục là đủ chứng minh đồ thị nhất quán.”** Sai: cần kiểm tra ID đúng đầu mút.
18. **“Một stress test chạy thành công là chứng minh thread-safe.”** Không: có thể chưa gặp lịch gây lỗi.
19. **“Lấy lock một lần rồi gọi mạng/email trong lock luôn an toàn hơn.”** Có thể giữ lock quá lâu, gây deadlock hoặc chặn các luồng khác; cần tách tác dụng phụ và thiết kế giao thức.
20. **“Snapshot chỉ là bản copy, không cần xét phiên bản dữ liệu.”** Khi yêu cầu kết quả mới nhất hoặc hợp nhất nhiều snapshot, phiên bản và thời điểm công bố rất quan trọng.

## 21. Tự kiểm tra

**Câu 1.** Bất biến của hai tài khoản A và B khi chỉ có chuyển khoản nội bộ là gì?

**Đáp án:** Tổng `A+B=C` không đổi và mỗi số dư không âm theo hợp đồng nghiệp vụ. Mọi thao tác chuyển thành công phải giữ các điều kiện này.

**Câu 2.** Luồng T1 đọc A=70; T2 chuyển 30 từ A sang B và hoàn thành; T1 đọc B=60. Vì sao tổng T1 tính là 130 dù không đọc trúng trạng thái giữa giao dịch?

**Đáp án:** Vì T1 đã ghép **hai lần đọc tại hai thời điểm khác nhau**. Muốn một tổng nhất quán phải đọc hai số dư trong cùng snapshot hoặc cơ chế đồng bộ tương đương.

**Câu 3.** Hai hàm `get_A()` và `get_B()` đều có mutex riêng. Biểu thức `get_A()+get_B()` có tự là giao dịch nguyên tử không?

**Đáp án:** Không. Mutex của mỗi lời gọi chỉ bảo vệ phạm vi lời gọi đó; giữa hai lời gọi một chuyển khoản có thể diễn ra.

**Câu 4.** Trong ví dụ `SoCai`, có 10 đơn vị ở A và 0 ở B. Hai luồng cùng yêu cầu chuyển 7 từ A sang B. Số lần thành công là bao nhiêu?

**Đáp án:** **Một**. Sau lần thành công đầu, A còn 3, nên lần còn lại trả `"HET_TIEN"`; tổng vẫn là 10.

**Câu 5.** `expected_version` giúp giải quyết vấn đề gì, và vì sao phải kiểm tra cùng lúc commit?

**Đáp án:** Nó giúp từ chối **quyết định dựa trên snapshot đã cũ**. Nếu kiểm tra trước rồi nhả đồng bộ trước khi commit, writer khác có thể thay trạng thái giữa hai bước, gây cập nhật sai.

**Câu 6.** Trong danh sách liên kết đôi, việc thay `A.next=X` nhưng chưa thay `X.prev=A` vi phạm bất biến nào?

**Đáp án:** Bất biến hai chiều `u.next=v ⇒ v.prev=u`. Reader duyệt trong lúc cập nhật dở có thể thấy cấu trúc không nhất quán.

**Câu 7.** Khi bảng băm mở rộng, tại sao không thể cho reader chỉ tra bảng mới khi writer mới chuyển một nửa các khóa?

**Đáp án:** Khóa có thể vẫn nằm trong bảng cũ nên reader kết luận sai rằng nó không tồn tại. Cần một giao thức chuyển/giao phiên bản mà người đọc chỉ thấy trạng thái hợp lệ.

**Câu 8.** Đồ thị có `edges/out/in`. Khi thêm `e=(u→v)`, những bản ghi nào phải cùng hiện diện trong trạng thái công bố?

**Đáp án:** `edges[e]`, `out[u]` và `in[v]`, cùng các chỉ mục/bộ đếm liên quan. Mỗi ID phải đúng nguồn và đích.

**Câu 9.** Một đỉnh B có một khuyên e3. Vì sao dùng `out[B] | in[B]` khi xóa B?

**Đáp án:** Khuyên e3 có trong cả hai tập, nhưng chỉ là **một cung**. Hợp tập giúp xóa đúng một lần; cung song song khác ID vẫn được xử lý riêng.

**Câu 10.** Một snapshot đồ thị chứa các tuple `(eid,source,target)` được sao chép trong lock. Có thể chạy BFS ngoài lock không, và có bảo đảm mới nhất không?

**Đáp án:** Có thể dựng danh sách kề từ snapshot và chạy BFS ngoài lock nếu các giá trị snapshot không thay đổi. Kết quả **nhất quán với snapshot**, không nhất thiết là trạng thái mới nhất khi BFS kết thúc.

**Câu 11.** Vì sao `dict(original)` có thể không đủ để tạo snapshot độc lập?

**Đáp án:** Vì đó là bản sao nông: các đối tượng mutable nằm trong giá trị có thể vẫn dùng chung với dict gốc. Cần sao chép hoặc bất biến hóa theo đúng cấu trúc dữ liệu.

**Câu 12.** Dùng `with lock` rồi cập nhật một nửa bảng chỉ mục trước khi có `MemoryError` có tự khôi phục trạng thái cũ không?

**Đáp án:** Không. Mutex ngăn thao tác khác xen vào khi lock đang giữ, nhưng không tự rollback. Cần kế hoạch rollback hoặc dựng bản mới rồi công bố sau khi đã hợp lệ.

**Câu 13.** Khi dùng nhiều khóa cho hai tài khoản, cách cơ bản nào giúp giảm nguy cơ deadlock?

**Đáp án:** Quy định **thứ tự lấy khóa toàn cục**, chẳng hạn theo ID tài khoản tăng dần, và mọi đường mã đều tuân thủ thứ tự đó.

**Câu 14.** Một thao tác có `O(1)` bước làm việc nhưng phải chờ mutex. Thời gian phản hồi có chắc `O(1)` không?

**Đáp án:** Không. Phần việc của thao tác và thời gian chờ khóa/lịch lập lịch là khác nhau; chờ có thể lâu hoặc không có cận hữu hạn khi bị starvation.

**Câu 15.** Chạy 10.000 lượt thử concurrent không gặp lỗi có chứng minh cấu trúc đúng với mọi lịch xen kẽ không?

**Đáp án:** Không. Những lịch gây lỗi có thể hiếm; cần kiểm tra bất biến, tạo lịch thử có chủ đích, so sánh với đặc tả và sử dụng công cụ kiểm chứng phù hợp.

**Ghi nhớ:** **Bảo vệ bất biến là bảo vệ toàn bộ trạng thái logic, không chỉ từng biến hoặc từng lời gọi.** Khi một thao tác sửa nhiều trường, phải giữ chúng nhất quán đối với người đọc và người ghi khác. Khi người đọc cần nhiều trường tương quan, hãy dùng **cùng một snapshot hoặc ranh giới đồng bộ**. Với bảng băm, cây, danh sách liên kết, queue và đồ thị nhiều chỉ mục, những cập nhật tưởng nhỏ có thể tạm phá bất biến nếu xen kẽ sai. Mutex, khóa theo vùng, kiểm tra phiên bản, copy-on-write và snapshot đều có ưu/nhược điểm; lựa chọn phải dựa trên **hợp đồng quan sát, chi phí cập nhật, khả năng tiến triển và mô hình bộ nhớ**. Cuối cùng, đừng nhầm **mutex với rollback**, **snapshot nhất quán với dữ liệu mới nhất**, hay **Big-O của thao tác với thời gian chờ dưới tranh chấp**.
