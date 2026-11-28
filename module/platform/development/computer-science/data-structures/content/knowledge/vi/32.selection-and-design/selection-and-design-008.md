# Kết hợp heap với bảng vị trí để cập nhật ưu tiên

Một hàng đợi công việc có thể chứa hàng nghìn tác vụ, mỗi tác vụ mang một mức ưu tiên. Hệ thống cần luôn lấy ra tác vụ quan trọng nhất, nhưng mức ưu tiên có thể thay đổi: một tác vụ chờ lâu được nâng mức khẩn cấp, một tác vụ đã gần hoàn tất được hạ ưu tiên, hoặc một tác vụ bị hủy khi vẫn đang xếp hàng.

**Heap nhị phân** rất phù hợp để xem hoặc lấy phần tử có ưu tiên cao nhất. Tuy nhiên, nếu chỉ biết mã tác vụ, heap thông thường không cho biết tác vụ nằm ở đâu trong mảng; tìm kiếm tuyến tính có thể mất `O(n)`. Giải pháp là **kết hợp heap với bảng vị trí `id → index`** để biến nó thành *indexed priority queue* (hàng đợi ưu tiên có chỉ mục).

Trong chương **Lựa chọn và thiết kế**, bài này cho thấy cách phối hợp hai cấu trúc với những nhiệm vụ riêng: heap duy trì bất biến ưu tiên; bảng băm hỗ trợ định vị phần tử theo ID. Ta sẽ thiết kế thao tác chèn, cập nhật tăng/giảm ưu tiên, lấy cực trị và xóa tùy ý, chứng minh bất biến, phân tích thời gian/bộ nhớ và viết ví dụ Python tự chứa.

## 1. Đặc tả yêu cầu trước khi chọn cấu trúc

Giả sử mỗi công việc có ba thuộc tính:

```text
Task {
    id: định danh duy nhất
    priority: độ ưu tiên
    payload: dữ liệu công việc
}
```

Ta chọn **min-heap**, nghĩa là **số ưu tiên nhỏ hơn thì quan trọng hơn**: mức 1 cấp bách hơn mức 5. Đây chỉ là quy ước; nếu ứng dụng coi số lớn hơn là ưu tiên cao hơn, có thể dùng max-heap hoặc đảo hàm so sánh.

Các phép toán cần hỗ trợ:

| Phép toán | Ý nghĩa | Kết quả mong muốn |
| --- | --- | --- |
| `insert(id, priority, payload)` | Thêm tác vụ mới có ID chưa tồn tại | Tác vụ được đặt đúng vị trí trong heap |
| `peekMin()` | Xem tác vụ ưu tiên cao nhất | Không loại phần tử |
| `popMin()` | Lấy và loại tác vụ ưu tiên cao nhất | Heap và bảng vị trí cùng được cập nhật |
| `updatePriority(id, newPriority)` | Sửa độ ưu tiên của một tác vụ bất kỳ | Tác vụ di chuyển lên hoặc xuống đúng hướng |
| `remove(id)` | Hủy tác vụ có ID xác định | Xóa đúng tác vụ, không để vị trí cũ trong map |
| `contains(id)` | Kiểm tra ID có còn trong hàng đợi | Kết quả tồn tại chính xác |
| `size()` | Số tác vụ hiện tại | Bằng số mục trong bảng vị trí |

Yêu cầu nghiệp vụ quan trọng:

- Mỗi `id` chỉ có **một phần tử đang hoạt động**; khi chèn trùng ID phải có chính sách rõ (ví dụ báo lỗi).
- Mỗi lần đổi ưu tiên, `peekMin()` phải phản ánh ngay thứ tự mới.
- Xóa hoặc lấy ra một tác vụ phải khiến `contains(id)` trả sai cho ID đó.
- Với **mức ưu tiên bằng nhau**, cần quy tắc phá hòa nếu muốn kết quả xác định.
- Thời gian thực hiện phải tính cả **tìm ID**, **điều chỉnh heap** và **duy trì bảng vị trí**.

Chỉ yêu cầu `peekMin()` và `popMin()` thì heap đơn thuần đã phù hợp. Nhu cầu **sửa hoặc xóa một phần tử biết trước ID** mới khiến việc thêm bảng vị trí trở nên hữu ích.

## 2. Vì sao heap đơn lẻ chưa đủ?

Heap nhị phân thường lưu trong mảng. Với chỉ số bắt đầu từ 0:

```text
parent(i) = (i - 1) // 2     nếu i > 0
left(i)   = 2 * i + 1
right(i)  = 2 * i + 2
```

Bất biến của **min-heap** là: đối với mọi nút có cha, **khóa ưu tiên của cha không lớn hơn khóa ưu tiên của nút đó**.

Ví dụ các số trong cây là độ ưu tiên:

```text
            2 (A)
          /       \
       5 (B)     3 (C)
       /   \       /
    9 (D) 7 (E)  8 (F)

Mảng heap:
i:        0     1     2     3     4     5
heap:    A:2   B:5   C:3   D:9   E:7   F:8
```

Phần tử gốc A có độ ưu tiên nhỏ nhất. Nhưng **mảng heap không được sắp tăng dần**: B:5 đứng trước C:3 vẫn hợp lệ vì B và C cùng cấp, không phải quan hệ cha–con.

Heap hỗ trợ:

- Xem gốc: `O(1)`.
- Thêm phần tử rồi đưa lên bằng `siftUp`: `O(log n)` bước điều chỉnh heap.
- Lấy gốc, đưa phần tử cuối về gốc rồi `siftDown`: `O(log n)` bước điều chỉnh heap.

Tuy nhiên, muốn sửa mức ưu tiên của E khi chỉ biết `id="E"`, ta cần **tìm E trong mảng heap** trước. Vì heap không có thứ tự tổng thể theo ID, quét tìm E có thể tốn `O(n)`. Vậy `updatePriority("E", 1)` trên heap thuần có thể mất `O(n + log n) = O(n)`.

Một `HashMap<Id, Index>` cho phép tìm chỉ số của E trong thời gian **kỳ vọng `O(1)`** dưới những giả định thích hợp, rồi chỉ cần phục hồi bất biến heap trong `O(log n)` bước.

## 3. Cấu trúc ghép: mảng heap và bảng vị trí

Thiết kế gồm hai thành phần:

```text
heap: array<Entry>
pos:  HashMap<Id, Integer>

Entry {
    id
    priority
    payload
    sequence  // số thứ tự chèn, dùng phá hòa nếu cần
}
```

Để cho kết quả xác định khi hai tác vụ có cùng ưu tiên, bài này so sánh theo **cặp `(priority, sequence)`**:

- `priority` nhỏ hơn được xếp trước.
- Nếu cùng `priority`, tác vụ **được thêm vào hàng đợi sớm hơn** được xếp trước.
- Cập nhật ưu tiên không thay đổi `sequence`; xóa rồi thêm lại cùng ID tạo một lượt chèn mới.
- `sequence` tăng duy nhất trong vòng đời hàng đợi. Nếu dùng số nguyên hữu hạn trong hệ thống thực, phải quy định cách tránh tràn/quay vòng.

Quy tắc phá hòa này duy trì thứ tự theo **lần chèn ban đầu trong hàng đợi** đối với các mục có cùng ưu tiên; nó không tự biến hàng đợi thành FIFO cho các mục từng có mức ưu tiên khác nhau.

Ví dụ:

```text
heap:
    index    0        1        2        3        4
           [B:3]    [E:7]    [C:6]   [D:10]   [A:8]

pos:
    B -> 0
    E -> 1
    C -> 2
    D -> 3
    A -> 4
```

Ở đây bảng vị trí ánh xạ **ID của tác vụ sang chỉ số hiện tại trong mảng heap**. Nó phải đổi theo mỗi lần hoán đổi, vì `siftUp` hoặc `siftDown` có thể di chuyển một tác vụ qua nhiều chỉ số.

### 3.1. Hai bất biến bắt buộc

**Bất biến heap (H):** với mọi chỉ số `i > 0`:

```text
rank(heap[parent(i)]) <= rank(heap[i])

rank(entry) = (entry.priority, entry.sequence)
```

**Bất biến ánh xạ (P):** với mọi vị trí hợp lệ `i` trong mảng:

```text
pos[heap[i].id] == i
len(pos) == len(heap)
```

Đồng thời không có hai phần tử cùng `id`, và mọi khóa trong `pos` đều trỏ đến đúng một phần tử còn tồn tại.

Hai bất biến liên quan nhưng độc lập: heap có thể vẫn có gốc nhỏ nhất đúng dù bảng vị trí đã sai; một lần `updatePriority(id,...)` sau đó mới làm lộ lỗi. Cũng có thể `pos` hoàn toàn đúng nhưng phần tử gốc không phải cực tiểu do quên `siftDown`.

### 3.2. Chi phí bộ nhớ

Với `n` tác vụ:

- Mảng heap chứa `n` mục: `O(n)` bộ nhớ.
- Bảng vị trí có `n` ánh xạ: `O(n)` bộ nhớ bổ sung.
- Mỗi mục có thể chứa ID, ưu tiên, payload và số thứ tự; nếu payload lớn, có thể lưu tham chiếu để tránh sao chép dữ liệu lớn mỗi lần swap.

Bộ nhớ phụ dành cho bảng vị trí tỷ lệ tuyến tính với số tác vụ. Đây là khoản đánh đổi để tránh quét tuyến tính khi sửa/xóa theo ID.

## 4. Quy tắc trung tâm: mọi lần `swap` phải sửa bảng vị trí

Giả sử tác vụ A đang ở vị trí `i`, B đang ở vị trí `j`. Sau khi đổi hai mục trong mảng, cần sửa **cả hai** ánh xạ:

```text
swap(i, j):
    exchange(heap[i], heap[j])

    pos[heap[i].id] = i
    pos[heap[j].id] = j
```

Sơ đồ:

```text
Trước:
heap[i] = A        pos[A] = i
heap[j] = B        pos[B] = j

Sau:
heap[i] = B        pos[B] = i
heap[j] = A        pos[A] = j
```

Nếu chỉ đổi phần tử trong mảng mà quên `pos`, thao tác `updatePriority(A, ...)` tiếp theo có thể sửa **B**. Đây là lỗi nghiêm trọng về tính đúng đắn, thường không phát hiện ngay bằng việc chỉ kiểm tra gốc heap.

Hãy **đóng gói thao tác hoán đổi trong một hàm duy nhất** và dùng nó ở mọi nơi: `siftUp`, `siftDown`, xóa phần tử bất kỳ, lấy gốc. Tránh các đoạn gán trực tiếp `heap[i] = heap[j]` rải rác nếu chưa cập nhật `pos` theo cùng thao tác.

Nếu `i == j`, có thể bỏ qua hoán đổi. Các khóa bảng vị trí phải có ngữ nghĩa hash/equality ổn định trong thời gian tác vụ còn ở hàng đợi.

## 5. Phục hồi heap bằng `siftUp` và `siftDown`

Khi đổi ưu tiên của một nút, quy tắc heap có thể bị vi phạm tại vị trí ấy. Ta không cần sắp lại toàn bộ mảng vì các phần khác vẫn thỏa bất biến.

### 5.1. `siftUp`: ưu tiên trở nên cao hơn

Trong min-heap, **giảm giá trị số của priority** làm tác vụ quan trọng hơn. Nếu nút mới có khóa nhỏ hơn cha, hoán đổi nút với cha, tiếp tục cho tới khi đúng thứ tự hoặc lên gốc.

```text
siftUp(i):
    while i > 0:
        p = parent(i)
        if rank(heap[p]) <= rank(heap[i]):
            break

        swap(p, i)      // swap cập nhật pos cho cả hai ID
        i = p
```

Chiều cao heap là `O(log n)` nên có tối đa `O(log n)` lần hoán đổi. Mỗi swap cần số thao tác mảng hằng số và một số thao tác bảng băm kỳ vọng hằng số; tổng thời gian dự kiến `O(log n)`.

### 5.2. `siftDown`: ưu tiên trở nên thấp hơn

Nếu **tăng giá trị số của priority**, phần tử có thể lớn hơn một trong hai con. Chọn con có khóa `(priority, sequence)` nhỏ hơn để hoán đổi xuống; tiếp tục cho đến khi đúng.

```text
siftDown(i):
    while true:
        l = 2*i + 1
        r = 2*i + 2
        smallest = i

        if l < size and rank(heap[l]) < rank(heap[smallest]):
            smallest = l
        if r < size and rank(heap[r]) < rank(heap[smallest]):
            smallest = r

        if smallest == i:
            break
        swap(i, smallest)
        i = smallest
```

Chi phí điều chỉnh heap dự kiến `O(log n)`. Lựa chọn **con nhỏ hơn** là cần thiết: nếu hoán đổi với con lớn hơn, ta có thể để một con nhỏ hơn nằm dưới cha mới và phá bất biến.

### 5.3. Hàm phục hồi tổng quát `repair(i)`

Sau khi đặt một phần tử bất kỳ vào vị trí `i`, có thể quyết định hướng phục hồi:

```text
repair(i):
    if i > 0 and rank(heap[i]) < rank(heap[parent(i)]):
        siftUp(i)
    else:
        siftDown(i)
```

Vì mảng trước thao tác đã thỏa bất biến heap, việc đặt một phần tử khác tại `i` chỉ có thể gây vi phạm trên đường liên quan tới phần tử ấy. Nếu nó nhỏ hơn cha, cần đưa lên; nếu không, kiểm tra các con để đưa xuống. Cách này đặc biệt tiện khi **xóa một phần tử không nằm ở gốc**, vì phần tử cuối được dời vào vị trí trống có thể cần đi **lên hoặc xuống**.

## 6. Cài đặt các thao tác bằng hai bất biến

### 6.1. Chèn một tác vụ mới

```text
insert(id, priority, payload):
    if pos chứa id:
        báo lỗi ID trùng

    e = Entry(id, priority, payload, nextSequence())
    i = heap.size
    heap.append(e)
    pos[id] = i
    siftUp(i)
```

Trước bước `siftUp`, bảng vị trí đã trỏ đúng phần tử mới. Mỗi swap đưa phần tử đi lên đều cập nhật map cho hai tác vụ. Ở cuối thao tác, cả (H) và (P) đúng.

Nếu mảng động còn dung lượng, chèn vào cuối mất `O(1)`. Nếu phải mở rộng mảng, một lần chèn có thể tốn thêm `O(n)` để cấp phát/sao chép. Với chiến lược tăng dung lượng theo cấp số nhân và hash map thông dụng, thao tác chèn có **kỳ vọng khấu hao `O(log n)`**; không nên tuyên bố `O(log n)` trường hợp xấu tuyệt đối cho toàn bộ lời gọi khi chưa xét cấp phát và rehash.

### 6.2. Cập nhật độ ưu tiên theo ID

```text
updatePriority(id, newPriority):
    if id không thuộc pos:
        báo lỗi NOT_FOUND

    i = pos[id]
    heap[i].priority = newPriority
    repair(i)
```

Mấu chốt là **không tìm tuyến tính trên heap**. Dùng `pos[id]` tìm vị trí kỳ vọng `O(1)` rồi khôi phục heap dự kiến `O(log n)`. Thao tác không thay `id` hoặc `sequence`.

Có thể tách API thành:

- `decreasePriority(id, newPriority)`: chỉ cho phép `newPriority < oldPriority`, dùng `siftUp`.
- `increasePriority(id, newPriority)`: chỉ cho phép `newPriority > oldPriority`, dùng `siftDown`.

Nếu giao diện nhận mọi kiểu thay đổi, `repair(i)` giúp tránh chọn sai chiều. Trong min-heap, “**decrease-key**” có nghĩa giảm **giá trị khóa số**, nhưng chính tác vụ lại có **ưu tiên thực tế cao hơn**. Cần làm rõ tên gọi để tránh đảo logic.

### 6.3. Lấy tác vụ ưu tiên cao nhất

```text
peekMin():
    if heap rỗng: return EMPTY
    return heap[0]

popMin():
    if heap rỗng: return EMPTY
    return removeAt(0)
```

Phần tử gốc luôn có khóa nhỏ nhất nhờ (H). `peekMin` không sửa cấu trúc, chi phí `O(1)`. `popMin` dùng cùng cơ chế xóa nút tại vị trí tùy ý để tránh hai cách cài đặt chồng chéo.

### 6.4. Xóa một tác vụ bất kỳ

Giả sử cần xóa phần tử ở chỉ số `i`, còn phần tử cuối ở chỉ số `last = n-1`. Ta có thể:

1. Hoán đổi phần tử cần xóa với phần tử cuối, đồng thời cập nhật map cho cả hai.
2. Bỏ phần tử cuối khỏi mảng, rồi xóa ID của phần tử đó khỏi map.
3. Nếu `i` vẫn nằm trong mảng sau khi xóa, gọi `repair(i)` để phục hồi heap.

```text
removeAt(i):
    last = heap.size - 1
    swap(i, last)

    removed = heap.popLast()
    pos.remove(removed.id)

    if i < heap.size:
        repair(i)

    return removed
```

Cách này không cần dịch mọi phần tử phía sau như xóa giữa mảng có giữ thứ tự. Heap **không yêu cầu giữ thứ tự mảng tuyến tính**, chỉ yêu cầu bất biến ưu tiên.

Trường hợp biên phải xử lý chính xác:

- Nếu chỉ có một phần tử, `i = last = 0`: xóa phần tử đó, mảng rỗng và không chạy `repair`.
- Nếu xóa phần tử cuối, `i = last`: không còn nút thay thế tại `i` nên không chạy `repair`.
- Nếu xóa một nút ở giữa, phần tử cuối sau khi chuyển vào có thể cần đi lên hoặc xuống.
- Sau khi xóa, ID bị xóa không còn trong `pos`; tái sử dụng cùng ID sau này là một lần chèn mới với thứ tự `sequence` mới.

Hàm `remove(id)` tìm `i = pos[id]` rồi gọi `removeAt(i)`. Tổng chi phí thông thường dự kiến `O(log n)` khi tính truy cập map, sửa liên kết của heap và biến động bộ nhớ theo mô hình thích hợp.

## 7. Mô phỏng các thay đổi trên một heap thực tế

Xét các tác vụ A, B, C, D, E được chèn theo thứ tự đó, với độ ưu tiên nhỏ hơn là cấp bách hơn. Giả sử tất cả ưu tiên khác nhau nên chưa cần xét `sequence`.

| Bước | Thao tác | Mảng heap sau thao tác | Giải thích |
| ---: | --- | --- | --- |
| 1 | `insert(A,8)` | `[A:8]` | A ở gốc |
| 2 | `insert(B,3)` | `[B:3, A:8]` | B sàng lên trên A |
| 3 | `insert(C,6)` | `[B:3, A:8, C:6]` | C không cần đổi chỗ |
| 4 | `insert(D,10)` | `[B:3, A:8, C:6, D:10]` | D ở lá |
| 5 | `insert(E,7)` | `[B:3, E:7, C:6, D:10, A:8]` | E đổi chỗ với A |
| 6 | `updatePriority(D,2)` | `[D:2, B:3, C:6, E:7, A:8]` | D sàng từ chỉ số 3 lên gốc |
| 7 | `updatePriority(D,9)` | `[B:3, E:7, C:6, D:9, A:8]` | D sàng xuống qua B rồi E |
| 8 | `remove(C)` | `[B:3, E:7, A:8, D:9]` | Đổi C với phần tử cuối A, xóa C; heap vẫn hợp lệ |
| 9 | `popMin()` | `[E:7, D:9, A:8]` | Trả B và phục hồi heap |

Kiểm tra thêm bảng vị trí ở bước 7:

```text
heap index:     0      1      2      3      4
heap:         B:3    E:7    C:6    D:9    A:8

pos["B"] = 0
pos["E"] = 1
pos["C"] = 2
pos["D"] = 3
pos["A"] = 4
```

Nếu `siftDown(D)` chỉ đổi dữ liệu trong `heap` mà không cập nhật `pos`, thì sau bước 7 có thể `pos["D"]` vẫn trỏ đến 0. Lệnh `remove("D")` tiếp theo sẽ xóa nhầm B. Đây là lỗi cần kiểm tra sau từng phép hoán đổi.

### Khi hai tác vụ có cùng ưu tiên

Giả sử chèn X mức 5, rồi Y mức 5, sau đó Z mức 1. Nếu dùng cặp `(priority, sequence)` với sequence theo thứ tự chèn, `popMin` sẽ trả Z trước, rồi X trước Y, miễn không có thay đổi khác làm thay đổi quy tắc so sánh. Nếu sau đó đổi X thành mức 8, X có ưu tiên thấp hơn Y nên Y được lấy trước, dù X được chèn trước.

## 8. Hiện thực Python 3: indexed min-heap

Đoạn mã sau minh họa một hàng đợi ưu tiên **có ID duy nhất, cập nhật được priority và xóa theo ID**. Bảng vị trí dùng `dict`, heap dùng `list`. API lựa chọn: chèn trùng ID báo `ValueError`; cập nhật/xóa ID chưa có báo `KeyError`; xem/lấy ở heap rỗng trả `None`.

```python
class _Entry:
    __slots__ = ("id", "priority", "payload", "sequence")

    def __init__(self, id, priority, payload, sequence):
        self.id = id
        self.priority = priority
        self.payload = payload
        self.sequence = sequence


class IndexedMinHeap:
    def __init__(self):
        self.heap = []               # mảng Entry
        self.pos = {}                # id -> chỉ số hiện tại
        self.next_sequence = 0

    def __len__(self):
        return len(self.heap)

    def contains(self, id):
        return id in self.pos

    def _rank(self, i):
        e = self.heap[i]
        return (e.priority, e.sequence)

    def _swap(self, i, j):
        if i == j:
            return
        self.heap[i], self.heap[j] = self.heap[j], self.heap[i]

        # Cập nhật đầy đủ bảng vị trí sau MỌI hoán đổi.
        self.pos[self.heap[i].id] = i
        self.pos[self.heap[j].id] = j

    def _sift_up(self, i):
        while i > 0:
            parent = (i - 1) // 2
            if self._rank(parent) <= self._rank(i):
                break
            self._swap(i, parent)
            i = parent

    def _sift_down(self, i):
        n = len(self.heap)
        while True:
            left = 2 * i + 1
            right = 2 * i + 2
            smallest = i

            if left < n and self._rank(left) < self._rank(smallest):
                smallest = left
            if right < n and self._rank(right) < self._rank(smallest):
                smallest = right

            if smallest == i:
                break
            self._swap(i, smallest)
            i = smallest

    def _repair(self, i):
        if i > 0 and self._rank(i) < self._rank((i - 1) // 2):
            self._sift_up(i)
        else:
            self._sift_down(i)

    def insert(self, id, priority, payload=None):
        if id in self.pos:
            raise ValueError("duplicate task ID")

        e = _Entry(id, priority, payload, self.next_sequence)
        self.next_sequence += 1

        i = len(self.heap)
        self.heap.append(e)
        self.pos[id] = i
        self._sift_up(i)

    def update_priority(self, id, new_priority):
        if id not in self.pos:
            raise KeyError(id)

        i = self.pos[id]
        old_priority = self.heap[i].priority
        self.heap[i].priority = new_priority
        self._repair(i)
        return old_priority

    def peek_min(self):
        if not self.heap:
            return None
        e = self.heap[0]
        return (e.id, e.priority, e.payload)

    def _remove_at(self, i):
        last = len(self.heap) - 1
        self._swap(i, last)

        removed = self.heap.pop()
        del self.pos[removed.id]

        if i < len(self.heap):
            self._repair(i)

        return (removed.id, removed.priority, removed.payload)

    def pop_min(self):
        if not self.heap:
            return None
        return self._remove_at(0)

    def remove(self, id):
        if id not in self.pos:
            raise KeyError(id)
        return self._remove_at(self.pos[id])

    def check_invariants(self):
        # Dành cho kiểm thử; O(n), không chạy sau mỗi lời gọi thực tế.
        assert len(self.pos) == len(self.heap)
        for i, entry in enumerate(self.heap):
            assert self.pos[entry.id] == i
            if i > 0:
                assert self._rank((i - 1) // 2) <= self._rank(i)
        return True

    def snapshot(self):
        # Thứ tự heap vật lý, KHÔNG phải thứ tự sắp toàn bộ.
        return [(e.id, e.priority) for e in self.heap]
```

Mã trên dùng khóa `id` có thể băm, `priority` hỗ trợ so sánh toàn phần nhất quán và một thứ tự chèn không bị tràn. Không nên truyền giá trị `NaN` làm priority trong số thực dấu phẩy động, vì `NaN` phá vỡ các phép so sánh thông thường. Với một hệ thống thời gian thực hoặc nhiều luồng, việc cấp phát lại mảng, tái băm và đồng bộ cần phân tích bổ sung.

### Kiểm chứng các thao tác và bất biến

```python
q = IndexedMinHeap()
for task, priority in [
    ("A", 8), ("B", 3), ("C", 6), ("D", 10), ("E", 7)
]:
    q.insert(task, priority)
    assert q.check_invariants()

assert q.snapshot() == [
    ("B", 3), ("E", 7), ("C", 6), ("D", 10), ("A", 8)
]

q.update_priority("D", 2)
assert q.peek_min() == ("D", 2, None)
assert q.check_invariants()

q.update_priority("D", 9)
assert q.snapshot() == [
    ("B", 3), ("E", 7), ("C", 6), ("D", 9), ("A", 8)
]
assert q.check_invariants()

assert q.remove("C") == ("C", 6, None)
assert not q.contains("C")
assert q.check_invariants()

assert q.pop_min() == ("B", 3, None)
assert q.snapshot() == [("E", 7), ("D", 9), ("A", 8)]
assert q.check_invariants()

# Khi priority bằng nhau, sequence theo thứ tự chèn phá hòa.
tie = IndexedMinHeap()
tie.insert("X", 5)
tie.insert("Y", 5)
tie.insert("Z", 1)
assert [tie.pop_min()[0] for _ in range(3)] == ["Z", "X", "Y"]

# Xóa phần tử cuối hoặc phần tử duy nhất.
single = IndexedMinHeap()
single.insert("one", 12)
assert single.remove("one") == ("one", 12, None)
assert single.pop_min() is None
assert single.check_invariants()
```

Các ví dụ này là **mã kiểm chứng minh họa**. Trong hệ thống lớn, nên kiểm thử thêm các chuỗi cập nhật tăng/giảm liên tiếp, xóa nút giữa/cuối, cập nhật gốc, ưu tiên trùng nhau và tải băm bất lợi. Mã ví dụ là đơn luồng; các thao tác sửa `heap` và `pos` cần được đồng bộ như một đơn vị logic nếu sử dụng từ nhiều luồng.

## 9. Chứng minh ngắn tính đúng đắn

Ta chứng minh theo quy nạp trên số thao tác hoàn tất. Ban đầu `heap=[]` và `pos={}` nên cả (H) và (P) đều đúng.

**Chèn:** trước khi phục hồi, mục mới được đặt ở cuối và `pos[id]` trỏ đúng vị trí đó; các phần tử cũ không đổi. Nếu mục mới nhỏ hơn cha, vi phạm heap chỉ nằm trên đường đi tới gốc. `siftUp` sửa từng vi phạm, và mỗi lần swap giữ (P). Sau khi hoàn tất, (H) và (P) đều đúng.

**Cập nhật ưu tiên:** thay đổi chỉ ở một mục, không phá (P). Nếu khóa giảm, mục có thể cần đi lên; nếu khóa tăng, có thể cần đi xuống. `repair` chọn hướng đúng dựa trên quan hệ với cha, còn `siftUp`/`siftDown` phục hồi (H) mà không quên (P).

**Xóa tại vị trí bất kỳ:** chuyển phần tử cuối vào ô bị xóa, xóa ID của nạn nhân khỏi map. Các mục còn lại đều có đúng một vị trí, và map đã được cập nhật trong swap. Chỉ đường liên quan tới mục thay thế có thể vi phạm heap; `repair` phục hồi bất biến.

**Lấy gốc:** gốc là phần tử có khóa nhỏ nhất từ bất biến (H). `popMin` dùng cùng thao tác xóa tại vị trí 0, vì vậy trả đúng cực trị và để lại một heap hợp lệ.

**Xem gốc/kiểm tra tồn tại:** không sửa cấu trúc. `peekMin` đúng nhờ (H), `contains(id)` đúng nhờ (P).

Điểm quyết định của chứng minh là **tất cả các lần thay đổi vị trí đều đi qua `swap` có cập nhật map**. Một phép hoán đổi trực tiếp không cập nhật `pos` đủ để làm chứng minh mất hiệu lực.

## 10. Độ phức tạp: tách chi phí heap và bảng băm

Gọi `n` là số tác vụ hiện có, các ID có chi phí băm/so sánh hằng số theo giả định chuẩn, các thao tác với map có chi phí kỳ vọng `O(1)`.

| Phép toán | Bước trên heap | Bước trên bảng vị trí | Tổng chi phí thông dụng |
| --- | --- | --- | --- |
| `peekMin()` | Đọc `heap[0]`: `O(1)` | Không cần | `O(1)` |
| `contains(id)` | Không cần | Tra map: kỳ vọng `O(1)` | Kỳ vọng `O(1)` |
| `insert(id,priority)` | Thêm cuối rồi `siftUp`: tối đa `O(log n)` lần swap | Một lần chèn và cập nhật map sau các swap | Kỳ vọng khấu hao `O(log(n+1))` |
| `updatePriority(id,p)` | `siftUp` hoặc `siftDown`, `O(log n)` bước | Tra và cập nhật map qua swap | Kỳ vọng `O(log n)` |
| `remove(id)` | Đưa phần tử cuối tới vị trí bị xóa, phục hồi `O(log n)` | Tra ID, sửa map qua swap, xóa khóa | Kỳ vọng khấu hao `O(log n)` |
| `popMin()` | Gỡ gốc, phục hồi `O(log n)` | Sửa map khi swap và xóa ID | Kỳ vọng khấu hao `O(log n)` |
| Liệt kê `n` phần tử trong heap | `O(n)` | Không cần | `O(n)`, **không có thứ tự tăng dần** |
| Lấy mọi phần tử theo ưu tiên | `n` lần `popMin` | Các cập nhật map tương ứng | Kỳ vọng khấu hao `O(n log n)`, heap bị tiêu thụ |

Bảng nhấn mạnh **chi phí dự kiến/khấu hao của toàn bộ cấu trúc triển khai bằng mảng động và hash map**, thay vì khẳng định mọi lời gọi đều có chặn trường hợp xấu logarithmic. Cụ thể:

- Một lần thêm có thể kích hoạt cấp phát lại vùng mảng heap, cần sao chép `Θ(n)` phần tử.
- Một thao tác bảng băm có thể gặp va chạm xấu hoặc kích hoạt rehash với chi phí tuyến tính.
- Một lần giảm kích thước mảng động cũng có thể có chi phí cấp phát/sao chép tùy triển khai.
- Nếu các mục được lưu bằng đối tượng lớn và phép hoán đổi thực sự sao chép toàn bộ nội dung, chi phí swap không còn `O(1)` theo kích thước payload. Hãy cân nhắc lưu tham chiếu hoặc bản ghi nhỏ trong heap.

Khi phân tích riêng **số bước điều chỉnh heap**, `siftUp`/`siftDown` có chặn `O(log n)` trường hợp xấu. Khi yêu cầu chặn thời gian cho **từng lời gọi API**, cần xem xét cả việc cấp phát, hash và đồng bộ.

### 10.1. So với các phương án khác

| Phương án | Tìm ID | Xem/lấy cực trị | Sửa ưu tiên một ID | Đánh đổi |
| --- | --- | --- | --- | --- |
| Mảng không sắp và quét | `O(n)` | Xem cực trị `O(n)` | Tìm ID `O(n)` | Đơn giản, duyệt thuận lợi |
| Heap nhị phân đơn lẻ | `O(n)` để tìm ID | Xem `O(1)`, lấy `O(log n)` bước heap | `O(n)` để tìm + sửa heap | Gọn, phù hợp khi không cập nhật theo ID |
| **Heap + `id → index`** | Kỳ vọng `O(1)` | Xem `O(1)`, lấy dự kiến `O(log n)` | Dự kiến `O(log n)` | Bộ nhớ thêm `O(n)` và bất biến map–heap |
| Cây tìm kiếm cân bằng theo `(priority,id)` + map ID | Kỳ vọng `O(1)` qua map | Cực trị `O(log n)` tìm từ gốc hoặc `O(1)` nếu duy trì con trỏ min thích hợp | Xóa khóa cũ/chèn khóa mới `O(log n)` | Hỗ trợ truy vấn khoảng và duyệt đầy đủ có thứ tự, chi phí nút lớn hơn |
| Hash map theo ID đơn lẻ | Kỳ vọng `O(1)` | Quét cực trị `O(n)` | Kỳ vọng `O(1)` cho việc sửa giá trị | Không duy trì cấu trúc ưu tiên |

Một cây cân bằng cũng có thể hỗ trợ truy vấn `lowerBound` hoặc duyệt theo ưu tiên; heap hữu ích khi chủ yếu cần **xem/lấy cực trị** và sửa ưu tiên theo ID. Nếu cần tất cả công việc theo thứ tự ưu tiên thường xuyên, phải tính chi phí xuất `n` kết quả và khả năng duy trì chỉ mục có thứ tự khác.

## 11. Ứng dụng: hàng đợi tác vụ và Dijkstra

### 11.1. Bộ lập lịch tác vụ

Một hệ thống xử lý nền giữ hàng đợi theo mức khẩn cấp:

- `insert(taskId, priority)` khi nhận tác vụ.
- `updatePriority(taskId, ...)` khi tác vụ sắp hết hạn hoặc thay đổi SLA.
- `remove(taskId)` khi tác vụ bị hủy.
- `popMin()` khi worker nhận tác vụ tiếp theo.

Với heap + bảng vị trí, thao tác theo ID không phải quét toàn bộ hàng đợi. Tuy nhiên, các tác vụ đã được worker lấy khỏi heap không còn trong `pos`; cần cơ chế khác để quản lý tác vụ **đang chạy, hoàn tất hoặc bị thử lại**. Cấu trúc heap chỉ mô tả hàng đợi chờ theo ưu tiên, không phải toàn bộ trạng thái hệ thống.

Nếu chính sách **ưu tiên thay đổi theo thời gian trôi qua** (aging), phải xác định cách cập nhật. Không thể chỉ sửa một hàm so sánh phụ thuộc đồng hồ rồi giả định heap tự sắp lại; khi thứ hạng giữa các phần tử thay đổi mà không đi qua thao tác cập nhật, bất biến (H) có thể không còn đúng. Cần cập nhật có kiểm soát, tái xây, hoặc một thiết kế ưu tiên có quy tắc khác.

### 11.2. Dijkstra: bài toán giảm khóa điển hình

Thuật toán **Dijkstra** tìm đường đi ngắn nhất từ một đỉnh nguồn trên đồ thị có **trọng số cạnh không âm**. Mỗi đỉnh chưa được xử lý có ước lượng khoảng cách `dist[v]`. Khi tìm được đường đi tốt hơn đến `v`, ta muốn **giảm khóa** của `v` trong hàng đợi ưu tiên.

Mã giả ý tưởng với indexed min-heap:

```text
dist[source] = 0
for các đỉnh v khác source:
    dist[v] = +∞

insert(source, 0)
settled = tập rỗng

while priorityQueue không rỗng:
    (u, du) = popMin()
    if u thuộc settled:
        continue
    settled.add(u)

    for mỗi cạnh u -> v có trọng số w >= 0:
        if v thuộc settled:
            continue

        candidate = du + w
        if candidate < dist[v]:
            dist[v] = candidate

            if priorityQueue.contains(v):
                priorityQueue.updatePriority(v, candidate)
            else:
                priorityQueue.insert(v, candidate)
```

Ở đây mỗi đỉnh **chưa cố định** xuất hiện tối đa một lần trong heap; khi cải thiện khoảng cách, ta cập nhật khóa của mục đang có. Thay vì tìm tuyến tính vị trí của đỉnh trong heap, bảng `pos` cung cấp vị trí nhanh.

Với danh sách kề, heap nhị phân và giả định thao tác bảng vị trí kỳ vọng hằng số, phân tích tiêu biểu là **`O((V+E) log V)` kỳ vọng/khấu hao** cho các thao tác hàng đợi có chi phí logarithmic, cộng thời gian duyệt `O(V+E)`. Cách viết tương đương thường gặp là `O(V log V + E log V)` khi `V ≥ 2`. Trên đồ thị không có cạnh âm và trong một mô hình RAM phù hợp, cấu trúc có thể giúp giảm số mục trong heap so với cách chèn bản ghi khoảng cách mới mỗi lần cải thiện.

Dijkstra **không đúng tổng quát cho đồ thị có cạnh trọng số âm**. Cấu trúc indexed heap chỉ tăng tốc hoạt động của hàng đợi; nó không thay đổi điều kiện đúng đắn của thuật toán đường đi ngắn nhất.

### 11.3. So với kỹ thuật chèn trùng và bỏ bản ghi cũ (*lazy deletion*)

Một phương án Dijkstra phổ biến là **không sửa ưu tiên của mục cũ**. Mỗi khi có khoảng cách nhỏ hơn, chèn cặp `(newDistance, vertex)` mới vào heap. Khi `pop`, nếu bản ghi không còn khớp `dist[vertex]` hoặc đỉnh đã cố định thì bỏ qua.

**Ưu điểm:** không cần bảng `vertex → index` và không cần thao tác xóa tùy ý; có thể dùng thư viện heap có sẵn.

**Đánh đổi:** heap có thể chứa nhiều mục cho cùng một đỉnh, cần kiểm tra bản ghi cũ, và số mục tồn tại trong heap có thể tăng theo số lần cải thiện khoảng cách (có thể lên tới `O(E)` trong cách phân tích phổ biến). Mỗi thao tác heap khi ấy có chi phí theo `log H` với `H` là số mục hiện có, thay vì luôn theo `log V` của một heap giữ một mục cho mỗi đỉnh.

Với đồ thị nhỏ hoặc khi thư viện heap không hỗ trợ giảm khóa, lazy deletion thường đơn giản hơn. Với đồ thị lớn và rất nhiều lần giảm khóa, indexed heap có thể giúp khống chế số mục đang tồn tại và bộ nhớ, đổi lại nhiều bất biến phải duy trì. Cần đo trong điều kiện dữ liệu thực.

## 12. Những lỗi triển khai thường gặp

**Quên cập nhật `pos` sau swap.** Mảng heap có thể trông hợp lệ nhưng lần truy cập theo ID tiếp theo thao tác sai phần tử. Đây là lỗi chính cần phòng ngừa bằng hàm `swap` thống nhất.

**Chỉ sửa `pos` của một trong hai phần tử sau swap.** Cả hai phần tử đã đổi chỗ; map phải sửa **hai** ánh xạ. Nếu không, một ID vẫn trỏ tới chỉ số cũ.

**Chỉ dùng `siftUp` cho mọi cập nhật.** Khi tăng giá trị ưu tiên trong min-heap, phần tử có thể cần xuống dưới. Không chạy `siftDown` sẽ khiến gốc hoặc quan hệ cha–con sai.

**Xóa tùy ý nhưng không xét cả hai hướng.** Phần tử cuối đưa vào ô bị xóa đôi khi có khóa nhỏ hơn cha, đôi khi lớn hơn con. `repair` phải chọn hướng đúng.

**Xóa phần tử cuối rồi vẫn cố sửa heap tại chỉ số đã hết hợp lệ.** Kiểm tra `i < len(heap)` sau khi pop trước khi `repair`.

**Quên xóa ID khỏi map khi `popMin` hoặc `remove`.** ID cũ còn trong map có thể khiến `contains` báo sai, cản trở việc chèn lại hoặc trỏ tới vị trí thuộc phần tử khác.

**Cập nhật bằng cách tạo mục mới cùng ID.** Indexed heap trong bài dùng bất biến mỗi ID xuất hiện đúng một lần. Nếu chèn một bản ghi thứ hai, phải chuyển sang thiết kế lazy deletion với hợp đồng khác, không thể tiếp tục tin `pos[id]` là vị trí của một mục duy nhất.

**So sánh nhầm chiều ưu tiên.** Với min-heap, giảm giá trị số làm ưu tiên thực tế *tăng*. Cần mô tả rõ “priority 1 quan trọng hơn priority 9” hoặc đảo comparator đồng nhất ở mọi hàm.

**Không xử lý khóa ưu tiên trùng nhau.** Chỉ so priority có thể cho một kết quả hợp lệ nhưng thứ tự phá hòa không ổn định theo yêu cầu. Có thể dùng cặp `(priority, sequence)` hoặc `(priority, id)` nếu các ID so sánh được; phải giữ comparator nhất quán.

**Dùng index heap như định danh bền vững.** Index thay đổi sau swap. Thành phần bên ngoài nên giữ `id` và tra bảng vị trí mỗi lần; không lưu lâu dài vị trí trần.

**Sửa trực tiếp nội dung priority của `heap[i]` từ bên ngoài.** Việc đó phá bất biến (H) nếu không gọi phục hồi. API nên quản lý mọi thay đổi priority trong một phương thức được kiểm soát.

**Giả định so sánh mọi priority đều hợp lệ.** Giá trị không có thứ tự toàn phần nhất quán (ví dụ `NaN`) có thể làm comparator thiếu tính bắc cầu/có những cặp không so sánh được, khiến heap không có ý nghĩa rõ ràng.

**Nhầm bảo đảm logarithmic của sift với bảo đảm thời gian thực.** Cấp phát mảng, rehash, bộ gom rác hoặc tranh chấp khóa có thể làm một lần chèn/xóa chậm hơn. Phải phân tích toàn bộ triển khai và tải công việc.

## 13. Đồng thời, thay đổi khóa và chính sách nâng cao

### 13.1. Đồng thời: thao tác map–heap là một đơn vị logic

Nếu hai luồng cùng chèn hoặc sửa các tác vụ, một luồng có thể thấy `pos[id]` đã đổi trong khi mảng heap chưa đổi tương ứng. Khi đó tra cứu ID có thể trỏ sai phần tử hoặc mảng đang tạm vi phạm bất biến.

Một giải pháp đơn giản cho hệ thống nhiều luồng là dùng **một khóa bảo vệ cả `heap` và `pos`** trong từng thao tác công khai. Nếu có yêu cầu thông lượng cao, có thể xem xét các thiết kế queue ưu tiên đồng thời chuyên dụng; không nên chỉ dùng một concurrent hash map rồi để heap list không đồng bộ.

Tính đúng đắn yêu cầu thao tác hoàn tất phải bảo toàn (H) và (P), và các luồng quan sát cấu trúc theo hợp đồng nhất quán đã định. Không phơi bày iterator hoặc tham chiếu tới phần tử nội bộ nếu có thể bị hoán đổi/xóa mà không có cơ chế bảo vệ vòng đời.

### 13.2. Thay ID khác với thay priority

Trong thiết kế này, **ID là khóa của bảng vị trí và phải ổn định**. Đổi priority chỉ thay `priority` rồi phục hồi heap. Nếu cần đổi ID, phải cập nhật map một cách có kiểm soát và đảm bảo không trùng khóa, hoặc định nghĩa đó là thao tác xóa ID cũ/chèn ID mới.

Không sửa trường `id` trực tiếp trên đối tượng `Entry` khi nó vẫn nằm trong map: bảng có thể tiếp tục chứa khóa cũ còn mảng mang ID mới, phá (P).

### 13.3. Hỗ trợ tăng/giảm ưu tiên đồng thời với lịch sử

Nếu nghiệp vụ cần ghi lịch sử mỗi lần thay mức ưu tiên, cấu trúc heap chỉ giữ **trạng thái hiện tại**. Cần lưu nhật ký sự kiện riêng hoặc phiên bản của các thay đổi; map `id → index` không lưu lịch sử vị trí, và thứ tự vật lý trong heap không biểu diễn thứ tự thời gian.

### 13.4. Bảng vị trí không nhất thiết phải là hash map

Nếu ID là số nguyên trong miền **nhỏ, dày đặc** `0..U-1`, có thể dùng mảng `pos[id]` với giá trị sentinel cho ID không tồn tại. Tra vị trí có chặn `O(1)` trường hợp xấu theo truy cập mảng, nhưng bộ nhớ là `O(U)` dù chỉ có ít tác vụ.

Nếu ID rải rác trên miền rất lớn, hash map có bộ nhớ theo số phần tử hơn. Nếu cần thứ tự theo ID hoặc chặn trường hợp xấu cho thao tác tìm vị trí, một cây cân bằng có thể thay map nhưng thêm chi phí `O(log n)` cho mỗi lần truy cập/cập nhật ánh xạ. Quyết định phải xét mật độ miền ID, nhu cầu tra cứu và bảo đảm hiệu năng.

### 13.5. Ưu tiên theo tiêu chí phức hợp

Một số hệ thống dùng khóa như `(deadline, severity, sequence)`. Chỉ cần định nghĩa comparator có thứ tự toàn phần nhất quán và không đổi logic ngầm trong khi heap đang chứa phần tử.

Nếu tiêu chí ưu tiên phụ thuộc **thời gian hiện tại** hoặc dữ liệu ngoài heap thay đổi tự phát, quan hệ thứ tự giữa các phần tử có thể đổi mà không đi qua `updatePriority`. Khi đó cần lập lịch làm mới, tái xây heap hoặc dùng thiết kế phù hợp hơn.

## 14. Bài tập áp dụng và tự kiểm tra

### Bài 1 — Chọn hướng di chuyển

Heap có gốc `A:2`, con `B:5` và `C:3`. Nếu B được cập nhật từ 5 xuống 1 thì dùng `siftUp` hay `siftDown`? Nếu A từ 2 tăng lên 9 thì dùng gì?

*Đáp án:* B có khóa nhỏ hơn cha nên `siftUp`; A có thể lớn hơn con nên `siftDown`. Cả hai thao tác phải sửa map sau mọi swap.

### Bài 2 — Xóa mục không ở gốc

Heap:

```text
i:      0    1    2    3    4
heap:  A:2  B:4  C:6  D:8  E:5
```

Xóa B ở vị trí 1. Phần tử cuối E:5 chuyển tới vị trí 1. Cần phục hồi theo hướng nào?

*Đáp án:* có thể chỉ cần kiểm tra quan hệ với cha/con; ở đây E:5 ≥ A:2 và ≤ D:8, nên không cần đổi chỗ. Map phải bỏ B và ghi E ở vị trí 1; đây là trường hợp `repair` không có swap nhưng vẫn cần đúng bảng vị trí.

### Bài 3 — Lỗi bảng vị trí

Một triển khai hoán đổi A và B trong heap nhưng chỉ chạy `pos[A] = newIndexA`. Điều gì có thể sai khi `updatePriority(B, 1)` chạy?

*Đáp án:* map của B vẫn lưu vị trí cũ, giờ chứa A. Lệnh cập nhật có thể sửa A, tạo sai kết quả và phá bất biến cả map–heap.

### Bài 4 — Tác vụ cùng ưu tiên

Chèn X:5 rồi Y:5 và dùng cặp `(priority, sequence)`. Nếu tiếp tục giảm Y xuống 1 rồi tăng lại 5, khi cả hai đều mức 5, X hay Y được lấy trước?

*Đáp án:* X, vì sequence của X nhỏ hơn và cập nhật priority không thay sequence. Đây là quy tắc phá hòa của thiết kế bài này.

### Bài 5 — Heap thuần hay indexed heap?

Hệ thống chỉ `push` và `popMin`, không bao giờ sửa/xóa theo ID. Có đáng duy trì map vị trí không?

*Gợi ý:* heap thuần thường đơn giản hơn và tiết kiệm bộ nhớ. Bảng vị trí chỉ đem lại lợi ích khi có thao tác cần định vị phần tử theo ID đủ thường xuyên.

### Bài 6 — Dijkstra và phần tử trùng

Một phiên bản Dijkstra thêm cặp `(newDist, v)` mới mỗi khi tìm đường tốt hơn mà không sửa bản ghi cũ. Có cần giữ duy nhất một vị trí `pos[v]` không?

*Đáp án:* không. Đây là kỹ thuật lazy deletion, có thể chứa nhiều bản ghi cùng đỉnh. Phải bỏ qua bản ghi cũ khi lấy ra; số mục và chi phí heap có thể tăng. Nếu dùng indexed heap, cần một mục cho mỗi đỉnh đang xếp hàng và gọi `updatePriority` thay vì chèn trùng.

### Bài 7 — Ưu tiên thay đổi theo đồng hồ

Mức ưu tiên được tính bằng `deadline - now` mỗi khi so sánh. Nếu heap không nhận bất kỳ `updatePriority` nào, có thể đảm bảo thứ tự heap luôn phản ánh chính sách mong muốn không?

*Định hướng:* không được mặc định. Cần phân tích liệu comparator thay đổi **quan hệ tương đối** giữa các phần tử theo thời gian hay không. Nếu chỉ trừ cùng một hằng số `now` khỏi mọi deadline, thứ tự theo deadline không đổi và có thể so trực tiếp deadline; với quy tắc aging phức tạp làm các mức ưu tiên tương đối đổi khác nhau, phải có cơ chế làm mới hoặc cấu trúc khác.

## Kết luận

**Heap quản lý thứ tự ưu tiên; bảng vị trí quản lý khả năng tìm một phần tử cụ thể theo ID.** Kết hợp hai cấu trúc giúp sửa ưu tiên và xóa tùy ý mà không phải quét `O(n)` phần tử. Đổi lại, mỗi lần hoán đổi trong heap phải cập nhật đúng **hai** ánh xạ ID → vị trí, và mỗi lần xóa phải loại ID khỏi map. Đây là cốt lõi của bất biến phối hợp.

Với heap nhị phân và hash map thông dụng, `peekMin` có chi phí `O(1)`, tìm ID kỳ vọng `O(1)`, còn thêm/cập nhật/xóa/lấy gốc thường có chi phí dự kiến hoặc kỳ vọng khấu hao `O(log n)` dưới các giả định phù hợp về lưu trữ và băm. Cấu trúc đặc biệt hữu ích cho bộ lập lịch, hàng đợi tác vụ thay đổi mức khẩn cấp và Dijkstra với thao tác giảm khóa.

Khi chọn thiết kế, hãy hỏi liệu ứng dụng có thực sự cần cập nhật ưu tiên theo ID, có cần thứ tự phá hòa, yêu cầu chặn thời gian nào, giới hạn bộ nhớ bao nhiêu và có nhiều luồng cùng truy cập hay không. Việc duy trì **đúng bất biến heap và bảng vị trí sau mọi thao tác** quan trọng ngang với lợi ích về độ phức tạp.
