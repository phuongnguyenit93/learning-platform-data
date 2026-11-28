# Thay đổi khóa, xóa phần tử và nhu cầu biết vị trí

## 1. Bài toán: không phải lúc nào ta cũng chỉ thêm và lấy gốc

Một **hàng đợi ưu tiên** (*priority queue*) quản lý nhiều yêu cầu, mỗi yêu cầu có một **khóa ưu tiên** (*priority key*). Nếu khóa nhỏ hơn nghĩa là cần xử lý trước, ta thường dùng **min-heap**:

```text
                   (2, B)
                  /      \
              (5, A)    (3, D)
              /   \      /   \
          (9, E) (7, C) (8, F) (4, G)

Mảng khóa:     [2, 5, 3, 9, 7, 8, 4]
Mảng ID:       [B, A, D, E, C, F, G]
Chỉ số:         0  1  2  3  4  5  6
```

Ta đã biết cách thêm một yêu cầu bằng **đẩy lên** (*sift-up*) và lấy yêu cầu ưu tiên nhất bằng **đẩy xuống** (*sift-down*). Nhưng một hệ thống thực tế còn cần:

- Công việc `C` được nâng mức khẩn cấp: thay khóa từ `7` xuống `1`.
- Công việc `A` bị hoãn: thay khóa từ `5` lên `10`.
- Công việc `E` bị hủy: xóa nó dù nó **không nằm ở gốc**.
- Người dùng chỉ đưa ra mã `"C"`, không biết hiện nó đang ở chỉ số nào của heap.

Ba thao tác **thay đổi khóa**, **xóa phần tử bất kỳ** và **xác định vị trí hiện tại của phần tử** liên quan chặt chẽ nhưng phải phân tích riêng. Đây là nơi một câu “heap thao tác `O(\log n)`” rất dễ bị hiểu sai.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt *decrease-key*, *increase-key*, xóa gốc và xóa tại vị trí bất kỳ.
2. Biết lúc nào cần `sift-up`, lúc nào cần `sift-down`, và vì sao.
3. Cài thao tác thay khóa và xóa khi **đã có chỉ số hợp lệ** trong `O(\log n)`.
4. Hiểu vì sao một heap thông thường không hỗ trợ tìm nhanh một `id` bất kỳ.
5. Thiết kế **indexed heap** với ánh xạ `id\to index` và cập nhật ánh xạ sau từng lần hoán đổi.
6. So sánh đánh đổi của **xóa lười** (*lazy deletion*) trên thư viện `heapq`.
7. Dự đoán lỗi khi khóa trùng, chỉ số bị cũ, đối tượng đổi vị trí hoặc có nhiều thao tác đồng thời.

Đây là nội dung của chương **Heap và hàng đợi ưu tiên** trong học phần **Cấu trúc dữ liệu**. Tư duy về bất biến, thời gian, bộ nhớ và nhu cầu định vị phần tử cũng áp dụng khi lựa chọn mảng, danh sách liên kết, stack, queue, bảng băm, cây và đồ thị.

## 2. Nhắc lại hai bất biến của binary heap

Một **binary heap** thông thường có hai bất biến độc lập.

**Bất biến hình dạng:** các nút tạo thành một **cây nhị phân hoàn chỉnh**; tầng cuối được lấp từ trái sang phải. Nhờ vậy, ta có thể dùng mảng `H` theo thứ tự tầng và không cần con trỏ `left`/`right` trong mỗi nút.

Với chỉ số mảng bắt đầu từ `0`:

\[
parent(i)=\left\lfloor\frac{i-1}{2}\right\rfloor \quad(i>0),
\]

\[
left(i)=2i+1,\qquad right(i)=2i+2.
\]

Chỉ số `j` là vị trí phần tử hợp lệ khi `0\le j<n`, với `n=len(H)`. Gốc `i=0` không có cha.

**Bất biến thứ tự bộ phận:**

- **Min-heap:** `key(parent)\le key(child)`.
- **Max-heap:** `key(parent)\ge key(child)`.

Đây chỉ là quan hệ giữa **cha và con**, không yêu cầu tất cả phần tử trong mảng tăng hoặc giảm dần. Ví dụ:

```text
Min-heap hợp lệ: [2, 5, 3, 9, 7, 8, 4]
                      ^     ^
                    5 > 3 nhưng không sai
```

Hệ quả:

- `peek` đọc gốc trong `O(1)`.
- `push` và `pop` sửa thứ tự theo một đường trong cây, thường `O(\log n)`.
- **Tìm một khóa hoặc ID bất kỳ**, nếu không có chỉ mục bổ sung, vẫn có thể mất `O(n)`.

Điều kiện “đã biết chỉ số phần tử cần sửa” là một tiền đề quan trọng khi phát biểu `O(\log n)` cho cập nhật hoặc xóa tùy ý.

## 3. Thay đổi khóa: tăng và giảm làm vi phạm những cạnh khác nhau

Giả sử một phần tử ở chỉ số `i` có khóa cũ `old`, được đổi thành `new` trong **min-heap** hợp lệ. Tất cả những phần tử khác không đổi.

### Giảm khóa (*decrease-key*)

Nếu `new<old`, phần tử vừa giảm **không thể lớn hơn những con vốn không nhỏ hơn `old`**. Vì vậy, các cạnh từ nó xuống con vẫn hợp lệ. Nhưng nó có thể trở nên **nhỏ hơn cha**:

```text
Trước:             Sau khi giảm khóa:

       2                       2
      / \                     / \
     5   3                   5   3
    / \ / \                 / \ / \
   9  7 8  4               9  1 8  4
      ↑                        ↑
    C: 7                     C: 1
```

Chỉ cần **đẩy lên** (*sift-up*): so sánh với cha, hoán đổi nếu cha có khóa lớn hơn, rồi lặp đến gốc hoặc đến khi quan hệ đúng.

### Tăng khóa (*increase-key*)

Nếu `new>old`, phần tử vẫn không nhỏ hơn cha cũ, nên không thể tự tạo vi phạm **với cha**. Tuy nhiên nó có thể **lớn hơn một trong các con**:

```text
Trước:             Sau khi tăng khóa:

       2                       2
      / \                     / \
     5   3                  10   3
    / \ / \                 / \ / \
   9  7 8  4               9  7 8  4

```

Chỉ cần **đẩy xuống** (*sift-down*): luôn chọn **con nhỏ nhất** nếu có hai con; hoán đổi nếu khóa hiện tại lớn hơn khóa của con ấy, rồi tiếp tục ở tầng dưới.

### Bảng quyết định

| Loại heap | Thay đổi khóa | Hướng sửa |
|---|---|---|
| Min-heap | `new<old` | `sift-up` |
| Min-heap | `new>old` | `sift-down` |
| Max-heap | `new>old` | `sift-up` |
| Max-heap | `new<old` | `sift-down` |
| Cả hai | Khóa không đổi theo quan hệ so sánh | Không cần dịch chuyển nếu không có tiêu chí phụ đổi |

Nếu khóa thực sự là **khóa ghép** `(priority, sequence)`, phải so sánh **toàn bộ khóa ghép** đang dùng cho heap. Chỉ nhìn con số `priority` có thể sai khi thay đổi cả tiêu chí phụ.

## 4. Mô phỏng giảm khóa trong min-heap

Cho mảng hợp lệ:

```text
Chỉ số:   0  1  2  3  4  5  6
H:       [2, 5, 3, 9, 7, 8, 4]
```

Thay phần tử ở `i=4` từ `7` thành `1`.

**Bước 1 — ghi giá trị mới:**

```text
[2, 5, 3, 9, 1, 8, 4]
             ^
             i=4
```

**Bước 2 — so sánh cha:** `parent(4)=(4-1)//2=1`; cha có khóa `5>1` nên hoán đổi:

```text
[2, 1, 3, 9, 5, 8, 4]
    ^
    i=1
```

**Bước 3 — tiếp tục:** `parent(1)=0`; cha có khóa `2>1` nên hoán đổi:

```text
[1, 2, 3, 9, 5, 8, 4]
 ^
 i=0
```

**Bước 4 — dừng tại gốc.** Mọi cạnh lại thỏa `cha\le con`. Có hai lần hoán đổi, mỗi lần đưa phần tử lên một tầng.

Nếu chỉ tìm `"C"` theo ID mà chưa biết nó ở chỉ số `4`, thuật toán phải **xác định vị trí trước**. Việc đẩy lên `O(\log n)` không tự bao gồm bước tìm ID đó.

## 5. Mô phỏng tăng khóa trong min-heap

Vẫn với mảng ban đầu `[2,5,3,9,7,8,4]`, tăng khóa tại `i=1` từ `5` lên `10`:

```text
Ghi khóa mới:
[2, 10, 3, 9, 7, 8, 4]
     ^
     i=1
```

Hai con của `i=1` là `i=3` (khóa `9`) và `i=4` (khóa `7`). **Con nhỏ nhất là `7`**, không phải nút trái `9`. Vì `10>7`, hoán đổi:

```text
[2, 7, 3, 9, 10, 8, 4]
             ^
             i=4 là lá
```

Kết quả hợp lệ:

- `2\le7,3`.
- `7\le9,10`.
- `3\le8,4`.

Nếu chọn con `9` thay vì con nhỏ hơn `7`, nút cha mới sẽ là `9` nhưng nút còn lại vẫn `7`, phá bất biến tại chính vị trí vừa xử lý. Quy tắc **chọn con có ưu tiên cao nhất** là bắt buộc đối với `sift-down`.

## 6. Viết hai phép đẩy lên và đẩy xuống bằng Python

Để các ví dụ có thể sử dụng độc lập, ta cài hai hàm trên **min-heap chứa số nguyên**. Chúng sửa trực tiếp `list`, không tạo bản sao.

```python
def sift_up_min(heap: list[int], index: int) -> None:
    """Đẩy phần tử ở index lên; yêu cầu index hợp lệ."""
    while index > 0:
        parent = (index - 1) // 2
        if heap[parent] <= heap[index]:
            break
        heap[parent], heap[index] = heap[index], heap[parent]
        index = parent


def sift_down_min(heap: list[int], index: int) -> None:
    """Đẩy phần tử ở index xuống; yêu cầu index hợp lệ."""
    n = len(heap)
    while True:
        left = 2 * index + 1
        if left >= n:
            break

        right = left + 1
        smaller = left
        if right < n and heap[right] < heap[left]:
            smaller = right

        if heap[index] <= heap[smaller]:
            break

        heap[index], heap[smaller] = heap[smaller], heap[index]
        index = smaller


def is_min_heap(heap: list[int]) -> bool:
    return all(
        heap[(i - 1) // 2] <= heap[i]
        for i in range(1, len(heap))
    )
```

**Tiền điều kiện của hai hàm đẩy:** chỉ một đường/cặp quan hệ quanh phần tử ở `index` có thể sai theo hướng phù hợp; những cây con còn lại phải đã là heap hợp lệ. Chúng **không** tự sửa mọi lỗi tùy ý trong một mảng chưa từng được `heapify`.

Trong ví dụ Python này, `list` hỗ trợ đọc/ghi theo chỉ số `O(1)`. Nếu một phần tử chỉ chứa khóa kích thước cố định, một lần so sánh và hoán đổi tốn `O(1)`.

## 7. Cài thao tác thay khóa khi đã biết chỉ số

Hàm sau thay đổi khóa của một phần tử tại vị trí `i` và chọn hướng sửa theo khóa cũ/mới:

```python
def change_min_key(heap: list[int], index: int, new_key: int) -> None:
    if not 0 <= index < len(heap):
        raise IndexError("Chỉ số không hợp lệ")

    old_key = heap[index]
    heap[index] = new_key

    if new_key < old_key:
        sift_up_min(heap, index)
    elif new_key > old_key:
        sift_down_min(heap, index)


heap = [2, 5, 3, 9, 7, 8, 4]
change_min_key(heap, 4, 1)
print(heap)               # [1, 2, 3, 9, 5, 8, 4]
print(is_min_heap(heap))  # True

heap = [2, 5, 3, 9, 7, 8, 4]
change_min_key(heap, 1, 10)
print(heap)               # [2, 7, 3, 9, 10, 8, 4]
print(is_min_heap(heap))  # True
```

### Phân tích độ phức tạp

Chiều cao cây nhị phân hoàn chỉnh có `n` phần tử là:

\[
h=\lfloor\log_2 n\rfloor \quad(n\ge1).
\]

Mỗi lần hoán đổi trong `sift-up` hoặc `sift-down` đi đúng **một tầng**, nên có nhiều nhất `O(\log n)` lần. Với chỉ số đầu vào `i` **đã biết và đang hợp lệ**:

\[
\boxed{T_{\mathrm{change-key}}(n)=O(\log n),\quad
S_{\mathrm{extra}}=O(1).}
\]

Nếu `new_key==old_key`, hàm không hoán đổi; thời gian là `O(1)`. Nếu `i` là nút lá và tăng khóa trong min-heap, `sift-down` cũng có thể kết thúc ngay.

**Vấn đề còn lại:** nếu người gọi chỉ biết ID hoặc đối tượng nghiệp vụ chứ **không biết `index`**, lấy được chỉ số ấy bằng cách nào?

## 8. Xóa phần tử bất kỳ: không được để lỗ trống trong cây

Giả sử ta muốn xóa phần tử tại chỉ số `i`, không nhất thiết ở gốc. Ví dụ min-heap:

```text
Chỉ số:  0  1  2  3  4  5  6
H:      [2, 5, 3, 9, 7, 8, 4]
                   ^
                 i=3 (9)
```

Nếu chỉ **đặt ô `i=3` thành rỗng**, ta tạo ra khoảng trống giữa các vị trí, phá bất biến hình dạng. Nếu dùng `pop(i)` của `list`, mọi ô sau `i` bị dồn trái, mất `O(n)` thời gian và còn có thể phá thứ tự cha–con.

**Cách xóa theo heap:**

1. Lưu phần tử ở chỉ số `i` để trả về hoặc xử lý hủy.
2. Lấy **phần tử cuối mảng** và giảm độ dài một.
3. Nếu `i` vốn là chỉ số cuối, xong ngay.
4. Nếu không, đặt phần tử cuối vào vị trí `i`.
5. Khôi phục bất biến quanh `i` bằng **đẩy lên hoặc đẩy xuống**, tùy quan hệ với cha và con.

Việc bỏ vị trí cuối giữ được cây nhị phân hoàn chỉnh. Không cần dịch toàn bộ phần đuôi.

### Ví dụ xóa làm phát sinh sift-up

Xóa `H[3]=9` khỏi `[2,5,3,9,7,8,4]`:

```text
Lấy phần tử cuối 4, giảm n:
    [2, 5, 3, 9, 7, 8]

Đặt 4 vào vị trí 3:
    [2, 5, 3, 4, 7, 8]
           ^
        4 < cha 5

Đổi với cha:
    [2, 4, 3, 5, 7, 8]
```

Lưu ý: sau xóa một phần tử `9`, phần tử thay thế `4` **nhỏ hơn cha** `5`, nên phải **đẩy lên**. Nếu mặc định luôn đẩy xuống sau mọi phép xóa, ví dụ này sẽ để lại vi phạm `5>4`.

### Ví dụ xóa làm phát sinh sift-down

Cho min-heap hợp lệ:

```text
[1, 3, 2, 7, 8, 5, 4, 12, 9, 10]
```

Xóa tại `i=1` (giá trị `3`), lấy giá trị cuối `10` thế vào:

```text
[1, 10, 2, 7, 8, 5, 4, 12, 9]
     ^
    10 >= cha 1, nhưng 10 > con 7 và 8
```

Đẩy xuống qua `7` rồi `9`:

```text
[1, 7, 2, 10, 8, 5, 4, 12, 9]
[1, 7, 2,  9, 8, 5, 4, 12, 10]
```

Kết quả thỏa min-heap. Vậy **sau xóa tùy ý, cả hai hướng sửa đều có thể cần thiết**.

## 9. Chọn hướng sửa khi xóa: kiểm tra quan hệ với cha

Đối với **min-heap** hợp lệ trước khi xóa, sau khi thay bằng phần tử cuối `x` ở vị trí `i`:

- Nếu `i>0` và `x<key(parent(i))`, vi phạm nằm về phía **cha** ⇒ dùng `sift-up`.
- Ngược lại, quan hệ với cha đã ổn; nếu có vi phạm thì nằm về phía **con** ⇒ dùng `sift-down`.

Sự thật quan trọng giúp chọn đúng hướng: trước khi xóa, các cây con tại `i` đều đã là min-heap. Khi đặt `x` vào `i`, ta chỉ đổi khóa của một vị trí, không đổi các cạnh khác; vì vậy chỉ một nhóm cạnh gần vị trí thay thế có thể sai.

```python
def remove_min_at(heap: list[int], index: int) -> int:
    """Xóa phần tử tại index trong một min-heap hợp lệ."""
    if not 0 <= index < len(heap):
        raise IndexError("Chỉ số không hợp lệ")

    removed = heap[index]
    last = heap.pop()

    # Nếu phần tử bị xóa vốn ở cuối thì không có vị trí cần sửa.
    if index == len(heap):
        return removed

    heap[index] = last
    if index > 0 and heap[index] < heap[(index - 1) // 2]:
        sift_up_min(heap, index)
    else:
        sift_down_min(heap, index)

    return removed


h = [2, 5, 3, 9, 7, 8, 4]
print(remove_min_at(h, 3))  # 9
print(h)                    # [2, 4, 3, 5, 7, 8]
print(is_min_heap(h))       # True

h = [1, 3, 2, 7, 8, 5, 4, 12, 9, 10]
print(remove_min_at(h, 1))  # 3
print(h)                    # [1, 7, 2, 9, 8, 5, 4, 12, 10]
print(is_min_heap(h))       # True
```

**Vì sao kiểm tra `index == len(heap)` sau `pop()` là đúng?** Trước khi xóa, chỉ số cuối là `n-1`. Sau khi bỏ cuối, độ dài trở thành `n-1`. Nếu `index` bằng độ dài mới, ta đã xóa đúng phần tử cuối cũ; không được ghi vào `heap[index]` nữa.

Đây là thao tác xóa theo **chỉ số đã biết**. Mọi bước xử lý sau khi tìm ra `index` chỉ đi theo tối đa một đường cao `O(\log n)` nên xóa mất:

\[
\boxed{O(\log n)\text{ thời gian, }O(1)\text{ bộ nhớ phụ}.}
\]

Nếu heap chỉ có một phần tử hoặc cần xóa cuối, thao tác có thể hoàn tất bằng `O(1)` bước. Với max-heap, đảo chiều các phép so sánh khi chọn hướng, đẩy lên và đẩy xuống.

## 10. Vì sao biết chỉ số là một giả định quan trọng?

Giả sử một heap chứa `n` công việc, mỗi công việc có `id` riêng và `priority`. Hàm nghiệp vụ muốn gọi:

```text
change_priority("job-218", 1)
cancel("job-047")
```

Nhưng heap mảng chỉ có thứ tự bộ phận theo **priority**, không có thứ tự theo `id`.

```text
Heap (theo priority):

             (2, B)
            /      \
         (5, A)  (3, D)
         /   \    /   \
      (9, E)(7,C)(8,F)(4,G)

Muốn biết C đang ở đâu?
Không suy ra từ C theo công thức cha–con hoặc tìm nhị phân.
```

Nếu chỉ có mảng heap, cách phổ biến là **duyệt lần lượt** các phần tử để so sánh `id`:

```python
def find_by_id(heap: list[tuple[int, str]], job_id: str) -> int | None:
    for index, (_, current_id) in enumerate(heap):
        if current_id == job_id:
            return index
    return None
```

Tìm kiếm này mất **`O(n)` thời gian trường hợp xấu nhất**, giả định so sánh ID `O(1)`. Sau đó thay khóa/xóa tại chỉ số mất thêm `O(\log n)`, nên toàn bộ yêu cầu theo ID là:

\[
O(n)+O(\log n)=\boxed{O(n)}.
\]

Không thể tự động dùng **binary search** trên mảng heap vì mảng không sắp theo ID hay theo priority. Nếu yêu cầu thực sự là tra cứu theo ID thường xuyên, ta cần một **chỉ mục bổ sung**, không chỉ thuật toán đẩy lên/xuống.

## 11. Indexed heap: kết hợp heap với bảng ánh xạ ID → vị trí

Giải pháp thông dụng là lưu đồng thời:

1. **Mảng heap** chứa các bản ghi `(priority, id)`.
2. **Bảng băm** `position[id]=index`, chỉ vị trí hiện tại của bản ghi trong heap.

```text
Heap:
Index:       0      1      2      3
Entry:     (2,B)  (5,A)  (3,D)  (9,E)

position:
   B -> 0
   A -> 1
   D -> 2
   E -> 3
```

Tìm vị trí theo ID bằng bảng băm thường `O(1)` **kỳ vọng**; sau đó sửa heap bằng `O(\log n)` phép cập nhật. Vì thế, với bảng băm hoạt động theo giả định phổ biến:

\[
\boxed{\text{change/remove theo ID}=O(\log n)\text{ kỳ vọng}.}
\]

Đây **không phải bảo đảm** rằng mọi phép tra bảng băm là `O(1)` trường hợp xấu nhất. Va chạm băm, khóa không đáng tin cậy hoặc chính sách tái cấp phát có thể làm chi phí cá biệt lớn hơn; phải phân biệt **kỳ vọng** với **xấu nhất**.

### Bất biến mới của indexed heap

Ngoài heap-order và hình dạng cây, ta cần thêm một bất biến **đồng bộ chỉ mục**:

\[
\forall\,i\in[0,n):\quad position[heap[i].id]=i.
\]

Và với mỗi `id` đang tồn tại, chỉ có **một** bản ghi tương ứng trong heap. Nói cách khác:

- `len(position)=len(heap)` nếu một ID chỉ được dùng một lần.
- Không có ID bị thiếu hoặc trùng trong bảng ánh xạ.
- Mỗi `position[id]` luôn nằm trong `[0,n)` và trỏ đúng `id`.

Nếu bất biến này sai, chương trình có thể sửa **nhầm công việc** dù bất biến heap-order vẫn đúng.

## 12. Từng lần hoán đổi phải cập nhật hai mục ánh xạ

Xét mảng công việc:

```text
Chỉ số:   0        1        2
Heap:   (2,B)    (5,A)    (3,D)
```

Giảm khóa `A` từ `5` xuống `1` sẽ làm A hoán đổi với B:

```text
Trước:
  heap[0]=(2,B)       position[B]=0
  heap[1]=(5,A)       position[A]=1

Sau:
  heap[0]=(1,A)       position[A] PHẢI = 0
  heap[1]=(2,B)       position[B] PHẢI = 1
```

Chỉ thay `heap[0]`, `heap[1]` mà quên cập nhật `position` khiến bảng băm vẫn khẳng định A ở chỉ số `1`. Lần tiếp theo gọi `change_priority("A",...)` có thể sửa nhầm B.

Vì vậy, trong indexed heap, **không nên hoán đổi trực tiếp bằng lệnh gán tuple rải rác**. Tốt hơn là tập trung thành một hàm duy nhất:

```python
def swap_positions(
    heap: list[tuple[int, str]],
    position: dict[str, int],
    i: int,
    j: int,
) -> None:
    heap[i], heap[j] = heap[j], heap[i]
    position[heap[i][1]] = i
    position[heap[j][1]] = j
```

Mỗi lần hoán đổi có `O(1)` lần cập nhật bảng băm **kỳ vọng**. `sift-up` và `sift-down` đi qua nhiều nhất `O(\log n)` tầng, nên việc đồng bộ chỉ số không làm thay đổi cận kỳ vọng `O(\log n)` của một lần sửa heap.

### Những thao tác khác cũng đổi vị trí

- **Thêm mới:** đưa mục mới vào cuối mảng rồi ghi `position[id]=last_index`; mỗi lần hoán đổi khi đẩy lên phải cập nhật bảng.
- **Lấy gốc:** xóa mapping của mục gốc, đưa mục cuối lên gốc rồi ghi vị trí mới; các lần đẩy xuống tiếp tục sửa mapping.
- **Xóa bất kỳ:** xóa mapping của mục bị xóa, thay bằng mục cuối, cập nhật mapping của mục cuối và đẩy lên/xuống.
- **Xây lại heap:** nếu dùng `heapify` hoặc đổi toàn bộ mảng, phải xây lại hoặc cập nhật mapping tương ứng với vị trí cuối.

**Chỉ số trong heap là một vị trí tạm thời, không phải định danh bền vững.** ID là định danh ứng dụng; `position[id]` là chỉ số hiện tại và có thể đổi sau bất kỳ thao tác hoán đổi nào.

## 13. Cài đặt indexed min-heap hoàn chỉnh bằng Python

Ví dụ sau giữ các bản ghi `(priority, sequence, job_id)`. Trường `sequence` là số thứ tự chèn tăng dần, giúp **giữ thứ tự đến trước** khi hai công việc có cùng priority.

Giao diện gồm:

- `push(job_id, priority)`: thêm công việc mới, không cho phép ID trùng khi đang hoạt động.
- `peek()` và `pop()`: xem/lấy công việc ưu tiên nhất.
- `change_priority(job_id, new_priority)`: đổi khóa theo ID.
- `remove(job_id)`: xóa công việc theo ID.
- `get_priority(job_id)`: tra khóa hiện tại theo ID.

### Toàn bộ mã nguồn

```python
from itertools import count


class IndexedMinHeap:
    def __init__(self) -> None:
        # Mỗi mục là (priority, sequence, job_id).
        self._heap: list[tuple[int, int, str]] = []
        self._pos: dict[str, int] = {}
        self._sequence = count()

    def __len__(self) -> int:
        return len(self._heap)

    def _key(self, i: int) -> tuple[int, int]:
        # So sánh theo priority rồi sequence, không so theo job_id.
        priority, sequence, _ = self._heap[i]
        return priority, sequence

    def _swap(self, i: int, j: int) -> None:
        self._heap[i], self._heap[j] = self._heap[j], self._heap[i]
        self._pos[self._heap[i][2]] = i
        self._pos[self._heap[j][2]] = j

    def _sift_up(self, i: int) -> None:
        while i > 0:
            parent = (i - 1) // 2
            if self._key(parent) <= self._key(i):
                break
            self._swap(parent, i)
            i = parent

    def _sift_down(self, i: int) -> None:
        n = len(self._heap)
        while True:
            left = 2 * i + 1
            if left >= n:
                break

            right = left + 1
            best = left
            if right < n and self._key(right) < self._key(left):
                best = right

            if self._key(i) <= self._key(best):
                break
            self._swap(i, best)
            i = best

    def _repair(self, i: int) -> None:
        if i > 0 and self._key(i) < self._key((i - 1) // 2):
            self._sift_up(i)
        else:
            self._sift_down(i)

    def push(self, job_id: str, priority: int) -> None:
        if job_id in self._pos:
            raise ValueError("ID đã tồn tại trong heap")

        entry = (priority, next(self._sequence), job_id)
        i = len(self._heap)
        self._heap.append(entry)
        self._pos[job_id] = i
        self._sift_up(i)

    def peek(self) -> tuple[str, int]:
        if not self._heap:
            raise IndexError("Heap rỗng")
        priority, _, job_id = self._heap[0]
        return job_id, priority

    def get_priority(self, job_id: str) -> int:
        i = self._pos[job_id]  # KeyError nếu không tồn tại.
        return self._heap[i][0]

    def change_priority(self, job_id: str, new_priority: int) -> None:
        i = self._pos[job_id]  # KeyError nếu ID không tồn tại.
        _, sequence, _ = self._heap[i]
        # Giữ nguyên sequence: chỉ thay priority, không đổi tuổi công việc.
        self._heap[i] = (new_priority, sequence, job_id)
        self._repair(i)

    def _remove_at(self, i: int) -> tuple[str, int]:
        removed = self._heap[i]
        last = self._heap.pop()
        del self._pos[removed[2]]

        if i < len(self._heap):
            self._heap[i] = last
            self._pos[last[2]] = i
            self._repair(i)

        return removed[2], removed[0]

    def remove(self, job_id: str) -> tuple[str, int]:
        i = self._pos[job_id]  # KeyError nếu không tồn tại.
        return self._remove_at(i)

    def pop(self) -> tuple[str, int]:
        if not self._heap:
            raise IndexError("Heap rỗng")
        return self._remove_at(0)


queue = IndexedMinHeap()
queue.push("A", 5)
queue.push("B", 2)
queue.push("C", 4)
queue.push("D", 3)

queue.change_priority("A", 1)
print(queue.peek())        # ('A', 1)
print(queue.remove("C"))   # ('C', 4)
print(queue.pop())         # ('A', 1)
print(queue.pop())         # ('B', 2)
print(queue.pop())         # ('D', 3)
print(len(queue))          # 0
```

### Vì sao cài đặt này duy trì đúng cả hai loại bất biến?

1. `push` chỉ thêm **cuối mảng**, giữ cây hoàn chỉnh.
2. `_remove_at` chỉ xóa **cuối mảng** và thay vị trí cũ bằng mục cuối, không tạo lỗ trống.
3. `_sift_up`, `_sift_down` và `_repair` sửa đúng các cạnh có thể bị vi phạm.
4. **Mọi hoán đổi** đều đi qua `_swap`, nên vị trí của cả hai ID được cập nhật.
5. Khi xóa, mapping của ID bị xóa bị xóa thật; mapping của phần tử cuối được cập nhật trước khi sửa heap tiếp.
6. `sequence` không đổi khi chỉ thay priority, bảo đảm các công việc còn tồn tại được so sánh nhất quán theo thời gian đến ban đầu.

Nếu hai công việc có cùng priority, công việc có `sequence` nhỏ hơn sẽ đứng trước trong thứ tự ưu tiên. Đây là quy tắc **chủ động thêm vào**, không phải đặc tính ổn định có sẵn của heap.

**Phạm vi của ví dụ:** giả định `job_id` là chuỗi hashable và duy nhất trong tập đang lưu, priority là số nguyên có so sánh nhất quán, không có hai luồng đồng thời sửa cấu trúc. Nếu chương trình cho phép thay đổi ID hoặc sửa trực tiếp `_heap` từ bên ngoài, phải có cơ chế duy trì bất biến tương ứng.

## 14. Kiểm tra bất biến của indexed heap

Để hiểu rõ điều kiện đúng, ta có thể tự viết hàm kiểm tra cho phiên bản vừa cài. Đây là đoạn mã **minh họa kiểm chứng**, không phải bước bắt buộc chạy sau mọi thao tác trên hệ thống thật:

```python
def verify_indexed_heap(queue: IndexedMinHeap) -> bool:
    entries = queue._heap
    pos = queue._pos
    n = len(entries)

    if len(pos) != n:
        return False

    for i, (priority, sequence, job_id) in enumerate(entries):
        if pos.get(job_id) != i:
            return False

        if i > 0:
            parent = (i - 1) // 2
            if queue._key(parent) > (priority, sequence):
                return False

    return True


q = IndexedMinHeap()
q.push("first", 2)
q.push("second", 2)
q.change_priority("second", 1)
assert verify_indexed_heap(q)
assert q.pop() == ("second", 1)
assert q.pop() == ("first", 2)
assert verify_indexed_heap(q)
```

Hàm xác minh có `O(n)` thời gian và `O(1)` bộ nhớ phụ theo số phần tử heap, bỏ qua bộ nhớ đã thuộc về cấu trúc. Trong ứng dụng thực tế, có thể dùng nó trong kiểm thử, bản debug hoặc kiểm tra có kiểm soát; thêm một vòng kiểm tra `O(n)` sau **mỗi** `push`/`pop` sẽ làm mất lợi ích hiệu năng của heap.

**Kiểm thử biên quan trọng:** xóa gốc, xóa phần tử cuối, xóa phần tử giữa, thay khóa tăng/giảm, ID không tồn tại, chèn ID trùng, heap rỗng và nhiều priority bằng nhau.

## 15. Bảng chi phí: có chỉ số, tìm tuyến tính hay dùng indexed heap?

Giả định các khóa có kích thước cố định và thao tác so sánh `O(1)`, heap nhị phân lưu `n` phần tử, bảng băm có hiệu năng kỳ vọng thông thường.

| Thao tác | Heap mảng khi **đã biết chỉ số** | Heap mảng khi **chỉ biết ID** | Indexed heap (ID + bảng băm) |
|---|---|---|---|
| `peek` gốc | `O(1)` | `O(1)` | `O(1)` |
| `pop` gốc | `O(\log n)` | `O(\log n)` | `O(\log n)` kỳ vọng gồm cập nhật map |
| Thêm một phần tử | `O(\log n)` | `O(\log n)` | `O(\log n)` kỳ vọng |
| Tìm vị trí theo ID | Không cần nếu đã có chỉ số | `O(n)` xấu nhất | `O(1)` kỳ vọng |
| Đổi priority theo ID | `O(\log n)` sau định vị | `O(n)` tính cả quét | `O(\log n)` kỳ vọng |
| Xóa theo ID | `O(\log n)` sau định vị | `O(n)` tính cả quét | `O(\log n)` kỳ vọng |
| Bộ nhớ ngoài mảng heap | `O(1)` cho một thao tác | `O(1)` cho quét | **`O(n)`** cho bảng `id\to index` |

Một heap mảng đơn giản chỉ cần `O(n)` ô cho các phần tử. Indexed heap vẫn cần mảng `O(n)` nhưng bổ sung bảng băm `O(n)`, cùng chi phí cập nhật mapping và chính sách xử lý ID duy nhất.

**Với ít yêu cầu sửa/xóa theo ID**, quét tuyến tính đôi khi đơn giản và hợp lý hơn giữ thêm chỉ mục. **Với nhiều cập nhật theo ID**, bảng ánh xạ thường đáng giá vì giảm chi phí tìm vị trí từ `O(n)` xuống `O(1)` kỳ vọng.

## 16. Khi dùng Python heapq: xóa lười (lazy deletion)

Module chuẩn `heapq` hỗ trợ `heappush`, `heappop`, `heapify` nhưng **không cung cấp trực tiếp một API chung để xóa theo ID hoặc decrease-key theo ID** trên một heap tùy ý.

Một kỹ thuật thông dụng là **xóa lười**:

1. Giữ heap các bản ghi `(priority, sequence, id)`.
2. Giữ bảng `active[id]=(priority, sequence)` biểu diễn bản ghi **mới nhất còn hiệu lực** của ID.
3. Khi đổi priority, **không tìm và sửa bản ghi cũ trong heap**; thêm bản ghi mới với `sequence` mới và cập nhật `active`.
4. Khi hủy, xóa `id` khỏi `active`; bản ghi trong heap trở thành **lỗi thời** (*stale*).
5. Khi `heappop`, bỏ qua mọi bản ghi không còn trùng với `active`.

Ví dụ độc lập:

```python
import heapq
from itertools import count


class LazyPriorityQueue:
    def __init__(self) -> None:
        self._heap: list[tuple[int, int, str]] = []
        self._active: dict[str, tuple[int, int]] = {}
        self._sequence = count()

    def upsert(self, job_id: str, priority: int) -> None:
        ticket = next(self._sequence)
        self._active[job_id] = (priority, ticket)
        heapq.heappush(self._heap, (priority, ticket, job_id))

    def discard(self, job_id: str) -> None:
        self._active.pop(job_id, None)

    def pop(self) -> tuple[str, int]:
        while self._heap:
            priority, ticket, job_id = heapq.heappop(self._heap)
            if self._active.get(job_id) == (priority, ticket):
                del self._active[job_id]
                return job_id, priority
            # Bản ghi đã bị hủy hoặc thay thế: bỏ qua.
        raise IndexError("Không còn công việc hợp lệ")

    def __len__(self) -> int:
        # Số ID còn hiệu lực, không phải số bản ghi trong heap.
        return len(self._active)


queue = LazyPriorityQueue()
queue.upsert("A", 8)
queue.upsert("B", 3)
queue.upsert("A", 1)      # Bản ghi A với priority 8 đã lỗi thời.
queue.discard("B")        # B trở thành lỗi thời.

print(len(queue))         # 1 công việc còn hiệu lực.
print(queue.pop())        # ('A', 1)
print(len(queue))         # 0
```

### Đánh đổi của lazy deletion

**Ưu điểm:** không cần biết chỉ số từng ID; không cần cập nhật bảng `id\to index` sau mỗi lần hoán đổi. Cách này thường dễ phối hợp với `heapq` khi trạng thái công việc do bảng băm khác quản lý.

**Nhược điểm:** các bản ghi lỗi thời **vẫn chiếm bộ nhớ** cho tới khi được pop hoặc heap được xây lại. Nếu một công việc đổi ưu tiên nhiều lần, trong heap có thể có rất nhiều bản ghi cũ của nó.

Gọi `m` là **tổng số bản ghi vật lý trong heap**, bao gồm cả bản ghi lỗi thời; `n` là số công việc hợp lệ, có thể `m\gg n`:

- Mỗi `upsert` thường `O(\log m)` để thêm một bản ghi.
- Một lần `pop` trả công việc hợp lệ có thể phải bỏ qua **nhiều** bản ghi cũ trước nó, nên không bảo đảm một lần gọi luôn `O(\log n)`.
- Mỗi bản ghi vật lý được chèn một lần và lấy khỏi heap nhiều nhất một lần; có thể phân tích chi phí **cộng dồn** trên chuỗi thao tác, thay vì bỏ qua thời gian dọn bản ghi lỗi thời.
- Bộ nhớ cho heap có thể tăng theo **tổng số lần thêm/cập nhật**, không chỉ số công việc còn hoạt động.

Trong hệ thống dài hạn, có thể định kỳ **lọc bản ghi còn hiệu lực rồi `heapify` lại** khi số bản ghi lỗi thời tăng vượt một ngưỡng được lựa chọn. Một lần lọc và xây lại heap tốn `O(m)` thời gian với danh sách đầu vào hiện có, đổi lại giảm dung lượng giữ những bản ghi đã bị hủy.

### Vấn đề ổn định khi đổi priority

Trong ví dụ lazy deletion, mỗi lần `upsert` được cấp **ticket mới**: đó là lựa chọn coi lần cập nhật như một lượt đưa công việc vào hàng đợi mới. Nếu nghiệp vụ yêu cầu một công việc giữ **thứ tự đến ban đầu** khi chỉ đổi priority, cần lưu thêm một `arrival_sequence` ổn định, đồng thời dùng **version riêng** để nhận diện bản ghi lỗi thời. Chính sách này phải được quyết định rõ, không nên dựa vào tính ổn định vốn không có của heap.

## 17. Indexed heap và lazy deletion: chọn phương án nào?

| Câu hỏi | Indexed heap `id\to index` | Heap có xóa lười |
|---|---|---|
| Sửa priority một ID đang hoạt động | Thay bản ghi tại chỗ, `sift-up/down` | Chèn bản ghi mới, bản cũ thành stale |
| Hủy một ID | Xóa vật lý ngay, sửa heap | Đánh dấu không còn hiệu lực |
| Cần cập nhật mapping khi swap | **Có**, sau mọi swap | **Không** với mapping vị trí |
| Số bản ghi vật lý | Gần số công việc hoạt động `n` | Có thể lớn hơn `n` nhiều lần |
| Độ phức tạp cập nhật theo ID | `O(\log n)` kỳ vọng | `O(\log m)` thông thường |
| Một lần pop công việc hợp lệ | `O(\log n)` kỳ vọng | Có thể phải loại nhiều stale |
| Hỗ trợ cùng ID xuất hiện nhiều bản ghi vật lý | Không trong cách cài đặt ví dụ | Có, nhưng chỉ bản ghi được đánh dấu active hợp lệ |
| Phù hợp khi | Cập nhật/hủy nhiều, muốn kiểm soát kích thước | Muốn tận dụng `heapq`, cập nhật đơn giản, chấp nhận dọn stale |

Không có lựa chọn luôn tối ưu. Nếu hệ thống **cần hủy đúng một công việc ngay và bộ nhớ bị giới hạn**, indexed heap có lợi. Nếu hệ thống **thường thêm các ứng viên khoảng cách mới** và dễ phát hiện mục lỗi thời lúc pop, lazy deletion có thể đơn giản hơn.

Trong cả hai phương án, vẫn cần giữ rõ **ID công việc**, **khóa ưu tiên**, **quy tắc hòa** và **hợp đồng cập nhật**; dùng thêm bảng băm không tự giải quyết lỗi nghiệp vụ.

## 18. Ứng dụng trong thuật toán đồ thị và lập lịch

### 18.1. Dijkstra và decrease-key

Trong thuật toán Dijkstra trên đồ thị có **trọng số cạnh không âm**, ta quản lý nhãn khoảng cách tạm thời `dist[v]` cho các đỉnh. Khi tìm được đường đi tốt hơn tới `v`, giá trị `dist[v]` **giảm**, nên:

```text
decrease_key(v, dist_moi)
```

phù hợp với min-heap đánh chỉ mục `v\to index`.

Nếu dùng một heap nhị phân chứa tối đa `V` đỉnh và quản lý chỉ mục chính xác:

- Mỗi `extract-min`: `O(\log V)`.
- Mỗi lần giảm nhãn tại vị trí đã biết: `O(\log V)`.
- Cách phân tích phổ biến của Dijkstra với adjacency list và indexed binary heap là `O((V+E)\log V)`, khi số lần sửa khóa/cập nhật được khống chế theo các bước duyệt cạnh.

Nếu dùng xóa lười, chương trình thường **chèn thêm** cặp `(distance, vertex)` khi có nhãn tốt hơn, sau đó bỏ qua cặp có khoảng cách không còn khớp nhãn mới nhất. Heap có thể giữ nhiều mục cho cùng một đỉnh; độ phức tạp và bộ nhớ lúc ấy phụ thuộc **số bản ghi được đẩy vào**, không chỉ số đỉnh đang hoạt động.

**Chú ý:** phiên bản Dijkstra chuẩn không hỗ trợ trọng số cạnh âm mà vẫn giữ bảo đảm đúng. Kỹ thuật heap chỉ giải quyết việc lấy khoảng cách nhỏ nhất, không thay thế điều kiện đúng đắn của thuật toán đường đi.

### 18.2. Lập lịch công việc có thể hủy

Một bộ lập lịch dùng min-heap theo `deadline`:

```text
("job-A", deadline=15)
("job-B", deadline=8)
("job-C", deadline=20)
```

Khi công việc B bị hủy, nếu chỉ có heap mảng và biết mỗi `id="job-B"`, hệ thống có thể phải quét `O(n)` để tìm nó. Với indexed heap, tìm vị trí bằng bảng băm, xóa bằng đẩy lên/xuống. Với lazy deletion, B được đánh dấu đã hủy và bị bỏ qua khi tới đầu heap.

Nếu cần truy cập **khách hàng theo ID** mà không liên quan đến ưu tiên, một bảng băm quản lý bản ghi nghiệp vụ vẫn là cấu trúc khác với heap. Heap tối ưu hóa **lấy công việc ưu tiên nhất**, không tự là cơ sở dữ liệu tra cứu mọi thuộc tính.

## 19. Lỗi thường gặp khi sửa hoặc xóa heap

| Nhầm lẫn/lỗi | Vì sao sai? | Cách xử lý |
|---|---|---|
| “Decrease-key trong min-heap phải sift-down.” | Khóa mới có thể nhỏ hơn **cha**, không phải con | `sift-up` |
| “Increase-key trong min-heap phải sift-up.” | Khóa mới có thể lớn hơn **con** | `sift-down` |
| “Xóa bất kỳ luôn cần sift-down như pop gốc.” | Phần tử cuối thay vào giữa có thể nhỏ hơn cha | Chọn hướng theo cha hoặc so sánh khóa thích hợp |
| “Có thể xóa trực tiếp phần tử giữa và để trống ô.” | Phá bất biến cây hoàn chỉnh | Thay bằng phần tử cuối, rồi sửa heap |
| “Dùng `list.pop(index)` là xóa heap `O(\log n)`.” | Xóa giữa mảng dịch `O(n)` và có thể phá heap | `pop()` cuối, thế vào vị trí cần xóa |
| “Biết ID tức biết vị trí trong heap.” | Heap chỉ sắp theo priority, không theo ID | Quét hoặc tạo `id\to index` |
| “Heap đã sắp nên dùng tìm kiếm nhị phân.” | Mảng heap không được sắp toàn phần | Không dùng binary search trực tiếp |
| “Sau swap không cần cập nhật bảng chỉ mục.” | Mapping trỏ sai ID/vị trí | Một hàm swap cập nhật cả hai mục |
| “ID trùng có thể dùng map `id\to index` duy nhất.” | Một khóa map chỉ lưu được một vị trí | Quy định ID duy nhất hoặc thiết kế ánh xạ nhiều vị trí |
| “Xóa ID khỏi heap nhưng quên xóa mapping.” | Mapping vẫn chứa vị trí đã vô hiệu | Xóa mapping khi xóa mục |
| “Đổi khóa trực tiếp `H[i]=...` là xong.” | Có thể vi phạm cha–con | Sửa theo `sift-up/down` |
| “Có thể giữ một chỉ số `i` sau nhiều phép swap.” | Vị trí có thể thay đổi | Tra lại mapping qua ID ổn định |
| “`heapq` tự hỗ trợ xóa arbitrary ID.” | API chuẩn không cung cấp trực tiếp hàm đó | Indexed heap riêng hoặc lazy deletion |
| “Lazy deletion không tốn bộ nhớ.” | Stale entries vẫn tồn tại cho tới khi pop/rebuild | Theo dõi `m` và dọn định kỳ |
| “Một lần pop lazy luôn `O(\log n)`.” | Có thể cần pop rất nhiều bản ghi stale | Phân tích theo `m` và chi phí cộng dồn |
| “Heap tự giữ thứ tự đến trước khi priority bằng nhau.” | Heap cơ bản không ổn định | Khóa phụ `sequence` |
| “Key số thực luôn có thứ tự hợp lệ.” | `NaN` có thể phá quy tắc so sánh | Chuẩn hóa khóa hoặc quy định xử lý |
| “Indexed heap an toàn khi sửa từ nhiều luồng.” | Heap và mapping là trạng thái chung cần đồng bộ | Dùng khóa/giao thức concurrent phù hợp |
| “Có thể đổi trực tiếp ID của mục đã lưu.” | Bảng chỉ mục cũ vẫn keyed theo ID cũ | Cấm đổi ID hoặc thực hiện chuyển định danh có kiểm soát |

### Những trường hợp biên cần kiểm tra

- Heap rỗng; `peek` và `pop` phải báo đúng trường hợp rỗng.
- Heap có đúng một phần tử; xóa gốc đồng thời là xóa cuối.
- Xóa **chính phần tử cuối**; không được ghi lại chỉ số đã vượt độ dài.
- Xóa phần tử giữa phải **đẩy lên**; xóa phần tử giữa khác phải **đẩy xuống**.
- Giảm khóa tại gốc và tăng khóa tại lá; có thể không cần hoán đổi.
- Khóa mới bằng khóa cũ và nhiều công việc có cùng priority.
- ID không tồn tại; ID trùng; thay khóa hoặc hủy một công việc đã pop.
- Sau một chuỗi swap, mọi `position[id]` vẫn phải khớp vị trí thực tế.

## 20. Bài tập tự kiểm tra

**Bài 1.** Cho min-heap `H=[2,5,3,9,7,8,4]`. Nếu giảm `H[4]` từ `7` xuống `1`, cần dùng hướng nào và mảng cuối là gì?

**Bài 2.** Với cùng heap ban đầu, tăng `H[1]` từ `5` lên `10`. Vì sao phải chọn con có khóa `7` trước con có khóa `9`? Mảng cuối?

**Bài 3.** Xóa phần tử tại chỉ số `3` trong `H=[2,5,3,9,7,8,4]`. Giá trị trả về và mảng sau xóa là gì? Hướng sửa là lên hay xuống?

**Bài 4.** Xóa chỉ số `1` của min-heap `[1,3,2,7,8,5,4,12,9,10]`. Chỉ ra hai lần hoán đổi cần thiết và mảng cuối.

**Bài 5.** Vì sao một phép `remove_at` không được làm `heap.pop(index)` khi `index` không ở cuối, nếu muốn có `O(\log n)` thời gian và giữ heap-order?

**Bài 6.** Nếu hàm `change_priority(id, p)` chỉ có `id`, chưa có bảng `id\to index`, việc tìm phần tử trong heap tốn bao nhiêu thời gian trường hợp xấu nhất? Tổng chi phí đổi khóa là bao nhiêu?

**Bài 7.** Sau khi hoán đổi hai mục `(2,A)` và `(5,B)` ở các chỉ số `i=0` và `j=3` trong indexed heap, bảng `position` phải thay đổi ra sao?

**Bài 8.** Một indexed heap có `n` mục. Nêu ít nhất **ba bất biến** cần duy trì, gồm cả bất biến ngoài quan hệ cha–con.

**Bài 9.** Khi xóa mục ở chỉ số cuối của heap gồm `n` phần tử, có cần `sift-up` hoặc `sift-down` không? Trường hợp nào phải kiểm tra trước khi ghi phần tử cuối vào vị trí xóa?

**Bài 10.** Trong min-heap, giảm khóa một phần tử đang ở **gốc** có thể phá bất biến không? Còn tăng khóa của **một lá** thì sao?

**Bài 11.** Một ứng dụng cho phép priority bằng nhau và yêu cầu công việc đến trước được lấy trước. Hãy định nghĩa khóa so sánh phù hợp và nói rõ phải làm gì với thứ tự đến khi chỉ thay priority.

**Bài 12.** Với lazy deletion, một công việc A được thêm với priority `8`, đổi sang `1`, rồi hủy. Heap có thể chứa những bản ghi vật lý nào? Có bao nhiêu công việc **hợp lệ**?

**Bài 13.** Vì sao không thể khẳng định một lần `pop` của lazy priority queue luôn chỉ mất `O(\log n)` với `n` là số công việc còn hiệu lực? Đại lượng nào phải tính?

**Bài 14.** Trong Dijkstra, nếu tìm được nhãn khoảng cách nhỏ hơn cho đỉnh `v`, nên dùng thao tác cập nhật khóa nào trong min-heap đánh chỉ mục? Nếu dùng `heapq` không hỗ trợ giảm khóa trực tiếp thì có thể làm gì?

**Bài 15.** Nếu `position[id]=i` là thông tin được lưu lâu dài bên ngoài indexed heap, điều gì có thể xảy ra sau các lần `push`, `pop` hoặc `change_priority`? Nên giao tiếp với cấu trúc qua định danh nào?

**Bài 16.** So sánh chi phí bộ nhớ của indexed heap và heap xóa lười khi có `100` công việc còn hiệu lực nhưng đã thực hiện `10.000` lần thay đổi priority. Vì sao không thể chỉ dùng số `100` để ước lượng bộ nhớ cho phương án xóa lười?

### Đáp án và giải thích

1. **Đẩy lên:** `[2,5,3,9,1,8,4]→[2,1,3,9,5,8,4]→[1,2,3,9,5,8,4]`. Khóa mới nhỏ hơn cha nên cần hai lần swap.
2. **Đẩy xuống:** tại `i=1`, chọn `min(9,7)=7`; kết quả `[2,7,3,9,10,8,4]`. Nếu chọn `9` thì cha mới có thể vẫn lớn hơn con `7`.
3. Xóa `9`, lấy `4` cuối thay vào `i=3`, rồi đẩy **lên** vì `4<5`; còn `[2,4,3,5,7,8]`.
4. Xóa `3`, lấy `10` cuối thay vào `i=1`; đẩy xuống đổi với `7` rồi `9`, thu `[1,7,2,9,8,5,4,12,10]`.
5. `pop(index)` làm dịch các phần tử sau chỉ số đó trong mảng động, mất `O(n)`; các nút sau khi dồn có thể đổi cha làm heap-order sai. Dùng xóa cuối + thay vào ô cần xóa + sửa một đường.
6. Tìm ID bằng quét `O(n)` xấu nhất; sửa khóa `O(\log n)` sau khi biết vị trí; tổng `O(n)`.
7. Nếu A và B hoán đổi cho nhau, `position[A]=3` và `position[B]=0`. Phải cập nhật **cả hai**, không chỉ ID vừa sửa khóa.
8. Cây hoàn chỉnh/biểu diễn các chỉ số liên tục; mọi cha không lớn hơn con (min-heap); mỗi ID đang hoạt động là duy nhất; `position[heap[i].id]=i` và không có mapping thừa.
9. Không cần sửa nếu xóa **chính ô cuối**. Sau `pop()`, nếu chỉ số xóa bằng độ dài mới, không được gán vào vị trí đó; với heap một phần tử, mảng đã rỗng.
10. Giảm khóa ở gốc vẫn không lớn hơn các con, nên không phá min-heap. Tăng khóa tại lá không tạo quan hệ mới với con, vẫn không nhỏ hơn cha, nên không phá min-heap.
11. Dùng `(priority, arrival_sequence)`. Nếu muốn giữ thứ tự đến ban đầu, giữ nguyên `arrival_sequence` khi chỉ đổi priority; nếu xem lần sửa là một lượt mới thì phải quy định rõ chính sách cấp sequence mới.
12. Heap có thể còn các bản ghi `(8,t0,A)` và `(1,t1,A)` nhưng cả hai đều **stale** sau khi hủy, bảng `active` không chứa A. Số công việc còn hợp lệ là `0`.
13. Một lần gọi có thể phải bỏ qua nhiều mục lỗi thời trước khi gặp mục hợp lệ. Phải tính `m` là số bản ghi vật lý và số stale được pop, hoặc phân tích tổng chi phí của nhiều lần gọi.
14. Dùng `decrease-key(v,new_dist)` nếu có chỉ mục `v\to index`; với `heapq` có thể đẩy cặp `(new_dist,v)` mới rồi bỏ qua bản ghi lỗi thời lúc lấy.
15. Vị trí `i` có thể đổi sau bất kỳ lần hoán đổi, nên giữ chỉ số cũ sẽ định vị sai công việc. Gọi API theo **ID ổn định**, để heap quản lý chỉ số nội bộ.
16. Indexed heap giữ gần `100` bản ghi vật lý và một bảng `O(100)` ánh xạ. Lazy heap có thể chứa rất nhiều bản ghi cũ của các lần cập nhật, tùy đã pop hoặc rebuild đến đâu; `m` có thể lên tới hàng nghìn dù số công việc hợp lệ vẫn là `100`.

## 21. Ghi nhớ

**Thay đổi khóa trong heap** yêu cầu biết **vị trí hiện tại** của phần tử. Với **min-heap**, giảm khóa dùng **`sift-up`**, tăng khóa dùng **`sift-down`**; với **max-heap**, đảo chiều. **Xóa tùy ý** phải đưa **phần tử cuối** vào ô bị xóa để giữ hình dạng cây hoàn chỉnh, sau đó chọn **đẩy lên hoặc đẩy xuống** theo vị trí vi phạm. Khi đã biết chỉ số, các thao tác sửa và xóa thường mất **`O(\log n)` thời gian, `O(1)` bộ nhớ phụ**. Nhưng nếu người gọi chỉ biết **ID**, heap không tự giúp tìm vị trí: quét tuyến tính là `O(n)`. Có thể bổ sung **indexed heap `id\to index`** với bảng băm `O(n)` bộ nhớ và cập nhật mapping sau **mọi lần hoán đổi**, hoặc dùng **lazy deletion** để khỏi sửa tại chỗ, đổi lại phải quản lý bản ghi lỗi thời và bộ nhớ tích lũy. Chọn thiết kế theo tần suất cập nhật, yêu cầu xóa ngay, tính ổn định của khóa và chính sách sở hữu dữ liệu.
