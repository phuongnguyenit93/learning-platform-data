# Khóa toàn cấu trúc, khóa từng vùng và đánh đổi mức tranh chấp

## 1. Vì sao phạm vi khóa ảnh hưởng cả tính đúng lẫn hiệu năng?

Một hệ thống quản lý học phần có bảng băm lưu hàng triệu lượt đăng ký. Hai nhân viên đồng thời cập nhật hai học phần **không liên quan**: người thứ nhất xử lý lớp A, người thứ hai xử lý lớp Z.

Nếu cả bảng chỉ có **một khóa (lock) chung**, thao tác trên A phải chờ thao tác trên Z hoàn tất, dù chúng không sửa chung mục dữ liệu nào. Đây là điểm yếu của **khóa toàn cấu trúc (coarse-grained locking)**: dễ giữ bất biến nhưng có thể giới hạn mức song song.

Nếu mỗi học phần có **một khóa riêng**, hai thao tác có thể tiến hành đồng thời. Tuy nhiên, khi một thao tác cần chuyển một sinh viên từ lớp A sang lớp Z, nó lại liên quan **hai vùng dữ liệu**. Khóa riêng từng vùng mà không có giao thức phối hợp có thể khiến sinh viên xuất hiện ở cả hai lớp, không ở lớp nào, hoặc gây deadlock.

Bài này phân tích **khóa toàn cấu trúc, khóa từng vùng, khóa theo bucket/đỉnh, khóa phân đoạn (striped locking)** và những đánh đổi khi nhiều luồng truy cập mảng, danh sách liên kết, bảng băm, cây, queue hoặc đồ thị. Ta chú ý hai câu hỏi phải được trả lời đồng thời:

1. **Đúng đắn:** mọi trạng thái được công bố và mọi kết quả đọc có tuân thủ bất biến của cấu trúc không?
2. **Hiệu năng:** bao nhiêu thao tác độc lập thực sự có thể thực thi cùng lúc, và chi phí quản lý khóa có lớn hơn lợi ích giảm tranh chấp không?

**Mục tiêu học tập:** biết xác định tài nguyên mà một thao tác chạm tới, chọn phạm vi khóa phù hợp, lấy nhiều khóa không bị đảo thứ tự, xử lý truy vấn toàn cục và thay đổi cấu trúc, phân tích thời gian chờ cùng chi phí thuật toán, và thiết kế thử nghiệm đánh giá thực tế.

## 2. Từ vựng và các bất biến cần bảo vệ

Trong bài, `n` là số phần tử/đỉnh và `m` là số cạnh/cung nếu ví dụ nói về đồ thị. **Vùng (region)** có thể là một bucket bảng băm, nhóm bucket, một nút, một đoạn mảng, một phân vùng tài khoản hoặc một cây con. Nó **không nhất thiết trùng** với ranh giới địa chỉ bộ nhớ vật lý.

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Mutex/lock** | Cho phép một chủ sở hữu tại một thời điểm vào đoạn găng đã được bảo vệ |
| **Critical section (đoạn găng)** | Những thao tác đọc/ghi phải phối hợp để giữ bất biến |
| **Coarse-grained lock** | Một khóa bảo vệ toàn bộ cấu trúc hoặc một miền rất rộng |
| **Fine-grained lock** | Nhiều khóa, mỗi khóa bảo vệ một vùng nhỏ hơn |
| **Striped lock** | Một số khóa cố định, mỗi khóa bảo vệ **nhiều** bucket/khóa dữ liệu theo hàm ánh xạ |
| **Contention (tranh chấp)** | Hai hoặc nhiều luồng cần cùng một khóa khi thao tác chồng lấp |
| **Lock ordering** | Quy định thứ tự toàn cục khi cần lấy nhiều khóa |
| **Linearizability** | Mỗi thao tác công khai có thể xem như xảy ra tại một điểm logic trong khoảng gọi–trả |
| **Snapshot nhất quán** | Các trường được đọc phản ánh **cùng một phiên bản hợp lệ** của trạng thái |

Ví dụ hai tài khoản A và B, chỉ cho phép chuyển tiền nội bộ:

\[
balance[A] \ge 0,\quad balance[B] \ge 0,
\quad balance[A]+balance[B]=C.
\]

Với bảng băm, một khóa `k` có thể được tìm đúng theo quy tắc bucket/probe; không được để người đọc nhìn thấy cấu trúc đang rehash nửa chừng như đã hoàn tất. Với đồ thị có hướng, nếu có cung `e=(u\to v)` thì cả `out[u]` và `in[v]` phải tham chiếu đúng tới `edge_id=e` trong bảng cạnh chuẩn.

**Khóa được chọn theo phạm vi bất biến**, không phải theo số dòng mã. Một phép cập nhật có thể là hai dòng nhưng cần bảo vệ cùng lúc nhiều vùng; một phép duyệt dài có thể chỉ đọc snapshot bất biến nên không cần cầm khóa ghi trong toàn bộ quá trình.

## 3. Khóa toàn cấu trúc: một quy tắc, một điểm đồng bộ

Thiết kế đơn giản nhất:

```text
Cấu trúc Map
┌───────────────────────────────────────────┐
│ lock_toan_bo                              │
│                                           │
│ bucket 0   bucket 1   ...    bucket 999  │
│                                           │
│ size, capacity, metadata, các chỉ mục    │
└───────────────────────────────────────────┘
```

Mọi thao tác truy cập trạng thái mutable phải theo cùng giao thức:

```text
add(k, v):
    lock(map_lock)
    xác nhận k hợp lệ
    cập nhật bucket của k, size và metadata
    unlock(map_lock)

find(k):
    lock(map_lock)
    đọc bucket và kết quả
    unlock(map_lock)
```

### Ưu điểm

- **Dễ suy luận bất biến:** không ai qua cùng API quan sát dữ liệu giữa các bước khi writer giữ khóa.
- **Dễ kết hợp nhiều trường:** size, bucket và bảng dữ liệu được cập nhật cùng đoạn găng.
- **Dễ hỗ trợ thao tác toàn cục:** xóa hết, resize, chụp snapshot và kiểm tra cấu trúc.
- **Ít quy tắc khóa hơn:** không phải tính thứ tự cho nhiều khóa hoặc bảo vệ vòng đời hàng trăm lock.

### Hạn chế

- Hai thao tác trên **hai khóa khác nhau** vẫn có thể phải chờ cùng mutex.
- Một phép xử lý dài hoặc chụp snapshot có thể khiến mọi cập nhật khác chờ.
- Khi số luồng tăng, **thời gian chờ khóa** có thể tăng nhanh hơn thời gian làm việc bên trong.
- Một luồng bị tạm dừng khi đang giữ mutex có thể kéo dài thời gian chờ của toàn cấu trúc.

Trong thiết kế có một mutex độc quyền, **một thời điểm tối đa một luồng nằm trong đoạn găng**. Nhưng không phải mọi câu lệnh của chương trình đều nằm trong đoạn găng: việc xử lý dữ liệu bất biến ở bên ngoài có thể song song.

**Một khóa chung không mặc nhiên là “chậm”.** Với dữ liệu nhỏ, đoạn găng rất ngắn, ít luồng hoặc hầu hết thao tác độc lập với lock, sự đơn giản của nó có thể mang lại hiệu năng và độ tin cậy tốt hơn thiết kế khóa chi tiết.

## 4. Một lịch xen kẽ: tăng khả năng song song nhưng phải giữ bất biến

Giả sử bảng điểm có hai mục A và Z, mỗi mục cần tăng một lần.

### Dùng một khóa chung

```text
T1: lock(global) ─ cập nhật A ─ unlock
T2:             chờ .......... lock(global) ─ cập nhật Z ─ unlock
```

Hai cập nhật độc lập vẫn phải tuần tự hóa vì dùng cùng khóa.

### Dùng hai khóa bảo vệ hai vùng độc lập

```text
T1: lock(L_A) ─ cập nhật A ─ unlock
T2: lock(L_Z) ─ cập nhật Z ─ unlock
                  ↑ có thể chồng lấp thời gian
```

Về lý thuyết, hai đoạn găng có thể thực thi đồng thời. Nhưng xét thao tác **chuyển 3 điểm thưởng từ A sang Z**, nếu thực hiện:

```text
lock(L_A) → A -= 3 → unlock(L_A)
lock(L_Z) → Z += 3 → unlock(L_Z)
```

thì một reader có thể thấy tổng bị giảm 3 trong lúc chuyển. **Khóa từng vùng không đủ nếu một thao tác cần bất biến trải trên nhiều vùng.**

Để thực hiện một chuyển khoản theo hợp đồng nguyên tử, writer cần bảo vệ **cả A và Z trong cùng giai đoạn**; reader muốn đọc tổng hai vùng cũng phải quan sát một snapshot chung hoặc theo cơ chế tương đương.

## 5. Các mức độ hạt khóa và hệ quả

| Mức khóa | Phạm vi được bảo vệ | Khả năng song song | Độ phức tạp thiết kế |
| --- | --- | --- | --- |
| **Toàn cấu trúc** | Toàn bộ map/list/graph | Hạn chế nếu mọi thao tác cần khóa | Thấp |
| **Theo vùng/chunk** | Một đoạn mảng, một partition | Các vùng khác nhau có thể xử lý đồng thời | Trung bình |
| **Theo bucket** | Một bucket trong hash table | Tối đa theo số bucket độc lập | Tăng khi resize và thay đổi bucket |
| **Striped** | Một trong `s` nhóm bucket/khóa | Tối đa theo số stripe đang hoạt động | Trung bình; có va chạm stripe |
| **Theo phần tử/nút** | Một khóa dữ liệu hay nút riêng | Tốt khi truy cập phân tán | Cao: vòng đời, deadlock, metadata |
| **Lock coupling/hand-over-hand** | Nắm khóa nút kế tiếp trước khi nhả nút trước | Có thể cho truy cập ở những vùng xa nhau | Cao: phải chứng minh an toàn khi liên kết đổi |
| **Read–write lock** | Nhiều reader cùng lúc, một writer độc quyền | Hợp với workload nhiều đọc | Cần chính sách ưu tiên và chống starvation |

**Mức khóa càng nhỏ không đồng nghĩa hệ thống càng nhanh**: số lock, lượng công việc quản lý lock, va chạm cache line, rủi ro deadlock, khả năng phải lấy nhiều lock và chi phí chụp trạng thái toàn cục đều có thể tăng.

**Mức độ hạt khóa** và **độ dài đoạn găng** là hai quyết định riêng. Ngay cả một khóa chung vẫn có thể giảm thời gian giữ khóa bằng cách xác thực phần không phụ thuộc trạng thái ở ngoài lock, hoặc xử lý bản sao bất biến sau khi nhả khóa.

## 6. Khóa phân đoạn (striping): dung hòa giữa một khóa và vô số khóa

Giả sử bảng băm có hàng nghìn khóa nghiệp vụ. Thay vì một lock cho tất cả hoặc một lock cho từng khóa, ta tạo trước `s` lock:

\[
stripe(k)=hash(k)\bmod s.
\]

```text
L_0 ──► partition 0:  các khóa có stripe(k)=0
L_1 ──► partition 1:  các khóa có stripe(k)=1
L_2 ──► partition 2:  các khóa có stripe(k)=2
L_3 ──► partition 3:  các khóa có stripe(k)=3
```

**Điều kiện then chốt:** một khóa dữ liệu phải luôn được quản lý bởi **cùng một stripe** trong suốt giai đoạn cấu trúc hoạt động theo ánh xạ đó. Nếu đổi số stripe, hàm phân vùng hoặc cách diễn giải hash mà không di chuyển dữ liệu và đồng bộ độc giả/writer, người đọc có thể tra sai chỗ.

Hai khóa nghiệp vụ khác nhau có thể:

- Rơi vào **hai stripe khác nhau** → hai thao tác chỉ chạm một stripe có thể thực thi đồng thời.
- Rơi vào **cùng stripe** → vẫn tranh cùng khóa, dù khóa nghiệp vụ khác nhau.

Nếu hash được phân bố đều và hai khóa độc lập, xác suất chúng trùng một trong `s` stripe xấp xỉ `1/s`. Đây chỉ là mô hình đơn giản; dữ liệu thực có thể lệch mạnh, đặc biệt khi nhiều luồng liên tục cập nhật **một khóa nóng**.

### Vì sao không luôn tạo lock theo từng khóa?

- Cần quản lý nhiều đối tượng lock và vòng đời của chúng khi khóa được tạo/xóa.
- Khi một khóa vừa bị xóa rồi tạo lại, các tham chiếu lock cũ có thể gây **hai lock bảo vệ cùng một khóa logic**.
- Thao tác đa khóa cần quy tắc sắp xếp lock.
- Kiểm tra `size`, snapshot hoặc xóa hàng loạt thường cần phối hợp nhiều lock cùng lúc.
- Khóa phân đoạn có số lượng cố định nên dễ giữ một bảng lock ổn định và dễ triển khai hơn.

## 7. Ví dụ Python: cùng một lớp hoạt động như khóa toàn cục hoặc khóa phân vùng

Ta xây một sổ cái **có tập tài khoản cố định** để tập trung vào khóa và bất biến. Mỗi stripe sở hữu một dict riêng. Tất cả dữ liệu mutable của stripe được đọc/ghi dưới lock tương ứng.

- `stripes=1` → mọi tài khoản dùng **một khóa chung**: chính là coarse-grained locking.
- `stripes>1` → nhiều vùng độc lập: có thể có song song giữa các cập nhật không chạm cùng stripe.
- Một chuyển khoản `source→target` phải giữ **cả hai khóa**, kể cả khi hai tài khoản nằm khác stripe.
- Một `snapshot()` toàn sổ cái phải lấy **tất cả các stripe lock** theo thứ tự nhất quán.

```python
from concurrent.futures import ThreadPoolExecutor
from threading import Lock


class SoCaiPhanVung:
    def __init__(self, balances, stripes=4):
        if type(stripes) is not int or stripes <= 0:
            raise ValueError("stripes phải là số nguyên dương")
        if not isinstance(balances, dict) or not balances:
            raise ValueError("Cần ít nhất một tài khoản")

        self._locks = [Lock() for _ in range(stripes)]
        self._parts = [{} for _ in range(stripes)]
        self._expected_total = 0

        # __init__ chạy trước khi chia sẻ đối tượng cho các luồng.
        for account, amount in balances.items():
            if not isinstance(account, str) or not account:
                raise ValueError("ID tài khoản không hợp lệ")
            if type(amount) is not int or amount < 0:
                raise ValueError("Số dư phải là số nguyên không âm")
            idx = self._stripe(account)
            self._parts[idx][account] = amount
            self._expected_total += amount

    def _stripe(self, account):
        # Mỗi khóa luôn tra tới cùng stripe; số stripe không đổi.
        return hash(account) % len(self._locks)

    def get(self, account):
        i = self._stripe(account)
        with self._locks[i]:
            return self._parts[i][account]

    def transfer(self, source, target, amount):
        if type(amount) is not int or amount <= 0:
            raise ValueError("Số tiền phải là số nguyên dương")
        if source == target:
            raise ValueError("Nguồn và đích phải khác nhau")

        a = self._stripe(source)
        b = self._stripe(target)
        selected = sorted({a, b})  # Một lock nếu trùng stripe.
        for i in selected:
            self._locks[i].acquire()

        try:
            if (source not in self._parts[a]
                    or target not in self._parts[b]):
                raise KeyError("Tài khoản không tồn tại")
            if self._parts[a][source] < amount:
                return False

            # Hai lần ghi được bảo vệ như một thao tác logic.
            self._parts[a][source] -= amount
            self._parts[b][target] += amount
            return True
        finally:
            for i in reversed(selected):
                self._locks[i].release()

    def snapshot(self):
        # Lấy tất cả lock theo thứ tự TĂNG và nhả theo chiều NGƯỢC.
        for lock in self._locks:
            lock.acquire()
        try:
            entries = tuple(
                (account, value)
                for part in self._parts
                for account, value in part.items()
            )
            # Dữ liệu snapshot gồm (str, int): không sửa tại chỗ qua API.
            return tuple(sorted(entries))
        finally:
            for lock in reversed(self._locks):
                lock.release()

    def check_total(self):
        return sum(value for _, value in self.snapshot()) == (
            self._expected_total
        )


def demo(stripes):
    ledger = SoCaiPhanVung(
        {"A": 10, "B": 0, "C": 20, "D": 0},
        stripes=stripes,
    )
    with ThreadPoolExecutor(max_workers=3) as pool:
        f1 = pool.submit(ledger.transfer, "A", "B", 7)
        f2 = pool.submit(ledger.transfer, "A", "B", 7)
        f3 = pool.submit(ledger.transfer, "C", "D", 8)
        results = [f1.result(), f2.result(), f3.result()]

    assert sum(results[:2]) == 1
    assert results[2] is True
    assert ledger.snapshot() == (
        ("A", 3), ("B", 7), ("C", 12), ("D", 8)
    )
    assert ledger.check_total()
    return ledger.snapshot()


print(demo(stripes=1))
# (('A', 3), ('B', 7), ('C', 12), ('D', 8))

print(demo(stripes=8))
# (('A', 3), ('B', 7), ('C', 12), ('D', 8))
```

### Vì sao khóa phân vùng vẫn giữ tổng tiền?

Có bất biến:

\[
\sum_{a\in Accounts} balance[a]=30
\]

vì chỉ có chuyển khoản nội bộ. Khi chuyển từ A sang B, hàm giữ tất cả lock của các vùng chứa A và B **cùng lúc**, kiểm tra đủ tiền rồi mới thay đổi hai số dư. Một người đọc chỉ lấy `get(A)` có thể nhìn một số dư riêng ở một thời điểm hợp lệ; người đọc cần tổng phải dùng `snapshot()` để lấy **một trạng thái nhất quán**.

Nếu một thao tác chuyển C→D diễn ra ở những stripe **không giao** với cặp A/B, hai đoạn găng **có thể** chồng lấp. Nhưng với `stripes=8` không có bảo đảm C/D và A/B nằm ở các stripe tách biệt: hàm hash có thể đưa nhiều tài khoản vào cùng stripe.

**Mã minh họa chưa hỗ trợ thêm/xóa tài khoản.** Nếu tập khóa thay đổi động, thiết kế cần thêm hợp đồng cho `_expected_total`, quyền tạo/xóa tài khoản, và cách chặn một tài khoản biến mất giữa thao tác hai vùng. Mã giả định các phép cập nhật Python không bị lỗi tài nguyên bất thường giữa hai lần ghi; mutex không tự làm rollback.

## 8. Khóa nhiều vùng: thứ tự nhất quán ngăn deadlock

Giả sử T1 chuyển A→B và T2 chuyển B→A. Nếu mỗi luồng khóa **nguồn trước**, có lịch nguy hiểm:

```text
T1: lock(A)   ....... chờ lock(B)
T2:           lock(B) ....... chờ lock(A)
              └── chờ vòng tròn ──┘
```

Cả hai giữ khóa đầu tiên và chờ khóa còn lại, tạo **deadlock**.

Cách cơ bản là đặt một **thứ tự khóa toàn cục** dựa trên chỉ số stripe:

```text
locks = sorted({stripe(A), stripe(B)})
acquire theo thứ tự tăng
thực hiện cả hai cập nhật
release theo thứ tự giảm
```

Dù gọi A→B hay B→A, hai luồng đều xin cùng thứ tự. Khi A và B thuộc **cùng stripe**, phải xin **một lock đúng một lần**; nếu gọi `Lock.acquire()` hai lần trên cùng lock thường, cùng luồng có thể tự kẹt vì khóa không tái nhập.

**Bất biến thứ tự khóa phải áp dụng cho mọi đường mã**, kể cả xóa vùng, snapshot, resize và hàm callback. Nếu một phương thức lấy lock theo thứ tự tăng còn phương thức khác lấy theo thứ tự giảm, deadlock vẫn có thể xảy ra.

Cần tránh thêm những khóa ngoài thiết kế vào giữa đoạn găng theo thứ tự tùy tiện. Một mô hình dùng `RLock` có thể cho cùng luồng tái nhập chính lock đó, nhưng **không** giải quyết chu trình chờ giữa **những khóa khác nhau**.

## 9. Truy vấn toàn cục: `size`, `sum` và snapshot không còn đơn giản

Khi chỉ có một lock, muốn chụp cấu trúc:

```text
lock(global)
    sao chép tất cả dữ liệu
unlock(global)
```

Với nhiều stripe, một cách sai là:

```text
snapshot = []
for stripe in stripes:
    lock(stripe)
    snapshot += copy(stripe.data)
    unlock(stripe)
```

Giữa lúc copy stripe 0 và stripe 1, một chuyển khoản **qua hai stripe** có thể hoàn thành. Kết quả có thể ghép `balance[A]` trước chuyển và `balance[B]` sau chuyển, làm **sai tổng**, dù mọi thao tác update và get riêng lẻ đều an toàn.

Trong `SoCaiPhanVung.snapshot()`, phương thức lấy **toàn bộ lock** theo thứ tự cố định trước khi copy, rồi nhả khi hoàn tất. Khi đó không writer nào có thể sửa bất kỳ vùng nào trong thời gian chụp.

### Những lựa chọn khác

- **Một khóa quản lý metadata:** có thể giữ `size`, nhưng việc cập nhật đồng bộ counter và bucket phải nằm trong một giao thức đúng; không được tạo counter nhanh nhưng sai.
- **Read–write lock cấp cấu trúc:** nhiều reader có thể cùng đọc nhưng writer cần độc quyền theo chính sách.
- **Snapshot bất biến/copy-on-write:** reader sử dụng phiên bản đã hoàn chỉnh, không khóa từng vùng lâu.
- **Optimistic snapshot:** đọc phiên bản trước/sau rồi thử lại nếu có thay đổi, với điều kiện thuật toán đảm bảo không đọc dữ liệu mutable bất hợp lệ trong lúc writer sửa. Một kiểm tra version đơn giản **không tự đủ** cho mọi kiểu vùng nhớ.
- **Thống kê gần đúng:** chấp nhận số liệu không chính xác tức thời nếu bài toán cho phép; phải ghi rõ hợp đồng và không dùng nó làm điều kiện thanh toán/khóa ngoại.

Tính đúng phải được ưu tiên. Khi yêu cầu tổng **chính xác của một thời điểm logic**, “cộng từng stripe trong lúc có writer” không phải cách đọc đủ mạnh.

## 10. Tranh chấp phụ thuộc mẫu truy cập, không chỉ số khóa

Hai thông số cơ bản:

- `s`: số stripe/khóa độc lập.
- `p`: số luồng cùng muốn tiến hành thao tác.

**Nếu mọi luồng liên tục tăng cùng một khóa nóng**, tất cả vẫn tranh một stripe bất kể `s` lớn đến đâu:

```text
Hot key: "course-popular"
T1, T2, T3, T4,... ──► cùng stripe của hot key
```

Ngược lại, nếu các luồng tác động tới những khóa phân bố đều, tăng `s` có thể giảm xác suất đụng nhau. Nhưng còn phải xét:

- Một thao tác chuyển khoản thường **nắm hai stripe**; điều này tăng cơ hội chồng lấp vùng khóa.
- Snapshot toàn cấu trúc phải xin **tất cả** stripe, tạm thời biến thành hoạt động có mức đồng bộ toàn cục.
- Nếu các thread làm việc trên cùng một cache line hoặc bộ đếm metadata, **contention bộ nhớ** vẫn có thể xảy ra dù lock khác nhau.
- Một stripe lock giữ quá lâu do thao tác đọc file/I/O có thể chặn nhiều khóa nghiệp vụ nằm chung vùng.
- Quá nhiều stripe có thể tăng bộ nhớ, chi phí khởi tạo, quản lý và chi phí quét tất cả stripe.

**Mở rộng số khóa chỉ giúp khi những thao tác thật sự có thể độc lập về bất biến và dữ liệu.** Không thể chỉ gắn thêm mutex vào nhiều chỗ để tạo thêm song song.

## 11. Thay đổi tập bucket: resize/rehash làm khóa phân vùng khó hơn

Trong bảng băm động, số bucket hoặc bảng lưu trữ có thể thay đổi khi hệ số tải vượt ngưỡng. Giả sử một khóa `k` từng thuộc bucket 2, sau resize có thể chuyển sang bucket 14.

Nếu chương trình gắn mutex **trực tiếp với bucket hiện hành**, nhiều câu hỏi phát sinh:

1. Khi bucket chuyển chỗ, lock nào bảo vệ `k` trong giai đoạn chuyển?
2. Reader có được tra bảng cũ, bảng mới hay cả hai?
3. Writer nào được thêm/xóa `k` khi nó đang được di chuyển?
4. Có thể công bố bảng mới khi mới di chuyển **một phần** dữ liệu không?
5. Khi nào được thu hồi vùng nhớ và lock của bảng cũ?

Một lịch lỗi:

```text
Writer:  chuyển k từ old_bucket sang new_bucket
Reader:  vẫn dùng old_bucket_lock, tìm k tại old_bucket
Writer:  đã xóa k khỏi bảng cũ nhưng chưa công bố bảng mới
Reader:  kết luận "k không tồn tại"   ← sai
```

### Một vài chiến lược đúng về nguyên tắc

- **Dùng một khóa cấu trúc riêng cho resize:** thao tác thông thường phối hợp với khóa ấy; writer resize lấy quyền độc quyền, xây và công bố bảng đầy đủ.
- **Khóa/đóng băng tất cả stripe** trong lúc xây lại, theo thứ tự xác định; đơn giản hơn nhưng làm toàn bộ truy cập bị chặn trong một thời gian.
- **Giữ stripe cố định theo hash của khóa** (như ví dụ) trong khi dữ liệu của mỗi stripe được quản lý độc lập; có thể resize bảng nội bộ từng stripe dưới lock của stripe đó.
- **Di chuyển tăng dần có giao thức trợ giúp (cooperative migration):** phức tạp hơn, phải quy định reader/writer thấy vùng nào và cách nhận biết phần đã chuyển.

**Không nên chỉ đổi phép `hash(k) % new_stripe_count`** khi dữ liệu đã nằm trong các dict cũ. Việc đổi ánh xạ mà chưa di chuyển đúng và phối hợp các thao tác đang chạy sẽ phá tìm kiếm.

Cũng không được mặc định `dict` có thể được đọc mà không đồng bộ trong khi luồng khác đang resize hoặc sửa nó: phải tuân theo hợp đồng concurrency của runtime, không dựa vào hành vi tình cờ của một phiên bản.

## 12. Danh sách liên kết và cây: khóa theo nút cần bảo vệ cả đường đi

### Danh sách liên kết

Với danh sách liên kết đơn, một thuật toán duyệt có thể giữ lock của nút hiện tại, **lấy lock của nút tiếp theo trước khi nhả nút hiện tại** (hand-over-hand hoặc lock coupling). Ý tưởng là không để liên kết đang dùng bị xóa giữa lúc chuyển bước.

```text
lock(current)
while next exists:
    lock(next)
    kiểm tra/tiến tới next
    unlock(current)
    current = next
unlock(current)
```

Nhưng đây chỉ là **phác thảo**. Muốn đúng còn cần xác định **quy tắc chèn/xóa**, vòng đời nút, trường hợp đầu/cuối, và việc tham chiếu `next` có thể đổi thế nào khi writer chạy. Nếu một luồng đọc `current.next` rồi mất quyền bảo vệ trước khi giữ được khóa của nút tiếp theo, một luồng khác có thể xóa hoặc thu hồi nút ấy.

**Danh sách liên kết đôi** còn có bất biến `u.next=v ⇒ v.prev=u`. Chèn vào giữa hoặc xóa một nút có thể thay đổi nhiều liên kết và bộ đếm, nên một lock của **một nút duy nhất** thường không bao trọn thao tác. Dễ bắt đầu đúng với một lock toàn danh sách rồi chỉ tối ưu mức khóa sau khi đã có thuật toán đã được chứng minh.

### Cây tìm kiếm/cây cân bằng

Trên cây, nhiều reader có thể tra các nhánh khác nhau. Khóa theo nút hoặc theo cây con có thể giúp song song, nhưng **phép xoay** cần cập nhật nhiều con trỏ cha/con cùng bất biến chiều cao/màu/kích thước.

Một phép xóa có thể thay đổi cả đường từ nút tới gốc. Không thể coi “chỉ sửa một nút” là thao tác cục bộ nếu metadata ở các tổ tiên cũng phải cập nhật.

**Điểm chung:** độ hạt khóa phải theo **tập nút và metadata bị tác động bởi thao tác**, chứ không chỉ theo điểm bắt đầu truy vấn.

## 13. Đồ thị: khóa theo đỉnh có đủ khi thêm/xóa cung?

Một đồ thị có hướng có thể lưu đồng thời:

```text
vertices: tập đỉnh
edges[eid] = (source, target): bảng cung chuẩn
out_ids[u]: các edge_id đi ra từ u
in_ids[v]: các edge_id đi vào v
```

Khi thêm cung `e=(u→v)` cần sửa **ít nhất ba nơi**: `edges[e]`, `out_ids[u]` và `in_ids[v]`. Nếu chỉ lấy khóa đỉnh u rồi thêm vào `out[u]`, sau đó nhả khóa và mới lấy khóa v để thêm `in[v]`, reader có thể thấy cung chỉ tồn tại ở một phía.

Một ý tưởng nâng cấp:

1. Có **chỉ mục đỉnh** được bảo vệ để kiểm tra u, v vẫn đang hoạt động.
2. Lấy lock của **cả hai đỉnh** theo thứ tự ID ổn định hoặc thứ tự lock key.
3. Cập nhật bảng cung chuẩn và hai chỉ mục theo một **giao thức bảo vệ bảng cạnh** phù hợp (có thể là bảng cạnh phân đoạn, hoặc một khóa bảng cạnh riêng).
4. Công bố kết quả và nhả khóa theo thứ tự ngược.
5. Khi **xóa đỉnh**, chặn thêm cung mới trỏ tới nó và loại bỏ toàn bộ cung đi vào/ra, không để tham chiếu mồ côi.

**Lưu ý:** đây là các yêu cầu thiết kế, **không phải thuật toán hoàn chỉnh**. Khóa từng đỉnh mà không có cơ chế bảo vệ **bảng edges, tạo edge ID và vòng đời đỉnh** là chưa đủ.

### Cung song song và khuyên

- Hai cung A→B với ID e0/e1 vẫn là hai bản ghi độc lập, không được gộp thành một chỉ vì khóa cùng hai đỉnh.
- Khuyên B→B liên quan tới **cùng một đỉnh ở hai vai trò nguồn/đích**. Nếu dùng lock theo đỉnh, phải lấy **một lock B** chứ không thử khóa hai lần mutex không tái nhập.
- Khi xóa B, tập liên kết liên quan là `out[B] ∪ in[B]`; phép hợp theo ID tránh xóa khuyên hai lần.
- Một bản snapshot đồ thị muốn phản ánh cùng trạng thái logic của tất cả chỉ mục phải dùng giao thức đọc nhất quán, không phải lấy từng khóa đỉnh một rồi ghép kết quả tùy thời điểm.

Nếu hệ thống có nhiều thao tác **chạy BFS/DFS dài**, một cách khác là giữ bản chuẩn động, rồi cung cấp **snapshot bất biến** cho thuật toán duyệt. Đổi lại phải trả chi phí tạo và quản lý phiên bản snapshot.

## 14. Read–write lock: nhiều người đọc có tự động tốt hơn không?

**Read–write lock (RWLock)** phân biệt hai chế độ:

- **Shared/read lock:** có thể cho nhiều reader cùng giữ khóa nếu không có writer.
- **Exclusive/write lock:** writer độc quyền khi sửa trạng thái.

Đối với workload **nhiều đọc và ít ghi**, read lock có thể giảm tranh chấp so với một mutex độc quyền cho mọi thao tác. Nhưng không có kết luận tuyệt đối:

- RWLock thường có thêm chi phí bookkeeping.
- Nếu writer đến liên tục, reader có thể chờ lâu; nếu reader đến liên tục, writer có thể bị đói, tùy chính sách ưu tiên.
- Một phép đọc **snapshot nhiều vùng** vẫn phải phối hợp để nhìn cùng phiên bản; nhiều read lock cục bộ không tự bảo đảm tính nguyên tử toàn cấu trúc.
- Đọc một đối tượng immutable có thể không cần khóa dài; quản lý công bố và vòng đời snapshot vẫn phải đúng.

Một số môi trường không có RWLock tích hợp ngay trong thư viện chuẩn giống `Lock`, và ngữ nghĩa ưu tiên reader/writer khác nhau giữa các thư viện. Không nên giả định tên “RWLock” đủ để biết chính sách công bằng hay khả năng nâng cấp lock.

**Nâng cấp read lock sang write lock** là tình huống dễ bị mắc kẹt nếu hai reader đều giữ read lock và cùng chờ lên writer. Chỉ dùng API upgrade nếu primitive có hợp đồng hỗ trợ rõ ràng.

## 15. Optimistic locking và immutable snapshot: giảm thời gian giữ khóa

### Optimistic validation

Một hướng là đọc snapshot với phiên bản `v`, xử lý tốn thời gian ở ngoài khóa, rồi khi commit:

```text
lock(phạm vi commit)
if current_version != v:
    hủy/tính lại kết quả
else:
    xác thực và ghi
    current_version += 1
unlock
```

**Điều bắt buộc:** bước kiểm tra phiên bản và bước ghi phải là **một giao thức nguyên tử**. Không được đọc version không đồng bộ rồi sửa cấu trúc khi thấy chưa đổi; một writer khác có thể chen vào giữa.

Nếu nhiều writer cùng tranh, cách lạc quan có thể **thử lại liên tục**. Nó không miễn phí và không tự là thuật toán lock-free.

### Bản chụp bất biến

Một writer có thể xây phiên bản mới **ngoài đường đọc hiện hành**, xác thực bất biến rồi công bố bản hoàn chỉnh. Reader giữ một handle snapshot hợp lệ và không bị writer sửa tại chỗ.

```text
R1: giữ V1 ───────────► đọc an toàn V1
W : dựng V2 → kiểm tra → công bố V2
R2:                    giữ V2 ──► đọc an toàn V2
```

Nhờ vậy, đường đọc dài không cần xin toàn bộ lock ghi mỗi bước. Nhưng phải quản lý:

- Công bố/hiển thị phiên bản theo mô hình bộ nhớ.
- Vòng đời phiên bản cũ khi còn reader.
- Không chia sẻ phần con mutable giữa V1 và V2.
- Chi phí sao chép, quản lý phiên bản và khả năng kết quả đọc hơi cũ.

**Snapshot nhất quán không đồng nghĩa mới nhất.** BFS trên V1 vẫn đúng với V1, dù V2 đã công bố trong lúc duyệt.

## 16. Mô hình chi phí: Big-O chưa tính thời gian chờ khóa

Giả sử một thao tác trong hash map cần `O(1)` kỳ vọng để tìm bucket và cập nhật một mục. Khi bị tranh chấp, thời gian phản hồi còn gồm **thời gian chờ lock** và các chi phí điều phối.

\[
T_{\text{response}}
= T_{\text{queue/wait}} + T_{\text{critical}} +
  T_{\text{noncritical}} + T_{\text{overhead}}.
\]

Đây là cách phân rã để phân tích, không phải một công thức dự đoán chính xác cho mọi hệ điều hành.

### Một khóa chung và giới hạn thông lượng

Nếu tất cả các thao tác phải giữ chung một mutex trong trung bình `t_c` đơn vị thời gian xử lý đoạn găng, **không thể** thực hiện hơn khoảng `1/t_c` thao tác/đơn vị thời gian chỉ từ đoạn găng ấy trong điều kiện bão hòa, chưa kể các overhead và thời gian khác. Đây là **giới hạn trên lý tưởng**, không phải thông lượng sẽ đạt được.

Nếu chỉ một phần `f` của công việc bắt buộc tuần tự, công thức **Amdahl** cho tốc độ tăng lý tưởng trên `p` bộ xử lý:

\[
Speedup(p)\leq\frac{1}{f+(1-f)/p}.
\]

Công thức đòi giả định một workload cố định và phân chia phần tuần tự/song song; nó **không** tự dự đoán thời gian chờ mutex, chi phí mở rộng bộ nhớ, độ lệch khóa nóng hay năng lực phần cứng.

### Tăng số stripe

Thêm stripe có thể giảm mức tranh chấp giữa những khóa dữ liệu phân tán, nhưng mức tăng thường giảm dần:

- Số luồng chạy đồng thời bị giới hạn bởi CPU và công việc thực.
- Một phép chuyển giữa hai stripe chiếm **hai lock**, không phải một.
- Stripe nóng vẫn thành điểm tuần tự.
- Snapshot/resize toàn cục vẫn cần đồng bộ rộng.
- Quá nhiều lock tăng overhead và có thể gây **false sharing** nếu metadata của những lock/bộ đếm được bố trí chung cache line.

Vì vậy, không nên áp dụng công thức “s stripe → nhanh s lần”. Cần đo trên mẫu truy cập thực tế và phần cứng thực tế.

## 17. False sharing, cache line và chi phí quản lý khóa

Hai biến có thể được hai luồng ghi hoàn toàn độc lập, mỗi biến có lock riêng, nhưng lại nằm trên **cùng một cache line**. CPU phải chuyển quyền sở hữu cache line giữa lõi khi hai luồng ghi, làm phát sinh **false sharing**.

```text
Cache line 64 byte (minh họa)
┌────────────────────────────────────┐
│ counter_A │ counter_B │ ...       │
└────────────────────────────────────┘
     ▲          ▲
    CPU1       CPU2
```

Vì thế, **ít tranh chấp mutex không đồng nghĩa không còn tranh chấp bộ nhớ**. Một thiết kế phân vùng có thể cần xem cách bố trí bộ đếm và dữ liệu nóng, nhất là trong C/C++ hoặc mảng typed chạy song song thật.

Ngược lại, mỗi lock riêng còn tốn:

- Vùng nhớ dành cho đối tượng lock và metadata.
- Lệnh nguyên tử, hàng rào bộ nhớ hoặc chuyển trạng thái kernel khi chờ.
- Quản lý tạo/hủy lock khi số phần tử thay đổi.
- Bộ đếm đo lường và bookkeeping nếu dùng cơ chế đồng bộ phức tạp.

Trong Python, hiệu năng còn phụ thuộc phiên bản và cách xây dựng trình thông dịch (có thể có GIL hoặc chế độ khác), thư viện gọi mã native và tỷ lệ I/O. Ví dụ `SoCaiPhanVung` chứng minh **giao thức khóa**, không chứng minh sẽ nhanh hơn khi benchmark tác vụ CPU-bound trong mọi cấu hình Python.

## 18. Thời gian giữ khóa, I/O và callback

Giảm mức khóa không có ích nếu một luồng vẫn giữ một lock nóng quá lâu. Hãy phân tách:

```text
xử lý/chuẩn bị dữ liệu không cần trạng thái chung   ← ngoài khóa
lock
    kiểm tra điều kiện trên trạng thái chung
    cập nhật những trường thuộc cùng bất biến
    tạo kết quả tối thiểu cần thiết
unlock
định dạng báo cáo, gọi dịch vụ ngoài, hiển thị       ← ngoài khóa
```

**Tuy nhiên, không chuyển bừa việc kiểm tra tiền điều kiện ra ngoài lock.** Nếu điều kiện liên quan tới trạng thái mutable đang được luồng khác sửa, nó phải được **kiểm tra lại trong đoạn găng** hoặc được bảo vệ bằng kiểm tra phiên bản và commit nguyên tử.

Không nên gọi callback, gửi email, thực hiện truy vấn mạng hoặc chờ input người dùng khi giữ lock cấu trúc trừ khi có lý do và giao thức cụ thể. Callback có thể gọi ngược vào cấu trúc, giữ khóa khác, hoặc chờ một luồng đang cần lock hiện tại → tăng nguy cơ deadlock và độ trễ.

**Mutex không phải giao dịch có rollback.** Nếu một ngoại lệ xảy ra sau khi đã cập nhật một nửa chỉ mục, `finally` có thể nhả lock nhưng không tự hoàn nguyên trạng thái. Cần xác thực trước, chuẩn bị dữ liệu, xây bản mới rồi công bố, hoặc có cơ chế khôi phục lỗi thích hợp.

## 19. Cách đo và lựa chọn mức khóa cho một workload

Một benchmark nên tách **đúng đắn** khỏi **hiệu năng**. Với cùng một API và dữ liệu đầu vào, hãy so ít nhất:

| Mẫu tải | Điều muốn học được |
| --- | --- |
| 1 luồng, nhiều thao tác nhỏ | Overhead của một lock so với nhiều lock |
| Nhiều luồng, khóa dữ liệu **phân tán đều** | Khóa phân vùng giảm tranh chấp ra sao |
| Nhiều luồng, một **khóa nóng** | Giới hạn khi không thể chia nhỏ bất biến |
| Nhiều chuyển khoản **qua hai stripe** | Chi phí lấy nhiều lock và va chạm khóa |
| Nhiều đọc một mục, ít ghi | RWLock/snapshot có lợi không |
| Chụp snapshot toàn bộ thường xuyên | Chi phí đồng bộ mọi stripe và chờ writer |
| Thêm/xóa nhiều khóa, resize | Overhead quản lý vùng và tính đúng trong rehash |
| Phân bố độ lớn tác vụ không đều | Lock convoy, độ trễ đuôi và starvation |

Nên đo:

- **Throughput:** thao tác hoàn thành/giây.
- **Latency:** trung vị và phân vị cao như p95/p99, không chỉ trung bình.
- **Lock wait time:** thời gian chờ trước khi vào đoạn găng.
- **Hold time:** thời gian nắm lock.
- **Tỷ lệ tranh chấp:** bao nhiêu lần xin khóa phải chờ.
- **Bộ nhớ:** số lock và metadata, phân vùng, snapshot.
- **Độ đúng:** bất biến, lịch sử các thao tác và khả năng tiến triển.

**Không kết luận từ một lượt chạy.** Sắp lịch của hệ điều hành, GC, JIT, cache, loại máy, mức nóng dữ liệu và cách khởi tạo có thể làm kết quả dao động. Đo nhiều lần, dùng dữ liệu đại diện và cố định các giả định quan trọng.

## 20. Kiểm thử đúng đắn khi có nhiều khóa

### Kiểm tra lịch xen kẽ có chủ đích

Dùng barrier hoặc hook trong test để hai luồng cùng đi tới điểm “sắp kiểm tra số dư” hoặc “sắp sửa chỉ mục”. Kiểm tra rằng giao thức khóa không cho chúng cùng hoàn thành một hành động vượt bất biến.

**Không đặt barrier của hai luồng ở vị trí chỉ một luồng có thể tới vì đang giữ một lock chung**; bài test tự gây deadlock và không chứng minh lỗi của chương trình.

### Kiểm tra trạng thái cuối và cả kết quả từng thao tác

Nếu ban đầu A=10, B=0 và hai yêu cầu cùng chuyển 7, phải có đúng **một** yêu cầu thành công và A=3, B=7. Chỉ kiểm tra tổng tiền 10 chưa đủ: hệ thống có thể có tổng đúng nhưng báo thành công cho cả hai.

Với map, kiểm tra rằng mỗi khóa đang hoạt động có thể tìm lại được sau nhiều lần chèn/xóa/resize. Với đồ thị, kiểm tra mọi edge ID xuất hiện đúng trong bảng cạnh và chỉ mục cung đi vào/ra, bao gồm khuyên và cung song song.

### Kiểm tra deadlock và khả năng tiến triển

Tạo thao tác hai vùng theo hai chiều A→B và B→A; test timeout và nhiều luồng để phát hiện đường mã lấy lock trái thứ tự. Không khẳng định không có deadlock chỉ vì một lượt test hoàn thành.

Nếu cần kiểm tra **linearizability**, phải ghi lịch sử lời gọi, kết quả và thứ tự thời gian của các thao tác, rồi đối chiếu với một đặc tả tuần tự hợp lệ, không chỉ xét trạng thái cuối.

## 21. Những lỗi tư duy thường gặp

1. **“Một lock chung luôn là thiết kế sai.”** Không: nó có thể tối ưu cho đơn giản, đúng đắn và workload ít tranh chấp.
2. **“Nhiều lock hơn luôn nhanh hơn.”** Không: có thể tăng overhead, deadlock và chi phí thao tác toàn cục.
3. **“Khóa theo từng mục khiến hai thao tác khác mục luôn độc lập.”** Sai nếu chúng cùng sửa metadata, bộ đếm hoặc bất biến toàn cấu trúc.
4. **“Mỗi lần `get` an toàn thì cộng nhiều `get` là snapshot an toàn.”** Không: trạng thái có thể đổi giữa hai lần gọi.
5. **“Chuyển khoản chỉ cần khóa tài khoản nguồn.”** Sai: cần bảo vệ cả nguồn, đích và phần dữ liệu liên quan.
6. **“Có thứ tự khóa cho transfer, snapshot không cần tuân thủ.”** Sai: mọi đường lấy nhiều khóa phải dùng quy tắc tương thích.
7. **“Hai tài khoản cùng stripe thì phải lấy lock hai lần.”** Sai với mutex không tái nhập; phải khử trùng tập lock.
8. **“Striped locking giống per-key locking.”** Không: nhiều key khác nhau có thể chia sẻ một stripe.
9. **“Tăng gấp đôi số stripe sẽ tăng gấp đôi throughput.”** Không: còn khóa nóng, CPU, metadata và thao tác nhiều vùng.
10. **“Đổi số stripe chỉ cần đổi phép modulo.”** Sai nếu chưa di chuyển dữ liệu an toàn và phối hợp các luồng.
11. **“Đang rehash nửa bảng vẫn có thể cho mọi reader tra bảng mới.”** Không nếu chưa có giao thức migration hợp lệ.
12. **“Khóa một đỉnh là đủ để thêm cung vào đồ thị có hai chỉ mục.”** Sai: còn đỉnh đích, bảng edges và vòng đời đỉnh.
13. **“Khuyên B→B cần khóa hai lần lock B.”** Không: đó là một lock cho một đỉnh, dù cung có hai vai trò.
14. **“Khóa theo nút cho phép xóa nút an toàn mà không quản lý vòng đời.”** Sai: reader có thể giữ tham chiếu đã bị xóa/thu hồi.
15. **“RWLock tự bảo đảm writer không starvation.”** Phụ thuộc chính sách và thư viện.
16. **“Một thao tác `O(1)` thì thời gian phản hồi chắc `O(1)`.”** Sai: chờ lock có thể kéo dài, thậm chí không có cận.
17. **“Không thấy tranh chấp lock nghĩa là không có tranh chấp cache.”** Sai: false sharing và cache-line bouncing vẫn có thể xảy ra.
18. **“Có lock thì ngoại lệ sẽ tự rollback.”** Không: nhả lock không sửa lại các cập nhật đã làm.
19. **“GIL khiến thiết kế nhiều khóa tự đúng.”** Không: cần hợp đồng đồng bộ của API và runtime cụ thể.
20. **“BFS có thể duyệt đồ thị đang thay đổi mà luôn tương đương một snapshot.”** Không bảo đảm nếu không có giao thức snapshot/phiên bản.
21. **“Benchmark chỉ đo throughput đủ chọn thiết kế.”** Chưa đủ: cần latency, wait/hold time, memory, đúng đắn và độ nóng của dữ liệu.

## 22. Tự kiểm tra

**Câu 1.** Khóa toàn cấu trúc và khóa từng vùng khác nhau chủ yếu ở điều gì?

**Đáp án:** Khóa toàn cấu trúc tuần tự hóa mọi thao tác có liên quan tới cùng lock; khóa từng vùng cho phép các thao tác **trên các vùng không giao nhau và không có bất biến chung cần bảo vệ** tiến hành đồng thời. Đổi lại, thao tác đa vùng phức tạp hơn.

**Câu 2.** Hai luồng cập nhật hai khóa nghiệp vụ khác nhau nhưng nằm cùng stripe có thể giữ hai lock khác nhau không?

**Đáp án:** Không trong mô hình striped: hai khóa cùng ánh xạ tới **một lock stripe**, nên chúng vẫn tranh chấp.

**Câu 3.** Nếu một sổ cái có `stripes=1`, mô hình `SoCaiPhanVung` hoạt động tương tự kiểu khóa nào?

**Đáp án:** **Một khóa chung cho toàn cấu trúc.** `get`, `transfer` và `snapshot` đều dùng cùng mutex.

**Câu 4.** Một chuyển khoản A→B và một chuyển khoản B→A lấy lock theo thứ tự nguồn rồi đích có nguy cơ gì?

**Đáp án:** **Deadlock:** hai luồng có thể giữ lock nguồn của mình và cùng chờ lock đích. Sắp lock theo một thứ tự toàn cục giúp loại bỏ chu trình chờ kiểu này.

**Câu 5.** Vì sao `selected = sorted({a,b})` dùng set trước khi lấy lock trong ví dụ?

**Đáp án:** Để **khử trùng** khi a và b là cùng stripe. Nếu xin hai lần cùng mutex không tái nhập, luồng có thể tự deadlock.

**Câu 6.** Vì sao đọc từng stripe rồi nhả lock ngay có thể làm tổng tiền sai, dù `transfer` của writer đúng?

**Đáp án:** Reader có thể chụp stripe nguồn trước một chuyển khoản và stripe đích sau chuyển khoản, ghép hai trạng thái **khác thời điểm**. Muốn tổng nhất quán cần lấy một snapshot chung.

**Câu 7.** Nếu tất cả luồng cùng tăng một khóa nóng, việc tăng từ 4 lên 64 stripe có bảo đảm tăng throughput tương ứng không?

**Đáp án:** Không. Mọi thao tác vẫn tranh **stripe chứa khóa nóng**, nên nút thắt chính không được loại bỏ.

**Câu 8.** `hash(k) % s` được đổi sang `hash(k) % (2*s)` khi bảng đã có dữ liệu. Cần chú ý điều gì?

**Đáp án:** Nhiều khóa sẽ đổi stripe, nên phải **di chuyển và công bố dữ liệu theo giao thức đồng bộ**; nếu chỉ đổi hàm phân vùng, các lần tra cứu có thể sai.

**Câu 9.** Một phép xoay cây có thể cập nhật những vùng nào ngoài nút bắt đầu?

**Đáp án:** Nhiều liên kết **cha/con** và metadata như chiều cao, màu, kích thước cây con; đôi khi cả đường tới gốc tùy thuật toán. Phải khóa/đồng bộ phạm vi thật sự tham gia bất biến.

**Câu 10.** Thêm cung `u→v` trong đồ thị có bảng `edges/out/in` cần gì ngoài khóa riêng đỉnh u?

**Đáp án:** Cần bảo vệ đỉnh v, bảng edges/ID cung, chỉ mục `in[v]`, cùng vòng đời đỉnh; khóa một mình u không đủ bảo đảm trạng thái nhất quán.

**Câu 11.** Một cung khuyên B→B có cần lấy hai lần lock của đỉnh B không?

**Đáp án:** Không. Chỉ lấy **một lần** lock B, nhưng phải cập nhật đúng hai vai trò nguồn/đích của cung trong những chỉ mục liên quan.

**Câu 12.** Snapshot bất biến có bảo đảm luôn là trạng thái mới nhất khi một thao tác BFS kết thúc không?

**Đáp án:** Không. Nó bảo đảm **nhất quán với phiên bản đã chụp**, có thể cũ nếu writer công bố phiên bản mới sau đó.

**Câu 13.** Nếu 90% thời gian công việc thực sự bắt buộc tuần tự, Amdahl cho biết speedup tối đa khi số lõi tiến tới rất lớn là bao nhiêu, bỏ qua overhead?

**Đáp án:** Khoảng `1/0.9 \approx 1.11` lần. Thêm lõi hoặc stripe không loại bỏ được phần tuần tự đó.

**Câu 14.** Hai luồng ghi hai bộ đếm riêng có lock riêng nhưng dữ liệu nằm cùng cache line có thể gặp vấn đề gì?

**Đáp án:** **False sharing:** cache line bị chuyển qua lại giữa các lõi, gây overhead dù không tranh cùng mutex.

**Câu 15.** Vì sao không nên gọi dịch vụ mạng trong khi giữ lock của một bảng băm hoặc đồ thị?

**Đáp án:** Lệnh mạng có thể chờ lâu và chặn những luồng cần lock đó; callback có thể gọi ngược, lấy lock khác hoặc gây deadlock. Nên tách phần ngoài trạng thái chung và xác thực lại khi commit nếu cần.

**Câu 16.** Đo kiểm để so sánh một mutex với striped locking nên gồm những chỉ số và mẫu tải nào?

**Đáp án:** So sánh throughput, p95/p99 latency, lock wait/hold time, bộ nhớ và bất biến. Chạy tải phân tán và **khóa nóng**, thao tác một vùng/nhiều vùng, snapshot toàn cục, nhiều mức luồng và nhiều lần thử.

**Ghi nhớ:** **Khóa toàn cấu trúc** đơn giản, dễ bảo vệ bất biến và snapshot nhưng có thể hạn chế khả năng song song. **Khóa từng vùng hoặc striped lock** giảm tranh chấp khi các thao tác thật sự độc lập, đổi lại phải quản lý **nhiều khóa, thứ tự lấy khóa, vòng đời vùng và các thao tác toàn cục**. Với chuyển khoản, resize bảng băm, xóa nút, xoay cây hoặc cập nhật đồ thị nhiều chỉ mục, phạm vi đồng bộ phải bao trọn **tất cả dữ liệu của bất biến liên quan**. Không chọn mức khóa chỉ bằng số luồng hay Big-O của thao tác: hãy đo **mẫu truy cập, khóa nóng, thời gian chờ, thời gian giữ khóa, độ trễ đuôi, bộ nhớ và tính đúng đắn**.
