# Kiểm tra bảo toàn phần tử, thứ tự và tính nhất quán giữa các chỉ mục

Một thao tác cập nhật có thể khiến cấu trúc dữ liệu **trông vẫn hợp lệ** nhưng âm thầm mất phần tử, đổi thứ tự hoặc làm các chỉ mục trả về những câu trả lời khác nhau. Ví dụ: di chuyển một công việc trong danh sách nhưng quên cập nhật bảng `id → vị trí`; đổi danh mục của một bản ghi nhưng quên xóa ID khỏi chỉ mục danh mục cũ; hoặc sắp xếp dữ liệu nhưng vô tình xóa một phần tử trùng.

Trong chương **Kiểm chứng và thực hành** của học phần cấu trúc dữ liệu, ta cần kiểm tra ba thuộc tính độc lập nhưng liên quan chặt chẽ:

1. **Bảo toàn phần tử:** thao tác phải giữ đúng những phần tử cần giữ, bao gồm số lần xuất hiện nếu cho phép trùng lặp.
2. **Bảo toàn thứ tự:** các phần tử có thứ tự phải tuân theo hợp đồng sau khi cập nhật, như FIFO, LIFO, thứ tự chèn, thứ tự sắp xếp hoặc thứ tự tương đối không bị tác động.
3. **Nhất quán giữa các chỉ mục:** các cách truy cập cùng dữ liệu (theo ID, vị trí, danh mục, khóa phụ, liên kết thuận/ngược) phải cùng mô tả một trạng thái logic.

Ba thuộc tính này bổ sung cho kiểm tra bất biến kích thước, phạm vi chỉ số và cấu trúc liên kết. Chúng đặc biệt quan trọng khi lựa chọn cách biểu diễn bằng mảng, danh sách liên kết, bảng băm, cây, heap hoặc đồ thị.

## 1. Xác định “phần tử” và “thứ tự” theo hợp đồng

Trước khi kiểm tra, cần nêu rõ cấu trúc lưu **giá trị**, **thực thể có định danh**, hay **nhiều lần xuất hiện của cùng giá trị**.

- Một `List` thường cho phép hai phần tử bằng nhau ở hai vị trí khác nhau: `[A, A, B]` có **ba lần xuất hiện**.
- Một `Set` chỉ lưu một đại diện cho mỗi giá trị logic: `add(A)` thêm lần hai thường không đổi tập.
- Một `Map` có một giá trị tại mỗi khóa: `put(k, v2)` thường **thay** giá trị cũ ở khóa `k`, không tạo khóa thứ hai.
- Một hệ thống công việc có thể sử dụng `task_id` duy nhất để xác định thực thể. Hai công việc cùng tiêu đề vẫn là hai phần tử khác nhau nếu ID khác nhau.
- Một `Heap` thường lưu các giá trị hoặc bản ghi có thể trùng độ ưu tiên. Thứ tự vật lý bên trong heap không phải thứ tự logic được bảo đảm, trừ khi API có cam kết riêng.

**Lỗi định nghĩa sẽ dẫn đến lỗi kiểm thử.** Nếu kiểm tra chỉ bằng `set(before) == set(after)`, hai dãy `[A, A, B]` và `[A, B, B]` bị coi là giống nhau, dù số lần xuất hiện đã thay đổi. Nếu chỉ so độ dài, `[A, B]` và `[A, C]` cũng bị xem là tương đương.

### Ba loại đối chiếu thường gặp

| Mục tiêu | Cách kiểm tra | Điều chưa chứng minh được |
|---|---|---|
| Tập phần tử không đổi | `set(before) == set(after)` | Số lần xuất hiện, thứ tự |
| Đa tập (*multiset*) không đổi | `Counter(before) == Counter(after)` | Thứ tự |
| Dãy không đổi | `before == after` | Chỉ đúng khi thứ tự cũng phải giữ nguyên |

Với các giá trị có thể băm, `collections.Counter` là công cụ phù hợp để kiểm tra số lần xuất hiện:

```python
from collections import Counter

before = ["A", "A", "B"]
after = ["A", "B", "A"]

assert Counter(before) == Counter(after)  # Khong mat phan tu
assert before != after                    # Thu tu da thay doi
```

Nếu phần tử không băm được hoặc có thể thay đổi nội dung, hãy dùng **ID ổn định** hoặc một phép so sánh dựa trên hợp đồng, thay vì cố đưa đối tượng thay đổi được vào `Counter`. Khi có ID duy nhất, việc bảo toàn tập ID phải đi kèm kiểm tra thuộc tính của từng ID.

## 2. Phát biểu thuộc tính bảo toàn cho từng phép toán

Giả sử trạng thái logic là dãy \(S=[s_0,s_1,\ldots,s_{n-1}]\), và \(M(S)\) là đa tập các phần tử trong \(S\).

| Phép toán | Bảo toàn phần tử | Bảo toàn thứ tự / nội dung |
|---|---|---|
| `swap(i, j)` | \(M(S')=M(S)\) | Chỉ hai vị trí `i`, `j` được hoán đổi |
| `move(i, j)` | \(M(S')=M(S)\) | Các phần tử không bị di chuyển giữ nguyên thứ tự tương đối |
| `sort()` | \(M(S')=M(S)\) | Dãy thỏa thứ tự sắp xếp; nếu cam kết ổn định, các phần tử cùng khóa giữ thứ tự tương đối |
| `append(x)` | \(M(S')=M(S)\uplus\{x\}\) | Dãy cũ là tiền tố của dãy mới |
| `remove_at(i)` | \(M(S')=M(S)\setminus\{s_i\}\) theo **một lần xuất hiện** | Các phần tử còn lại giữ thứ tự tương đối |
| `set(i, x)` | Thay đúng lần xuất hiện tại `i` | Các vị trí khác không thay đổi |
| `Map.put(k, v)` | Giữ nguyên tập khóa nếu `k` đã có; nếu chưa có, thêm đúng khóa `k` | Mọi ánh xạ của khóa khác `k` không đổi |

Ký hiệu \(\uplus\) là phép hợp của **đa tập**, nên hai lần thêm `x` được đếm thành hai lần xuất hiện. Với phép xóa, nếu có nhiều bản sao của một giá trị, chỉ một lần xuất hiện cụ thể bị loại theo hợp đồng.

### Thuộc tính mạnh hơn “không mất phần tử”

Một thao tác `move(x, j)` trên dãy các phần tử có ID duy nhất không chỉ giữ nguyên tập ID. Nó còn phải giữ **thứ tự tương đối của tất cả ID khác `x`**:

```python
def check_move(before_ids, after_ids, moved_id, new_index):
    assert len(before_ids) == len(after_ids)
    assert len(set(before_ids)) == len(before_ids)
    assert set(before_ids) == set(after_ids)
    assert after_ids[new_index] == moved_id

    before_others = [x for x in before_ids if x != moved_id]
    after_others = [x for x in after_ids if x != moved_id]
    assert before_others == after_others
```

Ví dụ `[A, B, C, D]` chuyển `D` về vị trí `1` phải thành `[A, D, B, C]`. Trạng thái `[A, D, C, B]` không mất phần tử và `D` ở đúng vị trí mới, nhưng **đã đảo thứ tự của `B`, `C`**, vi phạm điều kiện khung (*frame condition*).

Nếu phép toán là `sort`, cần nêu rõ có yêu cầu **sắp xếp ổn định** (*stable sort*) không. Ví dụ các bản ghi `(id, priority)`:

```text
Trước:  A:2, B:1, C:2
Sau ổn định theo priority tăng: B:1, A:2, C:2
```

`A` và `C` cùng độ ưu tiên nên giữ thứ tự `A` trước `C` nếu hợp đồng yêu cầu ổn định. Nếu không yêu cầu, không được coi mọi cách đổi chỗ giữa các phần tử bằng khóa là lỗi.

## 3. Nhiều chỉ mục cùng mô tả một dữ liệu logic

Một cấu trúc thực tế thường duy trì **một nguồn dữ liệu chính** và nhiều chỉ mục để tăng tốc tra cứu:

- `by_id`: tìm bản ghi theo ID.
- `order`: dãy ID theo thứ tự hiển thị hoặc thứ tự chèn.
- `position`: tra vị trí của một ID trong `order`.
- `by_category`: tìm các ID thuộc một danh mục.

Ví dụ một bảng công việc có ba phần tử:

```text
order        = [11, 22, 33]

by_id        = {
    11: Task(11, "Thiết kế", "todo"),
    22: Task(22, "Kiểm thử", "doing"),
    33: Task(33, "Tài liệu", "todo")
}

position     = {11: 0, 22: 1, 33: 2}

by_category  = {
    "todo":  {11, 33},
    "doing": {22}
}
```

Bốn cách nhìn trên phải trả lời nhất quán: công việc `33` ở vị trí `2`, có danh mục `todo`, xuất hiện **đúng một lần** trong dãy thứ tự và đúng danh mục ở chỉ mục phụ.

Gọi `P` là ánh xạ `id → bản ghi`, `O` là dãy ID, `pos` là ánh xạ ID → vị trí, và `C[g]` là tập ID của danh mục `g`. Các bất biến chính:

\[
\begin{aligned}
&|O|=|P|=|pos|,\\
&\operatorname{set}(O)=\operatorname{keys}(P)=\operatorname{keys}(pos),\\
&\forall i\in[0,|O|),\quad pos[O[i]]=i,\\
&\forall g,\quad C[g]=\{id\in\operatorname{keys}(P)\mid P[id].category=g\}.
\end{aligned}
\]

Thêm vào đó, **ID trong `O` phải duy nhất**, mỗi tập `C[g]` chỉ chứa ID đang tồn tại, và không được để lại nhóm danh mục rỗng nếu đã chọn quy ước xóa nhóm rỗng.

Các điều kiện này kiểm tra **tính nhất quán của các chỉ mục**, nhưng chưa đủ để chứng minh thao tác cập nhật đúng nghiệp vụ. Chẳng hạn, nếu đổi nhầm danh mục của một bản ghi ở cả `P` lẫn `C`, tất cả chỉ mục vẫn có thể nhất quán với nhau. Cần so trạng thái với mô hình hoặc giá trị mong đợi trước và sau thao tác.

### Một thay đổi phải cập nhật những nơi nào?

| Phép toán | Dữ liệu chính | Dãy thứ tự | Chỉ mục vị trí | Chỉ mục danh mục |
|---|---|---|---|---|
| Thêm công việc mới | Thêm `id → record` | Nối ID vào cuối | Gán vị trí cuối | Đưa ID vào đúng nhóm |
| Di chuyển công việc | Giữ nguyên record | Đổi vị trí một ID | Tính lại vị trí ID bị ảnh hưởng | Giữ nguyên |
| Đổi danh mục | Thay record tại ID | Giữ nguyên | Giữ nguyên | Bỏ nhóm cũ, thêm nhóm mới |
| Xóa công việc | Xóa ID | Xóa đúng một ID | Cập nhật các vị trí còn lại | Bỏ ID khỏi nhóm cũ |
| Đọc theo ID/vị trí/nhóm | Không đổi | Không đổi | Không đổi | Không đổi |

Dòng “giữ nguyên” rất quan trọng: nó là điều kiện khung cho từng thao tác. Một phép đổi danh mục không được vô tình đảo vị trí hiển thị; một phép di chuyển không được thay đổi nội dung hoặc nhóm của công việc.

## 4. Ví dụ Python: cấu trúc có ba loại chỉ mục

Ta xây dựng `IndexedTasks` với các phương thức `add`, `remove`, `move`, `change_category`, `get`, `position_of`, `ordered_items`, `ids_in_category`. Mỗi công việc có **ID duy nhất**; tiêu đề có thể trùng nhau. Chỉ số vị trí bắt đầu từ `0`, và `move(id, j)` đưa phần tử tới **vị trí cuối cùng `j`** sau khi di chuyển.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    category: str


class IndexedTasks:
    def __init__(self, check_invariants=True):
        self._by_id: dict[int, Task] = {}
        self._order: list[int] = []
        self._position: dict[int, int] = {}
        self._by_category: dict[str, set[int]] = {}
        self._check_enabled = check_invariants
        self._verify()  # Trang thai rong ban dau

    def __len__(self):
        return len(self._order)

    def _reindex_from(self, start):
        # Cap nhat lai tat ca chi so bi dich chuyen.
        for i in range(start, len(self._order)):
            self._position[self._order[i]] = i

    def _assert_consistent(self):
        n = len(self._order)

        # Khong co ID that lac hoac bi lap trong day thu tu.
        assert len(self._by_id) == len(self._position) == n
        assert len(set(self._order)) == n
        assert set(self._order) == set(self._by_id)
        assert set(self._order) == set(self._position)

        # Chi muc vi tri la nghich dao cua day thu tu.
        for index, task_id in enumerate(self._order):
            assert self._position[task_id] == index
            assert self._by_id[task_id].id == task_id

        # Xay dung chi muc danh muc ky vong tu nguon du lieu chinh.
        expected: dict[str, set[int]] = {}
        for task_id, task in self._by_id.items():
            expected.setdefault(task.category, set()).add(task_id)

        assert self._by_category == expected
        assert all(bucket for bucket in self._by_category.values())

    def _verify(self):
        if self._check_enabled:
            self._assert_consistent()

    def add(self, task: Task):
        if task.id in self._by_id:
            raise ValueError("ID da ton tai")

        index = len(self._order)
        self._by_id[task.id] = task
        self._order.append(task.id)
        self._position[task.id] = index
        self._by_category.setdefault(task.category, set()).add(task.id)
        self._verify()

    def move(self, task_id: int, new_index: int):
        if task_id not in self._by_id:
            raise KeyError(task_id)
        if not (0 <= new_index < len(self._order)):
            raise IndexError("vi tri dich khong hop le")

        old_index = self._position[task_id]
        self._order.pop(old_index)
        self._order.insert(new_index, task_id)
        self._reindex_from(min(old_index, new_index))
        self._verify()

    def change_category(self, task_id: int, new_category: str):
        task = self._by_id[task_id]  # KeyError neu khong co ID
        if task.category == new_category:
            self._verify()
            return

        old_bucket = self._by_category[task.category]
        old_bucket.remove(task_id)
        if not old_bucket:
            del self._by_category[task.category]

        updated = Task(task.id, task.title, new_category)
        self._by_id[task_id] = updated
        self._by_category.setdefault(new_category, set()).add(task_id)
        self._verify()

    def remove(self, task_id: int):
        task = self._by_id[task_id]  # KeyError truoc khi sua
        index = self._position[task_id]

        self._order.pop(index)
        del self._position[task_id]
        del self._by_id[task_id]

        bucket = self._by_category[task.category]
        bucket.remove(task_id)
        if not bucket:
            del self._by_category[task.category]

        self._reindex_from(index)
        self._verify()
        return task

    def get(self, task_id: int) -> Task:
        return self._by_id[task_id]

    def position_of(self, task_id: int) -> int:
        return self._position[task_id]

    def ordered_items(self) -> list[Task]:
        return [self._by_id[task_id] for task_id in self._order]

    def ids_in_category(self, category: str) -> list[int]:
        # Ket qua theo thu tu hien thi, khong theo thu tu cua set.
        ids = self._by_category.get(category, set())
        return sorted(ids, key=self._position.__getitem__)
```

### Cách các thao tác duy trì bất biến

**`add`:** từ chối ID đã có **trước khi cập nhật**, thêm bản ghi vào `by_id`, nối ID vào `order`, ghi `position[id]`, rồi thêm ID vào nhóm danh mục. Nếu chỉ thêm vào `order` mà quên `by_category`, `_assert_consistent` báo lỗi ngay sau thao tác.

**`move`:** bỏ ID ở vị trí cũ rồi chèn vào vị trí cuối cùng `new_index`, sau đó làm mới `position` từ vị trí nhỏ hơn trong hai vị trí cũ/mới. Chỉ thứ tự bị thay đổi; ID, nội dung và danh mục giữ nguyên.

**`change_category`:** xóa ID khỏi nhóm cũ, xóa bucket nếu rỗng, cập nhật bản ghi bất biến bằng một `Task` mới, rồi đưa ID vào nhóm mới. Thứ tự và chỉ mục vị trí không đổi.

**`remove`:** xóa bản ghi và đúng một lần xuất hiện của ID trong thứ tự, xóa vị trí cũ, rút ID khỏi danh mục rồi cập nhật chỉ số của phần tử bị dồn lại. Kết quả trả về là bản ghi vừa xóa.

Các phương thức dùng ngoại lệ cho ID không tồn tại hoặc vị trí không hợp lệ. Việc kiểm tra các điều kiện đã định trước khi cập nhật giúp các **nhánh lỗi đã biết** không làm thay đổi trạng thái. Ví dụ chưa đưa ra cam kết giao dịch khi gặp lỗi tài nguyên ngoài dự kiến (như hết bộ nhớ) hoặc khi bị truy cập đồng thời. Muốn có tính nguyên tử trước mọi ngoại lệ hay nhiều luồng, cần thiết kế cơ chế bổ sung.

### Chi phí cần hiểu đúng

Với bảng băm có hành vi phân phối bình thường, tra `get(id)` và `position_of(id)` có chi phí kỳ vọng `O(1)`. `add` thường là `O(1)` khấu hao cho phần thêm vào dãy, cùng chi phí bảng băm kỳ vọng. `change_category` thường là `O(1)` kỳ vọng cho các phép tra/xóa/thêm vào hai nhóm.

`move` và `remove` là `O(n)` do dịch phần tử trong mảng `order` và cập nhật lại nhiều chỉ số `position`. Truy vấn danh mục có `k` phần tử dùng sắp xếp theo vị trí nên tốn `O(k log k)` trong trường hợp tổng quát. Bộ nhớ chính cùng các chỉ mục là `O(n)` theo số công việc, cộng chi phí lưu nhóm danh mục.

**Khi bật `_verify()`**, mỗi phép cập nhật còn phải xây lại và so các chỉ mục, có chi phí kiểm tra tuyến tính theo số phần tử và số nhóm (dưới giả định thao tác băm trung bình). Vì vậy các chi phí ở trên là **chi phí của thuật toán khi tắt kiểm tra toàn bộ**. Bộ kiểm tra là công cụ giai đoạn phát triển; tùy nhu cầu có thể chạy sau từng cập nhật trong kiểm thử và giảm tần suất ở môi trường thực tế.

Các lệnh `assert` của Python có thể bị loại bỏ khi chạy với tùy chọn `-O`. Chúng dùng để phát hiện lỗi lập trình trong kiểm thử, không thay thế cơ chế kiểm tra đầu vào hay báo lỗi của API.

## 5. Kiểm thử đồng thời ba thuộc tính bằng mô hình độc lập

Ta chọn một **danh sách `Task` thường** làm mô hình tham chiếu. Mô hình chỉ lưu thứ tự và nội dung; không có `position` hay `by_category` riêng. Nhờ đó, nó tránh lặp lại đúng cơ chế có thể gây lỗi khi cập nhật chỉ mục.

```python
def assert_matches(tasks: IndexedTasks, expected: list[Task]):
    # Bao toan tat ca ban ghi va thu tu hien thi.
    assert tasks.ordered_items() == expected
    assert len(tasks) == len(expected)

    # Lookup theo ID va vi tri phai chi toi cung ban ghi.
    for index, item in enumerate(expected):
        assert tasks.get(item.id) == item
        assert tasks.position_of(item.id) == index

    # Chi muc danh muc phai tra du cac ID theo thu tu cua model.
    categories = {item.category for item in expected}
    categories.add("khong-ton-tai")
    for category in categories:
        expected_ids = [
            item.id for item in expected if item.category == category
        ]
        assert tasks.ids_in_category(category) == expected_ids


board = IndexedTasks(check_invariants=True)
model = [
    Task(11, "Thiet ke", "todo"),
    Task(22, "Kiem thu", "doing"),
    Task(33, "Tai lieu", "todo"),
]

for item in model:
    board.add(item)
assert_matches(board, model)

# Di chuyen phan tu cuoi len dau.
board.move(33, 0)
model.insert(0, model.pop(2))
assert_matches(board, model)

# Doi danh muc, thu tu khong thay doi.
board.change_category(22, "todo")
model[2] = Task(22, "Kiem thu", "todo")
assert_matches(board, model)

# Xoa phan tu o giua, cac vi tri sau no phai duoc cap nhat.
removed = board.remove(11)
assert removed == Task(11, "Thiet ke", "todo")
model = [item for item in model if item.id != 11]
assert_matches(board, model)

assert [item.id for item in board.ordered_items()] == [33, 22]
assert board.ids_in_category("todo") == [33, 22]
assert board.position_of(22) == 1
```

Tại sao phải so cả ba cách đọc? Nếu `move` đã cập nhật `order` nhưng quên `position`, `ordered_items()` vẫn có thể đúng, còn `position_of` trả sai. Nếu `change_category` cập nhật bản ghi chính mà quên nhóm phụ, `get()` có thể đúng nhưng `ids_in_category()` sai.

### Kiểm tra đường lỗi giữ nguyên trạng thái

```python
before = board.ordered_items()

try:
    board.add(Task(33, "Ban sao", "doing"))
except ValueError:
    pass
else:
    raise AssertionError("ID trung phai bi tu choi")

try:
    board.move(33, len(board))  # Vi tri cuoi hop le la n - 1.
except IndexError:
    pass
else:
    raise AssertionError("move vuot bien phai bi tu choi")

try:
    board.remove(999)
except KeyError:
    pass
else:
    raise AssertionError("ID khong ton tai phai bao loi")

assert board.ordered_items() == before
assert_matches(board, model)
```

Trong một ADT khác, `move` có thể cho phép đưa phần tử tới `index == size` rồi chuẩn hóa. Bài này **chọn** quy ước `0 <= new_index < size` để rõ hậu điều kiện; cần kiểm thử theo chính đặc tả đã công bố.

## 6. Tiêm lỗi để kiểm chứng bộ kiểm tra

Một bộ kiểm tra không nên được tin tưởng chỉ vì đã được viết. Hãy thử cố ý tạo sai lệch trong một đối tượng tách biệt:

```python
broken = IndexedTasks(check_invariants=False)
broken.add(Task(1, "A", "todo"))
broken.add(Task(2, "B", "doing"))
broken.move(2, 0)

# Mo phong bug: chi muc vi tri bi giu theo thu tu cu.
broken._position[2] = 1

try:
    broken._assert_consistent()
except AssertionError:
    print("Da phat hien chi muc vi tri khong nhat quan")
else:
    raise AssertionError("Bo kiem tra bo sot loi")
```

Cú sửa trực tiếp thuộc tính `_position` ở trên chỉ dành cho **kiểm thử chủ động tạo lỗi**, tuyệt đối không phải cách sử dụng API bình thường. Tương tự, có thể xóa ID khỏi `_by_category`, đưa một ID mồ côi vào nhóm, hoặc lặp một ID trong `_order` và xác nhận bộ kiểm tra báo sai.

Cũng cần hiểu giới hạn: nếu đồng thời sửa **mọi** chỉ mục cho phù hợp với một trạng thái nghiệp vụ sai, `_assert_consistent()` có thể vẫn đạt. Mô hình tham chiếu và các điều kiện sau thao tác sẽ giúp phát hiện trường hợp đó.

## 7. Thiết kế ca kiểm thử cho từng loại sai lệch

| Tình huống | Lỗi thường gặp | Kiểm tra cần có |
|---|---|---|
| Thêm bản ghi ID mới | Có trong `by_id` nhưng thiếu trong `order` | Bộ ID ở các chỉ mục bằng nhau |
| Thêm ID trùng | Ghi đè record cũ nhưng vẫn nối ID lần hai | Kích thước và tính duy nhất; trạng thái sau lỗi |
| Di chuyển đầu → cuối | Vị trí của các ID bị dồn không được cập nhật | `position[order[i]] == i` với mọi `i` |
| Di chuyển cuối → đầu | Các phần tử khác vô tình đổi thứ tự tương đối | Dãy sau lọc ID được di chuyển bằng dãy trước lọc ID đó |
| Xóa một phần tử | ID còn sót trong chỉ mục danh mục | Không còn ID ở bất kỳ chỉ mục nào |
| Xóa phần tử cuối trong nhóm | Nhóm phụ rỗng bị bỏ quên nếu quy ước cấm | So `by_category` với nhóm dựng lại từ `by_id` |
| Đổi danh mục | ID xuất hiện đồng thời ở nhóm cũ và nhóm mới | Mỗi ID có đúng một danh mục phù hợp record |
| Sắp xếp ổn định | Hai phần tử cùng khóa bị đảo | Kiểm tra thứ tự tương đối của các bản ghi bằng khóa |
| Xử lý bản sao giá trị | Mất một lần xuất hiện khi xóa | `Counter` hoặc kiểm đếm bằng ID |
| Truy vấn chỉ đọc | Đọc lại làm thay đổi thứ tự/cache quan sát được | Trạng thái logic trước và sau truy vấn giống nhau |

Thử đặc biệt các trạng thái **rỗng, một phần tử, hai phần tử, nhiều phần tử**, các vị trí `0`, `n-1`, các lần di chuyển qua nhau, đổi danh mục nhiều lần và thao tác lặp lại. Những trạng thái đó giúp bộc lộ lỗi cập nhật ở ranh giới của mảng và liên kết.

### Phân biệt mất phần tử và mất quyền truy cập

Một bản ghi có thể còn trong `by_id` nhưng không xuất hiện trong `order`; lúc đó nó **chưa bị xóa khỏi bộ nhớ**, nhưng người dùng duyệt danh sách sẽ không thấy nó. Ngược lại, `order` có thể giữ một ID không còn trong `by_id`, khiến thao tác duyệt gây lỗi.

Vì vậy, với cấu trúc có nhiều chỉ mục, “bảo toàn phần tử” có nghĩa mạnh hơn là **không làm rơi dữ liệu trong một mảng**: mỗi thực thể cần xuất hiện đầy đủ ở tất cả các lối truy cập mà hợp đồng bảo đảm.

## 8. Mở rộng kỹ thuật sang cấu trúc dữ liệu khác

### 8.1. Danh sách liên kết và các con trỏ thuận/ngược

Với danh sách liên kết đôi, `node.next.prev` phải trỏ trở lại `node` và `node.prev.next` phải trỏ tới `node` cho các liên kết hợp lệ. Kiểm tra từ `head` và từ `tail` phải gặp **cùng tập nút với thứ tự ngược nhau**. Sau khi xóa nút duy nhất, cả `head` và `tail` phải được đặt về trạng thái rỗng.

Một bộ kiểm tra tốt không chỉ đếm số bước duyệt bằng `size`: cần phát hiện chu trình bất thường hoặc nút lặp lại, nếu không có thể lặp vô hạn. Với danh sách cố ý dạng vòng, tiêu chí kết thúc và số nút phải được đặc tả riêng.

### 8.2. HashMap, chỉ mục thứ cấp và khóa trùng

Một HashMap có thể duy trì chỉ mục chính `id → record`, chỉ mục phụ `email → id` và chỉ mục nhóm `team → set[id]`. Với mỗi record:

\[
secondaryEmail[record.email] = record.id
\]

nếu email được cam kết là duy nhất. Khi đổi email, phải xóa ánh xạ email cũ, thêm ánh xạ mới và đảm bảo không có hai record dùng cùng email theo hợp đồng. Nếu email **không** duy nhất, chỉ mục phụ phải lưu tập ID thay vì một ID duy nhất.

Va chạm băm không đồng nghĩa khóa bằng nhau. Để kiểm tra, tạo hai khóa khác nhau có cùng hash và xác nhận vẫn tìm được cả hai; nếu có tái băm hoặc tombstone, phải thử tìm/xóa/chèn sau những lần thay đổi đó.

### 8.3. Cây tìm kiếm, cây tăng cường và chỉ mục thứ tự

Một BST phải duy trì thứ tự khóa **trên toàn cây**, không chỉ với cha trực tiếp. Nếu nút có trường `subtree_size` để hỗ trợ truy vấn hạng (*rank*) hoặc phần tử thứ `k` (*select*), bất biến thường là:

\[
subtree\_size(v) = 1 + subtree\_size(v.left) + subtree\_size(v.right).
\]

Sau chèn, xóa hoặc quay cây, cần cập nhật các trường tăng cường. Một cây có quan hệ khóa BST đúng vẫn có thể trả `select(k)` sai nếu `subtree_size` đã lỗi thời. Hãy đối chiếu dãy duyệt *in-order* với danh sách các khóa đã sắp xếp, đồng thời thử `rank`/`select` trên từng vị trí hợp lệ.

Nếu cây cho phép khóa trùng, phải đặc tả cách đếm bản sao trước khi sử dụng `subtree_size` hoặc kiểm tra rank.

### 8.4. Heap và các phần tử cùng độ ưu tiên

Min-heap yêu cầu `parent <= child`; điều đó không đồng nghĩa mọi phần tử được bảo toàn. Một lỗi trong `pop_min` có thể làm rơi một bản sao của giá trị trùng trong khi phần còn lại vẫn thỏa bất biến heap. So sánh **đa tập** trước và sau cùng giá trị trả về sẽ phát hiện lỗi.

Nếu yêu cầu thứ tự ổn định cho các bản ghi cùng ưu tiên, phải bổ sung số thứ tự chèn và kiểm tra phần tử được lấy ra bằng `(priority, sequence_number)` nhỏ nhất. Nếu không có cam kết ổn định, kiểm thử không nên đòi kết quả cụ thể giữa các bản ghi cùng khóa ưu tiên.

### 8.5. Đồ thị và chỉ mục cạnh thuận/ngược

Với đồ thị vô hướng lưu danh sách kề đối xứng, mỗi cạnh `(u, v)` phải được phản ánh ở cả phía `u` và phía `v`, theo quy ước về tự khuyên và cạnh song song. Với đồ thị có hướng có thêm chỉ mục cạnh vào `incoming[v]`, mỗi cung `u → v` trong `outgoing[u]` phải có biểu diễn tương ứng trong `incoming[v]`.

Khi xóa một đỉnh, các cạnh kề cần được loại bỏ khỏi mọi chỉ mục liên quan. Có thể so một **tập cạnh chuẩn hóa** trích từ các chỉ mục để phát hiện cung mồ côi. Đối với đa đồ thị, phải so số lần xuất hiện hoặc ID cạnh, không chỉ dùng `set`.

### 8.6. Fenwick Tree, Segment Tree và các tổng lưu sẵn

Khi cập nhật một phần tử của mảng logic, các tổng lưu trong Fenwick Tree hoặc Segment Tree phải phản ánh cùng thay đổi. Không cần đòi hai cấu trúc có cùng mảng nút nội bộ; chỉ cần **mọi truy vấn theo hợp đồng** cho cùng kết quả.

Với tập dữ liệu nhỏ, có thể so `range_sum(l, r)` với `sum(values[l:r])` trên nhiều đoạn nửa mở. Đặc biệt, khi cập nhật một vị trí, các đoạn **không chứa** vị trí đó phải giữ nguyên tổng. Đây là điều kiện khung tương tự việc một Map không được sửa khóa khác.

## 9. Kiểm tra độc lập và cách phục hồi chỉ mục bị lệch

Có hai cách kiểm tra tính nhất quán:

**Kiểm tra tại chỗ:** sau khi cập nhật, xác minh quan hệ như `position[order[i]] == i` hoặc `id ∈ by_category[category]`.

**Dựng lại kết quả mong đợi:** coi nguồn dữ liệu chính và dãy thứ tự đã được kiểm chứng là chuẩn tạm thời, dựng `expected_position` từ `order` và `expected_category` từ `by_id`, rồi so với các chỉ mục đang lưu. Cách thứ hai giúp phát hiện một thao tác quên cập nhật nhiều phần tử mà không cần đoán vị trí sai.

Nếu xác định **nguồn dữ liệu chính** đáng tin cậy, có thể xây lại các chỉ mục phụ sau một sự cố. Nhưng phải thận trọng: nếu bản thân `order` hoặc `by_id` đã mất dữ liệu, dựng lại chỉ mục phụ từ chúng chỉ khiến các chỉ mục **nhất quán với một trạng thái sai**. Cần dữ liệu nguồn, nhật ký thao tác, bản sao trước đó hoặc mô hình tham chiếu để xác định điều gì thực sự đúng.

Với hệ thống cập nhật nhiều chỉ mục một cách đồng thời, nên xem việc thay đổi dữ liệu chính và các chỉ mục phụ là **một giao dịch logic**. Người đọc không được quan sát trạng thái ở giữa cập nhật khi các chỉ mục chưa đồng bộ. Việc đặt `assert` ở cuối một phương thức chỉ kiểm tra trạng thái sau cùng trong luồng đang chạy; nó không tự cung cấp cơ chế cô lập, khóa, phiên bản hay khả năng khôi phục.

## 10. Bài tập thực hành

### Bài 1 — Phát hiện chỉ mục vị trí sai

Cho:

```text
order     = [10, 20, 30, 40]
position  = {10: 0, 20: 1, 30: 2, 40: 3}
```

Sau khi chuyển ID `40` đến vị trí cuối cùng `1`, dãy đúng là `[10, 40, 20, 30]`. Hãy viết lại toàn bộ `position` và xác định vì sao chỉ cập nhật `position[40] = 1` là chưa đủ.

**Đáp án:** `position = {10: 0, 40: 1, 20: 2, 30: 3}`. Hai phần tử `20`, `30` đã dịch sang phải, nên các vị trí cũ của chúng trở thành lỗi thời. Nếu chỉ cập nhật ID `40`, nhiều ID có thể cùng nhận vị trí `1` và phép truy vấn theo vị trí sẽ không nhất quán.

### Bài 2 — Giữ số lần xuất hiện trong heap

Một heap chứa các giá trị logic `[2, 2, 5, 7]`. Sau một lần `pop_min()`, nó trả `2` và còn `[2, 5, 7]` về mặt đa tập. Bộ kiểm thử nào sau đây đủ mạnh hơn: so `set`, so `len`, hay so `Counter`?

**Đáp án:** phải kiểm tra cả giá trị trả về và `Counter` của các phần tử còn lại. Chỉ so `set` có thể bỏ sót việc mất hoặc tăng bản sao; chỉ so `len` có thể bỏ sót thay đổi giá trị. Đồng thời cần kiểm tra bất biến heap trên biểu diễn thực tế.

### Bài 3 — Đồng bộ hai chỉ mục của Map

Nguồn dữ liệu chính có:

```text
by_id[7]  = {email: "a@example.org", team: "A"}
email_idx = {"a@example.org": 7}
team_idx  = {"A": {7}}
```

Hãy mô tả những thay đổi cần thiết khi email chuyển sang `"b@example.org"` và nhóm chuyển sang `"B"`.

**Đáp án:** cập nhật bản ghi tại ID `7`, bỏ ánh xạ email cũ và thêm email mới trỏ về `7`; loại ID `7` khỏi tập `team_idx["A"]`, thêm vào `team_idx["B"]`, xóa nhóm rỗng nếu quy ước như vậy. Trước khi cập nhật email, phải xử lý trường hợp email mới đã được ID khác sử dụng theo hợp đồng về tính duy nhất. `order` và các vị trí, nếu có, phải giữ nguyên.

### Bài 4 — Tự viết bộ kiểm tra cho danh sách liên kết đôi

Giả sử mỗi nút có `prev`, `next` và danh sách có `head`, `tail`, `size`. Hãy nêu những thuộc tính cần kiểm tra sau `insert_after`, `remove` và `move_to_front`.

**Gợi ý:** duyệt từ `head` phải gặp đúng `size` nút không lặp; duyệt từ `tail` phải gặp cùng các nút theo thứ tự ngược; từng liên kết thuận/ngược phải tương ứng; nút đầu không có `prev`, nút cuối không có `next`; nội dung và thứ tự các nút không bị thao tác tác động phải giữ đúng hợp đồng.

## 11. Checklist kiểm chứng bảo toàn và nhất quán

1. Đã xác định rõ **định danh phần tử**, cách xử lý bản sao và chính sách khóa trùng?
2. Với thao tác thêm/xóa/di chuyển, đã kiểm tra **số lượng và giá trị** trước/sau, không chỉ kích thước?
3. Đã kiểm tra thứ tự logic, đặc biệt thứ tự tương đối của các phần tử không bị tác động?
4. Đã xác định các chỉ mục nào phải cùng mô tả một bản ghi, khóa, vị trí hoặc cạnh?
5. Sau cập nhật, các chỉ mục thuận/ngược có còn đồng bộ và không chứa ID mồ côi?
6. Đã thử ca rỗng, một phần tử, phần tử đầu/cuối, ID trùng và các cập nhật lặp?
7. Các đường lỗi đã biết có giữ trạng thái cũ đúng hợp đồng?
8. Bộ kiểm tra có xây kỳ vọng độc lập từ mô hình hoặc nguồn dữ liệu phù hợp, tránh lặp lại cùng lỗi với cài đặt?
9. Khi nhiều chỉ mục được cập nhật, người đọc có được bảo vệ khỏi trạng thái trung gian hay không?
10. Có tách chi phí kiểm tra toàn bộ khỏi chi phí thao tác khi phân tích hiệu năng?

Một cấu trúc dữ liệu đáng tin cậy phải đảm bảo rằng **phần tử nào còn tồn tại, thứ tự nào được cam kết và mọi cách truy cập đều thống nhất**. Kiểm tra đồng thời ba thuộc tính này giúp phát hiện lỗi cập nhật chỉ mục vốn không lộ ra qua các điều kiện đơn giản như `size >= 0` hoặc “không phát sinh ngoại lệ”.
